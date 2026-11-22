# Chỉ mục duy nhất, chỉ mục biểu thức và chỉ mục có điều kiện theo hệ quản trị

Một chỉ mục (*index*) trong SQL thường được nhắc đến như công cụ giúp tìm hàng nhanh hơn. Nhưng không phải chỉ mục nào cũng chỉ phục vụ tốc độ. **Chỉ mục duy nhất** (*unique index*) còn bảo vệ một quy tắc toàn vẹn dữ liệu: không cho phép hai hàng có cùng khóa đã định nghĩa. **Chỉ mục biểu thức** (*expression/functional index*) lưu hoặc tổ chức khóa tính từ một biểu thức như `lower(email)`; nó có thể tăng tốc tìm kiếm hoặc kiểm soát tính duy nhất trên **giá trị đã biến đổi**. **Chỉ mục có điều kiện** (*partial/filtered index*) chỉ áp dụng cho **một tập con hàng** đáp ứng predicate, giúp index nhỏ hơn hoặc áp một quy tắc duy nhất chỉ với các hàng đang có hiệu lực.

Ba ý tưởng có thể kết hợp. Ví dụ quy tắc nghiệp vụ:

> Trong mỗi tenant, một email chỉ được có **một tài khoản chưa bị xóa mềm**, so sánh email không phân biệt chữ hoa/thường. Tài khoản đã xóa mềm được giữ trong lịch sử và có thể có email trùng.

Quy tắc đó không giải quyết tốt bằng một index đơn thuần trên `email`. Với PostgreSQL, ta có thể dùng:

```sql
CREATE UNIQUE INDEX ux_live_email_per_tenant
ON contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Một câu SQL ngắn này kết hợp **ba chiều**:

1. `UNIQUE`: các khóa giống nhau trong tập được index không được xuất hiện hai lần.
2. `lower(email)`: so sánh theo giá trị email đã chuyển chữ thường.
3. `WHERE deleted_at IS NULL`: chỉ kiểm tra những bản ghi **chưa xóa mềm**.

Tuy nhiên, cú pháp trên **không dùng nguyên xi ở mọi DBMS**. PostgreSQL/SQLite hỗ trợ partial index với `WHERE`; SQL Server có filtered index nhưng muốn dùng biểu thức làm khóa thường cần **computed column**; MySQL/MariaDB không có dạng filtered index tổng quát như vậy, thường dùng **generated column kết hợp UNIQUE và NULL**; Oracle có **function-based index** và có thể mô phỏng tính duy nhất có điều kiện bằng biểu thức `CASE`.

Bài học thuộc chương **Chỉ mục và kế hoạch** trong module **Database SQL**. Ta sẽ hiểu cách chỉ mục bảo vệ dữ liệu, khi nào optimizer có thể dùng chúng, cách thiết kế theo từng hệ và những sai lầm thường gặp về `NULL`, collation, điều kiện truy vấn, hiệu năng và di trú schema.

> Ví dụ thực hành chính theo **PostgreSQL**. Các đoạn MySQL, MariaDB, SQL Server, Oracle và SQLite được ghi nhãn riêng và giả định có bảng tương ứng; chúng là **các phương án thay thế**, không chạy chung nguyên văn trên một cơ sở dữ liệu. Thao tác tạo chỉ mục duy nhất có thể thất bại nếu dữ liệu đang chứa khóa trùng; hãy thử trên môi trường riêng trước khi thay đổi production.

## 1. Chỉ mục là gì và vì sao liên quan đến kế hoạch truy vấn?

Một bảng có thể được lưu theo cách khiến việc tìm một khóa cụ thể phải kiểm tra nhiều hàng. Một index tạo ra cấu trúc phụ, thường là B-tree đối với các trường hợp ví dụ, để DBMS tra cứu những khóa đã được tổ chức.

Ví dụ:

```sql
SELECT customer_id, customer_name
FROM customers
WHERE email = 'an@example.test';
```

Nếu có chỉ mục thích hợp trên `email`, optimizer **có thể** dùng index để tìm vị trí hàng cần đọc. Nhưng **không có cam kết** rằng mỗi truy vấn có điều kiện `WHERE` sẽ dùng index. Nếu bảng rất nhỏ, cần trả phần lớn dữ liệu, hoặc thống kê cho thấy quét tuần tự rẻ hơn, optimizer có thể chọn scan.

Phân biệt rõ ba lớp:

| Khái niệm | Câu hỏi nó giải quyết |
|---|---|
| **Index definition** | Những khóa nào được lưu và hàng nào được index? |
| **Constraint/uniqueness enforcement** | Dữ liệu mới có bị từ chối vì vi phạm khóa không? |
| **Query plan** | Truy vấn đọc sẽ dùng index hay scan, theo thứ tự nào, với chi phí ước tính bao nhiêu? |

Một **unique index** có thể đang thực thi quy tắc không cho trùng dù câu `SELECT` tương ứng **không dùng** nó. Tính toàn vẹn và lựa chọn kế hoạch truy vấn là hai vấn đề liên quan nhưng không đồng nhất.

### 1.1. Index không làm thay đổi kết quả logic của SELECT

Với cùng trạng thái dữ liệu và cùng ngữ nghĩa SQL, việc thêm/bớt một **index bình thường** chỉ nhằm thay đổi cách tìm dữ liệu, không làm `SELECT` tự trả thêm/bớt hàng. Ngoại lệ quan trọng của bài học là một **unique index** còn thay đổi **những trạng thái dữ liệu được phép tồn tại trong tương lai**.

Không dựa vào thứ tự ngẫu nhiên do index để hiển thị dữ liệu:

```sql
-- Không bảo đảm thứ tự kết quả chỉ vì có index trên email.
SELECT customer_id, email FROM customers;

-- Cần ORDER BY nếu giao diện yêu cầu thứ tự xác định.
SELECT customer_id, email
FROM customers
ORDER BY email, customer_id;
```

## 2. So sánh ba loại chỉ mục

| Loại index | Định nghĩa khóa | Tập hàng được index | Tác dụng nổi bật |
|---|---|---|---|
| Index thông thường | Cột/bộ cột | Thường toàn bộ bảng | Hỗ trợ truy vấn, JOIN, lọc, sắp xếp |
| **Unique index** | Cột/bộ cột | Thường toàn bộ bảng | Ngăn các khóa bằng nhau cùng tồn tại |
| **Expression index** | Biểu thức như `lower(email)` | Thường toàn bộ bảng | Hỗ trợ điều kiện trên kết quả biểu thức |
| **Partial/filtered index** | Cột hoặc biểu thức | Chỉ các hàng thỏa predicate `WHERE` | Nhỏ hơn, có thể tối ưu tập đang quan tâm |
| **Unique expression + partial** | Cột và biểu thức, có `UNIQUE` | Tập thỏa `WHERE` | Ràng buộc duy nhất theo **khóa đã biến đổi** trên **một phần dữ liệu** |

Các loại trong bảng không loại trừ nhau. Một index có thể **vừa unique, vừa expression, vừa partial**, như ví dụ `tenant_id, lower(email) WHERE deleted_at IS NULL`.

### 2.1. Index khác constraint ở mức mô hình dữ liệu

Viết:

```sql
CREATE TABLE users (
    user_id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

thể hiện **ràng buộc nghiệp vụ**: khóa chính phải duy nhất, email cũng phải duy nhất. Nhiều DBMS dùng một unique index để thực thi ràng buộc đó.

Viết:

```sql
CREATE UNIQUE INDEX ux_users_email ON users(email);
```

tạo trực tiếp một **index duy nhất**. Hai hình thức có thể thực thi tính duy nhất tương tự với khóa đơn giản, nhưng không phải lúc nào thay thế được về **metadata constraint, tên đối tượng, khóa ngoại, deferrable semantics hoặc công cụ migration**.

Với PostgreSQL, một `UNIQUE` constraint thường tự sinh unique B-tree index. **Không cần tạo thêm một unique index trùng y hệt chỉ để “tăng tốc hơn”**: index trùng tạo chi phí bảo trì và dung lượng mà không mang lại quy tắc mới.

## 3. Bộ dữ liệu thực hành PostgreSQL

Ta cần một bảng có nhiều tenant, email và cơ chế xóa mềm:

```sql
-- PostgreSQL, bảng TEMP tồn tại trong phiên đang kết nối.
CREATE TEMP TABLE demo_contacts (
    contact_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    email TEXT NOT NULL,
    display_name TEXT NOT NULL,
    contact_status TEXT NOT NULL
        CHECK (contact_status IN ('ACTIVE', 'INACTIVE')),
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO demo_contacts
    (tenant_id, email, display_name, contact_status, deleted_at)
VALUES
    (10, 'An@Example.test',   'An',         'ACTIVE',   NULL),
    (10, 'binh@example.test', 'Bình',       'ACTIVE',   NULL),
    (10, 'CHI@example.test',  'Chi',        'INACTIVE', NULL),
    (20, 'an@example.test',   'An tenant20','ACTIVE',   NULL),
    (10, 'an@example.test',   'Old An',     'INACTIVE',
         TIMESTAMPTZ '2026-10-01 00:00:00+00'),
    (10, 'old@example.test',  'Old record', 'INACTIVE',
         TIMESTAMPTZ '2026-09-01 00:00:00+00');

SELECT
    contact_id, tenant_id, email, contact_status, deleted_at
FROM demo_contacts
ORDER BY contact_id;
```

Bảng dữ liệu về mặt logic:

| tenant_id | email | Trạng thái | deleted_at |
|---:|---|---|---|
| 10 | An@Example.test | ACTIVE | `NULL` |
| 10 | binh@example.test | ACTIVE | `NULL` |
| 10 | CHI@example.test | INACTIVE | `NULL` |
| 20 | an@example.test | ACTIVE | `NULL` |
| 10 | an@example.test | INACTIVE | 2026-10-01 |
| 10 | old@example.test | INACTIVE | 2026-09-01 |

Quan sát:

- Hai tenant có thể sử dụng cùng email `an@example.test`.
- Tenant 10 còn giữ **hàng lịch sử đã xóa** dùng email An.
- `contact_status = 'INACTIVE'` **không đồng nghĩa** `deleted_at IS NOT NULL`. Chi vẫn chưa bị xóa mềm nên vẫn nằm trong tập email cần bảo vệ.
- ID do PostgreSQL sinh; không sử dụng ID được dự đoán khi đánh giá kết quả.

**Quy tắc nghiệp vụ sẽ thực thi:** trong mỗi tenant, **chỉ hàng có `deleted_at IS NULL`** được phép chiếm một email, không phân biệt kiểu chữ.

## 4. Unique index cơ bản: một cột và khóa ghép

Tạo bảng khác để thử unique đơn giản:

```sql
CREATE TEMP TABLE demo_skus (
    sku_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL,
    sku_name TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_demo_skus_sku
ON demo_skus (sku);

INSERT INTO demo_skus (sku, sku_name)
VALUES ('SKU-001', 'Mouse'),
       ('SKU-002', 'Keyboard');
```

Nếu chạy:

```sql
-- PostgreSQL: THỬ RIÊNG, bị từ chối vì duplicate SKU.
INSERT INTO demo_skus (sku, sku_name)
VALUES ('SKU-001', 'Mouse imported twice');
```

PostgreSQL phát hiện cùng `sku = 'SKU-001'` trong unique index và báo lỗi unique violation, thường SQLSTATE `23505`.

### 4.1. Không dùng SELECT trước làm lớp chống trùng duy nhất

Một quy trình kém an toàn:

```text
SELECT ... WHERE sku = 'SKU-001'
Nếu chưa có:
    INSERT ...
```

Hai transaction có thể cùng kiểm tra “chưa có” rồi cùng `INSERT`. **Unique index tại DB** mới là lớp phân xử quyết định khi có ghi đồng thời. Tùy nghiệp vụ, PostgreSQL có thể dùng `INSERT ... ON CONFLICT` để chọn bỏ qua hoặc cập nhật khi xung đột.

### 4.2. Unique index nhiều cột

Giả sử một mã SKU chỉ cần duy nhất **trong mỗi tenant**, không phải toàn hệ thống:

```sql
CREATE TEMP TABLE demo_tenant_skus (
    tenant_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    sku_name TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_demo_tenant_skus
ON demo_tenant_skus (tenant_id, sku);

INSERT INTO demo_tenant_skus (tenant_id, sku, sku_name)
VALUES (10, 'SKU-001', 'Mouse tenant10'),
       (20, 'SKU-001', 'Mouse tenant20');
```

Hai hàng hợp lệ vì khóa là **cặp `(tenant_id, sku)`**, không chỉ `sku`.

Nhưng:

```sql
-- THỬ RIÊNG: không hợp lệ vì cặp (10, SKU-001) đã tồn tại.
INSERT INTO demo_tenant_skus (tenant_id, sku, sku_name)
VALUES (10, 'SKU-001', 'Duplicate mouse');
```

sẽ vi phạm unique index.

**Nguyên tắc multi-tenant:** nếu ID nghiệp vụ chỉ duy nhất bên trong tenant, phải đưa **đầy đủ khóa phạm vi** vào unique index, vào điều kiện JOIN, vào `ON CONFLICT` và vào quy tắc phân quyền. Unique index không tự biết tenant hiện tại từ session ứng dụng.

### 4.3. Unique không phải primary key

`PRIMARY KEY` thường đòi hỏi khóa không NULL, một bảng chỉ có một khai báo primary key; trong khi một bảng có thể có **nhiều quy tắc UNIQUE** độc lập, ví dụ:

```sql
CREATE TABLE example_users (
    user_id BIGINT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    external_id TEXT UNIQUE
);
```

Một bảng vừa cần khóa chính ổn định, vừa có các candidate keys khác. Không chọn một unique index biểu thức tùy ý làm primary key nếu DBMS không cho phép hoặc nếu biểu thức không mang ý nghĩa danh tính hàng phù hợp.

## 5. UNIQUE và NULL theo phương ngữ

`NULL` không phải một giá trị thông thường như số 0 hay chuỗi rỗng. Các DBMS xử lý `NULL` trong unique index/constraint **không hoàn toàn giống nhau**.

### 5.1. PostgreSQL: mặc định nhiều NULL được phép

```sql
CREATE TEMP TABLE demo_external_ids (
    row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id TEXT UNIQUE,
    description TEXT NOT NULL
);

INSERT INTO demo_external_ids (external_id, description)
VALUES (NULL, 'No code A'),
       (NULL, 'No code B'),
       ('X-1', 'Has code');
```

Trong PostgreSQL, hai hàng `external_id NULL` được phép theo unique constraint mặc định. Nhưng thêm một hàng `external_id = 'X-1'` sẽ bị chặn.

Khi chỉ muốn khóa các giá trị đã biết là duy nhất, chính sách này thường hợp lý: **nhiều hàng chưa có mã** vẫn có thể tồn tại.

### 5.2. PostgreSQL 15+: NULLS NOT DISTINCT

Nếu nghiệp vụ yêu cầu **tối đa một hàng có `external_id NULL`**, PostgreSQL 15+ cho dùng:

```sql
-- PostgreSQL 15+
CREATE TEMP TABLE demo_single_missing_code (
    row_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    external_id TEXT,
    CONSTRAINT uq_single_missing_code
        UNIQUE NULLS NOT DISTINCT (external_id)
);
```

`NULLS NOT DISTINCT` buộc hệ coi những giá trị `NULL` là **không phân biệt** đối với kiểm tra tính duy nhất. Khi đã có một hàng `external_id NULL`, chèn hàng `NULL` thứ hai sẽ xung đột.

Một unique index tạo trực tiếp cũng có thể chỉ rõ chính sách:

```sql
-- PostgreSQL 15+
CREATE UNIQUE INDEX ux_demo_code_null_equal
ON demo_external_ids (external_id) NULLS NOT DISTINCT;
```

**Không chạy câu thứ hai ngay trên dữ liệu `demo_external_ids` đã có hai NULL**, vì việc tạo index sẽ thất bại do dữ liệu không đáp ứng chính sách mới. Đây là ví dụ **cú pháp và yêu cầu migration**, không phải bước tiếp nối có thể áp ngay vào dữ liệu hiện tại.

### 5.3. SQL Server: NULL trong UNIQUE khác PostgreSQL

Trong SQL Server, một `UNIQUE` index/constraint trên **một cột nullable** thông thường chỉ cho phép **một hàng với `NULL`** trong cột đó.

Nếu cần “không bắt buộc email nhưng các email đã biết phải duy nhất”, có thể dùng **unique filtered index**:

```sql
-- SQL Server: giả sử dbo.optional_emails tồn tại.
CREATE UNIQUE NONCLUSTERED INDEX ux_known_email
ON dbo.optional_emails (email)
WHERE email IS NOT NULL;
```

Khi đó các hàng `email IS NULL` không nằm trong index; các email không NULL phải duy nhất. Với khóa nhiều cột, quy tắc NULL/điều kiện của SQL Server còn có các chi tiết riêng; tránh suy tổng quát từ trường hợp một cột.

### 5.4. MySQL/MariaDB và SQLite

MySQL/MariaDB và SQLite thông thường cho phép **nhiều `NULL`** trong các unique keys theo cách thiết kế phổ biến của chúng. Chính sự khác biệt này thường được tận dụng để mô phỏng unique có điều kiện bằng **generated column trả NULL** cho những hàng ngoài tập cần ràng buộc.

### 5.5. Oracle: cần chú ý khóa ghép với NULL

Trong Oracle, B-tree index thông thường không lưu các mục có **toàn bộ key expressions là NULL**, và quy tắc unique đối với một khóa ghép chứa một số `NULL` có điểm khác các DBMS khác. Vì vậy **đừng kết luận** mọi DBMS đều cho số lượng NULL giống nhau trong unique composite key.

Khi mô phỏng conditional uniqueness trên Oracle bằng `CASE`, một mẫu an toàn là làm cho **toàn bộ biểu thức khóa đều NULL** đối với hàng nằm ngoài tập cần ràng buộc, và các biểu thức khóa có giá trị rõ ràng đối với hàng cần ràng buộc.

## 6. Expression index: chỉ mục trên giá trị được tính toán

Giả sử ứng dụng tìm email không phân biệt hoa/thường:

```sql
SELECT contact_id, tenant_id, email
FROM demo_contacts
WHERE lower(email) = 'an@example.test';
```

Một index thông thường trên `email` không nhất thiết hỗ trợ tối ưu điều kiện `lower(email)` như tra cứu khóa gốc, vì truy vấn **áp một hàm lên cột**. PostgreSQL hỗ trợ **index trên biểu thức**:

```sql
CREATE INDEX ix_demo_contacts_lower_email
ON demo_contacts (lower(email));
```

Với index này, PostgreSQL có thể sử dụng giá trị đã được tính của `lower(email)` để hỗ trợ truy vấn tìm kiếm.

### 6.1. Expression index khác cột được lưu riêng

Nếu không có expression index, DBMS có thể phải tính `lower(email)` cho nhiều hàng trong khi thực thi truy vấn. Khi có index biểu thức, giá trị khóa biểu thức được **duy trì khi dữ liệu được ghi/đổi** và truy vấn có thể tìm qua index.

Đánh đổi:

- **Đọc:** có thể nhanh hơn nếu predicate/plan phù hợp.
- **Ghi:** INSERT/UPDATE phải tính lại khóa biểu thức và bảo trì index khi cần.
- **Dung lượng:** index thêm dữ liệu và metadata.
- **Quy tắc biểu thức:** hàm cần đáp ứng các yêu cầu về tính ổn định/deterministic/immutable tùy DBMS.

Không tạo một index riêng cho mọi hàm trên mọi cột. Chỉ tạo khi có yêu cầu truy vấn hoặc ràng buộc rõ ràng.

### 6.2. UNIQUE expression index

Không chỉ tra cứu nhanh, ta có thể ngăn hai email chỉ khác chữ hoa/thường:

```sql
-- PostgreSQL
CREATE UNIQUE INDEX ux_demo_unique_lower_email
ON some_contacts (lower(email));
```

Giả sử bảng `some_contacts` tồn tại, chỉ có dữ liệu phù hợp với quy tắc và cần **duy nhất toàn bảng**. Nếu đã có `'An@Example.test'`, chèn `'an@example.test'` sẽ xung đột.

**Không tạo trực tiếp index unique toàn bảng này trên `demo_contacts`**, vì bộ dữ liệu mẫu cố ý có email An ở nhiều tenant và trong lịch sử xóa mềm. Với bài toán đã nêu, phải **kết hợp tenant và điều kiện deleted_at**, trình bày ở phần sau.

### 6.3. Biểu thức nhiều cột

PostgreSQL hỗ trợ:

```sql
-- Ví dụ cú pháp; giả sử bảng people phù hợp.
CREATE INDEX ix_people_full_name
ON people ((lower(first_name) || ' ' || lower(last_name)));
```

Cặp ngoặc bên ngoài biểu thức ghép là cần thiết theo cách phân tích cú pháp. Truy vấn có biểu thức tương thích có thể dùng index:

```sql
SELECT *
FROM people
WHERE lower(first_name) || ' ' || lower(last_name)
    = 'nguyen van an';
```

**Đừng đánh đồng biểu thức này với một hệ thống tìm kiếm tên người đầy đủ:** tên có dấu, khoảng trắng kép, nhiều họ, locale/collation và dấu câu có thể làm quy tắc ghép khác ý nghĩa. Chỉ mục phải gắn với cách chuẩn hóa được nghiệp vụ chấp nhận.

### 6.4. Biểu thức phải phù hợp với truy vấn

Nếu index lưu `lower(email)` mà câu truy vấn viết:

```sql
WHERE email = 'an@example.test'
```

thì điều kiện **khác về ngữ nghĩa** với `lower(email) = ...` trong một collation phân biệt chữ hoa/thường. Optimizer không có nghĩa vụ dùng expression index cho một truy vấn không biểu đạt điều kiện tương ứng.

Tương tự:

```sql
WHERE upper(email) = 'AN@EXAMPLE.TEST'
```

không mặc nhiên tương đương ở mọi locale/collation với `lower(email) = ...` cho mục đích tối ưu.

## 7. Tính bất biến của biểu thức và các hàm không an toàn

Một expression index giả định khóa được tính từ hàng có ý nghĩa **ổn định** trong lúc lưu index.

Ví dụ PostgreSQL:

```sql
-- Minh họa điều KHÔNG làm:
CREATE INDEX ix_bad_recent
ON events ((created_at < CURRENT_TIMESTAMP));
```

`CURRENT_TIMESTAMP` thay đổi theo thời gian. Một hàng có thể chuyển từ “chưa cũ” sang “đã cũ” mà không có UPDATE nào trên hàng đó. Index không thể tự cập nhật khóa chỉ vì đồng hồ đã tiến sang phút mới. PostgreSQL thường yêu cầu hàm trong định nghĩa expression index phải **IMMUTABLE**; ví dụ dùng hàm theo thời gian hiện tại không phù hợp và bị từ chối.

Tương tự, partial index:

```sql
-- Không tạo theo kiểu dynamic time:
CREATE INDEX ix_bad_expiry
ON sessions (expires_at)
WHERE expires_at < CURRENT_TIMESTAMP;
```

sẽ không có ý nghĩa lưu trữ ổn định và không được PostgreSQL chấp nhận theo yêu cầu tính bất biến.

### 7.1. Giải pháp cho “dữ liệu hết hạn tính theo hôm nay”

Có thể xây index bình thường trên `expires_at`:

```sql
CREATE INDEX ix_sessions_expires_at
ON sessions (expires_at);
```

rồi truy vấn:

```sql
SELECT session_id
FROM sessions
WHERE expires_at < CURRENT_TIMESTAMP;
```

Index theo cột thời gian có thể hỗ trợ so sánh với **giá trị thời gian tại lúc query**, không cần thay đổi index mỗi giây.

Nếu thật sự cần một tập “đang hiệu lực” cố định, có thể lưu cột trạng thái được cập nhật bởi một quy trình có kiểm soát hoặc dùng thiết kế partition/retention phù hợp. Nhưng phải xác định độ trễ làm mới trạng thái và yêu cầu đồng nhất dữ liệu.

### 7.2. Đừng đánh tráo tính bất biến bằng khai báo hàm tùy tiện

PostgreSQL có phân loại hàm `IMMUTABLE`, `STABLE`, `VOLATILE`. Không gắn nhãn `IMMUTABLE` cho một hàm phụ thuộc timezone session, bảng khác hoặc đồng hồ chỉ để lách lỗi `CREATE INDEX`. Dữ liệu trong index có thể trở nên sai mà không được bảo trì đúng.

Tương tự, SQLite hạn chế expression/partial index tới **deterministic functions**; MySQL/MariaDB có giới hạn hàm trong generated columns/functional key parts; SQL Server có tiêu chí **deterministic/precise** cho indexed computed columns; Oracle cũng có quy tắc function-based index.

## 8. Partial index: chỉ lưu khóa của một tập con

Một partial index của PostgreSQL có mệnh đề `WHERE`:

```sql
CREATE INDEX ix_demo_live_tenant
ON demo_contacts (tenant_id)
WHERE deleted_at IS NULL;
```

Chỉ những hàng `deleted_at IS NULL` được đưa vào index này. Những hàng đã xóa mềm không có mục nhập ở index này.

Đây là **index có điều kiện phục vụ đọc**, chưa phải UNIQUE. Nó có thể hỗ trợ truy vấn:

```sql
SELECT contact_id, email
FROM demo_contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL;
```

### 8.1. Vì sao partial index có thể nhỏ hơn?

Giả sử bảng có 10 triệu hàng lịch sử, nhưng chỉ 500.000 hàng còn hiệu lực. Một index toàn bảng trên `tenant_id` có thể chứa mục nhập tương ứng mọi hàng. Partial index `WHERE deleted_at IS NULL` chỉ giữ mục nhập của hàng còn hiệu lực.

Lợi ích tiềm năng:

- Index nhỏ hơn.
- Ít trang index hơn khi query chỉ cần hàng đang hiệu lực.
- Có thể giảm chi phí bảo trì đối với các hàng không thuộc predicate.
- Thống kê và selectivity của tập con có thể phù hợp hơn với workload.

Nhưng cũng có chi phí: khi `deleted_at` đổi từ `NULL` sang timestamp, index phải loại bỏ/thay đổi mục nhập; khi khôi phục hàng, phải đưa mục nhập trở lại và có thể gặp unique conflict. **Không có cam kết partial index luôn nhanh hơn**; vẫn phải xem phân bố dữ liệu và kế hoạch query.

### 8.2. Predicate của index khác WHERE trong query

`WHERE` ở cuối `CREATE INDEX` quyết định **hàng nào được đưa vào index**.

`WHERE` ở `SELECT` quyết định **hàng nào truy vấn muốn trả về**.

Để optimizer dùng partial index, điều kiện của truy vấn phải đủ để chứng minh **mọi hàng cần thiết nằm trong tập được index**.

Ví dụ:

```sql
-- Index chỉ chứa deleted_at IS NULL.
CREATE INDEX ix_demo_live_email
ON demo_contacts (email)
WHERE deleted_at IS NULL;

-- Query A: điều kiện tương thích, có thể dùng index.
SELECT contact_id, email
FROM demo_contacts
WHERE email = 'binh@example.test'
  AND deleted_at IS NULL;

-- Query B: không có điều kiện deleted_at.
SELECT contact_id, email
FROM demo_contacts
WHERE email = 'binh@example.test';
```

Query B có thể cần cả hàng đang hoạt động **và** hàng đã xóa mềm, nên partial index không chứa đủ mọi ứng viên. Nó không thể tự thay thế index toàn bảng cho truy vấn đó.

### 8.3. Partial index không bảo đảm được dùng nếu predicate tương thích

Ngay cả Query A vẫn có thể được PostgreSQL lập kế hoạch bằng sequential scan nếu bảng nhỏ, tỷ lệ hàng trả về cao hoặc chi phí khác khiến scan hợp lý.

**Partial index eligibility ≠ index chosen by optimizer.**

## 9. Unique partial expression index: kết hợp ba ý tưởng

Áp dụng quy tắc bài toán chính cho bảng `demo_contacts`:

```sql
CREATE UNIQUE INDEX ux_demo_live_email_tenant
ON demo_contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Ý nghĩa:

- Tập hàng index: chỉ `deleted_at IS NULL`.
- Khóa index: cặp `(tenant_id, lower(email))`.
- Tính chất: không có hai hàng trong tập ấy cùng cặp khóa.

### 9.1. Dữ liệu hiện có có hợp lệ không?

| Trường hợp | Có được cùng tồn tại? | Lý do |
|---|---|---|
| Tenant 10 `An@Example.test`, chưa xóa | Có | Một hàng active đã có |
| Tenant 20 `an@example.test`, chưa xóa | Có | Tenant khác, cặp khóa khác |
| Tenant 10 `an@example.test`, đã xóa mềm | Có | Không thuộc partial index |
| Tenant 10 `AN@example.test`, chưa xóa thêm lần nữa | **Không** | `lower(email)` trùng trong cùng tenant |
| Tenant 10 `chi@example.test`, chưa xóa thêm lần nữa | **Không** | Trùng với `CHI@example.test` chưa xóa |
| Tenant 10 `old@example.test`, chưa xóa | Có, nếu chưa có live bản đó | Lịch sử cũ đã xóa không chiếm khóa live |

### 9.2. Thử chèn một email trùng theo case

```sql
-- PostgreSQL: THỬ RIÊNG, bị từ chối bởi unique index.
INSERT INTO demo_contacts
    (tenant_id, email, display_name, contact_status)
VALUES
    (10, 'aN@eXample.test', 'Another An', 'ACTIVE');
```

Mặc dù chuỗi không giống byte-for-byte với `An@Example.test`, biểu thức `lower(email)` tạo cùng khóa trong cùng tenant khi dùng quy tắc lower/collation đang áp dụng.

### 9.3. Thử chèn email giống ở tenant khác

```sql
BEGIN;

INSERT INTO demo_contacts
    (tenant_id, email, display_name, contact_status)
VALUES
    (30, 'AN@example.test', 'An tenant30', 'ACTIVE');

-- Đây là tenant khác nên không xung đột với tenant 10/20.
ROLLBACK;
```

### 9.4. Thử chèn thêm một hàng lịch sử

```sql
BEGIN;

INSERT INTO demo_contacts
    (tenant_id, email, display_name, contact_status, deleted_at)
VALUES
    (10, 'AN@example.test', 'Old imported copy', 'INACTIVE',
     TIMESTAMPTZ '2026-11-01 00:00:00+00');

-- deleted_at khác NULL: không thuộc partial unique index.
ROLLBACK;
```

Dữ liệu lịch sử có thể trùng khóa vì quy tắc nghiệp vụ chỉ ràng buộc những hàng chưa xóa mềm. Nếu hệ thống không được phép giữ hai bản lịch sử cùng email, **cần một ràng buộc khác**; partial unique index không tự bảo vệ các hàng nằm ngoài predicate.

### 9.5. Khôi phục hàng đã xóa mềm có thể gây unique violation

Ví dụ cố khôi phục hàng `Old An` ở tenant 10 bằng:

```sql
-- THỬ RIÊNG: có thể lỗi vì đã có An đang hoạt động ở tenant 10.
UPDATE demo_contacts
SET deleted_at = NULL
WHERE tenant_id = 10
  AND display_name = 'Old An';
```

Trước UPDATE, hàng lịch sử không nằm trong index. Sau UPDATE, nó được đưa vào partial index, nhưng `lower(email)` trùng khóa live hiện có. PostgreSQL từ chối để bảo toàn quy tắc.

Đây là một chức năng quan trọng của unique partial index: nó kiểm soát không chỉ `INSERT` mà cả những `UPDATE` **làm một hàng đi vào tập index**.

### 9.6. Xóa mềm hàng live giải phóng khóa duy nhất

Trong một transaction:

```sql
BEGIN;

UPDATE demo_contacts
SET deleted_at = TIMESTAMPTZ '2026-11-14 00:00:00+00'
WHERE tenant_id = 10
  AND email = 'An@Example.test'
  AND deleted_at IS NULL;

INSERT INTO demo_contacts
    (tenant_id, email, display_name, contact_status)
VALUES
    (10, 'an@example.test', 'Replacement An', 'ACTIVE');

-- Câu INSERT mới có thể hợp lệ vì hàng cũ đã rời tập live.
ROLLBACK;
```

Nhưng trong môi trường concurrent, hai transaction không thể tự bảo đảm cùng chiếm khóa live chỉ bằng việc `SELECT` trước. Hệ thống phải dựa vào unique index và xử lý xung đột/khóa. Trong trường hợp có FK hoặc lịch sử ngoài bảng, việc “thay thế tài khoản” còn cần quy tắc định danh và liên kết riêng.

## 10. Partial unique index khác UNIQUE constraint

Trong PostgreSQL:

```sql
ALTER TABLE demo_tenant_skus
ADD CONSTRAINT uq_tenant_sku UNIQUE (tenant_id, sku);
```

là ràng buộc duy nhất thông thường và sẽ tạo index hỗ trợ. **Nhưng** bảng `demo_tenant_skus` đã có index unique trên đúng cặp khóa: thêm constraint như trên sẽ tạo một cấu trúc unique trùng lặp không cần thiết; đây là ví dụ minh họa sự khác biệt cú pháp, **không phải hướng dẫn thêm nó vào dữ liệu mẫu**.

Với quy tắc “duy nhất nếu deleted_at IS NULL”:

```sql
CREATE UNIQUE INDEX ux_demo_live_email_tenant
ON demo_contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

đây là **unique partial expression index**. Không có dạng constraint PostgreSQL tương đương:

```sql
-- SAI: UNIQUE constraint không có WHERE theo cách này.
ALTER TABLE demo_contacts
ADD CONSTRAINT unique_live_email
UNIQUE (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Một unique constraint thông thường cần khóa cột thích hợp, không chứa predicate lọc như unique partial index. Expression index cũng không thể tự biến thành một UNIQUE constraint cột đơn giản bằng cách thay từ khóa.

### 10.1. Tác động tới khóa ngoại

Trong PostgreSQL, một foreign key tham chiếu tới phía đích phải nhắm khóa duy nhất phù hợp theo quy tắc FK (PK, unique constraint hoặc unique index không partial thích hợp). **Không dùng một unique partial index như khóa đích FK tổng quát** vì nó không chứng minh duy nhất cho những hàng nằm ngoài predicate.

Nếu FK cần tham chiếu một thực thể duy nhất ổn định, hãy dùng khóa chính `contact_id`/khóa ứng viên phù hợp của toàn bảng, không dùng email “duy nhất trong số hàng chưa xóa”.

### 10.2. Tác động tới ON CONFLICT

Một partial unique index không phải một constraint có thể gọi bằng tên trong `ON CONFLICT ON CONSTRAINT`. Thường dùng **index inference** bằng biểu thức và predicate:

```sql
INSERT INTO demo_contacts AS c
    (tenant_id, email, display_name, contact_status)
VALUES
    (10, 'AN@example.test', 'An updated', 'ACTIVE')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO UPDATE
SET display_name = EXCLUDED.display_name;
```

Dạng này nhờ PostgreSQL suy luận unique index phù hợp dựa trên `tenant_id`, `lower(email)` và predicate. Nó có thể cập nhật hàng live đang có ở tenant 10.

**Không viết:**

```sql
-- Không phải cách chỉ tên partial unique INDEX trong PostgreSQL.
ON CONFLICT ON CONSTRAINT ux_demo_live_email_tenant
DO UPDATE ...
```

vì `ux_demo_live_email_tenant` là **tên index**, không phải tên một constraint có thể tham chiếu bằng `ON CONSTRAINT`.

### 10.3. Nhánh DO UPDATE không tự cập nhật mọi trường

Trong ví dụ `DO UPDATE SET display_name = EXCLUDED.display_name`, chỉ `display_name` được cập nhật; email và tenant ở hàng hiện có không tự đổi. Nếu muốn đổi nhiều cột hoặc ràng buộc phiên bản, phải viết `SET`/`WHERE` tương ứng.

## 11. Predicate implication: vì sao optimizer không dùng partial index?

Xét index:

```sql
CREATE INDEX ix_demo_active_tenant
ON demo_contacts (tenant_id, email)
WHERE deleted_at IS NULL;
```

Truy vấn có:

```sql
SELECT contact_id
FROM demo_contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL;
```

về mặt tập hàng có thể dùng index vì điều kiện truy vấn **bao hàm** predicate của index.

Khác với:

```sql
SELECT contact_id
FROM demo_contacts
WHERE tenant_id = 10;
```

không thể dùng index partial làm nguồn duy nhất cho mọi hàng, vì truy vấn còn muốn cả lịch sử `deleted_at IS NOT NULL`.

### 11.1. Điều kiện tương đương toán học chưa chắc được nhận diện

Một optimizer không cần chứng minh mọi công thức tương đương bằng biến đổi toán học phức tạp. PostgreSQL chỉ nhận diện một số quan hệ đơn giản giữa điều kiện truy vấn và predicate index ở **thời điểm lập kế hoạch**.

Ví dụ partial index:

```sql
CREATE INDEX ix_demo_inactive
ON demo_contacts (tenant_id)
WHERE contact_status = 'INACTIVE';
```

Truy vấn:

```sql
SELECT contact_id
FROM demo_contacts
WHERE tenant_id = 10
  AND contact_status = 'INACTIVE';
```

có predicate khớp rõ với index. Nhưng truy vấn dùng những biểu thức tương đương không hiển nhiên, ví dụ viết qua `CASE` phức tạp, có thể khiến optimizer không suy ra được quan hệ. Khi hiệu năng phụ thuộc index, ưu tiên viết predicate đọc **rõ ràng và tương thích** với định nghĩa index.

### 11.2. Prepared statements và tham số

Giả sử partial index chứa:

```sql
WHERE contact_status = 'ACTIVE'
```

nhưng truy vấn viết:

```sql
WHERE contact_status = $1
```

Khi optimizer dùng **generic plan** phải phù hợp cho mọi giá trị của `$1`, nó không thể kết luận tham số luôn là `'ACTIVE'`, nên partial index có thể không được xem là phù hợp. PostgreSQL có cơ chế **custom plan** với tham số đã biết trong một số tình huống, nên không được khẳng định mọi prepared statement đều **không bao giờ** dùng partial index.

Để tránh lệ thuộc suy luận theo giá trị tham số, nếu ứng dụng luôn truy vấn tập đang hoạt động, có thể đặt predicate cố định trong SQL:

```sql
WHERE contact_status = 'ACTIVE'
  AND tenant_id = $1
```

và giữ `tenant_id` làm tham số. Kết quả vẫn phụ thuộc plan và thống kê, nhưng điều kiện của partial index đã xuất hiện minh bạch.

### 11.3. OR có thể khiến index không đủ bao phủ

```sql
WHERE deleted_at IS NULL
   OR tenant_id = 20
```

Truy vấn này còn cần những hàng tenant 20 đã xóa, nên partial index `WHERE deleted_at IS NULL` không tự bao phủ toàn bộ kết quả. Một plan có thể kết hợp nhiều đường truy cập hoặc dùng scan.

**Đừng biến câu SELECT để phù hợp index nếu việc đó làm đổi nghĩa nghiệp vụ.** Đúng dữ liệu luôn quan trọng hơn việc ép optimizer dùng một index cụ thể.

## 12. EXPLAIN và thống kê: kiểm chứng kế hoạch

Sau khi tạo index, quan sát bằng PostgreSQL:

```sql
EXPLAIN
SELECT contact_id, email
FROM demo_contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

Một index như `ux_demo_live_email_tenant` có thể là ứng viên tốt cho điều kiện này. Tuy nhiên bộ dữ liệu mẫu chỉ có vài hàng, nên PostgreSQL **hoàn toàn có thể chọn `Seq Scan`** mà vẫn là kế hoạch hợp lý.

Với dữ liệu thử đủ lớn và môi trường an toàn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id, email
FROM demo_contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

Quan sát:

- `Index Scan`, `Index Only Scan`, `Bitmap Index Scan` hay `Seq Scan`.
- `Index Cond`, `Filter` và số hàng bị loại.
- `actual rows` so với `estimated rows`.
- `Buffers` và thời gian truy cập.
- Phạm vi dữ liệu: bao nhiêu tenant, phần trăm hàng còn live, có skew không.

### 12.1. ANALYZE cập nhật thống kê

```sql
ANALYZE demo_contacts;
```

PostgreSQL cập nhật thống kê được dùng để ước lượng chi phí. Không nhất thiết có “index mới thì mọi plan tốt ngay”; thống kê bảng và expression distributions có thể ảnh hưởng ước tính.

### 12.2. Không đánh giá tốc độ chỉ bằng một câu trên bảng tạm

Trên bảng có 6 hàng, scan tuần tự thường nhanh. Trên bảng có 10 triệu hàng với chỉ 1% còn live, partial index có thể hữu ích hơn. Nhưng độ rộng hàng, cache, phân bố khóa, concurrency và tỷ lệ DML quyết định hiệu quả.

Đo workload thực tế và so sánh trước/sau cùng điều kiện, không chọn index chỉ từ trực giác “đã có WHERE thì chắc chắn nên tạo”.

## 13. PostgreSQL: INCLUDE và index-only scan

Một index có thể chứa **cột không thuộc khóa** nhằm giúp truy vấn đọc mà không luôn phải lấy dữ liệu từ heap.

```sql
-- PostgreSQL 11+, ví dụ trên bảng riêng để tránh index trùng.
CREATE INDEX ix_demo_live_lookup_covering
ON demo_contacts (tenant_id, lower(email))
INCLUDE (display_name)
WHERE deleted_at IS NULL;
```

`display_name` là cột `INCLUDE` để phục vụ đọc, **không phải** thành phần dùng để tìm khóa chính của index. Với unique index, cột `INCLUDE` **không tham gia kiểm tra tính duy nhất**:

```sql
-- Ví dụ cú pháp: uniqueness dựa trên tenant_id và lower(email),
-- KHÔNG dựa trên display_name.
CREATE UNIQUE INDEX ux_demo_live_covering
ON demo_contacts (tenant_id, lower(email))
INCLUDE (display_name)
WHERE deleted_at IS NULL;
```

**Không tạo cả hai index trên bảng thật chỉ vì ví dụ.** Chúng phần lớn trùng công dụng, làm tăng ghi/dung lượng. Chỉ lựa chọn cấu trúc phù hợp workload.

`Index Only Scan` không được đảm bảo chỉ vì index có cột `INCLUDE`: PostgreSQL còn cần xét tính hiển thị MVCC (visibility map), kế hoạch và những cột truy vấn yêu cầu.

## 14. PostgreSQL: xây chỉ mục trên bảng đang có dữ liệu

Tạo một unique index nghĩa là DBMS **kiểm tra dữ liệu đã tồn tại**. Nếu hai hàng trùng khóa, index creation không thể thành công với quy tắc yêu cầu.

### 14.1. Tìm duplicate trước

Với quy tắc unique live theo tenant + email lower-case:

```sql
SELECT
    tenant_id,
    lower(email) AS normalized_email,
    COUNT(*) AS duplicate_count
FROM demo_contacts
WHERE deleted_at IS NULL
GROUP BY tenant_id, lower(email)
HAVING COUNT(*) > 1
ORDER BY tenant_id, normalized_email;
```

Nếu truy vấn trả hàng, phải chọn quy tắc xử lý duplicate: gộp dữ liệu, đổi email, xác định hàng cần giữ, hay đánh dấu xóa mềm. Không chọn ngẫu nhiên bản ghi “sống sót” nếu liên quan FK hoặc audit.

### 14.2. CREATE INDEX và khóa

Một câu `CREATE INDEX` bình thường có thể khóa/chặn hoạt động ghi trên bảng trong quá trình xây index theo quy tắc PostgreSQL. Đối với bảng lớn đang hoạt động, PostgreSQL có:

```sql
-- PostgreSQL: không chạy trong transaction block.
CREATE UNIQUE INDEX CONCURRENTLY ux_live_email
ON contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

`CONCURRENTLY` được thiết kế để giảm mức chặn DML khi xây index, nhưng:

- Không được chạy trong transaction block thông thường.
- Có thể mất thời gian hơn và cần nhiều giai đoạn quét/chờ.
- Việc phát hiện duplicate khi build unique index vẫn có thể làm thất bại.
- Nếu thất bại, có thể để lại **index INVALID** cần xử lý.
- Không phải thao tác “không có khóa” hoặc “không có tác động production”.

**Ví dụ chỉ mô tả tính năng; không chạy trên bảng production nếu chưa có kế hoạch migration và theo dõi.**

### 14.3. Unique index cũng có thể gây tranh chấp khi ghi đồng thời

Nếu hai transaction cố chèn cùng cặp `(tenant_id, lower(email))` trong tập live, unique index phải phân xử. Một transaction có thể chờ transaction khác; cuối cùng một thao tác có thể thành công, thao tác còn lại có thể lỗi `23505` hoặc đi theo nhánh `ON CONFLICT`.

Không dùng một lần `SELECT NOT EXISTS` như bằng chứng chống trùng bền vững. **Ràng buộc tại DB** là thành phần quan trọng nhất để bảo vệ uniqueness dưới concurrent writes.

## 15. SQL Server: UNIQUE và filtered index

SQL Server có cú pháp **filtered index**, gần vai trò partial index của PostgreSQL nhưng giới hạn predicate và cách tham chiếu biểu thức khác.

### 15.1. Unique index thông thường

```sql
-- SQL Server, giả sử dbo.contact_codes có cột code.
CREATE UNIQUE NONCLUSTERED INDEX ux_contact_codes_code
ON dbo.contact_codes (code);
```

Với một cột nullable, SQL Server thông thường coi `NULL` như một giá trị trong unique constraint, nên index trên cột đó chỉ cho một `NULL`. Nếu muốn cho phép nhiều `NULL` và chỉ ràng buộc giá trị đã biết:

```sql
CREATE UNIQUE NONCLUSTERED INDEX ux_contact_codes_not_null
ON dbo.contact_codes (code)
WHERE code IS NOT NULL;
```

Chọn **một** index phù hợp với chính sách; không thêm cả hai nếu bản thân unique toàn bảng đã chặn NULL theo cách bạn không muốn.

### 15.2. Filtered unique index cho soft delete

Giả sử bảng:

```sql
-- SQL Server: ví dụ schema tương đương.
CREATE TABLE dbo.contacts (
    contact_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    tenant_id INT NOT NULL,
    email NVARCHAR(255) NOT NULL,
    display_name NVARCHAR(200) NOT NULL,
    deleted_at DATETIME2 NULL
);
```

Ta muốn unique email của hàng chưa xóa:

```sql
CREATE UNIQUE NONCLUSTERED INDEX ux_live_email_tenant
ON dbo.contacts (tenant_id, email)
WHERE deleted_at IS NULL;
```

Đây là **unique filtered index**. Nó chặn trùng `(tenant_id, email)` trong tập `deleted_at IS NULL`.

**Nhưng cách so sánh hoa/thường phụ thuộc collation.** Nếu cột `email` dùng collation case-insensitive, có thể không cần tự gọi `LOWER`. Nếu dùng case-sensitive collation và nghiệp vụ yêu cầu bỏ qua case, cần thiết kế một khóa chuẩn hóa rõ ràng.

### 15.3. Expression index trong SQL Server: computed column

SQL Server không dùng cú pháp PostgreSQL:

```sql
-- KHÔNG phải cú pháp SQL Server:
CREATE INDEX ix_email ON dbo.contacts (LOWER(email));
```

Một cách phổ biến là thêm **computed column**:

```sql
ALTER TABLE dbo.contacts
ADD email_key AS LOWER(email) PERSISTED;
```

rồi tạo index trên cột này:

```sql
CREATE UNIQUE NONCLUSTERED INDEX ux_live_email_key
ON dbo.contacts (tenant_id, email_key)
WHERE deleted_at IS NULL;
```

Bước này cần kiểm tra các quy tắc của SQL Server đối với **indexed computed columns**: tính deterministic, precise, kiểu dữ liệu/collation, SET options và quyền. `PERSISTED` là một lựa chọn để lưu giá trị tính toán theo schema; không phải mọi biểu thức đều được phép làm cột indexed chỉ vì có từ khóa đó.

### 15.4. Predicate của filtered index có giới hạn

SQL Server filtered index phù hợp với những predicate tương đối **đơn giản** trên một bảng. Tài liệu SQL Server nêu không hỗ trợ `LIKE` trong filter, không lấy cột tính toán làm **filter definition** và không áp filter trực tiếp cho một `PRIMARY KEY/UNIQUE constraint`, nhưng có thể tạo **index với thuộc tính UNIQUE** và `WHERE`.

Cụ thể: computed column có thể nằm trong **key hoặc INCLUDE**, còn filter nên tham chiếu cột gốc hỗ trợ điều kiện như `deleted_at IS NULL`. Đừng viết:

```sql
-- Không dùng biểu thức như thế này làm khóa trực tiếp trong
-- SQL Server CREATE INDEX, hoặc giả định filter tùy ý.
CREATE UNIQUE INDEX ux_bad
ON dbo.contacts (LOWER(email))
WHERE LOWER(email) LIKE 'a%';
```

### 15.5. Query planner SQL Server và filtered index

Với:

```sql
SELECT contact_id, email
FROM dbo.contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL;
```

filtered index có thể hữu ích. Tuy nhiên SQL Server có các lưu ý riêng về parameterization, filtered statistics và việc index có bao phủ cột được truy vấn hay không.

Ví dụ tài liệu Microsoft nêu trong một số kế hoạch truy vấn `IS NULL`, filtered index có thể không được dùng nếu cột lọc `deleted_at` không hiện diện trong key/INCLUDE khi cần. Không nên coi “predicate đúng” là lời hứa plan luôn chọn index.

Đối với truy vấn cụ thể, xem **actual execution plan**, IO/time và thống kê filtered index.

## 16. MySQL 8.0.13+: functional key parts

MySQL 8.0.13+ có **functional key parts** trong index. Khác PostgreSQL, biểu thức cần một lớp ngoặc riêng:

```sql
-- MySQL 8.0.13+, giả sử contacts.email là VARCHAR phù hợp.
CREATE INDEX ix_contacts_lower_email
ON contacts ((LOWER(email)));
```

Tạo unique functional index:

```sql
CREATE UNIQUE INDEX ux_contacts_lower_email
ON contacts ((LOWER(email)));
```

Ý nghĩa: không cho hai hàng có cùng kết quả `LOWER(email)` trong phạm vi toàn bảng, theo collation/type/NULL semantics đang áp dụng.

### 16.1. MySQL functional index có ràng buộc của generated columns

MySQL triển khai functional key parts thông qua cơ chế **hidden virtual generated columns**, nên:

- Biểu thức phải nằm trong cặp ngoặc bổ sung.
- Không dùng tùy ý hàm không xác định, biến session, subquery hoặc tham số.
- Biểu thức và kiểu kết quả phải phù hợp giới hạn index.
- Với biểu thức trên JSON có thể cần `CAST` ra kiểu khóa có độ dài phù hợp.
- Index unique có thể chứa functional key part, nhưng primary key không dùng trực tiếp functional key part theo cách như một cột stored PK.

### 16.2. MySQL không có filtered CREATE INDEX ... WHERE tổng quát

Không sao chép:

```sql
-- Không phải cú pháp filtered index phổ biến của MySQL 8.0:
CREATE UNIQUE INDEX ux_live_email
ON contacts (tenant_id, (LOWER(email)))
WHERE deleted_at IS NULL;
```

MySQL không hỗ trợ mệnh đề `WHERE` sau `CREATE INDEX` như PostgreSQL/SQLite/SQL Server filtered index. Nếu cần unique chỉ với hàng chưa xóa, hãy **mô phỏng bằng generated column trả NULL cho hàng lịch sử**.

### 16.3. Mô phỏng bằng generated column + unique key

Giả sử có bảng `contacts` chứa `tenant_id INT NOT NULL`, `email VARCHAR(255) NOT NULL` và `deleted_at DATETIME NULL`:

```sql
-- MySQL: thiết kế bổ sung cột generated.
ALTER TABLE contacts
ADD COLUMN live_email_key VARCHAR(255)
    GENERATED ALWAYS AS (
        CASE
            WHEN deleted_at IS NULL THEN LOWER(email)
            ELSE NULL
        END
    STORED,
ADD UNIQUE KEY ux_live_email_per_tenant
    (tenant_id, live_email_key);
```

Điều gì xảy ra?

- Hàng live: `live_email_key = LOWER(email)`, nên mỗi tenant chỉ có một khóa đó.
- Hàng deleted: `live_email_key = NULL`, vì vậy nhiều hàng lịch sử có cùng email có thể tồn tại khi unique index theo quy tắc NULL của MySQL.
- Khi khôi phục hàng lịch sử bằng `UPDATE deleted_at = NULL`, generated column đổi từ `NULL` sang email lower-case; unique key sẽ chặn nếu đang có live row trùng.

Đây là mô phỏng **tính duy nhất có điều kiện**, không đồng nhất hoàn toàn với một partial index về kích thước hay tối ưu truy vấn: index unique trên `(tenant_id, live_email_key)` vẫn có thể lưu các khóa chứa `NULL` theo cơ chế MySQL. Không nói nó chỉ index tập live giống PostgreSQL.

**Điều kiện:** cần kiểu/độ dài/collation của generated column phù hợp biểu thức, phiên bản hỗ trợ và dữ liệu đã được làm sạch. Với collation case-insensitive, `LOWER` có thể thừa về so sánh, nhưng vẫn phải chọn chính sách nhất quán.

### 16.4. Prefix index không phải ràng buộc duy nhất trên toàn chuỗi

MySQL hỗ trợ index theo **prefix** của chuỗi trong những trường hợp nhất định:

```sql
CREATE INDEX ix_email_prefix
ON contacts (email(20));
```

Nếu biến nó thành UNIQUE, uniqueness chỉ xét **phần prefix được index**, có thể chặn sai hai email khác nhau nhưng cùng 20 ký tự đầu. Đừng dùng unique prefix index để thay yêu cầu toàn bộ email duy nhất nếu nghiệp vụ không thực sự muốn so sánh theo prefix.

### 16.5. MySQL collation và functional expression

Một cột `VARCHAR` MySQL có thể dùng collation case-insensitive/accent-insensitive. Khi đó unique index thường trên chính cột có thể đã chặn những biến thể chữ theo collation mà không cần `LOWER`.

Nhưng **không đồng nhất “không phân biệt case” với “email giống nhau theo chuẩn nghiệp vụ”**; dấu tiếng Việt, Unicode normalization, khoảng trắng hoặc quy tắc địa chỉ email có thể phức tạp hơn. Chọn collation/normalization và kiểm thử các dữ liệu mà ứng dụng thật sử dụng.

## 17. MariaDB: indexed generated columns thay cho functional key parts trực tiếp

MariaDB có hệ thống **generated columns** với các dạng `VIRTUAL` và `PERSISTENT`/`STORED`. Trong nhiều phiên bản MariaDB, giải pháp được tài liệu hỗ trợ để index biểu thức là **định nghĩa generated column rồi lập index trên cột đó**; không giả định cú pháp functional key parts `((LOWER(email)))` của MySQL 8.0.13+ dùng nguyên xi.

Ví dụ MariaDB:

```sql
-- MariaDB: giả sử bảng contacts có cấu trúc tương ứng.
ALTER TABLE contacts
ADD COLUMN email_key VARCHAR(255)
    GENERATED ALWAYS AS (LOWER(email)) PERSISTENT,
ADD INDEX ix_contacts_email_key (email_key);
```

Với uniqueness có điều kiện theo soft delete:

```sql
ALTER TABLE contacts
ADD COLUMN live_email_key VARCHAR(255)
    GENERATED ALWAYS AS (
        CASE
            WHEN deleted_at IS NULL THEN LOWER(email)
            ELSE NULL
        END
    ) PERSISTENT,
ADD UNIQUE KEY ux_live_email_tenant
    (tenant_id, live_email_key);
```

Đây là các **phương án thay thế cho những schema tương ứng**. Nếu một bảng đã có cột `email_key` hay `live_email_key`, cần migration phù hợp; không chạy liên tiếp để tạo cột trùng.

### 17.1. Vì sao generated column cần định nghĩa ổn định?

MariaDB có các yêu cầu về tính **deterministic** và tính nhất quán theo `sql_mode` khi index generated column. Một biểu thức tạo khóa thay đổi theo session setting có thể làm index sai hoặc bị từ chối tạo ở phiên bản nhất định.

MariaDB 11.8+ cải thiện việc optimizer nhận diện một số biểu thức khớp với generated column đã index; trên các phiên bản cũ hơn, viết query **tham chiếu trực tiếp cột generated** thường dễ dự đoán khả năng dùng index hơn.

Ví dụ:

```sql
SELECT contact_id, email
FROM contacts
WHERE tenant_id = 10
  AND live_email_key = 'an@example.test';
```

Không suy từ việc PostgreSQL nhận ra index `lower(email)` mà MariaDB mọi phiên bản cũng tự ánh xạ `WHERE LOWER(email)=...` tới generated-column index.

### 17.2. MariaDB không có partial-index WHERE tổng quát như PostgreSQL

Cú pháp:

```sql
CREATE INDEX ... ON contacts (...) WHERE deleted_at IS NULL;
```

không phải lựa chọn có thể giả định cho MariaDB. Sử dụng generated column/unique index khi cần **uniqueness có điều kiện**, và thiết kế index thường hoặc giải pháp phân vùng phù hợp nếu mục tiêu chính là **tăng tốc truy vấn tập con**.

## 18. Oracle: function-based index và conditional uniqueness qua CASE

Oracle Database có **function-based indexes**:

```sql
-- Oracle: giả sử CONTACTS có cột EMAIL.
CREATE INDEX ix_contacts_lower_email
ON contacts (LOWER(email));
```

Một function-based unique index cũng có thể ràng buộc giá trị đã biến đổi:

```sql
CREATE UNIQUE INDEX ux_contacts_lower_email
ON contacts (LOWER(email));
```

Đối với yêu cầu unique **chỉ khi chưa xóa**, Oracle không dùng tổng quát `CREATE INDEX ... WHERE deleted_at IS NULL` theo cùng cú pháp PostgreSQL. Một kỹ thuật lâu đời là tạo **unique function-based index trên biểu thức `CASE`**.

### 18.1. CASE chỉ tạo khóa khi hàng còn live

```sql
-- Oracle: giả sử TENANT_ID, EMAIL NOT NULL,
-- DELETED_AT nullable.
CREATE UNIQUE INDEX ux_live_email_tenant
ON contacts (
    CASE WHEN deleted_at IS NULL THEN tenant_id ELSE NULL END,
    CASE WHEN deleted_at IS NULL THEN LOWER(email) ELSE NULL END
);
```

Với hàng đang live:

```text
(tenant_id, LOWER(email))
```

Với hàng đã xóa mềm:

```text
(NULL, NULL)
```

Oracle B-tree không lưu entry khi **tất cả các key expressions đều NULL**. Những hàng lịch sử không chiếm khóa trong index; tính duy nhất được áp dụng với những hàng live có đủ khóa. Vì vậy biểu thức `CASE` có thể đóng vai trò tương đương **conditional uniqueness**, dù không dùng syntax `WHERE` của partial index.

### 18.2. Vì sao phải CASE cả tenant_id?

Nếu chỉ viết:

```sql
-- Không phải mẫu mong muốn cho mọi trường hợp Oracle:
CREATE UNIQUE INDEX ux_bad
ON contacts (
    tenant_id,
    CASE WHEN deleted_at IS NULL THEN LOWER(email) END
);
```

hàng đã xóa vẫn có `tenant_id` khác NULL, nên composite key không phải toàn NULL. Tùy Oracle NULL semantics với composite unique keys, kết quả có thể **không cho phép số hàng lịch sử trùng như mong muốn**.

Để diễn đạt rõ “hàng bị xóa không nằm trong tập ràng buộc”, làm **tất cả key expressions trả NULL** đối với hàng bị xóa.

### 18.3. Oracle partial index theo partition không đồng nghĩa WHERE arbitrary

Oracle có tính năng về **partial indexes đối với bảng partitioned** trong những bối cảnh nhất định. Không đồng nhất khái niệm đó với `CREATE INDEX ... WHERE predicate` linh hoạt của PostgreSQL/SQLite. Bài toán conditional uniqueness tùy trạng thái hàng có thể giải bằng function-based `CASE` như trên.

### 18.4. Query plan và thống kê function-based index

Oracle có optimizer và yêu cầu thống kê/phân tích của riêng mình đối với function-based index. Không suy rằng mọi truy vấn `WHERE LOWER(email) = ...` tự chọn index. Cần đối chiếu execution plan, selectivity, function determinism, collation/NLS và các quyền/hàm được gọi.

Nếu dùng hàm do ứng dụng tự định nghĩa trong index, phải đảm bảo tính deterministic đúng trên thực tế; sửa hàm hoặc thay đổi ngữ nghĩa có thể khiến index không còn phản ánh đúng khóa.

## 19. SQLite: expression indexes và partial indexes

SQLite có hai tính năng rất hữu ích:

- **Partial indexes** từ phiên bản **3.8.0**.
- **Indexes on expressions** từ phiên bản **3.9.0**.

Do đó với SQLite phù hợp phiên bản, có thể viết gần giống PostgreSQL:

```sql
-- SQLite 3.9.0+ (để có cả partial và expression index).
CREATE UNIQUE INDEX ux_live_email_tenant
ON contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Tính duy nhất chỉ áp dụng trong tập `deleted_at IS NULL`, dựa trên cặp khóa `tenant_id` và `lower(email)`.

### 19.1. SQLite yêu cầu deterministic expressions

SQLite không cho những chức năng không deterministic hoặc hàm phụ thuộc dữ liệu ngoài bảng xuất hiện tùy tiện trong expression index hay partial index predicate. Các ví dụ bị hạn chế gồm subqueries, bind parameters và non-deterministic functions.

Trên SQLite, một ứng dụng tự đăng ký user-defined function làm deterministic phải bảo đảm **thực sự deterministic**, nếu không index có thể trở nên không nhất quán với dữ liệu.

### 19.2. SQLite optimizer không tự biến đổi mọi biểu thức đại số

SQLite nhấn mạnh rằng planner của nó thường cần **biểu thức trong truy vấn trùng cấu trúc với biểu thức trong index** để dùng expression index.

Ví dụ:

```sql
CREATE TABLE demo_numbers (
    x INTEGER NOT NULL,
    y INTEGER NOT NULL
);

CREATE INDEX ix_demo_sum ON demo_numbers (x + y);
```

Truy vấn:

```sql
SELECT * FROM demo_numbers
WHERE x + y = 100;
```

có thể dùng `ix_demo_sum`. Nhưng:

```sql
SELECT * FROM demo_numbers
WHERE y + x = 100;
```

dù `x+y` và `y+x` tương đương toán học với số nguyên, SQLite không mặc nhiên coi hai biểu thức là **cùng biểu thức index** để tối ưu. Query planner không phải bộ chứng minh đại số tổng quát.

### 19.3. Partial-index implication ở SQLite có quy tắc nhận diện giới hạn

Ví dụ:

```sql
CREATE INDEX ix_demo_active
ON contacts (tenant_id, email)
WHERE deleted_at IS NULL;
```

Query có `WHERE deleted_at IS NULL` có thể dùng index. Nếu query không xác định `deleted_at` thì partial index không đủ bao phủ. SQLite có những quy tắc suy luận predicate cụ thể và có thể không nhận diện mọi điều kiện tương đương được viết khác cách.

### 19.4. SQLite LOWER và NOCASE cần lưu ý Unicode

SQLite cài đặt `LOWER` và `NOCASE` mặc định chủ yếu xử lý trường hợp ASCII, trừ khi mở rộng bằng chức năng/collation như ICU. Không giả định `lower(email)` trong SQLite cho kết quả Unicode giống PostgreSQL, Oracle hoặc MySQL với mọi ngôn ngữ.

Nếu hệ thống có yêu cầu Unicode case-folding nghiêm ngặt, cần chọn cách chuẩn hóa và collation có **hợp đồng phiên bản** và kiểm tra dữ liệu thật.

### 19.5. Kiểm tra bằng EXPLAIN QUERY PLAN

```sql
EXPLAIN QUERY PLAN
SELECT contact_id, email
FROM contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

SQLite có thể hiển thị hành vi `SEARCH ... USING INDEX` khi chọn index. Không ép một kết quả EXPLAIN cụ thể cho bảng nhỏ; SQLite cũng có thống kê và kế hoạch thay đổi theo phiên bản.

## 20. Bảng so sánh ngắn các phương ngữ

| DBMS | Unique index | Expression/functional index | Partial/filtered theo `WHERE` | Cách làm unique live email |
|---|---|---|---|---|
| **PostgreSQL** | Có, UNIQUE constraint thường tự sinh index | Có, `lower(email)`, expression B-tree | Có, `CREATE INDEX ... WHERE ...` | `UNIQUE (tenant_id, lower(email)) WHERE deleted_at IS NULL` |
| **SQL Server** | Có; NULL semantics khác PG | Thường dùng **indexed computed column** | Có, **filtered index** | Computed `email_key` + `UNIQUE INDEX ... WHERE deleted_at IS NULL` |
| **MySQL 8.0.13+** | Có | Có **functional key parts** `((expr))` | Không có dạng filtered WHERE tổng quát | Generated `live_email_key` trả NULL khi deleted + UNIQUE |
| **MariaDB** | Có | Dùng **indexed generated column** theo phiên bản | Không có dạng filtered WHERE tổng quát | Generated `live_email_key` + UNIQUE |
| **Oracle** | Có | Có **function-based index** | Không có dạng arbitrary WHERE giống PG; partition partial là khái niệm khác | Unique function-based index với `CASE` trả toàn NULL khi deleted |
| **SQLite 3.9.0+** | Có | Có expression index | Có partial index từ 3.8.0 | `UNIQUE (tenant_id, lower(email)) WHERE deleted_at IS NULL` |

Bảng nêu **năng lực chính**, không liệt kê mọi engine/kiểu bảng/giới hạn phiên bản. Ví dụ MariaDB có nhiều nhánh phát triển và MySQL với từng storage engine/collation khác nhau; kiểm tra cú pháp, quyền và version cụ thể trước khi đưa migration vào production.

## 21. Thiết kế case-insensitive uniqueness: lựa chọn collation hay LOWER?

Dùng `lower(email)` là cách dễ dạy, nhưng không phải luôn là cách tối ưu để xác định “cùng một email” trong ứng dụng quốc tế.

### 21.1. Cách A: unique theo collation

Ở những DBMS/collation **case-insensitive**, unique index trên `email` đã có thể coi `'An@Example.test'` và `'an@example.test'` là trùng, tùy collation.

Ví dụ trong SQL Server, các collation tên có `_CI` thường thể hiện case-insensitive, nhưng còn nhiều đặc tính accent/width/kana và quy tắc Unicode khác. MySQL cũng có những collation `_ci` và `_ai_ci` ảnh hưởng phép so sánh.

Ưu điểm: có thể không cần cột phát sinh hay biểu thức. Nhược điểm: ngữ nghĩa có thể phụ thuộc cấu hình DB và nâng cấp collation, không phải mọi hệ có cùng bảng quy tắc.

### 21.2. Cách B: expression index trên LOWER

Với PostgreSQL:

```sql
CREATE UNIQUE INDEX ux_demo_lower_email
ON some_contacts (lower(email));
```

Ưu điểm: quy tắc hiển thị rõ trong định nghĩa index. Nhưng hàm `lower` vẫn phụ thuộc locale/collation và không tự giải quyết mọi vấn đề chuẩn hóa email.

### 21.3. Cách C: lưu email_normalized do ứng dụng/DB tạo

```sql
-- Ý tưởng mô hình:
email_original   = 'An@Example.test'
email_normalized = 'an@example.test'
```

Dữ liệu nguồn giữ nguyên để hiển thị, cột chuẩn hóa được dùng tìm kiếm/unique theo chính sách đã định nghĩa.

Cần đảm bảo hai cột luôn nhất quán (generated column hoặc trigger/ứng dụng có kiểm soát), xử lý version của thuật toán chuẩn hóa và kiểm soát backfill khi thay đổi chính sách.

### 21.4. Email có những quy tắc ngoài SQL

Tên miền DNS không phân biệt case, nhưng phần local-part theo chuẩn có những khả năng phức tạp hơn và nhiều nhà cung cấp còn có quy tắc dấu chấm/plus addressing riêng. Không tự xóa dấu chấm hoặc phần `+tag` khỏi mọi email mà không có hợp đồng nghiệp vụ.

Bài học đang dùng `lower(email)` như ví dụ **expression index**, không tuyên bố đó là bộ chuẩn hóa email hoàn chỉnh cho mọi hệ.

## 22. Partial unique index và soft delete: các cạnh tranh dữ liệu

Một trường hợp race condition:

```text
Giao dịch A: kiểm tra không có email live của tenant 10
Giao dịch B: kiểm tra không có email live của tenant 10
Giao dịch A: INSERT email mới
Giao dịch B: INSERT cùng email
```

Nếu chỉ có `SELECT NOT EXISTS`, cả hai có thể cùng thấy “chưa có” tùy thời điểm và isolation. Unique index là lớp phân xử và sẽ chặn trạng thái có hai hàng live cùng khóa.

### 22.1. Upsert và partial conflict target

PostgreSQL có thể dùng:

```sql
INSERT INTO demo_contacts AS c
    (tenant_id, email, display_name, contact_status)
VALUES
    (10, 'an@example.test', 'Updated An', 'ACTIVE')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO UPDATE SET display_name = EXCLUDED.display_name
RETURNING contact_id, tenant_id, email, display_name;
```

Nếu có hàng live cùng khóa, thao tác cập nhật tên hàng đó theo cách đã khai báo. Nhưng nếu bạn muốn một **hàng mới** thay vì cập nhật hồ sơ cũ, `DO UPDATE` có thể sai nghiệp vụ; cần xác định chính sách trước.

### 22.2. Xử lý trùng trong cùng một multi-row upsert

```sql
-- PostgreSQL: THỬ RIÊNG, có thể lỗi cardinality.
INSERT INTO demo_contacts AS c
    (tenant_id, email, display_name, contact_status)
VALUES
    (10, 'new@example.test', 'New A', 'ACTIVE'),
    (10, 'NEW@example.test', 'New B', 'ACTIVE')
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO UPDATE SET display_name = EXCLUDED.display_name;
```

Hai hàng cùng câu có khóa normalize giống nhau, có thể khiến một `ON CONFLICT DO UPDATE` muốn tác động cùng hàng đích hai lần; PostgreSQL sẽ báo lỗi kiểu **cardinality violation**, không tự chọn “dòng sau thắng”.

Cần **deduplicate** nguồn theo `tenant_id, lower(email)` và quy tắc phiên bản trước khi upsert.

### 22.3. Soft delete không có nghĩa xóa dữ liệu khỏi mọi nơi

Một hàng có `deleted_at` vẫn chiếm chỗ trong bảng lịch sử, có thể được các truy vấn audit/backup nhìn thấy theo quyền. Partial index chỉ **giải phóng khóa duy nhất của tập live**, không thực thi chính sách xóa dữ liệu cá nhân hay retention.

Đừng dùng soft delete và unique partial index như lời hứa tuân thủ yêu cầu xóa dữ liệu pháp lý; phải có quy trình lưu giữ/hủy dữ liệu riêng.

## 23. Index nào giúp ORDER BY, LIMIT và truy vấn đa điều kiện?

Ngoài uniqueness, cấu trúc index còn quyết định khả năng hỗ trợ lọc và sắp xếp.

Giả sử truy vấn phổ biến:

```sql
SELECT contact_id, email, created_at
FROM demo_contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
ORDER BY created_at DESC, contact_id DESC
LIMIT 20;
```

Unique partial index `(tenant_id, lower(email)) WHERE deleted_at IS NULL` chủ yếu giúp tìm theo email, **không nhất thiết phục vụ tốt thứ tự created_at**.

Có thể cân nhắc **một index khác** phù hợp truy vấn top-N:

```sql
CREATE INDEX ix_demo_live_recent_per_tenant
ON demo_contacts (tenant_id, created_at DESC, contact_id DESC)
WHERE deleted_at IS NULL;
```

Các thành phần:

- `tenant_id` đứng đầu, phù hợp bộ lọc theo tenant.
- `created_at DESC, contact_id DESC` giúp lấy gần đây theo thứ tự có khóa tie-breaker.
- `WHERE deleted_at IS NULL` giảm tập index xuống những hàng chưa xóa.

**Không có công thức “một index giải quyết mọi query”.** Unique index theo email và index recent-by-tenant phục vụ hai workload khác nhau; tạo thêm index làm tăng chi phí DML, nên phải dựa trên lượng truy vấn thật.

### 23.1. Vị trí cột trong composite index

Với điều kiện:

```sql
WHERE tenant_id = 10
  AND lower(email) = 'an@example.test'
```

index `(tenant_id, lower(email))` có thể phù hợp. Nếu phần lớn truy vấn chỉ theo `lower(email)` mà không có tenant, index này không nhất thiết là lựa chọn tối ưu. Thứ tự cột, selectivity và cơ chế scan của từng optimizer đều ảnh hưởng.

Đừng đưa tenant ra khỏi index chỉ để cải thiện một câu query nếu uniqueness theo tenant là quy tắc nghiệp vụ quan trọng. Có thể tách **index ràng buộc** và **index phục vụ một workload đọc khác** khi cần.

### 23.2. Chỉ mục biểu thức và ORDER BY

Một index trên `lower(email)` có thể giúp một số truy vấn `ORDER BY lower(email)` khi trùng thứ tự/collation phù hợp. Nhưng nếu người dùng muốn `ORDER BY email` theo cách so sánh case-sensitive khác, điều kiện sắp không còn tương đương.

Chỉ dùng khả năng hỗ trợ ORDER BY khi EXPLAIN chứng minh plan phù hợp.

## 24. Index với trạng thái không cố định: đừng dùng thời gian động trong predicate

Một ý tưởng hấp dẫn là:

```sql
-- Không hợp lệ/không an toàn như một predicate immutable:
CREATE INDEX ix_current_orders
ON orders (customer_id)
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';
```

Nhưng sau 30 ngày, một hàng có thể chuyển từ “mới” sang “cũ” dù không có UPDATE nào. Index có điều kiện phải dựa trên biểu thức được phép và **ổn định với dữ liệu hàng**.

Phương án tốt hơn:

```sql
CREATE INDEX ix_orders_created_at
ON orders (created_at);
```

rồi tìm theo mốc thời gian động:

```sql
SELECT *
FROM orders
WHERE created_at >= CURRENT_DATE - INTERVAL '30 days';
```

Nếu tỷ lệ dữ liệu lịch sử rất lớn, cân nhắc partitioning theo ngày/tháng và cơ chế retention; không dùng unique partial index động dựa trên đồng hồ.

## 25. Partial index khi predicate có NULL hoặc điều kiện không bao phủ

Giả sử có index:

```sql
CREATE INDEX ix_pending
ON tickets (tenant_id)
WHERE status = 'PENDING';
```

Các hàng `status NULL` hoặc `status = 'DONE'` không được đưa vào index.

Nếu query:

```sql
WHERE status <> 'DONE'
```

thì theo logic SQL ba giá trị, `NULL <> 'DONE'` trả `UNKNOWN`, nên những hàng `NULL` không được chọn. Nhưng predicate `status <> 'DONE'` có thể chọn cả `PENDING` và `CANCELLED`, vì thế partial index chỉ có `PENDING` không đủ bao phủ.

Nếu nghiệp vụ yêu cầu “chưa DONE bao gồm NULL”, cần viết chính xác:

```sql
WHERE status <> 'DONE' OR status IS NULL
```

và cân nhắc index phục vụ **đúng tập** đó. Một index được đặt tên `ix_pending` không tự hiểu khái niệm “chưa hoàn tất” của ứng dụng.

### 25.1. Dùng CASE trong index để ràng buộc có điều kiện

MySQL/MariaDB/Oracle thường dùng `CASE` ở generated/function-based index để xác định giá trị khóa theo điều kiện. Nhưng nếu `CASE` trả `NULL` cho hàng không đủ điều kiện, sự đúng đắn phụ thuộc **NULL semantics của unique index** từng hệ.

Ví dụ Oracle thường cần tất cả expression key là NULL ở hàng nằm ngoài tập; MySQL dùng composite unique với generated key NULL và cho nhiều NULL. Không suy rằng cùng một cặp biểu thức `CASE` tạo cùng bảo đảm trong SQL Server.

## 26. Chi phí ghi và bảo trì chỉ mục

Một bảng có 10 index không có nghĩa truy vấn nhanh gấp 10 lần. Mỗi thao tác ghi có thể phải cập nhật nhiều cấu trúc index.

| Thao tác | Chi phí thường bị ảnh hưởng |
|---|---|
| `INSERT` | Tính biểu thức index, kiểm tra unique, thêm mục nhập index |
| `UPDATE` đổi cột trong key/predicate | Xóa/thay mục nhập cũ, thêm mục nhập mới, tính lại biểu thức |
| `UPDATE` không đổi cột index | Có thể vẫn có chi phí MVCC/index tùy DBMS và đường update |
| `DELETE` | Ghi/đánh dấu/xóa mục nhập theo cơ chế engine |
| `CREATE UNIQUE INDEX` | Quét dữ liệu, xây cấu trúc, phát hiện duplicate |
| `REINDEX/REBUILD` | Chi phí IO/CPU/khóa/log tùy DBMS |
| `ANALYZE/UPDATE STATISTICS` | Cập nhật số liệu cho optimizer |

### 26.1. Unique index chiếm CPU/lock dù SELECT không dùng nó

Một unique index trên `(tenant_id, lower(email))` phải được duy trì khi ghi để ngăn duplicate. Dù chưa có truy vấn đọc nào dùng index đó, **ràng buộc uniqueness vẫn có giá trị**.

Ngược lại, một index thường được tạo chỉ để tăng tốc đọc có thể không đáng giữ nếu workload đã đổi.

### 26.2. Chỉ mục trùng lặp

Nếu bảng đã có:

```sql
UNIQUE (email)
```

và DBMS đã tạo index hỗ trợ unique constraint, thêm:

```sql
CREATE INDEX ix_email_again ON contacts(email);
```

thường tạo cấu trúc gần như trùng lặp. Trước khi thêm index, hãy kiểm tra schema/index hiện có và truy vấn thực sự cần gì.

### 26.3. Độ chọn lọc thấp không tự quyết định vô dụng

Một index trên cột `status` chỉ có ba giá trị có thể kém hiệu quả cho truy vấn trả phần lớn bảng. Nhưng **partial index** chỉ chứa 1% hàng `PENDING` có thể hiệu quả khi ứng dụng thường xử lý đúng tập ấy.

Quan trọng là **tỷ lệ hàng trong tập lọc, cách truy vấn và kích thước bảng**, không chỉ là số lượng giá trị khác nhau của một cột.

## 27. Migration an toàn khi bổ sung unique expression/partial index

Thêm unique index vào bảng production là một thay đổi **luật hợp lệ của dữ liệu**, không chỉ tạo cấu trúc để tăng tốc.

Một quy trình có thể gồm:

1. **Xác định rule nghiệp vụ**: duy nhất toàn bảng hay theo tenant, theo email gốc hay email chuẩn hóa, có bao gồm soft-deleted không?
2. **Kiểm tra dữ liệu hiện có** với đúng biểu thức và predicate.
3. **Giải quyết duplicate** bằng chính sách có thể audit; đừng tự xóa một trong hai hồ sơ mà không biết FK và lịch sử.
4. **Kiểm tra NULL/collation/normalization** theo DBMS đang vận hành.
5. **Ước lượng kích thước index, thời gian build, lock và log**.
6. **Chọn cơ chế tạo online/concurrent** nếu DBMS hỗ trợ và workload yêu cầu.
7. **Triển khai ứng dụng hiểu lỗi unique** và xử lý `ON CONFLICT` hoặc cơ chế upsert phù hợp.
8. **Theo dõi kế hoạch truy vấn và chi phí ghi** sau thay đổi.
9. **Có phương án rollback schema/migration** theo DBMS; DDL rollback không giống nhau giữa PostgreSQL/MySQL/Oracle/SQL Server.
10. **Giữ chính sách phù hợp khi dữ liệu được khôi phục** từ soft delete.

### 27.1. SQL tìm duplicate phù hợp chính xác index

PostgreSQL:

```sql
SELECT tenant_id, lower(email) AS email_key,
       COUNT(*) AS n
FROM demo_contacts
WHERE deleted_at IS NULL
GROUP BY tenant_id, lower(email)
HAVING COUNT(*) > 1;
```

Đây là bước rà soát rule. Nếu rule đổi sang collation khác hay expression khác, kết quả duplicate có thể đổi; luôn dùng **đúng thuật toán chuẩn hóa dự kiến tạo index**.

### 27.2. Migration và collation version

Khi DBMS nâng cấp Unicode/collation libraries hoặc ứng dụng thay thuật toán chuẩn hóa, hai chuỗi trước đây khác khóa có thể trở thành bằng nhau hoặc ngược lại. Unique expression index có thể cần **rebuild/reindex** và xử lý duplicate theo hướng dẫn DBMS sau khi thay đổi collation.

Không xem biểu thức `lower(email)` là bất biến về ý nghĩa nếu bản thân quy tắc collation/locale được thay đổi bên ngoài dữ liệu.

## 28. Bài tập thực hành có đáp án

Các bài dưới đây dùng **PostgreSQL** trừ khi có nhãn hệ khác. Những câu tạo index/xóa dữ liệu là các **phương án riêng**, không bắt buộc chạy nối tiếp sau khi đã dùng cùng tên/index trong bài trước.

### Bài 1. Unique đơn giản

**Yêu cầu:** với bảng `products(sku, product_name)`, bảo đảm không có hai hàng trùng SKU.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_products_sku
ON products (sku);
```

Nếu `products.sku` đã có duplicate, tạo index sẽ lỗi. Nếu muốn diễn đạt quy tắc ở mức schema, có thể dùng `UNIQUE(sku)` constraint phù hợp.

### Bài 2. Unique theo tenant

**Yêu cầu:** cùng SKU được phép ở hai tenant khác nhau, nhưng không được trùng trong một tenant.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_tenant_sku
ON products (tenant_id, sku);
```

Đây là unique **khóa ghép**. Hãy bảo đảm `tenant_id` và `sku` có ràng buộc `NOT NULL` nếu đó là yêu cầu định danh.

### Bài 3. PostgreSQL cho phép bao nhiêu NULL?

**Tình huống:** cột `external_id TEXT UNIQUE` nullable.

**Đáp án:** theo mặc định PostgreSQL cho phép **nhiều hàng có external_id NULL**. Nếu muốn coi nhiều NULL là trùng, PostgreSQL 15+ có `UNIQUE NULLS NOT DISTINCT`.

### Bài 4. Phân biệt SQL Server NULL

**Câu hỏi:** tại sao `UNIQUE(email)` trên cột nullable của SQL Server có thể không chấp nhận hai email NULL, trong khi PostgreSQL cho phép?

**Đáp án:** các DBMS có **NULL semantics khác nhau** đối với unique constraints. Trong SQL Server, một unique key một cột thường chỉ chấp nhận một NULL; có thể dùng `CREATE UNIQUE INDEX ... WHERE email IS NOT NULL` nếu muốn chỉ ràng buộc các giá trị đã biết.

### Bài 5. Index biểu thức trên email

**Yêu cầu:** PostgreSQL thường tìm `WHERE lower(email) = ?`, hãy đề xuất index.

**Đáp án:**

```sql
CREATE INDEX ix_contacts_lower_email
ON contacts (lower(email));
```

Index có thể giúp truy vấn, nhưng optimizer vẫn có thể chọn scan nếu thống kê/chi phí phù hợp.

### Bài 6. Unique không phân biệt chữ hoa/thường

**Yêu cầu:** email không được trùng theo `lower(email)` trong toàn bảng PostgreSQL.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_contacts_email_ci
ON contacts (lower(email));
```

Đây là quy tắc unique toàn bảng; nếu cần độc lập giữa các tenant, phải thêm `tenant_id` vào khóa.

### Bài 7. Unique chỉ cho hàng chưa xóa

**Yêu cầu:** mỗi tenant chỉ có một email live theo `lower(email)`.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_contacts_live_email
ON contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Hàng deleted không thuộc index này. Thêm hàng live có cùng tenant và email lower-case sẽ vi phạm.

### Bài 8. Dự đoán khi khôi phục soft delete

**Tình huống:** tenant 10 có hàng live `An@Example.test`. Một hàng deleted cùng tenant, email `an@example.test`, được `UPDATE deleted_at = NULL`.

**Đáp án:** hàng lịch sử đi vào tập `deleted_at IS NULL` và tạo cặp khóa trùng. Unique partial expression index từ chối cập nhật nếu không có thay đổi khác giải quyết xung đột.

### Bài 9. Vì sao không tạo unique partial constraint bằng ALTER TABLE?

**Yêu cầu:** viết `ALTER TABLE contacts ADD CONSTRAINT ... UNIQUE (...) WHERE deleted_at IS NULL`.

**Đáp án:** PostgreSQL không có dạng **UNIQUE constraint với predicate WHERE** như ví dụ. Dùng **`CREATE UNIQUE INDEX ... WHERE ...`** để thực thi conditional uniqueness.

### Bài 10. ON CONFLICT cho partial unique index

**Yêu cầu:** PostgreSQL upsert email live theo tenant, có expression index `(tenant_id, lower(email)) WHERE deleted_at IS NULL`.

**Đáp án:**

```sql
INSERT INTO contacts AS c
    (tenant_id, email, display_name, deleted_at)
VALUES
    (10, 'an@example.test', 'Updated An', NULL)
ON CONFLICT (tenant_id, lower(email))
    WHERE deleted_at IS NULL
DO UPDATE SET display_name = EXCLUDED.display_name;
```

Không dùng `ON CONFLICT ON CONSTRAINT index_name` với một partial unique index không phải constraint.

### Bài 11. Partial index có dùng cho query thiếu predicate không?

Index:

```sql
CREATE INDEX ix_live_tenant
ON contacts (tenant_id)
WHERE deleted_at IS NULL;
```

Query:

```sql
SELECT * FROM contacts WHERE tenant_id = 10;
```

**Đáp án:** không thể dùng index này làm đường bao phủ toàn bộ tập kết quả vì query còn yêu cầu hàng đã xóa mềm, vốn không nằm trong partial index. Optimizer có thể chọn index khác hoặc scan.

### Bài 12. Đọc kế hoạch

**Yêu cầu:** trên PostgreSQL, xem query tìm email active theo tenant có dùng index hay không.

**Đáp án:**

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT contact_id
FROM contacts
WHERE tenant_id = 10
  AND deleted_at IS NULL
  AND lower(email) = 'an@example.test';
```

Đây là câu `SELECT` nên không thay đổi dữ liệu; kết quả plan cụ thể phụ thuộc kích thước, thống kê và phiên bản PostgreSQL.

### Bài 13. SQL Server filtered index

**Yêu cầu:** SQL Server bảo đảm mã `external_id` duy nhất nếu khác NULL.

**Đáp án:**

```sql
CREATE UNIQUE NONCLUSTERED INDEX ux_external_id
ON dbo.contacts (external_id)
WHERE external_id IS NOT NULL;
```

Predicate filtered index ở đây loại hàng thiếu external_id khỏi tập cần duy nhất.

### Bài 14. SQL Server expression index

**Yêu cầu:** SQL Server cần index trên email lower-case mà cột dùng case-sensitive collation.

**Đáp án minh họa:**

```sql
ALTER TABLE dbo.contacts
ADD email_key AS LOWER(email) PERSISTED;

CREATE INDEX ix_contacts_email_key
ON dbo.contacts (email_key);
```

Cần kiểm tra deterministic/precise, kiểu/collation, SET options và việc câu query tham chiếu expression/cột phù hợp.

### Bài 15. MySQL functional key parts

**Yêu cầu:** MySQL 8.0.13+ tạo index trên `LOWER(email)`.

**Đáp án:**

```sql
CREATE INDEX ix_contacts_lower
ON contacts ((LOWER(email)));
```

MySQL yêu cầu cặp ngoặc bổ sung quanh functional expression; không áp dụng nguyên xi sang MariaDB cũ.

### Bài 16. MySQL/MariaDB không có CREATE INDEX WHERE

**Yêu cầu:** mô phỏng uniqueness chỉ cho hàng chưa xóa.

**Đáp án:** tạo **generated column**:

```sql
-- MySQL: bảng contacts có tenant_id, email, deleted_at.
ALTER TABLE contacts
ADD COLUMN live_email_key VARCHAR(255)
GENERATED ALWAYS AS (
    CASE
        WHEN deleted_at IS NULL THEN LOWER(email)
        ELSE NULL
    END
) STORED,
ADD UNIQUE KEY ux_live_email (tenant_id, live_email_key);
```

Với MariaDB, dùng kiểu generated column được phiên bản hỗ trợ, như `PERSISTENT`. Dùng quy tắc `NULL` của unique key để hàng deleted không chiếm khóa unique live; đây là mô phỏng tính duy nhất, không phải partial index vật lý tương đương PostgreSQL.

### Bài 17. Oracle conditional unique bằng CASE

**Yêu cầu:** Oracle unique email live theo tenant, không yêu cầu hàng deleted duy nhất.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_oracle_live_email
ON contacts (
    CASE WHEN deleted_at IS NULL THEN tenant_id ELSE NULL END,
    CASE WHEN deleted_at IS NULL THEN LOWER(email) ELSE NULL END
);
```

Hàng deleted cho ra toàn bộ index key `NULL` nên không chiếm entry trong Oracle B-tree. Hàng live có khóa thực và được kiểm tra unique.

### Bài 18. SQLite biểu thức và partial

**Yêu cầu:** SQLite từ 3.9.0, ràng buộc mỗi tenant một email live theo lower-case.

**Đáp án:**

```sql
CREATE UNIQUE INDEX ux_sqlite_live_email
ON contacts (tenant_id, lower(email))
WHERE deleted_at IS NULL;
```

Cần chú ý SQLite `lower()` mặc định chủ yếu ASCII; nếu có Unicode phức tạp, phải thiết kế normalization/collation phù hợp.

### Bài 19. Vì sao không dùng NOW() trong partial index?

**Tình huống:** muốn index `WHERE expires_at < CURRENT_TIMESTAMP`.

**Đáp án:** predicate phụ thuộc thời gian hiện tại, một hàng có thể đổi trạng thái mà không được UPDATE; PostgreSQL không cho phép hàm không immutable trong index predicate. Thay bằng index cột `expires_at` rồi query so sánh với mốc thời gian lúc chạy.

### Bài 20. Query top-N theo tenant

**Yêu cầu:** lấy 20 liên hệ live mới nhất theo `created_at DESC, contact_id DESC` trong mỗi tenant; đề xuất index PostgreSQL.

**Đáp án:**

```sql
CREATE INDEX ix_live_recent
ON contacts (tenant_id, created_at DESC, contact_id DESC)
WHERE deleted_at IS NULL;
```

Index này phục vụ workload top-N theo thời gian; **khác mục tiêu** của unique index theo lower(email).

### Bài 21. Trùng trong một câu ON CONFLICT DO UPDATE

**Tình huống:** cùng câu PostgreSQL `INSERT` có hai hàng tenant 10, email `An@...` và `an@...`, cả hai live và cùng khóa `lower(email)`.

**Đáp án:** PostgreSQL có thể báo **cardinality violation** khi một `DO UPDATE` muốn tác động cùng hàng đích hai lần. Phải khử trùng dữ liệu nguồn theo khóa normalize trước khi upsert.

### Bài 22. Chọn index theo yêu cầu

**Tình huống:** ứng dụng rất hay tìm các ticket `PENDING` bằng tenant, nhưng 98% ticket đã `DONE`; không cần unique trên trạng thái.

**Đáp án PostgreSQL:**

```sql
CREATE INDEX ix_pending_tickets
ON tickets (tenant_id, created_at)
WHERE status = 'PENDING';
```

Đây là partial index **không unique** để tập trung truy vấn vào phần dữ liệu nhỏ. Cần kiểm tra `EXPLAIN` và thống kê thực tế; không gắn `UNIQUE` nếu nghiệp vụ cho phép nhiều ticket pending trong cùng tenant.

## 29. Tài liệu chính thức để tra cứu theo phiên bản

Các cú pháp và giới hạn kỹ thuật ở từng DBMS nên được đối chiếu với đúng phiên bản đang chạy:

- **PostgreSQL — Unique Indexes:** https://www.postgresql.org/docs/current/indexes-unique.html
- **PostgreSQL — Indexes on Expressions:** https://www.postgresql.org/docs/current/indexes-expressional.html
- **PostgreSQL — Partial Indexes:** https://www.postgresql.org/docs/current/indexes-partial.html
- **PostgreSQL — CREATE INDEX:** https://www.postgresql.org/docs/current/sql-createindex.html
- **SQL Server — Create Filtered Indexes:** https://learn.microsoft.com/en-us/sql/relational-databases/indexes/create-filtered-indexes
- **SQL Server — CREATE INDEX (Transact-SQL):** https://learn.microsoft.com/en-us/sql/t-sql/statements/create-index-transact-sql
- **MySQL — CREATE INDEX và functional key parts:** https://dev.mysql.com/doc/refman/8.4/en/create-index.html
- **MariaDB — Generated Columns:** https://mariadb.com/docs/server/reference/sql-statements/data-definition/create/generated-columns
- **Oracle — CREATE INDEX/function-based indexes:** https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-INDEX.html
- **SQLite — Indexes on Expressions:** https://www.sqlite.org/expridx.html
- **SQLite — Partial Indexes:** https://www.sqlite.org/partialindex.html

Một số tính năng xuất hiện ở mốc phiên bản nhất định: PostgreSQL **15+** có `NULLS NOT DISTINCT`; MySQL **8.0.13+** có functional key parts; SQLite có partial indexes từ **3.8.0** và expression indexes từ **3.9.0**. Hãy kiểm tra phiên bản server, storage engine, collation, quyền tạo index và bộ thư viện ứng dụng trước khi dùng cú pháp ngoài thực tế.

## Kết luận

**Unique index, expression index và partial/filtered index giải quyết những câu hỏi khác nhau nhưng kết hợp được với nhau.** Unique index **bảo vệ khóa không trùng**, expression index **định nghĩa khóa bằng một biểu thức** như `lower(email)`, còn partial/filtered index **chỉ bao phủ những hàng thỏa predicate**. Trong một ứng dụng multi-tenant có soft delete, tổ hợp `UNIQUE (tenant_id, lower(email)) WHERE deleted_at IS NULL` trên PostgreSQL/SQLite là ví dụ điển hình của cả ba chức năng.

Những điều cần ghi nhớ:

1. **Đúng nghiệp vụ trước, nhanh sau:** xác định khóa, tenant, soft delete, NULL semantics và normalization trước khi chọn cú pháp.
2. **Unique enforcement khác query plan:** index bảo vệ dữ liệu ngay cả khi SELECT không dùng nó; còn optimizer có thể chọn scan nếu index không kinh tế.
3. **Predicate phải phù hợp truy vấn:** một partial index chỉ được dùng khi optimizer biết điều kiện query bao hàm tập của index; parameterization và expression mismatch có thể ảnh hưởng.
4. **Đừng sao chép cú pháp giữa DBMS:** PostgreSQL/SQLite có partial index; SQL Server dùng filtered index và computed columns; MySQL/MariaDB có generated columns cho conditional uniqueness; Oracle dùng function-based `CASE`.
5. **Không xem NULL giống nhau ở mọi hệ:** PostgreSQL mặc định cho nhiều NULL, PostgreSQL 15+ có `NULLS NOT DISTINCT`, SQL Server unique một cột nullable thường chỉ cho một NULL, MySQL/SQLite có quy tắc khác.
6. **Đo và bảo trì:** thêm index tăng dung lượng và chi phí ghi. Dùng `EXPLAIN`/execution plan, thống kê và workload thật để chọn số lượng/index key hợp lý.
7. **Triển khai an toàn:** kiểm tra duplicate có sẵn, xử lý concurrent write, xem khóa/migration, kiểm tra index build và có phương án khôi phục.

Một schema tốt không phải schema có nhiều chỉ mục nhất, mà là schema dùng **đúng loại chỉ mục cho đúng ràng buộc dữ liệu và đúng mẫu truy vấn**, với ngữ nghĩa nhất quán trên DBMS thực sự được vận hành.

