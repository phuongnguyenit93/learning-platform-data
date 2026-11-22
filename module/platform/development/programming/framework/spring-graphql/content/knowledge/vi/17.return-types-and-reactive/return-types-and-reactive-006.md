# Flux trong Spring for GraphQL

`Flux<T>` là kiểu publisher của Project Reactor, biểu diễn một chuỗi bất đồng bộ có thể phát ra từ 0 đến nhiều phần tử. Trong Spring for GraphQL, `Flux` có thể được dùng làm kiểu trả về của controller và service để xử lý dữ liệu theo mô hình reactive.

Điểm quan trọng là ý nghĩa của `Flux` phụ thuộc vào loại GraphQL field. Với một query hoặc field thông thường có kiểu danh sách, Spring for GraphQL thu thập các phần tử của `Flux` để tạo một list trong một GraphQL response. Với subscription, `Flux` biểu diễn một luồng sự kiện; mỗi phần tử được phát ra tạo thành một kết quả subscription riêng. Vì vậy, không nên nhầm một query trả `Flux` với một subscription stream.

## 1. Flux là gì?

Reactor cung cấp hai kiểu publisher thường dùng:

| Kiểu | Số phần tử | Cách sử dụng thường gặp |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Lấy một object, một kết quả hoặc một thao tác hoàn tất. |
| `Flux<T>` | 0 đến nhiều | Lấy danh sách bất đồng bộ hoặc phát một chuỗi sự kiện. |

`Flux<T>` triển khai Reactive Streams `Publisher<T>`. Subscriber đăng ký nhận dữ liệu và điều khiển nhu cầu qua cơ chế backpressure. Các operator của Reactor cho phép biến đổi, lọc, kết hợp, xử lý lỗi và quản lý vòng đời của chuỗi dữ liệu.

Ví dụ tạo Flux đơn giản:

```java
import reactor.core.publisher.Flux;

Flux<String> names = Flux.just("An", "Binh", "Chi");
```

Tạo Flux từ một collection:

```java
List<Book> books = List.of(book1, book2, book3);
Flux<Book> bookFlux = Flux.fromIterable(books);
```

Tạo Flux rỗng hoặc kết thúc bằng lỗi:

```java
Flux<Book> empty = Flux.empty();
Flux<Book> failed = Flux.error(new IllegalStateException("Source unavailable"));
```

Flux không tự làm cho thao tác trở nên non-blocking. Nếu nguồn dữ liệu bên dưới vẫn gọi JDBC blocking hoặc chờ I/O đồng bộ, pipeline có thể vẫn chiếm thread trong lúc chờ. Muốn đạt lợi ích reactive end-to-end, nên dùng các client và persistence API có hỗ trợ reactive như WebClient hoặc R2DBC, đồng thời tránh blocking trên event-loop thread.

## 2. Flux là kiểu Java, không phải GraphQL scalar

GraphQL SDL không có kiểu `Flux`. SDL mô tả hình dạng dữ liệu mà client nhìn thấy; `Flux` là cách server cung cấp dữ liệu bất đồng bộ.

Ví dụ schema khai báo một field danh sách:

```graphql
type Query {
    books: [Book!]!
}

type Book {
    id: ID!
    title: String!
}
```

Resolver có thể trả `List<Book>` hoặc `Flux<Book>`:

```java
@QueryMapping
public Flux<Book> books() {
    return bookService.findAll();
}
```

Spring for GraphQL xử lý publisher và thu thập các phần tử để hoàn tất field list. Client vẫn nhận một mảng JSON trong một response GraphQL thông thường. Client không nhìn thấy kiểu Java `Flux`.

Với field chỉ trả về một object, có thể dùng `Mono<Book>`:

```graphql
type Query {
    book(id: ID!): Book
}
```

```java
@QueryMapping
public Mono<Book> book(@Argument("id") String id) {
    return bookService.findById(id);
}
```

`Mono<Book>` phù hợp với field trả về một object nullable. Nếu source không tìm thấy sách và trả `Mono.empty()`, field nullable có thể hoàn tất thành null. Nếu schema khai báo `Book!`, ứng dụng phải bảo đảm có giá trị hoặc xử lý lỗi phù hợp với hợp đồng Non-Null.

## 3. Dùng Flux cho Query trả về danh sách

Một query list thường hoàn tất sau khi nguồn dữ liệu phát đủ phần tử và kết thúc. Ví dụ service dùng reactive repository:

```java
import reactor.core.publisher.Flux;

public interface BookService {
    Flux<Book> findAll();
    Flux<Book> findByAuthor(String authorId);
}
```

Controller:

```java
import reactor.core.publisher.Flux;
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
    public Flux<Book> books() {
        return bookService.findAll();
    }

    @QueryMapping
    public Flux<Book> booksByAuthor(@Argument("authorId") String authorId) {
        return bookService.findByAuthor(authorId);
    }
}
```

SDL:

```graphql
type Query {
    books: [Book!]!
    booksByAuthor(authorId: ID!): [Book!]!
}
```

Client gọi query:

```graphql
query {
    booksByAuthor(authorId: "author-10") {
        id
        title
    }
}
```

Response có dạng list bình thường:

```json
{
  "data": {
    "booksByAuthor": [
      { "id": "book-1", "title": "Reactive Spring" },
      { "id": "book-2", "title": "GraphQL in Practice" }
    ]
  }
}
```

Query phải đợi publisher hoàn tất để tạo giá trị list. Vì vậy, chỉ dùng `Flux` cho query khi nguồn có thể kết thúc. Một `Flux` chạy vô hạn như `Flux.interval(...)` không phù hợp làm kết quả của query list thông thường vì response không thể hoàn tất.

## 4. Flux cho field lồng nhau

`Flux` cũng có thể được dùng cho một field list nằm trong object, ví dụ mỗi sách có nhiều tag:

```graphql
type Query {
    book(id: ID!): Book
}

type Book {
    id: ID!
    title: String!
    tags: [String!]!
}
```

Resolver field lồng nhau:

```java
import reactor.core.publisher.Flux;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookFieldController {

    private final TagService tagService;

    public BookFieldController(TagService tagService) {
        this.tagService = tagService;
    }

    @SchemaMapping(typeName = "Book", field = "tags")
    public Flux<String> tags(Book book) {
        return tagService.findNamesByBookId(book.id());
    }
}
```

Khi GraphQL hoàn tất field `tags`, publisher được thu thập thành list để đưa vào response của query. Nếu nhiều sách cùng được trả về và mỗi resolver `tags` gọi database riêng, ứng dụng có thể gặp N+1 query. Khi đó nên cân nhắc `@BatchMapping`, DataLoader hoặc truy vấn lấy dữ liệu theo lô; dùng `Flux` tự nó không loại bỏ N+1.

## 5. Dùng Flux cho Subscription

Subscription là loại operation dành cho dữ liệu được phát ra theo thời gian. Root field của subscription có thể trả về `Flux<T>` để đại diện cho chuỗi sự kiện.

SDL:

```graphql
type Query {
    books: [Book!]!
}

type Subscription {
    bookAdded: Book!
}

type Book {
    id: ID!
    title: String!
}
```

Controller:

```java
import reactor.core.publisher.Flux;
import org.springframework.graphql.data.method.annotation.SubscriptionMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookSubscriptionController {

    private final BookEventService bookEventService;

    public BookSubscriptionController(BookEventService bookEventService) {
        this.bookEventService = bookEventService;
    }

    @SubscriptionMapping
    public Flux<Book> bookAdded() {
        return bookEventService.bookAddedEvents();
    }
}
```

Client đăng ký:

```graphql
subscription {
    bookAdded {
        id
        title
    }
}
```

Khi `Flux` phát ra một `Book`, GraphQL thực thi selection set cho sự kiện đó và gửi một subscription response. Nếu publisher phát ra ba sách, client nhận ba kết quả riêng theo thời gian, thay vì một mảng chứa cả ba sách như query list.

| Đặc điểm | Query trả `Flux<Book>` | Subscription trả `Flux<Book>` |
| --- | --- | --- |
| SDL | Field thường có kiểu `[Book!]!` | Root field có kiểu `Book!` hoặc kiểu event phù hợp |
| Ý nghĩa Flux | Nguồn dữ liệu để tạo một list | Luồng sự kiện nhiều lần |
| Kết quả client | Một GraphQL response khi Flux hoàn tất | Nhiều GraphQL response theo từng event |
| Vòng đời | Thường hữu hạn | Có thể dài hạn cho đến khi complete/cancel/error |
| Khi phù hợp | Danh sách được tải bất đồng bộ | Thông báo hoặc dữ liệu thay đổi liên tục |

Subscription cần transport hỗ trợ streaming, thường là WebSocket hoặc RSocket trong Spring for GraphQL. HTTP request/response thông thường phù hợp với query và mutation; hãy cấu hình subscription transport và endpoint theo môi trường triển khai.

## 6. Tạo một luồng sự kiện bằng Reactor Sinks

Trong ví dụ nhỏ hoặc hệ thống đơn giản, có thể dùng `Sinks.Many` làm nguồn phát sự kiện:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

import org.springframework.stereotype.Service;

@Service
public class BookEventService {

    private final Sinks.Many<Book> sink =
            Sinks.many().multicast().onBackpressureBuffer();

    public Flux<Book> bookAddedEvents() {
        return sink.asFlux();
    }

    public void publish(Book book) {
        Sinks.EmitResult result = sink.tryEmitNext(book);
        if (result.isFailure()) {
            throw new IllegalStateException("Cannot publish book event: " + result);
        }
    }
}
```

Sau khi lưu sách thành công, một service có thể gọi `publish(savedBook)` để phát event. Subscriber đang hoạt động sẽ nhận sự kiện theo chính sách của sink.

`multicast()` là lựa chọn cho các subscriber đang đăng ký; subscriber mới không mặc nhiên nhận lại toàn bộ lịch sử event đã phát trước đó. Nếu cần phát lại dữ liệu gần đây, hãy thiết kế replay/cache hoặc đọc trạng thái từ database. `Sinks.Many` trong bộ nhớ phù hợp cho minh họa hoặc một instance ứng dụng đơn giản; nó không thay thế message broker khi cần chia sẻ event giữa nhiều instance, lưu bền vững hoặc khôi phục sau restart.

Lưu ý vòng đời của sink: multicast sink có chính sách auto-cancel khi subscriber cuối cùng hủy đăng ký ở cấu hình mặc định. Nếu giữ sink trong một singleton service và mong nó phục vụ các subscriber kết nối lại sau này, cần chọn cấu hình auto-cancel phù hợp với phiên bản Reactor đang dùng hoặc tạo/quản lý nguồn publisher theo vòng đời rõ ràng. Hãy kiểm thử cả trường hợp subscriber cuối cùng hủy rồi subscriber mới đăng ký.

Trong hệ thống production, nguồn Flux có thể đến từ Kafka, RabbitMQ, Redis Streams, RSocket hoặc một event service khác. Chọn công nghệ dựa trên yêu cầu lưu trữ, phân phối, thứ tự và khả năng retry của sự kiện.

## 7. Flux cold và hot

Không phải Flux nào cũng có cùng cách phát dữ liệu:

- *Cold publisher* thường bắt đầu công việc khi có subscriber mới. Mỗi subscriber có thể tạo một lần thực thi độc lập, ví dụ một query database.
- *Hot publisher* phát dữ liệu độc lập với việc subscriber đã đăng ký hay chưa. Subscriber đến muộn có thể bỏ lỡ các event trước đó, tùy cơ chế replay/buffer.

Ví dụ cold Flux:

```java
Flux<Book> books = Flux.defer(() -> bookRepository.findAll());
```

Mỗi lần subscribe, supplier được gọi để lấy publisher mới. Ví dụ hot stream với `Sinks.Many` được trình bày ở phần trước.

Với subscription, cần quyết định subscriber mới có nhận event cũ không. Nếu chỉ cần event từ thời điểm đăng ký, multicast có thể phù hợp. Nếu client cần trạng thái hiện tại, hãy cung cấp query riêng để đọc snapshot rồi dùng subscription để nhận cập nhật tiếp theo. Cần thiết kế ranh giới giữa snapshot và stream để tránh bỏ sót hoặc xử lý trùng event.

Không chia sẻ một hot stream toàn cục cho dữ liệu nhạy cảm mà không lọc theo tenant, quyền và điều kiện subscription. Mỗi subscriber có thể có phạm vi dữ liệu khác nhau.

## 8. Các operator thường dùng

Reactor cung cấp nhiều operator để biến đổi Flux. Ví dụ service lọc sách đã xuất bản, đổi sang DTO và giới hạn số phần tử:

```java
public Flux<BookView> recentPublishedBooks() {
    return bookRepository.findAll()
            .filter(BookEntity::isPublished)
            .map(BookView::from)
            .take(50);
}
```

Một số operator phổ biến:

| Operator | Công dụng | Lưu ý |
| --- | --- | --- |
| `map` | Biến đổi từng phần tử đồng bộ | Hàm mapping nên nhanh và không blocking. |
| `filter` | Giữ lại phần tử thỏa điều kiện | Phần tử không phù hợp bị bỏ qua. |
| `flatMap` | Ánh xạ sang publisher khác và hợp nhất kết quả | Có thể chạy đồng thời và làm thay đổi thứ tự. |
| `concatMap` | Ánh xạ tuần tự từng phần tử sang publisher | Giữ thứ tự nhưng có thể giảm mức song song. |
| `take(n)` | Chỉ lấy tối đa n phần tử rồi complete | Hữu ích để giới hạn kết quả, nhưng không thay thế pagination cho API lớn. |
| `distinct` | Loại phần tử trùng theo equality | Có thể cần giữ trạng thái và tiêu tốn bộ nhớ. |
| `timeout` | Phát lỗi nếu không có tín hiệu trong thời gian cấu hình | Cần chọn timeout theo SLA và nguồn dữ liệu. |
| `onErrorResume` | Chuyển sang publisher dự phòng khi có lỗi | Tránh biến lỗi quan trọng thành kết quả rỗng một cách âm thầm. |
| `doFinally` | Quan sát complete, error hoặc cancel | Phù hợp cho cleanup và metrics, không phải nơi đặt nghiệp vụ chính. |

Ví dụ xử lý lỗi có chọn lọc:

```java
public Flux<Book> findBooks(String authorId) {
    return bookRepository.findByAuthorId(authorId)
            .onErrorMap(DatabaseException.class,
                    ex -> new BookCatalogUnavailableException(ex));
}
```

Exception sau đó có thể được Spring for GraphQL xử lý qua `@GraphQlExceptionHandler`, `@ControllerAdvice` hoặc `DataFetcherExceptionResolver` theo chính sách ứng dụng.

## 9. Backpressure và giới hạn tài nguyên

Reactive Streams có cơ chế backpressure: subscriber báo cho publisher biết mình sẵn sàng nhận bao nhiêu phần tử. Điều này giúp điều tiết tốc độ giữa producer và consumer khi cả chuỗi hỗ trợ Reactive Streams đúng cách.

Một vài operator hỗ trợ điều tiết:

```java
Flux<Book> stream = bookEventService.bookAddedEvents()
        .limitRate(32);
```

`limitRate(32)` điều chỉnh cách subscriber yêu cầu dữ liệu từ upstream theo nhóm; nó không phải giới hạn tổng số event mà client có thể nhận.

Với nguồn hot phát nhanh hơn tốc độ xử lý, cần chọn chính sách khi downstream không theo kịp: buffer có giới hạn, drop event, giữ event mới nhất hoặc kết thúc subscription khi vượt ngưỡng. Ví dụ buffer có giới hạn:

```java
Flux<Book> buffered = source.onBackpressureBuffer(
        100,
        dropped -> log.warn("Backpressure buffer overflow for book {}", dropped.id()));
```

Khi buffer đầy, overload này báo overflow; ứng dụng cần xử lý lỗi theo chính sách đã chọn. Không nên dùng buffer không giới hạn cho stream dài hạn vì có thể làm tăng bộ nhớ liên tục.

Backpressure chỉ điều tiết publisher/subscriber trong pipeline reactive. Nó không tự giới hạn kích thước một query list mà server phải thu thập thành một response. Với query trả về dữ liệu lớn, cần pagination, giới hạn page size và query complexity.

## 10. Lỗi và giá trị rỗng trong Flux

Flux có ba trạng thái kết thúc quan trọng:

- Complete: publisher kết thúc bình thường.
- Error: publisher kết thúc do lỗi.
- Cancel: subscriber hủy đăng ký.

Không được phát `null` trong Reactive Streams. Nếu không có phần tử, hãy dùng `Flux.empty()`; nếu cần phát lỗi, dùng `Flux.error(...)` hoặc chuyển lỗi qua operator phù hợp.

Với query field kiểu list, `Flux.empty()` được thu thập thành danh sách rỗng `[]`. Với subscription, `Flux.empty()` không phát event nào và kết thúc stream. `Flux.error(...)` làm publisher kết thúc bằng lỗi; Spring for GraphQL/GraphQL Java sẽ xử lý lỗi theo ngữ cảnh thực thi và exception resolver.

Ví dụ:

```java
public Flux<Book> booksByAuthor(String authorId) {
    if (authorId == null || authorId.isBlank()) {
        return Flux.error(new IllegalArgumentException("authorId is required"));
    }
    return bookRepository.findByAuthorId(authorId);
}
```

Không nên thay mọi lỗi bằng `Flux.empty()` chỉ để tránh response lỗi. Điều đó có thể khiến client hiểu nhầm database hoặc upstream đang gặp sự cố thành kết quả hợp lệ nhưng không có dữ liệu.

## 11. Cancellation và dọn dẹp subscription

Subscription có thể sống lâu. Client có thể hủy subscription khi người dùng rời màn hình, đóng kết nối hoặc không còn cần dữ liệu. Khi transport truyền cancellation xuống Reactive Streams, Flux upstream có thể dừng công việc và giải phóng tài nguyên.

Ví dụ theo dõi vòng đời:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

public Flux<Book> bookAddedEvents() {
    return eventSource.events()
            .doFinally(signal -> {
                if (signal == SignalType.CANCEL) {
                    metrics.recordSubscriptionCancelled("bookAdded");
                }
            });
}
```

`doFinally` được gọi khi stream complete, error hoặc cancel. Dùng nó cho metrics, đóng resource hoặc cleanup gắn với subscription. Không dùng field mutable trong singleton controller để lưu trạng thái riêng của từng subscriber.

Nếu nguồn event mở connection hoặc đăng ký listener bên ngoài, cần bảo đảm cancellation đóng listener/connection tương ứng. Nếu không, người dùng đã unsubscribe nhưng server vẫn tiếp tục giữ tài nguyên.

## 12. Bảo mật và phạm vi dữ liệu của Subscription

Subscription tạo một luồng kết nối kéo dài, vì vậy cần kiểm tra quyền ở cả thời điểm đăng ký và trong phạm vi dữ liệu được phát ra:

1. Xác thực người dùng khi bắt đầu subscription.
2. Xác định tenant, user hoặc resource mà người dùng được phép theo dõi.
3. Lọc event theo phạm vi quyền ở server trước khi phát cho client.
4. Không dựa vào `userId` hoặc `tenantId` do client tự gửi mà chưa kiểm tra quyền.
5. Theo dõi thời lượng, số lượng subscription và giới hạn tài nguyên.
6. Xác định hành vi khi token hết hạn hoặc quyền người dùng bị thu hồi.

Ví dụ lọc event theo tenant:

```java
@SubscriptionMapping
public Flux<Book> bookAdded(@Argument("tenantId") String tenantId, Principal principal) {
    tenantAccessService.requireAccess(principal.getName(), tenantId);
    return bookEventService.bookAddedEvents()
            .filter(book -> book.tenantId().equals(tenantId));
}
```

Ví dụ giả định `Principal` có mặt và service xác minh quyền truy cập tenant. Trong hệ thống thực tế, có thể lấy tenant từ security context thay vì argument; nếu nhận từ client, phải xác minh quyền trước khi tạo stream. Việc lọc event cần được thực hiện ở server, không gửi mọi event cho client rồi để client tự lọc.

## 13. Kiểm thử Flux và Subscription

Có hai lớp kiểm thử khác nhau:

- Kiểm thử service publisher bằng `StepVerifier` để xác nhận chuỗi phát đúng giá trị, thứ tự, complete, error và cancellation.
- Kiểm thử GraphQL subscription qua transport hỗ trợ streaming để xác nhận schema, resolver và response event.

Ví dụ kiểm thử service:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

@Test
void bookEventsEmitExpectedBooks() {
    StepVerifier.create(bookEventService.bookAddedEvents())
            .then(() -> bookEventService.publish(book1))
            .then(() -> bookEventService.publish(book2))
            .expectNext(book1, book2)
            .thenCancel()
            .verify();
}
```

Ví dụ này giả định sink multicast đang được dùng và test đăng ký trước khi phát event. Với hot publisher, nếu phát event trước khi subscriber đăng ký thì event có thể bị bỏ lỡ.

Ví dụ kiểm thử GraphQL subscription bằng `GraphQlTester` đã được cấu hình trên WebSocket hoặc RSocket transport:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@Test
void subscriptionStreamsBookAddedEvents() {
    Flux<String> titles = graphQlTester.document("""
            subscription {
                bookAdded {
                    title
                }
            }
            """)
            .executeSubscription()
            .toFlux("bookAdded.title", String.class);

    StepVerifier.create(titles)
            .then(() -> bookEventService.publish(book1))
            .expectNext(book1.title())
            .thenCancel()
            .verify();
}
```

Test cần đồng bộ thời điểm subscription đã được thiết lập trước khi publish event; trong test integration có thể dùng latch hoặc tín hiệu xác nhận subscriber đăng ký. Đừng phụ thuộc vào timing ngẫu nhiên bằng cách phát event ngay khi tạo publisher nếu chưa chắc client đã subscribe.

## 14. Lỗi thường gặp khi dùng Flux

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Query không trả response | Flux của query không bao giờ complete | Chỉ dùng Flux hữu hạn cho list query; dùng Subscription cho stream dài hạn. |
| Client nhận một mảng thay vì event liên tục | Flux đang được dùng ở field query/list thông thường | Khai báo root `Subscription` và dùng `@SubscriptionMapping`. |
| Subscription không nhận event | Nguồn hot phát trước khi subscriber đăng ký hoặc transport chưa hỗ trợ subscription | Kiểm tra lifecycle, WebSocket/RSocket transport và chính sách replay. |
| Subscriber nhận event của tenant khác | Thiếu filter/authorization theo subscriber | Kiểm tra quyền và lọc event ở server. |
| Bộ nhớ tăng theo thời gian | Buffer không giới hạn hoặc subscriber chậm | Chọn bounded buffer/drop policy và giám sát lag. |
| Event bị mất khi reconnect | Stream chỉ phát event mới, không có replay/durable offset | Dùng event store/broker có replay hoặc query snapshot kết hợp subscription. |
| Blocking làm chậm cả hệ thống | Gọi JDBC hoặc API đồng bộ trên reactive thread | Dùng reactive client hoặc tách blocking work sang scheduler phù hợp. |
| Lỗi bị biến thành danh sách rỗng | `onErrorResume` fallback quá rộng | Chỉ xử lý lỗi dự kiến và giữ nguyên lỗi hệ thống cần báo. |
| Tài nguyên không được giải phóng sau unsubscribe | Không xử lý cancellation của upstream | Dùng `doFinally` hoặc `usingWhen` để cleanup đúng vòng đời. |

## 15. Checklist sử dụng Flux trong Spring for GraphQL

1. Dùng `Flux<T>` khi cần phát từ 0 đến nhiều phần tử; dùng `Mono<T>` cho 0 hoặc 1 kết quả.
2. Nhớ rằng `Flux` là kiểu Java, còn SDL vẫn khai báo list/object theo contract GraphQL.
3. Với Query và field list thông thường, chỉ trả Flux hữu hạn vì server cần thu thập thành một response.
4. Với event stream dài hạn, khai báo root `Subscription` và dùng `@SubscriptionMapping`.
5. Cấu hình WebSocket hoặc RSocket transport cho subscription theo môi trường.
6. Dùng reactive repository/client để tránh blocking trên reactive pipeline.
7. Chọn cold/hot semantics, replay và buffering theo yêu cầu event.
8. Giới hạn tài nguyên, backpressure và kích thước query list.
9. Xử lý error, complete và cancellation có chủ đích.
10. Xác thực và lọc event theo quyền của từng subscriber.
11. Kiểm thử publisher bằng `StepVerifier` và subscription qua transport thực tế.

`Flux` giúp Spring for GraphQL tích hợp các nguồn dữ liệu reactive. Với query list, nó là cách cung cấp nhiều phần tử bất đồng bộ cho một response; với subscription, nó là nguồn phát nhiều response theo thời gian. Chọn đúng loại operation, quản lý backpressure và cancellation, đồng thời bảo vệ từng subscriber sẽ giúp ứng dụng xử lý luồng dữ liệu hiệu quả và ổn định.

Tài liệu tham khảo: [Spring for GraphQL — Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html) và [Project Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/).
