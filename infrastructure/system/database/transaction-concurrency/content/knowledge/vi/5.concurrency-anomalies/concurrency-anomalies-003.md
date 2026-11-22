# Đọc không lặp lại (non-repeatable read): cùng hàng nhưng khác giá trị

Trong một transaction, ứng dụng có thể đọc cùng một bản ghi nhiều lần để kiểm tra trạng thái, tính toán hoặc hiển thị thông tin. Nếu một transaction khác cập nhật và commit bản ghi đó giữa hai lần đọc, transaction đầu tiên có thể nhận hai giá trị khác nhau dù truy vấn cùng một hàng với cùng điều kiện. Hiện tượng này gọi là **non-repeatable read (đọc không lặp lại)**.

Ví dụ, transaction T1 đọc số dư tài khoản A là 1.000.000 đồng. Trong khi T1 vẫn đang mở, T2 cộng thêm 200.000 đồng và commit. Khi T1 đọc lại tài khoản A, nó nhận 1.200.000 đồng. Cùng một transaction đọc cùng một hàng hai lần nhưng kết quả khác nhau.

Đây là một bất thường đồng thời liên quan đến **cách các transaction quan sát thay đổi đã commit**. Nó thường xuất hiện ở mức `READ COMMITTED` trong các DBMS dùng snapshot theo từng câu lệnh, chẳng hạn PostgreSQL. Mức cô lập cao hơn có thể duy trì góc nhìn ổn định hơn hoặc dùng khóa để ngăn thay đổi chen giữa hai lần đọc.

## 1. Định nghĩa non-repeatable read

Một lịch thực thi có non-repeatable read khi:

1. Transaction T1 đọc hàng X và nhận giá trị v1.
2. Transaction T2 cập nhật chính hàng X rồi commit giá trị mới v2.
3. T1 đọc lại chính hàng X bằng truy vấn tương đương.
4. T1 nhận v2, khác v1.

```text
Thời gian ---------------------------------------------------->

T1: BEGIN
    R1(X) = v1
                  |
T2:              BEGIN
                  W2(X) = v2
                  COMMIT
    R1(X) = v2
    COMMIT

                 v1 != v2
                 ^
                 |
        Non-repeatable read
```

Điểm quan trọng là T2 đã **commit** trước lần đọc thứ hai của T1. Do vậy, đây không phải dirty read. T1 nhìn thấy một giá trị đã commit, nhưng giá trị ấy khác với giá trị mà chính T1 đã đọc trước đó.

Một cách diễn đạt ngắn gọn: cùng một truy vấn đọc cùng một hàng trong cùng transaction có thể cho kết quả khác nhau do transaction khác đã commit thay đổi giữa hai lần đọc.

## 2. Ví dụ: số dư tài khoản thay đổi giữa hai lần đọc

Giả sử bảng tài khoản có dữ liệu:

| id | owner | balance |
|---|---|---:|
| A101 | An | 1.000.000 |
| B202 | Bình | 2.000.000 |

T1 đang lập báo cáo số dư tài khoản An. T2 nhận một khoản tiền và cập nhật tài khoản A101.

| Bước | Transaction T1 — báo cáo | Transaction T2 — cập nhật | Giá trị T1 quan sát |
|---:|---|---|---|
| 1 | Bắt đầu transaction | | |
| 2 | Đọc A101.balance | | 1.000.000 |
| 3 | | Bắt đầu transaction | |
| 4 | | Cộng 200.000 vào A101.balance | |
| 5 | | Commit | |
| 6 | Đọc lại A101.balance | | 1.200.000 |
| 7 | Commit | | |

Lịch thao tác:

```text
R1(A101)
    W2(A101)
    C2
R1(A101)
C1
```

T1 đọc cùng hàng A101 ở bước 2 và bước 6, cùng điều kiện lọc và cùng transaction, nhưng nhận số dư khác nhau. Đó chính là non-repeatable read.

### Minh họa bằng SQL

Giả sử DBMS hỗ trợ hai phiên/kết nối độc lập. Phiên thứ nhất:

```sql
BEGIN;

SELECT id, owner, balance
FROM accounts
WHERE id = 'A101';
-- Kết quả lần 1: balance = 1000000

-- Chưa COMMIT transaction này.
-- Trong lúc đó, phiên thứ hai cập nhật và commit.

SELECT id, owner, balance
FROM accounts
WHERE id = 'A101';
-- Ở READ COMMITTED, kết quả có thể là 1200000.

COMMIT;
```

Phiên thứ hai:

```sql
BEGIN;

UPDATE accounts
SET balance = balance + 200000
WHERE id = 'A101';

COMMIT;
```

Trình tự phải là: câu SELECT đầu tiên của phiên 1 hoàn tất, phiên 2 cập nhật và commit, sau đó phiên 1 thực hiện SELECT thứ hai. Nếu phiên 2 chưa commit, kết quả của phiên 1 không được gọi là non-repeatable read; nếu phiên 2 commit sau lần đọc thứ hai thì cũng không tạo ra hiện tượng này trong lịch trên.

Ở `READ COMMITTED` của PostgreSQL, mỗi câu lệnh bắt đầu với một snapshot mới. Vì thế, câu SELECT thứ hai có thể thấy thay đổi đã commit sau snapshot của câu đầu. Hành vi khóa và snapshot khác nhau giữa các DBMS; cần áp dụng đúng ngữ nghĩa của hệ quản trị đang sử dụng.

## 3. Vì sao hiện tượng này có thể làm sai logic ứng dụng?

Không phải mọi lần đọc ra giá trị mới đều là lỗi nghiệp vụ. Một trang hiển thị số dư cập nhật theo thời gian có thể chấp nhận dữ liệu mới ở lần tải sau. Vấn đề xuất hiện khi ứng dụng giả định rằng dữ liệu đã đọc ở đầu transaction sẽ giữ nguyên trong suốt một phép tính hoặc quyết định.

### Ví dụ: tính hóa đơn dựa trên giá sản phẩm

T1 đọc giá sản phẩm là 100.000 đồng. Một giao dịch quản trị thay đổi giá thành 120.000 đồng rồi commit. Nếu T1 đọc lại cùng hàng để ghi giá vào hóa đơn, nó có thể dùng giá mới dù các bước tính toán trước đó đã dùng giá cũ.

```text
T1 — lập hóa đơn                 T2 — quản trị giá
----------------                 ----------------
BEGIN
SELECT price = 100000
                                 BEGIN
                                 UPDATE product SET price = 120000
                                 COMMIT
SELECT price = 120000
Tính hóa đơn
COMMIT
```

Ứng dụng có thể rơi vào logic không mong muốn nếu một số trường được tính bằng giá cũ, còn bước sau lấy lại giá mới. Cách thiết kế thường phù hợp hơn là **chụp giá tại thời điểm tạo đơn** và lưu giá đó vào dòng chi tiết đơn hàng, thay vì đọc lại giá catalog hiện tại để dựng hóa đơn cũ.

### Ví dụ: kiểm tra trạng thái đơn hàng

Một tác vụ nền đọc đơn hàng ở trạng thái `PENDING`, thực hiện một số bước kiểm tra, rồi đọc lại để quyết định có tiếp tục không. Trong lúc đó, nhân viên hoặc tiến trình khác chuyển trạng thái thành `CANCELLED` và commit. Nếu lần đọc thứ hai nhận `CANCELLED`, tác vụ phải xử lý thay đổi này đúng quy tắc; tiếp tục dựa trên giả định cũ có thể tạo tác dụng phụ không hợp lệ.

Có thể dùng chuyển trạng thái có điều kiện:

```sql
UPDATE orders
SET status = 'PROCESSING'
WHERE id = 501
  AND status = 'PENDING';
```

Ứng dụng kiểm tra số dòng được cập nhật. Nếu không có dòng nào, trạng thái đã thay đổi hoặc đơn không còn tồn tại; ứng dụng cần đọc lại và quyết định. Cách ghi có điều kiện bảo vệ **chuyển trạng thái cụ thể** tại điểm ghi. Nó không tự tạo snapshot ổn định cho mọi truy vấn trong transaction.

## 4. Phân biệt với dirty read và phantom read

Non-repeatable read thường được học cùng các bất thường đọc khác:

| Hiện tượng | Điều gì thay đổi? | Transaction khác đã commit chưa? |
|---|---|---|
| **Dirty read** | Đọc thấy giá trị do transaction khác ghi nhưng chưa commit | Chưa |
| **Non-repeatable read** | Đọc lại cùng hàng, nhận giá trị khác vì hàng được cập nhật hoặc xóa | Đã commit |
| **Phantom read** | Chạy lại truy vấn theo điều kiện nhưng tập hàng thỏa điều kiện thay đổi | Thường đã commit |

### Dirty read

```text
T1: BEGIN
    W1(X) = 200
                     T2: BEGIN
                         R2(X) = 200  (T1 chưa commit)
                         COMMIT
T1: ROLLBACK
```

T2 đọc giá trị chưa commit của T1. Sau đó T1 rollback, nên T2 đã dựa vào một giá trị bị hủy. Đây là **dirty read**, khác với non-repeatable read vì giá trị mới chưa được commit.

### Non-repeatable read

```text
T1: R1(X) = 100
                 T2: W2(X) = 200
                     COMMIT
    R1(X) = 200
```

Giá trị mới của T2 đã commit trước lần đọc thứ hai. Cùng một hàng, khác giá trị.

### Phantom read

Giả sử T1 truy vấn tất cả đơn hàng đang chờ:

```sql
SELECT id, status
FROM orders
WHERE status = 'PENDING';
```

Lần đầu trả về hai hàng. Trong lúc T1 vẫn mở, T2 thêm đơn mới có trạng thái PENDING rồi commit. T1 chạy lại cùng truy vấn và nhận ba hàng.

```text
T1: SELECT ... WHERE status='PENDING' -> {101, 102}
T2: INSERT order 103, status='PENDING'; COMMIT
T1: SELECT ... WHERE status='PENDING' -> {101, 102, 103}
```

Đây là phantom read: tập kết quả thay đổi vì có hàng mới thỏa điều kiện. Non-repeatable read điển hình là đọc lại **một hàng cụ thể** nhưng các cột của nó có giá trị khác.

## 5. Non-repeatable read trong các mức Isolation

Isolation level quy định các giao dịch được phép quan sát và ảnh hưởng lẫn nhau ở mức nào. Theo phân loại chuẩn SQL, có thể khái quát:

| Isolation level | Non-repeatable read |
|---|---|
| `READ UNCOMMITTED` | Có thể xảy ra; mức yếu nhất, còn cho phép nhiều bất thường khác |
| `READ COMMITTED` | Có thể xảy ra; mỗi câu lệnh có thể quan sát snapshot mới hơn |
| `REPEATABLE READ` | Không cho phép non-repeatable read theo định nghĩa chuẩn; cách hiện thực tùy DBMS |
| `SERIALIZABLE` | Giao dịch thành công phải có hiệu ứng tương đương một lịch tuần tự |

Không nên áp dụng bảng này mà bỏ qua DBMS cụ thể:

- PostgreSQL thực thi `READ UNCOMMITTED` như `READ COMMITTED`; không cho dirty read.
- PostgreSQL `READ COMMITTED` tạo snapshot ở đầu mỗi câu lệnh, nên non-repeatable read có thể xuất hiện giữa hai câu SELECT.
- PostgreSQL `REPEATABLE READ` dựa trên snapshot ổn định trong transaction; các truy vấn đọc thông thường nhìn cùng góc nhìn dữ liệu. Một số xung đột cập nhật có thể khiến transaction bị lỗi.
- PostgreSQL `SERIALIZABLE` dùng Serializable Snapshot Isolation (SSI) để phát hiện các phụ thuộc có thể tạo lịch không serializable. Transaction có thể bị hủy với lỗi serialization; ứng dụng cần retry toàn bộ transaction.

Mỗi DBMS có cách triển khai locking, MVCC, range/predicate protection và serialization khác nhau. Cần xem tài liệu sản phẩm và kiểm chứng trên cấu hình thực tế trước khi kết luận một lịch được phép xảy ra hay không.

### READ COMMITTED: mỗi câu lệnh có thể thấy snapshot mới

```text
T1 BEGIN
  |
  +-- SELECT lần 1: snapshot S1, balance = 1000000
  |
T2 UPDATE balance = 1200000
T2 COMMIT
  |
  +-- SELECT lần 2 của T1: snapshot S2, balance = 1200000
  |
T1 COMMIT
```

Hai câu lệnh của T1 dùng snapshot khác nhau. Điều này cho phép READ COMMITTED thấy dữ liệu mới đã commit, nhưng không hứa lặp lại cùng kết quả trong suốt transaction.

### REPEATABLE READ: giữ góc nhìn ổn định hơn

```text
T1 BEGIN -> lấy snapshot S
  |
  +-- SELECT lần 1: balance = 1000000
  |
T2 UPDATE balance = 1200000 -> COMMIT
  |
  +-- SELECT lần 2 của T1 vẫn thấy phiên bản thuộc snapshot S
  |
T1 COMMIT
```

Tùy DBMS và loại thao tác, giao dịch đọc có thể tiếp tục thấy giá trị cũ trong khi giao dịch khác đã commit giá trị mới. Đây là đặc điểm của snapshot ổn định, không có nghĩa cập nhật của T2 chưa commit.

Trong PostgreSQL, REPEATABLE READ ngăn non-repeatable read thông thường nhưng vẫn có thể có **write skew**; nó không tương đương hoàn toàn với SERIALIZABLE.

### SERIALIZABLE: kết quả tương đương một thứ tự tuần tự

Ở mức serializable, DBMS phải bảo đảm các transaction đã commit thành công có hiệu ứng tương đương một lịch tuần tự hợp lệ. Tùy cách triển khai, transaction có thể chờ khóa, tiếp tục chạy rồi bị phát hiện xung đột khi commit, hoặc bị rollback với lỗi serialization và cần chạy lại toàn bộ transaction.

Với PostgreSQL, transaction SERIALIZABLE không nhất thiết phải chờ ngay ở lần SELECT thứ hai. Cơ chế SSI có thể để transaction chạy rồi phát hiện quan hệ đọc/ghi không thể sắp xếp tuần tự và hủy một transaction. Không nên mô tả serializable chỉ đơn giản là “DB khóa mọi hàng đến hết”; đó chỉ là một kiểu triển khai bảo thủ, không phải định nghĩa duy nhất.

## 6. Các cách xử lý non-repeatable read

Không phải mọi màn hình hay tác vụ đều cần isolation cao nhất. Cần xác định ứng dụng có yêu cầu một góc nhìn ổn định trong suốt transaction hay không.

### 6.1. Chọn mức isolation phù hợp

Nếu phép tính yêu cầu các lần đọc cùng một hàng phải nhất quán, có thể chọn REPEATABLE READ hoặc SERIALIZABLE tùy bất biến rộng hơn. Cần cân nhắc DBMS, việc transaction đọc một hàng hay tập hàng theo predicate, khả năng write skew và cách ứng dụng retry.

Đổi isolation level có thể làm tăng thời gian chờ, bộ nhớ giữ phiên bản MVCC, xung đột hoặc tỷ lệ abort tùy hệ thống và tải. Không nên bật mức cao nhất cho mọi transaction mà không cân nhắc yêu cầu.

### 6.2. Khóa hàng khi cần kiểm soát cập nhật

Trong DBMS hỗ trợ, transaction có thể khóa hàng cần dùng:

```sql
BEGIN;

SELECT id, balance
FROM accounts
WHERE id = 'A101'
FOR UPDATE;

-- Kiểm tra và thực hiện các thao tác nghiệp vụ.
-- Transaction khác muốn cập nhật hàng này có thể phải chờ
-- đến khi transaction hiện tại commit hoặc rollback.

COMMIT;
```

`FOR UPDATE` là khóa hàng dành cho thao tác cập nhật; thường giữ khóa tới cuối transaction. Cần phân biệt loại khóa và mức tương thích trong DBMS cụ thể: một SELECT thông thường khác có thể vẫn đọc phiên bản cũ bằng MVCC, trong khi thao tác ghi phải chờ. Vì vậy, `FOR UPDATE` bảo vệ tốt luồng cập nhật nhưng **không có nghĩa mọi giao dịch đọc khác đều bị buộc chờ**.

Chỉ khóa những hàng cần bảo vệ, giữ transaction ngắn và lấy khóa theo thứ tự nhất quán để giảm deadlock.

### 6.3. Kiểm soát cập nhật bằng version (optimistic locking)

Nếu ứng dụng cần tránh ghi đè thay đổi của người khác, có thể thêm cột phiên bản:

```sql
CREATE TABLE documents (
    id BIGINT PRIMARY KEY,
    content TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 1
);
```

Ứng dụng đọc version rồi cập nhật với điều kiện version không đổi:

```sql
UPDATE documents
SET content = 'Nội dung mới',
    version = version + 1
WHERE id = 42
  AND version = 7;
```

Nếu số dòng cập nhật bằng 0, dữ liệu đã bị thay đổi hoặc hàng không tồn tại. Ứng dụng tải lại và quyết định có thể áp dụng thay đổi hay cần báo người dùng. Optimistic locking phát hiện cập nhật cạnh tranh trên dòng/version được kiểm tra; nó không tự bảo đảm mọi câu SELECT trong transaction nhìn cùng snapshot và không thay thế isolation cho bất biến nhiều hàng.

### 6.4. Chụp dữ liệu cần thiết một lần

Với báo cáo hoặc quy trình cần dùng đúng giá trị tại thời điểm bắt đầu, có thể chụp và lưu các giá trị vào biến nghiệp vụ, snapshot ứng dụng hoặc bảng lịch sử. Tuy nhiên, lưu một giá trị vào biến không tự tạo snapshot đúng cho các dữ liệu khác. Nếu cần một tập dữ liệu thống nhất, phải dùng isolation/snapshot hoặc cơ chế versioning thích hợp.

Ví dụ giá sản phẩm: khi tạo đơn, ghi unit_price vào order_items theo chính sách tại thời điểm mua. Báo cáo đơn hàng sau này dùng giá đã chụp trong đơn, không đọc giá catalog hiện tại để tái dựng hóa đơn cũ.

```sql
INSERT INTO order_items
    (order_id, product_id, quantity, unit_price)
SELECT
    9001, id, 2, price
FROM products
WHERE id = 42;
```

Việc đảm bảo giá và hàng còn hiệu lực trong quy trình bán hàng hoàn chỉnh còn tùy yêu cầu và transaction bao quanh câu lệnh.

## 7. Non-repeatable read và read skew

Non-repeatable read tập trung vào việc **đọc lại cùng một hàng** và nhận giá trị khác. Một khái niệm liên quan là **read skew**: transaction đọc nhiều mục dữ liệu ở các thời điểm khác nhau, khiến tổ hợp giá trị quan sát không tương ứng với trạng thái nhất quán mà ứng dụng mong đợi.

Ví dụ chuyển tiền:

- Ban đầu A = 1.000, B = 500, tổng = 1.500.
- T1 đọc A = 1.000.
- T2 chuyển 100 từ A sang B rồi commit: A = 900, B = 600.
- T1 đọc B = 600.
- T1 tính tổng = 1.600.

T1 ghép số dư A trước giao dịch với số dư B sau giao dịch. Đây là read skew qua hai hàng, không phải ví dụ đơn giản về đọc lặp lại cùng một hàng. Nó cho thấy các lượt đọc không dùng một snapshot nhất quán có thể làm sai phép tính tổng hợp.

Nếu hai lượt đọc cùng hàng tạo ra hai giá trị khác nhau, đó là non-repeatable read điển hình. Nếu nhiều hàng tạo ra tổ hợp không nhất quán, cần xem xét read skew và các bất thường snapshot liên quan.

## 8. Kiểm thử hiện tượng bằng hai phiên giao dịch

Có thể tái hiện trên DB thử nghiệm với hai kết nối SQL client. Giả sử dữ liệu ban đầu:

```sql
CREATE TABLE accounts (
    id TEXT PRIMARY KEY,
    balance NUMERIC NOT NULL
);

INSERT INTO accounts (id, balance)
VALUES ('A101', 1000000);
```

**Phiên A** — mở transaction ở READ COMMITTED:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM accounts
WHERE id = 'A101';
-- Ghi nhận giá trị 1000000.
```

Giữ transaction này mở.

**Phiên B** — cập nhật và commit:

```sql
BEGIN;

UPDATE accounts
SET balance = balance + 200000
WHERE id = 'A101';

COMMIT;
```

**Quay lại phiên A**:

```sql
SELECT balance
FROM accounts
WHERE id = 'A101';
-- Trong PostgreSQL READ COMMITTED: 1200000.

COMMIT;
```

Kết quả chứng minh transaction A đã đọc cùng hàng hai lần với hai giá trị khác nhau. Có thể đổi isolation của phiên A thành REPEATABLE READ rồi chạy lại để quan sát snapshot ổn định của PostgreSQL. Mỗi lượt thử cần khởi tạo lại hoặc điều chỉnh số dư để đầu vào rõ ràng.

## 9. Khi nào nên chấp nhận và khi nào nên ngăn hiện tượng?

| Nghiệp vụ | Có thể chấp nhận dữ liệu thay đổi giữa transaction? | Lý do |
|---|---|---|
| Bảng điều khiển hiển thị thông tin cập nhật liên tục | Có thể | Mỗi lần tải là một thời điểm quan sát riêng |
| Lập hóa đơn cần cố định giá tại thời điểm mua | Thường không nên đọc lại giá hiện tại | Cần chụp giá và lưu vào hóa đơn |
| Báo cáo tổng số dư nhiều tài khoản | Tùy yêu cầu; thường cần snapshot nhất quán | Ghép giá trị ở nhiều thời điểm có thể làm sai tổng |
| Chuyển trạng thái đơn hàng | Cần kiểm soát điều kiện cập nhật | Trạng thái có thể đã đổi; cần kiểm tra tại điểm ghi |
| Xử lý hạn mức hoặc số lượng cuối cùng | Cần bảo vệ chặt | Quyết định dựa trên dữ liệu thay đổi có thể cấp vượt hạn mức |
| Trang hồ sơ cá nhân đang chỉnh sửa | Thường dùng version/conflict detection | Tránh ghi đè chỉnh sửa của người khác |

Khi chấp nhận dữ liệu thay đổi, hãy làm rõ rằng mỗi lần đọc có thể phản ánh một thời điểm khác nhau. Khi cần trạng thái ổn định, chọn isolation, snapshot hoặc chiến lược dữ liệu phù hợp.

## 10. Những nhầm lẫn thường gặp

**“Đọc hai lần khác nhau luôn là non-repeatable read.”** Chưa đủ. Phải là cùng một hàng trong cùng transaction, và thay đổi chen giữa đến từ transaction khác đã commit.

**“Non-repeatable read là đọc dữ liệu chưa commit.”** Đó là dirty read. Với non-repeatable read, giá trị mới đã commit.

**“Phantom read cũng là một hàng cũ thay giá trị.”** Phantom read điển hình là tập hàng phù hợp với điều kiện truy vấn thay đổi; non-repeatable read là cùng hàng nhưng giá trị thay đổi.

**“READ COMMITTED giữ nguyên snapshot suốt transaction.”** Không đúng với PostgreSQL: mỗi câu lệnh có snapshot tại thời điểm bắt đầu câu lệnh.

**“REPEATABLE READ và SERIALIZABLE giống nhau.”** Không. PostgreSQL REPEATABLE READ cung cấp snapshot ổn định nhưng vẫn có thể có write skew; SERIALIZABLE bổ sung phát hiện các phụ thuộc nguy hiểm để bảo đảm kết quả tương đương tuần tự.

**“Khóa hàng nghĩa là mọi lần đọc khác đều bị chặn.”** Không nhất thiết. MVCC cho phép truy vấn đọc thường thấy phiên bản trước trong khi thao tác ghi phải chờ khóa.

**“Thêm version column là đã giải quyết mọi bất thường đọc.”** Không. Version check chủ yếu phát hiện cập nhật cạnh tranh theo dòng được kiểm tra; nó không thay thế isolation khi phép tính phụ thuộc nhiều hàng.

## 11. Cách phân tích một lịch có non-repeatable read

Khi nhìn vào một lịch giao dịch, hãy lần lượt:

1. Xác định transaction nào đọc hàng X lần thứ nhất và giá trị nhận được.
2. Xác định transaction nào ghi hoặc xóa X, đồng thời kiểm tra nó đã commit chưa.
3. Tìm lần đọc thứ hai của transaction ban đầu: có phải cùng hàng và truy vấn tương đương không?
4. So sánh hai giá trị, dựng thứ tự thao tác đọc, ghi và commit.
5. Xác định isolation level và cách DBMS cấp snapshot/khóa để biết lịch đó có được phép xảy ra không.
6. Xác định nghiệp vụ có cần snapshot ổn định không; chọn mức isolation, khóa, version check hoặc chụp dữ liệu phù hợp.

Điều cần ghi nhớ là non-repeatable read mô tả **một lần quan sát thay đổi trong transaction**: cùng một hàng được đọc hai lần nhưng nhận hai giá trị, vì transaction khác đã commit cập nhật giữa hai lần đọc. Phân biệt chính xác hiện tượng này với dirty read, phantom read và read skew giúp thiết kế transaction đáp ứng đúng yêu cầu nhất quán của nghiệp vụ.
