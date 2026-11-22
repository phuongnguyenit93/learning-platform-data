# Chỉ mục phụ, tra cứu về hàng gốc và thứ tự lấy khóa

Trong InnoDB, chỉ mục phụ (secondary index) giúp tìm hàng mà không phải quét toàn bộ clustered index. Tuy nhiên, một entry của chỉ mục phụ thường không chứa toàn bộ dữ liệu của hàng. Nó chứa giá trị cột được lập chỉ mục cùng khóa chính để InnoDB tìm đến hàng gốc trong clustered index.

Với truy vấn chỉ đọc thông thường, việc tra cứu về clustered index có thể cần thiết để lấy các cột chưa có trong chỉ mục. Với locking read hoặc thao tác ghi, cơ chế khóa còn phải bảo vệ bản ghi dữ liệu tương ứng. Vì vậy, một câu SQL lọc qua secondary index có thể tạo khóa trên cả entry của secondary index và hàng trong clustered index. Thứ tự quét index và đường tra cứu ảnh hưởng đến thứ tự lấy khóa, từ đó có thể góp phần tạo blocking hoặc deadlock.

Bài này tập trung vào MySQL InnoDB. Chi tiết lock mode và cách hiển thị phụ thuộc isolation level, execution plan, phiên bản MySQL và loại câu lệnh. Khi cần biết phạm vi thật, hãy xem execution plan và lock instrumentation trong lúc transaction còn mở.

## 1. Clustered index và secondary index lưu gì?

InnoDB tổ chức dữ liệu bảng theo clustered index. Thông thường clustered index chính là khóa chính (PRIMARY KEY). Leaf page của clustered index chứa dữ liệu các cột của hàng.

Secondary index có cấu trúc riêng. Mỗi entry lưu các cột của secondary key và khóa chính của hàng tương ứng. Khóa chính được dùng làm phần định danh để tìm hàng trong clustered index.

Ví dụ:

```sql
CREATE TABLE users (
    id BIGINT NOT NULL,
    email VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_users_email (email),
    KEY ix_users_status (status)
) ENGINE = InnoDB;
```

Với dữ liệu:

| id | email | status | display_name |
|---:|---|---|---|
| 10 | an@example.test | ACTIVE | An |
| 20 | binh@example.test | ACTIVE | Bình |
| 30 | chi@example.test | LOCKED | Chi |

Có thể hình dung các index như sau:

```text
Clustered index PRIMARY (id)
┌──────────────────────────────────────────────┐
│ id=10 | email=an@...   | status=ACTIVE | An   │
│ id=20 | email=binh@... | status=ACTIVE | Bình │
│ id=30 | email=chi@...  | status=LOCKED | Chi  │
└──────────────────────────────────────────────┘

Secondary index uk_users_email (email, id)
┌───────────────────────────────────┐
│ an@example.test   -> id=10        │
│ binh@example.test -> id=20        │
│ chi@example.test  -> id=30        │
└───────────────────────────────────┘

Secondary index ix_users_status (status, id)
┌───────────────────────────────────┐
│ ACTIVE -> id=10                   │
│ ACTIVE -> id=20                   │
│ LOCKED -> id=30                   │
└───────────────────────────────────┘
```

Sơ đồ đã rút gọn. Với secondary index không unique, InnoDB đưa khóa chính vào entry để phân biệt các hàng có cùng giá trị secondary key. Với unique secondary index, giá trị unique vẫn được lưu cùng khóa chính trong cấu trúc index.

Nếu bảng không có khóa chính phù hợp hoặc unique index không nullable để làm clustered index, InnoDB có thể tạo clustered index nội bộ bằng row ID. Trong thiết kế ứng dụng, nên khai báo khóa chính rõ ràng để định danh hàng ổn định và dễ dự đoán.

## 2. Tra cứu qua secondary index rồi về hàng gốc

Giả sử ứng dụng chạy:

```sql
SELECT id, email, display_name
FROM users
WHERE status = 'ACTIVE';
```

Vì `status` có secondary index, optimizer có thể dùng `ix_users_status` để tìm các entry `ACTIVE`. Index entry cung cấp `id`, nhưng không chứa `email` và `display_name`. InnoDB cần dùng từng `id` để tra cứu hàng tương ứng trong clustered index.

Đường đi khái quát:

```text
SQL: WHERE status = 'ACTIVE'
             |
             v
   Secondary index ix_users_status
             |
             | tìm các entry ACTIVE
             v
       Lấy khóa chính id
             |
             v
      Clustered index PRIMARY
             |
             | tra cứu hàng theo id
             v
      Lấy email, display_name
             |
             v
       Trả kết quả cho ứng dụng
```

Đây thường được gọi là secondary-index lookup hoặc lookup về clustered index. Nếu chỉ mục phụ chứa đủ các cột cần thiết, một truy vấn đọc thường có thể được phục vụ bằng covering index mà không cần đọc toàn bộ hàng gốc.

### Covering index không đồng nghĩa bỏ qua khóa hàng

Với consistent read thông thường, covering index có thể giảm số lần truy cập clustered index. Nhưng với locking read như `SELECT ... FOR UPDATE`, InnoDB cần khóa các bản ghi được truy cập và bản ghi clustered tương ứng. Không nên kết luận rằng chỉ vì `EXPLAIN` báo `Using index`, locking read sẽ không khóa hàng gốc.

Phân biệt hai truy vấn:

```sql
-- Consistent read thông thường: không lấy row lock.
SELECT id
FROM users
WHERE email = 'an@example.test';

-- Locking read: cần khóa hàng được chọn.
SELECT id
FROM users
WHERE email = 'an@example.test'
FOR UPDATE;
```

Truy vấn thứ hai có thể tìm entry qua `uk_users_email` và vẫn cần khóa record của hàng trong clustered index. Việc cột `id` đã nằm trong secondary entry không loại bỏ yêu cầu khóa hàng cho locking read.

## 3. Vì sao một câu lệnh có thể tạo nhiều lock entry?

Khi một locking read tìm hàng bằng secondary index, InnoDB có thể cần bảo vệ cả:

1. Entry trong secondary index mà truy vấn đã dùng để tìm hàng.
2. Record tương ứng trong clustered index chứa dữ liệu hàng.
3. Gap hoặc next-key range liên quan nếu loại tìm kiếm và isolation level yêu cầu.

Do đó, quan sát `performance_schema.data_locks` có thể cho thấy nhiều dòng cho một hàng logic. Chẳng hạn, cùng một transaction có thể có lock trên `uk_users_email` và `PRIMARY`. Đây không nhất thiết là khóa trùng hoặc hai hàng khác nhau; chúng có thể là hai phần của cùng một đường truy cập.

Với truy vấn theo range trên secondary index không unique, InnoDB có thể khóa một khoảng index rộng hơn số hàng trả về. Ở `REPEATABLE READ`, next-key lock kết hợp record lock với gap lock để ngăn chèn vào khoảng được bảo vệ. Vì thế, lock footprint phụ thuộc index và phạm vi scan, không chỉ phụ thuộc số hàng cuối cùng.

Các mode có thể thấy trong `LOCK_MODE` gồm những dạng như `S`, `X`, `S,GAP`, `X,GAP`, `X,REC_NOT_GAP` hoặc dạng next-key tương ứng. Cách hiển thị và chi tiết cụ thể tùy phiên bản. Hãy đọc mode cùng `INDEX_NAME`, `LOCK_DATA` và câu SQL đang chạy.

## 4. Thứ tự lấy khóa đi theo đường truy cập thực tế

Khi transaction truy cập nhiều hàng, database cần lấy các khóa cần thiết để bảo vệ chúng. Thứ tự có thể chịu ảnh hưởng của:

- Index mà optimizer chọn để tìm hàng.
- Thứ tự các entry được quét trong index.
- Cách InnoDB tra cứu clustered index tương ứng.
- Các index cần thay đổi khi câu lệnh INSERT, UPDATE hoặc DELETE.
- Kiểm tra unique key, foreign key và các thao tác nội bộ liên quan.
- Execution plan và cách câu lệnh được thực hiện ở phiên bản database hiện tại.

Vì vậy, không nên dựa vào thứ tự cột trong câu SQL hoặc thứ tự giá trị trong `IN (...)` để khẳng định database chắc chắn lấy khóa theo thứ tự đó. Optimizer có thể chọn access path khác, và engine có thể phải khóa thêm index record hoặc khoảng liên quan.

### Ví dụ hai đường truy cập khác nhau

Giả sử bảng `users` có hai index:

- `PRIMARY(id)` — tìm hàng trực tiếp theo khóa chính.
- `uk_users_email(email)` — tìm hàng theo email rồi tra về clustered row.

Session A khóa hàng id=10 bằng email, sau đó khóa hàng id=20 bằng primary key:

```sql
-- Session A
START TRANSACTION;

SELECT id
FROM users
WHERE email = 'an@example.test'
FOR UPDATE;
-- Giả sử trả id=10; đường tìm kiếm dùng uk_users_email.

SELECT id
FROM users
WHERE id = 20
FOR UPDATE;
-- Khóa hàng id=20 qua PRIMARY.
```

Session B lấy khóa theo thứ tự ngược lại:

```sql
-- Session B
START TRANSACTION;

SELECT id
FROM users
WHERE id = 20
FOR UPDATE;

SELECT id
FROM users
WHERE email = 'an@example.test'
FOR UPDATE;
```

Nếu A đã khóa hàng 10 và B đã khóa hàng 20, câu lệnh thứ hai của A có thể chờ B; câu lệnh thứ hai của B có thể chờ A. Hai transaction tạo thành chu trình chờ và database có thể phát hiện deadlock.

```text
Session A                              Session B
---------                              ---------
Khóa users qua email: id=10
                                       Khóa users qua PRIMARY: id=20
Khóa id=20 -> chờ B
                                       Khóa email của id=10 -> chờ A

              A <------> B
                 DEADLOCK
```

Ví dụ minh họa cách hai đường truy cập và thứ tự khóa khác nhau có thể tạo deadlock. Lock cụ thể còn phụ thuộc isolation level, unique lookup, execution plan và trạng thái dữ liệu. Thực nghiệm trên đúng phiên bản MySQL để xác nhận chi tiết.

## 5. Cập nhật cột secondary index làm phát sinh thêm công việc khóa

Khi câu lệnh thay đổi một cột không được lập chỉ mục, InnoDB cần khóa hàng và cập nhật clustered record. Khi thay đổi cột nằm trong secondary index, engine còn phải cập nhật cấu trúc index phụ.

Ví dụ:

```sql
UPDATE users
SET status = 'LOCKED'
WHERE id = 10;
```

Vì `status` nằm trong `ix_users_status`, InnoDB phải thay đổi entry index tương ứng: entry cũ được loại khỏi tập giá trị `ACTIVE` và entry mới được thêm vào vùng `LOCKED`. Quá trình này cần phối hợp với clustered row và các index liên quan.

Nếu cập nhật `email`, InnoDB còn phải duy trì unique secondary index `uk_users_email` và kiểm tra không trùng giá trị. Các transaction đồng thời cập nhật email có thể cạnh tranh trên index entry hoặc gặp duplicate-key error.

Một câu INSERT cũng phải tạo clustered record và entry cho các secondary index. DELETE phải đánh dấu/xóa các entry liên quan. Những thay đổi này làm tăng số cấu trúc index mà transaction phải truy cập và có thể mở rộng cơ hội xung đột.

Đây là lý do một thao tác ghi trên cùng một hàng có thể tương tác với transaction khác đang tìm hàng qua secondary index, ngay cả khi hai câu SQL nhìn bề ngoài dùng các cột khác nhau.

## 6. Unique secondary index và non-unique secondary index

### Unique lookup trên toàn bộ khóa

Với truy vấn tìm đúng một hàng bằng toàn bộ cột của unique index:

```sql
SELECT id
FROM users
WHERE email = 'an@example.test'
FOR UPDATE;
```

Nếu `email` là unique và giá trị tồn tại, InnoDB có thể dùng unique lookup để khóa record cụ thể, thường không cần khóa gap bao quanh record đó. Sau khi tìm entry secondary, nó vẫn cần bảo vệ clustered record tương ứng.

### Range hoặc prefix không duy nhất

Với truy vấn:

```sql
SELECT id
FROM users
WHERE status = 'ACTIVE'
FOR UPDATE;
```

`status` không unique. InnoDB có thể phải quét nhiều entry liên tiếp trong `ix_users_status`. Ở `REPEATABLE READ`, range scan có thể dùng next-key lock/gap lock. Nếu chỉ có một số ít hàng trả về nhưng vùng index phải quét rộng, các thao tác khác có thể bị chặn trên những record hoặc gap liên quan.

Ở `READ COMMITTED`, InnoDB thường giảm gap locking cho các search/index scan thông thường; gap lock vẫn có thể được dùng cho kiểm tra foreign key và duplicate-key. Cùng một truy vấn có thể tạo lock footprint khác khi đổi isolation level.

## 7. Execution plan giúp hiểu index nào được dùng

Đừng suy luận đường truy cập chỉ từ câu SQL. Dùng `EXPLAIN` để xem optimizer dự kiến chọn index nào:

```sql
EXPLAIN FORMAT=JSON
SELECT id, email, display_name
FROM users
WHERE status = 'ACTIVE'
FOR UPDATE;
```

Các thông tin cần quan sát:

- `key`: index mà optimizer dự kiến sử dụng.
- `possible_keys`: những index có thể dùng theo ước lượng optimizer.
- `access_type` hoặc `type`: cách truy cập như `const`, `eq_ref`, `ref`, `range`, `index` hoặc `ALL`.
- `rows` và `rows_examined_per_scan`: số hàng ước lượng phải đọc.
- `filtered`: tỷ lệ hàng còn lại sau điều kiện lọc.
- `used_key_parts`: những phần của composite index được sử dụng.
- `attached_condition` hoặc `index_condition`: điều kiện được áp dụng trong từng giai đoạn.

Nếu `key = ix_users_status`, đường truy cập có thể bắt đầu từ secondary index. Nếu `key = PRIMARY` hoặc `access_type = ALL`, đường truy cập khác và phạm vi khóa có thể thay đổi.

`EXPLAIN` là kế hoạch/ước lượng, không phải danh sách lock thực tế. `EXPLAIN ANALYZE` thực thi truy vấn để đo số hàng thực tế và thời gian; với locking read, việc thực thi có thể lấy khóa. Chỉ dùng trong môi trường thử nghiệm hoặc transaction được kiểm soát.

### Vì sao plan có thể thay đổi?

Optimizer có thể chọn index khác khi:

- Tỷ lệ `ACTIVE` trong bảng thay đổi.
- Bảng tăng kích thước hoặc phân bố dữ liệu lệch.
- Thống kê index được cập nhật.
- Thêm hoặc xóa index.
- Điều kiện truy vấn hoặc giá trị tham số thay đổi.
- Phiên bản MySQL thay đổi thuật toán optimizer.

Khi plan thay đổi, thứ tự quét và thứ tự lấy khóa cũng có thể thay đổi. Một truy vấn chạy ổn định trong môi trường test có thể tạo lock footprint khác khi dữ liệu production lớn hơn hoặc phân bố khác.

## 8. Quan sát lock trên secondary index và clustered index

Trong MySQL 8.0, `performance_schema.data_locks` cung cấp các lock đang được giữ hoặc chờ. Có thể lọc theo bảng:

```sql
SELECT
    ENGINE_TRANSACTION_ID,
    THREAD_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_SCHEMA = DATABASE()
  AND OBJECT_NAME = 'users'
ORDER BY ENGINE_TRANSACTION_ID, INDEX_NAME, LOCK_DATA;
```

Ví dụ kết quả có thể cho thấy cùng transaction đang giữ khóa trên `uk_users_email` và `PRIMARY`. Điều này phù hợp với đường tìm qua secondary index rồi bảo vệ clustered row. Không phải mọi truy vấn đều tạo đúng hai dòng hoặc hai lock mode như nhau; số lượng phụ thuộc access path và kiểu thao tác.

Các cột quan trọng:

- `INDEX_NAME`: index đang được khóa, ví dụ `uk_users_email`, `ix_users_status` hoặc `PRIMARY`.
- `LOCK_TYPE`: thường là `RECORD` hoặc `TABLE`.
- `LOCK_MODE`: mode khóa và thông tin gap/record-only nếu có.
- `LOCK_STATUS`: `GRANTED` hoặc trạng thái chờ như `WAITING`, tùy phiên bản.
- `LOCK_DATA`: giá trị index key liên quan; có thể không hiển thị đầy đủ trong mọi trường hợp.
- `ENGINE_TRANSACTION_ID`: transaction engine sở hữu lock.

### Xem ai đang chờ ai

```sql
SELECT
    waits.REQUESTING_ENGINE_TRANSACTION_ID AS waiting_trx,
    waits.BLOCKING_ENGINE_TRANSACTION_ID AS blocking_trx,
    requested.OBJECT_SCHEMA,
    requested.OBJECT_NAME,
    requested.INDEX_NAME AS waiting_index,
    requested.LOCK_MODE AS waiting_mode,
    requested.LOCK_DATA AS waiting_key,
    blocking.INDEX_NAME AS blocking_index,
    blocking.LOCK_MODE AS blocking_mode,
    blocking.LOCK_DATA AS blocking_key
FROM performance_schema.data_lock_waits AS waits
JOIN performance_schema.data_locks AS requested
  ON requested.ENGINE_LOCK_ID = waits.REQUESTING_ENGINE_LOCK_ID
JOIN performance_schema.data_locks AS blocking
  ON blocking.ENGINE_LOCK_ID = waits.BLOCKING_ENGINE_LOCK_ID;
```

Truy vấn này giúp đối chiếu index/key của yêu cầu chờ và lock đang chặn. Quyền truy cập Performance Schema có thể bị giới hạn; tên cột và chi tiết hiển thị cần được xác nhận theo phiên bản.

### Kết hợp process list và InnoDB status

```sql
SHOW FULL PROCESSLIST;
SHOW ENGINE INNODB STATUS\G
```

Process list cho biết câu SQL và trạng thái kết nối. InnoDB status cung cấp transaction, lock wait và deadlock gần nhất. Dùng chúng cùng `data_locks` để liên kết connection với transaction và index đang bị khóa.

## 9. Thử nghiệm thứ tự khóa qua hai đường truy cập

Có thể xác nhận tác động của secondary index bằng một thử nghiệm trong database riêng. Tạo bảng:

```sql
CREATE TABLE lock_order_test (
    id BIGINT NOT NULL,
    email VARCHAR(200) NOT NULL,
    note VARCHAR(100),
    PRIMARY KEY (id),
    UNIQUE KEY uk_lock_order_email (email)
) ENGINE = InnoDB;

INSERT INTO lock_order_test (id, email, note) VALUES
(10, 'an@example.test', 'row-10'),
(20, 'binh@example.test', 'row-20');
```

Session A lấy hàng 10 qua unique secondary index, sau đó hàng 20 qua primary key:

```sql
START TRANSACTION;

SELECT id
FROM lock_order_test
WHERE email = 'an@example.test'
FOR UPDATE;

SELECT id
FROM lock_order_test
WHERE id = 20
FOR UPDATE;
```

Session B làm ngược lại:

```sql
START TRANSACTION;

SELECT id
FROM lock_order_test
WHERE id = 20
FOR UPDATE;

SELECT id
FROM lock_order_test
WHERE email = 'an@example.test'
FOR UPDATE;
```

Để tạo tình huống cạnh tranh, chạy câu lệnh đầu tiên ở cả hai session trước, rồi mới chạy câu lệnh thứ hai. Một session có thể phải chờ và InnoDB có thể phát hiện deadlock. Nếu deadlock xảy ra, đọc `SHOW ENGINE INNODB STATUS\G` và `performance_schema.data_locks` để xem chu trình thực tế.

Sau mỗi lượt, kết thúc transaction còn lại bằng `COMMIT` hoặc `ROLLBACK`, rồi xác nhận không còn lock wait. Thử lại bằng cách đổi thứ tự truy cập để xem deadlock có giảm hay không. Không chạy thí nghiệm này trên bảng production.

## 10. Giảm nguy cơ deadlock do nhiều index

### Dùng thứ tự truy cập hàng nhất quán

Nếu một transaction truy cập nhiều hàng, mọi luồng nên dùng cùng một thứ tự logic, ví dụ tăng dần theo primary key. Tránh để luồng A lấy hàng theo email rồi id, trong khi luồng B lấy id rồi email theo thứ tự ngược lại.

Nếu nghiệp vụ cần truy vấn qua secondary index, có thể tìm trước tập primary key cần xử lý, sắp xếp theo khóa chính rồi khóa từng hàng theo thứ tự đó trong transaction. Tuy nhiên, bước đọc danh sách id và bước khóa vẫn phải được thiết kế để xử lý thay đổi đồng thời; chỉ sắp xếp danh sách ở Java không tự bảo đảm mọi index/gap lock đều lấy theo thứ tự đó.

### Giảm số index phải cập nhật

Mỗi secondary index làm tăng công việc ghi. Khi thay đổi cột được lập chỉ mục, InnoDB phải duy trì entry tương ứng. Chỉ tạo index có ích cho workload; tránh các index dư thừa hoặc trùng prefix mà không có lý do rõ ràng.

### Dùng điều kiện truy vấn có tính chọn lọc

Index phù hợp giúp engine quét ít record hơn. Với locking read hoặc UPDATE/DELETE, điều này thường giảm số record có thể bị khóa và thời gian giữ khóa. Kiểm tra `EXPLAIN` sau khi thay đổi index.

### Giữ transaction ngắn

Đọc, kiểm tra, cập nhật và commit trong khoảng thời gian ngắn. Không gọi dịch vụ ngoài hoặc chờ người dùng trong khi giữ khóa trên clustered row và secondary index.

### Retry deadlock an toàn

Deadlock vẫn có thể xảy ra. Khi InnoDB trả lỗi deadlock, ứng dụng cần rollback và chạy lại toàn bộ transaction nếu thao tác an toàn. Lần retry phải đọc lại dữ liệu và tính lại quyết định, không dùng kết quả cũ. Giới hạn retry và bảo đảm tác dụng phụ ngoài database không bị lặp.

## 11. Các nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Secondary index chứa toàn bộ hàng. | Entry secondary thường chứa các cột index và khóa chính; muốn lấy cột khác cần tra clustered index. |
| Truy vấn chỉ chọn cột có trong secondary index thì locking read không khóa hàng gốc. | Locking read cần bảo vệ bản ghi dữ liệu tương ứng; covering index không loại bỏ yêu cầu khóa clustered record. |
| Một hàng logic luôn tương ứng một lock entry. | Có thể có lock trên secondary index, clustered index và gap/next-key range. |
| Thứ tự trong `WHERE id IN (...)` quyết định thứ tự lấy khóa. | Optimizer và access path quyết định đường quét thực tế; không dựa vào thứ tự văn bản của danh sách. |
| Deadlock chỉ xảy ra khi hai câu SQL khóa cùng một index. | Các transaction đi qua index khác nhau vẫn có thể khóa cùng hàng hoặc tài nguyên liên quan theo thứ tự ngược nhau. |
| Thêm index luôn giảm deadlock. | Index có thể thu hẹp scan, nhưng cũng tạo thêm cấu trúc cần duy trì và có thể làm thay đổi thứ tự lấy khóa. |
| `EXPLAIN` liệt kê chính xác tất cả lock sẽ được lấy. | `EXPLAIN` mô tả kế hoạch/ước lượng; phải quan sát `data_locks` trong transaction thật để xác nhận. |

## 12. Quy trình điều tra khi nghi ngờ secondary index gây blocking

1. Ghi lại câu SQL, connection id, transaction id và isolation level.
2. Chạy `EXPLAIN FORMAT=JSON` để xác định index và access path.
3. Kiểm tra `performance_schema.data_locks` theo bảng và transaction id.
4. Xem `INDEX_NAME`, `LOCK_MODE` và `LOCK_DATA` để nhận diện secondary index, PRIMARY và gap/record lock.
5. Dùng `data_lock_waits` để tìm phiên chờ và phiên chặn.
6. Đối chiếu process list và `information_schema.innodb_trx` để biết transaction nào đang mở lâu.
7. Kiểm tra deadlock report nếu có chu trình chờ.
8. Thử tái hiện trong môi trường test bằng cùng index, dữ liệu và isolation level.
9. Đánh giá thứ tự truy cập, index dư thừa, predicate và thời gian giữ transaction.
10. Sau khi thay đổi query/index, xác nhận lại execution plan và lock footprint.

## 13. Tự kiểm tra

**Secondary index của InnoDB thường lưu gì để tìm hàng gốc?**

Nó lưu các cột secondary key cùng khóa chính của hàng. Khóa chính giúp InnoDB tra cứu record trong clustered index.

**Vì sao `SELECT ... FOR UPDATE` qua secondary index có thể tạo lock trên cả secondary index và PRIMARY?**

InnoDB cần bảo vệ entry được dùng để tìm hàng và clustered record tương ứng. Locking read vẫn phải khóa hàng dữ liệu dù khóa chính đã nằm trong secondary entry.

**Vì sao hai transaction truy cập cùng hai hàng qua index khác nhau có thể deadlock?**

Chúng có thể lấy khóa trên các record liên quan theo thứ tự khác nhau. Khi mỗi transaction giữ một hàng và chờ hàng còn lại do transaction kia giữ, một chu trình chờ hình thành.

**`EXPLAIN` có đủ để kết luận phạm vi khóa không?**

Không. Nó cho biết kế hoạch dự kiến và ước lượng. Cần kết hợp `performance_schema.data_locks`, `data_lock_waits` và thử nghiệm cạnh tranh để xác nhận lock thực tế.

**Cách đơn giản để giảm deadlock do thứ tự truy cập là gì?**

Thống nhất thứ tự lấy khóa trên nhiều hàng và nhiều bảng trong mọi luồng, giảm thời gian transaction và dùng index phù hợp để tránh scan rộng.

Khi phân tích locking qua secondary index, hãy theo dõi trọn đường đi: **secondary entry được tìm thấy, khóa chính dẫn đến clustered row, các index cần duy trì và thứ tự transaction lấy từng khóa**. Execution plan cho biết đường truy cập dự kiến; lock instrumentation và thử nghiệm hai session mới xác nhận được hành vi đang xảy ra trong môi trường thực tế.
