# Giữ hợp đồng Publisher xuyên controller, dịch vụ và truy cập dữ liệu trong Spring WebFlux

## 1. Mục tiêu: một chuỗi reactive xuyên suốt

Trong một ứng dụng Spring WebFlux, controller, service và tầng truy cập dữ liệu không nên là ba thế giới thực thi tách biệt. Chúng nên **trả về và kết hợp các Publisher** trong cùng một luồng xử lý, từ HTTP request đến database và từ database trở lại HTTP response.

Ví dụ kiến trúc:

~~~text
HTTP GET /api/books/42
           |
           v
BookController.get(id)
           | Mono<BookView>
           v
BookService.findById(id)
           | Mono<Book>
           v
BookRepository.findById(id)
           | Mono<Book>
           v
R2DBC driver + database
           |
           +--- 1 Book -------> map(BookView::from) ---> HTTP 200 + JSON
           +--- empty --------> switchIfEmpty(...) ---> HTTP 404
           +--- onError ------> error handling -------> HTTP lỗi phù hợp
~~~

Mỗi tầng **mô tả một pipeline**; HTTP runtime của WebFlux sẽ subscribe khi cần thực hiện request/response. Không tầng nào phải tự gọi `subscribe()` để kích hoạt tầng tiếp theo, không tầng nào phải gọi `block()` để đổi dữ liệu reactive thành giá trị đồng bộ.

Cụm từ “giữ hợp đồng Publisher” có hai ý nghĩa:

1. **Hợp đồng kiểu dữ liệu:** method trả về `Mono<T>`, `Flux<T>` hoặc `Publisher<T>` đúng cardinality, không giả vờ đồng bộ bằng một object lấy ra từ `block()`.
2. **Hợp đồng thực thi:** giữ các tín hiệu `onNext`, `onError`, `onComplete`, yêu cầu demand, cancellation và Reactor Context trong cùng subscription, không tạo một subscription “rơi” ở giữa.

Sử dụng reactive API ở controller nhưng chạy JDBC/JPA blocking trên event-loop sẽ **không** tạo ra một chuỗi non-blocking thực sự. Cần nhìn toàn bộ các tầng và thư viện mà chúng gọi.

## 2. Publisher, Mono và Flux là gì?

Reactive Streams quy định giao thức giữa Publisher và Subscriber. Publisher phát dữ liệu theo nhu cầu của Subscriber thông qua Subscription; các tín hiệu quan trọng là:

- `onSubscribe(subscription)`: Subscriber nhận Subscription.
- `request(n)`: Subscriber yêu cầu tối đa n phần tử tiếp theo.
- `onNext(item)`: phát một phần tử hợp lệ.
- `onError(error)`: kết thúc bất thường.
- `onComplete()`: kết thúc bình thường.
- `cancel()`: ngừng tiêu thụ và yêu cầu hủy pipeline.

Project Reactor cung cấp hai kiểu chính:

| Loại | Số phần tử | Trường hợp phù hợp |
| --- | --- | --- |
| `Mono<T>` | 0 hoặc 1 | Tìm một bản ghi, lưu một entity, trả một DTO |
| `Flux<T>` | 0 đến N | Liệt kê bản ghi, stream thay đổi, đọc nhiều dòng |
| `Mono<Void>` | Không phát giá trị | Thao tác chỉ cần tín hiệu hoàn tất hoặc lỗi |
| `Publisher<T>` | Giao diện tổng quát | Ranh giới trừu tượng giữa thư viện reactive |

Ví dụ:

~~~java
Mono<Book> one = repository.findById(42L);
Flux<Book> all = repository.findAll();
Mono<Void> completed = repository.deleteById(42L);
~~~

`Mono.empty()` không có nghĩa là `null`. Mono không được phát một phần tử null; giá trị vắng mặt được diễn đạt bằng tín hiệu complete mà không có `onNext`.

Trong một API:

- Một bản ghi tồn tại: `Mono<Book>` phát một Book rồi complete.
- Không tìm thấy: `Mono<Book>` complete rỗng; service/controller cần quyết định thành 404, 204 hoặc kết quả khác.
- Nhiều bản ghi: `Flux<Book>` phát lần lượt các bản ghi.
- Lỗi database: Publisher phát `onError`, không tự động biến thành empty hay 404.

## 3. Hợp đồng đi qua từng tầng

### Tầng repository

Repository dùng Spring Data R2DBC:

~~~java
public interface BookRepository
        extends ReactiveCrudRepository<Book, Long> {

    Flux<Book> findByPriceCentsLessThanEqual(int maxPriceCents);
}
~~~

`findById(id)` trả `Mono<Book>`, `findAll()` trả `Flux<Book>`, `save(book)` trả `Mono<Book>`. Khi gọi các method này, ta nhận Publisher mô tả việc truy cập dữ liệu; đây không phải một bản ghi Java đã được lấy ra ngay lập tức.

### Tầng service

Service compose Publisher và chuyển entity sang DTO:

~~~java
public Mono<BookView> findById(long id) {
    return repository.findById(id)
        .map(BookView::from);
}

public Flux<BookView> findAll() {
    return repository.findAll()
        .map(BookView::from);
}
~~~

`map` là phép biến đổi đồng bộ ngắn và không blocking trên mỗi phần tử. Nó giữ nguyên số lượng tín hiệu dữ liệu, cùng lifecycle và cùng luồng lỗi của Publisher.

### Tầng controller

Controller trả Publisher cho Spring WebFlux:

~~~java
@GetMapping("/{id}")
public Mono<BookView> get(@PathVariable long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "Book not found")
        ));
}

@GetMapping
public Flux<BookView> list() {
    return service.findAll();
}
~~~

Controller không cần tự serialize JSON bằng Jackson. WebFlux sử dụng HTTP message codecs để encode các giá trị được Publisher phát ra, với media type phù hợp. Controller không gọi `block()` để lấy BookView rồi trả value đồng bộ.

## 4. Lazy execution: ai sẽ subscribe?

Khi service trả:

~~~java
Mono<BookView> result = repository.findById(42L)
    .map(BookView::from);
~~~

nó đang trả một mô tả công việc. Đối với Publisher cold điển hình của R2DBC/Reactor, truy vấn được thực hiện khi pipeline được subscribe.

Với WebFlux annotation controller:

~~~java
@GetMapping("/{id}")
public Mono<BookView> get(@PathVariable long id) {
    return service.findById(id);
}
~~~

Spring WebFlux tiếp nhận Publisher, kết hợp với HTTP response writer và subscribe theo vòng đời request. Không nên thêm:

~~~java
service.findById(id).subscribe();
return Mono.empty();
~~~

Đây là lỗi nghiêm trọng:

- Controller trả về một Mono rỗng, tách khỏi tác vụ đã chạy.
- Lỗi trong subscription riêng không còn được chuyển thành HTTP response như mong muốn.
- Cancellation khi client ngắt kết nối không điều khiển subscription riêng.
- Reactor Context, security context và transaction có thể không còn được liên kết đúng.
- Request có thể kết thúc trước khi truy vấn hoàn tất.

**Quy tắc:** compose và **return** Publisher. Chỉ subscribe ở biên của ứng dụng: HTTP runtime, scheduled job hoặc consumer được thiết kế để sở hữu vòng đời subscription.

## 5. Chọn toán tử đúng để không làm đứt pipeline

| Nhu cầu | Toán tử | Kiểu trả về ví dụ |
| --- | --- | --- |
| Biến một Book thành DTO | `map` | `Mono<BookView>` |
| Gọi một tác vụ async phụ thuộc Book | `flatMap` | `Mono<Details>` |
| Phát nhiều giá trị từ một giá trị | `flatMapMany` | `Flux<Item>` |
| Chuyển từng item thành Publisher và giữ thứ tự | `concatMap` | `Flux<Result>` |
| Lọc phần tử | `filter` | `Flux<T>` |
| Thay Publisher rỗng bằng lựa chọn khác | `switchIfEmpty` | `Mono<T>` |
| Biến lỗi thành lỗi khác | `onErrorMap` | `Mono<T>` hoặc `Flux<T>` |
| Fallback khi lỗi thật sự cho phép | `onErrorResume` | `Mono<T>` hoặc `Flux<T>` |
| Ghi side-effect quan sát | `doOnNext`, `doOnError` | Giữ kiểu và tín hiệu |
| Đợi tác vụ rồi giữ giá trị | `thenReturn` | `Mono<T>` |
| Chỉ quan tâm kết thúc | `then` | `Mono<Void>` |
| Kết hợp tác vụ đơn độc lập | `Mono.zip` | `Mono<Tuple2<...>>` |

Ví dụ chuyển đổi đồng bộ:

~~~java
return repository.findById(id)
    .map(book -> new BookView(
        book.id(),
        book.title(),
        book.priceCents()
    ));
~~~

Ví dụ gọi Publisher khác theo giá trị vừa đọc:

~~~java
return repository.findById(id)
    .flatMap(book -> inventoryClient.get()
        .uri("/stock/{id}", book.id())
        .retrieve()
        .bodyToMono(Stock.class)
        .map(stock -> new BookWithStock(book, stock)));
~~~

Điểm khác biệt:

- `map` dùng khi lambda trả về một giá trị cụ thể, không phải Publisher.
- `flatMap` dùng khi lambda trả về một `Mono<R>`.
- `flatMapMany` hữu ích khi một Mono mở rộng thành nhiều phần tử Flux.
- Dùng `map(book -> repository.save(book))` sẽ tạo `Mono<Mono<Book>>`; Publisher lồng bên trong không được tự động thực thi như kỳ vọng.
- Dùng `flatMap(book -> repository.save(book))` sẽ tạo một `Mono<Book>` phẳng và thực thi save khi subscribe.

## 6. Empty, 404, lỗi và mã trạng thái HTTP

Phải phân biệt ba trường hợp:

~~~text
findById(42)
  |
  +-- onNext(Book) + onComplete --> HTTP 200
  |
  +-- onComplete() không có item --> HTTP 404 theo policy của API
  |
  +-- onError(databaseFailure) --> HTTP 5xx hoặc lỗi được ánh xạ phù hợp
~~~

Repository trả `Mono.empty()` cho “không tìm thấy” là hợp lý. Controller có thể chuyển trường hợp này thành 404:

~~~java
return service.findById(id)
    .switchIfEmpty(Mono.error(
        new ResponseStatusException(HttpStatus.NOT_FOUND, "Book not found")
    ));
~~~

Đừng áp dụng một `onErrorResume(e -> Mono.empty())` chung cho mọi lỗi database. Nó biến “database mất kết nối” thành “không có dữ liệu”, làm sai semantics và che mất sự cố vận hành.

Nếu cần thay status và headers sau một thao tác async, WebFlux hỗ trợ:

~~~java
public Mono<ResponseEntity<BookView>> get(long id) {
    return service.findById(id)
        .map(ResponseEntity::ok)
        .switchIfEmpty(Mono.just(ResponseEntity.notFound().build()));
}
~~~

Đây là đoạn minh họa kiểu phản hồi; ở chương trình hoàn chỉnh bên dưới dùng `ResponseStatusException` để đơn giản và dễ test.

### Giá trị null không được phát qua Publisher

Sai:

~~~java
Mono.just(null);
~~~

Đúng khi giá trị có thể null:

~~~java
Mono.justOrEmpty(nullableValue);
~~~

Hoặc từ database, giữ nguyên `Mono.empty()` và xử lý ở đúng tầng. Không dùng “DTO rỗng” làm giả giá trị không tìm thấy nếu hợp đồng API quy định HTTP 404.

## 7. Tránh block() và subscribe() trong các tầng ứng dụng

### Sai: block() trong service

~~~java
public BookView findById(long id) {
    Book book = repository.findById(id).block();
    return BookView.from(book);
}
~~~

Khi gọi trên Netty event-loop, `block()` có thể bị Reactor từ chối hoặc làm nghẽn xử lý I/O. Dù chạy được ở thread khác, nó vẫn phá ý nghĩa non-blocking và gây khó khăn cho timeout, cancellation, context và transaction.

Cách đúng:

~~~java
public Mono<BookView> findById(long id) {
    return repository.findById(id).map(BookView::from);
}
~~~

### Sai: tự subscribe vào thao tác ghi

~~~java
public Mono<Void> create(Book book) {
    repository.save(book).subscribe();
    return Mono.empty();
}
~~~

HTTP request có thể kết thúc trước thao tác save; lỗi ghi không được truyền cho caller. Nếu request bị hủy, save vẫn có thể chạy trong subscription riêng.

Cách đúng:

~~~java
public Mono<Book> create(Book book) {
    return repository.save(book);
}
~~~

### Sai: Future/Publisher lồng nhau không được flatten

~~~java
Mono<Mono<Book>> nested = Mono.just(id)
    .map(repository::findById);
~~~

Cách đúng:

~~~java
Mono<Book> flat = Mono.just(id)
    .flatMap(repository::findById);
~~~

Đừng gọi `toFuture().join()` hoặc `Future.get()` chỉ để lấy dữ liệu rồi wrap lại bằng `Mono.just(...)`.

## 8. R2DBC thật sự reactive; JDBC và JPA là blocking

Spring Data R2DBC sử dụng R2DBC `ConnectionFactory` và driver tương thích reactive. Các repository như `ReactiveCrudRepository` tạo Publisher để tương tác với cơ sở dữ liệu.

Ngược lại, Spring Data JPA/JDBC tiêu chuẩn là API blocking. Đổi:

~~~java
Book book = jpaRepository.findById(id).orElseThrow();
return Mono.just(book);
~~~

thành một method trả `Mono<Book>` **không** làm lời gọi JPA non-blocking. Lệnh DB đã được thực hiện đồng bộ trước khi Mono được tạo.

Ngay cả:

~~~java
Mono.fromCallable(() -> jpaRepository.findById(id).orElse(null))
~~~

vẫn chạy synchronous code trên thread của subscriber nếu không chuyển scheduler. Nếu bắt buộc tích hợp thư viện blocking tạm thời, cô lập nó:

~~~java
Mono<Book> legacyResult = Mono.fromCallable(
        () -> legacyDao.findById(id)
    )
    .subscribeOn(Schedulers.boundedElastic());
~~~

Cách này chuyển blocking work sang bounded elastic threads, không biến JDBC thành R2DBC và không bảo đảm transaction imperative được truyền qua các scheduler. Cần giới hạn concurrency, thời gian chờ và connection pool cho nguồn blocking. Đối với luồng non-blocking xuyên suốt, ưu tiên driver và client reactive thực sự.

## 9. Một request có thể cần nhiều nguồn Publisher

Service thường kết hợp DB và HTTP downstream:

~~~java
public Mono<BookDetails> details(long id) {
    return repository.findById(id)
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND)
        ))
        .flatMap(book -> webClient.get()
            .uri("/stock/{id}", book.id())
            .retrieve()
            .bodyToMono(Stock.class)
            .map(stock -> new BookDetails(
                book.id(),
                book.title(),
                stock.available()
            )));
}
~~~

Như vậy:

- Không cần tự subscribe kết quả repository.
- HTTP call downstream chỉ được thực hiện khi tìm thấy Book.
- Nếu repository rỗng, nhánh WebClient không chạy.
- Nếu WebClient lỗi, lỗi được phát trong cùng pipeline.
- Nếu caller hủy request, cancellation được chuyển về các publisher đang active trong khả năng của từng adapter.

Với hai nguồn độc lập, có thể dùng `Mono.zip`:

~~~java
Mono<Profile> profile = profileClient.find(userId);
Mono<Settings> settings = settingsRepository.findByUserId(userId);

Mono<UserView> view = Mono.zip(profile, settings)
    .map(tuple -> new UserView(tuple.getT1(), tuple.getT2()));
~~~

Lưu ý: nếu một nguồn Mono hoàn tất rỗng, `zip` có thể hoàn tất mà không phát giá trị; nó không tự chuyển thành “hàng dữ liệu rỗng”. Muốn cung cấp default, xử lý ở mỗi Publisher trước khi zip.

## 10. Transactions reactive phải nằm trong cùng Reactor Context

Khi làm nhiều thao tác R2DBC cần tính nguyên tử, Spring có thể dùng `R2dbcTransactionManager` và `@Transactional` cho method trả Publisher.

Ví dụ minh họa hai repository reactive trong service:

~~~java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final AuditRepository audits;

    public OrderService(
            OrderRepository orders,
            AuditRepository audits) {
        this.orders = orders;
        this.audits = audits;
    }

    @Transactional
    public Mono<Order> place(Order order) {
        return orders.save(order)
            .flatMap(saved -> audits
                .save(new Audit(null, saved.id(), "CREATED"))
                .thenReturn(saved));
    }
}
~~~

Trong ví dụ, `OrderRepository`, `AuditRepository`, `Order` và `Audit` là các loại minh họa của một ứng dụng lớn hơn, không thuộc project runnable ở mục 13.

Điểm cốt lõi:

- Method cần trả Publisher để reactive transaction interceptor áp dụng.
- `ReactiveTransactionManager` dùng **Reactor Context**, không dựa vào ThreadLocal như transaction imperative thông thường.
- Các thao tác R2DBC liên quan phải chạy trong cùng reactive pipeline và cùng transaction context.
- Đừng gọi `subscribe()` riêng bên trong method: subscription mới không nhất thiết tham gia transaction đang được cấu hình.
- Khi reactive transaction publisher phát lỗi, manager rollback theo quy tắc transaction.
- Cancellation từ Spring Framework 5.3 dẫn đến rollback trong reactive transaction; cần thận trọng với `take()`, `next()` và timeout khiến một transaction Flux bị cancel sớm.
- Không gộp HTTP call tới hệ thống khác vào database transaction rồi mặc định cho rằng nó được rollback cùng database. HTTP và DB không cùng atomic boundary nếu không có cơ chế phối hợp đặc biệt.

Nếu cần transaction programmatic:

~~~java
Mono<Order> saved = orders.save(order)
    .flatMap(savedOrder -> audits
        .save(new Audit(null, savedOrder.id(), "CREATED"))
        .thenReturn(savedOrder))
    .as(transactionalOperator::transactional);
~~~

`TransactionalOperator` áp dụng transaction cho publisher. Nó không thay thế việc cấu hình reactive transaction manager và không làm side effect ngoài DB trở thành transactional.

## 11. Request body và response body đều là Publisher

WebFlux có thể nhận một request body async:

~~~java
@PostMapping("/books")
public Mono<BookView> create(
        @RequestBody Mono<CreateBookRequest> body) {

    return body.flatMap(service::create);
}
~~~

Ở đây client gửi JSON; WebFlux decode thành `Mono<CreateBookRequest>`. Service chỉ chạy khi request body phát ra một value.

Với body nhiều phần tử, có thể dùng `Flux<T>` khi giao thức và codec hỗ trợ. Ví dụ streaming:

~~~java
@PostMapping(
    path = "/books/import",
    consumes = MediaType.APPLICATION_NDJSON_VALUE
)
public Mono<Long> importMany(
        @RequestBody Flux<CreateBookRequest> body) {

    return body
        .concatMap(service::create)
        .count();
}
~~~

Đây là ví dụ về pattern xử lý lần lượt và đếm kết quả; nó **không** phải một transaction atomic cho toàn bộ import. Nếu item thứ ba lỗi sau khi hai item đầu đã lưu, hai item đầu có thể đã commit. Muốn all-or-nothing, cần transaction reactive có phạm vi phù hợp và test hành vi rollback.

Ở chiều response:

~~~java
@GetMapping(
    path = "/books/stream",
    produces = MediaType.APPLICATION_NDJSON_VALUE
)
public Flux<BookView> stream() {
    return service.list(null);
}
~~~

Với response JSON hữu hạn thông thường, `Flux<T>` có thể được codec gom thành một JSON array; với NDJSON, từng JSON record được encode theo streaming media type. Đừng nhầm “return Flux” với cam kết response luôn flush mỗi bản ghi trong mọi media type và mọi proxy.

## 12. Backpressure, cancellation và lỗi xuyên các tầng

### Backpressure

Reactive Streams cho phép Subscriber yêu cầu số lượng phần tử có thể xử lý thông qua `request(n)`. Khi API đi qua controller → service → repository mà không blocking hoặc subscribe ngoài luồng, demand có thể truyền qua các operator và adapter.

Tuy nhiên, không thể khẳng định mọi driver, network transport và database đều chỉ giữ đúng n phần tử trong memory. Buffering, fetch-size và cơ chế của R2DBC driver vẫn cần được kiểm tra khi streaming dữ liệu lớn.

Tránh:

~~~java
return repository.findAll().collectList()
    .flatMapMany(Flux::fromIterable);
~~~

Đoạn này gom toàn bộ kết quả vào list, làm mất lợi ích phát từng phần tử tại thời điểm chúng đến. Chỉ dùng `collectList()` khi nghiệp vụ thực sự cần toàn bộ collection hữu hạn.

### Cancellation

Nếu client disconnect hoặc request timeout, HTTP runtime có thể cancel publisher response. Cancellation đi qua các operator, giúp dừng xử lý đang diễn ra và giải phóng tài nguyên tùy khả năng của repository/driver.

Không tạo subscription riêng trong service vì như vậy cancellation của request không còn kiểm soát được công việc vừa tách ra.

### Error propagation

Nếu repository phát lỗi kết nối, pipeline tiếp tục bằng `onError` cho tới khi được xử lý. Với API, nên ánh xạ lỗi có ý nghĩa:

- Input không hợp lệ: HTTP 400.
- Entity không tồn tại: HTTP 404.
- Trùng khóa hoặc vi phạm ràng buộc nghiệp vụ: HTTP 409 nếu chính sách API xác định như vậy.
- Mất database hoặc sự cố downstream: HTTP 5xx phù hợp, có log và quan sát.
- Client cancel: không nên tạo side effect mới khi request đã không còn cần kết quả.

Không đưa chi tiết SQL, connection string hoặc stack trace nhạy cảm vào body response công khai.

## 13. Dự án chạy được: Spring Boot 3.5 + Java 17 + WebFlux + R2DBC H2

Ví dụ này tạo API quản lý sách:

- `GET /api/books` trả `Flux<BookView>`.
- `GET /api/books/{id}` trả `Mono<BookView>` hoặc HTTP 404.
- `GET /api/books/stream` phát NDJSON.
- `POST /api/books` nhận `Mono<CreateBookRequest>`, lưu bằng `ReactiveCrudRepository.save` và trả HTTP 201.
- Dữ liệu được lưu trong H2 in-memory qua driver R2DBC, không dùng JPA/JDBC trong request pipeline.

Cấu trúc:

~~~text
reactive-books/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/books/
    │   │   ├── ReactiveBooksApplication.java
    │   │   ├── Book.java
    │   │   ├── BookRepository.java
    │   │   ├── BookView.java
    │   │   ├── CreateBookRequest.java
    │   │   ├── BookService.java
    │   │   └── BookController.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/java/com/example/books/
        └── BookApiTest.java
~~~

### 13.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>reactive-books</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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
            <artifactId>spring-boot-starter-data-r2dbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.r2dbc</groupId>
            <artifactId>r2dbc-h2</artifactId>
            <scope>runtime</scope>
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

### 13.2. ReactiveBooksApplication.java

~~~java
package com.example.books;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveBooksApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveBooksApplication.class, args);
    }
}
~~~

### 13.3. application.properties

~~~properties
spring.r2dbc.url=r2dbc:h2:mem:///bookdb?options=DB_CLOSE_DELAY=-1
spring.r2dbc.username=sa
spring.r2dbc.password=
spring.sql.init.mode=always
~~~

Ở đây `spring.r2dbc.*` cấu hình ConnectionFactory, **không phải** `spring.datasource.*`. Spring Boot tự cấu hình R2DBC và đọc script `schema.sql`, `data.sql`. Cơ sở dữ liệu in-memory chỉ phục vụ demo; production cần driver và chiến lược migration thích hợp.

### 13.4. schema.sql và data.sql

`src/main/resources/schema.sql`:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(160) NOT NULL,
    price_cents INTEGER NOT NULL
);
~~~

`src/main/resources/data.sql`:

~~~sql
INSERT INTO books (title, price_cents)
VALUES ('Reactor nhập môn', 15000);

INSERT INTO books (title, price_cents)
VALUES ('WebFlux thực hành', 22000);
~~~

Các bản ghi seed tạo ID 1 và 2 trong database in-memory mới. Test minh họa dùng ID 1. Nếu chạy cùng DB được dùng lại giữa nhiều context, ID và dữ liệu có thể khác; production/test suite lớn nên tạo database độc lập cho từng test.

### 13.5. Book.java — Entity

~~~java
package com.example.books;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("books")
public record Book(
    @Id Long id,
    String title,
    int priceCents
) {}
~~~

Spring Data R2DBC ánh xạ trường Java `priceCents` sang cột `price_cents` theo naming strategy mặc định. Bản ghi mới có `id = null` để database cấp identity.

Entity thuộc tầng lưu trữ, không nên dùng trực tiếp để quyết định cấu trúc HTTP response trong hệ thống lớn.

### 13.6. BookRepository.java — Data access

~~~java
package com.example.books;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

import reactor.core.publisher.Flux;

public interface BookRepository
        extends ReactiveCrudRepository<Book, Long> {

    Flux<Book> findByPriceCentsLessThanEqual(int maxPriceCents);
}
~~~

Spring Data tạo implementation từ interface. `findAll` và phương thức query trả Flux; `findById` và `save` trả Mono.

### 13.7. CreateBookRequest.java — Request DTO

~~~java
package com.example.books;

public record CreateBookRequest(
    String title,
    int priceCents
) {}
~~~

DTO nhập tách khỏi entity DB. Ví dụ validation thực hiện trong service để không cần thêm starter validation.

### 13.8. BookView.java — Response DTO

~~~java
package com.example.books;

public record BookView(
    long id,
    String title,
    int priceCents
) {

    public static BookView from(Book book) {
        return new BookView(
            book.id(),
            book.title(),
            book.priceCents()
        );
    }
}
~~~

`BookView.from` là mapper đồng bộ thuần túy, nên dùng `map(BookView::from)`, không tạo Mono phụ.

### 13.9. BookService.java — Composition

~~~java
package com.example.books;

import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class BookService {

    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<BookView> findById(long id) {
        return repository.findById(id)
            .map(BookView::from);
    }

    public Flux<BookView> list(Integer maxPriceCents) {
        if (maxPriceCents != null && maxPriceCents < 0) {
            return Flux.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "maxPriceCents must be >= 0"
            ));
        }

        Flux<Book> source = maxPriceCents == null
            ? repository.findAll()
            : repository.findByPriceCentsLessThanEqual(maxPriceCents);

        return source.map(BookView::from);
    }

    public Mono<BookView> create(CreateBookRequest input) {
        if (input.title() == null
                || input.title().isBlank()
                || input.priceCents() <= 0) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "title and positive priceCents are required"
            ));
        }

        Book newBook = new Book(
            null,
            input.title().trim(),
            input.priceCents()
        );

        return repository.save(newBook)
            .map(BookView::from);
    }
}
~~~

Đáng chú ý:

- `findById` trả Mono, không block.
- `list` trả Flux cho cả danh sách và truy vấn có lọc.
- `create` trả Mono biểu diễn tác vụ lưu, không subscribe.
- Validation trả `Mono.error` / `Flux.error` khi sai, lỗi được truyền tới HTTP layer.
- DTO mapper chạy trong pipeline, không cần scheduler phụ vì đây là công việc nhẹ và đồng bộ.

### 13.10. BookController.java — HTTP boundary

~~~java
package com.example.books;

import java.net.URI;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<BookView> list(
            @RequestParam(required = false) Integer maxPriceCents) {
        return service.list(maxPriceCents);
    }

    @GetMapping(
        path = "/stream",
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<BookView> stream() {
        return service.list(null);
    }

    @GetMapping("/{id}")
    public Mono<BookView> get(@PathVariable long id) {
        return service.findById(id)
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND,
                "Book not found"
            )));
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<BookView>> create(
            @RequestBody Mono<CreateBookRequest> request) {

        return request
            .switchIfEmpty(Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Request body required"
            )))
            .flatMap(service::create)
            .map(book -> ResponseEntity
                .created(URI.create("/api/books/" + book.id()))
                .body(book));
    }
}
~~~

Ở POST, `request.flatMap(service::create)` giữ nguyên chuỗi publisher từ lúc decode JSON tới lúc database lưu xong. HTTP 201 và Location chỉ được tạo sau khi Mono từ repository phát ra entity đã lưu.

Ở GET một sách, `switchIfEmpty` biến vắng mặt thành HTTP 404; lỗi kết nối database không bị biến thành 404.

### 13.11. Chạy ứng dụng

Trong thư mục chứa pom.xml, với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Đọc sách có sẵn:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

HTTP 200 và body JSON dự kiến trong DB mới:

~~~json
{"id":1,"title":"Reactor nhập môn","priceCents":15000}
~~~

Danh sách hữu hạn:

~~~bash
curl -i http://localhost:8080/api/books
~~~

Body là một JSON array có hai sách seed. Không phụ thuộc thứ tự trả về nếu query không có ORDER BY; khi yêu cầu thứ tự ổn định, khai báo sorting rõ ràng.

Lọc sách có giá tối đa 20.000:

~~~bash
curl -i "http://localhost:8080/api/books?maxPriceCents=20000"
~~~

Tạo sách mới:

~~~bash
curl -i -X POST http://localhost:8080/api/books -H "Content-Type: application/json" -d "{\"title\":\"Java Reactive\",\"priceCents\":32000}"
~~~

Response HTTP 201, header Location trỏ đến `/api/books/{id}` và body chứa sách vừa lưu. ID được cấp bởi database nên không hard-code ID ở kết quả.

Không tìm thấy:

~~~bash
curl -i http://localhost:8080/api/books/999999
~~~

Response HTTP 404.

Đọc NDJSON:

~~~bash
curl -i -H "Accept: application/x-ndjson" http://localhost:8080/api/books/stream
~~~

Mỗi dòng là một JSON object độc lập; endpoint demo dùng nguồn DB hữu hạn. Với lưu lượng lớn, đo lường memory, driver fetch behavior và backpressure thực tế thay vì giả định chỉ cần đổi Content-Type là đủ.

### 13.12. BookApiTest.java — HTTP integration test

~~~java
package com.example.books;

import java.util.Map;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class BookApiTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsOneSeedBookThroughAllLayers() {
        client.get()
            .uri("/api/books/1")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.title").isEqualTo("Reactor nhập môn")
            .jsonPath("$.priceCents").isEqualTo(15000);
    }

    @Test
    void missingBookBecomes404() {
        client.get()
            .uri("/api/books/999999")
            .exchange()
            .expectStatus().isNotFound();
    }

    @Test
    void createsBookViaPublisher() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "title", "R2DBC cơ bản",
                "priceCents", 27000
            ))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.title").isEqualTo("R2DBC cơ bản")
            .jsonPath("$.id").isNumber();
    }

    @Test
    void rejectsInvalidPrice() {
        client.post()
            .uri("/api/books")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(Map.of(
                "title", "Invalid",
                "priceCents", 0
            ))
            .exchange()
            .expectStatus().isBadRequest();
    }
}
~~~

Chạy kiểm thử:

~~~bash
mvn test
~~~

Kiểm thử chạy qua controller, service, repository và database H2. Chúng kiểm tra không chỉ giá trị DTO mà cả mapping HTTP: 200, 201, 400 và 404.

Demo không có security để tập trung vào Publisher. Trong ứng dụng thật, hãy bổ sung Spring Security, kiểm soát quyền đọc/ghi và không trả trực tiếp lỗi SQL trong response.

## 14. Kiểm thử tín hiệu Publisher và cancellation

Ngoài WebTestClient, Reactor Test cung cấp `StepVerifier` để xác minh publisher:

~~~java
StepVerifier.create(service.findById(1L))
    .expectNextMatches(book -> book.title().equals("Reactor nhập môn"))
    .verifyComplete();
~~~

Đoạn này cần dependency `reactor-test` ở test scope, một ApplicationContext/test fixture có database và service bean, cùng import `reactor.test.StepVerifier`. Đây là snippet bổ sung, không thuộc file BookApiTest bên trên.

Để kiểm thử publisher rỗng:

~~~java
StepVerifier.create(service.findById(999999L))
    .verifyComplete();
~~~

Vì method ở service cố ý giữ `Mono.empty()` khi không tìm thấy; controller mới đổi nó thành HTTP 404.

Với service xử lý thời gian dài, test cancellation:

~~~java
StepVerifier.create(Flux.interval(Duration.ofMillis(10)))
    .expectNextCount(3)
    .thenCancel()
    .verify();
~~~

Đoạn trên minh họa tín hiệu hủy, không chứng minh driver database cụ thể đã hủy truy vấn. Muốn kiểm chứng cleanup thật, cần integration test hoặc metrics ở driver/connection pool.

## 15. Giữ Reactor Context thay vì phụ thuộc ThreadLocal

Thông tin request như trace ID, principal hoặc transaction context có thể phải đi cùng một chuỗi bất đồng bộ. Reactor Context được truyền **theo subscription**, không giống ThreadLocal gắn với một thread cố định.

Ví dụ:

~~~java
Mono<String> traced = Mono.deferContextual(ctx ->
    Mono.just("trace=" + ctx.getOrDefault("traceId", "missing"))
).contextWrite(ctx -> ctx.put("traceId", "req-42"));
~~~

Khi subscribe, Publisher phát:

~~~text
trace=req-42
~~~

Trong hệ thống có Spring Security reactive, có thể dùng `ReactiveSecurityContextHolder` hoặc cơ chế dependency-injection/controller principal theo API được hỗ trợ. Không giả định `SecurityContextHolder` ThreadLocal imperative luôn có cùng giá trị sau khi pipeline chuyển scheduler.

Đừng tạo subscription riêng ở service và kỳ vọng transaction, security hoặc tracing context từ request tự động theo sang subscription đó. Khi tích hợp MDC/logging, sử dụng context-propagation mechanism có chủ đích và cấu hình phù hợp phiên bản framework.

## 16. Những giới hạn thực tế của end-to-end reactive

Giữ Publisher xuyên các tầng là điều kiện quan trọng, nhưng chưa phải bảo đảm tuyệt đối rằng mọi thao tác đều non-blocking:

- `map` có thể chứa CPU task tốn thời gian hoặc blocking call.
- Một adapter có thể buffer toàn bộ dữ liệu nội bộ.
- Driver R2DBC có giới hạn riêng về fetch-size, cursor và cancellation.
- `flatMap` không giới hạn concurrency có thể gây quá tải DB pool hoặc downstream.
- Dùng `collectList` trên dòng dữ liệu vô hạn sẽ không hoàn tất.
- Transaction dài bao quanh một Flux streaming có thể giữ connection database lâu.
- Retry DB write không idempotent có thể tạo bản ghi trùng nếu lần trước đã commit nhưng response thất bại.
- HTTP client/server có thể buffer và flush khác nhau tùy media type và proxy.
- Lệnh JDBC/JPA không trở thành non-blocking chỉ vì được bao trong Mono.

Để kiểm chứng, theo dõi event-loop blocking, latency, memory/buffer, DB pool utilization, pending connections, error rate, cancellation và request throughput dưới tải thực tế.

## 17. Những lỗi phổ biến và cách sửa

1. **Controller trả DTO sau khi block:** chuyển sang trả Mono/Flux từ service.
2. **Service gọi subscribe rồi return Mono.empty():** thay bằng return Publisher nối trực tiếp.
3. **Repository là JPA nhưng service return Mono.just(result):** dữ liệu đã được đọc blocking; chuyển sang R2DBC nếu cần non-blocking thật.
4. **Dùng map khi lambda trả Mono:** gây nested Publisher; dùng flatMap.
5. **Dùng flatMap cho mapper đồng bộ đơn giản:** không cần thiết; dùng map.
6. **Nuốt mọi lỗi bằng onErrorResume(...Mono.empty()):** phân biệt not-found với database failure.
7. **Trả null từ mapper:** Reactor không chấp nhận null; xử lý optional/empty đúng cách.
8. **Dùng Mono.just(null):** sai; dùng Mono.justOrEmpty(value).
9. **Trả Flux khi nghiệp vụ luôn một bản ghi:** dùng Mono để thể hiện cardinality.
10. **Gom toàn bộ DB rows bằng collectList không cần thiết:** giữ Flux hoặc phân trang.
11. **Tạo subscription trong @Transactional:** có thể chạy ngoài transaction Reactor Context.
12. **Khai báo @Transactional trên method void cho R2DBC:** reactive transaction yêu cầu pipeline Publisher và manager phù hợp.
13. **Dùng imperative transaction manager cho R2DBC pipeline:** cấu hình ReactiveTransactionManager.
14. **Timeout gây cancel giữa transaction Flux:** hiểu rollback-on-cancel và xử lý phạm vi transaction.
15. **Giữ transaction qua external HTTP call:** tăng thời gian giữ DB connection, không tạo transaction phân tán tự động.
16. **Cho rằng return Flux luôn streaming từng JSON object:** media type và encoder quyết định aggregation/flush.
17. **Giới hạn backpressure bị bỏ qua do driver buffering:** phải đo hành vi driver và downstream.
18. **FlatMap concurrency không giới hạn:** chọn concurrency và connection pool phù hợp.
19. **Khai báo service trả Publisher nhưng thực hiện side effect eager trước return:** dùng defer khi cần trì hoãn tới subscription.
20. **Dùng ThreadLocal cho trace/security trong reactive chain:** ưu tiên Reactor Context và API reactive.
21. **Test chỉ gọi service rồi không subscribe:** không chắc publisher đã được thực thi; dùng StepVerifier/WebTestClient.
22. **Không test Mono.empty():** dễ biến “không tìm thấy” thành HTTP 200 rỗng ngoài ý muốn.
23. **Không xử lý client cancellation:** nguồn có thể tiếp tục tiêu tốn tài nguyên nếu tạo subscription riêng.
24. **Retry không idempotent:** có thể tạo side effect hai lần.
25. **Trộn nhiều thư viện reactive mà không hiểu adapter:** xác minh Publisher bridge vẫn giữ demand, error, context và cancellation.

## 18. Checklist thiết kế một use case mới

- Controller trả Mono/Flux hay đang block?
- Service mô tả công việc bằng Publisher và return nó chưa?
- Repository là reactive thật hay chỉ wrap JDBC/JPA?
- Kiểu Mono/Flux có phản ánh số phần tử thực tế không?
- Phân biệt empty với error ở tầng nào?
- Dùng map, flatMap, flatMapMany và concatMap đúng mục đích chưa?
- Có subscribe thủ công ở service/repository không?
- Có bước nào collectList, toFuture().join() hoặc block mà không cần không?
- Có cấu hình transaction reactive và giữ cùng Reactor Context không?
- Có xử lý rollback-on-cancel trong transaction dài không?
- Có giới hạn concurrency và quan sát DB connection pool không?
- Khi kết hợp WebClient và DB, cancellation và timeout có được propagate không?
- Có chọn Content-Type đúng cho JSON batch hay NDJSON stream không?
- Có mapping DTO tách entity DB và hợp đồng HTTP không?
- Có test 200/201/400/404, empty, error và cancellation ở tầng phù hợp không?
- Có đo hiệu năng end-to-end dưới tải thay vì chỉ nhìn chữ Mono/Flux không?

## 19. Câu hỏi tự kiểm tra

**1.** Vì sao service phải trả Mono/Flux từ repository? Để không mất tính async/lazy, error propagation và cancellation qua cùng subscription.

**2.** Ai subscribe vào Publisher trả về bởi controller WebFlux? HTTP runtime/message writer của WebFlux trong vòng đời request.

**3.** Mono.empty() có nghĩa gì? Complete mà không phát phần tử, khác null và khác onError.

**4.** Khi nào dùng map? Khi mỗi giá trị được chuyển thành giá trị khác một cách đồng bộ.

**5.** Khi nào dùng flatMap? Khi phép biến đổi trả về Mono/Publisher cần được flatten.

**6.** Mono<Mono<Book>> thường là dấu hiệu gì? Dùng map với một hàm đã trả Mono; xem xét flatMap.

**7.** Có nên dùng Mono.just(jpaRepository.findById(...)) trên event-loop không? Không; lời gọi JPA blocking đã chạy ngay trước khi Mono được tạo.

**8.** Nếu bắt buộc gọi thư viện blocking thì làm gì? Cô lập vào boundedElastic với fromCallable/subscribeOn và kiểm soát tài nguyên, coi đó là giải pháp chuyển tiếp.

**9.** Reactive transaction giữ state ở đâu? Trong Reactor Context; không phụ thuộc hoàn toàn ThreadLocal.

**10.** Tại sao tự subscribe trong @Transactional nguy hiểm? Tạo subscription mới có thể không có cùng transaction context.

**11.** Cancel một transaction reactive có thể dẫn tới điều gì? Rollback theo chính sách reactive transaction Spring Framework.

**12.** Return Flux<BookView> với application/json có luôn flush mỗi item không? Không; có thể serialize thành JSON array. Muốn streaming record, dùng NDJSON/SSE thích hợp.

**13.** Vì sao không dùng onErrorResume để biến mọi lỗi thành empty? Vì lỗi hạ tầng khác “không có dữ liệu”.

**14.** Khi nào dùng collectList? Khi business logic cần collection hữu hạn; không dùng vô điều kiện cho dữ liệu lớn/vô hạn.

**15.** Test nào xác nhận HTTP mapping và status? WebTestClient integration test; StepVerifier xác minh tín hiệu Publisher trong test tầng reactive.

**Ghi nhớ:** Hợp đồng Publisher trong Spring WebFlux phải được giữ xuyên controller, service và truy cập dữ liệu. Tầng repository trả Mono/Flux, service compose bằng operator, controller return Publisher cho WebFlux subscribe. Giữ empty/error/cancel/context trong cùng pipeline, không chèn block() hoặc subscribe() giữa đường, và không nhầm JDBC/JPA blocking với R2DBC reactive. Reactive transaction chỉ nhất quán khi dữ liệu và thao tác tham gia cùng Reactor Context; kiểm thử cả hành vi API lẫn tín hiệu Publisher.

**Tài liệu chính thức:**
- [Spring Framework 6.2 — WebFlux @ResponseBody và reactive return types](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responsebody.html)
- [Spring Framework 6.2 — ResponseEntity và Mono/Flux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/responseentity.html)
- [Spring Data Relational — R2DBC Repositories](https://docs.spring.io/spring-data/relational/reference/r2dbc/repositories.html)
- [Spring Boot 3.5 — Using R2DBC](https://docs.spring.io/spring-boot/3.5/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html)
- [Spring Framework 6.2 — Reactive @Transactional](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — TransactionalOperator](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/).