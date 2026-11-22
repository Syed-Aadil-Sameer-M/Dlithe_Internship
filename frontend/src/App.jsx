
import { useState } from "react";
import "./styles.css";
import { mockStoreProfile } from "./services/mockApi";
import ResearchStatus from "./components/ResearchStatus";

function App() {
  const [storeInput, setStoreInput] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!storeInput.trim()) {
      setError("Please enter a store name or website URL.");
      setResult(null);
      return;
    }

    setError("");
    setResult(null);
    setLoading(true);

    try {
      // TEMPORARY: Using illustrative mock data.
      // Replace this with the actual API call after DEV1
      // shares the confirmed API contract.
      await new Promise((resolve) => setTimeout(resolve, 1000));

      setResult({
        ...mockStoreProfile,
        storeUrl: storeInput.trim(),
      });
    } catch {
      setError("Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
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
                setResult(null);
              }}
            />

            {error && <p className="error">{error}</p>}

            <button type="submit" disabled={loading}>
              {loading ? "Researching..." : "Research Store"}
            </button>
          </form>

          <ResearchStatus
  status={loading ? "crawling" : result?.status || "idle"}
/>

{result && (
  <div className="result-message">
    <h3>Mock Research Completed</h3>
    <p><strong>Store:</strong> {result.storeName}</p>
    <p><strong>URL:</strong> {result.storeUrl}</p>
    <p><strong>Status:</strong> {result.status}</p>
    <p>{result.message}</p>
    <small>
      This is temporary sample data, not actual store research.
        </small>
      </div>
      )}
        </section>
      </main>

      <footer>
        <p>Store Research Tool | E-Commerce Intelligence</p>
      </footer>
    </div>
  );
}

export default App;
