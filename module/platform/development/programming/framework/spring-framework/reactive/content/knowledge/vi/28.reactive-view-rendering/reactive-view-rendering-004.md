# Phân biệt chờ model hoàn tất với hiển thị từng phần trong Spring WebFlux

> **Module:** Spring Framework – reactive · **Chủ đề cha:** Hiển thị giao diện. Bài học thiết kế hai trải nghiệm cho cùng một tác vụ sinh nội dung: chờ model trả kết quả hoàn chỉnh rồi hiển thị một lần, hoặc phát từng phần để giao diện cập nhật ngay khi model tạo ra nội dung. Trọng tâm là `Mono` và `Flux`, chọn HTTP media type đúng, gửi Server-Sent Events (SSE), cập nhật giao diện an toàn, xử lý lỗi/cancel/backpressure và kiểm thử rằng dữ liệu thực sự đến trước khi model hoàn tất.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt thời điểm model hoàn tất với thời điểm giao diện bắt đầu hiển thị kết quả.
2. Giải thích vì sao `Mono<T>` phù hợp với kết quả cuối cùng, còn `Flux<T>` phù hợp với chuỗi phần dữ liệu.
3. Hiểu rằng trả về `Flux` chưa đủ để bảo đảm trình duyệt nhìn thấy từng phần; cần chọn định dạng streaming như `text/event-stream` hoặc `application/x-ndjson`.
4. Thiết kế SSE event contract có `start`, `delta`, `completed` và `error`.
5. Xây dựng endpoint WebFlux vừa có chế độ chờ hoàn tất vừa có chế độ streaming.
6. Dùng `fetch()` và `ReadableStream` để gửi prompt bằng POST, parse SSE frame và nối các delta đúng thứ tự.
7. Hủy model generation khi người dùng dừng hoặc đóng giao diện.
8. Xử lý lỗi trước khi response commit và lỗi xảy ra sau khi stream đã bắt đầu.
9. Giữ backpressure, giới hạn output, heartbeat và timeout để stream vận hành ổn định.
10. Viết test chứng minh delta đầu tiên được phát trước event hoàn tất và cancellation đi ngược về model publisher.

**Điểm cốt lõi:** reactive là cách xử lý bất đồng bộ và luồng dữ liệu ở backend; streaming là quyết định về giao thức và cách giao diện tiêu thụ dữ liệu. Một endpoint trả `Mono` vẫn có thể hoàn toàn non-blocking nhưng chỉ cung cấp một kết quả cuối cùng. Một endpoint trả `Flux` chỉ mang lại trải nghiệm hiển thị từng phần khi codec, HTTP response, proxy và frontend đều giữ nguyên luồng dữ liệu.

## 2. Hai trải nghiệm khác nhau

Giả sử người dùng gửi prompt cho một model và model tạo ra câu trả lời dài. Có hai cách tổ chức luồng:

| Tiêu chí | Chờ model hoàn tất | Hiển thị từng phần |
| --- | --- | --- |
| Backend return type | Thường là `Mono<GenerationResult>` | Thường là `Flux<ServerSentEvent<...>>` |
| HTTP response | Một JSON document hoàn chỉnh | Một stream event kéo dài |
| Lần đầu người dùng thấy nội dung | Sau khi model hoàn tất và response được gửi | Khi delta đầu tiên tới trình duyệt |
| UI state | Loading → Completed hoặc Failed | Connecting → Streaming → Completed/Failed/Cancelled |
| Lỗi giữa generation | Có thể trả HTTP error trước khi body hoàn tất | Thường gửi event `error` trong stream đã mở |
| Memory | Thường phải giữ toàn bộ kết quả cuối trong bộ nhớ | Có thể xử lý từng delta, nhưng phải giới hạn buffer phía UI |
| Hủy generation | Hủy request trước khi kết quả được trả | Có thể hủy ngay khi đang nhận delta |
| Phù hợp | Kết quả ngắn, cần validate toàn bộ trước khi hiển thị | Chat, sinh nội dung dài, tiến độ, log hoặc tác vụ có output liên tục |

Hai cách không nói rằng một cách “reactive” còn cách kia “blocking”. `Mono` không đồng nghĩa với `block()`. Backend có thể đợi model hoàn tất bằng một pipeline non-blocking `Mono`; điều khác biệt là giao diện chỉ nhận một kết quả khi publisher hoàn tất.

### 2.1. Chờ hoàn tất: một kết quả duy nhất

~~~text
Browser                    WebFlux                     Model
   |                          |                           |
   | POST prompt              |                           |
   |------------------------->| gọi model                  |
   |                          |-------------------------->|
   |                          |       token 1              |
   |                          |<--------------------------|
   |                          |       token 2              |
   |                          |<--------------------------|
   |                          |       token ...            |
   |                          |<--------------------------|
   |                          |       model complete       |
   |                          |<--------------------------|
   |       JSON cuối cùng     |                           |
   |<-------------------------|                           |
   | hiển thị toàn bộ         |                           |
~~~

Trong thời gian model tạo token, backend có thể đã nhận dữ liệu từng phần nhưng vẫn gom chúng thành một kết quả duy nhất. Người dùng nhìn thấy spinner hoặc trạng thái “Đang tạo…” cho đến khi JSON cuối cùng tới.

### 2.2. Streaming: giao diện nhận từng delta

~~~text
Browser                    WebFlux                     Model
   |                          |                           |
   | POST prompt              |                           |
   |------------------------->|                           |
   | event: start             | gọi model stream           |
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
   | đánh dấu hoàn tất        |                           |
~~~

Giao diện có thể hiển thị nội dung trong khi model vẫn đang làm việc. Mỗi delta thường là một đoạn ký tự hoặc token; nó không nhất thiết là một từ hoàn chỉnh hay một câu hoàn chỉnh.

## 3. Hiểu `Mono`, `Flux` và HTTP media type

### 3.1. `Mono<T>`: chỉ phát kết quả cuối

Dùng `Mono<GenerationResult>` khi contract của API là một object hoàn chỉnh:

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

`collect` đợi publisher nguồn hoàn tất rồi mới phát `GenerationResult`. Trong lúc đợi, Reactor không cần chặn event-loop. Tuy vậy, toàn bộ nội dung được giữ trong `StringBuilder`, vì vậy cần giới hạn số token hoặc kích thước output.

### 3.2. `Flux<T>` không tự bảo đảm UI streaming

Một chi tiết dễ nhầm: nếu trả `Flux<GenerationChunk>` với `application/json`, Jackson encoder của WebFlux mặc định gom các phần tử thành một `List` rồi serialize thành một JSON array. Trình duyệt có thể chỉ nhận một JSON document hoàn chỉnh.

Để phát từng record, chọn media type có framing streaming rõ ràng:

| Media type | Cách truyền | Dùng khi |
| --- | --- | --- |
| `application/json` | Một JSON document/array; multi-value publisher mặc định có thể được gom | Kết quả hoàn chỉnh |
| `text/event-stream` | SSE frame, mỗi event được ghi và flush | Chat, tiến độ, event có tên và ID |
| `application/x-ndjson` | Mỗi JSON object là một dòng độc lập | Stream record có cấu trúc, dễ parse theo dòng |
| `text/plain` | Nội dung văn bản | Stream text đơn giản, khi hai bên có quy ước framing rõ |

Với giao diện chat, SSE thường tiện vì một event có thể mang tên `start`, `delta`, `completed` hoặc `error`. NDJSON phù hợp nếu mỗi phần là một object có schema và frontend tự đọc từng dòng.

Không coi ranh giới packet TCP hoặc HTTP chunk là ranh giới token của model. Một packet có thể chứa nhiều delta; một delta cũng có thể bị chia qua nhiều lần `reader.read()`. Ứng dụng phải parse theo framing của giao thức.

### 3.3. Spring WebFlux ghi SSE như thế nào?

Controller có thể trả:

~~~java
@GetMapping(
    value = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE)
public Flux<ServerSentEvent<ProgressEvent>> events() {
    return progressPublisher();
}
~~~

Spring dùng `ServerSentEventHttpMessageWriter` để serialize event. Với SSE, encoder xử lý từng event và flush để event được gửi mà không phải chờ toàn bộ stream. Spring Framework cũng khuyến nghị gửi dữ liệu định kỳ, ví dụ comment-only event, để phát hiện client đã ngắt kết nối sớm hơn.

Đọc thêm:
- Reactive Core: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Controller return values: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html

## 4. Thiết kế event contract cho model stream

Không nên gửi một chuỗi không có loại event rồi bắt frontend đoán khi nào model bắt đầu, kết thúc hoặc lỗi. Hãy định nghĩa contract rõ ràng.

Một stream mẫu:

~~~text
id: gen-123:1
event: start
data: {"text":"","code":null}

id: gen-123:2
event: delta
data: {"text":"Xin ","code":null}

id: gen-123:3
event: delta
data: {"text":"chào ","code":null}

id: gen-123:4
event: delta
data: {"text":"bạn!","code":null}

id: gen-123:5
event: completed
data: {"text":"","code":null}

~~~

Nếu model gặp lỗi sau khi đã gửi một phần:

~~~text
id: gen-123:3
event: delta
data: {"text":"Một phần nội dung","code":null}

id: gen-123:4
event: error
data: {"text":"","code":"MODEL_UNAVAILABLE"}

~~~

Các event cơ bản:

| Event | Ý nghĩa | UI nên làm gì |
| --- | --- | --- |
| `start` | Server đã nhận generation và mở stream | Xóa output cũ, hiển thị trạng thái đang tạo |
| `delta` | Có thêm text từ model | Nối text vào output hiện tại |
| `completed` | Model kết thúc bình thường | Đánh dấu hoàn tất, bật thao tác dùng kết quả |
| `error` | Generation thất bại sau khi stream bắt đầu | Giữ phần đã nhận, báo kết quả chưa hoàn chỉnh |
| `heartbeat` | Server còn giữ stream sống | Không thay đổi nội dung |
| `metadata` | Thông tin phụ như model, usage hoặc finish reason | Cập nhật phần metadata, không nối vào text |

`id` là sequence ID của event. Nó có ích cho logging và resume, nhưng chỉ gửi ID không tự tạo khả năng resume. Nếu muốn tiếp tục stream sau reconnect, server phải lưu lịch sử event hoặc trạng thái generation và xử lý `Last-Event-ID`/cursor tương ứng.

Với model có tool calling, có thể bổ sung event riêng như `tool_started`, `tool_result` hoặc `status`. Không đưa JSON argument nội bộ của tool vào vùng text mà người dùng nhìn thấy.

## 5. Ví dụ backend: hai endpoint cho hai chế độ

Ta xây dựng hai endpoint cùng dùng một `ModelGateway`:

- `POST /api/generations/complete` trả `Mono<GenerationResult>` khi model hoàn tất.
- `POST /api/generations` trả `Flux<ServerSentEvent<GenerationEvent>>` để UI nhận từng delta.

`ModelGateway` là abstraction của nhà cung cấp model. Ví dụ dùng một publisher giả lập để project chạy độc lập; trong production, thay implementation bằng SDK/API streaming thực tế của model.

### 5.1. ModelGateway.java

~~~java
package com.example.generation;

import reactor.core.publisher.Flux;

public interface ModelGateway {

    Flux<String> stream(String prompt);
}
~~~

Mỗi phần tử `String` là một delta đã được adapter giải mã từ model provider. Không giả định mỗi phần tử tương ứng đúng một token: provider có thể gộp nhiều token hoặc chia một từ thành nhiều đoạn.

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
                Flux.just("Một phần nội dung đã được tạo."),
                Flux.error(new IllegalStateException(
                    "internal model provider detail"))
            );
        }

        return Flux.just(
                "Mô hình ",
                "đang trả lời ",
                "theo từng phần."
            )
            .delayElements(Duration.ofMillis(180));
    }
}
~~~

`delayElements` chỉ giúp nhìn thấy sự khác biệt giữa chờ hoàn tất và streaming khi chạy demo. Model provider thực tế sẽ phát delta theo tốc độ generation của nó.

### 5.3. DTO

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

Event payload chỉ chứa thông tin giao diện cần. Không đưa stack trace, raw exception message, API key hoặc dữ liệu nội bộ của provider vào event.

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

Điểm cần chú ý:

1. `complete()` gom các delta vào `StringBuilder`; chỉ phát một `GenerationResult` sau khi publisher hoàn tất.
2. `stream()` dùng `Flux.concat` để phát `start`, sau đó lần lượt các `delta`, cuối cùng mới phát `completed`.
3. `Flux.defer` gọi model gateway khi có subscription và đưa lỗi phát sinh trong lúc tạo publisher vào reactive chain.
4. `onErrorResume` đổi lỗi model thành event `error` an toàn. Frontend biết generation thất bại mà không cần nhận exception message.
5. `doOnCancel` ghi nhận request bị hủy. Cancellation của HTTP response được truyền ngược qua `Flux`; model adapter phải nối cancellation đó tới SDK/provider để dừng generation thật.
6. `requestId` và sequence ID giúp nối log với từng event mà không cần ghi prompt hoặc nội dung model vào log.

Validation được thực hiện trước khi stream bắt đầu, vì vậy request không hợp lệ có thể nhận HTTP 400. Lỗi xảy ra sau event `start` được biểu diễn bằng event `error`.

## 6. Vì sao lỗi streaming cần event riêng?

HTTP status và body error có ý nghĩa rõ khi server chưa gửi response body. Khi SSE đã bắt đầu và event đầu tiên được flush, response có thể đã commit. Server không thể quay lại đổi status 200 thành 500 và ghi một JSON ProblemDetail mới vào cùng response.

Vì vậy cần phân biệt:

| Thời điểm lỗi | Cách xử lý |
| --- | --- |
| Prompt không hợp lệ trước khi stream mở | Trả HTTP 400 |
| Không xác thực được request trước khi stream mở | Trả HTTP 401/403 |
| Không thể tạo model stream trước event đầu tiên | Trả HTTP error nếu response chưa commit |
| Model lỗi sau một hoặc nhiều delta | Phát SSE `error` với code ổn định |
| Client ngắt kết nối | Hủy publisher và dừng model call nếu provider hỗ trợ |
| Proxy/network đóng stream mà không có `completed` | UI đánh dấu kết quả bị gián đoạn |

Không phát event `completed` khi model kết thúc bằng lỗi. Nếu frontend nhận EOF nhưng chưa thấy `completed` hoặc `error`, hãy coi đó là stream bị gián đoạn và không đánh dấu nội dung là kết quả hoàn chỉnh.

Trong chế độ `Mono`, nếu lỗi xảy ra trước khi kết quả được serialize, framework có thể tạo HTTP error response. Trong chế độ streaming, sau khi response đã commit, lỗi phải nằm trong protocol của stream.

## 7. Giao diện trình duyệt: POST bằng fetch và đọc SSE từng frame

### 7.1. Vì sao dùng fetch cho prompt?

`EventSource` của trình duyệt thuận tiện cho SSE GET và có reconnect tự động. Tuy nhiên, API EventSource không gửi request body POST và không cho đặt tùy ý Authorization header.

Khi prompt cần gửi trong JSON body, dùng `fetch()` với `POST`, `Accept: text/event-stream` và đọc `response.body` bằng `ReadableStream`. Nếu muốn dùng EventSource, một thiết kế khác là POST để tạo generation/job rồi dùng GET với ID ngắn để subscribe vào stream.

Không đưa prompt, access token hoặc dữ liệu riêng tư vào query string chỉ để dùng EventSource; URL thường xuất hiện trong proxy log, browser history và telemetry.

### 7.2. SSE parser

SSE phân tách event bằng một dòng trống. Một event có thể có nhiều dòng `data`; `id`, `event` và `retry` là các field riêng. Network chunk không đảm bảo trùng với SSE frame, vì vậy phải giữ phần dữ liệu chưa đủ frame trong buffer.

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

Comment-only heartbeat bắt đầu bằng `:` và không có `data`, nên parser bỏ qua. `TextDecoder` ở bước tiếp theo dùng `{ stream: true }` để giữ đúng ký tự UTF-8 nếu một ký tự đa byte bị chia qua hai lần đọc.

### 7.3. Đọc stream và cập nhật UI

Giả sử trang có hai phần tử:

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
        statusElement.textContent = "Đang tạo nội dung...";
        break;

      case "delta":
        fullText += parsed.data.text;
        // textContent tránh diễn giải nội dung model như HTML.
        outputElement.textContent = fullText;
        break;

      case "completed":
        completed = true;
        statusElement.textContent = "Đã hoàn tất";
        break;

      case "error":
        failed = true;
        statusElement.textContent =
          `Generation thất bại: ${parsed.data.code}`;
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
        "Stream kết thúc trước khi model xác nhận hoàn tất";
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

Đoạn code này nối từng delta vào `fullText` và cập nhật `textContent`. Nó không giả định mỗi lần `reader.read()` là một token. Một lần đọc có thể chứa nhiều event hoặc một phần của event; parser chỉ xử lý khi đã có dấu phân cách frame.

Dùng `textContent` cho output thô. Nếu cần render Markdown, hãy tích lũy nội dung và dùng Markdown renderer có sanitize HTML. Markdown đang được sinh có thể có code fence hoặc link chưa hoàn chỉnh; render HTML trực tiếp từ mỗi delta bằng `innerHTML` có thể gây lỗi giao diện và tạo nguy cơ XSS.

### 7.4. Nút hủy

Tạo một `AbortController` cho mỗi generation:

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

Trong ứng dụng thực, gắn listener một lần khi khởi tạo UI và bỏ listener sau khi request hoàn tất. Khi `abort()` được gọi, fetch bị hủy; server nhận cancellation khi transport đóng và reactive response publisher bị cancel. Adapter model phải đóng subscription hoặc gọi cancel API của provider.

Bắt `AbortError` ở lớp UI để hiển thị “Đã hủy” thay vì thông báo lỗi mạng chung.

## 8. Nếu dùng EventSource thay vì fetch

EventSource phù hợp khi server đã có generation ID và frontend chỉ cần subscribe GET:

~~~javascript
const source = new EventSource(
  `/api/generations/${encodeURIComponent(generationId)}/events`
);

source.addEventListener("delta", event => {
  const data = JSON.parse(event.data);
  output.textContent += data.text;
});

source.addEventListener("completed", () => {
  status.textContent = "Đã hoàn tất";
  source.close();
});

source.addEventListener("error", event => {
  // Network error và SSE event error cần được phân biệt
  // theo giao thức ứng dụng.
  status.textContent = "Kết nối stream bị gián đoạn";
  source.close();
});
~~~

SSE event có `id` có thể được trình duyệt gửi lại qua `Last-Event-ID` khi reconnect. Server chỉ nên tiếp tục từ ID đó nếu đã lưu event history và có logic xác thực generation ownership. Nếu generation không thể resume, hãy báo trạng thái interrupted và yêu cầu client tạo request mới theo chính sách idempotency.

Với fetch POST, trình duyệt không tự cung cấp cơ chế EventSource reconnect; nếu muốn resume, frontend phải lưu generation ID/sequence và gọi endpoint resume do server thiết kế.

## 9. Chọn giữa SSE và NDJSON

| Đặc điểm | SSE | NDJSON |
| --- | --- | --- |
| Framing | Event kết thúc bằng dòng trống | Một JSON object trên mỗi dòng |
| Event name | Có field `event` | Thường đặt `type` trong JSON |
| Event ID/retry | Có chuẩn field `id` và `retry` | Tự định nghĩa trong object |
| Browser API | `EventSource` hỗ trợ GET | Dùng `fetch` và đọc từng dòng |
| Hướng truyền | Server → client | Server → client trong response thông thường |
| Hợp với | Chat, tiến độ, trạng thái | Record stream, log, kết quả có schema |

Ví dụ NDJSON:

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

`GenerationChunk` có thể là:

~~~java
public record GenerationChunk(String type, String text) {}
~~~

Với NDJSON, frontend đọc theo dòng `\n` và parse mỗi dòng thành JSON. Không parse từng lần `reader.read()` thành một JSON object vì một dòng có thể bị chia qua nhiều lần đọc.

## 10. Backpressure và buffering

### 10.1. Giữ luồng reactive từ model tới response

Luồng nên có dạng:

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

Reactive Streams backpressure giúp điều phối demand giữa các publisher/subscriber. Tránh gom mọi delta vào `List` hoặc queue không giới hạn. Nếu UI hoặc network đọc chậm, pipeline phải giữ lượng dữ liệu chờ ở mức kiểm soát.

### 10.2. Tránh các thao tác làm mất streaming

Các thao tác sau làm kết quả chỉ xuất hiện sau khi upstream hoàn tất hoặc giữ toàn bộ output trong bộ nhớ:

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

Ví dụ thứ ba có thể đúng khi cố ý triển khai chế độ chờ hoàn tất, nhưng không phù hợp với endpoint muốn phát từng delta.

Cũng tránh gọi `subscribe()` thủ công trong controller để đẩy delta vào một biến dùng chung. Hãy trả publisher cho WebFlux để request lifecycle quản lý subscription, cancellation và lỗi.

### 10.3. Giới hạn output và memory

Streaming giảm nhu cầu giữ toàn bộ câu trả lời ở server, nhưng không có nghĩa memory được giới hạn tự động ở mọi tầng. Hãy:

- Giới hạn số token hoặc độ dài output ở model provider.
- Không lưu toàn bộ lịch sử delta trong một collection nếu chỉ cần phát tới UI.
- Giới hạn buffer ở browser và chỉ giữ phần lịch sử cần thiết.
- Đặt timeout tổng thể và timeout giữa các event.
- Giới hạn số generation đồng thời theo user/tenant.
- Hủy provider subscription khi client ngắt kết nối.
- Không gửi delta quá nhỏ với tần suất quá cao nếu việc gom chunk giúp giảm overhead mà không làm tăng đáng kể time-to-first-token.

## 11. Cancellation, timeout và heartbeat

### 11.1. Cancellation phải đi tới model provider

Nếu user bấm Stop, đường hủy mong muốn là:

1. Browser gọi `AbortController.abort()`.
2. HTTP request/response bị đóng.
3. WebFlux hủy subscription tới response publisher.
4. `Flux` của controller bị cancel.
5. Model gateway hủy subscription tới provider.
6. Provider dừng generation và giải phóng tài nguyên.

`doOnCancel` chỉ là hook để quan sát hoặc ghi log; nó không tự dừng một tác vụ blocking bên ngoài. Nếu adapter gọi SDK không reactive, cần giữ handle/cancel token và đóng nó trong cleanup.

Không để một model call tiếp tục chạy và tính phí sau khi browser đã rời trang nếu nghiệp vụ không yêu cầu generation nền.

### 11.2. Heartbeat cho stream dài

Nếu model có thể im lặng lâu trong lúc suy luận hoặc gọi tool, proxy/load balancer có thể đóng kết nối idle. SSE comment-only event là một heartbeat:

~~~java
ServerSentEvent.<GenerationEvent>builder()
    .comment("keepalive")
    .build();
~~~

Có thể phát heartbeat định kỳ khi không có delta. Heartbeat không phải nội dung model và frontend không nối nó vào output. Chọn chu kỳ nhỏ hơn idle timeout của proxy nhưng tránh quá dày.

Spring Reactive Core lưu ý rằng khi stream response như `text/event-stream` hoặc `application/x-ndjson`, nên gửi dữ liệu định kỳ để phát hiện client đã disconnect sớm hơn.

### 11.3. Proxy và compression

Ngay cả khi WebFlux flush từng SSE event, reverse proxy hoặc API gateway có thể buffer response trước khi gửi tới browser. Khi triển khai:

- Tắt response buffering cho route streaming theo cấu hình proxy.
- Kiểm tra compression middleware không giữ dữ liệu quá lâu trước khi flush.
- Đặt idle timeout đủ dài hoặc gửi heartbeat.
- Dùng `Cache-Control: no-cache` cho event stream.
- Kiểm thử qua toàn bộ ingress/CDN/gateway thật, không chỉ localhost.
- Đảm bảo HTTP/1.1 hoặc HTTP/2 proxy configuration hỗ trợ streaming đúng cách.

Một endpoint chạy tốt trong `WebTestClient` vẫn có thể bị buffer khi đi qua production proxy.

## 12. Thiết kế trạng thái giao diện

Không nên chỉ có một boolean `loading`. Streaming có nhiều trạng thái kết thúc khác nhau:

| State | Ý nghĩa | Hành vi |
| --- | --- | --- |
| `idle` | Chưa gửi prompt | Cho phép nhập và submit |
| `connecting` | Đang thiết lập request | Hiển thị spinner/đang kết nối |
| `streaming` | Đã nhận `start`, đang nhận delta | Append text, hiển thị nút Stop |
| `completed` | Đã nhận event `completed` | Cho phép copy/save/use result |
| `failed` | Đã nhận event `error` hoặc HTTP error | Giữ phần output và hiển thị mã lỗi |
| `cancelled` | User chủ động dừng | Giữ phần đã sinh, đánh dấu chưa hoàn tất |
| `interrupted` | Stream đóng mà không có terminal event | Đánh dấu kết quả chưa hoàn chỉnh, cho phép retry có chủ đích |

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

Đừng suy luận thành công chỉ vì fetch đã nhận HTTP 200. Chỉ event `completed` mới xác nhận model generation đã kết thúc bình thường theo contract của ứng dụng.

### 12.1. UX khi hiển thị từng phần

- Hiển thị nhãn “Đang tạo…” cho tới khi có `completed`.
- Cho phép dừng generation khi đang stream.
- Giữ phần đã nhận khi model lỗi, nhưng đánh dấu đó là nội dung chưa hoàn chỉnh.
- Không bật hành động phụ thuộc câu trả lời hoàn chỉnh trước terminal event.
- Có thể hiển thị thời gian tạo và trạng thái model riêng với nội dung.
- Với screen reader, dùng vùng `aria-live="polite"` và tránh phát announcement cho mọi token; cập nhật theo đoạn hoặc theo nhịp hợp lý.
- Khi nội dung quá dài, tránh render lại toàn bộ Markdown phức tạp ở mỗi token; có thể batch UI updates theo frame hoặc theo khoảng thời gian ngắn.

### 12.2. Markdown và HTML chưa hoàn chỉnh

Một delta có thể kết thúc giữa:
- code fence,
- link Markdown,
- bảng,
- inline code,
- HTML entity hoặc một cấu trúc JSON.

Nếu render mỗi delta như Markdown hoàn chỉnh, UI có thể nhấp nháy hoặc diễn giải sai. Cách đơn giản là hiển thị text thô bằng `textContent` trong lúc stream và chỉ render Markdown đã sanitize khi hoàn tất. Nếu cần render live, dùng parser hỗ trợ incremental input và sanitizer phù hợp.

Không dùng `innerHTML += modelDelta` cho nội dung model chưa được tin cậy.

## 13. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Trả `Mono<String>` nhưng kỳ vọng UI thấy token ngay | Chỉ có một kết quả cuối | Dùng `Flux` và media type streaming |
| Trả `Flux<T>` với `application/json` rồi kỳ vọng flush từng object | Jackson mặc định có thể gom thành JSON array | Dùng `text/event-stream` hoặc `application/x-ndjson` |
| Dùng `collectList()` trong endpoint streaming | Chờ toàn bộ model output | Chuyển tiếp publisher và map từng delta |
| Gọi `.block()` hoặc `blockLast()` trong controller | Chặn request thread/event-loop | Compose `Mono`/`Flux` |
| Xem mỗi `reader.read()` là một token | Ghép sai dữ liệu khi network chunk bị chia/gộp | Parse theo SSE frame hoặc NDJSON line |
| Nối delta bằng phép gán thay vì append | Mỗi phần mới xóa phần cũ | Duy trì `fullText += delta` |
| Đánh dấu hoàn tất khi HTTP status là 200 | Stream có thể lỗi hoặc disconnect sau đó | Chờ event `completed` |
| Trả HTTP 500 sau khi SSE đã commit | Không thể đổi status của response đã gửi | Gửi event `error` trong stream |
| Gửi raw exception message cho browser | Lộ nội bộ provider, host hoặc credential | Map sang stable error code và safe detail |
| Không truyền cancellation tới provider | Model tiếp tục chạy và tiêu tốn tài nguyên | Cleanup/cancel subscription của SDK |
| Không có heartbeat | Proxy đóng stream im lặng | Gửi SSE comment heartbeat định kỳ |
| Dùng EventSource cho POST có body | API EventSource không hỗ trợ request body | Dùng fetch stream hoặc POST job + GET EventSource |
| Tự động reconnect rồi chạy lại prompt | Có thể tạo generation mới và tính phí lần nữa | Dùng generation ID, event cursor và resume contract |
| Render delta bằng `innerHTML` | XSS và Markdown chưa hoàn chỉnh | `textContent` hoặc Markdown renderer đã sanitize |
| Buffer response ở reverse proxy | UI chỉ thấy kết quả khi proxy flush | Tắt buffering và test qua ingress thật |
| Gửi quá nhiều event nhỏ | Tăng framing/network/UI overhead | Gom delta có giới hạn nếu cần, giữ time-to-first-token tốt |
| Không giới hạn output/concurrency | Memory, chi phí model và số stream tăng | Token cap, rate limit, concurrency limit và timeout |

## 14. Kiểm thử streaming

Test cần chứng minh cả thứ tự event và thời điểm delta xuất hiện. Một test chỉ assert response body cuối cùng không đủ chứng minh streaming hoạt động.

Các điều cần kiểm tra:

1. `start` là event đầu tiên.
2. `delta` xuất hiện trước `completed`.
3. `completed` chỉ xuất hiện sau khi model publisher complete bình thường.
4. Lỗi model sau một delta tạo event `error` và không tạo `completed`.
5. Prompt trống trả HTTP 400 trước khi stream bắt đầu.
6. Khi subscriber cancel, model publisher nhận cancellation.
7. Response có `Content-Type: text/event-stream`.
8. Test qua proxy/ingress ở staging xác nhận event không bị buffer.

### 14.1. Test bằng WebTestClient và StepVerifier

`WebTestClient` gửi HTTP request qua WebFlux handler; `StepVerifier` kiểm tra thứ tự phần tử reactive.

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

`thenCancel()` trong test đầu tiên chủ động hủy sau delta đầu tiên. Test này chứng minh publisher không cần đợi toàn bộ model hoàn tất mới phát nội dung. Test cancellation xác nhận tín hiệu hủy đi tới nguồn model publisher.

`WebTestClient.bindToController` kiểm tra controller/codec trong test. Để kiểm chứng buffering, timeout và flush ở production, cần thêm test qua HTTP server thật và reverse proxy thực tế.

## 15. Cấu trúc project chạy độc lập

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

Ví dụ dùng Spring Boot 4.0.9 và Java 17+:

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

Các DTO, interface, demo gateway và controller sử dụng đúng nội dung ở mục 5; đặt mỗi public type vào file tương ứng theo cấu trúc project. Test nằm trong `src/test/java` và dùng `spring-boot-starter-test`.

### 15.3. Chạy ứng dụng

Yêu cầu JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Gọi chế độ chờ hoàn tất:

~~~bash
curl -i -X POST http://localhost:8080/api/generations/complete ^
  -H "Content-Type: application/json" ^
  -d "{\"prompt\":\"hello\"}"
~~~

Response JSON chỉ xuất hiện sau khi model publisher complete:

~~~json
{
  "text": "Mô hình đang trả lời theo từng phần."
}
~~~

Gọi chế độ streaming:

~~~bash
curl -N -X POST http://localhost:8080/api/generations ^
  -H "Content-Type: application/json" ^
  -H "Accept: text/event-stream" ^
  -d "{\"prompt\":\"hello\"}"
~~~

`-N` yêu cầu curl không buffer output. Output minh họa:

~~~text
id: <request-id>:1
event: start
data: {"text":"","code":null}

id: <request-id>:2
event: delta
data: {"text":"Mô hình ","code":null}

id: <request-id>:3
event: delta
data: {"text":"đang trả lời ","code":null}

id: <request-id>:4
event: delta
data: {"text":"theo từng phần.","code":null}

id: <request-id>:5
event: completed
data: {"text":"","code":null}
~~~

`<request-id>` được tạo mới cho mỗi request. Trong terminal thật, các event sẽ đến theo thời gian; chúng không đợi model hoàn tất mới xuất hiện.

Thử lỗi xảy ra sau khi có delta:

~~~bash
curl -N -X POST http://localhost:8080/api/generations ^
  -H "Content-Type: application/json" ^
  -H "Accept: text/event-stream" ^
  -d "{\"prompt\":\"fail\"}"
~~~

Kết quả có `start`, một `delta`, rồi `error` với code `MODEL_UNAVAILABLE`. Server không gửi `completed`.

Trên PowerShell, có thể chạy mỗi lệnh curl trên một dòng; dấu `^` ở ví dụ trên là ký tự nối dòng của Windows CMD.

## 16. Nối WebClient với model provider thật

Trong production, `ModelGateway` thường bọc một API streaming. Ví dụ nếu provider trả SSE, `WebClient` có thể đọc thành `Flux<ServerSentEvent<ModelDelta>>`:

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

Đây là fragment adapter; `ModelRequest` và `ModelDelta` phụ thuộc contract provider. Nếu provider trả NDJSON, dùng `accept(MediaType.APPLICATION_NDJSON)` và `bodyToFlux(ModelDelta.class)` tương ứng.

Khi tích hợp:
- Giữ API key ở backend; không đưa credential provider vào JavaScript.
- Map provider-specific delta thành một schema event ổn định của ứng dụng.
- Không chuyển tiếp raw provider error body.
- Tôn trọng usage/token limit, finish reason và tool call event.
- Timeout và cancellation phải được truyền tới request outbound.
- Giới hạn concurrency và rate theo user/tenant.
- Ghi metrics như time-to-first-token, generation duration, delta gap, token throughput, cancellation và error code.

Không để frontend phụ thuộc trực tiếp schema của một nhà cung cấp model. Adapter giúp thay provider mà không phải viết lại UI protocol.

## 17. Quan sát và đo chất lượng trải nghiệm

Hai metric quan trọng nhất để so sánh hai chế độ:

- **Time to first byte/event:** từ lúc submit đến khi browser nhận response hoặc event đầu tiên.
- **Time to first token/delta:** từ lúc submit đến delta có nội dung đầu tiên.

Các metric khác:

| Metric | Ý nghĩa |
| --- | --- |
| `generation.duration` | Thời gian từ start đến terminal event |
| `generation.output.length` | Số ký tự hoặc token được sinh |
| `generation.delta.count` | Số delta được phát |
| `generation.delta.interval` | Khoảng cách giữa các delta |
| `generation.cancelled` | Số generation bị user hoặc transport hủy |
| `generation.failed` | Số generation kết thúc bằng error |
| `generation.incomplete` | Stream đóng mà không có terminal event |
| `generation.active` | Số generation đang chạy đồng thời |

Gắn request ID/trace ID vào log để tìm một generation cụ thể. Tránh dùng prompt, raw output hoặc user ID làm metric tag vì chúng có thể chứa dữ liệu riêng tư và tạo cardinality rất cao.

Một trải nghiệm streaming tốt không chỉ là “có delta”. Hãy theo dõi time-to-first-token, độ đều của delta, tỷ lệ hoàn tất và tỷ lệ stream bị gián đoạn.

## 18. Bảo mật và độ tin cậy

- Xác thực và phân quyền trước khi mở stream.
- Không đưa prompt hoặc token vào URL/query string.
- Không gửi provider API key hoặc secret xuống browser.
- Sanitize Markdown/HTML trước khi render.
- Giới hạn prompt size, output token, thời gian và số generation đồng thời.
- Có rate limit theo user/tenant và quota chi phí.
- Không ghi toàn bộ prompt/response vào log mặc định.
- Xử lý CORS, CSRF và cookie theo chính sách auth của ứng dụng.
- Với SSE qua cookie session, bảo vệ endpoint khỏi cross-site request abuse.
- Khi reconnect, kiểm tra quyền truy cập generation ID và event cursor.
- Không cho client tự chọn một generation ID của user khác.
- Giữ event error ở dạng code ổn định, không trả stack trace hoặc exception message.

## 19. Quy trình debug khi UI không hiển thị từng phần

1. Kiểm tra provider thực sự trả delta hay chỉ trả một object cuối.
2. Kiểm tra `ModelGateway` có trả `Flux` và không `collectList()`/`block()` trước khi trả về.
3. Kiểm tra controller khai báo `produces = text/event-stream` hoặc NDJSON.
4. Kiểm tra response header `Content-Type`.
5. Dùng `curl -N` xem event có đến từng đợt hay không.
6. Kiểm tra Spring codec và response writer có flush event.
7. Kiểm tra reverse proxy/CDN có buffering hoặc compression gây trì hoãn.
8. Kiểm tra frontend parser có đợi dấu phân cách frame đúng chuẩn.
9. Kiểm tra `TextDecoder` có dùng stream mode để giữ UTF-8 khi chunk bị chia.
10. Kiểm tra UI append delta thay vì thay toàn bộ output.
11. Kiểm tra event `completed` có được phát và xử lý đúng.
12. Nếu bấm Stop, kiểm tra cancellation có đến provider hay không.

Nếu `curl -N` nhận từng event nhưng UI không cập nhật, lỗi thường nằm ở frontend parser/state/render. Nếu curl chỉ nhận sau cùng, kiểm tra backend aggregation, codec, proxy và buffering.

## 20. Checklist production

- [ ] Có contract riêng cho kết quả cuối và stream delta.
- [ ] `Mono` chỉ trả kết quả hoàn chỉnh sau khi model publisher complete.
- [ ] Streaming endpoint trả `Flux` với `text/event-stream` hoặc NDJSON.
- [ ] Event contract có `start`, `delta`, `completed` và `error`.
- [ ] Event ID/sequence được tạo ổn định trong một generation.
- [ ] Frontend parse frame, không phụ thuộc network chunk boundary.
- [ ] UI nối delta đúng thứ tự và có trạng thái interrupted.
- [ ] Không đánh dấu hoàn tất chỉ dựa trên HTTP 200.
- [ ] Lỗi sau response commit được gửi trong stream protocol.
- [ ] Cancellation được truyền tới model provider.
- [ ] Có heartbeat và timeout cho stream dài.
- [ ] Proxy/CDN buffering được kiểm tra và cấu hình phù hợp.
- [ ] Backpressure và output/concurrency limits được áp dụng.
- [ ] Prompt và output không bị log hoặc render thiếu an toàn.
- [ ] Có test cho delta-before-complete, error, cancel và invalid prompt.
- [ ] Có staging test qua ingress để xác nhận event flush thật.
- [ ] Có metrics cho time-to-first-token, duration, cancellation và incomplete stream.

## 21. Bài tập thực hành

**Bài 1 – Chờ hoàn tất.** Tạo endpoint `Mono<GenerationResult>` gom `Flux<String>` vào `StringBuilder`. Đo thời gian từ submit đến khi UI nhận JSON.

**Bài 2 – SSE cơ bản.** Tạo `Flux<ServerSentEvent<GenerationEvent>>` với `start`, ba `delta` và `completed`. Dùng `curl -N` xác nhận event đến lần lượt.

**Bài 3 – Parser phía browser.** Chia một SSE frame thành nhiều byte chunk giả lập. Kiểm tra parser chỉ phát event sau dòng trống.

**Bài 4 – UTF-8.** Chia byte của một ký tự tiếng Việt đa byte giữa hai lần `reader.read()`. Xác nhận `TextDecoder` với `{stream:true}` ghép đúng ký tự.

**Bài 5 – Lỗi sau delta.** Cho model publisher phát một delta rồi lỗi. Xác nhận UI giữ phần text đã nhận, hiện error code và không đánh dấu completed.

**Bài 6 – Cancellation.** Hủy fetch sau delta đầu tiên. Dùng `doOnCancel` trong test gateway để xác nhận upstream publisher bị cancel.

**Bài 7 – NDJSON.** Tạo endpoint `application/x-ndjson`, phát từng `GenerationChunk` và viết parser đọc từng dòng.

**Bài 8 – Heartbeat.** Thêm SSE comment định kỳ cho generation chờ lâu. Xác nhận frontend bỏ qua heartbeat và proxy không đóng idle stream.

**Bài 9 – Markdown streaming.** Thử model phát code fence hoặc link thành nhiều delta. So sánh render text thô với incremental Markdown renderer đã sanitize.

**Bài 10 – End-to-end.** Chạy qua staging ingress, đo time-to-first-token và tổng duration, hủy giữa chừng, rồi xác nhận provider đã dừng generation.

## 22. Tài liệu tham khảo chính thức

1. Spring Framework 7.0.8 – Reactive Core, streaming và heartbeat: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
2. Spring Framework 7.0.8 – Controller Return Values và `Flux<ServerSentEvent>`: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html
3. Spring Framework 7.0.8 – `ServerSentEvent` Javadoc: https://javadoc.io/static/org.springframework/spring-web/7.0.8/org/springframework/http/codec/ServerSentEvent.html
4. Spring Framework 7.0.8 – `ServerSentEvent.Builder` Javadoc: https://javadoc.io/static/org.springframework/spring-web/7.0.8/org/springframework/http/codec/ServerSentEvent.Builder.html
5. Spring Framework – WebClient `retrieve()` và `bodyToFlux`: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html
6. Spring Framework – WebClient streaming: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
7. Spring Framework – ResponseEntity với reactive body: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responseentity.html
8. Spring Boot – System Requirements: https://docs.spring.io/spring-boot/system-requirements.html
9. WHATWG – Server-Sent Events: https://html.spec.whatwg.org/multipage/server-sent-events.html
10. MDN – Using Server-Sent Events: https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
11. MDN – Fetch API and ReadableStream: https://developer.mozilla.org/en-US/docs/Web/API/ReadableStream

**Tự đánh giá cuối:** Vì sao `Mono` có thể non-blocking nhưng UI vẫn phải chờ model hoàn tất? Vì sao `Flux` với `application/json` chưa chắc hiển thị từng phần? Event nào xác nhận model đã kết thúc bình thường? Vì sao lỗi sau event đầu tiên cần một SSE `error` thay vì HTTP 500 mới? Khi user bấm Stop, cancellation phải đi tới đâu? Nếu bạn trả lời được và test chứng minh delta đến trước `completed`, bạn đã phân biệt được chờ kết quả cuối với streaming thực sự.
