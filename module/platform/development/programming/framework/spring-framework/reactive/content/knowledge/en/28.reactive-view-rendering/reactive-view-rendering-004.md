# Distinguishing Waiting for Model Completion from Incremental Rendering in Spring WebFlux

> **Module:** Spring Framework – reactive · **Parent topic:** View Rendering. This lesson designs two experiences for the same content-generation task: waiting for the model to return a complete result and displaying it once, or emitting incrementally so the UI updates as the model produces content. The focus is on `Mono` and `Flux`, choosing the right HTTP media type, sending Server-Sent Events (SSE), updating the UI safely, handling errors/cancellation/backpressure, and testing that data truly arrives before the model completes.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish the moment the model completes from the moment the UI begins displaying results.
2. Explain why `Mono<T>` fits a final result, while `Flux<T>` fits a sequence of data chunks.
3. Understand that returning `Flux` alone is not enough to guarantee the browser sees chunks incrementally; you must choose a streaming format such as `text/event-stream` or `application/x-ndjson`.
4. Design an SSE event contract with `start`, `delta`, `completed`, and `error`.
5. Build a WebFlux backend with both a wait-for-completion mode and a streaming mode.
6. Use `fetch()` and `ReadableStream` to send a prompt via POST, parse SSE frames, and append deltas in order.
7. Cancel model generation when the user stops or closes the UI.
8. Handle errors before the response is committed and errors occurring after the stream has started.
9. Maintain backpressure, output limits, heartbeats, and timeouts so the stream operates reliably.
10. Write tests proving that the first delta is emitted before the completion event and that cancellation propagates back to the model publisher.

**Core point:** reactive is how asynchronous work and data streams are handled in the backend; streaming is a decision about the protocol and how the UI consumes data. An endpoint returning `Mono` can still be completely non-blocking yet provide only one final result. An endpoint returning `Flux` only delivers an incremental rendering experience when the codec, HTTP response, proxy, and frontend all preserve the stream.

## 2. Two Different Experiences

Suppose a user submits a prompt to a model and the model generates a long answer. There are two ways to structure the flow:

| Criterion | Wait for model completion | Incremental display |
| --- | --- | --- |
| Backend return type | Usually `Mono<GenerationResult>` | Usually `Flux<ServerSentEvent<...>>` |
| HTTP response | A single complete JSON document | A long-lived event stream |
| First time user sees content | After the model completes and the response is sent | When the first delta reaches the browser |
| UI state | Loading → Completed or Failed | Connecting → Streaming → Completed/Failed/Cancelled |
| Mid-generation error | Can return an HTTP error before the body completes | Usually sends an `error` event in the already-open stream |
| Memory | Usually must hold the entire final result in memory | Can process each delta, though UI buffers must still be bounded |
| Cancellation | Cancel the request before the result is returned | Can cancel immediately while receiving deltas |
| Best suited for | Short results requiring full validation before display | Chat, long generation, progress, logs, or tasks with continuous output |

The two approaches do not mean one is "reactive" and the other is "blocking". `Mono` is not synonymous with `block()`. The backend can wait for the model to finish using a non-blocking `Mono` pipeline; the difference is that the UI only receives a single result once the publisher completes.

### 2.1. Wait for Completion: A Single Result

~~~text
Browser                    WebFlux                     Model
   |                          |                           |
   | POST prompt              |                           |
   |------------------------->| calls model               |
   |                          |-------------------------->|
   |                          |       token 1              |
   |                          |<--------------------------|
   |                          |       token 2              |
   |                          |<--------------------------|
   |                          |       token ...            |
   |                          |<--------------------------|
   |                          |       model complete       |
   |                          |<--------------------------|
   |       final JSON         |                           |
   |<-------------------------|                           |
   | display full output      |                           |
~~~

While the model generates tokens, the backend may already receive data incrementally yet still aggregate them into a single result. The user sees a spinner or a "Generating…" status until the final JSON arrives.

### 2.2. Streaming: The UI Receives Each Delta

~~~text
Browser                    WebFlux                     Model
   |                          |                           |
   | POST prompt              |                           |
   |------------------------->|                           |
   | event: start             | calls model stream        |
   |<-------------------------|-------------------------->|
   | event: delta             |<---------- token 1         |
   |<-------------------------|                           |
   | append text              |                           |
   | event: delta             |<---------- token 2         |
   |<-------------------------|                           |
   | append text              |                           |
   | event: delta             |<---------- token ...       |
   |<-------------------------|                           |
   | event: completed         |<---------- complete        |
   |<-------------------------|                           |
   | mark completed           |                           |
~~~

The UI can display content while the model is still working. Each delta is typically a segment of characters or tokens; it is not necessarily a complete word or a complete sentence.

## 3. Understanding `Mono`, `Flux`, and HTTP Media Types

### 3.1. `Mono<T>`: Emits Only the Final Result

Use `Mono<GenerationResult>` when the API contract is a single complete object:

~~~java
public Mono<GenerationResult> generateComplete(String prompt) {
    return modelGateway.stream(prompt)
        .collect(
            StringBuilder::new,
            (result, part) -> result.append(part)
        )
        .map(result ->
            new GenerationResult(result.toString()));
}
~~~

`collect` waits for the source publisher to complete before emitting `GenerationResult`. While waiting, Reactor does not need to block the event-loop. However, the entire content is held in `StringBuilder`, so token count or output size must be bounded.

### 3.2. `Flux<T>` Alone Does Not Guarantee UI Streaming

A subtle detail: if you return `Flux<GenerationChunk>` with `application/json`, WebFlux's Jackson encoder by default collects the items into a `List` and serializes them as a JSON array. The browser may only receive a single complete JSON document.

To emit records incrementally, choose a media type with explicit streaming framing:

| Media type | Delivery | Use when |
| --- | --- | --- |
| `application/json` | A single JSON document/array; multi-value publishers may be collected by default | Complete results |
| `text/event-stream` | SSE frames, each event written and flushed | Chat, progress, events with names and IDs |
| `application/x-ndjson` | Each JSON object is an independent line | Structured record streams, easy line-by-line parsing |
| `text/plain` | Plain text content | Simple text streams, when both sides have a clear framing convention |

For chat UIs, SSE is often convenient because each event can carry a name such as `start`, `delta`, `completed`, or `error`. NDJSON works well when each chunk is a schema-defined object and the frontend reads line by line.

Never treat TCP packet boundaries or HTTP chunks as model token boundaries. One packet can contain multiple deltas; a single delta can also be split across multiple `reader.read()` calls. The application must parse according to protocol framing.

### 3.3. How Does Spring WebFlux Write SSE?

A controller can return:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<ProgressEvent>> events() {
    return progressPublisher();
}
~~~

Spring uses `ServerSentEventHttpMessageWriter` to serialize events. With SSE, the encoder processes and flushes each event so it is sent without waiting for the entire stream. Spring Framework also recommends sending data periodically, such as comment-only events, to detect disconnected clients earlier.

Further reading:
- Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Controller return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html

## 4. Designing an Event Contract for Model Streams

Do not send untyped strings and force the frontend to guess when the model started, finished, or failed. Define an explicit contract.

Sample stream:

~~~text
id: gen-123:1
event: start
data: {"text":"","code":null}

id: gen-123:2
event: delta
data: {"text":"Hello ","code":null}

id: gen-123:3
event: delta
data: {"text":"there, ","code":null}

id: gen-123:4
event: delta
data: {"text":"friend!","code":null}

id: gen-123:5
event: completed
data: {"text":"","code":null}

~~~

If the model fails after sending part of the output:

~~~text
id: gen-123:3
event: delta
data: {"text":"Partial content","code":null}

id: gen-123:4
event: error
data: {"text":"","code":"MODEL_UNAVAILABLE"}

~~~

Core events:

| Event | Meaning | What the UI should do |
| --- | --- | --- |
| `start` | Server accepted the generation and opened the stream | Clear old output, display generating state |
| `delta` | More text arrived from the model | Append text to current output |
| `completed` | Model finished normally | Mark completed, enable actions that use the result |
| `error` | Generation failed after the stream started | Keep received portion, report incomplete result |
| `heartbeat` | Server is keeping the stream alive | Make no content changes |
| `metadata` | Auxiliary info such as model, usage, or finish reason | Update metadata section, do not append to text |

`id` is the event sequence ID. It is useful for logging and resuming, though sending an ID alone does not automatically enable resume. To resume a stream after reconnect, the server must persist event history or generation state and handle `Last-Event-ID`/cursors accordingly.

For models with tool calling, you can add dedicated events such as `tool_started`, `tool_result`, or `status`. Do not dump internal tool JSON arguments into the text area visible to users.

## 5. Backend Example: Two Endpoints for Two Modes

We will build two endpoints sharing one `ModelGateway`:

- `POST /api/generations/complete` returns `Mono<GenerationResult>` once the model completes.
- `POST /api/generations` returns `Flux<ServerSentEvent<GenerationEvent>>` so the UI receives each delta.

`ModelGateway` is the model provider abstraction. The example uses a simulated publisher so the project runs standalone; in production, replace the implementation with the model's actual streaming SDK/API.

### 5.1. ModelGateway.java

~~~java
package com.example.generation;

import reactor.core.publisher.Flux;

public interface ModelGateway {

    Flux<String> stream(String prompt);
}
~~~

Each `String` element is a delta decoded by the adapter from the model provider. Do not assume each element corresponds to exactly one token: the provider may batch multiple tokens or split a word across multiple segments.

### 5.2. DemoModelGateway.java

~~~java
package com.example.generation;

import java.time.Duration;

import org.springframework.stereotype.Component;

import reactor.core.publisher.Flux;

@Component
public class DemoModelGateway implements ModelGateway {

    @Override
    public Flux<String> stream(String prompt) {
        if ("fail".equalsIgnoreCase(prompt.trim())) {
            return Flux.concat(
                Flux.just("Partial content has been generated."),
                Flux.error(new IllegalStateException(
                    "internal model provider detail"))
            );
        }

        return Flux.just(
                "The model ",
                "is replying ",
                "incrementally."
            )
            .delayElements(Duration.ofMillis(180));
    }
}
~~~

`delayElements` only makes the difference between waiting for completion and streaming visible when running the demo. A real model provider emits deltas at its generation pace.

### 5.3. DTOs

`GenerationRequest.java`:

~~~java
package com.example.generation;

public record GenerationRequest(String prompt) {}
~~~

`GenerationResult.java`:

~~~java
package com.example.generation;

public record GenerationResult(String text) {}
~~~

`GenerationEvent.java`:

~~~java
package com.example.generation;

public record GenerationEvent(String text, String code) {}
~~~

Event payloads should contain only the information the UI needs. Do not include stack traces, raw exception messages, API keys, or internal provider data in events.

### 5.4. GenerationController.java

~~~java
package com.example.generation;

import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
public class GenerationController {

    private static final Logger log =
        LoggerFactory.getLogger(GenerationController.class);

    private final ModelGateway modelGateway;

    public GenerationController(ModelGateway modelGateway) {
        this.modelGateway = modelGateway;
    }

    @PostMapping(
        value = "/api/generations/complete",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<GenerationResult> complete(
            @RequestBody GenerationRequest request) {

        validate(request);

        return Flux.defer(() ->
                modelGateway.stream(request.prompt()))
            .collect(
                StringBuilder::new,
                (result, part) -> result.append(part)
            )
            .map(result ->
                new GenerationResult(result.toString()));
    }

    @PostMapping(
        value = "/api/generations",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<GenerationEvent>> stream(
            @RequestBody GenerationRequest request) {

        validate(request);

        String requestId = UUID.randomUUID().toString();
        AtomicLong sequence = new AtomicLong();

        Flux<ServerSentEvent<GenerationEvent>> start =
            Flux.just(event(
                requestId, sequence, "start", "", null));

        Flux<ServerSentEvent<GenerationEvent>> deltas =
            Flux.defer(() ->
                    modelGateway.stream(request.prompt()))
                .map(part -> event(
                    requestId, sequence, "delta", part, null));

        Flux<ServerSentEvent<GenerationEvent>> completed =
            Flux.just(event(
                requestId, sequence, "completed", "", null));

        return Flux.concat(start, deltas, completed)
            .doOnError(error ->
                log.warn(
                    "generation_failed requestId={} exceptionType={}",
                    requestId,
                    error.getClass().getSimpleName()))
            .onErrorResume(error ->
                Flux.just(event(
                    requestId,
                    sequence,
                    "error",
                    "",
                    "MODEL_UNAVAILABLE")))
            .doOnCancel(() ->
                log.info(
                    "generation_cancelled requestId={}",
                    requestId));
    }

    private static void validate(GenerationRequest request) {
        if (request == null
                || request.prompt() == null
                || request.prompt().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "prompt must not be blank");
        }
    }

    private static ServerSentEvent<GenerationEvent> event(
            String requestId,
            AtomicLong sequence,
            String eventName,
            String text,
            String code) {

        String eventId =
            requestId + ":" + sequence.incrementAndGet();

        return ServerSentEvent.<GenerationEvent>builder(
                new GenerationEvent(text, code))
            .id(eventId)
            .event(eventName)
            .build();
    }
}
~~~

Points to note:

1. `complete()` aggregates deltas into `StringBuilder`; it emits a single `GenerationResult` only after the publisher completes.
2. `stream()` uses `Flux.concat` to emit `start`, then each `delta`, and finally `completed`.
3. `Flux.defer` invokes the model gateway upon subscription and brings errors thrown during publisher creation into the reactive chain.
4. `onErrorResume` translates model errors into a safe `error` event. The frontend knows generation failed without receiving raw exception messages.
5. `doOnCancel` logs cancelled requests. HTTP response cancellation propagates upstream through `Flux`; the model adapter must connect that cancellation to the SDK/provider to actually stop generation.
6. `requestId` and sequence IDs help correlate logs with events without logging prompts or model content.

Validation runs before the stream starts, so invalid requests can receive HTTP 400. Errors occurring after the `start` event are represented by an `error` event.

## 6. Why Do Streaming Errors Need a Dedicated Event?

HTTP status codes and error bodies are clear when the server has not sent a response body yet. Once SSE begins and the first event is flushed, the response may already be committed. The server cannot go back to change status 200 to 500 and write a new JSON ProblemDetail into the same response.

Therefore, distinguish:

| Timing of error | Handling |
| --- | --- |
| Invalid prompt before stream opens | Return HTTP 400 |
| Unauthenticated/unauthorized request before stream opens | Return HTTP 401/403 |
| Unable to create model stream before first event | Return HTTP error if response is not yet committed |
| Model fails after one or more deltas | Emit SSE `error` with a stable code |
| Client disconnects | Cancel publisher and stop model call if provider supports it |
| Proxy/network closes stream without `completed` | UI marks the result as interrupted |

Do not emit a `completed` event when the model ends with an error. If the frontend encounters EOF without seeing `completed` or `error`, treat the stream as interrupted and do not mark the content as a complete result.

In `Mono` mode, if an error occurs before the result is serialized, the framework can produce an HTTP error response. In streaming mode, once the response is committed, errors must be carried inside the stream protocol.

## 7. Browser UI: POST with fetch and Parse SSE Frames

### 7.1. Why Use fetch for Prompts?

The browser's `EventSource` is convenient for GET SSE and provides automatic reconnect. However, the EventSource API cannot send a POST request body and does not allow setting arbitrary Authorization headers.

When the prompt must be sent in a JSON body, use `fetch()` with `POST`, `Accept: text/event-stream`, and read `response.body` via `ReadableStream`. If you want to use EventSource, an alternative design is to POST to create a generation/job and then use GET with a short ID to subscribe to the stream.

Do not place prompts, access tokens, or private data into the query string just to use EventSource; URLs frequently appear in proxy logs, browser history, and telemetry.

### 7.2. SSE Parser

SSE separates events with a blank line. One event can have multiple `data` lines; `id`, `event`, and `retry` are separate fields. Network chunks are not guaranteed to align with SSE frames, so incomplete frame data must be kept in a buffer.

~~~javascript
function parseSseFrame(frame) {
  let eventName = "message";
  const dataLines = [];

  for (const line of frame.split(/\r?\n/)) {
    if (line === "" || line.startsWith(":")) {
      continue;
    }

    const separator = line.indexOf(":");
    const field = separator < 0
      ? line
      : line.slice(0, separator);

    let value = separator < 0
      ? ""
      : line.slice(separator + 1);

    if (value.startsWith(" ")) {
      value = value.slice(1);
    }

    if (field === "event") {
      eventName = value;
    } else if (field === "data") {
      dataLines.push(value);
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  return {
    event: eventName,
    data: JSON.parse(dataLines.join("\n"))
  };
}
~~~

Comment-only heartbeats start with `:` and have no `data`, so the parser skips them. `TextDecoder` in the next step uses `{ stream: true }` to preserve UTF-8 characters properly if a multi-byte character is split across two reads.

### 7.3. Reading the Stream and Updating the UI

Suppose the page has two elements:

~~~html
<pre id="answer"></pre>
<p id="generation-status" role="status" aria-live="polite"></p>
~~~

JavaScript:

~~~javascript
async function generateIncrementally(
    prompt,
    outputElement,
    statusElement,
    abortSignal) {

  const response = await fetch("/api/generations", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Accept": "text/event-stream"
    },
    body: JSON.stringify({ prompt }),
    signal: abortSignal
  });

  if (!response.ok) {
    throw new Error(`Generation request failed: HTTP ${response.status}`);
  }

  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  let buffer = "";
  let fullText = "";
  let completed = false;
  let failed = false;

  function handleFrame(frame) {
    const parsed = parseSseFrame(frame);
    if (!parsed) {
      return;
    }

    switch (parsed.event) {
      case "start":
        fullText = "";
        outputElement.textContent = "";
        statusElement.textContent = "Generating content...";
        break;

      case "delta":
        fullText += parsed.data.text;
        // textContent avoids interpreting model content as HTML.
        outputElement.textContent = fullText;
        break;

      case "completed":
        completed = true;
        statusElement.textContent = "Completed";
        break;

      case "error":
        failed = true;
        statusElement.textContent =
          `Generation failed: ${parsed.data.code}`;
        break;
    }
  }

  try {
    while (true) {
      const { value, done } = await reader.read();

      buffer += decoder.decode(value, { stream: !done });
      buffer = buffer.replace(/\r\n/g, "\n");

      let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        handleFrame(frame);
      }

      if (done) {
        if (buffer.trim() !== "") {
          handleFrame(buffer);
        }
        break;
      }
    }

    if (!completed && !failed) {
      statusElement.textContent =
        "Stream ended before the model confirmed completion";
    }

    return {
      text: fullText,
      completed,
      failed
    };
  } finally {
    reader.releaseLock();
  }
}
~~~

This code appends each delta to `fullText` and updates `textContent`. It does not assume each `reader.read()` call yields one token. A single read can contain multiple events or part of an event; the parser only processes a frame once a frame delimiter arrives.

Use `textContent` for raw output. If Markdown needs to be rendered, accumulate the content and use a Markdown renderer that sanitizes HTML. In-progress Markdown may contain unfinished code fences or links; rendering HTML directly from each delta via `innerHTML` can break the layout and create XSS risks.

### 7.4. Cancel Button

Create one `AbortController` per generation:

~~~javascript
const controller = new AbortController();

const generationPromise = generateIncrementally(
  promptInput.value,
  document.querySelector("#answer"),
  document.querySelector("#generation-status"),
  controller.signal
);

document.querySelector("#cancel").addEventListener("click", () => {
  controller.abort();
});
~~~

In a real application, attach the listener once during UI initialization and clean it up after the request completes. When `abort()` is called, fetch is cancelled; the server receives cancellation when the transport closes and the reactive response publisher is cancelled. The model adapter must close the subscription or invoke the provider's cancel API.

Catch `AbortError` at the UI layer to display "Cancelled" instead of a generic network error message.

## 8. When Using EventSource Instead of fetch

EventSource is appropriate when the server already has a generation ID and the frontend only needs a GET subscription:

~~~javascript
const source = new EventSource(
  `/api/generations/${encodeURIComponent(generationId)}/events`
);

source.addEventListener("delta", event => {
  const data = JSON.parse(event.data);
  output.textContent += data.text;
});

source.addEventListener("completed", () => {
  status.textContent = "Completed";
  source.close();
});

source.addEventListener("error", event => {
  // Network errors and SSE error events must be distinguished
  // according to the application protocol.
  status.textContent = "Stream connection interrupted";
  source.close();
});
~~~

An SSE event with `id` can be resent by the browser via `Last-Event-ID` on reconnect. The server should only resume from that ID if it has stored event history and verifies generation ownership. If the generation cannot be resumed, report an interrupted state and ask the client to create a new request following idempotency policies.

With fetch POST, the browser does not provide EventSource's automatic reconnect; to resume, the frontend must store the generation ID/sequence and call a server-designed resume endpoint.

## 9. Choosing Between SSE and NDJSON

| Characteristic | SSE | NDJSON |
| --- | --- | --- |
| Framing | Events terminated by a blank line | One JSON object per line |
| Event name | Has an `event` field | Usually puts `type` inside JSON |
| Event ID/retry | Standard `id` and `retry` fields | Self-defined inside object |
| Browser API | `EventSource` supports GET | Use `fetch` and read line by line |
| Direction | Server → client | Server → client in normal responses |
| Fits | Chat, progress, status updates | Record streams, logs, schema-typed results |

NDJSON example:

~~~java
@PostMapping(
    value = "/api/generations/ndjson",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_NDJSON_VALUE)
public Flux<GenerationChunk> ndjson(
        @RequestBody GenerationRequest request) {

    validate(request);

    return Flux.defer(() ->
        modelGateway.stream(request.prompt()))
        .map(part -> new GenerationChunk("delta", part));
}
~~~

`GenerationChunk` can be:

~~~java
public record GenerationChunk(String type, String text) {}
~~~

With NDJSON, the frontend splits on `\n` and parses each line as JSON. Do not parse each `reader.read()` call directly as a JSON object because one line can be split across multiple reads.

## 10. Backpressure and Buffering

### 10.1. Keeping the Flow Reactive from Model to Response

The pipeline should look like:

~~~text
Model provider
    |
    v
Flux<String> delta
    |
    v
map / event envelope
    |
    v
Flux<ServerSentEvent<GenerationEvent>>
    |
    v
HttpMessageWriter
    |
    v
HTTP response
    |
    v
Browser ReadableStream
    |
    v
Append to UI
~~~

Reactive Streams backpressure coordinates demand between publishers and subscribers. Avoid collecting all deltas into a `List` or unbounded queue. If the UI or network reads slowly, the pipeline must keep pending data bounded.

### 10.2. Avoiding Operations That Break Streaming

The following operations cause results to appear only after upstream completes or hold the entire output in memory:

~~~java
modelGateway.stream(prompt)
    .collectList()
    .map(this::joinAll);
~~~

~~~java
modelGateway.stream(prompt)
    .blockLast();
~~~

~~~java
modelGateway.stream(prompt)
    .collect(
        StringBuilder::new,
        (builder, part) -> builder.append(part)
    );
~~~

The third example can be valid when intentionally implementing a wait-for-completion mode, but it is unsuitable for an endpoint intended to emit deltas incrementally.

Also avoid calling `subscribe()` manually inside a controller to push deltas into a shared variable. Return the publisher to WebFlux so the request lifecycle manages subscription, cancellation, and errors.

### 10.3. Limiting Output and Memory

Streaming reduces the need to hold the entire answer on the server, but that does not mean memory is automatically bounded at every layer. You should:

- Limit token count or output length at the model provider.
- Avoid storing the entire delta history in a collection if you only need to stream to the UI.
- Limit buffers in the browser and keep only necessary history.
- Set an overall timeout and an inter-event timeout.
- Limit concurrent generations per user/tenant.
- Cancel the provider subscription when the client disconnects.
- Avoid sending tiny deltas at excessively high frequency if batching chunks reduces overhead without noticeably hurting time-to-first-token.

## 11. Cancellation, Timeouts, and Heartbeats

### 11.1. Cancellation Must Reach the Model Provider

If the user clicks Stop, the desired cancellation path is:

1. The browser calls `AbortController.abort()`.
2. The HTTP request/response closes.
3. WebFlux cancels the subscription to the response publisher.
4. The controller's `Flux` is cancelled.
5. The model gateway cancels its subscription to the provider.
6. The provider stops generation and releases resources.

`doOnCancel` is only a hook for observing or logging; it does not automatically stop an external blocking operation. If the adapter calls a non-reactive SDK, retain a handle/cancel token and close it in cleanup.

Do not let a model call continue running and incurring charges after the browser has left the page unless the business workflow requires background generation.

### 11.2. Heartbeats for Long Streams

If the model can remain silent for a long time while reasoning or calling tools, proxies/load balancers may close idle connections. An SSE comment-only event serves as a heartbeat:

~~~java
ServerSentEvent.<GenerationEvent>builder()
    .comment("keepalive")
    .build();
~~~

You can emit heartbeats periodically when there are no deltas. Heartbeats are not model content and the frontend does not append them to output. Choose an interval shorter than the proxy's idle timeout while avoiding excessive frequency.

Spring Reactive Core notes that when streaming responses such as `text/event-stream` or `application/x-ndjson`, data should be sent periodically to detect disconnected clients sooner.

### 11.3. Proxies and Compression

Even when WebFlux flushes every SSE event, a reverse proxy or API gateway may buffer the response before sending it to the browser. When deploying:

- Disable response buffering for streaming routes in the proxy configuration.
- Verify that compression middleware does not hold data too long before flushing.
- Set an adequate idle timeout or send heartbeats.
- Use `Cache-Control: no-cache` for event streams.
- Test through the real ingress/CDN/gateway, not just localhost.
- Ensure HTTP/1.1 or HTTP/2 proxy configuration properly supports streaming.

An endpoint that passes `WebTestClient` can still end up buffered when passing through a production proxy.

## 12. Designing UI States

Do not use only a single `loading` boolean. Streaming has several distinct terminal states:

| State | Meaning | Behavior |
| --- | --- | --- |
| `idle` | Prompt not yet submitted | Allow input and submission |
| `connecting` | Establishing the request | Show spinner / connecting status |
| `streaming` | Received `start`, receiving deltas | Append text, show Stop button |
| `completed` | Received `completed` event | Enable copy/save/use result |
| `failed` | Received `error` event or HTTP error | Keep partial output and display error code |
| `cancelled` | User actively stopped | Keep generated portion, mark incomplete |
| `interrupted` | Stream closed without a terminal event | Mark result incomplete, allow intentional retry |

State machine:

~~~text
idle
  |
  v
connecting
  |
  +---- HTTP error ----------> failed
  |
  v
streaming
  |
  +---- completed -----------> completed
  |
  +---- error event ---------> failed
  |
  +---- user abort ----------> cancelled
  |
  +---- unexpected EOF ------> interrupted
~~~

Do not infer success just because fetch received HTTP 200. Only the `completed` event confirms that model generation finished normally according to the application's contract.

### 12.1. UX for Incremental Display

- Show a "Generating…" label until `completed` arrives.
- Allow stopping generation while streaming.
- Keep already-received output if the model fails, but mark it as incomplete content.
- Do not enable actions that depend on a complete answer before the terminal event.
- You can show generation time and model status separately from the content.
- For screen readers, use an `aria-live="polite"` region and avoid announcing every single token; update by paragraph or at a sensible cadence.
- When content grows long, avoid re-rendering complex Markdown on every token; you can batch UI updates per animation frame or short interval.

### 12.2. Incomplete Markdown and HTML

A delta can end in the middle of:
- a code fence,
- a Markdown link,
- a table,
- inline code,
- an HTML entity or a JSON structure.

Rendering each delta as complete Markdown can cause the UI to flicker or misparse syntax. A simple approach is to display raw text using `textContent` while streaming and only render sanitized Markdown once complete. If live rendering is needed, use a parser that supports incremental input and an appropriate sanitizer.

Never use `innerHTML += modelDelta` for untrusted model content.

## 13. Common Pitfalls and Fixes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Returning `Mono<String>` expecting the UI to see tokens immediately | Only one final result arrives | Use `Flux` and a streaming media type |
| Returning `Flux<T>` with `application/json` expecting object-by-object flush | Jackson by default may collect into a JSON array | Use `text/event-stream` or `application/x-ndjson` |
| Using `collectList()` in a streaming endpoint | Waits for the entire model output | Forward the publisher and map each delta |
| Calling `.block()` or `blockLast()` in a controller | Blocks the request thread/event-loop | Compose `Mono`/`Flux` |
| Treating each `reader.read()` as one token | Corrupts data when network chunks split or merge | Parse by SSE frame or NDJSON line |
| Replacing output instead of appending deltas | Each new chunk erases previous text | Maintain `fullText += delta` |
| Marking completed on HTTP status 200 | Stream can fail or disconnect afterward | Wait for the `completed` event |
| Returning HTTP 500 after SSE is committed | Cannot change the status of an already-sent response | Send an `error` event inside the stream |
| Sending raw exception messages to the browser | Leaks provider internals, hosts, or credentials | Map to a stable error code and safe details |
| Not propagating cancellation to the provider | Model keeps running and consuming resources | Clean up/cancel the SDK subscription |
| No heartbeat | Proxy silently closes idle streams | Send periodic SSE comment heartbeats |
| Using EventSource for POST with a body | EventSource API does not support request bodies | Use fetch streaming or POST job + GET EventSource |
| Auto-reconnecting and re-running the prompt | Can start a new generation and bill again | Use generation IDs, event cursors, and a resume contract |
| Rendering deltas with `innerHTML` | XSS and broken incomplete Markdown | `textContent` or a sanitized Markdown renderer |
| Buffering responses in reverse proxies | UI sees output only when the proxy flushes | Disable buffering and test through real ingress |
| Sending too many tiny events | Increases framing/network/UI overhead | Batch deltas within bounds if needed while keeping good time-to-first-token |
| No output/concurrency limits | Memory, model cost, and active stream count grow unchecked | Token caps, rate limits, concurrency limits, and timeouts |

## 14. Testing Streaming

Tests must prove both event ordering and that deltas arrive before completion. A test that only asserts the final response body is insufficient to prove streaming works.

Things to verify:

1. `start` is the first event.
2. `delta` arrives before `completed`.
3. `completed` only appears after the model publisher completes normally.
4. A model error after a delta produces an `error` event and does not produce `completed`.
5. A blank prompt returns HTTP 400 before the stream begins.
6. When the subscriber cancels, the model publisher receives cancellation.
7. The response has `Content-Type: text/event-stream`.
8. Staging tests through the proxy/ingress confirm events are not buffered.

### 14.1. Testing with WebTestClient and StepVerifier

`WebTestClient` sends HTTP requests through the WebFlux handler; `StepVerifier` verifies reactive element ordering.

~~~java
package com.example.generation;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GenerationControllerTest {

    private WebTestClient client(ModelGateway gateway) {
        return WebTestClient
            .bindToController(new GenerationController(gateway))
            .build();
    }

    private Flux<ServerSentEvent<GenerationEvent>> stream(
            WebTestClient client, String prompt) {

        FluxExchangeResult<ServerSentEvent<GenerationEvent>> result =
            client.post()
                .uri("/api/generations")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .bodyValue(new GenerationRequest(prompt))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(
                        MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<GenerationEvent>>() {});

        return result.getResponseBody();
    }

    @Test
    void firstDeltaArrivesBeforeCompletion() {
        WebTestClient client = client(new DemoModelGateway());

        StepVerifier.create(stream(client, "hello"))
            .assertNext(event ->
                assertEquals("start", event.event()))
            .assertNext(event ->
                assertEquals("delta", event.event()))
            .thenCancel()
            .verify(Duration.ofSeconds(3));
    }

    @Test
    void normalGenerationEndsWithCompletedEvent() {
        WebTestClient client = client(new DemoModelGateway());

        StepVerifier.create(stream(client, "hello"))
            .assertNext(event ->
                assertEquals("start", event.event()))
            .expectNextCount(3)
            .assertNext(event ->
                assertEquals("completed", event.event()))
            .verifyComplete();
    }

    @Test
    void modelFailureBecomesErrorEvent() {
        WebTestClient client = client(new DemoModelGateway());

        StepVerifier.create(stream(client, "fail"))
            .assertNext(event ->
                assertEquals("start", event.event()))
            .assertNext(event ->
                assertEquals("delta", event.event()))
            .assertNext(event -> {
                assertEquals("error", event.event());
                assertEquals(
                    "MODEL_UNAVAILABLE",
                    event.data().code());
            })
            .verifyComplete();
    }

    @Test
    void cancellationReachesModelPublisher() {
        AtomicBoolean cancelled = new AtomicBoolean();

        ModelGateway slowGateway = prompt ->
            Flux.<String>never()
                .doOnCancel(() -> cancelled.set(true));

        WebTestClient client = client(slowGateway);

        StepVerifier.create(stream(client, "hello"))
            .assertNext(event ->
                assertEquals("start", event.event()))
            .thenCancel()
            .verify(Duration.ofSeconds(3));

        assertTrue(cancelled.get());
    }

    @Test
    void blankPromptIsRejectedBeforeStreaming() {
        WebTestClient client = client(new DemoModelGateway());

        client.post()
            .uri("/api/generations")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.TEXT_EVENT_STREAM)
            .bodyValue(new GenerationRequest("  "))
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

`thenCancel()` in the first test intentionally cancels right after the first delta. This test proves the publisher does not need to wait for the entire model to finish before emitting content. The cancellation test confirms the cancel signal reaches the source model publisher.

`WebTestClient.bindToController` tests the controller and codecs in isolation. To verify buffering, timeouts, and flushing in production, add tests through a real HTTP server and real reverse proxy.

## 15. Standalone Runnable Project Structure

~~~text
webflux-model-stream/
├── pom.xml
├── src/main/java/com/example/generation/
│   ├── GenerationApplication.java
│   ├── GenerationRequest.java
│   ├── GenerationResult.java
│   ├── GenerationEvent.java
│   ├── ModelGateway.java
│   ├── DemoModelGateway.java
│   └── GenerationController.java
└── src/test/java/com/example/generation/
    └── GenerationControllerTest.java
~~~

### 15.1. pom.xml

Example using Spring Boot 4.0.9 and Java 17+:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.9</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-model-stream</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 15.2. GenerationApplication.java

~~~java
package com.example.generation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GenerationApplication {

    public static void main(String[] args) {
        SpringApplication.run(GenerationApplication.class, args);
    }
}
~~~

The DTOs, interface, demo gateway, and controller use the exact code from Section 5; place each public type in its corresponding file according to the project structure. Tests live in `src/test/java` and use `spring-boot-starter-test`.

### 15.3. Running the Application

Requires JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Call the wait-for-completion mode:

~~~bash
curl -i -X POST http://localhost:8080/api/generations/complete ^
  -H "Content-Type: application/json" ^
  -d "{\"prompt\":\"hello\"}"
~~~

The JSON response appears only after the model publisher completes:

~~~json
{
  "text": "The model is replying incrementally."
}
~~~

Call the streaming mode:

~~~bash
curl -N -X POST http://localhost:8080/api/generations ^
  -H "Content-Type: application/json" ^
  -H "Accept: text/event-stream" ^
  -d "{\"prompt\":\"hello\"}"
~~~

`-N` tells curl not to buffer output. Sample output:

~~~text
id: <request-id>:1
event: start
data: {"text":"","code":null}

id: <request-id>:2
event: delta
data: {"text":"The model ","code":null}

id: <request-id>:3
event: delta
data: {"text":"is replying ","code":null}

id: <request-id>:4
event: delta
data: {"text":"incrementally.","code":null}

id: <request-id>:5
event: completed
data: {"text":"","code":null}
~~~

`<request-id>` is generated fresh for each request. In a real terminal, events arrive over time; they do not wait for the model to finish before appearing.

Test an error occurring after a delta:

~~~bash
curl -N -X POST http://localhost:8080/api/generations ^
  -H "Content-Type: application/json" ^
  -H "Accept: text/event-stream" ^
  -d "{\"prompt\":\"fail\"}"
~~~

The output has `start`, one `delta`, and then `error` with code `MODEL_UNAVAILABLE`. The server does not send `completed`.

On PowerShell, you can run each curl command on a single line; the `^` character in the examples above is the Windows CMD line-continuation character.

## 16. Connecting WebClient to a Real Model Provider

In production, `ModelGateway` typically wraps a streaming API. For example, if the provider returns SSE, `WebClient` can read it as `Flux<ServerSentEvent<ModelDelta>>`:

~~~java
public Flux<String> streamFromProvider(
        WebClient client,
        ModelRequest request) {

    return client.post()
        .uri("/v1/generate")
        .contentType(MediaType.APPLICATION_JSON)
        .accept(MediaType.TEXT_EVENT_STREAM)
        .bodyValue(request)
        .retrieve()
        .bodyToFlux(
            new ParameterizedTypeReference<
                ServerSentEvent<ModelDelta>>() {})
        .filter(event -> event.data() != null)
        .map(event -> event.data().text())
        .filter(text -> text != null && !text.isEmpty());
}
~~~

This is an adapter fragment; `ModelRequest` and `ModelDelta` depend on the provider contract. If the provider returns NDJSON, use `accept(MediaType.APPLICATION_NDJSON)` and `bodyToFlux(ModelDelta.class)` accordingly.

When integrating:
- Keep API keys in the backend; never send provider credentials to JavaScript.
- Map provider-specific deltas into a stable application event schema.
- Do not forward raw provider error bodies.
- Respect usage/token limits, finish reasons, and tool call events.
- Timeouts and cancellation must be propagated to the outbound request.
- Enforce concurrency and rate limits per user/tenant.
- Record metrics such as time-to-first-token, generation duration, delta gaps, token throughput, cancellations, and error codes.

Never let the frontend depend directly on a single model provider's schema. The adapter allows swapping providers without rewriting the UI protocol.

## 17. Observability and Measuring Experience Quality

The two most important metrics for comparing the two modes:

- **Time to first byte/event:** from submission until the browser receives the response or first event.
- **Time to first token/delta:** from submission until the first delta carrying content.

Other metrics:

| Metric | Meaning |
| --- | --- |
| `generation.duration` | Time from start to terminal event |
| `generation.output.length` | Number of characters or tokens generated |
| `generation.delta.count` | Number of deltas emitted |
| `generation.delta.interval` | Interval between deltas |
| `generation.cancelled` | Number of generations cancelled by user or transport |
| `generation.failed` | Number of generations ending in error |
| `generation.incomplete` | Streams closed without a terminal event |
| `generation.active` | Number of concurrently running generations |

Attach a request ID/trace ID to logs to locate a specific generation. Avoid using prompts, raw output, or user IDs as metric tags because they may contain private data and create very high cardinality.

A good streaming experience is not just "having deltas". Track time-to-first-token, delta steadiness, completion rate, and interrupted-stream rate.

## 18. Security and Reliability

- Authenticate and authorize before opening the stream.
- Do not put prompts or tokens in URLs/query strings.
- Do not send provider API keys or secrets down to the browser.
- Sanitize Markdown/HTML before rendering.
- Limit prompt size, output tokens, duration, and concurrent generations.
- Enforce rate limits per user/tenant and cost quotas.
- Do not log full prompts/responses by default.
- Handle CORS, CSRF, and cookies according to the application's auth policy.
- With SSE over cookie sessions, protect endpoints against cross-site request abuse.
- On reconnect, verify ownership of the generation ID and event cursor.
- Do not allow clients to pick another user's generation ID.
- Keep error events as stable codes; do not return stack traces or exception messages.

## 19. Debugging Procedure When the UI Does Not Render Incrementally

1. Check whether the provider actually returns deltas or only a single final object.
2. Check whether `ModelGateway` returns `Flux` and does not call `collectList()`/`block()` before returning.
3. Check whether the controller declares `produces = text/event-stream` or NDJSON.
4. Check the `Content-Type` response header.
5. Use `curl -N` to see whether events arrive in waves.
6. Check whether the Spring codec and response writer flush events.
7. Check whether a reverse proxy/CDN buffers or compresses in a way that delays flushing.
8. Check whether the frontend parser waits for proper frame delimiters.
9. Check whether `TextDecoder` uses stream mode to preserve UTF-8 across split chunks.
10. Check whether the UI appends deltas instead of replacing the entire output.
11. Check whether the `completed` event is emitted and handled properly.
12. When clicking Stop, verify whether cancellation reaches the provider.

If `curl -N` receives events incrementally but the UI does not update, the bug is usually in the frontend parser/state/rendering. If curl only receives output at the end, check backend aggregation, codecs, proxies, and buffering.

## 20. Production Checklist

- [ ] Separate contracts exist for final results and delta streams.
- [ ] `Mono` returns a complete result only after the model publisher completes.
- [ ] The streaming endpoint returns `Flux` with `text/event-stream` or NDJSON.
- [ ] The event contract includes `start`, `delta`, `completed`, and `error`.
- [ ] Event IDs/sequences are generated consistently within a generation.
- [ ] Frontend parses frames without relying on network chunk boundaries.
- [ ] UI appends deltas in order and handles the interrupted state.
- [ ] Completion is not assumed based solely on HTTP 200.
- [ ] Errors after response commit are sent within the stream protocol.
- [ ] Cancellation propagates to the model provider.
- [ ] Heartbeats and timeouts are configured for long streams.
- [ ] Proxy/CDN buffering is checked and configured appropriately.
- [ ] Backpressure and output/concurrency limits are enforced.
- [ ] Prompts and outputs are not unsafely logged or rendered.
- [ ] Tests cover delta-before-complete, error, cancel, and invalid prompt.
- [ ] Staging tests through ingress confirm real event flushing.
- [ ] Metrics exist for time-to-first-token, duration, cancellation, and incomplete streams.

## 21. Hands-on Exercises

**Exercise 1 – Wait for completion.** Create a `Mono<GenerationResult>` endpoint that collects `Flux<String>` into a `StringBuilder`. Measure the time from submission until the UI receives JSON.

**Exercise 2 – Basic SSE.** Create a `Flux<ServerSentEvent<GenerationEvent>>` with `start`, three `delta` events, and `completed`. Use `curl -N` to verify events arrive one by one.

**Exercise 3 – Browser parser.** Split an SSE frame into multiple simulated byte chunks. Verify the parser emits the event only after the blank line.

**Exercise 4 – UTF-8.** Split the bytes of a multi-byte Vietnamese character across two `reader.read()` calls. Verify `TextDecoder` with `{stream:true}` reassembles the character properly.

**Exercise 5 – Error after delta.** Have the model publisher emit one delta and then fail. Verify the UI keeps the received text, displays the error code, and does not mark completed.

**Exercise 6 – Cancellation.** Abort fetch after the first delta. Use `doOnCancel` in a test gateway to verify the upstream publisher is cancelled.

**Exercise 7 – NDJSON.** Create an `application/x-ndjson` endpoint, emit each `GenerationChunk`, and write a line-by-line parser.

**Exercise 8 – Heartbeat.** Add periodic SSE comments for a slow generation. Verify the frontend ignores heartbeats and the proxy does not close idle streams.

**Exercise 9 – Markdown streaming.** Test a model emitting a code fence or link across multiple deltas. Compare raw text rendering with a sanitized incremental Markdown renderer.

**Exercise 10 – End-to-end.** Run through staging ingress, measure time-to-first-token and total duration, cancel midway, and verify the provider stopped generation.

## 22. Official References

1. Spring Framework 7.0.8 – Reactive Core, streaming and heartbeats: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
2. Spring Framework 7.0.8 – Controller Return Values and `Flux<ServerSentEvent>`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
3. Spring Framework 7.0.8 – `ServerSentEvent` Javadoc: https://javadoc.io/static/org.springframework/spring-web/7.0.8/org/springframework/http/codec/ServerSentEvent.html
4. Spring Framework 7.0.8 – `ServerSentEvent.Builder` Javadoc: https://javadoc.io/static/org.springframework/spring-web/7.0.8/org/springframework/http/codec/ServerSentEvent.Builder.html
5. Spring Framework – WebClient `retrieve()` and `bodyToFlux`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
6. Spring Framework – WebClient streaming: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
7. Spring Framework – ResponseEntity with reactive body: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
8. Spring Boot – System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
9. WHATWG – Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html
10. MDN – Using Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
11. MDN – Fetch API and ReadableStream: https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream

**Final self-check:** Why can `Mono` be non-blocking yet the UI still has to wait for the model to finish? Why is `Flux` with `application/json` not guaranteed to render incrementally? Which event confirms the model finished normally? Why does an error after the first event require an SSE `error` instead of a new HTTP 500? When the user clicks Stop, where must cancellation propagate? If you can answer these and have tests proving deltas arrive before `completed`, you can distinguish waiting for a final result from true streaming.
