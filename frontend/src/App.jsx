
import { useState } from "react";
import "./styles.css";

function App() {
  const [storeInput, setStoreInput] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();

    if (!storeInput.trim()) {
      setError("Please enter a store name or website URL.");
      return;
    }

    setError("");
    alert("Store input submitted successfully!");
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Store Research Tool</h1>
        <p>Smart insights for e-commerce store research</p>
      </header>

      <main className="main-container">
        <section className="search-card">
          <h2>Research an E-Commerce Store</h2>

          <p>
            Enter a store name or website URL to discover
            useful information about the store.
          </p>

          <form onSubmit={handleSubmit}>
            <label htmlFor="storeInput">
              Store Name or Website URL
            </label>

            <input
              id="storeInput"
              type="text"
              placeholder="Example: https://example.com"
              value={storeInput}
              onChange={(e) => {
                setStoreInput(e.target.value);
                setError("");
              }}
            />

            {error && <p className="error">{error}</p>}

            <button type="submit">
              Research Store
            </button>
          </form>
        </section>
      </main>

      <footer>
        <p>Store Research Tool | E-Commerce Intelligence</p>
      </footer>
    </div>
  );
}

export default App;
