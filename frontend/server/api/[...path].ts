import {
  appendResponseHeader,
  createError,
  getRequestHeaders,
  getRequestURL,
  readRawBody,
  setResponseStatus,
} from "h3";

const hopByHopHeaders = new Set([
  "connection",
  "content-length",
  "host",
  "transfer-encoding",
]);

export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event);
  const requestUrl = getRequestURL(event);
  const targetUrl = new URL(
    requestUrl.pathname + requestUrl.search,
    config.backendOrigin,
  );
  const headers = new Headers(getRequestHeaders(event));

  for (const header of hopByHopHeaders) {
    headers.delete(header);
  }

  const body = event.method === "GET" || event.method === "HEAD"
    ? undefined
    : await readRawBody(event, false);

  let response: Response;

  try {
    response = await fetch(targetUrl, {
      method: event.method,
      headers,
      body,
      redirect: "manual",
    });
  } catch {
    throw createError({
      statusCode: 502,
      statusMessage: "Backend unavailable",
      data: {
        detail: "The backend could not be reached.",
      },
    });
  }

  setResponseStatus(event, response.status, response.statusText);

  response.headers.forEach((value, key) => {
    if (!hopByHopHeaders.has(key.toLowerCase()) && key.toLowerCase() !== "set-cookie") {
      appendResponseHeader(event, key, value);
    }
  });

  if (typeof response.headers.getSetCookie === "function") {
    for (const cookie of response.headers.getSetCookie()) {
      appendResponseHeader(event, "set-cookie", cookie);
    }
  }

  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const responseBody = await response.text();

    if (!responseBody) {
      return null;
    }

    try {
      return JSON.parse(responseBody) as unknown;
    } catch {
      throw createError({
        statusCode: 502,
        statusMessage: "Invalid backend response",
        data: {
          detail: "The backend returned invalid JSON.",
        },
      });
    }
  }

  return await response.text();
});
