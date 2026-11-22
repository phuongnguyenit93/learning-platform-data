# Mô phỏng hai phiên để kiểm chứng tính cô lập và cơ chế khóa

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Khóa và đồng thời  
> **Mục tiêu:** Dùng hai kết nối Oracle độc lập để quan sát read consistency, mức cô lập READ COMMITTED/SERIALIZABLE/READ ONLY, row lock, table enqueue, SELECT FOR UPDATE, lost update, blocking và deadlock. Biết cách chuẩn bị dữ liệu lab, thực hiện từng bước theo thứ tự, nhận diện kết quả mong đợi và theo dõi session đang chờ.

## 1. Vì sao cần mô phỏng hai phiên?

Các vấn đề đồng thời khó hiểu nếu chỉ đọc một câu SQL riêng lẻ. Cùng một câu UPDATE có thể chạy ngay hoặc phải chờ tùy transaction khác đang giữ khóa nào. Một SELECT có thể đọc giá trị cũ đã commit trong khi writer đang sửa hàng. Hai transaction có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau nếu ứng dụng dùng cách đọc-sửa-ghi không có kiểm soát.

Mô phỏng hai phiên (two-session test) giúp nhìn thấy thứ tự sự kiện:

- Session A thực hiện DML nhưng chưa COMMIT.
- Session B đọc hoặc ghi cùng dữ liệu.
- Quan sát B có thấy thay đổi chưa commit không, có phải chờ không, hay có lỗi.
- A COMMIT/ROLLBACK để giải phóng transaction.
- B tiếp tục và kết quả cuối được kiểm tra.

Trong bài này, **session** là một kết nối database độc lập với transaction state riêng. Hai worksheet trong cùng một kết nối thường vẫn dùng chung session; chúng không đủ để mô phỏng hai transaction cạnh tranh.

| Hiện tượng | Điều cần kiểm chứng |
|---|---|
| Dirty read | Oracle không cho SELECT thông thường thấy dữ liệu chưa commit của session khác |
| Nonrepeatable read | READ COMMITTED có thể trả giá trị khác ở hai SELECT trong cùng transaction |
| Phantom read | Cùng predicate có thể trả thêm hàng sau khi session khác INSERT và COMMIT |
| Write blocking | UPDATE/DELETE cùng hàng phải chờ transaction đang giữ row lock |
| Consistent read | SELECT thông thường có thể đọc phiên bản đã commit cũ nhờ undo |
| SELECT FOR UPDATE | Có thể khóa hàng để đọc-sửa-ghi an toàn hơn |
| SERIALIZABLE | Các câu SELECT trong transaction nhìn cùng snapshot; ghi xung đột có thể nhận ORA-08177 |
| Deadlock | Hai transaction khóa hàng theo thứ tự ngược có thể tạo vòng chờ và ORA-00060 |

## 2. Chuẩn bị môi trường thử nghiệm

Dùng schema lab riêng, có quyền CREATE TABLE. Không chạy kịch bản cố tình gây blocking/deadlock trên bảng production.

Mở **hai kết nối Oracle độc lập** tới cùng schema/database, đặt tên dễ phân biệt là Session A và Session B. Có thể dùng hai connection trong SQL Developer, hai cửa sổ SQL*Plus hoặc hai kết nối từ ứng dụng thử nghiệm.

Trong SQL*Plus, tắt autocommit:

~~~sql
SET AUTOCOMMIT OFF;
~~~

Trong SQL Developer hoặc công cụ GUI, kiểm tra tùy chọn auto-commit và bảo đảm transaction không tự commit sau từng câu lệnh. Không dùng chung một connection/session cho cả A và B.

Kiểm tra SID của từng kết nối:

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid,
       SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user
FROM dual;
~~~

Ghi lại SID của A và B. Chúng phải khác nhau. SID giúp đối chiếu V$SESSION khi một session chờ session còn lại.

### 2.1. Tạo dữ liệu lab một lần

Chạy trong một kết nối chuẩn bị (hoặc Session A trước khi bắt đầu thử nghiệm):

~~~sql
CREATE TABLE lab_iso_rows (
    row_id NUMBER CONSTRAINT pk_lab_iso_rows PRIMARY KEY,
    category VARCHAR2(20 CHAR) NOT NULL,
    amount NUMBER(12,2) NOT NULL,
    version_no NUMBER DEFAULT 1 NOT NULL,
    note VARCHAR2(100)
);

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (1, 'A', 100, 1, 'Initial row 1');

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (2, 'A', 200, 1, 'Initial row 2');

INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (3, 'B', 300, 1, 'Initial row 3');

COMMIT;
~~~

Xác nhận trạng thái ban đầu:

~~~sql
SELECT row_id, category, amount, version_no, note
FROM lab_iso_rows
ORDER BY row_id;
~~~

Kết quả:

~~~text
ROW_ID  CATEGORY  AMOUNT  VERSION_NO
------  --------  ------  ----------
1       A         100     1
2       A         200     1
3       B         300     1
~~~

Không chạy lại phần CREATE TABLE khi bảng đã tồn tại. Sau mỗi thí nghiệm, hoàn tất COMMIT/ROLLBACK trước khi bắt đầu kịch bản kế tiếp.

## 3. READ COMMITTED: snapshot ở cấp statement

READ COMMITTED là isolation level mặc định của Oracle. Mỗi câu SELECT nhìn dữ liệu đã commit tại thời điểm câu lệnh bắt đầu, cộng với thay đổi của chính transaction hiện tại.

Điều này có hai hệ quả:

1. Một SELECT không nhìn thấy dữ liệu chưa commit của session khác.
2. Hai SELECT trong cùng transaction có thể nhìn thấy hai trạng thái khác nhau nếu session khác COMMIT ở giữa.

### 3.1. Thử nonrepeatable read

**Bước 1 — Session A:** đọc hàng 1:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Kết quả: 100.

**Bước 2 — Session B:** sửa và commit:

~~~sql
UPDATE lab_iso_rows
SET amount = 150
WHERE row_id = 1;

COMMIT;
~~~

**Bước 3 — Session A:** chạy lại đúng câu SELECT:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Kết quả: 150.

A đã đọc 100 ở statement đầu và 150 ở statement sau, dù A chưa kết thúc transaction. Đây là **nonrepeatable read**: một hàng được đọc lại trong cùng transaction có thể có giá trị khác dưới READ COMMITTED vì mỗi statement lấy snapshot mới.

Điều này không phải dirty read. Giá trị 150 chỉ xuất hiện sau khi B COMMIT.

### 3.2. Thử phantom read

Phantom read xảy ra khi cùng một predicate được chạy lại và tập hàng kết quả có thêm hoặc bớt hàng do transaction khác commit.

**Bước 1 — Session A:** đếm các hàng category A:

~~~sql
SELECT COUNT(*) AS rows_in_a
FROM lab_iso_rows
WHERE category = 'A';
~~~

Kết quả ban đầu: 2.

**Bước 2 — Session B:** thêm một hàng thuộc category A và commit:

~~~sql
INSERT INTO lab_iso_rows(row_id, category, amount, version_no, note)
VALUES (4, 'A', 400, 1, 'Inserted by session B');

COMMIT;
~~~

**Bước 3 — Session A:** chạy lại cùng truy vấn:

~~~sql
SELECT COUNT(*) AS rows_in_a
FROM lab_iso_rows
WHERE category = 'A';
~~~

Kết quả: 3.

Cùng predicate nhưng tập kết quả thay đổi vì READ COMMITTED tạo snapshot mới cho statement thứ hai.

### 3.3. Chứng minh không có dirty read

**Bước 1 — Session A:** UPDATE nhưng chưa commit:

~~~sql
UPDATE lab_iso_rows
SET amount = 999
WHERE row_id = 1;
~~~

**Bước 2 — Session B:** SELECT hàng 1:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B đọc giá trị đã commit gần nhất, không thấy 999. Nếu trước thí nghiệm amount là 150 thì B vẫn thấy 150.

**Bước 3 — Session A:** rollback:

~~~sql
ROLLBACK;
~~~

Sau rollback, giá trị đã commit vẫn là 150. Oracle không cung cấp dirty read cho SELECT thông thường như một số hệ quản trị cho phép READ UNCOMMITTED.

## 4. Consistent read và row lock là hai cơ chế khác nhau

Một điểm quan trọng khi quan sát hai session:

- SELECT thông thường dùng multiversion read consistency để đọc snapshot.
- UPDATE/DELETE cùng một hàng phải phối hợp qua row lock.
- Reader thông thường không phải chờ writer chỉ vì writer đang giữ row lock chưa commit.
- Writer muốn sửa cùng hàng có thể phải chờ transaction đang giữ khóa kết thúc.

Ví dụ:

**Session A:**

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 20
WHERE row_id = 1;
-- Chưa COMMIT
~~~

**Session B:**

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B thường thấy giá trị đã commit trước UPDATE của A, không thấy phần tăng 20 chưa commit và không cần chờ row lock.

Nếu B chạy:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

B phải chờ A COMMIT hoặc ROLLBACK vì cả hai muốn thay đổi cùng hàng.

Đây là nền tảng concurrency control trong Oracle: đọc thông thường không chặn ghi và ghi không chặn consistent read thông thường; xung đột giữa các writer vẫn cần được tuần tự hóa.

## 5. Mô phỏng write blocking trên cùng một hàng

Trước thí nghiệm, bảo đảm row 1 có amount đã biết và không còn transaction cũ chưa kết thúc.

### 5.1. Session A khóa hàng bằng UPDATE

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 20
WHERE row_id = 1;
~~~

Không COMMIT. A đang giữ row lock trên row 1 và transaction lock liên quan.

### 5.2. Session B đọc cùng hàng

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

B đọc phiên bản đã commit trước UPDATE của A. B không thấy thay đổi chưa commit và SELECT thông thường thường hoàn thành ngay.

### 5.3. Session B UPDATE cùng hàng

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

Câu lệnh của B chờ vì A giữ row lock. Để dễ quan sát, đừng commit A ngay; chuyển sang phần theo dõi blocker.

### 5.4. Session A kết thúc transaction

Trong Session A:

~~~sql
COMMIT;
~~~

Sau khi A commit, B có thể tiếp tục. Với READ COMMITTED, Oracle xử lý hàng hiện tại theo semantics của DML sau khi chờ; phép cộng amount = amount + 10 áp dụng lên giá trị hiện hành sau thay đổi của A.

Nếu A ROLLBACK thay vì COMMIT, B tiếp tục từ trạng thái đã khôi phục.

### 5.5. Kiểm tra kết quả

Sau khi cả hai session hoàn tất:

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Nếu ban đầu amount là 150, A tăng 20 và B tăng 10, kết quả cuối là 180. Cả hai phép cộng được áp dụng theo thứ tự tuần tự.

## 6. SELECT FOR UPDATE: khóa hàng trước khi đọc-sửa-ghi

Nếu ứng dụng cần đọc một giá trị rồi quyết định cập nhật dựa trên giá trị vừa đọc, có thể khóa hàng trước bằng SELECT FOR UPDATE.

Session A:

~~~sql
SELECT row_id, amount, version_no
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE;
~~~

A đọc hàng và giữ row lock đến COMMIT hoặc ROLLBACK. Session khác muốn UPDATE/DELETE hoặc SELECT FOR UPDATE cùng hàng có thể phải chờ.

Sau khi đọc, A có thể cập nhật:

~~~sql
UPDATE lab_iso_rows
SET amount = amount - 25
WHERE row_id = 1;

COMMIT;
~~~

### 6.1. NOWAIT

Nếu Session A đang khóa row 1, Session B có thể thử:

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE NOWAIT;
~~~

Nếu hàng đang bị khóa không tương thích, B trả lỗi ngay, thường là:

~~~text
ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired
~~~

NOWAIT phù hợp khi ứng dụng muốn báo “đang được xử lý” thay vì chờ.

### 6.2. WAIT n

~~~sql
SELECT row_id, amount
FROM lab_iso_rows
WHERE row_id = 1
FOR UPDATE WAIT 5;
~~~

B chờ tối đa khoảng thời gian được chỉ định. Nếu hết thời gian mà lock chưa được giải phóng, Oracle có thể báo ORA-30006 (resource busy; acquire with WAIT timeout expired).

### 6.3. SKIP LOCKED

Với mô hình queue/worker, một session có thể bỏ qua hàng đang bị session khác khóa:

~~~sql
SELECT row_id, note
FROM lab_iso_rows
WHERE row_id IN (1, 2, 3)
ORDER BY row_id
FOR UPDATE SKIP LOCKED;
~~~

Nếu A đang khóa row 2, B có thể nhận các hàng 1 và 3 mà không chờ row 2. B cũng khóa các hàng mà nó lấy được cho đến khi transaction kết thúc.

SKIP LOCKED hữu ích cho worker lấy việc từ queue, nhưng cần thiết kế claim/status/commit/retry để không bỏ quên công việc. Nó không bảo đảm công bằng thứ tự và không thay thế kiểm tra trạng thái nghiệp vụ.

### 6.4. Thời điểm giải phóng lock

Row lock do SELECT FOR UPDATE hoặc DML giữ đến khi transaction COMMIT/ROLLBACK, không phải chỉ đến khi câu SELECT kết thúc.

Không mở transaction khóa hàng rồi chờ người dùng nhập dữ liệu hoặc gọi dịch vụ mạng lâu. Hãy giữ khoảng thời gian khóa ngắn.

## 7. Lost update: hai người cùng sửa từ một giá trị cũ

Một ví dụ thường gặp không tạo ra lỗi lock rõ ràng nhưng vẫn làm mất cập nhật ở tầng ứng dụng.

Giả sử amount ban đầu là 100:

1. A SELECT amount và nhận 100.
2. B SELECT amount và cũng nhận 100.
3. A tính 100 - 10 = 90.
4. B tính 100 + 20 = 120.
5. A UPDATE amount = 90 và COMMIT.
6. B UPDATE amount = 120 và COMMIT.

Kết quả cuối là 120. Phần giảm 10 của A đã bị ghi đè. Đây là lost update do B ghi giá trị tuyệt đối tính từ dữ liệu cũ.

Ví dụ câu lệnh của ứng dụng:

~~~sql
UPDATE lab_iso_rows
SET amount = :p_new_amount
WHERE row_id = 1;
~~~

B không biết giá trị mà nó đọc trước đó đã lỗi thời.

### 7.1. Cách 1: dùng phép cập nhật tương đối trong SQL

Nếu nghiệp vụ chỉ là cộng/trừ delta, hãy để database tính trên giá trị hiện hành:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + :p_delta
WHERE row_id = :p_row_id;
~~~

Oracle tuần tự hóa các writer cùng hàng. Sau khi session trước kết thúc, phép cộng của session sau được áp dụng trên giá trị hiện hành thay vì giá trị client đọc cũ.

Cách này không phù hợp với mọi quy tắc nghiệp vụ, nhưng là lựa chọn tốt cho phép cộng/trừ đơn giản.

### 7.2. Cách 2: pessimistic locking với SELECT FOR UPDATE

Ứng dụng khóa hàng trước khi đọc:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = :p_row_id
FOR UPDATE;
~~~

Sau khi lấy lock, ứng dụng tính toán và UPDATE trong cùng transaction. Session khác muốn sửa cùng hàng phải chờ; sau khi A commit, B đọc giá trị mới nhất khi lấy khóa.

### 7.3. Cách 3: optimistic locking bằng version

Bảng có cột VERSION_NO. Client đọc amount và version:

~~~sql
SELECT amount, version_no
FROM lab_iso_rows
WHERE row_id = :p_row_id;
~~~

Giả sử client đọc amount 100, version 1. Khi ghi, client gửi lại version đã đọc:

~~~sql
UPDATE lab_iso_rows
SET amount = :p_new_amount,
    version_no = version_no + 1
WHERE row_id = :p_row_id
  AND version_no = :p_old_version;
~~~

Ứng dụng kiểm tra số hàng bị ảnh hưởng:

- ROWCOUNT = 1: cập nhật thành công.
- ROWCOUNT = 0: hàng đã bị session khác thay đổi hoặc không còn tồn tại; cần đọc lại và xử lý xung đột.

Có thể kiểm tra bằng PL/SQL:

~~~sql
DECLARE
    l_new_amount NUMBER := 90;
    l_old_version NUMBER := 1;
BEGIN
    UPDATE lab_iso_rows
    SET amount = l_new_amount,
        version_no = version_no + 1
    WHERE row_id = 1
      AND version_no = l_old_version;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Concurrent modification detected'
        );
    END IF;
END;
/
~~~

Optimistic locking phù hợp khi xung đột hiếm và không muốn giữ lock trong lúc người dùng suy nghĩ. Pessimistic locking phù hợp khi cần tuần tự hóa thao tác đọc-sửa-ghi ngay trong transaction.

## 8. SERIALIZABLE: snapshot ở cấp transaction

Trong READ COMMITTED, mỗi statement có snapshot riêng. SERIALIZABLE cung cấp góc nhìn nhất quán ở cấp transaction theo SCN bắt đầu transaction.

Đặt isolation level phải là thao tác đầu tiên trong transaction, trước các câu SQL khác:

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
~~~

### 8.1. Thử snapshot không đổi

**Session A:**

~~~sql
COMMIT;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Ghi lại giá trị A nhìn thấy.

**Session B:** cập nhật và commit:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 50
WHERE row_id = 1;

COMMIT;
~~~

**Session A:** chạy lại:

~~~sql
SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

A tiếp tục nhìn thấy giá trị tại snapshot của transaction, không tự chuyển sang giá trị mới do B vừa commit. Đây là khác biệt với READ COMMITTED.

### 8.2. Thử xung đột ghi và ORA-08177

Trong khi A vẫn ở SERIALIZABLE transaction đã đọc row 1, B đã sửa và commit row đó sau khi snapshot của A bắt đầu.

A thử:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 10
WHERE row_id = 1;
~~~

Oracle có thể báo:

~~~text
ORA-08177: can't serialize access for this transaction
~~~

Oracle từ chối thay đổi để không tạo kết quả vi phạm semantics serializable. Ứng dụng thường cần ROLLBACK và retry toàn bộ transaction với snapshot mới, không chỉ lặp lại riêng statement thất bại.

Sau thử nghiệm, A:

~~~sql
ROLLBACK;
~~~

### 8.3. SERIALIZABLE không khóa toàn bảng

SERIALIZABLE chủ yếu thay đổi snapshot và quy tắc xử lý xung đột ghi. Nó không đơn giản khóa toàn bộ bảng để ngăn mọi transaction khác. Oracle vẫn dùng MVCC/undo và lock để điều phối DML.

## 9. READ ONLY transaction

READ ONLY transaction cho phép nhiều câu SELECT dùng cùng snapshot transaction và không cho phép DML trong transaction đó.

Session A:

~~~sql
COMMIT;
SET TRANSACTION READ ONLY;

SELECT amount
FROM lab_iso_rows
WHERE row_id = 1;
~~~

Session B cập nhật và commit:

~~~sql
UPDATE lab_iso_rows
SET amount = amount + 25
WHERE row_id = 1;

COMMIT;
~~~

Session A chạy lại SELECT và vẫn thấy snapshot cũ. Nếu A thử INSERT/UPDATE/DELETE trong READ ONLY transaction, Oracle từ chối, thường với ORA-01456.

Kết thúc:

~~~sql
COMMIT;
~~~

READ ONLY phù hợp cho một quy trình báo cáo nhiều câu query cần cùng góc nhìn dữ liệu. Nó không khóa writer khỏi thay đổi dữ liệu; undo hỗ trợ A tiếp tục đọc snapshot.

## 10. Deadlock: hai session khóa theo thứ tự ngược

Blocking là một session chờ session khác. Deadlock là vòng chờ, khi mỗi session giữ một tài nguyên mà session kia cần.

Dùng hai hàng row 1 và row 2.

### 10.1. Trình tự tạo deadlock

**Bước 1 — Session A:** khóa row 1:

~~~sql
UPDATE lab_iso_rows
SET note = 'A owns row 1'
WHERE row_id = 1;
~~~

Chưa commit.

**Bước 2 — Session B:** khóa row 2:

~~~sql
UPDATE lab_iso_rows
SET note = 'B owns row 2'
WHERE row_id = 2;
~~~

Chưa commit.

**Bước 3 — Session A:** yêu cầu row 2:

~~~sql
UPDATE lab_iso_rows
SET note = 'A wants row 2'
WHERE row_id = 2;
~~~

A chờ vì B đang giữ row 2.

**Bước 4 — Session B:** yêu cầu row 1:

~~~sql
UPDATE lab_iso_rows
SET note = 'B wants row 1'
WHERE row_id = 1;
~~~

B chờ vì A đang giữ row 1. Hai session tạo vòng chờ.

Oracle phát hiện deadlock và một statement nhận lỗi:

~~~text
ORA-00060: deadlock detected while waiting for resource
~~~

### 10.2. Xử lý sau ORA-00060

Oracle thường rollback statement gây deadlock, không tự động rollback toàn bộ transaction của ứng dụng. Transaction vẫn có thể giữ các lock do statement trước đó lấy.

Session nhận lỗi cần xử lý transaction rõ ràng, thường ROLLBACK toàn transaction nếu đơn vị nghiệp vụ phải được chạy lại. Sau khi session đó rollback, session còn lại được giải phóng và có thể tiếp tục.

Không giả định chỉ cần statement báo lỗi là mọi lock của transaction đã được nhả.

### 10.3. Cách giảm deadlock

- Cập nhật nhiều hàng theo cùng một thứ tự khóa ở mọi transaction, ví dụ tăng dần ROW_ID.
- Giữ transaction ngắn.
- Không chờ người dùng hoặc gọi API ngoài khi đang giữ lock.
- Phân vùng batch để worker không cùng xử lý một tập khóa.
- Dùng retry có giới hạn và idempotency.
- Đọc trace deadlock để xác định object, SQL và thứ tự khóa thực tế.

## 11. Theo dõi session đang chờ và session chặn

Khi Session B bị treo ở UPDATE, dùng một kết nối giám sát (có quyền đọc dynamic performance views) để xác định blocker.

### 11.1. Xem SID và blocker

~~~sql
SELECT sid,
       serial#,
       username,
       status,
       event,
       wait_class,
       seconds_in_wait,
       blocking_session,
       blocking_session_status,
       sql_id,
       prev_sql_id
FROM v$session
WHERE blocking_session IS NOT NULL
ORDER BY seconds_in_wait DESC;
~~~

Các cột quan trọng:

- SID/SERIAL#: định danh session.
- EVENT/WAIT_CLASS: loại wait.
- SECONDS_IN_WAIT: thời gian chờ.
- BLOCKING_SESSION: SID đang chặn.
- SQL_ID/PREV_SQL_ID: câu SQL hiện tại/trước đó.

Trong một số trạng thái, BLOCKING_SESSION có thể NULL hoặc chưa đủ để mô tả toàn bộ chuỗi blocker. Kết hợp V$SESSION, V$LOCK và công cụ giám sát phù hợp.

### 11.2. Xem TX và TM enqueue

~~~sql
SELECT sid,
       type,
       id1,
       id2,
       lmode,
       request,
       block
FROM v$lock
WHERE type IN ('TX', 'TM')
ORDER BY type, sid;
~~~

- TX liên quan transaction và thường xuất hiện trong row-lock contention.
- TM liên quan table enqueue.
- LMODE là mode đang giữ.
- REQUEST là mode đang chờ.
- BLOCK cho biết thông tin chặn theo view.

### 11.3. Xem object đang bị khóa

~~~sql
SELECT lo.session_id,
       lo.oracle_username,
       lo.locked_mode,
       o.owner,
       o.object_name,
       o.object_type
FROM v$locked_object lo
JOIN dba_objects o
  ON o.object_id = lo.object_id
ORDER BY lo.session_id, o.owner, o.object_name;
~~~

V$LOCKED_OBJECT cho biết DML lock ở cấp object; nó không liệt kê từng row lock như một danh sách hàng. Kết hợp blocker SID, SQL_ID và transaction owner để tìm nguyên nhân.

Các view V$ và DBA có thể cần quyền SELECT_CATALOG_ROLE hoặc quyền SELECT được cấp riêng. Không cần cấp quyền DBA rộng cho tài khoản ứng dụng chỉ để chạy DML thông thường.

### 11.4. Ghi SID trong mỗi session

~~~sql
SELECT SYS_CONTEXT('USERENV', 'SID') AS sid
FROM dual;
~~~

Ghi SID A/B trước khi tạo blocking. Khi có blocker, đối chiếu SID trong V$SESSION với hai kết nối đã mở.

## 12. Ma trận kết quả mong đợi

| Thí nghiệm | Session A | Session B | Kết quả quan sát |
|---|---|---|---|
| Dirty read | UPDATE chưa commit | SELECT cùng hàng | B thấy giá trị đã commit cũ |
| Nonrepeatable read | SELECT, chờ B commit, SELECT lại | UPDATE + COMMIT | A lần đầu và lần sau có thể thấy giá trị khác |
| Phantom | COUNT, chờ B insert commit, COUNT lại | INSERT hàng thỏa predicate + COMMIT | A thấy số hàng tăng |
| Writer blocking | UPDATE row 1 chưa commit | UPDATE row 1 | B chờ A |
| Consistent read | UPDATE chưa commit | SELECT row 1 | B không chờ và không thấy giá trị chưa commit |
| NOWAIT | Giữ row lock | SELECT FOR UPDATE NOWAIT | B trả ORA-00054 |
| WAIT | Giữ row lock | SELECT FOR UPDATE WAIT n | B chờ tối đa n giây rồi lỗi nếu chưa được nhả |
| SKIP LOCKED | Giữ một số hàng | SELECT FOR UPDATE SKIP LOCKED | B lấy hàng chưa bị khóa |
| SERIALIZABLE | Bắt đầu snapshot rồi SELECT | UPDATE + COMMIT | A tiếp tục thấy snapshot cũ |
| SERIALIZABLE write conflict | A đã snapshot hàng | B sửa và commit, A sửa cùng hàng | A có thể nhận ORA-08177 |
| Deadlock | Khóa row 1 rồi chờ row 2 | Khóa row 2 rồi chờ row 1 | Một statement nhận ORA-00060 |

## 13. Các lỗi và cách diễn giải

| Mã lỗi/event | Ý nghĩa trong thí nghiệm | Việc cần làm |
|---|---|---|
| ORA-00054 | NOWAIT không lấy được resource lock | Retry sau hoặc báo busy |
| ORA-30006 | Hết thời gian WAIT khi lấy lock | Điều chỉnh timeout hoặc xử lý retry |
| ORA-00060 | Deadlock detected | Đọc trace, rollback transaction phù hợp, retry an toàn |
| ORA-08177 | SERIALIZABLE không thể serialize thay đổi | Rollback và retry toàn transaction |
| ORA-01456 | DML không được phép trong READ ONLY transaction | Kết thúc read-only transaction hoặc dùng transaction khác |
| enq: TX - row lock contention | Chờ transaction/row lock liên quan | Xác định blocker và hàng nghiệp vụ |
| enq: TM - contention | Chờ table enqueue | Kiểm tra object, lock mode và DDL |

Một mã lỗi chỉ là dấu hiệu. Cần kết hợp SQL, transaction state, object và thứ tự thao tác để kết luận nguyên nhân.

## 14. Nguyên tắc thiết kế ứng dụng đồng thời

### 14.1. Chọn đúng chiến lược khóa

| Nhu cầu | Chiến lược phù hợp |
|---|---|
| Chỉ đọc dữ liệu | SELECT thông thường với consistent read |
| Đọc-sửa-ghi trong transaction ngắn | SELECT FOR UPDATE |
| Xung đột hiếm, nhiều người dùng chỉnh sửa | Optimistic locking bằng version |
| Cộng/trừ delta | UPDATE cột = cột + delta |
| Worker lấy việc từ queue | SELECT FOR UPDATE SKIP LOCKED và cơ chế claim |
| Báo cáo nhiều câu query cùng snapshot | READ ONLY hoặc SERIALIZABLE tùy semantics |

### 14.2. Giữ transaction ngắn

Không giữ transaction mở khi người dùng đang xem màn hình, nhập liệu hoặc chờ dịch vụ bên ngoài. Nếu cần giữ trạng thái giữa nhiều request, dùng optimistic version hoặc một cơ chế nghiệp vụ riêng thay vì giữ database lock trong thời gian dài.

### 14.3. Retry phải an toàn

Một lỗi serialization hoặc deadlock có thể yêu cầu chạy lại transaction. Trước khi retry:

- Rollback transaction theo đúng trạng thái.
- Xác định thao tác có idempotent không.
- Không gửi thanh toán/gửi thông báo bên ngoài lần nữa chỉ vì transaction database được retry.
- Dùng idempotency key hoặc outbox pattern khi phối hợp DB với hệ thống ngoài.
- Retry có giới hạn, có backoff và log đủ thông tin.

### 14.4. Chọn isolation level theo yêu cầu

READ COMMITTED phù hợp với phần lớn OLTP Oracle. SERIALIZABLE và READ ONLY hữu ích khi nghiệp vụ cần snapshot ở cấp transaction, nhưng có thể làm transaction gặp xung đột serialization hoặc cần undo lâu hơn.

Không nâng isolation level chỉ để “tránh mọi lỗi đồng thời”. Isolation level không thay thế khóa hàng, version check hay thiết kế transaction.

## 15. Dọn dữ liệu sau các thí nghiệm

Trước khi dọn, bảo đảm cả A và B không còn transaction mở. Chạy COMMIT hoặc ROLLBACK rõ ràng trong từng session. Sau đó, trong một kết nối:

~~~sql
SELECT row_id, category, amount, version_no, note
FROM lab_iso_rows
ORDER BY row_id;
~~~

Khi không cần dữ liệu lab nữa:

~~~sql
DROP TABLE lab_iso_rows PURGE;
~~~

DDL Oracle có implicit commit trước/sau DDL trong các ngữ cảnh thông thường. Vì vậy, chỉ chạy DROP TABLE sau khi mọi transaction lab đã kết thúc; không dùng DDL để cố giải phóng lock trong khi thí nghiệm còn đang chạy.

## 16. Checklist khi tự mô phỏng

- [ ] Mở hai kết nối database độc lập và xác nhận SID khác nhau.
- [ ] Tắt autocommit hoặc hiểu rõ chế độ transaction của công cụ.
- [ ] Tạo dữ liệu lab và COMMIT trạng thái ban đầu.
- [ ] Ghi rõ statement nào chạy ở A, statement nào chạy ở B.
- [ ] Không COMMIT sớm ở session đang giữ lock trước khi quan sát.
- [ ] Phân biệt SELECT consistent read với SELECT FOR UPDATE.
- [ ] Kiểm tra B có thấy dữ liệu chưa commit hay không.
- [ ] Thử nonrepeatable read và phantom trong READ COMMITTED.
- [ ] Thử NOWAIT, WAIT và SKIP LOCKED trên các hàng khác nhau.
- [ ] Thử lost update và so sánh version-based với SELECT FOR UPDATE.
- [ ] Bắt đầu SERIALIZABLE/READ ONLY trước câu SQL đầu tiên của transaction.
- [ ] Quan sát ORA-08177, ORA-00054, ORA-30006 hoặc ORA-00060 khi điều kiện được tái hiện.
- [ ] Dùng V$SESSION/V$LOCK để tìm blocker nếu có quyền.
- [ ] Rollback/commit cả hai session sau mỗi bài.
- [ ] Chỉ dọn bảng lab sau khi mọi transaction đã kết thúc.

## 17. Ghi nhớ cốt lõi

- Muốn kiểm chứng concurrency phải dùng hai session độc lập; hai worksheet chung một connection không tạo ra hai transaction độc lập.
- Oracle READ COMMITTED tạo snapshot cho từng statement: không dirty read, nhưng có thể nonrepeatable read và phantom giữa các câu SELECT.
- SELECT thông thường dùng undo để đọc phiên bản nhất quán và thường không chờ row lock của writer.
- Hai writer sửa cùng hàng phải tuần tự hóa; session thứ hai có thể chờ đến khi transaction đầu COMMIT/ROLLBACK.
- SELECT FOR UPDATE khóa hàng để đọc-sửa-ghi; NOWAIT, WAIT và SKIP LOCKED thay đổi cách xử lý khi hàng đang bị khóa.
- Lost update có thể xảy ra khi client ghi giá trị tuyệt đối tính từ một lần đọc cũ; dùng phép cập nhật tương đối, SELECT FOR UPDATE hoặc optimistic version.
- SERIALIZABLE và READ ONLY cho snapshot ở cấp transaction theo semantics riêng; SERIALIZABLE có thể báo ORA-08177 khi ghi xung đột.
- Deadlock là vòng chờ tài nguyên; ORA-00060 thường rollback statement gây deadlock, không mặc nhiên rollback toàn transaction.
- TX enqueue thường gắn với transaction/row contention; TM enqueue liên quan table-level DML lock. Xác định đúng blocker và object trước khi xử lý.
- Transaction ngắn, thứ tự khóa nhất quán, retry có giới hạn và idempotency giúp ứng dụng xử lý đồng thời an toàn hơn.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database Concepts](https://docs.oracle.com/en/database/) — Transactions, data concurrency and consistency, locking và multiversion read consistency.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SET TRANSACTION, SELECT FOR UPDATE, NOWAIT, WAIT và SKIP LOCKED.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/) — Managing data concurrency, locks và transaction management.
- [Oracle Database Reference](https://docs.oracle.com/en/database/) — V$SESSION, V$LOCK, V$LOCKED_OBJECT và dynamic performance views.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — ORA-00054, ORA-00060, ORA-08177 và ORA-30006.

Chi tiết lock mode, wait event và lỗi có thể phụ thuộc phiên bản, cấu hình và loại thao tác. Hãy chạy từng bước trên schema lab, giữ transaction mở đúng thời điểm và ghi lại SID/event/blocker để kết quả có thể tái hiện.

