# Kiểm thử ánh xạ Java Driver và Spring Data Neo4j

## 1. Vì sao ánh xạ đúng quan trọng không kém câu Cypher đúng?

Một truy vấn Cypher có thể chạy thành công và trả đúng các node/relationship trong Neo4j nhưng ứng dụng Java vẫn trả sai dữ liệu. Lỗi không nhất thiết nằm ở database: chúng còn xuất hiện khi mã Java đọc sai kiểu `Value`, quên kiểm tra `null`, ánh xạ nhầm hướng relationship, giả định thứ tự của một collection hoặc dùng entity Spring Data Neo4j (SDN) không phản ánh đúng graph.

Trong mô-đun `DATABASE_ENGINE_GRAPH_NEO4J`, phần **Kiểm thử** này tập trung vào hai đường đi của dữ liệu:

- **Neo4j Java Driver:** ứng dụng tự thực thi Cypher, nhận `Record` và `Value`, rồi chuyển các giá trị sang DTO Java.
- **Spring Data Neo4j:** ứng dụng khai báo entity qua `@Node`, `@Id`, `@Relationship`, repository/`Neo4jClient`; framework chuyển kết quả graph sang object theo quy tắc mapping.

Cả hai đều dùng Neo4j và ngôn ngữ Cypher, nhưng **ranh giới ánh xạ khác nhau**. Một test chỉ chứng minh `RETURN count(n)` đúng không đảm bảo entity `Book` có đủ tác giả. Ngược lại, một unit test mock repository trả `Book` không chứng minh Neo4j thực sự chuyển property `DATE` thành `LocalDate` hay đọc đúng hướng quan hệ.

**Mục tiêu sau bài:**

1. Xác định hợp đồng ánh xạ (*mapping contract*) từ graph sang Java.
2. Viết fixture có đáp án độc lập cho node, relationship, kiểu dữ liệu, giá trị null và collection.
3. Kiểm thử tích hợp Java Driver, gồm `Record`, `Value`, session và database được chọn.
4. Kiểm thử entity/repository SDN với Neo4j thật trong Testcontainers.
5. Phát hiện khác biệt giữa kết quả Driver và SDN mà không nhầm chúng với lỗi Cypher hoặc lỗi giao dịch.
6. Thiết kế negative test, kiểm thử hồi quy và quy trình CI tái lập được.

> **Phạm vi ví dụ:** Java 17+, Neo4j 5.x, Spring Boot 3.x / Spring Data Neo4j 7.x và Testcontainers tương thích. Một số tên gói/lifecycle test đổi trong các phiên bản Spring Boot hoặc Testcontainers mới hơn; luôn đối chiếu BOM và API của dự án. Mã dưới đây là hướng dẫn học tập; bài viết **không tuyên bố đã chạy test trên Neo4j thực tế**.

## 2. Hai tuyến ánh xạ cần kiểm tra

~~~mermaid
flowchart LR
    C["Cypher + dữ liệu graph"] --> D["Neo4j Server"]
    D --> B["Bolt protocol"]
    B --> V["Java Driver: Record / Value"]
    V --> M["Mapper tự viết"]
    M --> T["DTO / API response"]
    B --> S["Spring Data Neo4j"]
    S --> E["@Node / @Relationship entity"]
    E --> U["Service / API response"]
    T --> A["Cùng hợp đồng dữ liệu"]
    U --> A
~~~

Cùng database không đồng nghĩa hai đường sẽ tự trả cấu trúc giống nhau:

| Khía cạnh | Java Driver thuần | Spring Data Neo4j |
|---|---|---|
| Câu Cypher | Do lập trình viên viết trực tiếp | Do repository sinh, `@Query` cung cấp hoặc `Neo4jClient` chạy |
| Dữ liệu trung gian | `Record` / `Value` / `Node` / `Relationship` | Kết quả truy vấn được converter ánh xạ sang entity/projection |
| Chuyển kiểu | Tự gọi `asString()`, `asLong()`, `asLocalDate()`, v.v. | SDN dựa trên metadata và conversion service |
| Null/thuộc tính thiếu | Tự kiểm tra `Value.isNull()` | Ánh xạ theo kiểu field và quy tắc converter |
| Quan hệ | Tự `MATCH` hoặc duyệt path, tự gom thành DTO | `@Relationship` khai báo hướng, type và kiểu collection |
| ID | Tự đọc property/elementId theo Cypher | `@Id` / `@GeneratedValue` theo entity mapping |
| Giao dịch | `Session` + `executeRead/executeWrite` | Spring transaction manager, repository, `Neo4jClient` |
| Rủi ro đặc thù | Sai alias, sai kiểu Value, Result đã đóng | Sai annotation, query không đủ relationship, save làm thay đổi graph ngoài ý định |

**Một hợp đồng dữ liệu chung** sẽ là chuẩn để kiểm thử cả hai đường: một cuốn sách có `isbn`, `title`, `pages`, `publishedOn`, `subtitle` và một tập tác giả được nối bởi quan hệ có hướng.

## 3. Chọn cấp độ kiểm thử: mock chưa chứng minh mapping thật

| Cấp kiểm thử | Nên kiểm tra | Không thể kết luận |
|---|---|---|
| **Unit test mapper thuần** | Logic chuyển từ object đã có sang DTO, kiểm tra null, kiểm tra field | Neo4j driver trả đúng `Record` hay SDN dựng graph đúng |
| **Repository/Driver integration** | Query thật, Bolt, data conversion, annotation, repository, constraint | Hiệu năng mạng production hoặc failover cluster |
| **Service/API integration** | Transaction, response JSON, validation, paging, phân quyền luồng ứng dụng | Tất cả topology production nếu container chỉ một instance |
| **Contract/regression test** | Tính ổn định giữa schema, version Java Driver/SDN/Neo4j | Không thay thế theo dõi p95/locks/I/O khi chạy thật |

Với yêu cầu “kiểm thử ánh xạ”, **integration test có Neo4j thật là bắt buộc ở ít nhất các ca quan trọng**. Mock một `BookRepository` rồi `when(findById(...)).thenReturn(book)` chỉ kiểm tra cách service dùng object được dựng sẵn. Nó **không kích hoạt** converter của SDN hay Bolt của Java Driver.

Neo4j trong **Testcontainers** giúp dùng phiên bản database xác định, data fixture độc lập và cấu hình test phù hợp với CI. Không dùng database production hoặc tự tạo/đổi dữ liệu trong database của đồng nghiệp để kiểm thử.

## 4. Hợp đồng ánh xạ và đáp án cố định

Ta chọn graph sách–tác giả:

~~~mermaid
flowchart LR
    B1["QA007Book B001"] -->|QA007_WRITTEN_BY| A1["QA007Author A01"]
    B1 -->|QA007_WRITTEN_BY| A2["QA007Author A02"]
    B2["QA007Book B002"] -->|QA007_WRITTEN_BY| A2
    B3["QA007Book B003"] -. "không có tác giả" .- Z["∅"]
~~~

### 4.1. Dữ liệu node

| ISBN | title | pages | publishedOn | subtitle |
|---|---|---:|---|---|
| B001 | Cypher Foundations | 120 | 2025-01-05 | An introduction |
| B002 | Spring Data Mapping | 200 | 2025-01-06 | *(không có property)* |
| B003 | Driver Essentials | 80 | 2025-01-07 | *(không có property)* |

Tác giả:

| authorId | name |
|---|---|
| A01 | An |
| A02 | Bình |

Relationships có hướng **từ Book sang Author**:

| from | type | to |
|---|---|---|
| B001 | `QA007_WRITTEN_BY` | A01 |
| B001 | `QA007_WRITTEN_BY` | A02 |
| B002 | `QA007_WRITTEN_BY` | A02 |

### 4.2. Bảng expected results

| Chỉ số hoặc câu hỏi | Đáp án |
|---|---|
| Tổng sách | **3** |
| Tổng tác giả | **2** |
| Tổng quan hệ `QA007_WRITTEN_BY` | **3** |
| Số tác giả của B001 | **2** |
| Số tác giả của B002 | **1** |
| Số tác giả của B003 | **0** |
| ISBN B001 có `pages` | `120L` trong Java |
| `publishedOn` của B002 | `LocalDate.of(2025, 1, 6)` |
| `subtitle` của B002 | `null` |
| Kết quả sau `OPTIONAL MATCH` từ 3 sách | **4 dòng trung gian**: 2 + 1 + 1 dòng không khớp |

**Chú ý:** ba sách khác với bốn **dòng trung gian** sau `OPTIONAL MATCH`. Một test viết `count(*) = 3` sau expand quan hệ sẽ sai; nếu muốn đếm node gốc, dùng `count(DISTINCT b)`.

## 5. Tạo fixture độc lập trên database test

Lệnh dưới đây chỉ để khởi tạo dữ liệu **trong database dùng riêng cho test**. Không chạy phần cleanup/seed nếu label `QA007Book` và `QA007Author` đang được người khác dùng.

### 5.1. Dọn dữ liệu của chính fixture

~~~cypher
MATCH (n)
WHERE n:QA007Book OR n:QA007Author
DETACH DELETE n;
~~~

Có thể tạo unique constraint nhằm xác nhận khóa nghiệp vụ không trùng:

~~~cypher
CREATE CONSTRAINT qa007_book_isbn IF NOT EXISTS
FOR (b:QA007Book) REQUIRE b.isbn IS UNIQUE;
~~~

~~~cypher
CREATE CONSTRAINT qa007_author_id IF NOT EXISTS
FOR (a:QA007Author) REQUIRE a.authorId IS UNIQUE;
~~~

Chờ các index phục vụ constraint đạt `ONLINE` nếu cần kiểm tra hiệu năng hoặc nhập nhiều dữ liệu.

### 5.2. Chèn đúng ba sách, hai tác giả và ba quan hệ

~~~cypher
CREATE
  (b1:QA007Book {
    isbn:'B001',
    title:'Cypher Foundations',
    pages:120,
    publishedOn:date('2025-01-05'),
    subtitle:'An introduction'
  }),
  (b2:QA007Book {
    isbn:'B002',
    title:'Spring Data Mapping',
    pages:200,
    publishedOn:date('2025-01-06')
  }),
  (b3:QA007Book {
    isbn:'B003',
    title:'Driver Essentials',
    pages:80,
    publishedOn:date('2025-01-07')
  }),
  (a1:QA007Author {authorId:'A01', name:'An'}),
  (a2:QA007Author {authorId:'A02', name:'Bình'}),
  (b1)-[:QA007_WRITTEN_BY]->(a1),
  (b1)-[:QA007_WRITTEN_BY]->(a2),
  (b2)-[:QA007_WRITTEN_BY]->(a2);
~~~

### 5.3. Query đối chứng không phụ thuộc Java mapper

~~~cypher
MATCH (b:QA007Book)
OPTIONAL MATCH (b)-[:QA007_WRITTEN_BY]->(a:QA007Author)
RETURN b.isbn AS isbn,
       count(a) AS authorCount,
       collect(a.authorId) AS authorIds
ORDER BY isbn;
~~~

| isbn | authorCount | authorIds |
|---|---:|---|
| B001 | 2 | A01, A02 |
| B002 | 1 | A02 |
| B003 | 0 | [] |

Thứ tự các phần tử bên trong `collect(...)` **không nên coi là được bảo đảm**, trừ khi sắp xếp có kiểm soát trước aggregation. Trong test, so sánh **set** của author IDs hoặc sắp xếp danh sách trước khi khẳng định. Trái lại, thứ tự các record theo `isbn` được xác định bởi `ORDER BY isbn`.

Kiểm tra số node/quan hệ:

~~~cypher
MATCH (b:QA007Book)
WITH count(b) AS books
MATCH (a:QA007Author)
WITH books, count(a) AS authors
MATCH ()-[r:QA007_WRITTEN_BY]->()
RETURN books, authors, count(r) AS relationships;
~~~

Đáp án `books = 3`, `authors = 2`, `relationships = 3`.

## 6. Mapping bằng Java Driver: Record và Value là dữ liệu có kiểu

Trong Java Driver, `Record` chứa tên cột/alias của câu `RETURN`; `Value` chứa kiểu Neo4j cụ thể. Không nên gọi `toString()` để chuyển mọi property vì có thể nhận biểu diễn có dấu ngoặc kép, null hoặc kiểu phức hợp khác với dữ liệu mong muốn.

### 6.1. Bảng kiểu dữ liệu thường gặp

| Cypher/Neo4j | Java Driver | Java DTO |
|---|---|---|
| `STRING` | `value.asString()` | `String` |
| `INTEGER` | `value.asLong()` | `long`/`Long` |
| `FLOAT` | `value.asDouble()` | `double`/`Double` |
| `BOOLEAN` | `value.asBoolean()` | `boolean`/`Boolean` |
| `DATE` | `value.asLocalDate()` | `LocalDate` |
| `DATETIME` có timezone | `value.asZonedDateTime()` | `ZonedDateTime` |
| `LIST<STRING>` | `value.asList(Value::asString)` | `List<String>` |
| `null` | `value.isNull()` | `null` / `Optional` theo API |
| Node | `value.asNode()` | `Node` của Driver, không phải SDN entity |

**Chọn kiểu có chủ đích:** Neo4j lưu integer theo phạm vi 64-bit; không tự ép tất cả sang `int`. `DATE` không phải `DATETIME`: dùng `LocalDate` sẽ giữ đúng ngày mà không giả tạo timezone. Trường bị thiếu và trường gán `null` cùng có thể xuất hiện như một `Value` null khi query trả `b.subtitle AS subtitle`.

### 6.2. DTO chung để đối chiếu hai cách ánh xạ

~~~java
import java.time.LocalDate;
import java.util.Set;

public record BookView(
    String isbn,
    String title,
    long pages,
    LocalDate publishedOn,
    String subtitle,
    Set<String> authorIds
) {}
~~~

`BookView` là contract ứng dụng, **không phải** entity SDN. Nó không giữ `Node`, `Record` hoặc `Result` còn phụ thuộc connection và session.

### 6.3. Hàm ánh xạ Record thành BookView

~~~java
import java.util.Set;
import org.neo4j.driver.Record;
import org.neo4j.driver.Value;

public final class BookRecordMapper {
    public static BookView from(Record record) {
        String subtitle = record.get("subtitle").isNull()
            ? null
            : record.get("subtitle").asString();

        Set<String> authors = Set.copyOf(
            record.get("authorIds").asList(Value::asString)
        );

        return new BookView(
            record.get("isbn").asString(),
            record.get("title").asString(),
            record.get("pages").asLong(),
            record.get("publishedOn").asLocalDate(),
            subtitle,
            authors
        );
    }
}
~~~

Mapper này dựa trên hợp đồng query: phải có các cột `isbn`, `title`, `pages`, `publishedOn`, `subtitle`, `authorIds`. Nếu alias đổi, test phải thất bại thay vì im lặng trả dữ liệu sai.

### 6.4. Query từ Java Driver

~~~java
import java.util.List;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;

public static List<BookView> readBooks(Driver driver) {
    String cypher = """
        MATCH (b:QA007Book)
        OPTIONAL MATCH
          (b)-[:QA007_WRITTEN_BY]->(a:QA007Author)
        RETURN b.isbn AS isbn,
               b.title AS title,
               b.pages AS pages,
               b.publishedOn AS publishedOn,
               b.subtitle AS subtitle,
               collect(a.authorId) AS authorIds
        ORDER BY isbn
        """;

    try (Session session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.executeRead(tx ->
            tx.run(cypher).list(BookRecordMapper::from)
        );
    }
}
~~~

Ở đây Driver tiêu thụ toàn bộ `Result` **trong transaction và session**. Hàm trả về danh sách DTO đã ánh xạ, tránh lỗi đọc cursor sau khi đóng Session. Với tập dữ liệu rất lớn, không nên `list()` tất cả; dùng phân trang hoặc streaming có transaction lifecycle đúng.

### 6.5. Các assertion cụ thể

Giả sử `books = readBooks(driver)`:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.Set;

assertEquals(3, books.size());

BookView first = books.get(0);
assertEquals("B001", first.isbn());
assertEquals(120L, first.pages());
assertEquals(LocalDate.of(2025, 1, 5), first.publishedOn());
assertEquals(Set.of("A01", "A02"), first.authorIds());

BookView second = books.get(1);
assertEquals("B002", second.isbn());
assertNull(second.subtitle());
assertEquals(Set.of("A02"), second.authorIds());

BookView third = books.get(2);
assertEquals("B003", third.isbn());
assertTrue(third.authorIds().isEmpty());
~~~

Test này cùng lúc phát hiện lỗi **alias**, **null**, **kiểu ngày**, **kiểu số** và **hướng quan hệ**. Nhưng nếu tự dựng `books` trong Java thay vì chạy Neo4j, nó không kiểm tra driver/DB integration.

## 7. Mapping Spring Data Neo4j bằng annotation

Spring Data Neo4j ánh xạ label thành entity Java thông qua `@Node`, ID qua `@Id` và relationship qua `@Relationship`. Với fixture, mô hình đọc phù hợp:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("QA007Author")
public class Author {
    @Id
    private String authorId;

    private String name;

    protected Author() {}

    public String getAuthorId() { return authorId; }
    public String getName() { return name; }
}
~~~

~~~java
import java.time.LocalDate;
import java.util.LinkedHashSet;
import java.util.Set;
import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("QA007Book")
public class Book {
    @Id
    private String isbn;

    private String title;
    private Long pages;
    private LocalDate publishedOn;
    private String subtitle;

    @Relationship(
        type = "QA007_WRITTEN_BY",
        direction = Relationship.Direction.OUTGOING
    )
    private Set<Author> authors = new LinkedHashSet<>();

    protected Book() {}

    public String getIsbn() { return isbn; }
    public String getTitle() { return title; }
    public Long getPages() { return pages; }
    public LocalDate getPublishedOn() { return publishedOn; }
    public String getSubtitle() { return subtitle; }
    public Set<Author> getAuthors() { return authors; }
}
~~~

Những entity này có constructor no-arg `protected` để framework dựng object và có getter để assertion. Trong ứng dụng thực có thể dùng constructor/`@PersistenceCreator`, immutable object hoặc record với yêu cầu mapping tương ứng; **không** coi entity trong ví dụ là một mô hình domain production hoàn chỉnh.

### 7.1. Điều gì thực sự được kiểm tra?

- `@Node("QA007Book")` khớp label trên node.
- `@Id String isbn` khớp property `isbn`; **không phải** `elementId` nội bộ.
- `Long pages` nhận số nguyên `120` từ Neo4j.
- `LocalDate publishedOn` nhận giá trị `DATE`.
- `String subtitle` nhận `null` khi property không tồn tại.
- `@Relationship(... OUTGOING)` lấy các tác giả theo đường `(b)-[:QA007_WRITTEN_BY]->(a)`.
- `Set<Author>` không bảo đảm thứ tự tác giả. So sánh qua `authorId`.

**Không dùng giả định lazy loading kiểu Hibernate/JPA.** Cách SDN hydrate quan hệ dựa vào query và converter; một query tùy biến chỉ trả node gốc có thể không tải đủ cấu trúc quan hệ mà entity mô tả.

### 7.2. Relationship có property: trường hợp khác

Nếu relationship chứa property nghiệp vụ như vai trò `role`, có thể cần một lớp `@RelationshipProperties` với `@TargetNode`:

~~~java
import org.springframework.data.neo4j.core.schema.RelationshipId;
import org.springframework.data.neo4j.core.schema.RelationshipProperties;
import org.springframework.data.neo4j.core.schema.TargetNode;

@RelationshipProperties
public class Authorship {
    @RelationshipId
    private Long graphRelationshipId;

    @TargetNode
    private Author author;

    private String role;

    protected Authorship() {}
}
~~~

Để sử dụng class này, field trên `Book` phải được đổi sang `Set<Authorship>` theo mô hình domain tương ứng. **Đừng đặt thêm đồng thời hai field ánh xạ cùng relationship type/direction mà không kiểm tra hành vi mapping.** `@RelationshipId` phục vụ SDN quản lý relationship, không nên xem ID nội bộ là khóa nghiệp vụ ổn định lâu dài. Phần mở rộng này **không áp dụng trực tiếp** cho fixture không có `role`.

## 8. Repository: khác gì với query Driver?

~~~java
import java.util.Optional;
import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface BookRepository
        extends Neo4jRepository<Book, String> {

    Optional<Book> findByIsbn(String isbn);

    @Query("""
        MATCH (b:QA007Book {isbn: $isbn})
        OPTIONAL MATCH
          (b)-[r:QA007_WRITTEN_BY]->(a:QA007Author)
        RETURN b, collect(r) AS rels, collect(a) AS authors
        """)
    Optional<Book> findBookWithAuthors(
        @Param("isbn") String isbn
    );
}
~~~

Trong `findByIsbn`, SDN sinh Cypher từ tên phương thức. Trong `findBookWithAuthors`, câu Cypher tùy biến mang theo node gốc `b` và **danh sách relationship cùng node đích** để SDN có cơ sở dựng entity graph.

**Vì sao phải gom quan hệ?** Nếu một query trả mỗi dòng một `b, r, a` rồi phân trang/ánh xạ tùy tiện, root B001 có thể xuất hiện hai lần hoặc bị nạp thiếu. SDN custom entity mapping cần cấu trúc kết quả phù hợp: một record/node gốc với những node và relationship liên quan đã được thu thập theo quy tắc mapping. Nếu trong entity có thêm relationship khác, custom query này **không tự động chứng minh** đã nạp chúng.

Trong bài này, test ưu tiên `findBookWithAuthors` để kiểm tra một contract **tường minh**. Với derived query `findByIsbn`, cũng cần test để biết SDN phiên bản đang dùng đã sinh truy vấn/hydrate quan hệ thế nào.

## 9. Testcontainers: vì sao nên dùng database thật?

Unit test không mô phỏng đầy đủ Bolt, Neo4j `DATE`, null semantics, graph hydration hay transaction. Testcontainers có thể chạy Neo4j trong Docker cho kiểm thử tích hợp, giúp:

- Cố định phiên bản máy chủ để tái lập lỗi.
- Seed fixture bằng Cypher thay vì dựng graph object giả.
- Kiểm tra Java Driver và SDN **trên cùng database**.
- Dọn dữ liệu giữa các test để giảm phụ thuộc thứ tự.
- Chạy cùng bộ test trong CI có Docker/compatible container runtime.

Một bộ test có thể dùng **một Neo4jContainer tĩnh cho cả test class**, không tạo container mới mỗi test method. Đừng dùng container này cho production; mật khẩu và database test phải tách khỏi secret thật.

### 9.1. Dependencies Maven tham khảo

Nếu ứng dụng Spring Boot 3.x quản lý các bản thư viện qua BOM, cấu hình thường cần:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-data-neo4j</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>neo4j</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.testcontainers</groupId>
  <artifactId>junit-jupiter</artifactId>
  <scope>test</scope>
</dependency>
~~~

Các artifact/version cụ thể của Testcontainers có thể khác ở **nhánh 2.x**; ví dụ tập trung vào API/gói Testcontainers 1.x phổ biến trong Spring Boot 3.x. Giữ các dependency version được khóa qua BOM và kiểm tra hỗ trợ JDK/Neo4j thực tế.

### 9.2. Sử dụng @DataNeo4jTest và DynamicPropertySource

~~~java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.AfterEach;
import org.neo4j.driver.Driver;
import org.neo4j.driver.Session;
import org.neo4j.driver.SessionConfig;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import java.time.LocalDate;
import java.util.Set;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.*;

@DataNeo4jTest
@Testcontainers
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class BookMappingIT {

    private static final String PASSWORD = "test-only-password";

    @Container
    static final Neo4jContainer<?> neo4j =
        new Neo4jContainer<>("neo4j:5.26")
            .withAdminPassword(PASSWORD);

    @DynamicPropertySource
    static void properties(DynamicPropertyRegistry registry) {
        registry.add("spring.neo4j.uri", neo4j::getBoltUrl);
        registry.add("spring.neo4j.authentication.username",
                     () -> "neo4j");
        registry.add("spring.neo4j.authentication.password",
                     () -> PASSWORD);
        registry.add("spring.data.neo4j.database",
                     () -> "neo4j");
    }

    @Autowired Driver driver;
    @Autowired BookRepository repository;

    @BeforeEach
    void seed() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (n)
                    WHERE n:QA007Book OR n:QA007Author
                    DETACH DELETE n
                    """).consume();
                tx.run("""
                    CREATE
                      (b1:QA007Book {
                        isbn:'B001', title:'Cypher Foundations',
                        pages:120, publishedOn:date('2025-01-05'),
                        subtitle:'An introduction'
                      }),
                      (b2:QA007Book {
                        isbn:'B002', title:'Spring Data Mapping',
                        pages:200, publishedOn:date('2025-01-06')
                      }),
                      (b3:QA007Book {
                        isbn:'B003', title:'Driver Essentials',
                        pages:80, publishedOn:date('2025-01-07')
                      }),
                      (a1:QA007Author {authorId:'A01', name:'An'}),
                      (a2:QA007Author {authorId:'A02', name:'Bình'}),
                      (b1)-[:QA007_WRITTEN_BY]->(a1),
                      (b1)-[:QA007_WRITTEN_BY]->(a2),
                      (b2)-[:QA007_WRITTEN_BY]->(a2)
                    """).consume();
                return null;
            });
        }
    }

    @AfterEach
    void clean() {
        try (Session session = driver.session(
                SessionConfig.forDatabase("neo4j"))) {
            session.executeWrite(tx -> {
                tx.run("""
                    MATCH (n)
                    WHERE n:QA007Book OR n:QA007Author
                    DETACH DELETE n
                    """).consume();
                return null;
            });
        }
    }

    @Test
    void driverMapsDateNullAndRelationships() {
        var rows = BookQueries.readBooks(driver);
        assertEquals(3, rows.size());
        assertEquals("B001", rows.get(0).isbn());
        assertEquals(120L, rows.get(0).pages());
        assertEquals(LocalDate.of(2025, 1, 5),
                     rows.get(0).publishedOn());
        assertEquals(Set.of("A01", "A02"),
                     rows.get(0).authorIds());
        assertNull(rows.get(1).subtitle());
        assertTrue(rows.get(2).authorIds().isEmpty());
    }

    @Test
    void sdnHydratesTheSameBook() {
        Book book = repository.findBookWithAuthors("B001")
            .orElseThrow();

        assertEquals("Cypher Foundations", book.getTitle());
        assertEquals(120L, book.getPages());
        assertEquals(LocalDate.of(2025, 1, 5),
                     book.getPublishedOn());

        Set<String> ids = book.getAuthors().stream()
            .map(Author::getAuthorId)
            .collect(Collectors.toSet());
        assertEquals(Set.of("A01", "A02"), ids);
    }

    @Test
    void emptyRelationshipAndMissingPropertyAreHandled() {
        Book book = repository.findBookWithAuthors("B003")
            .orElseThrow();

        assertNull(book.getSubtitle());
        assertTrue(book.getAuthors().isEmpty());
        assertEquals(80L, book.getPages());
    }
}
~~~

**Ghép ví dụ:** Trong test trên, `BookQueries.readBooks(driver)` là hàm ở mục 6.4 (có thể đặt trong class `BookQueries`); `BookView`, `BookRecordMapper`, `Book`, `Author` và `BookRepository` lấy từ các mục trước. Các class thuộc package được test scan thấy. Nếu không dùng class wrapper `BookQueries`, thay bằng tên class thực tế chứa phương thức `readBooks`.

Trong test, `@Transactional(propagation = NOT_SUPPORTED)` được dùng để **tránh phụ thuộc vào rollback tự động của test slice khi seed bằng Driver trực tiếp**. Mỗi lần seed/cleanup ở đây commit độc lập; không trông chờ transaction test sẽ rollback dữ liệu do một `Driver.session()` khác tạo ra. Không chạy song song hai test class có chung labels trong một Neo4jContainer mà không có cơ chế cô lập.

**Giới hạn ví dụ:** Không khai báo credentials hoặc image version như trong đoạn test cho production. Mục đích là minh họa kiểm thử tích hợp có trạng thái dự đoán được. Tùy Spring Boot version có thể cần cấu hình thêm package scan, repository scan hoặc import bean và thay đổi classpath.

## 10. Một nguồn dữ liệu, hai assertion: đối chiếu Driver và SDN

Thay vì viết hai bộ kỳ vọng khác nhau cho Driver và SDN, hãy dùng **same expected contract**:

~~~java
import java.time.LocalDate;
import java.util.Set;

BookView expected = new BookView(
    "B001",
    "Cypher Foundations",
    120L,
    LocalDate.of(2025, 1, 5),
    "An introduction",
    Set.of("A01", "A02")
);
~~~

Chuyển SDN entity về cùng DTO:

~~~java
import java.util.stream.Collectors;

static BookView fromEntity(Book book) {
    return new BookView(
        book.getIsbn(),
        book.getTitle(),
        book.getPages(),
        book.getPublishedOn(),
        book.getSubtitle(),
        book.getAuthors().stream()
            .map(Author::getAuthorId)
            .collect(Collectors.toSet())
    );
}
~~~

Kiểm tra kết quả được đọc từ graph:

~~~java
BookView fromDriver = BookQueries.readBooks(driver)
    .stream()
    .filter(b -> b.isbn().equals("B001"))
    .findFirst()
    .orElseThrow();

BookView fromSdn = fromEntity(
    repository.findBookWithAuthors("B001").orElseThrow()
);

assertEquals(expected, fromDriver);
assertEquals(expected, fromSdn);
~~~

Java `record` có `equals` theo giá trị các thành phần; `Set` so sánh theo phần tử chứ không phụ thuộc thứ tự. Đây là một *differential contract test*: nếu một nhánh ánh xạ khác kết quả mong đợi, cần điều tra **Cypher → converter → DTO** thay vì chấp nhận hai chuẩn khác nhau.

Cẩn thận: hai nhánh cùng sai **theo cùng một cách** vẫn có thể so bằng nhau; vì thế phải giữ **expected literal** có đáp án độc lập, không chỉ `assertEquals(fromDriver, fromSdn)`.

## 11. Những trường hợp mapping dễ sai và negative tests

### 11.1. Sai hướng relationship

Fixture chỉ tạo `(Book)-[:QA007_WRITTEN_BY]->(Author)`. Nếu annotation ghi `INCOMING` thay vì `OUTGOING`, hoặc Cypher tìm `(Author)-[:QA007_WRITTEN_BY]->(Book)`, các tác giả có thể mất khỏi kết quả.

Test nên khẳng định B001 có **đúng A01/A02**, chứ không chỉ kiểm tra object không null. Nếu đổi hướng làm mất dữ liệu, test phải fail.

### 11.2. Sai tên property hoặc alias

Driver query trả `RETURN b.isbn AS bookId` nhưng mapper đọc `record.get("isbn")`: alias bị lệch. SDN entity đổi field `publishedOn` thành `publicationDate` nhưng không khai báo `@Property("publishedOn")`: dữ liệu ngày có thể không được ánh xạ như mong đợi.

Ví dụ dùng tên khác có chủ đích:

~~~java
import org.springframework.data.neo4j.core.schema.Property;

@Property("publishedOn")
private LocalDate publicationDate;
~~~

Đây là **đoạn minh họa thay thế field** trong entity, không phải thêm đồng thời `publicationDate` và `publishedOn`.

### 11.3. Null, absent property và primitive Java

`b.subtitle` không có property nên Driver nhận `Value` null; SDN có thể điền `null` cho `String subtitle`. Ngược lại, khai báo `long pages` primitive làm bạn khó biểu diễn “pages chưa được biết”; dùng `Long` khi dữ liệu có thể thiếu.

Test nên có **một node thiếu property** và **một node đủ property**, không chỉ test “happy path” với tất cả dữ liệu đầy đủ.

### 11.4. Số nguyên 64-bit và miền giá trị

Neo4j `INTEGER` là 64-bit. Nếu code dùng `asInt()` với số ngoài miền 32-bit hoặc field Java `Integer` không phù hợp, có thể mất thông tin hoặc lỗi convert. Unit test với `1` và `2` sẽ không phát hiện tình huống này.

Đối với trường có khả năng vượt 2.147.483.647, dùng `Long`/`asLong()` và kiểm thử cả giá trị biên. Với `FLOAT`, không so sánh tuyệt đối theo biểu diễn số thực khi nghiệp vụ cho phép sai số; dùng tolerance có cơ sở.

### 11.5. Ngày và timezone

`date('2025-01-05')` tương ứng `LocalDate`; `datetime(...)` có timezone nên cần loại Java phù hợp như `ZonedDateTime` hoặc `OffsetDateTime` khi converter hỗ trợ. Không tự chuyển DATE sang `Instant` theo timezone máy test.

Test thời gian nên có timezone rõ ràng và ca biên như chuyển ngày theo vùng giờ. Fixture hiện tại dùng `DATE` để tránh nhập nhằng timezone; bài test `DATETIME` là ca mở rộng.

### 11.6. Collection null, empty và duplicate

`OPTIONAL MATCH` khi B003 không có author tạo một dòng với giá trị `a = null`; `collect(a.authorId)` bỏ qua null, trở thành danh sách rỗng. Đây khác với kết quả query không trả bất kỳ record nào.

Một `Set<Author>` có thể che các relationship trùng mà data model không muốn. Nếu nghiệp vụ đòi quan hệ đơn trị/không trùng, kiểm tra **số relationship thực tế** bằng Cypher và constraint/thiết kế dữ liệu thích hợp, không chỉ dựa vào size của Set.

### 11.7. Đọc đúng nhưng ghi lại có thể làm mất quan hệ

Trong SDN, `repository.save(book)` không luôn đơn thuần là “UPDATE một property”; tùy graph mapping và trạng thái entity, thao tác lưu có thể cập nhật relationship mà entity đang quản lý. Nếu custom query chỉ hydrate một phần graph rồi gọi `save`, có thể ảnh hưởng những relation không được tải.

Vì vậy, cần **test đọc riêng** và **test ghi riêng**. Khi chỉ cập nhật một property theo khóa, đôi lúc một Cypher update có kiểm soát sẽ phù hợp hơn việc round-trip một entity thiếu quan hệ.

## 12. Giao dịch, rollback và tính cô lập trong test

### 12.1. Driver transaction không tự đồng bộ với Spring transaction

~~~mermaid
sequenceDiagram
    participant T as JUnit Test
    participant S as Spring Transaction Manager
    participant D as Java Driver
    participant N as Neo4j
    T->>S: @Transactional test
    T->>D: driver.session().executeWrite()
    D->>N: Transaction riêng → COMMIT
    T->>S: test kết thúc, rollback transaction Spring
    Note over N: Dữ liệu Driver đã commit có thể vẫn tồn tại
~~~

Đừng cho rằng `@Transactional` của test sẽ rollback mọi ghi được tạo bằng Driver trực tiếp. Tùy cấu hình, Driver mở transaction riêng; rollback ở Spring transaction manager không đảo ngược được một transaction khác đã commit. Bài mẫu tắt test transaction tự động và dọn fixture rõ ràng.

### 12.2. Đặt database tường minh

~~~java
try (var session = driver.session(
        SessionConfig.forDatabase("neo4j"))) {
    // Seed/read đúng database test.
}
~~~

Nếu integration test seed database `neo4j` nhưng SDN repository được cấu hình sang database khác, test có thể nhận `Optional.empty()` dù fixture tồn tại. Kiểm tra `spring.data.neo4j.database`, URI Testcontainers và quyền database.

Khi kiểm thử multi-database, dùng **database test có thật** và phù hợp với edition. Không giả định một Neo4j instance luôn hỗ trợ mọi lệnh tạo database ở mọi edition.

### 12.3. Mỗi test phải độc lập

- `@BeforeEach` reset và seed đúng fixture; `@AfterEach` dọn nếu cần.
- Không phụ thuộc thứ tự chạy `testA` trước `testB`.
- Không dùng `MERGE` với ID tái sử dụng rồi giả định số node mới luôn bằng 1.
- Nếu bật JUnit parallel, mỗi test cần database/label namespace riêng hoặc khóa đồng bộ; tránh hai test cùng cleanup của nhau.
- Với external side effects, dùng endpoint giả lập và không nhận transaction rollback như cơ chế hoàn tác HTTP.

## 13. Kiểm thử custom @Query và nạp quan hệ không đầy đủ

Giả sử một repository có hai phương thức:

~~~java
@Query("""
    MATCH (b:QA007Book {isbn:$isbn})
    RETURN b
    """)
Optional<Book> findRootOnly(String isbn);

@Query("""
    MATCH (b:QA007Book {isbn:$isbn})
    OPTIONAL MATCH
      (b)-[r:QA007_WRITTEN_BY]->(a:QA007Author)
    RETURN b, collect(r) AS rels, collect(a) AS authors
    """)
Optional<Book> findWithAuthors(String isbn);
~~~

Câu thứ nhất chỉ trả node gốc, nên **không thể khẳng định** entity được hydrate đầy đủ author graph nếu framework không bổ sung các bước cần thiết. Câu thứ hai cung cấp cấu trúc node/relationship rõ ràng hơn cho việc dựng entity.

Một test nên xác minh:

1. `findWithAuthors("B001")` có A01 và A02.
2. `findWithAuthors("B003")` không có author.
3. Không có book phù hợp thì trả `Optional.empty()`.
4. Query không sinh hai entity `Book` độc lập cho B001 khi có hai relationships.
5. Nếu có thêm loại quan hệ khác trong domain, cần test cách nạp **từng loại**, không coi một `collect` đã đáp ứng tất cả.

Nếu mục tiêu chỉ là trang danh sách sách và số lượng tác giả, **DTO scalar** với `count(a)` là lựa chọn nhẹ hơn hydrate toàn bộ graph. Kiểm thử mapping nên xác nhận **đúng dữ liệu cần trả**, không ép mọi endpoint phải nạp entity graph đầy đủ.

## 14. Kiểm thử hành vi ghi: CREATE, MERGE và save

Ánh xạ đọc có thể đúng nhưng lưu dữ liệu vẫn sai. Xây test riêng cho các hợp đồng ghi:

| Ca kiểm thử | Điều kiện đầu vào | Kỳ vọng |
|---|---|---|
| Tạo mới ID chưa tồn tại | `B004` chưa có trong graph | Có đúng một node B004 với fields tương ứng |
| Cập nhật property | B001 đổi title | ISBN giữ nguyên; số node không tăng; title được lưu |
| Lưu lại cùng ID | Retry một nghiệp vụ đã xử lý | Không nhân bản node nếu thiết kế idempotent |
| Gán tác giả | B003 được thêm A01 | Có quan hệ đúng hướng; các quan hệ khác không mất |
| Gỡ tác giả | B001 bỏ A02 theo nghiệp vụ | Chỉ relationship dự kiến bị thay đổi |
| Vi phạm unique constraint | Tạo node cùng ISBN theo đường ghi cố ý không dùng MERGE | Transaction thất bại và graph không có node trùng |
| Rollback giữa chừng | Lệnh thứ hai lỗi trong cùng transaction | Những thay đổi thuộc transaction đó không được commit |

Đối với SDN `repository.save`, cần xem cách entity xác định trạng thái mới/cũ (`@Id`, `@GeneratedValue`, `@Version` hoặc cơ chế entity state), tránh suy rằng gán sẵn một ID sẽ luôn tạo hoặc luôn cập nhật. Các test phải dựa vào **số node/relationship cuối cùng trong Neo4j** chứ không chỉ kết quả trả về của repository.

Ví dụ một update Cypher có kiểm soát và kiểm tra đáp án:

~~~cypher
MATCH (b:QA007Book {isbn:'B001'})
SET b.title = 'Cypher Foundations Revised'
RETURN b.isbn AS isbn, b.title AS title;
~~~

~~~cypher
MATCH (b:QA007Book)
RETURN count(b) AS books,
       count(DISTINCT b.isbn) AS uniqueIsbns;
~~~

**Đáp án:** B001 có title mới, `books = 3` và `uniqueIsbns = 3`. Reset fixture trước test khác để không làm thay đổi expected title của cả bộ test.

## 15. Kiểm thử những lỗi tương tác giữa Driver và SDN

### 15.1. Trả Result ra ngoài session đã đóng

~~~java
// ANTI-PATTERN: không sao chép vào ứng dụng.
static org.neo4j.driver.Result queryBad(Driver driver) {
    try (var session = driver.session(
            SessionConfig.forDatabase("neo4j"))) {
        return session.run("MATCH (b:QA007Book) RETURN b");
    }
}
~~~

Session đã đóng trước khi caller tiêu thụ cursor. Test nên gọi một service **trả DTO/list** sau khi session đóng, chứng minh dữ liệu hoàn chỉnh và độc lập với connection.

### 15.2. Trộn transaction của Spring và Driver

Nếu một service `@Transactional` của Spring gọi SDN repository rồi gọi Driver `session.executeWrite` độc lập, hai thao tác **không mặc nhiên nằm trong cùng một transaction**. Một thất bại sau khi Driver commit có thể để lại trạng thái nửa vời. Viết test integration mô phỏng lỗi giữa hai bước để hiểu đúng ranh giới; nếu cần atomicity, sử dụng một transaction manager/phạm vi thống nhất.

### 15.3. Không xử lý result và summary

Với lệnh ghi qua Driver, dùng `consume()` hoặc tiêu thụ result đúng cách trước khi kết thúc transaction. Với SDN, test cần xác nhận state đã commit và re-read qua transaction mới. Đừng dùng một object Java đang nằm trong bộ nhớ làm bằng chứng rằng database đã lưu.

### 15.4. Sai tenant/database

Driver test đọc từ `neo4j` trong khi SDN test dùng database khác có thể tạo ảo giác mapping sai. Ghi rõ DB đích trong cả hai tuyến và xác minh trạng thái bằng một query chỉ đọc có database name được chỉ định.

## 16. Kiểm thử chất lượng truy vấn kèm mapping

Một kết quả có thể đúng trên fixture 3 node nhưng rất chậm khi graph lớn. Tách hai loại assertion:

| Nhóm | Assert gì? | Cách đo |
|---|---|---|
| **Functional mapping** | ID, property, kiểu ngày, null, số tác giả, direction | JUnit/Testcontainers, expected literal |
| **Query plan** | Dùng index nào, Rows/DB Hits, expand hay scan | `EXPLAIN`, `PROFILE` trên dataset đủ đại diện |
| **N+1** | Số truy vấn phụ khi số root tăng | Query logging/tracing trong test |
| **Over-fetch** | Số record/relationship thực nạp so với API cần | Driver summary, tracing và response payload |
| **Latency** | p50/p95 khi database nóng/lạnh, mạng, pool | Benchmark độc lập, không đặt ngưỡng mili-giây cứng trong mọi JUnit run |
| **Concurrency** | Xung đột unique ID, transaction retries và không tạo trùng | Integration test có quản lý thread, độc lập dữ liệu |

Không nên viết `assertTrue(elapsed < 10 ms)` làm điều kiện pass/fail của mapping test: CI chậm, Docker đang khởi động hoặc OS scheduler có thể gây flakiness. Mapping tests cần kiểm tra **giá trị**, còn benchmark định lượng nên được tổ chức riêng với điều kiện đo rõ ràng.

Một ví dụ để xem đúng chi phí mở rộng quan hệ:

~~~cypher
PROFILE
MATCH (b:QA007Book)
OPTIONAL MATCH (b)-[:QA007_WRITTEN_BY]->(a:QA007Author)
RETURN b.isbn AS isbn,
       collect(a.authorId) AS authorIds
ORDER BY isbn;
~~~

Kiểm tra `Rows`, `DB Hits` và có hay không index/scan trên dataset lớn. Trên fixture ba node, plan không có ý nghĩa đại diện cho workload production; điều có thể xác nhận là **ba record trả về** và danh sách author đúng.

## 17. Những bẫy khi nâng cấp thư viện

Các thành phần có thể thay đổi độc lập: phiên bản Neo4j server, Java Driver, Spring Data Neo4j, Spring Boot, Testcontainers và JDK. Khi nâng cấp:

1. Cố định phiên bản trong BOM và container image cho nhánh release.
2. Chạy test ánh xạ từ nguồn **Driver** và **SDN** trên cùng fixture.
3. Kiểm tra compatibility của `DATE`/`DATETIME`, numeric type, converter và getter.
4. Kiểm tra query tự sinh của repository, đặc biệt quan hệ vòng, relationship properties và custom `@Query`.
5. Kiểm tra transaction retry, bookmark, database selection và cấu hình TLS.
6. Giữ regression test cho case lỗi từng gặp: null, alias đổi, sai hướng, bản ghi gốc bị nhân lên, dữ liệu quan hệ bị ghi đè.
7. Nếu query count hoặc payload tăng sau nâng cấp, đo thêm N+1/over-fetch trước khi kết luận mapper sai.

Trong Spring Boot 4/SDN các thế hệ mới hơn, **package annotation test và dependency test slice có thể khác**. Đừng cố giữ import cũ khi đổi major version; đối chiếu hướng dẫn chính thức, sửa test setup nhưng **giữ nguyên expected contract**.

## 18. Bài tập có đáp án

### Bài 1 — Count sau OPTIONAL MATCH

Fixture có 3 Book, lần lượt có 2, 1, 0 tác giả. `OPTIONAL MATCH` từ Book sang Author trả bao nhiêu dòng và bao nhiêu Book duy nhất?

**Đáp án:** 4 dòng trung gian (2 + 1 + 1 dòng null), nhưng có **3 Book duy nhất**.

### Bài 2 — Null khi mapping

B002 không có property `subtitle`. Driver đọc `RETURN b.subtitle AS subtitle`; SDN có field `String subtitle`. Kỳ vọng?

**Đáp án:** Driver `Value.isNull() == true`, mapper trả Java `null`; SDN `getSubtitle() == null`. Không chuyển null thành chuỗi `"null"`.

### Bài 3 — Sai chiều relationship

Annotation `@Relationship(type="QA007_WRITTEN_BY", direction=INCOMING)` được đặt trên Book. Tại sao B001 không có A01/A02 như mong đợi?

**Đáp án:** Fixture dùng cạnh **OUTGOING** từ Book sang Author; hướng ngược không khớp. Test phải assert tập ID A01/A02 để bắt lỗi.

### Bài 4 — Chuyển kiểu ngày

Property `publishedOn = date('2025-01-06')` cần ánh xạ sang kiểu gì?

**Đáp án:** Driver `Value.asLocalDate()` và SDN `LocalDate`. Không phụ thuộc timezone server đối với kiểu `DATE`.

### Bài 5 — Mock repository có đủ không?

Test mock `BookRepository.findByIsbn` trả một Book dựng tay với hai tác giả. Có thể kết luận SDN map đúng quan hệ từ Neo4j không?

**Đáp án:** không. Mock bỏ qua Cypher, Bolt và converter. Cần integration test với Neo4j fixture và repository thật.

### Bài 6 — Tính độc lập transaction

Test Spring có `@Transactional`, nhưng `@BeforeEach` seed bằng Driver `executeWrite` và commit. Sau khi test rollback transaction Spring, dữ liệu Driver có chắc bị xóa không?

**Đáp án:** không. Đây là transaction độc lập; cần cleanup rõ ràng hoặc đưa seed vào cùng transaction có kiểm soát.

### Bài 7 — Hai đường cùng sai

Kết quả Driver và SDN đều trả `authorIds = []` cho B001, và test chỉ có `assertEquals(fromDriver, fromSdn)`. Test có đạt mục đích không?

**Đáp án:** chưa. Cả hai có thể sai chung một hướng quan hệ. So với expected độc lập `Set.of("A01","A02")`.

### Bài 8 — Thứ tự collection

`collect(a.authorId)` trả A02 trước A01, nhưng test mong A01 trước A02. Đây có chắc là lỗi ánh xạ?

**Đáp án:** không. Nếu không sắp xếp có kiểm soát, thứ tự của collection không được bảo đảm. Test so sánh theo set hoặc thêm `ORDER BY` thích hợp trước aggregation.

### Bài 9 — Save entity nạp thiếu

Custom query chỉ trả node Book, nhưng entity còn có relationship Authors. Service sửa title rồi `save(book)`. Rủi ro là gì?

**Đáp án:** trạng thái entity có thể không chứa đủ quan hệ; tùy phiên bản và mapping, việc lưu có thể cập nhật graph vượt quá phần title. Test riêng đọc/ghi và cân nhắc update bằng Cypher theo khóa khi chỉ cần đổi title.

## 19. Checklist kiểm thử ánh xạ dùng trong CI

- [ ] Neo4j chạy trong môi trường test tách biệt, container image và dependency được khóa version.
- [ ] Fixture có node đủ property, thiếu property, nhiều quan hệ, một quan hệ và **không có quan hệ**.
- [ ] Có expected literal độc lập, không chỉ so sánh hai mapper với nhau.
- [ ] Test kiểm tra alias, `String`, `Long`, `LocalDate`, null, ID và collection.
- [ ] Test kiểm tra hướng/type relationship và không giả định thứ tự Set/list nếu không có `ORDER BY`.
- [ ] Có integration test Driver thật và SDN repository thật, không chỉ mock.
- [ ] Driver tiêu thụ `Result` trước khi đóng Session/Transaction.
- [ ] Test chọn database tường minh và không dùng production credentials.
- [ ] Dọn fixture giữa test; không phụ thuộc order; không chạy parallel trên cùng label nếu chưa cô lập.
- [ ] Có test negative: thiếu node, sai ID, unique constraint, rollback và mapper bị đổi alias.
- [ ] Ghi/read được kiểm tra **sau commit**, không chỉ dựa vào object còn trong memory.
- [ ] Unit test, integration test và benchmark được phân tách, tránh ngưỡng latency cứng.
- [ ] Có regression test khi nâng cấp Neo4j/Driver/SDN/Spring Boot.

## 20. Dọn fixture và tài liệu tham khảo

Chỉ trong database test đã dùng:

~~~cypher
MATCH (n)
WHERE n:QA007Book OR n:QA007Author
DETACH DELETE n;
~~~

~~~cypher
DROP CONSTRAINT qa007_book_isbn IF EXISTS;
~~~

~~~cypher
DROP CONSTRAINT qa007_author_id IF EXISTS;
~~~

Kiểm tra:

~~~cypher
MATCH (n)
WHERE n:QA007Book OR n:QA007Author
RETURN count(n) AS remaining;
~~~

**Đáp án:** `remaining = 0`. Không chạy cleanup trong database thật hoặc với label mà hệ thống khác đang sử dụng.

**Tài liệu chính thức:**

- [Neo4j Java Driver Manual — Query database](https://neo4j.com/docs/java-manual/current/query-simple/): `Record`, `Value`, kết quả truy vấn và kiểu dữ liệu.
- [Neo4j Java Driver Manual — Transactions](https://neo4j.com/docs/java-manual/current/transactions/): transaction lifecycle, retry và phạm vi Session.
- [Neo4j Java Driver Manual — Data types](https://neo4j.com/docs/java-manual/current/data-types/): ánh xạ temporal, integer, collections, null.
- [Spring Data Neo4j Reference — Object mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/): `@Node`, `@Id`, property/relationship mapping, conversion.
- [Spring Data Neo4j Reference — Custom queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): hình dạng record cần cho graph mapping.
- [Spring Boot Reference — Data Neo4j tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): slice tests và môi trường Spring context.
- [Testcontainers for Java — Neo4j](https://java.testcontainers.org/modules/databases/neo4j/): tạo Neo4j container và kết nối cho integration test.
- [Neo4j Cypher Manual — Query plans](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/execution-plans/): `EXPLAIN`/`PROFILE` để xem Rows, DB Hits và memory.

**Ghi nhớ:** Một phép thử ánh xạ chất lượng phải chứng minh **graph thật → Cypher thật → kết quả Java đúng**, với đáp án độc lập cho giá trị, kiểu dữ liệu, hướng quan hệ và trường hợp thiếu dữ liệu. Java Driver yêu cầu mapper chủ động kiểm tra `Record/Value`; Spring Data Neo4j yêu cầu entity và query có cấu trúc phù hợp. Testcontainers giúp kiểm tra cả hai tuyến trên cùng một Neo4j có thể tái tạo, còn test transaction/cleanup giúp tránh kết luận sai do trạng thái dữ liệu sót lại.
