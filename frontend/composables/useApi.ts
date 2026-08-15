type ApiFetchOptions<T> = Parameters<typeof $fetch<T>>[1];

export function useApi() {
  async function apiFetch<T>(
    path: string,
    options?: ApiFetchOptions<T>,
  ) {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;

    return await $fetch<T>(`/api${normalizedPath}`, {
      ...options,
    });
  }

  function getErrorMessage(
    error: unknown,
    fallback = "Something went wrong.",
  ): string {
    if (
      error
      && typeof error === "object"
      && "data" in error
      && error.data
      && typeof error.data === "object"
    ) {
      const data = error.data as Record<string, unknown>;

      if (typeof data.detail === "string") {
        return data.detail;
      }

      const firstValue = Object.values(data)[0];

      if (typeof firstValue === "string") {
        return firstValue;
      }

      if (Array.isArray(firstValue) && typeof firstValue[0] === "string") {
        return firstValue[0];
      }
    }

    if (error instanceof Error) {
      return error.message;
    }

    return fallback;
  }

  return {
    apiFetch,
    getErrorMessage,
  };
}
