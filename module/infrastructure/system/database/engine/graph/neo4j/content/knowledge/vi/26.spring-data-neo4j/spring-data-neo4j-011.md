# Kiểm thử tích hợp và xác minh Cypher thực tế do ứng dụng thực thi

Một phương thức repository của **Spring Data Neo4j (SDN)** có thể chỉ dài một dòng Java, nhưng khi chạy nó có thể sinh ra một câu Cypher gồm nhiều `MATCH`, `WHERE`, `WITH`, `RETURN` hoặc các bước tải quan hệ. Một unit test chỉ mock repository sẽ cho biết service **gọi đúng phương thức**, nhưng không xác minh được **Cypher có chạy được trên Neo4j thật**, có trả đúng số node/relationship, có ánh xạ đúng thành Java object hay có gây tác dụng ghi ngoài mong muốn.

Bài này thuộc chương **Spring Data Neo4j** của module `DATABASE_ENGINE_GRAPH_NEO4J`. Trong hệ thống property graph Neo4j, ứng dụng cần truy vấn node, relationship, lọc, tổng hợp, tận dụng index/constraint và xử lý giao dịch. Vì vậy, kiểm thử tích hợp tốt phải kiểm tra **cả kết quả nghiệp vụ lẫn dữ liệu thật trong graph**, sau đó quan sát **Cypher thực tế do SDN/driver gửi đến Neo4j**. Nội dung cũng chỉ ra cách sử dụng log, server query log và `EXPLAIN`/`PROFILE` để điều tra những truy vấn chậm hoặc sinh nhiều hàng.

> **Phạm vi phiên bản:** Ví dụ Java chính dưới đây hướng đến **Spring Boot 3.5 / Spring Data Neo4j 7.5**, Java 17+, JUnit 5, Testcontainers và Neo4j 5.x. Spring Boot 4 / SDN 8 có thay đổi package và module kiểm thử; hãy xem mục tương thích trước khi chép mã vào dự án. Dùng đúng phiên bản phụ thuộc theo BOM của Spring Boot đang chạy.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt unit test, repository slice test và integration test xuyên qua service/API.
2. Dùng `@DataNeo4jTest` kết hợp **Neo4j Testcontainers** để chạy truy vấn thật trong CI/local.
3. Tạo fixture đồ thị có dữ liệu xác định, gọi repository và đối chiếu kết quả với Cypher độc lập.
4. Kiểm tra các truy vấn **tự sinh** từ tên method, các truy vấn khai báo bằng `@Query` và những thay đổi khi tải quan hệ.
5. Xem **câu Cypher và tham số thực tế** ở phía ứng dụng hoặc máy chủ mà không dựa vào suy đoán từ tên method.
6. Dùng đúng câu Cypher đã quan sát với `EXPLAIN`/`PROFILE` để tìm lỗi cardinality, index và sắp xếp.
7. Giữ bài kiểm thử cô lập, tránh ảnh hưởng của transaction rollback, cache, dữ liệu nền và cấu hình môi trường.

## 2. Ba cấp độ kiểm thử cần phân biệt

| Cấp độ | Thành phần dùng thật | Có chạy Cypher trên Neo4j? | Phát hiện tốt |
|---|---|---|---|
| **Unit test service** | Service, repository giả lập bằng mock | **Không** | Luật nghiệp vụ, xử lý exception, đúng lời gọi |
| **Repository slice test** | `@DataNeo4jTest`, mapping SDN, repository, Neo4j thực | **Có** khi cấu hình kết nối thật | Query derived, `@Query`, mapping, save/load, transaction |
| **Full integration test** | `@SpringBootTest`, service, controller và DB thực | **Có** | Tích hợp nhiều bean, transaction service, mapping response, quyền/cấu hình |

`@DataNeo4jTest` là **test slice**: Spring chỉ khởi tạo hạ tầng Neo4j và những bean liên quan theo quy tắc của slice; không mặc nhiên nạp toàn bộ `@Service`, `@Controller` hay cấu hình ứng dụng. Nếu đang cần xác minh một endpoint REST hoặc quy tắc transaction của service thực, hãy dùng `@SpringBootTest` hoặc chủ động import đúng thành phần cần kiểm tra.

**Điểm quan trọng:** `@DataNeo4jTest` **không tự khởi tạo một Neo4j embedded database**. Cần cung cấp một Neo4j thực, chẳng hạn Testcontainers hay Neo4j Test Harness. Chỉ thêm annotation và mock driver thì vẫn chưa kiểm thử việc thực thi Cypher.

~~~mermaid
flowchart TD
    U["Unit test + mock repository"] --> R["Kiểm tra service logic"]
    S["@DataNeo4jTest + Neo4j container"] --> C["Repository / SDN mapping"]
    C --> D["Neo4j Bolt / Cypher thực"]
    F["@SpringBootTest + Neo4j container"] --> A["API / Service / Transaction"]
    A --> C
    D --> V["Xác minh node, relationship, kết quả"]
    D --> L["Quan sát query thực thi, EXPLAIN / PROFILE"]
~~~

## 3. Chuẩn bị project kiểm thử có Neo4j thật

### 3.1. Phụ thuộc Gradle

Ví dụ cho **Spring Boot 3.5**, dùng `spring-boot-starter-data-neo4j` cho ứng dụng và thư viện kiểm thử được BOM quản lý:

~~~groovy
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
~~~

Các lớp ứng dụng có thể đã có starter Neo4j và BOM từ trước; khi đó chỉ bổ sung phần test còn thiếu. **Không trộn tùy tiện phiên bản riêng** của Spring Data Neo4j, Neo4j Java Driver và Spring Boot BOM. Trong CI, Testcontainers cần môi trường chạy container hoạt động (Docker hoặc runtime tương thích).

### 3.2. Chọn phiên bản test gần production

Giả sử production dùng Neo4j 5.26, test nên dùng cùng dòng Neo4j và cùng cấu hình ảnh hưởng Cypher/schema thay vì chọn ngẫu nhiên một phiên bản mới:

~~~java
@Container
@ServiceConnection
static Neo4jContainer<?> neo4j = new Neo4jContainer<>("neo4j:5.26");
~~~

`@ServiceConnection` cung cấp thông tin kết nối của container cho Spring Boot, gồm URI và thông tin xác thực phù hợp. Nó ưu tiên cấu hình connection details từ container thay cho các giá trị kết nối tĩnh của ứng dụng. Thử nghiệm với phiên bản khác là có ích, nhưng đó phải là một phép thử tương thích **có chủ đích**.

Với JUnit `@Testcontainers` và container là trường `static @Container`, vòng đời container gắn với lớp test. Nếu nhiều lớp test dùng lại Spring ApplicationContext đã được cache, container có thể dừng trong khi context còn được dùng. Khi xây **test suite lớn**, cân nhắc khai báo container dưới dạng **Spring test bean** để vòng đời phù hợp context, hoặc thiết kế một cách chia sẻ lifecycle có kiểm soát. Ví dụ tối giản ở phần sau chỉ mô tả **một lớp test**.

## 4. Mô hình dữ liệu Java để kiểm thử

Giả sử ứng dụng quản lý sách theo `isbn`, `title` và `price`. Chúng ta muốn gọi repository để tìm sách có giá từ một ngưỡng trở lên và sắp theo giá tăng.

**Entity:**

~~~java
package example.catalog;

import org.springframework.data.annotation.Id;
import org.springframework.data.neo4j.core.schema.Node;

@Node("CatalogBook")
public class CatalogBook {
    @Id
    private String isbn;
    private String title;
    private long price;

    protected CatalogBook() {
    }

    public CatalogBook(String isbn, String title, long price) {
        this.isbn = isbn;
        this.title = title;
        this.price = price;
    }

    public String getIsbn() { return isbn; }
    public String getTitle() { return title; }
    public long getPrice() { return price; }
}
~~~

`@Node` ánh xạ Java class sang node label `CatalogBook`. `@Id` biểu diễn khóa nhận diện của entity; không dùng `@GeneratedValue` vì trong ví dụ `isbn` được cấp từ hệ thống nghiệp vụ. Trên hệ thống thật, cần thêm **uniqueness constraint** trong Neo4j cho `isbn`; annotation của entity **không thay thế** constraint ở database.

**Repository:**

~~~java
package example.catalog;

import java.util.List;
import org.springframework.data.neo4j.repository.Neo4jRepository;

public interface CatalogBookRepository
        extends Neo4jRepository<CatalogBook, String> {

    List<CatalogBook> findByPriceGreaterThanEqualOrderByPriceAsc(long minPrice);
}
~~~

Method `findByPriceGreaterThanEqualOrderByPriceAsc` được SDN **phân tích tên** để tạo truy vấn. Không thể khẳng định chắc câu Cypher cuối cùng gồm những mệnh đề và alias nào chỉ từ chữ ký Java; SDN còn cần ánh xạ entity, version thư viện và tham số. Bài kiểm thử sẽ xác nhận **ngữ nghĩa** trước, sau đó mới xem chính xác Cypher được phát đi.

## 5. Bài kiểm thử tích hợp bằng `@DataNeo4jTest` + Testcontainers

Đây là một lớp kiểm thử minh họa **hoàn chỉnh theo phạm vi Spring Boot 3.5**. Nó tạo dữ liệu bằng `Neo4jClient` trong cùng ngữ cảnh transaction của test, gọi repository, rồi xác minh dữ liệu nguồn và kết quả:

~~~java
package example.catalog;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.data.neo4j.core.Neo4jClient;
import org.testcontainers.containers.Neo4jContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@DataNeo4jTest
class CatalogBookRepositoryIT {
    @Container
    @ServiceConnection
    static Neo4jContainer<?> neo4j =
            new Neo4jContainer<>("neo4j:5.26");

    @Autowired
    CatalogBookRepository repository;

    @Autowired
    Neo4jClient client;

    @BeforeEach
    void seedGraph() {
        client.query("""
                UNWIND $books AS row
                CREATE (:CatalogBook {
                    isbn: row.isbn,
                    title: row.title,
                    price: row.price
                })
                """)
                .bindAll(Map.of("books", List.of(
                        Map.of("isbn", "B01", "title", "Graph Basics",
                               "price", 120_000L),
                        Map.of("isbn", "B02", "title", "Intro Cypher",
                               "price", 80_000L),
                        Map.of("isbn", "B03", "title", "Neo4j Patterns",
                               "price", 150_000L))))
                .run();
    }

    @Test
    void derivedQueryFiltersAndOrdersByPrice() {
        var actual =
                repository.findByPriceGreaterThanEqualOrderByPriceAsc(
                        100_000L);

        assertThat(actual)
                .extracting(CatalogBook::getIsbn)
                .containsExactly("B01", "B03");

        assertThat(actual)
                .extracting(CatalogBook::getPrice)
                .containsExactly(120_000L, 150_000L);

        var count = client.query("""
                MATCH (b:CatalogBook)
                RETURN count(b) AS total
                """)
                .fetchAs(Long.class)
                .one();
        assertThat(count).contains(3L);
    }
}
~~~

**Những gì bài test thực sự xác minh:**

1. Spring tạo được repository và kết nối Neo4j bằng thông tin từ container.
2. Bộ dữ liệu tạo ra **ba node** có giá/khóa đã biết.
3. SDN biến method derived thành một truy vấn chạy được trên Neo4j thực.
4. Kết quả lọc bỏ `B02` (80.000), trả `B01` rồi `B03` theo giá tăng.
5. Ánh xạ property từ node thật về `CatalogBook` trả giá trị đúng.

**Những gì bài test chưa chứng minh:** nội dung chính xác của câu Cypher được sinh, số lần truy cập DB, index có được dùng, tác dụng khi nhiều relationship cùng khớp, độ trễ ở production, hay tính đúng đắn của toàn service/API.

### Vì sao tạo fixture qua `Neo4jClient`?

`Neo4jClient` được Spring Data Neo4j cung cấp để thực thi Cypher trực tiếp trong cùng hệ thống giao dịch Spring. Tạo fixture qua Cypher giúp biết rõ chính xác graph đầu vào, sau đó kiểm tra repository bằng một đường truy vấn **khác** với chính repository đó. Nếu chỉ dùng `repository.save(...)` để tạo rồi `repository.find...` để kiểm tra, hai thao tác có thể cùng mắc một lỗi mapping mà bài test không phát hiện.

Ở những bài test khác, vẫn nên kiểm tra `repository.save` và `Neo4jTemplate`, nhưng hãy xác định **đối tượng được kiểm thử** (save, load hay mapping) và có một cách quan sát dữ liệu nền độc lập.

## 6. Kiểm thử câu `@Query` do lập trình viên viết

Ngoài method derived, repository có thể khai báo Cypher thủ công:

~~~java
import java.util.List;
import org.springframework.data.neo4j.repository.query.Query;
import org.springframework.data.repository.query.Param;

public interface CatalogBookRepository
        extends Neo4jRepository<CatalogBook, String> {

    List<CatalogBook> findByPriceGreaterThanEqualOrderByPriceAsc(long minPrice);

    @Query("""
        MATCH (b:CatalogBook)
        WHERE b.price >= $minPrice
        RETURN b
        ORDER BY b.price ASC, b.isbn ASC
        """)
    List<CatalogBook> findPremiumBooks(@Param("minPrice") long minPrice);
}
~~~

Đây là **phiên bản mở rộng** của interface ở mục 4: thêm method `findPremiumBooks` vào cùng repository, không tạo một interface trùng tên khác trong dự án.

Test thêm:

~~~java
@Test
void customQueryUsesNamedParameter() {
    var actual = repository.findPremiumBooks(100_000L);

    assertThat(actual)
            .extracting(CatalogBook::getIsbn)
            .containsExactly("B01", "B03");
}
~~~

Test này kiểm tra rằng tên tham số `minPrice` được binding và câu query thực thi đúng trên Neo4j. Tuy nhiên, **đúng kết quả với ba node** không bảo đảm truy vấn đúng với dữ liệu lớn: cần thêm case trùng giá, thuộc tính null, dữ liệu không hợp lệ và quan hệ một-nhiều tùy nghiệp vụ.

## 7. Kiểm thử mapping quan hệ, số lượng hàng và dữ liệu bất thường

Với graph, một node có thể nối nhiều relationship. Một truy vấn `MATCH` mở hai nhánh độc lập có thể **nhân số hàng**. SDN còn cần biến tập kết quả Cypher thành object graph; khi truy vấn `@Query` trả thiếu biến/node/relationship cần thiết, object có thể thiếu quan hệ hoặc quan hệ bị tải khác kỳ vọng.

Giả sử mô hình:

~~~cypher
(:Customer {customerId: 'C01'})
  -[:PLACED]->(:Order {orderId: 'O01', amount: 120000})
  -[:PLACED]->(:Order {orderId: 'O02', amount: 180000})

(:Customer {customerId: 'C01'})
  -[:WROTE]->(:Review {reviewId: 'R01'})
  -[:WROTE]->(:Review {reviewId: 'R02'})
  -[:WROTE]->(:Review {reviewId: 'R03'})
~~~

Truy vấn sau có thể sinh **6 hàng** cho khách hàng có 2 đơn và 3 đánh giá:

~~~cypher
MATCH (c:Customer {customerId: 'C01'})
MATCH (c)-[:PLACED]->(o:Order)
MATCH (c)-[:WROTE]->(r:Review)
RETURN count(o) AS orderCount,
       count(r) AS reviewCount,
       sum(o.amount) AS totalAmount;
// Sai theo nghiệp vụ đếm node duy nhất:
// orderCount = 6, reviewCount = 6, totalAmount = 900000.
~~~

Nếu phương thức Java trả về DTO báo cáo đơn hàng, **integration test phải đối chiếu cả giá trị tổng hợp**, không chỉ `assertThat(result).isNotNull()`. Với số liệu trên, kết quả đúng theo mỗi đơn một lần là `2` đơn hàng, `3` đánh giá và `300000` tổng tiền. Hãy sửa Cypher bằng tổng hợp riêng từng nhánh hoặc cách tương đương trước khi coi test là đạt.

**Các ca cần đưa vào fixture:**

| Ca dữ liệu | Sai sót thường phát hiện |
|---|---|
| Không có relationship | `MATCH` loại mất node thay vì dùng `OPTIONAL MATCH` thích hợp |
| Một node có nhiều relationship cùng type | Kết quả bị nhân hàng, mapper nhận nhiều bản ghi |
| Hai nhánh một-nhiều | Sai `count`/`sum` do tích kết quả |
| Nhiều node có giá/score bằng nhau | `ORDER BY` thiếu khóa phụ, phân trang không ổn định |
| Thuộc tính null/không có | Mapping primitive Java, filter loại giá trị không mong muốn |
| Khóa định danh trùng | Cần uniqueness constraint và xử lý lỗi server |
| Relationship có chiều khác kỳ vọng | `@Relationship`, `MATCH` hoặc projection sai |
| Node đã lưu nhưng object chỉ tải một phần graph | Dễ ghi đè/xóa relation khi lưu lại entity tải không đầy đủ |

Riêng với `@Query` ánh xạ entity chứa relationships, hãy đọc tài liệu SDN về **mapping custom query**: kết quả có thể cần trả **node cùng các relationship/nodes liên quan** để mapper khôi phục graph. Chỉ `RETURN b` không đảm bảo mọi mối liên kết của `b` đã được nạp; không sử dụng một entity được tải một phần để ghi đè đồ thị khi chưa hiểu cơ chế lưu của SDN.

## 8. Xem **Cypher thực tế** mà SDN thực thi

Đây là bước cốt lõi của bài: **đừng đoán câu truy vấn từ tên Java method**. Tùy cách truy cập dữ liệu, SDN có thể tạo query khác biệt về alias, điều kiện lọc, `WITH`, `RETURN`, truy vấn tải graph và tham số.

### 8.1. Bật log phía ứng dụng trong profile test

Ví dụ cấu hình **`src/test/resources/application-test.yml`**:

~~~yaml
logging:
  level:
    org.springframework.data.neo4j: DEBUG
    org.springframework.data.neo4j.cypher: DEBUG
    org.neo4j.driver: INFO
~~~

Kích hoạt profile test bằng `@ActiveProfiles("test")` hoặc cấu hình chạy test tương ứng. Trên một số phiên bản, các mức log và nội dung được in khác nhau; hãy xác minh thực tế. Theo tài liệu SDN, logger `org.springframework.data.neo4j.cypher` có khả năng ghi các câu được SDN gọi và các notification từ server. **Đây là điểm quan sát phía ứng dụng**, không phải một bảo đảm rằng mọi query Bolt của các thư viện khác hoặc mọi tham số đều xuất hiện đầy đủ.

Khi test gọi:

~~~java
repository.findByPriceGreaterThanEqualOrderByPriceAsc(100_000L);
~~~

hãy tìm bản ghi log liên quan đến `CatalogBook` hoặc method đang chạy. Câu query có thể sử dụng alias khác tên biến `b`, dùng tham số thay vì ghi thẳng `100000`, và có mệnh đề bổ sung. **Không lấy query ví dụ viết tay `MATCH (b:CatalogBook) ...` làm bằng chứng đó là câu query SDN đã thực sự gửi.**

### 8.2. Kiểm tra query log **phía Neo4j**

Khi cần bằng chứng **server đã nhận và thực thi câu nào**, query log của Neo4j là điểm đối chiếu quan trọng. Trên **Neo4j Enterprise** hoặc môi trường có hỗ trợ query log, có thể cấu hình giới hạn trong **database test riêng**:

~~~properties
# neo4j.conf -- ví dụ dành cho môi trường quan sát test
db.logs.query.enabled=INFO
db.logs.query.threshold=0s
db.logs.query.parameter_logging_enabled=false
~~~

Giá trị `INFO` cùng `0s` nhằm ghi các truy vấn kết thúc mà không đặt ngưỡng thời gian tối thiểu. `parameter_logging_enabled=false` tránh ghi thẳng giá trị tham số nhạy cảm vào log. Trên các bản Neo4j mới, `VERBOSE` ghi cả điểm bắt đầu/kết thúc; hãy dùng đúng tài liệu phiên bản và không giữ mức log quá chi tiết trong production nếu không cần.

Query log chứa dữ liệu do **Neo4j nhận**, kể cả khi một lời gọi repository dẫn đến nhiều query. Khi đối chiếu, quan sát **database**, **username**, **timestamp**, **query text**, **metadata transaction**, **kết quả/thời gian** và **tham số khi chính sách cho phép**.

**Lưu ý hai giới hạn:**

1. Query log có thể cần bản **Enterprise**, quyền truy cập server/log và cấu hình của môi trường. Nếu đang dùng Community hoặc dịch vụ không cung cấp query log, hãy dùng logger phía ứng dụng hoặc cơ chế instrumentation ở tầng driver do dự án cho phép.
2. Việc log tham số, literal hay lỗi có thể tiết lộ dữ liệu khách hàng, token hoặc mật khẩu. Chỉ bật chi tiết ở môi trường thử nghiệm với dữ liệu giả; không sao chép nguyên log nhạy cảm vào issue/CI artifact.

### 8.3. Tương quan một request với log

Nếu chạy nhiều test song song, chỉ tìm chuỗi `MATCH` trong log có thể không biết query thuộc test nào. Có thể gắn metadata transaction ở tầng driver/service cho những giao dịch chủ động quản lý, ví dụ `requestId` hoặc `operation`, rồi dò chúng trong query log:

~~~java
TransactionConfig txConfig = TransactionConfig.builder()
        .withMetadata(Map.of(
                "operation", "catalog-filter-test",
                "requestId", requestId))
        .build();
~~~

Đoạn mã trên chỉ minh họa API **Neo4j Java Driver** cho transaction được cấu hình bằng `txConfig`; nó không tự gắn metadata vào mọi transaction SDN. Nếu muốn correlation xuyên qua repository SDN, cần tích hợp đúng transaction manager/driver instrumentation hoặc điểm chèn metadata có hỗ trợ ở phiên bản đang dùng.

## 9. Từ câu Cypher đã quan sát đến `EXPLAIN` và `PROFILE`

Sau khi lưu **query thực tế** và **các giá trị tham số tương ứng**, hãy chạy lại trên cùng database snapshot để kiểm tra plan. Không nên chỉ phân tích câu Cypher bạn **nghĩ** SDN sẽ sinh.

Ví dụ, nếu câu query **quan sát được** có điều kiện sau:

~~~cypher
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

thì có thể chạy:

~~~cypher
EXPLAIN
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

Trong Neo4j Browser, khai báo tham số trước:

~~~cypher
:param minPrice => 100000
~~~

`EXPLAIN` chỉ lập kế hoạch, **không thực thi** truy vấn. `PROFILE` thực thi và cung cấp thêm số liệu hàng/lượt truy cập:

~~~cypher
PROFILE
MATCH (b:CatalogBook)
WHERE b.price >= $minPrice
RETURN b
ORDER BY b.price ASC;
~~~

Đây là **một câu query minh họa**; nó chỉ đại diện cho query thực nếu log ở bước trước xác nhận đúng mẫu này. Khi log cho thấy query chứa `WITH`, `DISTINCT`, `LIMIT`, pattern dài hoặc nhiều lần `MATCH`, phải dùng đúng các thành phần đó để phân tích.

### Nên đọc gì trong kế hoạch?

| Chỉ số/toán tử | Câu hỏi thực tế |
|---|---|
| `NodeByLabelScan`, `NodeIndexSeek`, `NodeIndexScan` | Neo4j đang quét label hay dùng property index? |
| `Filter` | Bao nhiêu hàng bị loại sau bước đọc node? |
| `Expand(All)`/`Expand(Into)` | Quan hệ nào làm tăng số hàng trung gian? |
| `Sort`, `Top` | `ORDER BY`/`LIMIT` có cần sắp nhiều hàng không? |
| `Rows` | Số hàng thực chạy qua từng bước có tăng đột biến không? |
| `DB Hits` | Bước nào truy cập dữ liệu nhiều nhất theo thống kê execution plan? |
| `Estimated Rows` so với `Rows` thực | Optimizer có ước lượng sai do thống kê hoặc mô hình dữ liệu không? |

`DB Hits` **không bằng** số lần đọc vật lý từ đĩa; thời gian cũng chịu ảnh hưởng cache, dữ liệu, tải hệ thống và mạng. Nếu cần xác minh thay đổi index hoặc viết lại query, hãy giữ nguyên database snapshot/tham số và lặp nhiều lần trên dữ liệu đại diện.

**Không chạy `PROFILE` bừa bãi với câu Cypher ghi dữ liệu**: `PROFILE` **có thực thi**, nên `CREATE`/`MERGE`/`DELETE` có thể sửa dữ liệu thật. Hãy phân tích các query ghi ở database thử nghiệm, trong transaction được kiểm soát hoặc trên bản sao trước.

## 10. Ví dụ kiểm thử kết quả **sau khi save** qua đường đọc độc lập

Khi test `repository.save(entity)`, chỉ assert object trả về có ID vẫn chưa đủ. Cần xem dữ liệu **thực đã lưu trong graph**:

~~~java
@Test
void savePersistsExpectedProperties() {
    repository.save(new CatalogBook(
            "B04", "Graph Transactions", 220_000L));

    var price = client.query("""
            MATCH (b:CatalogBook {isbn: $isbn})
            RETURN b.price AS price
            """)
            .bind("B04").to("isbn")
            .fetchAs(Long.class)
            .one();

    assertThat(price).contains(220_000L);
}
~~~

Trong ví dụ này, phương thức chạy **trong cùng transaction của test**, nên query `Neo4jClient` có thể thấy thay đổi vừa thực hiện trước khi transaction được rollback ở cuối test. Nếu dùng **một Java Driver/session riêng ngoài transaction đó** để kiểm tra, query bên ngoài có thể **chưa thấy dữ liệu chưa commit**. Đây là vấn đề isolation, không phải bằng chứng SDN đã không lưu.

Test này minh họa một phương thức bổ sung vào lớp test ở mục 5. `@BeforeEach` của lớp vẫn tạo ba node `B01`–`B03`, còn `B04` là node được tạo trong test. Nếu database thực hành đã chứa `B04` từ test khác hoặc đang chạy nhiều suite song song, cần đổi khóa fixture/cô lập DB để bảo đảm kết quả xác định.

## 11. Transaction và rollback trong test dễ gây hiểu nhầm

Với `@DataNeo4jTest` **imperative**, Spring Boot mặc định chạy test trong transaction và **rollback cuối mỗi test**. Điều này hữu ích để cô lập fixture, nhưng cần hiểu những trường hợp sau:

| Trường hợp | Điều cần nhớ |
|---|---|
| Chạy `repository.save` rồi kiểm tra qua `Neo4jClient` cùng Spring transaction | Có thể thấy thay đổi chưa commit |
| Mở connection/driver riêng trong test | Có thể không thấy dữ liệu chưa commit của test transaction |
| Gọi service tạo **transaction độc lập** như `REQUIRES_NEW` | Có thể commit ngoài transaction test và **không bị rollback cùng test** |
| Thử `@TransactionalEventListener` hoặc callback sau commit | Test mặc định rollback có thể không kích hoạt luồng cần commit |
| Dùng reactive Neo4j repository | `@Transactional` mặc định của test slice **không thay** reactive transaction cho publisher |
| Dùng `@SpringBootTest` | Không tự suy rằng toàn request qua HTTP nằm trong transaction test |

Khi muốn kiểm tra hậu quả **sau commit**, phải thiết kế ranh giới riêng. Với kiểm thử Spring imperative, có thể dùng `TestTransaction.flagForCommit()` và `TestTransaction.end()` trong test transaction phù hợp, hoặc chạy luồng nghiệp vụ ở môi trường tách biệt và dọn fixture sau. Những bài test cần bảo vệ dữ liệu đang phục vụ nghiệp vụ không nên tự ý đổi cấu hình rollback mà thiếu cơ chế cleanup.

**Với reactive repository**, dùng `TransactionalOperator` hoặc cấu hình transaction reactive đúng cách; không đặt niềm tin vào annotation `@Transactional` kiểu imperative của lớp test để làm rollback một luồng `Mono`/`Flux`.

## 12. Đối chiếu query và kết quả theo từng mức độ tin cậy

Khi khẳng định “ứng dụng thực thi Cypher X và trả kết quả Y”, cần phân biệt các mức bằng chứng:

| Bằng chứng | Khẳng định hỗ trợ | Giới hạn |
|---|---|---|
| Method repository trong mã nguồn | Dự định truy vấn của lập trình viên | Không phản ánh query phát đi sau mapping |
| Unit test với mock | Service gọi repository đúng | Không chứng minh Neo4j thực thi gì |
| Integration test + assert object | SDN trả kết quả đúng cho fixture | Chưa cho thấy câu Cypher chính xác |
| Log `org.springframework.data.neo4j.cypher` | Câu SDN gọi và notification trong cấu hình log đó | Có thể khác các thao tác dùng trực tiếp driver/plugin |
| Server query log | Query Neo4j **thực sự nhận/thực thi** trong phạm vi log thu thập | Quyền/edition/cấu hình và ngưỡng log có thể giới hạn |
| `EXPLAIN` trên query đã bắt được | Kế hoạch dự kiến cho Cypher/tham số | Không có thống kê runtime |
| `PROFILE` trên query đã bắt được | Chi phí và số hàng thực thi trong lần thử | Có tác dụng ghi nếu query ghi; số đo chịu ảnh hưởng môi trường |

Để chắc chắn nhất, **kết hợp** ba lớp: (1) integration test khẳng định kết quả nghiệp vụ, (2) log xác nhận query được gửi, (3) plan cho biết nó được xử lý thế nào. Một lớp đơn lẻ không thay thế hai lớp còn lại.

## 13. Quy trình điều tra một repository chậm hoặc sai dữ liệu

1. **Tái hiện bằng một fixture nhỏ** có graph rõ ràng: số node, nhánh relationship, số lượng và thuộc tính.
2. **Viết assertion về kết quả đúng**: số hàng, giá trị tổng, thứ tự, ánh xạ quan hệ; thêm case 0/1/nhiều relationship.
3. **Bật application Cypher log trong test** và chạy **chính lời gọi repository/service** đang gặp vấn đề.
4. **Chụp query thực tế** cùng tham số, database và phiên bản SDN/Neo4j. Nếu query phát nhiều lần, cần phân biệt từng query.
5. **Kiểm tra server query log** nếu môi trường hỗ trợ để xác nhận query đã được gửi và thực thi.
6. **Dùng `EXPLAIN`/`PROFILE`** trên query đã thu thập, với đúng kiểu tham số; chú ý index, `Rows`, `DB Hits` và `Sort`.
7. **Sửa một yếu tố có chủ đích**: query, entity mapping, index/constraint hoặc cách tải graph; chạy lại toàn bộ assertion.
8. **So sánh trước/sau cùng dữ liệu** để tránh tối ưu sai kết quả hoặc chỉ hưởng lợi từ page cache.

### Ví dụ: phát hiện truy vấn không dùng index như dự định

Giả sử repository lọc theo `CatalogBook.price` và trả ít node. Nếu `PROFILE` cho thấy phần lớn query quét nhãn, có thể đánh giá một **range index** trong database thử nghiệm:

~~~cypher
CREATE RANGE INDEX catalog_book_price_idx IF NOT EXISTS
FOR (b:CatalogBook) ON (b.price);
~~~

Sau khi index `ONLINE`, chạy lại **đúng query đã ghi log** và so kế hoạch. Một test vài node có thể quá nhỏ để optimizer chọn index, nên không viết assertion “bắt buộc có `NodeIndexSeek`” như điều kiện mọi môi trường đều phải thỏa. Với bài test schema, hãy kiểm tra **sự tồn tại và trạng thái index** riêng; với bài test hiệu năng, đo trên dữ liệu đại diện.

## 14. Kiểm tra schema và dữ liệu thật thay vì chỉ tin annotation

SDN mapping nói cho ứng dụng hiểu cách chuyển node sang Java object; các quy tắc toàn vẹn như **uniqueness constraint** phải tồn tại thật trong Neo4j. Một số project sử dụng migration tool hoặc script cài schema trước khi chạy ứng dụng.

Kiểm tra:

~~~cypher
SHOW CONSTRAINTS
YIELD name, type, labelsOrTypes, properties
RETURN name, type, labelsOrTypes, properties
ORDER BY name;
~~~

Với miền `CatalogBook`, nếu `isbn` phải duy nhất, schema mong đợi có thể là:

~~~cypher
CREATE CONSTRAINT catalog_book_isbn_unique IF NOT EXISTS
FOR (b:CatalogBook)
REQUIRE b.isbn IS UNIQUE;
~~~

Không chạy ngẫu nhiên DDL schema **bên trong cùng transaction đang thao tác dữ liệu** của test rồi coi rollback test sẽ dọn sạch constraint. Hãy nạp schema trong bước migration/setup của database test, trước khi thực hiện fixture và các assertion nghiệp vụ. Nếu schema khác production, một số bài kiểm thử constraint hoặc hiệu năng sẽ không đại diện.

## 15. Dữ liệu kiểm thử và cấu hình phù hợp CI

Một test tích hợp đáng tin cần **chạy lặp lại cùng kết quả**:

- Dùng **khóa định danh rõ ràng** như `isbn`, `customerId`, `orderId`, không phụ thuộc `elementId()` cố định qua nhiều lượt chạy.
- Dùng giá trị test xác định, không lấy ngẫu nhiên hoặc `datetime()` hiện tại để assert thứ tự nếu không kiểm soát.
- Cô lập database hoặc dùng namespace/khóa fixture riêng cho từng test chạy song song.
- Xác định lifecycle container; tránh dùng chung container đã dừng với Spring ApplicationContext cache.
- Tách bài test transaction/commit ra khỏi bài test rollback mặc định.
- Đảm bảo Neo4j đã sẵn sàng và schema đã nạp trước khi gửi truy vấn; Testcontainers giúp kiểm soát startup.
- Chạy cùng version Neo4j/SDN cần hỗ trợ; thêm một phép thử compatibility riêng khi nâng cấp.
- Không so sánh độ trễ tuyệt đối trong CI như `< 10ms`, vì môi trường container/cache không ổn định. Đánh giá query plan và workload lớn trên môi trường benchmark riêng.

### Những lỗi môi trường thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng kiểm tra |
|---|---|---|
| `@DataNeo4jTest` không kết nối DB | Chưa cấu hình connection details/Neo4j chưa chạy | `@ServiceConnection`, container, URI, credential |
| Test xanh khi chạy một mình, đỏ khi chạy cả suite | Dữ liệu/chia sẻ container/transaction chồng lấn | Fixture isolation, context cache, parallel tests |
| Query thực thi nhưng giá trị Java sai | Mapping property, kiểu dữ liệu, converter hoặc query trả thiếu node/relationship | So Cypher trực tiếp với object mapping |
| Một query tạo nhiều hàng hơn số node | Mở rộng relationship và phép tổng hợp | Quan sát `Rows`, loại trùng/nhóm đúng |
| Log không thấy query SDN | Logger/profile chưa bật, mức log chưa phù hợp | Kiểm tra `application-test.yml`, tên logger, phiên bản |
| Query log server không có truy vấn | Edition/threshold/permission | Kiểm tra query logging và truy vấn thực thi trong server |
| Test tìm được object nhưng đọc trực tiếp không thấy data | Hai transaction/session có mức nhìn khác nhau | Cùng Spring transaction, commit/rollback, cách tạo kết nối |
| Tự tin index được dùng vì đã tạo | Planner có thể chọn kế hoạch khác | `SHOW INDEXES` + `EXPLAIN`/`PROFILE` |

## 16. Chú ý tương thích Spring Boot 4 và SDN 8

Ví dụ chính dùng **Spring Boot 3.5** vì package và module phổ biến:

~~~java
import org.springframework.boot.test.autoconfigure.data.neo4j.DataNeo4jTest;
import org.testcontainers.containers.Neo4jContainer;
~~~

Ở **Spring Boot 4**, slice test Neo4j đã được chuyển vào module chuyên biệt `spring-boot-data-neo4j-test` và annotation được import từ:

~~~java
import org.springframework.boot.data.neo4j.test.autoconfigure.DataNeo4jTest;
~~~

Khi dùng **Testcontainers 2.x**, Neo4j container cũng chuyển sang package module chuyên biệt:

~~~java
import org.testcontainers.neo4j.Neo4jContainer;
~~~

Không kết hợp ví dụ dependency của Boot 3.5 với package Boot 4 hoặc thư viện Testcontainers phiên bản khác mà không xem lại BOM. Dùng tài liệu đúng phiên bản Spring Boot, SDN, Neo4j và Testcontainers của dự án; cách viết Java entity/repository có thể giữ ý tưởng tương tự nhưng phần test infrastructure phải tương thích.

## 17. Bài tập thực hành

### Bài 1 — Chỉ unit test có đủ chưa?

Một developer mock `CatalogBookRepository` để trả hai sách có giá trên 100.000, rồi khẳng định method `findByPriceGreaterThanEqualOrderByPriceAsc` đã đúng. Kết luận có hợp lệ không?

<details>
<summary>Đáp án gợi ý</summary>

Chưa đủ. Unit test chỉ xác minh phần service xử lý kết quả mock. Cần `@DataNeo4jTest` cùng Neo4j thực, seed ít nhất ba sách có giá cao/thấp ngưỡng, gọi method và assert kết quả. Sau đó quan sát query do SDN thực thi bằng log.

</details>

### Bài 2 — Kiểm thử tổng hợp với nhiều relationship

Khách hàng `C01` có hai đơn (120.000 và 180.000) và ba đánh giá. Truy vấn mở cả hai nhánh `MATCH` rồi tính `count(o)` và `sum(o.amount)`. Hãy dự đoán kết quả và viết những assertion cần có.

<details>
<summary>Đáp án gợi ý</summary>

Có `2 × 3 = 6` hàng trung gian. `count(o) = 6` và `sum(o.amount) = 900000` là sai nếu nghiệp vụ muốn tính mỗi đơn một lần. Test cần assert `orderCount = 2`, `reviewCount = 3` và `totalAmount = 300000`, qua đó buộc query được sửa đúng.

</details>

### Bài 3 — Xác minh câu query thật

Repository tên `findByNameContainingIgnoreCase`. Một đồng nghiệp tự viết `WHERE toLower(n.name) CONTAINS toLower($keyword)` rồi dùng `PROFILE` để khẳng định đây là plan ứng dụng đang chạy. Thiếu bước gì?

<details>
<summary>Đáp án gợi ý</summary>

Phải chạy **method repository thật** dưới logger phù hợp và lấy câu Cypher cùng tham số do SDN thực sự gửi; nếu có thể, đối chiếu server query log. Chỉ khi đó mới dùng `EXPLAIN`/`PROFILE` trên câu đã quan sát. Truy vấn do đồng nghiệp tự suy đoán có thể khác câu thực thi.

</details>

### Bài 4 — Tại sao test đọc dữ liệu thấy null?

Một test `@DataNeo4jTest` gọi `repository.save(...)`, sau đó mở một Java Driver/session hoàn toàn mới để tìm node và không thấy gì. Điều đó chứng minh `save` lỗi chưa?

<details>
<summary>Đáp án gợi ý</summary>

Chưa. `@DataNeo4jTest` imperative thường chạy trong transaction bị rollback cuối test; session mới bên ngoài có thể không thấy dữ liệu chưa commit. Cần đọc qua `Neo4jClient` cùng transaction để kiểm tra hoặc thiết kế test commit có chủ đích rồi xác minh từ session độc lập.

</details>

### Bài 5 — Chọn phương pháp quan sát

Bạn có ba mục tiêu: (a) kiểm tra bộ lọc của repository đúng, (b) biết Neo4j server đã nhận query gì, (c) biết bước nào sinh nhiều `DB Hits`. Nên dùng công cụ nào cho từng mục tiêu?

<details>
<summary>Đáp án gợi ý</summary>

(a) Integration test với dữ liệu xác định và assertion kết quả; (b) query log server nếu môi trường hỗ trợ, cùng application Cypher logging; (c) `PROFILE` trên **query thực** với cùng tham số và dữ liệu. Ba bước bổ sung cho nhau.

</details>

## 18. Tài liệu tham khảo theo phiên bản

- [Spring Data Neo4j — Testing with Spring Boot và @DataNeo4jTest](https://docs.spring.io/spring-data/neo4j/reference/testing/testing-with-spring-boot.html)
- [Spring Data Neo4j — Logging](https://docs.spring.io/spring-data/neo4j/reference/appendix/logging.html)
- [Spring Data Neo4j — Defining Query Methods](https://docs.spring.io/spring-data/neo4j/reference/repositories/query-methods-details.html)
- [Spring Boot 3.5 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Testcontainers và @ServiceConnection](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html)
- [Spring Boot 4 — Auto-configured Data Neo4j Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Neo4j Operations Manual — Query Logging](https://neo4j.com/docs/operations-manual/current/monitoring/logging/)
- [Neo4j Cypher Manual — Query Tuning](https://neo4j.com/docs/cypher-manual/current/planning-and-tuning/)

Đường dẫn `current` có thể trỏ sang bản mới khi Spring hoặc Neo4j phát hành cập nhật. Trong hệ thống thật, hãy chọn tài liệu đúng phiên bản và kiểm tra thủ tục/log thực tế thay vì giả định mọi bản phát hành có cùng hành vi.

## 19. Ghi nhớ

- **Test repository thực với Neo4j thực** để xác minh Cypher và mapping; mock repository không kiểm tra được hai phần này.
- **`@DataNeo4jTest` là test slice**, thường rollback cuối test ở chế độ imperative và cần tự cung cấp database/Testcontainers.
- **Fixture phải có dữ liệu độc lập và có thể đối chiếu**: nhiều/không có relationship, giá trị null, khóa trùng, trường hợp đồng giá và kết quả tổng hợp.
- **Cypher thực tế là điều phải quan sát**, qua application log và khi có thể qua server query log; không suy từ tên method hay câu query viết lại bằng tay.
- **`EXPLAIN`/`PROFILE` chỉ có ý nghĩa khi chạy trên câu query và tham số đúng**, cùng dữ liệu đại diện; `PROFILE` có tác dụng ghi nếu truy vấn ghi.
- **Transaction, mapping, schema và phiên bản thư viện đều ảnh hưởng kết quả test**. Phân biệt lỗi logic truy vấn với lỗi do rollback/isolation hoặc môi trường chạy.
