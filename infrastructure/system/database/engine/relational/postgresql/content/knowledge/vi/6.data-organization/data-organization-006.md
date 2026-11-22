# Bảng thường, bảng tạm và bảng UNLOGGED trong PostgreSQL

## 1. Ba loại bảng phục vụ ba nhu cầu tổ chức dữ liệu

Trong PostgreSQL, phần lớn dữ liệu nghiệp vụ được lưu trong **bảng thường** (*permanent table*). Tuy nhiên, khi xử lý báo cáo, nhập dữ liệu hàng loạt hoặc tính toán nhiều bước, không phải tập dữ liệu nào cũng cần tồn tại lâu dài. PostgreSQL cung cấp thêm **bảng tạm** (*temporary table*) và **bảng UNLOGGED** để lựa chọn mức độ tồn tại và chi phí ghi phù hợp.

Ba kiểu tạo bảng:

```sql
-- Bảng thường: mặc định khi không ghi TEMP hoặc UNLOGGED.
CREATE TABLE app_orders (
    order_id bigint PRIMARY KEY,
    amount numeric(12,2) NOT NULL
);

-- Bảng tạm: tồn tại trong phạm vi phiên kết nối.
CREATE TEMP TABLE session_work (
    order_id bigint PRIMARY KEY
);

-- Bảng UNLOGGED: tồn tại qua các phiên, nhưng dữ liệu
-- không được bảo vệ bằng WAL như bảng thường.
CREATE UNLOGGED TABLE import_stage (
    batch_id bigint NOT NULL,
    raw_line text NOT NULL
);
```

Cùng là `CREATE TABLE`, nhưng chúng không có cùng vòng đời.

| Tiêu chí | Bảng thường (*permanent*) | Bảng tạm (*TEMP*) | Bảng `UNLOGGED` |
| --- | --- | --- | --- |
| Cú pháp cơ bản | `CREATE TABLE` | `CREATE TEMP TABLE` | `CREATE UNLOGGED TABLE` |
| Vòng đời đối tượng | Đến khi có lệnh xóa/đổi hoặc sự kiện quản trị | Thường đến khi session kết thúc; có thể ngắn hơn | Đến khi có lệnh xóa/đổi hoặc sự kiện quản trị |
| Đọc được từ session khác? | Có, theo quyền và MVCC | Không đọc trực tiếp bảng tạm của session khác | Có, theo quyền và MVCC |
| Còn sau khi client tạo bảng ngắt kết nối? | Có | Không | Có |
| Còn sau restart sạch? | Có | Không | Thường có |
| Bảo vệ dữ liệu qua crash bằng WAL thông thường? | Có, tùy cấu hình durability | Không; session bị chấm dứt | **Không**; dữ liệu có thể bị truncate |
| Được đưa sang physical standby bằng WAL như bảng thường? | Có theo cấu hình replication | Không | **Không** đối với nội dung dữ liệu |
| Có giao dịch, `COMMIT` và `ROLLBACK`? | Có | Có | Có |
| Tình huống điển hình | Đơn hàng, tài khoản, thanh toán | Kết quả trung gian của một session | Staging dùng chung, có thể nạp lại |

**Đừng hiểu “UNLOGGED” là “TEMP nhưng nhanh hơn”.** Bảng UNLOGGED là một đối tượng chung có vòng đời dài, trong khi TEMP gắn với một phiên kết nối. Điểm giống là chúng không cung cấp mức bảo vệ WAL đối với nội dung dữ liệu giống bảng thường.

Mục tiêu bài học: sau khi hoàn thành, bạn có thể thiết kế bảng đúng nhu cầu lưu giữ, biết tác động của transaction và crash, chọn cách sử dụng staging phù hợp, đồng thời kiểm tra loại bảng thực tế bằng SQL.

## 2. Tách bốn câu hỏi trước khi chọn loại bảng

Khi thiết kế, nên hỏi bốn câu độc lập:

1. **Dữ liệu cần tồn tại bao lâu?** Chỉ trong một phép tính, một giao dịch, một kết nối, một đợt import, hay nhiều năm?
2. **Ai cần đọc hoặc ghi dữ liệu?** Chỉ một session, nhiều kết nối ứng dụng, batch worker khác nhau, hay replica?
3. **Dữ liệu có cần sống sót sau sự cố không?** Nếu mất staging thì có thể lấy lại từ file gốc, object storage hoặc nguồn đáng tin cậy khác không?
4. **Chi phí vận hành quan trọng thế nào?** WAL, index, dung lượng lưu trữ, autovacuum, replication, backup, và khối lượng bảng tạm tạo/xóa.

Ví dụ một hệ thống bán hàng:

```text
Nguồn dữ liệu
   |
   +-- Giao dịch thanh toán ------------> permanent table
   |                                      (mất dữ liệu là không thể chấp nhận)
   |
   +-- Tập ID tạm khi tạo báo cáo ------> TEMP table
   |                                      (chỉ dùng trên cùng connection)
   |
   +-- File import có thể đọc lại ------> UNLOGGED staging table
                                          (nhiều worker đọc, chấp nhận nạp lại)
```

Phải lựa chọn dựa trên **yêu cầu dữ liệu**, không chỉ dựa trên cảm giác “TEMP nhanh” hay “WAL tốn tài nguyên”.

## 3. Bảng thường: nơi lưu dữ liệu lâu dài

### 3.1. Tạo và sử dụng

Bảng thường là mặc định:

```sql
CREATE SCHEMA IF NOT EXISTS table_kinds_lab;

CREATE TABLE table_kinds_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    amount numeric(12,2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now()
);
```

Thêm một đơn:

```sql
INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (101, 'Nguyễn An', 250000.00);
```

Nếu kết nối đang ở **autocommit**, câu `INSERT` thành công thường được commit như một transaction riêng. Nếu đang ở trong `BEGIN`, thay đổi phải đợi `COMMIT` mới trở thành dữ liệu đã commit.

Đọc từ kết nối khác:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM table_kinds_lab.orders
WHERE order_id = 101;
```

Session khác có thể đọc hàng đã commit nếu có quyền và snapshot cho phép.

### 3.2. `COMMIT`, `ROLLBACK` và khả năng hiển thị

Một thao tác trong transaction:

```sql
BEGIN;

INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (102, 'Trần Bình', 175000.00);

-- Trong transaction này, session có thể thấy thay đổi của chính mình.
SELECT * FROM table_kinds_lab.orders WHERE order_id = 102;

ROLLBACK;
```

Sau `ROLLBACK`, đơn 102 không trở thành dữ liệu đã commit.

Ngược lại:

```sql
BEGIN;

INSERT INTO table_kinds_lab.orders
    (order_id, customer_name, amount)
VALUES
    (103, 'Lê Chi', 300000.00);

COMMIT;
```

Dữ liệu đã commit của đơn 103 tiếp tục tồn tại sau khi phiên tạo nó đóng.

**Phân biệt hai thuộc tính:**

- **Hiển thị giữa phiên:** phụ thuộc commit, quyền và snapshot theo mức cô lập.
- **Bền vững sau sự cố:** phụ thuộc cơ chế WAL và cấu hình an toàn dữ liệu.

Một hàng đã commit có thể tạm thời chưa thấy ở transaction khác đang giữ snapshot cũ; điều đó không biến bảng permanent thành bảng tạm.

### 3.3. Vai trò của WAL

PostgreSQL sử dụng **Write-Ahead Log (WAL)** để ghi các thông tin thay đổi cần thiết trước khi dữ liệu tương ứng được coi là bền vững. Trong vận hành bình thường, WAL góp phần đảm bảo **crash recovery** và hỗ trợ replication/backup theo các cơ chế liên quan.

```text
UPDATE/INSERT vào bảng thường
             |
             v
  Thay đổi dữ liệu / tạo bản ghi WAL cần thiết
             |
             v
  COMMIT theo chính sách durability
             |
             v
  Khi cần: flush/ghi các trang dữ liệu
             |
             v
  Nếu gặp crash: dùng WAL để recovery
```

Bảng thường được thiết kế để bảo vệ các thay đổi đã commit trong điều kiện cấu hình durability phù hợp, nhưng không có nghĩa **không thể mất dữ liệu trong mọi tình huống**. Ví dụ:

- `synchronous_commit = off` có thể cho phép một số giao dịch được báo commit trước khi WAL tương ứng được ghi bền vững; một crash gần thời điểm đó có thể khiến chúng bị mất.
- Tắt `fsync` hoặc dùng thiết bị lưu trữ không giữ lời hứa flush làm giảm tính bền vững.
- Hỏng thiết bị hoặc xóa nhầm bảng vẫn đòi hỏi backup, quy trình khôi phục và bảo vệ vận hành.

**WAL không thay thế backup.** Dữ liệu lâu dài quan trọng cần cả chính sách sao lưu, kiểm tra restore và quyền truy cập phù hợp.

### 3.4. Khi nào phải dùng bảng thường?

Dữ liệu thường nên dùng permanent table khi:

- Là **nguồn sự thật** của nghiệp vụ.
- Không thể tái tạo đầy đủ khi server bị crash.
- Cần chia sẻ qua nhiều connection, dịch vụ và thời gian dài.
- Cần xuất hiện trên standby/replica theo chiến lược replication hỗ trợ.
- Cần backup, kiểm toán, bảo vệ quyền và các ràng buộc quan hệ ổn định.

Ví dụ: đơn mua hàng, số dư, lịch sử thanh toán, thông tin tài khoản, kết quả báo cáo cần lưu nhiều ngày, trạng thái tác vụ mà hệ thống phải khôi phục được sau restart.

## 4. Bảng TEMP: dữ liệu trung gian riêng của một phiên

### 4.1. Tạo một bảng tạm

PostgreSQL cho phép:

```sql
CREATE TEMP TABLE temp_order_ids (
    order_id bigint PRIMARY KEY
);
```

Hoặc viết đầy đủ:

```sql
CREATE TEMPORARY TABLE temp_order_ids (
    order_id bigint PRIMARY KEY
);
```

Bảng này có tên và các cột như bảng SQL bình thường, có thể `INSERT`, `SELECT`, `UPDATE`, `DELETE`, tạo index và join với bảng khác. Nhưng **phạm vi sở hữu là session tạo bảng**.

Một ví dụ dùng bảng tạm:

```sql
INSERT INTO temp_order_ids (order_id)
SELECT order_id
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT
    o.order_id,
    o.customer_name,
    o.amount
FROM table_kinds_lab.orders AS o
JOIN temp_order_ids AS t
    ON t.order_id = o.order_id
ORDER BY o.order_id;
```

Dữ liệu của `temp_order_ids` chỉ chứa danh sách mã đơn đã được chọn trong session hiện tại. Việc thêm/sửa bảng `orders` sau đó **không tự cập nhật** các hàng đã copy sang temp.

### 4.2. Tạo bảng TEMP bằng `CREATE TABLE AS`

Nếu muốn giữ kết quả một câu truy vấn thành bảng tạm:

```sql
CREATE TEMP TABLE temp_large_orders AS
SELECT
    order_id,
    customer_name,
    amount
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT * FROM temp_large_orders ORDER BY order_id;
```

`CREATE TEMP TABLE ... AS SELECT` tạo bảng chứa dữ liệu hiện tại của kết quả query. Khác với **view**, đây là các hàng riêng, không phải định nghĩa truy vấn sẽ tự tính lại khi đọc.

Trong một workflow nhiều bước:

```text
Query gốc
   |
   v
TEMP table
   |
   +-- Bước 1: thêm cột tính toán
   +-- Bước 2: tạo index
   +-- Bước 3: JOIN và tổng hợp
   +-- Bước 4: xuất báo cáo
   |
   v
Đóng session -> bảng bị xóa
```

Nếu một kết quả chỉ dùng trong **một câu SQL**, đôi khi CTE hoặc subquery đơn giản và ít overhead hơn việc tạo một bảng tạm.

### 4.3. Bảng tạm không chia sẻ giữa các session

Mở hai kết nối PostgreSQL riêng biệt, ví dụ hai cửa sổ `psql`.

**Session A:**

```sql
SELECT pg_backend_pid() AS session_a_pid;

CREATE TEMP TABLE session_notes (
    note_id integer PRIMARY KEY,
    content text NOT NULL
);

INSERT INTO session_notes (note_id, content)
VALUES (1, 'Dữ liệu của session A');

SELECT * FROM session_notes;
```

**Session B:**

```sql
SELECT pg_backend_pid() AS session_b_pid;

SELECT * FROM session_notes;
```

B thông thường nhận lỗi `relation "session_notes" does not exist` nếu B không có đối tượng khác cùng tên. B **không thể dùng bảng tạm của A như một bảng chung**.

B có thể tự tạo một bảng tạm cùng tên:

```sql
CREATE TEMP TABLE session_notes (
    note_id integer PRIMARY KEY,
    content text NOT NULL
);

INSERT INTO session_notes (note_id, content)
VALUES (2, 'Dữ liệu của session B');
```

Hai bảng là **hai đối tượng khác nhau**. Chúng có tên giống nhau nhưng thuộc hai session riêng. Một session có thể dùng nhiều transaction trong suốt vòng đời của nó mà bảng tạm vẫn còn, tùy chính sách `ON COMMIT`.

### 4.4. Bảng tạm sống đến khi nào?

Theo mặc định, một temp table thường tồn tại **đến khi session kết thúc** hoặc có lệnh `DROP TABLE`, với điều kiện nó không được tạo bên trong transaction sau đó bị rollback.

```text
Session A mở
   |
   +-- CREATE TEMP TABLE temp_order_ids
   +-- INSERT ...
   +-- COMMIT
   +-- SELECT ... từ temp_order_ids
   +-- BEGIN / UPDATE / COMMIT
   +-- SELECT ... từ temp_order_ids
   |
Session A đóng
   |
   +-- PostgreSQL loại bỏ temp_order_ids

Session B mở mới
   |
   +-- Không thấy temp_order_ids của A
```

**Bẫy thường gặp:** ứng dụng tạo temp table trong một connection, trả connection về pool rồi truy vấn nó bằng connection khác. Kết quả là `relation does not exist` dù file log ghi rằng bước tạo bảng đã thành công.

## 5. `ON COMMIT`: ba cách kết thúc dữ liệu TEMP ở ranh giới giao dịch

PostgreSQL hỗ trợ ba chính sách cho temporary table:

| Tùy chọn | Sau `COMMIT` | Bảng có thể dùng tiếp trong cùng session? |
| --- | --- | --- |
| **`ON COMMIT PRESERVE ROWS`** | Giữ các hàng đã commit | Có |
| **`ON COMMIT DELETE ROWS`** | Xóa mọi hàng trong bảng tạm | Có, nhưng bảng trống |
| **`ON COMMIT DROP`** | Xóa luôn bảng tạm | Không, phải tạo lại |

`ON COMMIT PRESERVE ROWS` là **mặc định của PostgreSQL**. Không được mặc định theo hành vi của một DBMS khác.

### 5.1. `ON COMMIT PRESERVE ROWS`

```sql
CREATE TEMP TABLE t_preserve (
    id integer PRIMARY KEY
) ON COMMIT PRESERVE ROWS;

BEGIN;

INSERT INTO t_preserve (id) VALUES (10);

COMMIT;

SELECT * FROM t_preserve;
```

Kết quả vẫn có hàng `id = 10` trong cùng session. Nhưng khi session đóng, bảng `t_preserve` bị loại bỏ.

### 5.2. `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE t_delete (
    id integer PRIMARY KEY
) ON COMMIT DELETE ROWS;

BEGIN;

INSERT INTO t_delete (id) VALUES (20), (21);

SELECT COUNT(*) AS before_commit
FROM t_delete;

COMMIT;

SELECT COUNT(*) AS after_commit
FROM t_delete;
```

Trong transaction, `before_commit = 2`. Sau commit, bảng vẫn tồn tại nhưng `after_commit = 0`.

**Lưu ý với autocommit:** nếu không dùng `BEGIN`, mỗi lệnh `INSERT` riêng có thể commit ngay; với `ON COMMIT DELETE ROWS`, các hàng có thể bị xóa trước khi câu `SELECT` kế tiếp được chạy. Để giữ chúng cho nhiều câu SQL cùng transaction, hãy mở transaction tường minh.

### 5.3. `ON COMMIT DROP`

```sql
BEGIN;

CREATE TEMP TABLE t_drop (
    id integer PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO t_drop (id) VALUES (30);

SELECT * FROM t_drop;

COMMIT;
```

Sau commit, tên bảng `t_drop` không còn tồn tại trong session:

```sql
-- Dự kiến báo lỗi sau commit:
SELECT * FROM t_drop;
```

**Tạo `ON COMMIT DROP` ngoài transaction rõ ràng** trong phiên autocommit có thể khiến bảng bị xóa ngay khi statement `CREATE TEMP TABLE` kết thúc. Vì vậy, khi chỉ muốn dùng temp table trong một transaction, hãy mở `BEGIN` trước khi tạo.

### 5.4. Chọn chính sách nào?

- **PRESERVE ROWS:** nhiều câu SQL thuộc nhiều transaction liên tiếp trên **cùng session** cần dùng lại dữ liệu.
- **DELETE ROWS:** muốn tái sử dụng cấu trúc nhưng mỗi transaction bắt đầu với bảng rỗng.
- **DROP:** bảng chỉ cần cho một transaction và phải tự dọn đúng lúc commit.

Không dùng `ON COMMIT` với bảng thường hay UNLOGGED theo cách của TEMP table: đây là tính năng quản lý vòng đời của **temporary table**.

## 6. TEMP vẫn có transaction và rollback

Tên “tạm” không có nghĩa DML trên bảng đó nằm ngoài quy tắc giao dịch.

```sql
CREATE TEMP TABLE t_tx (
    id integer PRIMARY KEY
);

INSERT INTO t_tx (id) VALUES (1);

BEGIN;

INSERT INTO t_tx (id) VALUES (2);

ROLLBACK;

SELECT id FROM t_tx ORDER BY id;
```

Giả sử câu insert hàng 1 chạy trong autocommit trước `BEGIN`, kết quả còn **id = 1**, không có hàng 2. Bảng tạm vẫn tồn tại trong session vì được tạo trước transaction rollback.

Nếu chính câu `CREATE TEMP TABLE` xảy ra trong một transaction bị rollback:

```sql
BEGIN;

CREATE TEMP TABLE t_new (
    id integer PRIMARY KEY
);

INSERT INTO t_new VALUES (1);

ROLLBACK;
```

thì **việc tạo bảng** cũng bị rollback. Sau đó `SELECT * FROM t_new` không còn tìm thấy bảng, nếu không có đối tượng khác cùng tên.

Tương tự, có thể dùng savepoint:

```sql
CREATE TEMP TABLE t_save (
    id integer PRIMARY KEY
);

BEGIN;

INSERT INTO t_save VALUES (1);

SAVEPOINT before_optional_insert;

INSERT INTO t_save VALUES (2);

ROLLBACK TO SAVEPOINT before_optional_insert;

COMMIT;

SELECT * FROM t_save ORDER BY id;
```

Kết quả chỉ còn id 1. Hành vi transaction của TEMP không biến thành “không an toàn dữ liệu” trong một session: PostgreSQL vẫn cung cấp các cơ chế nguyên tử và hoàn tác cho các thao tác phù hợp.

## 7. UNLOGGED: bảng tồn tại chung nhưng dữ liệu không crash-safe

### 7.1. Tạo bảng UNLOGGED

```sql
CREATE UNLOGGED TABLE table_kinds_lab.import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    raw_product_code text NOT NULL,
    raw_quantity text NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, line_no)
);
```

Bảng `import_lines` được tạo trong schema `table_kinds_lab`, giống như bảng thường về phạm vi tên và khả năng truy cập giữa các session. Các phiên có quyền thích hợp có thể `SELECT`, `INSERT` và `UPDATE` trên cùng một bảng.

Nhưng từ khóa **`UNLOGGED`** thay đổi một đặc tính lưu trữ rất quan trọng: PostgreSQL **không ghi WAL cho dữ liệu của quan hệ unlogged theo cách của bảng thường**.

Ví dụ:

```sql
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (5001, 1, 'P001', '2'),
    (5001, 2, 'P002', '3'),
    (5001, 3, 'INVALID', 'not-a-number');
```

Sau commit, một session khác có thể đọc:

```sql
SELECT *
FROM table_kinds_lab.import_lines
WHERE batch_id = 5001
ORDER BY line_no;
```

UNLOGGED không giới hạn dữ liệu trong session tạo bảng như TEMP.

### 7.2. Vì sao giảm WAL có thể hữu ích?

Khi nạp một lượng lớn dữ liệu có thể tái tạo, việc tránh WAL cho nội dung bảng và các index liên quan có thể **giảm khối lượng ghi WAL**, từ đó giúp một số workload nhanh hơn hoặc giảm áp lực lên WAL storage/archiving.

Tuy nhiên:

- `UNLOGGED` **không có nghĩa mọi thao tác đều không cần I/O**.
- PostgreSQL vẫn phải ghi trang dữ liệu/index, duy trì ràng buộc, dùng CPU, khóa và quản lý bộ nhớ.
- Một số thay đổi metadata hoặc hoạt động khác vẫn liên quan đến cơ chế logging.
- Bảng unlogged vẫn có chi phí index và vacuum.
- Mức lợi ích thực tế phụ thuộc bộ dữ liệu, cấu hình, phần cứng và query; **cần đo**, không tự giả định nhanh gấp một hệ số cố định.

### 7.3. Hậu quả sau crash hoặc shutdown không sạch

Một đặc trưng bắt buộc phải biết: **UNLOGGED không có bảo đảm phục hồi dữ liệu sau crash như permanent table**.

Khi PostgreSQL khởi động lại sau crash/unclean shutdown, nội dung bảng unlogged có thể bị **truncate** theo cơ chế phục hồi. Cấu trúc bảng vẫn tồn tại nhưng dữ liệu có thể bị xóa sạch.

```text
Trước crash:
    table_kinds_lab.import_lines
    batch 5001: 100.000 hàng
              |
              v
Server crash / unclean shutdown
              |
              v
Recovery của PostgreSQL
              |
              v
Bảng UNLOGGED tồn tại, nhưng dữ liệu bị truncate
              |
              v
Ứng dụng cần nạp lại từ nguồn gốc đáng tin cậy
```

Bảng UNLOGGED **thường vẫn còn dữ liệu qua một lần restart sạch**. Không đồng nhất mọi restart với crash: cơ chế mất dữ liệu đặc biệt áp dụng cho crash/unclean shutdown.

Quan trọng hơn, **`COMMIT` vẫn hoạt động về ngữ nghĩa transaction**, nhưng nó không biến dữ liệu UNLOGGED thành dữ liệu được WAL bảo vệ khi gặp crash. Một câu `INSERT` vào UNLOGGED có thể được commit hợp lệ và vẫn bị mất sau sự cố.

### 7.4. UNLOGGED và replication

Nội dung dữ liệu UNLOGGED **không được truyền qua physical streaming replication dựa trên WAL như dữ liệu của bảng thường**. Do đó:

- Không thiết kế ứng dụng mong standby luôn có bản sao nội dung staging UNLOGGED.
- Không dựa vào physical replica của PostgreSQL làm chiến lược khôi phục dữ liệu của bảng UNLOGGED.
- Sau failover, workflow dùng staging có thể cần nạp dữ liệu lại hoặc thay đổi chiến lược triển khai.

Nếu bạn cần một bảng để báo cáo qua read replica, dữ liệu trong bảng đó phải đi theo một cơ chế replication phù hợp; permanent table là lựa chọn mặc định dễ lý giải hơn.

### 7.5. Chọn UNLOGGED chỉ khi có khả năng tái tạo

Một staging table dùng chung có thể phù hợp với UNLOGGED khi:

1. Dữ liệu gốc đã được lưu an toàn ở file, object storage, message system có khả năng phát lại hoặc một bảng permanent khác.
2. Nếu mất staging sau crash, job có thể bắt đầu lại hoặc nạp lại một cách xác định.
3. Quy trình không phụ thuộc việc đọc nội dung bảng unlogged từ physical standby.
4. Nhiều session thực sự cần dùng chung dữ liệu trung gian.
5. Lợi ích vận hành đã được đo và đáng đánh đổi rủi ro.

**Không nên chọn UNLOGGED cho đơn hàng, hóa đơn, thanh toán, nhật ký kiểm toán bắt buộc hoặc dữ liệu duy nhất không có nguồn phục hồi đáng tin cậy.**

## 8. So sánh chi tiết durability, transaction và phạm vi

Một số ngộ nhận xuất hiện khi gộp ba thuộc tính độc lập: **persistence**, **transaction semantics** và **visibility**.

### 8.1. Persistence: đối tượng còn tồn tại không?

- Permanent: tồn tại cho đến khi `DROP` hoặc một thao tác quản trị phù hợp.
- TEMP: mặc định theo vòng đời session; `ON COMMIT DROP` có thể xóa sớm hơn.
- UNLOGGED: đối tượng tồn tại lâu, ngay cả sau khi dữ liệu bị truncate do crash.

### 8.2. Transaction semantics: có rollback được không?

Cả ba kiểu bảng đều hỗ trợ nhiều thao tác DML theo transaction. Ví dụ:

```sql
BEGIN;

INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (5002, 1, 'P003', '10');

ROLLBACK;
```

Hàng vừa insert vào UNLOGGED không trở thành thay đổi đã commit sau rollback, giống ý nghĩa rollback của bảng thường.

**Bẫy khái niệm:** “không WAL-logged như bảng thường” **không đồng nghĩa** “không có transaction”. Transaction rollback khi server đang hoạt động và crash recovery sau sự cố là hai yêu cầu khác nhau.

### 8.3. Visibility: session nào được nhìn thấy?

- Permanent và UNLOGGED: nhiều session có thể truy cập cùng đối tượng, nhưng các phiên khác chỉ thấy thay đổi theo commit/snapshot/quyền.
- TEMP: session A và B có đối tượng riêng; B không thể đọc trực tiếp hàng bảng tạm của A.
- Một session có thể tạo TEMP table trùng tên với permanent table, dẫn tới quy tắc phân giải tên đặc biệt.

## 9. Bảng so sánh theo sự kiện thực tế

Giả sử đã tạo cả ba loại bảng và dữ liệu được insert/commit đầy đủ.

| Sự kiện | Permanent | TEMP mặc định | UNLOGGED |
| --- | --- | --- | --- |
| Session tạo kết nối thực hiện `COMMIT` | Giữ hàng đã commit | Giữ hàng (`PRESERVE ROWS`) | Giữ hàng đã commit |
| Session tạo đóng kết nối | Còn bảng và dữ liệu | Bảng bị loại bỏ | Còn bảng và dữ liệu |
| Session khác mở mới và có quyền | Có thể đọc | Không đọc trực tiếp TEMP của phiên cũ | Có thể đọc |
| PostgreSQL shutdown sạch và restart | Còn | Session kết thúc, mất TEMP | Thường còn |
| PostgreSQL crash/unclean shutdown | WAL recovery theo durability | Session kết thúc, mất TEMP | Dữ liệu có thể bị truncate |
| Giao dịch có `INSERT` sau đó `ROLLBACK` | Insert bị hoàn tác | Insert bị hoàn tác | Insert bị hoàn tác |
| Có thể dùng `ON COMMIT DELETE ROWS` | Không theo cơ chế temp | Có | Không theo cơ chế temp |
| Tạo index thông thường | Có | Có | Có |
| Dùng trong truy vấn `JOIN`/`GROUP BY` | Có | Có | Có |

Điểm đáng lưu ý: bảng tạm không phải là “chỉ có thể tồn tại trong một transaction”; mặc định nó có thể trải qua **nhiều transaction** trên cùng connection.

## 10. Index, thống kê và ràng buộc của ba loại bảng

### 10.1. Có thể lập index cho TEMP và UNLOGGED

Ví dụ temp:

```sql
CREATE TEMP TABLE t_index_demo (
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL,
    amount numeric(12,2) NOT NULL
);

CREATE INDEX idx_t_index_customer
    ON t_index_demo (customer_id);
```

Index thuộc dữ liệu bảng tạm của session; nó không tự trở thành index toàn database dùng chung cho các session khác.

Ví dụ unlogged:

```sql
CREATE INDEX idx_import_lines_product
    ON table_kinds_lab.import_lines (raw_product_code);
```

Index dùng để hỗ trợ truy cập bảng UNLOGGED, nhưng cũng tiêu tốn dung lượng và chi phí ghi như bất kỳ thiết kế index nào. Các index trên bảng unlogged được quản lý với đặc tính unlogged phù hợp.

**Không phải cứ tạo index là query nhanh:** nếu bảng có ít hàng, quét toàn bảng có thể rẻ hơn. Cần dùng `EXPLAIN` và đo thực tế.

### 10.2. TEMP và thống kê planner

Autovacuum thông thường **không vacuum/analyze các temporary table của session khác**, vì chỉ backend sở hữu bảng tạm mới xử lý dữ liệu đó theo ngữ cảnh thích hợp. Với TEMP lớn, người dùng nên cân nhắc:

```sql
ANALYZE t_index_demo;
```

Sau khi nạp nhiều hàng, `ANALYZE` giúp PostgreSQL có thống kê để optimizer chọn JOIN/scan/index phù hợp.

Với bảng thường và UNLOGGED, cơ chế autovacuum/analyze hoạt động theo cấu hình và workload. Bảng unlogged không nên được coi là miễn mọi công việc bảo trì chỉ vì giảm WAL.

### 10.3. Constraint vẫn quan trọng

Cả ba kiểu bảng có thể có `PRIMARY KEY`, `UNIQUE`, `NOT NULL` và `CHECK` tùy khả năng áp dụng. Ví dụ:

```sql
CREATE TEMP TABLE t_validated_lines (
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (product_code)
);
```

Ràng buộc này bảo vệ tính hợp lệ của dữ liệu trung gian ngay trong session. Tuy vậy, việc lưu dữ liệu liên quan nhiều bảng và cần khóa ngoại có thể gặp các quy tắc giới hạn theo loại relation; đừng tự động chuyển toàn bộ schema quan hệ phức tạp thành temp/unlogged mà chưa kiểm tra tính phù hợp.

## 11. TEMP table và tên trùng với bảng permanent

PostgreSQL tạo schema tạm nội bộ cho session, thường có tên dạng `pg_temp_N`. Một temporary table **có thể che** một bảng thường cùng tên khi bạn sử dụng tên không kèm schema.

Ví dụ bảng permanent:

```sql
CREATE TABLE table_kinds_lab.daily_totals (
    report_date date PRIMARY KEY,
    total_amount numeric(12,2) NOT NULL
);

INSERT INTO table_kinds_lab.daily_totals
    (report_date, total_amount)
VALUES (DATE '2026-11-14', 750000.00);
```

Trong session A, tạo bảng tạm tên `daily_totals`:

```sql
CREATE TEMP TABLE daily_totals (
    report_date date PRIMARY KEY,
    total_amount numeric(12,2) NOT NULL
);

INSERT INTO daily_totals
    (report_date, total_amount)
VALUES (DATE '2026-11-14', 123.00);
```

Nếu dùng một tên không kèm schema:

```sql
SELECT * FROM daily_totals;
```

thì kết quả có thể đến từ **TEMP table của session A**, không phải bảng `table_kinds_lab.daily_totals`.

Để truy cập rõ ràng:

```sql
-- Bảng permanent:
SELECT * FROM table_kinds_lab.daily_totals;

-- Bảng tạm của chính session hiện tại:
SELECT * FROM pg_temp.daily_totals;
```

**Hệ quả:** với lệnh ghi/xóa quan trọng, việc không ghi tên schema có thể dẫn đến thao tác nhầm đối tượng. Đặc biệt khi dùng hàm `SECURITY DEFINER` hoặc cấu hình `search_path` phức tạp, phải thiết kế phân giải tên đối tượng an toàn.

## 12. Phân biệt bảng TEMP với file tạm của bộ thực thi

Bảng tạm được tạo có chủ đích bằng `CREATE TEMP TABLE`. Nhưng PostgreSQL cũng có thể tạo **temporary disk files** để phục vụ một truy vấn khi các thao tác xử lý trung gian không đủ chỗ trong bộ nhớ.

Ví dụ những thao tác có thể tạo file tạm:

- `ORDER BY` trên tập hàng lớn.
- Một số `GROUP BY`, hash join hoặc materialization.
- Sắp xếp dữ liệu trong các công việc cần nhiều bộ nhớ.

```text
SELECT ... ORDER BY ...
          |
          +-- Đủ bộ nhớ cho sort phù hợp
          |       |
          |       +-- Xử lý trong RAM
          |
          +-- Không đủ
                  |
                  +-- Spill ra temporary disk files
                  +-- Tự quản lý theo thực thi query
```

| Đặc điểm | TEMP table | Temporary file nội bộ |
| --- | --- | --- |
| Được tạo bằng SQL? | Có, `CREATE TEMP TABLE` | Thường được tạo tự động bởi executor |
| Có tên bảng cho `SELECT`? | Có | Không |
| Dùng lại qua nhiều câu lệnh? | Có thể | Thường không |
| Có thể tạo index bằng SQL? | Có | Không theo cách của bảng SQL |
| Dùng để làm gì? | Kết quả trung gian có chủ đích | Sort/hash/spill khi query cần |

Có thể quan sát hoạt động temp file của database:

```sql
SELECT
    datname,
    temp_files,
    pg_size_pretty(temp_bytes) AS temp_bytes_pretty
FROM pg_stat_database
WHERE datname = current_database();
```

`pg_stat_database.temp_files` và `temp_bytes` không phải bộ đếm số temporary table. Chúng phản ánh các tệp tạm theo thống kê của PostgreSQL.

Tham số `work_mem` liên quan tới bộ nhớ dùng cho một số phép sort/hash; tăng nó bừa bãi có thể gây thiếu RAM khi nhiều truy vấn đồng thời và mỗi truy vấn có nhiều nút xử lý.

## 13. Dùng `pg_class.relpersistence` để kiểm tra loại bảng

PostgreSQL lưu metadata trong system catalog. Trường `pg_class.relpersistence` cho biết trạng thái persistence của relation.

| Giá trị | Loại persistence |
| --- | --- |
| `p` | Permanent |
| `u` | Unlogged |
| `t` | Temporary |

Ví dụ:

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
    'temp_order_ids',
    'import_lines'
)
  AND c.relkind IN ('r', 'p')
ORDER BY n.nspname, c.relname;
```

Cách diễn giải:

- `relkind = 'r'` thường là ordinary table.
- `relkind = 'p'` là partitioned table trong các phiên PostgreSQL hiện đại.
- `relpersistence = 'p'`, `'u'` hoặc `'t'` phân biệt ba kiểu persistence.

**Đừng nhầm `relkind` với `relpersistence`.** Hai cột nói về hai khía cạnh khác nhau của relation. Truy vấn trong `pg_class` còn có thể hiển thị một số metadata liên quan temp relation trong các session khác, nhưng **không trao quyền truy vấn dữ liệu TEMP của phiên khác**.

### 13.1. Xác định schema TEMP của phiên

Trong session đã tạo temp table:

```sql
SELECT pg_backend_pid() AS backend_pid,
       pg_my_temp_schema() AS temp_schema_oid;
```

`pg_my_temp_schema()` trả về OID của schema tạm thuộc session hiện tại (hoặc 0 khi chưa có schema temp tương ứng). Có thể xem tên schema:

```sql
SELECT nspname
FROM pg_namespace
WHERE oid = pg_my_temp_schema();
```

Đối với code ứng dụng, đừng dựa vào việc tự đoán `pg_temp_N`; dùng alias `pg_temp` hoặc tên bảng phù hợp trong chính session.

### 13.2. Kiểm tra size không thay thế durability

```sql
SELECT
    pg_size_pretty(
        pg_total_relation_size('table_kinds_lab.orders')
    ) AS orders_total_size;
```

Hàm trên có thể giúp xem tổng kích thước quan hệ và thành phần liên quan ở trạng thái hiện tại. Tuy nhiên, một bảng rất nhỏ vẫn có thể là dữ liệu nghiệp vụ quan trọng, còn một UNLOGGED lớn vẫn không an toàn trước crash. **Kích thước không xác định loại persistence cần chọn**.

## 14. Workflow nhập dữ liệu: staging TEMP hay UNLOGGED?

Giả sử mỗi đêm hệ thống nhận một tệp chứa nhiều triệu dòng mã sản phẩm và số lượng. Dữ liệu cuối cùng phải được lưu bền vững, nhưng bước phân tích có thể tái tạo từ tệp nguồn.

Quy trình có thể như sau:

```text
Tệp nguồn bền vững / object storage
           |
           v
Import raw lines
           |
           +-- Nếu chỉ một session: TEMP staging
           |
           +-- Nếu nhiều worker cần cùng đọc: UNLOGGED staging
           |
           v
Validate / transform / deduplicate
           |
           v
Commit vào PERMANENT tables
           |
           v
Đánh dấu batch thành công ở hệ thống bền vững
           |
           v
Dọn staging theo chính sách
```

**Câu hỏi quyết định:** staging có cần được chia sẻ giữa các connection không?

- Nếu **không**, TEMP có thể đơn giản hơn vì tự dọn theo session.
- Nếu **có** và dữ liệu tái tạo được, UNLOGGED có thể phù hợp.
- Nếu **có** nhưng mất staging làm mất dữ liệu nghiệp vụ hoặc khó phục hồi, permanent staging vẫn an toàn hơn.

### 14.1. Nạp dữ liệu vào UNLOGGED staging

Bảng `table_kinds_lab.import_lines` đã được tạo ở trên. Có thể nạp mẫu:

```sql
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES
    (6001, 1, 'P001', '2'),
    (6001, 2, 'P002', '5'),
    (6001, 3, 'P003', 'invalid-number');
```

Các cột `raw_quantity text` cố ý giữ giá trị thô để bước xác minh có thể phát hiện dòng sai mà không làm toàn bộ lệnh import thất bại vì ép kiểu ngay khi đọc.

Để xử lý một batch:

```sql
SELECT
    batch_id,
    line_no,
    raw_product_code,
    raw_quantity
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
ORDER BY line_no;
```

Hai session đều có thể đọc batch đã commit.

### 14.2. Chọn phần dữ liệu hợp lệ trong một TEMP table

Trong một session xử lý:

```sql
BEGIN;

CREATE TEMP TABLE valid_import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (batch_id, line_no)
) ON COMMIT DROP;

INSERT INTO valid_import_lines
    (batch_id, line_no, product_code, quantity)
SELECT
    batch_id,
    line_no,
    raw_product_code,
    raw_quantity::integer
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
  AND raw_quantity ~ '^[1-9][0-9]*$';

SELECT *
FROM valid_import_lines
ORDER BY line_no;

COMMIT;
```

Ví dụ sử dụng regex để lọc những chuỗi là số nguyên dương trước khi cast. Trên dữ liệu thực, còn phải kiểm tra giá trị có nằm trong phạm vi `integer`, mã sản phẩm có hợp lệ, dòng trùng/thiếu, và chính sách xử lý lỗi. Ngay cả chuỗi chỉ chứa chữ số cũng có thể **overflow** khi cast sang `integer` nếu quá dài.

Với `ON COMMIT DROP`, bảng `valid_import_lines` tự biến mất sau commit. Nếu cần tiếp tục xử lý qua transaction khác trên cùng session, dùng `PRESERVE ROWS` thay vì `DROP`.

### 14.3. Ghi kết quả cuối vào bảng thường

Ví dụ bảng kết quả bền vững:

```sql
CREATE TABLE table_kinds_lab.accepted_import_lines (
    batch_id bigint NOT NULL,
    line_no integer NOT NULL,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (batch_id, line_no)
);
```

Trong một transaction mới, có thể tạo và dùng bảng tạm để quyết định dữ liệu nào được ghi vào bảng thật:

```sql
BEGIN;

CREATE TEMP TABLE to_accept
ON COMMIT DROP
AS
SELECT
    batch_id,
    line_no,
    raw_product_code AS product_code,
    raw_quantity::integer AS quantity
FROM table_kinds_lab.import_lines
WHERE batch_id = 6001
  AND raw_quantity ~ '^[1-9][0-9]*$';

INSERT INTO table_kinds_lab.accepted_import_lines
    (batch_id, line_no, product_code, quantity)
SELECT
    batch_id,
    line_no,
    product_code,
    quantity
FROM to_accept
WHERE true
ON CONFLICT (batch_id, line_no) DO NOTHING;

COMMIT;
```

`ON CONFLICT DO NOTHING` là **chính sách minh họa** để tránh thêm trùng một cặp `batch_id + line_no`. Trong dự án thực, cần quyết định rõ dữ liệu trùng là lỗi cần báo hay một thao tác retry hợp lệ.

Với batch lớn, cần thiết kế kiểm tra tính đầy đủ, invalid rows, idempotency, transaction size và giới hạn tài nguyên trước khi triển khai.

### 14.4. Điều gì nếu crash ở giữa import?

- Nếu dữ liệu trong UNLOGGED bị truncate, cần **đọc lại từ nguồn gốc** đã lưu an toàn.
- Nếu một transaction đang ghi vào bảng thường chưa commit, PostgreSQL rollback phần chưa commit theo cơ chế recovery phù hợp.
- Nếu các dòng đã commit vào bảng permanent, chúng có vòng đời bền vững theo cấu hình database.
- Bảng TEMP đang mở trong phiên xử lý biến mất khi kết nối bị chấm dứt.

Vì thế, trạng thái “file nào đã được xử lý thành công” nếu không thể tái tạo nên được ghi vào **bảng thường hoặc hệ thống trạng thái bền vững**, không chỉ nằm trong UNLOGGED staging.

## 15. `COPY` và `\copy` khi nạp dữ liệu staging

PostgreSQL có `COPY` để nhập/xuất dữ liệu hàng loạt. `psql` có meta-command `\copy` để xử lý file phía client.

Ví dụ nạp file CSV từ máy chạy `psql`:

```text
\copy table_kinds_lab.import_lines (batch_id, line_no, raw_product_code, raw_quantity) FROM 'batch_6002.csv' WITH (FORMAT csv, HEADER true)
```

Dòng trên là meta-command của **psql** và giả định file CSV đã có các cột đúng thứ tự. `\copy` đọc file từ môi trường client, trong khi những biến thể `COPY ... FROM '/server/path.csv'` do PostgreSQL server xử lý file ở máy server và yêu cầu quyền phù hợp.

Lựa chọn TEMP hay UNLOGGED **không tự quyết định** dùng `COPY` hay `\copy`. Hai câu hỏi độc lập:

- Bảng đích cần vòng đời/phạm vi/durability gì?
- File nguồn nằm ở máy client hay server, và có quyền đọc ở đâu?

Không dùng `COPY` từ file server trên môi trường không được cấp quyền, và không coi việc giảm WAL là lý do bỏ kiểm tra dữ liệu đầu vào.

## 16. Đổi bảng thường thành UNLOGGED hoặc ngược lại

PostgreSQL có các dạng lệnh đổi persistence của bảng phù hợp:

```sql
-- Chuyển bảng từ logged sang unlogged:
ALTER TABLE table_kinds_lab.some_staging
    SET UNLOGGED;

-- Chuyển trở lại logged:
ALTER TABLE table_kinds_lab.some_staging
    SET LOGGED;
```

**Các lệnh trên chỉ minh họa cú pháp**; `some_staging` chưa được tạo trong bài. Không chạy nguyên xi nếu không có bảng được chọn có chủ đích.

Những thay đổi này không phải công tắc hiệu năng miễn phí:

- Có thể yêu cầu **rewrite** dữ liệu và index phù hợp.
- Có thể cần khóa mạnh trên bảng trong quá trình thay đổi.
- Có tác động đến replication/durability.
- Có thể có hạn chế theo loại relation và quan hệ phụ thuộc.
- Phải đánh giá kích thước bảng, phiên bản PostgreSQL, thời gian bảo trì, quyền và phương án phục hồi.

**Không chuyển bảng nghiệp vụ đang chạy sang UNLOGGED chỉ để thử tăng tốc**, rồi tin rằng đổi lại `SET LOGGED` sẽ tự phục hồi dữ liệu đã mất trong crash trước đó.

Với TEMP table, không có ý nghĩa chuyển nó thành một bảng permanent đơn giản bằng cùng cú pháp persistence ở trên. Để giữ dữ liệu, cách thường rõ ràng hơn là **tạo bảng permanent và chèn dữ liệu từ TEMP trong lúc session còn tồn tại**.

Ví dụ:

```sql
-- Giả định temp_large_orders đang tồn tại trong session.
CREATE TABLE table_kinds_lab.saved_large_orders AS
SELECT * FROM temp_large_orders;
```

Bảng mới là permanent theo mặc định. Nhưng `CREATE TABLE AS` **không tự sao chép mọi ràng buộc/index/quyền** mà một bảng sản xuất cần; phải bổ sung thiết kế schema thích hợp.

## 17. Khi nào TEMP tốt hơn một CTE hoặc materialized view?

Ba công cụ này thường bị dùng lẫn vì đều có thể chứa “kết quả trung gian”.

### 17.1. CTE cho logic trong một câu SQL

```sql
WITH high_value AS (
    SELECT order_id, amount
    FROM table_kinds_lab.orders
    WHERE amount >= 200000
)
SELECT COUNT(*) AS order_count,
       COALESCE(SUM(amount), 0) AS total_amount
FROM high_value;
```

CTE không tạo một bảng TEMP có thể dùng độc lập trong các statement tiếp theo. PostgreSQL có thể inline hoặc materialize CTE tùy cấu trúc truy vấn, phiên bản và lựa chọn tối ưu; **không coi CTE luôn tương đương temp table vật lý**.

### 17.2. TEMP khi cần nhiều statement cùng một tập trung gian

Dùng TEMP khi cần:

- Nạp một tập ID lớn, tạo index và JOIN nhiều lần.
- Có nhiều bước xử lý khác nhau trong cùng backend/session.
- Muốn chủ động giữ dữ liệu trung gian trong session rồi tự dọn.

Nhưng mỗi lần tạo/drop bảng tạm có overhead về metadata và catalog. Với nhiều kết nối tạo hàng nghìn bảng tạm liên tục, cần đo chi phí, không tự giả định TEMP luôn tốt hơn CTE.

### 17.3. Materialized view có vòng đời khác

Materialized view lưu kết quả truy vấn tại thời điểm tạo/refresh như một đối tượng lâu dài:

```sql
CREATE MATERIALIZED VIEW table_kinds_lab.order_summary AS
SELECT
    COUNT(*) AS order_count,
    COALESCE(SUM(amount), 0) AS total_amount
FROM table_kinds_lab.orders;
```

Sau khi bảng nguồn thay đổi, materialized view không tự cập nhật liên tục; cần:

```sql
REFRESH MATERIALIZED VIEW table_kinds_lab.order_summary;
```

Materialized view phù hợp khi muốn lưu kết quả đọc lặp lại qua nhiều session và chủ động quản lý refresh. Nó **không phải TEMP table** chỉ vì dữ liệu bên trong được tính từ một query.

## 18. Connection pool và transaction pooling: cạm bẫy thực tế

Một service Java thường sử dụng connection pool. Một request gọi database qua connection A, trả lại pool; request sau có thể dùng A hoặc một connection khác.

```text
HTTP request 1
    |
    v
Connection A: CREATE TEMP TABLE report_rows
    |
    v
Trả Connection A về pool

HTTP request 2
    |
    +-- Nếu lấy Connection A: report_rows có thể còn
    |
    +-- Nếu lấy Connection B: report_rows không tồn tại
```

Vì vậy, **đừng thiết kế một workflow qua nhiều request dựa vào bảng TEMP còn tồn tại** nếu không có đảm bảo rõ ràng về cùng backend/session.

### 18.1. Session pooling và transaction pooling

Với một pooler như PgBouncer:

- **Session pooling:** kết nối server có thể được giữ cho một client session trong suốt session đó.
- **Transaction pooling:** kết nối server có thể được trả về pool và cấp cho client khác sau mỗi transaction.

Trong transaction pooling, không thể mặc nhiên tin rằng **TEMP table với `PRESERVE ROWS`**, prepared statement theo session, `SET` lâu dài hoặc advisory lock theo session luôn có mặt ở transaction kế tiếp của client.

Các tính năng tương thích có thể phụ thuộc phiên bản và cấu hình pooler. Nguyên tắc thiết kế an toàn là **chỉ sử dụng trạng thái mà chế độ pooling thực tế cam kết hỗ trợ**.

### 18.2. Giữ TEMP trong một transaction

Nếu dùng pooler cấp lại backend theo transaction, một chiến lược hợp lý cho tác vụ ngắn là tạo, sử dụng rồi xóa bảng tạm **bên trong cùng transaction**:

```sql
BEGIN;

CREATE TEMP TABLE selected_ids (
    order_id bigint PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO selected_ids (order_id)
SELECT order_id
FROM table_kinds_lab.orders
WHERE amount >= 200000;

SELECT o.order_id, o.amount
FROM table_kinds_lab.orders AS o
JOIN selected_ids AS s USING (order_id);

COMMIT;
```

Tất cả câu SQL phải thực hiện qua **đúng connection** trong transaction; driver/framework không được âm thầm đổi connection giữa các bước. Điều này cũng không có nghĩa temp table được chia sẻ sang request khác.

### 18.3. Dọn trạng thái đúng cách

Trong cùng session, có thể xóa bảng tạm rõ ràng:

```sql
DROP TABLE IF EXISTS pg_temp.selected_ids;
```

`DISCARD TEMP` có thể dùng để dọn các đối tượng tạm phù hợp trong một session do bạn kiểm soát:

```sql
DISCARD TEMP;
```

`DISCARD ALL` dọn nhiều loại trạng thái session hơn, nhưng không được dùng trong transaction block và có chi phí. Không tự chạy trong mọi request nếu chưa xem yêu cầu của connection pool.

Nếu workflow thật cần tiếp tục qua connection khác, nên lưu trạng thái vào **bảng thường** hoặc vào một cơ chế lưu trữ chia sẻ có vòng đời phù hợp.

## 19. Những câu hỏi vận hành về crash, backup và replication

### 19.1. Restart sạch khác crash

| Tình huống | Bảng thường | UNLOGGED | TEMP |
| --- | --- | --- | --- |
| Dừng PostgreSQL sạch và khởi động lại | Dữ liệu đã commit còn | Dữ liệu thường còn | Session cũ mất, bảng tạm mất |
| Crash/unclean shutdown và recovery | Theo WAL/durability | Dữ liệu bị truncate theo quy tắc recovery | Session cũ mất, bảng tạm mất |
| Client ngắt kết nối | Không mất dữ liệu đã commit | Không mất dữ liệu đã commit chỉ vì ngắt kết nối | Bảng của session đó bị xóa |

Đây là lý do không nên dùng từ “khởi động lại” chung chung khi thảo luận sự cố UNLOGGED. Cần biết PostgreSQL đã shutdown **sạch** hay **không sạch**.

### 19.2. Backup của bảng UNLOGGED

WAL-based recovery/physical replication **không cung cấp bảo vệ đầy đủ cho nội dung UNLOGGED**. Một số quy trình sao lưu logic có thể xuất dữ liệu unlogged tùy công cụ và tùy chọn, nhưng không được coi đó là bằng chứng mọi loại backup/replica đều có dữ liệu.

Ví dụ `pg_dump` có tùy chọn `--no-unlogged-table-data` để bỏ dữ liệu của UNLOGGED table. Vì vậy, khi làm kế hoạch backup/restore:

- Xác định loại backup (logical dump, physical backup, backup do nhà cung cấp quản lý).
- Xác nhận tùy chọn có hoặc không xuất nội dung unlogged.
- Thử khôi phục ở môi trường riêng để biết dữ liệu thực sự còn những gì.
- Coi nguồn import gốc là nơi đáng tin cậy để nạp lại staging.

### 19.3. Replication không phải backup

Một primary và standby không thay thế bản backup lịch sử để khôi phục khi có lỗi xóa dữ liệu, lỗi ứng dụng hoặc thao tác quản trị nhầm. Với UNLOGGED, nội dung không được physical streaming replication như bảng thường, càng cần thiết kế cách phát lại staging.

### 19.4. Monitoring

Với bảng UNLOGGED làm staging, nên theo dõi:

- Số batch đang xử lý.
- Số dòng đầu vào, hợp lệ và bị loại.
- Dung lượng staging và chỉ mục.
- Dữ liệu được nạp lại từ nguồn nào sau crash.
- Các job đang dở dang cần retry.
- Tác động tới CPU/I/O và hiệu năng câu SQL.

Với TEMP table, theo dõi thêm số connection đồng thời, mức độ tạo/drop temp, dung lượng tạm và tình trạng bloat/thống kê nếu workload phức tạp.

## 20. Hiệu năng: có nên đổi mọi bảng sang UNLOGGED hoặc TEMP?

**Không.** Chọn loại bảng chỉ là một quyết định trong tối ưu dữ liệu.

### 20.1. Chi phí tổng thể cần đo

Một truy vấn hoặc batch tiêu tốn:

```text
Tổng thời gian
  ≈ đọc nguồn
   + kiểm tra/ràng buộc
   + ghi dữ liệu và index
   + WAL/flush (nếu áp dụng)
   + xử lý JOIN/sort/aggregate
   + chờ khóa, I/O, CPU
   + tải dữ liệu qua mạng
```

Dùng UNLOGGED có thể giảm một phần chi phí WAL; nó không làm biến mất các phần còn lại.

### 20.2. So sánh đúng ba biến thể

Nếu mục tiêu là nạp 2 triệu dòng staging, có thể kiểm tra trên cùng môi trường:

| Biến thể | Bảng đích | Điều cần ghi |
| --- | --- | --- |
| A | Permanent | Thời gian import, WAL generated, CPU/I/O, chi phí index |
| B | UNLOGGED | Thời gian import, I/O, tác động khác, kế hoạch nạp lại |
| C | TEMP | Thời gian import trong một session, overhead, giới hạn sử dụng nhiều phiên |

Cần giữ bộ dữ liệu, chỉ mục, schema constraints, số worker và phương pháp nạp giống nhau khi có thể. Cân nhắc rằng TEMP và UNLOGGED có **ngữ nghĩa khác**, nên một biến thể có thời gian chạy tốt nhưng không đáp ứng chia sẻ/durability sẽ không phải lựa chọn hợp lệ.

### 20.3. Index trước hay sau khi nạp?

Với staging lớn có thể tái tạo, đôi khi nạp dữ liệu vào bảng ít index rồi tạo index phục vụ bước xử lý sau có lợi hơn so với duy trì nhiều index trong mọi lệnh insert. Nhưng:

- Index có chi phí tạo và tiêu thụ I/O.
- Có thể cần kiểm tra ràng buộc và tính nhất quán.
- Bảng permanent/UNLOGGED đang được dùng đồng thời cần xem thời điểm khóa/DDL.
- Với TEMP chỉ một session dùng, việc tạo index phải đáp ứng số lần JOIN/truy vấn còn lại.

Không có quy tắc “luôn tạo index sau import” đúng cho mọi workload.

## 21. Lựa chọn loại bảng: những tình huống cụ thể

| Tình huống | Loại bảng thường phù hợp | Lý do |
| --- | --- | --- |
| Đơn hàng đã thanh toán | **Permanent** | Không thể chấp nhận mất sau crash |
| Lịch sử kiểm toán bắt buộc | **Permanent** | Cần độ bền và quy trình backup |
| Cache kết quả chỉ dùng trong một session báo cáo | **TEMP** | Tự dọn khi session kết thúc |
| Tập ID trung gian dùng qua ba câu SELECT trong cùng transaction | **TEMP ON COMMIT DROP** | Dữ liệu chỉ cần đến lúc commit |
| Bảng scratch cần xóa hàng sau mỗi transaction | **TEMP ON COMMIT DELETE ROWS** | Giữ schema, xóa hàng khi commit |
| File import có thể nạp lại, nhiều worker cùng đọc | **UNLOGGED**, nếu chấp nhận rủi ro | Chia sẻ giữa session, giảm một phần WAL |
| File import duy nhất chưa lưu nơi khác | **Permanent** | Nếu mất staging sẽ mất nguồn dữ liệu |
| Báo cáo kết quả cần mở từ ứng dụng khác sau một ngày | **Permanent** hoặc lưu trữ bền vững khác | TEMP không tồn tại qua session |
| Dữ liệu trung gian chỉ dùng trong một câu SQL | CTE/subquery | Không cần tạo bảng riêng |
| Dữ liệu cần có trên physical standby | **Permanent** | UNLOGGED không truyền dữ liệu như bảng thường |
| Thống kê tổng hợp cần refresh theo lịch | Permanent/materialized view tùy thiết kế | Dữ liệu có vòng đời và chính sách cập nhật riêng |
| Một request có connection không cố định giữa các bước | Không dựa vào TEMP xuyên connection | Bảng TEMP thuộc một session cụ thể |

Những lựa chọn này là hướng dẫn thiết kế, không thay thế đánh giá quyền, ràng buộc, workload và kế hoạch vận hành.

## 22. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hiểu đúng |
| --- | --- |
| “TEMP là dữ liệu sống trong một transaction.” | TEMP mặc định sống theo **session**, có thể qua nhiều transaction |
| “`COMMIT` luôn xóa TEMP.” | PostgreSQL mặc định `ON COMMIT PRESERVE ROWS` |
| “`ON COMMIT DROP` có thể tạo ngoài transaction rồi dùng sau.” | Trong autocommit bảng có thể bị drop ngay sau statement tạo |
| “TEMP không dùng được transaction.” | DML/DDL phù hợp trên TEMP vẫn có `COMMIT`/`ROLLBACK` |
| “UNLOGGED là TEMP nhưng không tự xóa.” | UNLOGGED là bảng chung, có ngữ nghĩa persistence khác TEMP |
| “UNLOGGED mất dữ liệu sau mọi restart.” | Dữ liệu thường tồn tại qua restart sạch, nhưng bị truncate sau crash/unclean shutdown |
| “UNLOGGED nhanh nên thích hợp lưu số dư.” | Thiếu crash durability và replication của bảng thường; không phù hợp dữ liệu quan trọng |
| “Dữ liệu UNLOGGED đã `COMMIT` thì bảo đảm phục hồi qua crash.” | Commit không biến dữ liệu unlogged thành WAL-protected |
| “TEMP không thể có index hoặc PK.” | Có thể có index và nhiều ràng buộc phù hợp |
| “Autovacuum luôn cập nhật thống kê của mọi TEMP.” | TEMP thường cần `ANALYZE` chủ động khi lớn |
| “File tạm của sort cũng là TEMP table.” | Temporary disk files nội bộ không phải bảng có tên SQL |
| “Một session tạo TEMP, session khác đọc được nếu biết tên `pg_temp_N`.” | Dữ liệu TEMP thuộc session, không chia sẻ trực tiếp |
| “Connection pool trả connection về là session kết thúc.” | Pool có thể giữ backend và tái sử dụng trạng thái |
| “`CREATE TABLE AS SELECT` giữ mọi constraint/index của nguồn.” | Tạo bảng kết quả, không tự sao chép đầy đủ mọi đặc tính schema |
| “WAL bảo vệ cả dữ liệu UNLOGGED trên replica.” | Dữ liệu UNLOGGED không được physical replication bằng WAL như bảng thường |
| “Không thấy TEMP sau restart chứng minh crash đã xóa dữ liệu permanent.” | TEMP biến mất khi session kết thúc; không phản ánh độ bền bảng permanent |

## 23. Bài tập thực hành và đáp án

### Bài 1. Chọn bảng lưu kết quả thanh toán

Một giao dịch thanh toán đã được xác nhận, dữ liệu phải tồn tại sau khi ứng dụng ngắt kết nối và PostgreSQL phục hồi từ crash. Chọn kiểu bảng nào?

**Đáp án:** permanent table với transaction, cấu hình WAL/durability, backup và replication phù hợp. TEMP hay UNLOGGED không đáp ứng yêu cầu phục hồi dữ liệu quan trọng như vậy.

### Bài 2. Hai phiên cùng tạo `TEMP t`

Session A:

```sql
CREATE TEMP TABLE t (id integer);
INSERT INTO t VALUES (1);
```

Session B:

```sql
CREATE TEMP TABLE t (id integer);
INSERT INTO t VALUES (2);
```

**Hỏi:** A chạy `SELECT * FROM t` sẽ thấy gì?

**Đáp án:** A đọc bảng tạm của **chính A**, có hàng 1; không tự thấy hàng 2 ở bảng của B.

### Bài 3. Commit có xóa bảng tạm mặc định không?

```sql
CREATE TEMP TABLE t_default (id integer);
INSERT INTO t_default VALUES (10);
COMMIT;
SELECT * FROM t_default;
```

**Đáp án:** mặc định PostgreSQL là `ON COMMIT PRESERVE ROWS`. Nếu câu insert đã commit trong chế độ autocommit, bảng và hàng 10 vẫn tồn tại trong session. Lệnh `COMMIT` tường minh ngoài transaction có thể báo cảnh báo không có transaction, nhưng không làm bảng tạm biến mất.

### Bài 4. Chọn `ON COMMIT DELETE ROWS`

```sql
CREATE TEMP TABLE t_clean (id integer)
ON COMMIT DELETE ROWS;

BEGIN;
INSERT INTO t_clean VALUES (1), (2);
COMMIT;
SELECT COUNT(*) FROM t_clean;
```

**Đáp án:** `0`. Bảng còn tồn tại, nhưng hàng bị xóa khi transaction commit.

### Bài 5. Chọn `ON COMMIT DROP`

```sql
BEGIN;
CREATE TEMP TABLE t_once (id integer)
ON COMMIT DROP;
INSERT INTO t_once VALUES (5);
COMMIT;
```

**Hỏi:** sau commit có thể `SELECT * FROM t_once` không?

**Đáp án:** không, bảng đã bị drop theo chính sách của nó.

### Bài 6. UNLOGGED có phải không hỗ trợ rollback?

```sql
BEGIN;
INSERT INTO table_kinds_lab.import_lines
    (batch_id, line_no, raw_product_code, raw_quantity)
VALUES (7001, 1, 'P123', '4');
ROLLBACK;
```

**Đáp án:** rollback vẫn hoàn tác insert. UNLOGGED ảnh hưởng **WAL/crash recovery**, không xóa bỏ transaction semantics.

### Bài 7. Sau crash, bảng UNLOGGED có còn tên không?

**Đáp án:** có thể vẫn tồn tại cấu trúc/table definition, nhưng nội dung bảng unlogged bị truncate khi PostgreSQL phục hồi từ một shutdown không sạch. Ứng dụng phải có kế hoạch nạp lại nếu muốn tiếp tục xử lý.

### Bài 8. `pg_class.relpersistence = 'u'` cho biết gì?

**Đáp án:** đó là một relation kiểu **unlogged**. Giá trị `'p'` là permanent và `'t'` là temporary. Không nên nhầm cột này với `relkind`, vốn mô tả loại đối tượng quan hệ.

### Bài 9. Một báo cáo dùng TEMP table trong connection A, bước tiếp theo chạy ở connection B và báo không tìm thấy bảng

**Nguyên nhân:** bảng tạm thuộc A, B không dùng được. Cần giữ các bước trong cùng backend/session hoặc dùng lưu trữ chia sẻ khi workflow phải đi qua nhiều connection.

### Bài 10. Vì sao `pg_stat_database.temp_bytes` tăng nhưng không ai tạo TEMP table?

**Đáp án:** PostgreSQL có thể tạo temporary disk files để spill sort/hash trong quá trình thực thi query. Chúng không phải TEMP table SQL.

### Bài 11. Chọn loại bảng cho staging import

File CSV đã được lưu ở object storage, có thể nạp lại bất kỳ lúc nào. Ba worker trên cùng primary cần đọc chung batch staging; dữ liệu không cần ở standby. Có thể cân nhắc bảng nào?

**Đáp án:** UNLOGGED có thể phù hợp nếu chấp nhận việc dữ liệu staging bị truncate sau crash và đã thiết kế retry/reload. Permanent vẫn là lựa chọn hợp lệ nếu ưu tiên đơn giản và bảo vệ tốt hơn; TEMP không phù hợp để chia sẻ giữa các worker khác session.

### Bài 12. Bảng TEMP chứa 3 triệu hàng, planner chọn kế hoạch xấu

**Gợi ý:** sau khi nạp dữ liệu có thể chạy `ANALYZE` trên bảng TEMP, kiểm tra index và `EXPLAIN`. Đừng chờ autovacuum cập nhật thống kê bảng tạm của session như trên bảng permanent.

## 24. Mẫu quyết định trước khi tạo bảng

Một checklist thực dụng:

```text
Tên tập dữ liệu:
    _________________________________________

Tập dữ liệu tồn tại đến:
    [ ] Kết thúc một SQL
    [ ] COMMIT / ROLLBACK
    [ ] Kết thúc một session
    [ ] Kết thúc một batch/job
    [ ] Dài hạn

Ai đọc?
    [ ] Một connection
    [ ] Nhiều connection
    [ ] Nhiều service
    [ ] Read replica

Có thể tái tạo hoàn toàn sau crash?
    [ ] Có, từ nguồn bền vững
    [ ] Không
    [ ] Chưa rõ

Yêu cầu bảo vệ dữ liệu:
    [ ] Cần crash durability
    [ ] Chấp nhận mất staging
    [ ] Cần backup/restore
    [ ] Cần replication

Quy trình vận hành:
    [ ] Có người/worker chịu trách nhiệm dọn
    [ ] Có retry/idempotency
    [ ] Có thống kê và index phù hợp
    [ ] Có benchmark, theo dõi WAL/I/O/CPU
    [ ] Có xác nhận connection pooling

Loại bảng được chọn:
    [ ] Permanent
    [ ] TEMP + chính sách ON COMMIT: _________
    [ ] UNLOGGED + kế hoạch reload: __________
```

Nếu chưa biết chắc dữ liệu **có thể tái tạo sau crash** hay **cần chia sẻ giữa session**, đừng vội dùng UNLOGGED hoặc TEMP như một “mẹo tối ưu”.

## 25. Tổng kết

PostgreSQL cung cấp ba cách tổ chức bảng với những đánh đổi rõ ràng:

- **Permanent table** là mặc định cho dữ liệu bền vững: đối tượng và dữ liệu đã commit tồn tại qua các phiên/restart, có cơ chế crash recovery dựa trên WAL trong điều kiện cấu hình phù hợp.
- **TEMP table** là công cụ lưu kết quả trung gian của **một session**. Bảng có thể qua nhiều transaction và mặc định `ON COMMIT PRESERVE ROWS`; `DELETE ROWS` và `DROP` cho phép kết thúc dữ liệu/bảng ở commit.
- **UNLOGGED table** tồn tại và được chia sẻ như một bảng chung, nhưng dữ liệu **không được WAL bảo vệ qua crash và không được physical streaming replication như bảng thường**. Nó phù hợp nhất với dữ liệu staging có thể nạp lại.
- **Transaction và độ bền là hai khái niệm khác nhau.** TEMP/UNLOGGED vẫn có `COMMIT`, `ROLLBACK`, index và nhiều ràng buộc; nhưng không cung cấp cùng vòng đời và phục hồi như bảng permanent.
- **TEMP table khác temporary disk file**, và khác cả CTE/materialized view. Chỉ tạo bảng khi thật sự cần dữ liệu có tên và dùng lại nhiều bước.
- **Kiểm tra loại bảng bằng `pg_class.relpersistence`** khi cần: `p`, `t`, `u` tương ứng permanent, temporary và unlogged.
- **Connection pooling, tên bảng trùng nhau và `search_path`** có thể gây lỗi khó phát hiện nếu không hiểu phạm vi session.
- **Đo hiệu năng và đánh giá chi phí phục hồi** trước khi chọn UNLOGGED: giảm WAL không có giá trị nếu dữ liệu phải được bảo vệ qua mọi sự cố.

Câu hỏi cuối cùng để quyết định không phải “bảng nào nhanh nhất?”, mà là: **tập dữ liệu này cần tồn tại bao lâu, ai cần truy cập, có thể chấp nhận mất sau sự cố không, và hệ thống sẽ phục hồi thế nào?** Chọn đúng loại bảng theo các câu hỏi đó giúp thiết kế PostgreSQL vừa rõ ràng vừa phù hợp yêu cầu vận hành.
