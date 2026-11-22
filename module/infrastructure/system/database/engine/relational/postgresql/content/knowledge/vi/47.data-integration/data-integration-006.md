# Giao dịch, lỗi mạng và giới hạn tính nguyên tử với nguồn ngoài trong PostgreSQL

PostgreSQL cung cấp transactions với các thuộc tính ACID cho những thay đổi được quản lý trong cùng database transaction. Khi một transaction commit thành công, PostgreSQL bảo đảm các thay đổi thuộc transaction đó được áp dụng theo durability settings. Nếu transaction rollback, các thay đổi trong transaction không trở thành trạng thái đã commit.

Ranh giới này có giới hạn. Một transaction PostgreSQL không tự động bao gồm email đã gửi, HTTP request tới payment provider, file đã upload lên object storage, message đã publish vào broker hoặc thay đổi trên một database độc lập. Nếu ứng dụng cập nhật database rồi gọi dịch vụ bên ngoài, lỗi mạng có thể xảy ra giữa hai thao tác. Database có thể rollback trong khi dịch vụ ngoài đã thực hiện side effect, hoặc database đã commit nhưng client không nhận được phản hồi.

Vì vậy, tích hợp dữ liệu cần thiết kế rõ ràng cho các trạng thái không chắc chắn. Các kỹ thuật quan trọng gồm idempotency keys, retry có phân loại, transactional outbox, inbox/deduplication, saga với compensation và two-phase commit khi mọi participant thực sự hỗ trợ giao thức đó. Mỗi cách giải quyết một loại vấn đề khác nhau; không có một lệnh BEGIN/COMMIT nào tự mở rộng ACID sang mọi hệ thống.

Bài học này tập trung vào cách PostgreSQL xử lý transaction và lỗi kết nối, vì sao COMMIT có thể có kết quả chưa biết đối với client, cách xây dựng workflows chịu lỗi và cách xác minh tính nhất quán khi phối hợp với nguồn ngoài.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Xác định phạm vi atomicity của một PostgreSQL transaction.
2. Phân biệt transaction rollback với một external side effect đã hoàn tất.
3. Phân tích các thời điểm mạng có thể đứt trước, trong và sau COMMIT.
4. Giải thích ambiguous commit outcome và cách xác minh trạng thái.
5. Phân loại lỗi có thể retry và lỗi cần xử lý nghiệp vụ.
6. Thiết kế idempotency keys để client retry an toàn.
7. Phân biệt at-most-once, at-least-once và effectively-once processing.
8. Triển khai transactional outbox và inbox/deduplication.
9. Thiết kế saga, compensation và forward recovery.
10. Hiểu PREPARE TRANSACTION, COMMIT PREPARED và giới hạn của two-phase commit.
11. Đánh giá postgres_fdw, dblink, message brokers và external APIs.
12. Tránh giữ database transactions mở trong lúc chờ network calls dài.
13. Quản lý timeouts, retries, backoff, circuit breakers và connection pools.
14. Theo dõi in-flight operations, outbox backlog và reconciliation.
15. Xây dựng 80 bài tập thực hành về integration reliability.

## 2. Phạm vi ACID của PostgreSQL

ACID mô tả tính chất của một transaction trong resource manager thực hiện transaction đó.

- Atomicity: các thay đổi thuộc transaction được commit cùng nhau hoặc rollback cùng nhau.
- Consistency: constraints và các quy tắc được database enforce vẫn phải đúng sau transaction.
- Isolation: các transactions đồng thời quan sát và tác động lẫn nhau theo isolation level.
- Durability: sau commit thành công, dữ liệu được bảo vệ theo durability configuration và failure model.

### 2.1. Một transaction database

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

COMMIT;
~~~

Nếu transaction commit thành công, cả hai updates cùng được ghi nhận. Nếu một statement thất bại và transaction bị rollback, cả hai updates không được commit.

### 2.2. Atomicity không tự mở rộng qua HTTP

~~~text
PostgreSQL transaction
    BEGIN
      UPDATE orders
      INSERT payment_request
    COMMIT

External system
    HTTP POST /charge
~~~

Database và HTTP service là hai resource managers riêng. PostgreSQL không thể rollback một HTTP request đã được payment provider xử lý.

### 2.3. External resource có lifecycle riêng

Một external service có thể:
- Nhận request nhưng xử lý bất đồng bộ.
- Thực hiện side effect rồi mất kết nối trước khi trả response.
- Trả timeout trong khi operation vẫn tiếp tục ở server.
- Xử lý cùng request nhiều lần nếu client retry.
- Có trạng thái eventual consistency.
- Có API để query operation status hoặc idempotency key.

Ứng dụng phải hiểu contract của external service thay vì giả định request-response là một thao tác nguyên tử.

### 2.4. Transaction không phải distributed transaction mặc định

BEGIN/COMMIT chỉ điều khiển transaction trên connection/database đang tham gia. Nếu ứng dụng mở thêm connection tới database khác hoặc gọi HTTP, các resources đó không tự động tham gia cùng transaction.

## 3. Các kịch bản lỗi mạng quanh transaction

Khi kết nối bị đứt, kết quả phụ thuộc thời điểm lỗi.

| Thời điểm mất kết nối | Điều client biết | Hướng xử lý |
| --- | --- | --- |
| Trước khi server nhận request | Có thể request chưa chạy | Retry nếu operation được thiết kế an toàn |
| Trong khi statement đang chạy | Không biết statement đã chạy tới đâu | Xác minh connection/backend và transaction state |
| Trước khi gửi COMMIT | Transaction thường sẽ rollback khi session kết thúc, nhưng cần xác minh session/server state | Không suy luận từ client timeout đơn lẻ |
| Sau khi server commit nhưng trước khi gửi response | Transaction có thể đã commit | Xử lý ambiguous outcome |
| Sau khi client nhận commit success | Client biết server đã xác nhận commit | Tiếp tục workflow theo state đã lưu |

### 3.1. Request chưa tới server

Nếu TCP connection lỗi trước khi request tới PostgreSQL, server không thực hiện statement. Tuy nhiên, client thường khó phân biệt trường hợp này với request đã tới server nhưng response bị mất.

### 3.2. Statement đang chạy

Nếu client mất kết nối, backend có thể phát hiện socket failure và abort transaction. Nhưng detection không nhất thiết xảy ra tức thời; query có thể vẫn chạy trong một khoảng ngắn hoặc server chưa nhận ra disconnect.

### 3.3. Mất kết nối trước COMMIT

Nếu transaction chưa được commit và session kết thúc, PostgreSQL rollback transaction chưa commit. Nhưng client không nên dùng một timeout ở tầng ứng dụng làm bằng chứng tuyệt đối rằng backend đã kết thúc.

### 3.4. Mất kết nối trong lúc COMMIT

Đây là trường hợp khó nhất. Server có thể đã ghi commit record và hoàn tất commit, nhưng response bị mất trên đường về client. Client chỉ thấy connection error và không biết transaction đã commit hay chưa.

### 3.5. Mất kết nối sau COMMIT response

Nếu client đã nhận được response thành công cho COMMIT, PostgreSQL đã xác nhận commit theo durability policy đang cấu hình. Các external steps sau đó vẫn có thể thất bại độc lập.

## 4. Ambiguous commit outcome

Giả sử ứng dụng gửi:

~~~sql
BEGIN;
INSERT INTO orders(order_id, status) VALUES (9001, 'created');
COMMIT;
~~~

PostgreSQL commit thành công, nhưng network connection bị reset trước khi client nhận response. Client nhận lỗi kết nối. Nếu client chạy lại INSERT, có thể tạo duplicate hoặc gặp unique violation.

### 4.1. Vì sao client không thể suy ra kết quả?

TCP connection chỉ cho biết việc truyền thông tin giữa hai endpoints có bị gián đoạn hay không. Nó không cung cấp một câu trả lời nghiệp vụ cho câu hỏi "transaction đã commit chưa?" khi acknowledgement bị mất.

### 4.2. Không retry toàn bộ thao tác một cách mù quáng

Nếu transaction đã commit, retry có thể:
- Tạo duplicate row.
- Trừ tiền hai lần.
- Gửi hai orders.
- Phát hai messages.
- Thực hiện side effect ngoài database lần thứ hai.

### 4.3. Thiết kế để hỏi lại được trạng thái

Mỗi business operation nên có một stable identifier hoặc idempotency key. Sau lỗi không rõ kết quả, client có thể truy vấn trạng thái operation theo key thay vì thực hiện lại một command mới.

### 4.4. Commit acknowledgement và durability

Kết quả commit được xác nhận theo cấu hình durability, chẳng hạn synchronous_commit và synchronous replication policy. Nếu ứng dụng thay đổi durability settings, cần đánh giá RPO/failure model riêng. Một response commit success không có nghĩa external service đã xử lý.

## 5. Phân loại lỗi và retry

Không phải mọi lỗi đều nên retry.

### 5.1. Serialization failure

SQLSTATE 40001 biểu thị serialization failure. Với serializable transactions, ứng dụng thường phải retry toàn bộ transaction từ đầu sau khi lỗi này xảy ra.

### 5.2. Deadlock detected

SQLSTATE 40P01 biểu thị deadlock detected. PostgreSQL hủy một transaction làm victim. Ứng dụng có thể retry toàn bộ transaction nếu operation an toàn và retry budget còn.

### 5.3. Unique violation

SQLSTATE 23505 thường là vi phạm unique constraint. Không mặc định retry cùng transaction; xác định đó là duplicate request/idempotency collision hay business conflict.

### 5.4. Connection exception

SQLSTATE class 08 biểu thị connection exception. Khi lỗi xảy ra quanh COMMIT, transaction outcome có thể không xác định từ client. Cần dùng operation identifier để tra cứu.

### 5.5. Query cancellation và timeout

SQLSTATE 57014 thường liên quan query cancellation. Cần phân biệt query bị cancel trước commit với connection loss sau khi commit đã được gửi. Một timeout ở client có thể chỉ ngắt chờ ở client, tùy driver/cancellation mechanism.

### 5.6. Retry matrix

| Lỗi | Hành động thường phù hợp |
| --- | --- |
| 40001 serialization failure | Retry toàn bộ transaction với backoff |
| 40P01 deadlock | Retry toàn bộ transaction có giới hạn |
| 23505 unique violation | Xử lý duplicate/conflict theo business rule |
| 08xxx connection exception | Xác minh outcome; dùng idempotency/reconciliation |
| 57014 query canceled | Xác định cancellation point và transaction state |
| 22xxx data exception | Sửa input; không retry y nguyên |
| 28xxx authentication failure | Sửa credentials/permissions |
| 53xxx insufficient resources | Giảm tải/đợi capacity; retry có giới hạn nếu phù hợp |

### 5.7. Retry phải có giới hạn

Dùng bounded retries, exponential backoff, jitter, deadline và maximum elapsed time. Retry không giới hạn có thể tạo retry storm và làm dịch vụ đang lỗi càng quá tải.

## 6. Exponential backoff và jitter

Một retry policy thường tăng dần khoảng chờ giữa các lần thử.

~~~text
attempt 1: wait about 100 ms
attempt 2: wait about 200 ms
attempt 3: wait about 400 ms
attempt 4: wait about 800 ms
...
cap delay and add random jitter
~~~

### 6.1. Exponential backoff

Delay tăng theo số lần retry, thường có upper bound. Mục tiêu là giảm áp lực lên dependency đang gặp sự cố.

### 6.2. Jitter

Thêm một thành phần ngẫu nhiên giúp nhiều clients không retry cùng một thời điểm sau outage.

### 6.3. Deadline

Tổng thời gian retry phải nằm trong request deadline hoặc background job SLA. Nếu hết deadline, lưu operation state để xử lý sau thay vì tiếp tục retry vô hạn.

### 6.4. Retry budget

Giới hạn tỷ lệ retries trên tổng requests. Nếu tỷ lệ vượt ngưỡng, mở circuit hoặc giảm traffic để tránh khuếch đại lỗi.

### 6.5. Chỉ retry operation an toàn

Retry một GET thường ít rủi ro hơn retry payment POST, nhưng semantics thực tế phụ thuộc API. Hãy đọc contract và dùng idempotency key cho side effects.

## 7. Idempotency là gì?

Một operation idempotent có thể được thực hiện nhiều lần với cùng identity mà không tạo thêm hiệu ứng nghiệp vụ ngoài kết quả mong muốn.

Ví dụ, "đặt trạng thái order thành shipped" có thể idempotent nếu thao tác được định nghĩa đúng. "Trừ balance thêm 100" không idempotent nếu mỗi lần gọi đều tạo một lần trừ tiền.

### 7.1. Idempotency key

Client tạo một key ổn định cho một business request và gửi lại cùng key khi retry. Server lưu key cùng request identity, status và result.

### 7.2. Key scope

Key cần unique trong phạm vi xác định, ví dụ tenant + operation type + key. Đừng dùng một key chung cho các requests khác nhau.

### 7.3. Request fingerprint

Lưu hash/canonical representation của request. Nếu cùng idempotency key được dùng với payload khác, trả conflict thay vì dùng nhầm kết quả cũ.

### 7.4. Retention

Giữ idempotency records ít nhất bằng thời gian client/provider có thể retry và thời gian business operation cần tra cứu. Xóa record quá sớm có thể làm request cũ được thực hiện lại.

### 7.5. Idempotency không tự tạo exactly-once

Idempotency giúp duplicate attempts không tạo duplicate business effects trong phạm vi được bảo vệ. Nó không bảo đảm message chỉ được giao một lần hoặc mọi hệ thống ngoài cùng commit atomically.

## 8. Bảng idempotency trong PostgreSQL

Một bảng đơn giản:

~~~sql
CREATE TABLE app.idempotency_requests (
    tenant_id bigint NOT NULL,
    idempotency_key text NOT NULL,
    request_hash bytea NOT NULL,
    operation_type text NOT NULL,
    status text NOT NULL
        CHECK (status IN ('processing', 'completed', 'failed')),
    response_body jsonb,
    resource_id bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

### 8.1. Ghi nhận request

Trong transaction xử lý request, thử insert key:

~~~sql
INSERT INTO app.idempotency_requests (
    tenant_id,
    idempotency_key,
    request_hash,
    operation_type,
    status
)
VALUES ($1, $2, $3, $4, 'processing')
ON CONFLICT DO NOTHING;
~~~

Nếu insert tạo row, transaction hiện tại có thể sở hữu việc xử lý key. Nếu không insert được vì key đã tồn tại, đọc record đã có và so sánh request_hash.

### 8.2. Kiểm tra payload

Nếu hash khác, trả conflict vì client đang dùng lại key cho một request khác. Nếu hash giống và status completed, trả lại response đã lưu.

### 8.3. Concurrent duplicate requests

Unique constraint trên (tenant_id, idempotency_key) điều phối các inserts cạnh tranh. Một insert có thể phải chờ transaction khác commit/rollback. Sau đó request thua cuộc đọc trạng thái đã commit.

### 8.4. Cập nhật result cùng business changes

Với thao tác hoàn toàn local trong PostgreSQL, ghi business row, idempotency result và response trong cùng transaction. Nếu transaction rollback, key claim và business changes cùng rollback.

### 8.5. Không để processing record mồ côi vô thời hạn

Nếu operation gồm external side effect, không giữ một transaction database mở trong suốt network call. Dùng operation state machine/outbox để xử lý bất đồng bộ và có timeout/reconciliation.

## 9. Mẫu xử lý idempotent cho local operation

Ví dụ tạo order và lưu response trong một transaction:

~~~sql
BEGIN;

INSERT INTO app.idempotency_requests (
    tenant_id,
    idempotency_key,
    request_hash,
    operation_type,
    status
)
VALUES (42, 'req-7f31', decode('aabbcc', 'hex'), 'create_order', 'processing')
ON CONFLICT DO NOTHING;

-- Application checks whether this transaction inserted the row.
-- If not, it reads the existing row and returns the stored result
-- when the request hash matches and status is completed.

INSERT INTO app.orders (
    tenant_id,
    order_reference,
    status
)
VALUES (42, 'ORD-9001', 'created')
RETURNING order_id;

UPDATE app.idempotency_requests
SET status = 'completed',
    resource_id = 9001,
    response_body = '{"order_id":9001,"status":"created"}'::jsonb,
    updated_at = now()
WHERE tenant_id = 42
  AND idempotency_key = 'req-7f31';

COMMIT;
~~~

Đây là minh họa flow, không phải một script có thể chạy nguyên trạng cho mọi schema. Ứng dụng phải xác định chính xác transaction đã insert key hay đang đọc kết quả của request trước; không chạy INSERT order nếu key đã được xử lý.

### 9.1. Tránh race giữa select rồi insert

Pattern SELECT key trước rồi INSERT sau có race: hai requests có thể cùng thấy key chưa tồn tại. Dùng unique constraint và INSERT ... ON CONFLICT làm arbiter.

### 9.2. Lưu response ổn định

Nếu API cần trả lại cùng response cho retry, lưu resource identifier/status/response fields đủ để tái tạo response. Tránh lưu secrets hoặc dữ liệu nhạy cảm không cần thiết.

### 9.3. Key expiration

Expiration phải dựa trên business/retry window. Xóa record khi operation vẫn có thể được retry sẽ phá idempotency guarantee.

## 10. Tại sao gọi HTTP bên trong transaction thường không tốt?

Ví dụ:

~~~sql
BEGIN;
UPDATE app.orders SET status = 'paying' WHERE order_id = 9001;
-- Application calls payment provider and waits several seconds.
COMMIT;
~~~

Transaction giữ locks và snapshot trong lúc chờ mạng. Nếu provider timeout, database transaction có thể bị giữ lâu, gây contention và connection pool exhaustion.

### 10.1. Lock duration

Một transaction dài có thể giữ row/table locks, ngăn vacuum cleanup, kéo dài snapshot horizon và tăng dead tuples.

### 10.2. Network latency không dự đoán được

External APIs có thể mất vài milliseconds hoặc hàng chục seconds. Database transactions nên ngắn và có giới hạn.

### 10.3. Rollback không hoàn tác HTTP

Nếu payment provider đã charge nhưng client timeout, rollback database không hoàn tiền. Cần idempotency key với provider, query status hoặc compensation/refund workflow.

### 10.4. Availability coupling

Nếu database transaction cần provider trả lời trước khi commit, availability của database workflow bị phụ thuộc trực tiếp vào latency/availability của provider.

### 10.5. Khi nào synchronous call vẫn phù hợp?

Một số use cases cần response đồng bộ. Nếu thực hiện, giữ transaction ngắn nhất có thể, hiểu timeout semantics, dùng provider idempotency keys và lưu đủ state để reconcile. Tránh giữ row locks trong suốt một network call dài.

## 11. Transactional outbox pattern

Transactional outbox giải quyết bài toán: cập nhật database và ghi nhận một event cần gửi ra ngoài trong cùng một local transaction.

### 11.1. Ý tưởng

Trong một transaction:
1. Cập nhật business data.
2. Insert event vào outbox.
3. Commit cả hai cùng nhau.

Một worker riêng đọc outbox và publish event tới broker hoặc external service.

~~~text
Application
    |
    v
PostgreSQL transaction
    |-- update business row
    |-- insert outbox event
    |
    v
COMMIT
    |
    v
Outbox relay
    |
    v
Message broker / external API
~~~

### 11.2. Vì sao pattern này hữu ích?

Nếu transaction rollback, event không tồn tại. Nếu transaction commit, event đã được lưu bền vững trong database và relay có thể gửi sau khi network phục hồi.

### 11.3. Outbox không làm broker commit cùng database

Database commit và broker publish vẫn là hai bước riêng. Relay có thể publish thành công rồi crash trước khi đánh dấu event published. Vì vậy, duplicate delivery có thể xảy ra.

### 11.4. Delivery semantics

Outbox relay thường được thiết kế theo at-least-once delivery: event có thể được gửi lại cho tới khi được xác nhận. Consumer phải idempotent.

### 11.5. Outbox là durable intent

Outbox ghi nhận rằng database đã commit một business change và hệ thống cần thực hiện một external action. Nó không khẳng định external action đã thành công.

## 12. Thiết kế bảng outbox

~~~sql
CREATE TABLE app.outbox_events (
    event_id uuid PRIMARY KEY,
    aggregate_type text NOT NULL,
    aggregate_id text NOT NULL,
    aggregate_version bigint,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    available_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    attempts integer NOT NULL DEFAULT 0,
    last_error text
);

CREATE INDEX outbox_pending_idx
    ON app.outbox_events (available_at, occurred_at)
    WHERE published_at IS NULL;
~~~

### 12.1. event_id

Một ID ổn định được dùng để deduplicate ở consumer. UUID thường thuận tiện cho event identity.

### 12.2. aggregate identity

aggregate_type/aggregate_id nhóm events theo business entity, chẳng hạn order. aggregate_version có thể giúp phát hiện ordering/gaps.

### 12.3. payload

Lưu đủ thông tin consumer cần. Tránh chứa secrets, payment credentials hoặc dữ liệu không cần thiết. Cân nhắc payload versioning.

### 12.4. published_at

NULL biểu thị event chưa được xác nhận publish theo relay policy. Thời điểm được set sau khi broker/API xác nhận nhận event.

### 12.5. Index pending

Partial index giữ lookup cho unpublished events hiệu quả. Khi bảng lớn, cần retention/partitioning hoặc archive policy để outbox không tăng vô hạn.

## 13. Ghi business change và outbox cùng transaction

~~~sql
BEGIN;

UPDATE app.orders
SET status = 'confirmed',
    version = version + 1
WHERE order_id = 9001
RETURNING order_id, version;

INSERT INTO app.outbox_events (
    event_id,
    aggregate_type,
    aggregate_id,
    aggregate_version,
    event_type,
    payload
)
VALUES (
    gen_random_uuid(),
    'order',
    '9001',
    4,
    'order.confirmed',
    '{"order_id":9001,"status":"confirmed","version":4}'::jsonb
);

COMMIT;
~~~

Ứng dụng nên lấy order_id/version thực tế từ UPDATE ... RETURNING để tạo payload, thay vì hard-code như ví dụ. Có thể thực hiện bằng CTE hoặc application transaction logic.

### 13.1. Atomic local write

Nếu INSERT outbox thất bại, UPDATE order cũng rollback. Nếu commit thành công, cả business state và event intent đều tồn tại.

### 13.2. Không publish trước COMMIT

Nếu publish trước khi database commit, consumer có thể nhận event trong khi business transaction sau đó rollback. Outbox tránh thứ tự sai này bằng cách chỉ relay các rows đã commit.

### 13.3. Payload contract

Event schema nên có event type/version, event ID, aggregate ID, occurred_at và payload fields cần thiết. Consumer phải xử lý evolution của payload.

## 14. Outbox relay với SKIP LOCKED

Nhiều workers có thể lấy các events chưa publish bằng SELECT ... FOR UPDATE SKIP LOCKED.

~~~sql
WITH batch AS (
    SELECT event_id
    FROM app.outbox_events
    WHERE published_at IS NULL
      AND available_at <= now()
    ORDER BY occurred_at, event_id
    FOR UPDATE SKIP LOCKED
    LIMIT 100
)
SELECT e.*
FROM app.outbox_events AS e
JOIN batch AS b USING (event_id);
~~~

### 14.1. Transaction claim ngắn

Có thể claim một batch trong transaction ngắn và gán lease/worker identity. Sau đó commit claim trước khi gọi broker, để không giữ row locks trong suốt network call.

### 14.2. Lease model

Một schema production có thể có locked_by, locked_until hoặc claim_token. Worker chỉ xử lý rows mà lease còn thuộc về nó.

### 14.3. Publish ngoài transaction

Sau khi claim, worker gửi event tới broker. Nếu broker xác nhận, worker cập nhật published_at trong một transaction mới.

### 14.4. Crash sau publish

Nếu broker đã nhận event nhưng worker crash trước khi cập nhật published_at, lease hết hạn và event được gửi lại. Đây là duplicate có chủ đích trong at-least-once design.

### 14.5. Không giữ database lock trong network call

Claim rows, commit, publish, rồi ghi kết quả. Không giữ transaction mở trong khi chờ broker nếu không có một thiết kế đặc biệt đã được đo đạc.

## 15. Inbox pattern và consumer deduplication

Consumer nhận event có thể nhiều lần. Inbox table lưu event IDs đã xử lý cùng business update trong một transaction local.

~~~sql
CREATE TABLE app.inbox_events (
    consumer_name text NOT NULL,
    event_id uuid NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

### 15.1. Consumer transaction

~~~sql
BEGIN;

INSERT INTO app.inbox_events (consumer_name, event_id)
VALUES ('billing-projection', '11111111-1111-4111-8111-111111111111')
ON CONFLICT DO NOTHING;

-- Application checks whether this INSERT created a row.
-- Only a newly claimed event may apply the business update.

UPDATE app.customer_balances
SET order_count = order_count + 1
WHERE customer_id = 42;

UPDATE app.inbox_events
SET processed_at = now()
WHERE consumer_name = 'billing-projection'
  AND event_id = '11111111-1111-4111-8111-111111111111';

COMMIT;
~~~

Đây là flow minh họa. Consumer chỉ chạy UPDATE khi nó thực sự insert được inbox key. Nếu key đã tồn tại, bỏ qua duplicate event và không áp dụng business update lần nữa.

### 15.2. Atomic deduplication

Inbox insert và consumer business update nằm trong cùng transaction. Nếu transaction rollback, inbox claim cũng rollback, cho phép retry event.

### 15.3. Consumer side effect ngoài database

Nếu consumer còn gửi email hoặc gọi API khác, inbox transaction không bao gồm side effect đó. Consumer có thể cần outbox riêng hoặc idempotency key cho dependency tiếp theo.

### 15.4. Inbox retention

Giữ event IDs đủ lâu để bao phủ broker redelivery, replay và disaster recovery. Xóa inbox records quá sớm có thể làm replay tạo duplicate business effects.

## 16. At-most-once, at-least-once và effectively-once

### 16.1. At-most-once

Một event được xử lý tối đa một lần, nhưng có thể bị mất nếu consumer crash sau khi nhận nhưng trước khi xử lý/ack theo protocol.

### 16.2. At-least-once

Event được retry cho tới khi có acknowledgement hoặc policy kết thúc. Duplicate delivery có thể xảy ra.

### 16.3. Exactly-once claims

"Exactly once" cần xác định rõ scope. Broker có thể cung cấp semantics riêng trong một phạm vi nhất định, nhưng điều đó không tự tạo atomic commit giữa broker, PostgreSQL và payment API.

### 16.4. Effectively-once business effect

Một hệ thống có thể đạt kết quả nghiệp vụ tương đương xử lý một lần bằng:
- Stable event/operation IDs.
- Unique constraints.
- Inbox/deduplication.
- Idempotent handlers.
- Atomic local state transitions.
- Reconciliation cho trạng thái không rõ.

Đây là property của workflow được thiết kế, không phải lời hứa rằng mạng không bao giờ duplicate.

## 17. Saga pattern

Saga chia một business workflow dài thành nhiều local transactions, mỗi bước commit độc lập. Nếu bước sau thất bại, hệ thống thực hiện compensating action hoặc chuyển workflow sang trạng thái cần xử lý.

Ví dụ order/payment/shipping:

~~~text
Create order
    |
    v
Reserve inventory
    |
    v
Authorize payment
    |
    v
Arrange shipment
    |
    v
Complete order

If a later step fails:
    release inventory
    void/refund payment when appropriate
    mark order for compensation/review
~~~

### 17.1. Local transactions

Mỗi service/database commit state riêng. Không giữ một database transaction mở trong suốt saga.

### 17.2. Compensation

Compensation là business action để bù lại một bước trước đó. Nó không nhất thiết là phép inverse hoàn hảo. Ví dụ, email đã gửi không thể "unsend"; payment capture có thể cần refund thay vì xóa transaction.

### 17.3. Saga state machine

Lưu workflow state như pending, inventory_reserved, payment_authorized, shipment_requested, completed, compensating, failed hoặc manual_review.

### 17.4. Idempotent steps

Mỗi saga step có stable step ID/idempotency key. Retry step không được reserve inventory hoặc charge payment lần nữa.

### 17.5. Timeout và compensation

Timeout không chứng minh external step thất bại. Trước khi compensation, query provider status hoặc retry cùng idempotency key để xác định outcome.

### 17.6. Orchestration vs choreography

- Orchestration: một coordinator lưu state và điều khiển các steps.
- Choreography: services phản ứng với events và phát events tiếp theo.

Orchestration dễ quan sát state tập trung; choreography giảm central coordinator nhưng flow có thể khó truy vết hơn.

## 18. Lưu saga state trong PostgreSQL

~~~sql
CREATE TABLE app.sagas (
    saga_id uuid PRIMARY KEY,
    saga_type text NOT NULL,
    aggregate_id text NOT NULL,
    state text NOT NULL,
    current_step text,
    version bigint NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    last_error text
);

CREATE TABLE app.saga_steps (
    saga_id uuid NOT NULL REFERENCES app.sagas(saga_id),
    step_name text NOT NULL,
    status text NOT NULL,
    idempotency_key text NOT NULL,
    request_payload jsonb,
    result_payload jsonb,
    attempts integer NOT NULL DEFAULT 0,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (saga_id, step_name),
    UNIQUE (idempotency_key)
);
~~~

### 18.1. Optimistic concurrency

Dùng version column để tránh hai workers cùng cập nhật saga state:

~~~sql
UPDATE app.sagas
SET state = 'payment_authorized',
    version = version + 1,
    updated_at = now()
WHERE saga_id = $1
  AND version = $2;
~~~

Nếu affected row count bằng zero, worker cần đọc state mới và quyết định retry/reconcile.

### 18.2. Persist trước khi gọi ngoài

Ghi step intent/idempotency key trước khi gọi external API. Nếu process crash, worker khác có thể tiếp tục từ durable state.

### 18.3. Persist kết quả sau khi gọi

Khi nhận response, ghi provider operation ID/result và chuyển state trong transaction. Nếu response bị mất, tra cứu provider bằng idempotency key/operation ID.

### 18.4. Compensation state

Lưu trạng thái compensation riêng để biết bước nào đã được bù, bước nào đang retry và bước nào cần manual review.

## 19. Two-phase commit (2PC)

Two-phase commit là protocol phối hợp nhiều resource managers để đạt quyết định commit/abort chung thông qua coordinator.

Hai phases:
1. Prepare: mỗi participant ghi nhận sẵn sàng commit và giữ trạng thái prepared.
2. Commit/abort: coordinator phát quyết định cuối cùng cho tất cả participants.

~~~text
Coordinator
   |
   +---- PREPARE ----> Participant A
   |                       |
   |                       +-- prepared
   |
   +---- PREPARE ----> Participant B
                           |
                           +-- prepared

If all prepared:
   COMMIT PREPARED on A and B
Else:
   ROLLBACK PREPARED on participants
~~~

### 19.1. 2PC khác outbox/saga

2PC cố gắng đạt atomic commit giữa participants có hỗ trợ protocol. Outbox/saga dùng durable local transactions và asynchronous delivery/compensation. Chúng không cung cấp cùng semantics.

### 19.2. Coordinator cần durable decision log

Nếu coordinator crash sau prepare, nó phải khôi phục quyết định từ durable log và hoàn tất commit/abort. Nếu không, participants có thể ở trạng thái in-doubt.

### 19.3. Prepared participants giữ locks

Một prepared transaction có thể giữ locks và transaction resources sau khi client session đóng. Nếu bị bỏ quên, nó gây blocking và ảnh hưởng vacuum/transaction horizons.

### 19.4. 2PC không tự làm HTTP API tham gia

Một HTTP payment provider thường không hiểu PREPARE/COMMIT PREPARED. Không thể biến một HTTP request thành XA participant chỉ bằng cách đặt nó giữa hai SQL commands.

### 19.5. Operational cost

2PC cần transaction manager/coordinator đáng tin cậy, recovery procedure, monitoring prepared transactions và xử lý network partitions. Chỉ chọn khi mọi participants hỗ trợ và yêu cầu atomicity biện minh cho chi phí.

## 20. PostgreSQL prepared transactions

PostgreSQL hỗ trợ prepared transactions qua SQL commands khi max_prepared_transactions được cấu hình lớn hơn zero.

### 20.1. Cấu hình

~~~sql
SHOW max_prepared_transactions;
~~~

Mặc định thường là 0, nghĩa là prepared transactions bị tắt. Thay đổi setting này cần cấu hình server phù hợp và có thể yêu cầu restart theo version/deployment.

### 20.2. Prepare

~~~sql
BEGIN;

UPDATE app.accounts
SET balance = balance - 100
WHERE account_id = 10;

PREPARE TRANSACTION 'transfer-2026-0001';
~~~

PREPARE TRANSACTION kết thúc transaction hiện tại và để transaction ở trạng thái prepared. Global transaction identifier phải unique trong phạm vi database theo rules của PostgreSQL.

### 20.3. Commit prepared

~~~sql
COMMIT PREPARED 'transfer-2026-0001';
~~~

### 20.4. Rollback prepared

~~~sql
ROLLBACK PREPARED 'transfer-2026-0001';
~~~

COMMIT PREPARED và ROLLBACK PREPARED phải được thực hiện ngoài transaction block và theo quyết định của coordinator.

### 20.5. Kiểm tra prepared transactions

~~~sql
SELECT
    transaction,
    gid,
    prepared,
    owner,
    database
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

### 20.6. Không dùng PREPARE TRANSACTION như pause/resume tùy tiện

Prepared transactions không phải cơ chế lưu transaction cho application disconnect rồi tiếp tục sau. Chúng dành cho transaction manager có protocol/recovery rõ ràng.

### 20.7. Không tự ý commit/rollback GID

DBA không nên quyết định COMMIT PREPARED hoặc ROLLBACK PREPARED chỉ dựa trên tuổi transaction. Phải tham khảo coordinator's durable decision log hoặc runbook được thiết kế cho distributed transaction.

## 21. Giới hạn của 2PC

### 21.1. Blocking khi coordinator unavailable

Nếu participant đã prepared nhưng chưa nhận final decision, nó có thể giữ locks trong thời gian coordinator mất kết nối. Đây là đặc tính blocking của classic 2PC.

### 21.2. Participant support

Tất cả participants cần hỗ trợ protocol và semantics tương thích. Một database driver/API thông thường không tự cung cấp distributed transaction coordination.

### 21.3. Operational recovery

Cần biết:
- Coordinator nào sở hữu GID.
- Decision log nằm ở đâu.
- Ai có quyền resolve in-doubt transaction.
- Timeout/escalation policy.
- Cách phục hồi khi một participant không reachable.
- Cách tránh resolve trái với quyết định đã ghi.

### 21.4. Không thay thế backup

2PC phối hợp commit decision, không thay thế backup, PITR, disaster recovery hoặc business reconciliation.

### 21.5. Khi nào cân nhắc?

Khi có nhiều transactional resource managers hỗ trợ 2PC, cần atomic commit thực sự, chấp nhận coordinator/operational complexity và có tested recovery procedures.

## 22. postgres_fdw và remote database transactions

postgres_fdw cho phép truy vấn foreign tables trên PostgreSQL remote server. Nó có thể phối hợp remote transaction lifecycle với local transaction trong phạm vi implementation được hỗ trợ.

### 22.1. Ví dụ foreign server

~~~sql
CREATE EXTENSION postgres_fdw;

CREATE SERVER remote_db
FOREIGN DATA WRAPPER postgres_fdw
OPTIONS (host 'db.example.internal', dbname 'sales', port '5432');

CREATE USER MAPPING FOR app_user
SERVER remote_db
OPTIONS (user 'remote_reader', password 'managed-secret');

IMPORT FOREIGN SCHEMA public
LIMIT TO (customers)
FROM SERVER remote_db
INTO remote_sales;
~~~

Ví dụ chỉ minh họa cấu trúc. Credentials phải được quản lý bằng secret policy; không hard-code password trong migration/repository.

### 22.2. Remote transaction

Khi local transaction truy cập foreign server, postgres_fdw có thể mở remote transaction và quản lý nó tương ứng với local transaction. Nó cũng xử lý savepoints/subtransactions theo khả năng hỗ trợ.

### 22.3. Không giả định global 2PC

Không coi một transaction truy cập nhiều foreign servers và local tables là một distributed transaction atomic tuyệt đối trong mọi failure mode. postgres_fdw không phải coordinator tổng quát cung cấp 2PC cho mọi remote participants. Đọc documentation đúng version và kiểm tra failure semantics của topology.

### 22.4. Network failure

Nếu kết nối remote bị mất trong commit processing, local và remote outcomes có thể cần reconciliation tùy thời điểm failure và implementation. Không retry một business operation mù quáng chỉ vì client nhận lỗi.

### 22.5. Query pushdown

Một số filters/joins có thể được push xuống remote server. Pushdown giảm data transfer nhưng không làm tăng atomicity guarantee.

### 22.6. Credential và role mapping

USER MAPPING quyết định remote identity. Kiểm tra least privilege, password rotation và visibility. Không để application role có remote privileges rộng hơn nhu cầu.

## 23. dblink và external SQL connections

dblink cho phép mở kết nối tới PostgreSQL khác và gửi SQL. Nó là công cụ tích hợp hữu ích trong một số workloads nhưng không tự tạo một distributed transaction coordinator.

### 23.1. Remote call

dblink có thể thực hiện query trên remote connection. Transaction remote có lifecycle riêng tùy connection và commands được gửi.

### 23.2. Local rollback không đảm bảo remote rollback

Nếu remote statement đã commit hoặc remote transaction đã kết thúc, rollback local transaction không tự đảo ngược remote change.

### 23.3. Connection management

Quản lý remote connection lifecycle, error handling, credentials, timeouts và cleanup. Tránh để remote connections bị bỏ quên.

### 23.4. Không che lỗi bằng asynchronous calls

Nếu dùng dblink_send_query/dblink_get_result, cần quản lý result state và connection. Async execution không biến remote action thành atomic với local database.

## 24. External APIs: payment, email và object storage

Mỗi external resource có semantics khác nhau.

### 24.1. Payment provider

Dùng provider idempotency key, lưu provider operation ID, trạng thái authorization/capture/refund và reconciliation. Không giả định timeout nghĩa là payment không xảy ra.

### 24.2. Email service

Email đã được gửi thường không thể rollback. Dùng outbox để gửi sau commit, lưu message ID/status và chấp nhận retry/deduplication theo API support. Không gửi email trước khi business transaction commit.

### 24.3. Object storage

Upload object và ghi database metadata là hai operations. Có thể upload object vào temporary key, sau đó commit metadata/state và promote/finalize theo workflow; hoặc lưu pending state và garbage-collect orphan objects.

### 24.4. Search index

Database commit và search indexing thường eventual consistent. Dùng outbox/change stream và consumer idempotent; hiển thị indexing status nếu cần.

### 24.5. Webhooks

Webhook delivery thường at-least-once. Dùng stable event ID, signature verification, retry schedule, endpoint timeout và receiver deduplication.

## 25. Transactional outbox cho API integration

Một ứng dụng có thể tạo order và yêu cầu payment trong cùng database transaction bằng cách ghi một payment command vào outbox.

~~~sql
CREATE TABLE app.payment_commands (
    command_id uuid PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES app.orders(order_id),
    idempotency_key text NOT NULL UNIQUE,
    amount numeric(14,2) NOT NULL CHECK (amount > 0),
    currency char(3) NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'processing', 'succeeded', 'failed', 'unknown')),
    provider_reference text,
    last_error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
~~~

Trong transaction tạo order:

~~~sql
BEGIN;

INSERT INTO app.orders (order_id, status)
VALUES (9001, 'pending_payment');

INSERT INTO app.payment_commands (
    command_id,
    order_id,
    idempotency_key,
    amount,
    currency,
    status
)
VALUES (
    gen_random_uuid(),
    9001,
    'order-9001-payment-v1',
    125.00,
    'USD',
    'pending'
);

COMMIT;
~~~

Worker đọc command đã commit, gọi provider với cùng idempotency key, rồi lưu kết quả trong transaction mới.

### 25.1. Provider idempotency

Nếu worker timeout và không biết provider đã charge chưa, retry cùng provider idempotency key hoặc query operation status. Không tạo key mới cho cùng business intent.

### 25.2. Unknown state

Nếu provider không hỗ trợ lookup hoặc idempotency, trạng thái có thể cần manual reconciliation. Đừng tự động đánh dấu failed chỉ vì timeout.

### 25.3. Separate authorization and capture

Payment workflows thường có nhiều steps. Lưu state riêng cho authorization, capture, void và refund. Compensation cần theo provider semantics.

## 26. Reconciliation

Reconciliation so sánh trạng thái local với external system để giải quyết những outcomes không rõ hoặc events bị mất.

### 26.1. Khi cần reconciliation?

- Client mất connection quanh COMMIT.
- Provider timeout sau khi nhận request.
- Outbox relay publish rồi crash.
- Consumer xử lý side effect rồi mất acknowledgement.
- Saga step ở trạng thái processing quá lâu.
- External webhook đến trễ hoặc trùng.
- Operator khôi phục coordinator sau outage.

### 26.2. Reconciliation key

Dùng order ID, provider operation ID, idempotency key, event ID hoặc stable business reference. Không dựa vào fuzzy matching nếu có thể lưu identity rõ.

### 26.3. Reconciliation outcomes

- External và local đều thành công: mark completed.
- External chưa xử lý: retry cùng key.
- External thành công, local chưa ghi nhận: cập nhật local state theo provider evidence.
- External thất bại chắc chắn: mark failed hoặc start compensation.
- Không xác định được: giữ unknown/manual_review, không đoán.

### 26.4. Audit trail

Lưu request IDs, provider references, timestamps, attempt counts, response codes và state transitions. Không lưu payment secrets hoặc sensitive credentials.

### 26.5. Reconciliation không phải sửa số liệu mù

Mỗi correction phải dựa trên authoritative evidence và được audit. Một job tự động không nên tự hoàn tiền hoặc tạo lại order chỉ từ timeout message.

## 27. Connection pools và transaction boundaries

Connection pooling giúp tái sử dụng connections, nhưng application cần hiểu transaction/session state.

### 27.1. Connection loss

Nếu connection mất trong transaction, backend có thể rollback khi phát hiện disconnect. Application cần bỏ connection hỏng và không trả nó về pool như connection sạch.

### 27.2. Pool reset

Pooler phải reset session state theo mode. SET variables, temporary tables, prepared statements, advisory locks và session-level state có thể không sống theo cách application mong đợi trong transaction pooling.

### 27.3. PgBouncer transaction pooling

Trong transaction pooling, client được gán một server connection chỉ trong transaction. Sau COMMIT/ROLLBACK, connection có thể được dùng bởi client khác. Không dựa vào session affinity ngoài transaction.

### 27.4. External calls

Không giữ pooled connection/transaction mở trong khi chờ API response nếu không cần. Điều đó làm giảm pool capacity và có thể gây queueing.

### 27.5. Broken connection

Sau network exception, kiểm tra driver/pool semantics. Đánh dấu connection unusable nếu cần và tạo connection mới. Không gửi COMMIT/ROLLBACK lần nữa qua một connection không còn tin cậy.

## 28. Savepoints không giải quyết external atomicity

SAVEPOINT cho phép rollback một phần công việc trong cùng PostgreSQL transaction.

~~~sql
BEGIN;

INSERT INTO app.orders(order_id, status)
VALUES (9002, 'created');

SAVEPOINT before_optional_step;

UPDATE app.orders
SET status = 'validated'
WHERE order_id = 9002;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
~~~

### 28.1. Scope

SAVEPOINT chỉ điều khiển changes trong cùng transaction. Nó không undo email, payment, broker publish hoặc remote side effect đã commit.

### 28.2. Subtransactions

Savepoints có thể giúp phục hồi từ lỗi một phần trong database transaction. Không dùng chúng như substitute cho saga/2PC.

### 28.3. External operation result

Nếu external call đã xảy ra giữa SAVEPOINT và ROLLBACK TO SAVEPOINT, external system không biết database rollback savepoint. Application phải có compensation/reconciliation.

## 29. Isolation levels và external workflows

Isolation level ảnh hưởng concurrency giữa transactions trong PostgreSQL; nó không mở rộng atomicity sang external systems.

### 29.1. Read Committed

Mỗi statement có snapshot riêng theo semantics Read Committed. Một workflow đọc state rồi gọi external API cần bảo vệ state transition khỏi concurrent changes.

### 29.2. Repeatable Read

Giữ snapshot ổn định trong transaction, nhưng có thể dẫn đến serialization-like errors khi concurrent updates xảy ra. Transaction dài qua network calls làm snapshot cũ tồn tại lâu.

### 29.3. Serializable

PostgreSQL có thể abort transaction để bảo đảm serializable behavior. Ứng dụng phải retry toàn bộ transaction khi nhận serialization failure. External side effects không nên thực hiện trước khi biết local transaction commit.

### 29.4. Optimistic state transitions

Dùng version/status predicate:

~~~sql
UPDATE app.orders
SET status = 'processing',
    version = version + 1
WHERE order_id = $1
  AND status = 'pending'
  AND version = $2;
~~~

Kiểm tra affected row count. Chỉ một worker có thể chuyển state từ version đã đọc nếu điều kiện khớp.

### 29.5. Row locks

SELECT ... FOR UPDATE có thể bảo vệ một state transition local. Giữ lock trong lúc gọi API dài có thể gây contention; thường nên claim intent ngắn rồi gọi ngoài transaction.

## 30. Timeouts ở các lớp

Một integration workflow có nhiều timeout khác nhau.

| Timeout | Phạm vi | Ý nghĩa |
| --- | --- | --- |
| connect_timeout | Client kết nối PostgreSQL | Giới hạn thời gian mở connection |
| statement_timeout | PostgreSQL statement | Hủy statement khi vượt thời gian |
| lock_timeout | Chờ lock acquisition | Hủy nếu chờ lock quá lâu |
| idle_in_transaction_session_timeout | Session idle trong transaction | Đóng session idle quá lâu |
| TCP/network timeout | Transport | Giới hạn thời gian chờ mạng |
| HTTP client timeout | External API request | Client ngừng chờ response |
| Provider operation timeout | External system | Contract riêng của provider |
| Workflow deadline | Toàn business process | Giới hạn tổng thời gian |

### 30.1. Timeout không phải cancellation guarantee

Client timeout chỉ cho biết client không chờ thêm. External server có thể tiếp tục xử lý. PostgreSQL backend cũng có thể chưa nhận được cancellation ngay.

### 30.2. Layered deadlines

Chọn timeout sao cho tổng workflow deadline lớn hơn các bước cần thiết nhưng mỗi dependency có giới hạn riêng. Để đủ thời gian cho cleanup/reconciliation.

### 30.3. Timeout và retry

Nếu timeout xảy ra sau khi request được gửi, outcome có thể unknown. Retry cùng idempotency key hoặc query status.

## 31. Circuit breaker và bulkhead

### 31.1. Circuit breaker

Khi dependency có tỷ lệ lỗi cao, circuit breaker tạm dừng requests mới để tránh quá tải. Sau cooldown, thử một số requests probe trước khi mở lại.

### 31.2. Bulkhead

Tách concurrency pools/queues theo dependency để một external service chậm không chiếm toàn bộ worker threads/connections.

### 31.3. Queue buffering

Outbox/queue giúp tách database commit latency khỏi external API latency. Queue cần backpressure và capacity limits.

### 31.4. Không mất intent khi circuit mở

Nếu business change đã commit, command/event phải được lưu durable (ví dụ outbox). Circuit breaker chỉ trì hoãn delivery, không xóa intent.

## 32. Ordering và concurrent delivery

Events của cùng aggregate có thể cần thứ tự.

### 32.1. Aggregate version

Tăng version trong business transaction và lưu cùng outbox event. Consumer có thể phát hiện event đến sai thứ tự hoặc bị thiếu version.

### 32.2. Partitioning

Broker partition key theo aggregate ID có thể giữ ordering trong partition theo semantics broker. Ordering toàn hệ thống thường không được bảo đảm.

### 32.3. Outbox ordering

ORDER BY occurred_at không tự bảo đảm mọi workers publish theo đúng thứ tự nếu nhiều workers claim các batches khác nhau. Nếu ordering quan trọng, serialize theo aggregate hoặc dùng sequence/version checks.

### 32.4. Consumer version guard

Consumer có thể chỉ áp dụng event version kế tiếp, giữ event đến sớm/muộn trong inbox hoặc retry khi gap được xử lý. Thiết kế theo domain.

### 32.5. Clock ordering

Không dùng timestamp từ nhiều hosts làm thứ tự tuyệt đối. Dùng aggregate version hoặc database-generated sequence khi cần causal order.

## 33. Transactional inbox cho incoming webhooks

External provider gửi webhook có thể retry cùng event nhiều lần. Xác minh signature và deduplicate bằng event ID.

~~~sql
CREATE TABLE app.provider_webhook_inbox (
    provider_name text NOT NULL,
    provider_event_id text NOT NULL,
    payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    PRIMARY KEY (provider_name, provider_event_id)
);
~~~

### 33.1. Receive flow

1. Xác minh webhook signature.
2. Parse và validate event.
3. Insert inbox row với unique provider event ID.
4. Nếu duplicate, trả acknowledgement phù hợp.
5. Worker xử lý event trong transaction.
6. Cập nhật business state và processed_at cùng transaction.
7. Retry nếu lỗi transient.

### 33.2. Acknowledge timing

Chỉ trả success cho provider sau khi event đã được lưu durable hoặc xử lý theo contract. Nếu trả success trước khi persist, process crash có thể làm mất event.

### 33.3. Out-of-order webhooks

Webhook có thể đến sai thứ tự. Kiểm tra provider event version/timestamp/status transition và query authoritative provider state khi cần.

### 33.4. Signature replay

Signature verification không tự ngăn replay. Dùng event ID deduplication, timestamp tolerance và provider security guidance.

## 34. External file/object storage workflow

Database và object storage không chia sẻ transaction.

### 34.1. Upload trước, metadata sau

Nếu upload object thành công nhưng DB insert thất bại, object orphan. Dùng temporary key và garbage collector có retention window.

### 34.2. Metadata trước, upload sau

Nếu DB commit metadata trước nhưng upload thất bại, row tham chiếu object chưa có. Lưu state pending_upload và chỉ expose object khi ready.

### 34.3. Workflow có trạng thái

~~~text
pending_upload
      |
      v
uploading
      |
      +---- success ----> available
      |
      +---- failure ----> retry / failed
      |
      +---- unknown ----> reconcile provider object
~~~

### 34.4. Cleanup

Chỉ xóa orphan objects sau khi kiểm tra age, ownership và operation state. Không xóa object chỉ vì một database query tạm thời không tìm thấy row.

## 35. External payment workflow

Payment cần state machine rõ ràng vì timeout và duplicate charge có hậu quả nghiệp vụ.

### 35.1. Các trạng thái

Ví dụ:
- pending.
- authorization_requested.
- authorized.
- capture_requested.
- captured.
- failed.
- void_requested.
- voided.
- refund_requested.
- refunded.
- unknown.
- manual_review.

### 35.2. Idempotency per operation

Authorization, capture và refund có thể cần idempotency keys riêng nhưng ổn định cho từng intent. Không tái sử dụng key của authorization cho một refund khác.

### 35.3. Provider reference

Lưu provider payment/operation IDs và response metadata cần thiết để query status.

### 35.4. Timeout

Nếu capture request timeout, trạng thái local là unknown cho đến khi provider status được xác minh. Retry cùng key theo provider contract.

### 35.5. Compensation

Nếu order không thể fulfill sau authorization, có thể void authorization. Nếu đã capture, có thể refund. Đây là business compensation, không phải database rollback.

## 36. Foreign systems và data consistency models

### 36.1. Strong consistency trong một database

Một transaction PostgreSQL có thể cung cấp atomicity/consistency trong phạm vi database transaction.

### 36.2. Eventual consistency

Outbox/consumer cập nhật downstream projection sau commit. Trong một khoảng thời gian, database chính và search index/cache/reporting store có thể khác nhau.

### 36.3. Read-your-writes

Nếu client cần đọc thấy thay đổi ngay, đọc từ primary/local authoritative store hoặc chờ event/consumer acknowledgement theo contract.

### 36.4. Monotonic state transitions

Định nghĩa state machine không cho phép trạng thái quay lùi ngoài compensation được chỉ định. Dùng conditional UPDATE và version guards.

### 36.5. Reconciliation window

Định nghĩa bao lâu một operation có thể ở pending/unknown trước khi alert/manual review. Đừng tự đánh dấu failed chỉ vì một delay ngắn.

## 37. Distributed transaction qua nhiều databases

Một ứng dụng có thể cập nhật hai PostgreSQL databases độc lập.

### 37.1. Hai local commits

Nếu database A commit thành công và database B mất kết nối trước commit, trạng thái hai databases khác nhau. Local transaction ở A không thể rollback bằng một ROLLBACK gửi tới B sau khi A đã commit.

### 37.2. Coordinator

Nếu cả participants hỗ trợ 2PC, transaction manager có thể điều phối prepare/commit. Nếu không, dùng saga/outbox và reconciliation.

### 37.3. Dual writes

Ghi database A rồi database B trực tiếp là dual-write problem. Một crash giữa hai writes tạo divergence.

### 37.4. Replication/CDC

CDC có thể truyền changes từ một database sang downstream. Nó tạo asynchronous propagation, không phải synchronous global atomic commit.

### 37.5. Source of truth

Chọn một authoritative system cho mỗi loại dữ liệu. Tránh hai databases cùng được xem là owner của cùng field mà không có conflict resolution.

## 38. Distributed locks không thay transaction coordination

Advisory locks hoặc external distributed locks có thể giúp một worker claim work. Chúng không tự đảm bảo atomic commit giữa database và external service.

### 38.1. Lock lease

Distributed lock có thể hết hạn khi worker vẫn đang chạy. Worker cũ có thể tiếp tục side effect sau khi worker mới lấy lock.

### 38.2. Fencing token

Dùng monotonically increasing fencing token nếu downstream resource có thể từ chối writes từ lock holder cũ.

### 38.3. Idempotency vẫn cần

Lock giảm concurrency nhưng không xử lý response loss, retries, duplicate messages hoặc crash sau side effect.

## 39. Observability cho transaction và integration

Theo dõi cả PostgreSQL và external workflow.

### 39.1. Database metrics

- Active/idle-in-transaction sessions.
- Long-running transactions.
- Lock waits và deadlocks.
- Transaction commits/rollbacks.
- Connection failures.
- WAL/replication lag.
- Prepared transactions.
- Outbox/inbox table sizes.

### 39.2. Workflow metrics

- Operations pending/processing/unknown.
- Retry attempts và retry age.
- Outbox oldest unpublished age.
- Publish failure rate.
- Consumer lag.
- Inbox duplicate count.
- Saga duration/compensation count.
- Provider timeout/error rates.
- Reconciliation backlog.

### 39.3. Correlation identifiers

Ghi request_id, idempotency_key, saga_id, event_id, aggregate_id và provider_reference xuyên suốt logs/traces. Không log secrets hoặc full payment data.

### 39.4. Prepared transaction monitoring

~~~sql
SELECT
    gid,
    prepared,
    owner,
    database,
    now() - prepared AS prepared_age
FROM pg_prepared_xacts
ORDER BY prepared;
~~~

Alert cho prepared transactions tồn tại lâu hơn expected protocol window. Resolution phải theo coordinator decision log.

### 39.5. Long transactions

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 300) AS query
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start;
~~~

Tìm idle-in-transaction và transactions giữ locks/snapshots lâu.

## 40. Failure injection và testing

Reliability phải được thử trong môi trường có thể kiểm soát.

### 40.1. Mất kết nối trước COMMIT

Ngắt connection trước khi gửi COMMIT và xác minh transaction rollback khi session kết thúc.

### 40.2. Mất response sau COMMIT

Dùng proxy/test harness để drop response sau khi server nhận COMMIT. Xác minh client có thể query operation status bằng idempotency key.

### 40.3. Worker crash sau publish

Mô phỏng broker nhận event nhưng worker crash trước khi đánh dấu outbox published. Consumer phải xử lý duplicate an toàn.

### 40.4. Consumer crash trước commit

Đảm bảo inbox claim và business update rollback cùng nhau để event có thể được retry.

### 40.5. Provider timeout

Mô phỏng provider xử lý request nhưng response timeout. Worker phải dùng cùng idempotency key hoặc query status.

### 40.6. Coordinator crash

Nếu dùng 2PC, rehearsal coordinator crash sau prepare và xác minh recovery decision log trước khi resolve prepared transactions.

### 40.7. Clock skew và delayed messages

Thử webhook/event đến trễ, out-of-order và timestamp không đồng bộ. Dùng version/identity thay vì chỉ dựa timestamp.

## 41. Security cho external integrations

- Dùng TLS và verify certificates cho database/API connections.
- Quản lý secrets trong secret manager.
- Least privilege cho remote roles và application roles.
- Không ghi credentials/payment tokens vào outbox payload.
- Verify webhook signatures và chống replay.
- Validate payload schema/version.
- Giới hạn request size và rate.
- Redact PII trong logs/traces.
- Rotate provider credentials có kế hoạch.
- Audit manual compensation/refund actions.

## 42. Anti-patterns thường gặp

| Anti-pattern | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Gọi payment API trong transaction dài | Giữ locks/connection và vẫn không atomic | Outbox + provider idempotency |
| Nghĩ rollback DB undo email | Email đã gửi vẫn tồn tại | Gửi sau commit qua outbox |
| Retry sau connection error quanh COMMIT | Có thể duplicate business operation | Query theo idempotency key |
| Mỗi retry tạo key mới | Provider không deduplicate | Giữ key ổn định cho cùng intent |
| SELECT rồi INSERT idempotency key | Race giữa concurrent requests | Unique constraint + ON CONFLICT |
| Publish event trước DB commit | Consumer thấy event của transaction rollback | Transactional outbox |
| Mark published trước broker acknowledgement | Event có thể mất | Publish rồi ghi acknowledgement |
| Giả định broker exactly-once bao trùm DB | Cross-system side effects vẫn duplicate | Inbox/idempotent consumer |
| Consumer ack trước khi persist | Crash có thể mất event | Persist inbox trước acknowledgement |
| Inbox và business update ở transactions khác nhau | Duplicate hoặc mất consistency | Commit cùng transaction |
| Giữ DB transaction mở khi gọi API | Lock/snapshot/connection bị giữ lâu | Commit intent, call ngoài transaction |
| Timeout đồng nghĩa operation failed | Provider có thể đã xử lý | Unknown state và reconciliation |
| Saga compensation là rollback hoàn hảo | Side effects không thể đảo ngược | Business compensation rõ ràng |
| Dùng 2PC với HTTP service không hỗ trợ | Không có prepare protocol | Outbox/saga |
| Bỏ quên prepared transactions | Locks và xid resources tồn tại lâu | Coordinator recovery/monitoring |
| Tự commit prepared transaction theo tuổi | Có thể trái decision log | Resolve theo coordinator |
| Coi FDW là global atomic commit | Remote/local failure có thể lệch | Đánh giá semantics, outbox/saga |
| Retry vô hạn | Retry storm | Backoff, jitter, deadline, budget |
| Dựa timestamp để order events | Clock skew/out-of-order | Aggregate version/sequence |
| Không reconciliation unknown states | Divergence tồn tại lâu | Durable reconciliation workflow |

## 43. Bài tập thực hành PostgreSQL

Thực hiện trong lab/staging với test services. Không tạo payment, gửi email hoặc thay đổi external production resources chỉ để thử nghiệm.

1. **Local atomicity:** tạo transaction cập nhật hai tables và rollback.
2. **Commit:** commit transaction và xác minh state từ connection khác.
3. **Disconnect:** ngắt connection trước COMMIT và quan sát rollback.
4. **Ambiguous commit:** mô phỏng mất response sau COMMIT.
5. **SQLSTATE:** phân loại 40001, 40P01, 23505 và class 08 errors.
6. **Serialization retry:** tạo concurrent serializable transactions và retry toàn transaction.
7. **Deadlock retry:** tạo deadlock có kiểm soát và xử lý 40P01.
8. **Client timeout:** phân biệt client timeout với server cancellation.
9. **Idempotency schema:** tạo bảng idempotency_requests có unique key.
10. **Request hash:** dùng hash để phát hiện cùng key nhưng payload khác.
11. **Concurrent requests:** gửi hai requests cùng idempotency key.
12. **Duplicate response:** trả lại stored response cho request lặp.
13. **Key expiry:** thiết kế retention theo retry window.
14. **Local transaction:** ghi business row và idempotency result cùng transaction.
15. **Unique conflict:** phân biệt duplicate request với business unique violation.
16. **Backoff:** triển khai exponential backoff có cap.
17. **Jitter:** thêm random jitter cho retry workers.
18. **Deadline:** giới hạn tổng retry duration.
19. **Retry budget:** tạo metric retries/request.
20. **Outbox schema:** tạo outbox_events với event_id.
21. **Atomic outbox:** update order và insert event trong cùng transaction.
22. **Rollback test:** làm outbox insert fail và xác minh business update rollback.
23. **Relay:** viết worker lấy unpublished events.
24. **SKIP LOCKED:** chạy hai relay workers cạnh tranh.
25. **Lease:** thêm locked_by/locked_until cho outbox claims.
26. **Publish crash:** mô phỏng crash sau publish trước published_at.
27. **Duplicate delivery:** xác minh consumer chịu được duplicate.
28. **Inbox schema:** tạo inbox_events với unique consumer/event key.
29. **Inbox atomicity:** commit inbox claim và business update cùng transaction.
30. **Consumer rollback:** làm business update fail và xác minh inbox claim rollback.
31. **Retention:** xác định outbox/inbox retention policy.
32. **Ordering:** thêm aggregate_version vào events.
33. **Out-of-order:** mô phỏng events đến sai thứ tự.
34. **Saga schema:** tạo sagas và saga_steps tables.
35. **Saga state:** triển khai conditional state transition.
36. **Optimistic locking:** dùng version column để tránh concurrent updates.
37. **Compensation:** mô phỏng reserve inventory rồi release.
38. **Payment timeout:** mô phỏng provider xử lý nhưng response timeout.
39. **Provider key:** retry payment với cùng idempotency key.
40. **Unknown state:** lưu operation unknown và reconcile.
41. **Orchestration:** triển khai coordinator đơn giản cho saga.
42. **Choreography:** thiết kế event-driven workflow và phân tích observability.
43. **2PC setting:** kiểm tra max_prepared_transactions.
44. **Prepared transaction:** thử PREPARE TRANSACTION trong lab.
45. **Commit prepared:** hoàn tất bằng COMMIT PREPARED.
46. **Rollback prepared:** hoàn tất bằng ROLLBACK PREPARED.
47. **Catalog:** truy vấn pg_prepared_xacts.
48. **In-doubt:** mô phỏng coordinator crash sau prepare và đọc recovery log.
49. **Lock retention:** quan sát locks của prepared transaction.
50. **Cleanup policy:** viết runbook resolve prepared transaction theo coordinator.
51. **FDW:** cài postgres_fdw và query remote table.
52. **FDW transaction:** thử local/remote updates trong một local transaction lab.
53. **FDW failure:** mô phỏng network loss và phân tích commit outcome.
54. **dblink:** gọi remote query và quản lý connection lifecycle.
55. **Dual database:** mô phỏng commit DB A thành công, DB B thất bại.
56. **Outbox vs 2PC:** chọn pattern cho hai PostgreSQL services.
57. **Webhook inbox:** lưu provider event IDs và deduplicate.
58. **Webhook signature:** xác minh signature trước khi persist.
59. **Replay:** gửi lại webhook và xác minh business effect không lặp.
60. **Object storage:** thiết kế pending_upload/available states.
61. **Orphan cleanup:** xây garbage collector cho uploaded objects không có metadata.
62. **Email:** tạo outbox event cho email sau order commit.
63. **Search projection:** cập nhật search index bằng asynchronous consumer.
64. **PgBouncer:** kiểm tra behavior trong transaction pooling.
65. **Session state:** thử SET/temp table/session advisory lock qua transaction pooling.
66. **Connection pool:** xử lý broken connection sau network exception.
67. **Timeout layers:** cấu hình connect/statement/lock/HTTP/workflow deadlines.
68. **Circuit breaker:** mô phỏng provider outage và mở circuit.
69. **Bulkhead:** tách worker pools theo external dependency.
70. **Backpressure:** giới hạn outbox relay concurrency khi provider chậm.
71. **Monitoring:** tạo dashboard outbox age và retry rate.
72. **Reconciliation:** tạo report operations ở trạng thái unknown quá lâu.
73. **Correlation:** truyền request_id/event_id/saga_id qua logs.
74. **Prepared alert:** cảnh báo prepared transactions quá tuổi policy.
75. **Long transaction:** tìm idle-in-transaction sessions.
76. **Failure injection:** drop connection ở các thời điểm quanh COMMIT.
77. **Worker crash:** crash relay sau publish và kiểm tra duplicate handling.
78. **Restore:** restore database có outbox pending và tiếp tục relay.
79. **DR rehearsal:** phục hồi database rồi reconcile external provider states.
80. **Thiết kế tổng hợp:** xây order/payment/shipping workflow với PostgreSQL transaction, idempotency keys, transactional outbox, inbox deduplication, saga compensation, reconciliation, monitoring và tested failure recovery.

## 44. Checklist thiết kế integration

### Transaction boundary

- [ ] Xác định rõ dữ liệu nào nằm trong một PostgreSQL transaction.
- [ ] External API/broker/storage có transaction protocol riêng hay không.
- [ ] Không giả định local rollback undo external side effect.
- [ ] Tránh giữ transaction mở trong network calls dài.
- [ ] Xử lý ambiguous outcome quanh COMMIT.

### Idempotency và retry

- [ ] Mỗi business intent có stable idempotency key.
- [ ] Key được unique trong scope phù hợp.
- [ ] Request hash phát hiện payload mismatch.
- [ ] Retry có bounded attempts, backoff, jitter và deadline.
- [ ] Connection errors quanh COMMIT được reconcile.
- [ ] Provider API hỗ trợ idempotency/status lookup đã được xác minh.

### Outbox/inbox

- [ ] Business state và outbox event commit cùng transaction.
- [ ] Relay chỉ publish committed events.
- [ ] Relay chịu được crash sau publish.
- [ ] Consumer deduplicate bằng inbox unique key.
- [ ] Inbox claim và business update commit cùng transaction.
- [ ] Ordering/version và retention được định nghĩa.
- [ ] Outbox backlog có alert và backpressure.

### Saga/2PC

- [ ] Saga steps và compensation được định nghĩa.
- [ ] Unknown state không bị tự đánh dấu failed.
- [ ] 2PC chỉ dùng khi mọi participants hỗ trợ.
- [ ] Coordinator có durable decision log.
- [ ] Prepared transactions được monitor và recovery đúng policy.
- [ ] Không để GID in-doubt không có owner.

### Operations

- [ ] Connection pool xử lý broken connections.
- [ ] Timeout từng layer được cấu hình.
- [ ] Circuit breaker/bulkhead phù hợp.
- [ ] Correlation IDs xuyên suốt logs.
- [ ] Reconciliation có lịch và owner.
- [ ] Failure injection/restore drills được thực hiện.
- [ ] Secrets/PII được bảo vệ trong outbox và logs.

## 45. Tổng kết

PostgreSQL transaction cung cấp atomicity cho những thay đổi thuộc database transaction. Một external API, broker, object store hoặc database độc lập có resource manager và failure modes riêng. Network failure có thể khiến client không biết COMMIT đã thành công hay chưa, hoặc external system đã thực hiện side effect dù response bị mất.

~~~text
LOCAL BUSINESS CHANGE
       |
       v
POSTGRESQL TRANSACTION
  update business state
  insert outbox command/event
       |
       v
COMMIT
       |
       v
RELAY / WORKER
       |
       v
EXTERNAL SYSTEM
       |
       +---- acknowledged ----> record result
       |
       +---- timeout/lost reply -> unknown
                                      |
                                      v
                              idempotent retry
                              or reconciliation
~~~

Những nguyên tắc quan trọng:

- **ACID có phạm vi.** Một PostgreSQL transaction không tự bao gồm HTTP, email, message broker, object storage hoặc một database độc lập.
- **Mất kết nối quanh COMMIT tạo ambiguous outcome.** Client không thể suy ra transaction rollback chỉ từ connection error.
- **Không retry side effects một cách mù quáng.** Dùng stable operation IDs và idempotency keys để nhận diện cùng một business intent.
- **Retry theo loại lỗi.** Serialization/deadlock có thể cần retry toàn transaction; connection loss quanh commit cần xác minh trạng thái.
- **Outbox ghi durable intent cùng business state.** Relay publish sau commit và consumer phải chịu được duplicate delivery.
- **Inbox deduplicates trong local transaction.** Claim event và business update phải commit cùng nhau.
- **Saga chia workflow thành local transactions.** Compensation là business action, không phải rollback vật lý của side effect đã xảy ra.
- **2PC cần mọi participants và coordinator hỗ trợ.** Prepared transactions có thể giữ locks; phải có durable decision log và recovery procedure.
- **FDW/dblink không tự tạo global atomicity.** Hiểu semantics và failure behavior của từng remote integration.
- **Timeout không đồng nghĩa operation failed.** Dùng unknown state, provider status lookup và reconciliation.
- **Giữ database transactions ngắn.** Không giữ locks, snapshots và pooled connections trong lúc chờ external network calls dài.
- **Test failure points.** Mô phỏng lost commit response, duplicate publish, worker crash và provider timeout trước khi production rollout.

Một integration đáng tin cậy không dựa vào giả định mạng luôn trả lời đúng lúc. Nó lưu durable intent, nhận diện retries, xử lý duplicate delivery, ghi lại trạng thái không chắc chắn và có quy trình reconciliation để đưa các hệ thống về trạng thái nghiệp vụ nhất quán.

