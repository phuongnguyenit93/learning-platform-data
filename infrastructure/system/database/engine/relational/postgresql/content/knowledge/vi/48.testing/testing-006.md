# Kiểm thử cạnh tranh bằng nhiều kết nối và lịch thực thi có kiểm soát

Kiểm thử cạnh tranh (concurrency testing) kiểm tra điều gì xảy ra khi nhiều transaction cùng đọc hoặc thay đổi dữ liệu trong PostgreSQL. Một lỗi cạnh tranh thường không xuất hiện khi chạy từng câu lệnh riêng lẻ: nó chỉ lộ ra khi các thao tác xen kẽ theo một thứ tự nhất định. Vì vậy, bài kiểm thử cần điều khiển được thời điểm mỗi kết nối bắt đầu, đọc, ghi, chờ khóa và commit.

Mục tiêu của một bài kiểm thử tốt là tái tạo được lịch thực thi, quan sát được trạng thái trung gian và khẳng định được kết quả cuối cùng hoặc lỗi mà PostgreSQL phải trả về. Bài này dùng hai kết nối chính, ký hiệu **A** và **B**, cùng một kết nối **M** để quan sát khi cần.

## 1. Những cơ chế cần hiểu trước khi kiểm thử

Mỗi kết nối PostgreSQL có một backend riêng. Hai kết nối đồng thời có thể chạy hai transaction độc lập, với snapshot dữ liệu và trạng thái khóa riêng. Mở hai cửa sổ **psql**, hoặc lấy hai connection riêng từ connection pool, là cách đơn giản để mô phỏng hai người dùng cùng thao tác.

PostgreSQL dùng MVCC (Multi-Version Concurrency Control). Khi một transaction cập nhật một hàng, PostgreSQL tạo phiên bản hàng mới; transaction khác có thể vẫn nhìn thấy phiên bản cũ tùy isolation level và thời điểm snapshot được lấy. Cơ chế này giúp nhiều truy vấn đọc và ghi tiến hành đồng thời mà không phải khóa mọi thao tác đọc.

Isolation level quyết định một transaction nhìn thấy thay đổi của transaction khác như thế nào:

| Isolation level | Hành vi quan sát chính trong PostgreSQL |
|---|---|
| **READ COMMITTED** | Mức mặc định. Mỗi câu lệnh thông thường lấy snapshot mới; hai lần đọc trong cùng transaction có thể thấy hai trạng thái đã commit khác nhau. |
| **REPEATABLE READ** | Các câu lệnh trong transaction dùng cùng snapshot. Không thấy thay đổi được commit sau khi snapshot bắt đầu. PostgreSQL cũng ngăn phantom read ở mức này, nhưng vẫn có thể xảy ra serialization anomaly. |
| **SERIALIZABLE** | Cung cấp kết quả tương đương một thứ tự chạy tuần tự. PostgreSQL dùng Serializable Snapshot Isolation (SSI) và có thể hủy một transaction với lỗi serialization để bảo vệ tính đúng đắn. |

Trong PostgreSQL, **READ UNCOMMITTED** được xử lý như **READ COMMITTED**; không có dirty read theo nghĩa một transaction đọc dữ liệu chưa commit của transaction khác.

MVCC không loại bỏ nhu cầu khóa. **UPDATE**, **DELETE** và **SELECT ... FOR UPDATE** có thể lấy row lock. Khi hai transaction cần khóa xung đột trên cùng một hàng, một transaction phải chờ transaction còn lại kết thúc. Một câu **SELECT** thông thường thường không chặn **UPDATE** trên cùng hàng, nhưng vẫn lấy table-level lock phù hợp để bảo vệ cấu trúc bảng.

Các hiện tượng nên đưa vào bộ kiểm thử gồm:

- **Lost update:** hai transaction cùng đọc một giá trị rồi ghi giá trị tính từ bản đọc cũ, khiến một lần cập nhật bị ghi đè.
- **Non-repeatable read:** cùng một transaction đọc một hàng hai lần và nhận hai giá trị khác nhau.
- **Write skew:** hai transaction đọc cùng một điều kiện nghiệp vụ rồi cập nhật các hàng khác nhau; mỗi cập nhật riêng lẻ hợp lệ nhưng kết quả kết hợp vi phạm invariant.
- **Lock wait:** một transaction phải chờ row lock hoặc table lock do transaction khác đang giữ.
- **Deadlock:** các transaction chờ khóa theo vòng tròn; PostgreSQL phải hủy một transaction để phá vòng chờ.

## 2. Chuẩn bị môi trường và hai kết nối độc lập

Nên chạy ví dụ trong một database thử nghiệm hoặc schema riêng. Không dùng dữ liệu đang phục vụ người dùng thật. Tạo dữ liệu đầu vào rõ ràng để mỗi lần chạy có thể đưa database về cùng một trạng thái.

Ví dụ tạo bảng kiểm thử:

~~~sql
CREATE SCHEMA concurrency_lab;

CREATE TABLE concurrency_lab.counter (
    id      integer PRIMARY KEY,
    value   integer NOT NULL
);

INSERT INTO concurrency_lab.counter (id, value)
VALUES (1, 10);

CREATE TABLE concurrency_lab.lock_demo (
    id      integer PRIMARY KEY,
    note    text NOT NULL
);

INSERT INTO concurrency_lab.lock_demo (id, note)
VALUES (1, 'initial');

CREATE TABLE concurrency_lab.accounts (
    id          integer PRIMARY KEY,
    balance     numeric(12, 2) NOT NULL
);

INSERT INTO concurrency_lab.accounts (id, balance)
VALUES (1, 1000.00), (2, 1000.00);

CREATE TABLE concurrency_lab.on_call (
    doctor_id   integer PRIMARY KEY,
    on_call     boolean NOT NULL
);

INSERT INTO concurrency_lab.on_call (doctor_id, on_call)
VALUES (1, true), (2, true);
~~~

Nếu cần chạy lại ví dụ, khôi phục dữ liệu trước từng kịch bản. Chẳng hạn:

~~~sql
UPDATE concurrency_lab.counter SET value = 10 WHERE id = 1;
UPDATE concurrency_lab.lock_demo SET note = 'initial' WHERE id = 1;
UPDATE concurrency_lab.accounts SET balance = 1000.00;
UPDATE concurrency_lab.on_call SET on_call = true;
~~~

Mở hai terminal **psql** trỏ đến cùng database. Đặt tên ứng dụng để phân biệt kết nối khi xem **pg_stat_activity**:

~~~sql
-- Chạy ở kết nối A
SET application_name = 'concurrency-test-A';
SELECT pg_backend_pid();

-- Chạy ở kết nối B
SET application_name = 'concurrency-test-B';
SELECT pg_backend_pid();
~~~

Hai giá trị **pg_backend_pid()** phải khác nhau. Nếu viết kiểm thử bằng ứng dụng, hãy giữ đồng thời cả hai connection đã checkout từ pool và kiểm tra PID khác nhau. Nếu chỉ checkout lần lượt rồi trả connection về pool, ứng dụng có thể vô tình dùng lại cùng một backend và không tạo được cạnh tranh thật.

Mỗi kịch bản cần có bốn phần: trạng thái ban đầu, lịch thao tác A/B, kết quả mong đợi và bước khôi phục dữ liệu. Ghi rõ isolation level và transaction boundary. Không dựa vào thứ tự chạy ngẫu nhiên của test suite để tạo ra một tình huống cạnh tranh cụ thể.

## 3. Kiểm thử lost update

Giả sử một bộ đếm có giá trị ban đầu là **10**. Hai người dùng cùng đọc giá trị này, mỗi người muốn giảm đi một đơn vị. Nếu ứng dụng tính kết quả ở phía client rồi ghi một hằng số trở lại database, thao tác sau có thể ghi đè thao tác trước.

Đặt lại dữ liệu:

~~~sql
UPDATE concurrency_lab.counter SET value = 10 WHERE id = 1;
~~~

Thực hiện lịch sau ở mức **READ COMMITTED**:

| Thứ tự | Kết nối A | Kết nối B |
|---|---|---|
| 1 | **BEGIN;** | |
| 2 | | **BEGIN;** |
| 3 | **SELECT value FROM concurrency_lab.counter WHERE id = 1;** → **10** | |
| 4 | | **SELECT value FROM concurrency_lab.counter WHERE id = 1;** → **10** |
| 5 | **UPDATE concurrency_lab.counter SET value = 9 WHERE id = 1;** | |
| 6 | **COMMIT;** | |
| 7 | | **UPDATE concurrency_lab.counter SET value = 9 WHERE id = 1;** |
| 8 | | **COMMIT;** |

Kiểm tra kết quả:

~~~sql
SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

Kết quả là **9**, trong khi hai lần giảm độc lập đáng lẽ phải tạo ra giá trị **8**. Lần ghi của B đã ghi đè kết quả do A tạo ra. Đây là lost update ở tầng logic ứng dụng: B đã dùng giá trị cũ mà nó đọc trước đó.

**Cách sửa thứ nhất: thực hiện phép tính ngay trong câu UPDATE.**

~~~sql
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1;
~~~

Chạy câu lệnh này một lần trong mỗi transaction. PostgreSQL tuần tự hóa các cập nhật xung đột trên cùng hàng; mỗi câu lệnh áp dụng phép trừ lên phiên bản hàng phù hợp sau khi lấy được khóa. Hai lần cập nhật sẽ cho kết quả cuối là **8**.

Nếu có điều kiện nghiệp vụ, đưa điều kiện đó vào cùng câu lệnh và kiểm tra số hàng được cập nhật:

~~~sql
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1
  AND value > 0
RETURNING value;
~~~

Không có hàng trả về nghĩa là điều kiện không thỏa mãn hoặc hàng không tồn tại. Ứng dụng cần xử lý trường hợp đó thay vì giả định thao tác đã thành công.

**Cách sửa thứ hai: khóa hàng trước khi đọc và tính toán.**

~~~sql
BEGIN;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1
FOR UPDATE;

-- Tính toán dựa trên giá trị vừa đọc và cập nhật trong cùng transaction.
UPDATE concurrency_lab.counter
SET value = value - 1
WHERE id = 1;

COMMIT;
~~~

Nếu A đã khóa hàng, B sẽ chờ tại **SELECT ... FOR UPDATE**. Sau khi A commit, B lấy được khóa và đọc phiên bản hiện hành của hàng. Cách này hữu ích khi nghiệp vụ phải đọc nhiều trường hoặc áp dụng logic phức tạp trước khi cập nhật. Cần giữ transaction ngắn để không làm các kết nối khác chờ lâu.

## 4. Kiểm thử lock wait và timeout

Kịch bản này xác nhận một transaction bị chặn khi transaction khác đang giữ row lock.

Đặt lại hàng thử nghiệm:

~~~sql
UPDATE concurrency_lab.lock_demo
SET note = 'initial'
WHERE id = 1;
~~~

**Kết nối A** lấy khóa:

~~~sql
BEGIN;

SELECT *
FROM concurrency_lab.lock_demo
WHERE id = 1
FOR UPDATE;
~~~

Giữ transaction A mở. **Kết nối B** thử cập nhật cùng hàng:

~~~sql
BEGIN;

UPDATE concurrency_lab.lock_demo
SET note = 'updated by B'
WHERE id = 1;
~~~

Câu **UPDATE** của B sẽ chờ. Trong lúc đó, mở **kết nối M** để quan sát:

~~~sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name LIKE 'concurrency-test-%';
~~~

Khi B đang chờ khóa, **wait_event_type** thường là **Lock**, còn **pg_blocking_pids(pid)** trả về PID của kết nối đang chặn B. Giá trị cụ thể của **wait_event** phụ thuộc loại khóa và phiên bản PostgreSQL.

Quay lại A và commit:

~~~sql
COMMIT;
~~~

B sẽ tiếp tục chạy. Sau đó commit B:

~~~sql
COMMIT;
~~~

Kiểm tra giá trị mới:

~~~sql
SELECT note
FROM concurrency_lab.lock_demo
WHERE id = 1;
~~~

Có thể kiểm tra timeout bằng **lock_timeout**. Đặt giới hạn trong transaction B:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '500ms';

UPDATE concurrency_lab.lock_demo
SET note = 'timeout test'
WHERE id = 1;
~~~

Nếu A vẫn giữ khóa quá thời gian cho phép, PostgreSQL hủy câu lệnh của B với lỗi lock timeout. Transaction B lúc này ở trạng thái lỗi; cần chạy **ROLLBACK** trước khi tiếp tục dùng connection:

~~~sql
ROLLBACK;
~~~

**lock_timeout** giới hạn thời gian chờ cho mỗi lần lấy khóa. **statement_timeout** giới hạn tổng thời gian thực thi một câu lệnh. Hai thiết lập giải quyết hai vấn đề khác nhau. **SET LOCAL** chỉ có hiệu lực trong transaction hiện tại và tự hết hiệu lực khi transaction kết thúc.

## 5. Kiểm thử deadlock bằng thứ tự khóa đối nghịch

Deadlock xảy ra khi A giữ khóa mà B cần, đồng thời B giữ khóa mà A cần. PostgreSQL phát hiện vòng chờ và hủy một transaction để các transaction còn lại có thể tiếp tục.

Đặt lại hai tài khoản:

~~~sql
UPDATE concurrency_lab.accounts
SET balance = 1000.00;
~~~

Thực hiện lần lượt các bước sau, giữ transaction mở giữa các bước:

| Thứ tự | Kết nối A | Kết nối B |
|---|---|---|
| 1 | **BEGIN;** | |
| 2 | | **BEGIN;** |
| 3 | Cập nhật hàng **id = 1** | |
| 4 | | Cập nhật hàng **id = 2** |
| 5 | Cập nhật hàng **id = 2** và chờ B | |
| 6 | | Cập nhật hàng **id = 1**, tạo vòng chờ |

Câu lệnh cập nhật ở mỗi kết nối:

~~~sql
-- Kết nối A: chạy bước 3, sau đó bước 5
UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 1;

UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 2;

-- Kết nối B: chạy bước 4, sau đó bước 6
UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 2;

UPDATE concurrency_lab.accounts
SET balance = balance - 10
WHERE id = 1;
~~~

Sau khi vòng chờ hình thành, PostgreSQL phát hiện deadlock và trả lỗi SQLSTATE **40P01** cho một trong hai transaction. Transaction bị chọn làm nạn nhân sẽ ở trạng thái lỗi và phải **ROLLBACK**. Transaction còn lại có thể tiếp tục sau khi khóa được giải phóng rồi commit.

Không nên khẳng định A hay B luôn là transaction bị hủy. Việc lựa chọn phụ thuộc trạng thái thực tế tại thời điểm PostgreSQL phát hiện deadlock. Kiểm thử nên xác nhận có một transaction nhận **40P01**, hệ thống giải phóng được vòng chờ và dữ liệu cuối cùng vẫn thỏa invariant.

**Cách phòng tránh phổ biến:** mọi luồng cập nhật nhiều hàng nên lấy khóa theo cùng một thứ tự. Ví dụ, nếu một thao tác cần khóa cả hai tài khoản, luôn khóa **id** nhỏ trước rồi mới đến **id** lớn. Thứ tự thống nhất làm giảm khả năng tạo vòng chờ. Ứng dụng vẫn nên có cơ chế retry toàn bộ transaction khi gặp lỗi có thể thử lại, thay vì chỉ chạy lại câu lệnh cuối.

## 6. So sánh READ COMMITTED và REPEATABLE READ

Kịch bản non-repeatable read giúp xác nhận snapshot được lấy ở mỗi câu lệnh hay được giữ trong cả transaction.

Đặt lại dữ liệu:

~~~sql
UPDATE concurrency_lab.counter
SET value = 100
WHERE id = 1;
~~~

**Ở kết nối A**, bắt đầu transaction **READ COMMITTED** và đọc lần đầu:

~~~sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

Kết quả là **100**. Trong khi A vẫn mở transaction, **kết nối B** cập nhật và commit:

~~~sql
BEGIN;

UPDATE concurrency_lab.counter
SET value = 120
WHERE id = 1;

COMMIT;
~~~

A đọc lại:

~~~sql
SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

A nhận **120**, vì câu **SELECT** thứ hai ở **READ COMMITTED** lấy snapshot mới và nhìn thấy thay đổi đã commit của B. Kết thúc A:

~~~sql
COMMIT;
~~~

Chạy lại cùng lịch nhưng đổi transaction A thành **REPEATABLE READ**:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT value
FROM concurrency_lab.counter
WHERE id = 1;
~~~

Sau khi B cập nhật và commit, câu **SELECT** tiếp theo trong A vẫn thấy giá trị tại snapshot ban đầu. Đó là hành vi mong đợi của **REPEATABLE READ**.

Nếu A cố cập nhật chính hàng mà B đã thay đổi sau khi snapshot của A được thiết lập, PostgreSQL có thể hủy transaction A với lỗi serialization (**40001**, thường có thông báo về concurrent update). Ứng dụng phải rollback và chạy lại toàn bộ transaction với snapshot mới nếu nghiệp vụ cho phép.

Không nên suy luận rằng **REPEATABLE READ** bảo đảm mọi transaction chạy đồng thời đều tương đương một thứ tự tuần tự. PostgreSQL dùng snapshot isolation ở mức này; một số serialization anomaly vẫn có thể xảy ra. Kịch bản write skew tiếp theo cho thấy giới hạn đó.

## 7. Kiểm thử write skew và SERIALIZABLE

Giả sử có hai bác sĩ trực. Quy tắc nghiệp vụ yêu cầu luôn có ít nhất một bác sĩ đang trực. Mỗi transaction kiểm tra số bác sĩ trực rồi cho một bác sĩ nghỉ. Hai transaction có thể đọc cùng một trạng thái hợp lệ và cập nhật hai hàng khác nhau, khiến kết quả cuối vi phạm quy tắc.

Đặt lại dữ liệu:

~~~sql
UPDATE concurrency_lab.on_call
SET on_call = true;
~~~

**Thử với REPEATABLE READ.** Cả A và B bắt đầu transaction trước khi cập nhật:

~~~sql
-- Kết nối A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
-- Kết quả: 2
~~~

~~~sql
-- Kết nối B
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
-- Kết quả: 2
~~~

Sau đó cập nhật các hàng khác nhau:

~~~sql
-- Kết nối A
UPDATE concurrency_lab.on_call
SET on_call = false
WHERE doctor_id = 1;

COMMIT;
~~~

~~~sql
-- Kết nối B
UPDATE concurrency_lab.on_call
SET on_call = false
WHERE doctor_id = 2;

COMMIT;
~~~

Hai transaction có thể cùng commit vì chúng ghi vào hai hàng khác nhau và mỗi transaction dùng snapshot riêng. Kiểm tra:

~~~sql
SELECT count(*)
FROM concurrency_lab.on_call
WHERE on_call;
~~~

Kết quả là **0**, vi phạm invariant “ít nhất một bác sĩ đang trực”. Đây là write skew.

**Lặp lại với SERIALIZABLE.** Khôi phục cả hai hàng thành **true**, rồi chạy đúng lịch đọc trước, cập nhật sau như trên nhưng bắt đầu mỗi transaction bằng:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
~~~

PostgreSQL theo dõi quan hệ đọc/ghi bằng SSI. Khi nhận ra lịch thực thi không thể tương đương một thứ tự tuần tự hợp lệ, PostgreSQL sẽ hủy ít nhất một transaction. Lỗi serialization có SQLSTATE **40001**; lỗi có thể xuất hiện tại câu lệnh cập nhật hoặc khi commit. Sau khi rollback transaction bị hủy, kiểm tra dữ liệu phải cho thấy invariant vẫn được bảo toàn.

Với **SERIALIZABLE**, ứng dụng cần chủ động xử lý serialization failure bằng cách chạy lại **toàn bộ transaction** từ đầu. Không chỉ chạy lại câu lệnh bị lỗi, vì các quyết định trước đó được đưa ra dựa trên snapshot cũ. Khi retry, transaction phải đọc lại điều kiện nghiệp vụ và tính lại hành động.

Nếu cần bảo vệ invariant ở nhiều isolation level, hãy cân nhắc thiết kế khóa tường minh hoặc ràng buộc dữ liệu phù hợp. Ví dụ, có thể khóa một hàng đại diện cho tài nguyên chung trước khi kiểm tra và thay đổi các hàng liên quan. Chọn cách bảo vệ dựa trên invariant cụ thể, không chỉ dựa vào việc một câu lệnh đơn lẻ chạy thành công.

## 8. Quan sát transaction và khóa trong lúc test

**pg_stat_activity** cho biết backend đang chạy câu lệnh nào, trạng thái và wait event. **pg_blocking_pids()** giúp tìm kết nối đang chặn một backend.

Truy vấn sau hiển thị cặp kết nối bị chặn và kết nối chặn:

~~~sql
SELECT
    blocked.pid AS blocked_pid,
    blocked.application_name AS blocked_app,
    blocker.pid AS blocker_pid,
    blocker.application_name AS blocker_app,
    blocked.wait_event_type,
    blocked.wait_event,
    blocked.query AS blocked_query
FROM pg_stat_activity AS blocked
CROSS JOIN LATERAL
    unnest(pg_blocking_pids(blocked.pid)) AS p(blocker_pid)
JOIN pg_stat_activity AS blocker
    ON blocker.pid = p.blocker_pid
WHERE blocked.datname = current_database();
~~~

Có thể xem các lock của hai backend:

~~~sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation,
    mode,
    granted
FROM pg_locks
WHERE pid IN (
    SELECT pid
    FROM pg_stat_activity
    WHERE application_name IN (
        'concurrency-test-A',
        'concurrency-test-B'
    )
)
ORDER BY pid, granted, locktype;
~~~

**granted = false** cho biết lock đang chờ được cấp. **relation** có thể là **NULL** với loại lock không gắn trực tiếp vào một relation. Quyền xem đầy đủ thông tin của session khác phụ thuộc quyền database; tài khoản kiểm thử có thể cần quyền giám sát phù hợp như **pg_read_all_stats**.

Khi ghi log cho một test, nên lưu ít nhất **application_name**, backend PID, isolation level, thời điểm bắt đầu/kết thúc từng bước, câu lệnh liên quan và SQLSTATE của lỗi. Các dữ liệu này giúp phân biệt lỗi nghiệp vụ với timeout, deadlock hoặc serialization failure.

## 9. Điều khiển lịch thực thi trong kiểm thử tự động

Một bài kiểm thử tự động không nên trông chờ hai luồng “vô tình” chạy đúng thứ tự. Hãy dùng cơ chế đồng bộ của framework để điều khiển từng mốc:

1. Tạo hai connection độc lập và xác nhận PID khác nhau.
2. Cho A và B bắt đầu transaction, sau đó chờ cả hai báo đã sẵn sàng.
3. Cho A thực hiện thao tác đầu tiên; chỉ khi A báo hoàn tất mới cho B đi tiếp.
4. Khi cần kiểm thử lock wait, xác nhận B thực sự đang bị chặn bằng **pg_blocking_pids()** hoặc trạng thái chờ phù hợp trước khi giải phóng A.
5. Thu kết quả, kiểm tra SQLSTATE hoặc dữ liệu cuối cùng, rồi commit/rollback và khôi phục dữ liệu.

Các primitive như barrier, latch, semaphore, channel hoặc message giữa hai worker phù hợp để đồng bộ. Có thể dùng một connection quan sát thứ ba để xác nhận trạng thái database trước khi cho bước tiếp theo chạy.

**pg_sleep()** hữu ích khi cần tạo một khoảng chờ để quan sát thủ công, nhưng không nên dùng nó làm cơ chế đồng bộ chính trong test tự động. Ví dụ, “A ngủ 1 giây rồi B cập nhật” phụ thuộc tải máy, độ trễ và lịch CPU; trên CI, thứ tự có thể thay đổi. Một barrier chỉ nhả B sau khi điều kiện của A được xác nhận sẽ đáng tin cậy hơn.

Nếu cần khóa một luồng nghiệp vụ ở tầng ứng dụng, PostgreSQL cung cấp advisory lock. Khóa theo transaction tự được giải phóng khi transaction kết thúc:

~~~sql
BEGIN;

-- Hai số nguyên tạo thành một khóa ứng dụng.
SELECT pg_advisory_xact_lock(42, 1001);

-- Thực hiện phần công việc cần được bảo vệ.

COMMIT;
~~~

Một transaction khác dùng cùng cặp khóa sẽ phải chờ. Có thể dùng **pg_try_advisory_xact_lock(42, 1001)** để kiểm tra và nhận kết quả boolean thay vì chờ. Advisory lock không tự bảo vệ hàng hay ràng buộc dữ liệu; mọi luồng cần phối hợp phải tuân theo cùng quy ước khóa và cùng khóa định danh.

Khi xây dựng test tự động, cần giữ các nguyên tắc sau:

- Mỗi test có dữ liệu riêng hoặc có bước reset rõ ràng; tránh hai test cùng sửa một hàng.
- Dùng timeout có giới hạn để test không treo vô hạn. Khi timeout, rollback mọi transaction còn mở và đóng hoặc trả connection về pool đúng trạng thái.
- Giữ connection A và B cùng lúc để bảo đảm hai backend thật sự tồn tại đồng thời.
- Kiểm tra kết quả bằng invariant và SQLSTATE, không phụ thuộc vào tên backend được chọn làm deadlock victim.
- Với **40001** và **40P01**, nếu ứng dụng hỗ trợ retry thì kiểm tra cả logic retry ở ranh giới transaction.
- Không thực hiện side effect bên ngoài database trước khi transaction commit, trừ khi side effect đó có cơ chế đảm bảo nhất quán riêng. Nếu không, retry có thể gửi email hoặc tạo tác vụ trùng lặp.
- Chạy test trên database/schema dùng riêng và không để transaction thử nghiệm tồn tại sau khi test kết thúc.

## 10. Ma trận kịch bản nên có

| Kịch bản | Lịch thực thi trọng tâm | Kết quả cần xác nhận |
|---|---|---|
| Lost update | A và B cùng đọc một giá trị; mỗi bên ghi kết quả tính từ bản đọc cũ | Test phát hiện kết quả bị ghi đè; phiên bản dùng phép cập nhật nguyên tử cho ra kết quả đúng |
| Row lock wait | A **SELECT ... FOR UPDATE**; B cập nhật cùng hàng | B chờ, **pg_blocking_pids()** xác định được A, B tiếp tục sau khi A kết thúc |
| Lock timeout | A giữ khóa lâu hơn **lock_timeout** của B | B nhận lỗi timeout và transaction được rollback |
| Deadlock | A khóa hàng 1 rồi cần hàng 2; B khóa hàng 2 rồi cần hàng 1 | Có một transaction nhận **40P01**, vòng chờ được giải phóng |
| Non-repeatable read | B commit thay đổi giữa hai lần đọc của A | **READ COMMITTED** thấy giá trị mới; **REPEATABLE READ** giữ snapshot cũ |
| Write skew | A và B cùng đọc invariant rồi cập nhật hai hàng khác nhau | **REPEATABLE READ** có thể vi phạm invariant; **SERIALIZABLE** hủy transaction gây lịch không tuần tự được |
| Transaction retry | Tạo có kiểm soát **40001** hoặc **40P01** | Ứng dụng rollback và chạy lại toàn bộ transaction; dữ liệu cuối vẫn hợp lệ |

## 11. Những lỗi thường làm bài kiểm thử thiếu tin cậy

**Dùng chung một connection cho cả A và B.** Một PostgreSQL connection chỉ thực hiện một luồng transaction tại một thời điểm. Dùng chung connection sẽ làm sai mô hình cạnh tranh. Hãy xác nhận hai backend PID khác nhau.

**Không giữ transaction mở đủ lâu.** Nếu A commit ngay sau khi lấy khóa, B có thể không bao giờ rơi vào trạng thái chờ. Test cần có điểm dừng được điều khiển để giữ A mở cho đến khi quan sát được B bị chặn.

**Dùng pg_sleep() để đoán thứ tự.** Thời gian ngủ không chứng minh một transaction đã đến đúng điểm cần kiểm thử. Dùng barrier hoặc xác nhận trạng thái bằng truy vấn giám sát.

**Chỉ kiểm tra câu lệnh không báo lỗi.** Một transaction có thể commit thành công nhưng tổng thể vẫn vi phạm invariant, như write skew. Luôn kiểm tra trạng thái cuối và quy tắc nghiệp vụ.

**Retry một câu lệnh thay vì cả transaction.** Sau **40001**, các quyết định trước đó có thể dựa trên snapshot đã lỗi thời. Rollback rồi chạy lại từ đầu với lần đọc mới.

**Quên rollback sau lỗi.** Sau một lỗi SQL trong transaction, PostgreSQL đánh dấu transaction là aborted. Các câu lệnh tiếp theo sẽ không chạy bình thường cho đến khi rollback hoặc rollback về savepoint phù hợp.

**Để transaction treo trong test.** Một transaction quên commit/rollback có thể giữ lock và làm các test sau bị treo. Dùng cleanup trong khối **finally** của test harness, timeout rõ ràng và log PID để truy vết.

## 12. Checklist hoàn tất một bài kiểm thử cạnh tranh

Trước khi coi một kịch bản là có thể tái hiện, hãy xác nhận:

- [ ] Dữ liệu ban đầu được khởi tạo rõ ràng và có thể reset.
- [ ] A và B dùng hai PostgreSQL backend khác nhau.
- [ ] Isolation level và ranh giới transaction được ghi rõ.
- [ ] Lịch thao tác có thứ tự xác định, gồm cả điểm chờ và điểm commit.
- [ ] Có cách quan sát trạng thái chờ hoặc lỗi phát sinh.
- [ ] Kết quả mong đợi bao gồm dữ liệu cuối, invariant hoặc SQLSTATE.
- [ ] Mọi transaction được commit hoặc rollback, kể cả khi test thất bại.
- [ ] Test không phụ thuộc vào thời gian ngủ cố định hoặc thứ tự chạy ngẫu nhiên.

Khi kiểm thử cạnh tranh theo lịch có kiểm soát, nhóm phát triển có thể tái hiện lỗi hiếm gặp một cách ổn định, xác định transaction nào nhìn thấy dữ liệu nào và kiểm chứng rằng cách xử lý khóa, isolation level cùng retry giữ được quy tắc nghiệp vụ khi nhiều kết nối hoạt động đồng thời.

