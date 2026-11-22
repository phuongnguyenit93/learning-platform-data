# Đối chiếu SQL sinh ra và hành vi tải quan hệ sau nâng cấp

## 1. Mục tiêu: kiểm chứng hành vi thực tế, không chỉ kiểm tra ứng dụng khởi động

Khi nâng cấp **Spring Data JPA**, **Spring Boot**, **Hibernate/JPA provider** hoặc driver/database dialect, mã repository và JPQL có thể không đổi nhưng SQL phát sinh, kế hoạch truy vấn, số lần tải quan hệ và thời điểm khởi tạo association vẫn thay đổi. Một bộ kiểm thử chỉ xác nhận ứng dụng khởi động hay API trả HTTP 200 sẽ không phát hiện hết các vấn đề này.

Ví dụ một API trả danh sách 100 cuốn sách kèm tên tác giả:
- Trước nâng cấp: một query lấy sách và vài query lấy tác giả.
- Sau nâng cấp: số query tăng thành hàng chục hoặc số `JOIN` tăng mạnh; kết quả JSON nhìn vẫn đúng nhưng thời gian phản hồi giảm đáng kể.
- Một biến thể khác: sau nâng cấp dữ liệu quan hệ chỉ còn là proxy chưa khởi tạo; khi tầng web serialize bên ngoài transaction, API gặp `LazyInitializationException`.
- Chiều ngược lại: do thay đổi fetch plan, ORM bắt đầu tải nhiều bảng/collection hơn dự kiến; tiêu thụ RAM và dữ liệu truyền từ database tăng dù số SQL giảm.

**Mục tiêu kiểm chứng gồm hai phần độc lập:**
1. **Tính đúng đắn:** đúng số entity, đúng quan hệ, không rơi bản ghi, không lặp sai bản ghi, đúng thứ tự, đúng page và dữ liệu API.
2. **Hiệu năng/SQL:** SQL được chạy thực sự, bind values, số round-trip, số row đọc, join/subselect, chỉ mục và execution plan phù hợp với mức tải thực.

Không mặc định coi SQL đổi alias, thứ tự cột hoặc cách đặt dấu ngoặc là lỗi. JPA không hứa chuỗi SQL cố định giữa các provider/phiên bản; thứ cần bảo vệ là **ngữ nghĩa, giao ước tải dữ liệu và ngưỡng hiệu năng có cơ sở**.

## 2. Những thành phần nào có thể thay đổi khi nâng cấp?

| Lớp thay đổi | Tác động cần quan sát |
| --- | --- |
| Spring Boot dependency management | Phiên bản Spring Data, Hibernate, JDBC driver, transaction infrastructure |
| Spring Data JPA | Repository query derivation, phân tích `@Query`, projection, count query, `Pageable`, `@EntityGraph` |
| Hibernate/JPA provider | Dịch JPQL/Criteria thành SQL, fetch plan, xử lý kết quả join, lazy proxy, batch fetching, cache |
| Jakarta Persistence | Mapping `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany`, `FetchType`, entity graph và lifecycle |
| JDBC driver và dialect | SQL pagination, cách bind type, cú pháp function/sequence, khả năng DB, execution plan |
| Database schema/index/data | Foreign key, cardinality, statistics của optimizer, index, row count và độ chọn lọc |
| Cấu hình ứng dụng | Open EntityManager in View (OSIV), transaction scope, L2/query cache, `default_batch_fetch_size`, filters |
| Tầng serialization | DTO mapping, Jackson getter, lazy association được truy cập ở transaction hay controller |

Việc đổi một lúc nhiều lớp khiến khó quy trách nhiệm. Trước khi so sánh, **ghi phiên bản chính xác** của Spring Boot, Spring Data JPA, Hibernate, Java, JDBC driver, database engine và dialect trên cả baseline lẫn target. Không chỉ ghi “Hibernate 6” vì các bản minor có thể sửa query translation hoặc fetch behavior.

**Trường hợp đáng quan tâm: Hibernate 5.x → 6.x.** Hibernate 6 chuyển sang mô hình SQL AST/SQM mới nên SQL có thể đổi hình dạng: alias cột, join không cần thiết, phân giải path, kết quả của một số HQL query, logic fetch và pagination. Hướng dẫn migration Hibernate 6.0 còn ghi nhận:
- Hibernate 6 tự loại bản sao cùng root entity trong kết quả `join fetch` collection; việc `distinct` trong JPQL/HQL cũng được truyền tới SQL, và hint cũ `HINT_PASS_DISTINCT_THROUGH` đã bị bỏ.
- Cách đi qua các association eager trong một số graph/quan hệ tự tham chiếu có thể tạo nhiều join hơn.
- Một số cấu hình `@Fetch(FetchMode.JOIN)` kết hợp lazy có cách tôn trọng laziness khác trước.
- Chuyển `javax.persistence.*` → `jakarta.persistence.*` trong các đợt nâng cấp Jakarta; mapping và các API liên quan cần kiểm tra lại.

**Không áp dụng máy móc mọi điểm trên cho tất cả các bản Hibernate:** đọc migration guide của *đúng* phiên bản nguồn/đích và xác nhận bằng SQL đo được.

## 3. Hiểu đúng các kiểu tải quan hệ trước khi so sánh

### 3.1. Mapping fetch mode là điểm xuất phát, không phải kết quả đo SQL

Theo JPA, mặc định:
- `@ManyToOne` và `@OneToOne`: `FetchType.EAGER`.
- `@OneToMany` và `@ManyToMany`: `FetchType.LAZY`.

`EAGER` đòi hỏi provider tải association tương ứng; điều này **không có nghĩa phải dùng một câu SQL duy nhất**. Provider có thể sinh `JOIN` hoặc secondary select. `LAZY` là chủ ý trì hoãn việc tải và mức hỗ trợ chi tiết có thể phụ thuộc provider, proxy, bytecode enhancement, kiểu quan hệ và mapping. Đặc biệt `@OneToOne` phía nghịch đảo và quan hệ tùy chọn có những trường hợp Hibernate phải truy vấn bổ sung để biết sự tồn tại của đối tượng liên kết.

Một method repository có `@EntityGraph`, JPQL `join fetch`, Hibernate `@Fetch` hoặc batch fetching có thể **ghi đè/bổ sung fetch plan** của mapping. Khi so sánh, phải nhìn cả annotation ở entity **và** lời gọi repository cụ thể.

Ví dụ tối thiểu:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(name = "author_id", nullable = false)
private BookAuthor author;
```

Association `author` không nhất thiết được tải đầy đủ cùng root `Book` khi chỉ query danh sách sách. Khi gọi `book.getAuthor().getName()`, provider có thể phải phát thêm SQL. Nếu có hai cuốn sách dùng cùng một tác giả trong cùng persistence context, không nhất thiết mỗi cuốn đều tạo một SQL riêng: JPA L1 đã có thể tái sử dụng entity theo id.

### 3.2. N+1 là hành vi phụ thuộc đường truy cập

Một ví dụ N+1 phổ biến: `SELECT` đầu lấy N root entity, sau đó việc đọc thuộc tính association của từng root phát sinh các `SELECT` phụ. Tuy nhiên, số query thực tế chịu ảnh hưởng của:
- số id liên kết **khác nhau** và entity đã managed trong L1;
- Hibernate L2 cache và query cache (nếu bật);
- `@BatchSize` / `hibernate.default_batch_fetch_size` hoặc fetch bằng subselect;
- graph, join fetch hoặc fetch depth;
- nơi truy cập getter: service, mapper DTO, Jackson serializer, log hay `toString()`.

Vì thế, “N+1 = chính xác N+1 câu SQL” là tên của một mẫu vấn đề, **không phải công thức đúng với mọi fixture**.

### 3.3. Nạp collection và pagination có thêm rủi ro

`JOIN FETCH` collection `@OneToMany` khiến một root có nhiều child xuất hiện thành nhiều **SQL rows**. Hibernate có thể trả về một entity root duy nhất trong kết quả Java tùy phiên bản/cách xử lý, nhưng số hàng truyền qua JDBC vẫn có thể tăng mạnh.

Kết hợp pagination trực tiếp với collection fetch join dễ sai hoặc rất tốn kém: Hibernate có thể phải tải nhiều row rồi phân trang ở bộ nhớ; khi bật `hibernate.query.fail_on_pagination_over_collection_fetch=true`, nó có thể phát lỗi thay vì âm thầm làm như vậy. Cần test cả `Page.getTotalElements()`, số phần tử duy nhất, thứ tự, và SQL thực tế.

Một giải pháp thường dùng khi phân trang:
1. Query lấy **page id của root** với bộ lọc và thứ tự ổn định.
2. Query thứ hai fetch quan hệ cho tập id đó bằng `IN`, `@EntityGraph` hoặc truy vấn chuyên biệt.
3. Sắp xếp kết quả cuối theo thứ tự id ban đầu trong application nếu SQL thứ hai không giữ nguyên thứ tự.

Không kỳ vọng `JOIN FETCH` nhiều collection “giảm số SQL” luôn tốt hơn: row multiplication/cartesian product và lỗi multiple bag fetch có thể khiến phương án đó tệ hơn batch loading.

## 4. Thiết lập phép so sánh trước và sau nâng cấp

### 4.1. Khóa các biến để so sánh công bằng

Trước khi thay dependency, tạo **baseline có thể tái chạy**:

1. Lưu commit/tag ứng dụng cũ cùng lockfile/dependency tree (`mvn dependency:tree` hoặc `./gradlew dependencies`).
2. Ghi phiên bản Java, Spring Boot, Spring Data JPA, Hibernate, driver, database, dialect và settings quan trọng.
3. Dùng cùng schema migration (Flyway/Liquibase), index và **fixture dữ liệu có tương quan thực tế**: nhiều root, ít/nhiều child, quan hệ null, soft-deleted row, nhiều tenant, dữ liệu lớn.
4. Giữ cùng transaction scope, OSIV, fetch graph, phương thức repository, logic DTO và thời điểm truy cập getter.
5. Tách lượt **cold cache** và **warm cache**. Xóa L1 giữa phép đo; bật/tắt L2/query cache theo đúng kịch bản. Không để lượt trước vô tình làm lượt sau nhanh hơn.
6. Chạy trên cùng database engine/version (tốt nhất là container tương đương production); thay cả database và Hibernate cùng lúc không giúp quy nguyên nhân.
7. Chạy workload giống nhau: tham số query, page size, sorting, concurrency, mức dữ liệu và connection pool.

Với Spring Boot, kiểm tra runtime dependency thực sự đã resolve thay vì chỉ nhìn version trong `pom.xml`/`build.gradle`. Một thư viện có thể kéo thêm version Hibernate khác qua dependency override.

### 4.2. Các luồng nghiệp vụ phải được chụp baseline

Nên chọn tập truy vấn quan trọng, ít nhất bao gồm:
- `findById` một root và truy cập to-one/to-many;
- repository `findAll`/derived query và mapping sang DTO có dùng association;
- truy vấn có `@Query`, `@EntityGraph` hoặc `join fetch`;
- pagination + sorting + filter, nhất là to-many;
- projection interface/DTO, native query và Criteria/Specification nếu ứng dụng dùng;
- lazy access **sau transaction**, khi `spring.jpa.open-in-view=false`;
- ghi dữ liệu rồi đọc lại trong transaction khác để tránh L1 che thay đổi;
- soft-delete/tenant filter/inheritance/self-reference, nếu xuất hiện trong domain.

Không phải mọi query đều cần snapshot chuỗi SQL tuyệt đối. Chọn những nơi SQL shape là một phần giao ước cần kiểm soát: tránh full table scan, không phát sinh thêm query theo số lượng bản ghi, và dùng đúng điều kiện lọc.

## 5. Bật logging và số liệu đúng tầng

### 5.1. Hibernate 6: SQL, bind parameters và statistics

Trong môi trường dev/test (không bật TRACE bind chứa dữ liệu nhạy cảm tại production):

**`src/test/resources/application.properties`**

```properties
spring.jpa.show-sql=false
spring.jpa.properties.hibernate.format_sql=true
spring.jpa.properties.hibernate.generate_statistics=true
spring.jpa.properties.hibernate.cache.use_second_level_cache=false
spring.jpa.properties.hibernate.cache.use_query_cache=false
spring.jpa.open-in-view=false

logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
```

`org.hibernate.SQL` ghi SQL template. Logger `org.hibernate.orm.jdbc.bind` (Hibernate 6) giúp quan sát giá trị bind, kiểu dữ liệu; Hibernate 5.x từng dùng logger như `org.hibernate.type.descriptor.sql.BasicBinder`. Cấu hình log cụ thể **phải đối chiếu phiên bản thực tế**. Khi so sánh, lưu cả bind values: hai câu SQL text giống nhau với điều kiện bind khác nhau có thể chạy kế hoạch hoàn toàn khác.

Có thể lấy `Statistics` từ Hibernate `SessionFactory`:

```java
SessionFactory sessionFactory =
        entityManagerFactory.unwrap(SessionFactory.class);
Statistics stats = sessionFactory.getStatistics();

long sqlStatements = stats.getPrepareStatementCount();
long entityLoads = stats.getEntityLoadCount();
long collectionFetches = stats.getCollectionFetchCount();
```

Đây là đoạn **minh họa trong một method** có biến `entityManagerFactory` và các import `org.hibernate.SessionFactory`, `org.hibernate.stat.Statistics`. Bộ đếm cần bật trước khi đo và nên xóa/reset trước mỗi scenario. `Statistics` là số liệu phạm vi SessionFactory; nếu test chạy song song, chúng có thể lẫn hoạt động khác. `getPrepareStatementCount()` đếm JDBC prepared statement, **không phải độ trễ hoặc số physical rows đọc**.

Với Hibernate 5 và Hibernate 6, việc thay đổi logger/statistics API tùy version cũng là một phần của kế hoạch nâng cấp; đừng sao chép cấu hình cũ và mặc định tưởng log đang hoạt động.

### 5.2. Bổ sung SQL capture và database plan

Để đối chiếu chính xác theo test, có thể dùng `StatementInspector` của Hibernate hoặc JDBC datasource proxy/P6Spy trong môi trường test để thu SQL **của một luồng/giao dịch cụ thể**. Chỉ lưu bind params được phép; tránh lộ token, dữ liệu cá nhân hoặc bí mật.

Với query chậm, lấy `EXPLAIN`/`EXPLAIN ANALYZE` trên database tương ứng; đo:
- `JOIN`/`SELECT` shape, filter/order, index và scan type;
- số row ước lượng/thực tế, sort/hash, nested loop, temporary data;
- thời gian ở database và thời gian trong application;
- p50/p95/p99 latency dưới workload đủ lớn.

SQL đẹp hơn về mặt độ dài chưa chắc nhanh hơn. Một câu `JOIN` phức tạp có thể tốn hơn vài câu `SELECT` nhỏ; mục tiêu là truy cập dữ liệu chính xác với độ trễ chấp nhận được.

## 6. Ví dụ Java 17+ có thể dùng làm regression test

Các file dưới đây sử dụng Spring Boot 3.x, Spring Data JPA, Hibernate 6.x, Java 17+ và H2 cho bài test. Đặt đúng package `example.sqlcompare`; cần các dependency `spring-boot-starter-data-jpa`, `spring-boot-starter-test` và `com.h2database:h2` ở test runtime. Test dùng Hibernate statistics để đo **cùng một dữ liệu**, so sánh lazy load, `join fetch` và `@EntityGraph`.

H2 chỉ là môi trường dạy cách kiểm tra. Để kết luận về production SQL và execution plan, cần chạy thêm bộ test trên database/dialect thật (ví dụ PostgreSQL Testcontainers), với schema migration thực tế.

### 6.1. Khởi tạo ứng dụng

**`JpaSqlCompareApplication.java`**

```java
package example.sqlcompare;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JpaSqlCompareApplication {
    public static void main(String[] args) {
        SpringApplication.run(JpaSqlCompareApplication.class, args);
    }
}
```

### 6.2. Hai entity có quan hệ nhiều sách → một tác giả

**`BookAuthor.java`**

```java
package example.sqlcompare;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "book_authors")
public class BookAuthor {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected BookAuthor() {
    }

    public BookAuthor(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

**`LibraryBook.java`**

```java
package example.sqlcompare;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;

@Entity
@Table(name = "library_books")
public class LibraryBook {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "author_id", nullable = false)
    private BookAuthor author;

    protected LibraryBook() {
    }

    public LibraryBook(String title, BookAuthor author) {
        this.title = title;
        this.author = author;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public BookAuthor getAuthor() {
        return author;
    }
}
```

### 6.3. Repository với ba fetch plan

**`LibraryBookRepository.java`**

```java
package example.sqlcompare;

import java.util.List;
import org.springframework.data.jpa.repository.EntityGraph;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface LibraryBookRepository
        extends JpaRepository<LibraryBook, Long> {

    @Query("""
        select b from LibraryBook b
        join fetch b.author
        order by b.id
        """)
    List<LibraryBook> findAllWithAuthor();

    @EntityGraph(attributePaths = "author")
    @Query("select b from LibraryBook b order by b.id")
    List<LibraryBook> findAllWithAuthorGraph();
}
```

- `findAll(Sort.by("id"))` kế thừa `JpaRepository`: tải root books, association tác giả vẫn lazy.
- `findAllWithAuthor()` chỉ định `join fetch`: trong tình huống to-one này, Hibernate thường đưa sách và tác giả vào **một SQL JOIN**.
- `findAllWithAuthorGraph()` chỉ định fetch graph của `author`. `@EntityGraph` quy định thuộc tính cần tải, **không hứa chuỗi SQL JOIN y hệt JPQL** trên mọi provider và version.

### 6.4. Test đo số SQL và so sánh nội dung

**`src/test/java/example/sqlcompare/FetchPlanRegressionTest.java`**

```java
package example.sqlcompare;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.jpa.properties.hibernate.generate_statistics=true",
        "spring.jpa.properties.hibernate.cache.use_second_level_cache=false",
        "spring.jpa.properties.hibernate.cache.use_query_cache=false"
})
class FetchPlanRegressionTest {
    @PersistenceContext
    EntityManager entityManager;

    @Autowired
    EntityManagerFactory entityManagerFactory;

    @Autowired
    LibraryBookRepository repository;

    @Test
    void comparesLazyAccessWithFetchJoinAndEntityGraph() {
        BookAuthor an = new BookAuthor("An");
        BookAuthor binh = new BookAuthor("Binh");
        entityManager.persist(an);
        entityManager.persist(binh);

        entityManager.persist(new LibraryBook("Book-1", an));
        entityManager.persist(new LibraryBook("Book-2", binh));
        entityManager.persist(new LibraryBook("Book-3", an));

        entityManager.flush();
        entityManager.clear();

        Statistics stats = entityManagerFactory
                .unwrap(SessionFactory.class).getStatistics();

        // Trường hợp 1: query root rồi truy cập association LAZY.
        stats.clear();
        List<LibraryBook> plain = repository.findAll(Sort.by("id"));
        List<String> plainNames = plain.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long plainSql = stats.getPrepareStatementCount();

        // Trường hợp 2: JPQL fetch join.
        entityManager.clear();
        stats.clear();
        List<LibraryBook> joined = repository.findAllWithAuthor();
        List<String> joinedNames = joined.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long joinedSql = stats.getPrepareStatementCount();

        // Trường hợp 3: EntityGraph.
        entityManager.clear();
        stats.clear();
        List<LibraryBook> graphed = repository.findAllWithAuthorGraph();
        List<String> graphNames = graphed.stream()
                .map(book -> book.getAuthor().getName())
                .toList();
        long graphSql = stats.getPrepareStatementCount();

        assertThat(plainNames).containsExactly("An", "Binh", "An");
        assertThat(joinedNames).isEqualTo(plainNames);
        assertThat(graphNames).isEqualTo(plainNames);

        assertThat(joinedSql).isEqualTo(1L);
        assertThat(plainSql).isGreaterThan(joinedSql);
        assertThat(graphSql).isEqualTo(1L);
    }
}
```

Chạy trong project Maven có Maven Wrapper:

```bash
./mvnw test -Dtest=FetchPlanRegressionTest
```

Trên Windows có thể dùng `mvnw.cmd test -Dtest=FetchPlanRegressionTest`. Dùng Gradle thì chạy task `test` với filter tương đương. Test **không khẳng định stdout của ứng dụng**; điều kiện thành công là test PASS với ba nhóm assertion.

Trong fixture có 3 cuốn sách và 2 tác giả khác nhau. Nếu không bật L2, việc đọc danh sách root rồi truy cập tác giả LAZY thường cho **1 query sách + 2 query tác giả**, trong khi join fetch một quan hệ to-one thường cần **1 query**. Assertions chỉ yêu cầu `plainSql > joinedSql` để tránh trói bài test vào số query truy xuất lazy được tối ưu hóa theo implementation; `joinedSql == 1` và `graphSql == 1` là **kỳ vọng kiểm chứng cho Hibernate 6 + H2 của ví dụ**. Nếu bản nâng cấp thay đổi điều đó, hãy xem SQL và nguyên nhân trước khi cập nhật kỳ vọng.

`Statistics` cộng dồn trong `SessionFactory`: chạy test này độc lập, không chạy song song những test cũng dùng cùng factory nếu cần số đếm chặt chẽ. Việc `clear()` sau mỗi phương án giúp tránh entity đã managed ở L1 làm phương án sau không cần query nữa. Cả việc seed/flush dữ liệu diễn ra **trước** khi `stats.clear()` nên lệnh `INSERT` không làm nhiễu phép đo.

### 6.5. Điều chỉnh theo production

Khi ứng dụng có nhiều quan hệ, test thêm:
- `@OneToMany` collection có 0, 1 và nhiều phần tử; kiểm tra tổng số row và tập root id duy nhất.
- Association nullable và bảng có dữ liệu bị filter/soft delete; so sánh `LEFT JOIN` và `INNER JOIN`.
- Page đầu, page giữa và page cuối; đảm bảo thứ tự ổn định và đúng `totalElements`.
- Query projection chỉ chọn một phần cột; bảo vệ query không tải trọn graph ngoài ý muốn.
- Các path đọc từ controller/mapper; test với OSIV disabled để phát hiện lazy access ngoài transaction.

Nếu trường hợp nghiệp vụ cho phép backend tạo nhiều SQL nhưng vẫn nhanh, đừng sửa code chỉ để đạt một SQL duy nhất. Thay vì áp chung kỳ vọng của ví dụ, xác định ngân sách query/latency riêng dựa trên dữ liệu và SLA.

## 7. Đọc bản diff SQL sau nâng cấp

### 7.1. Nên so sánh những gì?

| Thuộc tính | Giá trị khi đối chiếu |
| --- | --- |
| Tổng số statement | Có xuất hiện N+1 hay query phát sinh khi serialize DTO/JSON? |
| Loại SQL | `SELECT`, `UPDATE`, `DELETE`, count query, subselect |
| Số và hướng `JOIN` | `INNER` hay `LEFT`; có mất root thiếu child, có fetch thừa? |
| `WHERE` | Tenant/soft-delete/authorization predicates có còn đúng? |
| `ORDER BY` / pagination | Có thứ tự ổn định, offset/limit được đẩy xuống DB? |
| Bind parameters | Giá trị/kiểu khác nhau có làm query plan đổi? |
| Row/cardinality | Có bị nhân hàng với to-many, rơi row do join sai? |
| Select list | Có tải quá nhiều cột/LOB, alias thay đổi gây lỗi native mapping? |
| DB execution plan | Index scan/seq scan, sort/hash, rows estimate vs actual |
| Entity initialization | Quan hệ nào initialized trước/sau truy cập, có secondary select? |
| Result/data | JSON/DTO, root id, child id, count và page có đúng không? |
| Cache | L1/L2/query cache hit/miss; có đang che truy vấn SQL? |

Các SQL dưới đây là **minh họa hình dạng**, không phải literal output cam kết của Hibernate:

Không fetch author:

```sql
SELECT b.id, b.title, b.author_id
FROM library_books b
ORDER BY b.id;

-- Có thể phát sinh sau khi truy cập getAuthor().getName():
SELECT a.id, a.name
FROM book_authors a
WHERE a.id = ?;
```

Fetch join to-one:

```sql
SELECT b.id, b.title, b.author_id, a.id, a.name
FROM library_books b
JOIN book_authors a ON a.id = b.author_id
ORDER BY b.id;
```

Alias, thứ tự cột, cú pháp join và cách bọc SQL có thể khác theo ORM/dialect. So sánh bằng **SQL shape + tham số + kết quả + số SQL**; chỉ so chuỗi ký tự SQL sẽ tạo nhiều false positive.

### 7.2. Ghi nhật ký kết quả so sánh có bằng chứng

Một mẫu báo cáo cho mỗi critical query:

| Trường | Nội dung |
| --- | --- |
| Query ID | `books.listWithAuthor` |
| Source | `LibraryBookRepository.findAllWithAuthor()` |
| Baseline | Commit, Boot/Data JPA/Hibernate/driver/dialect/database versions |
| Target | Commit và phiên bản tương ứng |
| Fixture | 3 books/2 authors cho unit regression; quy mô production-like cho benchmark |
| Result correctness | IDs, thứ tự, association values, page/count |
| SQL before/after | File log đã khử dữ liệu nhạy cảm, vị trí query |
| Statement count | `plainSql`, `joinedSql`, `graphSql`, warm/cold |
| Plan/latency | `EXPLAIN ANALYZE`, p95 dưới workload mô tả |
| Verdict | PASS, cần tối ưu, hoặc regression có bằng chứng |

Giữ artifact của baseline và target riêng. Nếu nâng cấp làm SQL đổi alias nhưng query count/result/performance vẫn đúng, ghi nhận **thay đổi hợp lệ** thay vì coi là regressions.

## 8. Những sai lệch thường gặp sau nâng cấp và cách xử lý

### 8.1. EAGER kéo theo nhiều SQL hoặc join hơn

Ví dụ entity có nhiều `@ManyToOne` mặc định EAGER, đặc biệt quan hệ tự tham chiếu nhiều tầng. Provider có thể mở rộng graph join hoặc dùng secondary selects khác bản cũ.

**Cách xử lý:** rà lại mapping, đặt `LAZY` cho to-one khi nghiệp vụ thích hợp và provider hỗ trợ, sau đó nêu rõ fetch plan cho từng use case qua `@EntityGraph`/`join fetch`. Không đổi tất cả association sang LAZY mà bỏ qua nơi service truy cập chúng ngoài transaction.

### 8.2. Xuất hiện N+1 trong mapper/serializer

Test repository chỉ gọi `findAll()` nên thấy một câu SQL, nhưng khi tạo DTO/JSON mới gọi `book.getAuthor().getName()` thì phát sinh SELECT thứ cấp.

**Cách xử lý:** đo toàn bộ hành trình đọc, không dừng ở repository return. Khi use case cần author, fetch ở query hoặc projection chỉ lấy trường cần thiết. Test với OSIV disabled để lộ đường truy cập không có transaction rõ ràng.

### 8.3. `@EntityGraph` không bảo đảm SQL y hệt `join fetch`

`@EntityGraph` chỉ thị graph tải thuộc tính; provider có thể quyết định cách SQL khác với JPQL explicit join fetch. `FETCH graph` và `LOAD graph` cũng có semantics khác nhau với các thuộc tính không nằm trong graph. Theo JPA, fetch graph đánh dấu các thuộc tính nêu ra là eager và những thuộc tính khác có thể được xem là lazy theo semantics graph (provider được phép fetch thêm); load graph giữ fetch policy từ mapping cho các thuộc tính không nêu.

**Cách xử lý:** đo từng repository method, kiểm tra eager/lazy initialization và SQL thực tế. Không kết luận chỉ từ tên annotation.

### 8.4. Kết quả collection fetch join có số phần tử gốc khác

Trong Hibernate 6, duplicate root entity do join fetch collection được xử lý khác so với một số bản trước, và cách dùng `DISTINCT`/hint cũ cũng thay đổi. Tuy nhiên điều này không tự giải quyết số **SQL rows** nhân lên và không thay thế việc kiểm tra page/count.

**Cách xử lý:** assert tập root ids, số child mỗi root, thứ tự, pagination và total count. Tránh suy đoán từ `List.size()` khi join nhiều to-many. Nếu query có custom `select` projection hoặc scalar result, kiểm tra riêng semantics `DISTINCT`.

### 8.5. Pagination với collection fetch join xử lý ở RAM

Khi query `Pageable` có fetch collection, provider có thể không áp giới hạn SQL như mong muốn. Query vẫn trả đúng một page ở Java, nhưng JDBC phải nạp quá nhiều row, hoặc Hibernate phát lỗi nếu được cấu hình fail-fast.

**Cách xử lý:** bật `hibernate.query.fail_on_pagination_over_collection_fetch=true` trong môi trường test; chuyển sang chiến lược page root ids trước rồi fetch child theo id. Kiểm tra count query được tạo/khai báo đúng.

### 8.6. Thay đổi SQL là do dialect/driver hoặc query planner

Sau nâng cấp, `limit/offset` có thể thành `offset ... fetch first ... rows only`, alias thay đổi hoặc DB chọn plan khác do statistics/index, không nhất thiết do annotation fetch.

**Cách xử lý:** kiểm tra dialect/driver và DB version; xem SQL và bind values, execution plan thật. Test H2 không thay thế kiểm thử PostgreSQL, MySQL, SQL Server hoặc Oracle khi ứng dụng dùng các hệ đó.

### 8.7. L1/L2 hoặc query cache che lỗi so sánh

Lần thứ hai chạy trong cùng transaction không thấy SQL vì L1 đã có entity. Hoặc L2 cache trả trạng thái, làm sai lệch so sánh cold-start.

**Cách xử lý:** cô lập transaction và `EntityManager.clear()`/mở context mới cho từng scenario; nếu dùng L2/query cache, đo riêng cache-on/cache-off và xóa cache bằng API provider khi thật sự cần. `EntityManager.clear()` **không xóa L2 hoặc Spring Cache**.

### 8.8. Quan hệ LAZY phát sinh `LazyInitializationException`

Nếu serializer truy cập association khi không còn persistence context, ứng dụng lỗi; khi OSIV bật, lỗi có thể bị che bằng các truy vấn ngoài service transaction. Thay đổi OSIV/transaction boundary cùng lần nâng cấp khiến biểu hiện đổi.

**Cách xử lý:** xác định dữ liệu cần trả và nạp/mapping DTO trong transaction service rõ ràng. Không bật EAGER mọi nơi hoặc kéo dài session vô hạn chỉ để làm serialization chạy được.

## 9. Quy trình chẩn đoán regression

Dùng thứ tự sau để tránh sửa sai nguyên nhân:

1. **Xác nhận lỗi tái hiện:** chạy cùng fixture/đường gọi trên baseline và target; kiểm tra source version, cấu hình và DB.
2. **Đối chiếu semantics:** root count/id, association, filter, page, order và null handling có còn đúng? Nếu sai, xử lý trước tối ưu hóa.
3. **Đếm SQL trên toàn use case:** repository → service → DTO/serializer; tách cold/warm cache.
4. **Phân loại diff:** nhiều secondary selects (N+1), thêm/đổi join, nhiều JDBC rows, pagination in-memory, L2/cache hoặc dialect/plan.
5. **Tìm nguồn fetch plan:** mapping, JPQL, derived query, `@EntityGraph`, Hibernate fetch annotation, configuration và transaction boundary.
6. **Sửa nhỏ nhất ở đúng tầng:** đổi fetch plan của use case, projection, batch loading, pagination hai bước, index hoặc dialect/config phù hợp.
7. **Chạy lại kiểm thử hai mặt:** kết quả business đúng và ngân sách SQL/latency không bị phá vỡ. Với dữ liệu production-like, xác minh plan/throughput.
8. **Lưu diff có chú giải:** nếu SQL đổi hợp lệ, ghi nguyên nhân; nếu là regression, bổ sung test để phát hiện ở lần nâng cấp sau.

Ví dụ ra quyết định:

| Quan sát sau nâng cấp | Khả năng cao | Hướng điều tra |
| --- | --- | --- |
| Query count tăng theo số root | N+1 association access | DTO mapper, serialization, fetch graph, batch fetching |
| Query count giảm nhưng p95 tăng | Join/row multiplication, plan tệ | `EXPLAIN ANALYZE`, số row, select list |
| Trả thiếu root không có child | `INNER JOIN` thay `LEFT JOIN` hoặc filter | SQL join predicate, `optional`, filter |
| Page nhỏ nhưng SQL đọc rất nhiều rows | Fetch collection + pagination | Warning `HHH000104`/tùy phiên bản, fail-fast property |
| Entity graph trả đúng dữ liệu nhưng SQL khác | Provider lựa chọn fetch strategy khác | Graph semantics và Hibernate SQL thực tế |
| Chỉ lỗi sau khi controller trả về | LAZY load ngoài context | OSIV/transaction và DTO mapping |
| Chỉ benchmark lần hai mới nhanh | L1/L2/query cache warm | Reset/cô lập cache, phân loại warm/cold |

## 10. Checklist trước khi chấp nhận nâng cấp

- [ ] Ghi versions đã resolve, mapping/dialect/database/schema và các tham số cấu hình.
- [ ] Có tập fixture đủ đại diện: null, đa trị, filter, pagination, dữ liệu lớn.
- [ ] Test đường đọc thực tế đến DTO/API, không chỉ repository query.
- [ ] So sánh SQL count, bind values, join shape, select list và row cardinality.
- [ ] Kiểm tra `@OneToMany`, `@ManyToOne`, `@OneToOne`, `@ManyToMany` và graph load.
- [ ] Bảo đảm không có lazy-access lỗi khi transaction đóng.
- [ ] Kiểm tra `DISTINCT`, duplicate root, count query và pagination có fetch collection.
- [ ] Tách cold/warm cache và sử dụng thống kê đúng phạm vi.
- [ ] Dùng database engine/dialect thật để đánh giá SQL plan và latency.
- [ ] Ghi các thay đổi SQL hợp lệ và regression có bằng chứng, rồi đưa test vào CI.

**Ghi nhớ:** khi nâng cấp JPA/Hibernate, “code không đổi” không có nghĩa “SQL và fetch plan không đổi”. Hãy dùng **cùng fixture + cùng transaction/use case + SQL/log/statistics + assertion về kết quả và hiệu năng** để đánh giá, thay vì chỉ nhìn HTTP 200 hoặc hình dạng SQL.

### Tài liệu chính thức để tham khảo theo phiên bản

- [Hibernate ORM 6.0 Migration Guide](https://docs.hibernate.org/orm/6.0/migration-guide/migration-guide/) — thay đổi generated SQL, fetch, DISTINCT, query và Jakarta API.
- [Hibernate ORM User Guide — Fetching](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html#fetching) — fetch plan, `join fetch`, batch/subselect và SQL behavior. Dùng bản docs đúng Hibernate version đang triển khai.
- [Spring Data JPA — JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html) — `@Query`, `@EntityGraph`, pagination và projection.
- [Spring Data JPA — EntityGraph API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/EntityGraph.html) — graph ad hoc và `FETCH`/`LOAD`.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — mapping, entity graph, fetch semantics.
