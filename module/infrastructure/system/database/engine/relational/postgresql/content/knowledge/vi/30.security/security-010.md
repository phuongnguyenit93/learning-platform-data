# search_path, schema công khai và nguy cơ chiếm quyền đối tượng trong PostgreSQL

Một ứng dụng có thể dùng cùng tên bảng hoặc function trong nhiều schema. Ví dụ, câu lệnh `SELECT * FROM accounts` không ghi rõ `accounts` thuộc schema nào. PostgreSQL phải tra cứu tên này theo cấu hình `search_path` của session. Đây là một tính năng tiện lợi, nhưng cũng là **ranh giới bảo mật**: nếu một vai trò không đáng tin được quyền tạo đối tượng trong schema được tìm trước, đối tượng của họ có thể được chọn thay cho đối tượng mà lập trình viên dự định gọi.

Rủi ro nghiêm trọng hơn khi những lệnh không ghi rõ tên schema chạy trong một function `SECURITY DEFINER`, một migration do tài khoản đặc quyền thực hiện hoặc một job quản trị. Khi đó, lỗi phân giải tên có thể tạo cơ hội để **chiếm quyền tham chiếu đối tượng** (*object hijacking*), dẫn tới thực thi logic không đáng tin trong một ngữ cảnh nhiều quyền hơn.

Bài thuộc chương **Bảo mật** của module *Database Engine Relational PostgreSQL*. Trọng tâm là hiểu cơ chế phân giải tên, phân tích quyền của schema `public`, xây dựng đường dẫn tin cậy và kiểm tra những code path có quyền cao.

Sau bài học, bạn sẽ:

- Hiểu vai trò của **schema**, `USAGE`, `CREATE`, owner và `PUBLIC`.
- Giải thích `search_path`, `current_schema()`, `current_schemas()` và tác động của tên chưa được schema-qualified.
- Phân biệt cách tra cứu `pg_catalog` và `pg_temp`; nhận diện nguy cơ che khuất bảng, function, kiểu dữ liệu và toán tử.
- Hiểu điểm khác nhau giữa **schema tên `public`** và **pseudo-role `PUBLIC`**.
- Biết vì sao quyền `CREATE` trên schema `public` có thể nguy hiểm và vì sao mặc định thay đổi ở PostgreSQL 15 đối với database mới.
- Viết function `SECURITY DEFINER` với `SET search_path` đáng tin, quyền `EXECUTE` hạn chế và tên đối tượng được qualified.
- Phân tích nguy cơ do function/operator overloading, extension, migration, connection pooling và search path do người dùng kiểm soát.
- Thực hành mô phỏng name shadowing **không sử dụng quyền của vai trò khác và không thay đổi schema public thực tế**.
- Kiểm toán quyền schema, role, function và xây kế hoạch khắc phục phù hợp cho database đang hoạt động.

> **Phạm vi an toàn:** Các ví dụ có thể chạy dùng schema thử nghiệm `sp_sec_lab_private` và `sp_sec_lab_untrusted`. Schema thứ hai chỉ **mô phỏng** vị trí mà một vai trò không đáng tin có thể ghi, không thực hiện việc giành quyền truy cập ngoài ý muốn. Các lệnh thay đổi quyền `public`/role toàn hệ thống được ghi dưới dạng ví dụ quản trị có cảnh báo; không chạy trên production khi chưa đánh giá phụ thuộc.

---

## 1. Schema là không gian tên, nhưng cũng là một ranh giới quyền

### 1.1. Một database có thể có nhiều schema

```text
database: shopdb
│
├── pg_catalog
│   ├── pg_class
│   ├── pg_namespace
│   └── các function/operator hệ thống
│
├── public
│   └── những đối tượng đã được tạo trong public
│
├── app
│   ├── accounts
│   ├── orders
│   └── calculate_total(...)
│
└── app_private
    ├── payment_secrets
    └── privileged_workflow(...)
```

Hai schema có thể chứa hai quan hệ cùng tên:

```sql
CREATE TABLE app.accounts (...);
CREATE TABLE public.accounts (...);
```

Đây là ví dụ cú pháp, không phải DDL cần chạy ngay. `app.accounts` và `public.accounts` là hai đối tượng **khác nhau**.

### 1.2. Tên qualified và unqualified

Tên **qualified** bao gồm schema:

```sql
SELECT * FROM app.accounts;
```

Tên **unqualified** chỉ có tên đối tượng:

```sql
SELECT * FROM accounts;
```

Trong trường hợp thứ hai, PostgreSQL cần biết schema nào được tìm và theo thứ tự nào.

### 1.3. Schema không tự cấp quyền đọc dữ liệu

Một role có thể có quyền `USAGE` trên schema nhưng chưa có quyền `SELECT` trên bảng trong schema. Ngược lại, được `GRANT SELECT` trên bảng không đủ để truy cập bằng tên nếu thiếu `USAGE` trên schema tương ứng.

Những quyền quan trọng:

| Quyền | Đối tượng | Ý nghĩa chính |
|---|---|---|
| `USAGE` | Schema | Cho phép tra cứu/sử dụng các đối tượng trong schema, còn phụ thuộc quyền của từng đối tượng |
| `CREATE` | Schema | Cho phép tạo đối tượng phù hợp bên trong schema |
| `SELECT` | Table/view | Cho phép đọc dữ liệu theo quy tắc quyền và RLS |
| `INSERT/UPDATE/DELETE` | Table | Cho phép thao tác dữ liệu tương ứng |
| `EXECUTE` | Function/procedure | Cho phép thực thi routine |
| Ownership | Schema/object | Có các quyền quản trị đặc biệt trên đối tượng do mình sở hữu, theo quy tắc PostgreSQL |

**Điểm bảo mật cốt lõi:** Được `CREATE` trong một schema nằm trên `search_path` của code đặc quyền có thể nguy hiểm hơn rất nhiều so với vẻ ngoài “chỉ được tạo bảng/function trong một namespace”.

### 1.4. Schema không phải database riêng

Các schema trong cùng database dùng chung kết nối và catalog. Không coi một schema công khai là sandbox đủ mạnh cho mã SQL không tin cậy, nhất là khi còn có chức năng tạo function, operator, cast hoặc extension theo quyền tương ứng.

---

## 2. search_path là gì?

### 2.1. Định nghĩa

`search_path` là tham số cấu hình liệt kê những schema được PostgreSQL tìm kiếm khi cần phân giải một tên đối tượng **không có schema tường minh**.

Ví dụ:

```sql
SET search_path = app, public;

SELECT * FROM orders;
```

Nếu có `app.orders` và role có thể truy cập, tên `orders` thường được phân giải tới `app.orders` trước `public.orders`.

### 2.2. Xem cấu hình

```sql
SHOW search_path;

SELECT current_setting('search_path') AS raw_path;
```

Giá trị thô không nhất thiết trùng danh sách schema **thực sự** được dùng; có thể có tên không tồn tại, tên không có `USAGE` hoặc các schema được tìm mặc định.

### 2.3. current_schema()

```sql
SELECT current_schema();
```

Hàm trả schema đầu tiên trong search path hiện hành có thể dùng làm nơi tạo đối tượng mặc định, theo quy tắc PostgreSQL. Nếu không có schema phù hợp, việc tạo đối tượng không qualified có thể lỗi.

### 2.4. current_schemas()

```sql
SELECT
    current_schemas(false) AS explicitly_resolved_schemas,
    current_schemas(true) AS including_implicit_schemas;
```

- `current_schemas(false)` biểu diễn các schema path được phân giải, loại trừ những schema implicit.
- `current_schemas(true)` bao gồm những schema được tìm **ngầm định**, như `pg_catalog` và có thể cả schema tạm khi tồn tại.

Đây là công cụ quan sát hữu ích hơn việc chỉ đọc chuỗi `SHOW search_path`.

### 2.5. Một schema trên path nhưng không có USAGE

Tên schema không tồn tại hoặc không có quyền `USAGE` thường không được dùng để tra cứu đối tượng như người cấu hình mong đợi. Vì vậy việc khai báo:

```sql
SET search_path = app_private, public;
```

không tự cấp quyền truy cập `app_private`. Cần kiểm tra quyền của role thực thi.

### 2.6. Path là một tham số session

`search_path` có thể bị ảnh hưởng bởi cấu hình database, role, session, transaction, connection options hoặc `SET` của code. Không chỉ đọc một file cấu hình server rồi mặc định mọi kết nối đều dùng giá trị đó.

---

## 3. Ví dụ đơn giản: cùng tên bảng, khác kết quả

### 3.1. Giả lập hai schema

```sql
CREATE SCHEMA sp_sec_lab_private;
CREATE SCHEMA sp_sec_lab_untrusted;

CREATE TABLE sp_sec_lab_private.sample_items (
    item_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE sp_sec_lab_untrusted.sample_items (
    item_id INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO sp_sec_lab_private.sample_items
VALUES (1, 'TRUSTED DATA');

INSERT INTO sp_sec_lab_untrusted.sample_items
VALUES (1, 'UNTRUSTED DATA');
```

**Lưu ý:** Schema `sp_sec_lab_untrusted` là schema được **chính bạn tạo để mô phỏng**; bài này không cấp quyền CREATE cho người khác hoặc tạo đối tượng giả trong schema `public` đang sử dụng.

### 3.2. Path ưu tiên schema trusted

```sql
BEGIN;
SET LOCAL search_path =
    pg_catalog, sp_sec_lab_private, sp_sec_lab_untrusted, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Truy vấn unqualified lấy `sp_sec_lab_private.sample_items` và trả `TRUSTED DATA`.

### 3.3. Đổi thứ tự path

```sql
BEGIN;
SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Lần này unqualified `sample_items` trỏ tới bảng trong schema mô phỏng untrusted và trả `UNTRUSTED DATA`.

### 3.4. Qualified name không bị đổi bởi path

```sql
SELECT item_id, label
FROM sp_sec_lab_private.sample_items;
```

Truy vấn chỉ rõ schema sẽ tìm đối tượng đó mà không nhờ search path chọn giữa hai bảng cùng tên.

### 3.5. Bài học

Nếu một chương trình giả định `FROM sample_items` luôn là bảng trusted, người có quyền tạo bảng cùng tên trong schema ưu tiên hơn có thể khiến chương trình **đọc hoặc ghi đối tượng khác**. Khi chương trình đặc quyền thực thi, ảnh hưởng có thể vượt quá quyền mà người tạo đối tượng đáng lẽ được sử dụng.

---

## 4. Các thành phần mặc định: "$user", public, pg_catalog

### 4.1. Mặc định thường gặp

Trong nhiều database PostgreSQL, `SHOW search_path` có thể trả:

```text
"$user", public
```

Đây là ví dụ thường gặp, **không phải cam kết** database của bạn luôn có cùng giá trị.

### 4.2. "$user" nghĩa là gì?

`"$user"` là phần tử đặc biệt biểu diễn schema có cùng tên với `CURRENT_USER` nếu schema đó tồn tại và có thể dùng. Nó không phải chuỗi tên schema cố định `$user`.

Ví dụ role `alice` có schema `alice` thích hợp, thì `alice` có thể được tìm trước `public`. Nếu schema không tồn tại hoặc không có quyền phù hợp, phần tử đó không có tác dụng như một schema tồn tại.

### 4.3. public là schema thật

`public` là schema thường được tạo mặc định trong nhiều database. Nó có thể chứa bảng, view, function, type và các đối tượng khác. **Tên `public` không làm nó tự động an toàn hoặc không an toàn; quyền tạo đối tượng và vị trí trong path mới quyết định rủi ro.**

### 4.4. pg_catalog chứa đối tượng hệ thống

`pg_catalog` chứa phần lớn các bảng catalog, type, function và operator hệ thống.

Nếu `pg_catalog` **không được liệt kê tường minh** trong `search_path`, PostgreSQL thường tìm nó **trước** các schema được khai báo trong path.

Ví dụ:

```sql
SET search_path = sp_sec_lab_untrusted, sp_sec_lab_private;
```

không có nghĩa mọi function trong `sp_sec_lab_untrusted` đều được ưu tiên hơn function cùng chữ ký trong `pg_catalog`: `pg_catalog` vẫn được tìm ngầm ở vị trí ưu tiên theo quy tắc này.

### 4.5. Nhưng có thể đưa pg_catalog vào vị trí bất lợi

Nếu `pg_catalog` được **liệt kê tường minh**, thứ tự của nó trong danh sách có ý nghĩa:

```sql
-- Không dùng như cấu hình production cho code đặc quyền:
SET search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private;
```

Đặt untrusted schema trước `pg_catalog` có thể làm tăng rủi ro shadowing của một số tên function/operator/type. **Đừng suy rằng PostgreSQL luôn bỏ qua thứ tự của pg_catalog.**

### 4.6. Cấu hình an toàn dễ đọc

```sql
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp;
```

Trong một code path chỉ dùng schema `sp_sec_lab_private` do role tin cậy quản lý, cấu hình này là một ví dụ hợp lý:

- `pg_catalog` ở đầu cho built-in names.
- Schema trusted ở phía trước mọi namespace không tin cậy.
- `pg_temp` được đặt cuối để giảm khả năng đối tượng tạm che khuất bảng/type trusted.

Độ an toàn vẫn phụ thuộc **ai có quyền CREATE trong từng schema**, không phải chuỗi SET đơn độc.

---

## 5. pg_temp: đường phân giải đặc biệt

### 5.1. Temporary schema thuộc session

Khi session tạo temporary table:

```sql
CREATE TEMP TABLE temp_example (id INTEGER);
```

PostgreSQL dùng một schema tạm riêng cho session (tên thực tế như `pg_temp_N`). `pg_temp` là alias tiện lợi trỏ tới schema tạm hiện hành.

### 5.2. pg_temp có thể được tìm trước nếu không khai báo

Với quan hệ và một số tên kiểu dữ liệu, khi schema tạm tồn tại mà `pg_temp` **không được liệt kê tường minh** trong path, PostgreSQL có thể ưu tiên tra cứu schema tạm trước các schema khác.

Đây là bẫy đáng chú ý cho `SECURITY DEFINER` function dùng bảng không qualified.

### 5.3. Thực hành temp table shadowing an toàn

Đã có `sp_sec_lab_private.sample_items`. Hãy chạy:

```sql
BEGIN;

CREATE TEMP TABLE sample_items (
    item_id INTEGER,
    label TEXT
) ON COMMIT DROP;

INSERT INTO pg_temp.sample_items
VALUES (1, 'TEMP DATA');

SET LOCAL search_path = sp_sec_lab_private;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Với cách tra cứu relation khi temp schema hiện diện nhưng không được nêu trong path, `sample_items` có thể trỏ đến **temporary table**, cho kết quả `TEMP DATA`.

### 5.4. Thêm pg_temp ở cuối path

```sql
BEGIN;

CREATE TEMP TABLE sample_items (
    item_id INTEGER,
    label TEXT
) ON COMMIT DROP;

INSERT INTO pg_temp.sample_items
VALUES (1, 'TEMP DATA');

SET LOCAL search_path = pg_catalog, sp_sec_lab_private, pg_temp;

SELECT item_id, label
FROM sample_items;

ROLLBACK;
```

Giờ PostgreSQL tìm `sp_sec_lab_private.sample_items` trước temporary table vì `pg_temp` được đặt tường minh **sau** schema trusted.

### 5.5. pg_temp không được dùng giống nhau cho mọi loại tên

Điểm cần phân biệt:

- Schema tạm có cơ chế tra cứu đặc biệt đối với **relation** và **data type**.
- PostgreSQL **không tìm function hoặc operator** trong temporary schema theo cách nó tra cứu table/type thông thường.

Đừng rút ra kết luận sai rằng một function có thể bị shadow chỉ bởi function trong `pg_temp` theo chính các quy tắc tìm bảng tạm.

### 5.6. Tại sao vẫn phải đặt pg_temp ở cuối SECURITY DEFINER?

Một function đặc quyền có thể tham chiếu bảng hoặc type không qualified. Đặt `pg_temp` cuối search path tường minh giúp tránh temporary relation/type được tìm ưu tiên trước schema đáng tin.

---

## 6. Schema public và role PUBLIC là hai khái niệm khác nhau

### 6.1. Schema tên public

`public` là một namespace trong database:

```sql
SELECT oid, nspname
FROM pg_namespace
WHERE nspname = 'public';
```

### 6.2. Pseudo-role PUBLIC

Trong cú pháp phân quyền, `PUBLIC` là nhóm **mọi role** theo nghĩa quyền được cấp chung:

```sql
GRANT USAGE ON SCHEMA public TO PUBLIC;
```

Đây là cú pháp quản trị để minh họa; **không cần chạy** trong database thực tập nếu không có lý do.

### 6.3. Hai từ public trong cùng một statement

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Ý nghĩa:

- `SCHEMA public`: đối tượng schema có tên `public`.
- `FROM PUBLIC`: thu hồi quyền CREATE được cấp cho tập mọi role.

Điều này **không xóa schema public** và **không thu hồi mọi quyền** của từng role đã được grant trực tiếp.

### 6.4. USAGE không phải CREATE

Một cấu hình phổ biến:

```text
PUBLIC role:
  USAGE on schema public
  NO CREATE on schema public
```

Cho phép tra cứu những đối tượng được cấp quyền phù hợp trong public nhưng không cho mọi role tạo đối tượng mới ở đó.

### 6.5. Không REVOKE ALL thiếu cân nhắc

Lệnh:

```sql
-- Không khuyến khích chạy trực tiếp mà chưa đánh giá:
-- REVOKE ALL ON SCHEMA public FROM PUBLIC;
```

có thể thu hồi cả `USAGE`, làm những ứng dụng trước đó đang gọi `public.some_function` hoặc `public.some_table` thất bại nếu không có grants khác. Nếu mục tiêu chỉ là ngăn object creation, cần đánh giá **`REVOKE CREATE` trước**.

---

## 7. PostgreSQL 15 thay đổi mặc định của public như thế nào?

### 7.1. Trước PostgreSQL 15

Trong cấu hình mặc định truyền thống của nhiều database PostgreSQL trước phiên bản 15, schema `public` thường có:

- `USAGE` cho `PUBLIC`.
- `CREATE` cho `PUBLIC`.

Điều đó nghĩa là một role không đáng tin nhưng có thể kết nối database có thể có khả năng tạo đối tượng trong `public`, trừ khi DBA đã thu hồi quyền.

### 7.2. PostgreSQL 15+ với database mới

Từ PostgreSQL 15, mặc định của những database **mới được tạo với template chuẩn tương ứng** đã an toàn hơn:

- Schema `public` thường được sở hữu bởi role đặc biệt **`pg_database_owner`**.
- Quyền `CREATE` trên `public` **không được cấp cho `PUBLIC` theo mặc định**.
- `USAGE` cho `PUBLIC` vẫn có thể được cấp theo mặc định.

`pg_database_owner` là role được định nghĩa đặc biệt để liên hệ quyền sở hữu database với những đối tượng thích hợp; nó không phải mọi người dùng database.

### 7.3. Không suy từ server_version để kết luận ACL

Một server chạy PostgreSQL 16/17/18 vẫn có thể có một database được nâng cấp từ phiên bản cũ, được clone từ template đã tùy chỉnh hoặc đã được DBA cấp lại quyền. Vì vậy:

> **Không kết luận “đang dùng PostgreSQL 15+ nên PUBLIC chắc chắn không có CREATE trên public”. Hãy kiểm tra ACL thực tế của từng database.**

### 7.4. Vì sao database nâng cấp vẫn cần audit?

Khi nâng cấp cluster/database, PostgreSQL không mặc nhiên xóa mọi quyền schema đã được cấu hình trước đó. Những quyền cũ có thể được duy trì, và các extensions/app migrations có thể thay đổi grants.

### 7.5. Mô hình quyền được khuyến nghị

Một thiết kế thông thường:

```text
public:
    USAGE for application roles khi thật sự cần
    CREATE chỉ dành cho chủ sở hữu / trusted migration role

app:
    chủ sở hữu trusted migration role
    read/write được cấp tường minh cho runtime roles

app_private:
    CREATE chỉ trusted owner
    USAGE/EXECUTE được cấp tối thiểu cho role cần dùng
```

Không trao `CREATE` trên một schema trong search path của code đặc quyền cho role mà bạn không tin hoàn toàn.

---

## 8. Vì sao quyền CREATE trong search_path có thể là vấn đề an ninh?

### 8.1. Tạo đối tượng không chỉ là lưu dữ liệu

Role có `CREATE` trong một schema có thể tạo những loại đối tượng khác nhau tùy các quyền tương ứng, chẳng hạn bảng, view, function hoặc operator.

Nếu code đặc quyền dùng tên không qualified và search path chứa schema đó, những đối tượng vừa tạo có thể ảnh hưởng đến name resolution.

### 8.2. Chuỗi rủi ro điển hình

```text
Vai trò ít quyền
    |
    v
Có CREATE trên schema xuất hiện trước
    |
    v
Tạo đối tượng trùng tên / overload
    |
    v
Code đặc quyền dùng tên không qualified
    |
    v
PostgreSQL chọn đối tượng theo lookup rules
    |
    v
Code đặc quyền có thể truy cập sai bảng/
gọi sai function, operator hoặc type
```

Đây là mô hình nguy cơ để **phòng tránh**, không phải hướng dẫn khai thác một hệ thống không được phép.

### 8.3. Name shadowing và object hijacking

- **Name shadowing:** đối tượng mới cùng tên che khuất đối tượng khác trong lookup.
- **Overloading:** cùng tên function/operator nhưng chữ ký tham số khác; quy tắc chọn routine không chỉ dựa vào thứ tự schema đơn giản.
- **Object hijacking:** code dự kiến gọi đối tượng tin cậy nhưng bị hướng tới đối tượng không tin cậy.

### 8.4. Quyền EXECUTE của routine và tính leo thang

Một function `SECURITY DEFINER` chạy với quyền của **function owner**. Nếu body gọi một function không tin cậy thông qua name resolution, hành vi thực tế có thể được thực hiện trong một ngữ cảnh bảo mật khác với ý định của tác giả.

Chỉ cần một lời gọi không qualified trong privileged code có thể tạo lỗ hổng, dù **tham số SQL đã được bind đúng và không có SQL injection dạng nối chuỗi**.

### 8.5. Gốc rễ là trust boundary

Đặt một schema vào `search_path` của routine đặc quyền nghĩa là **tin những người có thể tạo đối tượng trong schema đó**. Đây không phải chỉ là một lựa chọn viết SQL ngắn cho tiện.

---

## 9. Phòng thực hành: mô phỏng shadowing function mà không cấp quyền cao

### 9.1. Tạo function trong schema trusted

```sql
CREATE FUNCTION sp_sec_lab_private.format_label(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'TRUSTED: ' || p_text;
$function$;
```

### 9.2. Tạo function cùng tên trong schema mô phỏng untrusted

```sql
CREATE FUNCTION sp_sec_lab_untrusted.format_label(p_text TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'UNTRUSTED: ' || p_text;
$function$;
```

Hai function đều là ví dụ vô hại; chúng chỉ nối chuỗi và không truy cập dữ liệu nhạy cảm.

### 9.3. Chỉ đổi path đã đổi function được gọi

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_private, sp_sec_lab_untrusted, pg_temp;

SELECT format_label('hello'::text) AS selected_function;

ROLLBACK;
```

Kết quả:

```text
TRUSTED: hello
```

Đổi thứ tự:

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT format_label('hello'::text) AS selected_function;

ROLLBACK;
```

Kết quả:

```text
UNTRUSTED: hello
```

### 9.4. Gọi qualified cho kết quả ổn định

```sql
SELECT
    sp_sec_lab_private.format_label('hello'::text)
        AS trusted_result,
    sp_sec_lab_untrusted.format_label('hello'::text)
        AS untrusted_result;
```

Kết quả không phụ thuộc cách sắp xếp hai schema trong session search path.

### 9.5. Bài học từ thí nghiệm

Đây chỉ là một demo về **name resolution**, không phải chiếm quyền thực tế. Nhưng cơ chế tương tự trở nên nghiêm trọng nếu lời gọi nằm trong code có quyền cao, nhất là khi role ít quyền được phép tạo function trong schema được tìm trước.

---

## 10. Function overloading làm rủi ro phức tạp hơn

### 10.1. Không phải lúc nào cùng tên cũng cùng chữ ký

PostgreSQL hỗ trợ overloading:

```sql
CREATE FUNCTION sp_sec_lab_private.show_value(p_value INTEGER)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'integer: ' || p_value::text;
$function$;

CREATE FUNCTION sp_sec_lab_private.show_value(p_value TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $function$
    SELECT 'text: ' || p_value;
$function$;
```

Một lời gọi:

```sql
SELECT sp_sec_lab_private.show_value(10);
```

có chữ ký rõ ràng hơn lời gọi sử dụng literal chưa biết kiểu:

```sql
SELECT sp_sec_lab_private.show_value('10');
```

### 10.2. Một routine có thể bị can thiệp mà không cần cùng chữ ký

Nếu một schema không đáng tin nằm trên path, role có thể tạo **function cùng tên với chữ ký khác** theo những quyền tương ứng. Quy tắc lựa chọn function xét cả loại đối số, implicit casts, variadic/default arguments và độ khớp kiểu.

Vì vậy không nên nghĩ:

> “Function hệ thống/trusted luôn thắng vì nó xuất hiện trước trong path; các overload ở schema khác chắc chắn vô hại.”

Khẳng định đó quá đơn giản. Một overload khớp kiểu tốt hơn, hoặc một lời gọi có literal kiểu `unknown`, có thể làm lựa chọn phức tạp hơn.

### 10.3. pg_catalog implicit không thay mọi biện pháp phòng vệ

`pg_catalog` thường được tìm trước khi nó không được liệt kê trong path, điều đó hỗ trợ bảo vệ các built-in tên/chữ ký tương ứng. Nhưng **function resolution không chỉ là tìm một tên ở schema đầu tiên và dừng lại**. Với overloading/casts, cần kiểm soát quyền tạo routine trong những schema có thể tra cứu và chọn qualified names/explicit casts cho code nhạy cảm.

### 10.4. Không tạo wrapper IMMUTABLE thiếu trung thực

Một security routine có thể dùng `SET search_path` để ổn định resolution. Không nên giải quyết sự khác biệt name resolution bằng cách khai báo sai `IMMUTABLE` cho function thực sự đọc dữ liệu hoặc phụ thuộc môi trường. Sai volatility có thể làm optimizer lập kế hoạch dựa trên những giả định không đúng.

---

## 11. Toán tử và kiểu dữ liệu cũng có name resolution

### 11.1. Không chỉ FROM và tên function

Các thành phần SQL cần tra cứu tên bao gồm:

- Table, view, sequence, type.
- Function/procedure.
- Operator.
- Một số đối tượng có quy tắc tra cứu riêng như collation và domain.

Nguy cơ bảo mật không giới hạn ở `SELECT * FROM orders`.

### 11.2. Qualified operator

PostgreSQL có cú pháp dùng operator với schema:

```sql
SELECT 1 OPERATOR(pg_catalog.=) 1 AS equals_one;
```

Trong code có độ nhạy cảm cao và cần kiểm soát operator resolution đặc biệt, có thể dùng cú pháp này; nhưng thông thường tổ chức **trusted search_path + kiểu đối số rõ + không cấp CREATE cho untrusted role** có hiệu quả và dễ đọc hơn.

### 11.3. Type shadowing và pg_temp

Schema tạm có thể được tìm trước đối với **type names** nếu không đặt `pg_temp` tường minh ở cuối. Một function đặc quyền tạo/cast dữ liệu qua type unqualified phải được xem xét tương tự quan hệ unqualified.

### 11.4. Qualification không thay kiểu dữ liệu an toàn

Một câu `SELECT 1 OPERATOR(pg_catalog.=) 1` minh họa cách chỉ rõ operator, không thay kiểm tra kiểu dữ liệu, validation, SQL parameters hoặc quyền SELECT/EXECUTE.

---

## 12. SECURITY DEFINER: chức năng, lợi ích và rủi ro

### 12.1. SECURITY INVOKER

Function thông thường có mô hình mặc định `SECURITY INVOKER`: chạy theo quyền của người gọi đối với truy cập dữ liệu trong function, theo các quy tắc bảo mật áp dụng.

```sql
CREATE FUNCTION some_schema.public_helper(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY INVOKER
AS $function$
BEGIN
    ...
END;
$function$;
```

Đây là ví dụ cú pháp, không phải function hoàn chỉnh.

### 12.2. SECURITY DEFINER

`SECURITY DEFINER` khiến function chạy với quyền của **owner**, không phải quyền thực thi của người gọi theo cách thông thường. Nó hữu ích để cung cấp một thao tác hạn chế lên dữ liệu mà role ứng dụng không được truy cập trực tiếp.

Ví dụ: chỉ cho phép gọi `close_period(p_id)` thay vì cấp trực tiếp UPDATE trên tất cả các bảng kế toán liên quan.

### 12.3. Tại sao nó nguy hiểm nếu search_path không đáng tin?

Một privileged routine có dạng khái niệm:

```sql
-- KHÔNG triển khai mẫu không an toàn này:
-- CREATE FUNCTION privileged_action(...)
-- RETURNS ...
-- LANGUAGE plpgsql
-- SECURITY DEFINER
-- AS $function$
-- BEGIN
--     SELECT ... FROM accounts; -- tên không qualified
--     PERFORM validate_record(...); -- function không qualified
-- END;
-- $function$;
```

Nếu function không cố định search path đáng tin và người gọi có thể ảnh hưởng search path hoặc một schema trong path cho phép untrusted CREATE, việc phân giải `accounts` hoặc `validate_record` có thể sai lệch.

### 12.4. Giải pháp nhiều lớp

1. **Cố định search_path an toàn trên function** bằng thuộc tính `SET search_path`.
2. Chỉ đặt các schema **trusted** trước `pg_temp`.
3. Dùng qualified names với những bảng/function/type quan trọng.
4. Không cấp `CREATE` vào các schema trusted cho untrusted roles.
5. Thu hồi `EXECUTE` từ `PUBLIC` nếu function chỉ dành cho role cụ thể.
6. Kiểm soát owner, `SECURITY DEFINER` và RLS.
7. Kiểm thử dưới đúng role gọi và với search path cố ý khác.

Không có biện pháp đơn lẻ đủ thay cho các bước còn lại trong mọi trường hợp.

---

## 13. Thực hành: viết SECURITY DEFINER function an toàn

### 13.1. Bảng dữ liệu trusted

```sql
CREATE TABLE sp_sec_lab_private.accounts (
    account_id INTEGER PRIMARY KEY,
    account_name TEXT NOT NULL
);

INSERT INTO sp_sec_lab_private.accounts
VALUES (1, 'demo-account');
```

Bài này chỉ minh họa cú pháp và name resolution, không chứa thông tin cá nhân hoặc secret thật.

### 13.2. Function có function-level SET search_path

```sql
BEGIN;

CREATE FUNCTION sp_sec_lab_private.describe_account(
    p_account_id INTEGER
)
RETURNS TEXT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp
AS $function$
DECLARE
    v_name TEXT;
BEGIN
    IF p_account_id IS NULL THEN
        RAISE EXCEPTION 'Account ID is required'
            USING ERRCODE = '22023';
    END IF;

    SELECT a.account_name
    INTO STRICT v_name
    FROM sp_sec_lab_private.accounts AS a
    WHERE a.account_id = p_account_id;

    RETURN sp_sec_lab_private.format_label(v_name);
END;
$function$;

REVOKE ALL ON FUNCTION
    sp_sec_lab_private.describe_account(INTEGER)
FROM PUBLIC;

COMMIT;
```

### 13.3. Vì sao đặt SET trên function?

`SET search_path = ...` ở định nghĩa function làm PostgreSQL dùng cấu hình đó khi function chạy, thay vì tin vào path tùy ý của session gọi.

Đây là phòng vệ quan trọng cho `SECURITY DEFINER` vì code cần biết **những schema nào được phép tham gia phân giải tên**.

### 13.4. Vì sao pg_catalog ở đầu?

`pg_catalog` cung cấp function/operator/type hệ thống quen thuộc. Liệt kê nó ở đầu đảm bảo không vô ý đặt schema ứng dụng không tin cậy trước các built-in.

### 13.5. Vì sao pg_temp ở cuối?

Vì bảng và type tạm có quy tắc tìm ưu tiên đặc biệt, đặt `pg_temp` tường minh cuối path ngăn nó che bảng/type trusted mà function dùng tên unqualified.

### 13.6. Vì sao vẫn qualified tên bảng và function?

Function sử dụng:

```sql
FROM sp_sec_lab_private.accounts

RETURN sp_sec_lab_private.format_label(v_name);
```

Điều này giảm phụ thuộc vào name lookup và làm code dễ audit. `SET search_path` vẫn hữu ích cho built-ins và các tham chiếu không thể/không được qualified hết trong toàn bộ code.

### 13.7. Tại sao REVOKE EXECUTE trong cùng transaction tạo function?

Mặc định, PostgreSQL thường cấp `EXECUTE` cho `PUBLIC` khi một function mới được tạo. Một privileged routine không nên có khoảng thời gian mà người gọi không mong muốn có thể thực thi nó.

Đặt `CREATE FUNCTION` và `REVOKE ... FROM PUBLIC` trong **cùng transaction** loại bỏ khoảng cấp quyền ngoài ý muốn giữa các commit.

Đối với production, còn phải chủ động `GRANT EXECUTE` cho role cụ thể và `GRANT USAGE` trên schema nếu cần.

### 13.8. Gọi với caller search_path bất lợi

```sql
BEGIN;

SET LOCAL search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private, pg_temp;

SELECT sp_sec_lab_private.describe_account(1);

ROLLBACK;
```

Đây là bài test trên role tạo function trong lab. Function vẫn trỏ tới bảng và helper được schema-qualified; function-level search path đáng tin cũng không phụ thuộc path do caller cài.

### 13.9. Role khác cần được grant cụ thể

Nếu có role `app_runtime` được quản trị tạo trước, lệnh quản trị có thể là:

```sql
-- Chỉ dùng khi role tồn tại và policy cho phép:
-- GRANT USAGE ON SCHEMA sp_sec_lab_private TO app_runtime;
-- GRANT EXECUTE ON FUNCTION
--     sp_sec_lab_private.describe_account(INTEGER)
-- TO app_runtime;
```

Không tự động cấp SELECT trên `sp_sec_lab_private.accounts` nếu mục tiêu là chỉ cho phép thao tác qua function có giới hạn.

### 13.10. SECURITY DEFINER không tự làm function an toàn

Function vẫn cần:

- Authorization theo caller identity khi nghiệp vụ yêu cầu.
- Validation đầu vào.
- Giới hạn ảnh hưởng của thao tác.
- Không dùng dynamic SQL ghép input trực tiếp.
- Owner có ít quyền hơn superuser nếu có thể.
- Review RLS, grants và side effects.

`SECURITY DEFINER` chỉ đổi ngữ cảnh quyền; **nó có thể làm rủi ro tăng** nếu được thiết kế sơ sài.

---

## 14. Tại sao không chỉ dùng SET search_path ở đầu thân function?

### 14.1. Function-level SET

Ưu tiên:

```sql
CREATE FUNCTION app_private.sensitive_action(...)
RETURNS ...
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $function$
BEGIN
    ...
END;
$function$;
```

Mẫu này diễn đạt rằng đường dẫn là **thuộc tính bảo mật của routine**.

### 14.2. SET bên trong body

Nếu function thực thi `SET search_path = ...` sau một số thao tác, những thao tác trước đó có thể đã được xử lý dưới search path khác; việc khôi phục cấu hình cũng phức tạp hơn.

Với những function quan trọng, đặt cấu hình ở phần định nghĩa rõ ràng và dùng qualified names thay vì phụ thuộc một chuỗi lệnh thiết lập rải rác.

### 14.3. Không tin biến cấu hình do caller kiểm soát

Không xây kiểu logic:

```text
SECURITY DEFINER function
  -> đọc path hoặc schema name tùy ý do caller gửi
  -> ghép thành câu SQL
  -> chạy dưới quyền owner
```

Đó có thể là cả **name-resolution vulnerability** lẫn **SQL injection** nếu ghép chuỗi không an toàn.

### 14.4. Dùng dynamic SQL khi thật sự cần

Với `EXECUTE` trong PL/pgSQL, tên bảng/schema động phải được kiểm soát và quote bằng công cụ đúng như `format('%I.%I', schema_name, table_name)` cho identifier, và `USING` cho data values.

Nhưng **quote đúng chưa đủ**: untrusted caller có thể chọn một đối tượng mà privileged function không được phép thao tác theo nghiệp vụ. Phải dùng allowlist/ownership validation bên cạnh quoting.

---

## 15. search_path do client và connection pool thay đổi

### 15.1. SET ảnh hưởng session

```sql
SET search_path = sp_sec_lab_private, public;
```

`SET` thông thường thay session state cho đến khi được reset hoặc session kết thúc, theo quy tắc transaction/config của PostgreSQL.

### 15.2. SET LOCAL ảnh hưởng transaction

```sql
BEGIN;

SET LOCAL search_path = pg_catalog, sp_sec_lab_private, pg_temp;

SELECT current_schemas(true);

COMMIT;
```

`SET LOCAL` có hiệu lực trong transaction hiện hành, sau đó được khôi phục theo semantics cấu hình. Nó phù hợp khi một transaction cần path tạm mà không muốn rò rỉ trạng thái sang request khác.

### 15.3. Session pooling

Nếu một connection pool tái sử dụng session:

```text
Request A: SET search_path = tenant_a, public
              |
              v
        Trả connection về pool
              |
              v
Request B: mượn cùng connection
              |
              v
      search_path có thể vẫn tenant_a
```

Nếu pool không reset session state thích hợp, request sau có thể thao tác sai schema/tenant. Không dùng `search_path` do người dùng tùy ý đặt làm hàng rào tenant duy nhất.

### 15.4. Khuyến nghị

- Cấu hình connection/session startup ổn định.
- Khi có transaction-local context, dùng `SET LOCAL` và bảo đảm transaction kết thúc đúng.
- Reset/kiểm chứng state khi trả connection về pool theo thiết kế driver/pool.
- Với code nhạy cảm, qualified names vẫn cần.
- Đừng gắn role/tenant authorization chỉ vào search path.

### 15.5. search_path không phải SQL injection

SQL injection thường liên quan việc input bị ghép thành SQL code; object hijacking qua search_path là rủi ro **phân giải đối tượng** ngay cả khi query text cố định và bind parameters đúng.

Hai vấn đề có thể kết hợp nhưng không đồng nhất; ứng dụng cần **cả parameterization lẫn trusted namespace resolution**.

---

## 16. Thao tác CREATE không qualified cũng phụ thuộc path

### 16.1. CREATE TABLE không ghi schema

```sql
CREATE TABLE new_records (id bigint);
```

Nếu không ghi schema, PostgreSQL tạo đối tượng trong schema hiện hành thích hợp theo search path, tùy quyền CREATE.

Một migration chạy với path khác dự kiến có thể tạo bảng vào schema sai.

### 16.2. Thí nghiệm trong transaction

```sql
BEGIN;

SET LOCAL search_path =
    pg_catalog, sp_sec_lab_untrusted, sp_sec_lab_private, pg_temp;

SELECT current_schema() AS creation_target;

CREATE TABLE created_by_unqualified_name (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
```

Ví dụ cho thấy search path không chỉ tác động `SELECT`, mà còn chọn namespace khi `CREATE` đối tượng chưa có schema tường minh. `ROLLBACK` giữ lab sạch.

### 16.3. Migration nên dùng qualified names

```sql
CREATE TABLE app.orders (...);
CREATE INDEX orders_created_at_idx ON app.orders(created_at);
CREATE FUNCTION app_private.calculate_total(...) ...;
```

Đây là mẫu cú pháp. Ghi tường minh schema trong migration làm giảm phụ thuộc vào default path của user chạy migration.

### 16.4. Extension cũng có schema cài đặt

`CREATE EXTENSION` có các quy tắc lựa chọn schema tùy extension và cú pháp. Các objects được cài đặt vào namespace nhất định; điều đó ảnh hưởng đến path và quyền tạo/tra cứu.

Không cấp quyền cài extension hoặc chọn schema cài extension một cách tùy tiện. Với các extension có SQL scripts, đặc biệt cần theo hướng dẫn bảo mật của extension/PostgreSQL và đảm bảo schema được sử dụng là trusted.

### 16.5. Schema-qualification không bù quyền thiếu

`CREATE TABLE app.orders` vẫn cần quyền thích hợp. Qualified name chỉ xác định **đích**, không bypass permission checks.

---

## 17. View và lưu định nghĩa đối tượng: đừng suy quá mức

### 17.1. Khi CREATE VIEW

PostgreSQL phân tích truy vấn định nghĩa view, xác định những đối tượng được tham chiếu và lưu các phụ thuộc trong hệ thống.

```sql
CREATE VIEW sp_sec_lab_private.v_items AS
SELECT item_id, label
FROM sp_sec_lab_private.sample_items;
```

### 17.2. Cẩn trọng với lời khẳng định “đổi path đổi mọi view”

Một view đã được tạo **không tương đương** với việc lưu text SQL rồi phân giải lại tất cả tên bảng từ đầu theo `search_path` của người gọi trong mọi lần SELECT. PostgreSQL lưu cây truy vấn/phụ thuộc của view.

Điểm cần audit là:

- Path nào đã được dùng **khi tạo view** nếu định nghĩa viết tên không qualified?
- View đang phụ thuộc đối tượng OID nào?
- Owner và quyền đọc của view như thế nào?
- Các function/operator liên quan có semantics an toàn không?

### 17.3. Function có nhiều cách lưu/compile body

PL/pgSQL, SQL functions và các dạng body khác nhau có cơ chế parse/plan/cache riêng. Không nói một cách tuyệt đối rằng mọi unqualified name trong mọi routine đều được phân giải lại mỗi invocation.

Biện pháp phòng vệ thực tế vẫn là **cố định trusted search_path cho code đặc quyền và qualified những tham chiếu quan trọng**, sau đó kiểm tra dependencies/behavior trên phiên bản PostgreSQL đang dùng.

### 17.4. CREATE VIEW trong untrusted schema

Nếu một role được quyền tạo view trong schema mà privileged code tin cậy, code có thể bị ảnh hưởng nếu gọi tên view/table unqualified. Nhưng quyền thực thi và quy tắc owner/invoker/RLS của view phải được phân tích riêng; không suy mọi view luôn thực thi quyền của owner trong mọi phiên bản/cấu hình.

---

## 18. Kiểm toán schema public và quyền CREATE

**Không thay đổi quyền trước khi quan sát hiện trạng.**

### 18.1. Phiên bản và database đang kiểm tra

```sql
SELECT
    current_database() AS database_name,
    current_user AS effective_user,
    session_user AS session_user,
    current_setting('server_version') AS server_version,
    current_setting('search_path') AS configured_search_path;
```

### 18.2. Xem owner và ACL của public

```sql
SELECT
    n.nspname AS schema_name,
    pg_get_userbyid(n.nspowner) AS schema_owner,
    n.nspacl AS acl
FROM pg_namespace AS n
WHERE n.nspname = 'public';
```

`nspacl` cho thấy các quyền được lưu trong catalog. Giá trị NULL có thể biểu thị dùng mặc định quyền, **không tự động nghĩa là không có quyền nào**.

### 18.3. Kiểm tra quyền hiệu lực của current_user

```sql
SELECT
    has_schema_privilege('public', 'USAGE')
        AS can_use_public,
    has_schema_privilege('public', 'CREATE')
        AS can_create_in_public;
```

Nếu role có thể CREATE, cần xác định **quyền đến từ đâu**:

- Là owner của schema/database thích hợp.
- Là thành viên role có quyền.
- Có grant trực tiếp.
- Có quyền được cấp cho `PUBLIC`.
- Có quyền quản trị rộng khác.

Một giá trị `true` không nhất thiết chứng minh grant được cấp **cho PUBLIC**.

### 18.4. Kiểm tra các login roles có thể CREATE trong public

```sql
SELECT
    r.rolname,
    r.rolcanlogin,
    has_schema_privilege(
        r.oid,
        'public',
        'CREATE'
    ) AS can_create_in_public
FROM pg_roles AS r
WHERE r.rolcanlogin
ORDER BY r.rolname;
```

Truy vấn giúp tìm các login roles có quyền CREATE hiệu lực theo dữ liệu catalog/role membership và ngữ cảnh database hiện tại. Khi đánh giá triển khai thực tế, còn cần kiểm tra SET ROLE, owner, group memberships và các đường cấp quyền khác.

### 18.5. Xem quyền bằng psql

Trong `psql`:

```text
\dn+
```

Lệnh meta của psql hiển thị danh sách schema, owner và access privileges theo phiên bản client. Không chạy `\dn+` như một SQL statement trong JDBC.

### 18.6. Phân tích ACL có cấu trúc

```sql
SELECT
    n.nspname,
    x.grantee,
    x.privilege_type,
    x.is_grantable
FROM pg_namespace AS n
CROSS JOIN LATERAL aclexplode(
    COALESCE(
        n.nspacl,
        acldefault('n', n.nspowner)
    )
) AS x
WHERE n.nspname = 'public'
ORDER BY x.grantee, x.privilege_type;
```

Trong ACL, grantee có giá trị đặc biệt tương ứng `PUBLIC`; cột `grantee` là OID role, không phải text “mọi người”. Query này hữu ích để nhìn grants lưu trong ACL/default ACL. Để đánh giá **quyền hiệu lực thực sự** của một role, vẫn cần `has_schema_privilege` và xem role membership/ownership.

---

## 19. Thu hồi CREATE khỏi PUBLIC: làm đúng quy trình

### 19.1. Lệnh cốt lõi

```sql
-- Chỉ triển khai sau khi đã audit và được phê duyệt:
-- REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Đây là bước hardening quan trọng đối với database đang cấp CREATE cho mọi role trên public.

### 19.2. Không nên làm mù quáng trên production

Ứng dụng hoặc migration cũ có thể đang dựa vào quyền tạo đối tượng trong `public`. Nếu thu hồi CREATE, những quy trình này có thể lỗi, ví dụ:

- Tạo bảng tạm **không** dùng TEMP mà tạo table bình thường trong public.
- Tạo function khi deploy.
- Một extension/ETL job tạo đối tượng trong public.
- Migration chạy dưới role ứng dụng ít quyền.

### 19.3. Quy trình an toàn

1. Kiểm kê roles và quyền CREATE hiệu lực.
2. Tìm các schema và đối tượng được tạo thường xuyên.
3. Xác định migration role trusted, runtime roles và service accounts.
4. Chuyển DDL sang schema chuyên biệt/role quản trị phù hợp.
5. Thử revoke trong staging có cùng ACL/data shape.
6. Áp revoke ở thời điểm được phép.
7. Quan sát lỗi permission, deployment và jobs.
8. Đảm bảo không cấp lại CREATE cho PUBLIC qua script cũ.

### 19.4. Quyền CREATE được cấp trực tiếp vẫn còn

`REVOKE CREATE ... FROM PUBLIC` **không tự thu hồi** các grants riêng đã cấp cho một role cụ thể và không tước quyền ownership. Nếu muốn chặn một role không đáng tin, phải kiểm toán mọi nguồn quyền hiệu lực.

### 19.5. Tách runtime role và migration role

Một mô hình tốt:

```text
db_owner / migration_owner:
    DDL trong schema trusted

app_runtime:
    USAGE trên schema cần đọc
    SELECT/INSERT/UPDATE/DELETE trên bảng phù hợp
    EXECUTE trên function đã duyệt
    KHÔNG CREATE trong schema trusted

report_reader:
    Chỉ quyền đọc cần thiết
```

Đừng chạy ứng dụng web bằng superuser hoặc schema owner chỉ để không gặp lỗi grants.

---

## 20. Đặt search_path cho role và database

### 20.1. ALTER ROLE SET

```sql
-- Ví dụ quản trị khi app_runtime đã tồn tại:
-- ALTER ROLE app_runtime
-- SET search_path = pg_catalog, app, pg_temp;
```

Thiết lập này là default cho các session tương ứng khi kết nối theo quy tắc config. Nó không thay thế việc gắn `SET search_path` trực tiếp vào `SECURITY DEFINER` functions.

### 20.2. ALTER DATABASE SET

```sql
-- Ví dụ cú pháp, phải thay appdb bằng tên database thực:
-- ALTER DATABASE appdb
-- SET search_path = pg_catalog, app, pg_temp;
```

Đây là default ở cấp database, có thể bị những lớp cấu hình ưu tiên hơn ghi đè.

### 20.3. ALTER ROLE IN DATABASE

```sql
-- Ví dụ cú pháp:
-- ALTER ROLE app_runtime IN DATABASE appdb
-- SET search_path = pg_catalog, app, pg_temp;
```

Một lựa chọn khi cùng role kết nối nhiều databases nhưng mỗi database dùng namespace khác nhau.

### 20.4. Cảnh báo về trạng thái session đang tồn tại

Đổi default role/database thường ảnh hưởng **những session mới** khi cấu hình được áp dụng; những connection đang giữ trong pool có thể tiếp tục dùng session state đã đặt từ trước. Kế hoạch rollout cần xét reconnect/pool recycle.

### 20.5. Không để path là lựa chọn bảo mật duy nhất

Nếu role có quyền CREATE trong `app` hoặc `public` nằm trên path của `SECURITY DEFINER`, chỉ đưa `app` lên đầu không làm nó an toàn. Phải xét **trust của object creators**.

---

## 21. Search path cho function nhạy cảm: quy tắc lựa chọn

### 21.1. Một mẫu đáng tin

```sql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
```

Điều kiện tiên quyết:

- `app_private` thuộc owner/migration roles tin cậy.
- Không có untrusted role được `CREATE` tại đó.
- Function không gọi object không tin cậy qua dynamic SQL.
- Những table/function quan trọng được schema-qualified khi có thể.

### 21.2. Tại sao không giữ public trong path?

`public` có thể là schema ứng dụng hợp lệ nhưng ở một số database cũ nó có thể chứa objects do nhiều roles tạo. Với privileged function, đừng đưa `public` vào path chỉ để tránh phải qualified một vài bảng.

Nếu phải gọi `public.some_function`, cân nhắc:

- Migrate function tới một schema trusted.
- Qualified tên đối tượng và review owner/chữ ký.
- Không cấp CREATE cho untrusted roles trên public.

### 21.3. Không dùng "$user" trong đường dẫn privileged code

`"$user"` có thể trỏ tới schema khác tùy effective user. Trong `SECURITY DEFINER`, effective user có thể là owner của function. Dù hành vi cụ thể phụ thuộc ngữ cảnh, một path thay đổi theo user khó audit hơn một danh sách schema tường minh và trusted.

### 21.4. Chú ý search_path của function gọi function khác

Nếu `definer_a` gọi `definer_b` hoặc helper, cần xem:

- `definer_b` có function-level `SET search_path` riêng không?
- Ai sở hữu helper?
- Helper có dynamic SQL hoặc unqualified references không?
- Helper có `SECURITY DEFINER` hay `SECURITY INVOKER`?

Không nghĩ một function cấp trên đã an toàn thì mọi function ở sâu trong call chain tự an toàn.

### 21.5. Default EXECUTE trên function

`GRANT EXECUTE` của PostgreSQL không tự suy từ quyền SELECT trên table. Cần thiết kế quyền gọi từng privileged routine:

```sql
-- Mẫu quản trị:
-- REVOKE ALL ON FUNCTION app_private.sensitive_action(integer)
-- FROM PUBLIC;
--
-- GRANT EXECUTE ON FUNCTION app_private.sensitive_action(integer)
-- TO app_runtime;
```

Không cấp `EXECUTE` chung chỉ vì function tồn tại trong schema mà application truy cập.

---

## 22. Application authorization, RLS và definer privileges

### 22.1. Schema privilege không thay row-level authorization

Role có quyền `USAGE` trên schema và `SELECT` trên bảng vẫn có thể cần RLS để ngăn đọc rows của tenant khác.

`search_path` không phải một bộ lọc `tenant_id` và không phải chính sách RLS.

### 22.2. SECURITY DEFINER và RLS

`SECURITY DEFINER` dùng quyền owner; khi function owner là table owner hoặc có quyền bypass RLS, function có thể nhìn dữ liệu khác với caller theo các quy tắc RLS tương ứng.

Đối với function đa tenant, cần:

- Xác thực caller identity theo nguồn đáng tin.
- Giới hạn tenant/data scope trong SQL.
- Kiểm tra behavior dưới role thật.
- Xem owner và chính sách `FORCE ROW LEVEL SECURITY` khi phù hợp.

### 22.3. Đừng tin tenant_id do client nhập

Một privileged routine nhận `p_tenant_id` do ứng dụng truyền có thể phải kiểm tra người gọi có quyền với tenant đó. Chỉ vì tham số đã bind an toàn không chứng minh người gọi sở hữu tenant.

### 22.4. Function definer nên có quyền tối thiểu

Nếu routine chỉ cần đọc bảng phân quyền và cập nhật một bảng nghiệp vụ, owner của routine không cần là superuser. Quyền càng rộng, tác động của name resolution bug càng lớn.

---

## 23. Security audit trên function và routine

### 23.1. Liệt kê SECURITY DEFINER functions

```sql
SELECT
    n.nspname AS function_schema,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS args,
    pg_get_userbyid(p.proowner) AS owner,
    p.prosecdef AS security_definer,
    p.proconfig AS function_settings
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE p.prosecdef
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY n.nspname, p.proname;
```

`prosecdef=true` biểu thị SECURITY DEFINER; `proconfig` chứa những function-local GUC settings nếu được khai báo.

### 23.2. proconfig NULL không tự chứng minh lỗ hổng

Nếu `proconfig` không chứa `search_path`, function có thể chịu ảnh hưởng path khác. Đây là **dấu hiệu cần review**, không phải bằng chứng ngay lập tức rằng function có thể bị chiếm quyền. Nó có thể chỉ dùng qualified names/không gọi SQL nhạy cảm, nhưng vẫn cần xác định.

### 23.3. Xem định nghĩa để audit

```sql
SELECT pg_get_functiondef(
    'sp_sec_lab_private.describe_account(integer)'::regprocedure
);
```

`pg_get_functiondef` giúp inspect function body/config. Lưu ý body PL/pgSQL có thể gọi function khác hoặc dynamic SQL, nên review phải đi theo dependency/call chain.

### 23.4. Kiểm tra quyền EXECUTE

```sql
SELECT
    has_function_privilege(
        'sp_sec_lab_private.describe_account(integer)',
        'EXECUTE'
    ) AS current_role_can_execute;
```

Đây là kiểm tra **role hiện tại**. Muốn audit role khác, dùng overload có chỉ định role và xem role membership/privileges thực tế.

### 23.5. Xem routine chứa search_path config

```sql
SELECT
    p.oid::regprocedure AS routine,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
JOIN pg_namespace AS n ON n.oid = p.pronamespace
WHERE n.nspname = 'sp_sec_lab_private'
ORDER BY p.oid::regprocedure::text;
```

Với `describe_account`, kỳ vọng `proconfig` thể hiện `search_path=pg_catalog, sp_sec_lab_private, pg_temp` theo định nghĩa.

---

## 24. Quyền CREATE trên schema trusted và default privileges

### 24.1. Role runtime không cần tạo đối tượng trong schema code

Mô hình an toàn:

```text
app_runtime:
  USAGE on app
  SELECT/INSERT/UPDATE/DELETE trên bảng cần thiết
  EXECUTE trên routine cần gọi
  NO CREATE on app_private
```

Quyền `CREATE` nên dành cho trusted migration/owner roles.

### 24.2. Default privileges không tự quản lý schema CREATE

`ALTER DEFAULT PRIVILEGES` điều khiển default grants cho các đối tượng được tạo **sau này** bởi role thích hợp, không phải phép thay thế trực tiếp cho:

```sql
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
```

Hai loại quyền ở hai lớp khác nhau.

### 24.3. Hạn chế default EXECUTE của routine mới

Khi xây nhiều privileged routines, có thể cân nhắc:

```sql
-- Mẫu quản trị, áp dụng cho role tạo function tương ứng:
-- ALTER DEFAULT PRIVILEGES
-- REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
```

Cần hiểu phạm vi **role tạo objects và default privileges**; không giả định câu này retroactively sửa mọi function cũ hoặc áp cho mọi role.

### 24.4. GRANT USAGE không làm an toàn một schema có CREATE mở rộng

Nếu untrusted roles đã có CREATE trên một schema trong search path của privileged code, việc thêm GRANT USAGE cho các role khác không làm rủi ro biến mất.

Muốn xử lý trust boundary phải kiểm soát **ai được tạo đối tượng** và **đối tượng nào được phân giải**.

---

## 25. Kiểu đối tượng và những vị trí dễ bỏ sót khi audit

| Vị trí | Rủi ro khi không qualified | Hướng phòng vệ |
|---|---|---|
| `FROM accounts` | Đọc bảng/view trùng tên | `app.accounts` |
| `UPDATE balances` | Ghi sai relation | `app.balances` và kiểm tra quyền |
| `PERFORM helper(...)` | Chọn helper/overload không tin cậy | `app_private.helper(...)`, kiểu args rõ |
| `SELECT x + y` | Operator resolution có thể bị ảnh hưởng trong ngữ cảnh đặc biệt | Trusted path, kiểu args, qualification khi cần |
| Cast tới type không qualified | Type shadowing | Qualified type / trusted path |
| `nextval('sequence_name')` | Có thể phụ thuộc cách resolve sequence | `'schema.sequence_name'::regclass` thích hợp |
| CREATE TABLE không qualified | Tạo bảng nhầm schema | `CREATE TABLE app.name` |
| Extension objects | Cài/tra cứu ở schema không phù hợp | Cài trong schema trusted theo docs |
| Dynamic SQL với tên schema/table | Chọn nhầm object hoặc injection | Allowlist, `format('%I',...)`, parameters |
| Trigger function `SECURITY DEFINER` | Chạy dưới owner, có thể bị ảnh hưởng path | Function-level SET path và audit function |

### 25.1. regclass và tên sequence

Với một sequence đáng tin, nên chỉ rõ tên schema trong một literal được ép kiểu:

```sql
-- Ví dụ khi app.order_id_seq tồn tại:
-- SELECT nextval('app.order_id_seq'::regclass);
```

Một số biểu thức `regclass` được resolve tại thời điểm parse/plan theo semantics của cast; không đồng nhất nó với string được nối động không kiểm soát.

### 25.2. Dynamic identifier phải được kiểm soát nghiệp vụ

`format('%I.%I', schema_name, table_name)` chỉ **quote identifier**, không đảm bảo schema/table được phép đối với tác vụ. Với privileged routine, hãy xác minh nguồn của identifiers và giới hạn allowlist.

---

## 26. Kiểm thử bảo mật theo vai trò và path

### 26.1. Đừng chỉ test bằng database owner

Database owner thường có nhiều quyền, nên test dưới owner có thể bỏ qua những lỗi `permission denied` hoặc behavior RLS chỉ xuất hiện với role runtime.

### 26.2. Ma trận thử nghiệm

| Tình huống | Điều cần xác minh |
|---|---|
| Caller dùng path chuẩn | Truy vấn/function chạy đúng |
| Caller cố tình đặt schema mô phỏng untrusted trước | Routine nhạy cảm vẫn tham chiếu đúng object |
| Caller tạo TEMP TABLE trùng tên bảng trusted | Routine definer không đọc nhầm temp table |
| Role không có CREATE trên public | Không tạo được object trong public |
| Role không có EXECUTE trên privileged routine | Lời gọi bị từ chối |
| Role được EXECUTE nhưng không được SELECT trực tiếp | Chỉ thao tác giới hạn qua function hoạt động |
| Role tenant A gọi với tenant B | Bị authorization/RLS từ chối đúng |
| Migrations dùng path khác | Objects vẫn được tạo đúng schema |
| Session trong pool tái sử dụng | Không giữ path/tenant từ request trước |

### 26.3. Cách mô phỏng path khác mà không thay session lâu dài

```sql
BEGIN;

SET LOCAL search_path =
    sp_sec_lab_untrusted, pg_catalog, sp_sec_lab_private, pg_temp;

SELECT
    current_setting('search_path') AS configured,
    current_schemas(true) AS resolved;

SELECT sp_sec_lab_private.describe_account(1);

ROLLBACK;
```

Tất cả thay đổi path trong đoạn này là transaction-local. Function vẫn cần được gọi bằng tên schema tường minh.

### 26.4. Test temp table theo đúng loại đối tượng

`pg_temp` ưu tiên cho table/type, không phải function/operator. Hãy test một temporary table cùng tên với relation mà definer function dùng; đừng đưa ra kết luận dựa trên hành vi khác loại đối tượng.

### 26.5. Ghi nhận kết quả test

Nên lưu:

- PostgreSQL version.
- Role/session user.
- Current path và resolved schemas.
- Schema owner và ACL.
- Definition/config của routine.
- Kết quả expected/actual và lỗi SQLSTATE.

Không đưa secret, token hoặc connection password vào log test.

---

## 27. Kế hoạch hardening database đã vận hành lâu

### Giai đoạn 1 — Inventory

1. Liệt kê databases và versions.
2. Audit owner/ACL của schema `public` trong từng database.
3. Liệt kê login roles có thể CREATE trong public.
4. Liệt kê toàn bộ schemas nằm trong search path của app/jobs.
5. Liệt kê `SECURITY DEFINER` routines và quyền EXECUTE.
6. Tìm unqualified references/dynamic SQL trong code quan trọng.

### Giai đoạn 2 — Chốt mục tiêu

1. Runtime roles không được CREATE trong trusted schemas.
2. DDL dùng migration owner có kiểm soát.
3. Privileged routines có trusted function-level search_path.
4. Objects nhạy cảm được schema-qualified.
5. Privileged routine EXECUTE chỉ grant cho roles cần.
6. Mọi pool/connection startup có đường dẫn xác định.

### Giai đoạn 3 — Triển khai

1. Tạo schema trusted nếu cần.
2. Di chuyển routine/bảng khỏi public nếu chúng không nên thuộc namespace dùng chung.
3. Cập nhật references, grants và application code.
4. Thiết lập function-level search_path.
5. Thu hồi quyền CREATE từ PUBLIC hoặc các roles không đáng tin theo chính sách.
6. Triển khai migration theo thứ tự đã test.
7. Kiểm tra objects/roles sau rollout.

### Giai đoạn 4 — Vận hành

1. Tự động audit quyền CREATE/EXECUTE.
2. Kiểm tra privileged routines mới trước khi deploy.
3. Review thay đổi owner, extension và default privileges.
4. Giám sát các lỗi permission bất thường.
5. Test pool state và multi-tenant boundaries.
6. Có quy trình rollback migration nhưng không mở lại quyền quá rộng thiếu lý do.

### 27.1. Chuyển object khỏi public cần kế hoạch

`ALTER ... SET SCHEMA` có thể làm thay đổi tên qualified mà ứng dụng sử dụng, phụ thuộc catalog, grants và search path. Không mass-move toàn bộ objects khỏi `public` bằng script mà chưa đánh giá application queries, dependencies, extensions, RLS và quyền.

### 27.2. Revoke CREATE không xóa đối tượng đã được tạo

Ngay cả sau khi khóa quyền CREATE, những function/table lạ được tạo trước đó vẫn có thể tồn tại trong `public`. Một audit đầy đủ phải xem **đối tượng hiện có, owner và mã của chúng**, không chỉ ACL hiện tại.

---

## 28. Những nhầm lẫn và lỗi thường gặp

**1. “search_path chỉ ảnh hưởng SELECT FROM.”** Sai. Nó còn liên quan function, type, operator và namespace tạo object.

**2. “public là role.”** Sai. `public` là schema; `PUBLIC` trong GRANT/REVOKE là pseudo-role chỉ tập mọi roles.

**3. “USAGE trên schema đồng nghĩa SELECT mọi bảng.”** Sai. Quyền trên schema và quyền trên objects là các lớp riêng.

**4. “CREATE trên schema chỉ cho phép tạo bảng vô hại.”** Sai. Khả năng tạo những objects được tra cứu bởi privileged code có thể là rủi ro lớn.

**5. “Mặc định PostgreSQL 15+ nghĩa tất cả database nâng cấp đều an toàn.”** Không. Audit ACL từng database.

**6. “REVOKE CREATE FROM PUBLIC thu hồi mọi direct grant.”** Không.

**7. “REVOKE ALL trên public không ảnh hưởng ứng dụng.”** Có thể thu hồi USAGE và làm lỗi code đang chạy.

**8. “Không liệt kê pg_catalog thì nó không được tìm.”** Sai. Nó thường được tìm ngầm.

**9. “pg_catalog luôn được tìm trước bất kể cấu hình.”** Sai. Khi nêu tường minh, vị trí của nó trong path có ý nghĩa.

**10. “pg_temp chỉ được dùng khi ghi tên rõ.”** Sai. Với relation/type, nó có thể được tìm ngầm ở vị trí ưu tiên.

**11. “pg_temp dùng để shadow function và operator theo cùng quy tắc bảng tạm.”** Không.

**12. “SECURITY DEFINER function không cần SET search_path.”** Rất rủi ro nếu có unqualified references và untrusted schemas.

**13. “SECURITY DEFINER đồng nghĩa hàm đã an toàn.”** Không. Nó mở rộng bề mặt rủi ro qua quyền owner.

**14. “Chỉ cần SET search_path là không cần qualified names.”** Sai. Qualification làm code ít phụ thuộc lookup và dễ audit.

**15. “Đặt pg_temp trước trusted schema là cách mặc định an toàn.”** Không, relation/type temporary có thể che đối tượng trusted.

**16. “Function không trùng chữ ký sẽ không có nguy cơ overloading.”** Sai. Function resolution xét argument types/casts/variadic/defaults.

**17. “PreparedStatement tự ngăn object hijacking.”** Không. Binding data parameters không bảo đảm name resolution.

**18. “current_setting('search_path') luôn bằng resolved search path.”** Không. Có implicit schemas, phần tử không tồn tại hoặc không thể dùng.

**19. “current_schema() luôn là public.”** Không, phụ thuộc path và schema có thể dùng.

**20. “Một schema trong search_path mặc nhiên cấp USAGE cho role.”** Không.

**21. “SET LOCAL giữ path sau COMMIT trong pooled session.”** Không theo scope transaction-local.

**22. “SET session sẽ tự reset khi connection được trả về pool.”** Không được mặc định; tùy pool/reset policy.

**23. “Tách schema tenant bảo đảm tenant isolation dù ai cũng có CREATE.”** Không. Cần quyền/authorization/RLS và kiểm soát namespace.

**24. “Code không ghép SQL string thì chắc không còn rủi ro tên đối tượng.”** Không. Còn search_path/overloading.

**25. “Sửa function owner sang superuser giúp hết lỗi quyền và an toàn hơn.”** Ngược lại, tăng hậu quả khi code lỗi.

**26. “Mọi SECURITY DEFINER routine nên được PUBLIC EXECUTE.”** Không. Ưu tiên grants tối thiểu.

**27. “CREATE FUNCTION rồi hôm sau REVOKE PUBLIC là không có khoảng mở quyền.”** Sai. Nên làm trong cùng transaction.

**28. “ALTER DEFAULT PRIVILEGES tự thu hồi quyền CREATE trên schema public.”** Không.

**29. “REVOKE CREATE xóa các objects đã bị cài vào public trước đó.”** Không.

**30. “ALTER ROLE SET search_path cập nhật tức thì mọi pooled session hiện tại.”** Không được giả định.

**31. “View đã tạo sẽ phân giải lại mọi bảng theo path của caller ở mỗi SELECT.”** Không đúng một cách tổng quát; view lưu định nghĩa/phụ thuộc đối tượng.

**32. “Routine body luôn được phân giải tên một lần đúng thời điểm CREATE bất kể loại language.”** Không. Cần hiểu semantics của body/language/plan và cố định namespace.

**33. “format('%I', input) bảo đảm caller được phép chọn mọi schema.”** Không. Nó chỉ quote identifier.

**34. “Qualified SQL name bypass GRANT/REVOKE.”** Không. Quyền vẫn được kiểm tra.

**35. “Bật RLS trên base table tự làm mọi SECURITY DEFINER function bảo toàn tenant.”** Không. Owner/role và RLS bypass cần được review.

**36. “Đăng nhập bằng database owner trong test đại diện mọi role.”** Không. Quyền của runtime có thể khác.

**37. “Extension cài vào schema nào cũng như nhau.”** Không. Schema/owner và extension scripts có thể ảnh hưởng trust boundary.

**38. “Có CREATE ở public chỉ là vấn đề thẩm mỹ.”** Không. Với privileged unqualified lookups, có thể là lỗi bảo mật.

**39. “Không cần audit database cũ vì server đã nâng cấp.”** Sai. ACL và objects cũ có thể còn.

**40. “Một path tốt cho app runtime tự làm path của SECURITY DEFINER an toàn.”** Không. Function cần contract riêng.

---

## 29. Bài tập thực hành và đáp án

### Bài 1 — search_path dùng để làm gì?

**Câu hỏi:** Vì sao `SELECT * FROM sample_items` có thể trả dữ liệu khác khi đổi path?

**Đáp án:** Vì tên không qualified được phân giải trong các schema có thể dùng theo search path. Hai schema cùng có `sample_items`, schema được chọn ảnh hưởng kết quả.

### Bài 2 — Qualified name

**Yêu cầu:** đọc bảng trusted bất kể session path.

```sql
SELECT *
FROM sp_sec_lab_private.sample_items;
```

### Bài 3 — SHOW và current_schemas

```sql
SHOW search_path;
SELECT current_schema(), current_schemas(true);
```

**Đáp án:** `SHOW` hiển thị giá trị cấu hình, `current_schema` cho schema hiện hành, còn `current_schemas(true)` hiển thị danh sách resolved có các implicit schemas.

### Bài 4 — public và PUBLIC

**Câu hỏi:** Trong `REVOKE CREATE ON SCHEMA public FROM PUBLIC`, hai từ có cùng nghĩa không?

**Đáp án:** Không. Một là tên schema, một là pseudo-role của mọi roles.

### Bài 5 — USAGE và CREATE

**Câu hỏi:** Một role chỉ có `USAGE` trên `public` có thể tự `CREATE TABLE public.x` không?

**Đáp án:** Không chỉ nhờ `USAGE`. Cần `CREATE` hiệu lực hoặc quyền ownership/quyền khác thích hợp.

### Bài 6 — PostgreSQL 15 mặc định

**Câu hỏi:** Điểm cải thiện mặc định về public trong database mới từ PostgreSQL 15?

**Đáp án:** Mặc định không còn grant CREATE trên public cho pseudo-role PUBLIC, và schema public thường thuộc `pg_database_owner`.

### Bài 7 — Database nâng cấp

**Câu hỏi:** Server phiên bản 16 có chắc `PUBLIC` không có CREATE ở public?

**Đáp án:** Không. Database có thể giữ ACL cũ hoặc đã tùy chỉnh; phải audit thực tế.

### Bài 8 — Kiểm tra CREATE

```sql
SELECT has_schema_privilege('public', 'CREATE');
```

**Đáp án:** Kiểm tra quyền CREATE hiệu lực của current user trên schema public, không trực tiếp chứng minh grant cho pseudo-role PUBLIC.

### Bài 9 — Quyền grant direct

**Câu hỏi:** `REVOKE CREATE ... FROM PUBLIC` có xóa quyền được grant riêng cho role app_deployer không?

**Đáp án:** Không tự xóa direct grants; cần kiểm tra và xử lý từng nguồn quyền.

### Bài 10 — pg_catalog implicit

**Câu hỏi:** Nếu SHOW search_path là `"$user", public`, PostgreSQL có bỏ qua `pg_catalog` không?

**Đáp án:** Không. `pg_catalog` thường được tra cứu ngầm trước các schema path nếu không được liệt kê tường minh.

### Bài 11 — pg_catalog explicit

**Câu hỏi:** Vì sao `SET search_path = untrusted, pg_catalog` nguy hiểm?

**Đáp án:** Khi `pg_catalog` được liệt kê tường minh sau untrusted, một số tên có thể được tra cứu theo ưu tiên không mong muốn; privileged code không nên tin untrusted schema phía trước.

### Bài 12 — pg_temp

**Câu hỏi:** Khi không liệt kê `pg_temp`, loại tên nào có thể bị temporary schema che khuất?

**Đáp án:** Relation và data type theo quy tắc tra cứu đặc biệt. Function/operator không được tìm trong temporary schema giống bảng.

### Bài 13 — Secure path

```sql
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp;
```

**Đáp án:** Đặt built-ins ở đầu, schema trusted tiếp theo và temp schema cuối; cần bảo đảm không có untrusted CREATE trên schema trusted.

### Bài 14 — SECURITY DEFINER

**Câu hỏi:** Function `SECURITY DEFINER` dùng quyền của ai?

**Đáp án:** Function owner theo semantics PostgreSQL, không đơn thuần dùng quyền caller như SECURITY INVOKER.

### Bài 15 — Function-level path

**Yêu cầu:** Viết phần thuộc tính bảo vệ namespace cho function đặc quyền.

```sql
SECURITY DEFINER
SET search_path = pg_catalog, sp_sec_lab_private, pg_temp
```

### Bài 16 — Vì sao qualified table?

**Đáp án:** `FROM sp_sec_lab_private.accounts` cố định namespace dự kiến và giảm tác động từ path của caller.

### Bài 17 — Dynamic SQL

**Câu hỏi:** Dùng `format('%I.%I',schema,table)` có làm mọi object caller chọn trở nên được phép không?

**Đáp án:** Không. Nó chỉ quote identifiers; cần allowlist và authorization.

### Bài 18 — PUBLIC EXECUTE

**Câu hỏi:** Vì sao nên `REVOKE EXECUTE ... FROM PUBLIC` ngay sau CREATE privileged function trong cùng transaction?

**Đáp án:** Tránh khoảng routine mới bị gọi bởi role không được dự định cấp quyền, đồng thời công bố routine với permissions đã thiết lập.

### Bài 19 — Connection pool

**Tình huống:** Request A `SET search_path=tenant_a` rồi trả session về pool. Request B dùng lại session.

**Đáp án:** Nếu pool không reset session state, B có thể vẫn dùng path của A. Dùng startup/reset và transaction-local settings đúng contract, không dựa vào path như tenant authorization.

### Bài 20 — SQL injection khác object hijack

**Đáp án:** Prepared statements bảo vệ data parameterization, nhưng không tự khóa việc một tên không qualified được resolve tới object trong schema không đáng tin.

### Bài 21 — CREATION TARGET

**Yêu cầu:** xem schema tạo object mặc định.

```sql
SELECT current_schema();
```

### Bài 22 — View tồn tại

**Câu hỏi:** Khi caller đổi search_path, view đã tạo sẽ tự chuyển mọi relation references sang bảng cùng tên mới không?

**Đáp án:** Không thể giả định vậy; view lưu cây truy vấn và dependencies trên những objects đã phân giải trong định nghĩa.

### Bài 23 — RLS

**Câu hỏi:** SECURTY DEFINER có thể ảnh hưởng hành vi RLS không?

**Đáp án:** Có; execution role/owner và khả năng bypass RLS cần được xem xét riêng với chính sách tenant.

### Bài 24 — Chọn owner

**Câu hỏi:** Để privileged function hoạt động, có nên làm owner của nó thành superuser ngay?

**Đáp án:** Không nếu không cần. Dùng owner với quyền tối thiểu, giảm tác động nếu function có lỗ hổng.

### Bài 25 — Audit function

```sql
SELECT
    p.oid::regprocedure,
    p.prosecdef,
    p.proconfig
FROM pg_proc AS p
WHERE p.prosecdef;
```

**Đáp án:** Tìm SECURITY DEFINER routines và cấu hình function-local để đánh giá search_path; không coi `proconfig NULL` là kết luận tự động có lỗ hổng.

### Bài 26 — Audit role

```sql
SELECT
    rolname,
    has_schema_privilege(oid, 'public', 'CREATE')
        AS can_create_public
FROM pg_roles
WHERE rolcanlogin;
```

**Đáp án:** Liệt kê login roles có quyền CREATE hiệu lực trên public trong database đang kết nối.

### Bài 27 — REVOKE CREATE

**Câu hỏi:** Tác dụng của `REVOKE CREATE ON SCHEMA public FROM PUBLIC` là gì?

**Đáp án:** Thu hồi grant CREATE cấp chung cho mọi roles trên schema public, không xóa schema hoặc các objects đã có.

### Bài 28 — Chuyển objects

**Câu hỏi:** Có thể đơn giản chạy `ALTER ... SET SCHEMA` cho mọi object public mà không đánh giá code không?

**Đáp án:** Không. Phải kiểm tra dependencies, references, extension ownership, grants và migrations.

### Bài 29 — Pg temp function

**Câu hỏi:** Có thể tạo một function ở pg_temp rồi tin nó sẽ shadow function thường khi gọi unqualified không?

**Đáp án:** Không theo cơ chế lookup special dành cho temp relations/types; PostgreSQL không tìm temporary schema cho functions/operators theo cách ấy.

### Bài 30 — Security audit rollout

**Yêu cầu:** Nêu bốn kiểm tra tối thiểu trước khi gọi database đã hardening search_path.

**Đáp án:** (1) ACL/owner và CREATE hiệu lực trên public/trusted schemas; (2) SECURITY DEFINER routines có path và qualification an toàn; (3) quyền EXECUTE/USAGE đúng roles; (4) thực nghiệm dưới caller path khác, temp relation shadowing và connection pool state. Nên kiểm tra thêm RLS, extensions, migrations và inventory objects cũ.

---

## 30. Checklist bảo mật search_path và schema public

### Thiết kế namespace

1. Biết mỗi bảng/function/type thuộc schema nào.
2. Dùng qualified names cho các object quan trọng.
3. Không coi schema public là mặc nhiên an toàn.
4. Phân biệt schema `public` với pseudo-role `PUBLIC`.
5. Xác định schema nào **trusted** dựa trên quyền CREATE thực tế.
6. Không đặt schema có untrusted CREATE vào path của privileged code.

### Vai trò và grants

7. Kiểm tra PostgreSQL version **và** ACL thật của từng database.
8. Audit `has_schema_privilege(...,'CREATE')` cho mọi runtime role.
9. Thu hồi CREATE chung trên public nếu policy yêu cầu.
10. Không dùng `REVOKE ALL` thiếu đánh giá USAGE.
11. Không dùng runtime role làm schema owner/superuser không cần thiết.
12. Kiểm soát direct grants, memberships và owner privileges.
13. Hạn chế EXECUTE trên privileged routines.
14. Chặn privileged routine bị PUBLIC EXECUTE ngoài ý muốn ngay tại CREATE transaction.

### Cấu hình search path

15. Kiểm tra `SHOW search_path` và `current_schemas(true)`.
16. Xác định `"$user"` có thể mở rộng thành schema nào.
17. Biết `pg_catalog` được tìm ngầm và vị trí explicit ảnh hưởng lookup.
18. Biết `pg_temp` đặc biệt cho relations/types, không functions/operators.
19. Đặt `pg_temp` cuối trong search path của SECURITY DEFINER.
20. Có function-level `SET search_path` tin cậy.
21. Không dùng caller-provided schema/path tùy ý trong privileged code.
22. Với dynamic SQL, quote đúng và kiểm tra allowlist.

### Application và vận hành

23. Không coi search_path là tenant authorization.
24. Xem RLS/owner trong SECURITY DEFINER call chains.
25. Kiểm tra connection pool reset hoặc transaction-local path.
26. Migrations dùng qualified target schema.
27. Review extension installation và owner.
28. Không mặc định nâng cấp server tự sửa ACL legacy.
29. Kiểm tra objects lạ đã tồn tại trước khi revoke.
30. Test shadowing bằng schema lab vô hại, không bằng quyền sản xuất của người khác.
31. Audit `pg_proc.prosecdef` và `proconfig`.
32. Kiểm tra cả privileges trên schema và function/table tương ứng.
33. Đo behavior dưới role runtime, không chỉ DBA.
34. Có kế hoạch hardening với staging/rollback/observability.
35. Ghi nhận security review khi thêm privileged routine hoặc schema mới.

---

## 31. Tổng kết

`search_path` là một cơ chế phân giải tên thuận tiện, nhưng không thuần túy là cấu hình thẩm mỹ. **Schema nằm trong đường tìm kiếm của code đặc quyền phải được coi là một phần của bề mặt tin cậy**, vì người được tạo đối tượng trong schema đó có thể ảnh hưởng đến những tên không qualified.

Những nguyên tắc cần nhớ:

- **Schema public** là namespace; **PUBLIC** trong GRANT/REVOKE là tập roles.
- **USAGE** và **CREATE** trên schema khác nhau. Được CREATE trong schema trên search path của privileged routine có thể nguy hiểm.
- PostgreSQL 15 đã cải thiện mặc định của schema public cho **database mới**, nhưng database đã nâng cấp/tùy chỉnh vẫn cần audit quyền thực tế.
- Khi `pg_catalog` không được liệt kê, PostgreSQL thường tìm nó ngầm trước; nếu liệt kê tường minh, vị trí trong path có ý nghĩa.
- `pg_temp` có ưu tiên đặc biệt đối với **bảng và kiểu dữ liệu** khi không được liệt kê. Đặt `pg_temp` cuối path trong routine đặc quyền.
- `SECURITY DEFINER` cần **function-level trusted search_path**, qualified names, owner ít quyền và EXECUTE grants tối thiểu.
- Overloading/function resolution, extension objects, dynamic SQL, migrations và connection pooling đều có thể làm vấn đề phức tạp hơn việc chỉ gọi một bảng.
- **Prepared statements không thay thế namespace hardening**, và `search_path` không thay authentication, authorization hay RLS.
- Hardening production bắt đầu bằng inventory/ACL audit, triển khai có kiểm soát và test dưới roles thật.

**Câu hỏi để tự đánh giá:** Với một function `SECURITY DEFINER` do owner quyền cao tạo, nếu caller được đổi `search_path` và một schema nằm trên path cho phép untrusted `CREATE`, function có chắc chắn gọi đúng bảng/helper mà tác giả dự định không? Nếu bạn chưa thể chứng minh điều đó bằng **schema qualification, function-level path và grants**, đây là một rủi ro cần xử lý trước khi đưa function vào production.

### Tài liệu PostgreSQL chính thức

- [Schemas — search_path và Schema Usage](https://www.postgresql.org/docs/current/ddl-schemas.html).
- [Schemas — The Public Schema](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PUBLIC).
- [Schemas — The Schema Search Path](https://www.postgresql.org/docs/current/ddl-schemas.html#DDL-SCHEMAS-PATH).
- [Function Security — SECURITY DEFINER](https://www.postgresql.org/docs/current/sql-createfunction.html#SQL-CREATEFUNCTION-SECURITY).
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html).
- [Function Type Resolution](https://www.postgresql.org/docs/current/typeconv-func.html).
- [Operator Type Resolution](https://www.postgresql.org/docs/current/typeconv-oper.html).
- [GRANT](https://www.postgresql.org/docs/current/sql-grant.html).
- [REVOKE](https://www.postgresql.org/docs/current/sql-revoke.html).
- [ALTER ROLE](https://www.postgresql.org/docs/current/sql-alterrole.html).
- [SET](https://www.postgresql.org/docs/current/sql-set.html).
- [SET LOCAL](https://www.postgresql.org/docs/current/sql-set.html).
- [Runtime Configuration — Client Connection Defaults (search_path)](https://www.postgresql.org/docs/current/runtime-config-client.html).
- [System Information Functions — current_schema/current_schemas](https://www.postgresql.org/docs/current/functions-info.html).
- [Privilege Inquiry Functions — has_schema_privilege](https://www.postgresql.org/docs/current/functions-info.html#FUNCTIONS-INFO-ACCESS-TABLE).
- [pg_namespace](https://www.postgresql.org/docs/current/catalog-pg-namespace.html).
- [pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html).
- [Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html).
