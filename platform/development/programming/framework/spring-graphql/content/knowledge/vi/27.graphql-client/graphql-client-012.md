# `SubscriptionErrorException` trong Spring GraphQL Client

Khi client đăng ký một GraphQL subscription, kết quả được nhận dưới dạng một luồng bất đồng bộ như `Flux<T>`. Luồng có thể phát nhiều event rồi hoàn tất, bị hủy bởi client, mất kết nối hoặc kết thúc bằng lỗi do server gửi. Spring for GraphQL biểu diễn trường hợp subscription kết thúc bằng một GraphQL `error` message bằng `SubscriptionErrorException`.

`SubscriptionErrorException` là exception phía client, thuộc package `org.springframework.graphql.client`. Nó mang theo danh sách GraphQL errors mà server gửi trong thông điệp kết thúc subscription. Hiểu exception này giúp phân biệt lỗi nghiệp vụ từ server với lỗi của từng event, lỗi giải mã field và lỗi mất kết nối; từ đó chọn cách log, hiển thị, phục hồi hoặc đăng ký lại subscription phù hợp.

## 1. `SubscriptionErrorException` là gì?

`SubscriptionErrorException` là một lớp con của `GraphQlTransportException`, được Spring for GraphQL dùng khi subscription stream kết thúc bởi thông điệp GraphQL `error` từ server. Exception cung cấp phương thức `getErrors()` để đọc các GraphQL errors có trong payload đó.

Quan hệ kế thừa:

```text
RuntimeException
       |
       v
NestedRuntimeException
       |
       v
GraphQlClientException
       |
       v
GraphQlTransportException
       |
       v
SubscriptionErrorException
```

Các API chính:

| API | Ý nghĩa |
|---|---|
| `getErrors()` | Trả về `List<ResponseError>` chứa GraphQL errors từ thông điệp kết thúc subscription. |
| `getRequest()` | Kế thừa từ `GraphQlClientException`; trả về request GraphQL đã gặp lỗi. |
| `getMessage()` | Thông điệp của exception, hữu ích cho log tổng quát; không nên dùng làm mã lỗi ổn định. |
| `getCause()` | Nguyên nhân gốc nếu exception có cause. |

Class này có từ Spring for GraphQL 1.0.0. Javadoc mô tả đây là một WebSocket `GraphQlTransportException` được tạo khi subscription kết thúc bằng thông điệp `error`.

Spring for GraphQL có nhiều transport streaming như WebSocket, HTTP Server-Sent Events và RSocket. Cách biểu diễn lỗi cuối stream phụ thuộc transport và protocol; không nên giả định mọi transport đều tạo cùng một subtype exception trong mọi tình huống. Phần dưới tập trung vào trường hợp terminal GraphQL `error` message mà `SubscriptionErrorException` đại diện.

## 2. Khi nào subscription phát sinh exception này?

Với GraphQL over WebSocket, client gửi một subscription operation và server bắt đầu phát event. Nếu publisher phía server kết thúc bằng lỗi, transport có thể gửi một thông điệp `error` cuối cùng chứa danh sách GraphQL errors. Client nhận thông điệp này và kết thúc `Flux` bằng `SubscriptionErrorException`.

Ví dụ luồng:

```text
Client                         Server
  |                               |
  |---- subscribe operation ----->|
  |                               |
  |<--------- next event 1 -------|
  |<--------- next event 2 -------|
  |<--------- next event 3 -------|
  |                               |
  |<---- error [GraphQL errors] --|
  |                               |
  v                               |
Flux kết thúc bằng
SubscriptionErrorException
```

Đây là lỗi kết thúc operation. Client không nhận thêm event từ chính subscription đó sau thông điệp `error`; muốn tiếp tục cần xử lý nguyên nhân và tạo subscription mới nếu phù hợp.

Không phải mọi lỗi trong một event đều tạo ra `SubscriptionErrorException`. Một response `next` vẫn có thể chứa `data` và `errors` ở cấp field. Trường hợp đó được quan sát thông qua `ClientGraphQlResponse` hoặc `FieldAccessException` khi client dùng shortcut để giải mã field.

## 3. Sử dụng `retrieveSubscription`

`retrieveSubscription(path)` là cách ngắn gọn để lấy một field trong mỗi response của subscription. Kết quả trả về là một `Flux` có thể giải mã thành kiểu Java:

```java
Flux<OrderEvent> events = graphQlClient.document("""
        subscription WatchOrder($orderId: ID!) {
            orderStatusChanged(orderId: $orderId) {
                orderId
                currentStatus
                occurredAt
            }
        }
        """)
    .variable("orderId", "order-01")
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class);
```

`retrieveSubscription` phù hợp khi client chỉ cần một response path và muốn Spring chuyển từng event sang DTO. Luồng `events` có thể kết thúc theo các cách:

- Hoàn tất bình thường nếu subscription kết thúc bình thường.
- Phát `SubscriptionErrorException` nếu server gửi thông điệp `error` kết thúc operation.
- Phát `GraphQlTransportException`, ví dụ `WebSocketDisconnectedException`, nếu kết nối WebSocket bị đóng hoặc mất khi subscription đang chạy.
- Phát `FieldAccessException` nếu field path cần giải mã có lỗi hoặc không thể truy cập theo response.

`retrieveSubscription` là shortcut. Khi cần phân biệt rõ lỗi request, field nullable, field failure và các lỗi ở path khác, hãy dùng `executeSubscription()`.

## 4. Đọc GraphQL errors bằng `getErrors()`

Ví dụ bắt exception và đọc danh sách lỗi:

```java
import org.springframework.graphql.ResponseError;
import org.springframework.graphql.client.SubscriptionErrorException;

Flux<OrderEvent> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> {
        if (error instanceof SubscriptionErrorException ex) {
            ex.getErrors().forEach(graphQlError ->
                log.warn("Subscription error: message={}, path={}, extensions={}",
                    graphQlError.getMessage(),
                    graphQlError.getPath(),
                    graphQlError.getExtensions())
            );
        }
    });
```

`doOnError` chỉ quan sát lỗi; exception vẫn được truyền xuống subscriber. Đây thường là lựa chọn tốt khi cần ghi log, metrics hoặc tracing mà vẫn để tầng gọi quyết định cách xử lý.

Không nên log toàn bộ request variables nếu chúng có token, thông tin cá nhân hoặc dữ liệu nhạy cảm. `getRequest()` hữu ích để liên hệ exception với request đã gửi, nhưng cần chọn lọc metadata trước khi đưa vào log.

## 5. Nội dung của `ResponseError`

`getErrors()` trả về `List<ResponseError>`. Mỗi `ResponseError` cung cấp thông tin chuẩn của GraphQL error:

| Phương thức | Nội dung |
|---|---|
| `getMessage()` | Mô tả lỗi dành cho developer. |
| `getErrorType()` | Phân loại lỗi theo GraphQL Java nếu có. |
| `getExtensions()` | Metadata bổ sung, có thể chứa mã lỗi do server quy định. |
| `getLocations()` | Vị trí line/column trong GraphQL document nếu xác định được. |
| `getParsedPath()` | Danh sách path segment; field là `String`, chỉ số list là `Integer`. |
| `getPath()` | Path được biểu diễn thành chuỗi, ví dụ `order.events[2]`. |

Ví dụ đọc mã lỗi trong `extensions`:

```java
private void logSubscriptionErrors(SubscriptionErrorException exception) {
    for (ResponseError error : exception.getErrors()) {
        Object code = error.getExtensions().get("code");

        log.warn("GraphQL subscription failed: code={}, message={}, path={}",
            code, error.getMessage(), error.getPath());
    }
}
```

Server có thể không gửi `extensions.code`; vì vậy, hãy xử lý trường hợp thiếu code. Client nên dùng mã lỗi đã được API tài liệu hóa thay vì phân tích chuỗi `message`.

## 6. Phân biệt lỗi subscription cuối luồng với lỗi trong từng event

Đây là điểm quan trọng nhất khi sử dụng GraphQL client.

**Lỗi kết thúc subscription:** server gửi thông điệp `error` kết thúc operation. `retrieveSubscription` phát `SubscriptionErrorException`; không còn event tiếp theo trong stream đó.

**Lỗi ở một field trong response `next`:** server gửi một GraphQL execution result có thể chứa cả `data` và `errors`. Subscription vẫn có thể tiếp tục phát event tiếp theo. Nếu dùng `executeSubscription()`, client có thể kiểm tra từng response. Nếu dùng `retrieveSubscription(path)`, việc giải mã field có error có thể tạo `FieldAccessException`.

Ví dụ response event có partial data:

```json
{
  "data": {
    "orderStatusChanged": {
      "orderId": "order-01",
      "currentStatus": null
    }
  },
  "errors": [
    {
      "message": "Could not resolve current status",
      "path": ["orderStatusChanged", "currentStatus"],
      "extensions": { "code": "STATUS_LOOKUP_FAILED" }
    }
  ]
}
```

Response này là một event result có lỗi ở field. Nó khác với thông điệp terminal `error` của subscription protocol.

## 7. Dùng `executeSubscription()` để kiểm soát từng response

Khi cần xử lý partial data hoặc field error mà vẫn tiếp tục nhận event sau đó, dùng `executeSubscription()`:

```java
Flux<ClientGraphQlResponse> responses = graphQlClient
    .document(subscriptionDocument)
    .executeSubscription();
```

Mỗi phần tử `ClientGraphQlResponse` đại diện một execution result. Có thể kiểm tra response và field trước khi giải mã:

```java
Flux<OrderEvent> events = graphQlClient
    .document(subscriptionDocument)
    .executeSubscription()
    .handle((response, sink) -> {
        if (!response.isValid()) {
            response.getErrors().forEach(error ->
                log.warn("Subscription response error: {}", error.getMessage())
            );
            sink.error(new IllegalStateException("Subscription request is invalid"));
            return;
        }

        ClientResponseField field = response.field("orderStatusChanged");

        if (field.getValue() == null) {
            if (field.getErrors().isEmpty()) {
                // Giá trị null là hợp lệ theo schema.
                return;
            }

            field.getErrors().forEach(error ->
                log.warn("Event field error: {}", error.getMessage())
            );
            return;
        }

        sink.next(field.toEntity(OrderEvent.class));
    });
```

Đoạn code minh họa chính sách bỏ qua event có field lỗi và tiếp tục nhận event sau. Ứng dụng có thể chọn phát một domain result chứa lỗi, ghi nhận metrics hoặc kết thúc stream tùy hợp đồng client. Không nên âm thầm bỏ qua lỗi nếu việc thiếu event có thể làm sai trạng thái nghiệp vụ.

Lưu ý: `response.isValid()` giúp phát hiện request-level error; `field.getErrors()` cho biết lỗi liên quan tới field path. Một response `next` có lỗi không tự động có nghĩa toàn bộ subscription đã kết thúc.

## 8. Phân biệt với `FieldAccessException`

`FieldAccessException` là exception từ thao tác đọc/giải mã field của một GraphQL response. Nó thường xuất hiện khi:

- Response không hợp lệ.
- Field path không tồn tại.
- Field là `null` và có error liên quan.
- Có error tại, phía trên hoặc phía dưới field path cần truy cập.

Exception cung cấp:

- `getResponse()` để xem `ClientGraphQlResponse`.
- `getField()` để xem `ClientResponseField` gây lỗi.

Trong khi đó, `SubscriptionErrorException` báo rằng subscription stream nhận thông điệp terminal `error` từ server. Hai exception có mục đích khác nhau:

| Exception | Thời điểm | Dữ liệu có thể đọc |
|---|---|---|
| `SubscriptionErrorException` | Subscription kết thúc bằng protocol error message | `getErrors()`, `getRequest()`. |
| `FieldAccessException` | Shortcut không thể truy cập/giải mã field trong response | `getResponse()`, `getField()`. |
| `GraphQlTransportException` | Lỗi transport hoặc encoding/decoding | Request và cause tùy loại exception. |

Nếu cần xử lý partial data và field errors một cách tường minh, ưu tiên `executeSubscription()` thay vì chỉ dựa vào `retrieveSubscription(path)`.

## 9. Phân biệt với `WebSocketDisconnectedException`

`WebSocketDisconnectedException` là một `GraphQlTransportException` khác, được phát khi WebSocket bị đóng trong lúc request hoặc subscription còn đang chạy. Nó thường không mang danh sách GraphQL errors từ server; thay vào đó, nó cung cấp trạng thái đóng qua `getCloseStatus()`.

| Tình huống | Exception thường gặp | Hướng xử lý |
|---|---|---|
| Server gửi GraphQL `error` message để kết thúc subscription | `SubscriptionErrorException` | Đọc `getErrors()`, xác định lỗi và quyết định có đăng ký lại hay không. |
| WebSocket đóng hoặc mất kết nối | `WebSocketDisconnectedException` | Kiểm tra close status, reconnect và khởi động lại subscription nếu an toàn. |
| Field trong một event response có error | `FieldAccessException` khi dùng `retrieveSubscription` | Đọc response/field hoặc chuyển sang `executeSubscription`. |
| Lỗi client GraphQL khác | `GraphQlClientException` hoặc subtype | Kiểm tra request, cause và loại lỗi cụ thể. |

Không nên gom mọi lỗi vào một nhánh `onErrorResume(GraphQlTransportException.class, ...)` rồi retry vô điều kiện. `SubscriptionErrorException` và mất kết nối có ý nghĩa khác nhau, nên chính sách phục hồi cũng khác nhau.

## 10. Xử lý exception mà vẫn truyền lỗi cho tầng gọi

Khi cần log và sau đó để tầng trên quyết định, dùng `doOnError`:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(SubscriptionErrorException.class, this::logSubscriptionErrors);
```

Hoặc dùng một callback chung:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .doOnError(error -> {
        if (error instanceof SubscriptionErrorException ex) {
            logSubscriptionErrors(ex);
        }
    });
```

`doOnError` không thay thế exception bằng giá trị khác. Subscriber cuối cùng vẫn nhận lỗi và có thể hiển thị trạng thái phù hợp.

## 11. Khi nào dùng `onErrorResume`?

`onErrorResume` chuyển lỗi thành một publisher khác. Chỉ dùng khi ứng dụng có chính sách fallback rõ ràng.

Ví dụ một màn hình theo dõi chấp nhận kết thúc luồng và hiển thị trạng thái disconnected:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .onErrorResume(SubscriptionErrorException.class, exception -> {
        logSubscriptionErrors(exception);
        return Flux.empty();
    });
```

Ở đây `Flux.empty()` khiến stream hoàn tất bình thường sau khi ghi log. Chỉ dùng nếu UI hoặc tầng gọi đã có cách phân biệt trạng thái stream kết thúc do lỗi và kết thúc bình thường, ví dụ một state/metric riêng. Nếu không, lỗi server sẽ bị che khuất và client có thể hiểu nhầm rằng không còn event mới.

Nếu không thể phục hồi hoặc không có fallback an toàn, hãy truyền exception tiếp:

```java
.onErrorResume(SubscriptionErrorException.class, exception -> {
    logSubscriptionErrors(exception);
    return Flux.error(exception);
})
```

Không dùng `onErrorContinue` như một cách tổng quát để giữ subscription sống sau lỗi terminal. Khi protocol đã kết thúc operation, client cần đăng ký một operation mới nếu muốn tiếp tục.

## 12. Retry khi mất kết nối

Spring for GraphQL mô tả rằng khi kết nối WebSocket bị đóng hoặc mất, `Flux` có thể kết thúc bằng `WebSocketDisconnectedException`. Có thể dùng Reactor `retry` để kết nối lại và khởi động subscription mới.

Ví dụ chỉ retry lỗi disconnect với số lần giới hạn:

```java
Flux<OrderEvent> events = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .retryWhen(Retry.backoff(3, Duration.ofSeconds(1))
        .filter(WebSocketDisconnectedException.class::isInstance));
```

Ví dụ này không retry `SubscriptionErrorException`. Nếu server chủ động gửi GraphQL error, ứng dụng nên đọc error code và quyết định rõ lỗi đó có thể khắc phục bằng cách đăng ký lại hay không.

Retry subscription có thể tạo khoảng trống hoặc event trùng lặp:

- Event phát ra sau lần cuối client xử lý nhưng trước khi kết nối mất có thể không được client nhận.
- Khi đăng ký lại, server có thể phát lại event cũ nếu nguồn hỗ trợ replay.
- Nếu nguồn chỉ phát live event, client có thể bỏ lỡ event trong thời gian reconnect.

Nếu nghiệp vụ cần không mất event, subscription nên có event ID, cursor, offset hoặc resume token. Client lưu vị trí đã xử lý và gửi lại vị trí đó khi đăng ký lại. Retry chỉ khôi phục kết nối; nó không tự cung cấp exactly-once delivery hoặc resume semantics.

## 13. Cancellation không phải là lỗi

Client có thể chủ động hủy `Flux` để kết thúc subscription. Đây là cancellation, không phải `SubscriptionErrorException`.

Ví dụ chỉ nhận 10 event:

```java
Flux<OrderEvent> firstTen = client.document(subscriptionDocument)
    .retrieveSubscription("orderStatusChanged")
    .toEntity(OrderEvent.class)
    .take(10);
```

Sau phần tử thứ mười, `take(10)` hủy upstream. Với GraphQL over WebSocket, transport gửi thông điệp `complete` để server kết thúc operation. Cũng có thể hủy qua `Subscription` trong `Subscriber` hoặc các operator có khả năng cancellation.

Không ghi cancellation như lỗi hệ thống và không tự reconnect khi người dùng đã chủ động rời màn hình hoặc bỏ theo dõi.

## 14. Phân biệt lỗi phía client và resolver phía server

`SubscriptionErrorException` là exception mà GraphQL client nhìn thấy. Ở server, nguồn gốc có thể là publisher của `@SubscriptionMapping` phát `onError`.

`DataFetcherExceptionResolver` xử lý exception từ quá trình gọi data fetcher ban đầu, nhưng không xử lý được lỗi phát sinh sau đó từ publisher subscription. Spring for GraphQL cung cấp `SubscriptionExceptionResolver` để chuyển lỗi từ subscription publisher thành danh sách `GraphQLError` gửi qua transport.

Luồng tổng quát:

```text
Server @SubscriptionMapping
          |
          v
     Flux<Event>
          |
          | onError(exception)
          v
SubscriptionExceptionResolver
          |
          | List<GraphQLError>
          v
WebSocket transport sends error message
          |
          v
GraphQlClient receives terminal error
          |
          v
SubscriptionErrorException
          |
          v
client reads getErrors()
```

Ví dụ đăng ký adapter để ánh xạ exception publisher thành một GraphQL error:

```java
@Bean
SubscriptionExceptionResolver subscriptionExceptionResolver() {
    return SubscriptionExceptionResolverAdapter.forSingleError(exception ->
        GraphqlErrorBuilder.newError()
            .message("Order event stream is temporarily unavailable")
            .extensions(Map.of("code", "ORDER_STREAM_UNAVAILABLE"))
            .build()
    );
}
```

Resolver này chạy ở server. Khi GraphQL error được gửi trong terminal WebSocket error message, client có thể nhận `SubscriptionErrorException` và đọc `ORDER_STREAM_UNAVAILABLE` từ `getErrors()`.

Trong ứng dụng Spring Boot dùng GraphQL starter, Boot phát hiện các bean `SubscriptionExceptionResolver` và thêm chúng vào `GraphQlSource` để xử lý lỗi publisher. Nếu tự tạo `GraphQlSource`, đăng ký resolver qua `GraphQlSource.Builder.subscriptionExceptionResolvers(...)`.

Không nhầm `SubscriptionExceptionResolver` với `SubscriptionErrorException`: một bên là contract xử lý lỗi ở server, bên còn lại là exception ở client.

## 15. Kiểm thử bằng `StepVerifier`

Vì subscription trả về `Flux`, `StepVerifier` phù hợp để xác minh cả event bình thường và terminal error.

Ví dụ kiểm tra luồng kết thúc bằng `SubscriptionErrorException`:

```java
StepVerifier.create(subscriptionEvents)
    .expectNextMatches(event -> event.orderId().equals("order-01"))
    .expectErrorSatisfies(error -> {
        assertThat(error).isInstanceOf(SubscriptionErrorException.class);

        SubscriptionErrorException exception =
            (SubscriptionErrorException) error;

        assertThat(exception.getErrors())
            .anySatisfy(graphQlError ->
                assertThat(graphQlError.getExtensions())
                    .containsEntry("code", "ORDER_STREAM_UNAVAILABLE")
            );
    })
    .verify();
```

Đây là ví dụ kiểm thử integration; `subscriptionEvents` cần được tạo từ `WebSocketGraphQlClient` trỏ tới server test có `SubscriptionExceptionResolver` và publisher phát event rồi lỗi. Cần bảo đảm subscription đã được đăng ký trước khi test phát event để tránh race condition.

Nên kiểm thử riêng:

- Publisher hoàn tất bình thường: `Flux` hoàn tất, không có exception.
- Server gửi terminal `error`: client nhận `SubscriptionErrorException` và đọc được error code.
- WebSocket bị đóng giữa chừng: client nhận `WebSocketDisconnectedException`.
- Field trong một `next` response có lỗi: `executeSubscription()` vẫn cho phép kiểm tra response và field errors.
- `retrieveSubscription` gặp field error: kiểm tra `FieldAccessException` cùng response/field.
- Client hủy subscription: upstream được cancel và không phát sinh lỗi giả.
- Retry chỉ áp dụng với nhóm lỗi được phép, không retry mọi `GraphQlTransportException`.

## 16. Lưu ý khi xử lý và ghi log

`SubscriptionErrorException` chứa error message và extensions từ server. Đây là dữ liệu có thể đến từ hệ thống bên ngoài hoặc từ resolver, vì vậy cần xử lý như dữ liệu đầu vào:

1. Ưu tiên `extensions.code` ổn định để phân loại; không dựa vào message tự do.
2. Không trả nguyên văn thông tin nội bộ hoặc stack trace cho người dùng cuối.
3. Không ghi token, variables nhạy cảm hoặc toàn bộ GraphQL request vào log.
4. Gắn correlation ID hoặc operation identifier an toàn để đối chiếu log client/server.
5. Đếm metrics theo error code và transport để phát hiện lỗi tăng bất thường.
6. Giới hạn số lần retry và dùng backoff để tránh tạo tải lớn khi server đang gặp sự cố.
7. Phân biệt lỗi terminal từ server với lỗi mạng và cancellation chủ động.

## 17. Những lỗi thường gặp

**Bắt `SubscriptionErrorException` như thể nó là lỗi mất kết nối.** Exception này chứa GraphQL errors từ thông điệp kết thúc subscription. Đọc `getErrors()` trước khi quyết định retry.

**Cho rằng mọi field error đều tạo `SubscriptionErrorException`.** Field error trong một response `next` có thể chỉ ảnh hưởng event đó. Dùng `executeSubscription()` để đọc từng `ClientGraphQlResponse` hoặc xử lý `FieldAccessException` từ shortcut.

**Chỉ đọc `getMessage()` và bỏ qua `getErrors()`.** Mã lỗi, path, locations và extensions nằm trong `ResponseError`; đây là dữ liệu quan trọng để phân loại.

**Retry vô điều kiện.** Retry lỗi nghiệp vụ terminal có thể tạo vòng lặp đăng ký/hủy liên tục. Chỉ retry nhóm lỗi được xác định là tạm thời.

**Nuốt lỗi bằng `Flux.empty()`.** Stream kết thúc trông như thành công và tầng UI có thể không biết subscription đã thất bại. Chỉ dùng fallback nếu có trạng thái riêng thể hiện kết thúc do lỗi.

**Giả định retry sẽ không mất hoặc lặp event.** Kết nối lại có thể tạo khoảng trống hoặc event trùng. Dùng cursor/offset nếu nghiệp vụ cần replay.

**Nhầm cancellation với error.** Client chủ động hủy subscription là hành vi bình thường, không phải sự cố cần retry.

**Dùng `DataFetcherExceptionResolver` cho lỗi phát ra sau khi publisher bắt đầu.** Lỗi subscription publisher cần `SubscriptionExceptionResolver` ở server.

## Kết luận

`SubscriptionErrorException` là exception phía Spring GraphQL Client khi subscription kết thúc bằng thông điệp GraphQL `error` từ server. Nó mở rộng `GraphQlTransportException`, cung cấp `getErrors()` để đọc `ResponseError` và `getRequest()` để liên hệ với request gốc. Hãy phân biệt nó với `FieldAccessException` từ một field trong event response, `WebSocketDisconnectedException` do mất kết nối và cancellation chủ động. Dùng `retrieveSubscription` cho trường hợp đơn giản, `executeSubscription` khi cần kiểm tra từng response, `doOnError` để quan sát, `onErrorResume` khi có fallback rõ ràng và retry có điều kiện cho lỗi kết nối tạm thời. Ở server, dùng `SubscriptionExceptionResolver` để ánh xạ lỗi publisher thành GraphQL errors mà client có thể đọc qua exception này.

## Tài liệu tham khảo

- [Spring for GraphQL — Client: Subscription Requests](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL API — `SubscriptionErrorException`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Spring for GraphQL API — `ResponseError`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/ResponseError.html)
- [Spring for GraphQL API — `FieldAccessException`](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/FieldAccessException.html)
- [Spring for GraphQL — Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
