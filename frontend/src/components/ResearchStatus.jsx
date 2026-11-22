
const statusMessages = {
  idle: {
    title: "Ready to research",
    message: "Enter a store name or URL to get started.",
  },
  validating: {
    title: "Validating store",
    message: "Checking the submitted store details...",
  },
  queued: {
    title: "Research queued",
    message: "Your research request is waiting to start.",
  },
  crawling: {
    title: "Research in progress",
    message: "Collecting information from accessible public pages.",
  },
  processing: {
    title: "Processing results",
    message: "Organising the collected research information.",
  },
  succeeded: {
    title: "Research completed",
    message: "The research process has completed.",
  },
  blocked: {
    title: "Access blocked",
    message: "The website could not be accessed. Try another public store URL.",
  },
  unavailable: {
    title: "Service unavailable",
    message: "The research service is currently unavailable. Please try again later.",
  },
  failed: {
    title: "Research failed",
    message: "Something went wrong. Please try again.",
  },
};

function ResearchStatus({ status = "idle" }) {
  const currentStatus = statusMessages[status] || {
    title: "Unknown status",
    message: "The research status is not recognised. Please try again later.",
  };

  return (
    <section className={`research-status ${status}`}>
      <h3>{currentStatus.title}</h3>
      <p>{currentStatus.message}</p>
    </section>
  );
}

export default ResearchStatus;
