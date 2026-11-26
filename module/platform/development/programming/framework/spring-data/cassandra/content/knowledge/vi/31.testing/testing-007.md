# Kiểm thử khóa ghép, static column và kiểu dữ liệu lồng nhau

Trong **Spring Data Cassandra**, một bài kiểm thử thành công ở lớp repository chưa chắc chứng minh mô hình dữ liệu đúng. Một entity có thể lưu và đọc lại được, nhưng truy vấn vẫn chọn sai partition; một trường `static` có thể bị cập nhật ngoài ý muốn cho toàn bộ partition; một đối tượng lồng nhau có thể bị mất giá trị khi chuyển đổi giữa Java và CQL. Các lỗi này thường chỉ lộ rõ khi chạy trên **Apache Cassandra thật**, với nhiều dòng, nhiều partition và dữ liệu có cấu trúc phức tạp.

Bài thuộc chương **Kiểm thử** của module **SPRING_DATA_CASSANDRA**. Phạm vi bao gồm entity mapping, repository, `CassandraTemplate`/CQL và cách kiểm tra thiết kế bảng theo truy vấn, partition key, consistency, paging và hiệu năng. Trọng tâm là xây dựng một bộ **integration test có ý nghĩa** cho ba nhóm tính năng: **khóa chính ghép (composite primary key)**, **static column**, và **kiểu dữ liệu lồng nhau (nested UDT/collection)**.

> **Nguyên tắc:** Với các hành vi phụ thuộc mô hình lưu trữ của Cassandra, phải kiểm tra cả dữ liệu truy vấn thực tế ở CQL lẫn kết quả ánh xạ của Spring Data. Mock repository phù hợp cho logic nghiệp vụ thuần túy, nhưng không thể thay Cassandra để xác minh partition, clustering, static column hay `frozen` UDT.

## 1. Mục tiêu kiểm thử

Sau bài này, bạn có thể:

1. Tách rõ partition key và clustering key trong một composite key, đồng thời kiểm tra ranh giới truy vấn và thứ tự trả về.
2. Kiểm tra annotation Spring Data như `@PrimaryKeyClass`, `@PrimaryKeyColumn`, `@PrimaryKey` và khóa ID sử dụng cho repository.
3. Xác nhận rằng một `static column` dùng chung cho các dòng trong **cùng partition**, nhưng không lan sang partition khác.
4. Kiểm tra ánh xạ và round-trip của UDT, UDT lồng trong UDT, `list`, `set` và `map`; hiểu vai trò của `frozen`.
5. Đánh giá các ca lỗi: thiếu thành phần khóa, ghi trùng primary key, thứ tự timestamp, null/empty collection, cập nhật một phần UDT, xóa dòng và thay đổi schema.
6. Tổ chức integration test ổn định với Cassandra dùng riêng cho kiểm thử, có dữ liệu độc lập, assertion dựa trên hành vi CQL và kiểm tra hiệu năng cơ bản.

## 2. Tình huống mẫu: nhật ký hoạt động theo khách hàng

Giả sử hệ thống phải thực hiện những truy vấn sau:

- Lấy hoạt động gần nhất của một khách hàng trong một tenant.
- Xem chi tiết hoạt động theo khóa đầy đủ.
- Hiển thị phân khúc khách hàng hiện tại ngay trong danh sách hoạt động.
- Lưu địa chỉ giao hàng và danh sách mặt hàng có cấu trúc lồng nhau.

Một mô hình phù hợp là bảng `activity_by_customer`. Ta dùng khóa partition ghép `(tenant_id, customer_id)` để hai tenant có cùng mã khách hàng không đọc lẫn dữ liệu; khóa clustering `(occurred_at, activity_id)` để sắp xếp hoạt động theo thời gian và phân biệt các sự kiện xảy ra cùng mili giây.

### 2.1. CQL schema cho toàn bộ bài

~~~sql
CREATE KEYSPACE IF NOT EXISTS knowledge_test
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
};

CREATE TYPE IF NOT EXISTS knowledge_test.geo_point (
    lat double,
    lon double
);

CREATE TYPE IF NOT EXISTS knowledge_test.shipping_address (
    street text,
    city text,
    geo frozen<knowledge_test.geo_point>
);

CREATE TYPE IF NOT EXISTS knowledge_test.item_snapshot (
    sku text,
    quantity int,
    destination frozen<knowledge_test.shipping_address>
);

CREATE TABLE IF NOT EXISTS knowledge_test.activity_by_customer (
    tenant_id uuid,
    customer_id uuid,
    occurred_at timestamp,
    activity_id uuid,

    customer_segment text static,
    default_address frozen<knowledge_test.shipping_address> static,

    kind text,
    shipping_address frozen<knowledge_test.shipping_address>,
    labels set<text>,
    metadata map<text, text>,
    items list<frozen<knowledge_test.item_snapshot>>,

    PRIMARY KEY ((tenant_id, customer_id), occurred_at, activity_id)
) WITH CLUSTERING ORDER BY (occurred_at DESC, activity_id ASC);
~~~

**Giải nghĩa các thành phần:**

| Thành phần | Chức năng | Điều cần kiểm thử |
|---|---|---|
| `tenant_id` + `customer_id` | Composite partition key | Mọi thao tác dựa trên partition phải cung cấp **đủ cả hai** |
| `occurred_at` | Clustering key thứ nhất, giảm dần | Dòng mới hơn xuất hiện trước |
| `activity_id` | Clustering key thứ hai, tăng dần | Tạo tính duy nhất khi cùng thời điểm; thứ tự tie-breaker |
| `customer_segment` | Static column dạng `text` | Cùng giá trị trong partition, độc lập giữa các partition |
| `default_address` | Static column dạng frozen UDT | Cập nhật một địa chỉ chung, đọc thấy ở mọi dòng cùng partition |
| `shipping_address` | Frozen UDT thông thường | Mỗi hoạt động có địa chỉ riêng; thay cả giá trị khi cập nhật |
| `labels` | `set<text>` | Không có phần tử trùng và không có thứ tự theo insertion |
| `metadata` | `map<text,text>` | Cặp key/value, thay thế một key không tác động key khác |
| `items` | `list<frozen<item_snapshot>>` | Thứ tự danh sách và trường UDT lồng nhau được bảo toàn |

Bài sử dụng `SimpleStrategy` với một replica **chỉ cho môi trường kiểm thử đơn giản**. Production phải thiết kế replication theo topology thực tế, thường là `NetworkTopologyStrategy`. Tên keyspace trong các câu ví dụ là cố định để dễ đọc; test chạy song song có thể cấp keyspace riêng cho từng suite.

### 2.2. Các bất biến cần được chứng minh

~~~mermaid
flowchart TD
    A["(tenant_id, customer_id)"] --> P["Một partition"]
    P --> S["customer_segment STATIC"]
    P --> D["default_address STATIC"]
    P --> C1["occurred_at t2 / activity_id B"]
    P --> C2["occurred_at t1 / activity_id A"]
    C1 --> U1["shipping_address, labels, metadata, items"]
    C2 --> U2["shipping_address, labels, metadata, items"]
    Q["Một partition khác"] --> S2["STATIC độc lập"]
~~~

Bộ kiểm thử phải chứng minh rằng:

- Đổi `customer_id` **hoặc** `tenant_id` chuyển sang partition khác.
- Đổi `occurred_at` hoặc `activity_id` tạo **khóa dòng khác**, không phải cập nhật primary key tại chỗ.
- Mọi dòng trong cùng partition nhìn thấy cùng một giá trị `customer_segment` và `default_address` hiện tại.
- UDT và collection của từng hoạt động không bị lẫn với dữ liệu hoạt động khác.
- Dữ liệu ánh xạ Java khớp với CQL ở đúng khóa, đúng kiểu và đúng độ chính xác mà Cassandra lưu.

## 3. Chuẩn bị integration test

### 3.1. Công cụ và phạm vi

Một bộ kiểm thử thường dùng JUnit 5, AssertJ, Spring Boot Test/Spring Data Cassandra, DataStax Java Driver và **Testcontainers Cassandra**. Có thể dùng `@DataCassandraTest` cho repository/mapping, hoặc `@SpringBootTest` khi cần toàn bộ cấu hình ứng dụng. Version của Spring Boot, Spring Data, Java Driver và Testcontainers phải tương thích nhau.

Cần có:

1. Cassandra chạy trong container, hoặc một cụm test cô lập có phiên bản phù hợp production.
2. Keyspace và schema được dựng **trước khi** khởi tạo repository cần truy cập bảng/UDT.
3. `CqlSession` do Spring quản lý hoặc dùng riêng cho câu CQL kiểm chứng.
4. Bộ dữ liệu nhỏ với **ít nhất hai partition, hai dòng trong một partition, hai dòng trùng timestamp**, cùng UDT/collection khác nhau.
5. Cơ chế dọn dữ liệu sau test bằng khóa biết trước hoặc keyspace/schema riêng; không xóa dữ liệu của môi trường dùng chung.

Ví dụ khung triển khai dựa trên Testcontainers và Java Driver:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
class ActivityCqlIntegrationTest {

    @Container
    static final CassandraContainer<?> cassandra =
        new CassandraContainer<>("cassandra:4.1");

    static CqlSession session;

    @BeforeAll
    static void connectAndCreateSchema() {
        session = CqlSession.builder()
            .addContactPoint(cassandra.getContactPoint())
            .withLocalDatacenter(cassandra.getLocalDatacenter())
            .build();

        // Tạo keyspace, UDT và bảng từ schema ở mục 2,
        // rồi seed dữ liệu riêng của từng ca kiểm thử.
        // Không dùng USE keyspace để thay đổi ngữ cảnh
        // của session đang được chia sẻ.
    }

    @AfterAll
    static void closeSession() {
        if (session != null) {
            session.close();
        }
    }

    @Test
    void canConnectToCassandra() {
        // Test thực tế sẽ chạy assertions ở các mục tiếp theo.
    }
}
~~~

Đây là **khung**, chưa phải class có thể chạy độc lập: phải thêm lệnh tạo schema, seed và assertion. Package/API Testcontainers có thể khác giữa các major version; ví dụ trên theo cách dùng phổ biến ở nhánh Testcontainers 1.x. Với Testcontainers 2.x, tra lại artifact và package tương ứng. Nên khóa phiên bản image Cassandra để test không thay đổi hành vi ngoài ý muốn theo thời gian.

Nếu tích hợp Spring Boot, cấu hình các thuộc tính `spring.cassandra.contact-points`, `spring.cassandra.port`, `spring.cassandra.local-datacenter`, `spring.cassandra.keyspace-name` và schema initialization cho đúng phiên bản Boot đang chạy. Testcontainers có thể cấp host/port động; không hard-code `localhost:9042`.

### 3.2. Dữ liệu seed có chủ ý

Thay vì seed hàng trăm dòng ngẫu nhiên, dùng dữ liệu sao cho mỗi dòng phân biệt được một tính chất:

| Bản ghi | Partition | Thời gian | Activity ID | Mục tiêu |
|---|---|---|---|---|
| `A1` | `(tenant-A, customer-X)` | 09:00:00.000 | UUID nhỏ hơn | Thứ tự khi trùng thời gian |
| `A2` | `(tenant-A, customer-X)` | 09:00:00.000 | UUID lớn hơn | Thứ tự khi trùng thời gian |
| `A3` | `(tenant-A, customer-X)` | 10:00:00.000 | UUID khác | Kiểm tra DESC theo thời gian |
| `B1` | `(tenant-A, customer-Y)` | 11:00:00.000 | UUID khác | Tách theo customer |
| `C1` | `(tenant-B, customer-X)` | 12:00:00.000 | UUID khác | Tách theo tenant dù cùng customer |

Dùng các UUID **cố định trong từng test** để biết chính xác thứ tự so sánh; không phụ thuộc vào UUID ngẫu nhiên có thể thay đổi giữa các lần chạy.

Khi tạo `Instant`, chọn các thời điểm tròn mili giây. Kiểu Cassandra `timestamp` lưu theo độ chính xác mili giây; so sánh một `Instant` có nanosecond bất kỳ với giá trị đọc lại có thể gây test sai vì mất độ chính xác.

Ví dụ:

~~~java
UUID tenantA = UUID.fromString(
    "11111111-1111-4111-8111-111111111111");
UUID customerX = UUID.fromString(
    "22222222-2222-4222-8222-222222222222");

Instant time9 = Instant.parse("2026-11-25T09:00:00.000Z");
Instant time10 = Instant.parse("2026-11-25T10:00:00.000Z");
~~~

Dùng timezone `UTC` làm chuẩn khi tạo test timestamp; không phụ thuộc múi giờ máy chạy CI.

### 3.3. Không phụ thuộc vào thứ tự và trạng thái giữa các test

Cassandra không bảo đảm thứ tự kết quả toàn cục ngoài cách truy cập đã được thiết kế. Test thứ tự chỉ nên kiểm tra trong một partition khi query áp dụng đúng clustering order. Mỗi test nên tự seed và dọn dữ liệu của mình hoặc chạy trên keyspace riêng; tránh dùng thứ tự chạy JUnit làm điều kiện tiên quyết.

Trong môi trường test một node, kết quả thường nhất quán ngay sau write thành công, nhưng đừng đưa giả định “mọi replica tức thời đồng bộ” vào một bài test multi-node. Với trường hợp có retry/timeout, kiểm tra theo một hạn chót có giới hạn thay vì `Thread.sleep` cố định và hy vọng hệ thống đã kịp cập nhật.

## 4. Kiểm thử mapping khóa chính ghép

### 4.1. Cấu trúc mapping Spring Data

Với khóa `((tenant_id, customer_id), occurred_at, activity_id)`, entity có thể được ánh xạ theo mô hình:

~~~java
import java.io.Serializable;
import java.time.Instant;
import java.util.UUID;
import org.springframework.data.cassandra.core.cql.Ordering;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyClass;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyColumn;
import org.springframework.data.cassandra.core.mapping.PrimaryKeyType;

@PrimaryKeyClass
public class ActivityKey implements Serializable {

    @PrimaryKeyColumn(
        name = "tenant_id",
        ordinal = 0,
        type = PrimaryKeyType.PARTITIONED)
    private UUID tenantId;

    @PrimaryKeyColumn(
        name = "customer_id",
        ordinal = 1,
        type = PrimaryKeyType.PARTITIONED)
    private UUID customerId;

    @PrimaryKeyColumn(
        name = "occurred_at",
        ordinal = 2,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.DESCENDING)
    private Instant occurredAt;

    @PrimaryKeyColumn(
        name = "activity_id",
        ordinal = 3,
        type = PrimaryKeyType.CLUSTERED,
        ordering = Ordering.ASCENDING)
    private UUID activityId;

    // Constructor(s), getter/setter và equals/hashCode
    // phải được hiện thực đầy đủ trong mã production.
}
~~~

~~~java
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("activity_by_customer")
public class ActivityByCustomer {

    @PrimaryKey
    private ActivityKey id;

    // Các cột khác xem mục 6.
    // Constructor(s), getter/setter theo mapping strategy.
}
~~~

~~~java
import org.springframework.data.cassandra.repository.CassandraRepository;

public interface ActivityRepository
        extends CassandraRepository<ActivityByCustomer, ActivityKey> {
}
~~~

Ở đây `ActivityKey` được cắt gọn để tập trung vào annotation; để mã chạy thật, cần hàm tạo và truy cập property tương thích Spring Data, cùng `equals/hashCode` so sánh **đủ bốn thành phần khóa**. Nếu dùng `record` hoặc immutable mapping, kiểm tra khả năng hỗ trợ của đúng phiên bản Spring Data đang dùng.

Một lỗi hay gặp là đưa hai cột partition vào hai vị trí không tương ứng schema CQL, hoặc quên đánh dấu `type = PARTITIONED` cho `customer_id`. Unit test chỉ kiểm tra annotation hiện diện không đủ; hãy chạy round-trip và truy vấn CQL để xác nhận thứ tự/key thực tế.

### 4.2. Ca test 1 — Truy vấn chỉ đọc một partition

Truy vấn hợp lệ:

~~~sql
SELECT occurred_at, activity_id, kind
FROM knowledge_test.activity_by_customer
WHERE tenant_id = ? AND customer_id = ?;
~~~

Assertion:

- Lấy đúng `A1`, `A2`, `A3`, không lẫn `B1` hay `C1`.
- `A3` (10:00) xuất hiện trước các dòng 09:00.
- Ở 09:00, `A1` và `A2` xuất hiện theo thứ tự tăng dần của `activity_id` nếu schema quy định `ASC`.
- Kết quả không thay đổi ý nghĩa khi test chạy lại với thứ tự INSERT khác nhau.

Java minh họa assertion bằng Java Driver và AssertJ:

~~~java
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

List<Row> rows = session.execute(
    SimpleStatement.builder("""
        SELECT activity_id
        FROM knowledge_test.activity_by_customer
        WHERE tenant_id = ? AND customer_id = ?
        """)
        .addPositionalValues(tenantA, customerX)
        .build()
).all();

assertThat(rows)
    .extracting(row -> row.getUuid("activity_id"))
    .containsExactly(idAt10, idAt9Smaller, idAt9Larger);
~~~

Đoạn test giả định dữ liệu `A1/A2/A3` đã được seed với các ID `idAt9Smaller`, `idAt9Larger`, `idAt10` tương ứng. Phần quan trọng là assertion về **thứ tự đọc thực tế**, không chỉ kiểm tra `size() == 3`.

### 4.3. Ca test 2 — Thiếu một thành phần partition key

Truy vấn dưới đây không thuộc mẫu truy vấn mà bảng được thiết kế để hỗ trợ:

~~~sql
-- Thiếu tenant_id trong composite partition key:
SELECT *
FROM knowledge_test.activity_by_customer
WHERE customer_id = ?;
~~~

Cassandra thông thường từ chối truy vấn không cung cấp đủ partition key nếu không có cơ chế truy cập phù hợp. Test cần xác nhận câu truy vấn này **không được dùng nhầm trong production**, không thêm `ALLOW FILTERING` để biến test thành xanh.

Nếu cần truy vấn “mọi tenant có customer X”, thiết kế thêm bảng/trục tra cứu phù hợp hoặc thay đổi hợp đồng API. Không nên sửa sai bằng cách để một truy vấn scan dữ liệu trên cả cluster.

### 4.4. Ca test 3 — Khóa đầy đủ phân biệt các dòng

Seed hai activity cùng `tenant_id`, `customer_id` và `occurred_at` nhưng khác `activity_id`.

Kỳ vọng:

- `findById(new ActivityKey(..., idA))` đọc đúng A.
- `findById(new ActivityKey(..., idB))` đọc đúng B.
- Ghi hai lần cùng **bốn giá trị khóa** là upsert cùng logical row theo CQL, không sinh thêm dòng.
- Đổi một thành phần primary key là thao tác tạo dòng mới theo khóa khác; nếu muốn “di chuyển”, ứng dụng phải xóa khóa cũ có chủ đích.

Một phép kiểm tra chỉ nhìn cột `kind` có thể vô tình pass nếu hai activity có giá trị giống nhau. Hãy kiểm tra ID, timestamp và ít nhất một payload khác biệt.

### 4.5. Ca test 4 — Mapping equals/hashCode và cache

Composite key dùng làm định danh repository và thường được đưa vào `Map`/`Set` hoặc cache. Kiểm thử:

~~~java
ActivityKey k1 = new ActivityKey(
    tenantA, customerX, time9, idAt9Smaller);
ActivityKey k2 = new ActivityKey(
    tenantA, customerX, time9, idAt9Smaller);
ActivityKey k3 = new ActivityKey(
    tenantA, customerX, time9, idAt9Larger);

assertThat(k1).isEqualTo(k2);
assertThat(k1.hashCode()).isEqualTo(k2.hashCode());
assertThat(k1).isNotEqualTo(k3);
~~~

Ví dụ giả định có constructor đủ bốn tham số. Nếu key mutable và thay đổi sau khi đưa vào `HashMap`, kết quả lookup có thể không ổn định; cân nhắc immutable key. Đây là unit test hợp lý, nhưng vẫn cần integration test để kiểm chứng CQL mapping.

## 5. Kiểm thử static column đúng phạm vi partition

### 5.1. Tính chất cần hiểu

Trong Cassandra, `static column` có một giá trị logic ở **cấp partition**, không phải giá trị riêng của từng dòng clustering. Vì thế `customer_segment` của A1, A2, A3 được đọc là giống nhau nếu cả ba thuộc `(tenant-A, customer-X)`. Khách hàng Y hoặc tenant B có static value khác.

~~~sql
UPDATE knowledge_test.activity_by_customer
SET customer_segment = 'PREMIUM'
WHERE tenant_id = ? AND customer_id = ?;
~~~

Đây là **cập nhật static column với điều kiện partition key**, không cần `occurred_at` và `activity_id`. Trái lại, cập nhật cột thông thường như `kind` cần khóa clustering thích hợp để xác định dòng.

### 5.2. Ca test 5 — Một lần ghi, nhiều dòng đọc cùng giá trị

**Arrange:** seed A1/A2/A3 cùng partition, rồi ghi `customer_segment = PREMIUM` bằng câu CQL trên.

**Act:** đọc ba dòng theo composite partition key.

**Assert:**

- Cả A1/A2/A3 đều trả `PREMIUM`.
- Không có thêm một dòng hoạt động mới do thao tác chỉ cập nhật static.
- `kind` và `items` của từng dòng giữ nguyên.

~~~sql
SELECT activity_id, customer_segment, kind
FROM knowledge_test.activity_by_customer
WHERE tenant_id = ? AND customer_id = ?;
~~~

Sau đó cập nhật static thành `STANDARD` và đọc lại, cả ba dòng phải cùng nhìn thấy `STANDARD`. Test xác nhận **hành vi chia sẻ**, không kiểm tra mỗi entity ghi static riêng rồi hy vọng cùng giá trị.

### 5.3. Ca test 6 — Partition khác không bị ảnh hưởng

Seed ba partition:

- P1 = `(tenant-A, customer-X)`, segment `PREMIUM`.
- P2 = `(tenant-A, customer-Y)`, segment `BASIC`.
- P3 = `(tenant-B, customer-X)`, segment `PARTNER`.

Sau khi cập nhật P1 thành `STANDARD`, đọc P2/P3 và xác nhận vẫn là `BASIC`/`PARTNER`. Đây là ca có giá trị cao: chỉ một tenant hoặc customer khác đủ phát hiện lỗi binding thiếu thành phần của composite partition key.

### 5.4. Ca test 7 — Trường static trong Spring Data

Ở lớp entity, trường static cần được ánh xạ nhất quán với schema, ví dụ:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.StaticColumn;

@Table("activity_by_customer")
public class ActivityByCustomer {

    @PrimaryKey
    private ActivityKey id;

    @StaticColumn("customer_segment")
    private String customerSegment;

    @StaticColumn("default_address")
    private ShippingAddress defaultAddress;

    @Column("kind")
    private String kind;

    // Các trường payload khác và accessor/constructor.
}
~~~

Khi dùng `repository.save(entity)` hoặc `CassandraTemplate.insert/update`, cần kiểm thử đường ghi thật. Không nên cho rằng ghi một dòng có property static bằng `null` luôn vô hại: cách mapper tạo CQL và xử lý null/unset tùy API/phiên bản có thể ảnh hưởng static value của cả partition. Trong integration test, chạy đường ghi với payload thiếu static và xác nhận trạng thái sau khi đọc lại bằng CQL.

**Ca kiểm thử đề xuất:**

1. Seed static `customer_segment = PREMIUM`.
2. Ghi activity mới bằng đường repository với field static không được cung cấp.
3. Đọc lại tất cả activity trong partition.
4. Xác nhận static còn `PREMIUM` nếu đây là hợp đồng ứng dụng mong muốn.
5. Nếu phát hiện mapper tạo lệnh xóa/ghi null ngoài ý muốn, đổi cách ghi để chỉ mutate cột cần thiết (ví dụ câu CQL rõ ràng hoặc cơ chế insert/update có kiểm soát).

Không lấy kết quả của `save(entity)` làm bằng chứng rằng static column được bảo toàn; **đọc lại Cassandra**.

### 5.5. Ca test 8 — Xóa dòng và xóa static là hai việc khác nhau

~~~sql
DELETE FROM knowledge_test.activity_by_customer
WHERE tenant_id = ?
  AND customer_id = ?
  AND occurred_at = ?
  AND activity_id = ?;
~~~

Đây là thao tác xóa **một clustering row**. Nếu còn các activity cùng partition, `customer_segment` phải vẫn đọc được ở chúng. Xóa nhiều clustering row cũng không tương đương với xóa toàn partition.

Muốn xóa riêng static:

~~~sql
DELETE customer_segment
FROM knowledge_test.activity_by_customer
WHERE tenant_id = ? AND customer_id = ?;
~~~

Sau đó đọc lại các activity, `customer_segment` không còn giá trị (thường là `null` ở tầng Java nếu schema/mapping cho phép). Dữ liệu `kind` và `items` của từng activity phải còn nguyên.

Có thể tồn tại **partition chỉ chứa static value mà chưa có clustering row**. Hành vi kết quả `SELECT` và cách mapper materialize “static-only row” cần được kiểm thử theo phiên bản Cassandra/Spring Data đang sử dụng; không mặc định đó là một activity có ID hợp lệ. Nếu ứng dụng cần một đối tượng hồ sơ khách hàng độc lập, cân nhắc bảng riêng theo khóa partition thay vì dựa vào pseudo-row của bảng activity.

### 5.6. Static column và cạnh tranh ghi

Hai client ghi `customer_segment` cho cùng partition có thể cạnh tranh theo timestamp CQL/last-write-wins. Cassandra không tự đảm bảo segment được cập nhật theo “request đến sau” tại cấp nghiệp vụ khi hai request song song.

Test có thể cho hai client gửi lệnh khác nhau rồi kiểm tra hành vi ghi/đọc thực tế, nhưng **không dựa vào thứ tự luồng Java** làm đảm bảo kết quả cuối nếu không có điều kiện đồng bộ. Nếu segment là giá trị cần kiểm soát phiên bản, thiết kế thêm điều kiện/nguồn dữ liệu chuẩn phù hợp. Test race condition phải có điều kiện kỳ vọng rõ ràng trước khi viết assertion.

## 6. Kiểm thử nested UDT và collection

### 6.1. Từ Java object sang CQL

UDT giúp biểu diễn một cấu trúc có tên như địa chỉ hoặc vị trí. Trong ví dụ:

~~~text
shipping_address
  street: text
  city: text
  geo: geo_point
    lat: double
    lon: double

item_snapshot
  sku: text
  quantity: int
  destination: shipping_address
    geo: geo_point
~~~

`shipping_address` chứa `frozen<geo_point>`; `item_snapshot` chứa `frozen<shipping_address>`; cột `items` là `list<frozen<item_snapshot>>`. Cấu trúc lồng nhau đủ sâu để phát hiện việc bỏ sót field hoặc codec không biết kiểu bên trong.

Spring Data Cassandra có thể mapping UDT bằng `@UserDefinedType` và các field tương ứng:

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.UserDefinedType;

@UserDefinedType("geo_point")
public class GeoPoint {

    @Column("lat")
    private Double lat;

    @Column("lon")
    private Double lon;

    // Constructor(s) và accessor.
}

@UserDefinedType("shipping_address")
public class ShippingAddress {

    @Column("street")
    private String street;

    @Column("city")
    private String city;

    @Column("geo")
    private GeoPoint geo;

    // Constructor(s) và accessor.
}

@UserDefinedType("item_snapshot")
public class ItemSnapshot {

    @Column("sku")
    private String sku;

    @Column("quantity")
    private Integer quantity;

    @Column("destination")
    private ShippingAddress destination;

    // Constructor(s) và accessor.
}
~~~

Và entity:

~~~java
@Table("activity_by_customer")
public class ActivityByCustomer {

    @PrimaryKey
    private ActivityKey id;

    @StaticColumn("customer_segment")
    private String customerSegment;

    @StaticColumn("default_address")
    private ShippingAddress defaultAddress;

    @Column("kind")
    private String kind;

    @Column("shipping_address")
    private ShippingAddress shippingAddress;

    @Column("labels")
    private Set<String> labels;

    @Column("metadata")
    private Map<String, String> metadata;

    @Column("items")
    private List<ItemSnapshot> items;

    // Constructor(s) và accessor.
}
~~~

Các class trên trình bày **hình dạng mapping**, không lặp lại getter/setter để tập trung vào dữ liệu. Trong dự án thật, phải đảm bảo entity/UDT có cách khởi tạo và property access tương thích phiên bản Spring Data. Tùy cấu hình converter, nested UDT hoặc collection UDT có thể cần `@CassandraType` hay custom conversion; test phải chứng minh mapping thực sự chạy được, không chỉ compile.

### 6.2. Ca test 9 — Round-trip UDT lồng nhau

Tạo activity với địa chỉ:

~~~text
shipping_address:
  street: "21 Nguyen Hue"
  city: "Ho Chi Minh City"
  geo:
    lat: 10.776
    lon: 106.701
~~~

Ghi bằng repository, sau đó dùng **CQL đọc trực tiếp** và dùng repository đọc lại. Kỳ vọng:

- `street`, `city` đúng.
- `geo.lat` và `geo.lon` không bị đổi hoặc mất.
- Kiểu `double` được so sánh với epsilon phù hợp nếu xử lý số thực có phép biến đổi; với round-trip cùng primitive double không biến đổi có thể so sánh chính xác các giá trị được chuẩn hóa.
- Đọc repository trả object nested đúng và độc lập với object của activity khác.

Để kiểm tra tại tầng Driver thay vì chỉ dựa vào mapper:

~~~java
import com.datastax.oss.driver.api.core.data.UdtValue;

Row row = session.execute(
    SimpleStatement.builder("""
        SELECT shipping_address
        FROM knowledge_test.activity_by_customer
        WHERE tenant_id = ? AND customer_id = ?
          AND occurred_at = ? AND activity_id = ?
        """)
        .addPositionalValues(tenantA, customerX, time9, idAt9Smaller)
        .build()
).one();

assertThat(row).isNotNull();

UdtValue address = row.getUdtValue("shipping_address");
assertThat(address).isNotNull();
assertThat(address.getString("street"))
    .isEqualTo("21 Nguyen Hue");

UdtValue geo = address.getUdtValue("geo");
assertThat(geo.getDouble("lat")).isEqualTo(10.776);
assertThat(geo.getDouble("lon")).isEqualTo(106.701);
~~~

Khi một giá trị bên trong có thể null, trước khi gọi getter primitive như `getDouble` cần kiểm tra `isNull`; primitive getter không thay thế bài test cho null.

### 6.3. Ca test 10 — Danh sách UDT giữ đúng thứ tự

Một activity gồm hai item:

~~~text
items:
  - sku: "SKU-002"
    quantity: 2
    destination:
      street: "A"
      city: "Da Nang"
      geo: {lat: 16.05, lon: 108.20}
  - sku: "SKU-001"
    quantity: 1
    destination:
      street: "B"
      city: "Ha Noi"
      geo: {lat: 21.03, lon: 105.85}
~~~

Sau round-trip:

- `items.size() == 2`.
- Phần tử **đầu tiên vẫn là SKU-002**, phần tử thứ hai là SKU-001.
- `quantity` và `destination.geo` của từng item đúng.
- Item trong activity khác không bị trộn vào danh sách đang đọc.

Bộ test không nên sắp xếp hai item trước khi so sánh, vì như vậy sẽ che mất lỗi mất thứ tự của `list`.

### 6.4. Ca test 11 — Set không có ý nghĩa thứ tự insertion

Với `labels set<text>`, ghi danh sách từ Java có giá trị `["paid", "priority", "paid"]` sau khi chuẩn hóa thành `Set` sẽ chỉ còn hai phần tử. Assertion đúng là **tập phần tử**:

~~~java
assertThat(actualLabels)
    .containsExactlyInAnyOrder("paid", "priority");
~~~

Không dùng `containsExactly("paid", "priority")` chỉ vì thứ tự insert ở test trông ổn. Cassandra `set` không định nghĩa thứ tự theo insertion như `list`. Nếu cần thứ tự có ý nghĩa nghiệp vụ, hãy dùng kiểu dữ liệu khác.

### 6.5. Ca test 12 — Map kiểm tra key/value và cập nhật một phần

Với `metadata map<text,text>`:

~~~text
"source"  -> "mobile"
"locale"  -> "vi-VN"
"campaign" -> "black-friday"
~~~

Kiểm tra đủ key/value, đồng thời phân biệt key không tồn tại với key có giá trị khác. Khi muốn cập nhật một phần map, CQL hỗ trợ cú pháp phù hợp với non-frozen map:

~~~sql
UPDATE knowledge_test.activity_by_customer
SET metadata['locale'] = 'en-US'
WHERE tenant_id = ?
  AND customer_id = ?
  AND occurred_at = ?
  AND activity_id = ?;
~~~

Sau đó đọc lại, `locale` đổi còn `source` và `campaign` vẫn giữ nguyên. Đây là test quan trọng để phân biệt **cập nhật một phần map không frozen** với **thay cả UDT frozen**.

### 6.6. Ca test 13 — Frozen UDT được thay như một giá trị

`shipping_address frozen<shipping_address>` được lưu như một giá trị đơn. Muốn đổi `city`, ứng dụng phải tạo giá trị UDT mới với **đủ nội dung muốn giữ** và ghi lại toàn bộ cột:

~~~sql
UPDATE knowledge_test.activity_by_customer
SET shipping_address = ?
WHERE tenant_id = ?
  AND customer_id = ?
  AND occurred_at = ?
  AND activity_id = ?;
~~~

Không viết test giả định có thể cập nhật an toàn một field con của `frozen` UDT bằng cú pháp partial update. Hợp đồng của dữ liệu frozen là **thay toàn bộ giá trị**. Nếu tạo địa chỉ mới chỉ có `city`, các field không được mang theo có thể thành null.

Ca test nên:

1. Seed địa chỉ đầy đủ gồm `street`, `city`, `geo`.
2. Ghi một địa chỉ mới có `city` khác và giữ nguyên các field còn lại.
3. Đọc lại toàn bộ địa chỉ, xác nhận không mất `street` hoặc `geo`.
4. Kiểm tra mapping trả về object mới đúng như CQL.

Trong hệ thống có ghi đồng thời, hai thao tác thay địa chỉ bằng hai UDT frozen có thể ghi đè nhau; kiểm thử lost update cần cơ chế điều kiện riêng nếu yêu cầu nghiệp vụ không cho mất thông tin.

### 6.7. Ca test 14 — Static UDT và UDT của từng dòng không bị nhầm

Trong schema có hai cột cùng kiểu UDT nhưng khác phạm vi:

- `default_address` là `STATIC` và dùng chung cho partition.
- `shipping_address` là cột thường, khác nhau giữa từng activity.

Seed A1 có shipping address HCM, A2 có shipping address Hà Nội; default address của partition là Đà Nẵng. Sau khi đổi default address thành Huế:

- Cả A1 và A2 đều thấy `default_address = Huế`.
- `shipping_address` của A1 vẫn là HCM.
- `shipping_address` của A2 vẫn là Hà Nội.
- Các partition khác không bị đổi default address.

Ca này bắt được cả lỗi mapping sai annotation và lỗi cập nhật sai khóa CQL.

### 6.8. Ca test 15 — Null, collection rỗng và trường UDT tùy chọn

Ít nhất nên kiểm tra các tình huống sau:

| Dữ liệu đầu vào | Mục đích | Assertion phù hợp |
|---|---|---|
| `geo = null` trong địa chỉ | Field con tùy chọn | Đọc lại không gây lỗi converter; property là null nếu đó là hợp đồng |
| `shipping_address = null` | Không có toàn bộ UDT | Không tự tạo object “rỗng” trừ khi mapper được cấu hình như vậy |
| `items = []` | Không có item | Đọc không có item, không tự sinh item giả |
| `labels = empty set` | Không có label | Không phụ thuộc vào thứ tự hay giá trị hiển thị riêng cho empty |
| `metadata` thiếu key `locale` | Key không tồn tại | `containsKey("locale")` là false |
| `items` có UDT với một field null | Nested value chưa đầy đủ | Giữ các field hợp lệ và cách xử lý null đã định |

Cassandra/Driver có thể **không giữ được phân biệt null với collection rỗng theo cách ứng dụng kỳ vọng** trong mọi tổ hợp schema, version và thao tác ghi. Không viết một assertion rằng `null` và `[]` luôn được bảo toàn khác nhau mà chưa xác minh hành vi thực tế. Nếu nghiệp vụ cần phân biệt hai trạng thái, cân nhắc thêm cột trạng thái rõ ràng.

### 6.9. Ca test 16 — Khác biệt giữa Java type và CQL type

Một số cặp dễ gây lỗi:

| CQL | Java thường dùng | Cần kiểm tra |
|---|---|---|
| `uuid` | `UUID` | Không chuyển thành string làm mất kiểu trong key |
| `timestamp` | `Instant` | Độ chính xác mili giây, timezone UTC |
| `double` | `Double` | Null và độ chính xác số thực |
| `int` | `Integer` | Tránh null-unboxing thành primitive |
| `list<frozen<UDT>>` | `List<ItemSnapshot>` | Nested converter, thứ tự và phần tử null |
| `set<text>` | `Set<String>` | Tính duy nhất, không dựa vào thứ tự |
| `map<text,text>` | `Map<String,String>` | Key/value và biến đổi một phần map |

Nếu môi trường dùng custom converters, cần test hai chiều `WritingConverter` và `ReadingConverter`. Với dữ liệu có decimal hoặc ngày tháng trong UDT tương lai, bổ sung test độ chính xác/scale và quy tắc timezone tương ứng. Các test “lưu rồi đọc lại” bằng cùng converter chưa chắc phát hiện một quy ước sai trên cả hai chiều, vì vậy cần thêm **CQL readback** hoặc fixture độc lập.

## 7. Kiểm thử ở hai lớp: repository và CQL

Một mẫu test đáng tin cậy gồm hai pha kiểm chứng khác nhau.

### 7.1. Pha A — Ghi qua Spring Data, đọc qua CQL

~~~mermaid
sequenceDiagram
    participant T as JUnit Test
    participant R as Repository / CassandraTemplate
    participant C as Apache Cassandra
    participant D as CqlSession
    T->>R: save(entity với composite key + UDT)
    R->>C: CQL write
    T->>D: SELECT bằng khóa đã biết
    D->>C: CQL read
    C-->>D: Row + UDT + static
    D-->>T: CQL values
    Note over T: Assert khóa, static, nested fields
~~~

Mục đích: kiểm tra Spring Data có tạo đúng CQL và serialize đúng field hay không. Đọc bằng driver tránh việc lỗi serialize và deserialize “đối xứng” làm test round-trip bằng repository vẫn xanh.

### 7.2. Pha B — Ghi qua CQL, đọc qua Spring Data

Seed trực tiếp một row chứa UDT và collection bằng prepared statement/`UdtValue`; sau đó gọi:

~~~java
Optional<ActivityByCustomer> actual =
    repository.findById(new ActivityKey(
        tenantA, customerX, time9, idAt9Smaller));

assertThat(actual).isPresent();
assertThat(actual.orElseThrow().getId().getTenantId())
    .isEqualTo(tenantA);
~~~

Cần thêm assertion về `getCustomerSegment()`, `getShippingAddress()`, `getItems()` và `getMetadata()`. Đây là phép kiểm tra **deserialization thực tế**, độc lập cách Spring Data ghi dữ liệu.

Java Driver cho phép dựng nested UDT từ metadata:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import com.datastax.oss.driver.api.core.data.UdtValue;
import com.datastax.oss.driver.api.core.type.UserDefinedType;

UserDefinedType geoType = session.getMetadata()
    .getKeyspace(CqlIdentifier.fromCql("knowledge_test"))
    .orElseThrow()
    .getUserDefinedType(CqlIdentifier.fromCql("geo_point"))
    .orElseThrow();

UdtValue geoValue = geoType.newValue()
    .setDouble("lat", 10.776)
    .setDouble("lon", 106.701);

// Tạo shipping_address.newValue() và setUdtValue("geo", geoValue),
// rồi bind vào prepared statement cho cột frozen UDT.
~~~

Không tự ghép chuỗi đại diện UDT vào SQL khi dữ liệu chứa ký tự đặc biệt; sử dụng prepared statement và codec đúng kiểu để tránh lỗi quoting.

### 7.3. Kiểm tra CassandraTemplate

`CassandraTemplate` cung cấp đường truy cập khác repository. Test nên chọn những operation mà ứng dụng sử dụng thật, ví dụ:

- `insert` entity với composite key mới.
- `selectOne` hoặc `select` theo query có đủ partition key.
- `update` đúng một cột non-static ở khóa đầy đủ.
- Cập nhật static bằng CQL rõ ràng rồi xác minh entity đọc lại.
- Chuyển đổi UDT khi dùng custom converters hoặc `MappingCassandraConverter`.

Không cần lặp toàn bộ ma trận test cho cả repository và template nếu hai đường dùng cùng mapping. Tập trung vào những hành vi có nguy cơ khác nhau: cách sinh CQL update, xử lý null/unset, binding khóa và conversion.

## 8. Tránh test giả do dữ liệu/transaction/môi trường

### 8.1. Một container không tự chứng minh tính nhất quán phân tán

Testcontainers một Cassandra node rất phù hợp để kiểm tra:

- Schema, primary key và clustering order.
- Static column semantics.
- UDT codecs, converter và query validity.
- Các thao tác insert, update, delete và paging cơ bản.

Nhưng nó **không chứng minh** ứng dụng đã xử lý replica lag, network partition, consistency level trong multi-DC hoặc timeout khi replica bị lỗi. Các yêu cầu đó cần bài integration/chaos test riêng trên topology tương ứng. Trong test một replica, đừng suy luận rằng `LOCAL_QUORUM` có cùng đặc tính vận hành như cluster nhiều replica.

### 8.2. Test không nên dùng transaction rollback giả định

Các test Spring Boot quen thuộc với `@Transactional` và cơ chế rollback cuối test trong cơ sở dữ liệu quan hệ. Không được mặc định cơ chế đó sẽ đưa Cassandra về trạng thái ban đầu.

Thay vào đó:

- Sử dụng keyspace riêng hoặc khóa test có UUID cố định/duy nhất.
- Xóa dữ liệu theo đúng partition/full primary key sau test khi cần.
- Nếu `TRUNCATE`, chỉ dùng trên bảng **dành riêng** cho suite và tránh suite khác đang chạy chung.
- Không để các test chạy song song tranh cùng `static column` trong cùng partition.

Một test xanh nhờ dữ liệu của test trước là false positive. Một test đỏ do test khác thay static cùng partition là lỗi cô lập fixture, không nhất thiết là lỗi mapping.

### 8.3. DDL và schema metadata

Khi tạo UDT rồi tạo bảng tham chiếu UDT, phải chờ schema được các node nhận biết đủ để driver thấy metadata cần thiết. Với cluster nhiều node, schema agreement có thể cần thời gian. Nếu test vừa ALTER TYPE rồi lập tức đọc metadata cũ, lỗi có thể đến từ trạng thái schema chưa đồng bộ.

Không sửa UDT chung giữa các test song song. Với kịch bản schema evolution, chạy suite riêng:

1. Tạo UDT với các field ban đầu.
2. Ghi fixture cũ.
3. `ALTER TYPE` thêm field tùy chọn.
4. Xác nhận client/mapping phiên bản mới đọc được cả dữ liệu cũ lẫn mới theo hợp đồng.
5. Bảo đảm container/metadata được refresh khi cần.

Không tự động “chứng minh tương thích ngược” chỉ bằng việc `ALTER TYPE` chạy thành công.

## 9. Ca kiểm thử paging và tính ổn định của khóa ghép

Composite clustering key liên quan trực tiếp đến **paging**. Nếu truy vấn danh sách hoạt động theo partition, test cần bảo đảm toàn bộ page đọc về đúng thứ tự và không thiếu/trùng dòng trong **tập dữ liệu không thay đổi**.

~~~java
SimpleStatement statement = SimpleStatement.builder("""
    SELECT occurred_at, activity_id, kind
    FROM knowledge_test.activity_by_customer
    WHERE tenant_id = ? AND customer_id = ?
    """)
    .addPositionalValues(tenantA, customerX)
    .setPageSize(2)
    .build();

ResultSet result = session.execute(statement);

// Với paging ở Java Driver, iterator có thể tự lấy thêm page.
// Dùng getAvailableWithoutFetching() / paging state khi cần
// kiểm soát ranh giới page để kiểm thử API phân trang.
List<Row> allRows = result.all();

assertThat(allRows).hasSize(5);
~~~

Ví dụ chỉ kiểm tra số lượng; bài test đầy đủ cần assert từng `(occurred_at, activity_id)` theo thứ tự kỳ vọng. Để kiểm tra **đường paging thực sự**, dùng API paging state thích hợp của driver đang chạy, yêu cầu từng page và xác nhận không thiếu/trùng khóa. Đừng nhầm `setPageSize(2)` với giới hạn tổng kết quả hai dòng: Java Driver có thể tự fetch các page sau.

Với dữ liệu có concurrent insert/delete, Cassandra không cung cấp snapshot isolation cho một loạt truy vấn paging. Không viết assertion rằng tất cả page tạo thành một ảnh chụp bất biến nếu cùng lúc có ghi. Test paging nhất quán cần dữ liệu cố định; tình huống concurrent write phải có hợp đồng khác.

## 10. Kiểm thử trường hợp lỗi và schema xấu

Một số ca âm nên được kiểm thử vì giúp phát hiện lỗi cấu hình sớm:

| Ca âm | Tác nhân | Kết quả cần kiểm chứng |
|---|---|---|
| Truy vấn thiếu một phần partition key | `WHERE customer_id = ?` | Bị từ chối hoặc không được cho phép ở lớp ứng dụng |
| Mapped key sai cột | Sai tên/ordinal/type | Fail khi thao tác với schema thực hoặc có assertion schema metadata |
| Khóa thiếu thành phần | Entity ID null/không đầy đủ | Không ghi ra một dòng hợp lệ; lỗi rõ, không âm thầm ghép sai |
| Ghi một cột thường chỉ với partition key | `UPDATE kind = ?` không đủ khóa clustering | Không được tạo một “activity” mơ hồ |
| Frozen UDT cập nhật con | Muốn mutate `shipping_address.city` trực tiếp | Không được coi như partial update hợp lệ cho frozen value |
| Converter thiếu nested UDT | `List<ItemSnapshot>` không serialize được | Test fail ở tầng mapper thay vì chỉ assert Java object |
| Static bị cập nhật ngoài ý muốn | `save` row mới mang static null | Phát hiện qua CQL readback toàn partition |
| Dùng `ALLOW FILTERING` che khóa sai | Scan nhiều partition | Test query contract ngăn truy vấn ngoài thiết kế |
| Timestamp có nanos | `Instant` chính xác hơn mili giây | Chuẩn hóa hoặc kiểm tra round-trip theo precision CQL |
| Test chia sẻ partition | Hai test cùng thay `customer_segment` | Tách fixture và không phụ thuộc thứ tự chạy |

Nếu ứng dụng cần kiểm tra schema tự động, có thể đọc driver metadata rồi assert cấu trúc partition key, clustering column, clustering order, static column và CQL types. Đây là một lớp kiểm chứng bổ sung hữu ích khi nhiều phiên bản schema tồn tại trong pipeline triển khai.

## 11. Kiểm thử giới hạn hiệu năng gắn với thiết kế bảng

Mục tiêu chính của bài là **đúng hành vi**, nhưng một số test có thể phát hiện truy vấn truy cập sai phạm vi:

1. **Query contract:** mọi truy vấn danh sách chứa đủ `tenant_id` + `customer_id`. Khi có sắp xếp, chỉ dựa trên clustering order được hỗ trợ.
2. **Page size:** xác nhận controller/service không mặc định tải toàn bộ partition; driver có thể fetch thêm page khi iterator duyệt hết.
3. **Kích thước partition:** dữ liệu phát triển theo số activity của một khách hàng; nếu partition quá lớn, cần thiết kế bucket theo thời gian và viết lại test khóa tương ứng.
4. **Độ lớn nested UDT:** list chứa rất nhiều item làm row lớn, có thể tác động đọc/ghi và compaction. Cần giới hạn payload hợp đồng và kiểm thử với dữ liệu biên.
5. **Static write contention:** nhiều cập nhật segment của cùng một khách hàng có thể tranh trên một partition; theo dõi latency và luật cập nhật cạnh tranh.
6. **Tombstone khi xóa/thay UDT:** khi cập nhật thường xuyên field frozen hoặc xóa collection, số tombstone có thể tăng; hiệu năng cần đo trong môi trường có dữ liệu và compaction phù hợp.

Test hiệu năng nên ghi rõ phần cứng, số node, replication factor, quy mô dữ liệu, consistency level, warmup, latency p95/p99 và mức đồng thời. Tránh một assertion cứng “query phải nhanh hơn 5 ms” trên CI container, vì nó dễ thất bại vì tài nguyên hệ thống và không phản ánh bottleneck sản xuất. Dùng đo benchmark tách biệt để xác nhận mục tiêu vận hành.

## 12. Ma trận kiểm thử tối thiểu cho dự án

| ID | Nhóm | Test | Bằng chứng hoàn thành |
|---|---|---|---|
| K1 | Composite key | Đủ hai partition key, đọc đúng tập | Không lẫn tenant/customer |
| K2 | Composite key | `occurred_at DESC`, `activity_id ASC` | Thứ tự chính xác kể cả trùng timestamp |
| K3 | Composite key | Hai activity cùng timestamp khác ID | Hai dòng tồn tại và lookup độc lập |
| K4 | Composite key | Ghi trùng full key | Upsert cùng dòng, không sinh thêm |
| K5 | Composite key | Truy vấn thiếu partition key | Fail đúng quy tắc, không `ALLOW FILTERING` |
| S1 | Static column | Cập nhật một partition | Tất cả dòng trong partition đọc cùng static |
| S2 | Static column | Partition khác | Không bị ảnh hưởng |
| S3 | Static column | Xóa clustering row | Static và các dòng còn lại giữ nguyên |
| S4 | Static column | Xóa riêng static | Cột static mất giá trị, cột thường giữ nguyên |
| S5 | Static column | Spring Data save với static thiếu | Không vô tình xóa hoặc ghi sai theo contract |
| U1 | Nested UDT | Ghi qua Spring, đọc CQL | Đủ các field và nested geo |
| U2 | Nested UDT | Ghi CQL, đọc Spring | Converter đúng cả hai chiều |
| U3 | Collection | List UDT hai item | Đúng thứ tự và nested fields |
| U4 | Collection | Set và map | Đúng tính duy nhất và key/value |
| U5 | Frozen UDT | Thay địa chỉ nguyên khối | Không mất trường con cần bảo toàn |
| U6 | Null/empty | Field tùy chọn và collection rỗng | Contract đọc rõ ràng |
| P1 | Paging | Đọc nhiều page ở một partition | Không thiếu/trùng trong fixture ổn định |
| E1 | Environment | Mỗi test cô lập dữ liệu | Không phụ thuộc thứ tự chạy |
| E2 | Schema | Metadata cột/key/type | Schema thực khớp mô hình mapping |

Không nhất thiết chạy mọi ca ở mỗi tầng test. Ví dụ K1-K5 và S1-S4 phù hợp test CQL thực, U1-U6 hợp với hai chiều Spring/Driver; S5 kiểm tra đường repository/template đang dùng. Mỗi assertion nên được viết để thất bại nếu một lỗi cụ thể xảy ra.

## 13. Quy trình áp dụng từng bước

### Bước 1 — Xác định truy vấn nghiệp vụ

Ví dụ “lấy 20 hoạt động mới nhất của khách hàng trong một tenant”. Viết câu CQL truy cập bằng `tenant_id + customer_id`, xác định trường nào dùng sắp xếp và trường nào cần hiển thị.

### Bước 2 — Khóa schema và mapping

Ghi rõ:

- Cặp partition key, thứ tự clustering và phần tie-breaker.
- Cột nào static.
- Cột nào UDT, cột nào collection, vị trí `frozen`.
- Type conversion giữa Java và Cassandra.

Dựng schema bằng migration hoặc lệnh test được kiểm soát, không để entity tự tạo ra một bảng không giống production mà test vẫn xanh.

### Bước 3 — Tạo fixture tối thiểu có khả năng phân biệt lỗi

Hai partition là chưa đủ nếu cần phát hiện rò giữa tenant/customer; dùng ba partition như bảng ở mục 3.2. Có nhiều dòng trong một partition để phát hiện sai static, cùng timestamp để phát hiện sai tie-breaker và ít nhất hai item UDT để phát hiện lỗi thứ tự.

### Bước 4 — Viết assertion CQL trước

Xác nhận partition boundary, clustering order, static scope và UDT values ở dữ liệu gốc. Khi những bất biến này pass, triển khai test đường Spring Data để phát hiện lỗi mapping/converter.

### Bước 5 — Thêm test âm và null handling

Thử thiếu khóa, field null, empty collection, frozen replacement, mapper ghi static thiếu và CQL sai contract. Nếu behavior phụ thuộc phiên bản, ghi rõ behavior đã quan sát và yêu cầu ứng dụng cần.

### Bước 6 — Chạy riêng test đồng thời và hiệu năng

Cạnh tranh cập nhật static, write timeout, nhiều page và partition lớn là bài test chuyên biệt; không trộn chúng vào test mapping cơ bản khiến suite chậm, khó chẩn đoán và thất thường.

## 14. Bài tập thực hành

Cho khóa:

~~~text
PRIMARY KEY ((tenant_id, customer_id), occurred_at, activity_id)
CLUSTERING ORDER BY (occurred_at DESC, activity_id ASC)
~~~

Trong partition `(T1, C1)` có ba activity: E1 lúc 08:00, E2 lúc 09:00, E3 lúc 09:00; `activity_id(E2)` nhỏ hơn `activity_id(E3)`. Cả ba đang thấy `customer_segment = BASIC`. E1 có hai item dạng UDT lồng nhau; E2 có set nhãn `{"vip", "mobile"}`.

**Yêu cầu:**

1. Viết thứ tự các activity trả về khi query partition này.
2. Nếu chỉ cập nhật `customer_segment = VIP` với `WHERE tenant_id = T1 AND customer_id = C1`, những activity nào phải nhìn thấy `VIP`?
3. Nếu tạo activity E4 thuộc `(T2, C1)`, E4 có tự thừa hưởng `VIP` không?
4. Nếu xóa E2 theo đầy đủ primary key, E1 và E3 còn thấy `VIP` không?
5. Nếu muốn sửa `geo.lon` trong `shipping_address frozen<shipping_address>` của E1, cần thay phần nào của dữ liệu?
6. Với `labels set<text>`, có nên khẳng định vị trí của `"vip"` đứng trước `"mobile"` không?
7. Bộ test nào sẽ phát hiện trường hợp converter ghi sai `items[1].destination.geo` mà repository đọc sai theo cùng một cách?

**Gợi ý kiểm chứng:** Thứ tự phải là E2, E3, E1 (vì 09:00 trước 08:00, E2 có UUID nhỏ hơn E3). Cả E1/E2/E3 trong partition T1/C1 cùng thấy VIP; E4 thuộc partition khác thì không. Xóa E2 không xóa static value; E1/E3 vẫn thấy VIP. Frozen UDT cần được ghi lại như một giá trị hoàn chỉnh với các field muốn giữ. Set không có thứ tự insertion. Để phát hiện converter hai chiều cùng sai, cần kiểm tra **Spring write → CQL read** hoặc **CQL write → Spring read** bằng fixture độc lập.

## 15. Những điều cần nhớ

**Composite primary key quyết định đường truy vấn.** Phải test đủ các thành phần partition, thứ tự clustering, khóa phân biệt sự kiện trùng thời gian và hành vi upsert trên full key.

**Static column thuộc partition.** Chỉ một lần thay đổi có thể ảnh hưởng giá trị đọc của nhiều dòng. Test cần nhiều dòng cùng partition và ít nhất một partition khác để bắt lỗi phạm vi ghi.

**Nested UDT cần kiểm chứng ở ranh giới Java–CQL.** Round-trip bằng cùng một converter có thể che lỗi. Kết hợp repository/`CassandraTemplate` với `CqlSession`, kiểm tra giá trị lồng nhau, `frozen`, `list`, `set`, `map`, null/empty và precision.

**Môi trường test phải phản ánh ngữ nghĩa Cassandra.** Cassandra container là công cụ tốt để xác nhận schema và mapping; các bảo đảm về replica, consistency và cạnh tranh trên cluster phân tán phải được kiểm tra riêng khi chúng nằm trong hợp đồng ứng dụng. Kết quả kiểm thử đáng tin cậy đến từ fixture cô lập, assertion theo bất biến và lỗi được tái hiện rõ ràng.

---

**Tài liệu đối chiếu khi triển khai:** Apache Cassandra CQL về composite primary keys, static columns, user-defined types, collection types, frozen values, query ordering, paging; Spring Data Cassandra về mapping annotations, repository, `CassandraTemplate` và conversion; Java Driver về `CqlSession`, `UdtValue`, prepared statements và paging; Testcontainers về Cassandra module. Kiểm tra chính xác API và package theo các phiên bản được khóa trong dự án.
