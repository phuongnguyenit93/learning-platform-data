# Xử lý một câu lệnh thay đổi nhiều hàng

Trong SQL, một câu lệnh `INSERT`, `UPDATE` hoặc `DELETE` **không nhất thiết chỉ thay đổi một hàng**. Một câu `UPDATE ... WHERE tenant_id = 1` có thể cập nhật hàng trăm tài khoản; `DELETE` có thể xóa cả lô đơn hết hạn; `INSERT ... SELECT` có thể chèn hàng nghìn bản ghi. Khi những thao tác đó kích hoạt **trigger**, chương trình phải xử lý đúng **toàn bộ tập hàng bị ảnh hưởng**, không được mặc định mỗi câu lệnh chỉ có một bản ghi.

Ví dụ một hệ thống cần ghi nhận:

- **Nhật ký ở mức từng hàng:** tài khoản nào đổi số dư, từ bao nhiêu thành bao nhiêu.
- **Nhật ký ở mức cả câu lệnh:** trong một lần `UPDATE`, mỗi tenant có bao nhiêu tài khoản được xét, bao nhiêu tài khoản thực sự đổi số dư và tổng chênh lệch là bao nhiêu.
- **Quy tắc an toàn:** nếu một hàng không hợp lệ, thao tác phải thất bại theo ngữ nghĩa transaction, không được âm thầm ghi nhận một phần kết quả.

Vấn đề xuất hiện khi người viết trigger dùng một biến duy nhất để nhận ID, viết logic chỉ xử lý một hàng đầu tiên, hoặc thực hiện phép tính tổng dựa trên trạng thái trung gian của bảng trong khi một câu lệnh đang thay đổi nhiều hàng.

Bài học thuộc chương **Trigger** của **Database SQL**, lấy **PostgreSQL** làm môi trường thực hành chính. Ta sẽ phân biệt **trigger theo hàng** (*row-level trigger*) và **trigger theo câu lệnh** (*statement-level trigger*), sử dụng `OLD`/`NEW`, **transition tables** (`OLD TABLE` và `NEW TABLE`), xây ví dụ ghi audit và tổng hợp theo tập, rồi đối chiếu **SQL Server, Oracle, MySQL và SQLite**.

> **Mục tiêu quan trọng nhất:** xác định trigger đang nhận **một cặp hàng cũ/mới** hay **một tập nhiều hàng**, và viết logic tương ứng. Một câu SQL thay đổi 0, 1 hay 10.000 hàng đều phải có hành vi rõ ràng.

## 1. Một câu DML có thể ảnh hưởng bao nhiêu hàng?

Xem ba lệnh:

```sql
-- Có thể thay đổi đúng một hàng nếu account_id là PRIMARY KEY.
UPDATE accounts_demo
SET balance = balance + 10
WHERE account_id = 101;

-- Có thể thay đổi nhiều hàng.
UPDATE accounts_demo
SET balance = balance + 10
WHERE tenant_id = 1;

-- Có thể không thay đổi hàng nào nếu không có account_id 999.
UPDATE accounts_demo
SET balance = balance + 10
WHERE account_id = 999;
```

Các lệnh này đều là **một statement**. Khác biệt nằm ở **số hàng khớp điều kiện** và được cập nhật thành công.

| Số hàng cập nhật | Điều xảy ra với trigger theo hàng | Điều xảy ra với trigger theo câu lệnh |
|---:|---|---|
| 0 | Không có hàng nào để trigger chạy | Trigger theo câu lệnh vẫn có thể chạy **một lần** |
| 1 | Chạy cho 1 hàng | Chạy 1 lần |
| 3 | Chạy cho 3 hàng | Chạy 1 lần |
| 10.000 | Chạy cho 10.000 hàng | Chạy 1 lần |

Bảng này mô tả hành vi phổ biến ở **PostgreSQL và những DBMS có cả hai cấp trigger**. Chi tiết một trigger có chạy hay không còn phụ thuộc **sự kiện**, `WHEN`, lựa chọn cột `UPDATE OF`, trạng thái kích hoạt trigger và các tính năng đặc biệt của DBMS.

### 1.1. Đếm “hàng được cập nhật” khác “giá trị thực sự thay đổi”

Câu:

```sql
UPDATE accounts_demo
SET balance = balance
WHERE account_id IN (101, 102);
```

vẫn là một **câu `UPDATE` nhắm vào hai hàng**, dù `balance` giữ nguyên giá trị số học. Tùy DBMS, lệnh có thể vẫn kích hoạt trigger cập nhật và báo hai hàng bị tác động.

Nếu yêu cầu audit là “chỉ ghi khi số dư thật sự khác”, trigger phải **so sánh giá trị trước/sau**. Không thể mặc định mọi hàng đi qua `UPDATE` đều có một thay đổi nghiệp vụ.

### 1.2. Một dòng SQL không đồng nghĩa một đơn vị dữ liệu

Những lệnh dưới đây cũng có thể xử lý **nhiều hàng trong một statement**:

```sql
INSERT INTO target_table (id, value)
SELECT id, value
FROM staging_table
WHERE is_valid = TRUE;
```

```sql
DELETE FROM order_items
WHERE order_id IN (101, 102, 103);
```

Với `MERGE`, một statement có thể chọn các hành động chèn/sửa/xóa khác nhau, nhưng cách kích hoạt trigger theo từng loại hành động còn tùy **DBMS và phiên bản**. Không được suy ra số lần trigger từ số dòng mã SQL hay số mệnh đề `WHEN` một cách máy móc.

## 2. Hai cấp trigger: FOR EACH ROW và FOR EACH STATEMENT

### 2.1. Trigger theo hàng

Trong PostgreSQL:

```sql
CREATE TRIGGER trigger_name
AFTER UPDATE ON table_name
FOR EACH ROW
EXECUTE FUNCTION trigger_function();
```

Nếu câu `UPDATE` tác động ba hàng, trigger theo hàng được kích hoạt **cho từng hàng**. Trong một lần gọi:

- `OLD` biểu diễn **giá trị trước thay đổi của hàng đang xét**.
- `NEW` biểu diễn **giá trị sau thay đổi của cùng hàng**.
- Logic chỉ nhìn trực tiếp **một cặp OLD/NEW**.

Đây là cách thích hợp để ghi một dòng nhật ký cho **mỗi bản ghi có thay đổi**, hoặc kiểm tra điều kiện trên từng hàng.

### 2.2. Trigger theo câu lệnh

Trong PostgreSQL:

```sql
CREATE TRIGGER trigger_name
AFTER UPDATE ON table_name
FOR EACH STATEMENT
EXECUTE FUNCTION trigger_function();
```

Một lệnh `UPDATE` tác động ba hàng vẫn kích hoạt trigger **một lần** ở cấp statement.

Ở cấp này:

- Không có một cặp hàng `OLD`/`NEW` đại diện tự nhiên cho cả lệnh.
- `OLD`/`NEW` của trigger theo hàng **không phải danh sách ba hàng**.
- Nếu cần nhìn toàn bộ tập hàng trước/sau, PostgreSQL hỗ trợ **transition relations** cho các trigger `AFTER` phù hợp.

### 2.3. Mỗi cấp dùng cho mục tiêu nào?

| Mục tiêu | Trigger theo hàng | Trigger theo câu lệnh |
|---|---|---|
| Kiểm tra số dư không âm ở từng tài khoản | Phù hợp với `BEFORE EACH ROW` | Có thể cần cách kiểm tra tập khác |
| Ghi một audit record cho mỗi tài khoản đổi số dư | Phù hợp | Phù hợp nếu dùng transition table và SQL set-based |
| Tính một tổng chênh lệch cho toàn lệnh | Có thể nhưng phải tích lũy an toàn | Thường tự nhiên hơn khi có tập chuyển đổi |
| Thực thi một thao tác tổng hợp cho 10.000 hàng | 10.000 lần gọi, dễ tốn chi phí | Một lần gọi, có thể xử lý tập |
| Phân tích lệnh `UPDATE` không khớp hàng nào | Không có lần gọi row trigger | Có thể chạy, tập hàng chuyển đổi rỗng |

**Lưu ý:** một trigger theo câu lệnh không tự nhiên “nhanh hơn mọi trigger theo hàng”. Nó có thể thực hiện một phép quét rất nặng hoặc gây khóa/tranh chấp nếu viết không phù hợp. Điểm mạnh là **có cơ hội xử lý theo tập** thay vì chạy cùng một truy vấn lặp lại N lần.

## 3. Dữ liệu mẫu: năm tài khoản thuộc hai tenant

Phần chính dùng **PostgreSQL**. Tạo ba bảng độc lập với hệ thống thật:

1. `accounts_demo` — số dư hiện tại.
2. `account_row_audit_demo` — nhật ký từng hàng thay đổi số dư.
3. `account_statement_audit_demo` — nhật ký tổng hợp theo tenant cho mỗi câu `UPDATE`.

### 3.1. Tạo bảng tài khoản

```sql
CREATE TABLE accounts_demo (
    account_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL,
    balance NUMERIC(14, 2) NOT NULL
        CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

`account_id` là khóa chính, nghĩa là **một account ID xác định tối đa một hàng**. Trong bài, `account_id` và `tenant_id` được xem là **định danh ổn định**, không thay đổi khi cập nhật số dư. Giả định này quan trọng khi nối `OLD TABLE` với `NEW TABLE` ở phần sau.

### 3.2. Nạp dữ liệu

```sql
INSERT INTO accounts_demo
    (account_id, tenant_id, owner_name, balance)
VALUES
    (101, 1, 'An',   100.00),
    (102, 1, 'Binh', 200.00),
    (103, 1, 'Chi',   80.00),
    (201, 2, 'Dung',  50.00),
    (202, 2, 'Em',   120.00);
```

| account_id | tenant_id | owner_name | balance |
|---:|---:|---|---:|
| 101 | 1 | An | 100.00 |
| 102 | 1 | Binh | 200.00 |
| 103 | 1 | Chi | 80.00 |
| 201 | 2 | Dung | 50.00 |
| 202 | 2 | Em | 120.00 |

Ban đầu có **5 tài khoản**: tenant 1 có tổng số dư **380.00**; tenant 2 có tổng số dư **170.00**. Đây là dữ liệu minh họa, không phải hệ thống sổ cái tài chính thực tế.

### 3.3. Tạo bảng audit từng hàng

```sql
CREATE TABLE account_row_audit_demo (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id INTEGER NOT NULL,
    old_balance NUMERIC(14, 2) NOT NULL,
    new_balance NUMERIC(14, 2) NOT NULL,
    delta NUMERIC(14, 2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Mỗi bản ghi audit có:

- `account_id`: hàng đích đã thay đổi.
- `old_balance` và `new_balance`: giá trị trước/sau.
- `delta = new_balance - old_balance`: chênh lệch của hàng.
- `recorded_at`: thời điểm nhật ký.

### 3.4. Tạo bảng audit theo statement

```sql
CREATE TABLE account_statement_audit_demo (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    matched_rows BIGINT NOT NULL,
    changed_rows BIGINT NOT NULL,
    total_delta NUMERIC(14, 2) NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
```

Trong bảng này:

- `matched_rows`: số hàng tenant đã được câu `UPDATE` tác động, **kể cả những hàng có balance không đổi**.
- `changed_rows`: số hàng có `balance` thực sự khác trước.
- `total_delta`: tổng chênh lệch số dư sau trừ trước.

Một câu `UPDATE` nhiều tenant có thể tạo **một dòng tổng hợp cho mỗi tenant**, không nhất thiết đúng một dòng audit chung. Số dòng audit cuối cùng phụ thuộc **các nhóm tenant có hàng được cập nhật**.

> **Tái lập thực hành:** tạo schema và dữ liệu mẫu **một lần**. Các bài thử `UPDATE` sau đây được đặt trong `BEGIN ... ROLLBACK` để có thể thử lại từ số dư ban đầu. Nếu muốn làm sạch để bắt đầu hoàn toàn mới, hãy dùng một schema/database thực hành riêng và quản lý DDL có chủ đích, không chạy lệnh xóa trên bảng thật.

## 4. Tình huống chính: một UPDATE tác động hai tài khoản

Giả sử muốn chuyển **30 đơn vị** từ account 101 sang account 102 trong cùng tenant 1:

```sql
UPDATE accounts_demo
SET balance = CASE account_id
    WHEN 101 THEN balance - 30.00
    WHEN 102 THEN balance + 30.00
    ELSE balance
END
WHERE account_id IN (101, 102);
```

Đây là **một câu `UPDATE`** với điều kiện chọn hai hàng.

| account_id | Balance trước | Balance sau | Delta |
|---:|---:|---:|---:|
| 101 | 100.00 | 70.00 | -30.00 |
| 102 | 200.00 | 230.00 | +30.00 |

Tổng tenant 1 giữ nguyên **380.00**.

Kết quả mong muốn của hệ thống audit:

- **Hai dòng row audit**: mỗi tài khoản một dòng.
- **Một dòng statement audit của tenant 1**: `matched_rows=2`, `changed_rows=2`, `total_delta=0`.

### 4.1. Vì sao không thể giả định chỉ có một OLD/NEW cho cả lệnh?

Một trigger theo hàng gọi trên account 101 thấy:

```text
OLD.account_id = 101
OLD.balance    = 100
NEW.account_id = 101
NEW.balance    = 70
```

Ở lần gọi trên account 102, nó thấy:

```text
OLD.account_id = 102
OLD.balance    = 200
NEW.account_id = 102
NEW.balance    = 230
```

Không có “hàng OLD chung” mang hai số dư trước hoặc “hàng NEW chung” mang hai số dư sau. Nếu muốn tổng `-30 + 30 = 0` thì phải **gom dữ liệu nhiều hàng** theo cách có kiểm soát, không lấy giá trị từ một lần gọi row trigger rồi coi đó là toàn bộ câu `UPDATE`.

### 4.2. Không dựa vào thứ tự xử lý hàng

PostgreSQL **không hứa** rằng khi cập nhật `WHERE account_id IN (101, 102)`, trigger hàng 101 phải chạy trước 102. Kế hoạch thực thi, cách lưu trữ và các thay đổi khác có thể ảnh hưởng thứ tự.

Vì thế, logic dạng:

```text
Nếu account đầu tiên thì khởi tạo tổng;
nếu account cuối cùng thì ghi tổng;
```

là nguy hiểm nếu không có một cơ chế xác định chính xác đầu/cuối và bảo vệ trạng thái. Trigger theo statement với tập thay đổi là cách tự nhiên hơn cho ví dụ tổng hợp.

## 5. PostgreSQL: BEFORE ROW trigger kiểm tra từng hàng

Trước khi ghi audit, ta có thể khai báo một **trigger kiểm tra hợp lệ**. Bảng đã có `CHECK (balance >= 0)`; trigger này minh họa cách kiểm soát ở mức hàng bằng `NEW`, không nhằm thay thế constraint.

### 5.1. Tạo hàm trigger

```sql
CREATE OR REPLACE FUNCTION check_account_balance_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.balance < 0 THEN
        RAISE EXCEPTION
            'Account % would have negative balance %',
            NEW.account_id, NEW.balance
            USING ERRCODE = '23514';
    END IF;

    NEW.updated_at := clock_timestamp();

    RETURN NEW;
END;
$$;
```

### 5.2. Gắn BEFORE UPDATE FOR EACH ROW

```sql
CREATE TRIGGER trg_account_check_demo
BEFORE UPDATE OF balance ON accounts_demo
FOR EACH ROW
EXECUTE FUNCTION check_account_balance_demo();
```

Trong từng lần gọi:

1. `NEW.balance` chứa giá trị đề xuất sau `SET` cho hàng đang xét.
2. Nếu âm, `RAISE EXCEPTION` khiến câu `UPDATE` không hoàn tất thành công.
3. Nếu hợp lệ, trigger cập nhật `NEW.updated_at`.
4. `RETURN NEW` cho phép thao tác với hàng đã được chuẩn bị tiếp tục.

Với **hai hàng** 101 và 102 của ví dụ chuyển số dư, trigger có thể chạy **hai lần**. Với `UPDATE WHERE account_id=999`, nó chạy **0 lần**.

### 5.3. RETURN NULL trong BEFORE ROW không giống RAISE EXCEPTION

Một trigger `BEFORE ROW` trên PostgreSQL có thể trả `NULL` để **bỏ qua thao tác đối với hàng đang xét**. Đây không phải lỗi bắt buộc, và có thể dẫn đến số hàng thực sự được cập nhật ít hơn số hàng ban đầu khớp `WHERE`.

Ngược lại, `RAISE EXCEPTION` ném lỗi; nếu không được xử lý trong ngữ cảnh thích hợp, nó làm câu SQL thất bại và ảnh hưởng transaction.

Đối với quy tắc “không được âm số dư”, **báo lỗi** thường rõ hơn âm thầm bỏ qua hàng. Không dùng `RETURN NULL` để “cho qua” một hành động nhạy cảm mà ứng dụng tưởng đã hoàn tất.

### 5.4. UPDATE OF kiểm tra cột được nêu trong SET

`BEFORE UPDATE OF balance` liên quan đến việc **cột `balance` được chỉ định trong câu lệnh `UPDATE`**, không bảo đảm giá trị cuối khác giá trị đầu.

Ví dụ:

```sql
UPDATE accounts_demo
SET balance = balance
WHERE account_id = 101;
```

vẫn có thể kích hoạt trigger `UPDATE OF balance`, vì `balance` xuất hiện trong `SET`. Nếu muốn biết số dư **thật sự thay đổi**, cần so sánh `OLD.balance` và `NEW.balance`.

## 6. PostgreSQL: AFTER ROW trigger ghi audit đúng cho N hàng

Ta tạo một row-level trigger để ghi **một audit record cho từng hàng có số dư thay đổi**.

### 6.1. Hàm nhận OLD và NEW của từng hàng

```sql
CREATE OR REPLACE FUNCTION log_account_row_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO account_row_audit_demo (
        account_id, old_balance, new_balance, delta
    )
    VALUES (
        NEW.account_id,
        OLD.balance,
        NEW.balance,
        NEW.balance - OLD.balance
    );

    RETURN NULL;
END;
$$;
```

Vì đây là **AFTER trigger**, giá trị trả về không được dùng để sửa hàng đích; `RETURN NULL` ở đây không có tác dụng “bỏ qua update” như trong `BEFORE ROW`. Hành động có ích của trigger là câu `INSERT` vào bảng audit.

### 6.2. Chỉ ghi khi giá trị thật sự khác

```sql
CREATE TRIGGER trg_account_row_audit_demo
AFTER UPDATE OF balance ON accounts_demo
FOR EACH ROW
WHEN (OLD.balance IS DISTINCT FROM NEW.balance)
EXECUTE FUNCTION log_account_row_demo();
```

Điều kiện `WHEN` lọc những lần gọi có `balance` không thay đổi:

- Khi `100 → 70`: ghi.
- Khi `200 → 230`: ghi.
- Khi `100 → 100`: không ghi.

PostgreSQL hỗ trợ phép so sánh `IS DISTINCT FROM` xử lý cả trường hợp `NULL` theo ngữ nghĩa rõ ràng. Trong bảng mẫu, `balance` là `NOT NULL`, nhưng kỹ thuật này vẫn hữu ích khi thiết kế trigger cho những cột nullable khác.

### 6.3. Thử một UPDATE ảnh hưởng hai hàng

```sql
BEGIN;

UPDATE accounts_demo
SET balance = CASE account_id
    WHEN 101 THEN balance - 30.00
    WHEN 102 THEN balance + 30.00
    ELSE balance
END
WHERE account_id IN (101, 102);

SELECT
    account_id, old_balance, new_balance, delta
FROM account_row_audit_demo
ORDER BY audit_id;

ROLLBACK;
```

Kết quả về **tập hàng** của audit:

| account_id | old_balance | new_balance | delta |
|---:|---:|---:|---:|
| 101 | 100.00 | 70.00 | -30.00 |
| 102 | 200.00 | 230.00 | +30.00 |

**Không dựa vào `ORDER BY audit_id` để khẳng định account 101 luôn được trigger gọi trước 102.** Bảng trên mô tả hai bản ghi kỳ vọng, còn thứ tự vật lý/lần gọi không được dùng làm quy tắc nghiệp vụ.

Sau `ROLLBACK`, số dư và các dòng audit được chèn trong transaction thử nghiệm đều được hoàn tác. Các bộ đếm sequence/identity có thể vẫn có khoảng trống ID vì cơ chế cấp số không nhất thiết rollback theo giao dịch; đừng dùng ID audit liên tục làm điều kiện đúng sai.

### 6.4. Tại sao không dùng một biến duy nhất để ghi N hàng?

Một đoạn trigger sai về tư duy có dạng:

```sql
-- Ý tưởng sai cho statement-level trigger cần biết toàn bộ hàng:
-- SELECT account_id INTO v_account_id FROM changed_rows;
-- INSERT INTO log ... VALUES (v_account_id);
```

Nếu tập thay đổi chứa 100 tài khoản, **một biến `v_account_id` chỉ chứa một giá trị**, không tự biến thành danh sách 100 ID. Với row trigger, mỗi lần gọi có một `NEW.account_id` và có thể ghi một audit record; với statement trigger, phải **xử lý tập** bằng `INSERT ... SELECT`, tổng hợp hoặc vòng lặp có chủ đích.

## 7. PostgreSQL: transition tables cho trigger theo câu lệnh

Khi cần xử lý **mọi hàng bị thay đổi trong một statement**, PostgreSQL hỗ trợ **transition tables** (còn gọi *transition relations*) cho các `AFTER` trigger phù hợp.

Chúng cho phép tham chiếu:

- **`OLD TABLE`**: tập các phiên bản hàng **trước** thay đổi.
- **`NEW TABLE`**: tập các phiên bản hàng **sau** thay đổi.

Với `UPDATE`, một cặp transition tables có thể chứa **nhiều hàng** tương ứng với những bản ghi được cập nhật.

### 7.1. So sánh OLD/NEW và OLD TABLE/NEW TABLE

| Khái niệm | Trigger theo hàng | Trigger theo câu lệnh có transition table |
|---|---|---|
| Giá trị cũ | `OLD.balance` của một hàng | `old_rows` là quan hệ gồm nhiều hàng cũ |
| Giá trị mới | `NEW.balance` của một hàng | `new_rows` là quan hệ gồm nhiều hàng mới |
| Đối tượng xử lý | Một hàng mỗi lần gọi | Tập hàng của statement |
| Ghi audit cho N hàng | Hàm chạy N lần, mỗi lần INSERT một dòng | Một `INSERT ... SELECT` có thể ghi N dòng |
| Tính tổng delta của statement | Phải tích lũy và điều phối cẩn thận | `SUM(new.balance - old.balance)` trên tập ghép theo khóa |

**Quan trọng:** transition table không phải bảng thường lưu vĩnh viễn. Nó là quan hệ dữ liệu **được hệ quản trị cung cấp cho lần kích hoạt trigger**, không tồn tại như một bảng staging độc lập ngoài ngữ cảnh đó.

### 7.2. Các điều kiện sử dụng cần nhớ

Trong PostgreSQL:

- Transition relations được khai báo bằng `REFERENCING OLD TABLE AS ... NEW TABLE AS ...` khi tạo trigger tương ứng.
- Đây là khả năng của các **`AFTER` trigger** trên bảng và trong những tình huống được hỗ trợ; không sử dụng nguyên cú pháp này cho mọi `BEFORE` trigger hoặc mọi đối tượng.
- Với `INSERT` thường có **NEW TABLE**; với `DELETE` thường có **OLD TABLE**; với `UPDATE` có thể có **cả hai**.
- Một `UPDATE` trigger có transition relation **không được chỉ định danh sách cột kiểu `UPDATE OF balance`** theo giới hạn của PostgreSQL.
- Cần lưu ý các quy tắc bổ sung về constraint trigger, partition, sự kiện phối hợp và phiên bản PostgreSQL.

Vì vậy ở phần tiếp theo ta khai báo **`AFTER UPDATE ON accounts_demo`**, không dùng `AFTER UPDATE OF balance`, rồi kiểm tra giá trị thay đổi **bên trong logic trigger**.

## 8. Xây statement-level trigger tổng hợp theo tenant

Yêu cầu: sau **mỗi câu `UPDATE`** trên `accounts_demo`, ghi vào `account_statement_audit_demo`:

- Tenant nào có hàng được cập nhật.
- Bao nhiêu hàng được cập nhật trong tenant đó.
- Bao nhiêu hàng có số dư thực sự thay đổi.
- Tổng chênh lệch `NEW.balance - OLD.balance`.

### 8.1. Hàm trigger xử lý tập OLD/NEW

```sql
CREATE OR REPLACE FUNCTION log_account_statement_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_source_rows BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_source_rows
    FROM new_rows;

    RAISE NOTICE 'Statement UPDATE; rows in transition table=%',
        v_source_rows;

    INSERT INTO account_statement_audit_demo (
        tenant_id,
        matched_rows,
        changed_rows,
        total_delta
    )
    SELECT
        n.tenant_id,
        COUNT(*) AS matched_rows,
        COUNT(*) FILTER (
            WHERE n.balance IS DISTINCT FROM o.balance
        ) AS changed_rows,
        COALESCE(SUM(n.balance - o.balance), 0) AS total_delta
    FROM new_rows AS n
    JOIN old_rows AS o
      ON o.account_id = n.account_id
    GROUP BY n.tenant_id;

    RETURN NULL;
END;
$$;
```

Giải thích:

1. `new_rows` và `old_rows` là tên ta **sẽ khai báo trong trigger**, không phải hai bảng thường đã tạo ở mục 3.
2. `SELECT COUNT(*) FROM new_rows` cho số hàng được đưa vào transition table của lần chạy này.
3. `JOIN ... ON o.account_id = n.account_id` ghép phiên bản **cũ và mới của cùng tài khoản**.
4. `COUNT(*)` đếm hàng được câu `UPDATE` tác động.
5. `COUNT(*) FILTER (WHERE ... IS DISTINCT FROM ...)` đếm hàng có số dư thực sự khác.
6. `SUM(n.balance - o.balance)` tính tổng chênh lệch, có thể bằng **0 dù nhiều hàng thay đổi**.
7. `GROUP BY n.tenant_id` tạo một hàng tổng hợp cho mỗi tenant có hàng tham gia statement.

**Giả định thiết kế:** `account_id` không thay đổi trong statement. Nếu cập nhật khóa `account_id`, phép JOIN old/new theo `account_id` có thể **không ghép được cùng hàng**, khiến kết quả tổng hợp sai. Với bảng thật, phải chọn khóa ổn định hoặc thiết kế riêng cách theo dõi thay đổi khóa.

Đồng thời, ví dụ giả định `tenant_id` không thay đổi; nếu chuyển tài khoản giữa hai tenant trong cùng `UPDATE`, cần quy tắc rõ ràng về việc chênh lệch được tính theo **tenant cũ, tenant mới hay cả hai**. Chỉ nhóm theo `n.tenant_id` sẽ quy toàn bộ delta cho tenant mới, không phải kế toán chuyển số dư giữa các tenant.

### 8.2. Gắn trigger với hai transition tables

```sql
CREATE TRIGGER trg_account_statement_audit_demo
AFTER UPDATE ON accounts_demo
REFERENCING
    OLD TABLE AS old_rows
    NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION log_account_statement_demo();
```

Lúc này ta có:

- `trg_account_check_demo`: **BEFORE ROW**, kiểm tra và đặt `updated_at`.
- `trg_account_row_audit_demo`: **AFTER ROW**, ghi audit khi `balance` đổi.
- `trg_account_statement_audit_demo`: **AFTER STATEMENT**, nhận tập hàng cũ/mới và tổng hợp.

Ba trigger cùng tham gia quá trình cập nhật, nhưng phục vụ **ba mục tiêu khác nhau**.

### 8.3. Tại sao statement trigger không được dùng NEW.balance?

Trong trigger cấp statement, không có “một hàng NEW” đại diện cho cả lệnh:

```sql
-- Sai tư duy trong statement-level trigger:
-- v_delta := NEW.balance - OLD.balance;
```

Thay vào đó, ta viết SQL trên **tập**:

```sql
SELECT
    SUM(n.balance - o.balance)
FROM new_rows AS n
JOIN old_rows AS o
  ON n.account_id = o.account_id;
```

Nếu nguồn có N tài khoản, phép tổng hợp xét toàn bộ N cặp khóa phù hợp, không bị phụ thuộc vào việc một dòng trigger chạy trước hay sau dòng khác.

### 8.4. Vì sao COUNT(*) và COUNT(changed) khác nhau?

Nếu câu `UPDATE` nhắm đến một account nhưng đặt lại cùng số dư:

```sql
UPDATE accounts_demo
SET balance = balance
WHERE account_id = 101;
```

thì:

- `matched_rows = 1` vì câu `UPDATE` tác động hàng 101.
- `changed_rows = 0` vì `OLD.balance = NEW.balance`.
- `total_delta = 0`.

Tên `matched_rows` trong bài là **số hàng đã đi qua thao tác cập nhật của statement**, không phải “mọi hàng từng thỏa điều kiện ở một lần SELECT riêng”. Các trigger `BEFORE ROW` có khả năng bỏ qua hàng, các quy tắc khác và truy cập đồng thời có thể làm các khái niệm đó khác nhau.

## 9. Thực hành: một statement có hai hàng thay đổi

Sau khi tạo các trigger ở mục 5, 6 và 8, chạy transaction thử:

```sql
BEGIN;

UPDATE accounts_demo
SET balance = CASE account_id
    WHEN 101 THEN balance - 30.00
    WHEN 102 THEN balance + 30.00
    ELSE balance
END
WHERE account_id IN (101, 102);

SELECT account_id, balance
FROM accounts_demo
WHERE account_id IN (101, 102)
ORDER BY account_id;

SELECT
    account_id, old_balance, new_balance, delta
FROM account_row_audit_demo
ORDER BY account_id;

SELECT
    tenant_id, matched_rows, changed_rows, total_delta
FROM account_statement_audit_demo
ORDER BY audit_id;

ROLLBACK;
```

### 9.1. Kết quả bảng đích trong giao dịch

| account_id | balance |
|---:|---:|
| 101 | 70.00 |
| 102 | 230.00 |

### 9.2. Kết quả row audit

| account_id | old_balance | new_balance | delta |
|---:|---:|---:|---:|
| 101 | 100.00 | 70.00 | -30.00 |
| 102 | 200.00 | 230.00 | +30.00 |

Có **2 dòng audit theo hàng** vì cả hai hàng có số dư khác.

### 9.3. Kết quả statement audit

| tenant_id | matched_rows | changed_rows | total_delta |
|---:|---:|---:|---:|
| 1 | 2 | 2 | 0.00 |

Có **1 dòng statement audit cho tenant 1** vì cả hai hàng thuộc cùng tenant.

**Điểm dễ nhầm:** `total_delta = 0` không có nghĩa “không có thay đổi”. Tài khoản 101 giảm 30, tài khoản 102 tăng 30; **hai thay đổi triệt tiêu nhau ở tổng**. Vì vậy hệ thống giữ cả `changed_rows` và dữ liệu audit chi tiết.

Sau `ROLLBACK`:

- Số dư về 100/200.
- Hai dòng row audit trong transaction bị hủy.
- Một dòng statement audit trong transaction bị hủy.

Như vậy thay đổi và nhật ký ghi trong **cùng database transaction** có thể được commit hoặc rollback cùng nhau.

## 10. Một UPDATE tác động ba hàng, hai tenant hoặc không hàng nào

### 10.1. Ba hàng cùng tenant

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 10.00
WHERE tenant_id = 1;

SELECT
    tenant_id, matched_rows, changed_rows, total_delta
FROM account_statement_audit_demo
ORDER BY audit_id;

ROLLBACK;
```

Với trạng thái ban đầu:

- Account 101: 100 → 110.
- Account 102: 200 → 210.
- Account 103: 80 → 90.
- Row audit ghi **3 dòng**.
- Statement audit ghi **1 dòng** cho tenant 1: `matched_rows=3`, `changed_rows=3`, `total_delta=30`.

### 10.2. Một lệnh cập nhật hai tenant

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 5.00;

SELECT
    tenant_id, matched_rows, changed_rows, total_delta
FROM account_statement_audit_demo
ORDER BY tenant_id;

ROLLBACK;
```

Câu `UPDATE` không có `WHERE`, nên trên dữ liệu mẫu nó cập nhật **cả 5 tài khoản**.

| tenant_id | matched_rows | changed_rows | total_delta |
|---:|---:|---:|---:|
| 1 | 3 | 3 | 15.00 |
| 2 | 2 | 2 | 10.00 |

Row trigger ghi **5 dòng**. Statement trigger chạy **một lần** nhưng câu `INSERT ... SELECT ... GROUP BY` ghi **2 dòng tổng hợp**.

**Một lần gọi statement trigger không đồng nghĩa một hàng audit.** Nó có thể ghi 0, 1 hoặc nhiều dòng tùy dữ liệu nguồn và phép nhóm.

### 10.3. Câu UPDATE không khớp hàng nào

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 10.00
WHERE account_id = 999;

SELECT COUNT(*) AS row_audit_count
FROM account_row_audit_demo;

SELECT COUNT(*) AS statement_audit_count
FROM account_statement_audit_demo;

ROLLBACK;
```

Trong bộ dữ liệu mới tạo và không còn audit từ bài khác:

- `UPDATE` tác động **0 hàng**.
- Không có row trigger nào được gọi.
- Statement trigger **vẫn được gọi một lần**.
- `new_rows` và `old_rows` đều rỗng.
- Hàm statement trigger có thể in `rows in transition table=0`.
- `INSERT ... SELECT ... GROUP BY` không tạo dòng audit vì không có tenant nào có hàng.

Vì vậy **0 dòng ở bảng statement audit không chứng minh statement trigger không chạy**. Nó có thể chạy và quyết định không tạo record.

### 10.4. Hàng được UPDATE nhưng số dư không đổi

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance
WHERE account_id IN (101, 102);

SELECT
    tenant_id, matched_rows, changed_rows, total_delta
FROM account_statement_audit_demo
ORDER BY audit_id;

ROLLBACK;
```

Kết quả statement audit:

| tenant_id | matched_rows | changed_rows | total_delta |
|---:|---:|---:|---:|
| 1 | 2 | 0 | 0.00 |

Row audit **không thêm dòng nào**, do `WHEN (OLD.balance IS DISTINCT FROM NEW.balance)` là false. Trigger `BEFORE UPDATE OF balance` vẫn có thể đặt lại `updated_at` cho hai hàng; do đó “số dư không đổi” **không có nghĩa không có thuộc tính nào khác thay đổi**.

## 11. Set-based audit: ghi N dòng bằng một INSERT ... SELECT

Ví dụ chính dùng **row trigger** để ghi `account_row_audit_demo` và **statement trigger** để ghi `account_statement_audit_demo`. Nhưng nếu mục tiêu là ghi **N dòng chi tiết** và muốn xử lý theo tập, PostgreSQL có thể dùng transition tables:

```sql
-- Đoạn này minh họa phần thân một AFTER UPDATE
-- statement-level trigger có OLD TABLE/NEW TABLE.
INSERT INTO account_row_audit_demo (
    account_id, old_balance, new_balance, delta
)
SELECT
    n.account_id,
    o.balance,
    n.balance,
    n.balance - o.balance
FROM new_rows AS n
JOIN old_rows AS o
  ON o.account_id = n.account_id
WHERE n.balance IS DISTINCT FROM o.balance;
```

Nếu statement cập nhật 10.000 tài khoản, câu `INSERT ... SELECT` có thể ghi những dòng audit tương ứng **trong một thao tác set-based**, thay vì một câu `INSERT` riêng trong mỗi lần gọi row trigger.

### 11.1. Không gắn đồng thời hai trigger audit giống nhau một cách vô ý

Trong bộ thực hành, `trg_account_row_audit_demo` **đã ghi audit từng hàng**. Nếu bạn gắn thêm statement trigger chạy đoạn `INSERT ... SELECT` ở trên **vào cùng bảng audit** mà không tắt hoặc thay thế trigger cũ, mỗi hàng đổi số dư có thể bị ghi **hai lần**.

Đoạn code ở mục 11 là một **phương án thiết kế thay thế**, không phải bước tiếp theo bắt buộc của bộ setup chính.

Muốn chuyển từ row audit sang statement audit chi tiết, cần quản lý schema/migration để chỉ có cơ chế ghi hợp lệ được bật, xác minh không có dữ liệu trùng do trigger cũ, và thử mọi loại DML được hỗ trợ.

### 11.2. Vì sao set-based thường dễ tổng hợp hơn?

SQL có các phép:

```sql
COUNT(*)
SUM(...)
GROUP BY ...
JOIN ...
FILTER (WHERE ...)
```

chúng được thiết kế để thao tác **nhiều hàng cùng lúc**. Với bài toán tổng tiền, số lượng và audit tập, việc để database xử lý tập thường rõ hơn việc xây một biến tích lũy bên ngoài từng lần kích hoạt row trigger.

Tuy nhiên, ghi audit chi tiết vẫn tạo một hàng log cho mỗi thay đổi cần lưu, nên không thể loại bỏ chi phí lưu trữ chỉ bằng cách chuyển sang statement trigger.

## 12. INSERT nhiều hàng và DELETE nhiều hàng

Các nguyên tắc tương tự áp dụng cho `INSERT` và `DELETE`, nhưng tên quan hệ chuyển đổi khác.

### 12.1. INSERT có NEW, không có OLD của hàng đích

Với row-level `AFTER INSERT`:

- `NEW` là hàng được chèn.
- Không có một hàng cũ `OLD` tương ứng vì hàng vừa được tạo.

Với statement-level `AFTER INSERT` có transition table, PostgreSQL có thể cung cấp **`NEW TABLE`** là toàn bộ hàng mới được chèn bởi statement.

Ví dụ khái niệm:

```sql
CREATE OR REPLACE FUNCTION log_bulk_insert_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_inserted BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_inserted
    FROM inserted_rows;

    RAISE NOTICE 'Rows inserted in statement=%', v_inserted;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_bulk_insert_demo
AFTER INSERT ON accounts_demo
REFERENCING NEW TABLE AS inserted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION log_bulk_insert_demo();
```

Nếu chạy:

```sql
BEGIN;

INSERT INTO accounts_demo
    (account_id, tenant_id, owner_name, balance)
VALUES
    (301, 3, 'Lan', 40.00),
    (302, 3, 'Minh', 60.00),
    (303, 3, 'Nhi', 80.00);

ROLLBACK;
```

trigger statement chạy **một lần**, và `inserted_rows` chứa **3 hàng** trong trường hợp này. Nếu lệnh chèn 0 hàng như `INSERT ... SELECT ... WHERE FALSE`, statement trigger vẫn có thể chạy với transition table rỗng.

**Tách biệt:** trigger INSERT trên `accounts_demo` không tự kích hoạt trigger UPDATE đã tạo trước đó chỉ vì nó thay đổi số hàng của bảng; trigger được xác định theo **loại sự kiện**.

### 12.2. DELETE có OLD, không có NEW của hàng đích

Với row-level `AFTER DELETE`:

- `OLD` là hàng bị xóa.
- Không có một hàng mới `NEW` cho bản ghi đã xóa.

Statement-level `AFTER DELETE` có thể tham chiếu toàn bộ các hàng bị xóa bằng `OLD TABLE`:

```sql
CREATE OR REPLACE FUNCTION log_bulk_delete_demo()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_deleted BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_deleted
    FROM deleted_rows;

    RAISE NOTICE 'Rows deleted in statement=%', v_deleted;
    RETURN NULL;
END;
$$;

CREATE TRIGGER trg_bulk_delete_demo
AFTER DELETE ON accounts_demo
REFERENCING OLD TABLE AS deleted_rows
FOR EACH STATEMENT
EXECUTE FUNCTION log_bulk_delete_demo();
```

Thử trên database thực hành:

```sql
BEGIN;

DELETE FROM accounts_demo
WHERE tenant_id = 2;

ROLLBACK;
```

Với dữ liệu mẫu, tenant 2 có tài khoản 201 và 202, nên `deleted_rows` có **2 hàng**. Sau `ROLLBACK` hai tài khoản trở lại.

**Không được dùng nhánh DELETE hoặc TRUNCATE tùy tiện trên hệ thống nghiệp vụ.** Ví dụ này chỉ dành cho bảng `accounts_demo` tự tạo trong môi trường thực hành.

### 12.3. UPDATE cần ghép OLD/NEW theo khóa ổn định

`UPDATE` có cả hai tập phiên bản. Nhưng để tính **delta cho từng hàng**, câu:

```sql
FROM new_rows AS n
JOIN old_rows AS o
  ON n.account_id = o.account_id
```

chỉ đúng nếu `account_id` được giữ nguyên. Không có bảo đảm rằng hai quan hệ cũ/mới có **thứ tự hàng trùng nhau** để có thể ghép bằng “dòng thứ nhất với dòng thứ nhất”.

Đặc biệt, **không gán `ROW_NUMBER()` không có thứ tự đáng tin cậy cho mỗi tập rồi ghép theo số thứ tự**; làm vậy có thể ghép số dư của hai người khác nhau.

## 13. UPDATE ... FROM và nguồn nhiều hàng khớp một đích

Một ví dụ điển hình khiến người viết nhầm giữa **số hàng JOIN** và **số hàng thực sự được cập nhật** là `UPDATE ... FROM` trên PostgreSQL.

Giả sử bảng staging chứa hai dòng cho cùng account:

```sql
CREATE TABLE account_adjustment_demo (
    adjustment_id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    delta NUMERIC(14, 2) NOT NULL
);

INSERT INTO account_adjustment_demo
    (adjustment_id, account_id, delta)
VALUES
    (1, 101, 10.00),
    (2, 101, 20.00),
    (3, 102, -5.00);
```

Nếu muốn tăng account 101 **tổng 30** và giảm account 102 **5**, không nên viết:

```sql
-- KHÔNG dùng để cộng dồn tất cả adjustment của mỗi account:
UPDATE accounts_demo AS a
SET balance = a.balance + d.delta
FROM account_adjustment_demo AS d
WHERE d.account_id = a.account_id;
```

Trong PostgreSQL, một hàng đích có thể khớp **nhiều hàng nguồn**. Câu `UPDATE ... FROM` không bảo đảm sẽ lần lượt áp dụng tất cả điều chỉnh lên cùng hàng đích; việc chọn hàng nguồn dùng cho cập nhật có thể **không dự đoán được** nếu điều kiện JOIN không duy nhất. Không thể giả định account 101 được tăng 10 rồi tăng tiếp 20.

### 13.1. Chuẩn hóa nguồn thành một hàng cho mỗi account

```sql
BEGIN;

WITH summed_adjustments AS (
    SELECT account_id, SUM(delta) AS total_delta
    FROM account_adjustment_demo
    GROUP BY account_id
)
UPDATE accounts_demo AS a
SET balance = a.balance + s.total_delta
FROM summed_adjustments AS s
WHERE a.account_id = s.account_id
RETURNING a.account_id, a.balance;

ROLLBACK;
```

Ở trạng thái ban đầu:

| account_id | Tổng adjustment | Balance sau |
|---:|---:|---:|
| 101 | +30.00 | 130.00 |
| 102 | -5.00 | 195.00 |

`UPDATE` thực sự tác động **2 hàng đích**, không phải 3 hàng nguồn. Row trigger audit **2 hàng**; statement trigger cho tenant 1 ghi `matched_rows=2`, `changed_rows=2`, `total_delta=25`.

**Bài học:** phải xác định **mức chi tiết của dữ liệu nguồn**, tính duy nhất của khóa JOIN và ngữ nghĩa cộng dồn **trước khi cập nhật**. Trigger không thể tự sửa một câu UPDATE có ý định sai.

### 13.2. Một hàng nguồn không nhất thiết bằng một hàng audit

Nếu một adjustment không được phép (ví dụ gây balance âm), transaction có thể thất bại. Nếu hai dòng staging cùng account nhưng đã tổng hợp, có **một hàng đích** bị cập nhật. Nếu một hàng đích được gán lại cùng giá trị, row audit có điều kiện sẽ không ghi dù statement có tác động đến hàng.

Vì thế cần phân biệt:

- **Số dòng staging**.
- **Số cặp được tạo bởi JOIN**.
- **Số hàng đích được cập nhật**.
- **Số hàng có giá trị thực sự thay đổi**.
- **Số dòng audit được tạo**.

Không phải năm con số này luôn bằng nhau.

## 14. Tổng hợp trên toàn bảng trong row trigger: vì sao dễ sai?

Một ý tưởng dễ mắc là viết row trigger:

```sql
-- Mẫu tư duy nguy hiểm, không triển khai:
-- AFTER UPDATE FOR EACH ROW:
--   SELECT SUM(balance) FROM accounts_demo;
--   INSERT INTO summary_log(total_balance) VALUES (...);
```

Giả sử một statement cập nhật **ba tài khoản**. Nếu row trigger chạy ba lần và mỗi lần query toàn bảng:

1. Có thể tạo **ba dòng tổng** trong khi yêu cầu chỉ cần một tổng sau toàn lệnh.
2. Kết quả nhìn thấy có thể phụ thuộc **thời điểm và các quy tắc visibility** của DBMS.
3. Gây lặp việc quét bảng, tốn tài nguyên.
4. Trên Oracle, việc truy vấn bảng **đang bị thay đổi** trong row trigger thường vấp lỗi **mutating table**.
5. Một câu `UPDATE` tác động hàng nghìn tài khoản có thể gây hàng nghìn phép tính tổng không cần thiết.

### 14.1. Không đồng nhất số dư tổng cuối với delta của statement

Nếu chỉ cần tổng cuối cùng:

```sql
SELECT tenant_id, SUM(balance)
FROM accounts_demo
GROUP BY tenant_id;
```

đọc trực tiếp sau statement trong **cùng transaction** có thể cho trạng thái sau khi thao tác hoàn tất, nhưng nếu xây một bảng tổng hợp cập nhật thường xuyên, cần thiết kế **đồng thời, transaction và khả năng nhất quán** riêng. Không đưa query tổng toàn bảng vào mỗi lần gọi row trigger mà không đánh giá ngữ nghĩa.

### 14.2. Transition table cho một tập rõ ràng

Khi yêu cầu là “**tổng thay đổi của những hàng thuộc statement này**”, quan hệ `old_rows/new_rows` phù hợp:

```sql
SELECT
    n.tenant_id,
    SUM(n.balance - o.balance) AS delta_for_statement
FROM new_rows AS n
JOIN old_rows AS o
  ON n.account_id = o.account_id
GROUP BY n.tenant_id;
```

Nó không tự cộng những hàng **không thuộc statement**, và giúp tính chênh lệch đúng tập đang xử lý.

## 15. Tính nguyên tử, rollback và lỗi ở một trong nhiều hàng

Một câu DML trên database giao dịch có tính **nguyên tử theo cơ chế transaction**: nếu lỗi không được xử lý làm statement thất bại, không được để lệnh thành công một nửa trong trạng thái commit.

### 15.1. Ví dụ một hàng vi phạm số dư không âm

Trên dữ liệu ban đầu, tenant 1 có các số dư 100, 200, 80. Chạy:

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance - 150.00
WHERE tenant_id = 1;

ROLLBACK;
```

Kết quả đề xuất sẽ làm account 101 và 103 âm; trigger `BEFORE ROW` và constraint `CHECK` bảo vệ không cho thao tác không hợp lệ thành công. Trong PostgreSQL, khi câu UPDATE ném lỗi, transaction tường minh thường chuyển sang trạng thái lỗi và cần **`ROLLBACK`** trước khi tiếp tục các lệnh bình thường.

Không được diễn giải rằng account 102 chắc chắn đã giảm 150 chỉ vì một số row trigger có thể chạy trước khi gặp lỗi. **Câu lệnh thất bại phải được hoàn tác** theo transaction; các dòng audit ghi trong cùng transaction cũng không được commit như một thành công giả.

### 15.2. Không dùng ghi log ngoài transaction nếu cần audit nguyên tử

Nếu một row trigger gọi dịch vụ bên ngoài hoặc gửi email ngay khi thấy mỗi hàng, thao tác bên ngoài có thể xảy ra **trước khi một hàng khác làm statement thất bại**. `ROLLBACK` database không tự thu hồi email đã gửi.

Với audit cần nhất quán, nên ghi vào bảng audit trong **cùng transaction** hoặc thiết kế cơ chế outbox đáng tin cậy; sau commit mới thực hiện side effect bên ngoài theo quy tắc hệ thống.

### 15.3. Sequence và side effect không nhất thiết rollback

Trong PostgreSQL, số được cấp từ sequence/identity có thể tạo **khoảng trống** sau transaction rollback. Không dùng việc `audit_id` liên tục hay không liên tục làm thước đo “đã commit bao nhiêu audit record”.

Muốn đếm audit đã lưu, hãy truy vấn tập hàng đã commit theo khóa/sự kiện phù hợp; số ID lớn nhất không bằng số lần trigger chạy.

## 16. Thứ tự trigger và các trigger liên quan

Một statement có thể có nhiều trigger:

- `BEFORE STATEMENT`.
- `BEFORE ROW`.
- `AFTER ROW`.
- `AFTER STATEMENT`.

Trong PostgreSQL, trình tự xử lý có quy tắc cho từng giai đoạn, nhưng **thứ tự giữa những hàng khác nhau không phải hợp đồng nghiệp vụ**. Khi có nhiều trigger cùng loại/sự kiện trên một bảng, PostgreSQL có quy tắc gọi theo **tên trigger** ở những trường hợp phù hợp; không nên đặt logic đúng sai dựa vào việc một trigger có tên “trước” chạy để sửa dữ liệu cho trigger khác mà chưa thiết kế phụ thuộc rõ ràng.

### 16.1. BEFORE ROW có thể sửa NEW

Ở ví dụ `check_account_balance_demo()`:

```sql
NEW.updated_at := clock_timestamp();
RETURN NEW;
```

Điều này thay đổi giá trị hàng **trước khi ghi**. Transition table `NEW TABLE` của `AFTER UPDATE` phản ánh giá trị hàng đã được thực hiện theo quy tắc trigger, không chỉ biểu thức gốc trong `SET`.

Nếu nhiều `BEFORE ROW` trigger cùng sửa một cột, cần xác định quy tắc thứ tự và tránh phụ thuộc không cần thiết.

### 16.2. AFTER ROW không phải nơi sửa NEW rồi mong bảng tự cập nhật

Một `AFTER ROW` trigger dùng `NEW` để đọc giá trị sau thay đổi, nhưng việc `RETURN NEW` ở thời điểm này không tự sửa lại hàng trong bảng. Nếu muốn thay giá trị trước khi ghi, dùng `BEFORE ROW` phù hợp hoặc một câu `UPDATE` rõ ràng với kiểm soát recursion.

### 16.3. Row trigger có WHEN, statement trigger cần điều kiện khác

PostgreSQL cho phép `WHEN (OLD.balance IS DISTINCT FROM NEW.balance)` trong **row trigger UPDATE**. Nhưng statement trigger không có một cặp `OLD/NEW` hàng để dùng giống vậy.

Nếu muốn statement trigger chỉ ghi audit khi có số dư thực sự đổi, có thể lọc trên tập:

```sql
WHERE n.balance IS DISTINCT FROM o.balance
```

hoặc dùng `HAVING`/`FILTER` trong phép tổng hợp. Trigger **vẫn được gọi**, nhưng hàm có thể quyết định không ghi log khi không có thay đổi nghiệp vụ.

## 17. Tránh vòng lặp trigger và cập nhật chồng lấn

Một trigger có thể thực thi thêm DML. Nếu DML đó lại tác động đến **cùng bảng/sự kiện**, có nguy cơ tạo chuỗi kích hoạt lặp lại hoặc recursion.

Ví dụ ý tưởng nguy hiểm:

```sql
-- Bên trong AFTER UPDATE trigger của accounts_demo:
-- UPDATE accounts_demo
-- SET updated_at = clock_timestamp()
-- WHERE account_id = NEW.account_id;
```

Câu `UPDATE` mới có thể kích hoạt **các UPDATE trigger trên accounts_demo** lần nữa, và nếu không có điều kiện dừng chính xác sẽ lặp hoặc gây lỗi.

### 17.1. Chọn đúng điểm sửa dữ liệu

Nếu chỉ cần đặt `updated_at`, `BEFORE ROW`:

```sql
NEW.updated_at := clock_timestamp();
RETURN NEW;
```

thường đơn giản hơn `AFTER UPDATE` rồi chạy thêm một `UPDATE` lên chính bảng.

### 17.2. Trigger ghi sang bảng log riêng

Các trigger audit trong bài ghi vào `account_row_audit_demo` và `account_statement_audit_demo`. Những bảng này **không có trigger quay lại sửa `accounts_demo`** trong bộ ví dụ, nên không tạo vòng lặp ngược.

Ở hệ thống thật, phải xem cả chuỗi:

```text
UPDATE A
  -> trigger A ghi B
      -> trigger B sửa A
          -> trigger A ...
```

Một trigger đơn lẻ có thể trông hợp lý nhưng vẫn gây recursion khi kết hợp với trigger ở bảng khác.

### 17.3. Các DBMS có giới hạn khác nhau

MySQL có giới hạn về việc trigger sửa chính bảng đang được statement kích hoạt xử lý. SQL Server có các thiết lập/giới hạn về recursive hoặc nested triggers. Oracle có các quy tắc riêng, bao gồm mutating table. Không dịch một mẫu recursion từ PostgreSQL sang DBMS khác mà không xác nhận hành vi.

## 18. Xử lý dữ liệu đồng thời và cập nhật bảng tổng hợp

Trigger chạy trong ngữ cảnh giao dịch. Khi nhiều phiên cùng cập nhật các hàng khác nhau hoặc cùng một hàng, hệ quản trị phải điều phối khóa và quy tắc cô lập.

### 18.1. Không nghĩ statement trigger tạo ảnh chụp toàn hệ thống

`new_rows` và `old_rows` mô tả **những hàng được statement cụ thể thay đổi**. Nó không tự là snapshot đầy đủ của bảng ở một thời điểm tuyệt đối, cũng không bao gồm thay đổi của các transaction khác chưa commit.

Do đó:

```sql
SUM(n.balance - o.balance)
```

trên transition tables là **tổng chênh lệch của statement**, không phải tổng số dư hiện tại toàn hệ thống.

### 18.2. Cập nhật rollup table cần thiết kế đồng thời

Giả sử ứng dụng giữ bảng tổng số dư theo tenant và mỗi statement trigger tăng tổng:

```sql
-- Mẫu ý tưởng, giả định có bảng tenant_rollup.
UPDATE tenant_rollup AS r
SET total_balance = r.total_balance + d.total_delta
FROM (
    SELECT n.tenant_id,
           SUM(n.balance - o.balance) AS total_delta
    FROM new_rows AS n
    JOIN old_rows AS o USING (account_id)
    GROUP BY n.tenant_id
) AS d
WHERE r.tenant_id = d.tenant_id;
```

Phép `SET total_balance = total_balance + delta` trên hàng rollup có thể giúp tránh kiểu **đọc tổng vào biến rồi ghi đè**. Nhưng nó vẫn đòi hỏi:

- Hàng rollup của tenant đã tồn tại hoặc có chiến lược `INSERT/UPSERT` thích hợp.
- Khóa duy nhất trên tenant của rollup.
- Transaction và xử lý deadlock/retry khi nhiều phiên cạnh tranh.
- Quy tắc cho `INSERT`/`DELETE` tài khoản, không chỉ `UPDATE balance`.
- Quy tắc chuyển tenant hoặc đổi khóa tài khoản.
- Quy trình đối soát lại rollup với dữ liệu gốc khi cần.

**Một trigger UPDATE không tự bảo đảm rollup đúng nếu hệ thống còn INSERT/DELETE hoặc nhập dữ liệu bằng đường khác.**

### 18.3. Tránh cập nhật rollup nhiều lần theo từng row khi có thể gom

Nếu 10.000 account cùng tenant được cập nhật, row trigger có thể thực hiện 10.000 câu `UPDATE tenant_rollup`, tăng tranh chấp trên **một hàng rollup**. Statement trigger với `GROUP BY tenant_id` có thể cập nhật rollup **một lần cho mỗi tenant** trong statement.

Điều đó giảm số lần thao tác với rollup, nhưng không loại bỏ hoàn toàn khóa chờ giữa các transaction. Với workload ghi lớn, cần đo thực tế và cân nhắc đồng bộ bất đồng bộ/streaming khi tính nhất quán cho phép.

## 19. Trigger và TRUNCATE, MERGE, khóa ngoại

### 19.1. TRUNCATE không phải DELETE nhiều hàng

Trong PostgreSQL, `TRUNCATE` là thao tác khác `DELETE`:

```sql
TRUNCATE TABLE accounts_demo;
```

Nó **không chạy DELETE row triggers cho từng hàng**, vì không xử lý hàng theo cùng cách như `DELETE`. PostgreSQL hỗ trợ **`ON TRUNCATE` trigger cấp statement**, không phải `FOR EACH ROW` cho sự kiện truncate.

Vì vậy, nếu một bảng audit chỉ dựa vào `AFTER DELETE FOR EACH ROW`, đừng giả định nó ghi từng hàng bị xóa khi ai đó dùng `TRUNCATE`.

`TRUNCATE` có ảnh hưởng đến khóa và khóa ngoại, và có thể xóa toàn bộ dữ liệu bảng trong môi trường thực thi. Không chạy lệnh minh họa này trên bảng nghiệp vụ thật.

### 19.2. MERGE có nhiều loại hành động

`MERGE` có thể xử lý chèn, sửa hoặc xóa trong cùng một câu lệnh trên các DBMS hỗ trợ. Cách firing trigger khi `MERGE` chứa nhiều hành động có thể phức tạp:

- Trigger của sự kiện INSERT/UPDATE/DELETE nào sẽ chạy?
- Trigger cấp statement có chạy dù một nhánh không tác động hàng không?
- Hành động nào chạy trước?
- Thông tin hành động có được trả qua `OUTPUT`, `RETURNING` hoặc cơ chế khác không?

Các câu trả lời phụ thuộc **DBMS và phiên bản**. Không giả định một `MERGE` tác động 20 hàng sẽ gọi một loại trigger duy nhất đúng 20 lần.

### 19.3. Khóa ngoại CASCADE có thể tạo thay đổi gián tiếp

Xóa một hàng cha có `ON DELETE CASCADE` có thể dẫn đến các thay đổi ở bảng con. Những thay đổi gián tiếp có thể kích hoạt trigger tương ứng theo quy tắc DBMS. Vì vậy cần phân biệt:

- Số hàng của câu DML đích ban đầu.
- Số hàng thay đổi ở bảng con.
- Số lần kích hoạt trigger của từng bảng/sự kiện.
- Số hàng audit tạo ra.

Không tự cộng tất cả những con số đó thành “số hàng UPDATE” của câu lệnh ban đầu.

## 20. SQL Server: inserted và deleted là tập nhiều hàng

SQL Server T-SQL có mô hình trigger rất phù hợp để minh họa nguyên tắc **set-based**: trong DML trigger, hai bảng logic **`inserted`** và **`deleted`** chứa tập hàng trước/sau liên quan đến thao tác.

### 20.1. Ngữ nghĩa inserted/deleted

| Sự kiện | `inserted` | `deleted` |
|---|---|---|
| `INSERT` | Các hàng mới được chèn | Không có hàng cũ tương ứng |
| `DELETE` | Không có hàng mới tương ứng | Các hàng bị xóa |
| `UPDATE` | Các phiên bản hàng sau cập nhật | Các phiên bản hàng trước cập nhật |

Trong một `UPDATE` tác động 500 hàng, **`inserted` và `deleted` có thể chứa 500 hàng**, không phải một giá trị scalar.

**Đây là một điểm khác PostgreSQL row-level `NEW/OLD`**. Trigger DML SQL Server thường chạy **cấp statement**, nên phải viết logic **xử lý tập** dù test đơn lẻ chỉ thay đổi một hàng.

### 20.2. Ví dụ SQL Server: ghi audit bằng INSERT ... SELECT

Giả sử đã tạo bảng `dbo.accounts_demo` và `dbo.account_row_audit_demo` tương đương trên SQL Server:

```sql
CREATE OR ALTER TRIGGER dbo.trg_account_audit_sqlserver
ON dbo.accounts_demo
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.account_row_audit_demo (
        account_id, old_balance, new_balance, delta
    )
    SELECT
        i.account_id,
        d.balance,
        i.balance,
        i.balance - d.balance
    FROM inserted AS i
    INNER JOIN deleted AS d
        ON d.account_id = i.account_id
    WHERE i.balance <> d.balance;
END;
```

Nếu hai tài khoản 101/102 được cập nhật theo ví dụ chuyển 30, câu `INSERT ... SELECT` ghi **hai dòng audit**. Với trường hợp cột `balance` nullable, điều kiện `<>` không bắt mọi thay đổi liên quan `NULL`; phải dùng so sánh null-safe theo khả năng phiên bản và quy tắc DBMS.

**Giả định:** `account_id` không đổi. Nếu cập nhật khóa, JOIN phiên bản cũ/mới bằng khóa thay đổi có thể mất hàng, giống vấn đề đã giải thích với transition tables.

### 20.3. Lỗi kinh điển: SELECT biến từ inserted

Một mẫu sai:

```sql
-- KHÔNG dùng nếu inserted có thể chứa nhiều hàng:
DECLARE @account_id INT;
SELECT @account_id = account_id
FROM inserted;

-- Xử lý chỉ @account_id ...
```

Trong SQL Server, `SELECT @variable = column FROM inserted` khi có nhiều hàng có thể gán nhiều lần rồi chỉ giữ **một giá trị cuối**. Nó không biến câu lệnh thành một vòng lặp tự xử lý đủ các account, và thứ tự giá trị cuối không phải quy tắc nghiệp vụ đáng tin.

Thay vì gán scalar, dùng:

```sql
INSERT INTO audit_table (...)
SELECT ...
FROM inserted AS i
JOIN deleted AS d ON ...;
```

hoặc phép tổng hợp `GROUP BY` phù hợp.

### 20.4. SQL Server trigger có thể chạy khi 0 hàng

Không viết trigger với giả định rằng `inserted` luôn có hàng. Một câu `UPDATE` hợp lệ nhưng điều kiện không khớp có thể kích hoạt trigger với các bảng logic rỗng.

Mẫu:

```sql
IF NOT EXISTS (SELECT 1 FROM inserted)
    RETURN;
```

có thể giúp thoát sớm nếu trigger không có việc để làm. Tuy nhiên, với logic audit dùng `INSERT ... SELECT FROM inserted`, tập nguồn rỗng đã tự nhiên không ghi dòng nào; kiểm tra thêm chỉ cần thiết khi có các thao tác nặng sau đó.

### 20.5. UPDATE(column) không chứng minh giá trị thay đổi

SQL Server có `UPDATE(balance)` hoặc `COLUMNS_UPDATED()` trong trigger để phát hiện cột có mặt trong thao tác DML theo quy tắc của hệ. Nhưng:

```sql
UPDATE dbo.accounts_demo
SET balance = balance
WHERE account_id = 101;
```

vẫn có thể khiến `UPDATE(balance)` là true, dù `balance` không đổi.

Muốn ghi nhật ký thay đổi giá trị, so sánh dữ liệu **`inserted` với `deleted`**, không chỉ kiểm tra cột được đề cập.

### 20.6. SET NOCOUNT ON không làm trigger xử lý một hàng

`SET NOCOUNT ON` tránh những thông điệp số hàng không cần thiết từ các câu DML trong trigger. Nó không tự biến trigger thành row-level, không loại bỏ nhu cầu xử lý tập và không phải cách kiểm tra rằng chỉ có một hàng được cập nhật.

SQL Server có thể dùng `OUTPUT inserted.../deleted...` trong những câu DML phù hợp, nhưng `OUTPUT` của lệnh nguồn và logic trigger audit là các cơ chế riêng; phải thiết kế cách quan sát kết quả, ràng buộc và transaction thích hợp.

## 21. Oracle: row trigger, statement trigger và compound trigger

Oracle PL/SQL hỗ trợ trigger cấp hàng và cấp statement. Trong row trigger, dùng **`:OLD` và `:NEW`**; dấu hai chấm là một phần cú pháp Oracle trong ngữ cảnh đó, không phải cách PostgreSQL viết `OLD.balance`/`NEW.balance`.

### 21.1. Row trigger Oracle và nhiều hàng

Ví dụ ý tưởng:

```sql
CREATE OR REPLACE TRIGGER trg_account_row_oracle
AFTER UPDATE OF balance ON accounts_demo
FOR EACH ROW
BEGIN
    IF :OLD.balance <> :NEW.balance THEN
        INSERT INTO account_row_audit_demo (
            account_id, old_balance, new_balance, delta
        )
        VALUES (
            :NEW.account_id,
            :OLD.balance,
            :NEW.balance,
            :NEW.balance - :OLD.balance
        );
    END IF;
END;
/
```

Giả sử schema tương đương đã được tạo bằng cú pháp Oracle. Với hai hàng 101/102 thay đổi, row trigger có thể chạy **hai lần**, mỗi lần có cặp `:OLD/:NEW` tương ứng.

### 21.2. Mutating table: không tự query lại bảng đang sửa trong row trigger

Trong Oracle, nếu một row trigger cố query hoặc sửa chính bảng **đang bị statement nguồn thay đổi** trong bối cảnh bị hạn chế, có thể gặp:

```text
ORA-04091: table ... is mutating, trigger/function may not see it
```

Ví dụ lỗi tư duy: trong `AFTER UPDATE FOR EACH ROW` của `accounts_demo`, query toàn `accounts_demo` để tính tổng sau mỗi lần sửa hàng.

Đây là một lý do nên **thu thập thông tin từng hàng** rồi xử lý **ở giai đoạn sau statement**, hoặc thiết kế phép tính theo tập bên ngoài trigger, thay vì truy vấn trạng thái giữa chừng của bảng đang thay đổi.

### 21.3. Compound trigger cho nhiều hàng

Oracle có **compound DML trigger**, cho phép khai báo nhiều **timing sections** trong cùng trigger và chia sẻ trạng thái **theo lần firing statement**.

Ví dụ tối giản: đếm số hàng cập nhật và cộng delta, rồi ghi một lần sau statement:

```sql
CREATE OR REPLACE TRIGGER trg_account_compound_oracle
FOR UPDATE OF balance ON accounts_demo
COMPOUND TRIGGER

    g_affected_rows PLS_INTEGER := 0;
    g_total_delta NUMBER := 0;

    AFTER EACH ROW IS
    BEGIN
        g_affected_rows := g_affected_rows + 1;
        g_total_delta := g_total_delta
                         + (:NEW.balance - :OLD.balance);
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        IF g_affected_rows > 0 THEN
            INSERT INTO account_statement_audit_demo (
                matched_rows, total_delta
            )
            VALUES (g_affected_rows, g_total_delta);
        END IF;
    END AFTER STATEMENT;

END trg_account_compound_oracle;
/
```

Đoạn code này là **mẫu Oracle độc lập**, giả định bảng audit của Oracle có các cột `matched_rows` và `total_delta` và những cột bắt buộc khác (nếu có) được cung cấp giá trị/default phù hợp; **không sử dụng nguyên bảng PostgreSQL của mục 3** vì bảng đó còn cột `tenant_id NOT NULL`. Nó minh họa cách tích lũy ở `AFTER EACH ROW` rồi ghi một lần ở `AFTER STATEMENT`.

Với chuyển 30 giữa 101/102:

- `g_affected_rows = 2`.
- `g_total_delta = -30 + 30 = 0`.
- Phần `AFTER STATEMENT` ghi một dòng tổng hợp nếu điều kiện của ví dụ thỏa.

**Lưu ý:** compound trigger không tự giải quyết việc **nhóm theo tenant**. Nếu cần tổng theo từng tenant, phải dùng cấu trúc collection/map hoặc staging thích hợp, hoặc tổ chức lại thuật toán; ví dụ chỉ minh họa tổng toàn statement.

### 21.4. Không dùng biến package toàn cục một cách tùy tiện

Một kiểu giải pháp cũ có thể lưu danh sách ID vào biến package giữa các lần gọi row trigger. Nếu không quản lý **vòng đời, reset, lỗi, tính đồng thời và việc trigger được gọi lại**, dữ liệu tích lũy có thể bị rò giữa các lần chạy.

Compound trigger của Oracle có phạm vi trạng thái gắn với statement phù hợp hơn cho nhiều tình huống; dù vậy vẫn phải xử lý exception và rollback theo cơ chế Oracle.

## 22. MySQL: trigger theo hàng, không có FOR EACH STATEMENT thông thường

MySQL hỗ trợ các trigger thông dụng **`BEFORE/AFTER INSERT/UPDATE/DELETE FOR EACH ROW`**. Nó **không có cú pháp trigger `FOR EACH STATEMENT` tương đương PostgreSQL** trong mô hình phổ biến.

Vì vậy một `UPDATE` tác động 100 hàng có thể kích hoạt trigger hàng **100 lần**; không có sẵn một transition table `new_rows` chung cho cả statement để truy vấn như PostgreSQL.

### 22.1. Ví dụ MySQL row audit

Giả sử schema tương đương được tạo trong MySQL InnoDB:

```sql
DELIMITER //

CREATE TRIGGER trg_account_audit_mysql
AFTER UPDATE ON accounts_demo
FOR EACH ROW
BEGIN
    IF NOT (OLD.balance <=> NEW.balance) THEN
        INSERT INTO account_row_audit_demo (
            account_id, old_balance, new_balance, delta
        )
        VALUES (
            NEW.account_id,
            OLD.balance,
            NEW.balance,
            NEW.balance - OLD.balance
        );
    END IF;
END//

DELIMITER ;
```

`<=>` là toán tử so sánh **null-safe equality** của MySQL; `NOT (OLD.balance <=> NEW.balance)` đúng khi hai giá trị khác nhau theo ngữ nghĩa null-safe.

`DELIMITER` là chỉ dẫn của một số MySQL client để nhập khối có dấu chấm phẩy; không phải cú pháp SQL tiêu chuẩn mà mọi driver đều chấp nhận nguyên văn.

Nếu cập nhật hai hàng, trigger có thể ghi **hai audit records**. Nếu số dư không đổi, nhánh `IF` bỏ ghi nhật ký.

### 22.2. Muốn tổng hợp một lần cho cả batch thì sao?

Vì MySQL không có statement trigger tổng quát giống PostgreSQL, có thể thiết kế:

1. **Stored procedure** điều khiển cả batch và ghi tổng hợp sau câu `UPDATE` trong transaction.
2. Bảng staging có `batch_id` và phép `GROUP BY` tính delta có kiểm soát.
3. Xử lý tổng hợp ở lớp ứng dụng hoặc pipeline, với cơ chế transaction/idempotency phù hợp.
4. Dùng row triggers chỉ cho những quy tắc bắt buộc theo từng hàng.

Không thử tạo `CREATE TRIGGER ... FOR EACH STATEMENT` bằng cách sao chép cú pháp PostgreSQL: MySQL sẽ không hiểu theo mô hình trigger đang xét.

### 22.3. Giới hạn sửa chính bảng đang kích hoạt trigger

MySQL có giới hạn khi trigger/stored function muốn **sửa bảng đang được statement nguồn sử dụng**, có thể dẫn đến lỗi kiểu “can't update table ... because it is already used by statement”. Điều đó củng cố nguyên tắc tránh cho row trigger tự phát động những thao tác cập nhật chồng lấn lên cùng bảng.

Với InnoDB, thao tác trong trigger thuộc ngữ cảnh transaction của lệnh nguồn theo cơ chế giao dịch; một lỗi có thể khiến statement thất bại. Không giả định hành vi rollback tương tự với storage engine không giao dịch.

## 23. SQLite: NEW/OLD từng hàng, không có statement-level trigger

SQLite hỗ trợ trigger `BEFORE`, `AFTER` và `INSTEAD OF` trong những ngữ cảnh thích hợp. Trong bài toán DML trên bảng, trigger hoạt động **theo từng hàng**, với `NEW` và `OLD`.

### 23.1. Ví dụ SQLite

Giả sử schema SQLite có bảng tài khoản và audit tương đương:

```sql
CREATE TRIGGER trg_account_audit_sqlite
AFTER UPDATE OF balance ON accounts_demo
FOR EACH ROW
WHEN NEW.balance <> OLD.balance
BEGIN
    INSERT INTO account_row_audit_demo (
        account_id, old_balance, new_balance, delta
    )
    VALUES (
        NEW.account_id,
        OLD.balance,
        NEW.balance,
        NEW.balance - OLD.balance
    );
END;
```

Với dữ liệu `balance NOT NULL` của bộ mẫu, điều kiện `<>` thể hiện thay đổi số học. Nếu cột nullable, cần xử lý riêng phép so sánh có `NULL` (SQLite có phép `IS`/`IS NOT` với ngữ nghĩa phù hợp).

Trong SQLite, `FOR EACH ROW` là cơ chế row trigger; không có transition tables cấp statement như PostgreSQL.

### 23.2. Tại sao không port nguyên ví dụ PostgreSQL?

Đoạn:

```sql
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
```

không phải cú pháp SQLite. Nếu cần log một lần cho cả batch trong SQLite, thường để **lớp ứng dụng/transaction** chạy phép tổng hợp, hoặc thiết kế một bảng staging/batch rõ ràng. Trigger row-level có thể ghi chi tiết, nhưng không tự có một callback cấp statement để tổng hợp một lần.

### 23.3. Recursive triggers và giao dịch

SQLite có cấu hình liên quan recursive triggers và những giới hạn riêng khi trigger thực thi thêm DML. Việc dùng trigger để sửa bảng khác hoặc chính bảng cần kiểm tra theo phiên bản/cấu hình.

Với yêu cầu batch, không nên dựa vào những đặc tính ngẫu nhiên về thứ tự chạy row triggers để tính tổng; ưu tiên phép tổng hợp rõ ràng và transaction.

## 24. Bảng so sánh các phương ngữ

| Đặc điểm | PostgreSQL | SQL Server | Oracle | MySQL | SQLite |
|---|---|---|---|---|---|
| Trigger theo từng hàng | `FOR EACH ROW` | DML trigger thông thường xử lý tập qua `inserted/deleted` | `FOR EACH ROW` | `FOR EACH ROW` | Trigger theo hàng |
| Trigger theo câu lệnh | `FOR EACH STATEMENT` | DML trigger thường ở cấp statement | Có | Không có loại statement trigger thông dụng | Không có loại statement trigger tương đương |
| Cũ/mới của một hàng | `OLD`/`NEW` ở row trigger | Ghép tập `deleted`/`inserted` theo khóa | `:OLD`/`:NEW` ở row trigger | `OLD`/`NEW` | `OLD`/`NEW` |
| Cả tập cũ/mới | Transition tables `OLD TABLE`/`NEW TABLE` cho AFTER triggers phù hợp | Bảng logic `deleted`/`inserted` | Compound trigger/collections hoặc thiết kế khác | Cần tự tổ chức quy trình/batch | Cần tự tổ chức quy trình/batch |
| UPDATE 0 hàng | Statement trigger vẫn có thể chạy; row trigger không | Trigger có thể chạy với tập rỗng | Statement section có thể chạy; row section không có hàng | Không có lần gọi row trigger | Không có lần gọi row trigger |
| Tổng hợp N thay đổi trong một lần | `GROUP BY` trên transition tables | `GROUP BY` trên inserted/deleted | Compound trigger hoặc xử lý sau statement | Procedure/staging/ứng dụng | Transaction/ứng dụng/staging |
| Bẫy điển hình | Xem `NEW` trong statement trigger như một hàng, ghép old/new sai khóa | Gán `@id` từ `inserted` nhiều hàng | Mutating table trong row trigger | Không có statement-level trigger | Không có transition tables/row-level only |

**Bảng này là bản đồ khái niệm**, không thay thế tài liệu của DBMS và phiên bản thực tế. Đặc biệt `MERGE`, bảng phân vùng, trigger trên view, replica, constraint/deferrable triggers và thao tác DDL có quy tắc riêng.

## 25. Kiểm tra kết quả và quan sát trigger

### 25.1. Đọc số hàng lệnh DML thay đổi

PostgreSQL có thể trả trạng thái lệnh:

```text
UPDATE 2
```

với câu chuyển 30 giữa account 101/102. Con số này biểu thị số hàng câu `UPDATE` tác động trực tiếp trong ngữ cảnh lệnh, **không phải số lần tất cả trigger chạy** và không phải số dòng được ghi vào tất cả các bảng audit.

Trong PL/pgSQL, có thể đọc số hàng DML vừa tác động qua:

```sql
GET DIAGNOSTICS v_affected_rows = ROW_COUNT;
```

nhưng phải sử dụng nó trong khối PL/pgSQL và đọc vào thời điểm phù hợp. Không lấy `ROW_COUNT` của một câu `SELECT` sau đó rồi khẳng định đó là số hàng của câu `UPDATE` trước.

### 25.2. Đọc các bảng audit

Sau câu DML, để kiểm tra:

```sql
SELECT
    account_id, old_balance, new_balance, delta
FROM account_row_audit_demo
ORDER BY audit_id;

SELECT
    tenant_id, matched_rows, changed_rows, total_delta
FROM account_statement_audit_demo
ORDER BY audit_id;
```

Khi kiểm tra một lệnh cụ thể trong hệ thống thật, nhật ký nên có **transaction ID, batch ID, request ID hoặc correlation ID** theo thiết kế để đối chiếu đúng những record của lần chạy đó. Trong bảng mẫu không có những cột này, nên các ví dụ dùng transaction rollback để giữ tập audit mới tạo đơn giản.

### 25.3. Không dùng COUNT(*) của audit để kết luận toàn bộ DML

Một trigger có thể lọc chỉ những hàng khác giá trị. Một statement trigger có thể gom 100 hàng thành **một dòng summary**. Một lỗi có thể rollback toàn bộ audit. Trigger có thể bị tắt trong một số luồng đặc biệt hoặc không áp dụng cho sự kiện khác.

Vì vậy:

- `UPDATE 100` không nhất thiết tạo 100 dòng **statement audit**.
- Có thể tạo 100 dòng **row audit** hoặc ít hơn nếu lọc thay đổi.
- `total_delta = 0` không có nghĩa không thay đổi.
- Số dòng audit chỉ có ý nghĩa trong **hợp đồng ghi audit cụ thể**.

### 25.4. Kiểm tra bằng nhiều trường hợp, không chỉ UPDATE một hàng

Khi xây trigger nhiều hàng, cần thử các tình huống:

| Tình huống | Điều cần quan sát |
|---|---|
| 0 hàng | Statement trigger có chạy không, có ghi log không |
| 1 hàng thay đổi | OLD/NEW và delta |
| N hàng cùng tenant | Số row audit và tổng chênh lệch |
| N hàng nhiều tenant | GROUP BY tạo số nhóm phù hợp |
| UPDATE gán lại giá trị cũ | Matched rows khác changed rows |
| Một hàng vi phạm CHECK | Câu lệnh và audit rollback |
| Nguồn JOIN bị trùng khóa | Không nhân đôi/sai hành động cập nhật |
| Chuyển khóa/tenant | Giả định join và group có còn đúng không |
| Truy cập đồng thời | Khóa, xung đột, deadlock, số đếm cuối |

Đây là **những tình huống minh họa cần hiểu khi thiết kế trigger**. STEP 4 của tài liệu này chỉ tạo nội dung bài học, không chạy đánh giá/chấm tự động.

## 26. Hiệu năng khi một statement thay đổi nhiều hàng

### 26.1. Row trigger có thể gây hiệu ứng N lần

Giả sử một lệnh:

```sql
UPDATE accounts_demo
SET balance = balance + 1
WHERE tenant_id = 1;
```

trong hệ thống thật thay đổi 50.000 tài khoản. Một row trigger chạy:

```sql
INSERT INTO audit_table VALUES (...);
```

cho mỗi hàng có thể tạo 50.000 lượt gọi trigger và 50.000 thao tác ghi. Đây có thể là chi phí hợp lý nếu cần audit chi tiết, nhưng có thể đắt khi trigger còn gọi query tổng hợp hoặc API khác cho mỗi hàng.

### 26.2. Statement trigger set-based có thể giảm overhead

Với transition tables:

```sql
INSERT INTO audit_table (...)
SELECT ...
FROM new_rows AS n
JOIN old_rows AS o ON ...
WHERE ...;
```

database xử lý dữ liệu theo tập. Cách này có thể giảm overhead gọi hàm/statement lặp lại và giúp optimizer xử lý JOIN/aggregation.

Nhưng nó vẫn phải **đọc các hàng nguồn**, **ghi audit**, **duy trì index** và chịu chi phí transaction. Không mặc định statement trigger luôn nhanh hơn; cần đo trên khối lượng dữ liệu đại diện.

### 26.3. Chỉ mục đúng cho bảng audit

Nếu truy vấn audit thường tìm theo `account_id` hoặc thời gian:

```sql
CREATE INDEX idx_account_row_audit_account_time_demo
ON account_row_audit_demo (account_id, recorded_at DESC);
```

có thể có lợi trên bảng audit lớn. Nhưng mỗi index mới làm **INSERT audit** tốn thêm chi phí bảo trì. Cân bằng nhu cầu truy vấn/audit và tốc độ ghi.

### 26.4. UPDATE theo lô và tác động của nhiều statement

Nếu ứng dụng chia một chiến dịch 100.000 hàng thành 100 câu `UPDATE`, mỗi câu thay đổi khoảng 1.000 hàng, **statement trigger chạy 100 lần**, không phải một lần cho cả chiến dịch.

Nếu audit định nghĩa “mỗi câu SQL một dòng”, nó sẽ tạo nhiều record hơn khi chia lô. Nếu audit phải định nghĩa **một lần xử lý nghiệp vụ** xuyên qua nhiều statement, cần thêm **batch ID** và logic tổng hợp theo batch, không dựa hoàn toàn vào số lần statement trigger firing.

### 26.5. Thời gian transaction và khóa

Một trigger chạy truy vấn nặng có thể kéo dài transaction đã gọi nó, tăng thời gian giữ khóa và khả năng deadlock. Không viết trigger tự quét bảng lớn nhiều lần hoặc thực hiện công việc không cần đồng bộ với DML khi có phương án tốt hơn.

### 26.6. Audit là dữ liệu cần quản trị

Trên hệ thống thật:

- Chỉ lưu dữ liệu cần thiết, không tự lưu thông tin nhạy cảm không có mục đích.
- Dùng retention/partition/archive phù hợp quy định.
- Phân quyền đọc và thay đổi audit chặt chẽ.
- Ghi ngữ cảnh actor/request một cách đáng tin cậy.
- Có đối soát khi một luồng nhập dữ liệu không đi qua trigger hoặc trigger bị tắt.

Chỉ “có trigger” không đồng nghĩa có hệ thống audit bảo mật và đầy đủ.

## 27. Những lỗi thường gặp

### Lỗi 1 — Nghĩ UPDATE là một statement nên trigger chỉ nhìn một hàng

`UPDATE ... WHERE tenant_id = 1` có thể thay đổi nhiều tài khoản. Row trigger chạy theo từng hàng, statement trigger xử lý ở cấp statement; không được dùng một biến scalar đại diện cho tất cả.

### Lỗi 2 — Dùng NEW.balance trong statement trigger

`NEW`/`OLD` ở PostgreSQL mô tả một hàng trong **row trigger**. Nếu muốn tập hàng ở statement trigger, dùng transition tables phù hợp.

### Lỗi 3 — Gán SELECT từ inserted vào một biến trên SQL Server

`SELECT @id = id FROM inserted` khi có 100 hàng chỉ giữ một giá trị cuối; 99 hàng còn lại không được tự xử lý. Dùng set-based `INSERT ... SELECT` hoặc aggregation.

### Lỗi 4 — Nghĩ row trigger không chạy thì statement trigger cũng không chạy

PostgreSQL `UPDATE WHERE id=999` có thể kích hoạt statement trigger với transition table rỗng, dù row trigger không chạy lần nào.

### Lỗi 5 — Nhầm matched rows với changed rows

`SET balance=balance` vẫn là UPDATE; audit có `WHEN OLD.balance IS DISTINCT FROM NEW.balance` sẽ bỏ qua thay đổi số dư bằng nhau. Cần đếm hai chỉ số riêng.

### Lỗi 6 — Nghĩ tổng delta bằng 0 nghĩa không có thay đổi

Chuyển -30 từ tài khoản 101 và +30 vào tài khoản 102 có tổng delta 0 nhưng vẫn có hai thay đổi quan trọng.

### Lỗi 7 — Ghép OLD TABLE và NEW TABLE theo thứ tự hàng

Thứ tự các hàng không phải khóa nối. Dùng một khóa ổn định duy nhất để ghép các phiên bản, và xử lý trường hợp khóa có thể đổi.

### Lỗi 8 — Đổi khóa chính nhưng vẫn JOIN theo khóa cũ/mới

Nếu `account_id` thay đổi, `o.account_id = n.account_id` có thể không khớp. Phải xác định bất biến về khóa hoặc thiết kế mapping riêng.

### Lỗi 9 — Nhóm theo tenant mới mà không xét chuyển tenant

`GROUP BY n.tenant_id` tính delta theo tenant sau; nếu tài khoản chuyển tenant, kết quả không còn là biến động số dư ròng của từng tenant theo nghĩa cũ–mới. Cần thiết kế phép điều chỉnh ở cả tenant nguồn và đích.

### Lỗi 10 — Thực hiện SUM(balance) toàn bảng trong mọi row trigger

Một UPDATE 10.000 hàng có thể quét bảng 10.000 lần, gặp trạng thái trung gian hoặc lỗi mutating table. Dùng transition tables/statement-level strategy hay phép tổng hợp phù hợp.

### Lỗi 11 — Không phân biệt cột nằm trong SET với giá trị thật sự đổi

`UPDATE OF balance` và SQL Server `UPDATE(balance)` không tự bảo đảm `OLD.balance <> NEW.balance`. Kiểm tra giá trị.

### Lỗi 12 — Bật đồng thời hai đường ghi audit giống nhau

Row trigger và statement trigger cùng insert một dòng audit mỗi hàng có thể tạo **dữ liệu nhân đôi**. Chọn một nguồn audit chi tiết hoặc thiết kế phân biệt rõ mục đích hai đường.

### Lỗi 13 — Coi AFTER ROW RETURN NULL là bỏ qua UPDATE

Trên PostgreSQL, giá trị trả của AFTER trigger không dùng để sửa/bỏ cập nhật hàng. `RETURN NULL` có ý nghĩa bỏ qua hàng trong **BEFORE ROW** khi phù hợp, không phải AFTER.

### Lỗi 14 — Cố dùng transition tables trên BEFORE trigger

Transition relations trong PostgreSQL áp dụng cho các **AFTER triggers được hỗ trợ**; không sao chép `REFERENCING OLD TABLE/NEW TABLE` vào mọi loại trigger.

### Lỗi 15 — Dùng AFTER UPDATE OF balance cùng transition tables

PostgreSQL giới hạn transition relations với UPDATE trigger có danh sách cột `OF ...`. Dùng `AFTER UPDATE ON ...` và lọc thay đổi bên trong.

### Lỗi 16 — Nghĩ một statement trigger luôn ghi một dòng summary

Nếu GROUP BY tenant, một statement có thể tạo 0, 1 hoặc nhiều dòng summary. Số lần gọi trigger không bằng số hàng ghi log.

### Lỗi 17 — Gặp một hàng lỗi vẫn nghĩ các hàng trước đó đã commit

Trong transaction PostgreSQL, exception làm statement thất bại và các thay đổi của statement không được commit từng phần như thành công riêng lẻ. Không dùng side effect ngoài DB trước commit.

### Lỗi 18 — Dùng UPDATE FROM với nhiều nguồn trùng khóa rồi mong cộng hết delta

Một hàng đích khớp hai dòng adjustment không có nghĩa nó tự được cập nhật hai lần để cộng đủ hai delta. Chuẩn hóa nguồn bằng `GROUP BY account_id` trước.

### Lỗi 19 — Giả định thứ tự row trigger là theo PRIMARY KEY

Không dùng trigger để xác định “hàng đầu tiên/hàng cuối cùng” theo ID nếu DBMS không cam kết thứ tự xử lý. Aggregate theo tập hoặc điều phối rõ ràng.

### Lỗi 20 — Để trigger gọi lại UPDATE trên cùng bảng không có điều kiện dừng

Có thể tạo recursion hoặc DML chồng lấn. Nếu chỉ đặt timestamp, dùng BEFORE ROW sửa `NEW` phù hợp.

### Lỗi 21 — Copy SQL Server inserted/deleted sang PostgreSQL

`inserted`/`deleted` là bảng logic của SQL Server DML trigger; PostgreSQL dùng `OLD/NEW` theo hàng hoặc transition tables theo cú pháp `REFERENCING`.

### Lỗi 22 — Dùng Oracle row trigger query chính bảng đang thay đổi

Có thể gặp `ORA-04091 mutating table`. Xem compound trigger hoặc quy trình hậu statement/set-based.

### Lỗi 23 — Tạo MySQL FOR EACH STATEMENT

MySQL thông dụng chỉ hỗ trợ row triggers, không có statement trigger kiểu PostgreSQL. Muốn tổng hợp theo batch phải dùng procedure/staging/ứng dụng.

### Lỗi 24 — Nghĩ SQLite có NEW TABLE/OLD TABLE cho cả statement

SQLite có `NEW/OLD` theo từng hàng, không có transition tables cấp statement tương đương PostgreSQL.

### Lỗi 25 — Nghĩ TRUNCATE sẽ chạy DELETE row trigger

Trong PostgreSQL, `TRUNCATE` không gọi DELETE row triggers cho từng hàng. Muốn quan sát truncate cần cơ chế sự kiện phù hợp và quy tắc bảo trì dữ liệu.

### Lỗi 26 — Không tính tác động của FK CASCADE và MERGE

DML có thể kích hoạt thêm thay đổi trên bảng con hoặc nhiều loại trigger tùy DBMS/phiên bản. Không diễn giải số lần firing chỉ từ cú pháp ban đầu.

### Lỗi 27 — Dùng transaction ID/sequence ID làm số lượng audit tuyệt đối

ID identity có thể có khoảng trống do rollback; nhiều dòng audit có thể thuộc một statement, nhiều statement thuộc một batch. Cần correlation ID và phép đếm thực tế.

### Lỗi 28 — Giữ trigger nặng trong đường giao dịch nóng

Trigger chạy đồng bộ theo DML có thể làm tăng latency, khóa chờ và tải ghi. Đo hiệu năng theo batch lớn và cân nhắc xử lý set-based, outbox hoặc pipeline khi phù hợp.

## 28. Bài tập thực hành có đáp án

Các bài dùng bảng `accounts_demo` và các trigger ở mục 3–8, trừ bài có ghi “phương ngữ khác”. **Mỗi bài độc lập**, bắt đầu từ dữ liệu năm tài khoản ban đầu; khi thực hiện DML, dùng transaction `BEGIN ... ROLLBACK` để có thể thử lại. Bảng `account_adjustment_demo` chỉ cần cho các bài có nói đến staging.

### Bài 1 — UPDATE một hàng

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 10
WHERE account_id = 101;

ROLLBACK;
```

**Đáp án:** row trigger audit ghi **1 dòng** cho account 101 với `100 → 110`, delta `+10`. Statement trigger chạy **1 lần**, ghi tenant 1: `matched_rows=1`, `changed_rows=1`, `total_delta=10`.

### Bài 2 — UPDATE hai hàng chuyển số dư

```sql
BEGIN;

UPDATE accounts_demo
SET balance = CASE account_id
    WHEN 101 THEN balance - 30
    WHEN 102 THEN balance + 30
END
WHERE account_id IN (101, 102);

ROLLBACK;
```

**Đáp án:** account 101: 100→70; account 102: 200→230. **2 row audit**, **1 statement audit** cho tenant 1; `matched_rows=2`, `changed_rows=2`, `total_delta=0`.

### Bài 3 — UPDATE ba hàng

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 10
WHERE tenant_id = 1;

ROLLBACK;
```

**Đáp án:** ba hàng 101, 102, 103 đổi số dư; statement audit tenant 1 ghi **3 matched, 3 changed, delta +30**.

### Bài 4 — UPDATE tất cả năm hàng

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 5;

ROLLBACK;
```

**Đáp án:** statement trigger chạy **1 lần**, nhưng `GROUP BY tenant_id` ghi **2 dòng tổng hợp**: tenant 1 có `3/3/+15`; tenant 2 có `2/2/+10`. Row audit ghi **5 dòng**.

### Bài 5 — WHERE không khớp

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance + 1
WHERE account_id = 999;

ROLLBACK;
```

**Đáp án:** row trigger **0 lần**; statement trigger **vẫn có thể chạy một lần** với transition tables rỗng. Bảng statement audit không có nhóm nào để insert, nên không thêm dòng.

### Bài 6 — UPDATE không đổi giá trị

```sql
BEGIN;

UPDATE accounts_demo
SET balance = balance
WHERE account_id IN (101, 102);

ROLLBACK;
```

**Đáp án:** `matched_rows=2`, `changed_rows=0`, `total_delta=0`; row audit không thêm dòng do `WHEN` so sánh balance. Trigger BEFORE vẫn có thể đổi `updated_at`.

### Bài 7 — Phân biệt OLD/NEW

Trong lần gọi row trigger cho account 101 khi `100 → 70`, `OLD.balance` và `NEW.balance` bằng bao nhiêu?

**Đáp án:** `OLD.balance=100`, `NEW.balance=70`. Chỉ là **một cặp hàng** trong lần gọi này, không chứa số dư của account 102.

### Bài 8 — OLD TABLE/NEW TABLE

Sau UPDATE hai hàng 101/102, `old_rows` và `new_rows` của statement trigger có bao nhiêu hàng?

**Đáp án:** mỗi relation có **2 hàng** tương ứng với hai tài khoản được update; khi ghép theo `account_id` ổn định tạo hai cặp cũ/mới.

### Bài 9 — Tính tổng delta

Tính `SUM(n.balance - o.balance)` sau chuyển 30 giữa hai tài khoản.

**Đáp án:** `-30 + 30 = 0`. Không có nghĩa row count bằng 0 hoặc không có dữ liệu bị thay đổi.

### Bài 10 — COUNT(*) khác COUNT(FILTER)

Giả sử một UPDATE tác động ba hàng, chỉ hai hàng đổi số dư; hàng thứ ba `SET balance=balance`. Kết quả `matched_rows` và `changed_rows`?

**Đáp án:** `matched_rows=3`, `changed_rows=2`. Số hàng statement xử lý khác số hàng đổi giá trị nghiệp vụ.

### Bài 11 — Tại sao cần khóa ổn định?

Trong transition table, tại sao ghép:

```sql
ON n.account_id = o.account_id
```

chỉ đúng khi `account_id` không bị cập nhật?

**Đáp án:** nếu khóa ID thay đổi, phiên bản cũ và mới có ID khác nhau, JOIN có thể không ghép được một hàng với chính nó. Cần bất biến về khóa hoặc mapping ổn định.

### Bài 12 — Chuyển tenant

Một UPDATE đổi `tenant_id` từ 1 sang 2, không đổi balance. Nhóm theo `n.tenant_id` với delta số dư có phản ánh việc chuyển số dư giữa tenant không?

**Đáp án:** **không**. Nó chỉ nhóm theo tenant mới và tính `new.balance-old.balance=0`, nên bỏ qua luồng chuyển số dư giữa hai tenant. Phải thiết kế riêng việc giảm ở tenant cũ và tăng ở tenant mới.

### Bài 13 — Ghi audit bằng một INSERT ... SELECT

Viết phần thân statement trigger dùng transition tables:

```sql
INSERT INTO account_row_audit_demo (
    account_id, old_balance, new_balance, delta
)
SELECT
    n.account_id,
    o.balance,
    n.balance,
    n.balance - o.balance
FROM new_rows AS n
JOIN old_rows AS o USING (account_id)
WHERE n.balance IS DISTINCT FROM o.balance;
```

**Đáp án:** trên UPDATE 101/102 có **2 dòng audit**. Đây là **phương án thay thế** row audit trigger hiện có; không bật cả hai để tránh audit trùng.

### Bài 14 — UPDATE OF balance có nghĩa gì?

Một câu `SET balance = balance` có kích hoạt row trigger `AFTER UPDATE OF balance` không?

**Đáp án:** **có thể có**, vì cột được nêu trong `SET`. Nhưng `WHEN (OLD.balance IS DISTINCT FROM NEW.balance)` là false nên hàm row audit không được gọi cho hàng không đổi balance.

### Bài 15 — RETURN NULL khác nhau ở BEFORE và AFTER

So sánh `RETURN NULL` trong PostgreSQL `BEFORE UPDATE FOR EACH ROW` và `AFTER UPDATE FOR EACH ROW`.

**Đáp án:** trong BEFORE ROW, `RETURN NULL` có thể **bỏ qua thao tác trên hàng**. Trong AFTER ROW, giá trị trả về bị bỏ qua cho mục đích sửa/bỏ cập nhật; nó không hoàn tác update.

### Bài 16 — Hàng âm số dư

`UPDATE accounts_demo SET balance=balance-150 WHERE tenant_id=1` trên dữ liệu ban đầu sẽ thế nào?

**Đáp án:** có hàng đề xuất số dư âm, trigger bảo vệ/constraint gây lỗi; lệnh không được coi đã commit một phần. Transaction tường minh cần rollback khi lỗi ở PostgreSQL.

### Bài 17 — Tại sao không SUM toàn bảng ở mỗi row trigger?

Một UPDATE 100.000 hàng có row trigger gọi `SELECT SUM(balance)` sau mỗi hàng. Nêu hai vấn đề.

**Đáp án:** lặp **100.000 phép tổng** có thể tốn I/O/CPU; ngữ nghĩa trạng thái giữa câu UPDATE có thể không phản ánh tổng cuối. Trên Oracle còn có lỗi mutating table. Thay bằng xử lý sau statement/set-based phù hợp.

### Bài 18 — UPDATE FROM với staging trùng khóa

Staging có `(101,+10)`, `(101,+20)`, `(102,-5)`. Muốn áp dụng tổng các adjustment, cần chuẩn hóa thế nào?

**Đáp án:**

```sql
WITH summed AS (
    SELECT account_id, SUM(delta) AS total_delta
    FROM account_adjustment_demo
    GROUP BY account_id
)
UPDATE accounts_demo AS a
SET balance = a.balance + s.total_delta
FROM summed AS s
WHERE a.account_id = s.account_id;
```

Kết quả trên dữ liệu ban đầu: account 101 = **130**, account 102 = **195**, statement tổng delta tenant 1 **+25**.

### Bài 19 — SQL Server inserted có một hàng không?

Một trigger SQL Server chạy:

```sql
DECLARE @id INT;
SELECT @id = account_id FROM inserted;
```

khi UPDATE 200 hàng. Có phải nó đã xử lý đủ 200 hàng?

**Đáp án:** **không**. Một biến chỉ chứa một giá trị cuối; phải xử lý `inserted` như **tập** bằng `JOIN`, `INSERT ... SELECT` hoặc `GROUP BY`.

### Bài 20 — SQL Server kiểm tra thay đổi giá trị

Vì sao `UPDATE(balance)` không đủ để biết balance thực sự khác?

**Đáp án:** cột có thể xuất hiện trong `SET` nhưng giá trị sau giống trước. Cần so sánh `inserted.balance` với `deleted.balance` theo khóa và xử lý `NULL` nếu cột nullable.

### Bài 21 — Oracle compound trigger

Oracle muốn cộng delta của tất cả hàng rồi ghi một dòng khi statement hoàn tất. Dùng phần nào của compound trigger?

**Đáp án:** `AFTER EACH ROW` tích lũy `:NEW.balance-:OLD.balance` và số hàng trong biến trạng thái statement; `AFTER STATEMENT` ghi kết quả tổng hợp một lần.

### Bài 22 — Oracle ORA-04091

Vì sao một row trigger Oracle có thể bị lỗi khi query lại toàn bộ bảng đang bị UPDATE?

**Đáp án:** đó là trường hợp **mutating table**, vì bảng đang trong quá trình thay đổi và row trigger không được đọc lại theo cách đó trong các ngữ cảnh bị hạn chế. Dùng compound trigger/cách hậu statement phù hợp.

### Bài 23 — MySQL statement trigger

Có thể viết trong MySQL:

```sql
CREATE TRIGGER ...
AFTER UPDATE ON accounts_demo
FOR EACH STATEMENT ...
```

theo mô hình PostgreSQL không?

**Đáp án:** **không**. MySQL thông dụng chỉ có row-level DML triggers. Muốn tổng hợp một batch, dùng procedure/staging/transaction hoặc lớp ứng dụng.

### Bài 24 — SQLite trigger và NEW/OLD

Trên SQLite, `NEW.balance` và `OLD.balance` là giá trị của gì?

**Đáp án:** phiên bản mới/cũ của **một hàng đang được trigger xử lý**, không phải quan hệ nhiều hàng kiểu `new_rows` của PostgreSQL.

### Bài 25 — INSERT ba hàng

`INSERT INTO accounts_demo VALUES ...` chèn ba account 301/302/303 trong **một câu**. Statement trigger `AFTER INSERT REFERENCING NEW TABLE AS inserted_rows` chạy bao nhiêu lần và có bao nhiêu hàng?

**Đáp án:** một lần, transition table có **3 hàng**; row-level INSERT trigger (nếu có) sẽ chạy cho từng hàng theo cơ chế DBMS.

### Bài 26 — DELETE tenant 2

`DELETE FROM accounts_demo WHERE tenant_id=2` trên dữ liệu ban đầu: `OLD TABLE` của statement DELETE có mấy hàng?

**Đáp án:** **2 hàng** (201 và 202). Không có `NEW TABLE` tương ứng cho hai hàng đã xóa.

### Bài 27 — TRUNCATE và DELETE trigger

Có thể dựa vào `AFTER DELETE FOR EACH ROW` để ghi audit từng hàng khi chạy `TRUNCATE TABLE accounts_demo` ở PostgreSQL không?

**Đáp án:** **không**. `TRUNCATE` có ngữ nghĩa trigger riêng và không gọi DELETE row trigger cho từng bản ghi.

### Bài 28 — Chia một batch thành 100 statement

Một job dọn dữ liệu chia 100.000 hàng thành 100 câu UPDATE. Trigger `FOR EACH STATEMENT` chạy bao nhiêu lần?

**Đáp án:** thường **100 lần** cho 100 statement tương ứng được thực thi, không phải một lần cho toàn batch nghiệp vụ. Nếu muốn một summary theo batch, cần `batch_id`/quy trình tổng hợp riêng.

### Bài 29 — Tổng audit và số thao tác

Một statement cập nhật 5 account, trong đó 3 account đổi balance và 2 không đổi; 5 account thuộc hai tenant. Theo mô hình bài học, có thể có bao nhiêu loại con số khác nhau?

**Đáp án:** statement tác động **5 hàng**; row audit ghi **3 hàng**; statement trigger chạy **1 lần**; statement audit ghi **tối đa 2 hàng theo tenant có hàng cập nhật** (nếu cả hai tenant đều tham gia thì là 2); tổng delta phụ thuộc giá trị, có thể 0. Không đồng nhất các đại lượng.

### Bài 30 — Chọn cấp trigger

Ghép yêu cầu với thiết kế phù hợp:

1. Kiểm tra `NEW.balance >= 0` trước khi ghi từng hàng.
2. Ghi một audit record cho mỗi hàng đổi balance.
3. Tính tổng delta theo tenant cho cả một câu UPDATE.
4. Trên SQL Server, audit 1.000 hàng bị UPDATE.
5. Trên MySQL, tính summary cho toàn batch.

**Đáp án:**

1. `BEFORE EACH ROW` hoặc constraint.
2. `AFTER EACH ROW` có `WHEN`, hoặc statement trigger + transition table set-based trên PostgreSQL.
3. `AFTER EACH STATEMENT` dùng `OLD TABLE/NEW TABLE` của PostgreSQL.
4. Dùng `INSERT ... SELECT FROM inserted JOIN deleted`, không gán một biến scalar.
5. Stored procedure/staging/transaction hoặc xử lý ứng dụng, vì MySQL không có statement trigger tổng quát tương đương.

## 29. Bảng ghi nhớ nhanh

| Câu hỏi | Cách hiểu đúng |
|---|---|
| Một `UPDATE` có thể sửa mấy hàng? | 0, 1 hoặc nhiều hàng; `WHERE` và dữ liệu quyết định |
| Row-level trigger chạy mấy lần? | Theo từng hàng phù hợp với sự kiện/điều kiện |
| Statement-level trigger chạy mấy lần? | Thường một lần mỗi statement/sự kiện, kể cả khi 0 hàng ở DBMS hỗ trợ |
| PostgreSQL `OLD`/`NEW` dùng ở đâu? | Giá trị của một hàng trong row-level trigger |
| PostgreSQL lấy toàn bộ tập thay đổi ở đâu? | `REFERENCING OLD TABLE/NEW TABLE` trong AFTER trigger phù hợp |
| Khi UPDATE 0 hàng, transition table ra sao? | Rỗng; statement trigger có thể vẫn chạy |
| `UPDATE SET balance=balance` có phải thay đổi nghiệp vụ không? | Không đổi balance, nhưng vẫn là statement UPDATE |
| Đếm hàng thực sự đổi balance? | `IS DISTINCT FROM` hoặc phép so sánh tương ứng theo DBMS |
| Tổng delta = 0 có nghĩa không có update? | Không; các tăng/giảm có thể triệt tiêu |
| Ghép old/new bằng gì? | Khóa ổn định duy nhất; không ghép theo thứ tự dòng |
| Ghi audit cho N hàng? | Row trigger N lần hoặc statement trigger `INSERT ... SELECT` |
| Ghi tổng theo tenant? | `JOIN` old/new, `GROUP BY tenant_id`, `COUNT`/`SUM` |
| AFTER ROW RETURN NULL có bỏ update? | Không; giá trị trả không dùng như BEFORE ROW |
| Một hàng lỗi làm sao? | Theo transaction, lệnh thất bại/rollback; không được commit một phần như thành công |
| SQL Server dùng gì? | `inserted`/`deleted` là tập hàng |
| Oracle có gì khác? | `:OLD/:NEW` theo hàng, compound trigger và mutating table |
| MySQL có FOR EACH STATEMENT không? | Không trong mô hình trigger thông dụng |
| SQLite có transition table statement không? | Không; trigger theo hàng |
| TRUNCATE có chạy DELETE ROW trigger không? | Không trong PostgreSQL |
| Trigger có tự bảo đảm audit đầy đủ không? | Không; phải xét tất cả đường ghi, cascade, MERGE, quyền và transaction |

## Kết luận

Một câu lệnh DML có thể thay đổi **rất nhiều hàng**, vì thế trigger phải được viết theo đúng **mức chi tiết của thao tác**:

- **Trigger theo hàng** xử lý một cặp `OLD`/`NEW` trong mỗi lần gọi. Nó thích hợp cho kiểm tra/ghi log từng hàng, nhưng khi câu UPDATE tác động N hàng, logic có thể chạy N lần.
- **Trigger theo câu lệnh** chạy ở mức statement. Trong PostgreSQL, transition tables giúp lấy **toàn bộ tập hàng cũ/mới** và xử lý bằng `JOIN`, `GROUP BY`, `INSERT ... SELECT`, `COUNT` và `SUM`.
- **Không có hàng nào bị cập nhật** không nhất thiết nghĩa statement trigger không chạy. **Có hàng cập nhật nhưng giá trị không đổi** cũng không giống “không có UPDATE”.
- **Ghép đúng khóa ổn định** khi tính delta. Đừng giả định các tập cũ/mới có thứ tự giống nhau, và đừng quên trường hợp khóa hoặc tenant được thay đổi.
- **Một lần trigger chạy không đồng nghĩa một dòng audit**: statement trigger có thể ghi nhiều dòng theo nhóm, còn row trigger có thể bỏ những hàng không đổi.
- **Ngữ nghĩa theo phương ngữ khác nhau**: SQL Server xử lý tập `inserted`/`deleted`; Oracle có row/statement/compound triggers và giới hạn mutating table; MySQL và SQLite không có statement trigger tổng quát như PostgreSQL.
- **Tính đúng đắn còn phụ thuộc transaction, concurrency, ràng buộc, loại DML và side effects**. Một trigger hoạt động tốt khi UPDATE một hàng chưa chắc đúng khi UPDATE 10.000 hàng hoặc khi `MERGE`/cascade tạo thao tác khác.

Nguyên tắc cốt lõi là **thiết kế trigger để đúng với tập hàng của toàn câu lệnh, rồi mới xét hiệu năng và chi tiết triển khai**. Khi hiểu rõ sự khác biệt giữa **row-level** và **statement-level**, bạn có thể xây audit, kiểm tra ràng buộc và tổng hợp dữ liệu SQL mà không bỏ sót hàng, không nhân đôi kết quả và không phụ thuộc vào một thứ tự xử lý không được bảo đảm.
