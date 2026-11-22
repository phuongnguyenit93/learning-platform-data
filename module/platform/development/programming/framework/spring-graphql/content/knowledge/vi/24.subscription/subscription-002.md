# @SubscriptionMapping trong Spring for GraphQL

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích subscription khác query và mutation ở cách trả kết quả.
- Khai báo subscription field trong GraphQL SDL.
- Dùng `@SubscriptionMapping` để ánh xạ field gốc của type `Subscription`.
- Trả về `Publisher<T>` hoặc `Flux<T>` làm nguồn phát event.
- Hiểu cách GraphQL thực thi selection set cho từng event.
- Kết nối resolver với event source, phân biệt cold publisher và hot publisher.
- Lọc event theo argument và kiểm soát backpressure.
- Xử lý lỗi, cancellation và giải phóng tài nguyên khi subscriber ngắt kết nối.
- Áp dụng xác thực, authorization và giới hạn dữ liệu theo người đăng ký.
- Kiểm thử subscription bằng `GraphQlTester` và Reactor `StepVerifier`.

## 1. Subscription là gì?

GraphQL có ba loại operation chính:

- **Query** đọc dữ liệu tại thời điểm được gọi.
- **Mutation** thay đổi dữ liệu.
- **Subscription** đăng ký nhận các kết quả mới khi một sự kiện xảy ra.

Query thường trả về một response cho một lần thực thi. Subscription tạo một luồng kết quả: server giữ một publisher đang hoạt động và gửi một GraphQL response cho mỗi event mà publisher phát ra.

Ví dụ, client muốn theo dõi giá của một cuốn sách:

~~~graphql
subscription WatchBookPrice($bookId: ID!) {
    bookPriceChanged(bookId: $bookId) {
        bookId
        price
        changedAt
    }
}
~~~

Sau khi đăng ký thành công, client có thể nhận nhiều event:

~~~json
{
    "data": {
        "bookPriceChanged": {
            "bookId": "book-42",
            "price": 125000,
            "changedAt": "2026-11-20T10:15:00Z"
        }
    }
}
~~~

Một thời điểm sau, cùng subscription có thể nhận response mới với giá khác. Client không cần gửi lại query sau mỗi lần giá thay đổi.

Subscription phù hợp với dữ liệu cần cập nhật liên tục như trạng thái đơn hàng, tiến độ xử lý, thông báo, giá thị trường hoặc sự kiện cộng tác. Nó không thay thế query cho các thao tác đọc thông thường.

## 2. Khai báo subscription trong GraphQL SDL

Subscription field được khai báo trong root type `Subscription`.

~~~graphql
type BookPriceChanged {
    bookId: ID!
    price: Float!
    changedAt: String!
}

type Subscription {
    bookPriceChanged(bookId: ID!): BookPriceChanged!
}
~~~

Trong ví dụ:

- `bookPriceChanged` là field mà client đăng ký.
- `bookId` là argument dùng để lọc luồng event.
- `BookPriceChanged` là payload của mỗi event.
- `!` thể hiện các giá trị bắt buộc theo contract schema.

Một subscription operation chỉ có một root field. Các field được chọn bên trong root field xác định dữ liệu server trả về cho mỗi event.

Ví dụ hợp lệ:

~~~graphql
subscription {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
    }
}
~~~

Không thiết kế subscription operation với nhiều root field độc lập như một query thông thường. Nếu cần theo dõi nhiều loại sự kiện, hãy thiết kế một root event phù hợp hoặc tạo các subscription operation riêng.

## 3. @SubscriptionMapping ánh xạ field nào?

Trong annotated controller, `@SubscriptionMapping` dùng để ánh xạ method tới field của GraphQL root type `Subscription`.

Ví dụ:

~~~java
@Controller
class BookPriceSubscriptionController {

    private final BookPriceEventService eventService;

    BookPriceSubscriptionController(BookPriceEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookPriceChanged> bookPriceChanged(
            @Argument("bookId") String bookId) {

        return eventService.eventsForBook(bookId);
    }
}
~~~

Nếu tên method là `bookPriceChanged`, Spring ánh xạ method tới field cùng tên trong `Subscription`. `@SubscriptionMapping` là shortcut cho mapping trên root type `Subscription`; nó không phải mapping cho field con của payload.

Một số điểm cần nhớ:

- Method được gọi khi client bắt đầu subscription operation.
- `@Argument` đọc argument của root subscription field.
- Giá trị trả về là publisher phát các payload theo thời gian.
- Mỗi payload trở thành source value để GraphQL resolve selection set của event.
- Field con của payload vẫn có thể dùng `@SchemaMapping` nếu cần resolver riêng.

Không trả một object `BookPriceChanged` đơn lẻ nếu mục tiêu là duy trì luồng event. Hãy trả publisher như `Flux<BookPriceChanged>` hoặc kiểu `Publisher<BookPriceChanged>` tương thích.

## 4. Luồng thực thi của @SubscriptionMapping

Có thể hình dung vòng đời cơ bản:

~~~mermaid
flowchart TD
    A["Client gửi subscription operation"] --> B["WebSocket transport nhận operation"]
    B --> C["GraphQL thực thi root field Subscription"]
    C --> D["@SubscriptionMapping tạo Publisher"]
    D --> E["Publisher phát event"]
    E --> F["GraphQL resolve selection set cho event"]
    F --> G["Gửi GraphQL response cho client"]
    G --> H{"Còn event tiếp theo?"}
    H -->|Có| E
    H -->|Không| I["Publisher hoàn tất"]
    H -->|Client hủy| J["Hủy subscription và cleanup"]
~~~

Resolver không được gọi lại cho mỗi event để tạo một operation mới. Resolver tạo publisher cho subscription operation; publisher phát các event. Với mỗi event, GraphQL thực thi các field mà client đã chọn trên payload đó.

Ví dụ, nếu client chọn:

~~~graphql
subscription {
    bookPriceChanged(bookId: "book-42") {
        bookId
        price
        changedAt
    }
}
~~~

thì mỗi payload `BookPriceChanged` sẽ được GraphQL xử lý để tạo một response có ba field đã chọn.

Điều này cũng có nghĩa nested resolver và DataLoader có thể được gọi trong quá trình xử lý từng event. Hãy chú ý chi phí khi event phát thường xuyên hoặc selection set lớn.

## 5. Publisher và Flux là kiểu trả về chính

Spring for GraphQL hỗ trợ subscription resolver trả về reactive publisher. Trong ứng dụng Reactor, `Flux<T>` thường là lựa chọn thuận tiện:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

Ý nghĩa của các kiểu trả về:

| Kiểu trả về | Ý nghĩa với subscription |
| --- | --- |
| `Flux<T>` | Phát không, một hoặc nhiều event rồi có thể hoàn tất |
| `Publisher<T>` | Hợp đồng reactive tổng quát, không phụ thuộc trực tiếp Reactor |
| `Mono<T>` | Có thể phát tối đa một event rồi hoàn tất; phù hợp với trường hợp một lần phát duy nhất hơn là luồng dài |
| `T` hoặc `List<T>` | Giá trị đồng bộ, không biểu diễn một luồng event kéo dài |

Không gọi `block()` để chờ event trong subscription resolver. Làm vậy sẽ giữ thread và loại bỏ lợi ích của reactive stream.

Publisher phải tiếp tục phát event theo thời gian. Nếu nguồn dữ liệu chỉ có một giá trị và hoàn tất ngay, subscription cũng kết thúc sau một response.

## 6. Tạo event source bằng Reactor Sink

Để minh họa, có thể dùng `Sinks.Many` làm event source trong một ứng dụng chạy đơn instance.

Định nghĩa payload:

~~~java
public record BookPriceChanged(
        String bookId,
        double price,
        String changedAt) {
}
~~~

Event service:

~~~java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Service
class BookPriceEventService {

    private final Sinks.Many<BookPriceChanged> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookPriceChanged> eventsForBook(String bookId) {
        return sink.asFlux()
                .filter(event -> event.bookId().equals(bookId));
    }

    public Sinks.EmitResult publish(BookPriceChanged event) {
        return sink.tryEmitNext(event);
    }
}
~~~

Khi nghiệp vụ cập nhật giá thành công, service có thể phát event:

~~~java
import java.time.Instant;
import reactor.core.publisher.Sinks;

Sinks.EmitResult result = eventService.publish(
        new BookPriceChanged(
                "book-42",
                125000,
                Instant.now().toString()
        )
);

if (result.isFailure()) {
    // Ghi nhận hoặc retry theo chính sách của ứng dụng.
}
~~~

Ở code nghiệp vụ thực tế, cần kiểm tra `EmitResult` mà `publish` trả về. Nếu event không được phát, hãy áp dụng chính sách phù hợp như retry, ghi log hoặc lưu vào broker; đừng âm thầm bỏ qua kết quả.

Sink trong ví dụ là nguồn event trong bộ nhớ của một instance ứng dụng. Buffer được giới hạn ở 256 event; khi không thể phát, `tryEmitNext` trả về `EmitResult` thất bại để bên gọi quyết định cách xử lý. Tham số `false` tắt auto-cancel khi subscriber cuối cùng hủy, để sink có thể được dùng cho subscriber đến sau. Đây là ví dụ học tập, không tự lưu event bền vững và không tự đồng bộ giữa nhiều instance.

Trong production chạy nhiều instance, event source thường đến từ broker hoặc hệ thống event phân tán như Kafka, RabbitMQ hay nền tảng messaging phù hợp. Mỗi instance cần nhận đúng event cho các subscriber đang kết nối với nó.

Không bỏ qua `EmitResult`. Nếu sink từ chối event, ứng dụng cần có chính sách retry, ghi nhận lỗi hoặc chuyển event sang cơ chế bền vững phù hợp. Không giả định mọi lần `tryEmitNext` đều thành công.

## 7. Cold publisher và hot publisher

Cần hiểu event source được chia sẻ như thế nào giữa các subscriber.

**Cold publisher** thường bắt đầu công việc riêng khi có subscriber mới. Mỗi subscriber có thể nhận một luồng độc lập.

**Hot publisher** phát event độc lập với thời điểm subscriber đăng ký. Nhiều subscriber có thể cùng quan sát một nguồn event đang chạy; subscriber đến muộn có thể không nhận event đã phát trước đó.

| Đặc điểm | Cold publisher | Hot publisher |
| --- | --- | --- |
| Khi bắt đầu phát | Thường bắt đầu khi subscribe | Có thể phát trước khi có subscriber |
| Nguồn dữ liệu | Có thể tạo riêng cho mỗi subscriber | Thường chia sẻ nguồn event |
| Subscriber đến muộn | Bắt đầu luồng riêng theo publisher | Có thể bỏ lỡ event trước lúc đăng ký |
| Ví dụ | `Flux.defer`, một số luồng polling | `Sinks.Many`, shared event stream |
| Cần cân nhắc | Chi phí tạo nguồn cho mỗi subscriber | Fan-out, buffer, replay và mất event |

Trong ví dụ `Sinks.Many`, nhiều subscriber có thể cùng nhận event rồi lọc theo `bookId`. Nếu một subscriber cần lịch sử event trước khi đăng ký, hot stream đơn thuần không đáp ứng yêu cầu đó. Hãy kết hợp truy vấn lịch sử bằng Query hoặc dùng broker có retention/replay theo nhu cầu.

## 8. Lọc event bằng argument

Một subscription thường cần giới hạn event theo đối tượng mà client quan tâm.

Ví dụ:

~~~graphql
subscription WatchBookPrice($bookId: ID!) {
    bookPriceChanged(bookId: $bookId) {
        bookId
        price
        changedAt
    }
}
~~~

Resolver nhận `bookId` bằng `@Argument` rồi yêu cầu service tạo publisher đã lọc:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

Lọc event ở server giúp client chỉ nhận dữ liệu liên quan. Tuy nhiên, argument do client gửi không phải bằng chứng về quyền truy cập. Trước khi trả publisher, server cần kiểm tra người dùng có quyền theo dõi sách đó hay không.

Nếu event source là broker, hãy ưu tiên subscription/filter ở tầng phù hợp để tránh gửi toàn bộ event đến từng instance rồi lọc quá muộn khi lưu lượng lớn.

## 9. Nested field của event payload

Payload có thể chứa các field đơn giản hoặc quan hệ cần resolver riêng.

SDL:

~~~graphql
type BookPriceChanged {
    bookId: ID!
    price: Float!
    changedAt: String!
    book: Book
}

type Book {
    id: ID!
    title: String!
}
~~~

Resolver subscription phát payload:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId);
}
~~~

Nếu `book` không có sẵn trong payload, có thể resolve bằng `@SchemaMapping`:

~~~java
@SchemaMapping(typeName = "BookPriceChanged", field = "book")
public Book book(BookPriceChanged event) {
    return bookService.findById(event.bookId());
}
~~~

Với mỗi event, GraphQL resolve `BookPriceChanged.book` theo selection set của client. Nếu nhiều event liên tiếp đều tải cùng book, cân nhắc cách lấy dữ liệu hiệu quả, nhưng cần chú ý mỗi event có thể có execution context và DataLoader lifecycle riêng theo cách framework thực thi subscription.

Không đưa toàn bộ entity graph vào payload nếu chỉ cần một vài field. Payload nhỏ giúp giảm bộ nhớ, serialization và chi phí gửi qua WebSocket.

## 10. Cấu hình WebSocket transport

`@SubscriptionMapping` định nghĩa cách xử lý subscription field. Client còn cần một transport hỗ trợ truyền nhiều response theo thời gian. WebSocket là lựa chọn phổ biến trong ứng dụng Spring for GraphQL.

Với Spring Boot, có thể cấu hình endpoint WebSocket trong `application.yml`:

~~~yaml
spring:
  graphql:
    websocket:
      path: /graphql
~~~

Đường dẫn WebSocket phải khớp cấu hình endpoint và URL mà client sử dụng. Ứng dụng cũng cần có WebSocket runtime phù hợp với stack servlet hoặc reactive đang dùng.

Ví dụ:

- HTTP POST `/graphql` thường dùng cho Query và Mutation theo request/response.
- WebSocket `/graphql` được cấu hình để duy trì kết nối và truyền các event của Subscription.
- Một số hệ thống có thể dùng transport khác như RSocket nếu đã cấu hình tương ứng.

Chỉ khai báo `@SubscriptionMapping` không tự bật WebSocket endpoint. Hãy kiểm tra cấu hình transport, dependency và giao thức mà client/server cùng hỗ trợ.

## 11. Cancellation và cleanup

Subscription có thể sống lâu. Khi client hủy operation hoặc kết nối bị đóng, publisher cần được cancel để giải phóng tài nguyên.

Ví dụ gắn cleanup vào publisher:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
class BookPriceSubscriptionController {

    private static final Logger log =
            LoggerFactory.getLogger(BookPriceSubscriptionController.class);

    private final BookPriceEventService eventService;

    BookPriceSubscriptionController(BookPriceEventService eventService) {
        this.eventService = eventService;
    }

    @SubscriptionMapping
    public Flux<BookPriceChanged> bookPriceChanged(
            @Argument("bookId") String bookId) {

        return eventService.eventsForBook(bookId)
                .doFinally(signalType ->
                        log.debug(
                                "Book price subscription finished bookId={} signal={}",
                                bookId,
                                signalType
                        )
                );
    }
}
~~~

`doFinally` được gọi khi luồng hoàn tất, phát lỗi hoặc bị hủy. Có thể dùng nó để ghi nhận vòng đời subscription và dọn tài nguyên được tạo riêng cho subscriber.

Các tài nguyên cần giải phóng có thể gồm:

- Đăng ký listener vào message broker.
- Consumer hoặc channel được tạo riêng cho subscriber.
- Tài nguyên polling hoặc timer.
- Buffer riêng của subscription.
- Callback hoặc listener đăng ký vào service nội bộ.

Không tạo listener mới mà không có cơ chế hủy tương ứng. Nếu publisher được chia sẻ cho nhiều subscriber, cancellation của một subscriber không được vô tình đóng nguồn event chung cho tất cả subscriber.

## 12. Backpressure và subscriber chậm

Một nguồn event có thể phát nhanh hơn tốc độ client nhận và xử lý. Khi đó cần chính sách backpressure rõ ràng.

Các lựa chọn phổ biến:

- **Buffer:** giữ event trong hàng đợi để subscriber nhận sau; cần giới hạn dung lượng.
- **Drop:** bỏ event khi subscriber không theo kịp; chỉ phù hợp nếu nghiệp vụ cho phép mất event.
- **Latest:** giữ trạng thái mới nhất và bỏ các trạng thái trung gian; phù hợp với một số luồng cập nhật trạng thái.
- **Reject hoặc disconnect:** ngắt subscriber khi vượt giới hạn tài nguyên.
- **Durable broker:** dùng cơ chế lưu trữ/offset để subscriber có thể tiếp tục theo chính sách của hệ thống.

Không dùng buffer không giới hạn cho subscription lâu dài. Subscriber chậm có thể làm bộ nhớ tăng liên tục.

Nếu mỗi event đều quan trọng, ví dụ giao dịch hoặc thay đổi trạng thái cần audit, không nên dựa vào một sink trong bộ nhớ với buffer tạm thời. Hãy dùng event broker có retention, acknowledgment hoặc cơ chế replay phù hợp.

## 13. Xử lý lỗi trong subscription stream

Lỗi có thể xảy ra khi tạo publisher hoặc trong lúc publisher đang phát event.

Các nhóm lỗi thường gặp:

- Người dùng không có quyền bắt đầu subscription.
- Argument không hợp lệ hoặc đối tượng không tồn tại.
- Message broker mất kết nối.
- Lỗi xử lý một event.
- Publisher phát error signal.
- Client hủy kết nối.

Nên phân biệt lỗi từ lúc khởi tạo subscription với lỗi phát sinh sau khi luồng đã hoạt động. Khi nguồn event phát lỗi terminal, publisher thường kết thúc và subscription không tiếp tục nhận event từ luồng đó.

Có thể ánh xạ exception nghiệp vụ sang thông báo an toàn trước khi trả về stream, đồng thời ghi diagnostics ở server:

~~~java
@SubscriptionMapping
public Flux<BookPriceChanged> bookPriceChanged(
        @Argument("bookId") String bookId) {

    return eventService.eventsForBook(bookId)
            .onErrorMap(
                    EventSourceException.class,
                    exception -> new SubscriptionUnavailableException(
                            "Nguồn sự kiện hiện không khả dụng.",
                            exception
                    )
            );
}
~~~

Không đưa exception message, hostname broker hoặc stack trace vào payload event. Error handling của subscription vẫn phải tuân thủ contract GraphQL và chính sách bảo mật của ứng dụng.

Nếu chỉ một event lỗi do dữ liệu riêng lẻ, hãy quyết định rõ có bỏ qua event đó, phát một payload biểu diễn trạng thái lỗi hay kết thúc toàn stream. Không bắt mọi lỗi rồi trả một object rỗng, vì client sẽ không biết stream đã gặp sự cố.

## 14. Bảo mật subscription

Subscription thường giữ kết nối trong thời gian dài, vì vậy cần kiểm soát cả lúc đăng ký lẫn trong quá trình phát event.

Các nguyên tắc:

1. Xác thực kết nối theo cơ chế transport đang dùng.
2. Kiểm tra quyền của principal khi bắt đầu subscription.
3. Không tin `bookId`, `tenantId` hoặc filter do client gửi như dữ liệu đã được xác thực.
4. Lọc event theo tenant và quyền của subscriber ở server.
5. Xem xét quyền có thể thay đổi trong khi subscription vẫn hoạt động.
6. Hủy hoặc lọc tiếp luồng nếu người dùng bị thu hồi quyền.
7. Không gửi payload chứa dữ liệu của tenant hoặc người dùng khác.
8. Giới hạn số subscription và số kết nối đồng thời theo người dùng.
9. Tránh log token, cookie và toàn bộ event payload.

Nếu quyền truy cập có thể thay đổi trong suốt subscription, kiểm tra quyền một lần khi mở luồng có thể chưa đủ. Có thể cần kiểm tra lại theo event, hoặc dùng cơ chế thu hồi subscription khi quyền thay đổi.

## 15. Kiểm thử subscription bằng GraphQlTester

Spring GraphQL cung cấp `GraphQlTester` với API thực thi subscription trả về một luồng response. Khi kiểm thử reactive stream, có thể kết hợp Reactor `StepVerifier`.

Ví dụ operation:

~~~java
Flux<GraphQlTester.Response> responses =
        graphQlTester.document("""
                subscription WatchBookPrice($bookId: ID!) {
                    bookPriceChanged(bookId: $bookId) {
                        bookId
                        price
                    }
                }
                """)
                .variable("bookId", "book-42")
                .executeSubscription();
~~~

Kiểm tra một event rồi hủy subscription:

~~~java
StepVerifier.create(responses)
        .assertNext(response -> {
            response.path("bookPriceChanged.bookId")
                    .entity(String.class)
                    .isEqualTo("book-42");

            response.path("bookPriceChanged.price")
                    .entity(Double.class)
                    .isEqualTo(125000.0);
        })
        .thenCancel()
        .verify();
~~~

Test thực tế cần dùng tester có transport hỗ trợ subscription, ví dụ WebSocket tester, hoặc một test setup thực thi GraphQL subscription trực tiếp nếu đang kiểm tra riêng execution layer. `HttpGraphQlTester` theo request/response thông thường không thay thế transport subscription kéo dài.

Các trường hợp nên kiểm thử:

- Subscriber nhận event đúng với argument filter.
- Subscriber A không nhận event dành cho subscriber B.
- Nhiều event được phát theo đúng thứ tự mà event source bảo đảm.
- Publisher hoàn tất hoặc phát lỗi thì client nhận trạng thái tương ứng.
- Client hủy subscription thì cleanup được thực hiện.
- Subscriber chậm không làm buffer tăng vô hạn.
- Người dùng không có quyền không thể đăng ký hoặc nhận event.
- Payload không chứa field ngoài selection set hoặc dữ liệu nhạy cảm.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Subscription chỉ trả một response rồi kết thúc | Publisher chỉ phát một event hoặc là `Mono` đã hoàn tất | Kiểm tra event source và vòng đời publisher |
| `@SubscriptionMapping` không được gọi | Tên field không khớp SDL hoặc operation không đi tới root type Subscription | Kiểm tra schema và method mapping |
| Client nhận lỗi transport khi chạy subscription | WebSocket endpoint chưa bật hoặc URL/protocol không khớp | Kiểm tra cấu hình transport và client |
| Mọi subscriber đều nhận event không liên quan | Event source chia sẻ nhưng thiếu filter theo argument | Lọc theo đối tượng và quyền ở server |
| Subscriber đến muộn không nhận event cũ | Đang dùng hot publisher không có replay | Dùng Query lấy snapshot hoặc broker có retention |
| Bộ nhớ tăng theo thời gian | Buffer không giới hạn hoặc subscriber chậm | Giới hạn buffer và đặt chính sách overflow |
| Hủy client nhưng listener vẫn chạy | Không xử lý cancellation/cleanup | Dùng `doFinally` và hủy resource theo subscriber |
| Một subscriber đóng làm subscriber khác mất event | Cleanup đóng nhầm nguồn publisher dùng chung | Tách resource riêng và resource chia sẻ |
| Event source lỗi làm stream dừng | Publisher phát terminal error | Thiết kế retry/reconnect hoặc xử lý lỗi theo nghiệp vụ |
| Dữ liệu tenant khác bị gửi tới client | Chỉ lọc bằng argument client cung cấp | Xác định tenant từ principal và lọc tại server |

## 17. Quy trình triển khai @SubscriptionMapping

Khi xây dựng một subscription, hãy thực hiện theo trình tự:

1. **Xác định sự kiện.** Chọn event có ý nghĩa nghiệp vụ và payload cần gửi.
2. **Khai báo SDL.** Tạo root field trong `Subscription`, định nghĩa arguments và payload type.
3. **Viết controller mapping.** Dùng `@SubscriptionMapping` và `@Argument` cho filter.
4. **Tạo event source.** Kết nối với Reactor sink, broker hoặc publisher phù hợp.
5. **Trả Publisher.** Dùng `Flux<T>` hoặc `Publisher<T>`; không block để chờ event.
6. **Lọc dữ liệu ở server.** Kết hợp argument với principal và tenant scope.
7. **Chọn transport.** Cấu hình WebSocket hoặc transport subscription mà hệ thống hỗ trợ.
8. **Thiết kế backpressure.** Giới hạn buffer, concurrency và số subscription.
9. **Xử lý lỗi và cancellation.** Có chính sách cho terminal error và cleanup.
10. **Kiểm thử end-to-end.** Xác minh event, quyền truy cập, cancellation và transport.

## 18. Tổng kết

`@SubscriptionMapping` ánh xạ một method trong annotated controller tới field của GraphQL root type `Subscription`. Method thường nhận argument bằng `@Argument` và trả về `Publisher<T>` như `Flux<T>`. Publisher phát các payload theo thời gian; với mỗi payload, GraphQL resolve selection set và gửi một response mới cho subscriber.

Subscription cần event source và transport hỗ trợ luồng dữ liệu, thường là WebSocket trong ứng dụng Spring for GraphQL. Hãy phân biệt hot/cold publisher, lọc event theo quyền của người đăng ký, kiểm soát backpressure và giải phóng tài nguyên khi client hủy luồng. Dùng `GraphQlTester` với `StepVerifier` giúp kiểm thử nhiều event, lỗi và cancellation. `@SubscriptionMapping` là phần ánh xạ GraphQL; chất lượng subscription còn phụ thuộc event source, transport, bảo mật và cách quản lý vòng đời publisher.

