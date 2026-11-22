# Toàn cảnh Spring JDBC, ORM/JPA và R2DBC

Spring cung cấp nhiều cách truy cập cơ sở dữ liệu quan hệ. Ba hướng thường gặp là **Spring JDBC** (viết SQL và ánh xạ kết quả trực tiếp), **ORM/JPA** (làm việc với entity và persistence context) và **R2DBC** (truy cập SQL bằng API reactive, không chặn luồng trong lúc chờ I/O nếu driver hỗ trợ). Cả ba có thể cùng truy cập một hệ quản trị cơ sở dữ liệu, nhưng khác nhau ở mức trừu tượng, mô hình thực thi và cách quản lý transaction.

Bài này giúp trả lời bốn câu hỏi: “Tôi kiểm soát SQL ở mức nào?”, “Ai quản lý trạng thái đối tượng?”, “Lời gọi cơ sở dữ liệu có chặn luồng hay không?” và “Transaction gắn với ngữ cảnh nào?”.

## 1. Mục tiêu học tập và ranh giới

Sau bài này, bạn có thể:

1. Mô tả đường đi từ service đến database của JDBC, JPA và R2DBC; phân biệt vai trò của `DataSource`, `EntityManager` và `ConnectionFactory`.
2. Nhận biết các API chính: `JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`, `EntityManager`, `DatabaseClient` và các abstraction của Spring Data.
3. Giải thích việc ánh xạ hàng dữ liệu thành đối tượng, dirty checking, lazy loading, reactive publisher, connection và transaction.
4. Chọn cách tiếp cận theo loại truy vấn, mô hình ứng dụng, driver, khối lượng I/O, độ phức tạp domain và năng lực vận hành.
5. Tránh lỗi SQL injection, N+1 query, transaction không hiệu lực, blocking trong reactive flow, thiếu connection pool hoặc hiểu sai “reactive luôn nhanh hơn”.

**Ranh giới:** Đây là bài **tổng quan kiến trúc và cách lựa chọn**, không thay thế tài liệu chuyên sâu về JDBC batching, JPQL/Criteria, khóa/isolation hay Reactor. Spring Framework cung cấp lớp JDBC, tích hợp JPA/ORM và phần lõi R2DBC; các repository cao cấp thường thuộc **Spring Data**, là dự án liên quan nhưng khác tầng.

## 2. Bản đồ kiến trúc: cùng là SQL, khác đường đi

~~~text
HTTP / Message Consumer / Scheduled Job
                |
           Service layer
                |
          Transaction boundary
                |
    +-----------+-------------+----------------+
    |                         |                |
Spring JDBC                 JPA/ORM          R2DBC
JdbcClient/                 EntityManager    DatabaseClient
JdbcTemplate                (Hibernate...)   / Spring Data R2DBC
    |                         |                |
DataSource                 DataSource        ConnectionFactory
    |                         |                |
JDBC driver                JDBC driver       R2DBC driver
    |                         |                |
    +-------------------------+----------------+
                              |
                         SQL database
~~~

- **Spring JDBC:** Bạn sở hữu SQL. Spring giúp lấy/trả `Connection`, tạo `PreparedStatement`, ánh xạ `ResultSet` và chuẩn hóa ngoại lệ. Từng lệnh SQL được thực hiện khi gọi phương thức (blocking).
- **JPA/ORM:** Bạn thao tác trên entity đã được ánh xạ sang bảng; nhà cung cấp JPA (ví dụ Hibernate) quyết định và thực thi SQL cần thiết. Spring cấu hình/hòa nhập `EntityManagerFactory`, `EntityManager` và transaction. JPA thông dụng dựa trên JDBC và blocking.
- **R2DBC:** Bạn tạo chuỗi xử lý bằng `Publisher`, `Mono` hoặc `Flux`; hoạt động I/O được thực thi khi có subscription. Spring quản lý kết nối reactive và ánh xạ kết quả. R2DBC thường là truy vấn SQL hoặc mapping aggregate đơn giản, **không đồng nghĩa với JPA chạy bất đồng bộ**.

`DataSource` (thuộc JDBC) và `ConnectionFactory` (thuộc R2DBC) là hai loại factory khác nhau, sử dụng driver và cơ chế quản lý tài nguyên khác nhau. Cùng một bảng trong database không khiến hai stack tự động chia sẻ transaction.

## 3. Spring JDBC: SQL tường minh, ít boilerplate

### 3.1. Các thành phần

| Thành phần | Vai trò |
| --- | --- |
| `DataSource` | Cấp JDBC `Connection`; ở production thường đi kèm connection pool như HikariCP. |
| `JdbcTemplate` | API thực hiện query/update/batch, quản lý tài nguyên và ánh xạ bằng `RowMapper`, `ResultSetExtractor`. |
| `NamedParameterJdbcTemplate` | Cho phép tham số có tên như `:id`, tiện với truy vấn nhiều tham số. |
| `JdbcClient` | Fluent API có từ Spring Framework 6.1, sử dụng cả tham số vị trí và tham số tên; xây trên các JDBC template. |
| `DataAccessException` | Hệ phân cấp ngoại lệ không checked; Spring dịch lỗi cơ sở dữ liệu để mã gọi ít phụ thuộc vendor. |
| `DataSourceTransactionManager` | Quản lý transaction JDBC cục bộ dựa trên `DataSource`. |

Ví dụ dữ liệu từ SQL đi qua `RowMapper`: mỗi hàng `ResultSet` được biến thành một giá trị Java. Spring tự đóng tài nguyên mà template đã mở trong phạm vi thao tác. Tuy vậy, **bạn phải** quyết định SQL, chiến lược phân trang, index, quan hệ và cách mapping.

### 3.2. Ví dụ hoàn chỉnh có thể chạy: Spring JDBC + H2

Ví dụ dùng Java 17+, Gradle và H2 chạy trong bộ nhớ. Không cần Spring Boot hay Spring container để dùng `JdbcTemplate`; mục đích là làm rõ đường đi từ SQL đến đối tượng Java.

Cấu trúc:

~~~text
jdbc-overview/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/JdbcOverview.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'jdbc-overview'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.11'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.JdbcOverview'
}
~~~

`src/main/java/demo/JdbcOverview.java`:

~~~java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import javax.sql.DataSource;
import java.util.List;

public class JdbcOverview {
    public static void main(String[] args) {
        DataSource dataSource = new DriverManagerDataSource(
                "jdbc:h2:mem:learn;DB_CLOSE_DELAY=-1", "sa", "");
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(100) NOT NULL
                )
                """);

        jdbc.update("INSERT INTO books(id, title) VALUES (?, ?)",
                1L, "Spring");
        jdbc.update("INSERT INTO books(id, title) VALUES (?, ?)",
                2L, "JDBC");

        List<String> titles = jdbc.query(
                "SELECT title FROM books ORDER BY id",
                (rs, rowNum) -> rs.getString("title")
        );
        System.out.println(titles);
    }
}
~~~

Từ thư mục project, khi đã có JDK 17+ và Gradle phù hợp, chạy:

~~~bash
gradle run --quiet
~~~

Stdout của chương trình:

~~~text
[Spring, JDBC]
~~~

Giải thích: `jdbc.execute` tạo bảng; hai lệnh `jdbc.update` dùng placeholder `?` để bind giá trị; `jdbc.query` đọc từng hàng qua lambda `RowMapper`, tạo `List<String>` và in theo `ORDER BY id`. H2 in-memory vẫn tồn tại trong JVM nhờ `DB_CLOSE_DELAY=-1`. `DriverManagerDataSource` mở kết nối mới khi được yêu cầu và **không tạo pool**; chỉ dùng cho demo/test. Ứng dụng thực tế cần pool và cấu hình timeout thích hợp.

Các phiên bản thư viện trong ví dụ được ghim để tái hiện thí nghiệm này. Trong dự án Spring Boot, hãy để BOM của phiên bản Boot quản lý phiên bản Spring và driver phù hợp, thay vì tự ghim Spring Framework khác nhánh.

### 3.3. Hai phong cách JDBC thường dùng trong ứng dụng Spring

Đoạn sau là **minh họa phương thức**, giả sử `DataSource dataSource` đã được cấu hình và có bảng `books`; đây không phải một chương trình độc lập:

~~~java
JdbcClient client = JdbcClient.create(dataSource);

String title = client.sql(
        "SELECT title FROM books WHERE id = :id")
    .param("id", 1L)
    .query(String.class)
    .single();

int changed = client.sql(
        "UPDATE books SET title = :title WHERE id = :id")
    .param("title", "Spring JDBC")
    .param("id", 1L)
    .update();
~~~

`single()` phù hợp khi kỳ vọng chính xác một kết quả; với truy vấn có thể không có hàng, dùng `optional()` hoặc `list()` tùy ý định. `JdbcClient` rất thuận tiện cho CRUD SQL thường gặp; các thao tác phức tạp như batching hay stored procedure vẫn có thể dùng `JdbcTemplate`/`SimpleJdbcCall`.

Với JDBC, SQL và số lần round-trip thường hiện rõ trong mã. Điều này đặc biệt hữu ích cho truy vấn báo cáo, bulk operations, dữ liệu không khớp với mô hình entity hoặc yêu cầu tối ưu SQL theo vendor.

## 4. ORM/JPA: ánh xạ thực thể và quản lý vòng đời

**ORM** (Object–Relational Mapping) là kỹ thuật nối object graph với bảng/hàng/khóa. **JPA** là chuẩn API Jakarta Persistence; **Hibernate** thường là JPA provider triển khai chuẩn và có thêm khả năng riêng. **Spring ORM** tích hợp provider với DI, `@PersistenceContext`, resource management và transaction. **Spring Data JPA** (nếu sử dụng) thêm repository abstraction lên nền JPA.

Những thuật ngữ quan trọng:

- **Entity:** Lớp có `@Entity`, thường có `@Id`, ánh xạ đến dữ liệu quan hệ.
- **`EntityManagerFactory`:** Tạo `EntityManager`; thường là một bean có cấu hình chung cho persistence unit.
- **`EntityManager`:** API quản lý entity trong **persistence context**; không nên xem nó là client dùng chung state giữa mọi thread.
- **Persistence context:** Tập các entity đang được quản lý, giữ identity map/first-level cache và theo dõi thay đổi.
- **Dirty checking:** Khi một entity đang managed bị đổi thuộc tính, provider có thể sinh `UPDATE` lúc flush, không cần gọi update SQL cho mỗi setter.
- **Flush:** Đồng bộ các thay đổi chờ xử lý thành SQL; không có nghĩa transaction đã commit.
- **Lazy loading:** Một số quan hệ chỉ được nạp khi truy cập, cần ngữ cảnh còn hoạt động và có thể phát sinh truy vấn bổ sung.

### 4.1. Vòng đời entity cần hiểu

~~~text
new Book(...)  --persist-->  managed  --flush/commit-->  SQL/DB
                                     |
                                     +-- entity.setTitle(...)
                                         dirty checking
managed --detach/clear/close--> detached
detached --merge--> managed copy (không tự trở thành managed)
~~~

Khi đọc entity bằng `find` trong cùng persistence context, provider có thể dùng entity đã quản lý. Đổi field của entity managed trong một transaction thường được đồng bộ khi flush; provider có thể flush trước query hoặc commit tùy flush mode và tình huống. Entity detached không tự lưu thay đổi; `merge` trả về một bản managed để tiếp tục thao tác.

### 4.2. Ví dụ mapping và business operation

Đây là **hai đoạn lớp trong ứng dụng JPA đã được cấu hình** (cần JPA provider, `DataSource`, entity scanning và transaction manager). Chúng minh họa hành vi JPA, không độc lập chạy chỉ bằng `javac`:

`Book.java`:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "books")
public class Book {
    @Id
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() { }

    public Book(Long id, String title) {
        this.id = id;
        this.title = title;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

`BookService.java`:

~~~java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BookService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void renameBook(Long id, String newTitle) {
        Book book = em.find(Book.class, id);
        if (book == null) {
            throw new IllegalArgumentException("Book not found: " + id);
        }
        book.setTitle(newTitle);
    }
}
~~~

Lệnh `em.find` tìm entity theo khóa; `setTitle` sửa entity managed. Khi transaction hoàn tất bình thường, provider sẽ flush thay đổi cần thiết rồi commit. Chú ý `@Transactional` chỉ có tác dụng nếu đã bật transaction management, có transaction manager phù hợp và phương thức được gọi qua Spring proxy (mặc định). Việc một phương thức trong cùng object gọi trực tiếp phương thức có `@Transactional` không đi qua proxy.

### 4.3. Lợi ích và chi phí của JPA

JPA hữu ích khi domain có nhiều entity, quan hệ, business rules và yêu cầu CRUD theo vòng đời đối tượng. Repository của Spring Data JPA giảm nhiều mã lặp nhưng **không loại bỏ chi phí SQL**. Hãy nhìn SQL thực tế mà provider phát sinh.

Các rủi ro chính:

1. **N+1:** Đọc N parent rồi truy cập lazy children gây thêm N truy vấn. Cân nhắc fetch join, entity graph, DTO projection hoặc batch fetch theo nhu cầu; đừng chuyển mọi quan hệ thành eager mặc định.
2. **Khối lượng entity lớn:** Persistence context giữ entity managed; với batch lớn cần chia lô, `flush/clear` có chủ đích hoặc dùng JDBC cho thao tác set-based.
3. **SQL không như kỳ vọng:** Quan sát SQL và execution plan; sự tiện lợi của entity API không thay thế thiết kế index/query.
4. **Lazy ngoài transaction:** Truy cập quan hệ chưa nạp sau khi persistence context đóng có thể lỗi. Thiết kế query/DTO tại service boundary thay vì phụ thuộc Open Session in View.
5. **Hiểu nhầm flush/commit:** SQL đã gửi trong flush vẫn có thể rollback cả transaction.

## 5. R2DBC: xử lý dữ liệu quan hệ theo reactive streams

R2DBC (Reactive Relational Database Connectivity) là SPI cho truy cập database theo mô hình reactive. Spring Framework có `org.springframework.r2dbc.core.DatabaseClient` để thực thi SQL và `R2dbcTransactionManager` để quản lý transaction reactive. Spring Data R2DBC có thêm `R2dbcEntityTemplate` và repository để ánh xạ aggregate.

### 5.1. Những khác biệt có tính quyết định

- **`ConnectionFactory` thay `DataSource`:** Driver R2DBC cung cấp connection, có thể tích hợp `r2dbc-pool`. JDBC driver không tự biến thành R2DBC driver.
- **Publisher thay kết quả đồng bộ:** `Mono<T>` biểu diễn 0 hoặc 1 giá trị; `Flux<T>` biểu diễn 0 đến nhiều giá trị. Chain thường mô tả thao tác; truy vấn chạy khi subscriber subscribe.
- **Chờ I/O không giữ thread bị block theo cách của JDBC:** Có thể phục vụ nhiều kết nối đồng thời hiệu quả hơn trong workload I/O-bound phù hợp, nhưng vẫn chịu giới hạn pool, database, locks, CPU và khả năng driver.
- **Transaction theo subscriber context:** `R2dbcTransactionManager` gắn connection vào Reactor context, không dùng cách gắn transaction đồng bộ vào thread như JDBC/JPA.
- **Không có persistence context JPA:** `DatabaseClient` ánh xạ hàng kết quả. Spring Data R2DBC có mapping entity/aggregate nhưng không phải Hibernate lazy-loading/dirty-checking JPA.

### 5.2. Ví dụ DatabaseClient

Giả sử `DatabaseClient databaseClient` đã được inject, driver và bảng `books` đã cấu hình. Ví dụ này là **phương thức minh họa** trong DAO reactive:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import reactor.core.publisher.Mono;

public class ReactiveBookDao {
    private final DatabaseClient databaseClient;

    public ReactiveBookDao(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<String> findTitle(long id) {
        return databaseClient.sql(
                "SELECT title FROM books WHERE id = :id")
            .bind("id", id)
            .map((row, metadata) -> row.get("title", String.class))
            .one();
    }
}
~~~

`findTitle` trả về `Mono<String>`, chưa có `String` ngay lập tức. Nếu không có hàng, `one()` hoàn tất rỗng; nếu nhiều hàng, đây là lỗi cardinality. Consumer có thể compose tiếp `map`/`flatMap` và subscribe ở boundary (ví dụ WebFlux tự quản subscription). Không gọi `block()` bên trong đường xử lý non-blocking.

Khi cần nhiều hàng, dùng `all()` để nhận `Flux<T>`. Việc có `Flux` không bảo đảm mọi driver tối ưu fetch/streaming giống nhau; kiểm tra hỗ trợ cursor/fetch size và memory dưới tải thực.

### 5.3. Ví dụ transaction reactive đúng ngữ cảnh

Đoạn sau cần một `ReactiveTransactionManager` được cấu hình cho **cùng `ConnectionFactory`** mà `DatabaseClient` sử dụng; đây không phải chương trình độc lập:

~~~java
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

public class ReactiveBookService {
    private final DatabaseClient databaseClient;
    private final TransactionalOperator tx;

    public ReactiveBookService(
            DatabaseClient databaseClient,
            ReactiveTransactionManager transactionManager) {
        this.databaseClient = databaseClient;
        this.tx = TransactionalOperator.create(transactionManager);
    }

    public Mono<Void> renameBook(long id, String title) {
        return databaseClient.sql(
                "UPDATE books SET title = :title WHERE id = :id")
            .bind("title", title)
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .flatMap(count -> count == 1
                    ? Mono.<Void>empty()
                    : Mono.<Void>error(
                            new IllegalStateException("Expected one row")))
            .as(tx::transactional);
    }
}
~~~

`TransactionalOperator` bọc publisher để tạo/hoàn tất transaction trong lúc subscription; nếu thiếu hàng hoặc sửa sai số lượng hàng, ví dụ phát lỗi và transaction rollback. Có thể dùng `@Transactional` với phương thức trả `Mono`/`Flux` khi Spring chọn reactive transaction manager phù hợp. Tránh tạo subscription lẻ bên trong service vì nó có thể tách transaction, error propagation và lifecycle khỏi chuỗi chính.

**Cảnh báo:** Gói một JDBC/JPA blocking call vào `Mono.just(...)` không biến call đó thành non-blocking; `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` là cách cô lập công việc blocking trong một số trường hợp, song vẫn tiêu thụ thread và không tạo transaction R2DBC. Đừng kết hợp hai mô hình rồi giả định chúng chia sẻ cùng một transaction.

## 6. Bảng so sánh ra quyết định

| Tiêu chí | Spring JDBC | JPA/ORM (thường Hibernate) | Spring R2DBC |
| --- | --- | --- | --- |
| Mức trừu tượng | SQL + row mapping | Entity, quan hệ, persistence context | SQL reactive; thêm aggregate mapping nếu dùng Spring Data R2DBC |
| Người quyết định SQL | Lập trình viên | Chủ yếu provider, có thể dùng JPQL/native SQL | Lập trình viên hoặc template/repository |
| Thao tác kết quả | Giá trị/list đồng bộ | Entity managed hoặc projection đồng bộ | `Mono`/`Flux` |
| Mô hình I/O | Blocking JDBC | Blocking JDBC | Non-blocking qua driver R2DBC |
| Connection | `DataSource` | `DataSource` qua provider | `ConnectionFactory` |
| Transaction tiêu biểu | `DataSourceTransactionManager` / `JdbcTransactionManager` | `JpaTransactionManager` | `R2dbcTransactionManager` |
| Quản lý thay đổi entity | Tự viết SQL | Dirty checking/flush | Không có JPA persistence context |
| Độ minh bạch SQL | Rất cao | Cần quan sát SQL generated | Cao với `DatabaseClient` |
| Chi phí học/vận hành | SQL, mapping, pool | Entity lifecycle, fetch, cache, flush | Reactive composition, context, driver/pool |
| Phù hợp nhất | Query rõ ràng, báo cáo, bulk, SQL tinh chỉnh | Domain entity/relationship, CRUD phức tạp | Pipeline reactive từ đầu đến cuối, workload I/O phù hợp |
| Rủi ro thường gặp | SQL lặp, mapping thủ công | N+1, lazy/flush, memory | Blocking lẫn vào flow, subscription sai, pool/driver |

**Không có stack thắng mọi tình huống.** JPA tăng năng suất khi domain có quan hệ phức tạp; JDBC đơn giản và hiệu quả khi SQL là trung tâm; R2DBC hữu ích nếu ứng dụng đã thực sự có kiến trúc reactive cùng driver phù hợp. Đo latency/throughput trong workload thực tế trước khi kết luận.

## 7. Transaction: phần giống và phần khác

Spring cung cấp API `@Transactional` chung ở tầng khai báo, nhưng phía dưới cần đúng transaction manager và đúng resource.

### 7.1. Trong thế giới blocking

- JDBC: `DataSourceTransactionManager` (hoặc `JdbcTransactionManager`) điều phối connection từ `DataSource`. Các API JDBC của Spring tra cứu connection tham gia transaction qua cơ chế của Spring.
- JPA: `JpaTransactionManager` điều phối `EntityManager`/persistence context và transaction của provider. JPA và JDBC **có thể** phối hợp trong một transaction cục bộ nếu cấu hình cùng `DataSource`, manager thích hợp và dùng API JDBC tham gia transaction; không tự suy luận khi có nhiều manager.
- Mặc định `@Transactional` dùng propagation `REQUIRED`, isolation theo database, rollback khi có `RuntimeException` hoặc `Error`. Checked exception thường không rollback theo mặc định nếu chưa cấu hình `rollbackFor` hoặc quy tắc rollback khác.
- `@Transactional(readOnly = true)` là chỉ dẫn tối ưu/hint và có thể ảnh hưởng flush/connection tùy hệ thống, **không phải** hàng rào bảo mật tuyệt đối chống lệnh ghi.
- Transaction nên đặt ở **service operation** có ý nghĩa nghiệp vụ, không trải dài qua network call, chờ người dùng hoặc xử lý rất lâu.

### 7.2. Trong thế giới reactive

- `R2dbcTransactionManager` quản lý transaction cho một `ConnectionFactory`; connection được liên kết với subscriber context.
- Các bước trong **một reactive chain** phải cùng tham gia context, không tự `subscribe()` rời rạc. `TransactionalOperator` hoặc reactive `@Transactional` bọc publisher được trả về.
- Thao tác JDBC/JPA không tự tham gia R2DBC transaction. Khi cần phối hợp hai loại resource hay nhiều hệ thống, cần chiến lược nhất quán như outbox/saga/compensation hoặc cơ chế giao dịch phân tán được thiết kế rõ; tránh giả định annotation sẽ tạo atomic commit xuyên hai stack.

### 7.3. Ví dụ logic nghiệp vụ

Giả sử “tạo đơn hàng và trừ tồn kho” phải thành công hoặc thất bại cùng nhau. Nếu cả hai dùng **cùng DataSource/JPA manager**, đặt ranh giới transaction ở service để commit/rollback chung. Nếu một bước ghi bằng JDBC và bước kia bằng R2DBC **với hai manager**, hai thay đổi không tự atomic dù cùng là một database. Chọn một stack cho một transaction cục bộ hoặc thiết kế cơ chế nhất quán phù hợp.

## 8. Spring Framework, Spring Data và Spring Boot nằm ở đâu?

Dễ nhầm vì các tên đều bắt đầu bằng “Spring”:

| Tầng | Thành phần | Ý nghĩa |
| --- | --- | --- |
| Spring Framework | `spring-jdbc`, `JdbcTemplate`, `JdbcClient` | Core JDBC abstractions, SQL, mapping và resource handling |
| Spring Framework | `spring-orm`, tích hợp JPA/`JpaTransactionManager` | Tích hợp provider ORM/JPA vào IoC và transaction |
| Spring Framework | `spring-r2dbc`, `DatabaseClient` | Core reactive relational access |
| Spring Data | Spring Data JPA / `JpaRepository` | Tạo repository dựa trên JPA |
| Spring Data | Spring Data JDBC | Mapping aggregate đơn giản trên JDBC, **không** phải alias của `JdbcTemplate` và không có JPA dirty checking |
| Spring Data | Spring Data R2DBC / `R2dbcEntityTemplate` | Mapping aggregate và repository reactive trên R2DBC |
| Spring Boot | Auto-configuration, starter, properties | Ghép dependencies và cấu hình mặc định theo classpath/bean |

Với Boot, các starter hay gặp là `spring-boot-starter-jdbc`, `spring-boot-starter-data-jpa`, `spring-boot-starter-data-r2dbc`. Sử dụng starter không có nghĩa mọi API và manager đều tự hoạt động đúng khi phối hợp nhiều nguồn dữ liệu. Đọc cấu hình thực tế: bean `DataSource`, `ConnectionFactory`, entity manager factory, transaction manager, driver, schema migration và profile.

## 9. Cách chọn stack qua tình huống

**Tình huống A — Báo cáo phức tạp, nhiều join/aggregation:** Bạn đã có SQL được tối ưu và cần DTO. **Spring JDBC/`JdbcClient`** thường rõ ràng: truy vấn kiểm soát được, mapping thẳng sang DTO; JPA native query cũng khả thi nhưng không nhất thiết thêm giá trị.

**Tình huống B — Ứng dụng nghiệp vụ với entity và quan hệ:** Đơn hàng, khách hàng, dòng hàng cùng quy tắc sửa đổi trong một transaction. **JPA** hợp lý nếu nhóm hiểu fetch strategy, dirty checking và kiểm soát SQL. Dùng projection/JDBC cho màn hình báo cáo khi thấy JPA kém phù hợp.

**Tình huống C — Dịch vụ WebFlux end-to-end, nhiều I/O đồng thời:** Khi chuỗi HTTP → service → database đều reactive và có driver R2DBC ổn định, **R2DBC** là lựa chọn tự nhiên. Cần đo pool saturation, driver support và truy vấn thật; reactive không làm database chạy query nhanh hơn.

**Tình huống D — Database/driver chỉ hỗ trợ JDBC hoặc thư viện ORM bắt buộc:** Ưu tiên JDBC/JPA. Nếu ứng dụng web dùng reactive API ở ngoài, phải thiết kế ranh giới chạy blocking rõ ràng hoặc chấp nhận kiến trúc imperative cho phần đó; không ép R2DBC khi hệ sinh thái thiếu hỗ trợ.

**Tình huống E — Hệ thống dùng JPA nhưng có batch import hàng triệu bản ghi:** Giữ JPA cho phần domain, cân nhắc `JdbcTemplate.batchUpdate`/SQL set-based cho tác vụ đặc thù, với transaction và consistency được thiết kế rõ. Không tải hàng triệu entity vào một persistence context.

Quy trình quyết định hữu ích:

1. **Đầu vào:** Ứng dụng imperative hay reactive thực sự? Driver tương thích? Cần ORM relationship hay chỉ query/DTO?
2. **Mô hình nhất quán:** Một transaction cục bộ hay nhiều resource? API quản lý transaction nào đang dùng?
3. **Đặc tính truy vấn:** CRUD entity, SQL chuyên biệt, bulk import hay luồng đọc lớn? Cần xem index/execution plan.
4. **Vận hành:** Pool size, timeout, số query/request, tracing, exception handling, khả năng test theo DB thực.
5. **Thử tải:** So sánh độ trễ p95/p99, throughput, thread/connection sử dụng và CPU/database load bằng cùng workload.

## 10. Hiệu năng, bảo mật và lỗi thường gặp

### 10.1. Truy vấn và bảo mật

- **Bind parameter, không nối chuỗi từ input:** `WHERE id = :id`, `WHERE id = ?` và `bind("id", value)` giúp truyền giá trị an toàn. Với tên bảng/cột/`ORDER BY` động, placeholder thường không thay thế identifier: dùng allowlist cứng thay vì ghép input tùy ý.
- **Pagination đúng cách:** Có `ORDER BY` xác định; cân nhắc keyset pagination cho dữ liệu lớn. Dù dùng ORM hay reactive, query không phân trang có thể gây tải lớn.
- **Query plan:** Index và hình dạng SQL ảnh hưởng nhiều hơn việc chọn template/provider. Giới hạn cột đọc, projection và tránh fetch graph quá rộng.
- **Transaction isolation:** Chọn theo yêu cầu nhất quán và khả năng DB; hiểu lock, deadlock, retry/idempotency khi cập nhật đồng thời.
- **Connection pool:** Thiếu pool hoặc pool quá lớn đều có hại. Theo dõi active/idle/waiting connection, timeout, số connection tối đa của database.

### 10.2. Các hiểu lầm cần tránh

| Hiểu lầm | Điều đúng cần nhớ |
| --- | --- |
| “JPA không dùng SQL.” | Provider sinh và chạy SQL; vẫn phải quan sát query và tối ưu schema/index. |
| “`save()` luôn chạy `UPDATE` ngay lập tức.” | Trong JPA, thay đổi có thể được flush sau; cơ chế phụ thuộc entity state và thời điểm flush. |
| “Đặt `@Transactional` là đủ.” | Phải có transaction manager phù hợp, đi qua proxy/khung reactive hợp lệ và đúng resource. |
| “R2DBC là Hibernate reactive.” | R2DBC là driver SPI/reactive SQL; Spring Data R2DBC không mang JPA persistence context. |
| “`Mono` giúp JDBC hết blocking.” | Bao bọc kiểu trả về không đổi bản chất JDBC blocking. |
| “Reactive luôn có throughput cao hơn.” | Còn tùy DB, driver, pool, mức đồng thời, CPU và truy vấn; phải benchmark. |
| “Đọc entity trong service rồi trả thẳng cho JSON là tốt.” | Có thể phát sinh lazy query, vòng tham chiếu hoặc lộ dữ liệu; dùng DTO phù hợp. |
| “Một transaction annotation bao trùm JDBC và R2DBC.” | Hai mô hình có manager/context khác nhau; không tự có atomicity. |

### 10.3. Quan sát khi có sự cố

- **JDBC:** Log truy vấn có chọn lọc, số connection đang chờ, slow query, timeout, exception translation; lưu ý connection leak do code tự mở JDBC ngoài Spring.
- **JPA:** Theo dõi SQL/count per request, N+1, flush bất ngờ, số entity trong persistence context, query plan. Đừng bật SQL chi tiết chứa dữ liệu nhạy cảm ở production.
- **R2DBC:** Theo dõi subscription, pool acquisition timeout, lỗi driver/connection, query latency, blocking call trên event-loop, context transaction bị tách. Kết hợp trace ứng dụng với metrics database.

## 11. Kiểm thử đúng đặc tính mỗi stack

1. **Spring JDBC:** Test mapping và SQL thật với embedded DB cho case cơ bản; nếu phụ thuộc dialect, constraint hay isolation đặc thù thì dùng database tương thích production (ví dụ Testcontainers). Trong Spring Boot, `@JdbcTest` hỗ trợ test slice JDBC.
2. **JPA:** Test entity mapping, flush và query count; dùng `@DataJpaTest` trong Boot và kiểm tra lazy/N+1 cùng transaction boundary. Test chỉ mock repository không chứng minh SQL thực tế.
3. **R2DBC:** Test reactive publisher bằng Reactor `StepVerifier` (nếu thêm `reactor-test`), test rollback của `TransactionalOperator` và driver/pool đúng môi trường; Boot có `@DataR2dbcTest`.
4. **Chung:** Cần test lỗi unique constraint, 0 hàng, nhiều hàng, concurrent update và behavior rollback. H2 thuận tiện để học nhưng không thay thế hoàn toàn PostgreSQL/MySQL/Oracle khi cần xác thực SQL dialect và locking.

### Bài tập tự kiểm tra

- **Bài 1:** Chuyển ví dụ JDBC ở mục 3 thành `record Book(long id, String title)` và `RowMapper<Book>`; thêm `WHERE id = ?`. Dự đoán kết quả khi không có hàng và khi gọi API yêu cầu một hàng.
- **Bài 2:** Với hai entity `Order`/`OrderLine`, phân tích nơi có thể xuất hiện N+1 khi đọc 100 orders; đề xuất projection hoặc fetch strategy và cách đo số câu SQL.
- **Bài 3:** Viết trên giấy cùng một API “tìm tiêu đề theo id” bằng `JdbcClient` (trả `Optional<String>`) và `DatabaseClient` (trả `Mono<String>`). Ai quyết định subscription? Chọn transaction manager nào?
- **Bài 4:** Giải thích vì sao một service viết bằng JDBC rồi gọi một R2DBC repository không tự có transaction xuyên cả hai thao tác. Nêu một cách thiết kế lại để bảo đảm nghiệp vụ.
- **Bài 5:** Chọn stack cho import dữ liệu lớn, ứng dụng CRUD nhiều quan hệ và dịch vụ WebFlux có driver R2DBC; viết giả định và phép đo cần thiết trước khi chốt.

## 12. Checklist trước khi chọn và triển khai

- [ ] Xác định chính xác Spring Framework API nào, Spring Data module nào và driver nào sẽ dùng.
- [ ] Chọn blocking hay reactive theo **toàn đường xử lý**, không dựa vào tên API.
- [ ] Ghi rõ ai sở hữu SQL, entity state, mapping, schema migration và transaction.
- [ ] Xác định đúng `DataSource`/`ConnectionFactory`, transaction manager và connection pool.
- [ ] Dùng parameter binding và DTO/projection; kiểm tra query plan, pagination và quyền database.
- [ ] Test với truy vấn thực, transaction rollback, failure mode và database tương thích.
- [ ] Đo SQL count, p95/p99 latency, throughput, connection pool và khả năng mở rộng dưới tải.
- [ ] Khi phối hợp nhiều stack, mô tả tường minh ranh giới transaction và eventual consistency.

**Ghi nhớ:** Spring JDBC tối ưu cho **SQL tường minh**; JPA/ORM tối ưu cho **mô hình entity được quản lý**; R2DBC tối ưu cho **I/O quan hệ theo mô hình reactive**. Sự lựa chọn đúng bắt đầu từ yêu cầu domain, kiểu xử lý và database, rồi được kiểm chứng bằng SQL, test và số liệu vận hành.

## Tài liệu chính thức để đọc tiếp

- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
- [Spring Framework — ORM/JPA](https://docs.spring.io/spring-framework/reference/data-access/orm.html)
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Data JPA](https://docs.spring.io/spring-data/jpa/reference/)
- [Spring Data R2DBC](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
