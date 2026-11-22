# Sửa ghi lệch bằng khóa tường minh hoặc cơ chế khả tuần tự

Write skew là lỗi đồng thời xảy ra khi nhiều transaction cùng đọc một trạng thái hợp lệ, sau đó ghi các hàng khác nhau và cùng COMMIT, khiến tổ hợp dữ liệu cuối vi phạm một bất biến nghiệp vụ. Snapshot isolation có thể phát hiện hai transaction cùng sửa một hàng, nhưng không nhất thiết phát hiện trường hợp chúng sửa các hàng khác nhau dựa trên cùng một snapshot.

Để sửa write skew, cần bảo vệ **quyết định nghiệp vụ chung**. Có thể làm điều đó bằng khóa tường minh trên một hàng đại diện, khóa các hàng liên quan theo thứ tự ổn định, cập nhật nguyên tử một bộ đếm, hoặc dùng cơ chế SERIALIZABLE mà DBMS thực sự cung cấp. Cơ chế được chọn phải bao phủ tất cả đường ghi có thể ảnh hưởng đến bất biến.

Bài học này dùng quy tắc “luôn có ít nhất một bác sĩ trực” làm ví dụ xuyên suốt. Ta sẽ tái hiện lịch write skew, phân tích vì sao khóa cùng hàng không tự động giải quyết mọi predicate, xây dựng guard row, so sánh khóa tường minh với SERIALIZABLE trên các DBMS và thiết kế retry/test để chứng minh lỗi đã được ngăn.

## 1. Bắt đầu từ bất biến cần bảo vệ

### 1.1. Ví dụ: luôn có ít nhất một người trực

Giả sử một nhóm có hai bác sĩ đang trực. Nghiệp vụ cho phép tắt trạng thái trực của một bác sĩ, nhưng không cho phép tắt người trực cuối cùng.

Bất biến:

\[
COUNT(\text{IsOnCall = true}) \ge 1
\]

Dữ liệu ban đầu:

| DoctorId | IsOnCall |
|---:|---|
| 1 | true |
| 2 | true |

Hai request đồng thời muốn tắt mỗi người một bác sĩ. Nếu mỗi request tự đọc số người trực rồi quyết định, cả hai có thể cùng thấy số lượng bằng 2 và cùng cho rằng thao tác hợp lệ.

### 1.2. Vì sao mỗi transaction riêng lẻ đều có vẻ đúng?

Nếu chạy tuần tự:

- T1 đọc thấy hai người trực, tắt bác sĩ 1. Còn bác sĩ 2.
- T2 đọc trạng thái mới, thấy chỉ còn một người trực và từ chối tắt bác sĩ 2.

Hoặc theo thứ tự ngược lại, T2 được phép trước và T1 bị từ chối.

Dù thứ tự nào, chỉ một bác sĩ được tắt. Bất biến được giữ.

### 1.3. Lịch write skew

Khi hai transaction cùng đọc snapshot ban đầu:

~~~text
Trạng thái ban đầu: Doctor 1 = ON, Doctor 2 = ON

T1: BEGIN SNAPSHOT
T2: BEGIN SNAPSHOT

T1: đọc COUNT(ON) = 2
T2: đọc COUNT(ON) = 2

T1: UPDATE Doctor 1 thành OFF
T2: UPDATE Doctor 2 thành OFF

T1: COMMIT
T2: COMMIT

Trạng thái cuối: Doctor 1 = OFF, Doctor 2 = OFF
~~~

T1 chỉ ghi hàng 1. T2 chỉ ghi hàng 2. Write set không giao nhau, nên cơ chế phát hiện xung đột ghi cùng hàng có thể không hủy transaction nào.

### 1.4. Kết quả sai không nhất thiết có exception

Hai lệnh UPDATE có thể trả về row count bằng 1. Cả hai COMMIT thành công. Không có deadlock, không có lost update và không có constraint violation.

Chỉ khi kiểm tra bất biến sau đó mới phát hiện nhóm không còn người trực. Đây là lý do test phải kiểm tra trạng thái nghiệp vụ cuối, không chỉ kiểm tra response hoặc số exception.

## 2. Xác định đúng phạm vi cần tuần tự hóa

### 2.1. Khóa dữ liệu nào?

Write skew không nhất thiết nằm trên hàng được cập nhật. Nó nằm ở điều kiện mà các transaction cùng đọc:

- “Còn ít nhất một người trực.”
- “Tổng quota chưa vượt giới hạn.”
- “Chưa có lịch đặt giao với khoảng này.”
- “Chưa có tài khoản nào là mặc định.”
- “Số lượng đơn ACTIVE chưa đạt mức tối đa.”

Nếu chỉ khóa hàng mà transaction sắp sửa đổi, hai transaction vẫn có thể khóa hai hàng khác nhau và cùng phá một quy tắc chung.

### 2.2. Tìm một điểm đồng bộ chung

Có ba cách thường dùng:

1. **Guard row:** một hàng đại diện cho nhóm, phòng, tài khoản hoặc tài nguyên. Mọi transaction ảnh hưởng đến bất biến phải khóa hoặc cập nhật hàng này trước.
2. **Predicate/range locking:** dùng SERIALIZABLE hoặc locking read có phạm vi để bảo vệ điều kiện tìm kiếm, kể cả hàng chưa tồn tại.
3. **Constraint hoặc atomic update:** chuyển quy tắc thành điều kiện mà database có thể kiểm tra nguyên tử, ví dụ UNIQUE, exclusion constraint hoặc cập nhật bộ đếm có điều kiện.

Điểm đồng bộ phải trùng với phạm vi nghiệp vụ. Nếu bất biến áp dụng cho một nhóm, khóa guard theo group_id. Nếu áp dụng cho một phòng, khóa theo room_id.

### 2.3. Tránh khóa rộng hơn cần thiết

Nếu mọi nhóm trong hệ thống cùng dùng một guard row toàn cục, các thao tác không liên quan cũng phải chờ nhau.

Ví dụ:

- Một guard cho toàn bộ hệ thống: đơn giản nhưng contention lớn.
- Một guard cho mỗi tenant: giảm contention giữa tenant.
- Một guard cho mỗi group/room/account: cho phép các nhóm độc lập chạy đồng thời.

Chọn granularity theo phạm vi bất biến. Không chia nhỏ đến mức hai transaction có thể ảnh hưởng cùng một quy tắc nhưng lại khóa hai guard khác nhau.

### 2.4. Tất cả writer phải tuân thủ cùng giao thức

API chính có thể khóa guard đúng cách nhưng batch import, worker, admin tool hoặc stored procedure khác bỏ qua guard. Khi đó bất biến vẫn có thể bị phá.

Liệt kê mọi writer:

- API đồng bộ.
- Background worker.
- Message consumer.
- Webhook.
- Batch import/backfill.
- Admin tool.
- Trigger/stored procedure.
- Job đối soát hoặc thao tác thủ công.

Một giao thức khóa chỉ có hiệu lực nếu mọi đường ghi liên quan đều tham gia.

## 3. Cách 1: dùng guard row để bảo vệ bất biến

### 3.1. Guard row là gì?

Guard row là một hàng được tạo sẵn để đại diện cho phạm vi của bất biến. Các transaction muốn thay đổi dữ liệu trong phạm vi đó phải lấy khóa trên hàng này trước khi đọc và quyết định.

Ví dụ bảng:

~~~sql
CREATE TABLE InvariantGuard (
    ScopeId INT PRIMARY KEY,
    Version BIGINT NOT NULL
);
~~~

Một hàng cho mỗi nhóm:

~~~sql
INSERT INTO InvariantGuard (ScopeId, Version)
VALUES (10, 0), (20, 0);
~~~

Nhóm 10 và nhóm 20 có guard riêng. Thao tác của nhóm 10 không cần chờ thao tác nhóm 20.

### 3.2. Vì sao cần cập nhật Version?

Trong locking READ COMMITTED, chỉ lấy khóa guard và giữ đến cuối transaction thường đủ nếu mọi transaction lấy khóa trước khi đọc dữ liệu chi tiết.

Nhưng trong snapshot isolation, một transaction có thể tiếp tục đọc snapshot đã được xác lập trước khi nó chờ khóa. Chỉ chờ hoặc đọc guard row không nhất thiết làm snapshot cũ trở nên mới hơn.

Một cách bảo vệ mạnh hơn là **tăng Version trên guard row trong cùng transaction**. Hai transaction ảnh hưởng cùng bất biến khi đó cùng ghi một hàng. Cơ chế phát hiện write-write conflict của DBMS có thể hủy một transaction đang dùng snapshot cũ.

~~~sql
UPDATE InvariantGuard
SET Version = Version + 1
WHERE ScopeId = @ScopeId;
~~~

Version phải thực sự thay đổi. Không dùng một UPDATE giả không làm thay đổi giá trị với kỳ vọng mọi DBMS đều xem đó là xung đột ghi.

### 3.3. Trình tự chuẩn

Với một thao tác tắt trạng thái trực:

1. Bắt đầu transaction.
2. Khóa hoặc cập nhật guard row của nhóm.
3. Xác nhận guard row tồn tại và thao tác cập nhật thành công.
4. Đọc lại trạng thái các bác sĩ trong phạm vi nhóm.
5. Kiểm tra bất biến.
6. Thực hiện thay đổi trạng thái.
7. COMMIT.
8. Nếu conflict hoặc deadlock, rollback và retry toàn transaction theo chính sách.

~~~text
BEGIN
  |
  v
Lock/update guard for Group 10
  |
  v
Read current on-call doctors
  |
  v
Would this operation leave at least one ON?
  |                         |
  | yes                     | no
  v                         v
Update selected doctor    Reject operation
  |
  v
COMMIT
~~~

### 3.4. Vì sao guard phải được lấy trước khi đọc dữ liệu?

Nếu transaction đọc snapshot trước, sau đó mới lấy guard, dữ liệu đã đọc có thể cũ. Trong một số DBMS, snapshot không thay đổi chỉ vì transaction đã chờ khóa.

Hãy lấy guard ngay đầu transaction, trước khi đọc các hàng mà quyết định phụ thuộc vào chúng. Với snapshot isolation, cập nhật guard tạo write conflict nếu một transaction cạnh tranh đã cập nhật guard kể từ snapshot hiện tại.

### 3.5. Không được bỏ qua guard ở một nhánh code

Ví dụ, API tắt bác sĩ dùng guard nhưng batch import cập nhật trực tiếp:

~~~sql
UPDATE DoctorShift
SET IsOnCall = 0
WHERE DoctorId = @DoctorId;
~~~

Batch có thể phá bất biến mà không tạo xung đột trên guard. Hãy đóng gói giao thức trong stored procedure/service dùng chung hoặc giới hạn quyền ghi trực tiếp để mọi writer đi qua cùng đường.

## 4. Khóa guard tường minh trong PostgreSQL

### 4.1. READ COMMITTED với SELECT FOR UPDATE

PostgreSQL có thể khóa hàng guard bằng SELECT FOR UPDATE:

~~~sql
BEGIN;

SELECT scope_id
FROM invariant_guard
WHERE scope_id = 10
FOR UPDATE;

-- Đọc dữ liệu chi tiết sau khi đã lấy guard.
SELECT doctor_id, is_on_call
FROM doctor_shift
WHERE scope_id = 10;

-- Kiểm tra bất biến, cập nhật nếu hợp lệ.

COMMIT;
~~~

Ở READ COMMITTED, mỗi statement có snapshot riêng. Nếu transaction thứ hai chờ guard, sau khi lấy được khóa nó chạy câu SELECT chi tiết tiếp theo với snapshot mới, nên có thể thấy thay đổi đã commit của transaction trước.

Khóa hàng được giữ đến khi transaction kết thúc. Transaction khác muốn lấy khóa tương thích xung đột trên cùng guard phải chờ.

### 4.2. Không nhầm khóa hàng với bảo vệ snapshot cũ

Nếu transaction dùng REPEATABLE READ hoặc SNAPSHOT semantics, transaction có thể đã có snapshot cố định. Một SELECT FOR UPDATE chỉ khóa guard nhưng không nhất thiết cập nhật guard row.

Nếu transaction trước không sửa guard, transaction sau có thể chờ rồi lấy khóa và vẫn tiếp tục dùng snapshot cũ cho các consistent reads. Vì vậy, để bảo vệ write skew dưới snapshot isolation, hãy cập nhật một cột version trên guard row hoặc dùng SERIALIZABLE.

Ví dụ:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

UPDATE invariant_guard
SET version = version + 1
WHERE scope_id = 10;

-- Nếu một transaction khác đã cập nhật guard sau snapshot này,
-- PostgreSQL có thể trả serialization failure.

SELECT doctor_id, is_on_call
FROM doctor_shift
WHERE scope_id = 10;

-- Kiểm tra và ghi thay đổi.

COMMIT;
~~~

Khi hai transaction cùng cập nhật guard từ snapshot cũ, một transaction có thể nhận SQLSTATE 40001. Transaction đó phải rollback và chạy lại từ đầu với snapshot mới.

### 4.3. SERIALIZABLE của PostgreSQL dùng SSI

PostgreSQL SERIALIZABLE sử dụng Serializable Snapshot Isolation (SSI). Engine theo dõi các phụ thuộc đọc-ghi có thể tạo ra lịch không serializable.

Với ví dụ hai bác sĩ:

- T1 đọc cả A và B.
- T2 đọc cả A và B.
- T1 ghi A.
- T2 ghi B.

SSI có thể phát hiện cấu trúc phụ thuộc nguy hiểm và hủy một transaction bằng serialization failure, thường là SQLSTATE 40001.

Predicate locks trong SSI dùng để theo dõi phụ thuộc; chúng không hoạt động như khóa độc quyền thông thường khiến writer luôn phải chờ reader.

### 4.4. Xử lý serialization failure

Sau lỗi 40001:

1. ROLLBACK transaction hiện tại.
2. Bắt đầu transaction mới ở SERIALIZABLE.
3. Đọc lại dữ liệu.
4. Kiểm tra lại điều kiện.
5. Thực hiện lại toàn bộ thao tác.
6. Dừng khi thành công hoặc hết retry budget.

Không retry riêng câu UPDATE cuối dựa trên kết quả COUNT cũ.

## 5. Khóa guard tường minh trong SQL Server

### 5.1. READ COMMITTED với RCSI

Nếu database bật READ_COMMITTED_SNAPSHOT, truy vấn READ COMMITTED thông thường đọc phiên bản tại thời điểm bắt đầu statement. Có thể yêu cầu khóa trên guard row bằng UPDLOCK và HOLDLOCK:

~~~sql
BEGIN TRANSACTION;

SELECT ScopeId
FROM dbo.InvariantGuard WITH (UPDLOCK, HOLDLOCK)
WHERE ScopeId = @ScopeId;

-- Đọc trạng thái chi tiết sau khi đã lấy guard.
SELECT DoctorId, IsOnCall
FROM dbo.DoctorShift
WHERE ScopeId = @ScopeId;

-- Kiểm tra và cập nhật.

COMMIT TRANSACTION;
~~~

UPDLOCK yêu cầu update lock; HOLDLOCK áp dụng semantics SERIALIZABLE cho table reference. Khóa phù hợp được giữ theo transaction. Các transaction khác dùng cùng guard phải chờ hoặc xung đột theo lock mode.

Vì câu SELECT chi tiết được chạy sau khi lấy guard, dưới READ COMMITTED/RCSI nó có thể nhận snapshot statement mới sau khi transaction trước đã commit.

### 5.2. SNAPSHOT isolation: cập nhật guard row

Nếu session dùng SNAPSHOT, có thể tăng version guard trong transaction:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

UPDATE dbo.InvariantGuard
SET Version = Version + 1
WHERE ScopeId = @ScopeId;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Invariant guard not found', 1;
END;

SELECT DoctorId, IsOnCall
FROM dbo.DoctorShift
WHERE ScopeId = @ScopeId;

-- Kiểm tra và cập nhật.

COMMIT TRANSACTION;
~~~

Nếu một transaction khác đã cập nhật guard kể từ snapshot của transaction hiện tại, SQL Server SNAPSHOT có thể trả update conflict, thường là lỗi 3960. Transaction bị xung đột phải rollback.

Đây là cách chuyển phụ thuộc trên nhiều hàng thành write conflict trên một hàng chung. Phải thực hiện update guard trước khi đọc dữ liệu nghiệp vụ và bảo đảm mọi writer dùng cùng guard.

### 5.3. SERIALIZABLE và key-range locks

SQL Server SERIALIZABLE giữ khóa đọc và có thể dùng key-range locks để bảo vệ predicate. Ví dụ kiểm tra một khoảng reservation trước khi INSERT:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.Reservation
    WHERE RoomId = @RoomId
      AND StartTime < @RequestedEnd
      AND EndTime > @RequestedStart
      AND Status = 'ACTIVE'
)
BEGIN
    INSERT INTO dbo.Reservation
        (RoomId, StartTime, EndTime, Status)
    VALUES
        (@RoomId, @RequestedStart, @RequestedEnd, 'ACTIVE');
END
ELSE
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50002, 'Reservation overlaps', 1;
END;

COMMIT TRANSACTION;
~~~

SERIALIZABLE có thể khóa phạm vi index liên quan đến predicate để ngăn phantom. Hiệu quả và độ rộng khóa phụ thuộc index và execution plan. Một scan rộng có thể tăng blocking.

Nếu cần khóa phạm vi cụ thể, hãy tạo index phù hợp và kiểm tra deadlock graph/lock waits dưới tải đồng thời.

### 5.4. UPDLOCK và HOLDLOCK cho predicate

Một cách khác là dùng hint trên table reference:

~~~sql
BEGIN TRANSACTION;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.Reservation WITH (UPDLOCK, HOLDLOCK)
    WHERE RoomId = @RoomId
      AND StartTime < @RequestedEnd
      AND EndTime > @RequestedStart
      AND Status = 'ACTIVE'
)
BEGIN
    INSERT INTO dbo.Reservation
        (RoomId, StartTime, EndTime, Status)
    VALUES
        (@RoomId, @RequestedStart, @RequestedEnd, 'ACTIVE');
END;

COMMIT TRANSACTION;
~~~

HOLDLOCK tương đương SERIALIZABLE cho table reference. UPDLOCK giúp các transaction cạnh tranh lấy update lock sớm hơn. Cần xem plan và index vì predicate khoảng thời gian có thể không ánh xạ thành một range đơn giản trên một index.

## 6. Khóa guard trong MySQL InnoDB

### 6.1. SELECT FOR UPDATE

InnoDB hỗ trợ locking read:

~~~sql
START TRANSACTION;

SELECT scope_id
FROM invariant_guard
WHERE scope_id = 10
FOR UPDATE;

-- Sau khi lấy guard, đọc và kiểm tra dữ liệu chi tiết.
SELECT doctor_id, is_on_call
FROM doctor_shift
WHERE scope_id = 10;

-- Thực hiện thay đổi nếu bất biến còn đúng.

COMMIT;
~~~

SELECT FOR UPDATE là current read và lấy khóa trên record/index entry được truy cập. Transaction khác muốn cập nhật/khóa guard tương tự phải chờ.

### 6.2. Thứ tự đọc quan trọng ở REPEATABLE READ

InnoDB REPEATABLE READ dùng consistent snapshot cho plain SELECT. Snapshot thường được tạo ở lần consistent read đầu tiên.

Nếu transaction thực hiện plain SELECT dữ liệu chi tiết trước khi khóa guard, snapshot có thể đã được xác lập. Sau đó chờ SELECT FOR UPDATE không tự làm snapshot cũ đổi sang mới.

Vì vậy, với guard pattern:

1. Bắt đầu transaction.
2. Lấy guard bằng SELECT FOR UPDATE hoặc cập nhật guard.
3. Chỉ sau đó mới chạy plain consistent reads cần thiết.
4. Kiểm tra và ghi.
5. Commit.

Có thể dùng locking reads cho các dữ liệu cần đọc hiện trạng, nhưng phải hiểu locking read trả về current committed version và có semantics khác plain SELECT.

### 6.3. Cập nhật version guard

Một lựa chọn rõ ràng là:

~~~sql
START TRANSACTION;

UPDATE invariant_guard
SET version = version + 1
WHERE scope_id = 10;

-- Kiểm tra ROW_COUNT() = 1.
-- Đọc dữ liệu và thực hiện thao tác.

COMMIT;
~~~

UPDATE lấy khóa ghi trên guard. Transaction cạnh tranh cùng scope phải chờ. Nếu dùng snapshot đã được xác lập trước đó, cần chú ý quy tắc consistent read của InnoDB và đặt thao tác guard trước lần consistent read đầu tiên.

### 6.4. SERIALIZABLE và next-key locks

InnoDB SERIALIZABLE tăng cường locking semantics. Trong các trường hợp phù hợp, range scan có thể dùng next-key locks (record + gap) để bảo vệ khoảng index và ngăn phantom.

Index ảnh hưởng lớn đến phạm vi khóa. Nếu điều kiện không có access path phù hợp, engine có thể quét và khóa nhiều record hơn dự kiến.

Deadlock vẫn có thể xảy ra. InnoDB chọn victim và rollback transaction; ứng dụng cần nhận diện lỗi 1213/SQLSTATE 40001 và retry toàn transaction.

## 7. Oracle: dùng SELECT FOR UPDATE và kiểm tra semantics

### 7.1. READ COMMITTED

Có thể khóa guard row:

~~~sql
SELECT scope_id
FROM invariant_guard
WHERE scope_id = :scope_id
FOR UPDATE;
~~~

Khóa hàng được giữ đến COMMIT hoặc ROLLBACK. Các transaction cùng scope phải chờ trước khi đọc/ghi phần dữ liệu được bảo vệ.

Trong READ COMMITTED, statement đọc sau khi lấy khóa có thể nhìn thấy thay đổi đã commit trước khi statement đó bắt đầu.

### 7.2. SERIALIZABLE và snapshot semantics

Oracle SERIALIZABLE cung cấp transaction-level read consistency và có thể trả ORA-08177 khi transaction cố sửa một hàng đã bị transaction khác thay đổi sau khi transaction bắt đầu.

Tuy nhiên, không được chỉ dựa vào tên isolation level để kết luận mọi write skew hoặc predicate anomaly đều bị ngăn theo cùng cơ chế với PostgreSQL SSI hoặc SQL Server key-range locks. Hãy kiểm chứng đúng bất biến trên phiên bản Oracle đang dùng và dùng guard row/constraint phù hợp nếu cần.

### 7.3. Cập nhật guard row

Một guard version được cập nhật trong cùng transaction tạo điểm ghi chung:

~~~sql
UPDATE invariant_guard
SET version = version + 1
WHERE scope_id = :scope_id;
~~~

Nếu transaction cạnh tranh đã cập nhật guard sau snapshot hiện tại, Oracle có thể trả ORA-08177. Ứng dụng phải rollback transaction theo đơn vị nghiệp vụ rồi retry.

### 7.4. Phạm vi rollback và retry

Oracle thường rollback statement gây lỗi deadlock hoặc serialization conflict theo semantics của lỗi; transaction có thể còn các thay đổi trước đó. Với thao tác nghiệp vụ cần nguyên tử, ứng dụng nên chủ động rollback toàn transaction trước khi retry.

Không áp dụng máy móc quy tắc rollback toàn transaction của PostgreSQL hoặc SQL Server cho Oracle.

## 8. Cách 2: khóa trực tiếp các hàng liên quan

### 8.1. Khóa tất cả hàng đang tham gia quyết định

Nếu bất biến chỉ liên quan đến một tập hàng đã tồn tại và tập đó xác định được, có thể khóa chúng trực tiếp.

PostgreSQL/MySQL:

~~~sql
BEGIN;

SELECT doctor_id, is_on_call
FROM doctor_shift
WHERE scope_id = 10
ORDER BY doctor_id
FOR UPDATE;

-- Kiểm tra số người trực.
-- Cập nhật hàng được chọn.

COMMIT;
~~~

SQL Server:

~~~sql
BEGIN TRANSACTION;

SELECT DoctorId, IsOnCall
FROM dbo.DoctorShift WITH (UPDLOCK, HOLDLOCK)
WHERE ScopeId = 10
ORDER BY DoctorId;

-- Kiểm tra số người trực.
-- Cập nhật hàng được chọn.

COMMIT TRANSACTION;
~~~

Khóa các hàng theo thứ tự DoctorId giúp giảm nguy cơ hai transaction lấy cùng tập khóa theo thứ tự ngược nhau.

### 8.2. Khóa hàng hiện có không luôn bảo vệ hàng chưa tồn tại

Nếu predicate là “không có reservation giao với khoảng này”, SELECT FOR UPDATE có thể không tìm thấy hàng nào. Không có row lock trên một hàng không tồn tại.

Muốn bảo vệ khoảng trống cần:

- SERIALIZABLE/range locking theo DBMS.
- Guard row đã tồn tại cho resource.
- Constraint chuyên dụng.
- Một mô hình dữ liệu chuyển predicate thành khóa duy nhất hoặc hàng đại diện.

Không dựa vào SELECT FOR UPDATE trên kết quả rỗng như một khóa độc quyền cho mọi hàng có thể được chèn sau đó.

### 8.3. Thứ tự lấy khóa phải ổn định

Nếu một transaction khóa Doctor 1 rồi Doctor 2, transaction khác khóa Doctor 2 rồi Doctor 1, có thể tạo deadlock.

Quy định thứ tự toàn cục, ví dụ tăng dần theo primary key:

~~~text
Lock scope guard
Lock account rows by AccountId ascending
Lock inventory rows by Sku ascending
Lock order rows by OrderId ascending
~~~

Mọi code path phải tuân thủ cùng thứ tự. Trigger hoặc stored procedure cũng cần được tính vào thứ tự tài nguyên.

### 8.4. Khi nào khóa trực tiếp phù hợp?

Phù hợp khi:

- Tập hàng nhỏ và đã tồn tại.
- Có thể xác định trước các hàng cần khóa.
- Tất cả writer dùng cùng thứ tự.
- Muốn đọc rồi cập nhật trên chính các hàng đó.
- Không cần bảo vệ predicate rộng hoặc hàng chưa tồn tại.

Nếu bất biến phụ thuộc một tập động, range hoặc tổng hợp, guard row/constraint/SERIALIZABLE thường rõ ràng hơn.

## 9. Cách 3: dùng SERIALIZABLE để bảo vệ lịch

### 9.1. SERIALIZABLE làm gì?

Serializable isolation yêu cầu kết quả của các transaction đã commit tương đương với một thứ tự tuần tự hợp lệ.

DBMS có thể thực hiện điều này bằng:

- Khóa và giữ khóa đọc.
- Key-range/gap locks để bảo vệ predicate.
- Theo dõi phụ thuộc đọc-ghi và hủy transaction khi phát hiện chu trình nguy hiểm.
- Cơ chế kết hợp tùy engine.

Không phải mọi DBMS triển khai SERIALIZABLE giống nhau.

### 9.2. PostgreSQL: SSI

PostgreSQL SERIALIZABLE dùng SSI. Nó cho phép nhiều transaction đọc snapshot nhưng theo dõi read-write dependencies. Khi phát hiện cấu trúc có thể tạo lịch không serializable, engine hủy một transaction.

Với write skew, một transaction có thể nhận SQLSTATE 40001. Đây là serialization failure, không nhất thiết là deadlock vì không cần có vòng chờ khóa.

### 9.3. SQL Server: khóa và key-range protection

SQL Server SERIALIZABLE giữ khóa đọc đến cuối transaction và dùng key-range locks khi cần bảo vệ predicate. Điều này có thể chặn INSERT/UPDATE tạo phantom trong phạm vi đã đọc.

Index và plan quyết định phạm vi khóa thực tế. SERIALIZABLE có thể giảm concurrency, tăng blocking và deadlock nếu transaction dài hoặc truy cập nhiều resource.

### 9.4. MySQL InnoDB: next-key/gap locking

InnoDB SERIALIZABLE dùng locking behavior mạnh hơn READ COMMITTED/REPEATABLE READ. Range scan có thể dùng next-key locks để bảo vệ index range.

Cần kiểm tra index, access path và lock waits. Một truy vấn thiếu index phù hợp có thể khóa rộng hơn mong muốn.

### 9.5. Oracle: không suy ra semantics từ tên

Oracle SERIALIZABLE dùng transaction-level consistent reads và phát hiện một số xung đột ghi bằng ORA-08177. Vì cách phát hiện khác PostgreSQL SSI và SQL Server range locking, hãy tái hiện chính bất biến cần bảo vệ trên Oracle.

Nếu predicate có thể bị write skew, dùng guard row được cập nhật, khóa tường minh hoặc constraint phù hợp thay vì chỉ dựa vào tên SERIALIZABLE.

### 9.6. Chọn mức cô lập trước khi bắt đầu transaction

Trong JDBC, isolation level phải được cấu hình trước khi transaction bắt đầu theo cách driver/transaction manager hỗ trợ:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
    connection.setAutoCommit(false);

    try {
        // Đọc, kiểm tra và ghi toàn bộ đơn vị nghiệp vụ.
        connection.commit();
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    }
}
~~~

Framework transaction manager có thể quản lý connection và isolation thay cho code JDBC trực tiếp. Hãy chắc chắn cấu hình thực sự áp dụng cho transaction, không chỉ thay đổi một connection đã tham gia transaction.

## 10. Cách 4: thay đổi mô hình dữ liệu để biến predicate thành một hàng

### 10.1. Lưu bộ đếm đại diện

Với quota, thay vì mỗi request đọc SUM trên nhiều hàng, lưu Used và LimitValue trên một hàng quota.

~~~sql
UPDATE GroupQuota
SET Used = Used + @Amount
WHERE GroupId = @GroupId
  AND Used + @Amount <= LimitValue;
~~~

Nếu row count bằng 1, quota được cấp. Nếu row count bằng 0, quota không còn đủ.

Mọi cập nhật chi tiết phải đi cùng thay đổi counter trong một transaction.

### 10.2. Guard count cho người trực

Có thể lưu OnCallCount trong một hàng nhóm. Khi tắt một bác sĩ:

~~~sql
UPDATE GroupOnCallSummary
SET OnCallCount = OnCallCount - 1
WHERE ScopeId = @ScopeId
  AND OnCallCount > 1;
~~~

Nếu row count bằng 1, tiếp tục cập nhật DoctorShift trong cùng transaction. Nếu row count bằng 0, từ chối vì đây là người trực cuối cùng.

Bộ đếm và hàng chi tiết phải cập nhật nguyên tử. Nếu một transaction cập nhật summary nhưng không cập nhật DoctorShift, hoặc ngược lại, dữ liệu có thể lệch. Dùng constraint/trigger/procedure hoặc quyền ghi để bảo đảm giao thức được áp dụng ở mọi writer.

### 10.3. Chuyển bất biến thành trạng thái đơn hàng

Một số quy tắc có thể mô hình hóa bằng một hàng duy nhất:

- Một reservation slot có một trạng thái và owner.
- Một coupon có remaining_uses.
- Một job có owner, lease và fencing token.
- Một tài khoản có version và trạng thái hiện tại.

Khi nhiều transaction cùng cập nhật hàng đại diện, database có một điểm xung đột ghi rõ ràng.

### 10.4. Constraint vẫn là lớp bảo vệ tốt nhất khi biểu diễn được

Ví dụ:

- UNIQUE cho khóa nghiệp vụ.
- Partial/filtered unique index cho một hàng ACTIVE.
- CHECK cho điều kiện trong cùng hàng.
- FOREIGN KEY cho tham chiếu.
- PostgreSQL exclusion constraint cho khoảng thời gian không được chồng lấn.

Constraint không thay thế mọi cơ chế tuần tự hóa, nhưng giúp bảo vệ quy tắc ở tầng database trước mọi writer.

## 11. So sánh các phương án

| Phương án | Bảo vệ điều gì? | Chi phí chính | Rủi ro cần kiểm soát |
|---|---|---|---|
| Guard row + lock | Một bất biến trong scope guard | Transaction cùng scope phải chờ | Writer bỏ qua guard |
| Guard row + version update | Chuyển read dependency thành write conflict dưới SI | Hot row và retry | Snapshot cũ, retry sai phạm vi |
| Lock trực tiếp các hàng | Tập hàng đã tồn tại | Lock nhiều hàng | Phantom và thứ tự khóa |
| SERIALIZABLE | Lịch/predicate theo semantics DBMS | Blocking hoặc abort/retry | Khác biệt engine, contention |
| Atomic conditional UPDATE | Điều kiện trên một hàng/counter | Hot row serialization | Counter không đồng bộ với detail |
| UNIQUE/CHECK/exclusion | Quy tắc biểu diễn được bằng constraint | Index/constraint maintenance | Không biểu diễn được mọi tổng hợp |
| Application/advisory lock | Một business key hoặc resource | Lock lifecycle/coordination | Writer không tuân thủ, lock phân tán |

## 12. Chọn phương án theo tình huống

### 12.1. Ít nhất một bác sĩ phải trực

Các lựa chọn:

- Guard row theo nhóm, cập nhật version trước khi đọc.
- Khóa một hàng summary chứa OnCallCount.
- SERIALIZABLE với predicate phù hợp.
- Mô hình hóa một hàng trạng thái đại diện.

Nếu hệ thống có nhiều nhóm độc lập, dùng guard theo ScopeId để tránh khóa toàn hệ thống.

### 12.2. Quota tổng không được vượt giới hạn

Ưu tiên một hàng quota với atomic conditional UPDATE. Không cần SELECT SUM rồi tự tính ở ứng dụng nếu có thể duy trì bộ đếm đáng tin cậy.

Nếu quota được tính từ nhiều loại dữ liệu và không thể materialize an toàn, dùng guard hoặc SERIALIZABLE.

### 12.3. Reservation không được chồng lấn

Ưu tiên constraint chuyên dụng nếu DBMS hỗ trợ và mô hình phù hợp, ví dụ PostgreSQL exclusion constraint. Nếu không, dùng SERIALIZABLE/range locking hoặc guard row theo RoomId.

Khóa các hàng đã tồn tại bằng FOR UPDATE không bảo vệ được khoảng trống nếu chưa có reservation nào.

### 12.4. Chỉ một bản ghi ACTIVE

Partial/filtered unique index có thể biểu diễn trực tiếp quy tắc. Ví dụ chỉ một bản ghi mặc định ACTIVE trong một tenant:

~~~sql
CREATE UNIQUE INDEX UX_DefaultActive
ON UserPreference(TenantId, PreferenceType)
WHERE IsDefault = 1 AND IsActive = 1;
~~~

Cú pháp filtered/partial index khác nhau theo DBMS. Hãy dùng đúng cú pháp engine.

### 12.5. Chuyển tiền giữa nhiều tài khoản

Khóa các tài khoản theo AccountId tăng dần hoặc dùng cơ chế tuần tự hóa phù hợp. Cập nhật debit/credit trong một transaction. Kiểm tra số dư bằng conditional UPDATE và bảo đảm ledger cân bằng.

Retry phải giữ cùng transfer ID để không ghi sổ hai lần.

## 13. Xử lý lỗi và retry

### 13.1. Khóa tường minh có thể tạo blocking hoặc deadlock

Guard row làm các transaction cùng scope tuần tự hóa. Nếu transaction giữ guard lâu, các request sau phải chờ.

Giữ transaction ngắn:

- Không gọi HTTP trong transaction.
- Không chờ người dùng.
- Không xử lý file lớn.
- Không ngủ để điều phối.
- Chỉ đọc/ghi dữ liệu cần thiết.
- Commit ngay khi hoàn tất.

### 13.2. Serializable có thể từ chối một transaction

Tùy engine, transaction có thể nhận:

- PostgreSQL serialization failure: SQLSTATE 40001.
- PostgreSQL deadlock: SQLSTATE 40P01.
- SQL Server deadlock victim: error 1205.
- SQL Server SNAPSHOT update conflict: thường là 3960.
- MySQL InnoDB deadlock: error 1213 / SQLSTATE 40001.
- Oracle serialization conflict: ORA-08177.

Mã lỗi cần được phân loại theo driver/framework; không bắt mọi SQLException rồi retry giống nhau.

### 13.3. Retry toàn bộ transaction

Khi transaction bị serialization failure hoặc deadlock victim, dữ liệu đọc trước đó có thể đã cũ. Mẫu an toàn:

1. Rollback transaction lỗi theo semantics của DBMS.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu hiện tại.
4. Kiểm tra lại bất biến.
5. Tính lại quyết định.
6. Thực hiện toàn bộ thay đổi.
7. Commit.
8. Dừng khi thành công hoặc hết retry budget.

Không retry riêng câu UPDATE cuối.

### 13.4. Backoff và deadline

Dùng retry có giới hạn, backoff tăng dần và jitter. Tổng thời gian retry phải nằm trong deadline của request hoặc job.

Nếu nhiều request cùng retry ngay lập tức, chúng có thể tạo retry storm và tái hiện cùng xung đột.

### 13.5. Tác dụng phụ ngoài database

Rollback không thu hồi email, payment capture hoặc HTTP call đã thực hiện trước đó. Với thao tác có side effect:

- Ghi outbox event trong cùng transaction.
- Phát event sau commit.
- Consumer dùng inbox/dedup.
- Dùng idempotency key ổn định qua các lần retry.
- Đối soát nếu COMMIT outcome không rõ.

## 14. Những lỗi thường gặp khi áp dụng guard row

### 14.1. Guard row không tồn tại

SELECT FOR UPDATE trên một khóa không tìm thấy hàng không tự tạo một hàng guard chung trên mọi DBMS/isolation level.

Tạo guard row trước cho mỗi scope hoặc dùng một cơ chế constraint/serializable phù hợp để bảo vệ việc tạo mới.

### 14.2. Chỉ SELECT guard mà không cập nhật trong snapshot isolation

Trong snapshot isolation, transaction có thể tiếp tục dùng snapshot cũ sau khi chờ khóa. Nếu muốn biến guard thành điểm xung đột phiên bản, cập nhật version/counter trong transaction.

### 14.3. Đọc dữ liệu trước khi khóa guard

Transaction có thể đã xác lập snapshot cũ. Hãy lấy hoặc cập nhật guard trước khi đọc dữ liệu dùng để quyết định.

### 14.4. Khóa guard sau khi đã gọi dịch vụ ngoài

Nếu transaction giữ guard trong lúc gọi HTTP, các request cùng scope phải chờ lâu. Nếu gọi provider trước khi commit rồi transaction rollback, side effect có thể tồn tại dù database không ghi nhận.

Tách phần gọi dịch vụ ngoài bằng outbox hoặc workflow có idempotency.

### 14.5. Một số writer bỏ qua guard

Batch, admin hoặc trigger có thể phá bất biến. Tạo API/stored procedure dùng chung, kiểm soát quyền ghi và test tất cả writer.

### 14.6. Guard row toàn cục tạo hot spot

Một guard cho toàn hệ thống khiến các thao tác không liên quan chờ nhau. Chia guard theo đúng scope của bất biến.

### 14.7. Không thống nhất thứ tự lấy nhiều guard

Nếu một transaction lấy guard nhóm A rồi B, transaction khác lấy B rồi A, có thể deadlock. Sắp xếp key theo thứ tự ổn định trước khi lấy khóa.

### 14.8. Chỉ kiểm tra response

Hai request có thể đều trả thành công trong khi bất biến đã bị phá. Luôn truy vấn trạng thái đã commit bằng connection độc lập và kiểm tra oracle.

## 15. Bài thực hành: tái hiện và sửa write skew

### 15.1. Chuẩn bị dữ liệu

Ví dụ SQL Server:

~~~sql
CREATE TABLE dbo.DoctorShift (
    ScopeId INT NOT NULL,
    DoctorId INT NOT NULL,
    IsOnCall BIT NOT NULL,
    CONSTRAINT PK_DoctorShift PRIMARY KEY (ScopeId, DoctorId)
);

INSERT INTO dbo.DoctorShift (ScopeId, DoctorId, IsOnCall)
VALUES (10, 1, 1), (10, 2, 1);

CREATE TABLE dbo.InvariantGuard (
    ScopeId INT PRIMARY KEY,
    Version BIGINT NOT NULL
);

INSERT INTO dbo.InvariantGuard (ScopeId, Version)
VALUES (10, 0);
~~~

Đặt database ở chế độ cho phép SNAPSHOT nếu muốn tái hiện bằng SQL Server SNAPSHOT.

### 15.2. Tái hiện lỗi bằng hai session

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE ScopeId = 10 AND IsOnCall = 1;

-- Chờ Session B đọc xong.
UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE ScopeId = 10 AND DoctorId = 1;

COMMIT TRANSACTION;
~~~

Session B:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE ScopeId = 10 AND IsOnCall = 1;

-- Chỉ tiếp tục sau khi Session A cũng đã đọc.
UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE ScopeId = 10 AND DoctorId = 2;

COMMIT TRANSACTION;
~~~

Để tạo lịch chính xác, dùng test harness với barrier sau SELECT. Không dựa vào việc chạy hai cửa sổ query gần cùng lúc.

### 15.3. Oracle trước khi sửa

~~~sql
SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE ScopeId = 10 AND IsOnCall = 1;
~~~

Kết quả đúng phải >= 1. Nếu bằng 0, test đã tái hiện write skew.

### 15.4. Sửa bằng guard version

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

UPDATE dbo.InvariantGuard
SET Version = Version + 1
WHERE ScopeId = 10;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Guard row missing', 1;
END;

SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE ScopeId = 10 AND IsOnCall = 1;

-- Chỉ tắt bác sĩ nếu còn ít nhất một người sau thao tác.
UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE ScopeId = 10
  AND DoctorId = 1
  AND IsOnCall = 1
  AND (SELECT COUNT(*)
       FROM dbo.DoctorShift
       WHERE ScopeId = 10 AND IsOnCall = 1) > 1;

COMMIT TRANSACTION;
~~~

Session B dùng cùng trình tự và cùng ScopeId nhưng cập nhật DoctorId=2.

Hai transaction cùng ghi guard row. Một transaction có thể bị chặn hoặc nhận update conflict tùy thời điểm snapshot và DBMS. Nếu bị conflict, rollback và retry toàn transaction. Khi retry, nó đọc trạng thái mới và thấy chỉ còn một bác sĩ trực nên từ chối thao tác tắt người cuối cùng.

Ví dụ này minh họa cơ chế. Trong code production, hãy kiểm tra row count của thao tác cập nhật bác sĩ, phân biệt “không tồn tại” với “không đủ người trực”, và thực hiện kiểm tra/ghi theo một giao thức nguyên tử.

### 15.5. Cách đơn giản hơn với summary row

Nếu hệ thống duy trì OnCallCount đáng tin cậy, có thể dùng:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.GroupOnCallSummary
SET OnCallCount = OnCallCount - 1
WHERE ScopeId = 10
  AND OnCallCount > 1;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50002, 'Cannot turn off the last on-call doctor', 1;
END;

UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE ScopeId = 10
  AND DoctorId = @DoctorId
  AND IsOnCall = 1;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50003, 'Doctor state changed', 1;
END;

COMMIT TRANSACTION;
~~~

Hai transaction cạnh tranh cập nhật cùng summary row. Điều kiện OnCallCount > 1 được kiểm tra nguyên tử. Phải bảo đảm mọi thay đổi IsOnCall đều cập nhật summary row trong cùng transaction.

### 15.6. Sửa bằng SERIALIZABLE

Có thể chạy cùng kiểm tra và cập nhật trong SERIALIZABLE. DBMS phải bảo vệ lịch theo semantics của engine. Kết quả có thể là một transaction chờ, bị deadlock hoặc serialization failure.

Sau khi chạy, kiểm tra:

~~~sql
SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE ScopeId = 10 AND IsOnCall = 1;
~~~

Bất biến phải giữ. Ứng dụng phải xử lý transaction bị hủy bằng retry toàn bộ nghiệp vụ.

## 16. Viết test concurrency xác định trong Java

### 16.1. Một connection cho mỗi actor

Mỗi actor phải có connection và transaction riêng. Không chia sẻ connection hoặc EntityManager đang tham gia cùng transaction giữa hai thread.

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
CyclicBarrier afterRead = new CyclicBarrier(2);

Callable<Result> actorA = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        // Cấu hình isolation theo test.
        int count = readOnCallCount(connection, 10);
        afterRead.await(5, TimeUnit.SECONDS);
        return turnOffDoctor(connection, 10, 1, count);
    }
};

Callable<Result> actorB = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        // Cấu hình isolation theo test.
        int count = readOnCallCount(connection, 10);
        afterRead.await(5, TimeUnit.SECONDS);
        return turnOffDoctor(connection, 10, 2, count);
    }
};
~~~

Đây là khung minh họa. Mỗi actor cần commit khi thành công và rollback trong finally khi thất bại. Controller phải thu thập exception và đóng executor đúng cách.

### 16.2. Test bản lỗi và bản đã sửa

Bản lỗi:

- Cả hai actor đọc xong trước barrier.
- Cả hai ghi hai hàng khác nhau.
- Chạy ở snapshot isolation.
- Xác nhận có thể tạo trạng thái không còn người trực.

Bản sửa:

- Cả hai actor cập nhật/khóa cùng guard trước khi đọc dữ liệu.
- Hoặc chạy SERIALIZABLE.
- Một thao tác có thể bị conflict/retry.
- Oracle sau cùng xác nhận OnCallCount >= 1.

### 16.3. Không assert actor nào phải thắng

Scheduler, DBMS và deadlock detector có thể chọn transaction khác nhau. Test không nên bắt buộc A luôn thành công hoặc B luôn thất bại.

Hãy assert:

- Không có trạng thái cuối vi phạm bất biến.
- Kết quả mỗi request thuộc hợp đồng nghiệp vụ.
- Transaction conflict được phân loại đúng.
- Retry chạy trong transaction mới.
- Không có side effect trùng.
- Connection không còn transaction lỗi khi trả về pool.

### 16.4. Test writer bỏ qua guard

Tạo một actor giả lập batch/admin không cập nhật guard. Test cần chứng minh rằng một đường ghi không tuân thủ có thể phá bất biến.

Sau đó đưa đường ghi vào cùng stored procedure/service hoặc kiểm soát quyền để không thể bỏ qua protocol.

### 16.5. Chạy trên DBMS production

H2 hoặc mock repository không mô phỏng đầy đủ lock manager, MVCC, SSI, key-range locks và rollback semantics của SQL Server/PostgreSQL/MySQL/Oracle.

Chạy test trên đúng engine, phiên bản, isolation level, index, trigger và connection pool gần production nhất.

## 17. Quan sát và đo chi phí sau khi sửa

### 17.1. Chỉ số cần theo dõi

- Số lần lock wait trên guard.
- Thời gian giữ guard.
- Số deadlock.
- Số serialization failure/update conflict.
- Retry count và retry exhaustion.
- p95/p99 latency của thao tác trong cùng scope.
- Throughput theo scope/tenant.
- Số transaction mở lâu.
- Số lần bất biến bị vi phạm trong đối soát.

### 17.2. Guard row có thể trở thành hot row

Một guard row tạo điểm tuần tự hóa. Đây là chủ ý để bảo vệ bất biến, nhưng nếu scope quá rộng, throughput có thể giảm.

Giảm contention bằng cách:

- Chia guard theo đúng phạm vi nghiệp vụ.
- Rút ngắn transaction.
- Giảm số câu SQL sau khi lấy guard.
- Không gọi dịch vụ ngoài trong transaction.
- Chỉ khóa scope bị ảnh hưởng.
- Cân nhắc atomic counter hoặc constraint.
- Tránh cập nhật guard cho thao tác không làm thay đổi bất biến.

### 17.3. SERIALIZABLE có thể tăng abort rate

Với SSI, nhiều transaction đọc/ghi cùng vùng dữ liệu có thể tạo serialization conflicts. Với locking SERIALIZABLE, range locks có thể tăng blocking.

Theo dõi cả latency và tỷ lệ retry. Nếu retry tăng mạnh, hãy xem lại transaction duration, index, phạm vi predicate và mô hình dữ liệu.

### 17.4. Đừng bỏ bảo vệ chỉ vì benchmark giảm throughput

Nếu bất biến có giá trị nghiệp vụ cao, throughput cao nhưng dữ liệu sai không phải tối ưu. Hãy so sánh phương án bảo vệ theo:

- Correctness.
- Throughput.
- Tail latency.
- Retry cost.
- Operational complexity.
- Khả năng mọi writer tuân thủ.

## 18. Những lựa chọn sai thường gặp

**“Khóa hàng mà transaction sắp sửa đổi là đủ.”**

Sai. Hai transaction có thể ghi hai hàng khác nhau nhưng cùng phá một bất biến tổng hợp. Cần khóa điểm đồng bộ chung hoặc bảo vệ predicate.

**“SELECT FOR UPDATE trên guard luôn làm snapshot mới.”**

Sai. Khóa không tự thay đổi snapshot transaction. Với SI, hãy tạo write conflict trên guard bằng version update hoặc dùng cơ chế SERIALIZABLE phù hợp.

**“SELECT FOR UPDATE không tìm thấy hàng thì đã khóa khoảng trống.”**

Không đúng trên mọi DBMS/isolation level. Hàng không tồn tại không tự tạo một guard. Dùng hàng đại diện có sẵn, range locking hoặc constraint.

**“Chỉ API chính cần lấy guard.”**

Sai. Batch, worker, trigger, admin tool và stored procedure khác cũng có thể phá bất biến.

**“Khóa toàn bộ bảng sẽ đơn giản hơn.”**

Có thể ngăn nhiều lịch nhưng làm giảm concurrency và tạo contention rộng. Chọn khóa theo phạm vi bất biến.

**“SERIALIZABLE có cùng cách triển khai trên mọi database.”**

Sai. PostgreSQL SSI, SQL Server key-range locks và InnoDB next-key locking khác nhau. Oracle cũng có semantics riêng. Kiểm tra đúng engine.

**“Nếu transaction bị abort thì chỉ cần retry câu SQL cuối.”**

Sai. Quyết định đọc trước đó có thể đã cũ. Retry toàn bộ transaction.

**“Một test cập nhật cùng một hàng chứng minh write skew đã được sửa.”**

Sai. Write skew thường ghi các hàng khác nhau. Test phải ép hai transaction cùng đọc snapshot trước khi ghi các hàng khác nhau.

**“Guard row không tạo contention.”**

Sai. Guard là điểm đồng bộ. Chọn scope hợp lý và đo thời gian chờ.

**“Mutex trong Java bảo vệ mọi instance.”**

Sai. Mutex trong bộ nhớ chỉ phối hợp thread trong cùng process. Nhiều instance cần khóa database hoặc cơ chế phân tán có lease/fencing phù hợp.

## 19. Checklist chọn và triển khai giải pháp

Trước khi phát hành:

- Bất biến nghiệp vụ được viết thành điều kiện kiểm tra được chưa?
- Phạm vi guard có khớp tenant/group/room/resource không?
- Guard row có tồn tại trước khi transaction chạy không?
- Guard được khóa/cập nhật trước khi đọc dữ liệu nghiệp vụ chưa?
- Snapshot isolation có tạo write conflict trên guard hay không?
- Có transaction nào chỉ khóa guard nhưng không tạo xung đột phiên bản không?
- Mọi API, batch, worker, trigger và admin path có tuân thủ không?
- Có predicate/hàng chưa tồn tại cần range protection không?
- Index hỗ trợ truy vấn và phạm vi khóa đã phù hợp chưa?
- Thứ tự lấy nhiều khóa có ổn định không?
- Transaction có giữ khóa trong lúc gọi dịch vụ ngoài không?
- Retry có chạy lại toàn bộ transaction không?
- Retry có giới hạn, backoff và idempotency không?
- Có test write skew với hai hàng khác nhau không?
- Có test writer bỏ qua guard không?
- Oracle đọc trạng thái đã commit bằng connection mới không?
- Có metric lock wait, conflict, deadlock và retry không?

## 20. Quy trình sửa một lỗi write skew từ đầu đến cuối

1. **Tái hiện lỗi.** Dùng hai connection độc lập và barrier để cả hai đọc cùng trạng thái trước khi ghi.
2. **Viết bất biến.** Xác định điều kiện phải đúng sau mọi transaction đã commit.
3. **Xác định scope.** Tìm nhóm dữ liệu mà các transaction cùng ảnh hưởng.
4. **Chọn điểm đồng bộ.** Constraint, atomic counter, guard row, explicit row/range lock hoặc SERIALIZABLE.
5. **Chọn semantics theo DBMS.** Kiểm tra snapshot timing, lock retention, range protection và lỗi có thể trả về.
6. **Sửa mọi writer.** API, worker, batch và admin phải dùng cùng giao thức.
7. **Giữ transaction ngắn.** Không thực hiện tác dụng phụ ngoài DB khi đang giữ guard.
8. **Thiết kế retry.** Retry toàn bộ transaction sau serialization/deadlock conflict.
9. **Kiểm tra idempotency/outbox.** Không để retry nhân đôi side effect.
10. **Viết regression test.** Dùng deterministic schedule và oracle trên dữ liệu đã commit.
11. **Chạy trên engine thật.** Đúng phiên bản và cấu hình production.
12. **Đo sau triển khai.** So sánh correctness, throughput, latency, lock waits và retry rate.

## 21. Kết luận

Write skew xuất hiện khi các transaction đọc cùng một điều kiện nhưng ghi các hàng khác nhau. Khóa từng hàng được sửa có thể không tạo xung đột, dù kết quả kết hợp vi phạm bất biến.

Cách sửa là tạo một điểm đồng bộ chung cho quyết định nghiệp vụ: guard row được cập nhật hoặc khóa trước khi đọc, khóa trực tiếp các hàng/range phù hợp, atomic update trên một hàng đại diện, constraint hoặc SERIALIZABLE theo đúng semantics của DBMS. Với snapshot isolation, cần đặc biệt chú ý rằng chỉ chờ khóa không tự làm snapshot cũ trở nên mới; guard version update có thể chuyển phụ thuộc đọc-ghi thành xung đột ghi.

Sau khi sửa, hãy chạy lại lịch cạnh tranh bằng barrier, kiểm tra bất biến bằng connection độc lập và xác nhận retry toàn transaction an toàn. Một giải pháp chỉ đúng với API chính hoặc chỉ đúng khi chạy tuần tự vẫn chưa bảo vệ được dữ liệu trong hệ thống có nhiều writer.
