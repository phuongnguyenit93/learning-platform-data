# Khóa tư vấn theo khóa nghiệp vụ và trách nhiệm giải phóng

Trong một hệ thống nhiều giao dịch, có những tài nguyên nghiệp vụ cần được xử lý lần lượt dù chúng không tương ứng với một hàng dữ liệu cụ thể. Ví dụ: chỉ một tiến trình được tạo hóa đơn cho cùng một kỳ, chỉ một tác vụ được tổng hợp báo cáo tháng của một khách hàng, hoặc chỉ một giao dịch được giữ quyền đặt trước một mã hàng trong một khoảng thời gian ngắn.

Khóa hàng và khóa bảng bảo vệ tài nguyên dữ liệu mà DBMS quản lý. Nhưng đôi khi ứng dụng cần đồng bộ theo một **khóa nghiệp vụ** như `customer:42`, `inventory:SKU-100` hoặc `invoice:tenant-7:2026-11`. Những khóa này có thể không tồn tại dưới dạng hàng trong cơ sở dữ liệu, hoặc một công việc có thể liên quan đến nhiều bảng và nhiều câu lệnh. Khi đó, ứng dụng có thể dùng **khóa tư vấn (advisory lock)**.

Khóa tư vấn là cơ chế đồng bộ mà ứng dụng và DBMS cùng sử dụng theo một quy ước: ứng dụng đặt tên cho tài nguyên logic, yêu cầu khóa tương ứng trước khi thực hiện công việc, rồi giải phóng khóa khi hoàn tất. DBMS quản lý quyền sở hữu và chờ khóa, nhưng nó không tự hiểu ý nghĩa nghiệp vụ của tên khóa và không tự động ngăn mọi câu lệnh SQL khác sửa dữ liệu đó.

## 1. Khóa tư vấn giải quyết vấn đề gì?

Giả sử hệ thống có bảng `Invoice`, nhưng hóa đơn của một khách hàng trong một tháng chỉ được phát hành một lần. Hai worker chạy đồng thời có thể cùng thực hiện các bước:

1. Kiểm tra xem hóa đơn tháng này đã tồn tại chưa.
2. Tính tổng giao dịch của khách hàng.
3. Tạo hóa đơn.

Nếu hai worker kiểm tra cùng lúc trước khi worker nào tạo hóa đơn, cả hai đều có thể thấy chưa tồn tại và cùng tiếp tục. Khóa tư vấn cho phép hai worker thống nhất rằng công việc `invoice:customer-42:2026-11` chỉ được một worker xử lý tại một thời điểm.

```text
Worker A                         Worker B
   |                                |
   | acquire(invoice:42:2026-11)    |
   |------------------------------->|
   |                                | yêu cầu cùng khóa
   | được cấp khóa                  | phải chờ
   | kiểm tra và tạo hóa đơn         |
   | commit                          |
   | release / kết thúc giao dịch    |
   |                                | được cấp khóa
   |                                | kiểm tra lại trạng thái
   |                                | thấy hóa đơn đã có
   |                                | kết thúc mà không tạo trùng
```

Khóa tư vấn hữu ích khi tài nguyên cần đồng bộ là một **khái niệm nghiệp vụ** thay vì một hàng cụ thể. Một khóa có thể đại diện cho một khách hàng, một sản phẩm, một tài khoản, một kỳ chốt sổ hoặc một công việc định danh.

Những tình huống thường gặp:

- Ngăn hai worker xử lý cùng một công việc định kỳ hoặc cùng một khóa idempotency.
- Điều phối việc cấp số hóa đơn, mã chứng từ hoặc số thứ tự theo một phạm vi nghiệp vụ.
- Tuần tự hóa cập nhật nhiều hàng thuộc cùng một tài khoản hoặc một đối tượng tổng hợp.
- Ngăn nhiều tiến trình cùng tạo hoặc tái tạo một tài nguyên logic chưa có hàng tương ứng.
- Bảo vệ một thao tác dài gồm nhiều câu lệnh SQL mà khóa hàng riêng lẻ không diễn đạt được ranh giới nghiệp vụ.

## 2. Khóa tư vấn khác khóa dữ liệu thông thường như thế nào?

| Tiêu chí | Khóa dữ liệu (data lock) | Khóa tư vấn (advisory lock) |
|---|---|---|
| Đối tượng | Hàng, khóa chỉ mục, trang, bảng hoặc metadata do DBMS quản lý | Tài nguyên logic do ứng dụng đặt tên hoặc ánh xạ thành mã khóa |
| Mục đích | Bảo vệ truy cập dữ liệu và hỗ trợ quy tắc đồng thời của DBMS | Đồng bộ các tiến trình theo quy ước nghiệp vụ |
| Cách DBMS hiểu tài nguyên | DBMS biết câu lệnh đang truy cập đối tượng dữ liệu nào | DBMS chỉ biết mã/tên khóa; không hiểu nghiệp vụ gắn với nó |
| Tác động đến SQL thông thường | Có thể chặn thao tác xung đột trên tài nguyên dữ liệu | Không tự chặn câu lệnh SQL không yêu cầu cùng khóa tư vấn |
| Trách nhiệm ứng dụng | Chủ yếu chọn giao dịch, mức cô lập và thao tác phù hợp | Mọi luồng cùng sửa tài nguyên phải tuân thủ cùng quy ước khóa |

Điểm quan trọng nhất: **khóa tư vấn chỉ điều phối những bên cùng tham gia giao thức đó**. Nếu worker A lấy `invoice:42:2026-11`, nhưng một API khác tạo hóa đơn mà không lấy khóa này, khóa tư vấn không tự ngăn API đó. Các ràng buộc dữ liệu như `UNIQUE` vẫn cần thiết để bảo vệ tính đúng đắn trước những đường ghi không tuân thủ giao thức hoặc lỗi lập trình.

Khóa tư vấn cũng không thay thế giao dịch. Nếu một công việc cập nhật nhiều bảng, transaction vẫn cần bảo đảm các thay đổi dữ liệu được commit hoặc rollback cùng nhau. Khóa tư vấn bổ sung cơ chế điều phối giữa các tiến trình; transaction quản lý tính nguyên tử và nhất quán của thay đổi dữ liệu.

## 3. Thiết kế khóa theo khóa nghiệp vụ

Một advisory lock chỉ có tác dụng khi tất cả tiến trình tạo ra cùng một định danh cho cùng một tài nguyên. Thiết kế tên khóa là một phần của hợp đồng đồng thời giữa các thành phần ứng dụng.

### 3.1. Dùng tên có namespace

Không nên dùng một số hoặc chuỗi chung chung như `42` nếu hệ thống có nhiều loại tài nguyên. Giá trị `42` có thể đồng thời được hiểu là khách hàng 42, sản phẩm 42 hoặc đơn hàng 42.

Nên đưa loại tài nguyên và phạm vi vào tên khóa:

```text
customer:42
inventory:product:42
invoice:customer:42:period:2026-11
report:tenant:7:month:2026-11
```

Namespace giúp tránh va chạm giữa các miền nghiệp vụ. Nếu hệ thống đa tenant, mã tenant thường phải là một phần của khóa để khách hàng có cùng ID ở hai tenant không bị xem là cùng tài nguyên.

### 3.2. Chuẩn hóa cách biểu diễn

Các tiến trình phải tạo khóa theo cùng một quy tắc:

- Chuẩn hóa chữ hoa/chữ thường theo quy tắc nghiệp vụ.
- Chuẩn hóa khoảng trắng và định dạng mã.
- Dùng cùng cách biểu diễn ngày, kỳ kế toán và múi giờ.
- Bao gồm tenant hoặc namespace khi phạm vi nghiệp vụ yêu cầu.
- Tránh nối chuỗi mơ hồ, ví dụ `12` + `345` và `123` + `45` có thể tạo cùng chuỗi nếu không có dấu phân cách.

Ví dụ, nếu SKU không phân biệt hoa thường, `sku-100` và `SKU-100` phải ánh xạ tới cùng khóa. Nếu mã SKU phân biệt hoa thường theo quy tắc nghiệp vụ, không được tự ý chuyển đổi chữ hoa/thường.

### 3.3. Khi DBMS yêu cầu mã số

Một số API advisory lock nhận số nguyên 32-bit hoặc 64-bit thay vì chuỗi. Ứng dụng cần ánh xạ khóa nghiệp vụ sang mã ổn định. Không dùng hàm hash ngẫu nhiên thay đổi theo tiến trình hoặc lần chạy, vì hai worker có thể tạo ra hai mã khác nhau cho cùng tài nguyên.

Nếu dùng hash, cần chọn thuật toán xác định, cách mã hóa đầu vào thống nhất và chấp nhận rằng va chạm hash có thể khiến hai tài nguyên khác nhau phải chờ nhau. Va chạm thường gây giảm tính đồng thời, nhưng không được để khóa hash thay thế ràng buộc dữ liệu có tính đúng đắn. Với tài nguyên có ID số ổn định, dùng namespace số riêng kết hợp ID thường dễ kiểm soát hơn.

## 4. Phạm vi sở hữu: transaction hay session?

Một quyết định quan trọng khi dùng khóa tư vấn là khóa thuộc về transaction hay session/connection. Phạm vi sở hữu quyết định thời điểm khóa tự được giải phóng.

### 4.1. Khóa thuộc transaction

Khóa transaction được giữ trong phạm vi một giao dịch cơ sở dữ liệu. Khi transaction commit hoặc rollback, DBMS tự giải phóng khóa.

```text
BEGIN
  acquire advisory lock (transaction scope)
  đọc trạng thái nghiệp vụ
  kiểm tra điều kiện
  cập nhật các bảng liên quan
COMMIT  --> khóa tự giải phóng
```

Đây thường là lựa chọn phù hợp khi khóa chỉ cần bảo vệ một đơn vị công việc được thực hiện hoàn toàn trong transaction. Ưu điểm là vòng đời khóa gắn trực tiếp với vòng đời giao dịch: nhánh thành công commit, nhánh lỗi rollback, cả hai đều kết thúc quyền sở hữu khóa.

### 4.2. Khóa thuộc session/connection

Khóa session tồn tại theo phiên kết nối DB, không nhất thiết kết thúc khi transaction commit hoặc rollback. Ứng dụng thường phải gọi hàm giải phóng tương ứng; khóa cũng được giải phóng khi session thực sự đóng hoặc mất kết nối theo quy tắc của DBMS.

```text
Connection mở
  acquire advisory lock (session scope)
  BEGIN / COMMIT một hoặc nhiều transaction
  thực hiện công việc tiếp theo
  release advisory lock
Connection được trả về pool
```

Khóa session hữu ích khi cần bảo vệ một chuỗi công việc trải qua nhiều transaction. Tuy nhiên, nó tạo thêm trách nhiệm quản lý vòng đời. Nếu ứng dụng quên giải phóng, khóa có thể tồn tại sau khi transaction đã hoàn tất và làm các worker khác chờ không cần thiết.

### 4.3. Bảng quyết định lựa chọn

| Nhu cầu | Phạm vi nên cân nhắc | Lý do |
|---|---|---|
| Khóa chỉ bảo vệ các câu lệnh trong một transaction | Transaction | Commit/rollback tự giải phóng, dễ gắn với ranh giới dữ liệu |
| Khóa phải tồn tại qua nhiều transaction trên cùng connection | Session | Quyền sở hữu kéo dài qua commit/rollback |
| Ứng dụng dùng connection pool và chỉ cần khóa trong một lần cập nhật | Transaction | Tránh để khóa sống sót khi connection được trả về pool |
| Công việc kéo dài qua nhiều bước nhưng không thể giữ transaction mở | Cần thiết kế lại ranh giới; có thể cân nhắc session lock hoặc lease | Cần xác định rõ timeout, chủ sở hữu, phục hồi và giải phóng |

Không nên giữ một transaction mở trong thời gian dài chỉ để giữ advisory lock nếu công việc còn phải gọi API, chờ người dùng hoặc xử lý tệp. Transaction dài làm tăng thời gian giữ tài nguyên, tăng nguy cơ timeout và gây áp lực lên hệ thống. Nếu công việc kéo dài ngoài cơ sở dữ liệu, hãy cân nhắc mô hình lease/job ownership có thời hạn và cơ chế phục hồi thay vì khóa DB vô thời hạn.

## 5. Trách nhiệm giải phóng khóa

Người hoặc thành phần đã lấy khóa phải bảo đảm khóa được giải phóng đúng lúc. Với khóa transaction, DBMS hỗ trợ phần lớn việc này bằng commit/rollback. Với khóa session, ứng dụng cần có đường giải phóng rõ ràng kể cả khi xử lý lỗi.

Một vòng đời an toàn nên có các bước:

1. Tạo khóa từ khóa nghiệp vụ đã chuẩn hóa.
2. Yêu cầu khóa với timeout hữu hạn hoặc chế độ thử ngay.
3. Kiểm tra kết quả lấy khóa; chỉ tiếp tục khi quyền sở hữu đã được cấp.
4. Thực hiện công việc trong phạm vi được bảo vệ.
5. Commit hoặc rollback transaction.
6. Nếu là khóa session, gọi thao tác release trong khối `finally` hoặc cơ chế cleanup tương đương.
7. Chỉ trả connection về pool sau khi đã xác nhận khóa session được giải phóng.

### Dùng transaction để tự động giải phóng

Với transaction-scoped lock, cấu trúc thường có dạng:

```text
begin transaction
try:
    acquire transaction advisory lock
    read and validate business state
    update related rows
    commit
catch error:
    rollback
    propagate or classify error
```

Nếu lấy khóa thất bại hoặc hết thời gian chờ, transaction không được tiếp tục như thể đã có quyền sở hữu. Ứng dụng phải xử lý kết quả timeout, rollback nếu cần và trả về lỗi hoặc thử lại theo chính sách.

### Dùng `finally` cho khóa session

Với khóa session, cần giải phóng ngay cả khi có exception:

```java
boolean acquired = false;
try {
    acquired = acquireSessionLock(connection, lockName, timeout);
    if (!acquired) {
        throw new LockUnavailableException(lockName);
    }

    performWork(connection);
} finally {
    if (acquired) {
        releaseSessionLock(connection, lockName);
    }
}
```

Đây là mã giả minh họa trách nhiệm vòng đời. Hàm thực tế phải kiểm tra mã trả về của DBMS và xử lý lỗi giải phóng. Nếu không thể xác nhận connection còn ở trạng thái sạch, ứng dụng nên loại connection đó khỏi pool theo chính sách của driver/pool thay vì trả một session còn giữ khóa cho yêu cầu tiếp theo.

### Không release nhầm khóa

Ứng dụng cần ghi nhận chính xác khóa nào đã được cấp. Không gọi release vô điều kiện trong `finally` nếu thao tác acquire thất bại, vì một số DBMS trả về kết quả khác nhau khi session không sở hữu khóa. Nếu một session có thể lấy cùng khóa nhiều lần hoặc lấy nhiều khóa khác nhau, cần tuân thủ đúng quy tắc đếm và thứ tự release của DBMS.

## 6. Ví dụ trên các DBMS phổ biến

Khóa tư vấn là khái niệm chung, nhưng tên hàm, phạm vi sở hữu và mã kết quả khác nhau giữa các hệ quản trị. Không thể lấy cú pháp của một DBMS rồi dùng nguyên trạng trên DBMS khác.

### 6.1. PostgreSQL: khóa tư vấn theo transaction

PostgreSQL cung cấp các hàm như `pg_advisory_xact_lock` và `pg_try_advisory_xact_lock` cho khóa thuộc transaction. Các hàm có thể nhận một khóa `bigint` hoặc hai khóa `integer`.

Ví dụ dùng hai số nguyên để biểu diễn namespace và ID khách hàng:

```sql
BEGIN;

-- 100 là namespace cho nghiệp vụ phát hành hóa đơn;
-- 42 là customer_id.
SELECT pg_advisory_xact_lock(100, 42);

-- Đọc trạng thái sau khi đã có khóa.
SELECT invoice_id
FROM invoice
WHERE customer_id = 42
  AND invoice_period = DATE '2026-11-01';

-- Nếu chưa có, thực hiện tính toán và INSERT.
-- Các câu lệnh nghiệp vụ được đặt trong cùng transaction.

COMMIT;
```

Khi transaction kết thúc bằng `COMMIT` hoặc `ROLLBACK`, khóa transaction-scoped được tự động giải phóng. Nếu không muốn chờ, `pg_try_advisory_xact_lock(...)` trả về giá trị boolean cho biết có lấy được khóa hay không.

PostgreSQL cũng có `pg_advisory_lock(...)` và `pg_try_advisory_lock(...)` cho khóa session. Khóa session phải được giải phóng bằng hàm `pg_advisory_unlock(...)` tương ứng hoặc khi session kết thúc. Khóa session vẫn tồn tại qua `COMMIT` và `ROLLBACK`; vì vậy, cần đặc biệt cẩn thận khi dùng connection pool. Một session lấy cùng khóa session nhiều lần phải giải phóng đủ số lần đã lấy theo quy tắc của PostgreSQL.

### 6.2. MySQL: named lock qua `GET_LOCK`

MySQL cung cấp named lock với `GET_LOCK(name, timeout)` và `RELEASE_LOCK(name)`. Named lock thuộc session/connection, không thuộc transaction. Vì vậy, `COMMIT` hoặc `ROLLBACK` không tự giải phóng named lock.

```sql
-- Chờ tối đa 5 giây để lấy khóa.
SELECT GET_LOCK('invoice:customer:42:period:2026-11', 5);

-- Chỉ tiếp tục nếu kết quả là 1.
-- Thực hiện kiểm tra trạng thái và tạo hóa đơn trong transaction.
START TRANSACTION;

-- Các câu lệnh nghiệp vụ...

COMMIT;

-- Giải phóng khóa session trước khi trả connection về pool.
SELECT RELEASE_LOCK('invoice:customer:42:period:2026-11');
```

Ứng dụng cần kiểm tra kết quả `GET_LOCK`: `1` nghĩa là đã lấy được khóa, `0` nghĩa là hết thời gian chờ mà chưa lấy được, còn `NULL` biểu thị lỗi hoặc đối số không hợp lệ theo quy tắc của hàm. `RELEASE_LOCK` cũng có mã kết quả riêng; không nên bỏ qua kết quả khi quản lý connection pool.

Do named lock tồn tại ở cấp session, cần giải phóng trong đường cleanup kể cả khi transaction rollback hoặc ứng dụng gặp exception. Nếu connection được trả về pool khi vẫn giữ named lock, yêu cầu sau có thể sử dụng cùng session và vô tình giữ quyền sở hữu khóa từ yêu cầu trước.

### 6.3. SQL Server: `sp_getapplock`

SQL Server cung cấp `sp_getapplock` để yêu cầu khóa trên một tài nguyên ứng dụng. Tên tài nguyên có thể chứa khóa nghiệp vụ; phạm vi còn phụ thuộc database và database principal.

Ví dụ dùng khóa thuộc transaction:

```sql
BEGIN TRANSACTION;

DECLARE @result int;

EXEC @result = sys.sp_getapplock
    @Resource = N'invoice:customer:42:period:2026-11',
    @LockMode = 'Exclusive',
    @LockOwner = 'Transaction',
    @LockTimeout = 5000;

IF @result < 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Could not acquire invoice advisory lock.', 1;
END;

-- Đọc trạng thái và thực hiện các thay đổi nghiệp vụ.

COMMIT TRANSACTION;
```

Các giá trị trả về không âm biểu thị yêu cầu khóa được chấp nhận; giá trị âm biểu thị timeout, hủy yêu cầu, deadlock hoặc lỗi. Ứng dụng nên ghi nhận mã cụ thể để phân biệt nguyên nhân. Với `@LockOwner = 'Transaction'`, transaction phải đang hoạt động và khóa được tự giải phóng khi transaction commit hoặc rollback.

SQL Server cũng hỗ trợ `@LockOwner = 'Session'`. Khi đó, ứng dụng cần gọi `sp_releaseapplock` với đúng tài nguyên và chủ sở hữu session. Khóa session tồn tại qua commit/rollback và phải được giải phóng trước khi connection được tái sử dụng.

## 7. Timeout, thử khóa và xử lý khi không lấy được khóa

Không nên để một worker chờ khóa vô hạn mà không có chính sách. Khóa có thể đang được giữ bởi một transaction bị treo, một worker chạy lâu hoặc một lỗi cleanup.

Ba kiểu yêu cầu thường gặp:

- **Chờ có giới hạn:** đợi đến khi có khóa hoặc hết timeout. Phù hợp khi công việc có thể chờ trong một khoảng thời gian xác định.
- **Thử ngay (non-blocking):** nếu khóa đang bận, trả kết quả thất bại ngay. Phù hợp với job có thể bỏ qua lượt chạy hoặc lên lịch lại.
- **Chờ rồi retry:** nếu hết timeout, ghi nhận trạng thái và thử lại sau khoảng nghỉ có giới hạn.

Khi timeout, ứng dụng cần quyết định rõ: trả lỗi cho người gọi, đưa job về hàng đợi, thử lại sau, hay bỏ qua vì một worker khác đang xử lý. Không được tiếp tục phần công việc được bảo vệ khi chưa có khóa.

Nên dùng timeout phù hợp với thời gian xử lý nghiệp vụ và deadline của request. Timeout quá ngắn tạo ra nhiều lần thất bại giả; timeout quá dài khiến worker chiếm connection và tài nguyên trong lúc chờ. Với công việc nền, có thể dùng backoff tăng dần và jitter để tránh nhiều worker cùng thức dậy rồi tranh khóa lại đúng một thời điểm.

## 8. Deadlock khi lấy nhiều khóa tư vấn

Advisory lock vẫn có thể tham gia vào deadlock. Giả sử giao dịch A cần khóa khách hàng 1 rồi khách hàng 2, còn giao dịch B cần khóa khách hàng 2 rồi khách hàng 1:

```text
Transaction A                  Transaction B
  giữ customer:1                 giữ customer:2
  chờ customer:2                 chờ customer:1
       |                              |
       +----------- deadlock ---------+
```

Để giảm nguy cơ này, tất cả luồng nên lấy nhiều khóa theo một thứ tự toàn cục nhất quán, ví dụ sắp xếp khóa theo namespace rồi theo ID tăng dần. Nếu một transaction cần khóa nhiều khách hàng, nó lấy `customer:1` trước `customer:2` bất kể thứ tự đầu vào.

Thứ tự nhất quán không loại bỏ mọi deadlock vì transaction còn có thể giữ khóa dữ liệu thông thường hoặc khóa metadata. Cần giữ transaction ngắn, tránh gọi dịch vụ ngoài trong khi đang giữ khóa và có chính sách xử lý lỗi deadlock của DBMS.

Nếu một transaction cần kết hợp advisory lock và khóa hàng, cần thống nhất thứ tự lấy hai loại khóa giữa các luồng. Ví dụ, nếu một luồng lấy advisory lock rồi mới cập nhật hàng, luồng khác không nên cập nhật hàng trước rồi mới đợi advisory lock trên cùng tài nguyên, vì thứ tự ngược có thể tạo chu trình chờ.

## 9. Những lỗi thường gặp khi quản lý vòng đời khóa

### Quên giải phóng khóa session

Một nhánh exception bỏ qua câu lệnh release có thể khiến các yêu cầu sau chờ lâu. Dùng `finally`, `defer`, `using` hoặc cơ chế scope tương đương để đặt cleanup ngay cạnh thao tác acquire. Với transaction-scoped lock, luôn kết thúc transaction đúng cách.

### Trả connection về pool khi còn giữ khóa

Connection pool thường tái sử dụng session vật lý. Đóng connection ở tầng ứng dụng có thể chỉ trả nó về pool, không đóng session DB thật. Vì vậy, khóa session có thể vẫn tồn tại. Cần release trước khi trả connection hoặc loại bỏ session khỏi pool nếu trạng thái không thể khôi phục an toàn.

### Lấy khóa sau khi đã đọc trạng thái

Nếu ứng dụng đọc dữ liệu, quyết định rằng tài nguyên chưa được xử lý, rồi mới lấy khóa, một worker khác có thể thay đổi trạng thái trong khoảng giữa hai bước. Thông thường, phải lấy khóa trước khi đọc và kiểm tra trạng thái mà khóa có trách nhiệm bảo vệ.

### Có luồng không tuân thủ giao thức

Nếu chỉ một phần ứng dụng lấy khóa, các phần còn lại vẫn có thể tạo dữ liệu trùng hoặc cập nhật xung đột. Đặt thao tác lấy khóa trong một service hoặc repository dùng chung, ghi rõ namespace và hợp đồng nghiệp vụ. Đồng thời dùng constraint và kiểm tra dữ liệu làm lớp bảo vệ cuối cùng.

### Dùng khóa tư vấn như một hàng đợi công bằng

DBMS thường không cam kết thứ tự cấp khóa theo đúng thứ tự worker đến trước. Nếu nghiệp vụ yêu cầu FIFO, ưu tiên hoặc phân phối công việc công bằng, cần dùng hàng đợi có semantics phù hợp thay vì giả định advisory lock sẽ bảo đảm thứ tự đó.

### Giữ khóa quá lâu

Giữ khóa trong khi chờ người dùng, gọi API chậm hoặc xử lý tệp lớn làm tăng thời gian chờ của những tiến trình khác. Chỉ giữ khóa quanh phần quyết định và cập nhật cần được tuần tự hóa. Nếu cần phối hợp công việc dài, dùng trạng thái job/lease có thời hạn, heartbeat và cơ chế thu hồi quyền sở hữu khi worker chết.

## 10. Khóa tư vấn không thay thế ràng buộc dữ liệu

Giả sử quy tắc là mỗi khách hàng chỉ có một hóa đơn cho một kỳ. Advisory lock giúp các worker hợp tác tránh tạo trùng, nhưng dữ liệu vẫn nên có ràng buộc:

```sql
ALTER TABLE invoice
ADD CONSTRAINT uq_invoice_customer_period
UNIQUE (customer_id, invoice_period);
```

Ràng buộc `UNIQUE` bảo vệ tính duy nhất ngay cả khi:

- Một luồng code quên lấy advisory lock.
- Một phiên bản ứng dụng cũ chưa triển khai giao thức khóa.
- Hai hệ thống khác nhau cùng ghi vào bảng.
- Một lỗi cấu hình khiến khóa nghiệp vụ được ánh xạ thành hai tên khác nhau.

Advisory lock giúp giảm công việc trùng lặp và làm rõ quyền xử lý. Constraint là hàng rào dữ liệu được DBMS thực thi. Khi cả hai cùng tồn tại, ứng dụng vẫn phải xử lý lỗi vi phạm unique constraint như một tình huống có thể xảy ra.

Với những quy tắc không thể biểu diễn bằng constraint đơn giản, cần chọn mức cô lập hoặc cơ chế bảo vệ phù hợp. Advisory lock chỉ có thể bảo vệ quy tắc đó nếu mọi bên có quyền thay đổi dữ liệu đều tuân thủ giao thức khóa.

## 11. Quan sát và vận hành

Khóa tư vấn cần được quan sát như một phần của hệ thống đồng thời. Nên ghi nhận:

- Namespace và khóa nghiệp vụ đã chuẩn hóa (tránh ghi dữ liệu nhạy cảm nguyên văn nếu không cần thiết).
- Thời điểm yêu cầu, thời điểm được cấp và thời gian giữ khóa.
- Chủ sở hữu logic như worker ID, request ID hoặc job ID.
- Kết quả acquire: thành công, timeout, thử ngay thất bại hay lỗi DBMS.
- Kết quả release và lỗi cleanup.
- Số lượng worker đang chờ cùng namespace và các khóa thường xuyên bị tranh chấp.

Không nhất thiết log mọi lần polling hoặc lặp chờ ở mức chi tiết cao; nên dùng metric và log có cấu trúc để phát hiện khóa bị giữ lâu, timeout tăng hoặc một khóa nghiệp vụ trở thành điểm nóng.

Khi điều tra sự cố, cần xác định session/transaction nào đang sở hữu khóa, công việc đó có còn tiến triển không, transaction có đang chờ khóa dữ liệu khác không và khóa thuộc transaction hay session. Chỉ nhìn thấy một tên khóa đang bận chưa đủ để kết luận worker sở hữu khóa bị treo.

## 12. Checklist thiết kế một advisory lock

Trước khi đưa khóa tư vấn vào một luồng nghiệp vụ, hãy xác định:

1. **Tài nguyên logic:** chính xác điều gì cần được xử lý tuần tự?
2. **Khóa nghiệp vụ:** namespace, tenant, ID và quy tắc chuẩn hóa nào tạo nên định danh duy nhất?
3. **Phạm vi sở hữu:** transaction hay session? Điều gì làm khóa tự giải phóng?
4. **Thời điểm lấy khóa:** có lấy trước khi đọc và kiểm tra trạng thái cần bảo vệ không?
5. **Timeout:** chờ tối đa bao lâu, có chế độ thử ngay hay không?
6. **Cleanup:** nhánh thành công, exception, timeout, rollback và mất kết nối được xử lý thế nào?
7. **Connection pool:** session có thể được tái sử dụng khi vẫn còn khóa không?
8. **Deadlock:** nhiều khóa được lấy theo thứ tự thống nhất chưa?
9. **Bảo vệ dữ liệu:** có constraint hoặc cơ chế DBMS bảo đảm tính đúng đắn nếu một luồng không lấy khóa không?
10. **Quan sát:** có metric về thời gian chờ, thời gian giữ, timeout và lỗi release không?

Khóa tư vấn theo khóa nghiệp vụ là một công cụ hữu ích để điều phối các tiến trình cùng xử lý một tài nguyên logic. Hiệu quả của nó phụ thuộc vào việc định danh khóa thống nhất, lấy khóa đúng thời điểm và gắn vòng đời khóa với transaction hoặc session một cách có chủ đích. Khi dùng khóa session, trách nhiệm giải phóng thuộc trực tiếp về ứng dụng; khi dùng khóa transaction, commit hoặc rollback là ranh giới giải phóng rõ ràng. Kết hợp giao thức này với constraint dữ liệu, timeout hữu hạn và khả năng quan sát sẽ giúp hệ thống tránh xử lý trùng mà vẫn phục hồi được khi worker gặp lỗi.
