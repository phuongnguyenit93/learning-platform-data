# SELECT INTO biến và xử lý số hàng không phù hợp

Trong một câu `SELECT` thông thường, cơ sở dữ liệu có thể trả **0 hàng, 1 hàng hoặc nhiều hàng**. Nhưng trong **thủ tục (*procedure*), hàm (*function*) và khối SQL thủ tục**, ta thường muốn đưa kết quả truy vấn vào **một hoặc vài biến** để tiếp tục tính toán: lấy tên khách hàng, kiểm tra trạng thái đơn hàng, đọc hạn mức, tính số dư hoặc quyết định có được phép thực hiện một thao tác.

Ví dụ: một hàm nhận `tenant_id` và `email` rồi cần lấy `user_id`. Ba tình huống có ý nghĩa nghiệp vụ khác nhau:

1. **Không tìm thấy hàng:** người dùng không tồn tại trong phạm vi truy vấn.
2. **Tìm thấy đúng một hàng:** có thể gán các cột vào biến và tiếp tục.
3. **Tìm thấy nhiều hàng:** điều kiện tra cứu **không đủ phân định**, hoặc dữ liệu vi phạm quy tắc duy nhất; lấy đại một hàng có thể trả sai người.

Vấn đề không chỉ là viết `SELECT ... INTO ...` đúng cú pháp. Ta còn phải biết **DBMS xử lý từng số lượng hàng thế nào**, cách nhận biết kết quả rỗng, cách ném/bắt lỗi khi có nhiều hàng, cách phân biệt giá trị `NULL` với không có hàng và khi nào được phép cố ý chọn một hàng bằng `ORDER BY ... LIMIT 1`.

Bài học thuộc chương **Thủ tục và hàm** của Database SQL. Ví dụ chính dùng **PostgreSQL PL/pgSQL**, sau đó so sánh với **Oracle PL/SQL, SQL Server T-SQL, MySQL stored routines** và trường hợp SQLite không có thủ tục SQL lưu trữ tương tự. Mỗi phương ngữ có hành vi khác nhau; đặc biệt, **không được chuyển nguyên một đoạn `SELECT INTO` từ DBMS này sang DBMS khác mà giả định ý nghĩa giống nhau**.

## 1. Từ kết quả dạng bảng sang biến trong chương trình SQL

Câu SQL thông thường:

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'an@example.com';
```

trả một tập hàng. Trong ngôn ngữ thủ tục, ta có thể cần hai biến, ví dụ:

```text
v_user_id   = 101
v_user_name = 'An'
```

Sau đó chương trình có thể dùng chúng trong `IF`, `RETURN`, phép tính hoặc câu lệnh SQL tiếp theo.

Ở PostgreSQL PL/pgSQL, hình thức thường gặp là:

```sql
SELECT expression_1, expression_2
INTO variable_1, variable_2
FROM some_table
WHERE condition;
```

**Quan trọng:** Đây là cú pháp **gán kết quả vào biến trong PL/pgSQL**. Trong SQL chạy trực tiếp ngoài khối thủ tục, PostgreSQL và SQL Server còn có cú pháp `SELECT ... INTO new_table` với nghĩa **tạo bảng mới từ kết quả**. Hai nghĩa này phải được phân biệt; phần 12 trình bày chi tiết.

### 1.1. “Đúng một giá trị” và “đúng một hàng” không giống nhau

Một câu:

```sql
SELECT display_name
FROM app_users_demo
WHERE tenant_id = 1;
```

trả **một cột** nhưng có thể trả **nhiều hàng**. Việc chỉ chọn một cột không biến nó thành truy vấn một hàng.

Ngược lại:

```sql
SELECT user_id, display_name, status
FROM app_users_demo
WHERE user_id = 101;
```

chọn **ba cột**, nhưng vì `user_id` là khóa chính nên truy vấn trả **tối đa một hàng**.

Vì thế, khi nói “`SELECT INTO` phải có kết quả phù hợp”, ta cần xét **số hàng** mà câu truy vấn tạo ra, đồng thời xét **số và kiểu của các cột/biến đích**.

### 1.2. Ba kết quả và hai mục tiêu nghiệp vụ

| Số hàng nguồn | Nếu nghiệp vụ yêu cầu đúng một người | Nếu nghiệp vụ cho phép lấy người mới nhất |
|---:|---|---|
| 0 | Báo không tìm thấy hoặc trả trạng thái riêng | Báo không tìm thấy |
| 1 | Gán biến và xử lý | Gán biến và xử lý |
| Trên 1 | **Báo dữ liệu mơ hồ/trùng** | Có thể chọn một hàng theo thứ tự xác định |

**Không chọn `LIMIT 1` chỉ để che lỗi trùng.** Nếu quy tắc nói mỗi tenant/email phải duy nhất, hai hàng khớp là một **vi phạm cần phát hiện**. Nếu quy tắc nói “chọn bản ghi tạo gần nhất”, nhiều hàng là bình thường và cần một chiến lược `ORDER BY` rõ ràng.

## 2. Bộ dữ liệu mẫu dùng xuyên suốt

Ta tạo bảng `app_users_demo` trong **database PostgreSQL thực hành riêng**. Bảng cố tình có email trùng để minh họa nhánh “quá nhiều hàng” và có một hàng tên `NULL` để phân biệt “không có hàng” với “hàng có giá trị thiếu”.

### 2.1. Tạo bảng

```sql
CREATE TABLE app_users_demo (
    user_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT,
    status TEXT NOT NULL
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')),
    created_at TIMESTAMP NOT NULL,
    points INTEGER NOT NULL CHECK (points >= 0)
);
```

Ý nghĩa các cột:

- `user_id` là **khóa chính**, duy nhất trên toàn bảng.
- `tenant_id` phân chia người dùng theo tổ chức/khách thuê.
- `email` là một thuộc tính tìm kiếm nhưng **chưa có ràng buộc duy nhất** trong bộ dữ liệu thực hành.
- `display_name` được phép `NULL`: một hàng có thể tồn tại dù tên hiển thị chưa được nhập.
- `status` và `points` phục vụ các ví dụ điều kiện và tính toán.
- `created_at` giúp chọn bản ghi mới nhất một cách có định nghĩa.

### 2.2. Nạp dữ liệu

```sql
INSERT INTO app_users_demo
    (user_id, tenant_id, email, display_name, status, created_at, points)
VALUES
    (101, 1, 'an@example.com',    'An',   'ACTIVE',
     TIMESTAMP '2025-05-01 08:00:00', 120),
    (102, 1, 'binh@example.com',  'Binh', 'ACTIVE',
     TIMESTAMP '2025-05-02 09:00:00', 50),
    (103, 1, 'chung@example.com', 'Chi',  'ACTIVE',
     TIMESTAMP '2025-05-03 10:00:00', 75),
    (104, 1, 'chung@example.com', 'Dung', 'SUSPENDED',
     TIMESTAMP '2025-05-04 11:00:00', 30),
    (105, 2, 'an@example.com',    'An T2','ACTIVE',
     TIMESTAMP '2025-05-05 12:00:00', 200),
    (106, 1, 'em@example.com',    NULL,   'INACTIVE',
     TIMESTAMP '2025-05-06 13:00:00', 0),
    (107, 1, 'giang@example.com', 'Giang','ACTIVE',
     TIMESTAMP '2025-05-07 14:00:00', 45);
```

Tập ban đầu có **7 người dùng**:

| user_id | tenant_id | email | display_name | status | points |
|---:|---:|---|---|---|---:|
| 101 | 1 | an@example.com | An | ACTIVE | 120 |
| 102 | 1 | binh@example.com | Binh | ACTIVE | 50 |
| 103 | 1 | chung@example.com | Chi | ACTIVE | 75 |
| 104 | 1 | chung@example.com | Dung | SUSPENDED | 30 |
| 105 | 2 | an@example.com | An T2 | ACTIVE | 200 |
| 106 | 1 | em@example.com | `NULL` | INACTIVE | 0 |
| 107 | 1 | giang@example.com | Giang | ACTIVE | 45 |

### 2.3. Ba truy vấn dùng để kiểm tra hành vi

**Đúng một hàng:**

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'binh@example.com';
-- (102, 'Binh')
```

**Không có hàng:**

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';
-- 0 hàng
```

**Có hai hàng:**

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com'
ORDER BY user_id;
-- (103, 'Chi'), (104, 'Dung')
```

Một phép tra cứu khác:

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'em@example.com';
-- (106, NULL): có một hàng, nhưng tên là NULL
```

Khi nhìn kết quả, hãy phân biệt rõ **0 hàng** với **1 hàng chứa `NULL`**. Đây là một trong những lý do không nên chỉ nhìn giá trị cuối cùng của một biến để đoán truy vấn có tìm thấy hàng hay không.

## 3. PostgreSQL PL/pgSQL: SELECT INTO không dùng STRICT

Trong PL/pgSQL, ta khai báo biến trong phần `DECLARE` và gán bằng `SELECT ... INTO` ở phần `BEGIN ... END`.

### 3.1. Gán một hoặc nhiều cột vào biến

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'binh@example.com';

    RAISE NOTICE 'id=%, name=%', v_user_id, v_name;
END
$$;
```

Với bộ dữ liệu mẫu, thông báo tương đương:

```text
NOTICE: id=102, name=Binh
```

Giải thích:

1. `v_user_id` và `v_name` là các **biến của khối PL/pgSQL**, không phải tên cột bảng.
2. `SELECT u.user_id, u.display_name` trả hai biểu thức theo thứ tự.
3. `INTO v_user_id, v_name` gán biểu thức thứ nhất cho biến thứ nhất, biểu thức thứ hai cho biến thứ hai.
4. `WHERE` hạn chế các hàng nguồn.
5. `RAISE NOTICE` chỉ in thông báo minh họa; không phải cách tạo kết quả trả về của một hàm.

**Chú ý:** mã này chạy trong PostgreSQL PL/pgSQL `DO` block. Nếu nhập riêng phần `SELECT ... INTO v_user_id` như một câu SQL độc lập ngoài khối, PostgreSQL không có biến `v_user_id` của PL/pgSQL để gán theo ngữ nghĩa này.

### 3.2. Khi tìm thấy đúng một hàng

Với `SELECT INTO` **không có `STRICT`**, nếu truy vấn trả ít nhất một hàng, PostgreSQL gán các giá trị của **hàng được lấy đầu tiên** vào biến. Khi truy vấn có đúng một hàng, đó là kết quả tự nhiên.

Ví dụ theo khóa chính:

```sql
DO $$
DECLARE
    v_points INTEGER;
BEGIN
    SELECT u.points
    INTO v_points
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE 'points=%', v_points;
END
$$;
-- points=120
```

Vì `user_id` là khóa chính, truy vấn trả tối đa một hàng. Tuy nhiên, nếu user_id không tồn tại thì trường hợp **0 hàng** vẫn cần được xử lý; khóa chính chỉ bảo đảm *tối đa một*, không bảo đảm *luôn có một*.

### 3.3. Khi không tìm thấy hàng: biến được gán NULL

Trong PL/pgSQL PostgreSQL, `SELECT ... INTO` **không STRICT** khi không có hàng phù hợp sẽ gán **`NULL` cho các biến đích**.

```sql
DO $$
DECLARE
    v_user_id INTEGER := -1;
    v_name TEXT := 'Gia tri cu';
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com';

    RAISE NOTICE 'id=%, name=%', v_user_id, v_name;
END
$$;
```

Kết quả hai biến là `NULL`, **không giữ** các giá trị khởi tạo `-1` và `'Gia tri cu'`.

Điểm này khác đáng kể với **SQL Server `SELECT @variable = ... FROM ...`** và **MySQL `SELECT ... INTO variable`**, nơi không có hàng thường để nguyên giá trị biến cũ. Khi chuyển code, không được giữ giả định từ PostgreSQL.

### 3.4. Khi tìm thấy nhiều hàng: âm thầm chọn một hàng

Đối với `SELECT INTO` không `STRICT`, PostgreSQL PL/pgSQL **không tự báo lỗi** chỉ vì truy vấn trả nhiều hàng. Nó lấy hàng đầu tiên mà cách thực thi truy vấn cung cấp, rồi gán vào biến:

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'chung@example.com';

    RAISE NOTICE 'selected id=%, name=%', v_user_id, v_name;
END
$$;
```

Hai hàng 103 và 104 cùng khớp. **Không được bảo đảm** câu này chọn 103 hay 104 nếu không có `ORDER BY` xác định. Kết quả có thể phụ thuộc kế hoạch thực thi, chỉ mục, thống kê, cách lưu trữ hoặc thời điểm dữ liệu thay đổi.

Nếu một tính năng tìm hồ sơ khách bắt buộc có **đúng một người**, việc âm thầm chọn một trong hai là lỗi thiết kế. Khi đó cần `INTO STRICT` hoặc kiểm tra tính duy nhất bằng cơ chế phù hợp.

### 3.5. Tóm tắt hành vi PL/pgSQL không STRICT

| Số hàng truy vấn nguồn | Gán vào biến | Có lỗi tự động không? |
|---:|---|---|
| 0 | Các biến đích thành `NULL` | Không |
| 1 | Giá trị của hàng duy nhất | Không |
| 2 hoặc nhiều hơn | Giá trị của một hàng đầu tiên theo cách thực thi | **Không** |

Vì vậy `SELECT INTO` không `STRICT` phù hợp khi **chấp nhận 0 hàng** và đã biết truy vấn trả tối đa một hàng, hoặc khi cố ý chọn một hàng theo thứ tự rõ ràng. Nó **không** là cơ chế tự phát hiện dữ liệu trùng.

## 4. FOUND: phân biệt “không có hàng” với “giá trị NULL”

Trong PL/pgSQL, biến trạng thái đặc biệt **`FOUND`** cho biết một số câu lệnh trước đó có tìm thấy/tác động hàng hay không. Đối với `SELECT INTO` không `STRICT`:

- `FOUND = TRUE` khi truy vấn trả **ít nhất một hàng**.
- `FOUND = FALSE` khi truy vấn trả **không hàng nào**.

### 4.1. Kiểm tra ngay sau SELECT INTO

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
    v_found BOOLEAN;
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com';

    v_found := FOUND;

    IF NOT v_found THEN
        RAISE NOTICE 'Khong tim thay user';
    ELSE
        RAISE NOTICE 'Tim thay user id=%, name=%', v_user_id, v_name;
    END IF;
END
$$;
```

Ở ví dụ này thông báo là “Khong tim thay user”. Biến `v_found` giữ kết quả kiểm tra tại thời điểm ngay sau lệnh tra cứu.

### 4.2. NULL ở cột không đồng nghĩa FOUND = FALSE

Xét hàng user 106 có `display_name = NULL`:

```sql
DO $$
DECLARE
    v_name TEXT;
    v_found BOOLEAN;
BEGIN
    SELECT u.display_name
    INTO v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'em@example.com';

    v_found := FOUND;

    RAISE NOTICE 'found=%, name=%', v_found, v_name;
END
$$;
```

Kết quả có **`found=TRUE`** nhưng `name=NULL`. Điều đó hoàn toàn đúng: **hàng 106 tồn tại**, chỉ có cột tên đang thiếu giá trị.

Do vậy cách kiểm tra này là sai nếu muốn biết có người dùng hay không:

```sql
IF v_name IS NULL THEN
    -- Sai: không phân biệt không có hàng với hàng có tên NULL.
END IF;
```

Hãy dùng `FOUND` đã ghi nhận ngay sau truy vấn, hoặc tra khóa chính không `NULL`, hoặc `SELECT INTO STRICT` nếu yêu cầu đúng một hàng.

### 4.3. FOUND có thể bị lệnh khác thay đổi

`FOUND` là trạng thái của **khối PL/pgSQL hiện tại**, không phải một biến lịch sử bất biến gắn với câu SELECT đầu tiên. Nhiều câu lệnh như `PERFORM`, `SELECT INTO` và các lệnh DML có thể cập nhật nó.

Ví dụ không nên làm:

```sql
SELECT u.display_name INTO v_name
FROM app_users_demo AS u
WHERE u.user_id = 999;

PERFORM 1
FROM app_users_demo AS u
WHERE u.user_id = 101;

IF FOUND THEN
    -- FOUND giờ phản ánh PERFORM, không còn phản ánh SELECT đầu tiên.
END IF;
```

Nếu kết quả SELECT đầu quan trọng, hãy lưu:

```sql
SELECT ... INTO v_name FROM ... WHERE ...;
v_lookup_found := FOUND;
```

**ngay sau câu lệnh** và dùng `v_lookup_found` cho các quyết định về sau.

### 4.4. FOUND không phát hiện được nhiều hàng

Trên bộ dữ liệu mẫu:

```sql
SELECT u.user_id INTO v_user_id
FROM app_users_demo AS u
WHERE u.tenant_id = 1
  AND u.email = 'chung@example.com';
```

`FOUND` vẫn là **TRUE**, dù có **hai hàng** khớp. Nó chỉ phân biệt **có ít nhất một** hay **không có** hàng trong tình huống này, không phải một phép kiểm tra “đúng một hàng”.

## 5. SELECT INTO STRICT: yêu cầu chính xác một hàng

PostgreSQL PL/pgSQL cho phép thêm `STRICT` vào sau `INTO`:

```sql
SELECT expression_1, expression_2
INTO STRICT variable_1, variable_2
FROM some_table
WHERE condition;
```

Ý nghĩa: truy vấn **phải trả đúng một hàng**.

- **0 hàng:** phát sinh exception `NO_DATA_FOUND`.
- **1 hàng:** gán biến thành công.
- **Nhiều hơn 1 hàng:** phát sinh exception `TOO_MANY_ROWS`.

### 5.1. Tra cứu đúng một hàng

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    SELECT u.user_id, u.display_name
    INTO STRICT v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'binh@example.com';

    RAISE NOTICE 'Tim thay duy nhat id=%, name=%',
        v_user_id, v_name;
END
$$;
```

Kết quả là **102/Binh**; không có lỗi vì đúng một hàng.

### 5.2. Không có hàng: NO_DATA_FOUND

```sql
DO $$
DECLARE
    v_user_id INTEGER;
BEGIN
    SELECT u.user_id
    INTO STRICT v_user_id
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com';
END
$$;
```

Nếu không bắt exception, PostgreSQL báo lỗi `NO_DATA_FOUND` với SQLSTATE thường là **`P0002`**. Không có việc “gán `NULL` rồi chạy tiếp bình thường” như biến thể không `STRICT`.

### 5.3. Nhiều hàng: TOO_MANY_ROWS

```sql
DO $$
DECLARE
    v_user_id INTEGER;
BEGIN
    SELECT u.user_id
    INTO STRICT v_user_id
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'chung@example.com';
END
$$;
```

Vì có **hai user 103 và 104**, lệnh phát sinh `TOO_MANY_ROWS`, SQLSTATE thường là **`P0003`** trong PL/pgSQL.

Đây là tín hiệu quan trọng: nếu email đáng lẽ là khóa duy nhất trong một tenant, hệ thống cần xử lý **vấn đề dữ liệu hoặc thiết kế khóa**, thay vì lấy ngẫu nhiên một người.

### 5.4. Dữ liệu NULL vẫn có thể là một hàng hợp lệ

`STRICT` kiểm tra **số hàng**, không yêu cầu mọi giá trị cột đều khác `NULL`.

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    SELECT u.user_id, u.display_name
    INTO STRICT v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.user_id = 106;

    RAISE NOTICE 'id=%, name=%', v_user_id, v_name;
END
$$;
```

Lệnh **thành công** với `v_user_id = 106` và `v_name = NULL`. Không có `NO_DATA_FOUND` vì người dùng 106 tồn tại.

Nếu tên là thông tin **bắt buộc theo nghiệp vụ**, phải kiểm tra riêng `v_name IS NULL` hoặc đặt ràng buộc `NOT NULL` trên bảng phù hợp. Không coi `STRICT` là “mọi dữ liệu đều hợp lệ”.

### 5.5. Bảng đối chiếu STRICT và không STRICT

| Số hàng nguồn | `INTO` không `STRICT` (PostgreSQL) | `INTO STRICT` (PostgreSQL) |
|---:|---|---|
| 0 | Gán `NULL`; `FOUND = FALSE` | `NO_DATA_FOUND` |
| 1 | Gán giá trị; `FOUND = TRUE` | Gán giá trị thành công |
| 2+ | Gán một hàng đầu tiên; `FOUND = TRUE` | `TOO_MANY_ROWS` |

Với nghiệp vụ **phải có duy nhất một bản ghi**, `INTO STRICT` thường thể hiện ý định rõ hơn vì nó không âm thầm bỏ qua trường hợp trùng.

## 6. Bắt và xử lý ngoại lệ NO_DATA_FOUND, TOO_MANY_ROWS

Trong PL/pgSQL, khối `BEGIN ... EXCEPTION ... END` cho phép xử lý những lỗi cụ thể.

### 6.1. Xử lý hai lỗi khác nhau

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_email TEXT := 'chung@example.com';
BEGIN
    BEGIN
        SELECT u.user_id
        INTO STRICT v_user_id
        FROM app_users_demo AS u
        WHERE u.tenant_id = 1
          AND u.email = v_email;

        RAISE NOTICE 'Tim thay user id=%', v_user_id;

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE NOTICE 'Khong tim thay email=%', v_email;

        WHEN TOO_MANY_ROWS THEN
            RAISE NOTICE 'Email=% khop nhieu user', v_email;
    END;
END
$$;
```

Với `chung@example.com`, nhánh **`TOO_MANY_ROWS`** được xử lý. Nếu đổi thành `khongco@example.com`, nhánh **`NO_DATA_FOUND`** được xử lý. Nếu đổi thành `binh@example.com`, truy vấn thành công.

### 6.2. Không nhất thiết phải “nuốt” mọi ngoại lệ

Đoạn trên chỉ in thông báo, phù hợp minh họa. Trong ứng dụng thực:

- `NO_DATA_FOUND` có thể chuyển thành trạng thái “không tìm thấy” được tài liệu hóa, hoặc là một lỗi nghiệp vụ.
- `TOO_MANY_ROWS` thường phản ánh vi phạm tính duy nhất, cần báo lỗi và đưa vào quy trình kiểm tra dữ liệu.
- Những lỗi khác như sai kiểu, mất kết nối, ràng buộc hay phân quyền không nên bị đánh đồng với “không tìm thấy”.

Nếu muốn giữ nguyên lỗi cho tầng gọi xử lý:

```sql
EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        RAISE;
```

`RAISE;` không có đối số trong exception handler sẽ **ném lại lỗi hiện tại**. Đừng dùng `WHEN OTHERS THEN RETURN NULL` để che mọi lỗi hệ thống thành “không tồn tại”.

### 6.3. Khối EXCEPTION có chi phí và ngữ nghĩa giao dịch

Trong PostgreSQL PL/pgSQL, khối có `EXCEPTION` dùng cơ chế tương tự **subtransaction** để hoàn tác các thay đổi dữ liệu trong phần khối bị lỗi khi bắt exception, trong khi trạng thái biến PL/pgSQL có quy tắc riêng. Không nên đặt hàng nghìn khối exception không cần thiết chỉ để thay một phép kiểm tra đơn giản.

Việc bắt lỗi `NO_DATA_FOUND` bằng `STRICT` có thể rất rõ về ngữ nghĩa, nhưng nếu “không tìm thấy” là trường hợp thường xuyên và **không phải lỗi**, mẫu `INTO` không STRICT + `FOUND` có thể phù hợp hơn.

### 6.4. Biến sau khi quá nhiều hàng không nên được dùng làm kết quả hợp lệ

Khi `STRICT` gây `TOO_MANY_ROWS`, câu SELECT **không hoàn tất phép tra cứu hợp lệ**. Không nên tiếp tục sử dụng các biến đích như thể chúng chứa một hàng xác nhận đúng. Trong nhánh xử lý lỗi, hãy đặt trạng thái rõ ràng, ném lỗi hoặc quyết định khôi phục, thay vì dựa trên giá trị biến còn lại.

## 7. Đóng gói phép tra cứu trong hàm PostgreSQL

Một hàm nhận tham số thay vì hard-code email sẽ gần với ứng dụng thực hơn.

### 7.1. Hàm yêu cầu duy nhất một người

```sql
CREATE OR REPLACE FUNCTION get_user_id_strict(
    p_tenant_id INTEGER,
    p_email TEXT
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id INTEGER;
BEGIN
    SELECT u.user_id
    INTO STRICT v_user_id
    FROM app_users_demo AS u
    WHERE u.tenant_id = p_tenant_id
      AND u.email = p_email;

    RETURN v_user_id;
END;
$$;
```

Gọi hàm:

```sql
SELECT get_user_id_strict(1, 'binh@example.com');
-- 102
```

Các lời gọi:

```sql
SELECT get_user_id_strict(1, 'khongco@example.com');
-- Lỗi NO_DATA_FOUND.

SELECT get_user_id_strict(1, 'chung@example.com');
-- Lỗi TOO_MANY_ROWS.
```

Đây là hợp đồng có chủ đích: **hàm chỉ thành công khi tìm thấy chính xác một user** theo hai tham số.

### 7.2. Hàm trả trạng thái thay vì ném lỗi

Nếu tầng gọi cần xử lý “không tìm thấy” hoặc “trùng email” như các **kết quả nghiệp vụ**, có thể trả một cấu trúc:

```sql
CREATE OR REPLACE FUNCTION find_user_with_status(
    p_tenant_id INTEGER,
    p_email TEXT
)
RETURNS TABLE (
    result_status TEXT,
    found_user_id INTEGER,
    found_name TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    BEGIN
        SELECT u.user_id, u.display_name
        INTO STRICT v_user_id, v_name
        FROM app_users_demo AS u
        WHERE u.tenant_id = p_tenant_id
          AND u.email = p_email;

        result_status := 'FOUND';
        found_user_id := v_user_id;
        found_name := v_name;

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            result_status := 'NOT_FOUND';
            found_user_id := NULL;
            found_name := NULL;

        WHEN TOO_MANY_ROWS THEN
            result_status := 'AMBIGUOUS';
            found_user_id := NULL;
            found_name := NULL;
    END;

    RETURN NEXT;
END;
$$;
```

Thử ba tình huống:

```sql
SELECT * FROM find_user_with_status(1, 'binh@example.com');
-- FOUND | 102 | Binh

SELECT * FROM find_user_with_status(1, 'khongco@example.com');
-- NOT_FOUND | NULL | NULL

SELECT * FROM find_user_with_status(1, 'chung@example.com');
-- AMBIGUOUS | NULL | NULL
```

Và với hàng có tên thiếu:

```sql
SELECT * FROM find_user_with_status(1, 'em@example.com');
-- FOUND | 106 | NULL
```

**Vì sao trả nhiều trường?** Vì một giá trị `NULL` duy nhất không nói rõ nó đại diện “không có user”, “user tồn tại nhưng tên `NULL`” hay “truy vấn bị trùng”. Cấu trúc có `result_status` và `found_user_id` thể hiện các trường hợp tách biệt.

**Chú ý:** Hàm trên chỉ chuyển **hai exception cụ thể** thành trạng thái. Những lỗi khác vẫn được báo theo cơ chế thông thường. Trong hệ thống thật, phải xác định liệu `TOO_MANY_ROWS` có nên được trả dạng trạng thái hay phải làm transaction thất bại để không tiếp tục xử lý dữ liệu mơ hồ.

### 7.3. Quy ước đặt tên giúp tránh nhập nhằng cột và biến

Nên dùng:

- `p_tenant_id`, `p_email` cho **tham số đầu vào**.
- `v_user_id`, `v_name` cho **biến cục bộ**.
- `u.user_id`, `u.email` cho **cột bảng có alias**.

Tránh viết câu điều kiện mơ hồ:

```sql
WHERE user_id = user_id
```

Tùy ngữ cảnh, nó có thể vô tình so cột với chính nó, hoặc gây lỗi tên mơ hồ với biến PL/pgSQL. Đặc biệt với dữ liệu có `NULL`, so cột với chính nó cũng không biểu đạt điều kiện tìm đúng một user.

Đặt tên và dùng alias tường minh giúp người đọc biết **giá trị ở vế trái/vế phải đến từ đâu**.

## 8. Nếu cố ý lấy một hàng trong nhiều hàng: ORDER BY và LIMIT 1

Không phải truy vấn trả nhiều hàng lúc nào cũng là lỗi. Ví dụ người dùng hỏi:

> “Trong tenant 1, lấy tài khoản có email chung@example.com được tạo **gần đây nhất**.”

Khi đó, hai hàng 103 và 104 là dữ liệu cho phép lựa chọn. Quy tắc nghiệp vụ đã chỉ rõ **mới nhất**.

### 8.1. Chọn theo thứ tự xác định

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_name TEXT;
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'chung@example.com'
    ORDER BY u.created_at DESC, u.user_id DESC
    LIMIT 1;

    RAISE NOTICE 'latest id=%, name=%', v_user_id, v_name;
END
$$;
```

Kết quả: **104 / Dung**, vì `created_at` của 104 mới hơn 103.

`user_id DESC` là **khóa phân định** nếu hai hàng có cùng `created_at`. Trong ví dụ `user_id` là khóa chính duy nhất, nên thứ tự được xác định khi dữ liệu không đổi.

### 8.2. LIMIT 1 không thay thế yêu cầu tính duy nhất

Hai ý định khác nhau:

| Ý định | Cách viết hợp lý | Khi có hai hàng |
|---|---|---|
| “Phải có đúng một người với email này” | `SELECT ... INTO STRICT` **không `LIMIT 1`** | Báo `TOO_MANY_ROWS` |
| “Lấy người được tạo gần đây nhất với email này” | `ORDER BY created_at DESC, user_id DESC LIMIT 1` | Chọn 104 |

Nếu viết:

```sql
SELECT u.user_id
INTO STRICT v_user_id
FROM app_users_demo AS u
WHERE u.tenant_id = 1
  AND u.email = 'chung@example.com'
ORDER BY u.created_at DESC, u.user_id DESC
LIMIT 1;
```

thì `STRICT` chỉ thấy **tối đa một hàng sau `LIMIT 1`**. Nó không còn phát hiện rằng điều kiện gốc khớp hai hàng. Khi đã giới hạn thành một hàng, `STRICT` chủ yếu còn có tác dụng báo `NO_DATA_FOUND` nếu không có ứng viên.

Đây là lựa chọn đúng **nếu nghiệp vụ muốn latest**, nhưng sai nếu người viết muốn kiểm tra email **không trùng**.

### 8.3. ORDER BY không có khóa phân định có thể vẫn không ổn định

Nếu hai hàng có cùng thời điểm `created_at`, lệnh:

```sql
ORDER BY created_at DESC
LIMIT 1
```

không bảo đảm chọn cùng ID qua các lần chạy. Thêm một cột phân định duy nhất như `user_id DESC` khi có quy tắc chấp nhận được.

**Lưu ý:** Thứ tự chọn chỉ bảo đảm về logic `ORDER BY` trên dữ liệu được truy vấn; trong môi trường cập nhật đồng thời, hàng “mới nhất” vẫn có thể thay đổi giữa các transaction.

### 8.4. Khi không tìm thấy “latest” thì sao?

Ngay cả với `ORDER BY ... LIMIT 1`, query có thể trả **0 hàng**. Với PL/pgSQL:

```sql
SELECT ...
INTO v_result
FROM ...
WHERE ...
ORDER BY ...
LIMIT 1;

IF NOT FOUND THEN
    -- Không có ứng viên nào.
END IF;
```

Nếu chọn `INTO STRICT`, không tìm thấy sẽ gây `NO_DATA_FOUND`. Hãy chọn cách diễn đạt nhất quán với hợp đồng của hàm.

## 9. COUNT(*), MAX(), SUM() và bẫy “luôn có một hàng”

Nhiều người muốn kiểm tra số hàng trước khi `SELECT INTO` nên viết một câu `COUNT(*)`. Tuy nhiên, các hàm tổng hợp có ngữ nghĩa riêng mà người viết hàm cần hiểu.

### 9.1. COUNT(*) không GROUP BY trả đúng một hàng

```sql
SELECT COUNT(*)
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';
```

Kết quả là **một hàng có giá trị 0**, không phải 0 hàng.

Trong PL/pgSQL:

```sql
DO $$
DECLARE
    v_count BIGINT;
    v_found BOOLEAN;
BEGIN
    SELECT COUNT(*)
    INTO STRICT v_count
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com';

    v_found := FOUND;

    RAISE NOTICE 'count=%, found=%', v_count, v_found;
END
$$;
```

Kết quả: **`count = 0`, `FOUND = TRUE`**. Không có `NO_DATA_FOUND` vì truy vấn tổng hợp **trả một hàng**.

**Kết luận:** với `COUNT(*)` không có `GROUP BY`, phải kiểm tra **`v_count = 0`**, không dùng `NOT FOUND` để kết luận có hàng nguồn hay không.

### 9.2. MAX() và SUM() trên tập rỗng

```sql
SELECT MAX(points), SUM(points)
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';
```

Truy vấn cũng trả **một hàng**, nhưng các giá trị `MAX(points)` và `SUM(points)` là **`NULL`** trên tập rỗng. Chúng không tạo exception `NO_DATA_FOUND` chỉ vì không có hàng nguồn.

Không nên hiểu:

```sql
SELECT COALESCE(SUM(points), 0)
```

là một cách phát hiện user không tồn tại. Nó chủ yếu quyết định giá trị tổng khi tập không có hàng; muốn kiểm tra có user hay không cần điều kiện/đếm riêng.

### 9.3. GROUP BY có thể thay đổi số hàng tổng hợp

```sql
SELECT status, COUNT(*)
FROM app_users_demo
WHERE tenant_id = 1
GROUP BY status;
```

Với dữ liệu mẫu, câu này có **ba hàng**: `ACTIVE`, `INACTIVE`, `SUSPENDED`. `SELECT INTO STRICT` hai biến sẽ gây `TOO_MANY_ROWS` nếu không giới hạn/nhóm khác.

Nếu `WHERE` lọc ra tập rỗng:

```sql
SELECT status, COUNT(*)
FROM app_users_demo
WHERE tenant_id = 999
GROUP BY status;
```

kết quả là **0 hàng**, không phải một hàng có `count=0` cho mỗi trạng thái. Khi `GROUP BY`, chỉ các nhóm thực sự tồn tại trong dữ liệu mới được tạo (trừ các dạng tổng hợp nâng cao như grouping sets).

### 9.4. Dùng COUNT để phân loại 0/1/nhiều hàng

Nếu chỉ cần biết có bao nhiêu user khớp:

```sql
SELECT COUNT(*)
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';
-- 2
```

Trong thủ tục:

```sql
SELECT COUNT(*) INTO v_count
FROM app_users_demo AS u
WHERE u.tenant_id = p_tenant_id
  AND u.email = p_email;

IF v_count = 0 THEN
    -- Không có.
ELSIF v_count = 1 THEN
    -- Có đúng một tại thời điểm đếm.
ELSE
    -- Có nhiều.
END IF;
```

Đây là mẫu rõ ràng khi chỉ cần **phân loại số lượng**. Nhưng nếu sau đó lại chạy một `SELECT INTO` riêng để lấy dữ liệu, hai câu đọc **có thể quan sát trạng thái khác nhau** trong môi trường đồng thời, tùy isolation level. Với yêu cầu “đúng một hàng” và cần ngay dữ liệu, `SELECT INTO STRICT` có thể gọn hơn, hoặc database nên có ràng buộc duy nhất.

### 9.5. COUNT(DISTINCT ...) không giải quyết mọi vấn đề trùng

`COUNT(DISTINCT email)` đếm email phân biệt, không phải số người khớp. Với `chung@example.com` có hai user nhưng chỉ **một email phân biệt**. Nếu dùng `COUNT(DISTINCT email) = 1` để kết luận “đúng một người”, chương trình sẽ sai.

Phải đếm **hàng ở mức chi tiết cần nhận diện**, thường là `COUNT(*)` sau điều kiện chính xác, hoặc dùng khóa duy nhất/ràng buộc nghiệp vụ.

## 10. Gán nhiều cột, biến bản ghi và thứ tự đích

### 10.1. Số biểu thức phải phù hợp số biến

```sql
DO $$
DECLARE
    v_user_id INTEGER;
    v_status TEXT;
    v_points INTEGER;
BEGIN
    SELECT u.user_id, u.status, u.points
    INTO STRICT v_user_id, v_status, v_points
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE 'id=%, status=%, points=%',
        v_user_id, v_status, v_points;
END
$$;
```

Kết quả: **101, ACTIVE, 120**.

Khi dùng danh sách biến:

- Biểu thức SELECT thứ nhất đi vào biến thứ nhất.
- Biểu thức thứ hai vào biến thứ hai.
- Các kiểu dữ liệu phải tương thích; chuyển kiểu có thể thất bại hoặc biến đổi giá trị theo quy tắc DBMS.

Đừng viết nhầm:

```sql
SELECT u.status, u.points
INTO v_points, v_status
FROM ...
```

vì thứ tự biến/giá trị bị đảo. Hãy đối chiếu tên cột và tên biến theo đúng vị trí.

### 10.2. %TYPE để bám theo kiểu cột

PL/pgSQL hỗ trợ khai báo biến dựa trên kiểu cột:

```sql
DO $$
DECLARE
    v_user_id app_users_demo.user_id%TYPE;
    v_points app_users_demo.points%TYPE;
BEGIN
    SELECT u.user_id, u.points
    INTO STRICT v_user_id, v_points
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE 'id=%, points=%', v_user_id, v_points;
END
$$;
```

Khi kiểu cột thay đổi, `%TYPE` giúp biến theo cùng kiểu cột mà không phải ghi lặp tên kiểu thủ công. Tuy nhiên, thay đổi schema vẫn có thể yêu cầu cập nhật logic hàm, đặc biệt nếu biểu thức hoặc điều kiện không còn tương thích.

### 10.3. %ROWTYPE để lấy cả bản ghi

Khi cần nhiều cột của **một hàng**, có thể khai báo biến kiểu bản ghi bảng:

```sql
DO $$
DECLARE
    v_user app_users_demo%ROWTYPE;
BEGIN
    SELECT u.*
    INTO STRICT v_user
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE 'name=%, points=%',
        v_user.display_name, v_user.points;
END
$$;
```

`%ROWTYPE` giúp biểu diễn một hàng theo cấu trúc bảng. Nhưng `SELECT *` tạo phụ thuộc vào schema; nếu mục tiêu chỉ lấy `user_id` và `status`, khai báo hai biến/record phù hợp có thể rõ và ít ràng buộc hơn.

### 10.4. RECORD linh hoạt

PL/pgSQL có kiểu `RECORD` cho kết quả có cấu trúc được xác định lúc chạy truy vấn:

```sql
DO $$
DECLARE
    v_row RECORD;
BEGIN
    SELECT u.user_id, u.display_name, u.points
    INTO STRICT v_row
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE 'id=%, points=%', v_row.user_id, v_row.points;
END
$$;
```

Biến `RECORD` hữu ích khi query trả các cột khác với toàn bộ bảng. Nhưng nếu nhiều truy vấn gán những cấu trúc khác nhau cho cùng một record, truy cập một trường không còn tồn tại có thể gây lỗi lúc chạy. Cần giữ cấu trúc đầu ra nhất quán.

## 11. PERFORM, EXISTS và GET DIAGNOSTICS: khi không cần gán dữ liệu

Không phải mọi kiểm tra cần `SELECT INTO`.

### 11.1. PERFORM khi chỉ cần biết có hàng hay không

Trong PL/pgSQL, `PERFORM` thực hiện một truy vấn nhưng **bỏ kết quả**, đồng thời thiết lập `FOUND` phù hợp.

```sql
DO $$
DECLARE
    v_exists BOOLEAN;
BEGIN
    PERFORM 1
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'binh@example.com';

    v_exists := FOUND;

    IF v_exists THEN
        RAISE NOTICE 'Co it nhat mot user';
    ELSE
        RAISE NOTICE 'Khong co user';
    END IF;
END
$$;
```

`PERFORM 1 FROM ...` không gán `1` vào một biến. Nó giúp kiểm tra **tồn tại** mà không cần trả một cột thực tế.

Với email trùng, `FOUND` vẫn là `TRUE`; `PERFORM` không bảo đảm duy nhất.

### 11.2. SELECT EXISTS INTO một biến boolean

Có thể viết:

```sql
SELECT EXISTS (
    SELECT 1
    FROM app_users_demo AS u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com'
)
INTO v_exists;
```

`EXISTS(...)` là một **biểu thức boolean**, nên câu `SELECT` ngoài trả **một hàng** chứa `FALSE` khi không có user. `FOUND` của câu `SELECT INTO` ngoài vì vậy là `TRUE`, dù `v_exists = FALSE`.

Đây là sự khác nhau giữa:

- **`FOUND`:** câu SELECT ngoài có trả hàng không?
- **`v_exists`:** truy vấn con bên trong có ít nhất một hàng khớp không?

Đừng dùng `FOUND` để suy ra giá trị `EXISTS` của truy vấn con tổng hợp.

### 11.3. GET DIAGNOSTICS ROW_COUNT

PL/pgSQL có:

```sql
GET DIAGNOSTICS v_row_count = ROW_COUNT;
```

để đọc số hàng xử lý bởi **câu SQL gần nhất có thông tin số hàng**, rất hữu ích sau `UPDATE`, `DELETE`, `INSERT`.

Ví dụ:

```sql
DO $$
DECLARE
    v_changed BIGINT;
BEGIN
    UPDATE app_users_demo AS u
    SET points = points + 1
    WHERE u.tenant_id = 999;

    GET DIAGNOSTICS v_changed = ROW_COUNT;
    RAISE NOTICE 'updated=%', v_changed;
END
$$;
-- updated=0
```

Ví dụ này chạy DML nhưng không sửa hàng nào vì tenant 999 không tồn tại. Với câu DML thay đổi thật, nếu thực hành trong transaction muốn khôi phục, hãy kiểm soát transaction trước khi chạy.

**Không dùng `ROW_COUNT` của `SELECT INTO` không STRICT để suy ra có bao nhiêu hàng nguồn đã khớp trước khi chọn một hàng.** Truy vấn loại đó chủ đích chỉ đưa tối đa một hàng vào biến; nếu muốn phát hiện trùng, dùng `STRICT` hoặc truy vấn đếm đúng phạm vi.

Ngoài ra, cũng như `FOUND`, giá trị diagnostic liên quan **câu lệnh gần nhất**, nên phải đọc kịp thời trước khi chạy câu SQL khác.

## 12. Cùng từ khóa SELECT INTO nhưng hai ý nghĩa khác nhau

Đây là một trong những nhầm lẫn phổ biến nhất khi học từ ví dụ PostgreSQL, SQL Server hoặc tài liệu nhiều ngôn ngữ SQL.

### 12.1. PostgreSQL PL/pgSQL: INTO biến

Bên trong `DO`/function:

```sql
DO $$
DECLARE
    v_name TEXT;
BEGIN
    SELECT u.display_name INTO v_name
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE '%', v_name;
END
$$;
```

`v_name` là **biến PL/pgSQL** nhận giá trị `'An'`. Không có bảng mới nào được tạo.

### 12.2. PostgreSQL SQL thông thường: SELECT INTO bảng mới

Khi chạy SQL ngoài PL/pgSQL:

```sql
SELECT user_id, tenant_id, email
INTO app_users_copy_demo
FROM app_users_demo
WHERE tenant_id = 1;
```

đây là hình thức `SELECT INTO` mang nghĩa **tạo bảng mới** `app_users_copy_demo` với dữ liệu truy vấn, **không phải gán vào biến**. PostgreSQL thường khuyến nghị cú pháp tường minh hơn:

```sql
CREATE TABLE app_users_copy_demo AS
SELECT user_id, tenant_id, email
FROM app_users_demo
WHERE tenant_id = 1;
```

Hai câu trên là **hai cách minh họa cho một việc tạo bảng**; chỉ chạy **một** trong hai vì dùng cùng tên bảng đích. Bảng tạo bằng `CREATE TABLE AS` không tự sao chép đầy đủ mọi constraint, index, trigger và thuộc tính của bảng nguồn.

**Chú ý:** Nếu bạn đang viết PL/pgSQL, muốn tạo bảng từ truy vấn thì dùng `CREATE TABLE ... AS SELECT ...`, không nhầm `SELECT ... INTO variable` thành thao tác DDL.

### 12.3. SQL Server: SELECT INTO bảng khác với SELECT @var = ...

Trong SQL Server T-SQL:

```sql
-- Tạo bảng mới:
SELECT user_id, tenant_id, email
INTO dbo.app_users_copy_demo
FROM dbo.app_users_demo;
```

khác với:

```sql
-- Gán biến:
DECLARE @user_id INT;
SELECT @user_id = user_id
FROM dbo.app_users_demo
WHERE user_id = 101;
```

SQL Server không dùng `SELECT user_id INTO @user_id FROM ...` theo đúng ngữ nghĩa gán biến của PL/pgSQL/Oracle/MySQL stored routine.

### 12.4. Bảng đối chiếu nhanh

| Môi trường | Mẫu | Mục đích |
|---|---|---|
| PostgreSQL PL/pgSQL | `SELECT col INTO v_col FROM t` | Gán biến |
| PostgreSQL SQL bên ngoài PL/pgSQL | `SELECT col INTO new_table FROM t` | Tạo bảng mới |
| PostgreSQL SQL hiện đại | `CREATE TABLE new_table AS SELECT ...` | Tạo bảng mới rõ ràng |
| SQL Server T-SQL | `SELECT @v = col FROM t` | Gán biến |
| SQL Server T-SQL | `SELECT col INTO new_table FROM t` | Tạo bảng mới |
| Oracle PL/SQL | `SELECT col INTO v_col FROM t` | Gán biến, yêu cầu đúng một hàng |
| MySQL stored routine | `SELECT col INTO v_col FROM t` | Gán biến, số hàng phải xử lý đúng |

Đọc tài liệu về `SELECT INTO` cần xác định **ngữ cảnh ngôn ngữ và DBMS** trước khi kết luận cú pháp đang “đọc một hàng vào biến”.

## 13. Oracle PL/SQL: SELECT INTO yêu cầu đúng một hàng

Trong **Oracle PL/SQL**, `SELECT ... INTO ... FROM ...` thông thường mang ngữ nghĩa **exact fetch**: phải có **chính xác một hàng**.

Khác với PostgreSQL không STRICT, Oracle **không âm thầm lấy một hàng đầu tiên khi truy vấn khớp nhiều hàng**.

### 13.1. Ví dụ Oracle tương đương

Giả sử đã tạo bảng `app_users_demo` có cùng dữ liệu nghiệp vụ trên Oracle với kiểu cột tương ứng:

```sql
DECLARE
    v_user_id app_users_demo.user_id%TYPE;
    v_name app_users_demo.display_name%TYPE;
BEGIN
    SELECT u.user_id, u.display_name
    INTO v_user_id, v_name
    FROM app_users_demo u
    WHERE u.tenant_id = 1
      AND u.email = 'binh@example.com';

    DBMS_OUTPUT.PUT_LINE(
        'id=' || v_user_id || ', name=' || v_name
    );
END;
/
```

Với `binh@example.com`, có đúng một hàng 102/Binh nên thành công.

**Không chạy nguyên DDL PostgreSQL ở mục 2 trên Oracle rồi nghĩ cú pháp chắc chắn tương đương**: phần này giả định schema tương ứng đã được tạo bằng kiểu và quy tắc Oracle.

### 13.2. Không có hàng: NO_DATA_FOUND

```sql
DECLARE
    v_user_id NUMBER;
BEGIN
    SELECT u.user_id
    INTO v_user_id
    FROM app_users_demo u
    WHERE u.tenant_id = 1
      AND u.email = 'khongco@example.com';

EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Khong tim thay user');
END;
/
```

Trong Oracle PL/SQL, `NO_DATA_FOUND` được phát sinh khi một câu `SELECT INTO` exact fetch không trả hàng.

### 13.3. Nhiều hàng: TOO_MANY_ROWS

```sql
DECLARE
    v_user_id NUMBER;
BEGIN
    SELECT u.user_id
    INTO v_user_id
    FROM app_users_demo u
    WHERE u.tenant_id = 1
      AND u.email = 'chung@example.com';

EXCEPTION
    WHEN TOO_MANY_ROWS THEN
        DBMS_OUTPUT.PUT_LINE('Email khop nhieu user');
END;
/
```

Hai hàng 103/104 tạo `TOO_MANY_ROWS`. Khi lỗi này xảy ra, không nên dùng biến đích như một kết quả đã được xác nhận hợp lệ.

### 13.4. SELECT INTO và COUNT trên Oracle

```sql
SELECT COUNT(*)
INTO v_count
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';
```

trả một hàng có `v_count = 0`; **không phát sinh NO_DATA_FOUND**. Điều này giống nguyên tắc tổng hợp của PostgreSQL, dù cú pháp thủ tục và cơ chế bắt lỗi có khác.

### 13.5. Muốn chọn một hàng trong Oracle

Nếu ý định là “lấy user mới nhất” thay vì “yêu cầu duy nhất”, có thể dùng một truy vấn có `ORDER BY` và giới hạn hàng theo cú pháp Oracle phiên bản hỗ trợ. Ví dụ trên Oracle 12c+:

```sql
SELECT u.user_id, u.display_name
INTO v_user_id, v_name
FROM app_users_demo u
WHERE u.tenant_id = 1
  AND u.email = 'chung@example.com'
ORDER BY u.created_at DESC, u.user_id DESC
FETCH FIRST 1 ROW ONLY;
```

Với tập mẫu, chọn **104/Dung**. Việc giới hạn một hàng là **thay đổi hợp đồng nghiệp vụ**, không phải chữa lỗi `TOO_MANY_ROWS` nếu email phải duy nhất.

## 14. SQL Server T-SQL: gán biến bằng SELECT @variable =

SQL Server không dùng cú pháp `INTO v_variable` cho biến cục bộ như PL/pgSQL. Thay vào đó:

```sql
DECLARE @user_id INT;
DECLARE @user_name NVARCHAR(200);

SELECT
    @user_id = user_id,
    @user_name = display_name
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'binh@example.com';

SELECT @user_id AS user_id, @user_name AS user_name;
```

Với dữ liệu mẫu tương đương, gán **102/Binh**.

### 14.1. Không có hàng: biến giữ giá trị cũ

Trong T-SQL, `SELECT @v = column FROM table WHERE ...` khi **không trả hàng** thường **không thực hiện phép gán** cho biến. Biến giữ giá trị đang có.

```sql
DECLARE @user_id INT = -1;

SELECT @user_id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';

SELECT @user_id AS user_id;
-- -1
```

Đây là điểm **khác PostgreSQL PL/pgSQL không STRICT**, nơi không có hàng làm biến đích thành `NULL`.

Không dùng giá trị còn lại của biến như bằng chứng chắc chắn có hàng. Ví dụ nếu biến khởi tạo bằng một ID cũ, một phép tra cứu mới không có kết quả có thể khiến chương trình **vô tình tiếp tục dùng ID cũ**.

### 14.2. Nhiều hàng: gán nhiều lần và giữ một giá trị cuối

```sql
DECLARE @user_id INT = -1;

SELECT @user_id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';

SELECT @user_id AS selected_user_id;
```

Hai hàng 103/104 cùng khớp. Kiểu gán này có thể gán biến nhiều lần trong quá trình xử lý, và giá trị cuối phụ thuộc cách các hàng được xử lý; **không được coi có thứ tự chắc chắn** nếu không có quy tắc chọn phù hợp. SQL Server **không mặc định ném `TOO_MANY_ROWS`** với dạng `SELECT @v = col FROM ...`.

Vì thế, không dùng mẫu này để thực thi quy tắc “phải đúng một user” mà không kiểm tra số hàng.

### 14.3. @@ROWCOUNT ngay sau phép gán SELECT

SQL Server có `@@ROWCOUNT` để lấy số hàng được câu lệnh trước xử lý:

```sql
DECLARE @user_id INT = -1;
DECLARE @matched_rows INT;

SELECT @user_id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';

SET @matched_rows = @@ROWCOUNT;

SELECT
    @matched_rows AS matched_rows,
    @user_id AS assigned_id;
```

Với dữ liệu tương đương, `@matched_rows = 2`. Giá trị `@user_id` không nên được dùng để quyết định người nào đúng.

**Đọc `@@ROWCOUNT` ngay sau câu SELECT quan tâm.** Nhiều câu lệnh T-SQL tiếp theo thay đổi giá trị trạng thái; nếu đọc muộn sau một câu SELECT/SET khác, số hàng sẽ không còn phản ánh câu tra cứu ban đầu.

### 14.4. SET @v = (scalar subquery) có ngữ nghĩa khác

Trong T-SQL:

```sql
DECLARE @user_id INT = -1;

SET @user_id = (
    SELECT user_id
    FROM dbo.app_users_demo
    WHERE tenant_id = 1
      AND email = 'binh@example.com'
);
```

Truy vấn con phải được dùng như một **scalar subquery**:

- **Một hàng, một cột:** gán giá trị.
- **Không hàng:** biểu thức scalar subquery cho `NULL`, nên `@user_id` thành `NULL`.
- **Nhiều hàng:** SQL Server báo lỗi kiểu **“Subquery returned more than 1 value”**, không âm thầm chọn hàng cuối như `SELECT @v = col FROM ...`.

So sánh:

| T-SQL | 0 hàng | Nhiều hàng |
|---|---|---|
| `SELECT @v = col FROM t WHERE ...` | Giữ giá trị cũ | Có thể gán nhiều lần; giá trị cuối không đáng tin nếu không có thứ tự/chọn xác định |
| `SET @v = (SELECT col FROM t WHERE ...)` | Gán `NULL` | Báo lỗi scalar subquery |

Chọn cú pháp phải dựa trên **hợp đồng số hàng**, không chỉ thói quen dùng `SET` hay `SELECT`.

### 14.5. TOP (1) + ORDER BY khi cố ý chọn mới nhất

```sql
DECLARE @user_id INT;

SELECT TOP (1)
    @user_id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com'
ORDER BY created_at DESC, user_id DESC;

SELECT @user_id AS latest_user_id;
-- 104 trên dữ liệu mẫu tương đương
```

**`TOP (1)` không phải kiểm tra duy nhất**; nó chỉ áp dụng quy tắc lấy một hàng. Tương tự `LIMIT 1` trong PostgreSQL, cần thứ tự xác định để lấy “mới nhất”.

### 14.6. Một mẫu xử lý 0/1/nhiều hàng rõ ràng

Trong procedure T-SQL, có thể phân loại bằng `@@ROWCOUNT` ngay sau SELECT. Ví dụ khái niệm:

```sql
DECLARE @user_id INT = NULL;
DECLARE @row_count INT;

SELECT @user_id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';

SET @row_count = @@ROWCOUNT;

IF @row_count = 0
BEGIN
    PRINT 'NOT_FOUND';
END
ELSE IF @row_count > 1
BEGIN
    PRINT 'AMBIGUOUS';
END
ELSE
BEGIN
    PRINT 'FOUND';
END;
```

Đây là mẫu **diễn giải số hàng**; nó không thay thế ràng buộc duy nhất khi nhiều transaction cùng thay đổi dữ liệu. Nếu `@row_count > 1`, không sử dụng `@user_id` đã được gán như một kết quả được phép tiếp tục.

## 15. MySQL stored routines: SELECT ... INTO biến và số hàng

MySQL có cú pháp `SELECT ... INTO variable` trong stored procedure/function và cũng có thể gán **session variables** như `@name`. Bài này tập trung vào **biến cục bộ trong stored procedure**.

### 15.1. Gán biến trong stored procedure

Giả sử có bảng tương đương `app_users_demo` trên MySQL với cùng dữ liệu:

```sql
-- MySQL: ví dụ trong một stored procedure.
SELECT u.display_name
INTO v_name
FROM app_users_demo AS u
WHERE u.tenant_id = p_tenant_id
  AND u.email = p_email;
```

Trong MySQL, truy vấn dạng này phải phù hợp **một hàng nguồn**:

| Số hàng | Hành vi điển hình MySQL SELECT ... INTO |
|---:|---|
| 0 | Cảnh báo/điều kiện **No data** (thường mã 1329, SQLSTATE `02000`); **biến đích giữ giá trị cũ** |
| 1 | Gán giá trị vào biến |
| 2+ | Lỗi **Result consisted of more than one row** (thường mã 1172) |

Đặc biệt, trường hợp **0 hàng giữ nguyên biến** khác PostgreSQL PL/pgSQL không STRICT. Nếu biến đã có giá trị từ một lần tra cứu trước, cần tránh để chương trình vô tình dùng giá trị cũ.

### 15.2. Procedure xử lý NOT FOUND

Trong trình khách MySQL hỗ trợ `DELIMITER`, có thể tạo procedure:

```sql
DELIMITER //

CREATE PROCEDURE find_user_name_mysql(
    IN p_tenant_id INT,
    IN p_email VARCHAR(255),
    OUT p_name VARCHAR(255),
    OUT p_status VARCHAR(20)
)
BEGIN
    DECLARE v_no_data BOOLEAN DEFAULT FALSE;
    DECLARE CONTINUE HANDLER FOR NOT FOUND
        SET v_no_data = TRUE;

    SET p_name = NULL;
    SET p_status = 'FOUND';

    SELECT u.display_name
    INTO p_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = p_tenant_id
      AND u.email = p_email;

    IF v_no_data THEN
        SET p_status = 'NOT_FOUND';
    END IF;
END//

DELIMITER ;
```

`DELIMITER` là lệnh hỗ trợ của nhiều MySQL client để phân tách câu `CREATE PROCEDURE` có dấu `;` bên trong, **không phải từ khóa SQL tiêu chuẩn** gửi nguyên vào mọi API.

Khi không có hàng, handler `NOT FOUND` ghi `v_no_data = TRUE`; vì đã đặt `p_name = NULL` trước, kết quả không còn giữ một tên cũ. Khi tìm thấy đúng một hàng, `p_status` giữ `FOUND` và `p_name` nhận tên (có thể là `NULL` từ cột nguồn).

Nếu nhiều hàng khớp, MySQL báo lỗi nhiều hàng. Handler `NOT FOUND` **không xử lý thay** lỗi đó, nên procedure không im lặng chọn một hàng.

### 15.3. Xử lý TOO_MANY_ROWS trong MySQL

Nếu nghiệp vụ cần biến lỗi nhiều hàng thành một trạng thái riêng, có thể dùng handler cho mã lỗi tương ứng, nhưng phải thiết kế **phạm vi handler, transaction và thông báo** rõ ràng. Ví dụ:

```sql
-- Đặt trong phần khai báo của một BEGIN ... END MySQL.
DECLARE v_too_many BOOLEAN DEFAULT FALSE;
DECLARE CONTINUE HANDLER FOR 1172
    SET v_too_many = TRUE;
```

Sau câu `SELECT ... INTO`, cần đọc `v_too_many` và **không tin nội dung biến đích** nếu xảy ra lỗi. Trong hệ thống thật, đôi khi cách an toàn hơn là để lỗi thoát ra và dừng thao tác nghiệp vụ.

**Không tự biến mọi lỗi thành một giá trị `NULL`**. Lỗi 1172 có thể cho biết khóa truy vấn không duy nhất và cần được sửa ở dữ liệu hoặc schema.

### 15.4. Session variables khác biến cục bộ

MySQL có:

```sql
SELECT display_name
INTO @latest_name
FROM app_users_demo
WHERE user_id = 101;
```

`@latest_name` là **session variable**, có vòng đời và phạm vi khác với biến khai báo `DECLARE v_name ...` trong stored routine. Không dựa vào session variable cho từng request khi dùng connection pool mà không kiểm soát trạng thái session và các lần tái sử dụng kết nối.

### 15.5. LIMIT 1 và ORDER BY trong MySQL

Khi nghiệp vụ muốn bản ghi mới nhất:

```sql
SELECT u.user_id, u.display_name
INTO v_user_id, v_name
FROM app_users_demo AS u
WHERE u.tenant_id = 1
  AND u.email = 'chung@example.com'
ORDER BY u.created_at DESC, u.user_id DESC
LIMIT 1;
```

Kết quả chọn **104/Dung** trên dữ liệu tương đương. Một lần nữa, `LIMIT 1` là **chủ ý chọn một trong nhiều**, không phải công cụ kiểm tra rằng email duy nhất.

## 16. SQLite và lớp ứng dụng: khi không có stored procedure tương tự

SQLite không cung cấp ngôn ngữ stored procedure trong database với `DECLARE`, `BEGIN ... END`, `SELECT INTO local_variable` theo mô hình PL/pgSQL/PLSQL/T-SQL. Vì thế không nên dịch:

```sql
SELECT display_name INTO v_name
FROM app_users_demo
WHERE ...;
```

trực tiếp sang SQLite rồi kỳ vọng có biến thủ tục được gán.

### 16.1. Trả tập kết quả cho ứng dụng

Trên SQLite, ứng dụng thường chạy:

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = ?
  AND email = ?;
```

sau đó đọc kết quả:

- Không có dòng nào: xử lý `NOT_FOUND`.
- Có một dòng: đọc giá trị các cột (kể cả `NULL`).
- Có dòng thứ hai: xử lý `AMBIGUOUS` nếu yêu cầu duy nhất.

Đây là đúng cùng bài toán về **số hàng**, chỉ chuyển vị trí kiểm tra sang **lớp ứng dụng/driver**.

### 16.2. Một truy vấn giới hạn hai hàng giúp kiểm tra duy nhất

Nếu mục tiêu là biết **0, 1 hay ít nhất 2 hàng**, nhiều ngôn ngữ ứng dụng có thể dùng:

```sql
SELECT user_id, display_name
FROM app_users_demo
WHERE tenant_id = ?
  AND email = ?
LIMIT 2;
```

và đọc tối đa hai hàng:

| Số hàng trả về | Kết luận |
|---:|---|
| 0 | Không có |
| 1 | Đúng một theo snapshot/điều kiện truy vấn |
| 2 | Có ít nhất hai; không cần đọc hết tập để biết vi phạm |

Mục tiêu của `LIMIT 2` ở đây **khác `LIMIT 1`**. Nó giữ được khả năng **phát hiện trùng** nhưng không phải đếm tất cả bản sao. Dù vậy, nếu nghiệp vụ cần con số trùng chính xác hoặc báo cáo toàn bộ hàng lỗi, phải dùng truy vấn phù hợp.

## 17. JDBC: kiểm tra số hàng khi nhận ResultSet

Một chương trình Java gọi SQL trực tiếp cũng phải có hợp đồng về cardinality, kể cả khi không dùng stored function. Ví dụ JDBC dùng `PreparedStatement`:

```java
String sql = """
    SELECT user_id, display_name
    FROM app_users_demo
    WHERE tenant_id = ?
      AND email = ?
    ORDER BY user_id
    LIMIT 2
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, tenantId);
    ps.setString(2, email);

    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new NoSuchElementException("User not found");
        }

        int userId = rs.getInt("user_id");
        String displayName = rs.getString("display_name");

        if (rs.next()) {
            throw new IllegalStateException("Multiple matching users");
        }

        // Tại đây đúng một hàng được tìm thấy.
        // displayName vẫn có thể là null vì cột cho phép SQL NULL.
    }
}
```

Đây là **đoạn minh họa bên trong một phương thức có các biến `connection`, `tenantId` và `email` đã được định nghĩa**. Các kiểu `PreparedStatement`, `ResultSet`, `NoSuchElementException` cần được import phù hợp; code không phải lớp Java hoàn chỉnh.

Giải thích:

1. `rs.next()` đầu trả `false` nếu kết quả **0 hàng**.
2. Nếu có hàng đầu, đọc ID và tên.
3. `rs.next()` lần hai giúp phát hiện **ít nhất hai hàng**.
4. Nếu không có hàng thứ hai, một hàng được xác nhận theo kết quả truy vấn.
5. `getString("display_name")` có thể trả **`null`** vì cột SQL `NULL`, nhưng điều đó khác với việc `rs.next()` đầu trả `false`.

**Phân biệt:** Thư viện ORM hay repository có thể cung cấp API `findOne`, `single`, `optional`; hành vi khi nhiều hàng, không hàng hoặc `NULL` khác nhau theo thư viện. Không giả định chúng tương đương `SELECT INTO STRICT` của PostgreSQL mà không đọc hợp đồng API.

## 18. Tính duy nhất nên được bảo vệ bằng ràng buộc

Nếu quy tắc nghiệp vụ nói:

> “Trong mỗi tenant, email đã chuẩn hóa xác định duy nhất một user.”

thì việc chỉ viết `SELECT INTO STRICT` trong hàm là **kiểm tra khi đọc**, không ngăn hệ thống **ghi trùng**.

### 18.1. UNIQUE trên cặp khóa

Với dữ liệu đã sạch, một thiết kế tương ứng có thể là:

```sql
ALTER TABLE app_users_demo
ADD CONSTRAINT uq_users_tenant_email
UNIQUE (tenant_id, email);
```

Nhưng với **dữ liệu mẫu hiện tại**, lệnh này **không thể thành công**, vì hai hàng `103` và `104` cùng cặp `(1, 'chung@example.com')`. Ta cố ý giữ sự trùng này để thực hành.

Trước khi thêm constraint vào dữ liệu thực:

1. Xác nhận email có thật sự là khóa duy nhất không.
2. Xác định quy tắc chuẩn hóa chữ hoa/khoảng trắng/collation.
3. Phân loại bản ghi trùng để hợp nhất hoặc sửa qua quy trình nghiệp vụ.
4. Kiểm tra các khóa ngoại và hệ thống tham chiếu.
5. Tạo constraint phù hợp, xác nhận cơ chế ghi đồng thời.

Không tự xóa hàng 104 chỉ để `UNIQUE` chạy được nếu chưa biết nó có phải một tài khoản hợp lệ khác hay không.

### 18.2. Email không phải lúc nào cũng là định danh hoàn hảo

Email có thể:

- Được thay đổi.
- Được dùng chung.
- Có quy tắc chuẩn hóa phụ thuộc hệ thống.
- Có hoặc không phân biệt chữ hoa trong ứng dụng.
- Được xác minh hay chưa xác minh.

Nếu hệ thống đã có `user_id` là khóa chính, nhiều API nên tìm theo **ID** thay vì email, khi định danh thật sự đã biết. Email có thể là tiêu chí tìm kiếm trả nhiều ứng viên, không nhất thiết một khóa duy nhất.

### 18.3. Không trộn tenant

Trong bộ dữ liệu có:

```text
tenant 1, an@example.com -> user 101
tenant 2, an@example.com -> user 105
```

Lệnh:

```sql
WHERE email = 'an@example.com'
```

trả **hai hàng** dù email này không trùng **trong cùng tenant**. Nếu quy tắc định danh là **(tenant_id, email)**, truy vấn phải dùng **cả hai thành phần**.

Đối với ứng dụng đa tenant, quên điều kiện tenant không chỉ gây lỗi `TOO_MANY_ROWS` mà còn có thể dẫn đến **lộ dữ liệu của tổ chức khác**. Cần áp dụng quyền truy cập, kiểm tra tenant từ ngữ cảnh đã xác thực và ràng buộc dữ liệu tương ứng.

## 19. Ảnh hưởng của dữ liệu đồng thời và giao dịch

Một phép `SELECT INTO STRICT` chỉ kiểm tra số hàng **theo truy vấn và trạng thái dữ liệu mà nó quan sát tại thời điểm thực thi**. Nó không phải một lời hứa rằng số hàng đó sẽ giữ nguyên mãi mãi.

### 19.1. Hai SELECT riêng có thể thấy hai trạng thái

Giả sử transaction A làm:

```sql
SELECT COUNT(*)
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'binh@example.com';
-- 1
```

Giữa phép đếm và phép tra cứu tiếp theo, transaction B có thể chèn một hàng trùng email nếu database chưa có constraint bảo vệ. Ở mức cô lập như `READ COMMITTED` của PostgreSQL, hai câu SELECT có thể thấy **snapshot khác nhau**.

Do đó:

```text
COUNT(*) = 1
  -> chờ
  -> SELECT INTO
```

không tự bảo đảm câu SELECT sau vẫn chỉ có một hàng. Với yêu cầu đúng một hàng, dùng cơ chế kiểm tra trong cùng statement (ví dụ `STRICT`) và ràng buộc duy nhất để bảo vệ bất biến dài hạn.

### 19.2. SELECT INTO không tự khóa đối tượng nghiệp vụ

Câu:

```sql
SELECT u.points
INTO STRICT v_points
FROM app_users_demo AS u
WHERE u.user_id = 101;
```

lấy một giá trị trong khối PL/pgSQL, nhưng **không tự khóa hàng cho tới khi xong mọi phép tính về sau**. Nếu cần đọc rồi cập nhật dựa trên trạng thái không bị thay đổi, có thể cần transaction và khóa hàng:

```sql
SELECT u.points
INTO STRICT v_points
FROM app_users_demo AS u
WHERE u.user_id = 101
FOR UPDATE;
```

Trên PostgreSQL, `FOR UPDATE` yêu cầu khóa hàng phù hợp và giao dịch cần được quản lý đúng. Nếu nghiệp vụ chỉ muốn cộng điểm:

```sql
UPDATE app_users_demo
SET points = points + 10
WHERE user_id = 101;
```

thì một câu `UPDATE` nguyên tử có thể đơn giản và an toàn hơn **đọc điểm vào biến, cộng ở ứng dụng rồi ghi lại giá trị tuyệt đối** trong điều kiện nhiều phiên.

### 19.3. FOR UPDATE không tự ngăn mọi hàng trùng mới được chèn

Nếu khóa một hàng hiện tại rồi nghĩ “không ai có thể chèn user khác cùng email”, kết luận đó không đúng trong mọi isolation và DBMS. Khóa hàng đang tồn tại không tương đương ràng buộc **UNIQUE(tenant_id, email)** đối với hàng mới.

Vì thế:

- **`INTO STRICT`**: yêu cầu đúng một hàng khi đọc.
- **`UNIQUE`/`PRIMARY KEY`**: ngăn dữ liệu trùng theo ràng buộc ghi.
- **Transaction/isolation/locking**: phối hợp nhiều bước có phụ thuộc trạng thái.
- **Hợp đồng nghiệp vụ**: quyết định “không tìm thấy” và “trùng” có phải lỗi không.

Bốn lớp này bổ sung cho nhau, không thay thế hoàn toàn.

### 19.4. Nếu kết quả SELECT INTO được dùng cho thao tác nguy hiểm

Ví dụ hàm đọc `user_id` rồi xóa tất cả dữ liệu của user đó. Một lựa chọn sai do email trùng có thể gây hậu quả lớn. Quy trình an toàn cần:

1. Xác nhận đầy đủ khóa định danh (tenant + ID hoặc khóa nghiệp vụ được bảo vệ).
2. Từ chối khi có nhiều hàng và nghiệp vụ yêu cầu duy nhất.
3. Kiểm tra quyền thao tác và thông tin đã xác thực.
4. Sử dụng transaction và điều kiện cập nhật/xóa đủ chặt.
5. Kiểm tra số hàng bị ảnh hưởng và kết quả thực tế.
6. Ghi audit và tuân thủ chính sách lưu trữ/khôi phục.

Không dùng `LIMIT 1` để “chọn đại một user” trước hành động xóa, thanh toán hoặc thay đổi phân quyền.

## 20. Mẫu chọn chiến lược xử lý theo yêu cầu

| Yêu cầu nghiệp vụ | PostgreSQL PL/pgSQL | Điểm cần nhớ |
|---|---|---|
| Có thể không có user, nếu có thì tối đa một | `SELECT ... INTO ...; IF FOUND THEN ...` | Kiểm tra `FOUND` ngay sau SELECT |
| Bắt buộc đúng một user | `SELECT ... INTO STRICT ...` | Bắt `NO_DATA_FOUND` / `TOO_MANY_ROWS` nếu cần |
| Chỉ cần biết tồn tại ít nhất một | `PERFORM 1 FROM ...; IF FOUND ...` hoặc `SELECT EXISTS(...) INTO v_bool` | Không tự bảo đảm duy nhất |
| Cần đếm tổng số user khớp | `SELECT COUNT(*) INTO v_count ...` | COUNT không GROUP BY trả một hàng kể cả khi 0 |
| Cần một user mới nhất trong số nhiều | `ORDER BY created_at DESC, user_id DESC LIMIT 1` | Cố ý giới hạn, không kiểm tra trùng |
| Cần tất cả user | Trả tập kết quả, vòng `FOR ... IN SELECT` hoặc `RETURN QUERY` | Không nhét nhiều hàng vào một biến vô hướng |
| Cần nhiều thuộc tính của đúng một user | `INTO STRICT v_id,v_name` hoặc `%ROWTYPE`/`RECORD` | Kiểm tra kiểu và thứ tự cột |
| Cần ngăn trùng lâu dài | `UNIQUE(tenant_id,email)` sau khi xác minh quy tắc | Kiểm tra đọc không thay thế constraint |
| Cần update dựa trên trạng thái hiện tại | Transaction, locking hoặc UPDATE nguyên tử | Tránh đọc–ghi bị race |

### 20.1. Khi nào trả nhiều hàng là đúng?

Một hàm báo cáo như “danh sách mọi user ACTIVE trong tenant” **được phép trả nhiều hàng**. Khi đó, không nên ép query thành `SELECT INTO STRICT một biến`. Trên PostgreSQL PL/pgSQL có thể dùng `RETURN QUERY` trong hàm trả tập:

```sql
CREATE OR REPLACE FUNCTION active_users_for_tenant(
    p_tenant_id INTEGER
)
RETURNS TABLE (
    result_user_id INTEGER,
    result_name TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT u.user_id, u.display_name
    FROM app_users_demo AS u
    WHERE u.tenant_id = p_tenant_id
      AND u.status = 'ACTIVE'
    ORDER BY u.user_id;
END;
$$;
```

```sql
SELECT * FROM active_users_for_tenant(1);
```

Kết quả có **4 user**: **101, 102, 103, 107**. Trong trường hợp này nhiều hàng **không phải lỗi** vì hợp đồng của hàm là trả một **bảng kết quả**.

### 20.2. Hàm trả một giá trị không đồng nghĩa query nguồn trả một hàng

Một hàm `RETURNS INTEGER` có thể tính số lượng user bằng `COUNT(*)`; query nguồn có thể gồm hàng nghìn user, nhưng biểu thức tổng hợp trả một hàng chứa số đếm. Ngược lại, một hàm `RETURNS TEXT` dùng `SELECT name INTO ...` có thể gặp nhiều user nếu `WHERE` không phân định đủ.

Khi thiết kế thủ tục/hàm cần tách:

- **Số hàng dữ liệu nền được duyệt**.
- **Số hàng của kết quả SELECT ở cấp câu SQL**.
- **Số biến nhận kết quả**.
- **Kiểu đầu ra cuối cùng của function/procedure**.

## 21. Những lỗi thường gặp

### Lỗi 1 — Tin PostgreSQL SELECT INTO mặc định báo lỗi nếu có hai hàng

Không có `STRICT`, PostgreSQL lấy một hàng đầu tiên theo cách thực thi. Nếu cần bảo đảm đúng một, dùng `STRICT` và ràng buộc phù hợp.

### Lỗi 2 — Coi giá trị biến NULL nghĩa là không tìm thấy

User 106 tồn tại nhưng `display_name = NULL`. Truy vấn trả một hàng và `FOUND = TRUE`. Phải tách “hàng không tồn tại” khỏi “giá trị cột là NULL”.

### Lỗi 3 — Không lưu FOUND ngay sau SELECT

Một `PERFORM` hoặc DML ở giữa có thể thay đổi `FOUND`. Lưu `v_lookup_found := FOUND` ngay sau phép tra cứu cần xét.

### Lỗi 4 — Dùng FOUND để khẳng định chỉ có một hàng

`FOUND = TRUE` với cả 1 và 2+ hàng đối với `SELECT INTO` không STRICT. Nó chỉ biểu diễn có ít nhất một hàng được lấy.

### Lỗi 5 — Dùng STRICT nhưng thêm LIMIT 1 để “hết lỗi trùng”

`LIMIT 1` làm mất bằng chứng có nhiều hàng. Nếu nghiệp vụ yêu cầu duy nhất, phải giữ kiểm tra cardinality thực và sửa dữ liệu/khóa.

### Lỗi 6 — Dùng ORDER BY không có khóa phân định

“Mới nhất” theo `created_at` có thể đồng hạng. Dùng thêm một khóa duy nhất như `user_id DESC` nếu quy tắc chọn cho phép.

### Lỗi 7 — Nghĩ COUNT(*) trên tập rỗng gây NO_DATA_FOUND

`COUNT(*)` không `GROUP BY` trả một hàng có 0, nên `STRICT` không báo thiếu. Phải kiểm tra `v_count = 0`.

### Lỗi 8 — Nghĩ GROUP BY cũng luôn trả một hàng

Không có nhóm thì `GROUP BY` có thể trả 0 hàng; nhiều trạng thái có thể tạo nhiều hàng. Xét số hàng của **truy vấn cuối**, không chỉ thấy có hàm COUNT là đủ.

### Lỗi 9 — Đảo thứ tự biểu thức SELECT và biến INTO

`SELECT user_id, status INTO v_status, v_user_id` có thể gây chuyển kiểu sai hoặc gán nhầm ý nghĩa. Dùng thứ tự đúng và tên rõ ràng.

### Lỗi 10 — Nhầm SQL SELECT INTO tạo bảng với PL/pgSQL SELECT INTO biến

Trong PostgreSQL ngoài PL/pgSQL, `SELECT ... INTO new_table` tạo bảng. Trong PL/pgSQL, `INTO v_variable` gán biến. Dùng `CREATE TABLE ... AS SELECT` khi muốn tạo bảng trong quy trình.

### Lỗi 11 — Chuyển PostgreSQL không STRICT sang Oracle mà không đổi ngữ nghĩa

Oracle PL/SQL `SELECT INTO` exact fetch báo `NO_DATA_FOUND` hoặc `TOO_MANY_ROWS`; không có mặc định chọn hàng đầu như PL/pgSQL không STRICT.

### Lỗi 12 — Nghĩ SQL Server SELECT @v = col FROM không có hàng sẽ gán NULL

Nó thường **giữ giá trị cũ**. `SET @v = (scalar subquery)` mới có hành vi gán `NULL` khi truy vấn con không có hàng.

### Lỗi 13 — Nghĩ SQL Server SELECT @v = col FROM nhiều hàng sẽ báo lỗi

Biến có thể được gán nhiều lần, giá trị cuối không được dùng để suy ra một user đúng nếu không có quy tắc chọn. Cần kiểm tra `@@ROWCOUNT` hoặc dùng scalar subquery/constraint theo nhu cầu.

### Lỗi 14 — Đọc @@ROWCOUNT quá muộn

Trong SQL Server, các câu tiếp theo có thể thay đổi `@@ROWCOUNT`. Phải lưu ngay sau câu SELECT muốn kiểm tra số hàng.

### Lỗi 15 — MySQL SELECT INTO không có hàng nhưng dùng lại biến cũ

MySQL có thể để nguyên biến khi không có hàng, đồng thời báo điều kiện No data. Cần handler hoặc cách kiểm tra phù hợp, và khởi tạo trạng thái trước mỗi lần tra cứu.

### Lỗi 16 — Bắt mọi exception và trả NULL

Một lỗi duplicate, lỗi quyền, lỗi kết nối hay lỗi kiểu dữ liệu đều có thể bị che thành “không có user”. Bắt hẹp các trường hợp nghiệp vụ đã định nghĩa và để lỗi không mong đợi được báo rõ.

### Lỗi 17 — Đếm trước rồi tra cứu sau mà bỏ qua concurrency

Hai câu `SELECT` có thể thấy hai trạng thái khác nhau nếu có giao dịch đồng thời. Ràng buộc duy nhất và chiến lược transaction/locking là cần thiết khi dữ liệu phải nhất quán.

### Lỗi 18 — Chỉ lọc email mà quên tenant

`an@example.com` có ở tenant 1 và 2. Quên `tenant_id` làm kết quả mơ hồ và có thể gây rò rỉ dữ liệu giữa tổ chức.

### Lỗi 19 — Tưởng SELECT INTO STRICT ngăn ghi dữ liệu trùng

`STRICT` chỉ kiểm tra khi truy vấn thực thi; nó không phải ràng buộc ghi. Dùng `UNIQUE`/`PRIMARY KEY` phù hợp để bảo vệ dữ liệu lâu dài.

### Lỗi 20 — Dùng LIMIT 1 trước thao tác xóa hoặc đổi quyền quan trọng

Nếu khóa tra cứu không duy nhất, chọn ngẫu nhiên một user rồi làm hành động nhạy cảm có thể tác động sai người. Xác nhận khóa định danh và từ chối dữ liệu mơ hồ.

### Lỗi 21 — Dùng một biến vô hướng để “nhận danh sách”

Nếu cần tất cả user ACTIVE, thiết kế hàm trả tập hoặc vòng lặp; `SELECT INTO` một biến chỉ hợp với một kết quả theo ngữ nghĩa tương ứng.

### Lỗi 22 — Nhầm giá trị NULL của MAX/SUM với 0 hàng kết quả

Tổng hợp trên tập rỗng thường trả một hàng có giá trị `NULL` (trừ `COUNT` trả 0). Hãy phân biệt **hàng kết quả** với **giá trị trong hàng**.

## 22. Bài tập thực hành có đáp án

Các bài mặc định dùng bảng `app_users_demo` có 7 hàng từ mục 2. Mỗi bài là tình huống độc lập; các đoạn `DO`/function minh họa PostgreSQL trừ khi đề ghi rõ DBMS khác. Để thực hành nhiều lần, không cần sửa bảng nguồn.

### Bài 1 — Gán một user theo khóa chính

Viết khối PL/pgSQL lấy `display_name` và `points` của `user_id = 101`:

```sql
DO $$
DECLARE
    v_name TEXT;
    v_points INTEGER;
BEGIN
    SELECT display_name, points
    INTO STRICT v_name, v_points
    FROM app_users_demo
    WHERE user_id = 101;

    RAISE NOTICE 'name=%, points=%', v_name, v_points;
END
$$;
```

**Đáp án:** `An` và `120`; không có exception vì đúng một hàng.

### Bài 2 — Không STRICT, không tìm thấy

Một biến `v_id INTEGER := -1` nhận:

```sql
SELECT user_id INTO v_id
FROM app_users_demo
WHERE user_id = 999;
```

Sau SELECT, `v_id` bằng gì trong PL/pgSQL?

**Đáp án:** `NULL`, không phải `-1`. `FOUND = FALSE`.

### Bài 3 — Không STRICT, nhiều hàng

```sql
SELECT user_id INTO v_id
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';
```

**Đáp án:** câu lệnh không `STRICT` không tự báo lỗi; nó có thể gán ID **103 hoặc 104** tùy hàng đầu của cách thực thi. Không được suy luận chắc chắn chọn 103 nếu không có `ORDER BY` xác định.

### Bài 4 — STRICT, không tìm thấy

```sql
SELECT user_id INTO STRICT v_id
FROM app_users_demo
WHERE user_id = 999;
```

**Đáp án:** `NO_DATA_FOUND`. Phải bắt lỗi hoặc để nó thoát ra theo hợp đồng.

### Bài 5 — STRICT, nhiều hàng

```sql
SELECT user_id INTO STRICT v_id
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';
```

**Đáp án:** `TOO_MANY_ROWS` vì hai ID 103 và 104.

### Bài 6 — FOUND và tên NULL

```sql
SELECT display_name INTO v_name
FROM app_users_demo
WHERE user_id = 106;
```

**Đáp án:** `FOUND = TRUE`, `v_name = NULL`. Không nhầm với 0 hàng.

### Bài 7 — Trạng thái FOUND bị ghi đè

Lệnh đầu tìm user 999, sau đó chạy `PERFORM 1 FROM app_users_demo WHERE user_id = 101`, cuối cùng kiểm tra `FOUND`. Nó biểu thị truy vấn nào?

**Đáp án:** biểu thị phép `PERFORM` gần nhất. Lưu `v_lookup_found := FOUND` ngay sau truy vấn tìm user 999 nếu cần kết quả đó.

### Bài 8 — Lấy bản ghi mới nhất

Chọn user mới nhất trong tenant 1 có email `chung@example.com`:

```sql
SELECT user_id, display_name
INTO v_id, v_name
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com'
ORDER BY created_at DESC, user_id DESC
LIMIT 1;
```

**Đáp án:** **104/Dung**. Đây là chọn mới nhất, không chứng minh email duy nhất.

### Bài 9 — Vì sao STRICT + LIMIT 1 không báo trùng?

Lấy câu bài 5 nhưng thêm `ORDER BY ... LIMIT 1`.

**Đáp án:** dữ liệu đưa vào `STRICT` giờ đã bị giới hạn tối đa một hàng. `TOO_MANY_ROWS` không phát sinh dù điều kiện gốc khớp hai user; `STRICT` vẫn có thể báo `NO_DATA_FOUND` khi không có hàng.

### Bài 10 — COUNT(*) cho email không tồn tại

```sql
SELECT COUNT(*) INTO STRICT v_count
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'khongco@example.com';
```

**Đáp án:** `v_count = 0`, `FOUND = TRUE` và không có `NO_DATA_FOUND`, vì aggregate không GROUP BY trả một hàng.

### Bài 11 — COUNT(*) cho email trùng

```sql
SELECT COUNT(*) INTO v_count
FROM app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';
```

**Đáp án:** `v_count = 2`. Kiểm tra `v_count > 1` để phân loại mơ hồ; không dùng `FOUND` của phép đếm để kết luận số user.

### Bài 12 — GROUP BY làm đổi cardinality

```sql
SELECT status, COUNT(*)
FROM app_users_demo
WHERE tenant_id = 1
GROUP BY status;
```

**Đáp án:** **3 hàng** cho ACTIVE (4), INACTIVE (1), SUSPENDED (1). Nếu `INTO STRICT` hai biến, sẽ gây `TOO_MANY_ROWS`.

### Bài 13 — PERFORM và EXISTS

Trong PostgreSQL, viết một cách chỉ kiểm tra user 102 có tồn tại mà không cần lấy tên.

```sql
PERFORM 1
FROM app_users_demo
WHERE user_id = 102;

IF FOUND THEN
    RAISE NOTICE 'exists';
END IF;
```

**Đáp án:** báo exists. Có thể dùng `SELECT EXISTS(SELECT 1 ... ) INTO v_exists`; khi đó kiểm tra giá trị `v_exists`, không phải `FOUND` của SELECT ngoài.

### Bài 14 — Tên hàm và biến dễ nhập nhằng

Trong hàm có tham số `user_id` cùng tên cột bảng, tại sao `WHERE user_id = user_id` nguy hiểm?

**Đáp án:** có thể bị hiểu là cột so với chính nó hoặc gây lỗi tên mơ hồ tùy ngữ cảnh, không nhận diện đúng tham số. Dùng `p_user_id` và `u.user_id = p_user_id`.

### Bài 15 — %ROWTYPE

Khai báo biến chứa cả hàng user 101:

```sql
DECLARE
    v_user app_users_demo%ROWTYPE;
BEGIN
    SELECT u.* INTO STRICT v_user
    FROM app_users_demo AS u
    WHERE u.user_id = 101;

    RAISE NOTICE '%', v_user.display_name;
END;
```

**Đáp án:** tên `An`. `%ROWTYPE` gắn cấu trúc biến với bảng; `STRICT` kiểm tra số hàng.

### Bài 16 — Oracle SELECT INTO không có hàng

Oracle PL/SQL chạy `SELECT user_id INTO v_id ... WHERE user_id = 999`. Điều gì xảy ra?

**Đáp án:** phát sinh `NO_DATA_FOUND`, không gán `NULL` rồi tiếp tục như PL/pgSQL không STRICT.

### Bài 17 — Oracle SELECT INTO nhiều hàng

Oracle PL/SQL tra tenant 1/email `chung@example.com` bằng `SELECT ... INTO v_id`.

**Đáp án:** `TOO_MANY_ROWS`. Muốn “mới nhất” phải có `ORDER BY` và giới hạn hàng phù hợp; không dùng cách đó nếu email phải duy nhất.

### Bài 18 — SQL Server SELECT @v = col khi 0 hàng

```sql
DECLARE @id INT = -1;
SELECT @id = user_id
FROM dbo.app_users_demo
WHERE user_id = 999;
```

**Đáp án:** `@id` thường **vẫn bằng -1**. Không tự gán `NULL`.

### Bài 19 — SQL Server SET với scalar subquery

So sánh:

```sql
DECLARE @id INT = -1;
SET @id = (
    SELECT user_id
    FROM dbo.app_users_demo
    WHERE user_id = 999
);
```

**Đáp án:** `@id = NULL` vì scalar subquery không có hàng. Nếu subquery trả hai hàng 103/104, SQL Server báo lỗi nhiều giá trị.

### Bài 20 — @@ROWCOUNT

```sql
DECLARE @id INT;
DECLARE @n INT;

SELECT @id = user_id
FROM dbo.app_users_demo
WHERE tenant_id = 1
  AND email = 'chung@example.com';

SET @n = @@ROWCOUNT;
```

**Đáp án:** `@n = 2`. Không dùng `@id` làm kết quả đã xác minh duy nhất. Đọc `@@ROWCOUNT` ngay sau câu quan tâm.

### Bài 21 — MySQL không có hàng

Trong stored procedure MySQL, biến `v_name = 'old'`. Chạy `SELECT display_name INTO v_name ... WHERE user_id = 999`.

**Đáp án:** trường hợp không có hàng báo điều kiện/cảnh báo `No data` và **thường giữ giá trị cũ `'old'`**. Cần handler hoặc cách kiểm tra tương ứng, và thiết kế tránh dùng biến cũ.

### Bài 22 — MySQL nhiều hàng

`SELECT user_id INTO v_id FROM app_users_demo WHERE tenant_id=1 AND email='chung@example.com'` trong MySQL stored routine có hành vi gì?

**Đáp án:** báo lỗi nhiều hàng (thường mã 1172). Không âm thầm chọn một trong hai như PL/pgSQL không STRICT.

### Bài 23 — JDBC ResultSet

Ứng dụng chạy `SELECT user_id,display_name ... LIMIT 2`, sau đó:

1. `rs.next()` lần đầu `false`.
2. Lần đầu `true`, lần hai `false`.
3. Hai lần đều `true`.

**Đáp án:** tương ứng **0 hàng**, **đúng một hàng**, **ít nhất hai hàng**. `display_name = NULL` không làm `rs.next()` trả false nếu hàng tồn tại.

### Bài 24 — Email trùng giữa tenant

Truy vấn `WHERE email = 'an@example.com'` trả bao nhiêu hàng?

**Đáp án:** **2 user** (101 ở tenant 1, 105 ở tenant 2). Với định danh theo tenant/email, phải có cả `tenant_id`.

### Bài 25 — Không thể thêm UNIQUE ngay

Vì sao lệnh `ALTER TABLE ... UNIQUE (tenant_id,email)` có thể thất bại trên bảng mẫu?

**Đáp án:** có hai hàng **103/104** cùng `(1,'chung@example.com')`. Cần xác minh quy tắc và xử lý dữ liệu trước khi áp ràng buộc, không xóa đại một hàng.

### Bài 26 — Khi nào nên dùng hàm trả tập?

Yêu cầu: “Trả tất cả user ACTIVE trong tenant 1”. Nên dùng `SELECT INTO STRICT` một biến hay `RETURN QUERY`?

**Đáp án:** `RETURN QUERY` hoặc hàm trả tập vì có **4 hàng** (101, 102, 103, 107). Nhiều hàng là kết quả đúng nghiệp vụ.

### Bài 27 — Đếm rồi tìm trong giao dịch

Transaction A `COUNT(*) = 1` cho một email, rồi transaction B chèn một user cùng tenant/email trước khi A chạy `SELECT ... INTO`. Tại sao câu đếm đầu không đủ bảo đảm?

**Đáp án:** hai câu có thể nhìn thấy trạng thái khác nhau, tùy mức cô lập và cạnh tranh. Cần kiểm tra trong statement thích hợp, ràng buộc duy nhất nếu nghiệp vụ yêu cầu, và chiến lược transaction đúng.

### Bài 28 — Chọn chiến lược cho yêu cầu

Ghép các yêu cầu sau với công cụ phù hợp:

1. Chỉ biết có ít nhất một user hay không.
2. Bắt buộc có đúng một user.
3. Chọn user mới nhất trong nhiều user.
4. Trả mọi user ACTIVE.
5. Tính số user khớp.

**Đáp án:**

1. `EXISTS` hoặc `PERFORM` + `FOUND`.
2. `SELECT INTO STRICT` và xử lý `NO_DATA_FOUND`/`TOO_MANY_ROWS`.
3. `ORDER BY` với khóa phân định và `LIMIT 1`.
4. Hàm trả tập, `RETURN QUERY` hoặc vòng lặp xử lý nhiều hàng.
5. `COUNT(*)` và kiểm tra giá trị số đếm.

## 23. Bảng ghi nhớ nhanh

| Câu hỏi | PostgreSQL PL/pgSQL | Lưu ý |
|---|---|---|
| Gán một giá trị vào biến | `SELECT col INTO v FROM t WHERE ...` | Không STRICT có thể lấy một hàng đầu |
| Không có hàng, không STRICT | Biến đích thành `NULL` | `FOUND = FALSE` |
| Có nhiều hàng, không STRICT | Gán một hàng đầu tiên | Không tự báo lỗi; thứ tự không đảm bảo nếu thiếu `ORDER BY` |
| Bắt buộc đúng một hàng | `SELECT ... INTO STRICT ...` | 0 → `NO_DATA_FOUND`, 2+ → `TOO_MANY_ROWS` |
| Một hàng chứa NULL | `FOUND = TRUE` | Cột NULL khác không có hàng |
| Kiểm tra có hàng | `FOUND` ngay sau `SELECT INTO` hoặc `PERFORM` | Không bảo đảm duy nhất |
| Đếm nguồn | `SELECT COUNT(*) INTO v_count ...` | Không GROUP BY: luôn một hàng; v_count có thể 0 |
| Chọn mới nhất | `ORDER BY created_at DESC, id DESC LIMIT 1` | Mục đích khác kiểm tra tính duy nhất |
| Chọn nhiều cột | `INTO v1, v2` hoặc `%ROWTYPE`/`RECORD` | Thứ tự và kiểu phải khớp |
| Trả nhiều hàng | `RETURN QUERY`/hàm trả bảng | Không ép vào một biến scalar |
| Tạo bảng từ query PostgreSQL | `CREATE TABLE x AS SELECT ...` | Khác `SELECT INTO biến` trong PL/pgSQL |
| Oracle PL/SQL SELECT INTO | Exact fetch | 0 → `NO_DATA_FOUND`, 2+ → `TOO_MANY_ROWS` |
| SQL Server `SELECT @v = col FROM` | 0 giữ biến cũ, nhiều hàng có thể gán nhiều lần | Dùng `@@ROWCOUNT` ngay sau để kiểm tra |
| SQL Server `SET @v = (SELECT ...)` | 0 gán `NULL`, 2+ lỗi scalar subquery | Khác với `SELECT @v = col FROM` |
| MySQL stored routine `SELECT ... INTO` | 0: No data và biến giữ cũ; 2+: lỗi 1172 | Handler `NOT FOUND` nếu cần |
| SQLite | Đọc `ResultSet`/các hàng ở ứng dụng | Không có stored procedure `SELECT INTO` tương tự |
| Đảm bảo khóa nghiệp vụ duy nhất | `UNIQUE` hoặc `PRIMARY KEY` phù hợp | `STRICT` chỉ kiểm tra khi đọc |
| Dữ liệu thay đổi đồng thời | Transaction/isolation/lock/statement phù hợp | Đếm trước rồi lấy sau không tự nguyên tử |

## Kết luận

**`SELECT INTO biến`** là một công cụ rất hữu ích trong thủ tục và hàm SQL, nhưng cần hiểu rõ **hợp đồng số hàng của truy vấn**:

- **PostgreSQL PL/pgSQL không `STRICT`**: 0 hàng → biến thành `NULL`; 1 hàng → gán; nhiều hàng → lấy một hàng đầu tiên. Dùng `FOUND` để biết có ít nhất một hàng, nhưng `FOUND` không phát hiện trùng.
- **PostgreSQL `INTO STRICT`**: yêu cầu **đúng một hàng**; `NO_DATA_FOUND` cho 0 hàng và `TOO_MANY_ROWS` cho nhiều hàng. Một hàng chứa `NULL` vẫn là một hàng hợp lệ về cardinality.
- **Oracle PL/SQL**: `SELECT INTO` thông thường đã có yêu cầu exact fetch; hành vi giống mục tiêu `INTO STRICT` về số hàng, nhưng cú pháp và ngoại lệ theo Oracle.
- **SQL Server T-SQL**: dùng `SELECT @v = col FROM ...` hoặc `SET @v = (scalar subquery)`, với **hành vi 0/nhiều hàng khác nhau**; phải kiểm tra `@@ROWCOUNT` hoặc quy tắc scalar subquery tùy ý định.
- **MySQL stored routines**: `SELECT ... INTO` yêu cầu một hàng; 0 hàng thường phát sinh điều kiện No data và **không tự xóa giá trị biến cũ**, còn nhiều hàng gây lỗi.
- **Khi nghiệp vụ cho phép nhiều hàng**, dùng `ORDER BY ... LIMIT 1` để **cố ý chọn một** theo tiêu chí xác định, hoặc thiết kế hàm trả tập nếu cần **tất cả**. Không thêm `LIMIT 1` chỉ để che vi phạm duy nhất.
- **Khi dữ liệu phải duy nhất lâu dài**, dùng ràng buộc `UNIQUE`/`PRIMARY KEY` phù hợp. Kiểm tra trong function và transaction không thay thế ràng buộc ghi.

Thói quen quan trọng nhất là **xác định trước truy vấn được phép trả 0, 1 hay nhiều hàng**, rồi chọn cơ chế gán biến, kiểm tra `FOUND`, bắt ngoại lệ hoặc trả tập kết quả tương ứng. Khi phân biệt rõ **số hàng**, **giá trị `NULL`**, **thứ tự chọn** và **ngữ nghĩa theo DBMS**, bạn có thể viết thủ tục và hàm SQL dễ dự đoán, dễ xử lý lỗi và tránh những sai sót nghiệp vụ do âm thầm chọn nhầm bản ghi.
