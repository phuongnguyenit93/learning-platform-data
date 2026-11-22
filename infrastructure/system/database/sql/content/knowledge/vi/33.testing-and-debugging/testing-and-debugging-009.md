# Kiểm tra bất biến trước và sau INSERT, UPDATE, DELETE

Một câu lệnh DML có thể chạy thành công nhưng vẫn làm dữ liệu sai. Ví dụ, INSERT một đơn hàng nhưng không tạo dòng chi tiết; UPDATE tồn kho khiến số lượng âm; DELETE khách hàng nhưng để lại hóa đơn mồ côi; hoặc trigger ghi audit hai lần.

Để phát hiện các lỗi đó, cần kiểm tra **bất biến dữ liệu** (*data invariants*) và trạng thái trước/sau thao tác:

- Trước DML: dữ liệu có thỏa điều kiện đầu vào và các bất biến hiện tại không?
- Trong DML: câu lệnh có tác động đúng bản ghi, đúng số dòng và đúng phạm vi không?
- Sau DML: bất biến có còn đúng, và thay đổi có đúng như yêu cầu không?
- Khi thất bại: transaction có được rollback để không để lại trạng thái dở dang không?

Bài thuộc module **Database SQL**, chương **Kiểm thử và gỡ lỗi**, chủ đề **“Kiểm tra bất biến trước và sau INSERT, UPDATE, DELETE”**. PostgreSQL được dùng làm ví dụ chính; phần sau đối chiếu MySQL, SQL Server, Oracle và SQLite.

> **Thành công của DML không chỉ là không có exception. Cần xác nhận trạng thái dữ liệu sau thao tác đúng với hợp đồng nghiệp vụ và vẫn thỏa các bất biến.**

## 1. Bất biến dữ liệu là gì?

**Bất biến** là một điều kiện phải luôn đúng trong phạm vi đã xác định. Nó mô tả trạng thái hợp lệ của dữ liệu, độc lập với việc trạng thái đó được tạo bởi INSERT, UPDATE hay DELETE.

Ví dụ trong hệ thống bán hàng:

- Giá sản phẩm không âm.
- Số lượng tồn kho không âm.
- Mã SKU không trùng.
- Mỗi dòng đơn hàng tham chiếu đến một đơn hàng tồn tại.
- Tổng tiền đơn hàng bằng tổng các dòng chi tiết theo quy tắc làm tròn.
- Đơn hàng đã thanh toán không được xóa tùy tiện.
- Một thao tác chuyển tiền phải trừ ở tài khoản nguồn và cộng đúng số tiền ở tài khoản đích.

Một bất biến có thể thuộc nhiều phạm vi:

| Phạm vi | Ví dụ | Cơ chế thường dùng |
|---|---|---|
| Một cột | quantity không âm | NOT NULL, CHECK |
| Một dòng | start_date không sau end_date | CHECK |
| Nhiều dòng trong bảng | email không trùng | UNIQUE |
| Giữa các bảng | order_item phải có order | FOREIGN KEY |
| Toàn bảng/nhóm | tổng số lượng không vượt hạn mức | Transaction, constraint phù hợp, trigger hoặc logic ứng dụng |
| Toàn giao dịch | tổng tiền ghi Nợ bằng tổng tiền ghi Có | Transaction và kiểm tra tổng thể |
| Theo thời gian | trạng thái đơn hàng chỉ đi theo luồng cho phép | State transition rule, trigger/service, audit |

**Không phải mọi bất biến đều có thể viết bằng một CHECK constraint.** CHECK thường kiểm tra biểu thức trên dòng hiện tại; nó không phải công cụ tổng quát để truy vấn các dòng khác hoặc tính tổng toàn bảng.

## 2. Mô hình trước/sau DML

Có thể mô tả một thao tác bằng ba thành phần:

- `S`: trạng thái dữ liệu trước thao tác.
- `C`: câu lệnh DML.
- `S'`: trạng thái sau thao tác.

Một kiểm thử tốt cần chứng minh:

1. Trạng thái ban đầu `S` hợp lệ.
2. Điều kiện đầu vào của `C` được thỏa.
3. `C` chỉ thay đổi dữ liệu dự kiến.
4. Trạng thái mới `S'` thỏa tất cả bất biến liên quan.
5. Kết quả quan sát được (số dòng, ID, giá trị trả về, audit event) đúng hợp đồng.
6. Nếu một điều kiện thất bại, transaction không để lại thay đổi một phần.

Ta có thể viết thành công thức:

\[
I(S) \land Pre(C,S)
\Rightarrow
Post(C,S,S') \land I(S')
\]

Trong đó:

- `I` là tập bất biến.
- `Pre` là tiền điều kiện.
- `Post` là hậu điều kiện.

Ví dụ UPDATE tồn kho:

- Tiền điều kiện: sản phẩm tồn tại, lượng xuất dương, đủ tồn.
- Hậu điều kiện: tồn mới bằng tồn cũ trừ lượng xuất.
- Bất biến: tồn kho không âm.

### 2.1. Kiểm tra trước và sau không có nghĩa luôn SELECT hai lần

Một mẫu dễ mắc lỗi là:

```sql
SELECT quantity
FROM inventory
WHERE product_id = 10;

-- Ứng dụng kiểm tra quantity >= 5

UPDATE inventory
SET quantity = quantity - 5
WHERE product_id = 10;
```

Nếu một transaction khác cập nhật tồn kho sau SELECT nhưng trước UPDATE, phép kiểm tra đã lỗi thời. Đây là **race condition**.

Với điều kiện cần được bảo vệ nguyên tử, đưa tiền điều kiện vào chính câu UPDATE:

```sql
UPDATE inventory
SET quantity = quantity - :amount
WHERE product_id = :product_id
  AND :amount > 0
  AND quantity >= :amount;
```

Sau đó kiểm tra số dòng bị tác động theo semantics của driver/DBMS và xác nhận trạng thái cuối. CHECK constraint `quantity >= 0` vẫn là lớp bảo vệ quan trọng.

## 3. Phân biệt invariant, precondition và postcondition

Ba khái niệm liên quan nhưng không giống nhau.

| Khái niệm | Câu hỏi | Ví dụ |
|---|---|---|
| Invariant | Điều gì luôn phải đúng? | Số dư không âm |
| Precondition | Điều gì phải đúng trước thao tác này? | Tài khoản nguồn tồn tại và đủ số dư |
| Postcondition | Điều gì phải đúng sau thao tác? | Số dư nguồn giảm 100, đích tăng 100 |
| Side effect contract | Tác động phụ nào phải xuất hiện? | Có đúng một audit record |
| Failure contract | Khi thao tác thất bại, điều gì được giữ? | Không tài khoản nào đổi số dư |

Một giao dịch có thể bắt đầu từ trạng thái hợp lệ, nhưng precondition của thao tác cụ thể không đúng. Ví dụ tài khoản có số dư 50 vẫn là trạng thái hợp lệ, nhưng không thỏa precondition chuyển 100.

Ngược lại, câu lệnh có thể thỏa precondition nhưng tạo trạng thái sai nếu thiếu postcondition hoặc invariant thích hợp.

## 4. Chọn đúng nơi đặt bất biến

Nên đặt quy tắc càng gần dữ liệu càng tốt khi DBMS có thể bảo đảm nó một cách chính xác.

| Loại quy tắc | Nơi ưu tiên |
|---|---|
| Cột bắt buộc | NOT NULL |
| Giá trị trong miền | CHECK |
| Không trùng | UNIQUE hoặc PRIMARY KEY |
| Tham chiếu hợp lệ | FOREIGN KEY |
| Điều kiện đồng thời cần nguyên tử | DML có predicate + constraint + transaction |
| Quy tắc nhiều bảng | Transaction, trigger hoặc service theo thiết kế |
| Luồng trạng thái | Service/domain logic, có thể bổ sung trigger/constraint |
| Lịch sử/audit | Audit table, trigger hoặc event/outbox |
| Quy tắc báo cáo/đối soát | Query kiểm tra và reconciliation job |

### 4.1. Constraint và test có vai trò khác nhau

Constraint là **hàng rào thực thi**: dữ liệu không hợp lệ bị từ chối ngay khi ghi.

Test là **bằng chứng hành vi**: kiểm tra câu lệnh, trigger, transaction và quy tắc nghiệp vụ thực hiện đúng.

Ví dụ CHECK:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

Kiểm thử cần chứng minh cả hai tình huống:

- UPDATE từ 10 xuống 7 thành công.
- UPDATE từ 7 xuống -1 bị từ chối và giá trị vẫn là 7 sau rollback/statement failure theo transaction semantics.

Không chỉ test rằng constraint tồn tại trong schema.

### 4.2. CHECK không thay thế UNIQUE hay FOREIGN KEY

Không nên viết CHECK để tự kiểm tra trùng giữa các dòng. Dùng UNIQUE constraint/index.

Không nên viết CHECK chứa subquery sang bảng khác để xác thực foreign key. Dùng FOREIGN KEY hoặc cơ chế transaction phù hợp.

### 4.3. Invariant tổng hợp cần cẩn trọng

Ví dụ:

```text
Tổng số lượng đã phân bổ cho mọi đơn hàng
không được vượt số lượng kho.
```

Đây là điều kiện liên dòng/liên bảng. Một CHECK trên từng dòng không đủ. Có thể cần:

- Mô hình dữ liệu giữ một counter được cập nhật nguyên tử.
- Khóa dòng kho khi phân bổ.
- Transaction có isolation/locking phù hợp.
- Trigger được thiết kế cho nhiều dòng và concurrency.
- Một quy trình đối soát định kỳ để phát hiện sai lệch.

Không dùng một SELECT tổng đơn giản rồi UPDATE riêng nếu nhiều transaction có thể cùng tiêu thụ phần còn lại.

## 5. Bộ dữ liệu thực hành

Ta dùng ví dụ kho hàng để minh họa INSERT, UPDATE, DELETE và kiểm tra trạng thái trước/sau.

### 5.1. Tạo bảng

Cú pháp chính dưới đây theo PostgreSQL:

```sql
CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL
        CHECK (unit_price >= 0),
    active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL
        CHECK (quantity >= 0),
    version INTEGER NOT NULL DEFAULT 0
        CHECK (version >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE inventory_audit (
    audit_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL,
    old_quantity INTEGER,
    new_quantity INTEGER,
    action_name TEXT NOT NULL,
    changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Giải thích:

- SKU duy nhất và bắt buộc.
- Giá không âm.
- Số lượng tồn kho không âm.
- Mỗi inventory row tham chiếu đến sản phẩm có thật.
- version tăng khi có cập nhật để hỗ trợ optimistic concurrency.
- Audit ghi lại số lượng cũ/mới và hành động.

Bảng audit trong ví dụ không có foreign key tới products để có thể giữ lịch sử sau khi sản phẩm được xóa theo chính sách phù hợp. Trong hệ thống thực tế, có thể dùng khóa nghiệp vụ, soft delete hoặc bảng lịch sử riêng.

### 5.2. Dữ liệu ban đầu

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES
    ('SKU-100', 'Keyboard', 50.00),
    ('SKU-200', 'Mouse', 25.00);

INSERT INTO inventory (product_id, quantity)
SELECT product_id, 10
FROM products
WHERE sku = 'SKU-100';

INSERT INTO inventory (product_id, quantity)
SELECT product_id, 20
FROM products
WHERE sku = 'SKU-200';
```

Kiểm tra trạng thái:

```sql
SELECT
    p.product_id,
    p.sku,
    p.product_name,
    p.unit_price,
    i.quantity,
    i.version
FROM products AS p
JOIN inventory AS i
    ON i.product_id = p.product_id
ORDER BY p.product_id;
```

Kết quả logic ban đầu:

| SKU | Giá | Tồn kho | Version |
|---|---:|---:|---:|
| SKU-100 | 50.00 | 10 | 0 |
| SKU-200 | 25.00 | 20 | 0 |

## 6. Cách viết assertion cho kiểm thử SQL

SQL không có một câu lệnh ASSERT chuẩn được hỗ trợ giống nhau trên cả năm DBMS. Cách kiểm thử phụ thuộc vào môi trường.

Một test harness có thể:

1. Chạy DML trong transaction.
2. Chạy truy vấn assertion.
3. Đọc kết quả và so sánh expected/actual.
4. Nếu khác, ném lỗi và rollback.
5. Nếu đúng, rollback fixture hoặc commit theo mục tiêu test.

Ví dụ pseudo-code:

```text
BEGIN TRANSACTION

    tạo dữ liệu fixture
    kiểm tra invariant trước

    thực hiện DML

    đọc trạng thái sau
    assert trạng thái mong đợi
    assert mọi invariant liên quan

ROLLBACK
```

Với integration test, mỗi test nên có dữ liệu riêng và không phụ thuộc thứ tự chạy.

### 6.1. Assertion phải kiểm tra trạng thái, không chỉ số dòng

Ví dụ UPDATE trả về rowcount = 1 chưa chứng minh giá trị mới đúng. Cần đọc lại hoặc dùng RETURNING/OUTPUT để kiểm tra.

Ngược lại, rowcount = 0 có thể có nhiều nguyên nhân:

- Không tìm thấy khóa.
- Không thỏa precondition.
- Optimistic version đã cũ.
- Driver/DBMS báo số dòng thay đổi thay vì số dòng khớp.
- Một số semantics của UPDATE không giống nhau giữa hệ quản trị.

Định nghĩa hợp đồng rowcount theo DBMS/driver và luôn xác nhận trạng thái khi cần.

## 7. Kiểm tra trước và sau INSERT

INSERT thêm một thực thể mới. Các kiểm tra nên bao gồm:

### Trước INSERT

- Dữ liệu bắt buộc đã có.
- Kiểu/độ dài/định dạng phù hợp.
- Khóa nghiệp vụ chưa tồn tại, hoặc thao tác có chính sách conflict rõ.
- Các bản ghi cha cần tham chiếu tồn tại.
- Người gọi có quyền tạo dữ liệu.
- Dữ liệu liên quan đã ở trạng thái hợp lệ.

Kiểm tra trước ở ứng dụng giúp trả thông báo thân thiện, nhưng **không thay constraint** vì một transaction khác có thể chèn cùng khóa ngay sau lần kiểm tra.

### Sau INSERT

- Đúng một thực thể mới được tạo.
- Khóa chính được sinh hợp lệ.
- Giá trị mặc định đúng.
- Foreign key đúng.
- Các dòng phụ/audit/outbox được tạo đúng theo hợp đồng.
- Bất biến liên quan vẫn đúng.
- Không tạo dòng ngoài dự kiến.

### 7.1. INSERT hợp lệ và kiểm tra hậu điều kiện

PostgreSQL:

```sql
BEGIN;

INSERT INTO products (sku, product_name, unit_price)
VALUES ('SKU-300', 'Monitor', 180.00)
RETURNING product_id, sku, unit_price;

SELECT COUNT(*) AS matching_rows
FROM products
WHERE sku = 'SKU-300';

SELECT unit_price >= 0 AS price_is_valid
FROM products
WHERE sku = 'SKU-300';

ROLLBACK;
```

Trong test harness, xác nhận:

- RETURNING trả một dòng.
- matching_rows = 1.
- price_is_valid = TRUE.
- Sau ROLLBACK, SKU-300 không còn trong bảng.

ROLLBACK ở cuối giúp fixture không tồn tại sau test. Trong test production-like, có thể commit nếu đang kiểm thử hành vi commit; cần dọn dữ liệu riêng theo chiến lược test.

### 7.2. INSERT vi phạm UNIQUE

```sql
BEGIN;

INSERT INTO products (sku, product_name, unit_price)
VALUES ('SKU-100', 'Duplicate Keyboard', 55.00);

ROLLBACK;
```

Lệnh INSERT phải bị từ chối do SKU-100 đã tồn tại. Test nên xác nhận:

- Có lỗi unique violation tương ứng.
- Dòng SKU-100 ban đầu không đổi.
- Không có inventory row/audit row phụ được tạo một phần.
- Transaction được rollback hoặc xử lý đúng trạng thái lỗi của DBMS.

Không bắt lỗi rồi bỏ qua trong khi transaction còn ở trạng thái aborted; PostgreSQL yêu cầu rollback transaction hoặc rollback về savepoint trước khi tiếp tục câu lệnh khác.

### 7.3. INSERT vi phạm CHECK

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('SKU-BAD', 'Invalid', -1.00);
```

Kết quả phải bị từ chối vì unit_price âm. Sau lỗi, truy vấn theo SKU-BAD không được thấy dòng được chèn.

### 7.4. INSERT tham chiếu khóa ngoại không tồn tại

```sql
INSERT INTO inventory (product_id, quantity)
VALUES (999999, 5);
```

Nếu không có sản phẩm 999999, FOREIGN KEY từ chối thao tác. Hậu điều kiện là không có inventory row mồ côi.

### 7.5. Kiểm tra default

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES ('SKU-400', 'Webcam', 70.00)
RETURNING active;
```

Giá trị active dự kiến là TRUE do DEFAULT. Kiểm tra default thực tế thay vì chỉ xác nhận DDL có câu DEFAULT.

### 7.6. INSERT nhiều dòng

```sql
INSERT INTO products (sku, product_name, unit_price)
VALUES
    ('SKU-501', 'Cable A', 5.00),
    ('SKU-502', 'Cable B', 6.00),
    ('SKU-503', 'Cable C', 7.00)
RETURNING product_id, sku;
```

Kiểm tra số dòng được tạo là ba và tập SKU trả về đúng bằng tập đầu vào. Không phụ thuộc thứ tự sinh ID nếu không có ORDER BY ở bước đọc lại.

Một lỗi trên một dòng có thể khiến cả statement thất bại hoặc hành vi phụ thuộc conflict clause. Kiểm tra rõ atomicity của batch INSERT theo DBMS và driver.

## 8. Kiểm tra trước và sau UPDATE

UPDATE thay đổi trạng thái hiện có. Kiểm tra phải bao gồm cả giá trị cũ và giá trị mới.

### Trước UPDATE

- Bản ghi mục tiêu tồn tại.
- Người gọi được phép sửa bản ghi.
- Trạng thái hiện tại cho phép chuyển đổi.
- Giá trị mới hợp lệ.
- Version hoặc khóa concurrency đúng nếu có.
- Những quan hệ phụ thuộc không bị phá vỡ.

### Sau UPDATE

- Đúng dòng được cập nhật.
- Cột dự kiến thay đổi chính xác.
- Cột không liên quan không bị thay đổi.
- Invariant vẫn đúng.
- Version/timestamp/audit được cập nhật đúng.
- Các dòng liên quan vẫn nhất quán.

### 8.1. UPDATE tồn kho có precondition nguyên tử

Giả sử xuất 3 sản phẩm SKU-100:

```sql
BEGIN;

UPDATE inventory AS i
SET
    quantity = i.quantity - 3,
    version = i.version + 1,
    updated_at = CURRENT_TIMESTAMP
FROM products AS p
WHERE p.product_id = i.product_id
  AND p.sku = 'SKU-100'
  AND i.quantity >= 3
RETURNING
    p.sku,
    i.quantity AS new_quantity,
    i.version;

SELECT quantity >= 0 AS invariant_holds
FROM inventory AS i
JOIN products AS p USING (product_id)
WHERE p.sku = 'SKU-100';

ROLLBACK;
```

Kết quả dự kiến: tồn kho từ 10 xuống 7, version từ 0 lên 1. Sau đó xác nhận quantity không âm.

Trong ứng dụng, nếu UPDATE trả không dòng, không nên tự động kết luận chỉ có một nguyên nhân. Có thể không tìm thấy SKU hoặc tồn kho không đủ. Trả lỗi nghiệp vụ phù hợp sau khi xác định nguyên nhân theo chính sách.

### 8.2. UPDATE không được tác động nhầm dòng

Một test nên kiểm tra cả dòng mục tiêu và các dòng ngoài phạm vi:

```sql
SELECT sku, quantity
FROM inventory AS i
JOIN products AS p USING (product_id)
WHERE sku IN ('SKU-100', 'SKU-200')
ORDER BY sku;
```

Sau khi xuất 3 SKU-100, kết quả mong đợi:

- SKU-100: 7.
- SKU-200: vẫn 20.

Chỉ kiểm tra SKU-100 không phát hiện được câu UPDATE thiếu điều kiện khiến nhiều dòng bị giảm tồn.

### 8.3. UPDATE giá và kiểm tra giá trị cũ/mới

```sql
UPDATE products
SET unit_price = 55.00
WHERE sku = 'SKU-100'
RETURNING sku, unit_price;
```

Hậu điều kiện:

- SKU-100 tồn tại đúng một dòng.
- Giá mới bằng 55.00.
- SKU-200 vẫn 25.00.
- Không có giá âm.
- Nếu nghiệp vụ yêu cầu audit, có đúng event thay đổi giá theo thiết kế.

### 8.4. Optimistic concurrency bằng version

Một ứng dụng có thể đọc bản ghi với version 4, sau đó gửi UPDATE:

```sql
UPDATE inventory
SET
    quantity = 8,
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE product_id = :product_id
  AND version = :expected_version;
```

Nếu rowcount là 0, bản ghi đã thay đổi hoặc không còn tồn tại. Không ghi đè thay đổi mới hơn một cách âm thầm.

Hậu điều kiện khi thành công:

- quantity = 8.
- version = expected_version + 1.
- Chỉ một phiên bản được cập nhật.
- Invariant quantity >= 0 vẫn đúng.

Để bảo đảm số lượng không âm, vẫn nên có CHECK constraint và predicate kiểm tra lượng phù hợp; version không thay thế invariant nghiệp vụ.

### 8.5. UPDATE không làm thay đổi giá trị

Một số DBMS/driver báo affected rows theo số dòng matched; một số cấu hình có thể báo số dòng thực sự thay đổi. Do đó không nên dùng rowcount duy nhất để kết luận “giá trị có thay đổi hay không”.

Nếu nghiệp vụ yêu cầu chỉ audit khi giá trị khác, hãy diễn đạt điều kiện rõ:

```sql
UPDATE products
SET unit_price = :new_price
WHERE sku = :sku
  AND unit_price IS DISTINCT FROM :new_price;
```

`IS DISTINCT FROM` là cú pháp PostgreSQL và một số DBMS hỗ trợ tương đương; không portable nguyên văn. Có thể dùng biểu thức NULL-safe riêng theo dialect hoặc đọc giá trị cũ rồi so sánh trong transaction/lock phù hợp.

## 9. Kiểm tra trước và sau DELETE

DELETE loại bỏ dữ liệu, nên hậu điều kiện không chỉ là “không còn dòng”.

### Trước DELETE

- Bản ghi tồn tại.
- Người gọi có quyền xóa.
- Trạng thái cho phép xóa.
- Không có bản ghi phụ bị cấm xóa theo quy tắc nghiệp vụ.
- Chính sách FK đã được xác định: RESTRICT, CASCADE hay SET NULL.
- Audit/retention yêu cầu đã rõ.

### Sau DELETE

- Dòng mục tiêu không còn.
- Dòng liên quan có kết quả đúng theo FK policy.
- Không để lại orphan.
- Audit hoặc tombstone được ghi đúng nếu cần.
- Những dòng không liên quan vẫn còn nguyên.
- Không xóa nhầm nhiều dòng.

### 9.1. DELETE có kiểm tra trạng thái

```sql
DELETE FROM products
WHERE sku = 'SKU-400'
  AND active = FALSE
RETURNING product_id, sku;
```

Câu lệnh chỉ xóa sản phẩm inactive. Nếu SKU-400 active, không dòng nào bị xóa.

### 9.2. DELETE và ON DELETE RESTRICT

Trong schema mẫu, inventory tham chiếu products với ON DELETE RESTRICT. Vì SKU-100 còn inventory row, câu lệnh:

```sql
DELETE FROM products
WHERE sku = 'SKU-100';
```

phải bị từ chối. Test xác nhận:

- Product vẫn còn.
- Inventory vẫn còn.
- Quantity không đổi.
- Không có audit/event xóa một phần.

### 9.3. DELETE và ON DELETE CASCADE

Nếu quan hệ được khai báo ON DELETE CASCADE, xóa dòng cha có thể xóa dòng con tự động. Test phải xác nhận chính sách đó, ví dụ:

```sql
SELECT COUNT(*)
FROM order_items
WHERE order_id = :order_id;
```

Sau DELETE order, số dòng item liên quan phải bằng 0 nếu cascade là chủ đích.

Không kiểm tra riêng bảng cha rồi kết luận thao tác đúng; side effect ở bảng con cũng thuộc postcondition.

### 9.4. DELETE và ON DELETE SET NULL

Nếu FK khai báo SET NULL, sau khi xóa cha:

- Dòng con vẫn tồn tại.
- Cột FK trở thành NULL.
- Các bất biến khác của dòng con vẫn đúng.

Nếu cột FK cũng NOT NULL, SET NULL không thể thỏa schema; phải thiết kế lại.

### 9.5. Hard delete và soft delete

Soft delete thường dùng:

```sql
UPDATE products
SET
    active = FALSE,
    deleted_at = CURRENT_TIMESTAMP
WHERE product_id = :product_id
  AND deleted_at IS NULL;
```

Đây là UPDATE, không phải DELETE vật lý. Hậu điều kiện phải kiểm tra:

- Dòng vẫn tồn tại.
- deleted_at được đặt.
- Dòng không xuất hiện trong truy vấn mặc định chỉ lấy bản ghi active.
- FK và audit vẫn giữ nguyên.
- Quy tắc khôi phục (restore) được định nghĩa.

Không gọi soft delete là “đã xóa khỏi database” nếu dòng vẫn được lưu.

## 10. Bất biến liên bảng: ví dụ chuyển tiền

Bài toán chuyển tiền minh họa rõ việc kiểm tra cả trạng thái trước và sau của nhiều dòng.

### 10.1. Schema

```sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL
        CHECK (balance >= 0)
);

INSERT INTO accounts(account_id, balance)
VALUES (1, 1000.00), (2, 300.00);
```

### 10.2. Hợp đồng giao dịch chuyển 100

Trước:

- Tài khoản 1 có 1000.
- Tài khoản 2 có 300.
- Tổng hai tài khoản là 1300.
- Số tiền chuyển lớn hơn 0.
- Tài khoản nguồn và đích khác nhau.

Sau khi commit:

- Tài khoản 1 có 900.
- Tài khoản 2 có 400.
- Tổng vẫn là 1300.
- Không tài khoản nào âm.
- Có đúng một giao dịch chuyển tiền/audit event theo thiết kế.

### 10.3. Thực hiện trong một transaction

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100.00
WHERE account_id = 1
  AND balance >= 100.00;

UPDATE accounts
SET balance = balance + 100.00
WHERE account_id = 2;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (1, 2)
ORDER BY account_id;

ROLLBACK;
```

Đây là minh họa thao tác; trong test harness cần kiểm tra cả hai UPDATE tác động đúng một dòng. Nếu một UPDATE không tác động dòng nào, phải rollback thay vì commit một nửa giao dịch.

### 10.4. Vì sao chỉ kiểm tra tổng trước/sau chưa đủ?

Một lỗi có thể chuyển tiền giữa hai tài khoản sai nhưng vẫn giữ tổng bằng 1300. Vì vậy cần kiểm tra:

- Số dư từng tài khoản.
- Tổng tiền.
- Số lượng dòng bị cập nhật.
- Đúng nguồn và đúng đích.
- Giao dịch/audit record.
- Không có tác động ngoài phạm vi.

Invariant tổng là cần nhưng không đủ để chứng minh postcondition nghiệp vụ.

## 11. Assertion cụ thể trong PostgreSQL

PostgreSQL không có câu ASSERT tổng quát trong SQL query, nhưng PL/pgSQL có thể dùng DO block và RAISE EXCEPTION để biến điều kiện sai thành lỗi test.

Ví dụ:

```sql
BEGIN;

INSERT INTO products (sku, product_name, unit_price)
VALUES ('TEST-ASSERT-1', 'Test Item', 12.50);

DO $$
DECLARE
    v_count INTEGER;
    v_price NUMERIC(12, 2);
BEGIN
    SELECT COUNT(*), MAX(unit_price)
    INTO v_count, v_price
    FROM products
    WHERE sku = 'TEST-ASSERT-1';

    IF v_count <> 1 THEN
        RAISE EXCEPTION
            'Expected exactly one product, got %', v_count;
    END IF;

    IF v_price IS DISTINCT FROM 12.50 THEN
        RAISE EXCEPTION
            'Unexpected price: %', v_price;
    END IF;
END;
$$;

ROLLBACK;
```

Nếu assertion thất bại, test phải báo lỗi. Transaction sau đó cần rollback để không để fixture lại.

### 11.1. Assertion invariant toàn bảng

```sql
DO $$
DECLARE
    v_invalid_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_invalid_count
    FROM inventory
    WHERE quantity < 0;

    IF v_invalid_count <> 0 THEN
        RAISE EXCEPTION
            'Inventory invariant violated: % invalid rows',
            v_invalid_count;
    END IF;
END;
$$;
```

Nếu quantity đã có CHECK constraint, truy vấn này vẫn hữu ích trong audit/đối soát dữ liệu cũ hoặc dữ liệu được nạp qua một đường nhập đặc biệt.

### 11.2. Kiểm tra tổng nhiều bảng

Giả sử mỗi order có total_amount và order_items có quantity * unit_price:

```sql
SELECT
    o.order_id,
    o.total_amount,
    COALESCE(
        SUM(oi.quantity * oi.unit_price),
        0
    ) AS calculated_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount <>
       COALESCE(SUM(oi.quantity * oi.unit_price), 0);
```

Nếu không có dòng nào, các tổng bằng nhau theo biểu thức và quy tắc làm tròn đang dùng. Với tiền tệ, phải thống nhất rounding ở cấp dòng hay cấp tổng; phép tính ở đây chưa tự áp dụng quy tắc làm tròn nghiệp vụ.

### 11.3. Đừng chạy đối soát ngoài transaction mà không xét concurrency

Nếu dữ liệu đang được cập nhật đồng thời, truy vấn đối soát có thể nhìn thấy snapshot hợp lệ tại một thời điểm nhưng một transaction khác đang ở giữa quy trình nhiều bước. Hãy xác định isolation level và thời điểm chạy đối soát.

## 12. Trigger và bất biến trước/sau DML

Trigger có thể thay đổi dữ liệu hoặc ghi audit trong lúc INSERT/UPDATE/DELETE. Vì vậy kiểm thử DML cần quan sát cả side effect.

### 12.1. Trigger audit cho UPDATE

PostgreSQL:

```sql
CREATE OR REPLACE FUNCTION audit_inventory_change()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO inventory_audit (
        product_id,
        old_quantity,
        new_quantity,
        action_name
    )
    VALUES (
        OLD.product_id,
        OLD.quantity,
        NEW.quantity,
        'UPDATE'
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER inventory_update_audit
AFTER UPDATE OF quantity ON inventory
FOR EACH ROW
EXECUTE FUNCTION audit_inventory_change();
```

Test:

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = :product_id;

SELECT COUNT(*)
FROM inventory_audit
WHERE product_id = :product_id
  AND action_name = 'UPDATE';

ROLLBACK;
```

Cần xác nhận đúng số audit row theo số inventory row thực sự thay đổi. Nếu trigger chạy theo dòng, UPDATE 10 dòng có thể tạo 10 audit row.

### 12.2. Kiểm tra trigger không chạy khi UPDATE không khớp

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = -999;

SELECT COUNT(*)
FROM inventory_audit
WHERE product_id = -999;

ROLLBACK;
```

Kỳ vọng không có dòng inventory nào được cập nhật và không có audit row. Tuy nhiên trigger statement-level có thể chạy một lần ngay cả khi không có dòng bị thay đổi; cần hiểu loại trigger của DBMS.

### 12.3. Trigger phải xử lý nhiều dòng

SQL Server trigger thường được kích hoạt theo statement; các bảng logic inserted và deleted có thể chứa nhiều dòng. Không viết trigger SQL Server giả định chỉ có một dòng.

PostgreSQL, Oracle, MySQL và SQLite có mô hình trigger khác nhau về row/statement timing và khả năng transition data. Test bằng UPDATE/DELETE nhiều dòng, không chỉ một dòng.

### 12.4. Tránh side effect khó rollback

Audit table cùng database và cùng transaction thường rollback cùng DML. Nhưng nếu trigger gọi hệ thống bên ngoài hoặc phát thông điệp không transaction-aware, rollback database không tự thu hồi side effect đó.

Mẫu outbox thường an toàn hơn: ghi event vào bảng outbox trong cùng transaction, rồi worker phát event sau commit.

## 13. Kiểm tra UPDATE/DELETE nhiều dòng

Một câu DML có thể tác động nhiều dòng dù người viết dự định một dòng.

### 13.1. UPDATE nhiều dòng có kiểm soát

```sql
UPDATE inventory
SET
    quantity = quantity + 5,
    version = version + 1
WHERE product_id IN (101, 102, 103)
RETURNING product_id, quantity, version;
```

Test cần so sánh tập product_id thực tế với tập mong đợi, không chỉ đếm số dòng.

Nếu một ID không tồn tại, kết quả chỉ có hai dòng. Điều đó có thể là thành công hoặc thất bại tùy hợp đồng. Phải định nghĩa rõ có yêu cầu tất cả ID phải tồn tại không.

### 13.2. DELETE nhiều dòng

```sql
DELETE FROM inventory
WHERE product_id IN (101, 102)
RETURNING product_id;
```

Kiểm tra:

- Tập ID bị xóa đúng.
- Không xóa ID khác.
- FK side effect đúng.
- Audit đúng số lượng.
- Sau thao tác không còn dòng mục tiêu.

### 13.3. So sánh tập kết quả

Trong ứng dụng test, chuyển các ID trả về thành set và so sánh với set mong đợi. Không phụ thuộc thứ tự RETURNING/OUTPUT nếu không có quy tắc ORDER BY hỗ trợ.

## 14. Transaction, savepoint và rollback khi assertion thất bại

Một test DML nên cô lập dữ liệu và dọn dẹp an toàn.

### 14.1. Mẫu transaction tổng quát

```text
BEGIN TRANSACTION

    chuẩn bị fixture
    xác nhận trạng thái ban đầu

    chạy INSERT / UPDATE / DELETE
    xác nhận số dòng và giá trị trả về
    xác nhận invariant sau thao tác

    nếu tất cả đúng:
        ROLLBACK hoặc COMMIT theo mục tiêu test
    nếu có assertion sai:
        ROLLBACK và báo test failed
```

Trong unit/integration test, rollback thường giúp giữ database sạch. Một test về durability/commit cần commit và kiểm tra từ transaction/connection khác.

### 14.2. Savepoint

Có thể dùng savepoint để thử một thao tác dự kiến thất bại mà vẫn tiếp tục test trong transaction ngoài:

```sql
BEGIN;

SAVEPOINT before_invalid_update;

UPDATE inventory
SET quantity = -10
WHERE product_id = 1;

-- Nếu constraint từ chối, rollback về savepoint.
ROLLBACK TO SAVEPOINT before_invalid_update;

SELECT quantity
FROM inventory
WHERE product_id = 1;

ROLLBACK;
```

Cú pháp và trạng thái transaction sau lỗi khác nhau. PostgreSQL cần rollback về savepoint sau lỗi trước khi tiếp tục; không nên giả định mọi DBMS tự bỏ qua statement thất bại theo cùng cách.

### 14.3. Test failure path là bắt buộc

Không chỉ kiểm tra happy path. Hãy kiểm tra:

- UNIQUE violation.
- CHECK violation.
- FK violation.
- Không đủ tồn kho.
- Version cũ.
- Target không tồn tại.
- Trigger báo lỗi.
- Timeout/deadlock.
- Một bước trong giao dịch nhiều bước thất bại.

Sau mỗi lỗi, xác nhận dữ liệu không ở trạng thái nửa vời.

## 15. Kiểm tra concurrency và race condition

Kiểm tra trước/sau trên một connection không chứng minh an toàn khi có nhiều transaction.

### 15.1. Race condition trong kiểm tra tồn kho

Tồn kho hiện tại là 5. Hai transaction cùng đọc 5:

- Transaction A muốn xuất 4.
- Transaction B muốn xuất 4.
- Cả hai thấy đủ hàng.
- Nếu chỉ SELECT rồi UPDATE không điều kiện, cả hai có thể cùng xử lý theo trạng thái cũ.

Dùng UPDATE có predicate nguyên tử:

```sql
UPDATE inventory
SET quantity = quantity - :amount
WHERE product_id = :product_id
  AND :amount > 0
  AND quantity >= :amount;
```

Với constraint quantity >= 0, DBMS bảo vệ trạng thái. Trong tình huống hai transaction tranh chấp, một thao tác có thể chờ hoặc không còn thỏa predicate sau khi khóa được giải phóng. Ứng dụng phải xử lý kết quả phù hợp.

### 15.2. Test hai connection

Một concurrency test nên:

1. Tạo một sản phẩm với tồn kho 5.
2. Mở hai connection độc lập.
3. Đồng thời yêu cầu mỗi connection xuất 4.
4. Commit/rollback theo kết quả.
5. Xác nhận chỉ tối đa một thao tác thành công.
6. Xác nhận tồn cuối không âm.
7. Xác nhận audit/order allocation chỉ ghi cho thao tác thành công.

Không thể chứng minh race condition bằng một test tuần tự trên một connection.

### 15.3. Unique constraint là hàng rào concurrency

Mẫu không an toàn:

```sql
SELECT COUNT(*)
FROM products
WHERE sku = 'SKU-900';

-- Nếu count = 0 thì INSERT
```

Hai transaction có thể cùng đọc count = 0 rồi cùng INSERT. UNIQUE constraint mới là bảo đảm cuối cùng. Ứng dụng nên xử lý conflict/unique violation theo nghiệp vụ.

### 15.4. Isolation level không thay constraint

SERIALIZABLE có thể phát hiện/đẩy lỗi serialization và yêu cầu retry, nhưng UNIQUE/FK/CHECK vẫn là cách mô tả invariant schema phù hợp. Đừng bỏ constraint chỉ vì dùng isolation level cao.

### 15.5. Retry phải an toàn

Nếu retry sau deadlock/serialization failure:

- Transaction cũ phải rollback.
- Toàn bộ logic transaction cần chạy lại theo hợp đồng.
- Không gửi side effect ngoài DB trước commit.
- Dùng idempotency key nếu client có thể gửi lặp.
- Không giả định mọi lỗi database đều retry được.

## 16. Kiểm tra idempotency và thao tác lặp

Một request có thể được gửi lại do timeout hoặc mạng lỗi. Test cần xác định lặp INSERT/UPDATE/DELETE sẽ có tác động gì.

### 16.1. INSERT có idempotency key

Ví dụ bảng request:

```sql
CREATE TABLE payment_requests (
    request_key TEXT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

UNIQUE/PRIMARY KEY trên request_key ngăn cùng request được ghi hai lần. Tuy nhiên, xử lý conflict phải xác minh payload lần gửi lại có giống request gốc hay không; không chỉ bỏ qua mọi duplicate.

### 16.2. UPDATE lặp lại

Lệnh:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 10;
```

không idempotent: chạy hai lần sẽ trừ hai đơn vị.

Trong khi đặt trạng thái tuyệt đối:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE order_id = 100
  AND status = 'PENDING';
```

có thể an toàn hơn khi lặp, nhưng cần kiểm tra rowcount và trạng thái trước đó. Một lần lặp có thể trả 0 dòng vì trạng thái đã đổi.

### 16.3. DELETE lặp lại

DELETE cùng khóa lần đầu có thể xóa một dòng; lần thứ hai không xóa dòng nào. API nên quy định lần hai là thành công idempotent hay trả not found.

## 17. Kiểm tra trước/sau theo từng loại thao tác

| DML | Trước | Sau |
|---|---|---|
| INSERT | Khóa nghiệp vụ chưa xung đột, FK cha tồn tại, input hợp lệ, có quyền | Một dòng mới, ID/default đúng, side effect đúng, invariant vẫn đúng |
| UPDATE | Target tồn tại, trạng thái cho phép, version phù hợp, input hợp lệ | Giá trị mới đúng, dòng ngoài phạm vi không đổi, version/audit đúng |
| DELETE | Target tồn tại, được phép xóa, phụ thuộc FK đã xử lý | Target biến mất, cascade/restrict/set null đúng, không orphan, audit đúng |
| Batch DML | Tập khóa đầu vào xác định, chính sách partial success rõ | Tập dòng tác động đúng, không thiếu/thừa, invariant theo batch đúng |
| Multi-table transaction | Tất cả điều kiện ban đầu và quyền đã thỏa | Mọi bảng cùng chuyển trạng thái; không commit một phần |

## 18. Đối chiếu cách kiểm tra theo năm DBMS

Các nguyên tắc invariant giống nhau, nhưng cú pháp assertion, DML output, transaction và constraint khác nhau.

### 18.1. PostgreSQL

Điểm mạnh:

- RETURNING cho INSERT/UPDATE/DELETE.
- Constraint CHECK/UNIQUE/FK và một số constraint DEFERRABLE.
- DO block/PLpgSQL để viết assertion bằng RAISE EXCEPTION.
- Transactional DDL cho nhiều lệnh.
- MVCC và isolation levels.

Ví dụ hậu kiểm:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 1
RETURNING product_id, quantity;
```

Assertion bằng PL/pgSQL:

```sql
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM inventory
    WHERE quantity < 0;

    IF v_count > 0 THEN
        RAISE EXCEPTION 'Negative inventory detected';
    END IF;
END;
$$;
```

Lưu ý: khi một statement lỗi trong transaction, transaction bị đánh dấu aborted cho tới khi rollback toàn bộ hoặc rollback về savepoint.

### 18.2. MySQL

Với MySQL, dùng InnoDB nếu cần transaction, foreign key và row locking như ứng dụng OLTP thường kỳ vọng.

```sql
START TRANSACTION;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 1
  AND quantity >= 2;

SELECT product_id, quantity
FROM inventory
WHERE product_id = 1;

ROLLBACK;
```

MySQL không có RETURNING DML tổng quát như PostgreSQL trong MySQL 8.x; ứng dụng có thể SELECT lại trong cùng transaction hoặc dùng thông tin generated key/affected rows theo trường hợp.

CHECK constraint được thực thi trong MySQL từ 8.0.16; các bản cũ hơn có thể parse nhưng bỏ qua CHECK. Phải kiểm tra phiên bản thật.

Assertion phức tạp thường được thực hiện ở test harness hoặc stored procedure với SIGNAL:

```sql
DELIMITER //

CREATE PROCEDURE assert_inventory_nonnegative()
BEGIN
    IF EXISTS (
        SELECT 1
        FROM inventory
        WHERE quantity < 0
    ) THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Negative inventory detected';
    END IF;
END//

DELIMITER ;
```

SIGNAL có thể dùng trong stored program theo quy tắc MySQL; đây không phải cú pháp portable.

DDL nhiều loại có implicit commit. Không đặt ALTER TABLE vào giữa transaction test rồi giả định ROLLBACK sẽ hoàn nguyên schema.

### 18.3. SQL Server

SQL Server dùng T-SQL, OUTPUT và TRY/CATCH/THROW:

```sql
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    UPDATE dbo.inventory
    SET quantity = quantity - 2
    OUTPUT
        deleted.quantity AS old_quantity,
        inserted.quantity AS new_quantity
    WHERE product_id = 1
      AND quantity >= 2;

    IF @@ROWCOUNT <> 1
        THROW 51000, 'Expected one inventory row', 1;

    IF EXISTS (
        SELECT 1
        FROM dbo.inventory
        WHERE quantity < 0
    )
        THROW 51001, 'Negative inventory detected', 1;

    ROLLBACK TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
```

OUTPUT inserted/deleted có thể trả trạng thái trước/sau. Khi dùng OUTPUT trong câu lệnh có trigger, cần hiểu thứ tự và trạng thái mà OUTPUT phản ánh so với các thay đổi trong AFTER trigger; nếu cần trạng thái cuối sau trigger, hãy SELECT lại sau statement.

SQL Server không hỗ trợ deferrable constraints theo cách PostgreSQL/Oracle. Constraint được kiểm tra theo cơ chế của engine khi statement thực thi.

### 18.4. Oracle

Oracle dùng PL/SQL để assert:

```sql
DECLARE
    v_count NUMBER;
BEGIN
    UPDATE inventory
    SET quantity = quantity - 2
    WHERE product_id = 1
      AND quantity >= 2;

    IF SQL%ROWCOUNT <> 1 THEN
        RAISE_APPLICATION_ERROR(
            -20001,
            'Expected one inventory row'
        );
    END IF;

    SELECT COUNT(*)
    INTO v_count
    FROM inventory
    WHERE quantity < 0;

    IF v_count > 0 THEN
        RAISE_APPLICATION_ERROR(
            -20002,
            'Negative inventory detected'
        );
    END IF;

    ROLLBACK;
END;
/
```

Oracle có `SQL%ROWCOUNT` cho số dòng tác động của DML trong PL/SQL và `RETURNING INTO` để lấy giá trị.

DDL thường có implicit commit; test transaction DML không được trộn DDL vào giữa rồi kỳ vọng rollback mọi thứ. Oracle có một số constraint DEFERRABLE, nhưng phải khai báo và đặt timing rõ.

### 18.5. SQLite

SQLite hỗ trợ transaction và CHECK/UNIQUE/FOREIGN KEY, nhưng foreign key enforcement phải được bật cho connection:

```sql
PRAGMA foreign_keys = ON;

BEGIN IMMEDIATE;

UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 1
  AND quantity >= 2;

SELECT product_id, quantity
FROM inventory
WHERE product_id = 1;

ROLLBACK;
```

SQLite 3.35+ hỗ trợ RETURNING:

```sql
UPDATE inventory
SET quantity = quantity - 2
WHERE product_id = 1
RETURNING product_id, quantity;
```

SQLite không có stored procedure native hay PL/SQL/T-SQL assertion block. Assertion thường nằm trong test harness của ứng dụng; có thể dùng bảng tạm với CHECK để buộc một điều kiện test thất bại thành constraint error.

SQLite cho phép nhiều reader nhưng chỉ một writer đồng thời tại một thời điểm. BEGIN IMMEDIATE có thể lấy quyền writer sớm để tránh một số tình huống nâng cấp transaction đọc sang ghi thất bại; nó không biến SQLite thành hệ thống nhiều writer song song.

## 19. Ma trận khác biệt về constraint và transaction

| Tính năng | PostgreSQL | MySQL/InnoDB | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| CHECK | Có | Được thực thi từ 8.0.16 | Có | Có | Có |
| UNIQUE | Có | Có | Có | Có | Có |
| FOREIGN KEY | Có | Có với InnoDB | Có | Có | Có, cần bật enforcement |
| DEFERRABLE constraint | Một số loại | Không theo mô hình tổng quát | Không | Có với loại constraint hỗ trợ | FK có thể deferred |
| Transaction DML | Có | Có với InnoDB | Có | Có | Có |
| Transactional DDL | Nhiều DDL | Nhiều DDL implicit commit | Nhiều DDL, có ngoại lệ | DDL implicit commit | Nhiều DDL có thể transactional |
| DML output | RETURNING | Không tổng quát như PG | OUTPUT | RETURNING INTO | RETURNING từ 3.35 |
| Assertion block | PL/pgSQL DO | Stored program/SIGNAL hoặc harness | T-SQL THROW | PL/SQL raise_application_error | Test harness |

Đây là ma trận định hướng. Cần kiểm tra từng constraint type, DDL statement, engine và phiên bản.

## 20. Kiểm thử trigger nhiều dòng và thứ tự side effect

DML test nên bao gồm statement chỉ tác động một dòng và statement tác động nhiều dòng.

### 20.1. Vì sao chỉ test một dòng chưa đủ?

Một trigger hoặc stored routine có thể vô tình giả định chỉ có một bản ghi:

- SQL Server trigger đọc một giá trị scalar từ inserted.
- Trigger bỏ sót một số dòng trong batch.
- Audit chỉ ghi một event dù UPDATE thay đổi nhiều dòng.
- Tổng hợp dùng biến bị ghi đè qua mỗi dòng.
- Trigger chạy statement-level nhưng test nghĩ row-level.

### 20.2. Test batch

```sql
BEGIN;

UPDATE inventory
SET quantity = quantity + 1
WHERE product_id IN (1, 2, 3)
RETURNING product_id, quantity;

SELECT COUNT(*)
FROM inventory_audit
WHERE action_name = 'UPDATE'
  AND product_id IN (1, 2, 3);

ROLLBACK;
```

Nếu audit trigger là row-level và cả ba dòng đều thỏa điều kiện trigger, số audit event dự kiến là 3. Nếu trigger được thiết kế statement-level, hợp đồng có thể khác; cần test đúng mục tiêu.

### 20.3. Không giả định trigger order nếu DBMS không cam kết

Nếu có nhiều trigger cùng timing/event, thứ tự thực thi có thể khác hoặc cần khai báo cơ chế riêng. Không viết invariant phụ thuộc vào thứ tự không được tài liệu DBMS bảo đảm.

## 21. Kiểm tra bất biến theo trạng thái đơn hàng

Một ví dụ khác là luồng trạng thái:

```text
DRAFT -> CONFIRMED -> PAID -> SHIPPED -> COMPLETED
                 \-> CANCELLED (nếu chính sách cho phép)
```

Không phải mọi chuyển đổi đều hợp lệ. Ví dụ:

- DRAFT -> CONFIRMED: hợp lệ nếu có ít nhất một dòng hàng.
- CONFIRMED -> PAID: hợp lệ khi thanh toán được xác nhận.
- PAID -> CANCELLED: cần quy trình hoàn tiền.
- SHIPPED -> DRAFT: thường không hợp lệ.

### 21.1. Update có precondition

```sql
UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'DRAFT'
  AND EXISTS (
      SELECT 1
      FROM order_items
      WHERE order_items.order_id = orders.order_id
  );
```

Hậu điều kiện:

- Chỉ order DRAFT có ít nhất một item mới được chuyển.
- Đơn không có item không đổi.
- Đơn đang PAID/SHIPPED không bị chuyển ngược.
- Nếu yêu cầu có audit, ghi đúng một event transition.

### 21.2. State transition table

Có thể lưu bảng chuyển trạng thái hợp lệ:

```sql
CREATE TABLE allowed_order_transitions (
    from_status TEXT NOT NULL,
    to_status TEXT NOT NULL,
    PRIMARY KEY (from_status, to_status)
);
```

Service/trigger có thể kiểm tra cặp trạng thái. Test phải kiểm tra cả chuyển hợp lệ và không hợp lệ, bao gồm trạng thái cũ NULL hoặc không nhận diện.

### 21.3. Đừng chỉ test trạng thái cuối

Nếu đơn hàng chuyển DRAFT -> PAID trực tiếp, trạng thái cuối PAID có thể là một giá trị hợp lệ về mặt CHECK nhưng bỏ qua bước CONFIRMED và quy tắc thanh toán. Cần kiểm tra **transition**, không chỉ miền giá trị.

## 22. Kiểm tra bất biến với dữ liệu tiền tệ

Tiền cần quy tắc precision và rounding rõ ràng.

Ví dụ order total:

\[
Total = \sum_i Quantity_i \times UnitPrice_i
\]

Các câu hỏi cần chốt:

- Làm tròn từng dòng hay chỉ làm tròn tổng?
- Thuế tính trước hay sau chiết khấu?
- Mỗi dòng có thể dùng currency khác nhau không?
- Số chữ số thập phân theo currency nào?
- Giá snapshot tại thời điểm đặt hàng hay đọc giá hiện tại?
- UPDATE order item có cập nhật order total cùng transaction không?

Một test nên tạo dữ liệu có phần lẻ gây khác biệt rounding để chứng minh quy tắc, không chỉ test số nguyên dễ tính.

### 22.1. Kiểm tra aggregate sau UPDATE

```sql
SELECT
    o.order_id,
    o.total_amount,
    ROUND(
        COALESCE(
            SUM(oi.quantity * oi.unit_price),
            0
        ),
        2
    ) AS expected_total
FROM orders AS o
LEFT JOIN order_items AS oi
    ON oi.order_id = o.order_id
WHERE o.order_id = :order_id
GROUP BY o.order_id, o.total_amount;
```

Đây là truy vấn minh họa cho quy tắc làm tròn hai chữ số; hệ thống thực tế phải dùng đúng quy tắc thuế/tiền tệ đã thống nhất.

## 23. Kiểm tra audit, outbox và event

Nếu INSERT/UPDATE/DELETE phải tạo audit hoặc event, đó là một phần postcondition.

### 23.1. Audit row

Ví dụ sau UPDATE giá:

- Có đúng một audit event cho thay đổi.
- old_value đúng giá trước.
- new_value đúng giá sau.
- actor_id và timestamp có giá trị.
- Event gắn đúng product_id.

Không chỉ kiểm tra COUNT(*) = 1; hãy kiểm tra nội dung event.

### 23.2. Outbox event trong cùng transaction

Một transaction có thể cập nhật đơn hàng và thêm event:

```sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id
  AND status = 'DRAFT';

INSERT INTO outbox_events (
    aggregate_type,
    aggregate_id,
    event_type,
    payload
)
VALUES (
    'Order',
    :order_id,
    'OrderConfirmed',
    :payload
);

COMMIT;
```

Test cần bảo đảm:

- Nếu UPDATE thất bại thì không có outbox event.
- Nếu INSERT outbox thất bại thì UPDATE cũng rollback.
- Nếu commit thành công, cả trạng thái và event đều tồn tại.
- Consumer có thể xử lý event lặp bằng idempotency.

Không gọi external API trực tiếp từ trigger rồi giả định transaction rollback sẽ hoàn tác lời gọi mạng.

## 24. Thiết kế test fixture và cô lập dữ liệu

### 24.1. Dùng dữ liệu riêng cho mỗi test

Tránh dùng SKU cố định có thể đụng với test khác nếu database được chia sẻ. Có thể tạo namespace/test_run_id hoặc fixture có khóa riêng.

### 24.2. Không phụ thuộc ID tăng liên tục

Identity/sequence có thể tạo khoảng trống do rollback hoặc cache. Đừng test rằng ID tiếp theo phải đúng bằng ID trước + 1. Kiểm tra ID tồn tại, duy nhất và liên kết đúng.

### 24.3. Rollback fixture

Nếu mọi thao tác trong test nằm cùng connection/transaction, rollback có thể dọn dữ liệu. Nhưng:

- Một số DDL implicit commit.
- Một số test cần kiểm tra commit durability.
- Một số tác động bên ngoài không rollback.
- Connection pool có thể tái sử dụng connection với session state cũ.

Xác định rõ ranh giới transaction và reset session state.

### 24.4. Test chạy song song

Hai test dùng chung SKU/account cố định có thể đụng nhau. Tạo fixture cô lập hoặc database/schema riêng, không dựa vào thứ tự test.

## 25. Đối chiếu kiểm thử DML theo năm DBMS

| Nội dung | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
|---|---|---|---|---|---|
| Dòng cũ/mới trong DML | RETURNING cho trạng thái sau; trigger OLD/NEW | Trigger OLD/NEW; SELECT sau DML | OUTPUT deleted/inserted | RETURNING INTO; trigger :OLD/:NEW | RETURNING trạng thái sau; trigger OLD/NEW |
| Assertion thủ tục | DO/PLpgSQL RAISE | Procedure + SIGNAL | IF/THROW | PL/SQL raise_application_error | Test harness |
| Kiểm tra số dòng | Driver rowcount/GET DIAGNOSTICS | ROW_COUNT()/driver | @@ROWCOUNT | SQL%ROWCOUNT | changes()/driver |
| Rollback test | BEGIN/ROLLBACK, SAVEPOINT | START TRANSACTION/ROLLBACK | BEGIN TRAN/ROLLBACK | DML transaction, COMMIT/ROLLBACK | BEGIN/ROLLBACK/SAVEPOINT |
| Trigger multi-row | Có row/statement triggers | Row triggers | Statement triggers, inserted/deleted sets | Row/statement/compound triggers | Row triggers |
| DDL rollback | Nhiều DDL transactional | Nhiều DDL implicit commit | Nhiều DDL transactional có ngoại lệ | DDL implicit commit | Nhiều DDL transactional |

**Rowcount không có semantics hoàn toàn giống nhau ở mọi DBMS/driver.** Hãy kiểm tra trạng thái cuối và dùng OUTPUT/RETURNING hoặc SELECT trong transaction khi cần.

## 26. Các lỗi kiểm thử thường gặp

1. **Chỉ kiểm tra câu lệnh không ném lỗi.** Nó có thể cập nhật sai dòng hoặc sai giá trị.
2. **Chỉ kiểm tra rowcount.** Số dòng không chứng minh dữ liệu sau đúng.
3. **SELECT kiểm tra rồi mới UPDATE không khóa.** Có race condition.
4. **Không kiểm tra dòng ngoài phạm vi.** WHERE thiếu điều kiện có thể tác động hàng loạt.
5. **Chỉ test một dòng.** Batch/trigger có thể lỗi khi nhiều dòng.
6. **Không kiểm tra FK side effect.** Cascade/Set Null/Restrict có thể làm sai dữ liệu liên quan.
7. **Không test negative path.** CHECK/UNIQUE/FK/trigger có thể thất bại ngoài dự kiến.
8. **Nuốt exception.** Test báo pass dù transaction đã lỗi.
9. **Rollback không đúng transaction.** Fixture vẫn còn hoặc thao tác đã commit.
10. **Dùng DDL trong transaction rồi giả định mọi DB rollback DDL.** MySQL/Oracle có implicit commit.
11. **Dùng ID liên tiếp làm invariant.** Sequence có thể có gap.
12. **Không test concurrency.** Hai writer có thể phá invariant dù test đơn lẻ pass.
13. **Không kiểm tra version.** Lost update bị che khuất.
14. **Audit chỉ kiểm tra số dòng.** Nội dung old/new/actor có thể sai.
15. **Không kiểm tra trigger nhiều dòng.** SQL Server trigger có thể xử lý sai inserted/deleted set.
16. **Coi rowcount 0 luôn là lỗi.** Có thể là thao tác idempotent đã được áp dụng trước đó.
17. **Không phân biệt hard delete và soft delete.** Dữ liệu có thể vẫn còn.
18. **Chỉ kiểm tra tổng.** Hai dòng có thể sai riêng nhưng tổng vẫn đúng.
19. **Không kiểm tra rounding.** Tổng tiền sai ở các trường hợp biên.
20. **Chạy test trên SQLite rồi suy ra production server DBMS.** Locking, type, constraint và SQL semantics khác.
21. **Không cô lập fixture.** Test song song có thể va chạm.
22. **Gửi event trước commit.** Consumer có thể nhận event của giao dịch đã rollback.
23. **Dùng SELECT COUNT(*) để chống duplicate.** Unique constraint mới bảo đảm dưới concurrency.
24. **Không kiểm tra quyền.** DML đúng kỹ thuật nhưng người gọi không được phép sửa/xóa bản ghi.
25. **Không kiểm tra dữ liệu sau trigger.** Giá trị cuối có thể khác giá trị vừa gửi vào DML.

## 27. Bộ test mẫu cho INSERT, UPDATE, DELETE

Bộ test này dùng cùng một bảng đơn giản để mô tả cách tổ chức test.

### 27.1. Schema

```sql
CREATE TABLE test_items (
    item_id INTEGER PRIMARY KEY,
    item_code TEXT NOT NULL UNIQUE,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);
```

### 27.2. Test INSERT

**Arrange:**

```sql
BEGIN;

INSERT INTO test_items(item_id, item_code, quantity)
VALUES (1, 'ITEM-1', 10);
```

**Act:**

```sql
INSERT INTO test_items(item_id, item_code, quantity)
VALUES (2, 'ITEM-2', 5);
```

**Assert:**

```sql
SELECT COUNT(*) FROM test_items WHERE item_id = 2;
SELECT quantity FROM test_items WHERE item_id = 2;
```

Kỳ vọng: count = 1, quantity = 5. Sau đó rollback fixture.

Negative case: thử chèn item_code trùng và xác nhận dòng gốc không đổi.

### 27.3. Test UPDATE

**Arrange:** item 1 có quantity = 10.

**Act:**

```sql
UPDATE test_items
SET quantity = quantity - 3
WHERE item_id = 1
  AND quantity >= 3;
```

**Assert:**

```sql
SELECT quantity
FROM test_items
WHERE item_id = 1;
```

Kỳ vọng: quantity = 7; item 2 vẫn 5; không có quantity âm.

Negative case: thử trừ 100 và xác nhận không có dòng bị cập nhật hoặc constraint từ chối theo cách test được định nghĩa.

### 27.4. Test DELETE

**Arrange:** item 2 tồn tại.

**Act:**

```sql
DELETE FROM test_items
WHERE item_id = 2;
```

**Assert:**

```sql
SELECT COUNT(*)
FROM test_items
WHERE item_id = 2;
```

Kỳ vọng: count = 0; item 1 vẫn tồn tại và quantity vẫn 10 nếu test độc lập.

### 27.5. Test toàn bộ invariant sau mỗi thao tác

```sql
SELECT COUNT(*) AS invalid_rows
FROM test_items
WHERE item_code IS NULL
   OR quantity IS NULL
   OR quantity < 0;
```

Kỳ vọng invalid_rows = 0. Nếu CHECK/NOT NULL đã tồn tại, truy vấn này là lớp kiểm tra bổ sung cho test/reconciliation.

## 28. Tổ chức kiểm thử ở tầng ứng dụng

SQL test có thể được gọi từ Java/JUnit, Python/pytest hoặc framework tương ứng.

### 28.1. Arrange – Act – Assert

Một test dễ đọc có ba phần:

- **Arrange:** tạo fixture và xác nhận trạng thái ban đầu.
- **Act:** chạy một thao tác DML.
- **Assert:** kiểm tra hậu điều kiện, invariant và side effect.

Ví dụ pseudo Java:

```java
@Test
void decrementInventoryPreservesNonNegativeInvariant() {
    // Arrange
    long productId = insertProductWithStock(10);

    // Act
    int affected = repository.decrementStock(productId, 3);

    // Assert
    assertEquals(1, affected);
    assertEquals(7, repository.findStock(productId));
    assertTrue(repository.countNegativeStock() == 0);
}
```

Trong thực tế, test cần transaction/fixture cleanup phù hợp và kiểm tra behavior của repository trên DBMS thật.

### 28.2. Test lỗi mong đợi

Ví dụ:

```java
assertThrows(
    DataIntegrityViolationException.class,
    () -> repository.insertDuplicateSku("SKU-100")
);
```

Sau exception, cần kiểm tra dữ liệu ban đầu còn nguyên. Không chỉ xác nhận exception type; driver/framework có thể bọc exception, vì vậy test nên kiểm tra SQLSTATE/vendor code nếu cần phân loại chính xác.

### 28.3. Property-based testing

Với bất biến số lượng:

```text
Với mọi tồn kho ban đầu q >= 0
và lượng xuất d > 0:

nếu d <= q:
    thao tác thành công và tồn mới = q - d
nếu d > q:
    thao tác không làm tồn kho âm
```

Property-based test sinh nhiều cặp q,d để kiểm tra miền giá trị, đặc biệt 0, 1, số lớn và biên integer/decimal.

### 28.4. Mutation testing

Có thể kiểm tra chất lượng test bằng cách cố tình tạo lỗi trong code/query thử nghiệm:

- Bỏ điều kiện WHERE.
- Đổi dấu trừ thành dấu cộng.
- Bỏ tăng version.
- Bỏ ghi audit.
- Thay ON DELETE RESTRICT bằng CASCADE trong schema test.

Nếu test vẫn pass, test suite có thể chưa quan sát đủ hành vi.

## 29. Quy trình điều tra khi invariant bị vi phạm

Khi phát hiện trạng thái sai, đừng chỉ sửa dòng dữ liệu rồi bỏ qua nguyên nhân.

1. Ghi nhận khóa bản ghi và transaction/request liên quan.
2. Xác định bất biến nào bị phá.
3. So sánh trạng thái trước/sau từ audit/log nếu có.
4. Kiểm tra câu DML và predicate.
5. Kiểm tra trigger, cascade và stored procedure.
6. Kiểm tra transaction boundary và commit/rollback.
7. Kiểm tra concurrent writers, retry và isolation.
8. Xác định dữ liệu đã được đọc/ghi từ connection hoặc replica nào.
9. Tạo test tái hiện có fixture tối thiểu.
10. Sửa nguyên nhân và thêm regression test.
11. Đối soát dữ liệu đã bị ảnh hưởng theo quy trình được phê duyệt.

Không dùng log ứng dụng làm bằng chứng duy nhất về trạng thái database; transaction có thể rollback sau khi ứng dụng đã ghi log “đã xử lý”.

## 30. Bảng ghi nhớ nhanh

| Nội dung | Ghi nhớ |
|---|---|
| Invariant | Điều kiện phải luôn đúng |
| Precondition | Điều kiện trước thao tác |
| Postcondition | Trạng thái mong đợi sau thao tác |
| INSERT | Kiểm tra uniqueness, FK, defaults, row mới và side effect |
| UPDATE | Kiểm tra old/new, target scope, version và invariant |
| DELETE | Kiểm tra quyền, FK policy, orphan, audit và dòng còn lại |
| CHECK | Bất biến trên dòng |
| UNIQUE | Không trùng khóa |
| FOREIGN KEY | Tham chiếu hợp lệ |
| Transaction | Nhóm thay đổi commit/rollback cùng nhau |
| Savepoint | Điểm rollback cục bộ trong transaction |
| RETURNING | Trả dữ liệu DML ở PostgreSQL/SQLite hỗ trợ |
| OUTPUT | Trả inserted/deleted ở SQL Server |
| RETURNING INTO | Lấy giá trị DML trong PL/SQL |
| Rowcount | Hữu ích nhưng khác semantics theo driver/DBMS |
| Trigger | Side effect phải được kiểm tra |
| Multi-row DML | Test tập dòng, không chỉ một dòng |
| Concurrency | Test bằng nhiều connection |
| Optimistic version | Phát hiện lost update |
| Idempotency | Xử lý request lặp có chủ đích |
| Reconciliation | Truy vấn đối soát invariant |
| Fixture | Dữ liệu test riêng, có cleanup |
| Negative test | Chứng minh thao tác sai bị từ chối và không để lại trạng thái dở dang |

## 31. Bài tập có lời giải

Các bài tập dùng PostgreSQL làm cú pháp minh họa trừ khi nêu DBMS khác. Khi chạy trên hệ quản trị khác, thay cú pháp DML output/transaction tương ứng.

### Bài 1. Phân biệt invariant và precondition

**Câu hỏi:** “Số dư không âm” và “tài khoản nguồn có ít nhất 100 trước khi chuyển” là gì?

**Đáp án:** số dư không âm là invariant; đủ 100 để chuyển là precondition của thao tác cụ thể.

### Bài 2. Kiểm tra INSERT SKU duy nhất

**Đáp án:**

```sql
SELECT COUNT(*)
FROM products
WHERE sku = 'SKU-300';
```

Kết quả trước insert cần là 0, nhưng UNIQUE constraint vẫn phải bảo vệ race condition giữa kiểm tra và INSERT.

### Bài 3. Kiểm tra hậu điều kiện INSERT

**Đáp án:** sau insert, xác nhận đúng một dòng theo khóa nghiệp vụ, ID/default đúng, FK hợp lệ và các side effect theo hợp đồng.

### Bài 4. Vì sao SELECT trước rồi INSERT có race?

**Đáp án:** hai transaction có thể cùng đọc “chưa tồn tại” rồi cùng insert. UNIQUE constraint mới bảo đảm không trùng.

### Bài 5. Kiểm tra CHECK quantity

**Đáp án:**

```sql
quantity INTEGER NOT NULL CHECK (quantity >= 0)
```

Test cả giá trị hợp lệ và giá trị âm; sau lỗi xác nhận không có trạng thái âm được lưu.

### Bài 6. UPDATE trừ 3 từ tồn kho

**Đáp án:**

```sql
UPDATE inventory
SET quantity = quantity - 3
WHERE product_id = :id
  AND quantity >= 3;
```

Sau đó kiểm tra giá trị mới, dòng không liên quan và invariant.

### Bài 7. UPDATE trả rowcount 0 có nghĩa gì?

**Đáp án:** có thể không tìm thấy dòng, không thỏa precondition, version cũ hoặc semantics rowcount của driver. Cần định nghĩa hợp đồng và kiểm tra nguyên nhân.

### Bài 8. Kiểm tra optimistic concurrency

**Đáp án:**

```sql
UPDATE inventory
SET quantity = :new_quantity,
    version = version + 1
WHERE product_id = :id
  AND version = :expected_version;
```

Thành công phải tác động đúng một dòng; version tăng đúng một; không ghi đè phiên bản mới hơn.

### Bài 9. Vì sao rowcount 1 chưa đủ?

**Đáp án:** có thể cập nhật sai giá trị hoặc sai bản ghi. Phải xác nhận postcondition và các dòng ngoài phạm vi.

### Bài 10. DELETE RESTRICT khi còn inventory

**Đáp án:** DELETE sản phẩm bị từ chối; product và inventory vẫn còn nguyên.

### Bài 11. DELETE CASCADE cần test gì?

**Đáp án:** dòng cha biến mất, tất cả dòng con dự kiến bị xóa, không xóa nhầm dòng khác và audit side effect đúng.

### Bài 12. DELETE SET NULL cần điều kiện schema nào?

**Đáp án:** cột FK phải cho phép NULL; sau khi xóa cha, dòng con còn và FK trở thành NULL.

### Bài 13. Soft delete là DML nào?

**Đáp án:** thường là UPDATE đặt deleted_at/active, không phải DELETE vật lý. Test phải xác nhận dòng vẫn tồn tại và bị loại khỏi truy vấn mặc định.

### Bài 14. Chuyển tiền cần invariant nào?

**Đáp án:** số dư từng tài khoản không âm; tổng tiền được bảo toàn; đúng nguồn/đích và đúng amount; cả hai cập nhật cùng commit/rollback.

### Bài 15. Vì sao tổng tiền đúng vẫn chưa đủ?

**Đáp án:** hai tài khoản có thể nhận sai số tiền nhưng tổng vẫn bằng nhau. Phải kiểm tra từng postcondition.

### Bài 16. Trigger audit sau UPDATE cần kiểm tra gì?

**Đáp án:** số event, product_id, old_value, new_value, actor và timestamp theo hợp đồng.

### Bài 17. UPDATE không khớp dòng có thể kích hoạt trigger không?

**Đáp án:** row-level trigger thường không có dòng để kích hoạt; statement-level trigger có thể vẫn chạy. Phụ thuộc DBMS và loại trigger.

### Bài 18. SQL Server trigger cần xử lý inserted/deleted thế nào?

**Đáp án:** coi đây là tập có thể chứa nhiều dòng; không gán một giá trị scalar từ inserted/deleted như thể luôn chỉ có một dòng.

### Bài 19. Vì sao phải test batch DML?

**Đáp án:** lỗi trigger, audit, tổng hợp và phạm vi WHERE có thể chỉ xuất hiện khi nhiều dòng cùng thay đổi.

### Bài 20. Assertion PostgreSQL báo lỗi bằng gì?

**Đáp án:** PL/pgSQL RAISE EXCEPTION trong DO/function/block.

### Bài 21. SQL Server báo assertion failure bằng gì?

**Đáp án:** THROW trong T-SQL; kết hợp TRY/CATCH và rollback transaction.

### Bài 22. Oracle báo assertion failure bằng gì?

**Đáp án:** RAISE_APPLICATION_ERROR trong PL/SQL block.

### Bài 23. MySQL báo lỗi tùy chỉnh trong procedure bằng gì?

**Đáp án:** SIGNAL SQLSTATE trong stored program.

### Bài 24. SQLite assertion thường đặt ở đâu?

**Đáp án:** test harness ứng dụng; SQLite không có stored procedure/assertion block native như PL/SQL/T-SQL.

### Bài 25. DDL rollback giống nhau trên năm DBMS không?

**Đáp án:** Không. MySQL nhiều DDL và Oracle DDL thường implicit commit; PostgreSQL/SQLite/SQL Server có nhiều DDL transactional hơn nhưng vẫn cần kiểm tra từng lệnh.

### Bài 26. Làm sao test hai transaction cùng xuất hàng?

**Đáp án:** dùng hai connection đồng thời, tồn kho 5, mỗi transaction xuất 4; xác nhận tối đa một thành công và tồn cuối không âm.

### Bài 27. Vì sao SELECT COUNT rồi INSERT không chống duplicate?

**Đáp án:** có race condition. UNIQUE constraint phải bảo vệ ở database.

### Bài 28. Retry transaction cần lưu ý gì?

**Đáp án:** rollback transaction cũ, chạy lại toàn bộ logic phù hợp, không gửi side effect trước commit và dùng idempotency key khi cần.

### Bài 29. Kiểm tra audit chỉ COUNT(*) = 1 có đủ không?

**Đáp án:** Không. Cần kiểm tra nội dung old/new, actor, entity ID và event type.

### Bài 30. Nêu quy trình Arrange–Act–Assert cho UPDATE tồn kho

**Đáp án:**
1. Arrange: tạo sản phẩm với tồn kho 10.
2. Act: xuất 3 bằng UPDATE có predicate quantity >= 3.
3. Assert: đúng một dòng được cập nhật, tồn mới là 7, version tăng đúng, không có dòng âm và sản phẩm khác không đổi.
4. Rollback/cleanup fixture theo chiến lược test.

## 32. Kết luận

Kiểm tra bất biến trước và sau INSERT, UPDATE, DELETE giúp chứng minh dữ liệu không chỉ “ghi được” mà còn **đúng về nghiệp vụ và nhất quán sau mỗi thay đổi**.

Một bộ kiểm thử đáng tin cậy cần quan sát:

- Trạng thái ban đầu và precondition.
- Dòng thực sự bị tác động.
- Giá trị cũ/mới và hậu điều kiện.
- Constraint, foreign key, trigger và side effect.
- Transaction, rollback và lỗi giữa chừng.
- Concurrency, version và thao tác lặp.
- Các dòng/bảng không nằm trong phạm vi phải được giữ nguyên.

Hãy để constraint bảo vệ các quy tắc mà database có thể cưỡng chế, dùng transaction để nhóm thay đổi nguyên tử, và viết assertion để kiểm tra postcondition cùng side effect. Với dữ liệu nhiều bảng hoặc nhiều writer, cần kiểm thử bằng transaction/connection thực tế thay vì chỉ chạy một câu SELECT trước rồi một câu UPDATE sau.

**Một DML chỉ được xem là đúng khi trạng thái sau thao tác thỏa bất biến, đáp ứng hậu điều kiện, và khi thất bại không để lại dữ liệu dở dang.**

## Tài liệu tham khảo

- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): CHECK, UNIQUE, PRIMARY KEY, FOREIGN KEY và constraint deferral.
- [PostgreSQL — Transactions](https://www.postgresql.org/docs/current/tutorial-transactions.html): BEGIN, COMMIT, ROLLBACK và transaction.
- [PostgreSQL — RETURNING](https://www.postgresql.org/docs/current/dml-returning.html): lấy dữ liệu từ INSERT/UPDATE/DELETE.
- [PostgreSQL — PL/pgSQL Errors and Messages](https://www.postgresql.org/docs/current/plpgsql-errors-and-messages.html): RAISE và xử lý lỗi.
- [MySQL — InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-model.html): transaction và concurrency.
- [MySQL — CHECK Constraints](https://dev.mysql.com/doc/refman/8.4/en/create-table-check-constraints.html): CHECK constraint và phiên bản hỗ trợ.
- [MySQL — SIGNAL Statement](https://dev.mysql.com/doc/refman/8.4/en/signal.html): phát lỗi trong stored programs.
- [Microsoft Learn — OUTPUT Clause](https://learn.microsoft.com/en-us/sql/t-sql/queries/output-clause-transact-sql): giá trị inserted/deleted từ DML.
- [Microsoft Learn — TRY...CATCH](https://learn.microsoft.com/en-us/sql/t-sql/language-elements/try-catch-transact-sql): xử lý lỗi trong T-SQL.
- [Oracle — Constraints](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): constraint và deferrable behavior.
- [Oracle — DML RETURNING Clause](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html): RETURNING INTO và DML.
- [SQLite — Transactions](https://www.sqlite.org/lang_transaction.html): transaction modes và locking.
- [SQLite — Foreign Key Support](https://www.sqlite.org/foreignkeys.html): bật và kiểm tra foreign key enforcement.
- [SQLite — RETURNING](https://www.sqlite.org/lang_returning.html): RETURNING clause và giới hạn.
- [OWASP — Database Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Database_Security_Cheat_Sheet.html): quyền tối thiểu, bảo vệ dữ liệu và thực hành bảo mật database.

