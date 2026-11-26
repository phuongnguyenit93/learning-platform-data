# Giới hạn của mock khi kiểm tra CQL và mô hình partition

Trong **Spring Data Cassandra**, unit test dùng mock rất hữu ích để kiểm tra service, repository fragment, logic kiểm tra tham số và cách mã Java gọi `CassandraOperations`, `CassandraTemplate` hoặc `CqlSession`. Tuy nhiên, **mock không thực thi truy vấn trên Apache Cassandra**. Một bài test xanh khi mock repository vẫn có thể đi kèm một câu CQL không hợp lệ, bảng thiết kế sai partition key, truy vấn đọc trên nhiều partition hoặc độ trễ cao trong thực tế.

Bài thuộc phần **Kiểm thử** của module **SPRING_DATA_CASSANDRA**, đặt trọng tâm vào cách xây dựng bằng chứng kiểm thử đáng tin cậy cho hệ thống phân tán: phân biệt điều mock có thể chứng minh với điều phải kiểm tra bằng Cassandra thật, từ entity mapping và repository đến partition key, clustering order, paging, consistency và hiệu năng.

## 1. Vì sao test mock thường tạo cảm giác an toàn quá mức?

Ví dụ một service gọi:

```java
List<EventView> events = eventReader.findRecent(
        tenantId, 20261125, since, 20);
```

Một unit test có thể cấu hình `eventReader` trả hai đối tượng bất kỳ, rồi xác nhận service đã chuyển đúng `tenantId` và `limit`. Test đó chứng minh **hành vi của service theo giả định về collaborator**, nhưng chưa chứng minh được:

- Repository tạo ra CQL hợp lệ với schema hiện tại.
- Điều kiện `WHERE` bao gồm đầy đủ partition key.
- Điều kiện khoảng trên clustering column được Cassandra hỗ trợ.
- Kết quả được sắp xếp theo thứ tự clustering như yêu cầu.
- Mapping chuyển đúng các kiểu Cassandra như `uuid`, `timestamp`, `decimal` hoặc collections.
- Truy vấn không cần `ALLOW FILTERING` hoặc không quét partition khổng lồ.
- Truy vấn xử lý paging state, consistency, timeout và lỗi kết nối đúng trong môi trường phân tán.

Nếu mock được đặt ngay tại `CqlSession`, test còn có thể xác nhận Java đã gọi `execute(...)` và đã bind một số giá trị; nhưng **Cassandra server vẫn không phân tích hoặc thực thi CQL**. Chỉ mock ra `Row`/`ResultSet` không tạo ra dữ liệu thật với partition và clustering key tương ứng.

### Ba tầng kiểm thử cần phân biệt

```text
HTTP / Service / nghiệp vụ
        |
        |  Unit test: mock repository/fragment
        v
Spring Data Repository / CassandraTemplate / CqlSession
        |
        |  Integration test: dùng Cassandra thật
        v
CQL + schema + partition/clustering + dữ liệu thực
        |
        |  Kiểm thử tải & môi trường phân tán
        v
Latency + hotspot + tombstone + consistency + paging
```

| Câu hỏi kiểm thử | Mock là đủ? | Bằng chứng phù hợp |
| --- | --- | --- |
| Service từ chối `limit < 1` hoặc `limit > 100`? | **Có**, nếu validation thuộc service. | Unit test với Mockito/JUnit. |
| Service truyền đúng tenant và điều kiện lọc? | **Có**, ở ranh giới service. | `verify(...)` hoặc `ArgumentCaptor`. |
| Fragment tạo đúng đối tượng `Query`/`BoundStatement`? | **Một phần**: có thể kiểm tra lời gọi và một số thuộc tính. | Unit test kèm kiểm tra CQL trên Cassandra thật. |
| Spring Data ánh xạ đúng khóa tổng hợp và DTO? | **Không đầy đủ**. | Repository integration test với dữ liệu thật. |
| CQL hợp lệ với partition/clustering key? | **Không**. | `prepare`/`execute` trên Cassandra thật. |
| Truy vấn có vô tình dùng `ALLOW FILTERING`? | **Không đầy đủ**. | Kiểm tra CQL phát ra và chạy truy vấn thật. |
| Paging state cho phép đọc trang tiếp theo? | **Không**. | Integration test qua driver/repository với nhiều hàng. |
| Truy vấn có nhanh ở quy mô lớn hay tạo hotspot? | **Không**. | Benchmark/load test và metrics Cassandra. |
| `LOCAL_QUORUM` thực sự hoạt động khi một replica hỏng? | **Không**. | Kiểm thử cụm nhiều node với replication phù hợp. |

**Nguyên tắc:** đặt test ở tầng thấp nhất có thể chứng minh điều muốn kiểm tra. Đối với tính hợp lệ của CQL và mô hình partition, tầng đó bao gồm một Cassandra server thực.

## 2. Case study: bảng đọc theo tenant và ngày

Giả sử một ứng dụng thu thập sự kiện và cần truy vấn:

> Với một tenant và một ngày cụ thể, lấy tối đa 20 sự kiện từ thời điểm `since`, theo thứ tự mới nhất trước.

Trong Cassandra, bảng nên xuất phát từ **access pattern** này:

```sql
CREATE TABLE events_by_tenant_day (
    tenant_id   uuid,
    day_bucket  int,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    PRIMARY KEY ((tenant_id, day_bucket), occurred_at, event_id)
) WITH CLUSTERING ORDER BY (
    occurred_at DESC,
    event_id ASC
);
```

| Khóa | Chức năng |
| --- | --- |
| `tenant_id` + `day_bucket` | **Partition key tổng hợp**; dữ liệu cùng tenant trong một bucket ngày thuộc cùng logical partition. |
| `occurred_at` | Clustering column; hỗ trợ điều kiện khoảng và thứ tự thời gian giảm dần bên trong partition. |
| `event_id` | Clustering column bổ sung; phân biệt hai sự kiện cùng timestamp. |
| `event_type` | Cột giá trị thông thường; không tự động được dùng làm khóa lọc hiệu quả. |

CQL phù hợp:

```sql
SELECT event_id, occurred_at, event_type
FROM events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket = ?
  AND occurred_at >= ?
LIMIT ?;
```

Truy vấn có điều kiện bằng cho **đầy đủ hai thành phần partition key** và giới hạn khoảng trên clustering column đầu tiên. Thứ tự trả về theo clustering order của bảng: `occurred_at DESC`, rồi `event_id ASC` khi timestamp bằng nhau. Một `LIMIT` nhỏ giúp giới hạn số hàng trả về nhưng **không bảo đảm partition nhỏ hay truy vấn luôn rẻ**.

### Ba lỗi có thể lọt qua mock

**Lỗi 1 — Thiếu một phần partition key:**

```sql
-- Không đáp ứng access pattern của khóa tổng hợp
SELECT event_id, occurred_at
FROM events_by_tenant_day
WHERE tenant_id = ?
  AND occurred_at >= ?;
```

Mock `CqlSession` có thể trả một `ResultSet` giả như ý muốn. Cassandra thật phải áp dụng quy tắc hạn chế khóa truy vấn; với schema này, câu trên không thể thực hiện như truy vấn partition chuẩn. Nếu cố thêm `ALLOW FILTERING`, nó có thể dẫn tới công việc quét/lọc tốn kém và không giải quyết đúng bài toán thiết kế bảng.

**Lỗi 2 — Lọc bằng cột không nằm trong khóa:**

```sql
-- event_type không phải partition/clustering key của bảng
SELECT event_id
FROM events_by_tenant_day
WHERE event_type = 'PAYMENT_FAILED';
```

Một unit test mock không thể đo chi phí lọc trên nhiều partition. Nếu yêu cầu tra cứu theo `event_type` thật sự quan trọng, hãy cân nhắc **bảng đọc theo event type** (và khóa phân vùng phù hợp) hoặc tính năng indexing phù hợp với phiên bản Cassandra và tải thực tế. Chọn phương án dựa trên access pattern, cardinality và chi phí vận hành, không chỉ dựa vào khả năng câu lệnh được chấp nhận.

**Lỗi 3 — Kỳ vọng sort hoặc phân trang kiểu SQL quan hệ:**

```sql
-- Không phải cách phân trang sâu thông dụng trong CQL
SELECT event_id
FROM events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket = ?
ORDER BY event_type DESC
LIMIT 20 OFFSET 1000;
```

CQL có giới hạn riêng với `ORDER BY` và không cung cấp `OFFSET` tùy ý theo mô hình phân trang quan hệ. API nên sử dụng **paging state/cursor** với truy vấn và tham số ổn định. Nếu sản phẩm yêu cầu sắp xếp tùy ý theo nhiều cột, cần xem lại mô hình dữ liệu hoặc đưa xử lý sang hệ thống phù hợp.

## 3. Unit test với mock thực sự chứng minh được gì?

Hãy giữ một hợp đồng nhỏ cho repository fragment:

```java
public interface EventReader {
    List<EventView> findRecent(
            UUID tenantId,
            int dayBucket,
            Instant since,
            int limit
    );
}

public record EventView(
        UUID eventId,
        Instant occurredAt,
        String eventType
) {}
```

Service làm nhiệm vụ kiểm tra input trước khi gọi fragment:

```java
public final class EventQueryService {

    private final EventReader reader;

    public EventQueryService(EventReader reader) {
        this.reader = reader;
    }

    public List<EventView> recent(
            UUID tenantId, int dayBucket, Instant since, int limit) {

        if (tenantId == null || since == null) {
            throw new IllegalArgumentException("tenantId/since bắt buộc");
        }
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("limit phải từ 1 đến 100");
        }

        return reader.findRecent(tenantId, dayBucket, since, limit);
    }
}
```

Unit test minh họa bằng JUnit 5 và Mockito:

```java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class EventQueryServiceTest {

    @Test
    void chuyenDungDieuKienTruyVan() {
        EventReader reader = mock(EventReader.class);
        EventQueryService service = new EventQueryService(reader);

        UUID tenant = UUID.randomUUID();
        Instant since = Instant.parse("2026-11-25T08:00:00Z");
        List<EventView> expected = List.of(
                new EventView(UUID.randomUUID(), since, "CREATED"));

        when(reader.findRecent(tenant, 20261125, since, 20))
                .thenReturn(expected);

        List<EventView> actual =
                service.recent(tenant, 20261125, since, 20);

        assertEquals(expected, actual);
        verify(reader).findRecent(tenant, 20261125, since, 20);
    }

    @Test
    void tuChoiLimitKhongHopLe() {
        EventReader reader = mock(EventReader.class);
        EventQueryService service = new EventQueryService(reader);

        assertThrows(IllegalArgumentException.class,
                () -> service.recent(
                        UUID.randomUUID(), 20261125, Instant.now(), 0));

        verifyNoInteractions(reader);
    }
}
```

Hai test trên rất có giá trị: chúng khóa lại hành vi của service và không cần Cassandra chạy. Nhưng chúng **không đụng tới bảng `events_by_tenant_day`, cũng không dịch phương thức thành CQL**. Một triển khai fragment sai partition key vẫn có thể đi cùng hai test xanh này.

Nếu unit test ở lớp triển khai gọi `CassandraOperations.select(query, Entity.class)`, Mockito có thể kiểm tra `select` được gọi, thậm chí bắt `Query` bằng `ArgumentCaptor`. Với `CqlSession`, có thể kiểm tra việc chọn prepared statement và bind tham số nếu thiết kế cho phép. Những test ấy vẫn chỉ kiểm tra mã Java cùng cấu hình mock; **server không xác minh schema, CQL hay chiến lược đọc**.

### Đừng mock cả thứ đang cần chứng minh

Ví dụ một bài kiểm thử `@SpringBootTest` có `@MockBean` (hoặc cơ chế mock bean tương ứng ở phiên bản Spring Boot đang dùng) cho repository, rồi gọi API thành công, chỉ chứng minh luồng từ controller đến bean giả. Nếu mục tiêu là “repository query chạy đúng trên Cassandra”, phải thay bean giả bằng repository thực và kết nối với một Cassandra thực.

Tên annotation “integration test” hoặc việc khởi động Spring context không tự động chứng minh truy vấn đã được Cassandra xử lý; phải **thực thi đường truy cập dữ liệu thực** trong test.

## 4. Integration test với Cassandra thật bằng Testcontainers

Một cách thực dụng trong môi trường phát triển là dùng **Testcontainers** khởi chạy Cassandra trong Docker. Test có thể tạo keyspace, bảng, ghi các hàng đại diện và thực hiện CQL thông qua Java Driver. Điều này phát hiện các lỗi mà mock bỏ sót, như thiếu partition key, sai tên cột hoặc sai kiểu dữ liệu.

Ví dụ sau dùng **Java 17+, JUnit 5, Testcontainers Cassandra và Java Driver 4**. Các thư viện cùng phiên bản tương thích cần được cấu hình trong project. Test dùng `CqlSession` trực tiếp để tập trung vào bằng chứng **CQL + schema + dữ liệu**; ở phần sau sẽ nối tiếp với Spring Data repository thực.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.servererrors.InvalidQueryException;
import org.junit.jupiter.api.Test;
import org.testcontainers.containers.CassandraContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@Testcontainers
class EventCqlIntegrationTest {

    @Container
    static final CassandraContainer<?> CASSANDRA =
            new CassandraContainer<>(
                    DockerImageName.parse("cassandra:4.1"));

    @Test
    void truyVanDungPartitionVaClusteringKey() {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(new InetSocketAddress(
                        CASSANDRA.getHost(),
                        CASSANDRA.getMappedPort(9042)))
                .withLocalDatacenter("datacenter1")
                .build()) {

            session.execute("""
                    CREATE KEYSPACE IF NOT EXISTS learning_test
                    WITH replication = {
                        'class': 'SimpleStrategy',
                        'replication_factor': 1
                    }
                    """);

            session.execute("""
                    CREATE TABLE IF NOT EXISTS
                    learning_test.events_by_tenant_day (
                        tenant_id uuid,
                        day_bucket int,
                        occurred_at timestamp,
                        event_id uuid,
                        event_type text,
                        PRIMARY KEY (
                            (tenant_id, day_bucket),
                            occurred_at,
                            event_id
                        )
                    ) WITH CLUSTERING ORDER BY (
                        occurred_at DESC,
                        event_id ASC
                    )
                    """);

            UUID tenantA = UUID.randomUUID();
            UUID tenantB = UUID.randomUUID();
            UUID newest = UUID.randomUUID();
            UUID older = UUID.randomUUID();

            PreparedStatement insert = session.prepare("""
                    INSERT INTO learning_test.events_by_tenant_day
                        (tenant_id, day_bucket, occurred_at,
                         event_id, event_type)
                    VALUES (?, ?, ?, ?, ?)
                    """);

            session.execute(insert.bind(
                    tenantA, 20261125,
                    Instant.parse("2026-11-25T10:00:00Z"),
                    newest, "CREATED"));

            session.execute(insert.bind(
                    tenantA, 20261125,
                    Instant.parse("2026-11-25T09:00:00Z"),
                    older, "PAID"));

            // Cùng tenant, khác partition theo ngày
            session.execute(insert.bind(
                    tenantA, 20261124,
                    Instant.parse("2026-11-24T23:00:00Z"),
                    UUID.randomUUID(), "CREATED"));

            // Khác tenant, cùng bucket
            session.execute(insert.bind(
                    tenantB, 20261125,
                    Instant.parse("2026-11-25T11:00:00Z"),
                    UUID.randomUUID(), "CREATED"));

            PreparedStatement find = session.prepare("""
                    SELECT event_id, occurred_at, event_type
                    FROM learning_test.events_by_tenant_day
                    WHERE tenant_id = ?
                      AND day_bucket = ?
                      AND occurred_at >= ?
                    LIMIT ?
                    """);

            List<Row> rows = session.execute(find.bind(
                    tenantA,
                    20261125,
                    Instant.parse("2026-11-25T08:00:00Z"),
                    20)).all();

            assertEquals(2, rows.size());
            assertEquals(newest, rows.get(0).getUuid("event_id"));
            assertEquals(older, rows.get(1).getUuid("event_id"));

            // Truy vấn thiếu day_bucket phải bị Cassandra từ chối.
            assertThrows(InvalidQueryException.class,
                    () -> session.prepare("""
                            SELECT event_id
                            FROM learning_test.events_by_tenant_day
                            WHERE tenant_id = ?
                              AND occurred_at >= ?
                            """));
        }
    }
}
```

**Giá trị của test thực:** câu lệnh `CREATE TABLE`, `INSERT` và `SELECT` chạy trên cùng một Cassandra thực; kết quả xác nhận tính phân tách theo partition và thứ tự trả về trong tình huống đã chuẩn bị. Negative test đưa CQL thiếu `day_bucket` tới server và yêu cầu server từ chối.

**Giới hạn của ví dụ:** keyspace dùng `SimpleStrategy` với replication factor 1, thích hợp cho kiểm thử cục bộ một node. Bài test chưa chứng minh ứng dụng vận hành đúng trong cụm nhiều replica, nhiều data center, khi node hỏng hoặc lúc dữ liệu tăng lớn. Tên data center `datacenter1` phù hợp với image Cassandra mặc định dùng trong ví dụ; nếu tùy biến container, cần điều chỉnh cho đúng cấu hình thực tế. Nên tạo keyspace/bảng riêng cho từng nhóm test hoặc quản lý cleanup để các bài chạy song song không ảnh hưởng nhau.

### Khi nào tích hợp thêm Spring Data repository?

Nếu code sản xuất dùng `CassandraRepository`, entity mapping và query derivation hoặc `@Query` thì cần thêm integration test gọi **repository thực** hoặc **fragment thực** trên Cassandra của Testcontainers:

1. Khởi tạo Spring context phù hợp (`@DataCassandraTest` hoặc `@SpringBootTest` tùy phạm vi).
2. Cấu hình Cassandra contact point, port, local datacenter và keyspace của container qua cơ chế cấu hình test phù hợp với phiên bản Spring Boot, ví dụ `@DynamicPropertySource`.
3. Tạo schema và seed dữ liệu theo cơ chế rõ ràng, không phụ thuộc thứ tự test.
4. Gọi phương thức repository thực, khẳng định nội dung/ordering/giới hạn, và chạy thêm ca lỗi truy vấn nếu cần.
5. Đảm bảo bean repository, `CassandraOperations` hay `CqlSession` dùng trong đường cần kiểm tra không bị thay bằng mock.

Test gọi trực tiếp driver sẽ chứng minh CQL mục tiêu chạy được với bảng mẫu. Test đi qua Spring Data chứng minh thêm **Spring mapping, việc sinh câu truy vấn từ repository và wiring**. Hai mục tiêu này có liên hệ nhưng là hai bằng chứng khác nhau.

## 5. Ma trận kiểm thử cho partition key và clustering key

Có thể dùng bảng dưới đây làm bộ ca kiểm thử ban đầu cho `events_by_tenant_day`:

| Trường hợp | Dữ liệu/điều kiện | Kỳ vọng cần quan sát trên Cassandra thật |
| --- | --- | --- |
| Partition đúng | `tenantA`, `day_bucket=20261125` | Chỉ dữ liệu thuộc partition đó xuất hiện. |
| Tenant isolation | Cùng ngày, thêm hàng của `tenantB` | Không lẫn sự kiện của tenant khác. |
| Bucket isolation | Cùng tenant, thêm dữ liệu ngày trước | Query một bucket không trả dữ liệu bucket khác. |
| Giới hạn thời gian | Seed trước, đúng và sau `since` | `occurred_at >= since` bao gồm biên đúng. |
| Clustering order | Seed theo thứ tự insert ngẫu nhiên | Kết quả theo `occurred_at DESC`, không phụ thuộc thứ tự insert. |
| Trùng timestamp | Hai event khác `event_id` | Không bị ghi đè; thứ tự phụ theo `event_id`. |
| Giới hạn số hàng | Seed hơn 20 hàng, `LIMIT 20` | Không trả quá 20 hàng. |
| Thiếu partition key | Bỏ `day_bucket` | CQL bị từ chối hoặc không thỏa hợp đồng truy vấn đã thiết kế. |
| Sai kiểu dữ liệu | Bind `text` thay cho `uuid` | Test phát hiện lỗi codec/mapping thay vì nhận dữ liệu giả. |
| Mapping entity | Read/write qua repository Spring Data | Khóa tổng hợp và các field được ánh xạ đúng. |
| Paging | Seed nhiều hơn một page size | Các trang tiếp theo đọc được với cursor hợp lệ. |
| Time-to-live / tombstone | Dùng dữ liệu TTL hoặc delete | Xác minh chức năng và đo tác động khi phù hợp. |

Với những điều kiện **không hợp lệ**, hãy kiểm tra loại lỗi/ý nghĩa lỗi theo phiên bản Cassandra dùng trong dự án, tránh ràng buộc test vào toàn bộ chuỗi thông báo lỗi vốn có thể thay đổi. Với điều kiện **hợp lệ**, đừng chỉ assert “không ném exception”: cần assert tập kết quả và ordering.

### Những ca biên thường bị bỏ sót

**Khóa partition tổng hợp:** `PRIMARY KEY ((tenant_id, day_bucket), ...)` khác với `PRIMARY KEY (tenant_id, day_bucket, ...)`. Trong cú pháp thứ hai, chỉ `tenant_id` là partition key, còn `day_bucket` trở thành clustering column. Nếu mock chỉ trả đúng một danh sách, cả hai thiết kế có thể cho cùng kết quả test mặc dù chi phí truy cập và phân bố dữ liệu rất khác.

**Mốc thời gian và timezone:** kiểu CQL `timestamp` lưu thời điểm, nên kiểm thử bằng `Instant` và giá trị UTC rõ ràng. Không tạo giả định rằng bucket theo ngày UTC giống bucket theo ngày của mọi tenant. Quy tắc tính `day_bucket` phải do nghiệp vụ xác định.

**Đọc qua nhiều bucket:** CQL của ví dụ chỉ đọc một bucket. Để truy vấn 7 ngày gần nhất, service cần xác định những bucket liên quan, gọi từng truy vấn có biên, gộp/sắp xếp theo quy tắc rõ ràng và giới hạn số lần đọc. Một mock trả dữ liệu “đúng 7 ngày” không chứng minh logic query thật đã đi qua đủ bucket.

**Lọc trạng thái/event type:** thêm điều kiện trên cột thường vào query không tự động tạo access path hiệu quả. Test kiểm tra bản ghi đúng có thể vẫn xanh sau khi thêm `ALLOW FILTERING`, trong khi hiệu năng trên bảng lớn suy giảm. Cần kiểm tra schema/CQL cùng bằng chứng tải.

## 6. Paging: test trả dữ liệu đúng chưa đủ

Cassandra phân trang bằng **paging state** của driver/Spring Data, không phải bằng offset tùy ý. Có hai khái niệm thường bị lẫn:

- **CQL `LIMIT`** giới hạn tổng số hàng tối đa của câu truy vấn.
- **Driver page size/fetch size** giới hạn số hàng mục tiêu trong một lần lấy trang qua mạng; duyệt một `ResultSet` đồng bộ có thể tự fetch thêm trang khi cần.

Với API có “Xem thêm”, test mock thường chỉ tạo hai danh sách giả cho “trang 1” và “trang 2”. Nó không kiểm tra được trạng thái phân trang thực, ví dụ:

1. Tạo nhiều hàng hơn page size, cùng một partition.
2. Chạy cùng query với page size nhỏ để buộc nhiều lượt fetch.
3. Lấy paging state từ driver sau trang đầu rồi tiếp tục bằng cùng statement và các tham số ràng buộc.
4. Assert không bỏ sót hoặc lặp hàng trong bộ dữ liệu **ổn định**.
5. Kiểm tra cursor hết dữ liệu và cursor không hợp lệ/không phù hợp query.

Ở tầng API, nên thiết kế cursor dạng token khó đoán, gắn với tenant, query, bộ lọc và version khi cần; không chấp nhận một paging state từ yêu cầu khác một cách mù quáng. Trong dữ liệu có ghi/xóa đồng thời, **không mặc định** paging cho snapshot bất biến; tài liệu API cần nêu rõ mức ổn định thứ tự/kết quả mà người dùng được đảm bảo.

Nếu framework cung cấp `Slice` hoặc `CassandraPageRequest` ở phiên bản sử dụng, hãy kiểm thử cơ chế paging cụ thể ấy với repository thật, thay vì giả lập ý nghĩa của `Page` trong SQL. Việc đếm tổng số hàng trên Cassandra có thể tốn kém và không nên xuất hiện chỉ để hiển thị “tổng số trang” khi không cần.

## 7. Consistency và lỗi phân tán: mô phỏng ở đâu, kiểm chứng ở đâu?

Mockito có thể mô phỏng các nhánh mà ứng dụng cần xử lý khi driver báo lỗi:

```text
Query request
   |
   +-- thành công            -> chuyển kết quả thành DTO
   +-- timeout              -> retry/response theo chính sách
   +-- unavailable          -> fail fast hoặc fallback phù hợp
   +-- invalid query        -> ghi log/đánh dấu lỗi lập trình
   +-- kết nối bị gián đoạn -> phản hồi lỗi có kiểm soát
```

Các mock exception giúp chứng minh logic chuyển lỗi, retry policy, số lần gọi và việc không rò rỉ thông tin nhạy cảm qua API. Tuy nhiên, **mock exception không xác nhận cụm Cassandra thật sẽ có hành vi đó dưới mức consistency đã cấu hình**.

Cần phân biệt ba phạm vi:

| Loại test | Xác minh tốt | Không nên suy diễn |
| --- | --- | --- |
| Unit test mock lỗi driver | Cách ứng dụng xử lý exception và dừng/retry. | Tỷ lệ lỗi thực tế, thời điểm quorum không đạt. |
| Integration test một node | CQL, schema, mapping, read/write cơ bản. | Replication, failover, ứng xử quorum nhiều node. |
| Kiểm thử cụm nhiều node | Hành vi khi node hỏng, read/write consistency, một số kịch bản phục hồi. | Hiệu năng production nếu quy mô dữ liệu và network khác biệt. |

Ví dụ `LOCAL_QUORUM` yêu cầu quorum replica ở local data center cho thao tác thích hợp. Để thử ý nghĩa vận hành của nó phải có **replication factor và số node đại diện**; một container RF=1 không đủ chứng minh kịch bản mất replica trên cụm thật.

Ứng dụng cũng cần phân biệt read retry và write retry. Một write bị timeout có thể đã được một số replica áp dụng; retry không phải lúc nào cũng an toàn nếu thao tác không idempotent. Hãy cấu hình idempotence và retry có chủ đích; test mock phù hợp để kiểm tra chính sách của ứng dụng, còn fault-injection test hỗ trợ kiểm tra tương tác thực của driver/cụm.

## 8. Kiểm thử hiệu năng: mock không nhìn thấy hotspot và tombstone

Giả sử integration test trên vài chục hàng chạy trong vài mili giây. Điều đó cho thấy truy vấn hợp lệ; chưa đủ để kết luận nó ổn khi một tenant có hàng chục triệu sự kiện.

Vấn đề cần đo trong điều kiện tải đại diện:

- **Partition size**: kích thước và số hàng/tombstone trong partition; bucket ngày có phù hợp với tenant lớn không?
- **Hot partition**: tenant có lưu lượng đặc biệt cao có làm một nhóm replica chịu nhiều read/write hơn không?
- **Tombstone scans**: xóa/TTL dày đặc có làm tăng lượng dữ liệu phải đọc để trả vài hàng còn sống?
- **Read latency p95/p99** và tỷ lệ timeout: thay đổi ra sao khi lượng dữ liệu, mức concurrency và consistency tăng?
- **Paging overhead**: thời gian thực hiện một request và toàn bộ chuỗi trang; số lượt fetch.
- **Compaction, GC, disk I/O, network**: áp lực hệ thống khi truy vấn dài hoặc phân vùng không đều.

Một test tích hợp có thể bắt các lỗi logic rất sớm. Để đánh giá dung lượng và hiệu năng, cần thêm **load test, tracing/metrics và dữ liệu có phân phối gần thực tế**. Có thể dùng Testcontainers cho kiểm thử nhỏ lặp lại được, sau đó đo trên môi trường Cassandra có số node, cấu hình và dữ liệu gần với triển khai thực.

Không dùng thời gian chạy của Mockito hay `verify(execute)` để kết luận truy vấn CQL nhanh. Cũng không coi `LIMIT 20` là bằng chứng truy vấn luôn rẻ: nếu bảng/partition phân bố không phù hợp, công việc đọc vẫn có thể lớn.

## 9. Cách tổ chức bộ test có hiệu quả

Một chiến lược thực tế cho dự án Spring Data Cassandra:

| Tầng | Chạy khi nào | Ca kiểm thử tiêu biểu |
| --- | --- | --- |
| Unit mock | Mọi lần thay đổi code; rất nhanh | Validation, phân nhánh service, DTO transformation, xử lý exception, retry policy do ứng dụng quản lý. |
| Cassandra integration | Trong CI cho thay đổi repository, schema, fragment, converter | DDL thực, CQL hợp lệ, partition key, clustering key, dữ liệu trả về, CRUD, mapping, paging. |
| Contract/API integration | Khi thay API hoặc luồng dữ liệu | Phân quyền tenant, tham số, status code, cursor, serialization. |
| Kiểm thử tải/fault | Theo mốc release hoặc thay đổi data model lớn | Hot partition, tombstone, latency, timeout, failover, consistency. |

Để bộ test phản ánh đúng hệ thống, nên thực hiện các điều sau:

1. **Dùng schema tương ứng với môi trường chạy.** Nếu ứng dụng triển khai thay đổi schema theo migration, test phải dùng migration tương ứng thay vì tự định nghĩa một bảng đơn giản nhưng khác production.
2. **Không trộn unit mock với kết luận về database.** Đặt tên test theo đúng hành vi được chứng minh: `serviceRejectsInvalidLimit` khác `cqlRejectsMissingPartitionKey`.
3. **Seed dữ liệu đối chứng có chủ ý.** Luôn có ít nhất dữ liệu ngoài tenant, ngoài bucket và ngoài khoảng thời gian để phát hiện lọc sai.
4. **Giữ test độc lập.** Dùng keyspace/bảng và dữ liệu quản lý riêng cho test; không phụ thuộc kết quả bài trước hoặc thứ tự chạy.
5. **Tối thiểu một test negative CQL.** Xác minh lớp test thật sự đi tới Cassandra, vì một test chỉ assert danh sách rỗng rất dễ thành xanh giả.
6. **Giám sát câu truy vấn phát ra.** Với repository derivation, `@Query` hoặc `CassandraTemplate`, truy vấn thực cần được đối chiếu với schema. Logging/tracing phải tránh lộ dữ liệu nhạy cảm.
7. **Không bắt buộc mọi unit test khởi động Docker.** Giữ unit test nhanh; chỉ chuyển câu hỏi về database tới integration test.
8. **Ghi rõ phạm vi môi trường.** Cassandra một node với RF=1 phục vụ kiểm thử chức năng cơ bản; các tuyên bố về consistency, failure và hiệu năng cần bằng chứng riêng.

## 10. Những hiểu nhầm thường gặp

| Khẳng định dễ nhầm | Cách hiểu chính xác |
| --- | --- |
| “Mockito xác nhận `session.execute` chạy thì CQL hợp lệ.” | Mockito có thể xác nhận *lời gọi Java*; Cassandra phải nhận statement để kiểm tra CQL và schema. |
| “Repository mock trả đúng entity nên `@PrimaryKeyClass` chính xác.” | Entity giả không chứng minh Spring Data mapping đúng; cần gọi repository thật với dữ liệu đã ghi. |
| “Query trả đúng trên 10 hàng nên không có vấn đề partition.” | Kết quả chức năng không cho biết partition size hoặc hotspot khi dữ liệu tăng. |
| “Có `LIMIT` nghĩa là đọc rất ít dữ liệu.” | `LIMIT` giới hạn hàng trả về; chi phí đọc còn phụ thuộc schema, partition, tombstone và truy vấn. |
| “CQL có `ALLOW FILTERING` chạy được thì thiết kế ổn.” | Khả năng thực thi khác với truy vấn có access path tốt ở quy mô production. |
| “Testcontainers một node chứng minh quorum/failover.” | Cần cụm, replication và kịch bản lỗi đại diện để kiểm chứng behavior phân tán. |
| “Paging giống `OFFSET` trong SQL.” | Cassandra dùng paging state; cursor phụ thuộc truy vấn và trạng thái dữ liệu. |
| “`@SpringBootTest` mặc định là kiểm thử database đầy đủ.” | Cần bảo đảm phương thức thực được gọi trên Cassandra thật, schema và seed dữ liệu phù hợp. |

## 11. Bài tập thực hành

**Bài tập 1 — Test mock đi qua nhưng CQL sai:** tạo `EventQueryService` và unit test mock `EventReader` như mục 3. Sau đó cố ý sửa fragment để bỏ điều kiện `day_bucket`. Giải thích vì sao unit test vẫn xanh và thêm integration test mong Cassandra từ chối câu CQL.

**Bài tập 2 — Khóa tổng hợp:** tạo hai bảng có cùng tên cột nhưng lần lượt dùng `PRIMARY KEY ((tenant_id, day_bucket), occurred_at)` và `PRIMARY KEY (tenant_id, day_bucket, occurred_at)`. So sánh thành phần partition key, thứ tự clustering, truy vấn phù hợp và tác động đến phân bổ dữ liệu. Không giả định các bảng có cùng ý nghĩa chỉ vì kết quả một truy vấn mẫu giống nhau.

**Bài tập 3 — Đọc nhiều trang:** seed ít nhất 30 hàng trong cùng một partition, thực hiện paging với page size 7. Khẳng định đọc hết dữ liệu theo thứ tự mà không lặp hàng trong bộ dữ liệu ổn định. Phân biệt page size với `LIMIT`.

**Bài tập 4 — Đo hotspot:** tạo nhiều tenant nhỏ và một tenant lớn trong môi trường test tải. Đo phân phối partition size, latency p95/p99 và throughput. Thử thay `day_bucket` bằng bucket nhỏ hơn, rồi phân tích lợi ích cùng chi phí truy vấn qua nhiều bucket.

**Bài tập 5 — Consistency:** thiết kế test một node và test cụm nhiều node cho một read path. Nêu rõ điều gì được chứng minh bởi từng test, replication factor nào cần thiết và kịch bản node nào có thể bị dừng khi thử `LOCAL_QUORUM`.

## 12. Checklist trước khi tin vào kết quả kiểm thử

- [ ] Unit mock đã kiểm tra validation, mapping nghiệp vụ, phản hồi lỗi và lời gọi collaborator.
- [ ] Ít nhất một integration test đã thực thi **CQL thật** trên Cassandra với schema đúng.
- [ ] Query có điều kiện đầy đủ cho partition key và clustering key tương ứng.
- [ ] Test dữ liệu đối chứng ngoài tenant/bucket/điều kiện thời gian để bắt lọc sai.
- [ ] Đã kiểm tra ordering, `LIMIT`, paging và mapping trên trường hợp thực.
- [ ] Không lén thêm `ALLOW FILTERING` để vượt lỗi thiết kế bảng.
- [ ] Các tuyên bố về consistency và khả năng chịu lỗi có bằng chứng từ cụm phù hợp.
- [ ] Các tuyên bố về hiệu năng có số đo từ dữ liệu/tải đại diện.

**Ghi nhớ:** mock là công cụ kiểm tra logic Java, luồng nghiệp vụ và hợp đồng cộng tác giữa các lớp. Tính hợp lệ của CQL, cách Cassandra áp dụng partition/clustering key, kết quả paging và entity mapping phải được kiểm tra bằng đường truy cập dữ liệu thật. Độ bền vững trước tải, hotspot và lỗi replica lại cần dữ liệu, metrics và môi trường phân tán đại diện. Kết hợp các tầng kiểm thử đúng mục đích sẽ giúp ứng dụng **Spring Data Cassandra** vừa có vòng phản hồi phát triển nhanh vừa có bằng chứng về độ đúng và hiệu năng của mô hình dữ liệu.
