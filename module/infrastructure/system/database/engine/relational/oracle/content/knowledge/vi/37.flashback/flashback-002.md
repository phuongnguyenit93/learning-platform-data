# AS OF SCN, AS OF TIMESTAMP và truy vấn dữ liệu trong quá khứ

Oracle Flashback Query cho phép truy vấn dữ liệu của một bảng hoặc một đối tượng được hỗ trợ tại một thời điểm trong quá khứ. Hai cách chỉ định mốc thường dùng là **AS OF SCN** và **AS OF TIMESTAMP**.

- SCN (System Change Number) là số thứ tự thay đổi logic của database. Nó xác định một điểm nhất quán trong lịch sử database.
- TIMESTAMP là thời điểm theo đồng hồ. Oracle ánh xạ timestamp sang SCN phù hợp để thực hiện truy vấn.
- AS OF SCN truy vấn trạng thái dữ liệu tại SCN được chỉ định.
- AS OF TIMESTAMP truy vấn trạng thái dữ liệu tại thời điểm được chỉ định.

Ví dụ, nếu một nhân viên bị cập nhật nhầm lương lúc 10:15, DBA có thể truy vấn bảng EMPLOYEES tại SCN trước thao tác đó để xem giá trị cũ. Truy vấn lịch sử chỉ đọc dữ liệu cũ; nó không tự rollback transaction và cũng không tự ghi dữ liệu cũ trở lại bảng hiện tại.

Flashback Query dựa trên thông tin undo còn được giữ trong database. Vì vậy, khả năng truy vấn quá khứ phụ thuộc vào lượng undo, thời gian query, workload ghi đồng thời, cấu hình retention và các thay đổi cấu trúc object. Không thể giả định rằng mọi thời điểm trong quá khứ đều còn truy vấn được.

## 1. Flashback Query giải quyết vấn đề gì?

Trong hệ thống đang hoạt động, dữ liệu liên tục thay đổi bởi INSERT, UPDATE và DELETE. Khi cần kiểm tra một trạng thái cũ, truy vấn thông thường chỉ trả về dữ liệu hiện tại.

Flashback Query cho phép đặt một mốc lịch sử vào câu SELECT để đọc phiên bản dữ liệu tại thời điểm đó.

Các trường hợp sử dụng:

- Kiểm tra giá trị trước khi một transaction sửa nhầm dữ liệu.
- Đối chiếu dữ liệu trước và sau một lần chạy batch.
- Xác định một hàng đã có trạng thái gì tại thời điểm xảy ra sự cố.
- So sánh dữ liệu tại hai SCN.
- Điều tra một thao tác DELETE hoặc UPDATE ngoài ý muốn.
- Tạo bản sao kiểm tra từ dữ liệu lịch sử trước khi quyết định phục hồi.
- Hỗ trợ audit và phân tích sự cố khi dữ liệu undo còn sẵn.

### 1.1. Ví dụ dữ liệu thay đổi

Giả sử bảng EMPLOYEES có hàng:

~~~sql
EMPLOYEE_ID  NAME   SALARY
-----------  -----  -------
100          AN     3000
~~~

Sau đó một thao tác cập nhật nhầm:

~~~sql
UPDATE employees
SET salary = 300
WHERE employee_id = 100;

COMMIT;
~~~

Truy vấn bình thường sẽ thấy SALARY = 300. Nếu undo cần thiết vẫn còn, có thể truy vấn trạng thái trước thao tác:

~~~sql
SELECT employee_id,
       name,
       salary
FROM employees AS OF SCN 123456789
WHERE employee_id = 100;
~~~

Kết quả lịch sử có thể trả về SALARY = 3000. SCN trong ví dụ chỉ là số minh họa; phải dùng SCN thực tế trước transaction cần điều tra.

### 1.2. Flashback Query không phải rollback

Câu SELECT AS OF chỉ đọc dữ liệu lịch sử. Nó không:
- Hủy transaction đã COMMIT.
- Thay đổi hàng hiện tại.
- Khôi phục toàn bộ database.
- Tạo backup mới.
- Bảo đảm dữ liệu lịch sử tồn tại vô thời hạn.

Nếu cần phục hồi một số hàng, hãy truy vấn lịch sử, xác nhận dữ liệu với owner và thực hiện DML riêng theo kế hoạch có kiểm soát. Nếu cần quay lại toàn bộ database tới một thời điểm, đó là bài toán Flashback Database hoặc RMAN point-in-time recovery.

## 2. SCN và TIMESTAMP

### 2.1. SCN là gì?

SCN là số thứ tự logic Oracle sử dụng để sắp xếp các thay đổi và xác định tính nhất quán. SCN không phải số thứ tự của một hàng, cũng không phải số giây kể từ một epoch.

Một transaction có thể tạo ra các thay đổi được xác định bởi SCN khi commit. SCN giúp Oracle xác định phiên bản dữ liệu nào có thể nhìn thấy tại một điểm nhất quán.

Các đặc điểm cần nhớ:
- SCN tăng theo tiến trình thay đổi của database.
- SCN là định danh logic, không phải đồng hồ thời gian.
- Một SCN có thể được dùng làm mốc chung cho nhiều bảng trong một câu truy vấn.
- Không tự tính SCN bằng cách cộng số giây hoặc số transaction.
- Không so sánh SCN giữa các database khác nhau như thể chúng cùng một timeline.

### 2.2. TIMESTAMP là gì?

TIMESTAMP là mốc thời gian theo đồng hồ. Nó dễ đọc với con người và thường thuận tiện khi người dùng biết sự cố xảy ra lúc 10:15 hoặc trước một thời điểm nghiệp vụ.

Ví dụ:

~~~sql
TO_TIMESTAMP(
    '2026-11-14 10:15:00',
    'YYYY-MM-DD HH24:MI:SS'
)
~~~

Khi dùng timestamp:
- Format model phải khớp chuỗi.
- Xác định timezone của mốc thời gian.
- Không dựa vào NLS_DATE_FORMAT mặc định.
- Chú ý clock skew giữa application host, database host và hệ thống log.
- Tránh timestamp mơ hồ khi có thay đổi daylight saving time.

### 2.3. Khi nào chọn SCN, khi nào chọn TIMESTAMP?

| Nhu cầu | Nên ưu tiên |
| --- | --- |
| Có SCN đã ghi nhận ngay trước transaction | AS OF SCN |
| Có thời điểm từ log ứng dụng hoặc incident timeline | AS OF TIMESTAMP |
| Cần cùng một mốc chính xác cho nhiều bảng | AS OF SCN |
| Người vận hành chỉ biết thời gian xảy ra sự cố | AS OF TIMESTAMP, sau đó có thể đổi sang SCN |
| Cần tái lập một điểm nhất quán đã lưu trong audit | AS OF SCN |
| Cần truy vấn gần một thời điểm wall-clock | AS OF TIMESTAMP |

Nếu ứng dụng có thể ghi lại SCN tại ranh giới nghiệp vụ, SCN thường là lựa chọn tốt cho điều tra chính xác. Nếu chỉ có timestamp, cần hiểu Oracle ánh xạ thời gian sang SCN theo độ phân giải và lịch sử mapping hiện có.

## 3. Điều kiện để sử dụng Flashback Query

Flashback Query cần dữ liệu lịch sử đủ để Oracle tái tạo phiên bản được yêu cầu.

Các điều kiện quan trọng:

1. Database và object phải tồn tại tại mốc được truy vấn.
2. Undo cần thiết vẫn còn và có thể đọc.
3. User có quyền SELECT và quyền Flashback phù hợp.
4. Object chưa có thay đổi cấu trúc làm mất khả năng truy vấn qua mốc đó.
5. Mốc SCN/TIMESTAMP hợp lệ trong phạm vi lịch sử được Oracle hỗ trợ.
6. Câu truy vấn chỉ sử dụng các object và cấu trúc được Flashback Query hỗ trợ.

### 3.1. Undo là nền tảng của Flashback Query

Khi một hàng bị UPDATE hoặc DELETE, Oracle lưu thông tin undo để hỗ trợ rollback và read consistency. Flashback Query sử dụng các phiên bản undo này để dựng lại dữ liệu ở SCN cũ.

Nếu undo đã bị tái sử dụng, Oracle có thể không còn đủ thông tin để trả dữ liệu quá khứ.

### 3.2. UNDO_RETENTION không phải cam kết tuyệt đối trong cấu hình mặc định

Tham số UNDO_RETENTION đặt mục tiêu thời gian giữ undo theo giây trong automatic undo management. Tuy nhiên, khi undo tablespace chịu áp lực dung lượng, Oracle có thể tái sử dụng undo chưa hết retention trong cấu hình mặc định.

Muốn bảo đảm giữ undo chưa hết retention, DBA có thể cân nhắc RETENTION GUARANTEE trên undo tablespace. Cần hiểu rủi ro: nếu không còn chỗ để cấp phát undo mới, transaction DML có thể thất bại thay vì ghi đè undo được bảo vệ.

Không bật RETENTION GUARANTEE chỉ để Flashback Query chạy lâu hơn mà chưa đánh giá dung lượng và workload ghi.

### 3.3. Quyền cần thiết

User cần quyền đọc object và quyền Flashback phù hợp. Chủ sở hữu object có quyền trên object của mình; DBA có thể cấp quyền object cụ thể:

~~~sql
GRANT SELECT, FLASHBACK
ON hr.employees
TO report_user;
~~~

Hoặc cấp quyền hệ thống rộng hơn khi có lý do quản trị:

~~~sql
GRANT FLASHBACK ANY TABLE TO report_user;
~~~

FLASHBACK ANY TABLE có phạm vi rộng. Ưu tiên quyền object-level nếu chỉ cần truy vấn một số bảng. Việc cấp SELECT/FLASHBACK phải tuân theo chính sách least privilege.

Quyền truy vấn V$DATABASE hoặc các dynamic performance view để lấy SCN hiện tại là một vấn đề quyền riêng; user ứng dụng không nhất thiết được cấp quyền đó.

## 4. Truy vấn bằng AS OF SCN

AS OF SCN đặt mốc lịch sử ngay sau tên table trong FROM clause.

### 4.1. Cú pháp cơ bản

~~~sql
SELECT column_list
FROM table_name AS OF SCN scn_expression
WHERE condition;
~~~

SCN expression có thể là một literal hoặc bind variable phù hợp.

Ví dụ:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN 123456789
WHERE employee_id = 100;
~~~

Oracle trả về phiên bản hàng nhìn thấy tại SCN được chỉ định, nếu dữ liệu undo cần thiết vẫn còn.

### 4.2. Dùng bind variable

Trong ứng dụng hoặc SQL*Plus, nên truyền SCN bằng bind variable thay vì ghép chuỗi SQL động:

~~~sql
VARIABLE p_scn NUMBER
EXEC :p_scn := 123456789;

SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id = 100;
~~~

Bind variable giúp tái sử dụng câu SQL và tránh lỗi khi xây dựng câu lệnh từ input. Kiểu bind phải phù hợp với SCN.

### 4.3. Lấy SCN hiện tại

Có thể đọc CURRENT_SCN từ V$DATABASE:

~~~sql
SELECT current_scn
FROM v$database;
~~~

Nếu cần đánh dấu một thời điểm trước khi thực hiện thay đổi nghiệp vụ, lưu SCN cùng request ID hoặc audit event:

~~~sql
INSERT INTO operation_marker (
    request_id,
    captured_scn,
    captured_at
)
SELECT
    :request_id,
    current_scn,
    SYSTIMESTAMP
FROM v$database;
~~~

Ví dụ trên minh họa lưu mốc trước khi thao tác. Bảng operation_marker cần được thiết kế và bảo vệ theo nghiệp vụ. Nếu cần mốc chính xác cho một transaction, phải xác định rõ thời điểm chụp SCN so với DML/COMMIT; không lấy một SCN sau khi sự cố xảy ra rồi gọi đó là baseline trước sự cố.

### 4.4. So sánh dữ liệu hiện tại với dữ liệu tại SCN

~~~sql
SELECT 'CURRENT' AS source,
       employee_id,
       salary
FROM hr.employees
WHERE employee_id = 100
UNION ALL
SELECT 'HISTORICAL' AS source,
       employee_id,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id = 100;
~~~

Kết quả giúp thấy khác biệt giữa hiện tại và mốc lịch sử. Nếu hàng không tồn tại ở một phía, một nhánh có thể không trả dòng nào. Muốn thể hiện đầy đủ trạng thái missing/current/historical, có thể dùng outer join hoặc hai truy vấn kiểm tra riêng.

### 4.5. Dùng cùng SCN cho nhiều bảng

Khi truy vấn các bảng có quan hệ, dùng cùng SCN trên từng table reference:

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.customers AS OF SCN :p_scn c
  ON c.customer_id = o.customer_id
WHERE o.order_id = :p_order_id;
~~~

Điều này giúp các bảng được đọc tại cùng một điểm nhất quán. Nếu chỉ đặt AS OF SCN cho bảng ORDERS nhưng để CUSTOMERS đọc hiện tại, kết quả có thể trộn hai thời điểm và tạo ra quan hệ không phản ánh trạng thái lịch sử thống nhất.

Áp dụng mốc tương tự cho các bảng con trong subquery và view khi cần cùng một snapshot. Với view phức tạp, xác nhận khả năng hỗ trợ và cách Oracle áp dụng flashback clause.

## 5. Truy vấn bằng AS OF TIMESTAMP

AS OF TIMESTAMP thuận tiện khi mốc được biết theo giờ, phút, giây.

### 5.1. Cú pháp cơ bản

~~~sql
SELECT column_list
FROM table_name AS OF TIMESTAMP timestamp_expression
WHERE condition;
~~~

Ví dụ:

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF TIMESTAMP
     TO_TIMESTAMP(
         '2026-11-14 10:15:00',
         'YYYY-MM-DD HH24:MI:SS'
     )
WHERE employee_id = 100;
~~~

Timestamp được Oracle ánh xạ sang SCN phù hợp để thực hiện Flashback Query. Mốc trả về không nên được hiểu là một đồng hồ transaction chính xác tới từng microsecond.

### 5.2. Dùng bind variable kiểu TIMESTAMP

~~~sql
VARIABLE p_time VARCHAR2(19)
EXEC :p_time := '2026-11-14 10:15:00';

SELECT employee_id,
       salary
FROM hr.employees AS OF TIMESTAMP
     TO_TIMESTAMP(:p_time, 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100;
~~~

Trong ứng dụng, tốt hơn nên bind trực tiếp datatype TIMESTAMP nếu driver hỗ trợ, tránh chuyển qua chuỗi và phụ thuộc NLS.

### 5.3. Truy vấn tương đối so với thời điểm hiện tại

Ví dụ truy vấn trạng thái khoảng 10 phút trước:

~~~sql
SELECT employee_id,
       salary
FROM hr.employees AS OF TIMESTAMP
     (CAST(SYSTIMESTAMP AS TIMESTAMP) - INTERVAL '10' MINUTE)
WHERE employee_id = 100;
~~~

Biểu thức thời gian phải có datatype phù hợp và timezone được hiểu rõ. Khi cần tái lập sự cố, lưu timestamp thực tế đã dùng và kết quả SCN mapping nếu có.

### 5.4. Timezone và NLS

Không dùng chuỗi ngày mơ hồ như 11/14/26 nếu không có format model. Không phụ thuộc NLS_TIMESTAMP_FORMAT hoặc NLS_DATE_FORMAT của session.

Nếu timestamp xuất phát từ hệ thống khác:
- Xác định timezone nguồn.
- Chuyển về timezone thống nhất.
- Ghi rõ UTC offset.
- Kiểm tra đồng bộ clock.
- Dùng SCN nếu có thể ghi mốc trực tiếp từ database.

## 6. Chuyển đổi giữa SCN và TIMESTAMP

Oracle cung cấp các hàm ánh xạ SCN và timestamp.

### 6.1. TIMESTAMP_TO_SCN

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               '2026-11-14 10:15:00',
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS target_scn
FROM dual;
~~~

Hàm trả về SCN tương ứng với timestamp theo thông tin mapping mà Oracle còn lưu. Nó hữu ích khi muốn ghi nhận SCN sau khi người vận hành xác định được thời gian sự cố.

### 6.2. SCN_TO_TIMESTAMP

~~~sql
SELECT SCN_TO_TIMESTAMP(123456789) AS approximate_time
FROM dual;
~~~

Hàm trả timestamp gần tương ứng với SCN. Kết quả là mapping thời gian của Oracle, không phải bằng chứng rằng mọi thay đổi đều xảy ra đúng tại thời điểm đó.

### 6.3. Mapping có giới hạn

Oracle không duy trì mapping SCN-to-timestamp vô hạn. Nếu SCN hoặc timestamp nằm ngoài phạm vi mapping còn sẵn, hàm có thể phát sinh lỗi, ví dụ ORA-08181 hoặc ORA-08180 trong các tình huống liên quan.

Phạm vi thực tế phụ thuộc database và lịch sử mapping. Không hard-code giả định rằng timestamp luôn chuyển đổi được trong một số ngày cố định.

### 6.4. SCN và timestamp không thay thế nhau hoàn toàn

- SCN biểu diễn thứ tự logic và thường phù hợp cho ranh giới nhất quán.
- TIMESTAMP thuận tiện cho con người và log.
- Timestamp được ánh xạ sang SCN với độ phân giải hữu hạn.
- SCN_TO_TIMESTAMP trả một thời điểm gần đúng.
- Không so timestamp từ hai host chưa đồng bộ rồi giả định chúng khớp chính xác với SCN.

Nếu sự cố yêu cầu xác định transaction trước/sau một ranh giới cụ thể, ưu tiên SCN được ghi nhận ngay lúc sự kiện xảy ra.

## 7. Truy vấn nhiều bảng tại cùng một thời điểm

Một nghiệp vụ thường trải qua nhiều bảng. Nếu chỉ một bảng được flashback, kết quả có thể không nhất quán về mặt nghiệp vụ.

### 7.1. Ví dụ đơn hàng và chi tiết đơn hàng

~~~sql
SELECT o.order_id,
       o.order_status,
       i.line_id,
       i.product_id,
       i.quantity
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.order_items AS OF SCN :p_scn i
  ON i.order_id = o.order_id
WHERE o.order_id = :p_order_id;
~~~

Cả ORDERS và ORDER_ITEMS được truy vấn tại cùng SCN.

### 7.2. Không trộn current với historical nếu không có chủ đích

Tránh viết:

~~~sql
SELECT o.order_id,
       o.status,
       c.customer_name
FROM sales.orders AS OF SCN :p_scn o
JOIN sales.customers c
  ON c.customer_id = o.customer_id;
~~~

Ở đây ORDERS là historical còn CUSTOMERS là current. Nếu customer được đổi tên sau SCN, kết quả sẽ ghép order cũ với tên hiện tại. Điều đó có thể đúng nếu câu hỏi cần thông tin hiện tại, nhưng không phù hợp nếu mục tiêu là tái dựng toàn bộ trạng thái tại một thời điểm.

### 7.3. Dùng cùng mốc cho subquery

~~~sql
SELECT o.order_id,
       o.status
FROM sales.orders AS OF SCN :p_scn o
WHERE EXISTS (
    SELECT 1
    FROM sales.order_items AS OF SCN :p_scn i
    WHERE i.order_id = o.order_id
      AND i.quantity > 0
);
~~~

Tất cả table reference cần cùng SCN nếu mục tiêu là snapshot nhất quán.

## 8. Truy vấn hàng đã bị UPDATE hoặc DELETE

Flashback Query có thể đọc phiên bản hàng trước thay đổi khi undo còn sẵn.

### 8.1. Hàng bị UPDATE

~~~sql
SELECT employee_id,
       salary,
       department_id
FROM hr.employees AS OF SCN :before_update_scn
WHERE employee_id = 100;
~~~

Nếu hàng vẫn tồn tại hiện tại, câu truy vấn lịch sử trả phiên bản cũ tại SCN.

### 8.2. Hàng bị DELETE

~~~sql
SELECT employee_id,
       first_name,
       last_name
FROM hr.employees AS OF SCN :before_delete_scn
WHERE employee_id = 100;
~~~

Nếu hàng tồn tại tại SCN nhưng đã bị DELETE sau đó, truy vấn lịch sử vẫn có thể trả hàng cũ.

### 8.3. Hàng được INSERT sau mốc lịch sử

Nếu hàng chưa tồn tại tại SCN, truy vấn AS OF SCN sẽ không trả hàng đó. Đây là hành vi đúng của point-in-time query.

### 8.4. Phục hồi hàng có kiểm soát

Không nên trực tiếp UPDATE dữ liệu hiện tại chỉ vì truy vấn lịch sử trả về một giá trị cũ. Quy trình an toàn:
1. Truy vấn hàng tại SCN cần thiết.
2. Lưu kết quả vào bảng staging hoặc xuất ra file được kiểm soát.
3. Xác nhận đúng primary key và các cột cần phục hồi.
4. Kiểm tra các thay đổi hợp lệ phát sinh sau SCN.
5. Lập câu DML chỉ cho các hàng/cột cần sửa.
6. Thực hiện trong transaction có kiểm tra row count.
7. Đối chiếu dữ liệu sau commit.

Ví dụ chèn bản sao vào bảng staging:

~~~sql
INSERT INTO employees_recovery_stage (
    employee_id,
    first_name,
    last_name,
    salary,
    source_scn
)
SELECT employee_id,
       first_name,
       last_name,
       salary,
       :before_update_scn
FROM hr.employees AS OF SCN :before_update_scn
WHERE employee_id = 100;
~~~

Bảng staging cần được tạo với schema phù hợp và bảo vệ dữ liệu. Không dùng INSERT trực tiếp vào bảng nghiệp vụ nếu chưa kiểm tra duplicate key, foreign key, trigger, audit và các thay đổi mới hơn.

## 9. Flashback Versions Query: xem lịch sử trong một khoảng

AS OF SCN/TIMESTAMP trả một trạng thái tại một điểm. Nếu cần xem các phiên bản hàng qua một khoảng, dùng Flashback Versions Query với VERSIONS BETWEEN.

### 9.1. Cú pháp

~~~sql
SELECT versions_startscn,
       versions_endscn,
       versions_operation,
       versions_xid,
       employee_id,
       salary
FROM hr.employees
     VERSIONS BETWEEN SCN :start_scn AND :end_scn
WHERE employee_id = 100
ORDER BY versions_startscn;
~~~

Các pseudocolumn thường dùng:
- VERSIONS_STARTSCN: SCN bắt đầu phiên bản.
- VERSIONS_ENDSCN: SCN kết thúc phiên bản.
- VERSIONS_OPERATION: thao tác tạo phiên bản, thường I, U hoặc D.
- VERSIONS_XID: transaction ID liên quan.

### 9.2. Dùng khoảng TIMESTAMP

~~~sql
SELECT versions_starttime,
       versions_endtime,
       versions_operation,
       employee_id,
       salary
FROM hr.employees
     VERSIONS BETWEEN TIMESTAMP
         TO_TIMESTAMP('2026-11-14 09:00:00', 'YYYY-MM-DD HH24:MI:SS')
     AND TO_TIMESTAMP('2026-11-14 11:00:00', 'YYYY-MM-DD HH24:MI:SS')
WHERE employee_id = 100
ORDER BY versions_starttime;
~~~

Dùng timestamp khi mốc được xác định theo thời gian. Nhớ rằng dữ liệu phiên bản vẫn phụ thuộc undo retention và khả năng mapping.

### 9.3. Khi nào dùng AS OF và khi nào dùng VERSIONS?

| Nhu cầu | Cú pháp |
| --- | --- |
| Xem một hàng tại đúng một SCN | AS OF SCN |
| Xem trạng thái tại một thời điểm wall-clock | AS OF TIMESTAMP |
| Xem các phiên bản hàng trong một khoảng | VERSIONS BETWEEN SCN/TIMESTAMP |
| Xem một trạng thái cũ để đối chiếu | AS OF |
| Điều tra chuỗi INSERT/UPDATE/DELETE của một hàng | VERSIONS BETWEEN |

VERSIONS BETWEEN không phải audit log vô thời hạn. Nó cũng dựa trên lịch sử phiên bản còn khả dụng.

## 10. Flashback Query và các tính năng Flashback khác

Tên gọi gần nhau nhưng các tính năng giải quyết những bài toán khác nhau.

| Tính năng | Mục tiêu | Cơ chế/chạm phạm vi |
| --- | --- | --- |
| Flashback Query | Đọc dữ liệu bảng tại SCN/TIMESTAMP quá khứ | SELECT và undo |
| Flashback Versions Query | Xem các phiên bản hàng trong một khoảng | SELECT, versions và undo |
| Flashback Transaction Query | Xem thông tin transaction liên quan tới thay đổi | Transaction metadata và undo |
| Flashback Table | Đưa một hoặc nhiều bảng về trạng thái cũ | DML nội bộ, yêu cầu điều kiện riêng như row movement |
| Flashback Database | Đưa toàn database về SCN/time trước đó | Flashback logs và database recovery |
| RMAN point-in-time recovery | Restore/recover database tới thời điểm/SCN | Backup và archived redo |

Flashback Query không yêu cầu Flashback Database phải bật. Nó dùng undo, trong khi Flashback Database cần flashback logging và flashback area theo cấu hình.

Không dùng Flashback Table hoặc Flashback Database chỉ vì cần đọc một hàng cũ. Ngược lại, nếu cần phục hồi cả database sau lỗi lớn, một câu SELECT AS OF không thay thế được quy trình recovery.

## 11. Undo retention và nguy cơ ORA-01555

### 11.1. Vì sao Flashback Query có thể thất bại?

Khi query yêu cầu một phiên bản cũ, Oracle phải tìm undo để tái tạo dữ liệu. Nếu undo đã bị ghi đè hoặc không còn đủ, truy vấn có thể thất bại.

Nguyên nhân:
- UNDO_RETENTION quá thấp so với tuổi dữ liệu cần truy vấn.
- Undo tablespace không đủ dung lượng.
- DML workload tăng đột biến.
- Query lịch sử chạy lâu.
- Transaction lớn tạo undo nhanh.
- RETENTION GUARANTEE chưa được bật và Oracle tái sử dụng unexpired undo khi cần.

### 11.2. ORA-01555: snapshot too old

ORA-01555 thường cho biết Oracle không thể giữ hoặc tìm được phiên bản undo cần thiết cho read-consistent query. Flashback Query có thể gặp lỗi này khi lịch sử không còn đủ.

Không giả định tăng UNDO_RETENTION một mình sẽ giải quyết vấn đề. Cần xem dung lượng undo, tốc độ sinh undo, thời gian query và chính sách retention.

### 11.3. Kiểm tra UNDO_RETENTION

~~~sql
SHOW PARAMETER undo_retention;
SHOW PARAMETER undo_tablespace;
~~~

UNDO_RETENTION tính bằng giây. Giá trị cấu hình là mục tiêu retention; mức thực tế có thể được Oracle điều chỉnh dựa trên workload và dung lượng.

### 11.4. Theo dõi V$UNDOSTAT

~~~sql
SELECT begin_time,
       end_time,
       undoblks,
       txncount,
       maxquerylen,
       tuned_undoretention,
       ssolderrcnt,
       nospaceerrcnt
FROM v$undostat
ORDER BY begin_time DESC;
~~~

Các cột hữu ích:
- UNDOBLKS: số undo block được sử dụng trong interval.
- TXNCOUNT: số transaction trong interval.
- MAXQUERYLEN: độ dài query dài nhất được ghi nhận, theo giây.
- TUNED_UNDORETENTION: retention được điều chỉnh theo hoạt động thực tế, theo giây.
- SSOLDERRCNT: số lỗi snapshot too old trong interval.
- NOSPACEERRCNT: số lỗi liên quan không gian undo trong interval.

Xem xu hướng qua nhiều interval và so với thời gian Flashback Query cần hỗ trợ.

### 11.5. RETENTION GUARANTEE

DBA có thể cấu hình retention guarantee trên undo tablespace:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION GUARANTEE;
~~~

Tắt guarantee:

~~~sql
ALTER TABLESPACE undotbs1 RETENTION NOGUARANTEE;
~~~

RETENTION GUARANTEE ngăn Oracle ghi đè undo chưa hết retention theo chính sách. Đổi lại, nếu không còn chỗ để cấp phát undo mới, transaction DML có thể thất bại. Cần đánh giá kỹ trước khi bật, đặc biệt với workload ghi cao.

## 12. DDL và thay đổi cấu trúc object

Flashback Query tập trung vào phiên bản dữ liệu. Nếu cấu trúc object thay đổi, Oracle có thể không truy vấn được qua ranh giới DDL.

Ví dụ:
- DROP hoặc recreate table.
- TRUNCATE.
- Thay đổi cấu trúc cột.
- Một số thao tác partition hoặc move làm thay đổi metadata/segment.

Một lỗi có thể gặp là ORA-01466, báo không thể đọc dữ liệu vì định nghĩa table đã thay đổi.

### 12.1. DDL không giống DML

DML thay đổi row data và tạo undo theo transaction. DDL có thể thay đổi metadata và thường có implicit commit. Không kỳ vọng Flashback Query sẽ tái tạo mọi cấu trúc table như trước DDL chỉ nhờ undo row.

### 12.2. Nếu table bị DROP

Flashback Query không phải công cụ khôi phục object đã drop. Nếu table nằm trong recycle bin, có thể xem xét Flashback Drop theo điều kiện phù hợp. Nếu object không thể flashback từ recycle bin, cần restore/recovery từ backup hoặc phương án khác.

### 12.3. TRUNCATE

TRUNCATE là DDL, không thể xử lý như một loạt DELETE có thể truy vấn lịch sử vô thời hạn. Nếu cần phục hồi dữ liệu trước TRUNCATE, đánh giá recycle bin, backup, RMAN hoặc môi trường phụ trợ. Đừng mặc định AS OF SCN luôn truy vấn được qua TRUNCATE.

## 13. Giới hạn và các trường hợp cần kiểm tra

Flashback Query có các giới hạn theo datatype, object, DDL, quyền và phiên bản. Trước khi xây dựng một quy trình phụ thuộc vào nó, cần thử trên đúng loại object và release.

Các điểm cần lưu ý:
- Không phải mọi loại table/object đều hỗ trợ mọi dạng Flashback Query.
- Temporary table và external table có semantics riêng, không nên giả định hoạt động như heap table thông thường.
- Object phải tồn tại và có định nghĩa tương thích tại mốc được hỏi.
- Undo cần thiết phải còn sẵn.
- Một số thao tác DDL làm truy vấn qua mốc cũ không thực hiện được.
- Mốc timestamp có thể không ánh xạ được nếu mapping lịch sử không còn.
- Query lớn có thể chạy lâu và tiêu thụ tài nguyên khi dựng phiên bản cũ.
- Flashback Query không thay thế backup, archive log hoặc disaster recovery.

Nếu thiết kế quy trình audit hoặc recovery, hãy xác nhận giới hạn bằng tài liệu của đúng Oracle release và thử với schema đại diện.

## 14. Lấy mốc SCN cho ứng dụng và điều tra sự cố

Một quy trình tốt ghi SCN gần thời điểm nghiệp vụ quan trọng thay vì cố suy ra nhiều giờ sau từ timestamp log.

### 14.1. Lưu SCN trước thao tác nhạy cảm

Ví dụ:

~~~sql
SELECT current_scn
INTO :p_before_scn
FROM v$database;
~~~

Ứng dụng hoặc stored procedure có thể lưu SCN cùng request ID, batch ID và timestamp. Cần bảo đảm user có quyền đọc view hoặc dùng một service DBA-approved để ghi nhận.

### 14.2. Ghi cả SCN và timestamp

Một audit marker nên lưu:
- Request/batch ID.
- SCN.
- Timestamp có timezone.
- Database identity.
- Instance/service nếu liên quan.
- User/module/action.
- Mô tả thao tác.

SCN giúp tái lập snapshot logic; timestamp giúp liên kết với log và timeline con người.

### 14.3. Xác định SCN gần timestamp incident

Nếu chỉ có timestamp, dùng TIMESTAMP_TO_SCN:

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               :incident_time,
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS incident_scn
FROM dual;
~~~

Nếu chuyển đổi thất bại, kiểm tra mapping range, format, timezone và timestamp đầu vào. Không tự thay bằng SCN hiện tại.

### 14.4. Xác nhận mốc trước khi phục hồi

Chạy truy vấn thử trên primary key hoặc một tập hàng nhỏ. So sánh current với historical, xác nhận dữ liệu phù hợp với log nghiệp vụ rồi mới tạo staging/recovery script.

## 15. Ví dụ: điều tra UPDATE nhầm

Giả sử operator cập nhật sai salary của employee 100. Có timestamp sự cố là 10:15.

### 15.1. Chuyển timestamp sang SCN

~~~sql
SELECT TIMESTAMP_TO_SCN(
           TO_TIMESTAMP(
               '2026-11-14 10:15:00',
               'YYYY-MM-DD HH24:MI:SS'
           )
       ) AS incident_scn
FROM dual;
~~~

Giả sử kết quả là 987654321. Mốc thực tế cần được xác định theo timeline; nếu UPDATE đã xảy ra trước 10:15, cần chọn mốc trước transaction đó.

### 15.2. Đọc dữ liệu lịch sử

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees AS OF SCN 987654321
WHERE employee_id = 100;
~~~

### 15.3. Đọc dữ liệu hiện tại

~~~sql
SELECT employee_id,
       first_name,
       salary
FROM hr.employees
WHERE employee_id = 100;
~~~

Đối chiếu hai kết quả và audit trail để xác nhận đúng hàng và giá trị cần khôi phục.

### 15.4. Lưu bản lịch sử vào staging

~~~sql
INSERT INTO employee_salary_recovery (
    employee_id,
    salary_before,
    source_scn,
    captured_at
)
SELECT employee_id,
       salary,
       987654321,
       SYSTIMESTAMP
FROM hr.employees AS OF SCN 987654321
WHERE employee_id = 100;
~~~

Staging giúp người vận hành xem lại dữ liệu và kiểm tra trước khi cập nhật bảng nghiệp vụ.

## 16. Ví dụ: khôi phục có kiểm soát một số cột

Sau khi xác nhận giá trị lịch sử, có thể cập nhật có điều kiện. Ví dụ:

~~~sql
UPDATE hr.employees current_row
SET current_row.salary = (
    SELECT historical_row.salary
    FROM hr.employees AS OF SCN :p_scn historical_row
    WHERE historical_row.employee_id = current_row.employee_id
)
WHERE current_row.employee_id = :employee_id;
~~~

Trước khi COMMIT:
- Kiểm tra SQL%ROWCOUNT.
- Kiểm tra giá trị cũ và mới.
- Xác nhận không ghi đè thay đổi hợp lệ sau SCN.
- Kiểm tra trigger và audit.
- Kiểm tra transaction có ảnh hưởng bảng liên quan hay không.

Một hàng có thể đã được cập nhật hợp lệ nhiều lần sau sự cố. Phục hồi toàn bộ row về SCN cũ có thể xóa mất những thay đổi hợp lệ đó. Chỉ sửa đúng cột/hàng cần thiết theo quyết định nghiệp vụ.

Ví dụ kiểm tra trong transaction:

~~~sql
SAVEPOINT before_repair;

UPDATE hr.employees current_row
SET current_row.salary = (
    SELECT historical_row.salary
    FROM hr.employees AS OF SCN :p_scn historical_row
    WHERE historical_row.employee_id = current_row.employee_id
)
WHERE current_row.employee_id = :employee_id;

SELECT employee_id, salary
FROM hr.employees
WHERE employee_id = :employee_id;

-- COMMIT chỉ sau khi xác nhận.
-- Nếu kết quả không đúng:
ROLLBACK TO before_repair;
~~~

Không đưa lệnh COMMIT tự động vào script phục hồi nếu operator cần bước review. Ghi lại source SCN và incident ID trong change record.

## 17. Truy vấn qua schema, synonym và view

Flashback clause được đặt trên table reference trong FROM. Với schema khác, ghi rõ owner nếu cần tránh synonym trỏ tới object khác.

Ví dụ:

~~~sql
SELECT *
FROM app_owner.customer_orders AS OF SCN :p_scn o;
~~~

Khi dùng view:
- Kiểm tra view và các base table có hỗ trợ flashback trong ngữ cảnh đó.
- Đảm bảo quyền trên object và base object phù hợp.
- Với query phức tạp, có thể flashback từng base table trong FROM để kiểm soát cùng SCN.
- Không giả định synonym tự xác định được mốc lịch sử cho mọi dependency.

Nếu view dùng database link hoặc object bên ngoài, cần kiểm tra giới hạn riêng. Không coi một câu SELECT AS OF trên local table là bằng chứng mọi nguồn dữ liệu phân tán cũng có cùng snapshot.

## 18. CDB/PDB và môi trường RAC

### 18.1. PDB context

Trong multitenant, query phải chạy trong container có object cần đọc và quyền phù hợp. Cần ghi nhận:
- DBID/CDB identity.
- PDB name và CON_ID.
- SCN được lấy trong database context tương ứng.
- Timestamp và timezone.
- User và privilege.

Không ghép SCN/timestamp hoặc kết quả lịch sử từ các PDB khác nhau như thể chúng là cùng một object namespace. Xác nhận phạm vi SCN và view đang sử dụng theo phiên bản Oracle.

### 18.2. RAC

SCN là database-wide logical ordering trong một RAC database, nhưng dynamic performance view có thể hiển thị theo instance. Khi lấy thông tin chẩn đoán, ghi INST_ID và không nhầm instance identity với database identity.

Flashback Query đọc dữ liệu database tại SCN, không phải một counter riêng của từng instance. Tuy nhiên, nếu lấy timestamp, log và SCN từ nhiều node, đồng bộ clock và database identity vẫn quan trọng.

## 19. Theo dõi undo và kiểm tra khả năng truy vấn lịch sử

Trước khi triển khai quy trình truy vấn quá khứ, DBA nên kiểm tra:
- UNDO_RETENTION hiện tại.
- Kích thước undo tablespace.
- Tốc độ undo generation.
- MAXQUERYLEN.
- TUNED_UNDORETENTION.
- SSOLDERRCNT.
- NOSPACEERRCNT.
- Peak workload và transaction duration.

Ví dụ xem cấu hình:

~~~sql
SELECT tablespace_name,
       retention
FROM dba_tablespaces
WHERE contents = 'UNDO';
~~~

Xem undo file:

~~~sql
SELECT tablespace_name,
       file_name,
       bytes / 1024 / 1024 AS size_mb,
       autoextensible,
       maxbytes / 1024 / 1024 AS max_mb
FROM dba_data_files
WHERE tablespace_name = (
    SELECT value
    FROM v$parameter
    WHERE name = 'undo_tablespace'
);
~~~

Nếu ứng dụng cần truy vấn lịch sử 24 giờ nhưng undo chỉ giữ được một phần thời gian đó khi tải cao, thiết kế hiện tại không đáp ứng yêu cầu. Cần điều chỉnh capacity/retention hoặc chọn cơ chế lịch sử dài hạn như audit/history table, CDC, Flashback Data Archive hoặc backup-based recovery tùy nhu cầu.

## 20. Flashback Data Archive và lịch sử dài hạn

Flashback Query dựa trên undo thường phù hợp cho truy vấn quá khứ trong khoảng thời gian undo còn sẵn. Nếu yêu cầu nghiệp vụ cần lưu lịch sử hàng tháng hoặc hàng năm, hãy xem xét Flashback Data Archive (Total Recall) hoặc mô hình temporal/audit riêng.

Flashback Data Archive lưu lịch sử thay đổi của các bảng được cấu hình theo chính sách và retention. Nó khác với việc chỉ tăng UNDO_RETENTION.

Trước khi dùng, cần:
- Xác nhận phiên bản và license/feature entitlement.
- Xác định bảng được hỗ trợ.
- Thiết kế retention và storage.
- Xem tác động DML và quản trị.
- Xác định ai có quyền truy vấn lịch sử.
- Kiểm tra yêu cầu compliance và purge.

Không coi Flashback Data Archive là mặc định đã bật cho mọi bảng. Cần cấu hình và vận hành riêng.

## 21. Hiệu năng và chi phí truy vấn quá khứ

Flashback Query có thể cần đọc undo và tái tạo phiên bản cũ. Chi phí phụ thuộc:
- Độ tuổi của SCN.
- Số lượng hàng cần đọc.
- Số lượng thay đổi từ mốc lịch sử tới hiện tại.
- Undo block cần truy cập.
- Join, sort, aggregation và parallelism.
- Storage latency và buffer cache.
- Workload đồng thời.

### 21.1. Giới hạn phạm vi

Dùng WHERE theo primary key hoặc partition key nếu có thể. Tránh quét toàn bảng lịch sử khi chỉ cần vài hàng.

~~~sql
SELECT employee_id,
       salary
FROM hr.employees AS OF SCN :p_scn
WHERE employee_id BETWEEN :low_id AND :high_id;
~~~

### 21.2. Không chạy query lịch sử lớn trong lúc database đang chịu sự cố

Nếu database đang thiếu undo hoặc storage, một truy vấn Flashback Query lớn có thể làm tăng tải. Trước tiên xác định tập hàng cần thiết và chọn thời điểm truy vấn phù hợp.

### 21.3. Kiểm tra execution plan

Có thể dùng EXPLAIN PLAN hoặc DBMS_XPLAN theo quyền và quy trình môi trường. Flashback clause không làm cho mọi query tự động rẻ hơn. Join order, index, predicate và số lượng hàng vẫn quan trọng.

### 21.4. Chỉ lấy các cột cần thiết

Không SELECT * khi chỉ cần hai cột để phục hồi. Điều này giảm dữ liệu đọc, truyền và lưu vào staging.

## 22. Bảo mật và audit

Truy vấn lịch sử có thể tiết lộ dữ liệu đã bị xóa hoặc sửa, bao gồm thông tin cá nhân và dữ liệu nhạy cảm.

Kiểm soát:
- Cấp FLASHBACK privilege ở phạm vi tối thiểu.
- Cấp SELECT trên object cần thiết.
- Audit việc truy vấn dữ liệu nhạy cảm theo chính sách.
- Giới hạn staging/recovery table.
- Mã hóa và bảo vệ export.
- Không ghi dữ liệu nhạy cảm vào DBMS_OUTPUT hoặc log không được bảo vệ.
- Ghi SCN, request ID, người thực hiện và lý do phục hồi.

Không cấp FLASHBACK ANY TABLE rộng cho tài khoản ứng dụng chỉ để hỗ trợ một báo cáo nếu quyền object-level đủ dùng.

## 23. Lỗi thường gặp

| Lỗi/tình huống | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| ORA-01555 | Undo cần thiết không còn | Kiểm tra undo retention, size, generation và query duration |
| ORA-08180 | Không tìm thấy snapshot phù hợp cho timestamp | Kiểm tra timestamp, mapping và lịch sử còn sẵn |
| ORA-08181 | SCN không hợp lệ hoặc không có mapping phù hợp trong ngữ cảnh hàm | Xác nhận SCN/database và mapping range |
| ORA-01466 | Định nghĩa table thay đổi qua mốc lịch sử | Xác định DDL/segment change; dùng backup hoặc phương án khác |
| ORA-01031 | Thiếu quyền | Kiểm tra SELECT/FLASHBACK privilege |
| ORA-00942 | Object không tồn tại hoặc không có quyền nhìn thấy | Xác nhận owner, object và grant |
| Không thấy hàng lịch sử | Hàng chưa tồn tại tại SCN hoặc đã bị xóa trước SCN | Kiểm tra mốc và Versions Query |
| Timestamp trả giá trị không mong muốn | Sai format, timezone hoặc NLS | Dùng TO_TIMESTAMP với format rõ ràng |
| Một bảng đúng, bảng join sai thời điểm | Chỉ một table reference có AS OF | Áp cùng SCN cho mọi bảng cần snapshot chung |
| Query lịch sử chạy chậm | Phạm vi lớn, undo I/O, join/sort nặng | Thu hẹp predicate và kiểm tra plan |
| AS OF không đọc được object | Object type/DDL không được hỗ trợ | Kiểm tra giới hạn phiên bản và object |
| Hàng phục hồi ghi đè thay đổi hợp lệ | DML phục hồi toàn row không kiểm tra | Staging, đối chiếu và cập nhật có điều kiện |

Mã lỗi có thể phụ thuộc phiên bản và ngữ cảnh. Đọc toàn bộ error stack, alert log và trace khi cần; không chỉ dựa vào mã lỗi đầu tiên.

## 24. Runbook điều tra dữ liệu bị thay đổi nhầm

1. Xác định table, primary key và cột bị ảnh hưởng.
2. Ghi thời điểm sự cố từ application log, audit hoặc incident timeline.
3. Xác định database/PDB/service và timezone.
4. Lấy SCN gần mốc cần điều tra hoặc chuyển timestamp sang SCN.
5. Kiểm tra quyền SELECT/FLASHBACK.
6. Chạy AS OF SCN trên một hàng thử.
7. So sánh current và historical values.
8. Nếu cần xem chuỗi thay đổi, dùng VERSIONS BETWEEN.
9. Kiểm tra undo availability và DDL trong khoảng.
10. Lưu dữ liệu lịch sử vào staging an toàn.
11. Xác nhận với owner dữ liệu và đánh giá thay đổi hợp lệ sau SCN.
12. Viết DML có điều kiện và kiểm tra row count.
13. Chạy trong transaction có savepoint.
14. Review kết quả trước COMMIT.
15. Ghi lại SCN, người thao tác, script và kết quả.
16. Kiểm tra ứng dụng sau khi phục hồi.

Nếu undo không còn, dừng việc thử các mốc cũ liên tục. Chuyển sang phương án backup/restore auxiliary database, Flashback Data Archive hoặc audit source phù hợp.

## 25. Ví dụ tổng hợp: truy vấn đơn hàng tại một SCN

Giả sử có các bảng ORDERS và ORDER_ITEMS. Trước một batch thay đổi trạng thái, DBA ghi lại SCN:

~~~sql
SELECT current_scn
FROM v$database;
~~~

Sau batch, muốn biết đơn hàng 5001 ở trạng thái nào trước batch:

~~~sql
SELECT order_id,
       status,
       customer_id,
       total_amount
FROM sales.orders AS OF SCN :batch_start_scn
WHERE order_id = 5001;
~~~

Xem chi tiết tại cùng mốc:

~~~sql
SELECT i.order_id,
       i.line_no,
       i.product_id,
       i.quantity,
       i.unit_price
FROM sales.order_items AS OF SCN :batch_start_scn i
WHERE i.order_id = 5001
ORDER BY i.line_no;
~~~

Nếu cần một kết quả join duy nhất:

~~~sql
SELECT o.order_id,
       o.status,
       o.total_amount,
       i.line_no,
       i.product_id,
       i.quantity
FROM sales.orders AS OF SCN :batch_start_scn o
JOIN sales.order_items AS OF SCN :batch_start_scn i
  ON i.order_id = o.order_id
WHERE o.order_id = 5001
ORDER BY i.line_no;
~~~

Cùng một SCN bảo đảm cả header và detail được đọc tại cùng một snapshot logic, nếu undo và object metadata còn hỗ trợ mốc đó.

## 26. Những nhầm lẫn thường gặp

**AS OF SCN là một cách rollback transaction.** Không đúng. Nó chỉ đọc phiên bản dữ liệu cũ.

**AS OF TIMESTAMP chính xác tuyệt đối tới microsecond.** Không đúng. Oracle ánh xạ timestamp sang SCN theo mapping có độ phân giải hữu hạn.

**SCN là thời gian dạng số.** Không đúng. SCN là số thứ tự thay đổi logic, không phải epoch timestamp.

**UNDO_RETENTION bảo đảm mọi query lịch sử chạy được.** Không đúng trong cấu hình mặc định nếu undo bị áp lực và có thể tái sử dụng. Cần đánh giá dung lượng và retention guarantee.

**Flashback Query cần bật Flashback Database.** Không đúng. Flashback Query dùng undo; Flashback Database dùng flashback logs.

**AS OF SCN tự phục hồi dữ liệu.** Không đúng. Cần DML riêng nếu muốn sửa dữ liệu hiện tại.

**Chỉ đặt AS OF cho bảng chính là đủ.** Không đúng nếu cần snapshot nhất quán trên nhiều bảng. Áp cùng SCN cho từng table reference liên quan.

**Flashback Query thay thế backup.** Không đúng. Undo có thời hạn và không thay thế backup/archived redo.

**VERSIONS BETWEEN là lịch sử audit vô hạn.** Không đúng. Phiên bản phụ thuộc dữ liệu undo còn sẵn và giới hạn object.

**Có thể truy vấn qua mọi DDL.** Không đúng. DDL thay đổi cấu trúc có thể làm Flashback Query thất bại, ví dụ ORA-01466.

**Hàng bị DELETE không thể đọc lại.** Có thể đọc phiên bản trước DELETE nếu undo còn sẵn và object hỗ trợ.

**Có thể phục hồi toàn row cũ mà không ảnh hưởng thay đổi mới.** Không đúng. Phải đối chiếu các thay đổi hợp lệ sau SCN và chỉ sửa phần cần thiết.

**TIMESTAMP_TO_SCN luôn chuyển đổi mọi timestamp.** Không đúng. Mapping có phạm vi hữu hạn; timestamp quá cũ hoặc không hợp lệ có thể thất bại.

**SCN giữa hai database có thể so sánh trực tiếp.** Không nên. SCN có ý nghĩa trong lịch sử của database tương ứng.

## 27. Bài tập tự luyện

1. Giải thích Flashback Query dùng để làm gì.
2. Phân biệt SCN và TIMESTAMP.
3. Viết SELECT AS OF SCN cho một hàng theo primary key.
4. Viết SELECT AS OF TIMESTAMP với TO_TIMESTAMP và format model.
5. Vì sao không nên dựa vào NLS_TIMESTAMP_FORMAT?
6. Lấy CURRENT_SCN từ V$DATABASE.
7. Giải thích khi nào nên lưu SCN trước một thao tác nghiệp vụ.
8. Dùng TIMESTAMP_TO_SCN để chuyển thời gian incident thành SCN.
9. Dùng SCN_TO_TIMESTAMP để xem thời điểm gần tương ứng.
10. Giải thích vì sao SCN_TO_TIMESTAMP không phải đồng hồ chính xác tuyệt đối.
11. Nêu điều kiện undo cần thiết cho Flashback Query.
12. Phân biệt UNDO_RETENTION với RETENTION GUARANTEE.
13. Nêu rủi ro khi bật RETENTION GUARANTEE.
14. Viết câu GRANT SELECT và FLASHBACK cho một bảng.
15. Vì sao không nên cấp FLASHBACK ANY TABLE cho mọi user?
16. Viết query join ORDERS và ORDER_ITEMS tại cùng SCN.
17. Giải thích rủi ro khi một bảng dùng AS OF còn bảng kia dùng dữ liệu hiện tại.
18. Truy vấn một hàng đã bị UPDATE nhầm tại SCN trước thay đổi.
19. Truy vấn một hàng đã bị DELETE tại SCN trước DELETE.
20. Giải thích vì sao AS OF không tự rollback transaction.
21. Viết VERSIONS BETWEEN SCN để xem lịch sử một hàng.
22. Giải thích VERSIONS_OPERATION và VERSIONS_XID.
23. Phân biệt Flashback Query, Flashback Table và Flashback Database.
24. ORA-01555 có thể ảnh hưởng Flashback Query như thế nào?
25. ORA-01466 thường liên quan tới loại thay đổi nào?
26. Vì sao Flashback Query có thể thất bại sau TRUNCATE hoặc DDL?
27. Thiết kế quy trình staging trước khi phục hồi một hàng.
28. Tính năng nào phù hợp nếu cần lịch sử dữ liệu nhiều tháng?
29. Thiết kế audit marker ghi request ID, SCN, timestamp và module.
30. Xây dựng runbook điều tra UPDATE/DELETE nhầm, từ lấy mốc SCN tới DML phục hồi có kiểm soát.

**AS OF SCN và AS OF TIMESTAMP cho phép đọc trạng thái dữ liệu tại một điểm trong quá khứ; SCN xác định mốc logic, timestamp giúp định vị theo thời gian.** Flashback Query dựa trên undo còn sẵn, cần quyền phù hợp và có giới hạn khi object thay đổi cấu trúc. Dùng cùng SCN cho mọi bảng trong một snapshot, xác nhận dữ liệu lịch sử trước khi phục hồi và luôn thực hiện DML sửa dữ liệu theo quy trình có kiểm soát.

