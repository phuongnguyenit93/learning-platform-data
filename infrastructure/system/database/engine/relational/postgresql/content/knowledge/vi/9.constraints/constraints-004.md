# NULL trong ràng buộc duy nhất và lựa chọn NULLS NOT DISTINCT trong PostgreSQL

Khi thiết kế bảng người dùng, đơn hàng hoặc dữ liệu tích hợp, chúng ta thường đặt `UNIQUE` để không có hai bản ghi trùng email, mã định danh hay một tổ hợp khóa nghiệp vụ. Nhưng một câu hỏi quan trọng dễ bị bỏ qua là: **nếu một hoặc nhiều cột thuộc ràng buộc `UNIQUE` có giá trị `NULL` thì hai hàng được coi là trùng nhau hay không?**

Trong PostgreSQL, câu trả lời mặc định là: **các giá trị `NULL` được xem là phân biệt khi kiểm tra tính duy nhất**. Vì vậy, một cột `email TEXT UNIQUE` vẫn cho phép nhiều hàng có `email IS NULL`. Từ **PostgreSQL 15**, ta có thể chọn hành vi khác bằng cú pháp **`UNIQUE NULLS NOT DISTINCT`** hoặc **`CREATE UNIQUE INDEX ... NULLS NOT DISTINCT`**, tức coi hai giá trị `NULL` ở cùng vị trí là không phân biệt khi kiểm tra ràng buộc duy nhất.

Đây không phải chi tiết cú pháp đơn thuần. Nó phản ánh **quy tắc dữ liệu**:

- Email chưa được cung cấp có được phép xuất hiện ở nhiều tài khoản không?
- Trong mỗi tổ chức, có được có nhiều bản ghi với mã tham chiếu ngoài chưa biết không?
- Một bộ khóa gồm `tenant_id` và `external_code` cần xử lý trường hợp `external_code IS NULL` ra sao?
- Khi dùng `INSERT ... ON CONFLICT`, hai lần ghi `NULL` có tạo hai hàng hay cập nhật cùng một hàng?
- Nếu bảng đang có nhiều giá trị `NULL`, phải xử lý thế nào trước khi đổi sang `NULLS NOT DISTINCT`?

Bài học thuộc chương **Ràng buộc** của module *Database Engine Relational PostgreSQL*. Chúng ta sẽ thực hành với các bảng riêng, so sánh `UNIQUE` mặc định với `NULLS NOT DISTINCT`, phân tích khóa ghép, chỉ mục duy nhất, cách phát hiện dữ liệu trùng và các tình huống triển khai an toàn.

> **Điều kiện phiên bản:** Cú pháp `NULLS NOT DISTINCT` cho ràng buộc và chỉ mục duy nhất được PostgreSQL hỗ trợ từ **phiên bản 15**. Trên PostgreSQL 14 hoặc cũ hơn, không chạy các lệnh có cú pháp đó; phần cuối bài có phương án thay thế cho một số bài toán. Hãy chạy `SHOW server_version;` trước khi thực hành.

## 1. Ôn lại NULL và UNIQUE

### 1.1. NULL không phải một giá trị thông thường

Trong SQL, `NULL` biểu diễn một giá trị **không có/không biết**, chứ không phải chuỗi rỗng `''`, số `0` hoặc chữ `'NULL'`.

```sql
SELECT
    NULL = NULL AS so_sanh_bang,
    NULL <> NULL AS so_sanh_khac,
    NULL IS NULL AS kiem_tra_null,
    NULL IS NOT DISTINCT FROM NULL AS hai_gia_tri_khong_phan_biet;
```

Kết quả:

| so_sanh_bang | so_sanh_khac | kiem_tra_null | hai_gia_tri_khong_phan_biet |
|---|---|---|---|
| `NULL` | `NULL` | `true` | `true` |

Hai phép so sánh `=` và `<>` với `NULL` thường cho kết quả **unknown** (được biểu diễn là `NULL`), không phải `true` hoặc `false`. Để kiểm tra giá trị có thiếu hay không, dùng `IS NULL` hoặc `IS NOT NULL`.

PostgreSQL còn hỗ trợ:

```sql
SELECT
    10 IS DISTINCT FROM 10       AS a,
    10 IS DISTINCT FROM NULL     AS b,
    NULL IS DISTINCT FROM NULL   AS c,
    NULL IS NOT DISTINCT FROM NULL AS d;
```

Kết quả lần lượt là `false`, `true`, `false`, `true`. Hai toán tử `IS DISTINCT FROM` và `IS NOT DISTINCT FROM` cho kết quả boolean rõ ràng ngay cả khi có `NULL`.

**Quan trọng:** Tùy chọn `NULLS NOT DISTINCT` trên một ràng buộc `UNIQUE` **không thay đổi phép toán `NULL = NULL` trên toàn database**. Nó chỉ điều chỉnh cách kiểm tra hai khóa có trùng nhau trong ràng buộc/chỉ mục duy nhất cụ thể.

### 1.2. UNIQUE bảo vệ điều gì?

Ràng buộc `UNIQUE` yêu cầu không có hai hàng cùng mang **một tổ hợp khóa bị coi là trùng** theo ngữ nghĩa ràng buộc và kiểu dữ liệu/collation tương ứng.

Ví dụ một cột:

```sql
CREATE TABLE demo_unique_basic (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT UNIQUE
);
```

Nếu `email` khác `NULL`, hai giá trị bằng nhau như `'a@example.test'` và `'a@example.test'` không thể cùng tồn tại. Nhưng mặc định PostgreSQL **không coi hai giá trị `NULL` là một khóa trùng** trong `UNIQUE`.

### 1.3. UNIQUE khác PRIMARY KEY

| Ràng buộc | Có kiểm tra tính duy nhất? | Cho phép NULL? |
|---|---|---|
| `PRIMARY KEY (id)` | Có | **Không**: cột trong khóa chính bắt buộc `NOT NULL` |
| `UNIQUE (email)` | Có | Có, và mặc định **nhiều `NULL`** |
| `UNIQUE NULLS NOT DISTINCT (email)` | Có | Có, nhưng **tối đa một hàng `NULL`** trong khóa một cột |
| `UNIQUE (email)` + `email NOT NULL` | Có | Không; khi không có NULL, lựa chọn distinctness của NULL không còn tác dụng |

Một bảng có thể có nhiều ràng buộc `UNIQUE` nhưng chỉ một `PRIMARY KEY`. `PRIMARY KEY` xác định khóa định danh bắt buộc hiện diện; `UNIQUE` thường bảo vệ các khóa nghiệp vụ phụ.

## 2. Chuẩn bị môi trường thực hành

Để các ví dụ không ảnh hưởng dữ liệu khác, tạo schema riêng:

```sql
SHOW server_version;
SHOW server_version_num;

CREATE SCHEMA IF NOT EXISTS null_unique_lab;
```

Các bảng dùng các tên riêng như `users_default`, `users_strict` và `tenant_refs_default`. Khi làm trên database dùng chung, cần có quyền tạo schema/bảng, và không chạy các phần dọn dẹp `DROP` nếu đây không phải môi trường demo thuộc quyền quản lý của bạn.

Một số thử nghiệm cố tình gây lỗi trùng khóa. Chúng sẽ được **chú thích** để có thể chạy tuần tự các khối SQL hợp lệ trước; khi muốn quan sát thông báo lỗi, bỏ chú thích **một câu lệnh tại một thời điểm** trong môi trường thực hành.

## 3. UNIQUE mặc định: cho phép nhiều NULL

Tạo bảng lưu email tùy chọn:

```sql
CREATE TABLE null_unique_lab.users_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_users_default_email UNIQUE (email)
);
```

Chèn dữ liệu:

```sql
INSERT INTO null_unique_lab.users_default (email, display_name)
VALUES
    (NULL, 'Tài khoản chưa có email A'),
    (NULL, 'Tài khoản chưa có email B'),
    ('an@example.test', 'An'),
    ('binh@example.test', 'Bình');

SELECT id, email, display_name
FROM null_unique_lab.users_default
ORDER BY id;
```

Kết quả dự kiến:

| id | email | display_name |
|---:|---|---|
| 1 | `NULL` | Tài khoản chưa có email A |
| 2 | `NULL` | Tài khoản chưa có email B |
| 3 | an@example.test | An |
| 4 | binh@example.test | Bình |

Giả sử bảng mới và identity bắt đầu từ 1 như thông thường. **Hai hàng có email `NULL` được lưu thành công**, dù cột có ràng buộc `UNIQUE`.

Nếu thử thêm email đã tồn tại:

```sql
-- Chạy riêng trong lab nếu muốn xem lỗi:
-- INSERT INTO null_unique_lab.users_default (email, display_name)
-- VALUES ('an@example.test', 'An khác');
```

PostgreSQL sẽ từ chối vì email không `NULL` bị trùng. Lỗi điển hình:

```text
ERROR: duplicate key value violates unique constraint "uq_users_default_email"
SQLSTATE: 23505
```

### 3.1. Quy tắc mặc định có ý nghĩa gì?

Ở đây, `NULL` có thể hiểu là **chưa biết hoặc chưa cung cấp email**. Nếu có 1.000 tài khoản chưa cung cấp email, cho phép 1.000 giá trị `NULL` thường là quyết định hợp lý.

`UNIQUE` vẫn đảm bảo những email **đã cung cấp** không trùng nhau. Vì vậy, **đừng tự động thay mọi ràng buộc `UNIQUE` nullable bằng `NULLS NOT DISTINCT`**: với email tùy chọn, thay đổi ấy sẽ khiến chỉ một tài khoản trong cả bảng được phép chưa có email.

### 3.2. Mặc định này không phải “UNIQUE bị hỏng”

Nhiều người viết:

```sql
CREATE TABLE example_code (
    code TEXT UNIQUE
);
```

rồi thấy có nhiều hàng `code IS NULL` và tưởng PostgreSQL không thực thi constraint. Thực tế PostgreSQL vẫn thực thi đúng: các giá trị **không NULL** phải duy nhất, còn `NULL` mặc định được xem là phân biệt với `NULL` khác **chỉ trong ngữ nghĩa UNIQUE**.

Đây là hành vi chủ đích, không phải race condition và cũng không phụ thuộc một cấu hình bật/tắt chung nào ở server.

## 4. NULLS NOT DISTINCT: xem NULL là trùng trong UNIQUE

Từ PostgreSQL 15, thay đổi ngữ nghĩa bằng:

```sql
CREATE TABLE null_unique_lab.users_strict (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    display_name TEXT NOT NULL,
    CONSTRAINT uq_users_strict_email
        UNIQUE NULLS NOT DISTINCT (email)
);
```

Chèn một hàng không có email:

```sql
INSERT INTO null_unique_lab.users_strict (email, display_name)
VALUES
    (NULL, 'Tài khoản chưa có email duy nhất'),
    ('an@example.test', 'An'),
    ('binh@example.test', 'Bình');
```

Nhưng thêm `NULL` lần thứ hai sẽ vi phạm:

```sql
-- Chạy riêng trong lab để quan sát lỗi trên PostgreSQL 15+:
-- INSERT INTO null_unique_lab.users_strict (email, display_name)
-- VALUES (NULL, 'Tài khoản chưa có email thứ hai');
```

Do `UNIQUE NULLS NOT DISTINCT (email)`, PostgreSQL xem khóa `NULL` của hai hàng là **không phân biệt**, nên không cho phép tồn tại đồng thời.

### 4.1. NULLS NOT DISTINCT không có nghĩa NOT NULL

Hai câu lệnh này **không tương đương**:

```sql
-- A: Cấm mọi NULL.
CREATE TABLE null_unique_lab.sample_not_null (
    email TEXT NOT NULL UNIQUE
);

-- B: Cho phép một NULL, nhưng không cho phép hai NULL.
CREATE TABLE null_unique_lab.sample_one_null (
    email TEXT UNIQUE NULLS NOT DISTINCT
);
```

Điểm khác biệt:

| Dữ liệu cần lưu | `NOT NULL UNIQUE` | `UNIQUE NULLS NOT DISTINCT` |
|---|---|---|
| Không có hàng NULL | Hợp lệ | Hợp lệ |
| Một hàng NULL | **Không hợp lệ** | Hợp lệ |
| Hai hàng NULL | Không hợp lệ | **Không hợp lệ** |
| Hai hàng `'A'` | Không hợp lệ | Không hợp lệ |
| `'A'` và `'B'` | Hợp lệ | Hợp lệ |

Nếu nghiệp vụ yêu cầu **“không được thiếu”**, hãy dùng `NOT NULL`. Nếu yêu cầu **“có thể thiếu, nhưng chỉ một hàng được thiếu theo khóa hoặc phạm vi này”**, `NULLS NOT DISTINCT` có thể phù hợp.

### 4.2. Cú pháp viết tường minh NULLS DISTINCT

PostgreSQL 15+ cũng hỗ trợ khai báo ngược lại một cách tường minh:

```sql
CREATE TABLE null_unique_lab.users_explicit_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    CONSTRAINT uq_users_explicit_default_email
        UNIQUE NULLS DISTINCT (email)
);
```

`NULLS DISTINCT` chính là **hành vi mặc định** đã có của `UNIQUE`. Khi không cần nhấn mạnh cách xử lý `NULL`, `UNIQUE (email)` là đủ và tương thích với các phiên bản PostgreSQL cũ hơn.

### 4.3. Tính năng giới hạn trong từng ràng buộc/index

`NULLS NOT DISTINCT` là một thuộc tính của **ràng buộc `UNIQUE` hoặc chỉ mục `UNIQUE` cụ thể**. Nó **không làm**:

- Toán tử `=` coi `NULL = NULL` là `true`.
- Mọi ràng buộc `UNIQUE` khác trong database tự đổi cách hoạt động.
- Một cột trở thành `NOT NULL`.
- Các quy tắc `CHECK`, foreign key hoặc `JOIN ... ON a = b` tự đổi hành vi.

Để so sánh hai giá trị kể cả khi `NULL` trong truy vấn, vẫn phải dùng biểu thức thích hợp như `IS NOT DISTINCT FROM`.

## 5. Khóa ghép: trường hợp thường cần cân nhắc nhất

Trong hệ thống đa khách hàng (*multi-tenant*), khóa nghiệp vụ thường gồm hai hoặc nhiều cột, ví dụ `(tenant_id, external_code)`. Khi một cột được phép `NULL`, hành vi mặc định của `UNIQUE` dễ bị hiểu sai.

### 5.1. UNIQUE(tenant_id, external_code) mặc định

```sql
CREATE TABLE null_unique_lab.tenant_refs_default (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_default
        UNIQUE (tenant_id, external_code)
);

INSERT INTO null_unique_lab.tenant_refs_default
    (tenant_id, external_code, description)
VALUES
    (10, NULL, 'Tổ chức 10: mã chưa biết, lần 1'),
    (10, NULL, 'Tổ chức 10: mã chưa biết, lần 2'),
    (10, 'A-01', 'Tổ chức 10: mã A-01'),
    (20, NULL, 'Tổ chức 20: mã chưa biết'),
    (20, 'A-01', 'Tổ chức 20: mã A-01');
```

Các hàng trên hợp lệ. Đặc biệt:

- Hai hàng `(10, NULL)` được chấp nhận vì `NULL` mặc định phân biệt trong `UNIQUE`.
- `(10, 'A-01')` và `(20, 'A-01')` không trùng nhau vì `tenant_id` khác.
- Nếu thêm `(10, 'A-01')` lần nữa, constraint sẽ từ chối vì **cả hai thành phần khóa xác định đều trùng**.

### 5.2. UNIQUE NULLS NOT DISTINCT trên khóa ghép

```sql
CREATE TABLE null_unique_lab.tenant_refs_strict (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_strict
        UNIQUE NULLS NOT DISTINCT (tenant_id, external_code)
);

INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES
    (10, NULL, 'Bản ghi mã chưa biết của tổ chức 10'),
    (10, 'A-01', 'Bản ghi mã A-01 của tổ chức 10'),
    (20, NULL, 'Bản ghi mã chưa biết của tổ chức 20'),
    (20, 'A-01', 'Bản ghi mã A-01 của tổ chức 20');
```

Giờ nếu chèn `(10, NULL)` lần hai:

```sql
-- Cố tình lỗi do trùng tổ hợp khóa trong PostgreSQL 15+:
-- INSERT INTO null_unique_lab.tenant_refs_strict
--     (tenant_id, external_code, description)
-- VALUES (10, NULL, 'Một bản ghi thiếu mã khác');
```

PostgreSQL từ chối vì `(10, NULL)` và `(10, NULL)` **không phân biệt** theo định nghĩa của constraint.

Nhưng `(20, NULL)` vẫn được phép cùng tồn tại với `(10, NULL)` vì `tenant_id` khác. Như vậy, hành vi là **mỗi tenant tối đa một hàng có `external_code IS NULL`**, không phải toàn database chỉ có một hàng `NULL`.

### 5.3. Bảng chân trị về tính duy nhất của khóa ghép

Giả sử bảng đã có hàng bên trái; có thể thêm hàng bên phải không?

| Khóa đã có | Khóa mới | `UNIQUE` mặc định | `UNIQUE NULLS NOT DISTINCT` |
|---|---|---|---|
| `(10, 'A')` | `(10, 'A')` | Không | Không |
| `(10, 'A')` | `(10, 'B')` | Có | Có |
| `(10, 'A')` | `(20, 'A')` | Có | Có |
| `(10, NULL)` | `(10, NULL)` | **Có** | **Không** |
| `(10, NULL)` | `(20, NULL)` | Có | Có |
| `(10, NULL)` | `(10, 'A')` | Có | Có |

Điều này minh họa ý nghĩa của cụm “`NULLS NOT DISTINCT`”: hai hàng bị xem là trùng **nếu mọi thành phần tương ứng của tổ hợp khóa đều không phân biệt**, trong đó hai `NULL` cùng vị trí được coi tương đương khi kiểm tra unique.

### 5.4. Khi cả hai cột đều nullable

Ví dụ một khóa ghép `(group_id, slot_code)` mà **cả hai đều có thể NULL**:

```sql
CREATE TABLE null_unique_lab.optional_pairs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    group_id INTEGER,
    slot_code TEXT,
    CONSTRAINT uq_optional_pairs
        UNIQUE NULLS NOT DISTINCT (group_id, slot_code)
);

INSERT INTO null_unique_lab.optional_pairs (group_id, slot_code)
VALUES
    (NULL, NULL),
    (NULL, 'A'),
    (NULL, 'B'),
    (10, NULL),
    (20, NULL),
    (10, 'A');
```

Những hàng trên khác nhau theo tổ hợp khóa. Nhưng thêm một hàng giống bất kỳ tổ hợp nào, kể cả `(NULL, NULL)`, `(NULL, 'A')` hoặc `(10, NULL)`, đều bị từ chối.

**Không nên diễn giải** `NULLS NOT DISTINCT` là “bất cứ hàng nào có NULL thì đều trùng mọi hàng khác có NULL”. PostgreSQL vẫn so sánh **từng vị trí** của khóa; các thành phần không NULL vẫn phải bằng nhau.

### 5.5. Nếu thật sự muốn cấm mọi hàng thiếu mã?

Đừng dùng `NULLS NOT DISTINCT` để diễn đạt một quy tắc “mọi hàng bắt buộc có external_code”. Thay vào đó:

```sql
CREATE TABLE null_unique_lab.tenant_refs_required (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT NOT NULL,
    CONSTRAINT uq_tenant_refs_required
        UNIQUE (tenant_id, external_code)
);
```

Ràng buộc `NOT NULL` mô tả sự bắt buộc; `UNIQUE` mô tả không được trùng. Tách hai ý nghĩa giúp schema dễ đọc và thông báo lỗi đúng bản chất.

## 6. Chọn NULLS DISTINCT hay NULLS NOT DISTINCT theo nghiệp vụ

Không có một lựa chọn tốt nhất cho mọi cột. Hãy hỏi **`NULL` đại diện cho điều gì** và **được phép có bao nhiêu hàng thiếu giá trị trong cùng phạm vi**.

| Tình huống | Cách chọn thường hợp lý | Giải thích |
|---|---|---|
| Email là tùy chọn; nhiều khách chưa có email | `UNIQUE (email)` | Các email đã khai báo phải duy nhất, nhiều tài khoản chưa có email là bình thường |
| Mã đơn hàng phải có, không được trùng | `NOT NULL UNIQUE` | Không cho phép thiếu mã |
| Mỗi tenant chỉ được có một “slot mặc định” biểu diễn bằng `NULL` | `UNIQUE NULLS NOT DISTINCT (tenant_id, slot_code)` | Hai dòng `(tenant, NULL)` sẽ xung đột |
| Mỗi tenant được có nhiều bản ghi chờ bên thứ ba cấp mã | `UNIQUE (tenant_id, external_code)` | Nhiều mã chưa biết có thể cùng tồn tại |
| Một khóa gồm nhiều thành phần tùy chọn nhưng tổ hợp không được trùng, kể cả vị trí NULL | `UNIQUE NULLS NOT DISTINCT (col1, col2, ...)` | Hai tổ hợp giống nhau về các thành phần và NULL được coi trùng |
| Chỉ cần duy nhất khi bản ghi “đang hoạt động” | **Partial unique index** có `WHERE` | Lọc theo trạng thái nghiệp vụ, có thể kết hợp NULLS NOT DISTINCT nếu cần |

### 6.1. Không lạm dụng NULL làm “bản ghi mặc định”

Có hệ thống dùng `NULL` làm ký hiệu “giá trị mặc định” hoặc “áp dụng toàn bộ”. Điều này có thể hợp lý nếu được ghi rõ, nhưng cũng dễ mơ hồ: `NULL` vốn thường có nghĩa “không biết/không có”.

Nếu nghiệp vụ cần phân biệt “chưa biết mã” với “mã mặc định”, hãy cân nhắc dùng một cột trạng thái, một bản ghi riêng hoặc mã định danh rõ ràng. `NULLS NOT DISTINCT` giải quyết **tính duy nhất**, không tự làm sáng tỏ **ngữ nghĩa của NULL**.

## 7. UNIQUE constraint và UNIQUE index

PostgreSQL thường thực thi ràng buộc `UNIQUE` bằng một **chỉ mục duy nhất** ở bên dưới. Người quản trị cũng có thể tạo trực tiếp một unique index.

### 7.1. Tạo UNIQUE NULLS NOT DISTINCT bằng constraint

Ví dụ trong khai báo bảng:

```sql
CREATE TABLE null_unique_lab.login_aliases (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    alias TEXT,
    CONSTRAINT uq_login_aliases_tenant_alias
        UNIQUE NULLS NOT DISTINCT (tenant_id, alias)
);
```

Constraint có tên riêng, sẽ xuất hiện trong thông báo vi phạm `unique_violation` và có thể được chỉ định bằng `ON CONFLICT ON CONSTRAINT` trong trường hợp phù hợp.

### 7.2. Tạo unique index trực tiếp

Trên PostgreSQL 15+:

```sql
CREATE TABLE null_unique_lab.aliases_by_index (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    alias TEXT
);

CREATE UNIQUE INDEX uq_aliases_by_index
ON null_unique_lab.aliases_by_index (tenant_id, alias)
NULLS NOT DISTINCT;
```

Chỉ mục này vẫn thực thi quy tắc duy nhất, kể cả khi chưa có ràng buộc `UNIQUE` được khai báo riêng trong `pg_constraint`.

### 7.3. Syntax đối chiếu

| Mục đích | Cú pháp cơ bản trên PostgreSQL 15+ |
|---|---|
| UNIQUE nullable mặc định | `UNIQUE (email)` |
| Nêu rõ mặc định | `UNIQUE NULLS DISTINCT (email)` |
| Xem NULL là trùng | `UNIQUE NULLS NOT DISTINCT (email)` |
| Unique index mặc định | `CREATE UNIQUE INDEX ... ON table (email);` |
| Unique index xem NULL là trùng | `CREATE UNIQUE INDEX ... ON table (email) NULLS NOT DISTINCT;` |

Vị trí `NULLS NOT DISTINCT` khác nhau giữa **table constraint** và **CREATE INDEX**: trong constraint nằm **trước danh sách cột**, còn trong `CREATE UNIQUE INDEX` nằm **sau danh sách cột**. Đây là lỗi cú pháp dễ gặp khi chuyển từ một cách khai báo sang cách khác.

### 7.4. Không phải mọi unique index là một UNIQUE constraint

Một unique index có thể chứa biểu thức hoặc có điều kiện `WHERE`. Trong PostgreSQL, loại chỉ mục đó vẫn bảo vệ tính duy nhất trên tập hàng phù hợp, nhưng không tương đương hoàn toàn với một `UNIQUE` table constraint thông thường.

Ví dụ:

```sql
CREATE TABLE null_unique_lab.active_emails (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_emails_normalized
ON null_unique_lab.active_emails (lower(email))
WHERE deleted_at IS NULL AND email IS NOT NULL;
```

Quy tắc: không có hai hàng **đang hoạt động** (`deleted_at IS NULL`), **có email khác NULL**, và có `lower(email)` bằng nhau theo ngữ nghĩa so sánh của index.

Đây là một **partial expression unique index**, không phải ràng buộc `UNIQUE (email)` thường. Các hàng bị xóa mềm hoặc chưa có email không bị ràng buộc này kiểm tra theo cùng cách.

### 7.5. Partial unique index kết hợp NULLS NOT DISTINCT

Nếu bảng chỉ muốn giới hạn một tổ hợp khóa trong **những hàng đang hoạt động**, PostgreSQL 15+ cho phép:

```sql
CREATE TABLE null_unique_lab.active_slots (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    slot_code TEXT,
    archived_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX uq_active_slots
ON null_unique_lab.active_slots (tenant_id, slot_code)
NULLS NOT DISTINCT
WHERE archived_at IS NULL;
```

Ý nghĩa:

- Hai hàng `(tenant_id=10, slot_code=NULL)` **đang hoạt động** không thể cùng tồn tại.
- Khi một hàng có `archived_at IS NOT NULL`, nó không còn nằm trong phạm vi partial index này.
- Các hàng thuộc hai tenant khác nhau không xung đột.

Lưu ý: partial index cần `WHERE` đúng điều kiện thực tế; nó không tự xóa bản ghi cũ hay thay thế quy tắc vòng đời của ứng dụng.

## 8. Khóa ghép có NULL và truy vấn tìm bản ghi

Để tra một tổ hợp khóa có thể mang `NULL`, viết:

```sql
SELECT *
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = 10
  AND external_code IS NULL;
```

Không viết:

```sql
-- Sai về logic khi muốn tìm NULL:
-- WHERE external_code = NULL
```

### 8.1. Khi giá trị tham số đầu vào có thể NULL

Nếu query được chuẩn bị trước và mã tham chiếu có thể `NULL`, `IS NOT DISTINCT FROM` giúp so sánh theo ngữ nghĩa **hai NULL là khớp**:

```sql
PREPARE find_tenant_ref(INTEGER, TEXT) AS
SELECT id, tenant_id, external_code, description
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = $1
  AND external_code IS NOT DISTINCT FROM $2;

EXECUTE find_tenant_ref(10, NULL);
EXECUTE find_tenant_ref(10, 'A-01');

DEALLOCATE find_tenant_ref;
```

Ví dụ này giải quyết cả hai trường hợp: mã được truyền là chuỗi thật hoặc `NULL`. Nó **không làm thay đổi** cơ chế unique; nó chỉ giúp phần `WHERE` dùng cùng một quan hệ “không phân biệt” khi tìm bản ghi.

### 8.2. Khả năng dùng index vẫn phụ thuộc kế hoạch

Tương đương về mặt logic không có nghĩa mọi cú pháp dùng `IS NOT DISTINCT FROM` đều chắc chắn cho cùng kế hoạch thực thi với `=` hoặc `IS NULL`. PostgreSQL optimizer xem thống kê, operator, loại index, số hàng và tham số truy vấn. Với truy vấn quan trọng, dùng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện thay vì giả định.

## 9. INSERT ... ON CONFLICT khi khóa có NULL

Một tình huống thực tế là **upsert**: nếu đã có bản ghi tương ứng thì cập nhật; nếu chưa có thì chèn.

### 9.1. Với UNIQUE mặc định: NULL không tạo conflict

Trên bảng `tenant_refs_default`:

```sql
INSERT INTO null_unique_lab.tenant_refs_default
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Lần ghi tiếp theo với mã chưa biết')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_default
DO UPDATE
SET description = EXCLUDED.description
RETURNING id, tenant_id, external_code, description;
```

Vì các `NULL` **được coi phân biệt** trong ràng buộc `UNIQUE` mặc định, hàng `(10, NULL)` mới **không xung đột** với những hàng `(10, NULL)` đã có. Do đó, PostgreSQL có thể **chèn thêm hàng mới**, thay vì đi vào nhánh `DO UPDATE`.

`ON CONFLICT` không tự định nghĩa thế nào là trùng. Nó sử dụng **quy tắc duy nhất của chỉ mục/ràng buộc đang làm arbiter**.

### 9.2. Với NULLS NOT DISTINCT: NULL tạo conflict

Trên bảng `tenant_refs_strict`:

```sql
INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Đã cập nhật bản ghi thiếu mã của tenant 10')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_strict
DO UPDATE
SET description = EXCLUDED.description
RETURNING id, tenant_id, external_code, description;
```

Trong bảng đã có `(10, NULL)`, lệnh mới **xung đột** với hàng đó do `NULLS NOT DISTINCT`, vì vậy nhánh `DO UPDATE` được thực hiện. Nếu đổi `tenant_id` thành 30 và chưa có hàng cùng khóa, lệnh có thể tạo hàng mới.

### 9.3. ON CONFLICT DO NOTHING cũng khác nhau

```sql
INSERT INTO null_unique_lab.tenant_refs_strict
    (tenant_id, external_code, description)
VALUES (10, NULL, 'Không chèn vì đã tồn tại')
ON CONFLICT ON CONSTRAINT uq_tenant_refs_strict
DO NOTHING;
```

Lệnh trên không tạo hàng `(10, NULL)` thứ hai. Trong khi đó, với constraint `UNIQUE` mặc định, cùng tổ hợp có `NULL` có thể được chèn thêm.

**Không đánh đồng** `DO NOTHING` với “bỏ qua nếu dữ liệu giống nhau về mọi cột”. Nó chỉ phản ứng với những conflict mà PostgreSQL nhận biết từ các arbiter liên quan.

### 9.4. Cẩn thận nếu có nhiều unique index khả dụng

Khi viết `ON CONFLICT (tenant_id, external_code)`, PostgreSQL có cơ chế suy luận (*index inference*) để chọn unique index phù hợp. Nếu bảng có nhiều unique index cùng khóa nhưng khác mục đích hoặc điều kiện, cần hiểu chính xác arbiter được suy luận.

Với unique **constraint** có tên và không deferrable, `ON CONFLICT ON CONSTRAINT ten_constraint` làm mục tiêu xung đột tường minh hơn. Một **partial unique index** không nhất thiết có constraint name để dùng trong dạng `ON CONSTRAINT`; khi cần inference của partial index, phải viết đúng conflict target và điều kiện.

### 9.5. Constraint DEFERRABLE là trường hợp riêng

`UNIQUE` có thể được khai báo `DEFERRABLE` để trì hoãn kiểm tra tính duy nhất ở một số thời điểm transaction phù hợp. Tuy nhiên, **`ON CONFLICT DO UPDATE` không hỗ trợ dùng deferrable unique constraint làm arbiter**. Không nên đặt mặc định mọi constraint thành `DEFERRABLE` chỉ vì muốn thuận tiện khi cập nhật hàng loạt.

Ví dụ cú pháp để tham khảo trong transaction riêng:

```sql
-- Chỉ minh họa tính năng, không dùng bảng này cho các ví dụ upsert:
CREATE TABLE null_unique_lab.deferred_demo (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT uq_deferred_demo
        UNIQUE NULLS NOT DISTINCT (code)
        DEFERRABLE INITIALLY DEFERRED
);
```

Khi một constraint được trì hoãn, lỗi trùng có thể xuất hiện ở thời điểm `COMMIT` thay vì ngay sau lệnh ghi. Điều này thay đổi cách ứng dụng xử lý lỗi, nhưng không làm biến mất ràng buộc.

## 10. Thêm NULLS NOT DISTINCT vào bảng đang có dữ liệu

Thêm constraint mới lên bảng cũ không chỉ là thay một từ khóa. Nếu bảng đã có **nhiều tổ hợp khóa được xem trùng theo ngữ nghĩa mới**, PostgreSQL sẽ không thể tạo unique constraint/index thành công.

### 10.1. Xem dữ liệu hiện hữu trước

Trên bảng `tenant_refs_default` đã tạo ở mục 5:

```sql
SELECT
    tenant_id,
    external_code,
    COUNT(*) AS so_hang
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1
ORDER BY tenant_id, external_code NULLS FIRST;
```

Kết quả sẽ có ít nhất nhóm `(10, NULL)` với nhiều hàng. Câu lệnh dùng `GROUP BY` rất phù hợp để tìm tổ hợp trùng **kể cả `NULL`**.

### 10.2. Vì sao GROUP BY phát hiện trùng NULL nhưng UNIQUE mặc định cho phép?

Quy tắc **phân nhóm** và **ràng buộc duy nhất** không giống nhau. Trong SQL/PostgreSQL, các `NULL` thường được gom vào **cùng một nhóm** khi `GROUP BY` hay `SELECT DISTINCT`, nhưng mặc định `UNIQUE` lại xem `NULL` là phân biệt cho mục đích kiểm tra khóa.

Điều đó không mâu thuẫn: các toán tử dùng **những quy tắc ngữ nghĩa khác nhau** trong từng ngữ cảnh.

Không dùng:

```sql
SELECT COUNT(DISTINCT external_code)
FROM null_unique_lab.tenant_refs_default;
```

để tìm số tổ hợp trùng có NULL, vì `COUNT(DISTINCT external_code)` bỏ qua giá trị `NULL`.

### 10.3. Đếm các tổ hợp NULL trùng trong một tenant

Nếu `tenant_id` luôn `NOT NULL` và chỉ `external_code` nullable, có thể truy vấn chuyên biệt:

```sql
SELECT
    tenant_id,
    COUNT(*) AS so_ma_null
FROM null_unique_lab.tenant_refs_default
WHERE external_code IS NULL
GROUP BY tenant_id
HAVING COUNT(*) > 1
ORDER BY tenant_id;
```

Nếu `UNIQUE` mặc định đã bảo vệ trường hợp có mã khác `NULL`, các nhóm **mã NULL** thường là rủi ro chính trước khi chuyển sang `NULLS NOT DISTINCT`. Với khóa có nhiều thành phần nullable, dùng `GROUP BY` trên **toàn bộ thành phần khóa** để phát hiện các trường hợp trùng theo ngữ nghĩa mới.

### 10.4. Liệt kê hàng cần xem xét, không xóa tự động

Nếu cần liệt kê từng hàng nằm trong nhóm trùng:

```sql
WITH danh_dau AS (
    SELECT
        id,
        tenant_id,
        external_code,
        description,
        COUNT(*) OVER (
            PARTITION BY tenant_id, external_code
        ) AS so_hang_cung_khoa,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, external_code
            ORDER BY id
        ) AS thu_tu_trong_nhom
    FROM null_unique_lab.tenant_refs_default
)
SELECT *
FROM danh_dau
WHERE so_hang_cung_khoa > 1
ORDER BY tenant_id, external_code NULLS FIRST, id;
```

`ROW_NUMBER` giúp người vận hành **nhìn thấy** các bản ghi trong cùng nhóm, không phải quyết định tự động rằng hàng số 2 phải bị xóa. Trong nghiệp vụ thật, hai bản ghi `external_code IS NULL` có thể là hai thực thể hợp lệ; muốn ép chỉ còn một hàng cần quy tắc hợp nhất/cấp mã/thay đổi mô hình dữ liệu, không xóa tùy tiện.

## 11. Quy trình migration từ UNIQUE mặc định sang NULLS NOT DISTINCT

Ví dụ một bảng lớn đang dùng `UNIQUE (tenant_id, external_code)` nhưng tổ chức đã xác nhận yêu cầu mới: **mỗi tenant chỉ có một hàng không có mã**.

### 11.1. Bước 1: xác định phạm vi và nhu cầu thật

Cần trả lời:

- Có thật sự muốn chỉ một `NULL` trên **mỗi tenant**, hay muốn cấm `NULL` hoàn toàn?
- Có trạng thái `deleted_at` hoặc `archived_at` khiến một số hàng không còn thuộc phạm vi uniqueness?
- Có transaction hoặc job nào đang tạo hàng `NULL` mới?
- Ứng dụng có sử dụng `ON CONFLICT` theo tên constraint cũ không?
- Bảng có partitioning không, và unique key có bao gồm partition key phù hợp không?
- Có dữ liệu đã trùng khi áp quy tắc mới không?

Đừng thay constraint trước khi xác nhận semantics: một thay đổi đúng cú pháp có thể khiến luồng nhập dữ liệu đang hợp lệ trở thành lỗi.

### 11.2. Bước 2: tìm dữ liệu sẽ xung đột

```sql
SELECT tenant_id, external_code, COUNT(*)
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

Kết quả trống **tại thời điểm đọc** chưa đảm bảo migration an toàn nếu trong lúc kiểm tra có tiến trình khác vẫn chèn dữ liệu trùng. Khi cần, hãy thiết kế thời điểm chuyển đổi, khóa/điều phối ghi hoặc phương án xây chỉ mục thích hợp để tránh race condition.

### 11.3. Bước 3: xử lý trùng theo nghiệp vụ

Lựa chọn có thể là:

- Bổ sung `external_code` thật cho các hàng đang `NULL`, nếu nguồn mã có thể cung cấp chính xác.
- Hợp nhất hai bản ghi thực sự là một thực thể theo quy tắc nghiệp vụ.
- Đánh dấu một hàng không còn hoạt động rồi áp **partial unique index** chỉ với hàng đang hoạt động.
- Giữ hành vi `NULLS DISTINCT` nếu yêu cầu cũ vẫn đúng; không cần migration.

Không tự động `DELETE` tất cả ngoại trừ hàng có `MIN(id)`: khóa ngoại, lịch sử giao dịch và tính hợp lệ của dữ liệu có thể bị phá vỡ.

### 11.4. Bước 4: tạo constraint mới trên bảng nhỏ hoặc có cửa sổ bảo trì

Khi đã làm sạch dữ liệu và có kế hoạch bảo trì phù hợp, một lựa chọn đơn giản là:

```sql
-- Ví dụ cú pháp PostgreSQL 15+; chỉ dùng trên bảng đã kiểm tra.
ALTER TABLE null_unique_lab.tenant_refs_default
ADD CONSTRAINT uq_tenant_refs_default_strict
UNIQUE NULLS NOT DISTINCT (tenant_id, external_code);
```

Khi constraint mới thành công, các hàng không được trùng theo ngữ nghĩa mới. Nếu bảng đã có ràng buộc `UNIQUE` cũ cùng khóa, trong một thời gian có thể có **hai chỉ mục bảo vệ cùng bộ cột**; cần kế hoạch gỡ bỏ constraint cũ khi an toàn để tránh duy trì chỉ mục dư.

Ví dụ cú pháp gỡ constraint cũ, **không chạy trước khi chắc chắn các tham chiếu trong ứng dụng đã cập nhật**:

```sql
-- Sau khi đã kiểm soát dependency và mục tiêu ON CONFLICT:
-- ALTER TABLE null_unique_lab.tenant_refs_default
-- DROP CONSTRAINT uq_tenant_refs_default;
```

`ALTER TABLE ... ADD CONSTRAINT UNIQUE` cần quét/kiểm tra dữ liệu và có thể lấy khóa ảnh hưởng ghi/đọc. Với bảng lớn, phải đánh giá chi phí và khóa thực tế.

### 11.5. Bước 5: bảng lớn có thể xem xét CREATE UNIQUE INDEX CONCURRENTLY

PostgreSQL hỗ trợ tạo chỉ mục đồng thời nhằm hạn chế một số loại blocking của quá trình xây index:

```sql
-- Chỉ chạy khi dữ liệu đã được xử lý và có kế hoạch bảo trì.
CREATE UNIQUE INDEX CONCURRENTLY
    idx_tenant_refs_default_strict
ON null_unique_lab.tenant_refs_default
    (tenant_id, external_code)
NULLS NOT DISTINCT;
```

**Các giới hạn vận hành quan trọng:**

- `CREATE INDEX CONCURRENTLY` **không chạy bên trong transaction block**.
- Nó có thể chạy lâu hơn và tiêu tốn I/O đáng kể.
- Nếu phát hiện dữ liệu trùng hoặc thất bại, PostgreSQL có thể để lại **index không hợp lệ (*invalid*)**, cần kiểm tra và dọn bằng quy trình thích hợp.
- Các giao dịch ghi đồng thời vẫn phải được điều phối để tránh dữ liệu mới không phù hợp; tạo index concurrently không bỏ quy tắc nhất quán.
- Trên hệ thống thật, kiểm tra phiên bản PostgreSQL, topology và quyền trước khi chọn phương án này.

Khi unique index đã xây thành công và đủ điều kiện (index hợp lệ, không phải partial/expression index, kiểu hỗ trợ), PostgreSQL có thể cho phép **gắn index vào một table constraint**:

```sql
-- Ví dụ chỉ dành cho một index đã hoàn tất và đủ điều kiện:
ALTER TABLE null_unique_lab.tenant_refs_default
ADD CONSTRAINT uq_tenant_refs_default_strict
UNIQUE USING INDEX idx_tenant_refs_default_strict;
```

Khi sử dụng `USING INDEX`, PostgreSQL dùng index đã tồn tại thay vì xây lại toàn bộ một index mới, nhưng thao tác gắn constraint vẫn cần quyền/khóa thích hợp. Không cố dùng phương án này với **partial index** hoặc **expression index**, vì các loại đó không thể trở thành unique constraint thông thường theo cách trên.

**Lưu ý:** Hai phương án `ADD CONSTRAINT ... UNIQUE NULLS NOT DISTINCT` trực tiếp và `CREATE INDEX ...; ADD CONSTRAINT ... USING INDEX` là **hai lộ trình lựa chọn**, không chạy cả hai vào cùng bảng với cùng tên constraint.

### 11.6. Bước 6: kiểm tra ứng dụng sau chuyển đổi

Sau khi có ràng buộc mới:

1. Thử chèn tổ hợp khóa mới chưa tồn tại.
2. Thử chèn tổ hợp đã tồn tại với cột có `NULL` và xác nhận lỗi `23505`.
3. Thử upsert đúng `ON CONFLICT ON CONSTRAINT` nếu ứng dụng dùng cơ chế này.
4. Đảm bảo code không còn phụ thuộc tên constraint cũ đã được gỡ.
5. Kiểm tra chỉ mục dư, thời gian truy vấn và log lỗi.
6. Ghi rõ yêu cầu nghiệp vụ mới trong tài liệu schema/API.

**Không coi một lệnh ALTER thành công là đủ** nếu ứng dụng còn có luồng ghi coi nhiều `NULL` là hợp lệ.

## 12. Kiểm tra constraint và index hiện có

Để tránh sửa nhầm, nên biết ràng buộc hiện tại có thuộc tính gì.

### 12.1. Xem định nghĩa constraint từ catalog

```sql
SELECT
    conname AS constraint_name,
    contype,
    condeferrable,
    condeferred,
    pg_get_constraintdef(oid) AS constraint_definition
FROM pg_constraint
WHERE conrelid = 'null_unique_lab.tenant_refs_strict'::regclass
  AND contype IN ('u', 'p')
ORDER BY conname;
```

Trong `pg_constraint`:

- `contype = 'u'` biểu diễn unique constraint.
- `contype = 'p'` biểu diễn primary key.
- `condeferrable` và `condeferred` cho biết đặc tính trì hoãn.
- `pg_get_constraintdef` trả dạng SQL mô tả constraint.

Với constraint `NULLS NOT DISTINCT` trên PostgreSQL 15+, định nghĩa trả về có thể hiện thuộc tính này để dễ nhận diện.

### 12.2. Xem thuộc tính indnullsnotdistinct trong pg_index

PostgreSQL 15+ có cột `pg_index.indnullsnotdistinct`:

```sql
SELECT
    i.indexrelid::regclass AS index_name,
    i.indisunique AS is_unique,
    i.indnullsnotdistinct AS nulls_not_distinct,
    i.indisvalid AS is_valid,
    pg_get_indexdef(i.indexrelid) AS index_definition
FROM pg_index AS i
WHERE i.indrelid = 'null_unique_lab.tenant_refs_strict'::regclass
ORDER BY index_name;
```

Khi `indnullsnotdistinct = true` ở một unique index, PostgreSQL kiểm tra `NULL` theo quy tắc không phân biệt. Ở một primary key, các cột đã `NOT NULL` nên việc diễn giải `NULL` không có ý nghĩa thực tế.

**Cẩn thận phiên bản:** `indnullsnotdistinct` không tồn tại trên PostgreSQL 14 trở xuống. Không sao chép truy vấn catalog này sang bản cũ mà không sửa.

### 12.3. Xem index qua pg_indexes

Một truy vấn có thể dùng cho nhiều phiên bản:

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'null_unique_lab'
ORDER BY tablename, indexname;
```

`indexdef` giúp nhìn cú pháp index đã tạo, như `UNIQUE`, `NULLS NOT DISTINCT` hoặc `WHERE` của partial index. Tuy nhiên, đây không thay thế việc xem dependency, quyền và ràng buộc trong catalog khi thay đổi schema.

## 13. Phương án trước PostgreSQL 15

Trên PostgreSQL 14 hoặc cũ hơn, không có cú pháp `UNIQUE NULLS NOT DISTINCT`. Một số quy tắc tương đương có thể được tạo bằng **kết hợp các unique index có điều kiện**, tùy phạm vi nghiệp vụ.

### 13.1. Trường hợp một cột nullable, khóa tenant_id NOT NULL

Yêu cầu: mỗi `tenant_id` chỉ có một hàng `external_code IS NULL`, đồng thời các `external_code` không NULL phải duy nhất trong tenant.

```sql
CREATE TABLE null_unique_lab.legacy_tenant_refs (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    description TEXT NOT NULL,
    CONSTRAINT uq_legacy_tenant_code
        UNIQUE (tenant_id, external_code)
);

-- Chỉ một hàng external_code IS NULL cho mỗi tenant_id.
CREATE UNIQUE INDEX uq_legacy_one_null_per_tenant
ON null_unique_lab.legacy_tenant_refs (tenant_id)
WHERE external_code IS NULL;
```

Giải thích:

- `UNIQUE (tenant_id, external_code)` ngăn trùng mã khác `NULL` trong cùng tenant.
- Partial unique index trên `tenant_id` **chỉ gồm các hàng có external_code NULL**, nên ngăn có hai hàng `NULL` thuộc cùng tenant.
- `tenant_id NOT NULL` là giả định quan trọng: nếu tenant cũng nullable, quy tắc riêng của khóa đó phải được thiết kế lại.

Đây là **một phương án thay thế cho bài toán cụ thể**, không phải cú pháp tổng quát tự động chuyển mọi khóa nhiều cột nullable thành ngữ nghĩa PostgreSQL 15.

### 13.2. Nếu chỉ muốn duy nhất những giá trị khác NULL

Trong trường hợp một cột nullable:

```sql
CREATE UNIQUE INDEX uq_optional_external_code_nonnull
ON null_unique_lab.legacy_tenant_refs (external_code)
WHERE external_code IS NOT NULL;
```

**Cảnh báo ngữ nghĩa:** Index ví dụ này áp tính duy nhất của `external_code` **trên toàn bảng**, không theo tenant. Nếu muốn duy nhất **trong mỗi tenant**, phải dùng khóa `(tenant_id, external_code)`:

```sql
CREATE UNIQUE INDEX uq_legacy_nonnull_by_tenant
ON null_unique_lab.legacy_tenant_refs (tenant_id, external_code)
WHERE external_code IS NOT NULL;
```

Với khóa ghép, cả hai cột và điều kiện `WHERE` đều quyết định phạm vi. Trong schema đã có `UNIQUE (tenant_id, external_code)` mặc định, index partial vừa nêu thường **không cần thiết** để bảo vệ trùng mã khác NULL vì constraint hiện có đã làm việc đó; chỉ dùng nếu đang thiết kế thay thế hoặc có yêu cầu hiệu năng/chỉ mục khác.

### 13.3. Dùng COALESCE với giá trị sentinel có rủi ro

Trước PostgreSQL 15, đôi khi người ta dùng expression index:

```sql
-- Mô tả kỹ thuật, không nên sao chép nguyên xi:
-- CREATE UNIQUE INDEX uq_expr
-- ON some_table (tenant_id, COALESCE(external_code, '<MISSING>'));
```

Nó biến `NULL` thành một giá trị thay thế để so trùng, nhưng **có thể xung đột với dữ liệu thật** nếu một khách hàng hợp lệ dùng đúng chuỗi `'<MISSING>'`. Khi đó index sẽ gộp hai trường hợp khác nghĩa thành một khóa.

Muốn dùng kỹ thuật này phải **bảo đảm sentinel không nằm trong miền giá trị hợp lệ** bằng constraint/thiết kế nghiệp vụ phù hợp và phải xét kiểu, collation, quyền, hiệu năng. Nếu có PostgreSQL 15+, `NULLS NOT DISTINCT` thường trực tiếp và rõ nghĩa hơn.

### 13.4. Trigger kiểm tra trước INSERT có đủ không?

Một trigger kiểm tra:

```sql
-- Ý tưởng dễ sai nếu không xét đồng thời:
-- IF EXISTS (
--     SELECT 1 FROM table_name
--     WHERE tenant_id = NEW.tenant_id
--       AND external_code IS NOT DISTINCT FROM NEW.external_code
-- ) THEN ...
```

có thể gặp **race condition**: hai transaction cùng kiểm tra “chưa có hàng” rồi cùng chèn trước khi transaction còn lại commit. Unique constraint/index là cơ chế atomic được PostgreSQL dùng để giải quyết cạnh tranh này. Không thay một yêu cầu duy nhất bằng `SELECT EXISTS` ở ứng dụng hoặc trigger đơn giản khi chưa có thiết kế khóa/đồng thời đúng.

## 14. Lỗi 23505 và xử lý đồng thời

PostgreSQL bảo vệ uniqueness ở tầng storage/index khi ghi. Nếu hai transaction cùng cố tạo một tổ hợp khóa vi phạm, một transaction có thể phải chờ tình trạng giao dịch khác được xác định rồi nhận **SQLSTATE 23505**.

Điều này quan trọng vì cách làm sau **không đủ an toàn**:

```text
Ứng dụng A: SELECT kiểm tra chưa có key
Ứng dụng B: SELECT kiểm tra chưa có key
Ứng dụng A: INSERT key
Ứng dụng B: INSERT key
```

Chỉ check ở ứng dụng không ngăn được ghi đồng thời. Hãy dùng **constraint/index đúng ngữ nghĩa**, kết hợp `ON CONFLICT` hoặc xử lý `23505` theo loại thao tác.

### 14.1. Phân biệt unique_violation với lỗi khác

Trong PostgreSQL, SQLSTATE:

| Mã | Tên | Nghĩa |
|---|---|---|
| `23505` | `unique_violation` | Vi phạm unique constraint/index |
| `23502` | `not_null_violation` | Vi phạm `NOT NULL` |
| `23514` | `check_violation` | Vi phạm `CHECK` |
| `23503` | `foreign_key_violation` | Vi phạm khóa ngoại |

Không nên bắt tất cả exception database và trả cùng thông báo “email đã tồn tại”. Ví dụ `23502` nghĩa là thiếu giá trị bắt buộc, còn `23505` nghĩa là tổ hợp khóa đã được sử dụng.

### 14.2. Ví dụ xử lý JDBC

Trong Java, bắt mã SQLSTATE thay vì phụ thuộc hoàn toàn vào chuỗi thông báo có thể đổi theo locale hoặc phiên bản:

```java
import java.sql.SQLException;

public class UniqueErrorHandler {
    public static void handleWriteError(SQLException e)
            throws SQLException {
        if ("23505".equals(e.getSQLState())) {
            // Chuyển sang lỗi nghiệp vụ phù hợp
            // hoặc trả HTTP 409 tùy contract API.
            throw new IllegalStateException(
                "Khóa nghiệp vụ đã tồn tại",
                e
            );
        }
        throw e;
    }
}
```

Trong hệ thống có nhiều unique constraints, mã `23505` chỉ cho biết **có một vi phạm duy nhất**, không nói chắc là cột email. Nếu cần trả lỗi riêng cho từng ràng buộc, hãy lấy tên constraint từ thông tin lỗi có cấu trúc do driver cung cấp khi phù hợp, thay vì parse câu chữ trong thông báo.

### 14.3. Khi nào ON CONFLICT phù hợp?

`ON CONFLICT DO UPDATE` hữu ích khi nghiệp vụ thật sự muốn “ghi đè/cập nhật bản ghi có cùng khóa”. `ON CONFLICT DO NOTHING` phù hợp khi một thao tác lặp lại cần bỏ qua insert trùng. Còn nếu hai request đại diện hai thực thể khác nhau nhưng trùng mã, hành vi đúng có thể là **trả lỗi** để người dùng sửa dữ liệu.

Việc chọn `NULLS NOT DISTINCT` và chọn cách xử lý conflict là hai quyết định liên quan nhưng **không đồng nhất**.

## 15. UNIQUE, CHECK và NULL: những quy tắc ba giá trị

Không chỉ `UNIQUE` có chi tiết liên quan `NULL`. `CHECK` cũng có điểm cần chú ý: nó thường chấp nhận biểu thức trả `true` **hoặc `unknown/NULL`**, và chỉ bác bỏ khi biểu thức đánh giá thành `false`.

Ví dụ:

```sql
CREATE TABLE null_unique_lab.optional_codes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_code UNIQUE (code)
);
```

`CHECK (code <> '')` **không cấm code NULL**, vì `NULL <> ''` cho kết quả unknown. `UNIQUE (code)` mặc định còn cho phép **nhiều `NULL`**.

Nếu muốn code bắt buộc:

```sql
CREATE TABLE null_unique_lab.required_codes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT NOT NULL,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_required_code UNIQUE (code)
);
```

Nếu muốn code có thể thiếu nhưng chỉ một bản ghi được thiếu:

```sql
CREATE TABLE null_unique_lab.one_optional_code (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code TEXT,
    CONSTRAINT chk_code_nonempty CHECK (code <> ''),
    CONSTRAINT uq_one_optional_code
        UNIQUE NULLS NOT DISTINCT (code)
);
```

Đừng cố dùng một constraint để diễn đạt ba quy tắc khác nhau: **bắt buộc**, **đúng định dạng** và **không trùng**. Việc tách `NOT NULL`, `CHECK` và `UNIQUE` giúp bảng phản ánh nghiệp vụ rõ ràng hơn.

## 16. NULL, chuỗi rỗng và giá trị “chưa biết”

Các đầu vào sau không tương đương:

```sql
SELECT
    NULL::TEXT IS NULL AS la_null,
    ''::TEXT IS NULL AS empty_co_phai_null,
    ''::TEXT = ''::TEXT AS hai_chuoi_rong_bang_nhau;
```

Kết quả là `true`, `false`, `true`.

Trong một unique constraint, hai chuỗi rỗng `''` **được xem là trùng nhau**, bởi chúng là giá trị xác định bằng nhau. Vì vậy:

- `UNIQUE (email)` có thể chứa nhiều `NULL`.
- Nhưng chỉ có thể chứa **một `''`** theo quy tắc so sánh thông thường.
- `UNIQUE NULLS NOT DISTINCT (email)` có thể chứa tối đa một `NULL` **và** tối đa một `''`, vì đây là **hai khóa khác nhau**.

Nếu ứng dụng có chính sách “chuỗi rỗng đồng nghĩa với chưa cung cấp”, cần chuẩn hóa đầu vào **có chủ đích**; không mặc định PostgreSQL sẽ tự đổi `''` thành `NULL`.

### 16.1. Chuẩn hóa email và các giá trị định danh

Ví dụ hai chuỗi:

```text
Alice@Example.Test
alice@example.test
```

có thể cần được coi là cùng email theo quy tắc đăng nhập của ứng dụng; tuy nhiên `UNIQUE (email)` với `TEXT` và collation thông thường không tự bảo đảm quy tắc không phân biệt chữ hoa/thường.

Có thể cần normalizing ở ứng dụng hoặc một expression index trên `lower(email)`. Nhưng cách chuẩn hóa email cũng có chi tiết riêng theo giao thức, Unicode và nhà cung cấp; không dùng `lower()` một cách mù quáng nếu yêu cầu chính xác.

**`NULLS NOT DISTINCT` chỉ giải quyết cách so sánh NULL trong unique key**, không giải quyết case-insensitive uniqueness, ký tự có dấu, khoảng trắng hay Unicode normalization.

## 17. UNIQUE và partitioned tables

Nếu bảng dùng **declarative partitioning**, có ràng buộc riêng với `PRIMARY KEY` và `UNIQUE` được khai báo ở **bảng partitioned cha**: thông thường các cột partition key cần nằm trong khóa unique/primary key theo yêu cầu của PostgreSQL.

Ví dụ ý tưởng:

```sql
CREATE TABLE null_unique_lab.orders_partitioned (
    tenant_id INTEGER NOT NULL,
    created_on DATE NOT NULL,
    external_ref TEXT,
    payload TEXT
) PARTITION BY RANGE (created_on);
```

Một unique constraint trên bảng partitioned cha chỉ có `(tenant_id, external_ref)` có thể **không hợp lệ** vì thiếu partition key `created_on`. Khi cần unique trên bảng partitioned, thiết kế khóa có chứa partition key phù hợp và kiểm tra yêu cầu của phiên bản PostgreSQL/loại phân vùng.

Ví dụ có thể dùng khóa gồm:

```sql
-- Minh họa một khóa gồm partition key; chỉ áp dụng
-- khi quy tắc nghiệp vụ là unique trong từng ngày:
ALTER TABLE null_unique_lab.orders_partitioned
ADD CONSTRAINT uq_orders_partitioned
UNIQUE NULLS NOT DISTINCT (created_on, tenant_id, external_ref);
```

Ràng buộc này nói rằng **trong cùng ngày**, mỗi tenant chỉ có một tổ hợp external_ref (kể cả `NULL`). Nó **không bảo đảm** cùng external_ref là duy nhất trên **mọi ngày**. Nếu nghiệp vụ đòi global uniqueness vượt ranh giới partition key, cần thiết kế khác thay vì tuyên bố partitioned constraint có thể làm điều ấy tự động.

## 18. Hiệu năng: NULLS NOT DISTINCT có làm index nhanh hơn?

`UNIQUE NULLS NOT DISTINCT` trước hết là **ràng buộc toàn vẹn dữ liệu**, không phải một công tắc tối ưu tốc độ.

### 18.1. Chi phí duy trì uniqueness

Mỗi `INSERT`/`UPDATE` liên quan đến các cột được index phải được kiểm tra theo quy tắc unique. Với dữ liệu lớn và nhiều giao dịch đồng thời, cần dự trù:

- I/O và dung lượng của index.
- Thời gian kiểm tra khóa, có thể phải chờ transaction khác khi cạnh tranh.
- Chi phí ghi WAL cho thay đổi bảng/index.
- Tác động của nhiều index trùng ý nghĩa.
- Thời gian xây index hoặc kiểm tra constraint khi migration.

Việc chọn `NULLS NOT DISTINCT` vì đúng nghiệp vụ quan trọng hơn việc tìm lợi ích hiệu năng không được đo.

### 18.2. Index có NULL vẫn được PostgreSQL quản lý

Đừng hiểu “UNIQUE mặc định bỏ qua sự trùng nhau của NULL” là index **không lưu entry cho NULL**. Một unique B-tree index thông thường vẫn có các quy tắc lưu/index NULL; sự khác biệt là **cách đánh giá trùng để bác bỏ dòng mới**.

Nếu muốn loại một phần bản ghi khỏi index, hãy cân nhắc **partial index `WHERE ...`** và hiểu phạm vi của nó. Không dùng `NULLS NOT DISTINCT` thay thế partial-index predicate.

### 18.3. Kiểm tra EXPLAIN khi cần

```sql
EXPLAIN
SELECT id, tenant_id, external_code, description
FROM null_unique_lab.tenant_refs_strict
WHERE tenant_id = 10
  AND external_code IS NULL;
```

Trên bảng lab nhỏ, PostgreSQL có thể chọn sequential scan dù có unique index, vì quét vài hàng rẻ hơn truy cập index. Kế hoạch này không cho thấy index sai.

Với hệ thống thật, dùng `EXPLAIN (ANALYZE, BUFFERS)` trên truy vấn đọc đại diện, cân nhắc chi phí chạy truy vấn và khối lượng dữ liệu. Việc định nghĩa uniqueness **không bảo đảm** mọi truy vấn tự động có index scan.

## 19. Dọn dẹp dữ liệu thực hành

Khi kết thúc, chỉ xóa các bảng demo nếu bạn chắc chắn đang ở database/schema thực hành và không cần giữ dữ liệu:

```sql
-- Các lệnh xóa là tùy chọn, hãy chạy riêng sau khi xác nhận.
-- DROP TABLE IF EXISTS null_unique_lab.orders_partitioned;
-- DROP TABLE IF EXISTS null_unique_lab.deferred_demo;
-- DROP TABLE IF EXISTS null_unique_lab.active_slots;
-- DROP TABLE IF EXISTS null_unique_lab.active_emails;
-- DROP TABLE IF EXISTS null_unique_lab.aliases_by_index;
-- DROP TABLE IF EXISTS null_unique_lab.login_aliases;
-- DROP TABLE IF EXISTS null_unique_lab.legacy_tenant_refs;
-- DROP TABLE IF EXISTS null_unique_lab.optional_codes;
-- DROP TABLE IF EXISTS null_unique_lab.required_codes;
-- DROP TABLE IF EXISTS null_unique_lab.one_optional_code;
-- DROP TABLE IF EXISTS null_unique_lab.sample_not_null;
-- DROP TABLE IF EXISTS null_unique_lab.sample_one_null;
-- DROP TABLE IF EXISTS null_unique_lab.optional_pairs;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_required;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_strict;
-- DROP TABLE IF EXISTS null_unique_lab.tenant_refs_default;
-- DROP TABLE IF EXISTS null_unique_lab.users_explicit_default;
-- DROP TABLE IF EXISTS null_unique_lab.users_strict;
-- DROP TABLE IF EXISTS null_unique_lab.users_default;
```

Không dùng `DROP SCHEMA ... CASCADE` như một bước “dọn nhanh” trong database dùng chung: nó có thể xóa các đối tượng không thuộc bài thực hành nếu schema đã được người khác sử dụng.

## 20. Những nhầm lẫn thường gặp

**1. “UNIQUE luôn cấm hai NULL.”** Sai. `UNIQUE` mặc định PostgreSQL cho phép nhiều `NULL` ở khóa một cột.

**2. “Hai NULL luôn bằng nhau trong SQL.”** Sai. `NULL = NULL` cho unknown; `IS NOT DISTINCT FROM` mới trả true khi cả hai NULL.

**3. “NULLS NOT DISTINCT là cách viết khác của NOT NULL.”** Sai. `NULLS NOT DISTINCT` vẫn cho phép một `NULL` theo khóa duy nhất; `NOT NULL` cấm mọi `NULL`.

**4. “NULLS NOT DISTINCT là thiết lập toàn database.”** Sai. Đây là thuộc tính của từng unique constraint/index.

**5. “UNIQUE NULLS NOT DISTINCT (tenant_id, ref) nghĩa là chỉ một NULL cho toàn bảng.”** Sai nếu tenant khác nhau. Nó bảo vệ tổ hợp khóa; mỗi tenant có thể có một `ref NULL`.

**6. “Nếu bất kỳ cột khóa ghép NULL thì mọi hàng khác có NULL đều trùng.”** Sai. Tất cả thành phần khóa tương ứng phải không phân biệt; các phần không NULL vẫn phải khớp.

**7. “UNIQUE NULLS NOT DISTINCT dùng được trong mọi PostgreSQL.”** Sai. Cần PostgreSQL **15+**.

**8. “Chỉ đổi UNIQUE sang NULLS NOT DISTINCT là được, dù dữ liệu đang có nhiều NULL.”** Sai. Phải xử lý những tổ hợp trùng theo quy tắc mới.

**9. “ON CONFLICT DO UPDATE luôn bắt được hai lần INSERT NULL.”** Sai với ràng buộc `UNIQUE` mặc định; hai `NULL` có thể không conflict.

**10. “COUNT(DISTINCT code) giúp phát hiện số bản ghi code NULL trùng.”** Sai. `COUNT(DISTINCT code)` bỏ qua `NULL`.

**11. “GROUP BY NULL và UNIQUE NULL phải dùng cùng quy tắc.”** Sai. `GROUP BY` có thể gom các `NULL` vào cùng nhóm dù `UNIQUE` mặc định cho phép nhiều hàng NULL.

**12. “Một unique index luôn là table constraint.”** Sai. Partial/expression unique index có thể bảo vệ quy tắc khác và không thể gắn như constraint thường theo `USING INDEX`.

**13. “Index trên (tenant_id, code) giống index trên (code).”** Sai. Phạm vi duy nhất của khóa ghép khác với phạm vi duy nhất toàn bảng của một cột.

**14. “Trigger SELECT EXISTS là đủ chống chèn trùng đồng thời.”** Không an toàn nếu không có thiết kế khóa/concurrency đúng.

**15. “Một unique violation phải có nghĩa email trùng.”** Không. Cần xác định ràng buộc/index gây lỗi trong schema có nhiều khóa.

**16. “NULL và chuỗi rỗng giống nhau.”** Sai trong PostgreSQL. Hai chuỗi rỗng có thể trùng khóa, còn hai NULL tùy distinctness.

**17. “NOT NULL + UNIQUE và NULLS NOT DISTINCT khác nhau cả khi cột không bao giờ NULL.”** Về tình huống có dữ liệu không NULL hợp lệ, ngữ nghĩa bảo vệ trùng của chúng tương đương; khác biệt nằm ở việc chấp nhận hay cấm NULL.

**18. “Thêm unique index concurrently chắc chắn không tạo ảnh hưởng và luôn thành công.”** Sai. Nó tiêu thụ tài nguyên, có ràng buộc về transaction và có thể để lại index invalid khi thất bại.

**19. “Đặt NULLS NOT DISTINCT sẽ giải quyết email khác chữ hoa/thường.”** Sai. Đó là vấn đề chuẩn hóa/collation/expression index khác.

**20. “Unique constraint ở partitioned parent mặc nhiên bảo vệ mọi khóa nghiệp vụ xuyên partition.”** Không. Phải hiểu yêu cầu chứa partition key và phạm vi uniqueness thực tế.

## 21. Bài tập thực hành có đáp án

### Bài 1 — Nhiều NULL có được lưu không?

Bảng:

```sql
CREATE TABLE null_unique_lab.exercise_1 (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT UNIQUE
);
```

**Hỏi:** Chèn ba hàng `email=NULL` và một hàng `email='a@example.test'` có thành công không?

**Đáp án:** Có, nếu không vi phạm constraint khác. `UNIQUE` mặc định xem các `NULL` là phân biệt; email khác `NULL` vẫn cần duy nhất.

### Bài 2 — Một NULL toàn bảng

**Yêu cầu:** tạo bảng với cột `coupon_code` có thể để `NULL`, nhưng chỉ cho phép một hàng có `coupon_code IS NULL`; mọi giá trị không NULL cũng phải duy nhất.

**Đáp án PostgreSQL 15+:**

```sql
CREATE TABLE null_unique_lab.exercise_2 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    coupon_code TEXT,
    CONSTRAINT uq_exercise_2_coupon
        UNIQUE NULLS NOT DISTINCT (coupon_code)
);
```

Không thêm `NOT NULL` vì đề bài vẫn cho phép **một** hàng NULL.

### Bài 3 — Một NULL cho mỗi tenant

**Yêu cầu:** mỗi tenant có mã dự phòng `fallback_code` tùy chọn, nhưng chỉ một hàng thiếu mã trong từng tenant.

**Đáp án:**

```sql
CREATE TABLE null_unique_lab.exercise_3 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    fallback_code TEXT,
    CONSTRAINT uq_exercise_3
        UNIQUE NULLS NOT DISTINCT (tenant_id, fallback_code)
);
```

`(1,NULL)` và `(2,NULL)` được phép cùng tồn tại; thêm `(1,NULL)` lần hai thì bị từ chối.

### Bài 4 — Phân biệt hành vi trên khóa ghép

Giả sử bảng đã có `(tenant_id, external_code) = (7, NULL)`.

| Hàng muốn chèn | UNIQUE mặc định | NULLS NOT DISTINCT |
|---|---|---|
| `(7, NULL)` | Cho phép | Từ chối |
| `(8, NULL)` | Cho phép | Cho phép |
| `(7, 'X')` | Cho phép | Cho phép |
| `(7, 'X')` lần thứ hai | Từ chối | Từ chối |

**Giải thích:** `tenant_id` là thành phần của khóa. Chỉ cùng tenant và cùng mã (kể cả hai NULL khi chọn NULLS NOT DISTINCT) mới là một tổ hợp trùng.

### Bài 5 — Tìm dữ liệu cần làm sạch trước migration

**Yêu cầu:** liệt kê những tổ hợp `tenant_id, external_code` xuất hiện trên một lần.

**Đáp án:**

```sql
SELECT tenant_id, external_code, COUNT(*) AS so_luong
FROM null_unique_lab.tenant_refs_default
GROUP BY tenant_id, external_code
HAVING COUNT(*) > 1;
```

`GROUP BY` nhóm `NULL` cùng nhau nên đây là cách phát hiện những tổ hợp sẽ xung đột với `NULLS NOT DISTINCT`.

### Bài 6 — ON CONFLICT làm gì với NULL?

**Hỏi:** Bảng có `UNIQUE (code)` mặc định và một hàng `code=NULL`. Lệnh `INSERT ... VALUES(NULL) ON CONFLICT (code) DO NOTHING` có bỏ qua insert không?

**Đáp án:** Không nhất thiết; với unique default, hai `NULL` không xung đột nên có thể **chèn một hàng nữa**. Nếu dùng unique `NULLS NOT DISTINCT (code)` ở PostgreSQL 15+, `NULL` thứ hai tạo conflict và `DO NOTHING` sẽ bỏ qua.

### Bài 7 — Khi nào không dùng NULLS NOT DISTINCT?

Một hệ thống có hàng nghìn người dùng chưa cung cấp email. Email không NULL phải duy nhất, nhưng người dùng được phép đăng ký trước rồi cập nhật email sau.

**Đáp án:** `UNIQUE (email)` mặc định phù hợp hơn. `NULLS NOT DISTINCT` sẽ chỉ cho phép một tài khoản có email NULL trên toàn bảng, trái nghiệp vụ.

### Bài 8 — Workaround trước PostgreSQL 15

**Yêu cầu:** `tenant_id NOT NULL`, `external_code` nullable; trong mỗi tenant chỉ có một hàng NULL, mã không NULL không được trùng. PostgreSQL 14.

**Đáp án:** Kết hợp:

```sql
CREATE TABLE null_unique_lab.exercise_8 (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_code TEXT,
    UNIQUE (tenant_id, external_code)
);

CREATE UNIQUE INDEX uq_exercise_8_one_null
ON null_unique_lab.exercise_8 (tenant_id)
WHERE external_code IS NULL;
```

Constraint đầu bảo vệ mã xác định; partial unique index giới hạn một NULL trong từng tenant. Nếu các cột khác cũng nullable, cần thiết kế thêm quy tắc phù hợp.

### Bài 9 — Kiểm tra bằng pg_catalog

**Yêu cầu:** trên PostgreSQL 15+, tìm những unique index dùng `NULLS NOT DISTINCT` trong schema lab.

**Đáp án:**

```sql
SELECT
    ns.nspname AS schema_name,
    rel.relname AS table_name,
    idx.indexrelid::regclass AS index_name,
    pg_get_indexdef(idx.indexrelid) AS definition
FROM pg_index AS idx
JOIN pg_class AS rel
    ON rel.oid = idx.indrelid
JOIN pg_namespace AS ns
    ON ns.oid = rel.relnamespace
WHERE ns.nspname = 'null_unique_lab'
  AND idx.indisunique
  AND idx.indnullsnotdistinct
ORDER BY table_name, index_name;
```

Trên PostgreSQL 14, cột `indnullsnotdistinct` chưa tồn tại nên truy vấn không chạy được nguyên dạng.

### Bài 10 — NULLS NOT DISTINCT có làm NULL = NULL thành true?

**Đáp án:** Không. Chạy:

```sql
SELECT
    NULL = NULL AS so_sanh_thuong,
    NULL IS NOT DISTINCT FROM NULL AS so_sanh_null_safe;
```

Kết quả `NULL` và `true` vẫn như cũ, bất kể các bảng đang có những unique constraints nào.

### Bài 11 — Nếu muốn cấm NULL hoàn toàn?

Một mã hợp đồng bắt buộc có giá trị và duy nhất trong toàn bảng.

**Đáp án:** `contract_code TEXT NOT NULL UNIQUE`. Dùng `UNIQUE NULLS NOT DISTINCT` không đủ vì vẫn cho phép một `NULL`.

### Bài 12 — Một bản ghi đang hoạt động cho mỗi khóa

Một bảng chứa bản ghi đang hoạt động và bản ghi lưu trữ (`archived_at IS NOT NULL`); yêu cầu mỗi tenant chỉ một mã trùng, kể cả NULL, **trong số bản ghi đang hoạt động**.

**Đáp án PostgreSQL 15+:**

```sql
CREATE UNIQUE INDEX uq_exercise_active
ON null_unique_lab.active_slots (tenant_id, slot_code)
NULLS NOT DISTINCT
WHERE archived_at IS NULL;
```

*Lưu ý:* Bài lab ở mục 7 đã tạo index `uq_active_slots` bảo vệ cùng quy tắc; câu trên là **đáp án cú pháp minh họa**, không cần thực thi lại trên bảng đó trừ khi đã gỡ index cũ trong môi trường thử nghiệm.

## 22. Quy trình quyết định khi thiết kế một ràng buộc duy nhất

Khi nhận yêu cầu “các mã không được trùng”, hãy đi theo trình tự:

1. **Xác định khóa nghiệp vụ:** một cột hay một tổ hợp như `(tenant_id, external_code)`?
2. **Xác định phạm vi:** duy nhất toàn bảng, trong từng tenant, từng ngày, hay chỉ các hàng đang hoạt động?
3. **Xác định NULL:** được cấm, được phép xuất hiện nhiều lần, hay chỉ một lần trong mỗi phạm vi?
4. **Chọn cấu trúc:** `NOT NULL UNIQUE` nếu cấm NULL; `UNIQUE` mặc định nếu nhiều NULL hợp lệ; `UNIQUE NULLS NOT DISTINCT` khi NULL phải được xem là trùng.
5. **Nếu có điều kiện hàng:** xem xét partial unique index với `WHERE`.
6. **Nếu khóa có nhiều cột nullable:** xác nhận toàn bộ các tổ hợp NULL, không chỉ một trường hợp đơn giản.
7. **Nếu cần upsert:** quyết định rõ conflict target và cách xử lý `DO UPDATE`/`DO NOTHING` khi NULL.
8. **Nếu bảng đã có dữ liệu:** truy vấn `GROUP BY ... HAVING COUNT(*) > 1`, xử lý trùng theo nghiệp vụ trước khi thêm constraint mới.
9. **Nếu bảng lớn:** đánh giá `CREATE UNIQUE INDEX CONCURRENTLY`, khóa, I/O, chỉ mục invalid và dependency khi gắn constraint.
10. **Nếu cần hỗ trợ PostgreSQL 14 trở xuống:** dùng workaround được thiết kế cho từng phạm vi hoặc nâng phiên bản, không dùng cú pháp PostgreSQL 15+ trên server cũ.
11. **Nếu bảng partitioned:** xem yêu cầu chứa partition key và phạm vi uniqueness thực tế.
12. **Sau triển khai:** kiểm thử chèn trùng, lỗi `23505`, kết nối đồng thời, upsert và catalog index/constraint.

## 23. Tổng kết

Trong PostgreSQL, **`UNIQUE` mặc định coi các giá trị `NULL` là phân biệt khi kiểm tra tính duy nhất**, nên một cột nullable vẫn có thể có nhiều hàng `NULL`. Từ **PostgreSQL 15**, **`UNIQUE NULLS NOT DISTINCT`** và **`CREATE UNIQUE INDEX ... NULLS NOT DISTINCT`** cho phép coi hai `NULL` là **không phân biệt**, từ đó chặn những tổ hợp khóa giống nhau ngay cả khi có thành phần thiếu giá trị.

Ba quyết định cần nhớ:

- **Bắt buộc có giá trị:** chọn `NOT NULL` và thêm `UNIQUE` nếu cần tính duy nhất.
- **Cho phép nhiều bản ghi chưa có giá trị:** `UNIQUE` mặc định thường phù hợp.
- **Chỉ một tổ hợp có NULL trong một phạm vi:** cân nhắc `NULLS NOT DISTINCT`, đặc biệt với khóa ghép theo tenant hoặc các thực thể mặc định.

Điều chỉnh này chỉ tác động đến **ràng buộc/chỉ mục duy nhất được khai báo**, không thay đổi `NULL = NULL` hay mọi phép so sánh SQL. Khi áp dụng cho bảng đã có dữ liệu, hãy kiểm tra các tổ hợp trùng, hiểu `ON CONFLICT`, đánh giá khóa và chi phí migration, rồi kiểm thử với giao dịch đồng thời. **Một constraint đúng không phải chỉ là câu lệnh chạy được, mà phải diễn đạt đúng quy tắc nghiệp vụ khi dữ liệu có NULL.**

Tài liệu PostgreSQL chính thức để tra cứu:

- [Unique Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-UNIQUE-CONSTRAINTS).
- [CREATE TABLE](https://www.postgresql.org/docs/current/sql-createtable.html).
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).
- [INSERT và ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).
- [Indexes on Expressions / Partial Indexes](https://www.postgresql.org/docs/current/indexes-expressional.html), [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html).
