# VERSIONS BETWEEN và xem lịch sử thay đổi của dòng

Oracle Flashback Versions Query cho phép xem các phiên bản của một dòng dữ liệu trong một khoảng thời gian hoặc khoảng SCN. Thay vì chỉ trả về trạng thái hiện tại của hàng, truy vấn có thể trả nhiều phiên bản đã tồn tại trong khoảng được chọn, cùng metadata cho biết phiên bản bắt đầu/kết thúc khi nào, transaction nào tạo ra phiên bản và thao tác DML nào liên quan.

Đây là công cụ hữu ích khi cần điều tra:

- Một hàng đã thay đổi giá trị qua những lần nào?
- Giá trị trước và sau một lần UPDATE là gì?
- Hàng đã bị DELETE trong khoảng thời gian nào?
- Transaction nào tạo ra phiên bản đang xem?
- Dữ liệu thay đổi trước một sự cố hoặc thao tác nhầm ra sao?

Flashback Versions Query dựa trên thông tin phiên bản hàng và UNDO mà Oracle còn giữ. Nó không phải audit log vĩnh viễn, không thay thế backup và không bảo đảm có thể xem lịch sử vô thời hạn. Muốn có lịch sử lâu dài, có danh tính người dùng, lý do nghiệp vụ hoặc khả năng chứng minh tuân thủ, cần thiết kế auditing/CDC hoặc bảng lịch sử riêng.

## 1. Flashback Versions Query là gì?

Flashback Versions Query là khả năng truy vấn các phiên bản của hàng trong một khoảng SCN hoặc timestamp bằng mệnh đề VERSIONS BETWEEN.

Ví dụ cơ bản:

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100;
~~~

Nếu hàng nhân viên 100 đã có nhiều phiên bản trong khoảng SCN đó, kết quả có thể chứa nhiều dòng cùng EMPLOYEE_ID nhưng giá trị SALARY khác nhau. Mỗi dòng kết quả đại diện cho một phiên bản hàng.

### 1.1 Khác với SELECT thông thường

SELECT thông thường đọc trạng thái hiện tại:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE employee_id = 100;
~~~

Flashback Versions Query đọc các phiên bản của hàng trong một khoảng:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

### 1.2 Mỗi hàng kết quả là một row version

Giả sử một nhân viên có lương thay đổi:

~~~text
SCN 100: INSERT salary = 5000
SCN 150: UPDATE salary = 6000
SCN 190: UPDATE salary = 7000
SCN 230: DELETE employee
~~~

Trong một khoảng chứa các thay đổi đó, Versions Query có thể trả về các phiên bản tương ứng:

| Phiên bản | Giá trị SALARY | Thao tác tạo phiên bản | Khoảng tồn tại minh họa |
|---|---:|---|---|
| V1 | 5000 | I | SCN 100 đến trước 150 |
| V2 | 6000 | U | SCN 150 đến trước 190 |
| V3 | 7000 | U | SCN 190 đến trước 230 |
| V4 | Giá trị của hàng trước khi bị xóa | D | Phiên bản liên quan thao tác DELETE |

Bảng này mô tả khái niệm row version. Giá trị NULL ở các pseudocolumn biên và cách hiển thị phiên bản phụ thuộc khoảng truy vấn và lịch sử còn trong UNDO.

## 2. Cú pháp VERSIONS BETWEEN

Có hai cách xác định khoảng:

- SCN: dùng số System Change Number.
- TIMESTAMP: dùng thời gian.

### 2.1 Truy vấn theo SCN

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN SCN 100000 AND 200000
WHERE employee_id = 100;
~~~

SCN là mốc logic của database, phù hợp khi cần xác định ranh giới recovery hoặc tương quan với log/transaction.

### 2.2 Truy vấn theo timestamp

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 09:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 10:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100;
~~~

Timestamp dễ hiểu với người vận hành, nhưng ánh xạ timestamp sang SCN có độ chính xác và phạm vi phụ thuộc metadata Oracle còn lưu. Nếu cần ranh giới chính xác, hãy lưu SCN tại thời điểm nghiệp vụ quan trọng.

### 2.3 Dùng TIMESTAMP literal

Có thể dùng timestamp literal:

~~~sql
SELECT employee_id,
       salary
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TIMESTAMP '2026-11-14 09:00:00'
AND TIMESTAMP '2026-11-14 10:00:00'
WHERE employee_id = 100;
~~~

Đảm bảo kiểu timestamp và timezone được hiểu đúng với yêu cầu nghiệp vụ. Nếu hệ thống dùng timezone khác nhau giữa ứng dụng, database và vận hành, hãy ghi rõ quy ước thời gian.

### 2.4 Lấy SCN hiện tại

Có thể lấy SCN hiện tại bằng:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS current_scn
FROM dual;
~~~

Để khoanh vùng một thao tác, ghi SCN trước và sau thao tác trong cùng database:

~~~sql
SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_before
FROM dual;

-- Thực hiện thao tác cần theo dõi và COMMIT.

SELECT DBMS_FLASHBACK.GET_SYSTEM_CHANGE_NUMBER AS scn_after
FROM dual;
~~~

SCN đọc trước/sau là mốc tham chiếu. Transaction có thể commit ở SCN khác với thời điểm câu lệnh bắt đầu; hãy dùng commit/transaction metadata khi cần điều tra chính xác.

## 3. Các pseudocolumn của Versions Query

Oracle cung cấp các pseudocolumn để mô tả mỗi row version:

| Pseudocolumn | Ý nghĩa |
|---|---|
| VERSIONS_STARTSCN | SCN tại đó phiên bản hàng bắt đầu |
| VERSIONS_STARTTIME | Timestamp tương ứng thời điểm phiên bản bắt đầu |
| VERSIONS_ENDSCN | SCN tại đó phiên bản hàng kết thúc/hết hiệu lực |
| VERSIONS_ENDTIME | Timestamp tương ứng thời điểm phiên bản kết thúc |
| VERSIONS_XID | Transaction ID tạo ra phiên bản hàng |
| VERSIONS_OPERATION | Loại thao tác tạo phiên bản: I, U hoặc D |

Các pseudocolumn này chỉ có ý nghĩa trong query block dùng VERSIONS BETWEEN. Chúng không phải cột vật lý được lưu trong bảng.

### 3.1 VERSIONS_STARTSCN

VERSIONS_STARTSCN cho biết SCN bắt đầu của row version.

Nếu phiên bản đã bắt đầu trước lower bound của khoảng truy vấn, giá trị có thể là NULL vì thời điểm bắt đầu nằm ngoài khoảng được yêu cầu.

### 3.2 VERSIONS_ENDSCN

VERSIONS_ENDSCN cho biết SCN tại đó phiên bản kết thúc hoặc bị thay thế bởi phiên bản tiếp theo.

Nếu phiên bản còn hiệu lực tại upper bound của khoảng truy vấn, giá trị có thể là NULL.

### 3.3 STARTTIME và ENDTIME

VERSIONS_STARTTIME và VERSIONS_ENDTIME là dạng timestamp tương ứng với ranh giới row version. Chúng hữu ích để đọc kết quả trực quan, nhưng SCN thường phù hợp hơn khi cần tương quan với recovery hoặc transaction metadata.

### 3.4 VERSIONS_XID

VERSIONS_XID là transaction identifier của transaction tạo ra row version. Một transaction có thể thay đổi nhiều hàng; các phiên bản được tạo bởi cùng transaction có thể có cùng XID.

XID không trực tiếp cho biết username, application module hoặc người dùng nghiệp vụ. Muốn biết thêm chi tiết cần tương quan với nguồn thông tin khác, nếu thông tin đó còn tồn tại và người truy vấn có quyền.

### 3.5 VERSIONS_OPERATION

VERSIONS_OPERATION mô tả thao tác liên quan tới phiên bản:

- I: INSERT.
- U: UPDATE.
- D: DELETE.

Với UPDATE, một phiên bản mới được tạo và phiên bản cũ hết hiệu lực. Với DELETE, Versions Query có thể trả phiên bản hàng liên quan tới thao tác xóa trong khoảng được hỏi.

Không coi pseudocolumn này là audit record đầy đủ. Nó không tự cung cấp lý do thay đổi, câu lệnh gốc, người dùng ứng dụng hay nội dung request.

## 4. Truy vấn đầy đủ lịch sử của một dòng

Giả sử bảng EMPLOYEES:

~~~sql
CREATE TABLE employees (
    employee_id   NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    department_id NUMBER,
    salary        NUMBER(12,2)
);
~~~

Truy vấn lịch sử của một nhân viên:

~~~sql
SELECT employee_id,
       employee_name,
       department_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_starttime,
       versions_endtime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id
ORDER BY versions_startscn NULLS FIRST,
         versions_starttime NULLS FIRST;
~~~

Đây là mẫu truy vấn thường dùng khi điều tra một khóa chính. Thay bind bằng SCN và EMPLOYEE_ID thực tế.

### 4.1 Luôn lọc theo khóa nghiệp vụ

Nếu bảng có primary key, dùng khóa đó để chọn dòng cần xem. Tránh dựa duy nhất vào ROWID làm định danh lâu dài:

- ROWID có thể thay đổi sau move, shrink, export/import hoặc tái tổ chức segment.
- Một khóa chính thể hiện danh tính logic của hàng.
- Versions Query có thể trả nhiều phiên bản cùng primary key; đó chính là điều cần quan sát.

### 4.2 Sắp xếp kết quả

Nên sắp xếp theo VERSIONS_STARTSCN và khóa chính để nhìn tiến trình thay đổi. Nếu có phiên bản với STARTSCN NULL, đặt NULLS FIRST để thấy phiên bản đã tồn tại trước lower bound.

Không dựa vào thứ tự trả về mặc định; SQL không bảo đảm thứ tự nếu thiếu ORDER BY.

## 5. Ví dụ INSERT, UPDATE và DELETE

Thực hiện trong schema lab:

~~~sql
CREATE TABLE employee_history_demo (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(100),
    salary NUMBER(12,2)
);
~~~

Chèn hàng:

~~~sql
INSERT INTO employee_history_demo
    (employee_id, employee_name, salary)
VALUES
    (101, 'An', 5000);

COMMIT;
~~~

Cập nhật lần thứ nhất:

~~~sql
UPDATE employee_history_demo
SET salary = 6000
WHERE employee_id = 101;

COMMIT;
~~~

Cập nhật lần thứ hai:

~~~sql
UPDATE employee_history_demo
SET salary = 7000
WHERE employee_id = 101;

COMMIT;
~~~

Xóa hàng:

~~~sql
DELETE FROM employee_history_demo
WHERE employee_id = 101;

COMMIT;
~~~

Truy vấn các phiên bản:

~~~sql
SELECT employee_id,
       employee_name,
       salary,
       versions_startscn,
       versions_endscn,
       versions_xid,
       versions_operation
FROM employee_history_demo
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '1' HOUR
AND SYSTIMESTAMP
WHERE employee_id = 101
ORDER BY versions_startscn;
~~~

Nếu UNDO vẫn còn đủ và các giới hạn của Flashback Query được đáp ứng, kết quả có thể cho thấy các giá trị lương qua các phiên bản và thao tác liên quan. Nếu dữ liệu đã vượt thời gian lưu giữ UNDO, query có thể không trả đủ lịch sử.

### 5.1 Vì sao cần COMMIT?

Flashback Versions Query phục vụ xem các phiên bản đã được commit trong lịch sử. Thay đổi chưa commit của session khác không phải một phiên bản lịch sử ổn định để truy vấn như một commit đã hoàn tất.

Nếu transaction update rồi rollback, thay đổi rollback không trở thành row version đã commit trong lịch sử.

## 6. Đọc kết quả theo vòng đời row version

Giả sử một hàng có ba phiên bản đã commit:

~~~text
Version A: salary 5000
  STARTSCN = 100
  ENDSCN   = 150
  OPERATION = I

Version B: salary 6000
  STARTSCN = 150
  ENDSCN   = 190
  OPERATION = U

Version C: salary 7000
  STARTSCN = 190
  ENDSCN   = NULL
  OPERATION = U
~~~

Diễn giải:

- Version A được tạo bởi INSERT và tồn tại cho tới khi UPDATE tạo version B.
- Version B được tạo bởi UPDATE đầu tiên và tồn tại tới UPDATE tiếp theo.
- Version C là phiên bản hiện tại tại upper bound của truy vấn, vì vậy ENDSCN có thể NULL.

Đây là mô hình giải thích. SCN thực tế là giá trị do database cấp; ranh giới chính xác phải đọc từ kết quả.

### 6.1 Hàng được tạo trước khoảng truy vấn

Nếu một hàng đã tồn tại trước SCN bắt đầu, row version đầu tiên có thể có VERSIONS_STARTSCN NULL vì thời điểm tạo nằm trước lower bound.

Điều đó không có nghĩa hàng không có lịch sử hoặc không có transaction tạo ra nó; chỉ có nghĩa ranh giới tạo nằm ngoài khoảng đang yêu cầu.

### 6.2 Hàng vẫn tồn tại ở cuối khoảng

Nếu row version còn hiệu lực tại upper bound, VERSIONS_ENDSCN có thể NULL. Đây không phải lỗi dữ liệu.

### 6.3 Hàng bị xóa

Nếu DELETE nằm trong khoảng, Versions Query có thể trả phiên bản liên quan thao tác xóa với VERSIONS_OPERATION = D. Dữ liệu hiển thị là phiên bản hàng gắn với thao tác đó, hữu ích để xem giá trị trước khi hàng biến mất.

Sau khi DELETE, SELECT thông thường không còn trả hàng đó, nhưng Versions Query có thể cho thấy phiên bản lịch sử trong phạm vi UNDO.

## 7. Lọc lịch sử theo loại thao tác

Chỉ xem các phiên bản do UPDATE:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'U'
ORDER BY versions_startscn;
~~~

Chỉ xem INSERT:

~~~sql
SELECT employee_id,
       employee_name,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'I';
~~~

Chỉ xem DELETE:

~~~sql
SELECT employee_id,
       employee_name,
       salary,
       versions_startscn,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE versions_operation = 'D';
~~~

Các truy vấn trên là ví dụ lọc. Phiên bản có thể có pseudocolumn NULL ở biên của khoảng, vì vậy không nên dùng một điều kiện lọc operation như bằng chứng duy nhất về mọi thao tác từng xảy ra.

## 8. So sánh SCN và TIMESTAMP

| Tiêu chí | SCN | TIMESTAMP |
|---|---|---|
| Bản chất | Mốc logic của database | Mốc thời gian |
| Độ chính xác | Phù hợp làm mốc nội bộ/recovery | Phụ thuộc ánh xạ timestamp-SCN |
| Dễ đọc | Khó đọc với người vận hành | Dễ hiểu |
| Tương quan redo/recovery | Trực tiếp hơn | Có thể cần chuyển đổi |
| Rủi ro | Lấy sai SCN hoặc sai incarnation/context | Timezone, clock và mapping |
| Dùng khi | Điều tra chính xác theo SCN | Điều tra theo thời điểm nghiệp vụ |

### 8.1 TIMESTAMP_TO_SCN

Có thể chuyển timestamp sang SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP('2026-11-14 09:30:00',
                        'YYYY-MM-DD HH24:MI:SS')
       ) AS target_scn
FROM dual;
~~~

Hàm chỉ hoạt động trong phạm vi mapping timestamp-SCN mà Oracle còn lưu. Timestamp-to-SCN là ánh xạ xấp xỉ theo metadata, không phải phép chuyển đổi chính xác tuyệt đối cho mọi thời điểm lịch sử.

### 8.2 SCN_TO_TIMESTAMP

~~~sql
SELECT SCN_TO_TIMESTAMP(:target_scn)
FROM dual;
~~~

Hàm trả timestamp gần đúng tương ứng SCN nếu mapping còn khả dụng. Không coi kết quả là timestamp commit có độ chính xác tới từng mili giây.

### 8.3 Timezone và đồng hồ

Khi điều tra incident:

- Xác định timezone của database session.
- Xác định timezone của ứng dụng/log.
- Xác định máy chủ có đồng bộ NTP hay không.
- Ghi SCN nếu có thể tại thời điểm sự kiện.
- Không so sánh chuỗi timestamp mà bỏ qua timezone.

## 9. VERSIONS BETWEEN và AS OF khác nhau

Flashback Query AS OF trả trạng thái bảng tại một mốc:

~~~sql
SELECT employee_id,
       salary
FROM employees AS OF SCN :target_scn
WHERE employee_id = :employee_id;
~~~

Flashback Versions Query trả nhiều row version trong một khoảng:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_endscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id;
~~~

| Câu hỏi | Cơ chế |
|---|---|
| Hàng có giá trị gì tại SCN X? | AS OF SCN |
| Hàng có giá trị gì tại thời điểm T? | AS OF TIMESTAMP |
| Hàng có những phiên bản nào trong khoảng X-Y? | VERSIONS BETWEEN SCN |
| Những phiên bản nào tồn tại trong khoảng thời gian T1-T2? | VERSIONS BETWEEN TIMESTAMP |

AS OF phù hợp để xem một snapshot. VERSIONS BETWEEN phù hợp để xem diễn biến nhiều phiên bản.

## 10. Tương quan VERSIONS_XID với transaction

VERSIONS_XID cho biết transaction tạo ra row version. Có thể dùng XID để tìm thông tin transaction trong nguồn metadata phù hợp.

Một nguồn Oracle cung cấp là FLASHBACK_TRANSACTION_QUERY, tùy quyền và cấu hình:

~~~sql
SELECT xid,
       start_scn,
       commit_scn,
       start_timestamp,
       commit_timestamp,
       logon_user,
       operation,
       table_name,
       undo_sql
FROM flashback_transaction_query
WHERE xid = :xid;
~~~

View này có thể cung cấp thông tin transaction và UNDO_SQL trong những điều kiện được hỗ trợ. Khả năng truy vấn phụ thuộc quyền, supplemental logging và metadata còn lưu; không phải mọi transaction đều có đầy đủ thông tin.

### 10.1 Quyền truy cập transaction metadata

Để xem transaction metadata, user có thể cần quyền SELECT ANY TRANSACTION cùng các quyền đọc view liên quan. Đây là quyền rộng và nhạy cảm; chỉ DBA hoặc vai trò được phê duyệt mới nên được cấp.

Để chạy Versions Query trên bảng, người dùng cần quyền SELECT và quyền FLASHBACK phù hợp trên đối tượng, hoặc quyền hệ thống tương ứng theo chính sách:

~~~sql
GRANT SELECT ON employees TO analyst;
GRANT FLASHBACK ON employees TO analyst;
~~~

Không cấp FLASHBACK ANY TABLE hoặc SELECT ANY TRANSACTION cho ứng dụng chỉ để hỗ trợ một báo cáo lịch sử.

### 10.2 XID không phải user identity đầy đủ

XID định danh transaction ở tầng database. Nó không nhất thiết cho biết người dùng cuối đã bấm nút nào hoặc request HTTP nào. Nếu cần tương quan, ứng dụng nên gắn MODULE, ACTION, CLIENT_IDENTIFIER và hệ thống audit theo quy ước bảo mật.

### 10.3 UNDO_SQL không phải script replay an toàn

UNDO_SQL có thể hữu ích để hiểu thao tác đảo ngược ở tầng SQL. Không chạy trực tiếp hàng loạt UNDO_SQL trong production mà không kiểm tra:

- Thứ tự transaction.
- Foreign key và trigger.
- Side effect ngoài database.
- Sequence hoặc package state.
- Dữ liệu đã thay đổi tiếp sau đó.
- Điều kiện nghiệp vụ hiện tại.

UNDO_SQL là thông tin điều tra, không thay thế quy trình phục hồi có kiểm soát.

## 11. UNDO và thời gian lưu giữ lịch sử

Flashback Versions Query dựa trên thông tin UNDO để tái tạo phiên bản trước đó. Oracle lưu UNDO trong undo tablespace và tái sử dụng theo cơ chế quản lý undo.

Các yếu tố ảnh hưởng khả năng xem lịch sử:

- UNDO_RETENTION.
- Dung lượng undo tablespace.
- Tốc độ transaction/DML.
- Thời gian query.
- Retention guarantee nếu được cấu hình.
- Các thao tác làm thay đổi cấu trúc bảng.

### 11.1 UNDO_RETENTION

Kiểm tra:

~~~sql
SHOW PARAMETER undo_retention;
~~~

UNDO_RETENTION là mục tiêu thời gian giữ undo trong automatic undo management. Đây không phải bảo đảm tuyệt đối rằng mọi phiên bản sẽ tồn tại đủ số giây nếu thiếu dung lượng.

### 11.2 RETENTION GUARANTEE

Undo tablespace có thể được cấu hình retention guarantee trong những trường hợp cần giữ undo lâu hơn:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Khi bật guarantee, Oracle ưu tiên giữ undo chưa hết retention; nếu undo tablespace hết chỗ, các thao tác DML có thể thất bại thay vì ghi đè undo còn cần giữ.

Không bật retention guarantee mà chưa tính dung lượng, peak DML và nguy cơ làm ứng dụng không ghi được dữ liệu.

Có thể kiểm tra:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

### 11.3 ORA-01555 snapshot too old

Nếu undo cần để tái tạo phiên bản đã bị ghi đè, query có thể gặp ORA-01555: snapshot too old.

Hướng điều tra:

- Khoảng VERSIONS BETWEEN có quá dài?
- Query chạy quá lâu?
- DML volume cao?
- Undo tablespace có đủ dung lượng?
- UNDO_RETENTION có phù hợp?
- Có retention guarantee không?

Không chỉ tăng UNDO_RETENTION mà không kiểm tra dung lượng và tốc độ sinh undo.

### 11.4 Lịch sử không còn trong UNDO

Nếu UNDO đã bị tái sử dụng, Flashback Versions Query không thể tự tái tạo đầy đủ row version chỉ từ bảng hiện tại. Khi cần lịch sử lâu dài, phải dùng audit, CDC, temporal/history table hoặc backup/recovery strategy.

## 12. Giới hạn và các trường hợp không dùng được

Flashback Versions Query không phải công cụ lưu trữ lịch sử vô hạn. Một số giới hạn quan trọng:

- Row version chỉ truy vấn được khi thông tin UNDO cần thiết còn khả dụng.
- DDL làm thay đổi định nghĩa bảng trong khoảng có thể khiến flashback query thất bại hoặc bị giới hạn.
- TRUNCATE và các thao tác DDL không được biểu diễn như chuỗi row-level INSERT/UPDATE/DELETE thông thường.
- Một số loại object hoặc bảng đặc biệt có hạn chế hỗ trợ.
- External table, temporary table và một số cấu trúc không có lịch sử UNDO thông thường không phù hợp cho truy vấn này.
- Các thao tác partition maintenance, move, exchange hoặc truncate partition có thể làm mất khả năng truy vấn phiên bản như kỳ vọng.
- Nếu bảng được tạo sau lower bound, hoặc object definition không còn tương thích với thời điểm truy vấn, có thể phát sinh lỗi.

Kiểm tra tài liệu Flashback Query của đúng Oracle release trước khi dựa vào tính năng cho một loại object hoặc thao tác DDL cụ thể.

### 12.1 DDL và ORA-01466

Nếu định nghĩa object thay đổi trong khoảng cần flashback, Oracle có thể không thể đọc dữ liệu theo định nghĩa nhất quán cho thời điểm đó và trả lỗi như ORA-01466.

Không coi Versions Query là công cụ khôi phục mọi thay đổi DDL. DDL cần audit/deployment log và backup/recovery strategy riêng.

### 12.2 TRUNCATE khác DELETE

DELETE là DML và có thể tạo row version được phản ánh trong Flashback Versions Query nếu UNDO còn.

TRUNCATE là DDL, không tạo lịch sử từng hàng theo cách DELETE làm. Nếu table bị truncate, không mong đợi VERSIONS BETWEEN liệt kê mọi hàng trước truncate như một loạt thao tác DELETE.

### 12.3 Transaction chưa commit

Versions Query phục vụ lịch sử phiên bản đã commit. Transaction đang mở hoặc rollback không nên được diễn giải như một lịch sử commit hoàn chỉnh.

## 13. Phân tích nhiều dòng trong cùng một transaction

Một transaction có thể cập nhật nhiều hàng:

~~~sql
UPDATE employees
SET department_id = 20
WHERE department_id = 10;

COMMIT;
~~~

Các row version được tạo bởi cùng transaction có thể có cùng VERSIONS_XID. Có thể nhóm theo XID để nhận biết một nhóm thay đổi có cùng transaction:

~~~sql
SELECT versions_xid,
       versions_operation,
       COUNT(*) AS row_count,
       MIN(versions_startscn) AS first_start_scn,
       MAX(versions_startscn) AS last_start_scn
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
GROUP BY versions_xid, versions_operation
ORDER BY first_start_scn;
~~~

Đây là cách nhóm dữ liệu minh họa. Một transaction có thể tác động nhiều bảng; muốn dựng đầy đủ transaction cần truy vấn các bảng liên quan và metadata transaction, nếu còn.

## 14. Theo dõi thay đổi của nhiều cột

Ví dụ cần xem thay đổi SALARY và DEPARTMENT_ID:

~~~sql
SELECT employee_id,
       salary,
       department_id,
       versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid
FROM employees
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '2' DAY
AND SYSTIMESTAMP
WHERE employee_id = :employee_id
ORDER BY versions_startscn;
~~~

Mỗi phiên bản trả giá trị của hàng ở phiên bản đó. So sánh các phiên bản liên tiếp để xác định cột nào thay đổi.

### 14.1 Tìm thay đổi giá trị cụ thể

Nếu chỉ quan tâm SALARY, có thể hiển thị:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_operation,
       versions_xid
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id
ORDER BY versions_startscn;
~~~

SQL không tự tạo một cột old_value/new_value cho mỗi cột. Muốn so sánh old/new, có thể dùng analytic function trên tập row version đã truy vấn, hoặc xử lý kết quả ở ứng dụng.

## 15. So sánh phiên bản bằng analytic function

Ví dụ dùng LAG để so sánh lương với phiên bản trước:

~~~sql
WITH history AS (
    SELECT employee_id,
           salary,
           versions_startscn,
           versions_operation,
           versions_xid
    FROM employees
    VERSIONS BETWEEN SCN :scn_from AND :scn_to
    WHERE employee_id = :employee_id
)
SELECT employee_id,
       versions_startscn,
       versions_operation,
       salary,
       LAG(salary) OVER (
           PARTITION BY employee_id
           ORDER BY versions_startscn
       ) AS previous_salary
FROM history
ORDER BY versions_startscn;
~~~

LAG cho biết giá trị ở phiên bản trước theo thứ tự SCN. Với phiên bản có STARTSCN NULL, cần quy định cách xử lý thứ tự NULL. Nếu có nhiều row version cùng mốc SCN, cần bổ sung tiêu chí sắp xếp phù hợp và không giả định SCN đơn lẻ luôn tạo thứ tự nghiệp vụ duy nhất cho mọi trường hợp.

### 15.1 Tính chênh lệch

Có thể thêm:

~~~sql
salary - LAG(salary) OVER (
    PARTITION BY employee_id
    ORDER BY versions_startscn
) AS salary_delta
~~~

Chênh lệch này là thay đổi giữa hai row version liền kề trong kết quả. Nó không tự giải thích lý do nghiệp vụ.

## 16. Xem lịch sử xóa và điều tra xóa nhầm

Giả sử hàng CUSTOMER_ID = 500 bị xóa nhầm. Nếu UNDO còn đủ:

~~~sql
SELECT customer_id,
       customer_name,
       email,
       versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid
FROM customers
VERSIONS BETWEEN TIMESTAMP
    SYSTIMESTAMP - INTERVAL '1' DAY
AND SYSTIMESTAMP
WHERE customer_id = 500
ORDER BY versions_startscn;
~~~

Kết quả có thể cho thấy phiên bản cuối trước khi xóa và operation D.

### 16.1 Khôi phục một hàng bằng dữ liệu lịch sử

Nếu xác định được giá trị đúng trước DELETE, có thể cân nhắc INSERT lại hàng bằng các giá trị đã xem, nhưng cần:

- Xác minh mọi cột cần thiết.
- Kiểm tra foreign key.
- Kiểm tra trigger.
- Kiểm tra sequence/identity.
- Kiểm tra dữ liệu liên quan ở bảng con.
- Xác nhận không có transaction hợp lệ đã thay đổi trạng thái sau đó.
- Có phê duyệt nghiệp vụ.

Không copy kết quả query lịch sử vào INSERT một cách máy móc.

### 16.2 Khôi phục bằng Flashback Table

Nếu cần khôi phục cả bảng về một thời điểm, Flashback Table có thể là một cơ chế khác, nhưng nó có phạm vi và điều kiện riêng. Flashback Versions Query chỉ hiển thị lịch sử row version; nó không tự ghi ngược dữ liệu vào bảng.

## 17. Versions Query và Flashback Transaction Query

Hai tính năng có mục đích khác nhau:

| Tính năng | Vai trò |
|---|---|
| Flashback Versions Query | Hiển thị các phiên bản hàng trong một khoảng |
| Flashback Transaction Query | Hiển thị metadata transaction và thông tin undo SQL trong điều kiện hỗ trợ |

VERSIONS_XID là cầu nối để tìm transaction tương ứng. Tuy nhiên, không phải mọi transaction đều có đầy đủ metadata trong FLASHBACK_TRANSACTION_QUERY.

Một số thông tin undo SQL có thể cần supplemental logging phù hợp. Hãy xác nhận điều kiện release và cấu hình trước khi dựa vào nó trong quy trình audit.

## 18. Versions Query không phải audit trail

Flashback Versions Query hữu ích cho điều tra ngắn hạn, nhưng không phải nhật ký kiểm toán đầy đủ.

| Nhu cầu | Versions Query | Audit/CDC/history table |
|---|---|---|
| Xem giá trị row version trước đó | Có, nếu UNDO còn | Có nếu được thiết kế ghi lại |
| Xem thao tác I/U/D | Có metadata operation | Có thể ghi event chi tiết |
| Xem transaction XID | Có | Có thể lưu transaction context |
| Biết người dùng cuối | Không tự cung cấp đầy đủ | Có thể gắn identity/request |
| Biết lý do nghiệp vụ | Không | Có thể ghi reason/business event |
| Lưu nhiều năm | Không bảo đảm | Có thể thiết kế retention dài |
| Chống sửa/xóa lịch sử | Không phải mục tiêu | Có thể thiết kế immutable/off-host |
| Theo dõi DDL | Không đầy đủ | Audit/deployment log phù hợp hơn |

Nếu cần compliance hoặc forensic evidence, dùng Oracle auditing, CDC, application event log hoặc history table theo chính sách. Có thể kết hợp Versions Query để điều tra nhanh trong cửa sổ UNDO.

## 19. Performance và cách viết query

Versions Query có thể tốn tài nguyên vì Oracle phải dựng các phiên bản từ UNDO. Hãy giới hạn:

- Khoảng SCN/time.
- Primary key hoặc partition key.
- Danh sách cột cần xem.
- Số bảng tham gia.

Tránh truy vấn toàn bộ lịch sử của bảng lớn trong một khoảng dài nếu chỉ cần một hàng.

### 19.1 Lọc theo khóa

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_operation
FROM employees
VERSIONS BETWEEN SCN :scn_from AND :scn_to
WHERE employee_id = :employee_id;
~~~

### 19.2 Chỉ lấy cột cần thiết

Không dùng SELECT * khi bảng có LOB hoặc nhiều cột lớn. Chọn cột cần điều tra để giảm dữ liệu phải trả và dễ đọc kết quả.

### 19.3 Khoảng truy vấn ngắn

Bắt đầu với cửa sổ nhỏ quanh thời điểm sự cố, sau đó mở rộng nếu cần. Cửa sổ dài làm tăng công việc truy xuất lịch sử và nguy cơ thiếu UNDO.

### 19.4 Kiểm tra plan

Có thể xem execution plan bằng EXPLAIN PLAN hoặc DBMS_XPLAN.DISPLAY_CURSOR theo quyền. Khi đo runtime, ghi lại SQL_ID, elapsed, buffers và phạm vi thời gian. Không giả định Versions Query luôn dùng index giống SELECT hiện tại.

## 20. Các lỗi thường gặp

### ORA-01555: snapshot too old

UNDO cần thiết không còn đủ để dựng snapshot/row version.

Hướng xử lý:

- Thu hẹp khoảng VERSIONS BETWEEN.
- Chạy query sớm hơn sau sự cố.
- Kiểm tra UNDO_RETENTION và dung lượng undo.
- Xem DML workload có tăng đột biến.
- Nếu cần lịch sử dài hạn, thiết kế audit/history thay vì kéo dài UNDO vô hạn.

### ORA-01466: unable to read data - table definition has changed

Định nghĩa bảng thay đổi trong khoảng cần flashback hoặc metadata object không tương thích.

Hướng xử lý:

- Kiểm tra DDL/deployment log.
- Xác định object definition tại các thời điểm.
- Thu hẹp khoảng thời gian nếu có thể.
- Dùng backup/recovery hoặc nguồn audit khác khi DDL nằm giữa khoảng.

### Không có hàng trả về

Có thể do:

- Không có thay đổi hoặc phiên bản nào trong khoảng.
- SCN/time range sai.
- Sai khóa chính hoặc filter.
- Undo đã hết.
- Bảng/object không hỗ trợ trường hợp truy vấn.
- Quyền SELECT/FLASHBACK chưa đủ.

Không kết luận hàng chưa từng tồn tại chỉ vì query trả 0 hàng.

### VERSIONS_XID là NULL

Một số ranh giới/version nằm ngoài khoảng hoặc không có transaction metadata tương ứng trong kết quả. Đọc STARTSCN/ENDSCN và điều kiện query trước khi suy luận.

## 21. Quy trình điều tra một dòng bị thay đổi

Một quy trình có thể áp dụng:

1. Xác định primary key của hàng.
2. Xác định thời gian nghi vấn và timezone.
3. Lấy SCN nếu có log/application marker.
4. Chọn khoảng SCN/time hẹp.
5. Chạy VERSIONS BETWEEN và lấy pseudocolumns.
6. Sắp xếp theo STARTSCN.
7. So sánh giá trị qua các row version.
8. Ghi VERSIONS_XID và VERSIONS_OPERATION.
9. Nếu được phép, tương quan XID với transaction metadata.
10. Đối chiếu audit/application log để xác định actor và lý do.
11. Nếu cần khôi phục, chọn Flashback Table, row reinsert có kiểm soát hoặc RMAN recovery tùy phạm vi.
12. Lưu bằng chứng và tránh sửa dữ liệu trước khi hoàn tất điều tra.

## 22. Ví dụ thực tế: tìm ai đã đổi lương?

Versions Query có thể cho biết transaction XID, thời điểm và giá trị lương. Nhưng nó không tự cho biết người dùng cuối. Có thể bắt đầu:

~~~sql
SELECT employee_id,
       salary,
       versions_startscn,
       versions_starttime,
       versions_xid,
       versions_operation
FROM employees
VERSIONS BETWEEN TIMESTAMP
    TO_TIMESTAMP('2026-11-14 08:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
AND TO_TIMESTAMP('2026-11-14 12:00:00',
                 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Sau đó:

- Ghi XID của phiên bản UPDATE.
- Kiểm tra transaction metadata nếu quyền và dữ liệu còn.
- Tìm MODULE/ACTION/CLIENT_IDENTIFIER trong audit hoặc application log.
- Đối chiếu thời điểm deploy/job/request.

Nếu ứng dụng không ghi identity/request context, có thể không thể xác định người dùng cuối chỉ từ row version.

## 23. Các thực hành tốt

- Lưu primary key và SCN/time của các thao tác nghiệp vụ quan trọng nếu cần điều tra.
- Dùng Versions Query ngay sau khi phát hiện sự cố, khi UNDO còn khả dụng.
- Không đặt UNDO_RETENTION quá cao mà không dự trù dung lượng.
- Không bật RETENTION GUARANTEE nếu chưa đánh giá ảnh hưởng DML.
- Dùng auditing/CDC/history table cho yêu cầu lưu lịch sử dài hạn.
- Giữ application module/action/client identifier theo convention.
- Bảo vệ quyền FLASHBACK và SELECT ANY TRANSACTION.
- Không chạy UNDO_SQL như script rollback tự động.
- Không dùng Versions Query để thay backup/restore.
- Ghi timezone và SCN trong incident record.

## 24. Bài thực hành tự kiểm tra

Các bài tập nên chạy trong schema lab, với dữ liệu thử nghiệm.

### Bài 1 — Tạo lịch sử một hàng

Tạo bảng demo, INSERT, UPDATE hai lần và DELETE; commit từng thao tác.

### Bài 2 — Query theo SCN

Lấy SCN trước/sau các thao tác, truy vấn VERSIONS BETWEEN SCN và ghi các phiên bản.

### Bài 3 — Query theo timestamp

Truy vấn cùng khoảng bằng VERSIONS BETWEEN TIMESTAMP. So sánh với kết quả theo SCN và chú ý timezone.

### Bài 4 — Đọc pseudocolumns

Giải thích STARTSCN, ENDSCN, STARTTIME, ENDTIME, XID và OPERATION cho từng phiên bản.

### Bài 5 — Lọc theo operation

Lọc I, U và D. Giải thích vì sao DELETE có thể xuất hiện trong Versions Query dù SELECT hiện tại không còn thấy hàng.

### Bài 6 — Nhiều hàng trong một transaction

UPDATE nhiều hàng rồi COMMIT. Nhóm kết quả theo VERSIONS_XID và so sánh số hàng.

### Bài 7 — So sánh bằng LAG

Dùng analytic LAG để hiển thị salary trước đó và tính delta giữa hai row version.

### Bài 8 — Flashback AS OF

So sánh một snapshot AS OF SCN với nhiều phiên bản VERSIONS BETWEEN.

### Bài 9 — Transaction metadata

Trong môi trường được cấp quyền, thử tương quan VERSIONS_XID với FLASHBACK_TRANSACTION_QUERY. Ghi nhận các trường có thể NULL hoặc không khả dụng.

### Bài 10 — Undo retention

Theo dõi UNDO_RETENTION và chạy query trên một khoảng lịch sử. Quan sát điều kiện có thể gây ORA-01555 trong môi trường lab.

### Bài 11 — DDL boundary

Trong database lab riêng, thử thay đổi DDL giữa hai mốc và quan sát giới hạn flashback. Không thực hiện trên dữ liệu quan trọng.

### Bài 12 — Phân biệt Versions Query với audit

Lập bảng thông tin mà Versions Query cung cấp và thông tin cần application audit/CDC để xác định actor, reason và lưu lịch sử dài hạn.

## 25. Checklist trước khi dùng VERSIONS BETWEEN

**Khoảng truy vấn**

- Dùng SCN hay timestamp?
- Timezone có rõ ràng?
- Khoảng có nằm trong thời gian UNDO còn khả dụng?
- Có SCN marker trước/sau sự kiện?

**Định danh hàng**

- Đã có primary key?
- Có lọc đúng hàng?
- Có nhiều phiên bản cùng khóa?
- Có sắp xếp theo STARTSCN?

**Metadata**

- Đã đọc STARTSCN/ENDSCN?
- Đã hiểu NULL ở biên?
- Đã đọc OPERATION?
- Đã lưu XID?
- Có cần tương quan transaction metadata?

**Giới hạn**

- Có DDL/TRUNCATE/partition maintenance trong khoảng?
- Undo có thể đã bị ghi đè?
- Object type có hỗ trợ?
- Quyền SELECT/FLASHBACK có đủ?

**Điều tra và phục hồi**

- Có application/audit log để xác định actor?
- Có cần lưu lịch sử lâu dài?
- Có backup nếu cần recovery rộng?
- Có phê duyệt trước khi sửa/khôi phục dữ liệu?

## 26. Ghi nhớ

| Khái niệm | Điều cần nhớ |
|---|---|
| Flashback Versions Query | Xem nhiều phiên bản hàng trong một khoảng |
| VERSIONS BETWEEN SCN | Chọn khoảng theo SCN |
| VERSIONS BETWEEN TIMESTAMP | Chọn khoảng theo thời gian |
| VERSIONS_STARTSCN | SCN bắt đầu row version |
| VERSIONS_ENDSCN | SCN kết thúc row version |
| VERSIONS_STARTTIME | Thời điểm bắt đầu phiên bản |
| VERSIONS_ENDTIME | Thời điểm kết thúc phiên bản |
| VERSIONS_XID | Transaction ID tạo row version |
| VERSIONS_OPERATION | I, U hoặc D |
| AS OF SCN | Trạng thái tại một SCN |
| TIMESTAMP_TO_SCN | Ánh xạ timestamp sang SCN trong phạm vi hỗ trợ |
| UNDO_RETENTION | Mục tiêu giữ UNDO, không phải bảo đảm tuyệt đối nếu thiếu dung lượng |
| RETENTION GUARANTEE | Giữ undo theo retention, có thể làm DML lỗi khi hết chỗ |
| ORA-01555 | Snapshot/row version cần thiết không còn trong UNDO |
| ORA-01466 | Định nghĩa object thay đổi trong khoảng flashback |
| FLASHBACK_TRANSACTION_QUERY | Transaction metadata/undo SQL trong điều kiện hỗ trợ |
| Audit/CDC | Giải pháp lưu lịch sử lâu dài và actor/business context |

VERSIONS BETWEEN giúp xem diễn biến của một dòng bằng các row version và metadata SCN, timestamp, XID, operation. Dùng SCN khi cần ranh giới logic chính xác; dùng timestamp khi điều tra theo thời điểm nhưng phải chú ý timezone và mapping. Khả năng truy vấn phụ thuộc UNDO còn giữ, quyền FLASHBACK và giới hạn object/DDL. Công cụ này rất hữu ích để điều tra ngắn hạn, nhưng không phải audit trail lâu dài và không tự xác định người dùng cuối. Hãy kết hợp Versions Query với transaction metadata, application context, auditing và backup/recovery phù hợp.
