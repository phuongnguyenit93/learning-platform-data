# Đo riêng thao tác theo partition key và truy vấn qua chỉ mục

Trong **Spring Data Cassandra**, một truy vấn chạy thành công hoặc trả đúng dữ liệu chưa đủ để kết luận nó có hiệu năng tốt. **Apache Cassandra** phân phối dữ liệu theo **partition key**; các thao tác định vị chính xác partition thường có đặc điểm chi phí khác với truy vấn dựa vào **secondary index**, đặc biệt khi chỉ mục phải tìm dữ liệu ở nhiều partition hoặc giá trị lọc có độ chọn lọc thấp.

Bài học thuộc chương **Hiệu năng** của module **SPRING_DATA_CASSANDRA**, tập trung vào cách **đo riêng hai read path**: truy cập bảng được thiết kế trực tiếp theo partition key và truy vấn sử dụng chỉ mục. Mục tiêu là xây dựng thí nghiệm có thể tái lập, đọc đúng các chỉ số latency/throughput/paging, và ra quyết định thiết kế bảng phù hợp với mô hình dữ liệu phân tán. Những ví dụ sử dụng **CQL**, **Java Driver / CqlSession**, đồng thời chỉ ra cách diễn giải kết quả khi đi qua **CassandraTemplate** hoặc **repository** của Spring Data.

## 1. Hai read path có gì khác nhau?

### 1.1. Đọc theo partition key

Cassandra dùng partition key để xác định token và những replica sở hữu dữ liệu. Khi câu truy vấn cung cấp đầy đủ khóa phân vùng, coordinator có thể định tuyến request tới các replica liên quan; clustering key tiếp tục xác định phạm vi và thứ tự dữ liệu **trong partition**.

Ví dụ:

```sql
SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day_type
WHERE tenant_id = ?
  AND day_bucket = ?
  AND event_type = ?;
```

Ở bảng ví dụ, ba cột trong điều kiện `WHERE` cùng cấu thành **composite partition key**. Truy vấn định vị một logical partition; chi phí còn tùy kích thước partition, tombstone, số hàng trả về, cache, consistency, page size và trạng thái cụm.

### 1.2. Đọc qua secondary index

Secondary index duy trì cấu trúc tra cứu bổ sung để tìm hàng theo một cột không nằm trong khóa chính của bảng. Chẳng hạn `event_type` là cột thường nhưng được lập chỉ mục trong bảng còn lại:

```sql
SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket = ?
  AND event_type = ?;
```

Với một index thích hợp, Cassandra có thể dùng điều kiện `event_type` để chọn các hàng phù hợp. Tuy vậy, truy vấn index vẫn cần phối hợp tra cứu, lọc và đọc dữ liệu; chi phí phụ thuộc **độ chọn lọc**, phân bố dữ liệu theo partition, loại index, cỡ kết quả và hoạt động của replica.

Không có quy tắc rằng “truy vấn qua index luôn chậm”. **Một index có tính chọn lọc cao trên workload phù hợp** có thể rất hữu ích. Cũng không có quy tắc rằng “biết partition key là luôn nhanh”: đọc một partition cực lớn với nhiều tombstone vẫn có thể chậm.

### 1.3. Phải nói rõ đang đo loại index nào

Apache Cassandra có các cơ chế chỉ mục khác nhau theo phiên bản và bản phân phối. **Storage-Attached Indexing (SAI)** trong Apache Cassandra 5.0 không có cùng chi phí vận hành với legacy secondary index (2i) hoặc những cơ chế indexing khác. Khi báo cáo benchmark, cần ghi chính xác:

- Phiên bản Cassandra và kiểu chỉ mục (ví dụ **SAI**, không viết chung chung “index”).
- Schema và câu lệnh tạo index, trạng thái index đã build xong.
- Cấu hình replica/consistency, phần cứng, cấu hình driver và dữ liệu thử.

Ví dụ của bài dùng **SAI với Apache Cassandra 5.0**. Nếu hệ thống đang chạy Cassandra phiên bản hoặc bản phân phối khác, hãy điều chỉnh cú pháp và đánh giá khả năng hỗ trợ indexing trước khi áp dụng. Không lấy số đo của SAI để kết luận trực tiếp cho 2i.

## 2. Thiết kế thí nghiệm với cùng một access pattern

Giả sử sản phẩm thu thập sự kiện của nhiều tenant. Màn hình giám sát cần tra cứu:

> “Cho một tenant, một ngày và một loại sự kiện, đọc các sự kiện tương ứng.”

Để đo công bằng, hai bảng phải chứa **cùng dữ liệu logic**, trả cùng cột và xử lý cùng bộ lọc. Ta sẽ dùng hai thiết kế vật lý:

1. **Bảng A:** đưa `event_type` vào partition key, tối ưu truy vấn bằng key.
2. **Bảng B:** dùng partition key theo tenant/ngày, thêm SAI cho `event_type`.

### 2.1. Schema của hai bảng

```sql
CREATE KEYSPACE IF NOT EXISTS perf
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
};

-- A: Thiết kế bảng phục vụ trực tiếp truy vấn đã biết.
CREATE TABLE IF NOT EXISTS perf.events_by_tenant_day_type (
    tenant_id   uuid,
    day_bucket  date,
    event_type  text,
    occurred_at timestamp,
    event_id    uuid,
    payload     text,
    PRIMARY KEY (
        (tenant_id, day_bucket, event_type),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id ASC
);

-- B: Phân vùng theo tenant/ngày, event_type là cột thường.
CREATE TABLE IF NOT EXISTS perf.events_by_tenant_day (
    tenant_id   uuid,
    day_bucket  date,
    occurred_at timestamp,
    event_id    uuid,
    event_type  text,
    payload     text,
    PRIMARY KEY (
        (tenant_id, day_bucket),
        occurred_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (
    occurred_at DESC, event_id ASC
);

-- Apache Cassandra 5.0: SAI trên cột cần lọc.
CREATE CUSTOM INDEX IF NOT EXISTS events_event_type_sai
ON perf.events_by_tenant_day (event_type)
USING 'StorageAttachedIndex';
```

Đoạn DDL minh họa **cụm có ít nhất 3 replica trong datacenter1**. Không sử dụng cấu hình RF=3 nguyên xi trên Testcontainers một node: với thử nghiệm cục bộ một node, tạo keyspace riêng RF=1 và ghi rõ rằng kết quả không đại diện cho cụm production. Điều chỉnh tên datacenter và replication theo hệ thống thật.

| Tiêu chí | Bảng A: partition-key read | Bảng B: indexed read |
| --- | --- | --- |
| Partition key | `(tenant_id, day_bucket, event_type)` | `(tenant_id, day_bucket)` |
| `event_type` | Thành phần của khóa phân vùng | Cột thường có SAI |
| Cách định vị | Câu truy vấn cung cấp đủ partition key | Partition key tenant/ngày và index predicate |
| Độ rộng partition | Phân nhỏ thêm theo event type | Có thể chứa nhiều loại sự kiện trong cùng ngày |
| Bảo trì | Duy trì thêm bảng tối ưu access pattern | Duy trì index gắn với bảng |
| Khả năng đáp ứng access pattern khác | Cần bảng/query khác nếu không biết type | Có thể hỗ trợ thêm các điều kiện index phù hợp, cần xác minh riêng |

**Không được xem bảng A là “miễn phí”**: nếu ứng dụng phải ghi cùng sự kiện vào cả bảng A và B hoặc các bảng materialized theo access pattern, chi phí ghi, lưu trữ, sửa/xóa và đồng bộ dữ liệu sẽ tăng. Index cũng có chi phí lưu trữ, xây dựng và cập nhật khi ghi; benchmark đọc chỉ là một phần quyết định.

### 2.2. Hai câu truy vấn tương đương về logic

```sql
-- Query A: partition-key read
SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day_type
WHERE tenant_id = ?
  AND day_bucket = ?
  AND event_type = ?;

-- Query B: read với SAI trên event_type
SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day
WHERE tenant_id = ?
  AND day_bucket = ?
  AND event_type = ?;
```

Với dữ liệu seed đồng nhất và không có cập nhật đồng thời, cả hai query phải trả **cùng tập event_id**. Nếu một truy vấn trả ít hoặc nhiều hơn, việc so sánh latency chưa đáng tin: có thể lỗi ingest, khác TTL, khác dữ liệu hoặc mapping sai.

Để giữ cùng lượng kết quả, bài thử đầu tiên **không dùng LIMIT** và đọc hết một tập kết quả đã được giới hạn kích thước từ khâu tạo dữ liệu. Ở benchmark của API thực tế, nên đo thêm từng kịch bản `LIMIT 20`, `LIMIT 100` và paging với cùng hợp đồng trả về. Không lấy phép đo “A trả 20 hàng” so với “B trả 20.000 hàng” để kết luận về tốc độ của cơ chế định vị.

### 2.3. Một query index qua nhiều partition là bài toán khác

Có thể thử thêm:

```sql
-- Query C: tìm cùng event_type trên nhiều tenant/ngày
SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day
WHERE event_type = ?
LIMIT 100;
```

Câu C nhằm đo **tìm kiếm dựa trên index không chỉ định partition**; số partition có thể tham gia hoàn toàn khác Query A/B. Hãy báo cáo C thành **workload riêng**, không so trực tiếp với Query A rồi tuyên bố index thua hoặc thắng. Với giá trị phổ biến xuất hiện ở hàng triệu partition, một câu truy vấn rộng có thể khiến coordinator/replica làm nhiều việc. `LIMIT 100` chỉ giới hạn hàng trả về, không đảm bảo công việc tìm kiếm luôn nhỏ.

## 3. Chuẩn bị dữ liệu để tránh benchmark sai lệch

Khi đo Cassandra, dữ liệu giả có phân bố đồng đều quá mức thường che giấu hotspot. Nên tạo ít nhất ba nhóm:

| Nhóm thử | Phân bố | Điều cần quan sát |
| --- | --- | --- |
| Giá trị hiếm | Một `event_type` chỉ chiếm khoảng 1% bản ghi trong mỗi partition | SAI có lợi thế lựa chọn bản ghi khi ít kết quả hay không? |
| Giá trị phổ biến | Một `event_type` chiếm khoảng 40–60% bản ghi | Index còn đáng dùng khi độ chọn lọc giảm? |
| Tenant nóng | Một số ít tenant có số sự kiện cao hơn nhiều tenant khác | Partition size, p99, request đến replica có bị lệch? |

Ví dụ: sinh 100 tenant, 14 ngày, khoảng 500–2.000 sự kiện mỗi tenant/ngày ở thử nghiệm chức năng/ban đầu; tạo thêm kịch bản tenant lớn để kiểm tra giới hạn. Con số chỉ là **đầu vào đề xuất để thiết kế test**, không phải thông số chuẩn của Cassandra. Trước khi dùng kết quả để quyết định production, hãy mô phỏng đúng cardinality, payload size, write rate, TTL và phân phối dữ liệu của hệ thống.

Yêu cầu khi seed:

1. Mỗi sự kiện có cùng `tenant_id`, `day_bucket`, `event_type`, `occurred_at`, `event_id` và `payload` trong **cả hai bảng**.
2. Bảo đảm `event_id` phân biệt hàng có cùng timestamp; lưu ý khóa chính khác nhau nên cùng dữ liệu được phân nhóm khác nhau.
3. Sinh payload có kích thước đại diện; không chỉ ghi các chuỗi 1 byte nếu production có payload hàng KB.
4. Hoàn tất toàn bộ ghi **trước khi đo đọc**; nếu đo mixed workload, đó là benchmark riêng.
5. Đợi quá trình tạo index hoàn tất và dữ liệu có thể truy vấn; việc vừa tạo index vừa benchmark khiến kết quả không ổn định.
6. Nếu có TTL, delete và tombstone, dựng kịch bản riêng; không pha trộn ngẫu nhiên khiến hai bảng có trạng thái khác nhau.
7. Lưu seed, cấu hình và tham số random để chạy lại cùng tập test.

Với hai bảng duy trì bằng application-side dual writes, phải kiểm tra dữ liệu đã nhất quán trước benchmark. Cassandra không tự tạo transaction ACID nhiều bảng cho mọi chuỗi ghi ứng dụng; dữ liệu thiếu ở một bảng sẽ làm sai cả kết quả lẫn số đo.

## 4. Xác minh tính đúng trước khi bấm đồng hồ

Trước phép đo, chọn một tập key mẫu (`tenantId`, `dayBucket`, `eventType`) và kiểm tra:

```text
Seed 2 bảng cùng logical events
               |
               v
Đọc A + đọc B với cùng key
               |
               v
So sánh tập event_id, các cột và số hàng
       |                         |
      Khớp                     Không khớp
       |                         |
       v                         v
Đo latency               Dừng, sửa dữ liệu/query
```

Trong khi benchmark đo thời gian, không cần so toàn bộ payload mỗi request vì thao tác so tập dữ liệu có thể làm nhiễu số đo; có thể xác minh đầy đủ trước mỗi đợt chạy và đếm số hàng trong timed path. Việc kiểm tra trước benchmark cũng nên xác minh Query B thực sự đi qua **index hợp lệ**, không có `ALLOW FILTERING`, và SQL thực tế đang chạy đúng schema đã định nghĩa.

Những lỗi hay gặp khi chỉ viết mock test hoặc gọi repository giả:

- Repository mock trả 100 entity không chứng minh CQL có đủ partition key.
- Một điều kiện `WHERE` trên cột không thuộc khóa hay chỉ mục có thể bị Cassandra từ chối.
- Sự tương đương về kết quả không chứng minh hai đường truy vấn có cùng lượng I/O.
- Entity mapping có thể thêm chi phí converter/DTO mà driver benchmark trực tiếp không phản ánh.
- Kết quả từ vài chục hàng không thể đại diện cho partition lớn với tombstone.

## 5. Đo riêng từ Java Driver bằng cùng một harness

Để tập trung vào **chi phí truy vấn + truyền dữ liệu + driver**, trước tiên đo bằng `CqlSession`, dùng prepared statements cho cả hai đường. Đặt cùng mức consistency, page size và request timeout (nếu thay đổi mặc định) để tránh khác biệt do cấu hình client.

Ví dụ dưới đây là phần benchmark tối giản cho Java 17+, DataStax Java Driver 4 và Cassandra 5.0. Giả sử đã tạo schema, nạp cùng dữ liệu và có `CqlSession session` kết nối đến đúng cụm:

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Random;
import java.util.UUID;

public final class CassandraReadBenchmark {

    public record Key(UUID tenantId, LocalDate day, String type) {}

    public record Sample(long nanos, int rows) {}

    private static final String BY_KEY = """
            SELECT event_id, occurred_at, payload
            FROM perf.events_by_tenant_day_type
            WHERE tenant_id = ?
              AND day_bucket = ?
              AND event_type = ?
            """;

    private static final String BY_INDEX = """
            SELECT event_id, occurred_at, payload
            FROM perf.events_by_tenant_day
            WHERE tenant_id = ?
              AND day_bucket = ?
              AND event_type = ?
            """;

    private static Sample measure(
            CqlSession session,
            PreparedStatement prepared,
            Key key) {

        BoundStatement stmt = prepared.bind(
                key.tenantId(), key.day(), key.type())
                .setPageSize(128);

        long start = System.nanoTime();
        ResultSet result = session.execute(stmt);

        int rowCount = 0;
        for (Row row : result) {
            // Đọc giá trị thật để bao gồm cả decode và fetch các trang.
            row.getUuid("event_id");
            row.getInstant("occurred_at");
            row.getString("payload");
            rowCount++;
        }

        return new Sample(System.nanoTime() - start, rowCount);
    }

    private static double percentileMs(List<Long> values, double p) {
        List<Long> sorted = new ArrayList<>(values);
        sorted.sort(Comparator.naturalOrder());
        int index = Math.max(0,
                (int) Math.ceil(sorted.size() * p) - 1);
        return sorted.get(index) / 1_000_000.0;
    }

    public static void run(
            CqlSession session, List<Key> validKeys) {

        if (validKeys.isEmpty()) {
            throw new IllegalArgumentException("Cần key thử nghiệm");
        }

        PreparedStatement byKey = session.prepare(BY_KEY);
        PreparedStatement byIndex = session.prepare(BY_INDEX);

        Random random = new Random(20261125L);

        // Warmup cả hai đường, dữ liệu phải được seed từ trước.
        for (int i = 0; i < 1_000; i++) {
            Key key = validKeys.get(
                    random.nextInt(validKeys.size()));
            measure(session, byKey, key);
            measure(session, byIndex, key);
        }

        List<Long> keyNs = new ArrayList<>();
        List<Long> indexNs = new ArrayList<>();

        // Đảo thứ tự A/B để tránh luôn ưu tiên A trong cache.
        for (int i = 0; i < 10_000; i++) {
            Key key = validKeys.get(
                    random.nextInt(validKeys.size()));
            Sample a, b;

            if (random.nextBoolean()) {
                a = measure(session, byKey, key);
                b = measure(session, byIndex, key);
            } else {
                b = measure(session, byIndex, key);
                a = measure(session, byKey, key);
            }

            if (a.rows() != b.rows()) {
                throw new IllegalStateException(
                        "Số hàng A/B không khớp cho " + key);
            }

            keyNs.add(a.nanos());
            indexNs.add(b.nanos());
        }

        System.out.printf(
                "By key:   p50=%.3f ms, p95=%.3f ms, p99=%.3f ms%n",
                percentileMs(keyNs, 0.50),
                percentileMs(keyNs, 0.95),
                percentileMs(keyNs, 0.99));

        System.out.printf(
                "By index: p50=%.3f ms, p95=%.3f ms, p99=%.3f ms%n",
                percentileMs(indexNs, 0.50),
                percentileMs(indexNs, 0.95),
                percentileMs(indexNs, 0.99));
    }
}
```

Ví dụ đặt `pageSize=128` và **duyệt hết ResultSet**, tức thời gian tính cả fetch các page tiếp theo khi có hơn 128 hàng. Nếu chỉ đo thời gian `session.execute(...)` rồi bỏ qua việc lấy hết dữ liệu, phép đo có thể chỉ phản ánh thời gian lấy trang đầu; không phù hợp khi API thực cần toàn bộ kết quả.

Các giới hạn của harness này:

- **Đo tuần tự một luồng**, phù hợp cho baseline latency, **không đo throughput khi concurrency cao**.
- Dùng `System.nanoTime()` để đo duration trong process, không suy từ timestamp đồng hồ hệ thống.
- Đã có warmup nhưng không tạo được một “cold-cache run” thật sự; Cassandra, OS và driver có nhiều lớp cache.
- `Random(20261125L)` giúp lặp thứ tự workload, nhưng không biến dữ liệu thành workload production.
- `rows()` chỉ so sánh số hàng trong vòng đo; bước kiểm thử đúng dữ liệu phải so `event_id` và giá trị trước đó.
- Số vòng 1.000 và 10.000 là **ví dụ khởi đầu**; p99 cần đủ sample, chạy nhiều lần và đọc thêm khoảng biến thiên. Không xem một kết quả duy nhất là định luật.
- Trong benchmark ở tải cao, nên dùng công cụ workload/load test chuyên dụng hoặc harness bất đồng bộ có concurrency kiểm soát để tránh giới hạn của một thread.

### Thêm read path của Spring Data

Khi dùng `CassandraRepository`, `CassandraTemplate` hoặc `CassandraOperations` trong code sản xuất, nên đo thêm **độ trễ tại API/service** vì Java Driver benchmark chưa bao gồm mọi chi phí Spring mapping, conversion, validation và xây DTO.

Ví dụ fragment có hai phương thức:

```java
public interface EventSearchFragment {

    List<EventView> byPartitionKey(
            UUID tenantId, LocalDate day, String eventType);

    List<EventView> byIndex(
            UUID tenantId, LocalDate day, String eventType);
}
```

Implementation có thể sử dụng `CassandraOperations` (khi mapping/Query API phù hợp) hoặc `CqlSession` để kiểm soát CQL, consistency và page size chi tiết. Trong test đo hiệu năng, gọi **implementation thật trên Cassandra thật**; mock repository chỉ phù hợp kiểm tra tham số hoặc nhánh nghiệp vụ, không đo chi phí database.

Một cách đo latency nhìn từ ứng dụng với Micrometer:

```java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public List<EventView> fetchByIndex(
        UUID tenantId, LocalDate day, String type) {

    Timer.Sample sample = Timer.start(registry);
    try {
        return eventSearch.byIndex(tenantId, day, type);
    } finally {
        sample.stop(registry.timer(
                "cassandra.application.read",
                "path", "indexed",
                "operation", "events_by_type"));
    }
}
```

Trong ví dụ trên, `registry` là `MeterRegistry` được inject, và `eventSearch` là fragment thực. Mã chỉ minh họa phương pháp đo; cần đưa vào một class có dependency phù hợp. Một đường đo tương tự với tag `path=partition_key` giúp so ở tầng ứng dụng. Nên cấu hình histogram/percentiles đúng nhu cầu quan sát của hệ thống và giới hạn tag có cardinality thấp; **không đưa tenant_id hoặc raw CQL vào metric tags**.

## 6. Những biến số phải giữ ổn định

Một benchmark có ý nghĩa cần cố định hoặc ghi rõ các biến sau:

| Biến số | Vì sao ảnh hưởng kết quả? | Cách kiểm soát |
| --- | --- | --- |
| Cùng dataset logic | Khác số hàng/bytes làm latency không tương đương | Seed đồng nhất; so count và event IDs trước test |
| Độ chọn lọc `event_type` | Loại hiếm và loại phổ biến tạo số candidate khác nhau | Tách cohort 1%, 10%, 50%, không trộn số |
| Partition size | Đọc partition lớn khác partition nhỏ | Ghi phân phối kích thước và bucket |
| Payload/projection | Trả nhiều byte làm thay đổi truyền mạng và deserialize | Dùng cùng danh sách cột, cùng cỡ payload |
| Consistency level | `LOCAL_ONE` và `LOCAL_QUORUM` có chi phí/đảm bảo khác nhau | Chọn theo workload, áp dụng giống nhau cho cả hai |
| Page size và `LIMIT` | Xác định số lần fetch và hàng trả | Thiết lập giống nhau, đếm toàn bộ hàng đã tiêu thụ |
| Driver và pool | Connection pool, warmup, speculative execution tác động latency | Dùng cùng session/config; ghi cấu hình |
| Cache/memtable | Dữ liệu mới ghi khác dữ liệu đã flush/compaction | Tách warm/cold-ish workloads; ghi điều kiện |
| Concurrent writes | Ghi và index maintenance có thể làm tăng read latency | Đo read-only và mixed load thành hai đợt |
| Node placement | Replica, network, rack, coordinator ảnh hưởng thời gian | Dùng cùng cụm và topology đại diện |
| Tenant skew | Hot tenant gây tail latency | Tạo cohort tenant thường/tenant nóng riêng |
| Timeout/errors | Loại bỏ các request lỗi làm kết quả “đẹp” giả | Ghi error rate, timeout count và retry cùng latency |

**Đừng vô tình thay đổi đồng thời nhiều biến** khi muốn biết hiệu ứng của chỉ mục. Chẳng hạn, nếu thay page size, kích thước payload và consistency trong cùng một lần, không thể biết yếu tố nào làm p99 tăng.

## 7. Không chỉ nhìn thời gian trung bình

Chỉ số cần ghi lại cho mỗi đường truy cập:

- **p50**: trường hợp thường gặp của latency.
- **p95, p99**: độ trễ của nhóm request chậm; quan trọng với API có SLA.
- **Throughput**: request/giây ở mức concurrency xác định.
- **Error/timeout rate**: số request thất bại hoặc hết hạn; không bỏ request lỗi khỏi báo cáo.
- **Rows và bytes/request**: kích thước kết quả và chi phí dữ liệu.
- **Pages fetched/request**: số lần driver lấy thêm trang.
- **CPU, disk I/O, GC, compaction, pending tasks, tombstone/read metrics** trên cụm.
- **Sự phân bố theo coordinator và replica** nếu có hotspot hoặc lệch tải.

Bảng báo cáo đề xuất (các ô là **chỗ điền số đo thực tế**, không phải kết quả đo):

| Workload | Read path | p50 (ms) | p95 (ms) | p99 (ms) | RPS | Error % | Rows/req | Ghi chú |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Type hiếm, tenant thường | Partition key | ... | ... | ... | ... | ... | ... | RF/CL/page size |
| Type hiếm, tenant thường | SAI + partition | ... | ... | ... | ... | ... | ... | Cùng bộ key |
| Type phổ biến, tenant thường | Partition key | ... | ... | ... | ... | ... | ... | Cùng bộ key |
| Type phổ biến, tenant thường | SAI + partition | ... | ... | ... | ... | ... | ... | Cùng bộ key |
| Tenant nóng | Partition key | ... | ... | ... | ... | ... | ... | Kích thước partition |
| Tenant nóng | SAI + partition | ... | ... | ... | ... | ... | ... | Index status/metrics |

Nếu thử các mức concurrency 1, 8, 32, 128, cần **bảng riêng hoặc cột ghi concurrency** để tránh so p99 của tải nhẹ với tải nặng. Khi báo throughput, mô tả driver dùng blocking hay async, số thread, rate target và cách kiểm soát **coordinated omission** (không làm mất các request bị trì hoãn khỏi mẫu). Một hệ thống có p50 đẹp nhưng tỷ lệ timeout cao không thể coi là nhanh.

### Client metrics và server metrics trả lời hai câu hỏi khác nhau

**Client-side latency** đo người gọi phải chờ bao lâu; nó gồm thời gian network, coordinator, replica, fetch, driver và có thể Spring mapping. **Server metrics** giúp xác định công việc bên trong Cassandra có bị nặng không. Ví dụ:

- p99 tăng cùng lúc với read latency và CPU/compaction tăng: cần kiểm tra tài nguyên node, partition size, tombstone và maintenance.
- Client p99 tăng nhưng server read latency ổn định: kiểm tra network, thread pool ứng dụng, connection pool hoặc mapping.
- Query index dùng ít hàng trả về nhưng chậm khi loại sự kiện phổ biến: kiểm tra độ chọn lọc, số partition liên quan và index metrics tương ứng với phiên bản Cassandra.

Không suy ra nguyên nhân duy nhất chỉ từ một metric. Cần phối hợp trace request, metrics, cấu hình, dữ liệu và khả năng lặp lại.

## 8. Tracing và phân tích đường truy vấn

Có thể chạy một số truy vấn đại diện với **tracing** để quan sát hoạt động ở coordinator/replica. Trong `cqlsh`:

```sql
TRACING ON;

SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day_type
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND day_bucket = '2026-11-25'
  AND event_type = 'PAYMENT_FAILED';

SELECT event_id, occurred_at, payload
FROM perf.events_by_tenant_day
WHERE tenant_id = 00000000-0000-0000-0000-000000000001
  AND day_bucket = '2026-11-25'
  AND event_type = 'PAYMENT_FAILED';

TRACING OFF;
```

Các literal trên chỉ là **ví dụ cú pháp**; thay bằng key đã seed trước. Tracing có overhead, nên bật cho **một số query chẩn đoán**, không bật cho toàn bộ đợt benchmark. Thông tin trace có thể khác nhau theo phiên bản Cassandra và loại index; xem đây là nguồn bằng chứng hỗ trợ, không thay thế metrics tổng thể.

Nếu có truy vấn bị từ chối do restriction sai hoặc index không tồn tại, hãy sửa CQL/schema hoặc mô hình dữ liệu. Tránh thêm `ALLOW FILTERING` chỉ để phép đo chạy: khi đó bạn có thể đang so query theo partition key với query lọc/quét theo cơ chế khác hẳn.

## 9. Đo cả chi phí ghi và dung lượng

Chọn giữa bảng tối ưu theo partition key và index không thể chỉ dựa trên latency đọc. Cần đo thêm:

**Write amplification.** Nếu hệ thống dùng hai bảng theo hai access pattern, một sự kiện có thể phải ghi nhiều nơi. Việc cập nhật/xóa cũng cần phản ánh ở mọi bảng đọc; sai lệch giữa các bảng có thể xuất hiện nếu một phần ghi thất bại.

**Index maintenance.** Index cần duy trì cấu trúc riêng và có thể ảnh hưởng thời gian ghi, disk usage, compaction hoặc build/rebuild. Mức ảnh hưởng phụ thuộc kiểu index và phiên bản Cassandra.

**Storage overhead.** Với bảng phục vụ thêm access pattern, dữ liệu lặp lại; với SAI, index chiếm dung lượng riêng. So sánh tổng disk usage, compaction, GC và chi phí vận hành, không chỉ số hàng logic.

**Change rate và TTL.** Workload ghi đè, xóa, TTL cao tạo tombstone và có thể tác động đến cả hai đường đọc. Một benchmark chỉ INSERT rồi SELECT không mô tả đầy đủ hệ thống có nhiều delete/update.

Có thể tổ chức ba pha độc lập:

1. **Read-only:** seed xong, chờ môi trường ổn định, đo hai read path.
2. **Mixed read/write:** giữ tỉ lệ ghi/đọc giống thực tế, đo lại p95/p99/error và throughput.
3. **Maintenance/aging:** đo sau một thời gian TTL/delete/compaction, theo dõi kích thước index và partition.

Không diễn giải chênh lệch chỉ mục khi quá trình build index hoặc seed vẫn đang chạy như trạng thái vận hành bình thường.

## 10. Khi nào nên chọn partition-key table, khi nào cân nhắc index?

| Tình huống | Hướng thiết kế thường phù hợp | Cần xác minh |
| --- | --- | --- |
| Truy vấn rất phổ biến, điều kiện lọc ổn định và SLA chặt | Bảng đọc theo partition key đúng access pattern | Cỡ partition, số bảng ghi bổ sung và chi phí đồng bộ |
| Nhiều bộ lọc linh hoạt, thuộc tính có chọn lọc cao | Cân nhắc SAI trên phiên bản hỗ trợ | Độ chọn lọc, số partition, CQL hợp lệ, tail latency |
| Giá trị indexed xuất hiện gần như mọi hàng | Cân nhắc thiết kế bảng/bucket khác | Index có còn giảm công việc đọc không? |
| Tenant hoặc bucket có partition quá lớn | Điều chỉnh partitioning/time bucket | Tác động đến truy vấn nhiều bucket, số request |
| Tìm kiếm toàn văn/xếp hạng phức tạp qua nhiều thuộc tính | Đánh giá hệ tìm kiếm chuyên dụng nếu yêu cầu vượt mô hình CQL | Đồng bộ dữ liệu, độ trễ index, vận hành |
| Nhiều access pattern cố định và đọc nhiều hơn ghi | Có thể dùng nhiều bảng denormalized | Write amplification, consistency giữa bảng |
| Khối lượng ghi lớn, chi phí lưu trữ nghiêm ngặt | Đo đầy đủ index maintenance và số bản sao dữ liệu | Tác động ghi, compaction, disk và p99 đọc |

Không có một ngưỡng tỷ lệ chọn lọc cố định (ví dụ “dưới 5% luôn dùng index”) áp dụng cho mọi hệ thống. Partition size, mức phân tán của candidate rows, loại index, cache và consistency có thể làm kết quả thay đổi đáng kể.

## 11. Những lỗi thường làm benchmark thiếu tin cậy

| Lỗi thiết kế thí nghiệm | Tại sao sai | Cách khắc phục |
| --- | --- | --- |
| Dùng query index toàn cụm so với query theo một partition | Hai access pattern khác nhau, số partition/rows khác nhau | Tách query C thành cohort riêng; so A/B cùng bộ lọc |
| So dữ liệu vừa INSERT với dữ liệu đã có lâu | Cache, memtable và compaction khác trạng thái | Seed xong, ổn định môi trường, ghi điều kiện |
| Chỉ đo `session.execute`, không consume hết hàng | Có thể chưa fetch các trang tiếp theo | Duyệt hết kết quả hoặc đo từng page nhất quán |
| Chỉ lấy average latency | Che khuất tail latency | Báo p50/p95/p99, lỗi và timeout |
| Chỉ dùng một tenant nhỏ | Bỏ sót skew/hot partition | Tạo cohort tenant lớn và dữ liệu lệch |
| Không kiểm tra index đã build | Request đầu có hành vi khác thường hoặc query lỗi | Kiểm tra trạng thái index/readiness trước đo |
| Đổi consistency/page size giữa hai query | So hai cấu hình khác nhau | Cố định config, ghi lại phiên bản/thiết lập |
| Mock `CassandraRepository` | Không gửi request tới Cassandra | Dùng DB thật, mock chỉ cho unit test logic |
| Đo trên một node rồi khẳng định production | Không đại diện replica/network/failure | Đo lại với topology, RF và tải đại diện |
| Chạy tải cao nhưng loại bỏ request timeout | Thống kê đẹp sai lệch | Báo lỗi/timeout và mức tải cùng latency |

## 12. Bài tập thực hành

### Bài 1 — Benchmark cơ bản theo cùng dữ liệu

Tạo hai bảng A/B, SAI và 20.000 sự kiện giả lập đã được ghi giống nhau. Lập danh sách key chỉ có một vài chục kết quả mỗi query; xác minh tập `event_id` bằng nhau. Đo latency từng đường qua `CqlSession` với cùng page size, consistency, connection pool và ba lần chạy độc lập. Lập bảng p50/p95/p99; mô tả điều kiện đo thay vì kết luận chỉ từ một con số.

### Bài 2 — Thử độ chọn lọc

Dùng dữ liệu với `event_type` hiếm (~1%), trung bình (~10%) và phổ biến (~50%). Đo A/B và query C tách biệt. Giải thích vì sao số hàng match và số partition liên quan quan trọng; đối chiếu kết quả với metrics/tracing thực tế.

### Bài 3 — Thay đổi partitioning

Tăng sự kiện của một tenant lên nhiều lần so với các tenant khác. So bucket theo ngày và bucket theo giờ; nêu số partition tạo ra, số query phải thực hiện để đáp ứng “7 ngày gần nhất”, p99 và chi phí gộp dữ liệu.

### Bài 4 — Benchmark qua Spring Data

Viết repository fragment dùng `CassandraOperations` hoặc `CqlSession` cho cả hai đường truy cập. Đo thời gian ở tầng service bằng Micrometer, so với driver baseline, giải thích phần overhead có thể đến từ converter, DTO mapping, serialization hoặc business logic.

### Bài 5 — Chi phí ghi

Giữ tỉ lệ ghi/đọc đại diện, đo write latency, read p99 và storage/compaction metrics cho phương án index so với thêm bảng đọc. Chỉ đưa ra khuyến nghị khi có cả bằng chứng chức năng và chi phí vận hành.

## 13. Checklist báo cáo kết quả

- [ ] Cùng access pattern, cùng dataset logic và cùng projection cho hai đường A/B.
- [ ] Có xác minh cùng tập hàng thực, không chỉ cùng số lượng.
- [ ] Cassandra version, SAI/2i, schema, index readiness và RF/datacenter được ghi rõ.
- [ ] Client config (consistency, page size, timeout, retry, pooling) giống nhau.
- [ ] Đã tách warmup, đo nhiều lần và xáo thứ tự workload để hạn chế thiên lệch.
- [ ] Có p50/p95/p99, throughput, concurrency, error và timeout.
- [ ] Có kích thước partition, độ chọn lọc, số hàng/bytes và trang tải.
- [ ] Có quan sát server CPU/disk/tombstone/index/compaction khi phân tích nguyên nhân.
- [ ] Đã đo riêng query index qua nhiều partition nếu sản phẩm thực sự cần.
- [ ] Đã tính chi phí ghi, storage và nhất quán dữ liệu cho bảng denormalized.
- [ ] Không dựa vào kết quả Mockito, một node hay dữ liệu nhỏ để kết luận hiệu năng production.

**Ghi nhớ:** trong **Spring Data Cassandra**, tối ưu query bắt đầu từ **mô hình dữ liệu theo access pattern**. Đo riêng truy cập theo partition key và truy vấn qua index bằng **cùng workload, cùng kết quả và cùng cấu hình** giúp tìm ra chi phí thật của từng read path. Thêm các phép đo về độ chọn lọc, partition size, paging, p99, metrics cụm và chi phí ghi sẽ cho phép lựa chọn giữa bảng denormalized và chỉ mục một cách có căn cứ, thay vì dựa vào giả định “có index là nhanh” hoặc “truy vấn theo key luôn tốt”.
