# Khóa theo giao dịch khác gì với khóa theo phiên

Khi ứng dụng cần phối hợp nhiều tiến trình cùng xử lý một tài nguyên logic, nó có thể yêu cầu cơ sở dữ liệu cấp một khóa chủ động (explicit lock), khóa ứng dụng (application lock) hoặc khóa tư vấn (advisory lock). Ngoài chế độ khóa như chia sẻ hay độc quyền, một quyết định quan trọng là **khóa thuộc về giao dịch (transaction-scoped) hay thuộc về phiên kết nối (session-scoped)**.

Khác biệt cốt lõi nằm ở vòng đời của quyền sở hữu khóa:

- **Khóa theo giao dịch** được giữ trong phạm vi một transaction và tự giải phóng khi transaction commit hoặc rollback.
- **Khóa theo phiên** thuộc về phiên kết nối database. Nó có thể tiếp tục được giữ sau khi transaction commit hoặc rollback, cho đến khi ứng dụng chủ động nhả khóa hoặc phiên kết nối kết thúc.

Hai kiểu khóa có thể dùng để bảo vệ cùng một tài nguyên logic và đều có thể khiến phiên khác phải chờ nếu yêu cầu không tương thích. Chúng khác nhau ở thời điểm bắt đầu/kết thúc quyền sở hữu, vì vậy cần chọn theo ranh giới công việc mà ứng dụng muốn bảo vệ.

## 1. Phân biệt transaction và session

**Transaction (giao dịch)** là một đơn vị công việc dữ liệu có ranh giới commit hoặc rollback. Một transaction có thể gồm một hoặc nhiều câu lệnh SQL. Khi transaction commit, các thay đổi được xác nhận; khi rollback, các thay đổi chưa commit bị hủy theo quy tắc của hệ quản trị.

**Session (phiên)** là ngữ cảnh kết nối mà client dùng để giao tiếp với database. Trong nhiều ứng dụng, một session gắn với một kết nối vật lý tới máy chủ database. Một session có thể thực hiện nhiều transaction nối tiếp nhau:

```text
Session S1 (một kết nối database)
  |
  +-- Transaction T1: BEGIN ... COMMIT
  |
  +-- Transaction T2: BEGIN ... ROLLBACK
  |
  +-- Transaction T3: BEGIN ... COMMIT
  |
  +-- tiếp tục nhận câu lệnh hoặc transaction khác
```

Do đó, transaction thường ngắn hơn hoặc bằng vòng đời session. Kết thúc một transaction không đồng nghĩa kết thúc session. Một kết nối có thể sống lâu và được tái sử dụng cho nhiều request của ứng dụng.

Lưu ý: session trong bài này là session phía database, không phải phiên đăng nhập HTTP, phiên người dùng trên trình duyệt hay session nghiệp vụ của ứng dụng. Một HTTP request có thể dùng một kết nối trong connection pool, nhưng không nhất thiết sở hữu trọn vòng đời của kết nối đó.

## 2. Khóa theo giao dịch (transaction-scoped lock)

Khóa theo giao dịch được gắn với một transaction cụ thể. Khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`, hệ quản trị tự giải phóng khóa thuộc phạm vi transaction đó.

```text
BEGIN TRANSACTION
       |
       v
  ACQUIRE LOCK
       |
       v
  Thực hiện công việc được bảo vệ
       |
       v
  COMMIT hoặc ROLLBACK
       |
       v
  LOCK ĐƯỢC TỰ ĐỘNG GIẢI PHÓNG
```

Ví dụ, một tiến trình cần đảm bảo chỉ có một transaction xử lý việc chốt đơn hàng `order_id = 42` tại một thời điểm. Nó lấy khóa độc quyền theo transaction, thực hiện cập nhật và commit. Khi transaction kết thúc, khóa tự được giải phóng ngay cả khi ứng dụng không gọi lệnh unlock riêng.

### 2.1. Đặc điểm

- Vòng đời khóa đi cùng transaction đang sở hữu nó.
- `COMMIT` giải phóng khóa transaction-scoped.
- `ROLLBACK` cũng giải phóng khóa transaction-scoped.
- Nếu transaction bị hủy do lỗi hoặc kết nối mất và DBMS rollback transaction, khóa được giải phóng theo quá trình kết thúc transaction/session.
- Muốn tiếp tục bảo vệ tài nguyên qua nhiều transaction, ứng dụng phải lấy khóa transaction-scoped mới trong từng transaction hoặc chọn cơ chế sở hữu theo session nếu phù hợp.

Kiểu khóa này phù hợp khi vùng tới hạn (critical section) chính là một đơn vị công việc nguyên tử trong database. Vòng đời ngắn và tự giải phóng giúp giảm nguy cơ quên nhả khóa.

### 2.2. Ví dụ với PostgreSQL advisory lock

PostgreSQL cung cấp nhóm hàm advisory lock có phạm vi transaction. Ví dụ:

```sql
BEGIN;

-- Khóa độc quyền theo transaction cho tài nguyên có mã 42.
SELECT pg_advisory_xact_lock(42);

UPDATE orders
SET processing_state = 'COMPLETED'
WHERE order_id = 42;

COMMIT; -- advisory lock tự được giải phóng
```

Nếu transaction rollback thay vì commit, khóa `pg_advisory_xact_lock` cũng được giải phóng khi transaction kết thúc. Nếu gọi hàm này trong một câu lệnh chạy ở chế độ autocommit mà không mở transaction tường minh, transaction ngầm có thể kết thúc ngay sau câu lệnh đó; khóa khi ấy không bảo vệ các câu lệnh tiếp theo.

Advisory lock là giao thức phối hợp do ứng dụng chủ động tuân thủ. Nó không tự động ngăn một đoạn code khác cập nhật bảng `orders` nếu đoạn code đó không yêu cầu cùng khóa advisory hoặc không có cơ chế database khác bảo vệ.

## 3. Khóa theo phiên (session-scoped lock)

Khóa theo phiên được gắn với session database, không gắn với một transaction riêng. Khi transaction commit hoặc rollback, khóa vẫn còn hiệu lực. Ứng dụng phải chủ động nhả khóa hoặc đóng session để giải phóng nó.

```text
Session S1 bắt đầu
       |
       v
  ACQUIRE SESSION LOCK
       |
       v
  Transaction T1: BEGIN ... COMMIT
       |
       v
  Khóa vẫn được giữ
       |
       v
  Transaction T2: BEGIN ... ROLLBACK
       |
       v
  Khóa vẫn được giữ
       |
       v
  EXPLICIT UNLOCK hoặc đóng Session S1
       |
       v
  LOCK ĐƯỢC GIẢI PHÓNG
```

Ví dụ, một session cần giữ quyền điều phối một tác vụ nhập dữ liệu qua nhiều transaction nhỏ. Session lấy khóa trước khi bắt đầu tác vụ, commit từng lô dữ liệu, rồi nhả khóa sau khi toàn bộ tác vụ kết thúc. Nếu dùng khóa theo transaction, khóa của lô đầu tiên sẽ tự mất sau lần commit đầu tiên, dù công việc tổng thể chưa hoàn tất.

### 3.1. Đặc điểm

- Vòng đời khóa đi cùng session sở hữu khóa.
- `COMMIT` không tự giải phóng khóa session-scoped.
- `ROLLBACK` cũng không tự giải phóng khóa session-scoped.
- Khóa được giữ cho đến khi có lệnh unlock phù hợp hoặc session kết thúc.
- Session có thể chạy nhiều transaction trong lúc vẫn giữ khóa.

Kiểu khóa này hữu ích khi vùng tới hạn kéo dài qua nhiều transaction nhưng vẫn nằm trong cùng một session database. Đổi lại, ứng dụng phải quản lý việc nhả khóa cẩn thận và đảm bảo session không bị dùng lại khi khóa cũ còn tồn tại.

### 3.2. Ví dụ với PostgreSQL advisory lock

PostgreSQL có các hàm advisory lock cấp session:

```sql
-- Lấy khóa theo session; câu lệnh trả về sau khi đã lấy được khóa.
SELECT pg_advisory_lock(42);

BEGIN;
UPDATE import_job
SET status = 'BATCH_1_DONE'
WHERE job_id = 42;
COMMIT;

BEGIN;
UPDATE import_job
SET status = 'BATCH_2_DONE'
WHERE job_id = 42;
COMMIT;

-- Commit ở trên không giải phóng khóa session.
SELECT pg_advisory_unlock(42);
```

Nếu transaction rollback, advisory lock cấp session vẫn được giữ. PostgreSQL còn cung cấp `pg_advisory_unlock_all()` để giải phóng toàn bộ advisory lock cấp session của kết nối hiện tại; việc dùng lệnh này cần cân nhắc vì có thể nhả nhiều khóa mà session đang sở hữu.

Một session có thể lấy cùng advisory lock cấp session nhiều lần theo quy tắc đếm số lần sở hữu của PostgreSQL; ứng dụng phải gọi unlock tương ứng đủ số lần. Không nên giả định hành vi đếm hoặc tái nhập này giống nhau ở mọi DBMS.

## 4. So sánh trực tiếp

| Tiêu chí | Khóa theo giao dịch | Khóa theo phiên |
|---|---|---|
| Chủ sở hữu | Một transaction | Một database session |
| Thời điểm bắt đầu | Khi transaction lấy khóa | Khi session lấy khóa |
| `COMMIT` | Tự giải phóng | Tiếp tục được giữ |
| `ROLLBACK` | Tự giải phóng | Tiếp tục được giữ |
| Cách giải phóng thông thường | Kết thúc transaction | Gọi unlock hoặc kết thúc session |
| Phạm vi công việc phù hợp | Một đơn vị công việc nguyên tử | Một quy trình kéo dài qua nhiều transaction trong cùng session |
| Rủi ro thường gặp | Transaction quá ngắn làm khóa hết hạn sớm | Quên unlock, giữ khóa quá lâu hoặc trả session còn khóa về pool |

Điểm cần nhớ là “theo giao dịch” và “theo phiên” mô tả **thời gian sở hữu khóa**, không mô tả cấp dữ liệu mà khóa bảo vệ. Một khóa theo session vẫn có thể bảo vệ một tài nguyên logic đại diện cho một đơn hàng; một khóa theo transaction cũng có thể đại diện cho cả một tác vụ lớn.

## 5. Cùng một session, nhiều transaction: khác biệt thể hiện ở đâu?

Giả sử session S1 cần xử lý ba lô dữ liệu. Mỗi lô phải commit riêng để giới hạn thời gian transaction và kích thước log.

### 5.1. Dùng khóa theo transaction

```text
S1:
  T1: BEGIN -> lấy khóa K -> xử lý lô 1 -> COMMIT
                         |
                         +-- khóa K tự giải phóng

  T2: BEGIN -> xử lý lô 2 -> COMMIT
       (không còn khóa K bảo vệ toàn bộ tác vụ)

  T3: BEGIN -> xử lý lô 3 -> COMMIT
```

Sau commit T1, một session khác có thể lấy khóa K và bắt đầu công việc trên cùng tài nguyên trong lúc S1 đang chuẩn bị lô 2. Nếu yêu cầu nghiệp vụ là khóa cả quy trình ba lô, khóa transaction-scoped không đủ để giữ quyền sở hữu xuyên suốt các lần commit.

### 5.2. Dùng khóa theo session

```text
S1: lấy khóa K
  |
  +-- T1: BEGIN -> xử lý lô 1 -> COMMIT
  |
  +-- T2: BEGIN -> xử lý lô 2 -> COMMIT
  |
  +-- T3: BEGIN -> xử lý lô 3 -> COMMIT
  |
  +-- nhả khóa K
```

Session khác yêu cầu cùng khóa K phải chờ trong suốt quy trình, kể cả giữa hai transaction của S1. Đây là hành vi phù hợp nếu ứng dụng thực sự cần một chủ thể giữ quyền điều phối xuyên qua các ranh giới commit.

Tuy nhiên, session lock chỉ giữ quyền điều phối. Nó không làm ba transaction trở thành một transaction nguyên tử. Nếu lô 1 và lô 2 đã commit nhưng lô 3 thất bại, dữ liệu của hai lô trước vẫn đã commit. Muốn cả quy trình thành công hoặc thất bại cùng nhau, ứng dụng cần một transaction dài hoặc một thiết kế nghiệp vụ có checkpoint, bù trừ hay trạng thái xử lý từng bước.

## 6. Ví dụ với SQL Server application lock

SQL Server cung cấp `sp_getapplock` để yêu cầu khóa trên một tài nguyên do ứng dụng đặt tên. Tham số `@LockOwner` xác định quyền sở hữu là `Transaction` hay `Session`.

### 6.1. Khóa thuộc transaction

```sql
BEGIN TRANSACTION;

DECLARE @result int;
EXEC @result = sys.sp_getapplock
    @Resource = N'order:42',
    @LockMode = 'Exclusive',
    @LockOwner = 'Transaction',
    @LockTimeout = 5000;

IF @result < 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Cannot acquire transaction application lock', 1;
END;

UPDATE dbo.Orders
SET ProcessingState = 'Completed'
WHERE OrderId = 42;

COMMIT TRANSACTION; -- khóa transaction được giải phóng
```

Khóa owner `Transaction` cần được lấy trong một transaction đang hoạt động. Khi transaction commit hoặc rollback, SQL Server giải phóng application lock đó. Ứng dụng phải kiểm tra mã trả về của `sp_getapplock`; giá trị âm biểu thị yêu cầu khóa không thành công hoặc gặp lỗi theo quy ước của thủ tục.

### 6.2. Khóa thuộc session

```sql
DECLARE @result int;
EXEC @result = sys.sp_getapplock
    @Resource = N'daily-import',
    @LockMode = 'Exclusive',
    @LockOwner = 'Session',
    @LockTimeout = 5000;

IF @result < 0
    THROW 50002, 'Cannot acquire session application lock', 1;

BEGIN TRANSACTION;
-- xử lý lô dữ liệu thứ nhất
COMMIT TRANSACTION;

BEGIN TRANSACTION;
-- xử lý lô dữ liệu thứ hai
COMMIT TRANSACTION;

EXEC sys.sp_releaseapplock
    @Resource = N'daily-import',
    @LockOwner = 'Session';
```

Application lock thuộc session vẫn được giữ qua hai lần commit. Ứng dụng cần gọi `sp_releaseapplock` với đúng resource và owner tương ứng; kết thúc session cũng giải phóng khóa. Đây là khóa ứng dụng được quản lý bởi SQL Server lock manager, không phải câu lệnh khóa dòng thông thường.

## 7. Ví dụ với MySQL named lock

MySQL cung cấp các hàm named lock như `GET_LOCK()` và `RELEASE_LOCK()`. Named lock là khóa cấp session; nó không tự được giải phóng khi transaction commit hoặc rollback.

```sql
-- Trả về 1 nếu lấy được khóa, 0 nếu hết thời gian chờ,
-- hoặc NULL nếu có lỗi.
SELECT GET_LOCK('daily-import', 5);

START TRANSACTION;
UPDATE import_job
SET status = 'BATCH_1_DONE'
WHERE job_id = 42;
COMMIT;

START TRANSACTION;
UPDATE import_job
SET status = 'BATCH_2_DONE'
WHERE job_id = 42;
COMMIT;

-- Commit không tự nhả named lock.
SELECT RELEASE_LOCK('daily-import');
```

Nếu ứng dụng rollback transaction, named lock vẫn còn cho session. Khi kết nối kết thúc, MySQL giải phóng các named lock do session đó nắm giữ. Ứng dụng phải kiểm tra kết quả `GET_LOCK()` trước khi chạy phần công việc được bảo vệ và phải bảo đảm `RELEASE_LOCK()` được gọi trên đúng kết nối đã lấy khóa.

Không nên suy rộng API của một DBMS sang DBMS khác. PostgreSQL advisory locks, SQL Server application locks và MySQL named locks có tên hàm, cách đặt tên resource, quy tắc tái nhập, giá trị trả về và chi tiết tương thích riêng. Hãy đọc tài liệu phiên bản DBMS đang dùng trước khi dựa vào một chi tiết triển khai.

## 8. Khóa theo session và connection pool

Connection pool giữ các kết nối database mở để tái sử dụng giữa nhiều request. Đây là nơi session-scoped lock dễ gây lỗi nếu ứng dụng coi kết nối được mượn như một tài nguyên ngắn hạn.

Giả sử request A mượn kết nối C1, lấy khóa session `job:42`, thực hiện một transaction rồi trả C1 về pool mà quên unlock. Request B sau đó mượn đúng C1. Vì khóa vẫn thuộc session C1, request B kế thừa một session đang giữ khóa từ công việc trước.

```text
Request A                  Connection Pool                 Request B
   |                             |                              |
   +-- mượn C1 ----------------->|                              |
   +-- lấy session lock K        |                              |
   +-- COMMIT                    |                              |
   +-- trả C1 còn giữ K -------->|                              |
                                 +--------- cấp C1 ------------->|
                                 |                         bắt đầu công việc
                                 |                         session vẫn giữ K
```

Hậu quả là request B nhận một session vẫn giữ khóa từ công việc trước và có thể vô tình chạy dưới quyền điều phối của request A. Nếu B yêu cầu lại cùng resource, cách xử lý phụ thuộc API: một số cơ chế cho phép cùng owner lấy lặp lại khóa và theo dõi số lần sở hữu. Trong mọi trường hợp, các session khác vẫn có thể bị chặn cho tới khi khóa được nhả. Một session được pool tái sử dụng cũng có thể làm request khác chờ khóa do một request trước đó bỏ quên.

Khi dùng khóa session-scoped với pool:

1. Giữ quyền sử dụng đúng connection trong toàn bộ thời gian khóa còn hiệu lực; không trả connection về pool giữa chừng.
2. Đặt lệnh unlock trong khối cleanup luôn chạy, kể cả khi xử lý lỗi hoặc rollback.
3. Nếu unlock thất bại hoặc trạng thái khóa không xác định, loại bỏ/đóng connection theo chính sách pool thay vì trả nó như một kết nối sạch.
4. Theo dõi thời gian giữ khóa và cảnh báo session giữ khóa quá lâu.
5. Kiểm tra kỹ hành vi khi timeout, cancel request, mất mạng hoặc ứng dụng bị dừng đột ngột.

Nếu vùng tới hạn chỉ cần bảo vệ một transaction, khóa transaction-scoped thường phù hợp hơn vì transaction kết thúc sẽ tự giải phóng khóa trước khi connection được tái sử dụng.

## 9. Chọn kiểu khóa nào?

Hãy bắt đầu từ ranh giới công việc cần được bảo vệ.

### Chọn khóa theo transaction khi

- Công việc cần bảo vệ nằm gọn trong một transaction.
- Muốn khóa tự được giải phóng khi commit hoặc rollback.
- Cần tránh quên lệnh unlock trong nhiều nhánh xử lý.
- Connection có thể được trả về pool ngay sau khi transaction kết thúc.
- Tính nguyên tử dữ liệu gắn trực tiếp với vùng tới hạn.

Ví dụ: một transaction cập nhật trạng thái đơn hàng và ghi nhận kết quả xử lý tương ứng; một transaction cấp mã hoặc thay đổi một tài nguyên cần phối hợp với các transaction khác.

### Chọn khóa theo session khi

- Quy trình cần giữ quyền điều phối qua nhiều transaction riêng biệt.
- Các bước commit trung gian là chủ đích và không làm kết thúc vùng tới hạn logic.
- Ứng dụng có thể giữ nguyên một database session trong toàn bộ thời gian khóa.
- Có cơ chế cleanup đáng tin cậy khi thành công, thất bại, timeout và mất kết nối.

Ví dụ: một worker giữ quyền chạy một tác vụ bảo trì dài, chia thành nhiều transaction nhỏ, và cần ngăn worker khác chạy cùng tác vụ trong toàn bộ thời gian đó.

Nếu công việc cần kéo dài qua nhiều session hoặc nhiều máy mà không thể giữ một kết nối database liên tục, session lock thường không phải cơ chế điều phối phù hợp. Có thể cần một bản ghi lease có thời hạn, owner ID, heartbeat và fencing token trong database hoặc một hệ thống điều phối chuyên dụng. Lease cần xử lý trường hợp worker cũ hoạt động trở lại sau khi quyền thuê đã hết hạn; fencing token giúp tài nguyên đích từ chối thao tác của owner cũ.

## 10. Những điểm cần phân biệt thêm

### 10.1. Phạm vi sở hữu không phải phạm vi dữ liệu

Transaction-scoped và session-scoped cho biết khóa tồn tại bao lâu và ai chịu trách nhiệm nhả khóa. Chúng không tự quyết định khóa áp dụng cho dòng, bảng, database hay tài nguyên ứng dụng. Resource name và lock mode mới mô tả đối tượng logic và mức tương thích.

### 10.2. Khóa chủ động không tự bảo vệ mọi đường truy cập

Với advisory/application lock, các thành phần ứng dụng phải cùng tuân thủ giao thức. Nếu worker A lấy khóa `order:42` nhưng worker B cập nhật `orders` mà không yêu cầu khóa đó, khóa chủ động không tự ngăn B cập nhật. Nếu cần bảo đảm toàn vẹn cho mọi đường ghi, hãy dùng constraint, transaction và cơ chế khóa dữ liệu phù hợp của DBMS.

### 10.3. Session lock không làm transaction trở nên dài hơn

Một session có thể giữ khóa xuyên qua nhiều transaction, nhưng mỗi transaction vẫn commit hoặc rollback độc lập. Nếu transaction thứ hai thất bại, kết quả đã commit từ transaction thứ nhất không tự bị hoàn tác chỉ vì session vẫn giữ khóa.

### 10.4. Cả hai kiểu đều có thể gây chờ và deadlock

Khóa session tồn tại lâu nên có thể làm tăng thời gian chờ. Khóa transaction thường ngắn hơn nhưng vẫn có thể tạo deadlock khi nhiều transaction lấy các resource theo thứ tự khác nhau. Cần có timeout, xử lý lỗi khóa và quy tắc lấy khóa nhất quán.

### 10.5. Tên gọi và API phụ thuộc DBMS

Một sản phẩm có thể gọi là advisory lock, named lock hoặc application lock. Sản phẩm khác có thể không cung cấp cả hai phạm vi sở hữu hoặc dùng API khác để đạt hành vi tương tự. Không nên giả định mọi `LOCK` trong SQL đều có tùy chọn `Transaction`/`Session` giống nhau.

## 11. Lỗi thường gặp và cách phòng tránh

| Lỗi | Vì sao xảy ra | Cách phòng tránh |
|---|---|---|
| Khóa transaction mất quá sớm | Transaction tự commit sau một câu lệnh hoặc một lô | Mở transaction tường minh bao quanh đúng vùng tới hạn |
| Khóa session không được nhả | Nhánh lỗi bỏ qua lệnh unlock | Dùng `finally`/cleanup và kiểm tra kết quả unlock |
| Giữ khóa qua thời gian chờ người dùng | Session lock được giữ dù transaction đã kết thúc | Không giữ khóa database trong lúc chờ thao tác bên ngoài |
| Connection pool trả session còn khóa | Ứng dụng trả kết nối trước khi giải phóng session lock | Chỉ trả connection sau unlock; loại bỏ kết nối có trạng thái không xác định |
| Hai thành phần dùng tên resource khác nhau | Quy ước tên khóa không thống nhất | Chuẩn hóa resource name và cách mã hóa định danh |
| Nghĩ khóa advisory chặn mọi câu lệnh ghi | Các code path khác không tuân thủ giao thức khóa | Dùng constraint/khóa dữ liệu cho bảo đảm toàn vẹn bắt buộc |
| Dùng session lock như distributed lock dài hạn | Một session/kết nối không được bảo đảm sống qua mọi sự cố | Dùng lease/fencing hoặc cơ chế điều phối phù hợp |

Một khối xử lý session lock nên có cấu trúc tương tự:

```text
connection = borrow_from_pool()
lock_acquired = false

try:
    acquire_session_lock(connection, resource)
    lock_acquired = true

    run_one_or_more_transactions(connection)
finally:
    if lock_acquired:
        release_session_lock(connection, resource)

    if connection_state_is_clean:
        return_to_pool(connection)
    else:
        discard_connection(connection)
```

Đây là pseudocode mô tả trách nhiệm vòng đời. Mã thực tế phải xử lý timeout, kết quả acquire, lỗi release và quy tắc của driver/connection pool.

## 12. Cách phân tích một khóa đang bị giữ

Khi một session khác chờ khóa, hãy tìm câu trả lời cho các câu hỏi sau:

1. Khóa là row/table lock thông thường hay explicit/advisory/application lock?
2. Resource name hoặc đối tượng được khóa là gì?
3. Lock mode hiện tại và mode đang yêu cầu có tương thích không?
4. Owner là transaction hay session?
5. Transaction sở hữu khóa còn hoạt động không, hay session đang giữ khóa nhưng không có transaction mở?
6. Nếu transaction đã commit/rollback, khóa có đúng là loại transaction-scoped không?
7. Nếu khóa thuộc session, có lệnh unlock nào đã chạy trên đúng connection không?
8. Connection có nằm trong pool và đã được tái sử dụng bởi request khác không?
9. Thời gian chờ có phải do lock timeout, deadlock hay session bị bỏ quên?
10. Tất cả code path truy cập cùng tài nguyên có tuân thủ một giao thức khóa không?

Trong SQL Server, có thể quan sát application lock qua các DMV và thông tin khóa của hệ thống. PostgreSQL có các hàm/quan sát advisory lock cùng `pg_locks`. MySQL có các hàm quản lý named lock và thông tin metadata lock phù hợp với loại khóa. Cách truy vấn chẩn đoán cụ thể phụ thuộc phiên bản và loại lock; không nên suy luận owner chỉ từ việc session đang có transaction mở.

## 13. Quy tắc ghi nhớ

Hãy xác định trước điều gì đánh dấu kết thúc vùng tới hạn:

- Nếu kết thúc khi transaction commit hoặc rollback, chọn khóa theo transaction.
- Nếu kết thúc sau một quy trình có nhiều transaction nhưng vẫn trong cùng database session, khóa theo session có thể phù hợp; phải bảo đảm unlock và quản lý connection an toàn.

Khóa theo giao dịch gắn vòng đời khóa với tính nguyên tử của một transaction. Khóa theo phiên gắn vòng đời khóa với kết nối database và cho phép giữ quyền điều phối qua nhiều transaction. Hiểu đúng ranh giới này giúp tránh việc khóa tự hết hạn quá sớm, bị giữ quá lâu hoặc vô tình đi theo connection pool sang request tiếp theo.
