# Đọc rồi cập nhật mà không bảo vệ dữ liệu đã đọc

Một lỗi đồng thời rất phổ biến xuất hiện khi ứng dụng đọc dữ liệu, đưa ra quyết định dựa trên giá trị vừa đọc, rồi cập nhật sau đó mà không bảo vệ mối liên hệ giữa hai bước. Trong khoảng thời gian ở giữa, transaction khác có thể thay đổi dữ liệu. Ứng dụng vẫn tiếp tục dùng kết quả đọc cũ và có thể ghi đè thay đổi mới, thực hiện một hành động không còn hợp lệ hoặc phá vỡ bất biến nghiệp vụ.

Mẫu sai này thường được gọi là **read-then-write**, **check-then-act** hoặc **stale-read update**. Bản thân câu SELECT không sai; vấn đề là quyết định ở bước ghi không kiểm tra dữ liệu vẫn còn ở trạng thái mà ứng dụng đã đọc hay không.

Ví dụ, một kho có 5 sản phẩm. Hai request cùng đọc số lượng 5, mỗi request muốn bán 4 sản phẩm. Cả hai đều thấy đủ hàng. Nếu mỗi request ghi lại số lượng tính từ giá trị cũ, hệ thống có thể ghi nhận kết quả sai hoặc bán vượt tồn. Một transaction có thể đã commit sau khi request kia đọc nhưng trước khi request đó cập nhật.

Bài này giải thích khoảng đua giữa đọc và ghi, các dạng lỗi thường gặp, và cách bảo vệ dữ liệu đã đọc bằng câu lệnh cập nhật nguyên tử, version check, khóa bi quan, constraint hoặc mức cô lập phù hợp.

## 1. Mẫu sai: đọc, kiểm tra rồi cập nhật

Một đoạn code ứng dụng thường có dạng:

~~~java
ProductStock stock = repository.findByProductId(productId);

if (stock.getQuantity() >= requested) {
    stock.setQuantity(stock.getQuantity() - requested);
    repository.save(stock);
}
~~~

Khi chỉ có một request, code có vẻ đúng:

1. Đọc số lượng hiện tại.
2. Kiểm tra đủ hàng.
3. Trừ số lượng cần bán.
4. Lưu kết quả.

Nhưng khi hai request chạy đồng thời, cả hai có thể đọc cùng một giá trị trước khi bất kỳ request nào ghi.

Giả sử tồn kho ban đầu là 5, A và B đều muốn bán 4:

~~~text
Thời gian       Request A                    Request B
----------------------------------------------------------------
T1              SELECT quantity -> 5
T2                                           SELECT quantity -> 5
T3              kiểm tra 5 >= 4: đúng
T4                                           kiểm tra 5 >= 4: đúng
T5              tính quantity mới = 1
T6                                           tính quantity mới = 1
T7              UPDATE quantity = 1
T8              COMMIT
T9                                           UPDATE quantity = 1
T10                                          COMMIT
~~~

Trạng thái cuối là 1, trong khi hai đơn hàng đã bán tổng cộng 8 sản phẩm. Một lần trừ đã bị mất. Nếu hệ thống chỉ nhìn cột quantity, nó có thể không phát hiện đã nhận hai đơn hàng vượt tồn kho.

Đây là lost update kết hợp với check-then-act race. Vấn đề không được giải quyết chỉ bằng cách đặt SELECT và UPDATE trong một transaction ở mức cô lập mặc định.

## 2. Vì sao transaction không tự bảo vệ kết quả SELECT?

Transaction gom các câu lệnh vào một đơn vị commit/rollback. Nó không có nghĩa mọi dữ liệu đã đọc sẽ tự động bị khóa cho đến khi transaction kết thúc.

Ở nhiều DBMS, mức READ COMMITTED cho phép một transaction đọc một giá trị đã commit, sau đó transaction khác cập nhật và commit, rồi transaction đầu tiếp tục chạy. Nếu câu UPDATE của transaction đầu chỉ lọc theo ID và ghi giá trị tuyệt đối đã tính từ trước, nó có thể ghi đè dữ liệu mới.

~~~text
Transaction A                         Transaction B
BEGIN                                  BEGIN
SELECT quantity = 5
                                       SELECT quantity = 5
                                       UPDATE quantity = 1
                                       COMMIT
UPDATE quantity = 1
COMMIT
~~~

Transaction A vẫn có thể commit sau B vì câu UPDATE không nói rằng nó chỉ được phép ghi nếu quantity vẫn bằng 5 hoặc version vẫn bằng giá trị A đã đọc.

### SELECT thông thường và SELECT có khóa

SELECT thông thường thường đọc theo semantics isolation/MVCC của DBMS. Nó không nhất thiết giữ khóa ngăn transaction khác cập nhật hàng sau khi câu SELECT kết thúc.

Một locking read như SELECT ... FOR UPDATE có thể yêu cầu khóa hàng trong transaction để transaction khác không cập nhật tài nguyên đó cho đến khi khóa được giải phóng. Tuy nhiên, cú pháp và semantics khác nhau theo DBMS; khóa phải được lấy trước khi đưa ra quyết định và phải nằm trong cùng transaction với thao tác ghi.

### Autocommit làm cửa sổ đua dễ thấy hơn

Nếu mỗi câu lệnh chạy ở autocommit riêng, SELECT và UPDATE có thể là hai transaction hoàn toàn khác nhau:

~~~text
Transaction 1: SELECT quantity -> COMMIT
                  khoảng thời gian không được bảo vệ
Transaction 2: UPDATE quantity -> COMMIT
~~~

Tắt autocommit rồi bọc hai câu lệnh trong một transaction vẫn chưa đủ nếu isolation/locking không bảo vệ dữ liệu đã đọc. Cần chọn một cơ chế cụ thể phù hợp với bất biến.

## 3. Phân biệt các dạng lỗi

Read-then-update không bảo vệ dữ liệu đã đọc có thể dẫn đến nhiều hiện tượng:

| Hiện tượng | Mô tả | Ví dụ |
|---|---|---|
| Lost update | Ghi đè thay đổi của transaction khác | Hai người cùng sửa một hồ sơ; lần lưu sau ghi cả object cũ |
| Check-then-act race | Điều kiện đúng lúc đọc nhưng không còn đúng lúc ghi | Hai request cùng thấy còn hàng rồi cùng bán |
| Stale state overwrite | Ghi dữ liệu cũ lên trạng thái mới hơn | Form được mở lâu, người dùng lưu lại toàn bộ dữ liệu cũ |
| Duplicate creation | Cùng kiểm tra chưa có bản ghi rồi cùng INSERT | Hai request cùng tạo username/email |
| Invalid state transition | Quyết định chuyển trạng thái dựa trên trạng thái đã cũ | Hai worker cùng xử lý một đơn hàng PENDING |
| Write skew | Hai transaction đọc cùng invariant nhiều hàng rồi ghi hai hàng khác nhau | Hai bác sĩ cùng tắt trạng thái trực, khiến không còn ai trực |

Không phải mọi trường hợp đều cần cùng một cách sửa. Một hàng bị ghi đè có thể được bảo vệ bằng version hoặc atomic UPDATE; tính duy nhất thường cần unique constraint; invariant nhiều hàng có thể cần guard row hoặc SERIALIZABLE.

## 4. Cách sửa đầu tiên: đưa điều kiện vào chính câu UPDATE

Nếu quyết định có thể được biểu diễn bằng điều kiện trên hàng đang cập nhật, hãy kết hợp kiểm tra và thay đổi trong một câu DML nguyên tử.

Thay vì đọc quantity rồi tính giá trị tuyệt đối trong ứng dụng:

~~~sql
SELECT quantity
FROM product_stock
WHERE product_id = :product_id;

-- Ứng dụng kiểm tra và tính quantity mới.

UPDATE product_stock
SET quantity = :quantity_calculated_in_application
WHERE product_id = :product_id;
~~~

Hãy dùng:

~~~sql
UPDATE product_stock
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND :requested > 0
  AND quantity >= :requested;
~~~

DBMS kiểm tra điều kiện quantity hiện tại và trừ số lượng trong cùng thao tác cập nhật. Nếu hai request cạnh tranh trên cùng hàng, DBMS điều phối việc ghi; request chạy sau đánh giá điều kiện trên giá trị phù hợp với cơ chế cập nhật của DBMS.

### Diễn giải số hàng bị ảnh hưởng

Ứng dụng phải kiểm tra affected rows:

- **1 hàng:** cập nhật thành công, đã giữ chỗ/trừ hàng.
- **0 hàng:** sản phẩm không tồn tại, số lượng không đủ hoặc một điều kiện khác không còn đúng.

Nếu API cần phân biệt “không tìm thấy sản phẩm” và “hết hàng”, có thể thực hiện truy vấn bổ sung sau khi UPDATE không khớp. Nhưng quyết định cuối cùng về việc trừ tồn phải nằm trong câu UPDATE có điều kiện.

Không nên giả định mọi driver báo affected rows giống nhau trong mọi trường hợp, nhất là với câu UPDATE gán lại cùng giá trị hoặc các tùy chọn client. Với câu lệnh trên, giá trị quantity thay đổi khi requested dương, nhưng vẫn cần xác nhận semantics của driver đang dùng.

### Thêm CHECK constraint làm hàng rào cuối

~~~sql
ALTER TABLE product_stock
ADD CONSTRAINT ck_product_stock_nonnegative
CHECK (quantity >= 0);
~~~

CHECK bảo đảm không transaction nào commit quantity âm. Nó không thay thế điều kiện quantity >= requested trong UPDATE: nếu ứng dụng ghi sai một giá trị dương, constraint không biết đơn hàng nào đã được chấp nhận hoặc số lượng cần trừ là bao nhiêu.

## 5. Phép cộng/trừ tương đối khác với ghi giá trị tuyệt đối

Hai cách cập nhật dưới đây có ý nghĩa đồng thời khác nhau.

**Ghi giá trị tuyệt đối từ snapshot cũ:**

~~~sql
UPDATE account
SET balance = :balance_calculated_before
WHERE account_id = :id;
~~~

Giá trị mới được tính từ dữ liệu ứng dụng đã đọc trước đó. Nếu dữ liệu thay đổi giữa lúc đọc và lúc ghi, câu lệnh có thể ghi đè thay đổi đó.

**Cập nhật tương đối trên giá trị hiện tại:**

~~~sql
UPDATE account
SET balance = balance + :delta
WHERE account_id = :id;
~~~

DBMS áp dụng phép cộng vào giá trị đang có khi câu UPDATE được thực hiện. Với hai khoản cộng độc lập, cả hai có thể được giữ lại thay vì một phép gán tuyệt đối ghi đè phép kia.

Tuy vậy, cập nhật tương đối không tự bảo vệ mọi quy tắc. Nếu số dư không được âm, cần thêm điều kiện:

~~~sql
UPDATE account
SET balance = balance - :withdrawal
WHERE account_id = :id
  AND :withdrawal > 0
  AND balance >= :withdrawal;
~~~

Nếu một thao tác cần thay đổi nhiều hàng, ví dụ chuyển tiền từ A sang B, cả hai UPDATE phải nằm trong cùng transaction và ứng dụng phải kiểm tra số hàng bị ảnh hưởng của từng bước. Nếu bước thứ hai thất bại, rollback toàn bộ transaction.

## 6. Cách sửa bằng optimistic locking: kiểm tra version đã đọc

Khi ứng dụng cần đọc dữ liệu, tính toán ở tầng nghiệp vụ rồi mới lưu, optimistic locking thường phù hợp. Mỗi hàng có một cột version tăng sau mỗi cập nhật thành công.

Ví dụ bảng:

~~~sql
CREATE TABLE product (
    product_id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Ứng dụng đọc:

~~~sql
SELECT product_id, name, price, version
FROM product
WHERE product_id = :id;
~~~

Giả sử đọc được version 7. Khi lưu, phải dùng version đã đọc trong WHERE và tăng version trong cùng câu lệnh:

~~~sql
UPDATE product
SET name = :new_name,
    price = :new_price,
    version = version + 1
WHERE product_id = :id
  AND version = :expected_version;
~~~

Nếu một transaction khác đã cập nhật hàng và version thành 8, câu UPDATE với expected_version = 7 sẽ tác động 0 hàng. Ứng dụng biết dữ liệu đã thay đổi kể từ lần đọc và có thể trả conflict, tải lại rồi hợp nhất.

### Lịch hai phiên

Trạng thái đầu: product 10 có price 500000, version 7.

| Bước | Session A | Session B |
|---|---|---|
| 1 | Đọc price 500000, version 7 | |
| 2 | | Đọc price 500000, version 7 |
| 3 | Cập nhật price 520000, version 8; affected rows = 1 | |
| 4 | Commit | |
| 5 | | Cập nhật dựa trên version 7; affected rows = 0 |

Session B không được báo thành công. Nó cần quyết định đọc lại dữ liệu mới và áp dụng lại ý định nghiệp vụ hay trả lỗi xung đột cho người dùng.

### Version phải được mọi đường ghi cập nhật

Nếu ORM dùng @Version nhưng một batch job hoặc native SQL thay đổi hàng mà không tăng version, entity đang giữ version cũ vẫn có thể ghi đè dữ liệu mới. Mọi đường ghi có ý nghĩa nghiệp vụ phải tuân thủ hợp đồng version, kể cả:

- ORM-managed entity update.
- JPQL/HQL bulk DML.
- Native SQL và JDBC.
- Batch import.
- Stored procedure hoặc trigger.
- Script vận hành và job nền.

Bulk DML thường bỏ qua dirty checking và optimistic locking tự động của ORM. Nếu cần giữ semantics version, câu lệnh bulk phải tự thêm predicate version khi so sánh một snapshot cụ thể, hoặc tăng version cho các hàng thay đổi để làm stale các entity đã đọc trước đó.

## 7. Cách sửa bằng pessimistic locking: khóa trước khi đọc quyết định

Khi xung đột thường xuyên hoặc nghiệp vụ yêu cầu chỉ một transaction được quyết định trên một hàng tại một thời điểm, có thể dùng khóa bi quan.

Ví dụ theo cú pháp PostgreSQL/MySQL:

~~~sql
BEGIN;

SELECT quantity
FROM product_stock
WHERE product_id = :product_id
FOR UPDATE;

-- Kiểm tra quantity trong transaction đang giữ khóa.

UPDATE product_stock
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;

COMMIT;
~~~

SELECT ... FOR UPDATE yêu cầu khóa hàng cho đến khi transaction kết thúc. Transaction khác muốn cập nhật hàng đó phải chờ hoặc nhận lỗi tùy cách truy vấn và timeout. Khi transaction đầu commit, transaction tiếp theo mới tiếp tục và có thể đọc giá trị đã cập nhật.

### Khóa phải được lấy trước khi kiểm tra

Mẫu sau không bảo vệ được quyết định:

~~~sql
BEGIN;

SELECT quantity
FROM product_stock
WHERE product_id = :product_id;

-- Chờ hoặc xử lý lâu ở ứng dụng.

SELECT quantity
FROM product_stock
WHERE product_id = :product_id
FOR UPDATE;

-- Dữ liệu đã đọc ở SELECT đầu không còn là căn cứ đáng tin cậy.
~~~

Nếu cần khóa, lấy khóa trước khi đọc giá trị dùng để quyết định. Sau khi lấy khóa, thực hiện kiểm tra và ghi trong cùng transaction.

### Đánh đổi của khóa bi quan

- Transaction khác có thể phải chờ, làm tăng latency.
- Transaction mở lâu giữ khóa lâu và có thể gây lock timeout/deadlock.
- Nếu khóa theo thứ tự khác nhau giữa các luồng, deadlock có thể xuất hiện.
- Nếu truy vấn không có index phù hợp, phạm vi khóa có thể rộng hơn dự kiến tùy DBMS.
- Giữ khóa trong lúc gọi API hoặc chờ người dùng là thiết kế rủi ro.

Chuẩn hóa thứ tự lấy khóa, giữ transaction ngắn và chỉ khóa phạm vi cần thiết. Nếu một hàng nóng bị tranh chấp liên tục, hãy cân nhắc atomic DML hoặc mô hình dữ liệu khác.

## 8. Dùng SERIALIZABLE khi quyết định phụ thuộc predicate hoặc nhiều hàng

Version trên một hàng không bảo vệ được mọi invariant nhiều hàng. Ví dụ, quy tắc là “mỗi khoa phải có ít nhất một bác sĩ trực”. Hai transaction có thể cùng đọc hai bác sĩ đang trực, rồi mỗi transaction tắt một hàng khác nhau. Version của từng hàng vẫn khớp, nhưng kết quả tổng hợp bị phá vỡ.

Khi quyết định phụ thuộc một predicate hoặc tập hàng, có thể cần SERIALIZABLE, guard row hoặc constraint chuyên biệt.

Ví dụ logic:

~~~text
BEGIN SERIALIZABLE
  đếm số bác sĩ đang trực trong khoa
  nếu thay đổi làm số người trực còn 0:
      từ chối
  cập nhật trạng thái bác sĩ
COMMIT
~~~

DBMS bảo đảm lịch được chấp nhận tương đương với một thứ tự tuần tự hợp lệ. Một transaction có thể bị chặn hoặc bị hủy bằng serialization failure. Ứng dụng phải rollback và retry toàn bộ transaction trong snapshot mới nếu thao tác có thể chạy lại an toàn.

### Guard row

Một cách điều phối tường minh là tạo một hàng đại diện cho phạm vi nghiệp vụ, ví dụ một hàng cho mỗi khoa. Mọi transaction thay đổi lịch trực khóa hàng guard trước khi đếm và cập nhật.

~~~sql
BEGIN;

SELECT department_id
FROM department_guard
WHERE department_id = :department_id
FOR UPDATE;

SELECT COUNT(*)
FROM doctor_duty
WHERE department_id = :department_id
  AND on_call = TRUE;

-- Kiểm tra invariant và cập nhật.

COMMIT;
~~~

Guard row biến nhiều thay đổi liên quan thành một điểm điều phối chung. Mọi đường ghi ảnh hưởng invariant phải tuân thủ cùng giao thức. Nếu có đường ghi bỏ qua guard, bảo vệ không còn đầy đủ.

## 9. Constraint bảo vệ điều gì và không bảo vệ điều gì?

Constraint là hàng rào ở database và thường là nơi tốt nhất để thực thi quy tắc có thể biểu diễn trực tiếp.

| Quy tắc | Cơ chế thường dùng |
|---|---|
| ID không trùng | PRIMARY KEY |
| Email/SKU duy nhất | UNIQUE |
| Số lượng hoặc giá không âm | CHECK |
| Hàng con phải có hàng cha | FOREIGN KEY |
| Hai booking không chồng thời gian | Exclusion/range constraint nếu DBMS hỗ trợ, hoặc điều phối predicate phù hợp |
| Tổng nhiều hàng không vượt hạn mức | Atomic aggregate/guard/serializable hoặc mô hình dữ liệu phù hợp |

Không nên viết SELECT kiểm tra chưa tồn tại rồi INSERT và cho rằng transaction đã bảo vệ tính duy nhất. Hai transaction có thể cùng thấy không có hàng. UNIQUE constraint phải là hàng rào cuối; một transaction sẽ thắng, transaction kia nhận unique violation hoặc kết quả xung đột theo cú pháp UPSERT.

CHECK thông thường kiểm tra biểu thức trên hàng hiện tại, không phải công cụ tổng quát để chạy COUNT hoặc SUM trên các hàng khác. Dùng trigger mà không khóa hoặc kiểm tra đồng thời đúng cách vẫn có thể tạo race condition.

## 10. Cập nhật trạng thái: kiểm tra trạng thái cũ ngay trong WHERE

Một lỗi read-then-update khác xảy ra khi nhiều worker cùng xử lý một đối tượng có trạng thái PENDING.

Mẫu dễ lỗi:

~~~text
SELECT status
if status == PENDING:
    xử lý nghiệp vụ
    UPDATE status = PROCESSING
~~~

Hai worker có thể cùng đọc PENDING rồi cùng bắt đầu xử lý.

Hãy chuyển việc nhận quyền xử lý thành một conditional update:

~~~sql
UPDATE job
SET status = 'PROCESSING',
    worker_id = :worker_id,
    started_at = CURRENT_TIMESTAMP
WHERE job_id = :job_id
  AND status = 'PENDING';
~~~

Chỉ worker nhận được affected rows = 1 mới được xem là đã claim công việc. Worker nhận 0 hàng phải coi job đã được worker khác nhận hoặc trạng thái đã thay đổi.

Nếu quyền xử lý có thời hạn, cần thêm lease_until, claim token, heartbeat và điều kiện ACK theo token hiện tại. Một câu UPDATE đổi status không tự xử lý được worker chết hoặc worker cũ thức dậy sau khi lease hết hạn.

## 11. DBMS khác nhau ở cách đọc và khóa

Không nên giả định cùng một lịch SELECT rồi UPDATE sẽ block hoặc trả kết quả giống nhau ở mọi DBMS. Cần ghi rõ hệ quản trị, isolation level, engine và cấu hình.

| DBMS | Hành vi cần lưu ý |
|---|---|
| PostgreSQL | READ COMMITTED tạo snapshot mới cho mỗi statement; SELECT thường không khóa hàng chống UPDATE; SELECT FOR UPDATE lấy row lock. REPEATABLE READ dùng snapshot ổn định và có thể cho write skew; SERIALIZABLE dùng SSI và có thể trả SQLSTATE 40001. |
| MySQL/InnoDB | Mặc định thường là REPEATABLE READ; consistent SELECT và SELECT ... FOR UPDATE có semantics khác nhau. Locking read đọc theo quy tắc khóa hiện tại. Gap/next-key lock có thể bảo vệ range trong một số truy vấn và isolation. |
| SQL Server | READ COMMITTED có thể dùng khóa hoặc row versioning tùy cấu hình READ_COMMITTED_SNAPSHOT. UPDLOCK yêu cầu update lock; HOLDLOCK có semantics tương đương SERIALIZABLE cho tham chiếu bảng trong phạm vi áp dụng. |
| Oracle | SELECT thông thường dùng read consistency và không khóa hàng để ngăn writer. SELECT FOR UPDATE khóa hàng; SERIALIZABLE có thể phát sinh ORA-08177 khi transaction không thể serialize. |

### Ví dụ SQL Server với update lock

~~~sql
BEGIN TRANSACTION;

SELECT quantity
FROM dbo.ProductStock WITH (UPDLOCK, ROWLOCK)
WHERE product_id = @product_id;

-- Kiểm tra giá trị trong khi giữ update lock.

UPDATE dbo.ProductStock
SET quantity = quantity - @requested
WHERE product_id = @product_id
  AND quantity >= @requested;

COMMIT TRANSACTION;
~~~

Đây là mẫu minh họa. Nếu cần bảo vệ một predicate/range hoặc hàng chưa tồn tại, có thể cần SERIALIZABLE/HOLDLOCK và index phù hợp. ROWLOCK là hint, không phải cam kết tuyệt đối rằng engine chỉ dùng row lock trong mọi tình huống.

### Ví dụ Oracle

~~~sql
SELECT quantity
FROM product_stock
WHERE product_id = :product_id
FOR UPDATE;
~~~

Oracle giữ khóa hàng đến khi transaction kết thúc. Nếu ứng dụng cần NOWAIT hoặc WAIT n giây, cú pháp khóa có thể bổ sung tùy phiên bản. Không giữ khóa khi gọi dịch vụ ngoài.

## 12. ORM không tự bảo vệ mọi câu lệnh

ORM có thể tự thêm version predicate khi cập nhật entity được quản lý nếu mapping được cấu hình optimistic locking, ví dụ JPA @Version hoặc EF Core concurrency token.

Nhưng các đường ghi sau thường bỏ qua dirty checking/version check tự động:

- JPQL/HQL bulk UPDATE hoặc DELETE.
- Native SQL.
- JDBC/Dapper.
- EF Core ExecuteUpdate/ExecuteDelete.
- Batch job hoặc script ngoài ORM.

Ví dụ một native UPDATE chỉ lọc theo ID:

~~~sql
UPDATE product
SET price = :price
WHERE product_id = :id;
~~~

Câu lệnh không kiểm tra version cũ dù entity có @Version. Nếu cần optimistic check, phải viết:

~~~sql
UPDATE product
SET price = :price,
    version = version + 1
WHERE product_id = :id
  AND version = :expected_version;
~~~

Sau bulk DML, persistence context/change tracker có thể còn entity cũ. Cần flush trước khi chạy bulk nếu có thay đổi đang chờ, rồi clear/reload/refresh entity bị ảnh hưởng theo đúng phạm vi. Không tiếp tục lưu object cũ mà không hiểu trạng thái của nó.

## 13. Một transaction không làm cho tác động ngoài database trở nên nguyên tử

Nếu code đọc dữ liệu, cập nhật database rồi gọi API ngoài trong cùng một phương thức transactional, rollback database không thể hoàn tác API đã thành công.

Ví dụ:

~~~text
BEGIN database transaction
  đọc tồn kho
  kiểm tra đủ hàng
  cập nhật tồn kho
  gọi Payment API
  Payment thành công
  transaction DB gặp deadlock và rollback
END
~~~

Database có thể rollback tồn kho trong khi Payment vẫn đã charge. Khi retry, ứng dụng có nguy cơ charge lần nữa.

Giữ transaction DB ngắn và dùng idempotency key cho API ngoài. Nếu cần phát message sau commit, dùng transactional outbox. Nếu workflow đi qua nhiều service, cân nhắc saga và compensation. Không coi transaction annotation của framework là transaction phân tán.

## 14. Kiểm thử lỗi đọc rồi cập nhật không bảo vệ

Một test tốt phải tạo được interleaving cụ thể bằng hai connection độc lập.

### Kịch bản A: chứng minh stale overwrite

Trạng thái đầu:

| product_id | quantity |
|---:|---:|
| 101 | 5 |

Lịch:

1. Session A đọc quantity = 5.
2. Session B đọc quantity = 5.
3. A ghi quantity = 1 và commit.
4. B ghi quantity = 1 theo giá trị đã tính từ lần đọc cũ và commit.
5. Đọc trạng thái cuối.

Kết quả mong đợi: quantity = 1 dù hai yêu cầu đã bán tổng cộng 8. Đây là bằng chứng phép ghi tuyệt đối từ snapshot cũ đã làm mất một thay đổi.

### Kịch bản B: chứng minh conditional UPDATE ngăn bán vượt tồn

Reset quantity về 5. Hai session cùng chạy:

~~~sql
UPDATE product_stock
SET quantity = quantity - 4
WHERE product_id = 101
  AND quantity >= 4;
~~~

Kết quả mong đợi:

- Một session cập nhật 1 hàng và trừ stock từ 5 xuống 1.
- Session còn lại cập nhật 0 hàng vì điều kiện quantity >= 4 không còn đúng.
- Trạng thái cuối là 1; chỉ một yêu cầu được chấp nhận.

Thứ tự session thắng có thể thay đổi. Điều cần assert là tổng số yêu cầu thành công bằng một và quantity không âm.

### Kịch bản C: chứng minh optimistic version check

1. A và B cùng đọc version 7.
2. A UPDATE với WHERE version = 7 và tăng version lên 8; affected rows = 1.
3. B UPDATE vẫn với WHERE version = 7; affected rows = 0.
4. B trả conflict hoặc tải lại dữ liệu theo nghiệp vụ.

Kết quả mong đợi là không có cập nhật im lặng từ version cũ.

### Kịch bản D: chứng minh khóa bi quan

1. A BEGIN và SELECT ... FOR UPDATE hàng tồn kho.
2. B thử SELECT FOR UPDATE hoặc UPDATE cùng hàng.
3. B phải chờ hoặc nhận lỗi theo timeout/lock mode.
4. A kiểm tra, cập nhật và COMMIT.
5. B tiếp tục, đọc trạng thái phù hợp rồi quyết định.

Ghi nhận lock wait và trạng thái cuối. Không chỉ assert B bị block; cần chứng minh B không dùng giá trị đã đọc trước khi lấy khóa.

## 15. Tránh test phụ thuộc sleep

Không nên dùng sleep cố định để hy vọng hai request đọc cùng lúc. Máy CI, scheduler và tải database có thể làm lịch thực thi khác nhau.

Trong integration test, dùng barrier/latch:

~~~java
CountDownLatch bothRead = new CountDownLatch(2);
CountDownLatch allowUpdate = new CountDownLatch(1);

// Mỗi transaction:
var state = readStock();
bothRead.countDown();
bothRead.await(timeout);
allowUpdate.await(timeout);
performUpdateUsingReadState(state);
~~~

Đây là mã giả mô tả cách đồng bộ. Test thực tế phải có timeout ở mọi barrier để không treo. Dùng hai connection riêng và kiểm tra DBMS/transaction state sau test.

## 16. Những dấu hiệu cho thấy ứng dụng đang mắc lỗi stale read

Các triệu chứng thường gặp:

- Số dư hoặc số lượng bị ghi đè về giá trị cũ.
- Hai request cùng nhận thành công dù chỉ một request đáng lẽ được phép.
- Đơn hàng chuyển từ trạng thái mới về trạng thái cũ.
- Một bản ghi được tạo trùng dù code đã SELECT kiểm tra trước.
- Dữ liệu thay đổi bất thường khi người dùng mở form lâu rồi mới bấm Save.
- ORM báo optimistic lock exception ở một số đường ghi nhưng native SQL vẫn ghi đè im lặng.
- Batch job chạy đồng thời với API làm mất thay đổi.

Khi điều tra, cần nối log request với transaction/session, xem câu SELECT ban đầu và câu UPDATE cuối, kiểm tra điều kiện WHERE, version token và số hàng bị ảnh hưởng. Chỉ nhìn câu UPDATE cuối có thể không thấy giá trị cũ đã được đọc và dùng để tính toán.

## 17. Các cách sửa không đầy đủ

| Cách làm | Vì sao chưa đủ |
|---|---|
| Chỉ bọc SELECT và UPDATE trong BEGIN/COMMIT | Isolation mặc định có thể không giữ khóa bảo vệ dữ liệu đã đọc |
| Thêm một SELECT kiểm tra ngay trước UPDATE | Transaction khác vẫn có thể ghi giữa SELECT mới và UPDATE |
| Kiểm tra ở giao diện | Nhiều request có thể cùng vượt qua kiểm tra ở client |
| Chỉ thêm cột version | Mọi câu UPDATE không tự động kiểm tra cột đó |
| Chỉ dùng ORM @Version | Native/bulk SQL có thể bỏ qua version semantics |
| Tăng timeout | Không ngăn stale overwrite hoặc check-then-act race |
| Retry câu UPDATE cuối | Có thể dùng lại giá trị và quyết định từ snapshot cũ |
| Thêm khóa ứng dụng nhưng một số đường ghi bỏ qua | Giao thức không bảo vệ toàn bộ dữ liệu |
| Chỉ dùng CHECK quantity >= 0 | Không ngăn mọi quy tắc bán/đặt chỗ vượt số lượng nếu dữ liệu sai vẫn không âm |

## 18. Chọn cơ chế theo loại quyết định

| Câu hỏi nghiệp vụ | Cơ chế nên xem xét trước |
|---|---|
| Có thể cập nhật bằng một phép cộng/trừ trên giá trị hiện tại không? | Atomic UPDATE |
| Có điều kiện đơn giản trên chính hàng được ghi không? | Conditional UPDATE và affected-row check |
| Người dùng đọc rồi chỉnh sửa một entity trong thời gian dài? | Optimistic version check |
| Xung đột thường xuyên trên một hàng và cần tuần tự hóa thao tác? | SELECT FOR UPDATE hoặc cơ chế khóa tương đương |
| Có invariant liên quan nhiều hàng/predicate? | Constraint phù hợp, guard row hoặc SERIALIZABLE |
| Cần ngăn hai request tạo cùng khóa nghiệp vụ? | UNIQUE constraint và INSERT/UPSERT phù hợp |
| Có worker cùng nhận một trạng thái công việc? | Conditional claim, lease/token và ACK có điều kiện |
| Có tác động ngoài database? | Idempotency, outbox hoặc saga bên cạnh transaction cục bộ |

Có thể kết hợp nhiều cơ chế. Ví dụ, trừ tồn kho bằng conditional UPDATE, giữ CHECK quantity >= 0 làm hàng rào cuối, và ghi order cùng inventory change trong một transaction. Nếu thao tác còn phát event, ghi outbox trong cùng transaction.

## 19. Checklist trước khi lưu dữ liệu đã đọc

Trước khi viết code theo mẫu SELECT rồi UPDATE, hãy trả lời:

1. Giá trị đã đọc có thể bị transaction khác thay đổi trước khi ghi không?
2. Quyết định nghiệp vụ có còn đúng nếu giá trị thay đổi không?
3. Có thể đưa điều kiện và phép cập nhật vào một câu UPDATE nguyên tử không?
4. Nếu không, có version token để compare-and-swap không?
5. Nếu cần khóa, khóa có được lấy trước khi đọc và giữ trong cùng transaction không?
6. Invariant có phụ thuộc nhiều hàng hoặc một predicate không?
7. Có constraint database để bảo vệ quy tắc ở mọi đường ghi không?
8. Bulk/native SQL và job nền có tuân thủ cùng cơ chế không?
9. Khi affected rows = 0 hoặc có optimistic conflict, ứng dụng phản hồi thế nào?
10. Retry có chạy lại toàn bộ transaction với dữ liệu mới không?
11. Có side effect ngoài database cần idempotency/outbox không?
12. Integration test có tái tạo được hai session chạy xen kẽ không?

## 20. Nguyên tắc kết luận

Đọc dữ liệu rồi cập nhật sau đó là một mẫu bình thường trong ứng dụng; lỗi xuất hiện khi quyết định ghi vẫn dựa trên dữ liệu đã đọc nhưng không xác nhận dữ liệu đó còn hợp lệ. Transaction đơn thuần không bảo vệ mọi kết quả SELECT. Cần đưa điều kiện vào câu UPDATE, dùng version check, khóa trước khi đọc, constraint hoặc SERIALIZABLE tùy phạm vi invariant.

Hãy để database kiểm tra điều kiện tại thời điểm ghi và kiểm tra kết quả affected rows. Với cập nhật entity kéo dài, dùng optimistic locking; với tranh chấp thường xuyên, cân nhắc khóa bi quan; với invariant nhiều hàng, bảo vệ predicate hoặc phạm vi nghiệp vụ; với tác động ngoài database, thêm idempotency và outbox. Mục tiêu là không cho một quyết định dựa trên trạng thái cũ âm thầm ghi đè hoặc làm sai trạng thái mới hơn.
