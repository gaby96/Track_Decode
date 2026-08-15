export function useCsrfToken() {
  const config = useRuntimeConfig();
  const csrfToken = useState<string>(
    "csrf-token",
    () => "",
  );

  async function getCsrfToken() {
    if (import.meta.server) {
      return "";
    }

    if (csrfToken.value) {
      return csrfToken.value;
    }

    const response = await $fetch<{ csrfToken: string }>(
      `${config.public.backendOrigin}/api/csrf/`,
      {
        credentials: "include",
      },
    );

    csrfToken.value = response.csrfToken;
    return csrfToken.value;
  }

  return {
    getCsrfToken,
  };
}
