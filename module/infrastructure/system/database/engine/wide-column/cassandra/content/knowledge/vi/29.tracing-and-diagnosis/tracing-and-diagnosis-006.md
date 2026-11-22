# Đọc chênh lệch digest, đọc bổ sung và xử lý read repair

## Mục tiêu và bối cảnh

Apache Cassandra cho phép dữ liệu của cùng một **partition key** được lưu trên nhiều **replica**. Nhờ replication factor và các mức **read/write consistency**, ứng dụng vẫn có thể tiếp tục đọc, ghi khi một số node bị chậm hoặc tạm ngừng. Đổi lại, trong những thời điểm nhất định, các replica có thể giữ các phiên bản dữ liệu khác nhau.

Khi đọc với mức nhất quán yêu cầu nhiều replica, **coordinator** có thể so sánh các **digest** (giá trị tóm tắt nội dung phản hồi) để kiểm tra các bản sao có nhất quán với truy vấn hay không. Nếu digest khác nhau, coordinator phải **đọc bổ sung dữ liệu đầy đủ**, thực hiện **reconciliation** theo timestamp/tombstone, và tùy phiên bản, cấu hình bảng có thể thực hiện **read repair**.

Bài học này thuộc chương **Tracing và chẩn đoán** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Nó liên hệ trực tiếp với mô hình wide-column, partition key, thiết kế bảng theo truy vấn, replication, consistency level, compaction, repair, xử lý lỗi và tích hợp từ ứng dụng Java.

Sau bài học, bạn có thể:

1. Phân biệt **data request**, **digest request** và **additional/full data request** trong một lần đọc.
2. Giải thích vì sao **digest mismatch** thường là dấu hiệu replica chưa hội tụ, **không mặc nhiên là lỗi ổ đĩa hoặc dữ liệu bị hỏng**.
3. Hiểu các bước **digest comparison → full data reads → reconciliation → read repair** và sự khác biệt giữa `read_repair = 'BLOCKING'` với `'NONE'` trong Cassandra 4.0+.
4. Dùng `cqlsh TRACING`, `system_traces`, logs và `nodetool` để nhận diện chi phí đọc bổ sung, đối chiếu latency.
5. Tạo lab RF=3 với replica tạm down, ghi ở quorum rồi dùng read tracing để tìm bằng chứng khác biệt.
6. Dùng Java Driver 4.x bật tracing theo từng truy vấn, thu trace ID và phân loại lỗi mà không coi read timeout là “dữ liệu mất”.

> **Giới hạn phiên bản:** các giải thích chung về digest và reconciliation áp dụng cho đường đọc Cassandra, nhưng chi tiết request, tracing event và tùy chọn `read_repair` thay đổi theo phiên bản. Ví dụ cấu hình `read_repair = 'BLOCKING'/'NONE'` ở bài này nhắm tới **Apache Cassandra 4.0 trở lên**. Hãy kiểm tra phiên bản đang chạy trước khi sao chép lệnh quản trị.

## 1. Ba lớp cần tách bạch khi đọc

Giả sử một keyspace có **RF=3** trong datacenter `datacenter1`. Partition `run_id='trace-demo-01'` nằm trên ba replica `R1`, `R2`, `R3`. Ứng dụng gửi:

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

Ba câu hỏi độc lập cần trả lời là:

| Lớp | Câu hỏi | Tránh nhầm với |
| --- | --- | --- |
| **Availability/CL** | Có đủ replica phản hồi để hoàn thành yêu cầu đọc không? | Dữ liệu tại mọi replica đã giống nhau |
| **Reconciliation** | Nếu các phản hồi không giống nhau, kết quả logic nào phải được trả? | Chỉ lấy hàng từ replica phản hồi nhanh nhất |
| **Read repair** | Có cần sửa replica đã cũ **trong đường đọc này** không? | Repair toàn bộ cluster hoặc chạy compaction |

`LOCAL_ONE` chỉ cần một phản hồi trong local DC, nên thông thường không cần so sánh digest giữa nhiều replica cho cùng lần đọc. `LOCAL_QUORUM` với RF=3 cần hai replica local đáp ứng; `ALL` cần ba replica đáp ứng. Khi đọc với nhiều replica, coordinator có cơ hội phát hiện khác biệt, nhưng **số replica được kiểm tra và đường đi chính xác phụ thuộc CL, chiến lược chọn replica, speculative retry và phiên bản**.

### Dữ liệu mẫu tại thời điểm các replica chưa hội tụ

~~~text
Partition key: run_id = trace-demo-01
Clustering key: order_id = 1

R1: status = PAID,    version = 2, mutation mới
R2: status = PAID,    version = 2, mutation mới
R3: status = PENDING, version = 1, mutation cũ
~~~

Trong ví dụ này, dữ liệu `PENDING` tại R3 **không có nghĩa R3 bị hỏng**: nó có thể đã ngừng hoạt động lúc phiên bản 2 được ghi. Đọc có quorum cùng DC từ R1 và R2 sẽ không nhất thiết thấy mismatch, vì **hai replica tham gia có dữ liệu giống nhau**. Nếu R3 nằm trong nhóm đọc, mismatch có thể xuất hiện.

## 2. Digest là gì và không phải là gì?

**Digest** là giá trị tóm tắt được Cassandra tính từ nội dung phản hồi cho **truy vấn đọc cụ thể**, để coordinator so sánh các replica mà không bắt tất cả chúng gửi toàn bộ dữ liệu trả về qua mạng ngay từ đầu.

Thông thường, coordinator chọn một replica để gửi **data request** (yêu cầu trả dữ liệu đầy đủ), và gửi **digest request** cho những replica khác cần tham gia đạt consistency level. Nó so sánh digest từ các phản hồi với nội dung dữ liệu nhận được.

| Khái niệm | Chức năng |
| --- | --- |
| **Data request / full data response** | Trả dữ liệu hàng/cột cần thiết cho coordinator hòa giải và trả cho client. |
| **Digest request / digest response** | Trả bản tóm tắt để so sánh nội dung truy vấn, giảm lượng dữ liệu truyền ban đầu. |
| **Digest match** | Các phản hồi được so sánh phù hợp với nhau trong **phạm vi truy vấn**. |
| **Digest mismatch** | Ít nhất hai phản hồi cho phạm vi được so sánh khác nhau; cần thêm dữ liệu để hòa giải. |
| **Read repair** | Cơ chế sửa các replica bị cũ trong đường đọc, theo chiến lược cấu hình. |

**Digest không phải checksum của cả node, cả SSTable hoặc cả bảng.** Nếu truy vấn chỉ đọc `order_id=1`, digest phù hợp không chứng minh mọi hàng khác của partition đã đồng bộ. Nó cũng không phải bằng chứng các byte lưu trữ vật lý trên mỗi replica hoàn toàn giống nhau: Cassandra có thể có các SSTable/memtable khác nhau nhưng cùng kết quả logic cho truy vấn.

Vì vậy **không dùng “digest match” để thay `nodetool repair`**. Anti-entropy repair đối chiếu những phạm vi dữ liệu lớn hơn trên các replica và có cơ chế riêng, thường dựa trên cấu trúc so sánh theo range.

## 3. Đường đọc khi digest khớp

Một đường đọc lý tưởng hóa ở `LOCAL_QUORUM` với RF=3 có thể như sau:

~~~mermaid
sequenceDiagram
    participant Client as Java / cqlsh
    participant C as Coordinator
    participant R1 as Replica R1
    participant R2 as Replica R2
    participant R3 as Replica R3
    Client->>C: SELECT (LOCAL_QUORUM)
    C->>R1: Data request
    C->>R2: Digest request
    R1-->>C: Full data
    R2-->>C: Digest
    Note over C: So sánh digest với dữ liệu
    C-->>Client: Kết quả đọc (đủ CL)
    Note over R3: Không nhất thiết tham gia lần đọc
~~~

Sơ đồ chỉ mô tả **nguyên tắc**. Coordinator có thể gửi yêu cầu đến nhiều replica hơn để đạt thời gian phản hồi mục tiêu, dùng đường đi khác khi có speculative retry, hoặc cần xử lý timeout. **Không được gắn cứng “R1 luôn nhận data, R2 luôn nhận digest”** trong code hoặc khi đọc tracing.

### Vì sao đường đọc này giảm chi phí?

Nếu trả hàng có kích thước lớn, truyền toàn bộ dữ liệu từ mọi replica ngay từ đầu tốn network và CPU. Digest cho phép so sánh trong trường hợp thường gặp là các replica đã có cùng nội dung. Khi digest **khớp**, coordinator có thể hoàn thành sau khi đáp ứng ngưỡng CL mà **không cần yêu cầu thêm dữ liệu đầy đủ chỉ để giải quyết bất đồng**.

Vẫn có chi phí đọc SSTable/memtable, giải mã, áp dụng TTL/tombstone và tổng hợp phản hồi. Một digest nhỏ trên mạng **không có nghĩa** thao tác ở replica miễn phí về disk I/O.

## 4. Đường đọc khi digest mismatch: đọc bổ sung và hòa giải

Khi so sánh thấy digest khác nhau, coordinator **không thể chỉ chọn một digest là đúng** vì digest không chứa thông tin đầy đủ để quyết định giá trị thắng. Nó cần thêm **full data responses** từ các replica liên quan để hòa giải dữ liệu.

~~~mermaid
sequenceDiagram
    participant Client as Client
    participant C as Coordinator
    participant R1 as R1 có dữ liệu mới
    participant R2 as R2 có dữ liệu mới
    participant R3 as R3 còn dữ liệu cũ
    Client->>C: SELECT (CL = ALL)
    C->>R1: Data request
    C->>R2: Digest request
    C->>R3: Digest request
    R1-->>C: PAID, version=2
    R2-->>C: Digest mới
    R3-->>C: Digest cũ
    Note over C: Phát hiện digest mismatch
    C->>R2: Full data request bổ sung
    C->>R3: Full data request bổ sung
    R2-->>C: PAID, version=2
    R3-->>C: PENDING, version=1
    Note over C: Reconciliation theo timestamp và tombstone
    opt BLOCKING read repair khi cần
        C->>R3: Mutation sửa dữ liệu cũ
        R3-->>C: ACK sửa theo điều kiện đợi
    end
    C-->>Client: PAID, version=2 hoặc lỗi nếu không đạt CL/timeout
~~~

**Bốn bước cần phân biệt:**

1. **Digest comparison:** phát hiện khác biệt **trong phản hồi truy vấn**; chưa đủ dữ liệu để biết chi tiết hàng/cột nào cũ.
2. **Additional/full data reads:** lấy nội dung từ các replica cần thiết để xử lý mismatch. Tùy trường hợp, coordinator có thể cần thêm round-trip, tăng thời gian chờ.
3. **Reconciliation:** áp dụng quy tắc Cassandra về timestamp, tombstone, TTL và phạm vi hàng/cột được yêu cầu để xác định **kết quả logic**.
4. **Read repair (nếu có):** gửi mutation sửa tới replica cũ; thời điểm chờ ACK phụ thuộc cấu hình. Client có thể phải đợi lâu hơn nếu read repair là **blocking**.

Không phải mọi mismatch đều có cùng số message, cùng thứ tự event hoặc cùng thời gian. Nếu một replica chậm, các full data request bổ sung hoặc repair không hoàn tất trước request timeout, client có thể nhận `ReadTimeout` **dù dữ liệu hợp lệ còn tồn tại**.

### Mismatch không có nghĩa dữ liệu bị sửa sai trong query

Kết quả có thể khác nhau do:

- Replica vừa phục hồi và **chưa nhận mutation** trong lúc down.
- Ghi đạt `ONE` hoặc `LOCAL_QUORUM` nhưng replica ngoài nhóm ACK vẫn còn trạng thái cũ.
- Có **tombstone/TTL** khiến dữ liệu logic ở các bản sao tạm thời khác nhau.
- Có ghi/xóa cạnh tranh và yêu cầu đọc xảy ra đúng thời gian dữ liệu đang lan truyền.
- Một số node đang chịu tải, gặp delay, streaming, hinted handoff hoặc repair chưa hoàn tất.

Việc ứng dụng nhìn thấy `digest mismatch` trong trace là **đầu mối điều tra sự khác biệt giữa replica**, không phải kết luận ngay rằng corrupt SSTable, mạng trả dữ liệu giả hoặc Cassandra đã làm mất dữ liệu. Nếu nghi corruption, cần bằng chứng độc lập từ logs/disk/verification.

## 5. Read repair trong Cassandra 4.0+: BLOCKING và NONE

Trong các phiên bản Cassandra hỗ trợ table option `read_repair`, một bảng có thể cấu hình:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'BLOCKING';
~~~

hoặc:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'NONE';
~~~

**Cassandra 4.0+ mặc định dùng `BLOCKING` cho các bảng thông thường** nếu không cấu hình khác. Trước khi áp dụng, kiểm tra phiên bản và metadata của chính bảng. Một số hướng dẫn cũ cho Cassandra 3.x bàn về `read_repair_chance` hoặc `dclocal_read_repair_chance`; **không copy các tùy chọn cũ đó sang Cassandra 4.x/5.x** như thể chúng tương đương với `read_repair`.

### Bảng so sánh

| Khía cạnh | `BLOCKING` | `NONE` |
| --- | --- | --- |
| Khi digest mismatch | Vẫn lấy dữ liệu đầy đủ cần thiết và hòa giải | **Vẫn lấy dữ liệu và hòa giải**; không bỏ qua mismatch |
| Sửa replica cũ trong đường đọc | Coordinator thực hiện các mutation repair và **chờ** đủ điều kiện sửa theo CL của read trước khi trả thành công | Không thực hiện read repair tương ứng trên đường đọc |
| Độ trễ | Có thể tăng vì thêm round-trip đọc và ghi sửa | Tránh thời gian chờ các write repair, nhưng **vẫn có chi phí đọc bổ sung/reconciliation** |
| Thuộc tính đáng lưu ý | Hỗ trợ **monotonic quorum reads** theo phạm vi bảo đảm của read repair | Ưu tiên **partition-level write atomicity** trong một số mẫu đọc/ghi |
| Việc còn phải làm | Không thay anti-entropy repair toàn phạm vi | Vẫn phải có anti-entropy repair; replica cũ không tự được chữa chỉ vì một SELECT |

**Điều cực kỳ quan trọng:** `read_repair='NONE'` **không có nghĩa coordinator trả dữ liệu từ một replica bất kể digest mismatch**, cũng không có nghĩa bỏ qua consistency level. Nó có nghĩa không dùng cơ chế read repair đó để ghi bù trong đường đọc; reconciliation vẫn nhằm trả dữ liệu đúng theo giao thức đọc/CL.

### Monotonic quorum reads và partition-level write atomicity

Vì sao Cassandra cho chọn hai hành vi?

Giả sử ứng dụng ghi nhiều hàng/cột thuộc **cùng partition** trong một thao tác ghi phân vùng:

~~~text
Partition: run_id = batch-demo
Hàng 1: order_id = 10 -> PAID
Hàng 2: order_id = 11 -> PAID

R1/R2 nhận toàn bộ mutation.
R3 bỏ lỡ toàn bộ mutation và giữ trạng thái cũ.
~~~

Sau đó, một truy vấn chỉ đọc `order_id=10` có thể phát hiện mismatch. Với read repair blocking, Cassandra có thể **sửa phần dữ liệu được truy vấn** trên R3 mà chưa sửa `order_id=11`. Điều này bảo đảm các lần đọc quorum sau khó quay lại trạng thái cũ đối với phần vừa đọc, nhưng **có thể làm yếu tính nguyên tử hiển thị ở cấp partition** nếu ứng dụng đọc những phần khác của cùng partition sau đó ở CL khác.

`NONE` tránh việc một SELECT phạm vi hẹp ghi sửa **một phần** partition theo cách đó; đổi lại nó không mang bảo đảm monotonic quorum reads do blocking read repair đem lại. Đây là lựa chọn đánh đổi thuộc tính, **không phải công tắc “bật nhất quán/tắt nhất quán”**.

**Đừng suy diễn:** blocking read repair không biến Cassandra thành database giao dịch serializable, không thay LWT/`IF version` khi chống lost update, và không cam kết mọi replica trên mọi DC lập tức đồng bộ. Việc chọn chính sách phải dựa trên truy vấn theo partition, mẫu batch và yêu cầu nghiệp vụ.

## 6. Quan sát digest mismatch bằng cqlsh TRACING

`TRACING` trong `cqlsh` cho phép xem các bước thực thi của một truy vấn Cassandra: coordinator liên lạc replica, đọc dữ liệu/digest và những hoạt động phát sinh khi xử lý mismatch. Thông điệp trong trace khác giữa phiên bản và loại truy vấn; **chỉ xem các tên event dưới đây là nhóm dấu hiệu, không phải chuỗi bắt buộc phải xuất hiện y hệt**.

### 6.1. Bật và tắt tracing theo từng phiên

~~~text
TRACING ON
~~~

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

~~~text
TRACING OFF
~~~

`TRACING ON`/`OFF` là **lệnh của cqlsh**, không phải CQL. Chúng áp dụng cho những câu lệnh trong phiên cqlsh theo hành vi client. Kết quả có thể cho một **Tracing session ID** và chuỗi hoạt động trên coordinator/replica.

### 6.2. Nhận diện các nhóm event

| Nhóm hoạt động trong trace | Ý nghĩa thường gặp | Việc cần kiểm tra |
| --- | --- | --- |
| Chuẩn bị/điều phối READ | Coordinator chọn replica và gửi yêu cầu | CL, endpoints được chọn, topology |
| **Data request** | Một replica được yêu cầu trả dữ liệu đầy đủ | Chi phí đọc SSTable/memtable, latency |
| **Digest request** | Replica khác trả tóm tắt cho truy vấn | Số phản hồi cần ở CL |
| **Digest mismatch** | Nội dung so sánh khác nhau giữa replica tham gia | Replica vừa down? ghi CL thấp? tombstone/TTL? |
| **Additional/full data request** | Coordinator cần dữ liệu thay vì chỉ digest để reconcile | Số round-trip, replica chậm hoặc timeout |
| Reconciliation | Dữ liệu/tombstone được hòa giải thành kết quả logic | Timestamp, TTL, ghi đồng thời |
| **Read repair** / mutation update | Có thể gửi ghi sửa tới replica cũ | `BLOCKING` hay `NONE`, ACK, độ trễ |
| Hoàn thành truy vấn hoặc lỗi | Có đủ phản hồi để trả cho client hay không | Tổng duration, timeout, CL |

Nếu **không có dòng mismatch** trong một trace, chưa thể kết luận không có replica cũ. Coordinator có thể không chọn replica cũ trong lần đọc đó, hints có thể đã khôi phục khác biệt, hoặc việc quan sát trace chưa đầy đủ.

### 6.3. Truy vấn system_traces khi cần

Cassandra lưu thông tin tracing trong keyspace hệ thống `system_traces`. Với UUID phiên tracing **đã được in ra trong cqlsh**, có thể truy vấn:

~~~sql
-- UUID bên dưới là ví dụ, phải thay bằng tracing session ID thật.
SELECT session_id, coordinator, started_at, duration, request
FROM system_traces.sessions
WHERE session_id = 11111111-1111-4111-8111-111111111111;

SELECT event_id, activity, source, source_elapsed, thread
FROM system_traces.events
WHERE session_id = 11111111-1111-4111-8111-111111111111;
~~~

Trong bảng events, `event_id` là timeuuid hỗ trợ sắp xếp sự kiện, `source` là node báo hoạt động, `source_elapsed` thường tính microsecond theo mốc truy vết ở nguồn liên quan. Khi phân tích nhiều node, **không tự cộng các giá trị `source_elapsed` của từng event để ra thời gian chờ**: có thể có hoạt động song song, khác điểm đo và độ trễ mạng. Dùng tổng duration của phiên kết hợp timeline để nhận diện nút nghẽn.

Các trace event có thể được lưu/đến trễ hoặc hết hạn theo cấu hình hệ thống. Truy vấn không thấy bản ghi `system_traces` không mặc nhiên chứng minh query không có vấn đề. Hạn chế lấy trace khối lượng lớn trên production: tracing có chi phí lưu event, network và latency.

## 7. Lab RF=3: tạo cơ hội cho digest mismatch

Thí nghiệm sau cần **ba node Cassandra cùng một DC**, ví dụ `cass-1`, `cass-2`, `cass-3` tại `datacenter1`, Cassandra 4.0+ nếu muốn dùng `read_repair` table option. Chỉ thao tác trên cluster **lab/staging được phép dừng node**.

### 7.1. Kiểm tra topology

~~~bash
nodetool status
~~~

Kỳ vọng ba node đều `UN` (*Up/Normal*) và keyspace có RF3 trong DC local. `cqlsh` kiểm tra DC/phiên bản trên node đang kết nối:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` chỉ trả thông tin node hiện tại; nếu cần đảm bảo mọi node cùng phiên bản hoặc tên DC chính xác, phải kiểm tra các node liên quan. Trong ví dụ, nếu tên DC khác `datacenter1`, sửa lệnh tạo keyspace tương ứng.

### 7.2. Tạo schema và ghi dữ liệu gốc

~~~sql
CREATE KEYSPACE IF NOT EXISTS tracing_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS tracing_lab.orders_by_run (
    run_id text,
    order_id int,
    status text,
    version int,
    updated_at timestamp,
    PRIMARY KEY ((run_id), order_id)
) WITH read_repair = 'BLOCKING';
~~~

`run_id` là **partition key**, `order_id` là **clustering key**. Không dùng `SELECT *` quét toàn bảng: mỗi truy vấn thử tập trung vào đúng partition và hàng đã biết. `version` là metadata bài học, **không tự chống cập nhật cạnh tranh** khi dùng `UPDATE` bình thường.

**Nếu bảng/keyspace đã tồn tại**, `IF NOT EXISTS` không đổi RF hay read repair option. Kiểm tra metadata trước khi diễn giải:

~~~sql
SELECT keyspace_name, replication
FROM system_schema.keyspaces
WHERE keyspace_name = 'tracing_lab';

SELECT table_name, read_repair
FROM system_schema.tables
WHERE keyspace_name = 'tracing_lab'
  AND table_name = 'orders_by_run';
~~~

Trong `cqlsh` đặt consistency của lệnh ghi:

~~~text
CONSISTENCY ALL
~~~

~~~sql
INSERT INTO tracing_lab.orders_by_run
    (run_id, order_id, status, version, updated_at)
VALUES (
    'trace-demo-01', 1, 'PENDING', 1,
    '2026-11-21T09:00:00Z'
);
~~~

Chỉ coi baseline hợp lệ nếu client thực sự **nhận thành công** ở `ALL` (cả ba replica ACK). Nếu timeout, tạo run ID mới hoặc xác minh lại trước khi tiếp tục.

### 7.3. Cho một replica bỏ lỡ UPDATE

Trong lab Docker giả sử node thứ ba là container `cass-3`:

~~~bash
# Chỉ chạy trên lab, không dừng một node production.
docker kill --signal=KILL cass-3
~~~

Kiểm tra hai node còn lại `UN` và node thứ ba `DN`:

~~~bash
nodetool status
~~~

Kết nối `cqlsh` vào node sống, đặt:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
UPDATE tracing_lab.orders_by_run
SET status = 'PAID',
    version = 2,
    updated_at = '2026-11-21T09:05:00Z'
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

Ở RF3 một DC, `LOCAL_QUORUM` cần **2/3 replica** xác nhận. Nếu hai node còn sống ACK, UPDATE có thể thành công dù `cass-3` còn giữ `PENDING`. Điều này tạo tình huống replica tạm thiếu dữ liệu mà Cassandra phải hòa giải khi nó tham gia đọc.

**Không đánh dấu UPDATE đã ACK nếu cqlsh trả timeout**; mutation có thể đã được áp dụng một phần dù client không nhận thành công.

### 7.4. Khởi động lại replica và bật tracing

~~~bash
docker start cass-3
nodetool status
~~~

Đợi ba node đều `UN`, sau đó đặt read consistency:

~~~text
CONSISTENCY ALL
TRACING ON
~~~

~~~sql
SELECT order_id, status, version
FROM tracing_lab.orders_by_run
WHERE run_id = 'trace-demo-01'
  AND order_id = 1;
~~~

~~~text
TRACING OFF
~~~

**Vì sao chọn `ALL` trong lab?** Khi đủ ba replica khỏe, `ALL` buộc truy vấn cần phản hồi của cả ba replica trong RF3; nhờ đó dễ có cơ hội so sánh bản cũ của `cass-3` nếu nó chưa bắt kịp. Với `LOCAL_QUORUM`, coordinator có thể chọn hai replica đều đã có `PAID` nên không thấy mismatch.

**Không bảo đảm trace sẽ xuất hiện mismatch:** hinted handoff hoặc một quá trình sửa chữa khác có thể đã cập nhật `cass-3` rất nhanh sau restart. Nếu trace chỉ có đường đọc thông thường và trả `PAID`, đó cũng là kết quả có ý nghĩa; **không sửa nội dung tệp SSTable, không hạ grace, không ép phá topology** chỉ để tạo cảnh báo.

### 7.5. Giải thích những khả năng quan sát

| Quan sát trong trace hoặc kết quả | Diễn giải thận trọng |
| --- | --- |
| `PAID`, không có mismatch | Các replica tham gia có thể đã hội tụ trước phép đọc hoặc khác biệt không còn quan sát được |
| `Digest mismatch` rồi full data reads | Có khác biệt trong các phản hồi đọc; coordinator phải lấy thêm dữ liệu để hòa giải |
| Có mutation/read repair event | Đường đọc có thể đang sửa replica cũ theo `BLOCKING`, cần xem ACK/latency |
| `PAID` được trả ở `ALL` | Truy vấn đọc hoàn tất tại CL `ALL` với kết quả logic đó; **không tự chứng minh toàn bộ cluster/table đã repair** |
| `ReadTimeout` hoặc `Unavailable` | Query không hoàn tất ở CL; không được coi là “đã mất hàng” |
| `PENDING` hoặc dữ liệu bất ngờ | Kiểm tra UPDATE ACK, timestamp, concurrent writers, schema, DC/RF và trạng thái node |

Sau phép đọc, quan sát logs/metrics hints/repair nếu cần. **Truy vấn kết quả đúng** là dữ liệu quan sát tại CL và thời điểm cụ thể; còn “mọi replica hoàn toàn đồng bộ” cần bằng chứng về phạm vi repair và trạng thái replica.

## 8. Thực hành so sánh BLOCKING và NONE

Để học sự khác nhau của cấu hình, chỉ thay đổi **bảng lab** và sử dụng **run ID mới**, vì read repair blocking ở vòng trước có thể đã sửa bất đồng:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'NONE';
~~~

Tiếp tục quy trình ghi baseline `ALL`, cho một replica down, ghi phiên bản mới ở `LOCAL_QUORUM`, đưa node trở lại và đọc ở `ALL` với run ID **`trace-demo-02`**. Trong giai đoạn này:

- Nếu có digest mismatch, coordinator **vẫn đọc dữ liệu bổ sung và reconcile** để trả kết quả logic theo CL, dù read repair đặt `NONE`.
- Không kỳ vọng `NONE` tự ghi sửa replica cũ trong quá trình truy vấn đó.
- Nếu không có mismatch, có thể hints đã sửa hoặc trạng thái replica đã hội tụ; đừng kết luận điều gì về `NONE` chỉ từ một lần đọc.
- Không so latency hai lần đọc nếu một lần có mismatch và lần kia không. Cần so trên workload và trạng thái replica tương đương, thu nhiều mẫu.

Đưa bảng lab về `BLOCKING` khi muốn kết thúc so sánh:

~~~sql
ALTER TABLE tracing_lab.orders_by_run
WITH read_repair = 'BLOCKING';
~~~

**Cẩn trọng:** thay đổi `read_repair` là thay đổi **schema toàn bảng**, không phải chỉ một tùy chọn cục bộ của cqlsh. Không tùy tiện bật/tắt trên bảng production trong lúc ứng dụng có thể cần một trong hai thuộc tính monotonic quorum reads hoặc partition-level write atomicity. Kiểm tra schema agreement khi các node đang nhận thay đổi DDL.

## 9. Đọc trace cùng metrics, không tách khỏi triệu chứng

Một digest mismatch có thể là tín hiệu thoáng qua bình thường. Đáng điều tra hơn khi có **tần suất tăng, p95/p99 tăng, timeout, read repair liên tục hoặc replica không hội tụ**.

### Checklist theo thứ tự

1. **Xác định truy vấn thật:** keyspace, bảng, partition key, clustering range, CL, coordinator, mốc thời gian, trace ID và request ID phía ứng dụng.
2. **Đọc trace:** có data/digest request nào, mismatch, full data read bổ sung, read repair, node nào trả lời chậm?
3. **Xác minh RF và topology:** `nodetool status`, DC/rack, node vừa phục hồi hay đang streaming?
4. **Kiểm tra write path:** client ghi ở CL nào, có timeout/UNKNOWN, hints pending hay node offline lúc ghi?
5. **Kiểm tra dữ liệu bị xóa:** tombstone, TTL, `gc_grace_seconds`, replica quá hạn repair, dấu hiệu zombie.
6. **Xem tài nguyên:** disk I/O, compaction backlog, CPU, network và read/write timeouts theo node.
7. **Xác định phạm vi:** một vài partition hay nhiều token ranges; kết quả sửa theo đường đọc có đủ hay cần anti-entropy repair?
8. **Ghi kết luận có giới hạn:** sự kiện đã quan sát, giả thuyết, chứng cứ ủng hộ và việc cần theo dõi tiếp.

Các lệnh quan sát cơ bản:

~~~bash
# Chạy trên node phù hợp; không ép compaction hoặc repair khi chưa phân tích.
nodetool status
nodetool tablestats tracing_lab.orders_by_run
nodetool compactionstats
nodetool netstats
~~~

| Dấu hiệu | Hướng điều tra đầu tiên | Không nên kết luận |
| --- | --- | --- |
| Mismatch thỉnh thoảng sau restart | Hints/repair đang bắt kịp, replica vừa hồi phục | “Ổ đĩa đã hỏng” |
| Mismatch kèm read latency tăng | Full data round-trip, blocking repair, replica chậm | “Đổi CL thành ONE là sửa dữ liệu” |
| Mismatch lặp lại với một node | Hints không giao, repair lỗi, node quá tải, đồng hồ/timestamp bất thường | “SELECT một lần sẽ repair cả bảng” |
| `ReadTimeout` khi repair chạy | I/O/network chậm, thiếu ACK trước timeout | “Hàng chắc chắn không tồn tại” |
| Đọc `ONE` khác đọc `QUORUM` | Replica khác trạng thái, chọn replica khác nhau | “QUORUM nhất thiết đã sửa mọi replica” |
| Tombstone nhiều/latency cao | TTL, DELETE, range scan và compaction | “Digest mismatch là nguyên nhân duy nhất” |
| Trace không có mismatch | Tập replica đọc giống nhau hoặc đã được repair | “Toàn bộ cluster không còn lệch” |

**Đừng giảm CL chỉ để che dấu mismatch.** Đọc `LOCAL_ONE` có thể nhanh hơn nhưng không cần so sánh nhiều replica và có thể trả dữ liệu cũ. Đây là quyết định đánh đổi về độ mới/sẵn sàng cần được chấp nhận ở tầng nghiệp vụ, không phải biện pháp chữa lỗi đồng bộ.

## 10. Phân biệt read repair và anti-entropy repair

| Tiêu chí | Read repair | Anti-entropy repair |
| --- | --- | --- |
| Kích hoạt | Phát hiện khác biệt trong đường đọc; phụ thuộc chính sách bảng/phiên bản | Quản trị vận hành, ví dụ `nodetool repair` |
| Phạm vi | Hàng/cột/partition slice tham gia query | Token ranges và các replica tham gia repair |
| Thời điểm | Có thể nằm trong latency truy vấn người dùng | Chạy theo phiên bảo trì, tốn I/O/network |
| Kết quả | Sửa dữ liệu cũ được phát hiện trong một lần đọc | Đồng bộ dữ liệu/tombstone theo phạm vi đã chạy |
| Giới hạn | Không phát hiện partition chưa truy vấn, không chữa mọi replica | Không phục hồi sự kiện đã mất trên **tất cả** replica/nguồn; không chữa tombstone đã mất mọi nơi |

Với bảng có `gc_grace_seconds`, lịch anti-entropy repair và thời gian node down phải được thiết kế để **tombstone còn cơ hội lan tới replica đã bỏ lỡ DELETE trước khi bị purge**. `read_repair='BLOCKING'` không thay lịch repair định kỳ, nhất là khi nhiều partition **không bao giờ được người dùng đọc**.

Thao tác compaction chỉ hợp nhất SSTable **cục bộ trên một node**, không tự gửi mutation tới replica khác. Hệ thống có thể có read latency cao do compaction/tombstone mà **không có digest mismatch**; cần xem các nguồn chi phí riêng.

## 11. Java Driver: bật tracing cho đúng truy vấn

Java Driver 4.x cho phép bật request tracing trên một statement. Ví dụ dưới chỉ đọc **một partition và một clustering key**, có CL rõ ràng và lưu **tracing ID** để đối chiếu với `system_traces`.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ExecutionInfo;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

public final class DigestTraceProbe {
    public enum State { FOUND, MISSING, READ_ERROR }
    public record Outcome(State state, String status,
                          Integer version, UUID tracingId,
                          long elapsedMillis) {}

    private final CqlSession session;
    private final PreparedStatement select;

    public DigestTraceProbe(CqlSession session) {
        this.session = session;
        this.select = session.prepare(
            "SELECT status, version FROM tracing_lab.orders_by_run " +
            "WHERE run_id = ? AND order_id = ?");
    }

    public Outcome readWithTracing(String runId, int orderId) {
        BoundStatement statement = select.bind(runId, orderId)
            .setConsistencyLevel(DefaultConsistencyLevel.ALL)
            .setTracing(true)
            .setIdempotence(true);

        long started = System.nanoTime();
        try {
            ResultSet result = session.execute(statement);
            ExecutionInfo info = result.getExecutionInfo();
            UUID tracingId = info.getTracingId();
            Row row = result.one();
            long millis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);

            if (row == null) {
                return new Outcome(
                    State.MISSING, null, null, tracingId, millis);
            }
            return new Outcome(
                State.FOUND, row.getString("status"),
                row.isNull("version") ? null : row.getInt("version"),
                tracingId, millis);
        } catch (RuntimeException error) {
            long millis = TimeUnit.NANOSECONDS.toMillis(
                System.nanoTime() - started);
            System.err.printf(
                "READ_ERROR run=%s order=%d type=%s timeMs=%d%n",
                runId, orderId, error.getClass().getSimpleName(), millis);
            return new Outcome(
                State.READ_ERROR, null, null, null, millis);
        }
    }
}
~~~

Trong ứng dụng thật, `CqlSession` và `PreparedStatement` nên được tái sử dụng. `setTracing(true)` chỉ nên bật cho request được lựa chọn để điều tra; **không bật toàn bộ traffic** vì trace sinh thêm tải. Driver có thể không trả tracing ID khi server không cung cấp hoặc request thất bại; trong trường hợp đó `null` là hợp lệ và cần giữ client request ID/logs để tra cứu.

### Đọc kết quả Java một cách đúng đắn

- `FOUND`: query ở `ALL` trả một hàng theo khóa được hỏi; không đồng nghĩa mọi partition khác đã hội tụ.
- `MISSING`: query **hoàn tất thành công** nhưng không có hàng; cần đối chiếu manifest, TTL, DELETE và trạng thái ghi trước khi kết luận mất dữ liệu.
- `READ_ERROR`: truy vấn không hoàn tất; **không cộng vào MISSING** hoặc tự suy ra digest mismatch.
- `elapsedMillis` là thời gian đo end-to-end ở client cho một lần gọi, có cả network/driver; muốn có p95/p99 cần thu **nhiều mẫu cùng điều kiện tải**.
- `tracingId` dùng để tìm event server; một trace đã bật **không tự bảo đảm** chứa mọi hoạt động nằm ngoài truy vấn đó, như repair định kỳ.
- `setIdempotence(true)` áp dụng cho câu `SELECT` đọc thuần trong ví dụ; nếu thay bằng CQL có side effect thì phải đánh giá lại retry.

**Tại sao ví dụ dùng CL `ALL`?** Trong lab ba node đã khỏe, nó tăng cơ hội quan sát khác biệt giữa replica. Trong production, phải chọn CL theo SLA, RF/DC và khả năng sẵn sàng; không dùng `ALL` mặc định cho mọi truy vấn chỉ vì muốn nhìn thấy nhiều replica.

## 12. Sự cố minh họa và phương pháp điều tra

### Ca 1 — Truy vấn chậm bất thường sau khi replica hồi phục

**Hiện tượng:** một số `SELECT` ở `LOCAL_QUORUM` đột nhiên tăng từ vài chục mili giây lên vài trăm mili giây sau khi node quay lại. Trace cho thấy digest mismatch và full data read bổ sung.

**Giả thuyết hợp lý:** replica từng down còn dữ liệu cũ; coordinator phải đọc nhiều dữ liệu và với `BLOCKING` có thể chờ ghi repair. Kiểm tra hints, quá trình hồi phục, trạng thái compaction, số request và read-repair metrics. **Không kết luận ngay** đây là lỗi partition key hoặc ổ đĩa bị hỏng.

### Ca 2 — Mismatch lặp lại, dù truy vấn vẫn đúng

**Hiện tượng:** mỗi lần kiểm tra một nhóm partition có khác biệt, nhưng kết quả `LOCAL_QUORUM` thường là giá trị mới.

**Hướng xử lý:** xác minh `read_repair` của bảng, số replica tham gia và việc client có đang đọc từ nhiều DC. Nếu `NONE`, một lần đọc đúng **không tự sửa replica**. Nếu `BLOCKING` mà còn mismatch, xem UPDATE/DELETE vẫn đang diễn ra, repair mutation có lỗi/timeout hoặc một số replica không được chọn trong lần đọc trước. Dùng anti-entropy repair có kế hoạch nếu có phạm vi lệch rộng.

### Ca 3 — Read timeout trong lúc digest mismatch

**Hiện tượng:** trace ngắt trước khi coordinator trả kết quả; một replica không kịp trả full data hoặc repair.

**Điều không được làm:** báo “đơn hàng không tồn tại” hoặc tự phát lại toàn bộ thao tác ghi nghiệp vụ vì lần đọc thất bại. **Read timeout là trạng thái chưa biết kết quả**, phải thu logs/trace, đánh giá CL, node health, retry đọc có giới hạn nếu phù hợp và điều tra tải.

### Ca 4 — Không có mismatch nhưng dữ liệu nghiệp vụ thiếu

**Hiện tượng:** một `event_id` từ nguồn nghiệp vụ không có trong Cassandra, nhưng mọi replica trả cùng kết quả trống nên digest vẫn khớp.

**Giải thích:** digest chỉ giúp so sánh các replica trên dữ liệu **đang có** trong phạm vi read; nếu sự kiện chưa từng được ghi thành công ở bất kỳ replica nào, read repair không thể tự tạo nó. Cần đối soát với event log/manifest/outbox và backfill có ID ổn định nếu đủ căn cứ.

## 13. Checklist diễn tập và câu hỏi tự kiểm tra

**Bài 1 — Dự đoán digest.** Với RF3, R1/R2 có `PAID`, R3 có `PENDING`. Đọc `LOCAL_QUORUM` dùng R1/R2 có bắt buộc mismatch không? Nếu đọc `ALL` khi cả ba node sống, điều gì khiến coordinator phải lấy thêm full data?

**Bài 2 — Phân tích trace.** Chạy `TRACING ON` cho một SELECT có partition key rõ ràng. Phân loại các event tìm thấy thành data request, digest request, full data read bổ sung, read repair và hoàn thành. Nếu không có dòng mismatch, nêu ít nhất ba giả thuyết khác với “cluster hoàn toàn đồng bộ”.

**Bài 3 — BLOCKING và NONE.** Dùng hai run ID riêng trong lab, thử `read_repair='BLOCKING'` và `'NONE'`. Vì sao `NONE` vẫn phải reconcile khi digest khác? Vì sao không thể so latency từ một trace có mismatch với một trace không có mismatch?

**Bài 4 — Partition-level write atomicity.** Một mutation trong cùng partition cập nhật hai clustering rows. Một truy vấn chỉ yêu cầu row thứ nhất gây read repair. Giải thích nguy cơ “sửa một phần partition” của blocking repair và lý do chọn `NONE` trong một số workload.

**Bài 5 — Lỗi đọc và dữ liệu thiếu.** Một SELECT ở `ALL` timeout, sau đó SELECT ở `LOCAL_ONE` trả `PAID`. Có đủ bằng chứng nói mọi replica đều có `PAID` không? Tại sao không được đổi read timeout thành kết quả `MISSING`?

**Bài 6 — Tombstone.** Một node bỏ lỡ `DELETE` và down lâu hơn `gc_grace_seconds`; tombstone đã bị purge ở những bản sao khác. Tại sao chỉ tăng CL hoặc thử đọc bổ sung không thể bảo đảm loại bỏ zombie? Cần cân nhắc bước sửa chữa/phục hồi nào?

**Bài 7 — Java tracing.** Từ `ExecutionInfo.getTracingId()`, truy vấn `system_traces.events` và so với thời gian client. Vì sao `source_elapsed` không nên cộng thẳng thành client latency? Khi nào cần tắt tracing?

**Bài 8 — Khác biệt với LWT.** Một ứng dụng gặp lost update khi hai worker cùng sửa `version`. Có nên bật `read_repair='BLOCKING'` để chống cập nhật đồng thời không? Giải thích vai trò riêng của `IF version = ?`, Paxos và serial consistency trong LWT.

## Ghi nhớ

**Digest mismatch là dấu hiệu các replica được so sánh trả nội dung khác nhau cho một truy vấn, không phải kết luận dữ liệu đã mất hoặc ổ đĩa hỏng.** Coordinator có thể phải gửi **full data request bổ sung**, hòa giải bằng timestamp/tombstone và, với cấu hình `BLOCKING`, chờ read repair trước khi hoàn thành. `NONE` vẫn reconcile nhưng không làm read repair tương ứng. Hãy dùng tracing, topology, consistency level, logs và metrics để xác định **phạm vi và chi phí**; dùng anti-entropy repair có kế hoạch cho bất đồng diện rộng và đối soát nguồn nghiệp vụ khi cần kiểm tra dữ liệu thật sự còn thiếu.
