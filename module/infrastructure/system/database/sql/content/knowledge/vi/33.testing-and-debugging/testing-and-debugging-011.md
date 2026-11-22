# Đọc SQLSTATE, mã lỗi và thông báo theo hệ quản trị

Khi một câu SQL thất bại, database thường trả về nhiều thông tin: mã trạng thái SQL, mã lỗi riêng của hệ quản trị, thông báo, mức độ nghiêm trọng, tên constraint, bảng/cột liên quan và đôi khi cả vị trí xảy ra lỗi. Đọc đúng các thông tin này giúp xác định nguyên nhân nhanh hơn, phân biệt lỗi dữ liệu với lỗi cú pháp hoặc kết nối, và quyết định có nên thử lại transaction hay cần sửa câu lệnh.

Một thông báo như `duplicate key value violates unique constraint` cho biết điều gì vừa xảy ra, nhưng **mã lỗi có cấu trúc mới là tín hiệu phù hợp để chương trình phân loại lỗi**. Thông báo có thể thay đổi theo phiên bản, driver, ngôn ngữ hoặc cấu hình. Không nên viết logic nghiệp vụ bằng cách dò chuỗi message.

Bài học thuộc chương **Kiểm thử và gỡ lỗi** của **Database SQL**. Nội dung giải thích SQLSTATE, vendor error code và diagnostic message; cách đọc lỗi PostgreSQL, SQL Server, MySQL, SQLite và Oracle; cách lấy thông tin trong JDBC, Python và PL/SQL; cách phân biệt lỗi có thể retry với lỗi cần sửa; và cách kiểm thử, ghi log, xử lý lỗi mà không làm lộ dữ liệu nhạy cảm.

> **Nguyên tắc:** dùng mã lỗi có cấu trúc để phân loại; dùng message, detail, hint và context để điều tra; luôn đọc tài liệu đúng DBMS, phiên bản và driver. Không giả định một mã vendor hoặc cách viết message có cùng ý nghĩa trên mọi hệ quản trị.

## 1. Một lỗi SQL có thể có nhiều lớp thông tin

Khi câu lệnh thất bại, ứng dụng có thể nhìn thấy một exception chứa nhiều trường:

| Trường | Ý nghĩa |
|---|---|
| SQLSTATE | Mã trạng thái SQL có cấu trúc, thường gồm 5 ký tự |
| Vendor error code / native error number | Mã lỗi riêng của DBMS hoặc driver |
| Message | Mô tả ngắn lỗi cho con người |
| Detail | Chi tiết bổ sung, ví dụ giá trị hoặc constraint liên quan |
| Hint | Gợi ý cách xử lý, nếu DBMS cung cấp |
| Severity / class | Mức độ nghiêm trọng hoặc phân loại lỗi theo DBMS |
| Schema / table / column | Đối tượng liên quan, nếu được cung cấp |
| Constraint | Tên constraint bị vi phạm |
| Position / line / procedure | Vị trí hoặc thủ tục xảy ra lỗi |
| Cause / next exception | Lỗi gốc hoặc lỗi tiếp theo trong chuỗi exception |

Không phải DBMS hay driver nào cũng cung cấp mọi trường. Có hệ thống có SQLSTATE nhưng không có detail riêng; có hệ thống có native error number và severity; có driver bọc nhiều lỗi vào một exception hoặc chuỗi exception.

### 1.1. SQLSTATE không phải message

Ví dụ PostgreSQL:

~~~text
SQLSTATE: 23505
Message: duplicate key value violates unique constraint "customers_email_key"
Detail: Key (email)=(an@example.test) already exists.
~~~

SQLSTATE `23505` là mã `unique_violation` trong PostgreSQL. Message mô tả lỗi; detail chỉ ra khóa cụ thể đã trùng.

Chương trình nên nhận diện lỗi unique bằng SQLSTATE khi driver cung cấp, còn message/detail dùng cho log hoặc phản hồi đã được kiểm soát.

### 1.2. Vendor code không phải SQLSTATE

Một lỗi có thể có:

~~~text
SQLSTATE: 23000
Native error code: 1062
Message: Duplicate entry ...
~~~

Đây là dạng thường gặp với MySQL: SQLSTATE biểu thị nhóm integrity constraint violation; mã native `1062` cụ thể hơn cho duplicate entry.

Không so sánh `1062` với SQLSTATE `23505` như thể chúng cùng một hệ mã. Một mã là native code MySQL, mã kia là PostgreSQL SQLSTATE.

### 1.3. Message có thể thay đổi

Message có thể thay đổi do:

- Phiên bản DBMS hoặc driver.
- Ngôn ngữ và locale.
- Cách DBMS diễn giải cùng một lỗi.
- Tên bảng, cột, constraint và giá trị dữ liệu.
- Cấu hình hiển thị detail hoặc mức verbosity.

Vì thế, code như sau rất mong manh:

~~~java
if (exception.getMessage().contains("duplicate")) {
    // Coi là duplicate.
}
~~~

Nó có thể hỏng khi message đổi ngôn ngữ, thêm tiền tố hoặc đổi cách diễn đạt. Hãy dùng SQLSTATE/native code và API diagnostic chính thức.

## 2. Cấu trúc SQLSTATE

SQLSTATE là mã trạng thái có cấu trúc, thông thường gồm **5 ký tự chữ-số**. Hai ký tự đầu là **class** (nhóm lỗi); ba ký tự sau là **subclass** (loại cụ thể hơn).

~~~text
SQLSTATE = CC SSS
             |  |
             |  +-- Subclass: ba ký tự cuối
             +----- Class: hai ký tự đầu
~~~

Ví dụ:

~~~text
23505
^^
||
|+-- Class 23: integrity constraint violation
+--- Subclass 505: mã cụ thể do chuẩn/DBMS định nghĩa
~~~

Mã có thể được quy định bởi chuẩn SQL hoặc mở rộng riêng theo DBMS. Không phải mọi DBMS hỗ trợ cùng tập mã, và không phải mọi driver đều chuyển đổi lỗi theo cùng cách.

### 2.1. Một số class SQLSTATE thường gặp

| Class | Nhóm | Ý nghĩa tổng quát |
|---|---|---|
| 00 | Successful completion | Hoàn tất thành công |
| 01 | Warning | Cảnh báo |
| 02 | No data | Không có dữ liệu hoặc không tìm thấy hàng theo ngữ cảnh |
| 08 | Connection exception | Lỗi kết nối |
| 0A | Feature not supported | Tính năng không được hỗ trợ |
| 21 | Cardinality violation | Vi phạm số lượng hàng/giá trị theo ngữ cảnh |
| 22 | Data exception | Lỗi dữ liệu hoặc chuyển đổi kiểu |
| 23 | Integrity constraint violation | Vi phạm constraint |
| 24 | Invalid cursor state | Trạng thái cursor không hợp lệ |
| 25 | Invalid transaction state | Trạng thái transaction không hợp lệ |
| 28 | Invalid authorization specification | Thông tin xác thực/quyền không hợp lệ |
| 2D | Invalid transaction termination | Kết thúc transaction không hợp lệ |
| 40 | Transaction rollback | Transaction bị rollback |
| 42 | Syntax error or access rule violation | Lỗi cú pháp hoặc quy tắc truy cập |
| 53 | Insufficient resources | Thiếu tài nguyên |
| 54 | Program limit exceeded | Vượt giới hạn hệ thống/chương trình |
| 55 | Object not in prerequisite state | Đối tượng chưa ở trạng thái cần thiết |
| 57 | Operator intervention | Can thiệp từ operator, hủy hoặc shutdown theo ngữ cảnh |
| 58 | System error | Lỗi hệ thống |
| HY | ODBC/driver-specific class | Một số trạng thái do ODBC/driver quy định |

Đây là bản đồ định hướng. Khi cần xử lý một mã cụ thể, tra tài liệu chính thức của DBMS và driver đang sử dụng.

### 2.2. Class 22 — Data exception

Class 22 thường liên quan đến giá trị dữ liệu:

- Chuyển chuỗi sang số không thành công.
- Giá trị số vượt miền kiểu dữ liệu.
- Chuỗi quá dài.
- Giá trị ngày/giờ không hợp lệ.
- Chia cho 0 hoặc biểu thức số học không hợp lệ theo ngữ cảnh.

Ví dụ PostgreSQL:

| SQLSTATE | Tên thường dùng | Tình huống |
|---|---|---|
| 22003 | numeric_value_out_of_range | Số vượt miền kiểu |
| 22007 | invalid_datetime_format | Định dạng ngày giờ không hợp lệ |
| 22012 | division_by_zero | Chia cho 0 |
| 22001 | string_data_right_truncation | Chuỗi bị cắt/vượt độ dài |
| 22P02 | invalid_text_representation | Biểu diễn văn bản không chuyển được sang kiểu đích |

Mã subclass có thể khác theo DBMS; không sao chép mã PostgreSQL sang một hệ quản trị khác.

### 2.3. Class 23 — Integrity constraint violation

Nhóm này bao gồm:

- PRIMARY KEY hoặc UNIQUE bị trùng.
- FOREIGN KEY tham chiếu không hợp lệ.
- NOT NULL bị vi phạm.
- CHECK constraint không thỏa.

Trong PostgreSQL, các SQLSTATE phổ biến:

| SQLSTATE | Tên | Ý nghĩa |
|---|---|---|
| 23000 | integrity_constraint_violation | Class tổng quát |
| 23502 | not_null_violation | Ghi NULL vào cột NOT NULL |
| 23503 | foreign_key_violation | Vi phạm khóa ngoại |
| 23505 | unique_violation | Vi phạm UNIQUE/PRIMARY KEY |
| 23514 | check_violation | Vi phạm CHECK |

Khi gặp class 23, thường phải sửa dữ liệu hoặc quy tắc nghiệp vụ. Retry cùng một statement với đúng dữ liệu cũ thường không giúp ích.

### 2.4. Class 40 — Transaction rollback

Một số tình huống:

- Serialization failure.
- Deadlock khiến DBMS chọn transaction làm nạn nhân.

PostgreSQL:

| SQLSTATE | Tên | Ý nghĩa |
|---|---|---|
| 40001 | serialization_failure | Transaction không thể hoàn tất theo isolation |
| 40P01 | deadlock_detected | Phát hiện deadlock |

Hai lỗi này thường có thể retry **toàn bộ transaction** theo chính sách có giới hạn, sau khi rollback và bắt đầu transaction mới.

### 2.5. Class 42 — Syntax/access rule violation

PostgreSQL có các mã hay gặp:

| SQLSTATE | Tên | Tình huống |
|---|---|---|
| 42601 | syntax_error | Cú pháp SQL sai |
| 42P01 | undefined_table | Không tìm thấy bảng/quan hệ |
| 42703 | undefined_column | Không tìm thấy cột |
| 42501 | insufficient_privilege | Thiếu quyền |
| 42883 | undefined_function | Không tìm thấy hàm phù hợp |

Lỗi class 42 thường yêu cầu sửa SQL, schema, search_path hoặc quyền. Retry nguyên câu lệnh thường không giải quyết được.

### 2.6. Class 08 — Connection exception

Class 08 biểu thị vấn đề kết nối. Ví dụ PostgreSQL có các mã như 08000 (connection exception), 08003 (connection does not exist), 08006 (connection failure).

Khi kết nối bị mất, trạng thái transaction có thể không rõ đối với ứng dụng: server có thể đã commit nhưng phản hồi bị mất, hoặc transaction chưa commit. Không được tự động gửi lại mọi thao tác ghi nếu không có cơ chế idempotency.

## 3. Đọc lỗi theo quy trình có hệ thống

Khi một truy vấn thất bại, đọc thông tin theo thứ tự:

1. **Xác định thao tác:** câu lệnh nào, endpoint/job nào, transaction đang làm gì?
2. **Đọc SQLSTATE:** class nào, subclass cụ thể nào?
3. **Đọc vendor code:** DBMS có mã native chi tiết hơn không?
4. **Đọc message và detail:** đối tượng, cột, constraint, kiểu dữ liệu hoặc giá trị nào liên quan?
5. **Đọc vị trí:** line, position, procedure, schema, table, column.
6. **Đọc chuỗi exception:** lỗi gốc, lỗi tiếp theo, lỗi do rollback hoặc đóng connection?
7. **Xác định transaction state:** còn hoạt động, đã rollback hay connection đã mất?
8. **Chọn hành động:** sửa input, sửa SQL/schema, xử lý conflict, rollback/retry hoặc chuyển lỗi cho người vận hành.

### 3.1. Ví dụ đọc lỗi UNIQUE

Giả sử PostgreSQL trả:

~~~text
ERROR: duplicate key value violates unique constraint "customers_email_key"
DETAIL: Key (email)=(an@example.test) already exists.
SQLSTATE: 23505
~~~

Diễn giải:

- Class 23: integrity constraint violation.
- Subclass 505: unique violation.
- Constraint: customers_email_key.
- Cột: email.
- Giá trị trùng: an@example.test.

Hành động:

- Nếu email phải duy nhất: trả conflict/validation phù hợp.
- Nếu đây là thao tác tạo-or-update: cân nhắc UPSERT theo đúng khóa nghiệp vụ.
- Nếu duplicate không được phép nhưng đáng lẽ không thể xảy ra: kiểm tra retry, request lặp, race condition và luồng ghi.
- Không retry nguyên INSERT với cùng email mà không đổi chiến lược.

### 3.2. Ví dụ đọc lỗi chuyển kiểu

~~~text
ERROR: invalid input syntax for type integer: "abc"
SQLSTATE: 22P02
~~~

Diễn giải:

- Class 22: data exception.
- SQLSTATE 22P02 trong PostgreSQL: biểu diễn văn bản không hợp lệ cho kiểu đích.
- Đầu vào "abc" không thể chuyển thành integer.

Hành động:

- Kiểm tra validation ở tầng API.
- Kiểm tra kiểu bind và schema.
- Không bắt lỗi rồi đổi thành 0 vì sẽ làm sai dữ liệu.
- Ghi nhận lỗi đầu vào mà không log dữ liệu nhạy cảm không cần thiết.

### 3.3. Ví dụ đọc lỗi nhiều hàng trong scalar subquery

Một scalar subquery trong PostgreSQL trả nhiều hàng sẽ gây lỗi cardinality. Đây là dấu hiệu truy vấn giả định một kết quả duy nhất nhưng dữ liệu thực tế có nhiều hàng.

Hành động:

- Kiểm tra điều kiện lọc và khóa unique.
- Nếu nghiệp vụ cần một hàng, xác định quy tắc chọn hàng rõ ràng.
- Nếu nghiệp vụ cho phép nhiều hàng, dùng IN/EXISTS/JOIN hoặc một truy vấn trả danh sách.
- Không thêm LIMIT 1 chỉ để làm lỗi biến mất mà không xác định semantics.

## 4. PostgreSQL: SQLSTATE, message, detail và hint

PostgreSQL cung cấp SQLSTATE ổn định để ứng dụng phân loại lỗi. Message/detail/hint có thể giúp người phát triển điều tra.

### 4.1. Các trường chẩn đoán thường gặp

Ví dụ lỗi unique:

~~~text
ERROR: duplicate key value violates unique constraint "customers_email_key"
DETAIL: Key (email)=(an@example.test) already exists.
SCHEMA NAME: public
TABLE NAME: customers
CONSTRAINT NAME: customers_email_key
SQLSTATE: 23505
~~~

Tùy client và driver, các trường schema/table/constraint có thể xuất hiện riêng trong diagnostic object thay vì được in thành dòng văn bản.

Các thông tin quan trọng:

- Severity: mức ERROR, WARNING, NOTICE...
- SQLSTATE: mã phân loại.
- Message: mô tả ngắn.
- Detail: thông tin bổ sung.
- Hint: gợi ý.
- Position/Internal position: vị trí trong câu SQL hoặc câu SQL nội bộ.
- Context: stack context của PL/pgSQL.
- Schema/table/column/constraint: đối tượng liên quan.

### 4.2. Lỗi thường gặp trong PostgreSQL

| SQLSTATE | Tên | Ví dụ nguyên nhân |
|---|---|---|
| 23502 | not_null_violation | INSERT thiếu giá trị NOT NULL |
| 23503 | foreign_key_violation | Giá trị FK không tồn tại |
| 23505 | unique_violation | Trùng khóa duy nhất |
| 23514 | check_violation | Giá trị không thỏa CHECK |
| 22P02 | invalid_text_representation | Chuỗi không chuyển được sang kiểu |
| 22003 | numeric_value_out_of_range | Số vượt miền kiểu |
| 22012 | division_by_zero | Chia cho 0 |
| 42601 | syntax_error | Sai cú pháp |
| 42P01 | undefined_table | Sai tên bảng/schema |
| 42703 | undefined_column | Sai tên cột |
| 42501 | insufficient_privilege | Thiếu quyền |
| 40001 | serialization_failure | Xung đột serialization |
| 40P01 | deadlock_detected | Deadlock |
| 55P03 | lock_not_available | Không lấy được lock theo yêu cầu |
| 57014 | query_canceled | Query bị hủy hoặc timeout theo ngữ cảnh |
| 08006 | connection_failure | Kết nối bị lỗi |

Đây là mã PostgreSQL, không phải bảng ánh xạ chung cho mọi DBMS.

### 4.3. Đọc SQLSTATE trong psql

Trong psql, có thể hiển thị SQLSTATE sau lỗi bằng biến đặc biệt:

~~~sql
\set VERBOSITY verbose
SELECT 1 / 0;
~~~

Chế độ verbose hiển thị thêm SQLSTATE và vị trí trong chẩn đoán. Tùy phiên bản psql, có thể cấu hình mức verbosity khác nhau. Khi làm việc trong ứng dụng, lấy SQLSTATE từ driver thay vì parse output terminal.

### 4.4. PL/pgSQL: GET STACKED DIAGNOSTICS

Trong exception handler, có thể lấy thông tin lỗi có cấu trúc:

~~~sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_constraint TEXT;
BEGIN
    INSERT INTO customers_lab(customer_id, customer_name, email)
    VALUES (2, 'Duplicate Binh', 'binh@example.test');
EXCEPTION
    WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail = PG_EXCEPTION_DETAIL,
            v_hint = PG_EXCEPTION_HINT,
            v_constraint = CONSTRAINT_NAME;

        RAISE NOTICE 'SQLSTATE=%', v_state;
        RAISE NOTICE 'MESSAGE=%', v_message;
        RAISE NOTICE 'DETAIL=%', v_detail;
        RAISE NOTICE 'HINT=%', v_hint;
        RAISE NOTICE 'CONSTRAINT=%', v_constraint;
END;
$$;
~~~

Đoạn ví dụ giả định customers_lab có hàng customer_id = 2 và email binh@example.test. Nếu fixture khác, hãy điều chỉnh để thực sự tạo lỗi unique.

Trong production, không nên bắt mọi lỗi rồi chỉ in NOTICE và tiếp tục như không có gì. Cần quyết định lỗi nào được xử lý, lỗi nào phải được ném lại bằng RAISE hoặc chuyển lên tầng ứng dụng.

### 4.5. Phân biệt lỗi do câu SQL và lỗi do transaction

PostgreSQL thường đánh dấu transaction là failed sau một statement error. Các statement tiếp theo trong transaction sẽ bị từ chối cho tới khi ROLLBACK hoặc ROLLBACK TO SAVEPOINT.

Ví dụ:

~~~sql
BEGIN;

INSERT INTO customers_lab(customer_id, customer_name, email)
VALUES (2, 'Duplicate', 'binh@example.test');

SELECT 1;
~~~

Nếu INSERT vi phạm unique, SELECT sau đó không chạy bình thường trong transaction đã failed. Cần:

~~~sql
ROLLBACK;
~~~

hoặc nếu đã tạo savepoint trước thao tác có thể lỗi:

~~~sql
BEGIN;
SAVEPOINT before_optional_insert;

-- Statement có thể gây lỗi.

ROLLBACK TO SAVEPOINT before_optional_insert;
-- Transaction có thể tiếp tục từ savepoint.
COMMIT;
~~~

Savepoint hữu ích khi lỗi là một phần có thể dự kiến và được xử lý. Không dùng nó để che lỗi lập trình hoặc tiếp tục với trạng thái dữ liệu không nhất quán.

## 5. SQL Server: Error Number, State, Severity và SqlException

SQL Server thường hiển thị thông tin lỗi theo dạng:

~~~text
Msg 2627, Level 14, State 1, Line 1
Violation of PRIMARY KEY constraint ...
~~~

Các thành phần:

- **Error number:** mã lỗi native, ví dụ 2627.
- **Severity/Level:** mức độ nghiêm trọng.
- **State:** trạng thái phụ để phân biệt ngữ cảnh phát sinh cùng error number.
- **Line:** dòng xảy ra lỗi.
- **Procedure:** stored procedure nếu có.
- **Message:** mô tả lỗi.

Trường `State` của SQL Server **không phải SQLSTATE**. Không nhầm hai khái niệm cùng tên.

### 5.1. Một số mã SQL Server thường gặp

| Error number | Tình huống |
|---:|---|
| 2601 | Duplicate key trong unique index |
| 2627 | Vi phạm PRIMARY KEY hoặc UNIQUE constraint |
| 547 | Vi phạm FOREIGN KEY hoặc CHECK constraint |
| 515 | Ghi NULL vào cột NOT NULL |
| 207 | Invalid column name |
| 208 | Invalid object name |
| 245 | Chuyển đổi kiểu dữ liệu không thành công trong một số ngữ cảnh |
| 8115 | Arithmetic overflow |
| 1205 | Transaction bị chọn làm deadlock victim |
| 1222 | Lock request timeout |
| 18456 | Login failed |
| 4060 | Không mở được database được yêu cầu |

Đây là error number native của SQL Server. Driver có thể cung cấp thêm SQLState theo lớp JDBC/ODBC, nhưng không được coi native error number là SQLSTATE.

### 5.2. Đọc SqlException trong C#

~~~csharp
try
{
    using var command = new SqlCommand(
        "INSERT INTO dbo.Customers(Email) VALUES (@email)",
        connection);

    command.Parameters.AddWithValue("@email", email);
    command.ExecuteNonQuery();
}
catch (SqlException ex)
{
    foreach (SqlError error in ex.Errors)
    {
        Console.WriteLine($"Number: {error.Number}");
        Console.WriteLine($"State: {error.State}");
        Console.WriteLine($"Class: {error.Class}");
        Console.WriteLine($"Procedure: {error.Procedure}");
        Console.WriteLine($"Line: {error.LineNumber}");
        Console.WriteLine($"Message: {error.Message}");
    }

    throw;
}
~~~

Một SqlException có thể chứa nhiều SqlError trong collection Errors. Đừng chỉ giả định exception luôn có đúng một lỗi.

Trong code production, dùng error number để phân loại; không trả message database nguyên văn cho client. Ví dụ 2601/2627 có thể được ánh xạ thành conflict nếu đúng là duplicate theo quy tắc nghiệp vụ.

### 5.3. TRY...CATCH và ERROR_* trong T-SQL

~~~sql
BEGIN TRY
    INSERT INTO dbo.Customers(Email)
    VALUES ('existing@example.test');
END TRY
BEGIN CATCH
    SELECT
        ERROR_NUMBER() AS error_number,
        ERROR_SEVERITY() AS error_severity,
        ERROR_STATE() AS error_state,
        ERROR_PROCEDURE() AS error_procedure,
        ERROR_LINE() AS error_line,
        ERROR_MESSAGE() AS error_message;
END CATCH;
~~~

Các hàm ERROR_* đọc thông tin của lỗi trong block CATCH. Nếu cần transaction có thể rollback, kiểm tra trạng thái bằng XACT_STATE() và xử lý theo chính sách transaction.

### 5.4. Deadlock và retry

Error 1205 cho biết transaction bị chọn làm deadlock victim. Sau khi transaction rollback, ứng dụng có thể retry **toàn bộ đơn vị công việc** với số lần giới hạn và backoff.

Không chỉ chạy lại statement cuối nếu transaction đã bị rollback. Phải đảm bảo các side effect ngoài database (gửi email, gọi API, phát message) không bị thực hiện hai lần hoặc cần outbox/idempotency.

## 6. MySQL: SQLSTATE và native error number

MySQL thường trả đồng thời:

- SQLSTATE, ví dụ 23000.
- Error number, ví dụ 1062.
- Message.

Ví dụ:

~~~text
ERROR 1062 (23000): Duplicate entry 'an@example.test' for key 'customers.email'
~~~

`1062` là mã native MySQL; `23000` là SQLSTATE class integrity constraint violation.

### 6.1. Một số mã MySQL thường gặp

| Error number | SQLSTATE thường gặp | Tình huống |
|---:|---|---|
| 1062 | 23000 | Duplicate entry |
| 1452 | 23000 | Không thêm được hàng con do FK |
| 1451 | 23000 | Không xóa/cập nhật hàng cha đang được tham chiếu |
| 1048 | 23000 | Cột không thể NULL |
| 1366 | 22007 hoặc mã theo ngữ cảnh/phiên bản | Incorrect value/conversion |
| 1054 | 42S22 | Unknown column |
| 1146 | 42S02 | Table doesn't exist |
| 1064 | 42000 | Syntax error |
| 1213 | 40001 | Deadlock |
| 1205 | HY000 | Lock wait timeout |
| 1045 | 28000 | Access denied |
| 2006 | HY000 | MySQL server has gone away |
| 2013 | HY000 | Lost connection during query |

Mã SQLSTATE cụ thể có thể phụ thuộc loại lỗi và phiên bản. Khi triển khai, xác minh theo tài liệu MySQL và connector đang dùng.

### 6.2. Đọc lỗi trong Python mysql-connector

~~~python
import mysql.connector

try:
    cursor.execute(
        "INSERT INTO customers(email) VALUES (%s)",
        (email,),
    )
    connection.commit()
except mysql.connector.Error as exc:
    print("errno:", exc.errno)
    print("sqlstate:", exc.sqlstate)
    print("message:", exc.msg)
    connection.rollback()
    raise
~~~

Các thuộc tính cụ thể phụ thuộc connector. Một số driver Python khác đặt tên thuộc tính khác; đọc tài liệu driver thay vì giả định mọi DB-API exception có cùng thuộc tính.

### 6.3. MySQL warning khác error

MySQL có warning và error. Một statement có thể hoàn tất nhưng tạo warning, ví dụ chuyển đổi hoặc cắt dữ liệu theo SQL mode. Ứng dụng cần biết SQL mode và chính sách dữ liệu để quyết định warning có chấp nhận được không.

Có thể kiểm tra warning trong client:

~~~sql
SHOW WARNINGS;
~~~

Không bỏ qua warning trong môi trường mà dữ liệu bị cắt/chuyển kiểu có thể gây sai lệch nghiệp vụ.

## 7. SQLite: primary result code và extended result code

SQLite có hệ mã riêng. Các mã cơ sở thường được chia thành nhóm; extended result code bổ sung nguyên nhân chi tiết hơn.

### 7.1. Một số result code

| Code/name | Ý nghĩa |
|---|---|
| SQLITE_OK (0) | Thành công |
| SQLITE_ERROR (1) | Lỗi SQL tổng quát |
| SQLITE_BUSY (5) | Database đang bận, không thể cấp quyền truy cập ngay |
| SQLITE_LOCKED (6) | Xung đột lock |
| SQLITE_NOMEM (7) | Không đủ bộ nhớ |
| SQLITE_READONLY (8) | Thao tác ghi trên database read-only |
| SQLITE_IOERR (10) | Lỗi I/O |
| SQLITE_CORRUPT (11) | Database có thể bị hỏng |
| SQLITE_CONSTRAINT (19) | Vi phạm constraint |
| SQLITE_MISMATCH (20) | Kiểu dữ liệu không phù hợp theo ngữ cảnh |

Một số extended constraint code:

| Extended code/name | Ý nghĩa |
|---|---|
| SQLITE_CONSTRAINT_CHECK (275) | CHECK constraint |
| SQLITE_CONSTRAINT_FOREIGNKEY (787) | Foreign key |
| SQLITE_CONSTRAINT_NOTNULL (1299) | NOT NULL |
| SQLITE_CONSTRAINT_PRIMARYKEY (1555) | Primary key |
| SQLITE_CONSTRAINT_UNIQUE (2067) | UNIQUE |

Giá trị số extended code ở đây theo các định nghĩa SQLite phổ biến; dùng constant của thư viện/driver thay vì hard-code nếu có.

### 7.2. Đọc lỗi trong Python sqlite3

Với Python phiên bản mới hỗ trợ thuộc tính lỗi của sqlite3 exception:

~~~python
import sqlite3

try:
    cursor.execute(
        "INSERT INTO customers(email) VALUES (?)",
        (email,),
    )
    connection.commit()
except sqlite3.IntegrityError as exc:
    print("message:", exc)
    print("sqlite_errorcode:", getattr(exc, "sqlite_errorcode", None))
    print("sqlite_errorname:", getattr(exc, "sqlite_errorname", None))
    connection.rollback()
    raise
except sqlite3.DatabaseError:
    connection.rollback()
    raise
~~~

`sqlite_errorcode` và `sqlite_errorname` có từ các bản Python mới (được bổ sung trong Python 3.11). Dùng getattr hoặc kiểm tra phiên bản khi hỗ trợ runtime cũ.

### 7.3. BUSY và LOCKED không giống nhau

`SQLITE_BUSY` thường chỉ database đang bị connection khác giữ lock khiến thao tác hiện tại không thể tiếp tục ngay. `SQLITE_LOCKED` liên quan đến xung đột lock khác, thường trong cùng connection/shared cache tùy ngữ cảnh.

Có thể cần retry có giới hạn với BUSY, nhưng phải hiểu transaction, timeout và journal mode. Không lặp vô hạn hoặc dùng sleep tùy tiện. Với LOCKED, có thể cần sửa cách dùng connection/cursor hoặc cấu trúc transaction thay vì chỉ retry.

## 8. Oracle: ORA error code, SQLCODE và SQLERRM

Oracle thường hiển thị lỗi với mã:

~~~text
ORA-00001: unique constraint (...) violated
~~~

Đây là **Oracle error number/code**, không phải SQLSTATE. Trong PL/SQL:

- `SQLCODE` trả mã lỗi số của exception hiện tại.
- `SQLERRM` trả thông báo lỗi.
- Có thể bắt exception cụ thể như DUP_VAL_ON_INDEX.

### 8.1. Một số ORA code thường gặp

| ORA code | Ý nghĩa |
|---|---|
| ORA-00001 | Vi phạm unique constraint/index |
| ORA-02291 | Không tìm thấy parent key cho foreign key |
| ORA-02292 | Không thể xóa parent vì còn child record |
| ORA-01400 | Không thể insert NULL vào cột NOT NULL |
| ORA-01403 | NO_DATA_FOUND trong PL/SQL |
| ORA-00904 | Invalid identifier |
| ORA-00942 | Table or view does not exist hoặc không truy cập được |
| ORA-01722 | Invalid number |
| ORA-00060 | Deadlock detected |
| ORA-08177 | Cannot serialize access for this transaction |

ORA-00942 có thể xuất hiện khi đối tượng không tồn tại hoặc người dùng không có quyền truy cập, tùy ngữ cảnh; không suy ra chắc chắn một nguyên nhân duy nhất chỉ từ message.

### 8.2. PL/SQL: SQLCODE và SQLERRM

~~~sql
DECLARE
    v_code NUMBER;
    v_message VARCHAR2(4000);
BEGIN
    INSERT INTO customers(email)
    VALUES ('existing@example.test');
EXCEPTION
    WHEN DUP_VAL_ON_INDEX THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        DBMS_OUTPUT.PUT_LINE('Code: ' || v_code);
        DBMS_OUTPUT.PUT_LINE('Message: ' || v_message);
        RAISE;
    WHEN OTHERS THEN
        v_code := SQLCODE;
        v_message := SQLERRM;
        DBMS_OUTPUT.PUT_LINE('Unexpected error: ' || v_code);
        RAISE;
END;
/
~~~

`DUP_VAL_ON_INDEX` là exception định danh cho lỗi duplicate. Khi bắt OTHERS, thường phải log và RAISE lại nếu không có cách xử lý cụ thể; nuốt lỗi có thể làm caller tưởng thao tác thành công.

### 8.3. Đọc stack và backtrace

Trong PL/SQL, có thể dùng DBMS_UTILITY.FORMAT_ERROR_STACK và FORMAT_ERROR_BACKTRACE để lấy stack/backtrace phục vụ chẩn đoán. Cần quản lý quyền và tránh trả toàn bộ thông tin nội bộ cho client.

## 9. So sánh nhanh giữa các hệ quản trị

| Hệ quản trị | Mã chính thường dùng | Cách đọc |
|---|---|---|
| PostgreSQL | SQLSTATE 5 ký tự | JDBC getSQLState, PG JDBC server error fields, PL/pgSQL GET STACKED DIAGNOSTICS |
| SQL Server | Native error number + severity + state | SqlException.Errors, ERROR_NUMBER/SEVERITY/STATE/MESSAGE |
| MySQL | Native error number + SQLSTATE | Connector attributes, client error output |
| SQLite | Primary/extended result code | sqlite3 exception attributes hoặc API result code |
| Oracle | ORA-nnnnn, SQLCODE/SQLERRM | PL/SQL exception, JDBC vendor code/message |

**Không được so sánh trực tiếp các mã khác hệ.** Ví dụ:

- PostgreSQL 23505.
- MySQL 1062.
- SQL Server 2627.
- SQLite SQLITE_CONSTRAINT_UNIQUE.
- Oracle ORA-00001.

Tất cả có thể liên quan đến duplicate/unique violation, nhưng chúng thuộc các hệ mã khác nhau và có chi tiết khác nhau. Ứng dụng đa DBMS nên tạo lớp ánh xạ lỗi theo driver/DBMS, không dùng một số nguyên chung rồi đoán ý nghĩa.

## 10. JDBC: đọc SQLException đúng cách

JDBC cung cấp các trường quan trọng:

- `getSQLState()`: SQLSTATE nếu driver cung cấp.
- `getErrorCode()`: vendor-specific error code.
- `getMessage()`: message.
- `getNextException()`: exception tiếp theo trong chuỗi.
- `getCause()`: nguyên nhân theo chuỗi Throwable.

### 10.1. In toàn bộ chuỗi SQLException

~~~java
try {
    statement.executeUpdate(sql);
} catch (SQLException ex) {
    for (SQLException current = ex;
         current != null;
         current = current.getNextException()) {

        System.err.println("SQLState: " + current.getSQLState());
        System.err.println("Vendor code: " + current.getErrorCode());
        System.err.println("Message: " + current.getMessage());
    }

    throw ex;
}
~~~

Một số driver có thể dùng cause chain, next-exception chain hoặc cả hai. Khi cần chẩn đoán đầy đủ, duyệt cả cấu trúc theo hướng dẫn của driver; tránh lặp vô hạn nếu driver có chuỗi bất thường.

### 10.2. Phân loại duplicate theo SQLSTATE

Ví dụ PostgreSQL qua JDBC:

~~~java
try {
    insertCustomer(email);
} catch (SQLException ex) {
    if ("23505".equals(ex.getSQLState())) {
        throw new DuplicateEmailException(email, ex);
    }
    throw ex;
}
~~~

Đây là ví dụ cho PostgreSQL. Không dùng SQLSTATE 23505 làm điều kiện duy nhất nếu ứng dụng còn chạy trên DBMS khác mà driver ánh xạ mã khác.

### 10.3. SQLTransientException và SQLIntegrityConstraintViolationException

JDBC có các lớp exception theo tính chất:

- `SQLTransientException`: lỗi có thể tạm thời, có thể thử lại theo điều kiện phù hợp.
- `SQLNonTransientException`: lỗi không có khả năng tự hết nếu chạy lại nguyên thao tác.
- `SQLRecoverableException`: có thể phục hồi sau khi đóng/tạo lại connection theo driver.
- `SQLIntegrityConstraintViolationException`: vi phạm integrity constraint.

Driver không nhất thiết ánh xạ mọi lỗi vào subclass giống nhau. Dùng SQLSTATE/native code và tài liệu driver cùng với type exception; đừng chỉ dựa vào class.

### 10.4. Lỗi batch

Khi dùng executeBatch(), JDBC có thể ném BatchUpdateException. Đọc:

- getUpdateCounts(): số hàng được cập nhật theo từng phần tử batch, tùy driver và trạng thái lỗi.
- getNextException(): lỗi tiếp theo.
- getSQLState()/getErrorCode(): mã lỗi.

Không giả định toàn bộ batch luôn thành công hoặc luôn rollback như nhau. Transaction mode, driver và DBMS quyết định hành vi thực tế. Nếu cần tính nguyên tử, chạy batch trong transaction và rollback khi thất bại.

## 11. Python: exception class, SQLSTATE và native code

DB-API định nghĩa một hệ exception tổng quát như:

- Warning
- Error
- InterfaceError
- DatabaseError
- DataError
- OperationalError
- IntegrityError
- InternalError
- ProgrammingError
- NotSupportedError

Driver cụ thể có thể bổ sung thuộc tính SQLSTATE/native code.

### 11.1. Bắt exception theo nhóm

~~~python
try:
    cursor.execute(
        "INSERT INTO customers(email) VALUES (?)",
        (email,),
    )
    connection.commit()
except sqlite3.IntegrityError:
    connection.rollback()
    # Xử lý conflict/constraint theo nghiệp vụ.
    raise
except sqlite3.OperationalError:
    connection.rollback()
    # Điều tra lock, connection hoặc lỗi vận hành.
    raise
except sqlite3.DatabaseError:
    connection.rollback()
    raise
~~~

Đây là ví dụ SQLite. Với psycopg hoặc mysql-connector, dùng exception class của driver tương ứng.

### 11.2. psycopg: lấy SQLSTATE và diagnostic

Với psycopg:

~~~python
try:
    cursor.execute(
        "INSERT INTO customers(email) VALUES (%s)",
        (email,),
    )
except Exception as exc:
    sqlstate = getattr(exc, "sqlstate", None)
    diag = getattr(exc, "diag", None)

    print("SQLSTATE:", sqlstate)
    if diag is not None:
        print("message:", getattr(diag, "message_primary", None))
        print("detail:", getattr(diag, "message_detail", None))
        print("hint:", getattr(diag, "message_hint", None))
        print("schema:", getattr(diag, "schema_name", None))
        print("table:", getattr(diag, "table_name", None))
        print("column:", getattr(diag, "column_name", None))
        print("constraint:", getattr(diag, "constraint_name", None))
    raise
~~~

Ví dụ minh họa cách truy cập diagnostic fields của psycopg. Tên thuộc tính/API có thể khác giữa psycopg phiên bản 2 và 3; kiểm tra tài liệu driver thực tế. Trong production, dùng logger có cấu trúc thay vì print.

### 11.3. Không bắt Exception quá rộng rồi nuốt lỗi

Không nên:

~~~python
try:
    cursor.execute(sql, params)
except Exception:
    return []
~~~

Cách này biến lỗi cú pháp, lỗi quyền, mất kết nối và lỗi constraint thành “không có dữ liệu”. Nó che lỗi thật và làm kết quả API sai.

Chỉ bắt nhóm lỗi mà ứng dụng có cách xử lý cụ thể. Các lỗi chưa hiểu phải được ném lại hoặc chuyển qua tầng xử lý lỗi chung.

## 12. Phân loại lỗi: sửa dữ liệu, sửa code, retry hay dừng?

Không phải mọi lỗi database đều nên retry. Phân loại dựa trên SQLSTATE, vendor code, transaction state và ngữ cảnh nghiệp vụ.

### 12.1. Lỗi đầu vào hoặc dữ liệu — thường không retry

Ví dụ:

- Giá trị không chuyển được sang integer/date.
- Chuỗi vượt giới hạn.
- NOT NULL hoặc CHECK bị vi phạm do input.
- Foreign key không tồn tại.

Hành động:

- Kiểm tra và validate input.
- Trả lỗi 4xx phù hợp nếu xuất phát từ request.
- Không lặp cùng câu lệnh với cùng dữ liệu.
- Giữ thông tin lỗi đủ để điều tra, nhưng không tiết lộ schema nội bộ cho client.

### 12.2. Lỗi constraint — xử lý theo nghiệp vụ

Duplicate có thể là:

- Người dùng gửi dữ liệu trùng và cần conflict.
- Retry cùng request sau timeout.
- Hai request đồng thời tạo cùng tài nguyên.
- Lỗi thiết kế khóa hoặc idempotency.

Không tự động coi mọi duplicate là thành công. Nếu nghiệp vụ cho phép create-or-update, dùng UPSERT với conflict target rõ ràng. Nếu phải từ chối, ánh xạ thành conflict.

### 12.3. Lỗi cú pháp/schema/quyền — sửa cấu hình hoặc code

Ví dụ:

- Syntax error.
- Undefined table/column.
- Permission denied.
- Feature not supported.

Retry cùng SQL thường không giải quyết được. Kiểm tra migration, schema search path, quyền role, phiên bản DBMS và SQL dialect.

### 12.4. Lỗi transaction tạm thời — có thể retry toàn transaction

Ví dụ PostgreSQL:

- 40001 serialization_failure.
- 40P01 deadlock_detected.

SQL Server:

- 1205 deadlock victim.

MySQL:

- 1213 deadlock.

Hành động:

1. Rollback transaction bị lỗi.
2. Đợi backoff có jitter.
3. Bắt đầu transaction mới.
4. Chạy lại toàn bộ đơn vị công việc.
5. Giới hạn số lần retry và ghi metric.

Không retry vô hạn. Nếu cùng một transaction liên tục deadlock, điều tra thứ tự lấy lock, index và phạm vi transaction.

### 12.5. Lock timeout và lock conflict

Một lock timeout có thể retry, nhưng cũng có thể là dấu hiệu transaction khác giữ lock quá lâu. Kiểm tra:

- Transaction nào đang giữ lock?
- Có transaction mở lâu không?
- Các luồng có lấy lock theo thứ tự khác nhau không?
- Có index phù hợp cho điều kiện UPDATE/DELETE không?
- Timeout có quá ngắn so với workload không?

Retry không giới hạn có thể làm hàng đợi càng dài.

### 12.6. Lỗi kết nối và kết quả commit không rõ

Nếu connection mất trong lúc COMMIT, ứng dụng có thể không biết transaction đã commit hay chưa. Không gửi lại thao tác ghi một cách mù quáng.

Các giải pháp:

- Idempotency key có UNIQUE constraint.
- Ghi nhận request/event ID trong cùng transaction với dữ liệu.
- Transactional outbox cho side effect.
- Truy vấn lại trạng thái theo khóa nghiệp vụ trước khi retry.
- Thiết kế API cho phép client retry an toàn.

### 12.7. Lỗi tài nguyên và lỗi hệ thống

Thiếu bộ nhớ, hết disk, lỗi I/O, database shutdown hoặc corruption cần phân loại theo mức độ. Một số lỗi tạm thời có thể tự hết; một số cần can thiệp vận hành. Không biến tất cả thành retry thông thường.

## 13. Transaction state sau lỗi

Đọc SQLSTATE thôi chưa đủ; phải biết transaction còn dùng được không.

### 13.1. PostgreSQL

Sau statement error trong transaction, transaction thường chuyển sang trạng thái aborted. Các lệnh tiếp theo thất bại cho đến khi ROLLBACK hoặc ROLLBACK TO SAVEPOINT.

### 13.2. SQL Server

Sau lỗi, transaction có thể còn commit được, cần rollback hoặc ở trạng thái không thể commit. Dùng XACT_STATE() trong T-SQL để xác định:

- 1: transaction active và có thể commit/rollback.
- -1: transaction uncommittable, chỉ có thể rollback.
- 0: không có user transaction đang hoạt động.

Ví dụ:

~~~sql
BEGIN TRY
    BEGIN TRANSACTION;

    -- Các thao tác database.

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
~~~

### 13.3. MySQL

Hành vi transaction phụ thuộc storage engine và loại lỗi. Với InnoDB, nhiều lỗi statement chỉ rollback statement, trong khi deadlock có thể rollback toàn transaction; lock wait timeout thường có hành vi khác và còn phụ thuộc cấu hình. Không giả định mọi lỗi đều rollback toàn transaction hoặc không rollback gì.

### 13.4. SQLite

Một số lỗi có thể rollback statement, một số có thể khiến transaction hoặc connection cần xử lý khác. BUSY/LOCKED và lỗi I/O/corruption không nên được gom thành một chính sách chung.

### 13.5. Quy tắc ứng dụng

Sau lỗi:

1. Đọc trạng thái transaction theo driver/DBMS.
2. Rollback khi transaction không thể tiếp tục hoặc nghiệp vụ yêu cầu hủy.
3. Chỉ retry sau khi đã kết thúc transaction lỗi và bắt đầu transaction mới.
4. Không trả connection đang ở trạng thái không xác định về pool.
5. Nếu lỗi xảy ra lúc commit và kết quả không rõ, kiểm tra idempotency trước khi gửi lại.

## 14. Logging lỗi SQL an toàn

Log cần đủ dữ liệu để điều tra, nhưng không được làm lộ bí mật hoặc dữ liệu cá nhân.

### 14.1. Trường nên ghi

- Timestamp và correlation/request ID.
- Tên service, endpoint hoặc job.
- DBMS, driver và phiên bản có liên quan.
- Operation name hoặc query fingerprint.
- SQLSTATE và vendor code.
- Exception class.
- Transaction/retry attempt.
- Tên constraint/table/column nếu chính sách cho phép.
- Duration và connection pool state khi hữu ích.

### 14.2. Trường cần cân nhắc che hoặc loại bỏ

- Password, access token, API key.
- Connection string có credential.
- Nội dung PII hoặc dữ liệu khách hàng.
- Toàn bộ bind parameters nếu chứa thông tin nhạy cảm.
- Raw SQL có literal nhúng trực tiếp.
- Detail message có giá trị email, số tài khoản hoặc định danh.

Không phải message/detail nào cũng an toàn để gửi vào log tập trung. Dùng redaction theo loại dữ liệu và quyền truy cập log.

### 14.3. Log có cấu trúc

Ví dụ JSON log đã lược bỏ giá trị nhạy cảm:

~~~json
{
  "event": "database_query_failed",
  "request_id": "req-8f31",
  "operation": "create_customer",
  "dbms": "PostgreSQL",
  "sqlstate": "23505",
  "constraint": "customers_email_key",
  "retryable": false,
  "attempt": 1
}
~~~

Không đưa email thật hoặc toàn bộ exception detail vào log này nếu không cần thiết. Nếu cần lưu detail cho điều tra, áp dụng quyền truy cập và retention phù hợp.

### 14.4. Không ghi message rồi bỏ mã lỗi

Log chỉ có:

~~~text
Database error: duplicate key
~~~

không đủ để phân biệt unique, foreign key hoặc lỗi khác. Ghi SQLSTATE/vendor code cùng message đã kiểm soát.

## 15. Không trả lỗi nội bộ nguyên văn cho người dùng cuối

Database message có thể tiết lộ:

- Tên bảng, schema, cột, index và constraint.
- Một phần giá trị dữ liệu.
- Cấu trúc truy vấn và đường dẫn nội bộ.
- Thông tin máy chủ, user hoặc cấu hình.

API nên ánh xạ lỗi thành thông điệp theo hợp đồng sản phẩm:

| Loại lỗi | Phản hồi API có thể phù hợp |
|---|---|
| Input không hợp lệ | 400 hoặc 422 |
| Tài nguyên không tồn tại | 404 |
| Duplicate/conflict nghiệp vụ | 409 |
| Không xác thực/không có quyền | 401/403 theo ngữ cảnh |
| Lỗi tạm thời/DB unavailable | 503 hoặc lỗi hệ thống phù hợp |
| Lỗi SQL nội bộ bất ngờ | 500 với request ID |

Không ánh xạ máy móc mọi lỗi class 23 thành 409 nếu có lỗi do bug hoặc dữ liệu nội bộ. Cần xét operation và constraint cụ thể.

## 16. Kiểm thử lỗi có chủ ý

Một bộ kiểm thử database tốt phải xác minh cả thành công lẫn lỗi mong đợi.

### 16.1. Tạo fixture constraint

PostgreSQL:

~~~sql
CREATE TABLE error_lab_customers (
    customer_id INTEGER PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    age INTEGER CHECK (age >= 18)
);

CREATE TABLE error_lab_orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES error_lab_customers(customer_id)
);
~~~

### 16.2. Test duplicate key

~~~sql
INSERT INTO error_lab_customers VALUES (1, 'a@example.test', 25);
INSERT INTO error_lab_customers VALUES (2, 'a@example.test', 30);
~~~

Lệnh thứ hai gây unique violation. Kiểm thử xác minh SQLSTATE 23505 và constraint tương ứng.

### 16.3. Test foreign key

~~~sql
INSERT INTO error_lab_orders VALUES (10, 999);
~~~

Nếu customer 999 không tồn tại, PostgreSQL trả foreign_key_violation (23503).

### 16.4. Test NOT NULL và CHECK

~~~sql
INSERT INTO error_lab_customers(customer_id, email, age)
VALUES (3, NULL, 25);

INSERT INTO error_lab_customers(customer_id, email, age)
VALUES (4, 'b@example.test', 12);
~~~

Lệnh đầu vi phạm NOT NULL (23502); lệnh thứ hai vi phạm CHECK (23514).

### 16.5. Test lỗi chuyển kiểu

~~~sql
SELECT 'abc'::INTEGER;
~~~

PostgreSQL trả invalid_text_representation (22P02).

### 16.6. Test lỗi cú pháp

~~~sql
SELEC 1;
~~~

PostgreSQL trả syntax_error (42601). Không nên để test suite phụ thuộc chính xác toàn bộ message; assert SQLSTATE và điều kiện cần thiết.

### 16.7. Test lỗi quyền

Tạo role test không có quyền SELECT trên bảng rồi chạy truy vấn. Xác minh permission denied (42501) trong PostgreSQL. Test quyền nên chạy trong database test có thể tạo role hoặc fixture quyền được kiểm soát.

## 17. Viết test tự động cho lỗi

### 17.1. Assert SQLSTATE trong Java

~~~java
SQLException error = assertThrows(
    SQLException.class,
    () -> repository.insertCustomer("a@example.test")
);

assertEquals("23505", error.getSQLState());
~~~

Ví dụ này dành cho PostgreSQL JDBC. Với driver khác, mã SQLSTATE hoặc exception subclass có thể khác.

### 17.2. Assert vendor code và SQLSTATE riêng

~~~java
assertEquals("23000", error.getSQLState());
assertEquals(1062, error.getErrorCode());
~~~

Ví dụ cho MySQL driver có mapping tương ứng. Không tái sử dụng hai assertion này cho PostgreSQL.

### 17.3. Test Python exception

~~~python
with pytest.raises(sqlite3.IntegrityError) as captured:
    cursor.execute(
        "INSERT INTO customers(email) VALUES (?)",
        ("a@example.test",),
    )

error = captured.value
assert error.sqlite_errorname in {
    "SQLITE_CONSTRAINT_UNIQUE",
    "SQLITE_CONSTRAINT_PRIMARYKEY",
}
~~~

Ví dụ giả định fixture đã có email hoặc khóa trùng và Python runtime cung cấp sqlite_errorname. Điều chỉnh expected code theo constraint được kích hoạt.

### 17.4. Không assert toàn bộ message nếu không cần

Một test kiểu:

~~~java
assertEquals(
    "duplicate key value violates unique constraint ...",
    error.getMessage()
);
~~~

thường quá mong manh. Hãy assert SQLSTATE/vendor code, exception type, tên constraint nếu driver cung cấp riêng và trạng thái dữ liệu sau lỗi.

### 17.5. Kiểm tra transaction sau lỗi

Test nên xác minh:

- Transaction có bị aborted không?
- Connection có cần rollback trước khi dùng tiếp không?
- Savepoint có phục hồi được transaction không?
- Connection được trả về pool trong trạng thái sạch không?
- Retry có tạo duplicate side effect không?

## 18. Retry policy: giới hạn và idempotency

Retry chỉ phù hợp khi lỗi có khả năng tạm thời và thao tác có thể lặp an toàn.

### 18.1. Backoff có jitter

Một chính sách minh họa:

~~~text
attempt 1: chạy ngay
attempt 2: đợi khoảng 100 ms + jitter
attempt 3: đợi khoảng 250 ms + jitter
attempt 4: đợi khoảng 500 ms + jitter
Sau đó dừng và báo lỗi
~~~

Đây chỉ là ví dụ, không phải giá trị phù hợp cho mọi workload. Chọn giới hạn theo latency budget, thời gian lock, timeout và mức độ quan trọng của thao tác.

### 18.2. Retry toàn transaction

Nếu transaction bị serialization failure/deadlock, rollback transaction và chạy lại toàn bộ logic đọc-tính-ghi. Chỉ chạy lại câu lệnh cuối có thể dùng dữ liệu đã đọc từ snapshot cũ và phá vỡ tính đúng đắn.

### 18.3. Idempotency key

Ví dụ bảng ghi nhận request:

~~~sql
CREATE TABLE processed_requests (
    request_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Trong cùng transaction, ứng dụng ghi request_id vào bảng này và ghi dữ liệu nghiệp vụ. UNIQUE request_id ngăn cùng một yêu cầu được áp dụng nhiều lần, nếu luồng xử lý được thiết kế đúng.

Idempotency key không tự giải quyết side effect ngoài transaction; cần outbox hoặc cơ chế phối hợp tương ứng.

### 18.4. Không retry lỗi vĩnh viễn

Không retry vô hạn với:

- Syntax error.
- Undefined table/column.
- Invalid input.
- NOT NULL/CHECK/FOREIGN KEY violation do dữ liệu.
- Permission denied.
- Feature not supported.

Retry chỉ làm tăng tải và làm log nhiễu.

## 19. Chẩn đoán lỗi trong production

Khi một lỗi xuất hiện ở production:

1. Lấy request/correlation ID.
2. Tìm log có SQLSTATE và vendor code.
3. Xác định DBMS, phiên bản và driver.
4. Xác định operation/query fingerprint.
5. Xem transaction và retry attempt.
6. Kiểm tra schema migration, constraint và quyền.
7. Kiểm tra lock, connection pool và tài nguyên nếu thuộc nhóm vận hành.
8. So sánh lỗi với thời điểm deploy hoặc thay đổi dữ liệu.
9. Tái hiện trong môi trường test với fixture tối thiểu.
10. Viết regression test theo mã lỗi và trạng thái dữ liệu.

### 19.1. Khi thấy duplicate violation

Kiểm tra:

- Request có được gửi hai lần?
- Client có retry sau timeout?
- Có hai worker xử lý cùng event?
- Unique key có đúng phạm vi tenant?
- Có cần UPSERT hoặc idempotency key?
- Một migration mới có thêm constraint không?

### 19.2. Khi thấy foreign key violation

Kiểm tra:

- Hàng cha đã được tạo chưa?
- ID có đúng tenant/schema không?
- Thứ tự ghi parent-child có đúng không?
- Có transaction khác xóa parent đồng thời không?
- FK có tham chiếu đúng cột/đúng schema không?

### 19.3. Khi thấy undefined table/column

Kiểm tra:

- Migration đã chạy ở môi trường này chưa?
- Tên schema và search_path có đúng không?
- Identifier có phân biệt hoa/thường do quote không?
- Ứng dụng đang kết nối đúng database không?
- Code mới có chạy trước migration không?

### 19.4. Khi thấy deadlock hoặc lock timeout

Kiểm tra:

- Transaction giữ lock trong bao lâu?
- Các luồng lấy lock theo thứ tự nào?
- Có query thiếu index khiến khóa nhiều hàng hơn không?
- Có transaction mở lâu do chờ network/user input không?
- Có batch update/delete quá lớn không?

## 20. Bảng quyết định xử lý lỗi

| Nhóm lỗi | Hành động đầu tiên | Retry? |
|---|---|---|
| Syntax/undefined object | Sửa SQL, schema hoặc migration | Không |
| Invalid input/conversion | Validate và sửa dữ liệu | Không |
| Unique/FK/NOT NULL/CHECK | Xử lý conflict hoặc dữ liệu | Thường không |
| Serialization failure | Rollback và chạy lại transaction | Có, có giới hạn |
| Deadlock | Rollback, xem lock order, retry transaction | Có, có giới hạn |
| Lock timeout/BUSY | Kiểm tra lock và timeout; backoff nếu phù hợp | Có điều kiện |
| Connection lost | Kiểm tra trạng thái commit và idempotency | Không mù quáng |
| Permission denied | Sửa quyền hoặc danh tính kết nối | Không |
| Resource/system failure | Kiểm tra sức khỏe DB và vận hành | Theo nguyên nhân |

## 21. Checklist đọc một lỗi SQL

Khi nhận lỗi, hãy ghi lại:

- DBMS, version và driver version.
- Operation name và request ID.
- SQLSTATE nếu có.
- Native/vendor error number nếu có.
- Exception type/class.
- Severity/state/line/procedure nếu DBMS cung cấp.
- Message, detail, hint và constraint/object fields theo quyền log.
- Transaction state và connection state.
- Retry attempt và kết quả rollback.
- Hành động đã thực hiện và trạng thái dữ liệu cuối.

Khi viết code:

- Phân loại bằng mã có cấu trúc, không parse message.
- Xử lý từng nhóm lỗi có chủ đích.
- Không nuốt exception không hiểu.
- Rollback transaction khi cần.
- Không trả message database thô cho client.
- Redact bind values và thông tin xác thực khỏi log.
- Retry chỉ khi lỗi tạm thời và thao tác idempotent hoặc được bảo vệ.
- Test lỗi constraint, kiểu dữ liệu, cú pháp, quyền, lock và kết nối trong môi trường phù hợp.

## 22. Bài tập thực hành có đáp án

### Bài 1 — SQLSTATE có bao nhiêu ký tự?

**Đáp án:** Thông thường 5 ký tự; hai ký tự đầu là class, ba ký tự sau là subclass.

### Bài 2 — Class 23 nói về điều gì?

**Đáp án:** Integrity constraint violation, ví dụ UNIQUE, PRIMARY KEY, FOREIGN KEY, NOT NULL hoặc CHECK.

### Bài 3 — PostgreSQL 23505

**Đáp án:** unique_violation.

### Bài 4 — PostgreSQL 23503

**Đáp án:** foreign_key_violation.

### Bài 5 — PostgreSQL 23502

**Đáp án:** not_null_violation.

### Bài 6 — PostgreSQL 22P02

**Đáp án:** invalid_text_representation, ví dụ chuỗi abc không chuyển được sang integer.

### Bài 7 — PostgreSQL 42601

**Đáp án:** syntax_error.

### Bài 8 — PostgreSQL 40001

**Đáp án:** serialization_failure; thường cần rollback và retry toàn transaction theo chính sách.

### Bài 9 — PostgreSQL 40P01

**Đáp án:** deadlock_detected.

### Bài 10 — SQL Server 2627

**Đáp án:** Vi phạm PRIMARY KEY hoặc UNIQUE constraint.

### Bài 11 — SQL Server State có phải SQLSTATE?

**Đáp án:** Không. State là trường phụ trong thông tin lỗi SQL Server; SQLSTATE là mã trạng thái SQL 5 ký tự.

### Bài 12 — SQL Server 1205

**Đáp án:** Transaction bị chọn làm deadlock victim.

### Bài 13 — MySQL 1062

**Đáp án:** Duplicate entry; thường đi kèm SQLSTATE 23000.

### Bài 14 — MySQL 1213

**Đáp án:** Deadlock; thường đi kèm SQLSTATE 40001.

### Bài 15 — MySQL 1146

**Đáp án:** Table doesn't exist, thường SQLSTATE 42S02.

### Bài 16 — SQLite SQLITE_CONSTRAINT_UNIQUE

**Đáp án:** Vi phạm UNIQUE constraint; là extended result code thuộc nhóm constraint.

### Bài 17 — SQLite BUSY

**Đáp án:** Database bận, có thể cần chờ/retry có giới hạn tùy transaction và cấu hình.

### Bài 18 — Oracle ORA-00001

**Đáp án:** Vi phạm unique constraint/index.

### Bài 19 — Oracle ORA-01403

**Đáp án:** NO_DATA_FOUND trong PL/SQL.

### Bài 20 — Oracle SQLCODE và SQLERRM

**Đáp án:** SQLCODE trả mã lỗi số; SQLERRM trả thông báo lỗi của exception hiện tại.

### Bài 21 — Vì sao không parse message?

**Đáp án:** Message có thể thay đổi theo version, driver, locale và đối tượng; mã có cấu trúc ổn định hơn để phân loại.

### Bài 22 — Vendor code và SQLSTATE khác gì?

**Đáp án:** SQLSTATE là mã trạng thái theo cấu trúc SQL/driver; vendor code là mã riêng của DBMS/driver. Không so sánh trực tiếp hai hệ mã.

### Bài 23 — JDBC lấy SQLSTATE ở đâu?

**Đáp án:** SQLException.getSQLState(); native code qua getErrorCode(); exception tiếp theo qua getNextException().

### Bài 24 — Một SQLException có thể có nhiều lỗi không?

**Đáp án:** Có. Duyệt getNextException() và xem cause chain theo driver.

### Bài 25 — Python DB-API có một thuộc tính SQLSTATE chung cho mọi driver không?

**Đáp án:** Không. DB-API định nghĩa nhóm exception; thuộc tính SQLSTATE/native code phụ thuộc driver.

### Bài 26 — Sau PostgreSQL statement error trong transaction thì sao?

**Đáp án:** Transaction thường chuyển sang trạng thái aborted; cần ROLLBACK hoặc ROLLBACK TO SAVEPOINT trước khi tiếp tục.

### Bài 27 — Deadlock nên retry statement hay transaction?

**Đáp án:** Rollback rồi chạy lại toàn bộ transaction với giới hạn và backoff, vì các lần đọc/tính toán trước đó có thể không còn hợp lệ.

### Bài 28 — Connection mất lúc COMMIT

**Đáp án:** Kết quả commit có thể không rõ. Kiểm tra trạng thái theo idempotency key trước khi gửi lại thao tác ghi.

### Bài 29 — Duplicate có luôn là lỗi 500 không?

**Đáp án:** Không. Nếu là conflict nghiệp vụ, API có thể trả 409 hoặc kết quả phù hợp. Cần xác định constraint và operation.

### Bài 30 — Có nên trả nguyên SQL message cho client?

**Đáp án:** Không. Message có thể tiết lộ schema, dữ liệu hoặc cấu trúc nội bộ. Trả thông báo an toàn kèm request ID.

## 23. Bảng ghi nhớ nhanh

| Câu hỏi | Cách đọc |
|---|---|
| SQLSTATE là gì? | Mã trạng thái 5 ký tự; 2 ký tự class + 3 ký tự subclass |
| Class 22 | Data exception |
| Class 23 | Integrity constraint violation |
| Class 40 | Transaction rollback |
| Class 42 | Syntax/access rule violation |
| PostgreSQL duplicate | 23505 |
| PostgreSQL foreign key | 23503 |
| PostgreSQL serialization | 40001 |
| SQL Server duplicate | 2601 hoặc 2627 |
| SQL Server deadlock | 1205 |
| MySQL duplicate | Native 1062, SQLSTATE thường 23000 |
| MySQL deadlock | Native 1213, SQLSTATE thường 40001 |
| SQLite constraint | SQLITE_CONSTRAINT và extended code |
| Oracle duplicate | ORA-00001 |
| JDBC SQLSTATE | SQLException.getSQLState() |
| JDBC vendor code | SQLException.getErrorCode() |
| PL/pgSQL diagnostics | GET STACKED DIAGNOSTICS |
| T-SQL diagnostics | ERROR_NUMBER(), ERROR_MESSAGE(), XACT_STATE() |
| PL/SQL diagnostics | SQLCODE, SQLERRM, error stack/backtrace |
| Retry | Chỉ lỗi tạm thời, rollback và chạy lại transaction khi an toàn |
| Logging | Mã có cấu trúc, request ID, redaction dữ liệu nhạy cảm |

## Kết luận

**SQLSTATE, vendor error code và message là ba loại thông tin khác nhau, mỗi loại có vai trò riêng khi đọc lỗi SQL.** SQLSTATE giúp phân loại theo class/subclass; mã native cung cấp chi tiết theo DBMS; message, detail, hint và vị trí giúp con người tìm nguyên nhân.

Khi xử lý lỗi:

- **Đọc SQLSTATE và vendor code trước**, không dựa vào việc tìm từ trong message.
- **Dùng đúng hệ mã của DBMS**: PostgreSQL SQLSTATE, SQL Server error number/state/severity, MySQL native code + SQLSTATE, SQLite result code và Oracle ORA/SQLCODE.
- **Đọc cả transaction state và exception chain**; một statement error có thể khiến transaction không thể tiếp tục.
- **Không retry lỗi dữ liệu, cú pháp hoặc quyền** bằng cách chạy lại nguyên câu lệnh.
- **Retry transaction tạm thời có giới hạn** sau rollback; bảo vệ thao tác ghi bằng idempotency khi kết quả commit không rõ.
- **Ghi log có cấu trúc và che dữ liệu nhạy cảm**; trả thông báo phù hợp cho client thay vì message database nguyên văn.
- **Kiểm thử lỗi có chủ ý** và assert mã lỗi, trạng thái transaction cùng dữ liệu cuối thay vì phụ thuộc toàn bộ message.

Khi biết đọc mã lỗi theo đúng hệ quản trị và đặt nó trong ngữ cảnh transaction, việc gỡ lỗi sẽ chuyển từ phỏng đoán dựa trên một dòng message thành quy trình có thể kiểm chứng, tự động hóa và vận hành an toàn.
