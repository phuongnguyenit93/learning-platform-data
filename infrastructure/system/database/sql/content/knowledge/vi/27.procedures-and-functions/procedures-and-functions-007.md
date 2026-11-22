# Xử lý ngoại lệ và phát sinh lỗi có ý nghĩa

Trong **Database SQL**, stored procedure và function không chỉ đọc/ghi dữ liệu: chúng còn là nơi thực thi các quy tắc nghiệp vụ, kiểm tra tính nhất quán và phối hợp nhiều câu lệnh. Khi có tình huống bất thường — số tiền chuyển không hợp lệ, tài khoản không tồn tại, khóa trùng, vi phạm khóa ngoại, deadlock — người viết cần quyết định **phát sinh lỗi**, **xử lý lỗi**, hay **chuyển lỗi thành một kết quả nghiệp vụ có kiểm soát**.

Một thủ tục tốt không đơn thuần “không bị lỗi”. Nó phải:

- **Bảo vệ tính đúng đắn:** không lưu trạng thái dở dang khi một bước bắt buộc thất bại.
- **Trả tín hiệu có nghĩa:** người gọi phân biệt được đầu vào sai, vi phạm nghiệp vụ, xung đột đồng thời và lỗi hệ thống.
- **Không che giấu nguyên nhân:** lỗi ngoài dự kiến phải được truyền lên hoặc ghi nhận đúng nơi.
- **Không tiết lộ thông tin nhạy cảm:** thông báo cho client không chứa mật khẩu, truy vấn nội bộ, email hay dữ liệu cá nhân không cần thiết.
- **Có hành vi giao dịch rõ ràng:** biết phần nào được rollback, phần nào được giữ, và bên nào quyết định retry/commit.

Bài học thuộc chương **Thủ tục và hàm**. Phần chính sử dụng **PostgreSQL PL/pgSQL**, sau đó so sánh với **MySQL/MariaDB, SQL Server, Oracle và SQLite**. Các ví dụ có thể chạy trong database thử nghiệm, nhưng cú pháp xử lý lỗi **không hoàn toàn dùng chung giữa các DBMS**.

## 1. Lỗi của SQL khác “kết quả không có dữ liệu”

Hãy phân biệt các trường hợp:

| Tình huống | Cách thể hiện thường phù hợp | Ý nghĩa |
| --- | --- | --- |
| Tìm một đơn hàng nhưng không có dòng nào | Trả tập rỗng hoặc `NULL` theo hợp đồng | Có thể là kết quả bình thường |
| Người dùng nhập số tiền âm | Lỗi xác thực đầu vào | Thao tác không được phép thực hiện |
| Chuyển tiền vượt số dư | Lỗi nghiệp vụ có mã riêng | Người gọi có thể sửa yêu cầu |
| Chèn một `request_key` đã tồn tại | Lỗi ràng buộc duy nhất | Có thể là request trùng hoặc vấn đề idempotency |
| Giao dịch bị deadlock | Lỗi đồng thời, có thể retry có kiểm soát | Thường không phải sai dữ liệu đầu vào |
| Mất kết nối database | Lỗi hạ tầng | Có thể chưa biết giao dịch đã hoàn tất hay chưa |

Ví dụ:

```sql
SELECT *
FROM orders
WHERE order_id = 999999;
```

Nếu không có đơn hàng tương ứng, câu `SELECT` đơn thuần thường trả **0 dòng**, không tự phát sinh exception. Nhưng trong function nghiệp vụ “cập nhật đúng một đơn hàng đã tồn tại”, không tìm thấy đơn có thể là lỗi cần nêu rõ.

**Không dùng exception cho mọi nhánh điều khiển thông thường.** Khi “không tìm thấy” là một kết quả dự kiến, trả `NULL`, mã kết quả hoặc không có hàng có thể rõ ràng và rẻ hơn. Khi “không tìm thấy” vi phạm hợp đồng của thao tác, lỗi có ý nghĩa là lựa chọn hợp lý.

## 2. Phát sinh lỗi và bắt lỗi là hai thao tác khác nhau

**Phát sinh lỗi (raise/throw/signal)** chủ động thông báo không thể hoàn thành công việc theo hợp đồng.

**Bắt lỗi (catch/handle)** chặn một exception khi nó xuất hiện để quyết định:

1. Khôi phục một phần trạng thái hợp lệ nếu DBMS cho phép.
2. Chuyển lỗi kỹ thuật thành lỗi nghiệp vụ ổn định.
3. Bổ sung ngữ cảnh chẩn đoán.
4. Thực hiện thao tác xử lý an toàn rồi **ném lại lỗi**.
5. Trong tình huống lỗi thật sự dự kiến, chuyển thành một kết quả hợp lệ.

Sơ đồ tư duy:

```text
Caller gọi procedure/function
               |
               v
       Kiểm tra đầu vào
          /          \
       Hợp lệ      Không hợp lệ
         |             |
         v             v
   Thực hiện DML    RAISE lỗi
         |
      /     \
    Thành   Lỗi DB / lỗi nghiệp vụ
    công              |
      |               v
      v         Exception handler?
   Trả kết quả      /       \
                  Có        Không
                  |           |
           Xử lý cụ thể       v
           hoặc ném lại    Lỗi lên caller
                  |
             Trả kết quả
             hoặc ném lại
```

Một handler **không làm lỗi “biến mất” một cách miễn phí**: nếu nó bắt lỗi rồi tiếp tục, caller có thể tưởng thao tác đã thành công. Cần xác định rõ việc bắt lỗi có làm thay đổi kết quả nghiệp vụ hay không.

## 3. Các thành phần của một lỗi có ích

Một lỗi chuyên nghiệp có thể có nhiều trường:

| Thành phần | Chức năng | Ví dụ |
| --- | --- | --- |
| **Mã lỗi** | Cho chương trình nhận diện ổn định | `23505`, `22023`, `P3403` |
| **Thông báo** | Cho người đọc biết điều gì xảy ra | “Số dư không đủ để chuyển” |
| **Chi tiết** | Thêm ngữ cảnh được phép công bố | “Số tiền yêu cầu vượt số dư khả dụng” |
| **Gợi ý** | Đề xuất hành động khắc phục | “Chọn số tiền nhỏ hơn hoặc bổ sung số dư” |
| **Ngữ cảnh kỹ thuật** | Vị trí routine/dòng SQL gây lỗi | Tên function, dòng code, constraint |
| **Mức độ** | Lỗi dừng thao tác hay chỉ là cảnh báo | `EXCEPTION`, `WARNING`, `NOTICE` |

**Máy nên dựa vào mã ổn định, không parse chuỗi thông báo.** Thông báo có thể thay đổi ngôn ngữ hoặc cách diễn đạt; ứng dụng nên dựa trên SQLSTATE hoặc mã lỗi nghiệp vụ đã công bố.

Ví dụ thông điệp tốt:

```text
Code: P3403
Message: Số dư không đủ để thực hiện chuyển tiền
Hint: Kiểm tra số dư và thử với số tiền nhỏ hơn
```

Ví dụ không nên trả cho client:

```text
Account 101 balance=875.00, owner email=..., internal SQL=...
```

Khi dữ liệu nhạy cảm, thông điệp công khai có thể cần **ít chi tiết hơn** bản ghi audit/monitoring nội bộ.

## 4. SQLSTATE: nhóm mã lỗi quan trọng

Nhiều DBMS và driver có khái niệm mã trạng thái SQL chuẩn hoặc mã tương tự. Mã SQLSTATE thường có **5 ký tự**; hai ký tự đầu là **class**.

| Mã/class | Ý nghĩa điển hình | Thường làm gì? |
| --- | --- | --- |
| `22xxx` | Lỗi dữ liệu/giá trị | Sửa đầu vào hoặc xử lý dữ liệu không hợp lệ |
| `22012` | Chia cho 0 | Kiểm tra mẫu số |
| `22023` | Tham số/giá trị không hợp lệ (PostgreSQL: `invalid_parameter_value`) | Sửa tham số |
| `23xxx` | Vi phạm ràng buộc toàn vẹn | Kiểm tra NOT NULL, UNIQUE, FK, CHECK |
| `23502` | `not_null_violation` trong PostgreSQL | Điền giá trị bắt buộc |
| `23503` | `foreign_key_violation` trong PostgreSQL | Sửa tham chiếu |
| `23505` | `unique_violation` trong PostgreSQL | Xử lý bản ghi trùng |
| `23514` | `check_violation` trong PostgreSQL | Sửa dữ liệu theo CHECK |
| `40xxx` | Lỗi rollback giao dịch | Xem khả năng retry giao dịch |
| `40001` | `serialization_failure` (thường gặp) | Retry toàn giao dịch có kiểm soát |
| `40P01` | `deadlock_detected` trong PostgreSQL | Retry toàn giao dịch khi an toàn |
| `42xxx` | Lỗi cú pháp/quyền/định nghĩa đối tượng tùy DBMS | Sửa SQL, schema hoặc quyền |
| `P0001` | `raise_exception` mặc định của PL/pgSQL khi RAISE EXCEPTION không chỉ định SQLSTATE | Có thể cần thay bằng mã cụ thể |
| `45000` | SQLSTATE tổng quát cho lỗi do người dùng phát sinh trong MySQL/MariaDB | Phân biệt thêm mã nghiệp vụ ở tầng ứng dụng |

Bảng này dùng nhiều **mã cụ thể của PostgreSQL** để thực hành. Không nên giả định vendor nào cũng dùng cùng mã cho mọi tình huống. SQL Server còn có **error number** riêng; Oracle thường dùng **ORA-nnnnn** và mã lỗi của Oracle.

### Mã tùy chỉnh

Trong PL/pgSQL có thể chọn SQLSTATE gồm 5 ký tự chữ in hoa/chữ số, ví dụ:

- `P3401`: tài khoản không tồn tại.
- `P3402`: tài khoản bị vô hiệu hóa.
- `P3403`: số dư không đủ.
- `P3404`: từ chối yêu cầu chuyển vì quy tắc nghiệp vụ khác.

Các mã này chỉ là **quy ước riêng của bài thực hành**, không phải mã chuẩn cho mọi hệ thống. Tránh tạo mã kết thúc bằng `000` vì các mã class rộng không phù hợp để nhận diện một điều kiện cụ thể trong handler.

## 5. PostgreSQL: RAISE EXCEPTION cơ bản

Trong **PL/pgSQL function, procedure hoặc DO block**, cú pháp đơn giản:

```sql
DO $$
DECLARE
    v_amount NUMERIC := -10;
BEGIN
    IF v_amount <= 0 THEN
        RAISE EXCEPTION 'Số tiền phải lớn hơn 0, nhận được %', v_amount;
    END IF;
END;
$$;
```

Khi chạy, PL/pgSQL phát sinh exception, và nếu không có handler phù hợp, câu lệnh thất bại.

Dấu `%` trong chuỗi format của `RAISE` được thay bằng giá trị truyền sau chuỗi; để đưa dấu phần trăm theo nghĩa ký tự, dùng `%%` trong cú pháp format tương ứng.

### RAISE với mã lỗi, chi tiết và gợi ý

```sql
DO $$
DECLARE
    v_amount NUMERIC := -10;
BEGIN
    IF v_amount <= 0 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Số tiền chuyển phải là số dương',
            DETAIL = format('Giá trị đầu vào không hợp lệ: %s', v_amount),
            HINT = 'Nhập số tiền lớn hơn 0.';
    END IF;
END;
$$;
```

Cấu trúc `USING` cho phép đặt các trường như `MESSAGE`, `DETAIL`, `HINT`, `ERRCODE`. Không đưa thông tin cá nhân, chuỗi kết nối hoặc bí mật vào `DETAIL` nếu có khả năng đi tới client/log không phù hợp.

Có thể dùng dạng:

```sql
RAISE EXCEPTION 'Số tiền không hợp lệ: %', v_amount
    USING ERRCODE = '22023';
```

Cả hai đều tạo lỗi, nhưng cách `USING` dễ mở rộng khi cần mã, hint và thông điệp rõ ràng.

## 6. PostgreSQL: các mức RAISE khác nhau

`RAISE` có thể ghi nhận một thông điệp mà **không làm thao tác thất bại** nếu chọn mức độ không phải `EXCEPTION`.

```sql
DO $$
BEGIN
    RAISE DEBUG 'Thông tin debug';
    RAISE LOG 'Thông tin log';
    RAISE INFO 'Thông tin tham khảo';
    RAISE NOTICE 'Đã cập nhật bản ghi';
    RAISE WARNING 'Cấu hình sắp bị ngừng hỗ trợ';
    -- RAISE EXCEPTION 'Lỗi buộc dừng thao tác';
END;
$$;
```

| Mức | Tác động khái quát |
| --- | --- |
| `DEBUG` | Thông tin phục vụ điều tra; khả năng hiển thị phụ thuộc cấu hình |
| `LOG` | Thông tin gửi tới hệ thống log theo quy tắc của PostgreSQL |
| `INFO` | Thông điệp thông tin; không tự abort thao tác |
| `NOTICE` | Thông báo thường thấy khi chạy script |
| `WARNING` | Cảnh báo có điều đáng chú ý nhưng chưa abort |
| `EXCEPTION` | Phát sinh lỗi; nếu không bị bắt, thao tác thất bại |

Việc client có thấy từng mức hay không phụ thuộc các thiết lập như `client_min_messages`, `log_min_messages` và cấu hình môi trường.

**Không dùng `NOTICE` hoặc `WARNING` thay exception khi một quy tắc nghiệp vụ bắt buộc bị vi phạm.** Nếu chỉ hiện thông báo rồi vẫn commit, caller có thể tưởng thao tác đã thành công.

## 7. Chuẩn bị bộ dữ liệu PostgreSQL để thực hành

Các ví dụ sau dùng schema có tiền tố riêng `sql341`. Chỉ chạy trên **database học tập** mà bạn có quyền tạo schema, function và table. Bộ dữ liệu minh họa mô hình chuyển số dư, không phải hệ thống ngân hàng thực: giao dịch tiền thật cần thêm cơ chế ledger, kiểm soát ngoại tệ, idempotency, phân quyền và kiểm toán nghiêm ngặt.

### 7.1. Tạo schema và bảng

```sql
CREATE SCHEMA sql341;

CREATE TABLE sql341.accounts (
    account_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL,
    balance NUMERIC(14,2) NOT NULL
        CHECK (balance >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE sql341.transfers (
    transfer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_key TEXT NOT NULL UNIQUE,
    from_account INTEGER NOT NULL
        REFERENCES sql341.accounts(account_id),
    to_account INTEGER NOT NULL
        REFERENCES sql341.accounts(account_id),
    amount NUMERIC(14,2) NOT NULL
        CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account <> to_account)
);
```

Ràng buộc là **lớp bảo vệ ở database**:

- `PRIMARY KEY` ngăn account/transfer trùng ID.
- `UNIQUE(request_key)` ngăn ghi cùng mã yêu cầu hai lần.
- `FOREIGN KEY` ngăn tham chiếu account không tồn tại.
- `CHECK(balance >= 0)` và `CHECK(amount > 0)` bảo vệ miền giá trị.

Kiểm tra ở function giúp trả lỗi dễ hiểu **trước khi** chạm constraint; constraint vẫn cần để bảo vệ dữ liệu trước mọi đường ghi khác.

### 7.2. Chèn dữ liệu

```sql
INSERT INTO sql341.accounts (account_id, label, balance, active)
VALUES
    (101, 'Ví nguồn',      1000.00, TRUE),
    (102, 'Ví đích',        200.00, TRUE),
    (103, 'Ví tạm khóa',     50.00, FALSE);
```

Kiểm tra:

```sql
SELECT account_id, label, balance, active
FROM sql341.accounts
ORDER BY account_id;
```

Bảng đầu vào có hai account hoạt động và một account vô hiệu hóa, đủ để thử cả thao tác thành công và lỗi nghiệp vụ.

## 8. Viết function chuyển số dư với lỗi có nghĩa

Bài lab dùng function `transfer_funds` nhận:

- `p_request_key`: khóa yêu cầu do caller cung cấp để phát hiện yêu cầu trùng.
- `p_from_account`: account nguồn.
- `p_to_account`: account đích.
- `p_amount`: số tiền chuyển.

Kết quả: `transfer_id` khi hoàn thành. Nếu không thể hoàn thành, function **ném lỗi**, không trả `NULL` như thể chuyển thành công.

### 8.1. Function PL/pgSQL

```sql
CREATE OR REPLACE FUNCTION sql341.transfer_funds(
    p_request_key TEXT,
    p_from_account INTEGER,
    p_to_account INTEGER,
    p_amount NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $func$
DECLARE
    v_source_balance NUMERIC(14,2);
    v_source_active BOOLEAN;
    v_target_active BOOLEAN;
    v_transfer_id BIGINT;
BEGIN
    -- 1. Kiểm tra tham số trước khi ghi dữ liệu.
    IF p_request_key IS NULL OR btrim(p_request_key) = '' THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'request_key không được để trống',
            HINT = 'Truyền một khóa yêu cầu có ý nghĩa.';
    END IF;

    IF p_from_account IS NULL
       OR p_to_account IS NULL
       OR p_from_account = p_to_account THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Tài khoản nguồn và đích phải hợp lệ, khác nhau';
    END IF;

    IF p_amount IS NULL
       OR p_amount <= 0
       OR p_amount <> round(p_amount, 2) THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Số tiền phải dương và có tối đa 2 chữ số thập phân',
            HINT = 'Dùng số tiền dương, ví dụ 125.00.';
    END IF;

    -- 2. Khóa hai account theo thứ tự ID để giảm nguy cơ deadlock.
    PERFORM 1
    FROM sql341.accounts
    WHERE account_id IN (p_from_account, p_to_account)
    ORDER BY account_id
    FOR UPDATE;

    -- 3. Kiểm tra account nguồn.
    SELECT balance, active
    INTO v_source_balance, v_source_active
    FROM sql341.accounts
    WHERE account_id = p_from_account;

    IF NOT FOUND THEN
        RAISE EXCEPTION SQLSTATE 'P3401'
            USING MESSAGE = 'Không tìm thấy tài khoản nguồn';
    END IF;

    -- 4. Kiểm tra account đích.
    SELECT active
    INTO v_target_active
    FROM sql341.accounts
    WHERE account_id = p_to_account;

    IF NOT FOUND THEN
        RAISE EXCEPTION SQLSTATE 'P3401'
            USING MESSAGE = 'Không tìm thấy tài khoản đích';
    END IF;

    IF NOT v_source_active OR NOT v_target_active THEN
        RAISE EXCEPTION SQLSTATE 'P3402'
            USING MESSAGE = 'Một trong hai tài khoản đang bị vô hiệu hóa';
    END IF;

    IF v_source_balance < p_amount THEN
        RAISE EXCEPTION SQLSTATE 'P3403'
            USING
                MESSAGE = 'Số dư không đủ để chuyển tiền',
                HINT = 'Giảm số tiền hoặc bổ sung số dư.';
    END IF;

    -- 5. Ghi nhận yêu cầu. UNIQUE(request_key) chặn trùng.
    INSERT INTO sql341.transfers
        (request_key, from_account, to_account, amount)
    VALUES
        (p_request_key, p_from_account, p_to_account, p_amount)
    RETURNING transfer_id INTO v_transfer_id;

    -- 6. Cập nhật cả hai account trong cùng statement gọi function.
    UPDATE sql341.accounts
    SET balance = balance - p_amount
    WHERE account_id = p_from_account;

    UPDATE sql341.accounts
    SET balance = balance + p_amount
    WHERE account_id = p_to_account;

    RETURN v_transfer_id;
END;
$func$;
```

### 8.2. Vì sao thứ tự các bước quan trọng?

Function kiểm tra **tham số** trước, rồi khóa hàng và kiểm tra **trạng thái tài khoản**, sau đó mới INSERT/UPDATE.

Lợi ích:

- Đầu vào sai được trả thông báo cụ thể.
- Kiểm tra số dư sau khi khóa account làm giảm nguy cơ hai phiên cùng dùng một số dư cũ.
- Khóa các account theo `account_id` giúp giảm nguy cơ deadlock khi các phiên chuyển theo chiều ngược nhau.
- Ràng buộc bảng vẫn bảo vệ dữ liệu nếu có một đường ghi khác bỏ qua function.
- Khi statement gọi function phát sinh lỗi chưa được bắt, các thay đổi của statement không được commit dở dang.

Mẫu trên chỉ minh họa logic một loại tiền, số lẻ hai chữ số. Hệ thực cần thiết kế quyền gọi, hạn mức, chống gian lận, định danh yêu cầu, audit, ledger bất biến và cách xác định trạng thái cuối khi kết nối thất bại.

## 9. Chạy trường hợp thành công và trường hợp lỗi

### 9.1. Chuyển thành công

```sql
SELECT sql341.transfer_funds(
    'request-001', 101, 102, 125.00
) AS new_transfer_id;
```

Kiểm tra:

```sql
SELECT account_id, balance
FROM sql341.accounts
ORDER BY account_id;

SELECT
    transfer_id, request_key, from_account, to_account, amount
FROM sql341.transfers
ORDER BY transfer_id;
```

Sau lần chuyển này:

| account_id | balance |
| ---: | ---: |
| 101 | 875.00 |
| 102 | 325.00 |
| 103 | 50.00 |

Có một dòng chuyển `request-001`, số tiền 125.00.

### 9.2. Số tiền không hợp lệ

```sql
-- Dự kiến ERROR, SQLSTATE 22023:
SELECT sql341.transfer_funds(
    'request-invalid', 101, 102, -50.00
);
```

Function phát sinh lỗi ngay khi kiểm tra tham số. Không có bản ghi transfer hay biến động số dư nào được ghi cho yêu cầu này.

### 9.3. Không đủ số dư

```sql
-- Dự kiến ERROR, SQLSTATE P3403:
SELECT sql341.transfer_funds(
    'request-too-large', 101, 102, 100000.00
);
```

Lỗi mô tả **quy tắc nghiệp vụ** thay vì trả thông báo chung “something went wrong”. Nếu lỗi này không được bắt và bỏ qua, statement thất bại.

### 9.4. Account không tồn tại hoặc bị khóa

```sql
-- Dự kiến ERROR, SQLSTATE P3401:
SELECT sql341.transfer_funds(
    'request-no-account', 101, 999, 10.00
);

-- Dự kiến ERROR, SQLSTATE P3402:
SELECT sql341.transfer_funds(
    'request-inactive', 101, 103, 10.00
);
```

**Chạy mỗi lệnh gây lỗi như một thử nghiệm riêng.** Nếu bạn đang ở trong một transaction PostgreSQL mở bằng `BEGIN`, sau lỗi không được bắt, transaction chuyển sang trạng thái failed và các câu lệnh tiếp theo sẽ báo “current transaction is aborted” cho đến khi `ROLLBACK` hoặc khôi phục bằng savepoint phù hợp.

### 9.5. Request key trùng

```sql
-- request-001 đã tồn tại sau lệnh chuyển thành công:
SELECT sql341.transfer_funds(
    'request-001', 101, 102, 125.00
);
```

Trên thiết kế lab, lỗi trùng khóa phát sinh từ `UNIQUE(request_key)`, thường có SQLSTATE `23505` trong PostgreSQL. Do statement thất bại, nó **không được coi là chuyển thêm lần thứ hai**.

**Phân biệt phát hiện trùng với idempotency đầy đủ:** một API idempotent còn phải xác minh cùng `request_key` có cùng nội dung yêu cầu hay không, truy vấn/lưu kết quả của yêu cầu đã xử lý và xử lý trường hợp timeout không biết giao dịch đã commit chưa. Lab này chỉ dùng unique constraint để chặn trùng, **chưa tự động trả lại kết quả cũ**.

## 10. Không “bắt mọi lỗi rồi trả 0” trong function chuyển tiền

Một anti-pattern:

```sql
-- KHÔNG dùng mẫu này cho giao dịch quan trọng.
CREATE OR REPLACE FUNCTION sql341.bad_transfer_example()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Thao tác chuyển tiền thất bại';

EXCEPTION WHEN OTHERS THEN
    RETURN 0;
END;
$$;
```

Caller thấy function trả 0, nhưng không biết:

- Có cập nhật được gì không?
- Trả 0 có nghĩa “không có dữ liệu”, “thất bại” hay “ID 0”?
- Lỗi là do không đủ tiền, lỗi hạ tầng hay lỗi lập trình?
- Có thể retry an toàn không?

Bắt lỗi rộng chỉ để tránh exception thường **che nguyên nhân**, gây báo cáo thành công giả hoặc xử lý sai.

Nếu API có hợp đồng “trả object kết quả thay vì exception”, hãy định nghĩa rõ kiểu kết quả, mã lỗi, tính nguyên tử và trách nhiệm caller. Đối với lỗi chưa lường trước, thường nên truyền exception ra ngoài để cơ chế giám sát và giao dịch xử lý.

## 11. PL/pgSQL: cú pháp EXCEPTION WHEN

PL/pgSQL cho phép bắt exception ở cuối **một block**:

```sql
DO $$
BEGIN
    BEGIN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Đầu vào không hợp lệ';

    EXCEPTION
        WHEN invalid_parameter_value THEN
            RAISE NOTICE 'Đã bắt lỗi giá trị đầu vào';
    END;

    RAISE NOTICE 'Block bên ngoài vẫn tiếp tục';
END;
$$;
```

Các phần:

- `BEGIN ... END`: khối PL/pgSQL có thể chứa lệnh.
- `EXCEPTION WHEN condition THEN ...`: handler nằm **cuối block**.
- `invalid_parameter_value`: tên condition của SQLSTATE `22023` trong PostgreSQL.
- `RAISE NOTICE`: chỉ thông báo; không tự throw lại.
- Block bên ngoài vẫn tiếp tục sau khi inner block xử lý lỗi.

Có thể bắt theo mã:

```sql
EXCEPTION
    WHEN SQLSTATE 'P3403' THEN
        RAISE NOTICE 'Phát hiện lỗi số dư không đủ';
```

Hoặc nhiều condition:

```sql
EXCEPTION
    WHEN unique_violation OR foreign_key_violation THEN
        RAISE NOTICE 'Vi phạm tính toàn vẹn dữ liệu';
```

**Không đưa tất cả lỗi vào một handler rồi gán cùng ý nghĩa.** `unique_violation` và `foreign_key_violation` thường có cách khắc phục khác nhau.

## 12. Bắt lỗi rồi ném lại: RAISE không tham số

Trong handler PL/pgSQL, dùng:

```sql
RAISE;
```

để **ném lại exception đang được xử lý** cùng mã và ngữ cảnh thích hợp.

Ví dụ:

```sql
DO $$
BEGIN
    BEGIN
        PERFORM sql341.transfer_funds(
            'request-should-fail', 101, 102, 999999.00
        );

    EXCEPTION
        WHEN SQLSTATE 'P3403' THEN
            RAISE NOTICE 'Không đủ số dư; không tiếp tục chuyển';
            RAISE;
    END;
END;
$$;
```

Câu `RAISE;` **không phải thông báo tùy ý**: nó chuyển lỗi gốc lên caller. Vì vậy kết quả cuối vẫn là ERROR `P3403`.

Mẫu thường có ích khi bạn cần:

- Bổ sung metric/trace không nhạy cảm.
- Làm cleanup bên ngoài database nếu có cơ chế phù hợp.
- Quyết định rollback transaction ở caller.
- Vẫn bảo toàn tín hiệu lỗi để tầng ứng dụng xử lý.

**Không dùng RAISE EXCEPTION '... lỗi bất kỳ' thay cho RAISE; nếu muốn giữ mã gốc.** Tạo lỗi mới có thể làm mất SQLSTATE cụ thể, ngữ cảnh constraint và khả năng retry chính xác.

## 13. GET STACKED DIAGNOSTICS: lấy chi tiết lỗi đã bắt

Trong PostgreSQL, bên trong `EXCEPTION` handler, `GET STACKED DIAGNOSTICS` đọc dữ liệu về **exception đang được xử lý**.

```sql
DO $$
DECLARE
    v_state TEXT;
    v_message TEXT;
    v_detail TEXT;
    v_hint TEXT;
    v_context TEXT;
BEGIN
    BEGIN
        PERFORM sql341.transfer_funds(
            'diag-fail', 101, 102, 999999.00
        );

    EXCEPTION WHEN OTHERS THEN
        GET STACKED DIAGNOSTICS
            v_state   = RETURNED_SQLSTATE,
            v_message = MESSAGE_TEXT,
            v_detail  = PG_EXCEPTION_DETAIL,
            v_hint    = PG_EXCEPTION_HINT,
            v_context = PG_EXCEPTION_CONTEXT;

        RAISE NOTICE 'SQLSTATE: %, message: %',
            v_state, v_message;
        RAISE NOTICE 'hint: %', v_hint;
        -- Trong hệ thật, kiểm soát nơi lưu/hiển thị context kỹ thuật.
    END;
END;
$$;
```

Các trường phổ biến:

| Trường PL/pgSQL | Mục đích |
| --- | --- |
| `RETURNED_SQLSTATE` | Mã SQLSTATE của exception |
| `MESSAGE_TEXT` | Thông báo chính |
| `PG_EXCEPTION_DETAIL` | Chi tiết bổ sung nếu có |
| `PG_EXCEPTION_HINT` | Gợi ý bổ sung nếu có |
| `PG_EXCEPTION_CONTEXT` | Ngữ cảnh stack/vị trí phát sinh |
| `CONSTRAINT_NAME` | Tên constraint liên quan nếu có |
| `TABLE_NAME` / `SCHEMA_NAME` | Đối tượng liên quan nếu được cung cấp |
| `COLUMN_NAME` | Cột liên quan nếu được cung cấp |

Các trường có thể rỗng tùy loại lỗi. Không giả định mọi exception đều mang đầy đủ tên bảng, constraint, cột.

### SQLSTATE và SQLERRM viết tắt

Trong `EXCEPTION` handler, PostgreSQL cũng có các biến đặc biệt:

```sql
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Lỗi %, %', SQLSTATE, SQLERRM;
```

`SQLSTATE` và `SQLERRM` thuận tiện với trường hợp đơn giản. `GET STACKED DIAGNOSTICS` phù hợp khi cần nhiều thành phần chi tiết.

**Đừng dùng `WHEN OTHERS` như chính sách nuốt lỗi mặc định.** Trong PostgreSQL, handler `OTHERS` không bắt một số điều kiện đặc biệt như `QUERY_CANCELED` và `ASSERT_FAILURE` theo quy tắc của PL/pgSQL; quan trọng hơn, một handler rộng còn có thể che lỗi lập trình không dự kiến.

## 14. ROLLBACK nào xảy ra khi bắt exception trong PL/pgSQL?

Một chi tiết cực kỳ quan trọng: **block PL/pgSQL có `EXCEPTION` sử dụng cơ chế subtransaction nội bộ**. Khi một lỗi xảy ra trong block và được handler xử lý:

- Những **thay đổi dữ liệu** thực hiện bên trong block đã thất bại được rollback về trạng thái trước khi block đó bắt đầu.
- Các câu lệnh sau handler có thể tiếp tục trong transaction bên ngoài.
- Các **biến PL/pgSQL** không nhất thiết được hoàn nguyên như dữ liệu bảng; giá trị biến có thể phản ánh phép gán trước lỗi.
- Các thay đổi ngoài block thất bại, nếu thuộc transaction còn hợp lệ, có thể vẫn tồn tại.

Ví dụ độc lập:

```sql
DO $$
DECLARE
    v_before NUMERIC(14,2);
    v_after NUMERIC(14,2);
BEGIN
    SELECT balance INTO v_before
    FROM sql341.accounts
    WHERE account_id = 101;

    BEGIN
        UPDATE sql341.accounts
        SET balance = balance - 20
        WHERE account_id = 101;

        RAISE EXCEPTION SQLSTATE 'P3404'
            USING MESSAGE = 'Chủ động thử rollback inner block';

    EXCEPTION WHEN SQLSTATE 'P3404' THEN
        RAISE NOTICE 'Lỗi trong inner block đã được xử lý';
    END;

    SELECT balance INTO v_after
    FROM sql341.accounts
    WHERE account_id = 101;

    RAISE NOTICE 'Trước: %, sau: %', v_before, v_after;
END;
$$;
```

Kỳ vọng `v_after = v_before` vì lệnh UPDATE trong inner block bị rollback khi exception xảy ra. Outer block vẫn chạy tiếp.

### Phân biệt ba phạm vi rollback

| Tình huống | Phạm vi điển hình |
| --- | --- |
| Lỗi SQL không được bắt trong một statement PostgreSQL | Statement thất bại; nếu đang trong explicit transaction, transaction ở trạng thái failed cho đến khi rollback |
| Lỗi được bắt bởi PL/pgSQL `EXCEPTION` block | Những thay đổi persistent trong block thất bại được rollback như một subtransaction; outer block có thể tiếp tục |
| Caller thực hiện `ROLLBACK` cả transaction | Toàn bộ thay đổi chưa commit của transaction bị hoàn nguyên |

Do vậy câu “bắt exception thì mọi thay đổi trước đó đều bị rollback” là **quá rộng**. Cần xác định ranh giới block và transaction.

## 15. Không gọi COMMIT/ROLLBACK tùy tiện trong function

Trong PostgreSQL, function gọi bằng `SELECT my_function(...)` **không phải nơi được phép tùy ý `COMMIT` hoặc `ROLLBACK` transaction của caller**.

Một số **procedure** gọi bằng `CALL` và các `DO` block trong ngữ cảnh phù hợp có thể thực hiện transaction control với các ràng buộc cụ thể; ví dụ transaction control trong block có `EXCEPTION` bị hạn chế vì block đó đang có subtransaction.

Với mẫu `sql341.transfer_funds`, lựa chọn đơn giản là:

- Function **chỉ thực hiện logic chuyển**, không tự `COMMIT`.
- Caller quyết định gọi trong transaction riêng hoặc transaction đang có.
- Khi function trả thành công và transaction được commit, thay đổi mới bền vững.
- Nếu function ném lỗi và caller rollback, thay đổi không được giữ.

Ví dụ client SQL:

```sql
BEGIN;

SELECT sql341.transfer_funds(
    'request-002', 101, 102, 15.00
);

-- Các bước SQL khác cùng giao dịch nếu thật sự cần.

COMMIT;
```

Nếu có lỗi giữa `BEGIN` và `COMMIT`, client phải xử lý đúng trạng thái transaction và thường dùng `ROLLBACK`, không cố tiếp tục commit như thể không có gì xảy ra.

## 16. Savepoint: xử lý lỗi ở cấp transaction SQL

Ngoài `EXCEPTION` trong PL/pgSQL, caller có thể dùng `SAVEPOINT` để tạo điểm khôi phục trong transaction.

```sql
BEGIN;

SAVEPOINT before_optional_step;

-- Ví dụ một câu lệnh có thể thất bại:
-- SELECT sql341.transfer_funds(
--     'request-optional', 101, 102, 999999.00
-- );

-- Nếu bước trên lỗi:
-- ROLLBACK TO SAVEPOINT before_optional_step;

-- Khi xử lý xong điểm khôi phục:
-- RELEASE SAVEPOINT before_optional_step;

COMMIT;
```

Đây là **khung thao tác**, không phải script chạy liên tục đầy đủ vì nhánh rollback phụ thuộc kết quả thực thi. Trong thực tế, driver hoặc code ứng dụng phải bắt lỗi, chọn rollback tới savepoint hoặc rollback cả transaction, rồi quyết định tiếp tục.

Không dùng savepoint để “bỏ qua” một lỗi bắt buộc trong thao tác tài chính. Nếu chuyển tiền là công việc chính, lỗi không đủ số dư thường phải làm **toàn bộ yêu cầu thất bại**, chứ không nên tiếp tục commit một phần workflow mà không có quyết định nghiệp vụ rõ ràng.

## 17. SELECT INTO và trường hợp không tìm thấy dòng

Trong PL/pgSQL:

```sql
SELECT balance
INTO v_source_balance
FROM sql341.accounts
WHERE account_id = p_from_account;
```

Nếu không tìm được dòng, biến đích có thể nhận `NULL` và `FOUND` là `FALSE`, thay vì ném exception tự động.

Vì thế function `transfer_funds` kiểm tra:

```sql
IF NOT FOUND THEN
    RAISE EXCEPTION SQLSTATE 'P3401'
        USING MESSAGE = 'Không tìm thấy tài khoản nguồn';
END IF;
```

### SELECT INTO STRICT

Khi hợp đồng yêu cầu **đúng một dòng**, có thể dùng:

```sql
SELECT balance
INTO STRICT v_source_balance
FROM sql341.accounts
WHERE account_id = p_from_account;
```

Trong PL/pgSQL:

- Không có dòng: phát sinh `NO_DATA_FOUND` (condition PL/pgSQL).
- Nhiều hơn một dòng: phát sinh `TOO_MANY_ROWS`.
- Đúng một dòng: gán biến.

Lưu ý `SELECT INTO` bên trong **PL/pgSQL** là cú pháp gán giá trị vào biến, khác một số cú pháp SQL top-level `SELECT INTO new_table`. Khi bảng có khóa chính theo account ID, tình huống nhiều dòng không thể xảy ra nếu query chỉ lọc theo PK và dữ liệu toàn vẹn.

### Bắt riêng khi không có dữ liệu

```sql
BEGIN
    SELECT balance
    INTO STRICT v_source_balance
    FROM sql341.accounts
    WHERE account_id = p_from_account;

EXCEPTION WHEN NO_DATA_FOUND THEN
    RAISE EXCEPTION SQLSTATE 'P3401'
        USING MESSAGE = 'Tài khoản nguồn không tồn tại';
END;
```

Đây là mẫu trích đoạn để đặt trong function có biến đã khai báo. Nó chuyển lỗi kỹ thuật “không có dòng” thành lỗi nghiệp vụ rõ ràng.

**Không nhầm `NO_DATA_FOUND` trong `INTO STRICT` với mọi `SELECT` trả 0 dòng:** câu `SELECT` thông thường trả tập rỗng không phát sinh exception.

## 18. Kiểm tra FOUND và số dòng bị ảnh hưởng

Sau các câu DML trong PL/pgSQL, có thể kiểm tra liệu thao tác có tác động dòng nào không.

Ví dụ:

```sql
UPDATE sql341.accounts
SET active = FALSE
WHERE account_id = 999;

IF NOT FOUND THEN
    RAISE EXCEPTION SQLSTATE 'P3401'
        USING MESSAGE = 'Không tìm thấy tài khoản cần khóa';
END IF;
```

`FOUND` là biến trạng thái của PL/pgSQL, được cập nhật bởi một số câu lệnh như `SELECT INTO`, `PERFORM`, `INSERT`, `UPDATE`, `DELETE`. Nó có thể đổi khi câu lệnh khác chạy, nên hãy kiểm tra **ngay sau câu lệnh liên quan**.

Nếu cần số lượng dòng cụ thể:

```sql
GET DIAGNOSTICS v_row_count = ROW_COUNT;
```

`ROW_COUNT` là số dòng được xử lý bởi câu SQL gần nhất theo quy tắc PL/pgSQL, không phải biến lưu “tổng số dòng của cả transaction”.

Với hợp đồng “phải cập nhật đúng một bản ghi”, có thể kiểm tra `v_row_count = 1`. Nhưng ràng buộc primary key/unique vẫn nên được thiết kế đúng để đảm bảo tính duy nhất, không dùng mỗi kiểm tra sau UPDATE làm thay thế constraint.

## 19. Constraint là nguồn phát sinh lỗi đáng tin cậy

Các ràng buộc database hoạt động ngay cả khi code ứng dụng hoặc routine không tự kiểm tra:

```sql
-- Thử trên bảng học tập, dự kiến lỗi CHECK:
INSERT INTO sql341.accounts (account_id, label, balance)
VALUES (201, 'Sai số dư', -1.00);
```

PostgreSQL thường trả `23514` (`check_violation`).

```sql
-- Dự kiến lỗi PRIMARY KEY/UNIQUE:
INSERT INTO sql341.accounts (account_id, label, balance)
VALUES (101, 'Trùng ID', 10.00);
```

PostgreSQL thường trả `23505`.

### Vì sao không chỉ SELECT kiểm tra trước rồi INSERT?

Mẫu:

```sql
-- Dễ có race nếu dùng làm bảo đảm duy nhất.
IF NOT EXISTS (
    SELECT 1
    FROM sql341.transfers
    WHERE request_key = p_request_key
) THEN
    INSERT INTO sql341.transfers (...);
END IF;
```

Hai transaction có thể cùng thấy “chưa có khóa” trước khi một transaction kịp insert. **UNIQUE constraint** mới là lớp chống trùng cần thiết.

Bạn có thể kiểm tra trước để trả lỗi sớm cho tình huống bình thường, nhưng **vẫn phải xử lý `unique_violation` khi insert**, vì race vẫn tồn tại.

Tương tự, điều kiện check “số dư đủ” phải đi cùng cơ chế khóa/UPDATE có điều kiện thích hợp trong môi trường đồng thời; không đọc số dư một lần rồi cập nhật không có bảo vệ.

## 20. Bắt lỗi ràng buộc phải đủ hẹp

Ví dụ một function insert transfer bị `unique_violation`. Viết:

```sql
EXCEPTION WHEN unique_violation THEN
    RAISE EXCEPTION SQLSTATE 'P3404'
        USING MESSAGE = 'request_key đã được sử dụng';
```

có thể hợp lý **chỉ khi bạn biết chắc unique constraint nào vừa vi phạm**. Nhưng cùng block có thể insert vào nhiều bảng hoặc đụng một unique constraint khác. Bắt mọi `23505` và chuyển thành “request_key trùng” sẽ gán sai nguyên nhân.

Ở PostgreSQL, có thể lấy **tên constraint**:

```sql
-- Trích đoạn trong EXCEPTION handler:
DECLARE
    v_constraint TEXT;
BEGIN
    -- Lệnh INSERT có thể ném unique_violation.
    NULL;

EXCEPTION WHEN unique_violation THEN
    GET STACKED DIAGNOSTICS
        v_constraint = CONSTRAINT_NAME;

    IF v_constraint = 'transfers_request_key_key' THEN
        RAISE EXCEPTION SQLSTATE 'P3404'
            USING MESSAGE = 'request_key đã được sử dụng';
    ELSE
        RAISE;  -- Giữ nguyên lỗi nếu không đúng constraint kỳ vọng.
    END IF;
END;
```

Đây là **đoạn cấu trúc block minh họa**, không phải function hoàn chỉnh; tên `transfers_request_key_key` là tên mặc định điển hình cho ràng buộc UNIQUE của bảng lab nếu không đặt tên thủ công. Trong hệ thật, **nên đặt tên constraint tường minh** và kiểm tra metadata sau migration.

Nếu đổi mọi `23505` thành cùng một thông điệp, bạn sẽ khó phát hiện lỗi dữ liệu hoặc bug khác không liên quan đến request key.

## 21. Không log lỗi trong cùng transaction rồi cho rằng log sẽ tồn tại

Giả sử:

```sql
EXCEPTION WHEN OTHERS THEN
    INSERT INTO sql341.error_log (...);
    RAISE;
```

Nếu handler chèn log vào cùng transaction rồi `RAISE;` làm caller rollback cả transaction, **dòng log đó cũng có thể bị rollback**. Điều này là đặc tính giao dịch, không phải lỗi của logger.

Phân biệt:

- **Log bên trong database cùng transaction:** phù hợp nếu muốn log được commit cùng kết quả hợp lệ, nhưng không bảo đảm tồn tại khi toàn transaction rollback.
- **Log phía ứng dụng/monitoring:** có thể ghi nhận lỗi sau khi DB trả exception, theo cơ chế riêng.
- **Log server:** PostgreSQL có logging hệ thống tùy cấu hình; vẫn cần quản lý dữ liệu nhạy cảm và retention.
- **Audit nghiệp vụ:** cần thiết kế tính nhất quán và độ bền riêng, không chỉ `INSERT` vào bảng log rồi ném lỗi.

Đừng “sửa” bằng cách lạm dụng transaction độc lập hoặc side effect ngoài database nếu chưa thiết kế tính nhất quán và quyền truy cập. Trong nhiều trường hợp **caller là nơi phù hợp nhất để ghi nhận lỗi thất bại**.

## 22. Khi nào nên xử lý lỗi và tiếp tục?

Có những lỗi thật sự có thể phục hồi cục bộ.

Ví dụ xử lý import một danh sách bản ghi, được yêu cầu **bỏ qua bản ghi không hợp lệ** nhưng tiếp tục các bản ghi khác. Một block riêng cho mỗi bản ghi có thể bắt lỗi xác thực dự kiến và ghi nhận kết quả lỗi thay vì dừng toàn bộ import.

Mẫu ý tưởng:

```sql
DO $$
DECLARE
    v_input INTEGER;
BEGIN
    FOREACH v_input IN ARRAY ARRAY[1, -2, 3]
    LOOP
        BEGIN
            IF v_input <= 0 THEN
                RAISE EXCEPTION SQLSTATE '22023'
                    USING MESSAGE = 'Giá trị đầu vào phải dương';
            END IF;

            RAISE NOTICE 'Xử lý thành công: %', v_input;

        EXCEPTION WHEN invalid_parameter_value THEN
            RAISE NOTICE 'Bỏ qua giá trị không hợp lệ: %', v_input;
        END;
    END LOOP;
END;
$$;
```

Đây là luồng phục hồi **đã được mô tả trong hợp đồng nhập dữ liệu**.

Tuy nhiên:

- Nếu import yêu cầu **all-or-nothing**, không nên tiếp tục sau mỗi lỗi.
- Nếu lỗi do kết nối, disk full hoặc constraint quan trọng, không nên gộp vào nhóm “bản ghi bị bỏ qua”.
- Mỗi `EXCEPTION` block có chi phí quản lý subtransaction; không dùng lỗi làm vòng lặp điều khiển thông thường khi có thể kiểm tra trước.

## 23. Phát sinh lỗi nghiệp vụ hay trả mã kết quả?

Có hai phong cách API phổ biến:

**A. Lỗi bằng exception**

```sql
SELECT sql341.transfer_funds('request-003', 101, 102, 10.00);
```

Thành công trả `transfer_id`; không thành công phát sinh exception với mã cụ thể. Phong cách này phù hợp khi thao tác **không nên commit** trong tình huống thất bại.

**B. Lỗi dự kiến bằng kết quả có cấu trúc**

Một function khác có thể trả:

| success | error_code | message | transfer_id |
| --- | --- | --- | --- |
| true | `NULL` | `NULL` | 123 |
| false | `INSUFFICIENT_FUNDS` | Số dư không đủ | `NULL` |

Cách B phù hợp cho workflow cần đánh giá nhiều lỗi dự kiến mà không muốn exception làm transaction failed. Nhưng phải bảo đảm:

- Thất bại không để lại thay đổi DML không mong muốn.
- Mỗi nhánh thành công/thất bại có định nghĩa rõ.
- Caller **bắt buộc kiểm tra `success`**, không bỏ qua.
- Lỗi hạ tầng ngoài dự kiến vẫn được truyền ra đúng cách.
- Mã nghiệp vụ ổn định không phụ thuộc nội dung message.

**Không có một lựa chọn luôn tốt nhất.** Điều cốt lõi là API phải nhất quán giữa routine, caller và mức giao dịch.

## 24. Retry khi gặp deadlock hoặc serialization failure

Một số lỗi không xuất phát từ người dùng nhập sai. Trong các workload đồng thời, DBMS có thể phải hủy một transaction để bảo vệ tính nhất quán.

PostgreSQL có các mã quan trọng:

- `40001`: `serialization_failure`.
- `40P01`: `deadlock_detected`.

Khi gặp chúng, caller có thể **retry toàn transaction** sau khi rollback, nhưng không nên tự retry tùy tiện **một câu UPDATE riêng lẻ** nếu transaction gồm nhiều bước phụ thuộc nhau.

Ví dụ tư duy:

```text
Bắt đầu transaction
      |
      v
Đọc dữ liệu -> kiểm tra -> ghi dữ liệu -> commit
      |
      +-- 40001 / 40P01 --> ROLLBACK
                               |
                               v
                         chờ ngẫu nhiên ngắn
                               |
                               v
                       thử lại TOÀN bộ transaction
                         (có giới hạn số lần)
```

Quy tắc retry an toàn:

1. **Chỉ retry các loại lỗi được xác định có thể retry**, không retry `22023` hay `P3403` mãi mãi.
2. **Rollback** transaction thất bại trước khi thử lại.
3. Có **giới hạn số lần**, backoff và jitter để tránh nhiều client cùng va chạm.
4. Giao dịch phải có cơ chế **idempotency** nếu có nguy cơ caller không biết đã commit hay chưa.
5. Không lặp các **side effect ngoài database** như gửi email, thanh toán qua cổng hoặc gọi webhook mà không có cơ chế chống trùng.
6. Thu thập metric retry/failure để biết hệ thống đang gặp contention thật.

Trong PostgreSQL, retry ở **tầng ứng dụng** thường dễ quản lý hơn cố làm vòng lặp retry trong function, vì function không tự làm chủ transaction của caller.

## 25. MySQL/MariaDB: SIGNAL, HANDLER và RESIGNAL

MySQL/MariaDB dùng cú pháp khác PL/pgSQL.

### 25.1. SIGNAL SQLSTATE

Trong stored procedure:

```sql
-- MySQL/MariaDB, ví dụ chạy trong client hiểu DELIMITER.
DELIMITER //

CREATE PROCEDURE validate_transfer_amount(
    IN p_amount DECIMAL(14,2)
)
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Amount must be positive';
    END IF;
END//

DELIMITER ;
```

`SIGNAL SQLSTATE '45000'` là cách phổ biến phát sinh exception do người dùng định nghĩa trong MySQL/MariaDB. Có thể bổ sung `MYSQL_ERRNO` và các item chẩn đoán khi cần và được phiên bản hỗ trợ.

`DELIMITER` là lệnh của **nhiều công cụ client MySQL**, không phải câu lệnh SQL server chuẩn. Khi chạy qua driver/migration tool, cách gửi nguyên khối procedure phụ thuộc công cụ.

### 25.2. Handler

Cú pháp MySQL/MariaDB cho phép `DECLARE ... HANDLER`:

```sql
DELIMITER //

CREATE PROCEDURE example_handler()
BEGIN
    DECLARE v_duplicate BOOLEAN DEFAULT FALSE;

    DECLARE CONTINUE HANDLER FOR 1062
        SET v_duplicate = TRUE;

    -- Lệnh INSERT có thể gây duplicate-key error ở đây.
    -- Sau handler CONTINUE, code có thể kiểm tra v_duplicate.

    IF v_duplicate THEN
        SELECT 'duplicate detected' AS outcome;
    END IF;
END//

DELIMITER ;
```

Ở đây mã vendor `1062` đại diện cho duplicate key thường gặp trong MySQL. Đây là **mẫu cấu trúc**, không phải procedure thao tác dữ liệu đầy đủ.

Các loại handler chính:

- `CONTINUE`: xử lý condition rồi tiếp tục theo quy tắc của MySQL.
- `EXIT`: rời block nơi handler được khai báo sau khi xử lý.
- `UNDO` xuất hiện trong cú pháp tài liệu nhưng không được hỗ trợ thực tế theo cách người học có thể giả định; không thiết kế dựa trên nó.

**Không dùng CONTINUE cho mọi `SQLEXCEPTION`** chỉ để tiếp tục chạy: sau lỗi ghi dữ liệu, các giả định của bước tiếp theo có thể không còn đúng.

### 25.3. RESIGNAL

Trong một handler, `RESIGNAL` chuyển condition đang được xử lý ra ngoài, đồng thời có thể chỉnh một số thông tin lỗi:

```sql
DELIMITER //

CREATE PROCEDURE example_resignal(
    IN p_amount DECIMAL(14,2)
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        -- Thực hiện cleanup/diagnostics phù hợp nếu cần.
        RESIGNAL;
    END;

    IF p_amount IS NULL OR p_amount <= 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Amount must be positive';
    END IF;
END//

DELIMITER ;
```

Nếu procedure tự mở transaction, handler cần chính sách `ROLLBACK` phù hợp trước khi `RESIGNAL`; không giả định việc catch một lỗi tự rollback **toàn bộ** transaction trên mọi engine/configuration.

## 26. SQL Server: TRY...CATCH và THROW

Trong T-SQL, xử lý lỗi thường dùng `BEGIN TRY ... END TRY` và `BEGIN CATCH ... END CATCH`.

```sql
-- SQL Server; đoạn procedure minh họa.
CREATE OR ALTER PROCEDURE dbo.validate_transfer_amount
    @amount DECIMAL(14,2)
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        IF @amount IS NULL OR @amount <= 0
        BEGIN
            THROW 51001, 'Amount must be positive', 1;
        END;
    END TRY
    BEGIN CATCH
        -- Có thể đọc ERROR_NUMBER(), ERROR_MESSAGE()...
        THROW;
    END CATCH;
END;
```

- `THROW 51001, '...', 1` tạo lỗi với số lỗi do người dùng định nghĩa; trong SQL Server, số dùng ở dạng này phải **từ 50000 trở lên**.
- `THROW;` trong `CATCH` ném lại lỗi hiện tại.
- `ERROR_NUMBER()`, `ERROR_MESSAGE()`, `ERROR_LINE()`, `ERROR_PROCEDURE()`, `ERROR_SEVERITY()` và `ERROR_STATE()` hỗ trợ chẩn đoán trong `CATCH`.

### Transaction và XACT_STATE

Khi procedure tự mở transaction, một mẫu phổ biến:

```sql
CREATE OR ALTER PROCEDURE dbo.example_transaction
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRY
        BEGIN TRANSACTION;

        -- Thực hiện các bước DML có liên quan.
        -- Nếu phát sinh lỗi, chuyển sang CATCH.

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF XACT_STATE() <> 0
            ROLLBACK TRANSACTION;

        THROW;
    END CATCH;
END;
```

`XACT_STATE()` cho biết transaction hiện có đang ở trạng thái có thể commit, không thể commit hay không tồn tại; khi procedure **tự sở hữu transaction**, rollback trong `CATCH` là phương án thường dùng.

**Quan trọng:** Nếu procedure được gọi **bên trong transaction do ứng dụng sở hữu**, không nên sao chép mẫu `BEGIN/COMMIT/ROLLBACK` mà không thiết kế rõ quyền sở hữu transaction và savepoint. `ROLLBACK` có thể ảnh hưởng toàn bộ transaction ngoài.

SQL Server còn có `RAISERROR` trong code legacy; với code mới, thường ưu tiên `THROW` khi phù hợp. `RAISERROR` và `THROW` có khác biệt về cách tương tác với `SET XACT_ABORT` và các thông số lỗi.

## 27. Oracle PL/SQL: EXCEPTION, RAISE và RAISE_APPLICATION_ERROR

Oracle PL/SQL dùng cấu trúc:

```sql
CREATE OR REPLACE PROCEDURE validate_transfer_amount(
    p_amount IN NUMBER
)
AS
BEGIN
    IF p_amount IS NULL OR p_amount <= 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Amount must be positive'
        );
    END IF;

EXCEPTION
    WHEN OTHERS THEN
        -- Khi không có chiến lược xử lý thực sự:
        RAISE;
END;
/
```

Trong Oracle:

- `RAISE_APPLICATION_ERROR` dùng mã lỗi ứng dụng trong khoảng **-20000 đến -20999**.
- `RAISE;` trong exception handler ném lại exception hiện tại.
- `SQLCODE` và `SQLERRM` hỗ trợ lấy mã và thông báo trong exception handler.
- `WHEN OTHERS` bắt các lỗi không được xử lý bởi handler cụ thể hơn; không nên nuốt lỗi mặc định.

Một số exception có tên sẵn:

```sql
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Required account was not found'
        );
    WHEN DUP_VAL_ON_INDEX THEN
        RAISE_APPLICATION_ERROR(
            -20003,
            'Duplicate request'
        );
    WHEN OTHERS THEN
        RAISE;
```

Đây là **đoạn handler minh họa**, chỉ nên chuyển lỗi `DUP_VAL_ON_INDEX` thành “request trùng” nếu đã xác định đúng constraint/statement gây lỗi.

Oracle có đối số thứ ba cho `RAISE_APPLICATION_ERROR` để điều chỉnh việc giữ stack lỗi; cần xem hợp đồng thông báo, bảo mật thông tin và quy tắc rollback của procedure. Không mặc định mọi `WHEN OTHERS` cần gọi `COMMIT` hoặc `ROLLBACK`; caller có thể đang quản lý transaction.

Dấu `/` ở cuối block là quy ước thực thi của một số công cụ Oracle, không phải một phần thân procedure PL/SQL.

## 28. SQLite: không có stored procedure SQL như các hệ server

SQLite không có hệ stored procedure/function SQL theo cùng cách PostgreSQL PL/pgSQL, SQL Server T-SQL, Oracle PL/SQL. Tuy nhiên SQLite hỗ trợ constraint và phát sinh lỗi trong **trigger** bằng hàm `RAISE(...)`.

```sql
-- SQLite:
CREATE TABLE transfers (
    transfer_id INTEGER PRIMARY KEY,
    amount NUMERIC
);

CREATE TRIGGER trg_transfer_positive
BEFORE INSERT ON transfers
WHEN NEW.amount IS NULL OR NEW.amount <= 0
BEGIN
    SELECT RAISE(ABORT, 'Amount must be positive');
END;
```

Khi insert amount không hợp lệ, trigger phát sinh lỗi. SQLite có các dạng `RAISE(ROLLBACK, ...)`, `RAISE(ABORT, ...)`, `RAISE(FAIL, ...)` và `RAISE(IGNORE)` với ý nghĩa khác nhau về xử lý thay đổi và transaction.

Không suy rằng SQLite cho phép dùng `RAISE(...)` trong bất kỳ câu `SELECT` nào hay có `EXCEPTION WHEN` tương tự PL/pgSQL. Khi xây API ứng dụng SQLite, nhiều quy tắc nghiệp vụ thường được kiểm tra ở **application layer** kết hợp constraint và trigger.

## 29. So sánh nhanh các DBMS

| DBMS | Tạo lỗi có chủ đích | Bắt/xử lý lỗi | Ném lại | Lưu ý |
| --- | --- | --- | --- | --- |
| PostgreSQL | `RAISE EXCEPTION` trong PL/pgSQL | `EXCEPTION WHEN ...` | `RAISE;` | SQLSTATE, subtransaction trong EXCEPTION block |
| MySQL/MariaDB | `SIGNAL SQLSTATE` | `DECLARE ... HANDLER` | `RESIGNAL` | `CONTINUE`/`EXIT`, diagnostics area, giao dịch tùy engine |
| SQL Server | `THROW number, message, state` | `TRY...CATCH` | `THROW;` | `XACT_STATE()`, `XACT_ABORT`, error number |
| Oracle | `RAISE` / `RAISE_APPLICATION_ERROR` | `EXCEPTION WHEN ...` | `RAISE;` | Mã ứng dụng `-20000..-20999`, `SQLCODE` |
| SQLite | Constraint; `RAISE(...)` trong trigger | Xử lý qua application/SQLite API | Tùy ứng dụng | Không có PL/pgSQL-like stored procedure SQL tích hợp |

**Không ghép cú pháp giữa các hệ.** Ví dụ `SIGNAL SQLSTATE` không phải cú pháp PL/pgSQL, còn `THROW 51001...` là mẫu SQL Server.

## 30. Tầng Java/JDBC nhận lỗi SQL như thế nào?

Trong Java, lỗi từ SQL thường được biểu diễn qua `SQLException` hoặc subclass tương ứng. Các trường quan trọng:

- `getSQLState()`: SQLSTATE nếu driver cung cấp.
- `getErrorCode()`: mã lỗi riêng của DBMS/driver.
- `getMessage()`: thông điệp có thể thay đổi và có thể chứa chi tiết kỹ thuật.
- `getCause()` / `getNextException()`: thêm ngữ cảnh ngoại lệ.

Ví dụ minh họa:

```java
try {
    // Gọi routine/chạy statement bằng PreparedStatement.
} catch (SQLException e) {
    String sqlState = e.getSQLState();

    if ("22023".equals(sqlState)) {
        // Giá trị đầu vào không hợp lệ.
        // Trả lỗi validation theo hợp đồng API.
    } else if ("P3403".equals(sqlState)) {
        // Nghiệp vụ: số dư không đủ.
    } else if ("23505".equals(sqlState)) {
        // Có vi phạm UNIQUE; kiểm tra constraint/ngữ cảnh.
    } else if ("40001".equals(sqlState)
            || "40P01".equals(sqlState)) {
        // Có thể retry TOÀN transaction nếu an toàn.
    } else {
        // Không nuốt lỗi bất ngờ.
        throw e;
    }
}
```

Đây là **khung điều hướng**, không phải code production hoàn chỉnh: thiếu kết nối, transaction, rollback, số lần retry và mapping HTTP/API. Khi có nhiều DBMS, cần thiết kế adapter/vendor-specific mapping; không giả định mọi driver đều trả đúng SQLSTATE của PostgreSQL.

### Không phân loại bằng message

Tránh:

```java
if (e.getMessage().contains("duplicate")) {
    // ...
}
```

Vì:

- Message có thể được bản địa hóa hoặc đổi giữa phiên bản.
- Nhiều constraint khác nhau cùng báo “duplicate”.
- Nội dung lỗi có thể chứa thông tin nhạy cảm.
- Việc parse chuỗi không ổn định so với mã lỗi.

Ưu tiên **SQLSTATE + vendor code/constraint name khi cần + ngữ cảnh thao tác**.

## 31. Lỗi SQL và mã HTTP/API

Một service có thể dịch lỗi database sang lỗi API. Ví dụ thiết kế **tham khảo**, không phải bảng ánh xạ bắt buộc:

| Trường hợp | Tín hiệu từ DB | Hướng API thường dùng |
| --- | --- | --- |
| Tham số số tiền sai | `22023` | 400 Bad Request hoặc 422 Unprocessable Content theo hợp đồng |
| Tài khoản không tồn tại | `P3401` | 404 Not Found nếu việc tiết lộ sự tồn tại là phù hợp |
| Tài khoản bị khóa | `P3402` | 409 Conflict hoặc mã nghiệp vụ tương ứng |
| Không đủ số dư | `P3403` | 409 Conflict hoặc 422 theo chính sách |
| Request key trùng | `23505` trên constraint request_key | 409, hoặc trả lại kết quả cũ nếu API idempotent đã xác minh |
| Deadlock/serialization | `40P01` / `40001` | Retry nội bộ có giới hạn; nếu hết retry trả lỗi tạm thời thích hợp |
| Lỗi hệ thống bất ngờ | Nhiều loại | 500/503 tùy trường hợp; ghi log an toàn |

Chọn HTTP status phải xét tài nguyên API, an toàn thông tin và hợp đồng public. Không trả stack trace của function, lệnh SQL hay thông tin bảng/constraint nhạy cảm trong response sản xuất.

Đồng thời cần giữ **correlation ID / request ID** để nối log ứng dụng với lỗi cơ sở dữ liệu, mà không phải chép toàn bộ nội dung dữ liệu người dùng vào log.

## 32. Quy tắc đặt mã lỗi nghiệp vụ

Một bộ mã tốt cần **ổn định, dễ phân loại và không xung đột**.

Ví dụ:

| Mã DB lab | Tên ứng dụng | Ý nghĩa |
| --- | --- | --- |
| `P3401` | `ACCOUNT_NOT_FOUND` | Không có account nguồn/đích bắt buộc |
| `P3402` | `ACCOUNT_INACTIVE` | Account không hoạt động |
| `P3403` | `INSUFFICIENT_FUNDS` | Không đủ số dư khả dụng |
| `P3404` | `DUPLICATE_REQUEST` hoặc lỗi nghiệp vụ khác theo hợp đồng | Cần quy ước duy nhất trong dự án |

**Không sử dụng cùng một mã `P3404` cho hai lỗi khác nhau trong cùng hệ thống thực.** Các ví dụ trước dùng `P3404` cho minh họa thao tác rollback và mapping duplicate ở những đoạn độc lập; nếu xây sản phẩm, phải chốt **một ý nghĩa duy nhất cho mỗi mã**, chẳng hạn tách mã kiểm thử khỏi mã sản phẩm.

Một quy ước tốt thường có:

1. Danh sách mã được quản lý tập trung và có version.
2. Mô tả điều kiện phát sinh cụ thể.
3. Thông điệp công khai và thông điệp nội bộ tách riêng.
4. Hướng xử lý phía caller (sửa input, bỏ qua, retry, báo support).
5. Ví dụ test cho mỗi mã.
6. Không tái sử dụng mã cũ với ý nghĩa mới gây vỡ hợp đồng.

Mã lỗi là một phần **giao diện giữa database routine và application**, giống kiểu trả về hay tên tham số.

## 33. Bảo mật: lỗi có thể làm lộ dữ liệu

Exception không chỉ là vấn đề kỹ thuật. Thông báo lỗi có thể tiết lộ:

- Tên bảng/cột/constraint nội bộ.
- Khóa khách hàng hoặc tài khoản tồn tại.
- Dữ liệu có trong ràng buộc bị vi phạm.
- Đường dẫn file, stack function, truy vấn có dữ liệu nhạy cảm.
- Sự khác biệt giữa “người dùng không tồn tại” và “không có quyền xem người dùng” khiến attacker suy ra danh tính.

Vì vậy:

- **Thông báo lỗi hiển thị cho client** nên vừa đủ để họ sửa thao tác hợp lệ.
- **Log nội bộ** chứa thêm SQLSTATE, constraint và correlation ID theo quyền truy cập thích hợp.
- **Không log bí mật** như token, mật khẩu hay thông tin tài chính chi tiết khi không cần.
- **Không dùng lỗi quá chi tiết để tiết lộ sự tồn tại của tài khoản** cho người không có quyền; có thể trả thông báo chung tùy nghiệp vụ.
- **Quyền thực thi function/procedure** phải được giới hạn; một function `SECURITY DEFINER` phát sinh lỗi rất chi tiết có thể trở thành kênh suy luận dữ liệu.

Ngay cả khi function không trả hàng nào, việc nó phản hồi khác nhau cho ID tồn tại và ID không tồn tại có thể tiết lộ thông tin. Thiết kế mã lỗi phải cân bằng tính dễ dùng và phân quyền.

## 34. Kiểm thử xử lý lỗi đúng cách

Một bộ kiểm thử routine không chỉ có “happy path”.

| Test | Đầu vào/tình huống | Kỳ vọng |
| --- | --- | --- |
| Thành công | Hai account hoạt động, số dư đủ | Có transfer, tổng số dư bảo toàn |
| Số âm/0 | `p_amount <= 0` | `22023`, không ghi dữ liệu |
| Tiền nhiều chữ số lẻ | Ví dụ `10.123` | `22023` |
| Tự chuyển | Nguồn bằng đích | `22023` |
| Account thiếu | ID không tồn tại | `P3401` |
| Account bị khóa | ID 103 | `P3402` |
| Không đủ tiền | Amount vượt số dư | `P3403` |
| Request key trùng | Dùng lại `request-001` | `23505` hoặc mã API idempotency được thiết kế |
| Lỗi DML sau bước ghi | Gây constraint failure ở điểm phù hợp | Không giữ cập nhật nửa chừng |
| Hai phiên đồng thời | Chuyển tiền đồng thời/ngược chiều | Số dư không âm, không double-spend; xử lý deadlock/retry đúng |
| Timeout/mất kết nối | Caller không rõ commit | Truy vấn idempotency key trước khi retry có kiểm soát |
| Lỗi không dự kiến | Mất quyền/bảng/loại dữ liệu không hợp lệ | Không bị handler nuốt thành “thành công” |

Trong PostgreSQL, có thể dùng test harness/bộ kiểm thử tích hợp để khẳng định **SQLSTATE** và **trạng thái dữ liệu sau lỗi**, thay vì chỉ nhìn dòng thông báo.

### Một truy vấn kiểm tra tổng số dư

```sql
SELECT SUM(balance) AS combined_balance
FROM sql341.accounts;
```

Trước và sau chuyển tiền **nội bộ** thành công, tổng số dư của ba account lab phải giữ nguyên **1250.00** (khi chưa có nghiệp vụ nạp/rút hoặc phí). Đây là bất biến quan trọng hơn việc chỉ kiểm tra rằng function không ném lỗi.

### Kiểm tra dòng transfer sau yêu cầu thất bại

```sql
SELECT request_key, from_account, to_account, amount
FROM sql341.transfers
ORDER BY transfer_id;
```

Sau các phép thử thất bại chưa được retry thành công, không được xuất hiện transfer mới cho những request key sai đầu vào hoặc không đủ tiền.

## 35. Những lỗi thiết kế phổ biến

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| `WHEN OTHERS THEN NULL` | Nuốt lỗi, caller tưởng thành công | Chỉ bắt lỗi dự kiến; với lỗi khác `RAISE;` |
| Trả `0`/`NULL` cho mọi lỗi | Mất ngữ nghĩa; dễ nhầm với kết quả hợp lệ | Hợp đồng lỗi có mã rõ |
| Dùng `RAISE NOTICE` khi vi phạm quy tắc bắt buộc | Workflow vẫn tiếp tục/commit | `RAISE EXCEPTION` hoặc kết quả thất bại được caller kiểm tra |
| Tạo lỗi mới chung khi bắt mọi exception | Mất mã gốc, khó retry | Chỉ chuyển lỗi đã biết; dùng `RAISE;` cho lỗi khác |
| Parse error message | Dễ vỡ do ngôn ngữ/phiên bản | Dùng SQLSTATE/vendor code |
| Ghi log trong transaction rồi rethrow và nghĩ log đã commit | Log có thể rollback | Monitoring/log ngoài transaction, thiết kế audit rõ |
| Check tồn tại trước INSERT nhưng không có UNIQUE | Race condition khi đồng thời | Constraint + xử lý lỗi xung đột |
| Đọc số dư rồi UPDATE không khóa/điều kiện | Lost update/double spend | Row lock hoặc UPDATE điều kiện phù hợp |
| Retry mọi lỗi | Vòng lặp vô ích, trùng side effect | Chỉ retry loại lỗi đã biết và toàn transaction |
| Retry không giới hạn | Bão retry khi hệ thống quá tải | Backoff, jitter, giới hạn số lần |
| COMMIT trong function hoặc procedure không làm chủ transaction | Vi phạm cú pháp hoặc phá tính nguyên tử workflow | Quy định rõ transaction owner |
| Dùng `EXCEPTION` để xử lý logic bình thường trong loop lớn | Subtransaction overhead, code khó đọc | Kiểm tra điều kiện bình thường bằng IF |
| Trả chi tiết SQL/constraint cho người không đủ quyền | Rò rỉ thông tin | Sanitize response, ghi log có phân quyền |
| Một SQLSTATE tùy chỉnh cho hai nghĩa khác nhau | Caller mapping sai | Registry mã lỗi ổn định |
| Chỉ kiểm tra lỗi có xuất hiện, không kiểm tra dữ liệu | Có thể bỏ sót cập nhật dở dang | Assert trạng thái/bất biến sau lỗi |

## 36. Bài tập thực hành

Các bài dưới đây dựa trên bảng/function `sql341`, trừ khi ghi rõ DBMS khác. Chạy mỗi câu dự kiến ERROR trong một thử nghiệm riêng, hoặc dùng harness có xử lý transaction đúng.

### Bài 1 — Phân loại

Cho bốn tình huống: amount âm, request key trùng, không đủ tiền, deadlock. Hãy xác định tình huống nào cần sửa input, tình huống nào liên quan tính toàn vẹn và tình huống nào có thể retry giao dịch. Không giả định mọi lỗi được retry.

### Bài 2 — Phát sinh lỗi có mã

Viết một `DO` block PostgreSQL nhận biến `v_discount NUMERIC = 150`. Nếu discount không thuộc khoảng 0–100 thì phát sinh SQLSTATE `22023` với `MESSAGE` và `HINT`.

### Bài 3 — Bắt lỗi đặc hiệu

Viết inner block bắt đúng SQLSTATE `P3403` khi gọi `transfer_funds` với amount vượt số dư. In `NOTICE`, sau đó ném lại lỗi gốc. Vì sao không nên thay bằng handler `OTHERS`?

### Bài 4 — Lấy diagnostics

Trong `EXCEPTION` block, dùng `GET STACKED DIAGNOSTICS` lấy `RETURNED_SQLSTATE`, `MESSAGE_TEXT` và `PG_EXCEPTION_CONTEXT`. Phân biệt field nào phù hợp để phân loại tự động và field nào thiên về điều tra.

### Bài 5 — Đọc transaction

Một inner PL/pgSQL block UPDATE balance trừ 20, sau đó `RAISE EXCEPTION` và được handler cùng block bắt. Số dư có bị giảm 20 sau khi outer block tiếp tục không? Giải thích theo subtransaction.

### Bài 6 — SELECT INTO

Trong function, `SELECT balance INTO v_balance FROM accounts WHERE account_id = 999` không trả hàng. `FOUND` là gì? Nếu dùng `INTO STRICT` thì chuyện gì xảy ra?

### Bài 7 — Constraint và race

Hai session cùng kiểm tra chưa có `request_key='abc'`, rồi đều INSERT. Vì sao một `IF NOT EXISTS` đơn thuần không bảo đảm duy nhất? Constraint nào là lớp bảo vệ bắt buộc?

### Bài 8 — Audit lỗi

Một handler ghi `INSERT INTO error_log(...)` rồi `RAISE;` làm transaction ngoài rollback. Dòng log có chắc tồn tại không? Đề xuất vị trí ghi log thất bại bền vững hơn.

### Bài 9 — SQL Server

Viết khung `TRY...CATCH` cho procedure kiểm tra `@amount > 0`, sử dụng `THROW 51001, ...`. Nêu vai trò của `XACT_STATE()` khi procedure có transaction.

### Bài 10 — MySQL/MariaDB

Viết ý tưởng tạo lỗi amount <=0 bằng `SIGNAL SQLSTATE '45000'`. Handler `CONTINUE` khác `EXIT` ở điểm nào? `RESIGNAL` dùng để làm gì?

### Bài 11 — Oracle

Trong Oracle, dùng hàm nào để phát sinh lỗi ứng dụng `-20001`? Khi bắt một lỗi không thể phục hồi, câu nào giúp ném lại exception gốc?

### Bài 12 — SQLite

Vì sao không viết `EXCEPTION WHEN` như PostgreSQL trong một SQLite stored procedure SQL? Cơ chế nào có thể phát sinh lỗi có thông điệp khi insert amount <=0?

### Bài 13 — Retry đúng phạm vi

Một transaction gồm đọc tồn kho, ghi đơn, trừ tồn, ghi thanh toán. Nó gặp `40001` ở cuối. Vì sao không chỉ retry câu UPDATE cuối cùng? Khi retry toàn transaction, cần lưu ý side effect ngoài DB và idempotency như thế nào?

### Bài 14 — Thiết kế mã lỗi

Đề xuất bốn mã và tên nghiệp vụ cho: account không tồn tại, account bị khóa, số dư không đủ, request key trùng. Vì sao không nên dùng một mã cho hai ý nghĩa?

### Bài 15 — Thử nghiệm dữ liệu

Sau khi chuyển 125 từ account 101 sang 102 thành công, hãy viết SQL kiểm tra tổng `balance` của toàn bộ account và tổng số dòng transfer. Khi một lần chuyển tiếp theo thất bại vì không đủ số dư, hai đại lượng đó có thay đổi không?

### Bài 16 — Bảo mật thông báo

Một lỗi trả thẳng “account 101 có số dư 875.00, email chủ tài khoản ...”. Vì sao đây là thông điệp có thể nguy hiểm? Đề xuất cách tách mã lỗi công khai và thông tin chẩn đoán nội bộ.

## 37. Gợi ý đáp án

**Bài 1.** Amount âm: lỗi dữ liệu/đầu vào `22023`. Request key trùng: thường `23505` trong PostgreSQL (cần xem constraint và idempotency). Không đủ tiền: lỗi nghiệp vụ `P3403`. Deadlock: `40P01` có thể retry **toàn giao dịch** khi an toàn.

**Bài 2.**

```sql
DO $$
DECLARE
    v_discount NUMERIC := 150;
BEGIN
    IF v_discount < 0 OR v_discount > 100 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Discount ngoài khoảng hợp lệ',
            HINT = 'Discount phải nằm trong [0, 100].';
    END IF;
END;
$$;
```

**Bài 3.**

```sql
DO $$
BEGIN
    BEGIN
        PERFORM sql341.transfer_funds(
            'exercise-too-large', 101, 102, 999999
        );
    EXCEPTION WHEN SQLSTATE 'P3403' THEN
        RAISE NOTICE 'Yêu cầu vượt số dư';
        RAISE;
    END;
END;
$$;
```

Handler đúng condition không nuốt các lỗi không liên quan như thiếu bảng, mất quyền, deadlock.

**Bài 4.**

```sql
GET STACKED DIAGNOSTICS
    v_state   = RETURNED_SQLSTATE,
    v_message = MESSAGE_TEXT,
    v_context = PG_EXCEPTION_CONTEXT;
```

`v_state` phù hợp cho phân loại ổn định; `v_message` dễ đọc nhưng có thể thay đổi; `v_context` phù hợp log/điều tra có phân quyền.

**Bài 5.** Không. Thay đổi DML của inner block thất bại được rollback khi exception được bắt; outer block có thể tiếp tục với dữ liệu như trước inner block.

**Bài 6.** `FOUND` là `FALSE`; biến nhận `NULL` trong trường hợp thường. Với `INTO STRICT`, PL/pgSQL phát sinh `NO_DATA_FOUND` khi không có hàng.

**Bài 7.** Hai session có thể cùng thấy “không tồn tại” tại hai thời điểm trước khi INSERT. `UNIQUE(request_key)` là lớp bảo vệ chống trùng; code còn phải xử lý lỗi trùng một cách có ý nghĩa.

**Bài 8.** Không. Dòng log ghi cùng transaction có thể rollback. Có thể ghi ở tầng ứng dụng/monitoring hoặc dùng một thiết kế audit độc lập có chủ đích, không dựa vào việc catch rồi INSERT cùng transaction.

**Bài 9.**

```sql
BEGIN TRY
    IF @amount IS NULL OR @amount <= 0
        THROW 51001, 'Amount must be positive', 1;
END TRY
BEGIN CATCH
    -- Nếu procedure tự sở hữu transaction, xem XACT_STATE()
    -- và rollback khi cần, rồi ném lại.
    THROW;
END CATCH;
```

`XACT_STATE()` giúp phân biệt không có transaction và trạng thái transaction có/không còn committable; không tự động quyết định ownership.

**Bài 10.**

```sql
IF p_amount IS NULL OR p_amount <= 0 THEN
    SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Amount must be positive';
END IF;
```

`CONTINUE` xử lý rồi tiếp tục, `EXIT` rời block handler; `RESIGNAL` ném lại hoặc điều chỉnh condition trong handler.

**Bài 11.** `RAISE_APPLICATION_ERROR(-20001, '...')` tạo lỗi ứng dụng. `RAISE;` trong handler ném lại lỗi hiện tại.

**Bài 12.** SQLite không có PL/pgSQL-like stored procedure SQL tích hợp. Có thể dùng constraint hoặc trigger `SELECT RAISE(ABORT, '...')` trong ngữ cảnh trigger.

**Bài 13.** `40001` cho biết transaction bị rollback vì xung đột serialization; cần tính toán lại dựa trên trạng thái mới. Chỉ retry UPDATE cuối có thể làm kết quả lệch. Phải có retry giới hạn, backoff, idempotency và tách side effect ngoài DB.

**Bài 14.** Ví dụ `P3401/ACCOUNT_NOT_FOUND`, `P3402/ACCOUNT_INACTIVE`, `P3403/INSUFFICIENT_FUNDS`, `P3405/DUPLICATE_REQUEST`. Một mã cho hai nghĩa khiến caller xử lý sai.

**Bài 15.**

```sql
SELECT SUM(balance) AS total_balance
FROM sql341.accounts;

SELECT COUNT(*) AS transfer_count
FROM sql341.transfers;
```

Sau lần thành công duy nhất của mục 9, tổng là **1250.00**, số transfer là **1**. Một lần chuyển tiếp bị lỗi vì số dư không đủ không được thêm transfer hoặc đổi tổng số dư.

**Bài 16.** Thông điệp có thể tiết lộ số dư và danh tính cho người gọi chưa đủ quyền. Trả mã `INSUFFICIENT_FUNDS` với lời giải thích được phép công bố; ghi chi tiết kỹ thuật cần thiết vào log có quyền truy cập và retention phù hợp, dùng correlation ID để đối chiếu.

## 38. Dọn dữ liệu thực hành

Sau khi hoàn tất bài và chắc chắn hai bảng/function thuộc **riêng môi trường thử**, có thể xóa schema học tập:

```sql
-- PostgreSQL: chỉ chạy trên database học tập đã xác nhận.
DROP SCHEMA sql341 CASCADE;
```

`CASCADE` xóa các đối tượng bên trong và những đối tượng phụ thuộc theo quy tắc PostgreSQL. Không chạy trên schema chung/sản xuất và không dùng để “ép dọn” khi chưa biết những phụ thuộc có thể bị xóa.

## 39. Tổng kết

**Xử lý ngoại lệ và phát sinh lỗi có ý nghĩa** là một phần của thiết kế API trong stored procedure/function, không phải chỉ là kỹ thuật chống crash. Một routine đáng tin cần xác định rõ **đâu là lỗi dữ liệu**, **đâu là lỗi nghiệp vụ**, **đâu là xung đột đồng thời**, và **đâu là sự cố hệ thống**.

Trong PostgreSQL, người học cần nắm các công cụ **`RAISE EXCEPTION`**, **`ERRCODE`**, **`EXCEPTION WHEN`**, **`RAISE;`**, **`GET STACKED DIAGNOSTICS`**, `FOUND`/`INTO STRICT` và đặc biệt **cơ chế rollback ở block có EXCEPTION**. Khi chuyển hệ, hãy dùng đúng cơ chế **`SIGNAL/RESIGNAL`** của MySQL/MariaDB, **`TRY...CATCH/THROW`** của SQL Server, **`EXCEPTION/RAISE_APPLICATION_ERROR`** của Oracle, hoặc constraint/trigger của SQLite.

Công thức thực hành an toàn là: **ràng buộc dữ liệu ở database, kiểm tra nghiệp vụ rõ ràng, chỉ bắt những lỗi có thể xử lý, ném lại lỗi ngoài dự kiến, quản lý transaction ở đúng tầng, và trả mã lỗi ổn định nhưng không tiết lộ dữ liệu nhạy cảm**. Quan trọng hơn việc “không có exception” là **hệ thống vẫn giữ đúng trạng thái khi exception xảy ra**.
