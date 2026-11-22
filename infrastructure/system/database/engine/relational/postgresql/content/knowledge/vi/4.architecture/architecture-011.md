# Phân biệt dữ liệu bền vững, trạng thái phiên và dữ liệu tạm trong PostgreSQL

## 1. Tại sao cần phân biệt ba loại trạng thái?

Trong PostgreSQL, không phải mọi thứ được tạo ra hoặc thay đổi bởi một câu SQL đều có cùng **vòng đời**. Có dữ liệu phải sống qua việc ứng dụng ngắt kết nối hoặc máy chủ khởi động lại. Có trạng thái chỉ tồn tại trong một kết nối. Lại có các bảng tạm hoặc tệp tạm phục vụ một công việc ngắn hạn, và một số dữ liệu được tạo trong giao dịch còn có thể bị hoàn tác khi `ROLLBACK`.

Ví dụ, một ứng dụng xử lý đơn hàng thực hiện:

```sql
INSERT INTO orders (order_id, amount)
VALUES (1001, 250000.00);
```

Một phiên làm việc khác thực hiện:

```sql
SET statement_timeout = '5s';
```

Và một báo cáo tạo:

```sql
CREATE TEMP TABLE selected_orders AS
SELECT * FROM orders WHERE amount >= 100000;
```

Ba thao tác này trông đều giống hoạt động SQL, nhưng tác dụng rất khác:

- `orders` là bảng thông thường; thay đổi **đã commit** của nó được thiết kế để tồn tại sau khi client ngắt kết nối và sau một lần restart PostgreSQL bình thường.
- `statement_timeout` đặt ở mức phiên chỉ ảnh hưởng tới **kết nối hiện tại** và không trở thành cấu hình vĩnh viễn của database.
- `selected_orders` là **temporary table**, chỉ thuộc phiên đang tạo nó và thường biến mất khi phiên đó kết thúc.

Nếu nhầm lẫn các vòng đời này, hệ thống có thể phát sinh những lỗi khó tìm: một batch tưởng đã lưu báo cáo nhưng bảng bị mất khi connection pool đóng kết nối; một request thừa hưởng `search_path` của request trước; hoặc một quy trình dùng bảng `UNLOGGED` cho dữ liệu nghiệp vụ rồi mất dữ liệu sau sự cố.

> **Nguyên tắc nền tảng:** trong PostgreSQL, cần hỏi riêng **đối tượng tồn tại bao lâu**, **ai có thể nhìn thấy nó**, **khi nào thay đổi được commit/rollback** và **nó có được phục hồi sau sự cố không**. Bốn câu hỏi này liên quan nhưng không đồng nghĩa.

## 2. Bản đồ khái niệm: database, session, transaction và temporary object

PostgreSQL là hệ quản trị theo kiến trúc client/server. Một ứng dụng hay `psql` mở kết nối đến server để gửi truy vấn. Mỗi kết nối thông thường được phục vụ bởi một tiến trình backend chuyên biệt trong PostgreSQL, với trạng thái riêng của phiên.

```text
                 PostgreSQL Server
        +------------------------------------+
        |                                    |
Client A ---> Backend / Session A            |
        |       |                            |
        |       +-- GUC: search_path         |
        |       +-- Prepared statements      |
        |       +-- Temporary table A        |
        |       +-- Transaction hiện tại     |
        |                                    |
Client B ---> Backend / Session B            |
        |       |                            |
        |       +-- GUC: statement_timeout   |
        |       +-- Temporary table B        |
        |       +-- Transaction hiện tại     |
        |                                    |
        |           Shared database          |
        |       +-------------------------+  |
        |       | Permanent tables        |  |
        |       | Indexes, catalog        |  |
        |       | WAL / durable storage   |  |
        |       +-------------------------+  |
        +------------------------------------+
```

Bốn khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa | Vòng đời thường gặp |
| --- | --- | --- |
| **Database object thông thường** | Bảng, index, view và dữ liệu có tính lâu dài | Cho đến khi bị thay đổi/xóa bằng SQL hoặc thao tác quản trị |
| **Session** | Một kết nối làm việc với PostgreSQL cùng trạng thái riêng | Từ khi kết nối được mở đến khi kết nối đóng/mất |
| **Transaction** | Nhóm thao tác cần tính nguyên tử và cô lập | Từ `BEGIN` đến `COMMIT`/`ROLLBACK`, hoặc một statement khi autocommit |
| **Temporary object/data** | Bảng tạm hoặc dữ liệu trung gian phục vụ phiên/công việc | Phụ thuộc loại: thường theo session; có thể ngắn hơn theo transaction hoặc statement |

**Session không phải transaction.** Một session có thể chạy nhiều transaction nối tiếp. Ngược lại, một transaction chỉ diễn ra trên kết nối đang thực thi nó; ứng dụng không thể mở transaction ở connection A rồi mong các câu SQL gửi qua connection B tự động thuộc transaction đó.

### 2.1. Vòng đời lồng nhau

```text
Session A (mở kết nối)
│
├── SET statement_timeout = '5s'
│   └── Có hiệu lực trong session A cho đến RESET/SET khác/đóng kết nối
│
├── Transaction 1: BEGIN ... COMMIT
│   └── Những thay đổi đã commit trở thành thay đổi database
│
├── Transaction 2: BEGIN ... ROLLBACK
│   └── Những thay đổi trong transaction này bị hoàn tác
│
├── Temporary table session_report
│   └── Thường vẫn tồn tại qua nhiều transaction trong session A
│
└── Đóng connection
    ├── Trạng thái session biến mất
    └── Temporary table của session bị loại bỏ

Database
└── Dữ liệu bảng thường đã commit vẫn ở đó
    qua nhiều session và các lần restart bình thường
```

Từ sơ đồ này có thể thấy **`COMMIT` không đồng nghĩa với đóng session**, và **đóng session không đồng nghĩa với xóa dữ liệu thông thường đã commit**.

## 3. Dữ liệu bền vững: bảng thông thường và giao dịch đã commit

### 3.1. Permanent table là mặc định

Trong PostgreSQL, một bảng tạo bằng `CREATE TABLE` mà không dùng `TEMP` hoặc `UNLOGGED` là **bảng thường** (permanent table).

```sql
CREATE SCHEMA IF NOT EXISTS lifecycle_lab;

CREATE TABLE IF NOT EXISTS lifecycle_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Dữ liệu trong bảng được duy trì như một phần của database. Nếu một transaction ghi và `COMMIT` thành công, phiên khác được phép truy cập có thể đọc thay đổi đó theo quy tắc **MVCC và mức cô lập giao dịch**.

Ví dụ:

```sql
BEGIN;

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES
    (1001, 'Nguyễn An', 250000.00);

COMMIT;
```

Sau khi client đóng kết nối, hàng `order_id = 1001` **không bị xóa chỉ vì session kết thúc**.

Trong một phiên khác:

```sql
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE order_id = 1001;
```

Phiên B có thể thấy hàng đã commit nếu có quyền `SELECT` và không đang bị ràng buộc bởi một snapshot cũ theo mức cô lập.

### 3.2. Thay đổi trước commit chưa phải dữ liệu đã commit

Giả sử session A:

```sql
BEGIN;

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES (1002, 'Trần Bình', 160000.00);

-- Chưa COMMIT.
```

Trong khi đó session B thực hiện:

```sql
SELECT * FROM lifecycle_lab.orders WHERE order_id = 1002;
```

Ở mức cô lập mặc định `READ COMMITTED`, B **chưa nhìn thấy** hàng mới chưa commit của A. Nếu A chạy:

```sql
COMMIT;
```

một câu `SELECT` mới ở B có thể thấy hàng 1002. Nếu A chạy `ROLLBACK` thay vì `COMMIT` thì hàng đó không trở thành dữ liệu đã commit.

Sự kiện này cho thấy cần phân biệt:

- **Tồn tại trong transaction hiện tại**: phiên tạo hàng có thể đọc thay đổi của chính nó.
- **Đã commit và có thể quan sát từ phiên khác**: phụ thuộc commit, quyền và snapshot.
- **Bền vững trước sự cố**: liên quan thêm đến WAL và cấu hình durability.

### 3.3. WAL và cơ chế bền vững

PostgreSQL sử dụng **Write-Ahead Log (WAL)** để phục hồi những thay đổi cần thiết khi gặp sự cố. Khái quát:

```text
INSERT/UPDATE/DELETE
        |
        v
Thay đổi trong bộ nhớ đệm và các thông tin WAL cần thiết
        |
        v
COMMIT: xác nhận theo chính sách ghi WAL hiện hành
        |
        v
Khi cần: ghi trang dữ liệu xuống đĩa
        |
        v
Crash recovery sử dụng WAL để phục hồi nhất quán
```

Trong cấu hình durability bình thường, PostgreSQL được thiết kế để giữ các thay đổi đã commit qua một lần crash theo những bảo đảm của WAL, hệ điều hành và thiết bị lưu trữ.

**Không nên giải thích “đã commit thì chắc chắn không bao giờ mất dữ liệu trong mọi hoàn cảnh”.** Có các ngoại lệ và rủi ro như:

- `synchronous_commit = off` cho phép xác nhận commit trước khi một số thông tin WAL được flush bền vững, nên có thể mất một số giao dịch vừa được xác nhận nếu server crash.
- Tắt `fsync` hoặc dùng hệ thống lưu trữ không bảo đảm flush có thể làm suy giảm durability.
- Hỏng thiết bị, lỗi phần cứng hoặc thao tác quản trị không đúng vẫn có thể làm mất dữ liệu.
- Replication và backup có chính sách bền vững và khôi phục riêng; WAL không thay thế backup.

Vì vậy, **permanent** nói về loại bảng và vòng đời dự kiến; **durable** là thuộc tính giao dịch và lưu trữ dưới một cấu hình cụ thể.

### 3.4. Đóng phiên hoặc restart có tác dụng gì?

Nếu bảng `lifecycle_lab.orders` đã tồn tại và hàng 1001 đã commit:

| Sự kiện | Bảng thường và dữ liệu đã commit |
| --- | --- |
| Đóng `psql` hoặc kết nối ứng dụng | Tiếp tục tồn tại |
| Mở một session mới | Có thể đọc theo quyền và snapshot |
| `COMMIT` ở session khác | Không xóa bảng |
| `ROLLBACK` của giao dịch chỉ đọc | Không làm mất dữ liệu đã commit trước đó |
| Restart PostgreSQL bình thường | Dữ liệu vẫn tồn tại |
| Crash/recovery | Được phục hồi theo WAL và chính sách durability |
| `DROP TABLE` đã commit | Đối tượng bị xóa theo hành vi SQL |
| `DELETE` đã commit | Hàng bị xóa theo điều kiện và quy tắc MVCC |

“Bền vững” không có nghĩa “không thể xóa”; câu SQL hợp lệ có quyền vẫn có thể xóa bảng hoặc dữ liệu.

## 4. Trạng thái phiên (session state) là gì?

Một **session** là ngữ cảnh làm việc gắn với một kết nối PostgreSQL. Nó chứa các lựa chọn và tài nguyên riêng mà server cần giữ trong lúc connection còn hoạt động.

Ví dụ session state có thể gồm:

- Giá trị cấu hình đặt bằng `SET` (GUC, tức *Grand Unified Configuration* settings).
- `search_path` và các lựa chọn về định dạng ngày giờ, timezone, timeout.
- Prepared statements tạo bằng SQL `PREPARE`.
- Những cursor/portal còn hiệu lực theo vòng đời tương ứng.
- Session-level advisory locks.
- Đăng ký `LISTEN` cho channel thông báo.
- Bảng tạm thuộc phiên đó.
- Transaction hiện tại, savepoint và những thay đổi chưa commit.

### 4.1. Xác định phiên bằng backend PID

Trong hai cửa sổ `psql` riêng:

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    current_database() AS db_name,
    current_user AS db_user;
```

Mỗi session kết nối trực tiếp thông thường có **backend PID** khác nhau. Khi đóng rồi mở lại, connection mới có một backend mới (mặc dù PID của hệ điều hành có thể được tái sử dụng theo thời gian).

Không dùng một PID như khóa định danh vĩnh viễn của người dùng. Nó chỉ phục vụ quan sát một backend trong khoảng hoạt động hiện tại.

### 4.2. Session tồn tại bao lâu trong ứng dụng?

Trong `psql` tương tác, session thường kéo dài từ lúc kết nối đến khi `\q` hoặc mất kết nối.

Trong ứng dụng Java sử dụng connection pool:

```text
HTTP request A -> mượn Connection #5
               -> SET search_path...
               -> trả Connection #5 về pool

HTTP request B -> mượn Connection #5
               -> có thể gặp session state còn sót
```

Trả một connection **về pool** không nhất thiết là **đóng session trên server**. Nếu pool tái sử dụng cùng connection, những thiết lập ở mức session có thể tiếp tục tồn tại và ảnh hưởng request sau.

Một số pool hoặc proxy có chính sách reset; cần hiểu cấu hình thực tế, không tự giả định mọi lần mượn connection đều là một session PostgreSQL hoàn toàn mới.

## 5. Ví dụ rõ nhất của session state: `SET` và `RESET`

Giả sử kết nối A:

```sql
SHOW statement_timeout;

SET statement_timeout = '5s';

SHOW statement_timeout;
```

`statement_timeout` là cấu hình giới hạn thời gian thực thi câu lệnh trong phiên. Sau `SET`, những câu lệnh tiếp theo của session A chịu giá trị này cho đến khi có `SET` khác, `RESET` hoặc phiên kết thúc, có xét đến transaction rollback.

Ở kết nối B:

```sql
SHOW statement_timeout;
```

B **không tự nhận** giá trị do A đặt. Nó dùng cấu hình của riêng B theo các mức mặc định server/database/role/session.

### 5.1. `SET` ở mức phiên

```sql
SET search_path TO lifecycle_lab, public;
SET statement_timeout = '5s';
SET TIME ZONE 'Asia/Ho_Chi_Minh';
```

Các thay đổi trên thường áp dụng từ lúc được thiết lập cho đến khi được thay thế/reset hoặc session kết thúc. Nếu `SET` được thực hiện trong một transaction rồi transaction đó rollback, tác động của `SET` cũng có thể bị hoàn tác theo ngữ nghĩa giao dịch của PostgreSQL.

Kiểm tra:

```sql
SHOW search_path;
SHOW statement_timeout;
SHOW TimeZone;
```

Phân biệt `SET` với việc sửa cấu hình mặc định bằng `ALTER ROLE ... SET` hoặc `ALTER DATABASE ... SET`: các lệnh DDL đó thay đổi **giá trị mặc định cho các phiên thích hợp**, không chỉ trạng thái tạm thời của connection đang sử dụng.

### 5.2. `SET LOCAL` chỉ trong transaction hiện tại

```sql
BEGIN;

SET LOCAL statement_timeout = '2s';

SHOW statement_timeout;

SELECT COUNT(*)
FROM lifecycle_lab.orders;

COMMIT;

SHOW statement_timeout;
```

Trong transaction, `statement_timeout` được đặt cục bộ thành `2s`. Sau `COMMIT`, tác động của `SET LOCAL` kết thúc, phiên quay về giá trị trước đó tương ứng.

**Không dùng `SET LOCAL` bên ngoài một transaction block rồi kỳ vọng nó bảo vệ các câu SQL sau.** Với PostgreSQL, `SET LOCAL` cần transaction phù hợp và có thể được cảnh báo/không tạo hiệu lực có ích nếu đặt ngoài transaction.

### 5.3. `RESET` và khôi phục mặc định

```sql
SET statement_timeout = '5s';

RESET statement_timeout;

SHOW statement_timeout;
```

`RESET` đưa tham số về giá trị mặc định áp dụng cho session (theo nguồn cấu hình và mức ưu tiên tương ứng), không nhất thiết luôn bằng 0.

Có thể dùng:

```sql
RESET ALL;
```

nhưng lệnh này chỉ reset các cấu hình thích hợp; nó **không đồng nghĩa** với việc xóa mọi temporary table, prepared statement hoặc tài nguyên session khác.

### 5.4. `SET ROLE` cũng là trạng thái phiên

Trong môi trường có role phù hợp, có thể thay đổi role hoạt động:

```sql
SET ROLE reporting_role;

SELECT current_user, session_user;

RESET ROLE;
```

`reporting_role` là tên ví dụ; cần role tồn tại và tài khoản có quyền chuyển role tương ứng. Thay role không tạo một kết nối mới. Quên hoàn nguyên có thể khiến các câu lệnh kế tiếp trong cùng connection sử dụng ngữ cảnh quyền khác mong đợi.

## 6. Transaction state: ngắn hơn session nhưng không đồng nghĩa dữ liệu tạm

**Transaction** là đơn vị nguyên tử với ranh giới `BEGIN`, `COMMIT` và `ROLLBACK`. Transaction state bao gồm snapshot đang dùng, các thay đổi chưa commit, khóa, savepoint và lựa chọn `SET LOCAL`.

```sql
BEGIN;

UPDATE lifecycle_lab.orders
SET amount = amount + 10000
WHERE order_id = 1001;

-- Chỉ transaction hiện tại đã biết thay đổi chưa commit của nó.

ROLLBACK;
```

Sau rollback, giá trị `amount` đã commit trước đó không bị cộng thêm 10000.

### 6.1. Cùng một session có thể có nhiều transaction

```text
Connection A
   ├── BEGIN (Transaction 1)
   ├── UPDATE ...
   ├── COMMIT
   ├── SELECT ...
   ├── BEGIN (Transaction 2)
   ├── SET LOCAL ...
   ├── SELECT ...
   ├── ROLLBACK
   └── Connection vẫn mở
```

**Kết thúc transaction không đóng session.** Đây là lý do các biến `SET` thông thường hoặc temporary table `ON COMMIT PRESERVE ROWS` có thể tiếp tục tồn tại sau `COMMIT`.

### 6.2. `SAVEPOINT` quản lý rollback một phần

```sql
BEGIN;

UPDATE lifecycle_lab.orders
SET amount = amount + 1000
WHERE order_id = 1001;

SAVEPOINT before_optional_step;

UPDATE lifecycle_lab.orders
SET amount = amount + 5000
WHERE order_id = 1001;

ROLLBACK TO SAVEPOINT before_optional_step;

COMMIT;
```

Kết quả là phần cập nhật sau savepoint bị hoàn tác, còn phần trước savepoint có thể được commit. Savepoint thuộc **transaction**, không tồn tại sau khi transaction kết thúc.

### 6.3. Mức cô lập quyết định khả năng nhìn thấy thay đổi

Ở `READ COMMITTED`, mỗi câu lệnh thông thường có snapshot mới cho những dữ liệu đã commit trước thời điểm statement tương ứng. Ở `REPEATABLE READ`, transaction giữ cách nhìn dữ liệu nhất quán theo snapshot của transaction, trong giới hạn và quy tắc của mức cô lập.

Do đó, một phiên B có thể **chưa thấy** dữ liệu A vừa commit trong một transaction với snapshot cũ, mặc dù bảng đó là permanent và dữ liệu đã được commit.

**Độ bền, độ hiển thị và vòng đời session là ba thuộc tính khác nhau**.

## 7. Temporary table: bảng thuộc phiên, không phải bảng chung

PostgreSQL cho phép tạo **temporary table**:

```sql
CREATE TEMP TABLE work_ids (
    order_id bigint PRIMARY KEY
);
```

Hoặc dạng đầy đủ:

```sql
CREATE TEMPORARY TABLE work_ids (
    order_id bigint PRIMARY KEY
);
```

Bảng này có cấu trúc và dữ liệu giống một bảng SQL bình thường trong phạm vi sử dụng, nhưng:

- Chỉ phiên tạo bảng mới truy cập bảng tạm đó theo cách thông thường.
- Phiên khác có thể có bảng tạm **cùng tên** nhưng đó là một đối tượng riêng.
- Bảng tạm thường được tự động loại bỏ khi session kết thúc.
- Mặc định, PostgreSQL dùng chính sách **`ON COMMIT PRESERVE ROWS`**, tức commit **không** xóa dữ liệu trong bảng tạm.
- Có thể chọn chính sách khác với `ON COMMIT DELETE ROWS` hoặc `ON COMMIT DROP`.

### 7.1. Tạo bảng tạm để giữ kết quả trung gian

Giả sử bảng `lifecycle_lab.orders` đã có dữ liệu và bạn muốn chọn những đơn giá trị cao:

```sql
CREATE TEMP TABLE high_value_orders AS
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE amount >= 200000;

SELECT *
FROM high_value_orders
ORDER BY amount DESC, order_id;
```

`CREATE TEMP TABLE ... AS SELECT` tạo bảng tạm chứa một **bản sao kết quả của truy vấn tại thời điểm thực thi**, không phải một view tự cập nhật theo bảng gốc. Nếu sau đó bảng `orders` thay đổi, `high_value_orders` **không tự thay đổi**.

Đây là một điểm dễ nhầm:

- **View:** biểu diễn truy vấn, khi đọc sẽ thực thi theo cơ chế tương ứng trên nguồn dữ liệu.
- **Temporary table:** lưu các hàng riêng trong phạm vi session.
- **CTE:** thành phần tổ chức một câu SQL, không đồng nghĩa với một bảng tạm có thể truy vấn qua nhiều statement.

### 7.2. Bảng tạm không chia sẻ với session khác

Ở session A:

```sql
CREATE TEMP TABLE report_stage (
    id integer PRIMARY KEY,
    note text
);

INSERT INTO report_stage (id, note)
VALUES (1, 'Session A only');

SELECT * FROM report_stage;
```

Ở session B (kết nối độc lập):

```sql
SELECT * FROM report_stage;
```

B thông thường nhận lỗi không tìm thấy bảng nếu không có đối tượng cùng tên ở schema khác. B **không thấy bảng tạm của A** chỉ vì cùng kết nối đến một database.

Nếu B tự tạo:

```sql
CREATE TEMP TABLE report_stage (
    id integer PRIMARY KEY,
    note text
);

INSERT INTO report_stage (id, note)
VALUES (2, 'Session B only');
```

thì hai session đang có **hai bảng tạm khác nhau**, dù tên SQL trùng nhau.

### 7.3. Dùng bảng tạm không đòi hỏi tên chung toàn database

PostgreSQL tự quản lý các schema nội bộ cho bảng tạm theo phiên, thường có tên dạng `pg_temp_N`. Bạn có thể truy cập bảng tạm theo tên không có schema hoặc qua alias đặc biệt `pg_temp` trong phiên của chính mình.

```sql
SELECT * FROM pg_temp.report_stage;
```

`pg_temp` là cách tham chiếu schema tạm của phiên hiện tại, không phải một schema toàn cục dùng để chia sẻ dữ liệu tạm giữa các kết nối.

## 8. Ba chính sách `ON COMMIT` của bảng tạm

Trong PostgreSQL, mỗi temporary table có thể chọn phản ứng khi **transaction commit**:

| Chính sách | Sau `COMMIT` | Sau khi session đóng |
| --- | --- | --- |
| `ON COMMIT PRESERVE ROWS` | Giữ cấu trúc bảng và dữ liệu đã commit | Bảng bị loại bỏ |
| `ON COMMIT DELETE ROWS` | Giữ cấu trúc, xóa toàn bộ các hàng trong bảng | Bảng bị loại bỏ |
| `ON COMMIT DROP` | Xóa bảng tạm khi transaction commit | Bảng đã bị xóa trước đó hoặc bị loại bỏ lúc kết thúc phiên |

### 8.1. Mặc định: `ON COMMIT PRESERVE ROWS`

```sql
CREATE TEMP TABLE stage_preserve (
    id integer PRIMARY KEY
) ON COMMIT PRESERVE ROWS;

BEGIN;

INSERT INTO stage_preserve (id)
VALUES (10);

COMMIT;

SELECT * FROM stage_preserve;
```

Ở cùng session, kết quả vẫn chứa `id = 10` sau commit. Nếu đóng kết nối và mở session mới, bảng `stage_preserve` không còn thuộc session mới.

### 8.2. `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE stage_delete (
    id integer PRIMARY KEY
) ON COMMIT DELETE ROWS;

BEGIN;

INSERT INTO stage_delete (id)
VALUES (20);

SELECT COUNT(*) AS rows_before_commit
FROM stage_delete;

COMMIT;

SELECT COUNT(*) AS rows_after_commit
FROM stage_delete;
```

Trong transaction, có 1 hàng. Sau `COMMIT`, bảng vẫn tồn tại nhưng không còn hàng nào; `rows_after_commit = 0`.

Chính sách này hữu ích nếu mỗi transaction dùng lại cấu trúc bảng tạm nhưng muốn bắt đầu xử lý dữ liệu mới từ bảng trống.

**Chú ý autocommit:** nếu bạn chạy `INSERT` vào bảng `ON COMMIT DELETE ROWS` mà không bắt đầu transaction tường minh, statement có thể là một transaction tự động riêng. Các hàng vừa insert bị xóa ngay lúc transaction của statement commit. Do đó, để kiểm tra dữ liệu trước khi commit, cần `BEGIN` rõ ràng.

### 8.3. `ON COMMIT DROP`

```sql
BEGIN;

CREATE TEMP TABLE stage_drop (
    id integer PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO stage_drop (id)
VALUES (30);

SELECT * FROM stage_drop;

COMMIT;
```

Sau `COMMIT`, bảng `stage_drop` không còn tồn tại:

```sql
-- Sau commit, ở cùng session:
SELECT * FROM stage_drop;
-- Dự kiến báo lỗi relation does not exist.
```

**Cảnh báo quan trọng:** tạo `ON COMMIT DROP` ngoài transaction tường minh trong phiên autocommit có thể làm bảng bị xóa ngay sau statement `CREATE TEMP TABLE`. Vì thế ví dụ đặt `BEGIN` **trước** lệnh tạo bảng.

### 8.4. Vì sao cần nắm ba chính sách?

Một script multi-step có thể chạy:

```text
CREATE TEMP TABLE stage
INSERT rows
COMMIT
SELECT FROM stage
```

Nếu `stage` dùng `PRESERVE ROWS`, dữ liệu còn. Nếu dùng `DELETE ROWS`, bảng còn nhưng rỗng. Nếu dùng `DROP`, lệnh `SELECT` lỗi vì bảng đã mất.

Đó là ba kết quả hoàn toàn khác nhau dù đều được gọi chung là “bảng tạm”.

## 9. Temporary table vẫn chịu quy tắc transaction

Temporary table là đối tượng có **vòng đời session**, nhưng thao tác tạo, sửa và ghi dữ liệu vào nó vẫn tuân theo nhiều quy tắc transaction.

### 9.1. `ROLLBACK` dữ liệu đã insert

Giả sử trong session A:

```sql
CREATE TEMP TABLE temp_tx (
    id integer PRIMARY KEY
);

INSERT INTO temp_tx(id) VALUES (1);

BEGIN;

INSERT INTO temp_tx(id) VALUES (2);

ROLLBACK;

SELECT id FROM temp_tx ORDER BY id;
```

Kết quả còn `id = 1` nhưng không có `id = 2`. Lý do: hàng 1 được commit ở statement trước đó (giả sử autocommit bật), còn insert hàng 2 nằm trong transaction đã rollback.

Như vậy, dữ liệu bảng tạm **không** đồng nghĩa với “không có transaction” hay “không rollback được”.

### 9.2. `ROLLBACK` việc tạo bảng

```sql
BEGIN;

CREATE TEMP TABLE temp_created_in_tx (
    id integer
);

INSERT INTO temp_created_in_tx(id)
VALUES (1);

ROLLBACK;
```

Sau rollback, bản thân `CREATE TEMP TABLE` cũng bị hoàn tác và bảng `temp_created_in_tx` không còn tồn tại ở session đó.

Ngược lại, bảng tạm đã được tạo và commit trước transaction có thể vẫn còn sau khi một transaction sau bị rollback. Vòng đời session và hành vi transaction **cùng tồn tại**, không loại trừ nhau.

### 9.3. `SAVEPOINT` với bảng tạm

```sql
CREATE TEMP TABLE temp_savepoint (
    id integer PRIMARY KEY
);

BEGIN;

INSERT INTO temp_savepoint(id) VALUES (1);

SAVEPOINT before_second_insert;

INSERT INTO temp_savepoint(id) VALUES (2);

ROLLBACK TO SAVEPOINT before_second_insert;

COMMIT;

SELECT * FROM temp_savepoint ORDER BY id;
```

Sau commit, chỉ còn `id = 1`. Đây là ví dụ cho thấy PostgreSQL vẫn dùng transaction và savepoint để bảo vệ thao tác trên bảng tạm.

## 10. Unlogged table: không phải permanent đầy đủ, cũng không phải temp

Một loại bảng thứ ba đặc biệt quan trọng trong PostgreSQL là **UNLOGGED table**:

```sql
CREATE UNLOGGED TABLE lifecycle_lab.import_stage (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    raw_value text NOT NULL,
    PRIMARY KEY (batch_id, line_no)
);
```

UNLOGGED table:

- Là bảng có tên và đối tượng **tồn tại giữa các session**.
- Có thể được những session khác truy cập theo quyền và cơ chế transaction.
- Thông thường vẫn tồn tại **qua một lần shutdown/restart sạch**.
- Không ghi WAL cho **dữ liệu bảng** theo cách của permanent table, nên giảm một số chi phí ghi WAL.
- **Không được bảo vệ phục hồi như bảng thường**: sau crash hoặc shutdown không sạch, PostgreSQL sẽ **truncate** dữ liệu của bảng unlogged.
- Dữ liệu unlogged không được truyền qua **physical streaming replication** theo cách dữ liệu permanent được WAL bảo vệ; không dùng nó làm nguồn dữ liệu bền vững trên standby.

### 10.1. UNLOGGED không đồng nghĩa với TEMP

| Thuộc tính | Permanent table | UNLOGGED table | TEMP table |
| --- | --- | --- | --- |
| Nhiều session truy cập cùng đối tượng? | Có, theo quyền và MVCC | Có, theo quyền và MVCC | Không; đối tượng theo phiên |
| Còn khi session tạo đóng? | Có | Có | Không |
| Còn qua restart sạch? | Có | Có | Không |
| Dữ liệu qua crash được bảo vệ bởi WAL thông thường? | Có, theo durability config | Không; có thể bị truncate | Không; session kết thúc |
| Phù hợp dữ liệu nghiệp vụ lâu dài? | Có | Không nếu không thể tái tạo | Không |
| Hỗ trợ transaction cho DML? | Có | Có | Có |

UNLOGGED là một lựa chọn cho **dữ liệu có thể tái tạo hoặc nạp lại**, chẳng hạn một số staging table phục vụ import. Nó không phù hợp với dữ liệu duy nhất không thể phục hồi từ nguồn khác.

### 10.2. Ví dụ hai session với UNLOGGED

Session A:

```sql
INSERT INTO lifecycle_lab.import_stage
    (batch_id, line_no, raw_value)
VALUES (7, 1, 'original file line');

COMMIT;
```

Nếu ở autocommit, lệnh `INSERT` đã được commit ngay sau statement; `COMMIT` tường minh tiếp theo ngoài transaction có thể chỉ tạo cảnh báo không có transaction. Trong ví dụ triển khai thực tế, nên chọn **một cách quản lý transaction nhất quán**:

```sql
BEGIN;

INSERT INTO lifecycle_lab.import_stage
    (batch_id, line_no, raw_value)
VALUES (7, 2, 'another line');

COMMIT;
```

Session B có thể đọc hai hàng đã commit:

```sql
SELECT *
FROM lifecycle_lab.import_stage
WHERE batch_id = 7
ORDER BY line_no;
```

Dữ liệu unlogged không bị giới hạn trong session A như temporary table. Nhưng nếu hệ thống gặp crash, nó có thể bị xóa/truncate theo cơ chế của PostgreSQL.

### 10.3. Quy tắc chọn UNLOGGED

Chỉ xem xét nếu thỏa các điều kiện:

1. Dữ liệu có thể phục hồi từ nguồn đáng tin cậy.
2. Các tác động khi crash và mất nội dung staging đã được chấp nhận.
3. Không phụ thuộc vào replication theo cơ chế WAL thông thường.
4. Lợi ích giảm chi phí WAL đáng kể đối với workload đã đo.
5. Có quy trình dọn dẹp, nạp lại và xử lý công việc còn dang dở.

Không chuyển bảng đơn hàng, thanh toán hay số dư thành UNLOGGED chỉ để tăng tốc ghi.

## 11. So sánh theo ba trục: vòng đời, phạm vi nhìn thấy, khả năng phục hồi

Để không nhầm, nên tách ba câu hỏi:

**Câu hỏi A – Vòng đời:** dữ liệu biến mất khi nào?

- Permanent: tồn tại cho đến khi bị xóa/đổi bằng SQL hoặc quản trị.
- UNLOGGED: đối tượng tồn tại lâu, nhưng dữ liệu có thể bị truncate sau crash.
- TEMP: biến mất khi session đóng, hoặc sớm hơn theo `ON COMMIT DROP`.
- `SET LOCAL`: hết hiệu lực khi transaction kết thúc.
- Session `SET`: thường hết hiệu lực khi session đóng hoặc khi được thay đổi/reset.

**Câu hỏi B – Ai nhìn thấy?**

- Permanent và UNLOGGED: nhiều phiên, có kiểm soát bằng quyền và MVCC.
- TEMP: phiên tạo có bảng riêng; phiên khác không đọc trực tiếp bảng tạm đó.
- Session settings: chỉ kết nối tương ứng.
- Transaction uncommitted changes: không tự xuất hiện ở các session khác.

**Câu hỏi C – Có phục hồi sau crash không?**

- Permanent table, theo cấu hình durability và WAL.
- UNLOGGED table không có bảo đảm đó đối với dữ liệu.
- Temporary table và session state biến mất vì connection đã kết thúc.
- Temporary files dùng cho xử lý trung gian không phải kho dữ liệu phục hồi lâu dài.

## 12. Kiểm tra loại bảng bằng catalog `pg_class`

PostgreSQL lưu metadata về quan hệ trong các system catalog. Trường `pg_class.relpersistence` biểu thị mức persistence của nhiều loại relation:

| Giá trị | Ý nghĩa |
| --- | --- |
| `p` | Permanent |
| `u` | Unlogged |
| `t` | Temporary |

Có thể kiểm tra trên database thử nghiệm:

```sql
SELECT
    n.nspname AS schema_name,
    c.relname AS relation_name,
    c.relkind,
    c.relpersistence
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.relname IN (
    'orders',
    'import_stage',
    'temp_tx',
    'stage_preserve'
)
ORDER BY n.nspname, c.relname;
```

Nếu bạn chạy query này từ session không tạo bảng tạm, các bảng tạm của session khác có thể xuất hiện ở catalog trong một số ngữ cảnh, nhưng **không đồng nghĩa** phiên đó có thể truy cập dữ liệu bảng tạm khác. Hãy phân biệt metadata catalog với quyền nhìn thấy dữ liệu của object trong session.

### 12.1. Nhận diện schema tạm của phiên

```sql
SELECT
    pg_backend_pid() AS backend_pid,
    pg_my_temp_schema() AS my_temp_schema_oid;
```

`pg_my_temp_schema()` trả OID của schema tạm gắn với session hiện tại (hoặc 0 nếu session chưa có schema temp tương ứng). Có thể xem tên schema bằng cách nối catalog, nếu cần:

```sql
SELECT nspname
FROM pg_namespace
WHERE oid = pg_my_temp_schema();
```

Việc schema tạm có tên nội bộ như `pg_temp_3` không có nghĩa người dùng nên tự xây dựng logic để truy cập dữ liệu phiên khác bằng cách đoán số thứ tự schema. Dùng tên `pg_temp` của chính phiên hoặc tên bảng tạm không schema là cách tiếp cận thích hợp.

## 13. Bảng tạm và tên đối tượng trùng nhau

Giả sử có bảng thật:

```sql
CREATE TABLE lifecycle_lab.metrics (
    metric_name text PRIMARY KEY,
    metric_value integer NOT NULL
);

INSERT INTO lifecycle_lab.metrics
    (metric_name, metric_value)
VALUES ('daily_orders', 100);
```

Session A tạo bảng tạm trùng tên phần bảng:

```sql
CREATE TEMP TABLE metrics (
    metric_name text PRIMARY KEY,
    metric_value integer NOT NULL
);

INSERT INTO metrics
VALUES ('daily_orders', 999);
```

Trong session A:

```sql
SELECT * FROM metrics;
```

có thể truy cập bảng tạm trước do quy tắc phân giải tên tạm trong `search_path`.

Muốn lấy chắc chắn bảng thật:

```sql
SELECT *
FROM lifecycle_lab.metrics;
```

Muốn lấy bảng tạm của phiên:

```sql
SELECT *
FROM pg_temp.metrics;
```

**Bài học:** khi một bảng tạm che tên bảng permanent, câu SQL không ghi schema có thể đọc/ghi **nhầm đối tượng**. Với tác vụ quan trọng, nên dùng tên schema đầy đủ và đặt tên bảng tạm có mục đích rõ.

### 13.1. Lưu ý an toàn về `search_path` và hàm SECURITY DEFINER

Cơ chế phân giải tên đối tượng cần được xem xét đặc biệt khi dùng các hàm có quyền cao hơn người gọi (`SECURITY DEFINER`). Không nên viết code quyền cao dùng tên bảng không được schema-qualify rồi để một session tạo bảng tạm trùng tên làm thay đổi đối tượng được truy cập.

Những hàm quyền cao cần kiểm soát `search_path` một cách an toàn và sử dụng tên schema rõ ràng cho đối tượng quan trọng. Đây không chỉ là vấn đề thuận tiện mà còn liên quan tới bảo mật và quyền truy cập.

## 14. Phân biệt temporary table với temporary file

PostgreSQL còn tạo **tệp tạm** trên đĩa để thực thi query khi cần bộ nhớ trung gian lớn hơn giới hạn phù hợp. Ví dụ:

- `ORDER BY` cần sắp xếp tập dữ liệu lớn.
- `GROUP BY` hoặc hash join cần bộ nhớ trung gian và có thể spill.
- Một số thao tác materialization hoặc xử lý trung gian.

```text
SELECT ... ORDER BY ...
         |
         v
Sort node
         |
         +-- Vừa bộ nhớ: xử lý in-memory
         |
         +-- Không đủ: tạo temporary disk files
                        |
                        +-- Phục vụ query/iterator
                        +-- Không phải bảng SQL để SELECT
                        +-- Được dọn theo vòng đời thực thi
```

**Temporary disk file không phải temporary table**:

| Đặc điểm | Temporary table | Temporary file của executor |
| --- | --- | --- |
| Người dùng tự tạo bằng SQL? | Có, `CREATE TEMP TABLE` | Thường do executor tạo tự động |
| Có tên quan hệ SQL? | Có | Không phải quan hệ SQL để truy vấn trực tiếp |
| Có thể `SELECT` nhiều lần? | Có, trong cùng session | Không |
| Dùng cho nhiều statement? | Có thể, theo `ON COMMIT` và session | Thường theo thời gian thực thi/nhu cầu nội bộ |
| Có thể tạo index tường minh? | Có | Không dùng như index quan hệ thông thường |
| Chủ yếu để làm gì? | Lưu dữ liệu trung gian có chủ đích | Spill/sort/hash nội bộ do query cần |

### 14.1. `work_mem` và spill

Tham số `work_mem` ảnh hưởng lượng bộ nhớ mà **mỗi hoạt động query phù hợp** như sort/hash có thể sử dụng trước khi cân nhắc spill, với những chi tiết riêng về hash và bộ nhớ. Nó không phải giới hạn RAM tuyệt đối cho toàn session.

```sql
SHOW work_mem;
```

Có thể tạm thay đổi cho **một transaction** trong môi trường thử nghiệm:

```sql
BEGIN;

SET LOCAL work_mem = '32MB';

SELECT order_id, amount
FROM lifecycle_lab.orders
ORDER BY amount DESC;

COMMIT;
```

Không tăng `work_mem` toàn hệ thống một cách vô hạn: nhiều query đồng thời, mỗi query có nhiều sort/hash node, có thể cùng tiêu thụ lượng bộ nhớ đáng kể.

### 14.2. Theo dõi temporary file

PostgreSQL có thống kê ở `pg_stat_database`:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_data_written
FROM pg_stat_database
WHERE datname = current_database();
```

`temp_files` và `temp_bytes` phản ánh temporary files được PostgreSQL thống kê trong khoảng thống kê tương ứng. Chúng không tương đương với “số temporary table đã được tạo” hay “tổng kích thước bảng tạm của phiên”.

Cấu hình `log_temp_files` có thể giúp ghi nhận những temporary file của executor vượt ngưỡng; việc bật có thể tác động dung lượng log, nên cần tuân thủ quy trình quan sát vận hành.

## 15. Trạng thái phiên khác với cache và dữ liệu dùng chung

Có một nhóm dữ liệu khác thường gây nhầm: **cache và bộ nhớ dùng chung của server**.

PostgreSQL có **shared buffers**, cache của hệ điều hành, các bộ đệm WAL và nhiều cấu trúc nội bộ phục vụ nhiều backend. Chúng khác session state:

- Bộ đệm của một trang từ bảng permanent có thể được nhiều backend hưởng lợi.
- Một giá trị `SET statement_timeout` của session A không tự áp dụng cho session B chỉ vì dữ liệu bảng đang cùng cache.
- Prepared statement của session A không trở thành prepared statement của session B chỉ vì cả hai chạy cùng câu SQL.

Việc data page đang ở RAM **không quyết định** đó là permanent hay temporary table. Temporary table vẫn có thể ghi dữ liệu xuống đĩa; permanent table cũng thường được đọc từ cache. **Nơi các trang đang được cache** và **vòng đời/độ bền logic của dữ liệu** là hai khía cạnh khác nhau.

## 16. Những thành phần session state khác cần biết

### 16.1. SQL `PREPARE` và `EXECUTE`

`PREPARE` tạo prepared statement trong session:

```sql
PREPARE find_order (bigint) AS
SELECT order_id, customer_name, amount
FROM lifecycle_lab.orders
WHERE order_id = $1;

EXECUTE find_order(1001);
```

Trong session này, có thể gọi lại:

```sql
EXECUTE find_order(1002);
```

Để giải phóng:

```sql
DEALLOCATE find_order;
```

Prepared statement được tạo bằng SQL `PREPARE` thuộc vòng đời phiên, không tự có ở session B. Session B chạy `EXECUTE find_order(1001)` sẽ gặp lỗi nếu nó chưa tạo prepared statement tên đó.

**Đừng nhầm SQL `PREPARE` với prepared transaction (`PREPARE TRANSACTION`)** của cơ chế two-phase commit. Đó là hai chức năng khác nhau, có vòng đời và cách vận hành khác nhau.

### 16.2. Session-level advisory lock

PostgreSQL có advisory lock để ứng dụng phối hợp theo khóa do mình chọn.

Ví dụ session A:

```sql
SELECT pg_advisory_lock(9001);
```

Đây là khóa dạng **session-level**; không nhất thiết tự giải phóng chỉ vì một transaction commit hoặc rollback. Cần giải phóng:

```sql
SELECT pg_advisory_unlock(9001);
```

hoặc để session kết thúc.

Ngược lại:

```sql
BEGIN;

SELECT pg_advisory_xact_lock(9002);

-- Thực hiện công việc phối hợp.
COMMIT;
```

`pg_advisory_xact_lock` gắn với **transaction**, được giải phóng khi transaction kết thúc.

| Loại khóa | Vòng đời |
| --- | --- |
| `pg_advisory_lock` | Session, đến khi unlock hoặc session chấm dứt |
| `pg_advisory_xact_lock` | Transaction, đến khi commit/rollback |
| Khóa hàng khi `SELECT ... FOR UPDATE` | Theo transaction |
| Khóa nội bộ khi DDL/DML | Theo cơ chế và ranh giới transaction tương ứng |

Session-level advisory lock có thể gây vấn đề nghiêm trọng nếu ứng dụng trả connection về pool mà **quên unlock**: request kế tiếp mượn cùng connection có thể kế thừa một tài nguyên khóa còn giữ.

### 16.3. `LISTEN`/`NOTIFY`

Một phiên có thể đăng ký nhận thông báo trên một channel:

```sql
LISTEN order_events;
```

Phiên khác có thể phát thông báo:

```sql
NOTIFY order_events, 'order-1001-updated';
```

Việc đăng ký `LISTEN` là trạng thái gắn với session. Nếu connection đóng, đăng ký không tồn tại sang session mới. Một thông báo `NOTIFY` cũng không thay thế **hàng dữ liệu bền vững** hay một message queue có retention và khả năng đọc lại độc lập.

Trong các trường hợp cần không mất sự kiện khi listener offline, nên lưu sự kiện đáng tin cậy trong bảng hoặc hệ thống message phù hợp, thay vì chỉ dựa vào `NOTIFY`.

### 16.4. Cursor

Một cursor truy vấn có thể được mở trong transaction để đọc nhiều lần:

```sql
BEGIN;

DECLARE order_cursor CURSOR FOR
SELECT order_id, amount
FROM lifecycle_lab.orders
ORDER BY order_id;

FETCH 2 FROM order_cursor;

CLOSE order_cursor;

COMMIT;
```

Cursor thông thường có vòng đời gắn với transaction. PostgreSQL còn hỗ trợ các kiểu cursor `WITH HOLD` với quy tắc giữ qua commit nhất định, nhưng nó không phải bản sao một bảng permanent. Không giả định một cursor có thể tiếp tục được sử dụng ở session khác.

## 17. Connection pooling: vấn đề phổ biến nhất khi nhầm session

Trong ứng dụng dùng connection pool, request của người dùng không đồng nghĩa một session PostgreSQL mới.

```text
Connection Pool
   +-------------+
   | Connection 1| -> Request A, sau đó Request C
   | Connection 2| -> Request B, sau đó Request D
   +-------------+
```

Nếu A thực hiện:

```sql
SET search_path TO tenant_a, public;
```

rồi trả connection về pool mà không reset, request C có thể tiếp tục dùng `search_path` với `tenant_a`, dù C phục vụ tenant khác. Đây là lỗi **rò rỉ trạng thái phiên** và có thể trở thành lỗi truy cập dữ liệu chéo tenant nếu thiết kế quyền/định tuyến không đúng.

Một cách giảm rủi ro khi thay session state cho **một transaction**:

```sql
BEGIN;

SET LOCAL search_path TO tenant_a, public;

-- SQL nghiệp vụ của tenant_a trong transaction.
-- Ví dụ cần schema và bảng thực sự tồn tại.
SELECT COUNT(*) FROM orders;

COMMIT;
```

Sau commit, tác động của `SET LOCAL` kết thúc. Tuy nhiên, ứng dụng còn phải đảm bảo **đúng transaction, đúng connection và kiểm tra tenant/authorization**, không chỉ dựa vào `search_path`.

### 17.1. Pool theo session và pool theo transaction

Một số proxy/pooler như PgBouncer có nhiều kiểu pooling:

| Kiểu pooling | Ý nghĩa khái quát |
| --- | --- |
| Session pooling | Một kết nối server thường được gắn với client session trong suốt session đó |
| Transaction pooling | Kết nối server có thể được trả về pool và gán cho client khác **sau mỗi transaction** |

Với transaction pooling, không nên kỳ vọng trạng thái `SET` session, bảng tạm cần tồn tại qua transaction, SQL `PREPARE`, session-level advisory lock hoặc listener `LISTEN` luôn được gắn cố định với client trong toàn bộ thời gian sử dụng. Một số pooler hiện đại có tính năng theo dõi riêng cho một số loại state; hỗ trợ thực tế phụ thuộc phiên bản/cấu hình. Phương án an toàn là thiết kế theo **hợp đồng pooling được hỗ trợ**, không dựa vào sự trùng hợp vẫn gặp cùng backend.

### 17.2. Reset session

PostgreSQL có:

```sql
DISCARD ALL;
```

Lệnh này yêu cầu dọn lại nhiều phần trạng thái session, như một số cấu hình, prepared statements, temporary objects và những trạng thái được PostgreSQL hỗ trợ reset. `DISCARD ALL` **không được chạy bên trong transaction block**, và không thể thay thế trách nhiệm kiểm soát connection lifecycle của pool.

Các lệnh chuyên biệt khác có thể hữu ích:

```sql
RESET ALL;
DEALLOCATE ALL;
DISCARD TEMP;
UNLISTEN *;
```

Chúng không hoàn toàn tương đương:

- `RESET ALL` đặt lại những tham số cấu hình thích hợp.
- `DEALLOCATE ALL` giải phóng prepared statements SQL trong session.
- `DISCARD TEMP` xóa temporary tables và các đối tượng tạm thích hợp trong session.
- `UNLISTEN *` hủy đăng ký LISTEN của session.

**Không dùng `DISCARD ALL` ở mọi request một cách máy móc.** Nó có chi phí và hạn chế transaction; nên làm theo chính sách reset mà driver/pool cung cấp và kiểm tra nhu cầu cụ thể.

## 18. Quyết định dùng TEMP table hay bảng thường trong một workflow

### 18.1. Dữ liệu đầu ra cần được giữ sau khi job kết thúc

Ví dụ một job tạo báo cáo doanh số phải được người khác mở vào hôm sau. Dùng **bảng thường** với khóa report/job:

```sql
CREATE TABLE lifecycle_lab.report_results (
    report_id bigint NOT NULL,
    order_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL,
    PRIMARY KEY (report_id, order_id)
);
```

Khi job insert và commit, các phiên được phép có thể đọc kết quả về sau.

**Không dùng temporary table** làm kho kết quả cuối cần nhiều người đọc qua session khác.

### 18.2. Dữ liệu trung gian của một job trong cùng session

Ví dụ một job cần chọn tập ID, tạo index tạm, rồi JOIN nhiều lần trước khi hoàn thành:

```sql
CREATE TEMP TABLE stage_order_ids
ON COMMIT PRESERVE ROWS
AS
SELECT order_id
FROM lifecycle_lab.orders
WHERE amount >= 200000;

CREATE INDEX ON stage_order_ids (order_id);

ANALYZE stage_order_ids;

SELECT o.order_id, o.amount
FROM lifecycle_lab.orders AS o
JOIN stage_order_ids AS s
    ON s.order_id = o.order_id
ORDER BY o.order_id;
```

Bảng tạm hợp lý khi tập kết quả trung gian cần **dùng lại qua nhiều statement trên cùng session**.

PostgreSQL autovacuum **không thể vacuum/analyze temporary table của một phiên khác** theo cách vận hành thông thường; vì vậy với bảng tạm lớn, chạy `ANALYZE` chủ động sau khi nạp dữ liệu có thể giúp planner có thống kê tốt hơn.

### 18.3. Dữ liệu có thể tái tạo nhưng cần chia sẻ giữa nhiều job

Nếu dữ liệu staging được nhiều session đọc và có thể nạp lại sau sự cố, `UNLOGGED` có thể đáng cân nhắc. Tuy nhiên, phải hiểu rõ crash truncate, replication và quy trình nạp lại.

### 18.4. Chỉ cần trung gian trong một câu query

Một **CTE** thường đơn giản hơn việc tạo bảng tạm:

```sql
WITH high_value AS (
    SELECT order_id, amount
    FROM lifecycle_lab.orders
    WHERE amount >= 200000
)
SELECT COUNT(*) AS order_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM high_value;
```

CTE không tạo một tên bảng độc lập dùng được qua nhiều câu SQL. PostgreSQL có thể inline hoặc materialize CTE tùy query, phiên bản và các hint/chính sách phù hợp; không nên mặc định CTE luôn tạo một temporary table vật lý.

### 18.5. Bảng quyết định

| Yêu cầu | Lựa chọn thường phù hợp |
| --- | --- |
| Đơn hàng/thanh toán cần giữ lâu dài | Permanent table |
| Báo cáo đã hoàn thành cần được mở từ session khác | Permanent table |
| Bộ ID tạm chỉ trong một backend, dùng lại nhiều query | TEMP table |
| Mỗi transaction cần một bảng trung gian rỗng | TEMP `ON COMMIT DELETE ROWS` |
| Tạo bảng chỉ phục vụ một transaction | TEMP `ON COMMIT DROP` |
| Dữ liệu nạp được lại, cần nhiều session cùng truy cập | Có thể cân nhắc UNLOGGED |
| Tham số timeout riêng cho một transaction | `SET LOCAL` |
| Tham số riêng cho một kết nối được quản lý | `SET` và reset phù hợp |
| Điều kiện trung gian của một query duy nhất | Subquery hoặc CTE |

## 19. Thực hành hai phiên psql: phân biệt phạm vi bằng quan sát

Phần này là thực hành có thể chạy trên **database thử nghiệm riêng**. Không chạy các câu tạo/xóa bảng trên production.

### 19.1. Chuẩn bị dữ liệu permanent

Kết nối A hoặc phiên quản trị thử nghiệm:

```sql
CREATE SCHEMA IF NOT EXISTS lifecycle_lab;

CREATE TABLE IF NOT EXISTS lifecycle_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO lifecycle_lab.orders
    (order_id, customer_name, amount)
VALUES (1101, 'Khách A', 125000.00)
ON CONFLICT (order_id)
DO UPDATE SET
    customer_name = EXCLUDED.customer_name,
    amount = EXCLUDED.amount;
```

Trong một môi trường lab mới, đoạn này tạo schema, bảng và dữ liệu. Những bảng đã tồn tại không được `IF NOT EXISTS` kiểm chứng tự động có cấu trúc như mong muốn, nên hãy chọn schema riêng và môi trường kiểm thử sạch.

### 19.2. Session A: tạo trạng thái và bảng tạm

Mở terminal A:

```bash
psql -h localhost -U lab_user -d lab_db
```

Trong phiên A:

```sql
SELECT pg_backend_pid() AS session_a_pid;

SET statement_timeout = '5s';

CREATE TEMP TABLE temp_notes (
    note_id integer PRIMARY KEY,
    note text NOT NULL
) ON COMMIT PRESERVE ROWS;

INSERT INTO temp_notes (note_id, note)
VALUES (1, 'Only session A');

SELECT * FROM temp_notes;

SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;
```

Trong A, bảng tạm và giá trị `statement_timeout` đều có hiệu lực.

### 19.3. Session B: kiểm tra trạng thái không được chia sẻ

Mở **terminal B** với kết nối psql mới:

```bash
psql -h localhost -U lab_user -d lab_db
```

Trong phiên B:

```sql
SELECT pg_backend_pid() AS session_b_pid;

SHOW statement_timeout;

SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;
```

Session B có thể đọc hàng đã commit trong bảng permanent (nếu có quyền) và thường thấy `statement_timeout` theo cấu hình riêng của B, không phải do A vừa `SET`.

Tiếp:

```sql
SELECT * FROM temp_notes;
```

Dự kiến B báo không tìm thấy quan hệ `temp_notes` nếu B chưa tự tạo một đối tượng trùng tên. Không cần biết tên schema tạm của A; dữ liệu tạm thuộc A không được chia sẻ cho B.

### 19.4. Session A: kiểm tra COMMIT không xóa bảng tạm mặc định

Trong A:

```sql
BEGIN;

INSERT INTO temp_notes (note_id, note)
VALUES (2, 'Committed within A');

COMMIT;

SELECT * FROM temp_notes ORDER BY note_id;
```

Kết quả A có hai hàng 1 và 2 vì `ON COMMIT PRESERVE ROWS`.

Trong B, query `SELECT * FROM temp_notes` vẫn không thể lấy dữ liệu bảng tạm của A.

### 19.5. Đóng session A rồi mở lại

Trong A:

```text
\q
```

Mở lại một kết nối mới và chạy:

```sql
SELECT * FROM lifecycle_lab.orders
WHERE order_id = 1101;

SELECT * FROM temp_notes;
```

Bảng permanent vẫn có hàng đã commit. Bảng tạm `temp_notes` không còn trong session mới. `statement_timeout` cũng trở về cấu hình mặc định áp dụng cho session mới, thay vì kế thừa thay đổi `SET` đơn lẻ của A.

**Bài học kết thúc:** permanent data, session setting và TEMP table có ba vòng đời khác nhau, dù cùng được tạo và truy cập qua các câu SQL.

## 20. Tình huống lỗi thường gặp khi nhầm vòng đời

### 20.1. “Tôi đã COMMIT nhưng bảng tạm vẫn tồn tại”

Đó là hành vi bình thường nếu temporary table dùng `ON COMMIT PRESERVE ROWS` (mặc định). Muốn xóa hàng ở mỗi commit dùng `ON COMMIT DELETE ROWS`; muốn xóa bảng khi commit dùng `ON COMMIT DROP` trong transaction phù hợp.

### 20.2. “Tôi đóng kết nối và mất bảng báo cáo”

Nếu báo cáo nằm trong `CREATE TEMP TABLE`, dữ liệu của nó chỉ thuộc session, nên mất bảng khi session đóng là đúng thiết kế. Hãy lưu kết quả cần chia sẻ trong bảng permanent.

### 20.3. “Tôi tạo temp table rồi request tiếp theo không tìm thấy”

Request sau có thể được pool đưa sang **connection khác** hoặc pooler transaction-mode phân bổ backend khác. Temporary table không thể coi là một kho dữ liệu liên request độc lập.

### 20.4. “Tôi dùng UNLOGGED và dữ liệu biến mất sau sự cố”

UNLOGGED không ghi WAL cho dữ liệu theo cơ chế permanent. PostgreSQL có thể truncate dữ liệu của bảng unlogged sau crash/unclean shutdown. Nếu dữ liệu cần durability, sử dụng permanent table và backup/replication phù hợp.

### 20.5. “Tôi chạy SET ở request A, request B nhận cấu hình lạ”

Nhiều khả năng hai request sử dụng lại cùng backend connection từ pool mà state chưa được reset. Hãy kiểm soát reset theo chính sách pool hoặc dùng `SET LOCAL` trong transaction nếu hợp lý.

### 20.6. “Tôi đã ROLLBACK nhưng bảng tạm không mất”

Nếu bảng tạm được tạo **trước** transaction đã rollback, rollback chỉ hoàn tác những thay đổi thuộc transaction. Bản thân bảng vẫn còn cho đến khi session kết thúc hoặc bạn `DROP TABLE`/`DISCARD TEMP`.

### 20.7. “Tôi thấy temp_files tăng nhưng chưa CREATE TEMP TABLE”

Có thể executor đang spill sort/hash sang disk. Temporary disk file và temporary table là hai cơ chế khác nhau. Xem `EXPLAIN (ANALYZE, BUFFERS)` hoặc thống kê phù hợp nếu cần điều tra hiệu năng, trong môi trường và quyền cho phép.

### 20.8. “Bảng tạm cùng tên bảng thật khiến query trả kết quả lạ”

Tên bảng tạm có thể che tên bảng permanent khi không ghi schema. Dùng tên rõ ràng, `pg_temp.tên_bảng` cho bảng tạm hoặc `schema_thật.tên_bảng` cho bảng permanent.

### 20.9. “Tôi dùng PREPARE ở phiên A, phiên B EXECUTE không được”

SQL prepared statement thuộc session A. B phải tạo prepared statement của riêng nó, hoặc ứng dụng cần dùng cơ chế driver/pooler được hỗ trợ. Một câu `PREPARE` không tạo truy vấn có tên toàn database.

### 20.10. “Tôi dùng SET LOCAL nhưng query sau COMMIT không còn timeout”

Đó là ý nghĩa `SET LOCAL`: hiệu lực chỉ trong transaction. Muốn áp dụng cho cả session dùng `SET` với quy trình reset phù hợp, hoặc đặt default ở phạm vi cấu hình được quản trị.

## 21. Bài tập thực hành

### Bài 1: Phân loại đối tượng

Cho các thao tác:

```sql
CREATE TABLE public.a (id integer PRIMARY KEY);
CREATE UNLOGGED TABLE public.b (id integer PRIMARY KEY);
CREATE TEMP TABLE c (id integer PRIMARY KEY);
SET statement_timeout = '3s';
BEGIN;
SET LOCAL work_mem = '16MB';
COMMIT;
```

Hãy phân loại:

| Thành phần | Loại vòng đời |
| --- | --- |
| `public.a` | Permanent table, dữ liệu được WAL bảo vệ theo cấu hình durability |
| `public.b` | UNLOGGED, chia sẻ giữa session nhưng không bảo vệ dữ liệu qua crash theo WAL thông thường |
| `c` | TEMP table, tồn tại trong session và bị xóa khi session kết thúc |
| `statement_timeout` | Session setting, thường có hiệu lực đến khi reset hoặc session đóng |
| `work_mem` từ `SET LOCAL` | Chỉ trong transaction, hết hiệu lực sau commit |

### Bài 2: Điều gì xảy ra với `ON COMMIT DELETE ROWS`?

```sql
CREATE TEMP TABLE t (
    id integer
) ON COMMIT DELETE ROWS;

BEGIN;
INSERT INTO t VALUES (1), (2);
COMMIT;

SELECT COUNT(*) FROM t;
```

**Đáp án:** bảng `t` vẫn tồn tại nhưng không còn hàng; truy vấn `COUNT(*)` trả 0.

### Bài 3: Điều gì xảy ra với `ON COMMIT DROP`?

```sql
BEGIN;

CREATE TEMP TABLE t_drop (
    id integer
) ON COMMIT DROP;

INSERT INTO t_drop VALUES (10);

COMMIT;
```

**Đáp án:** bảng `t_drop` bị loại bỏ tại commit của transaction. Một `SELECT` sau đó trong cùng session sẽ không tìm thấy bảng.

### Bài 4: Session A và B có chia sẻ `SET` không?

A:

```sql
SET statement_timeout = '7s';
```

B:

```sql
SHOW statement_timeout;
```

**Đáp án:** B không tự thấy giá trị 7 giây do A đặt; giá trị của B phụ thuộc cấu hình mặc định và các thiết lập riêng của B.

### Bài 5: Bảng tạm có rollback được dữ liệu không?

```sql
CREATE TEMP TABLE t_tx (id integer);

INSERT INTO t_tx VALUES (1);

BEGIN;
INSERT INTO t_tx VALUES (2);
ROLLBACK;

SELECT * FROM t_tx ORDER BY id;
```

**Đáp án:** chỉ còn hàng 1 nếu autocommit đã commit lệnh insert đầu. Bảng tạm vẫn tuân theo transaction cho thao tác ghi.

### Bài 6: Chọn loại bảng cho staging khi nhiều worker cùng đọc

Một bộ dữ liệu staging phải được nhiều session đọc và có thể nạp lại hoàn toàn từ object storage nếu crash. Nên cân nhắc gì?

**Đáp án:** có thể dùng permanent table để đơn giản hóa durability, hoặc cân nhắc UNLOGGED nếu chấp nhận crash truncation và giới hạn replication. TEMP table thường không phù hợp vì dữ liệu bị giới hạn trong một session.

### Bài 7: Kết quả báo cáo cần tồn tại tới ngày mai

Dùng `CREATE TEMP TABLE` có phù hợp không?

**Đáp án:** không, nếu báo cáo cần đọc từ session khác sau khi job đã ngắt kết nối. Nên lưu vào permanent table hoặc hệ thống lưu trữ kết quả có độ bền phù hợp.

### Bài 8: Phân biệt temp file với temp table

`pg_stat_database.temp_bytes` tăng mạnh khi chạy một query `ORDER BY` lớn, nhưng không ai chạy `CREATE TEMP TABLE`.

**Đáp án:** executor có thể dùng file tạm cho sort/hash. Đó không phải temporary table SQL.

### Bài 9: `PREPARE` có sống qua restart server không?

```sql
PREPARE find_order(bigint) AS
SELECT * FROM lifecycle_lab.orders WHERE order_id = $1;
```

**Đáp án:** không. Prepared statement bằng SQL `PREPARE` thuộc session; restart làm các connection kết thúc và trạng thái phiên biến mất.

### Bài 10: Vì sao `SET LOCAL` thường hợp hơn `SET` khi dùng connection pool?

**Đáp án:** vì tác dụng của `SET LOCAL` kết thúc sau transaction; nó giảm khả năng để lại trạng thái cấu hình ảnh hưởng request dùng lại connection. Nhưng vẫn phải đảm bảo mọi truy vấn của request dùng đúng transaction và không dựa vào trạng thái session ngoài dự kiến.

## 22. Tổng kết

PostgreSQL đồng thời quản lý **dữ liệu lâu dài**, **trạng thái của từng kết nối** và **đối tượng/trung gian tạm thời**. Nắm rõ ba phạm vi này giúp viết ứng dụng và quy trình vận hành an toàn hơn.

Những nguyên tắc quan trọng nhất:

1. **Permanent table** giữ dữ liệu đã commit qua các phiên và restart, với cơ chế durability dựa trên WAL và cấu hình hệ thống.
2. **Commit không phải đóng session.** Transaction có vòng đời ngắn hơn session; `ROLLBACK` hoàn tác thay đổi thuộc transaction mà không nhất thiết xóa những đối tượng đã tạo trước đó.
3. **Session state** gồm `SET`, role, prepared statements, advisory locks và tài nguyên khác; trạng thái có thể bị giữ lại khi pool tái sử dụng connection.
4. **`SET LOCAL`** phù hợp cho thiết lập cục bộ trong một transaction; `SET` thường gắn với session và cần reset khi cần.
5. **TEMP table** là bảng SQL thuộc riêng session. Mặc định `ON COMMIT PRESERVE ROWS`; có thêm `DELETE ROWS` và `DROP` với hành vi khác nhau.
6. **UNLOGGED table không phải TEMP table.** Nó chia sẻ được giữa các phiên và tồn tại qua restart sạch, nhưng dữ liệu có thể bị truncate sau crash/unclean shutdown.
7. **Temporary file do executor tạo** phục vụ sort/hash khác với temporary table người dùng tạo bằng SQL.
8. **Không giả định mọi request dùng một session mới.** Connection pool và transaction pooling cần chính sách reset/kiểm soát trạng thái cụ thể.
9. **Dùng đúng loại lưu trữ theo yêu cầu:** kết quả cần chia sẻ/durable dùng bảng thường; dữ liệu tạm riêng một session dùng TEMP; staging có thể tái tạo có thể cân nhắc UNLOGGED.
10. **Luôn hỏi bốn câu:** đối tượng sống bao lâu, ai được thấy, transaction ảnh hưởng thế nào và có phục hồi sau sự cố hay không.

Khi phân biệt rạch ròi **database persistence**, **session scope** và **temporary processing**, bạn sẽ tránh được nhiều lỗi vận hành phổ biến: mất dữ liệu do chọn sai loại bảng, truy vấn không tìm thấy bảng sau khi thay connection, rò rỉ thiết lập giữa các request và hiểu nhầm về mức độ an toàn của các thay đổi vừa commit.
