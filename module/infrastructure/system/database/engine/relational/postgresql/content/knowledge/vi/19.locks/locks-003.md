# SELECT FOR UPDATE, FOR NO KEY UPDATE, FOR SHARE, FOR KEY SHARE trong PostgreSQL

Khi nhiều transaction cùng đọc và sửa một hàng, **MVCC** giúp các câu `SELECT` thông thường nhìn thấy dữ liệu nhất quán mà không cần chờ mọi phép ghi. Nhưng MVCC không trả lời hết các câu hỏi nghiệp vụ: nếu hai người cùng muốn trừ tồn kho, nếu một phiên chuẩn bị xóa khách hàng còn phiên khác muốn tạo đơn tham chiếu khách hàng đó, hoặc nếu nhiều worker cùng chọn một job, **transaction nào được phép đi tiếp và transaction nào phải chờ?**

PostgreSQL cung cấp bốn **chế độ khóa hàng** (*row-level lock modes*) để thể hiện mức độ bảo vệ cần thiết:

- `FOR UPDATE` — khóa mạnh nhất trong nhóm, xung đột với cả bốn chế độ.
- `FOR NO KEY UPDATE` — khóa cho cập nhật không đổi khóa định danh/khóa liên quan đến foreign key; cho phép một số phép đọc giữ khóa tham chiếu.
- `FOR SHARE` — nhiều phiên có thể cùng giữ khóa chia sẻ để đọc, nhưng không cho writer cập nhật hàng đó khi khóa còn giữ.
- `FOR KEY SHARE` — khóa chia sẻ yếu hơn, chủ yếu bảo vệ hàng khỏi bị xóa hoặc thay đổi giá trị khóa quan trọng; cho phép cập nhật các cột không phải khóa trong nhiều trường hợp.

Đây là một bài học về **khóa hàng**, không phải bốn loại snapshot. Chúng hoạt động cùng MVCC, transaction isolation, table-level locks, foreign key và cơ chế phát hiện deadlock.

Bạn sẽ thực hành bằng **hai phiên PostgreSQL**, đọc ma trận xung đột, dùng `NOWAIT`/`SKIP LOCKED`, khóa đúng bảng qua `OF`, quan sát transaction bị chặn, xử lý lỗi trong JDBC và nhận biết trường hợp **không nên dùng khóa hàng thay cho unique constraint**.

## 1. Vì sao SELECT thông thường chưa đủ?

Giả sử một cửa hàng có sản phẩm còn 5 đơn vị. Hai worker cùng thực hiện:

~~~text
Worker A                           Worker B
---------------------------------  ---------------------------------
SELECT stock_qty → 5               SELECT stock_qty → 5
Xác nhận còn hàng                  Xác nhận còn hàng
Chuẩn bị trừ 4                     Chuẩn bị trừ 4
UPDATE stock_qty = 1               UPDATE stock_qty = 1
~~~

Nếu ứng dụng đọc 5, tính trước số mới 1 rồi ghi `SET stock_qty = 1` không có điều kiện/kiểm tra phù hợp, hệ thống có thể ghi đè mất một phép xuất kho. Việc mỗi `SELECT` nhìn thấy dữ liệu đã commit theo MVCC **không tự biến toàn bộ quy trình đọc–quyết định–ghi thành một thao tác nguyên tử**.

Có hai hướng giải quyết thông dụng:

1. **Đưa điều kiện và phép thay đổi vào chính DML**, ví dụ `UPDATE ... SET stock_qty = stock_qty - 4 WHERE stock_qty >= 4 RETURNING ...`. Đây thường là cách đơn giản nhất khi chỉ sửa một hàng.
2. **Khóa hàng khi đọc bằng `SELECT ... FOR UPDATE`** rồi thực hiện một hoặc nhiều quyết định/UPDATE có liên quan trong cùng transaction. Cách này phù hợp khi nghiệp vụ cần đọc nhiều thông tin trước khi ghi.

Khóa hàng không phải lựa chọn duy nhất và cũng không phải lúc nào là lựa chọn nhanh nhất. Hãy dùng khi **cần phối hợp giữa những transaction có khả năng thao tác trên cùng dữ liệu**.

## 2. So sánh SELECT thông thường và SELECT có khóa hàng

Một SELECT không có locking clause:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101;
~~~

Thông thường lấy snapshot theo isolation và không đặt row-level lock kiểu `FOR UPDATE` lên hàng được trả về.

Một SELECT có locking clause:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

ngoài việc đọc kết quả còn yêu cầu **khóa hàng đã chọn**. Khóa có tác dụng phối hợp với những transaction khác đang tìm cách lấy row lock hoặc ghi hàng đó.

Cần phân biệt hai hiện tượng:

| Hiện tượng | SELECT thông thường | SELECT ... FOR UPDATE |
| --- | --- | --- |
| Đọc phiên bản dữ liệu theo MVCC | Có | Có, cùng ngữ nghĩa khóa/cập nhật liên quan |
| Chủ động lấy khóa hàng để phối hợp ghi | Không | Có |
| Có thể chờ writer đang giữ khóa hàng | Thường không, nếu chỉ SELECT thường | Có thể |
| Có thể cản writer khác trên hàng đã khóa | Thông thường không | Có |
| Khóa giữ tới khi nào? | Không có row lock tương ứng | Thường đến cuối transaction hoặc khi rollback thích hợp |

**Không nên hiểu “SELECT thường không khóa” là hoàn toàn không dùng khóa nào.** PostgreSQL vẫn sử dụng khóa cấp bảng như `ACCESS SHARE` để bảo vệ cấu trúc trong khi đọc; khóa này có thể xung đột với DDL cần `ACCESS EXCLUSIVE`. Ở đây chúng ta tập trung vào **row-level locks**.

## 3. Bốn chế độ khóa và ý nghĩa của từng loại

| Khóa hàng | Mục đích chính | Các giao dịch khác có thể làm gì? |
| --- | --- | --- |
| `FOR UPDATE` | Bảo vệ hàng khi transaction có thể sửa hoặc xóa theo bất kỳ cách xung đột nào | Không lấy được các row lock trong bốn loại trên cho cùng hàng cho tới khi khóa được giải phóng |
| `FOR NO KEY UPDATE` | Bảo vệ hàng cho thao tác cập nhật **không thay đổi key liên quan** | Vẫn cho phép `FOR KEY SHARE` cùng hàng |
| `FOR SHARE` | Nhiều reader cùng giữ khóa chia sẻ, không cho cập nhật/xóa hàng khi còn giữ khóa | Cho phép `FOR SHARE` và `FOR KEY SHARE` |
| `FOR KEY SHARE` | Bảo vệ sự tồn tại và khóa tham chiếu của hàng | Cho phép `FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, nhưng không `FOR UPDATE` |

Có thể xem mức độ bảo vệ đại khái theo chiều:

~~~text
FOR UPDATE
  mạnh nhất: xung đột với mọi row-lock mode

FOR NO KEY UPDATE
  chặn writer không-key, share và update;
  tương thích KEY SHARE

FOR SHARE
  nhiều người cùng share; chặn writer thay đổi hàng

FOR KEY SHARE
  nhẹ nhất: bảo vệ khóa/sự tồn tại, cho phép non-key update
~~~

Tuy nhiên, đây **không phải thang số đơn giản** mà chỉ cần so sánh “mạnh hơn/yếu hơn” để biết mọi hành vi. Cách chính xác là dùng **ma trận xung đột** ở mục tiếp theo.

## 4. Ma trận xung đột row-level lock

Giả sử **transaction A đã giữ một row lock** trên cùng một hàng và **transaction B muốn lấy khóa mới**. Ký hiệu:

- **X:** hai khóa xung đột; B có thể phải chờ A kết thúc, hoặc lỗi nếu chọn `NOWAIT`.
- **✓:** hai khóa tương thích theo loại khóa hàng; vẫn có thể chờ vì lý do khác như table lock, transaction, DDL, FK.

| Khóa B yêu cầu ↓ / Khóa A đang giữ → | `FOR KEY SHARE` | `FOR SHARE` | `FOR NO KEY UPDATE` | `FOR UPDATE` |
| --- | :---: | :---: | :---: | :---: |
| **`FOR KEY SHARE`** | ✓ | ✓ | ✓ | X |
| **`FOR SHARE`** | ✓ | ✓ | X | X |
| **`FOR NO KEY UPDATE`** | ✓ | X | X | X |
| **`FOR UPDATE`** | X | X | X | X |

Ma trận đối xứng: nếu A xung đột với B, B cũng xung đột với A khi cùng giữ/yêu cầu khóa trên cùng hàng.

### Bốn kết luận cần nhớ

1. **`FOR UPDATE` xung đột với tất cả**, kể cả `FOR KEY SHARE`.
2. **`FOR NO KEY UPDATE` tương thích với `FOR KEY SHARE`**, nhờ đó những thao tác bảo vệ khóa tham chiếu vẫn có thể tiến hành cùng một cập nhật không-key.
3. **Hai `FOR SHARE` tương thích**, nên nhiều transaction có thể cùng đọc có khóa chia sẻ.
4. **`FOR SHARE` và `FOR NO KEY UPDATE` xung đột**, dù cả hai đều yếu hơn `FOR UPDATE`.

Câu `SELECT` thông thường **không có mặt trong ma trận** vì nó không lấy một trong bốn loại row lock đang xét. Nó thường vẫn đọc được phiên bản đã commit trong khi một transaction khác giữ row lock.

## 5. Những khóa này giữ trong phạm vi nào?

Một câu `SELECT ... FOR ...` cần được đặt trong ngữ cảnh transaction.

~~~sql
BEGIN;

SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- Những statement tiếp theo trên cùng connection
-- vẫn chạy trong transaction đã giữ khóa.

COMMIT;
~~~

Khóa hàng thông thường giữ đến khi transaction **`COMMIT`** hoặc **`ROLLBACK`**. Nếu chạy `SELECT ... FOR UPDATE` với autocommit bật và không có transaction block dài hơn, khóa thường được giải phóng ngay sau khi statement kết thúc; do đó nó **không còn bảo vệ** một câu UPDATE được gửi tiếp như một transaction mới.

### Phải dùng cùng connection/session

~~~text
Connection A:
    BEGIN
    SELECT ... FOR UPDATE

Connection B:
    UPDATE ...
~~~

Connection B **không thừa hưởng khóa của A**. Trong ứng dụng Java, nếu SELECT khóa một hàng bằng connection thứ nhất nhưng UPDATE lại sử dụng connection thứ hai độc lập, bạn có thể đã đánh mất ý nghĩa của critical section.

Muốn đọc–quyết định–ghi được bảo vệ, các thao tác phải nằm **cùng transaction** do service/transaction manager kiểm soát.

### SAVEPOINT

Khi rollback về `SAVEPOINT`, PostgreSQL giải phóng những khóa được lấy sau savepoint theo quy tắc rollback của subtransaction. Điều này khác với việc chỉ `RELEASE SAVEPOINT`, vốn không kết thúc transaction cấp ngoài.

## 6. Dựng database lab và dữ liệu mẫu

Các ví dụ sẽ chạy trong một database PostgreSQL **dành riêng cho học tập**. Đoạn chuẩn bị xóa schema `lock_lab` nếu có. **Không chạy trong database production hoặc schema chung có dữ liệu cần giữ.**

### 6.1. Tạo schema và bảng

~~~sql
-- CẢNH BÁO: chỉ chạy trên database lab do bạn sở hữu.
DROP SCHEMA IF EXISTS lock_lab CASCADE;
CREATE SCHEMA lock_lab;

CREATE TABLE lock_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    tier text NOT NULL DEFAULT 'standard'
        CHECK (tier IN ('standard', 'silver', 'gold')),
    email text NOT NULL UNIQUE
);

CREATE TABLE lock_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES lock_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    total numeric(12,2) NOT NULL CHECK (total >= 0)
);

CREATE TABLE lock_lab.products (
    product_id integer PRIMARY KEY,
    product_name text NOT NULL,
    stock_qty integer NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE lock_lab.jobs (
    job_id integer PRIMARY KEY,
    job_type text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),
    priority integer NOT NULL DEFAULT 0,
    claimed_by text,
    claimed_at timestamptz,
    attempts integer NOT NULL DEFAULT 0
        CHECK (attempts >= 0)
);

CREATE INDEX idx_lock_lab_jobs_pending
ON lock_lab.jobs (priority DESC, job_id)
WHERE status = 'pending';
~~~

Chỉ có hai bảng liên quan FK là `orders` và `customers`; đây là điểm quan trọng để minh họa `FOR KEY SHARE`. `products` phục vụ ví dụ trừ kho; `jobs` phục vụ nhiều worker dùng `SKIP LOCKED`.

### 6.2. Nạp dữ liệu

~~~sql
INSERT INTO lock_lab.customers
    (customer_id, full_name, tier, email)
VALUES
    (1, 'An',   'gold',     'an@example.test'),
    (2, 'Binh', 'silver',   'binh@example.test'),
    (3, 'Chi',  'standard', 'chi@example.test');

INSERT INTO lock_lab.orders
    (order_id, customer_id, status, total)
VALUES
    (101, 1, 'pending', 120.00),
    (102, 2, 'paid',     75.00);

INSERT INTO lock_lab.products
    (product_id, product_name, stock_qty)
VALUES
    (101, 'Coffee', 10),
    (102, 'Tea',     5),
    (103, 'Cup',     0);

INSERT INTO lock_lab.jobs
    (job_id, job_type, status, priority)
VALUES
    (1001, 'send_email', 'pending', 10),
    (1002, 'create_pdf', 'pending',  7),
    (1003, 'sync_stock', 'pending',  7),
    (1004, 'cleanup',    'pending',  2);
~~~

Dữ liệu khởi tạo:

| Bảng | Khóa | Giá trị phục vụ ví dụ |
| --- | --- | --- |
| `customers` | 1 | An, tier gold |
| `customers` | 2 | Binh, tier silver |
| `customers` | 3 | Chi, tier standard, chưa có orders |
| `orders` | 101 | Đơn pending của An |
| `products` | 101 | Coffee, stock 10 |
| `jobs` | 1001–1004 | Bốn job pending, ưu tiên 10/7/7/2 |

### 6.3. Chuẩn bị hai cửa sổ psql

Mở **hai kết nối khác nhau tới cùng database**:

- **Phiên A:** giữ khóa trong transaction.
- **Phiên B:** thử lấy khóa tương thích, xung đột hoặc chạy UPDATE.

Có thể xem ID backend để phân biệt:

~~~sql
SELECT pg_backend_pid() AS my_pid;
~~~

Trước mỗi thí nghiệm, **kết thúc transaction của thí nghiệm trước ở cả A và B**. Những lệnh ghi dùng `ROLLBACK` để dữ liệu quay về seed ban đầu. Nếu một phiên bị lỗi và transaction ở trạng thái aborted, thực hiện `ROLLBACK` trước khi bắt đầu bước mới.

Không cần tạo thêm database hoặc sửa cấu hình PostgreSQL toàn hệ thống để làm các bài cơ bản.

## 7. Thí nghiệm 1: FOR UPDATE chặn một FOR UPDATE khác

Mục tiêu: cho thấy transaction B không lấy được row lock mạnh nhất trên sản phẩm Coffee khi A đang giữ khóa.

**Phiên A:**

~~~sql
BEGIN;

SELECT product_id, product_name, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- A giữ transaction mở; chuyển sang B.
~~~

**Phiên B — thử NOWAIT để không bị treo chờ:**

~~~sql
BEGIN;

SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE NOWAIT;

-- Dự kiến lỗi 55P03 (lock_not_available)
-- khi A vẫn giữ FOR UPDATE trên cùng hàng.

ROLLBACK;
~~~

Lỗi `NOWAIT` khiến transaction B thường chuyển sang trạng thái lỗi và cần rollback. `NOWAIT` giúp ví dụ không phải chờ vô hạn; nó **không có nghĩa khóa đã được lấy thành công**.

**Phiên A kết thúc:**

~~~sql
ROLLBACK;
~~~

Bây giờ một câu `SELECT ... FOR UPDATE NOWAIT` trong transaction mới có thể lấy khóa trên sản phẩm 101 nếu không có phiên nào khác giữ khóa xung đột.

### FOR UPDATE không làm SELECT thường bị chặn

Trong lúc A còn giữ `FOR UPDATE`, một phiên khác có thể chạy:

~~~sql
SELECT product_id, stock_qty
FROM lock_lab.products
WHERE product_id = 101;
~~~

và thông thường vẫn đọc giá trị đã commit theo snapshot. Đây chính là sự phối hợp giữa **MVCC cho plain SELECT** và **row lock cho các thao tác cần đồng bộ**.

## 8. Thí nghiệm 2: FOR UPDATE chặn UPDATE

**Phiên A:**

~~~sql
BEGIN;

SELECT stock_qty
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

**Phiên B:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- Nếu A chưa giải phóng khóa:
-- B chờ, sau đó có thể nhận lỗi 55P03 vì lock_timeout.

ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

`UPDATE` cần khóa hàng để thay đổi tuple. Dù B chỉ sửa `stock_qty` và không thay khóa `product_id`, nó vẫn xung đột với `FOR UPDATE` của A.

### Tại sao dùng SET LOCAL lock_timeout?

`SET LOCAL lock_timeout = '1s'` chỉ có tác dụng trong transaction hiện tại; sau khi transaction kết thúc không còn hiệu lực. Đây là cách giới hạn thời gian đợi khóa trong ví dụ mà không thay đổi cấu hình cho mọi session.

Không nhầm:

- `lock_timeout`: giới hạn thời gian chờ để **lấy khóa**.
- `statement_timeout`: giới hạn thời gian của **toàn statement**.

Với production, chọn timeout theo SLA và loại giao dịch; không dùng 1 giây như một giá trị bắt buộc cho mọi hệ thống.

## 9. FOR NO KEY UPDATE: khóa một cập nhật không đổi khóa

`FOR NO KEY UPDATE` gần với `FOR UPDATE` nhưng yếu hơn ở một điểm quan trọng: nó **không xung đột với `FOR KEY SHARE`**.

Ví dụ A dự định chỉnh sửa phân khúc khách hàng nhưng không đổi khóa `customer_id`:

**Phiên A:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;

-- Giữ transaction mở.
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT customer_id, full_name
FROM lock_lab.customers
WHERE customer_id = 1
FOR KEY SHARE NOWAIT;

-- Có thể thành công theo ma trận,
-- vì FOR KEY SHARE tương thích FOR NO KEY UPDATE.

ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

Tuy cả hai phiên giữ khóa hàng, chúng có mục đích khác nhau:

- A muốn bảo vệ khả năng cập nhật **thuộc tính không phải khóa**.
- B chỉ cần đảm bảo hàng cha và khóa tham chiếu không bị xóa/thay đổi theo cách xung đột.

Vì hai mục đích không mâu thuẫn, PostgreSQL có thể cho phép cả hai tiếp tục.

### Nhưng FOR NO KEY UPDATE vẫn chặn writer không-key khác

Nếu A đang giữ `FOR NO KEY UPDATE` trên khách hàng 1, transaction B muốn:

~~~sql
UPDATE lock_lab.customers
SET tier = 'silver'
WHERE customer_id = 1;
~~~

thì B phải lấy row lock phục vụ UPDATE và có thể bị chặn. Hai writer không được tùy ý cùng sửa một hàng chỉ vì không đổi khóa.

## 10. Vì sao tên “NO KEY UPDATE” có ý nghĩa với foreign key?

Một hàng `customers` có thể được nhiều hàng `orders` tham chiếu qua khóa ngoại:

~~~sql
customer_id integer
    REFERENCES lock_lab.customers(customer_id)
~~~

Khi tạo một đơn tham chiếu khách hàng 1, PostgreSQL phải đảm bảo hàng khách hàng đó không bị xóa hoặc đổi khóa theo cách làm FK không hợp lệ trong lúc kiểm tra. Cơ chế này có thể sử dụng khóa hàng thuộc nhóm **`FOR KEY SHARE`** trên hàng cha.

Nếu một transaction khác chỉ cập nhật `tier` từ gold sang silver, khóa mạnh kiểu `FOR UPDATE` không luôn cần thiết. `FOR NO KEY UPDATE` được thiết kế để tương thích với `FOR KEY SHARE`, nhờ đó **thao tác sửa thuộc tính không-key** có thể diễn ra đồng thời với **thao tác bảo vệ FK**.

~~~mermaid
flowchart TD
    A["Customer 1"] --> B["UPDATE tier (không đổi khóa)"]
    A --> C["INSERT order tham chiếu customer_id=1"]
    B --> D["FOR NO KEY UPDATE"]
    C --> E["Kiểm tra FK / KEY SHARE"]
    D --> F["Hai loại row lock tương thích"]
    E --> F
~~~

Đây là lợi ích thực tế quan trọng của việc có **nhiều chế độ khóa thay vì chỉ một khóa độc quyền**.

**Giới hạn:** chi tiết tiến trình FK còn phụ thuộc câu SQL, trigger, constraint và concurrency; khả năng hai row lock tương thích không hứa toàn bộ một statement không phải chờ bất kỳ tài nguyên nào khác.

## 11. UPDATE và DELETE thường tự lấy row lock nào?

PostgreSQL không đòi người viết luôn dùng `SELECT ... FOR ...` trước khi sửa dữ liệu. Các lệnh DML **tự thực hiện thao tác khóa phù hợp**.

### UPDATE không thay đổi khóa có thể dùng mức FOR NO KEY UPDATE

Ví dụ:

~~~sql
UPDATE lock_lab.customers
SET tier = 'silver'
WHERE customer_id = 1;
~~~

Lệnh này sửa `tier`, không đổi khóa định danh `customer_id`, nên thuộc nhóm UPDATE thông thường có mức khóa hàng tương đương `FOR NO KEY UPDATE`.

### UPDATE thay đổi khóa quan trọng có thể dùng mức FOR UPDATE

~~~sql
UPDATE lock_lab.customers
SET customer_id = 30
WHERE customer_id = 3;
~~~

Khóa chính thay đổi; PostgreSQL cần mức khóa mạnh để phối hợp với những transaction đang giữ `FOR KEY SHARE` trên hàng đó.

Với khách hàng 3 chưa có orders trong lab, statement này có thể thực hiện nếu không có khóa xung đột; hãy bọc `BEGIN ... ROLLBACK` khi thử.

### DELETE dùng mức mạnh

~~~sql
DELETE FROM lock_lab.customers
WHERE customer_id = 3;
~~~

DELETE đe dọa sự tồn tại của hàng cha, nên xung đột với `FOR KEY SHARE` và các chế độ khác, tương đương mức mạnh `FOR UPDATE` ở góc độ row-lock conflict.

### Thế nào là “key” khi UPDATE?

Với quy tắc PostgreSQL, một UPDATE được xem là có thay đổi khóa quan trọng nếu sửa những cột thuộc **unique index có thể dùng cho foreign key**. Các index partial và expression không nằm trong tập được xét theo cách đó. Cách hiểu này **không** có nghĩa mọi cột ứng dụng gọi là “key” bằng tên đều tự có tính chất khóa mạnh.

Nên nhớ quy tắc ở mức thực hành:

- Sửa cột dữ liệu thông thường như `tier`, `status`, `note` → thường là non-key update.
- Sửa primary key hoặc cột unique đủ điều kiện tham chiếu FK → có thể cần mức tương đương `FOR UPDATE`.
- DELETE → cần bảo vệ mạnh vì hàng có thể biến mất.

## 12. FOR SHARE: nhiều reader cùng giữ khóa chia sẻ

`FOR SHARE` dùng khi transaction muốn **đọc và giữ hàng khỏi bị UPDATE/DELETE bởi transaction khác**, nhưng vẫn cho các transaction khác lấy khóa chia sẻ.

**Phiên A:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 2
FOR SHARE;
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT customer_id, full_name, tier
FROM lock_lab.customers
WHERE customer_id = 2
FOR SHARE NOWAIT;

-- Thành công theo ma trận: SHARE và SHARE tương thích.

ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

### FOR SHARE chặn phép UPDATE không-key

Thử lại với A giữ `FOR SHARE`; B chạy:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 2;

-- Có thể hết thời gian chờ vì A giữ FOR SHARE.

ROLLBACK;
~~~

Vì `FOR SHARE` xung đột với `FOR NO KEY UPDATE`, B không thể tự sửa hàng trong khi A giữ khóa chia sẻ.

### FOR SHARE không giống SELECT thường

Một báo cáo chỉ đọc dữ liệu, không dựa vào việc hàng phải giữ nguyên sau SELECT, thường **không cần `FOR SHARE`**. Nếu nhiều báo cáo tùy tiện lấy SHARE rồi giữ transaction lâu, writer có thể bị chặn không cần thiết.

Dùng `FOR SHARE` khi transaction thực sự cần **cam kết bảo vệ hàng đọc được khỏi cập nhật** cho một bước nghiệp vụ tiếp theo, không dùng chỉ vì tên nghe giống “đọc”.

## 13. FOR KEY SHARE: bảo vệ khóa chứ không khóa mọi thuộc tính

`FOR KEY SHARE` là khóa hàng yếu nhất trong bốn loại.

**Phiên A:**

~~~sql
BEGIN;

SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 3
FOR KEY SHARE;
~~~

**Phiên B — sửa cột thường:**

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 3
RETURNING customer_id, tier;

-- Có thể thành công vì UPDATE không-key
-- tương thích với FOR KEY SHARE.

ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

A yêu cầu giữ khách hàng ID 3 và khóa định danh ổn định, nhưng **không yêu cầu chặn thay đổi tier**. B có thể sửa tier mà không vi phạm mục đích đó.

### FOR KEY SHARE chặn DELETE và thay đổi key

Nếu A vẫn giữ `FOR KEY SHARE`:

~~~sql
BEGIN;
SET LOCAL lock_timeout = '1s';

DELETE FROM lock_lab.customers
WHERE customer_id = 3;

-- Có thể chờ rồi hết lock_timeout.

ROLLBACK;
~~~

Tương tự, việc đổi `customer_id` của cùng hàng có thể bị chặn vì thay đổi key là thao tác xung đột.

**Không nhầm KEY SHARE với SHARE:** `FOR SHARE` ngăn cập nhật thông thường, còn `FOR KEY SHARE` thường không ngăn cập nhật những cột không-key.

## 14. Tóm tắt bốn kiểu qua một tình huống

Giả sử transaction A giữ khóa khách hàng 1. Phiên B muốn làm một trong các việc: đọc thường, đọc có khóa, sửa tier, đổi customer_id hoặc xóa hàng.

| Khóa A | B SELECT thường | B FOR KEY SHARE | B FOR SHARE | B UPDATE tier | B DELETE |
| --- | --- | --- | --- | --- | --- |
| `FOR UPDATE` | Thường đọc được | Chờ | Chờ | Chờ | Chờ |
| `FOR NO KEY UPDATE` | Thường đọc được | Được | Chờ | Chờ | Chờ |
| `FOR SHARE` | Thường đọc được | Được | Được | Chờ | Chờ |
| `FOR KEY SHARE` | Thường đọc được | Được | Được | Thường được | Chờ |

**“Được” trong bảng chỉ xét tương thích row lock**, không cam kết miễn mọi loại lock/constraint hoặc thay đổi snapshot khác. UPDATE tier giả định là non-key update theo schema mẫu.

Dòng quan trọng nhất để ghi nhớ: nếu chỉ muốn bảo vệ khóa tham chiếu khi tạo FK, **`FOR KEY SHARE` cho phép nhiều concurrency hơn `FOR SHARE` hoặc `FOR UPDATE`**.

## 15. FOR NO KEY UPDATE khác FOR UPDATE khi nào?

Đây là câu hỏi thường gặp nhất vì hai chế độ đều có thể bảo vệ một bước cập nhật.

Giả sử ứng dụng đọc tài khoản rồi sẽ sửa cột `status` nhưng không thay mã khóa định danh. Một số người mặc định dùng:

~~~sql
SELECT customer_id, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR UPDATE;
~~~

Câu này khóa mạnh, chặn ngay cả transaction khác chỉ muốn `FOR KEY SHARE` để bảo vệ FK.

Nếu nghiệp vụ chỉ cần khóa để cập nhật cột không-key:

~~~sql
SELECT customer_id, tier
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;
~~~

nó vẫn xung đột với writer không-key khác và `FOR SHARE`, nhưng **tương thích KEY SHARE**, giúp hạn chế một số wait không cần thiết.

### Đừng hạ mức khóa chỉ để “nhanh hơn”

Nếu transaction thực sự sẽ xóa hàng hoặc thay key quan trọng, `FOR KEY SHARE` của transaction khác có lý do chính đáng để được bảo vệ. Dùng khóa yếu không đủ hoặc viết một workflow dựa trên điều kiện sai có thể gây chờ sau đó, deadlock hoặc làm hỏng giả định của ứng dụng.

Chọn chế độ theo **hành động dự kiến và bất biến nghiệp vụ**, không phải theo một quy tắc “cứ yếu nhất là nhanh nhất”.

## 16. NOWAIT: báo lỗi thay vì chờ khóa hàng

Cú pháp:

~~~sql
SELECT *
FROM lock_lab.jobs
WHERE job_id = 1001
FOR UPDATE NOWAIT;
~~~

Nếu có row lock xung đột, PostgreSQL có thể trả lỗi `lock_not_available`, SQLSTATE **`55P03`**, thay vì chờ khóa hàng được giải phóng.

Dùng `NOWAIT` khi:

- API cần phản hồi nhanh “đang bận, thử lại”.
- Worker không muốn chờ một đối tượng đang được xử lý.
- Công việc có thể được đưa về queue xử lý sau.
- Muốn minh họa xung đột lock trong lab mà không để phiên bị treo.

### NOWAIT không đảm bảo mọi thao tác đều tức thì

`NOWAIT` trong locking clause áp dụng cho **row-level locks** liên quan. Bản thân statement vẫn lấy các table-level locks cần thiết theo cơ chế thông thường và có thể chờ một xung đột ở cấp bảng.

Nếu cần chính sách không chờ cả table-level lock cho một nghiệp vụ chuyên biệt, có thể cần dùng `LOCK TABLE ... NOWAIT` hoặc cấu hình timeout phù hợp. Không nên mặc định rằng thêm `FOR UPDATE NOWAIT` biến mọi khâu của truy vấn thành nonblocking.

## 17. SKIP LOCKED: bỏ qua hàng đã bị worker khác khóa

`SKIP LOCKED` cho phép một worker **bỏ qua** những hàng mà nó không thể lấy row lock ngay do có phiên khác giữ khóa xung đột.

~~~sql
SELECT job_id, job_type, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

Nếu job 1001 đang bị worker A khóa, worker B có thể chọn job 1002 hoặc một job pending khác, tùy dữ liệu đang nhìn thấy và kế hoạch truy vấn.

### Vì sao phù hợp cho queue?

Trong bảng job, hai worker thường không cần chờ nhau chỉ để tranh **cùng một job**. Worker B có thể xử lý job kế tiếp.

~~~mermaid
flowchart LR
    J["Pending jobs: 1001, 1002, 1003"] --> A["Worker A: lock 1001"]
    J --> B["Worker B: SKIP LOCKED"]
    B --> C["Bỏ qua 1001 đang khóa"]
    C --> D["Lock 1002"]
~~~

### Vì sao không phù hợp cho báo cáo chính xác?

`SKIP LOCKED` cố ý tạo một cái nhìn **không đầy đủ** về tập hàng — các hàng đang khóa có thể biến mất khỏi kết quả tạm thời. Đừng dùng nó để kết luận:

- Có đúng bao nhiêu đơn pending trong toàn hệ thống.
- Tất cả khách hàng nào cần kiểm toán.
- Tổng tiền chính xác của mọi hàng thỏa điều kiện.

Nó thích hợp cho **tranh công việc giữa nhiều consumer**, không phải một cách chung để “tránh lock cho mọi SELECT”.

## 18. Thí nghiệm hai worker với SKIP LOCKED

Sau khi reset `jobs` về seed, chạy ở **hai session**.

**Phiên A:**

~~~sql
BEGIN;

SELECT job_id, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Kết quả: job 1001 (priority 10).
-- Giữ transaction A mở.
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT job_id, priority
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;

-- Khi 1001 bị A khóa, B thường chọn job 1002.

ROLLBACK;
~~~

**Phiên A:**

~~~sql
ROLLBACK;
~~~

Vì cả hai session rollback mà không đổi status, tất cả jobs trở lại pending. Việc B nhận 1002 trong ví dụ minh họa do job 1001 đã bị A khóa chứ không phải vì nó đã được commit thành running.

### Một lưu ý về fairness

`SKIP LOCKED` không bảo đảm thứ tự phục vụ tuyệt đối hay tránh starvation. Một hàng liên tục bị khóa có thể bị nhiều worker bỏ qua; job ưu tiên cao có thể phải chờ điều kiện nghiệp vụ khác. Hệ thống queue thực tế cần lease, retry, timeout, metrics và chính sách phục hồi job mắc kẹt.

## 19. Claim job một cách nguyên tử bằng CTE + UPDATE

Chỉ `SELECT ... FOR UPDATE SKIP LOCKED` rồi đóng transaction **không đủ** để worker sở hữu job lâu dài. Sau commit/rollback, khóa được giải phóng; worker khác có thể chọn lại cùng job nếu status chưa đổi.

Mẫu thường dùng là **chọn và đánh dấu running trong cùng transaction**:

~~~sql
BEGIN;

WITH picked AS (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, job_id
    LIMIT 1
    FOR UPDATE SKIP LOCKED
)
UPDATE lock_lab.jobs AS j
SET
    status = 'running',
    claimed_by = 'worker-A',
    claimed_at = clock_timestamp(),
    attempts = attempts + 1
FROM picked AS p
WHERE j.job_id = p.job_id
  AND j.status = 'pending'
RETURNING
    j.job_id,
    j.job_type,
    j.status,
    j.claimed_by,
    j.attempts;

COMMIT;
~~~

Từng bước:

1. CTE `picked` tìm một job pending và lấy `FOR UPDATE SKIP LOCKED` ngay lúc chọn.
2. `UPDATE` đổi trạng thái job đã được chọn sang running.
3. `RETURNING` trả **đúng job được claim** để worker bắt đầu xử lý.
4. `COMMIT` lưu claim; khi lock được giải phóng, transaction khác không còn chọn job này vì `status <> 'pending'`.

Nếu không có job đủ điều kiện, `RETURNING` trả 0 hàng. Worker có thể nghỉ hoặc thử lại theo lịch, không phải báo lỗi SQL.

**Rủi ro sau commit:** nếu worker chết ngay sau khi claim nhưng trước khi xử lý xong, job có thể mắc kẹt ở running. Một hệ thống production phải có **lease deadline/heartbeat, retry/backoff, idempotency** và cơ chế đưa job lỗi về trạng thái xử lý lại an toàn. Row lock tồn tại trong transaction không thay thế workflow recovery sau commit.

## 20. OF table_alias: khóa đúng bảng trong câu JOIN

Một câu JOIN có thể đọc nhiều bảng:

~~~sql
SELECT
    o.order_id,
    o.status,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE;
~~~

Khi không chỉ rõ `OF`, locking clause có thể áp dụng cho **mọi bảng cơ sở đủ điều kiện được tham chiếu** trong query. Vì vậy query trên có thể yêu cầu khóa hàng của cả `orders` và `customers`, làm tăng tranh chấp không cần thiết.

Nếu chỉ muốn khóa **đơn hàng**, còn tên khách hàng chỉ để hiển thị:

~~~sql
SELECT
    o.order_id,
    o.status,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o;
~~~

`FOR UPDATE OF o` yêu cầu khóa hàng ở vai trò bảng `o`, không áp cùng locking clause lên hàng của `c`.

### Khi thực sự cần hai mức khóa khác nhau

Có thể viết nhiều locking clause với mục tiêu rõ ràng:

~~~sql
SELECT
    o.order_id,
    c.customer_id,
    c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o
FOR KEY SHARE OF c;
~~~

Ở đây:

- Đơn hàng được khóa mạnh vì có thể bị sửa.
- Khách hàng chỉ cần khóa bảo vệ key/sự tồn tại khi transaction dựa vào FK.

Nếu bảng được tham chiếu với alias, dùng **alias đó** trong `OF`. Việc áp nhiều locking clause lên cùng bảng được PostgreSQL tổng hợp theo mức mạnh nhất áp dụng.

### LEFT JOIN có một giới hạn

Không phải lúc nào cũng có thể khóa phía **nullable** của một outer join; PostgreSQL có giới hạn với locking clause trên bên có thể sinh hàng NULL của outer join. Khi đó cần tổ chức lại query hoặc chỉ khóa phía bảng hợp lệ bằng `OF`.

## 21. CTE và phạm vi của khóa

Khóa được lấy ở nơi locking clause thực sự áp dụng. Nếu dùng CTE để chọn một tập hàng cần khóa, hãy đặt locking clause **bên trong CTE**:

~~~sql
WITH chosen AS (
    SELECT job_id
    FROM lock_lab.jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, job_id
    LIMIT 2
    FOR UPDATE SKIP LOCKED
)
SELECT job_id
FROM chosen;
~~~

Một `FOR UPDATE` ở **truy vấn ngoài** không tự động có hiệu lực với mọi CTE được tham chiếu theo cách người viết có thể tưởng.

Trong pipeline queue ở mục 19, việc `FOR UPDATE SKIP LOCKED` nằm trong `picked` là có chủ ý: hàng được khóa **ngay khi chọn** để nhiều worker không cùng claim.

### Không đặt locking clause ở vị trí không hợp lệ

Locking clause có những hạn chế khi truy vấn có `DISTINCT`, `GROUP BY`, phép tập hợp và những dạng kết quả không thể gắn trực tiếp về một hàng nguồn xác định. Ví dụ không nên kỳ vọng:

~~~sql
-- Không phải cách đúng để khóa từng hàng nguồn:
SELECT status, COUNT(*)
FROM lock_lab.jobs
GROUP BY status
FOR UPDATE;
~~~

Để khóa hàng nguồn rồi tổng hợp, thường phải thiết kế tách bước hoặc dùng một CTE chứa các hàng nguồn hợp lệ để khóa. Nhưng phải cân nhắc câu hỏi nghiệp vụ: **vì sao cần khóa để đếm?** Với báo cáo, snapshot MVCC thường thích hợp hơn.

## 22. READ COMMITTED: khóa có thể chờ rồi đánh giá lại hàng

Giả sử phiên B đang cập nhật job 1001 từ `pending` sang `running` nhưng chưa commit. Phiên A chạy:

~~~sql
SELECT job_id, status
FROM lock_lab.jobs
WHERE job_id = 1001
  AND status = 'pending'
FOR UPDATE;
~~~

Ở `READ COMMITTED`, nếu câu `SELECT ... FOR UPDATE` gặp hàng đang bị transaction khác cập nhật, nó có thể **chờ** transaction kia. Khi writer commit, PostgreSQL sẽ xử lý hàng đã được cập nhật và kiểm tra lại điều kiện `WHERE` theo quy tắc của mức isolation.

Nếu trạng thái sau commit là `running`, hàng có thể **không còn được trả về**, vì không thỏa `status='pending'`.

Vì vậy:

- `SELECT ... FOR UPDATE` không có nghĩa chắc chắn sẽ trả đúng những hàng từng thỏa điều kiện ở thời điểm trước khi chờ.
- Một hàng có thể được bỏ qua nếu transaction khác đã thay đổi nó và điều kiện không còn phù hợp.
- Ứng dụng cần xử lý kết quả 0 hàng như một trường hợp cạnh tranh hợp lệ.

Đây cũng là lý do các workflow thường thêm điều kiện kiểm tra lại trạng thái ngay trong `UPDATE`.

## 23. REPEATABLE READ và SERIALIZABLE có thể báo lỗi thay vì cho cập nhật lại

Ở `REPEATABLE READ`, snapshot được giữ theo transaction. Nếu transaction cố khóa hoặc cập nhật một hàng đã bị transaction khác thay đổi kể từ snapshot đó, PostgreSQL có thể trả lỗi như:

~~~text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
~~~

Điều này khác với hành vi ở `READ COMMITTED`, nơi một câu UPDATE có thể chờ rồi xử lý lại hàng theo phiên bản đã commit mới.

### Khi gặp 40001 phải làm gì?

Thông thường cần:

1. `ROLLBACK` transaction lỗi.
2. Bắt đầu transaction **mới**.
3. Đọc lại dữ liệu và đưa ra quyết định lại theo snapshot mới.
4. Lặp lại thao tác ghi nếu nghiệp vụ cho phép.
5. Có retry limit và backoff để tránh vòng lặp vô hạn.

**Không chỉ lặp lại đúng câu UPDATE cuối** nếu quyết định trước đó dựa trên những câu SELECT đã đọc ở snapshot cũ.

`SERIALIZABLE` có thể phát hiện thêm những xung đột logic giữa các transaction và chủ động abort một transaction để giữ tính serializable. Row lock giúp phối hợp nhưng **không thay thế** mọi ràng buộc cần thiết của isolation cao.

## 24. Deadlock: khóa hàng theo thứ tự đối nghịch

Khóa có thể gây **deadlock** khi hai transaction chờ nhau theo vòng.

Ví dụ hai tài khoản logic A và B được lưu ở `products`.

**Phiên A:**

~~~sql
BEGIN;

SELECT product_id
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- A đang giữ khóa sản phẩm 101.
~~~

**Phiên B:**

~~~sql
BEGIN;

SELECT product_id
FROM lock_lab.products
WHERE product_id = 102
FOR UPDATE;

-- B đang giữ khóa sản phẩm 102.
~~~

Bây giờ:

**Phiên A yêu cầu hàng của B:**

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id = 102
FOR UPDATE;

-- A chờ B.
~~~

**Phiên B yêu cầu hàng của A:**

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;

-- B chờ A: tạo vòng deadlock.
~~~

PostgreSQL có cơ chế phát hiện deadlock và sẽ hủy một transaction với SQLSTATE **`40P01`** để phá vòng chờ. Transaction bị hủy phải rollback; transaction còn lại có thể tiếp tục sau khi khóa được giải phóng.

### Giảm deadlock bằng thứ tự khóa thống nhất

Nếu mọi code path đều khóa nhiều sản phẩm **theo product_id tăng dần**, nguy cơ vòng chờ giảm đáng kể:

~~~sql
SELECT product_id
FROM lock_lab.products
WHERE product_id IN (101, 102)
ORDER BY product_id
FOR UPDATE;
~~~

Thứ tự khóa cần được thiết kế nhất quán trên những đường thực thi liên quan, kể cả khi có trigger/FK hoặc nhiều bảng. `ORDER BY` trong câu đơn là kỹ thuật hữu ích nhưng không phải chứng minh hệ thống sẽ không bao giờ có deadlock.

Các khuyến nghị khác:

- Giữ transaction ngắn.
- Không gọi API mạng khi đang giữ khóa nếu có thể tránh.
- Chọn khóa theo thứ tự thống nhất giữa các service.
- Tránh khóa nhiều hàng/bảng hơn cần thiết.
- Có retry transaction an toàn khi gặp `40P01`.

## 25. Lock timeout khác deadlock

Hai lỗi có thể đều làm câu lệnh thất bại nhưng nguyên nhân khác:

| SQLSTATE | Tình huống | Cách tiếp cận |
| --- | --- | --- |
| `55P03` | Không lấy được lock do `NOWAIT` hoặc hết `lock_timeout` | Phản hồi bận, chờ/retry có kiểm soát hoặc chọn công việc khác |
| `40P01` | Deadlock được phát hiện | Rollback và retry transaction theo chính sách |
| `40001` | Serialization failure | Retry toàn transaction với snapshot mới |
| `57014` | Statement bị hủy, ví dụ vì statement timeout hoặc user cancel | Xem nguyên nhân; không tự coi là lock conflict |

**Không retry mọi lỗi SQL bằng cùng một cách.** Đặc biệt nếu transaction đã có side effect bên ngoài PostgreSQL, cần idempotency và reconciliation trước khi retry.

## 26. Quan sát những phiên đang bị chặn

Dùng một **phiên C** để chẩn đoán khi A và B đang chạy thí nghiệm.

### 26.1. Ai đang chờ và bị ai chặn?

~~~sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 160) AS query_snippet
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY pid;
~~~

Một session bị chặn bởi row lock có thể hiển thị `wait_event_type = 'Lock'` và một `wait_event` liên quan tới transaction ID hoặc loại lock khác. Đừng chỉ tìm một chuỗi cố định như `tuple`: row locks và việc chờ transaction được phản ánh qua các loại metadata khác nhau.

`pg_blocking_pids(pid)` giúp tìm PID đang chặn transaction được quan sát.

### 26.2. Xem table-level locks

~~~sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE relation = 'lock_lab.products'::regclass
ORDER BY pid, granted, mode;
~~~

Bạn có thể thấy các lock cấp quan hệ như `RowShareLock` và `RowExclusiveLock` liên quan tới những statement truy cập bảng.

**Quan trọng:** không phải mọi row lock đang giữ đều xuất hiện rõ ràng như một hàng `locktype='tuple'` trong `pg_locks`. Thông tin khóa hàng còn được lưu trong tuple metadata trên đĩa; khi chờ, session thường chờ transaction khác kết thúc. Do đó, kết hợp `pg_stat_activity`, `pg_blocking_pids` và `pg_locks` sẽ hữu ích hơn việc chỉ tìm mọi row lock trong `pg_locks`.

### 26.3. Đừng tự terminate phiên trên production

Một transaction lâu có thể đang chạy migration, báo cáo hoặc xử lý nghiệp vụ quan trọng. Không tự chạy `pg_terminate_backend` khi thấy PID chờ lâu mà chưa xác định owner, mức ảnh hưởng và phương án rollback.

## 27. Table-level lock đi kèm row-level locking clause

Khi dùng:

~~~sql
SELECT *
FROM lock_lab.products
WHERE product_id = 101
FOR UPDATE;
~~~

PostgreSQL còn lấy khóa cấp quan hệ **`ROW SHARE`** trên các bảng chịu locking clause. Ngược lại, `UPDATE` lấy khóa cấp bảng **`ROW EXCLUSIVE`** cùng row locks phục vụ những hàng thực sự sửa.

Tên `ROW SHARE`/`ROW EXCLUSIVE` dễ gây hiểu lầm vì đây là **tên các chế độ khóa cấp bảng**, không phải row-level `FOR SHARE` và `FOR UPDATE`.

| Loại khóa | Ví dụ | Phạm vi |
| --- | --- | --- |
| Table-level `ACCESS SHARE` | SELECT thường | Quan hệ/bảng |
| Table-level `ROW SHARE` | SELECT FOR UPDATE/SHARE | Quan hệ/bảng |
| Table-level `ROW EXCLUSIVE` | UPDATE/INSERT/DELETE | Quan hệ/bảng |
| Row-level `FOR UPDATE` | SELECT ... FOR UPDATE | Những hàng được khóa |

Do đó:

- Hai câu SELECT thường không chặn nhau vì row lock.
- Một SELECT FOR UPDATE có thể phải chờ DDL ngay cả khi không có writer cùng hàng.
- `NOWAIT` trên locking clause không giải quyết mọi xung đột table-level lock.

Khi phân tích hệ thống bị chậm vì khóa, luôn hỏi **đang chờ khóa hàng hay khóa bảng**, không đánh đồng hai loại.

## 28. Khóa hàng không bảo vệ một hàng chưa tồn tại

Giả sử hai request cùng muốn tạo khách hàng với email `new@example.test`.

Một transaction chạy:

~~~sql
SELECT customer_id
FROM lock_lab.customers
WHERE email = 'new@example.test'
FOR UPDATE;
~~~

Nếu **không có hàng**, query trả 0 hàng và **không có tuple nào được khóa**. Transaction khác vẫn có thể thử INSERT email này.

Vì vậy, kiểu code:

~~~text
SELECT ... WHERE email=? FOR UPDATE;
Nếu không thấy thì INSERT ...
~~~

**không đủ** làm tuyến bảo vệ chính chống tạo trùng. PostgreSQL không tự tạo “khóa gap trên giá trị chưa có” theo cách mà người viết có thể kỳ vọng ở một số hệ quản trị khác.

### Cách đúng cho tính duy nhất

Bảng `customers` có `UNIQUE(email)`, nên dùng constraint và `INSERT ... ON CONFLICT` hoặc xử lý unique violation theo nghiệp vụ:

~~~sql
INSERT INTO lock_lab.customers
    (customer_id, full_name, email)
VALUES
    (10, 'New', 'new@example.test')
ON CONFLICT (email) DO NOTHING
RETURNING customer_id;
~~~

Nếu hai phiên cùng INSERT, PostgreSQL sẽ phối hợp qua unique index để không commit hai hàng cùng email.

**Row lock bảo vệ hàng đang tồn tại; unique constraint bảo vệ bất biến duy nhất của khóa khi nhiều transaction INSERT đồng thời.** Hai cơ chế có mục tiêu khác nhau.

## 29. Khóa hàng không tự bảo vệ mọi bất biến nhiều hàng

Ví dụ ứng dụng yêu cầu tổng tồn kho của hai sản phẩm không xuống dưới một ngưỡng, hoặc bắt buộc còn ít nhất một nhân viên trực ca.

Hai transaction có thể khóa và sửa **hai hàng khác nhau**, mỗi bên đọc một snapshot rồi quyết định dựa vào hàng còn lại. Nếu không có xung đột writer trên cùng hàng, có thể xuất hiện **write skew** ở một số isolation.

Giải pháp có thể bao gồm:

- Khóa **toàn bộ tập hàng liên quan** một cách nhất quán.
- Tạo một hàng “điểm phối hợp” để khóa theo nghiệp vụ.
- Dùng constraint có thể diễn đạt bất biến trực tiếp.
- Sử dụng `SERIALIZABLE` và retry transaction khi cần.
- Điều chỉnh mô hình dữ liệu để việc ghi một bất biến tập trung vào một khóa có thể tranh chấp rõ ràng.

Không suy rằng **cứ một SELECT FOR UPDATE ở bất kỳ đâu thì toàn transaction đã serializable**. Muốn chứng minh tính đúng phải biết **hàng nào được đọc, hàng nào được khóa, hàng nào được sửa và những tình huống concurrent transaction nào có thể xảy ra**.

## 30. Khóa hàng không phải khóa tư vấn (advisory lock)

PostgreSQL còn hỗ trợ **advisory locks** để ứng dụng tự đặt khóa theo một khóa logic được chọn, ví dụ `pg_advisory_xact_lock(...)`. Chúng khác row lock:

| Đặc tính | Row-level FOR ... | Advisory lock |
| --- | --- | --- |
| Gắn với hàng trong bảng | Có | Không bắt buộc |
| PostgreSQL tự dùng cho UPDATE/FK | Có | Không tự động |
| Khóa đối tượng chưa có hàng | Không, vì chưa có tuple | Có thể khóa một khóa logic do ứng dụng chọn |
| Cần ứng dụng thống nhất quy ước khóa | Ít hơn cho dữ liệu hàng | Có |
| Khi nào dùng | Chống tranh chấp trên hàng đang tồn tại | Điều phối một tài nguyên logic hoặc nghiệp vụ đặc biệt |

Advisory locks không thay thế `UNIQUE`, FK hay row lock cho mọi tình huống. Chúng hữu ích khi không có một hàng rõ ràng để khóa, nhưng phải quản lý phạm vi khóa, deadlock, connection pooling và quy tắc release.

Bài này tập trung vào **bốn row-level locking modes**, không sử dụng advisory locks trong lab để tránh lẫn hai cơ chế.

## 31. Lọc, thứ tự và số hàng bị khóa

Một câu SELECT có locking clause hoạt động trên những hàng nó phải khóa trong quá trình thực thi theo kế hoạch và quy tắc PostgreSQL. Không nên giả định số row locks luôn bằng đúng số hàng hiển thị trên màn hình trong mọi query phức tạp.

### LIMIT

~~~sql
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE;
~~~

Với kiểu query này, locking có thể dừng khi đã đủ hàng để trả theo `LIMIT`, nên thích hợp với chọn một job. Nhưng cần hiểu các chi tiết plan/scan nếu có join, subquery, offset hoặc concurrent update.

### OFFSET

Hàng được bỏ qua bởi `OFFSET` vẫn có thể bị khóa trong một locking query. Vì vậy không dùng `OFFSET` lớn rồi mặc định chỉ có các hàng hiển thị mới chịu ảnh hưởng khóa.

### ORDER BY và READ COMMITTED

Ở `READ COMMITTED`, một query có `ORDER BY ... FOR UPDATE` đôi khi **trả hàng không còn đúng thứ tự theo giá trị mới nhất** nếu phải chờ row lock và dữ liệu sắp xếp thay đổi trong lúc chờ. PostgreSQL có giải thích và workaround trong tài liệu, nhưng workaround có thể khiến phạm vi khóa rộng hơn.

Với queue, hãy chọn khóa có tie-breaker rõ ràng (`ORDER BY priority DESC, job_id`), giữ transaction ngắn và chấp nhận rằng concurrent worker có thể làm thứ tự claim không hoàn toàn tuyệt đối.

## 32. Không nên giữ khóa trong lúc gọi dịch vụ mạng chậm

Một anti-pattern:

~~~text
BEGIN;
SELECT order_id FROM orders WHERE order_id=? FOR UPDATE;
Gọi payment API trong 30 giây;
Đợi callback;
UPDATE orders;
COMMIT;
~~~

Trong toàn bộ thời gian chờ API, transaction tiếp tục giữ khóa hàng và có thể khiến các transaction khác chờ, gây tăng latency, timeout hoặc deadlock.

Tùy nghiệp vụ, có thể thiết kế:

1. Ghi trạng thái `processing`/claim vào database và commit sớm.
2. Gọi dịch vụ ngoài với idempotency key.
3. Trong transaction mới, xác nhận kết quả và cập nhật trạng thái hợp lệ.
4. Ghi event outbox để xử lý phần việc tiếp theo.
5. Thiết kế retry/reconciliation cho trường hợp không rõ API đã thực hiện hay chưa.

Đây là workflow nhiều bước phức tạp hơn, nhưng thường an toàn vận hành hơn việc giữ row lock trong suốt một request mạng không kiểm soát được thời lượng.

## 33. Đọc và khóa qua JDBC

Trong Java với pgJDBC, hãy giữ locking read và UPDATE **trong cùng một transaction và cùng connection**.

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class ProductStockService {

    public static boolean deduct(
        Connection connection,
        int productId,
        int requested
    ) throws SQLException {
        if (requested <= 0) {
            throw new IllegalArgumentException(
                "requested must be positive"
            );
        }

        // Giả định connection đang thuộc một transaction
        // do caller/service quản lý (autoCommit = false).
        String readSql = """
            SELECT stock_qty
            FROM lock_lab.products
            WHERE product_id = ?
            FOR UPDATE
            """;

        String updateSql = """
            UPDATE lock_lab.products
            SET stock_qty = stock_qty - ?
            WHERE product_id = ?
              AND stock_qty >= ?
            RETURNING stock_qty
            """;

        try (PreparedStatement read =
                 connection.prepareStatement(readSql)) {
            read.setInt(1, productId);

            try (ResultSet rs = read.executeQuery()) {
                if (!rs.next() || rs.getInt("stock_qty") < requested) {
                    return false;
                }
            }
        }

        try (PreparedStatement update =
                 connection.prepareStatement(updateSql)) {
            update.setInt(1, requested);
            update.setInt(2, productId);
            update.setInt(3, requested);

            try (ResultSet rs = update.executeQuery()) {
                return rs.next();
            }
        }
    }
}
~~~

Ví dụ cố ý cho thấy locking read **không mất ý nghĩa** khi connection duy trì cùng transaction. Phần `UPDATE ... WHERE stock_qty >= ?` kiểm tra lại điều kiện, giúp logic phòng thủ tốt hơn.

**Tối ưu có thể áp dụng:** nếu chỉ cần trừ tồn kho một hàng, câu UPDATE có điều kiện kèm RETURNING **không cần SELECT FOR UPDATE trước** vẫn có thể đủ. Dùng locking read khi cần nhiều quyết định/ghi dựa trên những trường đã đọc, không làm quy trình dài hơn chỉ vì thói quen.

### Transaction boundary ở service

~~~java
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setAutoCommit(false);

    boolean success = ProductStockService.deduct(
        connection, 101, 3
    );

    if (success) {
        connection.commit();
    } else {
        connection.rollback();
    }
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
} finally {
    connection.setAutoCommit(oldAutoCommit);
}
~~~

Đây là minh họa cho **connection do đoạn code trực tiếp sở hữu**. Nếu ứng dụng dùng Spring/Hibernate hoặc một transaction manager, transaction boundary phải do framework quản lý; không tự bật/tắt autocommit trên connection được chia sẻ mà không có hợp đồng rõ ràng.

### Xử lý SQLSTATE

~~~java
try {
    // SELECT ... FOR UPDATE NOWAIT hoặc DML.
} catch (SQLException ex) {
    String state = ex.getSQLState();

    if ("55P03".equals(state)) {
        // lock_not_available: phản hồi bận hoặc retry có kiểm soát.
    } else if ("40P01".equals(state)) {
        // deadlock_detected: rollback, cân nhắc retry transaction.
    } else if ("40001".equals(state)) {
        // serialization_failure: retry toàn transaction.
    }

    throw ex;
}
~~~

Sau lỗi, transaction PostgreSQL có thể ở trạng thái aborted. Hãy rollback hoặc rollback về savepoint phù hợp trước khi tiếp tục.

## 34. Hiệu năng, WAL và tác động của việc khóa hàng

Row-level locking không đồng nghĩa miễn phí:

- Có chi phí kiểm tra/đặt khóa và tranh chấp khi có nhiều phiên.
- Lock có thể làm tăng độ trễ cho transaction khác.
- `SELECT ... FOR UPDATE` có thể khiến PostgreSQL phải **ghi metadata khóa vào tuple trên đĩa** và tạo WAL liên quan, dù câu SQL không thay đổi giá trị cột nghiệp vụ.
- Lock kéo dài làm transaction khác chờ, tạo thêm transaction age và áp lực vận hành.
- Khi nhiều transaction cùng khóa nhiều hàng, nguy cơ deadlock tăng.

Nếu mục tiêu chỉ là báo cáo/đọc dữ liệu, **SELECT thường dựa trên MVCC** có thể phù hợp hơn.

### Theo dõi trước khi tối ưu

- Tỉ lệ lock waits và thời gian chờ.
- `pg_blocking_pids` và `pg_stat_activity.wait_event`.
- Tần suất `55P03`, `40P01`, `40001`.
- Transaction dài và `idle in transaction`.
- Độ rộng tập hàng được locking query chọn.
- Số lượng worker cùng tranh một job/hàng nóng.
- Query plan và index để tìm đúng hàng mà không quét phạm vi quá lớn.

Một index trên điều kiện chọn (như `job_id` hoặc `status + priority`) giúp giảm chi phí tìm hàng, nhưng không làm row lock trở nên miễn xung đột. Cần phân biệt **truy vấn chậm vì tìm hàng** và **truy vấn chậm vì chờ khóa**.

## 35. Những lỗi thường gặp

### 35.1. Nghĩ SELECT FOR UPDATE chặn cả SELECT thông thường

Reader thường có thể tiếp tục đọc tuple phù hợp theo MVCC. Khóa FOR UPDATE chủ yếu xung đột với locking reads/writes khác, không biến mọi reader thành blocked.

### 35.2. Quên transaction và dùng autocommit

Lock có thể được giải phóng ngay khi statement kết thúc; câu UPDATE kế tiếp trên transaction khác không còn được bảo vệ bởi khóa trước đó.

### 35.3. Lấy khóa trên connection A, ghi trên connection B

Hai connection không chia sẻ một transaction. Phải giữ locking read và thao tác dựa vào nó trong cùng transaction/connection.

### 35.4. Dùng FOR UPDATE khi FOR NO KEY UPDATE là đủ

Khóa mạnh hơn có thể chặn các transaction chỉ cần KEY SHARE để kiểm tra FK. Chọn đúng mức bảo vệ cần thiết.

### 35.5. Nhầm FOR KEY SHARE với FOR SHARE

KEY SHARE vẫn cho phép nhiều non-key UPDATE; SHARE thì xung đột với kiểu update đó.

### 35.6. Nghĩ FOR NO KEY UPDATE cho hai writer cùng sửa một hàng

Hai NO KEY UPDATE trên cùng hàng vẫn xung đột. Tương thích KEY SHARE không có nghĩa tương thích mọi thao tác ghi.

### 35.7. Dùng SKIP LOCKED để làm báo cáo đầy đủ

Nó bỏ qua hàng đang bị khóa, tạo một tập kết quả không đầy đủ.

### 35.8. Dùng NOWAIT rồi nghĩ không thể chờ bất kỳ lock nào

NOWAIT trong locking clause áp dụng cho row locks; table-level locks vẫn có thể chờ.

### 35.9. Không dùng OF trong JOIN

Câu FOR UPDATE không có OF có thể khóa cả các bảng được đọc để hiển thị, làm tăng tranh chấp không cần thiết.

### 35.10. Nghĩ SELECT FOR UPDATE khóa giá trị chưa tồn tại

Không có hàng thì không có row tuple để khóa. Dùng UNIQUE/ON CONFLICT cho bài toán tránh INSERT trùng.

### 35.11. Quên UPDATE/DELETE đã tự lấy khóa

Không phải mọi phép UPDATE đều cần một SELECT FOR UPDATE trước. Với một hàng, UPDATE có điều kiện thường đơn giản hơn.

### 35.12. Giữ khóa khi gọi API ngoài

Transaction dài gây chờ lock và rủi ro vận hành. Thiết kế state machine/idempotency nếu workflow ngoài database kéo dài.

### 35.13. Khóa nhiều hàng theo thứ tự khác nhau ở mỗi code path

Có thể tạo deadlock; chọn thứ tự nhất quán và retry transaction khi cần.

### 35.14. Chỉ retry statement cuối sau lỗi 40001

Nếu quyết định dựa trên các SELECT trước đó, phải retry **toàn transaction**.

### 35.15. Nghĩ pg_locks liệt kê đầy đủ mọi row lock đang giữ

Không phải mọi row lock đều có một bản ghi dễ đọc ở đó; dùng pg_blocking_pids, pg_stat_activity và hiểu tuple metadata.

### 35.16. Dùng FOR SHARE cho báo cáo dài không cần bảo vệ khỏi writer

Có thể khiến writer bị chặn lâu; plain SELECT và snapshot isolation thường phù hợp hơn.

### 35.17. Nghĩ FOR UPDATE tự ngăn write skew xuyên nhiều hàng

Khóa những hàng được chọn không bảo đảm mọi bất biến tập hợp đều đúng. Cần khóa đúng tập, constraint hoặc SERIALIZABLE.

### 35.18. Không xử lý kết quả 0 hàng sau khi chờ khóa

Ở READ COMMITTED, hàng có thể không còn thỏa WHERE sau khi transaction khác cập nhật và commit. Kết quả 0 hàng không nhất thiết là lỗi SQL.

### 35.19. Dùng OFFSET lớn trong locking query và tin chỉ khóa những hàng hiển thị

Những hàng bị bỏ qua bởi OFFSET có thể vẫn chịu khóa, tăng tranh chấp bất ngờ.

### 35.20. Coi lock_timeout như lịch chờ tối đa của toàn transaction

`lock_timeout` giới hạn việc chờ lấy khóa theo cách PostgreSQL quy định; `statement_timeout` và timeout ở ứng dụng là các cơ chế khác.

## 36. Bài tập thực hành có đáp án

Sử dụng dữ liệu lab mục 6. Với bài hai phiên, giữ A mở, chạy B, sau đó rollback cả hai. Nếu câu thử bị timeout hoặc NOWAIT báo lỗi, rollback phiên bị lỗi trước khi chạy tiếp.

### Bài 1. Khóa nào xung đột với mọi row lock khác?

**Đáp án:** `FOR UPDATE`. Nó xung đột với `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE` và `FOR KEY SHARE` trên cùng hàng.

### Bài 2. Hai FOR SHARE trên cùng hàng có chờ nhau không?

**Đáp án:** Không vì loại khóa hàng này tương thích với chính nó, trừ khi có yếu tố khác đang chặn (ví dụ khóa mạnh của transaction thứ ba hoặc table lock).

### Bài 3. FOR NO KEY UPDATE và FOR KEY SHARE

**Phiên A:**

~~~sql
BEGIN;
SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 1
FOR NO KEY UPDATE;
~~~

**Phiên B:**

~~~sql
BEGIN;
SELECT customer_id
FROM lock_lab.customers
WHERE customer_id = 1
FOR KEY SHARE NOWAIT;
ROLLBACK;
~~~

**Đáp án:** B có thể lấy KEY SHARE vì hai mode tương thích. Sau đó A rollback.

### Bài 4. FOR SHARE và FOR NO KEY UPDATE

**Câu hỏi:** A giữ FOR SHARE trên khách hàng 2, B yêu cầu FOR NO KEY UPDATE cùng hàng với NOWAIT.

**Đáp án:** Xung đột; B có thể nhận `55P03`.

### Bài 5. KEY SHARE có chặn UPDATE tier không?

~~~sql
UPDATE lock_lab.customers
SET tier = 'gold'
WHERE customer_id = 3;
~~~

**Đáp án:** Theo schema, `tier` không phải key cho FK nên là cập nhật không-key. Mode tương đương FOR NO KEY UPDATE và tương thích với KEY SHARE của A.

### Bài 6. KEY SHARE có chặn DELETE không?

**Đáp án:** Có. DELETE cần khóa hàng mạnh và xung đột KEY SHARE.

### Bài 7. Vì sao foreign key cần KEY SHARE?

**Đáp án:** Khi tạo hàng con trỏ tới hàng cha, hệ thống cần bảo vệ hàng cha khỏi bị xóa/đổi key xung đột trong lúc kiểm tra FK, nhưng không nhất thiết phải chặn cập nhật cột không-key của cha.

### Bài 8. NOWAIT khác SKIP LOCKED như thế nào?

**Đáp án:** NOWAIT báo lỗi khi gặp row lock xung đột; SKIP LOCKED bỏ qua hàng bị khóa và tiếp tục lấy những hàng có thể lấy được.

### Bài 9. Worker B chọn job nào?

A giữ FOR UPDATE trên job 1001. B chạy:

~~~sql
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 1
FOR UPDATE SKIP LOCKED;
~~~

**Đáp án:** Với seed và không có thay đổi khác, B có thể chọn **1002** vì 1001 đang bị khóa và 1002 là job pending ưu tiên tiếp theo.

### Bài 10. Vì sao phải UPDATE status khi claim job?

**Đáp án:** Row lock được giải phóng khi transaction kết thúc; nếu status vẫn pending, worker khác có thể chọn lại job. Cần lưu claim/trạng thái trong transaction và có recovery cho worker thất bại.

### Bài 11. JOIN khóa bảng nào?

~~~sql
SELECT o.order_id, c.full_name
FROM lock_lab.orders AS o
JOIN lock_lab.customers AS c
    ON c.customer_id = o.customer_id
WHERE o.order_id = 101
FOR UPDATE OF o;
~~~

**Đáp án:** Locking clause nhắm vào hàng của bảng `orders` ở vai trò `o`, không yêu cầu FOR UPDATE đối với hàng khách hàng `c` qua chính clause đó.

### Bài 12. READ COMMITTED sau khi phải chờ

A đang chờ khóa trên job pending; B đổi job thành running rồi commit.

**Đáp án:** A có thể tiếp tục với phiên bản đã được xử lý lại và không trả hàng đó nếu điều kiện `status='pending'` không còn đúng.

### Bài 13. REPEATABLE READ có thể lỗi gì?

**Đáp án:** Nếu cố lock/update hàng đã bị transaction khác thay đổi kể từ snapshot, PostgreSQL có thể báo `40001`; ứng dụng rollback rồi retry toàn transaction.

### Bài 14. Hai transaction khóa hai hàng theo thứ tự ngược

**Đáp án:** Có thể tạo deadlock. PostgreSQL phát hiện và abort một transaction với `40P01`; hãy dùng thứ tự khóa nhất quán và retry có kiểm soát.

### Bài 15. Vì sao SELECT FOR UPDATE không thay thế UNIQUE?

**Đáp án:** Khi truy vấn không thấy hàng trùng nào, nó không khóa một giá trị key chưa tồn tại để ngăn transaction khác INSERT. Unique constraint là hàng rào bảo vệ tính duy nhất.

### Bài 16. Dùng SELECT FOR UPDATE trước khi trừ stock 3 đơn vị có bắt buộc không?

**Đáp án:** Không nhất thiết. Nếu thao tác là một hàng, một câu UPDATE có điều kiện và RETURNING có thể đủ:

~~~sql
UPDATE lock_lab.products
SET stock_qty = stock_qty - 3
WHERE product_id = 101
  AND stock_qty >= 3
RETURNING product_id, stock_qty;
~~~

Với seed, kết quả stock là **7**. Khi làm bài trong lab, bọc bằng BEGIN/ROLLBACK.

### Bài 17. Xem ai đang chặn một session

~~~sql
SELECT
    pid,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blockers
FROM pg_stat_activity
WHERE datname = current_database();
~~~

**Đáp án:** `pg_blocking_pids(pid)` cung cấp danh sách PID có khả năng đang chặn session được kiểm tra, tùy thời điểm quan sát. Kết hợp query, transaction age và lock metadata để chẩn đoán.

### Bài 18. Khóa của SELECT FOR UPDATE giữ bao lâu?

**Đáp án:** Thường đến khi transaction COMMIT/ROLLBACK. Nếu autocommit bật, statement hoàn tất cũng kết thúc transaction, nên không bảo vệ câu lệnh gửi sau như một transaction mới.

### Bài 19. Vì sao không nên dùng FOR SHARE khi chỉ xem báo cáo?

**Đáp án:** Nó có thể chặn writer cần FOR NO KEY UPDATE trên những hàng được đọc, giảm concurrency. Plain SELECT với MVCC thường phù hợp hơn khi chỉ cần snapshot.

### Bài 20. Tạo phép thử SKIP LOCKED rồi rollback

**Phiên A:**

~~~sql
BEGIN;
SELECT job_id
FROM lock_lab.jobs
WHERE job_id = 1001
FOR UPDATE;
~~~

**Phiên B:**

~~~sql
BEGIN;
SELECT job_id
FROM lock_lab.jobs
WHERE status = 'pending'
ORDER BY priority DESC, job_id
LIMIT 2
FOR UPDATE SKIP LOCKED;
ROLLBACK;
~~~

**Đáp án:** Trong điều kiện seed, B có thể nhận **1002 và 1003**, bỏ qua job 1001. Sau khi A rollback, trạng thái dữ liệu không thay đổi.

## 37. Checklist chọn đúng khóa trong dự án thật

1. **Định nghĩa bất biến nghiệp vụ:** muốn bảo vệ khỏi sửa hàng, xóa hàng, đổi key hay chỉ bảo vệ FK?
2. **Xác định hàng đã tồn tại hay chưa:** với giá trị chưa tồn tại, row lock không thay thế UNIQUE.
3. **Ưu tiên DML nguyên tử khi đủ:** một UPDATE có điều kiện/RETURNING có thể đơn giản hơn SELECT FOR UPDATE rồi UPDATE.
4. **Nếu cần đọc–quyết định–ghi, dùng cùng transaction và connection.**
5. **Chọn khóa tối thiểu nhưng đủ mạnh:** KEY SHARE, SHARE, NO KEY UPDATE hoặc UPDATE theo ma trận xung đột.
6. **Phân biệt row lock và table lock:** NOWAIT/SKIP LOCKED trên hàng không loại bỏ mọi table-level wait.
7. **Với JOIN, chỉ định OF alias nếu chỉ cần khóa một bảng.**
8. **Với CTE, đặt locking clause ở nguồn cần khóa.**
9. **Không dùng SKIP LOCKED làm nguồn báo cáo đầy đủ.**
10. **Có fallback cho NOWAIT/timeout và kết quả 0 hàng.**
11. **Giữ transaction ngắn**, hạn chế gọi API ngoài khi giữ khóa.
12. **Đặt thứ tự khóa nhất quán** khi cần nhiều hàng/bảng.
13. **Xử lý 55P03, 40P01, 40001 theo nguyên nhân**, rollback và retry có giới hạn.
14. **Kiểm soát cách xử lý worker sau commit:** job claim không tự bảo đảm exactly-once hay phục hồi crash.
15. **Đo lock wait thực tế** với pg_stat_activity, pg_blocking_pids và pg_locks.
16. **Không dùng cột hệ thống như ctid/xmin để thay thế key nghiệp vụ** cho việc chọn hàng lâu dài.
17. **Kiểm thử bằng hai phiên thật** với cả tình huống B commit và B rollback.
18. **Kiểm tra isolation level**, vì READ COMMITTED và REPEATABLE READ phản ứng khác nhau khi gặp hàng vừa đổi.

## 38. Tài liệu PostgreSQL chính thức

Để đối chiếu cú pháp và quy tắc theo **major version PostgreSQL thực tế**, tham khảo:

- [Explicit Locking — Row-Level Locks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-ROWS): bốn chế độ row-level locks, ma trận xung đột và implicit locks từ DML.
- [SELECT](https://www.postgresql.org/docs/current/sql-select.html): `FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`; `OF`, `NOWAIT`, `SKIP LOCKED`, giới hạn với join/aggregation.
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): snapshots, READ COMMITTED, REPEATABLE READ, SERIALIZABLE.
- [Explicit Locking — Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-DEADLOCKS): phát hiện deadlock và thứ tự lấy khóa.
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` và các chỉ số đợi.
- [System View pg_locks](https://www.postgresql.org/docs/current/view-pg-locks.html): các lock được báo cáo và giới hạn khi quan sát row locks.
- [Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html): `55P03`, `40P01`, `40001`.
- [INSERT / ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html): chống tạo trùng bằng UNIQUE và upsert thay vì khóa một hàng chưa tồn tại.

Đường dẫn `/current/` trỏ tới tài liệu phiên bản PostgreSQL hiện hành trên website. Khi vận hành server có major version khác, nên mở tài liệu của **đúng phiên bản đó** để xác nhận từng chi tiết.

## 39. Tổng kết

Bốn locking clauses trong PostgreSQL không cùng một ý nghĩa:

| Mức khóa | Ghi nhớ ngắn |
| --- | --- |
| **`FOR UPDATE`** | Khóa mạnh nhất; xung đột tất cả row-level lock modes khác trên cùng hàng |
| **`FOR NO KEY UPDATE`** | Dành cho tình huống cập nhật không-key; vẫn tương thích `FOR KEY SHARE` |
| **`FOR SHARE`** | Nhiều transaction có thể cùng đọc chia sẻ; chặn cập nhật/xóa xung đột |
| **`FOR KEY SHARE`** | Bảo vệ khóa và sự tồn tại của hàng; cho phép non-key updates |

Ba nguyên tắc nền tảng:

1. **MVCC giúp SELECT thông thường không phải chờ writer trong nhiều trường hợp; locking SELECT là yêu cầu phối hợp bổ sung**, không thay thế snapshot.
2. **Chọn row lock theo ma trận xung đột, phạm vi hàng và nghiệp vụ**, thay vì luôn dùng FOR UPDATE theo thói quen.
3. **Khóa phải nằm trong một transaction được quản lý rõ ràng**. Với queue có thể dùng `SKIP LOCKED` và lưu trạng thái claim; với API cần phản hồi nhanh có thể dùng `NOWAIT`; với JOIN dùng `OF` để tránh khóa các bảng không liên quan.

Hiểu bốn chế độ này giúp bạn thiết kế những thao tác PostgreSQL **đúng khi nhiều phiên chạy đồng thời**, giảm khóa quá mức, nhận biết được các trường hợp phải chờ hoặc retry và tránh những lỗi logic mà một câu SELECT thông thường không tự ngăn được.
