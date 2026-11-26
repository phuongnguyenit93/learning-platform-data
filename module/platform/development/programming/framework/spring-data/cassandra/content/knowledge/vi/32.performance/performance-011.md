# Đối chiếu tối ưu bằng số đo và kiểm tra tính đúng đắn

Một thay đổi trong **Spring Data Cassandra** có thể làm truy vấn nhanh hơn nhưng âm thầm đổi kết quả nghiệp vụ. Ví dụ, chuyển bảng đơn hàng từ một partition theo khách hàng sang nhiều partition theo tháng có thể giảm kích thước partition, nhưng làm thiếu đơn khi kết quả cần đi qua ranh giới tháng. Thu hẹp danh sách cột trong `SELECT` có thể giảm dữ liệu truyền về, nhưng khiến mapper thiếu thuộc tính mà API đang sử dụng. Tăng page size có thể giảm số round-trip khi đọc nhiều dữ liệu, nhưng lại làm tăng latency trang đầu và bộ nhớ cần dùng.

Vì vậy, **một tối ưu chỉ thành công khi vừa có số đo cải thiện đáng tin cậy, vừa chứng minh được tính đúng đắn của hành vi cần giữ**. Không lấy cảm giác “nhanh hơn” hoặc một lần đo trên máy phát triển làm bằng chứng.

Bài thuộc chương **Hiệu năng** của module **SPRING_DATA_CASSANDRA**: truy cập Apache Cassandra bằng entity mapping, repository, `CassandraTemplate` và truy vấn CQL; thiết kế bảng theo truy vấn, partition key, consistency level, paging và kiểm soát hiệu năng trong mô hình dữ liệu phân tán. Nội dung tập trung vào phương pháp thiết lập baseline, so sánh trước/sau, đo hiệu năng thực và đối chiếu kết quả trên cùng tập dữ liệu.

## 1. Hai mặt phải chứng minh khi tối ưu

Mỗi phương án tối ưu phải trả lời hai câu hỏi độc lập:

1. **Nhanh hơn bao nhiêu, trong điều kiện nào?** Đo latency, throughput, mức tiêu thụ tài nguyên, lỗi và độ ổn định theo workload đại diện.
2. **Có trả về kết quả nghiệp vụ đúng như trước không?** Xác minh tập dữ liệu, thứ tự, bộ lọc, pagination, tính nhất quán và các tác dụng phụ ghi/xóa.

Giả sử API lấy 20 đơn mới nhất của một khách hàng, cần giữ những điều kiện:

- Chỉ trả đơn thuộc đúng `customer_id`.
- Sắp xếp `created_at DESC`; nếu trùng thời điểm thì `order_id ASC`.
- Không bỏ sót hay trả trùng đơn hợp lệ khi dữ liệu cố định.
- Trả đủ `order_id`, `created_at`, `status` và `total_amount` với đúng giá trị.
- Phân trang tiếp tục đúng qua mọi vùng dữ liệu và kết thúc đúng khi hết đơn.
- Tôn trọng hợp đồng nhất quán, độ trễ cập nhật và hành vi khi timeout.

Đó là **hợp đồng tính đúng đắn**. Nếu thay đổi cố ý làm một trong các đặc tính khác đi, cần mô tả và chấp nhận sự thay đổi trước khi đo, chứ không gọi là tối ưu giữ nguyên hành vi.

| Bằng chứng | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Số đo hiệu năng | Chạy nhanh hơn và có chịu tải tốt hơn không? | p50/p95/p99, RPS thành công, CPU |
| Kiểm thử chức năng | Dữ liệu và thứ tự còn đúng không? | Đúng đơn, đúng trang, không trùng |
| Kiểm tra vận hành | Có bền vững dưới dữ liệu/tải thực tế không? | Partition size, tombstone, compaction, retry |

Một biểu đồ p95 đẹp không thể thay cho kiểm tra dữ liệu đúng. Ngược lại, test chức năng pass không chứng minh latency đáp ứng SLO.

## 2. Ví dụ xuyên suốt: tối ưu bảng đơn hàng theo khách hàng

### 2.1. Phương án ban đầu

Bảng `orders_by_customer_v1` phục vụ truy vấn danh sách đơn theo khách hàng:

~~~sql
CREATE TABLE orders_by_customer_v1 (
    customer_id uuid,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

CQL:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_v1
WHERE customer_id = ?
LIMIT 20;
~~~

Bảng phù hợp đường đọc: một partition theo khách hàng và thứ tự clustering có sẵn. Nhưng một khách hàng có thể tích lũy hàng triệu đơn theo thời gian. Partition lớn hoặc nóng gây chi phí xử lý tăng, đặc biệt với tải tập trung vào ít khách hàng lớn.

### 2.2. Giả thuyết tối ưu

Chia các đơn của mỗi khách hàng thành bucket theo tháng UTC:

~~~sql
CREATE TABLE orders_by_customer_v2 (
    customer_id uuid,
    order_month text,
    created_at timestamp,
    order_id uuid,
    status text,
    total_amount decimal,
    PRIMARY KEY ((customer_id, order_month), created_at, order_id)
) WITH CLUSTERING ORDER BY (created_at DESC, order_id ASC);
~~~

`order_month` là chuỗi dạng `YYYY-MM` theo UTC, ví dụ `2026-11`. Có thể dùng kiểu biểu diễn khác trong production, nhưng mọi writer/reader phải cùng quy tắc tính bucket.

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_v2
WHERE customer_id = ? AND order_month = ?
LIMIT 20;
~~~

**Mặt trái:** truy vấn mới chỉ lấy đơn trong một tháng. API muốn 20 đơn mới nhất toàn lịch sử phải đọc lần lượt tháng hiện tại rồi những tháng trước, cho tới khi đủ 20 hoặc đến giới hạn thời gian lưu trữ. Nếu tháng hiện tại chỉ có 3 đơn mà service trả 3 đơn rồi dừng, CQL vẫn hợp lệ nhưng **API sai**.

Bảng mới có thể giảm kích thước một partition, nhưng tăng số CQL trên mỗi request. Nếu một khách hàng vẫn tạo quá nhiều đơn trong một tháng, bucket vẫn có thể quá lớn và cần thiết kế khác. Đây là giả thuyết cần đo, chưa phải kết luận.

### 2.3. Bất biến khi chuyển từ v1 sang v2

- Một đơn phải thuộc đúng bucket tính từ `created_at`, không phụ thuộc múi giờ máy chạy.
- Danh sách sau khi ghép nhiều tháng phải tương đương `created_at DESC, order_id ASC` của v1.
- Không bỏ sót đơn ở ranh giới tháng, kể cả `23:59:59.999Z` và `00:00:00.000Z`.
- Không trùng khi di chuyển qua bucket hoặc qua trang.
- Pagination token phải chứa vị trí hợp lệ cho truy vấn tiếp theo; paging state native của một câu CQL theo tháng không phải token tổng hợp cho mọi tháng.
- Trạng thái đơn, số tiền và chính sách đồng bộ projection không bị đổi ngoài ý muốn.
- Nếu dữ liệu mới được cập nhật bất đồng bộ, phải có giới hạn lag và đối soát như hợp đồng đã xác định.

~~~mermaid
flowchart LR
    A["Yêu cầu 20 đơn mới nhất"] --> B["Tháng gần nhất"]
    B --> C{"Đủ 20 đơn?"}
    C -->|Chưa| D["Tháng trước đó"]
    D --> C
    C -->|Đủ hoặc hết phạm vi| E["Ghép đúng thứ tự"]
    E --> F["Kiểm tra kết quả và token trang"]
~~~

Với bucket theo **tháng của chính `created_at`**, các bucket tháng khác nhau không chồng lấn theo thời gian, nên có thể đọc tháng mới đến cũ. Nếu thay bucket bằng `hash(order_id)`, các shard có thời gian chồng lấn và phải merge top-N giữa nhiều shard; không được nối tuần tự.

## 3. Baseline phải mô tả hệ thống hiện tại

**Baseline** là số đo có thể tái lập trước khi tối ưu. Nó cần xác định chậm tại đâu: HTTP, mapping Java, Java Driver, coordinator Cassandra, replica, tombstone, GC hay đĩa.

~~~mermaid
flowchart LR
    A["Load generator"] --> B["HTTP API"]
    B --> C["Spring Service"]
    C --> D["Java Driver"]
    D --> E["Cassandra Coordinator"]
    E --> F["Replica / Storage"]
~~~

| Tầng | Nên quan sát | Lý do |
|---|---|---|
| Client/API | Total latency, RPS, error/timeout, response bytes | Thời gian người dùng thực nhận |
| Spring Service | Xử lý nghiệp vụ, số CQL/request, mapping/allocations | Bắt lỗi fan-out và tải dữ liệu thừa |
| Java Driver | Request latency, retry, timeout, in-flight, pool | Đánh giá đường đi tới cluster |
| Cassandra | Read/write latency, CPU, GC, disk I/O, tombstone, compaction | Xác định tài nguyên và điểm nghẽn |

Đặt timer ở cả **đường API** và **đường CQL**. Nếu v2 phải thực hiện bốn truy vấn và merge dữ liệu, latency một câu CQL có thể giảm trong khi latency API lại tăng. Các timer lồng nhau không được cộng lại vì timer bên ngoài đã bao gồm phần bên trong.

### 3.1. Chỉ số cần đo

- **p50, p95, p99 latency** cho từng endpoint và mẫu truy vấn.
- **Offered RPS** (đã phát), **successful RPS** (đáp ứng thành công), throughput dữ liệu.
- **Error và timeout rate** tính trên toàn bộ request được gửi, kể cả lỗi.
- **CPU, heap, GC, network, disk, compaction** ở ứng dụng và Cassandra.
- **Số query/request**, số partition được đọc, số row materialize, bytes phản hồi.
- **Hot partition, partition size distribution, tombstone scanned**, tốc độ đọc/ghi thực.
- Nếu có projection bất đồng bộ: **projection lag, backlog, retry, mismatch**.
- Nếu có nhiều replica: consistency level đọc/ghi, topology, retry/speculative execution.

Đo p99 đòi hỏi đủ số mẫu. Không suy ra tail latency từ vài chục request. Không lấy trung bình của các p95 riêng lẻ làm p95 tổng; muốn percentile tổng phải gộp phân bố/histogram phù hợp.

### 3.2. Mẫu hồ sơ baseline

~~~yaml
experiment_id: customer-orders-bucketing
scope: customer-orders-list
variant: v1
query_shape: latest-orders-by-customer
dataset:
  customer_count: "<số lượng thực>"
  history_months: "<phạm vi thực>"
  skew: "<phân bố khách hàng nhỏ/lớn>"
environment:
  cassandra_version: "<phiên bản thực>"
  replication_factor: "<số replica thực>"
  local_datacenter: "<DC thực>"
  consistency: "<ví dụ LOCAL_QUORUM, nếu phù hợp>"
  app_replicas: "<số instance thực>"
traffic:
  offered_rps: "<các mức tải>"
  request_mix: "<tỷ lệ trang đầu/trang sau>"
measurement:
  warmup: "<thời lượng>"
  steady_state: "<thời lượng>"
  sample_count: "<số mẫu>"
acceptance:
  correctness: "toàn bộ ca bắt buộc pass"
  p95: "<SLO đã thống nhất>"
  p99: "<SLO đã thống nhất>"
  errors: "<error budget>"
~~~

Đây là **mẫu mô tả thí nghiệm**, không phải kết quả hoặc khuyến nghị điền giá trị cố định cho mọi hệ thống.

## 4. Kiểm soát biến trong phép so sánh

Hai biến thể chỉ so sánh trực tiếp được khi workload và những yếu tố khác tương đương.

### 4.1. Cố định hoặc ghi nhận đầy đủ

- Phiên bản Cassandra, Spring Data Cassandra, Java Driver và JVM.
- Số node, replication factor, topology, consistency level và timeout.
- CPU, bộ nhớ, disk, network và app instances.
- Tỉ lệ đọc/ghi, request mix, page size, bộ lọc và payload response.
- Số lượng khách hàng, phân bố số đơn, partition size, tombstone, TTL.
- Tải nền, repair, compaction, backup, cache state và warmup.
- Thời lượng thử nghiệm, số mẫu và thuật toán phát tải.

Không thay consistency level và schema cùng lúc nếu mục tiêu là kiểm chứng lợi ích riêng của schema mới. `LOCAL_ONE` trên v2 với `LOCAL_QUORUM` trên v1 là phép so hai cấu hình có semantics khác nhau.

### 4.2. Dữ liệu phải có phân bố thực tế

| Nhóm dữ liệu | Vì sao cần |
|---|---|
| Khách hàng 0–10 đơn | Đường đọc nhẹ, phần lớn workload |
| Khách hàng hàng chục nghìn đơn | Partition lớn, nhiều page |
| Khách hàng cực nhiều đơn trong cùng tháng | Kiểm tra bucket còn nóng không |
| Có tháng rỗng liên tiếp | Bắt lỗi dừng đọc bucket quá sớm |
| Đơn ở biên tháng | Kiểm tra tính bucket UTC |
| Hai đơn cùng timestamp | Bắt sai thứ tự tie-break |
| Đơn sửa trạng thái hoặc bị xóa | Kiểm tra projection, tombstone |
| Dữ liệu cũ có TTL | Đo trạng thái giống production hơn |
| Trang sâu và trang đầu | Phân biệt hiệu năng cursor |

Một dataset 1 triệu row rải đều trên mọi khách hàng không đại diện hệ có hot key. Cassandra nhạy với phân bố khóa partition và kích thước partition. Nên seed dữ liệu trước, ghi nhận compaction/cache state rồi mới chạy steady-state.

### 4.3. Một container không đại diện cluster production

Cassandra chạy một node bằng Testcontainers phù hợp test schema, mapping, CQL và paging. Nhưng nó chưa chứng minh hiệu năng của hệ có replica, network hop, consistency level, repair, GC và compaction phân tán. Muốn kết luận production, cần kiểm thử trên môi trường có topology và phân bố tải đủ gần.

## 5. Thiết kế workload để không đo nhầm

### 5.1. Closed-loop và open-loop

**Closed-loop**: client gửi request tiếp theo sau khi request trước hoàn tất. Khi ứng dụng chậm, tốc độ gửi tự giảm. Nếu chỉ báo successful latency, phép đo dễ che tình trạng quá tải.

**Open-loop/arrival-rate**: phát request theo tốc độ đầu vào định trước, theo dõi tất cả request đã đến, kể cả backlog, timeout hoặc drop. Cần load generator đủ năng lực để không trở thành điểm nghẽn. Tránh *coordinated omission* khiến tail latency trông thấp giả.

**Concurrency** (số request đang chạy đồng thời) không đồng nghĩa RPS. Khi tăng concurrency, throughput có thể tăng rồi bão hòa trong khi p99 và lỗi tăng mạnh.

### 5.2. Các pha của một lần thử

1. **Warmup**: đưa JVM/JIT, session, prepared statement, pool và cache vào trạng thái đo đã định.
2. **Steady state**: thu latency, lỗi, RPS và tài nguyên khi lưu lượng giữ ổn định.
3. **Step-load**: tăng offered RPS theo từng mức để thấy điểm bão hòa, backlog và tail latency.
4. **Recovery**: giảm tải, theo dõi hệ thống có phục hồi, queue/compaction có về bình thường không.

Không đưa mẫu warmup vào kết quả steady-state. Nên chạy nhiều lần và dùng thứ tự A–B–A–B hoặc canary có chia tải được kiểm soát để giảm nhiễu do thời gian, compaction hoặc cache. Nếu v1/v2 chạy chung tài nguyên, phải ghi nhận chúng có thể tranh CPU/disk/cache.

## 6. Đo đúng phạm vi request ở Spring Data Cassandra

Một endpoint có thể xác thực, chọn bucket, gọi nhiều CQL, map row thành DTO, tạo token rồi serialize JSON. Đo mỗi `session.execute` có thể bỏ sót chi phí materialization hoặc các truy vấn bổ sung.

Ví dụ instrumentation cho một truy vấn v1 bằng Java Driver và Micrometer:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

public final class RecentOrderReader {
    private final CqlSession session;
    private final MeterRegistry registry;
    private final PreparedStatement query;

    public RecentOrderReader(CqlSession session, MeterRegistry registry) {
        this.session = session;
        this.registry = registry;
        this.query = session.prepare("""
            SELECT order_id, created_at, status, total_amount
            FROM orders_by_customer_v1
            WHERE customer_id = ? LIMIT 20
            """);
    }

    public List<UUID> listOrderIds(UUID customerId) {
        Timer.Sample sample = Timer.start(registry);
        try {
            BoundStatement bound = query.bind(customerId)
                .setPageSize(20);
            ResultSet result = session.execute(bound);

            List<UUID> ids = new ArrayList<>();
            for (var row : result) {
                ids.add(row.getUuid("order_id"));
            }
            return ids;
        } finally {
            sample.stop(registry.timer(
                "customer_orders_query_duration",
                "variant", "v1",
                "operation", "recent_orders"));
        }
    }
}
~~~

Đây là **ví dụ instrumentation**, chỉ trả ID để minh họa; API production phải trả đủ trường đã cam kết. Timer dừng sau khi đã đọc hết các row của câu truy vấn. Với async hoặc reactive stream, timer phải dừng khi tác vụ/stream hoàn thành; dừng ngay khi tạo future hoặc publisher sẽ cho số đo giả.

Không thêm `customer_id`, `order_id` làm metric tags vì cardinality không giới hạn. Dùng tag hữu hạn như variant, query class, outcome và phân nhóm kích thước.

### 6.1. Page size không phải giới hạn tổng số row

`LIMIT 20` giới hạn tổng dòng CQL; `setPageSize(20)` chỉ định kích thước page mục tiêu. Java Driver có thể fetch page tiếp theo khi duyệt iterator hoặc gọi `ResultSet.all()`. Phải đo số page thực fetch, số row đọc và số row trả API.

Ở Spring Data Cassandra, lựa chọn repository, `CassandraTemplate` hay `CqlSession` ảnh hưởng cách query, mapping và pagination được thực thi. Không mặc định `Page` có tổng số bản ghi miễn phí như ở cơ sở dữ liệu quan hệ; nếu API không cần tổng đếm, nghiên cứu `Slice` hoặc continuation token phù hợp với phiên bản đang dùng.

### 6.2. Giải thích số đo bằng tracing và storage metrics

Nếu p99 cao nhưng CPU app thấp, xem driver timeout, coordinator, network, disk và Cassandra metrics. Nếu p99 API cao trong khi driver latency thấp, kiểm tra mapping, merge bucket, JSON, allocation và GC. Nếu tombstone scanned cao, xem TTL, delete, compaction và cách query truy cập dữ liệu.

Có thể dùng tracing CQL để điều tra một số query đại diện, nhưng tracing có overhead: chỉ bật có kiểm soát, không bật trên mọi request production để benchmark. Các metric cụ thể phụ thuộc phiên bản Cassandra và cơ chế export đang dùng, cần xác minh trong môi trường thực.

## 7. Xây dựng oracle để kiểm tra tính đúng đắn

Một **oracle** là nguồn cho biết kết quả kỳ vọng. Khi tối ưu database, oracle phải độc lập với điều đang thay đổi càng nhiều càng tốt.

Có ba lựa chọn bổ sung cho nhau:

1. **Triển khai v1 đã được xác minh:** đọc v1 và v2 trên một tập dữ liệu cố định, chuẩn hóa về cùng DTO và so từng field theo đúng thứ tự.
2. **Nguồn dữ liệu chuẩn (canonical):** so từng đơn với nguồn nghiệp vụ có thẩm quyền, tránh trường hợp v1 đã sai mà v2 chỉ sao chép lỗi.
3. **Bất biến độc lập:** kiểm tra mọi dòng có đúng khách hàng, đúng bucket UTC, không trùng order ID, đúng thứ tự, đủ số dòng ở mỗi page.

Nếu vừa đổi query vừa đổi converter, hai đường đọc Java có thể cùng sai theo một cách. Hãy bổ sung **CQL readback trực tiếp** hoặc fixture do test tự tạo, không phụ thuộc đường ghi đang được kiểm chứng.

### 7.1. Định nghĩa rõ “cùng kết quả”

| Thuộc tính | Hợp đồng | Assertion cần có |
|---|---|---|
| Phạm vi | Đúng `customer_id` và filter | Không lẫn khách hàng |
| Tập dòng | Không thiếu/thừa với dữ liệu cố định | So full primary key |
| Thứ tự | `created_at DESC, order_id ASC` | So danh sách theo đúng vị trí |
| Dữ liệu | Trường hiển thị chính xác | So field-by-field |
| Phân trang | Nối các page bằng kết quả đầy đủ | Không trùng, không skip |
| Null và kiểu | Đúng hợp đồng mapper | Timestamp, decimal, null |
| Cập nhật | Không trả giá trị cũ quá SLA | So version/trạng thái chuẩn |
| Lỗi | Không ngầm đổi lỗi thành danh sách rỗng | Assert status/error semantics |

Không dùng `Set` khi kết quả cần thứ tự, vì set che lỗi sắp xếp và có thể loại trùng trước khi test phát hiện. Không chỉ so số lượng; hai tập có thể cùng size nhưng thiếu hai đơn khác nhau.

### 7.2. Chọn trạng thái dữ liệu phù hợp phép thử

Phép so với v1/v2 có thể sai lệch nếu ứng dụng đang ghi trong lúc đọc hai bảng. Muốn kiểm tra logic bucket và paging, dùng **fixture bất biến** hoặc một mốc dữ liệu đã đối soát. Nếu hệ thống cho phép eventual consistency, thêm bài test riêng với SLA lag; không trộn sai lệch do đồng bộ với lỗi thuật toán truy vấn.

Với dữ liệu chứa TTL, timestamp và cập nhật liên tục, cần ghi mốc đo và quy tắc hết hạn. Không so một row trước khi TTL hết hạn với row sau khi TTL hết hạn rồi kết luận tối ưu làm mất dữ liệu.

## 8. Ví dụ đối chiếu danh sách vượt ranh giới tháng

Giả sử có các đơn sau của cùng một khách hàng:

| Đơn | Thời điểm UTC | Bucket | Thứ tự |
|---|---|---|---:|
| O6 | 2026-12-01 09:00:00.000 | 2026-12 | 1 |
| O5 | 2026-11-30 21:00:00.000 | 2026-11 | 2 |
| O4 | 2026-11-30 20:00:00.000 | 2026-11 | 3 |
| O3 | 2026-11-01 08:00:00.000 | 2026-11 | 4 |
| O2 | 2026-10-31 23:00:00.000 | 2026-10 | 5 |
| O1 | 2026-10-01 11:00:00.000 | 2026-10 | 6 |

Với `size=4`, kết quả đúng là O6, O5, O4, O3. Nếu chỉ đọc tháng 12, v2 trả thiếu. Với `size=5`, v2 phải tiếp tục đọc tháng 10. Một khách hàng không có đơn tháng 11 vẫn có thể có đơn tháng 10: logic reader phải phân biệt **bucket rỗng** với **hết lịch sử**.

### 8.1. Mã comparator và assertion trong Java

Sau khi chuẩn hóa row từ hai đường đọc thành DTO:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.UUID;

record OrderView(
    UUID orderId,
    Instant createdAt,
    String status,
    BigDecimal totalAmount
) {}

Comparator<OrderView> orderComparator =
    Comparator.comparing(OrderView::createdAt)
        .reversed()
        .thenComparing(OrderView::orderId);

List<OrderView> expected = legacy.stream()
    .sorted(orderComparator)
    .toList();

assertThat(bucketed).containsExactlyElementsOf(expected);

assertThat(bucketed.stream()
    .map(OrderView::orderId)
    .distinct()
    .count())
    .isEqualTo(bucketed.size());
~~~

Đoạn code nằm trong một test có `legacy` và `bucketed` là `List<OrderView>` đã seed/đọc, `assertThat` đến từ AssertJ, Java hỗ trợ record. Phép `containsExactlyElementsOf` kiểm tra cả giá trị và thứ tự.

Cần thêm assertion tất cả `orderId` thuộc customer hiện tại, dữ liệu `status` và `totalAmount` theo nguồn chuẩn. Với CQL `timestamp`, chú ý Cassandra lưu độ chính xác mili giây; không đem `Instant` có nanos tùy ý so trực tiếp mà chưa quy định cách làm tròn/cắt. Với `BigDecimal`, quy định scale/so sánh số tiền theo nghiệp vụ, không đổi sang `double` để bỏ qua sai lệch.

### 8.2. Bucket đúng nhưng thuật toán page sai

Không thể lấy 20 row gần nhất mỗi tháng rồi ghép tùy ý, đặc biệt khi cần 20 row **toàn bộ lịch sử** và có filter. Nếu filter loại nhiều row, reader phải tiếp tục truy vấn các tháng trước đến khi đủ dữ liệu hợp lệ theo contract.

Với bucket theo tháng tạo đơn, có thể nối các kết quả đã sắp xếp theo tháng giảm dần vì thời gian tháng sau lớn hơn tháng trước. Nếu chuyển thành sharding bằng hash order ID, các shard chồng lấn về thời gian; khi đó phải **merge k-way** theo comparator thay vì nối từng shard.

### 8.3. Kiểm thử ranh giới thời gian và duplicate key

Đặc biệt kiểm tra:

- `2026-10-31T23:59:59.999Z` thuộc tháng 10.
- `2026-11-01T00:00:00.000Z` thuộc tháng 11.
- Hai đơn cùng `created_at` vẫn có thứ tự nhờ `order_id ASC`.
- Một `order_id` không xuất hiện ở hai bucket trừ khi có lỗi đồng bộ.
- Khi đổi khóa thuộc primary key của bảng projection, thao tác “move” cần xóa khóa cũ và tạo khóa mới, không chỉ update một cột primary key.

Nếu ứng dụng tính tháng theo timezone người dùng thay vì UTC, có thể chuyển đơn sang bucket khác tùy hệ thống chạy ở đâu. Bắt buộc có một chính sách timezone thống nhất và test cụ thể.

## 9. Kiểm tra paging: trang đầu đúng chưa đủ

### 9.1. Token tổng hợp cho nhiều bucket

Cassandra paging state thuộc truy vấn và bộ tham số tương ứng. Ở v1 một request có thể đọc một partition; ở v2 nhiều tháng nghĩa là **nhiều truy vấn**.

Token API có thể phải mang:

- Bucket hiện tại.
- Paging state của truy vấn tại bucket đó (nếu còn).
- Vị trí khóa cuối đã trả và trạng thái chuyển tháng.
- Query version, filter và page size hoặc thông tin cần để kiểm tra token không bị dùng sai.
- Dữ liệu cần để tránh lặp lại row khi phát lại token theo hợp đồng đã định.

Không dùng paging state của `order_month = '2026-12'` để gọi `order_month = '2026-11'`. Nếu mã hóa token cho client, cần đảm bảo token hợp lệ, không bị sửa tùy tiện và không tạo lộ thông tin không cần thiết.

### 9.2. Thử qua ít nhất ba trang

Với sáu đơn O6…O1 và `page size=2`:

| Trang | Kỳ vọng | Lỗi có thể phát hiện |
|---|---|---|
| 1 | O6, O5 | Băng qua tháng 12 sang tháng 11 |
| 2 | O4, O3 | Tiếp tục đúng vị trí trong tháng 11 |
| 3 | O2, O1 | Chuyển sang tháng 10 |
| 4 | Rỗng | Hết dữ liệu, token không tạo vòng lặp |

Nối mọi page thành một danh sách và so với oracle đã sort. Kiểm tra không trùng `order_id`, không thiếu và token trang sau không trùng token trang trước một cách khiến client lặp vô hạn. Bổ sung các ca trang vừa đủ kết thúc bucket, bucket rỗng liên tiếp, dữ liệu rỗng và size lớn/nhỏ.

### 9.3. Khi có ghi đồng thời

Cassandra không cung cấp snapshot isolation trên cả loạt truy vấn paging xuyên nhiều partition. Nếu đơn mới được insert hoặc có delete giữa trang 1 và 2, kết quả có thể khác với fixture bất biến.

Do đó cần tách hai hợp đồng:

- **Fixture ổn định:** nối tất cả page phải cho đúng toàn bộ kết quả và đúng thứ tự.
- **Concurrent writes:** dùng chiến lược cursor theo khóa, snapshot/version hoặc semantics được công bố; không khẳng định mọi page tạo thành cùng một ảnh chụp nguyên tử trừ khi đã có cơ chế thật sự cung cấp điều đó.

Với cursor dựa trên khóa `(created_at, order_id)`, phải triển khai điều kiện CQL phù hợp clustering key và giới hạn partition, xử lý bucket chuyển tiếp, update/delete và idempotency của token. Đừng suy ra một điều kiện CQL keyset xuyên nhiều tháng hoạt động giống một khóa toàn cục.

## 10. Đối chiếu khi có ghi và đồng bộ nhiều bảng

Nếu v2 được tạo dưới dạng projection song song với v1 hoặc bảng chuẩn, cần kiểm tra **quá trình đưa dữ liệu sang bảng mới**. Một query v2 đúng logic vẫn trả sai nếu backfill thiếu dòng hoặc consumer chưa xử lý sự kiện.

| Sai lệch | Hướng điều tra |
|---|---|
| Thiếu đơn mới | Backfill gap, event lag, bucket sai |
| Đơn đã xóa vẫn tồn tại | Delete projection chưa chạy, TTL khác |
| Trạng thái cũ | Event cũ, out-of-order, missing update |
| Logical order trùng | Khóa `created_at` không ổn định hoặc ghi hai bucket |
| Query thiếu đơn ở tháng trước | Reader dừng sai khi bucket đầu thiếu |
| Trang sâu chậm hơn | Fan-out nhiều bucket, số CQL/request tăng |

### 10.1. Backfill phải không có khoảng trống dữ liệu

Một lộ trình thường gặp:

~~~mermaid
flowchart TD
    A["Tạo schema v2"] --> B["Thiết lập thu thay đổi bền vững"]
    B --> C["Backfill theo checkpoint"]
    C --> D["Replay các thay đổi trong thời gian backfill"]
    D --> E["Reconcile với dữ liệu chuẩn"]
    E -->|Còn sai lệch| F["Sửa và kiểm tra lại"]
    F --> E
    E -->|Đạt điều kiện| G["Shadow read / canary v2"]
    G --> H["Đo correctness + latency"]
~~~

Cơ chế nhận thay đổi phải bao phủ thời gian từ snapshot dùng backfill đến khi replay hoàn tất; nếu không có thể mất cập nhật nằm giữa. **Dual write** qua hai repository không tự có giao dịch ACID xuyên bảng/partition. Cần retry bền vững, idempotent và đối soát.

### 10.2. Phiên bản và thứ tự sự kiện

Lưu `version` trong bản chuẩn/projection có ích cho chẩn đoán, nhưng chỉ thêm cột version không khiến Cassandra tự từ chối ghi cũ. Phải thực thi guard/kiểm soát thứ tự theo order ID hoặc có reconciler hội tụ về nguồn chuẩn.

Test ít nhất: cùng sự kiện giao hai lần; v8 đến trước v7; worker chết giữa hai mutation; timeout mà ghi đã thành công; delete cũ chưa xử lý; canonical lên v9 trong lúc reconcile v8.

### 10.3. Độ trễ projection được phép

Nếu hợp đồng là eventual consistency trong một giới hạn đã công bố, test nên xác nhận:

1. Bảng chuẩn đã ghi thành công.
2. Projection có thể tạm thời cũ.
3. Trong deadline được quy định theo SLA, projection phải hội tụ.
4. Khi timeout, lỗi được ghi nhận/retry và đưa vào đối soát.
5. Không chấp nhận một mismatch tồn tại mãi chỉ vì test không chờ nữa.

Sử dụng polling có deadline và giới hạn concurrency thay vì ngủ cố định một khoảng rồi giả định thành công.

## 11. Consistency level không tự sửa sai lệch giữa các bảng

Consistency level (CL) quy định mức replica xác nhận cho **mỗi thao tác**. Nó không đồng bộ hai projection có khóa hoặc bảng khác nhau.

- Khi so v1/v2, dùng cùng CL để cô lập hiệu ứng schema/query.
- Nếu đổi CL là mục tiêu thí nghiệm, đo riêng cả latency và các thay đổi về khả năng sẵn sàng/semantics.
- Với RF=3 trong một local DC, `LOCAL_QUORUM` thường đòi đa số replica của DC đó; ở RF=1 hành vi và chi phí khác.
- Đọc nhiều partition không phải snapshot nguyên tử.
- `LOGGED BATCH` không cung cấp read isolation hoặc rollback nghiệp vụ xuyên partition.
- Timeout ở client có kết quả chưa xác định, không chứng minh write thất bại. Khi retry phải giữ idempotency key, kiểm tra trạng thái hiện có và tránh nhân đôi logical row.

Khi báo p95/p99, nếu bỏ request timeout khỏi tập latency thành công, luôn trình bày error/timeout rate **đi kèm** để tránh kết luận tốt giả do đã loại bỏ request chậm nhất.

## 12. Ma trận kiểm thử regression cần có

| ID | Dữ liệu hoặc kích thích | Assertion |
|---|---|---|
| C01 | Chỉ có đơn tháng hiện tại | V1/v2 trả cùng danh sách |
| C02 | Tháng hiện tại ít hơn page size | Đọc tháng trước đến đủ |
| C03 | Có tháng rỗng | Không dừng quá sớm |
| C04 | Đơn ở giây cuối/đầu tháng | Bucket UTC chính xác |
| C05 | Hai đơn cùng timestamp | Tie-break `order_id ASC` |
| C06 | Hai khách hàng cùng có đơn | Không đọc lẫn partition |
| C07 | Page kết thúc đúng cuối bucket | Token chuyển bucket đúng |
| C08 | Page vượt qua nhiều bucket | Không thiếu/trùng |
| C09 | Khách hàng không có đơn | Kết quả rỗng, không loop vô hạn |
| C10 | Update `status` | Trạng thái hội tụ với nguồn chuẩn |
| C11 | Delete/TTL | Không trả dữ liệu đã hết hiệu lực |
| C12 | Replay event v7 sau v8 | Không hạ state xuống v7 |
| C13 | Dữ liệu cố định | Nối tất cả page bằng oracle |
| C14 | Ghi concurrent | Tuân thủ hợp đồng paging đã công bố |
| C15 | Null, decimal, timestamp | Mapper không làm sai dữ liệu |
| C16 | Timeout/retry | Ghi lỗi đúng và không nhân đôi đơn |
| C17 | Partition rất lớn/nóng | Đo thêm tail latency và fan-out |
| C18 | Trang sâu qua nhiều tháng | Duy trì cursor đúng |
| C19 | Backfill chạy lại | Không sinh duplicate |
| C20 | CQL thiếu partition key | Không thêm `ALLOW FILTERING` để che schema sai |

### 12.1. Các tầng test phù hợp

**Unit test:** tính bucket UTC, comparator, merge kết quả, encode/decode token, xác định tháng kế tiếp.

**Integration test trên Cassandra thật:** repository/`CassandraTemplate`, composite key, CQL, paging, static/UDT/TTL khi liên quan, backfill, readback từ driver. Testcontainers Cassandra phù hợp để xác minh hành vi này.

**Load/soak test trên topology đại diện:** đo tail latency, throughput, GC, storage, compaction, hot partition, concurrency và recovery. Không dùng latency container CI làm chứng cứ thay cho cluster production.

### 12.2. Property-based testing

Ngoài các fixture cố định, sinh nhiều tập đơn nhỏ với các tháng ngẫu nhiên, timestamps trùng và bucket rỗng; kiểm tra:

- Nối toàn bộ các page v2 tương đương sorted oracle.
- Thay page size không thay thứ tự danh sách đầy đủ.
- Chèn đơn mới có timestamp lớn hơn mọi đơn cũ phải đặt đơn mới ở đầu.
- Replay backfill hai lần không làm tăng số logical row.
- Đổi tháng của tất cả đơn nhưng giữ quan hệ thời gian phải giữ thứ tự tương đối.

Property-based test giúp tìm ca biên không lường trước, nhưng cần CQL integration test vì bộ giả lập Java không tái hiện hoàn toàn semantics của Cassandra.

## 13. Cách đọc kết quả benchmark và ra quyết định

Giả sử có bảng số liệu **minh họa giả định**, không phải kết quả đã đo, khi cả hai phương án nhận cùng 1.000 offered requests mỗi giây:

| Chỉ số | v1 | v2 | Ý nghĩa |
|---|---:|---:|---|
| p50 HTTP | 62 ms | 48 ms | V2 nhanh hơn ở median |
| p95 HTTP | 210 ms | 145 ms | V2 giảm khoảng 31% |
| p99 HTTP | 480 ms | 670 ms | **Tail latency v2 tệ hơn** |
| Error + timeout | 0,2% | 1,1% | V2 có nhiều request lỗi hơn |
| CQL/request (trung bình) | 1,0 | 2,9 | Fan-out qua nhiều bucket |
| Successful RPS | 998 | 989 | Throughput hữu ích giảm |
| Test sai trang | 0 | 4 | V2 chưa đạt correctness gate |

Không thể nói “v2 tốt hơn” chỉ vì p95 giảm. Theo bảng này, v2 **chưa đạt điều kiện đưa vào production**: p99 xấu, error rate tăng và kết quả một số trang sai.

### 13.1. Tính phần trăm cải thiện

Với latency, phần trăm giảm được tính:

\[
\text{Mức giảm latency} = \frac{L_{\mathrm{before}} - L_{\mathrm{after}}}{L_{\mathrm{before}}} \times 100\%
\]

Ví dụ p95 giảm từ 210 xuống 145 ms:

\[
\frac{210 - 145}{210} \times 100\% \approx 30{,}95\%
\]

Con số này chỉ có ý nghĩa khi đo cùng tải, cùng cách lấy mẫu và cùng hợp đồng truy vấn. Một thay đổi 3% trong môi trường biến động 10% có thể chưa đủ tin cậy để quyết định.

### 13.2. Những điều phải ghi bên cạnh percentile

- **Số mẫu và số lần chạy:** không khẳng định p99 ổn định từ một tập mẫu rất nhỏ.
- **Khoảng dao động giữa các run:** median của các lần, phương sai/độ trải hoặc khoảng tin cậy theo phương pháp phù hợp.
- **Tỷ lệ lỗi:** successful latency riêng, timeout và error rate riêng, không che lỗi bằng cách chỉ thống kê những request kịp hoàn tất.
- **Mức tải:** p95 ở 100 RPS không đủ chứng minh hệ chịu 1.000 RPS.
- **Phân nhóm khách hàng:** nhóm có hàng triệu đơn có thể regress dù p50 chung cải thiện.
- **Tổng công việc:** số query/partition/page/request và chi phí cập nhật projection.
- **Giới hạn phép thử:** sự khác biệt topology, cache, compaction, traffic nền hoặc dataset chưa đại diện.

Không lấy trung bình số học của p95 các nhóm để gọi là p95 tổng. Nếu cần percentile tổng, phải hợp nhất dữ liệu phân bố hoặc histogram tương thích.

### 13.3. So sánh hiệu năng theo nhiều mức tải

Một ứng viên tốt ở tải thấp có thể gây bão hòa sớm vì số CQL/request tăng. Có thể tạo bảng với từng mức offered RPS, ví dụ 100, 300, 600, 1.000, sau đó so:

- Tail latency tại mỗi mức.
- Successful throughput và request đang đợi.
- Tốc độ tăng timeout khi tiến gần điểm bão hòa.
- Thời gian hệ thống phục hồi sau một giai đoạn tải cao.
- Sự thay đổi partition size, tombstone, CPU, GC, disk và compaction.

Các mức là ví dụ, không phải chuẩn. Chọn theo tải dự kiến và năng lực load generator thực tế.

## 14. Đặt tiêu chí chấp nhận trước khi chạy benchmark

Nếu chờ đến khi thấy số đo đẹp mới chọn ngưỡng, nhóm dễ điều chỉnh tiêu chí để hợp thức hóa kết quả. Nên chốt các **guardrail** trước.

Ví dụ bộ tiêu chí minh họa:

~~~text
Correctness:
  - 100% ca regression bắt buộc pass trên fixture ổn định
  - Không sai khóa, thứ tự, field, filter hoặc kết quả page
  - Mọi mismatch backfill/projection được giải quyết trong SLA
  - Event trùng/sai thứ tự không ghi lùi trạng thái
  - Không có logical duplicate sau retry/backfill

Performance, tại cùng offered load:
  - p95 HTTP giảm ít nhất 15%
  - p99 HTTP không tăng quá 5%
  - Successful RPS không giảm
  - Error/timeout rate không vượt ngân sách
  - CPU, heap, disk, compaction trong giới hạn được chấp nhận

Operations:
  - Dashboard và cảnh báo đã sẵn sàng
  - Có đường rollback đọc về v1
  - Có cơ chế sửa projection bị trễ/lệch
  - Có owner và playbook xử lý sự cố
~~~

Các ngưỡng 15% và 5% chỉ để **minh họa cách viết tiêu chí**, không áp dụng máy móc cho mọi hệ thống. Bài toán thanh toán, báo cáo tài chính hoặc dữ liệu người dùng quan trọng có thể yêu cầu tính đúng đắn nghiêm ngặt hơn.

### 14.1. Hard gate và trade-off

**Hard gate:** sai dữ liệu khách hàng, thiếu đơn, duplicate, lỗi phân trang, mất cập nhật, sai số tiền, lỗi vượt SLO bắt buộc. Khi các lỗi này xuất hiện, không lấy cải thiện latency để bù trừ.

**Trade-off có thể đánh giá:** thêm dung lượng hoặc số mutation để giảm read latency; tăng một chút CPU để giảm p99; nhiều bucket đọc hơn để tránh partition quá lớn. Mọi trade-off phải có số đo và ngân sách vận hành.

**Ví dụ:** tối ưu bằng bảng projection mới làm write amplification tăng hai lần nhưng p95 read giảm đáng kể. Điều này có thể hữu ích cho ứng dụng rất nặng đọc; nhưng vẫn phải đo tốc độ ghi, compaction, storage và chi phí đồng bộ projection trước khi quyết định.

## 15. Tối ưu nhỏ hơn: giảm dữ liệu đọc và kiểm soát mapper

Không phải lúc nào cũng cần thay schema. Trước khi tạo bảng mới, có thể kiểm chứng một tối ưu hẹp hơn.

### 15.1. `SELECT *` so với chỉ chọn cột cần thiết

~~~sql
-- Phương án A: trả mọi cột
SELECT *
FROM orders_by_customer_v1
WHERE customer_id = ?
LIMIT 20;

-- Phương án B: chỉ trả cột cần cho danh sách
SELECT order_id, created_at, status, total_amount
FROM orders_by_customer_v1
WHERE customer_id = ?
LIMIT 20;
~~~

Giả thuyết: B giảm bytes truyền và chi phí chuyển đổi nếu bảng có payload lớn nhưng màn hình danh sách không cần.

Cần đo **response bytes, CPU mapping, allocation và latency API**, đồng thời kiểm tra API vẫn trả đúng bốn trường cần thiết. Đừng lấy một entity chỉ load một phần cột rồi vô điều kiện `repository.save(entity)`: tùy đường ghi và xử lý null/unset, dữ liệu không được load có thể bị ảnh hưởng. DTO đọc riêng hoặc query projection phù hợp thường dễ bảo toàn hợp đồng hơn.

### 15.2. Repository, CassandraTemplate và CqlSession

Ba đường truy cập có thể tạo câu CQL/mapping khác nhau:

- `CassandraRepository` phù hợp truy cập theo primary key và query method đã định.
- `CassandraTemplate` tiện khi cần query/insert/update có kiểm soát.
- `CqlSession` và prepared statement cho phép chủ động CQL, page size, CL và chuyển đổi dữ liệu.

Nếu thử thay repository bằng driver trực tiếp, giữ nguyên query shape, dataset, field trả về và concurrency để cô lập chi phí mapping. Nếu đồng thời đổi schema, CL, DTO và số thread, sẽ khó biết yếu tố nào tạo ra cải thiện hoặc lỗi.

Với Cassandra, một repository method có tên hợp lý vẫn cần được kiểm tra câu CQL thực tế. Thiết kế truy vấn sai partition key không nên được “sửa” bằng `ALLOW FILTERING` trên tập dữ liệu lớn. Hãy xác định truy vấn nghiệp vụ trước rồi chọn bảng/khóa phục vụ nó.

## 16. Shadow read và canary khi tối ưu thay schema

Một tối ưu tác động đến dữ liệu nên được triển khai từng bước để kiểm soát rủi ro.

### 16.1. Shadow read

Ở một tỷ lệ nhỏ request, ứng dụng tiếp tục trả response v1, đồng thời đọc v2 để **so sánh ngoài đường quyết định response**.

Chỉ số cần ghi:

- `shadow_mismatch_total` phân loại missing, extra, value, order, paging và stale.
- `shadow_compare_duration` và query count cho riêng shadow.
- Phân bố mismatch theo nhóm khách hàng, bucket và query class.
- Lag giữa nguồn chuẩn và projection, nếu cập nhật bất đồng bộ.

Shadow read cũng tạo tải và hiệu ứng cache nên cần giới hạn concurrency và chú thích khi so performance. Không shadow toàn bộ production traffic khi chưa có ngân sách CPU/disk.

Một mismatch trong khi dữ liệu đang thay đổi cần được phân loại theo thời điểm/version; không tự động coi v2 sai nếu hai truy vấn nhìn hai thời điểm khác nhau. Đồng thời cũng không dùng eventual consistency để bỏ qua mọi mismatch vô thời hạn.

### 16.2. Các bước canary

1. Tạo schema, chuẩn bị writer/change capture và backfill.
2. Đối soát dữ liệu, bảo đảm không có khoảng trống giữa snapshot và stream cập nhật.
3. Chạy regression suite trên Cassandra thật, bao gồm ranh giới tháng và trang sâu.
4. Bật shadow read có kiểm soát, ghi mismatch.
5. Mở v2 cho một tỷ lệ nhỏ traffic, theo dõi p95/p99, error, RPS, số CQL/request, compaction và lag.
6. Tăng traffic khi correctness và guardrail cùng pass trên đủ số mẫu.
7. Nếu có regression, chuyển đường đọc về v1, phân tích lỗi và sửa dữ liệu/logic trước khi thử lại.
8. Chỉ gỡ bảng/đường đọc cũ sau giai đoạn quan sát và khi kế hoạch phục hồi đã rõ.

Feature flag rollback chỉ điều khiển **đường đọc**. Nó không tự sửa dữ liệu đã ghi sai ở v2 hay nguồn chuẩn, nên cần playbook xử lý projection và checkpoint.

### 16.3. Bảng ra quyết định canary

| Trạng thái | Hành động |
|---|---|
| Có lỗi correctness | Dừng mở rộng; sửa và kiểm tra lại |
| Correctness pass, cả p95/p99 tăng | Rollback hoặc điều tra thêm |
| p95 giảm nhưng p99 gần ngưỡng | Giữ canary nhỏ, thu thêm mẫu |
| Mismatch tăng theo projection lag | Xem backfill, consumer, replay, ordering |
| Lỗi chỉ ở hot customers | Phân tích bucket size, fan-out, pagination |
| Mọi guardrail pass qua nhiều lần chạy | Có thể tăng canary theo kế hoạch |

## 17. Những lỗi suy luận thường gặp

### “Nhanh hơn một lần là đủ”

Kết quả có thể do cache, JIT, repair/compaction đã kết thúc hoặc tải nền thay đổi. Cần đo lặp và ghi điều kiện.

### “p50 hoặc trung bình giảm là tối ưu tốt”

Khách hàng thường chịu ảnh hưởng rõ ở p95/p99 và timeout. Tail latency có thể xấu đi trong khi trung bình giảm.

### “COUNT giống nhau tức hai bảng giống nhau”

Hai bảng cùng 1.000 row vẫn có thể chứa những ID khác nhau. Kiểm tra theo khóa, trường, thứ tự và paging; checksum chỉ là hỗ trợ.

### “CQL query đúng nghĩa là API đúng”

Service có thể ghép bucket sai, chuyển DTO sai, cache sai hoặc tạo token trang tiếp theo sai. Kiểm thử cần đến tận response hợp đồng.

### “Page size lớn chắc chắn nhanh hơn”

Page lớn có thể giảm round-trip khi tải nhiều dữ liệu nhưng làm trang đầu chậm, tiêu thụ bộ nhớ và mạng hơn. Đo đúng hành vi người dùng cần.

### “Batch lớn giúp bulk write nhanh”

CQL batch có các bảo đảm cụ thể về áp dụng mutation, không phải công cụ mặc định tăng throughput ghi xuyên partition. Batch lớn có thể tăng tải coordinator và batch log.

### “CL cao làm hai bảng không bao giờ lệch”

Consistency level áp dụng cho từng lệnh đọc/ghi tới replica, không thay thế đồng bộ projection hay atomic transaction nhiều bảng.

### “Version column tự bảo vệ khỏi sự kiện cũ”

Cột `version` giúp kiểm tra nhưng không tự chặn last-write-wins. Cần cơ chế thực thi guard hoặc xử lý sự kiện theo thứ tự và đối soát.

### “Container một node chứng minh hiệu năng production”

Container phù hợp integration test schema/mapping. Đo tail latency production cần topology, tải và dữ liệu đại diện.

### “Bỏ các request timeout giúp p99 chính xác hơn”

Làm vậy có thể giấu phần đuôi xấu nhất. Phải nêu rõ latency thành công, timeout/error rate, offered và successful throughput.

## 18. Mẫu báo cáo để người khác có thể tái lập

~~~text
Tên thử nghiệm: customer-orders-bucketing

Hành vi cần giữ:
  - 20 đơn mới nhất theo created_at DESC, order_id ASC
  - Không thiếu/trùng và đúng các trường đã cam kết
  - Pagination đi hết lịch sử dữ liệu ổn định

Baseline:
  - Schema v1 và câu CQL cụ thể
  - Bản ghi môi trường, CL, RF, driver, dataset, traffic mix
  - p50/p95/p99 API + CQL, error, RPS, CPU, disk, bytes

Candidate:
  - Schema v2, thuật toán bucket và token
  - Backfill/change capture/reconcile
  - Cùng phương pháp phát tải và đo

Correctness:
  - Mỗi test pass/fail, oracle, fixture, mismatch
  - Xử lý TTL, delete, concurrency, event replay
  - Tình huống nào chấp nhận eventual consistency

Performance:
  - Bảng before/after theo nhiều mức tải
  - Số query/request, partition size, tombstone, compaction
  - Thống kê nhiều lần chạy và giới hạn tin cậy

Decision:
  - Go / No-Go / Cần đo thêm
  - Ngưỡng nào đạt, ngưỡng nào fail
  - Kế hoạch canary, giám sát, rollback, owner
~~~

Nên lưu script phát tải, dữ liệu fixture/seed, dashboard và kết quả raw histogram để người khác tái lập thí nghiệm. Báo cáo chính cần diễn giải quyết định và giới hạn, không chỉ đính kèm đồ thị.

## 19. Bài tập vận dụng

Một nhóm phát triển báo cáo p95 của endpoint danh sách đơn giảm từ **220 ms xuống 140 ms** khi đổi partition từ khách hàng sang khách hàng + tháng. Họ thử trên RF=1 với 100 khách hàng, mỗi khách hàng có 50 đơn trong tháng hiện tại. Không có đơn tháng trước, không kiểm tra trang thứ hai, chỉ so count trang đầu. Đồng thời họ đổi consistency level từ `LOCAL_QUORUM` sang `LOCAL_ONE`.

**Yêu cầu:**

1. Nêu bốn yếu tố khiến kết luận “tối ưu tốt hơn” chưa đủ cơ sở.
2. Thiết kế dữ liệu kiểm tra tháng rỗng, cuối/đầu tháng và hai đơn cùng timestamp.
3. Nêu cách xác nhận nối tất cả page v2 bằng thứ tự đầy đủ của oracle.
4. Chọn metric để phát hiện fan-out, tail latency, timeout, tombstone và chi phí ghi.
5. Giải thích tại sao kết quả RF=1 không đại diện trực tiếp cho RF=3.
6. Nếu p95 giảm 25% nhưng p99 tăng 40%, lỗi tăng và có một trường hợp thiếu đơn, bạn quyết định thế nào?

**Gợi ý tự kiểm tra:** Workload không đại diện vì không đòi hỏi đi qua bucket cũ; CL bị đổi cùng lúc; RF=1 không phản ánh đủ replication; thiếu test pagination và đối chiếu dữ liệu. Cần dữ liệu đóng băng có đơn qua nhiều tháng, so cả khóa, thứ tự và field từng trang. Nếu còn thiếu đơn hoặc vượt guardrail, **chưa mở rộng canary**, dù p95 đẹp hơn.

## 20. Checklist trước khi kết luận một tối ưu

- [ ] Xác định query pattern, partition/clustering key, mapping và điểm nghẽn đã đo.
- [ ] Baseline lưu rõ môi trường, workload, dataset, consistency level, warmup và cách đo.
- [ ] Có p50/p95/p99, offered/successful RPS, error/timeout và tài nguyên.
- [ ] Có nhiều lần chạy hoặc cách giảm nhiễu; không dùng một phép thử nhỏ làm kết luận.
- [ ] Có oracle, fixture, assertion field-by-field, thứ tự, duplicate và tất cả page.
- [ ] Test ranh giới bucket, hot partition, trang sâu, TTL/delete, retry và sự kiện sai thứ tự.
- [ ] Tách ảnh hưởng của schema, CL, DTO/mapper và concurrency.
- [ ] Nếu thêm bảng, đã kiểm tra backfill, lag, reconcile và write amplification.
- [ ] Có guardrail, canary, dashboard, rollback và người phụ trách.
- [ ] Quyết định cuối dựa trên **cả phép đo lẫn tính đúng đắn**.

---

## Tổng kết

Tối ưu Spring Data Cassandra không dừng ở việc viết một câu CQL ngắn hơn. Thiết kế bảng theo truy vấn, partition key, clustering order, paging và consistency level quyết định cả tốc độ lẫn ý nghĩa dữ liệu. Repository, `CassandraTemplate` và Java Driver cung cấp cách truy cập; việc chứng minh một thay đổi tốt hơn vẫn thuộc trách nhiệm của nhóm phát triển.

Một quy trình đáng tin cậy là **định nghĩa hợp đồng → dựng baseline → cô lập một thay đổi → đo trên workload đại diện → đối chiếu dữ liệu và phân trang → đánh giá tail latency/error → canary có rollback**. Nếu hai mặt của phép thử đều đạt, tối ưu mới tạo ra giá trị thực.

**Tài liệu tham khảo để đối chiếu khi triển khai:** Apache Cassandra Documentation về data modeling, partition/clustering key, consistency level, tombstones, compaction và query tracing; Spring Data for Apache Cassandra Reference về entity mapping, repository, CassandraTemplate và paging; DataStax Java Driver Documentation về prepared statements, paging, execution và metrics; Micrometer Documentation về Timer, percentile/histogram; Testcontainers Cassandra module. Kiểm tra API/cấu hình theo phiên bản thực tế của dự án.
