# Tạo subscription bằng Flux

## 1. Mục tiêu thực hành

Query trả về một kết quả tại thời điểm client gửi request. Subscription thiết lập một luồng để server gửi nhiều kết quả khi có sự kiện mới. Trong Spring for GraphQL, một method được đánh dấu `@SubscriptionMapping` có thể trả về `Flux<T>` của Project Reactor.

Ta sẽ xây dựng chức năng theo dõi sự kiện sách. Client đăng ký `bookEvents`, có thể lọc theo `bookId`; server phát event khi sách được tạo hoặc cập nhật; mỗi subscriber nhận các event phù hợp. Bài học tập trung vào vòng đời Publisher, ranh giới transport, xác thực, backpressure, lỗi, cancellation và kiểm thử.

Sau bài thực hành, cùng cấu trúc có thể dùng cho trạng thái đơn hàng, thông báo, tiến trình xử lý hoặc cập nhật dữ liệu trực tiếp.

## 2. Subscription trong GraphQL

GraphQL schema có ba root operation type: `Query`, `Mutation` và `Subscription`. Một field trên `Subscription` mô tả dữ liệu được phát ra cho mỗi sự kiện:

```graphql
type Subscription {
    bookEvents(bookId: ID): BookEvent!
}
```

Client đăng ký bằng operation:

```graphql
subscription WatchBook($bookId: ID) {
    bookEvents(bookId: $bookId) {
        eventId
        bookId
        eventType
        title
        occurredAt
    }
}
```

Server không trả về một danh sách event duy nhất. Thay vào đó, mỗi phần tử từ Publisher tạo ra một payload GraphQL riêng theo selection set của client. Argument `bookId` là nullable để client có thể theo dõi tất cả sách hoặc một sách cụ thể.

`@SubscriptionMapping` là annotation rút gọn của `@SchemaMapping` với root type `Subscription`. Mặc định, tên method được dùng làm tên field; có thể chỉ rõ field bằng thuộc tính `value` khi tên method khác tên SDL.

## 3. Vì sao chọn Flux?

`Flux<T>` biểu diễn một Publisher có thể phát từ 0 đến nhiều phần tử, rất phù hợp với event stream. `Mono<T>` chỉ phát tối đa một phần tử. Spring for GraphQL hỗ trợ cả hai kiểu reactive này trong annotated controller. Với Subscription, dùng `Flux<T>` để trả nhiều event; GraphQL Java nhận luồng dưới dạng Reactive Streams `Publisher` trong quá trình thực thi.

| Kiểu trả về | Số phần tử | Trường hợp dùng |
| --- | --- | --- |
| `T` | Một giá trị | Resolver đồng bộ của Query/Mutation |
| `Mono<T>` | 0 hoặc 1 | Một kết quả bất đồng bộ |
| `Flux<T>` | 0 đến nhiều | Subscription và dữ liệu stream |

Ví dụ dưới đây trả `Flux<BookEvent>`. Nếu tự đăng ký một GraphQL Java `DataFetcher` thay vì dùng annotated controller, có thể làm việc trực tiếp với Reactive Streams `Publisher`; với method `@SubscriptionMapping`, dùng `Flux` là lựa chọn rõ ràng và được Spring for GraphQL hỗ trợ trực tiếp.

Không gọi `.block()`, `.collectList()` hoặc tự gọi `.subscribe()` trong resolver. `block()` có thể chặn thread; `collectList()` gom stream thành một kết quả; tự subscribe tạo một luồng nằm ngoài vòng đời GraphQL request. Hãy trả `Flux` trực tiếp để framework quản lý subscription và cancellation.

## 4. Dependencies và cấu trúc ví dụ

Ví dụ dùng Spring Boot, Spring for GraphQL và WebFlux:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-graphql")
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.graphql:spring-graphql-test")
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-graphql-test") // Boot 4.x
    // Boot 3.x: bỏ dependency trên; @GraphQlTest có trong spring-boot-test-autoconfigure
}
```

Để phục vụ Subscription qua WebSocket, ứng dụng Servlet cần WebSocket starter phù hợp; WebFlux có WebSocket support trong stack reactive. Dependency và cấu hình endpoint phải khớp với loại server đang dùng. Spring Boot quản lý version qua dependency management nên thông thường không cần khai báo version riêng cho các dependency trên.

Cấu trúc package gợi ý:

```text
src/main/java/com/example/books/
    BookEvent.java
    BookEventType.java
    BookView.java
    UpdateBookInput.java
    BookEventPublisher.java
    BookEventService.java
    BookQueryController.java
    BookSubscriptionController.java
    BookMutationController.java
    BookService.java
    BookRepository.java
    BookApplicationService.java       # Phương án phát event sau commit
    BookUpdatedEventListener.java     # Phương án phát event sau commit
src/main/resources/graphql/
    schema.graphqls
```

## 5. Khai báo schema SDL

Tạo `src/main/resources/graphql/schema.graphqls`:

```graphql
type Query {
    book(id: ID!): Book
}

type Mutation {
    updateBook(input: UpdateBookInput!): Book!
}

type Subscription {
    bookEvents(bookId: ID): BookEvent!
}

type Book {
    id: ID!
    title: String!
}

type BookEvent {
    eventId: ID!
    bookId: ID!
    eventType: BookEventType!
    title: String
    occurredAt: String!
}

enum BookEventType {
    CREATED
    UPDATED
    DELETED
}

input UpdateBookInput {
    id: ID!
    title: String!
}
```

Field `bookEvents` trả về một `BookEvent` cho mỗi lần phát. `BookEvent!` có nghĩa payload của từng event phải có giá trị; nó không có nghĩa Subscription chỉ phát đúng một event. `occurredAt` dùng `String` để ví dụ không cần custom scalar. Trong ứng dụng thực tế, có thể khai báo scalar `DateTime` và đăng ký scalar tương ứng.

## 6. Tạo model event

Dùng Java record để biểu diễn event bất biến:

```java
public record BookEvent(
        String eventId,
        String bookId,
        BookEventType eventType,
        String title,
        String occurredAt) {
}
```

Enum Java tương ứng với GraphQL enum:

```java
public enum BookEventType {
    CREATED,
    UPDATED,
    DELETED
}
```

Input và kiểu dữ liệu mutation dùng trong ví dụ:

```java
public record UpdateBookInput(String id, String title) {
}

public record BookView(String id, String title) {
}
```

`BookService` cung cấp thao tác đọc và cập nhật sách; phần triển khai persistence được lược bỏ vì trọng tâm bài học là phát event từ thay đổi nghiệp vụ:

```java
import java.util.Optional;

public interface BookService {
    Optional<BookView> findById(String id);
    BookView update(UpdateBookInput input);
}
```

Trong ví dụ phát event sau commit bên dưới, `BookRepository` có method `BookView update(UpdateBookInput input)` để lưu thay đổi:

```java
public interface BookRepository {
    BookView update(UpdateBookInput input);
}
```

Khi tạo event, đặt thời gian ở định dạng ISO-8601 UTC:

```java
String occurredAt = Instant.now().toString();
```

Spring GraphQL ánh xạ record accessor như `eventId()` và `bookId()` tới các field GraphQL có tên tương ứng. Nếu model khác cấu trúc schema, dùng `@SchemaMapping` hoặc DTO riêng để điều chỉnh.

## 7. Tạo event publisher bằng Sinks.Many

Subscription cần một nguồn phát event. Để thực hành trong một JVM, dùng Reactor `Sinks.Many`:

```java
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

@Component
public class BookEventPublisher {

    private final Sinks.Many<BookEvent> sink =
            Sinks.many().multicast().onBackpressureBuffer(256, false);

    public Flux<BookEvent> events() {
        return sink.asFlux();
    }

    public Sinks.EmitResult publish(BookEvent event) {
        return sink.tryEmitNext(event);
    }
}
```

`multicast` cho phép nhiều subscriber đang hoạt động cùng nhận event mới. Sink này không replay toàn bộ lịch sử cho subscriber đến sau. Buffer có giới hạn giúp tránh để một subscriber chậm làm bộ nhớ tăng vô hạn; khi không thể phát event, `tryEmitNext` trả về `EmitResult` để producer xử lý.

Đây là publisher trong bộ nhớ của một process. Event sẽ mất khi process restart và không tự đồng bộ giữa nhiều replica. Với nghiệp vụ cần delivery bền vững, dùng message broker hoặc Transactional Outbox; mỗi instance GraphQL có thể tiêu thụ stream từ broker rồi phân phối đến các subscriber cục bộ.

## 8. Xử lý kết quả emit

Không bỏ qua kết quả trả về từ `tryEmitNext`:

```java
import org.springframework.stereotype.Service;
import reactor.core.publisher.Sinks;

@Service
public class BookEventService {

    private final BookEventPublisher publisher;

    public BookEventService(BookEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void publish(BookEvent event) {
        Sinks.EmitResult result = publisher.publish(event);
        if (result.isFailure()) {
            throw new IllegalStateException(
                    "Cannot publish book event: " + result);
        }
    }
}
```

Một số tình huống thất bại thường gặp:

| Kết quả | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `FAIL_OVERFLOW` | Buffer không còn chỗ cho event mới | Xem lại tốc độ consumer và chính sách buffer/drop |
| `FAIL_NON_SERIALIZED` | Nhiều producer phát đồng thời | Tuần tự hóa lệnh emit hoặc dùng emission handler có retry |
| `FAIL_TERMINATED` | Sink đã complete hoặc error | Kiểm tra lifecycle, tạo publisher mới nếu đúng thiết kế |
| `FAIL_CANCELLED` | Sink đã bị cancel | Kiểm tra cấu hình auto-cancel và lifecycle |
| `OK` | Event được chấp nhận | Tiếp tục xử lý |

Với event quan trọng, cần metric, log có correlation ID và cơ chế retry/lưu bền vững. Không âm thầm bỏ event khi producer nhận kết quả thất bại.

## 9. Viết resolver @SubscriptionMapping trả Flux

Controller ánh xạ field `Subscription.bookEvents`:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Flux;

@Controller
public class BookSubscriptionController {

    private final BookEventPublisher publisher;

    public BookSubscriptionController(BookEventPublisher publisher) {
        this.publisher = publisher;
    }

    @SubscriptionMapping
    public Flux<BookEvent> bookEvents(
            @Argument("bookId") String bookId) {

        Flux<BookEvent> events = publisher.events();
        if (bookId == null) {
            return events;
        }
        return events.filter(event -> bookId.equals(event.bookId()));
    }
}
```

Tên method trùng với field SDL nên Spring có thể suy ra mapping. `@Argument` đọc giá trị client gửi. `filter` chạy trên từng event, vì vậy subscriber chỉ nhận event có `bookId` khớp.

Nếu tên method không trùng field, khai báo rõ:

```java
@SubscriptionMapping("bookEvents")
public Flux<BookEvent> streamBookChanges(
        @Argument String bookId) {
    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()));
}
```

Một resolver chỉ tạo Publisher. Không cần tự tạo thread, giữ danh sách subscriber hay gửi payload qua socket; Spring for GraphQL và transport handler thực hiện phần kết nối.

Root query trong SDL có thể được ánh xạ bằng controller đọc sách:

```java
import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookQueryController {

    private final BookService bookService;

    public BookQueryController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public BookView book(@Argument("id") String id) {
        return bookService.findById(id).orElse(null);
    }
}
```

`Query.book` là nullable trong SDL nên controller có thể trả null khi không tìm thấy sách. `BookView` cung cấp hai property `id` và `title` tương ứng với GraphQL type `Book`.

## 10. Phát event từ Mutation

Khi Mutation cập nhật sách thành công, ứng dụng có thể tạo event:

```java
import java.time.Instant;
import java.util.UUID;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookMutationController {

    private final BookService bookService;
    private final BookEventService eventService;

    public BookMutationController(
            BookService bookService,
            BookEventService eventService) {
        this.bookService = bookService;
        this.eventService = eventService;
    }

    @MutationMapping
    public BookView updateBook(@Argument UpdateBookInput input) {
        BookView updated = bookService.update(input);

        eventService.publish(new BookEvent(
                UUID.randomUUID().toString(),
                updated.id(),
                BookEventType.UPDATED,
                updated.title(),
                Instant.now().toString()));

        return updated;
    }
}
```

Trong ví dụ này, nếu `bookService.update` là một transactional service method được gọi qua Spring proxy và không có transaction bên ngoài bao quanh controller, transaction của service commit trước khi method trả về; lệnh publish tiếp theo vì thế chạy sau commit. Nếu event được phát bên trong transaction hoặc có một transaction bên ngoài bao trùm cả mutation, subscriber có thể nhận event trước khi transaction cuối cùng commit. Production nên làm rõ ranh giới này bằng application event và `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)`, hoặc dùng Transactional Outbox khi không được phép mất event giữa commit và publish.

Trong đường đi trực tiếp này, nếu `eventService.publish` thất bại sau khi service đã commit, mutation có thể trả lỗi dù dữ liệu sách đã được cập nhật. Outbox giúp ghi ý định phát event cùng transaction nghiệp vụ để worker có thể retry độc lập.

Một cách dùng application event để chỉ phát ra sink sau khi transaction commit:

Đặt `BookUpdatedApplicationEvent`, `BookApplicationService` và `BookUpdatedEventListener` trong các file riêng. Các import được gom ở đầu đoạn minh họa:

```java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

public record BookUpdatedApplicationEvent(BookView book) {
}

@Service
public class BookApplicationService {

    private final BookRepository bookRepository;
    private final ApplicationEventPublisher applicationEvents;

    public BookApplicationService(
            BookRepository bookRepository,
            ApplicationEventPublisher applicationEvents) {
        this.bookRepository = bookRepository;
        this.applicationEvents = applicationEvents;
    }

    @Transactional
    public BookView update(UpdateBookInput input) {
        BookView updated = bookRepository.update(input);
        applicationEvents.publishEvent(new BookUpdatedApplicationEvent(updated));
        return updated;
    }
}

@Component
public class BookUpdatedEventListener {

    private final BookEventService eventService;

    public BookUpdatedEventListener(BookEventService eventService) {
        this.eventService = eventService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(BookUpdatedApplicationEvent event) {
        BookView book = event.book();
        eventService.publish(new BookEvent(
                UUID.randomUUID().toString(),
                book.id(),
                BookEventType.UPDATED,
                book.title(),
                Instant.now().toString()));
    }
}
```

`BookRepository.update` đại diện cho thao tác persistence của ứng dụng. Application event được phát bên trong transaction; listener `AFTER_COMMIT` chỉ chuyển nó thành stream event sau khi transaction thành công. Nếu process dừng sau commit nhưng trước khi listener phát event, in-memory sink vẫn có thể mất event; dùng Outbox và broker nếu cần delivery bền vững.

Khi dùng phương án này, mutation gọi `BookApplicationService.update(...)` và bỏ lời gọi `eventService.publish(...)` trực tiếp trong controller để tránh phát trùng event. Lỗi ở listener sau commit không thể rollback database transaction đã hoàn tất.

## 11. Transport boundary: WebSocket, SSE và RSocket

GraphQL Subscription cần một transport có thể truyền nhiều payload trong suốt vòng đời operation. Spring for GraphQL cung cấp tích hợp cho WebSocket và RSocket. Spring Boot hiện cũng hỗ trợ HTTP Server-Sent Events (SSE) cho Subscription khi client yêu cầu media type `text/event-stream`; khả năng và cấu hình cụ thể phụ thuộc phiên bản Spring Boot/Spring for GraphQL.

| Transport | Cách truyền | Điểm cần kiểm tra |
| --- | --- | --- |
| WebSocket | GraphQL over WebSocket, thường dùng `graphql-transport-ws` | Handshake, subprotocol, `connection_init`, `connection_ack`, payload và close |
| SSE | HTTP response `text/event-stream` | `Accept` header, event đầu tiên, timeout và client đóng stream |
| RSocket | `request-stream` | Session, route và demand/cancel |
| HTTP JSON request/response thông thường | Một response cho mỗi request | Phù hợp với Query/Mutation; không phải stream Subscription liên tục |

Ví dụ cấu hình WebSocket endpoint:

```yaml
spring:
  graphql:
    websocket:
      path: /graphql
      connection-init-timeout: 10s
      keep-alive: 20s
```

WebSocket cần được bật bằng dependency và cấu hình phù hợp với Servlet hoặc WebFlux. Boot Starter không expose WebSocket endpoint mặc định; cấu hình `spring.graphql.websocket.path` để bật endpoint và chọn path phù hợp. `connection_init` có thể mang thông tin xác thực; server phản hồi `connection_ack` khi chấp nhận khởi tạo kết nối. Ack chỉ xác nhận connection initialization, chưa chứng minh resolver thực thi được.

SSE là luồng một chiều từ server đến client, thích hợp cho Subscription qua HTTP khi client gửi `Accept: text/event-stream`; kiểm tra thêm các thuộc tính `spring.graphql.http.sse.*` mà phiên bản Boot đang dùng cung cấp. RSocket truyền Subscription theo interaction model `request-stream`. Client phải dùng đúng transport endpoint; gửi HTTP POST JSON thông thường tới `/graphql` không tự biến request thành stream.

## 12. Authentication và authorization

Xác thực kết nối và kiểm tra quyền truy cập event là hai việc liên quan nhưng khác nhau. Có thể xác thực người dùng ở HTTP handshake/WebSocket connection initialization hoặc qua cơ chế security của ứng dụng. Sau khi xác thực, Subscription resolver có thể nhận `Principal`:

```java
public interface BookAuthorization {
    boolean canReadBook(java.security.Principal principal, String bookId);
}
```

Method dưới đây nằm trong `BookSubscriptionController`, nơi inject `BookEventPublisher` và `BookAuthorization` qua constructor:

```java
import java.security.Principal;

// Đặt method trong controller có inject BookEventPublisher và BookAuthorization.
@SubscriptionMapping
public Flux<BookEvent> bookEvents(
        @Argument String bookId,
        Principal principal) {

    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()))
            .filter(event -> authorization.canReadBook(
                    principal, event.bookId()));
}
```

`authorization.canReadBook` ở đây là service nghiệp vụ trả về boolean. Trong ứng dụng reactive, nếu kiểm tra quyền bất đồng bộ, dùng `filterWhen` với `Mono<Boolean>` để không block thread.

Không coi `bookId` do client truyền là bằng chứng authorization. Client có thể đoán ID thuộc người dùng hoặc tenant khác. Quyền phải được xác định từ principal đã xác thực và dữ liệu sở hữu ở server.

Với Subscription kéo dài, quyền có thể thay đổi sau lúc kết nối. Nếu nghiệp vụ yêu cầu thu hồi quyền tức thời, cần kiểm tra quyền theo event hoặc đóng subscription khi nhận tín hiệu thu hồi. Không ghi token hay payload `connection_init` vào log; tránh đặt bearer token trong URL query string.

## 13. Backpressure và subscriber chậm

Reactive Streams có cơ chế demand: subscriber báo số phần tử muốn nhận và publisher/operator phối hợp để không phát vô hạn vượt nhu cầu. Tuy nhiên, backpressure trong `Flux` không có nghĩa mọi transport đều truyền nguyên vẹn demand đến tận browser.

- RSocket `request-stream` có mô hình demand ở protocol.
- WebSocket GraphQL protocol không định nghĩa một thông điệp demand tương đương Reactive Streams; server, framework, socket và client có thể có buffer riêng.
- SSE chạy trên HTTP streaming; tốc độ đọc của client và buffer ở server/proxy vẫn ảnh hưởng đến tài nguyên.

Thứ tự phát từ source `Flux` cũng không luôn bảo đảm thứ tự payload đến client: GraphQL Java có thể resolve các field con bất đồng bộ. Nếu thứ tự event là một phần của contract, có thể bật `SubscriptionExecutionStrategy.KEEP_SUBSCRIPTION_EVENTS_ORDERED` trong `GraphQLContext` qua `Instrumentation`; đổi lại engine có thể phải buffer kết quả để giữ thứ tự.

Vì vậy cần giới hạn buffer, kích thước event, số subscription trên mỗi connection và tốc độ phát. Với sink multicast, subscriber chậm có thể ảnh hưởng việc phát chung. Nếu `tryEmitNext` trả `FAIL_OVERFLOW`, producer cần áp dụng chính sách rõ ràng:

| Chính sách | Khi phù hợp |
| --- | --- |
| Buffer có giới hạn | Chậm trong thời gian ngắn và event cần được giữ tạm |
| Drop event | Event có thể được tải lại hoặc chỉ mang tính best-effort |
| Giữ trạng thái mới nhất | Chỉ giá trị cuối cùng có ý nghĩa, ví dụ giá hiện tại |
| Ngắt stream và reconnect | Không thể tiếp tục đảm bảo tính đúng đắn |
| Durable broker + cursor | Event phải được lưu và consumer có thể tiếp tục từ offset |

Không tăng buffer vô hạn. Một subscriber chậm có thể làm bộ nhớ tăng và ảnh hưởng các request khác.

## 14. Cancellation và giải phóng tài nguyên

Subscription kết thúc khi client gửi complete/cancel, đóng WebSocket, đóng SSE response, đóng RSocket interaction, hoặc publisher complete/error. Framework sẽ cancel subscription upstream khi transport hủy operation.

Có thể quan sát lifecycle bằng `doFinally`:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

// Đặt các thành phần này trong BookSubscriptionController.
private static final Logger logger =
        LoggerFactory.getLogger(BookSubscriptionController.class);

@SubscriptionMapping
public Flux<BookEvent> bookEvents(@Argument String bookId) {
    return publisher.events()
            .filter(event -> bookId == null || bookId.equals(event.bookId()))
            .doFinally(signal ->
                    logger.debug("bookEvents finished: {}", signal));
}
```

`doFinally` chạy khi stream complete, error hoặc cancel. Có thể dùng để giảm subscriber counter, ghi metric hoặc giải phóng resource gắn với subscriber. Nếu Publisher đăng ký callback ở hệ thống ngoài, phải hủy callback khi stream bị cancel; cân nhắc `Flux.using` hoặc `Flux.usingWhen` để quản lý resource.

Không giữ subscription vô hạn nếu client đã rời đi. Đặt timeout/maximum lifetime nếu yêu cầu vận hành cần giới hạn session, và thiết kế client reconnect có backoff.

## 15. Xử lý lỗi trong stream

Lỗi có thể xuất hiện lúc tạo Publisher hoặc sau khi Subscription đã phát một số event. Cần phân biệt lỗi request ban đầu, lỗi khi thực thi một payload và lỗi làm kết thúc Publisher.

Có thể ghi nhận lỗi ở stream:

```java
return publisher.events()
        .doOnError(error ->
                logger.warn("Book event stream failed", error));
```

Không tự động đổi mọi lỗi thành `Flux.empty()` vì client có thể tưởng stream kết thúc bình thường và bỏ lỡ event. Nếu có thể phục hồi, hãy xác định rõ chiến lược retry/reconnect và cách client lấy lại trạng thái. Lưu ý `DataFetcherExceptionResolver` và `@GraphQlExceptionHandler` xử lý lỗi phát sinh khi resolver tạo Publisher; chúng không xử lý `onError` phát sinh sau đó trong stream. Để ánh xạ lỗi của Subscription Publisher thành GraphQL error gửi cho client, đăng ký một bean `SubscriptionExceptionResolver`. Sanitize thông tin trả về và không để lộ stack trace hoặc dữ liệu nội bộ.

Một số lỗi nghiệp vụ riêng lẻ có thể được biểu diễn thành event trạng thái nếu đó là một phần của contract. Còn lỗi làm hỏng nguồn stream nên kết thúc stream và được quan sát qua metric/log. Client nên reconnect với exponential backoff và thực hiện Query lấy snapshot trước khi tiếp tục nhận event để tránh khoảng trống dữ liệu.

## 16. Kiểm thử Publisher bằng StepVerifier

`StepVerifier` của Reactor Test kiểm tra publisher mà không cần khởi động GraphQL server:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Sinks;
import reactor.test.StepVerifier;

class BookEventPublisherTests {

    @Test
    void emitsAnEventAndSupportsCancellation() {
        BookEventPublisher publisher = new BookEventPublisher();
        BookEvent event = new BookEvent(
                "event-1", "book-10", BookEventType.UPDATED,
                "Spring GraphQL", "2026-11-20T10:00:00Z");

        StepVerifier.create(publisher.events())
                .then(() -> assertThat(publisher.publish(event))
                        .isEqualTo(Sinks.EmitResult.OK))
                .expectNext(event)
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }
}
```

Test trên xác nhận event được phát tới subscriber và kiểm tra cancellation. Nó chưa kiểm tra SDL, mapping của `@SubscriptionMapping` hay giao thức WebSocket.

## 17. Kiểm thử GraphQL Subscription bằng GraphQlTester

Spring GraphQL Test cung cấp `GraphQlTester.executeSubscription()` để kiểm tra stream kết quả. `toFlux(path, type)` chuyển field trong mỗi payload thành Flux Java. Có thể dùng một tester phù hợp với execution service để kiểm tra GraphQL layer; khi cần xác nhận transport thật, cấu hình `WebSocketGraphQlTester` và chạy test với server WebSocket đang hoạt động.

Ví dụ kiểm tra GraphQL subscription với một `GraphQlTester` đã được cấu hình trong test context:

```java
// Spring Boot 4.x:
import org.springframework.boot.graphql.test.autoconfigure.GraphQlTest;
// Spring Boot 3.x:
// import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;
import reactor.core.publisher.Sinks;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@GraphQlTest(BookSubscriptionController.class)
@Import(BookEventPublisher.class)
class BookSubscriptionTests {

    @Autowired
    GraphQlTester graphQlTester;

    @Autowired
    BookEventPublisher publisher;

    @Test
    void streamsBookEvents() {
        Flux<BookEvent> events = graphQlTester.document("""
                subscription {
                    bookEvents(bookId: "book-10") {
                        eventId
                        bookId
                        eventType
                        title
                        occurredAt
                    }
                }
                """)
                .executeSubscription()
                .toFlux("bookEvents", BookEvent.class);

        StepVerifier.create(events)
                .then(() -> assertThat(publisher.publish(new BookEvent(
                        "event-other", "book-99", BookEventType.UPDATED,
                        "Other book", "2026-11-20T10:00:30Z")))
                        .isEqualTo(Sinks.EmitResult.OK))
                .then(() -> assertThat(publisher.publish(new BookEvent(
                        "event-2", "book-10", BookEventType.UPDATED,
                        "Reactive GraphQL", "2026-11-20T10:01:00Z")))
                        .isEqualTo(Sinks.EmitResult.OK))
                .assertNext(event -> {
                    assertThat(event.eventId()).isEqualTo("event-2");
                    assertThat(event.title()).isEqualTo("Reactive GraphQL");
                })
                .thenCancel()
                .verify(Duration.ofSeconds(3));
    }
}
```

`@GraphQlTest` tự cấu hình `GraphQlTester` để kiểm tra execution phía server nhưng không tự scan các bean `@Component`; `@Import(BookEventPublisher.class)` đưa publisher vào test slice. Đảm bảo publisher được subscribe trước khi test phát event; `StepVerifier.then` thực hiện hành động sau khi subscription được thiết lập. Trong test thực tế, dùng publisher riêng cho từng test để tránh event từ test khác lọt vào stream.

Khi kiểm tra transport, dùng `WebSocketGraphQlTester` được tạo với URL/subprotocol và WebSocket client tương ứng. Test qua transport nên xác nhận handshake, authentication, nhận payload, complete/cancel và đóng connection. `GraphQlTester` ở execution layer không tự chứng minh network, reverse proxy hay WebSocket handshake đang hoạt động.

## 18. Checklist và lỗi thường gặp

| Vấn đề | Nguyên nhân thường gặp | Cách khắc phục |
| --- | --- | --- |
| Subscription chỉ trả một lần | Resolver gom Flux thành list hoặc trả Mono | Trả `Flux<T>` trực tiếp |
| Không nhận event | Producer chưa emit, subscriber đăng ký sai thời điểm hoặc sink đã terminate | Kiểm tra lifecycle và `EmitResult` |
| Nhiều client nhận dữ liệu sai tenant | Chỉ filter theo argument client gửi | Kiểm tra quyền dựa trên Principal ở server |
| Event bị mất giữa các replica | Dùng sink trong bộ nhớ của một JVM | Dùng broker hoặc outbox bền vững |
| Bộ nhớ tăng khi client chậm | Buffer không giới hạn hoặc event phát quá nhanh | Giới hạn buffer, rate và số subscription |
| Tài nguyên vẫn chạy sau khi client đóng | Tự subscribe hoặc không cleanup callback | Trả Publisher cho framework và xử lý cancellation |
| Test treo | Không có event, không cancel hoặc thiếu timeout | Dùng StepVerifier với timeout và trigger event sau subscribe |
| HTTP endpoint không stream | Dùng request/response JSON thường | Bật và dùng WebSocket, SSE hoặc RSocket phù hợp |

Trước khi đưa vào production, xác nhận các điểm sau:

- [ ] SDL khai báo root `Subscription` và event type đúng contract.
- [ ] Resolver `@SubscriptionMapping` trả `Flux<T>` trực tiếp.
- [ ] Event chỉ phát sau khi thao tác nghiệp vụ đã commit.
- [ ] Producer kiểm tra `Sinks.EmitResult` hoặc kết quả publish từ broker.
- [ ] Client kết nối qua transport hỗ trợ streaming.
- [ ] Authentication và authorization được áp dụng cho từng người dùng/tenant.
- [ ] Buffer, event size, số connection và số subscription có giới hạn.
- [ ] Cancellation giải phóng listener, resource và metric đúng cách.
- [ ] Lỗi được quan sát, sanitize và có chiến lược reconnect/resync.
- [ ] Có test Publisher, GraphQL execution và transport integration.

## Kết luận

Trong Spring for GraphQL, `@SubscriptionMapping` ánh xạ một field trên root type `Subscription`. Resolver trả về `Flux<T>`; Spring GraphQL kết nối luồng này với transport và quản lý vòng đời operation. `Sinks.Many` giúp thực hành phát event trong một JVM, còn hệ thống phân tán hoặc event quan trọng nên dùng broker và cơ chế lưu bền vững.

Thiết kế Subscription cần quan tâm cả GraphQL schema lẫn transport: WebSocket, SSE và RSocket có cách kết nối và truyền stream khác nhau. Xác thực connection chưa thay thế authorization trên dữ liệu event; backpressure ở Reactor không đảm bảo mọi transport có cùng semantics; cancellation phải giải phóng resource; lỗi stream cần được quan sát và có chiến lược reconnect. `StepVerifier` kiểm tra Publisher, còn `GraphQlTester` và `WebSocketGraphQlTester` giúp kiểm tra GraphQL execution và transport tương ứng.

## Tài liệu tham khảo

- [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html)
- [Spring for GraphQL — Request Execution and Subscription Exceptions](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring for GraphQL — Server Transports](https://docs.spring.io/spring-graphql/reference/transports.html)
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring Boot — Spring for GraphQL](https://docs.spring.io/spring-boot/reference/web/spring-graphql.html)
- [Project Reactor — Sinks](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html)
- [Reactive Streams Specification](https://www.reactive-streams.org/)
- [GraphQL over WebSocket Protocol](https://github.com/enisdenjo/graphql-ws/blob/master/PROTOCOL.md)
