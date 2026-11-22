# Cờ idempotent và trách nhiệm xác định ngữ nghĩa thao tác

> **Chương:** Retry và lỗi Java  
> **Module:** DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA  
> **Ngữ cảnh:** Apache Cassandra là cơ sở dữ liệu wide-column phân tán. Khi Java gọi CQL, cần hiểu partition key, replication, consistency level, quy tắc ghi last-write-wins, compaction, repair, timeout và đường đi qua coordinator/replica.  
> **Trọng tâm:** Cờ **idempotent** của Apache Cassandra Java Driver 4.x và trách nhiệm của lập trình viên khi retry hay speculative execution.

## 1. Tình huống mở đầu: sau timeout, retry có tạo hai tác dụng?

Giả sử dịch vụ Java gửi sự kiện OrderCreated vào Cassandra. Driver nhận **WriteTimeout**, nhưng không biết mutation đã được áp dụng ở bao nhiêu replica. Có ba khả năng: một phần replica đã ghi, server đã hoàn tất nhưng phản hồi thất lạc, hoặc request chưa hoàn thành. **Không được suy từ timeout ra “chưa ghi”.**

Nếu Java tạo UUID mới rồi gửi lại, một logical event có thể thành hai row. Nếu retry phép **counter increment**, counter có thể tăng hai lần. Với **INSERT IF NOT EXISTS**, lần đầu có thể true nhưng mất phản hồi; lần retry trả **[applied]=false** dù row do chính request đầu tạo.

Phải phân biệt:

1. **Idempotency của CQL:** cùng một thao tác được áp dụng lại có giữ trạng thái dữ liệu theo bất biến yêu cầu?
2. **Cờ idempotent của Java Driver:** metadata cho các policy như retry/speculative execution; cờ **không thay đổi bản chất** thao tác CQL.
3. **Idempotency nghiệp vụ:** cùng HTTP request tạo order, thu tiền, phát event hoặc gửi email không gây tác dụng lặp trái hợp đồng.

**Trách nhiệm xác định tính idempotent thuộc người thiết kế dữ liệu, API và nghiệp vụ, không thuộc cơ chế tự suy luận của driver.**

### Mục tiêu

- Hiểu điều kiện idempotent trong Cassandra và vai trò của **setIdempotent(true/false)**.
- Phân loại SELECT, INSERT, UPDATE, DELETE, counter, collection, LWT, TTL, timestamp, batch.
- Chọn cờ theo ngữ nghĩa, không theo mong muốn “đỡ timeout”.
- Thiết kế request ID ổn định, retry budget, backoff và đối soát sau outcome không rõ.
- Sử dụng Java Driver 4.x với **BoundStatement**, **PreparedStatement**, consistency level và async execution.
- Kiểm thử dữ liệu cuối, duplicate side effects, retry/faults và điều kiện cluster RF/DC.
- Liên hệ hot partition, compaction, repair và observability khi tải tăng.

> **Phiên bản:** Ví dụ dùng Java Driver **4.x** trong namespace **com.datastax.oss.driver.api**. Tên option, policy và API cụ thể cần đối chiếu phiên bản Cassandra/driver/JDK đang sử dụng. Các bài thực hành chỉ chạy trên cluster lab/staging.

## 2. Định nghĩa idempotency ở ba tầng

Một phép biến đổi trạng thái f được coi là idempotent nếu:

\[
f(f(s)) = f(s)
\]

Nói đơn giản: thực hiện cùng phép biến đổi hai lần không tạo trạng thái cuối khác so với thực hiện một lần.

~~~text
status := "PAID"
status := "PAID"
=> Xét riêng trường status, trạng thái vẫn là "PAID".

total := total + 1
total := total + 1
=> Counter tăng 2, không idempotent.

events := events + ["paid"]
events := events + ["paid"]
=> List có thể nhận hai phần tử, không idempotent.
~~~

Trong Cassandra, cần xét thêm **timestamp, TTL, tombstone, replica, ghi cạnh tranh và đường đọc**. Hai lần ghi cùng giá trị hiển thị có thể mang timestamp khác nhau và ảnh hưởng cách Cassandra phân giải với ghi khác.

| Tầng | Câu hỏi | Ví dụ |
|---|---|---|
| **Storage state** | Mutation lặp lại có giữ dữ liệu phù hợp với bất biến? | Gán status cố định trên cùng primary key |
| **Request result** | Lần thử lại có trả cùng kết quả? | LWT IF NOT EXISTS: true rồi false |
| **Business workflow** | Toàn bộ yêu cầu có đúng một hiệu ứng theo hợp đồng? | Tạo order và phát event/sending email |

### 2.1. Idempotency key phải thuộc logical request

Một khách hàng bấm “Đặt hàng” rồi gateway retry sau timeout. Nếu mỗi attempt sinh một **orderId mới**, các INSERT có thể đều thành công trên những partition khác nhau. Cờ idempotent của mỗi statement không cứu được tình huống này.

Thiết kế nên cấp **idempotency key** trước attempt đầu và giữ nguyên qua tất cả retry. Phạm vi key (tenant, loại thao tác, thời hạn, fingerprint payload) phải được xác định rõ. Một key trùng nhưng nội dung yêu cầu khác phải được báo conflict, không im lặng coi là cùng request.

### 2.2. Retry giống nhau về câu chữ nhưng khác về thời điểm

Giả sử Java tạo cùng CQL INSERT nhưng timestamp được sinh lại mỗi attempt. Xét ba mutation:

~~~text
T1: Request A đặt status=PAID với timestamp 100.
T2: Request B đặt status=REFUNDED với timestamp 110.
T3: Retry A đặt status=PAID với timestamp 120.

Kết quả có thể quay về PAID dù request A chỉ "thử lại".
~~~

Đó là nguy cơ **last-write-wins**. Một phép gán nhìn có vẻ idempotent riêng lẻ chưa chắc retry an toàn khi có writer khác. Có thể cần **revision/CAS bằng LWT**, timestamp xác định trước, idempotency key và các quy tắc hội tụ; không dùng timestamp client tùy tiện để giả lập transaction.

## 3. Ý nghĩa thật của setIdempotent trong Java Driver 4.x

~~~java
BoundStatement safe = prepared.bind(...)
    .setIdempotent(true);

BoundStatement unsafe = prepared.bind(...)
    .setIdempotent(false);
~~~

Đây là **metadata trên statement**. Driver dùng metadata này trong các chính sách thực thi phù hợp, nhất là:

- **Retry policy:** có thể thử lại lỗi đủ điều kiện trên một statement đã xác nhận idempotent. Loại lỗi, số lần thử và kết quả còn phụ thuộc policy/version.
- **Speculative execution:** nếu được cấu hình, driver có thể phát execution khác khi attempt trước chưa hoàn tất để giảm tail latency; thao tác không idempotent không nên được chạy lặp theo cách đó.
- **Review/observability:** giúp nhóm lập trình thấy ý định, nhưng không phải bằng chứng an toàn nghiệp vụ.

Cờ **không**:

- Biến counter increment, list append thành phép gán.
- Thêm IF NOT EXISTS hoặc transaction vào CQL.
- Bảo đảm mọi lỗi được retry hoặc retry thành công.
- Tự xác định timestamp, TTL, requestId hay business fingerprint.
- Bảo đảm timeout có nghĩa server chưa thực thi.
- Thay consistency level, replication factor, serial CL của LWT.
- Kiểm soát email, thanh toán, broker hoặc side effect ngoài Cassandra.
- Chữa hot partition, compaction backlog, disk saturation.

### 3.1. Bốn trường hợp cần ghi nhớ

| Ngữ nghĩa thật | Cờ driver | Hệ quả |
|---|---|---|
| Safe để chạy lại | **true** | Driver được phép xem xét retry/speculation theo policy |
| Unsafe để chạy lại | **false** | Bảo vệ khỏi các kiểu chạy lặp không an toàn mà policy kiểm tra |
| Unsafe nhưng gắn true | **true sai** | Có thể nhân side effect hoặc ghi đè trạng thái mới |
| Safe nhưng gắn false | **false bảo thủ** | Ít cơ hội retry/speculation, nhưng không tự làm sai dữ liệu |

Không đặt default true cho mọi statement chỉ vì muốn “ít lỗi hơn”. Nếu chưa xác định được an toàn, chọn **bảo thủ** rồi review.

### 3.2. BoundStatement immutable và lỗi bỏ giá trị setter

Trong Java Driver 4.x, setter trên statement thường trả về statement mới.

~~~java
BoundStatement original = prepared.bind(...);
original.setIdempotent(true);  // Bỏ kết quả, không sửa original.
session.execute(original);     // Không dùng statement đã đặt true.
~~~

Đúng:

~~~java
BoundStatement request = prepared.bind(...)
    .setIdempotent(true)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);

session.execute(request);
~~~

Lưu ý tương tự với **setSerialConsistencyLevel**, **setPageSize**, **setExecutionProfileName** và các thuộc tính khác.

### 3.3. Mặc định và execution profile

Một dạng cấu hình HOCON của Java Driver 4.x:

~~~hocon
datastax-java-driver {
  basic {
    request {
      consistency = LOCAL_QUORUM
      timeout = 2 seconds
      default-idempotence = false
    }
  }
}
~~~

Các giá trị là **minh họa**; phải kiểm tra configuration reference/effective configuration của bản driver thực tế. Giữ default idempotence bảo thủ rồi đặt true có chủ đích trên các statement được review. Named execution profile có thể gom timeout, CL và retry policy; **profile không thể tự biến mutation nguy hiểm thành an toàn**.

## 4. Ma trận CQL theo tính chất lặp lại

| Loại thao tác | Có thể idempotent? | Điều kiện và bẫy |
|---|---|---|
| **SELECT** không có side effect | **Thường có** | Retry có thể đọc giá trị mới, nhưng không tự ghi Cassandra |
| **INSERT** cùng khóa và giá trị cố định | **Có điều kiện** | Timestamp/TTL, concurrent writers, CDC và side effect |
| **UPDATE SET field = giá trị cố định** | **Có điều kiện** | Ghi cạnh tranh/timestamp, trạng thái nghiệp vụ |
| **DELETE** theo khóa cố định | **Có điều kiện** | Tombstone timestamp, resurrection và ghi cạnh tranh |
| **COUNTER: total = total + 1** | **Không** | Mỗi lần chạy có thể tăng thêm |
| **LIST append/prepend** | **Thường không** | Một phần tử có thể được thêm nhiều lần |
| **SET add/remove** | **Có điều kiện** | Phần tử có tính tập hợp, nhưng timestamp/tombstone/concurrency vẫn quan trọng |
| **MAP gán key/value** | **Có điều kiện** | Gán cố định khác với biến đổi dựa trên trạng thái |
| **BATCH** | **Phải review cả batch** | Batch có thể chứa mutation không idempotent; không tự có transaction đa partition |
| **IF NOT EXISTS / IF column = ?** | **Cần review riêng** | LWT có [applied] thay đổi theo lần thử và timeout không rõ |
| **DDL CREATE/ALTER/DROP** | **Không mặc định** | IF NOT EXISTS không phải schema diff hoặc rollback |

### 4.1. Phép gán cố định so với phép tăng/append

~~~sql
-- Có thể safe khi gắn với đúng khóa, version và timestamp.
UPDATE shop.orders_by_id
SET status = 'PAID'
WHERE tenant_id = ? AND order_id = ?;

-- Không safe để retry mù:
UPDATE shop.counters_by_tenant
SET total = total + 1
WHERE tenant_id = ?;

-- Không safe khi append list có thể tạo phần tử lặp:
UPDATE shop.tasks_by_id
SET events = events + ?
WHERE tenant_id = ? AND task_id = ?;
~~~

Các bảng trong khối code chỉ minh họa **cú pháp thao tác**, không tồn tại nếu chưa tạo CQL schema tương ứng.

### 4.2. TTL là trường hợp tinh vi

~~~sql
INSERT INTO shop.expiring_event_by_id (
    tenant_id, event_id, event_type
) VALUES (?, ?, ?)
USING TTL 120;
~~~

TTL tương đối có thể khiến một retry muộn làm thay đổi thời điểm hết hạn/metadata sống của cell. Nếu hợp đồng nghiệp vụ yêu cầu **hết hạn 120 giây tính từ request đầu**, không được mặc nhiên coi câu CQL này idempotent chỉ vì giá trị cột cố định. Cần thiết kế **expires_at** cố định, timestamp và quy tắc retention phù hợp, rồi kiểm thử phiên bản Cassandra đang dùng.

### 4.3. Batch không tự cứu các mutation nguy hiểm

~~~text
BATCH gồm 2 INSERT cùng khóa/value/timestamp ổn định:
  Có thể xét tính idempotent của toàn batch.

BATCH có counter increment hoặc list append:
  Không thể đánh dấu toàn batch safe chỉ vì một phần là INSERT.

BATCH + gửi email ở Java:
  Cờ idempotent của batch không kiểm soát email.
~~~

Cassandra LOGGED BATCH có cơ chế batchlog riêng, không phải một transaction ACID nhiều partition/đa dịch vụ có rollback. Không dùng batch lớn trải hàng nghìn partition như bulk loader.

## 5. Vì sao timeout không nói “chưa ghi”?

Một request Java thường đi qua coordinator rồi tới những replica giữ partition. Với **RF = 3 tại dc1** và **LOCAL_QUORUM**, write thường cần đủ phản hồi từ **hai replica** theo điều kiện của Cassandra. Nếu chỉ một replica xác nhận và hai replica chậm, client có thể thấy WriteTimeout trong khi replica đầu tiên **đã áp dụng mutation**.

~~~mermaid
sequenceDiagram
    participant J as Java Driver
    participant C as Coordinator
    participant A as Replica A
    participant B as Replica B
    participant D as Replica C
    J->>C: INSERT, LOCAL_QUORUM
    C->>A: Mutation
    C->>B: Mutation
    C->>D: Mutation
    A-->>C: ACK
    B--xC: Chậm/mất phản hồi
    D--xC: Chậm/mất phản hồi
    C-->>J: WriteTimeout / không đủ ACK
    Note over J,D: A có thể đã nhận ghi.
    J->>J: Không kết luận "chưa ghi"
~~~

### 5.1. Ma trận lỗi và mức kết luận

| Tín hiệu | Có thể kết luận | Không được suy ra |
|---|---|---|
| **WriteTimeout** | Không đủ xác nhận trước timeout server | Mọi replica chưa ghi |
| **WriteFailure** | Một hoặc nhiều lỗi ghi được thông báo; không đạt điều kiện thành công | Không có phần dữ liệu nào đã được áp dụng |
| **Driver-side request timeout** | Client đợi quá deadline/timeout của driver | Coordinator đã dừng xử lý |
| **Unavailable** | Không đủ replica khả dụng theo CL được yêu cầu | Row chắc chắn không tồn tại |
| **Overloaded** | Server báo áp lực nhận/xử lý | Retry ngay giúp hệ thống tốt hơn |
| **ReadTimeout/ReadFailure** | Đường đọc không đạt điều kiện phản hồi | Ghi trước đó không xảy ra |
| **LWT [applied]=false** | Điều kiện của attempt đó không thỏa | Attempt trước của chính request chưa áp dụng |

Lỗi hạ tầng có thể làm trạng thái **UNKNOWN**. Đó là **một giá trị nghiệp vụ có ý nghĩa**, không phải thứ phải ép về false để đơn giản hóa code.

### 5.2. RF, CL và replica không phải cơ chế deduplication

Việc tăng **RF** hoặc dùng **LOCAL_QUORUM/QUORUM/ALL** có thể thay đổi khả dụng, độ trễ và điều kiện xác nhận. Nhưng điều đó **không** biến counter +1 thành idempotent hay biến SELECT rồi INSERT thành một compare-and-set.

**Repair** giúp các replica hội tụ dữ liệu theo cơ chế Cassandra, không biết orderId nào bị tạo trùng theo nghiệp vụ. **Compaction** hợp nhất SSTable và xử lý dữ liệu/tombstone ở nền, không khử hai row với **hai request_id khác nhau**. Mô hình khóa và deduplication phải được thiết kế ở tầng ứng dụng.

### 5.3. Retry không phải exactly-once

Retry có thể tăng cơ hội một logical operation **hoàn tất**, nhưng không bảo đảm server thực thi đúng một lần. Exactly-once end-to-end liên quan request identity, một hoặc nhiều sink, sự kiện đã phát, các ghi cạnh tranh và checkpoint bền vững. Với Cassandra, thường cần **at-least-once + idempotent consumer/deduplication + reconciliation** cho workflow nhiều hệ thống.

## 6. CQL lab: phân biệt ba kiểu mutation

Tạo keyspace thử nghiệm trên cluster phù hợp. Ví dụ RF = 3 ở **dc1**; nếu lab chỉ có một node, phải chỉnh RF/CL tương ứng và ghi rõ giới hạn kiểm thử.

~~~sql
CREATE KEYSPACE IF NOT EXISTS idempotency_lab
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};

-- Một logical request có khóa riêng để đối soát chính xác.
CREATE TABLE IF NOT EXISTS idempotency_lab.event_by_request (
    tenant_id uuid,
    request_id uuid,
    event_type text,
    payload text,
    created_at timestamp,
    PRIMARY KEY ((tenant_id, request_id))
);

-- Collection list để chứng minh nguy cơ append lặp.
CREATE TABLE IF NOT EXISTS idempotency_lab.task_list_by_id (
    tenant_id uuid,
    task_id uuid,
    events list<text>,
    PRIMARY KEY ((tenant_id, task_id))
);

-- Table counter tách riêng theo quy tắc CQL.
CREATE TABLE IF NOT EXISTS idempotency_lab.counter_by_tenant (
    tenant_id uuid PRIMARY KEY,
    total counter
);
~~~

**Phân tích wide-column:**

- **event_by_request** dùng composite partition key **(tenant_id, request_id)**, định vị mỗi logical request để đọc/đối soát. Không có một partition tenant duy nhất tăng vô hạn.
- **task_list_by_id** chỉ dùng để chứng minh tính không an toàn của list append. Trong production, nếu events tăng liên tục, ưu tiên **nhiều row theo task/bucket** để tránh collection khổng lồ.
- **counter_by_tenant** minh họa phép cộng dồn không an toàn khi retry; một tenant nóng có thể tạo **hot partition**.
- Partition key quyết định nhóm replica; CL quyết định phản hồi cần thiết. Cờ idempotent **không thay đổi** token/routing.

### 6.1. Fixture cho phép gán ổn định

~~~sql
INSERT INTO idempotency_lab.event_by_request (
    tenant_id, request_id, event_type, payload, created_at
) VALUES (
    11111111-1111-4111-8111-111111111111,
    22222222-2222-4222-8222-222222222222,
    'ORDER_CREATED', '{"order":"lab-01"}',
    '2026-11-21T08:00:00Z'
);

SELECT event_type, payload, created_at
FROM idempotency_lab.event_by_request
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND request_id = 22222222-2222-4222-8222-222222222222;
~~~

Câu CQL trên minh họa logical request có khóa cố định; write timestamp không được chỉ định riêng. Đoạn Java sau sẽ cho cách cố định timestamp ở **một nguồn duy nhất** khi điều kiện nghiệp vụ đòi hỏi.

### 6.2. Hai kiểu không idempotent

~~~sql
-- Gửi lại khi outcome chưa rõ có thể làm counter tăng thêm.
UPDATE idempotency_lab.counter_by_tenant
SET total = total + 1
WHERE tenant_id = 11111111-1111-4111-8111-111111111111;

-- Gửi lại có thể thêm phần tử "STARTED" nhiều lần.
UPDATE idempotency_lab.task_list_by_id
SET events = events + ['STARTED']
WHERE tenant_id = 11111111-1111-4111-8111-111111111111
  AND task_id = 33333333-3333-4333-8333-333333333333;
~~~

CQL chỉ là fixture lab. Không chạy chúng trên counter hoặc list chứa dữ liệu thật chỉ để quan sát idempotency; thay bằng test cluster cô lập.

## 7. Java Driver 4.x: đặt cờ đúng cho từng statement

### 7.1. Prepared INSERT với khóa và timestamp cố định

Đoạn sau thực thi **một logical request** với tenantId, requestId, payload, createdAt và write timestamp ổn định. Trong thực tế, service tạo chúng **một lần trước attempt đầu** rồi lưu/giữ nguyên cho những retry được phê duyệt.

~~~java
import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;

public final class IdempotentWriteDemo {
    public static void main(String[] args) {
        UUID tenantId = UUID.fromString(
            "11111111-1111-4111-8111-111111111111");
        UUID requestId = UUID.fromString(
            "22222222-2222-4222-8222-222222222222");
        Instant createdAt =
            Instant.parse("2026-11-21T08:00:00Z");

        // Demo: timestamp microseconds chọn MỘT LẦN.
        long writeTimestampMicros =
            createdAt.toEpochMilli() * 1_000L;

        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO idempotency_lab.event_by_request " +
                "(tenant_id, request_id, event_type, " +
                "payload, created_at) VALUES (?, ?, ?, ?, ?) " +
                "USING TIMESTAMP ?");

            BoundStatement request = insert.bind(
                    tenantId, requestId, "ORDER_CREATED",
                    "{\"order\":\"lab-01\"}",
                    createdAt, writeTimestampMicros)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            session.execute(request);

            // Nếu phải retry: gửi lại CHÍNH mutation với
            // requestId, giá trị và timestamp không đổi.
        }
    }
}
~~~

**Điều kiện để có thể chọn true cho ví dụ:**

1. Bind values **không đổi** giữa các lần gửi.
2. Primary key ổn định, không tạo UUID mới sau timeout.
3. Write timestamp ổn định và phù hợp chính sách versioning của dữ liệu.
4. Không dùng TTL tương đối, counter, list append hoặc LWT response-dependent.
5. Không có side effect ngoài DB chưa được thiết kế idempotent.
6. Đã kiểm tra concurrent writers, tombstone, timestamps bằng test và hợp đồng nghiệp vụ.

**Không suy ra “cố định timestamp là có transaction”.** Nếu nhiều request khác nhau cùng dùng timestamp hay update cạnh tranh, vẫn phải hiểu last-write-wins/tombstone; với điều kiện trạng thái, cần **CAS/LWT hoặc thiết kế versioning thích hợp**.

### 7.2. Một anti-pattern: timestamp tái tạo mỗi attempt

~~~java
// Không tạo mutation mới từ clock mỗi lần thử lại.
BoundStatement attempt = insert.bind(
    tenantId, requestId, eventType, payload,
    createdAt, System.currentTimeMillis() * 1_000L);
~~~

Mặc dù primary key và payload có thể không đổi, timestamp đã đổi. Một retry đến sau ghi của writer khác có thể thắng theo quy tắc timestamp, làm sai trạng thái nghiệp vụ.

### 7.3. Counter: phải đặt false

~~~java
PreparedStatement increment = session.prepare(
    "UPDATE idempotency_lab.counter_by_tenant " +
    "SET total = total + 1 WHERE tenant_id = ?");

BoundStatement counterWrite = increment.bind(tenantId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(false);

session.execute(counterWrite);
~~~

Câu lệnh nằm trong method có **session** và **tenantId** đã khởi tạo. **setIdempotent(false)** giúp driver tránh thực thi lặp tự động trong các policy áp dụng cờ, nhưng **không tự giải quyết trường hợp timeout đã áp dụng một phần**. API phải có cơ chế theo dõi/đối soát thay vì tự retry tại service.

### 7.4. List append: không đánh dấu true cho dễ retry

~~~java
import java.util.List;

PreparedStatement append = session.prepare(
    "UPDATE idempotency_lab.task_list_by_id " +
    "SET events = events + ? " +
    "WHERE tenant_id = ? AND task_id = ?");

BoundStatement appendEvent = append.bind(
        List.of("STARTED"), tenantId, taskId)
    .setIdempotent(false);

session.execute(appendEvent);
~~~

Một phần tử list có thể xuất hiện nhiều lần khi gửi lại. Nếu ứng dụng cần tập sự kiện theo thứ tự, hãy thiết kế **table mỗi event có eventId riêng** thay vì cho list tăng không giới hạn. Mẫu dùng **List.of** cần Java 9+; trong dự án JDK cũ hơn, sử dụng cấu trúc list tương đương.

### 7.5. SimpleStatement cũng có cờ

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement query = SimpleStatement.builder(
        "SELECT event_type FROM idempotency_lab.event_by_request " +
        "WHERE tenant_id = ? AND request_id = ?")
    .addPositionalValues(tenantId, requestId)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setIdempotent(true)
    .build();
~~~

Trong ứng dụng có truy vấn lặp, **PreparedStatement** thường phù hợp hơn vì giảm chi phí prepare và bind giá trị theo kiểu CQL. Ví dụ SimpleStatement chỉ minh họa nơi đặt metadata; so chữ ký API với driver version đã khóa.

### 7.6. Batch: cờ phải phản ánh toàn bộ hành động

Khi dùng **BatchStatement** hoặc câu CQL BATCH, đánh giá idempotency cho **toàn tập mutation**, không đánh dấu true chỉ vì một statement thành phần là INSERT. Một batch chứa counter/list operation hoặc dùng timestamp/TTL không ổn định cần policy riêng. Batch nhiều partition không tự cung cấp rollback business workflow.

## 8. LWT: cùng row nhưng kết quả [applied] khác

~~~sql
CREATE TABLE IF NOT EXISTS idempotency_lab.claim_by_key (
    tenant_id uuid,
    request_id uuid,
    owner_token text,
    status text,
    PRIMARY KEY ((tenant_id, request_id))
);

INSERT INTO idempotency_lab.claim_by_key (
    tenant_id, request_id, owner_token, status
) VALUES (?, ?, ?, ?)
IF NOT EXISTS;
~~~

Với một key chưa tồn tại:

~~~text
Attempt 1: Cassandra áp dụng IF NOT EXISTS, [applied] = true.
Response bị mất, client thấy timeout.
Attempt 2: Client retry cùng khóa, [applied] = false.
Row đọc lại có owner_token của chính request ban đầu.
~~~

**[applied]=false không tương đương “request ban đầu chưa tạo row”.** Cần đọc lại theo khóa và so owner_token/request fingerprint để phân biệt cùng request retry với người khác thắng.

### 8.1. Regular CL và serial CL

~~~java
BoundStatement lwt = preparedConditional.bind(
        tenantId, requestId, ownerToken, "CLAIMED")
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setSerialConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_SERIAL)
    .setIdempotent(false);
~~~

Ở đây chọn **false bảo thủ** nếu workflow dựa vào lần nhận **[applied]** để quyết định side effect và chưa chứng minh retry an toàn. **LOCAL_QUORUM** là regular CL cho pha xác nhận, còn **LOCAL_SERIAL** liên quan phạm vi đồng thuận của LWT; hai giá trị khác nhau.

Nếu tổ chức có writers từ nhiều DC và cần invariant toàn cục, phải xem xét **SERIAL** vs **LOCAL_SERIAL** đúng phạm vi của Cassandra version, không mặc định LOCAL_SERIAL đủ chỉ vì nhanh hơn. Cờ idempotent **không thay** serial CL.

### 8.2. Kiểm tra [applied] khi có response

~~~java
import com.datastax.oss.driver.api.core.cql.Row;

Row result = session.execute(lwt).one();
if (result == null) {
    throw new IllegalStateException("LWT returned no result");
}

if (result.getBoolean("[applied]")) {
    // Được tạo trong attempt có response.
} else {
    // Điều kiện false: tra row và xác định duplicate/conflict.
}
~~~

Khi **session.execute(lwt)** throw timeout/network exception, **không** tự chạy nhánh false. Trạng thái cần theo dõi là **UNKNOWN**, có thể đòi hỏi đối soát dữ liệu sau khi cluster phục hồi.

## 9. Phân loại kết quả ba trạng thái cho service

Một API có thể dùng domain outcome:

~~~text
APPLIED_TRUE
  Server trả [applied]=true.

APPLIED_FALSE
  Server trả [applied]=false.

UNKNOWN
  Timeout/transport/failure khiến không đủ kết luận.
~~~

Bảng ánh xạ gợi ý:

| Tín hiệu | Service làm gì? |
|---|---|
| True và dữ liệu phù hợp | Báo tạo mới/đã áp dụng |
| False, row trùng idempotency key và fingerprint | Báo đã xử lý bởi cùng request theo hợp đồng |
| False, row thuộc request khác | Báo conflict nghiệp vụ |
| Timeout/WriteFailure/driver timeout | Không trả “false”; giữ unknown, reconcile khi có thể |
| Overloaded/Unavailable | Giảm tải, có thể fail fast; chỉ retry nếu còn budget và an toàn |
| Authentication/invalid CQL/codec | Sửa code/cấu hình, không retry mù |

**Một kết quả false sau retry có thể là tín hiệu thành công của attempt trước.** Bởi vậy cần lưu ID/owner/fingerprint trước lần thử đầu, không sinh lại những giá trị này theo số lần retry.
## 10. Java async: giữ lỗi là lỗi, không chuyển thành false

Đối với service trả **CompletionStage**, lỗi từ server/driver thường làm stage hoàn thành exceptionally. Nếu gộp mọi lỗi thành giá trị false, tầng HTTP có thể báo “đã có đơn hàng” dù hệ thống chưa xác minh được trạng thái.

### 10.1. Anti-pattern đặc biệt nguy hiểm

~~~java
// SAI: timeout, overload, lỗi mạng bị biến thành điều kiện không thỏa.
return session.executeAsync(lwt)
    .thenApply(result ->
        result.currentPage().iterator()
            .next().getBoolean("[applied]"))
    .exceptionally(error -> false);
~~~

Đoạn này làm mất khả năng phân biệt **APPLIED_FALSE** và **UNKNOWN**. Khi lỗi xảy ra, cần giữ exception/cause để đối soát hoặc trả lỗi có thông tin phù hợp.

### 10.2. Ví dụ CompletionStage bảo toàn outcome

~~~java
import java.util.Iterator;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.Row;

public final class ConditionalWriteService {
    private final CqlSession session;

    public ConditionalWriteService(CqlSession session) {
        this.session = session;
    }

    public CompletionStage<Boolean> executeConditional(
            BoundStatement lwt) {
        return session.executeAsync(lwt)
            .thenApply(page -> {
                Iterator<Row> it =
                    page.currentPage().iterator();
                if (!it.hasNext()) {
                    throw new IllegalStateException(
                        "Missing [applied] result");
                }
                return it.next().getBoolean("[applied]");
            })
            .whenComplete((applied, error) -> {
                if (error != null) {
                    Throwable cause = unwrap(error);
                    System.err.println(
                        "LWT error class: " +
                        cause.getClass().getSimpleName());
                }
            });
    }

    private static Throwable unwrap(Throwable error) {
        while (error instanceof CompletionException &&
                error.getCause() != null) {
            error = error.getCause();
        }
        return error;
    }
}
~~~

**Ý nghĩa:**

- Stage chỉ hoàn thành với **true/false** khi server trả kết quả điều kiện.
- Khi timeout hoặc lỗi driver, stage vẫn thất bại; **whenComplete** chỉ quan sát, không biến nó thành false.
- Không log raw BoundStatement, credential, payload hoặc idempotency token nhạy cảm.
- Ví dụ cần được gắn vào service có **CqlSession dùng chung**, không tạo session theo mỗi HTTP request.
- Đoạn code này không tự khởi động retry; đó là chủ đích. Retry cần được quyết định ở nơi biết **business contract**.

### 10.3. Exception class không tự quyết định retry

Nếu service bắt:

~~~java
import com.datastax.oss.driver.api.core.servererrors.WriteTimeoutException;
import com.datastax.oss.driver.api.core.servererrors.WriteFailureException;
import com.datastax.oss.driver.api.core.servererrors.OverloadedException;

try {
    session.execute(write);
} catch (WriteTimeoutException ex) {
    // Outcome mơ hồ: giữ request identity, đối soát.
} catch (WriteFailureException ex) {
    // Kiểm tra lỗi và khả năng partial application.
} catch (OverloadedException ex) {
    // Giảm tải; không retry tức thì khi server đang quá tải.
}
~~~

thì **write** là BoundStatement được tạo trước đó. Đây chỉ là khung minh họa phân loại, không phải full exception handler. Còn có **UnavailableException, read failures, client timeout, network/TLS/auth/codec errors**. Phân loại đầy đủ ở tầng vận hành không có nghĩa cứ gặp một class là chắc chắn retry được.

## 11. Retry budget: đủ điều kiện mới thực thi lại

Một chính sách retry cần đáp ứng đồng thời các điều kiện:

1. **Thao tác đã được chứng minh idempotent** trong phạm vi lưu trữ và nghiệp vụ.
2. **Lỗi có khả năng tạm thời**, không phải bug CQL/schema/auth.
3. **Còn deadline** end-to-end sau khi trừ backoff và thời gian attempt tiếp.
4. **Còn retry budget** và không có dấu hiệu server đang overload/circuit breaker mở.
5. **Không có retry chồng lớp ngoài kiểm soát** giữa driver, service, gateway và HTTP client.
6. **Đúng consistency level và serial consistency**, không hạ ngầm để làm lỗi biến mất.

~~~mermaid
flowchart TD
    A["Attempt gặp lỗi"] --> B{"Mutation có thể thực thi lại an toàn?"}
    B -->|Không/Chưa rõ| R["Không auto retry; giữ UNKNOWN/đối soát"]
    B -->|Có| C{"Lỗi tạm thời và server còn khả năng?"}
    C -->|Không| F["Fail fast / shed load"]
    C -->|Có| D{"Còn deadline + retry budget?"}
    D -->|Không| G["Trả lỗi, không tạo attempt mới"]
    D -->|Có| E["Backoff + jitter + thử lại với cùng identity"]
    E --> H["Đo attempt và kết quả; không sinh ID mới"]
~~~

### 11.1. Full jitter không chặn thread

Ví dụ chính sách **minh họa**, không phải ngưỡng chuẩn Cassandra:

~~~text
max_attempts = 3 (bao gồm lần đầu)
base_backoff = 100 ms
max_backoff = 1000 ms

Nếu được retry:
  ceiling = min(max_backoff, base_backoff * 2^(attempt - 1))
  delay = random(0, ceiling)

Chỉ schedule attempt khi:
  còn deadline đủ cho delay + thời gian xử lý tối thiểu,
  và nguồn tải không ở trạng thái cần shed load.
~~~

Trong Java async, dùng **ScheduledExecutorService**, CompletableFuture delayed executor (nếu JDK hỗ trợ) hoặc scheduler của framework. **Không Thread.sleep** trong driver callback hay reactive event loop.

### 11.2. Tại sao retry budget phải tính cả tầng driver?

Giả sử gateway retry một HTTP call tối đa 2 lần, service retry mỗi CQL tối đa 3 lần, và driver cũng có policy retry. Số physical requests có thể lớn hơn số logical requests nhiều lần, tùy policy/timing.

Cần đo:

~~~text
logical_requests
driver_physical_attempts
service_retry_attempts
gateway_retry_attempts
speculative_executions
in_flight_requests
admission_rejected_requests
~~~

Không đưa ra công thức nhân cố định khi chưa xác định chính xác policy của mỗi tầng, nhưng **phải đặt giới hạn tổng** và biết ai thực sự có quyền retry. Với **speculative execution**, phải xét khả năng hai execution cùng tồn tại trong một logical request.

### 11.3. Một ví dụ sai về deadline

HTTP deadline **2 giây**. Request đã đợi queue **400 ms**, attempt Cassandra mất **1.300 ms**, service định backoff **200 ms** rồi thử tiếp với driver timeout **1 giây**.

~~~text
2.000 ms - 400 ms - 1.300 ms - 200 ms = 100 ms
~~~

Chỉ còn 100 ms cho attempt thứ hai, xử lý kết quả và HTTP response. Việc khởi động một attempt có timeout 1 giây không phù hợp deadline này. Trả lỗi có kiểm soát và để hệ thống phục hồi an toàn tốt hơn phát thêm request orphaned.

## 12. Backpressure và Overloaded: false không chữa quá tải

Nếu Cassandra báo **Overloaded**, retry ngay có thể làm tình trạng xấu hơn:

1. Request inflight tăng.
2. Coordinator/replica queue và disk/GC chịu thêm tải.
3. Tail latency tăng, dẫn đến timeout cho những request khác.
4. Nhiều client cùng retry, tạo **retry storm**.
5. API đã hết deadline vẫn có công việc trên server.

Cờ idempotent có thể cho phép xem xét retry, nhưng **không có nghĩa retry lúc nào cũng có lợi**. Khi quá tải phải áp **admission control, bounded concurrency, rate limit, backoff, queue hữu hạn và load shedding**.

### 12.1. Java semaphore cho logical operations

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.AsyncResultSet;
import com.datastax.oss.driver.api.core.cql.BoundStatement;

public final class BoundedCqlGateway {
    private final CqlSession session;
    private final Semaphore inFlight;

    public BoundedCqlGateway(
            CqlSession session, int maxConcurrent) {
        if (maxConcurrent <= 0) {
            throw new IllegalArgumentException(
                "maxConcurrent must be positive");
        }
        this.session = session;
        this.inFlight = new Semaphore(maxConcurrent);
    }

    public CompletionStage<AsyncResultSet> execute(
            BoundStatement statement) {
        if (!inFlight.tryAcquire()) {
            CompletableFuture<AsyncResultSet> denied =
                new CompletableFuture<>();
            denied.completeExceptionally(
                new RejectedExecutionException(
                    "Cassandra client admission limit"));
            return denied;
        }
        try {
            return session.executeAsync(statement)
                .whenComplete((result, error) ->
                    inFlight.release());
        } catch (RuntimeException ex) {
            inFlight.release();
            throw ex;
        }
    }
}
~~~

**Giới hạn của ví dụ:**

- Permit bảo vệ **một executeAsync** cho trang/kết quả đầu; nếu cần **toàn bộ chuỗi phân trang**, phải giữ permit qua **fetchNextPage()** tới khi toàn pipeline hoàn tất.
- Đây là giới hạn **mỗi Java instance**, không phải toàn service. N instances có thể nhân tổng concurrency.
- **RejectedExecutionException** do app tự chặn khác **OverloadedException** từ Cassandra; log/metrics phải phân biệt.
- Nếu service có manual retry, nên giữ ngân sách/quota cho **logical operation**, không cấp một permit mới không kiểm soát cho mỗi retry.
- Với LWT, thời gian chờ và CAS contention có thể dài hơn ghi thường; cần capacity budget riêng.
- Hệ thống thật phải có deadline, cancellation, queue limits và shutdown/drain hợp lý.

### 12.2. Request rate và concurrency là hai trục khác nhau

Với quy tắc trung bình của Little trong hệ ổn định:

\[
L \approx \lambda W
\]

Trong đó **L** là số request trung bình trong hệ thống, **λ** là thông lượng request/s và **W** là thời gian trung bình mỗi request.

| RPS trung bình | Thời gian trung bình | In-flight ước lượng |
|---|---:|---:|
| 1.000/s | 0,1 s | 100 |
| 1.000/s | 0,5 s | 500 |
| 1.000/s | 2,0 s | 2.000 |

Khi Cassandra chậm 20 lần nhưng arrival rate giữ nguyên, số request tồn đọng cũng có thể tăng rất mạnh. **Tăng timeout mà không giới hạn concurrency** dễ gây memory pressure, p99 xấu và Overloaded. Đây là ước lượng trạng thái ổn định, không phải dự báo chính xác khi hệ bão hòa hoặc có request bị drop.

## 13. Trách nhiệm của các tầng trong kiến trúc Java/Cassandra

| Thành phần | Cần chịu trách nhiệm | Không nên giả định |
|---|---|---|
| **Business/domain owner** | Định nghĩa một logical operation, duplicate policy, same-request/conflict | Driver biết một payment đã được thu hay chưa |
| **Java application developer** | Stable keys/values, cờ idempotent đúng, exception mapping, retry/deadline | setIdempotent(true) tự bảo đảm safety |
| **Repository/data model owner** | Partition key, clustering, schema query, TTL/timestamp semantics | Thay CL có thể chữa truy vấn không theo khóa |
| **Platform/SRE** | RF/DC, health, capacity, compaction/repair, metrics, backup | Replica sẽ tự loại duplicate business records |
| **Driver/policy** | Thực thi CQL theo cấu hình, retry/speculation được phép | Có thông tin nghiệp vụ ngoài request |
| **Gateway/HTTP client** | Tôn trọng deadline và idempotency headers, tránh retries lồng nhau | Mọi POST đều retry an toàn |
| **Downstream sink** | Deduplication/outbox/reconciliation nếu có side effect | Một INSERT Cassandra thành công bảo đảm email đã gửi |

### 13.1. Code review phải đặt câu hỏi ngữ nghĩa

Trước khi chấp nhận một setter **setIdempotent(true)**, reviewer nên yêu cầu:

1. **Operation identity** là gì? RequestId có ổn định qua retry không?
2. **Primary key** có đổi giữa các attempts không?
3. Bind values, **write timestamp, TTL** có đổi không?
4. Có counter/list append, thao tác tương đối hay LWT phụ thuộc response không?
5. Các writers khác có thể xen vào và thay đổi ý nghĩa timestamp/version không?
6. Có side effect ngoài Cassandra được thực hiện trước/sau CQL không?
7. Dùng **retry/speculative execution policy** nào và có bao nhiêu attempts tối đa?
8. Sau timeout, làm sao xác minh kết quả nếu outcome UNKNOWN?
9. Consistency level/RF/DC có phù hợp cam kết nghiệp vụ không?
10. Có integration test chứng minh chạy lặp an toàn và test lỗi không?

Nếu không trả lời được các câu hỏi chính, **đừng bật true chỉ để cải thiện tỷ lệ request thành công**.

## 14. Dùng một bảng idempotency/claim khi nghiệp vụ cần uniqueness

Với quy tắc **“chỉ một request tạo claim cho business key”**, một cách là dùng LWT:

~~~sql
CREATE TABLE IF NOT EXISTS idempotency_lab.claim_by_business_key (
    tenant_id uuid,
    business_key text,
    request_id uuid,
    payload_fingerprint text,
    state text,
    PRIMARY KEY ((tenant_id, business_key))
);

INSERT INTO idempotency_lab.claim_by_business_key (
    tenant_id, business_key, request_id,
    payload_fingerprint, state
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

**Thiết kế:**

- **(tenant_id, business_key)** là partition key của invariant.
- **request_id** xác định logical request đã giữ claim.
- **payload_fingerprint** cho phép phát hiện cùng key nhưng payload khác, không cần lưu plaintext nhạy cảm trong log.
- **state** biểu diễn trạng thái workflow, cần một quy tắc cập nhật có điều kiện nếu nhiều workers cùng thay đổi.

Sau **[applied]=false**, service đọc row với CL phù hợp, so **request_id + payload_fingerprint**:

~~~text
Cùng request_id và fingerprint:
    Có thể xử lý là duplicate của chính request,
    cần kiểm tra state để biết bước nghiệp vụ đã hoàn tất chưa.

Khác request_id hoặc fingerprint:
    Conflict nghiệp vụ; không retry vô hạn tới khi thắng.

Không đọc được vì timeout/unavailable:
    UNKNOWN; chưa đủ bằng chứng để báo đã tạo/chưa tạo.
~~~

**LWT không cung cấp transaction đa bảng/ngoài hệ thống.** Nếu claim đã tạo nhưng ghi detail hoặc phát event lỗi, cần **state machine + outbox/reconciliation**, không hy vọng một CAS sẽ tự rollback email hay message broker.

### 14.1. TTL của idempotency key và cửa sổ chống trùng

Nếu lưu claim chỉ trong một khoảng thời gian rồi hết hạn, phải xác định:

- Khách hàng/gateway có thể retry sau thời hạn đó không?
- Sự kiện cũ còn tồn tại trong downstream hay không?
- Tái sử dụng key sau khi TTL hết có được phép nghiệp vụ không?
- Row hết hạn/tombstone có làm thêm tải đọc/compaction/repair không?

Nếu idempotency record hết hạn trước khi retry cuối cùng xảy ra, cùng logical operation có thể được coi là request mới. Vì vậy, **retention/idempotency window phải thống nhất với retry horizon và thời gian lưu giữ dữ liệu nghiệp vụ**.

### 14.2. Fingerprint không thay quyền truy cập

Fingerprint giúp so payload nhưng không phải bằng chứng định danh người dùng. API phải xác thực/ủy quyền theo tenant, không để một client truy vấn trạng thái claim của tenant khác bằng business_key. Khi log, dùng request ID đã được cho phép và không ghi raw payment token, secrets hay thông tin nhạy cảm.
## 15. Kiểm thử tích hợp JUnit 5: cùng mutation và mutation cộng dồn

Một bài kiểm thử chỉ xác nhận rằng code gọi **setIdempotent(true)** không đủ chứng minh idempotency. Cần gọi thao tác lặp trên **fixture độc lập** và xác minh dữ liệu cuối, sau đó kiểm tra các kịch bản có fault và concurrent writers.

### 15.1. Test gửi lại INSERT cùng khóa, cùng dữ liệu, cùng timestamp

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.net.InetSocketAddress;
import java.time.Instant;
import java.util.UUID;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import org.junit.jupiter.api.Test;

public class IdempotenceIntegrationIT {
    @Test
    void repeatedSameInsertHasOneLogicalRow() {
        UUID tenantId = UUID.randomUUID();
        UUID requestId = UUID.randomUUID();
        Instant occurredAt =
            Instant.parse("2026-11-21T09:00:00Z");
        long stableTimestampMicros =
            occurredAt.toEpochMilli() * 1_000L;

        // Đổi contact point/DC, auth/TLS theo cluster lab.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            PreparedStatement insert = session.prepare(
                "INSERT INTO idempotency_lab.event_by_request " +
                "(tenant_id, request_id, event_type, payload, " +
                "created_at) VALUES (?, ?, ?, ?, ?) " +
                "USING TIMESTAMP ?");

            BoundStatement sameMutation = insert.bind(
                    tenantId, requestId,
                    "ORDER_CREATED", "{\"order\":\"lab-01\"}",
                    occurredAt, stableTimestampMicros)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM)
                .setIdempotent(true);

            // Đây là test chủ động thực thi hai lần,
            // không cần đợi driver tự retry.
            session.execute(sameMutation);
            session.execute(sameMutation);

            PreparedStatement select = session.prepare(
                "SELECT event_type, payload, created_at " +
                "FROM idempotency_lab.event_by_request " +
                "WHERE tenant_id = ? AND request_id = ?");

            Row row = session.execute(select
                .bind(tenantId, requestId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM))
                .one();

            assertNotNull(row);
            assertEquals(
                "ORDER_CREATED",
                row.getString("event_type"));
            assertEquals(
                "{\"order\":\"lab-01\"}",
                row.getString("payload"));
            assertEquals(
                occurredAt,
                row.getInstant("created_at"));
        }
    }
}
~~~

**Phạm vi đã kiểm chứng:** hai lần thực thi **cùng một BoundStatement** cho **cùng partition key** và **cùng write timestamp** cho trạng thái cuối như mong đợi trong lab.

**Chưa chứng minh:** An toàn khi có writer khác đan xen, TTL tương đối, CDC, tombstone, failed attempts hoặc side effects ngoài Cassandra. Nếu những thứ đó thuộc workflow, bổ sung test tương ứng trước khi review cờ true.

### 15.2. Counter tăng hai lần nếu bị gửi lặp

Thêm một test method vào class hoặc một class riêng với imports tương ứng:

~~~java
@Test
void repeatedCounterIncrementHasTwoEffects() {
    UUID tenantId = UUID.randomUUID();

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement increment = session.prepare(
            "UPDATE idempotency_lab.counter_by_tenant " +
            "SET total = total + 1 " +
            "WHERE tenant_id = ?");

        BoundStatement oneIncrement = increment
            .bind(tenantId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false);

        // Cố ý thực thi cùng statement hai lần để
        // minh họa: cờ false không thay đổi ngữ nghĩa CQL.
        session.execute(oneIncrement);
        session.execute(oneIncrement);

        PreparedStatement select = session.prepare(
            "SELECT total FROM idempotency_lab.counter_by_tenant " +
            "WHERE tenant_id = ?");

        Row row = session.execute(select
            .bind(tenantId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        assertNotNull(row);
        assertEquals(2L, row.getLong("total"));
    }
}
~~~

**Điểm nhấn:** **setIdempotent(false)** ngăn những cơ chế retry/speculation tự động tương ứng được driver điều khiển, **nhưng không ngăn Java code tự gọi session.execute hai lần**. Trong test ta chủ động gửi hai mutation, nên counter có thể tăng 2. Đây là lý do manual retry ở service phải được review riêng.

Trên cluster lab quá tải hoặc có request lỗi, kết quả có thể không xác định; chạy bài test này dưới điều kiện **healthy cluster, không fault injection**. Trên JUnit suite thực tế, tạo schema trong fixture/setup riêng, không để mỗi test drop bảng chung làm nhiễu test khác.

### 15.3. Test list append không idempotent

~~~java
@Test
void repeatedListAppendCreatesDuplicates() {
    UUID tenantId = UUID.randomUUID();
    UUID taskId = UUID.randomUUID();

    try (CqlSession session = CqlSession.builder()
            .addContactPoint(
                new InetSocketAddress("127.0.0.1", 9042))
            .withLocalDatacenter("dc1")
            .build()) {

        PreparedStatement append = session.prepare(
            "UPDATE idempotency_lab.task_list_by_id " +
            "SET events = events + ? " +
            "WHERE tenant_id = ? AND task_id = ?");

        BoundStatement statement = append.bind(
                java.util.List.of("STARTED"), tenantId, taskId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setIdempotent(false);

        session.execute(statement);
        session.execute(statement);

        PreparedStatement select = session.prepare(
            "SELECT events " +
            "FROM idempotency_lab.task_list_by_id " +
            "WHERE tenant_id = ? AND task_id = ?");

        Row row = session.execute(select.bind(
                tenantId, taskId)
                .setConsistencyLevel(
                    DefaultConsistencyLevel.LOCAL_QUORUM))
            .one();

        assertNotNull(row);
        java.util.List<String> actual =
            row.getList("events", String.class);
        assertNotNull(actual);
        assertEquals(2, actual.size());
        assertEquals("STARTED", actual.get(0));
        assertEquals("STARTED", actual.get(1));
    }
}
~~~

Một test demo trên list không có nghĩa Cassandra luôn giữ đúng thứ tự khi có **concurrent list writes** từ nhiều clients. Ở đây hai lần append được thực hiện **tuần tự** trong một môi trường lab. Mục đích là chứng minh list append khác với phép gán giá trị cố định.

### 15.4. Test đòi hỏi môi trường nhiều replica

Nếu CI chỉ dùng một Cassandra container RF = 1, bài test có thể chứng minh CQL và ứng dụng hoạt động ở mức cơ bản. Nó **không chứng minh**:

- LOCAL_QUORUM với RF = 3 hoạt động khi một replica lỗi.
- Driver retry/speculation dưới lỗi mạng đa node.
- CAS LWT giữa writers đến từ nhiều DC.
- Sự thay đổi latency khi compaction/repair chiếm I/O.
- Khả năng hội tụ dữ liệu sau một phần replica chỉ nhận mutation.

Cần một suite staging nhiều node/đúng DC với fault injection có kiểm soát; không suy kết quả production từ một test unit hay single-node local.

## 16. Kiểm thử mất phản hồi sau khi ghi đã áp dụng

Một lỗi dễ tạo **duplicate business effect** là: **server đã ghi xong nhưng client không nhận được response**. Có thể minh họa an toàn qua một test double ở tầng service mà không cố phá network production.

### 16.1. Kịch bản kiểm thử

~~~text
1. Service tạo requestId K và payload P một lần.
2. Repository gửi mutation K/P, Cassandra xác nhận.
3. Test adapter cố tình ẩn response, trả lỗi "response lost".
4. Tầng API nhận UNKNOWN và gọi logic reconciliation.
5. Query row theo K với CL phù hợp, thấy payload P.
6. Service kết luận request đã tồn tại với cùng fingerprint,
   không tạo ID mới, không phát event trùng.
~~~

**Chú ý:** Đây là mô phỏng **mất response sau thành công**, không phải tạo **WriteTimeoutException thực từ server**. Kiểm thử lỗi mạng thật cần một suite khác ở cluster staging có fault injection.

### 16.2. Pseudocode test phản hồi bị mất

~~~java
// Pseudocode cấp service, không phải API sẵn có của driver.
UUID requestId = UUID.randomUUID();
String fingerprint = "hash-of-canonical-payload";

// Adapter test: ghi thành công, sau đó giả lập mất phản hồi.
fakeRepository.whenWrite(requestId, () -> {
    realRepository.writeStableRequest(requestId, fingerprint);
    throw new SimulatedLostResponseException();
});

Outcome first = service.create(requestId, fingerprint);
assertEquals(Outcome.UNKNOWN, first);

Outcome afterReconciliation =
    service.reconcile(requestId, fingerprint);
assertEquals(Outcome.ALREADY_PROCESSED, afterReconciliation);

assertEquals(1, businessSink.countByRequestId(requestId));
~~~

Các tên **fakeRepository, service, Outcome, SimulatedLostResponseException, businessSink** là **test doubles và domain types giả định**, không phải class của Java Driver 4.x. Bài test thực cần định nghĩa chúng theo kiến trúc dự án.

**Điểm kiểm chứng là kết quả nghiệp vụ**: sau một lời gọi ban đầu có kết quả không rõ, request vẫn được đối soát, không tạo side effect lặp. Không cố chuyển tất cả timeout thành “thành công” khi chưa có bằng chứng từ dữ liệu.

### 16.3. LWT false sau retry là ca kiểm thử khác

~~~sql
INSERT INTO idempotency_lab.claim_by_business_key (
    tenant_id, business_key, request_id,
    payload_fingerprint, state
) VALUES (?, ?, ?, ?, ?)
IF NOT EXISTS;
~~~

Kịch bản:

1. Lần đầu trả **[applied]=true** ở server nhưng client không thấy.
2. Lần retry cùng business key nhận **[applied]=false**.
3. Java đọc row, so request_id và fingerprint.
4. Nếu cùng logical request, có thể trả **ALREADY_PROCESSED** theo contract.
5. Nếu khác, trả **CONFLICT**.
6. Nếu đọc cũng timeout hoặc replica không khả dụng, giữ **UNKNOWN**.

Không viết test **assert false = conflict** cho mọi lần retry. Test phải phân biệt **same request** và **other request**.

## 17. Kiểm thử tải và fault injection có giới hạn

### 17.1. Ma trận bài thử

| Kịch bản | Điều kiểm chứng | Rủi ro cần tránh |
|---|---|---|
| **Repeated stable INSERT** | Row cuối khớp expected state | Chỉ nhìn row count rồi bỏ timestamp/TTL |
| **Counter/list repeated** | Hai lần gửi tạo hai tác dụng | Gắn true vì muốn giảm error |
| **WriteTimeout** | Không tự kết luận chưa ghi | Sinh ID mới khi retry |
| **Lost response** | Reconciliation tìm đúng request | False bị coi là conflict |
| **Overloaded** | Backpressure/shed load, retry không tăng vô hạn | Retry storm và queue phình |
| **Replica chậm** | Deadline, CL, retry budget và trạng thái ghi | Hạ CL ngầm |
| **Concurrent writers** | Stale retry không ghi đè version mới | Coi gán cùng giá trị là luôn safe |
| **TTL gần hết hạn** | Expiration đúng yêu cầu sau retry | TTL bị kéo dài hoặc xóa sai |
| **Multi-DC LWT** | Serial CL phù hợp invariant | Dùng LOCAL_SERIAL theo thói quen |
| **Downstream event** | Không gửi trùng khi DB retry | Cờ CQL bị nhầm thành exactly-once |

Tất cả cần chạy với **request IDs/tenant IDs thử nghiệm** và dưới giới hạn concurrency/rate cho phép. Không cố tạo WriteTimeout hay cắt mạng production để chứng minh hành vi.

### 17.2. Một test quan trọng về writer đan xen

Thứ tự minh họa:

~~~text
A đặt status=PAID, timestamp 100.
B đặt status=REFUNDED, timestamp 110.
A retry với timestamp:
  (a) 100 cố định
  (b) 120 mới tạo
~~~

**Kỳ vọng cần kiểm chứng theo version/timestamp rules:** trường hợp (b) có thể ghi đè cập nhật hợp lệ của B; trường hợp (a) không vì timestamp thấp hơn trong tình huống đơn giản này. Nhưng nếu B dùng timestamp bằng A, có tombstone/TTL khác, hoặc logic nghiệp vụ không phù hợp, vẫn có thể sai theo cách khác.

Đừng viết “sau mỗi retry, dữ liệu giống nhau nên an toàn” mà không bao gồm **writer concurrency** trong tiêu chí kiểm chứng.

### 17.3. Kết luận từ test phải có giới hạn

Một test pass chỉ chứng minh ngữ nghĩa trong **cluster version, topology, data fixture, CL và error model** đã thử. Tài liệu kết quả nên ghi:

~~~yaml
suite: "idempotent-flag-integration"
run_id: "lab-2026-11-21-example"
cassandra_version: "<exact-version>"
java_driver_version: "<exact-version>"
jdk_version: "<exact-version>"
topology:
  datacenter: "dc1"
  nodes: 3
  replication_factor: 3
request:
  kind: "stable-insert"
  consistency: "LOCAL_QUORUM"
  idempotent_flag: true
  stable_primary_key: true
  stable_write_timestamp: true
verification:
  repeated_writes: 2
  row_state_matches_expected: true
  result: "PASS"
scope:
  concurrent_writer_tested: false
  network_fault_tested: false
~~~

Đây là **report format do ứng dụng định nghĩa**, không phải cấu hình Cassandra. Không ghi secrets, raw binding values, idempotency token nhạy cảm hay payload người dùng trong log.

## 18. Chẩn đoán khi một retry gây sai dữ liệu

### 18.1. Những câu hỏi phải trả lời

1. Có **logical request ID** từ trước lần gửi đầu tiên không?
2. Có bao nhiêu physical attempts ở driver, app, gateway và caller?
3. Các attempts có cùng primary key, payload, timestamp và TTL không?
4. Có speculatively executed attempts không?
5. Từ thời điểm nào có một writer khác thay đổi row?
6. Query có dùng IF/LWT hoặc ghi thường? Kết quả **[applied]** có bị chuyển thành boolean false khi lỗi không?
7. CL và serial CL thực tế là gì? RF/DC/node health như thế nào?
8. Có hot partition, GC pause, disk I/O, compaction, repair gây timeout không?
9. Có side effect ngoài Cassandra bị gọi hai lần không?
10. Bản backup/CDC/log có đủ hỗ trợ reconciliation hoặc incident response không?

### 18.2. Nodetool và chỉ số có ích

Trên node Cassandra được phép, cú pháp tùy version:

~~~bash
nodetool status
nodetool info
nodetool tpstats
nodetool compactionstats
nodetool tablestats idempotency_lab.event_by_request
nodetool tablehistograms idempotency_lab event_by_request
~~~

Kết hợp node logs, GC/heap/native RSS, disk free/latency, pending/dropped messages, read/write/CAS latency, coordinator/replica và application tracing.

**Compaction** có thể làm tăng disk pressure, **repair** có thể cạnh tranh I/O/network và lộ ra dữ liệu hội tụ muộn. Nhưng **không chạy repair để “xóa duplicate order”**: hai order khác requestId là hai hàng hợp lệ theo primary key, Cassandra không biết chúng cùng một hành động nghiệp vụ.

### 18.3. Mẫu log có kiểm soát

~~~json
{
  "event": "cassandra_write_outcome_unknown",
  "operation": "event_by_request.insert",
  "request_id_hash": "hash-example-72",
  "statement_idempotent": true,
  "consistency": "LOCAL_QUORUM",
  "exception_class": "WriteTimeoutException",
  "application_attempt": 1,
  "driver_attempts_observed": 1,
  "logical_deadline_remaining_ms": 185,
  "reconciliation_required": true
}
~~~

Đây là **JSON mẫu**, không phải log mặc định của driver. Chỉ ghi hash/request correlation đã được phê duyệt, không ghi UUID khách hàng, password, token, thanh toán, raw payload hoặc nguyên giá trị BoundStatement.

### 18.4. Runbook xử lý

~~~mermaid
flowchart TD
    A["Phát hiện duplicate / retry bất thường"] --> B["Cô lập logical request và attempts"]
    B --> C{"Ghi có side effect chưa rõ?"}
    C -->|Có| D["Giữ UNKNOWN, bảo vệ bằng chứng"]
    C -->|Không| E["So key/value/timestamp/TTL/flag"]
    D --> E
    E --> F["Đọc row bằng CL phù hợp; so fingerprint"]
    F --> G{"Có đủ bằng chứng kết luận?"}
    G -->|Không| H["Pause replay, reconciliation/incident"]
    G -->|Có| I["Phân loại SAME_REQUEST/CONFLICT/COMPLETED"]
    I --> J["Sửa retry policy, kiểm thử lỗi, rollout có giám sát"]
~~~

Nếu sự cố có mất tiền/sai đơn hàng, hãy ưu tiên **bảo toàn evidence và khắc phục nghiệp vụ**, không chỉ chỉnh cờ rồi coi đã giải quyết. Một thay đổi setIdempotent có thể giảm nguy cơ retry sau này nhưng không tự sửa dữ liệu/side effect sai đã phát sinh.
## 19. Những anti-pattern thường gặp

| Anti-pattern | Hậu quả | Cách thay |
|---|---|---|
| **setIdempotent(true)** cho mọi mutation | Counter/list/side effect có thể chạy lại | Review từng thao tác theo ngữ nghĩa |
| Cho rằng INSERT nào cũng idempotent | Timestamp/TTL/retry ID có thể đổi | Stable key, value, timestamp và test cạnh tranh |
| Sinh UUID khác sau timeout | Một logical event có nhiều rows | Tạo ID một lần từ request, dùng lại |
| Coi **WriteTimeout = chưa ghi** | Retry gây duplicate/ghi đè | Giữ UNKNOWN, đối soát bằng primary key |
| Coi **LWT false = người khác thắng** | Bỏ sót lần đầu của chính client đã thành công | So request ID/fingerprint và state |
| Bắt exception rồi trả **false** | Không phân biệt conflict và lỗi hạ tầng | Domain outcome có UNKNOWN |
| Đánh dấu counter/list append là safe | Tăng/append lặp lại khi retry/speculation | setIdempotent(false), mô hình event chống trùng |
| Dùng default-idempotence=true toàn service | Sai chính sách âm thầm trên query mới | Mặc định bảo thủ, set trên statement rõ ràng |
| Gọi setter rồi bỏ statement trả về | Cờ/CL thực tế không như kỳ vọng | Gán/nối returned statement immutable |
| Đổi CL xuống ONE khi retry | Vi phạm cam kết consistency | Giữ CL theo hợp đồng; phục hồi node/tải |
| Hạ SERIAL xuống LOCAL_SERIAL để giảm timeout | Có thể đổi phạm vi bất biến multi-DC | Review invariant và topology |
| Retry ngay khi Overloaded | Retry storm/queue phình | Load shedding/backoff, bounded in-flight |
| Retry ở driver + app + gateway không có tổng budget | Số attempts tăng ngoài dự kiến | Một chính sách end-to-end, đo physical attempts |
| Dùng batch lớn như transaction đa bảng | Không có rollback workflow, quá tải coordinator | Batch nhỏ đúng ngữ nghĩa, outbox/reconciliation |
| Dùng set/map/list khổng lồ trong một partition | Mutation lớn, tombstone và compaction pressure | Row/bucket theo access pattern |
| Dùng **Thread.sleep** trong async callback | Chặn thread I/O, tail latency xấu | Scheduler không chặn, deadline |
| Đóng CqlSession sau mỗi HTTP request | Churn kết nối, mất hiệu quả driver | Session được tái sử dụng theo lifecycle service |
| Chỉ test một node rồi suy RF3/multi-DC | Bỏ qua quorum, lỗi replica | Suite cluster đại diện riêng |
| Repair để “sửa duplicate order” | Replica vẫn giữ hai row với hai khóa hợp lệ | Domain deduplication/reconciliation |

## 20. Bài tập tình huống và hướng giải

### Bài 1 — Gắn true có làm phép cộng an toàn?

Một developer viết:

~~~java
BoundStatement request = incrementCounter.bind(tenantId)
    .setIdempotent(true);
~~~

**Hỏi:** Counter UPDATE total=total+1 có an toàn khi driver retry không?

**Đáp án gợi ý:** Không. Cờ chỉ mô tả ý định cho driver, không đổi mutation. Khi outcome không rõ, lần retry có thể cộng thêm. Dùng false, không manual retry mù và thiết kế chống trùng theo business event.

### Bài 2 — INSERT dùng cùng primary key

App INSERT cùng primary key, payload và created_at nhưng mỗi lần retry lại tạo một write timestamp mới.

**Hỏi:** Có đủ để khẳng định idempotent trong môi trường có writer cạnh tranh không?

**Đáp án:** Chưa. Retry muộn với timestamp mới có thể ghi đè mutation hợp lệ đến sau. Cần stable timestamp/version rule, test cạnh tranh và reconciliation khi phù hợp; một phép gán cố định riêng lẻ chưa chứng minh toàn workflow.

### Bài 3 — TTL và hạn sử dụng

Bản ghi được viết **USING TTL 120**. Sau 90 giây, client retry cùng CQL vì không thấy ACK lần đầu.

**Hỏi:** Có thể khiến thời điểm hết hạn khác dự tính không?

**Đáp án:** Có nguy cơ; TTL tương đối và semantics của mutation/retry phải được kiểm chứng. Nếu hạn phải tính từ request đầu, cần lưu mốc tuyệt đối/chiến lược expiry phù hợp thay vì mặc định retry an toàn.

### Bài 4 — WriteTimeout ở LOCAL_QUORUM

RF = 3, một replica trả ACK, hai replica chậm. Coordinator trả WriteTimeout.

**Hỏi:** Có thể kết luận không replica nào đã ghi không?

**Đáp án:** Không. Một số replica có thể đã áp dụng mutation. Chọn retry theo idempotency, giữ request identity và đối soát thay vì sinh row mới.

### Bài 5 — Một POST tạo hai order

HTTP client tự retry sau timeout. Mỗi lần service chạy đều gọi UUID.randomUUID để tạo orderId mới trước INSERT.

**Hỏi:** Vì sao cờ true trên INSERT không ngăn được hai order?

**Đáp án:** Hai attempts thực tế dùng **hai primary keys** khác nhau. Idempotency key phải thuộc logical request, được giữ qua HTTP/gateway/service retries, đồng thời so payload fingerprint.

### Bài 6 — LWT false sau retry

Attempt đầu **INSERT IF NOT EXISTS** được áp dụng nhưng mất response. Attempt hai nhận **[applied]=false**, row có cùng request ID.

**Hỏi:** Có nên trả conflict?

**Đáp án:** Không mặc nhiên. Nếu row có đúng fingerprint của request ban đầu, đây có thể là duplicate của chính request. Đối soát state/workflow, trả kết quả idempotent theo contract và không gửi side effect trùng.

### Bài 7 — Xử lý lỗi async

Service viết:

~~~java
return session.executeAsync(statement)
    .thenApply(page -> parseApplied(page))
    .exceptionally(error -> false);
~~~

**Hỏi:** Sai ở đâu?

**Đáp án:** Biến lỗi timeout, network hoặc overloaded thành false của điều kiện. Cần giữ exception/UNKNOWN và có logic reconciliation; chỉ true/false khi có response LWT hợp lệ.

### Bài 8 — Counter test trả hai

Một test dùng tenantId mới, thực thi cùng counter UPDATE hai lần, đọc thấy total=2.

**Hỏi:** Vì sao điều này không mâu thuẫn với cờ false của driver?

**Đáp án:** Code đã chủ động gửi hai lần. setIdempotent(false) không cấm ứng dụng gọi execute lặp lại; nó chỉ cung cấp metadata cho cơ chế thực thi tự động của driver/policy.

### Bài 9 — Retry policy chồng ba tầng

Gateway, service và driver đều có retry riêng. App thấy application_retry_count=0 nên kết luận DB chỉ nhận một attempt.

**Hỏi:** Kết luận có chính xác không?

**Đáp án:** Không. Cần đo logical vs physical attempts, retry/speculative execution ở driver, service, gateway và caller. Một app-level counter bằng 0 không chứng minh không có retries.

### Bài 10 — Giảm CL khi timeout

Một endpoint cam kết ghi LOCAL_QUORUM. Sau WriteTimeout, policy retry ở LOCAL_ONE để tăng tỷ lệ thành công.

**Hỏi:** Rủi ro gì?

**Đáp án:** Thay đổi điều kiện xác nhận theo hợp đồng, không sửa nguyên nhân replica/disk/compaction. Không hạ consistency ngầm; điều tra availability hoặc đưa ra chế độ degradation được nghiệp vụ phê duyệt rõ.

### Bài 11 — Speculative execution với list append

Driver được cấu hình speculative execution và statement list append đánh dấu true.

**Hỏi:** Có thể xảy ra gì?

**Đáp án:** Một logical request có thể có nhiều execution cùng làm append, tạo duplicate list elements. Phải đánh dấu false và tránh phép biến đổi không idempotent nếu cần thực thi lặp.

### Bài 12 — Bảng theo truy vấn và retry

Một tenant có partition events lớn nhiều GiB. Team tăng page size/timeout, gắn true và cho retry 5 lần khi ReadTimeout.

**Hỏi:** Tại sao không xử lý nguyên nhân?

**Đáp án:** Query vẫn dồn vào nhóm replica của partition lớn; tombstone, SSTable và compaction I/O vẫn nặng. Cần chia bucket/shard theo access pattern, giảm tải và điều tra read path. Cờ idempotent không tối ưu mô hình dữ liệu.

### Bài 13 — LWT bảo vệ uniqueness nhưng email bị lặp

INSERT IF NOT EXISTS true, sau đó gửi email. Caller mất HTTP response nên retry; app nhận false rồi vẫn gửi email một lần nữa.

**Hỏi:** LWT có lỗi không?

**Đáp án:** Không nhất thiết. LWT bảo vệ claim trong Cassandra, không quản lý email. Cần idempotency key ở sink/outbox hoặc lưu trạng thái workflow và đối soát, không kích hoạt email dựa trên false đơn thuần.

### Bài 14 — Cờ false trên một SELECT

Một SELECT chỉ đọc có cùng bind values và không có side effects nhưng bị đặt setIdempotent(false).

**Hỏi:** Có sai dữ liệu không, và đánh đổi gì?

**Đáp án:** Đây là lựa chọn bảo thủ, thường không làm SELECT ghi dữ liệu sai, nhưng có thể hạn chế retry/speculation theo policy và tăng lỗi/latency người dùng trong các tình huống lỗi tạm thời. Đội cần review để chọn true nếu chứng minh an toàn.

### Bài 15 — Một request khác nội dung dùng lại key

Hai HTTP requests từ cùng tenant có **cùng idempotency key** nhưng payload thanh toán khác nhau.

**Hỏi:** Có thể trả ALREADY_PROCESSED cho lần sau không?

**Đáp án:** Không nên. So fingerprint/canonical payload và quyền truy cập; key trùng với nội dung khác là conflict hoặc lỗi hợp đồng. Cờ trên CQL không giải quyết việc chiếm dụng key sai.

### Bài 16 — Test single-node và production multi-DC

Team chạy test INSERT/SELECT trên một Cassandra container RF1 rồi tuyên bố mọi writer đa DC dùng LOCAL_SERIAL bảo vệ uniqueness toàn cục.

**Hỏi:** Thiếu gì?

**Đáp án:** Cần kiểm thử writers từ các DC khác nhau, RF/DC, SERIAL/LOCAL_SERIAL đúng policy, network faults và driver version. Single-node chỉ chứng minh semantics cơ bản, không chứng minh invariant multi-DC.

## 21. Checklist code review và vận hành

- [ ] Đã định nghĩa **logical operation** và idempotency key ở tầng API/nghiệp vụ.
- [ ] Request ID, partition key và payload fingerprint ổn định qua mọi attempt được phép.
- [ ] Đã phân biệt **storage idempotence, response idempotence và workflow idempotence**.
- [ ] Không gắn true cho counter, list append hoặc các thao tác biến đổi tương đối chưa được chứng minh an toàn.
- [ ] Với INSERT/UPDATE/DELETE, đã review timestamp, TTL, tombstone, concurrent writers và trạng thái nghiệp vụ.
- [ ] Không mặc định LWT safe để retry; xử lý **[applied] true/false/UNKNOWN**.
- [ ] Có đọc/đối soát row theo khóa sau timeout khi nghiệp vụ cần, không tạo ID mới bừa bãi.
- [ ] Không biến exception thành boolean false trong async/repository.
- [ ] Các statement immutable được gán/nối đúng giá trị sau setter.
- [ ] Default-idempotence và execution profiles được kiểm tra trên driver version đã pin.
- [ ] Cờ true được khai báo ở **đúng statement**; false là lựa chọn bảo thủ khi chưa rõ.
- [ ] Retry policy/speculative execution được review và giới hạn attempts thực.
- [ ] Có **deadline end-to-end**, backoff/jitter, retry budget và circuit/admission.
- [ ] Không retry Overloaded tức thì hoặc tự hạ CL ngoài hợp đồng nghiệp vụ.
- [ ] Có bounded in-flight, queue hữu hạn và rate limit per tenant/endpoint khi phù hợp.
- [ ] Đã kiểm tra RF/DC, CL, local datacenter và serial CL với LWT multi-DC.
- [ ] Partition key phù hợp truy vấn; collection/mutation/batch/partition không phát triển vô hạn.
- [ ] Theo dõi coordinator/replica, disk/GC, tombstone, compaction/repair trước khi tăng retries.
- [ ] Có integration tests chạy lại cùng mutation, counter/list negative test và lost-response test.
- [ ] Có fault injection trên lab nhiều node với outcome UNKNOWN và reconciliation.
- [ ] Có tests cho concurrent writes, TTL gần hạn và duplicate side effects bên ngoài.
- [ ] CqlSession/PreparedStatement dùng chung theo lifecycle service, không tạo mới theo HTTP request.
- [ ] Không ghi secrets, raw bind values, payment payload hoặc định danh người dùng vào log.
- [ ] Báo cáo test nêu đúng phiên bản driver/Cassandra, topology, RF/CL, attempts và phạm vi chưa thử.

## 22. Tổng kết

**Idempotency không phải một thuộc tính mà Java Driver có thể tự suy từ tên câu lệnh CQL.** Nó là hợp đồng về **thực thi lại cùng logical operation**, được xác định bởi primary key, giá trị bind, timestamp/TTL, writer cạnh tranh, kết quả điều kiện và side effects.

Cờ **setIdempotent(true)** nói cho driver rằng đội ứng dụng **đã đánh giá thao tác an toàn để thực thi lại** theo policy, chứ không làm thao tác trở nên an toàn. Counter increment, list append và workflow có side effect cần xử lý khác; LWT có thể trả **[applied]=false sau khi lần trước đã true nhưng mất phản hồi**. Với WriteTimeout/WriteFailure, trạng thái có thể **UNKNOWN**, không được suy là chưa ghi.

Trong Apache Cassandra, bảo đảm đúng phải kết hợp **idempotency key ổn định, bảng theo partition key, consistency level đúng RF/DC, retry/deadline có giới hạn, backpressure và reconciliation**. Khi có lỗi, compaction/repair và sức khỏe replica ảnh hưởng khả năng hoàn tất request, nhưng không thay thế được việc nhận diện duplicate nghiệp vụ. Chỉ bật cờ true sau khi **chứng minh được ngữ nghĩa**, kiểm thử được thực thi lặp và biết cách đối soát trong trường hợp kết quả không rõ.
