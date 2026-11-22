# Ảnh hưởng của read-only transaction tới flush và tối ưu hóa ORM trong Spring Framework

## 1. Bài toán: đọc dữ liệu nhưng ORM vẫn phải quản lý entity

Một service Spring sử dụng JPA/Hibernate thường load hàng chục hoặc hàng nghìn entity để dựng báo cáo, API response hoặc danh sách. Khi các entity ở trạng thái **managed**, ORM có thể lưu bản chụp (snapshot) trạng thái ban đầu, theo dõi thay đổi và kiểm tra xem có phải tạo lệnh `UPDATE` hay không. Việc này có chi phí bộ nhớ và CPU, dù nghiệp vụ chỉ muốn đọc.

Spring cho phép khai báo ý định:

~~~java
@Transactional(readOnly = true)
public BookDto loadBook(long id) {
    // Đọc và trả dữ liệu, không chủ ý thay đổi DB.
}
~~~

Đoạn trên **chỉ minh họa cú pháp**, chưa phải chương trình độc lập. Tùy Spring transaction manager và ORM provider, `readOnly = true` có thể chuyển xuống tầng JDBC và Hibernate như một **gợi ý tối ưu hóa**. Trong cấu hình Spring + Hibernate thông dụng, nó còn tác động đến **flush mode** và **dirty checking**.

Câu hỏi bài này trả lời:

1. **Flush** là gì và khác **commit** ở đâu?
2. Vì sao `readOnly=true` thường khiến Hibernate dùng `FlushMode.MANUAL`?
3. Vì sao Hibernate có thể giảm dirty checking/snapshot cho entity được load trong read-only transaction?
4. Vì sao `readOnly=true` **không phải khóa an toàn** ngăn mọi lệnh `INSERT`, `UPDATE` hoặc `DELETE`?
5. Khi nào lợi ích này có hiệu lực, khi nào bị hạn chế bởi propagation, persistence context và transaction manager?
6. `timeout` tác động gì tới truy vấn dài, bước flush và hiệu năng?
7. Làm sao viết một ví dụ Java 17+ để kiểm tra **giá trị trong object** và **dữ liệu thực sự đã commit**?

Phạm vi chính: **Spring Framework Transaction Management + Spring Data JPA/Hibernate ORM** với transaction imperative trên thread. Những chi tiết riêng của Hibernate sẽ được gọi rõ tên, không xem chúng là quy tắc bắt buộc cho mọi JPA provider.

## 2. Phân biệt persistence context, dirty checking, flush và commit

Bốn khái niệm liên quan nhưng không đồng nghĩa.

### 2.1. Persistence context và managed entity

Trong JPA, `EntityManager` quản lý một **persistence context**, thường giữ các entity đã được load bằng `find` hoặc JPQL query. Một entity **managed** có thể được Hibernate quan sát khi thuộc tính thay đổi.

~~~java
Book book = entityManager.find(Book.class, 1L);
book.setTitle("New title");
// Đã đổi object Java; chưa thể kết luận có UPDATE SQL hay commit.
~~~

Đây là **mảnh mã minh họa** bên trong một transaction phù hợp. Không cần gọi `repository.save(book)` cho mọi thay đổi trên managed entity: trong read-write transaction, Hibernate có thể phát hiện sự thay đổi và flush thành SQL sau đó.

### 2.2. Dirty checking

**Dirty checking** là quá trình ORM xác định entity managed nào đã thay đổi so với trạng thái được tải/đồng bộ trước đó.

Với Hibernate, khi sử dụng snapshot-based dirty checking, ORM có thể so sánh trạng thái hiện tại và snapshot. Bytecode enhancement có thể theo dõi các thuộc tính đã được sửa để giảm chi phí so sánh, nhưng không làm dirty checking biến mất hoàn toàn.

Các chi phí có thể gồm:

- Lưu trạng thái của nhiều managed entities trong persistence context.
- So sánh hoặc theo dõi thuộc tính thay đổi lúc flush.
- Duy trì action queue, xử lý quan hệ/cascade và thứ tự SQL.
- Tăng lượng heap, thời gian GC và thời gian giữ transaction nếu một lần đọc load quá nhiều entity.

Với truy vấn đọc dài, có thể chỉ cần chuyển entity thành DTO/projection rồi trả về. Nếu không có chủ ý ghi, một số công việc ORM trên là chi phí có thể giảm.

### 2.3. Flush: đồng bộ trạng thái đang quản lý thành SQL

**Flush** yêu cầu ORM đồng bộ các thay đổi pending từ persistence context xuống database, thường bằng các `INSERT`, `UPDATE` và `DELETE` thích hợp. Flush **không nhất thiết là commit**.

~~~text
Entity managed bị đổi thuộc tính
  -> Hibernate xác định pending changes
  -> FLUSH: gửi SQL vào DB transaction
  -> COMMIT: kết thúc transaction, làm thay đổi có hiệu lực bền vững
~~~

Ví dụ trong một transaction:

~~~java
book.setTitle("Draft");
entityManager.flush(); // Có thể phát UPDATE SQL ngay.
throw new IllegalStateException("rollback");
// Transaction rollback: UPDATE đã flush vẫn bị hoàn tác.
~~~

Đoạn này là **mã minh họa**, chỉ đúng khi entity có thể được cập nhật, có actual transaction và không có cơ chế khác ngăn flush. `flush()` không biến thay đổi thành committed state. Trong đa số trường hợp, chỉ sau commit thành công mới có thể nói transaction đã hoàn tất.

### 2.4. Flush tự động tùy mode

JPA chuẩn có `FlushModeType.AUTO` và `FlushModeType.COMMIT`. Hibernate còn có các giá trị riêng như `FlushMode.AUTO`, `COMMIT`, `MANUAL` và `ALWAYS` (tùy phiên bản).

- **`AUTO`**: Hibernate có thể flush trước khi commit và trước truy vấn khi cần để kết quả truy vấn phản ánh pending changes. Không có quy tắc “mọi SELECT đều flush”.
- **`COMMIT`**: trì hoãn việc tự flush chủ yếu đến commit; hành vi trước query phụ thuộc JPA/provider.
- **`MANUAL`** (Hibernate-specific): Hibernate không tự flush theo những trigger thông thường; người dùng phải flush tường minh nếu muốn đồng bộ pending state. Tuy nhiên các lệnh SQL tường minh, sequence/identity handling hoặc cơ chế khác vẫn có thể gửi SQL.
- **`ALWAYS`** (Hibernate-specific): có thể flush thường xuyên hơn, kể cả trước truy vấn.

**Chú ý về tên API:** `jakarta.persistence.FlushModeType` không có `MANUAL`. Nếu viết `FlushModeType.MANUAL`, code không biên dịch. Giá trị MANUAL trong bài là `org.hibernate.FlushMode.MANUAL`.

## 3. `@Transactional(readOnly = true)` thực sự làm gì?

Spring `@Transactional(readOnly = true)` biểu đạt **ý định**: transaction này chủ yếu chỉ đọc. `readOnly` là một transaction attribute, được transaction manager xử lý khi transaction được tạo hoặc tài nguyên được chuẩn bị.

Với **Spring + Hibernate/JPA** trong cấu hình phổ biến:

1. Spring transaction infrastructure nhận được thuộc tính `readOnly=true`.
2. `JpaTransactionManager`/`HibernateJpaDialect` có thể áp metadata xuống JDBC connection dưới dạng `Connection.setReadOnly(true)`, nếu dialect/connection handling cho phép.
3. Hibernate flush mode của Session được đặt thành **`MANUAL`**, giảm/loại bỏ automatic flush trong read-only scope.
4. Với transaction-local `EntityManager` do Spring chuẩn bị, Hibernate Session còn có thể được đặt **`setDefaultReadOnly(true)`**. Các entity được load sau đó mặc định read-only; Hibernate không cần dirty-check các thuộc tính đơn giản của những entity ấy theo cách như read-write entities.

**Giá trị chính là giảm công việc của ORM khi đọc**, đặc biệt với nhiều managed entities. Nhưng không coi những bước này là cam kết giống nhau giữa tất cả Spring/Hibernate versions, JPA providers, transaction managers và cách mở EntityManager.

### Ba tầng cần phân biệt

| Tầng | Dấu hiệu read-only | Ý nghĩa chính |
| --- | --- | --- |
| Spring transaction metadata | `@Transactional(readOnly = true)` hoặc `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Spring/caller khai báo transaction này chỉ đọc. |
| Hibernate Session | `Session.getHibernateFlushMode() == MANUAL`, `Session.isDefaultReadOnly()` | Giảm auto flush, có thể mặc định không dirty-check entity được load sau đó. |
| JDBC/database | `Connection.setReadOnly(true)` hoặc một DB read-only transaction mode | Gợi ý/thiết lập trên connection; mức enforce phụ thuộc driver, DB và cấu hình. |

**Không tầng nào chỉ bằng một boolean đủ để khẳng định 100% mọi đường ghi SQL đã bị khóa.** Có DB thực sự từ chối DML trong read-only transaction, nhưng với nơi khác đây chỉ là hint.

## 4. FlushMode.MANUAL và read-only entity không phải một thứ

Hai tối ưu của Hibernate liên quan nhưng cần tách rời.

### 4.1. `FlushMode.MANUAL`: hạn chế auto flush

Khi Session ở `MANUAL`, Hibernate không tự đồng bộ mọi pending changes theo các trigger `AUTO` thường dùng. Đây là một lý do `@Transactional(readOnly=true)` hữu ích khi load nhiều entity mà không chủ ý ghi.

Tuy nhiên:

- `entityManager.flush()` có thể yêu cầu đồng bộ thay đổi của **các entity còn modifiable**.
- Bulk JPQL/native query là **lệnh thay đổi dữ liệu tường minh**, không phải dirty checking của entity load từ SELECT.
- Hibernate `persist(...)` với identifier generation tùy kiểu và các thao tác khác có thể phát SQL trước lúc bạn nghĩ tới commit.
- Nếu DB dùng read-only enforcement, lệnh DML có thể bị từ chối; nếu DB chỉ nhận JDBC hint, lệnh DML có thể vẫn chạy.

Vậy **MANUAL không tương đương “chặn mọi lệnh ghi”**.

### 4.2. `Session.setDefaultReadOnly(true)`: cách theo dõi entity mới được load

Hibernate còn có trạng thái read-only của **entity**:

~~~java
Session session = entityManager.unwrap(Session.class);
boolean defaultReadOnly = session.isDefaultReadOnly();
boolean entityReadOnly = session.isReadOnly(book);
~~~

Đoạn trên là **ví dụ API**, cần import `org.hibernate.Session` và có `book` là managed entity trong transaction phù hợp.

Khi `defaultReadOnly=true`, những entity được load sau đó **mặc định** có thể được đánh dấu read-only. Hibernate không dirty-check những **thuộc tính scalar thông thường** của read-only entity để tạo UPDATE; snapshot dành cho tracking đơn giản cũng có thể được giảm bớt.

Nhưng:

- Đổi `defaultReadOnly` **không tự đổi trạng thái của entity đã managed trước đó**.
- `Session.setReadOnly(entity, true/false)` có thể thay đổi trạng thái cho một managed instance cụ thể, phải hiểu tác động tới snapshot và sự đồng bộ.
- Thay đổi **collection** hoặc cascade có thể vẫn tạo tác dụng phụ SQL tùy mapping. Hibernate không coi read-only entity là bất biến tuyệt đối ở mọi quan hệ.
- Nếu có second-level cache, entity graph, query hints hoặc extended persistence context, cần kiểm chứng trên chính cấu hình của dự án.

### 4.3. Một object đổi trong RAM không đồng nghĩa DB đổi

Ví dụ:

~~~text
Trong read-only transaction:
  Book được load: title = "Original"
  Java setter:     title = "Modified in memory"
  System.out:      "Modified in memory"
  Database:        vẫn có thể là "Original" sau scope

Trong read-write transaction:
  Book được load: title = "Original"
  Java setter:     title = "Committed"
  Hibernate dirty checking + flush tại commit
  Database:        "Committed" sau commit
~~~

Đây là **sơ đồ khái niệm**, demo ở mục 7 kiểm tra nó trong một cấu hình cụ thể. Không nên xây dựng nghiệp vụ dựa vào việc “setter trong read-only sẽ âm thầm bị bỏ qua”; đó là kết quả phụ thuộc Hibernate và là nguồn gây bug nếu nhóm phát triển vô tình gọi write method bên trong read-only boundary.

## 5. Ma trận: read-write và read-only trong Spring + Hibernate

Giả sử cả hai phương thức đều được gọi qua Spring proxy, **tạo transaction mới**, dùng `JpaTransactionManager` với Hibernate provider và transaction-local `EntityManager`.

| Thành phần | `@Transactional` (read-write) | `@Transactional(readOnly=true)` |
| --- | --- | --- |
| Ý định của service | Có thể thay đổi dữ liệu | Chủ yếu chỉ đọc |
| `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` | Thường `false` | Thường `true` |
| Hibernate flush mode | Thường `AUTO` | Thường `MANUAL` |
| Hibernate defaultReadOnly | Thường `false` | Có thể `true` với transaction-local EntityManager |
| Entity mới load | Thường modifiable, theo dõi dirty state | Có thể mặc định read-only, giảm snapshot/dirty checking |
| Setter trên managed entity | Có thể được flush thành `UPDATE` khi commit | Thay đổi scalar của entity read-only thường **không** được đồng bộ |
| Lệnh JPQL/native UPDATE tường minh | Có thể thực thi nếu được phép | **Không tự bị cấm bởi Spring annotation**; DB/driver có thể từ chối |
| `entityManager.flush()` | Đồng bộ pending changes, chưa commit | Vẫn là thao tác flush tường minh; hiệu quả phụ thuộc trạng thái entity và DB |
| Timeout | Theo `timeout`/manager khi tạo transaction | Cũng có thể cấu hình timeout; không phải hệ quả tự động của readOnly |
| Bảo đảm commit/rollback | Phụ thuộc boundary và exception | Vẫn phụ thuộc boundary và exception; không thể suy chỉ từ hint |
| Hiệu năng | Tốt khi cần ghi và dirty checking | Có thể giảm CPU/heap cho truy vấn thuần đọc, cần benchmark |

Dùng các từ **thường**, **có thể** vì đây là tích hợp Spring/Hibernate, không phải API JPA quy định Hibernate flushMode MANUAL cho mọi provider.

## 6. Dùng read-only transaction ở đúng ranh giới service

Một thiết kế thường gặp:

~~~java
@Service
public class CatalogService {
    private final BookRepository books;

    public CatalogService(BookRepository books) {
        this.books = books;
    }

    @Transactional(readOnly = true)
    public BookDto find(long id) {
        Book book = books.findById(id).orElseThrow();
        return new BookDto(book.getId(), book.getTitle());
    }

    @Transactional
    public void rename(long id, String title) {
        Book book = books.findById(id).orElseThrow();
        book.setTitle(title); // Dirty checking trong read-write transaction.
    }
}
~~~

Đây là **mẫu minh họa**, không phải source độc lập: cần định nghĩa `BookRepository` và `BookDto` (được cung cấp riêng nếu áp dụng trong dự án). Điểm quan trọng là đặt transaction boundary ở **service use case**, không dựa vào annotations rải rác ở nhiều repository method mà bỏ qua caller.

### Spring Data JPA có default gì?

Theo tài liệu Spring Data JPA, các phương thức CRUD kế thừa từ `SimpleJpaRepository`:

- Các thao tác **đọc** kế thừa read-only transaction configuration.
- Các thao tác **ghi** được cấu hình transaction read-write.
- **Query method tự khai báo** không được bảo đảm tự có transaction chỉ vì repository là Spring Data interface; nên đặt `@Transactional` thích hợp ở repository hoặc service theo yêu cầu.
- Nếu service ngoài đã mở một transaction, **boundary ngoài** thường quyết định transaction thực sự. Không thể luôn biến một outer read-only transaction thành writable chỉ bằng annotation read-write ở method repository phía trong.

Ví dụ JPQL update cần phân biệt `@Modifying` và transaction:

~~~java
public interface BookRepository extends JpaRepository<Book, Long> {
    @Modifying
    @Transactional
    @Query("update Book b set b.title = :title where b.id = :id")
    int renameById(@Param("id") Long id, @Param("title") String title);
}
~~~

Đây là **mẫu repository minh họa**, cần imports và entity tương ứng. `@Modifying` làm query có ý nghĩa cập nhật; `@Transactional` cung cấp boundary, nhưng nếu một service đã mở read-only transaction và repository join vào đó, annotation tại repository có thể **không ghi đè** flush/connection read-only settings đang tồn tại. Ngoài ra bulk update bypass persistence context của managed entities; cần hiểu stale entity state và yêu cầu clear/refresh.

### Ưu tiên projection khi chỉ cần vài cột

Nếu API chỉ cần `id` và `title`, DTO projection có thể giảm số entity được materialize và tránh quản lý object graph lớn. Read-only transaction giúp tối ưu nếu vẫn load entities, nhưng **không thay thế** việc giới hạn cột, pagination, join strategy, index và fetch plan.

Ví dụ cấu trúc query minh họa:

~~~java
@Query("select new demo.BookSummary(b.id, b.title) from Book b")
List<BookSummary> listSummaries();
~~~

`BookSummary` phải có constructor/record đúng chữ ký. Đây là ví dụ tối ưu số thuộc tính trả về, không phải chứng minh một truy vấn cụ thể nhanh hơn nếu chưa benchmark.

## 7. Demo Maven Java 17+: kiểm tra flush và dữ liệu DB thật

Demo sử dụng **Spring Boot 3.4.4** (tích hợp Spring Framework 6.2.5 và Hibernate ORM qua starter Data JPA), **H2 in-memory**, Java 17+ và Maven. Spring Boot được dùng để cấu hình JPA/Hibernate ngắn gọn, còn cơ chế transaction đang minh họa là **Spring Framework Transaction Management**.

Mục tiêu:

1. Khởi tạo bảng `books` với một hàng `id=1, title=Original`.
2. Gọi `BookService.observeReadOnly()` qua Spring proxy. Hibernate Session được kiểm tra flush mode và read-only flags; code sửa object Java nhưng **không chủ đích ghi DB**.
3. Đọc DB **sau khi read-only transaction kết thúc**: vẫn `Original`.
4. Gọi `BookService.changeInWritableTx()` qua Spring proxy, sửa cùng entity trong writable transaction.
5. Đọc DB **sau commit**: thành `Persisted from write tx`.

### 7.1. Cấu trúc thư mục

~~~text
read-only-flush-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/demo/
        │   ├── ReadOnlyFlushDemo.java
        │   ├── Book.java
        │   └── BookService.java
        └── resources/
            └── application.properties
~~~

### 7.2. Tạo `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>read-only-flush-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
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

BOM của `spring-boot-starter-parent` quản lý các version transitive như Hibernate và H2. Demo không pin từng dependency vì để Boot dùng **bộ dependency versions đã kiểm thử tương thích** trong release 3.4.4. Để lặp lại kết quả, giữ nguyên phiên bản parent này.

### 7.3. Tạo `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:flush_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
logging.level.root=ERROR
~~~

`ddl-auto=create-drop` chỉ dùng cho demo, để Hibernate tạo bảng rồi dọn khi đóng context. **Không** đưa thiết lập này vào production vì nó có thể phá hủy schema/dữ liệu.

`open-in-view=false` giúp ví dụ tránh ngữ cảnh EntityManager được giữ lâu qua request; với CLI không có HTTP, property này chỉ làm ý định rõ ràng.

### 7.4. Tạo `src/main/java/demo/Book.java`

~~~java
package demo;

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

    protected Book() {
        // Constructor JPA cần để tạo entity.
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

Entity được load trong transaction bằng `EntityManager.find(...)`. Trong demo, row ban đầu được thêm trực tiếp qua `JdbcTemplate` nên không cần constructor nhận tham số hoặc `@GeneratedValue`.

### 7.5. Tạo `src/main/java/demo/BookService.java`

~~~java
package demo;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

import org.hibernate.Session;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class BookService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public void observeReadOnly(long id) {
        Session session = entityManager.unwrap(Session.class);
        Book book = entityManager.find(Book.class, id);

        System.out.println("readOnly.flag="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
        System.out.println("readOnly.flushMode="
                + session.getHibernateFlushMode());
        System.out.println("readOnly.defaultReadOnly="
                + session.isDefaultReadOnly());
        System.out.println("readOnly.entityReadOnly="
                + session.isReadOnly(book));

        book.setTitle("Changed only in memory");
        System.out.println("readOnly.objectTitle=" + book.getTitle());
    }

    @Transactional
    public void changeInWritableTx(long id) {
        Session session = entityManager.unwrap(Session.class);
        Book book = entityManager.find(Book.class, id);

        System.out.println("readWrite.flag="
                + TransactionSynchronizationManager.isCurrentTransactionReadOnly());
        System.out.println("readWrite.flushMode="
                + session.getHibernateFlushMode());
        System.out.println("readWrite.defaultReadOnly="
                + session.isDefaultReadOnly());
        System.out.println("readWrite.entityReadOnly="
                + session.isReadOnly(book));

        book.setTitle("Persisted from write tx");
        // Không gọi save() hay flush() tường minh.
        // Hibernate có thể dirty-check và flush khi commit.
    }
}
~~~

Điểm cần quan sát: ở read-only transaction, `Session.getHibernateFlushMode()` được đặt `MANUAL`, `isDefaultReadOnly()`/`isReadOnly(book)` dự kiến `true`. Setter vẫn thay đổi **object Java trong RAM** nhưng Hibernate không tự tạo UPDATE scalar cho entity read-only ở scope này.

Trong writable transaction, Session thông thường dùng `AUTO`, entity được load là modifiable; khi proxy kết thúc, transaction manager commit và Hibernate flush thay đổi `title`.

### 7.6. Tạo `src/main/java/demo/ReadOnlyFlushDemo.java`

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class ReadOnlyFlushDemo {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(ReadOnlyFlushDemo.class, args)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            BookService service = context.getBean(BookService.class);

            jdbc.update(
                    "INSERT INTO books (id, title) VALUES (?, ?)",
                    1L, "Original");

            service.observeReadOnly(1L);
            System.out.println("DB_after_readOnly=" + getTitle(jdbc));

            service.changeInWritableTx(1L);
            System.out.println("DB_after_readWrite=" + getTitle(jdbc));
        }
    }

    private static String getTitle(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT title FROM books WHERE id = 1",
                String.class);
    }
}
~~~

`@SpringBootApplication` bật auto-configuration JPA, DataSource và component scanning trong package `demo`. `BookService` là Spring-managed bean lấy qua context, lời gọi public method qua transaction proxy; **không phải** `new BookService()` hay `this.method()`. Hibernate tạo bảng vì `ddl-auto=create-drop`, sau đó JdbcTemplate insert một row vào DB.

### 7.7. Chạy và stdout mong đợi

~~~bash
mvn -q spring-boot:run
~~~

Những dòng do code `System.out` in, bỏ qua log framework/driver khác:

~~~text
readOnly.flag=true
readOnly.flushMode=MANUAL
readOnly.defaultReadOnly=true
readOnly.entityReadOnly=true
readOnly.objectTitle=Changed only in memory
DB_after_readOnly=Original
readWrite.flag=false
readWrite.flushMode=AUTO
readWrite.defaultReadOnly=false
readWrite.entityReadOnly=false
DB_after_readWrite=Persisted from write tx
~~~

**Giải thích:**

1. `readOnly.flag=true` là metadata Spring công bố cho transaction mới.
2. `flushMode=MANUAL` là tối ưu flush từ `HibernateJpaDialect`. `defaultReadOnly=true` và `entityReadOnly=true` là tối ưu quản lý entity trong cấu hình transaction-local EntityManager.
3. Setter đặt title mới trên **Java object**; dòng `readOnly.objectTitle` chỉ chứng minh object thay đổi. Sau scope, JdbcTemplate query DB vẫn thấy `Original`.
4. `changeInWritableTx` mở read-write transaction mới. Hibernate quản lý snapshot/dirty state và flush thay đổi khi commit; sau đó query DB mới thấy `Persisted from write tx`.
5. Không có `entityManager.flush()` trong demo. Điều đó nhấn mạnh Hibernate có thể tự flush ở read-write transaction, trong khi read-only transaction tránh công việc không cần thiết.

**Giới hạn của kết quả dự kiến:** Các flag `MANUAL/AUTO` và default read-only được dự đoán theo Spring Boot 3.4.4 sử dụng Hibernate/JpaTransactionManager chuẩn. Nếu dự án thay transaction manager, provider, cách tạo EntityManager hoặc gọi trong outer transaction, giá trị có thể khác; không sao chép kết quả này như hợp đồng chung của mọi hệ thống JPA. Ví dụ được thiết kế để biên dịch/chạy nhưng kết quả cần kiểm nghiệm bằng Maven trên môi trường có dependency tương ứng.

## 8. Một read-only transaction có thật sự “không thể ghi”?

**Không bảo đảm.** Đó là một **optimization hint và transaction metadata**, không phải quy tắc phân quyền dữ liệu bắt buộc.

Ví dụ:

~~~java
@Transactional(readOnly = true)
public void dangerousBulkUpdate() {
    entityManager.createQuery(
            "update Book b set b.title = 'Changed' where b.id = 1")
            .executeUpdate();
}
~~~

Đây là **đoạn minh họa rủi ro**, không nằm trong demo hoàn chỉnh. Bulk JPQL update là thao tác DML tường minh, không phụ thuộc hoàn toàn vào dirty checking của một entity được load bằng `find`. Tùy DB/JDBC read-only enforcement, nó **có thể** chạy hoặc bị DB/driver từ chối.

Tương tự, gọi trực tiếp `JdbcTemplate.update(...)` trong read-only service không tự động được Spring AOP biến thành “chỉ đọc”. JDBC connection có thể được gắn flag read-only mà database không thực thi đầy đủ. Muốn **chặn ghi thật sự**, cần dùng quyền DB read-only, read replica, cấu hình database-level read-only transaction khi được hỗ trợ, hoặc chính sách bảo mật thực sự.

### “MANUAL” không phải “không bao giờ flush”

Nếu một Session đang giữ những entity **modifiable** hoặc pending actions khác, lệnh `entityManager.flush()` vẫn là yêu cầu tường minh để đồng bộ. Việc Hibernate không dirty-check simple properties của **entity đã read-only** là tối ưu riêng; đừng trộn lẫn hai cơ chế.

Hibernate read-only entity cũng không có nghĩa mọi collection/cascade/delete đều bị cấm. Khi cần đảm bảo tuyệt đối “hàm này không viết dữ liệu”, test phải kiểm tra truy vấn SQL thực sự và quyền DB, không chỉ đọc một flag.

### Flush không phải commit và không đảm bảo isolation

Nếu writable transaction đã flush UPDATE nhưng sau đó rollback, database hoàn tác thay đổi theo transaction semantics. Nếu gọi `flush()` rồi query trong chính transaction đó, có thể thấy dữ liệu mới; một transaction khác có được nhìn thấy hay không phụ thuộc isolation và commit.

Ngược lại, nếu một entity read-only trong persistence context bị setter đổi giá trị, code Java trong cùng request có thể đọc lại giá trị mới trên object, **dù database vẫn giữ giá trị cũ**. Đây là một lý do không nên cố viết vào entity read-only rồi dựa vào hành vi “không flush” làm business rule.

## 9. Propagation quyết định read-only và flush mode thực tế

`@Transactional(readOnly=true)` có ảnh hưởng mạnh nhất khi Spring **tạo một transaction mới** với tài nguyên/persistence context tương ứng. Nếu method chỉ tham gia transaction đang có, thuộc tính ở method trong không nhất thiết được áp lại lên physical transaction.

### 9.1. Outer write transaction, inner read-only

~~~java
@Service
class Writer {
    private final Reader reader;

    Writer(Reader reader) {
        this.reader = reader;
    }

    @Transactional
    public void update() {
        reader.load(); // Gọi một bean khác qua Spring proxy.
    }
}

@Service
class Reader {
    @Transactional(readOnly = true)
    public void load() {
        // Có thể đang tham gia physical read-write transaction của Writer.
    }
}
~~~

**Mảnh mã minh họa**, không phải chương trình hoàn chỉnh. Với mặc định `Propagation.REQUIRED`, `Reader.load()` tham gia transaction đang có, thay vì tạo mới và chuyển toàn bộ Session sang MANUAL. Đừng suy luận từ annotation tại inner rằng connection/flush mode đang thực sự read-only.

### 9.2. Outer read-only, inner write

~~~java
@Transactional(readOnly = true)
public void outerRead() {
    otherService.updateSomething(); // Method inner @Transactional mặc định.
}
~~~

Nếu inner `REQUIRED` chỉ tham gia physical transaction read-only của outer, việc inner khai báo read-write **không đảm bảo** nâng transaction thành writable. Đây là bug dễ gặp khi đánh dấu `@Transactional(readOnly=true)` ở class service, rồi thêm một phương thức ghi mới mà quên override/đổi boundary thích hợp.

Nếu nghiệp vụ thực sự cần transaction ghi độc lập, có thể cân nhắc `Propagation.REQUIRES_NEW` trên **bean riêng** để mở physical transaction mới với metadata read-write, nhưng phải xét tính nguyên tử nghiệp vụ, connection pool, visibility và exception handling. Không coi REQUIRES_NEW là “cách chữa chung” cho mọi lỗi read-only.

### 9.3. Read-only + SUPPORTS và manager policy

Một method `@Transactional(propagation=SUPPORTS, readOnly=true)` gọi ngoài transaction không mở physical transaction mới. Spring có thể vẫn công bố read-only metadata và synchronization scope. ORM provider có thể dùng thông tin đó khi bind Session, nhưng không được suy ra nó sẽ giống hệt một transaction-local read-only JPA transaction đã bắt đầu.

**Nguyên tắc:** nếu hành vi flush/read-only quan trọng, kiểm tra **transaction boundary thực**, Hibernate Session và SQL trên DB, thay vì suy luận chỉ từ annotation nguồn.

## 10. Timeout ảnh hưởng gì đến flush và truy vấn ORM?

Nhóm bài học còn có **timeout**, nhưng timeout và read-only là hai trục độc lập:

~~~java
@Transactional(readOnly = true, timeout = 5)
public List<BookDto> loadCatalog() {
    // Transaction có ý định chỉ đọc và timeout 5 giây.
}
~~~

Đây là **mảnh khai báo minh họa**, chưa có implementation. `timeout=5` là timeout transaction tính bằng **giây**, không phải milliseconds. Nó được transaction manager dùng khi **mở transaction mới** (thường với REQUIRED không có outer hoặc REQUIRES_NEW). Một inner REQUIRED chỉ join outer không mặc nhiên thay deadline của transaction ngoài bằng timeout mới.

### Timeout KHÔNG có nghĩa gì?

- Không tự chạy một timer luôn có thể ngắt lập tức thread Java sau 5 giây.
- Không bảo đảm hủy mọi CPU task, I/O network hay mọi thao tác DB nếu driver/provider không thực thi được timeout.
- Không tự chuyển Hibernate flush mode sang MANUAL.
- Không biến `readOnly=false` thành `readOnly=true`.
- Không đảm bảo query đã timeout thì DB chưa thực hiện bất kỳ phần việc nào; ứng dụng cần xử lý lỗi/rollback theo manager và driver.

Spring có thể truyền timeout xuống query/statement hoặc kiểm tra deadline khi transaction-aware resource được dùng. JPA có cơ chế query timeout hint (thường milliseconds), nhưng **transaction timeout** và **query timeout** không hoàn toàn tương đương.

Ví dụ câu lệnh JPQL có hint timeout ở cấp query:

~~~java
TypedQuery<Book> query = entityManager.createQuery(
        "select b from Book b order by b.id", Book.class);
query.setHint("jakarta.persistence.query.timeout", 2000); // ms
List<Book> books = query.getResultList();
~~~

Đây là **mảnh mã minh họa**, phụ thuộc provider/driver có hỗ trợ hint. `2000` nghĩa là 2.000 milliseconds; `@Transactional(timeout = 5)` nghĩa là năm giây. Đừng nhầm đơn vị.

### Flush có thể bị ảnh hưởng bởi timeout thế nào?

Trong read-write transaction, Hibernate có thể phát nhiều SQL khi flush trước commit. Nếu quá trình SQL/flush vượt transaction deadline, transaction manager/provider/driver có thể ném exception và transaction có thể rollback. Nhưng việc timeout được thi hành ở **thời điểm nào** phụ thuộc cơ chế thực tế.

Trong read-only transaction với `MANUAL`, giảm auto flush và dirty checking có thể giảm công việc trước commit/query. Đó **không phải** cách sửa một câu SELECT chậm do thiếu index, N+1 queries, join/fetch plan tệ hoặc database lock contention. Cần đo đúng nguồn thời gian.

### Ví dụ anti-pattern

~~~java
@Transactional(readOnly = true, timeout = 2)
public void doWork() throws InterruptedException {
    Thread.sleep(5000);
    // Không được khẳng định chắc chắn thread sẽ bị interrupt
    // chính xác ở giây thứ hai bởi Spring Transaction Management.
}
~~~

Đây là mảnh minh họa không chạy độc lập. Spring timeout không phải Java thread interruption API. Nếu sau đó truy vấn DB, có thể có kiểm tra deadline hay query timeout từ transaction manager.

## 11. Kỹ thuật tối ưu ORM hữu ích hơn việc chỉ bật read-only

Read-only transaction có ích nhất khi **đặt đúng vào truy vấn thực sự chỉ đọc**, nhưng không thay thế các quyết định truy vấn:

| Vấn đề | Giải pháp cần cân nhắc | Vai trò `readOnly=true` |
| --- | --- | --- |
| Load nhiều entity để trả ba trường | DTO projection/select ít cột | Có thể giảm tracking khi vẫn load entity, nhưng không tránh load dư cột |
| N+1 query vì lazy associations | Fetch join, EntityGraph hoặc batch fetching có kiểm soát | Không sửa được N+1 |
| Trả quá nhiều dòng | Pagination/keyset pagination, giới hạn window | Không giảm lượng dữ liệu nếu truy vấn trả cả bảng |
| Quét DB chậm | Index phù hợp, kế hoạch truy vấn, điều kiện filter | Không thay thế query tuning |
| Read-only scan có nhiều entity managed | Read-only transaction, projection, read-only Hibernate query/session, detach/clear theo lô | Có thể giảm snapshot và dirty checking |
| Batch update hàng nghìn entity | Batch size, flush/clear theo lô, bulk DML thận trọng | Không nên bật readOnly nếu cần persist changes |
| Transaction dài, giữ connection/locks lâu | Rút ngắn boundary, phân tách I/O mạng, pagination hợp lý | Có thể giảm flush overhead, không thay isolation/locks |
| Query timeout thường xuyên | Explain plan, index, lock waits, statement/query timeout thích hợp | Có thể giúp ORM CPU nhưng không giải quyết DB contention |

### Hibernate query-level read-only

Nếu chỉ một truy vấn lớn là read-only nhưng service transaction có cả phần ghi, Hibernate có API kiểu:

~~~java
Session session = entityManager.unwrap(Session.class);
List<Book> books = session.createQuery(
        "from Book", Book.class)
        .setReadOnly(true)
        .getResultList();
~~~

Đây là ví dụ API provider-specific, không đồng nghĩa mọi entity đã managed trước truy vấn sẽ đổi trạng thái. Dùng Hibernate query read-only phải hiểu tác động lên dirty checking của những entity cụ thể; không nên ghi trên chúng rồi mặc định các setter sẽ được flush.

### Tránh tối ưu khi chưa có số đo

Một số triệu chứng tưởng do flush nhưng thực ra là:

- SQL query chậm do index/plan, không phải dirty checking.
- N+1 SELECT quá nhiều, flush mode không giảm số query.
- Entity graph quá lớn do fetch eager không cần thiết.
- Transaction dài vì gọi HTTP/network trong scope.
- Lock wait ở DB khiến commit chậm.
- Bị bật SQL logging/bind logging quá chi tiết trong benchmark.

Mọi tuyên bố “nhanh hơn X%” cần được đo trong workload cụ thể; không có hệ số tăng tốc mặc định cho `readOnly=true`.

## 12. Cách đo và kiểm thử đúng

### 12.1. Đo SQL và hành vi commit

Trong môi trường kiểm thử có thể bật có chọn lọc:

~~~properties
spring.jpa.show-sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Đây là **cấu hình logging tùy chọn**, không nằm trong file `application.properties` của demo để giữ stdout dễ đọc. Đừng log bind parameters nhạy cảm trên production.

Đối với một method được cho là read-only, cần quan sát:

1. Có SQL `UPDATE`/`INSERT` bất ngờ không?
2. `Session.getHibernateFlushMode()` là gì?
3. Entity mới được load có `Session.isReadOnly(entity)` không?
4. Dữ liệu DB **sau khi transaction kết thúc** có thay đổi không?
5. Cơ chế quyền DB có thật sự từ chối write khi cần không?

### 12.2. Benchmark workload

So sánh cùng truy vấn với readOnly false/true:

- Thời gian truy vấn DB (đo riêng khi có thể).
- Thời gian xử lý Hibernate ORM, lượng entity managed và heap allocated.
- Số lần flush, entity updates/inserts/deletes và số câu SQL.
- GC pressure, p95/p99 latency và throughput dưới tải thực.
- Ảnh hưởng của cache, connection pool, OSIV và fetch plan.

Hibernate có `Statistics`/metrics phù hợp khi được bật; đo flush count và entity update count có thể có giá trị chẩn đoán. Nhưng **flush count thấp hơn không tự chứng minh DB đã an toàn** hoặc endpoint nhanh hơn.

### 12.3. Bài kiểm thử có giá trị hơn một flag

- **Read-only scope:** load entity, đổi một thuộc tính scalar, kiểm tra DB sau scope; kết quả kỳ vọng đúng theo provider/config đã chọn.
- **Read-write scope:** load và đổi thuộc tính scalar, kiểm tra DB sau commit; có UPDATE đúng.
- **Explicit DML trong read-only:** chạy thử trên database mục tiêu và xác định nó bị cấm hay được phép; không dùng test này để ghi dữ liệu production.
- **Outer read-only, inner write REQUIRED:** kiểm tra transaction được tham gia và kết quả thực sự, không chỉ annotation inner.
- **Timeout:** kiểm tra với một query có thể hủy và timeout tại DB/driver; không thay bằng `Thread.sleep` rồi kết luận timeout hỏng.
- **Rollback sau flush:** gọi `flush()` trong writable transaction rồi ném unchecked exception; xác nhận DB phục hồi sau rollback.

Nếu dùng Spring TestContext với `@Transactional` trên chính test method, nó có thể mở transaction ngoài và rollback sau test. Khi muốn kiểm tra boundary commit/rollback của method đang thử, **đừng vô tình đặt toàn bộ test trong transaction ngoài**.

## 13. Các lỗi phổ biến

| Hiểu nhầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| “`readOnly=true` khóa ghi tuyệt đối” | Direct DML có thể vẫn chạy, tùy DB | Dùng quyền DB hoặc chế độ DB read-only thật để enforce |
| “`flush()` đồng nghĩa commit” | Đọc sai kết quả, không hiểu rollback sau flush | Phân biệt SQL synchronization và final commit |
| “MANUAL không thể có SQL write” | Bỏ qua explicit DML, persist/cascade | Kiểm tra các đường viết SQL thực tế |
| “Setter đổi object tức DB đã đổi” | Trả dữ liệu trong RAM khác DB | Kiểm tra DB sau boundary |
| “Mọi JPA provider dùng MANUAL cho read-only” | Giả định Hibernate-specific thành JPA chuẩn | Đối chiếu transaction manager/provider |
| “Default read-only đổi mọi entity đã managed” | Entity cũ vẫn có state riêng | Kiểm tra `Session.isReadOnly(entity)` |
| “Query read-only làm mọi entity immutable” | Collection/cascade có thể vẫn tác động | Dùng đúng API và test quan hệ |
| “Repository write annotation ghi đè outer read-only” | Join transaction có thể giữ read-only settings | Đặt boundary tại service, xem propagation |
| “Thêm timeout sẽ bỏ qua flush” | Hai cơ chế độc lập | Tối ưu ORM/SQL riêng và đặt deadline đúng |
| “`timeout=5` bằng 5 ms” | Cấu hình sai mức timeout | Spring transaction timeout là giây |
| “Mọi timeout sẽ interrupt thread ngay” | Chờ đợi cơ chế không có | Hiểu manager/JDBC query timeout |
| “Đổi readOnly sẽ sửa N+1” | Vẫn nhiều SELECT | Sửa fetch plan/projection/index |
| “`this.someMethod()` kích hoạt transaction advice” | Annotation method con có thể bị bỏ qua | Gọi qua Spring-managed proxy |
| “Read-only là tốt cho tất cả methods” | Write path có thể mất dirty-check/flush | Chỉ dùng khi method thực sự thuần đọc |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Entity được load trong Hibernate read-only transaction, sau đó setter đổi title. `System.out(book.getTitle())` thấy giá trị mới. Điều này chứng minh DB đã được UPDATE không?

**Đáp án:** Không. Object Java đã thay đổi trong RAM; Hibernate có thể không dirty-check entity read-only và không auto flush. Kiểm tra DB sau khi transaction kết thúc.

**Câu 2.** Tại sao `FlushMode.MANUAL` trong Hibernate không giống `FlushModeType.COMMIT` trong JPA?

**Đáp án:** `MANUAL` là giá trị đặc thù Hibernate, chủ yếu đợi lệnh flush tường minh; `COMMIT` là flush mode JPA với semantics riêng. API JPA `FlushModeType` không có `MANUAL`.

**Câu 3.** Vì sao `@Transactional(readOnly=true)` có thể tăng hiệu năng khi đọc hàng nghìn entity?

**Đáp án:** Có thể hạn chế automatic flush và giảm chi phí snapshot/dirty checking cho entity read-only trong Hibernate. Mức lợi ích phụ thuộc lượng entity và workload thật.

**Câu 4.** Một bulk JPQL UPDATE nằm trong method `@Transactional(readOnly=true)` có chắc bị Spring từ chối không?

**Đáp án:** Không. Read-only là hint/transaction metadata; SQL có thể bị DB cấm hoặc vẫn chạy tùy cấu hình. Muốn enforce phải dựa vào quyền/chế độ DB thích hợp.

**Câu 5.** Inner method `@Transactional` read-write gọi trong outer `@Transactional(readOnly=true)` với `REQUIRED` mặc định. Inner có chắc nhận Session `AUTO` không?

**Đáp án:** Không. Inner có thể join physical transaction read-only của outer; không tự thay metadata/flush mode đã thiết lập. Cần xác định transaction boundary thực.

**Câu 6.** `entityManager.flush()` gửi SQL UPDATE rồi method ném unchecked exception. DB có bắt buộc giữ UPDATE không?

**Đáp án:** Không. Nếu SQL ở trong transaction và transaction rollback, UPDATE bị hoàn tác dù đã flush.

**Câu 7.** `@Transactional(timeout=3)` có nghĩa Spring tự interrupt mọi Java thread đúng sau 3 giây không?

**Đáp án:** Không. Timeout phụ thuộc transaction manager/provider và các thao tác thực thi; không phải một Java thread timer phổ quát.

**Câu 8.** Read-only transaction đã được bật nhưng endpoint vẫn chậm do N+1 SELECT. Có nên chỉ đổi flush mode?

**Đáp án:** Không. N+1 là vấn đề fetch/query plan; cần projection, fetch join, EntityGraph hoặc batch fetching phù hợp và đo lại.

**Câu 9.** Hibernate Session đã `setDefaultReadOnly(true)` sau khi load một entity. Entity cũ tự trở thành read-only không?

**Đáp án:** Không tự động. Default ảnh hưởng entity được load sau đó; có API thay trạng thái riêng cho managed instance.

## Ghi nhớ

- **Flush ≠ commit.** Flush đồng bộ trạng thái thành SQL; commit kết thúc giao dịch. Flush rồi rollback vẫn có thể hoàn tác SQL.
- **Spring readOnly là hint.** Trong Hibernate transaction-local integration, Spring thường đặt `FlushMode.MANUAL` và `Session.setDefaultReadOnly(true)`, qua đó giảm auto flush và dirty checking cho entity mới load.
- **Object state ≠ DB state.** Setter có thể đổi entity trong RAM nhưng không được persist khi entity là read-only.
- **MANUAL không phải write guard.** Explicit DML/operations vẫn có thể thực thi; quyền DB và provider mới quyết định việc ghi có bị chặn.
- **Propagation quan trọng.** Inner REQUIRED join outer có thể không nhận lại read-only/flush settings theo annotation riêng.
- **Timeout không thay flush mode.** Timeout giây của Spring cần được hiểu và kiểm tra ở transaction manager/JDBC provider.
- Tối ưu ORM hiệu quả dựa trên **đo SQL, dirty checking, heap, query plan, fetch strategy và DB state sau boundary**, không dựa vào annotation một cách máy móc.

## Tài liệu tham khảo chính thức

1. Spring Data JPA — [Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): readOnly là hint, Hibernate sử dụng MANUAL flush mode và tối ưu dirty checking.
2. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): readOnly, timeout, propagation và rollback rules.
3. Spring Framework — [`HibernateJpaDialect` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/orm/jpa/vendor/HibernateJpaDialect.html): chuẩn bị Session/JDBC transaction và flush mode.
4. Hibernate ORM 6.6 — [User Guide](https://docs.jboss.org/hibernate/orm/6.6/userguide/html_single/Hibernate_User_Guide.html): persistence context, flush, dirty checking và read-only entities.
5. Hibernate ORM 6.6 — [`Session` Javadoc](https://docs.jboss.org/hibernate/orm/6.6/javadocs/org/hibernate/Session.html): `isDefaultReadOnly`, `setDefaultReadOnly`, `isReadOnly`.
6. Spring Framework — [TransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/TransactionDefinition.html): read-only hint và transaction timeout.
7. Spring Boot — [3.4.4 release](https://spring.io/blog/2025/03/20/spring-boot-3-4-4-available-now/): phiên bản dùng trong ví dụ Maven.
