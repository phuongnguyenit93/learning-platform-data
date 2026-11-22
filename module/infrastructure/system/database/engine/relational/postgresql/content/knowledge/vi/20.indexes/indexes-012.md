# Chỉ mục duy nhất, NULL và ràng buộc dữ liệu

Một ứng dụng đăng ký người dùng cần ngăn hai tài khoản có cùng email. Một hệ thống nhiều khách hàng (*multi-tenant*) cần email chỉ duy nhất **trong từng tenant**. Một bảng lưu mã tham chiếu từ đối tác cho phép mã chưa được cung cấp (`NULL`), nhưng mỗi tenant chỉ được phép có một bản ghi thiếu mã. Một bảng dùng **soft delete** phải cho phép tạo lại email sau khi tài khoản cũ đã bị xóa mềm, đồng thời không cho phép hai tài khoản đang hoạt động trùng email.

Tất cả đều liên quan tới **tính duy nhất** (*uniqueness*), nhưng không thể giải quyết chính xác bằng một mẫu `UNIQUE` áp dụng máy móc.

Trong PostgreSQL:

- **`UNIQUE` constraint** bảo vệ một bất biến về dữ liệu và được thực thi nhờ **unique B-tree index**.
- **Unique index** có thể được tạo trực tiếp, bao gồm những biến thể linh hoạt như **expression index** và **partial unique index** mà constraint thông thường không diễn đạt được.
- Mặc định, các giá trị **`NULL` được coi là phân biệt** khi kiểm tra tính duy nhất; vì thế nhiều hàng có thể có cùng tổ hợp khóa với `NULL`.
- Từ **PostgreSQL 15**, `NULLS NOT DISTINCT` cho phép coi `NULL` như bằng nhau trong kiểm tra unique.
- **`PRIMARY KEY`** không chỉ duy nhất mà còn yêu cầu **`NOT NULL`** với mọi cột khóa.
- Kiểm tra uniqueness diễn ra an toàn dưới **concurrency**; một `SELECT` không thấy bản ghi không chứng minh transaction khác chưa chèn khóa ấy.
- **`ON CONFLICT`** hỗ trợ xử lý trùng khóa một cách nguyên tử nhưng có giới hạn quan trọng với **deferrable constraints** và các loại index.

Bài học đi từ cú pháp và ngữ nghĩa đến thiết kế dữ liệu thật, migration trên bảng lớn, xử lý trùng lặp, quan sát catalog, Java/JDBC và bài tập.

> **Môi trường:** Bài sử dụng PostgreSQL hiện đại. Các ví dụ có `NULLS NOT DISTINCT` cần **PostgreSQL 15 trở lên**. Chỉ chạy lệnh tạo/xóa bảng, index, constraint hoặc làm sạch dữ liệu trong **database lab**. Trên production phải kiểm tra phiên bản server, dữ liệu hiện tại, kế hoạch khóa, tải ghi và chính sách triển khai migration trước khi thay đổi tính duy nhất.

## 1. Chỉ mục duy nhất giải quyết vấn đề gì?

Giả sử bảng lưu khách hàng:

| account_id | tenant_id | email |
|---:|---:|---|
| 1 | 10 | an@example.test |
| 2 | 10 | binh@example.test |
| 3 | 20 | an@example.test |

Nếu yêu cầu “**mỗi tenant không có hai tài khoản cùng email**”, dữ liệu trên hợp lệ: email của An xuất hiện ở **tenant khác nhau**, không vi phạm khóa kết hợp.

Nhưng thêm:

| account_id | tenant_id | email |
|---:|---:|---|
| 4 | 10 | an@example.test |

sẽ vi phạm bất biến.

Ở tầng PostgreSQL, ràng buộc:

```sql
UNIQUE (tenant_id, email)
```

buộc hệ thống phát hiện và từ chối những thao tác tạo ra hai hàng có cùng tổ hợp `(tenant_id, email)` theo quy tắc equality, collation và NULL được dùng.

### Tại sao không chỉ SELECT trước khi INSERT?

```sql
SELECT 1
FROM accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';

-- Không thấy hàng, sau đó:
INSERT INTO accounts (...);
```

Hai transaction có thể **cùng SELECT thấy chưa tồn tại**, rồi cùng INSERT. Đây là một race condition kinh điển:

```text
Transaction A                  Transaction B
-------------------------      -------------------------
SELECT key => chưa có
                               SELECT key => chưa có
INSERT key
                               INSERT key
COMMIT
                               COMMIT ?
```

Nếu không có ràng buộc unique ở database, cả hai hàng có thể được lưu. Với unique constraint/index, PostgreSQL kiểm soát xung đột ở tầng lưu trữ và transaction để **không cho hai bản ghi vi phạm cùng được commit**.

**Đừng coi kiểm tra ở application là thay thế ràng buộc dữ liệu.** Validation trước khi ghi giúp trả lỗi dễ hiểu, nhưng unique constraint mới là lớp bảo vệ cuối cùng trước race.

## 2. UNIQUE constraint và UNIQUE index: giống và khác

Hai cách thường thấy:

```sql
-- Cách 1: khai báo constraint ở schema bảng.
CREATE TABLE accounts_example (
    account_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    CONSTRAINT uq_accounts_tenant_email
        UNIQUE (tenant_id, email)
);
```

```sql
-- Cách 2: tạo unique index trực tiếp.
CREATE UNIQUE INDEX ux_accounts_tenant_email
ON accounts_example (tenant_id, email);
```

Hai đoạn là **ví dụ độc lập**; không cần tạo cả hai trên cùng một bảng vì chúng bảo vệ cùng tổ hợp khóa và thường gây trùng lặp index.

| Tiêu chí | `UNIQUE` constraint | `CREATE UNIQUE INDEX` |
|---|---|---|
| Mục đích biểu đạt | Bất biến dữ liệu trong schema quan hệ. | Cấu trúc chỉ mục thực thi tính duy nhất. |
| Cơ chế thực thi | Được hỗ trợ bởi unique index. | Chính unique index bảo vệ uniqueness. |
| Khóa gồm nhiều cột | Có. | Có. |
| `NULLS NOT DISTINCT` (PostgreSQL 15+) | Có. | Có. |
| Expression như `lower(email)` | Không khai báo trực tiếp expression trong danh sách cột constraint. | Có. |
| Predicate `WHERE deleted_at IS NULL` | Không có partial unique constraint trực tiếp. | Có partial unique index. |
| `DEFERRABLE` | Có với constraint phù hợp. | Index tạo trực tiếp không phải một deferrable constraint. |
| Foreign key tham chiếu | Có thể là khóa tham chiếu nếu đáp ứng điều kiện. | Non-partial unique index trên cột phù hợp cũng có thể làm khóa được tham chiếu. |
| Tạo `CONCURRENTLY` | Không trực tiếp trên `ALTER TABLE ... ADD UNIQUE`. | `CREATE UNIQUE INDEX CONCURRENTLY` được hỗ trợ. |

**Cách chọn:** ưu tiên `UNIQUE` constraint khi muốn nêu quy tắc dữ liệu trên **những cột thực**. Dùng unique index trực tiếp khi cần **biểu thức**, **điều kiện lọc**, hoặc chiến lược triển khai index online phù hợp.

### Một constraint UNIQUE thường đã có index

Khai báo:

```sql
CONSTRAINT uq_accounts_tenant_email UNIQUE (tenant_id, email)
```

thường đã tạo unique B-tree index tương ứng. Không tự tạo thêm:

```sql
CREATE UNIQUE INDEX ...
ON accounts (tenant_id, email);
```

nếu nó thực chất trùng công dụng. Index dư gây tốn dung lượng, WAL và chi phí INSERT/UPDATE/DELETE.

## 3. Chuẩn bị database lab

Tạo schema riêng:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_unique;
```

Tạo bảng tài khoản có khóa kết hợp duy nhất:

```sql
CREATE TABLE lesson_unique.accounts (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_accounts_tenant_email
        UNIQUE (tenant_id, email)
);
```

Thêm dữ liệu hợp lệ:

```sql
INSERT INTO lesson_unique.accounts (
    tenant_id, email, display_name
)
VALUES
    (10, 'an@example.test', 'An ở tenant 10'),
    (10, 'binh@example.test', 'Bình ở tenant 10'),
    (20, 'an@example.test', 'An ở tenant 20');
```

Kiểm tra:

```sql
SELECT
    account_id,
    tenant_id,
    email,
    display_name
FROM lesson_unique.accounts
ORDER BY tenant_id, email;
```

### Phát sinh lỗi unique_violation

```sql
INSERT INTO lesson_unique.accounts (
    tenant_id, email, display_name
)
VALUES (
    10, 'an@example.test', 'Tài khoản trùng'
);
```

PostgreSQL từ chối hàng mới, thường với:

```text
ERROR: duplicate key value violates unique constraint
       "uq_accounts_tenant_email"
DETAIL: Key (tenant_id, email)=(10, an@example.test)
        already exists.
SQLSTATE: 23505
```

**Lưu ý về transaction:** Nếu thực hiện câu lỗi trong `BEGIN ... COMMIT`, transaction có thể trở thành **aborted**, cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` hợp lệ trước khi chạy tiếp. Chạy các ví dụ tạo lỗi ở chế độ autocommit trong lab, hoặc chủ động quản lý rollback.

## 4. Một UNIQUE constraint có thể bao gồm nhiều cột

Ràng buộc:

```sql
UNIQUE (tenant_id, email)
```

đảm bảo **tổ hợp** là duy nhất, không bảo đảm từng cột riêng lẻ đều duy nhất.

| tenant_id | email | Hợp lệ? |
|---:|---|---|
| 10 | an@example.test | Hàng đầu tiên, hợp lệ. |
| 10 | binh@example.test | Hợp lệ vì email khác. |
| 20 | an@example.test | Hợp lệ vì tenant khác. |
| 10 | an@example.test | **Không hợp lệ** vì toàn bộ tổ hợp trùng. |

### Không đồng nghĩa hai UNIQUE đơn cột

```sql
UNIQUE (tenant_id),
UNIQUE (email)
```

khác hoàn toàn với:

```sql
UNIQUE (tenant_id, email)
```

Cách thứ nhất yêu cầu mỗi `tenant_id` xuất hiện tối đa một lần **và** mỗi email xuất hiện tối đa một lần toàn bảng — gần như luôn sai cho ứng dụng nhiều tài khoản trong từng tenant.

### Thứ tự cột có ảnh hưởng tới hiệu năng

Về tính duy nhất của **tổ hợp**, `UNIQUE (tenant_id, email)` và `UNIQUE (email, tenant_id)` bảo vệ cùng một tập cặp bằng nhau. Nhưng thứ tự cột trong **B-tree index** có thể ảnh hưởng tới khả năng khai thác index cho những truy vấn lọc/sắp xếp, chẳng hạn:

```sql
WHERE tenant_id = 10 AND email = ?
```

hoặc:

```sql
WHERE tenant_id = 10 ORDER BY email
```

Không thêm hai unique indexes đảo thứ tự chỉ vì cùng ràng buộc. Hãy chọn thiết kế từ workload và đo kế hoạch thực thi.

## 5. NULL trong SQL không phải giá trị thông thường

`NULL` biểu diễn **thiếu/không biết giá trị**, không phải chuỗi rỗng, số 0 hay một ký tự đặc biệt.

Các phép so sánh thông thường:

```sql
SELECT
    NULL = NULL AS equal_result,
    NULL <> NULL AS not_equal_result,
    NULL IS NULL AS is_null_result,
    NULL IS NOT NULL AS is_not_null_result;
```

Kết quả khái niệm:

| Biểu thức | Kết quả |
|---|---|
| `NULL = NULL` | SQL `NULL` (*unknown*). |
| `NULL <> NULL` | SQL `NULL` (*unknown*). |
| `NULL IS NULL` | `true`. |
| `NULL IS NOT NULL` | `false`. |

Khi muốn so sánh hai giá trị kể cả null theo nghĩa “không phân biệt null”:

```sql
SELECT
    NULL IS NOT DISTINCT FROM NULL AS same_null,
    NULL IS DISTINCT FROM 5 AS differs_from_five,
    5 IS NOT DISTINCT FROM 5 AS same_value;
```

Ba kết quả đều `true`.

**Không dùng `column = NULL` để lọc hàng thiếu giá trị.** Dùng `column IS NULL`.

### NULL và chuỗi rỗng

```sql
SELECT
    '' IS NULL AS empty_is_null,
    '' = '' AS empty_equals_empty;
```

Chuỗi rỗng là một **giá trị thực** với kiểu text. Nó có thể bị kiểm tra unique như một giá trị khác rỗng/null và có thể lặp hoặc không tùy khóa.

## 6. UNIQUE mặc định cho phép nhiều NULL

Đây là quy tắc dễ gây bất ngờ nhất của bài học.

```sql
CREATE TABLE lesson_unique.codes_default (
    id INTEGER PRIMARY KEY,
    optional_code TEXT UNIQUE
);
```

Thử:

```sql
INSERT INTO lesson_unique.codes_default(id, optional_code)
VALUES
    (1, NULL),
    (2, NULL),
    (3, 'CODE-A'),
    (4, 'CODE-B');
```

**Câu trên thành công** với unique semantics mặc định: có **hai hàng cùng `NULL`** trong cột `optional_code`.

Ngược lại:

```sql
INSERT INTO lesson_unique.codes_default(id, optional_code)
VALUES (5, 'CODE-A');
-- ERROR 23505 vì CODE-A đã tồn tại.
```

### Vì sao nhiều NULL được phép?

Theo ngữ nghĩa mặc định của PostgreSQL, các giá trị null trong unique index/constraint được coi là **khác biệt** (*NULLS DISTINCT*) cho mục đích kiểm tra tính duy nhất. Vì không biết hai giá trị thiếu đó có thực sự giống nhau hay không, database cho phép nhiều hàng null.

Đây là **ngữ nghĩa riêng của UNIQUE**, không có nghĩa PostgreSQL luôn coi null khác nhau trong mọi ngữ cảnh:

- `GROUP BY` thường gom các hàng có null vào cùng nhóm.
- `IS NOT DISTINCT FROM` coi hai null như không khác biệt.
- `UNIQUE` mặc định cho phép nhiều null.

Không suy diễn trực tiếp từ kết quả `GROUP BY` sang `UNIQUE`.

## 7. UNIQUE nhiều cột khi một thành phần là NULL

Tạo bảng:

```sql
CREATE TABLE lesson_unique.refs_default (
    ref_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_refs_default
        UNIQUE (tenant_id, external_ref)
);
```

Các hàng sau **được phép**:

```sql
INSERT INTO lesson_unique.refs_default(
    ref_id, tenant_id, external_ref
)
VALUES
    (1, 10, NULL),
    (2, 10, NULL),
    (3, 10, 'EXT-A'),
    (4, 20, 'EXT-A'),
    (5, 20, NULL);
```

Giải thích:

- Hai hàng `(10, NULL)` được phép dù tenant giống nhau.
- `(10,'EXT-A')` và `(20,'EXT-A')` được phép vì tenant khác.
- Một hàng `(10,'EXT-A')` **thứ hai** sẽ vi phạm unique.

### Quy tắc tổng quát

Với `UNIQUE (a,b)` mặc định, nếu một hoặc nhiều giá trị trong khóa là `NULL`, những hàng có tổ hợp đó có thể cùng tồn tại mà không bị coi là vi phạm như khi toàn bộ giá trị đều non-null và bằng nhau.

Đó là lý do quy tắc:

> “Mỗi tenant chỉ có tối đa một bản ghi có external_ref chưa biết”

**không được bảo vệ** bằng `UNIQUE(tenant_id, external_ref)` mặc định nếu `external_ref` nullable.

## 8. NULLS NOT DISTINCT từ PostgreSQL 15

PostgreSQL 15 giới thiệu khả năng lựa chọn:

```sql
UNIQUE NULLS NOT DISTINCT (column_name)
```

hoặc:

```sql
CREATE UNIQUE INDEX ...
ON some_table (column_name) NULLS NOT DISTINCT;
```

Với ngữ nghĩa này, hai giá trị null được xem là **không phân biệt** khi kiểm tra unique, tương tự ý nghĩa `IS NOT DISTINCT FROM` trên các thành phần khóa.

### Bảng một cột

```sql
CREATE TABLE lesson_unique.codes_strict (
    id INTEGER PRIMARY KEY,
    optional_code TEXT,
    CONSTRAINT uq_codes_strict
        UNIQUE NULLS NOT DISTINCT (optional_code)
);
```

Thêm hàng đầu:

```sql
INSERT INTO lesson_unique.codes_strict(id, optional_code)
VALUES (1, NULL);
```

Thêm hàng thứ hai với NULL:

```sql
INSERT INTO lesson_unique.codes_strict(id, optional_code)
VALUES (2, NULL);
-- ERROR 23505 trên PostgreSQL 15+.
```

Giờ **tối đa một hàng null** được cho phép trong toàn bảng đối với cột `optional_code`, nếu không có quy tắc/phạm vi khác.

### Không nhầm với NOT NULL

- `NOT NULL`: **không cho bất kỳ null nào**.
- `UNIQUE` mặc định: cho nhiều null, không cho giá trị non-null trùng.
- `UNIQUE NULLS NOT DISTINCT`: cho **tối đa một null** (với khóa một cột), không cho giá trị non-null trùng.

Ba lựa chọn phục vụ **ba bất biến dữ liệu khác nhau**.

## 9. NULLS NOT DISTINCT với khóa kết hợp

```sql
CREATE TABLE lesson_unique.refs_strict (
    ref_id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    external_ref TEXT,
    CONSTRAINT uq_refs_strict
        UNIQUE NULLS NOT DISTINCT (
            tenant_id,
            external_ref
        )
);
```

Đây là quy tắc: **mỗi cặp tenant và external_ref là duy nhất, kể cả khi external_ref null**.

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES
    (1, 10, NULL),
    (2, 20, NULL),
    (3, 10, 'EXT-A'),
    (4, 20, 'EXT-A');
```

Tất cả hợp lệ. Mỗi tenant hiện có một hàng null và một hàng `EXT-A`.

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (5, 10, NULL);
-- ERROR 23505: (10, NULL) đã tồn tại.
```

Trong khi:

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (6, 30, NULL);
-- Thành công vì tenant_id=30 khác.
```

**Không phải cả bảng chỉ có thể có một NULL** khi unique key gồm nhiều cột. Ràng buộc xét **toàn bộ tổ hợp khóa**, nên `(10,NULL)` và `(20,NULL)` vẫn khác nhau nhờ tenant.

### Nhiều cột nullable

Với `UNIQUE NULLS NOT DISTINCT(a,b,c)`, hai hàng vi phạm khi **mỗi thành phần tương ứng không phân biệt nhau**, bao gồm cả trường hợp null ở cùng vị trí. Nếu chỉ một thành phần non-null khác nhau, hai tổ hợp vẫn khác.

## 10. Tạo unique index trực tiếp với NULLS NOT DISTINCT

Thay vì constraint, có thể viết:

```sql
CREATE TABLE lesson_unique.codes_indexed (
    id BIGINT PRIMARY KEY,
    optional_code TEXT
);

CREATE UNIQUE INDEX ux_codes_indexed_not_distinct
ON lesson_unique.codes_indexed (optional_code)
NULLS NOT DISTINCT;
```

Index này bảo vệ quy tắc **không có hai hàng có cùng optional_code, kể cả NULL**.

### Khi nào chọn constraint?

Nếu đây là một bất biến đơn giản ở mô hình dữ liệu, thích hợp đặt:

```sql
CONSTRAINT uq_optional_code
UNIQUE NULLS NOT DISTINCT (optional_code)
```

trong định nghĩa bảng.

Nếu index được tạo trực tiếp để hỗ trợ migration online hoặc cần expression/partial predicate, chọn cú pháp index tương ứng. Với index unique đơn giản, vẫn có khả năng đính kèm thành constraint sau khi tạo xong, theo những điều kiện được PostgreSQL hỗ trợ.

### Phiên bản cũ hơn PostgreSQL 15

Trước PostgreSQL 15, cú pháp `NULLS NOT DISTINCT` không được hỗ trợ. Không copy lệnh này vào server cũ rồi nghĩ PostgreSQL sẽ tự bỏ qua tùy chọn.

Kiểm tra:

```sql
SHOW server_version;

SELECT current_setting('server_version_num')::integer
       AS server_version_num;
```

Nếu cần quy tắc “tối đa một NULL” ở phiên bản cũ, phải thiết kế giải pháp thay thế như partial unique indexes trên từng phạm vi thích hợp, hoặc thay đổi mô hình dữ liệu.

## 11. Mẹo cũ: unique partial index chỉ cho một NULL

Trên PostgreSQL cũ hơn 15, một cột `code` có thể được bảo vệ bằng:

```sql
CREATE TABLE lesson_unique.legacy_codes (
    id BIGINT PRIMARY KEY,
    code TEXT
);

-- Các code non-null phải duy nhất.
CREATE UNIQUE INDEX ux_legacy_code_nonnull
ON lesson_unique.legacy_codes (code)
WHERE code IS NOT NULL;

-- Chỉ một hàng được phép có code IS NULL.
CREATE UNIQUE INDEX ux_legacy_code_null
ON lesson_unique.legacy_codes ((true))
WHERE code IS NULL;
```

Vì những hàng `code IS NULL` đều được index với khóa biểu thức hằng `true`, unique index thứ hai không cho có hai hàng trong tập này.

### Ưu và nhược

- Biểu đạt được quy tắc trên PostgreSQL cũ.
- Nhưng cần **hai indexes** và logic tinh tế hơn.
- Dễ gặp sai sót khi mở rộng thành nhiều cột/tenant.
- Không phải một `UNIQUE NULLS NOT DISTINCT` constraint thông thường.
- Migration và `ON CONFLICT` cần xem xét kỹ khả năng chọn arbiter index.

Trên PostgreSQL 15+, `NULLS NOT DISTINCT` thường là lựa chọn trực tiếp, rõ ràng hơn cho trường hợp này.

## 12. PRIMARY KEY khác UNIQUE như thế nào?

`PRIMARY KEY` đòi hỏi các cột tham gia khóa **không null** và **duy nhất**. Một bảng chỉ có **một primary key constraint** (có thể gồm nhiều cột), nhưng có thể có nhiều unique constraints.

```sql
CREATE TABLE lesson_unique.products (
    product_id BIGINT PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    barcode TEXT UNIQUE,
    product_name TEXT NOT NULL
);
```

Ý nghĩa:

- `product_id`: không null, duy nhất, là khóa chính.
- `sku`: không null, duy nhất; có thể là **alternate key**.
- `barcode`: duy nhất với các giá trị đã biết, nhưng **cho phép nhiều NULL** theo mặc định.
- `product_name`: không null nhưng **không duy nhất**; nhiều sản phẩm có thể cùng tên.

### Khóa chính nhiều cột

```sql
CREATE TABLE lesson_unique.order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
```

Không thể chèn hai dòng có cùng `(order_id,line_no)`. Các cột của primary key đồng thời chịu `NOT NULL`.

### Có nên dùng UNIQUE nullable thay PRIMARY KEY?

Nếu một cột là danh tính bắt buộc và được tham chiếu xuyên hệ thống, `PRIMARY KEY` thường diễn đạt đúng hơn. Nếu một mã tùy chọn có thể chưa được biết, `UNIQUE` nullable phù hợp hơn.

Không dùng `UNIQUE NULLS NOT DISTINCT` như cách thay primary key nếu nghiệp vụ thực sự yêu cầu **không bao giờ có null**.

## 13. NOT NULL và UNIQUE giải quyết hai câu hỏi khác nhau

Một ví dụ:

```sql
CREATE TABLE lesson_unique.api_clients (
    client_id BIGINT PRIMARY KEY,
    client_key TEXT NOT NULL,
    tenant_id BIGINT NOT NULL,
    CONSTRAINT uq_api_clients_tenant_key
        UNIQUE (tenant_id, client_key)
);
```

- `NOT NULL`: key phải có giá trị.
- `UNIQUE`: key không được trùng **trong một tenant**.

Ràng buộc có thể bổ sung kiểm tra format:

```sql
ALTER TABLE lesson_unique.api_clients
ADD CONSTRAINT ck_api_client_key_nonblank
CHECK (length(btrim(client_key)) > 0);
```

Nhưng ngay cả như vậy, `client_key='ABC'` và `client_key='abc'` vẫn có thể được coi là khác nhau theo các quy tắc so sánh/collation mặc định.

**Dữ liệu hợp lệ cần nhiều lớp constraint:** not null, unique, check, foreign key và các quy tắc khác bảo vệ những khía cạnh khác nhau.

## 14. CHECK không thay thế UNIQUE

`CHECK` kiểm tra điều kiện trên **hàng đang được thao tác**, không phải một công cụ tổng quát để so sánh mọi hàng trong bảng.

Ví dụ đúng:

```sql
CHECK (quantity >= 0)
```

Ví dụ sai về mặt thiết kế:

```sql
-- Không thể coi mẫu dưới là cách tạo CHECK tương đương UNIQUE:
-- CHECK (
--    NOT EXISTS (
--      SELECT 1 FROM this_table WHERE ... 
--    )
-- )
```

PostgreSQL không cho phép subquery tùy ý trong CHECK constraint theo cách đó. Và ngay cả khi bạn cố bọc một phép đọc bảng vào user-defined function trong CHECK, nó không phải cơ chế an toàn/ổn định để cưỡng chế uniqueness dưới concurrency và có thể gây lỗi khi dump/restore.

**Dùng UNIQUE/unique index cho tính duy nhất; dùng CHECK cho điều kiện hợp lệ của một hàng.**

## 15. Soft delete: tại sao UNIQUE(tenant_id, email, deleted_at) thường sai?

Giả sử:

```sql
CREATE TABLE lesson_unique.members_wrong (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    deleted_at TIMESTAMPTZ,
    UNIQUE (tenant_id, email, deleted_at)
);
```

Bạn muốn:

- Mỗi tenant có **tối đa một member đang hoạt động** cho mỗi email.
- Member đang hoạt động có `deleted_at IS NULL`.
- Những bản đã soft-delete có `deleted_at` khác null và có thể lưu để audit.

Tuy nhiên, lệnh sau **có thể chèn thành công cả hai hàng**:

```sql
INSERT INTO lesson_unique.members_wrong(
    member_id, tenant_id, email, deleted_at
)
VALUES
    (1, 10, 'an@example.test', NULL),
    (2, 10, 'an@example.test', NULL);
```

Vì unique constraint mặc định coi NULL ở cột `deleted_at` là **distinct**, nó không chặn hai tổ hợp có null cuối cùng.

### NULLS NOT DISTINCT có giải quyết đúng soft delete không?

Nếu dùng:

```sql
UNIQUE NULLS NOT DISTINCT (
    tenant_id, email, deleted_at
)
```

thì các hàng active cùng email (với deleted_at null) sẽ bị chặn. Nhưng quy tắc này còn áp dụng cho **các hàng đã xóa** có cùng `deleted_at` — đôi khi đó không phải điều nghiệp vụ yêu cầu. Đồng thời, chỉ số thời gian soft delete không phải một thành phần khóa định danh đẹp về mặt nghiệp vụ.

**Thiết kế rõ ràng hơn:** dùng **partial unique index chỉ áp dụng cho hàng active**.

## 16. Partial unique index cho bản ghi đang hoạt động

```sql
CREATE TABLE lesson_unique.members (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

Ý nghĩa:

- Index chỉ chứa những hàng thỏa `deleted_at IS NULL`.
- Trong tập **active**, `(tenant_id,email)` phải duy nhất.
- Các hàng soft-deleted (`deleted_at IS NOT NULL`) **không tham gia index này**, nên có thể giữ nhiều bản lịch sử cùng email.

Ví dụ:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES
    (1, 10, 'an@example.test', 'An cũ',
        TIMESTAMPTZ '2026-01-01 00:00:00+00'),
    (2, 10, 'an@example.test', 'An hiện tại', NULL),
    (3, 20, 'an@example.test', 'An tenant 20', NULL);
```

Ba hàng hợp lệ.

Thử thêm bản active cho tenant 10:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (4, 10, 'an@example.test', 'An trùng', NULL);
-- ERROR 23505: trùng trong tập active.
```

### Soft delete rồi tạo lại

```sql
UPDATE lesson_unique.members
SET deleted_at = now()
WHERE member_id = 2;

INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (5, 10, 'an@example.test', 'An mới', NULL);
```

Sau khi bản 2 không còn thỏa predicate, bản 5 có thể được chèn nếu không có xung đột active khác.

### Không có partial UNIQUE constraint trực tiếp

Đây là cú pháp **index**:

```sql
CREATE UNIQUE INDEX ...
WHERE deleted_at IS NULL;
```

Không có cú pháp `CONSTRAINT UNIQUE (...) WHERE deleted_at IS NULL` trong định nghĩa constraint thông thường của PostgreSQL. Do đó không thể dùng `ALTER TABLE ... ADD CONSTRAINT UNIQUE USING INDEX` để chuyển **partial unique index** thành unique constraint bình thường.

## 17. Một tenant, nhiều email, và khóa duy nhất có điều kiện

Các quy tắc có thể khác nhau:

| Nghiệp vụ | Cách biểu diễn thường hợp lý |
|---|---|
| Email duy nhất trên toàn hệ thống, không được null | `email TEXT NOT NULL UNIQUE`. |
| Email duy nhất trong từng tenant | `UNIQUE (tenant_id,email)`. |
| Email tùy chọn, nhiều người chưa có email được phép | `UNIQUE(email)` mặc định hoặc khóa kết hợp. |
| Email nullable nhưng chỉ tối đa một NULL | `UNIQUE NULLS NOT DISTINCT(email)` (PG15+). |
| Chỉ email active được duy nhất | `CREATE UNIQUE INDEX ... WHERE deleted_at IS NULL`. |
| Email không phân biệt hoa thường | Expression index như `lower(email)` hoặc mô hình/collation thích hợp. |
| Chỉ non-null email active được duy nhất | Partial unique index với predicate kết hợp; cần quyết định cách null. |

### Điều kiện WHERE phải phản ánh đúng định nghĩa “active”

Một ứng dụng có thể coi active là:

```sql
deleted_at IS NULL AND status = 'ACTIVE'
```

chứ không chỉ `deleted_at IS NULL`. Nếu predicate index không khớp định nghĩa nghiệp vụ, database có thể cho phép trùng trong trường hợp ứng dụng tưởng bị cấm, hoặc chặn một trường hợp ứng dụng muốn cho phép.

**Predicate của partial unique index là một phần của bất biến dữ liệu.** Review nó như review business rule, không chỉ như mẹo tối ưu truy vấn.

## 18. Expression unique index: tính duy nhất theo biểu thức

Đôi khi hai email cần được coi là cùng một khóa dù khác chữ hoa/thường hoặc có khoảng trắng hai đầu:

```text
An@Example.Test
an@example.test
 an@example.test 
```

Một unique index theo biểu thức:

```sql
CREATE TABLE lesson_unique.normalized_accounts (
    account_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_normalized_accounts_email
ON lesson_unique.normalized_accounts (
    tenant_id,
    lower(btrim(email))
);
```

Khi đó `lower(btrim(email))` dùng làm **khóa của index**, chứ không phải giá trị nguyên văn `email`.

Ví dụ:

```sql
INSERT INTO lesson_unique.normalized_accounts(
    account_id, tenant_id, email
)
VALUES (1, 10, 'An@Example.Test');

INSERT INTO lesson_unique.normalized_accounts(
    account_id, tenant_id, email
)
VALUES (2, 10, ' an@example.test ');
-- Có thể ERROR 23505 do hai biểu thức khóa bằng nhau.
```

### Điều kiện để expression index hoạt động

PostgreSQL yêu cầu những hàm/biểu thức được dùng làm index key thỏa các quy tắc tính bất biến phù hợp, thường yêu cầu function **IMMUTABLE**. Không xây unique index dựa trên những kết quả thay đổi theo giờ hiện tại, trạng thái bên ngoài hoặc setting tùy phiên.

### Cảnh báo về email và Unicode

`lower(btrim(email))` chỉ là một **quy tắc minh họa**. Khả năng phân biệt/chuyển chữ thường phụ thuộc collation/locale và quy tắc ứng dụng. Không mặc định mọi địa chỉ email theo mọi tiêu chuẩn đều phải được chuẩn hóa bằng cùng một phép lower/trim.

Với hệ thống quốc tế hóa, cần thống nhất chính sách Unicode, collation, chuẩn hóa và định danh email trước khi cưỡng chế uniqueness.

## 19. Kết hợp expression và partial unique index

Hai yêu cầu:

1. Trong một tenant, không cho hai member active có email giống nhau **sau chuẩn hóa**.
2. Cho phép nhiều bản đã soft-delete với cùng email.

Có thể định nghĩa:

```sql
CREATE TABLE lesson_unique.members_normalized (
    member_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    deleted_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX ux_members_normalized_active
ON lesson_unique.members_normalized (
    tenant_id,
    lower(btrim(email))
)
WHERE deleted_at IS NULL;
```

Index này chỉ kiểm tra những hàng active, trên **khóa chuẩn hóa**. Nó đồng thời là:

- **Unique index**.
- **Expression index**.
- **Partial index**.

### Kiểm tra chính sách từ API

Giả sử user nhập email `" AN@example.test "`. Application nên xử lý format/validation trước khi insert để đưa ra thông báo dễ hiểu. Tuy vậy, database unique index mới là lớp cưỡng chế cuối cùng khi có hai request đồng thời.

### Không thể tham chiếu partial/expression index bằng ON CONSTRAINT

`ON CONFLICT ON CONSTRAINT name` nhận **tên constraint**, không phải tên arbitrary index. Index `ux_members_normalized_active` vừa tạo **không phải unique constraint** khai báo qua `ALTER TABLE`.

Nếu cần UPSERT qua index này, phải dùng **conflict-target inference** phù hợp với expression và predicate, hoặc xem xét thay đổi mô hình (ví dụ generated column) cho dễ sử dụng.

## 20. Case-insensitive uniqueness: lower, citext và collation

Có nhiều chiến lược:

### Cách A — Expression index

```sql
CREATE UNIQUE INDEX ux_email_lower
ON lesson_unique.normalized_accounts (
    tenant_id, lower(email)
);
```

Trong một hệ thống thật, tránh tạo đồng thời `ux_email_lower` và `ux_normalized_accounts_email` nếu chúng trùng mục tiêu nhưng khác quy tắc trim; cần chọn **một chính sách rõ ràng**.

### Cách B — citext

PostgreSQL có extension `citext` cung cấp kiểu text so sánh không phân biệt hoa/thường theo semantics extension/collation:

```sql
-- Chỉ thực hiện nếu có quyền và extension được phép:
CREATE EXTENSION IF NOT EXISTS citext;

-- Ví dụ riêng:
CREATE TABLE lesson_unique.citext_users (
    user_id BIGINT PRIMARY KEY,
    email CITEXT NOT NULL UNIQUE
);
```

Sử dụng extension đòi kiểm tra môi trường deployment, phụ thuộc loại extension và quy tắc collation. `citext` không mặc định giải quyết tất cả vấn đề chuẩn hóa Unicode, whitespace hoặc local-part email theo chính sách nghiệp vụ.

### Cách C — Nondeterministic collations

PostgreSQL hiện đại hỗ trợ một số collation không xác định (*nondeterministic*) cho so sánh text theo tiêu chí như không phân biệt chữ hoa/diacritics, tùy provider/locale và phiên bản. Khi lựa chọn cần kiểm tra những giới hạn về operator, hiệu năng và thay đổi phiên bản ICU.

**Không trộn các cách này tùy tiện.** Hai cấu hình collation khác nhau có thể đưa ra khái niệm “bằng nhau” khác nhau, và từ đó uniqueness khác nhau.

## 21. INCLUDE columns không tham gia tính duy nhất

Một B-tree index có thể lưu thêm cột để hỗ trợ index-only scans:

```sql
CREATE TABLE lesson_unique.customer_directory (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_customer_directory_email
ON lesson_unique.customer_directory (tenant_id, email)
INCLUDE (display_name);
```

Index có:

- **Key columns:** `tenant_id` và `email`.
- **Included/non-key column:** `display_name`.

Tính duy nhất được kiểm tra **chỉ trên key columns**, không gồm `display_name`.

### Ví dụ

Hai hàng:

```text
(tenant=10, email='a@example.test', display_name='A')
(tenant=10, email='a@example.test', display_name='B')
```

vẫn vi phạm unique, dù display name khác nhau.

### INCLUDE không miễn phí

Cột INCLUDE làm index lớn hơn và tăng công việc ghi. Index-only scan còn phụ thuộc visibility map và workload, không được bảo đảm chỉ vì có INCLUDE. Cần đo `EXPLAIN (ANALYZE, BUFFERS)` nếu đang tối ưu.

## 22. UNIQUE constraint DEFERRABLE

Theo mặc định, unique constraint thường được kiểm tra **ngay khi thao tác đòi hỏi**, nhưng PostgreSQL hỗ trợ **deferrable unique constraints** để trì hoãn thời điểm kiểm tra hợp lệ.

```sql
CREATE TABLE lesson_unique.priority_slots (
    slot_id INTEGER PRIMARY KEY,
    position INTEGER NOT NULL,
    CONSTRAINT uq_priority_position
        UNIQUE (position)
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO lesson_unique.priority_slots(slot_id, position)
VALUES (1, 10), (2, 20);
```

### Tại sao cần DEFERRABLE?

Giả sử muốn **hoán đổi position 10 và 20** giữa hai hàng. Trong quá trình cập nhật, có thể có trạng thái trung gian vi phạm uniqueness dù trạng thái cuối hợp lệ.

Một transaction có thể trì hoãn kiểm tra:

```sql
BEGIN;

SET CONSTRAINTS uq_priority_position DEFERRED;

UPDATE lesson_unique.priority_slots
SET position = CASE
    WHEN slot_id = 1 THEN 20
    WHEN slot_id = 2 THEN 10
END
WHERE slot_id IN (1, 2);

COMMIT;
```

Khi constraint được deferred, trạng thái tạm thời có thể vi phạm nhưng trạng thái cuối phải thỏa constraint lúc kiểm tra.

### INITIALLY IMMEDIATE và INITIALLY DEFERRED

- `DEFERRABLE INITIALLY IMMEDIATE`: mặc định kiểm tra theo chế độ immediate, nhưng có thể chuyển sang deferred trong transaction.
- `DEFERRABLE INITIALLY DEFERRED`: mặc định trì hoãn đến cuối transaction, trừ khi được đặt lại.
- `NOT DEFERRABLE`: không thể chuyển thành deferred chỉ bằng `SET CONSTRAINTS`.

### Kiểm tra lỗi tại COMMIT

Nếu trạng thái cuối vẫn có hai hàng cùng position, `COMMIT` có thể thất bại với `23505`. Không coi `UPDATE` thành công trước đó là bằng chứng transaction chắc chắn commit.

**Không phải mọi ràng buộc đều cùng khả năng deferrable.** `NOT NULL` và `CHECK` có quy tắc khác; đừng nghĩ `SET CONSTRAINTS ALL DEFERRED` trì hoãn mọi kiểm tra của PostgreSQL.

## 23. DEFERRABLE khác unique index tạo trực tiếp

`CREATE UNIQUE INDEX` tạo cơ chế uniqueness theo index. Nó **không tự tạo một deferrable unique constraint**.

Khi cần có thể chuyển chế độ immediate/deferred:

```sql
CONSTRAINT uq_priority_position
UNIQUE (position)
DEFERRABLE
```

thay vì chỉ:

```sql
CREATE UNIQUE INDEX ...
ON ... (position);
```

### DEFERRABLE và ON CONFLICT

Một giới hạn đặc biệt quan trọng: **deferrable unique constraints không thể được sử dụng làm arbiter của `INSERT ... ON CONFLICT DO UPDATE`**. PostgreSQL cần một cơ chế conflict arbitration có tính immediate phù hợp.

Do đó, nếu nghiệp vụ chủ yếu là UPSERT theo `(tenant_id, external_id)`, một unique constraint **`NOT DEFERRABLE`** thường thích hợp hơn.

Đừng thêm `DEFERRABLE` chỉ vì nghĩ “linh hoạt hơn”, rồi phát hiện UPSERT không tương thích.

## 24. ALTER TABLE ADD CONSTRAINT và kiểm tra dữ liệu có sẵn

Một bảng đã có hàng trùng không thể đơn giản “đắp unique constraint” mà vẫn giữ dữ liệu vi phạm.

```sql
ALTER TABLE lesson_unique.accounts
ADD CONSTRAINT uq_accounts_email_global
UNIQUE (email);
```

Câu trên **không phù hợp với dữ liệu mẫu**, vì email `an@example.test` xuất hiện ở tenant 10 và 20. Nếu chạy, PostgreSQL sẽ phát hiện dữ liệu vi phạm và không tạo thành công constraint.

### Nguyên tắc

Trước khi thêm ràng buộc:

1. Xác định khóa nghiệp vụ đúng.
2. Kiểm tra dữ liệu có trùng theo đúng semantics NULL/normalization không.
3. Chọn bản đại diện nếu phải làm sạch.
4. Xác minh các foreign keys/audit/references bị ảnh hưởng.
5. Lập kế hoạch khóa và thời gian tạo index.
6. Chỉ thêm constraint khi dữ liệu đã phù hợp.

### Không coi NOT VALID là giải pháp chung cho UNIQUE

PostgreSQL hỗ trợ `NOT VALID` cho một số loại constraint như foreign key/CHECK, nhưng không thể dùng `ADD CONSTRAINT ... UNIQUE NOT VALID` như cách trì hoãn kiểm tra tính duy nhất của dữ liệu hiện có.

Với bảng lớn, kỹ thuật triển khai phổ biến là **xây unique index concurrently rồi attach thành constraint** nếu index đủ điều kiện.

## 25. CREATE UNIQUE INDEX CONCURRENTLY

Khi bảng lớn và ứng dụng vẫn đọc/ghi, tạo index thông thường có thể tác động đáng kể tới khả năng ghi đồng thời. PostgreSQL cung cấp:

```sql
CREATE UNIQUE INDEX CONCURRENTLY ux_accounts_tenant_email_new
ON lesson_unique.accounts (tenant_id, email);
```

Đây là **ví dụ cú pháp**, không cần tạo một index trùng với constraint đã có trong lab.

### Lợi ích

`CREATE INDEX CONCURRENTLY` nhằm giảm việc chặn các thao tác INSERT/UPDATE/DELETE so với tạo index thông thường, bằng quy trình xây và xác minh theo nhiều giai đoạn.

### Giới hạn

- **Không chạy trong transaction block tường minh** (`BEGIN ... COMMIT`).
- Có thể mất thời gian hơn và tiêu thụ I/O/CPU đáng kể.
- Unique index vẫn có thể **thất bại** nếu dữ liệu trùng hoặc có conflict do writer đồng thời.
- Trong một số giai đoạn xây unique index concurrently, uniqueness có thể bắt đầu được kiểm tra với các transaction khác **trước khi index được đánh dấu hoàn toàn valid**.
- Nếu quá trình thất bại, có thể để lại một index **INVALID**, cần điều tra và dọn dẹp có kiểm soát.

**CONCURRENTLY không có nghĩa “không khóa gì” hay “không rủi ro”.** Nó vẫn phải phối hợp với transaction khác và có thể chờ các transaction/snapshot liên quan.

## 26. Đính kèm unique index thành constraint

Đối với một index unique đã xây xong và đủ điều kiện:

```sql
-- Ví dụ migration trên bảng chưa có constraint tương ứng:
CREATE UNIQUE INDEX CONCURRENTLY ux_future_unique_key
ON some_schema.some_table (tenant_id, business_key);

ALTER TABLE some_schema.some_table
ADD CONSTRAINT uq_future_unique_key
UNIQUE USING INDEX ux_future_unique_key;
```

Đây là **mẫu migration**, `some_schema.some_table` chưa được tạo trong lab.

Quy trình ý tưởng:

1. Bảng đã không còn dữ liệu trùng.
2. Tạo index unique bằng `CONCURRENTLY` ngoài transaction block.
3. Kiểm tra index được xây **thành công và valid**.
4. Attach bằng `ALTER TABLE ... ADD CONSTRAINT ... USING INDEX`.

### Những điều kiện quan trọng

Index để attach phải đáp ứng quy tắc PostgreSQL, điển hình là **unique B-tree index** hợp lệ trên cột thực, không phải partial/expression index. Các điều kiện về định dạng/sắp xếp và thuộc tính index cũng được PostgreSQL kiểm tra.

Nếu constraint yêu cầu `PRIMARY KEY`, mọi cột khóa phải `NOT NULL` và quá trình attach có thể cần bước kiểm tra/đặt NOT NULL phù hợp.

### ALTER TABLE vẫn cần lock

Ngay cả khi index được xây concurrently, bước `ALTER TABLE` thường cần lock metadata mạnh trong khoảng thời gian thích hợp. Nên triển khai trong cửa sổ bảo trì phù hợp và có `lock_timeout`/retry migration theo chính sách.

## 27. Index INVALID sau CREATE INDEX CONCURRENTLY thất bại

Một build concurrently có thể thất bại do:

- Dữ liệu có duplicate.
- Một writer tạo duplicate trong quá trình build.
- Deadlock, cancel, lỗi tài nguyên hoặc vấn đề vận hành.

Trạng thái catalog cần kiểm tra:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS index_name,
    i.indisunique,
    i.indisvalid,
    i.indisready
FROM pg_catalog.pg_index AS i
JOIN pg_catalog.pg_class AS c
  ON c.oid = i.indexrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = c.relnamespace
WHERE n.nspname = 'lesson_unique'
ORDER BY c.relname;
```

Đặc biệt:

- `indisvalid = false`: planner thường không sử dụng index như một index hợp lệ cho truy vấn.
- `indisready`: chỉ báo index đã sẵn sàng cho thao tác ghi theo ngữ nghĩa catalog.
- Unique index INVALID đôi khi **vẫn phát sinh chi phí ghi hoặc kiểm tra uniqueness** tùy giai đoạn lỗi, không nên nghĩ INVALID nghĩa là hoàn toàn vô tác dụng.

### Phương án phục hồi

1. Đọc thông báo build lỗi và catalog state.
2. Tìm duplicate và nguyên nhân writer đồng thời.
3. Nếu được phê duyệt, drop index lỗi theo phương thức phù hợp:

```sql
DROP INDEX CONCURRENTLY IF EXISTS
    lesson_unique.ux_failed_build_example;
```

Đây chỉ là **cú pháp minh họa**; không tự chạy khi chưa xác định đúng index và phụ thuộc. `DROP INDEX CONCURRENTLY` có các giới hạn, gồm không chạy trong transaction block và không áp dụng tùy ý cho index đang hỗ trợ constraint.

4. Làm sạch dữ liệu và chỉnh ingestion.
5. Tạo lại index đúng phương án migration.

Không coi `IF NOT EXISTS` là bảo đảm index cũ có đúng định nghĩa: một object cùng tên nhưng INVALID hoặc sai cấu hình vẫn cần xem xét riêng.

## 28. UNIQUE có thể làm arbiter của ON CONFLICT

`INSERT ... ON CONFLICT` giúp định nghĩa cách xử lý khi thao tác insert gặp khóa unique đã tồn tại.

Ví dụ **bỏ qua conflict**:

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'An mới gửi lại')
ON CONFLICT (tenant_id, email)
DO NOTHING
RETURNING account_id;
```

Vì tổ hợp `(10,'an@example.test')` đã tồn tại, câu lệnh không tạo hàng mới và `RETURNING` trả **0 hàng**.

### DO NOTHING không sửa bản cũ

Nếu client muốn lấy ID bản đã tồn tại, `DO NOTHING RETURNING` không tự trả lại hàng cũ. Ứng dụng có thể thiết kế truy vấn bổ sung, hoặc một UPSERT chính xác theo nghiệp vụ, chú ý concurrency/snapshot semantics.

### DO UPDATE

```sql
INSERT INTO lesson_unique.accounts AS a (
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'Tên hiển thị mới')
ON CONFLICT (tenant_id, email)
DO UPDATE SET
    display_name = EXCLUDED.display_name
RETURNING a.account_id, a.display_name;
```

`EXCLUDED` biểu diễn hàng được đề xuất để insert, dùng để tính giá trị cho nhánh UPDATE khi xảy ra conflict.

**Không phải mọi ứng dụng nên update khi trùng.** Với signup, hai request đăng ký cùng email có thể cần trả lỗi “đã tồn tại” thay vì ghi đè tên hiển thị của account cũ.

## 29. ON CONFLICT ON CONSTRAINT

Khi có một **constraint được đặt tên**, có thể dùng:

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'An đăng ký lại')
ON CONFLICT ON CONSTRAINT uq_accounts_tenant_email
DO NOTHING;
```

Đây là cách chỉ rõ **unique constraint** dùng để xử lý conflict.

### Tên index không đồng nghĩa tên constraint

Nếu tạo:

```sql
CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

thì `ux_members_active_email` là **index**, không tự tạo thành một `UNIQUE` constraint có thể chỉ định bằng `ON CONSTRAINT ux_members_active_email`.

Trong trường hợp index inference, dùng danh sách khóa/predicate tương ứng.

### ON CONFLICT DO NOTHING có thể bỏ conflict target

```sql
INSERT INTO lesson_unique.accounts(
    tenant_id, email, display_name
)
VALUES (10, 'an@example.test', 'An khác')
ON CONFLICT DO NOTHING;
```

Đây là cú pháp hợp lệ cho `DO NOTHING`, nhưng cần cân nhắc: nó có thể **bỏ qua nhiều loại unique conflict** thay vì chỉ conflict mà business logic dự kiến. Khi yêu cầu cụ thể, viết conflict target để mã rõ ràng hơn.

## 30. ON CONFLICT với NULLS NOT DISTINCT

Với bảng `refs_strict`:

```sql
INSERT INTO lesson_unique.refs_strict(
    ref_id, tenant_id, external_ref
)
VALUES (7, 10, NULL)
ON CONFLICT (tenant_id, external_ref)
DO NOTHING
RETURNING ref_id;
```

Vì khóa `(10,NULL)` đã tồn tại theo `NULLS NOT DISTINCT`, câu lệnh nhận conflict và bỏ qua.

Nếu bảng chỉ có `UNIQUE` mặc định:

```sql
INSERT INTO lesson_unique.refs_default(
    ref_id, tenant_id, external_ref
)
VALUES (7, 10, NULL)
ON CONFLICT (tenant_id, external_ref)
DO NOTHING
RETURNING ref_id;
```

thì **không có conflict do cặp `(10,NULL)`**, nên insert có thể thành công nếu `ref_id` chưa được dùng.

### Bài học

Hành vi `ON CONFLICT` với null phụ thuộc **semantics của unique arbiter**. Không viết code “insert if absent” mà bỏ qua việc unique index hiện đang dùng `NULLS DISTINCT` hay `NULLS NOT DISTINCT`.

## 31. ON CONFLICT với partial unique index

Với bảng `lesson_unique.members` đã có:

```sql
CREATE UNIQUE INDEX ux_members_active_email
ON lesson_unique.members (tenant_id, email)
WHERE deleted_at IS NULL;
```

Khi chèn thành viên active:

```sql
INSERT INTO lesson_unique.members(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES (6, 10, 'an@example.test', 'An đăng ký lại', NULL)
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
DO NOTHING
RETURNING member_id;
```

Phần:

```sql
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
```

giúp PostgreSQL **infer** index có khóa và predicate tương ứng trong hoàn cảnh hỗ trợ.

### Không nhầm hai vị trí WHERE

`WHERE` sau danh sách conflict target dùng để **infer partial index**:

```sql
ON CONFLICT (tenant_id, email)
WHERE deleted_at IS NULL
```

Trong khi `WHERE` sau `DO UPDATE SET` là điều kiện quyết định có thực hiện UPDATE với hàng đã conflict:

```sql
ON CONFLICT (...) DO UPDATE
SET ...
WHERE <condition_for_update>
```

Đây là **hai điều kiện khác nhau**. Predicate inference không phải phép filter hàng đầu vào của `INSERT`.

### Phải bảo vệ key khi cập nhật trạng thái

Nếu UPDATE một hàng từ `deleted_at IS NOT NULL` về `NULL`, hàng đó **đi vào tập active**. Partial unique index sẽ kiểm tra xem đã có một member active cùng key hay chưa. Uniqueness không chỉ có tác dụng ở INSERT.

## 32. ON CONFLICT với expression unique index

Với `members_normalized`:

```sql
CREATE UNIQUE INDEX ux_members_normalized_active
ON lesson_unique.members_normalized (
    tenant_id, lower(btrim(email))
)
WHERE deleted_at IS NULL;
```

Một conflict target có thể suy luận expression/predicate tương ứng:

```sql
INSERT INTO lesson_unique.members_normalized(
    member_id, tenant_id, email, display_name, deleted_at
)
VALUES
    (1, 10, 'An@Example.Test', 'An', NULL)
ON CONFLICT (
    tenant_id,
    (lower(btrim(email)))
)
WHERE deleted_at IS NULL
DO NOTHING;
```

Với biểu thức index, dấu ngoặc quanh expression trong conflict target giúp diễn đạt đây là **index expression**. Index inference phụ thuộc đúng biểu thức/column set và điều kiện theo quy tắc của PostgreSQL.

### Khi logic phức tạp

Nếu unique key có nhiều bước chuẩn hóa và UPSERT xuất hiện ở nhiều nơi, có thể cân nhắc:

- Cột canonical được ứng dụng duy trì một cách đáng tin.
- **Stored generated column** phù hợp, sau đó đặt UNIQUE trên cột đó.
- Một unique constraint có tên dễ sử dụng khi không cần predicate.

Đừng nhân đôi nhiều biểu thức normalization hơi khác nhau ở các đường ghi.

## 33. Partial unique index và query planner

Partial index chỉ chứa subset hàng theo predicate. Nó có thể vừa bảo vệ uniqueness vừa giúp truy vấn phù hợp được tối ưu.

Ví dụ:

```sql
EXPLAIN
SELECT member_id, display_name
FROM lesson_unique.members
WHERE tenant_id = 10
  AND email = 'an@example.test'
  AND deleted_at IS NULL;
```

Predicate trong query chứa `deleted_at IS NULL` nên PostgreSQL có cơ sở cân nhắc partial index.

Nhưng nếu truy vấn **không chứng minh được** nó chỉ tìm trong tập hàng thuộc predicate:

```sql
SELECT *
FROM lesson_unique.members
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

thì partial index riêng cho active **không chứa hàng đã xóa**, nên không thể tự đại diện cho toàn bộ kết quả.

### Prepared statement và tham số

Việc planner có chứng minh một điều kiện truy vấn hàm ý predicate partial index hay không phụ thuộc biểu thức và plan. Những điều kiện tổng quát dùng parameter như `status = $1` không nhất thiết chứng minh `status='ACTIVE'` cho mọi giá trị khi kế hoạch được tái sử dụng.

**Không nghĩ rằng có partial index thì mọi query sẽ dùng nó.** Kiểm tra `EXPLAIN` với truy vấn và kiểu plan thực tế.

## 34. UNIQUE và NULL theo collation/type

Unique B-tree index không chỉ so từng byte thô của text trong mọi trường hợp. **Operator class và collation** tham gia định nghĩa thứ tự/equality cho index key.

Ví dụ:

- `text` với collation xác định có thể coi `'A'` khác `'a'`.
- `citext` có ngữ nghĩa so sánh không phân biệt hoa/thường theo môi trường.
- Expression `lower(email)` biến hai input thành cùng giá trị khóa khi biểu thức cho kết quả bằng nhau.
- Nondeterministic collations có thể coi nhiều chuỗi khác byte là tương đương theo chính sách.

### Vì sao upgrade collation đáng chú ý?

Khi thư viện collation/ICU của hệ thống thay đổi phiên bản hoặc quy tắc, thứ tự/equality của text có thể thay đổi. Có thể cần chiến lược kiểm tra/reindex theo hướng dẫn PostgreSQL cho môi trường. Không chỉ nhìn DDL ban đầu mà bỏ qua phụ thuộc collation trong vận hành.

### Không dùng UNIQUE làm validation định dạng

Một email unique vẫn có thể là:

```text
not-an-email
```

`UNIQUE` trả lời **“có bị lặp theo khóa không?”**, không trả lời **“giá trị có đúng format theo nghiệp vụ không?”**. Validation/check constraint hoặc xử lý ứng dụng là lớp riêng.

## 35. Unique index và concurrency

Một unique index phải xử lý những transaction chưa hoàn tất. Hai request có thể cùng insert một khóa.

```text
Session A                                Session B
----------------------------------       ----------------------------------
BEGIN;
INSERT key=('tenant10','A');
-- chưa COMMIT
                                        INSERT key=('tenant10','A');
                                        -- có thể CHỜ A
COMMIT;
                                        -- thường kết thúc bằng 23505
```

Nếu A **ROLLBACK** thay vì commit, B có thể được phép insert key ấy.

### Không phải SELECT thấy hàng nào thì unique index chỉ kiểm tra hàng ấy

Ở `READ COMMITTED`, B có thể `SELECT` chưa thấy hàng chưa commit của A. Nhưng unique index cần quyết định **tính duy nhất toàn cục**, nên có thể phải chờ trạng thái A để quyết định.

Chính sự kết hợp giữa kiểm tra index và trạng thái transaction khiến constraint bảo vệ dữ liệu tốt hơn phép kiểm tra pre-insert không có synchronization.

### MVCC không làm uniqueness tùy từng snapshot

Unique constraint không có nghĩa “chỉ cấm hai hàng trùng trong snapshot của người đang insert”. Nếu vậy, hai transaction cùng commit có thể tạo dữ liệu vi phạm. PostgreSQL phải xét xung đột mà một SELECT thông thường không nhìn thấy.

## 36. Kịch bản hai session kiểm tra uniqueness

Tạo bảng riêng:

```sql
CREATE TABLE lesson_unique.concurrent_keys (
    row_id BIGINT PRIMARY KEY,
    business_key TEXT NOT NULL UNIQUE
);
```

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_unique.concurrent_keys(
    row_id, business_key
)
VALUES (1, 'KEY-X');

-- Giữ transaction mở.
```

**Session B:**

```sql
BEGIN;

SELECT *
FROM lesson_unique.concurrent_keys
WHERE business_key = 'KEY-X';
-- Không thấy hàng chưa commit của A.

INSERT INTO lesson_unique.concurrent_keys(
    row_id, business_key
)
VALUES (2, 'KEY-X');
-- Có thể đứng chờ transaction A.
```

**Session A:**

```sql
COMMIT;
```

**Session B:** có thể nhận lỗi `23505`. Vì B đang ở transaction tường minh đã lỗi:

```sql
ROLLBACK;
```

Lặp lại thí nghiệm với A `ROLLBACK` thay vì commit (trên dữ liệu lab sạch) để quan sát khả năng B chèn thành công.

### pg_locks khi B đang đợi

Từ session giám sát:

```sql
SELECT
    a.pid,
    a.wait_event_type,
    a.wait_event,
    pg_catalog.pg_blocking_pids(a.pid) AS blockers
FROM pg_catalog.pg_stat_activity AS a
WHERE a.datname = current_database()
  AND a.wait_event_type = 'Lock';
```

Tranh chấp unique có thể biểu hiện chờ transaction ID. Đây là công cụ chẩn đoán, không phải hợp đồng mỗi lần trùng key đều tạo cùng một mẫu lock.

## 37. Bảo vệ dữ liệu bằng UNIQUE nhưng lỗi vẫn cần được xử lý

Khi insert trùng:

```text
SQLSTATE 23505
unique_violation
```

Ứng dụng nên phân loại:

1. Nếu conflict là **kết quả nghiệp vụ dự kiến**, có thể trả thông báo “đã tồn tại”/HTTP 409 hoặc thiết kế `ON CONFLICT`.
2. Nếu conflict báo **bug ở pipeline**, cần logging và điều tra nguồn trùng.
3. Nếu hệ thống đã ở trong transaction tường minh, lỗi có thể làm transaction aborted, phải rollback.
4. Nếu ứng dụng có retry chung, **không retry vô hạn 23505**; nếu key không đổi, retry nhiều lần chỉ tạo thêm tải.
5. Nếu conflict xảy ra trong UPSERT nhưng với **một unique index khác không được chỉ định**, statement vẫn có thể lỗi.

### SQLSTATE vs message

Không nên xử lý bằng:

```java
if (e.getMessage().contains("duplicate key")) { ... }
```

Thông điệp có thể khác theo locale/server version. Dùng `SQLException.getSQLState()` và tên constraint/index từ metadata khi cần phân biệt loại conflict.

## 38. Foreign key cần một khóa tham chiếu phù hợp

Một foreign key phải tham chiếu một tập cột được bảo đảm uniqueness theo tiêu chí PostgreSQL.

Ví dụ:

```sql
CREATE TABLE lesson_unique.tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_name TEXT NOT NULL UNIQUE
);

CREATE TABLE lesson_unique.tenant_profiles (
    profile_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL
        REFERENCES lesson_unique.tenants(tenant_id),
    profile_name TEXT NOT NULL
);
```

Primary key là khóa tham chiếu tự nhiên.

Ngoài ra, target của FK có thể là những cột có **non-deferrable unique/primary key constraint** hoặc một **non-partial unique index** phù hợp trên cột, theo quy tắc PostgreSQL. Không phải mọi unique expression/partial index đều có thể là mục tiêu FK.

### Vì sao partial unique index không thay thế khóa FK?

Một partial unique index chỉ bảo đảm duy nhất trong **tập con** hàng. Foreign key cần định nghĩa tham chiếu ổn định tới những hàng theo khóa được hỗ trợ. Index chỉ áp dụng `WHERE deleted_at IS NULL` không tự tạo một khóa tham chiếu hợp lệ cho mọi giá trị.

### NULL trong foreign key là câu chuyện khác

Foreign key mặc định có những quy tắc riêng cho giá trị null bên tham chiếu. Đừng đồng nhất ngữ nghĩa NULL của FK với `UNIQUE NULLS NOT DISTINCT` trên bảng đích; cần thiết kế `MATCH`/NOT NULL và khóa tham chiếu theo yêu cầu thực.

## 39. Unique constraint trên bảng partitioned

Đối với **declarative partitioned tables**, PostgreSQL có giới hạn đáng chú ý khi khai báo primary key/unique constraint: khóa unique trên parent thường phải **bao gồm toàn bộ partition key columns** theo những điều kiện được phiên bản hỗ trợ. Bởi uniqueness thực tế được cưỡng chế ở partition indexes và PostgreSQL cần có khả năng bảo đảm hai hàng trùng key không nằm ở hai partition khác nhau.

Ví dụ partition theo tenant:

```sql
CREATE TABLE lesson_unique.partitioned_events (
    tenant_id INTEGER NOT NULL,
    event_id BIGINT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (tenant_id, event_id)
) PARTITION BY LIST (tenant_id);

CREATE TABLE lesson_unique.partitioned_events_t10
PARTITION OF lesson_unique.partitioned_events
FOR VALUES IN (10);

CREATE TABLE lesson_unique.partitioned_events_t20
PARTITION OF lesson_unique.partitioned_events
FOR VALUES IN (20);
```

Khóa chính gồm `tenant_id` và `event_id`, bao gồm partition key `tenant_id`.

### Tại sao UNIQUE(event_id) riêng có thể không hợp lệ?

Nếu hai partition khác nhau được phép chứa cùng `event_id` và mỗi partition chỉ kiểm tra dữ liệu của nó, không thể suy ra global uniqueness của `event_id` trên parent từ các index nội bộ ấy.

Nếu nghiệp vụ đòi `event_id` duy nhất **trên toàn bộ tenant**, cần kiến trúc phù hợp (global ID generation phối hợp, một bảng registry/lookup có unique key, hoặc chiến lược khác). Không tự giả định parent partitioned table hỗ trợ global unique index độc lập với partition key như một bảng không partition.

### Partitioning và unique NULL

`NULLS NOT DISTINCT` vẫn cần được đánh giá trong phạm vi khóa/partition key hợp lệ, không vượt qua giới hạn uniqueness toàn bảng phân vùng.

## 40. Kiểm tra metadata của UNIQUE trong catalog

PostgreSQL có catalog:

- `pg_constraint`: mô tả constraint, gồm loại constraint, các flags về deferrability và index hỗ trợ.
- `pg_index`: thuộc tính index như unique, valid/ready và NULL semantics.
- `pg_class`: tên bảng/index.
- `pg_namespace`: schema.
- `pg_indexes`: view biểu diễn định nghĩa index theo schema.

### Liệt kê constraint

```sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    c.condeferrable,
    c.condeferred,
    pg_catalog.pg_get_constraintdef(c.oid) AS definition
FROM pg_catalog.pg_constraint AS c
JOIN pg_catalog.pg_class AS t
  ON t.oid = c.conrelid
JOIN pg_catalog.pg_namespace AS n
  ON n.oid = t.relnamespace
WHERE n.nspname = 'lesson_unique'
  AND c.contype IN ('p', 'u')
ORDER BY t.relname, c.conname;
```

Giải nghĩa:

- `contype = 'p'`: primary key.
- `contype = 'u'`: unique constraint.
- `condeferrable`: constraint có thể hoãn kiểm tra hay không.
- `condeferred`: trạng thái initially deferred theo cấu hình constraint.

### Liệt kê index definitions

```sql
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_catalog.pg_indexes
WHERE schemaname = 'lesson_unique'
ORDER BY tablename, indexname;
```

Lệnh này hiển thị **cả unique indexes tạo trực tiếp** như partial/expression indexes mà `pg_constraint` có thể không có hàng constraint tương ứng.

## 41. Xem indnullsnotdistinct trên PostgreSQL 15+

Trong PostgreSQL 15 trở lên, `pg_index` có thông tin:

```sql
SELECT
    tbl_ns.nspname AS table_schema,
    tbl.relname AS table_name,
    idx.relname AS index_name,
    pi.indisunique,
    pi.indnullsnotdistinct,
    pi.indisvalid,
    pg_catalog.pg_get_indexdef(idx.oid) AS index_definition
FROM pg_catalog.pg_index AS pi
JOIN pg_catalog.pg_class AS idx
  ON idx.oid = pi.indexrelid
JOIN pg_catalog.pg_class AS tbl
  ON tbl.oid = pi.indrelid
JOIN pg_catalog.pg_namespace AS tbl_ns
  ON tbl_ns.oid = tbl.relnamespace
WHERE tbl_ns.nspname = 'lesson_unique'
ORDER BY tbl.relname, idx.relname;
```

- `indisunique`: index là unique index.
- `indnullsnotdistinct`: NULL được coi là không phân biệt cho uniqueness của index.
- `indisvalid`: trạng thái index hợp lệ.

**Đừng chạy truy vấn có `indnullsnotdistinct` trên PostgreSQL cũ hơn 15**, vì cột catalog này chưa có và SQL có thể lỗi `undefined_column`. Dùng `server_version_num` hoặc catalog fields thực sự được hỗ trợ.

### Catalog không phải hợp đồng ORM dài hạn

Tooling quản trị có thể đọc catalog, nhưng migration/ORM phải xét biến thể phiên bản PostgreSQL. Không dùng trực tiếp những trường catalog phiên bản mới nếu sản phẩm vẫn hỗ trợ server cũ.

## 42. information_schema.table_constraints

Trong các công cụ cần truy vấn SQL gần chuẩn, có thể dùng information schema:

```sql
SELECT
    table_schema,
    table_name,
    constraint_name,
    constraint_type,
    is_deferrable,
    initially_deferred
FROM information_schema.table_constraints
WHERE table_schema = 'lesson_unique'
ORDER BY table_name, constraint_name;
```

Nó phù hợp để liệt kê constraint của bảng nhưng **không thay thế `pg_indexes`** khi muốn thấy partial/expression unique indexes được tạo trực tiếp.

### psql meta-commands

Trong `psql`:

```text
\d lesson_unique.accounts
\d lesson_unique.members
\di lesson_unique.*
```

Đây là các **meta-command của psql**, không phải SQL gửi trực tiếp qua JDBC.

## 43. Tìm dữ liệu trùng trước khi tạo UNIQUE

Giả sử một bảng staging lưu nhiều lần nhận cùng business key:

```sql
CREATE TABLE lesson_unique.raw_contacts (
    contact_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    external_key TEXT,
    received_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL
);

INSERT INTO lesson_unique.raw_contacts(
    contact_id, tenant_id, external_key,
    received_at, payload
)
VALUES
    (1, 10, 'A', TIMESTAMPTZ '2026-11-10 09:00:00+07',
        '{"v":1}'::jsonb),
    (2, 10, 'A', TIMESTAMPTZ '2026-11-11 09:00:00+07',
        '{"v":2}'::jsonb),
    (3, 10, NULL, TIMESTAMPTZ '2026-11-11 10:00:00+07',
        '{"v":1}'::jsonb),
    (4, 10, NULL, TIMESTAMPTZ '2026-11-12 10:00:00+07',
        '{"v":2}'::jsonb),
    (5, 20, 'A', TIMESTAMPTZ '2026-11-12 11:00:00+07',
        '{"v":1}'::jsonb);
```

### Đếm duplicate theo semantics NULLS NOT DISTINCT

```sql
SELECT
    tenant_id,
    external_key,
    COUNT(*) AS row_count
FROM lesson_unique.raw_contacts
GROUP BY tenant_id, external_key
HAVING COUNT(*) > 1
ORDER BY tenant_id, external_key NULLS FIRST;
```

Kết quả cho tenant 10 có:

- `(10, 'A')`: 2 hàng.
- `(10, NULL)`: 2 hàng.

**Điểm tinh tế:** `GROUP BY` gom `NULL` theo nhóm. Truy vấn trên là lựa chọn hợp lý khi bạn định thêm **`UNIQUE NULLS NOT DISTINCT`**. Nếu định thêm `UNIQUE` mặc định, nhóm `(10,NULL)` **không phải một vi phạm uniqueness** dù query báo COUNT > 1.

### Kiểm tra đúng chính sách trước khi xóa

Đừng xóa tất cả nhóm COUNT > 1 nếu target constraint mặc định cho phép nhiều null và mỗi bản ghi null mang ý nghĩa hợp lệ. Truy vấn tìm trùng phải phản ánh **bất biến đích**, không chỉ cơ chế GROUP BY.

## 44. Tìm bản ghi đại diện bằng ROW_NUMBER

Nếu nghiệp vụ yêu cầu giữ một hàng cho mỗi `(tenant_id, external_key)` theo **thời điểm nhận mới nhất**, dùng:

```sql
WITH ranked AS (
    SELECT
        c.*,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
SELECT
    tenant_id,
    external_key,
    contact_id,
    received_at,
    rn
FROM ranked
ORDER BY tenant_id, external_key NULLS FIRST, rn;
```

Ở ví dụ này:

- `(10,'A')`: giữ contact 2.
- `(10,NULL)`: giữ contact 4 **nếu NULL được coi là một khóa cần duy nhất**.
- `(20,'A')`: giữ contact 5.

### Không chọn bản đại diện tùy ý

Nếu hai hàng có cùng `received_at`, `contact_id DESC` giúp quyết định ổn định. Nhưng ID lớn hơn không tự đảm bảo **payload mới nhất về mặt nguồn**. Nếu có `source_version` đáng tin, nên dùng version đó làm thứ tự ưu tiên trước.

### NULL trong PARTITION BY

`PARTITION BY (tenant_id, external_key)` gom các hàng có cùng tenant và external_key null vào một partition, tương tự `GROUP BY`. Đây là hành vi cần hiểu trước khi dùng window function để chuẩn bị migration `NULLS NOT DISTINCT`.

## 45. Xem trước những hàng sẽ xóa

Đầu tiên **chỉ SELECT**:

```sql
WITH ranked AS (
    SELECT
        c.contact_id,
        c.tenant_id,
        c.external_key,
        c.received_at,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
SELECT *
FROM ranked
WHERE rn > 1
ORDER BY tenant_id, external_key NULLS FIRST, rn;
```

Trong lab, truy vấn dự kiến chọn contact 1 và contact 3 làm hàng dư, **theo chính sách chỉ giữ một null cho mỗi tenant**.

Trước khi xóa thật, phải xác nhận:

- Các hàng là cùng entity nghiệp vụ, không phải event lịch sử hợp lệ.
- Đã xác định bản authoritative.
- Có foreign key trỏ tới hàng sắp xóa hay không.
- Có cần archive/audit trước khi xóa không.
- Có transaction khác đang insert cùng key không.
- Có backup/rollback hoặc chiến lược sửa dữ liệu nếu nhầm không.

## 46. Xóa duplicate trong transaction lab

Mẫu cleanup:

```sql
BEGIN;

WITH ranked AS (
    SELECT
        c.contact_id,
        ROW_NUMBER() OVER (
            PARTITION BY c.tenant_id, c.external_key
            ORDER BY
                c.received_at DESC,
                c.contact_id DESC
        ) AS rn
    FROM lesson_unique.raw_contacts AS c
)
DELETE FROM lesson_unique.raw_contacts AS c
USING ranked AS r
WHERE c.contact_id = r.contact_id
  AND r.rn > 1
RETURNING
    c.contact_id,
    c.tenant_id,
    c.external_key;

-- Chỉ để học, hoàn nguyên thao tác xóa:
ROLLBACK;
```

Trong ứng dụng thật, không nên mặc định xóa bảng **raw**: nhiều kiến trúc cần giữ toàn bộ lần nhận dữ liệu để audit/replay, sau đó ghi bản canonical vào một bảng khác có UNIQUE. Đối với bảng canonical có constraint, cleanup và tạo index cần kế hoạch migration để ngăn dữ liệu trùng tái phát.

### Vì sao phải có khóa chính để xóa?

`contact_id` là định danh hàng ổn định trong thao tác DELETE. Nếu join chỉ theo `(tenant_id, external_key)`, bạn có nguy cơ chọn **cả bản muốn giữ** khi nhiều hàng cùng khóa.

## 47. Thêm constraint sau cleanup

Về mặt ý tưởng, sau khi dữ liệu đã sạch theo quy tắc `NULLS NOT DISTINCT`:

```sql
ALTER TABLE lesson_unique.raw_contacts
ADD CONSTRAINT uq_raw_contacts_tenant_external
UNIQUE NULLS NOT DISTINCT (tenant_id, external_key);
```

**Câu này sẽ thất bại nếu chạy ngay sau phần 46**, vì phần cleanup dùng `ROLLBACK` và dữ liệu trùng vẫn còn. Muốn thử thành công, cần làm sạch thật **trong lab** rồi kiểm tra lại trước khi tạo constraint.

### Cleanup xong vẫn phải chặn writer trùng

Nếu có writer đang hoạt động giữa lúc cleanup và tạo index, dữ liệu trùng có thể xuất hiện lại. Cần quyết định:

- Tạm dừng hoặc điều phối ingestion.
- Thiết kế ghi idempotent ngay từ trước migration.
- Chọn phương pháp xây index concurrently phù hợp.
- Có chiến lược retry và xử lý lỗi nếu unique build bị conflict.

“Xóa duplicate một lần” không đủ để bảo đảm bất biến về lâu dài.

## 48. UNIQUE và dữ liệu canonical so với raw data

Một thiết kế pipeline hợp lý:

```text
Nguồn API / message queue
         │
         ▼
raw_contacts
  - append-only
  - mỗi lần nhận có contact_id riêng
  - cho phép business key lặp để audit
         │
         │ normalize + deduplicate
         ▼
canonical_contacts
  - UNIQUE (tenant_id, external_key)
  - hoặc UNIQUE NULLS NOT DISTINCT
  - hoặc partial unique theo trạng thái
         │
         ▼
Ứng dụng nghiệp vụ / báo cáo
```

Nếu raw log cố ý giữ các sự kiện lặp, đặt unique constraint trên raw table sẽ làm mất khả năng audit của những lần nhận lại. Cần phân biệt **“khóa duy nhất của bản canonical”** và **“định danh vật lý mỗi lần nhận”**.

Một message có thể được gửi lại bởi cơ chế retry của queue. Dùng unique business key/idempotency key ở bảng canonical để chống nhân đôi hiệu ứng, không nhất thiết xóa mọi duplicate raw.

## 49. Một UPSERT idempotent cho bảng canonical

Ví dụ:

```sql
CREATE TABLE lesson_unique.canonical_contacts (
    tenant_id BIGINT NOT NULL,
    external_key TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    PRIMARY KEY (tenant_id, external_key)
);
```

Mẫu upsert:

```sql
INSERT INTO lesson_unique.canonical_contacts AS c (
    tenant_id,
    external_key,
    source_version,
    payload
)
VALUES (
    10,
    'A',
    42,
    '{"name":"An"}'::jsonb
)
ON CONFLICT (tenant_id, external_key)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    payload = EXCLUDED.payload
WHERE EXCLUDED.source_version > c.source_version;
```

Ý nghĩa:

- Chưa có key → insert.
- Có key và version mới hơn → update.
- Có key và version cũ hơn hoặc bằng → không ghi đè.

**Không dùng `received_at` nếu mục tiêu là version mới nhất của nguồn và message có thể đến không đúng thứ tự.**

### Concurrency

Ràng buộc unique bảo vệ key khi hai worker upsert đồng thời. PostgreSQL điều phối conflict/locking phù hợp, thay vì để hai worker cùng SELECT không thấy rồi cùng INSERT trùng.

### NULL external_key

Ví dụ canonical đặt `external_key NOT NULL` vì đó là một phần primary key và danh tính bắt buộc. Nếu business key tùy chọn, cần mô hình khác, không thể dùng primary key nullable.

## 50. UNIQUE và lỗi transaction trong JDBC

Khi PostgreSQL trả `23505` trong một transaction tường minh, transaction thường chuyển sang trạng thái failed. Nếu tiếp tục gửi SQL mà không rollback, driver có thể nhận `25P02`:

```text
INSERT duplicate key → SQLSTATE 23505
SELECT khác         → SQLSTATE 25P02
ROLLBACK            → session trở lại trạng thái hợp lệ
```

### Ví dụ phân loại lỗi

```java
try {
    preparedStatement.executeUpdate();
} catch (SQLException e) {
    String state = e.getSQLState();
    if ("23505".equals(state)) {
        // Unique violation: map sang conflict nghiệp vụ phù hợp.
    } else if ("23502".equals(state)) {
        // NOT NULL violation.
    } else if ("23514".equals(state)) {
        // CHECK violation.
    }
    throw e;
}
```

Đoạn code giả định `preparedStatement` hợp lệ và exception được truyền đến transaction owner để rollback.

### Mẫu JDBC transaction

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        String sql = """
            INSERT INTO lesson_unique.accounts(
                tenant_id, email, display_name
            )
            VALUES (?, ?, ?)
            """;

        try (PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setLong(1, 10L);
            ps.setString(2, "an@example.test");
            ps.setString(3, "Tên hiển thị");
            ps.executeUpdate();
        }

        conn.commit();
    } catch (SQLException | RuntimeException failure) {
        try {
            conn.rollback();
        } catch (SQLException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
        throw failure;
    }
}
```

Ví dụ dùng Java text blocks, giả định `DataSource`, imports và phương thức có xử lý `SQLException`. Trong Spring/JPA, để transaction manager xử lý rollback thay vì tự điều khiển JDBC connection thuộc framework.

### Chi tiết lỗi pgJDBC

Với driver PostgreSQL, một số exception còn chứa metadata như tên constraint, schema/table và detail. Khi cần phân biệt **unique email** với **unique primary key**, nên đọc trường cấu trúc do driver cung cấp thay vì parse message tiếng Anh.

**Không trả toàn bộ DETAIL của lỗi database trực tiếp cho người dùng cuối** nếu chứa email, khóa nghiệp vụ hoặc thông tin hệ thống nhạy cảm.

## 51. Spring và quản lý UNIQUE

Trong ứng dụng Spring Data/JPA:

- Unique constraints có thể được khai báo qua migration hoặc ORM schema metadata.
- Một lỗi unique có thể được bọc thành exception thuộc tầng Spring persistence, ví dụ `DataIntegrityViolationException`.
- Tầng service cần xác định conflict nào là **business validation** và trả thông báo phù hợp.
- Nếu transaction đã lỗi ở PostgreSQL, **bắt exception rồi tiếp tục dùng cùng transaction** có thể gây `25P02`; cần rollback hoặc xử lý conflict qua UPSERT/savepoint phù hợp.
- Nếu ORM flush thất bại, persistence context có thể không còn an toàn để tiếp tục thao tác; rollback transaction và kết thúc scope thường là lựa chọn đúng.

### Đừng tin mỗi @Column(unique=true)

Annotation như `@Column(unique = true)` có thể giúp mô tả schema khi dùng ORM DDL generation, nhưng trong môi trường production việc migration/constraint tồn tại thực tế phải được kiểm chứng bằng catalog. Nếu server không có constraint, Java annotation không thể ngăn hai service ghi trùng do race.

### API idempotency

Một endpoint tạo đơn cần idempotency key để retry an toàn:

```text
POST /orders
Idempotency-Key: req-123
```

Nếu database bảo vệ unique key theo merchant/tenant, các request lặp có thể được xử lý có kiểm soát. Nhưng cần lưu kết quả nghiệp vụ, trạng thái request và logic trả kết quả nhất quán; **unique constraint một mình không định nghĩa toàn bộ giao thức idempotency**.

## 52. Đặc điểm hiệu năng của unique index

Unique index là công cụ bảo đảm đúng dữ liệu, đồng thời có thể hỗ trợ query:

```sql
SELECT account_id
FROM lesson_unique.accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

Index hỗ trợ constraint `uq_accounts_tenant_email` có thể được optimizer sử dụng để tìm key.

### Chi phí đi kèm

- Mỗi insert phải kiểm tra không có key xung đột theo quy tắc index.
- Update cột key có thể cần kiểm tra và cập nhật index.
- Index tiêu thụ disk space/cache và sinh WAL.
- Bảng nhiều index hơn thường ghi chậm hơn, nhất là workload nhiều update.
- Nếu một khóa rất “nóng”, nhiều writer tranh chấp cùng key có thể phải chờ nhau.

### Unique index không đảm bảo query luôn dùng index

Với bảng rất nhỏ, sequential scan có thể rẻ hơn. Với query không có predicate thích hợp, planner cũng có thể không chọn index.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT account_id
FROM lesson_unique.accounts
WHERE tenant_id = 10
  AND email = 'an@example.test';
```

`EXPLAIN ANALYZE` **thực sự chạy query**. Ở ví dụ là SELECT nên an toàn hơn. Với `DELETE`/`UPDATE` phải xét tác động, transaction và rollback trước khi chạy.

## 53. UNIQUE không tự bảo đảm “một hàng cho mỗi tenant”

Ràng buộc:

```sql
UNIQUE (tenant_id, email)
```

không giới hạn **số account trong tenant** — mỗi tenant có thể có hàng triệu email khác nhau. Nếu nghiệp vụ thật là **tối đa một owner chính** cho tenant, cần một bất biến khác.

Ví dụ:

```sql
CREATE TABLE lesson_unique.tenant_memberships (
    membership_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    role_name TEXT NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE UNIQUE INDEX ux_one_active_owner_per_tenant
ON lesson_unique.tenant_memberships (tenant_id)
WHERE role_name = 'OWNER'
  AND active;
```

Index này cho phép:

- Nhiều user/member roles khác nhau trong tenant.
- Tối đa **một hàng OWNER active** mỗi tenant.
- Các OWNER đã inactive không tham gia kiểm tra.

### Predicate có thể thay đổi theo nghiệp vụ

Nếu hệ thống cho phép nhiều owner cùng lúc, constraint trên là **sai**. Trước khi tạo unique index, cần xác định yêu cầu chính xác. Database chỉ bảo vệ điều bạn đã khai báo, không tự đoán ý định của product team.

## 54. UNIQUE và partitioning theo thời gian

Một tình huống khác: bảng sự kiện partition theo tháng. Bạn muốn `external_event_id` duy nhất **toàn bộ lịch sử**.

Nếu partition key là tháng sự kiện và unique key chỉ gồm `external_event_id`, PostgreSQL không có cơ chế global uniqueness trực tiếp như trên bảng không partition, trong các giới hạn declarative partitioned tables đã nêu.

Một thiết kế có thể cân nhắc:

```text
event_keys
  UNIQUE (tenant_id, external_event_id)
  └── registry của key toàn hệ thống

events_2026_11
events_2026_12
...
  └── bảng partition lưu payload
```

Tuy nhiên, registry phải được cập nhật **trong cùng giao thức transaction** để tránh tạo key mà không ghi event hoặc ngược lại. Đây là một quyết định kiến trúc, không phải mẹo index miễn phí.

Đôi khi quy tắc nghiệp vụ thực chỉ cần unique theo **tenant và tháng**, khi đó unique key bao gồm partition key có thể là mô hình đúng. Cần hỏi rõ phạm vi duy nhất.

## 55. UNIQUE và quyền/DDL trong production

Tạo constraint/index yêu cầu quyền owner/schema phù hợp. Khi chạy migration:

1. Sử dụng role được phép thay đổi schema.
2. Kiểm tra transactions đang giữ khóa bảng.
3. Phân biệt `CREATE INDEX` và `CREATE INDEX CONCURRENTLY`.
4. Kiểm tra index đã tạo có đúng predicate/expression/null semantics.
5. Bảo đảm application code hiểu SQLSTATE `23505` và xử lý transaction rollback.
6. Không tạo duplicate indexes do nhiều migration/ORM DDL tools cùng chạy.
7. Kiểm tra tên constraint/index không xung đột với object khác trong schema.
8. Theo dõi hiệu năng ghi và contention sau deploy.

### DDL có thể chặn ứng dụng

`ALTER TABLE ... ADD CONSTRAINT UNIQUE` trực tiếp trên bảng lớn có thể cần lock và quét dữ liệu. Trên workload quan trọng, cân nhắc xây unique index concurrently rồi attach khi index hợp lệ, nhưng phải hiểu bước attach vẫn có lock.

**Không thực hiện trên production chỉ vì cú pháp chạy nhanh trong lab vài dòng.**

## 56. Quy trình thiết kế unique rule từ yêu cầu nghiệp vụ

Hãy trả lời những câu hỏi:

1. **Đối tượng nào cần duy nhất?** Email, SKU, external ID, cặp tenant + key?
2. **Phạm vi duy nhất ở đâu?** Toàn database, mỗi tenant, mỗi organization, mỗi ngày, chỉ active?
3. **Có được NULL không?** Nếu có, cho phép nhiều NULL hay tối đa một NULL?
4. **Có chuẩn hóa giá trị trước so sánh không?** Lowercase, trim, unicode, collation?
5. **Có cần xóa mềm không?** Quy tắc có áp dụng cho bản đã xóa?
6. **Cần ON CONFLICT không?** Nếu có, arbiter có phải non-deferrable và infer được không?
7. **Có FK tham chiếu không?** Khóa unique có đủ điều kiện làm referenced key?
8. **Bảng partitioned không?** Unique key có bao gồm partition key?
9. **Dữ liệu hiện có đã sạch chưa?** Hàng null/trùng theo biểu thức có bao nhiêu?
10. **Có writer đồng thời trong migration không?** Ai chịu trách nhiệm idempotency?

Từ câu trả lời chọn giải pháp:

| Yêu cầu | Giải pháp điển hình |
|---|---|
| Key bắt buộc và duy nhất | `NOT NULL` + `UNIQUE` hoặc `PRIMARY KEY`. |
| Key tùy chọn, nhiều NULL hợp lệ | `UNIQUE` mặc định. |
| Key tùy chọn, tối đa một NULL trong phạm vi | `UNIQUE NULLS NOT DISTINCT` (PG15+). |
| Duy nhất chỉ khi active | Partial unique index. |
| Duy nhất theo giá trị chuẩn hóa | Expression unique index, generated canonical key hoặc type/collation phù hợp. |
| Duy nhất theo chuẩn hóa và active | Partial expression unique index. |
| Cần hoán đổi giá trị tạm thời | `DEFERRABLE UNIQUE` khi phù hợp. |
| Cần UPSERT | Non-deferrable unique index/constraint với conflict target tương ứng. |
| Bảng lớn đang ghi | Migration có kế hoạch, cân nhắc `CREATE UNIQUE INDEX CONCURRENTLY`. |

## 57. Những lỗi và hiểu nhầm phổ biến

### 57.1. “UNIQUE nghĩa là chỉ có một NULL”

Sai với ngữ nghĩa mặc định của PostgreSQL. Muốn tối đa một null, dùng `NULLS NOT DISTINCT` trên PostgreSQL 15+ hoặc thiết kế thay thế.

### 57.2. “NULL = NULL là true”

Sai. `NULL = NULL` trả unknown/SQL null. Dùng `IS NULL` hoặc `IS NOT DISTINCT FROM` tùy mục đích.

### 57.3. “UNIQUE(tenant_id,email) nghĩa là email global unique”

Sai. Hai tenant khác nhau có thể trùng email.

### 57.4. “UNIQUE(tenant_id,email,deleted_at) cấm hai hàng active”

Không đúng với `deleted_at IS NULL` theo mặc định. Dùng partial unique index cho active, hoặc `NULLS NOT DISTINCT` nếu đúng toàn bộ quy tắc mong muốn.

### 57.5. “NULLS NOT DISTINCT giống NOT NULL”

Sai. `NULLS NOT DISTINCT` vẫn có thể cho một hàng null trên khóa một cột; `NOT NULL` không cho null nào.

### 57.6. “Nếu thêm id vào unique thì chống trùng email tốt hơn”

Nếu viết `UNIQUE(id,email)` với `id` vốn duy nhất, tổ hợp gần như không ngăn email lặp. Khóa phải gồm **các thành phần định nghĩa trùng**, không phải thêm PK vô điều kiện.

### 57.7. “Tạo UNIQUE constraint rồi còn cần unique index y hệt”

Thường không. Constraint đã được hỗ trợ bằng index tương ứng; index trùng gây overhead.

### 57.8. “Partial unique index là constraint và dùng ON CONSTRAINT được”

Không. Partial unique index không phải named unique constraint để tham chiếu bằng `ON CONSTRAINT`.

### 57.9. “INCLUDE(display_name) làm display_name tham gia unique key”

Không. Included column không phải key column cho uniqueness.

### 57.10. “DEFERRABLE UNIQUE tốt hơn cho mọi trường hợp”

Không. Có chi phí/semantics riêng và không dùng làm arbiter cho `ON CONFLICT DO UPDATE`.

### 57.11. “UNIQUE không cần xét khi UPDATE”

Sai. Update key, chuyển deleted_at thành null hoặc thay đổi cột trong expression/predicate đều có thể gây `23505`.

### 57.12. “SELECT không thấy record thì insert không thể trùng”

Sai dưới concurrency. Transaction khác có thể đang insert cùng key nhưng chưa commit; unique enforcement phải phối hợp với transaction đó.

### 57.13. “ON CONFLICT DO NOTHING RETURNING sẽ trả hàng cũ”

Không. Nếu không insert, `RETURNING` không tự trả hàng đã tồn tại.

### 57.14. “ON CONFLICT tự xử lý mọi constraint”

Không. Nó xử lý conflict phù hợp với cú pháp/arbiter; những lỗi NOT NULL, CHECK, foreign key hoặc unique index khác có thể vẫn xảy ra.

### 57.15. “CREATE INDEX CONCURRENTLY không bao giờ gây chờ”

Sai. Nó giảm một số blocking nhưng vẫn có giai đoạn phối hợp/chờ và rủi ro tài nguyên.

### 57.16. “Index INVALID chắc chắn không còn ảnh hưởng gì”

Không đúng trong mọi giai đoạn build unique index concurrently thất bại. Cần xem `indisvalid`/`indisready` và dọn index lỗi có kiểm soát.

### 57.17. “NOT VALID dùng được để thêm UNIQUE trên bảng có duplicate”

Không theo cách dùng với CHECK/FK. Uniqueness cần được cưỡng chế/kiểm tra bởi unique index.

### 57.18. “Cứ GROUP BY COUNT>1 là duplicate bị UNIQUE mặc định chặn”

Không với khóa có NULL: `GROUP BY` gom null trong khi UNIQUE mặc định cho phép nhiều null.

### 57.19. “Tất cả email chỉ cần lower là chuẩn hóa đúng”

Không nhất thiết. Locale/Unicode/collation và chính sách nhận diện email cần được xác định rõ.

### 57.20. “Unique index trên partitioned table tự unique toàn cluster”

Không. Cần xét partition key và giới hạn unique constraints trên declarative partitioning.

### 57.21. “Có UNIQUE thì không cần xử lý SQLException”

Sai. Constraint bảo vệ database, còn ứng dụng vẫn phải rollback transaction, phân loại `23505` và thông báo đúng.

### 57.22. “Khác constraint name thì chắc chắn không liên quan index”

Constraint và supporting index có quan hệ catalog. Tên có thể bị đổi/attach theo migration; kiểm tra `pg_constraint`, `pg_index` thay vì suy đoán bằng chuỗi tên.

### 57.23. “Index-only scan chắc chắn xảy ra vì có INCLUDE”

Không. Planner, visibility map và workload quyết định. INCLUDE chỉ tạo cơ hội.

### 57.24. “Unique trên email là bảo đảm account an toàn”

Không. Unique không thay thế xác thực người dùng, verification email, password hashing, authorization, RLS hay các chính sách bảo mật khác.

## 58. Bài tập thực hành

### Bài 1 — UNIQUE một cột

Tạo bảng có `email TEXT UNIQUE`. Thử hai email giống nhau, ghi SQLSTATE của lỗi. Vì sao không nên chỉ dựa vào SELECT trước INSERT?

### Bài 2 — UNIQUE hai cột

Với `UNIQUE (tenant_id,email)`, thử cùng email ở tenant 10 và 20; sau đó thử cùng email hai lần trong tenant 10. Giải thích kết quả.

### Bài 3 — NULL mặc định

Chèn hai hàng `optional_code=NULL` vào `codes_default`. Vì sao cả hai được phép? `NULL = NULL` trả kết quả gì?

### Bài 4 — NULLS NOT DISTINCT

Trên PostgreSQL 15+, chèn hai hàng null vào `codes_strict`. So sánh với bài 3. Vì sao nó không tương đương `NOT NULL`?

### Bài 5 — NULL trong khóa kết hợp

Với `UNIQUE NULLS NOT DISTINCT (tenant_id,external_ref)`, kiểm tra `(10,NULL)` hai lần và `(20,NULL)` một lần. Kết quả nào hợp lệ?

### Bài 6 — Phiên bản PostgreSQL

Dùng `server_version_num` xác định server có hỗ trợ `NULLS NOT DISTINCT` không. Nếu không, đề xuất giải pháp partial unique index cho cột nullable một phạm vi.

### Bài 7 — PRIMARY KEY và UNIQUE

Tạo bảng có `id BIGINT PRIMARY KEY`, `email TEXT UNIQUE` và `nickname TEXT`. Giải thích cột nào bắt buộc non-null, cột nào có thể có nhiều null và vì sao.

### Bài 8 — Soft delete sai

Cho bảng `members_wrong` có `UNIQUE (tenant_id,email,deleted_at)`. Chèn hai hàng active với deleted_at null. Dự đoán có conflict hay không và giải thích bằng semantics NULL mặc định.

### Bài 9 — Partial unique active

Tạo index `UNIQUE (tenant_id,email) WHERE deleted_at IS NULL`. Thử bản active và bản đã xóa cùng email; thử hai bản active. Nêu bất biến được bảo vệ.

### Bài 10 — Restore soft delete

Một tenant đã có member active email A và một member deleted email A. Nếu đổi deleted_at của member deleted về NULL, chuyện gì xảy ra? Vì sao partial unique index kiểm tra cả UPDATE?

### Bài 11 — Expression index

Tạo unique index theo `(tenant_id, lower(btrim(email)))`. Thử `'An@Example.Test'` và `' an@example.test '`. Giải thích chính sách chuẩn hóa và những giới hạn của nó.

### Bài 12 — Expression + partial

Thiết kế unique index cho email không phân biệt hoa/thường của các member active, còn member deleted được phép trùng. Viết `CREATE UNIQUE INDEX` hoàn chỉnh.

### Bài 13 — INCLUDE

Tạo unique index `(tenant_id,email) INCLUDE(display_name)`. Hai hàng cùng key nhưng khác display_name có được phép không? Vì sao?

### Bài 14 — DEFERRABLE swap

Tạo bảng position với `UNIQUE(position) DEFERRABLE INITIALLY IMMEDIATE`. Trong transaction, đặt `SET CONSTRAINTS ... DEFERRED` và đổi vị trí hai hàng. So sánh với constraint NOT DEFERRABLE.

### Bài 15 — Deferred failure tại COMMIT

Trong lab, tạo hai hàng cuối cùng vẫn trùng khóa dưới constraint deferrable đang deferred. Lỗi có thể xuất hiện lúc nào? Ứng dụng JDBC phải xử lý kết quả COMMIT thế nào?

### Bài 16 — ON CONFLICT DO NOTHING

Thử insert một khóa đã tồn tại với `ON CONFLICT (tenant_id,email) DO NOTHING RETURNING account_id`. Vì sao RETURNING không trả ID hàng cũ?

### Bài 17 — ON CONFLICT DO UPDATE

Viết UPSERT cho account theo `(tenant_id,email)` chỉ cập nhật display_name khi conflict. Phân tích vì sao điều này có thể không phù hợp với endpoint đăng ký tài khoản.

### Bài 18 — Partial index inference

Viết `ON CONFLICT (tenant_id,email) WHERE deleted_at IS NULL DO NOTHING` cho bảng `members`. Phân biệt WHERE ở conflict target với WHERE sau DO UPDATE.

### Bài 19 — Expression index inference

Viết conflict target cho index `(tenant_id, lower(btrim(email))) WHERE deleted_at IS NULL`. Vì sao không sử dụng `ON CONFLICT ON CONSTRAINT <index_name>`?

### Bài 20 — Kiểm tra duplicate có NULL

Trên `raw_contacts`, dùng `GROUP BY tenant_id,external_key HAVING COUNT(*)>1`. Giải thích vì sao nhóm có null được báo trùng nhưng `UNIQUE` mặc định có thể vẫn cho phép dữ liệu ấy.

### Bài 21 — Dedup và giữ bản mới nhất

Dùng `ROW_NUMBER() OVER (PARTITION BY tenant_id,external_key ORDER BY received_at DESC,contact_id DESC)` để giữ một bản/key. Nếu nguồn có source_version, bạn sẽ thay đổi thứ tự thế nào?

### Bài 22 — Cleanup an toàn

Viết `SELECT` xem trước các hàng `rn>1` rồi mô tả `DELETE ... USING` với khóa chính và `ROLLBACK` trong transaction lab. Vì sao không nên xóa trực tiếp trong bảng raw audit?

### Bài 23 — Migration trên bảng lớn

Mô tả cách dùng `CREATE UNIQUE INDEX CONCURRENTLY` để giảm chặn writer, kiểm tra `indisvalid`, sau đó attach `UNIQUE USING INDEX` khi đủ điều kiện. Tại sao không chạy concurrently trong `BEGIN`?

### Bài 24 — Index INVALID

Một build unique index concurrently thất bại do duplicate. Bạn sẽ kiểm tra những cột nào trong `pg_index` và làm gì trước khi thử xây lại?

### Bài 25 — Foreign key

Vì sao FK có thể tham chiếu khóa primary/unique phù hợp, nhưng không tự tham chiếu một expression partial unique index như một khóa đối tượng?

### Bài 26 — Partitioned table

Thiết kế bảng partition theo `tenant_id`. Tại sao primary key/unique constraint trên parent thường phải bao gồm partition key? Đề xuất cách bảo vệ event_id global unique nếu business yêu cầu.

### Bài 27 — Concurrent INSERT

Hai session cùng insert business_key chưa commit. Tại sao một phiên có thể phải chờ phiên kia và sau đó nhận `23505` dù trước đó SELECT không thấy hàng?

### Bài 28 — SQLSTATE và JDBC

Viết catch cho `SQLException` phân loại `23505`, `23502`, `23514`. Khi gặp lỗi trong manual transaction, vì sao phải rollback trước khi dùng lại connection?

### Bài 29 — Catalog metadata

Truy vấn `pg_constraint` và `pg_indexes` để so sánh: một UNIQUE constraint, một partial unique index và một expression unique index. Vì sao `information_schema.table_constraints` không hiển thị mọi index?

### Bài 30 — Thiết kế tổng hợp

Một nền tảng nhiều tenant có yêu cầu: member active không trùng email không phân biệt hoa thường; member deleted được giữ lịch sử; external_ref tùy chọn nhưng mỗi tenant chỉ cho tối đa một null; các request tạo phải idempotent. Hãy đề xuất:

1. Schema cột và các NOT NULL/CHECK quan trọng.
2. Partial expression unique index cho email active.
3. `UNIQUE NULLS NOT DISTINCT` cho external_ref và phạm vi tenant (nếu semantics đúng).
4. UPSERT/conflict handling không làm mất bản ghi cũ.
5. Chiến lược migration khi dữ liệu cũ đã trùng.
6. Cách kiểm thử hai request đồng thời.

## Kết luận

Trong PostgreSQL, **`UNIQUE` không chỉ là thuộc tính “cấm trùng” của một cột** mà là ràng buộc trên **tập khóa**, với những quy tắc cụ thể về **NULL**, biểu thức, predicate, collation và transaction. Một unique constraint được hỗ trợ bởi unique index; một unique index tạo trực tiếp còn có thể biểu đạt **partial uniqueness** và **expression-based uniqueness** mà constraint thông thường không diễn đạt trực tiếp.

Quy tắc quan trọng nhất là: **`UNIQUE` mặc định cho phép nhiều `NULL`**. Khi yêu cầu “tối đa một NULL” hoặc “hai tổ hợp có NULL ở cùng vị trí phải bị coi là trùng”, dùng **`NULLS NOT DISTINCT` trên PostgreSQL 15+**. Nếu yêu cầu là chỉ cấm trùng trong nhóm bản ghi **đang hoạt động**, dùng **partial unique index với predicate đúng nghiệp vụ**, thay vì mù quáng thêm `deleted_at` vào khóa unique. Với email/mã cần chuẩn hóa, dùng expression/generated canonical key hoặc kiểu/collation phù hợp sau khi thống nhất quy tắc so sánh.

Trong triển khai thực tế, hãy phân biệt **PRIMARY KEY**, **NOT NULL**, **UNIQUE constraint**, **partial/expression unique index** và **DEFERRABLE UNIQUE**; xác định giới hạn của **`ON CONFLICT`**, **foreign key** và **partitioned tables**. Trước khi thêm unique rule vào dữ liệu có sẵn, phải tìm trùng theo **đúng NULL semantics**, xem trước bản ghi sẽ loại, và chọn chiến lược migration/CONCURRENTLY có kiểm soát. Dưới concurrency, unique index là lớp bảo vệ bất biến cuối cùng mà `SELECT trước INSERT` không thể thay thế.

Một thiết kế tốt bắt đầu bằng câu hỏi **“thế nào mới được coi là cùng một đối tượng nghiệp vụ?”**, rồi mới lựa chọn cột khóa, cách đối xử với NULL, phạm vi active/tenant và giao thức ghi. Khi quy tắc này được diễn đạt rõ trong PostgreSQL và ứng dụng xử lý `23505` đúng cách, tính nhất quán dữ liệu sẽ vững hơn ngay cả khi có nhiều request và worker ghi đồng thời.
