# SERIALIZABLE và tác động đến khóa hoặc mức đồng thời

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích ý nghĩa của isolation level `SERIALIZABLE` và các bất thường đọc mà nó hướng tới ngăn chặn.
- Mô tả cách InnoDB triển khai `SERIALIZABLE`, đặc biệt việc chuyển plain `SELECT` thành shared locking read trong transaction tường minh.
- Phân biệt hành vi khi `autocommit` bật với khi nhiều câu lệnh nằm trong cùng transaction.
- Hiểu shared lock, record lock, gap lock và next-key lock ảnh hưởng thế nào đến thao tác ghi.
- Nhận diện trường hợp truy vấn phạm vi có thể chặn INSERT và tạo lock wait.
- Đánh giá ảnh hưởng của index, thứ tự truy cập và thời gian giữ transaction tới mức đồng thời.
- So sánh `SERIALIZABLE` với `REPEATABLE READ` và `READ COMMITTED` trong InnoDB.
- Chọn isolation level theo yêu cầu nhất quán, tải đọc/ghi và khả năng xử lý deadlock.
- Cấu hình isolation level trong SQL và Java JDBC, đồng thời kiểm tra bằng hai session.

## 1. SERIALIZABLE là gì?

`SERIALIZABLE` là isolation level cao nhất trong bốn mức isolation tiêu chuẩn mà InnoDB cung cấp. Mục tiêu của nó là làm cho kết quả của các transaction đồng thời tương đương với một thứ tự thực thi tuần tự nào đó: mỗi transaction có thể được xem như chạy trọn vẹn trước hoặc sau transaction khác, thay vì tạo ra kết quả không thể giải thích bằng bất kỳ thứ tự tuần tự nào.

Mức này hướng tới việc ngăn các bất thường như:

- **Dirty read:** đọc dữ liệu do transaction khác ghi nhưng chưa commit.
- **Non-repeatable read:** đọc cùng một hàng nhiều lần trong một transaction nhưng nhận giá trị khác nhau do transaction khác commit thay đổi.
- **Phantom read:** chạy lại một điều kiện phạm vi và thấy thêm hoặc mất các hàng phù hợp do transaction khác INSERT/DELETE.
- Các kết quả đọc/ghi không thể sắp xếp thành một thứ tự tuần tự hợp lệ.

Đổi lại, `SERIALIZABLE` thường cần nhiều khóa hơn, làm các transaction xung đột phải chờ nhau và giảm khả năng xử lý đồng thời. Nó không có nghĩa MySQL chỉ cho phép một transaction chạy trên toàn server tại một thời điểm. Các transaction vẫn có thể chạy song song nếu chúng không xung đột trên dữ liệu hoặc tài nguyên cần khóa.

## 2. SERIALIZABLE trong InnoDB hoạt động thế nào?

InnoDB sử dụng MVCC cho consistent read và cơ chế khóa cho locking read, UPDATE, DELETE cùng các thao tác cần bảo vệ dữ liệu. Ở các isolation level thấp hơn, một plain `SELECT` thông thường có thể đọc từ snapshot mà không khóa các hàng đang đọc.

Với `SERIALIZABLE`, hành vi của plain `SELECT` thay đổi tùy cách transaction được sử dụng:

- Khi `autocommit` bị tắt hoặc câu lệnh nằm trong một transaction tường minh, InnoDB ngầm chuyển plain `SELECT` thành một locking read tương đương `SELECT ... FOR SHARE`.
- Khi `autocommit = 1` và một plain `SELECT` là transaction duy nhất của nó, câu đọc đó là một transaction chỉ đọc riêng lẻ; InnoDB có thể serialize transaction đọc này mà không cần giữ shared lock qua nhiều câu lệnh.

Đây là điểm quan trọng khi kiểm tra `SERIALIZABLE`: chỉ đặt isolation level rồi chạy một câu SELECT đơn lẻ không chứng minh được cách khóa của một transaction gồm nhiều câu lệnh. Muốn kiểm tra tác động khóa trong transaction, hãy bắt đầu transaction tường minh.

### 2.1. Plain SELECT trong transaction tường minh

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;

-- Trong SERIALIZABLE, plain SELECT này có hành vi shared locking read.
SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Các câu lệnh khác của nghiệp vụ...

COMMIT;
```

Shared lock được giữ theo thời gian sống của transaction. Transaction khác vẫn có thể đọc cùng hàng bằng shared lock, nhưng thao tác cần exclusive lock như UPDATE/DELETE trên hàng đó phải chờ cho đến khi shared lock được giải phóng.

### 2.2. So sánh với REPEATABLE READ

Với `REPEATABLE READ` (mức mặc định thường gặp của InnoDB), plain `SELECT` là consistent read và đọc từ snapshot của transaction. Các lần đọc thông thường trong cùng transaction nhìn thấy cùng snapshot, nhưng không đặt shared lock trên các hàng chỉ vì đang đọc chúng.

Với `SERIALIZABLE`, plain `SELECT` trong transaction tường minh được chuyển thành shared locking read. Vì vậy, transaction đọc có thể chặn transaction ghi vào các hàng hoặc phạm vi mà nó khóa.

Không nên hiểu `REPEATABLE READ` là không có khóa: `SELECT ... FOR UPDATE`, `SELECT ... FOR SHARE`, UPDATE và DELETE vẫn dùng khóa theo quy tắc InnoDB. Điểm khác biệt chính ở đây là cách xử lý plain SELECT.

## 3. Cấu hình isolation level SERIALIZABLE

MySQL cho phép đặt isolation level ở các phạm vi khác nhau. Nên cấu hình trước khi bắt đầu transaction.

### 3.1. Kiểm tra mức hiện tại

```sql
SELECT
    @@SESSION.transaction_isolation AS session_isolation,
    @@GLOBAL.transaction_isolation AS global_isolation,
    @@SESSION.autocommit AS session_autocommit;
```

`SESSION` là giá trị áp dụng cho connection hiện tại. `GLOBAL` là giá trị mặc định cho các connection mới; thay đổi GLOBAL không tự thay đổi isolation level của các session đang mở.

### 3.2. Đặt mặc định cho session hiện tại

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;
SELECT * FROM accounts WHERE account_id = 101;
COMMIT;
```

Các transaction tiếp theo trên connection hiện tại dùng `SERIALIZABLE` cho tới khi isolation level của session được thay đổi.

### 3.3. Chỉ đặt cho transaction kế tiếp

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

COMMIT;
```

`SET TRANSACTION` không có `GLOBAL` hoặc `SESSION` đặt đặc tính cho transaction kế tiếp. Đây là lựa chọn phù hợp khi chỉ một đơn vị nghiệp vụ cần isolation level khác với mặc định của connection.

### 3.4. Đặt mặc định toàn server

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL SERIALIZABLE;
```

Thao tác này ảnh hưởng các session được tạo sau đó và cần quyền quản trị phù hợp. Không nên thay đổi GLOBAL chỉ để xử lý một truy vấn riêng. Nếu thay đổi mặc định server, hãy đánh giá tác động tới toàn bộ workload và cách ứng dụng mở connection.

### 3.5. Không đổi isolation level giữa transaction đang chạy

Hãy đặt isolation level trước `START TRANSACTION`. MySQL không cho đổi đặc tính transaction khi transaction đã bắt đầu. Nếu cần mức khác, kết thúc transaction hiện tại bằng `COMMIT` hoặc `ROLLBACK`, sau đó cấu hình cho transaction kế tiếp.

Tên biến `transaction_isolation` dùng trong MySQL 8.0; một số phiên bản cũ sử dụng tên `tx_isolation` đã lỗi thời. Luôn xác minh phiên bản server mục tiêu.

## 4. Shared lock và tác động tới thao tác ghi

Trong transaction `SERIALIZABLE`, plain SELECT được xử lý như shared locking read. Shared lock cho phép các transaction khác cùng giữ shared lock tương thích trên dữ liệu đó, nhưng xung đột với exclusive lock mà thao tác ghi cần có.

Ví dụ Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101;

-- Chưa COMMIT hoặc ROLLBACK; shared lock vẫn được giữ.
```

Trong lúc đó, Session B:

```sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 101;
```

UPDATE ở Session B cần khóa độc quyền trên hàng tài khoản. Nó phải chờ Session A kết thúc transaction và giải phóng shared lock.

Khi Session A chạy:

```sql
COMMIT;
```

Session B mới có thể tiếp tục, tùy trạng thái transaction và các khóa khác.

### 4.1. Shared lock không chặn mọi hoạt động đọc

Nhiều shared lock có thể cùng tồn tại trên một hàng. Vì thế, một transaction đọc không nhất thiết chặn transaction đọc khác. Xung đột chủ yếu xảy ra khi transaction khác cần exclusive lock để thay đổi hàng hoặc cần khóa phạm vi bị transaction hiện tại bảo vệ.

### 4.2. Hai transaction cùng đọc rồi cùng muốn ghi

Một tình huống dễ gây deadlock:

1. Session A đọc hàng X và giữ shared lock.
2. Session B cũng đọc hàng X và giữ shared lock.
3. Session A muốn UPDATE X nên cần nâng lên exclusive lock, nhưng phải chờ shared lock của B.
4. Session B cũng muốn UPDATE X, nhưng phải chờ shared lock của A.

InnoDB phát hiện deadlock và rollback một transaction làm nạn nhân. Nếu biết ngay từ đầu rằng nghiệp vụ sẽ đọc rồi sửa hàng, hãy cân nhắc locking read tường minh bằng `SELECT ... FOR UPDATE` thay vì cả hai transaction cùng lấy shared lock rồi chuyển sang ghi.

`FOR UPDATE` cũng làm tăng mức xung đột; chỉ dùng khi thật sự cần đọc rồi cập nhật trong cùng transaction.

## 5. Gap lock và next-key lock: vì sao INSERT có thể bị chặn?

Để ngăn phantom read, InnoDB có thể khóa không chỉ các index record đang tồn tại mà còn cả khoảng trống giữa các record trong một range scan.

- **Record lock:** khóa một index record.
- **Gap lock:** khóa một khoảng trống giữa các index record, ngăn transaction khác chèn index record vào khoảng đó.
- **Next-key lock:** kết hợp khóa index record với khoảng trống ngay trước record đó.

Trong các locking read ở `REPEATABLE READ` và `SERIALIZABLE`, InnoDB có thể dùng next-key lock cho các index range scan. Điều này bảo vệ phạm vi điều kiện truy vấn khỏi việc xuất hiện thêm hàng phù hợp trước khi transaction kết thúc.

### 5.1. Ví dụ truy vấn phạm vi

Giả sử có bảng:

```sql
CREATE TABLE products (
    product_id BIGINT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    product_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (product_id),
    KEY idx_products_price (price)
) ENGINE = InnoDB;
```

Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT product_id, price, product_name
FROM products
WHERE price >= 100
  AND price < 200
ORDER BY price, product_id;

-- Giữ transaction mở để quan sát khóa.
```

Vì Session A đang ở `SERIALIZABLE` trong transaction tường minh, plain SELECT hoạt động như shared locking read. Với access path dùng index `idx_products_price`, InnoDB có thể khóa các record và gap liên quan đến range được quét.

Session B thử thêm sản phẩm có giá nằm trong khoảng:

```sql
INSERT INTO products (product_id, price, product_name)
VALUES (90001, 150, 'New product');
```

INSERT có thể phải chờ vì cần chèn index record vào gap đang được Session A khóa. Sau khi Session A chạy `COMMIT` hoặc `ROLLBACK`, Session B mới có thể tiếp tục nếu không còn xung đột khác.

Phạm vi khóa chính xác phụ thuộc execution plan, index được chọn và các giá trị đang có. Ví dụ này minh họa cơ chế; khi kiểm tra trên môi trường thật, cần xem index và trạng thái khóa thực tế.

### 5.2. Tra cứu bằng unique key khác với quét range

Nếu truy vấn dùng điều kiện bằng trên toàn bộ một unique index để tìm đúng một record, InnoDB thường chỉ cần record lock cho record được tìm thấy, không cần khóa gap trước nó.

Ví dụ:

```sql
SELECT account_id, balance
FROM accounts
WHERE account_id = 101;
```

Nếu `account_id` là primary key, truy vấn là unique point lookup. Nó thường có lock footprint hẹp hơn range scan trên cột không unique.

Ngược lại, điều kiện như:

```sql
SELECT product_id, price
FROM products
WHERE price BETWEEN 100 AND 200;
```

có thể quét nhiều index record và các gap liên quan. Nếu cột `price` không unique, một giá trị có thể khớp nhiều sản phẩm.

Không suy luận lock chỉ từ câu SQL. Cần xem optimizer dùng index nào và InnoDB đã khóa những index record/gap nào.

## 6. Index quyết định phạm vi khóa và mức đồng thời

Index không chỉ ảnh hưởng tốc độ truy vấn. Với locking read và các thao tác ghi, access path có thể ảnh hưởng đáng kể đến số record và gap mà InnoDB phải khóa.

### 6.1. Index phù hợp giúp khóa chính xác hơn

Giả sử truy vấn thường xuyên đọc phạm vi theo `warehouse_id` và `product_id`:

```sql
SELECT product_id, quantity
FROM inventory
WHERE warehouse_id = 10
  AND product_id BETWEEN 1000 AND 1100;
```

Một index phù hợp có thể là:

```sql
CREATE INDEX idx_inventory_warehouse_product
ON inventory (warehouse_id, product_id);
```

Index ghép giúp InnoDB tìm phạm vi liên quan tới một kho và dải sản phẩm. Nếu không có index phù hợp, optimizer có thể phải quét nhiều record hơn, làm phạm vi khóa lớn hơn và tăng khả năng chặn transaction không liên quan.

Thứ tự cột index phải dựa trên điều kiện lọc, độ chọn lọc và các truy vấn thực tế. Không tạo index chỉ theo ví dụ; hãy kiểm tra bằng `EXPLAIN` và đo workload.

### 6.2. Index quá rộng cũng có chi phí

Thêm index giúp truy vấn tìm hàng hiệu quả hơn nhưng làm tăng dung lượng, chi phí INSERT/UPDATE/DELETE và số cấu trúc cần duy trì. Nên có index cho access path quan trọng, không tạo mọi tổ hợp cột có thể nghĩ ra.

### 6.3. Kiểm tra access path

```sql
EXPLAIN
SELECT product_id, price, product_name
FROM products
WHERE price >= 100
  AND price < 200
ORDER BY price, product_id;
```

Quan sát `key`, `type`, số hàng ước lượng và phần điều kiện lọc. Nếu server hỗ trợ, `EXPLAIN FORMAT=TREE` có thể giúp đọc luồng thực thi. `EXPLAIN ANALYZE` thực sự chạy truy vấn, vì vậy chỉ dùng với câu lệnh và môi trường phù hợp.

## 7. SERIALIZABLE ngăn phantom nhưng có thể tạo lock wait

Phantom read là trường hợp một transaction chạy lại truy vấn theo cùng điều kiện phạm vi và thấy thêm hoặc mất hàng phù hợp do transaction khác thay đổi tập hàng đó.

Ví dụ nghiệp vụ kiểm tra số chỗ còn trống:

```sql
SELECT reservation_id
FROM reservations
WHERE room_id = 20
  AND reserved_at >= '2026-12-01'
  AND reserved_at < '2026-12-02';
```

Nếu logic nghiệp vụ dựa trên số hàng hiện có để quyết định có thể thêm reservation hay không, chỉ đọc một snapshot mà không khóa phạm vi có thể chưa đủ. Trong transaction `SERIALIZABLE`, shared locking read và next-key locking có thể ngăn transaction khác chèn record phù hợp vào range đang được bảo vệ.

Tuy nhiên, khóa phạm vi có thể làm các yêu cầu đặt phòng độc lập nhưng nằm gần nhau trên cùng index phải chờ. Nếu thiết kế index không phù hợp, lock footprint có thể lớn hơn mong đợi.

### 7.1. SERIALIZABLE không thay thế constraint nghiệp vụ

Nếu quy tắc có thể biểu diễn bằng unique key hoặc constraint, hãy dùng constraint để bảo vệ ở cấp database. Ví dụ, nếu mỗi người dùng chỉ được có một reservation cho một slot duy nhất, unique index trên các cột định danh phù hợp có thể là lớp bảo vệ trực tiếp hơn.

Không phải mọi quy tắc chống trùng đều biểu diễn được bằng unique key, đặc biệt với khoảng thời gian chồng lấn. Khi đó, cần kết hợp transaction, locking strategy, mô hình dữ liệu và kiểm tra nghiệp vụ phù hợp.

### 7.2. Cân nhắc locking read tường minh ở mức thấp hơn

Nếu chỉ một phần nghiệp vụ cần khóa phạm vi hoặc khóa hàng, có thể giữ isolation level mặc định và dùng `SELECT ... FOR UPDATE` hoặc `SELECT ... FOR SHARE` tại đúng vị trí. Cách này cho phép chọn rõ phạm vi locking read thay vì biến mọi plain SELECT trong transaction thành shared locking read.

Ví dụ:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT account_id, balance
FROM accounts
WHERE account_id = 101
FOR UPDATE;

-- Kiểm tra và cập nhật cùng hàng trong transaction.

COMMIT;
```

Lựa chọn này không tương đương hoàn toàn với `SERIALIZABLE` cho mọi truy vấn và mọi bất thường. Nó phù hợp khi ứng dụng xác định được chính xác dữ liệu cần khóa.

## 8. Tác động tới mức đồng thời và hiệu năng

`SERIALIZABLE` thường làm giảm concurrency so với `REPEATABLE READ` vì plain SELECT trong transaction tường minh giữ shared lock. Tác động phụ thuộc vào mức độ chồng lấn dữ liệu và thời gian transaction mở.

Các hệ quả thường gặp:

- UPDATE/DELETE phải chờ khi hàng đang được transaction khác giữ shared lock.
- INSERT có thể chờ khi cần chèn vào gap bị khóa.
- Các transaction đọc cùng dữ liệu có thể cùng giữ shared lock.
- Transaction đọc rồi chuyển sang ghi có thể gặp deadlock do nâng cấp lock.
- Transaction dài giữ khóa lâu, làm tăng lock wait và giảm thông lượng.
- Range scan rộng hoặc thiếu index có thể khóa nhiều record/gap hơn cần thiết.
- Nhiều transaction cùng truy cập một vùng index nóng có thể tạo hàng đợi chờ.

### 8.1. SERIALIZABLE không có nghĩa khóa toàn bộ database

InnoDB khóa record và index range theo access path, không phải mặc định đặt một mutex toàn server. Hai transaction thao tác trên những hàng độc lập có thể vẫn chạy đồng thời. Tuy nhiên, một truy vấn quét phạm vi rộng hoặc thiếu index có thể tạo phạm vi khóa lớn và khiến nhiều transaction không liên quan về mặt nghiệp vụ vẫn bị ảnh hưởng.

### 8.2. Giữ transaction ngắn

Ví dụ không nên làm:

1. Mở transaction `SERIALIZABLE`.
2. Đọc nhiều hàng và giữ shared lock.
3. Gọi dịch vụ HTTP hoặc chờ người dùng xác nhận.
4. Sau vài giây mới cập nhật và commit.

Trong thời gian chờ, các thao tác ghi có thể bị chặn. Hãy thực hiện bước tính toán hoặc gọi dịch vụ ngoài trước khi mở transaction nếu an toàn; sau đó mở transaction ngắn, đọc/khóa lại dữ liệu cần thiết, xác minh điều kiện và ghi.

Không di chuyển bước đọc ra ngoài transaction nếu điều đó làm mất bảo đảm nhất quán. Hãy thiết kế lại quy trình để phần cần bảo vệ vẫn được kiểm tra bên trong transaction ngắn.

### 8.3. Theo dõi lock wait và deadlock

Khi hệ thống dùng `SERIALIZABLE`, theo dõi:

- Thời gian chờ khóa và tỷ lệ lock wait timeout.
- Số lượng deadlock và transaction bị rollback.
- Transaction tồn tại lâu và connection giữ transaction mở.
- Truy vấn range scan có số hàng lớn.
- Index được chọn và sự thay đổi execution plan sau khi dữ liệu tăng.

Có thể điều tra bằng `SHOW ENGINE INNODB STATUS` và các bảng `performance_schema` liên quan đến data locks/lock waits trên phiên bản hỗ trợ. Cần quyền phù hợp và chọn đúng công cụ quan sát cho phiên bản server.

## 9. So sánh SERIALIZABLE, REPEATABLE READ và READ COMMITTED

| Khía cạnh | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|
| Plain SELECT thông thường | Consistent read theo snapshot của từng statement | Consistent read theo snapshot của transaction | Trong transaction tường minh, chuyển thành shared locking read |
| Đọc lại cùng hàng | Có thể thấy commit mới ở statement sau | Thường giữ cùng snapshot trong transaction | Khóa đọc làm transaction ghi xung đột phải chờ |
| Phantom với plain consistent read | Có thể thấy tập hàng khác ở statement sau | Snapshot của transaction giữ tập nhìn thấy ổn định | Khóa phạm vi trong locking read để ngăn thay đổi phantom cho phạm vi được quét |
| Gap/next-key locking | Giảm gap locking cho nhiều thao tác thông thường; vẫn có ngoại lệ như FK/duplicate check | Dùng trong nhiều locking read và thao tác ghi | Dùng cho locking read phát sinh từ plain SELECT trong transaction |
| Khả năng đồng thời | Thường cao hơn | Cân bằng giữa nhất quán và concurrency | Thường thấp hơn khi nhiều transaction đọc/ghi cùng vùng dữ liệu |
| Trường hợp phù hợp | Workload cần dữ liệu mới ở mỗi statement và concurrency cao | Workload OLTP phổ biến cần snapshot ổn định trong transaction | Nghiệp vụ cần thứ tự tuần tự nghiêm ngặt và chấp nhận chi phí khóa |

Bảng trên mô tả hành vi phổ biến của InnoDB. Chi tiết khóa phụ thuộc loại câu lệnh, index, access path, isolation level, autocommit và phiên bản MySQL.

## 10. Thực hành kiểm tra bằng hai session

Thực hành sau giúp quan sát việc một plain SELECT ở `SERIALIZABLE` giữ shared lock và có thể chặn UPDATE/INSERT.

### 10.1. Chuẩn bị dữ liệu

Chạy một lần trong schema thử nghiệm:

```sql
DROP TABLE IF EXISTS serializable_demo;

CREATE TABLE serializable_demo (
    item_id BIGINT NOT NULL,
    item_value INT NOT NULL,
    description VARCHAR(100) NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_item_value (item_value)
) ENGINE = InnoDB;

INSERT INTO serializable_demo (item_id, item_value, description)
VALUES
    (1, 10, 'A'),
    (2, 20, 'B'),
    (3, 30, 'C'),
    (4, 40, 'D');
```

### 10.2. Session A: đọc và giữ transaction

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT item_id, item_value, description
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

Giữ Session A mở, chưa commit.

### 10.3. Session B: thử cập nhật hàng đang đọc

Mở một connection khác và chạy:

```sql
UPDATE serializable_demo
SET description = 'Changed'
WHERE item_id = 2;
```

UPDATE có thể bị chặn vì Session A đang giữ shared lock trên hàng phù hợp. Trong lúc Session B chờ, quay lại Session A:

```sql
COMMIT;
```

Sau khi Session A commit, Session B có thể tiếp tục.

### 10.4. Thử INSERT vào phạm vi được đọc

Lặp lại Session A:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL SERIALIZABLE;
START TRANSACTION;

SELECT item_id, item_value
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

Trong Session B:

```sql
INSERT INTO serializable_demo (item_id, item_value, description)
VALUES (5, 25, 'Inserted in range');
```

Nếu access path dùng index `idx_item_value` và phạm vi gap tương ứng đang được khóa, INSERT có thể chờ Session A kết thúc transaction. Sau `COMMIT` hoặc `ROLLBACK` ở Session A, kiểm tra Session B tiếp tục và dữ liệu được chèn.

Kết quả chi tiết phụ thuộc access path và index. Dùng `EXPLAIN` trước khi thử và không chạy bài thực hành trên dữ liệu production.

### 10.5. So sánh với REPEATABLE READ

Đặt Session A về `REPEATABLE READ`, sau đó chạy plain SELECT trong transaction:

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT item_id, item_value
FROM serializable_demo
WHERE item_value >= 20
  AND item_value < 40
ORDER BY item_value, item_id;
```

Plain consistent read ở `REPEATABLE READ` không lấy shared lock chỉ vì đọc. Session B thường có thể UPDATE hàng hoặc INSERT giá trị mới phù hợp mà không phải chờ shared lock của plain SELECT. Session A tiếp tục đọc theo snapshot của nó trong transaction.

Kết thúc Session A bằng `COMMIT` hoặc `ROLLBACK` trước khi lặp lại thử nghiệm khác.

## 11. Sử dụng SERIALIZABLE trong Java JDBC

JDBC có hằng số `Connection.TRANSACTION_SERIALIZABLE` để yêu cầu isolation level cho connection:

```java
try (Connection connection = dataSource.getConnection()) {
    int originalIsolation = connection.getTransactionIsolation();
    boolean originalAutoCommit = connection.getAutoCommit();
    boolean reusable = false;
    Throwable primaryFailure = null;

    try {
        connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
        connection.setAutoCommit(false);

        // Tất cả câu lệnh của nghiệp vụ dùng cùng connection.
        // Đọc, xác minh điều kiện và ghi dữ liệu cần thiết.

        connection.commit();
        reusable = true;
    } catch (SQLException | RuntimeException ex) {
        primaryFailure = ex;
        try {
            connection.rollback();
            reusable = true;
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        if (reusable) {
            try {
                connection.setAutoCommit(originalAutoCommit);
                connection.setTransactionIsolation(originalIsolation);
            } catch (SQLException resetError) {
                poolAdapter.invalidate(connection);
                if (primaryFailure != null) {
                    primaryFailure.addSuppressed(resetError);
                } else {
                    throw resetError;
                }
            }
        } else {
            poolAdapter.invalidate(connection);
        }
    }
}
```

`poolAdapter.invalidate(connection)` trong ví dụ là lời gọi minh họa tới API loại bỏ connection của pool đang dùng; đây không phải API chuẩn của JDBC. Nếu rollback thất bại, không reset `autocommit` bằng cách bật nó lên vì thao tác đó có thể commit transaction còn trạng thái không xác định. Hãy loại bỏ connection trước khi nó được trả về pool. Nếu reset thuộc tính thất bại, cũng phải evict connection. Khi `commit()` ném lỗi do mất kết nối, trạng thái commit có thể chưa xác định; cần idempotency key hoặc cách truy vấn trạng thái nghiệp vụ trước khi retry.

### 11.1. Chỉ dùng SERIALIZABLE cho transaction cần thiết

Không nhất thiết đặt mọi connection của ứng dụng ở `SERIALIZABLE`. Có thể giữ isolation level thông thường cho phần lớn workload và chỉ nâng isolation cho transaction có yêu cầu rõ ràng.

Ví dụ, một nghiệp vụ kiểm tra nhiều hàng trong một phạm vi rồi quyết định ghi có thể cần đánh giá `SERIALIZABLE`; các truy vấn đọc danh sách sản phẩm thông thường thường không cần giữ shared lock trên phạm vi trong suốt transaction.

### 11.2. Xử lý deadlock và timeout

Ứng dụng phải chuẩn bị cho các lỗi concurrency:

- Nếu InnoDB phát hiện deadlock, một transaction bị chọn làm nạn nhân và bị rollback.
- Nếu lock wait timeout xảy ra, phạm vi rollback phụ thuộc cấu hình; ứng dụng nên rollback toàn transaction trước khi retry hoặc trả connection về pool.
- Chỉ retry khi nghiệp vụ an toàn để thực hiện lại; dùng idempotency key hoặc unique request identifier nếu có thể phát sinh lặp thao tác.
- Retry toàn bộ transaction trên connection ở trạng thái sạch, với số lần giới hạn và backoff phù hợp.

Không retry vô hạn. Nếu lỗi lặp lại, cần xem xét thứ tự khóa, index, thời gian transaction và mô hình dữ liệu.

## 12. Khi nào nên chọn SERIALIZABLE?

`SERIALIZABLE` phù hợp khi yêu cầu đúng đắn của nghiệp vụ khó đảm bảo bằng constraint hoặc locking strategy hẹp hơn, và hệ thống chấp nhận chi phí concurrency.

Có thể cân nhắc khi:

- Một quyết định ghi phụ thuộc vào kết quả của truy vấn phạm vi và cần ngăn transaction khác làm thay đổi tập hàng đó trước khi commit.
- Quy tắc nghiệp vụ liên quan nhiều hàng mà không thể biểu diễn đầy đủ bằng unique constraint hoặc một phép cập nhật nguyên tử.
- Độ chính xác của kết quả quan trọng hơn thông lượng tối đa và mức xung đột dữ liệu tương đối thấp.
- Đã kiểm thử lock wait, deadlock và throughput dưới tải đại diện.

Không nên chọn chỉ vì muốn “an toàn hơn” mà chưa xác định bất thường cần ngăn chặn. Với nhiều nghiệp vụ, các lựa chọn sau có thể hiệu quả hơn:

- Unique key hoặc CHECK constraint để bảo vệ invariant trực tiếp.
- UPDATE có điều kiện, ví dụ `UPDATE ... WHERE quantity >= ?`.
- `SELECT ... FOR UPDATE` để khóa các hàng cần đọc rồi sửa.
- `SELECT ... FOR SHARE` khi cần shared locking read tường minh.
- `REPEATABLE READ` với snapshot nhất quán khi chỉ cần đọc ổn định.
- Thiết kế lại transaction để giảm phạm vi dữ liệu và thời gian giữ khóa.

## 13. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế | Cách xử lý |
|---|---|---|
| SERIALIZABLE khóa toàn bộ database | InnoDB khóa record/index range theo access path; dữ liệu độc lập vẫn có thể xử lý đồng thời | Xem phạm vi khóa và truy vấn thực tế |
| Mọi SELECT ở SERIALIZABLE luôn khóa | Với autocommit bật, một SELECT riêng lẻ là read-only transaction và không cần giữ khóa qua nhiều statement | Kiểm tra autocommit và dùng transaction tường minh khi thử locking behavior |
| Shared lock chặn mọi transaction đọc | Shared lock tương thích với shared lock khác | Phân biệt xung đột đọc-đọc với đọc-ghi |
| SERIALIZABLE chỉ khóa các hàng đang tồn tại | Range scan có thể lấy next-key/gap lock để ngăn INSERT tạo phantom | Kiểm tra index và điều kiện range |
| Có index thì không còn lock wait | Index giúp thu hẹp access path nhưng các record/gap cần bảo vệ vẫn có thể xung đột | Thiết kế index và transaction theo nghiệp vụ |
| SERIALIZABLE loại bỏ deadlock | Nâng cấp shared lock, thứ tự khóa khác nhau và nhiều transaction vẫn có thể tạo deadlock | Xử lý deadlock và retry toàn transaction |
| REPEATABLE READ không dùng gap lock | Locking read và thao tác ghi ở REPEATABLE READ vẫn có thể dùng next-key lock | Phân biệt plain consistent read với locking read |
| Chỉ cần nâng isolation level là đủ bảo vệ invariant | Isolation không thay thế constraint, kiểm tra nghiệp vụ và idempotency | Dùng nhiều lớp bảo vệ phù hợp |

## 14. Quy trình đánh giá trước khi bật SERIALIZABLE

1. **Mô tả bất thường cần ngăn chặn:** dirty read, non-repeatable read, phantom hay quyết định ghi dựa trên một phạm vi dữ liệu?
2. **Kiểm tra constraint:** có thể dùng unique key, CHECK hoặc UPDATE có điều kiện để bảo vệ invariant không?
3. **Xác định phạm vi transaction:** câu SELECT nào cần được bảo vệ và transaction phải giữ khóa đến thời điểm nào?
4. **Kiểm tra autocommit:** plain SELECT đơn lẻ và SELECT trong transaction tường minh có hành vi khác nhau.
5. **Xem index và access path:** range scan có thể khóa record/gap nào; thiếu index có làm phạm vi quét rộng không?
6. **Mô phỏng hai session:** thử đọc, UPDATE và INSERT ở các vùng khóa chồng lấn.
7. **Đo dưới tải:** theo dõi throughput, latency, lock wait timeout và deadlock.
8. **Thiết kế retry:** rollback transaction thất bại và retry toàn bộ đơn vị nghiệp vụ có giới hạn.
9. **Triển khai theo phạm vi nhỏ:** chỉ nâng isolation cho transaction cần thiết, theo dõi trước khi mở rộng.

## 15. Checklist production

- [ ] Đã xác định bất thường dữ liệu cụ thể cần ngăn chặn.
- [ ] Đã xác nhận bảng tham gia dùng InnoDB.
- [ ] Isolation level được đặt trước khi transaction bắt đầu.
- [ ] Đã kiểm tra `@@SESSION.transaction_isolation` và `@@SESSION.autocommit`.
- [ ] Đã hiểu plain SELECT trong transaction tường minh ở SERIALIZABLE là shared locking read.
- [ ] Đã xem xét hành vi autocommit của SELECT đơn lẻ.
- [ ] Truy vấn phạm vi có index phù hợp và lock footprint đã được kiểm tra.
- [ ] Đã đánh giá khả năng gap/next-key lock chặn INSERT.
- [ ] Transaction ngắn và không chờ HTTP, người dùng hoặc tác vụ ngoài database khi đang giữ khóa.
- [ ] Có xử lý deadlock, lock wait timeout và retry có giới hạn.
- [ ] Đã so sánh với REPEATABLE READ, locking read tường minh hoặc constraint.
- [ ] Đã đo throughput và latency trên workload đại diện.
- [ ] Connection được reset isolation/autocommit hoặc bị loại khỏi pool khi reset thất bại.

## 16. Kết luận

`SERIALIZABLE` yêu cầu các transaction có kết quả tương đương một thứ tự chạy tuần tự. Trong InnoDB, khi `autocommit` tắt hoặc plain SELECT nằm trong transaction tường minh, SELECT thông thường được chuyển thành shared locking read. Với truy vấn phạm vi, InnoDB có thể dùng next-key/gap lock để ngăn INSERT tạo phantom. Khi autocommit bật và SELECT là transaction đọc độc lập, câu đọc đó có thể được serialize mà không cần giữ khóa qua nhiều câu lệnh.

Mức isolation này tăng bảo đảm nhất quán nhưng cũng làm tăng lock wait, deadlock và chi phí đồng thời. Index quyết định access path và phạm vi khóa; transaction dài làm xung đột kéo dài. Hãy chọn `SERIALIZABLE` khi nghiệp vụ thực sự cần, kiểm tra bằng nhiều session, ưu tiên constraint hoặc locking strategy hẹp hơn khi đủ đáp ứng, và đo hiệu năng trước khi áp dụng rộng rãi.
