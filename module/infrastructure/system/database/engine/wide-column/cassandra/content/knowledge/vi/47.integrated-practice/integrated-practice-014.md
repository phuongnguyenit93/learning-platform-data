# Hoàn thiện sơ đồ, quyết định thiết kế và sổ tay bằng bằng chứng thực nghiệm

Một hệ thống dùng **Apache Cassandra** chỉ thực sự hoàn thiện về mặt kiến trúc khi nhóm có thể giải thích được ba điều: **hệ thống vận hành như thế nào**, **vì sao chọn thiết kế hiện tại**, và **phải làm gì khi giả định ban đầu không còn đúng**. Sơ đồ, bản ghi quyết định kiến trúc (Architecture Decision Record — ADR) và sổ tay vận hành (runbook) phải cùng tham chiếu đến dữ liệu đo, thay vì tồn tại như ba tài liệu độc lập không kiểm chứng được.

Bài thực hành tổng hợp này đặt Cassandra vào một luồng ứng dụng Java, vận dụng kiến thức về **wide-column, partition key, thiết kế bảng theo truy vấn, mức nhất quán, replication, compaction, repair và xử lý lỗi**. Người học sẽ bắt đầu với một thiết kế ứng viên, xây dựng phép thử, rồi cập nhật cả ba loại tài liệu dựa trên kết quả. Các số liệu về tải, SLO và chi phí dưới đây là **giả định của tình huống học tập**; không được coi là benchmark thực tế.

## 1. Đề bài, đầu ra và điều kiện hoàn thành

### 1.1. Tình huống

Một doanh nghiệp vận hành **12.000 cảm biến nhiệt độ kho lạnh**, thuộc nhiều khách hàng và địa điểm. Mỗi cảm biến bình thường gửi một phép đo **15 giây/lần**. Hệ thống có hai API:

- **Q1 — Lịch sử cảm biến:** lấy 100 phép đo gần nhất của một cảm biến và có thể mở rộng sang một khoảng thời gian tối đa 48 giờ.
- **Q2 — Cảnh báo theo kho:** lấy 100 cảnh báo mới nhất của một kho trong một ngày, có thể chuyển trang và xem ngày kế tiếp.

Luồng ghi nhận phép đo dùng hàng đợi hoặc message broker để chịu được lưu lượng dồn; ứng dụng Java ghi dữ liệu vào Cassandra. Một bộ xử lý cảnh báo nhận cùng sự kiện và ghi bảng phục vụ Q2. Vì hai bảng được cập nhật bất đồng bộ, giao diện phải chấp nhận **độ trễ đồng bộ nhỏ đã được định nghĩa**, có kiểm soát retry và trùng lặp.

| Thông số đầu vào | Giá trị giả định |
|---|---|
| Cảm biến | 12.000; trung bình 4 phép đo/phút/cảm biến |
| Tải ghi trung bình | 800 phép đo/giây |
| Tải ghi đỉnh cần thử | 5.000 phép đo/giây trong 30 phút |
| Tải đọc đồng thời khi thử | 300 yêu cầu/giây, gồm Q1 và Q2 |
| Thời gian lưu phép đo | 14 ngày tính từ thời điểm ghi |
| Thời gian lưu cảnh báo | 90 ngày tính từ thời điểm ghi |
| Mục tiêu độ trễ ghi | p99 phía Java client ≤ 100 ms tại tải mục tiêu |
| Mục tiêu độ trễ đọc | p99 phía API ≤ 180 ms tại tải mục tiêu |
| Mục tiêu lỗi khi bình thường | Tỷ lệ yêu cầu lỗi < 0,1% trong cửa sổ đo |
| Thử mất một node | Không mất khả năng phục vụ ngoài ngưỡng lỗi được phê duyệt; phải đo thời gian phục hồi |

**Lưu ý về phép đo:** p99 phía Java client và p99 phía API là hai vị trí đo khác nhau. Muốn kết luận SLO của API đạt, phải đo độ trễ API từ đầu đến cuối, kể cả thời gian hợp nhất kết quả nhiều partition. Đề bài chưa cung cấp ngưỡng lỗi cụ thể khi mất node và thời gian phục hồi: nhóm phải thống nhất hai giá trị đó **trước khi** thực hiện failure test.

### 1.2. Bộ sản phẩm cuối của bài thực hành

| Mã | Sản phẩm | Điều kiện có thể kiểm tra |
|---|---|---|
| D1 | Sơ đồ ngữ cảnh và sơ đồ triển khai phiên bản cuối | Có đường ghi/đọc, phạm vi DC, RF, CL, thành phần retry và điểm quan sát |
| D2 | Bảng truy vết truy vấn → schema → API | Q1/Q2 có partition key và truy vấn CQL phù hợp |
| E1 | Báo cáo thử nghiệm | Ghi workload, môi trường, phép đo, thời gian, lần chạy, kết quả thành công và thất bại |
| A1 | ADR thiết kế dữ liệu/consistency | Ghi các giả định, phương án, bằng chứng E1, quyết định và điều kiện xem xét lại |
| R1 | Runbook thao tác và xử lý sự cố | Nêu trigger, lệnh quan sát, ngưỡng chuyển cấp, tiêu chí khôi phục và người phụ trách |
| T1 | Ma trận truy vết cuối | Chỉ rõ thông số trên D1/D2 được chứng minh bởi phần nào của E1 và ghi ở A1/R1 |

Bài được coi là hoàn thành ở mức thực hành khi người khác có thể **chạy lại thí nghiệm**, tìm bằng chứng cho từng quyết định quan trọng, và theo runbook để chẩn đoán một sự cố mô phỏng. Chưa đủ bằng chứng thì ghi **CHƯA XÁC MINH** thay vì đánh dấu đạt.

## 2. Chốt yêu cầu, giả định và miền lỗi

Trước khi vẽ sơ đồ, nhóm điền một bảng giả định có chủ sở hữu:

| ID | Phát biểu cần kiểm chứng | Rủi ro nếu sai | Nguồn bằng chứng dự kiến |
|---|---|---|---|
| AS-01 | Hầu hết cảm biến gửi 4 bản ghi/phút | Partition lớn bất thường khi cảm biến bị lỗi | Phân bố bản ghi theo sensor_id, p95/p99/max |
| AS-02 | Thiết bị gửi lại cùng event_id khi retry | Cùng sự kiện sinh nhiều hàng | Trace từ producer đến consumer |
| AS-03 | API chỉ đọc theo cảm biến hoặc kho và ngày | Phát sinh truy vấn phải quét dữ liệu | Nhật ký truy vấn và hợp đồng API |
| AS-04 | Chấp nhận cảnh báo xuất hiện chậm hơn phép đo | Mất đồng bộ giữa hai luồng cập nhật | Ngưỡng trễ nghiệp vụ và đo độ trễ end-to-end |
| AS-05 | Một node ngừng hoạt động không làm cụm mất quorum tại DC | Các thao tác LOCAL_QUORUM thất bại | Thử ngắt một node tại staging |
| AS-06 | Retention theo thời điểm ghi, không theo thời điểm cảm biến đo | Sự kiện đến muộn sống lâu hơn mong đợi | Kiểm thử TTL và sự kiện đến muộn |

Phải phân loại **đã xác nhận**, **đang giả định**, **đã bác bỏ** và **chưa kiểm tra**. Nếu AS-02 sai, mọi nhận xét về tính an toàn của retry dựa trên ID ổn định đều phải sửa, kể cả mã Java và runbook.

Ranh giới của bài tập là **một Cassandra datacenter** gồm ba node trên ba miền lỗi độc lập nếu hạ tầng cho phép (ví dụ ba zone). Replication factor **RF = 3**, nhất quán ứng viên cho cả đọc/ghi **LOCAL_QUORUM**. Với ba replica trong cùng DC, LOCAL_QUORUM yêu cầu hai replica phản hồi. Khả năng phục vụ khi mất một node chỉ được công nhận sau phép thử với tải đã định; không suy ra khả năng chịu mất toàn bộ datacenter. Nếu triển khai thật đa DC, cần thiết kế và thí nghiệm riêng cho replication mỗi DC, chính sách chọn local DC và đường failover.

## 3. Sơ đồ kiến trúc ứng viên: vẽ những gì cần đo

### 3.1. Luồng dữ liệu và các điểm quan sát

~~~mermaid
flowchart LR
    S["Cảm biến kho lạnh"] --> C["Collector / Ingest API"]
    C --> B[("Broker: sự kiện có event_id ổn định")]
    B --> W["Java reading writer"]
    B --> A["Java alert detector"]
    W --> D[("Cassandra — dc1, RF=3")]
    A --> D
    U["Dashboard / người dùng"] --> Q["Query API Java"]
    Q --> D
    C -.-> M["Metrics + logs + tracing"]
    W -.-> M
    A -.-> M
    Q -.-> M
    D -.-> M
    M --> O["On-call / runbook"]
~~~

Trong sơ đồ, **broker** thể hiện một hệ thống giao nhận thông điệp theo cơ chế *at least once*; không bắt buộc dùng sản phẩm broker cụ thể để làm bài. Nếu muốn benchmark riêng Cassandra, trình tạo tải Java có thể ghi trực tiếp bằng driver với cùng loại prepared statements. Kết quả benchmark trực tiếp này **không đại diện** cho độ trễ tổng thể của pipeline có broker.

Những đường cần đánh dấu trong bản sơ đồ nộp:

1. **Đường ghi phép đo:** collector → broker → worker → Cassandra; ack thông điệp sau khi đã nhận phản hồi thành công theo chính sách ứng dụng.
2. **Đường tạo cảnh báo:** broker → detector → Cassandra; kết quả có thể trễ hơn phép đo.
3. **Đường đọc:** dashboard → Query API → Cassandra; API chủ động xác định bucket cần đọc và áp giới hạn số trang/truy vấn.
4. **Đường sự cố:** timeout/thông điệp trùng → bounded retry với backoff và jitter; thông điệp không xử lý được → dead-letter queue có cảnh báo và thủ tục xử lý lại.
5. **Đường quan sát:** mỗi yêu cầu mang trace_id; ghi metric độ trễ, timeout, retry, lag của consumer và trạng thái node/compaction.

Đánh dấu **điểm bắt đầu và kết thúc của mỗi phép đo SLO**. Nếu người vận hành chỉ thấy Cassandra read latency nhưng người dùng gặp p99 API cao do fan-out, sơ đồ phải giúp tìm ra phần thời gian bị thiếu.

### 3.2. Triển khai Cassandra và miền lỗi

~~~mermaid
flowchart TB
    J["Ứng dụng Java / driver chọn local DC: dc1"]
    subgraph DC["Cassandra datacenter: dc1 — RF=3"]
        N1["Node 1 — rack/zone A"]
        N2["Node 2 — rack/zone B"]
        N3["Node 3 — rack/zone C"]
        N1 <-->|"Gossip + streaming khi cần"| N2
        N2 <-->|"Gossip + streaming khi cần"| N3
        N3 <-->|"Gossip + streaming khi cần"| N1
    end
    J -->|"Token-aware routing; LOCAL_QUORUM ứng viên"| DC
~~~

Ba node và cách phân chia rack/zone là **đầu vào của mô hình**, không phải cấu hình tự phát sinh từ CQL. Đặt đủ replica vào các miền lỗi cần cấu hình snitch, topology và địa điểm triển khai phù hợp. Sơ đồ thực tế phải bổ sung số CPU/RAM, loại ổ đĩa, mạng, phiên bản Cassandra, phiên bản Java driver, cơ chế backup và vị trí hệ thống giám sát.

Mỗi lần thay đổi schema, RF, consistency, số node hoặc miền lỗi, tăng **phiên bản sơ đồ**. Ghi ngày, người sửa và tham chiếu thí nghiệm mới để tránh trường hợp sơ đồ mô tả hệ thống của nhiều tháng trước.

## 4. Hiện thực hóa các truy vấn bằng wide-column và CQL

### 4.1. Thiết kế bảng từ API

Q1 có bộ lọc **tenant + sensor + ngày**, sắp xếp theo thời gian giảm dần. Chọn partition key gồm ba phần; clustering columns chứa thời gian quan sát và ID sự kiện để tránh đè các sự kiện trùng timestamp. Q2 có bộ lọc **tenant + kho + ngày** và sắp xếp theo thời gian cảnh báo. Một bảng không cần và cũng không nên cố phục vụ cả hai đường truy vấn khác nhau này.

Ví dụ CQL dưới đây dùng datacenter giả định **dc1**:

~~~sql
CREATE KEYSPACE IF NOT EXISTS coldchain
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS coldchain.readings_by_sensor_day (
    tenant_id uuid,
    sensor_id uuid,
    event_day date,
    observed_at timestamp,
    event_id timeuuid,
    temperature_c decimal,
    battery_mv int,
    PRIMARY KEY (
        (tenant_id, sensor_id, event_day),
        observed_at,
        event_id
    )
) WITH CLUSTERING ORDER BY (observed_at DESC, event_id DESC)
  AND default_time_to_live = 1209600;

CREATE TABLE IF NOT EXISTS coldchain.alerts_by_site_day (
    tenant_id uuid,
    site_id uuid,
    alert_day date,
    raised_at timestamp,
    alert_id timeuuid,
    sensor_id uuid,
    severity text,
    description text,
    PRIMARY KEY (
        (tenant_id, site_id, alert_day),
        raised_at,
        alert_id
    )
) WITH CLUSTERING ORDER BY (raised_at DESC, alert_id DESC)
  AND default_time_to_live = 7776000;
~~~

Với bảng Q1, **1209600 giây = 14 ngày**; với Q2, **7776000 giây = 90 ngày**. TTL mặc định được tính từ **thời điểm ghi**, không phải từ observed_at/raised_at. Khi retry hoặc cập nhật, thời điểm hết hạn của các ô dữ liệu có thể thay đổi. Yêu cầu pháp lý hoặc nghiệp vụ dựa trên thời gian phát sinh sự kiện phải được giải quyết bằng chính sách retention riêng, không suy từ TTL mặc định.

Mọi cột thuộc primary key phải có giá trị. **event_id và alert_id là timeuuid**, không phải UUID phiên bản 4 bất kỳ. Với cơ chế at least once, cùng sự kiện nghiệp vụ phải giữ ổn định ID/partition key và giá trị ghi khi gửi lại; nếu tạo timeuuid mới sau timeout thì Cassandra lưu một hàng mới thay vì ghi lại hàng cũ.

Hai truy vấn CQL điển hình:

~~~sql
CONSISTENCY LOCAL_QUORUM;

-- Q1: 100 phép đo mới nhất trong bucket ngày được chỉ định
SELECT observed_at, event_id, temperature_c, battery_mv
FROM coldchain.readings_by_sensor_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND sensor_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
LIMIT 100;

-- Q2: 100 cảnh báo mới nhất tại một kho trong bucket ngày
SELECT raised_at, alert_id, sensor_id, severity, description
FROM coldchain.alerts_by_site_day
WHERE tenant_id = 11111111-1111-1111-1111-111111111111
  AND site_id = 33333333-3333-3333-3333-333333333333
  AND alert_day = '2026-11-21'
LIMIT 100;
~~~

**Truy vấn xuyên nhiều ngày:** API cần tính các giá trị event_day hoặc alert_day liên quan, gọi lần lượt hoặc song song **có giới hạn**, phân trang và hợp nhất kết quả. LIMIT 100 áp cho **mỗi truy vấn partition**, không tự bảo đảm toàn bộ kết quả 48 giờ chỉ có 100 dòng. Khi cần lấy đúng 100 bản ghi mới nhất toàn khoảng thời gian, API phải sắp xếp/hợp nhất theo observed_at và event_id rồi giới hạn kết quả cuối. Nên chặn khoảng thời gian quá lớn ngay tại API để tránh fan-out ngoài dự kiến.

### 4.2. Đường ghi Java có khả năng gửi lại an toàn

Ví dụ Java Driver 4.x sau chủ ý nhận session đã được cấu hình ở tầng ứng dụng; trong môi trường thật, session nên được tái sử dụng và đóng khi dừng ứng dụng:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.UUID;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;

public final class SensorReadingRepository {
    private final CqlSession session;
    private final PreparedStatement insert;

    public SensorReadingRepository(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO coldchain.readings_by_sensor_day " +
            "(tenant_id, sensor_id, event_day, observed_at, " +
            "event_id, temperature_c, battery_mv) VALUES (?, ?, ?, ?, ?, ?, ?)"
        );
    }

    public CompletionStage<AsyncResultSet> save(
            UUID tenantId, UUID sensorId, Instant observedAt,
            UUID stableTimeUuid, BigDecimal temperatureC, int batteryMv) {
        LocalDate utcDay = observedAt.atZone(ZoneOffset.UTC).toLocalDate();
        BoundStatement statement = insert.bind(
            tenantId, sensorId, utcDay, observedAt,
            stableTimeUuid, temperatureC, batteryMv
        ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
         .setIdempotent(true);
        return session.executeAsync(statement);
    }
}
~~~

Chỉ đặt **setIdempotent(true)** khi cùng lần thử lại dùng **đúng khóa và dữ liệu**, không có counter, phép cộng hoặc tác dụng phụ khác không lặp an toàn. Đặc biệt, producer phải tạo và lưu **stableTimeUuid phiên bản 1 (timeuuid)** một lần cho sự kiện; repo không tự tạo ID sau mỗi lần thử. Dù primary key giữ nguyên, retry ở thời điểm khác có thể làm mới TTL; nếu cần hết hạn theo mốc cố định, phải thiết kế thêm cơ chế xác định expiry.

Đối với worker dùng broker: chỉ xác nhận offset sau khi nhận biết thành công theo CL được chọn; khi WRITE_TIMEOUT, **không mặc định thao tác chưa ghi**. Cần sử dụng khóa idempotency ổn định, giới hạn số lần retry, backoff, jitter, giám sát retry và dead-letter queue. Đừng gộp hai ghi vào hai bảng thành một “giao dịch ACID” giả định. Cassandra không cung cấp isolation của giao dịch nhiều bảng như RDBMS; tính đúng đắn của cảnh báo bất đồng bộ dựa vào hợp đồng sự kiện và quy trình đối soát.

### 4.3. Biến số kiến trúc cần so sánh

| Ký hiệu | Partition lịch sử | Ưu điểm có thể có | Điểm dễ thất bại |
|---|---|---|---|
| V1 | (tenant_id, sensor_id, event_day) | Ít bucket cho Q1 xuyên 48 giờ | Sensor tăng tải đột biến làm partition ngày quá lớn |
| V2 | (tenant_id, sensor_id, event_hour) | Giới hạn kích thước partition tốt hơn khi sensor “nóng” | Q1 qua 48 giờ có thể phải đọc đến 48 bucket |
| V3 | Bucket ngày + shard tính từ thuộc tính ổn định | Phân tán tải của sensor rất nóng | API phải đọc nhiều shard và hợp nhất, tăng chi phí |

V2 và V3 là **các phương án để thử**, không phải code triển khai đầy đủ trong ví dụ V1. Nếu chọn V2/V3, phải sửa schema, câu truy vấn, chiến lược truy hồi và kế hoạch chuyển dữ liệu; không thể đổi partition key của bảng hiện hữu bằng ALTER TABLE.

## 5. Viết kế hoạch thực nghiệm trước khi đo

### 5.1. Ma trận giả thuyết → phép thử → tiêu chí

| Mã thử | Giả thuyết cần bác bỏ | Thao tác | Tiêu chí ví dụ |
|---|---|---|---|
| EXP-01 | V1 phục vụ Q1/Q2 ở tải bình thường | Replay 800 ghi/s và 300 đọc/s bằng truy vấn thật | p99 ghi ≤ 100 ms, p99 API đọc ≤ 180 ms, lỗi < 0,1% |
| EXP-02 | V1 chịu được đỉnh 5.000 ghi/s | Tăng tải trong 30 phút, giữ hỗn hợp Q1/Q2 | Không vượt ngưỡng độ trễ/lỗi đã chốt |
| EXP-03 | Partition phù hợp cả khi lệch tải | Tạo sensor nóng 100 ghi/s trong một ngày tương đương | p99/max partition dưới ngân sách đã duyệt |
| EXP-04 | LOCAL_QUORUM hoạt động khi mất một node | Dừng có kiểm soát một node ở staging; tiếp tục workload | Lỗi và độ trễ nằm trong ngưỡng failure-mode được duyệt |
| EXP-05 | TTL/compaction không sinh backlog kéo dài | Quan sát nhiều chu kỳ flush/compaction và dữ liệu có TTL | Dung lượng/compaction backlog ổn định theo mô hình |
| EXP-06 | Retry không tạo bản ghi nghiệp vụ trùng | Gây timeout/đọc lại message với cùng event_id | Một sự kiện được biểu diễn bằng một primary key |
| EXP-07 | Q1 qua 48 giờ có chi phí chấp nhận được | Đọc 2 ngày V1, so sánh V2 hoặc V3 ở cùng dữ liệu | Tổng latency API và request fan-out đạt ngân sách |
| EXP-08 | Sổ tay khôi phục dùng được | Diễn tập một lỗi timeout, một lỗi node, một lỗi compaction | Có thời gian chẩn đoán, hành động và xác nhận phục hồi |

**Ngân sách partition không có hằng số chung cho mọi Cassandra.** Chọn một ngưỡng thử ban đầu theo hardware và tỷ lệ phân mảnh, chẳng hạn mục tiêu nội bộ **max < 256 MiB**, ghi rõ đây là giả thuyết cần kiểm chứng với phiên bản Cassandra và loại truy vấn cụ thể. Không coi 256 MiB là giới hạn được Cassandra bảo đảm. Tương tự, phải đo cả partition của **alerts_by_site_day**: một kho sinh rất nhiều cảnh báo cũng có thể trở thành điểm nóng, dù các partition phép đo phân bố đều. Với mô hình dữ liệu giả định 400 byte/phép đo:

~~~text
Bình thường: 4 * 60 * 24 = 5.760 phép đo/sensor/ngày
Payload bình thường/sensor/ngày ≈ 5.760 * 400 B ≈ 2,20 MiB

Sensor nóng 100 phép đo/giây:
Payload/ngày = 100 * 86.400 * 400 B ≈ 3,22 GiB
Payload/giờ = 100 * 3.600 * 400 B ≈ 137 MiB
~~~

Đây chỉ là **payload logic**, chưa bao gồm metadata, storage overhead và ảnh hưởng compaction. Nếu thí nghiệm cho thấy sensor nóng duy trì được tải này, V1 nhiều khả năng cần xem xét lại; V2 giảm kích thước partition một giờ nhưng tăng số bucket phải đọc. Kết luận cuối cùng cần dữ liệu benchmark chứ không chỉ phép tính.

### 5.2. Quy trình chạy để so sánh công bằng

1. **Đóng băng cấu hình:** ghi version Cassandra/driver, cấu hình heap/GC, CPU/RAM, IOPS, số node, snitch, RF, CL, retry, timeout, page size, schema, TTL, compaction strategy và hash commit của bộ tạo tải.
2. **Định nghĩa dữ liệu:** số tenant/site/sensor, phân bố nóng/lạnh, kích thước payload, tỷ lệ sự kiện muộn, thứ tự thời gian và tỷ lệ cảnh báo. Bộ dữ liệu phải đủ lớn để hiện tượng partition và compaction có thể xuất hiện.
3. **Đo trạng thái ban đầu:** nodetool status, dung lượng đĩa, GC, pending compactions, các metric về đọc/ghi và consumer lag.
4. **Warm-up và tải ổn định:** loại bỏ nhiễu khởi động, chạy đủ lâu để thấy flush/compaction; không dùng vài phút chạy thành công để kết luận retention 14 hoặc 90 ngày.
5. **Chạy các biến thể:** V1 và V2/V3 trên dataset, phần cứng, CL và điều kiện khởi tạo tương đương. Thay **một nhóm biến thiết kế** mỗi lần, ghi rõ những gì khác.
6. **Lặp thí nghiệm:** ít nhất vài lần độc lập, ghi p50/p95/p99, throughput, lỗi, sử dụng đĩa, CPU và backlog; giải thích các kết quả ngoại lệ.
7. **Inject failure ở staging:** chỉ thực hiện khi đã có khả năng khôi phục và quyền vận hành; ghi thời điểm tắt/rejoin node, toàn bộ lỗi và thời gian hồi phục.
8. **Đóng gói bằng chứng:** xuất raw metric, trace đã ẩn dữ liệu nhạy cảm, cấu hình, log, ảnh đồ thị, commit và người chạy. Không thay raw data khi chỉnh báo cáo.

Không đổi cả CL và partition strategy trong một phép so sánh rồi kết luận nguyên nhân do partition strategy. Nếu cần kiểm tra LOCAL_ONE so với LOCAL_QUORUM, tạo **một thí nghiệm khác** cùng dataset, ghi rõ khác biệt về độ mới dữ liệu và khả năng chịu lỗi.

### 5.3. Metric, lệnh quan sát và nguồn tin

| Lớp | Quan sát ưu tiên | Nguồn |
|---|---|---|
| API/driver | p50/p95/p99 theo Q1/Q2, timeout, retry, số request fan-out | OpenTelemetry/APM, metric Java driver |
| Ingest | End-to-end event lag, queue depth, DLQ, duplicate event_id | Broker và ứng dụng |
| Cassandra write/read | Latency, timeout/unavailable, pending tasks, dropped messages | JMX/metrics, nodetool |
| Node | CPU, heap, GC, đĩa, mạng, disk saturation | Node exporter, JMX, hạ tầng |
| SSTable/partition | SSTable count, tombstone, partition size, pending compactions | tablestats, compactionstats, metric riêng |
| Khôi phục | Thời gian node trở lại, backlog/hints/repair và p99 sau sự cố | Timeline sự cố, nodetool, metrics |

Các lệnh **quan sát**, không thay đổi dữ liệu:

~~~bash
nodetool status
nodetool tablestats coldchain.readings_by_sensor_day
nodetool tablestats coldchain.alerts_by_site_day
nodetool tpstats
nodetool compactionstats
nodetool netstats
~~~

Một số tùy chọn nodetool và metric khác nhau theo phiên bản Cassandra; hãy ghi đúng phiên bản môi trường và kiểm tra trợ giúp lệnh khi áp dụng. **nodetool status** cho biết trạng thái node, không thay thế phép đo tỷ lệ request thành công. **nodetool tablestats** là chỉ số tổng hợp; muốn đánh giá p99/max partition và sensor nóng, cần thêm thống kê khóa/phân phối từ tập dữ liệu hoặc công cụ chuyên dụng phù hợp phiên bản.

Ví dụ lược đồ dữ liệu thô cho một lần chạy:

~~~csv
run_id,at_utc,commit,schema,rf,cl_read,cl_write,write_rps,read_rps,node_failure,read_p99_ms,write_p99_ms,error_pct,partition_max_MiB,compaction_pending,disk_used_GiB
EXP-01-R1,YYYY-MM-DDTHH:MM:SSZ,<commit>,V1,3,LOCAL_QUORUM,LOCAL_QUORUM,800,300,false,<measured>,<measured>,<measured>,<measured>,<measured>,<measured>
~~~

Chuỗi **<measured>** là chỗ điền số đo; hàng này là **mẫu**, không phải kết quả thí nghiệm. Lưu thêm raw histogram cho p99, độ dài cửa sổ quan sát và tỷ lệ thành công theo loại truy vấn; nếu chỉ lưu một giá trị p99 tổng hợp, rất khó giải thích hiện tượng tail latency.

## 6. Phân tích consistency, replication và đường phục hồi

Với RF = 3 trong dc1, LOCAL_QUORUM yêu cầu **2 phản hồi trong 3 replica** cho thao tác thông thường. Khi một replica không sẵn sàng, vẫn còn khả năng đạt quorum nếu hai replica còn lại đáp ứng kịp. Tuy nhiên tài nguyên của hai node còn lại, mạng, tốc độ repair, topology và timeout có thể khiến SLO không đạt ngay cả khi thao tác về mặt lý thuyết đủ replica.

Trong điều kiện không có ghi cạnh tranh bất thường, lựa chọn ghi W = 2 và đọc R = 2 tạo giao nhau vì **R + W > RF**. Đây là cơ sở lập luận cho LOCAL_QUORUM, **không** biến toàn bộ ứng dụng thành giao dịch linearizable: cần cân nhắc last-write-wins, xung đột timestamp, retry, sự kiện đến muộn và cập nhật nhiều bảng. Nếu cần kiểm tra và cập nhật điều kiện, nghiên cứu lightweight transaction (LWT) và đo chi phí riêng.

### 6.1. Kịch bản lỗi phải thể hiện trong sơ đồ

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant W as Java worker
    participant C as Cassandra
    participant O as Observability
    B->>W: event_id ổn định
    W->>C: INSERT, LOCAL_QUORUM
    alt Nhận xác nhận thành công
        C-->>W: OK
        W-->>B: ACK message
    else WRITE_TIMEOUT / kết quả chưa chắc chắn
        C--xW: Timeout
        W->>O: Metric + trace + retry count
        W->>C: Retry có giới hạn, cùng khóa và payload
        alt Được xác nhận
            C-->>W: OK
            W-->>B: ACK message
        else Hết ngưỡng retry
            W->>O: Cảnh báo / đánh dấu DLQ
        end
    end
~~~

**Timeout không có nghĩa Cassandra chưa ghi.** Một số replica có thể đã ghi thành công trước khi client hết thời gian chờ. Nếu cùng event_id bị tái tạo thành ID khác, luồng retry có thể tạo dữ liệu trùng. Trong báo cáo EXP-06 cần kiểm tra ít nhất: số ID duy nhất đầu vào, số primary key xuất hiện sau retry, số sự kiện vào DLQ và số lần gửi lại.

### 6.2. Compaction, TTL, tombstone và repair là một quyết định liên quan

Khi đo V1/V2, ghi rõ compaction strategy đang chạy:

- **SizeTieredCompactionStrategy (STCS):** thường hợp luồng ghi nhiều; có thể gây khuếch đại đọc khi nhiều SSTable.
- **LeveledCompactionStrategy (LCS):** có thể giảm SSTable cần đọc nhưng tăng chi phí compaction/ghi; phải đo I/O.
- **TimeWindowCompactionStrategy (TWCS):** ứng viên cho chuỗi thời gian có TTL tương đồng và dữ liệu chủ yếu ghi theo thời gian; ghi đến muộn hoặc cập nhật nhiều tuổi dữ liệu có thể làm việc thu hồi SSTable hết hạn kém hiệu quả.

Không kết luận TWCS tốt nhất chỉ vì hệ thống có timestamp. Theo dõi tombstone và backlog qua nhiều chu kỳ dữ liệu. **gc_grace_seconds** liên quan đến khả năng chống dữ liệu đã xóa xuất hiện lại khi replica bỏ lỡ thao tác xóa; thay đổi nó phải gắn với tính đúng đắn của repair, SLA phục hồi node và phiên bản Cassandra. TTL hết hạn không đồng nghĩa byte trên đĩa biến mất ngay: dữ liệu có thể còn đến khi compaction đủ điều kiện dọn.

**Repair** có mục tiêu đồng bộ các replica sau mất kết nối/đứt quãng và nằm trong quy trình vận hành. Không chạy repair quy mô lớn một cách máy móc khi chưa biết trạng thái node, khoảng thời gian hỏng, tài nguyên đĩa/mạng và quy trình bảo trì. Trong thực hành, nhóm phải thiết kế lịch repair theo phiên bản/topology và diễn tập trên staging trước khi đưa lệnh thực thi vào runbook production.

## 7. Tính chi phí để kết luận dựa trên hiệu năng lẫn khả năng vận hành

Lấy kích thước trung bình **400 byte dữ liệu logic/phép đo** làm giả định:

~~~text
events/day = 12.000 sensors * 4/min * 1.440 min = 69.120.000
logical_data/day = 69.120.000 * 400 B ≈ 25,75 GiB
logical_data/14 days ≈ 360,49 GiB ≈ 0,352 TiB
replicated_data/RF3 ≈ 1,056 TiB
~~~

Nếu để minh họa ta giả sử overhead trên đĩa bằng **1,30 lần dữ liệu logic đã nhân bản** và chỉ sử dụng tối đa **60% dung lượng cấp phát** nhằm giữ headroom:

~~~text
provisioned_total ≈ 1,056 TiB * 1,30 / 0,60 ≈ 2,29 TiB
provisioned_per_node (3 node đều nhau) ≈ 0,76 TiB
~~~

Hai hệ số **1,30** và **60%** không phải quy tắc phổ quát. Thực tế chịu tác động của nén, overhead bảng, index, tombstone, compaction, sửa chữa, snapshot và tốc độ tăng dữ liệu. Bảng cảnh báo giữ 90 ngày **chưa được cộng** vì chưa có tỷ lệ cảnh báo/payload; cần đo và bổ sung trước khi đặt mua tài nguyên. Nếu chọn V3 hoặc thêm bảng phục vụ truy vấn, tính riêng số byte ghi thêm và tác động lên CPU/disk.

Mẫu bảng chi phí cho bản nộp:

| Hạng mục | Công thức hoặc cách đo | V1 ngày | V2 giờ | V3 ngày + shard |
|---|---|---|---|---|
| Storage thực đo | used GiB theo node, gồm compaction overhead | Chưa đo | Chưa đo | Chưa đo |
| CPU/IOPS ở p99 tải | metric node trong cùng cửa sổ | Chưa đo | Chưa đo | Chưa đo |
| Request fan-out Q1/48h | số partition/page truy cập | Tối đa 2 bucket ngày | Tối đa 48 bucket giờ | Phụ thuộc số shard |
| Độ trễ API p99 | cùng workload + CL | Chưa đo | Chưa đo | Chưa đo |
| Giờ công vận hành | repair, xử lý hotspot, on-call | Ước tính có nguồn | Ước tính có nguồn | Ước tính có nguồn |
| Rủi ro migration | backfill, dual-write, rollback | Thấp ở hệ thống mới | Phải xác minh | Phải xác minh |

Tổng chi phí sở hữu phải bao gồm **node và storage, mạng, backup, quan sát, thời gian trực vận hành, sửa lỗi và migration**. Nếu nhà cung cấp đã tính storage vào giá node thì không cộng trùng. Chi phí triển khai lại table hoặc backfill dữ liệu thường là phần bị quên khi phương án mới nhìn có vẻ rẻ hơn.

## 8. Chuyển bằng chứng thành ADR có thể duyệt

ADR phải ghi **dữ liệu hỗ trợ hoặc chống lại quyết định**. Một bảng đánh giá chưa có kết quả phải giữ trạng thái trống:

| Tiêu chí | Ngưỡng đã chốt | V1 | V2 | Quyết định hiện tại |
|---|---|---|---|---|
| p99 Q1/48h | ≤ 180 ms tại API | Chưa đo | Chưa đo | Chưa quyết |
| p99 ghi tại đỉnh | ≤ 100 ms tại Java client | Chưa đo | Chưa đo | Chưa quyết |
| Kích thước partition cực đại | Ngân sách kỹ thuật đã duyệt | Chưa đo | Chưa đo | Chưa quyết |
| Lỗi khi mất một node | Ngưỡng failure-mode đã duyệt | Chưa đo | Chưa đo | Chưa quyết |
| Chi phí tháng | Dưới trần ngân sách dự án | Chưa đo | Chưa đo | Chưa quyết |
| Độ khó migration | Chấp nhận được theo kế hoạch triển khai | Chưa đánh giá | Chưa đánh giá | Chưa quyết |

### Mẫu ADR gắn với các bằng chứng cụ thể

~~~markdown
# ADR-014 — Partition và consistency cho coldchain

Trạng thái: Proposed
Người phụ trách: <tên vai trò/nhóm>
Ngày cập nhật: <YYYY-MM-DD>
Phiên bản sơ đồ liên quan: D1-v<version>

## Bối cảnh
- Q1: 100 phép đo cảm biến mới nhất, truy vấn tối đa 48 giờ.
- Q2: cảnh báo theo site và ngày.
- Lưu phép đo 14 ngày; cảnh báo 90 ngày.
- SLO đã được chủ sản phẩm phê duyệt: <mô tả cửa sổ đo>.

## Lựa chọn
- V1: partition theo cảm biến/ngày.
- V2: partition theo cảm biến/giờ.
- V3: partition theo cảm biến/ngày và shard.
- Ghi và đọc: so sánh LOCAL_QUORUM, các trường hợp cần CL khác.

## Giả định
- AS-01 ... (trạng thái, chủ sở hữu, bằng chứng)
- AS-02 ...
- AS-05 ...

## Bằng chứng
- EXP-01: <đường dẫn raw metrics, thời gian, commit, người chạy>
- EXP-03: <phân phối partition và thiết bị nóng>
- EXP-04: <failure timeline, lượng lỗi, thời gian hồi phục>
- EXP-05: <SSTable/tombstone/compaction qua thời gian>

## Quyết định
- Chọn: CHƯA QUYẾT ĐỊNH nếu còn phép thử quan trọng chưa chạy.
- Khi đủ số liệu: ghi V1/V2/V3, CL, RF, TTL/compaction và lý do.
- Ghi rõ phương án bị loại và bằng chứng tương ứng.

## Hệ quả
- Fan-out và paging phía Java API.
- Chi phí vận hành repair, backup, failover và quan sát.
- Chi phí thay đổi partition key và kế hoạch migration.

## Điều kiện xem xét lại
- Thay đổi query shape/SLO, tải thiết bị nóng, retention hoặc miền lỗi.
- p99, tỷ lệ lỗi, partition size, compaction backlog hoặc chi phí
  vượt ngân sách đã phê duyệt.

## Phê duyệt
- Owner/Reviewer: <vai trò>
- Ngày/phiên bản cấu hình chấp thuận: <nếu đã có>
~~~

Không tự điền các con số benchmark giả định vào ADR như bằng chứng. Bằng chứng phải có **run ID**, thời gian, cấu hình, phiên bản, dataset và raw output. Nếu EXP-04 thất bại nhưng EXP-01 thành công, không được ghi “V1 đạt yêu cầu”; quyết định phải ghi rõ **chưa đạt điều kiện chịu lỗi** hoặc phạm vi được chấp thuận có ràng buộc.

## 9. Runbook: biến phát hiện sự cố thành thao tác kiểm chứng được

Runbook tốt không chỉ là danh sách lệnh nodetool. Mỗi tình huống phải nêu **triệu chứng → phạm vi ảnh hưởng → cách xác nhận → hành động an toàn → tiêu chí phục hồi → cách bàn giao**.

### 9.1. Runbook mẫu — tăng READ_TIMEOUT hoặc WRITE_TIMEOUT

**Trigger:** tỷ lệ READ_TIMEOUT/WRITE_TIMEOUT tăng liên tục so với SLO trong cửa sổ đã thống nhất; alert cần đính kèm biểu đồ theo endpoint, CL và tenant.

**Bước chẩn đoán:**

1. Kiểm tra request timeout ở Java API và driver; phân biệt READ_TIMEOUT, WRITE_TIMEOUT và UNAVAILABLE. Ghi tỷ lệ lỗi, p99, số lần retry và bắt đầu sự cố.
2. Chạy **nodetool status** trên node quản trị phù hợp để phát hiện node Down/Up, kiểm tra topology và cấu hình local DC.
3. Đối chiếu CPU, disk latency, heap/GC, dropped messages, pending tasks với **nodetool tpstats**, cùng metric từ hệ thống quan sát.
4. Kiểm tra **nodetool compactionstats**, tablestats và sensor/partition nóng. Khi có fan-out bất thường, đối chiếu query shape Q1/Q2 và phạm vi ngày được yêu cầu.
5. Kiểm tra network, consumer lag và đỉnh tải ứng dụng; tách lỗi upstream/broker khỏi lỗi Cassandra.

**Hành động theo nguyên nhân đã xác minh:** giảm tải đầu vào bằng backpressure có đo được, giới hạn concurrency/paging, khoanh vùng truy vấn quá rộng, xử lý node hỏng theo quy trình đã duyệt, hoặc lập kế hoạch mở rộng capacity. Không tự động **hạ consistency level, tăng timeout vô hạn, vô hiệu bảo vệ query hoặc chạy repair hàng loạt** chỉ để giảm biểu đồ lỗi.

**Xác nhận phục hồi:** p99/tỷ lệ lỗi đạt SLO trong một cửa sổ quan sát định nghĩa trước; backlog retry/compaction và consumer lag quay về phạm vi an toàn; audit số sự kiện bị gửi lại hoặc DLQ. Ghi timeline, truy vấn chịu ảnh hưởng, thay đổi đã áp dụng và rollback nếu cần.

### 9.2. Runbook mẫu — một node Down

**Trigger:** trạng thái node khác Up/Normal hoặc cảnh báo mất liên lạc; cần phân biệt lỗi mạng thoáng qua với node thực sự ngừng hoạt động.

1. Xác minh tình trạng hạ tầng, topology, rack/zone và số replica còn phục vụ; theo dõi yêu cầu LOCAL_QUORUM, latency và lỗi.
2. Tránh tạo thêm tải nền không cần thiết khi đang suy giảm. Nếu nghiệp vụ cho phép, giảm lưu lượng hoặc hoãn batch workload.
3. Thực hiện thủ tục khôi phục node phù hợp nguyên nhân (dịch vụ, ổ đĩa, mạng), có người chịu trách nhiệm và bản sao lưu khi cần.
4. Khi node trở lại, theo dõi streaming/hints, độ trễ, dung lượng và các hàng đợi nền. Đánh giá nhu cầu repair theo version, thời gian mất kết nối và chính sách đã phê duyệt.
5. Chỉ đóng sự cố khi node ổn định, các phép đọc/ghi kiểm tra thành công, metric phục hồi và backlog được xử lý.

**Không** đánh dấu “đã phục hồi” ngay khi nodetool status hiển thị UN: đó chỉ là một tín hiệu. Cần đối chiếu dữ liệu, backlog và trải nghiệm người dùng. Nếu node có dấu hiệu hỏng đĩa hoặc dữ liệu không nhất quán, chuyển cấp cho người vận hành có quyền trước khi sửa tại chỗ.

### 9.3. Runbook mẫu — đĩa tăng và compaction/tombstone backlog

**Trigger:** dung lượng dự báo chạm ngưỡng headroom, pending compactions duy trì cao, read p99 tăng hoặc tỷ lệ tombstone scan tăng.

Chẩn đoán thời điểm tăng dữ liệu, tốc độ ghi, TTL đã thực sự hết hạn chưa, kích thước và số lượng SSTable, sự kiện đến muộn, repair gần đây và lượng snapshot/backup lưu trên node. Phân biệt **đang giữ dữ liệu đúng retention** với **dữ liệu chưa thể thu hồi qua compaction**. Thử chính sách compaction ở staging bằng cùng dataset và đo write amplification, read latency, disk headroom.

Không xóa thủ công SSTable, snapshot hoặc giảm gc_grace_seconds khi chưa có quy trình được phê duyệt. Kế hoạch xử lý có thể gồm thêm dung lượng, giảm tải theo backpressure, điều chỉnh compaction đã đo, kiểm tra repair, hoặc thay đổi retention sau khi được xác nhận bởi nghiệp vụ. Xác nhận tốc độ tăng đĩa và pending compactions trở về mức dự kiến, không chỉ giảm tức thời.

### 9.4. Mẫu mục runbook để điền

~~~text
ID sự cố:
Owner / người nhận chuyển cấp:
Trigger và ngưỡng:
Dashboard / query / lệnh chẩn đoán:
Phiên bản Cassandra, topology, RF/CL:
Những gì KHÔNG được thao tác khi chưa có phê duyệt:
Biện pháp an toàn đã được kiểm chứng bằng EXP-xx:
Rollback hoặc quy trình thay thế:
Điều kiện thoát sự cố:
Đường dẫn timeline/log/raw evidence:
Ngày diễn tập gần nhất và người xác nhận:
~~~

## 10. Truy vết chéo: sửa ba tài liệu cùng một quyết định

Giả sử EXP-03 chứng minh sensor nóng làm partition theo ngày vượt ngân sách đã đặt. Nhóm không chỉ sửa một dòng ADR. Phải lan truyền thay đổi:

| Thay đổi do bằng chứng | Sơ đồ D1/D2 | ADR A1 | Runbook R1 |
|---|---|---|---|
| Chọn bucket giờ cho cảm biến nóng | Cập nhật schema, tên bảng, chiến lược xác định bucket và số request Q1 | Trích EXP-03/EXP-07, ghi chi phí fan-out và migration | Thêm cảnh báo số bucket/request và ngưỡng phân vùng nóng |
| Chuyển CL cho một API | Ghi trên đường đọc/ghi và vị trí đo | Giải thích đánh đổi consistency/latency bằng EXP riêng | Thêm tác động khi mất node và điều kiện chuyển cấp |
| Thay retention/compaction | Thêm TTL/compaction ở chú giải bảng, phiên bản schema | Trích EXP-05, ảnh hưởng dữ liệu đến muộn và chi phí | Cập nhật alert đĩa/tombstone, lịch review repair |
| Thêm node hoặc thay topology | Vẽ lại số node, rack, DC, RF được áp dụng | Trích failure/capacity test, phân tích chi phí | Cập nhật kiểm tra quorum, hướng xử lý node down |

**Ma trận truy vết ví dụ:**

| Quyết định | Giả định | Kiểm thử | Tài liệu liên quan | Trạng thái |
|---|---|---|---|---|
| DEC-01: V1 bucket ngày | AS-01, AS-03 | EXP-01, EXP-03, EXP-07 | D2-v1, ADR-014, R1-hot-partition | Pending |
| DEC-02: RF3, LOCAL_QUORUM | AS-05 | EXP-02, EXP-04 | D1-v1, ADR-014, R1-node-down | Pending |
| DEC-03: TTL 14/90 ngày | AS-06 | EXP-05 | D2-v1, ADR-014, R1-disk | Pending |
| DEC-04: Retry idempotent | AS-02 | EXP-06 | D1-v1, ADR-014, R1-timeout | Pending |

Không xóa hàng Pending để làm báo cáo trông hoàn chỉnh. Khi một phép thử tạo bằng chứng ngược, chuyển trạng thái **Rejected/Needs revision**, dẫn raw evidence và mở quyết định thay thế. Sơ đồ cập nhật phải có revision; ADR cũ giữ lại trạng thái **Superseded** nếu bị thay bởi ADR mới.

## 11. Cách tổ chức buổi thực hành và chấm kết quả

### Giai đoạn A — Khởi tạo

1. Xác nhận query contract Q1/Q2, SLO và ngân sách failure-mode.
2. Chuẩn bị một cụm Cassandra staging, data generator và ứng dụng Java driver 4.x; không sử dụng dữ liệu cá nhân hoặc token sản xuất trong báo cáo.
3. Đánh dấu version/commit của schema và sơ đồ D1/D2 ứng viên. Thực thi schema, smoke test insert/select qua prepared statements; xác nhận ngày bucket dùng UTC.

### Giai đoạn B — Đo và thử lỗi

4. Nạp dữ liệu theo phân bố bình thường và lệch tải; chạy EXP-01/02/03/07 theo cùng điều kiện. Lưu histogram và lỗi, không chỉ trung bình.
5. Kiểm tra retry cùng event_id và tình huống timeout ở EXP-06; đối soát số ID/số hàng sau khi chạy lại message.
6. Thử mất một node ở staging (EXP-04) và theo dõi hồi phục; đo compaction/TTL ở EXP-05 qua khoảng thời gian đủ có ý nghĩa.
7. So sánh V1/V2/V3 bằng bảng chứng cứ và chi phí. Nếu chưa có điều kiện chạy đủ chu kỳ TTL, ghi rõ giới hạn kiểm thử.

### Giai đoạn C — Chốt và bàn giao

8. Hoàn thiện sơ đồ D1/D2, đưa các quyết định đã chứng minh và những phần Pending vào ADR.
9. Diễn tập runbook R1 bằng hai kịch bản trong phạm vi staging, lưu time-to-diagnose/time-to-recovery; người khác trong nhóm phải thực hiện được theo tài liệu.
10. Hoàn thiện ma trận T1, kiểm tra không còn tham chiếu tới schema hoặc CL đã cũ; đưa quyết định còn Pending vào kế hoạch cải tiến.

### Rubric tự đánh giá

| Hạng mục | Điểm tối đa | Dấu hiệu đạt |
|---|---:|---|
| Đúng mô hình wide-column theo truy vấn | 20 | Không dùng quét toàn cụm cho Q1/Q2; partition key và fan-out hợp lý |
| Bằng chứng thử nghiệm có thể lặp lại | 25 | Có workload, môi trường, raw metric, failure drill và mã phiên bản |
| ADR có giả định và đánh đổi rõ | 20 | Quyết định phân biệt số đo thật với giả định, có trigger xem xét lại |
| Runbook thực thi và xác nhận được | 20 | Có trigger, chẩn đoán, hành động, rollback, tiêu chí phục hồi |
| Liên kết D1/D2 ↔ E1 ↔ A1 ↔ R1 | 15 | Mọi thay đổi thiết kế quan trọng truy ngược đến bằng chứng |
| **Tổng** | **100** | **Không tự động đạt nếu một phép thử bắt buộc chưa thực hiện** |

Người học không cần cố gắng làm mọi phép thử đều thành công. Một thí nghiệm chứng minh V1 thất bại trước sensor nóng là **kết quả có ích** nếu được đo công bằng, lưu đủ dữ liệu và khiến nhóm sửa sơ đồ, ADR cùng runbook.

## 12. Câu hỏi phản biện cuối bài

1. Nếu EXP-01 đạt nhưng EXP-04 thất bại khi mất một node, những dòng nào trên D1, ADR và runbook bắt buộc phải thay đổi?
2. Nếu p99 Cassandra tốt nhưng p99 Q1/48h ở API vượt SLO, bạn đo fan-out và phân trang như thế nào để phân biệt lỗi dữ liệu với lỗi ứng dụng?
3. Nếu một cảm biến gửi 100 phép đo/giây suốt 24 giờ, vì sao partition theo ngày có thể rủi ro dù tổng tải cụm không tăng nhiều? Phương án bucket giờ đổi lại chi phí gì?
4. Nếu producer gửi lại một sự kiện với **event_id mới**, vì sao lời hứa “retry an toàn” trong ADR không còn đúng?
5. Nếu ổ đĩa tăng sau khi TTL hết hạn, bạn cần quan sát những chỉ số nào trước khi kết luận Cassandra không xóa dữ liệu?
6. Nếu người vận hành thay CL từ LOCAL_QUORUM sang LOCAL_ONE để giảm timeout, điều gì phải được kiểm chứng lại về độ mới dữ liệu và khả năng chịu lỗi?
7. Một quyết định được chấp thuận trên staging vào tháng này có thể bị vô hiệu bởi những thay đổi nào của dữ liệu, traffic và topology trong quý sau?

**Kết quả cốt lõi:** sơ đồ mô tả trạng thái triển khai có thể đo được, ADR chứng minh lý do chọn thiết kế, còn runbook hướng dẫn ứng xử khi hệ thống đi lệch giả định. Ba tài liệu được xem là **một bộ hiện vật sống** khi cùng dùng mã quyết định, ID thí nghiệm, phiên bản và tiêu chí xác nhận — để kiến trúc Cassandra có thể bảo vệ, vận hành và cải tiến bằng bằng chứng thực nghiệm.
