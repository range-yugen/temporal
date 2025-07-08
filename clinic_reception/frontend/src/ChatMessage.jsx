const ChatMessage = ({ message }) => {
  return (
    <div className={`message ${message.role}`}>
      <div className="message-bubble">
        <strong>{message.role === "user" ? "You" : "Bot"}:</strong>{" "}
        {message.content.split(" ").map((word, index) =>
          word.startsWith("http") ? (
            <a key={index} href={word} target="_blank" rel="noopener noreferrer">
              {word}
            </a>
          ) : (
            word + " "
          )
        )}
      </div>
    </div>
  );
};

export default ChatMessage;
