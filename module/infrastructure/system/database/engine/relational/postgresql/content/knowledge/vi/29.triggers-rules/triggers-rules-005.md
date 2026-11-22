# Điều kiện WHEN và giới hạn các cột kích hoạt

Trong PostgreSQL, một trigger không nhất thiết phải thực thi hàm ở mọi sự kiện INSERT, UPDATE hoặc DELETE. Bạn có thể khai báo **điều kiện `WHEN</BT>** để giới hạn những hàng đủ điều kiện chạy trigger, hoặc dùng **`UPDATE OF</BT>** để chỉ quan tâm đến những câu UPDATE có nhắc tới các cột cụ thể. Hai cơ chế này rất hữu ích cho audit log, cập nhật dữ liệu dẫn xuất, phát sự kiện theo trạng thái, kiểm tra nghiệp vụ và giảm chi phí của những trigger được gọi thường xuyên.

Tuy vậy, điểm cốt lõi của bài là: **`UPDATE OF column_name</BT> không có nghĩa “giá trị của cột đã đổi”**. Nó chủ yếu kiểm tra **cột có được nêu là mục tiêu trong danh sách SET của câu UPDATE không**. Ngược lại, điều kiện `WHEN (OLD.column IS DISTINCT FROM NEW.column)</BT> có thể kiểm tra **giá trị cũ và mới thật sự khác nhau**, kể cả khi một trong hai là NULL.

Ví dụ:

~~~sql
CREATE TRIGGER orders_status_changed
AFTER UPDATE OF status
ON orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

Trigger này kết hợp hai bộ lọc: câu UPDATE phải nhắm tới cột `status</BT> và giá trị status của hàng phải thật sự khác trước. Nếu bỏ `WHEN</BT>, câu `UPDATE orders SET status = status</BT> vẫn có thể khiến trigger chạy dù giá trị giữ nguyên. Nếu bỏ `UPDATE OF status</BT>, trigger có thể phát hiện thay đổi status do một BEFORE trigger gây ra ngay cả khi câu UPDATE ban đầu không nhắc tới status.

Bài học thuộc chương **Trigger và luật** trong module **Database Engine Relational PostgreSQL**. Nội dung đi từ cú pháp `CREATE TRIGGER</BT>, `WHEN</BT>, `UPDATE OF</BT>, `OLD</BT>/`NEW</BT>, NULL semantics, thời điểm BEFORE/AFTER, đến các tình huống kết hợp trigger, giới hạn của statement-level trigger, generated columns, transition tables, hiệu năng, bảo mật và một bài lab PostgreSQL có thể thực hành từng bước.

## 1. Trigger nằm ở đâu trong quá trình xử lý dữ liệu?

Một cách nhìn đơn giản:

~~~text
Client gửi INSERT / UPDATE / DELETE
                   |
                   v
          PostgreSQL xác định rows
                   |
                   v
         BEFORE statement triggers
                   |
                   v
       Với từng row cần xử lý:
         BEFORE row triggers
          [WHEN được xét]
             |
             v
       Thực hiện row operation
             |
             v
         AFTER row triggers
          [WHEN được xét]
          [xếp sự kiện để chạy]
                   |
                   v
          AFTER statement triggers
                   |
                   v
      Statement hoàn tất / transaction
~~~

Sơ đồ chỉ trình bày ý tưởng; thứ tự thực thi chi tiết, các transition tables, foreign-key actions và những trường hợp như `INSERT ... ON CONFLICT</BT>, partition row movement hoặc `MERGE</BT> có thêm quy tắc. Không lấy sơ đồ này thay tài liệu thực thi chính xác của từng phiên bản PostgreSQL.

### 1.1. Trigger không phải câu WHERE của UPDATE

Một trigger `AFTER UPDATE ... WHEN (...)</BT> không quyết định hàng có được UPDATE hay không; nó quyết định **có thực thi hành động trigger cho hàng đó không**. Câu UPDATE chính vẫn được thực thi theo điều kiện WHERE và các ràng buộc khác.

### 1.2. Trigger function là gì?

PostgreSQL dùng function trả về `trigger</BT> để xử lý sự kiện, thường khai báo bằng `LANGUAGE plpgsql</BT>. Function có thể đọc các biến như `NEW</BT>, `OLD</BT>, `TG_OP</BT>, `TG_NAME</BT>.

### 1.3. Vì sao cần giới hạn số lần gọi?

Một bảng có hàng triệu rows, nếu mỗi UPDATE gọi hàm audit quá mức, database có thể tốn CPU, WAL, index I/O và storage không cần thiết. `UPDATE OF</BT> và `WHEN</BT> cho phép mô tả điều kiện kích hoạt **ngay trong định nghĩa trigger**, tránh một phần việc vô ích.

## 2. Cú pháp CREATE TRIGGER liên quan bài học

Mẫu khái quát:

~~~sql
CREATE TRIGGER trigger_name
{ BEFORE | AFTER | INSTEAD OF }
{ INSERT | UPDATE | DELETE | TRUNCATE }
ON table_name
FOR EACH { ROW | STATEMENT }
WHEN (boolean_condition)
EXECUTE FUNCTION trigger_function();
~~~

Đây là biểu diễn rút gọn để giải thích, **không phải toàn bộ văn phạm `CREATE TRIGGER</BT>**. Trong SQL thật, bạn chọn timing/event/level hợp lệ. Điều kiện `WHEN</BT> có các giới hạn theo timing và level; không được tùy ý gắn vào mọi tổ hợp.

Cú pháp chọn cột khi UPDATE:

~~~sql
CREATE TRIGGER trigger_name
AFTER UPDATE OF status, amount
ON table_name
FOR EACH ROW
EXECUTE FUNCTION trigger_function();
~~~

Có thể kết hợp:

~~~sql
CREATE TRIGGER trigger_name
AFTER UPDATE OF status
ON table_name
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_function();
~~~

### 2.1. FOR EACH ROW

Trigger xét từng hàng chịu tác động của DML. Đây là ngữ cảnh thường dùng `OLD.column</BT> và `NEW.column</BT> trong `WHEN</BT>.

### 2.2. FOR EACH STATEMENT

Trigger chạy theo **statement event**, không theo số hàng thực sự bị ảnh hưởng. Một UPDATE không sửa hàng nào vẫn có thể kích hoạt statement-level trigger tương ứng. Không xem statement-level trigger như một phép lọc row bằng `OLD</BT>/`NEW</BT>.

### 2.3. BEFORE và AFTER

- **BEFORE row trigger** chạy trước khi row operation hoàn thành, có thể thay đổi `NEW</BT> hoặc ngăn một row operation theo cơ chế `RETURN NULL</BT>.
- **AFTER row trigger** quan sát kết quả row operation đã diễn ra theo semantics thực thi và phù hợp để ghi audit hoặc các xử lý hậu cập nhật.
- **INSTEAD OF trigger** thường gắn với view và có quy tắc riêng; không được coi là AFTER/BEFORE row trigger trên bảng vật lý.

## 3. WHEN là gì?

`WHEN</BT> là một **biểu thức Boolean** đặt ở định nghĩa trigger. PostgreSQL dùng kết quả điều kiện để quyết định có gọi trigger function đối với sự kiện/hàng tương ứng hay không.

~~~sql
CREATE TRIGGER accounts_low_balance
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION log_low_balance();
~~~

Nếu điều kiện không TRUE, function không được gọi cho hàng đó.

### 3.1. WHEN khác IF trong trigger function

Có hai cách diễn đạt gần nhau:

~~~sql
-- Cách A: kiểm tra ở định nghĩa trigger
CREATE TRIGGER example_a
AFTER UPDATE ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION do_work();
~~~

~~~sql
-- Cách B: function tự kiểm tra
CREATE FUNCTION do_work()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.balance < 0 THEN
        -- Xử lý...
    END IF;
    RETURN NEW;
END;
$$;
~~~

Cả hai có thể bảo vệ cùng nhánh logic nếu function và điều kiện được thiết kế tương ứng, nhưng **chi phí và thời điểm xét khác nhau**, nhất là AFTER row triggers.

### 3.2. WHEN không cần gọi function để kiểm tra FALSE

Nếu điều kiện WHEN không TRUE, PostgreSQL tránh lời gọi trigger function cho hàng đó. Với AFTER row triggers, điều này còn có thể tránh ghi sự kiện trigger vào hàng đợi xử lý ở cuối statement.

### 3.3. Không phải điều kiện SELECT thông thường

Biểu thức WHEN bị giới hạn bởi ngữ cảnh trigger; ví dụ **không được dùng subquery trực tiếp** trong WHEN. Không viết `WHEN (EXISTS (SELECT ...))</BT> và kỳ vọng PostgreSQL chấp nhận như WHERE tùy ý.

### 3.4. NULL trong WHEN

Giống các điều kiện Boolean SQL khác, trigger chỉ thực hiện khi WHEN cho kết quả **TRUE**. Nếu kết quả FALSE hoặc NULL/UNKNOWN, function bị bỏ qua cho hàng tương ứng.

## 4. OLD và NEW: giá trị trước và sau thay đổi

Trong row-level trigger:

| Event | OLD | NEW | Ý nghĩa |
|---|---|---|---|
| INSERT | Không có row cũ | Row mới | Kiểm tra giá trị đang chèn |
| UPDATE | Row cũ | Row mới | So sánh trước/sau |
| DELETE | Row cũ | Không có row mới | Kiểm tra row đang bị xóa |

### 4.1. WHEN cho INSERT

~~~sql
CREATE TRIGGER audit_large_insert
AFTER INSERT ON payments
FOR EACH ROW
WHEN (NEW.amount >= 1000000)
EXECUTE FUNCTION log_large_payment();
~~~

### 4.2. WHEN cho UPDATE

~~~sql
CREATE TRIGGER audit_status_change
AFTER UPDATE ON orders
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

### 4.3. WHEN cho DELETE

~~~sql
CREATE TRIGGER audit_important_delete
AFTER DELETE ON customers
FOR EACH ROW
WHEN (OLD.is_vip IS TRUE)
EXECUTE FUNCTION log_vip_delete();
~~~

### 4.4. Không dùng NEW trong DELETE hoặc OLD trong INSERT

Các giá trị hàng không tồn tại ở event tương ứng. Khi thiết kế trigger function dùng chung nhiều event, phải phân nhánh theo `TG_OP</BT> trước khi đọc những field chỉ có ở event đó.

## 5. SQL có ba giá trị logic: TRUE, FALSE và UNKNOWN

Đây là lý do phổ biến khiến WHEN không chạy như dự định.

Giả sử:

| OLD.email | NEW.email | `OLD.email <> NEW.email</BT> |
|---|---|---|
| `'a@example.test'</BT> | `'b@example.test'</BT> | TRUE |
| `'a@example.test'</BT> | `'a@example.test'</BT> | FALSE |
| NULL | `'b@example.test'</BT> | NULL/UNKNOWN |
| `'a@example.test'</BT> | NULL | NULL/UNKNOWN |
| NULL | NULL | NULL/UNKNOWN |

Với `<></BT>, so sánh có NULL thường trả UNKNOWN, và WHEN không được kích hoạt.

### 5.1. Dùng IS DISTINCT FROM

~~~sql
WHEN (OLD.email IS DISTINCT FROM NEW.email)
~~~

Toán tử này có ngữ nghĩa so sánh **an toàn với NULL**.

| OLD.email | NEW.email | `IS DISTINCT FROM</BT> |
|---|---|---|
| `'a@example.test'</BT> | `'b@example.test'</BT> | TRUE |
| `'a@example.test'</BT> | `'a@example.test'</BT> | FALSE |
| NULL | `'b@example.test'</BT> | TRUE |
| `'a@example.test'</BT> | NULL | TRUE |
| NULL | NULL | FALSE |

### 5.2. Khi chỉ quan tâm một trạng thái cụ thể

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

Điều kiện này chỉ cho trigger chạy khi status **chuyển thành** paid. Nếu chỉ dùng `NEW.status='paid'</BT>, những UPDATE khác trên hàng đã paid vẫn có thể kích hoạt trigger.

### 5.3. Khi chỉ quan tâm ngưỡng

~~~sql
WHEN (
    OLD.balance >= 0
    AND NEW.balance < 0
)
~~~

Ví dụ chỉ bắt sự kiện vượt qua ngưỡng từ không âm sang âm, không phải mọi UPDATE trên hàng đã âm. Nếu balance có thể NULL, cần xác định rõ NULL được xử lý như thế nào.

## 6. UPDATE OF: chỉ cột xuất hiện trong SET

Ví dụ:

~~~sql
CREATE TRIGGER orders_amount_targeted
AFTER UPDATE OF amount
ON orders
FOR EACH ROW
EXECUTE FUNCTION log_amount_update();
~~~

Trigger này được xem xét khi câu UPDATE liệt kê `amount</BT> trong `SET</BT> theo những quy tắc của PostgreSQL.

### 6.1. Cột được SET, giá trị không đổi

~~~sql
UPDATE orders
SET amount = amount
WHERE order_id = 101;
~~~

Câu lệnh nhắm cột `amount</BT>, nên `AFTER UPDATE OF amount</BT> **vẫn có thể kích hoạt** nếu row được cập nhật. Việc giá trị không thay đổi không tự loại trigger.

### 6.2. Cột khác được SET

~~~sql
UPDATE orders
SET updated_at = CURRENT_TIMESTAMP
WHERE order_id = 101;
~~~

Nếu `amount</BT> không được nhắm trong danh sách SET, column-specific trigger trên amount thường **không kích hoạt**, dù row vẫn được UPDATE.

### 6.3. Cần nhiều cột

~~~sql
CREATE TRIGGER orders_business_columns_targeted
AFTER UPDATE OF status, amount, customer_id
ON orders
FOR EACH ROW
EXECUTE FUNCTION log_business_field_update();
~~~

Điều kiện `UPDATE OF</BT> là **OR theo các cột được liệt kê**: chỉ cần ít nhất một cột thuộc danh sách xuất hiện trong target list là event được xem xét. Nó **không có nghĩa cả ba cột phải thay đổi**.

### 6.4. Không tự so sánh giá trị trước/sau

Nếu yêu cầu là “chỉ ghi audit khi giá trị thực sự thay đổi”, hãy kết hợp `WHEN</BT> với `IS DISTINCT FROM</BT>.

## 7. Tại sao UPDATE OF không phải bộ phát hiện thay đổi?

Một câu UPDATE có thể nhắm cột nhưng giữ nguyên giá trị:

~~~sql
UPDATE accounts
SET status = status
WHERE account_id = 1;
~~~

Ngược lại, một **BEFORE UPDATE trigger khác** có thể sửa `NEW.status</BT> trong khi câu UPDATE ban đầu chỉ nhắm cột `balance</BT>.

~~~text
UPDATE accounts SET balance = 0 WHERE account_id = 1
              |
              v
BEFORE UPDATE trigger:
    NEW.status := 'suspended'
              |
              v
Row được lưu với status mới
              |
              v
AFTER UPDATE OF status:
    không được kích hoạt chỉ vì BEFORE trigger đổi status
              |
              v
AFTER UPDATE ... WHEN OLD.status IS DISTINCT FROM NEW.status:
    có thể phát hiện status thật sự đổi
~~~

Đây là một khác biệt **rất quan trọng**. Một column-specific trigger chỉ dựa vào `UPDATE OF status</BT> có thể bỏ sót thay đổi status được tạo bởi BEFORE trigger nếu câu UPDATE gốc không liệt kê status.

### 7.1. Dùng AFTER UPDATE không OF khi cần mọi nguồn thay đổi

~~~sql
CREATE TRIGGER accounts_any_status_change
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION log_status_change();
~~~

Điều kiện này không yêu cầu status phải có mặt trong SET; nó xét kết quả row cũ và row mới.

### 7.2. Khi vẫn nên dùng UPDATE OF

Nếu hợp đồng nghiệp vụ là “quan tâm những lệnh UPDATE chủ động nhắm cột status”, kể cả giá trị không đổi, `UPDATE OF status</BT> là phù hợp. Nếu business event là “status thật sự đổi”, cần kiểm tra OLD/NEW, và cân nhắc các BEFORE triggers khác.

### 7.3. WHEN không tự bảo đảm không có cập nhật

Khi WHEN FALSE, PostgreSQL vẫn có thể ghi phiên bản row mới do UPDATE, tùy MVCC/plan. Muốn tránh một UPDATE vô nghĩa, hãy cân nhắc điều kiện ngay trong WHERE của UPDATE hoặc trong BEFORE logic một cách có chủ đích.

## 8. So sánh các định nghĩa trigger thường gặp

| Định nghĩa | Khi nào được xem xét | Kiểm tra giá trị thật sự đổi? |
|---|---|---|
| `AFTER UPDATE</BT> | Mọi row được UPDATE | Không |
| `AFTER UPDATE OF status</BT> | SET có nhắc status | Không |
| `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status)</BT> | Mọi UPDATE row, nhưng chỉ chạy hàm khi status đổi | Có |
| `AFTER UPDATE OF status ... WHEN (OLD.status IS DISTINCT FROM NEW.status)</BT> | SET nhắc status và giá trị đổi | Có, trong phạm vi UPDATE OF |
| `AFTER UPDATE ... WHEN (NEW.status='paid')</BT> | Hàng sau UPDATE đang paid | Không nhất thiết là chuyển trạng thái |
| `AFTER UPDATE ... WHEN (OLD.status IS DISTINCT FROM NEW.status AND NEW.status='paid')</BT> | Chuyển thành paid | Có |

### 8.1. Chọn theo ý nghĩa sự kiện

- “Bất kỳ lệnh nào nhắm tới email” → `UPDATE OF email</BT>.
- “Email thực sự thay đổi” → `WHEN (OLD.email IS DISTINCT FROM NEW.email)</BT>.
- “Email chuyển từ NULL sang có giá trị” → `WHEN (OLD.email IS NULL AND NEW.email IS NOT NULL)</BT>.
- “Chỉ khi đã xác nhận email” → điều kiện trên status/verification fields theo đúng business semantics.
- “Mọi thay đổi sau BEFORE triggers” → thường không giới hạn bằng `UPDATE OF</BT> nếu cột có thể được sửa gián tiếp.

## 9. Timing của BEFORE row WHEN

Ví dụ:

~~~sql
CREATE TRIGGER validate_new_amount
BEFORE UPDATE OF amount
ON orders
FOR EACH ROW
WHEN (NEW.amount < 0)
EXECUTE FUNCTION reject_negative_amount();
~~~

Khi row được xem xét, PostgreSQL đánh giá WHEN **trước khi gọi function này**.

### 9.1. Khi WHEN FALSE

Function không chạy. Row operation tiếp tục theo cơ chế bình thường, chịu những triggers/ràng buộc khác.

### 9.2. Khi WHEN TRUE

Function được gọi và có thể kiểm tra/đổi `NEW</BT> hoặc trả NULL để bỏ qua row operation trong trường hợp BEFORE row trigger, nếu thiết kế hợp lệ.

### 9.3. Điều kiện có thể thấy NEW từ BEFORE trigger trước đó

Khi nhiều BEFORE row triggers cùng event, thứ tự kích hoạt có liên quan. Một BEFORE trigger chạy trước có thể chỉnh NEW, và trigger chạy sau có thể thấy giá trị NEW đã được chỉnh sửa.

### 9.4. Vì sao không nên dùng BEFORE trigger cho kiểm tra đơn giản?

Nếu chỉ cần `amount >= 0</BT>, một `CHECK(amount >= 0)</BT> thường là cách trực tiếp, dễ hiểu và bảo vệ toàn vẹn mạnh hơn so với trigger function tự kiểm tra. Trigger phù hợp khi logic không thể biểu đạt bằng ràng buộc thông thường hoặc cần tác dụng phụ đã được cân nhắc.

## 10. Timing của AFTER row WHEN

Với AFTER row trigger, PostgreSQL đánh giá WHEN **ngay sau thao tác thay đổi hàng**, trước khi quyết định có xếp sự kiện kích hoạt trigger vào hàng đợi hay không.

~~~sql
CREATE TRIGGER audit_status
AFTER UPDATE
ON accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION write_status_audit();
~~~

### 10.1. Lợi ích hiệu năng

Nếu một UPDATE làm thay đổi 100.000 rows nhưng chỉ 100 rows có status khác, WHEN có thể tránh ghi 99.900 sự kiện trigger tương ứng vào hàng đợi để chạy function sau đó.

### 10.2. Khác việc IF ở đầu AFTER trigger function

Nếu chỉ kiểm tra bên trong function, PostgreSQL vẫn phải lên lịch/chạy function cho nhiều hàng rồi mới bỏ qua. Đẩy predicate đơn giản vào WHEN có thể tiết kiệm overhead đáng kể.

### 10.3. Không làm giảm số row được UPDATE

Điều kiện WHEN giúp tối ưu phần trigger, không có nghĩa UPDATE chỉ tác động 100 rows. 100.000 rows vẫn có thể được xử lý bởi câu UPDATE.

### 10.4. Cần xem logic đồng thời

Một audit row có thể được ghi sau UPDATE nhưng vẫn thuộc transaction. Nếu transaction rollback, audit INSERT trong cùng PostgreSQL transaction cũng rollback, trừ side effect nằm ngoài DB/sequence semantics.

## 11. Thứ tự nhiều triggers trên cùng bảng

PostgreSQL có quy tắc thứ tự kích hoạt triggers cùng loại/sự kiện trên cùng relation, thường theo **thứ tự tên trigger theo alphabet** đối với các triggers cùng loại.

Ví dụ:

~~~text
a10_normalize_status  (BEFORE UPDATE)
b20_validate_status   (BEFORE UPDATE)
c30_audit_change      (AFTER UPDATE)
~~~

### 11.1. Thứ tự BEFORE ảnh hưởng NEW

Nếu `a10_normalize_status</BT> thay NEW.status, `b20_validate_status</BT> có thể thấy trạng thái mới khi nó chạy.

### 11.2. Đặt tên không nên là cách duy nhất mô tả workflow

Thứ tự tên có thể được tận dụng có chủ ý trong những tình huống cần thiết, nhưng rất dễ bị phá khi thêm trigger khác hoặc rename. Logic phụ thuộc mạnh giữa các bước thường nên được gói trong một trigger function hoặc command function/procedure rõ ràng nếu điều đó phù hợp.

### 11.3. WHEN của trigger sau phụ thuộc trạng thái lúc xét

Một trigger BEFORE có điều kiện `WHEN (NEW.status='active')</BT> có thể chạy hoặc không tùy những BEFORE triggers đã thay NEW trước đó.

### 11.4. AFTER quan sát kết quả cuối của BEFORE

AFTER row trigger dùng OLD và NEW theo trạng thái row được cập nhật, nên có thể phát hiện thay đổi do BEFORE trigger tạo ra, miễn trigger không bị giới hạn nhầm bằng `UPDATE OF</BT>.

## 12. UPDATE OF với generated columns

PostgreSQL có **generated columns**, ví dụ stored generated column được tính từ các cột cơ sở.

~~~sql
CREATE TABLE product_names (
    product_id BIGINT PRIMARY KEY,
    display_name TEXT NOT NULL,
    normalized_name TEXT
      GENERATED ALWAYS AS (lower(display_name)) STORED
);
~~~

Một column-specific trigger có thể liệt kê generated column:

~~~sql
CREATE TRIGGER product_normalized_target
AFTER UPDATE OF normalized_name
ON product_names
FOR EACH ROW
EXECUTE FUNCTION log_product_name_change();
~~~

### 12.1. Dependency của generated column được tính đến

Theo semantics PostgreSQL, nếu một **generated column được liệt kê trong UPDATE OF** và câu UPDATE nhắm tới một cột cơ sở mà generated column phụ thuộc, điều đó có thể làm column-specific trigger được xem xét.

### 12.2. Không áp dụng logic này tùy tiện cho mọi cột dẫn xuất

Việc thay status bằng BEFORE trigger hoặc thay một giá trị tính trong function khác không tương đương generated-column dependency được PostgreSQL quản lý. Cần phân biệt cột generated theo catalog và cột chỉ được application/trigger tự duy trì.

### 12.3. Giá trị generated vẫn có thể không thay đổi

Ví dụ đổi chữ hoa/thường:

~~~sql
UPDATE product_names
SET display_name = 'POSTGRESQL'
WHERE product_id = 1;
~~~

Nếu normalized_name là `lower(display_name)</BT>, giá trị có thể vẫn giống trước. `UPDATE OF</BT> kiểm tra target/dependency chứ không bảo đảm generated result đã khác.

### 12.4. Khi cần giá trị thật sự đổi

Với AFTER row trigger trên generated column phù hợp, có thể dùng:

~~~sql
WHEN (
    OLD.normalized_name
    IS DISTINCT FROM NEW.normalized_name
)
~~~

Cần kiểm tra đúng PostgreSQL version và hành vi generated columns theo timing của trigger; không giả định BEFORE row trigger thấy mọi giá trị generated mới đã được tính xong.

## 13. Không thể giới hạn UPDATE OF bằng biểu thức JSON path tùy ý

Nếu bảng có cột `details JSONB</BT>:

~~~sql
UPDATE products
SET details = jsonb_set(
    details,
    '{status}',
    '"published"'
)
WHERE product_id = 10;
~~~

Column-specific trigger:

~~~sql
AFTER UPDATE OF details
~~~

được xem xét vì cả **cột details** xuất hiện trong SET, không phải vì PostgreSQL biết path `details.status</BT> đã đổi.

### 13.1. Không viết UPDATE OF details->>'status'

Danh sách `UPDATE OF</BT> dùng tên cột target, không phải biểu thức trích xuất JSON path.

### 13.2. Dùng WHEN để so giá trị trường

~~~sql
WHEN (
    (OLD.details ->> 'status')
    IS DISTINCT FROM
    (NEW.details ->> 'status')
)
~~~

### 13.3. Nếu path có kiểu phức tạp

Khi JSON có cấu trúc lồng sâu, cần hiểu sự khác biệt giữa missing key, JSON null, SQL NULL và text coercion. Một biểu thức `->></BT> có thể quy các tình huống khác nhau thành SQL NULL. Nếu business cần phân biệt, dùng phép so sánh JSONB/ngữ nghĩa riêng.

### 13.4. Nếu cần bảo vệ invariant

Một CHECK constraint hoặc typed columns được thiết kế tốt có thể phù hợp hơn so với giữ toàn bộ business state trong JSONB và dựa vào trigger để giải mã.

## 14. Row-level và statement-level: không thay thế nhau

Ví dụ row-level:

~~~sql
CREATE TRIGGER log_each_change
AFTER UPDATE ON accounts
FOR EACH ROW
EXECUTE FUNCTION log_row_change();
~~~

Ví dụ statement-level:

~~~sql
CREATE TRIGGER log_update_command
AFTER UPDATE ON accounts
FOR EACH STATEMENT
EXECUTE FUNCTION log_statement_change();
~~~

### 14.1. UPDATE 0 rows

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = -1;
~~~

Với lệnh không cập nhật row nào:

- Row-level trigger không có row để chạy.
- Statement-level trigger của event tương ứng **vẫn có thể chạy một lần**.

### 14.2. Statement-level trigger không có OLD/NEW row

Một statement có thể tác động nhiều rows; không có một OLD/NEW đại diện duy nhất. Muốn xử lý cả tập rows, có thể cân nhắc transition tables khi phù hợp.

### 14.3. WHEN không phải điều kiện row của statement-level trigger

Trong những phiên bản PostgreSQL thông dụng, `WHEN</BT> được quy định cho row-level triggers, không phải một cách viết tùy ý để lọc từng hàng của `FOR EACH STATEMENT</BT>. Muốn lọc dữ liệu trong statement-level trigger, phải dùng logic trong function và/hoặc transition relations khi được hỗ trợ.

### 14.4. UPDATE OF statement-level

Nếu cần chỉ kích hoạt một statement-level trigger khi câu UPDATE nhắm các cột cụ thể, cần kiểm tra syntax/semantics đúng phiên bản. Dù trigger chạy một lần, `UPDATE OF</BT> vẫn liên quan target list của command, **không có nghĩa giá trị của một row đã đổi**.

## 15. Transition tables khác OLD và NEW của một hàng

PostgreSQL có thể cho AFTER triggers tham chiếu **transition relations** chứa tập rows cũ/mới của statement trong những điều kiện hỗ trợ.

Ví dụ tổng quát:

~~~sql
CREATE TRIGGER accounts_change_batch
AFTER UPDATE ON accounts
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION process_account_changes();
~~~

### 15.1. Vì sao hữu ích?

Một UPDATE ảnh hưởng 10.000 accounts có thể được xử lý theo tập trong trigger function thay vì thực thi 10.000 lời gọi row-level function.

### 15.2. Có giới hạn kết hợp với UPDATE OF

Theo quy tắc PostgreSQL, một UPDATE trigger dùng transition tables không được đồng thời chỉ định danh sách cột bằng `UPDATE OF column_list</BT> trong những dạng bị giới hạn. Vì vậy không thể tùy tiện ghép mọi tính năng vào một định nghĩa.

### 15.3. Transition tables cần được xử lý đúng

Một function sử dụng transition relation phải được viết để truy vấn các relations được đặt tên trong `REFERENCING</BT>; nó không có sẵn giá trị OLD/NEW scalar như row-level trigger.

### 15.4. Khi nào chọn statement-level + transition tables?

Với audit/bulk derived data ở quy mô lớn, xử lý set-based có thể hiệu quả. Nhưng phải cân nhắc memory, semantics với partitions, FK effects và khả năng từng PostgreSQL version.

## 16. Constraint triggers và điều kiện WHEN

PostgreSQL có **constraint triggers** dùng cho những yêu cầu kiểm tra ràng buộc đặc biệt, được tạo bằng `CREATE CONSTRAINT TRIGGER</BT> theo các điều kiện được hỗ trợ.

~~~sql
CREATE CONSTRAINT TRIGGER check_business_rule
AFTER UPDATE ON some_table
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
WHEN (NEW.status = 'final')
EXECUTE FUNCTION validate_business_rule();
~~~

Đây là cú pháp minh họa: table, function và rule cần tồn tại.

### 16.1. Hành động trigger có thể được trì hoãn

Một constraint trigger có thể được cấu hình để action được thực thi vào thời điểm deferred phù hợp, thay vì ngay thời điểm row operation.

### 16.2. WHEN không tự được trì hoãn

Điểm quan trọng: đối với constraint triggers có WHEN, **điều kiện WHEN được đánh giá ngay sau row update**, không chờ đến lúc deferred action chạy. Chỉ những events thỏa WHEN tại thời điểm đó mới được xếp hàng.

### 16.3. Không đánh đồng với CHECK/FK

Một số constraints cốt lõi có hỗ trợ tối ưu và concurrency semantics riêng. Nếu quy tắc có thể biểu đạt bằng CHECK, UNIQUE, FOREIGN KEY hay EXCLUDE thì nên xem xét ràng buộc khai báo trước khi viết constraint trigger.

### 16.4. Không dùng deferred trigger cho mọi validation

Chặn dữ liệu lỗi càng sớm càng tốt có thể giúp đơn giản hóa API; deferred checks phù hợp khi invariant chỉ có thể đúng ở cuối transaction sau nhiều bước, nhưng làm debugging và lỗi commit phức tạp hơn.

## 17. INSTEAD OF triggers và giới hạn WHEN

`INSTEAD OF</BT> triggers thường được dùng trên views để thay hành vi INSERT/UPDATE/DELETE đối với view.

~~~sql
CREATE TRIGGER customer_view_update
INSTEAD OF UPDATE ON customer_view
FOR EACH ROW
EXECUTE FUNCTION update_customer_underlying_tables();
~~~

### 17.1. Khác BEFORE/AFTER table trigger

INSTEAD OF trigger thực hiện thay thao tác DML vào view. Không tự coi mọi quy tắc WHEN hoặc column-specific UPDATE OF của AFTER row triggers trên bảng vật lý đều áp dụng y hệt cho INSTEAD OF trigger.

### 17.2. Thực hành phù hợp

Nếu muốn kiểm tra thay đổi của một field trên view, xử lý rõ OLD/NEW ở trigger function theo semantics INSTEAD OF, hoặc xem khả năng automatically updatable views và CHECK OPTION trước.

### 17.3. Tránh lẫn với rule

PostgreSQL còn có rewrite rules, ví dụ `CREATE RULE</BT>, là cơ chế rewrite ở mức query. Trigger và rule có lifecycle, visibility và execution behavior khác nhau; `WHEN</BT> trong trigger không đồng nghĩa điều kiện `WHERE</BT> hay điều kiện `CREATE RULE</BT>.

## 18. Trigger WHEN so với ràng buộc CHECK

Nếu mục tiêu chỉ là không cho balance âm:

~~~sql
ALTER TABLE accounts
ADD CONSTRAINT accounts_balance_nonnegative
CHECK (balance >= 0);
~~~

Thường nên dùng CHECK thay vì:

~~~sql
CREATE TRIGGER reject_negative_balance
BEFORE INSERT OR UPDATE ON accounts
FOR EACH ROW
WHEN (NEW.balance < 0)
EXECUTE FUNCTION reject_negative_balance();
~~~

### 18.1. CHECK có ưu điểm

- Áp dụng invariant theo cách khai báo.
- Dễ nhận diện bằng schema tools.
- Có semantics phù hợp với các đường ghi dữ liệu.
- Không cần runtime/function riêng cho trường hợp đơn giản.
- Dễ dùng với constraints và migrations.

### 18.2. CHECK không làm mọi thứ

CHECK không phù hợp trực tiếp để kiểm tra cross-row aggregate invariant hoặc thao tác audit. Khi logic vượt quá phạm vi CHECK, có thể cần unique/FK/exclusion/transaction protocol/trigger phù hợp.

### 18.3. BEFORE trigger dùng khi cần biến đổi

Ví dụ làm sạch/chuẩn hóa giá trị đầu vào trước khi ghi, khi generated column hoặc application-side preprocessing không đáp ứng. Nhưng cần quy tắc thứ tự, NULL và security rõ.

## 19. Trigger WHEN so với điều kiện WHERE trong UPDATE

Hai câu:

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = 101;
~~~

và:

~~~sql
UPDATE accounts
SET status = 'active'
WHERE account_id = 101
  AND status IS DISTINCT FROM 'active';
~~~

không có cùng chi phí khi giá trị đang là active.

### 19.1. WHERE ngăn UPDATE vô nghĩa

Nếu row đang active, câu thứ hai không xử lý row đó, giúp tránh một số update work và trigger firing.

### 19.2. WHEN chỉ chặn function trigger

Với `WHEN (OLD.status IS DISTINCT FROM NEW.status)</BT>, câu UPDATE đầu vẫn có thể thực hiện row operation; chỉ function trigger không được gọi khi giá trị giống nhau.

### 19.3. Hệ quả với MVCC

Một UPDATE dù dữ liệu logic không đổi vẫn có thể tạo phiên bản tuple mới và WAL, làm tăng bloat/index maintenance tùy HOT eligibility và storage. Chỉ chặn audit function không loại bỏ tất cả chi phí này.

### 19.4. Không lạm dụng WHERE khi có tác dụng phụ cần thiết

Một số ứng dụng cố tình UPDATE dù giá trị giống nhau để ghi nhận “touch”, cập nhật modified_at hoặc bump version. Lúc đó cần làm rõ hợp đồng event, không mặc định mọi UPDATE không đổi phải bị bỏ qua.

## 20. Lab PostgreSQL: chuẩn bị môi trường

Bài lab sau dùng schema riêng và dữ liệu giả lập. **Chỉ chạy trong database thử nghiệm**. Nếu schema `trigger_when_lab</BT> đã tồn tại, dùng tên schema khác để tránh ghi đè. Không DROP dữ liệu của người khác.

### 20.1. Tạo schema

~~~sql
CREATE SCHEMA trigger_when_lab;
~~~

### 20.2. Tạo bảng accounts

~~~sql
CREATE TABLE trigger_when_lab.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'closed')),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0,
    contact_email TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 20.3. Tạo bảng audit

~~~sql
CREATE TABLE trigger_when_lab.trigger_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trigger_name TEXT NOT NULL,
    operation TEXT NOT NULL,
    account_id BIGINT,
    old_status TEXT,
    new_status TEXT,
    old_balance NUMERIC(12,2),
    new_balance NUMERIC(12,2),
    detail TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

### 20.4. Nạp dữ liệu mẫu

~~~sql
INSERT INTO trigger_when_lab.accounts (
    owner_name, status, balance, contact_email
)
VALUES
    ('Nguyen An', 'active', 500.00, 'an@example.test'),
    ('Tran Binh', 'active', 250.00, NULL),
    ('Le Chi', 'suspended', 0.00, 'chi@example.test'),
    ('Pham Dung', 'active', 1000.00, 'dung@example.test');
~~~

### 20.5. Xác nhận dữ liệu để hiểu ví dụ

~~~sql
SELECT
    account_id, owner_name, status, balance, contact_email
FROM trigger_when_lab.accounts
ORDER BY account_id;
~~~

Trong lab mới, identity IDs thường bắt đầu từ 1. Nếu đã có dữ liệu/sequence từ lượt thực hành trước, hãy dùng ID trả về thực tế thay vì giả định 1–4.

## 21. Lab: trigger function ghi audit khi cột được nhắm

Tạo một function dùng chung cho các AFTER UPDATE triggers:

~~~sql
CREATE FUNCTION trigger_when_lab.log_account_event()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name,
        operation,
        account_id,
        old_status,
        new_status,
        old_balance,
        new_balance,
        detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NEW.account_id,
        OLD.status,
        NEW.status,
        OLD.balance,
        NEW.balance,
        'row-level AFTER trigger'
    );

    RETURN NEW;
END;
$$;
~~~

### 21.1. TG_NAME và TG_OP

- `TG_NAME</BT>: tên trigger hiện đang gọi function.
- `TG_OP</BT>: tên event như INSERT/UPDATE/DELETE.
- `OLD</BT>/`NEW</BT>: row records trong row trigger thích hợp.

### 21.2. Function này dành cho UPDATE

Ví dụ truy cập cả OLD và NEW nên dùng với **row-level UPDATE**. Nếu gắn vào INSERT/DELETE mà không sửa function, sẽ gặp lỗi ngữ nghĩa vì thiếu record tương ứng. Một trigger function dùng nhiều events phải phân nhánh theo TG_OP.

### 21.3. RETURN trong AFTER trigger

Giá trị RETURN của row-level AFTER trigger thường không được dùng để sửa row đã lưu. `RETURN NEW</BT> ở đây là cách viết thông dụng; việc chặn UPDATE bằng RETURN NULL thuộc semantics của BEFORE row trigger, không phải AFTER.

## 22. Lab: tạo hai trigger để thấy UPDATE OF khác WHEN

### 22.1. Trigger thứ nhất: chỉ xét cột có mặt trong SET

~~~sql
CREATE TRIGGER a10_status_targeted
AFTER UPDATE OF status
ON trigger_when_lab.accounts
FOR EACH ROW
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.2. Trigger thứ hai: xét cột mục tiêu và thay đổi thật

~~~sql
CREATE TRIGGER b20_status_changed_targeted
AFTER UPDATE OF status
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.3. Trigger thứ ba: phát hiện mọi thay đổi status

~~~sql
CREATE TRIGGER c30_status_changed_any_update
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (OLD.status IS DISTINCT FROM NEW.status)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 22.4. Khác nhau ở đâu?

- `a10</BT>: chạy nếu lệnh nhắm status, kể cả status không đổi.
- `b20</BT>: chạy nếu lệnh nhắm status **và** status thật sự đổi.
- `c30</BT>: chạy nếu status thật sự đổi, **không yêu cầu** status có mặt trong SET.

Ba trigger cùng dùng function để log event, nên dễ quan sát khác biệt bằng `trigger_name</BT>.

## 23. Lab: UPDATE SET status = status

~~~sql
UPDATE trigger_when_lab.accounts
SET status = status
WHERE account_id = 1;
~~~

Xem audit:

~~~sql
SELECT
    event_id, trigger_name, operation,
    old_status, new_status
FROM trigger_when_lab.trigger_events
ORDER BY event_id;
~~~

### 23.1. Kỳ vọng

Nếu row account_id=1 tồn tại:

- `a10_status_targeted</BT> ghi một sự kiện vì status được nêu trong SET.
- `b20_status_changed_targeted</BT> không ghi vì OLD.status và NEW.status giống nhau.
- `c30_status_changed_any_update</BT> không ghi vì giá trị thật không đổi.

### 23.2. Bài học

Chỉ dùng `UPDATE OF status</BT> **không đồng nghĩa** bạn đang ghi nhật ký “status change”.

### 23.3. Tránh nhầm số bản ghi audit

Nếu đã chạy lại các bước nhiều lần, audit sẽ tích lũy thêm event. Có thể lọc theo thời điểm hoặc kiểm tra những event mới sau lần chạy, thay vì giả định bảng luôn chỉ có một hàng.

## 24. Lab: thay đổi status thật sự

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'suspended'
WHERE account_id = 1;
~~~

Xem audit:

~~~sql
SELECT
    event_id,
    trigger_name,
    old_status,
    new_status
FROM trigger_when_lab.trigger_events
WHERE account_id = 1
ORDER BY event_id;
~~~

### 24.1. Kỳ vọng của UPDATE này

Nếu account_id=1 trước đó active và các triggers đều enabled:

- `a10</BT> ghi event.
- `b20</BT> ghi event.
- `c30</BT> ghi event.

### 24.2. Vì sao ba event?

Đây là ba trigger độc lập, cùng dùng một audit function. Một thay đổi status có thể ghi ba dòng **vì chính ta tạo ba triggers**. Trong sản phẩm thật, thường chỉ giữ trigger phục vụ một hợp đồng cụ thể thay vì tạo ba logging triggers trùng chức năng.

### 24.3. Ví dụ điều kiện transition

Nếu chỉ quan tâm từ active sang suspended, dùng:

~~~sql
WHEN (
    OLD.status = 'active'
    AND NEW.status = 'suspended'
)
~~~

Điều này chặt hơn “bất kỳ thay đổi status”.

## 25. Lab: UPDATE một cột không phải status

~~~sql
UPDATE trigger_when_lab.accounts
SET balance = balance + 50
WHERE account_id = 2;
~~~

### 25.1. Kỳ vọng

Nếu không có trigger nào khác chỉnh status, ba trigger đã tạo **không ghi audit**:

- Hai trigger UPDATE OF status không được xem xét vì SET chỉ nhắm balance.
- Trigger c30 có thể được xét cho row nhưng WHEN FALSE vì status không đổi.

### 25.2. Mục tiêu

Đây là trường hợp `WHEN</BT> có ích để chặn function overhead cho row mà business field quan tâm không thay đổi.

### 25.3. Không đánh đồng với INSERT

`UPDATE OF status</BT> chỉ liên quan UPDATE event; INSERT không kích hoạt nó. Nếu cần log insert trạng thái ban đầu, cần trigger INSERT riêng theo quy tắc phù hợp.

## 26. Lab: BEFORE trigger đổi status dù UPDATE không nhắc status

Tạo function áp dụng quy tắc: nếu balance <= 0 sau UPDATE balance thì status thành suspended.

~~~sql
CREATE FUNCTION trigger_when_lab.suspend_when_empty()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.balance <= 0
       AND NEW.status = 'active' THEN
        NEW.status := 'suspended';
    END IF;

    RETURN NEW;
END;
$$;
~~~

Gắn function vào BEFORE UPDATE OF balance:

~~~sql
CREATE TRIGGER a05_suspend_on_balance_update
BEFORE UPDATE OF balance
ON trigger_when_lab.accounts
FOR EACH ROW
EXECUTE FUNCTION trigger_when_lab.suspend_when_empty();
~~~

### 26.1. Lệnh chỉ cập nhật balance

~~~sql
UPDATE trigger_when_lab.accounts
SET balance = 0
WHERE account_id = 4;
~~~

Account 4 ban đầu active với balance=1000 trong lab mới. BEFORE trigger thay `NEW.status</BT> thành suspended.

### 26.2. Các AFTER triggers nào ghi audit?

- `a10_status_targeted</BT>: **không**, vì câu UPDATE gốc chỉ SET balance.
- `b20_status_changed_targeted</BT>: **không**, cùng lý do.
- `c30_status_changed_any_update</BT>: **có**, vì OLD.status active và NEW.status suspended.

### 26.3. Kiểm tra

~~~sql
SELECT account_id, status, balance
FROM trigger_when_lab.accounts
WHERE account_id = 4;

SELECT event_id, trigger_name, old_status, new_status
FROM trigger_when_lab.trigger_events
WHERE account_id = 4
ORDER BY event_id;
~~~

### 26.4. Ý nghĩa thiết kế

Nếu muốn audit **mọi thay đổi thực của status**, hãy dùng AFTER UPDATE với WHEN dựa trên OLD/NEW, không dựa hoàn toàn vào `UPDATE OF status</BT> khi cột có thể bị thay bởi BEFORE triggers.

### 26.5. Lưu ý nghiệp vụ

Quy tắc tự chuyển status khi balance <= 0 chỉ dùng minh họa. Hệ thống tài chính thật cần mô hình trạng thái và transaction/ràng buộc chặt hơn; không đưa rule này lên production nguyên trạng.

## 27. Lab: WHEN với NULL cho contact_email

Tạo trigger chỉ ghi khi email thật sự thay đổi:

~~~sql
CREATE FUNCTION trigger_when_lab.log_email_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id,
        detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NEW.account_id,
        'contact_email changed'
    );

    RETURN NEW;
END;
$$;
~~~

~~~sql
CREATE TRIGGER d40_email_changed
AFTER UPDATE OF contact_email
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.contact_email
    IS DISTINCT FROM
    NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_email_change();
~~~

### 27.1. NULL → có email

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = 'binh-new@example.test'
WHERE account_id = 2;
~~~

Trigger chạy nếu trước đó contact_email là NULL.

### 27.2. Có email → cùng email

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = contact_email
WHERE account_id = 2;
~~~

Trigger không chạy vì giá trị không khác.

### 27.3. Có email → NULL

~~~sql
UPDATE trigger_when_lab.accounts
SET contact_email = NULL
WHERE account_id = 2;
~~~

Trigger chạy vì `IS DISTINCT FROM</BT> nhận diện khác biệt NULL-safe.

### 27.4. Vì sao <> không tương đương?

`OLD.contact_email <> NEW.contact_email</BT> trả UNKNOWN nếu một phía NULL, khiến WHEN không TRUE. Đây là một lỗi audit khá phổ biến.

## 28. Lab: chỉ bắt trạng thái chuyển sang closed

Giả sử nghiệp vụ chỉ cần báo khi tài khoản chuyển sang trạng thái closed, không báo những UPDATE khác trên tài khoản đã closed.

~~~sql
CREATE TRIGGER e50_account_closed
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'closed'
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 28.1. Đưa status tới closed

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'closed'
WHERE account_id = 2;
~~~

Trigger e50 chạy nếu status trước đó khác closed.

### 28.2. UPDATE khi đã closed

~~~sql
UPDATE trigger_when_lab.accounts
SET updated_at = now()
WHERE account_id = 2;
~~~

Trigger e50 không chạy vì OLD.status và NEW.status đều closed.

### 28.3. Đơn giản hơn chỉ NEW.status='closed'?

Không. Điều kiện chỉ trên NEW.status sẽ chạy khi row đang closed và UPDATE một cột khác, có thể dẫn đến gửi sự kiện “account closed” trùng.

### 28.4. Tính idempotency

Ngay cả khi lọc transition chính xác trong một database statement, hệ thống phát message ra ngoài vẫn cần outbox và consumer idempotency nếu có retries/failure. WHEN không thay một giao thức exactly-once.

## 29. Lab: BEFORE WHEN để chuẩn hóa input

Tạo function đơn giản chuẩn hóa owner_name:

~~~sql
CREATE FUNCTION trigger_when_lab.trim_owner_name()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.owner_name := btrim(NEW.owner_name);
    RETURN NEW;
END;
$$;
~~~

Gắn vào BEFORE UPDATE OF owner_name với WHEN:

~~~sql
CREATE TRIGGER b10_trim_owner_name
BEFORE UPDATE OF owner_name
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (NEW.owner_name IS DISTINCT FROM btrim(NEW.owner_name))
EXECUTE FUNCTION trigger_when_lab.trim_owner_name();
~~~

### 29.1. Khi owner_name đã chuẩn

~~~sql
UPDATE trigger_when_lab.accounts
SET owner_name = 'Nguyen An'
WHERE account_id = 1;
~~~

Nếu chuỗi không có khoảng trắng thừa, WHEN FALSE và function không cần chạy.

### 29.2. Khi nhập khoảng trắng

~~~sql
UPDATE trigger_when_lab.accounts
SET owner_name = '  Nguyen An  '
WHERE account_id = 1;
~~~

WHEN TRUE và function cắt khoảng trắng trước khi lưu.

### 29.3. Generated column hoặc application validation?

Nếu chỉ cần chuẩn hóa đơn giản và không cần side effect, có thể xử lý ở ứng dụng hoặc thiết kế generated/normalized column khi phù hợp. Trigger hữu ích khi muốn mọi đường ghi (JDBC, SQL script, ETL...) cùng áp dụng quy tắc chuyển đổi.

### 29.4. Tránh gọi hàm nặng trong WHEN

Nếu WHEN thực hiện nhiều biểu thức phức tạp hoặc gọi hàm truy cập dữ liệu, bạn vẫn trả chi phí kiểm tra cho từng row. Lọc ở WHEN tốt khi predicate đủ rẻ và giúp tránh công việc lớn phía sau.

## 30. Lab: trigger FOR EACH STATEMENT với UPDATE 0 rows

Tạo function log sự kiện statement-level:

~~~sql
CREATE FUNCTION trigger_when_lab.log_statement_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id, detail
    )
    VALUES (
        TG_NAME,
        TG_OP,
        NULL,
        'statement-level UPDATE executed'
    );
    RETURN NULL;
END;
$$;
~~~

Gắn trigger:

~~~sql
CREATE TRIGGER z90_update_statement
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_when_lab.log_statement_update();
~~~

### 30.1. UPDATE không trúng hàng

~~~sql
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = -999;
~~~

### 30.2. Kiểm tra

~~~sql
SELECT
    event_id, trigger_name, operation, account_id, detail
FROM trigger_when_lab.trigger_events
WHERE trigger_name = 'z90_update_statement'
ORDER BY event_id DESC;
~~~

Statement-level trigger vẫn có thể ghi event dù 0 row UPDATE; row-level triggers không có hàng để xét.

### 30.3. Phạm vi của log

Event này chỉ nói “câu lệnh UPDATE đã chạy”, không nói “đã đổi N rows” hay “một cột nào đó thật sự khác”. Muốn row count hoặc delta, cần logic/instrumentation phù hợp.

## 31. Lab: khi cần giảm số câu UPDATE không đổi

So hai cách cập nhật status:

~~~sql
-- Có thể thực hiện row UPDATE dù status đã active.
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = 3;
~~~

~~~sql
-- Không nhắm row nếu status đã active.
UPDATE trigger_when_lab.accounts
SET status = 'active'
WHERE account_id = 3
  AND status IS DISTINCT FROM 'active';
~~~

### 31.1. Khác về rows affected

Trong trường hợp status đã active, câu đầu có thể báo một row updated; câu thứ hai báo 0 rows updated.

### 31.2. Khác về trigger

Câu đầu vẫn có thể làm trigger a10 chạy vì SET status. Câu thứ hai không có row-level event nếu không row nào thỏa WHERE.

### 31.3. Statement-level trigger vẫn có thể chạy

Với trigger z90, câu UPDATE thứ hai dù 0 row vẫn có thể ghi statement event.

### 31.4. Cần xét semantics trả về ứng dụng

Nhiều Java services dùng row count để biết bản ghi tồn tại hay không. Nếu thay WHERE bằng `IS DISTINCT FROM</BT>, 0 rows có thể nghĩa “row tồn tại nhưng giá trị đã đúng” **hoặc** “row không tồn tại”. Hãy thiết kế API/RETURNING và cách phân biệt kết quả khi cần.

## 32. Kết hợp UPDATE OF và WHEN cho nhiều cột

Ví dụ audit khi ít nhất một trong ba cột business thay đổi:

~~~sql
CREATE TRIGGER important_fields_changed
AFTER UPDATE OF status, balance, contact_email
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
    OR OLD.contact_email IS DISTINCT FROM NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

### 32.1. Hai lớp OR khác nhau

- `UPDATE OF status, balance, contact_email</BT>: OR theo **cột xuất hiện trong SET**.
- `WHEN (a_changed OR b_changed OR c_changed)</BT>: OR theo **giá trị khác nhau**.

### 32.2. Nếu BEFORE trigger thay một cột không có trong SET?

Ví dụ SET updated_at nhưng BEFORE trigger chỉnh balance. Trigger `UPDATE OF status, balance, contact_email</BT> vẫn có thể **không được xét** nếu những cột đó không nằm trong target list.

### 32.3. Nếu cần audit bất kỳ thay đổi thực

Bỏ `OF</BT>:

~~~sql
CREATE TRIGGER important_fields_any_change
AFTER UPDATE
ON trigger_when_lab.accounts
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
    OR OLD.contact_email IS DISTINCT FROM NEW.contact_email
)
EXECUTE FUNCTION trigger_when_lab.log_account_event();
~~~

Hai câu CREATE trên là **hai phương án minh họa**, không nhất thiết nên giữ đồng thời trong production vì có thể ghi audit trùng.

## 33. So sánh OLD/NEW toàn hàng

PostgreSQL có thể so sánh toàn row records:

~~~sql
WHEN (OLD IS DISTINCT FROM NEW)
~~~

Đây là một cách phát hiện có bất kỳ thay đổi nào trong row representation theo semantics phép so sánh hàng.

### 33.1. Lợi ích

Đơn giản khi muốn audit mọi field (và logic business thật sự đòi điều đó).

### 33.2. Hạn chế

- Thay `updated_at</BT> cũng tính là thay đổi, có thể gây audit noise.
- Nếu có fields lớn, so sánh toàn hàng có thể tốn thêm chi phí.
- Khi schema thay đổi/thêm cột, tập fields tham gia so sánh cũng đổi theo.
- Cần hiểu semantics so sánh composite/NULL và khả năng so sánh của các data types.

### 33.3. Nên liệt kê business columns khi thích hợp

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    OR OLD.balance IS DISTINCT FROM NEW.balance
)
~~~

Cách này minh bạch hơn nếu hợp đồng audit chỉ quan tâm hai trường.

### 33.4. Không thay data validation

Một row “khác” không đồng nghĩa thay đổi hợp lệ. Ràng buộc nghiệp vụ vẫn cần CHECK/UNIQUE/FK/transaction logic.

## 34. Điều kiện WHEN có subquery được không?

Ví dụ muốn chỉ ghi audit nếu customer ở bảng khác đang active:

~~~sql
-- KHÔNG HỢP LỆ: subquery trực tiếp trong trigger WHEN
WHEN (
    EXISTS (
        SELECT 1 FROM customers
        WHERE customer_id = NEW.customer_id
          AND status = 'active'
    )
)
~~~

### 34.1. Giới hạn

PostgreSQL không cho subquery trực tiếp trong WHEN expression của trigger.

### 34.2. Lựa chọn phù hợp

- Đưa kiểm tra SQL vào trigger function, với transaction/concurrency semantics rõ.
- Tái thiết kế bằng FK/CHECK/constraints nếu logic thực chất là invariant.
- Dùng một state column/derived representation được cập nhật nhất quán khi phù hợp.
- Gói thao tác trong command transaction thay vì trigger nếu business workflow phức tạp.

### 34.3. Hàm trong WHEN không phải luôn miễn phí

Một function được gọi từ WHEN có thể chạy SQL nội bộ nếu được phép, nhưng bạn vẫn trả chi phí function cho mỗi row được xét và có thể tạo race/visibility issues. Đừng dùng function đọc bảng trong WHEN chỉ để né giới hạn cú pháp subquery mà không phân tích correctness.

## 35. WHEN có thể kết hợp nhiều phép logic

### 35.1. AND

~~~sql
WHEN (
    OLD.status IS DISTINCT FROM NEW.status
    AND NEW.status = 'paid'
)
~~~

Chỉ thực thi khi **cả hai** điều kiện TRUE.

### 35.2. OR

~~~sql
WHEN (
    OLD.email IS DISTINCT FROM NEW.email
    OR OLD.phone IS DISTINCT FROM NEW.phone
)
~~~

Chỉ cần một trong hai field khác.

### 35.3. NOT

~~~sql
WHEN (NOT (NEW.status = 'archived'))
~~~

Nếu NEW.status NULL, biểu thức có thể UNKNOWN thay vì TRUE. Khi status có thể NULL, dùng `IS DISTINCT FROM</BT> hoặc điều kiện NULL rõ nếu muốn hành vi khác.

### 35.4. Điều kiện tổ hợp cần dấu ngoặc

~~~sql
WHEN (
    (
        OLD.status IS DISTINCT FROM NEW.status
        AND NEW.status = 'paid'
    )
    OR (
        OLD.balance >= 0
        AND NEW.balance < 0
    )
)
~~~

Việc tách nhóm giúp đọc đúng thứ tự ưu tiên toán tử và business intent.

### 35.5. Không đưa logic quá lớn vào DDL

WHEN nên thể hiện predicate tương đối rõ ràng. Nếu điều kiện nhiều tầng, phụ thuộc dữ liệu từ nhiều bảng và trạng thái phức tạp, hãy cân nhắc cấu trúc lại business workflow hoặc dùng một function được tài liệu hóa.

## 36. Performance: đo trước và sau giới hạn trigger

Một trigger được gọi trên từng row có thể ảnh hưởng latency theo công thức tư duy:

\[
T_{\mathrm{statement}}
\approx T_{\mathrm{base\ DML}}
+ N_{\mathrm{fired}}\cdot T_{\mathrm{function}}
+ T_{\mathrm{queue/constraints}}
\]

Đây là **mô hình gần đúng**. Thực tế ảnh hưởng còn do cache, WAL, locks, IO, trigger ordering và executor.

### 36.1. UPDATE OF giảm phạm vi trigger

Nếu 95% câu UPDATE chỉ cập nhật `last_seen_at</BT>, một trigger `AFTER UPDATE OF email</BT> sẽ không được xem xét với những statements không nhắm email, có thể giảm overhead.

### 36.2. WHEN giảm số hàng phải gọi function

Nếu một câu UPDATE SET email=email trên một triệu rows, `WHEN (OLD.email IS DISTINCT FROM NEW.email)</BT> có thể tránh gọi audit function cho phần lớn rows nếu giá trị không đổi.

### 36.3. Nhưng WHEN có chi phí đánh giá

Điều kiện WHEN vẫn cần được đánh giá ở những hàng liên quan. Nếu predicate gọi function rất đắt hoặc thao tác JSON phức tạp, lợi ích có thể giảm.

### 36.4. AFTER WHEN có thể tiết kiệm hàng đợi

Một AFTER trigger mà function chỉ IF kiểm tra giá trị có thể phải queue và gọi function nhiều hơn so với WHEN ở định nghĩa trigger.

### 36.5. Không ngăn WAL của UPDATE

WHEN FALSE không có nghĩa UPDATE miễn phí. Nếu mục tiêu là tránh DML vô nghĩa, cần xem điều kiện WHERE của UPDATE và behavior của application.

## 37. Trigger cho bulk updates và migration

Một bulk UPDATE có thể chạm hàng triệu rows:

~~~sql
UPDATE products
SET normalized_name = lower(display_name);
~~~

### 37.1. Nếu có row trigger

Mỗi row bị UPDATE có thể làm trigger function được gọi một lần hoặc nhiều lần, tùy số triggers và WHEN/UPDATE OF.

### 37.2. WHEN có thể giúp nhưng không giải toàn bộ

Nếu nhiều hàng có normalized_name đã đúng, `WHEN</BT> có thể chặn audit function; nhưng câu UPDATE vẫn có thể ghi hàng không cần thiết.

### 37.3. Thêm WHERE tránh rows không đổi

~~~sql
UPDATE products
SET normalized_name = lower(display_name)
WHERE normalized_name
      IS DISTINCT FROM lower(display_name);
~~~

Ví dụ chỉ phù hợp nếu normalized_name là **cột thường có thể UPDATE**, không phải stored generated column. Với generated column, không gán trực tiếp giá trị theo cách này.

### 37.4. Statement-level trigger có thể phù hợp

Nếu cần cập nhật aggregate/log cho cả batch, sử dụng transition tables và set-based SQL khi được hỗ trợ thường đáng đánh giá hơn row-by-row trigger thực thi nhiều SQL.

### 37.5. Chú ý locks và transaction length

Bulk UPDATE vẫn giữ transaction, locks và WAL. Trigger không phải cách đơn giản thay batch sizing, VACUUM, indexes và migration safety.

## 38. Trigger function và tác dụng phụ ngoài database

Một audit trigger có thể INSERT vào bảng audit cùng transaction:

~~~sql
INSERT INTO audit_events (...);
~~~

Khi transaction chính rollback, audit row thường rollback cùng.

### 38.1. External HTTP/email là khác

Nếu trigger function gọi extension gửi HTTP request ra ngoài, PostgreSQL transaction rollback không tự thu hồi request đã gửi.

### 38.2. WHEN không làm external effects exactly-once

Nếu transaction được retry, trigger có thể được thực thi lại. Khi mạng thất bại, external receiver có thể thấy thông điệp nhiều lần hoặc trước khi database commit.

### 38.3. Transactional outbox

Một cách thiết kế an toàn hơn cho events:

~~~text
UPDATE business row
    |
AFTER row trigger WHEN meaningful change
    |
INSERT event_outbox cùng transaction
    |
COMMIT
    |
Worker ngoài database gửi message
    |
Consumer idempotent
~~~

### 38.4. Không giải quyết duplicate semantics chỉ bằng WHEN

Nếu một trạng thái được chuyển qua lại, hay UPDATE được retry trong transaction khác, bạn vẫn cần event ID, idempotency key, schema version và consumer policy phù hợp.

## 39. Trigger recursion và vòng lặp cập nhật

Một trigger function trên `accounts</BT> tự thực hiện:

~~~sql
UPDATE trigger_when_lab.accounts
SET updated_at = clock_timestamp()
WHERE account_id = NEW.account_id;
~~~

có thể kích hoạt trigger UPDATE khác (hoặc chính trigger) và dẫn đến recursion.

### 39.1. WHEN không tự chặn mọi recursion

Nếu mỗi lần UPDATE đều khiến điều kiện WHEN TRUE hoặc có trigger khác thay field liên tục, vòng lặp vẫn có thể xảy ra.

### 39.2. Hướng tốt hơn cho updated_at

Một BEFORE UPDATE row trigger có thể đặt:

~~~sql
NEW.updated_at := clock_timestamp();
RETURN NEW;
~~~

để sửa **chính row đang được update**, tránh tạo một UPDATE mới trên cùng table.

### 39.3. pg_trigger_depth()

PostgreSQL có `pg_trigger_depth()</BT> giúp quan sát độ sâu trigger execution. Tuy nhiên, dùng `WHEN (pg_trigger_depth() = 0)</BT> làm guard tổng quát có thể khiến legitimate nested operations bị bỏ qua. Không dựa vào depth như một thay thế cho thiết kế workflow không đệ quy.

### 39.4. Giới hạn bằng column list

Một BEFORE UPDATE OF status trigger sửa updated_at không tự làm trigger UPDATE OF updated_at kích hoạt riêng vì việc sửa NEW không phải một UPDATE SET statement mới. Nhưng nếu function chạy một UPDATE statement riêng, tình huống khác.

## 40. Trigger WHEN và partitions

Với declarative partitioning, row-level triggers và trigger definitions có những quy tắc áp dụng xuống partitions theo PostgreSQL version và cấu trúc hierarchy.

### 40.1. Kiểm tra object trigger ở parent và leaves

Nếu trigger được định nghĩa ở partitioned parent, PostgreSQL hiện đại có cơ chế tạo/duy trì các trigger tương ứng trên partitions theo những quy tắc cụ thể. Không giả định mọi trigger trên parent chỉ được gọi một lần cho toàn bộ bảng logic.

### 40.2. Row movement

UPDATE partition key có thể khiến hàng chuyển từ partition này sang partition khác, liên quan các hành vi DELETE/INSERT ở cấp vật lý và trigger firing semantics đặc biệt. Không suy ra `AFTER UPDATE OF key</BT> chắc chắn luôn phản ánh mọi sự kiện ở từng leaf như bảng không partitioned.

### 40.3. Transition relations và partitions

Khi dùng transition tables với partitioned tables, cần kiểm tra hỗ trợ, phạm vi rows và thời điểm firing theo PostgreSQL version. Những giới hạn về BEFORE/AFTER và column lists vẫn có thể ảnh hưởng thiết kế.

### 40.4. Kiểm thử với dữ liệu qua nhiều partitions

Nếu business event quan trọng (thanh toán, trạng thái pháp lý), cần test thực tế cả UPDATE trong partition và UPDATE làm thay partition key, không chỉ một table đơn lẻ.

## 41. ON CONFLICT DO UPDATE và MERGE

SQL hiện đại có các đường ghi dữ liệu không chỉ là một UPDATE đơn giản.

### 41.1. INSERT ... ON CONFLICT DO UPDATE

~~~sql
INSERT INTO accounts(account_id, status)
VALUES (101, 'active')
ON CONFLICT (account_id)
DO UPDATE SET status = EXCLUDED.status;
~~~

Tùy nhánh thực thi và PostgreSQL semantics, các BEFORE/AFTER INSERT/UPDATE triggers có thể được xét theo những quy tắc đặc biệt. Khi `DO UPDATE SET status=...</BT>, column-specific UPDATE trigger quan tâm status theo target list của nhánh UPDATE.

### 41.2. ON CONFLICT DO NOTHING

Nhánh không INSERT row và không UPDATE row thì không có row-level AFTER INSERT/UPDATE event cho hàng đó; statement-level trigger behavior cần hiểu riêng.

### 41.3. MERGE

PostgreSQL hỗ trợ MERGE trong các phiên bản hiện đại; các actions INSERT/UPDATE/DELETE có semantics trigger cụ thể. Không tự coi một lệnh MERGE là một UPDATE OF đơn giản dù nó có nhánh UPDATE.

### 41.4. Kiểm tra theo phiên bản

Khi ứng dụng dùng UPSERT/MERGE, phải test trigger firing thực tế với nhánh INSERT, UPDATE, DO NOTHING và các tình huống conflict/WHERE, nhất là khi audit hoặc outbox không được phép trùng/mất sự kiện.

## 42. Trigger trên view và rewrite rule khác nhau

Chương **Trigger và luật** còn phân biệt hai cơ chế:

| Tính năng | Trigger | Rule |
|---|---|---|
| Mục tiêu | Thực thi trigger function theo event | Rewrite query theo rule system |
| Thời điểm | BEFORE/AFTER/INSTEAD OF theo loại | Biến đổi statement tại rewrite stage |
| Row values | OLD/NEW trong row triggers | OLD/NEW có semantics rule riêng |
| WHEN | Boolean predicate theo trigger rules | Rule condition có ngữ nghĩa khác |
| Audit row changes | Row-level AFTER trigger thường phù hợp | Không nên giả định tương đương |
| Optimization | Row/statement execution overhead | Query rewrite tác động SQL |
| Khả năng hiểu | Trigger function có flow xử lý rõ | Rule có thể tạo những hành vi bất ngờ nếu lạm dụng |

### 42.1. WHERE và WHEN khác nhau

`WHERE</BT> trong UPDATE quyết định hàng nào được cập nhật. `WHEN</BT> của trigger quyết định có thực thi function cho event/row hay không. Điều kiện của CREATE RULE hoạt động ở giai đoạn rewrite, không phải thay thế trực tiếp một row-level AFTER trigger WHEN.

### 42.2. Khi xây audit mới

Một AFTER ROW trigger với điều kiện giá trị thay đổi có thể rõ ràng hơn một rule tự ghi bảng audit, vì trigger thực thi với row events và NEW/OLD phù hợp.

### 42.3. Cần đọc legacy rules

Nếu database cũ dùng `CREATE RULE</BT> hoặc INSTEAD OF view rules, phải hiểu rewrite semantics trước khi “chuyển” sang trigger; không sửa chỉ vì cùng có chữ WHEN/WHERE.

## 43. Hiệu năng và thứ tự DML với nhiều triggers

Một table có thể có:

- BEFORE normalization.
- BEFORE validation.
- AFTER audit.
- AFTER outbox.
- AFTER statement metrics.

### 43.1. Một UPDATE có thể gây nhiều function calls

Nếu 10.000 rows được UPDATE và có ba AFTER row triggers không lọc, có thể có tới hàng chục nghìn function executions. Những triggers có WHEN có thể giảm số lời gọi theo dữ liệu thật.

### 43.2. Ghi audit cũng là DML

INSERT vào bảng audit có WAL, indexes và locks riêng. GIN/B-tree index dư thừa trên bảng audit có thể tăng write latency. Khi thiết kế, đừng chỉ đếm CPU của trigger function mà bỏ chi phí I/O.

### 43.3. Khi muốn giữ only relevant events

Dùng WHEN ngay ở AFTER trigger để loại những rows không meaningful. Nếu event chỉ cần một row cho toàn statement, cân nhắc transition tables/set-based processing.

### 43.4. Chi phí điều kiện

`OLD.status IS DISTINCT FROM NEW.status</BT> thường rẻ hơn việc gọi function lớn đọc bảng khác để “xem có thay đổi không”, nhưng cả hai vẫn phải được đánh giá theo workload.

### 43.5. Lỗi trong trigger

Nếu trigger function RAISE EXCEPTION và không được xử lý phù hợp, statement DML có thể thất bại và transaction bị ảnh hưởng. Điều kiện WHEN không biến trigger thành một tác vụ nền bất đồng bộ.

## 44. Chẩn đoán trigger không chạy

Nếu bạn kỳ vọng trigger kích hoạt nhưng không thấy audit:

1. Kiểm tra DML thực là INSERT/UPDATE/DELETE nào.
2. Kiểm tra trigger timing và `FOR EACH ROW/STATEMENT</BT>.
3. Kiểm tra hàng có thực sự được UPDATE theo WHERE không.
4. Kiểm tra các cột nằm trong SET và `UPDATE OF</BT>.
5. Kiểm tra BEFORE triggers khác có thay NEW không.
6. Kiểm tra WHEN cho TRUE/FALSE/NULL.
7. Kiểm tra dùng `<></BT> với NULL thay vì `IS DISTINCT FROM</BT>.
8. Kiểm tra trigger enabled/disabled theo metadata và session replication role.
9. Kiểm tra function có RAISE EXCEPTION hay rollback không.
10. Kiểm tra transaction có COMMIT không.
11. Kiểm tra quyền/search_path và schema qualification.
12. Kiểm tra có thay đổi data thông qua partition/view/upsert/merge đặc biệt không.
13. Kiểm tra trigger function được gắn đúng bảng và đúng tên.
14. Kiểm tra SET statement nhắm generated column/dependency gì.
15. Kiểm tra observation query có lọc đúng audit rows không.

### 44.1. Đừng kết luận khi audit trống

Audit trống có thể do WHEN FALSE, không có row, transaction rollback, trigger disabled, hoặc việc ghi audit xảy ra ở bảng khác. Cần xác định tầng nào đã ngăn sự kiện.

### 44.2. Không khắc phục bằng xóa WHEN ngay lập tức

Bỏ WHEN có thể làm trigger ghi nhiều sự kiện không mong muốn và tăng chi phí. Hãy xác định yêu cầu “touched column” hay “value changed” trước.

## 45. Xem trigger definitions trong catalogs

### 45.1. pg_trigger

~~~sql
SELECT
    t.tgname AS trigger_name,
    t.tgenabled,
    pg_get_triggerdef(t.oid, true) AS definition
FROM pg_trigger AS t
WHERE t.tgrelid =
    'trigger_when_lab.accounts'::regclass
  AND NOT t.tgisinternal
ORDER BY t.tgname;
~~~

### 45.2. Ý nghĩa tgenabled

Metadata cho biết trạng thái trigger enable/replication context theo ký hiệu PostgreSQL. Đừng chỉ nhìn trigger được tạo mà bỏ qua whether it fires under current session replication role.

### 45.3. pg_get_triggerdef

Hàm giúp xem SQL định nghĩa trigger, bao gồm timing, UPDATE OF, WHEN, function. Đây là cách đáng tin cậy hơn việc đoán từ tên trigger.

### 45.4. pg_get_functiondef

~~~sql
SELECT pg_get_functiondef(
    'trigger_when_lab.log_account_event()'::regprocedure
);
~~~

Dùng để đọc definition function đang được trigger thực thi.

### 45.5. information_schema.triggers

~~~sql
SELECT
    event_object_schema,
    event_object_table,
    trigger_name,
    event_manipulation,
    action_timing,
    action_orientation
FROM information_schema.triggers
WHERE event_object_schema = 'trigger_when_lab'
ORDER BY event_object_table, trigger_name;
~~~

View chuẩn hóa metadata có thể chịu giới hạn về quyền và không trình bày mọi chi tiết PostgreSQL-specific như pg_get_triggerdef.

## 46. Xem số lần chạy trigger bằng EXPLAIN

PostgreSQL có thể cho thông tin thời gian/số lần gọi triggers trong `EXPLAIN (ANALYZE)</BT> của các statements thay đổi dữ liệu, tùy kiểu trigger và plan.

Ví dụ:

~~~sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE trigger_when_lab.accounts
SET status = status
WHERE account_id = 1;

ROLLBACK;
~~~

### 46.1. Vì sao BEGIN/ROLLBACK?

`EXPLAIN ANALYZE</BT> **thực sự chạy UPDATE**, kể cả triggers và các DML trong trigger. Dùng transaction rollback trong lab để không giữ kết quả ghi, dù sequence side effects không rollback như row data.

### 46.2. Thông tin cần quan sát

- Thời gian execution tổng.
- Số rows ở plan.
- Buffers.
- Thông tin trigger calls/timing nếu được hiển thị.
- Khả năng audit function ghi dữ liệu.
- Sự khác biệt khi WHEN TRUE và FALSE.

### 46.3. Row-level trigger vs index scan

Một UPDATE tìm row bằng Index Scan không có nghĩa trigger function được tối ưu vào index. Trigger execution và tìm row là hai phần công việc khác nhau.

### 46.4. Một phép đo không đủ kết luận

Với bảng 4 rows, độ chênh lệch trigger rất nhỏ, có thể bị nhiễu bởi cache/timer. Để benchmark hiệu năng, cần dữ liệu đại diện, nhiều lần chạy và monitoring phù hợp, nhưng việc benchmark nội dung không thuộc bước ghi file của worker.

## 47. pg_stat_user_functions và trigger function stats

Khi cấu hình `track_functions</BT> được bật phù hợp, bạn có thể xem thống kê calls/time:

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'trigger_when_lab'
ORDER BY total_time DESC;
~~~

### 47.1. Không mặc định có dữ liệu

Nếu `track_functions</BT> đang none hoặc function không thuộc loại được track, view có thể không ghi nhận calls như mong đợi.

### 47.2. EXPLAIN và thống kê phục vụ mục tiêu khác nhau

EXPLAIN cho một statement có thể hiển thị tác động trigger của lần chạy đó. `pg_stat_user_functions</BT> tổng hợp calls/time theo phạm vi thống kê của cluster từ lần reset tương ứng.

### 47.3. Đừng nhầm số lời gọi với số hàng business thay đổi

Một UPDATE có thể chạy nhiều triggers trên cùng hàng; số trigger calls không phải số distinct business events, và có WHEN nên có thể ít hơn số rows updated.

## 48. Bảo mật và quyền trong trigger function

Trigger function thường chạy dưới mô hình security rights cụ thể; theo mặc định là `SECURITY INVOKER</BT> nếu không khai báo khác. `SECURITY DEFINER</BT> có thể chạy với quyền owner và cần hardening.

### 48.1. Khi audit cần đặc quyền ghi

Một caller có thể có quyền UPDATE trên bảng business nhưng không có INSERT trực tiếp vào audit table. Trigger function SECURITY DEFINER được thiết kế an toàn có thể ghi audit với quyền owner phù hợp.

### 48.2. Search path an toàn

Với SECURITY DEFINER, sử dụng trusted schemas và schema-qualify objects để tránh name-resolution hijacking:

~~~sql
CREATE FUNCTION trigger_when_lab.secure_audit_example()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, trigger_when_lab, pg_temp
AS $$
BEGIN
    INSERT INTO trigger_when_lab.trigger_events (
        trigger_name, operation, account_id, detail
    )
    VALUES (TG_NAME, TG_OP, NEW.account_id, 'secure audit');
    RETURN NEW;
END;
$$;
~~~

Function này là ví dụ dành cho UPDATE/INSERT row, không dùng trực tiếp với DELETE nếu chưa phân nhánh NEW/OLD.

### 48.3. RLS và owner

Owner privileges, RLS policies và các role có BYPASSRLS có thể khiến kết quả khác với application role. Cần kiểm thử dưới quyền thực tế.

### 48.4. WHEN không thay authorization

Một condition `WHEN (NEW.tenant_id = 42)</BT> chỉ lọc trigger events; nó không cấm caller đọc/sửa tenant khác nếu quyền SQL cho phép. Dùng grants, RLS, constraints và API authorization theo thiết kế.

### 48.5. Không cho phép user sửa tắt audit

Nếu security/compliance yêu cầu audit không thể bị bypass, cần kiểm soát quyền DISABLE TRIGGER, owner/superuser privileges, replication settings và các đường ingest dữ liệu. Một trigger không phải biện pháp kiểm soát bất khả xâm phạm đối với database admin.

## 49. Hiểu đúng những hạn chế của WHEN

| Hạn chế | Hệ quả thiết kế |
|---|---|
| Boolean condition theo ngữ cảnh trigger | Không thay mọi điều kiện SQL tùy ý |
| Không chứa subquery trực tiếp | Kiểm tra bảng khác cần thiết kế khác |
| Có NULL/UNKNOWN | Dùng IS DISTINCT FROM khi so trước/sau |
| OLD/NEW phụ thuộc event | Không dùng OLD ở INSERT hoặc NEW ở DELETE |
| Timing khác nhau | BEFORE/AFTER quan sát giá trị ở giai đoạn khác |
| AFTER WHEN không ngăn row update | Muốn ngăn DML phải xử lý WHERE/BEFORE/constraint |
| Chạy theo row khi row-level | Predicate rất đắt cũng bị lặp nhiều lần |
| Không bảo đảm exactly-once external effects | Cần outbox/idempotency |
| Không thay authorization | Phải dùng RLS/grants/role policies |
| Không là một batch transition table | Dữ liệu nhiều rows cần thiết kế riêng |

### 49.1. Giới hạn là cơ chế bảo vệ

PostgreSQL hạn chế những điều kiện trigger tùy ý để giữ execution semantics có thể dự đoán hơn. Khi nghiệp vụ muốn cross-table validation quá phức tạp, câu hỏi đầu tiên nên là **nó có phù hợp với trigger không?**.

## 50. Hiểu đúng những hạn chế của UPDATE OF

| Tình huống | UPDATE OF status |
|---|---|
| `SET status='paid'</BT> | Có thể kích hoạt |
| `SET status=status</BT> | Có thể kích hoạt |
| `SET amount=100</BT> | Không kích hoạt theo status |
| BEFORE trigger sửa NEW.status nhưng SET chỉ amount | Không kích hoạt chỉ vì giá trị status bị sửa |
| `UPDATE OF status, amount</BT>, SET chỉ amount | Có thể kích hoạt |
| Cột generated phụ thuộc cột trong SET | Có quy tắc dependency đặc biệt |
| UPDATE zero rows | Không có row-level firing |
| INSERT/DELETE | Không thuộc UPDATE OF event |
| JSONB path trong một cột | Chỉ biết cột JSONB nằm trong SET, không tự biết nested field đổi |
| WHEN kiểm tra OLD/NEW | Là tầng lọc giá trị bổ sung, không đổi ý nghĩa target list |

### 50.1. Không dùng UPDATE OF để bảo vệ mọi integrity invariant

Nếu ứng dụng UPDATE một cột gián tiếp làm status hoặc balance thay đổi qua trigger, column-specific trigger có thể bỏ sót. Với integrity invariant quan trọng, dùng CHECK/FK/UNIQUE hoặc kiểm tra AFTER/BEFORE không phụ thuộc target list trong những trường hợp cần.

## 51. Checklist khi thiết kế một trigger mới

### 51.1. Xác định business event

- Cần biết cột được **SET** hay giá trị thật sự **đổi**?
- Muốn bắt transition cụ thể hay mọi trạng thái sau UPDATE?
- Một row hay cả statement?
- Có cần ghi audit/outbox hay chỉ validate?
- Có cần đồng bộ side effect cùng transaction?
- Có generated columns hoặc BEFORE triggers sửa giá trị?

### 51.2. Xác định timing

- BEFORE có cần chỉnh NEW?
- AFTER có cần thấy row đã được ghi?
- AFTER WHEN có giúp tránh queue/call vô ích?
- INSTEAD OF trên view có semantics riêng không?
- Có constraint trigger deferred không?

### 51.3. Xác định predicate

- Dùng OLD/NEW phù hợp event chưa?
- Có NULL không? Nên dùng IS DISTINCT FROM?
- Có cần xét OR/AND đúng nhóm không?
- Có subquery không hợp lệ trong WHEN không?
- Có function đắt trong WHEN không?
- Có cần bỏ UPDATE OF vì BEFORE trigger khác có thể sửa cột quan tâm?

### 51.4. Xác định hiệu năng

- Có bao nhiêu rows được UPDATE trên một statement?
- Có bao nhiêu row triggers trên bảng?
- Function có SQL per-row hoặc external call không?
- Có thể viết set-based hoặc transition table không?
- WHERE có thể ngăn UPDATE không đổi không?
- Audit/outbox storage và WAL có lớn không?

### 51.5. Xác định bảo mật và vận hành

- Function chạy invoker hay definer?
- Quyền ghi bảng audit được kiểm soát chưa?
- RLS/tenant isolation có được bảo vệ không?
- Search path trusted và schema-qualified chưa?
- Trigger có thể bị DISABLE bởi role không?
- Migrations/partitioning/upsert/merge có thay firing behavior không?
- Có monitoring, rollback và recovery plan không?

## 52. Những hiểu lầm phổ biến

### 52.1. “UPDATE OF status chỉ chạy khi status khác trước”

**Sai.** Nó kiểm tra target list, không kiểm tra giá trị trước/sau.

### 52.2. “SET status=status thì không kích hoạt UPDATE OF status”

**Sai.** Cột vẫn xuất hiện trong SET.

### 52.3. “BEFORE trigger thay status sẽ tự kích hoạt mọi UPDATE OF status”

**Sai** nếu câu UPDATE ban đầu không nhắm status; có ngoại lệ/quy tắc riêng cho generated-column dependencies.

### 52.4. “WHEN OLD.x <> NEW.x luôn bắt mọi thay đổi”

**Sai.** Nếu có NULL, biểu thức có thể UNKNOWN.

### 52.5. “IS DISTINCT FROM chỉ khác <> ở cú pháp”

**Sai.** Nó cung cấp so sánh NULL-safe.

### 52.6. “WHEN FALSE làm UPDATE không diễn ra”

**Sai** với AFTER trigger; nó chỉ bỏ qua function trigger.

### 52.7. “AFTER WHEN và IF trong AFTER trigger function luôn có cùng overhead”

**Sai.** WHEN có thể tránh queue event và function invocation.

### 52.8. “WHEN có thể dùng EXISTS SELECT trực tiếp”

**Sai.** Trigger WHEN không cho subquery trực tiếp.

### 52.9. “UPDATE OF a,b đòi cả a và b cùng đổi”

**Sai.** Chỉ cần một cột được nhắm.

### 52.10. “UPDATE OF JSONB path chọn riêng trường lồng nhau”

**Sai.** Danh sách là tên cột, không phải JSON expression.

### 52.11. “AFTER UPDATE WHEN NEW.status='paid' chỉ báo chuyển thành paid”

**Sai.** Những UPDATE khác trên hàng đã paid vẫn có thể thỏa.

### 52.12. “Statement trigger không chạy khi UPDATE 0 rows”

**Sai.** Statement-level trigger có thể chạy dù row count bằng 0.

### 52.13. “Statement-level trigger có một NEW đại diện toàn bộ hàng”

**Sai.** Cần transition tables/logic khác cho tập rows.

### 52.14. “Constraint trigger deferred thì WHEN cũng deferred”

**Sai.** WHEN được đánh giá ngay sau row operation theo semantics hỗ trợ.

### 52.15. “Generated column dependency giống BEFORE trigger sửa cột”

**Sai.** PostgreSQL có quy tắc riêng cho generated columns được nêu trong UPDATE OF.

### 52.16. “Nếu WHEN kiểm tra giá trị đổi thì không còn WAL của UPDATE”

**Sai.** UPDATE chính vẫn có thể tạo tuple mới.

### 52.17. “Trigger audit tự đảm bảo exactly-once event ngoài database”

**Sai.** Cần xem retries, outbox và idempotency.

### 52.18. “Trigger bảo vệ mọi tenant nếu có WHEN theo tenant”

**Sai.** WHEN không thay RLS/grants.

### 52.19. “RETURN NULL trong AFTER trigger sẽ hủy UPDATE”

**Sai.** RETURN NULL để bỏ qua row operation thuộc cơ chế BEFORE row trigger; AFTER không có quyền đảo ngược UPDATE bằng giá trị return.

### 52.20. “Chỉ cần xem tên trigger là biết nó chạy thế nào”

**Sai.** Xem `pg_get_triggerdef</BT>, function definition, trạng thái enabled và context.

### 52.21. “UPDATE qua view, partition và MERGE luôn giống UPDATE bảng thường”

**Sai.** Các đường ghi dữ liệu đó có quy tắc firing riêng.

### 52.22. “Nhiều triggers đặt tên khác nhau không liên quan nhau”

**Không đúng chung.** BEFORE triggers có thể sửa NEW và ảnh hưởng WHEN của triggers chạy sau.

### 52.23. “Một CHECK constraint nên thay bằng trigger vì linh hoạt hơn”

**Không nên mặc định.** Invariant đơn giản thường nên dùng CHECK/UNIQUE/FK.

### 52.24. “Trigger function không có chi phí nếu chỉ INSERT audit”

**Sai.** INSERT audit vẫn ghi WAL/index, có locks và chi phí lưu trữ.

### 52.25. “EXPLAIN ANALYZE UPDATE chỉ xem plan và không sửa dữ liệu”

**Sai.** Nó thực thi UPDATE và triggers, cần dùng transaction thử nghiệm.

## 53. Bài tập thực hành

### Bài 1 — Định nghĩa

Giải thích sự khác nhau giữa `UPDATE OF status</BT> và `WHEN (OLD.status IS DISTINCT FROM NEW.status)</BT>.

**Gợi ý:** Target list so với giá trị thay đổi.

### Bài 2 — SET giống nhau

Một row đang status='active'. Chạy `UPDATE ... SET status=status</BT>. Trigger AFTER UPDATE OF status có thể chạy không?

**Đáp án:** Có.

### Bài 3 — Giá trị không đổi

Nếu kết hợp WHEN kiểm tra IS DISTINCT FROM, trigger có chạy khi SET status=status không?

**Đáp án:** Không nếu OLD/NEW status bằng nhau.

### Bài 4 — Column list nhiều cột

`UPDATE OF status, amount</BT> có đòi cả status và amount cùng nằm trong SET không?

**Đáp án:** Không; một cột là đủ.

### Bài 5 — BEFORE sửa status

UPDATE chỉ SET balance; BEFORE trigger đổi NEW.status. Trigger UPDATE OF status có tự chạy không?

**Đáp án:** Không theo cơ chế target list thông thường.

### Bài 6 — Phát hiện mọi status change

Viết định nghĩa AFTER trigger phù hợp nếu status có thể đổi do BEFORE trigger.

**Gợi ý:** AFTER UPDATE không OF, với WHEN OLD.status IS DISTINCT FROM NEW.status.

### Bài 7 — NULL đổi thành text

OLD.email=NULL và NEW.email='a'. `OLD.email <> NEW.email</BT> bằng TRUE không?

**Đáp án:** Không; UNKNOWN.

### Bài 8 — IS DISTINCT FROM

OLD.email=NULL, NEW.email='a'. Kết quả IS DISTINCT FROM là gì?

**Đáp án:** TRUE.

### Bài 9 — NULL sang NULL

OLD.email=NULL, NEW.email=NULL. IS DISTINCT FROM là gì?

**Đáp án:** FALSE.

### Bài 10 — Chuyển sang paid

Tạo WHEN chỉ chạy khi status thật sự đổi và NEW.status='paid'.

**Gợi ý:** AND giữa IS DISTINCT FROM và NEW.status='paid'.

### Bài 11 — Chỉ NEW.status='paid'

Vì sao câu WHEN này có thể tạo duplicate event?

**Gợi ý:** Row đã paid vẫn thỏa khi update cột khác.

### Bài 12 — BEFORE return

Row-level BEFORE trigger có thể RETURN NULL để làm gì?

**Gợi ý:** Bỏ qua row operation theo semantics BEFORE row trigger.

### Bài 13 — AFTER return

AFTER trigger RETURN NULL có hủy UPDATE không?

**Đáp án:** Không.

### Bài 14 — WHEN FALSE

AFTER trigger WHEN FALSE có ngăn câu UPDATE chính không?

**Đáp án:** Không.

### Bài 15 — WHEN với subquery

Có thể trực tiếp `WHEN (EXISTS(SELECT ...))</BT> không?

**Đáp án:** Không.

### Bài 16 — Generated column

Nếu generated normalized_name phụ thuộc display_name, `UPDATE OF normalized_name</BT> có thể được xem xét khi SET display_name không?

**Gợi ý:** Có quy tắc generated-column dependency phù hợp.

### Bài 17 — Generated value không đổi

Nếu display_name đổi chữ hoa/thường nhưng lower(display_name) không đổi, UPDATE OF normalized_name có tự bảo đảm normalized_name đổi không?

**Đáp án:** Không.

### Bài 18 — JSONB

Muốn xem path `details.status</BT> thay đổi, nên so sánh gì?

**Gợi ý:** OLD.details->>'status' và NEW.details->>'status' bằng IS DISTINCT FROM.

### Bài 19 — Statement-level

UPDATE 0 rows có thể chạy AFTER UPDATE FOR EACH STATEMENT trigger không?

**Đáp án:** Có.

### Bài 20 — Row-level

UPDATE 0 rows có row-level trigger invocation không?

**Đáp án:** Không có row để gọi.

### Bài 21 — Transition table

Vì sao transition tables có lợi khi cần audit 10.000 rows?

**Gợi ý:** Có thể xử lý set-based trong statement-level trigger.

### Bài 22 — UPDATE OF và transition tables

Có được tự ghép UPDATE OF column list với mọi transition relation configuration không?

**Đáp án:** Không; có hạn chế định nghĩa.

### Bài 23 — Deferred WHEN

Constraint trigger deferred có trì hoãn cả lúc đánh giá WHEN không?

**Đáp án:** Không; WHEN được xét ngay theo trigger semantics.

### Bài 24 — Timing

AFTER row WHEN được đánh giá vào thời điểm nào?

**Gợi ý:** Sau khi row operation, trước khi quyết định queue event.

### Bài 25 — BEFORE trigger order

Nếu BEFORE trigger a đổi NEW.status trước BEFORE trigger b, b có thể thấy giá trị nào?

**Gợi ý:** Giá trị NEW đã được a sửa.

### Bài 26 — CHECK vs trigger

Nếu chỉ cần amount>=0, nên xem giải pháp nào trước?

**Gợi ý:** CHECK constraint.

### Bài 27 — Tránh no-op UPDATE

Viết WHERE để tránh SET status='active' khi status đã active.

**Gợi ý:** status IS DISTINCT FROM 'active'.

### Bài 28 — Row count application

Khi thêm WHERE trên, 0 rows affected có thể có hai nghĩa gì?

**Gợi ý:** Không tồn tại hoặc giá trị đã đúng.

### Bài 29 — Recursion

Vì sao trigger UPDATE accounts tự UPDATE accounts có thể gây recursion?

**Gợi ý:** Lệnh UPDATE mới lại kích hoạt trigger.

### Bài 30 — updated_at

Trong BEFORE UPDATE trigger, làm sao đặt NEW.updated_at mà không chạy UPDATE riêng?

**Gợi ý:** Gán trực tiếp vào NEW rồi RETURN NEW.

### Bài 31 — Audit rollback

Nếu transaction rollback, audit INSERT cùng transaction có còn không?

**Đáp án:** Không.

### Bài 32 — Sequence gap

ID event_id identity có thể bị nhảy sau rollback không?

**Đáp án:** Có.

### Bài 33 — External webhook

Webhook được gọi trong trigger có tự rollback theo PostgreSQL không?

**Đáp án:** Không.

### Bài 34 — Outbox

Vì sao outbox phù hợp hơn gọi webhook trực tiếp từ AFTER trigger?

**Gợi ý:** Atomic intent cùng DB và gửi ngoài qua worker có retry.

### Bài 35 — Enable state

Xem trạng thái trigger ở catalog nào?

**Gợi ý:** pg_trigger.tgenabled.

### Bài 36 — Definition

Hàm nào dựng lại CREATE TRIGGER DDL?

**Đáp án:** pg_get_triggerdef.

### Bài 37 — Function definition

Hàm nào đọc định nghĩa trigger function?

**Đáp án:** pg_get_functiondef.

### Bài 38 — EXPLAIN ANALYZE

Vì sao phải cẩn thận với EXPLAIN ANALYZE UPDATE?

**Gợi ý:** Nó thực thi DML thật.

### Bài 39 — Statement vs row count

Một statement UPDATE 100 rows với ba row-level triggers có thể tạo bao nhiêu function calls tối đa trong điều kiện tất cả đều được kích hoạt?

**Gợi ý:** Nhiều hơn 100, ví dụ 300, tùy WHEN và enabled states.

### Bài 40 — Security

WHEN NEW.tenant_id=42 có tự cấm caller sửa tenant 43 không?

**Đáp án:** Không.

### Bài 41 — SECURITY DEFINER

Cần chú ý gì ở search_path của trigger function SECURITY DEFINER?

**Gợi ý:** Trusted schemas, schema qualification, pg_temp xử lý đúng.

### Bài 42 — Trạng thái chuyển

Viết WHEN chỉ ghi khi balance từ >=0 sang <0.

**Gợi ý:** OLD.balance >= 0 AND NEW.balance < 0, với NULL semantics phù hợp.

### Bài 43 — OR nhiều fields

Viết WHEN để audit khi status hoặc contact_email thật sự đổi.

**Gợi ý:** OR giữa hai IS DISTINCT FROM.

### Bài 44 — Whole-row comparison

So sánh OLD IS DISTINCT FROM NEW có thể gây audit noise khi nào?

**Gợi ý:** updated_at hoặc field kỹ thuật thay đổi.

### Bài 45 — Kiến trúc

Một hệ thống cần audit mọi thay đổi email, dù email bị sửa bởi BEFORE trigger và có thể NULL. Bạn sẽ định nghĩa trigger ra sao?

**Gợi ý:** AFTER UPDATE (không OF) FOR EACH ROW WHEN (OLD.email IS DISTINCT FROM NEW.email) rồi function ghi audit/outbox.

### Bài 46 — Bài tập đo hiệu năng

Một UPDATE set last_seen_at trên một triệu rows; table có AFTER UPDATE trigger ghi audit nhưng business chỉ quan tâm status. Đề xuất cách giới hạn hợp lý.

**Gợi ý:** UPDATE OF status khi hợp đồng là target column; hoặc AFTER UPDATE WHEN status changed nếu status có thể đổi gián tiếp, và xem WHERE tránh no-op UPDATE.

### Bài 47 — Lab chẩn đoán

Với các triggers a10/b20/c30, hãy dự đoán event logs cho ba trường hợp: SET status=status, SET status='suspended', SET balance=0 khi BEFORE trigger chuyển status.

**Đáp án gợi ý:** A: chỉ a10; B: a10+b20+c30 khi đổi thật; C: chỉ c30 cho status change gián tiếp.

### Bài 48 — MERGE/UPSERT

Vì sao không suy luận rằng MERGE hoặc INSERT ON CONFLICT DO UPDATE luôn kích hoạt triggers giống một UPDATE độc lập?

**Gợi ý:** Nhiều nhánh actions và semantics theo PostgreSQL version.

### Bài 49 — Constraint trigger

Nếu validation cần deferred action, điều gì phải nhớ về WHEN?

**Gợi ý:** WHEN được đánh giá ngay; chỉ action có thể deferred.

### Bài 50 — Thiết kế hoàn chỉnh

Một ứng dụng đặt hàng cần: chỉ phát OrderPaid khi trạng thái từ new sang paid; cập nhật modified_at; không ghi trùng event nếu UPDATE status=status; gửi message đến broker; phục vụ bulk updates. Hãy chọn trigger timing, WHEN, update predicate, outbox và phương án batch.

**Gợi ý:** Chỉ phát trên transition thực, AFTER ROW WHEN OLD.status IS DISTINCT FROM NEW.status AND NEW.status='paid', BEFORE sửa NEW.updated_at nếu cần; WHERE tránh no-op; ghi outbox transactional, worker idempotent; xem transition tables/set-based khi bulk load đặc biệt lớn.

## 54. Quy trình chọn UPDATE OF, WHEN hay WHERE

~~~text
Cần bỏ qua cả row UPDATE nếu giá trị không đổi?
    |
    +-- Có -> Đặt điều kiện IS DISTINCT FROM trong WHERE
    |         hoặc thiết kế BEFORE logic/constraint phù hợp
    |
    +-- Không / vẫn muốn UPDATE -> Tiếp tục
                                   |
                Cần trigger vì cột được nêu trong SET?
                     |
                     +-- Có -> UPDATE OF column_list
                     |
                     +-- Không, cần giá trị thật sự đổi
                             |
                             v
                        AFTER UPDATE
                        WHEN OLD.col IS DISTINCT FROM NEW.col
                             |
                Có cần giới hạn cả target list và value?
                     |
                     +-- Có -> UPDATE OF ... + WHEN ...
                     |
               BEFORE trigger có thể sửa field khác?
                     |
                     +-- Có -> Cẩn thận UPDATE OF có thể bỏ sót
~~~

### 54.1. Khi bạn định nghĩa “touched”

Dùng UPDATE OF, kể cả nếu người dùng gán giá trị cũ.

### 54.2. Khi bạn định nghĩa “changed”

Dùng OLD/NEW comparison và xử lý NULL rõ ràng.

### 54.3. Khi bạn muốn ngăn DML thừa

Xem WHERE ngay trong SQL UPDATE, vì AFTER WHEN không hủy thao tác ghi.

### 54.4. Khi bạn cần batch

Xem statement-level trigger/transition tables và SQL theo tập, không chỉ tối ưu WHEN của row triggers.

## 55. Bảng tra cứu nhanh

| Thành phần | Ghi nhớ |
|---|---|
| `WHEN (...)</BT> | Predicate Boolean để lọc trigger invocation |
| `OLD</BT> | Row trước UPDATE/DELETE |
| `NEW</BT> | Row mới của INSERT/UPDATE |
| `IS DISTINCT FROM</BT> | So sánh khác nhau NULL-safe |
| `UPDATE OF x</BT> | Target list nhắc x |
| `UPDATE OF x,y</BT> | Target list nhắc x hoặc y |
| `SET x=x</BT> | Vẫn có thể kích hoạt UPDATE OF x |
| BEFORE sửa NEW.x | Không tự làm UPDATE OF x của cùng UPDATE kích hoạt |
| AFTER UPDATE WHEN old/new khác | Bắt thay đổi thực sau BEFORE triggers |
| AFTER WHEN FALSE | Không queue/gọi trigger function cho hàng đó |
| BEFORE WHEN FALSE | Không gọi function đó |
| UPDATE WHERE value khác | Có thể bỏ row operation không cần thiết |
| `<></BT> và NULL | UNKNOWN |
| `IS DISTINCT FROM</BT> và NULL | TRUE/FALSE xác định |
| JSONB key | So extracted fields trong WHEN |
| Generated column | Có dependency rule riêng với UPDATE OF |
| `FOR EACH ROW</BT> | Một event trên từng row liên quan |
| `FOR EACH STATEMENT</BT> | Event theo statement, kể cả 0 rows |
| Transition tables | OLD TABLE/NEW TABLE cho xử lý tập rows |
| Constraint trigger WHEN | WHEN được xét ngay dù action có thể deferred |
| Trigger recursion | Tránh UPDATE cùng bảng từ trong trigger khi không cần |
| AFTER audit | Ghi log/outbox khi row đã thay đổi |
| BEFORE normalize | Gán NEW và RETURN NEW |
| CHECK/UNIQUE/FK | Ưu tiên cho bất biến được hỗ trợ |
| `pg_trigger</BT> | Metadata trigger |
| `pg_get_triggerdef</BT> | Xem SQL định nghĩa trigger |
| `pg_get_functiondef</BT> | Xem trigger function |
| `pg_stat_user_functions</BT> | Calls/time khi bật tracking |
| `EXPLAIN (ANALYZE)</BT> | Chạy SQL thật, gồm triggers |
| Transactional outbox | Tách gửi external events khỏi DB transaction |
| RLS/GRANT | Authorization, không phải WHEN |
| SECURITY DEFINER | Cần trusted search_path và least privilege |
| UPSERT/MERGE | Trigger firing có quy tắc riêng |
| `CREATE RULE</BT> | Rewrite cơ chế khác trigger |

---

## Kết luận

**`WHEN</BT> và `UPDATE OF</BT> giải quyết hai câu hỏi khác nhau.** `UPDATE OF</BT> hỏi **cột nào được nhắm trong câu UPDATE**, còn `WHEN</BT> hỏi **điều kiện của row/event hiện tại có thỏa hay không**. Vì vậy `UPDATE ... SET status=status</BT> có thể kích hoạt trigger `UPDATE OF status</BT>, dù giá trị status không đổi. Ngược lại, một BEFORE UPDATE trigger có thể thay status trong `NEW</BT> mà không khiến trigger `UPDATE OF status</BT> hoạt động nếu status không nằm trong target list của lệnh gốc.

Khi hợp đồng nghiệp vụ là **giá trị thật sự thay đổi**, mô hình quan trọng cần nhớ là **`AFTER UPDATE FOR EACH ROW WHEN (OLD.column IS DISTINCT FROM NEW.column)</BT>**. Đây là cách so sánh NULL-safe, hữu ích cho audit, outbox hoặc xử lý hậu cập nhật. Nếu còn cần chỉ xử lý statements nhắm cột đó, có thể kết hợp với `UPDATE OF</BT>, nhưng phải hiểu rằng cách kết hợp có thể bỏ sót thay đổi gián tiếp do BEFORE triggers.

Điều kiện WHEN có thể giảm số lần gọi trigger function, đặc biệt với AFTER row triggers vì PostgreSQL tránh lập lịch event khi điều kiện không TRUE. Tuy nhiên, **WHEN không phải WHERE của UPDATE**, không ngăn toàn bộ row update, không thay CHECK/UNIQUE/FK, không tự bảo vệ phân quyền và không làm các external side effects exactly-once. Khi dữ liệu thay đổi hàng loạt, nên đánh giá cả SQL theo tập, transition tables, WHERE để tránh no-op updates và chi phí WAL/index/locks.

Nguyên tắc thiết kế: **xác định rõ bạn muốn bắt “cột được nhắc tới” hay “giá trị thực sự đổi”, chọn timing/level đúng, xử lý NULL bằng IS DISTINCT FROM, kiểm tra ảnh hưởng của BEFORE triggers và đo chi phí trên workload thật**. Nhờ vậy trigger vừa chính xác về nghiệp vụ, vừa tránh những lời gọi không cần thiết và giảm rủi ro audit sai hoặc mất sự kiện quan trọng.
