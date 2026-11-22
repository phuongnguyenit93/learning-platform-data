# Kiểm tra Flux, SSE và luồng không kết thúc bằng StepVerifier trong Spring WebFlux

## 1. Mục tiêu bài học

Spring WebFlux có thể trả response chứa nhiều phần tử theo thời gian, chẳng hạn `Flux<OrderEvent>`, `Flux<ServerSentEvent<Alert>>`, luồng JSON Lines/NDJSON hoặc một stream đọc từ broker. Khác với response JSON hữu hạn, các luồng này **có thể không bao giờ phát onComplete**. Kiểm thử một endpoint streaming vì thế không thể chỉ gọi `expectBodyList(...)` rồi chờ toàn bộ response kết thúc.

Bài học này tập trung vào cách phối hợp:

- `StepVerifier` của `reactor-test` để kiểm tra signals của `Flux`.
- `WebTestClient` của Spring để tạo HTTP request tới WebFlux controller và đọc response streaming.
- `FluxExchangeResult<T>.getResponseBody()` để lấy Flux ở client sau khi đã xác minh HTTP status và headers.
- `thenCancel()` để kết thúc bài test hữu hạn về thời gian đối với một **luồng nghiệp vụ không có điểm kết thúc**.
- `withVirtualTime(...)` để kiểm tra timer, delay, timeout bằng đồng hồ ảo ở tầng Reactor, không chờ thật.
- `TestPublisher` và `PublisherProbe` để mô phỏng upstream/error/cancellation một cách quyết định.
- Phân biệt HTTP status, media type, SSE frame và dữ liệu ứng dụng đã được decode.

Sau bài này, người học cần biết test một Flux có điểm kết thúc, một Flux vô hạn, SSE từ HTTP, NDJSON streaming, một nguồn lỗi giữa stream và đường truyền hủy subscription; đồng thời tránh các bài test treo, flaky hoặc sai contract.

## 2. Cần phân biệt ba lớp kiểm thử

~~~text
                        WebTestClient
                             |
                             | HTTP GET /api/streams/sse
                             v
                      WebFlux Controller
                             |
                             | Flux<ServerSentEvent<Notice>>
                             v
                HttpMessageWriter / SSE Encoder
                             |
                             | HTTP response
                             | Content-Type: text/event-stream
                             v
                  FluxExchangeResult<T>
                             |
                             | getResponseBody()
                             v
                         StepVerifier
                  value, order, timing, error,
                  completion, cancellation
~~~

Có ba câu hỏi khác nhau:

1. **HTTP contract:** status có phải 200 không, response header có phải `text/event-stream` hoặc `application/x-ndjson` không?
2. **Stream contract:** client nhận các đối tượng nào, đúng thứ tự không, có lỗi không?
3. **Lifecycle contract:** nguồn là finite hay infinite, khi nào downstream hủy, và upstream có cleanup tài nguyên không?

`WebTestClient` kiểm tra phần HTTP, còn `StepVerifier` diễn đạt kỳ vọng trên publisher. Cùng nhau, chúng kiểm thử nhiều tầng hơn một test chỉ gọi trực tiếp method controller.

Không dùng một assertion “response body bằng chuỗi cố định” để kiểm tra mọi event-stream. Response SSE có framing, có thể thêm comment heartbeat, retry, id và line breaks; thông thường nên kiểm tra dữ liệu đã decode và các metadata thực sự cần thiết.

## 3. Flux hữu hạn và Flux không kết thúc

Một `Flux<T>` có thể kết thúc bình thường, kết thúc bằng lỗi hoặc không bao giờ tự kết thúc.

| Nguồn | Tín hiệu điển hình | Test phù hợp |
| --- | --- | --- |
| `Flux.just("A", "B")` | onNext A, B rồi onComplete | expectNext + verifyComplete |
| `Flux.empty()` | onComplete, không có onNext | verifyComplete |
| `Flux.error(ex)` | onError | expectError/expectErrorMatches |
| `Flux.interval(Duration)` | phát theo thời gian, mặc định không complete | expectNextCount + thenCancel |
| `Flux.never()` | không onNext, không terminal | expectSubscription + thenCancel |
| Hot broker/feed | Có thể phát lâu dài và dừng khi hủy | TestPublisher/Sinks + thenCancel |
| `Flux.interval(...).take(3)` | phát 3 phần tử rồi complete | expectNext + verifyComplete |

### 3.1. Test luồng hữu hạn

~~~java
Flux<Integer> numbers = Flux.just(1, 2, 3);

StepVerifier.create(numbers)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

`verifyComplete()` chỉ thành công khi downstream phát đúng ba phần tử và phát `onComplete`. Nếu Flux tiếp tục phát giá trị thứ tư, test thất bại.

### 3.2. Test luồng không có onComplete

~~~java
Flux<Long> ticks = Flux.interval(Duration.ofMillis(100));

StepVerifier.create(ticks)
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify(Duration.ofSeconds(3));
~~~

Đây là test **hữu hạn về thời gian**, dù nguồn vô hạn. `thenCancel()` hủy subscription sau khi đủ ba phần tử. Nó **không** xác minh nguồn tự complete.

Nếu thay `thenCancel()` bằng `verifyComplete()`, test sẽ chờ một tín hiệu không bao giờ xuất hiện. Với timeout, test sẽ thất bại; không có timeout, test có nguy cơ treo lâu.

### 3.3. Test một nguồn hoàn toàn im lặng

~~~java
Flux<String> silent = Flux.never();

StepVerifier.create(silent)
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(2));
~~~

`Flux.never()` không phát item cũng không phát terminal signal. Nếu muốn chứng minh không có item trong một khoảng thời gian, có thể dùng `expectNoEvent(Duration)` sau `expectSubscription()`. Cách đó có ý nghĩa temporal, khác với việc chỉ hủy ngay.

## 4. StepVerifier là một subscriber có kịch bản

Các method quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `StepVerifier.create(publisher)` | Tạo script xác minh và subscribe khi verify |
| `expectSubscription()` | Đợi subscription |
| `expectNext(value)` | Kỳ vọng giá trị cụ thể |
| `expectNextMatches(predicate)` | Kỳ vọng giá trị thỏa điều kiện |
| `assertNext(consumer)` | Thực hiện assertion trên object |
| `expectNextCount(n)` | Kỳ vọng n phần tử bất kỳ |
| `expectNoEvent(duration)` | Không được có event trong khoảng thời gian |
| `thenAwait(duration)` | Cho thời gian trôi, không assert “không có event” |
| `then(Runnable)` | Điều khiển nguồn/side effect trong test |
| `thenRequest(n)` | Cấp thêm Reactive Streams demand |
| `thenCancel()` | Chủ động cancel downstream |
| `expectComplete()` | Yêu cầu completion |
| `expectError(...)` | Yêu cầu error |
| `verify(Duration)` | Chạy bài test với giới hạn thời gian |
| `verifyComplete()` | Shortcut xác minh completion |

**Cẩn thận về thứ tự:** chỉ tạo builder bằng `StepVerifier.create(...)` chưa có subscription. Khi gọi `verify(...)`, các bước mới được thực thi. Nếu sử dụng hot source như TestPublisher, hãy phát dữ liệu qua `then(...)` sau bước subscription.

Ví dụ kiểm tra object:

~~~java
StepVerifier.create(service.findAll())
    .assertNext(item -> {
        assertEquals("Keyboard", item.name());
        assertTrue(item.price().signum() > 0);
    })
    .expectNextCount(2)
    .verifyComplete();
~~~

Ở một test khác, nếu service là feed không kết thúc, thay expectation terminal bằng `thenCancel()`.

## 5. SSE là gì và khi nào dùng?

**Server-Sent Events (SSE)** là cơ chế HTTP streaming một chiều từ server tới client. Client gửi request thông thường (thường GET), server trả `Content-Type: text/event-stream` rồi giữ response mở để đẩy event liên tục.

SSE khác WebSocket:

| Đặc điểm | SSE | WebSocket |
| --- | --- | --- |
| Hướng chính | Server → client | Hai chiều |
| Transport | HTTP response dài | WebSocket handshake/frames |
| Media type | text/event-stream | Không phải MIME response stream thông thường |
| Browser API | EventSource | WebSocket |
| Reconnect | EventSource tự có cơ chế reconnect | Ứng dụng tự chọn reconnect |
| Event ID | id/Last-Event-ID | Tự định nghĩa nếu cần |
| Test | WebTestClient + StepVerifier | WebSocketClient + reactive test |

SSE có thể được phát từ Spring WebFlux controller với:

~~~java
@GetMapping(
    path = "/events",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<String>> events() {
    return Flux.interval(Duration.ofSeconds(1))
        .map(i -> ServerSentEvent.<String>builder()
            .id(Long.toString(i))
            .event("tick")
            .data("tick-" + i)
            .build());
}
~~~

`ServerSentEvent<T>` thuộc package `org.springframework.http.codec`. Wrapper này cho phép đặt metadata `id`, `event`, `retry`, `comment` và `data`. Nếu chỉ cần payload, WebFlux có thể ghi một `Flux<T>` dưới dạng SSE khi mapping/content negotiation chọn `text/event-stream`, nhưng dùng wrapper sẽ rõ ràng hơn khi cần metadata.

## 6. Cấu trúc SSE trên đường truyền

Một event SSE thường chứa các dòng:

~~~text
id:0
event:notice
retry:3000
data:{"sequence":0,"message":"notice-0"}

~~~

Dòng trống kết thúc một event. Một stream có thể chứa nhiều event nối tiếp trong cùng HTTP response, không có một JSON array bao ngoài.

Ý nghĩa:

- `id`: ID của event, giúp client có thể gửi `Last-Event-ID` khi reconnect.
- `event`: loại event để browser `EventSource.addEventListener("notice", ...)` nhận.
- `retry`: thời gian reconnect gợi ý, tính bằng **mili giây** khi ghi thành SSE wire format.
- `data`: payload, thường là text hoặc JSON.
- Dòng bắt đầu bằng dấu hai chấm `:`: comment, có thể dùng làm keepalive.
- Dòng trống: ranh giới giữa các event.

Không so sánh nguyên văn tất cả newline/field order của SSE nếu mục tiêu test là domain data. Prefer decode thành `ServerSentEvent<Notice>` và assert `id()`, `event()`, `data()`, `retry()`.

**Giới hạn quan trọng:** Có SSE id chưa đủ để bảo đảm resume. Server phải thực sự đọc `Last-Event-ID`, lưu hoặc truy vấn lịch sử event và định nghĩa semantics replay. Một demo chỉ dùng `Flux.interval` theo mỗi connection không có durable event log.

## 7. WebTestClient kiểm tra HTTP streaming đúng cách

Spring Framework chính thức khuyến nghị với response streaming như `text/event-stream` hoặc `application/x-ndjson`:

1. Gửi HTTP request, khai báo Accept phù hợp.
2. Gọi `exchange()`.
3. Kiểm tra status và headers.
4. Dùng `returnResult(Type)` để nhận `FluxExchangeResult<T>`.
5. Lấy `result.getResponseBody()` là `Flux<T>`.
6. Dùng StepVerifier để kiểm tra một vài item và **thenCancel** nếu stream không kết thúc.

~~~java
FluxExchangeResult<MyEvent> result =
    webTestClient.get()
        .uri("/api/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(MyEvent.class);

StepVerifier.create(result.getResponseBody())
    .assertNext(event -> assertEquals("A", event.message()))
    .expectNextCount(2)
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

Đây là **snippet** minh họa API; class MyEvent và endpoint tương ứng nằm trong ứng dụng giả định. Phần demo hoàn chỉnh ở cuối bài sử dụng `Notice` và chạy được độc lập.

### 7.1. Vì sao returnResult cần thiết?

Với response JSON hữu hạn, bạn có thể viết:

~~~java
webTestClient.get()
    .uri("/api/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(Product.class)
    .hasSize(3);
~~~

Body list assertion cần nhận đủ response và decode thành collection. Nhưng nếu endpoint là infinite SSE, body sẽ không bao giờ hoàn tất nên assertion body-list không có một điểm tự nhiên để kết thúc.

`returnResult(...)` trả quyền điều khiển Flux đã decode về cho test. Nó cho phép yêu cầu từng item, xác minh thứ tự, hủy sau N item và tránh chờ toàn bộ response vô hạn.

### 7.2. Chọn cách decode

- SSE chỉ chứa plain string: có thể dùng `returnResult(String.class)` để nhận dữ liệu sau decoding theo cấu hình client.
- SSE có metadata: dùng `returnResult(new ParameterizedTypeReference<ServerSentEvent<Notice>>() {})` để giữ generic type.
- NDJSON: `returnResult(Notice.class)` để nhận từng object JSON.
- SSE cần kiểm tra framing byte chính xác: dùng decoder/raw response chuyên biệt; không đánh đồng với test domain objects.

Không dựa vào Java generics bị xóa như `ServerSentEvent.class` rồi cast trực tiếp `data()` thành Notice. Với DTO phức tạp, dùng `ParameterizedTypeReference` để giữ generic type cho codec.

## 8. Test SSE metadata bằng generic type

Ví dụ endpoint trả `Flux<ServerSentEvent<Notice>>`. Trong test:

~~~java
FluxExchangeResult<ServerSentEvent<Notice>> response =
    webTestClient.get()
        .uri("/api/streams/sse")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.TEXT_EVENT_STREAM)
        .returnResult(
            new ParameterizedTypeReference<
                ServerSentEvent<Notice>>() {}
        );

StepVerifier.create(response.getResponseBody())
    .assertNext(event -> {
        assertEquals("0", event.id());
        assertEquals("notice", event.event());
        assertEquals(Duration.ofSeconds(3), event.retry());
        assertEquals(
            new Notice(0L, "notice-0"), event.data()
        );
    })
    .assertNext(event ->
        assertEquals(
            new Notice(1L, "notice-1"), event.data()
        )
    )
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

Đây là một test **streaming contract**: nó không đợi completion, nhưng kiểm tra hai event đầu, id, event name và retry metadata. Vì stream là hot/timer theo mỗi request, thứ tự event là 0 rồi 1; không gán kỳ vọng rằng response phải đến chính xác sau 100,000 mili giây trên network thật.

## 9. NDJSON: một JSON object trên một dòng

`application/x-ndjson` là định dạng streaming gồm nhiều JSON value phân tách bởi newline:

~~~text
{"sequence":0,"message":"notice-0"}
{"sequence":1,"message":"notice-1"}
{"sequence":2,"message":"notice-2"}
~~~

Khác với `application/json` chứa một array đầy đủ:

~~~json
[
  {"sequence":0,"message":"notice-0"},
  {"sequence":1,"message":"notice-1"},
  {"sequence":2,"message":"notice-2"}
]
~~~

Với NDJSON, client có thể decode từng object trước khi HTTP response hoàn tất. Trong WebFlux:

~~~java
@GetMapping(
    path = "/ndjson",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<Notice> ndjson() {
    return service.live();
}
~~~

Test:

~~~java
FluxExchangeResult<Notice> result = webTestClient.get()
    .uri("/api/streams/ndjson")
    .accept(MediaType.APPLICATION_NDJSON)
    .exchange()
    .expectStatus().isOk()
    .expectHeader()
    .contentTypeCompatibleWith(MediaType.APPLICATION_NDJSON)
    .returnResult(Notice.class);

StepVerifier.create(result.getResponseBody())
    .assertNext(n -> assertEquals(0L, n.sequence()))
    .assertNext(n -> assertEquals(1L, n.sequence()))
    .thenCancel()
    .verify(Duration.ofSeconds(8));
~~~

Không giả định NDJSON và SSE có cùng wire format. NDJSON không có các field `event`, `id`, `retry` của SSE; với client chỉ cần JSON rows, NDJSON thường đơn giản hơn. Browser EventSource không đọc NDJSON tự động như SSE.

## 10. verifyComplete, thenCancel và take(n) có nghĩa khác nhau

Ba cách này hay bị dùng lẫn:

| Cách | Downstream quan sát | Upstream |
| --- | --- | --- |
| `expectComplete().verify()` | Cần onComplete | Nguồn đã hoàn tất bình thường |
| `thenCancel().verify()` | Test chủ động hủy | Nguồn thường nhận cancel |
| `take(3).verifyComplete()` | Flux sau take phát 3 phần tử rồi complete | take thường hủy upstream trước khi upstream tự complete |

Ví dụ:

~~~java
Flux<Long> infinite = Flux.interval(
    Duration.ofMillis(20)
);

StepVerifier.create(infinite.take(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Đây là một test hợp lệ, nhưng **chứng minh completion của pipeline có take(3)**, không chứng minh nguồn `Flux.interval` tự kết thúc. Nếu mục tiêu là kiểm tra source infinite và cleanup khi downstream hủy, test trực tiếp nguồn:

~~~java
StepVerifier.create(infinite)
    .expectNext(0L, 1L, 2L)
    .thenCancel()
    .verify(Duration.ofSeconds(5));
~~~

Khi dùng `take(n)` trên response client, các phần tử đủ N có thể dẫn tới cancellation trên HTTP receive. Tuy nhiên, việc cleanup ở server diễn ra bất đồng bộ qua network; không assert flag server được set **ngay tức thì** chỉ sau khi client verifier trả về, nếu không có cơ chế đồng bộ/đợi điều kiện phù hợp.

## 11. Virtual time: không chờ timer chạy thật

Trong unit test service dùng `Flux.interval` hoặc `delayElements`, nên dùng `StepVerifier.withVirtualTime(...)` khi mục tiêu là logic thời gian, không phải HTTP/network.

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2)
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofMinutes(59))
    .thenAwait(Duration.ofMinutes(1))
    .expectNext(0L)
    .thenAwait(Duration.ofHours(1))
    .expectNext(1L)
    .verifyComplete();
~~~

Ví dụ không đợi hai giờ thật. Virtual scheduler được gắn trước khi `Flux.interval` được tạo, nhờ publisher được xây **bên trong supplier**.

### 11.1. expectNoEvent khác thenAwait

- `expectNoEvent(duration)` vừa tiến thời gian vừa khẳng định không có onNext/onError/onComplete trong khoảng đó.
- `thenAwait(duration)` tiến thời gian nhưng không assert rằng không có tín hiệu.
- Subscription là một event. Nếu muốn khẳng định không có onNext trong một khoảng sau subscribe, dùng `expectSubscription().expectNoEvent(...)`.

Ví dụ:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
~~~

### 11.2. Không dùng virtual time cho HTTP integration một cách máy móc

`WebTestClient.bindToServer()` kết nối qua network thật. Kernel socket, network I/O, Netty event loop và flush không được điều khiển toàn bộ bởi Reactor virtual scheduler. Vì vậy:

- Unit test service/timer: dùng `withVirtualTime`.
- HTTP integration test streaming: dùng real-time `verify(Duration)` với timeout hợp lý, interval nhỏ và assertion không phụ thuộc mili giây chính xác.
- Nếu cần test handshake/headers/cancellation server-side, dùng WebTestClient hoặc WebClient integration test thay vì chỉ gọi service.

## 12. TestPublisher: điều khiển upstream và lỗi theo thời điểm

Một stream thật có thể nhận dữ liệu từ message broker, database change feed hoặc sensor. TestPublisher giúp phát signal theo kế hoạch mà không cần hạ tầng thật.

~~~java
TestPublisher<Long> upstream = TestPublisher.create();

Flux<Notice> output =
    service.transform(upstream.flux());

StepVerifier.create(output)
    .then(() -> upstream.next(7L))
    .expectNext(new Notice(7L, "notice-7"))
    .then(() -> upstream.error(
        new IllegalStateException("broker down")
    ))
    .expectErrorMessage("broker down")
    .verify(Duration.ofSeconds(3));
~~~

`then(...)` quan trọng vì `TestPublisher.create()` là nguồn hot: nếu phát trước khi StepVerifier subscribe, item có thể bị mất.

Nếu muốn kiểm tra cancellation:

~~~java
TestPublisher<Long> upstream = TestPublisher.create();

StepVerifier.create(
        service.transform(upstream.flux()).take(2)
    )
    .then(() -> upstream.next(10L, 11L))
    .expectNext(
        new Notice(10L, "notice-10"),
        new Notice(11L, "notice-11")
    )
    .verifyComplete();

upstream.assertCancelled();
~~~

Hành vi trên chứng minh `take(2)` phát completion downstream rồi cancel nguồn TestPublisher.

**Không dùng TestPublisher trong production** như một message bus: nó thuộc reactor-test và được tạo để kiểm thử. Với production imperative-to-reactive bridge, xem Reactor `Sinks` hoặc adapter phù hợp.

## 13. Kiểm thử lỗi trên streaming response

Lỗi xảy ra **trước** khi HTTP response được commit có thể khiến WebFlux chọn một HTTP error status, tùy exception handling. Nhưng nếu endpoint đã gửi nhiều SSE event và flush response, server không thể quay lại đổi status thành HTTP 500 cho response đã bắt đầu.

Ví dụ test **service layer**:

~~~java
Flux<Notice> feed = Flux.concat(
    Flux.just(new Notice(0L, "notice-0")),
    Flux.error(new IllegalStateException("feed failed"))
);

StepVerifier.create(feed)
    .expectNext(new Notice(0L, "notice-0"))
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "feed failed".equals(error.getMessage())
    )
    .verify(Duration.ofSeconds(2));
~~~

Test này đảm bảo service phát event đầu rồi error. Nó **không** khẳng định một HTTP SSE client sẽ nhìn thấy một HTTP 500 sau event đầu. Khi network response bị lỗi giữa stream, client có thể quan sát connection close, decoder error hoặc reconnect tùy client/proxy.

Nếu ứng dụng muốn gửi “business error” dưới dạng SSE có kiểm soát, bạn có thể chuyển một số lỗi nghiệp vụ thành một `ServerSentEvent<...>` với `event("error")` và body an toàn, rồi quyết định complete hay tiếp tục stream. Không gửi stack trace hoặc token trong SSE data.

### 13.1. Test fallback trong service

~~~java
Flux<Notice> recovered = feed
    .onErrorResume(error ->
        Flux.just(new Notice(-1L, "temporarily-unavailable"))
    );

StepVerifier.create(recovered)
    .expectNext(
        new Notice(0L, "notice-0"),
        new Notice(-1L, "temporarily-unavailable")
    )
    .verifyComplete();
~~~

Đây là một chính sách nghiệp vụ cụ thể; đừng dùng `onErrorResume` biến mọi lỗi production thành thành công giả. Lỗi không mong đợi phải có log, metric và contract rõ.

## 14. Cancellation và giải phóng tài nguyên

Với stream vô hạn, **cancellation là một kết quả kiểm thử bình thường**, không phải test failure.

Ví dụ service:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(
    Duration.ofMillis(50)
).doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectNext(0L, 1L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertTrue(cancelled.get());
~~~

Đây là unit test trên một pipeline in-memory. Nó xác minh `cancel` đi vào upstream.

### 14.1. Cleanup khi dùng nguồn bên ngoài

Nếu stream có subscription broker, database cursor hoặc resource bất đồng bộ, hãy gắn resource vào lifecycle của publisher:

~~~java
Flux<String> events = Flux.usingWhen(
    broker.openSubscription(channel),
    subscription -> subscription.messages(),
    subscription -> subscription.close(),
    (subscription, error) -> subscription.close(),
    subscription -> subscription.close()
);
~~~

`usingWhen` có cleanup khác nhau cho complete, error và cancel. Đảm bảo operation thực tế được trả về dưới dạng reactive publisher và không tự subscribe độc lập ở ngoài.

Trong HTTP integration test, việc client `thenCancel()` giúp yêu cầu hủy body consumption. Để xác minh cleanup thật sự ở server, nên instrument resource (counter/metrics, latch hoặc test broker fake có signal), rồi đợi signal được xác nhận thay vì dùng `Thread.sleep` và đọc một boolean ngay lập tức.

### 14.2. Response stream từ broker phải được giới hạn

Đừng tạo một `Flux` vô hạn từ một source nhiều tenant mà không phân quyền topic, giới hạn subscription, queue và thời gian sống. Slow clients có thể giữ connection lâu; cancellation đúng giúp trả resource về pool.

## 15. Backpressure: request(n) và streaming HTTP

Reactive Streams có `request(n)`, nhưng HTTP/TCP và codec tạo những lớp buffer khác nhau. Nếu StepVerifier khởi tạo demand bằng 1, không được kết luận TCP chỉ đọc đúng một packet hoặc server chỉ tạo đúng một element. Buffering, prefetch và network flush có thể làm số lượng request ở từng tầng khác nhau.

Ví dụ unit test:

~~~java
StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .verifyComplete();
~~~

Khi test WebFlux SSE integration:

- Hãy kiểm tra semantics client thực nhận: thứ tự, dữ liệu, cancellation.
- Không assert exact upstream request(n) từ HTTP client trừ khi đây là contract cần kiểm chứng với instrumentation phù hợp.
- Nếu dùng `Flux.interval`, cần nhớ nó có thể phát `OverflowException` khi downstream không có demand; không dùng một unit test demand=0 với interval thật mà không thiết kế kỳ vọng.
- Limit queue, max in-memory size, event size và số connection là yêu cầu vận hành khác với assertion StepVerifier.

## 16. Heartbeat và keepalive cho SSE

Spring Framework khuyến nghị streaming response như SSE/NDJSON gửi dữ liệu định kỳ để phát hiện disconnect sớm hơn. Khi feed nghiệp vụ có thể im lặng lâu, có thể phát SSE comment-only heartbeat:

~~~java
Flux<ServerSentEvent<String>> heartbeat =
    Flux.interval(Duration.ofSeconds(15))
        .map(i -> ServerSentEvent.<String>builder()
            .comment("keepalive")
            .build());
~~~

Một comment SSE bắt đầu bằng dấu hai chấm trên wire, không phải một event nghiệp vụ thông thường. Client có thể dùng heartbeat để giữ connection hoạt động và tránh idle timeout của reverse proxy.

Không thiết kế test “mọi event nhận được đều phải là Notice” khi stream thực tế có heartbeat hoặc nhiều loại event mà decoder expose. Tách test dữ liệu nghiệp vụ khỏi test keepalive, hoặc chọn cách filter/inspect phù hợp.

Khi có proxy/load balancer:

- Xác minh idle/read timeout lớn hơn chu kỳ heartbeat.
- Đánh giá buffering của proxy; nếu proxy gom response, client sẽ không nhận event ngay.
- Theo dõi client disconnect/cancel.
- Dùng TLS, authorization và connection quota.
- Với browser EventSource, cân nhắc reconnect/backoff và `Last-Event-ID`.

## 17. Test SSE cho browser EventSource

Về phía trình duyệt:

~~~javascript
const stream = new EventSource("/api/streams/sse");

stream.addEventListener("notice", event => {
    const notice = JSON.parse(event.data);
    console.log(notice.sequence, notice.message);
});

stream.onerror = error => {
    console.error("SSE connection problem", error);
};

// Khi giao diện không cần stream nữa:
stream.close();
~~~

EventSource có cơ chế reconnect khi connection bị gián đoạn. Điều này khác với StepVerifier: StepVerifier chỉ kiểm tra một subscription ở test, không tự mô phỏng retry policy của browser.

Nếu cần test resume:

1. Server lưu event ID và lịch sử đủ lâu.
2. Client reconnect với `Last-Event-ID`.
3. Server trả đúng phần event tiếp theo.
4. Test cần xác minh không mất/không lặp ngoài semantics đã công bố.

Một server chỉ map `Flux.interval` sang id `"0", "1", ...` cho mỗi kết nối **không tự có replay**. Đừng viết test yêu cầu resume nếu server chưa implement.

## 18. Demo hoàn chỉnh: Spring Boot WebFlux, Java 17+, JUnit 5

Dự án dưới đây có ba endpoint:

- `GET /api/streams/finite` trả hai Notice dưới dạng JSON array và complete.
- `GET /api/streams/sse` trả một stream `ServerSentEvent<Notice>` vô hạn, phát mỗi 100 ms.
- `GET /api/streams/ndjson` trả stream NDJSON vô hạn với cùng notice data.

Phần unit test dùng StepVerifier, virtual time, TestPublisher và cancellation. Phần HTTP integration test dùng WebTestClient + `FluxExchangeResult` + StepVerifier.

### 18.1. Cấu trúc dự án

~~~text
webflux-stream-test/
  settings.gradle
  build.gradle
  src/
    main/java/demo/streams/
      StreamTestApplication.java
      Notice.java
      NoticeStreamService.java
      NoticeStreamController.java
    test/java/demo/streams/
      NoticeStreamServiceTest.java
      NoticeStreamHttpTest.java
~~~

### 18.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-stream-test'
~~~

### 18.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot 3.5.6 quản lý các phiên bản Spring Framework, Reactor Core và reactor-test tương thích. Với ứng dụng WebFlux này không cần thêm `spring-boot-starter-web` vì khi có cả Spring MVC và WebFlux starter, Boot thường ưu tiên MVC auto-configuration.

### 18.4. StreamTestApplication.java

~~~java
package demo.streams;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StreamTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(StreamTestApplication.class, args);
    }
}
~~~

### 18.5. Notice.java

~~~java
package demo.streams;

public record Notice(long sequence, String message) {
}
~~~

Record bất biến có value equality. Vì vậy StepVerifier có thể so sánh `new Notice(0, "notice-0")` bằng `expectNext(...)`.

### 18.6. NoticeStreamService.java

~~~java
package demo.streams;

import java.time.Duration;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class NoticeStreamService {

    public Flux<Notice> finite() {
        return Flux.just(
            new Notice(1L, "ready"),
            new Notice(2L, "done")
        );
    }

    public Flux<Notice> live() {
        return Flux.interval(Duration.ofMillis(100))
            .map(sequence ->
                new Notice(sequence, "notice-" + sequence)
            );
    }

    public Flux<Notice> transform(Flux<Long> source) {
        return source.map(sequence ->
            new Notice(sequence, "notice-" + sequence)
        );
    }
}
~~~

`finite()` là nguồn hữu hạn. `live()` là publisher cold theo subscription: mỗi subscriber bắt đầu timer riêng, phát sequence 0, 1, 2... và không hoàn tất nếu không bị cancel. `transform(...)` giúp test bằng nguồn giả do TestPublisher điều khiển, không cần timer thật.

### 18.7. NoticeStreamController.java

~~~java
package demo.streams;

import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/streams")
public class NoticeStreamController {

    private final NoticeStreamService service;

    public NoticeStreamController(NoticeStreamService service) {
        this.service = service;
    }

    @GetMapping(
        path = "/finite",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Flux<Notice> finite() {
        return service.finite();
    }

    @GetMapping(
        path = "/sse",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    public Flux<ServerSentEvent<Notice>> sse() {
        return service.live()
            .map(notice -> ServerSentEvent.<Notice>builder()
                .id(Long.toString(notice.sequence()))
                .event("notice")
                .retry(Duration.ofSeconds(3))
                .data(notice)
                .build());
    }

    @GetMapping(
        path = "/ndjson",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<Notice> ndjson() {
        return service.live();
    }
}
~~~

`@RestController` dùng HttpMessageWriter để ghi response; không phải server-side view rendering. `produces` giúp chọn codec và format. Endpoint SSE có các field id/event/retry/data. Endpoint NDJSON có mỗi Notice là một JSON object trên một dòng.

### 18.8. NoticeStreamServiceTest.java

~~~java
package demo.streams;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class NoticeStreamServiceTest {

    private final NoticeStreamService service =
        new NoticeStreamService();

    @Test
    void finiteStreamCompletes() {
        StepVerifier.create(service.finite())
            .expectNext(
                new Notice(1L, "ready"),
                new Notice(2L, "done")
            )
            .verifyComplete();
    }

    @Test
    void liveStreamProducesValuesUnderVirtualTime() {
        StepVerifier.withVirtualTime(service::live)
            .expectSubscription()
            .expectNoEvent(Duration.ofMillis(99))
            .thenAwait(Duration.ofMillis(1))
            .expectNext(new Notice(0L, "notice-0"))
            .thenAwait(Duration.ofMillis(100))
            .expectNext(new Notice(1L, "notice-1"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void cancellationReachesUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.withVirtualTime(() ->
                service.live()
                    .doOnCancel(() ->
                        cancelled.set(true))
            )
            .expectSubscription()
            .thenAwait(Duration.ofMillis(100))
            .expectNext(new Notice(0L, "notice-0"))
            .thenCancel()
            .verify(Duration.ofSeconds(2));

        assertTrue(cancelled.get());
    }

    @Test
    void takeThreeCompletesButCancelsItsSource() {
        TestPublisher<Long> source = TestPublisher.create();

        StepVerifier.create(
                service.transform(source.flux()).take(3)
            )
            .then(() -> source.next(10L, 11L, 12L))
            .expectNext(
                new Notice(10L, "notice-10"),
                new Notice(11L, "notice-11"),
                new Notice(12L, "notice-12")
            )
            .verifyComplete();

        source.assertCancelled();
    }

    @Test
    void controlledSourceErrorIsPropagated() {
        TestPublisher<Long> source = TestPublisher.create();

        StepVerifier.create(
                service.transform(source.flux())
            )
            .then(() -> source.next(7L))
            .expectNext(new Notice(7L, "notice-7"))
            .then(() -> source.error(
                new IllegalStateException("feed failed")
            ))
            .expectErrorMessage("feed failed")
            .verify(Duration.ofSeconds(2));
    }

    @Test
    void boundedDemandDoesNotRequireInfiniteCompletion() {
        StepVerifier.create(
                Flux.range(1, 3), 0
            )
            .expectSubscription()
            .thenRequest(1)
            .expectNext(1)
            .thenRequest(2)
            .expectNext(2, 3)
            .verifyComplete();
    }

    @Test
    void neverSourceCanBeCancelledExplicitly() {
        StepVerifier.create(Flux.<Notice>never())
            .expectSubscription()
            .thenCancel()
            .verify(Duration.ofSeconds(2));
    }
}
~~~

Các test có ý nghĩa khác nhau:

- `finiteStreamCompletes` xác minh onComplete thật.
- `liveStreamProducesValuesUnderVirtualTime` xác minh hai lần tick mà không đợi 200 ms thực.
- `cancellationReachesUpstream` kiểm tra doOnCancel trong cùng pipeline.
- `takeThreeCompletesButCancelsItsSource` phân biệt downstream completion với upstream cancellation.
- `controlledSourceErrorIsPropagated` xác minh một event trước lỗi.
- `boundedDemandDoesNotRequireInfiniteCompletion` kiểm tra initial request bằng 0 và cấp request từng phần.
- `neverSourceCanBeCancelledExplicitly` cho thấy một nguồn im lặng hoàn toàn vẫn test được mà không cần đợi complete.

### 18.9. NoticeStreamHttpTest.java

~~~java
package demo.streams;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.test.StepVerifier;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class NoticeStreamHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void finiteResponseCanBeAssertedAsJsonArray() {
        client.get()
            .uri("/api/streams/finite")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON)
            .expectBodyList(Notice.class)
            .hasSize(2)
            .contains(
                new Notice(1L, "ready"),
                new Notice(2L, "done")
            );
    }

    @Test
    void sseEventsAreDecodedAndCancelled() {
        FluxExchangeResult<ServerSentEvent<Notice>> response =
            client.get()
                .uri("/api/streams/sse")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.TEXT_EVENT_STREAM)
                .returnResult(
                    new ParameterizedTypeReference<
                        ServerSentEvent<Notice>>() {}
                );

        StepVerifier.create(response.getResponseBody())
            .assertNext(event -> {
                assertEquals("0", event.id());
                assertEquals("notice", event.event());
                assertEquals(Duration.ofSeconds(3), event.retry());
                assertNotNull(event.data());
                assertEquals(
                    new Notice(0L, "notice-0"),
                    event.data()
                );
            })
            .assertNext(event -> {
                assertEquals("1", event.id());
                assertEquals(
                    new Notice(1L, "notice-1"),
                    event.data()
                );
            })
            .thenCancel()
            .verify(Duration.ofSeconds(8));
    }

    @Test
    void ndjsonResponseCanBeReadIncrementally() {
        FluxExchangeResult<Notice> result =
            client.get()
                .uri("/api/streams/ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_NDJSON)
                .returnResult(Notice.class);

        StepVerifier.create(result.getResponseBody())
            .expectNext(
                new Notice(0L, "notice-0"),
                new Notice(1L, "notice-1")
            )
            .thenCancel()
            .verify(Duration.ofSeconds(8));
    }
}
~~~

Đây là integration tests có server HTTP thật chạy trên random port. Khác với unit test virtual-time, ở đây dùng timer thật 100 ms. Test giới hạn 8 giây để tránh treo nếu server không phát event. `thenCancel()` kết thúc việc tiêu thụ body và cho phép network resource được giải phóng.

**Không có assertion nguồn phải complete**, vì hai endpoint này có thiết kế vô hạn. `expectBodyList(...)` chỉ dùng cho `/finite`.

### 18.10. Chạy và thử thủ công

Cần Java 17 và Gradle. Ở thư mục dự án:

~~~bash
gradle test
~~~

Chạy ứng dụng:

~~~bash
gradle bootRun
~~~

Lấy JSON hữu hạn:

~~~bash
curl -i http://localhost:8080/api/streams/finite
~~~

Response body dự kiến:

~~~json
[
  {"sequence":1,"message":"ready"},
  {"sequence":2,"message":"done"}
]
~~~

Lấy SSE với output streaming không bị curl buffer:

~~~bash
curl -N -H "Accept: text/event-stream" \
  http://localhost:8080/api/streams/sse
~~~

Một đoạn SSE đầu stream có dạng:

~~~text
id:0
event:notice
retry:3000
data:{"sequence":0,"message":"notice-0"}

id:1
event:notice
retry:3000
data:{"sequence":1,"message":"notice-1"}

~~~

Dạng field và whitespace trên wire phụ thuộc encoder/codec, nhưng ý nghĩa `id`, `event`, `retry`, `data` phải được bảo toàn. Dùng Ctrl+C để hủy client stream; không chờ server tự complete.

Lấy NDJSON:

~~~bash
curl -N -H "Accept: application/x-ndjson" \
  http://localhost:8080/api/streams/ndjson
~~~

Các dòng đầu:

~~~text
{"sequence":0,"message":"notice-0"}
{"sequence":1,"message":"notice-1"}
{"sequence":2,"message":"notice-2"}
~~~

Không có một stdout Gradle cố định, vì version, cache và thời gian chạy thay đổi theo môi trường. Đối với test, kết quả quan trọng là task test PASS và assertions trong test class.

## 19. Phương pháp test khi upstream là repository hoặc broker

Một ứng dụng production có thể stream notification từ Redis pub/sub, Kafka hoặc database change feed. Unit test không cần broker thật nếu mục tiêu là transform/filter/order/error handling.

Ví dụ interface:

~~~java
interface LiveFeed {
    Flux<Notice> subscribe(String userId);
}
~~~

Service:

~~~java
final class FilteredFeed {
    private final LiveFeed feed;

    FilteredFeed(LiveFeed feed) {
        this.feed = feed;
    }

    Flux<Notice> forUser(String userId) {
        return feed.subscribe(userId)
            .filter(n -> n.sequence() >= 10);
    }
}
~~~

Test:

~~~java
TestPublisher<Notice> source = TestPublisher.create();
LiveFeed fake = userId -> source.flux();

FilteredFeed filtered = new FilteredFeed(fake);

StepVerifier.create(filtered.forUser("u-1"))
    .then(() -> source.next(
        new Notice(5L, "skip"),
        new Notice(10L, "keep"),
        new Notice(11L, "keep-2")
    ))
    .expectNext(
        new Notice(10L, "keep"),
        new Notice(11L, "keep-2")
    )
    .thenCancel()
    .verify(Duration.ofSeconds(2));

source.assertCancelled();
~~~

Đây là snippet kiểm tra service logic; không có HTTP. Khi cần xác minh codec/headers/reconnect/authorization, bổ sung integration tests.

Đừng fake Kafka/Redis behavior phức tạp bằng một TestPublisher rồi kết luận toàn bộ hệ thống production sẽ xử lý y hệt. Backpressure, reconnect, partition, consumer group và broker acknowledgements cần kiểm thử ở tầng tích hợp riêng.

## 20. Lỗi phổ biến khiến test SSE/Flux bị treo hoặc flaky

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng verifyComplete trên stream vô hạn | Chờ completion không tồn tại | thenCancel sau đủ dữ liệu |
| Dùng expectBodyList cho SSE vô hạn | Chờ toàn bộ body | returnResult + StepVerifier |
| Không đặt verify timeout | Suite có thể treo | verify(Duration) |
| Mong timer phát ngay t=0 | Flux.interval thông thường bắt đầu sau period đầu | expect đúng thời điểm hoặc virtual time |
| So sánh timestamp chính xác đến mili giây trên network | Flaky khi CI chậm | assert order/content và timeout đủ |
| Khởi tạo interval trước withVirtualTime | Scheduler ảo có thể không điều khiển | Tạo publisher trong supplier |
| expectNoEvent làm bước đầu | Subscription bị tính là event | expectSubscription trước |
| Phát hot TestPublisher trước verify | Dữ liệu mất | Phát qua then(...) |
| Nhầm take(3) complete với upstream complete | Test sai lifecycle | assert source cancellation |
| Assert cờ cleanup server ngay sau cancel client | Race do network async | Dùng signal/latch/await condition |
| Mong SSE lỗi giữa stream đổi HTTP status | Response đã commit | Test service error và transport/client riêng |
| Đọc SSE bằng expectBody(String.class) | Body vô hạn không hoàn tất | returnResult và lấy một số event |
| Nhầm NDJSON với JSON array | Decoder/framing khác nhau | Chọn produces/Accept và decoder đúng |
| Bỏ qua media type | Không chắc dùng codec nào | Assert Content-Type phù hợp |
| Dùng ServerSentEvent.class rồi cast data | Mất generic type, dữ liệu có thể là Map | ParameterizedTypeReference |
| Mong Last-Event-ID tự có replay | Có ID nhưng server chưa lưu history | Thiết kế store/replay rõ ràng |
| Dùng blocking Thread.sleep trong test | Test chậm và bất định | Virtual time hoặc signal kiểm soát |
| Dùng interval quá dày | Gây overflow/buffer issues | Interval hợp lý, limits/backpressure |
| Không hủy WebTestClient result | Connection/resource có thể giữ mở | thenCancel hoặc take(n) có chủ đích |
| Stream không có authorization | Lộ event người dùng khác | Phân quyền từng subscription |
| Log payload nhạy cảm | Lộ dữ liệu người dùng | Log metadata có kiểm soát |
| Proxy buffer SSE | Client không nhận incrementally | Kiểm tra config proxy/content type/flush |

## 21. Checklist QA cho streaming endpoint

Trước khi đánh dấu test hoàn tất, kiểm tra:

1. Endpoint dùng `produces` và Content-Type chính xác chưa?
2. Với SSE, event có id/event/data/retry theo contract chưa?
3. Với NDJSON, mỗi item có decode thành object độc lập chưa?
4. Đã phân biệt finite với infinite ở expectation terminal chưa?
5. HTTP test có dùng WebTestClient.returnResult để kiểm tra streaming chưa?
6. Đã dùng thenCancel khi không mong nguồn tự complete chưa?
7. Có verify timeout để không treo test không?
8. Với interval, test dùng virtual time ở unit test và real-time ở integration đúng chỗ chưa?
9. Có kiểm tra cancellation tới upstream cleanup bằng fake/signal chưa?
10. Có test error giữa stream ở tầng service chưa?
11. Có test fallback/empty trong trường hợp nghiệp vụ cần không?
12. Đã xử lý codec generic type cho ServerSentEvent chưa?
13. Có tránh assert mili giây chính xác trên network thật chưa?
14. Có giới hạn số lượng event và connection trong production chưa?
15. Có kiểm thử reconnect, heartbeat và replay nếu client phụ thuộc chúng không?

## 22. Câu hỏi ôn tập có đáp án

**Câu 1. Vì sao dùng verifyComplete cho Flux.interval vô hạn là sai?**

Vì publisher không tự phát onComplete; test sẽ đợi mãi hoặc thất bại do timeout. Dùng thenCancel sau khi kiểm tra đủ phần tử.

**Câu 2. StepVerifier.thenCancel có nghĩa upstream complete không?**

Không. Downstream chủ động hủy subscription; đây không phải tín hiệu onComplete.

**Câu 3. take(3) khác thenCancel trực tiếp thế nào?**

take(3) tạo một pipeline hoàn tất downstream sau ba phần tử và thường cancel upstream; thenCancel là hành động chủ động của test subscriber.

**Câu 4. Vì sao WebTestClient.expectBodyList không phù hợp cho SSE vô hạn?**

Vì nó muốn decode toàn bộ response thành collection, trong khi body không có điểm kết thúc.

**Câu 5. API nào của WebTestClient lấy Flux streaming?**

`returnResult(...)` tạo `FluxExchangeResult<T>` và `getResponseBody()` trả `Flux<T>`.

**Câu 6. SSE khác NDJSON ở đâu?**

SSE là format event-stream có field id/event/retry/data và event delimiter; NDJSON là các JSON object tách bằng newline.

**Câu 7. Vì sao dùng ParameterizedTypeReference<ServerSentEvent<Notice>>?**

Để giữ thông tin generic type khi decoder tạo ServerSentEvent và Notice thay vì data thành Map/Object không rõ type.

**Câu 8. Khi nào dùng withVirtualTime?**

Khi test logic dựa trên Reactor scheduler như interval/delay/timeout, để không chờ thời gian thật.

**Câu 9. Vì sao Flux.interval phải được tạo trong supplier của withVirtualTime?**

Vì scheduler ảo cần được cài trước khi operator thời gian được xây; tạo trước có thể dùng scheduler thực.

**Câu 10. expectNoEvent có xem subscription là event không?**

Có. Vì vậy thường viết expectSubscription() rồi expectNoEvent(duration).

**Câu 11. Vì sao test HTTP cancellation không nên assert server flag ngay sau verify?**

Cancellation truyền qua network và server xử lý bất đồng bộ; cần cơ chế chờ signal rõ ràng nếu muốn assert cleanup server.

**Câu 12. Có thể trả HTTP 500 sau khi SSE response đã gửi một event không?**

Không thể đổi status của response đã commit. Cần test service lỗi và client transport/contract riêng.

**Câu 13. Browser EventSource có tự replay event nhờ id không?**

Nó có thể gửi Last-Event-ID lúc reconnect, nhưng server phải implement lưu history/replay; chỉ tạo id không bảo đảm không mất event.

**Câu 14. Một test WebFlux streaming hoàn chỉnh cần xác minh những gì?**

HTTP status/content-type, decoded events và order, termination/cancellation, cùng resource cleanup hoặc reconnect nếu chúng thuộc contract.

## 23. Tổng kết

- `Flux` có thể finite, empty, error hoặc infinite; lựa chọn StepVerifier terminal expectation phải bám đúng contract.
- SSE là HTTP `text/event-stream` một chiều, có thể mang metadata id/event/retry/data.
- NDJSON là các JSON object theo dòng, cũng dùng cho HTTP streaming.
- Với WebTestClient streaming, hãy assert status/headers trước, gọi returnResult, sau đó đưa getResponseBody() vào StepVerifier.
- Infinite stream: kiểm tra một số item rồi thenCancel; không chờ verifyComplete.
- Virtual time dành cho time-based operator ở unit test; HTTP integration vẫn có network timing thật.
- TestPublisher điều khiển upstream; StepVerifier xác minh downstream.
- Cancellation có thể cleanup resource, nhưng test integration cần tính đến độ trễ network.
- Không nhầm việc Flux.take(n) complete với upstream tự complete.
- SSE event ID không tự biến thành durable replay.
- Đặt timeout cho test và giới hạn memory/connection/producer trong production.

## 24. Tài liệu chính thức

1. [Spring Framework Reference — WebTestClient, Streaming Responses](https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html): flow status/header/returnResult/getResponseBody/StepVerifier thenCancel.
2. [Project Reactor — Testing Reference](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, TestPublisher và PublisherProbe.
3. [Reactor StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): verify, thenCancel, withVirtualTime và method contracts.
4. [Spring Framework — ServerSentEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/http/codec/ServerSentEvent.html): data, id, event, retry, comment và builder.
5. [Spring Framework — Reactive Core, Streaming](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): SSE/NDJSON streaming, periodic data, heartbeats và memory limit.
6. [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/responsebody.html): reactive return types được serialize vào HTTP body.
7. [Spring Framework — Return Values](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html): Flux<ServerSentEvent> và các reactive return types.
8. [WHATWG HTML Living Standard — Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html): EventSource, event stream format, ID, reconnection và retry.
9. [Project Reactor — TestPublisher Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): nguồn điều khiển và assertions.
10. [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): SpringBootTest, WebTestClient và test web environment.
