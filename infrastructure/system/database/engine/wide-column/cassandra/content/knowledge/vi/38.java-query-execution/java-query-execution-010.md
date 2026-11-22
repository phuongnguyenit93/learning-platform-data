# BatchStatement và giới hạn theo loại/bản ghi/phân vùng

## Mục tiêu bài học

Trong Apache Cassandra, **batch** không có nghĩa “càng gom nhiều câu CQL thì hệ thống càng nhanh”. Một batch có thể hữu ích khi nghiệp vụ cần **nhóm các mutation liên quan** vào cùng partition, nhưng có thể rất đắt khi gom hàng trăm hoặc hàng nghìn bản ghi thuộc **nhiều partition**: coordinator phải phân phối tới nhiều replica, giữ thông tin batchlog nếu là logged batch, xử lý timeout và cạnh tranh tài nguyên.

Bài này thuộc chương **Truy vấn từ Java** của module `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`. Ta tìm hiểu `BatchStatement` của **Cassandra Java Driver 4.x**, cách chọn `LOGGED`, `UNLOGGED`, `COUNTER`, và giới hạn theo **loại mutation**, **số statement**, **kích thước byte** và **số partition**. Nội dung liên hệ partition key/wide-column, thiết kế bảng theo truy vấn, mức nhất quán, replication nhiều DC, CQL, compaction, repair, xử lý timeout và Java Driver.

Sau bài học, bạn có thể:

1. Giải thích Cassandra batch khác gì transaction ACID và khác gì công cụ bulk ingestion.
2. Chọn đúng **logged**, **unlogged** hoặc **counter batch** cho từng nhóm thao tác.
3. Nhận ra **batch một partition** và **batch nhiều partition** bằng primary key, kể cả trường hợp viết nhiều bảng.
4. Xây dựng `BatchStatement` từ `PreparedStatement`/`BoundStatement`, đặt consistency level và đánh giá idempotence theo nghiệp vụ.
5. Dựng hàng rào kiểm tra **số statement, số partition, bytes ước lượng, TTL, timestamp, loại dữ liệu và quyền ghi** trước khi gửi.
6. Phân loại **ACK**, **UNKNOWN_WRITE**, lỗi validation và dữ liệu đọc lại sai; không tự động retry counter hoặc batch có side effect.
7. Benchmark batch cùng với **ghi riêng có giới hạn concurrency** để quyết định giải pháp tốt hơn bằng p95/p99, throughput và lỗi.

> **Giới hạn phiên bản:** ví dụ Java dùng API `com.datastax.oss.driver.api.core...` của Java Driver 4.x và Java 17. Mức guardrail, tên tùy chọn, cú pháp CQL đặc thù và hành vi batch có thể thay đổi giữa Cassandra 3.x/4.x/5.x hoặc bản phân phối; luôn đối chiếu tài liệu đúng phiên bản khi triển khai production. Các lệnh ghi dữ liệu chỉ dùng trong **lab/staging**.

## 1. Một batch CQL thực sự làm gì?

Một request `BatchStatement` chứa **nhiều mutation CQL**. Driver gửi batch tới một **coordinator**; coordinator xác định token/replica cho các partition liên quan và thực hiện cơ chế ghi phù hợp loại batch. Các replica vẫn ghi qua commit log và memtable, sau đó flush/compaction theo đường ghi Cassandra thông thường.

~~~mermaid
flowchart LR
    A["Java / BatchStatement"] --> C["Coordinator"]
    C --> P{"Các mutation thuộc bao nhiêu partition?"}
    P -->|"Một partition"| R1["Replica set của P"]
    P -->|"Nhiều partition"| R2["Replica set của P1"]
    P -->|"Nhiều partition"| R3["Replica set của P2"]
    C -. "Logged cross-partition batch" .-> B["Batchlog, khi cần"]
    B -. "Replay sau lỗi" .-> R2
    B -.-> R3
~~~

### Ba loại batch quan trọng

| Loại | Mục đích thường gặp | Đặc điểm cần nhớ |
| --- | --- | --- |
| **`LOGGED`** | Gom mutation thông thường khi cần bảo đảm hoàn tất cả nhóm trong các tình huống lỗi theo cơ chế batchlog, nhất là nhiều partition | Có thể phát sinh **batchlog và chi phí điều phối**; không cung cấp isolation giao dịch toàn cluster |
| **`UNLOGGED`** | Gom các mutation thông thường khi không cần bảo đảm batchlog xuyên nhiều partition | **Không** cung cấp tính atomicity cross-partition; không tự nhanh hơn những ghi độc lập |
| **`COUNTER`** | Gom những phép tăng/giảm **cột counter** | Có ngữ nghĩa counter riêng; retry không an toàn nếu thiếu kiểm soát; không được trộn với mutation thường |

**Tên `LOGGED` không đồng nghĩa “mỗi mutation đều được ghi đúng một lần”**, còn `UNLOGGED` không đồng nghĩa “không ghi commit log”. `UNLOGGED` chỉ tránh **batchlog dành cho logged batch**; mỗi replica vẫn thực hiện cơ chế bền vững của đường ghi thông thường theo cấu hình Cassandra.

Một logged batch chứa mutation **cùng partition** thường có tối ưu đường ghi mà không cần batchlog cross-partition; chi tiết phụ thuộc phiên bản. Nhưng đừng lấy tối ưu này làm lý do gom vô hạn số hàng vào một partition nóng.

## 2. Atomicity, isolation và durability: đừng nhầm với transaction SQL

Nhiều hệ quản trị quan hệ triển khai transaction có những bảo đảm ACID mà lập trình viên quen thuộc. Cassandra batch có những bảo đảm **hẹp hơn và khác mục tiêu**.

### 2.1. Cùng một partition

Khi nhiều mutation tác động tới **cùng partition** và được áp dụng bằng batch, Cassandra có thể bảo đảm **atomicity/isolation ở mức partition** theo semantics batch của hệ thống: reader không nên thấy một phần các cập nhật cùng partition trong phép đọc tương ứng. Điều này hữu ích khi cần cập nhật các hàng/cột liên quan trong một partition.

Tuy nhiên:

- Batch **không thêm kiểm tra điều kiện nghiệp vụ** như “số dư không âm” hoặc “version phải bằng 7”. Cần LWT/thiết kế cạnh tranh riêng nếu cần compare-and-set.
- Atomicity theo partition không tự trở thành transaction nhiều bảng/nhiều partition, và không tạo serializable isolation trên toàn cluster.
- Với dữ liệu có nhiều TTL, timestamp hoặc conflict writers, cần hiểu cơ chế **last-write-wins** và tombstone; atomicity không thay chính sách timestamp.
- Một write thành công tại `LOCAL_QUORUM` vẫn chỉ có số ACK theo CL, không phải mọi replica/DC đều đã hội tụ.

### 2.2. Nhiều partition

Logged batch xuyên nhiều partition cung cấp cơ chế **durable batchlog/replay** để các mutation trong batch được áp dụng cuối cùng sau những trường hợp lỗi được hỗ trợ. Nhưng **không có isolation snapshot xuyên nhiều partition**:

~~~text
P1: mutation đã hiển thị tại thời điểm T1
P2: mutation chưa hiển thị tại thời điểm T1

Một reader đọc riêng P1 và P2 ở T1
có thể nhìn thấy trạng thái tạm thời không đồng bộ.
~~~

Vì thế, **không** dùng logged batch như transaction ngân hàng hai tài khoản nếu nghiệp vụ yêu cầu toàn bộ người đọc thấy trạng thái chuyển tiền nguyên tử và có điều kiện. Thay vào đó, thiết kế ledger/operation ID, state machine, LWT ở phạm vi phù hợp hoặc cơ chế điều phối giao dịch khác theo yêu cầu.

### 2.3. Timeout không trả lời được “đã ghi hay chưa”

Một `WriteTimeout` từ `session.execute(batch)` **không chứng minh** cả batch bị rollback. Một số mutation/replica có thể đã được ghi; batchlog có thể còn replay sau đó. Trạng thái an toàn để báo ứng dụng là **UNKNOWN_WRITE** cho đến khi có bằng chứng đủ tin cậy.

| Kết quả | Diễn giải | Hành động |
| --- | --- | --- |
| `execute` trả thành công | Coordinator xác nhận theo **CL và batch semantics** được yêu cầu | Ghi ACK cùng batch ID, CL, timestamp |
| `WriteTimeout` | Chưa đủ ACK trong deadline; hậu quả thực tế chưa chắc chắn | Lưu UNKNOWN, đọc đối soát theo PK/operation ID |
| `Unavailable` | Không đủ replica sẵn sàng để đáp ứng CL khi thực thi | Kiểm RF/DC/node; không giả định hoàn toàn chưa ghi nếu trạng thái không rõ |
| `InvalidQuery`/validation failure | CQL/type/loại batch không hợp lệ | Sửa input, không retry mù quáng |
| Readback thiếu một marker | Truy vấn đã hoàn tất nhưng không thấy marker ở CL đang đọc | Xem TTL, timestamp, replica/repair và manifest |

**Điểm cốt lõi:** batchlog dùng để hỗ trợ atomicity/durability của logged batch, **không phải** nhật ký giao dịch nghiệp vụ thay cho event log/outbox và không phải cơ chế rollback dễ dàng sau lỗi.

## 3. Nhận diện partition: yếu tố quan trọng nhất khi thiết kế batch

Trong Cassandra, partition key được dùng để tính token và xác định **replica set**. Dù Java gửi một `BatchStatement`, coordinator vẫn phải xử lý các partition liên quan.

Giả sử một bảng lưu sự kiện theo khách hàng/ngày:

~~~sql
PRIMARY KEY ((customer_id, event_day), event_ts, event_id)
~~~

- Hai hàng có **cùng `customer_id` và `event_day`** thuộc **một partition của bảng đó**, dù khác `event_ts` hoặc `event_id`.
- Hai hàng có **khác ngày** hoặc **khác customer** thuộc **hai partition khác nhau**.
- Nếu hai bảng có cùng chuỗi giá trị `customer_id` nhưng primary-key schema khác nhau, **không** tự suy luận chúng là một partition vật lý chung có cùng atomicity.
- Ngay cả khi các partition khác nhau có token/replica set chồng lấn, chúng vẫn là **các partition khác nhau**; điều kiện “cùng node” không thay thế điều kiện “cùng partition”.

### Cùng khóa ứng dụng nhưng khác bảng vẫn là tình huống khác

Ví dụ:

~~~text
orders_by_customer_day:
    partition = (customer_id, day)

order_details_by_id:
    partition = (customer_id, order_id)

Cùng customer_id, nhưng hai cách định vị partition khác nhau.
Một batch ghi hai bảng không tự có isolation/rollback ACID
cho hai đường đọc nghiệp vụ.
~~~

Nếu hệ thống denormalize vào nhiều bảng theo truy vấn, cần **idempotency, operation ID, event/outbox và đối soát** để xử lý trường hợp một bảng được quan sát thấy trước bảng khác.

### Batch nhiều partition tốn chi phí ở đâu?

| Thành phần | Batch một partition | Batch nhiều partition |
| --- | --- | --- |
| Replica sets | Một tập replica cho partition liên quan | Có thể nhiều tập replica khác nhau |
| Coordinator | Phân phối mutation tập trung | Fan-out tới nhiều endpoints, nhiều ACK |
| Logged batchlog | Thường có tối ưu cho cùng partition | Chi phí batchlog/replay thường đáng kể |
| Latency | Phụ thuộc kích thước partition/mutation và CL | Có thể chịu endpoint/replica chậm nhất và fan-out |
| Availability | Phụ thuộc các replica của partition và CL | Nhiều partition tăng phạm vi có thể gặp lỗi |
| Rủi ro workload | Hot partition, batch quá lớn | Batchlog bottleneck, network, GC, timeout |

**Không chọn batch chỉ để giảm số round-trip client** nếu đổi lại coordinator phải xử lý nhiều partition và batchlog lớn. Với bulk ingestion trên nhiều partition, nhiều **INSERT bất đồng bộ có backpressure** thường là đường cơ sở tốt hơn để benchmark.

## 4. Lab CQL: chuẩn bị bảng sự kiện và counter

### 4.1. Điều kiện lab

Giả sử cluster lab có **ba node** trong DC `datacenter1`, dùng `NetworkTopologyStrategy` với RF3. Nếu môi trường không như vậy, chỉnh RF và CL theo topology; đừng cố dùng `LOCAL_QUORUM` RF3 trong lab chỉ có một node.

~~~bash
nodetool status
~~~

Trong `cqlsh`:

~~~sql
SELECT release_version, data_center, host_id
FROM system.local;
~~~

`system.local` nói về node đang trả lời, không tự kiểm tất cả node. Các ví dụ nên chạy trên bảng mới của lab và dùng ID/range mới cho mỗi lượt để tránh dữ liệu cũ ảnh hưởng thí nghiệm.

### 4.2. Bảng thường theo partition customer/day

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_batch_lab
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'datacenter1': 3
}
AND durable_writes = true;

CREATE TABLE IF NOT EXISTS java_batch_lab.events_by_customer_day (
    customer_id uuid,
    event_day date,
    event_ts timestamp,
    event_id uuid,
    status text,
    amount_minor bigint,
    detail text,
    PRIMARY KEY ((customer_id, event_day), event_ts, event_id)
) WITH CLUSTERING ORDER BY (event_ts DESC, event_id DESC);
~~~

Tại bảng này:

- `(customer_id, event_day)` là **composite partition key**.
- `event_ts`, `event_id` là clustering keys, giúp truy vấn các sự kiện gần nhất của một khách hàng/ngày.
- `status`, `amount_minor` và `detail` là regular columns.
- Không có partition key thay đổi được bằng `UPDATE`; đổi khóa nghĩa là ghi row/partition mới và xử lý row cũ theo nghiệp vụ.

`IF NOT EXISTS` không làm mới schema/keyspace đã tồn tại. Kiểm replication trước khi dùng CL:

~~~sql
SELECT keyspace_name, replication, durable_writes
FROM system_schema.keyspaces
WHERE keyspace_name = 'java_batch_lab';
~~~

### 4.3. Bảng counter hoàn toàn tách biệt

~~~sql
CREATE TABLE IF NOT EXISTS java_batch_lab.counts_by_customer_day (
    customer_id uuid,
    event_day date,
    metric text,
    total counter,
    PRIMARY KEY ((customer_id, event_day), metric)
);
~~~

Counter có semantics riêng, không được trộn với cột regular non-primary-key thông thường trong cùng bảng theo mô hình counter Cassandra. **Đừng dùng counter làm số tiền hoặc số thứ tự nghiệp vụ cần exactly-once**; retry tăng counter sau timeout có thể làm tăng thêm.

## 5. LOGGED batch một partition: tình huống nên cân nhắc

Ví dụ nghiệp vụ ghi hai sự kiện **cùng customer/day** vào bảng lab và muốn các mutation trong partition được xử lý theo semantics batch.

Trong `cqlsh`, `BEGIN BATCH` là cú pháp **logged batch mặc định**; chỉ thêm `UNLOGGED` hoặc `COUNTER` khi cần loại tương ứng:

~~~text
CONSISTENCY LOCAL_QUORUM
~~~

~~~sql
BEGIN BATCH
  INSERT INTO java_batch_lab.events_by_customer_day
      (customer_id, event_day, event_ts, event_id,
       status, amount_minor, detail)
  VALUES (
      11111111-1111-4111-8111-111111111111,
      '2026-11-21', '2026-11-21T09:00:00Z',
      22222222-2222-4222-8222-222222222222,
      'CREATED', 20500, 'created')
  ;
  INSERT INTO java_batch_lab.events_by_customer_day
      (customer_id, event_day, event_ts, event_id,
       status, amount_minor, detail)
  VALUES (
      11111111-1111-4111-8111-111111111111,
      '2026-11-21', '2026-11-21T09:01:00Z',
      33333333-3333-4333-8333-333333333333,
      'PAID', 20500, 'paid')
  ;
APPLY BATCH;
~~~

Hai lệnh có cùng partition key `(customer_id, event_day)`. Chúng khác **clustering key** nên tạo hai hàng trong cùng partition.

Kiểm kết quả bằng partition key:

~~~sql
SELECT event_ts, event_id, status, amount_minor
FROM java_batch_lab.events_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
LIMIT 20;
~~~

**Batch không bảo đảm thứ tự thực thi tuần tự như một chương trình Java.** Hai lệnh INSERT ở đây ghi vào **hai primary key khác nhau**; mỗi hàng phải có định danh nghiệp vụ và timestamp phù hợp. Nếu hai mutation ghi **cùng cell/key** với timestamp bằng nhau hoặc cạnh tranh writer khác, thứ tự xuất hiện trong văn bản batch **không nên được dùng làm quy tắc quyết định giá trị cuối cùng**.

### Khi nào một mutation sẽ đơn giản hơn?

Nếu ứng dụng chỉ cần cập nhật **nhiều cột của cùng một hàng**, một `INSERT` hoặc `UPDATE` liệt kê các cột trong cùng mutation thường đủ. Không tạo batch gồm nhiều `UPDATE` trên **cùng row** nếu có thể dùng một câu CQL tương đương.

Ví dụ:

~~~sql
UPDATE java_batch_lab.events_by_customer_day
SET status = 'PAID',
    amount_minor = 20500,
    detail = 'confirmed'
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21'
  AND event_ts = '2026-11-21T09:00:00Z'
  AND event_id = 22222222-2222-4222-8222-222222222222;
~~~

Đây là một mutation trên cùng row, không cần batch chỉ để gộp ba phép gán.

## 6. UNLOGGED và logged nhiều partition: rủi ro thường bị hiểu sai

### 6.1. UNLOGGED cho các mutation cùng partition

~~~sql
BEGIN UNLOGGED BATCH
  UPDATE java_batch_lab.events_by_customer_day
  SET status = 'VERIFIED'
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND event_ts = '2026-11-21T09:00:00Z'
    AND event_id = 22222222-2222-4222-8222-222222222222;
  UPDATE java_batch_lab.events_by_customer_day
  SET status = 'VERIFIED'
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND event_ts = '2026-11-21T09:01:00Z'
    AND event_id = 33333333-3333-4333-8333-333333333333;
APPLY BATCH;
~~~

Trường hợp cùng partition có thể hưởng các bảo đảm cập nhật theo partition của Cassandra mà không cần batchlog cross-partition. Dù vậy, `UNLOGGED` **không** phải tín hiệu cho phép tạo batch cực lớn hay dựa vào atomicity giữa nhiều partition.

### 6.2. Anti-pattern: gom nhiều khách hàng/ngày để “bulk insert nhanh”

~~~text
Một luồng ETL gom 5.000 INSERT bất kỳ:
  P1 = customer A / 2026-11-21
  P2 = customer B / 2026-11-21
  P3 = customer C / 2026-11-20
  ...
  P5000 = customer khác / ngày khác

Sau đó gửi một BEGIN BATCH ... APPLY BATCH (logged mặc định).
~~~

Vấn đề:

- Coordinator phân phối tới nhiều replica/token ranges và có thể giữ batchlog lớn.
- Nếu một replica hoặc token range chậm, latency cả batch có thể tăng.
- Retry một batch lớn làm khuếch đại tải và khó xác định hậu quả của timeout.
- Một request CQL ít hơn **không chứng minh throughput tổng cao hơn**.
- Batching không làm thay đổi partition key hay biến 5.000 mutation thành một thao tác storage rẻ.

Gửi cùng nhóm 5.000 mutation theo kiểu `UNLOGGED` cũng **không tự giải quyết** bài toán: vẫn có fan-out và request lớn, còn mất cơ chế batchlog cross-partition. Thay vì vậy, ưu tiên **những ghi riêng/batch nhỏ theo partition**, có rate limit, giới hạn in-flight và metrics.

### 6.3. Logged cross-partition có lúc nào hợp lý?

Có, nhưng phải có yêu cầu rõ ràng về **eventual completion của một nhóm mutation liên quan** và chấp nhận **không có isolation giữa các partition**. Ví dụ một số workflow có thể muốn nhóm các bản sao denormalized có cùng operation ID để có cơ chế batchlog hỗ trợ khi coordinator lỗi. Tuy nhiên, để ứng dụng quan sát trạng thái nhất quán và khắc phục sai lệch sau sự cố, vẫn cần **outbox/operation state/reconciliation**.

**Không dùng logged batch như phương án thay thế đầy đủ cho transaction quan hệ**, đặc biệt khi có tranh chấp ghi, điều kiện nghiệp vụ nhiều khóa hoặc hệ thống khác ngoài Cassandra.

## 7. COUNTER BATCH là một loại riêng

Counter trong Cassandra dùng phép **tăng/giảm**, không phải kiểu số bình thường cho thao tác overwrite. Chúng có semantics retry và consistency riêng, nên Cassandra phân biệt **COUNTER batch** với các mutation thông thường.

~~~sql
BEGIN COUNTER BATCH
  UPDATE java_batch_lab.counts_by_customer_day
  SET total = total + 1
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND metric = 'created';
  UPDATE java_batch_lab.counts_by_customer_day
  SET total = total + 1
  WHERE customer_id = 11111111-1111-4111-8111-111111111111
    AND event_day = '2026-11-21'
    AND metric = 'paid';
APPLY BATCH;
~~~

Lưu ý:

- Counter mutation **không được trộn với INSERT/UPDATE regular** vào cùng batch.
- Counter dùng `UPDATE ... SET counter_col = counter_col + delta`; không dùng `INSERT` gán giá trị counter tuyệt đối.
- Nếu request báo timeout, tăng counter có thể đã được thực hiện. **Retry có thể tăng gấp đôi** nếu cùng phép tăng được gửi lại.
- Không đánh dấu counter batch `idempotent=true` chỉ để bật retry/speculative execution.
- Muốn đếm sự kiện với độ chính xác nghiệp vụ/khả năng replay, nên cân nhắc **event IDs + bảng fact/ledger + tổng hợp**; counter phù hợp khi semantics và mức sai lệch có thể chấp nhận đã được xác định.

Đọc kết quả:

~~~sql
SELECT metric, total
FROM java_batch_lab.counts_by_customer_day
WHERE customer_id = 11111111-1111-4111-8111-111111111111
  AND event_day = '2026-11-21';
~~~

Nếu chạy lại cùng đoạn `COUNTER BATCH`, giá trị có thể tăng thêm; đây là hành vi cộng chứ không phải lỗi driver. Dùng khóa lab mới cho mỗi thử nghiệm có kỳ vọng giá trị cố định.

## 8. Java Driver 4.x: xây BatchStatement từ BoundStatement

### 8.1. Tạo CqlSession một lần

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import java.net.InetSocketAddress;

public final class CassandraLabSession {
    public static CqlSession open() {
        return CqlSession.builder()
            .addContactPoint(new InetSocketAddress("10.10.0.11", 9042))
            .addContactPoint(new InetSocketAddress("10.10.0.12", 9042))
            .withLocalDatacenter("datacenter1")
            .build();
    }
}
~~~

Các IP chỉ là **ví dụ lab**. Production cần TLS, authentication/authorization, secret management, timeout, load balancing đúng local DC, backpressure và metrics. **Tái sử dụng `CqlSession`**; tạo session trên mỗi batch làm tăng handshake, connection churn và làm sai benchmark.

### 8.2. Chuẩn bị query shape trước

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

PreparedStatement insertEvent = session.prepare(
    "INSERT INTO java_batch_lab.events_by_customer_day (" +
    "customer_id, event_day, event_ts, event_id, " +
    "status, amount_minor, detail) " +
    "VALUES (?, ?, ?, ?, ?, ?, ?)");
~~~

`PreparedStatement` được chuẩn bị **một lần cho query shape** rồi dùng nhiều lần với `BoundStatement`. Không ghép CQL từ dữ liệu người dùng, không chuẩn bị lại cùng câu cho mỗi hàng.

### 8.3. Ví dụ LOGGED batch đúng một partition

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.time.Instant;
import java.time.LocalDate;
import java.util.UUID;

public final class TwoEventsBatch {
    private final CqlSession session;
    private final PreparedStatement insert;

    public TwoEventsBatch(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO java_batch_lab.events_by_customer_day " +
            "(customer_id, event_day, event_ts, event_id, " +
            "status, amount_minor, detail) VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void writeTwo(UUID customerId, LocalDate day) {
        BoundStatement created = insert.bind(
            customerId, day, Instant.parse("2026-11-21T09:00:00Z"),
            UUID.fromString("44444444-4444-4444-8444-444444444444"),
            "CREATED", 20500L, "created");

        BoundStatement paid = insert.bind(
            customerId, day, Instant.parse("2026-11-21T09:01:00Z"),
            UUID.fromString("55555555-5555-4555-8555-555555555555"),
            "PAID", 20500L, "paid");

        BatchStatement batch = BatchStatement.builder(DefaultBatchType.LOGGED)
            .addStatement(created)
            .addStatement(paid)
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            // Chưa chứng minh idempotency timestamp/TTL/retry:
            .setIdempotence(false)
            .build();

        session.execute(batch);
        // Không ném lỗi nghĩa là coordinator đã xác nhận theo CL.
    }
}
~~~

**Điểm cần đọc kỹ:**

- Hai `BoundStatement` nhận **cùng `customerId` và `day`** nên cùng partition của **cùng bảng**.
- `BatchStatement.builder(DefaultBatchType.LOGGED)` tạo batch loại logged; `UNLOGGED` hoặc `COUNTER` là lựa chọn khác, không được đổi chỉ để thử nhanh mà không hiểu yêu cầu.
- `LOCAL_QUORUM` với RF3 trong một DC chờ quorum local; không xác nhận mọi replica trong DC remote.
- `session.execute(batch)` là đồng bộ và có thể chặn thread cho tới khi có kết quả hoặc timeout.
- Lệnh trả thành công **không phải hàng dữ liệu SELECT**; với batch thường, `ResultSet` không chứa số hàng đã cập nhật để đếm.
- Hai `UUID` cố định ở đây chỉ dùng cho lab. Trong ứng dụng, ID nên xuất phát từ **operation ID/event ID ổn định**, không tạo ID mới khi retry một sự kiện.
- Mã chọn `setIdempotence(false)` một cách thận trọng. Nếu hệ thống có hợp đồng writer ownership, timestamp/TTL và tính lặp lại đã được chứng minh, mới cân nhắc bật true theo chính sách driver.

### 8.4. Biến đổi loại batch trong Java

~~~java
BatchStatement unlogged = BatchStatement.builder(
        DefaultBatchType.UNLOGGED)
    .addStatement(created)
    .addStatement(paid)
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotence(false)
    .build();
~~~

Đây là cấu trúc mã minh họa, không phải lời khuyên chuyển tất cả logged batch sang unlogged. Một counter batch phải chứa **chỉ counter statements**, ví dụ:

~~~java
PreparedStatement increment = session.prepare(
    "UPDATE java_batch_lab.counts_by_customer_day " +
    "SET total = total + 1 " +
    "WHERE customer_id = ? AND event_day = ? AND metric = ?");

BatchStatement counters = BatchStatement.builder(DefaultBatchType.COUNTER)
    .addStatement(increment.bind(customerId, day, "created"))
    .addStatement(increment.bind(customerId, day, "paid"))
    .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotence(false)
    .build();

session.execute(counters);
~~~

Không thêm `insert.bind(...)` của bảng thường vào `counters`. Khi counter batch trả timeout, không retry tự động như thể phép cộng chưa xảy ra.

## 9. Giới hạn theo số statement, byte và partition trong Java

### 9.1. Vì sao cần giới hạn ở ứng dụng?

Cassandra có thể cảnh báo hoặc từ chối batch quá lớn bằng các ngưỡng như `batch_size_warn_threshold_in_kb` và `batch_size_fail_threshold_in_kb` (tên/mức cụ thể tùy version/config), và có cảnh báo cho unlogged batch trải nhiều partition. Nhưng **không nên chờ server phát cảnh báo mới giới hạn dữ liệu từ client**.

Ví dụ một API nhận:

~~~text
POST /customers/{customerId}/events/batch
[
  { "event_id": "...", "day": "2026-11-21", "detail": "..." },
  ...
]
~~~

Nếu client có thể gửi 50.000 row, một batch có thể gây pressure bộ nhớ, network, disk, coordinator, replica và thậm chí tạo timeout cho workload khác. Hàng rào ở API/Java nên có **ba trần độc lập**:

1. **Số mutation/statement tối đa**, ví dụ **25** trong lab.
2. **Tổng byte ước lượng**, ví dụ **64 KiB** trong lab (đây không phải cấu hình mặc định hoặc khuyến nghị chung).
3. **Số partition khác nhau**, ví dụ **đúng một partition** cho API logged-batch này.

Ngoài ra: không cho mixed counter/regular, giới hạn độ dài field, không nhận null primary key, không cho CQL tùy ý từ người dùng, và giữ CL/idempotency policy cố định theo nghiệp vụ.

### 9.2. Chỉ cho phép một partition, rồi mới tạo BatchStatement

Mã sau là **mẫu guardrail phía ứng dụng**, giả định input đã qua authentication/authorization và sử dụng cùng bảng `events_by_customer_day`. Nó giới hạn **25 statement** và **64 KiB ước lượng**, không giả vờ biết chính xác kích thước binary CQL.

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BatchStatement;
import com.datastax.oss.driver.api.core.cql.BatchStatementBuilder;
import com.datastax.oss.driver.api.core.cql.DefaultBatchType;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class BoundedBatchWriter {
    private static final int MAX_MUTATIONS = 25;
    private static final int MAX_ESTIMATED_BYTES = 64 * 1024;
    private static final int MAX_DETAIL_BYTES = 8 * 1024;

    public record InputEvent(
        UUID customerId,
        LocalDate eventDay,
        Instant eventTs,
        UUID eventId,
        String status,
        long amountMinor,
        String detail) {}

    private final CqlSession session;
    private final PreparedStatement insert;

    public BoundedBatchWriter(CqlSession session) {
        this.session = session;
        this.insert = session.prepare(
            "INSERT INTO java_batch_lab.events_by_customer_day " +
            "(customer_id, event_day, event_ts, event_id, " +
            "status, amount_minor, detail) " +
            "VALUES (?, ?, ?, ?, ?, ?, ?)");
    }

    public void writeOnePartition(List<InputEvent> input) {
        if (input == null || input.isEmpty()
                || input.size() > MAX_MUTATIONS) {
            throw new IllegalArgumentException(
                "Batch cần 1.." + MAX_MUTATIONS + " mutation");
        }

        InputEvent first = Objects.requireNonNull(input.get(0));
        UUID partitionCustomer = Objects.requireNonNull(first.customerId());
        LocalDate partitionDay = Objects.requireNonNull(first.eventDay());
        long estimatedBytes = 0;

        BatchStatementBuilder builder =
            BatchStatement.builder(DefaultBatchType.LOGGED);

        for (InputEvent event : input) {
            Objects.requireNonNull(event);
            if (!partitionCustomer.equals(event.customerId())
                    || !partitionDay.equals(event.eventDay())) {
                throw new IllegalArgumentException(
                    "Batch API này chỉ nhận một partition");
            }
            Objects.requireNonNull(event.eventTs());
            Objects.requireNonNull(event.eventId());
            Objects.requireNonNull(event.status());
            Objects.requireNonNull(event.detail());

            int detailBytes = event.detail()
                .getBytes(StandardCharsets.UTF_8).length;
            if (detailBytes > MAX_DETAIL_BYTES) {
                throw new IllegalArgumentException("detail quá lớn");
            }

            int statusBytes = event.status()
                .getBytes(StandardCharsets.UTF_8).length;
            // Ngân sách PHỎNG ĐOÁN: overhead/keys/strings.
            // Không phải số bytes serializer driver tạo ra.
            estimatedBytes += 128L + detailBytes + statusBytes;
            if (estimatedBytes > MAX_ESTIMATED_BYTES) {
                throw new IllegalArgumentException(
                    "Vượt ngân sách kích thước batch");
            }

            builder.addStatement(insert.bind(
                event.customerId(), event.eventDay(),
                event.eventTs(), event.eventId(), event.status(),
                event.amountMinor(), event.detail()));
        }

        BatchStatement batch = builder
            .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotence(false)
            .build();
        session.execute(batch);
    }
}
~~~

**Điều đoạn mã kiểm được:** số statement, same-table/same-partition theo hai trường khóa, một phần kích thước và kiểu dữ liệu. **Điều nó chưa thay thế:** kiểm schema/query ownership, số cell thực tế, độ dài binary protocol metadata, timestamp/TTL, sự tương thích RF/CL, timeout, log/audit và chính sách retry.

Vì vậy, **64 KiB là một ngân sách ứng dụng minh họa**; server có thể báo ngưỡng batch size thấp hơn theo configuration của cluster. Hãy benchmark và đặt giới hạn **nghiêm ngặt hơn** khi schema/row lớn. Trong production, cần kiểm thêm trạng thái batch được kiểm soát, duplicate event ID và xác thực customer thuộc tenant được phép.

### 9.3. Nếu cần hỗ trợ nhiều partition thì sao?

Một phương án là **group theo partition key**, rồi gửi mỗi nhóm như một tác vụ nhỏ:

~~~text
input events
    -> validate + deduplicate source event_id
    -> group by (customer_id, event_day)
    -> giới hạn statements và bytes trên mỗi nhóm
    -> execute với concurrency/rate limit
    -> lưu outcome theo từng nhóm
    -> đối soát UNKNOWN_WRITE theo từng primary key
~~~

Nhưng **group rồi gửi hàng nghìn batch đồng thời** vẫn có thể làm nghẽn cluster. Giới hạn **in-flight requests, QPS per partition và tổng memory buffered**. Với nhóm chỉ một mutation, có thể gửi một `BoundStatement` riêng; không cần tạo batch một phần tử chỉ để thống nhất API.

Một nhóm vượt giới hạn có thể được **chia nhỏ thành nhiều batch** nếu nghiệp vụ không yêu cầu atomicity toàn nhóm. Nếu yêu cầu atomicity của hơn 25 mutation trong một partition, **không tự động chia nhỏ rồi tuyên bố còn giữ nguyên bảo đảm**; phải thiết kế lại phạm vi công việc hoặc thương lượng giới hạn.

## 10. Idempotency, timestamp, TTL và tranh chấp ghi

### 10.1. Idempotent không chỉ là “dùng cùng câu INSERT”

Một mutation có **cùng primary key và cùng giá trị** có thể là idempotent trong một số điều kiện. Nhưng xét thêm:

- **Client tạo UUID mới khi retry** → mỗi lần là **row khác**, không idempotent.
- **TTL thay đổi theo thời điểm gửi** → thời điểm hết hạn có thể bị đẩy về sau.
- **Timestamp write khác nhau** → retry có thể thắng ghi cạnh tranh và ghi đè dữ liệu mới.
- **Counter +1** → lặp lại tăng tiếp, không idempotent.
- **LWT hoặc side effect bên ngoài Cassandra** → cần hợp đồng retry riêng; `[applied]` và trạng thái giữa hai lần có thể khác.
- **Batch nhiều bảng** → dù một số mutation lặp lại an toàn, một mutation không idempotent làm **toàn batch không idempotent** theo nhu cầu retry.

**Không dùng `setIdempotence(true)` để ép driver thử lại** mà chưa chứng minh toàn bộ mutation an toàn khi phát lại. Ngay cả khi idempotent, cần **retry budget**, exponential backoff/jitter, timeout policy và theo dõi amplification; retry storm có thể đẩy cluster đang chậm vào trạng thái lỗi nặng hơn.

### 10.2. Timestamps và thứ tự mutation

Cassandra dùng write timestamps để reconcile; thứ tự các statement xuất hiện trong batch **không phải hàng rào serializable** giữa writer khác nhau. Khi cần expected state, dùng operation/version record, cột trạng thái, LWT phù hợp hoặc một state machine tại ứng dụng.

Một thiết kế import có thể dùng timestamp ghi do ứng dụng đặt rõ ràng, nhưng **đơn vị CQL `USING TIMESTAMP` là microsecond**; không nhầm với CQL `timestamp` lưu millisecond epoch. Timestamp giả/mốc event quá cũ có thể thua tombstone mới hơn. Không tự gắn timestamp cũ để “đảm bảo batch có thứ tự”.

### 10.3. TTL trong batch

TTL có thể được đặt trên các mutation CQL theo cú pháp được phiên bản hỗ trợ; các row/cell có thể hết hạn ở thời điểm khác nhau. Batch **không biến một nhóm có nhiều TTL thành một đơn vị hết hạn nguyên tử vĩnh viễn**. Khi kiểm thử, ghi TTL/time of write để tránh nhầm dữ liệu hết hạn hợp lệ thành mất dữ liệu do batch.

## 11. Batch điều kiện và LWT: giới hạn riêng

Cassandra có hỗ trợ **conditional mutations** qua các biểu thức `IF` (LWT/Paxos). Một số hình thức conditional batch được hỗ trợ nhưng đi kèm **ràng buộc về partition và loại câu lệnh** theo phiên bản; không thể chuyển tùy ý một batch nhiều partition thành transaction CAS toàn cluster.

Ví dụ LWT đơn lẻ trước khi học conditional batch:

~~~sql
INSERT INTO java_batch_lab.events_by_customer_day
    (customer_id, event_day, event_ts, event_id,
     status, amount_minor, detail)
VALUES (
    11111111-1111-4111-8111-111111111111,
    '2026-11-21', '2026-11-21T09:10:00Z',
    66666666-6666-4666-8666-666666666666,
    'CREATED', 20500, 'created-once')
IF NOT EXISTS;
~~~

Kết quả LWT thường có cột `[applied]` để biết điều kiện có áp dụng hay không. Nếu chạy lại với cùng PK, `[applied]=false` có thể là **hành vi đúng**, không phải lỗi Cassandra.

### Vì sao không tạo batch LWT bừa?

- Điều kiện chỉ có nghĩa trong phạm vi mà Cassandra hỗ trợ Paxos/conditional batch; nhiều partition có ràng buộc khác và thường không hợp lệ/không có bảo đảm như mong muốn.
- LWT phát sinh nhiều lượt trao đổi Paxos, latency cao hơn write thường.
- Không phối hợp counter với LWT/batch thường trong cùng batch.
- Retry LWT sau timeout cần phân biệt **outcome không xác định** và bảo vệ operation ID; không suy từ timeout rằng điều kiện chưa từng được áp dụng.

Nếu nghiệp vụ yêu cầu chuyển trạng thái **`CREATED → PAID` chỉ khi version khớp**, cân nhắc LWT trên partition/row đúng đắn, không dùng một logged batch không điều kiện rồi kỳ vọng không có lost update.

## 12. Bulk ingestion: so batch với các write bất đồng bộ

### 12.1. Hai lựa chọn cần benchmark

**Lựa chọn A — Batch nhỏ theo partition**

~~~text
source events
 -> group by partition
 -> batch <= app limits
 -> coordinator / replica sets
 -> đo p95/p99, batch size, errors
~~~

**Lựa chọn B — Ghi riêng bất đồng bộ**

~~~text
source events
 -> PreparedStatement + BoundStatement
 -> executeAsync mỗi mutation
 -> bounded in-flight + rate limiter
 -> đo p95/p99, throughput, errors
~~~

Ví dụ driver:

~~~java
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import java.util.concurrent.CompletionStage;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;

BoundStatement one = insert.bind(
    customerId, day, eventTs, eventId,
    "CREATED", 20500L, "new-event");

CompletionStage<AsyncResultSet> completion =
    session.executeAsync(one);

// Đây là một lời gọi ví dụ; hệ thống thật cần giới hạn
// số request đang chờ và xử lý lỗi theo từng event.
~~~

Không lấy đoạn code này làm một **load generator không giới hạn**; với bulk import, dùng queue/semaphore/rate limiter và checkpoint. Nếu database đang có compaction backlog hoặc pending tasks, mở thêm concurrency dễ làm latency và timeout tăng.

### 12.2. Vì sao nhiều async writes có thể tốt hơn một batch lớn?

Driver có thể định tuyến từng mutation theo partition key/token-aware khi nhận đủ routing metadata, phân phối coordinator và xử lý backpressure theo request. Một logged batch lớn gom nhiều partition vào một coordinator có thể làm mất sự phân tán này, tăng batchlog và kéo dài tail latency.

**Nhưng** nhiều async writes riêng cũng không có atomicity nhóm và có thể gửi quá nhiều request nếu thiếu giới hạn. Chọn theo **semantics nghiệp vụ trước**, sau đó benchmark.

### 12.3. Một CQL batch không thay SELECT bulk

`BEGIN BATCH ... APPLY BATCH` dành cho **INSERT/UPDATE/DELETE** và các mutation hợp lệ, **không dùng gom nhiều SELECT**. Nếu API tạo N+1 reads, cần thiết kế bảng theo truy vấn, đọc đúng partition/projection và giảm fan-out, không thử nhét `SELECT` vào BatchStatement.

## 13. Benchmark và quan sát chi phí batch

### 13.1. Biến cần giữ cố định

Khi so LOGGED, UNLOGGED và nhiều writes độc lập, giữ các yếu tố tương đương:

| Biến | Vì sao cần cố định |
| --- | --- |
| Cassandra version, RF/DC, số node khỏe | Ảnh hưởng replica placement và CL |
| CL ghi/đọc | Ảnh hưởng số ACK/phản hồi và latency |
| Tổng số mutation | Tránh batch chạy ít việc hơn nên “nhanh” |
| Partition popularity | Hot partition có latency khác nhiều khóa phân tán |
| Payload/bytes và TTL | Tạo chi phí network/storage/compaction khác |
| Concurrency và target QPS | Thay đổi overload, pending tasks, retry |
| Retry/speculative settings | Có thể khuếch đại tổng requests |
| Warm-up, background compaction/repair | Có thể che kết quả |

**Chỉ so cùng nghiệp vụ được bảo đảm.** Không xem UNLOGGED nhanh hơn LOGGED là “thắng” nếu nghiệp vụ cần completion semantics của LOGGED. Và không so 1 batch xuyên nhiều partition với 100 write riêng rồi bỏ qua sai khác về idempotency/partial visibility.

### 13.2. Các thước đo

~~~text
batch_id, batch_type, first_partition_key_hash,
statement_count, distinct_partition_count, estimated_bytes,
CL, coordinator, elapsed_ms, outcome, retry_count
~~~

Trong báo cáo production cần tránh log **raw partition key, PII hoặc payload**, thay bằng hash/ID nội bộ thích hợp. Tối thiểu thu:

- `p50/p95/p99` của **batch end-to-end**, phân theo loại batch và số mutation.
- **Mutations/sec** cùng **CQL requests/sec**, vì một batch là một request nhưng nhiều mutation.
- **Error rate** theo WriteTimeout/Unavailable/WriteFailure/InvalidQuery và trạng thái UNKNOWN.
- **Batch warnings/guardrail rejection**, kích thước batch thực/ước lượng và số partition.
- CPU/GC, heap, network, disk I/O, commitlog/memtable, pending tasks, compaction.
- Trạng thái batchlog/replay, hints, read repair/anti-entropy repair nếu có.
- Coordinator/replica distribution theo node và DC; không chỉ đo tổng trung bình cluster.

Các công cụ cơ bản:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats java_batch_lab.events_by_customer_day
nodetool netstats
~~~

Tùy phiên bản, thêm metrics/JMX về batchlog và dropped messages, nhưng **không giả định tên metric hay output giống nhau** trên mọi Cassandra. `nodetool status` cho biết health/token/load, **không trực tiếp chứng minh một batch có bao nhiêu partition**; thông tin này phải thu từ ứng dụng hoặc đo/tracing có chọn lọc.

### 13.3. Số ví dụ hoàn toàn giả định

| Thử nghiệm | Mutations | Partitions | p95 | Errors/10k | Kết luận hợp lý |
| --- | ---: | ---: | ---: | ---: | --- |
| A: LOGGED 2 sự kiện cùng partition | 2 | 1 | 9 ms | 0 | Có thể chấp nhận nếu cần semantics nhóm |
| B: LOGGED 200 sự kiện nhiều partition | 200 | 200 | 180 ms | 40 | Có dấu hiệu fan-out và batch lớn, cần xem metrics |
| C: 200 INSERT async, bounded | 200 | 200 | 14 ms/INSERT | 3 | Cần đo **thời gian hoàn tất cả nhóm** và correctness trước khi so A/B |

Các số trên là **ví dụ để luyện cách đọc báo cáo**, không phải số benchmark thật. p95 **một INSERT** không thể so trực tiếp p95 **hoàn tất cả nhóm 200 INSERT**; phải thống nhất đơn vị đo và bảo đảm nghiệp vụ.

## 14. Runbook chẩn đoán và giới hạn production

### 14.1. Khi gặp “Batch too large” hoặc warning

1. Ghi **batch type, số statement, số partition, bytes ước lượng** của request gây lỗi.
2. Đọc cấu hình ngưỡng batch size/guardrail của đúng Cassandra version.
3. Đối chiếu thời gian coordinator, memory, pending tasks, batchlog và network.
4. Giảm batch/đổi sang ghi riêng **nếu semantics nghiệp vụ cho phép**.
5. Không tự nâng `batch_size_fail_threshold_in_kb` chỉ để cho batch hàng MiB đi qua khi chưa đánh giá RAM/GC và I/O.

### 14.2. Khi logged batch timeout

- Ghi `UNKNOWN_WRITE`, batch ID, operation IDs, CL, coordinator, thời điểm và danh sách PK.
- Không coi một phần readback thiếu tức cả batch đã rollback.
- Đánh giá idempotency của **từng mutation**, timestamp/TTL, concurrent writers và replay.
- Đối soát theo manifest với `FOUND_MATCH`, `MISSING_AT_CL`, `MISMATCH`, `READ_ERROR`. Không dùng một `COUNT(*)` toàn bảng để quyết định.
- Nếu cần recovery, dùng workflow/outbox/repair theo kế hoạch; **repair không tạo lại event chưa từng được ghi ở replica nào**.

### 14.3. Khi counter batch timeout

- **Không retry tự động** phép `+1`.
- Nếu số đếm mang tính nghiệp vụ quan trọng, đối soát từ **event ledger/source IDs** rồi thiết kế cơ chế sửa số đếm phù hợp, không suy từ một giá trị counter đang đọc rằng mọi phép tăng trước đó đều đã nhận ACK.

### 14.4. Khi batch làm p99 tăng

| Triệu chứng | Giả thuyết | Biện pháp thử có kiểm soát |
| --- | --- | --- |
| p99 tăng theo số partition | Coordinator fan-out/batchlog | Giới hạn 1 partition hoặc thử async writes bounded |
| CPU/GC tăng theo bytes | Payload/serialization quá lớn | Giảm projection/row size, trần bytes |
| Timeout ở một vài node | Replica hot, compaction, network | Đo theo token/partition, pending tasks và disk |
| Retry tăng sau timeout | Retry storm hoặc speculative duplication | Giảm retry/concurrency, đánh giá idempotency |
| Multi-DC chậm | Client chọn coordinator sai DC hoặc WAN replication | Kiểm local DC/CL và network |
| Dữ liệu không khớp sau re-run | UUID mới, timestamp/TTL, concurrent writer | Operation ID ổn định, manifest và ownership |

### 14.5. Checklist trước khi triển khai

- [ ] Mục đích dùng batch rõ ràng: atomicity/hoàn tất nhóm hay chỉ tối ưu throughput?
- [ ] Chọn đúng LOGGED/UNLOGGED/COUNTER, không trộn counter và mutation thường.
- [ ] Đã kiểm **số partition thực tế**, không nhầm cùng customer với cùng partition khi khác bảng/ngày.
- [ ] Có trần statements/bytes/partition count và field sizes ở API.
- [ ] Đủ RF/CL cho local DC; không hạ CL để che lỗi batch.
- [ ] Prepared statement tái sử dụng, `CqlSession` dài hạn, hạn chế N+1 và query filtering.
- [ ] Có timeout/retry budget và xét idempotence **từng mutation**, không chỉ batch.
- [ ] Có operation ID/manifest độc lập, phân loại UNKNOWN_WRITE/READ_ERROR.
- [ ] Đã benchmark với writes độc lập có bounded concurrency, cùng workload/semantics.
- [ ] Theo dõi p95/p99, warning batch size, errors, pending tasks, coordinator/replica load.
- [ ] Có canary, rollback/forward-fix và phương án sửa dữ liệu không dựa vào xóa SSTable.

## 15. Câu hỏi và bài tập thực hành

**Bài 1 — Nhận diện partition.** Bảng có `PRIMARY KEY ((customer_id, event_day), event_ts, event_id)`. Hai event cùng customer nhưng khác `event_day` thuộc một hay hai partition? Nếu cùng customer/day nhưng khác `event_id` thì sao?

**Bài 2 — LOGGED hay UNLOGGED?** Nhóm hai mutation cùng partition cần được quan sát như một nhóm; nhóm 200 mutation nhiều partition chỉ nhằm giảm số request client. Hãy đề xuất cách thực hiện riêng cho hai tình huống, nêu đánh đổi.

**Bài 3 — Atomicity vs isolation.** Vì sao một logged batch ghi P1 và P2 không được dùng như transaction chuyển tiền hai tài khoản nếu một reader có thể thấy P1 trước P2? Đề xuất ledger/operation state để khắc phục.

**Bài 4 — Counters.** Một COUNTER BATCH tăng hai metric, client timeout, sau đó app retry. Giá trị cuối có thể sai thế nào? Vì sao đổi `idempotence=true` không tạo exactly-once?

**Bài 5 — Giới hạn byte.** Có 20 mutation, mỗi detail UTF-8 10 KiB. Tổng dữ liệu detail đã khoảng 200 KiB trước protocol overhead. Với ngân sách ứng dụng 64 KiB, request phải được xử lý thế nào? Vì sao `LIMIT` không giải quyết write batch?

**Bài 6 — Java code.** Viết `BatchStatement.builder(DefaultBatchType.LOGGED)` từ hai `BoundStatement` với cùng `customerId` và `eventDay`, đặt `LOCAL_QUORUM`. Giải thích vì sao dùng `PreparedStatement` thay string concatenation.

**Bài 7 — Retry và TTL.** Một mutation cùng PK được retry sau 10 phút nhưng dùng TTL 1 giờ tính tại mỗi lần gửi. Vì sao thời điểm hết hạn có thể thay đổi? Thiết kế timestamp/TTL/ownership contract để replay an toàn.

**Bài 8 — Multi-table.** Ứng dụng ghi một bảng danh sách theo `(customer_id, day)` và một bảng chi tiết theo `(customer_id, order_id)` bằng logged batch. Vì sao không nên gọi đây là transaction có isolation xuyên hai bảng? Cần kiểm chứng gì khi timeout?

**Bài 9 — Bulk ingestion.** Với 10.000 sự kiện trên 8.000 partition, so một logged batch khổng lồ, 400 batch nhỏ và 10.000 async writes có in-flight bound. Các thước đo nào phải thu để so đúng throughput và failure semantics?

**Bài 10 — LWT.** Một lệnh `INSERT ... IF NOT EXISTS` đã trả `[applied]=true`, lần tiếp theo cùng PK trả `false`. Đây có phải bug? Tại sao conditional batch nhiều partition không thể mặc định là transaction CAS?

**Bài 11 — Chẩn đoán.** Cassandra cảnh báo batch quá lớn và pending tasks tăng. Nêu các bước trước khi điều chỉnh guardrail, và vì sao mở rộng threshold có thể làm tình hình tệ hơn.

**Bài 12 — Đối soát.** Batch gồm ba mutation đã trả timeout. Readback: hai `FOUND_MATCH`, một `READ_ERROR`. Bạn có được báo một mutation bị mất không? Cần lưu gì trong manifest để xác minh đúng?

## Ghi nhớ

**`BatchStatement` gom nhiều mutation CQL thành một request, nhưng không phải công cụ bulk ingestion nhanh mặc định và không phải transaction ACID xuyên nhiều partition.** Chọn đúng **LOGGED**, **UNLOGGED** hoặc **COUNTER**; phân biệt atomicity ở phạm vi phù hợp với isolation toàn cluster; nhận diện partition bằng **đầy đủ partition key và bảng**. Trong Java, dùng `PreparedStatement`/`BoundStatement`, giới hạn **statement count, payload bytes, distinct partitions, in-flight requests**, giữ RF/CL đúng yêu cầu và xem timeout là **UNKNOWN_WRITE** cho tới khi đối soát. Với nhiều partition không cần semantics nhóm, benchmark **ghi riêng bất đồng bộ có backpressure** thay vì tạo batch khổng lồ. Thành công được chứng minh bằng **dữ liệu, lỗi, latency p95/p99 và tài nguyên**, không phải bằng số request CQL giảm đi.
