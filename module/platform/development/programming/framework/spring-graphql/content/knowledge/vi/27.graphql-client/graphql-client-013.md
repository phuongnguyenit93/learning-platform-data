# GraphQlTransportException

## 1. `GraphQlTransportException` là gì?

Spring for GraphQL cung cấp `GraphQlClient` để gửi GraphQL operation qua HTTP, WebSocket hoặc RSocket. Client tạo request, chuyển request qua transport, nhận response rồi giải mã dữ liệu theo field path hoặc Java type.

Trong quá trình đó, lỗi có thể xuất hiện trước khi server trả về một GraphQL response hợp lệ. Ví dụ kết nối bị từ chối, DNS không phân giải được, timeout, WebSocket bị đóng, lỗi đọc/ghi dữ liệu hoặc lỗi encode request/decode response. Spring for GraphQL dùng `GraphQlTransportException` để biểu diễn lỗi phát sinh từ transport hoặc bọc exception do một implementation của transport ném ra.

Class nằm trong package:

```java
import org.springframework.graphql.client.GraphQlTransportException;
```

`GraphQlTransportException` là unchecked exception và kế thừa `GraphQlClientException`. Nó giữ request đã thất bại thông qua `getRequest()` và giữ nguyên exception gốc trong `cause` nếu transport cung cấp.

## 2. Phân biệt lỗi transport và lỗi GraphQL response

Không phải mọi lỗi được trả về từ GraphQL server đều là `GraphQlTransportException`. Cần phân biệt lỗi ở tầng giao tiếp với lỗi được biểu diễn trong GraphQL response:

| Loại lỗi | Ví dụ | Cách client thường nhận |
| --- | --- | --- |
| Transport failure | DNS, connection refused, timeout, socket đóng, lỗi I/O | `GraphQlTransportException` hoặc subclass |
| Lỗi encode/decode ở transport | Không serialize được request hoặc không decode được response/protocol message | Transport có thể kết thúc bằng exception và bọc thành `GraphQlTransportException` |
| GraphQL execution error | Resolver ném exception hoặc validation/authorization được trả về trong GraphQL response | `ClientGraphQlResponse` chứa `errors`, có thể vẫn có `data` một phần |
| Field access error | Field path không tồn tại hoặc field null kèm error khi dùng `retrieve(...)` | `FieldAccessException` |
| Decode sai Java type | Response field tồn tại nhưng không chuyển được sang kiểu Java đích | `GraphQlClientException` |

Ví dụ server trả response hợp lệ nhưng có lỗi ở một field:

```json
{
  "data": {
    "book": {
      "id": "book-42",
      "title": null
    }
  },
  "errors": [
    {
      "message": "Không thể tải tiêu đề sách",
      "path": ["book", "title"]
    }
  ]
}
```

Đây vẫn là một GraphQL response. Transport đã hoàn thành việc gửi và nhận dữ liệu; lỗi nằm trong kết quả thực thi GraphQL. Client có thể dùng `execute()` để kiểm tra `isValid()`, `getErrors()` và dữ liệu trả về.

Ngược lại, nếu server không thể kết nối hoặc WebSocket bị ngắt trước khi response đến, client không có GraphQL response để phân tích. Khi đó, lỗi được phát dưới dạng transport exception.

## 3. Vị trí trong hệ thống exception của GraphQL client

Hệ thống exception chính có cấu trúc:

```text
GraphQlClientException
├── FieldAccessException
└── GraphQlTransportException
    ├── SubscriptionErrorException
    └── WebSocketDisconnectedException
```

Ý nghĩa:

- `GraphQlClientException`: lớp cơ sở cho lỗi phát sinh từ `GraphQlClient`.
- `FieldAccessException`: lỗi khi truy cập hoặc giải mã một field từ response không hợp lệ, field null hoặc field có lỗi.
- `GraphQlTransportException`: lỗi từ transport hoặc exception được bọc từ transport implementation.
- `SubscriptionErrorException`: Subscription kết thúc do server gửi WebSocket message loại `error`.
- `WebSocketDisconnectedException`: WebSocket connection bị đóng hoặc mất khi request/Subscription đang chạy.

Vì hai exception chuyên biệt của WebSocket kế thừa `GraphQlTransportException`, có thể bắt lớp cha để xử lý chung. Nếu cần chính sách khác nhau cho lỗi Subscription và lỗi mất kết nối, hãy bắt subclass cụ thể trước.

## 4. Các constructor và dữ liệu có thể đọc

`GraphQlTransportException` có hai constructor:

```java
public GraphQlTransportException(Throwable cause, GraphQlRequest request)

public GraphQlTransportException(
    String message,
    Throwable cause,
    GraphQlRequest request)
```

Constructor thứ nhất tạo message mặc định. Constructor thứ hai cho phép đặt message riêng. Cả hai nhận:

- `cause`: exception gốc từ transport, có thể null.
- `request`: GraphQL request đã thất bại ở tầng transport.

Các phương thức quan trọng:

| Phương thức | Nguồn | Mục đích |
| --- | --- | --- |
| `getRequest()` | Kế thừa từ `GraphQlClientException` | Lấy request gây lỗi |
| `getCause()` | `Throwable` | Lấy exception được bọc trực tiếp |
| `getRootCause()` | `NestedRuntimeException` | Lấy nguyên nhân gốc sâu nhất nếu có |
| `getMostSpecificCause()` | `NestedRuntimeException` | Lấy cause cụ thể nhất; nếu không có cause thì trả về chính exception |
| `getMessage()` | `Throwable` | Đọc message phục vụ chẩn đoán |

`GraphQlTransportException` không cung cấp một `getStatusCode()` chung. HTTP status, WebSocket close status hoặc thông tin riêng của transport phải được đọc từ subclass, cause hoặc API transport tương ứng.

`getRequest()` trả về `GraphQlRequest`, có thể dùng để xác định document, operation name, variables và extensions. Cần cẩn thận khi log request vì variables có thể chứa access token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm.

## 5. Những tình huống thường tạo transport exception

Tùy transport, lỗi có thể xuất hiện ở các giai đoạn khác nhau:

**HTTP:**

- Không phân giải được hostname hoặc không thiết lập được TCP connection.
- TLS handshake thất bại hoặc certificate không hợp lệ.
- Request timeout hoặc connection bị reset.
- Lỗi khi ghi request body hoặc đọc response body.
- Response không thể giải mã theo codec được cấu hình.

**WebSocket:**

- Không thể mở WebSocket connection.
- Connection bị đóng khi operation đang chạy.
- Protocol/session initialization thất bại.
- Server hoặc proxy ngắt connection.

**RSocket:**

- Không thể thiết lập hoặc duy trì session.
- Connection bị mất khi request đang thực thi.
- Lỗi ở tầng request/response hoặc streaming interaction.

`GraphQlTransportException` là abstraction chung. Exception cụ thể và cause phụ thuộc vào transport implementation, chẳng hạn WebClient, RestClient, WebSocket client hoặc RSocket requester. Không nên chỉ dựa vào message để xác định nguyên nhân; hãy kiểm tra cause và loại transport đang dùng.

## 6. Xử lý transport exception với `HttpGraphQlClient`

`HttpGraphQlClient` dùng Spring `WebClient` và thực thi theo mô hình non-blocking. Các thao tác trả về `Mono` nên có thể xử lý transport exception bằng Reactor operators.

Tạo client:

```java
import org.springframework.graphql.client.HttpGraphQlClient;
import org.springframework.web.reactive.function.client.WebClient;

WebClient webClient = WebClient.builder()
    .baseUrl("https://api.example.com/graphql")
    .build();

HttpGraphQlClient graphQlClient = HttpGraphQlClient.builder(webClient)
    .build();
```

Thực hiện query và ghi nhận lỗi transport:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

Mono<Book> book = graphQlClient.document("""
        query BookById($id: ID!) {
            book(id: $id) {
                id
                title
            }
        }
        """)
    .variable("id", "book-42")
    .retrieve("book")
    .toEntity(Book.class)
    .doOnError(GraphQlTransportException.class, exception -> {
        log.warn("GraphQL transport failed", exception);
    });
```

`doOnError` chỉ quan sát lỗi và không phục hồi luồng. Nếu muốn chuyển lỗi sang exception của application hoặc trả fallback, dùng `onErrorMap` hoặc `onErrorResume` theo hợp đồng của service.

Ví dụ chuyển lỗi transport thành lỗi nghiệp vụ ở tầng tích hợp:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

return graphQlClient.document(document)
    .retrieve("book")
    .toEntity(Book.class)
    .onErrorMap(
        GraphQlTransportException.class,
        exception -> new CatalogUnavailableException(
            "Catalog service is unavailable", exception)
    );
```

Không chuyển mọi exception của `GraphQlClient` thành lỗi transport. `FieldAccessException` hoặc lỗi decode có cách xử lý khác và có thể chỉ ảnh hưởng một field trong response.

## 7. Xử lý với `HttpSyncGraphQlClient`

`HttpSyncGraphQlClient` dùng Spring `RestClient` và có execution chain blocking. Trong trường hợp này, exception được ném trực tiếp khi gọi `executeSync()` hoặc `retrieveSync(...)`.

```java
import org.springframework.graphql.GraphQlRequest;
import org.springframework.graphql.client.GraphQlTransportException;
import org.springframework.graphql.client.HttpSyncGraphQlClient;
import org.springframework.web.client.RestClient;

RestClient restClient = RestClient.create("https://api.example.com/graphql");
HttpSyncGraphQlClient graphQlClient = HttpSyncGraphQlClient.create(restClient);
```

Phương thức service có thể bắt lỗi như sau:

```java
public Book findBook(String id) {
try {
    Book book = graphQlClient.document("""
            query BookById($id: ID!) {
                book(id: $id) {
                    id
                    title
                }
            }
            """)
        .variable("id", id)
        .retrieveSync("book")
        .toEntity(Book.class);

    return book;
}
catch (GraphQlTransportException exception) {
    GraphQlRequest failedRequest = exception.getRequest();
    Throwable rootCause = exception.getMostSpecificCause();

    log.error("Cannot reach GraphQL service for operation {}",
        failedRequest.getOperationName(), rootCause);
    throw new CatalogUnavailableException(
        "Catalog service is unavailable", exception);
}
}
```

Với client blocking, dùng `try/catch` là cách xử lý tự nhiên. Không cần chuyển toàn bộ lời gọi sang Reactor chỉ để bắt exception.

## 8. `SubscriptionErrorException`: server kết thúc Subscription bằng lỗi

`SubscriptionErrorException` là subclass của `GraphQlTransportException`. Nó được tạo khi WebSocket Subscription nhận message `error` từ server. Danh sách lỗi GraphQL trong message được cung cấp qua `getErrors()`.

Ví dụ xử lý:

```java
import org.springframework.graphql.client.SubscriptionErrorException;
import reactor.core.publisher.Flux;

Flux<Book> events = graphQlClient.document("""
        subscription BookAdded {
            bookAdded {
                id
                title
            }
        }
        """)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .doOnError(SubscriptionErrorException.class, exception -> {
        exception.getErrors().forEach(error ->
            log.warn("Subscription error: {}", error.getMessage())
        );
    });
```

Đây là lỗi mà server chủ động gửi theo protocol để kết thúc operation. Nguyên nhân có thể là operation không hợp lệ, không đủ quyền, lỗi nghiệp vụ hoặc lỗi subscription resolver. Không nên tự động retry tất cả `SubscriptionErrorException`; hãy đọc `getErrors()` để quyết định có thể thử lại hay cần sửa request/quyền truy cập.

## 9. `WebSocketDisconnectedException`: connection bị mất

`WebSocketDisconnectedException` là subclass khác của `GraphQlTransportException`. Nó được phát khi WebSocket connection đóng hoặc mất trong lúc request hay Subscription đang chạy.

Ngoài `getRequest()` kế thừa, exception này có:

```java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import org.springframework.web.socket.CloseStatus;

try {
    // Thực hiện request qua WebSocketGraphQlClient.
}
catch (WebSocketDisconnectedException exception) {
    CloseStatus closeStatus = exception.getCloseStatus();
    log.warn("WebSocket closed: {}", closeStatus);
}
```

`getCloseStatus()` trả về `CloseStatus` dùng để đóng WebSocket session. Thông tin này hữu ích khi phân biệt đóng bình thường, đóng do server/proxy hoặc lỗi giao thức.

Ví dụ:

```java
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;

Flux<Book> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .doOnError(WebSocketDisconnectedException.class, exception -> {
        log.warn(
            "GraphQL WebSocket disconnected: {}",
            exception.getCloseStatus()
        );
    });
```

Khi connection mất, các request hoặc Subscription đang chạy trên connection đó có thể kết thúc bằng lỗi. `WebSocketGraphQlClient` có thể thiết lập lại connection cho request tiếp theo; điều đó không có nghĩa operation đang chạy được tiếp tục từ đúng event đã nhận cuối cùng.

## 10. Phân biệt `FieldAccessException` và `GraphQlTransportException`

Hai exception đều kế thừa `GraphQlClientException`, nhưng nguyên nhân khác nhau:

```text
GraphQlClientException
├── FieldAccessException       // đọc field từ response thất bại
└── GraphQlTransportException  // giao tiếp với transport thất bại
```

Ví dụ `retrieve("book")` có thể phát `FieldAccessException` khi:

- Đường dẫn `book` không tồn tại trong response.
- Giá trị `book` là null và field có GraphQL errors.
- Response không hợp lệ cho thao tác decode được yêu cầu.

`FieldAccessException` cung cấp `getResponse()` và `getField()` để đọc response cùng field gây lỗi. Nếu field có tồn tại nhưng không thể decode sang Java type đích, client có thể ném `GraphQlClientException` thông thường.

Ví dụ xử lý field access riêng:

```java
import org.springframework.graphql.client.ClientResponseField;
import org.springframework.graphql.client.FieldAccessException;
import reactor.core.publisher.Mono;

return graphQlClient.document(document)
    .retrieve("book")
    .toEntity(Book.class)
    .onErrorResume(FieldAccessException.class, exception -> {
        ClientResponseField field = exception.getField();
        log.warn("Cannot access GraphQL field: {}", field);
        return Mono.empty();
    });
```

Không dùng `onErrorResume(GraphQlClientException.class, ...)` để trả fallback chung cho mọi trường hợp nếu chưa phân loại lỗi. Làm như vậy có thể che giấu lỗi kết nối, lỗi dữ liệu và lỗi decode dưới cùng một kết quả rỗng.

## 11. Khi cần xem toàn bộ response, dùng `execute()`

`retrieve(path)` là shortcut để truy cập một field và decode sang Java type. Nếu cần phân biệt response không có data, lỗi ở một field hoặc giá trị null hợp lệ, hãy dùng `execute()`.

```java
import java.util.Optional;
import org.springframework.graphql.client.ClientResponseField;
import reactor.core.publisher.Mono;

Mono<Optional<Book>> book = graphQlClient.document(document)
    .variable("id", "book-42")
    .execute()
    .map(response -> {
        if (!response.isValid()) {
            log.warn("GraphQL returned errors: {}", response.getErrors());
        }

        ClientResponseField field = response.field("book");
        Book value = field.toEntity(Book.class);
        return Optional.ofNullable(value);
    });
```

`toEntity` trả về `null` nếu field null nhưng không có lỗi; nếu field null trong response không hợp lệ hoặc có field errors, nó ném `FieldAccessException`. `Mono` không được phát giá trị `null`, vì vậy dùng `Optional` hoặc result type riêng để biểu diễn trường hợp không có dữ liệu.

Lỗi trong `response.getErrors()` không tự động có nghĩa transport thất bại. Response vẫn có thể chứa `data` một phần và cần được xử lý theo nghiệp vụ.

## 12. Retry: khi nào nên thử lại?

Không phải transport exception nào cũng có thể retry an toàn. Cần xem nguyên nhân, loại operation và khả năng idempotent của request.

| Trường hợp | Retry? | Lý do |
| --- | --- | --- |
| Query gặp lỗi kết nối tạm thời | Có thể | Query thường không tạo side effect, nhưng cần giới hạn số lần và thời gian |
| Query timeout | Có điều kiện | Server có thể vẫn đang xử lý; retry có thể tạo tải trùng |
| Mutation bị mất kết nối sau khi gửi | Không tự động | Server có thể đã commit mutation nhưng response bị mất |
| `SubscriptionErrorException` do validation/authorization | Thường không | Gửi lại cùng operation không sửa được nguyên nhân |
| `WebSocketDisconnectedException` | Có thể resubscribe | Connection có thể khôi phục, nhưng có nguy cơ mất event trong khoảng gián đoạn |
| Lỗi decode do kiểu Java sai | Không | Cần sửa DTO hoặc response mapping |

Với operation có side effect, hãy dùng idempotency key hoặc cơ chế deduplication ở server trước khi bật retry. Nếu không, client có thể tạo trùng đơn hàng, thanh toán hoặc mutation khác.

## 13. Retry Subscription sau khi WebSocket mất kết nối

Spring for GraphQL cho phép dùng Reactor `retry` để bắt đầu lại Subscription sau khi transport bị ngắt. Ví dụ giới hạn ba lần retry với exponential backoff:

```java
import java.time.Duration;
import org.springframework.graphql.client.WebSocketDisconnectedException;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

Flux<Book> events = graphQlClient.document(subscriptionDocument)
    .retrieveSubscription("bookAdded")
    .toEntity(Book.class)
    .retryWhen(
        Retry.backoff(3, Duration.ofSeconds(1))
            .filter(WebSocketDisconnectedException.class::isInstance)
    );
```

Khi retry, client đăng ký lại operation. Đây là một Subscription mới; không đảm bảo server phát lại những event đã xảy ra trong thời gian connection bị mất. Nếu nghiệp vụ không được phép mất event, schema nên hỗ trợ cursor/sequence ID, `after` hoặc `lastEventId`, và server cần có event store hoặc broker có khả năng replay.

Không đặt retry vô hạn mà không có backoff, giới hạn hoặc cơ chế dừng. Một server đang gặp sự cố có thể bị quá tải thêm nếu hàng nghìn client liên tục reconnect.

## 14. Xử lý lỗi theo transport trong service layer

Service tích hợp nên chuyển exception kỹ thuật thành hợp đồng lỗi phù hợp với phần còn lại của ứng dụng, nhưng vẫn giữ nguyên cause để phục vụ chẩn đoán.

Ví dụ:

```java
import org.springframework.graphql.client.GraphQlTransportException;
import reactor.core.publisher.Mono;

public Mono<Book> loadBook(String id) {
    return graphQlClient.documentName("bookById")
        .variable("id", id)
        .retrieve("book")
        .toEntity(Book.class)
        .onErrorMap(
            GraphQlTransportException.class,
            exception -> new RemoteCatalogException(
                "Catalog transport failed", exception)
        );
}
```

Controller hoặc API layer có thể chuyển `RemoteCatalogException` thành lỗi nghiệp vụ của ứng dụng. Không trả nguyên stack trace, host nội bộ, query variables hoặc thông tin xác thực cho client cuối.

Nếu cần fallback, hãy xác định rõ giá trị fallback có đúng về nghiệp vụ hay không. Ví dụ danh sách recommendation có thể cho phép fallback rỗng; thông tin tồn kho hoặc kết quả thanh toán thường không nên giả vờ là rỗng khi hệ thống nguồn không truy cập được.

## 15. Logging và observability

Khi ghi log transport exception, nên giữ đủ thông tin để chẩn đoán nhưng không làm lộ dữ liệu request.

Nên ghi nhận:

- Tên service đích hoặc transport đã cấu hình.
- Operation name hoặc persisted operation ID.
- Loại exception cụ thể.
- Root cause class và message đã được lọc.
- Thời điểm, thời lượng và số lần retry.
- WebSocket close status nếu là `WebSocketDisconnectedException`.
- Error code/path từ `SubscriptionErrorException.getErrors()` nếu phù hợp.

Tránh log toàn bộ `GraphQlRequest`, variables hoặc authorization headers. Nếu cần liên kết request, dùng correlation ID hoặc trace ID thay vì in toàn bộ payload.

Các metric hữu ích gồm số transport failures theo loại, timeout rate, số lần reconnect, số Subscription bị kết thúc và số retry đã dùng. Không gắn raw query hoặc user ID nhạy cảm làm metric tag vì có thể tạo cardinality rất lớn và lộ thông tin.

## 16. Kiểm thử xử lý `GraphQlTransportException`

Nên kiểm thử riêng ba lớp hành vi:

1. **Phân loại lỗi:** transport failure được nhận diện là `GraphQlTransportException`; field failure được nhận diện là `FieldAccessException`.
2. **Chính sách phục hồi:** query retry theo giới hạn; mutation không bị retry ngoài ý muốn; Subscription chỉ retry loại lỗi được cho phép.
3. **Thông tin chẩn đoán:** request được giữ trong exception, cause không bị mất và close status/errors của subclass được đọc đúng.

Với unit test cho service, có thể mock transport hoặc `GraphQlClient` để trả `Mono.error(...)`/`Flux.error(...)`, rồi dùng Reactor `StepVerifier` xác nhận exception được chuyển đổi hoặc retry đúng số lần.

Với integration test, dùng HTTP test server hoặc WebSocket test server để tạo các tình huống:

- Server không lắng nghe hoặc đóng connection.
- Server trì hoãn response quá timeout của client.
- Response body không đúng định dạng.
- WebSocket đóng khi Subscription đang hoạt động.
- Server gửi message `error` cho Subscription.
- Server gửi response hợp lệ nhưng có GraphQL `errors` và partial `data`.

Hai ca cuối đặc biệt quan trọng: message `error` của Subscription tạo `SubscriptionErrorException`, trong khi response GraphQL thông thường có `errors` vẫn có thể được đọc qua `ClientGraphQlResponse`.

## 17. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bắt `GraphQlTransportException` nhưng không chạy | Lỗi thực tế là `FieldAccessException` hoặc response chứa GraphQL errors | Kiểm tra response và exception hierarchy |
| Query có `errors` nhưng không có transport exception | Server trả GraphQL response hợp lệ có lỗi thực thi | Dùng `execute()` và kiểm tra `getErrors()` |
| Không biết request nào thất bại | Chưa đọc `getRequest()` | Ghi operation name/ID an toàn từ request |
| Không thấy nguyên nhân gốc | Chỉ log message của exception cha | Kiểm tra `getCause()` hoặc `getMostSpecificCause()` |
| Mất thông tin HTTP status | Chỉ kiểm tra `GraphQlTransportException` | Kiểm tra cause cụ thể từ HTTP transport |
| Subscription dừng nhưng không reconnect | Flux kết thúc bằng `WebSocketDisconnectedException` | Dùng retry có backoff nếu nghiệp vụ cho phép |
| Subscription bị mất event sau retry | Client tạo operation mới, server không replay event cũ | Dùng cursor/sequence và event store hoặc broker replay |
| Mutation bị thực hiện hai lần | Retry sau timeout dù server đã commit lần đầu | Dùng idempotency key hoặc deduplication |
| Retry liên tục làm server quá tải | Không có giới hạn hoặc backoff | Dùng retry có giới hạn, backoff và jitter |
| Fallback che giấu lỗi hệ thống | Mọi transport error bị đổi thành dữ liệu rỗng | Chỉ fallback khi nghiệp vụ cho phép và ghi nhận degraded state |

## 18. Checklist xử lý transport exception

- [ ] Phân biệt transport failure với GraphQL response errors.
- [ ] Hiểu `GraphQlTransportException` kế thừa `GraphQlClientException`.
- [ ] Nhận biết `FieldAccessException` là nhánh exception riêng.
- [ ] Đọc `getRequest()` để xác định request gây lỗi.
- [ ] Giữ nguyên `cause` và dùng `getMostSpecificCause()` khi chẩn đoán.
- [ ] Bắt `SubscriptionErrorException` riêng khi cần đọc GraphQL errors.
- [ ] Bắt `WebSocketDisconnectedException` riêng khi cần đọc close status.
- [ ] Dùng `execute()` khi cần phân tích response có partial data và errors.
- [ ] Không retry mọi transport exception một cách mù quáng.
- [ ] Không retry Mutation nếu chưa bảo đảm idempotency.
- [ ] Retry Subscription có giới hạn, backoff và chiến lược replay event.
- [ ] Không log token, variables nhạy cảm hoặc toàn bộ request.
- [ ] Kiểm thử lỗi kết nối, timeout, lỗi protocol, Subscription error và partial GraphQL response.

## Kết luận

`GraphQlTransportException` là exception phía client dùng cho lỗi do `GraphQlTransport` phát sinh hoặc exception được bọc từ transport implementation. Nó kế thừa `GraphQlClientException`, giữ request qua `getRequest()` và giữ nguyên cause để chẩn đoán. Hai subclass quan trọng là `SubscriptionErrorException` cho WebSocket Subscription kết thúc bằng message `error`, và `WebSocketDisconnectedException` khi connection mất trong lúc request đang chạy.

Không nhầm transport exception với lỗi GraphQL nằm trong response hoặc lỗi truy cập field. Với Query/Mutation, dùng `execute()` khi cần đọc partial data và `errors`; với `retrieve()` hãy xử lý riêng `FieldAccessException`. Với Subscription, phân biệt lỗi server gửi với lỗi connection bị ngắt. Retry chỉ an toàn khi nguyên nhân có thể phục hồi và operation có tính idempotent; đặc biệt, resubscribe có thể làm mất event nếu server không hỗ trợ replay. Giữ cause, ghi log đã lọc dữ liệu nhạy cảm và kiểm thử từng loại lỗi để client phục hồi đúng cách.

## Tài liệu tham khảo

- [Spring for GraphQL — Client](https://docs.spring.io/spring-graphql/reference/client.html)
- [Spring for GraphQL — `GraphQlTransportException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransportException.html)
- [Spring for GraphQL — `GraphQlClientException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlClientException.html)
- [Spring for GraphQL — `FieldAccessException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/FieldAccessException.html)
- [Spring for GraphQL — `SubscriptionErrorException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/SubscriptionErrorException.html)
- [Spring for GraphQL — `WebSocketDisconnectedException` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/WebSocketDisconnectedException.html)
- [Spring for GraphQL — `GraphQlTransport` API](https://docs.spring.io/spring-graphql/docs/current/api/org/springframework/graphql/client/GraphQlTransport.html)
