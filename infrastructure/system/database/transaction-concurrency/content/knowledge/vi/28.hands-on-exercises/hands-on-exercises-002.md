# Chọn cơ chế bảo vệ cho từng bất biến từ đơn giản đến nhiều hàng

Một bất biến nghiệp vụ (business invariant) là điều kiện dữ liệu phải luôn đúng sau mỗi transaction được commit. Ví dụ: mã khách hàng không được trùng, số lượng tồn kho không âm, một booking không được chiếm cùng tài nguyên trong hai khoảng thời gian chồng lấn, hoặc mỗi ca trực phải còn ít nhất một nhân viên.

Cơ chế bảo vệ phù hợp phụ thuộc vào **phạm vi của bất biến** và **cách các transaction có thể xung đột**. Nếu điều kiện chỉ liên quan đến một hàng, một CHECK constraint hoặc câu UPDATE có điều kiện thường đủ. Nếu điều kiện liên quan đến nhiều hàng, một truy vấn kiểm tra rồi ghi riêng có thể bị race condition; cần một cơ chế đồng bộ hóa phạm vi dữ liệu đó, chẳng hạn guard row, khóa phạm vi, SERIALIZABLE hoặc mô hình dữ liệu khác.

Bài này đi từ các bất biến đơn giản đến các bất biến nhiều hàng. Với mỗi trường hợp, hãy xác định dữ liệu nào phải cùng thay đổi, hai transaction có thể cùng nhìn thấy điều gì, cơ chế nào thực sự bảo vệ điều kiện và cách kiểm chứng bằng nhiều session.

## 1. Bắt đầu bằng cách viết bất biến thật rõ

Trước khi chọn khóa hoặc isolation level, hãy diễn đạt điều kiện bằng một câu có thể kiểm tra.

Ví dụ:

| Nghiệp vụ | Bất biến |
|---|---|
| Tạo tài khoản | account_id là duy nhất |
| Tạo username | Username không trùng trong cùng tenant |
| Tồn kho | available_quantity luôn lớn hơn hoặc bằng 0 |
| Đặt chỗ | Số chỗ đã giữ không vượt capacity |
| Chuyển tiền | Số dư tài khoản không âm; hai phía chuyển tiền cùng commit |
| Lịch trực | Mỗi ca luôn có ít nhất một nhân viên đang trực |
| Ngân sách | Tổng phân bổ không vượt ngân sách được duyệt |
| Booking theo thời gian | Hai booking đang hoạt động không chồng lấn trên cùng tài nguyên |

Một bất biến nên trả lời được bốn câu hỏi:

1. **Phạm vi**: điều kiện áp dụng cho một hàng, một aggregate, một nhóm hàng, một tenant hay toàn hệ thống?
2. **Thời điểm**: điều kiện phải đúng sau từng statement, sau mỗi transaction commit hay trong toàn bộ vòng đời nghiệp vụ?
3. **Tập writer**: mọi service, batch, admin tool và import job nào có thể thay đổi dữ liệu này?
4. **Hành vi khi xung đột**: transaction thứ hai phải chờ, bị từ chối, đọc lại dữ liệu hay retry toàn bộ?

Nếu chưa xác định được phạm vi, rất dễ chọn một khóa quá hẹp và vẫn để lọt race condition.

### Phân biệt invariant với validation

Validation ở application kiểm tra yêu cầu đầu vào và đưa ra thông báo thân thiện. Invariant là điều kiện dữ liệu phải giữ dù thay đổi đến từ API, worker, script quản trị hay một service khác.

Ví dụ, kiểm tra trong Java rằng quantity không âm là hữu ích, nhưng hai request đồng thời vẫn có thể cùng đọc một quantity cũ và cùng quyết định giảm. Database cần có điều kiện ghi nguyên tử hoặc constraint để bảo vệ dữ liệu tại điểm commit.

Một hệ thống tốt thường có nhiều lớp: validation để phản hồi sớm, transaction/locking để phối hợp thao tác đồng thời và constraint để từ chối trạng thái không hợp lệ.

## 2. Bất biến trên một hàng: dùng constraint trước

Khi điều kiện chỉ phụ thuộc vào giá trị của một hàng, constraint thường là cơ chế rõ ràng và đáng tin cậy nhất.

Ví dụ bảng tài khoản:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    email VARCHAR(320) NOT NULL UNIQUE,
    balance DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_accounts_balance_nonnegative
        CHECK (balance >= 0)
);
~~~

Các ràng buộc có ý nghĩa khác nhau:

- PRIMARY KEY bảo đảm định danh hàng duy nhất.
- UNIQUE bảo đảm không có hai hàng cùng giá trị khóa duy nhất.
- NOT NULL bảo đảm trường bắt buộc không bị bỏ trống.
- CHECK bảo đảm biểu thức trên hàng thỏa điều kiện.
- FOREIGN KEY bảo đảm tham chiếu đến hàng cha hợp lệ theo quy tắc constraint.

Constraint được database thực thi cho mọi đường ghi tuân theo constraint, kể cả khi ứng dụng có lỗi hoặc có nhiều writer đồng thời.

### UNIQUE bảo vệ cuộc đua tạo bản ghi

Một cách không an toàn là kiểm tra username trước rồi mới INSERT:

~~~sql
SELECT COUNT(*)
FROM users
WHERE tenant_id = :tenant_id
  AND username = :username;

-- Nếu count = 0 thì INSERT.
~~~

Hai transaction có thể cùng thấy count bằng 0 rồi cùng INSERT. Kiểm tra SELECT không khóa được một giá trị chưa tồn tại theo cách portable và đáng tin cậy.

Hãy đặt UNIQUE constraint theo đúng phạm vi nghiệp vụ:

~~~sql
ALTER TABLE users
ADD CONSTRAINT uq_users_tenant_username
UNIQUE (tenant_id, username);
~~~

Sau đó INSERT trực tiếp. Nếu hai request cùng tạo một username trong cùng tenant, database chỉ cho một request commit; request còn lại nhận unique violation và ứng dụng chuyển thành phản hồi “username đã được sử dụng”.

Không cần giữ một transaction dài chỉ để SELECT kiểm tra trước. Có thể vẫn kiểm tra sớm để cải thiện trải nghiệm, nhưng UNIQUE constraint mới là lớp bảo vệ cuối cùng.

### CHECK chỉ kiểm tra dữ liệu trong phạm vi hàng

Ví dụ:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_quantity
CHECK (available_quantity >= 0);
~~~

CHECK phù hợp cho điều kiện một hàng. Hầu hết DBMS không cho dùng CHECK constraint thông thường để truy vấn tổng hợp nhiều hàng hoặc đọc bảng khác. Không thể dựa vào CHECK kiểu “SUM(order_lines.quantity) <= warehouse.capacity” như một constraint hàng đơn giản.

Khi điều kiện vượt ra ngoài một hàng, cần thiết kế cơ chế ở các phần sau.

## 3. Bất biến trên một hàng nhưng có nhiều writer: cập nhật nguyên tử

Giả sử tồn kho hiện tại là 5. Hai request cùng muốn lấy 4 sản phẩm.

Cách sai:

~~~text
A đọc available = 5
B đọc available = 5
A kiểm tra 5 >= 4
B kiểm tra 5 >= 4
A ghi available = 1
B ghi available = 1
~~~

Cả hai request có thể được chấp nhận dù tổng lượng đã giữ là 8. Một lần giảm bị ghi đè và nghiệp vụ oversell xảy ra.

Đưa điều kiện và phép cập nhật vào cùng một statement:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
~~~

Kiểm tra số hàng bị ảnh hưởng:

- Một hàng: đã giữ được số lượng yêu cầu.
- Không hàng: sản phẩm không tồn tại hoặc không còn đủ số lượng.

Có thể phân biệt hai trường hợp bằng một truy vấn bổ sung nếu cần thông báo riêng, nhưng quyết định giữ hàng phải dựa trên UPDATE có điều kiện. CHECK constraint không âm là lớp bảo vệ bổ sung.

### Vì sao atomic UPDATE đủ cho trường hợp này?

Hai transaction cùng cập nhật một hàng phải được DBMS phối hợp qua khóa ghi hoặc cơ chế tương đương. Transaction thứ hai đánh giá điều kiện trên trạng thái có hiệu lực khi nó được phép cập nhật. Nếu transaction đầu đã giảm số lượng, điều kiện của transaction sau có thể không còn đúng.

Điểm quan trọng là biểu thức sử dụng giá trị trong database:

~~~sql
SET available_quantity = available_quantity - :quantity
~~~

Không gửi một giá trị tuyệt đối được tính từ lần SELECT cũ.

### Một câu lệnh có thể thay thế SELECT rồi UPDATE

Nếu chỉ cần giảm tồn kho khi đủ hàng, hãy dùng UPDATE có điều kiện. Nếu cần kiểm tra thêm nhiều quy tắc hoặc ghi nhiều bảng, giữ các thao tác trong cùng transaction và bảo đảm quyết định quan trọng được bảo vệ bằng điều kiện/khóa phù hợp.

## 4. Bất biến trên một hàng với thao tác đọc rồi sửa: optimistic locking

Không phải lúc nào ứng dụng cũng chỉ cộng hoặc trừ một giá trị. Ví dụ người dùng mở tài liệu, chỉnh sửa trong vài phút rồi lưu. Trong thời gian đó, người khác có thể đã sửa cùng tài liệu.

Giữ khóa database trong suốt thời gian người dùng suy nghĩ là không phù hợp. Dùng version column để phát hiện bản ghi đã thay đổi.

~~~sql
CREATE TABLE documents (
    document_id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
~~~

Khi đọc, ứng dụng lấy version hiện tại. Khi ghi:

~~~sql
UPDATE documents
SET title = :new_title,
    body = :new_body,
    version = version + 1
WHERE document_id = :document_id
  AND version = :version_read;
~~~

Nếu UPDATE ảnh hưởng một hàng, bản sửa dựa trên version hiện tại đã được chấp nhận. Nếu không có hàng nào, tài liệu đã bị thay đổi hoặc bị xóa. Ứng dụng trả conflict để người dùng tải lại, hợp nhất thay đổi hoặc quyết định ghi đè theo chính sách.

### Optimistic locking bảo vệ điều gì?

Nó phát hiện hai writer cùng dựa trên một version cũ. Nó không tự bảo vệ bất biến tổng hợp nhiều hàng. Nếu một quyết định dựa trên tổng của nhiều bản ghi, chỉ version của một hàng không đủ trừ khi hàng đó đại diện cho toàn bộ invariant.

### Khi nào optimistic locking phù hợp?

- Xung đột hiếm.
- Transaction ngắn.
- Người dùng chỉnh sửa dữ liệu trong thời gian dài.
- Có thể yêu cầu client đọc lại và giải quyết conflict.
- Không cần khóa tài nguyên trong lúc client chưa gửi lệnh lưu.

Không tự động retry ghi đè với version mới nếu dữ liệu mới chưa được đọc và logic nghiệp vụ chưa được tính lại. Retry mù có thể biến optimistic locking thành lost update trá hình.

## 5. Bất biến một hàng với nhiều bước đọc/ghi: pessimistic locking

Một số use case cần đọc một hàng, kiểm tra nhiều điều kiện rồi mới quyết định cập nhật. Nếu xung đột thường xuyên hoặc không thể tính lại dễ dàng, transaction có thể khóa hàng trước khi đọc.

PostgreSQL:

~~~sql
BEGIN;

SELECT available_quantity
FROM inventory
WHERE product_id = :product_id
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.

UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id;

COMMIT;
~~~

SQL Server có thể dùng update lock:

~~~sql
BEGIN TRANSACTION;

SELECT AvailableQuantity
FROM dbo.Inventory WITH (UPDLOCK)
WHERE ProductId = @ProductId;

-- Kiểm tra và cập nhật trong cùng transaction.

UPDATE dbo.Inventory
SET AvailableQuantity = AvailableQuantity - @Quantity
WHERE ProductId = @ProductId;

COMMIT TRANSACTION;
~~~

Tên cú pháp và semantics khác nhau giữa DBMS. Với MySQL InnoDB có thể dùng locking read phù hợp như SELECT ... FOR UPDATE. Cần xác định isolation level và index để biết chính xác phạm vi khóa.

### Khóa hàng không thay thế constraint

Ngay cả khi application dùng SELECT FOR UPDATE, vẫn nên giữ CHECK/UNIQUE/FK phù hợp. Có thể có đường ghi khác không dùng đúng giao thức. Constraint bảo vệ invariant tại database.

### Giữ transaction ngắn

Không gọi HTTP, chờ người dùng hoặc publish message trong lúc giữ khóa. Chỉ thực hiện các thao tác cần thiết rồi commit/rollback.

## 6. Nhiều hàng nhưng cùng một aggregate: bảo vệ bằng transaction và khóa có thứ tự

Chuyển tiền là ví dụ kinh điển. Một giao dịch phải trừ tiền từ tài khoản nguồn và cộng vào tài khoản đích. Hai thay đổi phải cùng commit hoặc cùng rollback.

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :source_id
  AND balance >= :amount;

-- Nếu không cập nhật đúng một hàng, hủy transaction.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :destination_id;

COMMIT;
~~~

Nếu bước cộng tiền thất bại, transaction rollback bước trừ tiền. CHECK balance >= 0 tiếp tục bảo vệ từng hàng.

Khi nhiều transaction chuyển tiền theo hai chiều ngược nhau, thứ tự khóa có thể gây deadlock:

~~~text
A: khóa tài khoản 10, sau đó yêu cầu 20
B: khóa tài khoản 20, sau đó yêu cầu 10
~~~

Một quy ước phổ biến là khóa các account theo ID tăng dần, bất kể chiều chuyển tiền. Cả hai code path truy cập cùng tập account theo cùng thứ tự:

~~~text
Transaction A: account 10 -> account 20
Transaction B: account 10 -> account 20
~~~

Một transaction có thể chờ ở account đầu tiên, nhưng vòng chờ do thứ tự ngược nhau được loại bỏ cho tập tài nguyên đó.

Nếu dùng UPDATE riêng lẻ, execution plan và DBMS vẫn quyết định thứ tự lấy khóa bên trong statement. Khi cần bảo đảm thứ tự rõ ràng, có thể khóa các hàng theo thứ tự ổn định bằng locking read trong transaction rồi cập nhật. Cần kiểm thử trên đúng DBMS và index.

### Bất biến liên bảng cần commit cùng nhau

Các hàng account và transfer ledger nên được cập nhật trong cùng transaction:

~~~sql
BEGIN;

-- Trừ nguồn có điều kiện.
-- Cộng đích.
-- Ghi transfer record và ledger entries.

COMMIT;
~~~

Không commit từng repository riêng. Nếu số dư đã thay đổi nhưng ledger không có record tương ứng, hệ thống không thể đối soát chính xác.

## 7. Nhiều hàng theo predicate: nguy cơ write skew

Một bất biến có thể phụ thuộc vào tập hàng thỏa một điều kiện, chứ không chỉ một hàng cụ thể.

Ví dụ lịch trực: mỗi ca phải có ít nhất một nhân viên đang trực.

Dữ liệu ban đầu:

| Nhân viên | Đang trực |
|---|---|
| An | Có |
| Bình | Có |

Hai transaction chạy đồng thời:

~~~text
A đọc: có 2 người đang trực
B đọc: có 2 người đang trực

A tắt trạng thái trực của An
B tắt trạng thái trực của Bình

A commit
B commit
~~~

A và B sửa hai hàng khác nhau. Nếu mỗi transaction chỉ kiểm tra snapshot đã đọc, cả hai có thể thấy điều kiện “còn một người khác” vẫn đúng. Kết quả cuối cùng là không còn ai trực.

Đây là write skew. Khóa từng hàng mà transaction định sửa có thể không đủ, vì hai transaction không sửa cùng một hàng.

### Vì sao SELECT COUNT rồi UPDATE không đủ?

~~~sql
SELECT COUNT(*)
FROM on_call_roster
WHERE shift_id = :shift_id
  AND is_on_call = TRUE;
~~~

Sau đó ứng dụng kiểm tra count lớn hơn 1 rồi tắt một người. Hai transaction có thể cùng đếm 2 trước khi ghi. Mỗi transaction có thể sửa một hàng khác nhau và không tạo write-write conflict.

Bất biến này thuộc phạm vi toàn ca trực. Cơ chế bảo vệ phải điều phối mọi thao tác thay đổi roster trong cùng phạm vi ca.

## 8. Guard row: tạo một điểm đồng bộ cho invariant nhiều hàng

Một cách đơn giản là có một hàng đại diện cho phạm vi invariant, ví dụ một hàng cho mỗi shift. Mọi transaction thay đổi roster phải khóa hàng đó trước khi đọc/ghi danh sách nhân viên.

~~~sql
CREATE TABLE shift_guards (
    shift_id BIGINT PRIMARY KEY
);
~~~

Với PostgreSQL:

~~~sql
BEGIN;

SELECT shift_id
FROM shift_guards
WHERE shift_id = :shift_id
FOR UPDATE;

SELECT COUNT(*)
FROM on_call_roster
WHERE shift_id = :shift_id
  AND is_on_call = TRUE;

-- Kiểm tra không tắt người cuối cùng.
-- Cập nhật roster.

COMMIT;
~~~

Với SQL Server, có thể dùng UPDLOCK/HOLDLOCK trên guard row trong transaction:

~~~sql
BEGIN TRANSACTION;

SELECT ShiftId
FROM dbo.ShiftGuards WITH (UPDLOCK, HOLDLOCK)
WHERE ShiftId = @ShiftId;

-- Đếm người đang trực, kiểm tra invariant và cập nhật.

COMMIT TRANSACTION;
~~~

Transaction thứ hai trong cùng shift phải chờ guard row. Sau khi transaction đầu commit, transaction thứ hai đọc trạng thái mới và quyết định dựa trên dữ liệu hiện tại.

### Guard row chỉ có tác dụng nếu mọi writer tuân thủ

Nếu một admin script hoặc batch cập nhật roster mà không khóa guard row, nó có thể phá bất biến. Quy tắc này phải được áp dụng ở mọi đường ghi: API, worker, import, admin tool và migration dữ liệu.

Có thể đóng gói thao tác trong stored procedure hoặc application service chung, hạn chế quyền ghi trực tiếp vào bảng và bổ sung audit để giảm nguy cơ bỏ qua giao thức.

Guard row là một điểm tuần tự hóa có chủ ý. Nó giảm concurrency trong cùng một shift nhưng các shift khác nhau có thể dùng guard row khác nhau và tiếp tục song song.

## 9. SERIALIZABLE: bảo vệ predicate bằng isolation

Một cách khác là dùng isolation SERIALIZABLE cho transaction có bất biến phụ thuộc tập hàng.

PostgreSQL:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM on_call_roster
WHERE shift_id = :shift_id
  AND is_on_call = TRUE;

-- Kiểm tra và cập nhật roster.

COMMIT;
~~~

PostgreSQL dùng Serializable Snapshot Isolation (SSI) để phát hiện một số cấu trúc phụ thuộc nguy hiểm. Transaction có thể bị hủy với SQLSTATE 40001 và cần retry toàn bộ transaction.

SQL Server SERIALIZABLE có thể dùng key-range locks để bảo vệ predicate theo access path và index. MySQL InnoDB dùng locking/gap/next-key behavior tùy truy vấn và isolation. Không suy luận rằng mọi DBMS triển khai SERIALIZABLE theo cùng một cách.

### Retry là một phần của thiết kế

Nếu DBMS từ chối một transaction vì serialization conflict, ứng dụng cần:

1. Rollback transaction đã lỗi.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu.
4. Tính lại quyết định nghiệp vụ.
5. Thực hiện lại toàn bộ use case nếu còn hợp lệ.
6. Dừng khi hết retry budget hoặc gặp lỗi không retry được.

Không retry riêng câu UPDATE cuối vì các SELECT và quyết định trước đó thuộc snapshot cũ.

### Guard row hay SERIALIZABLE?

| Tiêu chí | Guard row | SERIALIZABLE |
|---|---|---|
| Phạm vi đồng bộ | Một key đại diện cho aggregate | Predicate và các read/write phụ thuộc theo DBMS |
| Cách điều phối | Explicit lock trên hàng guard | Isolation engine phát hiện/khóa xung đột |
| Khả năng mở rộng | Có thể chia guard theo tenant/shift/resource | Phụ thuộc index, workload và DBMS |
| Xung đột | Transaction cùng guard phải xếp hàng | Có thể chờ hoặc bị abort để retry |
| Yêu cầu ở code | Mọi writer phải khóa guard | Transaction phải retry serialization failure |
| Dễ quan sát | Nhìn thấy hàng guard và lock | Cần hiểu serialization/dependency behavior |

Guard row phù hợp khi có một phạm vi nghiệp vụ rõ và mọi writer có thể tuân thủ giao thức. SERIALIZABLE phù hợp khi cần bảo vệ predicate phức tạp và DBMS cung cấp semantics đáng tin cậy cho workload đó. Có thể dùng cả hai khi cần, nhưng phải hiểu khóa nào bảo vệ điều kiện nào.

## 10. Bất biến tổng số không vượt ngân sách

Giả sử một dự án có ngân sách 100. Nhiều request phân bổ tiền cho các hạng mục khác nhau. Bất biến là tổng phân bổ không vượt 100.

Một cách ngây thơ:

~~~sql
SELECT SUM(amount)
FROM allocations
WHERE project_id = :project_id;

-- Nếu tổng + số mới <= budget thì INSERT.
~~~

Hai transaction có thể cùng đọc tổng là 80. A thêm 15 và B thêm 15. Cả hai thấy 95 <= 100 và cùng commit; tổng cuối là 110.

Đây là một bất biến nhiều hàng, dù mỗi transaction insert vào một hàng allocation khác nhau.

### Dùng guard row theo project

~~~sql
CREATE TABLE project_budgets (
    project_id BIGINT PRIMARY KEY,
    budget DECIMAL(19, 2) NOT NULL,
    allocated DECIMAL(19, 2) NOT NULL,
    CONSTRAINT ck_project_allocated
        CHECK (allocated >= 0 AND allocated <= budget)
);
~~~

Trong transaction tạo allocation:

~~~sql
BEGIN;

UPDATE project_budgets
SET allocated = allocated + :amount
WHERE project_id = :project_id
  AND allocated + :amount <= budget;

-- Nếu không cập nhật một hàng thì từ chối phân bổ.

INSERT INTO allocations (project_id, amount)
VALUES (:project_id, :amount);

COMMIT;
~~~

Hàng project_budgets là điểm đồng bộ cho tổng ngân sách. UPDATE có điều kiện bảo vệ giới hạn và khóa hàng project trong khi transaction thực hiện. INSERT allocation phải cùng transaction để counter và chi tiết phân bổ không lệch nhau.

Đây là một dạng materialized aggregate: allocated được lưu sẵn để quyết định nhanh. Cần bảo đảm mọi đường tạo, sửa, hủy allocation đều cập nhật allocated trong cùng transaction. Có thể thêm quy trình đối soát định kỳ giữa allocated và SUM(amount) từ bảng chi tiết.

### Chọn mô hình dữ liệu để đơn giản hóa invariant

Nếu nghiệp vụ thường xuyên cần kiểm tra tổng, một hàng aggregate có thể làm invariant dễ bảo vệ hơn nhiều so với việc quét và khóa hàng loạt. Đổi lại, hàng aggregate có thể trở thành hotspot. Có thể chia phạm vi theo project/tenant/resource nếu quy tắc nghiệp vụ cho phép.

Không phân mảnh tổng một cách tùy tiện nếu cần giới hạn toàn cục chính xác. Nếu nhiều shard tự nhận phân bổ mà không có quota được cấp trước, tổng có thể vượt ngân sách.

## 11. Bất biến không được có hai khoảng thời gian chồng lấn

Ví dụ đặt phòng họp: cùng một phòng không được có hai booking ACTIVE với khoảng thời gian giao nhau.

Điều kiện này không chỉ là UNIQUE trên room_id vì một phòng có thể có nhiều booking ở các khoảng thời gian khác nhau.

### PostgreSQL: exclusion constraint

PostgreSQL có thể dùng range type và exclusion constraint:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL
);

ALTER TABLE room_bookings
ADD CONSTRAINT ex_room_booking_no_overlap
EXCLUDE USING gist (
    room_id WITH =,
    during WITH &&
)
WHERE (status = 'ACTIVE');
~~~

Constraint này từ chối hai hàng ACTIVE có cùng room_id và khoảng thời gian giao nhau. Việc kiểm tra nằm ở database và phối hợp với các transaction đồng thời.

Cần xác định rõ khoảng thời gian đóng/mở đầu mút. Ví dụ dùng khoảng nửa mở [start, end) để booking 10:00–11:00 và 11:00–12:00 không bị xem là chồng lấn.

### SQL Server hoặc DBMS không có exclusion constraint tương đương

Có thể dùng transaction SERIALIZABLE hoặc khóa phạm vi với index phù hợp:

~~~sql
BEGIN TRANSACTION;

SELECT BookingId
FROM dbo.RoomBookings WITH (UPDLOCK, HOLDLOCK)
WHERE RoomId = @RoomId
  AND Status = 'ACTIVE'
  AND StartAt < @NewEnd
  AND EndAt > @NewStart;

IF @@ROWCOUNT = 0
BEGIN
    INSERT INTO dbo.RoomBookings
        (BookingId, RoomId, StartAt, EndAt, Status)
    VALUES
        (@BookingId, @RoomId, @NewStart, @NewEnd, 'ACTIVE');
END
ELSE
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50002, 'Room is already booked for this interval', 1;
END;

COMMIT TRANSACTION;
~~~

Đây là mẫu minh họa. Khả năng bảo vệ range phụ thuộc index, execution plan và semantics lock của DBMS. Nếu không có index phù hợp, khóa có thể rộng và chi phí cao. Nếu hai transaction cùng tìm khoảng trống, cần kiểm thử bằng hai session trên đúng engine.

Nếu DBMS không thể bảo vệ predicate theo cách đủ rõ, dùng guard row cho room_id: mọi thao tác booking của cùng phòng khóa guard row trước khi kiểm tra overlap và INSERT. UNIQUE constraint không thể tự biểu diễn toàn bộ điều kiện khoảng thời gian trong mọi hệ quản trị.

## 12. Bất biến liên bảng: dùng foreign key và transaction

Một đơn hàng phải có khách hàng hợp lệ. Đây là tham chiếu giữa bảng, nhưng database có cơ chế trực tiếp: foreign key.

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id);
~~~

Khi tạo order và các dòng hàng, cần transaction để giữ các bước bắt buộc cùng commit:

~~~sql
BEGIN;

INSERT INTO orders (order_id, customer_id, status)
VALUES (:order_id, :customer_id, 'NEW');

INSERT INTO order_lines (order_id, product_id, quantity)
VALUES
    (:order_id, :product_a, :quantity_a),
    (:order_id, :product_b, :quantity_b);

COMMIT;
~~~

Foreign key bảo vệ tham chiếu. Transaction bảo vệ đơn hàng không bị commit một phần. Hai cơ chế bổ sung cho nhau.

### Không phải mọi invariant liên bảng đều có thể giải quyết bằng FK

FK có thể bảo đảm hàng con tham chiếu hàng cha, nhưng không tự bảo đảm:

- Tổng quantity của order lines bằng order.total.
- Tổng payment không vượt order amount.
- Mỗi order chỉ có một payment thành công.
- Tổng reservation không vượt capacity.

Với từng điều kiện, cần chọn UNIQUE, CHECK trên aggregate row, atomic update, guard row, SERIALIZABLE hoặc một mô hình dữ liệu phù hợp.

## 13. Bảo vệ nhiều tài nguyên theo tenant hoặc partition

Phạm vi invariant có thể là toàn tenant, không phải toàn hệ thống.

Ví dụ mỗi tenant có quota 10.000 request mỗi ngày. Dùng một counter row với khóa (tenant_id, quota_date) và UPDATE có điều kiện:

~~~sql
UPDATE tenant_daily_quotas
SET used = used + :cost
WHERE tenant_id = :tenant_id
  AND quota_date = :quota_date
  AND used + :cost <= quota_limit;
~~~

Một tenant có thể trở thành điểm nóng nếu mọi request cập nhật cùng hàng. Nhưng các tenant khác nhau có hàng khác nhau và có thể xử lý song song.

Khi chia phạm vi, hãy xác định khóa tổng hợp phản ánh đúng invariant:

- Tenant + ngày.
- Warehouse + product.
- Room + ngày hoặc room guard.
- Project + budget period.
- Account ID.
- Shift ID.

Nếu quota toàn hệ thống, không thể chỉ chia counter theo worker rồi cộng sau mà vẫn hứa không bao giờ vượt quota. Có thể cấp trước quota con cho từng worker/partition, rồi bảo đảm tổng quota đã phân bổ không vượt giới hạn toàn cục.

## 14. Dùng constraint, lock và isolation cùng nhau

Các cơ chế không loại trừ nhau. Thường cần kết hợp nhiều lớp:

| Lớp | Vai trò | Ví dụ |
|---|---|---|
| Schema constraint | Từ chối trạng thái không hợp lệ | PK, UNIQUE, CHECK, FK |
| Atomic statement | Gộp kiểm tra và thay đổi thành một thao tác | UPDATE quantity có điều kiện |
| Optimistic concurrency | Phát hiện dữ liệu đã đổi từ lúc đọc | Version column / rowversion |
| Pessimistic lock | Tuần tự hóa writer trên tài nguyên xác định | FOR UPDATE, UPDLOCK |
| Guard row | Đại diện cho phạm vi invariant nhiều hàng | Một guard cho mỗi shift/project |
| Isolation level | Điều phối hoặc phát hiện các phụ thuộc transaction | SERIALIZABLE, SNAPSHOT |
| Transaction boundary | Giữ nhiều thay đổi cùng commit | Order + lines + inventory |
| Idempotency | Ngăn request/message lặp tạo hiệu ứng lặp | Unique operation key, inbox |

Ví dụ giữ tồn kho:

- UPDATE có điều kiện quyết định có đủ hàng không.
- CHECK bảo vệ quantity không âm.
- Transaction ghi reservation cùng với cập nhật inventory.
- UNIQUE(operation_id) ngăn request retry tạo reservation trùng.
- Outbox ghi sự kiện yêu cầu giao hàng cùng transaction nếu cần publish.

Mỗi lớp có một nhiệm vụ. Đừng thêm khóa chỉ để thay thế một constraint mà database có thể bảo đảm trực tiếp.

## 15. Chọn giữa pessimistic locking và optimistic concurrency

| Câu hỏi | Pessimistic locking | Optimistic concurrency |
|---|---|---|
| Khi nào phát hiện xung đột? | Trước hoặc trong lúc truy cập khóa | Khi UPDATE/COMMIT kiểm tra version |
| Hành vi khi cạnh tranh | Transaction chờ khóa | Một transaction có thể bị từ chối |
| Phù hợp khi | Xung đột thường xuyên, critical section ngắn | Xung đột hiếm, đọc nhiều, ghi ít |
| Chi phí chính | Lock wait, deadlock, giữ connection | Retry/reload và xử lý conflict |
| Rủi ro | Transaction giữ khóa lâu | Client retry mù gây ghi đè |
| Cần constraint? | Có | Có |

Không có lựa chọn tốt nhất cho mọi hệ thống. Đo tỷ lệ xung đột, thời gian transaction và độ nhạy nghiệp vụ. Với dữ liệu do người dùng chỉnh sửa, optimistic locking thường phù hợp. Với một hàng quota nóng cần quyết định tức thời, atomic UPDATE hoặc pessimistic lock có thể phù hợp hơn.

## 16. Chọn guard row hay khóa trực tiếp tất cả hàng?

Khi invariant phụ thuộc nhiều hàng, có hai hướng phổ biến.

**Khóa trực tiếp các hàng liên quan** khi tập hàng đã biết trước và có thể khóa theo thứ tự ổn định. Ví dụ chuyển tiền giữa hai account cụ thể.

**Khóa guard row** khi invariant thuộc một nhóm hoặc predicate mà tập hàng thay đổi theo thời gian. Ví dụ “còn ít nhất một người trực trong shift” hoặc “tổng phân bổ của project không vượt budget”.

Guard row đơn giản hóa phạm vi đồng bộ, nhưng tạo một điểm tuần tự hóa cho mọi writer trong cùng nhóm. Chia guard theo phạm vi nghiệp vụ nếu có thể, không chia nhỏ hơn mức invariant cho phép.

### Ví dụ so sánh

| Bất biến | Khóa trực tiếp | Guard row |
|---|---|---|
| Chuyển tiền giữa hai tài khoản | Khóa hai account theo ID tăng dần | Không cần guard riêng nếu hai account đã là tài nguyên chính |
| Không tắt người trực cuối cùng | Khó biết hàng nào sẽ là hàng cuối nếu chỉ khóa người được sửa | Một guard theo shift |
| Tổng phân bổ project không vượt budget | Phải khóa/serialize tập allocation rộng | Một budget row theo project |
| Booking không overlap theo phòng | Khóa range theo index nếu DBMS hỗ trợ | Một guard theo room |

Nếu dùng guard row, phải bảo đảm hàng guard tồn tại. Nếu không có hàng để khóa, hai transaction có thể cùng không khóa được gì rồi tiếp tục. Tạo guard trước khi cho phép ghi, hoặc dùng thao tác upsert/insert có constraint để bảo đảm một hàng guard duy nhất.

## 17. Khi nào dùng SERIALIZABLE?

Dùng SERIALIZABLE khi logic cần một kết quả tương đương với việc các transaction chạy tuần tự và các cơ chế đơn giản hơn không đủ bảo vệ predicate/invariant.

Ví dụ:

- Kiểm tra không tồn tại booking chồng lấn rồi INSERT.
- Đếm số reservation trước khi chấp nhận reservation mới.
- Kiểm tra tổng hạn mức trên nhiều hàng.
- Đọc một tập hàng rồi cập nhật các hàng khác nhau dựa trên kết quả đọc.

Tuy nhiên, SERIALIZABLE có chi phí:

- Có thể tăng lock wait hoặc transaction abort.
- Có thể cần index để khóa phạm vi hợp lý.
- Cần retry toàn bộ transaction khi DBMS báo serialization failure.
- Transaction dài làm tăng khả năng xung đột.
- Hành vi và lỗi cụ thể khác nhau giữa DBMS.

Chỉ nâng isolation level cho phạm vi cần thiết nếu framework/DBMS cho phép. Không dùng SERIALIZABLE toàn ứng dụng như một cách thay thế việc xác định invariant.

## 18. Khi nào cần mô hình hóa lại dữ liệu?

Đôi khi bất biến khó bảo vệ vì trạng thái được phân tán trên quá nhiều hàng hoặc bảng. Có thể thay đổi mô hình để biến điều kiện phức tạp thành một thao tác nguyên tử trên một hàng.

Ví dụ, thay vì mỗi lần đặt chỗ quét tất cả reservation để đếm số chỗ còn lại, lưu capacity và reserved_count trên hàng event. UPDATE có điều kiện tăng reserved_count nếu còn chỗ, rồi INSERT reservation trong cùng transaction.

Tương tự, project budget có thể lưu allocated tổng hợp trên hàng project. Mỗi allocation cập nhật hàng đó trước khi tạo detail.

Đây là denormalization có chủ đích. Cần có:

- Một nguồn chuẩn rõ ràng.
- Mọi đường ghi cập nhật aggregate trong cùng transaction.
- CHECK constraint trên aggregate row.
- Unique key cho operation để chống duplicate.
- Job đối soát hoặc cách rebuild từ dữ liệu chi tiết.
- Theo dõi hotspot nếu một hàng aggregate có nhiều writer.

Không thêm counter dẫn xuất nếu không có kế hoạch giữ đồng bộ và phục hồi nó.

## 19. Bảo vệ invariant khi có trigger hoặc nhiều service writer

Một constraint ở database có thể áp dụng cho mọi writer. Nhưng một giao thức chỉ nằm trong application code, như “luôn khóa guard row trước khi cập nhật”, có thể bị bỏ qua bởi:

- Một service cũ.
- Batch import.
- Stored procedure khác.
- Admin script.
- Migration hoặc data repair job.

Cần lập danh sách writer cho từng bảng/aggregate và chọn nơi thực thi phù hợp.

Các lựa chọn:

- Giới hạn quyền ghi trực tiếp và chỉ cho phép gọi stored procedure.
- Dùng application service/repository chung làm entry point.
- Dùng constraint để bảo vệ điều kiện mà schema biểu diễn được.
- Dùng trigger chỉ khi semantics và locking của trigger được hiểu rõ, có kiểm thử concurrency.
- Ghi audit để phát hiện đường ghi ngoài giao thức.

Trigger không tự động làm một truy vấn tổng hợp nhiều hàng trở nên an toàn. Nếu trigger thực hiện COUNT rồi kiểm tra, nó vẫn có thể gặp race condition trừ khi dùng khóa/isolation phù hợp.

## 20. Retry phải phù hợp với cơ chế bảo vệ

Khi transaction bị từ chối hoặc hủy do xung đột, retry cần tuân theo loại lỗi.

| Kết quả | Cách xử lý |
|---|---|
| UNIQUE violation | Thường là xung đột nghiệp vụ đã tồn tại; trả kết quả phù hợp, không retry mù |
| CHECK/FK violation | Dữ liệu hoặc logic không hợp lệ; sửa đầu vào/logic |
| Optimistic version conflict | Đọc lại và yêu cầu hợp nhất hoặc tính lại |
| Deadlock victim | Có thể retry toàn transaction với backoff/jitter nếu operation idempotent |
| Serialization failure | Rollback và chạy lại toàn transaction trên snapshot mới |
| Lock timeout | Phân tích blocker; retry có giới hạn nếu nghiệp vụ cho phép |
| Không đủ tồn kho/quota | Kết quả nghiệp vụ từ chối, không retry liên tục |
| Duplicate message | Deduplicate bằng event ID/inbox |

Không retry mọi SQLException. Một constraint violation thường là tín hiệu nghiệp vụ cần xử lý; retry cùng dữ liệu không làm nó biến mất. Retry toàn transaction khi các quyết định đọc trước đó có thể đã cũ.

## 21. Ma trận chọn cơ chế theo phạm vi bất biến

| Phạm vi invariant | Ví dụ | Cơ chế ưu tiên | Lớp bảo vệ bổ sung |
|---|---|---|---|
| Một hàng, tính duy nhất | account_id, email | PRIMARY KEY / UNIQUE | Xử lý unique violation |
| Một hàng, miền giá trị | balance >= 0 | CHECK + atomic UPDATE | Validation |
| Một hàng, nhiều writer cộng/trừ | inventory, quota | Conditional atomic UPDATE | CHECK, transaction |
| Một hàng, đọc rồi sửa | Document version | Optimistic version check | Conflict response |
| Một hàng, critical section | Claim job | Pessimistic lock/atomic status update | Lease, claim token |
| Hai hoặc vài hàng đã biết | Transfer hai account | Một transaction + khóa theo thứ tự | CHECK, ledger |
| Nhiều hàng theo aggregate | Shift, project budget | Guard row hoặc aggregate row | CHECK, audit/reconciliation |
| Predicate/range | Không có booking overlap | Exclusion constraint hoặc SERIALIZABLE/range lock | Index, UNIQUE nếu áp dụng |
| Nhiều bảng cùng use case | Order + lines + inventory | Transaction boundary | FK, CHECK, UNIQUE, outbox |
| Nhiều service/database | Order → inventory → payment | Saga và transaction cục bộ | Outbox, idempotency |

## 22. Bài tập tổng hợp: chọn cơ chế và giải thích trade-off

Với mỗi tình huống, hãy xác định phạm vi invariant, hai transaction có thể xung đột ở đâu, cơ chế bảo vệ và cách kiểm thử.

### Bài 1 — Username duy nhất theo tenant

Hai request đồng thời tạo cùng username trong một tenant.

**Gợi ý cơ chế:** UNIQUE(tenant_id, username). Không dựa vào SELECT COUNT trước INSERT. Test hai connection cùng INSERT và xác nhận chỉ một transaction commit.

### Bài 2 — Tồn kho không âm

Hai request cùng mua số lượng lớn hơn tổng hàng hiện có.

**Gợi ý cơ chế:** UPDATE có điều kiện trên inventory row, CHECK quantity >= 0 và ghi reservation trong cùng transaction. Kiểm tra tổng reservation sau nhiều request đồng thời.

### Bài 3 — Tài liệu bị sửa đồng thời

Hai người mở cùng document, mỗi người chỉnh sửa rồi lưu.

**Gợi ý cơ chế:** version column/rowversion và UPDATE có điều kiện theo version đã đọc. Request thứ hai nhận conflict và cần đọc lại hoặc hợp nhất.

### Bài 4 — Chuyển tiền giữa hai account

Hai transfer chạy ngược chiều giữa cùng cặp account.

**Gợi ý cơ chế:** một transaction cho debit, credit và ledger; kiểm tra số dư bằng UPDATE có điều kiện; khóa account theo thứ tự ID thống nhất để giảm deadlock. Kiểm tra tổng số dư và ledger sau stress test.

### Bài 5 — Mỗi ca phải có ít nhất một người trực

Hai transaction cùng tắt hai người khác nhau.

**Gợi ý cơ chế:** guard row theo shift hoặc SERIALIZABLE với semantics phù hợp. Test write skew bằng hai session cùng đọc roster trước khi ghi.

### Bài 6 — Tổng phân bổ không vượt ngân sách

Hai request tạo allocation trên hai hàng detail khác nhau.

**Gợi ý cơ chế:** budget/aggregate row với UPDATE có điều kiện và detail INSERT trong cùng transaction; hoặc SERIALIZABLE nếu kiểm tra SUM trực tiếp. Đối soát aggregate với SUM detail.

### Bài 7 — Không có booking chồng lấn

Hai request đặt cùng phòng ở hai khoảng thời gian giao nhau.

**Gợi ý cơ chế:** exclusion constraint nếu DBMS hỗ trợ; nếu không, SERIALIZABLE/range lock hoặc guard row theo room. Test hai request cùng kiểm tra khoảng trống trước khi INSERT.

### Bài 8 — Một message chỉ tạo một payment attempt

Broker giao cùng event nhiều lần hoặc hai consumer nhận cùng lúc.

**Gợi ý cơ chế:** UNIQUE idempotency key/event ID, ghi inbox và payment attempt trong cùng transaction; side effect provider dùng idempotency key riêng. Test redelivery và crash window.

### Cách trình bày lời giải

Với mỗi bài, ghi:

1. Bất biến bằng một câu chính xác.
2. Phạm vi hàng/aggregate/predicate cần bảo vệ.
3. Hai transaction có thể cùng đọc hoặc ghi điều gì?
4. Constraint nào có thể biểu diễn điều kiện?
5. Nếu cần khóa, khóa resource nào và trong bao lâu?
6. Isolation level hoặc retry nào cần thiết?
7. Những writer nào phải tuân thủ giao thức?
8. Test hai session nào chứng minh cơ chế hoạt động?
9. Metric nào cho thấy contention khi tải tăng?
10. Cách đối soát nếu dữ liệu đã bị sai.

## 23. Quy trình chọn cơ chế từ đơn giản đến nhiều hàng

1. **Viết invariant**: diễn đạt điều kiện thành câu và công thức nếu có.
2. **Xác định phạm vi**: một hàng, nhiều hàng đã biết, aggregate, predicate/range hay nhiều service.
3. **Tìm constraint trực tiếp**: PK, UNIQUE, CHECK, FK hoặc exclusion constraint.
4. **Ưu tiên atomic DML**: gộp kiểm tra và cập nhật trong một statement nếu có thể.
5. **Chọn concurrency control**: optimistic version, row lock, guard row hoặc SERIALIZABLE.
6. **Xác định transaction boundary**: các thay đổi nào phải cùng commit/rollback?
7. **Lập danh sách mọi writer**: API, worker, batch, admin, import và script.
8. **Định nghĩa conflict behavior**: chờ, từ chối, reload hay retry toàn transaction?
9. **Kiểm thử lịch cạnh tranh**: dùng hai connection độc lập và mốc đồng bộ.
10. **Kiểm tra constraint và invariant cuối**: đọc bằng connection mới sau khi transaction kết thúc.
11. **Đo trade-off**: lock wait, deadlock, abort, retry, latency và throughput.
12. **Chuẩn bị phục hồi**: audit, reconciliation, rebuild aggregate và idempotency.

## 24. Những sai lầm thường gặp

### Dùng validation ở application làm lớp bảo vệ duy nhất

Hai request có thể cùng vượt qua validation dựa trên cùng một trạng thái cũ. Cần constraint hoặc thao tác nguyên tử ở database.

### Dùng SELECT rồi INSERT để bảo đảm uniqueness

Hai transaction có thể cùng thấy chưa tồn tại. Dùng UNIQUE constraint và xử lý xung đột.

### Dùng CHECK cho điều kiện tổng hợp nhiều hàng

CHECK thường chỉ bảo vệ biểu thức của hàng hiện tại. Dùng guard/aggregate row, exclusion constraint hoặc isolation phù hợp.

### Khóa mỗi hàng mà quên predicate

Hai transaction sửa hai hàng khác nhau vẫn có thể phá invariant tổng hợp. Cần khóa phạm vi, guard row hoặc SERIALIZABLE.

### Dùng SERIALIZABLE mà không retry

DBMS có thể từ chối transaction để giữ tính tuần tự. Nếu không xử lý serialization failure, request chỉ chuyển thành lỗi người dùng.

### Có guard row nhưng một writer bỏ qua

Một batch hoặc script ghi trực tiếp có thể phá invariant. Mọi đường ghi phải dùng cùng giao thức hoặc bị constraint bảo vệ.

### Denormalize aggregate mà không có đối soát

Counter lưu sẵn có thể lệch với dữ liệu chi tiết nếu một đường ghi quên cập nhật. Cần transaction chung, audit và quy trình rebuild.

### Chỉ đo hiệu năng mà quên correctness

Một cơ chế ít khóa hơn chưa chắc đúng. Luôn kiểm tra invariant sau concurrency test và failure-path.

## 25. Checklist xác nhận cơ chế bảo vệ

- [ ] Bất biến được viết rõ và có phạm vi cụ thể.
- [ ] Đã xác định mọi bảng/hàng/predicate liên quan.
- [ ] Đã chọn constraint trực tiếp nếu schema có thể biểu diễn điều kiện.
- [ ] Các phép kiểm tra và cập nhật quan trọng được thực hiện nguyên tử.
- [ ] Transaction boundary bao phủ mọi thay đổi phải cùng commit.
- [ ] Lock/guard được lấy trước khi đọc dữ liệu dùng để quyết định.
- [ ] Mọi writer đều tuân thủ cùng giao thức.
- [ ] Retry xử lý đúng unique conflict, deadlock và serialization failure.
- [ ] Có test hai session tái hiện race condition.
- [ ] Có test rollback và duplicate operation/message.
- [ ] Trạng thái cuối được kiểm tra bằng connection mới.
- [ ] Có metric cho lock wait, deadlock, retry, abort và latency.
- [ ] Có cách đối soát/rebuild nếu dữ liệu dẫn xuất bị lệch.

Cơ chế bảo vệ nên theo đúng phạm vi của bất biến. Điều kiện trên một hàng thường được bảo vệ tốt nhất bằng constraint và atomic UPDATE. Thao tác đọc rồi sửa có thể cần optimistic version hoặc pessimistic lock. Bất biến nhiều hàng cần đồng bộ hóa toàn bộ phạm vi liên quan bằng guard row, SERIALIZABLE, range constraint hoặc mô hình aggregate phù hợp. Sau cùng, mọi đường ghi phải tuân thủ cùng giao thức và được kiểm tra bằng lịch hai session; một thiết kế chỉ đúng khi dữ liệu vẫn giữ invariant sau cả commit, rollback, retry và xử lý đồng thời thực tế.
