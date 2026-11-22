# Slow query logging và công cụ theo phiên bản trong Apache Cassandra

## 1. Tại sao cần nhận diện truy vấn chậm thay vì chỉ xem CPU hoặc average latency?

Apache Cassandra là cơ sở dữ liệu phân tán theo mô hình **wide-column**, phân phối partition theo **partition key**, nhân bản theo **replication strategy** và cho phép ứng dụng đặt **consistency level** cho thao tác CQL. Một câu SELECT hoặc INSERT có thể đi qua Java Driver, coordinator, nhiều replica, network, memtable, SSTable, compaction hoặc tác vụ repair đang chiếm tài nguyên.

Khi ứng dụng báo **p99 đọc tăng từ 80 ms lên 1.500 ms**, nhìn trung bình độ trễ toàn cluster không đủ để biết truy vấn nào đã chậm, partition nào bị ảnh hưởng hoặc thời gian bị tiêu hao ở lớp nào. **Slow query logging** giúp ghi lại các lần thực thi vượt ngưỡng; **query tracing** giúp xem luồng xử lý của một số request được chọn; **metrics/histogram** cho biết vấn đề lớn đến mức nào.

Tình huống ví dụ:

- Một API đọc 30 sự kiện mới nhất của một thiết bị có p50 là 12 ms.
- 99% request vẫn nhanh, nhưng khoảng 1% mất hơn 800 ms.
- Một vài partition của thiết bị có nhiều tombstone và cùng dữ liệu nằm trong nhiều SSTable.
- Nếu chỉ bật log ở mức ERROR hoặc xem CPU trung bình, có thể không thấy manh mối.

Trong chương **Tracing và chẩn đoán** của module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, chúng ta tập trung vào việc thu thập bằng chứng có thể sử dụng để trả lời: **request nào chậm, đo tại đâu, vì sao chậm, công cụ nào có mặt ở phiên bản Cassandra đang chạy, và xử lý thế nào mà không làm sự cố nặng hơn**.

## 2. “Slow query log” không đồng nghĩa với tracing hay Full Query Logging

Cụm từ *slow query logging* có thể chỉ các giải pháp khác nhau tùy sản phẩm và phiên bản. Khi vận hành **Apache Cassandra**, không nên giả định luôn có một bảng hoặc một tệp log mặc định giống MySQL chứa mọi câu CQL vượt ngưỡng thời gian.

| Cơ chế | Dữ liệu chính | Khi nào hữu ích | Giới hạn quan trọng |
|---|---|---|---|
| **Application/driver slow-query log** | Query ID, latency, outcome, CL và metadata đã được làm sạch | Biết operation thực tế nào vượt ngưỡng từ góc nhìn client | Phải tự instrument hoặc dùng khả năng logging được cấu hình; không tự giải thích nội bộ replica |
| **CQL tracing** | Các bước xử lý request trên coordinator và replica | Phân tích chi tiết một request đại diện | Có overhead, chỉ bao phủ request được trace; trace data có thời hạn lưu |
| **Histogram / JMX metrics** | Phân bố latency, số thao tác, timeout, backlog | Theo dõi xu hướng p95/p99, so sánh DC/node/table | Có thể không chỉ ra truy vấn và tham số cụ thể |
| **Full Query Logging (FQL)** | Luồng CQL request/đầu vào để phục vụ ghi nhận và replay theo tính năng được hỗ trợ | Điều tra workload, tái hiện chuỗi query trong môi trường kiểm soát | **Không phải log chỉ các slow query**; không mặc định chứa tổng thời gian thực thi |
| **Audit logging** | Sự kiện truy cập và thao tác phục vụ kiểm toán | Điều tra ai thực hiện loại thao tác nào | Không được dùng thay histogram hoặc slow-query timer |
| **Server debug/TRACE logs** | Sự kiện nội bộ tùy logger và bản phát hành | Chẩn đoán hẹp theo hướng dẫn sản phẩm | Log rất nhiều, overhead và dữ liệu nhạy cảm; không bật tràn lan |

**Nguyên tắc:** để biết request có chậm vượt ngưỡng hay không, ưu tiên **timer ở biên client hoặc driver**; để biết tại sao chậm, ghép với **trace có chọn lọc** và **metrics coordinator/replica**. FQL hoặc audit có thể bổ trợ nhưng **không tự động trả lời câu hỏi p99**.

### 2.1. Thế nào là một “slow query event” hữu ích?

Một sự kiện được ghi có thể chứa:

~~~text
event=cassandra_slow_request
operation=read_device_events
duration_ms=842
threshold_ms=200
outcome=success
keyspace=telemetry
table=events_by_device_day
cl=LOCAL_QUORUM
page_size=50
dc=dc1
attempts=2
trace_id=<mã tương quan nếu thực sự có>
timestamp=<thời điểm UTC>
~~~

Các trường trên là **schema log đề xuất**, không phải định dạng log Cassandra mặc định. Nếu không có trace ID hoặc số lần attempt từ driver, phải để trống/bỏ trường; **không tự tạo ID rồi coi là server trace**.

Điều nên tránh: ghi nguyên partition key thuộc dữ liệu cá nhân, giá trị bind nhạy cảm, toàn bộ nội dung row, mật khẩu, token, raw query chứa tham số hay exception stack trace trùng lặp ở tốc độ cao. Sử dụng **query template ID** ổn định để nhóm sự cố; khi thật sự cần khóa đặc thù, dùng công cụ kiểm soát truy cập và chính sách khử định danh.

## 3. Đo ở lớp nào? Chọn ngưỡng đúng phạm vi

### 3.1. Một request CQL có nhiều loại latency

~~~mermaid
flowchart TD
    A["Service Java: bắt đầu đo end-to-end"] --> B["Java Driver: queue, chọn node, retry"]
    B --> C["Network tới coordinator"]
    C --> D["Coordinator: parse/execute, gửi tới replica"]
    D --> E["Replica: memtable, SSTable, I/O hoặc commit log"]
    E --> D
    D --> F["Đủ phản hồi theo consistency level"]
    F --> G["Network về Java Driver"]
    G --> H["Ứng dụng nhận kết quả / page"]
    I["Compaction, GC, repair, streaming"] -. tranh tài nguyên .-> E
    J["WAN, replica chậm, topology"] -. ảnh hưởng .-> D
~~~

Ví dụ hai hệ thống cùng có `Table.ReadLatency p99=20 ms`, nhưng một hệ thống có `Java request p99=700 ms`. Khoảng chênh lệch có thể nằm ở coordinator, queue, network, CL, retry hoặc thành phần không bao gồm trong metric table-local.

**Không trừ hai phân vị để suy ra một phân vị khác:** `p99(client) - p99(table)` không phải `p99(network)`, vì các p99 có thể thuộc hai tập request khác nhau.

| Nơi đo | Phạm vi có thể bao gồm | Nên dùng vào việc gì? |
|---|---|---|
| **HTTP/gRPC endpoint** | Toàn bộ business flow và các dependency | SLO người dùng |
| **Ứng dụng quanh `session.execute`** | Driver, network, coordinator, phản hồi, phần truy cập dữ liệu tương ứng | Slow-query logging từ góc nhìn ứng dụng |
| **Driver internal metrics** | Request latency, retries, speculative executions, pool/queue theo khả năng cấu hình | Phân biệt network/client và server |
| **Coordinator/client request metrics** | Đường xử lý CQL ở Cassandra coordinator | Tìm node điều phối chậm |
| **Table-level metrics** | Hoạt động local của engine trên một node | Tìm SSTable/tombstone/I/O và load tại replica |

### 3.2. Ngưỡng chậm phải theo operation

Ví dụ đặt ngưỡng **minh họa**, không phải khuyến nghị mặc định của Cassandra:

| Operation | Mẫu truy vấn | Ngưỡng logging thử nghiệm |
|---|---|---:|
| `read_device_latest` | Một partition, lấy tối đa 50 row | 200 ms |
| `write_measurement` | INSERT một mutation nhỏ | 300 ms |
| `read_daily_summary` | Truy vấn phân vùng theo ngày | 500 ms |
| `administrative_scan` | Job được kiểm soát, throughput thấp | 3.000 ms |

Không áp cùng một ngưỡng cho truy vấn tương tác nhỏ và job phân tích/batch. Đặt ngưỡng từ **SLO**, baseline theo operation, điều kiện tải và số mẫu, đồng thời theo dõi p50/p95/p99 và tỷ lệ timeout.

Một request timeout **có thể không xuất hiện trong histogram chỉ đo thành công**. Để không tạo ảo tưởng p99 tốt, phải ghi cả **outcome=timeout/error** và đếm tổng request.

### 3.3. Thời gian đầu tiên nhận kết quả khác toàn bộ thời gian đọc

Trong Java Driver, `session.execute(statement)` của một truy vấn paged có thể hoàn thành sau khi **page đầu tiên** có sẵn; việc duyệt các page tiếp theo có thể gây thêm request. Một timer chỉ bọc lệnh execute không phải thời gian tải hết hàng triệu row.

Khi báo slow query, ghi rõ đang đo:

- **Time to first page**.
- **Một page** hoặc **mỗi driver request**.
- **Time to consume all pages**.
- **Toàn bộ endpoint** (kể cả business logic).

Đối với async query, phải kết thúc timer **khi completion stage hoàn thành**, không phải ngay khi gọi `executeAsync`.

## 4. CQL tracing với cqlsh: xem một request diễn ra thế nào

### 4.1. Bật tracing cho một số câu lệnh có chủ đích

Giả sử keyspace `telemetry` đã tồn tại và bảng được thiết kế theo partition key gồm `device_id` và `event_day`.

~~~cql
TRACING ON;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

TRACING OFF;
~~~

`TRACING ON` là lệnh của **cqlsh**, không phải cú pháp SELECT thuần của CQL trong Java Driver. Khi được hỗ trợ và truy vấn tạo trace, cqlsh có thể hiển thị **trace session ID**, các hoạt động theo thứ tự thời gian và một số thông tin coordinator/replica.

Chỉ dùng tracing có chọn lọc trên những query có thể tái hiện và được cấp quyền. Tracing có chi phí tạo/ghi sự kiện nên **không bật mặc định cho mọi query production**.

### 4.2. Đọc trace theo các câu hỏi cụ thể

| Trường/tín hiệu | Ý nghĩa | Giới hạn |
|---|---|---|
| **Trace session ID** | Liên kết các event của cùng lần thực thi | Không phải request ID chung của toàn ứng dụng nếu chưa tạo liên kết |
| **Coordinator / source** | Node nào khởi tạo hoặc sinh event | Không chỉ ra nguyên nhân chậm nếu thiếu log/metrics |
| **Activity** | Bước xử lý như gửi read hoặc nhận phản hồi | Câu chữ khác theo phiên bản và loại query |
| **Source elapsed** | Mốc tương đối theo hoạt động trace trên source | Không nên cộng máy móc thành end-to-end latency |
| **Duration** | Thời lượng được ghi cho trace session khi có | Không tự bao phủ thời gian tại HTTP/client |
| **Các khoảng trống giữa event** | Gợi ý chỗ chờ, network hoặc bước chưa được trace | Không chứng minh chính xác tài nguyên nào nghẽn |

Tìm những nơi coordinator chờ replica, replica quét SSTable, hoặc bước xử lý bất thường; đối chiếu với disk latency/CPU và metrics cùng thời điểm. **Trace là bằng chứng theo sự kiện**, không phải flame graph đầy đủ; thiếu một event không chứng minh bước tương ứng không diễn ra.

### 4.3. Tra dữ liệu tracing trong system_traces

Cassandra lưu các session/event trace trong keyspace hệ thống dành cho tracing (đối với các phiên bản hỗ trợ giao diện này).

~~~cql
-- Ví dụ: thay UUID bằng session_id THỰC nhận từ tracing.
SELECT *
FROM system_traces.sessions
WHERE session_id = 11111111-1111-1111-1111-111111111111;

SELECT *
FROM system_traces.events
WHERE session_id = 11111111-1111-1111-1111-111111111111;
~~~

Ví dụ UUID chỉ là placeholder; đừng mong có dữ liệu tương ứng.

- Bảng `sessions` giữ thông tin tổng quan về phiên trace.
- Bảng `events` mô tả các sự kiện bên trong phiên.
- Dữ liệu tracing có thời hạn lưu/TTL và có thể đã bị dọn trước lúc truy vấn; việc tìm không thấy session cũ **không có nghĩa request không xảy ra**.
- Query vào system keyspace phải được cấp quyền và tránh quét toàn bộ dữ liệu sự kiện.

Trong môi trường production, ưu tiên ghi nhận trace ID tương quan với mẫu request thực sự đang điều tra và thời điểm UTC.

### 4.4. Lấy mẫu tracing tự động

Một số phiên bản Cassandra hỗ trợ lệnh quản trị như `nodetool settraceprobability` để cấu hình xác suất tracing trên node. **Không dùng như slow query log mặc định**: xác suất mẫu chọn các query theo cơ chế sampling, không chỉ chọn query chậm, và có thể làm tăng I/O/CPU.

Trước khi dùng:

~~~bash
nodetool help
nodetool help settraceprobability
~~~

Nếu bản Cassandra hỗ trợ và runbook cho phép, đặt tỷ lệ lấy mẫu **rất thấp, có thời hạn và giám sát overhead**, rồi hoàn nguyên thiết lập theo cấu hình được phê duyệt. Không chép nguyên một lệnh hoặc giá trị xác suất từ bài minh họa cho cluster đang tải cao.

## 5. Full Query Logging, audit logging và khác biệt phiên bản

### 5.1. Full Query Logging (FQL) là gì?

Trong các bản Apache Cassandra hiện đại **có hỗ trợ FQL** (chẳng hạn dòng 4.x và 5.x), cơ chế này ghi lại thông tin luồng request CQL để phục vụ phân tích và các công cụ replay phù hợp.

FQL **không tự động là một slow-query log**:

- Có thể ghi **nhiều request, bao gồm cả request nhanh**.
- Dữ liệu lưu giữ có thể là **log binary theo định dạng riêng**, không phải file text có thể grep như application log.
- Thông tin query/bind có thể nhạy cảm.
- Nó có thể tăng đáng kể disk throughput và dung lượng sử dụng.
- Việc có request trong FQL không tự chứng minh request đó chậm bao nhiêu; vẫn cần timer và correlation.

Một số phiên bản cung cấp những lệnh `nodetool` quản lý FQL như `enablefullquerylog` và `disablefullquerylog`. **Kiểm tra trợ giúp trực tiếp** trước khi chạy:

~~~bash
nodetool help
nodetool help enablefullquerylog
nodetool help disablefullquerylog
~~~

Không bật FQL diện rộng trong sự cố disk-full chỉ để “tìm câu SQL chậm”: việc ghi thêm lượng lớn log có thể làm sự cố nghiêm trọng hơn. Cần hiểu path lưu, cơ chế rotation/quota, retention và dữ liệu nhạy cảm trước khi bật.

### 5.2. Audit logging không phải slow-query timer

Audit logging phục vụ kiểm tra truy cập và sự kiện thao tác, được các bản Cassandra hỗ trợ theo cấu hình/tính năng cụ thể. Nó có thể giúp biết ai gọi dạng CQL nào hoặc thao tác quản trị gì, nhưng **không thay phân phối latency ở client**.

Không kết luận “truy vấn có trong audit log nghĩa là chậm” hoặc “không có trong audit log nghĩa là không chạy”, vì scope/filter và trạng thái bật audit ảnh hưởng dữ liệu thu được.

### 5.3. Ma trận chọn công cụ theo dòng phiên bản

| Dòng triển khai | Công cụ nên bắt đầu | Chú ý kiểm tra |
|---|---|---|
| **Apache Cassandra 3.x** | cqlsh tracing, `system_traces`, `nodetool`, JMX, application slow logging | Không mặc định áp dụng hướng dẫn FQL của các bản mới |
| **Apache Cassandra 4.x** | Các công cụ cơ bản, cùng FQL/audit nếu tính năng và cấu hình hiện diện | Tên lệnh, tùy chọn retention, quyền và cách xuất log cần xác nhận |
| **Apache Cassandra 5.x hoặc mới hơn** | Các công cụ cơ bản và khả năng logging/observability của đúng release | Không giả định metric hoặc virtual table có cấu trúc giống 4.x |
| **Bản do nhà cung cấp đóng gói / phân phối khác** | Tài liệu của phiên bản và vendor đang vận hành | Có thể thêm slow-query logger riêng; không suy ra là tính năng chuẩn Apache |

Mục đích bảng là **phân loại khả năng**, không phải danh mục tính năng đầy đủ theo từng patch release. Cách an toàn là xác định `nodetool version`, đọc `nodetool help` và đối chiếu cấu hình với quy trình đã phê duyệt.

**Không khẳng định sự tồn tại của một tham số cấu hình “slow query threshold” chung cho mọi Cassandra** chỉ vì sản phẩm dữ liệu khác có tham số tương tự.

## 6. Các lệnh nodetool phục vụ chẩn đoán truy vấn chậm

CQL tracing cung cấp chi tiết của một request; khi điều tra p99 hoặc nhiều request chậm, cần xem thêm các thống kê node/bảng.

~~~bash
# Xác nhận phiên bản node và danh sách lệnh có thật.
nodetool version
nodetool help

# Đọc/write latency và tình trạng SSTable theo table.
nodetool tablestats telemetry.events_by_device_day

# Histogram đọc/ghi, SSTables per read và các chỉ số khác tùy bản.
nodetool tablehistograms telemetry events_by_device_day

# Histogram request gần coordinator, tùy phiên bản.
nodetool proxyhistograms

# Stage / thread pool, pending và dropped messages.
nodetool tpstats

# Compaction đang chạy và backlog I/O.
nodetool compactionstats

# Streaming / network transfer trong lúc thay topology/repair.
nodetool netstats

# Node UP/DOWN theo datacenter/rack.
nodetool status
~~~

Nếu một cú pháp không được bản cài hỗ trợ, kiểm tra `nodetool help <command>` thay vì đoán. Các trường latency có thể sử dụng **đơn vị khác nhau** (microseconds, milliseconds, nanoseconds), và cách histogram tính cửa sổ/mẫu có thể khác với Prometheus hay client timer.

### 6.1. Nên nhìn theo thứ tự nào?

1. **Ứng dụng:** slow request rate, p95/p99, timeout/error và loại operation.
2. **Coordinator:** proxy/client request latency, pending/dropped, số replica cần ACK theo CL.
3. **Table tại node:** read/write latency, SSTables per read, tombstone, partition size, compaction backlog.
4. **Hạ tầng:** network, disk I/O latency, CPU, GC, disk free.
5. **Thao tác nền/topology:** streaming, repair, bootstrap, hinted handoff hoặc replica down.

Một chỉ số **table-local tốt** nhưng ứng dụng chậm không loại trừ Cassandra: coordinator, mạng hay một replica khác vẫn có thể là điểm nghẽn.

### 6.2. Tránh so trung bình các p99 giữa node

Nếu muốn ước lượng p99 của toàn cluster, không tính:

~~~text
p99_cluster = (p99_node_A + p99_node_B) / 2  # SAI
~~~

Percentile **không cộng hoặc lấy trung bình được**. Cần gộp dữ liệu phân phối/histogram cùng bucket, cùng thời gian và cùng loại request; sau đó mới tính quantile. Đặc biệt không gộp p99 của read với write hoặc p99 table-local với p99 client.

## 7. Khai thác dữ liệu chậm một cách có phương pháp

### 7.1. Phân loại query theo shape thay vì theo raw CQL

Ví dụ hai request:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 11111111-1111-1111-1111-111111111111
  AND event_day = '2026-11-21'
LIMIT 50;

SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = 22222222-2222-2222-2222-222222222222
  AND event_day = '2026-11-21'
LIMIT 50;
~~~

Hai câu có **cùng query shape**, khác giá trị bind. Nếu ứng dụng ghi một log event cho mỗi request, nên nhóm theo ID như `read_device_events_by_day`, không tạo hai giá trị label metrics mới cho hai UUID.

Sau đó so tỷ lệ chậm theo operation và truy tìm dữ liệu đặc biệt bằng trace có kiểm soát nếu hợp lệ.

### 7.2. Query shape ảnh hưởng read path

Một truy vấn có đủ partition key thường giúp Cassandra định tuyến tới một tập replica cụ thể. Nhưng nó vẫn có thể chậm khi:

- Partition có quá nhiều hàng hoặc clustering range quá rộng.
- Có nhiều tombstone từ DELETE/TTL, gây **tombstone scan**.
- Cùng partition trải trên nhiều SSTable do flush/compaction backlog.
- Hot partition được nhiều client truy cập cùng lúc.
- Disk/cache hoặc compaction/repair làm replica chậm.

Ngược lại, `ALLOW FILTERING` với điều kiện không có partition key có thể gây quét dữ liệu khó dự đoán:

~~~cql
-- Minh họa anti-pattern: không dùng làm truy vấn production mặc định.
SELECT device_id, event_time, value
FROM telemetry.events_by_device_day
WHERE value > 80
ALLOW FILTERING;
~~~

Không phải mọi slow query đều chữa bằng tăng cache, và tăng timeout thường chỉ kéo dài thời gian chờ thay vì sửa nguyên nhân.

### 7.3. LIMIT không loại được chi phí quét tombstone

Truy vấn `LIMIT 20` chỉ giới hạn **số row trả về**, không bảo đảm chỉ kiểm tra 20 entry trên đĩa. Một partition với hàng nghìn tombstone có thể yêu cầu đọc nhiều SSTable/row bị xóa trước khi tìm đủ kết quả.

Nếu một số truy vấn có p99 xấu, kết hợp log query ID với `tablehistograms`, dấu hiệu tombstone và tracing có chọn lọc. Cân nhắc mô hình TTL/retention, partition bucket và compaction strategy dựa trên workload.

## 8. Ví dụ Java Driver 4.x: ghi slow query event an toàn

### 8.1. Ví dụ CQL và mô hình dữ liệu

Giả sử ứng dụng đọc sự kiện thiết bị theo ngày:

~~~cql
-- Giả sử keyspace telemetry đã tồn tại.
CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Ví dụ truy vấn:

~~~cql
SELECT event_time, value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT 50;
~~~

Trong Java, chuẩn bị statement một lần và truyền partition key qua bind parameter; không nối trực tiếp giá trị vào CQL string. Ví dụ đo **đường đọc đồng bộ cho một page đầu tiên**, dùng SLF4J:

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDate;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class DeviceEventReader {
    private static final Logger LOG =
        LoggerFactory.getLogger(DeviceEventReader.class);
    private static final long SLOW_THRESHOLD_MS = 200L;

    private final CqlSession session;
    private final PreparedStatement readByDay;

    public DeviceEventReader(CqlSession session) {
        this.session = session;
        this.readByDay = session.prepare(
            "SELECT event_time, value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT 50"
        );
    }

    public Row readFirst(UUID deviceId, LocalDate day) {
        BoundStatement statement = readByDay.bind(deviceId, day)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(50);

        long startNs = System.nanoTime();
        String outcome = "success";

        try {
            return session.execute(statement).one();
        } catch (RuntimeException ex) {
            // Không ghi thông điệp exception có thể chứa dữ liệu nhạy cảm.
            outcome = ex.getClass().getSimpleName();
            throw ex;
        } finally {
            long durationMs = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - startNs
            );
            if (durationMs >= SLOW_THRESHOLD_MS
                    || !"success".equals(outcome)) {
                LOG.warn(
                    "cassandra_request queryId={} durationMs={} " +
                    "thresholdMs={} outcome={} cl={} pageSize={}",
                    "read_device_events_by_day",
                    durationMs,
                    SLOW_THRESHOLD_MS,
                    outcome,
                    "LOCAL_QUORUM",
                    50
                );
            }
        }
    }
}
~~~

Ví dụ này đo thời gian thực thi `execute` và lấy row đầu tiên; **không đo toàn bộ pagination hoặc thời gian HTTP**. Nó không ghi `deviceId` và `day` vì các giá trị bind có thể thuộc dữ liệu nhạy cảm hoặc làm tăng cardinality.

**Điểm cần triển khai thêm trong production:**

- Dùng metrics histogram cho **mọi request**, không chỉ request vượt ngưỡng; slow log là tín hiệu điều tra, histogram là số đo phân phối.
- Tách outcome thành tập giá trị hữu hạn như `success`, `timeout`, `unavailable`, `error`.
- Giới hạn tốc độ log và có sampling khi tỷ lệ request chậm cao, để **logging không tự làm p99 tệ hơn**.
- Đảm bảo logger có định dạng UTC, retention và kiểm soát truy cập phù hợp.
- Gắn request correlation ID **không chứa thông tin cá nhân**; phân biệt nó với server trace session ID.
- Nếu cần quan sát retry/attempt, sử dụng metrics/extension của driver theo phiên bản thực tế; không suy từ một lần `session.execute` rằng chỉ có một attempt.
- Với asynchronous/Reactive APIs, đo tới khi future/stream hoàn tất theo ngữ nghĩa nghiệp vụ, không đo mỗi thời gian phát lệnh.

### 8.2. Không chỉ log chậm, hãy ghi histogram

Nếu sử dụng Micrometer/OpenTelemetry hoặc một metrics backend khác, ưu tiên histogram duration theo **query ID ổn định**, CL, DC và outcome. Ví dụ những bucket cần thiết có thể tập trung quanh 50, 100, 200, 500, 1.000 và 2.000 ms tùy SLO.

Không tính `p99_cluster` bằng cách trung bình các p99 từ pod. Histogram phải được tổng hợp đúng phạm vi và cửa sổ. Đồng thời theo dõi **request count, timeout rate, retry rate**; khi request chậm timeout rồi biến khỏi histogram thành công, chỉ nhìn p99 thành công có thể gây hiểu sai.

## 9. Chẩn đoán một số nguyên nhân chậm thường gặp

| Dấu hiệu từ slow log + metrics | Giả thuyết chính | Bằng chứng cần tìm |
|---|---|---|
| SELECT cụ thể có p99 cao, tombstone scan tăng | TTL/DELETE để lại nhiều tombstone | Query range, warning logs, tracing, SSTables per read |
| Một partition bị chậm, bảng khác bình thường | Hot/wide partition hoặc skew token | Query pattern, partition size, load theo node |
| Read p99 tăng khi compaction backlog tăng | Read amplification và tranh disk I/O | `compactionstats`, table histograms, disk latency |
| Write p99 cao cùng commit log/disk latency | Replica không ACK kịp do storage | Coordinator/replica metrics, disk, GC |
| Client p99 cao nhưng table-local thấp | Driver queue/retry, coordinator hoặc WAN | Driver metrics, network RTT, proxyhistograms |
| LWT p99 cao riêng biệt | Paxos contention hoặc đường serial consistency | CQL `IF`, conflict rate, retries, replica health |
| Timeout/unavailable tăng khi DC lỗi | CL không được đáp ứng hoặc mạng partition | RF theo DC, `nodetool status`, write/read CL |
| Slow request tăng khi repair/streaming | Background I/O cạnh tranh | `netstats`, `compactionstats`, disk/network |
| FQL lớn, disk gần đầy | Ghi FQL/audit quá nhiều | Log path, quota, retention, I/O metrics |

Bảng chỉ nêu **giả thuyết ban đầu**, không phải quy tắc chẩn đoán tự động. Một triệu chứng có thể đến từ nhiều nguyên nhân và một nguyên nhân có thể làm ảnh hưởng nhiều metric.

### 9.1. Nhận biết retry và speculative execution

Một request có tổng latency 800 ms có thể gồm những attempt khác nhau. Nếu driver retry vì timeout hoặc speculative execution theo cấu hình, các attempt có thể tác động tới nhiều coordinator/replica.

Do đó khi chỉ xem trace một attempt, **không được giả định nó giải thích toàn bộ 800 ms phía client**. Cần đối chiếu request/attempt IDs khi có, số lần retry, lỗi, node đích và elapsed time.

Cũng cần hiểu consistency level: `LOCAL_QUORUM` đọc/ghi có thể bị một replica chậm tác động khác `ONE`; thay CL để giảm p99 có thể làm thay đổi bảo đảm dữ liệu và tính sẵn sàng, không chỉ là tối ưu hiệu năng.

## 10. Quy trình ứng phó: p99 đọc tăng nhưng truy vấn trung bình vẫn nhanh

Giả sử API `GET /devices/{id}/events` có:

~~~text
Trước sự cố:
  p50 = 12 ms, p95 = 45 ms, p99 = 90 ms
  timeout = 0,05%

Trong sự cố:
  p50 = 15 ms, p95 = 55 ms, p99 = 1.200 ms
  timeout = 1,5%
~~~

Bước 1 — **Chốt khoảng thời gian và lớp đo.** Kiểm tra metric đo từ Java/app hay server table-local, số request trong mỗi cửa sổ và thời điểm deploy, tránh so dữ liệu khác đơn vị/cửa sổ.

Bước 2 — **Phân nhóm theo query ID, keyspace/table, DC và CL.** Tìm operation nào chiếm tỷ lệ bad request lớn nhất. Nếu chỉ nhóm `read_device_events_by_day` chậm, tập trung vào query đó trước.

Bước 3 — **Đọc slow event có kiểm soát.** Lấy những request chậm đại diện, đối chiếu duration, outcome, page size, retry và timestamp. Không cần log toàn bộ payload hoặc tất cả bind values.

Bước 4 — **Đối chiếu node/bảng.** Sử dụng `tablestats`, `tablehistograms`, `proxyhistograms`, `tpstats`, `compactionstats` và disk/network metrics cùng khoảng thời gian.

Bước 5 — **Trace một số query tái hiện được.** Bật `TRACING ON` trong cqlsh khi cần, truy vấn đúng partition key/range, xem trace session và events; tắt tracing ngay sau phạm vi thử nghiệm. Nếu workload có PII, bảo vệ transcript/trace theo quy định.

Bước 6 — **Đánh giá thay đổi phù hợp.** Ví dụ: giới hạn clustering range, sửa mô hình bucket, điều chỉnh tốc độ backfill/repair, xử lý compaction backlog, cải thiện disk, hoặc thay ứng xử retry. Tránh tăng timeout hoặc đổi CL trước khi hiểu hậu quả.

Bước 7 — **Xác minh sau sửa.** So p50/p95/p99, timeout, throughput, số lượng slow event và disk/replica health trên cùng loại operation với đủ mẫu. Nếu p99 giảm nhưng timeout tăng, **không kết luận đã cải thiện**.

### Vì sao không bật FQL hoặc TRACE toàn cluster ngay khi sự cố xảy ra?

Khi hệ thống đã nghẽn disk/CPU, ghi thêm log trên mọi request có thể chiếm những tài nguyên đang thiếu. Nên ưu tiên **metrics vốn có**, application logging có sampling/giới hạn, và trace đúng một số truy vấn đại diện. Chỉ dùng FQL, audit hoặc debug log khi mục tiêu điều tra thật sự cần, đã ước tính overhead và có phương án tắt/thu hồi.

## 11. Bảo mật và chi phí của khả năng chẩn đoán

Slow query logging có thể vô tình lưu thông tin nhạy cảm:

- Giá trị `user_id`, `device_id` hoặc khóa phân vùng mang thông tin định danh.
- Query có literal nhạy cảm thay vì bind parameters.
- Batch statement chứa nhiều mutation.
- Kết quả query, exception message hoặc full trace lộ cấu trúc nội bộ.
- FQL hoặc audit giữ câu lệnh theo định dạng có thể tái hiện giao dịch.

Một chính sách tốt cần:

1. **Sanitize log:** dùng query ID cố định, không log raw bindings khi không cần.
2. **Giới hạn quyền đọc:** chỉ nhóm vận hành được xem log/trace theo chính sách.
3. **Có retention và quota:** tránh để lưu log vô hạn trên ổ dữ liệu Cassandra.
4. **Có sampling/rate limit:** đặc biệt khi lỗi lặp lại hàng nghìn lần/giây.
5. **Theo dõi overhead:** log volume, disk free, I/O và mức tăng p99 sau khi bật công cụ.
6. **Gắn tên phiên bản/cấu hình:** để người trực không chạy lệnh bị đổi tên hoặc không được hỗ trợ.

**Không dùng raw CQL chứa dữ liệu nhạy cảm làm nhãn Prometheus**. Cardinality sẽ tăng và dữ liệu nhạy cảm lan sang nhiều hệ thống quan sát. Đối với thông tin quá chi tiết, sử dụng trace được cấp quyền và có kiểm soát thay cho một metric label.

## 12. Checklist theo phiên bản và môi trường

Trước khi bật công cụ, người trực nên ghi lại:

~~~text
[ ] Cassandra edition/distribution và version của từng node
[ ] Keyspace, table, partition key và dạng truy vấn
[ ] Read/write consistency level, RF, datacenter liên quan
[ ] p50/p95/p99 và timeout/error rate theo operation
[ ] Tên/đơn vị metrics từ JMX/exporter hiện tại
[ ] Lệnh nodetool có thực sự nằm trong nodetool help?
[ ] Cqlsh tracing hoặc driver logging có được bật đúng scope?
[ ] Có cần FQL/audit không, hay chỉ cần metrics + một trace?
[ ] Giới hạn thời gian bật, mức sampling, đường dẫn, quota, retention
[ ] Có thể tắt tính năng và xác minh overhead trở về bình thường?
[ ] Có nguy cơ lộ dữ liệu ở bind values hoặc trace transcript không?
[ ] Đã xác minh lại sau khắc phục bằng cùng định nghĩa phép đo?
~~~

Không đọc “phiên bản 4.x” rồi mặc định mọi nút có cùng tập công cụ; bản vá, gói phân phối, exporter và cách triển khai có thể khác nhau. Khi thay cấu hình cluster, cần tuân theo quy trình thay đổi và rollback riêng.

## 13. Bài tập tự kiểm tra

### Câu 1 — Log chậm và tracing

Một API có p99 = 800 ms. Đội vận hành muốn biết **truy vấn nào** chậm rồi **bước nào** của một request bị kẹt. Nên dùng hai loại công cụ nào?

**Đáp án:** Application/driver slow request logging hoặc metrics theo query ID để xác định nhóm operation chậm; sau đó cqlsh tracing/trace được chọn để xem các bước trên coordinator/replica. Histogram dùng để đo phạm vi ảnh hưởng.

### Câu 2 — FQL có thay slow-query timer không?

Có người bật Full Query Logging và kết luận mọi CQL nằm trong FQL đều là slow query. Đúng hay sai?

**Đáp án:** Sai. FQL là chức năng ghi nhận luồng request phục vụ quan sát/replay theo cấu hình; không tự chỉ chọn truy vấn vượt ngưỡng latency hoặc đo end-to-end duration.

### Câu 3 — Chênh lệch p99

Java request có p99 700 ms, table-local có p99 20 ms. Có thể kết luận network p99 = 680 ms không?

**Đáp án:** Không. Percentile không thể trừ như vậy và hai metric không cùng phạm vi. Cần xem coordinator, network, retries, driver queue và node replica khác.

### Câu 4 — LIMIT và tombstone

Câu SELECT có `LIMIT 20` nhưng phải duyệt hàng nghìn tombstone mới lấy đủ row. Có thể xem LIMIT đã bảo đảm query rẻ không?

**Đáp án:** Không. LIMIT chỉ hạn chế kết quả trả về, không giới hạn trực tiếp số entry/tombstone phải đọc.

### Câu 5 — Tracing không thấy dữ liệu

Sau một ngày, người trực không tìm thấy session ID trong `system_traces.sessions`. Có chứng minh query chưa từng chạy không?

**Đáp án:** Không. Trace có thời hạn lưu; dữ liệu có thể đã hết TTL hoặc chưa được ghi theo cách mong đợi. Cần xem log/metrics tại thời điểm xảy ra sự cố.

### Câu 6 — Request timeout làm p99 “đẹp”

Sau sự cố, p99 của request thành công giảm từ 900 xuống 100 ms nhưng timeout tăng từ 0,1% lên 7%. Hệ thống đã tốt hơn chưa?

**Đáp án:** Chưa thể kết luận; nhiều request chậm có thể đã timeout và biến khỏi mẫu thành công. Phải đánh giá cả good-request ratio, error rate, QPS và SLO.

### Câu 7 — Phiên bản và lệnh chẩn đoán

Một hướng dẫn bảo dùng `nodetool enablefullquerylog`, nhưng node đang chạy không nhận lệnh. Có nên thử thay đổi cấu hình tùy ý để ép bật không?

**Đáp án:** Không. Cần kiểm tra `nodetool version`, `nodetool help`, distribution, tài liệu đúng phiên bản và quy trình vận hành. Có thể dùng application timer, tracing và histogram mà không cần FQL.

### Câu 8 — Java async logging

Một lập trình viên đo thời gian bao quanh duy nhất câu lệnh `session.executeAsync(statement)` và luôn thấy dưới 2 ms. Có phải Cassandra thật sự hoàn thành request trong 2 ms không?

**Đáp án:** Không. Đó có thể chỉ là thời gian tạo/kích hoạt tác vụ async. Phải đo cho tới khi future hoàn thành; phân biệt page đầu với toàn bộ kết quả.

## 14. Ghi nhớ

**Slow query logging là cách chọn ra những lần request vượt ngưỡng**, còn **tracing là cách phân tích các bước của một request**. Với Apache Cassandra:

- Không mặc định có một **slow query log chung cho mọi phiên bản**; ứng dụng/driver thường là nơi ổn định nhất để đo latency theo operation.
- `TRACING ON` trong cqlsh và `system_traces` cung cấp chi tiết có chọn lọc nhưng có overhead và retention riêng.
- Full Query Logging và audit logging phục vụ mục đích khác nhau, **không thay histogram p99 hoặc slow-query timer**.
- Công cụ `nodetool`, JMX và các metric cần được xác minh **theo phiên bản và distribution cụ thể**.
- Khi truy vấn chậm, đối chiếu **query shape, partition key, CL, tombstone/SSTable, compaction, replica, WAN, queue và retry**.
- Không dùng p99 trung bình giữa các node, không để timeout biến mất khỏi SLO, và không log dữ liệu nhạy cảm.
- Tối ưu cần được xác nhận bằng **cùng operation, cùng cửa sổ đo và đủ số mẫu** trước/sau thay đổi.

**Quy trình ngắn gọn:** đo phân bố độ trễ → nhận diện operation chậm → xem metrics node/bảng → trace có chọn lọc → kiểm chứng nguyên nhân → thay đổi nhỏ có đo lường → xác minh p99 **và** tỷ lệ lỗi. Đây là cách chẩn đoán phù hợp với hệ thống wide-column phân tán, nơi cùng một câu CQL có thể trải qua nhiều lớp trước khi ứng dụng Java nhận kết quả.
