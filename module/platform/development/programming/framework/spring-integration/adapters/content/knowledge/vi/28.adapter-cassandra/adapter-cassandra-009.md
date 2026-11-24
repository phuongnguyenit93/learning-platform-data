# Retry unavailable và timeout trong Cassandra message flow

## 1. Bài toán thực tế: cùng một event, ba loại thất bại

Một ứng dụng nhận `OrderPaid` qua JMS, chuyển thành Spring Integration `Message<OrderPaidEvent>` rồi ghi Apache Cassandra. Trong giờ cao điểm, hệ thống thấy:

- `UnavailableException` khi một số replica không khả dụng cho `LOCAL_QUORUM`.
- `WriteTimeoutException` khi coordinator đã gửi mutation nhưng chưa nhận đủ phản hồi.
- `DriverTimeoutException` khi Java Driver hết request deadline dù trạng thái mutation phía Cassandra chưa rõ.

Nếu nhóm phát triển đơn giản bọc mọi lỗi trong `retry(10)`, hàng nghìn JMS messages có thể nhân thành hàng chục nghìn Cassandra requests. Ngược lại, nếu thấy timeout rồi xác nhận JMS message thành công, event có thể bị bỏ sót nếu write thực sự chưa hoàn tất.

**Vấn đề trung tâm không phải “retry bao nhiêu lần”, mà là:** lỗi thuộc tầng nào, Cassandra có thể đã làm gì, operation có an toàn khi lặp lại không, deadline nào còn lại và hệ thống nguồn sẽ acknowledge vào lúc nào?

Đây là bài **Retry unavailable và timeout** thuộc chương **Adapter Cassandra**, module **SPRING_INTEGRATION_ADAPTERS**. Module kết nối các hệ thống ngoài vào Spring Integration qua inbound/outbound adapter, gateway, poller và `MessageChannel`; thực hành trao đổi với file, SFTP, HTTP, JMS, AMQP, Kafka và cơ sở dữ liệu, xử lý message contracts, lỗi và connection lifecycle. Bài tập trung vào retry Cassandra khi một message đi từ nguồn ngoài tới adapter/gateway.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt `UnavailableException`, `ReadTimeoutException`, `WriteTimeoutException`, `DriverTimeoutException` và lỗi transport/request abort.
2. Giải thích consistency level, replication factor, coordinator và các giá trị `required`, `alive`, `received`, `blockFor`.
3. Hiểu `DefaultRetryPolicy` của Java Driver 4.x retry **trường hợp nào** và **không retry trường hợp nào**.
4. Đánh giá idempotency của `INSERT`, `UPDATE`, LWT, batch và counter trước khi bật retry.
5. Cấu hình driver request timeout, consistency, execution profile và per-statement options.
6. Đặt retry ở tầng driver, Reactor/Spring service hay JMS/Kafka broker **một cách có chủ đích**, tránh retry storm.
7. Thiết kế Spring Integration Cassandra flow với error propagation và acknowledgement boundary rõ ràng.
8. Xây test matrix cho node failure, server/client timeout, response loss và redelivery.

## 2. Cassandra write đi qua nhiều ranh giới

~~~mermaid
flowchart LR
    S["HTTP/JMS/Kafka source"] --> I["Spring Integration inbound endpoint"]
    I --> M["MessageChannel + validator/transformer"]
    M --> H["CassandraMessageHandler"]
    H --> O["ReactiveCassandraOperations"]
    O --> D["Java Driver CqlSession"]
    D --> C["Cassandra coordinator"]
    C --> R1[("Replica A")]
    C --> R2[("Replica B")]
    C --> R3[("Replica C")]
    R1 -. "ACK" .-> C
    R2 -. "ACK" .-> C
    R3 -. "ACK" .-> C
    C -. "Success/error/timeout" .-> D
~~~

Giả sử keyspace có replication factor `RF=3` trong một datacenter và write consistency `LOCAL_QUORUM`. Coordinator cần phản hồi từ **hai trong ba local replicas** để báo write thành công theo mức nhất quán yêu cầu. Khi chỉ một replica phản hồi trước thời hạn, coordinator có thể trả `WRITE_TIMEOUT`; điều đó **không phủ định** rằng replica ấy đã áp dụng mutation.

### 2.1. Năm kết quả thường bị gọi chung là “DB lỗi”

| Kết quả phía client | Cassandra có thể đã làm gì? | Kết luận an toàn |
|---|---|---|
| Write success | Có đủ ACK theo CL | Operation đạt yêu cầu tại thời điểm phản hồi, không atomic với broker |
| `UNAVAILABLE` | Coordinator biết không đủ replica đang khả dụng cho CL | Không đạt CL; không có căn cứ để tự hạ CL |
| `WRITE_TIMEOUT` | Mutation có thể đã tới một/vài replicas | Outcome không chắc, không khẳng định rollback |
| `DRIVER_TIMEOUT` | Request có thể chưa ra khỏi driver, đang chạy, hoặc đã xong | Client không nhận kết quả trong deadline |
| Network closed / aborted | Coordinator có thể đã nhận mutation trước khi kết nối mất | Không tự suy rằng write chưa xảy ra |

Với **read**, timeout cũng không tự có nghĩa row không tồn tại. Tầng API không được chuyển mọi Cassandra read timeout thành HTTP `404 Not Found` hoặc `Mono.empty()`, vì “không tìm thấy” khác “không thể xác nhận kết quả đọc”.

### 2.2. Không có distributed transaction tự động

~~~mermaid
sequenceDiagram
    participant Broker as JMS broker
    participant SI as Integration flow
    participant DB as Cassandra
    Broker->>SI: Deliver evt-9001
    SI->>DB: INSERT evt-9001
    DB-->>SI: Mutation đã hoàn tất nhưng response bị mất
    Note over SI,DB: Client nhận timeout, trạng thái chưa chắc
    SI-->>Broker: Rollback / không ack theo policy
    Broker->>SI: Redeliver evt-9001
    SI->>DB: Retry cùng primary key/payload
    DB-->>SI: Success
    SI-->>Broker: Commit/ack
~~~

Thành công ở Cassandra **không commit JMS session**. Tương tự Kafka offset commit không chung transaction với Cassandra write. Khi nguồn redeliver sau Cassandra success, ứng dụng phải có **stable event ID và idempotent mutation** để không gây side effect lặp.

## 3. Replication factor, consistency và chữ “unavailable”

### 3.1. Replication factor (RF) không phải số consumer

Ví dụ test cluster có ba Cassandra nodes trong datacenter `dc1`:

~~~sql
CREATE KEYSPACE IF NOT EXISTS shop_integration
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
};
~~~

RF=3 nghĩa là Cassandra lưu replicas của một partition trên **ba nodes theo replication strategy**, không phải ba JMS consumers hoặc ba Kafka partitions. Trong môi trường một node Testcontainers với RF=1, không thể dùng cùng lab để chứng minh cơ chế mất một trong ba replicas.

Với `LOCAL_QUORUM` và RF=3:

\[
Q = \left\lfloor \frac{3}{2} \right\rfloor + 1 = 2
\]

| Consistency level | Số phản hồi cần thiết (RF=3, một DC) | Rủi ro chính |
|---|---:|---|
| `LOCAL_ONE` | 1 replica local | Read có thể chưa thấy write mới |
| `ONE` | 1 replica | Phạm vi DC khác tùy topology/routing |
| `LOCAL_QUORUM` | 2 replicas local | Có thể thất bại khi hai replicas không đáp ứng |
| `QUORUM` | 2 replicas toàn keyspace trong ví dụ một DC | Multi-DC khác LOCAL_QUORUM |
| `ALL` | 3 replicas | Replica chậm/lỗi làm giảm availability |

Trong multi-DC, `LOCAL_QUORUM` lấy quorum trên **RF của local datacenter**, không cộng mọi replicas toàn cluster. Một write `LOCAL_QUORUM` ở dc1 không có nghĩa read `LOCAL_QUORUM` ở dc2 đã thấy dữ liệu ngay; replication giữa các DC có thể chưa hội tụ.

### 3.2. Vì sao coordinator trả UnavailableException?

`UNAVAILABLE` thường xảy ra khi coordinator **biết trước** rằng số replicas sống/khả dụng theo thông tin cluster **ít hơn số cần cho CL**.

~~~text
RF=3, CL=LOCAL_QUORUM
required = 2
alive    = 1

Coordinator: không thể đạt LOCAL_QUORUM ngay
             -> UNAVAILABLE
~~~

`UnavailableException` có metadata liên quan `consistencyLevel`, `required` và `alive` (tên accessor theo driver version). Hai giá trị này giúp chẩn đoán **yêu cầu CL không đạt**, không cung cấp bằng chứng đầy đủ về dữ liệu có/không tồn tại trên từng replica.

### 3.3. Vì sao không tự chuyển LOCAL_QUORUM thành ONE?

Nếu một nghiệp vụ cam kết **read-after-write** dựa vào R/W quorum overlap, hạ write CL xuống `ONE` có thể phá vỡ giả định đó. Ví dụ:

~~~text
RF=3, write ONE: A ACK.
Read QUORUM: B và C trả dữ liệu cũ trước khi hội tụ.

Write có thể đã được ứng dụng báo "thành công",
nhưng read ngay sau đó không thấy.
~~~

`ConsistencyDowngradingRetryPolicy` có thể thử CL yếu hơn trong một số tình huống, nhưng tài liệu driver cảnh báo nó có thể **phá invariants và làm sai datacenter locality**. Với event thanh toán/audit, mặc định nên giữ CL có chủ đích và xử lý availability bằng retry/backoff/reconciliation thay vì downgrade âm thầm.

## 4. Phân biệt Unavailable, server timeout và driver timeout

| Exception / tín hiệu | Phát sinh từ | Khi nào? | Điều cần làm rõ |
|---|---|---|---|
| `UnavailableException` | Cassandra coordinator | Không đủ live replicas theo CL tại thời điểm xử lý | `required`, `alive`, DC/RF, coordinator view |
| `ReadTimeoutException` | Cassandra coordinator | Không đủ read responses/data đúng hạn | `received`, `blockFor`, `dataPresent` |
| `WriteTimeoutException` | Cassandra coordinator | Không đủ ACK cho write đúng hạn | `received`, `blockFor`, `WriteType` |
| `ReadFailureException` | Cassandra server | Lỗi xử lý read khác timeout | Replica failures, logs, có nên retry |
| `WriteFailureException` | Cassandra server | Lỗi xử lý write khác timeout | Outcome uncertainty, write type |
| `DriverTimeoutException` | Java Driver client | Hết **tổng request deadline** | Driver queue, network, retries, server response |
| `ClosedConnectionException` / heartbeat error | Driver transport | Mất connection trước khi nhận kết quả | Request có thể đã tới server |
| `OverloadedException` | Cassandra server | Node quá tải không đáp ứng | Giảm concurrency, tránh retry storm |
| `RequestThrottlingException` | Java Driver throttler | Không được phép chạy/enqueue | Ứng dụng đang overload, có thể fail fast |
| `InvalidQueryException` / `UnauthorizedException` | Cassandra server | CQL/schema/permission không hợp lệ | Permanent cho tới khi sửa config/schema |

### 4.1. ReadTimeout: đủ responses nhưng chưa có dữ liệu

Cassandra read có thể hỏi một số replicas lấy **data** và số khác lấy **digest**. Nếu đủ replicas đã phản hồi nhưng chưa có actual data response, coordinator vẫn có thể trả `ReadTimeoutException`.

~~~text
Read CL=QUORUM, RF=3, blockFor=2
received=2, dataPresent=false

Hai phản hồi không tự đồng nghĩa dữ liệu cần thiết đã nhận đủ.
~~~

Do đó driver `DefaultRetryPolicy` có thể **retry cùng coordinator một lần** trong trường hợp cụ thể `received >= blockFor && !dataPresent`, còn các read timeouts khác thường bị trả về caller.

### 4.2. WriteTimeout: writeType ảnh hưởng retry

Server-side write timeout có metadata `WriteType`. Các loại có thể bao gồm `SIMPLE`, `BATCH`, `UNLOGGED_BATCH`, `BATCH_LOG`, `COUNTER`, `CAS` tùy Cassandra/driver version.

**Điểm rất dễ sai:** `DefaultRetryPolicy` Java Driver 4.x không tự retry mọi `WriteTimeoutException` cho một `INSERT`. Mặc định nó chỉ cân nhắc **một retry trên cùng coordinator với `BATCH_LOG`** khi query idempotent, vì cơ chế ghi batchlog có đặc thù riêng. Với `SIMPLE` write timeout, thông thường driver **rethrow** để ứng dụng xử lý trạng thái chưa rõ.

### 4.3. DriverTimeout không đồng nghĩa coordinator WriteTimeout

`basic.request.timeout` trong Java Driver 4.x là **deadline cho toàn bộ request phía client**, tính cả retries và speculative executions. Nếu driver có throttling queue, request có thể timeout **trước khi gửi tới một Cassandra node**.

~~~mermaid
sequenceDiagram
    participant App as Application
    participant D as Driver
    participant C as Coordinator
    App->>D: Execute INSERT (deadline 2s)
    D->>C: Request
    C-->>D: Có thể phản hồi muộn
    Note over D: Hết deadline phía client
    D-->>App: DriverTimeoutException
    Note over C: Mutation có thể đã áp dụng hoặc còn đang xử lý
~~~

**Không suy ngược từ `DriverTimeoutException` rằng coordinator đã gửi `WRITE_TIMEOUT`.** Driver timeout và server timeout khác tầng, có thể xuất hiện trong những trường hợp khác nhau.

### 4.4. Timeout ngoài Cassandra

Spring `sendTimeout`, Spring gateway `replyTimeout`, HTTP caller deadline, Reactor `timeout(Duration)`, JMS transaction boundary và Kafka poll/offset lifecycle đều **khác** driver timeout.

Nếu Spring gateway hết hạn sau 1,5 giây nhưng Cassandra request còn đang chạy tối đa 3 giây, caller có thể nhận timeout **dù database hoàn tất sau đó**. Hủy subscription/client wait không tự rollback mutation đã tới Cassandra.

## 5. DefaultRetryPolicy Java Driver 4.x hoạt động thế nào?

Java Driver có một **retry policy cấp request**, được cấu hình bởi `advanced.retry-policy`. `DefaultRetryPolicy` là mặc định và chọn retry trong **một số trường hợp có xác suất thành công cao**, thay vì lặp mọi lỗi. Driver cũng có các quy tắc nội bộ như thử node khác khi request **chưa thể gửi bytes lên network**; chúng không hoàn toàn đi qua callback của retry policy.

### 5.1. Quyết định của policy

| Tín hiệu lỗi | Hành vi tiêu biểu của DefaultRetryPolicy 4.19 | Tại sao? |
|---|---|---|
| `UNAVAILABLE` | Tối đa một retry trên **node kế tiếp** trong query plan | Coordinator đầu có thể nhìn sai trạng thái cluster do cô lập mạng |
| `READ_TIMEOUT`, đủ responses nhưng không có data | Tối đa một retry trên **cùng coordinator** | Có thể chọn lại replica cung cấp dữ liệu |
| `READ_TIMEOUT` không đủ responses | Rethrow | Chưa có dấu hiệu retry cùng CL sẽ thành công |
| `WRITE_TIMEOUT` loại `BATCH_LOG` | Tối đa một retry trên **cùng coordinator**, nếu idempotent | Có thể vượt tình huống batchlog endpoints chậm |
| `WRITE_TIMEOUT` loại `SIMPLE`/`COUNTER` thông thường | Rethrow | Mutation có thể đã áp dụng, retry có thể gây tác động lặp |
| Connection closed / heartbeat request aborted | Thử **next node** nếu idempotent | Không biết request cũ đã áp dụng hay chưa |
| `OverloadedException`, `ServerError`, `TruncateException` | Có thể thử next node khi policy cho phép | Có khả năng một coordinator khác xử lý được |
| `ReadFailureException`/`WriteFailureException` | Thường rethrow | Nhiều trường hợp không nên retry blind |
| Invalid query/authorization/codec mismatch | Fail/rethrow | Không sửa được bằng retry cùng input |

**Phạm vi quan trọng:** các rule trên mô tả driver 4.19. `DefaultRetryPolicy` nói chung đòi hỏi request được đánh dấu **idempotent** để cho phép các retry có nguy cơ operation đã tới server. Driver có một số đường xử lý cứng trước network write không cần flag đó. **Không xem bảng như lời hứa retry chính xác một lần cho mọi exception và mọi phiên bản.**

### 5.2. RetryVerdict API: đừng dùng callback cũ

Driver 4.10+ bổ sung các callback trả `RetryVerdict` trong interface `RetryPolicy`:

~~~java
// Chữ ký API (minh họa, không phải class triển khai đầy đủ):
onUnavailableVerdict(
    Request request, ConsistencyLevel cl,
    int required, int alive, int retryCount);

onReadTimeoutVerdict(
    Request request, ConsistencyLevel cl,
    int blockFor, int received,
    boolean dataPresent, int retryCount);

onWriteTimeoutVerdict(
    Request request, ConsistencyLevel cl,
    WriteType writeType,
    int blockFor, int received, int retryCount);

onRequestAbortedVerdict(
    Request request, Throwable error, int retryCount);

onErrorResponseVerdict(
    Request request, CoordinatorException error, int retryCount);
~~~

Các phương thức cũ `onUnavailable(...)`, `onReadTimeout(...)`, `onWriteTimeout(...)` trả `RetryDecision` đã **deprecated** từ 4.10. Nếu buộc phải triển khai custom policy, dùng API đúng version, giới hạn attempts và giải thích lý do từng verdict. **Không cần custom retry policy cho hầu hết ứng dụng**; mặc định thường tốt hơn một policy thử lại mọi exception.

### 5.3. Vì sao không bật ConsistencyDowngradingRetryPolicy?

Policy này có thể trả trạng thái “thành công” cho write chỉ có một replica ACK dù CL yêu cầu quorum, hoặc đọc ở CL yếu hơn. Kết quả là một số business invariants dựa trên quorum **không còn đúng**, và local datacenter preference có thể bị phá.

**Không bật `ConsistencyDowngradingRetryPolicy` cho thanh toán, audit, quyền truy cập hoặc bất kỳ luồng nào đòi mức CL cụ thể** chỉ để làm giảm tỷ lệ exceptions. Nếu use case thực sự cho phép eventual stale reads, hãy chọn CL phù hợp ngay từ business contract và giám sát hệ quả.

## 6. Idempotency là điều kiện trước retry, không phải kết quả của retry

Trong Cassandra, **idempotent operation** là thao tác lặp lại vẫn để database ở trạng thái tương đương thao tác một lần (xét semantics và concurrent writes). Driver **không tự biết** business contract của mọi CQL statement.

### 6.1. Hai lớp idempotency

| Lớp | Ví dụ | Không tự làm được |
|---|---|---|
| **CQL statement idempotency** | `INSERT` cùng primary key và same values | Đảm bảo email/HTTP side effect ngoài DB chỉ gửi một lần |
| **Business event idempotency** | `eventId` bất biến qua JMS redelivery/Kafka replay | Tự đảm bảo hai Cassandra tables cùng commit atomic |

Một statement có thể idempotent trong Cassandra nhưng toàn bộ workflow vẫn không idempotent: ví dụ ghi row cùng ID rồi gửi email lần nữa sau mỗi replay.

### 6.2. Ma trận xem xét idempotency

| CQL/business operation | Có nên retry tự động? | Điều kiện cần |
|---|---|---|
| `SELECT` theo primary key | Thường có | Read có thể thấy dữ liệu mới hơn giữa các lần thử |
| Immutable `INSERT` cùng `event_id` và values | Có điều kiện | Payload, primary key, timestamp/TTL semantics cố định |
| `UPDATE SET state = 'PAID'` | Có điều kiện | Không có stale overwrite do concurrent version |
| `UPDATE list = ['x'] + list` | **Không** | Lặp làm list có thể thêm phần tử hai lần |
| Cassandra counter `+1` | **Không** | Retry có thể tăng hai lần |
| `INSERT ... IF NOT EXISTS` | Chỉ khi có handling LWT result | `applied=false` cần phân biệt duplicate/conflict |
| Multi-partition batch | Tùy mutations | **Tất cả** component mutations phải an toàn khi lặp |
| Gửi HTTP/payment/email sau Cassandra write | Không tự idempotent | Downstream idempotency key/durable outbox |

### 6.3. `setIdempotent(true)` chỉ là metadata cho driver

Ví dụ `OrderPaid` được lưu thành một row bất biến:

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_event (
    event_id text PRIMARY KEY,
    order_id text,
    event_type text,
    payload_json text
);
~~~

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement insert = SimpleStatement.newInstance(
        "INSERT INTO shop_integration.order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)",
        "evt-9001", "ORD-9001", "OrderPaid",
        "{\"eventId\":\"evt-9001\",\"amountMinor\":150000}"
).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
 .setTimeout(Duration.ofSeconds(3))
 .setIdempotent(true);

session.execute(insert);
~~~

Các setter của built-in statement trong Java Driver 4.x là **immutable**, trả statement mới; chain như trên giữ các thay đổi. `setIdempotent(true)` cho driver biết operation này **được ứng dụng xem là an toàn để thử lại**, **không tạo unique constraint hoặc inbox deduplication**.

### 6.4. Đừng đánh dấu mọi statement idempotent ở global config

Driver option:

~~~hocon
datastax-java-driver {
  basic.request.default-idempotence = false
}
~~~

Mặc định Java Driver 4.x là `false`. Hãy đánh dấu **từng statement** hoặc execution profile khi đã xác định semantics. Việc đặt `basic.request.default-idempotence = true` toàn cục trong hệ thống có counters, list appends, side effects và writes với giá trị thay đổi qua replay có thể tạo retry sai nghiệp vụ.

### 6.5. Vì sao cùng primary key vẫn chưa chắc idempotent end-to-end?

Giả sử retry cùng `event_id` nhưng consumer:

- Tạo lại `occurredAt = Instant.now()`, làm thay đổi dữ liệu/event timeline.
- Sinh `payloadJson` khác (có retry timestamp, random token, thông tin volatile).
- Ghi `USING TTL 86400` mới, kéo dài expiration so với lần đầu.
- Ghi bảng projection thứ hai nhưng crash giữa hai writes.
- Sau mỗi success lại gọi thanh toán/email một lần.

Lúc đó **Cassandra upsert không còn đủ** để bảo đảm kết quả nghiệp vụ chỉ một lần. Cần durable event identity, immutable payload, explicit TTL/timestamp policy và recovery/reconciliation cho các bước khác.

## 7. Retry budget phải thuộc toàn workflow

Một message có thể trải qua nhiều nơi có retry:

~~~mermaid
flowchart TD
    A["JMS/Kafka source"] --> B["Spring Integration handler"]
    B --> C["Service retry / Reactor retryWhen"]
    C --> D["Java Driver RetryPolicy"]
    D --> E["Cassandra coordinator / replicas"]
    E -. "Timeout/error" .-> D
    D -. "Failed request" .-> C
    C -. "Exhausted" .-> B
    B -. "Throw/rollback" .-> A
    A -. "Redelivery/replay" .-> B
~~~

### 7.1. Retry multiplication

Ví dụ một JMS message được thử tối đa **5 deliveries**, service thực hiện tối đa **3 attempts mỗi delivery** (lần đầu + hai retries), và driver có tối đa **2 executions** cho một request trong tình huống được phép. Cận trên lý thuyết trong kịch bản đó có thể là:

\[
5 \times 3 \times 2 = 30 \text{ Cassandra executions}
\]

Đây là **minh họa**; không phải mọi loại exception làm driver retry, và speculative execution có thể tạo thêm attempts nếu được bật. Với 1.000 messages/s ở thời điểm cluster overload, retry multiplication có thể đẩy Cassandra vào **feedback loop** khiến outage nặng hơn.

### 7.2. Chọn một lớp chịu trách nhiệm retry dài hạn

Đối với inbound JMS/Kafka, cách dễ kiểm soát thường là:

1. **Driver `DefaultRetryPolicy`** xử lý số ít network/coordinator failures an toàn trong cùng request budget.
2. **Application service retry** chỉ dùng cho một tập transient failures nhỏ, có backoff/jitter và giới hạn attempts.
3. **Broker redelivery/retry topics** cho retry bền vững sau lỗi/process crash, có retry limit/DLQ.
4. **Reconciliation** cho timeout outcome không chắc, không chỉ retry mà còn xác minh event theo primary key.

Nếu broker đã có delayed retry policy bền vững, không nhất thiết cần thêm nhiều vòng `retryWhen` trong service. Nếu không có broker retry, phải thiết kế durable recovery thay vì gọi `Thread.sleep` vô hạn trong message listener.

### 7.3. Khi nào không retry?

Không retry cùng input cho `InvalidQueryException`, thiếu keyspace/table, quyền Cassandra sai, JSON schema sai, converter/codec mismatch hoặc missing `eventId`. Các lỗi này thường chỉ khắc phục được bằng **thay contract, migration, config hoặc code**.

Ngay cả khi `UNAVAILABLE` là lỗi hạ tầng, retry chỉ hữu ích nếu có khả năng cluster phục hồi và workflow còn deadline/budget. Nếu cả hai replicas cần cho quorum đang down trong nhiều phút, retry 100 lần trong 1 giây chỉ gây tốn tài nguyên.

## 8. Cấu hình Java Driver: timeout, CL, retry policy và execution profile

### 8.1. File application.conf

Java Driver 4.x sử dụng cấu hình HOCON `datastax-java-driver`:

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
    default-idempotence = false
  }

  advanced.retry-policy.class = DefaultRetryPolicy
  advanced.speculative-execution-policy.class = NoSpeculativeExecutionPolicy
}
~~~

**Các giá trị chỉ minh họa** cho cluster có replication/topology phù hợp. `LOCAL_QUORUM` không thể tự tạo thêm replicas khi keyspace/test cluster chỉ có một node. Timeout 3 giây không thay đổi Cassandra `read_request_timeout`/`write_request_timeout` hoặc deadline HTTP client.

Driver mặc định đã dùng `DefaultRetryPolicy` và tắt speculative execution; có thể **không cần khai báo hai dòng cuối**. Ví dụ viết tường minh để người học thấy quyết định retry không phải ngẫu nhiên.

### 8.2. Execution profiles tách read và write

~~~hocon
datastax-java-driver {
  basic.request {
    consistency = LOCAL_QUORUM
    timeout = 3 seconds
  }
  profiles {
    event-write {
      basic.request.consistency = LOCAL_QUORUM
      basic.request.timeout = 3 seconds
    }
    analytical-read {
      basic.request.consistency = LOCAL_ONE
      basic.request.timeout = 1500 milliseconds
    }
  }
}
~~~

`analytical-read` chỉ phù hợp khi nghiệp vụ **chấp nhận stale reads**; không dùng cho endpoint đòi read-after-write theo invariant quorum. Profile được chọn **theo use case đã được server xác thực**, không để một HTTP header chưa tin cậy tùy ý đổi CL xuống `ONE`.

### 8.3. Per-statement timeout và idempotency

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement select = SimpleStatement.newInstance(
        "SELECT event_id, event_type "
        + "FROM shop_integration.order_event WHERE event_id = ?",
        "evt-9001");

select = select
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(2))
        .setIdempotent(true);

var result = session.execute(select);
~~~

`SimpleStatement`/`BoundStatement` trong driver 4.x là **immutable**. Setter trả **statement mới**; nếu bỏ kết quả, config cũ vẫn còn. Dùng builder hoặc gán lại như ví dụ. `SELECT` theo key nhìn chung có thể retry, nhưng dữ liệu đọc lần sau có thể đã thay đổi do concurrent writer.

### 8.4. PreparedStatement và immutable BoundStatement

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

PreparedStatement prepared = session.prepare(
        "INSERT INTO shop_integration.order_event "
        + "(event_id, order_id, event_type, payload_json) "
        + "VALUES (?, ?, ?, ?)");

BoundStatement statement = prepared.bind(
        event.eventId(),
        event.orderId(),
        event.eventType(),
        event.payloadJson());

statement = statement
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setTimeout(Duration.ofSeconds(3))
        .setIdempotent(true);

session.execute(statement);
~~~

Đây là fragment của một DAO có `session` và business DTO `event` đã validate. Cờ `idempotent=true` chỉ đúng nếu **eventId, primary key, payload và TTL/write timestamp policy** ổn định. `PreparedStatement` có thể reuse giữa các requests, còn mỗi event cần một `BoundStatement` riêng; không sửa một builder dùng chung giữa nhiều consumers.

### 8.5. Kiểm tra effective config

~~~java
import com.datastax.oss.driver.api.core.config.DefaultDriverOption;
import com.datastax.oss.driver.api.core.config.DriverExecutionProfile;

DriverExecutionProfile profile = session.getContext()
        .getConfig()
        .getDefaultProfile();

System.out.println("requestTimeout="
        + profile.getDuration(DefaultDriverOption.REQUEST_TIMEOUT));
System.out.println("consistency="
        + profile.getString(DefaultDriverOption.REQUEST_CONSISTENCY));
System.out.println("defaultIdempotence="
        + profile.getBoolean(DefaultDriverOption.REQUEST_DEFAULT_IDEMPOTENCE));
~~~

Với named execution profile, đọc `session.getContext().getConfig().getProfile("event-write")` thay vì chỉ nhìn default. Spring Boot hoặc code tạo `CqlSession` có thể override `application.conf`; **file tồn tại không chứng minh option có hiệu lực**.

### 8.6. Driver timeout bao gồm nhiều bước hơn thời gian trên wire

~~~text
request deadline bắt đầu
   |
   +-- driver throttling queue / borrow connection
   +-- first coordinator attempt
   +-- optional retry on another/same coordinator
   +-- optional speculative execution (nếu bật)
   +-- response handling
   |
   +-- hết deadline -> DriverTimeoutException
~~~

Với driver 4.x, `basic.request.timeout` áp cho **toàn request**, không cấp lại 3 giây cho mỗi retry. Một request có thể chưa ra khỏi queue nhưng vẫn hết hạn. Đó là lý do tăng retry count không nhất thiết giúp khi queue/cluster đã quá tải.

## 9. Spring Data Cassandra: cấu hình write timeout trên đúng operation

Spring Data Cassandra cung cấp `ReactiveCassandraOperations`, `CqlTemplate` và các options cho CQL/entity operations. `WriteOptions` kế thừa phần tùy chọn query, gồm consistency, timeout và idempotency theo API phù hợp với Spring Data version.

### 9.1. Entity có business ID bất biến

~~~java
import org.springframework.data.cassandra.core.mapping.Column;
import org.springframework.data.cassandra.core.mapping.PrimaryKey;
import org.springframework.data.cassandra.core.mapping.Table;

@Table("order_event")
public record OrderEventRow(
        @PrimaryKey("event_id") String eventId,
        @Column("order_id") String orderId,
        @Column("event_type") String eventType,
        @Column("payload_json") String payloadJson) {}
~~~

Ví dụ mapping tên cột rõ ràng để tránh phụ thuộc `NamingStrategy`. Nếu schema có thêm tenantId, timestamp hoặc composite partition key, phải bổ sung field/annotation và mapper tương ứng, không mặc định `eventId` một mình phục vụ mọi query.

### 9.2. WriteOptions với CL và deadline

~~~java
import java.time.Duration;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.cql.WriteOptions;

@Configuration
class CassandraWritePolicyConfiguration {

    @Bean
    WriteOptions immutableEventWriteOptions() {
        return WriteOptions.builder()
                .consistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
                .timeout(Duration.ofSeconds(3))
                .idempotent(true)
                .build();
    }
}
~~~

Chỉ dùng `idempotent(true)` nếu DAO/flow thực sự ghi **immutable event** như hợp đồng ở mục 6. Với counter increments, list append và non-idempotent mutations, hãy chọn options khác và tránh retry tự động.

### 9.3. Cassandra outbound channel adapter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Bean
public IntegrationFlow persistImmutableOrderEvents(
        ReactiveCassandraOperations operations,
        WriteOptions immutableEventWriteOptions) {

    return IntegrationFlow.from("validatedOrderEventRows")
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(immutableEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

`validatedOrderEventRows` nhận Spring Message có payload **`OrderEventRow` với `@Table`**, không phải JSON String tùy ý. `WriteOptions` được dùng cho entity INSERT/UPDATE/DELETE mode; nếu handler nhận một driver `Statement<?>` qua `statementFunction(...)`, đặt CL/timeout/idempotency trên chính statement hoặc driver execution profile.

**Spring Integration `CassandraMessageHandler` mặc định async.** `endpoint.async(false)` yêu cầu chờ completion trong đường gọi đồng bộ (ví dụ `DirectChannel`) để lỗi Cassandra có thể propagate tới upstream listener. Nó **không** biến Cassandra và JMS thành một transaction nguyên tử.

### 9.4. Vì sao không thay WriteOptions trên singleton mỗi lần?

CL và timeout là **application policy**. Nếu source HTTP gửi header `"consistency": "ANY"`, đừng cho header đó thay đổi singleton template/handler options toàn cục; có thể phá giả định read-after-write và ảnh hưởng đồng thời nhiều tenants. Dùng execution profiles hoặc riêng flows theo use case được cấu hình server-side.

### 9.5. Khi app dùng service imperative hoặc reactive trực tiếp

Nếu ứng dụng chọn `@ServiceActivator` gọi custom DAO, nó có thể:

- Dùng `CqlSession.execute(Statement<?>)` và nhận driver exceptions.
- Dùng `ReactiveCassandraOperations.insert(entity)` trả reactive publisher.
- Dùng `CqlTemplate`/`ReactiveCqlTemplate` để chuyển đổi `DataAccessException`.

**Không giả định top-level exception luôn là driver exception class.** Spring Data có exception translation; cần xem cause chain và phân loại chính xác.

## 10. Service-layer retry có giới hạn bằng Reactor

Service-layer retry có thể hữu ích khi nguồn là một HTTP request hoặc workflow cần một vài attempts nhanh trước khi chuyển sang broker delayed retry. Nhưng nó phải được bật **sau khi đã xác định idempotency** và thống nhất retry budget với driver/broker.

### 10.1. Phân loại transient failure theo cause chain

~~~java
import com.datastax.oss.driver.api.core.DriverTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;
import com.datastax.oss.driver.api.core.servererrors.UnavailableException;
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;

public final class CassandraRetryClassifier {
    private CassandraRetryClassifier() {}

    // CHỈ dùng cho operation đã được chứng minh idempotent.
    public static boolean forImmutableEventWrite(Throwable error) {
        Throwable current = error;
        for (int depth = 0; current != null && depth < 12;
                depth++, current = current.getCause()) {
            if (current instanceof UnavailableException
                    || current instanceof WriteTimeoutException
                    || current instanceof DriverTimeoutException
                    || current instanceof OverloadedException) {
                return true;
            }
        }
        return false;
    }
}
~~~

Hàm này là **policy ví dụ** cho immutable event INSERT. `WriteTimeoutException`/`DriverTimeoutException` có **unknown outcome**; chỉ retry được vì business key/payload đã được chứng minh ổn định, không phải vì timeout an toàn cho mọi write. Với operation counter/append, classifier phải trả false cho các outcome-unknown paths; với read SELECT, dùng classifier riêng.

Không dùng classifier `forImmutableEventWrite` cho `LWT`, counter, HTTP call hay batch có các mutations non-idempotent. Nó cũng không phân biệt mọi tình trạng hạ tầng (ví dụ session closed do application shutdown); production cần thêm budget, cancellation, liveness và domain-specific conditions.

### 10.2. Retry.backoff trong reactive service

~~~java
import java.time.Duration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ImmutableOrderEventWriter {

    private final ReactiveCassandraOperations operations;

    public ImmutableOrderEventWriter(
            ReactiveCassandraOperations operations) {
        this.operations = operations;
    }

    public Mono<Void> save(OrderEventRow row) {
        if (row == null || row.eventId() == null
                || row.eventId().isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "eventId is required"));
        }

        return Mono.defer(() -> operations.insert(row).then())
                .retryWhen(Retry.backoff(
                            2, Duration.ofMillis(250))
                        .maxBackoff(Duration.ofSeconds(1))
                        .jitter(0.4)
                        .filter(CassandraRetryClassifier::forImmutableEventWrite));
    }
}
~~~

`Retry.backoff(2, ...)` có nghĩa tối đa **hai lần retry sau lần thử đầu**, không phải hai attempts tổng cộng. `Mono.defer(...)` tạo lại publisher cho mỗi subscription/attempt; dữ liệu `row` phải **bất biến** trong suốt các lần thử.

**Có thể không cần retry này trong một JMS listener vốn đã có broker redelivery/retry topics.** Ví dụ dành cho trường hợp cần service retries nhỏ, và phải tính chung với driver attempts + nguồn retries, tránh storm.

### 10.3. Không block Reactor/WebFlux event-loop

~~~java
// KHÔNG LÀM trên reactive event-loop:
writer.save(row).block();
~~~

Nếu sử dụng WebFlux/reactive integration, trả `Mono` cho framework và kết nối acknowledgment/completion theo reactive contract. Với listener JMS synchronous, muốn chờ DB completion thì dùng endpoint sync/đường xử lý phù hợp hoặc một boundary được thiết kế rõ; không ngẫu nhiên `block()` trong mọi callback mà không biết threading model.

### 10.4. Timeout của Reactor không rollback Cassandra

~~~java
Mono<Void> withinBusinessDeadline =
        writer.save(row).timeout(Duration.ofSeconds(4));
~~~

Nếu Reactor phát `TimeoutException` sau 4 giây, downstream work có thể đã tới coordinator. Subscription cancellation và DB rollback là hai khái niệm khác nhau. Mọi replay vẫn phải giữ same `eventId` và cần reconciliation khi outcome không rõ.

## 11. Spring Integration: đặt retry ở đâu trong message flow?

Một Spring Integration flow có thể chứa transformer, filter, router, `DirectChannel`, `ExecutorChannel`, gateway và Cassandra outbound adapter. **Không có một retry policy Cassandra duy nhất bao trùm tất cả chúng**. Khi quyết định retry, phải xác định retry **toàn message**, chỉ **Cassandra call** hay cả **downstream side effects**.

### 11.1. Flow đồng bộ để propagate error

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.cassandra.core.ReactiveCassandraOperations;
import org.springframework.data.cassandra.core.cql.WriteOptions;
import org.springframework.integration.cassandra.dsl.Cassandra;
import org.springframework.integration.cassandra.outbound.CassandraMessageHandler;
import org.springframework.integration.dsl.IntegrationFlow;

@Configuration
public class CassandraEventIntegrationConfig {

    @Bean
    public IntegrationFlow persistOrderEvents(
            ReactiveCassandraOperations operations,
            WriteOptions immutableEventWriteOptions) {

        return IntegrationFlow.from("orderEventsReadyForDb")
                .handle(Cassandra.outboundChannelAdapter(
                                operations, CassandraMessageHandler.Type.INSERT)
                        .writeOptions(immutableEventWriteOptions),
                        endpoint -> endpoint.async(false))
                .get();
    }
}
~~~

Input `orderEventsReadyForDb` phải là Spring Message chứa **`OrderEventRow`** có Cassandra `@Table`/`@PrimaryKey`, không phải raw JSON String. Với một `DirectChannel` và handler `async(false)`, Cassandra exception có thể truyền về thread gửi message.

**Lưu ý:** đây là flow ghi một chiều, không trả `CassandraWriteResult` cho upstream như outbound gateway; do đó không dựa vào `replyChannel` để quyết định một write có thành công. Thành công/lỗi phải được quan sát theo endpoint completion/exception và policy nguồn.

### 11.2. Transform JSON hoặc business event trước khi ghi

~~~java
@Bean
public IntegrationFlow mappedOrderEvents(
        ReactiveCassandraOperations operations,
        WriteOptions immutableEventWriteOptions,
        OrderEventMapper mapper) {

    return IntegrationFlow.from("validatedDomainOrderEvents")
            .transform(OrderPaidEvent.class, mapper::toRow)
            .handle(Cassandra.outboundChannelAdapter(
                            operations, CassandraMessageHandler.Type.INSERT)
                    .writeOptions(immutableEventWriteOptions),
                    endpoint -> endpoint.async(false))
            .get();
}
~~~

Đây là **đường thay thế** mục 11.1 (đầu vào là DTO thay vì entity), không nên đăng ký hai flows cùng nhận một channel rồi kỳ vọng mỗi event chỉ được ghi một lần. `OrderEventMapper` và `OrderPaidEvent` là domain component do ứng dụng định nghĩa. Mapper phải:

- Validate eventId/tenantId/orderId/version.
- Bảo toàn eventId và dữ liệu immutable qua retry.
- Chuẩn hóa timestamp theo contract (UTC, CQL millisecond precision nếu dùng timestamp).
- Tránh sinh random ID hoặc lấy current time làm primary-key component lúc replay.
- Đảm bảo không serialize secrets/headers không cần thiết vào row.

### 11.3. DirectChannel khác ExecutorChannel ở điểm nào?

~~~text
Đường A — đồng bộ:
  JMS listener
   -> DirectChannel
   -> Transformer
   -> Cassandra handler async(false)
   -> Cassandra completion/exception
   -> listener xử lý commit/rollback

Đường B — bất đồng bộ:
  JMS listener
   -> ExecutorChannel / in-memory QueueChannel
   -> listener return/commit theo cấu hình
   -> Cassandra handler chạy sau
   -> Cassandra có thể lỗi nhưng JMS đã commit
~~~

Trong đường B, `errorChannel` có thể nhận error message, nhưng **không thể quay ngược thời gian để rollback một JMS commit đã hoàn tất**. Nếu cần async processing bền vững, dùng durable broker/inbox/handoff có cơ chế replay riêng.

### 11.4. Error channel không phải “automatic retry”

Trong Spring Integration, `ErrorMessage` có thể được đưa tới `errorChannel` khi một lỗi được phát/nhận trong messaging infrastructure. Nhưng:

1. Một `errorChannel` được subscribe không tự thực hiện Cassandra retry.
2. Nếu error handler **nuốt exception**, một listener transacted có thể coi callback là success.
3. Nếu handler gọi retry rồi cuối cùng thành công, event có thể được ghi nhiều lần; cần idempotency.
4. Một error channel chỉ nằm trong memory **không phải DLQ bền vững** sau process crash.

Không đặt toàn bộ exception vào một “catch all” rồi `return null` từ transformer, vì sẽ đánh đồng một permanent mapping error với một Cassandra timeout.

### 11.5. Advice và retry không nên áp dụng bừa

Spring Integration có các cơ chế advice/retry cho endpoint phù hợp, nhưng **không phải mọi endpoint đều có cùng semantics**. Nếu một retry advice bọc toàn bộ handler, hãy biết chính xác nó retry:

- Chỉ database operation hay cả mapper/validator?
- Có lặp một HTTP/email call phía trước không?
- Có thể nhận exception đồng bộ từ Cassandra handler không, hay handler đã handoff async?
- Có dùng Spring Retry `RetryContext` và `RecoveryCallback` cùng broker redelivery không?

Với Cassandra handler async mặc định, một advice đồng bộ không đợi publisher completion có thể **không nhìn thấy lỗi** phát ra sau khi handler return. Chọn sync boundary hoặc reactive pipeline đã kết nối error signal/ack callback rõ ràng.

## 12. JMS redelivery: khi retry có thể khiến source giao cùng message hai lần

### 12.1. Một listener có session transacted

Ví dụ kiến trúc:

~~~mermaid
sequenceDiagram
    participant JMS as JMS Broker
    participant L as Message-driven listener
    participant SI as DirectChannel / Cassandra handler sync
    participant DB as Cassandra
    JMS->>L: Deliver OrderPaid evt-9001
    L->>SI: Send Message<OrderEventRow>
    SI->>DB: INSERT evt-9001 (LOCAL_QUORUM)
    alt Cassandra success
        DB-->>SI: Success
        SI-->>L: Handler returns
        L-->>JMS: Session commit
    else Cassandra unavailable/timeout
        DB-->>SI: Exception
        SI-->>L: Exception propagated
        L-->>JMS: Session rollback
        JMS->>L: Redelivery sau delay theo broker policy
    end
~~~

Đây là **mục tiêu kiến trúc** khi listener được cấu hình session transacted, flow đồng bộ và exception thật sự truyền tới container. Không phải Spring Integration tự chọn JMS rollback cho mọi lỗi hoặc mọi cấu hình.

### 12.2. Cửa sổ lỗi thứ nhất: DB đã ghi, JMS chưa commit

~~~text
t0   Broker deliver evt-9001
t1   Cassandra INSERT evt-9001 thành công
t2   JVM crash trước JMS session commit
t3   Broker redeliver evt-9001
t4   Cassandra INSERT lại cùng event_id và payload
~~~

Nếu `event_id` là Cassandra primary key và mutation là immutable upsert, retry có thể không tạo row thứ hai. Nếu consumer đổi event ID, bucket hoặc amount, dữ liệu có thể trùng/sai. Nếu sau insert còn gửi email, email phải có idempotency riêng.

### 12.3. Cửa sổ lỗi thứ hai: JMS commit trước DB completion

~~~text
t0   Broker deliver evt-9001
t1   Listener gửi message vào ExecutorChannel
t2   Listener return, JMS commit
t3   Worker thực hiện Cassandra INSERT
t4   Cassandra WriteTimeoutException
t5   Broker không còn trách nhiệm tự redeliver message đã commit
~~~

Muốn chạy async mà vẫn không mất công việc, cần **durable handoff**: lưu một record vào queue/inbox bền vững trước commit, rồi worker retry Cassandra sau; hoặc có recovery process từ broker/source-of-truth độc lập.

### 12.4. Chọn delayed retry thay vì retry nóng trong listener

Nếu Cassandra mất quorum trong vài phút, việc retry liên tục trong JMS listener chỉ giữ threads bận và tăng áp lực lên cluster. Có thể:

- Cho exception propagate để broker redelivery theo **delay/backoff** được cấu hình.
- Dùng retry queue/destination theo tầng thời gian, với max deliveries.
- Chuyển sự kiện permanent lỗi vào DLQ/quarantine.
- Thêm alert về queue depth, oldest message age và retry attempt.

Không phải broker nào cũng hỗ trợ cùng một cấu hình redelivery; `JMSXDeliveryCount` và DLQ semantics phụ thuộc provider/container. Kiểm thử trên broker sử dụng thực tế thay vì giả định hành vi.

### 12.5. JMS transaction không bao trùm Cassandra

`sessionTransacted=true` (khi được dùng trong listener container phù hợp) chỉ điều khiển transaction phía JMS session. Nó không biến Cassandra write thành một phần của transaction hai pha. Cassandra không tham gia một XA commit chung theo kiểu RDBMS/JMS XA trong flow bình thường. Vì vậy **idempotent replay vẫn bắt buộc** ngay cả khi có synchronous error propagation.

## 13. Kafka retry, offset commit và consumer liveness

Kafka record key/partition/offset chỉ định vị trí trong broker log, không tự tạo Cassandra primary key hoặc transaction.

### 13.1. Commit offset sau database success

~~~text
Kafka poll record offset=120, eventId=evt-9001
    -> validate + Cassandra write
    -> write completion được quan sát
    -> commit/ack offset theo consumer/container policy
~~~

Đây là một policy thường dùng để giảm nguy cơ mất data khi downstream lỗi. Nếu JVM crash **sau Cassandra success nhưng trước offset commit**, Kafka vẫn có thể replay offset 120; eventId/primary key phải ổn định.

### 13.2. Chạy async mà commit offset quá sớm

~~~text
poll offset=120
    -> gửi vào ExecutorChannel
    -> Kafka offset commit
    -> Cassandra write chạy trong executor
    -> driver timeout
    -> offset 120 đã được commit; tự replay không còn được đảm bảo
~~~

Không khẳng định Kafka transactions hoặc exactly-once producer semantics tự bao trùm một Cassandra mutation. Kafka transaction chỉ quản lý các resources/protocol được hỗ trợ; Cassandra không tự gia nhập giao dịch Kafka.

### 13.3. Retry topics so với retry ngay trong poll loop

Một số Kafka frameworks hỗ trợ error handler, seek/replay, retry topics và dead-letter topics. Chọn theo yêu cầu **ordering và liveness**:

- Retry ngay trong consumer callback có thể giữ partition bị chặn lâu, ảnh hưởng poll/consumer-group membership.
- Retry topic cho phép delay bền vững nhưng có thể thay đổi ordering giữa events cùng aggregate nếu không thiết kế cẩn thận.
- DLQ giúp cách ly poisoned record; replay sau sửa lỗi phải giữ eventId.
- Với business state yêu cầu ordering, dùng `aggregateVersion`/conditional writes hoặc serial processing theo key, không chỉ dựa vào số retry.

### 13.4. Kafka key khác Cassandra partition key

Kafka key `tenant42:ORD-9001` có thể giữ các events của order trong một Kafka partition, nhưng Cassandra token/replica placement được tính từ **CQL partition key**. Mọi phép hash/sharding ở consumer phải ổn định qua retries, deploys và backfill. Không lấy offset/consumer-assignment như một phần Cassandra row key nếu nó thay đổi theo replay topology.

## 14. LWT, CAS và kết quả applied=false

Một số event không chỉ cần insert lịch sử mà phải **cập nhật current state theo version**. Khi hai Kafka/JMS events có thể đến sai thứ tự, việc dùng regular `UPDATE` cùng `LOCAL_QUORUM` không tự ngăn event version thấp ghi đè state version cao.

### 14.1. Ví dụ bảng current state

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_state (
    order_id text PRIMARY KEY,
    version bigint,
    state text,
    last_event_id text
);
~~~

Một compare-and-set:

~~~sql
UPDATE shop_integration.order_state
SET version = ?, state = ?, last_event_id = ?
WHERE order_id = ?
IF version = ?;
~~~

LWT trong Cassandra sử dụng **serial consistency** (`SERIAL`/`LOCAL_SERIAL`) và regular consistency level cho pha liên quan. Nó có chi phí lớn hơn regular write và nên dùng khi business invariant thực sự đòi compare-and-set.

### 14.2. Đọc applied result

~~~java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement conditional = SimpleStatement.newInstance(
        "UPDATE shop_integration.order_state "
        + "SET version = ?, state = ?, last_event_id = ? "
        + "WHERE order_id = ? IF version = ?",
        3L, "SHIPPED", "evt-9003", "ORD-9001", 2L)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .setSerialConsistencyLevel(DefaultConsistencyLevel.LOCAL_SERIAL);

var result = session.execute(conditional);
boolean applied = result.wasApplied();
~~~

Nếu `applied=false`, server có thể đã trả một **business result hợp lệ**: stored version không bằng 2. Đừng retry mù quáng như transport error.

### 14.3. Ba cách diễn giải

| Kết quả | Diễn giải | Hướng xử lý |
|---|---|---|
| `applied=true` | Conditional mutation đã được áp | Xác nhận operation theo policy |
| `applied=false`, stored version=3 và same event ID | Có thể là replay đã applied trước đó | Reconcile và coi duplicate hợp lệ nếu payload/version khớp |
| `applied=false`, stored version mới hơn hoặc khác event ID | Conflicting/out-of-order state update | Phân loại domain conflict, không retry nóng |
| Timeout trong LWT | Chưa rõ pha/condition đã hoàn tất chưa | Read-back/reconcile theo key + version; retry có kiểm soát |

**Không** dùng `Cassandra.outboundChannelAdapter(...)` một chiều rồi suy `send(true)` tương đương `wasApplied()==true`. Khi cần LWT result, dùng driver API hoặc một outbound gateway/service có reply contract phù hợp.

### 14.4. LWT không giải quyết atomicity với broker

Nếu LWT đã applied nhưng JVM crash trước JMS commit, cùng event redeliver. Lần sau conditional `IF version=2` có thể trả false vì stored version đã là 3. Ứng dụng phải phát hiện **đã hoàn tất cùng event ID** chứ không coi false là “chắc chắn thất bại” để gửi lại vô hạn.

## 15. Batch và counter: retry đặc biệt nguy hiểm

### 15.1. Logged batch không phải transaction SQL

~~~sql
BEGIN BATCH
    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9004', 'ORD-9001', 'OrderPaid', '{}');

    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9005', 'ORD-9002', 'OrderPaid', '{}');
APPLY BATCH;
~~~

Với multi-partition **LOGGED** batch, Cassandra dùng batchlog để hỗ trợ hoàn tất mutations sau coordinator failure. Tuy nhiên, các partitions có thể **hiển thị không đồng thời**, không có snapshot isolation xuyên partitions. Khi caller timeout, một hoặc nhiều mutations có thể đã được áp dụng, hoặc Cassandra có thể đang replay batchlog.

`WriteTimeoutException` có `WriteType.BATCH_LOG` là trường hợp đặc biệt `DefaultRetryPolicy` cân nhắc một retry nếu request idempotent. **Không vì thế mà bật retry mọi multi-partition batch**: cần đánh giá từng mutation, batch size và timeout budget.

### 15.2. UNLOGGED batch có thể áp dụng một phần

~~~sql
BEGIN UNLOGGED BATCH
    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9006', 'ORD-9006', 'OrderPaid', '{}');

    INSERT INTO shop_integration.order_event
        (event_id, order_id, event_type, payload_json)
    VALUES ('evt-9007', 'ORD-9007', 'OrderPaid', '{}');
APPLY BATCH;
~~~

Với nhiều partitions, UNLOGGED batch không dùng batchlog để bảo đảm hoàn tất tất cả khi coordinator lỗi. Nếu mutations độc lập, **individual async writes có concurrency cap** thường là lựa chọn tốt hơn một batch lớn chỉ để tăng throughput.

### 15.3. Counter update không an toàn khi replay

~~~sql
CREATE TABLE IF NOT EXISTS shop_integration.order_counters (
    order_id text PRIMARY KEY,
    event_count counter
);

UPDATE shop_integration.order_counters
SET event_count = event_count + 1
WHERE order_id = 'ORD-9001';
~~~

Nếu lần `+1` đầu **đã được Cassandra áp dụng** nhưng response bị mất, retry có thể tăng thành `+2`. Vì vậy counter increment thường **không idempotent**. Không đặt `setIdempotent(true)` hoặc dùng classifier mục 10 cho nó.

Nếu cần số lượng events chính xác có khả năng phục hồi, có thể:

1. Lưu event log với stable event IDs.
2. Deduplicate theo event ID trong một projection/inbox được thiết kế.
3. Cập nhật counter/state theo protocol đã được kiểm chứng.
4. Có cơ chế recompute/reconcile từ event log.

### 15.4. TTL, timestamp và partial update

Ngay cả một regular `INSERT` cùng key có thể không tương đương sau retry nếu:

- Sử dụng TTL tính lại, kéo dài thời gian tồn tại.
- Sử dụng timestamp mới, thay conflict resolution khi có concurrent writes.
- Bind `NULL` thay vì `UNSET` trong partial update, làm tombstone/xóa dữ liệu cũ.
- Đọc event metadata thay đổi theo mỗi attempt.

**Đừng nhầm** “cùng primary key” với “kết quả business bất biến trong mọi điều kiện”. Idempotency phải được review trên **full mutation + side effects + concurrent writes**.

## 16. Reconciliation: xử lý kết quả không chắc chắn một cách có chứng cứ

Retry hữu ích với một số lỗi transient, nhưng **đọc lại/truy vết trạng thái** có thể cần thiết khi caller không biết Cassandra đã áp dụng mutation hay chưa.

### 16.1. Một mẫu dữ liệu reconciliation

~~~json
{
  "eventId": "evt-9001",
  "orderId": "ORD-9001",
  "eventType": "OrderPaid",
  "schemaVersion": 1,
  "payloadHash": "sha256-of-canonical-payload",
  "occurredAt": "2026-11-23T03:00:00Z"
}
~~~

`payloadHash` trong ví dụ là placeholder **minh họa trường**; production phải tính hash thực của canonical payload, chọn algorithm/encoding ổn định và bảo vệ collision/domain boundaries nếu dùng nó như chứng cứ toàn vẹn.

Đối với bảng `order_event(event_id PRIMARY KEY, ...)`, service có thể đọc theo `event_id` sau timeout khi cluster ổn định:

~~~sql
SELECT event_id, order_id, event_type, payload_json
FROM shop_integration.order_event
WHERE event_id = 'evt-9001';
~~~

### 16.2. Các trạng thái reconciliation

| Kết quả đọc lại | Có thể kết luận? | Hành động gợi ý |
|---|---|---|
| Row có, same event ID + same canonical payload | Write có thể đã hoàn tất hoặc duplicate hợp lệ | Đánh dấu processed theo business invariant |
| Row có, same ID nhưng payload khác | **Conflict**; không coi là duplicate an toàn | Quarantine/alert/điều tra producer |
| Row không thấy nhưng cluster còn stale/read CL yếu | Chưa thể kết luận write chưa xảy ra | Chờ/retry read theo CL, kiểm tra topology |
| Row không thấy khi cluster khỏe, hết reconciliation window | Có khả năng cần replay | Retry theo same event ID/payload nếu idempotent |
| Read cũng timeout/unavailable | Trạng thái vẫn không rõ | Không xác nhận giả; backoff/defer reconciliation |

**Lưu ý quan trọng:** Cassandra eventual consistency và CL ảnh hưởng kết quả read-back. Một read `LOCAL_ONE` ngay sau write `LOCAL_QUORUM` có thể không thoả mọi giả định về visibility trên replica được chọn; thiết kế read/write CL phù hợp, và không dựa vào một lần đọc vội ở DC khác để kết luận âm tính.

### 16.3. Inbox và outbox: chọn một nguồn sự thật

Nếu một business event cần ghi Cassandra lẫn gửi email hoặc cập nhật hệ khác, các bước là **nhiều tài nguyên riêng biệt**. Gợi ý kiến trúc:

- **Durable event inbox** có event ID và trạng thái xử lý, cho phép resume từ bước còn thiếu.
- **Outbox** trong transactional source of truth khi có thể, để phát event ra broker đáng tin cậy.
- **Idempotent downstream handlers** dùng event ID, version hoặc request token.
- **Reconciliation worker** so sánh source/destination và replay có kiểm soát.

Không tạo một “dedup record” ở Cassandra table A rồi ghi table B và cho rằng hai writes có SQL atomic commit. Nếu crash sau A trước B, cần quy trình phục hồi/đối soát để bù bước B còn thiếu.

### 16.4. Late retries và event ordering

Một Kafka `OrderPaid(v2)` có thể đến lại **sau** `OrderCancelled(v3)`. Nếu handler retry `UPDATE current_state='PAID'` mà không version guard, có thể viết lùi trạng thái. Event log immutable có thể cho phép cả hai records theo ID; current-state projection nên kiểm tra `aggregateVersion`/LWT hoặc protocol ordering riêng.

## 17. Deadline và retry budget từ business SLA

Một lỗi transient chỉ đáng retry khi còn **thời gian hợp lý** để hoàn thành và không làm tình trạng cluster xấu hơn. Nếu HTTP client chỉ chờ 4 giây, đừng để Cassandra driver timeout 5 giây rồi service retry thêm ba lần.

### 17.1. Ví dụ phân bổ thời hạn

~~~text
HTTP gateway deadline              5.0 giây
  - deserialize/authorize          0.3 giây (dự trù)
  - app/handler logic              0.3 giây
  - Cassandra request timeout      2.0 giây
  - optional backoff/retry          trong phần budget còn lại
  - response/network buffer        0.5 giây
  - phần dự phòng                  theo thực đo
~~~

Đây là **con số minh họa**, không phải mặc định của framework. Các thời đoạn có thể chồng lấn nếu pipeline asynchronous. Đo traces p95/p99 rồi đặt deadline, số retries và backoff phù hợp use case.

### 17.2. Cân bằng response với trạng thái chưa chắc chắn

Khi write timeout, API không nên luôn trả “đã hủy giao dịch” nếu Cassandra có thể đã ghi. Nếu business cho phép asynchronous reconciliation, có thể trả một trạng thái **accepted/pending** cùng event ID và API status lookup *khi đã có durable handoff đủ bảo đảm*.

**Không được trả 202 Accepted chỉ vì đã đặt message vào một in-memory queue** rồi có thể mất nó khi JVM crash. Trạng thái accepted cần gắn với công việc đã được lưu/bàn giao bền vững theo contract.

### 17.3. Cẩn trọng khi “tăng timeout”

Timeout dài hơn không tăng capacity của Cassandra. Nếu 1.000 messages/s vào mà Cassandra chỉ xử lý ổn định được 600 writes/s, backlog tăng xấp xỉ **400 messages/s**. Khi cho nhiều requests chờ hơn, memory/in-flight connection streams có thể quá tải và p99 tiếp tục tăng.

Đặt ngưỡng:

- Max in-flight Cassandra operations.
- Max retry attempts và backoff.
- Max broker redelivery/DLQ age.
- Max JVM queue depth, batch size và Kafka consumer lag.
- Circuit breaker khi downstream outage kéo dài.
- Business-specific deadline/maximum staleness.

## 18. Backpressure, throttling và speculative execution

### 18.1. Giới hạn concurrency trong Reactor

Với một nguồn `Flux<OrderEventRow>` đã validate, ví dụ giới hạn **tối đa tám writes cùng lúc**:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<OrderEventRow> completed = source.flatMap(
        row -> operations.insert(row).thenReturn(row),
        8);
~~~

Đây là fragment trong một reactive service đã có `source` và `ReactiveCassandraOperations operations`. Nó **không** tạo Spring Integration broker acknowledgment tự động; cần nối completion/error tới source policy. `flatMap` có thể hoàn tất **không theo thứ tự input**, vì vậy với aggregate state cần ordering hãy dùng `concatMap` hoặc version guard, tùy throughput/invariant.

### 18.2. Driver throttling khác broker backpressure

Java Driver 4.x có request throttling, ví dụ `ConcurrencyLimitingRequestThrottler`. Request timeout tiếp tục đếm **kể cả khi request nằm trong throttler queue**. Nếu queue đầy, driver có thể phát `RequestThrottlingException`; thông điệp đúng là ứng dụng đang tạo áp lực vượt mức được phép, không phải “retry ngay thêm mười lần”.

Với driver, nên xem metrics `pool.in-flight`, `pool.available-streams`, số queued requests, failed/timeout counts. Với broker, xem queue depth, consumer lag và oldest message age. Cần **giảm tốc upstream/consumer concurrency**, không chỉ tăng timeout.

### 18.3. Speculative execution là retry song song có chi phí

Java Driver 4.x **tắt speculative execution theo mặc định**. Nếu bật policy này cho idempotent statements, driver có thể gửi một query tới coordinator khác khi attempt đầu chậm.

~~~text
Request SELECT id=evt-9001
 t=0ms   Execute ở coordinator A
 t=100ms Chưa có response -> có thể gửi speculative attempt tới B
 t=120ms B trả trước -> driver trả response cho client
 t=200ms A trả muộn -> response bị bỏ qua
~~~

Trong Cassandra, “cancel attempt A” phía driver **chỉ bỏ qua response**; server không nhất thiết hủy work đã bắt đầu. Do vậy:

- Chỉ bật cho idempotent operations.
- Kiểm soát số speculative attempts và delay.
- Theo dõi orphaned streams/available streams.
- Không dùng để chữa cluster-wide overload hoặc hot partition.
- Mỗi speculative execution có thể có retry policy riêng, làm tăng request amplification.

### 18.4. Một thứ tự xử lý khi cluster quá tải

~~~mermaid
flowchart TD
    A["Timeout tăng + broker backlog"] --> B["Phân loại exception"]
    B --> C{"Unavailable vì thiếu replicas?"}
    C -->|"Có"| D["Sửa node/topology; giữ CL theo contract"]
    C -->|"Không"| E{"Driver/Server timeout?"}
    E -->|"Có"| F["Đo in-flight, p99, hot partitions, compactions"]
    F --> G["Giảm concurrency / throttle producer"]
    G --> H["Backoff và recovery có kiểm soát"]
    D --> H
    E -->|"Không"| I["Kiểm tra contract/codec/authorization"]
    I --> J["Fail fast / quarantine nếu permanent"]
~~~

**Không downgrade consistency tự động** như một lối thoát cho retry storm; điều đó có thể biến failure hiển thị thành dữ liệu stale/conflicting khó phát hiện.

## 19. Quan sát retry: phân biệt lỗi thật với traffic amplification

| Metric/tín hiệu | Nguồn | Cần trả lời |
|---|---|---|
| `UnavailableException` count theo CL | Driver/app | Có thiếu live replicas để đạt CL? |
| `ReadTimeoutException` / `WriteTimeoutException` | Driver/server | Coordinator timeout hay chỉ client hết deadline? |
| `DriverTimeoutException` count | App/driver | Client deadline kết thúc khi nào? |
| `RetryPolicy` retry count và coordinator switches | Driver metrics/logs | Retry có giúp hay chỉ chuyển load? |
| Request success-after-retry rate | App tracing | Retries có hiệu quả thật không? |
| WriteType trong `WriteTimeoutException` | Driver | SIMPLE, BATCH_LOG hay loại khác? |
| `pool.in-flight` / available streams | Driver | Kết nối đã bão hòa chưa? |
| Read/write p50, p95, p99 | Cassandra/driver | Tail latency hay toàn bộ workload chậm? |
| ClientRequest timeouts/unavailables/failures | Cassandra nodes | Server-side error rate |
| Hot partitions, compaction, pending tasks | Cassandra | Query/model/GC bottleneck? |
| JMS delivery count / queue depth | Broker | Số lần redelivery có tăng? |
| Kafka consumer lag/retry-topic backlog | Kafka | Downstream có làm nhóm consumer tụt lại? |
| Duplicate/conflicting event IDs | Business metrics | Replay có tạo data corruption? |
| Quarantine/DLQ oldest age | Recovery systems | Permanent errors đang tồn lâu? |

### 19.1. Trace một request có đủ thông tin

Ví dụ log **không chứa payload nhạy cảm**:

~~~text
traceId=tr-9138
eventId=evt-9001
operation=order_event_insert
consistency=LOCAL_QUORUM
driverTimeoutMs=3000
attempt=2
elapsedMs=2805
exception=WriteTimeoutException
writeType=SIMPLE
requiredResponses=2
receivedResponses=1
source=jms
sourceAck=NOT_COMMITTED
~~~

`attempt` trên đây phải được định nghĩa rõ (attempt ở driver, service hay broker), tránh ghi một con số mơ hồ. Nếu exception không có `required/received` hoặc lỗi chỉ ở driver client, **đừng tự điền số giả**.

Không dùng `eventId` làm metrics label trên Prometheus cho mỗi event (cardinality quá lớn). EventId/traceId phù hợp logs/traces, còn metrics aggregate theo operation, errorType, service, cluster/DC.

### 19.2. Quy trình điều tra 6 câu hỏi

1. **Lỗi xảy ra ở tầng nào?** Coordinator, driver, Spring gateway, broker hay mapper?
2. **RF, CL và DC topology là gì?** Có đủ live replicas cho CL không?
3. **Request có tới coordinator chưa?** Tìm client/server traces, queue time, network drops.
4. **Operation có idempotent không?** Xem primary key, payload, TTL, timestamp, side effects.
5. **Broker đã commit chưa?** Nếu chưa, có redelivery; nếu đã, recovery dựa vào đâu?
6. **Cần retry hay reconcile?** Với timeout outcome không rõ, không kết luận âm tính.

### 19.3. Cảnh báo nên có

Một số alert có giá trị:

- Timeout/unavailable rate vượt baseline.
- Driver retry/request ratio tăng nhanh nhưng success-after-retry không cải thiện.
- JMS queue depth hoặc Kafka consumer lag liên tục tăng.
- In-flight requests/available streams vượt ngưỡng an toàn.
- Một node hoặc partition có p99 latency bất thường.
- Duplicate/conflicting events tăng hoặc DLQ bị tồn đọng.

Đừng chỉ alert CPU trung bình toàn cluster; một partition/node nóng có thể phá p99 trong khi CPU trung bình vẫn bình thường.

## 20. Bảng xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `UnavailableException` với `LOCAL_QUORUM` | Không đủ live replicas local cho RF/CL | Kiểm tra RF, datacenter, replica health; không tự downgrade CL |
| `UnavailableException` dù còn Cassandra node | Có node nhưng không đủ replicas của partition cần quorum | Đối chiếu token placement/replica sets, RF/CL |
| `ReadTimeoutException` `received>=blockFor` nhưng `dataPresent=false` | Chỉ nhận digest, chưa có actual data | DefaultRetryPolicy có thể retry cùng coordinator một lần |
| `WriteTimeoutException` với SIMPLE | Mutation có thể đã đến replicas | Reconcile, chỉ retry nếu idempotent, không tạo eventId mới |
| `WriteTimeoutException` với BATCH_LOG | Chậm khi ghi batchlog | Điều tra coordinator/batchlog, hiểu default policy cho phép retry có điều kiện |
| `DriverTimeoutException` không có server timeout | Deadline client hết trước coordinator response hoặc queue | Kiểm tra driver throttle queue, network, request timeout, in-flight |
| `RequestThrottlingException` | Driver đã đạt concurrency/queue limit | Giảm producer/consumer concurrency, tránh retry nóng |
| `OverloadedException` tăng cùng backlog | Cassandra coordinator/replicas quá tải | Throttle, backoff/circuit breaker, xử lý hot partitions |
| Retry `InvalidQueryException` vô hạn | Schema/CQL sai hoặc thiếu table | Fail-fast; migration/configuration fix |
| Retry `UnauthorizedException` vô hạn | Cassandra role thiếu quyền | Sửa permissions/secrets, không retry cùng trạng thái |
| Retry counter khiến giá trị tăng gấp đôi | Non-idempotent mutation | Không đánh dấu idempotent, dùng event log/dedup protocol |
| Immutable INSERT nhưng kết quả khác sau retry | Payload/TTL/timestamp thay đổi | Freeze canonical event, kiểm tra concurrent writes |
| LWT `applied=false` nhưng app báo database down | Nhầm business condition với transport error | Đọc row hiện có, so event/version |
| Cassandra write thành công nhưng JMS redeliver | Crash trước JMS commit | Stable primary key, replay idempotent |
| JMS không redeliver sau DB timeout | Listener đã ack/commit trước async error | Sync completion hoặc durable handoff/replay |
| Kafka lag tăng khi retry trong poll callback | Blocking/retry lâu làm consumer chậm | Retry topics/delayed processing, monitor poll liveness |
| `errorChannel` có lỗi nhưng nguồn không retry | Handler error đã được xử lý sau source commit | Rà soát ack boundary và async flow |
| Tăng timeout làm memory tăng | Nhiều requests pending/in-flight | Giảm concurrency, xử lý bottleneck |
| App chỉ đọc `Mono.empty()` khi Cassandra lỗi | Lỗi bị nuốt và chuyển thành not found | Phân biệt empty result với timeout/DataAccessException |
| Gateway `replyTimeout` trước Cassandra completion | Deadline gateway ngắn hơn DB request | Cân đối deadlines và uncertainty semantics |
| `setIdempotent(true)` không có tác dụng | Bỏ kết quả immutable setter | Gán lại statement hoặc dùng builder |
| Custom retry policy làm hạ LOCAL_QUORUM | Dùng consistency downgrading | Quay lại policy an toàn, review business invariants |
| Speculative execution tăng số writes | Bật cho idempotent writes với độ trễ quá thấp | Kiểm tra max-executions/delay, throughput, orphaned streams |
| Driver retry không xảy ra với write timeout | DefaultRetryPolicy cố ý rethrow SIMPLE | Xử lý ở service/broker nếu business idempotent |
| Testing RF=3 trên một node thất bại | Không có đủ replica nodes | Lab một node dùng RF=1; multi-node để test quorum |

### 20.1. Checklist quyết định retry

Trước mỗi quyết định retry hãy trả lời:

1. **Exception class:** `Unavailable`, `WriteTimeout`, `DriverTimeout`, `InvalidQuery` hay lỗi app?
2. **Operation:** SELECT, immutable INSERT, partial UPDATE, LWT, batch hay counter?
3. **Idempotency:** same full PK, values, timestamp/TTL, version, side effects?
4. **Current CL:** có business invariant yêu cầu quorum? Không tự downgrade.
5. **Budget:** còn deadline, attempts, backoff, in-flight capacity?
6. **Source:** JMS/Kafka/HTTP đã acknowledge chưa, có durable replay?
7. **Unknown outcome:** có cần read-back/reconciliation không?
8. **Permanent error:** phải quarantine/alert thay vì retry?

### 20.2. Quy tắc ra quyết định rút gọn

~~~mermaid
flowchart TD
    A["Cassandra operation lỗi"] --> B{"Lỗi contract/authorization/CQL?"}
    B -->|"Có"| P["Fail fast / quarantine"]
    B -->|"Không"| C{"Transient unavailable/timeout?"}
    C -->|"Không"| X["Điều tra lỗi khác"]
    C -->|"Có"| D{"Operation idempotent?"}
    D -->|"Không"| R["Reconcile / domain-specific recovery"]
    D -->|"Có"| E{"Còn retry budget và cluster có capacity?"}
    E -->|"Có"| T["Backoff có jitter, retry có giới hạn"]
    E -->|"Không"| Q["Durable retry queue / reconcile / DLQ"]
    T --> F{"Thành công?"}
    F -->|"Có"| K["Ack nguồn theo policy"]
    F -->|"Chưa"| Q
~~~

**Sơ đồ là phương pháp ra quyết định, không phải thư viện tự động.** Với timeout outcome không chắc, ngay cả một mutation idempotent vẫn cần giám sát/truy vết và có thể cần reconciliation để chứng minh business effect hoàn tất.

## 21. Bài thực hành: kiểm chứng retry unavailable và timeout

**Môi trường:** Java 17+, Spring Integration Cassandra tương thích với Spring Data Cassandra reactive, Java Driver 4.x, Cassandra test cluster, một JMS broker/Kafka cluster test khi cần nguồn thực. Các bài liên quan `RF=3`, quorum và node failure phải dùng **ít nhất ba Cassandra replica nodes thực**, không đủ nếu chỉ có một container.

### Bài A — Phân biệt RF/CL và Unavailable

1. Khởi tạo test cluster ba nodes thuộc một DC `dc1`.
2. Tạo keyspace `shop_integration` với `NetworkTopologyStrategy 'dc1':3`.
3. Chạy một `INSERT` có `LOCAL_QUORUM`, kiểm chứng đủ hai local responses trong điều kiện khỏe.
4. Chủ động tắt **một replica node** trong test; thử `LOCAL_QUORUM`, ghi nhận có thể vẫn thành công.
5. Tắt thêm replica node (chỉ trong test orchestration an toàn), thử lại và quan sát `UnavailableException` hoặc lỗi phù hợp tại thời điểm failure detection.
6. Thu metadata `required/alive` và effective CL từ driver/server.
7. Khôi phục cluster, kiểm tra trạng thái ring/replication trước bài tiếp theo.

**PASS:** giải thích vì sao `required=2, alive=1` là UNAVAILABLE, và vì sao không tự hạ CL để vượt qua lỗi.

### Bài B — Server ReadTimeout và WriteTimeout

1. Trên cluster RF=3 khỏe, cấu hình CL=LOCAL_QUORUM.
2. Dùng network latency/failure injection **trên môi trường test** để làm một vài replicas phản hồi chậm.
3. Chạy read/write với server timeout/test deadline phù hợp và ghi lại exception.
4. Khi có `ReadTimeoutException`, ghi `received`, `blockFor`, `dataPresent`.
5. Khi có `WriteTimeoutException`, ghi `received`, `blockFor`, `writeType`.
6. Query lại theo same primary key sau khi cluster phục hồi.
7. Không cố ép mọi lần thử phải có cùng exception: nếu node bị nhận diện down sớm có thể ra UNAVAILABLE thay vì WRITE_TIMEOUT.

**PASS:** nhận diện coordinator-side timeout khác thiếu replicas ngay từ đầu; không suy một write timeout là DB rollback.

### Bài C — DriverTimeout vs server timeout

1. Đặt `basic.request.timeout = 2 seconds` trong test driver config.
2. Tạo request bị delay hoặc nằm trong driver throttling queue.
3. Quan sát `DriverTimeoutException` khi client deadline hết.
4. So sánh với server-side timeout metrics/logs: có thể server không báo `WRITE_TIMEOUT` tương ứng.
5. Thử per-statement `setTimeout(Duration.ofSeconds(1))` và đọc effective config.
6. Kiểm tra request vẫn có thể đã tới server dù client hết thời gian chờ.

**PASS:** giải thích request deadline bao gồm driver queue/retries; phân biệt client timeout và coordinator timeout.

### Bài D — DefaultRetryPolicy không retry mọi lỗi

1. Dùng `DefaultRetryPolicy` với một immutable SELECT `setIdempotent(true)`.
2. Tạo tình huống `UNAVAILABLE` ở coordinator đầu và quan sát policy có thể thử next node theo query plan.
3. Tạo `READ_TIMEOUT` với `received>=blockFor && !dataPresent`, kiểm chứng rule retry cùng coordinator nếu test environment cho phép.
4. Tạo `WRITE_TIMEOUT` SIMPLE trong test: xác minh driver thường rethrow, không retry vô hạn.
5. Tạo conditional test cho `BATCH_LOG` timeout nếu có multi-node fault injection và quyền quan sát batchlog.
6. Kiểm tra các rule xử lý errors **trước network write** có thể khác callback `RetryPolicy`.

**PASS:** mô tả được các quyết định mặc định theo exception/writeType, không kết luận một setting “maxRetry=1” áp cho mọi lỗi.

### Bài E — Idempotency và retry cùng event ID

1. Tạo bảng `order_event(event_id PRIMARY KEY, ...)`.
2. Gửi `evt-9001` lần đầu với một payload immutable.
3. Mô phỏng response loss/timeout rồi gửi lại **same event ID và values**.
4. Query lại, xác minh chỉ có row theo same PK.
5. Gửi lại same ID nhưng khác `payload_json`, phân loại conflicting duplicate.
6. Tạo counter table test và tăng `+1` hai lần: quan sát non-idempotent effect.
7. Thử TTL viết lại hoặc timestamp thay đổi để giải thích vì sao “cùng key” chưa đủ.

**PASS:** phân biệt CQL idempotence với business idempotence và không bật `setIdempotent(true)` cho counter.

### Bài F — Reactor retryWhen, backoff và circuit breaker

1. Tạo `OrderEventRow` và `ImmutableOrderEventWriter.save(...)` ở mục 10.
2. Dùng test doubles **chỉ cho unit policy** để phát hai `UnavailableException` rồi một success; kiểm tra số attempts và backoff.
3. Với `InvalidQueryException`/mapping error, kiểm tra classifier không retry.
4. Với non-idempotent operation, không dùng classifier `forImmutableEventWrite`.
5. Dùng Reactor `StepVerifier.withVirtualTime` để test retry delay khi môi trường test hỗ trợ.
6. Đặt max concurrency để không phát vô hạn `Mono` cùng lúc.
7. Thử toàn workflow với Cassandra thật để kiểm tra error translation/cause chain.

**PASS:** retry có giới hạn và only for allowed failures, không làm mất error signal, không retry JSON malformed.

### Bài G — Spring Integration và JMS commit boundary

1. Dùng JMS transacted inbound endpoint + `DirectChannel` + Cassandra handler `async(false)`.
2. Gửi `evt-9001` với deterministic primary key.
3. Giả lập Cassandra timeout, xác minh exception propagate tới listener và rollback/redelivery theo broker policy.
4. Cho Cassandra write xong rồi mô phỏng JVM crash trước JMS commit; broker gửi lại same event.
5. Đổi sang `ExecutorChannel` hoặc handler async để thấy listener có thể return/commit trước Cassandra completion.
6. Thiết kế durable handoff/retry queue cho case async.
7. Gửi poisoned JSON/schema event vào DLQ/quarantine thay vì retry nóng.

**PASS:** biết chính xác source ack xảy ra khi nào và vì sao Cassandra+JMS không có atomic commit.

### Bài H — Kafka replay và ordering

1. Producer gửi ba events cùng business order với Kafka key ổn định.
2. Dùng consumer/flow để ghi Cassandra event log theo event ID.
3. Cho Cassandra write thành công nhưng crash trước offset commit, kiểm tra replay không tạo business duplicate.
4. Dùng retry topic/delay test, quan sát một event cũ có thể hoàn tất sau event mới.
5. Bảo vệ current-state projection bằng `aggregateVersion`/LWT.
6. Tách permanent schema error vào dead-letter topic, kiểm tra alert/retention/replay.

**PASS:** không dựa vào Kafka offset làm Cassandra event ID; xử lý redelivery và out-of-order phù hợp.

### Bài I — LWT, batchlog và reconciliation

1. Tạo bảng `order_state` với version.
2. Chạy `UPDATE ... IF version = ?`, đọc `wasApplied()`.
3. Gửi cùng event lần thứ hai, phân biệt `applied=false` duplicate hợp lệ với conflict.
4. Tạo multi-partition logged batch test và quan sát batchlog/failure metrics khi coordinator chậm.
5. Cho client timeout, query lại từng event ID sau cluster recovery.
6. Ghi lại trạng thái: `known success`, `known conflict`, `unknown outcome`, `eventually reconciled`.

**PASS:** không nhầm LWT `applied=false` với driver timeout, không coi batchlog là transaction xuyên JMS/Kafka.

### Bài J — Benchmark khi Cassandra quá tải

1. Đo baseline latency p50/p95/p99 với request rate thấp.
2. Tăng gradually số concurrent events, giữ payload/schema ổn định.
3. Bật `DefaultRetryPolicy` và đếm retry/success-after-retry.
4. Thêm optional service retry giới hạn và đo traffic amplification.
5. So sánh với phương án giảm concurrency/backpressure.
6. Đo driver in-flight/available streams, Cassandra timeouts, Kafka/JMS backlog và hot partitions.
7. Chỉ trên test, thử speculative execution với idempotent SELECT để quan sát thêm request traffic.

**PASS:** chọn concurrency/retry budget dựa trên kết quả đo, không tăng timeout/retry chỉ vì giảm error rate ngắn hạn.

### Ma trận kiểm chứng cuối bài

| Nhóm | Kết quả PASS |
|---|---|
| CL/RF | Hiểu `LOCAL_QUORUM` cần hai local replicas khi RF=3 |
| Unavailable | Metadata `required/alive` được diễn giải đúng |
| ReadTimeout | Kiểm tra `received/blockFor/dataPresent` |
| WriteTimeout | Phân biệt `SIMPLE` và `BATCH_LOG` retry rules |
| DriverTimeout | Client deadline không đồng nghĩa server rollback |
| Driver policy | DefaultRetryPolicy retry chọn lọc, không downgrade CL |
| Idempotency | Cùng event ID/full PK/values qua replay |
| Reactor | Retry.backoff có max attempts, filter và jitter |
| Spring Integration | Error propagation theo sync/async boundary |
| JMS | Commit/rollback và redelivery được kiểm chứng với broker thật |
| Kafka | Offset/replay không tạo side effect trùng |
| LWT | `applied=false` khác transport error |
| Batch/counter | Không retry mù non-idempotent mutations |
| Reconciliation | Unknown outcome có kế hoạch xác minh/read-back |
| Observability | Đo p99, retries, backlog và in-flight |
| Recovery | Có DLQ/quarantine/durable handoff phù hợp |

**Giới hạn kiểm thử:** unit mocks chỉ kiểm tra classifier/flow invocation; không chứng minh replica placement, quorum, coordinator timeout, batchlog replay hay network response loss. Cần Cassandra multi-node test cluster và broker phù hợp để kiểm thử những hành vi này.

## 22. Câu hỏi tự đánh giá

1. Vì sao retry một `WriteTimeoutException` có thể làm mutation được thực hiện thêm một lần?
2. `UnavailableException` khác `WriteTimeoutException` về thời điểm coordinator nhận biết lỗi như thế nào?
3. Metadata `required=2, alive=1` với `LOCAL_QUORUM` thể hiện điều gì?
4. Cassandra RF=3 và CL=LOCAL_QUORUM cần bao nhiêu replica responses trong một DC?
5. `LOCAL_QUORUM` ở dc1 có bảo đảm read `LOCAL_QUORUM` tại dc2 thấy ngay write mới không?
6. `ReadTimeoutException` `received>=blockFor` nhưng `dataPresent=false` có ý nghĩa gì?
7. Vì sao `DefaultRetryPolicy` có thể retry một READ_TIMEOUT trường hợp đủ digest responses nhưng chưa có data?
8. `WriteType.BATCH_LOG` khác `WriteType.SIMPLE` thế nào đối với default retry?
9. `DefaultRetryPolicy` có tự retry mọi `WRITE_TIMEOUT` không?
10. Driver retry policy có được gọi cho mọi lỗi xảy ra trước khi bytes được ghi lên network không?
11. `DriverTimeoutException` xuất hiện ở driver hay coordinator?
12. Driver request timeout 3 giây có được cấp lại 3 giây cho mỗi retry không?
13. Request đang nằm trong driver throttler queue có thể `DriverTimeoutException` không?
14. `RequestThrottlingException` gợi ý phải tăng retry count hay giảm áp lực?
15. `ConsistencyDowngradingRetryPolicy` có nguy cơ phá invariants read-after-write như thế nào?
16. Vì sao không nên tự hạ `LOCAL_QUORUM` thành `ONE` khi chỉ còn một replica?
17. `SERIAL`/`LOCAL_SERIAL` được dùng trong operation Cassandra nào?
18. `applied=false` của LWT có phải exception không?
19. LWT timeout có cho phép khẳng định condition chưa applied không?
20. Cassandra `INSERT` cùng primary key nhưng payload khác có thể tạo vấn đề gì?
21. `setIdempotent(true)` có tạo database unique constraint hoặc dedup inbox không?
22. Vì sao `list = ['x'] + list` không idempotent?
23. Vì sao counter increment `+1` không an toàn khi retry mù?
24. Một batch chứa immutable INSERT và counter có thể đánh dấu toàn batch idempotent không?
25. TTL tính lại mỗi lần retry có thể thay đổi kết quả nghiệp vụ không?
26. Vì sao nên dùng `eventId` cố định và payload canonical để reconcile timeout?
27. `Retry.backoff(2, ...)` trong Reactor có nghĩa hai attempts tổng hay hai retries?
28. Vì sao `Mono.defer(...)` hữu ích khi cần mỗi retry tạo lại publisher?
29. Khi dùng Spring Data, exception gốc có thể bị bao trong `DataAccessException` như thế nào?
30. Tại sao classifier retry nên xem cause chain thay vì tìm substring `"timeout"`?
31. Tại sao classifier của immutable INSERT không được dùng nguyên cho LWT hoặc counter?
32. `WriteOptions.timeout(...)` và `WriteOptions.ttl(...)` có giống nhau không?
33. Java Driver `Statement.setTimeout(...)` có sửa Cassandra server `write_request_timeout` không?
34. Vì sao `CassandraMessageHandler` async mặc định ảnh hưởng đến JMS commit?
35. `DirectChannel` + handler `async(false)` có tạo transaction chung Cassandra/JMS không?
36. Vì sao `errorChannel` không thay thế broker DLQ?
37. Khi Cassandra ghi xong nhưng JMS commit thất bại, điều gì xảy ra?
38. Khi JMS commit trước Cassandra async failure, nguồn có tự redeliver không?
39. Kafka offset commit có đồng bộ atomic với Cassandra INSERT không?
40. Retry topic Kafka có thể ảnh hưởng ordering của cùng order ra sao?
41. `ExecutorChannel` in-memory có phải durable queue sau JVM crash không?
42. Vì sao tăng driver timeout có thể làm số requests in-flight tăng mà không tăng capacity?
43. Speculative execution có thật sự hủy remote Cassandra mutation đã gửi không?
44. Đâu là các metric cần theo dõi khi retry storm xảy ra?
45. Khi read-back sau timeout không thấy row tại `LOCAL_ONE`, ta có thể kết luận chắc chắn write chưa xảy ra không?
46. Reconciliation phân biệt duplicate hợp lệ và conflicting event ID ra sao?
47. Đâu là khác biệt giữa transient database failure và permanent JSON/codec error?
48. Tại sao không dùng `eventId` làm một metric label cho mọi sự kiện?
49. Muốn test `LOCAL_QUORUM` với RF=3 khi mất một replica, cần môi trường Cassandra thế nào?
50. Trình bày một chiến lược retry end-to-end với driver policy, service attempts, JMS/Kafka redelivery, DLQ và reconciliation.

## 23. Tài liệu tham khảo chính thức

- [Apache Cassandra Java Driver 4.19 — Retries](https://apache.github.io/cassandra-java-driver/4.19.0/core/retries/): `DefaultRetryPolicy`, `ConsistencyDowngradingRetryPolicy`, các trường hợp UNAVAILABLE/READ_TIMEOUT/WRITE_TIMEOUT, request aborted và retry verdicts.
- [Apache Cassandra Java Driver 4.19 — Idempotence](https://apache.github.io/cassandra-java-driver/4.19.0/core/idempotence/): `basic.request.default-idempotence`, `setIdempotent` và điều kiện retry/speculative execution an toàn.
- [Apache Cassandra Java Driver 4.19 — Configuration](https://apache.github.io/cassandra-java-driver/4.19.0/core/configuration/): `basic.request.timeout`, `basic.request.consistency`, execution profiles và effective config.
- [Apache Cassandra Java Driver 4.19 — Speculative Execution](https://apache.github.io/cassandra-java-driver/4.19.0/core/speculative_execution/): thêm attempts, idempotency, stream ID pressure và giới hạn cancellation.
- [Apache Cassandra Java Driver 4.19 — Request Throttling](https://apache.github.io/cassandra-java-driver/4.19.0/core/throttling/): giới hạn concurrent requests/queue, `RequestThrottlingException` và request deadline.
- [Apache Cassandra Java Driver 4.19 — Upgrade Guide](https://apache.github.io/cassandra-java-driver/4.19.0/upgrade-README/): toàn request timeout trong driver 4.x và `RetryVerdict` API từ 4.10.
- [Apache Cassandra Java Driver API — RetryPolicy](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/retry/RetryPolicy.html): callback `onUnavailableVerdict`/`onReadTimeoutVerdict`/`onWriteTimeoutVerdict` và tham số `required/received/blockFor/writeType`.
- [Apache Cassandra Java Driver API — DriverTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/DriverTimeoutException.html): client-side deadline.
- [Apache Cassandra Java Driver API — UnavailableException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/UnavailableException.html): coordinator-side unavailable.
- [Apache Cassandra Java Driver API — WriteTimeoutException](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/servererrors/WriteTimeoutException.html): coordinator-side write timeout và WriteType.
- [Apache Cassandra — Tunable Consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html): RF, read/write CL, coordinator và quorum reasoning.
- [Apache Cassandra — Monitoring and Metrics](https://cassandra.apache.org/doc/stable/cassandra/managing/operating/metrics.html): ClientRequest timeouts/unavailables/failures và read/write latency.
- [Spring Data Cassandra — Reactive Cassandra](https://docs.spring.io/spring-data/cassandra/reference/cassandra/reactive-cassandra.html): `ReactiveCassandraOperations`, publisher lifecycle và reactive database access.
- [Spring Data Cassandra API — WriteOptions](https://docs.spring.io/spring-data/cassandra/docs/current/api/org/springframework/data/cassandra/core/cql/WriteOptions.html): per-operation consistency, timeout, idempotence, write TTL.
- [Spring Integration — Apache Cassandra Support](https://docs.spring.io/spring-integration/reference/cassandra.html): Cassandra outbound channel adapter/gateway, `CassandraMessageHandler` và `setAsync(false)`.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): `ErrorMessage`, `errorChannel` và synchronous/asynchronous error propagation.
- [Spring Integration — JMS Support](https://docs.spring.io/spring-integration/reference/jms.html): JMS inbound endpoints, transactions và redelivery considerations.
- [Spring Integration — Kafka Support](https://docs.spring.io/spring-integration/reference/kafka.html): inbound/outbound integration và Kafka consumer considerations.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html#_retrying): `retryWhen`, backoff và error handling.

**Ghi nhớ:** `UNAVAILABLE`, `READ/WRITE_TIMEOUT` và `DRIVER_TIMEOUT` không phải một lỗi duy nhất. **DefaultRetryPolicy** Java Driver 4.x chỉ retry chọn lọc và **không tự retry mọi WRITE_TIMEOUT**; cờ **`idempotent`** phải phản ánh đúng nghiệp vụ. **Timeout không chứng minh Cassandra chưa ghi.** Trong Spring Integration, xác định rõ handler sync/async, nguồn JMS/Kafka acknowledge khi nào và retry thuộc tầng nào. Với immutable events, dùng stable `eventId`, bounded retries, backoff, backpressure và reconciliation; với LWT, batch và counter phải xử lý semantics riêng. Đừng tự downgrade consistency hoặc tạo retry storm để che sự cố Cassandra.







