# Kiểm tra trước khi ghi và tranh chấp khi nhiều thao tác xảy ra đồng thời

Một hệ thống có thể kiểm tra dữ liệu đầu vào rất kỹ nhưng vẫn ghi ra dữ liệu sai khi nhiều yêu cầu chạy cùng lúc. Ví dụ, hai khách hàng cùng đặt chiếc ghế cuối cùng trong kho. Cả hai yêu cầu đều đọc thấy còn một chiếc, cả hai đều vượt qua bước kiểm tra, rồi cùng tạo đơn hàng. Kết quả là hệ thống bán nhiều hơn số hàng thực có.

Vấn đề nằm ở khoảng thời gian giữa lúc kiểm tra và lúc ghi dữ liệu. Một điều kiện đúng tại thời điểm đọc có thể không còn đúng khi transaction khác thay đổi dữ liệu. Đây là dạng **race condition** thường gặp trong xử lý đồng thời. Muốn bảo vệ bất biến dữ liệu, cần đặt việc kiểm tra và cập nhật trong một thao tác nguyên tử, dùng khóa phù hợp hoặc để cơ sở dữ liệu thực thi ràng buộc.

Trong phạm vi **DATABASE_DATA_MODELING**, bài học giải thích cách kiểm tra trước khi ghi, nhận diện tranh chấp, chọn transaction và cơ chế đồng bộ, đồng thời thiết kế constraint để bảo vệ dữ liệu ngay cả khi nhiều ứng dụng cùng ghi.

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích vì sao kiểm tra ở ứng dụng trước khi ghi không đủ để bảo đảm bất biến khi có nhiều transaction.
- Nhận diện race condition và lỗi TOCTOU (time-of-check to time-of-use).
- Chuyển điều kiện kiểm tra đơn giản thành câu lệnh cập nhật nguyên tử.
- Chọn giữa constraint, optimistic locking, pessimistic locking và mức cô lập transaction.
- Xử lý giới hạn tồn kho, số chỗ, số dư và các quy tắc phụ thuộc nhiều hàng.
- Thiết kế retry, idempotency và kiểm thử đồng thời có thể tái hiện.

## 1. Bất biến và thời điểm kiểm tra

**Bất biến (invariant)** là điều kiện phải luôn đúng đối với trạng thái dữ liệu mà hệ thống quản lý. Một số ví dụ:

- Số lượng tồn kho không được âm.
- Số dư tài khoản không được thấp hơn mức cho phép.
- Mỗi mã đơn hàng phải duy nhất.
- Một đăng ký phải tham chiếu đến sinh viên và lớp học phần tồn tại.
- Số người đăng ký đang hoạt động không vượt quá sức chứa lớp.
- Tổng tiền của giao dịch phải phù hợp với các dòng hàng và quy tắc tính tiền.

Kiểm tra trước khi ghi là bước xác minh dữ liệu hoặc trạng thái hiện tại đáp ứng điều kiện nghiệp vụ. Tuy nhiên, cần phân biệt hai loại kiểm tra:

- **Kiểm tra đầu vào:** dữ liệu có đúng định dạng và miền giá trị không, ví dụ số lượng là số nguyên dương.
- **Kiểm tra trạng thái dùng chung:** tài nguyên hoặc trạng thái trong database có còn đáp ứng điều kiện không, ví dụ tồn kho còn đủ để bán hay lớp còn chỗ.

Kiểm tra đầu vào thường có thể thực hiện sớm ở ứng dụng để phản hồi nhanh. Kiểm tra trạng thái dùng chung phải được gắn với thao tác ghi bằng cơ chế đồng bộ phù hợp, vì transaction khác có thể thay đổi trạng thái đó.

### 1.1. TOCTOU: kiểm tra đúng nhưng sử dụng sai thời điểm

TOCTOU là viết tắt của *time of check to time of use*: khoảng thời gian từ lúc kiểm tra một điều kiện đến lúc sử dụng kết quả kiểm tra. Nếu trạng thái thay đổi trong khoảng đó, quyết định dựa trên kết quả cũ có thể sai.

Ví dụ tồn kho đang có một sản phẩm:

| Thời điểm | Transaction A | Transaction B |
|---|---|---|
| T1 | Đọc `available = 1` | |
| T2 | | Đọc `available = 1` |
| T3 | Kiểm tra đủ hàng: đúng | |
| T4 | | Kiểm tra đủ hàng: đúng |
| T5 | Tạo đơn hàng | |
| T6 | | Tạo đơn hàng |
| T7 | Cả hai đơn cùng được xác nhận | |

Hai transaction đều kiểm tra dựa trên cùng một trạng thái cũ. Nếu mỗi transaction chỉ đọc rồi ghi một cách riêng rẽ, hệ thống có thể xác nhận hai đơn cho một sản phẩm.

### 1.2. Race condition không chỉ là hai lần ghi cùng một hàng

Tranh chấp có thể xảy ra khi:

- Hai transaction cập nhật cùng một hàng.
- Hai transaction cùng kiểm tra một điều kiện tổng hợp rồi ghi vào các hàng khác nhau.
- Một transaction đọc một tập hàng trong khi transaction khác thêm hoặc xóa hàng làm thay đổi kết quả truy vấn.
- Một yêu cầu được gửi lại sau timeout dù lần đầu đã commit.
- Nhiều service cùng ghi vào một bảng hoặc cùng quản lý một tài nguyên nghiệp vụ.

Vì vậy, chỉ nhìn từng câu `INSERT` hoặc `UPDATE` riêng lẻ chưa đủ. Cần xem toàn bộ thao tác nghiệp vụ và các transaction có thể chạy xen kẽ.

## 2. Vì sao `SELECT` rồi mới `UPDATE` có thể sai?

Giả sử bảng tồn kho:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
```

Một cách làm dễ mắc lỗi là:

```sql
SELECT available
FROM inventory
WHERE product_id = 101;

-- Ứng dụng kiểm tra available >= requested_quantity.

UPDATE inventory
SET available = $1 - 1
WHERE product_id = 101;
```

Ở đây `$1` là giá trị `available` mà ứng dụng đã đọc trước đó. Nếu cả hai transaction cùng đọc `1`, cả hai có thể ghi `0` rồi cùng tạo đơn; constraint không âm vẫn đúng nhưng hệ thống đã xác nhận hai đơn cho một chiếc. Nếu dùng phép trừ trực tiếp trên giá trị hiện tại mà không có điều kiện đủ hàng, một transaction có thể làm số lượng âm và bị `CHECK` từ chối.

`CHECK (available >= 0)` ngăn số tồn kho âm, nhưng câu `UPDATE` không có điều kiện `available >= 1` gắn với phép trừ. Quan trọng hơn, logic kiểm tra và logic thay đổi chưa được kết hợp thành một quyết định nguyên tử rõ ràng.

Không nên dựa vào việc “đọc ngay trước khi ghi” để loại bỏ race condition. Khoảng thời gian đó vẫn tồn tại, và transaction khác có thể chen vào.

## 3. Cập nhật nguyên tử bằng điều kiện trong câu lệnh ghi

Với điều kiện đơn giản trên cùng một hàng, cách tốt thường là đưa điều kiện vào chính câu `UPDATE`. Database đánh giá điều kiện và thực hiện thay đổi như một thao tác nguyên tử đối với hàng được cập nhật.

### 3.1. Trừ tồn kho có điều kiện

```sql
UPDATE inventory
SET available = available - $1
WHERE product_id = $2
  AND $1 > 0
  AND available >= $1
RETURNING available;
```

Ứng dụng truyền số lượng cần mua vào `$1`, mã sản phẩm vào `$2`:

- Nếu trả về một hàng, thao tác đã trừ tồn kho thành công.
- Nếu không trả về hàng nào, sản phẩm không tồn tại, số lượng đầu vào không hợp lệ hoặc tồn kho không đủ. Ứng dụng có thể truy vấn thêm để phân biệt nguyên nhân nếu cần thông báo chi tiết.

Điểm quan trọng là điều kiện `available >= $1` được kiểm tra cùng lúc với phép trừ. Nếu hai transaction cùng tranh một chiếc, một transaction cập nhật trước; transaction còn lại sẽ đánh giá lại điều kiện trên trạng thái mới và không thể trừ tiếp xuống số âm.

### 3.2. Chuyển số dư có điều kiện

Với tài khoản, có thể dùng câu lệnh tương tự:

```sql
UPDATE account
SET balance = balance - $1
WHERE account_id = $2
  AND $1 > 0
  AND balance >= $1
RETURNING balance;
```

Điều kiện bảo đảm số dư không bị trừ quá mức trong thao tác cập nhật. Bảng vẫn nên có constraint:

```sql
ALTER TABLE account
    ADD CONSTRAINT account_balance_nonnegative
    CHECK (balance >= 0);
```

Điều kiện trong `UPDATE` giúp xử lý nghiệp vụ và trả kết quả thành công/thất bại; `CHECK` là hàng rào cuối cùng chống ghi dữ liệu vi phạm bất biến từ các đường ghi khác.

### 3.3. Tạo đơn hàng trong cùng transaction

Trừ tồn kho và tạo đơn hàng là một nghiệp vụ gồm nhiều thay đổi. Nếu trừ kho thành công nhưng insert đơn hàng thất bại, dữ liệu không được để ở trạng thái nửa chừng. Hãy dùng một transaction:

```sql
BEGIN;

UPDATE inventory
SET available = available - $1
WHERE product_id = $2
  AND $1 > 0
  AND available >= $1
RETURNING available;

-- Ứng dụng phải xác nhận UPDATE trả về đúng một hàng.
-- Nếu không, ROLLBACK và trả lỗi hết hàng/đầu vào không hợp lệ.

INSERT INTO sales_order (order_id, customer_id, status)
VALUES ($3, $4, 'CONFIRMED');

INSERT INTO order_line (order_id, line_no, product_id, quantity)
VALUES ($3, 1, $2, $1);

COMMIT;
```

Đoạn SQL minh họa luồng điều khiển: ứng dụng phải kiểm tra số hàng được `UPDATE ... RETURNING` trả về trước khi tiếp tục; nếu không có hàng, transaction phải rollback. Với đơn có nhiều sản phẩm, cần trừ tồn cho từng sản phẩm trong cùng transaction và rollback toàn bộ nếu bất kỳ dòng nào không đủ hàng.

Transaction bảo đảm các thay đổi được commit cùng nhau hoặc rollback cùng nhau. Nó không tự động biến mọi kiểm tra trước đó thành an toàn; điều kiện phải được đặt đúng chỗ và các hàng liên quan phải được khóa/cập nhật theo chiến lược nhất quán.

## 4. Constraint là hàng rào bảo vệ dữ liệu

Kiểm tra ở ứng dụng giúp phản hồi dễ hiểu, nhưng dữ liệu thường có nhiều đường ghi: API, batch job, import, admin tool, consumer message hoặc tác vụ sửa dữ liệu. Constraint ở database giúp bảo vệ bất biến bất kể đường ghi nào được sử dụng.

### 4.1. Các constraint thường dùng

| Constraint | Bất biến được bảo vệ | Ví dụ |
|---|---|---|
| `NOT NULL` | Thuộc tính bắt buộc phải có giá trị | `customer_id NOT NULL` |
| `CHECK` | Điều kiện trên các cột của một hàng | `quantity > 0`, `balance >= 0` |
| `UNIQUE` | Không có giá trị/tổ hợp bị trùng theo quy tắc | `UNIQUE (tenant_id, external_code)` |
| `PRIMARY KEY` | Mỗi hàng có định danh duy nhất và không null | `PRIMARY KEY (order_id, line_no)` |
| `FOREIGN KEY` | Tham chiếu đến hàng được phép tồn tại | `customer_id REFERENCES customer(customer_id)` |
| Exclusion constraint | Cấm các giá trị/range xung đột theo toán tử | Không cho hai lịch đặt phòng cùng phòng chồng thời gian |

### 4.2. Constraint và kiểm tra liên hàng

`CHECK` thông thường kiểm tra giá trị trong cùng một hàng. Không nên viết `CHECK` phụ thuộc vào tổng số hàng con hoặc truy vấn sang bảng khác để bảo vệ quy tắc nhiều hàng. PostgreSQL không bảo đảm loại `CHECK` liên bảng đó theo cách an toàn khi dữ liệu thay đổi đồng thời.

Ví dụ, quy tắc “một lớp có tối đa 30 sinh viên đang hoạt động” không thể được bảo vệ chỉ bằng `CHECK` trên từng hàng đăng ký. Cần một cơ chế đồng bộ ở cấp lớp, bộ đếm có kiểm soát, khóa hàng cha hoặc transaction ở mức cô lập phù hợp.

### 4.3. UNIQUE bảo vệ chống trùng dưới cạnh tranh

Nếu mỗi khách hàng chỉ được có một hồ sơ cho một nhà cung cấp ngoài, dùng constraint:

```sql
ALTER TABLE external_customer
    ADD CONSTRAINT one_external_customer_per_source
    UNIQUE (source_system, external_customer_id);
```

Hai transaction có thể cùng kiểm tra “chưa có mã này” và cùng định insert. `UNIQUE` khiến database chỉ cho phép một transaction thành công; transaction còn lại nhận lỗi unique violation. Kiểm tra trước bằng `SELECT` không thể thay thế constraint này.

Nếu muốn xử lý trường hợp đã tồn tại, có thể dùng `INSERT ... ON CONFLICT`:

```sql
INSERT INTO external_customer
    (source_system, external_customer_id, customer_name)
VALUES
    ($1, $2, $3)
ON CONFLICT (source_system, external_customer_id)
DO NOTHING;
```

`ON CONFLICT` giúp xử lý xung đột theo cách tường minh. Nếu cần cập nhật bản ghi đã có, dùng `DO UPDATE` nhưng phải xác định rõ trường nào được phép ghi đè và cách xử lý hai nguồn cập nhật đồng thời.

## 5. Pessimistic locking: khóa trước khi thay đổi

Pessimistic locking giả định tranh chấp có thể xảy ra và khóa hàng liên quan trước khi đọc/ghi. Transaction khác muốn cập nhật hoặc khóa cùng hàng sẽ phải chờ cho đến khi khóa được giải phóng.

### 5.1. SELECT FOR UPDATE

Ví dụ xử lý tồn kho theo cách khóa hàng:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = $1
FOR UPDATE;

-- Ứng dụng kiểm tra available >= requested_quantity.

UPDATE inventory
SET available = available - $2
WHERE product_id = $1
  AND $2 > 0
  AND available >= $2;

-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.

COMMIT;
```

`FOR UPDATE` khóa hàng tồn kho đã tìm thấy cho đến khi transaction kết thúc. Transaction khác muốn cập nhật hoặc khóa hàng đó phải chờ. Sau khi có khóa, transaction đọc trạng thái mới nhất phù hợp với hành vi của mức cô lập đang dùng và có thể thực hiện kiểm tra cùng thay đổi.

### 5.2. Khi nào dùng khóa bi quan?

Phù hợp khi:

- Xung đột thường xuyên và chi phí retry cao.
- Nghiệp vụ cần đọc nhiều trường rồi quyết định cập nhật.
- Cần khóa một hàng cha làm điểm đồng bộ cho nhiều hàng con.
- Transaction ngắn, có thể hoàn tất nhanh trong khi giữ khóa.

Hạn chế:

- Transaction khác phải chờ, giảm thông lượng khi nhiều yêu cầu tranh cùng tài nguyên.
- Giữ khóa lâu có thể gây timeout và làm hệ thống chậm dây chuyền.
- Khóa nhiều hàng theo thứ tự khác nhau có thể tạo deadlock.
- `SELECT ... FOR UPDATE` chỉ khóa các hàng tìm thấy; nó không tự khóa một hàng chưa tồn tại hoặc mọi hàng tương lai thỏa điều kiện truy vấn.

Không gọi API ngoài, gửi email, chờ người dùng hoặc thực hiện tác vụ chậm trong khi đang giữ khóa database. Hãy giữ transaction ngắn và commit/rollback sớm.

### 5.3. Khóa hàng cha để bảo vệ điều kiện trên tập hàng con

Giả sử một lớp học phần có giới hạn chỗ. Nếu chỉ đếm số đăng ký hiện tại rồi insert, hai transaction có thể cùng thấy còn một chỗ.

Một cách là khóa hàng `course_offering` làm điểm đồng bộ:

```sql
BEGIN;

SELECT capacity
FROM course_offering
WHERE offering_id = $1
FOR UPDATE;

SELECT COUNT(*)
FROM enrollment
WHERE offering_id = $1
  AND status IN ('PENDING', 'CONFIRMED');

-- Ứng dụng chỉ INSERT nếu số đang hoạt động < capacity.

INSERT INTO enrollment (student_id, offering_id, status)
VALUES ($2, $1, 'PENDING');

COMMIT;
```

Mọi đường ghi đăng ký cho cùng lớp phải tuân thủ cùng giao thức khóa hàng cha. Nếu một service bỏ qua khóa này, bảo đảm sẽ không còn đầy đủ. Cần transaction và kiểm tra điều kiện sau khi đã lấy khóa.

### 5.4. Bộ đếm sức chứa có điều kiện

Với workload lớn, có thể duy trì `enrolled_count` trên hàng lớp và cập nhật nguyên tử:

```sql
UPDATE course_offering
SET enrolled_count = enrolled_count + 1
WHERE offering_id = $1
  AND enrolled_count < capacity
RETURNING enrolled_count;
```

Nếu không trả về hàng, lớp đã đầy hoặc không tồn tại. Thao tác tăng bộ đếm và insert Enrollment phải ở cùng transaction; nếu insert thất bại, rollback cả bộ đếm. Khi hủy đăng ký, giảm bộ đếm trong cùng transaction. Bảng nên có constraint `CHECK (enrolled_count >= 0 AND enrolled_count <= capacity)`.

Bộ đếm là dữ liệu dẫn xuất, cần có quy trình đối soát với số đăng ký thực tế để phát hiện sai lệch do lỗi cũ hoặc đường ghi không tuân thủ giao thức.

## 6. Optimistic locking: phát hiện xung đột khi ghi

Optimistic locking không khóa hàng trong suốt quá trình đọc và xử lý. Thay vào đó, hệ thống ghi kèm một phiên bản (version) hoặc giá trị đã đọc. Nếu hàng đã bị transaction khác thay đổi, thao tác cập nhật không khớp và được xem là xung đột.

### 6.1. Cột version

```sql
CREATE TABLE product_price (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(14, 2) NOT NULL CHECK (price >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

Ứng dụng đọc `price` và `version`, tính giá mới, sau đó cập nhật:

```sql
UPDATE product_price
SET price = $1,
    version = version + 1
WHERE product_id = $2
  AND version = $3
RETURNING price, version;
```

Nếu trả về một hàng, cập nhật thành công. Nếu không có hàng, phiên bản đã thay đổi hoặc sản phẩm không còn tồn tại. Ứng dụng có thể đọc lại, tính toán lại và thử lại theo chính sách, hoặc báo xung đột để người dùng xác nhận.

### 6.2. Khi nào dùng optimistic locking?

Phù hợp khi:

- Xung đột không thường xuyên.
- Có nhiều thao tác đọc và ít cập nhật cạnh tranh.
- Muốn tránh giữ khóa trong thời gian ứng dụng xử lý.
- Có thể phát hiện và xử lý trường hợp dữ liệu đã thay đổi.

Không phù hợp nếu xung đột xảy ra liên tục và retry làm tăng tải. Với quy tắc liên quan nhiều hàng, một cột version trên một hàng đơn lẻ cũng không đủ nếu các transaction có thể sửa những hàng khác nhau nhưng cùng vi phạm một bất biến chung. Khi đó cần điểm đồng bộ hoặc mức cô lập mạnh hơn.

## 7. Transaction isolation và các hiện tượng đồng thời

Transaction isolation quy định transaction có thể quan sát thay đổi của transaction khác như thế nào. Mức cô lập cao hơn có thể ngăn thêm các bất thường, nhưng thường làm tăng chi phí chờ hoặc khả năng transaction bị hủy và phải thử lại.

### 7.1. Các hiện tượng cần hiểu

- **Dirty read:** đọc dữ liệu chưa commit của transaction khác.
- **Non-repeatable read:** cùng một hàng được đọc hai lần nhưng giá trị khác do transaction khác commit cập nhật.
- **Phantom read:** cùng một điều kiện truy vấn nhưng lần đọc sau có thêm hoặc mất hàng do transaction khác commit insert/delete.
- **Lost update:** hai transaction cập nhật dựa trên cùng giá trị cũ và một thay đổi ghi đè thay đổi còn lại.
- **Write skew:** hai transaction đọc cùng một tập trạng thái, sau đó cập nhật các hàng khác nhau nhưng kết quả kết hợp vi phạm bất biến.

### 7.2. Mức cô lập phổ biến

| Mức cô lập | Đặc điểm khái quát | Lưu ý khi thiết kế |
|---|---|---|
| Read Uncommitted | Cho phép đọc dữ liệu chưa commit theo định nghĩa SQL; một số DBMS triển khai tương đương mức cao hơn | Tránh dùng nếu không chấp nhận dirty read |
| Read Committed | Mỗi câu lệnh đọc thấy dữ liệu đã commit tại thời điểm bắt đầu câu lệnh | Phổ biến; một `SELECT` trước `UPDATE` vẫn có thể bị race |
| Repeatable Read | Giữ snapshot ổn định trong transaction theo triển khai DBMS | Hạn chế non-repeatable read; vẫn cần hiểu write skew và lỗi serialization của DBMS |
| Serializable | Kết quả các transaction thành công tương đương một thứ tự chạy tuần tự | Có thể hủy transaction khi phát hiện xung đột; ứng dụng phải retry toàn bộ transaction |

Tên mức cô lập giống nhau không bảo đảm mọi DBMS có hành vi triển khai hoàn toàn giống nhau. Hãy đọc tài liệu của hệ quản trị đang dùng và kiểm thử đúng workload.

Với PostgreSQL, `READ UNCOMMITTED` được xử lý như `READ COMMITTED`. `REPEATABLE READ` dùng snapshot ổn định và ngăn phantom read trong PostgreSQL, nhưng vẫn có thể xảy ra một số serialization anomaly như write skew. `SERIALIZABLE` dùng Serializable Snapshot Isolation và có thể hủy một transaction với lỗi serialization để ngăn các anomaly đó.

### 7.3. Ví dụ write skew

Một phòng trực cần ít nhất một bác sĩ đang trực. Có hai bác sĩ A và B, cả hai đều đang trực. Hai transaction đồng thời:

1. A đọc thấy có hai bác sĩ đang trực.
2. B cũng đọc thấy có hai bác sĩ đang trực.
3. Transaction A tắt trạng thái trực của A.
4. Transaction B tắt trạng thái trực của B.
5. Mỗi transaction cập nhật một hàng khác nhau và có thể cùng commit dưới mức cô lập không phát hiện write skew.

Kết quả cuối cùng không còn ai trực, dù mỗi transaction riêng lẻ đều thấy điều kiện ban đầu được đáp ứng. Cần khóa một hàng đại diện cho lịch trực, dùng mô hình phân bổ có đồng bộ hoặc dùng `SERIALIZABLE` và xử lý retry. Chỉ khóa hàng bác sĩ đang được cập nhật không đủ để bảo vệ bất biến trên toàn bộ nhóm.

### 7.4. Serializable yêu cầu retry

Ở mức `SERIALIZABLE`, database có thể hủy một transaction để ngăn kết quả không thể tương đương với thứ tự tuần tự. Ứng dụng phải nhận diện lỗi serialization và thử lại **toàn bộ transaction** với dữ liệu mới. Không chỉ chạy lại câu lệnh cuối vì các quyết định trước đó có thể đã dựa trên snapshot cũ.

Retry cần giới hạn số lần, có backoff phù hợp và chỉ áp dụng cho thao tác có thể chạy lại an toàn. Nếu transaction đã gây side effect bên ngoài trước khi bị hủy, việc retry có thể gửi trùng thông báo hoặc thực hiện hành động hai lần.

## 8. Chọn cơ chế phù hợp với loại bất biến

Không có một kỹ thuật duy nhất giải quyết mọi tranh chấp. Chọn theo phạm vi điều kiện và dữ liệu bị thay đổi.

| Tình huống | Cơ chế thường phù hợp | Lý do |
|---|---|---|
| Số lượng tồn kho không được âm | Conditional `UPDATE` + `CHECK` | Điều kiện và phép trừ được thực hiện nguyên tử; constraint bảo vệ thêm |
| Mã ngoài phải duy nhất | `UNIQUE` constraint + `ON CONFLICT` | Database phân xử an toàn giữa các insert đồng thời |
| Cập nhật hồ sơ hiếm khi xung đột | Optimistic locking với `version` | Không cần giữ khóa trong lúc người dùng chỉnh sửa |
| Cập nhật một hàng thường xuyên tranh chấp | `SELECT FOR UPDATE` hoặc conditional update | Đồng bộ các transaction cùng sửa hàng |
| Giới hạn số đăng ký của một lớp | Khóa hàng cha, bộ đếm nguyên tử hoặc Serializable | Bất biến phụ thuộc nhiều hàng |
| Lịch đặt phòng không được chồng thời gian | Exclusion constraint hoặc khóa/transaction theo tài nguyên | Cần bảo vệ khoảng thời gian, không chỉ một hàng |
| Chuyển tiền giữa hai tài khoản | Một transaction cập nhật cả hai tài khoản, khóa theo thứ tự ổn định và constraint số dư | Hai phía phải cùng thành công hoặc cùng thất bại |

### 8.1. Chuyển tiền giữa hai tài khoản

Chuyển tiền là ví dụ điển hình của một nghiệp vụ nhiều hàng. Cần bảo đảm tài khoản nguồn đủ số dư và cả hai cập nhật cùng commit.

```sql
BEGIN;

-- Khóa theo thứ tự account_id để giảm nguy cơ deadlock.
SELECT account_id, balance
FROM account
WHERE account_id IN ($1, $2)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng xác nhận cả hai tài khoản tồn tại, amount > 0,
-- và tài khoản nguồn có đủ số dư.

UPDATE account
SET balance = balance - $3
WHERE account_id = $1
  AND balance >= $3;

-- Ứng dụng phải xác nhận đúng một hàng được cập nhật.

UPDATE account
SET balance = balance + $3
WHERE account_id = $2;

-- Ghi ledger/debit/credit trong cùng transaction nếu mô hình yêu cầu.

COMMIT;
```

Nếu bất kỳ bước nào không đạt điều kiện, rollback toàn bộ. Cần kiểm tra `$1 <> $2` hoặc định nghĩa rõ xử lý chuyển vào chính tài khoản đó. Trong hệ thống tài chính, thường nên lưu ledger giao dịch bất biến và đối soát tổng số dư; cập nhật số dư là một phần của quy trình ghi sổ.

## 9. Deadlock và thứ tự khóa

Deadlock xảy ra khi các transaction chờ khóa của nhau theo vòng tròn.

Ví dụ:

- Transaction A khóa tài khoản 10 rồi chờ tài khoản 20.
- Transaction B khóa tài khoản 20 rồi chờ tài khoản 10.
- Cả hai không thể tiếp tục nếu không có cơ chế phát hiện và hủy một transaction.

Để giảm nguy cơ:

1. Khóa nhiều hàng theo cùng một thứ tự ổn định, ví dụ tăng dần theo khóa chính.
2. Giữ transaction ngắn và chỉ khóa những hàng cần thiết.
3. Tránh gọi dịch vụ bên ngoài trong transaction.
4. Tạo chỉ mục phù hợp để truy vấn tìm hàng khóa không quét phạm vi quá lớn.
5. Nhận diện lỗi deadlock và retry toàn bộ transaction với giới hạn.

Không thể loại bỏ mọi deadlock trong hệ thống có nhiều luồng cập nhật. Ứng dụng cần coi deadlock là lỗi đồng thời có thể phục hồi, không phải lý do để retry vô hạn.

## 10. Idempotency khi yêu cầu bị gửi lại

Không phải mọi lần chạy lặp đều là race condition, nhưng retry từ client, gateway hoặc message broker có thể tạo cùng một nghiệp vụ nhiều lần. Ví dụ client gửi yêu cầu thanh toán, server đã commit nhưng phản hồi bị mất; client gửi lại và hệ thống trừ tiền lần thứ hai.

**Idempotency** giúp một yêu cầu logic được xử lý tối đa một lần theo khóa idempotency đã định nghĩa, dù cùng request được gửi nhiều lần.

Ví dụ cấu trúc:

```sql
CREATE TABLE idempotency_request (
    client_id VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (client_id, idempotency_key)
);
```

Khi nhận yêu cầu:

1. Tạo hoặc chiếm bản ghi theo `(client_id, idempotency_key)` trong transaction.
2. Nếu khóa đã tồn tại và request hash giống nhau, trả kết quả đã lưu hoặc chờ xử lý đang diễn ra theo chính sách.
3. Nếu khóa đã tồn tại nhưng nội dung request khác, từ chối vì cùng idempotency key được dùng cho hai yêu cầu khác nhau.
4. Nếu là yêu cầu mới, thực hiện nghiệp vụ và lưu kết quả trong cùng transaction nếu có thể.

Idempotency không thay thế constraint và transaction. Nó giải quyết việc nhận lặp cùng một yêu cầu logic; constraint vẫn bảo vệ bất biến dữ liệu và transaction bảo vệ tính nguyên tử.

## 11. Kiểm thử tranh chấp đồng thời

Kiểm thử đơn luồng thường không phát hiện được race condition. Cần tạo nhiều transaction chạy đồng thời với điểm bắt đầu gần nhau và kiểm tra bất biến sau khi tất cả kết thúc.

### 11.1. Kịch bản tồn kho

Thiết lập:

- Một sản phẩm có `available = 1`.
- Hai client cùng yêu cầu mua một sản phẩm.
- Hai transaction bắt đầu gần như đồng thời.

Kết quả mong đợi:

- Chỉ một yêu cầu trừ kho và tạo đơn thành công.
- Yêu cầu còn lại nhận kết quả hết hàng hoặc xung đột có thể xử lý.
- `available` cuối cùng bằng 0, không âm.
- Không có hai đơn hàng được xác nhận cho cùng một đơn vị tồn kho.

### 11.2. Kịch bản sức chứa

Thiết lập lớp còn một chỗ và cho nhiều client cùng đăng ký. Sau khi chạy:

- Số đăng ký đang hoạt động không vượt `capacity`.
- Bộ đếm (nếu có) bằng số bản ghi đăng ký theo quy tắc tính.
- Không có client nào nhận xác nhận nếu transaction của nó đã rollback.

### 11.3. Kịch bản optimistic locking

Hai client đọc cùng `version = 5`. Client A cập nhật thành công lên version 6. Client B gửi cập nhật với version 5 và phải nhận kết quả không có hàng được cập nhật. B không được âm thầm ghi đè dữ liệu A.

### 11.4. Kịch bản idempotency

Gửi đồng thời nhiều request cùng idempotency key và cùng nội dung. Kết quả phải chỉ có một giao dịch nghiệp vụ; mọi request lặp nhận cùng kết quả theo contract. Gửi cùng key nhưng payload khác phải bị từ chối.

### 11.5. Cách tổ chức test

- Dùng hai hoặc nhiều connection database độc lập.
- Dùng barrier/latch để điều khiển các transaction cùng đi tới bước kiểm tra trước khi tiếp tục.
- Không chỉ dùng mock repository; cần kiểm thử trên DBMS thật vì locking và isolation phụ thuộc hệ quản trị.
- Kiểm tra cả kết quả trả về, dữ liệu cuối cùng và log lỗi.
- Lặp lại kịch bản đủ nhiều lần hoặc dùng test có điều khiển để tránh kết luận sai từ một lần chạy.
- Sau test, đối soát các invariant bằng truy vấn độc lập.

## 12. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| `SELECT` kiểm tra rồi `UPDATE` không điều kiện | Hai transaction cùng dùng kết quả đọc cũ | Dùng conditional update, lock hoặc isolation phù hợp |
| Chỉ validate ở ứng dụng | Batch job hoặc service khác có thể ghi dữ liệu sai | Đặt constraint ở database cho bất biến có thể thực thi |
| Nghĩ transaction mặc định ngăn mọi race | Một số anomaly vẫn xảy ra tùy mức cô lập và câu lệnh | Chọn mức cô lập và cơ chế đồng bộ theo bất biến |
| Dùng `CHECK` cho tổng nhiều hàng | Constraint không bảo vệ điều kiện liên hàng một cách an toàn | Dùng unique/exclusion, khóa hàng cha, counter hoặc Serializable |
| Dùng `SELECT FOR UPDATE` nhưng không khóa hàng cha | Transaction khác có thể insert hàng con mới làm thay đổi tổng | Khóa điểm đồng bộ chung hoặc dùng cơ chế bảo vệ phạm vi |
| Giữ khóa trong khi gọi API ngoài | Tăng thời gian chờ, deadlock và giảm thông lượng | Tách side effect khỏi transaction, dùng outbox khi phù hợp |
| Retry mọi lỗi | Có thể lặp side effect hoặc che giấu lỗi nghiệp vụ | Chỉ retry lỗi đồng thời có thể phục hồi; giới hạn số lần và bảo đảm idempotency |
| Không khóa theo thứ tự ổn định | Tăng nguy cơ deadlock | Chuẩn hóa thứ tự khóa và xử lý deadlock |
| Có surrogate key nhưng thiếu UNIQUE nghiệp vụ | Cho phép dữ liệu trùng logic | Bổ sung candidate key/unique constraint |

## 13. Quy trình thiết kế thao tác ghi an toàn

1. **Viết bất biến bằng câu rõ ràng:** ví dụ “tồn kho khả dụng không âm” hoặc “mỗi lớp không vượt sức chứa”.
2. **Xác định phạm vi dữ liệu:** một hàng, nhiều hàng, một tập theo điều kiện hay nhiều bảng.
3. **Chọn nơi bảo vệ:** `NOT NULL`, `CHECK`, `UNIQUE`, FK, exclusion constraint, transaction hoặc logic miền.
4. **Xác định điểm tranh chấp:** các transaction nào có thể cùng đọc/ghi tài nguyên hoặc cùng làm thay đổi điều kiện.
5. **Chọn cơ chế đồng bộ:** conditional update, optimistic version, pessimistic row lock, khóa hàng cha hoặc Serializable.
6. **Đóng gói thay đổi trong transaction:** tất cả thay đổi thuộc một nghiệp vụ phải commit/rollback nhất quán.
7. **Xác định lỗi và retry:** phân biệt vi phạm nghiệp vụ, xung đột version, deadlock, serialization failure và lỗi hệ thống.
8. **Bảo vệ request lặp:** dùng idempotency key cho thao tác có side effect hoặc có thể được gửi lại.
9. **Kiểm thử đồng thời:** tái hiện xen kẽ transaction, xác minh trạng thái cuối và đối soát invariant.
10. **Theo dõi vận hành:** quan sát số lần conflict, retry, deadlock, lock wait, timeout và constraint violation.

## 14. Checklist kiểm chứng

- [ ] Bất biến được viết rõ, có phạm vi và thời điểm áp dụng.
- [ ] Kiểm tra đầu vào được phân biệt với kiểm tra trạng thái dùng chung.
- [ ] Không dựa vào kết quả `SELECT` cũ để quyết định `UPDATE` không điều kiện.
- [ ] Điều kiện đơn giản được gắn vào conditional update khi phù hợp.
- [ ] Constraint database bảo vệ bất biến ở mọi đường ghi có thể.
- [ ] Quy tắc liên hàng có điểm đồng bộ rõ ràng.
- [ ] Transaction bao trọn các thay đổi cần cùng thành công hoặc cùng thất bại.
- [ ] Chiến lược khóa và thứ tự lấy khóa được xác định.
- [ ] Optimistic locking kiểm tra version và xử lý conflict tường minh.
- [ ] Mức cô lập phù hợp với anomaly cần ngăn và đặc tính DBMS.
- [ ] Retry chỉ áp dụng cho lỗi có thể phục hồi, có giới hạn và chạy lại toàn transaction.
- [ ] Request lặp được bảo vệ bằng idempotency khi cần.
- [ ] Có kiểm thử với nhiều connection và đối soát bất biến sau khi chạy.

## Tóm tắt

Kiểm tra trước khi ghi là cần thiết nhưng không đủ nếu trạng thái có thể thay đổi đồng thời. Với điều kiện trên một hàng, conditional update thường kết hợp kiểm tra và thay đổi trong một thao tác nguyên tử. Constraint như `CHECK`, `UNIQUE` và khóa ngoại bảo vệ dữ liệu ở database. Với nghiệp vụ phức tạp hơn, cần transaction cùng optimistic locking, pessimistic locking hoặc mức cô lập phù hợp.

Các bất biến trên nhiều hàng như sức chứa lớp hoặc lịch trực cần một điểm đồng bộ chung; chỉ khóa hàng đang sửa có thể chưa đủ. Hệ thống cũng cần xử lý deadlock, serialization failure và request gửi lại bằng retry có kiểm soát và idempotency. Chất lượng thiết kế được xác nhận bằng kiểm thử đồng thời trên DBMS thật và đối soát trạng thái cuối.

## Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Invariant | Điều kiện phải luôn đúng đối với trạng thái dữ liệu |
| TOCTOU | Khoảng cách giữa thời điểm kiểm tra và thời điểm sử dụng kết quả kiểm tra |
| Race Condition | Kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác đồng thời |
| Atomic Update | Cập nhật mà điều kiện và thay đổi được database xử lý như một thao tác nguyên tử |
| Transaction | Nhóm thao tác commit hoặc rollback như một đơn vị |
| Pessimistic Locking | Khóa tài nguyên trước khi đọc/ghi để ngăn transaction khác thay đổi đồng thời |
| Optimistic Locking | Dùng version hoặc giá trị đã đọc để phát hiện xung đột khi cập nhật |
| Isolation Level | Mức cô lập quy định transaction quan sát thay đổi của transaction khác |
| Write Skew | Các transaction cập nhật những hàng khác nhau nhưng kết hợp lại vi phạm một bất biến |
| Deadlock | Các transaction chờ khóa của nhau theo vòng tròn |
| Idempotency | Xử lý lặp cùng một yêu cầu logic mà không lặp tác động nghiệp vụ |
| Serialization Failure | Lỗi khi DBMS hủy transaction để bảo vệ tính tương đương với thực thi tuần tự |
