# Thiết kế giao dịch ngắn, kiểm soát lỗi và quy tắc retry trong Oracle Database

Một giao dịch database cần giữ các thay đổi liên quan trong cùng một đơn vị nhất quán, nhưng cũng cần kết thúc nhanh để không giữ khóa quá lâu, chiếm tài nguyên và cản trở các session khác. Khi có lỗi, ứng dụng phải biết lỗi nào có thể thử lại, lỗi nào cần trả về cho người dùng, và làm thế nào để không thực hiện một nghiệp vụ hai lần nếu kết quả của lần chạy trước chưa rõ.

Thiết kế transaction tốt cần cân bằng bốn mục tiêu:

1. **Tính nguyên tử:** các thay đổi thuộc cùng một nghiệp vụ phải cùng thành công hoặc cùng bị hủy.
2. **Thời gian ngắn:** chỉ giữ transaction và khóa trong khoảng cần thiết.
3. **Xử lý lỗi rõ ràng:** rollback đúng phạm vi, giữ nguyên nguyên nhân lỗi và không che giấu lỗi.
4. **Retry an toàn:** chỉ thử lại khi có cơ sở, có giới hạn và thao tác có thể lặp lại mà không tạo tác dụng phụ trùng.

Trong Oracle, các vấn đề này gắn với transaction isolation, row locks, SAVEPOINT, SQL%ROWCOUNT, exception handling trong PL/SQL, unique constraints, idempotency key và các lỗi như ORA-00060 hoặc ORA-08177. Bài học trình bày cách thiết kế từ một thao tác DML đơn giản đến luồng giao dịch trong ứng dụng và worker xử lý hàng đợi.

## 1. Transaction là ranh giới của một nghiệp vụ

Transaction gom các thay đổi dữ liệu có quan hệ nghiệp vụ thành một đơn vị. Ví dụ chuyển tiền giữa hai tài khoản cần:

- Trừ tiền ở tài khoản nguồn.
- Cộng tiền ở tài khoản đích.
- Có thể ghi một bản ghi lịch sử giao dịch.

Nếu chỉ trừ tiền thành công nhưng cộng tiền thất bại, dữ liệu không còn đúng. Ba thao tác cần nằm trong cùng một transaction:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

INSERT INTO transfer_log (
    from_account_id,
    to_account_id,
    amount,
    created_at
)
VALUES (
    10,
    20,
    100,
    SYSTIMESTAMP
);

COMMIT;
~~~

Nếu một bước thất bại trước COMMIT, ứng dụng có thể ROLLBACK để hủy các thay đổi của transaction. COMMIT xác nhận toàn bộ thay đổi; ROLLBACK hủy các thay đổi chưa commit.

### 1.1 Transaction không đồng nghĩa với một câu SQL

Một transaction có thể gồm một hoặc nhiều câu SQL. Một câu UPDATE đơn lẻ cũng được thực thi trong transaction. Một quy trình nghiệp vụ nhiều bước có thể cần nhiều câu DML trước khi commit.

Oracle cung cấp tính nguyên tử ở cấp câu lệnh: nếu một câu SQL lỗi trong khi thực thi, các thay đổi của chính câu lệnh đó được rollback. Điều này **không có nghĩa toàn bộ transaction trước đó tự động rollback**.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

-- Câu lệnh này lỗi vì account_id không tồn tại hoặc điều kiện/ràng buộc không hợp lệ:
UPDATE accounts
SET balance = balance + 100
WHERE account_id = -999;
~~~

Lỗi của UPDATE thứ hai không tự hủy UPDATE thứ nhất. Nếu nghiệp vụ cần cả hai thao tác cùng thành công, caller phải ROLLBACK transaction khi phát hiện lỗi.

### 1.2 Oracle mặc định dùng READ COMMITTED

Isolation level mặc định của Oracle là READ COMMITTED. Mỗi câu truy vấn nhìn thấy dữ liệu đã commit trước thời điểm câu truy vấn bắt đầu, cùng với thay đổi của chính transaction hiện tại. Một câu SELECT tiếp theo có thể nhìn thấy dữ liệu mới được session khác commit sau câu SELECT trước.

Điều này có nghĩa hai câu SELECT trong cùng transaction READ COMMITTED không nhất thiết nhìn cùng một snapshot. Nếu nghiệp vụ cần bảo vệ một dòng đang chuẩn bị cập nhật, có thể dùng SELECT FOR UPDATE hoặc optimistic concurrency bằng version column/điều kiện cập nhật.

Không nên nhầm READ COMMITTED với việc transaction tự commit sau mỗi câu lệnh. DML vẫn chưa commit cho đến khi ứng dụng hoặc session thực hiện COMMIT, trừ khi client/driver đang bật autocommit.

## 2. Vì sao cần giữ transaction ngắn?

Transaction dài làm tăng thời gian giữ row lock, tăng lượng undo cần duy trì, kéo dài thời gian chờ của session khác và làm khó phục hồi khi lỗi. Một transaction dài cũng dễ bị gián đoạn bởi timeout, mất kết nối hoặc thao tác người dùng.

### 2.1 Những việc không nên làm khi đang giữ transaction

Tránh giữ transaction mở trong khi:

- Chờ người dùng xác nhận trên màn hình.
- Gọi HTTP API, dịch vụ thanh toán, email hoặc message broker.
- Upload/download file hoặc xử lý file lớn.
- Chạy một phép tính CPU kéo dài không cần đọc/ghi database.
- Chờ một tác vụ bên ngoài hoặc sleep để retry.
- Chờ người vận hành kiểm tra kết quả.

Ví dụ luồng không tốt:

~~~text
BEGIN TRANSACTION
    UPDATE dữ liệu và giữ row lock
    Gọi API bên ngoài, chờ 15 giây
    Chờ người dùng xác nhận
    Ghi log
COMMIT
~~~

Trong suốt thời gian chờ, khóa có thể vẫn được giữ. Các session cần cập nhật cùng dòng có thể bị chặn.

### 2.2 Tổ chức luồng tốt hơn

~~~text
Kiểm tra đầu vào và chuẩn bị dữ liệu
              |
              v
Bắt đầu transaction ngắn
              |
              v
Đọc/khóa dữ liệu cần thiết
              |
              v
Kiểm tra bất biến và thực hiện DML
              |
              v
Ghi các bản ghi liên quan
              |
              v
COMMIT
              |
              v
Thực hiện side effect bên ngoài qua cơ chế phù hợp
~~~

Chỉ đưa các thao tác cần nguyên tử với nhau vào transaction. Những công việc độc lập và chậm nên được chuẩn bị trước hoặc thực hiện sau commit bằng một cơ chế có thể retry.

### 2.3 Ngắn không có nghĩa là chia nhỏ tùy tiện

Không chia một nghiệp vụ thành nhiều transaction chỉ để mỗi transaction ngắn hơn nếu điều đó phá vỡ tính nguyên tử. Ví dụ chuyển tiền không thể commit bước trừ tiền rồi mới bắt đầu transaction khác để cộng tiền, trừ khi có mô hình nghiệp vụ bù trừ và trạng thái trung gian được thiết kế rõ.

Với import hàng triệu dòng, có thể commit theo batch nếu từng batch là một đơn vị độc lập và có checkpoint. Khi đó hệ thống chấp nhận trạng thái hoàn thành một phần và phải có khả năng tiếp tục an toàn. Đây là quyết định nghiệp vụ/kiến trúc, không phải một tối ưu kỹ thuật vô hại.

## 3. Giảm thời gian giữ khóa

### 3.1 Chỉ khóa khi thực sự cần

SELECT thông thường không khóa các dòng theo cách SELECT FOR UPDATE khóa chúng. Nếu cần đọc rồi cập nhật một dòng và phải ngăn session khác thay đổi dòng giữa hai bước, có thể khóa:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE;
~~~

Sau khi lấy khóa, session có thể kiểm tra số dư và cập nhật trong cùng transaction. Khóa được giữ đến COMMIT hoặc ROLLBACK.

### 3.2 NOWAIT và WAIT

Nếu không muốn chờ khóa vô thời hạn, có thể chọn chính sách chờ:

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE NOWAIT;
~~~

NOWAIT yêu cầu báo lỗi ngay nếu dòng đang bị session khác khóa. Ứng dụng có thể trả thông báo bận hoặc áp dụng retry có giới hạn theo nghiệp vụ.

~~~sql
SELECT balance
FROM accounts
WHERE account_id = :p_account_id
FOR UPDATE WAIT 5;
~~~

WAIT 5 cho phép chờ tối đa số giây được chỉ định trước khi báo lỗi khóa. Thời gian chờ cần phù hợp với SLA và timeout tổng của request.

### 3.3 SKIP LOCKED cho hàng đợi

~~~sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
FOR UPDATE SKIP LOCKED;
~~~

SKIP LOCKED bỏ qua những dòng đang bị session khác khóa, hữu ích khi nhiều worker cùng lấy công việc từ một queue. Nó không phù hợp cho truy vấn người dùng cần thấy toàn bộ dữ liệu vì các dòng bị khóa sẽ bị bỏ qua âm thầm.

Với queue, nên khóa và nhận quyền xử lý trong một transaction ngắn, cập nhật trạng thái/lease rồi commit. Công việc nặng thực hiện sau khi đã nhả khóa.

### 3.4 Cập nhật theo điều kiện thay vì đọc rồi mới kiểm tra

Nếu cần trừ số lượng tồn kho nhưng không được âm, một câu UPDATE có điều kiện thường an toàn hơn SELECT trước rồi UPDATE sau:

~~~sql
UPDATE inventory
SET available_qty = available_qty - :p_quantity
WHERE product_id = :p_product_id
  AND available_qty >= :p_quantity;
~~~

Sau đó kiểm tra:

~~~sql
IF SQL%ROWCOUNT = 0 THEN
    RAISE_APPLICATION_ERROR(
        -20001,
        'Không đủ tồn kho hoặc sản phẩm không tồn tại'
    );
END IF;
~~~

Điều kiện được đánh giá cùng thao tác cập nhật dưới cơ chế khóa của Oracle. Hai session cùng đặt hàng không thể cùng trừ một số lượng vượt quá tồn kho chỉ vì cả hai đã đọc một giá trị cũ trước đó.

Nếu cần phân biệt “sản phẩm không tồn tại” với “không đủ hàng”, có thể truy vấn thêm theo khóa hoặc trả mã kết quả nghiệp vụ riêng. Không bỏ kiểm tra SQL%ROWCOUNT.

## 4. Optimistic concurrency với version column

Không phải luồng nào cũng cần SELECT FOR UPDATE. Khi xung đột không thường xuyên và có thể phát hiện dữ liệu đã đổi, optimistic concurrency là một lựa chọn.

### 4.1 Thêm cột phiên bản

~~~sql
ALTER TABLE account_profile
ADD (version_no NUMBER DEFAULT 0 NOT NULL);
~~~

Ứng dụng đọc VERSION_NO cùng dữ liệu. Khi cập nhật, gửi lại phiên bản đã đọc:

~~~sql
UPDATE account_profile
SET display_name = :p_display_name,
    version_no = version_no + 1
WHERE account_id = :p_account_id
  AND version_no = :p_expected_version;
~~~

Kiểm tra SQL%ROWCOUNT:

- 1: cập nhật thành công; phiên bản hiện tại khớp phiên bản ứng dụng đã đọc.
- 0: dòng không tồn tại hoặc đã bị session khác cập nhật trước; đây là conflict cần xử lý.

### 4.2 Không tự động ghi đè conflict

Nếu UPDATE trả 0 dòng, ứng dụng nên đọc lại dữ liệu mới nhất và quyết định:

- Báo người dùng rằng dữ liệu đã thay đổi.
- Hợp nhất thay đổi nếu quy tắc nghiệp vụ cho phép.
- Tính lại thao tác trên dữ liệu mới rồi thử lại có giới hạn.

Không tự động lặp UPDATE với cùng VERSION_NO vì nó sẽ tiếp tục không khớp. Cũng không bỏ điều kiện version để ép ghi đè nếu chưa có chính sách rõ.

### 4.3 Phân biệt conflict nghiệp vụ và lỗi tạm thời

Optimistic conflict không nhất thiết là lỗi database tạm thời. Nó có thể là một thay đổi hợp lệ do người dùng khác thực hiện. UI thường cần tải dữ liệu mới và yêu cầu người dùng xác nhận/hợp nhất thay vì tự retry mù.

## 5. Giữ thứ tự khóa nhất quán để giảm deadlock

Deadlock xảy ra khi hai transaction chờ tài nguyên mà transaction kia đang giữ theo một chu trình.

Ví dụ:

~~~text
Session A                       Session B
---------                       ---------
Khóa account 10                 Khóa account 20
Chờ account 20                  Chờ account 10
        \                       /
         \------ deadlock -----/
~~~

Oracle phát hiện deadlock và báo ORA-00060 cho một câu lệnh. Để giảm khả năng xảy ra:

- Khi cần khóa nhiều dòng, mọi luồng nên lấy khóa theo cùng một thứ tự ổn định, ví dụ tăng dần ACCOUNT_ID.
- Giữ transaction ngắn và tránh chờ dịch vụ bên ngoài trong lúc đang giữ khóa.
- Không khóa nhiều dòng hơn mức cần thiết.
- Thiết kế index phù hợp để giảm thời gian tìm dòng.
- Xem lại luồng nghiệp vụ có thể cập nhật hai tập dòng theo thứ tự ngược nhau không.

Thứ tự khóa nhất quán làm giảm deadlock nhưng không loại bỏ mọi nguyên nhân deadlock. Trigger, foreign key, index và các bảng liên quan cũng có thể tạo đường khóa bổ sung.

## 6. Kiểm soát lỗi trong PL/SQL

### 6.1 Exception không tự rollback toàn bộ transaction

Nếu một câu DML lỗi, Oracle rollback tác động của câu lệnh đó. Các DML trước đó trong transaction vẫn còn cho đến khi caller COMMIT hoặc ROLLBACK.

Ví dụ:

~~~sql
BEGIN
    UPDATE accounts
    SET balance = balance - 100
    WHERE account_id = 10;

    UPDATE accounts
    SET balance = balance + 100
    WHERE account_id = -999;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

RAISE chuyển lỗi lên caller. Nó không tự động rollback UPDATE đầu tiên. Caller phải quyết định rollback transaction nếu nghiệp vụ yêu cầu hai thao tác cùng thành công.

### 6.2 Khi nào dùng RAISE_APPLICATION_ERROR?

Để trả lỗi nghiệp vụ có mã riêng trong khoảng -20000 đến -20999:

~~~sql
IF p_amount <= 0 THEN
    RAISE_APPLICATION_ERROR(
        -20010,
        'Số tiền chuyển phải lớn hơn 0'
    );
END IF;
~~~

Mã lỗi riêng giúp ứng dụng phân biệt validation nghiệp vụ với lỗi Oracle. Không dùng mã tùy ý trùng với lỗi hệ thống hoặc biến mọi lỗi thành một mã chung khiến mất nguyên nhân gốc.

### 6.3 WHEN OTHERS không nên nuốt lỗi

Không nên viết:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Cách này làm ứng dụng tưởng thao tác thành công trong khi dữ liệu có thể chỉ được cập nhật một phần hoặc không đúng mong đợi.

Mẫu tối thiểu nếu chỉ cần chuyển lỗi lên:

~~~sql
EXCEPTION
    WHEN OTHERS THEN
        RAISE;
~~~

Nếu cần ghi log, hãy ghi thông tin có ích như SQLCODE, SQLERRM, mã request và bước nghiệp vụ; sau đó RAISE lại. Lưu ý log trong cùng transaction có thể bị rollback cùng transaction. Cơ chế log độc lập cần được thiết kế riêng, không tự ý commit thay đổi nghiệp vụ.

### 6.4 Procedure dùng chung không nên tự ý COMMIT

Một stored procedure có thể được gọi từ nhiều luồng khác nhau. Nếu procedure tự COMMIT, nó có thể commit cả những thay đổi khác mà caller đã thực hiện trong cùng session transaction.

Quy ước thường dễ kiểm soát:

- Procedure thực hiện các DML cần thiết.
- Procedure trả kết quả hoặc raise lỗi.
- Caller sở hữu transaction boundary và quyết định COMMIT/ROLLBACK.

Nếu một API database được thiết kế rõ là tự sở hữu transaction, hãy tài liệu hóa hợp đồng đó. Không trộn lẫn hai mô hình trong cùng hệ thống.

## 7. SAVEPOINT và rollback một phần

SAVEPOINT đánh dấu một vị trí trong transaction hiện tại:

~~~sql
SAVEPOINT before_optional_step;

UPDATE customer_profile
SET note = 'processed'
WHERE customer_id = 10;

-- Nếu bước tùy chọn thất bại:
ROLLBACK TO before_optional_step;
~~~

ROLLBACK TO SAVEPOINT hủy thay đổi kể từ savepoint nhưng không kết thúc transaction. Các thay đổi trước savepoint vẫn còn.

### 7.1 SAVEPOINT không phải nested transaction

SAVEPOINT không tạo transaction con độc lập và không có COMMIT riêng. COMMIT transaction sẽ commit tất cả thay đổi còn lại, kể cả phần trước và sau savepoint chưa bị rollback.

### 7.2 Dùng savepoint cho phần việc có thể bỏ qua

Ví dụ một transaction cập nhật đơn hàng, sau đó thử ghi dữ liệu tùy chọn:

~~~sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :p_order_id;

SAVEPOINT before_optional_audit;

BEGIN
    INSERT INTO optional_order_note (order_id, note_text)
    VALUES (:p_order_id, :p_note);
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK TO before_optional_audit;
        -- Chỉ bỏ qua nếu chính sách cho phép bước này là tùy chọn.
END;

-- Caller vẫn phải quyết định COMMIT/ROLLBACK transaction.
~~~

Chỉ dùng kiểu xử lý này khi ghi note thật sự không phải điều kiện bắt buộc để xác nhận đơn. Nếu audit là yêu cầu pháp lý hoặc nghiệp vụ bắt buộc, không được nuốt lỗi rồi tiếp tục.

### 7.3 Savepoint trong procedure dùng chung

Tên savepoint thuộc transaction hiện tại, không có phạm vi lexical riêng cho từng procedure. Một procedure tạo savepoint trùng tên với savepoint caller có thể thay thế mốc đó. Nếu dùng savepoint nội bộ, cần tên có quy ước riêng và tài liệu hóa hành vi; nhiều hệ thống đơn giản hơn khi để caller quản lý rollback.

### 7.4 DDL làm mất savepoint

Oracle DDL có implicit commit. Savepoint được tạo trước DDL không còn hiệu lực sau ranh giới commit. Không dùng SAVEPOINT để kỳ vọng rollback một phần qua CREATE, ALTER, DROP hoặc TRUNCATE.

## 8. Phân loại lỗi: retry được hay không?

Không phải mọi lỗi đều nên retry. Retry chỉ hữu ích khi nguyên nhân có khả năng tạm thời biến mất và thao tác có thể lặp lại an toàn.

| Tình huống | Ví dụ Oracle | Cách xử lý thường phù hợp |
|---|---|---|
| Deadlock | ORA-00060 | Rollback đơn vị nghiệp vụ, xem lại thứ tự khóa; có thể retry có giới hạn |
| Không thể serialize transaction | ORA-08177 | Rollback và retry toàn bộ transaction nếu nghiệp vụ cho phép |
| Dòng đang bị khóa, dùng NOWAIT | ORA-00054 | Trả trạng thái bận hoặc retry có giới hạn theo SLA |
| Trùng khóa/unique | ORA-00001 | Kiểm tra đó là request lặp hay xung đột dữ liệu; không retry mù |
| Không tìm thấy parent cho FK | ORA-02291 | Sửa thứ tự/đầu vào hoặc trả lỗi nghiệp vụ; thường không retry |
| Vi phạm FK do còn child | ORA-02292 | Xử lý quan hệ dữ liệu; không retry mù |
| Không được phép NULL | ORA-01400 | Sửa dữ liệu đầu vào hoặc quy tắc; không retry |
| Giá trị quá dài | ORA-12899 | Sửa dữ liệu hoặc schema; không retry |
| Chuyển kiểu không hợp lệ | ORA-01722 | Sửa dữ liệu/câu SQL; không retry |
| Người dùng hủy câu lệnh | ORA-01013 | Tôn trọng yêu cầu hủy; không tự chạy lại |
| Snapshot quá cũ | ORA-01555 | Xem lại thời gian truy vấn, undo và workload; không coi là lỗi có thể retry mù |
| Mất kết nối khi COMMIT | Lỗi mạng/connection | Kết quả commit có thể chưa rõ; tra cứu bằng idempotency key trước khi quyết định |

Mã lỗi chỉ là một phần thông tin. Cần xét vị trí phát sinh, transaction isolation, trạng thái connection, tính idempotent và quy tắc nghiệp vụ.

### 8.1 ORA-00060: deadlock detected

Oracle phát hiện chu trình chờ và hủy một câu lệnh để phá deadlock. Các DML trước đó trong transaction có thể vẫn còn. Nếu nghiệp vụ gồm nhiều bước phụ thuộc nhau, ứng dụng nên ROLLBACK toàn bộ transaction rồi mới quyết định retry từ đầu.

Nếu cứ retry cùng một câu lệnh trong transaction còn các thay đổi trước đó, có thể tạo trạng thái nghiệp vụ khó hiểu. Cần tìm nguyên nhân deadlock và chuẩn hóa thứ tự khóa, không chỉ tăng số lần retry.

### 8.2 ORA-08177: can't serialize access

Lỗi này có thể xuất hiện khi transaction dùng SERIALIZABLE và không thể duy trì tính tuần tự theo snapshot đã chọn. Thường cần rollback transaction và chạy lại toàn bộ đơn vị nghiệp vụ để có snapshot mới.

Không chỉ retry câu UPDATE bị lỗi nếu logic trước đó đã đọc dữ liệu và đưa ra quyết định dựa trên snapshot cũ.

### 8.3 ORA-00054: resource busy

Lỗi này thường liên quan đến thao tác yêu cầu khóa nhưng được cấu hình NOWAIT hoặc timeout. Nếu tài nguyên chỉ bận tạm thời, có thể trả trạng thái bận hoặc retry có giới hạn sau khi rollback và nhả các khóa của transaction hiện tại.

Không chờ vô hạn. Một request có deadline phải có tổng thời gian chờ hữu hạn.

### 8.4 ORA-00001: unique constraint violated

Đây thường là lỗi dữ liệu hoặc dấu hiệu request đã được xử lý, không phải deadlock tạm thời. Nếu bảng có UNIQUE constraint trên idempotency key, duplicate có thể cho biết một lần gọi trước đã tạo kết quả.

Ứng dụng cần truy vấn bản ghi theo key, kiểm tra payload/hash và trả lại kết quả đã lưu nếu đó là cùng một yêu cầu. Nếu cùng key nhưng nội dung khác, trả conflict thay vì coi là thành công.

## 9. Quy tắc retry an toàn

### 9.1 Retry toàn bộ đơn vị nghiệp vụ

Với lỗi concurrency như ORA-08177 hoặc deadlock, thông thường cần:

1. Dừng xử lý đơn vị nghiệp vụ hiện tại.
2. ROLLBACK transaction để bỏ các thay đổi còn lại.
3. Giải phóng connection/khóa theo cách phù hợp.
4. Chờ một khoảng ngắn có giới hạn.
5. Bắt đầu transaction mới và đọc lại dữ liệu mới nhất.
6. Thực hiện lại toàn bộ logic, không tái sử dụng quyết định dựa trên snapshot cũ.

Retry một statement riêng lẻ có thể sai nếu các bước trước đó ảnh hưởng đến điều kiện nghiệp vụ.

### 9.2 Bounded retry

Luôn giới hạn:

- Số lần thử, ví dụ tối đa 3 lần sau lần đầu.
- Tổng thời gian retry theo deadline của request.
- Khoảng chờ tối đa giữa các lần.
- Loại lỗi được phép retry.

Không lặp vô hạn. Nếu một xung đột xảy ra liên tục, cần trả lỗi hoặc đưa vào hàng chờ xử lý thay vì giữ request và tài nguyên mãi.

### 9.3 Exponential backoff và jitter

Exponential backoff tăng khoảng chờ theo từng lần retry. Jitter thêm độ ngẫu nhiên để nhiều client không cùng thức dậy và tranh khóa tại một thời điểm.

Một công thức minh họa:

\[
\text{delay}_k =
\min(\text{cap}, \text{base}\times 2^{k-1})
\times U(0.5, 1.5)
\]

Trong đó U là hệ số ngẫu nhiên trong khoảng 0.5 đến 1.5. Ví dụ base 100 ms, cap 2 giây và tối đa 4 lần thử. Giá trị thực tế cần dựa trên latency mục tiêu, mức tải và SLA.

Quan trọng: rollback và nhả khóa trước khi sleep. Không giữ transaction mở trong thời gian backoff.

### 9.4 Không retry lỗi dữ liệu vĩnh viễn

Các lỗi như dữ liệu quá dài, sai kiểu, thiếu khóa ngoại, thiếu giá trị bắt buộc hoặc lỗi cú pháp không tự biến mất sau vài trăm mili giây. Retry chỉ làm tăng tải và kéo dài phản hồi.

Hãy phân loại theo mã lỗi và ngữ cảnh; lỗi chưa được phân loại nên được xử lý an toàn như không retry cho đến khi có chính sách rõ.

## 10. Idempotency: nền tảng của retry an toàn

Một thao tác idempotent có thể được thực hiện lặp lại mà kết quả nghiệp vụ cuối cùng không bị nhân đôi. Đây là yếu tố thiết yếu khi client có thể gửi lại request sau timeout hoặc mất kết nối.

### 10.1 Vì sao request có thể bị gửi lại?

Ví dụ:

1. Client gửi yêu cầu tạo đơn hàng.
2. Database INSERT và COMMIT thành công.
3. Response bị mất trên mạng trước khi client nhận được.
4. Client nghĩ request thất bại và gửi lại.

Nếu mỗi lần gửi đều INSERT đơn mới, một thao tác của người dùng tạo ra hai đơn hàng.

### 10.2 Idempotency key

Client tạo một request key ổn định cho cùng một ý định nghiệp vụ, ví dụ UUID. Database lưu key với ràng buộc duy nhất:

~~~sql
CREATE TABLE api_request (
    request_key   VARCHAR2(64) PRIMARY KEY,
    payload_hash  VARCHAR2(128) NOT NULL,
    result_id     NUMBER,
    request_state VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
~~~

Trong transaction tạo đơn:

1. Thử INSERT request key.
2. Tạo đơn hàng và các bản ghi liên quan.
3. Lưu result_id và trạng thái hoàn tất vào API_REQUEST.
4. COMMIT cùng một transaction.

Nếu request được gửi lại với cùng key:

- Nếu bản ghi đã hoàn tất và payload hash giống nhau, trả lại kết quả đã lưu.
- Nếu key đã tồn tại nhưng payload hash khác, trả lỗi conflict.
- Nếu request trước đang xử lý theo mô hình nhiều bước, dùng trạng thái/lease và quy tắc phục hồi đã thiết kế; không giả định key tồn tại đồng nghĩa nghiệp vụ đã hoàn tất.

### 10.3 Unique constraint là hàng rào chống race

Chỉ SELECT kiểm tra key chưa tồn tại rồi INSERT là chưa đủ khi nhiều session đồng thời. Hai session có thể cùng thấy chưa có dòng. PRIMARY KEY/UNIQUE constraint buộc database chỉ chấp nhận một key.

Session thua cuộc có thể nhận ORA-00001 sau khi session thắng commit. Ứng dụng đọc lại request theo key và xác định có thể trả lại kết quả cũ hay không.

### 10.4 Cùng key phải cùng payload

Không chỉ kiểm tra request_key. Hãy lưu một payload hash hoặc các trường nghiệp vụ đủ để xác nhận request lặp là cùng nội dung. Nếu client tái sử dụng key cho số tiền hoặc tài khoản khác, không được trả nhầm kết quả cũ.

Hash phải được tạo từ biểu diễn payload chuẩn hóa, có quy tắc rõ về thứ tự field, số thập phân, encoding và các giá trị NULL.

## 11. Kết quả COMMIT không rõ khi mất kết nối

Đây là trường hợp đặc biệt cần tránh retry mù.

### 11.1 Commit request có thể đã đến server

Client gửi COMMIT nhưng kết nối bị đứt trước khi nhận phản hồi. Có hai khả năng:

- Oracle đã commit, nhưng response bị mất.
- Oracle chưa commit hoặc transaction bị rollback khi session kết thúc.

Client không thể chỉ dựa vào lỗi mạng để kết luận giao dịch chưa thành công.

### 11.2 Không gửi lại thao tác không idempotent

Nếu thao tác là tạo đơn, trừ tiền hoặc tạo thanh toán, gửi lại ngay có thể nhân đôi tác dụng nếu lần đầu đã commit.

Quy trình phù hợp:

1. Dùng cùng idempotency key của request ban đầu.
2. Kết nối lại database.
3. Tra cứu trạng thái request/operation bằng key.
4. Nếu đã hoàn tất, trả kết quả đã lưu.
5. Nếu chưa tồn tại hoặc được xác nhận chưa hoàn tất, chạy lại theo quy tắc nghiệp vụ.
6. Nếu trạng thái vẫn chưa thể xác định, giữ trạng thái pending và tiếp tục đối soát; không tự tạo một request mới với key khác.

### 11.3 Phân biệt lỗi trước COMMIT và lỗi trong COMMIT

Nếu lỗi xảy ra trước khi gửi COMMIT và connection/session bị đóng, transaction chưa commit sẽ được Oracle rollback khi session kết thúc. Nhưng nếu lỗi xảy ra trong lúc COMMIT và response không đến client, kết quả có thể không rõ.

Vì vậy code retry nên nhận biết phase đang thực hiện. Một lỗi kết nối trong câu SELECT khác với lỗi kết nối ngay khi COMMIT.

## 12. Giao dịch với dịch vụ bên ngoài: Transactional Outbox

Không giữ transaction database mở trong lúc gọi dịch vụ bên ngoài:

~~~text
BEGIN DB TRANSACTION
    UPDATE order
    Call payment provider
    Wait response
    UPDATE payment status
COMMIT
~~~

Luồng này giữ khóa trong lúc mạng không ổn định. Nếu payment provider đã thu tiền nhưng response bị mất, database và provider có thể không đồng bộ.

### 12.1 Mẫu transactional outbox

Trong cùng transaction database:

1. Cập nhật đơn hàng sang trạng thái cần thanh toán.
2. Ghi một sự kiện vào bảng OUTBOX.
3. COMMIT.

Ví dụ:

~~~sql
UPDATE orders
SET status = 'PAYMENT_PENDING'
WHERE order_id = :p_order_id;

INSERT INTO outbox_event (
    event_id,
    aggregate_id,
    event_type,
    payload,
    event_status,
    created_at
)
VALUES (
    :p_event_id,
    :p_order_id,
    'REQUEST_PAYMENT',
    :p_payload,
    'READY',
    SYSTIMESTAMP
);

COMMIT;
~~~

Worker đọc OUTBOX, gọi payment provider với một idempotency key ổn định, rồi cập nhật trạng thái gửi. Database transaction ngắn và thay đổi đơn hàng/outbox được commit cùng nhau.

### 12.2 Vì sao outbox vẫn cần idempotency?

Worker có thể:

1. Gửi request thành công đến provider.
2. Provider xử lý thành công.
3. Worker bị dừng trước khi đánh dấu event đã gửi.
4. Worker chạy lại và gửi event lần nữa.

Vì vậy provider hoặc consumer cần deduplicate bằng event/request ID. Outbox thường cung cấp at-least-once delivery; không tự bảo đảm exactly-once side effect ở hệ thống bên ngoài.

### 12.3 Consumer cũng phải xử lý lặp

Consumer có thể lưu EVENT_ID đã xử lý với unique constraint. Khi nhận lại cùng event, nó kiểm tra trạng thái và không áp dụng tác dụng nghiệp vụ lần thứ hai.

## 13. Retry trong ứng dụng Java/JDBC

Ứng dụng Java thường quản lý transaction bằng Connection:

~~~java
connection.setAutoCommit(false);
~~~

Sau khi thực hiện các câu DML:

~~~java
connection.commit();
~~~

Khi lỗi trước commit:

~~~java
connection.rollback();
~~~

### 13.1 Pseudocode retry có phân biệt commit

~~~java
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            Result result = executeBusinessUnit(connection, requestKey);

            // Từ đây, lỗi phản hồi COMMIT có thể làm kết quả không rõ.
            try {
                connection.commit();
            } catch (SQLException commitError) {
                throw new CommitOutcomeUnknownException(
                    requestKey,
                    commitError
                );
            }

            return result;
        } catch (CommitOutcomeUnknownException e) {
            // Không retry mù. Tra cứu requestKey bằng connection mới.
            throw e;
        } catch (SQLException | RuntimeException e) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                e.addSuppressed(rollbackError);
            }

            if (!isRetryable(e) || attempt == maxAttempts) {
                throw e;
            }
        }
    }

    sleepWithBackoffAndJitter(attempt);
}
~~~

Đây là pseudocode minh họa cấu trúc, không phải một lớp retry hoàn chỉnh cho mọi driver. Cần bổ sung phân loại SQL error code, deadline, xử lý connection hỏng, logging và bước reconcile commit outcome bằng request key.

### 13.2 Trả connection về pool trong trạng thái sạch

Trước khi trả connection cho pool:

- COMMIT hoặc ROLLBACK transaction theo đúng kết quả.
- Không để transaction dang dở.
- Không giữ statement/result set không cần thiết.
- Nếu connection hỏng hoặc trạng thái transaction không thể xác định, loại connection khỏi pool theo cơ chế driver/pool.

Không dùng lại một connection có trạng thái không rõ cho request tiếp theo.

### 13.3 Retry không nên nằm ở nhiều tầng cùng lúc

Nếu JDBC layer retry 3 lần, service layer retry 3 lần và API gateway retry 3 lần, một thao tác có thể bị thực hiện tới 27 lần. Chọn một tầng sở hữu retry chính, hoặc thiết kế retry budget tổng thể xuyên suốt các tầng.

## 14. Ví dụ PL/SQL: chuyển tiền với rollback đúng phạm vi

Ví dụ sau minh họa transaction do block gọi sở hữu. Trong procedure dùng chung, nên để caller quyết định commit/rollback theo hợp đồng transaction của hệ thống.

### 14.1 Kiểm tra tham số và thực hiện DML

~~~sql
DECLARE
    l_amount NUMBER := 100;
    l_from_id NUMBER := 10;
    l_to_id NUMBER := 20;
    l_rows PLS_INTEGER;
BEGIN
    IF l_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Amount must be positive');
    END IF;

    IF l_from_id = l_to_id THEN
        RAISE_APPLICATION_ERROR(-20011, 'Accounts must be different');
    END IF;

    UPDATE accounts
    SET balance = balance - l_amount
    WHERE account_id = l_from_id
      AND balance >= l_amount;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20012,
            'Source account missing or insufficient balance'
        );
    END IF;

    UPDATE accounts
    SET balance = balance + l_amount
    WHERE account_id = l_to_id;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(-20013, 'Destination account not found');
    END IF;

    INSERT INTO transfer_log (
        from_account_id,
        to_account_id,
        amount,
        created_at
    )
    VALUES (
        l_from_id,
        l_to_id,
        l_amount,
        SYSTIMESTAMP
    );

    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

Block này sở hữu transaction riêng cho ví dụ nên ROLLBACK toàn bộ khi lỗi và COMMIT khi mọi bước thành công. Không bê nguyên COMMIT/ROLLBACK trong block này vào procedure được gọi bên trong một transaction lớn hơn của ứng dụng.

### 14.2 Cập nhật theo điều kiện bảo vệ số dư

Điều kiện BALANCE >= AMOUNT nằm ngay trong UPDATE. Điều này tránh tình huống hai session cùng đọc số dư cũ rồi cả hai cùng quyết định có thể trừ tiền.

Tuy nhiên, chuyển tiền còn cần xử lý khóa hai tài khoản, thứ tự khóa ổn định, tài khoản đích tồn tại, giới hạn số dư và idempotency key cho request. Ví dụ trên minh họa tính nguyên tử và SQL%ROWCOUNT, không phải một hệ thống ngân hàng production hoàn chỉnh.

### 14.3 Deadlock khi chuyển tiền ngược chiều

Nếu một session chuyển từ tài khoản 10 sang 20 và session khác chuyển từ 20 sang 10, mỗi session có thể khóa nguồn trước rồi chờ đích, tạo deadlock. Hệ thống thực tế nên khóa các tài khoản theo cùng thứ tự khóa ổn định, ví dụ account ID tăng dần, rồi mới thực hiện debit/credit theo vai trò nguồn/đích.

## 15. Queue worker và giao dịch ngắn

Một mô hình worker xử lý hàng đợi:

### 15.1 Claim công việc trong transaction ngắn

~~~sql
SELECT job_id
FROM job_queue
WHERE status = 'READY'
ORDER BY priority DESC, created_at, job_id
FOR UPDATE SKIP LOCKED;
~~~

Sau khi chọn dòng, worker cập nhật:

~~~sql
UPDATE job_queue
SET status = 'PROCESSING',
    claimed_at = SYSTIMESTAMP,
    lease_until = SYSTIMESTAMP + INTERVAL '2' MINUTE,
    worker_id = :p_worker_id
WHERE job_id = :p_job_id;

COMMIT;
~~~

Transaction claim kết thúc nhanh và nhả khóa. Worker thực hiện công việc bên ngoài transaction.

### 15.2 Hoàn tất trong transaction khác

Sau khi xử lý, worker mở transaction ngắn:

~~~sql
UPDATE job_queue
SET status = 'DONE',
    completed_at = SYSTIMESTAMP
WHERE job_id = :p_job_id
  AND worker_id = :p_worker_id
  AND status = 'PROCESSING';

COMMIT;
~~~

Điều kiện worker_id và status giúp tránh worker cũ cập nhật nhầm sau khi lease đã được cấp cho worker khác. Hệ thống cần định nghĩa chính sách lease expiry, heartbeat và retry count.

### 15.3 Worker chết giữa chừng

Nếu worker chết sau khi thực hiện side effect nhưng trước khi đánh dấu DONE, công việc có thể được nhận lại sau khi lease hết hạn. Do đó thao tác xử lý phải idempotent hoặc có deduplication key. Trạng thái queue một mình không bảo đảm side effect chỉ chạy một lần.

## 16. Batch và commit theo lô

Với tác vụ xử lý hàng triệu dòng, một transaction duy nhất có thể quá dài và tạo lượng undo lớn. Có thể chia thành batch nếu mỗi batch độc lập và có khả năng tiếp tục.

### 16.1 Mẫu batch theo khóa

Một quy trình có thể:

1. Chọn một khoảng khóa chưa xử lý.
2. Cập nhật dữ liệu trong khoảng đó.
3. Ghi checkpoint hoặc batch ID trong cùng transaction.
4. COMMIT.
5. Chuyển sang batch tiếp theo.

~~~sql
UPDATE large_table
SET processed_flag = 'Y'
WHERE id > :p_last_id
  AND id <= :p_next_id
  AND processed_flag = 'N';

UPDATE batch_checkpoint
SET last_id = :p_next_id,
    updated_at = SYSTIMESTAMP
WHERE job_name = 'PROCESS_LARGE_TABLE';

COMMIT;
~~~

Checkpoint và dữ liệu batch nên được commit cùng nhau để tránh checkpoint tiến lên nhưng dữ liệu chưa hoàn thành, hoặc ngược lại.

### 16.2 Không commit trong vòng lặp theo từng dòng nếu không cần

Commit từng dòng có thể tạo nhiều round trip/log sync, làm giảm throughput và khiến tác vụ chỉ hoàn thành một phần rất khó kiểm soát. Dùng bulk DML hoặc batch size hợp lý nếu nghiệp vụ cho phép.

### 16.3 Chọn batch size theo dữ liệu thực tế

Batch size phụ thuộc:

- Kích thước dòng và lượng undo/redo.
- Thời gian khóa.
- Tốc độ log writer và I/O.
- Độ trễ cho các giao dịch online.
- Khả năng retry và thời gian phục hồi.

Không có một batch size cố định phù hợp mọi hệ thống. Đo trên môi trường đại diện và điều chỉnh theo SLA.

### 16.4 Khi nghiệp vụ cần tất cả hoặc không gì cả

Nếu tất cả dòng phải thay đổi như một đơn vị không thể chia nhỏ, giữ một transaction nguyên tử dù nó dài hơn. Khi đó cần tối ưu truy vấn, xử lý theo tập hợp, tránh thao tác bên ngoài và chuẩn bị đủ tài nguyên thay vì commit giữa chừng làm sai nghiệp vụ.

## 17. Logging và quan sát lỗi

Khi retry hoặc rollback, log cần đủ thông tin để phân tích mà không làm lộ dữ liệu nhạy cảm.

Thông tin có thể ghi:

- Request ID hoặc idempotency key.
- Mã nghiệp vụ/đối tượng liên quan ở dạng an toàn.
- Bước xử lý và tên operation.
- Oracle error code, SQLCODE, SQLERRM.
- Số lần retry và thời gian chờ.
- Thời điểm bắt đầu/kết thúc và tổng latency.
- Kết quả commit đã xác định hay còn ambiguous.

Trong PL/SQL, có thể dùng DBMS_APPLICATION_INFO để gắn module/action:

~~~sql
BEGIN
    DBMS_APPLICATION_INFO.SET_MODULE(
        module_name => 'ORDER_SERVICE',
        action_name => 'CONFIRM_ORDER'
    );
END;
/
~~~

Ứng dụng có thể đặt CLIENT_IDENTIFIER để hỗ trợ truy vết session theo request/user đã được kiểm soát. Không ghi password, token, số thẻ hoặc payload nhạy cảm vào log.

### 17.1 Log lỗi không được làm mất lỗi gốc

Nếu ghi log trong exception handler rồi thao tác log cũng lỗi, hãy bảo đảm lỗi gốc vẫn được giữ lại hoặc được ghi nhận. Không để lỗi phụ che lỗi chính.

### 17.2 Transaction log và audit độc lập

Log được ghi trong cùng transaction có thể rollback. Nếu cần lưu cả sự kiện thất bại dù transaction nghiệp vụ rollback, cần thiết kế logging độc lập có chủ đích, ví dụ logger autonomous transaction hoặc hệ thống log bên ngoài. Autonomous transaction không nhìn thấy thay đổi chưa commit của transaction chính và phải tránh phụ thuộc vào dữ liệu chưa commit.

## 18. Quy trình retry tổng thể

Có thể dùng quy trình sau cho một request cập nhật dữ liệu:

~~~text
Nhận request + idempotency key
              |
              v
Kiểm tra request đã hoàn tất?
       | Có             | Chưa
       v                v
Trả kết quả cũ      Bắt đầu transaction
                         |
                         v
                 Đọc/kiểm tra dữ liệu
                         |
                         v
                 Thực hiện DML nguyên tử
                         |
                         v
                 Ghi kết quả + outbox
                         |
                         v
                       COMMIT
                    /          \
              Thành công     Mất phản hồi
                  |               |
                  v               v
              Trả kết quả    Tra cứu key
                                  |
                        +---------+---------+
                        |                   |
                    Đã commit          Chưa hoàn tất
                        |                   |
                        v                   v
                   Trả kết quả       Retry theo chính sách
~~~

Nếu DML gặp lỗi retryable trước commit:

1. Rollback transaction.
2. Ghi nhận lỗi và attempt.
3. Nhả khóa/connection.
4. Backoff có jitter.
5. Bắt đầu transaction mới và đọc lại dữ liệu.
6. Dừng khi thành công, lỗi permanent hoặc hết retry budget.

## 19. Các lỗi thiết kế thường gặp

| Lỗi thiết kế | Hậu quả | Cách cải thiện |
|---|---|---|
| Giữ transaction trong lúc gọi HTTP | Khóa lâu, tăng blocking | Commit dữ liệu và outbox trước; gọi bên ngoài sau |
| Retry vô hạn | Tạo tải và chờ không giới hạn | Retry budget, deadline và giới hạn attempt |
| Retry chỉ câu SQL lỗi trong transaction cũ | Có thể giữ thay đổi trước đó và snapshot cũ | Rollback và chạy lại toàn bộ đơn vị nghiệp vụ khi phù hợp |
| Retry mọi ORA error | Lỗi dữ liệu bị lặp vô ích | Phân loại retryable/permanent |
| Không dùng idempotency key | Request lặp có thể tạo đơn/thu tiền hai lần | Unique request key và lưu kết quả |
| Dựa vào SELECT trước INSERT để chống trùng | Race condition giữa session | UNIQUE constraint |
| Mất response COMMIT rồi gửi request mới | Có thể thực hiện nghiệp vụ hai lần | Tra cứu theo cùng idempotency key |
| Procedure tự COMMIT | Có thể commit công việc của caller | Quy định rõ transaction ownership |
| WHEN OTHERS THEN NULL | Che lỗi và trạng thái một phần | RAISE hoặc trả lỗi có kiểm soát |
| Sleep khi vẫn giữ transaction | Tiếp tục giữ khóa trong lúc chờ | Rollback/commit rồi mới backoff |
| Lock nhiều dòng theo thứ tự khác nhau | Deadlock | Thống nhất thứ tự khóa |
| Chia transaction dù nghiệp vụ cần atomic | Trạng thái trung gian sai | Giữ một transaction hoặc thiết kế state machine/bù trừ |
| Commit từng dòng không có checkpoint | Khó tiếp tục và khó đối soát | Batch độc lập + checkpoint cùng transaction |
| Gọi dịch vụ ngoài rồi mới commit DB | Side effect ngoài có thể thành công trong khi DB rollback | Outbox, idempotency và quy trình đối soát |
| Dùng SKIP LOCKED cho truy vấn người dùng | Dữ liệu đang khóa biến mất khỏi kết quả | Chỉ dùng cho worker/queue có semantics phù hợp |

## 20. Checklist thiết kế transaction và retry

Trước khi đưa một luồng nghiệp vụ vào production, hãy xác định:

1. Những thay đổi nào bắt buộc phải cùng thành công hoặc cùng thất bại?
2. Transaction bắt đầu ở đâu và ai sở hữu COMMIT/ROLLBACK?
3. Có thao tác người dùng, mạng, file hoặc sleep nào nằm trong lúc giữ transaction không?
4. Có thể dùng một câu DML có điều kiện thay cho SELECT rồi UPDATE không?
5. Cần SELECT FOR UPDATE hay optimistic version check?
6. Nếu khóa nhiều dòng, mọi luồng có lấy theo cùng thứ tự không?
7. Có giới hạn WAIT/NOWAIT phù hợp không?
8. Exception handler có rollback đúng phạm vi và giữ lỗi gốc không?
9. Có savepoint không, và savepoint có thể xung đột với caller không?
10. Những Oracle error code nào được phép retry?
11. Retry có rollback và bắt đầu transaction mới không?
12. Retry có giới hạn số lần, deadline và backoff/jitter không?
13. Request có idempotency key và unique constraint không?
14. Nếu COMMIT response bị mất, có cách xác định kết quả theo key không?
15. Side effect bên ngoài có dùng outbox hoặc cơ chế đồng bộ đáng tin cậy không?
16. Worker/consumer có thể nhận lại cùng một event không, và có deduplicate không?
17. Batch có checkpoint được commit cùng dữ liệu không?
18. Log có request ID, error code và attempt mà không lộ dữ liệu nhạy cảm không?

## 21. Bài tập tự luyện

**Câu 1 — Atomicity.** Một transaction trừ tiền tài khoản A rồi cộng tiền tài khoản B. UPDATE thứ hai lỗi. Điều gì xảy ra nếu PL/SQL chỉ RAISE mà caller không rollback?

Gợi ý: Câu lệnh lỗi được rollback, nhưng UPDATE đầu vẫn nằm trong transaction; caller phải rollback nếu cần hủy cả nghiệp vụ.

**Câu 2 — Transaction ngắn.** Vì sao không nên gọi payment provider trong khi đang giữ SELECT FOR UPDATE?

Gợi ý: Mạng có thể chậm hoặc timeout, khiến row lock bị giữ lâu và chặn session khác.

**Câu 3 — Optimistic concurrency.** UPDATE theo VERSION_NO trả SQL%ROWCOUNT bằng 0. Nên làm gì?

Gợi ý: Đọc lại dữ liệu, báo conflict hoặc hợp nhất theo quy tắc; không lặp cùng version vô hạn.

**Câu 4 — Deadlock.** Hai session khóa account 10 và 20 theo thứ tự ngược nhau. Cách giảm deadlock?

Gợi ý: Thống nhất thứ tự khóa theo account ID tăng dần.

**Câu 5 — Phân loại lỗi.** ORA-12899 có nên retry sau 500 ms không?

Gợi ý: Không. Dữ liệu vượt độ dài cột là lỗi đầu vào/schema, không tự biến mất.

**Câu 6 — ORA-08177.** Khi SERIALIZABLE transaction gặp lỗi này, nên retry statement hay transaction?

Gợi ý: Rollback và chạy lại toàn bộ đơn vị nghiệp vụ với snapshot mới nếu retry được.

**Câu 7 — Unique conflict.** ORA-00001 trên idempotency key có thể có nghĩa gì?

Gợi ý: Một request cùng key đã được ghi. Tra cứu kết quả và so sánh payload thay vì retry mù.

**Câu 8 — Commit outcome.** Client mất kết nối ngay khi gọi COMMIT. Vì sao không nên tạo request mới?

Gợi ý: Commit có thể đã thành công nhưng response bị mất. Dùng cùng key để tra cứu trạng thái.

**Câu 9 — Outbox.** Vì sao outbox vẫn cần consumer idempotent?

Gợi ý: Worker có thể gửi thành công rồi chết trước khi đánh dấu event hoàn tất; event có thể được gửi lại.

**Câu 10 — Batch.** Khi commit theo batch, checkpoint nên được ghi lúc nào?

Gợi ý: Trong cùng transaction với dữ liệu batch để trạng thái tiến độ và dữ liệu không lệch nhau.

## 22. Tổng kết

Thiết kế giao dịch tốt trong Oracle cần giữ đúng ranh giới nghiệp vụ và kết thúc transaction sớm sau khi hoàn thành các DML cần nguyên tử. Không giữ khóa trong lúc chờ người dùng hoặc dịch vụ bên ngoài; dùng điều kiện UPDATE, SELECT FOR UPDATE hoặc optimistic version check tùy mức độ cạnh tranh. Khi có lỗi, nhớ rằng lỗi một câu SQL không tự rollback toàn bộ transaction; caller phải sở hữu và xử lý COMMIT/ROLLBACK rõ ràng.

Retry phải có phân loại, giới hạn, backoff và idempotency:

- ORA-00060 và ORA-08177 thường cần rollback rồi thử lại toàn bộ đơn vị nghiệp vụ nếu có thể.
- ORA-00054 có thể là xung đột khóa tạm thời, nhưng phải giới hạn thời gian chờ.
- ORA-00001 cần kiểm tra request trùng/unique conflict, không retry mù.
- Lỗi dữ liệu như ORA-01400, ORA-02291 hoặc ORA-12899 thường cần sửa đầu vào hoặc quy tắc, không retry.
- Mất kết nối trong COMMIT có thể khiến kết quả chưa rõ; tra cứu bằng idempotency key trước khi thực hiện lại.
- Outbox và consumer idempotent giúp xử lý side effect bên ngoài mà không giữ transaction database kéo dài.

Khi transaction ngắn, lỗi được phân loại đúng và request có thể xử lý lặp an toàn, hệ thống sẽ giảm blocking, tránh dữ liệu một phần, phục hồi tốt hơn khi xung đột và duy trì hành vi nhất quán khi mạng hoặc worker gặp sự cố.
