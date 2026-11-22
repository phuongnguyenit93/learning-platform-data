# Bế tắc do lấy khóa theo thứ tự khác nhau

Trong hệ thống có nhiều transaction đồng thời, một transaction có thể phải chờ khóa mà transaction khác đang giữ. Việc chờ là bình thường: DBMS cần bảo đảm các thao tác xung đột không làm dữ liệu sai. Nhưng nếu các transaction giữ những khóa khác nhau rồi chờ lẫn nhau, hệ thống có thể rơi vào **deadlock (bế tắc)**.

Một nguyên nhân rất phổ biến là các transaction lấy cùng một tập khóa theo thứ tự khác nhau. Ví dụ, transaction A khóa tài khoản 1 rồi cần tài khoản 2, trong khi transaction B khóa tài khoản 2 rồi cần tài khoản 1. A phải chờ B, còn B phải chờ A. Không bên nào có thể tiếp tục để giải phóng khóa.

Cách phòng ngừa quan trọng là quy định một thứ tự lấy khóa nhất quán cho mọi luồng xử lý có thể tranh chấp cùng tài nguyên. Nếu nhiều tài khoản cần được khóa, mọi transaction đều khóa theo account_id tăng dần. Nếu có nhiều loại tài nguyên, hệ thống cần một thứ tự tổng thể cho các loại khóa và định danh của chúng.

## 1. Deadlock hình thành như thế nào?

Một transaction thường giữ khóa cho đến khi kết thúc hoặc đến thời điểm DBMS giải phóng khóa theo ngữ nghĩa của loại khóa đó. Nếu transaction khác yêu cầu khóa xung đột, nó phải chờ.

Một tình trạng chờ đơn lẻ chưa phải deadlock. Deadlock xuất hiện khi các transaction tạo thành một vòng chờ: mỗi transaction đang giữ tài nguyên mà transaction tiếp theo cần, và transaction cuối cùng lại chờ tài nguyên do transaction đầu tiên giữ.

Ví dụ có hai hàng tài khoản:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance DECIMAL(18, 2) NOT NULL
);

INSERT INTO accounts (account_id, balance)
VALUES
    (1, 500.00),
    (2, 300.00);
~~~

Transaction A chuyển tiền từ tài khoản 1 sang tài khoản 2. Transaction B chuyển tiền theo chiều ngược lại.

| Thứ tự | Transaction A | Transaction B |
|---|---|---|
| 1 | Khóa hàng account 1 | |
| 2 | | Khóa hàng account 2 |
| 3 | Yêu cầu khóa account 2 và phải chờ B | |
| 4 | | Yêu cầu khóa account 1 và phải chờ A |
| 5 | Chờ B | Chờ A |

Hai transaction không thể tự tiến triển. A không thể nhả khóa account 1 trước khi hoàn tất; B cũng không thể nhả khóa account 2 trước khi hoàn tất. DBMS cần phát hiện vòng chờ và chọn một transaction làm nạn nhân để phá vỡ deadlock.

### Wait-for graph

DBMS có thể biểu diễn tình trạng chờ bằng đồ thị chờ (wait-for graph):

~~~text
Transaction A  ---- chờ khóa ---->  Transaction B
      ^                                  |
      |                                  |
      +----------- chờ khóa -------------+
~~~

Một cạnh A → B có nghĩa A đang chờ tài nguyên mà B giữ. Khi tồn tại chu trình, ví dụ A → B → A, hệ thống có deadlock.

Với nhiều transaction hơn, chu trình có thể dài hơn:

~~~text
A -> B -> C -> D
^               |
|_______________|
~~~

Điều kiện cốt lõi vẫn là có một vòng phụ thuộc chờ không thể tự giải quyết. DBMS thường theo dõi lock request và phát hiện chu trình trong các cấu trúc quản lý khóa của nó.

## 2. Vì sao thứ tự lấy khóa khác nhau tạo ra deadlock?

Giả sử hai transaction cùng cần cập nhật hai tài khoản:

- A lấy khóa account 1 trước, sau đó account 2.
- B lấy khóa account 2 trước, sau đó account 1.

Mỗi transaction giữ khóa đầu tiên trong khi chờ khóa thứ hai. Khi hai yêu cầu chồng lấn đúng thời điểm, vòng chờ hình thành.

Nếu cả A và B đều lấy account 1 trước rồi account 2, một transaction sẽ lấy được khóa account 1 trước. Transaction còn lại phải chờ ngay ở khóa đầu tiên, trước khi nó giữ bất kỳ khóa nào trong tập tài nguyên cần dùng. Transaction thắng có thể lấy tiếp account 2, hoàn thành và commit; sau đó transaction chờ mới tiếp tục.

Minh họa:

~~~text
Thứ tự không thống nhất:

A: lock(1) -> lock(2)
B: lock(2) -> lock(1)

Có thể tạo vòng chờ A <-> B.


Thứ tự thống nhất:

A: lock(1) -> lock(2)
B: lock(1) -> lock(2)

Một bên chờ ngay tại lock(1); không hình thành vòng chờ giữa hai transaction này.
~~~

Thứ tự thống nhất không loại bỏ mọi deadlock trong hệ thống. Một transaction còn có thể khóa bảng, index, hàng cha, hàng con hoặc tài nguyên khác theo thứ tự không nhất quán. Nhưng quy tắc thứ tự toàn cục loại bỏ một nhóm nguyên nhân deadlock rất phổ biến.

## 3. Phòng ngừa bằng thứ tự khóa nhất quán

Cách cơ bản là xác định thứ tự toàn phần (total order) cho các tài nguyên có thể bị khóa. Mọi transaction phải yêu cầu khóa theo thứ tự đó.

Ví dụ với tài khoản:

~~~text
Thứ tự khóa:
account_id tăng dần

Cần khóa account 17 và account 42:
1. Khóa account 17
2. Khóa account 42
3. Thực hiện chuyển tiền
4. Commit
~~~

Nếu transaction xử lý một tập id không cố định, hãy chuẩn hóa và sắp xếp danh sách trước khi lấy khóa. Không dựa vào thứ tự đầu vào từ HTTP request, JSON array, HashSet hoặc collection không bảo đảm thứ tự.

### Ví dụ chuyển tiền an toàn hơn

Một cách minh họa trong PostgreSQL là khóa hai hàng theo account_id tăng dần:

~~~sql
BEGIN;

SELECT account_id, balance
FROM accounts
WHERE account_id IN (1, 2)
ORDER BY account_id
FOR UPDATE;

-- Sau khi đã khóa cả hai hàng:
-- kiểm tra số dư tài khoản nguồn,
-- tính số tiền chuyển và cập nhật hai tài khoản.

UPDATE accounts
SET balance = balance - 50.00
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 50.00
WHERE account_id = 2;

COMMIT;
~~~

Transaction chuyển ngược chiều cũng phải khóa account 1 trước account 2, dù account 1 là đích và account 2 là nguồn. Thứ tự khóa được xác định theo định danh tài nguyên, không theo hướng nghiệp vụ của giao dịch.

Cú pháp khóa hàng và cách DBMS thực thi thứ tự có khác nhau. Ví dụ trên dùng cú pháp PostgreSQL; với hệ quản trị khác cần xác nhận locking read, ORDER BY và lock acquisition behavior theo tài liệu của engine. Nếu cần bảo đảm chặt chẽ trong code đa DBMS, có thể lấy khóa từng id theo thứ tự đã sắp xếp bằng các câu lệnh riêng trong cùng transaction.

### Đừng nhầm thứ tự cập nhật với thứ tự lấy khóa

Viết hai câu UPDATE theo thứ tự account_id tăng dần có thể giúp, nhưng không phải lúc nào cũng chứng minh được thứ tự khóa bên trong DBMS. Optimizer có thể chọn access path và thứ tự xử lý riêng cho câu lệnh cập nhật nhiều hàng.

Nếu tính đúng đắn của giao thức phụ thuộc thứ tự khóa, hãy chủ động khóa các hàng theo thứ tự đã định trước, hoặc dùng một cơ chế DBMS có hợp đồng rõ ràng cho locking read. Sau đó kiểm tra hành vi trên đúng DBMS và execution plan thực tế.

## 4. Thứ tự khóa phải thống nhất ở mọi đường xử lý

Một quy tắc chỉ hiệu quả nếu mọi transaction có thể tranh chấp cùng tài nguyên đều tuân thủ.

Giả sử API chuyển tiền đã khóa tài khoản theo thứ tự tăng dần, nhưng batch job đối soát lại khóa tài khoản theo thứ tự đọc từ file. Batch job vẫn có thể tạo deadlock với API.

Các luồng cần cùng quy ước có thể bao gồm:

- API chuyển tiền, hoàn tiền hoặc điều chỉnh số dư.
- Batch job tổng hợp hoặc đối soát.
- Worker xử lý message.
- Stored procedure và trigger.
- Tác vụ quản trị dữ liệu.
- Service khác dùng chung database.
- Các transaction cập nhật nhiều loại tài nguyên liên quan.

Không nên chỉ sửa một đoạn code nhìn thấy deadlock đầu tiên rồi cho rằng vấn đề đã được giải quyết. Cần truy tìm tất cả đường lấy khóa trên cùng tập tài nguyên.

### Xác định thứ tự cho nhiều loại tài nguyên

Khi transaction khóa nhiều loại đối tượng, có thể định nghĩa thứ tự theo loại trước, rồi theo id:

~~~text
1. Khóa hàng tenant
2. Khóa hàng account theo account_id tăng dần
3. Khóa hàng invoice theo invoice_id tăng dần
4. Khóa hàng ledger theo ledger_id tăng dần
~~~

Mọi luồng xử lý phải tuân thủ cùng thứ tự. Nếu một transaction cần khóa account rồi invoice, còn transaction khác khóa invoice rồi account, deadlock vẫn có thể xảy ra dù từng nhóm id đã được sắp xếp.

Quy tắc phải bao phủ toàn bộ tài nguyên có thể bị khóa trong transaction, bao gồm các khóa phát sinh gián tiếp do foreign key, unique index, trigger hoặc câu lệnh phụ.

## 5. Khóa nhiều hàng theo danh sách động

Nhiều nghiệp vụ không biết trước số hàng cần cập nhật. Ví dụ, một thao tác hợp nhất hai nhóm người dùng có thể cần khóa nhiều tài khoản, hoặc một job cần cập nhật tất cả đơn hàng thuộc một nhóm.

Hãy:

1. Xác định tập id cần thao tác.
2. Loại bỏ id trùng lặp.
3. Sắp xếp theo khóa định danh ổn định.
4. Lấy khóa theo thứ tự đó trong cùng transaction.
5. Kiểm tra số hàng thực sự tìm thấy và trạng thái hiện tại.
6. Thực hiện thay đổi rồi commit.

Pseudocode:

~~~text
ids = findResourceIdsForOperation()
ids = distinct(ids)
ids = sortAscending(ids)

begin transaction

for id in ids:
    row = select row by id for update
    if row does not exist:
        handle missing resource
    else:
        keep lock and continue

validate business rules
apply all changes
commit
~~~

Đây là pseudocode mô tả giao thức, không phải cú pháp SQL. Trong ứng dụng, việc lấy khóa từng hàng có thể tạo nhiều round trip. Nếu DBMS hỗ trợ một locking read có thứ tự rõ ràng, có thể lấy nhiều hàng trong một câu lệnh để giảm round trip. Cần đo chi phí và xác nhận thứ tự khóa thực tế.

Nếu tập id được tính từ một truy vấn có thể thay đổi trong lúc transaction chạy, cần xem xét isolation level và cách bảo vệ predicate. Sắp xếp các id đã tìm thấy không tự ngăn một hàng mới xuất hiện trong phạm vi truy vấn.

## 6. Chỉ mục và access path có thể ảnh hưởng đến deadlock

Index giúp DBMS tìm hàng nhanh hơn, nhưng execution plan cũng ảnh hưởng đến cách engine truy cập và khóa các tài nguyên.

Ví dụ, hai câu UPDATE cùng thao tác trên một tập hàng nhưng optimizer chọn hai access path khác nhau. Một câu đi theo index A rồi index B; câu kia có thể đi theo index B rồi index A. Trong một số trường hợp, các khóa trên hàng, index record hoặc page được lấy theo thứ tự khác nhau và tạo vòng chờ.

Một số điểm cần chú ý:

- UPDATE/DELETE không có index phù hợp có thể quét và kiểm tra nhiều hàng hơn dự kiến.
- Index phụ cần được duy trì khi giá trị cột index thay đổi.
- Foreign key và unique constraint có thể khiến DBMS kiểm tra hoặc khóa thêm tài nguyên.
- Trigger có thể cập nhật bảng khác và mở rộng tập khóa của transaction.
- Thay đổi thống kê hoặc index có thể làm execution plan thay đổi.
- Index hotspot có thể gây latch contention; latch contention và transaction deadlock là hai vấn đề khác nhau.

Index phù hợp thường giúp giảm công việc tìm kiếm và phạm vi tranh chấp, nhưng không thay thế quy tắc thứ tự khóa. Không dựa vào execution plan tình cờ đang có để làm giao thức đồng bộ nghiệp vụ.

## 7. Deadlock có thể xảy ra ngoài khóa hàng

Ví dụ hai tài khoản thường minh họa row lock, nhưng tài nguyên gây deadlock có thể là:

- Row/key lock.
- Table lock hoặc partition lock.
- Index record hoặc key range.
- Gap/next-key lock trong InnoDB.
- Key-range lock trong SQL Server.
- Advisory/application lock.
- Tài nguyên liên quan đến foreign key hoặc unique index.
- Một số tài nguyên nội bộ khác do DBMS quản lý.

Thứ tự khóa nhất quán nên được hiểu ở cấp tài nguyên nghiệp vụ, đồng thời cần xem deadlock graph để biết DBMS thực sự ghi nhận tài nguyên nào.

Không phải mọi tình trạng chờ đều là deadlock. Một transaction có thể chờ lâu vì transaction khác giữ khóa lâu, nhưng nếu không có vòng chờ thì đó chỉ là lock wait. Ngược lại, deadlock có thể được phát hiện và phá vỡ nhanh đến mức người dùng chỉ nhìn thấy một lỗi transaction.

## 8. DBMS phát hiện và xử lý deadlock

Các hệ quản trị thường phát hiện deadlock bằng cách kiểm tra đồ thị chờ hoặc cơ chế tương đương. Khi phát hiện chu trình, DBMS chọn một transaction làm victim để phá vòng chờ.

Thông thường, DBMS cân nhắc các yếu tố như:

- Lượng công việc transaction đã thực hiện.
- Chi phí rollback ước tính.
- Mức độ ưu tiên transaction.
- Số lượng khóa đang giữ.
- Chính sách lựa chọn victim riêng của engine.

Không nên dựa vào giả định rằng transaction bắt đầu trước luôn thắng hoặc transaction nhỏ luôn bị hủy. Quy tắc lựa chọn victim phụ thuộc DBMS và cấu hình.

### Sau khi bị chọn làm victim

Transaction bị chọn nhận lỗi deadlock. Ứng dụng cần:

1. Xác định lỗi bằng mã lỗi/SQLSTATE của driver.
2. Đưa transaction về trạng thái hợp lệ bằng rollback theo yêu cầu của DBMS.
3. Nếu nghiệp vụ cho phép, bắt đầu transaction mới và chạy lại toàn bộ thao tác.
4. Giới hạn số lần retry và thêm backoff/jitter.
5. Ghi log để phát hiện mẫu deadlock lặp lại.

Phạm vi rollback khi deadlock khác nhau giữa các DBMS. PostgreSQL đánh dấu transaction lỗi sau deadlock và yêu cầu rollback transaction; InnoDB thường chọn và rollback toàn bộ transaction victim; SQL Server thường rollback transaction victim; Oracle có thể rollback statement gây deadlock và trả ORA-00060, nên ứng dụng cần tuân thủ trạng thái transaction và hướng dẫn của Oracle. Một cách xử lý portable là rollback transaction hiện tại rồi quyết định retry toàn bộ nghiệp vụ trong transaction mới.

### Một số mã lỗi thường gặp

| DBMS | Mã lỗi thường gặp | Ý nghĩa |
|---|---|---|
| PostgreSQL | SQLSTATE 40P01 | Deadlock detected |
| MySQL InnoDB | Error 1213 / SQLSTATE 40001 | Deadlock found; transaction bị rollback |
| SQL Server | Error 1205 | Transaction bị chọn làm deadlock victim |
| Oracle | ORA-00060 | Deadlock detected while waiting for resource |

Driver có thể trình bày lỗi theo nhiều dạng. Nên phân loại bằng mã lỗi ổn định do DBMS/driver cung cấp, không chỉ dò chuỗi thông báo.

## 9. Deadlock khác lock timeout như thế nào?

Deadlock và lock timeout đều có thể khiến một câu SQL không hoàn thành, nhưng nguyên nhân khác nhau.

| Tiêu chí | Deadlock | Lock timeout |
|---|---|---|
| Nguyên nhân | Có vòng chờ giữa các transaction | Một transaction chờ khóa quá thời gian cấu hình |
| Có chu trình chờ? | Có | Không nhất thiết |
| DBMS xử lý | Phát hiện chu trình và chọn victim | Hủy hoặc báo lỗi thao tác/transaction tùy DBMS và cấu hình |
| Cách khắc phục | Sửa thứ tự lấy khóa, giảm phạm vi/giữ khóa, xử lý retry | Giảm thời gian giữ khóa, giảm contention, điều chỉnh timeout có chủ đích |
| Có thể retry? | Thường có thể nếu thao tác an toàn và retry toàn bộ transaction | Tùy lỗi, trạng thái transaction và nghiệp vụ |

Tăng lock timeout không giải quyết deadlock. Nó chỉ thay đổi thời gian chờ trước khi báo lỗi ở những trường hợp timeout. Deadlock có thể được phát hiện ngay khi DBMS xác định vòng chờ.

## 10. Ví dụ chuyển tiền với thứ tự khóa thống nhất

Một transaction chuyển tiền cần bảo đảm:

- Tài khoản nguồn tồn tại.
- Tài khoản đích tồn tại.
- Số dư nguồn đủ.
- Tổng tiền không tự mất trong quá trình chuyển.
- Hai hàng được cập nhật trong cùng transaction.

Mẫu PostgreSQL:

~~~sql
BEGIN;

-- Khóa cả hai hàng theo account_id tăng dần.
SELECT account_id, balance
FROM accounts
WHERE account_id IN (:source_id, :target_id)
ORDER BY account_id
FOR UPDATE;

-- Ứng dụng xác nhận đủ hai hàng và kiểm tra số dư nguồn.
-- Sau đó thực hiện cập nhật có điều kiện.

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :source_id
  AND balance >= :amount;

-- Kiểm tra số hàng bị ảnh hưởng là 1.
-- Nếu không, rollback và trả lỗi nghiệp vụ.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :target_id;

COMMIT;
~~~

Nếu source_id lớn hơn target_id, thứ tự khóa vẫn là account_id nhỏ trước, lớn sau. Không khóa nguồn trước chỉ vì đó là tài khoản bị trừ.

Trong code thực tế, cần xử lý trường hợp source_id và target_id trùng nhau, amount không dương, tài khoản không tồn tại và cập nhật nguồn không thành công. Nếu một câu lệnh hoặc kiểm tra thất bại, rollback toàn bộ transaction.

Nếu nhiều loại giao dịch cập nhật thêm ledger, limit hoặc audit row, hãy mở rộng thứ tự khóa cho tất cả tài nguyên đó. Nếu một trigger hoặc stored procedure khóa tài nguyên ngoài dự kiến, cần đưa nó vào phân tích deadlock.

## 11. Khi không thể kiểm soát toàn bộ thứ tự khóa

Một số hệ thống có nhiều service, stored procedure hoặc thành phần bên thứ ba cùng truy cập database. Có thể khó áp dụng ngay một thứ tự khóa toàn cục. Khi đó, cân nhắc:

### Giảm số lượng tài nguyên cùng khóa

Chia thao tác lớn thành các phần nhỏ nếu nghiệp vụ cho phép. Ít hàng được giữ đồng thời có thể giảm khả năng tạo vòng chờ. Tuy nhiên, không chia transaction nếu điều đó làm mất tính nguyên tử cần thiết của nghiệp vụ.

### Dùng guard row hoặc khóa theo tài nguyên nghiệp vụ

Nếu nhiều thao tác luôn ảnh hưởng cùng một tài nguyên logic, một hàng guard có thể làm điểm đồng bộ. Mọi transaction lấy khóa guard trước rồi mới khóa các hàng chi tiết. Giao thức này cần được tất cả đường ghi tuân thủ.

### Dùng thao tác nguyên tử

Nếu nghiệp vụ có thể biểu diễn bằng một UPDATE có điều kiện, DBMS có thể xử lý trực tiếp mà không cần ứng dụng đọc rồi khóa nhiều hàng theo cách phức tạp.

Ví dụ trừ số dư có điều kiện:

~~~sql
UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
~~~

Kiểm tra số hàng ảnh hưởng để biết thao tác có thành công. Có thể bổ sung CHECK constraint bảo vệ balance không âm. Cách này không giải quyết mọi nghiệp vụ nhiều hàng, nhưng có thể loại bỏ một số bước đọc/ghi riêng và giảm thời gian giữ khóa.

### Giữ transaction ngắn

Không gọi HTTP, gửi email, chờ message broker hoặc đợi người dùng trong khi đang giữ khóa. Thực hiện các bước tính toán không phụ thuộc trạng thái khóa trước khi mở transaction nếu có thể; trong transaction chỉ đọc/kiểm tra dữ liệu cần bảo vệ, cập nhật và commit.

### Chấp nhận deadlock có kiểm soát

Ngay cả hệ thống có thứ tự khóa tốt vẫn có thể gặp deadlock do tài nguyên nội bộ, trigger, foreign key, plan thay đổi hoặc đường ghi không được dự đoán. Ứng dụng cần có retry hữu hạn và theo dõi deadlock graph.

## 12. Kiểm thử deadlock bằng hai session

Có thể tái hiện lỗi trong môi trường thử nghiệm với hai connection độc lập.

Khởi tạo dữ liệu:

~~~sql
CREATE TABLE deadlock_demo (
    id INT PRIMARY KEY,
    value INT NOT NULL
);

INSERT INTO deadlock_demo (id, value)
VALUES (1, 100), (2, 200);
~~~

**Session A**

~~~sql
BEGIN;

UPDATE deadlock_demo
SET value = value + 1
WHERE id = 1;

-- Tạm dừng ở đây, chưa commit.
~~~

**Session B**

~~~sql
BEGIN;

UPDATE deadlock_demo
SET value = value + 1
WHERE id = 2;

-- Session B đang giữ khóa id = 2.
~~~

Tiếp tục Session A:

~~~sql
UPDATE deadlock_demo
SET value = value + 1
WHERE id = 2;

-- A chờ B.
~~~

Tiếp tục Session B:

~~~sql
UPDATE deadlock_demo
SET value = value + 1
WHERE id = 1;

-- B chờ A; DBMS có thể phát hiện deadlock.
~~~

Một transaction sẽ nhận lỗi deadlock và bị chọn làm victim. Transaction còn lại có thể tiếp tục sau khi khóa được giải phóng.

### Kiểm thử sau khi chuẩn hóa thứ tự

Chạy lại với cả hai session lấy khóa id = 1 trước rồi id = 2:

~~~sql
BEGIN;

SELECT id, value
FROM deadlock_demo
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

-- Thực hiện các thay đổi cần thiết.

COMMIT;
~~~

Cần dùng hai connection riêng và điều khiển thứ tự bằng tay hoặc bằng barrier trong test harness. Nếu chạy toàn bộ câu lệnh tuần tự trên một connection, bạn không tạo được tình huống tranh chấp.

Với DBMS không hỗ trợ cùng cú pháp ORDER BY ... FOR UPDATE, dùng cách lấy khóa theo id đã sắp xếp phù hợp với engine. Ghi nhận transaction nào chờ, resource nào bị khóa và lỗi trả về. Sau đó xác nhận trạng thái cuối vẫn đúng.

## 13. Quan sát deadlock trên môi trường thực tế

Khi có deadlock, thông báo tổng quát thường chưa đủ để tìm nguyên nhân. Cần lấy thông tin về:

- Transaction bị chọn làm victim.
- Transaction còn lại trong chu trình.
- Câu SQL đang chạy và câu SQL đã lấy khóa trước đó.
- Resource type và resource identifier.
- Index hoặc key liên quan.
- Isolation level.
- Thời điểm bắt đầu transaction và thời gian giữ khóa.
- Execution plan nếu access path có thể ảnh hưởng đến thứ tự truy cập.

Công cụ theo dõi tùy DBMS:

| DBMS | Công cụ quan sát thường dùng |
|---|---|
| PostgreSQL | Log deadlock, pg_stat_activity, pg_locks và thông tin wait event |
| MySQL InnoDB | SHOW ENGINE INNODB STATUS, Performance Schema và deadlock output |
| SQL Server | Extended Events, deadlock graph và system_health session |
| Oracle | Trace file và thông tin deadlock trong diagnostic data |

Tên view và quyền truy cập phụ thuộc phiên bản/cấu hình. Không nên chỉ tăng log toàn bộ câu SQL trong production nếu câu lệnh có thể chứa dữ liệu nhạy cảm. Ưu tiên correlation id, mã lỗi, tên nghiệp vụ và thông tin resource đủ để chẩn đoán.

## 14. Checklist thiết kế thứ tự khóa

Trước khi đưa một luồng cập nhật nhiều tài nguyên vào production, hãy xác nhận:

- [ ] Đã liệt kê toàn bộ hàng/tài nguyên mà transaction có thể khóa chưa?
- [ ] Có một thứ tự tổng thể ổn định cho loại tài nguyên và id chưa?
- [ ] Các API, worker, batch job, procedure và trigger có tuân thủ cùng thứ tự không?
- [ ] Danh sách id động có được loại trùng và sắp xếp trước khi khóa không?
- [ ] Có dựa nhầm vào thứ tự UPDATE hoặc execution plan để suy ra thứ tự khóa không?
- [ ] Transaction có giữ khóa trong lúc gọi dịch vụ ngoài hoặc chờ người dùng không?
- [ ] Có kiểm thử bằng nhiều session độc lập để tái hiện deadlock không?
- [ ] Ứng dụng phân loại deadlock, timeout và serialization failure bằng mã lỗi không?
- [ ] Retry có giới hạn và chạy lại toàn bộ transaction không?
- [ ] Side effect bên ngoài có được bảo vệ khỏi việc thực hiện lặp không?
- [ ] Có thu thập deadlock graph hoặc thông tin tương đương khi lỗi xảy ra không?

Thứ tự khóa nhất quán là một quy tắc thiết kế cần được áp dụng xuyên suốt các luồng truy cập dữ liệu. Khi mọi transaction yêu cầu các tài nguyên theo cùng một thứ tự, chúng khó tạo vòng chờ chỉ vì lấy khóa ngược chiều nhau. Kết hợp với transaction ngắn, index phù hợp, kiểm thử nhiều session và retry có kiểm soát, hệ thống sẽ giảm đáng kể deadlock do thứ tự khóa không nhất quán mà vẫn giữ được tính nguyên tử của nghiệp vụ.
