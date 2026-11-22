# Tải dữ liệu từ kho không reactive và hệ quả khi tích hợp vào Spring WebFlux

> **Bối cảnh:** Spring Boot web runtime, menu cha **Thực thi reactive**. Bài phân tích việc HTTP handler trả `Mono`/`Flux` nhưng phải đọc dữ liệu từ kho có API **đồng bộ, chặn thread**, chẳng hạn JDBC, JPA/Hibernate, SDK đọc file, thư viện tìm kiếm hoặc HTTP client đồng bộ. Ví dụ chạy dùng Spring Boot **4.1.2**, Java **17+**, Maven và H2 qua `JdbcTemplate`. Các nguyên lý áp dụng cho Spring Boot 3.x, nhưng cần chọn starter/phiên bản tương ứng.

## Mục tiêu học tập

Sau bài này, bạn sẽ:

1. Giải thích vì sao **reactive controller không biến một repository blocking thành nguồn non-blocking**, kể cả khi chữ ký trả `Mono<T>` hoặc `Flux<T>`.
2. Chỉ rõ tác động khi gọi JDBC/JPA ngay trên **event loop** của WebFlux: latency, thông lượng, thời gian chờ, tài nguyên thread và nghẽn dây chuyền.
3. Dùng đúng mẫu `Mono.fromCallable(() -> blockingRepository.find(...)).subscribeOn(Schedulers.boundedElastic())`, hiểu rõ phần nào vẫn blocking.
4. Ràng buộc tải theo **database connection pool**, số truy vấn đồng thời, queue, backpressure, timeout và kích thước dữ liệu.
5. Xử lý đúng empty, exception, cancellation và **ranh giới transaction** khi đi từ Reactor sang repository imperative.
6. Chọn hợp lý giữa **cầu nối blocking tạm thời**, Spring MVC phù hợp với workload blocking, hoặc chuyển sang driver reactive thực sự như R2DBC.

## 1. “Kho không reactive” là gì?

**Kho dữ liệu không reactive** trong bài là một nguồn truy cập dữ liệu được expose qua API **imperative/synchronous**: lời gọi chỉ trả kết quả sau khi đã hoàn tất hoặc ném exception. Khi đang chờ, thread gọi có thể phải đứng yên.

Những ví dụ quen thuộc:

| Công nghệ/API | Chữ ký minh họa | Tính chất cần hiểu |
| --- | --- | --- |
| JDBC, `JdbcTemplate` | `Book findById(long id)` hoặc `List<Book> findAll()` | Chờ lấy connection, gửi SQL, nhận kết quả; sử dụng thread gọi để chờ |
| Spring Data JPA/Hibernate | `Optional<Book> findById(Long id)` | Repository imperative; lazy loading và transaction/JPA session là vấn đề riêng |
| Spring Data JDBC | `CrudRepository<T, ID>` trả đối tượng/collection | ORM nhỏ hơn JPA nhưng vẫn xây trên JDBC blocking |
| HTTP client đồng bộ | `restClient.get()...body(...)` | Thread chờ network I/O |
| File/SDK legacy | `InputStream.read()`, thư viện chỉ có synchronous API | Thread chờ I/O hoặc tài nguyên khác |
| R2DBC/Spring Data R2DBC | `Mono<T> findById(ID id)` | Mô hình truy cập SQL reactive, **nếu driver và chuỗi I/O thực sự hỗ trợ** |

**Reactive Streams** là hợp đồng `Publisher`, `Subscriber`, `Subscription` với tín hiệu yêu cầu dữ liệu, phát giá trị, hoàn tất, lỗi và hủy. Nó không tự biến mọi lệnh được bọc thành I/O non-blocking. Nếu `JdbcTemplate.query(...)` vẫn chờ phản hồi DB theo cách synchronous, thì JDBC vẫn chiếm một thread trong suốt thời gian chờ, dù nó nằm trong `Mono`.

Cần phân biệt ba thuật ngữ:

- **Non-blocking I/O:** việc chờ network/disk không buộc một thread ứng dụng đứng yên; hệ thống nhận thông báo khi có thể tiếp tục.
- **Asynchronous execution:** công việc chạy lệch thời điểm hoặc trên thread khác; công việc ấy **có thể vẫn blocking**.
- **Reactive API:** trình bày chuỗi tính toán dưới dạng Publisher/operator với demand, error và cancel; bản thân kiểu trả về không bảo đảm toàn bộ nguồn dữ liệu là non-blocking.

Cầu nối `boundedElastic` giúp tách công việc synchronous khỏi event loop, nhưng **không thay JDBC bằng R2DBC**.

## 2. Vì sao WebFlux nhạy cảm với lệnh blocking?

Spring WebFlux được thiết kế cho request pipeline không chặn. Trong triển khai thường gặp với Reactor Netty, có **một số lượng nhỏ event-loop thread** nhận sự kiện kết nối, xử lý callback I/O và tiếp tục pipeline.

Nếu một handler chạy truy vấn JDBC trực tiếp trên event loop:

~~~java
// SAI: minh họa trong WebFlux controller; repository.findById dùng JDBC blocking.
@GetMapping("/api/books/{id}")
Mono<Book> get(@PathVariable long id) {
    Book book = repository.findById(id); // block event-loop thread
    return Mono.justOrEmpty(book);       // Mono được tạo sau khi query đã xong
}
~~~

Khi SQL mất 300 ms, event-loop thread có thể bị giữ ở điểm gọi JDBC trong khoảng thời gian đó. Trong khi chờ, thread không xử lý được công việc khác đã đến lượt nó. Khi nhiều request đồng thời chờ DB, timeout, độ trễ đuôi (p95/p99) và queue có thể tăng mạnh.

So sánh:

~~~text
KHÔNG AN TOÀN (JDBC ngay trên event loop)

Reactor Netty event loop
  -> route/controller
  -> JDBC query: WAIT 300 ms  [event-loop bị giữ]
  -> tạo Mono/response
  -> trả bytes

PHÙ HỢP HƠN KHI CHƯA THỂ ĐỔI JDBC

Reactor Netty event loop
  -> route/controller -> tạo Mono.fromCallable(...).subscribeOn(...)
  -> trả Publisher cho WebFlux
  -> event loop tiếp tục xử lý việc khác

boundedElastic worker
  -> lấy JDBC connection -> chạy SQL -> map kết quả
  -> onNext/onComplete hoặc onError về pipeline
  -> WebFlux ghi HTTP response
~~~

Đường thứ hai giải phóng event loop trong lúc chờ DB; **boundedElastic worker vẫn bị chiếm** và connection JDBC vẫn là tài nguyên hữu hạn.

### Những hậu quả cụ thể khi làm sai

- **Head-of-line blocking:** một request chậm giữ thread và làm chậm những request khác ngay cả khi chúng không đụng database.
- **Tail latency xấu:** p95/p99 tăng nhanh trước khi CPU thật sự bận, vì phần lớn thời gian đang chờ I/O.
- **Thread starvation:** nhiều event loop bị giữ; request đọc headers, đọc body, viết response, ping/health check cũng chậm.
- **Connection starvation:** nhiều truy vấn đồng thời hơn số connection có sẵn khiến thời gian đợi pool kéo dài, dù đã offload.
- **Không còn lợi thế mở rộng với ít thread:** nếu toàn workload blocking, throughput cuối cùng bị giới hạn bởi số worker và số connection.
- **Tải không được điều tiết tốt:** một queue lớn hấp thụ lượng request đến nhưng chỉ dời thời điểm xảy ra timeout và có thể tăng bộ nhớ.

Một phép nhẩm để tư duy tải: nếu trung bình 50 yêu cầu/giây thực sự thực hiện một truy vấn **200 ms**, hệ thống cần khoảng **10 truy vấn đồng thời** chỉ để theo kịp nhu cầu lý tưởng, chưa tính độ lệch latency, queue và tài nguyên khác. Nếu pool chỉ có 5 connection, tăng threads lên hàng trăm không làm DB xử lý được 10 query cùng lúc. Đây là mô hình ước lượng, không phải dự báo benchmark.

## 3. Bọc blocking repository đúng cách

Mẫu chuẩn của Reactor:

~~~java
Mono<Book> result = Mono.fromCallable(() -> repository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
~~~

**Tại sao đúng?**

1. `Mono.fromCallable(...)` **trì hoãn lời gọi** đến lúc có subscription. JDBC chưa chạy khi controller đang xây pipeline.
2. `subscribeOn(Schedulers.boundedElastic())` chuyển subscription và thao tác ở nguồn callable sang worker dành cho công việc blocking.
3. `Mono` phát **một** kết quả rồi hoàn tất; nếu callable trả `null` thì Mono hoàn tất rỗng; nếu callable ném exception thì phát `onError`.
4. WebFlux sở hữu subscription HTTP; controller **trả** Publisher và không tự `subscribe()`.
5. Khi callback hoàn tất, phần còn lại của chuỗi Reactor tiếp tục theo scheduler context thích hợp; không giả định mọi operator tự động chạy trên event loop.

**Điều không xảy ra:** thread đang thực thi JDBC không biến mất; nó vẫn chờ result set hoặc connection. Backpressure cũng không thể yêu cầu một lệnh `queryForObject` đang chạy “trả nửa bản ghi”.

### Những cách viết thường sai

~~~java
// 1. SAI: gọi JDBC ngay lúc tạo Mono.
Mono<Book> a = Mono.just(repository.load(id));

// 2. SAI: JDBC đã chạy rồi; publishOn ở cuối không cứu event loop.
Mono<Book> b = Mono.just(repository.load(id))
        .publishOn(Schedulers.boundedElastic());

// 3. SAI: block() đặt vòng chờ ngay trong WebFlux handler.
Book c = reactiveService.fetch(id).block();

// 4. SAI: tự subscribe và trả response ngay, mất lifecycle gắn với HTTP.
repositoryMono.subscribe();
return Mono.empty();
~~~

Có trường hợp cần `publishOn` để chuyển **các toán tử phía sau** sang scheduler mới. Với một nguồn synchronous blocking, lời gọi `subscribeOn` ngay sau `fromCallable` rõ ý nghĩa hơn. `publishOn` đặt **sau** một lời gọi blocking đã chạy không thể đảo ngược việc event loop bị giữ.

### Khi đã có `Optional<T>`

~~~java
// Đúng: Optional được tính trong callable, tránh query chạy trước subscribe.
Mono<Book> result = Mono.fromCallable(() ->
        repository.findById(id).orElse(null))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` xử lý giá trị `null` như hoàn tất rỗng. Nhưng “không tìm thấy” có thể cần trả HTTP 404; ứng dụng quyết định bằng `switchIfEmpty(Mono.error(...))` tại boundary HTTP.

### Khi dữ liệu nhiều hơn một phần tử

~~~java
// Ví dụ minh họa: repository.findPage() trả List<Book> bằng JDBC.
Mono<List<Book>> page = Mono.fromCallable(() -> repository.findPage(0, 50))
        .subscribeOn(Schedulers.boundedElastic());

Flux<Book> items = page.flatMapMany(Flux::fromIterable);
~~~

Dữ liệu của **một page** đã được JDBC fetch và materialize thành list trên worker trước khi Flux phát phần tử. Flux giúp biểu diễn downstream processing/encoding theo demand, nhưng không khiến truy vấn JDBC đó stream non-blocking.

Không viết `Flux.fromIterable(repository.findAll())` trực tiếp trên event loop nếu `findAll()` thực hiện blocking query ngay khi gọi. Cũng đừng dùng `Flux.fromStream(...)` với một stream JPA/ResultSet ràng buộc connection mà không quản lý transaction, đóng tài nguyên và scheduler; đóng connection trước khi subscriber duyệt xong có thể gây lỗi, còn giữ connection suốt một response stream dài có thể làm nghẽn pool.

## 4. Scheduler, pool và hàng chờ: giới hạn thực tế

`Schedulers.boundedElastic()` là scheduler mặc định hữu ích để cô lập lời gọi blocking legacy. Nó **có giới hạn số thread và hàng đợi**, vì vậy an toàn hơn một pool thread mở rộng vô hạn, nhưng không loại bỏ overload. Ở một số cấu hình Java 21+, Reactor có thể dùng virtual thread cho biến thể boundedElastic; ví dụ Java 17 ở đây dùng platform thread.

| Tài nguyên | Vai trò | Điều cần đo/giới hạn |
| --- | --- | --- |
| Netty event loops | Nhận/gửi HTTP non-blocking | Không chạy JDBC/JPA, sleep hay block trên event loop |
| boundedElastic workers | Chạy các blocking callable | Số task đang chạy, queue, thời gian chờ để được lên lịch |
| HikariCP connection pool | Cấp JDBC connection | Maximum pool size, active/idle/pending connections, timeout chờ connection |
| Database server | Thực thi SQL và duy trì transaction | Slow query, lock, query plan, số connection thực tế, CPU/I/O |
| Reactor operator | Ghép request và kết quả | `flatMap` concurrency, prefetch, buffering, error/cancel |
| HTTP clients và gateway | Chờ response | Timeout, retry, giới hạn kết nối/độ trễ, ngắt kết nối |

**Không nên** tăng boundedElastic thread count vô hạn chỉ vì DB chậm. Hàng đợi threads có thể kéo theo hàng đợi lấy connection, rồi hàng đợi lock/query ở DB. Mỗi tầng có latency và timeout riêng, làm p99 xấu và khiến giải pháp trông có vẻ hoạt động khi chưa bão hòa.

Một cách điều tiết là giới hạn số truy vấn JDBC có thể chạy đồng thời:

~~~java
// Minh họa trong một service; findOne(id) là Mono<Book> đã bọc JDBC đúng cách.
Flux<Book> findMany(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(this::findOne, 4);
}
~~~

`flatMapSequential` có thể subscribe tối đa **4** inner Publisher đồng thời và **giữ thứ tự phát ra theo đầu vào** (có thể buffer kết quả đến sớm). `flatMap` cũng có tham số concurrency nhưng kết quả có thể khác thứ tự. Concurrency 4 là số minh họa; chọn theo pool/query tải thực, không suy từ số CPU đơn giản. Nếu nhiều HTTP request cùng thực thi đoạn trên, **tổng** số query đồng thời có thể lớn hơn 4: giới hạn per-request không tự là giới hạn toàn hệ thống. Cần cơ chế bulkhead/semaphore hoặc điều tiết ingress cho giới hạn toàn cục khi hệ thống yêu cầu.

### Ba lớp timeout không thể thay thế nhau

1. **Connection acquisition timeout:** thời gian đợi một connection trong pool; ví dụ `spring.datasource.hikari.connection-timeout=2000` nghĩa là Hikari đợi tối đa khoảng 2 giây để cấp connection trước khi báo lỗi. Không phải thời gian tối đa của truy vấn.
2. **Query/statement timeout:** giới hạn thời gian chạy SQL do JDBC/driver/database hỗ trợ (ví dụ `JdbcTemplate.setQueryTimeout(...)` hoặc timeout ở DB). Việc driver có hủy được query hay không tùy hỗ trợ thực tế.
3. **Reactive response timeout:** `.timeout(Duration.ofSeconds(3))` chuyển chuỗi Reactor sang lỗi sau hạn; có thể cancel subscription nhưng **không bảo đảm cắt ngay một JDBC call đang blocked** hoặc rollback mọi side effect đã xảy ra.

Khi chọn timeout phải phối hợp các tầng: đừng để API chờ 500 ms nhưng DB connection acquisition vẫn treo lâu mà không có giám sát; cũng đừng retry liên tục vào một DB đang bão hòa. Thiết kế deadline dựa vào SLO thực tế và kiểm thử khi slow query/pool hết connection.

## 5. Ví dụ chạy được: WebFlux đọc dữ liệu từ H2 qua JdbcTemplate

Mục đích demo: quan sát **controller reactive**, **repository JDBC blocking** và **điểm chuyển scheduler**. Không cần hệ quản trị DB ngoài máy: H2 tạo bảng và dữ liệu mẫu khi khởi động. Ví dụ dùng phiên bản Spring Boot 4.1.2 từ Maven Central và JDK 17+.

Cấu trúc dự án:

~~~text
webflux-blocking-store/
  pom.xml
  src/main/java/com/example/blockingstore/
    BlockingStoreApplication.java
    BookDto.java
    BookRepository.java
    BookService.java
    BookController.java
  src/main/resources/
    application.properties
    schema.sql
    data.sql
~~~

### 5.1. Maven dependencies

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>webflux-blocking-store</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

`spring-boot-starter-webflux` tạo web runtime reactive với Reactor Netty khi không có web server starter MVC lấn quyền; `spring-boot-starter-jdbc` cung cấp Spring JDBC/HikariCP, không tạo reactive database driver. `h2` là kho SQL chạy in-memory cho demo. JSON body được xử lý bởi codec phù hợp có sẵn trong cấu hình WebFlux/Boot.

### 5.2. Khởi động và DTO

**`src/main/java/com/example/blockingstore/BlockingStoreApplication.java`**

~~~java
package com.example.blockingstore;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BlockingStoreApplication {
    public static void main(String[] args) {
        SpringApplication.run(BlockingStoreApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/blockingstore/BookDto.java`**

~~~java
package com.example.blockingstore;

public record BookDto(long id, String title, int priceCents) {}
~~~

`record` Java 17 định nghĩa đối tượng dữ liệu bất biến dùng để serialize JSON response. Trường `priceCents` dùng số nguyên để tránh sai số số thực khi mô phỏng giá tiền.

### 5.3. Repository imperative

**`src/main/java/com/example/blockingstore/BookRepository.java`**

~~~java
package com.example.blockingstore;

import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class BookRepository {
    private final JdbcTemplate jdbcTemplate;

    public BookRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Optional<BookDto> findById(long id) {
        List<BookDto> rows = jdbcTemplate.query(
                "select id, title, price_cents from books where id = ?",
                (rs, rowNum) -> new BookDto(
                        rs.getLong("id"),
                        rs.getString("title"),
                        rs.getInt("price_cents")),
                id);
        return rows.stream().findFirst();
    }
}
~~~

Đây là phương thức **blocking**: `jdbcTemplate.query(...)` đợi query hoàn tất và xây `List<BookDto>` trước khi trả. Vì điều kiện `id` là khóa chính nên query có tối đa một row, phù hợp với ví dụ. Với truy vấn trả hàng nghìn row phải pagination/giới hạn kết quả, không dùng cách trên để đọc mọi dữ liệu tùy ý.

**Chú ý bảo mật truy vấn:** cú pháp `where id = ?` dùng bind parameter, giúp tránh ghép dữ liệu người dùng trực tiếp vào SQL. Mẫu này vẫn cần phân quyền và validation tùy nghiệp vụ.

### 5.4. Service làm cầu nối blocking → reactive

**`src/main/java/com/example/blockingstore/BookService.java`**

~~~java
package com.example.blockingstore;

import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class BookService {
    private final BookRepository repository;

    public BookService(BookRepository repository) {
        this.repository = repository;
    }

    public Mono<BookDto> findById(long id) {
        return Mono.fromCallable(() -> repository.findById(id).orElse(null))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đây là **ranh giới quan trọng nhất** của ví dụ. `findById(...)` trả về ngay một mô tả Publisher; khi WebFlux subscribe, callable được thực thi trên boundedElastic worker. Trong callable, JDBC vẫn block một worker. Không cần tự tạo `Thread` hay gọi `subscribe()`.

### 5.5. Controller reactive

**`src/main/java/com/example/blockingstore/BookController.java`**

~~~java
package com.example.blockingstore;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/books")
public class BookController {
    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Mono<BookDto> findById(@PathVariable long id) {
        return service.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Book not found")));
    }
}
~~~

Controller **không biết chi tiết SQL** và **không block**. Nếu book tồn tại, `Mono<BookDto>` phát một DTO để WebFlux mã hóa JSON và ghi response. Nếu không có bản ghi, `switchIfEmpty` chuyển thành lỗi có status HTTP 404. Lỗi DB bất ngờ vẫn đi qua `onError`; cần chính sách error mapping khi đưa vào production.

### 5.6. H2, connection pool và dữ liệu mẫu

**`src/main/resources/application.properties`**

~~~properties
server.port=8080

spring.datasource.url=jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=

spring.datasource.hikari.maximum-pool-size=5
spring.datasource.hikari.connection-timeout=2000

spring.sql.init.mode=always
~~~

Pool tối đa 5 JDBC connections để dễ quan sát giới hạn DB (chỉ là giá trị minh họa). `connection-timeout=2000` là **2.000 ms thời gian chờ lấy connection**, không phải query timeout. DB `catalog` nằm trong bộ nhớ và biến mất khi process kết thúc; không dùng cấu hình này cho dữ liệu cần lưu lâu dài.

**`src/main/resources/schema.sql`**

~~~sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    price_cents INTEGER NOT NULL
);
~~~

**`src/main/resources/data.sql`**

~~~sql
INSERT INTO books (id, title, price_cents) VALUES
    (1, 'Reactor in Practice', 2500),
    (2, 'SQL Basics', 1800),
    (3, 'Web Runtime', 3100);
~~~

Boot chạy script khởi tạo schema/data với H2 như cấu hình; thông thường chỉ nên chọn **một** cơ chế tạo schema trong ứng dụng thật (migration Flyway/Liquibase hoặc scripts có kiểm soát), tránh xung đột với Hibernate DDL.

### 5.7. Biên dịch, chạy, kiểm tra

Tại thư mục chứa `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

Trong terminal khác:

~~~bash
curl -i http://localhost:8080/api/books/1
~~~

Kỳ vọng HTTP 200 cùng body JSON sau:

~~~json
{"id":1,"title":"Reactor in Practice","priceCents":2500}
~~~

Gọi bản ghi thứ hai:

~~~bash
curl -i http://localhost:8080/api/books/2
~~~

Body kỳ vọng:

~~~json
{"id":2,"title":"SQL Basics","priceCents":1800}
~~~

Gọi ID không tồn tại:

~~~bash
curl -i http://localhost:8080/api/books/999
~~~

Kỳ vọng HTTP 404; nội dung body lỗi cụ thể phụ thuộc cấu hình Spring Boot, vì vậy không cố định JSON error trong bài.

Trên PowerShell, dùng `curl.exe -i http://localhost:8080/api/books/1` hoặc `Invoke-RestMethod http://localhost:8080/api/books/1`. Lệnh `mvn package` rồi `java -jar target/webflux-blocking-store-0.0.1-SNAPSHOT.jar` cũng chạy được khi Maven đã tải xong dependency.

### 5.8. Xem chính xác phần nào là blocking

| Thời điểm | Thành phần | Thread có thể bị giữ? |
| --- | --- | --- |
| Server nhận `GET /api/books/1` | Reactor Netty, WebFlux routing | Không gọi JDBC; xử lý non-blocking của web runtime |
| Controller gọi `service.findById(1)` | Tạo `Mono.fromCallable` + `subscribeOn` | Chưa thực hiện query |
| Runtime subscribe vào pipeline | Reactor lên lịch callable | Event loop không chờ JDBC trực tiếp |
| Worker gọi `repository.findById(1)` | boundedElastic → HikariCP → JDBC → H2 | **Có:** worker chờ connection/query |
| Callable trả `BookDto` | Mono phát giá trị và hoàn tất | Worker được giải phóng khi callable xong |
| Framework mã hóa DTO | WebFlux HTTP codec | Response được ghi qua web runtime |

Kết quả hoạt động **giữ tính reactive ở tầng HTTP**, nhưng **đường đi dữ liệu tổng thể vẫn tiêu thụ thread mỗi khi JDBC chờ**. Không được ghi là “end-to-end non-blocking”.

## 6. Transaction của JDBC/JPA không tự đi theo Reactor Context

Đây là một lỗi tinh vi: **transaction imperative** và **transaction reactive** sử dụng hai cơ chế lan truyền ngữ cảnh khác nhau.

- Với `PlatformTransactionManager` cho JDBC/JPA, Spring thường gắn trạng thái transaction/connection vào **thread hiện hành** thông qua `ThreadLocal`.
- Với `ReactiveTransactionManager` cho R2DBC, Spring dùng **Reactor Context** gắn với subscription thay cho một thread cố định.
- Di chuyển callable sang boundedElastic đổi thread. Một transaction đang mở trên event loop **không tự chuyển** sang worker bằng `subscribeOn`.
- `@Transactional` trên một method **trả `Mono`** nhưng bên trong chỉ mới dựng Publisher có thể tạo hiểu lầm với imperative transaction: method trả về trước khi JDBC chạy. Không dựa vào nó để bao trọn JDBC I/O.

### Thiết kế đúng cho một transaction JDBC

Đặt toàn bộ hoạt động cần cùng transaction trong **một method imperative** có `@Transactional`, được gọi **bên trong callable** trên boundedElastic. Transaction phải được mở, dùng và đóng trên cùng thread synchronous. Ví dụ:

~~~java
// Minh họa ranh giới transaction; các kiểu OrderDto/OrderRow/Dao giả định
// đã được định nghĩa trong dự án. Đây không phải chương trình độc lập.
@Service
public class LegacyOrderReader {
    private final JdbcOrderDao dao;

    public LegacyOrderReader(JdbcOrderDao dao) {
        this.dao = dao;
    }

    @Transactional(readOnly = true)
    public OrderDto load(long id) {
        OrderRow row = dao.findById(id);
        return new OrderDto(row.id(), row.totalCents());
    }
}
~~~

Rồi gọi từ **bean khác** để Spring AOP proxy thực thi transaction:

~~~java
// Minh họa trong reactive service; reader là bean LegacyOrderReader được inject.
public Mono<OrderDto> findOrder(long id) {
    return Mono.fromCallable(() -> reader.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

Trường hợp nhiều truy vấn trong transaction, toàn bộ chuỗi `dao.loadA(); dao.loadB(); ...` nên nằm trong method imperative `@Transactional` đó. Không chia những lệnh bắt buộc cùng transaction ra các nhánh `flatMap` chạy trên worker khác, vì thread-bound transaction có thể bị mất. Với JPA, đừng đưa proxy entity/lazy collection chưa khởi tạo ra sau khi transaction/session đã đóng rồi mới serialize trong WebFlux; hãy ánh xạ thành DTO **bên trong** phạm vi transaction.

**Self-invocation:** khi một method trong cùng bean gọi `this.load(...)`, Spring proxy-based `@Transactional` có thể không được áp dụng. Đặt transaction boundary ở bean được inject qua proxy hoặc dùng `TransactionTemplate` trong callable cho đường đi rõ ràng hơn.

### Nếu muốn transaction reactive thực sự

Chuyển dữ liệu sang R2DBC với driver phù hợp và dùng `ReactiveTransactionManager`/`TransactionalOperator`. Điều này không chỉ đổi kiểu trả về repository: cần rà soát schema mapping, query, transaction semantics, library hỗ trợ driver, database và phụ thuộc của ứng dụng. Spring Data R2DBC khác Spring Data JPA/Hibernate; không thể coi là bản thay JPA ngang tính năng.

## 7. Đọc nhiều bản ghi: paging, buffering và backpressure

Mặc dù lớp HTTP trả `Flux<BookDto>`, **JDBC vẫn chờ đồng bộ** ở tầng truy vấn. Không giả định `Flux` sẽ cấp phép JDBC đọc từng row theo `request(1)`.

### Một danh sách lớn có thể chiếm RAM như thế nào?

~~~java
// SAI nếu câu query trả dữ liệu rất lớn: lệnh findAll() vẫn blocking
// và có thể gom toàn bộ kết quả vào List trước khi Flux thấy phần tử.
return Flux.fromIterable(repository.findAll());
~~~

Ngay cả khi viết:

~~~java
// Tốt hơn cho event loop nhưng vẫn buffer cả tập dữ liệu.
return Mono.fromCallable(repository::findAll)
        .subscribeOn(Schedulers.boundedElastic())
        .flatMapMany(Flux::fromIterable);
~~~

event loop không block, song list lớn được giữ trong RAM và query chiếm một JDBC worker/connection trong lúc đọc dữ liệu. Với các tập dữ liệu lớn, ưu tiên **keyset pagination hoặc bounded pagination** và giới hạn kích thước mỗi page.

Một ý tưởng phân trang:

~~~java
// Minh họa; repo.readPage(pageNo, 100) trả List<BookDto> theo JDBC.
// Tất cả pages được đọc tuần tự, mỗi page giới hạn 100 rows.
// Cần tiêu chí dừng và thứ tự ổn định trong triển khai thực tế.
Flux<BookDto> books = Flux.range(0, 10)
    .concatMap(pageNo ->
        Mono.fromCallable(() -> repo.readPage(pageNo, 100))
            .subscribeOn(Schedulers.boundedElastic()))
    .concatMapIterable(page -> page);
~~~

Đoạn này dùng **10 trang đã biết** để minh họa; ứng dụng thật cần phân trang đến hết dữ liệu với cursor/keyset phù hợp, không hardcode số trang. `concatMap` duy trì thứ tự và tránh chạy tất cả query song song. Dù Flux có thể stream downstream từng page, **mỗi page vẫn được JDBC materialize blocking** trước.

### Giới hạn các lần truy cập song song

Nếu xử lý một danh sách 100 ID và mỗi ID dùng `Mono.fromCallable` riêng, dùng `flatMapSequential(id -> lookup(id), concurrency)` hoặc `flatMap(..., concurrency)` để giới hạn số in-flight query **trong một pipeline**. Thêm giới hạn tổng tải nếu nhiều request đồng thời; đồng bộ giới hạn với Hikari pool và năng lực database.

Khi cần tải một danh sách, một câu SQL `WHERE id IN (...)` có bind parameters, batching hợp lý hoặc join có index tốt có thể hiệu quả hơn 100 query riêng; tránh hiệu ứng **N+1 query** trong JPA. Dùng query plan, index và pagination trước khi chỉ tăng scheduler threads.

### Backpressure có tác dụng đến đâu?

`request(n)` điều khiển số phần tử reactive downstream muốn nhận. Nó có thể giới hạn tốc độ tiêu thụ/khởi tạo query tiếp theo khi pipeline được cấu trúc đúng. Nhưng đã bắt đầu một `JdbcTemplate.query` đồng bộ thì demand **không có cách chung để dừng giữa chừng ở hàng thứ 37**. Cùng một cách, Netty áp dụng backpressure không có nghĩa database driver JDBC hỗ trợ Reactive Streams. Đây là **ranh giới không reactive** cần được ghi rõ trong thiết kế.

## 8. Lỗi, timeout, hủy và retry khi nguồn vẫn blocking

Khi dùng `Mono.fromCallable`, exception do JDBC hoặc pool ném được chuyển thành `onError`. Ví dụ:

~~~java
// Minh họa trong service; dao.readById(id) dùng JDBC.
return Mono.fromCallable(() -> dao.readById(id))
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(3))
        .onErrorMap(
                java.sql.SQLTransientException.class,
                ex -> new DataAccessTemporarilyUnavailableException(ex));
~~~

Đây là đoạn minh họa, cần import và class `DataAccessTemporarilyUnavailableException` của dự án; `JdbcTemplate` cũng có thể chuyển `SQLException` thành Spring `DataAccessException`, nên mapping phải nhắm vào **loại exception thực tế**, không mặc định lúc nào cũng thấy `SQLException`.

### Tại sao timeout của Reactor chưa đủ?

Giả sử `timeout(3s)` phát lỗi sau 3 giây. Upstream nhận cancel, nhưng thread JDBC có thể còn đang chờ query hoặc socket; query có thể tiếp tục đến khi driver/DB timeout hoặc hỗ trợ interrupt/cancel. Vì vậy cần kết hợp:

- Timeout **đợi connection** ở Hikari.
- Timeout của **statement** và **network/socket** ở JDBC driver/database.
- Deadline của **reactive request** ở HTTP.
- Giới hạn **concurrency và queue**, đặc biệt khi downstream DB chậm.
- Chỉ retry có chọn lọc khi lỗi tạm thời, có backoff/jitter, giới hạn số lần và điều kiện **idempotency**.

**Không retry ghi DB một cách mù quáng.** Nếu client timeout khi một lệnh INSERT đã commit, retry request có thể ghi trùng. Dùng idempotency key, constraint DB, transaction/outbox hoặc quy trình đối soát tùy nghiệp vụ.

### Client ngắt kết nối có tự dừng SQL không?

Không thể bảo đảm. HTTP layer có thể cancel subscription và khiến những task **chưa được chạy** không được thực hiện. Nhưng task JDBC đã ở trong driver có thể chỉ dừng khi API/driver thực sự hỗ trợ hủy. Cancel cũng không tự rollback giao dịch đã commit hoặc thao tác với hệ thống ngoài.

### Lỗi nào trả HTTP status gì?

- Không tìm thấy record: có thể chuyển `Mono.empty()` thành **404** khi contract định nghĩa vậy.
- Đầu vào không hợp lệ: thường **400** với validation rõ ràng.
- Hết connection pool, database unreachable hoặc lỗi query: thường lỗi máy chủ hoặc **503** khi dịch vụ không sẵn sàng (theo chính sách ứng dụng), cần log/tracing riêng, không rò SQL/stack trace ra client.
- Timeout: có thể trả status lỗi phù hợp khi response chưa commit; đừng luôn gán một code cố định nếu nguyên nhân/contract khác nhau.

Khi response streaming đã commit một phần, không thể thay headers/status để “trả 503 mới”; client cần được thiết kế để xử lý stream dở dang.

## 9. Quan sát và kiểm thử để không “đánh tráo” chữ reactive

### Chứng minh event loop không block

Đặt log thread tại hai vị trí:

~~~java
// Minh họa trong service, không phải source độc lập.
return Mono.fromCallable(() -> {
    log.info("JDBC thread={}", Thread.currentThread().getName());
    return repository.load(id);
}).subscribeOn(Schedulers.boundedElastic());
~~~

Với scheduler platform-thread mặc định, tên thread JDBC thường liên quan `boundedElastic-...`; tên chính xác không phải contract API, nên không viết assertion bám tên. Quan sát đầu controller hoặc `doOnSubscribe` cũng cần hiểu operator/scheduler: tên thread trong từng callback có thể khác nhau.

Kiểm thử **đúng hành vi** chứ không chỉ tên thread:

1. Đưa query vào trạng thái chậm có kiểm soát; gọi nhiều request và đo p50/p95/p99.
2. Trong lúc DB chậm, gọi endpoint không truy cập DB; xác nhận HTTP event loop còn phục vụ được request nhẹ.
3. Đo active/pending Hikari connections, boundedElastic queue, DB CPU, lock wait và số request đồng thời.
4. Giảm maximum pool size để tạo nghẽn thử; xác nhận request timeout/giới hạn concurrency thay vì hàng đợi không kiểm soát.
5. Cho client cancel/timeout khi query đang chạy; quan sát query thật sự kết thúc lúc nào, connection có được trả về pool đúng cách không.
6. Kiểm tra hợp đồng 404/5xx, dữ liệu lớn, cache miss, N+1 query và SQL injection từ input.
7. Nếu dùng JPA, kiểm tra lazy loading/transaction sau khi chuyển scheduler và cấu hình fetching.

### Kết quả từ việc đo nên được đọc ra sao?

| Dấu hiệu | Giả thuyết có thể kiểm tra |
| --- | --- |
| HTTP request nhẹ chậm khi JDBC chậm | Có blocking trên event loop hoặc event loop bị quá tải |
| Hikari pending connections tăng liên tục | Tạo DB task nhanh hơn tốc độ pool có thể cung cấp |
| boundedElastic queue phình ra | Nguồn blocking bị bão hòa; cần giới hạn tiếp nhận, giảm query latency hoặc thêm năng lực thực sự |
| DB CPU thấp nhưng latency cao | Có thể đang chờ pool, lock, network, query planning hoặc thread |
| Rất nhiều worker đang chờ cùng query | N+1 query, pool nhỏ, DB/lock contention hoặc retry không kiểm soát |
| RSS/heap tăng khi trả `Flux` | Dữ liệu lớn đã materialize, buffering, prefetch hay cache |
| Timeout HTTP nhưng DB query vẫn chạy | Cancellation chưa dừng blocking I/O; cần timeout từ driver/database |

Trong dự án có Reactor debugging, các công cụ BlockHound có thể phát hiện một số thao tác blocking trên non-blocking thread ở môi trường phát triển/test. Dùng công cụ tương thích phiên bản và đừng xem nó thay thế test tải và quan sát DB; không phải mọi JDBC waiting đều được detect tự động.

## 10. Chọn chiến lược tích hợp phù hợp

| Tình huống | Lựa chọn thực tế | Điều đánh đổi |
| --- | --- | --- |
| Ứng dụng WebFlux cần gọi một JDBC/JPA repository hiện có | `Mono.fromCallable(...).subscribeOn(boundedElastic())` + giới hạn concurrency/timeout | Duy trì hợp đồng Publisher ở web, nhưng query vẫn giữ worker và JDBC connection |
| Đa số request dùng JPA/JDBC và mọi nghiệp vụ đồng bộ | Xem xét **Spring MVC** với thread pool/container thích hợp | Mô hình đơn giản hơn cho blocking workload; không có lợi thế event loop non-blocking |
| Hệ thống I/O đồng thời cao, DB và driver hỗ trợ reactive | R2DBC/Spring Data R2DBC | Cần sửa repository, transaction, mapping, driver và đo lại behavior |
| Kho không có driver reactive, API ít thay đổi | Adapter blocking được cô lập sau service boundary | Dễ chuyển đổi từng phần, nhưng phải quản lý scheduler/capacity |
| Dữ liệu đọc lớn liên tục | Pagination/keyset/batch hoặc cơ chế streaming có quản lý tài nguyên | Không được hứa stream từ JDBC non-blocking; cần kiểm soát connection và lifecycle |
| Yêu cầu giao dịch JPA phức tạp, lazy-loading, ORM features | Giữ JPA imperative trong transaction riêng; cân nhắc MVC | “Đổi sang Mono” không thay ORM/transaction semantics |
| Tác vụ đọc nặng kéo dài hoặc chạy nền | Job/batch hoặc dịch vụ riêng, queue với concurrency hữu hạn | Đổi mô hình xử lý/tính eventual consistency; tránh trói HTTP connection dài |

**Spring MVC + JDBC không phải thiết kế sai.** WebFlux có lợi khi nhiều tầng thực sự non-blocking. Nếu nút thắt chính là database synchronous và hệ thống không có nhu cầu concurrent I/O lớn, Spring MVC có thể dễ vận hành và debug hơn. Lựa chọn dựa vào đặc điểm workload, giới hạn tài nguyên và đo đạc thực tế.

**R2DBC không phải “JPA reactive”.** Spring Data R2DBC có mô hình repository/template và mapping riêng, không mặc nhiên có lazy loading/cascade/session và toàn bộ tính năng của Hibernate. Trước khi chuyển, đánh giá transaction isolation, SQL driver, dữ liệu phức tạp và công cụ migration.

## 11. Quy trình triển khai an toàn từng bước

1. **Xác định mọi điểm blocking:** method repository, JDBC/JPA, HTTP client đồng bộ, filesystem, cache client, SDK, logging xuất đồng bộ; đánh dấu rõ ranh giới.
2. **Tách adapter rõ ràng:** đặt gọi blocking trong một bean DAO/service imperative; dùng một reactive service bọc bằng `fromCallable` và `subscribeOn(boundedElastic())`.
3. **Thiết kế transaction nguyên khối trên worker:** các bước cần một JDBC transaction nằm trong một method imperative `@Transactional` được gọi qua proxy; không kéo lazy entity ra ngoài.
4. **Đặt giới hạn ở nguồn:** connection pool, số tác vụ đồng thời, queue/bulkhead, kích thước page, JDBC/query timeout và HTTP deadline.
5. **Bảo đảm error/empty semantics:** mapping 404, 400, 503 khi phù hợp; không nuốt exception và không đặt `block()` trong controller.
6. **Đo dưới tải:** kiểm tra event loop responsiveness, connection acquisition wait, throughput, p99, memory và behavior khi hủy kết nối.
7. **Đánh giá thay thế:** tối ưu SQL trước, rồi xem workload có cần R2DBC hay dùng Spring MVC sẽ đơn giản hơn.
8. **Giữ hợp đồng dữ liệu:** khi thay công nghệ truy cập, kiểm thử mapping, transaction, cache, paging, ordering và kết quả JSON để tránh đổi hành vi ngoài ý muốn.

## 12. Những hiểu lầm thường gặp

- **“Repository trả `Mono` nên JDBC tự non-blocking.”** Sai: wrapper thay giao diện lập trình, không thay API I/O bên dưới.
- **“`Mono.just(jdbc.query(...))` an toàn vì Mono là lazy.”** Sai: đối số của `Mono.just` được tính ngay trước khi tạo Mono; query đã chạy.
- **“Đặt `publishOn` sau query sẽ dời query sang worker.”** Sai: query đã hoàn tất hoặc đang chờ trên thread gọi trước khi `publishOn` có tác dụng.
- **“boundedElastic biến database thành reactive.”** Sai: nó offload blocking call, vẫn dùng thread chờ connection/query.
- **“Tăng worker threads là tăng throughput DB.”** Không nếu nút thắt là pool, lock hoặc năng lực database.
- **“`Flux.fromIterable(allRows)` là stream từ DB.”** Không nếu `allRows` đã được materialize bằng query synchronous.
- **“Cancellation của HTTP chắc chắn dừng JDBC.”** Không: tùy driver, trạng thái query và cancellation support.
- **“`@Transactional` phía ngoài `Mono.fromCallable` luôn giữ transaction cho query.”** Không bảo đảm với imperative thread-bound transactions; boundary phải đặt phù hợp.
- **“R2DBC và Spring Data JPA giống nhau, chỉ khác `Mono`.”** Sai: transaction, mapping, ORM semantics và driver khác nhau.
- **“Dùng WebFlux luôn nhanh hơn MVC.”** Sai: kết quả phụ thuộc work profile, concurrency, resource caps, DB, I/O thực và cách triển khai.

## 13. Bài tự kiểm tra có đáp án

**Tình huống A:** WebFlux endpoint đang gọi trực tiếp `jdbcTemplate.query(...)` rồi gói kết quả trong `Mono.just(...)`. Điều gì sai?

**Đáp án:** SQL được chạy ngay trên thread handler trước khi Mono ra đời; nếu thread là Netty event loop, nó bị block. Dùng `Mono.fromCallable(() -> jdbcTemplate.query(...)).subscribeOn(Schedulers.boundedElastic())` và trả Publisher cho runtime.

**Tình huống B:** Hikari pool có 5 connections, bạn tăng boundedElastic workers lên 100. Số query DB đồng thời có mặc nhiên thành 100 không?

**Đáp án:** Không. Thông thường tối đa khoảng số connections sẵn có của pool trên instance đó; phần còn lại chờ connection hoặc timeout. Database có thể có giới hạn riêng.

**Tình huống C:** `Mono.fromCallable(repository::findAll).flatMapMany(Flux::fromIterable)` có phải đọc row-by-row không blocking từ DB?

**Đáp án:** Không. `findAll()` vẫn tạo list đồng bộ; nếu thêm `subscribeOn` thì chặn trên worker thay vì event loop. Muốn giảm bộ nhớ, dùng pagination/batch có giới hạn.

**Tình huống D:** Bạn đặt `@Transactional` trên reactive method trả `Mono<Order>`, còn JDBC thực thi sau đó trên boundedElastic. Vì sao transaction có thể không bao được query?

**Đáp án:** Transaction imperative dùng ThreadLocal, trong khi method đã trả Mono và thread thực thi sau này khác. Đặt transaction ở method imperative được gọi **bên trong** `fromCallable` và bảo đảm gọi qua Spring proxy.

**Tình huống E:** Client hủy request khi query đang chạy. Có chắc query dừng, connection được trả tức thì không?

**Đáp án:** Không. Cancellation dừng chuỗi reactive khi có thể, nhưng JDBC call đang chờ phụ thuộc driver/timeout/interruption. Cần đo và cấu hình timeout ở nhiều tầng.

**Tình huống F:** Khi nào nên thay JDBC bằng R2DBC thay vì chỉ offload?

**Đáp án:** Khi database/driver và phần lớn downstream hỗ trợ I/O reactive, workload có lợi từ xử lý non-blocking đồng thời, và đội ngũ chấp nhận chi phí đổi mapping/transaction, có benchmark chứng minh lợi ích. Nếu phần lớn nghiệp vụ vẫn blocking, có thể ưu tiên MVC hoặc giữ adapter blocking với giới hạn rõ ràng.

## Tài liệu chính thức tham khảo

- [Spring Framework — Spring WebFlux Overview và concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Project Reactor — Threading and Schedulers, boundedElastic](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Project Reactor — FAQ: Wrap a synchronous, blocking call](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Spring Boot — SQL Databases (JDBC, connection pooling)](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html)
- [Spring Framework — Declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Programmatic transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Data — JDBC và R2DBC Reference](https://docs.spring.io/spring-data/relational/reference/)
- [Spring Data — R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)

**Nguyên tắc cốt lõi:** khi dữ liệu đến từ repository không reactive, giữ **sự thật về blocking** ngay trong thiết kế. `fromCallable + subscribeOn(boundedElastic)` bảo vệ event loop, còn DB query vẫn chiếm worker và connection. Muốn hệ thống thực sự end-to-end reactive, cả các nguồn dữ liệu và driver ở phía dưới cũng phải hỗ trợ non-blocking, đồng thời cần quản lý backpressure, transaction, timeout và giới hạn tài nguyên.