# Database, catalog, schema và không gian đặt tên

Khi mở một công cụ thực hành SQL, ta thường phải chọn **server**, **database**, đôi khi cả **schema** trước khi viết `SELECT`. Các tên này không phải những cách gọi thay thế hoàn toàn cho nhau. Chúng mô tả các tầng tổ chức và cách hệ quản trị cơ sở dữ liệu (DBMS) tìm đúng bảng, view hay đối tượng khác mà câu lệnh nhắc đến.

Bài này giúp bạn đọc đúng các tên như `practice.students`, `training_lab.practice.students`, biết câu lệnh đang chạy ở đâu, tránh tạo bảng nhầm chỗ và hiểu vì sao cùng một câu `SELECT * FROM students` có thể cho kết quả khác nhau giữa hai phiên làm việc.

## 1. Bắt đầu từ một tình huống thực hành

Giả sử máy chủ SQL phục vụ nhiều nhóm học tập. Hai nhóm đều có bảng tên `students`:

```text
Máy chủ DBMS
└── Database: training_lab
    ├── Schema: class_a
    │   └── Bảng: students
    └── Schema: class_b
        └── Bảng: students
```

Nếu gọi rõ `class_a.students` và `class_b.students`, DBMS biết chính xác bạn muốn đọc bảng nào. Nếu chỉ viết `students`, hệ quản trị sẽ áp dụng **quy tắc phân giải tên** của hệ đó: schema mặc định, đường dẫn tìm kiếm (search path), database đang chọn hoặc ngữ cảnh người dùng.

Đó là lý do cần phân biệt hai việc:

- **Tổ chức dữ liệu**: một bảng thuộc database/schema nào?
- **Phân giải tên**: khi SQL chỉ ghi tên ngắn, DBMS tra cứu đối tượng ở đâu?

## 2. Bốn khái niệm chính

### 2.1. Database

**Database (cơ sở dữ liệu)** là một đơn vị dữ liệu được DBMS quản lý. Tùy hệ quản trị, database có thể là ranh giới kết nối, quản trị, sao lưu, phân quyền hoặc tổ chức lưu trữ. Bên trong database thường có bảng, view, index, ràng buộc và các đối tượng phụ trợ.

Ví dụ: `training_lab` là database phục vụ thực hành, còn `sales_prod` là database của một ứng dụng bán hàng. Hai tên này nói về các môi trường dữ liệu khác nhau; việc một kết nối có thể truy vấn chéo hai database hay không phụ thuộc DBMS.

Không nên suy ra rằng mỗi schema là một database riêng, hoặc hai schema trong cùng database luôn được cách ly như hai database độc lập.

### 2.2. Catalog

Trong mô hình tên của **chuẩn SQL**, *catalog* là tầng chứa các schema. Vì vậy một tên đầy đủ thường được mô tả theo dạng:

```text
catalog.schema.object
   │       │      └── Bảng, view hoặc đối tượng SQL
   │       └───────── Nhóm tên logic
   └───────────────── Tầng chứa schema theo mô hình chuẩn
```

Trong các hệ quản trị cụ thể, từ *catalog* còn dùng để chỉ **kho siêu dữ liệu** (metadata): danh sách bảng, cột, kiểu dữ liệu, quyền truy cập… Điều này dễ gây nhầm lẫn:

- **Catalog trong tên ba phần** là một tầng định danh theo mô hình chuẩn SQL.
- **System catalog** là các bảng/view nội bộ ghi thông tin về đối tượng và cấu hình DBMS.
- Trong PostgreSQL, `pg_catalog` **là tên một schema hệ thống**, không phải tên database đang kết nối.

Vì vậy, không thể chỉ nhìn chữ `catalog` rồi mặc định rằng mọi DBMS đều có câu lệnh `CREATE CATALOG` hoặc cho phép truy vấn chéo database bằng ba phần tên.

### 2.3. Schema

**Schema** là một không gian tổ chức và đặt tên cho các đối tượng SQL. Bạn có thể dùng schema để tách đối tượng theo nhóm, chức năng hoặc quyền truy cập:

```text
training_lab
├── practice
│   ├── students
│   └── enrollments
└── reporting
    ├── students_summary
    └── enrollments_by_month
```

Trong một database có hỗ trợ nhiều schema, `practice.students` và `reporting.students` có thể là hai bảng khác nhau. Ngược lại, cùng một schema không thể tùy ý tạo nhiều đối tượng xung đột tên; quy tắc dùng chung tên còn tùy loại đối tượng và DBMS.

Từ *schema* cũng xuất hiện trong cụm **database schema** để nói về toàn bộ thiết kế cấu trúc dữ liệu: bảng, cột, quan hệ và ràng buộc. Đây là nghĩa rộng của từ, khác với **một schema có tên** như `practice` trong PostgreSQL hoặc SQL Server.

### 2.4. Namespace (không gian đặt tên)

**Namespace** là phạm vi mà trong đó một tên được xác định hoặc phải là duy nhất theo quy tắc cụ thể. Schema thường đóng vai trò namespace của bảng/view, nhưng không phải mọi loại đối tượng đều có phạm vi tên giống nhau.

Ví dụ, tên cột `id` chỉ có nghĩa trong ngữ cảnh bảng hoặc biểu thức truy vấn. Hai bảng khác nhau đều có thể có cột `id`. Tương tự, `class_a.students` và `class_b.students` có cùng phần tên cuối nhưng khác namespace.

**Tên đầy đủ (qualified name)** thêm thông tin về namespace, còn **tên ngắn (unqualified name)** để DBMS dựa vào ngữ cảnh mà tìm đối tượng.

## 3. Các DBMS tổ chức tên khác nhau

| Hệ quản trị | Tổ chức thường gặp | Ví dụ tham chiếu bảng | Điểm cần nhớ |
| --- | --- | --- | --- |
| **PostgreSQL** | Server → database → schema → object | `practice.students` | Kết nối tới một database cụ thể; schema `public` và `pg_catalog` có vai trò riêng. Không thể dùng tên ba phần để truy vấn trực tiếp một database khác. |
| **MySQL** | Server → database/schema → object | `training_lab.students` | Từ khóa `DATABASE` và `SCHEMA` gần như đồng nghĩa trong thao tác tạo/chọn vùng chứa bảng; không có tầng schema độc lập bên trong một database như PostgreSQL. |
| **SQL Server** | Server → database → schema → object | `TrainingLab.practice.students` | Một database có thể có nhiều schema; `dbo` là schema phổ biến. Có thể gặp tên bốn phần khi dùng linked server. |
| **Oracle Database** | Database → schema gắn với người dùng → object | `PRACTICE.STUDENTS` | Schema gắn với chủ sở hữu là database user; cách tạo/quản lý khác PostgreSQL. |
| **SQLite** | Kết nối → `main`, `temp` hoặc database được `ATTACH` → object | `main.students` | Không có cơ chế schema nhiều tầng như PostgreSQL; tiền tố trước dấu chấm thường chọn database được gắn vào kết nối. |

Các cách viết trong bảng là **ví dụ theo từng hệ**, không phải cú pháp dùng chung trên mọi DBMS. Đặc biệt, `database.schema.table` của SQL Server không có cùng ý nghĩa với cách PostgreSQL phân giải `schema.table`.

### Ví dụ cùng một ý tưởng, khác cú pháp

Trong **MySQL**:

```sql
CREATE DATABASE IF NOT EXISTS training_lab;
USE training_lab;

CREATE TABLE students (
    student_id INT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL
);

SELECT * FROM training_lab.students;
```

`USE training_lab` đổi database mặc định của kết nối hiện tại. `CREATE SCHEMA training_lab` trong MySQL về cơ bản tương đương `CREATE DATABASE training_lab`.

Trong **SQL Server**, giả sử database `TrainingLab` đã tồn tại và bạn có quyền tương ứng:

```sql
USE TrainingLab;
GO

CREATE SCHEMA practice;
GO

CREATE TABLE practice.students (
    student_id INT IDENTITY(1,1) PRIMARY KEY,
    full_name NVARCHAR(100) NOT NULL
);

SELECT * FROM TrainingLab.practice.students;
```

`GO` là ký hiệu kết thúc batch được một số công cụ SQL Server hỗ trợ, **không phải câu lệnh SQL chuẩn**. Trong một ứng dụng gửi câu lệnh qua driver, cách gửi batch có thể khác.

Trong **SQLite**, có thể gắn thêm tệp database vào kết nối:

```sql
ATTACH DATABASE 'lab.sqlite' AS lab;
CREATE TABLE lab.students (student_id INTEGER PRIMARY KEY, full_name TEXT);
SELECT * FROM lab.students;
```

`lab` ở đây là tên database được gắn bằng `ATTACH`, không phải một schema PostgreSQL. Chạy ví dụ này trong thư mục thực hành vì nó tạo hoặc mở tệp `lab.sqlite`.

## 4. Thực hành có hướng dẫn với PostgreSQL

Các lệnh ở phần này dành cho **PostgreSQL**. Hãy dùng một database thử nghiệm đã được cấp quyền `CONNECT` và `CREATE`, chẳng hạn `training_lab`. Bạn có thể thao tác từ `psql`, pgAdmin hoặc công cụ SQL khác kết nối đến đúng database. Đừng chạy DDL minh họa trên database sản xuất.

### Bước 1: Xác nhận bạn đang ở đâu

```sql
SELECT
    current_database() AS database_dang_dung,
    current_schema()   AS schema_hien_tai,
    current_user       AS tai_khoan_dang_dung;

SHOW search_path;
```

- `current_database()` cho biết database của kết nối hiện tại.
- `current_schema()` trả về schema hiện hành dùng cho việc tạo đối tượng không ghi rõ schema; giá trị phụ thuộc `search_path` và schema hiện có.
- `current_user` giúp xác định vai trò đang thực thi câu lệnh.
- `SHOW search_path` cho biết đường dẫn mà PostgreSQL sẽ dùng khi phân giải nhiều tên đối tượng không có tiền tố schema.

Giá trị `"$user", public` là một cấu hình `search_path` thường gặp; nó không có nghĩa chắc chắn mọi đối tượng sẽ được tìm trong `public`. `$user` được diễn giải theo tên người dùng nếu schema tương ứng tồn tại và dùng được.

### Bước 2: Tạo schema và bảng bằng tên đầy đủ

```sql
CREATE SCHEMA IF NOT EXISTS practice;

CREATE TABLE practice.students (
    student_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name  TEXT NOT NULL,
    email      TEXT UNIQUE
);

INSERT INTO practice.students (full_name, email)
VALUES
    ('An Nguyen', 'an@example.test'),
    ('Binh Tran', 'binh@example.test');

SELECT student_id, full_name, email
FROM practice.students
ORDER BY student_id;
```

`practice.students` luôn chỉ định bảng `students` trong schema `practice` của **database hiện đang kết nối**. Việc dùng tên đầy đủ làm vị trí tạo bảng và vị trí đọc bảng rõ ràng hơn.

Nếu chạy lại nguyên khối trên môi trường đã tạo bảng, `CREATE TABLE` có thể báo đối tượng đã tồn tại. Đối với bài thực hành, hãy chạy một lần trên database thử nghiệm mới hoặc dùng tên/schema mới.

### Bước 3: Xem danh sách bảng qua metadata

```sql
SELECT table_catalog, table_schema, table_name, table_type
FROM information_schema.tables
WHERE table_schema = 'practice'
ORDER BY table_name;
```

`information_schema` là tập các view metadata dựa trên chuẩn SQL được nhiều DBMS hỗ trợ, dù mức độ đầy đủ và khả năng nhìn thấy đối tượng khác nhau. Trong PostgreSQL, truy vấn trên giúp quan sát:

- `table_catalog`: tên database chứa bảng ở kết nối hiện tại;
- `table_schema`: schema sở hữu bảng, ở đây là `practice`;
- `table_name`: tên bảng, ở đây là `students`.

Danh sách metadata có thể chịu ảnh hưởng của quyền truy cập. Không thấy một bảng trong `information_schema` chưa đủ để kết luận bảng không tồn tại.

PostgreSQL còn có các catalog nội bộ như `pg_catalog.pg_class` và `pg_catalog.pg_namespace`. Chúng phục vụ các thông tin đặc thù PostgreSQL; khi cần ví dụ SQL dễ di chuyển giữa các hệ, nên ưu tiên `information_schema` ở những phần mà DBMS có hỗ trợ.

## 5. Tên ngắn được tìm như thế nào?

Xét hai câu lệnh PostgreSQL:

```sql
SELECT * FROM practice.students; -- ghi rõ schema
SELECT * FROM students;          -- tên ngắn, cần phân giải
```

Với câu đầu tiên, tên `practice.students` xác định cụ thể bảng mong muốn. Với câu thứ hai, PostgreSQL dùng `search_path` để tìm đối tượng tên `students` theo thứ tự thích hợp. Nếu không có đối tượng phù hợp trong những schema có thể tra cứu, câu lệnh có thể báo lỗi `relation "students" does not exist`.

Bạn có thể đặt `search_path` cho **phiên kết nối hiện tại**:

```sql
SET search_path TO practice, public;

SELECT current_schema();
SELECT * FROM students;

RESET search_path;
```

Nếu schema `practice` tồn tại và có thể sử dụng, `students` sẽ được tìm tại đó trước `public`. `RESET search_path` trả cài đặt của phiên về giá trị mặc định đã được cấu hình, không nhất thiết luôn là `public`.

PostgreSQL còn có quy tắc tìm schema hệ thống `pg_catalog` và schema tạm; vì vậy không nên diễn giải `search_path` thành một phép nối chuỗi đơn giản. Đặc biệt khi viết SQL chạy trong nhiều tài khoản hoặc nhiều schema, dùng `schema.table` thường giúp câu lệnh dễ dự đoán hơn.

Trong **SQL Server**, tên ngắn thường được phân giải dựa vào schema mặc định của người dùng và quy tắc dự phòng của SQL Server, thường liên quan đến `dbo`. Trong **MySQL**, `USE training_lab` thay đổi database mặc định cho các tên bảng không ghi tiền tố. Đừng đem nguyên quy tắc `search_path` của PostgreSQL áp dụng cho hai hệ này.

## 6. Hai schema có thể chứa hai bảng cùng tên

Ví dụ sau dùng riêng PostgreSQL. Chạy một lần trong database thử nghiệm và có quyền tạo schema:

```sql
CREATE SCHEMA lab_a;
CREATE SCHEMA lab_b;

CREATE TABLE lab_a.items (
    id    INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE TABLE lab_b.items (
    id    INTEGER PRIMARY KEY,
    label TEXT NOT NULL
);

INSERT INTO lab_a.items (id, label) VALUES (1, 'Du lieu A');
INSERT INTO lab_b.items (id, label) VALUES (1, 'Du lieu B');

SELECT * FROM lab_a.items; -- id = 1, label = 'Du lieu A'
SELECT * FROM lab_b.items; -- id = 1, label = 'Du lieu B'
```

Bây giờ đổi thứ tự tìm kiếm:

```sql
SET search_path TO lab_b, lab_a;
SELECT * FROM items;       -- đọc lab_b.items

SET search_path TO lab_a, lab_b;
SELECT * FROM items;       -- đọc lab_a.items

RESET search_path;
```

Hai bảng hoàn toàn độc lập dù tên ngắn cùng là `items`. Kết quả thay đổi **do ngữ cảnh phân giải tên**, không phải vì dữ liệu trong bảng tự thay đổi. Thí nghiệm cũng cho thấy một câu SQL không có tiền tố schema có thể phụ thuộc vào cấu hình phiên làm việc.

## 7. Quy tắc viết tên: chữ hoa, dấu nháy và tên đầy đủ

Tên bảng/cột/schema được gọi là **identifier**; chuỗi dữ liệu được gọi là **string literal**. Hai thứ này dùng dấu nháy với ý nghĩa khác nhau:

```sql
-- PostgreSQL
SELECT full_name FROM practice.students WHERE full_name = 'An Nguyen';
--     ^^^^^^^^^ cột        ^^^^^^^^^^^^^^^ bảng           ^^^^^^^^^^^ dữ liệu
```

PostgreSQL mặc định chuyển **identifier không đặt trong dấu nháy kép** thành chữ thường. Ví dụ `Students`, `STUDENTS` và `students` đều được hiểu là `students` nếu không đặt trong dấu nháy kép. Tuy nhiên:

```sql
CREATE TABLE practice."Students" (id INTEGER);

SELECT * FROM practice."Students"; -- đúng tên có chữ S hoa
SELECT * FROM practice.students;   -- là một tên khác
```

Quy tắc chữ hoa/chữ thường khác nhau giữa DBMS: MySQL còn phụ thuộc hệ điều hành và cấu hình tên bảng, SQL Server thường phụ thuộc collation; MySQL thường dùng backtick (`` `name` ``), SQL Server có thể dùng `[name]`, trong khi tên được quote theo chuẩn SQL dùng dấu nháy kép. **Không nên giả định rằng kiểu quote hoặc quy tắc chữ hoa ở một hệ sẽ hoạt động y hệt ở hệ khác.**

Trong bài thực hành, cách dễ đọc và ít rắc rối là chọn tên chữ thường dạng `snake_case`, ví dụ `practice.enrollment_records`; tránh khoảng trắng và các từ khóa SQL như `order`, `user`, `select` nếu không thật sự cần.

## 8. Schema liên quan gì đến phân quyền?

Schema không chỉ hỗ trợ đặt tên; nó còn là một phạm vi quản lý quyền. Với PostgreSQL, một tài khoản có thể truy cập database nhưng vẫn không có quyền sử dụng một schema hoặc đọc bảng bên trong.

Ví dụ minh họa dành cho người quản trị/chủ sở hữu đối tượng, giả sử role `learner` đã tồn tại:

```sql
GRANT USAGE ON SCHEMA practice TO learner;
GRANT SELECT ON ALL TABLES IN SCHEMA practice TO learner;
```

Hai lệnh có mục đích khác nhau:

1. `USAGE ON SCHEMA` cho phép role phân giải và tham chiếu đến đối tượng trong schema theo điều kiện quyền liên quan.
2. `SELECT ON ALL TABLES IN SCHEMA` cấp quyền đọc các bảng/view phù hợp **đang tồn tại** trong schema ở thời điểm cấp quyền; không tự cấp quyền cho tất cả bảng sẽ tạo trong tương lai.

Quyền kết nối database (`CONNECT`), quyền tạo đối tượng (`CREATE`), quyền trên schema và quyền trên bảng là những lớp cần xem xét riêng. Việc có thể nhìn thấy tên bảng không đồng nghĩa được phép `SELECT`, `INSERT` hay `DROP` bảng đó.

Trong ứng dụng thực tế, tránh để tên đối tượng quan trọng phụ thuộc vào `search_path` có thể bị chỉnh bởi tài khoản không đáng tin cậy. Khi truy cập đối tượng qua nhiều schema hoặc dùng tài khoản có quyền cao, hãy khai báo schema rõ ràng và chỉ cấp quyền cần thiết.

## 9. Lỗi thường gặp trong môi trường thực hành

| Triệu chứng | Nguyên nhân có thể gặp | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| `relation "students" does not exist` trên PostgreSQL | Đang ở sai database/schema; `search_path` không chứa schema cần tìm; tên được quote khác chữ hoa | Kiểm tra `current_database()`, `SHOW search_path`, thử `practice.students` và tra metadata |
| Có bảng `students` nhưng kết quả `SELECT` khác kỳ vọng | Hai schema có bảng cùng tên, tên ngắn được phân giải sang bảng khác | Ghi rõ `schema.students`; kiểm tra schema mặc định hoặc thứ tự `search_path` |
| `permission denied for schema practice` | Role thiếu quyền sử dụng schema | Kiểm tra role đang đăng nhập và quyền `USAGE` trên schema |
| Truy cập được schema nhưng không đọc được bảng | Thiếu quyền trên bảng | Kiểm tra `SELECT` trên đối tượng cụ thể, không chỉ `USAGE` trên schema |
| Truy vấn `other_db.practice.students` không đọc được database khác trong PostgreSQL | PostgreSQL không hỗ trợ kiểu tham chiếu chéo database trực tiếp này | Kết nối đúng database; nếu thật sự cần dữ liệu từ database khác, nghiên cứu cơ chế như `postgres_fdw` và phân quyền phù hợp |
| `USE training_lab` báo lỗi trong PostgreSQL | Đang dùng lệnh chuyển database của MySQL/SQL Server | Tạo kết nối mới tới database mong muốn; trong `psql` có lệnh riêng `\connect training_lab` (lệnh client, không phải SQL) |
| `CREATE SCHEMA` không hoạt động trong MySQL như ví dụ PostgreSQL | MySQL coi database và schema là hai tên gần như đồng nghĩa | Dùng `CREATE DATABASE`/`USE` và tên `database.table` |

## 10. Bài tự luyện

Hãy làm trong PostgreSQL với một database thực hành. Không cần dùng dữ liệu thật.

**Bài 1 — Xác định ngữ cảnh.** Chạy `SELECT current_database(), current_schema(), current_user;` rồi `SHOW search_path;`. Ghi lại đâu là tên database, đâu là tên schema và đâu là cấu hình tìm kiếm.

**Bài 2 — Đọc tên nhiều phần.** Với `training_lab.practice.students`, xác định vai trò dự kiến của từng phần nếu đó là tên theo mô hình `database.schema.table` của SQL Server. Giải thích vì sao không thể mặc định dùng chính cú pháp đó để truy vấn database `training_lab` từ một database PostgreSQL khác.

**Bài 3 — Kiểm chứng namespace.** Thực hiện ví dụ `lab_a.items` và `lab_b.items` ở mục 6. Trước khi chạy từng `SELECT * FROM items`, dự đoán bảng nào sẽ được đọc. Sau đó chạy cả hai câu có tên đầy đủ để so sánh.

**Bài 4 — Tìm bảng bằng metadata.** Dùng `information_schema.tables` để liệt kê các bảng trong schema `lab_a`; thay `lab_a` bằng `lab_b`. Đối chiếu `table_catalog`, `table_schema` và `table_name`.

**Bài 5 — Giải thích lỗi.** Một người bạn thấy `practice.students` trong công cụ quản lý database nhưng `SELECT * FROM students` báo không tồn tại. Nêu ít nhất ba điều cần kiểm tra trước khi kết luận bảng đã bị xóa.

### Gợi ý đối chiếu

- **Bài 2:** `training_lab` là database, `practice` là schema, `students` là bảng trong cách gọi SQL Server. PostgreSQL cần kết nối tới đúng database; tên ba phần không tạo quyền truy vấn chéo database.
- **Bài 3:** Khi `search_path` bắt đầu bằng `lab_b`, tên ngắn chọn `lab_b.items`; khi bắt đầu bằng `lab_a`, nó chọn `lab_a.items`. Tên đầy đủ không bị đổi đích vì thứ tự này.
- **Bài 4:** Hai dòng có thể cùng `table_name = 'items'` nhưng khác `table_schema`; `table_catalog` vẫn là database thử nghiệm hiện tại.
- **Bài 5:** Kiểm tra database đang kết nối, schema/search path, kiểu viết hoa và dấu nháy của identifier, cũng như quyền truy cập/hiển thị metadata.

Khi bước vào một môi trường SQL mới, hãy tập thói quen xác định **DBMS đang dùng → database đang kết nối → schema hoặc database mặc định → quy tắc phân giải tên** trước khi tạo hay thay đổi dữ liệu. Chỉ riêng thói quen này đã tránh được nhiều lỗi nhầm bảng, nhầm môi trường và nhầm quyền trong quá trình thực hành.
