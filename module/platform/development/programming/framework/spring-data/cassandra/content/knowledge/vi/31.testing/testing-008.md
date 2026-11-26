# Kiểm thử truy vấn dẫn xuất, `@Query` và điều kiện không hợp lệ trong Spring Data Cassandra

## 1. Mục tiêu kiểm thử

**Spring Data Cassandra** giúp truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và CQL. Repository có thể sinh câu truy vấn từ tên phương thức (*derived query*) hoặc thực thi câu CQL được khai báo trong `@Query`. Tuy nhiên, một phương thức Java hợp lệ về cú pháp **không đảm bảo** truy vấn hợp lệ với mô hình phân tán của Cassandra.

Khác với cách thử repository chỉ bằng mock, kiểm thử truy vấn Cassandra cần trả lời những câu hỏi cụ thể:

1. Spring Data có phân giải đúng tên thuộc tính, kể cả thuộc tính trong composite primary key, và ánh xạ sang đúng tên cột CQL không?
2. Điều kiện `WHERE` có cung cấp partition key và tuân theo quy tắc clustering key không?
3. Truy vấn `@Query` có bind tham số đúng kiểu, đúng thứ tự, không ghép chuỗi giá trị người dùng vào CQL không?
4. Truy vấn không hợp lệ có thật sự bị Cassandra từ chối; ứng dụng có nhận diện đúng lỗi đó không?
5. Truy vấn hợp lệ có trả đúng partition, đúng mốc thời gian, đúng bản ghi và thứ tự mong đợi không?
6. Phân trang, consistency và chi phí truy vấn có được kiểm tra đúng giới hạn của môi trường test không?

Mục tiêu cuối cùng không chỉ là “test xanh”. Một bộ kiểm thử tốt phải phát hiện được **lỗi thiết kế truy vấn theo bảng** trước khi lỗi xuất hiện dưới tải production.

## 2. Fixture dữ liệu phải phản ánh thiết kế bảng theo truy vấn

Giả sử ứng dụng cung cấp chức năng “liệt kê đơn hàng của một khách hàng theo thời gian, từ mới đến cũ”. Ta tạo bảng dành riêng cho mẫu truy vấn này:

```sql
CREATE KEYSPACE IF NOT EXISTS commerce_test
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS commerce_test.orders_by_customer (
    customer_id text,
    created_at  timestamp,
    order_id    uuid,
    status      text,
    total       decimal,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
```

Trong schema này:

- `customer_id` là **partition key**; truy vấn thường cần giới hạn theo khách hàng để đọc đúng partition.
- `created_at` và `order_id` là **clustering columns**. Chúng hỗ trợ điều kiện trên các thành phần khóa theo thứ tự phù hợp.
- `status` và `total` là cột thường. Không có secondary index hoặc cơ chế truy vấn khác cho `status` trong fixture.
- `created_at DESC` là thứ tự clustering được lưu trong schema. Không nên giả định kết quả sẽ được sắp theo một cột bất kỳ chỉ vì repository trả về `List`.

Chọn `uuid` cho `order_id` để fixture có thể dùng UUID cố định, tránh nhầm với quy tắc phiên bản UUID của kiểu CQL `timeuuid`. `decimal` được ánh xạ tự nhiên sang `BigDecimal`; `timestamp` sang `Instant`.

### 2.1. Ánh xạ entity và khóa ghép

Ví dụ dùng Spring Data Cassandra trong dự án Java, với các annotation thuộc gói `org.springframework.data.cassandra.core.mapping`:

```java
@PrimaryKeyClass
public class OrderKey implements Serializable {
    @PrimaryKeyColumn(
        name = "customer_id", ordinal = 0,
        type = PrimaryKeyType.PARTITIONED
    )
    private String customerId;

    @PrimaryKeyColumn(
        name = "created_at", ordinal = 1,
        type = PrimaryKeyType.CLUSTERED
    )
    private Instant createdAt;

    @PrimaryKeyColumn(
        name = "order_id", ordinal = 2,
        type = PrimaryKeyType.CLUSTERED
    )
    private UUID orderId;

    // Constructor rỗng, constructor có tham số, getters/setters,
    // equals và hashCode theo ba thành phần khóa.
}

@Table("orders_by_customer")
public class OrderByCustomer {
    @PrimaryKey
    private OrderKey key;

    @Column("status")
    private String status;

    @Column("total")
    private BigDecimal total;

    // Constructor rỗng, constructor nhận (key, status, total),
    // getters/setters phù hợp với cơ chế mapping được dùng.
}
```

Đây là phần khai báo trọng tâm; ví dụ được rút gọn import và boilerplate. Trong mã thật, kiểu khóa cần `equals`/`hashCode` nhất quán, các constructor/accessor phù hợp, và ứng dụng kết nối vào `commerce_test`. Đừng suy ra rằng chỉ đổi annotation `@PrimaryKeyColumn` sẽ thay được cấu trúc primary key của bảng đã tồn tại.

### 2.2. Repository có cả truy vấn hợp lệ và truy vấn cần kiểm chứng lỗi

```java
public interface OrderRepository
        extends CassandraRepository<OrderByCustomer, OrderKey> {

    // Điều kiện trên partition key qua property path key.customerId.
    List<OrderByCustomer> findByKeyCustomerId(String customerId);

    // Điều kiện hợp lệ: partition key + khoảng của clustering key đầu tiên.
    List<OrderByCustomer>
        findByKeyCustomerIdAndKeyCreatedAtGreaterThanEqual(
            String customerId, Instant from);

    // CQL tường minh; ?0, ?1 là tham số được framework bind.
    @Query("""
           SELECT * FROM orders_by_customer
           WHERE customer_id = ?0 AND created_at >= ?1
           """)
    List<OrderByCustomer> findRecentByQuery(
        String customerId, Instant from);

    // Cố ý sai với schema fixture: status là cột không thuộc khóa,
    // không có index và không bật ALLOW FILTERING.
    List<OrderByCustomer> findByStatus(String status);

    // Cố ý sai: đã có partition key nhưng vẫn lọc trực tiếp
    // trên một cột thường không được lập index.
    @Query("""
           SELECT * FROM orders_by_customer
           WHERE customer_id = ?0 AND status = ?1
           """)
    List<OrderByCustomer> findStatusByQuery(
        String customerId, String status);
}
```

`@Query` ở đây là `org.springframework.data.cassandra.repository.Query`, không phải annotation cùng tên của Spring Data JPA. Chuỗi query trên dùng Java text block (Java 15+); với Java cũ có thể dùng chuỗi Java thông thường.

Tên `findByKeyCustomerId` đi theo đường thuộc tính `key.customerId`. Spring Data Commons có quy tắc phân giải tên thuộc tính lồng nhau; nếu mô hình có tên gây mơ hồ, cân nhắc dấu gạch dưới để chỉ ranh giới property path và **xác nhận bằng kiểm thử tích hợp**. Câu CQL do Spring Data sinh ra mới là bằng chứng rằng ánh xạ đã đúng.

Các phương thức “cố ý sai” chỉ dùng để làm bài kiểm thử âm. Trong code sản phẩm, nên tách chúng vào repository test chuyên dụng hoặc loại bỏ sau khi xác định hành vi lỗi.

## 3. Thiết kế ma trận kiểm thử trước khi viết assertion

Bảng sau phân biệt rõ **kỳ vọng dữ liệu** với **kỳ vọng Cassandra từ chối truy vấn**:

| Truy vấn cần thử | Điều kiện mẫu | Kỳ vọng | Điều được kiểm chứng |
| --- | --- | --- | --- |
| Derived: `findByKeyCustomerId` | `customer_id = 'KH-01'` | Thành công, chỉ có hàng của KH-01 | Ánh xạ property path tới partition key |
| Derived: `...CreatedAtGreaterThanEqual` | Partition key + `created_at >= t2` | Thành công, không chứa hàng cũ hơn `t2` | Toán tử `GreaterThanEqual` và giá trị biên |
| `@Query` hợp lệ | `customer_id = ?0 AND created_at >= ?1` | Thành công, cùng tập dữ liệu dự kiến | CQL, bind và conversion |
| Derived không hợp lệ | `status = 'PAID'` | Cassandra từ chối nếu không có index/filter | Không thể lọc cột thường tùy ý |
| `@Query` không hợp lệ | Partition key + `status = ?1` | Cassandra từ chối với fixture hiện tại | Có partition key chưa đủ cho mọi `WHERE` |
| Thiếu partition key | Chỉ `created_at >= t2` | Bị từ chối trong schema này | Quy tắc chọn partition/clustering |
| `@Query` sai cột | `missing_column = ?0` | Bị từ chối vì cột không tồn tại | Tên CQL phải khớp schema |
| Giá trị bind có dấu nháy | Chuỗi khách hàng chứa `'` | Được coi là dữ liệu, không thay đổi cấu trúc CQL | Bind tham số an toàn |
| Khóa phân vùng không tồn tại | `customer_id = 'KH-X'` | Trả tập rỗng, không lỗi CQL | Phân biệt “không có dữ liệu” và “truy vấn sai” |

**Điều kiện của ma trận:** bảng fixture không có index trên `status`, không dùng `ALLOW FILTERING`, cùng keyspace và phiên bản schema. Nếu thêm index hoặc thay thiết kế bảng, cần cập nhật kết quả kỳ vọng. Không ghi cứng kỳ vọng “truy vấn theo status luôn sai” cho mọi mô hình Cassandra.

## 4. Thiết lập kiểm thử tích hợp với Cassandra thật

Một unit test chỉ viết:

```java
when(orderRepository.findByKeyCustomerId("KH-01"))
    .thenReturn(List.of(order));
```

chỉ kiểm tra hành vi của mock. Nó **không chạy CQL**, không kiểm tra parser của Cassandra, metadata primary key, driver codec hoặc quy tắc `WHERE`. Vì vậy phần kiểm thử này nên dùng Cassandra thật trong môi trường cô lập, chẳng hạn **Testcontainers**.

### 4.1. Chuẩn bị schema khi container khởi động

Đặt câu CQL của mục 2 vào một resource test, ví dụ `src/test/resources/cassandra/schema-test.cql`, để container khởi tạo keyspace và bảng. Không phụ thuộc vào schema của máy lập trình viên hoặc một keyspace dùng chung.

Ví dụ cấu hình với Spring Boot 3.x, JUnit 5 và Testcontainers (điều chỉnh property nếu phiên bản Spring Boot khác):

```java
@DataCassandraTest
@Testcontainers
class OrderRepositoryIT {

    @Container
    static final CassandraContainer<?> CASSANDRA =
        new CassandraContainer<>("cassandra:5.0")
            .withInitScript("cassandra/schema-test.cql");

    @DynamicPropertySource
    static void cassandraProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.cassandra.contact-points",
                     CASSANDRA::getHost);
        registry.add("spring.cassandra.port",
                     CASSANDRA::getFirstMappedPort);
        registry.add("spring.cassandra.local-datacenter",
                     () -> "datacenter1");
        registry.add("spring.cassandra.keyspace-name",
                     () -> "commerce_test");
        registry.add("spring.cassandra.schema-action",
                     () -> "NONE");
    }

    @Autowired OrderRepository repository;
    @Autowired CqlSession session;

    // Các phương thức kiểm thử ở những mục tiếp theo.
}
```

Các import chính:

- `org.springframework.boot.test.autoconfigure.data.cassandra.DataCassandraTest`;
- `org.testcontainers.junit.jupiter.Testcontainers` và `Container`;
- `org.testcontainers.containers.CassandraContainer`;
- `org.springframework.test.context.DynamicPropertySource`, `DynamicPropertyRegistry`;
- `com.datastax.oss.driver.api.core.CqlSession`.

Dự án cần dependencies tương thích cho Spring Data Cassandra, driver, Spring Boot Test, JUnit 5, AssertJ và Testcontainers Cassandra. Tùy phiên bản Spring Boot, việc tạo kết nối, khai báo keyspace và tự động đăng ký container có thể khác; ví dụ trên cho thấy **nguyên tắc cô lập** hơn là thay thế cấu hình thực tế của từng dự án.

Container một node, replication factor 1 đủ để phát hiện lỗi mapping, CQL và bind. Nó **không mô phỏng đầy đủ** quorum, network partition hay độ trễ giữa replica ở cluster nhiều node. Các đặc tính consistency và hiệu năng phân tán cần môi trường kiểm thử riêng.

### 4.2. Cố định dữ liệu đầu vào cho mỗi lần test

Cần ít nhất hai partition và nhiều mốc thời gian trong cùng một partition, để test không thể “qua tình cờ” khi query đọc nhầm:

| Khách hàng | Thời gian UTC | Trạng thái | Dùng để kiểm tra |
| --- | --- | --- | --- |
| KH-01 | 2026-01-01 09:00 | NEW | Hàng trước mốc thời gian |
| KH-01 | 2026-01-01 10:00 | PAID | Hàng ở đúng mốc thời gian |
| KH-01 | 2026-01-01 11:00 | PAID | Hàng sau mốc thời gian |
| KH-02 | 2026-01-01 10:30 | PAID | Phát hiện lẫn partition |

Có thể đặt trong chính lớp `OrderRepositoryIT`:

```java
private static final Instant FROM =
    Instant.parse("2026-01-01T10:00:00Z");

@BeforeEach
void seed() {
    // Chỉ dùng TRUNCATE trên keyspace/bảng cô lập của test.
    session.execute("TRUNCATE commerce_test.orders_by_customer");

    save("KH-01", "2026-01-01T09:00:00Z",
         "00000000-0000-4000-8000-000000000001", "NEW");
    save("KH-01", "2026-01-01T10:00:00Z",
         "00000000-0000-4000-8000-000000000002", "PAID");
    save("KH-01", "2026-01-01T11:00:00Z",
         "00000000-0000-4000-8000-000000000003", "PAID");
    save("KH-02", "2026-01-01T10:30:00Z",
         "00000000-0000-4000-8000-000000000004", "PAID");
}

private void save(String customerId, String timestamp,
                  String orderId, String status) {
    OrderKey key = new OrderKey(
        customerId,
        Instant.parse(timestamp),
        UUID.fromString(orderId)
    );
    repository.save(
        new OrderByCustomer(key, status, new BigDecimal("20.00"))
    );
}
```

Đoạn fixture dùng các constructor đã ghi chú ở phần entity. Mỗi test phải khởi đầu từ dữ liệu xác định. Nếu bộ kiểm thử chạy song song, các test dùng cùng một bảng và lệnh `TRUNCATE` có thể ảnh hưởng nhau: cấu hình không chạy song song nhóm test này, hoặc dùng keyspace/bảng tách biệt. Việc cố định UTC và UUID giúp tránh flakiness do múi giờ hoặc thứ tự tạo dữ liệu.

## 5. Kiểm thử truy vấn dẫn xuất hợp lệ

### 5.1. Phân vùng đúng và không trả dữ liệu của khách hàng khác

```java
@Test
void derivedQueryReadsOnlyOnePartition() {
    List<OrderByCustomer> rows =
        repository.findByKeyCustomerId("KH-01");

    assertThat(rows).hasSize(3);
    assertThat(rows)
        .extracting(row -> row.getKey().getCustomerId())
        .containsOnly("KH-01");

    assertThat(repository.findByKeyCustomerId("KH-X"))
        .isEmpty();
}
```

Kết quả ba hàng kiểm tra số lượng; assertion `containsOnly("KH-01")` kiểm tra không lẫn partition. Trường hợp `KH-X` phân biệt repository trả rỗng một cách hợp lệ với exception do truy vấn sai.

### 5.2. Kiểm thử `GreaterThanEqual` tại giá trị biên

```java
@Test
void derivedQueryIncludesLowerBoundAndExcludesOlderRows() {
    List<OrderByCustomer> rows =
        repository
            .findByKeyCustomerIdAndKeyCreatedAtGreaterThanEqual(
                "KH-01", FROM);

    assertThat(rows)
        .extracting(row -> row.getKey().getCreatedAt())
        .containsExactlyInAnyOrder(
            Instant.parse("2026-01-01T10:00:00Z"),
            Instant.parse("2026-01-01T11:00:00Z")
        );
}
```

Dùng `containsExactlyInAnyOrder` vì test này kiểm tra **tập kết quả và biên điều kiện**. Nếu cần kiểm tra thứ tự sắp xếp, viết một test riêng dựa trên `CLUSTERING ORDER BY` đã khai báo và điều kiện chọn một partition. Tránh vô tình buộc một phương thức chỉ yêu cầu lọc phải đáp ứng thứ tự không được công bố trong contract.

Một test bổ sung nên dùng `GreaterThan` (không có `Equal`) nếu ứng dụng có phương thức này: tại mốc 10:00, hàng đúng 10:00 phải bị loại. Đó là cách bắt lỗi đổi nhầm toán tử so sánh.

### 5.3. Đối chiếu kết quả với CQL độc lập

Với lỗi khó phân biệt giữa query derivation và entity mapping, có thể kiểm tra một truy vấn chuẩn bằng `CqlSession`:

```java
PreparedStatement prepared = session.prepare("""
    SELECT customer_id, created_at, order_id, status, total
    FROM commerce_test.orders_by_customer
    WHERE customer_id = ?
    """);

ResultSet result = session.execute(prepared.bind("KH-01"));
List<Row> rawRows = result.all();

assertThat(rawRows).hasSize(3);
```

Test này có giá trị chẩn đoán vì bỏ qua tầng xây dựng query repository. Nếu CQL độc lập chạy đúng mà derived query lỗi, kiểm tra tên method, property path và metadata mapping. Nếu CQL độc lập cũng lỗi, kiểm tra schema, keyspace, kiểu bind hoặc dữ liệu fixture trước.

## 6. Kiểm thử `@Query` và binding

### 6.1. Kiểm tra tập kết quả tương đương

```java
@Test
void annotatedQueryFiltersByPartitionAndTime() {
    List<OrderByCustomer> rows =
        repository.findRecentByQuery("KH-01", FROM);

    assertThat(rows)
        .extracting(row -> row.getKey().getCreatedAt())
        .containsExactlyInAnyOrder(
            Instant.parse("2026-01-01T10:00:00Z"),
            Instant.parse("2026-01-01T11:00:00Z")
        );
}
```

Trong `@Query`:

- `?0` tương ứng tham số đầu tiên `customerId`, `?1` tương ứng `from`.
- Tên trong CQL là tên **cột/bảng vật lý**, không phải tên property Java.
- Tham số nên được bind bởi framework; không ghép chuỗi chứa dữ liệu người dùng vào nội dung câu CQL.
- Kiểu `Instant` phải tương thích `timestamp`; kiểu không tương thích cần được phát hiện bằng test với schema thật.

Có thể đối chiếu hai truy vấn hợp lệ:

```java
@Test
void derivedAndAnnotatedQueriesReturnSameKeys() {
    List<OrderByCustomer> derived =
        repository
            .findByKeyCustomerIdAndKeyCreatedAtGreaterThanEqual(
                "KH-01", FROM);

    List<OrderByCustomer> annotated =
        repository.findRecentByQuery("KH-01", FROM);

    assertThat(annotated)
        .extracting(OrderByCustomer::getKey)
        .containsExactlyInAnyOrderElementsOf(
            derived.stream()
                   .map(OrderByCustomer::getKey)
                   .toList()
        );
}
```

Đây là phép đối chiếu hữu ích, nhưng vẫn cần kiểm tra kết quả dự kiến riêng như ở mục 5.2: nếu cả hai phương thức cùng mắc một lỗi ánh xạ và trả cùng kết quả sai, kiểm tra “hai bên bằng nhau” chưa đủ.

### 6.2. Đảm bảo giá trị bind được coi là dữ liệu

Một chuỗi chứa dấu nháy không được làm thay đổi cấu trúc truy vấn:

```java
@Test
void queryParameterIsNotConcatenatedIntoCql() {
    String untrustedCustomerId = "KH-01' OR customer_id = 'KH-02";

    assertThat(
        repository.findRecentByQuery(untrustedCustomerId, FROM)
    ).isEmpty();
}
```

Test này xác minh hành vi với dữ liệu đầu vào có ký tự đặc biệt; việc chống injection còn phụ thuộc toàn bộ đường tạo câu truy vấn. Không chỉ vì có một test xanh mà cho phép lập trình viên xây `@Query` bằng nối chuỗi user input ở chỗ khác. Với tên cột/bảng động, cần whitelist riêng vì bind marker chỉ thay thế **giá trị**, không thay thế identifier CQL.

### 6.3. Kiểm tra phép chiếu và kiểu trả về

Nếu `@Query` chỉ chọn một số cột, kiểu projection và những property thực sự được dùng phải được kiểm chứng. Ví dụ:

```java
@Query("""
       SELECT customer_id, created_at, order_id, status
       FROM orders_by_customer
       WHERE customer_id = ?0
       """)
List<OrderByCustomer> findPartial(String customerId);
```

Câu trên không trả `total`. Việc ánh xạ vào entity đầy đủ có thể để `total` ở `null` tùy mapping; như vậy không phù hợp nếu service giả định số tiền luôn được tải đầy đủ. Cách tốt hơn khi cần dữ liệu rút gọn là dùng projection/DTO phù hợp với khả năng của phiên bản Spring Data đang dùng và kiểm thử cụ thể phần dữ liệu có mặt, thay vì dựa vào mặc định ngầm định.

## 7. Kiểm thử điều kiện `WHERE` không hợp lệ

### 7.1. Vì sao “chạy được trên SQL” vẫn bị Cassandra từ chối?

Cassandra chọn dữ liệu theo partition. Truy vấn trên một cột thường không có index có thể đòi đọc rất nhiều partition hoặc nhiều hàng trong partition. Mặc định Cassandra hạn chế những truy vấn như vậy, trừ khi dùng cơ chế phù hợp và trong một số trường hợp có `ALLOW FILTERING`.

Với schema đã định nghĩa:

| CQL rút gọn | Hợp lệ? | Nguyên nhân |
| --- | --- | --- |
| `WHERE customer_id = ?` | Có | Chỉ định partition key |
| `WHERE customer_id = ? AND created_at >= ?` | Có | Giới hạn partition và clustering key đầu tiên |
| `WHERE status = ?` | Không, với fixture này | Cột không thuộc khóa, không có index |
| `WHERE customer_id = ? AND status = ?` | Không, với fixture này | Điều kiện cột thường chưa được hỗ trợ |
| `WHERE created_at >= ?` | Không, với fixture này | Thiếu partition key |
| `WHERE customer_id = ? AND order_id = ?` | Thường không hợp lệ | Bỏ qua clustering key đứng trước `order_id` |
| `WHERE customer_id = ? ORDER BY status` | Không | `status` không phải clustering column để sắp xếp như vậy |
| `WHERE missing_column = ?` | Không | Cột không tồn tại trong schema |

Cassandra có những khả năng bổ sung như index, `IN`, lọc và truy vấn theo tổ hợp khóa tùy phiên bản; chúng thay đổi tập câu lệnh khả dụng, nhưng cũng thay đổi đặc tính hiệu năng. Bảng trên là kết luận **trong phạm vi schema fixture cụ thể**, không phải luật phủ định tuyệt đối cho mọi cluster.

Không dùng `ALLOW FILTERING` chỉ để “sửa” test thất bại: test này có nhiệm vụ phát hiện truy vấn không phù hợp với thiết kế bảng. Nếu cần truy vấn theo `status` thường xuyên, hãy cân nhắc bảng theo truy vấn hoặc index phù hợp sau khi đánh giá cardinality, dữ liệu, phiên bản Cassandra và tải dự kiến.

### 7.2. Assertion đối với truy vấn bị từ chối

Một test âm nên khẳng định lỗi đến từ **Cassandra từ chối CQL**, thay vì chỉ `assertThrows(Exception.class)` vì điều đó cũng “đậu” khi ứng dụng lỗi kết nối hoặc converter không liên quan.

Với Cassandra Java Driver 4, khi server trả lỗi truy vấn không hợp lệ thường có `com.datastax.oss.driver.api.core.servererrors.InvalidQueryException`. Spring Data có thể bọc hoặc chuyển dịch ngoại lệ theo phiên bản; có thể kiểm tra chuỗi `cause`:

```java
private static boolean hasInvalidQueryCause(Throwable error) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {
        if (current instanceof InvalidQueryException) {
            return true;
        }
    }
    return false;
}

@Test
void derivedFilterOnUnindexedColumnIsRejected() {
    assertThatThrownBy(() -> repository.findByStatus("PAID"))
        .satisfies(error ->
            assertThat(hasInvalidQueryCause(error)).isTrue()
        );
}

@Test
void annotatedFilterOnUnindexedColumnIsRejected() {
    assertThatThrownBy(
        () -> repository.findStatusByQuery("KH-01", "PAID")
    ).satisfies(error ->
        assertThat(hasInvalidQueryCause(error)).isTrue()
    );
}
```

Điều kiện để hai test này ổn định: schema có đúng cột, không có index trên `status`, không có `ALLOW FILTERING`, session kết nối đúng keyspace. Nếu truy vấn bị kiểm tra **ngay khi khởi tạo repository** ở phiên bản framework đang dùng, test âm cần đặt trong context riêng và assert lỗi khởi tạo đó; đừng để nó làm hỏng toàn bộ các test dương.

Không gắn chặt assertion vào toàn bộ nguyên văn thông báo từ server: thông điệp có thể đổi theo phiên bản Cassandra. Khi driver phiên bản khác hoặc Spring xử lý exception khác, điều chỉnh kiểm tra dựa trên cause chain và xác nhận thật sự là lỗi CQL mong đợi.

### 7.3. Negative test cho cột sai và thiếu partition key

Các phép thử bổ sung giúp phân biệt lỗi metadata với lỗi quy tắc `WHERE`:

```java
// Thí dụ CQL cố ý sai, chạy trong một test tích hợp riêng:
session.execute(
    "SELECT * FROM commerce_test.orders_by_customer " +
    "WHERE missing_column = 'X'"
);

// Thí dụ khác: clustering key không có partition key:
session.execute(
    "SELECT * FROM commerce_test.orders_by_customer " +
    "WHERE created_at >= '2026-01-01T10:00:00Z'"
);
```

Hai câu trên là **mẫu thao tác bị từ chối**, không phải mã nên gọi không bắt lỗi. Trong test thực, đặt mỗi câu vào `assertThatThrownBy(...)` và xác minh loại lỗi từ Cassandra. Nên ưu tiên câu đầu để kiểm tra chính xác phát hiện cột không tồn tại; câu thứ hai để minh họa query theo clustering key khi không xác định partition.

Một negative test khác là gọi repository bằng `null` ở thành phần partition key. Tuy nhiên việc từ chối có thể xảy ra ở validation, tầng mapping, driver hoặc server. Phải xác định tầng muốn kiểm tra; không mặc định mọi `null` đều trả cùng một loại exception.

### 7.4. Phân biệt lỗi dự kiến với lỗi do môi trường

Khi test bị đỏ, đối chiếu theo thứ tự:

1. **Container/connection:** Cassandra đã khởi động? Driver có vào được cluster và local datacenter đúng không?
2. **Keyspace/schema:** Bảng đang có cùng partition key, clustering key, cột và index với fixture không?
3. **Chuỗi truy vấn:** Tên bảng/cột CQL, thứ tự tham số `?0`/`?1` và toán tử có đúng không?
4. **Conversion:** Giá trị Java có bind được sang kiểu CQL không (`Instant`/`timestamp`, `BigDecimal`/`decimal`)?
5. **Quy tắc Cassandra:** `WHERE` có chọn được partition và chuỗi clustering key hợp lệ không?
6. **Kết quả:** Nếu query chạy thành công, dữ liệu trả về có đúng ranh giới, partition và thứ tự không?

Đừng sửa test thành `catch (Exception ignored)` hoặc assert “bất kỳ exception nào” để che lỗi. Trong kiểm thử âm, ngoại lệ là kết quả kỳ vọng **chỉ khi** root cause đúng quy tắc đang kiểm tra.

## 8. Dùng `CassandraTemplate` để tách lỗi query và lỗi repository

`CassandraTemplate` dùng cùng hệ thống mapping nhưng cho phép biểu diễn truy vấn tường minh hơn:

```java
Query query = Query.query(
    Criteria.where("customer_id").is("KH-01")
);

List<OrderByCustomer> rows =
    cassandraTemplate.select(query, OrderByCustomer.class);

assertThat(rows).hasSize(3);
```

Ví dụ trên dùng `org.springframework.data.cassandra.core.query.Query`, `Criteria` và `org.springframework.data.cassandra.core.CassandraTemplate`.

Khi `CqlSession` với prepared CQL chạy đúng nhưng derived repository sai, hãy kiểm tra phương thức sinh query và mapping property path. Nếu `CassandraTemplate` cũng sai, cần xem lại metadata của entity, conversion và schema. Nếu cả ba đường đều thất bại, ưu tiên kiểm tra kết nối, keyspace, schema và dữ liệu bind. Đây là cách **khoanh vùng lỗi**, không phải cơ sở để bỏ qua kiểm thử repository thực tế.

## 9. Kiểm thử paging, thứ tự và đặc tính phân tán

Với Cassandra, `LIMIT` trong CQL không đồng nghĩa đầy đủ với phân trang ổn định. Driver có cơ chế fetch size, paging state; ứng dụng không nên mặc định offset-based pagination kiểu SQL. Khi test API phân trang repository hoặc `CassandraTemplate`, cần chú ý:

- Tạo nhiều hàng trong cùng partition hơn page size (ví dụ 7 hàng, kích thước trang 3) và duyệt qua các trang để xác minh đủ 7 hàng, không lặp hoặc bỏ sót.
- Kiểm tra paging state/token tiếp tục truy vấn hợp lệ trong cùng ngữ cảnh truy vấn và tham số; không tự chế offset bằng cách bỏ qua hàng.
- Nếu contract yêu cầu thứ tự, xác minh thứ tự dựa trên clustering order và `ORDER BY` hợp lệ. Không dùng thứ tự insertion làm oracle.
- Không mặc định một phương thức `Page` luôn rẻ: tính tổng số hàng toàn bộ bảng/partition có thể tốn kém hoặc không được API hỗ trợ như SQL. Cân nhắc `Slice` hoặc driver paging state theo API thực tế.
- Không chỉ kiểm tra số lượng hàng: hãy kiểm tra khóa duy nhất và ranh giới trang; nếu dữ liệu đang thay đổi đồng thời, cần quy định rõ khả năng xuất hiện trùng/thiếu theo cơ chế truy vấn.

Testcontainers một node xác nhận logic mapping/paging cơ bản, nhưng không thay thế test tải. Để đánh giá hiệu năng, đo latency và số lần truy cập dưới partition đủ lớn, kiểm tra query plan theo công cụ phù hợp, metrics và ảnh hưởng của consistency level. Những kiểm tra này phụ thuộc hạ tầng và cấu hình cluster; một unit test hoặc vài hàng dữ liệu không thể chứng minh truy vấn đủ nhanh trong production.

## 10. Lỗi thường gặp khi viết test repository Cassandra

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Chỉ dùng mock repository | Không phát hiện CQL sai hay thiếu partition key | Dùng test tích hợp với Cassandra thật |
| Chia sẻ keyspace với môi trường khác | Test phụ thuộc dữ liệu cũ, có thể xóa nhầm dữ liệu | Testcontainers/keyspace cô lập |
| Không cố định schema/index | Negative test lúc đậu lúc không | Tạo schema từ resource test có phiên bản |
| Chỉ có một partition | Không phát hiện query đọc lẫn khách hàng | Seed tối thiểu hai partition |
| Không có giá trị đúng biên | Không phân biệt `>` và `>=` | Seed trước/tại/sau mốc thời gian |
| Assert nguyên văn thông báo lỗi | Dễ gãy khi nâng phiên bản Cassandra | Xác minh loại lỗi và cause chain |
| Tự thêm `ALLOW FILTERING` | Che thiết kế truy vấn không phù hợp | Đánh giá lại bảng theo query |
| Ghép chuỗi để tạo `@Query` | Sai cú pháp, nguy cơ injection | Dùng bind parameter |
| So sánh thứ tự `List` không có contract | Test đỏ do giả định sắp xếp sai | Assert tập kết quả, test thứ tự riêng |
| Quên paging và kích thước partition | Test nhỏ xanh nhưng API chậm khi dữ liệu lớn | Test paging nhiều trang và tải thực tế |

## 11. Checklist hoàn thành

- [ ] CQL fixture tạo đúng keyspace, bảng, partition key và clustering columns.
- [ ] Test thực thi cùng phiên bản migration/schema mà ứng dụng dự kiến sử dụng.
- [ ] Derived query đọc đúng partition và có test giá trị biên của toán tử so sánh.
- [ ] `@Query` bind đúng tham số, đúng kiểu và truy vấn không rò sang partition khác.
- [ ] Các negative test cố ý tạo điều kiện `WHERE` không hợp lệ, xác minh lỗi từ Cassandra.
- [ ] Không có index hoặc `ALLOW FILTERING` ngoài dự tính khiến negative test đổi ý nghĩa.
- [ ] Có dữ liệu rỗng, hai partition, nhiều mốc thời gian và ít nhất một trường hợp ký tự đặc biệt.
- [ ] Các assertion không phụ thuộc dữ liệu từ test khác, thứ tự không công bố hay văn bản exception cứng.
- [ ] Có kiểm tra paging và ranh giới trang nếu API trả dữ liệu nhiều trang.
- [ ] Nếu yêu cầu bảo đảm consistency/hiệu năng, có kế hoạch kiểm chứng trên môi trường nhiều node và dữ liệu đủ lớn.

Kiểm thử truy vấn trong **Spring Data Cassandra** phải tôn trọng nguyên tắc thiết kế bảng theo truy vấn. Repository và `@Query` là hai cách xây lệnh CQL, nhưng **cluster và lược đồ thật** mới quyết định câu truy vấn có hợp lệ, hiệu quả và cho kết quả đúng hay không. Test tích hợp có fixture rõ ràng, các trường hợp âm có chủ đích và các assertion về partition, biên thời gian, paging sẽ giúp phát hiện sai lệch trước khi hệ thống chịu tải phân tán.
