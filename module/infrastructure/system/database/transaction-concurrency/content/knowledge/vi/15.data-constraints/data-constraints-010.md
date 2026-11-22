# Sequence, cột tự tăng và lý do không nên suy luận thứ tự COMMIT từ mã sinh

Sequence và cột tự tăng (auto-increment/identity) giúp database cấp một giá trị định danh duy nhất cho mỗi bản ghi mà không cần ứng dụng tự chọn số. Chúng rất hữu ích để tạo khóa chính (primary key), nhưng **thứ tự mã được cấp không phải là thứ tự transaction COMMIT**.

Một transaction có thể lấy ID 100 trước, tạm dừng, trong khi transaction khác lấy ID 101 và COMMIT trước. Sau đó transaction đầu mới COMMIT. Khi truy vấn sắp xếp theo ID, bản ghi 101 có thể xuất hiện trước bản ghi 100 dù ID 100 được cấp sớm hơn.

Sự khác biệt này xuất phát từ việc bộ sinh số thường hoạt động độc lập với transaction commit. Sequence bảo đảm việc cấp số an toàn khi có nhiều session cạnh tranh; nó không tự tạo ra một hàng đợi commit và cũng không ghi lại thứ tự hoàn tất nghiệp vụ.

## 1. Sequence và cột tự tăng dùng để làm gì?

Một bảng thường cần khóa chính để nhận diện từng dòng. Ứng dụng có thể tự tạo ID, nhưng nếu nhiều request cùng chọn số tiếp theo thì chúng có thể chọn trùng. Database cung cấp các cơ chế sinh số để phối hợp việc này an toàn.

Ví dụ bảng Order:

~~~sql
CREATE TABLE Orders
(
    OrderId     bigint PRIMARY KEY,
    CustomerId  int NOT NULL,
    TotalAmount decimal(18, 2) NOT NULL
);
~~~

Một sequence có thể cấp giá trị cho OrderId:

~~~sql
CREATE SEQUENCE dbo.OrderSequence
    AS bigint
    START WITH 1
    INCREMENT BY 1;
~~~

Khi insert, ứng dụng lấy giá trị tiếp theo:

~~~sql
INSERT INTO dbo.Orders (OrderId, CustomerId, TotalAmount)
VALUES (NEXT VALUE FOR dbo.OrderSequence, @customerId, @totalAmount);
~~~

Ở nhiều DBMS, cột tự tăng/identity kết hợp bộ sinh số với định nghĩa cột. Ứng dụng chỉ cần bỏ cột ID khỏi INSERT và database tự cấp giá trị.

Các cơ chế này giải quyết việc **cấp định danh**, thường có các đặc điểm:

- Nhiều session có thể xin số đồng thời mà không phải tự phối hợp ở tầng ứng dụng.
- Mỗi lần cấp thường tạo ra giá trị khác nhau trong phạm vi sequence.
- Việc cấp số thường không bị hoàn tác cùng transaction.
- Có thể xuất hiện khoảng trống (gap).
- Thứ tự số không đại diện cho thứ tự commit hay thứ tự hoàn tất công việc.

Giá trị ID nên được xem là định danh kỹ thuật. Một khóa chính duy nhất có thể nhận diện bản ghi, nhưng không tự cho biết bản ghi được commit lúc nào, request nào đến trước hoặc nghiệp vụ nào hoàn tất trước.

## 2. Phân biệt thời điểm cấp số và thời điểm COMMIT

Hãy xét hai transaction cùng insert một đơn hàng:

~~~text
Thời gian tăng dần
    |
    v

Transaction A                    Transaction B
--------------                    --------------
BEGIN
Lấy sequence: 100
INSERT OrderId = 100
                                  BEGIN
                                  Lấy sequence: 101
                                  INSERT OrderId = 101
                                  COMMIT
COMMIT

Thứ tự cấp ID: 100 rồi 101
Thứ tự COMMIT: B rồi A
~~~

T1/A lấy ID 100 trước, nhưng chưa commit. T2/B lấy ID 101 sau và commit trước. Khi A commit, database đã có cả hai dòng.

Một truy vấn:

~~~sql
SELECT OrderId, CustomerId, TotalAmount
FROM Orders
ORDER BY OrderId;
~~~

sẽ hiển thị dòng có ID 100 trước dòng có ID 101. Đây là thứ tự số tăng dần, không phải thứ tự commit.

Điều này không phải lỗi của sequence. Sequence đã thực hiện đúng nhiệm vụ: cấp các giá trị không trùng theo cơ chế của nó. Transaction manager có nhiệm vụ commit và bảo đảm tính nhất quán dữ liệu; nó không yêu cầu commit theo thứ tự ID.

### 2.1. Vì sao transaction có thể commit khác thứ tự?

Sau khi lấy ID, transaction còn có thể phải:

- Chờ khóa do transaction khác giữ.
- Kiểm tra hoặc cập nhật nhiều bảng.
- Ghi dữ liệu vào nhiều index.
- Chờ I/O, log flush hoặc tài nguyên hệ thống.
- Thực hiện trigger hoặc constraint.
- Chạy thêm logic ứng dụng trước khi commit.
- Gặp lỗi và retry.

Thời gian hoàn tất của mỗi transaction khác nhau. Sequence không biết transaction nào sẽ hoàn tất trước, và cũng không giữ các transaction trong một hàng đợi theo số ID.

### 2.2. Thứ tự hiển thị cũng không tự có

SQL không bảo đảm thứ tự dòng trả về nếu câu SELECT không có ORDER BY. Dù ID thường tăng, database vẫn có thể trả kết quả theo kế hoạch truy vấn, index, parallel execution hoặc cách lưu trữ.

Nếu muốn sắp xếp theo ID, phải viết:

~~~sql
SELECT OrderId, CustomerId
FROM Orders
ORDER BY OrderId;
~~~

Câu lệnh này bảo đảm thứ tự kết quả theo OrderId. Nó vẫn không biến OrderId thành commit timestamp.

## 3. Sequence không rollback cùng transaction

Một đặc điểm quan trọng của sequence là giá trị đã cấp thường không được trả lại khi transaction rollback.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

INSERT INTO Orders (OrderId, CustomerId, TotalAmount)
VALUES (NEXT VALUE FOR dbo.OrderSequence, 10, 500000);

ROLLBACK TRANSACTION;
~~~

Giả sử sequence đã cấp số 102. Transaction rollback nên dòng Order không được lưu, nhưng số 102 vẫn đã được tiêu thụ. Lần tiếp theo có thể nhận 103.

~~~text
Sequence:
100 -> đã dùng
101 -> đã dùng
102 -> đã cấp cho transaction rollback
103 -> lần cấp tiếp theo

Các dòng thực sự tồn tại có thể chỉ mang ID 100, 101, 103.
~~~

Khoảng trống không có nghĩa dữ liệu bị mất hoặc transaction commit thất bại bất thường. Nó là hành vi bình thường của bộ sinh số không transactional.

### 3.1. Những nguyên nhân khác tạo gap

Ngoài rollback, sequence/identity có thể tạo khoảng trống vì:

- Một câu INSERT thất bại sau khi giá trị ID đã được lấy.
- Một câu INSERT bị từ chối bởi constraint hoặc trigger.
- Một thao tác upsert phát hiện xung đột sau khi đã tiêu thụ sequence value.
- Ứng dụng lấy NEXTVAL nhưng sau đó không dùng giá trị.
- Database hoặc session cấp trước một nhóm số thông qua cache rồi bị dừng.
- Quản trị viên đặt lại sequence hoặc thay đổi cấu hình.
- Các thao tác xóa bản ghi làm ID đã dùng không còn xuất hiện trong bảng.

Vì vậy, không nên dùng việc đếm ID để suy ra số transaction thành công, số đơn hàng đã tạo hoặc số giao dịch đã commit.

### 3.2. Vì sao không nên yêu cầu ID không có gap?

Một sequence được thiết kế để cấp số nhanh cho nhiều transaction. Nếu mỗi số phải được giữ lại cho đến khi transaction commit, các transaction sẽ phải phối hợp qua một bộ đếm được tuần tự hóa. Điều đó có thể làm giảm concurrency và tạo điểm nghẽn.

Trong nhiều hệ thống, gap không ảnh hưởng đến tính đúng đắn vì ID chỉ là khóa định danh. Nếu nghiệp vụ cần số chứng từ liên tục, hãy thiết kế một cơ chế đánh số nghiệp vụ riêng, có transaction và quy tắc hủy/void rõ ràng. Không ép sequence kỹ thuật đảm nhiệm yêu cầu đó.

## 4. Cache làm thứ tự cấp số càng không phải đồng hồ thời gian

Để giảm chi phí đồng bộ, nhiều DBMS cho phép cache một nhóm giá trị sequence. Một session hoặc instance có thể được cấp trước một dải số để sử dụng dần.

Ví dụ minh họa:

~~~text
Session A được cache: 1, 2, 3, 4, 5
Session B được cache: 6, 7, 8, 9, 10

B sử dụng 6 trước.
A sau đó mới sử dụng 2.

Thứ tự giá trị được phát ra:
6, 2, ...

Giá trị số:
2 < 6
~~~

Khi cache được dùng, giá trị số vẫn được cấp theo các quy tắc duy nhất của sequence, nhưng thời điểm một session sử dụng một giá trị trong dải cache không nhất thiết theo thứ tự tăng toàn cục.

Nếu database dừng bất thường, phần giá trị đã cache nhưng chưa dùng có thể bị bỏ qua. Điều này tạo gap sau khi khởi động lại.

Không phải mọi DBMS và mọi cấu hình đều dùng cache theo cùng cách. Nhưng dù tắt cache, vẫn không thể suy ra thứ tự COMMIT từ ID: transaction có thể lấy số trước rồi commit sau.

## 5. Hành vi của các DBMS phổ biến

Tên gọi khác nhau, nhưng điểm chung là giá trị identity/sequence được cấp không phải bằng chứng về thứ tự commit.

| DBMS | Cơ chế thường gặp | Điều cần nhớ |
|---|---|---|
| PostgreSQL | SEQUENCE, SERIAL, GENERATED AS IDENTITY | nextval không rollback; cache có thể tạo gap và việc cấp số tách khỏi COMMIT |
| SQL Server | IDENTITY hoặc SEQUENCE | Giá trị identity/sequence có thể bị tiêu thụ khi transaction rollback hoặc insert thất bại; sequence có cache |
| MySQL InnoDB | AUTO_INCREMENT | Giá trị đã cấp có thể tạo gap khi rollback, insert thất bại hoặc nhiều insert cạnh tranh; không biểu diễn commit order |
| Oracle Database | SEQUENCE và identity column | NEXTVAL độc lập với transaction; cache và rollback có thể tạo gap; ORDER không đảm bảo thứ tự COMMIT |

### 5.1. PostgreSQL

PostgreSQL có thể tạo sequence tường minh:

~~~sql
CREATE SEQUENCE order_id_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 20;
~~~

Lấy số tiếp theo:

~~~sql
SELECT nextval('order_id_seq');
~~~

Hoặc khai báo identity:

~~~sql
CREATE TABLE orders
(
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
);
~~~

nextval cấp giá trị ngay khi được gọi. Giá trị đó không được trả lại khi transaction rollback. Tùy cấu hình CACHE, session có thể giữ trước một nhóm số. Vì vậy, sequence không nên được dùng làm đồng hồ commit.

Để lấy ID của dòng vừa insert, dùng RETURNING:

~~~sql
INSERT INTO orders (customer_id)
VALUES (42)
RETURNING order_id;
~~~

RETURNING trả về ID được tạo cho chính dòng vừa insert; nó không cho biết transaction khác commit trước hay sau.

### 5.2. SQL Server

SQL Server hỗ trợ IDENTITY:

~~~sql
CREATE TABLE dbo.Orders
(
    OrderId bigint IDENTITY(1, 1) PRIMARY KEY,
    CustomerId int NOT NULL
);
~~~

Hoặc sequence độc lập:

~~~sql
CREATE SEQUENCE dbo.OrderSequence
    AS bigint
    START WITH 1
    INCREMENT BY 1
    CACHE 50;
~~~

Lấy ID được sinh trong câu INSERT bằng OUTPUT:

~~~sql
INSERT INTO dbo.Orders (CustomerId)
OUTPUT INSERTED.OrderId
VALUES (@customerId);
~~~

SCOPE_IDENTITY() cũng có thể trả identity mới nhất trong cùng scope, nhưng OUTPUT hữu ích khi cần lấy ID của nhiều dòng vừa insert.

IDENTITY và SEQUENCE không bảo đảm các số liên tiếp không có gap hoặc transaction commit theo thứ tự ID. SQL Server có tùy chọn sequence cache; việc server dừng hoặc khởi động lại có thể làm bỏ qua các giá trị đã cache.

### 5.3. MySQL InnoDB

MySQL thường dùng AUTO_INCREMENT:

~~~sql
CREATE TABLE orders
(
    order_id bigint NOT NULL AUTO_INCREMENT,
    customer_id bigint NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE = InnoDB;
~~~

Sau khi insert, có thể lấy ID vừa cấp trong cùng connection bằng LAST_INSERT_ID():

~~~sql
INSERT INTO orders (customer_id)
VALUES (42);

SELECT LAST_INSERT_ID();
~~~

LAST_INSERT_ID() là thông tin theo connection, hữu ích để lấy ID của thao tác insert hiện tại. Không dùng SELECT MAX(order_id) để tìm ID vừa tạo, vì một transaction khác có thể đã insert ID lớn hơn.

InnoDB có các chế độ AUTO_INCREMENT lock ảnh hưởng đến cách phối hợp insert đồng thời và phân bổ ID trong những thao tác một dòng, nhiều dòng hoặc bulk insert. Dù chọn chế độ nào, giá trị AUTO_INCREMENT không cho biết thứ tự commit. Rollback và insert thất bại cũng có thể để lại gap.

### 5.4. Oracle Database

Oracle dùng sequence tường minh:

~~~sql
CREATE SEQUENCE order_seq
    START WITH 1
    INCREMENT BY 1
    CACHE 50;
~~~

Lấy giá trị:

~~~sql
SELECT order_seq.NEXTVAL
FROM dual;
~~~

Có thể dùng sequence trong INSERT:

~~~sql
INSERT INTO orders (order_id, customer_id)
VALUES (order_seq.NEXTVAL, 42);
~~~

Hoặc lấy ID vừa insert qua RETURNING INTO trong PL/SQL:

~~~sql
DECLARE
    v_order_id orders.order_id%TYPE;
BEGIN
    INSERT INTO orders (order_id, customer_id)
    VALUES (order_seq.NEXTVAL, 42)
    RETURNING order_id INTO v_order_id;
END;
~~~

Oracle có tùy chọn ORDER cho sequence trong môi trường hỗ trợ, yêu cầu giá trị được cấp theo thứ tự yêu cầu NEXTVAL. Đây là thứ tự cấp giá trị, không phải thứ tự transaction COMMIT. Một transaction nhận số trước vẫn có thể commit sau transaction nhận số tiếp theo.

## 6. Ví dụ cụ thể: ID nhỏ hơn nhưng commit muộn hơn

Giả sử sequence bắt đầu từ 500. Hai session chạy đồng thời.

Session A:

~~~sql
BEGIN TRANSACTION;

INSERT INTO dbo.Orders (OrderId, CustomerId, TotalAmount)
VALUES (NEXT VALUE FOR dbo.OrderSequence, 10, 1000000);

-- Giữ transaction mở, chưa COMMIT.
~~~

Session B:

~~~sql
BEGIN TRANSACTION;

INSERT INTO dbo.Orders (OrderId, CustomerId, TotalAmount)
VALUES (NEXT VALUE FOR dbo.OrderSequence, 20, 2000000);

COMMIT TRANSACTION;
~~~

Sau đó Session A mới COMMIT:

~~~sql
COMMIT TRANSACTION;
~~~

Kết quả có thể là:

| OrderId | Transaction | Thứ tự lấy ID | Thứ tự COMMIT |
|---:|---|---:|---:|
| 500 | A | 1 | 2 |
| 501 | B | 2 | 1 |

Truy vấn ORDER BY OrderId hiển thị 500 rồi 501. Nhưng B đã commit trước A.

Nếu ứng dụng dùng điều kiện OrderId lớn hơn lastSeenId để đọc các bản ghi mới theo giả định ID luôn phản ánh commit order, nó có thể bỏ sót bản ghi.

Ví dụ:

1. Consumer đọc đến OrderId 499.
2. A lấy 500 nhưng chưa commit.
3. B lấy 501 và commit.
4. Consumer truy vấn các dòng có OrderId lớn hơn 499, thấy 501 rồi lưu checkpoint 501.
5. A commit bản ghi 500.
6. Consumer truy vấn các dòng có OrderId lớn hơn 501, không còn thấy 500.

Bản ghi 500 đã commit sau checkpoint nhưng có ID nhỏ hơn checkpoint, nên consumer bỏ sót nó.

Đây là một lỗi thực tế khi dùng auto-increment ID làm watermark cho đồng bộ dữ liệu hoặc phân trang tăng dần trong khi có transaction chạy lâu.

## 7. Không dùng ID làm watermark đồng bộ nếu commit có thể đảo thứ tự

Một số quy trình đọc dữ liệu mới sử dụng ID lớn nhất đã xử lý làm checkpoint:

~~~sql
SELECT *
FROM Orders
WHERE OrderId > @lastProcessedId
ORDER BY OrderId;
~~~

Cách này chỉ an toàn nếu hệ thống có một bảo đảm bổ sung về thứ tự và thời điểm dữ liệu trở nên nhìn thấy. Sequence đơn thuần không cung cấp bảo đảm đó.

Các phương án phù hợp hơn tùy yêu cầu:

**Change Data Capture hoặc transaction log position.** Nếu cần theo dõi thay đổi đã commit, dùng CDC, logical decoding hoặc cơ chế đọc transaction log của DBMS. Vị trí log/LSN được thiết kế để xác định thứ tự thay đổi trong log và có thể làm checkpoint. Cần dùng đúng API và semantics của công nghệ CDC cụ thể.

**Outbox với consumer checkpoint.** Ghi event cùng transaction nghiệp vụ trong bảng Outbox. Publisher phát event sau commit; consumer lưu EventId đã xử lý và xử lý idempotent. Nếu cần thứ tự trong một aggregate, thêm version theo aggregate và bảo đảm publisher/consumer giữ thứ tự đó.

**Cột thời gian nghiệp vụ.** Nếu cần sắp xếp theo thời điểm tạo đơn, lưu CreatedAt với định nghĩa rõ ràng về thời điểm: lúc nhận request, lúc bắt đầu xử lý hay lúc transaction ghi bản ghi. Timestamp được ghi trước COMMIT cũng không nhất thiết là commit timestamp. Nhiều transaction có thể có timestamp theo thứ tự khác với commit.

**Cursor dựa trên khóa ổn định kết hợp quét lặp.** Nếu không có change log, có thể quét theo cửa sổ thời gian chồng lấn, dùng trạng thái đã xử lý và idempotency để bắt các bản ghi đến muộn. Cần thiết kế checkpoint và xử lý trùng một cách rõ ràng.

Không có một cột ID tự tăng nào thay thế được cơ chế ghi nhận thứ tự commit khi hệ thống cần bảo đảm đó.

## 8. Nếu cần thứ tự nghiệp vụ, hãy mô hình hóa nó rõ ràng

Có nhiều loại "thứ tự" khác nhau. Trước khi chọn giải pháp, hãy xác định nghiệp vụ muốn biết điều gì.

| Yêu cầu | Dữ liệu/cơ chế phù hợp |
|---|---|
| Nhận diện duy nhất một bản ghi | Primary key bằng identity, sequence, UUID hoặc ID khác |
| Sắp xếp theo lúc người dùng tạo yêu cầu | Request timestamp được định nghĩa rõ, có quy tắc múi giờ và nguồn đồng hồ |
| Sắp xếp theo phiên bản thay đổi của một đơn hàng | Version tăng trong transaction khi cập nhật aggregate |
| Đánh số chứng từ trong một phạm vi nghiệp vụ | Counter riêng được cập nhật có tuần tự hóa và quy tắc void/hủy |
| Theo dõi thứ tự thay đổi đã commit | CDC, transaction log position hoặc outbox/event stream có semantics rõ |
| Sắp xếp kết quả hiển thị | ORDER BY cột nghiệp vụ phù hợp, kèm tie-breaker duy nhất |

### 8.1. Dùng version theo aggregate

Nếu cần biết thay đổi nào của một đơn hàng xảy ra trước thay đổi nào, có thể thêm Version vào dòng Order hoặc bảng quản lý aggregate.

Ví dụ SQL Server:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.Orders
SET Status = @newStatus,
    Version = Version + 1
OUTPUT INSERTED.OrderId, INSERTED.Version
WHERE OrderId = @orderId
  AND Version = @expectedVersion;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50020, 'Order version conflict.', 1;
END;

COMMIT TRANSACTION;
~~~

Hai transaction cùng cập nhật một Order sẽ cạnh tranh trên cùng dòng. Transaction sau phải chờ hoặc thất bại do version không còn khớp. Version biểu diễn thứ tự cập nhật đã được tuần tự hóa trên aggregate đó.

Đây là thứ tự theo từng Order, không phải thứ tự toàn hệ thống. Hai đơn hàng khác nhau vẫn có thể tăng version độc lập và commit theo bất kỳ thứ tự nào.

### 8.2. Dùng counter transactional khi cần số nghiệp vụ tuần tự

Nếu nghiệp vụ cần số chứng từ theo một nhóm, có thể lưu bộ đếm trong bảng và cập nhật trong cùng transaction tạo chứng từ.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.DocumentCounter
SET NextNumber = NextNumber + 1
OUTPUT DELETED.NextNumber
WHERE CounterName = 'INVOICE';

-- Dùng số vừa lấy để INSERT chứng từ
-- trong chính transaction này.

COMMIT TRANSACTION;
~~~

Việc UPDATE dòng counter được phối hợp bằng khóa của database. Transaction tiếp theo muốn tăng cùng counter phải chờ transaction trước kết thúc. Nếu transaction rollback, thay đổi counter cũng rollback, nên số chưa commit có thể được sử dụng lại.

Đánh đổi là tất cả transaction thuộc cùng CounterName phải đi qua một dòng và bị tuần tự hóa. Một counter toàn hệ thống có thể trở thành điểm nghẽn. Nếu cần đánh số theo chi nhánh hoặc loại chứng từ, có thể tách counter theo phạm vi nghiệp vụ.

Cần định nghĩa rõ cách xử lý chứng từ đã phát hành nhưng bị hủy: nhiều hệ thống giữ số và chuyển trạng thái VOID thay vì xóa chứng từ. Counter transactional có thể tạo dãy số không gap do rollback, nhưng không tự bảo đảm không gap nếu ứng dụng xóa bản ghi, bỏ số sau commit hoặc có thao tác ngoài quy trình.

## 9. Không dùng MAX(ID) để tự sinh ID hoặc xác định bản ghi vừa insert

Một lỗi thường gặp:

~~~sql
INSERT INTO Orders (CustomerId, TotalAmount)
VALUES (@customerId, @amount);

SELECT MAX(OrderId)
FROM Orders;
~~~

MAX(OrderId) trả về ID lớn nhất mà truy vấn nhìn thấy trong phạm vi dữ liệu của nó, không nhất thiết là ID của dòng vừa insert. Một transaction khác có thể đã insert và commit một ID lớn hơn giữa hai câu lệnh.

Ví dụ:

~~~text
Session A                          Session B
---------                          ---------
INSERT OrderId = 600
                                   INSERT OrderId = 601
                                   COMMIT
SELECT MAX(OrderId)
Kết quả: 601
~~~

A vừa tạo dòng 600 nhưng lại nhận nhầm 601. Đây là race condition.

Hãy dùng cơ chế trả ID thuộc chính câu INSERT:

| DBMS | Cách lấy ID vừa insert |
|---|---|
| PostgreSQL | INSERT ... RETURNING id |
| SQL Server | OUTPUT INSERTED.Id hoặc SCOPE_IDENTITY() trong đúng scope |
| MySQL | LAST_INSERT_ID() trên cùng connection |
| Oracle | RETURNING ... INTO hoặc lấy sequence value trong cùng thao tác |

Không dùng MAX(ID), đoán số tiếp theo bằng MAX cộng 1, hoặc lấy ID từ một connection khác.

## 10. UUID, ULID và ID có thành phần thời gian có giải quyết được không?

Một số hệ thống dùng UUID hoặc ULID thay vì số tự tăng:

- UUID ngẫu nhiên giảm phụ thuộc vào một sequence dùng chung.
- UUID phiên bản có thành phần thời gian hoặc ULID có thể sắp xếp gần theo thời điểm tạo ID.
- ID phân tán có thể được sinh tại nhiều service mà không cần hỏi database cho từng giá trị.

Nhưng ID có thành phần thời gian vẫn thường được tạo **trước khi transaction commit**. Hai request có thể sinh ID theo thứ tự thời gian rồi hoàn tất theo thứ tự khác. Đồng hồ giữa các máy có thể lệch; ID có thể được tạo trước khi request bị retry hoặc bị hủy.

Vì vậy:

- UUID/ULID có thể giúp phân tán việc cấp ID.
- Một số dạng ID có thể hỗ trợ sắp xếp gần theo thời điểm sinh.
- Không loại nào tự bảo đảm thứ tự commit.
- Nếu cần thứ tự commit, hãy dùng log/CDC hoặc một cơ chế tuần tự hóa được định nghĩa cho nghiệp vụ.

## 11. Thời gian tạo bản ghi cũng không nhất thiết là commit time

Một cột CreatedAt thường được gán khi ứng dụng hoặc database bắt đầu thực hiện câu INSERT. Nếu transaction giữ mở lâu, CreatedAt có thể sớm hơn thời điểm commit đáng kể.

Ví dụ:

~~~text
T1: CreatedAt = 10:00:00
T1: INSERT
T1: chờ khóa 5 giây
T1: COMMIT lúc 10:00:05

T2: CreatedAt = 10:00:02
T2: INSERT
T2: COMMIT lúc 10:00:03
~~~

Sắp xếp theo CreatedAt cho T1 trước T2, nhưng T2 commit trước T1.

Ngoài ra, hàm thời gian trong DBMS có thể có semantics khác nhau:

- PostgreSQL now()/transaction_timestamp() trả thời điểm bắt đầu transaction; statement_timestamp() trả thời điểm bắt đầu câu lệnh; clock_timestamp() đọc đồng hồ thực tại thời điểm gọi.
- SQL Server SYSUTCDATETIME() trả thời gian UTC tại lúc hàm được đánh giá trong câu lệnh.
- Các DBMS khác có hàm thời gian và độ chính xác riêng.

Dù dùng đồng hồ nào, timestamp được ghi trước COMMIT không tự trở thành commit timestamp. Nếu nghiệp vụ cần thời gian nhận request, thời gian tạo bản ghi hoặc thời gian hoàn tất, hãy đặt tên và ghi nhận đúng sự kiện đó. Nếu cần thứ tự commit thực tế, dùng cơ chế log/CDC được DBMS hỗ trợ.

## 12. Các sai lầm thường gặp

| Giả định | Vì sao sai | Cách làm phù hợp |
|---|---|---|
| ID lớn hơn nghĩa là transaction commit sau | Transaction có thể lấy số trước nhưng commit sau | Dùng commit log/CDC nếu cần thứ tự commit |
| Không có gap nghĩa là mọi transaction đã thành công | Sequence có thể được cấp rồi rollback; ngược lại, ID có thể bị xóa | Theo dõi trạng thái nghiệp vụ hoặc event đã commit |
| MAX(ID) là ID của dòng vừa insert | Transaction khác có thể chèn dòng mới giữa hai câu lệnh | Dùng RETURNING, OUTPUT hoặc LAST_INSERT_ID |
| ORDER BY ID cho biết thứ tự tạo nghiệp vụ | ID chỉ phản ánh cơ chế cấp số, không nhất thiết thời điểm request | Dùng CreatedAt/BusinessSequence có semantics rõ |
| Tắt cache sẽ làm ID theo thứ tự COMMIT | Cache không phải nguyên nhân duy nhất gây đảo thứ tự commit | Tuần tự hóa commit theo khóa nghiệp vụ nếu thực sự cần |
| Sequence là bộ đếm hóa đơn liên tục | Rollback và lỗi insert tạo gap; cache có thể bỏ số | Dùng counter transactional và quy tắc void/hủy |
| UUID/ULID giải quyết thứ tự commit | ID có thể được tạo trước khi commit và đồng hồ có thể lệch | Dùng CDC/log hoặc version/sequence nghiệp vụ |

## 13. Chọn cơ chế theo mục đích

Trước khi dùng sequence, hãy trả lời câu hỏi: giá trị này cần bảo đảm điều gì?

**Nếu chỉ cần khóa chính duy nhất:** dùng identity, auto-increment hoặc sequence. Chấp nhận gap và không suy luận commit order từ ID.

**Nếu cần hiển thị bản ghi mới:** dùng ORDER BY trên trường thời gian hoặc trạng thái nghiệp vụ được định nghĩa rõ, kèm ID làm tie-breaker khi timestamp bằng nhau.

**Nếu cần đồng bộ dữ liệu không bỏ sót commit đến muộn:** dùng CDC, transaction log position hoặc một giao thức outbox/checkpoint có khả năng xử lý sự kiện đến muộn. Không chỉ lưu ID lớn nhất đã nhìn thấy.

**Nếu cần version theo một đơn hàng/tài khoản:** tăng version trong transaction trên chính aggregate đó và kiểm tra version khi cập nhật.

**Nếu cần số chứng từ trong một phạm vi:** dùng counter transactional có khóa tuần tự hóa và quy tắc lưu số đã hủy. Đánh giá throughput vì counter có thể là điểm tranh chấp.

**Nếu cần thứ tự toàn cục của mọi transaction:** đây là yêu cầu tuần tự hóa mạnh, có chi phí phối hợp. Cần xác định chính xác thứ tự cần quan sát là thứ tự commit trong một database, thứ tự sự kiện trong log hay thứ tự nghiệp vụ của request. Chọn nguồn dữ liệu và giao thức tương ứng thay vì dùng ID kỹ thuật.

## 14. Những nguyên tắc cần ghi nhớ

- Sequence, IDENTITY và AUTO_INCREMENT cấp giá trị định danh; chúng không xếp hàng transaction theo thứ tự COMMIT.
- Transaction A có thể nhận ID nhỏ trước, transaction B nhận ID lớn sau nhưng commit trước.
- Giá trị sequence thường không rollback; rollback, lỗi insert, cache và các thao tác khác có thể tạo gap.
- Sequence cache có thể làm thời điểm một session sử dụng giá trị không trùng với thứ tự số toàn cục.
- ORDER BY ID chỉ sắp xếp theo giá trị ID; không cho biết thứ tự commit.
- Không dùng MAX(ID) để lấy ID của dòng vừa insert; dùng RETURNING, OUTPUT, LAST_INSERT_ID hoặc RETURNING INTO phù hợp với DBMS.
- Không dùng ID tự tăng làm watermark CDC nếu transaction có thể commit đảo thứ tự.
- Timestamp ghi lúc bắt đầu hoặc trong câu lệnh không nhất thiết là commit timestamp.
- Dùng version theo aggregate, counter transactional, outbox hoặc CDC khi cần thứ tự nghiệp vụ hay thứ tự thay đổi đã commit.
- UUID/ULID có thể hỗ trợ sinh ID phân tán hoặc sắp xếp gần theo thời điểm tạo, nhưng vẫn không bảo đảm thứ tự COMMIT.

Sequence giúp nhiều transaction lấy ID an toàn mà không cần ứng dụng tự khóa một bộ đếm. Chính sự độc lập đó làm cho việc cấp số có thể diễn ra nhanh và song song, nhưng cũng có nghĩa mã số không thể thay thế thông tin về thời điểm commit. Hãy dùng ID để nhận diện bản ghi và dùng một cơ chế có semantics rõ ràng khi nghiệp vụ cần thứ tự.

