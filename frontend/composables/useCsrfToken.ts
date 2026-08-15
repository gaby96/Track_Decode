export function useCsrfToken() {
  function getCsrfToken() {
    if (import.meta.server) {
      return "";
    }

    const match = document.cookie.match(
      /(?:^|;\s*)csrftoken=([^;]+)/,
    );

    return match ? decodeURIComponent(match[1]) : "";
  }

  return {
    getCsrfToken,
  };
}
