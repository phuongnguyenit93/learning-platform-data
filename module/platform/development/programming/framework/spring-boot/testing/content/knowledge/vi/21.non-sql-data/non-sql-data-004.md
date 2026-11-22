# @DataNeo4jTest cho quan hệ và truy vấn đồ thị

Trong nhóm **Dữ liệu ngoài SQL** của module **Spring Boot - testing**, `@DataNeo4jTest` là một **test slice** tập trung vào Spring Data Neo4j: kiểm tra repository, ánh xạ `@Node`, `@Relationship` và câu truy vấn **Cypher** trên cơ sở dữ liệu đồ thị Neo4j thật. Test không cần mở HTTP server, không cần tải tất cả service/controller của ứng dụng nhưng **phải có một Neo4j instance để kết nối**.

Điểm khác biệt lớn nhất so với `@DataJdbcTest` hay `@DataJpaTest` là dữ liệu đồ thị gồm **node, relationship có hướng, label, property và pattern/path**. Một test chỉ kiểm tra `repository.save(person)` trả object không null là quá yếu: nó chưa chứng minh quan hệ đúng chiều, số cạnh chính xác, query match đúng pattern, parameter được bind an toàn, hay lỗi transaction/schema có thể xảy ra.

**Sau bài học, bạn cần làm được:**

- Chọn đúng `@DataNeo4jTest` thay vì `@DataJpaTest`, `@JdbcTest` hay `@SpringBootTest`.
- Dựng môi trường Spring Boot 3.5 + Neo4j 5 qua Testcontainers và `@ServiceConnection`.
- Tạo `Author`/`Book` với cạnh có hướng `(:Author)-[:WROTE]->(:Book)`.
- Kiểm tra repository CRUD, nạp relationship, query derived, Cypher `@Query` và query trực tiếp bằng `Neo4jClient`.
- Kiểm tra **đúng hướng** và **đúng số cạnh**, không suy diễn từ một object Java trong bộ nhớ.
- Hiểu transaction rollback của test imperative; tránh để lại dữ liệu khi test reactive, khi tắt rollback hoặc dùng container dùng chung.
- Nhận biết những thứ slice **không chứng minh**: full service wiring, HTTP, security, production database configuration, lock/concurrency và query performance.
- Thêm trường hợp nâng cao: relationship properties, unique constraints, path queries, optional matches và test idempotency.

Ví dụ gồm **Java 17+**, Spring Boot **3.5.x**, Spring Data Neo4j 7.5 và JUnit Jupiter. Những API/imports thuộc Spring Boot 4.x có thể được chuyển sang module/package khác; không copy nguyên đường import của Boot 3.5 sang Boot 4 mà không kiểm tra version.

## 1. @DataNeo4jTest thực sự tạo môi trường gì?

Một test tối thiểu:

```java
@DataNeo4jTest
class AuthorRepositoryTest {
    @Autowired AuthorRepository repository;
    @Autowired Neo4jClient neo4jClient;
}
```

Đây chỉ là **skeleton**, chưa phải class chạy độc lập: bạn phải khai báo repository, có Neo4j đang hoạt động và cung cấp cấu hình driver. `@DataNeo4jTest` định hướng Spring Boot:

1. Khởi tạo **ApplicationContext hẹp** với các auto-configurations phục vụ Spring Data Neo4j.
2. Scan domain objects có `@Node`, khởi tạo Neo4j repositories và những thành phần tương ứng như `Neo4jClient`, `Neo4jTemplate` và transaction infrastructure tùy dependencies.
3. Không mặc định load mọi `@Service`, `@Component`, controller hay `@ConfigurationProperties` tùy ý. Nếu một bean thật sự cần cho repository mapping, phải đưa vào slice có chủ đích.
4. Với imperative tests, mặc định **test-managed transaction + rollback sau mỗi test method**.
5. **Không tự mang sẵn database nhúng** hoặc URI kết nối; bạn phải cung cấp Neo4j thông qua Testcontainers, Neo4j test harness hoặc một instance test an toàn.

**Chú ý phiên bản:** Trong Boot 3.5, annotation được import từ:

```java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
```

Không nhầm với import của một số bản Spring Boot 4.x, nơi tính năng đã được tổ chức lại theo module `spring-boot-data-neo4j-test` và package khác.

### Không giả định test tạo một Neo4j in-memory mới

Với H2/SQLite test, bạn có thể quen chuyện một annotation đưa sẵn database vào RAM. Với Neo4j hiện đại, `@DataNeo4jTest` chỉ thiết lập **Spring side** của kết nối và repositories. **Không có container hoặc server/harness**, repository sẽ gặp lỗi kết nối khi thực thi.

Hai lựa chọn thực tế:

| Lựa chọn | Ưu điểm | Giới hạn |
| --- | --- | --- |
| **Testcontainers Neo4j** | Engine Neo4j qua Bolt, gần sản phẩm thật; phù hợp CI có Docker | Cần Docker runtime, tải image, startup tốn thời gian hơn |
| **Neo4j test harness** | Dựng server trong JVM, hữu ích khi test procedures/extensions | Version/JVM compatibility, thời gian và vận hành không giống remote deployment |
| Neo4j test server chuyên dụng | Có thể tái dùng, giống một môi trường kiểm thử | Phải bảo đảm isolation, auth, schema/cleanup, không trỏ nhầm production |

Bài runnable dùng **Testcontainers** để tránh giả định Neo4j tự có sẵn.

## 2. Các khái niệm node, relationship, direction và Cypher

Neo4j lưu **property graph**. Một đồ thị nhỏ:

```text
(:Author {name:"An"})
   |
   +--[:WROTE]--> (:Book {title:"Graph Basics", year:2025})
   |
   +--[:WROTE]--> (:Book {title:"Cypher Patterns", year:2024})

(:Author {name:"Mai"})
   |
   +--[:WROTE]--> (:Book {title:"Data Modeling", year:2023})
```

Ý nghĩa cấu trúc:

- `Author` và `Book` là **node labels**.
- `name`, `title` và `year` là **properties của node**.
- `WROTE` là **relationship type** có hướng **Author → Book**.
- Một node có thể có nhiều label; một pair node có thể có nhiều relationships, tùy model/ràng buộc.
- Đồ thị không tự suy diễn quy tắc “mỗi Author chỉ có hai Book” hoặc uniqueness của `name`. Bạn phải định nghĩa và kiểm tra constraint/contract.

Cypher tìm tác giả và sách:

```cypher
MATCH (a:Author {name: $name})-[:WROTE]->(b:Book)
RETURN b.title AS title
ORDER BY title
```

Trong Java, `$name` là **query parameter** do driver/Spring Data bind. Không nối trực tiếp input vào Cypher kiểu `"... WHERE a.name = '" + input + "'"`; điều đó vừa khó escape vừa tạo nguy cơ query injection.

### Hướng relationship không phải chi tiết trang trí

Hai pattern này **khác nhau**:

```cypher
MATCH (a:Author)-[:WROTE]->(b:Book)
RETURN count(b) AS total
```

```cypher
MATCH (b:Book)-[:WROTE]->(a:Author)
RETURN count(a) AS total
```

Trong dữ liệu ví dụ, pattern đầu tìm các cạnh WROTE thật; pattern thứ hai không match nếu không có cạnh WROTE đi từ Book sang Author. Nếu cần traversal không xét hướng, Cypher hỗ trợ relationship **undirected pattern** như `-[:WROTE]-`, nhưng đừng dùng khi hợp đồng bắt buộc direction.

### Graph query khác JOIN SQL

Trong SQL, bạn thường viết `JOIN ... ON foreign_key`. Với Neo4j, relationship là cấu trúc dữ liệu được lưu. Query pattern và traversal phụ thuộc:

- Relationship direction và type.
- Bội số cạnh (có thể có 0, 1, nhiều cạnh).
- Đường đi (path) và độ dài traversal.
- Optional match/null semantics.
- Số bản ghi trả về từ một query; join hoặc traversal có thể nhân bản kết quả.
- Constraint/index trên node properties và cardinality thực.

Vì thế, test graph cần quan sát **cạnh** và **số lượng cạnh** bằng Cypher bên cạnh việc đọc domain object từ repository.

## 3. So sánh các test slice trong Spring Boot

| Annotation / cách test | Tầng cần kiểm tra | Có DB thật? | Dùng cho |
| --- | --- | --- | --- |
| JUnit thuần + mock repository | Java/service logic với contract giả | Không | Validation, policy, mapping thuần |
| `@DataNeo4jTest` | Neo4j repository, mapping, Cypher | **Có** Neo4j test instance | Quan hệ và truy vấn đồ thị |
| `@DataMongoTest` | MongoDB documents và repositories | MongoDB theo test setup | Document queries |
| `@DataJdbcTest` | Spring Data JDBC + SQL | SQL datasource | Relational JDBC |
| `@DataJpaTest` | JPA/Hibernate | SQL datasource | JPA entities/JPQL |
| `@DataR2dbcTest` | R2DBC | R2DBC datasource | Reactive SQL access |
| `@SpringBootTest` | Context rộng của ứng dụng | Phụ thuộc cấu hình | Service/transaction/proxy/integration đa tầng |
| `@WebMvcTest` hoặc `@WebFluxTest` | Web controller, JSON, HTTP contract | Thường mock service | Status, routing, validation, security boundary phù hợp |

**Không dùng `@DataJpaTest` cho `@Node` Neo4j**: JPA không hiểu `@Relationship` của Spring Data Neo4j. Ngược lại, `@DataNeo4jTest` không tự chứng minh JPA entity, SQL datasource, REST API hay một Kafka consumer.

Đây là test slice **có ApplicationContext**, không phải unit test Java thuần; nhưng vẫn hẹp hơn full application. Một test repository Neo4j có thể chạy bằng `@DataNeo4jTest` mà không có service bean production. Đây là lợi thế về tốc độ/chẩn đoán, không phải lỗ hổng.

## 4. Ví dụ runnable: mô hình Author → Book

Ta dùng model hai loại node:

- **Author:** có ID Neo4j, tên và danh sách sách mà tác giả viết.
- **Book:** có ID, tiêu đề và năm phát hành.
- **WROTE:** cạnh có hướng từ Author tới Book, không mang properties ở ví dụ đơn giản.
- Repository cung cấp `save`, `findById`, `findByName` và query Cypher để lấy tiêu đề sách.

**Bộ file:**

```text
src/
├── main/java/example/testing/neo4j/
│   ├── GraphApplication.java
│   ├── Author.java
│   ├── Book.java
│   ├── AuthorRepository.java
│   ├── GraphRule.java
│   └── GraphRuleDemo.java
└── test/java/example/testing/neo4j/
    ├── AuthorRepositoryTest.java
    └── GraphRuleTest.java
```

Chọn một package gốc thống nhất để `@SpringBootApplication` có thể tìm repositories và nodes. Dưới đây là tất cả source files cần thiết.

### 4.1. Gradle dependencies cho Spring Boot 3.5

Trong một project Gradle đã tạo bằng Spring Initializr (đã có plugins, repositories, dependency management và Java 17+), phần phụ thuộc liên quan trong `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-neo4j'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:neo4j'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **đoạn bổ sung**, không phải một `build.gradle` độc lập. Boot 3.5 BOM quản lý phiên bản Spring Data Neo4j/Testcontainers tương thích; project dùng BOM của Boot 4 cần kiểm tra các package Testcontainers 2.x và module test đã thay đổi.

**Yêu cầu vận hành:** Docker/container runtime sẵn sàng, quyền pull image `neo4j:5.26` và mạng/CPU/RAM đủ để container khởi động. Không dùng Neo4j database production hoặc credentials thật để chạy destructive tests.

### 4.2. GraphApplication.java

Tạo `src/main/java/example/testing/neo4j/GraphApplication.java`:

```java
package example.testing.neo4j;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphApplication.class, args);
    }
}
```

Class này giúp Spring Boot tìm cấu hình ứng dụng trong cùng package. Các slice tests ở mục 5 **không cần chạy `main()`** hoặc mở HTTP server. Nếu chạy application thật bằng `main`, phải cung cấp `spring.neo4j.uri` và authentication đến một Neo4j instance của môi trường đó. Ví dụ không cố gắng tạo server Neo4j trong method `main()`.

### 4.3. Book.java — node đích

Tạo `src/main/java/example/testing/neo4j/Book.java`:

```java
package example.testing.neo4j;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("Book")
public class Book {

    @Id
    @GeneratedValue
    private Long id;

    private String title;
    private int year;

    public Book() {
    }

    public Book(String title, int year) {
        this.title = title;
        this.year = year;
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

    public int getYear() {
        return year;
    }

    public void setYear(int year) {
        this.year = year;
    }
}
```

**Giải thích:** `@Node("Book")` map Java object sang label `Book`. Cặp `@Id @GeneratedValue Long` dùng **Neo4j-generated internal identifier** trong SDN 7.5; `null` khi object chưa được lưu. Ví dụ này chọn internal ID để giữ code ngắn và tập trung vào relationship.

**Cảnh báo thiết kế production:** Neo4j internal ID không phải business key ổn định để expose cho client; nó có thể được tái sử dụng sau khi dữ liệu bị xóa và không có ý nghĩa giữa databases. Với model production, cân nhắc UUID/string business ID qua `@GeneratedValue(UUIDStringGenerator.class)` hoặc assigned stable ID + constraints phù hợp.

Class có constructor không tham số, một constructor tạo dữ liệu và getters/setters cần thiết; Spring Data Neo4j có thể ánh xạ và gán ID. Không dùng `jakarta.persistence.Entity` hay `@GeneratedValue` của JPA trong file này.

### 4.4. Author.java — node gốc và cạnh có hướng

Tạo `src/main/java/example/testing/neo4j/Author.java`:

```java
package example.testing.neo4j;

import java.util.ArrayList;
import java.util.List;

import org.springframework.data.neo4j.core.schema.GeneratedValue;
import org.springframework.data.neo4j.core.schema.Id;
import org.springframework.data.neo4j.core.schema.Node;
import org.springframework.data.neo4j.core.schema.Relationship;

@Node("Author")
public class Author {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @Relationship(
            type = "WROTE",
            direction = Relationship.Direction.OUTGOING)
    private List<Book> books = new ArrayList<>();

    public Author() {
    }

    public Author(String name) {
        this.name = name;
    }

    public void addBook(Book book) {
        books.add(book);
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public List<Book> getBooks() {
        return books;
    }

    public void setBooks(List<Book> books) {
        this.books = new ArrayList<>(books);
    }
}
```

**Ý nghĩa mapping:**

- `@Relationship(type="WROTE", direction=OUTGOING)` tạo cạnh **Author → Book** cho các elements trong `books`.
- Các `Book` tham chiếu từ aggregate root có thể được lưu cùng lúc với `Author` theo semantics của Spring Data Neo4j; khi đọc `Author`, repository mapping khôi phục các relationships được truy vấn theo cơ chế entity loading.
- `List<Book>` ở đây không tự hứa một **thứ tự lưu cạnh** như danh sách Java. Trong test, hãy sort titles khi business **không yêu cầu thứ tự**, không giả định lần load lại luôn trả đúng thứ tự `addBook`.
- Tránh tạo hai phía mapping có thể gây vòng đệ quy hoặc duplicate graph edges ngoài ý muốn nếu chưa hiểu chính xác ownership/direction.
- Không nhầm `@Relationship` này với annotation JPA `@OneToMany`; Neo4j lưu **edge**, không phải một foreign key trong bảng.

Nếu phải lưu **properties ngay trên cạnh** (ví dụ `role`, `since`, `weight`), xem `@RelationshipProperties`/`@TargetNode` ở mục nâng cao. Không thêm trường của relationship vào `Book` rồi ngầm coi chúng thuộc từng cạnh, vì cùng một Book có thể liên kết với nhiều Author với vai trò khác nhau.

### 4.5. AuthorRepository.java — derived và custom query

Tạo `src/main/java/example/testing/neo4j/AuthorRepository.java`:

```java
package example.testing.neo4j;

import java.util.List;
import java.util.Optional;

import org.springframework.data.neo4j.repository.Neo4jRepository;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface AuthorRepository
        extends Neo4jRepository<Author, Long> {

    Optional<Author> findByName(String name);

    @Query("""
            MATCH (a:Author {name: $name})-[:WROTE]->(b:Book)
            RETURN b.title AS title
            ORDER BY title
            """)
    List<String> findBookTitles(
            @Param("name") String name);
}
```

**Hai loại query:**

- `findByName` là repository derived query dựa trên property `name` của node `Author`.
- `findBookTitles` dùng `@Query` viết Cypher rõ ràng: lọc Author theo `$name`, đi theo cạnh `WROTE` đúng hướng, trả titles đã sort. Đây là **scalar projection** `List<String>` chứ không yêu cầu SDN dựng full `Author` aggregate từ một custom Cypher query.
- `@Param("name")` bind an toàn Java argument vào `$name`; không nối chuỗi từ input.
- `ORDER BY title` giúp assertion deterministic.

Các method chuẩn `Neo4jRepository` như `save`, `findById`, `findAll`, `deleteById`, `count` và `existsById` do Spring Data cung cấp. Test dùng **repository bean thật**, không mock nó, để chứng minh Cypher và mapping thực sự hoạt động.

**Vì sao không viết `@Query("MATCH (a)-[r]->(b) RETURN a,r,b")` rồi giả định luôn map đúng?** Spring Data Neo4j có quy tắc dựng aggregate từ các records, nodes và relationships. Với query trả nhiều records cho cùng root hoặc thiếu phần relationship cần thiết, entity mapping có thể không được hydration đúng. Khi query chỉ cần scalar, trả scalar; khi cần hydrate graph phức tạp, thiết kế Cypher trả đủ root/nodes/relationships theo tài liệu SDN.

## 5. Testcontainers Neo4j + @DataNeo4jTest hoàn chỉnh

Tạo `src/test/java/example/testing/neo4j/AuthorRepositoryTest.java`:

```java
package example.testing.neo4j;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@DataNeo4jTest
class AuthorRepositoryTest {

    @Container
    @ServiceConnection
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26");

    @Autowired
    private AuthorRepository authors;

    @Autowired
    private Neo4jClient neo4jClient;

    private static Author authorWithTwoBooks() {
        Author author = new Author("An");
        author.addBook(new Book("Graph Basics", 2025));
        author.addBook(new Book("Cypher Patterns", 2024));
        return author;
    }

    private long countWroteEdges(String authorName) {
        return neo4jClient.query("""
                MATCH (a:Author {name: $name})
                      -[r:WROTE]->(b:Book)
                RETURN count(r) AS total
                """)
                .bind(authorName).to("name")
                .fetchAs(Long.class)
                .mappedBy((typeSystem, record) ->
                        record.get("total").asLong())
                .one()
                .orElseThrow();
    }

    @Test
    void savesRootAndRelatedNodes() {
        Author saved = authors.save(authorWithTwoBooks());

        assertNotNull(saved.getId());

        Author loaded = authors.findById(
                saved.getId()).orElseThrow();

        assertEquals("An", loaded.getName());
        assertEquals(2, loaded.getBooks().size());
        assertTrue(loaded.getBooks().stream()
                .allMatch(book -> book.getId() != null));
        assertEquals(2L, countWroteEdges("An"));
    }

    @Test
    void derivedQueryLoadsMappedRelationships() {
        authors.save(authorWithTwoBooks());

        Author loaded = authors.findByName("An").orElseThrow();

        List<String> titles = loaded.getBooks().stream()
                .map(Book::getTitle)
                .sorted()
                .toList();

        assertEquals(
                List.of("Cypher Patterns", "Graph Basics"),
                titles);
        assertTrue(authors.findByName("Missing").isEmpty());
    }

    @Test
    void customCypherUsesDirectionAndStableOrdering() {
        authors.save(authorWithTwoBooks());

        assertEquals(
                List.of("Cypher Patterns", "Graph Basics"),
                authors.findBookTitles("An"));
        assertEquals(List.of(), authors.findBookTitles("Mai"));
    }

    @Test
    void cypherParameterIsNotStringConcatenation() {
        authors.save(authorWithTwoBooks());

        List<String> result =
                authors.findBookTitles("An' OR true");

        assertTrue(result.isEmpty());
        assertEquals(2L, countWroteEdges("An"));
    }

    @Test
    void missingRootAndEmptyRelationshipsAreDistinct() {
        authors.save(new Author("Mai"));

        assertTrue(authors.findByName("Missing").isEmpty());
        assertTrue(
                authors.findByName("Mai")
                        .orElseThrow()
                        .getBooks()
                        .isEmpty());
        assertEquals(0L, countWroteEdges("Mai"));
    }

    @Test
    void updatesNodePropertyOnSave() {
        Author saved = authors.save(new Author("An"));

        saved.setName("An Updated");
        Author updated = authors.save(saved);

        assertEquals(
                "An Updated",
                authors.findById(updated.getId())
                        .orElseThrow()
                        .getName());
        assertTrue(authors.findByName("An").isEmpty());
    }

    @Test
    void deletingRootRemovesItsOutgoingEdges() {
        Author saved = authors.save(authorWithTwoBooks());

        assertEquals(2L, countWroteEdges("An"));
        authors.deleteById(saved.getId());

        assertFalse(authors.existsById(saved.getId()));
        assertEquals(0L, countWroteEdges("An"));
    }

    @Test
    void testsDoNotAssumeGeneratedIdValues() {
        Author saved = authors.save(new Author("Mai"));

        assertNotNull(saved.getId());
        assertTrue(authors.existsById(saved.getId()));
    }
}
```

**Class có đúng 8 method `@Test`**. Đây là một Spring Data Neo4j slice test với Neo4j container thật. Nó kiểm tra **node + cạnh + scalar Cypher query**, không chỉ một fake Java object.

### Tại sao @ServiceConnection hoạt động?

- `@Testcontainers` và `@Container` quản lý vòng đời Neo4j container qua JUnit Testcontainers extension.
- `@ServiceConnection` của Spring Boot tạo **`Neo4jConnectionDetails`** từ container và để Neo4j auto-configuration sử dụng. Điều này giúp tránh hardcode URI, credentials và cổng ngẫu nhiên.
- `@DataNeo4jTest` vẫn là **slice**, không tự biến thành `@SpringBootTest`; chỉ các beans liên quan được nạp.
- Testcontainers Neo4j dùng Bolt driver đến Neo4j chạy trong container; không phải in-memory graph giả.
- Các test imperative trong class được Spring quản lý transaction và rollback theo mặc định. Mỗi test tự tạo fixture, không phụ thuộc thứ tự chạy.

**Lưu ý:** Testcontainers 1.x (được Boot 3.5 BOM quản lý) dùng `org.testcontainers.containers.Neo4jContainer`. Trong hệ Testcontainers 2.x, package/module cho Neo4j có thể khác; mã trên cố ý nhắm đến **Boot 3.5**, tránh ghép code các thế hệ dependency khác nhau.

### Phân tích tám case

**Case 1 — save root + related nodes:** `authors.save(...)` ghi một Author và hai Book, cùng hai cạnh `WROTE`. Test load lại qua `findById` và kiểm tra size 2, IDs không null. Quan trọng hơn, `Neo4jClient` đếm **cạnh thật** bằng Cypher, không chỉ đếm một List có sẵn trong object.

**Case 2 — derived query:** `findByName("An")` tìm root và hydration relationships; ta **sort titles** trước assertion vì order của relationship collection không mặc nhiên là business contract. `findByName("Missing")` trả `Optional.empty()`, không giống một Author có danh sách Book rỗng.

**Case 3 — custom Cypher:** test `findBookTitles` trên graph thật, lọc theo `$name` và duyệt đúng `-[:WROTE]->`; `ORDER BY title` làm output có thứ tự rõ. Không dùng query giả chỉ trả một chuỗi cố định.

**Case 4 — parameters:** input `"An' OR true"` được truyền như **string parameter**, không bị ghép vào câu Cypher. Kết quả không match, trong khi graph Author “An” vẫn có hai cạnh. Test này là regression guard của cách bind, **không thay thế security review của mọi query builder**.

**Case 5 — missing vs empty relationship:** không tìm thấy Author là `Optional.empty()`; tìm thấy “Mai” không viết sách là một Author hợp lệ với `books=[]`. Test đảm bảo hai trường hợp không bị trộn.

**Case 6 — update node:** sau khi save, đổi tên và save lại. Test đọc lại property qua repository và kiểm tra tên cũ không match. Không dựa vào việc sửa `saved.getName()` trong Java memory rồi cho đó là SQL/Cypher đã chạy.

**Case 7 — delete root:** test xác minh root không còn và không có cạnh `WROTE` xuất phát từ Author cũ. **Không tự kết luận tất cả Book nodes đã bị xóa** vì việc xóa các node liên quan cần xem rõ ownership và aggregate persistence semantics; đặc biệt trong graph nhiều root có thể cùng tham chiếu một node.

**Case 8 — generated ID:** chỉ kiểm tra ID không null và repository có thể tìm theo ID. **Không assert ID phải là 0, 1 hoặc một số liên tiếp**, vì internal IDs không phải khóa nghiệp vụ hay API contract.

### Vì sao dùng Neo4jClient bên cạnh repository?

`Neo4jClient` cho phép viết query Cypher trực tiếp **trong Spring-managed context/transaction**. Phép kiểm tra `countWroteEdges`:

```cypher
MATCH (a:Author {name: $name})-[r:WROTE]->(b:Book)
RETURN count(r) AS total
```

kiểm tra số **relationships** ở storage thay vì tin hoàn toàn vào mapper. `fetchAs(Long.class).mappedBy(...)` lấy trường `total` từ Neo4j result record, trả `Optional<Long>`; test gọi `orElseThrow()` khi query không trả dòng nào. Với `count(...)`, Cypher trả một dòng có giá trị 0 ngay cả khi không match.

**Không chuyển sang Neo4j Java Driver mở session độc lập để kiểm tra uncommitted writes của test transaction** nếu chưa hiểu transaction boundaries. Một driver session khác có thể không thấy changes chưa commit của Spring-managed test transaction. `Neo4jClient` được inject từ context có thể tham gia transaction phù hợp và cho một nguồn kiểm chứng dữ liệu thực tế.

## 6. Chạy và đọc kết quả

Trên macOS/Linux:

```bash
./gradlew test --tests example.testing.neo4j.AuthorRepositoryTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.neo4j.AuthorRepositoryTest"
```

**Kỳ vọng khi môi trường đúng:** 8 JUnit methods pass. Neo4j container được tạo và chạy trong lifecycle của test class; Spring Boot cấu hình `Neo4jConnectionDetails` để repositories và client kết nối.

Kết quả hiển thị trên console tùy Gradle/JUnit version, nên không hứa một stdout cố định. Nếu Docker không khả dụng, test có thể thất bại **trước khi assertion chạy**; đó là lỗi environment/CI, không được báo nhầm thành repository mapping fail.

**Các lỗi cần kiểm tra trước khi sửa code test:**

- `Could not connect to localhost:7687`: test đang dùng URI mặc định thay vì connection details; kiểm tra `@ServiceConnection`, container được start và dependencies.
- `No qualifying bean of type AuthorRepository`: kiểm tra starter Spring Data Neo4j, package của `GraphApplication`/repository và `@DataNeo4jTest`.
- Mismatch package imports: không trộn Boot 3.5 với Boot 4 hoặc Testcontainers 1.x với 2.x.
- Nếu query không thấy relationships: kiểm tra direction/type, setup `addBook(...)`, entity mapping và transaction visibility.
- `ClientException` của Cypher: đọc lỗi syntax, label/property names và parameter binding; không tự thêm `MATCH (n) DETACH DELETE n` vào startup của mọi test để che vấn đề.
- Docker image không thể pull: kiểm tra registry/network, Docker memory/cgroup và image tag tương thích.

## 7. Transaction rollback và cô lập dữ liệu test

### 7.1. Mặc định với imperative @DataNeo4jTest

Trong Spring Boot 3.5, imperative `@DataNeo4jTest` dùng test-managed transaction và rollback ở cuối test method. Kịch bản thường là:

```text
TestContext mở test transaction
          |
          v
@Test: authors.save(author)
          |
          v
@Test: authors.findById(...) + Neo4jClient query(...)
          |
          v
Assert đủ giá trị và relationships
          |
          v
TestContext rollback transaction
```

Điều này làm từng test method của ví dụ tự tạo fixture độc lập. Khi một test vừa `save` vừa `findById` trong cùng transaction, dữ liệu có thể được nhìn thấy ngay, nhưng **không chứng minh đã commit** vào graph sau khi method kết thúc.

**Không viết test A tạo node, test B dựa vào node đó.** JUnit không có thứ tự chạy cố định theo source code. Không vì một test class có container static mà mặc định data phải được share giữa methods.

### 7.2. Tắt rollback khi thật sự cần kiểm tra commit

Nếu mục tiêu là kiểm tra hành vi ngoài test transaction, có thể tắt transaction wrapper:

```java
@DataNeo4jTest
@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ExplicitCommitBehaviorTest {
    // Các test ở đây phải tự tạo fixture và cleanup.
}
```

Đây là **class skeleton**, thiếu các imports/fields/test methods; không phải file chạy độc lập. Lúc đó repository methods/transaction boundaries thật có thể commit và **dữ liệu không được rollback tự động** cuối test method.

Chỉ dùng setup này với một Neo4j instance **dành riêng cho test**, dữ liệu namespace/IDs duy nhất và cleanup đáng tin. Nếu dùng container được JUnit quản lý và chỉ có một test class sở hữu, shutdown có thể xóa toàn bộ ephemeral data; nhưng không nên dùng shutdown container thay cho isolation khi container dùng chung giữa nhiều classes.

### 7.3. Reactive Spring Data Neo4j là trường hợp đặc biệt

Spring Data Neo4j có cả imperative và reactive infrastructure tùy dependencies. Tuy nhiên **test-managed `@Transactional` theo imperative không thể trực tiếp quản lý Reactive Streams transactions** của repository methods trả `Mono`/`Flux`.

Nếu test repository reactive:

- Cấu hình test bằng `@Transactional(propagation = NOT_SUPPORTED)` để tránh gắn imperative test transaction vào reactive access.
- Dùng `StepVerifier` để kiểm tra publisher đã **subscribe/complete/error**, không chỉ so `Mono` objects.
- Muốn atomic rollback trong chuỗi reactive, dùng `TransactionalOperator` phù hợp hoặc service reactive có transaction semantics được thiết kế/kiểm chứng rõ.
- Dùng Neo4j instance/test database riêng và cleanup; đừng nghĩ test reactive được rollback tự động chỉ vì class có `@DataNeo4jTest`.
- Không trộn imperative và reactive repositories trong một test rồi kỳ vọng chúng tự chia sẻ cùng transaction qua thread/context.

**Bộ ví dụ runnable trong bài dùng hoàn toàn imperative repositories.** Đoạn reactive này là hướng dẫn chọn phạm vi, không phải lời khẳng định đã cung cấp một reactive test hoàn chỉnh.

## 8. Test quan hệ có properties: @RelationshipProperties

Ở graph thực, relationship thường mang dữ liệu. Ví dụ một người tham gia dự án với vai trò và thời điểm:

```text
(:Person {name:"An"})
   -[:MEMBER_OF {role:"LEAD", since:2023}]->
(:Project {key:"P-7"})
```

Trong Spring Data Neo4j, dùng `@RelationshipProperties` với một `@TargetNode`. Dưới đây là mẫu khai báo **concept**, chưa phải bộ file runnable độc lập vì cần constructors/getters, graph classes và repository:

```java
@Node("Person")
class Person {
    @Id @GeneratedValue
    private Long id;

    @Relationship(type = "MEMBER_OF",
                  direction = Relationship.Direction.OUTGOING)
    private List<Membership> memberships = new ArrayList<>();
}

@RelationshipProperties
class Membership {
    @RelationshipId
    private Long relationshipId;

    private String role;
    private int since;

    @TargetNode
    private Project project;
}

@Node("Project")
class Project {
    @Id @GeneratedValue
    private Long id;

    private String key;
}
```

**Điều cần test cho relationship properties:**

1. Có một cạnh `MEMBER_OF` đúng chiều.
2. `role`/`since` thực sự được lưu trên **relationship**, không phải trên Person hay Project.
3. Load lại qua repository khôi phục `Membership.role`/`since` và `@TargetNode Project` đúng.
4. Update thuộc tính cạnh không vô tình tạo cạnh trùng hoặc xóa cạnh của chủ thể khác.
5. Nếu nhiều edges cùng source-target được cho phép, phải assert **bội số** và identity/semantics thật, không chỉ `count >= 1`.
6. Nếu cần uniqueness trên cặp Person–Project hoặc trên role, xác định constraint/business policy riêng; Neo4j không mặc định cấm nhiều relationships cùng type giữa một cặp nodes.

**Tại sao có `@RelationshipId`?** Spring Data Neo4j cần nhận diện một relationship instance cụ thể để quản lý lifecycle/update mapping an toàn. Không bỏ annotation này khi xây relationship properties theo SDN 7.5 rồi chỉ dựa vào object reference.

Với quan hệ hai chiều hoặc self-reference, xác định rõ owner/direction và tránh vòng mapping vô hạn khi serialize HTTP JSON. Entity graph giàu quan hệ không nên được trả thẳng dưới dạng REST response DTO.

## 9. Các trường hợp graph query phải kiểm tra riêng

### 9.1. Cạnh có hướng và pattern đảo chiều

Giả sử `Author(An)-[:WROTE]->Book(Graph Basics)`. Test:

```cypher
MATCH (:Author {name: $name})-[:WROTE]->(:Book)
RETURN count(*) AS outgoing
```

và đối chứng:

```cypher
MATCH (:Book)-[:WROTE]->(:Author {name: $name})
RETURN count(*) AS reverse
```

Trong graph do ví dụ tạo, `outgoing=2` còn `reverse=0`. Nếu developer vô tình đổi `@Relationship(Direction.INCOMING)`, test chỉ nhìn “có hai book trong Java List” có thể bỏ sót; test Cypher theo direction sẽ đỏ.

### 9.2. Path traversal nhiều hop

Ví dụ mạng người:

```cypher
MATCH p = (start:Person {name: $startName})
          -[:KNOWS*1..3]->
          (end:Person {name: $endName})
RETURN length(p) AS hops
```

Đoạn này là **mẫu query**, không chạy trong bộ Author/Book ở mục 5 vì nó dùng label `Person` và relationship `KNOWS` chưa được seed. Khi viết test path:

- Tạo một graph nhỏ có số hop đã biết (chẳng hạn A→B→C).
- Kiểm tra chiều và giới hạn `*1..3`, tránh query không giới hạn dẫn tới traversal lớn.
- Một graph có nhiều đường đi hợp lệ có thể trả **nhiều records**; không giả định một kết quả duy nhất.
- Nếu mục tiêu là shortest path, dùng cú pháp/query phù hợp phiên bản Cypher và test khi có nhiều đường đi bằng độ dài bằng nhau.
- Không khẳng định kết quả path đã được map thành một aggregate đầy đủ nếu query trả thiếu nodes/relationships.

### 9.3. OPTIONAL MATCH và null

`OPTIONAL MATCH` có semantics giống outer match ở chỗ một Author không có WROTE vẫn có thể xuất hiện với Book là null:

```cypher
MATCH (a:Author {name: $name})
OPTIONAL MATCH (a)-[:WROTE]->(b:Book)
RETURN a.name AS authorName, b.title AS bookTitle
```

Với “Mai” không có sách, query có thể trả một row trong đó `bookTitle=null`. Điều này **khác** với `MATCH (a)-[:WROTE]->(b)`, nơi không có cạnh thì không có row. Test phải phân biệt **missing root**, **root có collection rỗng** và **optional null projection**.

### 9.4. Duplicates và nhiều đường đi

Neo4j không tự loại duplicate records trừ khi query/aggregation yêu cầu. `MATCH` qua nhiều edges/path có thể phát nhiều records cho cùng node. Khi business contract yêu cầu tác giả duy nhất, dùng `DISTINCT` có chủ đích và assert đúng count. **Không thêm DISTINCT tùy tiện** nếu số lần xuất hiện của relationship (bội số) là dữ liệu cần bảo vệ.

### 9.5. Sắp xếp và phân trang

Không có `ORDER BY`, database không bảo đảm thứ tự records. Nếu API cần thứ tự:

```cypher
MATCH (a:Author)-[:WROTE]->(b:Book)
RETURN b.title AS title
ORDER BY title ASC, elementId(b) ASC
SKIP $skip LIMIT $limit
```

Đây là snippet query cần params `$skip`, `$limit`; dùng `elementId(b)` chỉ để **tie-break trong một database/query**, không xem nó là business identifier ổn định. Với pagination production, ưu tiên khóa ổn định/unique được định nghĩa ở domain để tránh kết quả thay đổi giữa requests.

Nếu repository method dùng `Pageable` cùng custom `@Query`, phải kiểm tra rõ query template có áp dụng `SKIP/LIMIT`, sort và count query phù hợp. Không giả định các semantics SQL/JPA paging được tự động ghép vào mọi Cypher query thủ công.

## 10. Unique constraints, indexes và schema migrations

Khác với relational test có `schema.sql` chứa bảng, Neo4j không cần tạo “bảng” cho `Author` hay `Book` trước khi ghi nodes. Nhưng một hệ thống production thường vẫn cần **constraints/indexes**.

Ví dụ Cypher:

```cypher
CREATE CONSTRAINT author_name_unique IF NOT EXISTS
FOR (a:Author) REQUIRE a.name IS UNIQUE
```

Constraint này (Neo4j 5) cấm hai nodes `Author` trùng `name` trên database đang được tạo. **Nó không tự được sinh chỉ từ `@Node("Author")` hoặc field `name`**.

Nếu test muốn xác minh uniqueness:

1. Khởi tạo constraint qua cơ chế schema migration/set up hợp lệ **trước** khi test transaction chạy.
2. Tạo Author cùng tên từ hai write operations khác nhau.
3. Kỳ vọng database/driver/Spring data exception phù hợp, không chỉ nhìn validator Java.
4. Chú ý constraint creation có thể là **schema operation cần transaction riêng**, không cố chạy DDL trong test-managed transaction đang thực hiện DML rồi giả định rollback dọn constraint.
5. Nếu test dùng container share giữa classes, tạo/drop schema có thể ảnh hưởng test khác; cô lập database/schema/test lifecycle.

**Không đưa constraint creation vào mỗi `@BeforeEach` một cách máy móc.** DDL và indexing có chi phí, và test transaction rollback thường không được thiết kế để “hoàn tác schema” giữa methods. Dùng migrations/test fixture setup theo lifecycle phù hợp hoặc một container riêng cho schema-focused tests.

Một index có thể làm query chạy nhanh hơn nhưng một unit graph test với 3 nodes **không chứng minh kế hoạch query trên dữ liệu production**. Khi performance quan trọng, dùng `EXPLAIN/PROFILE`, dataset đại diện và Neo4j engine/edition thích hợp, test riêng khỏi unit/repository correctness tests.

## 11. Neo4jClient, Neo4jTemplate và repository test khác nhau thế nào?

| API | Cách làm việc | Test phù hợp |
| --- | --- | --- |
| `Neo4jRepository<Author, Long>` | Repository proxy, derived methods, custom `@Query` | Public repository contract |
| `Neo4jTemplate` | SDN mapping operations theo domain metadata | Mapping/persistence ngoài repository |
| `Neo4jClient` | Cypher trực tiếp với binding và result mapping | Query result, count node/edge, custom projections |
| Neo4j Java `Driver` | Neo4j Bolt sessions/transactions ở mức driver | Kết nối/protocol, transaction handling, low-level graph |
| Mock repository | Không vào Neo4j thật | Service logic chỉ cần collaborator fake |

**Cần tránh một phép kiểm tra tự xác nhận:** nếu production repository query sai mà test chỉ gọi cùng một repository method để chuẩn bị expected data, cả setup và assertion có thể cùng sai. Với graph test, kết hợp repository setup với một query `Neo4jClient` viết rõ `MATCH ...-[r:TYPE]->...` hoặc đọc raw graph structure giúp giảm rủi ro ấy.

**Tuy vậy:** nếu dùng `Neo4jClient` trong cùng Spring test transaction, nó thấy dữ liệu chưa commit — đó là một điều tốt cho slice verification, nhưng không tự xác minh commit/isolation trên kết nối khác. Khi cần test transaction boundaries, hãy dùng thiết kế integration tường minh và tránh nhầm transaction của test với transaction production.

### Cẩn thận với query mapping đầy đủ aggregate

Giả sử custom query trả nhiều records cho cùng một `Author`:

```cypher
MATCH (a:Author)-[r:WROTE]->(b:Book)
RETURN a, r, b
```

Khi muốn SDN dựng một aggregate với tất cả related nodes, hãy tham khảo cách nhóm/collect relationships và nodes **mỗi root một record** hoặc path mapping theo tài liệu Spring Data Neo4j. Nếu trả nhiều records trùng root mà không đúng cấu trúc mapper chờ đợi, collection properties có thể không được hydrate đầy đủ.

Trong ví dụ runnable, custom query chỉ trả `List<String>` để không trộn một test scalar projection với các phức tạp của aggregate hydration. Repository derived `findByName` chịu trách nhiệm kiểm thử mối quan hệ Author→Books.

## 12. H2 không thay được Neo4j; Testcontainers cũng có giới hạn

**Không có cấu hình `@AutoConfigureTestDatabase(replace = NONE)` theo nghĩa JDBC dành cho Neo4j.** Đó là annotation phục vụ test SQL datasource replacement, không tạo Neo4j graph database. Để kết nối Neo4j, cung cấp `spring.neo4j.*`/`Neo4jConnectionDetails` hoặc custom driver configuration.

Với Boot 3.5, `@ServiceConnection` có thể phát connection details cho Neo4j container; đây là cách code ngắn và ít khả năng trỏ sai URL. Nếu không dùng được nó, có thể dùng `@DynamicPropertySource` và `registry.add("spring.neo4j.uri", container::getBoltUrl)` cùng username/password; **đừng trộn hai cách tùy tiện** và tạo nguồn cấu hình cạnh tranh.

Testcontainers mang lại:

- Neo4j engine thật qua Bolt trong container cô lập.
- Khả năng kiểm tra data mapping, Cypher, transaction và database errors thực.
- Một môi trường nhất quán hơn giữa máy dev và CI có Docker.

Nhưng không tự chứng minh:

- Cluster, replica routing, high availability và transaction bookmarks production.
- Cloud authentication, TLS certificates, network latency, reverse proxies.
- Production data volume/index cardinality, plan cache và performance.
- Quyền truy cập của user production, role-based authorization/enterprise features.
- Mọi cấu hình plugins/extensions hoặc migrations giống môi trường production.

Vì vậy cần một số integration/E2E tests có chọn lọc nếu rủi ro nằm ngoài repository boundary.

## 13. Dữ liệu test sạch và tránh @DirtiesContext sai mục đích

Mỗi method ở `AuthorRepositoryTest` tự tạo Author/Book, và rollback imperative transaction bảo đảm DML đã được test quản lý không để lại nodes committed. Điều đó thường đủ để method độc lập.

Tuy nhiên, **có những ngoại lệ**:

- Test tắt `@Transactional` hoặc dùng `Propagation.NOT_SUPPORTED`.
- Work chạy trong transaction riêng/`REQUIRES_NEW`, commit ngoài test transaction.
- Reactive pipeline không tham gia imperative test transaction.
- Low-level driver mở session độc lập, code external worker hoặc asynchronous side effect commit riêng.
- Test tạo schema constraints/indexes, external events hoặc cache không rollback theo transaction test.

Trong những trường hợp đó, dùng test DB/container riêng, stable fixture IDs và explicit cleanup phù hợp. **Không chạy `MATCH (n) DETACH DELETE n` trên database chưa xác nhận là test-only.**

`@DirtiesContext` làm Spring TestContext tạo lại context khi cần, nhưng **không phải lệnh reset Neo4j server**. Rebuilding context có thể tốn chi phí và không xóa committed data của container đang chạy. Chỉ dùng `@DirtiesContext` khi state của Spring context thực sự thay đổi.

### Container lifecycle và cached ApplicationContext

Một `@Container static` thuộc JUnit class lifecycle; một Spring context có thể được cache/reuse giữa classes. Nếu context giữ Neo4j Driver kết nối đến container đã dừng ở cuối class trước, test class sau dùng lại context có thể lỗi bất ngờ.

Các cách tránh:

- Với ví dụ đơn class, container static quản lý bởi JUnit là đủ.
- Khi chia sẻ nhiều test classes, cân nhắc **context-scoped container bean** hoặc một lifecycle test container phù hợp, bảo đảm container sống ít nhất lâu bằng context đang sử dụng nó.
- Không bật parallel tests dùng chung một graph database có seed/cleanup va chạm mà không có cơ chế isolation.
- Không giữ mutable global container/static repository giữa unrelated suites mà không kiểm soát lifecycle.

**Một test xanh riêng lẻ nhưng đỏ khi chạy suite** thường là dấu hiệu state/transaction/container lifecycle đang bị chia sẻ sai.

## 14. Ví dụ Java 17 thuần: phân biệt hướng cạnh mà không cần Neo4j

Để thấy phần nào có thể test bằng JUnit thuần và phần nào **phải có database**, ta tạo một rule nhỏ đếm quan hệ có hướng trong bộ dữ liệu Java:

Tạo `src/main/java/example/testing/neo4j/GraphRule.java`:

```java
package example.testing.neo4j;

import java.util.List;
import java.util.Objects;

public final class GraphRule {
    private GraphRule() {
    }

    public record Edge(String from, String to) {
    }

    public static long outgoingCount(
            List<Edge> edges, String from) {
        Objects.requireNonNull(edges, "edges");
        return edges.stream()
                .filter(edge -> Objects.equals(
                        edge.from(), from))
                .count();
    }

    public static boolean hasDirectedEdge(
            List<Edge> edges, String from, String to) {
        return edges.stream()
                .anyMatch(edge -> Objects.equals(
                        edge.from(), from)
                        && Objects.equals(edge.to(), to));
    }
}
```

Tạo `src/main/java/example/testing/neo4j/GraphRuleDemo.java`:

```java
package example.testing.neo4j;

import java.util.List;

public class GraphRuleDemo {
    public static void main(String[] args) {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Graph Basics"),
                new GraphRule.Edge("An", "Cypher Patterns"),
                new GraphRule.Edge("Mai", "Data Modeling"));

        System.out.println(
                GraphRule.outgoingCount(edges, "An"));
        System.out.println(
                GraphRule.hasDirectedEdge(
                        edges, "An", "Graph Basics"));
        System.out.println(
                GraphRule.hasDirectedEdge(
                        edges, "Graph Basics", "An"));
    }
}
```

Biên dịch/chạy bằng JDK 17+ tại root project:

```bash
javac -d out src/main/java/example/testing/neo4j/GraphRule.java src/main/java/example/testing/neo4j/GraphRuleDemo.java
java -cp out example.testing.neo4j.GraphRuleDemo
```

Stdout **chính xác**:

```text
2
true
false
```

Tạo `src/test/java/example/testing/neo4j/GraphRuleTest.java`:

```java
package example.testing.neo4j;

import java.util.List;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GraphRuleTest {

    @Test
    void countsOutgoingEdgesOnly() {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Book A"),
                new GraphRule.Edge("Book A", "An"),
                new GraphRule.Edge("An", "Book B"));

        assertEquals(2L, GraphRule.outgoingCount(edges, "An"));
    }

    @Test
    void directionIsNotSymmetricByDefault() {
        List<GraphRule.Edge> edges = List.of(
                new GraphRule.Edge("An", "Book A"));

        assertTrue(
                GraphRule.hasDirectedEdge(
                        edges, "An", "Book A"));
        assertFalse(
                GraphRule.hasDirectedEdge(
                        edges, "Book A", "An"));
    }
}
```

Đây là **2 JUnit unit tests**, chạy không cần Spring context hoặc Neo4j:

```bash
./gradlew test --tests example.testing.neo4j.GraphRuleTest
```

**Tách ranh giới rõ:** các case Java thuần chỉ chứng minh logic của `GraphRule` trên List<Edge> giả lập. Chúng **không chứng minh** Spring Data Neo4j đã tạo cạnh WROTE trong database. Test `@DataNeo4jTest` với `Neo4jClient` là bằng chứng cần thiết cho mapping và Cypher thực.

## 15. Debug và các lỗi thường gặp

**1. Nghĩ `@DataNeo4jTest` tự khởi chạy Neo4j embedded.** Spring Data Neo4j 7.x không tự cung cấp database; cần Testcontainers/harness/test server.

**2. Dùng `@DataJpaTest` cho `@Node`.** JPA/Hibernate không xử lý Spring Data Neo4j mapping. Chọn slice theo persistence technology.

**3. Import sai package của `@DataNeo4jTest` giữa Boot 3.5 và Boot 4.** Kiểm tra BOM/module/version và import thực tế; đừng ghép ví dụ hai thế hệ.

**4. Mock `AuthorRepository` rồi kết luận Cypher đúng.** Mock không chạy Bolt, không kiểm tra labels/edges/queries. Giữ repository và client thật trong slice test.

**5. Chỉ assert Java List size trước khi lưu.** Nó không chứng minh database có cạnh. Query Cypher đếm relationships sau save.

**6. Nhầm `INCOMING` và `OUTGOING`.** Node ↔ node có cùng hai đầu nhưng hướng khác nhau là quan hệ khác; test chiều theo contract.

**7. Kiểm tra `findById` mà không kiểm tra related nodes.** Dữ liệu root có thể đúng nhưng relationship mapping sai; test hydrate và query edge count.

**8. Tin thứ tự của relationship List.** Không có explicit order, database không hứa trả đúng insertion order. Assert set/sorted values nếu order không phải contract.

**9. Viết Cypher bằng nối chuỗi input.** Dùng `$parameter` và `@Param`/Neo4jClient.bind thay vì interpolation.

**10. Custom query trả trùng root records rồi nghĩ mapping đầy đủ.** SDN có yêu cầu về shape của records/nodes/relationships; dùng scalar projection hoặc custom mapping có kiểm soát.

**11. Nhầm thiếu root với root có collection rỗng.** `Optional.empty` khác `Author.books=[]`. Viết cả hai case.

**12. Giả định internal Neo4j ID là business key.** Không assert ID liên tiếp hoặc expose nó như stable public identifier; ưu tiên UUID/key có constraint nếu cần.

**13. Quên UNIQUE constraint hoặc migration schema.** Neo4j không tự tạo uniqueness chỉ nhờ `@Node`; test constraint cần setup DB đúng lifecycle.

**14. Chạy constraint DDL trong test transaction rồi mong rollback.** Schema lifecycle khác DML; tạo qua test DB setup/migrations phù hợp.

**15. Gắn `@Transactional` rồi tưởng mọi reactive writes được rollback.** Test-managed imperative transaction không bao phủ reactive pipeline; dùng ReactiveTransactionManager/TransactionalOperator và cleanup.

**16. Dùng test đã commit dữ liệu rồi phụ thuộc order.** Test class chia sẻ Neo4j container có thể rò nodes; giữ transaction rollback hoặc explicit cleanup.

**17. Dùng Neo4j Driver session khác để đọc uncommitted data.** Một connection/transaction độc lập có thể không thấy row/node test chưa commit; hiểu transaction boundaries.

**18. Không kiểm soát Docker/container lifecycle.** Context cache có thể sống lâu hơn container; khi nhiều classes share context cần lifecycle thống nhất.

**19. Dùng test graph nhỏ để chứng minh index/performance production.** Cần representative dataset, EXPLAIN/PROFILE và môi trường tương tự production.

**20. Dùng `@SpringBootTest` cho mọi test repository.** Full context thường chậm và khó chẩn đoán; dùng slice khi chỉ cần Cypher/mapping.

## 16. Checklist QA cho @DataNeo4jTest

**Trước khi chạy:**

- Đúng version Spring Boot, Spring Data Neo4j và Testcontainers chưa?
- `@Node`, `@Id`, `@GeneratedValue`, `@Relationship` được import từ **Spring Data Neo4j**, không phải JPA?
- Có Neo4j test instance thật, `@ServiceConnection` hoặc `@DynamicPropertySource` hợp lệ?
- Test kết nối đến **database test**, không đến production?
- Container lifecycle có phù hợp context cache/parallel execution?

**Đối với mapping:**

- Có kiểm tra node label, properties, generated ID và load lại từ database?
- Cạnh có đúng **type, direction, số lượng**?
- Có object con/nested relationship nào cần hydration?
- Collection test có so nội dung mà không dựa vào thứ tự không được bảo đảm?
- Các relationship properties nếu có được lưu/read đúng và có `@TargetNode`/`@RelationshipId`?

**Đối với Cypher:**

- Query dùng `$params` thay string concatenation?
- Có test cả match, no match, missing root, empty relationships?
- `MATCH`/`OPTIONAL MATCH` và null semantics có đúng contract?
- Query trả scalar hay full aggregate? Record shape có đủ để map?
- Có `ORDER BY` khi test/ứng dụng cần deterministic ordering?
- Constraints/indexes/migrations nếu thuộc contract có được thiết lập và test riêng?

**Đối với isolation và chất lượng:**

- Test imperative có rollback? Có tránh suy diễn rằng dữ liệu đã commit?
- Test reactive đã có transaction/cleanup riêng, không dựa vào rollback imperative?
- Nếu tắt transaction, có cleanup test data và namespace riêng?
- Có kết hợp repository và Neo4jClient để xác minh graph thật?
- Có giữ service/controller/security tests ở level riêng phù hợp?
- Có kiểm tra Testcontainers startup khi lỗi từ Docker thay vì code?
- Kết luận của test có giới hạn đúng phạm vi **Neo4j graph/persistence**?

**Kết luận:** `@DataNeo4jTest` là lựa chọn phù hợp để kiểm chứng **mapping nodes/relationships và Cypher repository queries** bằng một Spring context hẹp **với Neo4j instance thật**. Để test có giá trị, hãy chứng minh các cạnh `WROTE` theo **type + direction + số lượng**, các nodes được nạp và kết quả query được bind/sắp xếp đúng. Testcontainers + `@ServiceConnection` đem lại môi trường lặp lại được; transaction rollback giúp cô lập imperative tests. Với reactive access, schema constraints, multi-service orchestration hoặc production performance, cần bổ sung test ở boundary tương ứng thay vì suy diễn từ một slice xanh.

## 17. Tài liệu tham khảo

- [Spring Boot 3.5 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): phạm vi `@DataNeo4jTest`, rollback và reactive caveat.
- [Spring Data Neo4j 7.5 — Testing with Spring Boot](https://docs.spring.io/spring-data/neo4j/reference/7.5/testing/testing-with-spring-boot.html): Neo4jClient/repository slice và Testcontainers/harness.
- [Spring Boot 3.4/3.5 — Testcontainers Service Connections](https://docs.spring.io/spring-boot/3.4/reference/testing/testcontainers.html): Neo4jContainer, `@ServiceConnection`/Neo4jConnectionDetails.
- [Spring Data Neo4j — Metadata-based Mapping](https://docs.spring.io/spring-data/neo4j/reference/object-mapping/metadata-based-mapping.html): `@Node`, `@Relationship`, `@RelationshipProperties` và `@TargetNode`.
- [Spring Data Neo4j 7.5 — Handling IDs](https://docs.spring.io/spring-data/neo4j/reference/7.5/object-mapping/mapping-ids.html): internal IDs, UUID generators và business keys.
- [Spring Data Neo4j — Custom Queries](https://docs.spring.io/spring-data/neo4j/reference/appendix/custom-queries.html): `@Query`, parameter binding và aggregate mapping pitfalls.
