import { useState, useEffect } from "react";
import { API_URL } from "./config";
import ChatMessage from "./ChatMessage";
import "./index.css";

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [phoneInput, setPhoneInput] = useState("");
  const [pendingPhone, setPendingPhone] = useState(null);
  const [pendingDecision, setPendingDecision] = useState(null);
  const [pendingRegistration, setPendingRegistration] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [currentWorkflowId, setCurrentWorkflowId] = useState(null);
  const [prescriptionUrl, setPrescriptionUrl] = useState(null);
  const [workflowStatus, setWorkflowStatus] = useState(null);
  const [pollingInterval, setPollingInterval] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  
  // Add this state to track which messages have been shown
  const [shownMessages, setShownMessages] = useState(new Set());

  const [registrationData, setRegistrationData] = useState({
    name: "",
    gender: "",
    age: "",
    address: ""
  });

  // Cleanup polling on component unmount
  useEffect(() => {
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [pollingInterval]);

  // Start polling for prescription/workflow status
  const startPolling = (workflowId) => {
    if (isPolling) return; // Prevent multiple polling intervals
    
    setIsPolling(true);
    console.log("Starting polling for workflow:", workflowId);
    
    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/check_prescription/${workflowId}`);
        const data = await response.json();

        console.log("Polling response:", data);

        // Create a unique key for each message type to prevent duplicates
        const messageKey = `${workflowId}-${data.status}`;

        // Handle different statuses from the backend
        if (data.status === "prescription_ready" && data.prescription_url) {
          if (!shownMessages.has(messageKey)) {
            setPrescriptionUrl(data.prescription_url);
            setMessages((prev) => [
              ...prev,
              { role: "bot", content: data.response, prescriptionUrl: data.prescription_url }
            ]);
            setShownMessages(prev => new Set([...prev, messageKey]));
          }
        } else if (data.status === "consultation_in_progress") {
          if (!shownMessages.has(messageKey)) {
            setMessages((prev) => [
              ...prev,
              { role: "bot", content: data.response }
            ]);
            setShownMessages(prev => new Set([...prev, messageKey]));
          }
        } else if (data.status === "finalizing_prescription") {
          if (!shownMessages.has(messageKey)) {
            setMessages((prev) => [
              ...prev,
              { role: "bot", content: data.response }
            ]);
            setShownMessages(prev => new Set([...prev, messageKey]));
          }
        } else if (data.status === "adding_to_queue") {
          if (!shownMessages.has(messageKey)) {
            setMessages((prev) => [
              ...prev,
              { role: "bot", content: data.response }
            ]);
            setShownMessages(prev => new Set([...prev, messageKey]));
          }
        } else if (data.status === "completed") {
          setMessages((prev) => [
            ...prev,
            { role: "bot", content: data.response }
          ]);
          clearInterval(interval);
          setPollingInterval(null);
          setCurrentWorkflowId(null);
          setIsPolling(false);
          setShownMessages(new Set()); // Clear shown messages for next session
        } else if (data.status === "error") {
          setMessages((prev) => [
            ...prev,
            { role: "bot", content: data.response }
          ]);
          clearInterval(interval);
          setPollingInterval(null);
          setCurrentWorkflowId(null);
          setIsPolling(false);
          setShownMessages(new Set()); // Clear shown messages for next session
        }
      } catch (error) {
        console.error("Error polling prescription status:", error);
        clearInterval(interval);
        setPollingInterval(null);
        setCurrentWorkflowId(null);
        setIsPolling(false);
        setShownMessages(new Set()); // Clear shown messages for next session
      }
    }, 3000); // 3-second interval (faster for better UX)

    setPollingInterval(interval);
  };

  // Stop polling
  const stopPolling = () => {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      setPollingInterval(null);
    }
    setIsPolling(false);
  };

  const sendMessage = async () => {
    if (!input.trim()) return;
    setIsLoading(true);
    const newMsg = { role: "user", content: input };
    setMessages((prev) => [...prev, newMsg]);
    setInput("");

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: input }),
      });
      const data = await res.json();

      setMessages((prev) => [...prev, { role: "bot", content: data.response }]);

      if (data.requires_phone) {
        setPendingPhone({ workflow_id: data.workflow_id });
        setCurrentWorkflowId(data.workflow_id);
      }

    } catch (error) {
      setMessages((prev) => [...prev, { role: "bot", content: "Server error. Please try again." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const submitPhone = async () => {
    if (!phoneInput.trim() || !pendingPhone) return;
    setIsLoading(true);
    
    setMessages((prev) => [...prev, { role: "user", content: `📱 Phone: ${phoneInput}` }]);

    try {
      const res = await fetch(`${API_URL}/phone`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: pendingPhone.workflow_id,
          phone_number: phoneInput
        }),
      });
      const data = await res.json();

      setMessages((prev) => [...prev, { role: "bot", content: data.response }]);
      setPendingPhone(null);
      setPhoneInput("");

      // Handle different response types
      if (data.requires_decision) {
        setPendingDecision({
          workflow_id: data.workflow_id,
          wait_time: data.wait_time,
          patient_name: data.patient_name
        });
      } else if (data.requires_registration) {
        setPendingRegistration({
          workflow_id: data.workflow_id,
          phone_number: phoneInput
        });
      } else if (data.requires_prescription_check) {
        // This is the key fix - start polling for patients with appointments
        console.log("Starting prescription polling for workflow:", data.workflow_id);
        startPolling(data.workflow_id);
      }

    } catch (error) {
      setMessages((prev) => [...prev, { role: "bot", content: "Error processing phone number. Please try again." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const submitRegistration = async () => {
    const { name, gender, age, address } = registrationData;
    if (!name || !gender || !age || !address || !pendingRegistration) return;
    setIsLoading(true);

    setMessages((prev) => [...prev, { 
      role: "user", 
      content: `Registration: ${name}, ${gender}, ${age}, ${address}` 
    }]);

    try {
      const res = await fetch(`${API_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: pendingRegistration.workflow_id,
          ...registrationData
        }),
      });
      const data = await res.json();

      setMessages((prev) => [...prev, { role: "bot", content: data.response }]);
      setPendingRegistration(null);
      setRegistrationData({ name: "", gender: "", age: "", address: "" });

      if (data.requires_decision) {
        setPendingDecision({
          workflow_id: data.workflow_id,
          wait_time: data.wait_time,
          patient_name: data.patient_name
        });
      }

    } catch (error) {
      setMessages((prev) => [...prev, { role: "bot", content: "Error processing registration. Please try again." }]);
    } finally {
      setIsLoading(false);
    }
  };

  const makeDecision = async (decision) => {
    if (!pendingDecision) return;
    setIsLoading(true);

    const decisionText = decision === "continue" ? "Continue (Wait in Queue)" : "Book for Later";
    setMessages((prev) => [...prev, { role: "user", content: `Decision: ${decisionText}` }]);

    try {
      const res = await fetch(`${API_URL}/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_id: pendingDecision.workflow_id,
          decision
        }),
      });
      const data = await res.json();

      // Add the initial response message
      setMessages((prev) => [...prev, { 
        role: "bot", 
        content: data.response,
        prescriptionUrl: data.prescription_url
      }]);
      
      // Handle different response states
      if (data.prescription_url) {
        setPrescriptionUrl(data.prescription_url);
      }

      // Clear pending decision
      setPendingDecision(null);

      // If continuing with appointment, start polling for updates
      if (decision === "continue" && data.requires_prescription_check) {
        console.log("Starting prescription polling after decision");
        startPolling(currentWorkflowId);
      } else if (decision === "book_later") {
        // For "book_later", clear the workflow
        setCurrentWorkflowId(null);
      }

    } catch (error) {
      setMessages((prev) => [...prev, { role: "bot", content: "Error processing decision. Please try again." }]);
    } finally {
      setIsLoading(false);
    }
  };

  // Reset all states for a new conversation
  const resetChat = () => {
    stopPolling();
    setMessages([]);
    setInput("");
    setPhoneInput("");
    setPendingPhone(null);
    setPendingDecision(null);
    setPendingRegistration(null);
    setCurrentWorkflowId(null);
    setPrescriptionUrl(null);
    setWorkflowStatus(null);
    setRegistrationData({ name: "", gender: "", age: "", address: "" });
    setShownMessages(new Set()); // Clear shown messages
  };

  const isInputDisabled = isLoading || pendingPhone || pendingDecision || pendingRegistration;

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>🏥 Clinic Reception System</h2>
        <p>Enter doctor name to check availability</p>
        {currentWorkflowId && (
          <div className="workflow-status">
            <span className="workflow-id">Session: {currentWorkflowId.slice(-8)}</span>
            {isPolling && <span className="polling-indicator">● Monitoring</span>}
          </div>
        )}
      </div>

      <div className="chat-box">
        {messages.map((msg, index) => (
          <ChatMessage key={index} message={msg} />
        ))}

        {isLoading && (
          <div className="loading-message">
            <div className="message bot">
              <div className="message-bubble">
                <div className="loading-dots">
                  <strong>Bot:</strong> Processing... 
                  <span className="dots">
                    <span></span>
                    <span></span>
                    <span></span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Show workflow status if polling */}
        {isPolling && (
          <div className="status-indicator">
            <div className="status-content">
              <div className="status-spinner"></div>
              <p>🔄 Monitoring your appointment progress...</p>
              <small>We'll automatically update you on the next steps</small>
            </div>
          </div>
        )}
      </div>

      {pendingPhone && (
        <div className="phone-panel">
          <div className="phone-content">
            <h3>📱 Phone Number Required</h3>
            <p>Please enter your phone number to check for existing appointments and patient records:</p>
            <div className="phone-input-group">
              <input
                type="tel"
                placeholder="Enter phone number (e.g., +1234567890)"
                value={phoneInput}
                onChange={(e) => setPhoneInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !isLoading && submitPhone()}
                disabled={isLoading}
                className="phone-input"
              />
              <button
                onClick={submitPhone}
                disabled={isLoading || !phoneInput.trim()}
                className="phone-submit-btn"
              >
                {isLoading ? "Verifying..." : "Submit"}
              </button>
            </div>
            <p className="phone-help">
              We'll check if you have any existing appointments or need to register as a new patient
            </p>
          </div>
        </div>
      )}

      {pendingRegistration && (
        <div className="registration-panel">
          <div className="registration-content">
            <h3>New Patient Registration</h3>
            <p>Phone number not found in our system. Please register as a new patient:</p>
            <div className="registration-form">
              <div className="form-column">
                <div className="form-group">
                  <label>Full Name: <span className="required">*</span></label>
                  <input
                    type="text"
                    placeholder="Enter your full name"
                    value={registrationData.name}
                    onChange={(e) => setRegistrationData(prev => ({ ...prev, name: e.target.value }))}
                    disabled={isLoading}
                  />
                </div>
                <div className="form-group">
                  <label>Age: <span className="required">*</span></label>
                  <input
                    type="number"
                    placeholder="Enter your age"
                    min="1"
                    max="120"
                    value={registrationData.age}
                    onChange={(e) => setRegistrationData(prev => ({ ...prev, age: e.target.value }))}
                    disabled={isLoading}
                  />
                </div>
              </div>
              <div className="form-column">
                <div className="form-group">
                  <label>Gender: <span className="required">*</span></label>
                  <select
                    value={registrationData.gender}
                    onChange={(e) => setRegistrationData(prev => ({ ...prev, gender: e.target.value }))}
                    disabled={isLoading}
                  >
                    <option value="">Select Gender</option>
                    <option value="Male">Male</option>
                    <option value="Female">Female</option>
                    <option value="Other">Other</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Address: <span className="required">*</span></label>
                  <textarea
                    placeholder="Enter your complete address"
                    value={registrationData.address}
                    onChange={(e) => setRegistrationData(prev => ({ ...prev, address: e.target.value }))}
                    disabled={isLoading}
                    rows="3"
                  />
                </div>
              </div>
            </div>
            <button
              onClick={submitRegistration}
              disabled={
                isLoading ||
                !registrationData.name.trim() ||
                !registrationData.gender ||
                !registrationData.age ||
                !registrationData.address.trim()
              }
              className="registration-submit-btn"
            >
              {isLoading ? "Registering..." : "Complete Registration"}
            </button>
            <p className="registration-help">
              All fields are required. This information will be used for your medical records.
            </p>
          </div>
        </div>
      )}

      {pendingDecision && (
        <div className="decision-panel">
          <div className="decision-content">
            <h3>Decision Required</h3>
            <div className="decision-info">
              <p><strong>👤 Patient:</strong> {pendingDecision.patient_name}</p>
              <p><strong>Estimated wait time:</strong> {pendingDecision.wait_time} minutes</p>
              <p><strong>No scheduled appointment found for today</strong></p>
              <p>What would you like to do?</p>
            </div>
            <div className="decision-buttons">
              <button
                className="btn-continue"
                onClick={() => makeDecision("continue")}
                disabled={isLoading}
              >
                <span className="btn-icon">⏳</span>
                <span className="btn-text">Continue (Wait in Queue)</span>
                <span className="btn-subtext">Join walk-in queue</span>
              </button>
              <button
                className="btn-book-later"
                onClick={() => makeDecision("book_later")}
                disabled={isLoading}
              >
                <span className="btn-icon">📅</span>
                <span className="btn-text">Book for Later</span>
                <span className="btn-subtext">Schedule appointment</span>
              </button>
            </div>
            <p className="decision-help">
              If you continue, you'll be added to the walk-in queue and receive a prescription slip
            </p>
          </div>
        </div>
      )}

      <div className="chat-input">
        <input
          type="text"
          placeholder={isInputDisabled ? "Please complete the current step..." : "Enter doctor name (e.g., Smith, Johnson)"}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !isInputDisabled && sendMessage()}
          disabled={isInputDisabled}
        />
        <button onClick={sendMessage} disabled={isInputDisabled || !input.trim()}>
          {isLoading ? "Sending..." : "Send"}
        </button>
        {messages.length > 0 && (
          <button onClick={resetChat} className="reset-btn" disabled={isLoading}>
            🔄 New Chat
          </button>
        )}
      </div>
    </div>
  );
}

export default App;