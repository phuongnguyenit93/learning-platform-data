# LISTEN, NOTIFY và giới hạn của thông báo trong cơ sở dữ liệu PostgreSQL

Trong các ứng dụng có nhiều kết nối đến PostgreSQL, một tiến trình đôi khi cần biết **dữ liệu vừa thay đổi** để làm mới cache, đánh thức worker, cập nhật dashboard hoặc bắt đầu xử lý các tác vụ mới. Nếu worker cứ liên tục chạy `SELECT` để kiểm tra bảng, hệ thống có thể phát sinh rất nhiều truy vấn khi không có việc gì mới.

PostgreSQL có cơ chế **asynchronous notifications** với các thành phần chính:

- `LISTEN channel`: đăng ký một **session** lắng nghe thông báo trên kênh có tên.
- `NOTIFY channel, 'payload'`: gửi một notification đến những sessions lắng nghe channel đó.
- `pg_notify(channel, payload)`: function tương đương, thuận tiện khi channel/payload là biểu thức hoặc được bind bằng JDBC.

Ví dụ có hai session cùng kết nối đến một database:

~~~sql
-- Session A: đăng ký lắng nghe.
LISTEN app_events;

-- Session B: gửi thông báo.
NOTIFY app_events, 'changed';
~~~

Sau khi transaction gửi **COMMIT**, listener đủ điều kiện có thể nhận một notification chứa tên channel, payload và process ID của backend gửi.

**Nhưng LISTEN/NOTIFY không phải hệ thống hàng đợi bền vững.** Một listener mất kết nối có thể bỏ lỡ các notification. PostgreSQL không tự lưu per-consumer offset, không cung cấp replay cho những thông báo bị bỏ lỡ và không biết nghiệp vụ đã được xử lý thành công hay chưa.

Bài **“LISTEN, NOTIFY và giới hạn của thông báo trong cơ sở dữ liệu”**, thuộc chương **Kết nối ứng dụng**, module **Database Engine Relational PostgreSQL**, trình bày cú pháp, ngữ nghĩa transaction, phạm vi database/session, thứ tự/gộp thông báo, payload/queue limits, bảo mật, ứng dụng Java/pgJDBC, thiết kế outbox, vận hành và các bài tập thực hành.

> **An toàn:** ví dụ tạo bảng và trigger chỉ dành cho database lab. Đừng dùng NOTIFY chứa secrets, PII hoặc dữ liệu giao dịch quan trọng làm phương tiện lưu trữ duy nhất. Khi thay đổi hệ thống production, kiểm tra quyền, tải thông báo và transaction semantics trước.

---

## 1. Vì sao không chỉ polling?

Một worker có thể liên tục chạy:

~~~sql
SELECT task_id, title
FROM tasks
WHERE status = 'pending'
ORDER BY task_id
LIMIT 10;
~~~

Nếu không có task mới, những truy vấn lặp chỉ tạo thêm round trips, planning/execution, I/O và hoạt động trên connection.

Sơ đồ polling:

~~~text
Worker               Database
  |----- SELECT -------->|
  |<------ 0 rows -------|
  |----- SELECT -------->|
  |<------ 0 rows -------|
  |----- SELECT -------->|
  |<------ 1 row --------|
~~~

Với NOTIFY, một transaction ghi dữ liệu có thể gửi tín hiệu:

~~~text
Application --INSERT task + NOTIFY--> PostgreSQL
                     |
                   COMMIT
                     |
                     v
                   Listener
                     |
                     v
               SELECT tasks
~~~

Worker chủ yếu chỉ query khi có tín hiệu hoặc theo lịch reconciliation dự phòng. Cách này giảm độ trễ phát hiện khi online nhưng **không xóa hoàn toàn nhu cầu polling** nếu dữ liệu không được phép bỏ sót.

## 2. Phân biệt notification và business event

Một notification có thể chỉ chứa:

~~~text
channel = jobs_changed
payload = changed
~~~

Một business event cần xử lý đáng tin cậy có thể chứa:

~~~json
{
  "event_id": 901,
  "event_type": "task_created",
  "task_id": 41,
  "version": 1
}
~~~

Nếu event chỉ tồn tại trong NOTIFY, một listener không online lúc phát sẽ không tự nhận lại event sau khi reconnect.

Một thiết kế tốt thường là:

- Lưu task/event trong **bảng bền vững**.
- Dùng NOTIFY làm **hint đánh thức**.
- Khi nhận hint, query bảng để lấy các rows cần xử lý.
- Có cơ chế retry, idempotency và reconciliation.

### 2.1. Khi nào NOTIFY đơn lẻ có thể đủ?

Với một tín hiệu **được phép mất**, ví dụ khuyến khích làm mới UI hoặc invalidation cache có TTL, NOTIFY trực tiếp có thể đáp ứng. Tuy nhiên khi không có NOTIFY mới sau một lần bị lỡ, cache vẫn có thể stale nếu không có TTL/polling.

## 3. LISTEN có cú pháp gì?

~~~sql
LISTEN channel_name;
~~~

Ví dụ:

~~~sql
LISTEN inventory_changed;
~~~

Đăng ký thuộc **session PostgreSQL hiện tại**.

Một session là một kết nối/backend. Khi session bị đóng:

- Đăng ký LISTEN của session mất.
- Kết nối mới không tự kế thừa LISTEN.
- Ứng dụng phải gửi LISTEN lại sau reconnect.

### 3.1. LISTEN không query dữ liệu

`LISTEN inventory_changed` không kiểm tra có bao nhiêu hàng trong bảng inventory và không nhận những thông báo từ trước khi đăng ký. Nó chỉ tham gia cơ chế nhận các notification tương lai phù hợp.

## 4. NOTIFY có cú pháp gì?

~~~sql
NOTIFY channel_name;

NOTIFY channel_name, 'payload';
~~~

Ví dụ:

~~~sql
NOTIFY inventory_changed, 'item_updated';
~~~

Cú pháp `NOTIFY` dùng identifier cho channel và một chuỗi payload literal tùy chọn.

Nếu cần tạo payload từ dữ liệu động, `pg_notify` tiện hơn.

### 4.1. NOTIFY vẫn hợp lệ nếu chưa ai LISTEN

Một session có thể gửi thông báo khi không có listener. Nó không trở thành event bền vững chờ người đến sau đăng ký.

### 4.2. NOTIFY không ghi một hàng vào bảng nghiệp vụ

Không có một bảng `inventory_changed` tự được tạo. Channel chỉ là tên logic của luồng thông báo giữa sessions.

## 5. pg_notify cho dữ liệu động

~~~sql
SELECT pg_notify(
    'inventory_changed',
    json_build_object(
        'kind', 'item_updated',
        'item_id', 1001
    )::TEXT
);
~~~

`pg_notify(channel TEXT, payload TEXT)` có thể được gọi từ SQL hoặc PL/pgSQL.

Trong function/procedure PL/pgSQL, nếu bỏ qua kết quả, dùng:

~~~sql
PERFORM pg_notify(
    'inventory_changed',
    'changed'
);
~~~

### 5.1. Tại sao nên gửi hint thay vì cả record?

Payload rất nhỏ, dễ kiểm soát bytes, không phải nơi lưu trữ dữ liệu nhạy cảm, và listener luôn lấy record từ nguồn có GRANT/RLS phù hợp.

## 6. Channel names và chữ hoa/chữ thường

Tên channel trong `LISTEN` và `NOTIFY` theo quy tắc identifier PostgreSQL.

~~~sql
LISTEN AppEvents;
~~~

Tên không quote thường được chuẩn hóa thành lowercase. Nếu dùng:

~~~sql
LISTEN "AppEvents";
~~~

thì identifier phân biệt chữ hoa/thường.

Đối số channel của:

~~~sql
SELECT pg_notify('AppEvents', 'changed');
~~~

là text, không được SQL parser đổi thành lowercase như identifier trần. Vì vậy không trộn tên được quote và tên không quote vô ý.

**Quy ước tốt:** dùng tên chữ thường, snake_case, ví dụ `orders_changed`.

### 6.1. Channel identifier không thể dài tùy ý

Với cấu hình PostgreSQL thông dụng, identifier có giới hạn mặc định khoảng **63 bytes**. Không tạo channel chứa JSON, token hoặc một đường dẫn tùy ý dài.

## 7. Phạm vi của LISTEN/NOTIFY là một database

~~~text
PostgreSQL cluster
  |
  +-- database_a
  |     +-- Session A: LISTEN events
  |     +-- Session B: NOTIFY events
  |                  |
  |                  +--> A nhận được
  |
  +-- database_b
        +-- Session C: LISTEN events
                     |
                     +--> Không nhận event từ database_a
~~~

**Cùng cluster không đồng nghĩa cùng database.** LISTEN/NOTIFY không tự phát thông báo từ database A sang B.

Nó cũng không phải cơ chế pub/sub tự động xuyên nhiều PostgreSQL clusters hoặc độc lập hoạt động trên replicas.

## 8. Đăng ký LISTEN có hiệu lực lúc COMMIT

Nếu thực hiện:

~~~sql
BEGIN;

LISTEN orders_changed;

COMMIT;
~~~

đăng ký LISTEN có hiệu lực khi transaction commit thành công theo ngữ nghĩa PostgreSQL.

Nếu:

~~~sql
BEGIN;

LISTEN orders_changed;

ROLLBACK;
~~~

đăng ký mới không được áp dụng.

### 8.1. Vì sao quan trọng?

Nếu code mở transaction rồi LISTEN nhưng không COMMIT, listener có thể chưa thực sự được đăng ký. Một notification được phát trong khoảng đó sẽ không đợi nó đăng ký.

UNLISTEN trong transaction cũng có semantics commit/rollback tương ứng.

## 9. Session listener và session publisher

Mở hai terminal/psql connections cùng một database.

**Session A:**

~~~sql
LISTEN demo_channel;
~~~

**Session B:**

~~~sql
NOTIFY demo_channel, 'hello';
~~~

Sau khi B commit, session A có thể nhận thông báo. Trong psql, nếu chưa hiển thị ngay, chạy:

~~~sql
SELECT 1;
~~~

để client xử lý thêm protocol traffic và quan sát các notifications.

Thông báo có thể hiển thị kèm:

- Tên channel.
- Payload.
- PID của backend gửi.

### 9.1. PID không phải event ID

~~~sql
SELECT pg_backend_pid();
~~~

trả process ID backend của session hiện tại. PID giúp chẩn đoán/self-notifications, nhưng không phải một khóa sự kiện bền vững; nó có thể thay đổi sau reconnect và bị tái sử dụng.

## 10. NOTIFY chỉ phát sau COMMIT

Trong session B:

~~~sql
BEGIN;

NOTIFY demo_channel, 'not_yet_committed';

-- Chưa COMMIT, listener chưa nhận notification này.
~~~

Chỉ khi:

~~~sql
COMMIT;
~~~

notification mới được phát đến listeners thích hợp.

### 10.1. Vì sao đây là tính chất tốt?

Nếu code INSERT một task rồi NOTIFY nhưng sau đó rollback transaction, worker không bị đánh thức bởi một task chưa tồn tại theo trạng thái committed.

### 10.2. Gửi thành công không có nghĩa xử lý thành công

Sender COMMIT không đợi listener thực hiện xong business action, và PostgreSQL không có cơ chế per-consumer ACK để bảo đảm xử lý.

## 11. ROLLBACK hủy notification chưa commit

~~~sql
BEGIN;

NOTIFY demo_channel, 'will_disappear';

ROLLBACK;
~~~

Thông báo này không được phát như một event committed.

Các NOTIFY phát từ trigger trong cùng transaction ghi dữ liệu cũng chịu semantics tương tự.

**Không dùng notification như một lối thoát để gửi event bền vững khi transaction nghiệp vụ rollback.**

## 12. Listener đang trong transaction có thể nhận trễ

Một session đã LISTEN nhưng mở transaction dài có thể bị trì hoãn việc giao thông báo tới client cho tới khi transaction đó kết thúc.

Ví dụ session A:

~~~sql
BEGIN;

SELECT pg_sleep(5);

COMMIT;
~~~

Nếu session B phát NOTIFY trong lúc A còn transaction, A có thể chỉ quan sát notification sau khi nó kết thúc transaction.

### 12.1. Hệ quả

- Worker nhận event trễ.
- Long transaction giữ tài nguyên.
- Việc dọn notification queue có thể bị ảnh hưởng trong một số điều kiện.
- Ứng dụng có vẻ “ngủ” dù có data mới.

Đó là lý do listener nên giữ một **connection chuyên dụng**, ở trạng thái **không giữ transaction dài** khi chờ.

## 13. Race condition khi khởi động

Một sequence không an toàn:

~~~text
1. Worker SELECT pending jobs -> 0
2. API INSERT job, NOTIFY, COMMIT
3. Worker LISTEN channel, COMMIT
4. Worker chờ mãi
~~~

Notification bước 2 đã gửi khi worker chưa đăng ký. Job vẫn ở database nhưng worker có thể không được đánh thức.

### 13.1. Trình tự khởi động đúng hơn

~~~text
1. Mở connection listener.
2. LISTEN channel.
3. Commit đăng ký LISTEN.
4. Query/reconcile bảng durable tasks.
5. Chờ notifications.
6. Mỗi khi nhận notification, query lại bảng.
7. Poll định kỳ để tự phục hồi nếu mất tín hiệu.
~~~

Một NOTIFY tới ngay giữa bước 3 và 4 có thể liên quan dữ liệu đã được query nhìn thấy ở bước 4. Cách giải quyết là **xử lý idempotent**, không cố khẳng định mỗi NOTIFY là một event mới duy nhất.

## 14. Thông báo trùng trong cùng transaction được gộp

Nếu một transaction gửi nhiều notifications **cùng channel và cùng payload**:

~~~sql
BEGIN;

SELECT pg_notify('demo_channel', 'same');
SELECT pg_notify('demo_channel', 'same');
SELECT pg_notify('demo_channel', 'same');

COMMIT;
~~~

PostgreSQL có thể giao **một** notification cho cặp channel/payload giống hệt này.

### 14.1. Payload khác nhau

~~~sql
BEGIN;

SELECT pg_notify('demo_channel', 'a');
SELECT pg_notify('demo_channel', 'b');

COMMIT;
~~~

Hai payload khác nhau không bị gộp theo quy tắc duplicate cùng channel/payload.

### 14.2. Transactions riêng biệt

Nếu hai transactions khác nhau đều gửi `'same'` thì không bị gộp xuyên transactions theo quy tắc gộp trong một transaction.

### 14.3. Bài học

**Đừng suy số rows/events từ số notifications nhận được.** Một transaction có thể INSERT 1000 rows nhưng chỉ tạo một hint.

## 15. Thứ tự notifications

PostgreSQL có quy tắc đảm bảo thứ tự notifications phù hợp với thứ tự phát trong một transaction và thứ tự commit giữa những transactions.

Tuy nhiên cần phân biệt:

- Thứ tự gọi NOTIFY.
- Thứ tự commit.
- Thứ tự cấp sequence/identity ID.
- Thứ tự nghiệp vụ theo timestamp/version.

Chúng không phải lúc nào cũng giống nhau.

### 15.1. Identity ID không phải commit order

~~~text
Transaction T1 lấy event_id=100, giữ mở
Transaction T2 lấy event_id=101, COMMIT trước
Worker thấy 101
Transaction T1 COMMIT sau
Worker mới thấy 100
~~~

Nếu worker lưu checkpoint là `last_id=101` rồi chỉ truy vấn `event_id > 101`, event 100 có thể bị bỏ sót. Không dùng high-watermark sequence đơn giản khi có transactions commit lệch thứ tự mà không có cơ chế bù.

## 16. Session có thể nghe thông báo của chính nó

Nếu một session vừa LISTEN vừa NOTIFY cùng channel, nó có thể nhận notification do chính backend đó gửi sau commit.

Trong pgJDBC, thông báo mang PID sender; có thể so sánh với `pg_backend_pid()` của connection để nhận diện self-notification.

Dù vậy, nên thiết kế xử lý idempotent hơn là dựa vào PID như business event key.

## 17. Payload bị giới hạn theo bytes

Với cấu hình PostgreSQL thông dụng, payload NOTIFY phải **ngắn hơn khoảng 8000 bytes**.

**Bytes không phải số ký tự.** Một chuỗi tiếng Việt hoặc emoji có thể chiếm nhiều bytes trong UTF-8 hơn số ký tự hiển thị hoặc Java UTF-16 code units.

### 17.1. Đo bytes

~~~sql
SELECT
    octet_length('đã thay đổi'::TEXT) AS bytes,
    length('đã thay đổi'::TEXT) AS characters;
~~~

Nếu payload lớn:

~~~sql
SELECT pg_notify(
    'orders_changed',
    repeat('x', 100000)
);
~~~

lời gọi sẽ vượt giới hạn kích thước thông thường và có thể báo lỗi. Không cần chạy câu này chỉ để kiểm tra.

### 17.2. Tốt nhất là gửi ID hoặc hint

~~~sql
SELECT pg_notify(
    'orders_changed',
    '{"event_id":901}'::TEXT
);
~~~

Hoặc:

~~~sql
SELECT pg_notify(
    'orders_changed',
    'changed'
);
~~~

Worker query event/task tương ứng từ bảng.

## 18. Không gửi payload nhạy cảm

Tránh payload chứa:

- Mật khẩu, token, API keys.
- Dữ liệu thanh toán/định danh cá nhân.
- Nội dung hồ sơ y tế hoặc thông tin riêng tư.
- Toàn bộ JSON business record.
- Cấu trúc nội bộ cần được phân quyền theo tenant.

Với LISTEN/NOTIFY, channel **không có ACL riêng kiểu broker** để giới hạn mỗi topic cho những users cụ thể theo một cơ chế GRANT channel.

Bởi vậy payload nên đủ nhỏ, không nhạy cảm và không được coi là bằng chứng authorization.

## 19. Không có GRANT LISTEN ON CHANNEL

PostgreSQL không cung cấp SQL grant channel-level tương tự:

~~~sql
-- Không phải cú pháp hợp lệ:
-- GRANT LISTEN ON CHANNEL orders_changed TO app_user;
~~~

Những database roles được phép kết nối có thể LISTEN/NOTIFY trên các channel names phù hợp.

Nếu hệ thống có các trust groups rất khác nhau, hãy kiểm soát:

- Quyền CONNECT tới database.
- Roles, network credentials và TLS.
- Quyền đọc bảng nguồn qua GRANT/RLS.
- Secrets và kết nối ứng dụng.
- Việc worker kiểm tra dữ liệu từ DB thay vì tin payload.

**Một tên channel khó đoán không phải cơ chế bảo mật.**

## 20. Notification queue hữu hạn

PostgreSQL có notification queue dùng chung cho việc phát các notifications tới những listeners trong database.

Hàng đợi có dung lượng hữu hạn; tài liệu PostgreSQL mô tả kích thước lớn, thường khoảng **8 GB trong cấu hình chuẩn**, nhưng không vô tận.

Nếu queue rất đầy:

- Hệ thống có thể cảnh báo.
- Transaction gửi NOTIFY có thể bị lỗi ở COMMIT.
- Long-running transactions của listeners có thể làm queue không được dọn kịp.

### 20.1. Quan sát dung lượng queue

~~~sql
SELECT pg_notification_queue_usage();
~~~

Giá trị trả là **tỷ lệ sử dụng queue**, không phải số event nghiệp vụ chưa được xử lý.

Ví dụ:

~~~sql
SELECT
    pg_notification_queue_usage()
        AS queue_fraction;
~~~

Một giá trị gần 1 thể hiện queue đang đầy hơn và cần điều tra. Không suy được số lượng task còn pending từ hàm này.

## 21. Vì sao long listener transactions đáng lo?

Nếu một session đã LISTEN nhưng giữ transaction mở lâu, PostgreSQL có thể phải giữ dữ liệu notification để bảo đảm delivery semantics.

Các câu hỏi khi queue tăng:

1. Có listener nào `idle in transaction` không?
2. Có query/report dài trên connection listener?
3. Có publisher gửi nhiều payload khác nhau mỗi hàng?
4. Có bulk DML kích hoạt trigger gửi NOTIFY hàng loạt?
5. Có bất thường network khiến listener hoạt động chậm?
6. Có cần giảm tần suất notifications hoặc dùng hint gộp?

Thêm `NOTIFY` vào trigger mọi row mà không đo có thể làm latency DML và commit tăng.

## 22. Queue đầy có thể ảnh hưởng transaction business

Khác với một cơ chế fire-and-forget luôn bỏ thông báo khi bận, NOTIFY gắn với transaction và việc quản lý queue.

Khi queue đầy, transaction chứa NOTIFY có thể không commit được. Nếu function/trigger gửi NOTIFY bên trong transaction đang ghi order, áp lực notification queue có thể ảnh hưởng **khả năng commit order**.

Do đó monitoring queue và kiểm soát notification volume là yêu cầu vận hành, không chỉ tối ưu.

## 23. Một listener offline không được replay

~~~text
10:00  Listener A online, LISTEN jobs_changed
10:01  DB gửi event X, A nhận
10:02  A mất kết nối
10:03  DB gửi event Y, A bỏ lỡ
10:04  A reconnect và LISTEN
10:05  DB gửi event Z, A nhận
~~~

Thông báo Y không tự được server gửi lại cho connection mới.

Nếu Y đại diện cho một công việc bắt buộc, phải có **hàng dữ liệu bền vững** mà A tìm lại được sau reconnect.

## 24. Không có ACK nghiệp vụ

Khi một listener nhận:

~~~text
channel=jobs_changed
payload=changed
~~~

PostgreSQL không biết worker đã:

- SELECT bảng pending chưa.
- Xử lý thành công chưa.
- Gọi external API xong chưa.
- COMMIT kết quả chưa.
- Crash giữa chừng hay không.

Không có API LISTEN/NOTIFY tích hợp để ACK từng event và yêu cầu server retry đúng message đó cho consumer.

## 25. Không có consumer groups

Nếu ba sessions đều LISTEN cùng channel:

~~~text
             NOTIFY jobs_changed
                      |
            +---------+---------+
            |         |         |
         Worker A  Worker B  Worker C
~~~

cả ba có thể nhận hint. PostgreSQL **không phân công** “task 1 cho A, task 2 cho B” như một consumer group.

Nếu chỉ một worker được xử lý mỗi task, cần **atomic claiming**, row locks, lease và idempotency.

## 26. Vai trò của một connection listener riêng

Một listener tốt thường:

- Giữ session mở liên tục.
- Có `autoCommit=true`.
- Không giữ transaction dài khi chờ.
- Đăng ký LISTEN ngay sau connect.
- Lấy notification qua pgJDBC/protocol.
- Reconnect/re-LISTEN khi lỗi.
- Định kỳ query lại durable state.

Không dùng session listener để xử lý SQL báo cáo lâu dài hoặc giao dịch nghiệp vụ nặng.

## 27. Vì sao connection pool có thể gây khó khăn?

Giả sử:

~~~text
Worker lấy connection X từ pool
Worker chạy LISTEN jobs_changed
Worker trả X về pool
Request khác nhận X, mở transaction dài
Worker vẫn tưởng mình giữ listener
~~~

LISTEN gắn với **session X**, không gắn với object listener của ứng dụng.

Giải pháp: giữ một **dedicated connection** cho listener, không trả về pool khi còn hoạt động. Có thể dùng DataSource riêng nếu ứng dụng cần quản lý lifecycle rõ.

## 28. Lab: tạo bảng tasks và outbox

Chạy trong **database lab trống**:

~~~sql
CREATE SCHEMA notify_lab;

CREATE TABLE notify_lab.tasks (
    task_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending', 'processing', 'done', 'failed'
        )),
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp(),
    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE TABLE notify_lab.outbox (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id BIGINT NOT NULL
        REFERENCES notify_lab.tasks(task_id),
    event_type TEXT NOT NULL,
    event_data JSONB NOT NULL,
    published_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL
        DEFAULT statement_timestamp()
);

CREATE INDEX idx_outbox_unpublished
ON notify_lab.outbox(event_id)
WHERE published_at IS NULL;
~~~

Các bảng có trách nhiệm khác nhau:

- `tasks`: nguồn sự thật của công việc.
- `outbox`: nguồn sự thật của event phải được relay/xử lý.
- NOTIFY chỉ là **hint**, không nằm trong cấu trúc bảng.

## 29. Procedure tạo task và event atomically

~~~sql
CREATE PROCEDURE notify_lab.create_task(
    IN p_title TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_task_id BIGINT;
BEGIN
    IF p_title IS NULL
       OR btrim(p_title) = ''
    THEN
        RAISE EXCEPTION
            'Task title must not be empty';
    END IF;

    INSERT INTO notify_lab.tasks (title)
    VALUES (p_title)
    RETURNING task_id INTO v_task_id;

    INSERT INTO notify_lab.outbox (
        task_id,
        event_type,
        event_data
    )
    VALUES (
        v_task_id,
        'task_created',
        jsonb_build_object(
            'task_id', v_task_id,
            'kind', 'task_created'
        )
    );
END;
$$;
~~~

Procedure này **không tự COMMIT**. Caller:

~~~sql
BEGIN;

CALL notify_lab.create_task('Import invoice A');

COMMIT;
~~~

Nếu transaction ROLLBACK, task và outbox event cùng rollback.

### 29.1. Vì sao atomicity quan trọng?

Tránh các trạng thái:

- Task đã commit nhưng event không tồn tại.
- Event đã gửi tới hệ thống ngoài nhưng task cuối cùng rollback.

Transactional outbox giải quyết phần atomicity giữa business state và event record trong cùng PostgreSQL transaction.

## 30. Trigger phát hint khi outbox có hàng mới

Tạo AFTER STATEMENT trigger dùng transition relation:

~~~sql
CREATE FUNCTION notify_lab.notify_outbox_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM inserted_rows
    ) THEN
        PERFORM pg_notify(
            'notify_lab_outbox',
            'changed'
        );
    END IF;

    RETURN NULL;
END;
$$;

CREATE TRIGGER outbox_notify_insert
AFTER INSERT ON notify_lab.outbox
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION notify_lab.notify_outbox_change();
~~~

Khi một statement INSERT outbox rows:

1. Transition relation `inserted_rows` chứa các rows mới của statement.
2. Nếu có ít nhất một row, trigger gọi `pg_notify`.
3. NOTIFY tham gia transaction gửi.
4. Listener chỉ nhận khi transaction commit.

### 30.1. Vì sao statement-level thay vì row-level?

Nếu INSERT 1000 outbox rows, chỉ cần một hint. Trigger cấp statement giúp tránh chạy riêng một function cho từng row.

### 30.2. Vì sao payload 'changed'?

Worker không phải biết event ID từ notification. Nó chỉ cần biết rằng **nên query outbox**. Điều này không phụ thuộc số notifications được gửi hay bị gộp.

## 31. Lab hai session: nhận hint sau COMMIT

**Session A:**

~~~sql
LISTEN notify_lab_outbox;
~~~

**Session B:**

~~~sql
BEGIN;

CALL notify_lab.create_task('Import invoice A');

-- Session A chưa nhận hint từ transaction này.
COMMIT;
~~~

Sau commit, session A có thể nhận:

~~~text
channel = notify_lab_outbox
payload = changed
~~~

Sau đó session A kiểm tra dữ liệu bền vững:

~~~sql
SELECT
    event_id,
    task_id,
    event_type,
    event_data,
    published_at
FROM notify_lab.outbox
WHERE published_at IS NULL
ORDER BY event_id;
~~~

Chính những rows này mới là công việc cần xử lý.

## 32. Lab ROLLBACK không tạo event committed

**Session B:**

~~~sql
BEGIN;

CALL notify_lab.create_task(
    'Task should not exist'
);

ROLLBACK;
~~~

Không có task/outbox row committed của lần gọi này và không có notification committed tương ứng.

### 32.1. Identity counters có thể có khoảng trống

Dù INSERT bị rollback, identity/sequence đã cấp có thể không quay lại. Khoảng trống event_id/task_id là bình thường, không đồng nghĩa sự kiện đã được xử lý hoặc commit.

## 33. Lab coalescing với cùng payload

~~~sql
BEGIN;

CALL notify_lab.create_task('Task B');
CALL notify_lab.create_task('Task C');

COMMIT;
~~~

Mỗi lần INSERT outbox kích hoạt hint `pg_notify('notify_lab_outbox','changed')`. Vì cả hai notification cùng channel/payload trong cùng transaction, listener có thể chỉ nhận **một**.

Nhưng outbox có **hai rows** mới. Worker query bảng và xử lý cả hai, không đếm notifications.

## 34. Không dùng event_id lớn nhất làm cursor commit tuyệt đối

Một ví dụ cạnh tranh:

~~~text
T1 INSERT outbox event_id = 501, chưa COMMIT
T2 INSERT outbox event_id = 502, COMMIT trước
Worker xử lý 502, lưu last_id = 502
T1 COMMIT và event 501 xuất hiện
~~~

Nếu worker chỉ query:

~~~sql
SELECT *
FROM notify_lab.outbox
WHERE event_id > 502;
~~~

thì event 501 bị bỏ qua.

**Không suy thứ tự commit từ sequence values**. Một worker an toàn hơn đọc những events chưa xử lý (`published_at IS NULL`) hoặc dùng một cơ chế claim/checkpoint được thiết kế xử lý transaction concurrency đúng.

## 35. Worker đọc durable events

Ví dụ đơn giản:

~~~sql
SELECT
    event_id,
    task_id,
    event_type,
    event_data
FROM notify_lab.outbox
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 100;
~~~

Query này phù hợp giới thiệu nguồn công việc. Tuy nhiên với **nhiều workers**, chỉ SELECT không lock có thể khiến cùng một row được hai workers lấy.

Cần thêm cơ chế:

- Atomic claim.
- `FOR UPDATE SKIP LOCKED`.
- Status/lease/retry.
- Idempotency key.
- Chính sách timeout và worker recovery.

## 36. Claim công việc bằng FOR UPDATE SKIP LOCKED

Ví dụ atomic claim tối đa 10 tasks:

~~~sql
WITH picked AS (
    SELECT task_id
    FROM notify_lab.tasks
    WHERE status = 'pending'
    ORDER BY task_id
    FOR UPDATE SKIP LOCKED
    LIMIT 10
)
UPDATE notify_lab.tasks AS t
SET status = 'processing',
    updated_at = statement_timestamp()
FROM picked AS p
WHERE t.task_id = p.task_id
RETURNING
    t.task_id,
    t.title,
    t.status;
~~~

Câu lệnh này giúp nhiều workers claim những rows khác nhau dưới transaction/locking phù hợp.

### 36.1. SKIP LOCKED không bảo đảm exactly-once

Nếu worker crash sau khi claim, task có thể kẹt ở `processing`. Hệ thống thật cần lease/timeout/requeue và xử lý idempotent.

### 36.2. Không giữ lock qua external HTTP call dài

Nên tách bước claim transaction ngắn và processing theo thiết kế durable state. Giữ transaction mở để chờ mạng có thể gây contention và tốn connection.

## 37. Transactional outbox không tự bảo đảm exactly-once publication

Luồng relay thường:

~~~text
1. Query outbox event chưa publish
2. Publish event tới broker/HTTP target
3. Đánh dấu published_at
~~~

Nếu worker crash **sau bước 2 nhưng trước bước 3**, event có thể được publish lại.

Vì vậy outbox thường cung cấp **at-least-once delivery**, cần downstream idempotency theo event_id/business key.

### 37.1. Một published_at không phải ACK cho nhiều subscribers

Nếu event có nhiều consumer độc lập, phải có per-consumer state hoặc broker offset phù hợp. Một timestamp dùng chung không chứng minh tất cả consumers đã xử lý thành công.

## 38. Java/pgJDBC hỗ trợ notifications qua API nào?

Các interface của PostgreSQL JDBC driver:

- `org.postgresql.PGConnection`.
- `org.postgresql.PGNotification`.

Có thể unwrap JDBC connection:

~~~java
import org.postgresql.PGConnection;

PGConnection pg =
    connection.unwrap(PGConnection.class);
~~~

`PGConnection` hỗ trợ `getNotifications()` và ở các phiên bản driver phù hợp có `getNotifications(timeoutMillis)`.

Không có API durable consumer/ACK giống message broker trong `java.sql.Connection` chuẩn.

## 39. Java listener chuyên dụng

Ví dụ dùng `DataSource` đã cấu hình pgJDBC:

~~~java
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;

import javax.sql.DataSource;

import org.postgresql.PGConnection;
import org.postgresql.PGNotification;

public final class OutboxNotificationListener {

    private final DataSource listenerDataSource;

    public OutboxNotificationListener(
            DataSource listenerDataSource) {
        this.listenerDataSource = listenerDataSource;
    }

    public void runUntilInterrupted()
            throws SQLException {

        try (Connection connection =
                 listenerDataSource.getConnection()) {

            // Dành connection này riêng cho listener.
            connection.setAutoCommit(true);

            try (Statement statement =
                     connection.createStatement()) {
                statement.execute(
                    "LISTEN notify_lab_outbox"
                );
            }

            PGConnection pg =
                connection.unwrap(PGConnection.class);

            // Sau khi LISTEN có hiệu lực,
            // đọc durable tasks/events trước.
            reconcileOutbox();

            while (!Thread.currentThread().isInterrupted()) {

                PGNotification[] notifications =
                    pg.getNotifications(5000);

                if (notifications != null) {
                    for (PGNotification n : notifications) {

                        if ("notify_lab_outbox".equals(
                                n.getName())) {
                            System.out.printf(
                                "channel=%s pid=%d payload=%s%n",
                                n.getName(),
                                n.getPID(),
                                n.getParameter()
                            );
                        }
                    }
                }

                // Poll fallback cả khi không có notification.
                reconcileOutbox();
            }
        }
    }

    private void reconcileOutbox() {
        // TODO: query durable outbox bằng working connection;
        // claim/lock jobs, xử lý idempotent, ghi trạng thái.
        // Ví dụ không giả vờ bảo đảm exactly-once.
    }
}
~~~

Đoạn code chỉ minh họa listener lifecycle, không phải implementation đầy đủ của worker. Hàm `reconcileOutbox` phải được nối với transaction/claim/retry logic thực tế.

### 39.1. Tại sao getNotifications có timeout?

Để worker không bị block vô thời hạn và có thể kiểm tra cờ shutdown, đồng thời thực hiện reconciliation định kỳ.

### 39.2. Nếu connection lỗi?

`SQLException` phải được bắt ở vòng điều phối cấp cao, đóng connection, backoff, mở connection mới, `LISTEN` lại và reconcile. Không thể coi session cũ vẫn còn đăng ký.

### 39.3. Không dùng cùng connection từ nhiều threads

Một JDBC connection dùng đồng thời bởi listener và worker query có thể gây tranh chấp protocol/transaction. Dùng connection riêng cho listener và working transactions.

## 40. Java gửi notification bằng PreparedStatement

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public final class NotifyPublisher {

    public void send(
            Connection connection,
            String channel,
            String payload) throws SQLException {

        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SELECT pg_notify(?, ?)"
                 )) {
            ps.setString(1, channel);
            ps.setString(2, payload);
            ps.execute();
        }
    }
}
~~~

Parameter binding giúp tránh SQL injection từ channel/payload string. Nó **không** xác thực business intent.

### 40.1. Thời điểm NOTIFY khi connection autocommit=false

Nếu connection đang trong transaction, `pg_notify` chỉ phát notification sau COMMIT. Không mở thêm connection autocommit khác để gửi hint trước khi data transaction hoàn tất.

## 41. Java service và transaction owner

Một application service có thể thực hiện:

~~~text
BEGIN
  INSERT task
  INSERT outbox
  Trigger pg_notify('notify_lab_outbox','changed')
COMMIT
      |
      v
Listener nhận hint
      |
      v
Worker đọc outbox
~~~

Nếu dùng Spring `@Transactional`, thường để transaction manager commit. Procedure `notify_lab.create_task` không tự COMMIT nên có thể được gọi trong transaction service.

Không tự thay `autoCommit` hay gọi `connection.commit()` trên connection đã được Spring/ORM quản lý nếu không có contract cho phép.

## 42. Reconnect/backoff loop

Một vòng vận hành hợp lý:

~~~text
while service is running:
    try:
        open dedicated DB connection
        set autocommit=true
        LISTEN channel
        reconcile durable rows
        while connected:
            getNotifications(timeout)
            reconcile durable rows
    catch connection error:
        close connection
        wait with bounded exponential backoff + jitter
        reconnect and re-LISTEN
~~~

Backoff giúp tránh hàng trăm app instances cùng reconnect dồn sau một outage.

**Sau reconnect phải reconcile**, vì notifications phát trong khoảng offline không được replay.

## 43. LISTEN với Spring @Transactional

Transaction ghi:

~~~text
@Transactional createTask()
    |
    +--> INSERT tasks
    +--> INSERT outbox
    +--> trigger NOTIFY
    +--> COMMIT
            |
            v
          Listener
~~~

là mô hình phù hợp.

Nhưng đừng viết listener như một function `@Transactional` giữ transaction mở suốt vòng chờ:

~~~text
@Transactional listenForever()
  -> LISTEN
  -> wait for notifications
  -> transaction chưa bao giờ COMMIT
~~~

Có thể khiến LISTEN chưa có hiệu lực và gây trì hoãn delivery. Listener nên quản lý connection/transaction riêng.

## 44. LISTEN/NOTIFY và cache invalidation

Một use case phổ biến:

~~~text
API instance A: UPDATE product.price + COMMIT
                   |
                   v
            NOTIFY products_changed
                   |
            +------+------+ 
            |             |
       Instance B     Instance C
            |             |
       Invalidate      Invalidate
         cache           cache
~~~

Nếu instance C offline lúc NOTIFY, nó có thể bỏ lỡ. Vì vậy cache nên có TTL hoặc cơ chế refresh/reconcile.

### 44.1. Eventual consistency cần được chấp nhận rõ

LISTEN/NOTIFY không tự đảm bảo mọi cache ở mọi node luôn đồng bộ tức thì. Nếu nghiệp vụ đòi đồng bộ nghiêm ngặt, cần cơ chế nhất quán khác hoặc route query tới nguồn authoritative.

## 45. Có nên đặt channel theo từng task ID?

Không nên tạo hàng triệu channel:

~~~text
LISTEN task_1001
LISTEN task_1002
LISTEN task_1003
...
~~~

Nên chọn channel theo **loại tác vụ**:

~~~text
LISTEN tasks_changed
LISTEN orders_changed
LISTEN cache_invalidated
~~~

và dùng dữ liệu bền vững hoặc ID nhỏ trong payload khi cần tìm object cụ thể.

## 46. NOTIFY per-row trong trigger: một anti-pattern

Ví dụ:

~~~sql
CREATE FUNCTION notify_lab.notify_each_task()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    PERFORM pg_notify(
        'tasks_changed',
        NEW.task_id::TEXT
    );

    RETURN NEW;
END;
$$;
~~~

Nếu gắn AFTER INSERT FOR EACH ROW và INSERT một triệu tasks, trigger có thể phát nhiều payload khác nhau, làm tăng queue usage và chi phí DML.

Nếu mục tiêu chỉ là “có task mới”, trigger **statement-level hint** trên outbox thường phù hợp hơn.

### 46.1. Coalescing không cứu mọi trường hợp

Khi payload khác nhau, chúng không được gộp như cùng channel/payload. Không dựa vào cơ chế gộp để cứu thiết kế per-row notifications rất lớn.

## 47. Bulk import và giới hạn tải

Khi có:

~~~sql
INSERT INTO notify_lab.tasks(title)
SELECT
    'Task ' || g::TEXT
FROM generate_series(1, 100000) AS g;
~~~

một statement có thể tạo rất nhiều rows.

Nếu trigger phát NOTIFY cho từng hàng, hệ thống bị tải lớn. Nếu một statement chỉ phát một hint, tải notification giảm nhưng workers phải tự query/reconcile nhiều data rows.

**Không chạy ví dụ bulk insert lớn trên shared production database**. Benchmark trên lab có giới hạn.

## 48. Không có channel-level security

Một role khác có thể gửi:

~~~sql
NOTIFY tasks_changed, 'run_admin_job';
~~~

nếu nó có quyền kết nối/thực thi SQL thích hợp.

Worker **không được tin chuỗi payload là chỉ thị quyền cao**. Cách tốt hơn:

~~~text
NOTIFY changed
      |
      v
Query durable table
      |
      v
Validate authorization, status, version
      |
      v
Claim work atomically
      |
      v
Execute intended operation
~~~

Dùng notification chỉ như hint, không phải request có chữ ký hay mệnh lệnh đáng tin.

## 49. NOTIFY không thay logical replication/CDC

| Tiêu chí | LISTEN/NOTIFY | Logical decoding/CDC |
|---|---|---|
| Mục tiêu | Tín hiệu nhanh giữa sessions | Đọc các thay đổi committed từ WAL |
| Replay khi consumer offline | Không built-in | Có cơ chế offsets/slots theo thiết kế |
| Payload | Text nhỏ | Change records theo protocol/plugin |
| Per-consumer ACK | Không | Cơ chế xác nhận vị trí stream tùy framework |
| Độ phức tạp vận hành | Tương đối thấp | Cao hơn, cần quản lý WAL/slots/lag |
| Phù hợp wake-up | Rất tốt | Có thể dùng nhưng thường nặng hơn |
| Phù hợp CDC dài hạn | Không đủ một mình | Phù hợp hơn khi cấu hình đúng |

CDC cũng không tự bảo đảm exactly-once end-to-end; vẫn cần idempotency và quy trình failover phù hợp.

## 50. So sánh với message broker

Broker như Kafka/RabbitMQ hoặc dịch vụ queue chuyên dụng có thể cung cấp những tính năng không có ở LISTEN/NOTIFY, tùy sản phẩm/cấu hình:

- Durable messages.
- Per-consumer offsets/ACK.
- Retry/dead-letter.
- Consumer groups.
- Backpressure/retention.
- Replay.
- Cross-service/cloud fan-out.

Đổi lại cần thêm infrastructure, monitoring và chi phí vận hành.

### 50.1. Chọn theo yêu cầu chứ không theo trào lưu

Nếu mục tiêu chỉ là đánh thức một worker để query PostgreSQL, LISTEN/NOTIFY + outbox có thể đơn giản hơn cả một broker.

Nếu cần phân phối hàng triệu events, replay độc lập và consumer groups, message broker/CDC đáng cân nhắc.

## 51. Two-phase commit và NOTIFY

PostgreSQL có giới hạn: một transaction đã dùng `NOTIFY` **không thể được chuẩn bị** bằng `PREPARE TRANSACTION` theo cơ chế two-phase commit. Các thao tác `LISTEN/UNLISTEN` cũng có giới hạn liên quan prepared transactions.

Nếu ứng dụng dùng XA/2PC, đừng giả định có thể nhúng NOTIFY vào mọi transaction được chuẩn bị. Cần xác minh yêu cầu và đặt phần gửi notification ở vị trí tương thích.

## 52. Failover và lifecycle

Khi primary restart hoặc failover:

- Các sessions cũ có thể ngắt.
- Đăng ký LISTEN không tự đi sang connection mới.
- Notification đã gửi trong lúc client offline không có per-client backlog để replay.
- Outbox rows committed vẫn có thể được kiểm tra lại khi hệ thống phục hồi theo replication/durability architecture.

Một listener sau failover cần reconnect, LISTEN lại và rescan durable work.

## 53. Read replica và replication lag

Nếu listener nhận NOTIFY từ primary rồi ngay lập tức SELECT trên replica, replica có thể **chưa áp dụng thay đổi committed** do replication lag.

Cần xác định:

- Listener kết nối database/primary nào?
- Worker đọc từ primary hay replica?
- Ứng dụng có yêu cầu read-after-write không?
- Có cần chờ replica catch-up theo cơ chế LSN/lag?
- Độ trễ chấp nhận được?

Không coi NOTIFY là barrier chứng minh replica đã đồng bộ.

## 54. Metrics và quan sát

Những chỉ số hữu ích:

- `pg_notification_queue_usage()`.
- Số listeners/connection errors.
- Số notifications nhận/s.
- Số wake-ups nhưng không có rows.
- Latency từ commit đến worker xử lý.
- Số outbox rows chưa publish.
- Tuổi của oldest unpublished event.
- Số retries và duplicate processing.
- Tốc độ claim/complete jobs.
- Lock waits/deadlocks.
- Số lần reconnect và thời gian phục hồi.

### 54.1. Quan sát pg_stat_activity

~~~sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
~~~

Một session listener `idle in transaction` lâu là tín hiệu cần điều tra. Không public các query texts hoặc thông tin session nhạy cảm ra dashboard không được phân quyền.

## 55. Những lỗi phổ biến

### 55.1. LISTEN sau khi query pending

Có race mất notification giữa SELECT và LISTEN.

### 55.2. LISTEN nhưng chưa COMMIT

Đăng ký có thể chưa có hiệu lực.

### 55.3. Giữ listener transaction quá lâu

Notifications có thể bị trì hoãn và queue bị ảnh hưởng.

### 55.4. Trả connection listener vào pool

Session lifecycle không còn thuộc worker.

### 55.5. Không đăng ký lại sau reconnect

Listener mới không tự giữ channel subscriptions của session cũ.

### 55.6. Không reconciliation sau outage

Events committed trong thời gian offline có thể bị bỏ sót.

### 55.7. Đếm notifications như đếm business events

Duplicate folding làm giả định này sai.

### 55.8. Payload 8000 ký tự Unicode

Giới hạn được tính bằng bytes, không phải Java String length.

### 55.9. Payload chứa token/PII

Channel không phải permission boundary.

### 55.10. Tin payload để thực hiện hành động đặc quyền

Một role khác có thể gửi NOTIFY cùng channel.

### 55.11. Mọi listeners cùng xử lý một task

LISTEN/NOTIFY không phải consumer group; cần claim/idempotency.

### 55.12. Dựa vào sequence ID làm commit ordering

Concurrent transactions có thể commit lệch thứ tự cấp ID.

### 55.13. Dùng NOTIFY làm durable event storage

Client offline sẽ mất notifications.

### 55.14. Không giám sát notification queue

Queue full có thể ảnh hưởng commit của transaction gửi.

### 55.15. Chỉ chạy integration test một session

Cần thử ít nhất hai sessions, commit/rollback và reconnect.

### 55.16. Gửi một thông báo khác nhau cho mỗi row bulk import

Có thể tạo notification storm.

### 55.17. Đọc replica ngay sau NOTIFY mà kỳ vọng data đã có

Có thể gặp replication lag.

### 55.18. Không định nghĩa shutdown behavior

Listener có thể giữ connection/thread khi ứng dụng dừng.

### 55.19. Không có backoff sau lỗi

Nhiều instances reconnect dồn gây thêm tải.

### 55.20. Coi pg_notification_queue_usage là số event tồn

Đó là queue occupancy, không phải business backlog.

## 56. Checklist triển khai LISTEN/NOTIFY

**Semantics**

1. Thông báo chỉ là hint hay sự kiện không được phép mất?
2. Nếu client offline, có nguồn dữ liệu bền vững để rescan không?
3. Có cần xử lý theo đúng thứ tự nghiệp vụ không?
4. Có cho phép duplicate processing không?
5. Có định nghĩa idempotency/event ID không?

**SQL và transaction**

6. LISTEN có commit trước khi reconcile không?
7. NOTIFY có nằm trong cùng transaction cần atomicity?
8. Payload nhỏ và không nhạy cảm?
9. Có tránh gửi per-row notifications quá lớn?
10. Có tránh long transactions ở listener?
11. Có quan sát queue usage?
12. Có xem xét 2PC/XA nếu ứng dụng sử dụng?

**Kết nối ứng dụng**

13. Listener có connection riêng?
14. Reconnect có re-LISTEN?
15. Có backoff/jitter khi DB lỗi?
16. Có reconcile sau startup/reconnect?
17. Có polling fallback định kỳ?
18. Có xử lý array notifications null/empty?
19. Có graceful shutdown?
20. Có test với pgJDBC version đang dùng?

**Tính bền vững**

21. Business event đã được lưu trong outbox?
22. Nhiều workers có atomic claim?
23. Có lease/retry cho worker crash?
24. Có cơ chế xử lý duplicates?
25. Có monitoring/alerting cho event backlog?

## 57. Bài tập thực hành

### Bài 1 — LISTEN

Viết SQL đăng ký kênh `orders_changed`.

**Gợi ý:** `LISTEN orders_changed;`.

### Bài 2 — NOTIFY

Phát payload `changed` lên kênh `orders_changed`.

**Gợi ý:** `NOTIFY orders_changed, 'changed';`.

### Bài 3 — pg_notify

Gửi notification với channel/payload được tính theo runtime.

**Gợi ý:** `SELECT pg_notify(channel_text,payload_text);`.

### Bài 4 — Same database

Session ở database B có nhận được NOTIFY từ database A cùng cluster không?

**Gợi ý:** không.

### Bài 5 — Registration

LISTEN bên trong transaction có hiệu lực khi nào?

**Gợi ý:** tại COMMIT.

### Bài 6 — Rollback

NOTIFY trong transaction bị rollback có được giao không?

**Gợi ý:** không.

### Bài 7 — Listener transaction

Listener giữ transaction dài ảnh hưởng delivery ra sao?

**Gợi ý:** notifications có thể bị trì hoãn.

### Bài 8 — Startup race

Tại sao SELECT trước LISTEN có thể bỏ sót việc mới?

**Gợi ý:** NOTIFY phát giữa hai bước.

### Bài 9 — Startup sequence

Nêu thứ tự LISTEN/COMMIT/reconcile an toàn hơn.

**Gợi ý:** LISTEN rồi reconcile.

### Bài 10 — Coalescing

Gửi ba notifications giống channel/payload trong một transaction; có chắc nhận ba không?

**Gợi ý:** không, có thể chỉ một.

### Bài 11 — Different payloads

Cùng channel nhưng payload khác nhau có bị coalesce giống hệt payload không?

**Gợi ý:** không theo quy tắc cùng channel/payload.

### Bài 12 — Two transactions

Hai transactions riêng gửi payload giống nhau có bị gộp như một transaction không?

**Gợi ý:** không.

### Bài 13 — Business event count

Có thể dùng số notification để suy số rows INSERT không?

**Gợi ý:** không.

### Bài 14 — UTF-8 bytes

Tại sao `length` và `octet_length` khác nhau?

**Gợi ý:** ký tự và bytes.

### Bài 15 — Payload limit

Có nên gửi toàn bộ record JSON lớn qua NOTIFY không?

**Gợi ý:** không, giới hạn bytes và không durable.

### Bài 16 — Queue usage

Viết query xem queue occupancy.

**Gợi ý:** `pg_notification_queue_usage()`.

### Bài 17 — Queue full

Queue đầy có thể ảnh hưởng commit thế nào?

**Gợi ý:** commit transaction NOTIFY có thể fail.

### Bài 18 — Channels

Lấy danh sách channels session hiện tại nghe bằng hàm gì?

**Gợi ý:** `pg_listening_channels()`.

### Bài 19 — UNLISTEN

Bỏ tất cả channel subscriptions trong session bằng gì?

**Gợi ý:** `UNLISTEN *;`.

### Bài 20 — PID

PID trong PGNotification có phải ID bền vững của event không?

**Gợi ý:** không.

### Bài 21 — Offline

Worker reconnect có được replay notifications lúc offline không?

**Gợi ý:** không.

### Bài 22 — Outbox

Vì sao lưu outbox trong cùng transaction với task?

**Gợi ý:** atomicity.

### Bài 23 — Hint

Tại sao trigger có thể gửi payload `changed` thay vì đầy đủ event_data?

**Gợi ý:** worker đọc outbox durable.

### Bài 24 — Statement-level

Vì sao trigger theo statement phù hợp bulk insert chỉ cần wake-up?

**Gợi ý:** giảm notification volume.

### Bài 25 — Worker claim

Hai workers cùng SELECT một row pending có thể xử lý trùng không?

**Gợi ý:** có, cần atomic claim.

### Bài 26 — SKIP LOCKED

Cơ chế này giúp gì cho nhiều workers?

**Gợi ý:** bỏ các rows bị lock khi claim.

### Bài 27 — Exactly-once

LISTEN/NOTIFY có per-consumer ACK/offset không?

**Gợi ý:** không.

### Bài 28 — Reconnect

Sau reconnect cần làm những bước nào?

**Gợi ý:** re-LISTEN, commit, reconcile.

### Bài 29 — Java API

pgJDBC có các interface nào liên quan notifications?

**Gợi ý:** PGConnection/PGNotification.

### Bài 30 — PreparedStatement

Bind channel và payload bằng SQL nào?

**Gợi ý:** `SELECT pg_notify(?, ?)`.

### Bài 31 — Dedicated connection

Tại sao không trả listener connection vào pool đang dùng cho HTTP requests?

**Gợi ý:** session và transaction lifecycle.

### Bài 32 — Security

Có thể dùng tên channel như một ACL bí mật không?

**Gợi ý:** không.

### Bài 33 — Spoofed notification

Worker có nên thực thi payload như một lệnh không?

**Gợi ý:** không, kiểm tra trạng thái trong DB.

### Bài 34 — Multiple listeners

Một NOTIFY được tự chia cho mỗi worker một task khác nhau không?

**Gợi ý:** không, fan-out.

### Bài 35 — Replication lag

Vì sao đọc replica ngay sau nhận NOTIFY từ primary có thể chưa thấy data?

**Gợi ý:** replica lag.

### Bài 36 — 2PC

Transaction đã NOTIFY có luôn PREPARE TRANSACTION được không?

**Gợi ý:** không.

### Bài 37 — Sequence order

Tại sao last_event_id lớn nhất có thể khiến bỏ sót event cũ hơn?

**Gợi ý:** thứ tự cấp ID và commit khác nhau.

### Bài 38 — Monitoring

Nêu ba metric quan trọng khi vận hành listener/outbox.

**Gợi ý:** queue usage, oldest unpublished, reconnect count, latency.

### Bài 39 — Cache

Vì sao cache invalidation bằng NOTIFY vẫn nên có TTL?

**Gợi ý:** listener offline có thể mất tín hiệu.

### Bài 40 — Broker

Nêu trường hợp nên chọn broker/CDC thay NOTIFY đơn lẻ.

**Gợi ý:** durability, replay, ack và consumer groups.

## 58. Câu hỏi thường gặp

### LISTEN có tự lấy thông báo phát trước khi đăng ký không?

Không. Đây là registration theo session; cần query durable data để xử lý trạng thái cũ.

### NOTIFY được phát ngay khi SQL chạy hay khi COMMIT?

Sau khi transaction gửi commit thành công. ROLLBACK làm notification không được phát.

### Có thể nhận thông báo khi session listener đang ở transaction dài không?

Có thể bị trì hoãn đến khi transaction của listener kết thúc. Giữ connection listener không ở trong transaction dài khi chờ.

### Payload tối đa có phải 8000 ký tự không?

Không. Giới hạn thông thường ngắn hơn khoảng 8000 **bytes**, không phải số ký tự.

### Gửi nhiều NOTIFY giống nhau có luôn nhận đủ số lần?

Không. Những notifications cùng channel/payload trong cùng transaction có thể được gộp.

### Có thể LISTEN một channel của database khác không?

Không trực tiếp. LISTEN/NOTIFY có phạm vi database.

### LISTEN có tồn tại sau reconnect không?

Không. Phải đăng ký lại trên connection mới.

### Có ACK message sau khi worker xử lý xong không?

Không có per-consumer ACK tích hợp trong LISTEN/NOTIFY. Phải dùng bảng trạng thái/broker nếu cần.

### NOTIFY có thay message broker không?

Không cho những yêu cầu durable replay, consumer group, retry/ack hoặc throughput rất lớn.

### Vì sao phải poll dù đã LISTEN?

Để phát hiện durable tasks/events khi thông báo bị mất trong lúc offline, failover hoặc startup race.

### Có nên gửi email hoặc token trong payload không?

Không. Channel không có permission ACL riêng phù hợp và payload không phải nơi lưu bí mật.

### pg_notification_queue_usage cho biết số job đang chờ không?

Không. Nó cho biết tỷ lệ dung lượng notification queue đang sử dụng.

### Trigger có thể gửi NOTIFY trong cùng transaction không?

Có. Dùng `PERFORM pg_notify(...)` trong trigger function. Notification chỉ được giao sau commit.

### Có thể dùng pgJDBC để nhận notifications không?

Có, qua PGConnection/PGNotification. Cần một connection chuyên dụng, vòng chờ và reconnect/reconcile.

### Nhiều workers cùng LISTEN có tự chia công việc không?

Không. Mọi worker có thể cùng nhận hint; phải claim công việc atomically.

### Nếu producer có NOTIFY, rồi listener crash sau khi nhận, liệu job có bị mất?

Notification không có ACK nghiệp vụ. Nếu task/event chỉ nằm trong NOTIFY, thông tin có thể mất. Nếu nằm trong bảng outbox, worker khởi động lại vẫn có thể tìm và xử lý.

## 59. Tổng kết

Các cú pháp nền tảng:

~~~sql
-- Đăng ký lắng nghe.
LISTEN app_events;

-- Phát thông báo.
NOTIFY app_events, 'changed';

-- Phát với function.
SELECT pg_notify('app_events', 'changed');

-- Các channels của session hiện tại.
SELECT * FROM pg_listening_channels();

-- Bỏ một hoặc tất cả subscriptions.
UNLISTEN app_events;
UNLISTEN *;

-- Quan sát notification queue.
SELECT pg_notification_queue_usage();

-- PID của backend đang thực thi.
SELECT pg_backend_pid();
~~~

Những nguyên tắc quan trọng:

1. **LISTEN gắn với session**, không sống qua reconnect.
2. **NOTIFY được giao sau COMMIT**, rollback hủy thông báo chưa commit.
3. **Listener trong transaction dài có thể nhận trễ**.
4. **LISTEN có hiệu lực tại COMMIT**; đăng ký trước rồi query/reconcile để tránh startup race.
5. **Notifications cùng channel/payload trong một transaction được gộp**, không dùng số lượng NOTIFY để đếm business events.
6. **Payload có giới hạn bytes**, nên chỉ gửi hint/ID nhỏ.
7. **Notification queue hữu hạn**; theo dõi `pg_notification_queue_usage()`.
8. **LISTEN/NOTIFY hoạt động trong một database**, không phải pub/sub cross-cluster.
9. **Không có replay, per-consumer ACK hay consumer group**.
10. **Không có channel-level GRANT phù hợp như broker ACL**; không gửi thông tin nhạy cảm.
11. **Dedicated connection, autocommit và reconnect/re-LISTEN** là lựa chọn thường phù hợp.
12. **Periodic reconciliation** là hàng rào an toàn khi tín hiệu bị mất.
13. **Transactional outbox** lưu event bền vững; NOTIFY chỉ đánh thức worker.
14. **Nhiều workers cần claim/lease/idempotency** để tránh xử lý trùng.
15. **pgJDBC cung cấp PGConnection/PGNotification**, không phải durable broker API.
16. **Bulk DML nên tránh row-level notification storm**, cân nhắc statement-level hint.
17. **Failover và replica lag** cần được tính vào thiết kế.
18. **Đúng loại giao tiếp** quan trọng hơn việc dùng một tính năng cụ thể: NOTIFY cho hint, outbox cho durability, broker/CDC cho distribution/replay khi cần.

Sơ đồ kiến trúc cuối:

~~~text
Business transaction
        |
        +--> INSERT/UPDATE task
        |
        +--> INSERT durable outbox event
        |
        +--> Trigger pg_notify('notify_lab_outbox','changed')
        |
        v
      COMMIT
        |
        +--> Outbox row bền vững
        |
        +--> NOTIFY hint (có thể mất khi listener offline)
                    |
                    v
            Dedicated listener
                    |
                    +--> LISTEN sau mỗi reconnect
                    +--> Reconcile khi startup
                    +--> Reconcile sau notification
                    +--> Poll fallback định kỳ
                    |
                    v
              Claim durable events
                    |
                    v
              Idempotent processing
                    |
                    v
            Commit processing state
~~~

**Kết luận:** `LISTEN` và `NOTIFY` là công cụ đơn giản, hữu ích để **thông báo nhanh khi trạng thái PostgreSQL thay đổi**. Nhưng chúng không phải một nguồn sự kiện bền vững. Khi tác vụ quan trọng không được phép mất, hãy dùng notifications như **tín hiệu đánh thức** kết hợp với bảng trạng thái/outbox, cơ chế retry, idempotency và reconciliation.
