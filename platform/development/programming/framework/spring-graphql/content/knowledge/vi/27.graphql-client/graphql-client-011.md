# Subscription bằng retrieveSubscription

GraphQL Query và Mutation thường trả về một response cho mỗi request. Subscription khác ở chỗ server phát ra nhiều kết quả theo thời gian, ví dụ thông báo khi sách được cập nhật, đơn hàng đổi trạng thái hoặc giá sản phẩm thay đổi. Phía client cần một transport có khả năng streaming và một cách tiêu thụ luồng dữ liệu đó.

Spring for GraphQL cung cấp `GraphQlClient` với API dùng chung cho HTTP, WebSocket và RSocket. Để nhận dữ liệu Subscription dưới dạng một luồng đã giải mã, client gọi `retrieveSubscription(path)` rồi chọn kiểu đích bằng `toEntity(...)`. Kết quả là `Flux<T>`: mỗi GraphQL response event được giải mã từ field path đã chọn thành một phần tử trong Flux.

Bài học này tập trung vào `retrieveSubscription`: chuẩn bị GraphQL document và variables, chọn transport, giải mã từng event, xử lý GraphQL errors và transport errors, hủy subscription, reconnect có kiểm soát, dùng interceptor và kiểm thử luồng dữ liệu.

## 1. Subscription tạo ra luồng dữ liệu

Ví dụ API thư viện phát sự kiện khi một cuốn sách được cập nhật:

```graphql
type Subscription {
  bookUpdated(bookId: ID!): BookEvent!
}

type BookEvent {
  eventId: ID!
  occurredAt: String!
  book: Book!
}

type Book {
  id: ID!
  title: String!
  status: String!
}
```

Client đăng ký:

```graphql
subscription BookUpdated($bookId: ID!) {
  bookUpdated(bookId: $bookId) {
    eventId
    occurredAt
    book {
      id
      title
      status
    }
  }
}
```

Server có thể gửi nhiều response cho cùng một operation:

```json
{
  "data": {
    "bookUpdated": {
      "eventId": "evt-101",
      "occurredAt": "2026-11-20T10:15:00Z",
      "book": {
        "id": "book-1",
        "title": "Spring for GraphQL",
        "status": "AVAILABLE"
      }
    }
  }
}
```

Một response tương ứng một event trong stream. Khi có cập nhật tiếp theo, server gửi response mới theo cùng selection set. Subscription không phải một truy vấn Query được gọi lặp lại theo chu kỳ; nó duy trì một luồng thực thi do server phát dữ liệu.

## 2. retrieveSubscription hoạt động thế nào?

Với Query hoặc Mutation, client thường dùng:

```java
Mono<Book> book = client.document("""
        query {
            bookById(id: "book-1") {
                id
                title
            }
        }
        """)
        .retrieve("bookById")
        .toEntity(Book.class);
```

`retrieve(...)` giải mã một response thành `Mono<T>`. Với Subscription, mỗi response event cần được giải mã và phát tiếp, nên API là:

```java
Flux<BookEvent> events = client.document("""
        subscription BookUpdated($bookId: ID!) {
            bookUpdated(bookId: $bookId) {
                eventId
                occurredAt
                book {
                    id
                    title
                    status
                }
            }
        }
        """)
        .variable("bookId", "book-1")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Luồng gọi API:

1. `document(...)` khai báo GraphQL Subscription operation.
2. `variable(...)` cung cấp giá trị cho biến `$bookId`.
3. `retrieveSubscription("bookUpdated")` chọn field trong phần `data` của mỗi response.
4. `toEntity(BookEvent.class)` giải mã giá trị field thành Java object.
5. `Flux<BookEvent>` phát một BookEvent cho mỗi response event nhận được.

`retrieveSubscription(path)` là shortcut của `executeSubscription()` với một field path được giải mã lặp lại cho từng response. Path được tính tương đối từ key `data`, dùng dấu chấm để đi qua field lồng nhau. Nếu field được alias trong operation, hãy dùng alias tương ứng trong path.

Ví dụ với alias:

```graphql
subscription {
  update: bookUpdated(bookId: "book-1") {
    eventId
    book { id title }
  }
}
```

Path phải là `update`:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("update")
        .toEntity(BookEvent.class);
```

## 3. Khai báo kiểu Java cho event

DTO có thể là Java record:

```java
public record BookEvent(
        String eventId,
        String occurredAt,
        BookSnapshot book) {
}

public record BookSnapshot(
        String id,
        String title,
        String status) {
}
```

Nếu một response event trả về list ở field được chọn, dùng `toEntityList(...)`:

```java
Flux<List<BookEvent>> batches = client.document("""
        subscription {
            recentBookEvents {
                eventId
                occurredAt
            }
        }
        """)
        .retrieveSubscription("recentBookEvents")
        .toEntityList(BookEvent.class);
```

Với generic type phức tạp, có thể dùng `ParameterizedTypeReference`:

```java
ParameterizedTypeReference<Map<String, BookEvent>> eventType =
        new ParameterizedTypeReference<>() {};

Flux<Map<String, BookEvent>> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(eventType);
```

Kiểu Java cần khớp cấu trúc dữ liệu thực tế mà selection set trả về. Không yêu cầu DTO phải chứa mọi field của GraphQL type; chỉ cần các field được chọn và muốn giải mã.

## 4. Chọn transport hỗ trợ Subscription

Không phải GraphQlClient nào cũng hỗ trợ streaming. Spring for GraphQL cung cấp ba lựa chọn phổ biến:

| Client | Transport | Khi phù hợp |
| --- | --- | --- |
| `HttpGraphQlClient` | HTTP Server-Sent Events (SSE) | Muốn dùng HTTP và stream một chiều từ server |
| `WebSocketGraphQlClient` | WebSocket | Cần kết nối hai chiều, nhiều subscription hoặc multiplexing |
| `RSocketGraphQlClient` | RSocket | Ứng dụng dùng RSocket request-stream và session |

`HttpSyncGraphQlClient` dùng blocking HTTP transport và không phải lựa chọn cho Subscription streaming. Dùng client transport có hỗ trợ stream trước khi gọi `retrieveSubscription`.

### HTTP với Server-Sent Events

`HttpGraphQlClient` sử dụng `WebClient` và có thể nhận Subscription qua SSE nếu server hỗ trợ:

```java
WebClient webClient = WebClient.builder()
        .baseUrl("https://api.example.com/graphql")
        .build();

HttpGraphQlClient client = HttpGraphQlClient.builder(webClient)
        .build();
```

Sau đó dùng chung API `retrieveSubscription`:

```java
Flux<BookEvent> events = client.document("""
        subscription {
            bookUpdated(bookId: "book-1") {
                eventId
                occurredAt
                book { id title status }
            }
        }
        """)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Với SSE, client gửi HTTP POST có GraphQL request JSON và yêu cầu response media type `text/event-stream`. Server gửi các response event theo định dạng Server-Sent Events. SSE là luồng một chiều từ server đến client; client hủy luồng bằng cách đóng/cancel HTTP response.

### WebSocket

`WebSocketGraphQlClient` dùng một WebSocket connection được chia sẻ cho các request:

```java
URI url = URI.create("wss://api.example.com/graphql");
WebSocketClient webSocketClient = new ReactorNettyWebSocketClient();

WebSocketGraphQlClient client =
        WebSocketGraphQlClient.builder(url, webSocketClient)
                .build();
```

WebSocket client là connection-oriented và multiplexed:

- Kết nối được thiết lập tự động khi có request đầu tiên.
- Có thể gọi `start()` để kết nối trước.
- Nhiều request/Subscription dùng chung một connection.
- Khi connection mất, client có thể kết nối lại ở request tiếp theo hoặc khi gọi `start()`.
- `stop()` hủy request đang chạy, đóng connection và từ chối request mới.

Nên dùng một `WebSocketGraphQlClient` cho mỗi server để chia sẻ connection. Tạo một client instance cho mỗi Subscription sẽ tạo nhiều connection không cần thiết.

### RSocket

Nếu server cung cấp GraphQL qua RSocket, có thể tạo client như sau:

```java
URI uri = URI.create("ws://localhost:7000/rsocket");
ClientTransport transport = WebsocketClientTransport.create(uri);

RSocketGraphQlClient client = RSocketGraphQlClient.builder()
        .clientTransport(transport)
        .build();
```

RSocket client cũng duy trì session dùng chung và hỗ trợ request streaming. Cách khai báo GraphQL operation và gọi `retrieveSubscription` vẫn giống HTTP/WebSocket; phần khác biệt nằm ở transport builder và cách server triển khai RSocket.

## 5. Đưa variables và operation name vào request

Subscription có thể nhận arguments giống Query:

```graphql
subscription BookUpdated($bookId: ID!, $includeAudit: Boolean!) {
  bookUpdated(bookId: $bookId, includeAudit: $includeAudit) {
    eventId
    book {
      id
      title
    }
  }
}
```

Client truyền variables:

```java
Flux<BookEvent> events = client.document(document)
        .operationName("BookUpdated")
        .variable("bookId", "book-1")
        .variable("includeAudit", false)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Hoặc truyền tất cả variables cùng lúc:

```java
Map<String, Object> variables = Map.of(
        "bookId", "book-1",
        "includeAudit", false);

Flux<BookEvent> events = client.document(document)
        .operationName("BookUpdated")
        .variables(variables)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class);
```

Khai báo operation name hữu ích khi GraphQL document chứa nhiều operation hoặc khi cần quan sát log/tracing theo tên operation. Biến GraphQL phải khớp tên và kiểu đã khai báo trong document.

## 6. Tiêu thụ Flux và hủy Subscription

`retrieveSubscription` chỉ tạo publisher. Subscription thực sự bắt đầu khi có subscriber:

```java
Disposable disposable = client.document(document)
        .variable("bookId", "book-1")
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .subscribe(
                event -> log.info("Book updated: {}", event.eventId()),
                error -> log.error("Subscription failed", error),
                () -> log.info("Subscription completed"));
```

Để dừng từ client, hủy subscription:

```java
disposable.dispose();
```

Với WebSocket, cancellation của Flux khiến client gửi message `complete` cho operation tương ứng. Transport có thể tiếp tục giữ connection để các Subscription khác hoạt động.

Một số operator tự hủy upstream:

```java
Flux<BookEvent> firstTenEvents = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .take(10);
```

`take(10)` hoàn tất sau mười event và cancel Subscription phía trên. Có thể dùng `timeout(...)` để giới hạn thời gian chờ:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .timeout(Duration.ofMinutes(5));
```

Timeout phát lỗi `TimeoutException` và hủy upstream. Hãy phân biệt việc hủy một operation với việc đóng toàn bộ WebSocket client bằng `stop()`.

Không gọi `subscribe()` bên trong service rồi bỏ quên `Disposable`. Hãy để caller sở hữu vòng đời stream hoặc lưu handle cancellation trong một component quản lý subscription có lifecycle rõ ràng.

## 7. Xử lý SubscriptionErrorException và lỗi transport

Subscription Flux có thể kết thúc vì nhiều nguyên nhân. Hai nhóm quan trọng:

| Loại lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `SubscriptionErrorException` | Server WebSocket kết thúc Subscription bằng message `error` có GraphQL errors | Đọc errors, phân loại lỗi nghiệp vụ hoặc lỗi operation |
| `GraphQlTransportException` | Lỗi transport hoặc kết nối, ví dụ WebSocket bị ngắt | Xem xét reconnect/retry nếu phù hợp |
| `WebSocketDisconnectedException` | WebSocket connection bị đóng hoặc mất trước khi stream kết thúc | Kết nối lại và đăng ký lại khi chính sách cho phép |
| `FieldAccessException` | Field path không có giá trị hợp lệ hoặc có field errors khi giải mã | Đọc response và field liên quan |
| `GraphQlClientException` | Response field không giải mã được sang kiểu Java yêu cầu | Kiểm tra selection set và DTO |

`SubscriptionErrorException` chứa GraphQL errors nhận từ WebSocket error message. Class này kế thừa `GraphQlTransportException`, vì vậy nếu retry theo base class thì cần loại trừ exception chuyên biệt này. Đây là lỗi do server chủ động kết thúc stream, khác với lỗi mất kết nối. Không nên retry vô điều kiện lỗi nghiệp vụ hoặc lỗi authorization vì chúng sẽ lặp lại mà không tự khắc phục.

Ví dụ retry có giới hạn cho lỗi transport:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
                .filter(error ->
                        error instanceof GraphQlTransportException
                                && !(error instanceof SubscriptionErrorException)));
```

Retry sẽ thực hiện lại Subscription operation khi transport error xảy ra. Nó không đảm bảo nhận đủ hoặc đúng một lần mọi event trong khoảng thời gian connection bị mất. Nếu nghiệp vụ cần không bỏ sót sự kiện, thiết kế event ID/cursor và cơ chế resume hoặc truy vấn bù sau khi reconnect.

Có thể ghi lại GraphQL errors của server trước khi stream kết thúc:

```java
Flux<BookEvent> events = client.document(document)
        .retrieveSubscription("bookUpdated")
        .toEntity(BookEvent.class)
        .doOnError(SubscriptionErrorException.class,
                error -> log.warn("Subscription errors: {}", error.getErrors()));
```

`getErrors()` trả về danh sách GraphQL response errors có trong WebSocket `error` message. Hãy ghi log có kiểm soát và không đưa dữ liệu nhạy cảm từ error extensions vào log công khai.

## 8. Khi nào dùng executeSubscription thay cho retrieveSubscription?

`retrieveSubscription(path)` phù hợp khi chỉ cần một field đã chọn từ mỗi response. Nếu cần đọc toàn bộ response, xem GraphQL errors, xử lý field null hoặc metadata, dùng `executeSubscription()`:

```java
Flux<ClientGraphQlResponse> responses = client.document(document)
        .variable("bookId", "book-1")
        .executeSubscription();
```

Ví dụ xử lý từng response:

```java
Flux<BookEvent> events = client.document(document)
        .executeSubscription()
        .map(response -> {
            if (!response.isValid()) {
                // Request-level failure: inspect response.getErrors().
                throw new IllegalStateException("Subscription response is invalid");
            }

            ClientResponseField field = response.field("bookUpdated");
            if (field.getValue() == null) {
                if (field.getErrors().isEmpty()) {
                    // Field is optional and has no value for this event.
                    return null;
                }
                // Field failure: inspect field.getErrors().
                throw new IllegalStateException("bookUpdated field failed");
            }

            return field.toEntity(BookEvent.class);
        })
        .filter(Objects::nonNull);
```

Đoạn code minh họa cách kiểm tra response và field; trong ứng dụng thật, thay exception mẫu bằng domain exception hoặc error type riêng. `ClientGraphQlResponse` cho phép kiểm tra response validity và truy cập `ClientResponseField`.

So sánh:

| API | Kết quả | Dùng khi |
| --- | --- | --- |
| `retrieveSubscription(path).toEntity(Type.class)` | `Flux<Type>` | Chỉ cần decode một field trong từng event |
| `retrieveSubscription(path).toEntityList(Type.class)` | `Flux<List<Type>>` | Field được chọn là list |
| `executeSubscription()` | `Flux<ClientGraphQlResponse>` | Cần kiểm tra toàn response và nhiều field |

## 9. Interceptor cho Subscription stream

`GraphQlClientInterceptor` có hai method:

- `intercept(...)` cho request trả về một response.
- `interceptSubscription(...)` cho Subscription trả về `Flux<ClientGraphQlResponse>`.

Ví dụ ghi log từng response event:

```java
public class SubscriptionLoggingInterceptor implements GraphQlClientInterceptor {

    @Override
    public Mono<ClientGraphQlResponse> intercept(
            ClientGraphQlRequest request,
            Chain chain) {
        return chain.next(request);
    }

    @Override
    public Flux<ClientGraphQlResponse> interceptSubscription(
            ClientGraphQlRequest request,
            SubscriptionChain chain) {

        return chain.next(request)
                .doOnNext(response -> log.debug(
                        "Received GraphQL subscription response"));
    }
}
```

Đăng ký interceptor qua builder:

```java
WebSocketGraphQlClient client = WebSocketGraphQlClient.builder(url, webSocketClient)
        .interceptor(new SubscriptionLoggingInterceptor())
        .build();
```

Interceptor phù hợp cho logging, tracing, correlation metadata và quan sát lỗi ở mức client. Không log toàn bộ payload nếu event có dữ liệu cá nhân hoặc thông tin nhạy cảm. Với WebSocket connection-specific messages như `connection_init` và `connection_ack`, dùng `WebSocketGraphQlClientInterceptor`. Mỗi `WebSocketGraphQlClient` chỉ đăng ký tối đa một interceptor thuộc loại chuyên biệt này.

## 10. Authentication với WebSocket connection

WebSocket client có thể gửi headers trong lúc thiết lập handshake:

```java
WebSocketGraphQlClient client = WebSocketGraphQlClient.builder(url, webSocketClient)
        .headers(headers -> headers.setBearerAuth(accessToken))
        .build();
```

Một số server yêu cầu token trong payload `connection_init` thay vì HTTP handshake headers. Khi đó có thể triển khai `WebSocketGraphQlClientInterceptor`:

```java
public class WebSocketAuthInterceptor implements WebSocketGraphQlClientInterceptor {

    private final String accessToken;

    public WebSocketAuthInterceptor(String accessToken) {
        this.accessToken = accessToken;
    }

    @Override
    public Mono<Object> connectionInitPayload() {
        return Mono.just(Map.of("Authorization", "Bearer " + accessToken));
    }

    @Override
    public Mono<Void> handleConnectionAck(Map<String, Object> payload) {
        return Mono.empty();
    }
}
```

Chỉ dùng đúng cơ chế mà server GraphQL WebSocket đã cấu hình. Không gửi cùng credential vào nhiều vị trí một cách tùy tiện. Khi token hết hạn, cần cập nhật credential và tái lập connection/session theo cơ chế của client/server; connection đã xác thực không tự động nhận token mới.

## 11. WebSocket client lifecycle

`WebSocketGraphQlClient` giữ connection dùng chung cho nhiều operation. Có thể quản lý tường minh:

```java
client.start()
        .thenMany(client.document(document)
                .retrieveSubscription("bookUpdated")
                .toEntity(BookEvent.class))
        .subscribe(this::handleEvent);
```

Khi ứng dụng dừng:

```java
Mono<Void> stopSession = client.stop();
```

`stop()` trả về `Mono<Void>` và đóng connection, đồng thời hủy request đang chạy. Phải subscribe hoặc ghép publisher này vào shutdown pipeline; chỉ gọi `client.stop()` rồi bỏ qua Mono không chờ quá trình dừng hoàn tất. Trong Spring application, nên quản lý client như một singleton bean và đóng nó ở lifecycle shutdown. Không tạo client mới cho từng message hoặc từng lần gọi method.

Nếu client kết nối lại sau khi mất mạng, các subscription đang chạy có thể bị kết thúc. Việc mở lại connection không đảm bảo tự động khôi phục đúng vị trí stream cũ. Hãy đăng ký lại operation và dùng cursor/event ID nếu cần resume.

## 12. Kiểm thử Subscription Flux

Có thể dùng Reactor `StepVerifier` để kiểm tra cách consumer xử lý event stream:

```java
StepVerifier.create(bookEventService.eventsFor("book-1"))
        .expectNextMatches(event ->
                event.book().id().equals("book-1"))
        .expectNextMatches(event ->
                event.book().status().equals("AVAILABLE"))
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Ví dụ trên kiểm tra một publisher do service cung cấp. Để kiểm tra `retrieveSubscription` thực sự tích hợp đúng transport, cần integration test với GraphQL server có Subscription endpoint và một client thật:

1. Khởi chạy server WebSocket hoặc SSE trong test.
2. Tạo `WebSocketGraphQlClient` hoặc `HttpGraphQlClient`.
3. Đăng ký Subscription bằng `retrieveSubscription`.
4. Kích hoạt mutation hoặc event publisher phía server.
5. Dùng `StepVerifier` xác nhận client nhận đúng event.
6. Hủy Flux và xác nhận server nhận cancellation/complete.
7. Kiểm tra server error và transport disconnect riêng biệt.

Không dùng `Thread.sleep` để chờ event trong test. Dùng `StepVerifier`, timeout có giới hạn và tín hiệu đồng bộ để test ổn định.

## 13. Lỗi thường gặp

| Biểu hiện | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `retrieveSubscription` không nhận được event | Client transport không hỗ trợ streaming hoặc server chưa bật Subscription transport | Dùng HTTP SSE, WebSocket hoặc RSocket tương thích |
| Lỗi khi dùng `HttpSyncGraphQlClient` | Blocking HTTP client không hỗ trợ Subscription stream | Chuyển sang `HttpGraphQlClient` với SSE hoặc WebSocket |
| `FieldAccessException` khi decode | Sai path, alias hoặc field trả error | Kiểm tra response path; dùng `executeSubscription()` nếu cần toàn response |
| DTO không giải mã được | Selection set và Java type không khớp | Sửa field selection hoặc DTO |
| Flux không bắt đầu | Chưa có subscriber | Subscribe hoặc trả Flux cho framework tiêu thụ |
| Server không dừng stream sau khi client rời đi | Consumer không cancel hoặc resource server không xử lý cancellation | Hủy Disposable/Flux và kiểm tra publisher cleanup |
| Subscription kết thúc bằng `SubscriptionErrorException` | Server gửi error message | Đọc GraphQL errors; chỉ retry nếu lỗi có thể phục hồi |
| `WebSocketDisconnectedException` | Connection bị mất | Xử lý transport error, reconnect có giới hạn và đăng ký lại |
| Nhận thiếu event sau reconnect | Subscription được tạo lại từ thời điểm mới | Dùng event ID/cursor và cơ chế resume/replay |
| Tạo quá nhiều WebSocket connection | Tạo client instance lặp lại | Dùng một client dùng chung cho mỗi server |
| Credential không được nhận | Server yêu cầu handshake header hoặc connection-init payload khác nhau | Đồng bộ cách xác thực với WebSocket server |
| Test treo chờ event | Không có timeout hoặc publisher không phát tín hiệu | Dùng StepVerifier với timeout và cleanup |

## 14. Nguyên tắc sử dụng retrieveSubscription

- Chọn transport có khả năng streaming: HTTP SSE, WebSocket hoặc RSocket.
- Viết operation bằng `subscription` và truyền variables đúng kiểu.
- Chọn đúng field path dưới `data` trong `retrieveSubscription(path)`.
- Dùng `toEntity` cho một object hoặc `toEntityList` cho list trong mỗi event.
- Dùng `executeSubscription()` khi cần đọc toàn bộ response, GraphQL errors hoặc field null.
- Xử lý riêng `SubscriptionErrorException` và `GraphQlTransportException`.
- Retry có giới hạn và lọc loại lỗi; không retry vô điều kiện lỗi nghiệp vụ.
- Hủy Flux khi không còn cần stream để giải phóng tài nguyên server.
- Dùng một `WebSocketGraphQlClient`/`RSocketGraphQlClient` dùng chung cho mỗi server.
- Quản lý client lifecycle và credential rotation.
- Dùng event ID/cursor nếu ứng dụng cần resume hoặc chống bỏ sót event sau reconnect.
- Kiểm thử event, error, cancellation và disconnect bằng `StepVerifier` cùng integration test.

## 15. Bài tập thực hành

Xây dựng client nhận thông báo cập nhật sách:

1. Khai báo Subscription `bookUpdated(bookId: ID!)` và type `BookEvent` trên server.
2. Tạo `WebSocketGraphQlClient` trỏ tới endpoint của server.
3. Viết GraphQL document có biến `$bookId`.
4. Gọi `retrieveSubscription("bookUpdated").toEntity(BookEvent.class)`.
5. Tiêu thụ Flux và in event ID cùng trạng thái sách.
6. Thử truyền operation name và nhiều variables.
7. Hủy Flux sau năm event và xác nhận server dừng Subscription.
8. Thử `executeSubscription()` để đọc response cùng GraphQL errors.
9. Mô phỏng server phát Subscription error và xử lý `SubscriptionErrorException`.
10. Ngắt WebSocket và xử lý `WebSocketDisconnectedException`.
11. Thêm retry có giới hạn chỉ cho lỗi transport.
12. Thiết kế event ID để consumer có thể đồng bộ lại sau reconnect.
13. Viết StepVerifier test cho event stream, error và cancellation.

Sau bài tập, bạn cần hiểu `retrieveSubscription` giải mã từng response event thành Flux như thế nào, chọn đúng transport, quản lý vòng đời stream và phân biệt lỗi GraphQL với lỗi kết nối.

## 16. Tài liệu tham khảo

- [Spring for GraphQL — Client: Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — GraphQlClient.RequestSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RequestSpec.html)
- [Spring for GraphQL — RetrieveSubscriptionSpec API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClient.RetrieveSubscriptionSpec.html)
- [Spring for GraphQL — WebSocketGraphQlClient API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketGraphQlClient.html)
- [Spring for GraphQL — SubscriptionErrorException API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Project Reactor — Testing with StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)

Method signatures và transport behavior có thể thay đổi theo phiên bản Spring for GraphQL. Hãy kiểm tra reference documentation/Javadoc khớp với dependency mà Spring Boot quản lý, đặc biệt khi nâng cấp client hoặc WebSocket protocol.
