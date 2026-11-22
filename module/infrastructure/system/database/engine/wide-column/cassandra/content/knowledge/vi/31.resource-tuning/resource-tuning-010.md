# Tải coordinator, replica và phân phối yêu cầu giữa các nút

## Mục tiêu và phạm vi

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**. Một yêu cầu CQL có thể đi qua **coordinator** rồi được nhiều **replica** xử lý theo partition key, replication factor và consistency level. Do vậy, khi một node có CPU cao, hàng đợi dài hoặc p99 tăng, câu hỏi đầu tiên không chỉ là “node này nhận bao nhiêu kết nối?” mà còn là: **nó đang điều phối bao nhiêu yêu cầu, phục vụ bao nhiêu dữ liệu với tư cách replica, và vì sao các yêu cầu được đưa đến nó?**

Bài học thuộc chương **Tối ưu tài nguyên** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Ta kết nối các kiến thức về token ring, partition key, thiết kế bảng theo truy vấn, replication, consistency level đọc/ghi, compaction, repair, chẩn đoán lỗi và Cassandra Java Driver 4.x.

Sau khi học, bạn có thể:

1. Phân biệt tài nguyên tiêu thụ khi node đóng vai **coordinator** với khi nó là **replica**, kể cả khi một node đóng cả hai vai trò trong cùng request.
2. Giải thích **token-aware routing**, local datacenter, driver load balancing, routing key và tác động của speculative execution/retry.
3. Phát hiện hai loại mất cân bằng: **coordinator hot** do điều phối client và **replica hot** do partition hoặc token range nóng.
4. Dự đoán các request cần phản hồi ở `ONE`, `LOCAL_QUORUM` và `ALL` mà không nhầm số ACK với số replica có thể nhận mutation.
5. Thiết kế phép đo dựa trên latency, request rate, CPU, network, thread pools, compaction, tombstone và phân bố khóa.
6. Thực hành CQL và Java để so sánh traffic phân bố đều với traffic tập trung vào một partition, rồi tối ưu có kiểm soát.

> **Phạm vi thao tác:** các ví dụ tạo dữ liệu và sinh tải chỉ dành cho lab/staging. Không đẩy tải lớn lên cluster sản xuất để “thử cân bằng”, không đổi replication factor hoặc compaction strategy trước khi có bằng chứng nút nghẽn.

## 1. Hai vai trò khác nhau trong cùng một node

**Coordinator** là node tiếp nhận request từ client, xác định replica liên quan, gửi yêu cầu đến các replica, đợi đủ phản hồi theo consistency level, tổng hợp kết quả và trả phản hồi cho client. **Replica** là node được placement chọn để giữ dữ liệu của partition và thực hiện phần đọc/ghi trên storage cục bộ.

Một node có thể đồng thời là coordinator **và** một replica cho partition đang truy vấn. Ngược lại, một coordinator không nhất thiết chứa replica của partition đó; khi ấy nó còn phải chuyển request đến những node có dữ liệu.

~~~mermaid
flowchart LR
    J["Java client"] --> C["Coordinator C"]
    C --> R1["Replica R1"]
    C --> R2["Replica R2"]
    C --> R3["Replica R3"]
    R1 --> C
    R2 --> C
    R3 --> C
    C --> J
~~~

### Tải được tạo ở đâu?

| Công việc | Coordinator thường chịu | Replica thường chịu |
| --- | --- | --- |
| Kết nối client/CQL protocol | Nhận, giải mã request và gửi response | Có thể nhận request khác khi làm coordinator cho client khác |
| Tính routing, chọn endpoints | Xác định replica từ metadata/token | Không tự chọn tất cả endpoints cho request đang được phục vụ |
| Ghi mutation | Phân phối mutation, quản lý ACK, timeout/hints tùy tình huống | Ghi commit log, cập nhật memtable, flush SSTable |
| Đọc | Gửi data/digest requests, hòa giải kết quả, có thể read repair | Đọc memtable/SSTable, lọc theo clustering, áp dụng TTL/tombstone |
| Bảo trì dữ liệu | Có thể chịu tải điều phối các hoạt động khác | Compaction, flush, repair/streaming, I/O cục bộ |
| Trả dữ liệu lớn | Serialization/protocol/network ra client | Đọc và truyền dữ liệu/digest đến coordinator |

**Kết luận chẩn đoán:** nếu C có rất nhiều yêu cầu client nhưng ít dữ liệu local cho các partition ấy, C có thể nghẽn ở vai trò coordinator/network. Nếu R2 giữ những partition được truy cập nhiều, R2 có thể quá tải **dù không phải coordinator của phần lớn request**.

Tránh suy luận “CPU cao ở node nào thì client chắc chắn đã kết nối node đó”. CPU cao cũng có thể do replica reads, compaction, repair, flush, streaming, GC hoặc công việc nền khác.

## 2. Partition key quyết định replica; driver chọn coordinator

Cassandra dùng **partition key** để tính token. Replication strategy, token ownership, datacenter và rack quyết định **tập replica tự nhiên** của partition; đây là việc của metadata/placement trong cluster. Driver chọn node nào làm **coordinator** cho một request; hai quyết định có liên quan nhưng **không giống nhau**.

Giả sử có bốn node cùng datacenter và RF=3:

~~~text
Partition P1 -> replicas: N1, N2, N3
Partition P2 -> replicas: N2, N3, N4
Partition P3 -> replicas: N1, N3, N4

Mọi request tới P1 đều cần dữ liệu/ghi trên tập replica của P1,
nhưng coordinator có thể là N1, N2, N3 hoặc node khác tùy routing.
~~~

**Token-aware routing** là cách driver ưu tiên coordinator thuộc tập replica của partition (thường ưu tiên replica trong **local DC** khi cấu hình phù hợp). Điều này có thể giảm một bước chuyển tiếp và phân bố trách nhiệm điều phối giữa các node có dữ liệu. Nhưng nó **không thay tập replica của P1** và **không làm P1 tự động phân tán sang mọi node** khi P1 trở thành hot partition.

~~~mermaid
flowchart TD
    A["CQL + giá trị partition key"] --> B{"Driver xác định routing key?"}
    B -->|Có| C["Lấy danh sách replicas/token-aware"]
    C --> D["Ưu tiên replica hợp lệ trong local DC"]
    B -->|Không| E["Chọn coordinator theo policy/fallback"]
    D --> F["Coordinator điều phối đọc/ghi"]
    E --> F
    F --> G["Replica thực thi theo placement + CL"]
~~~

### Điều kiện để token-aware routing có ích

- Driver có metadata topology và schema phù hợp; có thể xác định **routing key** của statement.
- Query đặt đủ thành phần **partition key** và sử dụng statement/binding mà driver hiểu cách gắn routing key, thường là **prepared statement** với marker `?` ở các vị trí thích hợp.
- `CqlSession` cấu hình **local datacenter** đúng và load-balancing policy không bị tùy chỉnh sai.
- Các node replica đang sẵn sàng; khi replica ưu tiên down hoặc kết nối lỗi, driver có thể chọn coordinator khác theo policy.

Không thể kết luận driver “đang token-aware” chỉ vì một câu `SELECT` trả nhanh. Cần nhìn **coordinator được chọn theo từng request** và đối chiếu với partition routing, trạng thái node, topology và metrics.

**Điểm tinh tế:** token-aware giúp **phân bổ coordinator** và giảm hop, nhưng nếu 90% traffic cùng một partition, nhóm replica của partition đó vẫn phải xử lý rất nhiều yêu cầu. Để chữa replica hotspot, thường phải **thiết kế lại khóa/kiểu truy vấn hoặc chia nhỏ dữ liệu nóng**, không chỉ chỉnh connection pool.

## 3. Consistency level tạo bao nhiêu công việc?

Với keyspace `NetworkTopologyStrategy` có **RF=3 trong một datacenter**, số phản hồi tối thiểu cần để hoàn thành:

| Consistency level | Read cần đủ | Write cần đủ | Chú ý |
| --- | ---: | ---: | --- |
| `ONE`/`LOCAL_ONE` | 1 replica (local với `LOCAL_ONE`) | 1 ACK (local với `LOCAL_ONE`) | Có thể trả dữ liệu chưa cập nhật ở replica khác |
| `LOCAL_QUORUM` | 2 replica thuộc local DC | 2 ACK thuộc local DC | Nhiều replica phải đáp ứng; có thể có digest comparison/read repair |
| `ALL` | 3 replica | 3 ACK | Rất nhạy với một replica chậm hoặc down |

**Số ACK đợi không bằng số mutation được gửi.** Đường ghi Cassandra thường phân phối mutation tới các replica được placement chọn, kể cả khi CL chỉ cần một hoặc hai ACK; node down có thể được phục vụ sau bằng hinted handoff/repair tùy điều kiện. Không diễn giải `ONE` là “chỉ có đúng một replica nhận dữ liệu”.

Với đọc `LOCAL_QUORUM`, coordinator có thể lấy một full-data response và digest từ replica khác, rồi cần **đọc bổ sung/read repair** nếu thấy mismatch. Do đó tải đọc phụ thuộc cả **CL, data size, sự khác biệt replica và tình trạng node**, không chỉ tổng số câu `SELECT`.

### Mô hình ước lượng, không phải phép đo thực tế

Nếu một partition nóng được đọc `Q` lần/giây ở RF3, `LOCAL_QUORUM` cần tối thiểu hai replica tham gia đáp ứng mỗi read thành công; tổng lượng công việc liên quan replica có thể cỡ **2Q hoặc lớn hơn**, do digest, retry, speculative execution và repair. Phân bố công việc giữa ba replica không nhất thiết là 1/3 đều tuyệt đối.

Với ghi, một mutation có thể được gửi đến **nhiều replica hơn số ACK cần chờ**. Do đó giảm write CL từ `LOCAL_QUORUM` xuống `ONE` không tự chia ba I/O ghi hoặc loại bỏ áp lực compaction.

### Trong nhiều datacenter

`LOCAL_QUORUM` được tính trong **datacenter của coordinator**, chẳng hạn 2/3 ở `dc_a`; ACK remote `dc_b` không thay thế ACK local còn thiếu. Replication remote vẫn có thể diễn ra, tạo network/I/O khác với số phản hồi client chờ. Nếu driver chạy ở vùng B nhưng định tuyến tới coordinator A, yêu cầu có thể chịu thêm WAN RTT và tạo coordinator load không mong muốn ở A.

**Không tự giảm CL để xử lý CPU cao** khi nghiệp vụ cần đọc-sau-ghi hoặc độ mới nhất định; thay đổi CL là thay đổi bảo đảm nhất quán và khả năng sẵn sàng.

## 4. Hai dạng nóng: coordinator hotspot và replica hotspot

### 4.1. Coordinator hotspot

Một node có quá nhiều kết nối hoặc request từ client so với các node khác. Nguyên nhân thường gặp:

- Client chỉ cấu hình **một địa chỉ** và policy không chuyển tải phù hợp.
- Driver cũ/cấu hình sai local DC; custom load balancing khiến phần lớn request đi qua một coordinator.
- Ứng dụng liên tục mở `CqlSession` mới, làm handshake/auth/pool churn.
- Request thiếu routing key, tạo nhiều lần chuyển tiếp coordinator → replica.
- Retry/speculative execution quá mạnh làm một số node nhận thêm request khi hệ thống đã quá tải.

Dấu hiệu cần kiểm tra là **coordinator request count, kết nối, in-flight requests, CPU/GC, network ra client và latency**, không chỉ kích thước dữ liệu trên đĩa.

### 4.2. Replica hotspot

Một số partition đặc biệt nóng luôn đi tới tập replica cố định. Nguyên nhân:

- Partition key dùng hằng số như `tenant_id='global'` hoặc chỉ dùng một tenant có traffic cực lớn.
- Một khách hàng/thiết bị nhận nhiều sự kiện trong cùng bucket thời gian.
- Partition quá lớn, nhiều tombstone hoặc phải đọc nhiều SSTable.
- Một replica đang compaction/repair/streaming khiến cùng một lượng traffic tạo latency cao hơn.
- Replica placement hoặc số lượng node không đáp ứng mức tải thực; vnode/token ownership chưa cân bằng theo **mức nóng**, dù dung lượng cân bằng.

Một node có thể **ít làm coordinator nhưng CPU/disk rất cao** vì đọc/ghi của các hot partition nó đang giữ. Thêm contact points hoặc round-robin giữa coordinator **không làm giảm dữ liệu mà replica đó bắt buộc phải xử lý**.

### 4.3. Phân biệt bằng chứng

| Quan sát | Hướng nghi ngờ đầu tiên | Dữ liệu cần thêm |
| --- | --- | --- |
| C1 nhận phần lớn CQL requests, nhưng CPU replica khác cũng tăng | Coordinator routing không đều | Coordinator histogram theo driver, routing key, network |
| C1 ít nhận CQL requests nhưng disk I/O/read latency rất cao | Replica hot / compaction / tombstone | Partition histogram, table latency, compaction, SSTable |
| Mỗi node có coordinator requests khá đều, một node CPU rất cao | Placement/hot partition hoặc nền | Token ranges, traffic theo key, node metrics |
| Cả cluster latency tăng theo tải, queues dài | Quá tải toàn cụm hoặc retry amplification | Request rate, in-flight, dropped messages, retry count |
| Chỉ client ở DC B chậm | WAN/local DC routing khác | Coordinator DC, RTT, CL, cross-DC metrics |
| CPU bình thường nhưng p99 cao | Disk I/O, timeout, compaction, network, GC pauses | Per-stage/queue latency, I/O, GC, logs |

## 5. Chia đều token chưa chắc chia đều tải

Các virtual nodes (*vnodes*) giúp quản lý phân bố token ranges, nhưng **data size balance không đồng nghĩa request rate balance**. Một partition hot là một đơn vị placement: replica set của nó không tự mở rộng chỉ vì cluster có thêm node.

~~~text
Node   SSTable size     Client coordinator RPS     Replica work/CPU
N1     300 GiB          1.000                      Rất cao (hot partition)
N2     310 GiB          1.050                      Rất cao (hot partition)
N3     290 GiB            950                      Rất cao (hot partition)
N4     305 GiB          1.000                      Thấp hơn

=> Dung lượng và coordinator RPS gần cân bằng,
   nhưng N1/N2/N3 là replica của partition rất nóng.
~~~

Đây là **số liệu giả định** chỉ dùng để diễn giải. Khi phân tích thật, cần xác minh partition/range và công việc nền chứ không quy hết CPU cao cho một key.

### Các cách xử lý hợp lý

1. **Chỉnh thiết kế bảng theo truy vấn:** nếu thường đọc “20 sự kiện gần nhất của một khách hàng/ngày”, dùng composite partition key có tenant, customer và bucket, không dùng một khóa `global`.
2. **Chia bucket theo thời gian:** ngày/giờ phù hợp tốc độ ingest và độ lớn partition. Bucket quá lớn tạo hot partition, nhưng quá nhỏ tăng fan-out khi đọc.
3. **Sharding có chủ đích:** khi một partition vẫn quá nóng, thêm `shard_no` vào partition key dựa trên hash/event ID và giới hạn số shard. Đọc phải fan-out/merge kết quả qua các shard.
4. **Tách workload list/detail hoặc dữ liệu lớn:** giảm dữ liệu phải đọc/serialize cho đường API thường gặp.
5. **Kiểm soát query fan-out:** một request HTTP không được quét hàng trăm partition không giới hạn.
6. **Bổ sung node/tăng năng lực** nếu tải tổng thật sự vượt công suất và placement sau mở rộng có thể giảm bottleneck.

**Không thay partition key bằng `ALLOW FILTERING`**, và không sharding mù quáng: thêm shard có chi phí đọc nhiều partition, thứ tự toàn cục, ghi/đối soát và migration dữ liệu. Thay schema cần kế hoạch chuyển đổi từ khóa cũ sang khóa mới, không sửa primary key của bảng đang chứa dữ liệu bằng một `ALTER TABLE` đơn giản.

## 6. Truy vấn rộng và payload lớn làm coordinator quá tải

Ngay cả khi coordinator được phân đều, một request truy vấn không giới hạn có thể gây áp lực không tương xứng:

- `SELECT *` trên partition lớn tạo nhiều byte response và bộ nhớ xử lý.
- `ALLOW FILTERING` hoặc quét nhiều token ranges có thể buộc nhiều replica tham gia.
- Đọc nhiều trang kết quả liên tiếp tạo nhiều request/response; `pageSize` quá nhỏ làm tăng round-trip, quá lớn làm tăng payload/heap/GC.
- Bảng có nhiều tombstone làm replica duyệt nhiều dữ liệu để trả ít hàng sống; coordinator có thể phải chờ read repair hoặc timeout.
- `COUNT(*)` trên diện rộng không thay thế hệ thống phân tích/OLAP.

**Nên thiết kế đường đọc có giới hạn**: biết partition key, clustering range, số hàng tối đa, projection cột cần thiết, page size và tổng số trang. Nếu ứng dụng cần báo cáo tổng hợp nhiều partition, cân nhắc pre-aggregation, pipeline phân tích hoặc bảng truy vấn riêng thay vì gom mọi việc vào một coordinator.

### Chi phí phải tách riêng

| Chỉ số | Dùng để kiểm tra |
| --- | --- |
| Client request bytes / response bytes | Projection, payload, số hàng |
| Client request latency p50/p95/p99 | Thời gian ứng dụng thấy, gồm network/driver |
| Coordinator requests và in-flight | Định tuyến và nghẽn xử lý request |
| Replica read/write latency | Đường lưu trữ, tombstone, SSTable, compaction |
| Network giữa các node và ra client | Chuyển tiếp, replication, multi-DC |
| Retries/speculative executions | Khuếch đại tải do client khi node chậm |
| Pending tasks/dropped messages | Thành phần xử lý không theo kịp |

Một request CQL phía client có thể gây nhiều thông điệp trong cụm. **Không lấy số HTTP requests bằng số replica operations** hoặc số network packets.

## 7. Java Driver 4.x và phân phối coordinator

Driver Cassandra Java 4.x có cơ chế load balancing dựa trên metadata topology; cấu hình mặc định phù hợp sẽ ưu tiên replica/local DC khi xác định được routing key. Nên dùng **prepared statements**, cấu hình **local datacenter** rõ ràng và tái sử dụng `CqlSession`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;

import java.net.InetSocketAddress;

public final class CassandraConnections {
    public static CqlSession create() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

Các địa chỉ IP là **ví dụ lab**. Ứng dụng thật cần contact points hợp lệ, authentication, TLS, timeouts, DNS/service discovery và local DC đúng snitch. Contact points chủ yếu hỗ trợ **khám phá cluster**; không phải danh sách cứng duy nhất các coordinator mà driver được phép sử dụng sau khi biết topology.

### Những lựa chọn có thể phá cân bằng

| Thiết kế phía client | Rủi ro | Thay bằng |
| --- | --- | --- |
| Tạo một `CqlSession` trên mỗi HTTP request | Handshake, connection churn, CPU/GC | Tái sử dụng session dài hạn |
| Viết một routing layer luôn dùng một node | Coordinator hotspot | Chính sách load balancing/driver được cấu hình đúng |
| Query thiếu/bỏ sót phần partition key | Không xác định được token hoặc tạo truy vấn không hợp lệ/quét rộng | Prepared statement và đủ khóa |
| Fan-out hàng nghìn query cùng lúc | Tăng in-flight, saturate pool/node | Concurrency giới hạn, backpressure |
| Retry mọi timeout ngay lập tức | Thêm tải khi node đang chậm; write không chắc thất bại | Retry có ngân sách, idempotency và phân loại lỗi |
| Speculative execution quá mạnh | Gửi bản sao request, tăng tổng tải | Chỉ dùng cho request idempotent, có đo lường và cấu hình phù hợp |
| Định tuyến nhầm local DC | WAN RTT, coordinator load ở vùng sai | `withLocalDatacenter` và giám sát coordinator thực tế |

**Retry không phải luôn an toàn:** nếu một write timeout, một số replica có thể đã xử lý. Với counter, LWT hoặc side effect ngoài Cassandra, retry tùy tiện có thể sai nghiệp vụ. Chỉ đánh dấu statement idempotent khi thực sự có căn cứ, và vẫn giới hạn tần suất retry khi quá tải.

## 8. Lab RF=3 trên bốn node: quan sát phân bố công việc

### 8.1. Điều kiện trước khi chạy

Chuẩn bị cluster lab **bốn node cùng một datacenter** tên `datacenter1`, replication factor ba bản sao. Nếu lab khác tên DC, thay đúng trong lệnh tạo keyspace. Không chạy thử tải với bảng production.

~~~bash
# Chạy trên node lab có quyền quản trị.
nodetool status
~~~

Kỳ vọng cả bốn node `UN` (*Up/Normal*), không có bootstrap/decommission/repair lớn đang chạy. Lưu phiên bản, CPU, RAM, disk và network để phân tích kết quả có bối cảnh.

### 8.2. Tạo keyspace và bảng có partition bucket

~~~sql
CREATE KEYSPACE IF NOT EXISTS resource_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS resource_lab.events_by_customer_day (
    tenant_id text,
    customer_id uuid,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    event_type text,
    summary text,
    PRIMARY KEY ((tenant_id, customer_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

Trong bảng này:

- `(tenant_id, customer_id, event_day)` là **composite partition key**. Các hàng cùng tenant/khách/ngày chia sẻ một partition.
- `event_ts` và `event_id` là clustering columns. Thứ tự giảm dần cho phép đọc sự kiện gần nhất trong partition.
- Chọn `event_day` giúp giới hạn kích thước partition theo ngày, nhưng **không bảo đảm** cân bằng tải nếu một khách hàng ghi hàng chục nghìn lần mỗi giây vào cùng ngày.
- Không có TTL hay `DELETE` trong lab ban đầu để loại bớt ảnh hưởng tombstone.

`IF NOT EXISTS` **không sửa** keyspace/bảng đã tồn tại. Xác minh replication của lab trước khi tính CL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'resource_lab';
~~~

### 8.3. Nạp dữ liệu mẫu và truy vấn có giới hạn

~~~sql
INSERT INTO resource_lab.events_by_customer_day
    (tenant_id, customer_id, event_day, event_ts, event_id,
     event_type, summary)
VALUES (
    'tenant-a', 11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:30:00Z',
    22222222-2222-4222-8222-222222222222,
    'PAYMENT', 'paid-order-01'
);
~~~

Trong `cqlsh` đặt read consistency theo môi trường một DC:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
SELECT event_ts, event_id, event_type, summary
FROM resource_lab.events_by_customer_day
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

Câu `SELECT` có đủ partition key và trần 20 hàng, không cần `ALLOW FILTERING`. Bản thân một hàng mẫu không tạo tải đáng kể; muốn quan sát nóng, cần sinh nhiều dữ liệu và request **có giới hạn từ một workload generator của lab**, không dùng một câu `SELECT` duy nhất để rút kết luận.

### 8.4. Hai pha tạo tải được kiểm soát

Để cô lập tác động phân bố khóa, giữ nguyên **tổng QPS, query shape, page size, CL, payload và thời gian đo**:

| Pha | Phân bố partition key | Dự đoán |
| --- | --- | --- |
| **A — Phân tán** | Nhiều cặp `customer_id + event_day` khác nhau, có dữ liệu tương đương | Replica work có cơ hội trải trên nhiều node |
| **B — Tập trung** | Một hoặc vài `customer_id + event_day` nóng | Tập replica của partition nóng có thể chịu CPU/disk cao |

Giữ số request đồng thời trong ngân sách lab. Bắt đầu với tải thấp, tăng từng mức có kiểm soát, dừng nếu p99, timeouts, pending tasks hoặc disk I/O vượt giới hạn đã định. Không chạy hai pha song song rồi so sánh vì compaction/cache và áp lực tài nguyên khác nhau.

**Chú ý:** các partition khác nhau không nhất thiết cho chia tải hoàn toàn đều trong mẫu ngắn. Driver có thể chọn coordinator khác nhau; token distribution, rack, cache và lỗi node cũng tác động. Dùng nhiều khóa và nhiều chu kỳ đo.

## 9. Java Driver: ghi nhận coordinator và độ trễ từng request

Mẫu sau minh họa **đọc có giới hạn** và log coordinator thực tế mà Java Driver 4.x báo cho request thành công. Nó không ép driver dùng một IP cố định; prepared statement có đủ partition key để driver có cơ hội token-aware routing.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.metadata.Node;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class CoordinatorProbe {
    public record Observation(String coordinator, int rows, long elapsedMicros) {}

    private final CqlSession session;
    private final PreparedStatement read;

    public CoordinatorProbe(CqlSession session) {
        this.session = session;
        this.read = session.prepare(
            "SELECT event_ts, event_id, event_type, summary " +
            "FROM resource_lab.events_by_customer_day " +
            "WHERE tenant_id = ? AND customer_id = ? " +
            "AND event_day = ? LIMIT 20");
    }

    public Observation query(
            String tenantId, UUID customerId, LocalDate eventDay) {
        BoundStatement statement = read.bind(tenantId, customerId, eventDay)
            .setPageSize(20)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(true);

        long started = System.nanoTime();
        ResultSet result = session.execute(statement);
        ExecutionInfo info = result.getExecutionInfo();
        Node coordinator = info.getCoordinator();

        int rows = 0;
        for (Row row : result) {
            rows++;
            // Giải mã giá trị được trả để đo phần client đọc dữ liệu.
            row.getString("summary");
        }

        long elapsedMicros = TimeUnit.NANOSECONDS.toMicros(
            System.nanoTime() - started);
        String endpoint = coordinator == null
            ? "unknown"
            : coordinator.getEndPoint().toString();

        System.out.printf(
            "key=%s day=%s coord=%s rows=%d time_us=%d%n",
            customerId, eventDay, endpoint, rows, elapsedMicros);
        return new Observation(endpoint, rows, elapsedMicros);
    }
}
~~~

**Cách dùng để phân tích:**

1. Dùng **một `CqlSession` tái sử dụng** với local DC chính xác, không tạo session mới trong mỗi vòng lặp.
2. Gọi `query` trên nhiều `customerId` thuộc các partition khác nhau, lưu số request theo `coordinator`.
3. Gọi `query` trên một `customerId` cố định trong cùng ngày, rồi so sánh phân bố coordinator, latency và tài nguyên **replica**.
4. Đối chiếu với `nodetool`/metrics theo node; **coordinator histogram của Java không phải biểu đồ replica work**.
5. Khi statement timeout, ghi nhận **READ_ERROR** riêng, không xem như truy vấn thành công có `0` hàng.

Mã trên cố ý **không** tạo workload generator chạy vô hạn. Một phép thử thực tế cần rate limiter, giới hạn in-flight, thời gian chạy, kiểm soát warm-up và tránh logs đồng bộ chiếm CPU. `LIMIT 20` cùng `pageSize(20)` giữ kết quả nhỏ; tuy nhiên số request lớn vẫn có thể quá tải cluster.

### Vì sao log coordinator vẫn chưa đủ?

Nếu `query` được route từ nhiều coordinator khác nhau đến **cùng hot partition**, các replica vẫn có thể chịu tải cao. Ngược lại, một coordinator có số request lớn có thể chỉ đang trả nhiều request cực nhẹ. Phải đo thêm **request cost**: bytes, rows, latency, read repair, timeout và CPU/I/O của các replica.

## 10. Thu thập chỉ số theo node và theo truy vấn

### 10.1. Công cụ cơ bản

~~~bash
# Chạy trong lab trên các node tương ứng, không chỉ một node.
nodetool status
nodetool tpstats
nodetool tablestats resource_lab.events_by_customer_day
nodetool compactionstats
nodetool netstats
~~~

Tùy phiên bản Cassandra, có thể xem thêm histogram/phân bố latency bằng `nodetool tablehistograms` hoặc metrics/JMX. Tên metric, stage và hình thức hiển thị có thể đổi giữa các phiên bản hoặc hệ phân phối; ghi rõ phiên bản khi lập dashboard.

| Nguồn | Chỉ số cần đo | Vì sao cần |
| --- | --- | --- |
| Java Driver/ứng dụng | Request rate theo coordinator, retries, speculative executions, in-flight, p95/p99 | Kiểm tra phân phối coordinator và amplification |
| Cassandra client request metrics | Read/write latency, timeouts, unavailable, failures | Phản ánh áp lực điều phối và độ sẵn sàng |
| Thread pools / messaging | Pending/active/dropped tasks/messages theo nhóm | Phát hiện queue tăng khi node không theo kịp |
| Table metrics | Read/write latency, SSTables, tombstones, partition sizes | Phân biệt hot data với coordinator bottleneck |
| OS/container | CPU, RSS/heap, GC pause, disk IOPS/latency, network | Kiểm tra nút nghẽn tài nguyên |
| Repair/compaction/streaming | Pending compactions, bytes streamed, hoạt động bảo trì | Công việc nền có thể tranh tài nguyên với client |
| Topology | Node `UN`/`DN`, DC/rack, token ownership | Kiểm tra khả năng phân bố và lỗi node |

**Lưu ý về metrics:** `nodetool status` cho biết `Load`/ownership, nhưng **không đo trực tiếp QPS của từng hot partition**. `tablestats` thường tổng hợp theo **bảng trên node**; nó không tự cho biết một request cụ thể do node đó làm coordinator hay replica. Muốn kết luận cần **tương quan nhiều nguồn** (driver, tracing chọn mẫu, JMX, logs, CPU/disk và traffic theo khóa).

### 10.2. Chọn tracing hợp lý

Trong `cqlsh`:

~~~text
TRACING ON
~~~

~~~sql
SELECT event_ts, event_id, event_type, summary
FROM resource_lab.events_by_customer_day
WHERE tenant_id = 'tenant-a'
  AND customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

~~~text
TRACING OFF
~~~

Trace có thể cho biết coordinator, replica được liên lạc, data/digest requests, chậm ở bước nào, và có đọc bổ sung/read repair không. **Không bật tracing toàn bộ traffic sản xuất** chỉ để đếm coordinator; tracing tạo overhead và dữ liệu hệ thống. Khi có `trace ID`, liên kết nó với timestamp, request ID, partition key đã ẩn danh và metrics tương ứng.

## 11. Quy trình tối ưu có bằng chứng

### Bước 1 — Đặt giả thuyết kiểm chứng được

Ví dụ:

> “p99 cao vì tất cả Java clients dùng một coordinator không phù hợp, tạo thêm hop,”

hoặc:

> “p99 cao vì một customer cực nóng làm ba replica của partition đó quá tải, dù coordinator đã được phân đều.”

Hai giả thuyết này có **hành động khắc phục khác nhau**. Đừng đồng thời thay routing, RF, page size, compaction, heap và partition key rồi không biết yếu tố nào tạo thay đổi.

### Bước 2 — Thu baseline dưới tải đại diện

Giữ nguyên:

- Query shape và tỷ lệ read/write;
- RF, CL, số node sống và tên DC;
- Tập partition keys và mức độ nóng, payload/row size;
- Page size, retry/speculative policies, mức request concurrent;
- Các job compaction/repair/streaming lớn có thể ảnh hưởng thời điểm đo.

Thu ít nhất p50/p95/p99, error rate, in-flight, request count theo coordinator, CPU/I/O và số node replica chịu tải cao.

### Bước 3 — Chọn đúng đòn bẩy

| Nút nghẽn đã có bằng chứng | Thử thay đổi trước | Điều không nên làm |
| --- | --- | --- |
| Coordinator skew, driver route sai | Sửa local DC, policy, routing key, contact points; tái sử dụng session | Thay PK/RF khi chưa cần |
| Replica hot do một partition | Chia bucket/shard theo nhu cầu đọc, thay thiết kế bảng | Chỉ tăng số coordinator |
| Quá nhiều hàng/bytes | Projection, clustering range, LIMIT/page size | Giảm CL để che lượng dữ liệu |
| Retry/speculation tăng vọt | Giới hạn retry, speculation; kiểm soát in-flight | Mở nhiều request hơn lúc node đang quá tải |
| Compaction/tombstone/disk I/O | Phân tích TTL, schema, compaction và repair schedule | Tăng thread pool mù quáng |
| Toàn cluster vượt công suất | Thêm capacity theo kế hoạch, benchmark placement mới | Giả định thêm node tự chữa hot partition |
| Cross-DC latency | Định tuyến app vào local DC, kiểm tra RF/CL | Chọn coordinator remote mà không đánh giá WAN/RPO |

### Bước 4 — Canary và so sánh

Áp dụng thay đổi trước trên lab hoặc nhóm traffic nhỏ có kiểm soát, giữ cùng mục tiêu độ nhất quán. So sánh cùng cửa sổ tải và thống kê **cả request lỗi**. Nếu throughput tăng nhưng timeout/p99 xấu hơn, chưa thể gọi là tối ưu thành công.

### Bước 5 — Kế hoạch quay lui

Sửa routing policy/timeout có thể quay lại tương đối nhanh, nhưng **đổi partition key hoặc thêm shard là migration dữ liệu**, không tự hoàn nguyên bằng một lệnh CQL. Cần song song ghi/đọc có kiểm soát, kiểm chứng marker và cơ chế idempotent. Nếu node mới thêm hay topology thay đổi, theo dõi streaming/repair và dung lượng.

## 12. Những ngộ nhận dễ dẫn tới xử lý sai

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Cassandra phân tán nên mọi node sẽ tự nhận số request bằng nhau.” | Phụ thuộc driver policy, coordinator selection, partition popularity và replica placement. |
| “Tăng contact points sẽ chia hot partition ra mọi node.” | Contact points hỗ trợ kết nối/khám phá; hot partition vẫn thuộc tập replica của nó. |
| “Node CPU cao chắc chắn đang làm coordinator nhiều nhất.” | Có thể chịu replica reads, compaction, repair, flush hoặc GC. |
| “`ONE` chỉ ghi một bản sao nên nhẹ hơn RF3 đúng ba lần.” | Write thường phân phối tới các replica; CL xác định ACK phải đợi, không phải số bản sao cấu hình. |
| “`LOCAL_QUORUM` ở DC A có thể dùng ACK remote DC B để đủ hai.” | Quorum local chỉ tính replica trong DC của coordinator. |
| “Đặt page size rất nhỏ sẽ luôn giảm latency.” | Có thể làm tăng số lần fetch và RTT tổng nếu đọc nhiều trang. |
| “Thêm node luôn giải quyết hot key.” | Nếu tập replica của hot partition vẫn có giới hạn và tải tập trung, cần xem xét chia key/capacity. |
| “`nodetool status` Load đều là tải CPU/QPS đều.” | Load chủ yếu phản ánh dữ liệu/ownership, không đại diện phân bố lưu lượng nóng. |
| “Timeout nghĩa là query không chạy ở bất cứ replica nào.” | Write có thể đã áp dụng một phần; read timeout không chứng minh hàng vắng. |
| “Đọc `SELECT *` nhanh trong lab chứng minh production cũng nhanh.” | Payload, tombstones, concurrency, cache và network ở production khác. |

## 13. Bài tập thực hành

**Bài 1 — Phân biệt vai trò.** Một node nhận 15% CQL requests từ driver nhưng CPU đạt 95%, còn node khác nhận 35% request nhưng CPU chỉ 35%. Nêu ít nhất năm giả thuyết và các metrics cần thu để phân biệt coordinator load, replica hotspot, compaction và GC.

**Bài 2 — CL không quyết định số replica lưu dữ liệu.** Với RF3 một DC, tính số ACK/replica đáp ứng cần cho `LOCAL_ONE`, `LOCAL_QUORUM` và `ALL`. Giải thích vì sao ghi `ONE` thành công không đồng nghĩa các replica khác không nhận mutation.

**Bài 3 — Token-aware.** Tạo prepared statement với đủ `(tenant_id, customer_id, event_day)` và log `ExecutionInfo.getCoordinator()` cho nhiều khóa khác nhau. Nếu coordinator không đồng đều, bạn cần kiểm tra policy, trạng thái node, local DC và tập replica như thế nào trước khi kết luận routing lỗi?

**Bài 4 — Hot partition.** Một tenant có một thiết bị gửi 10.000 event/giây vào partition `(tenant_id, device_id, day)`. Hãy đề xuất bucket theo giờ hoặc shard có giới hạn, nêu rõ thay đổi truy vấn “100 event mới nhất” và cách merge kết quả từ nhiều partition.

**Bài 5 — Đo sai lệch.** Pha A dùng 1.000 customer keys, pha B dùng một customer key; tổng QPS không đổi. Hãy nêu cách so CPU theo node, coordinator counts, replica/table latency và p99 để phát hiện replica hotspot thay vì chỉ nhìn request count.

**Bài 6 — Retry storm.** Một node chậm, Java Driver retry và speculative execution quá thường xuyên. Giải thích vòng phản hồi có thể khiến p99 tăng và đề xuất rate limit, retry budget, backpressure và cách xác định statement idempotent.

**Bài 7 — Multi-DC.** Client ở `dc_b` nhưng `CqlSession` đặt local DC là `dc_a`. Điều gì xảy ra với coordinator routing, WAN latency và ý nghĩa `LOCAL_QUORUM`? Nếu failover sang `dc_b`, cần xác minh những điều gì về dữ liệu remote trước khi cho phép ghi?

**Bài 8 — Lập kế hoạch sản xuất.** Chọn một trường hợp nghẽn cụ thể, định nghĩa baseline, giả thuyết, một thay đổi canary, điều kiện PASS/FAIL, rollback và biên bản kết quả. Không sử dụng `COUNT(*)` toàn bảng hoặc `ALLOW FILTERING` để tạo “benchmark” quét rộng.

## Ghi nhớ

**Coordinator quyết định đường điều phối request; replica xử lý dữ liệu của những partition nó được phân công.** Token-aware routing có thể cân bằng coordinator và giảm chuyển tiếp, nhưng không tự phân tán một hot partition ra ngoài tập replica của nó. Để tối ưu tài nguyên Cassandra, phải đo **cả traffic theo coordinator lẫn tải trên replica**, đối chiếu partition key, RF/CL, page size, retry/speculation, compaction và topology. Hãy sửa nguyên nhân thật bằng thiết kế bảng theo truy vấn, routing đúng local DC, giới hạn fan-out và benchmark có kiểm soát; không thay đổi consistency hoặc mở rộng node mù quáng.
