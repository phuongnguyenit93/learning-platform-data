# Phân loại lỗi nghiệp vụ, lỗi ràng buộc và lỗi đồng thời tạm thời

Khi một transaction thất bại, ứng dụng cần quyết định nên trả lỗi cho người dùng, sửa dữ liệu đầu vào, đọc lại trạng thái hay chạy lại toàn bộ transaction. Quyết định này phụ thuộc vào **nguyên nhân của lỗi**, không chỉ vào việc câu SQL nào đã phát sinh exception.

Trong xử lý giao dịch, có thể chia lỗi thành ba nhóm chính:

1. **Lỗi nghiệp vụ (business errors):** thao tác không hợp lệ theo quy tắc của ứng dụng, chẳng hạn số dư không đủ hoặc đơn hàng đã đóng.
2. **Lỗi ràng buộc (constraint errors):** dữ liệu ghi vào vi phạm quy tắc toàn vẹn do database bảo vệ, chẳng hạn khóa duy nhất, khóa ngoại hoặc CHECK constraint.
3. **Lỗi đồng thời tạm thời (transient concurrency errors):** transaction không thể hoàn tất vì xung đột với transaction khác hoặc vì phải chờ tài nguyên khóa, chẳng hạn deadlock, serialization failure hoặc lock timeout.

Ba nhóm này có cách xử lý khác nhau. Lỗi nghiệp vụ thường cần trả kết quả có ý nghĩa cho nghiệp vụ; lỗi ràng buộc cần xác định dữ liệu hoặc quan hệ nào bị vi phạm; lỗi đồng thời tạm thời có thể phù hợp để retry với giới hạn. Retry mọi exception là cách dễ gây lặp vô hạn, tải tăng đột biến và tác dụng phụ bị thực hiện nhiều lần.

## 1. Vì sao cần phân loại lỗi?

Giả sử một API xử lý lệnh chuyển tiền. Một request có thể thất bại vì nhiều nguyên nhân:

- Tài khoản không tồn tại hoặc số dư không đủ: điều kiện nghiệp vụ không được đáp ứng.
- Mã giao dịch đã được dùng: vi phạm unique constraint hoặc request lặp cần được nhận diện theo idempotency key.
- Hai giao dịch đồng thời cập nhật cùng tài khoản và một giao dịch bị deadlock victim: xung đột đồng thời có thể thử lại.

Nếu ứng dụng xử lý cả ba trường hợp bằng cùng một vòng lặp retry, nó sẽ lặp lại những việc không thể thành công dù dữ liệu đầu vào không thay đổi. Ví dụ, retry một yêu cầu rút tiền khi số dư vẫn không đủ không giúp giải quyết vấn đề. Ngược lại, nếu trả lỗi ngay khi gặp deadlock, ứng dụng có thể từ chối một thao tác chỉ thất bại tạm thời và có thể thành công ở lần chạy tiếp theo.

Một luồng xử lý hợp lý:

```text
Transaction thất bại
        |
        v
Nhận diện SQLSTATE / vendor code / constraint
        |
        v
Phân loại theo nguyên nhân
        |
        +---- Lỗi nghiệp vụ ----------------> Trả kết quả nghiệp vụ
        |
        +---- Lỗi ràng buộc ----------------> Xác định constraint và dữ liệu
        |                                      -> trả lỗi hoặc xử lý conflict
        |
        +---- Lỗi đồng thời tạm thời --------> Rollback transaction
                                               -> backoff
                                               -> chạy lại toàn bộ transaction
        |
        +---- Lỗi khác / chưa xác định ------> Ghi log, xử lý theo chính sách
```

Phân loại phải dựa trên mã lỗi có cấu trúc của driver/DBMS và ngữ cảnh nghiệp vụ. Không nên phân loại chỉ bằng cách tìm từ như `duplicate`, `timeout` hoặc `deadlock` trong thông báo lỗi vì message có thể thay đổi theo phiên bản và ngôn ngữ.

## 2. Lỗi nghiệp vụ (Business Errors)

Lỗi nghiệp vụ xuất hiện khi yêu cầu không thỏa quy tắc mà ứng dụng cần duy trì. Database có thể chưa phát sinh lỗi kỹ thuật nào; ứng dụng chủ động từ chối thao tác sau khi kiểm tra dữ liệu hoặc trạng thái hiện tại.

Ví dụ:

- Người dùng yêu cầu rút 500.000 đồng trong khi số dư khả dụng chỉ còn 300.000 đồng.
- Đơn hàng đã chuyển sang trạng thái `SHIPPED`, nên không thể hủy theo quy trình thông thường.
- Ngày kết thúc hợp đồng sớm hơn ngày bắt đầu.
- Người dùng không có quyền thực hiện thao tác trên tài nguyên.
- Một mã giảm giá đã hết hạn theo thời gian nghiệp vụ.

Các lỗi này thường được biểu diễn bằng mã lỗi do ứng dụng định nghĩa, chẳng hạn `INSUFFICIENT_BALANCE`, `ORDER_ALREADY_SHIPPED`, `INVALID_DATE_RANGE` hoặc `COUPON_EXPIRED`.

### 2.1. Vì sao thường không retry?

Retry chỉ chạy lại cùng yêu cầu với dữ liệu và điều kiện tương tự. Nếu điều kiện nghiệp vụ vẫn không thay đổi, lần chạy tiếp theo thường tiếp tục thất bại.

Ví dụ:

```java
if (account.getAvailableBalance().compareTo(amount) < 0) {
    throw new BusinessException("INSUFFICIENT_BALANCE");
}
```

Ứng dụng nên trả lỗi nghiệp vụ rõ ràng để client có thể thay đổi yêu cầu hoặc chờ một sự kiện khác. Không nên tự động retry nhiều lần một request rút tiền khi số dư không đủ.

### 2.2. Điều kiện nghiệp vụ cần được kiểm tra trong transaction

Một kiểm tra nghiệp vụ thực hiện trước transaction có thể trở nên lỗi thời trước khi ghi. Ví dụ, ứng dụng đọc số dư rồi quyết định cho phép rút tiền; một giao dịch khác có thể rút tiền trong khoảng giữa lần đọc và lần ghi.

Với điều kiện gắn trực tiếp vào một dòng, hãy đưa điều kiện vào câu lệnh ghi:

```sql
UPDATE account
SET balance = balance - :amount
WHERE account_id = :account_id
  AND balance >= :amount;
```

Ứng dụng kiểm tra số dòng được cập nhật. Nếu không có dòng nào, yêu cầu không thực hiện được; nguyên nhân có thể là tài khoản không tồn tại hoặc số dư không đủ. Có thể đọc thêm trong một transaction phù hợp để phân biệt hai kết quả nếu API cần thông báo riêng.

Điều này giúp database kiểm tra điều kiện và cập nhật như một thao tác ghi được điều phối đồng thời. Với quy tắc liên quan nhiều dòng hoặc nhiều bảng, cần transaction, constraint, khóa hoặc isolation level phù hợp; một lần đọc trước transaction không đủ để bảo vệ quy tắc đó.

### 2.3. Không phải mọi lỗi nghiệp vụ đều là lỗi SQL

Ví dụ `ORDER_ALREADY_SHIPPED` thường được ứng dụng phát hiện khi đọc trạng thái đơn hàng. Nó không nhất thiết tương ứng với SQLSTATE nào. Lớp dịch vụ nên có mã lỗi nghiệp vụ ổn định, độc lập với vendor code của database.

Một unique violation cũng có thể được chuyển thành lỗi nghiệp vụ. Ví dụ, khi đăng ký username đã tồn tại, database báo vi phạm unique constraint; API có thể chuyển lỗi đó thành `USERNAME_ALREADY_TAKEN`. Nguyên nhân kỹ thuật là constraint error, còn cách trình bày cho người dùng là business result. Hai góc nhìn này không mâu thuẫn: phân loại kỹ thuật giúp quyết định retry, còn phân loại nghiệp vụ giúp xây dựng phản hồi phù hợp.

## 3. Lỗi ràng buộc (Constraint Errors)

Constraint là quy tắc toàn vẹn được khai báo trong database. Nó bảo vệ dữ liệu ngay cả khi nhiều ứng dụng, batch job hoặc câu SQL khác nhau cùng ghi vào bảng.

Các loại constraint thường gặp:

| Constraint | Quy tắc | Ví dụ vi phạm |
|---|---|---|
| `PRIMARY KEY` | Mỗi dòng có khóa chính duy nhất và không null | Chèn hai dòng cùng `customer_id` |
| `UNIQUE` | Giá trị hoặc tổ hợp cột phải duy nhất theo quy tắc DBMS | Tạo hai tài khoản cùng email đã chuẩn hóa |
| `FOREIGN KEY` | Giá trị tham chiếu phải trỏ tới dòng cha hợp lệ | Chèn đơn hàng có `customer_id` không tồn tại |
| `NOT NULL` | Cột bắt buộc phải có giá trị | Ghi `NULL` vào `email` bắt buộc |
| `CHECK` | Giá trị phải thỏa biểu thức kiểm tra | Ghi `quantity = -3` khi CHECK yêu cầu không âm |

Khi constraint bị vi phạm, database từ chối câu lệnh hoặc transaction theo quy tắc của hệ quản trị. Ứng dụng cần biết constraint nào bị vi phạm và dữ liệu đầu vào nào liên quan.

### 3.1. Unique violation

Ví dụ:

```sql
CREATE TABLE account (
    account_id BIGINT PRIMARY KEY,
    email      VARCHAR(255) NOT NULL UNIQUE
);

INSERT INTO account (account_id, email)
VALUES (1, 'lan@example.test');

INSERT INTO account (account_id, email)
VALUES (2, 'lan@example.test'); -- unique violation
```

Nếu email đã tồn tại, retry nguyên câu `INSERT` với cùng dữ liệu không giải quyết được lỗi. Ứng dụng có thể:

- Trả kết quả `EMAIL_ALREADY_REGISTERED`.
- Đọc lại tài khoản hiện có nếu nghiệp vụ cho phép liên kết hoặc cập nhật.
- Dùng UPSERT nếu yêu cầu thực sự là insert-if-absent/update-if-present.
- Với idempotency key, kiểm tra xem đây có phải request đã được xử lý trước đó không.

Không được tự động biến mọi unique violation thành UPSERT. Vi phạm có thể xảy ra trên một unique key khác với khóa nghiệp vụ mà ứng dụng định dùng; cập nhật nhầm dòng có thể làm sai dữ liệu.

### 3.2. Foreign key violation

Ví dụ:

```sql
INSERT INTO orders (order_id, customer_id)
VALUES (9001, 404);
```

Nếu không có khách hàng `404`, database từ chối insert. Lỗi này thường cho biết tham chiếu đầu vào không hợp lệ hoặc thứ tự tạo dữ liệu chưa đúng.

Trong một workflow có nhiều transaction, đôi khi dòng cha đang được tạo đồng thời và transaction con chạy trước. Nếu ứng dụng biết rõ đây là tình huống tạm thời có thể xảy ra do thứ tự xử lý, nó có thể đọc lại/trì hoãn/retry theo một chính sách giới hạn sau khi xác định trạng thái transaction cha. Tuy nhiên, retry mù một foreign key violation thường không hữu ích: nếu ID cha không tồn tại thật, lỗi sẽ lặp lại.

### 3.3. Check và NOT NULL violation

Ví dụ:

```sql
CREATE TABLE inventory (
    sku      VARCHAR(40) PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0)
);

INSERT INTO inventory (sku, quantity)
VALUES ('A-17', -5); -- CHECK violation
```

Nếu dữ liệu đầu vào là `-5`, retry không thay đổi gì. Cần trả lỗi dữ liệu hoặc lỗi nghiệp vụ phù hợp. Nếu ứng dụng tin rằng dữ liệu hợp lệ nhưng database lại từ chối, cần kiểm tra sự khác nhau giữa validation ở ứng dụng và constraint trong schema.

### 3.4. Constraint là hàng rào cuối cùng

Kiểm tra dữ liệu ở tầng ứng dụng giúp đưa ra thông báo sớm và dễ hiểu, nhưng không thay thế constraint. Hai request có thể cùng kiểm tra một điều kiện trước khi ghi. Unique constraint hoặc foreign key mới là nơi bảo vệ toàn vẹn dưới cạnh tranh.

Một quy trình an toàn thường kết hợp:

1. Validation ở ứng dụng để trả phản hồi dễ hiểu.
2. Transaction để gom các thay đổi liên quan.
3. Constraint ở database để bảo vệ dữ liệu trước mọi đường ghi.
4. Xử lý exception constraint cụ thể để ánh xạ sang phản hồi hoặc luồng nghiệp vụ.

## 4. Lỗi đồng thời tạm thời (Transient Concurrency Errors)

Lỗi đồng thời tạm thời xảy ra khi transaction không thể tiếp tục do tương tác với transaction khác. Sau khi transaction cạnh tranh kết thúc hoặc hệ thống chọn một thứ tự thực thi khác, cùng một thao tác có thể thành công.

Các loại thường gặp:

- **Deadlock:** hai hoặc nhiều transaction chờ tài nguyên mà transaction còn lại đang giữ, tạo thành chu trình chờ. DBMS thường chọn một transaction làm nạn nhân và rollback nó để phá chu trình.
- **Serialization failure:** DBMS phát hiện lịch đồng thời không thể được chấp nhận ở mức cô lập yêu cầu, nên hủy một transaction.
- **Lock wait timeout:** transaction chờ khóa quá thời gian cấu hình và bị từ chối tiếp tục.
- **Snapshot/update conflict:** transaction cố ghi một phiên bản đã bị transaction khác thay đổi theo quy tắc snapshot/isolation của DBMS.
- **Resource busy/lock unavailable:** thao tác yêu cầu khóa ngay lập tức nhưng tài nguyên đang bị khóa hoặc chính sách `NOWAIT` không cho phép chờ.

Những lỗi này có thể retry, nhưng chỉ sau khi transaction hiện tại đã được rollback hoặc đưa về trạng thái hợp lệ để bắt đầu transaction mới.

## 5. Deadlock và cách xử lý

Giả sử hai transaction cập nhật hai tài khoản theo thứ tự ngược nhau:

```text
T1                              T2
---------------------------     ---------------------------
BEGIN                           BEGIN
UPDATE account A                UPDATE account B
giữ khóa A                      giữ khóa B
                                UPDATE account A -> chờ T1
UPDATE account B -> chờ T2
```

T1 chờ khóa B do T2 giữ; T2 chờ khóa A do T1 giữ. Hai transaction không thể tiếp tục. DBMS phát hiện deadlock và chọn một transaction làm victim.

Ứng dụng nhận lỗi deadlock từ transaction bị hủy. Cách xử lý thông thường:

1. Rollback transaction thất bại theo yêu cầu của DBMS/driver.
2. Đợi một khoảng ngắn có jitter.
3. Bắt đầu transaction mới.
4. Đọc lại dữ liệu và thực hiện lại toàn bộ thao tác nghiệp vụ.
5. Dừng sau số lần retry tối đa; nếu vẫn thất bại, trả lỗi có thể thử lại hoặc ghi nhận để xử lý sau.

Một biện pháp giảm deadlock là yêu cầu mọi luồng cập nhật nhiều tài khoản theo cùng một thứ tự, ví dụ luôn khóa tài khoản có ID nhỏ trước. Điều này không loại bỏ mọi deadlock nhưng giảm khả năng các transaction giữ tài nguyên theo thứ tự đối nghịch.

Không nên chỉ chạy lại câu `UPDATE` cuối cùng sau deadlock. Các quyết định và dữ liệu đã đọc trước đó có thể không còn hợp lệ; cần chạy lại toàn bộ transaction với snapshot/trạng thái mới.

## 6. Serialization failure và snapshot conflict

Ở mức cô lập `SERIALIZABLE`, hệ quản trị có thể phát hiện một lịch thực thi đồng thời không tương đương với bất kỳ thứ tự tuần tự nào. Khi đó, một transaction bị hủy để bảo toàn tính đúng đắn.

Ví dụ, hai giao dịch cùng đọc một quy tắc “ít nhất một bác sĩ đang trực” rồi mỗi giao dịch tắt trạng thái của một bác sĩ khác nhau. Nếu cả hai cùng commit, quy tắc bị vi phạm. Cơ chế SSI hoặc serializable validation có thể phát hiện phụ thuộc và hủy một giao dịch.

Serialization failure không có nghĩa dữ liệu đầu vào sai. Nó cho biết lần chạy này không thể commit trong lịch đồng thời hiện tại. Ứng dụng có thể chạy lại transaction, đọc trạng thái mới và đưa ra quyết định mới.

Với PostgreSQL, SQLSTATE `40001` biểu thị serialization failure. PostgreSQL cũng dùng `40P01` cho deadlock detected. Với SQL Server, snapshot update conflict thường có mã lỗi `3960`; deadlock victim có mã `1205`. MySQL/InnoDB trả mã `1213` cho deadlock và thường dùng SQLSTATE `40001`. Các mã này là ví dụ theo sản phẩm; ứng dụng cần kiểm tra phiên bản và driver đang dùng.

## 7. Lock timeout không giống deadlock

Deadlock là chu trình chờ; lock timeout là một transaction đã chờ quá thời gian được cho phép. Khi timeout xảy ra, có thể transaction giữ khóa vẫn đang chạy hợp lệ nhưng chậm, hoặc một session bị treo lâu.

Ví dụ, T1 cập nhật một dòng rồi thực hiện thêm công việc trước khi commit. T2 muốn cập nhật cùng dòng và phải chờ. Nếu thời gian chờ vượt cấu hình, T2 nhận lock timeout.

Lock timeout có thể phù hợp để retry sau một khoảng chờ, nhưng cần xem xét nguyên nhân:

- Nếu transaction giữ khóa đang chạy bình thường và sắp hoàn tất, retry ngay có thể tiếp tục va chạm.
- Nếu transaction giữ khóa bị treo hoặc ứng dụng quên commit/rollback, retry nhiều lần chỉ làm tăng tải.
- Nếu timeout được cấu hình rất ngắn, hệ thống có thể tạo nhiều lỗi dù contention chỉ thoáng qua.
- Nếu câu lệnh dùng `NOWAIT`, lỗi lock unavailable là kết quả chính sách tức thời, không phải bằng chứng database hỏng.

Hãy theo dõi thời gian giữ transaction, blocker session, lock wait duration và số lần timeout. Retry nên có backoff và giới hạn, đồng thời cần sửa nguyên nhân giữ khóa quá lâu nếu đó là vấn đề chính.

## 8. Mã lỗi thường gặp theo DBMS

Các mã dưới đây giúp nhận diện nhóm lỗi. Chúng không thay thế tài liệu của phiên bản DBMS, driver hoặc framework đang sử dụng.

### 8.1. PostgreSQL

| SQLSTATE | Ý nghĩa | Nhóm thường gặp | Xử lý gợi ý |
|---|---|---|---|
| `23505` | `unique_violation` | Ràng buộc | Kiểm tra unique key; trả lỗi nghiệp vụ hoặc xử lý conflict có chủ đích |
| `23503` | `foreign_key_violation` | Ràng buộc | Kiểm tra bản ghi cha và thứ tự tạo dữ liệu |
| `23514` | `check_violation` | Ràng buộc | Sửa dữ liệu/logic; không retry mù |
| `23502` | `not_null_violation` | Ràng buộc | Bổ sung giá trị bắt buộc hoặc sửa mapping |
| `40001` | `serialization_failure` | Đồng thời tạm thời | Rollback và retry toàn bộ transaction |
| `40P01` | `deadlock_detected` | Đồng thời tạm thời | Rollback và retry có backoff; xem thứ tự lấy khóa |
| `55P03` | `lock_not_available` | Đồng thời/chính sách khóa | Kiểm tra `NOWAIT`/lock timeout; retry chỉ khi chính sách cho phép |
| `57014` | `query_canceled` | Hủy/timeout | Xác định do người dùng hủy, statement timeout hay quản trị; không mặc định retry |

PostgreSQL thường đánh dấu transaction ở trạng thái lỗi sau một statement thất bại. Ứng dụng phải rollback transaction hoặc rollback về savepoint phù hợp trước khi tiếp tục dùng transaction đó. Với serialization failure, tài liệu PostgreSQL khuyến nghị chạy lại toàn bộ transaction để các lần đọc và quyết định được làm mới.

### 8.2. MySQL / InnoDB

| Error code | Tên/ý nghĩa | Nhóm thường gặp | Xử lý gợi ý |
|---:|---|---|---|
| `1062` | Duplicate entry | Ràng buộc | Xác định unique index; xử lý duplicate theo nghiệp vụ/UPSERT |
| `1452` | Cannot add or update child row | Ràng buộc | Kiểm tra foreign key và bản ghi cha |
| `3819` | Check constraint violated | Ràng buộc | Sửa dữ liệu hoặc logic |
| `1213` | Deadlock found | Đồng thời tạm thời | Rollback transaction và retry có backoff |
| `1205` | Lock wait timeout exceeded | Đồng thời tạm thời | Kiểm tra blocker và cấu hình; xử lý transaction theo trạng thái thực tế |

MySQL/InnoDB thường rollback toàn bộ transaction của victim khi phát hiện deadlock. Với lock wait timeout, mặc định InnoDB thường rollback statement bị timeout, còn việc rollback toàn bộ transaction phụ thuộc cấu hình như `innodb_rollback_on_timeout`. Ứng dụng không nên giả định hai loại lỗi có cùng trạng thái transaction; cần rollback rõ ràng theo chính sách của ứng dụng trước khi retry.

### 8.3. SQL Server

| Error code | Ý nghĩa | Nhóm thường gặp | Xử lý gợi ý |
|---:|---|---|---|
| `2601` | Duplicate key trong unique index | Ràng buộc | Xác định index và xử lý duplicate |
| `2627` | Vi phạm PRIMARY KEY hoặc UNIQUE constraint | Ràng buộc | Trả lỗi nghiệp vụ hoặc xử lý conflict có chủ đích |
| `547` | Vi phạm FOREIGN KEY/CHECK hoặc constraint liên quan | Ràng buộc | Xác định constraint cụ thể trong message/metadata |
| `1205` | Deadlock victim | Đồng thời tạm thời | Transaction victim bị rollback; retry toàn bộ transaction |
| `1222` | Lock request timeout | Đồng thời tạm thời/chính sách | Kiểm tra transaction state và blocker trước khi retry |
| `3960` | Snapshot isolation transaction aborted due to update conflict | Đồng thời tạm thời | Bắt đầu transaction mới và đọc lại dữ liệu |

Với SQL Server, ứng dụng nên kiểm tra `XACT_STATE()` sau lỗi để biết transaction còn có thể commit, đang ở trạng thái không thể commit hay không còn transaction. Một số lỗi làm transaction trở thành uncommittable; khi đó cần rollback trước khi bắt đầu công việc mới. Không được tiếp tục ghi trong một transaction đang ở trạng thái lỗi chỉ vì câu lệnh tiếp theo vẫn được gửi đi.

### 8.4. Oracle Database

| Error code | Ý nghĩa | Nhóm thường gặp | Xử lý gợi ý |
|---|---|---|---|
| `ORA-00001` | Unique constraint violated | Ràng buộc | Xác định constraint và xử lý duplicate |
| `ORA-02291` | Parent key not found | Ràng buộc | Kiểm tra bản ghi cha của foreign key |
| `ORA-02290` | Check constraint violated | Ràng buộc | Sửa dữ liệu hoặc logic |
| `ORA-00060` | Deadlock detected | Đồng thời tạm thời | Statement bị lỗi; rollback theo transaction policy rồi retry toàn bộ công việc phù hợp |
| `ORA-08177` | Cannot serialize access for this transaction | Đồng thời tạm thời | Retry transaction ở mức cô lập serializable |
| `ORA-30006` | Resource busy; acquire with WAIT timeout expired | Đồng thời/chờ khóa | Xem blocker và chính sách timeout |

Oracle thường rollback statement gây lỗi, nhưng không phải mọi lỗi đều tự động rollback toàn bộ transaction. Ứng dụng cần quyết định rõ có rollback transaction hiện tại hay dùng savepoint để khôi phục phần công việc. Với deadlock và serialization failure, việc retry phải bắt đầu từ một ranh giới transaction hợp lệ.

## 9. Phân biệt lỗi theo mã và theo ngữ cảnh

Không nên chỉ dựa vào một mã tổng quát nếu mã đó có thể xuất hiện trong nhiều tình huống. Ví dụ:

- SQLSTATE class `23` trong PostgreSQL chỉ ra integrity constraint violation; cần đọc mã con như `23505` hoặc `23503` để biết loại constraint.
- SQLSTATE `40001` thường biểu thị transaction rollback do serialization/deadlock theo DBMS, nhưng vendor code vẫn giúp phân biệt nguyên nhân cụ thể.
- MySQL lock wait timeout dùng SQLSTATE `HY000` cùng error code `1205`; chỉ nhìn SQLSTATE tổng quát có thể không đủ.
- SQL Server và Oracle thường cần kết hợp vendor error number với trạng thái transaction và ngữ cảnh câu lệnh.

Một bộ phân loại nên xem xét ít nhất:

1. Vendor/database product và phiên bản.
2. SQLSTATE nếu driver cung cấp.
3. Vendor error code.
4. Tên constraint hoặc tên resource nếu có.
5. Transaction hiện tại đã rollback, còn hoạt động hay ở trạng thái không thể commit.
6. Loại thao tác và quy tắc nghiệp vụ đang thực hiện.

Message chỉ nên dùng cho log/chẩn đoán hoặc làm thông tin bổ sung, không nên là khóa chính của logic retry.

## 10. Quyết định retry: khi nào nên, khi nào không?

| Loại lỗi | Retry tự động? | Hành động thường phù hợp |
|---|---|---|
| Số dư không đủ, đơn hàng đã đóng, coupon hết hạn | Không | Trả lỗi nghiệp vụ; chờ người dùng hoặc sự kiện nghiệp vụ thay đổi |
| Unique violation do username đã tồn tại | Không | Trả `USERNAME_ALREADY_TAKEN` hoặc xử lý duplicate theo yêu cầu |
| Foreign key không có bản ghi cha | Thường không | Kiểm tra dữ liệu tham chiếu và thứ tự tạo dữ liệu |
| Check/NOT NULL violation | Không | Sửa dữ liệu đầu vào hoặc mapping |
| Deadlock victim | Có thể | Rollback, backoff, chạy lại toàn bộ transaction có giới hạn |
| Serialization failure | Có thể | Bắt đầu transaction mới, đọc lại và chạy lại toàn bộ logic |
| Lock wait timeout | Có điều kiện | Xác định blocker, transaction state và chính sách timeout trước khi retry |
| Người dùng hủy query | Không mặc định | Tôn trọng cancellation; không tự chạy lại công việc đã bị hủy |
| Kết nối mất trong lúc commit | Chưa xác định | Xử lý kết quả commit không rõ bằng idempotency/reconciliation |

Một unique violation đôi khi xuất hiện do hai request cùng tạo một tài nguyên. Nếu nghiệp vụ muốn “tạo một lần, các request lặp nhận lại cùng kết quả”, hãy dùng idempotency key hoặc UPSERT/`DO NOTHING` có chủ đích. Đây là xử lý conflict theo thiết kế, không phải retry vô điều kiện.

## 11. Retry toàn bộ transaction như thế nào?

Với deadlock hoặc serialization failure, cách an toàn thường là chạy lại toàn bộ đơn vị công việc transaction. Không nên chỉ gửi lại câu SQL cuối cùng vì những dữ liệu đã đọc trước đó có thể đã thay đổi.

Pseudocode:

```text
for attempt in 1..MAX_ATTEMPTS:
    begin new transaction
    try:
        read current data
        validate business conditions
        perform all writes
        commit
        return success

    catch error:
        rollback if transaction is still active

        if error is a retryable concurrency error
           and attempt < MAX_ATTEMPTS:
            wait with exponential backoff and jitter
            continue

        throw mapped error
```

Một ví dụ Java mang tính khái niệm:

```java
Result executeWithRetry(Command command) {
    int maxAttempts = 4;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return transactionTemplate.execute(status -> {
                // Toàn bộ logic được chạy lại trong transaction mới.
                Account account = repository.findForUpdate(command.accountId());
                validateBusinessRules(account, command);
                repository.apply(command);
                return Result.success();
            });
        } catch (RuntimeException ex) {
            if (!isTransientConcurrencyError(ex) || attempt == maxAttempts) {
                throw mapToApplicationError(ex);
            }

            sleepWithBackoffAndJitter(attempt);
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

Đây là pseudocode. Trong ứng dụng thực tế, `transactionTemplate.execute` phải thực sự mở transaction mới ở mỗi lần gọi. Không đặt vòng retry bên trong một transaction đã bị đánh dấu rollback-only hoặc đã mất tính hợp lệ.

### 11.1. Backoff và jitter

Nếu nhiều request cùng bị deadlock rồi lập tức retry, chúng có thể va chạm lại theo đúng nhịp cũ. Exponential backoff tăng dần thời gian chờ; jitter thêm một độ lệch ngẫu nhiên để các request không đồng loạt thử lại.

Ví dụ thời gian chờ cơ sở:

```text
attempt 1: 50 ms  + jitter
attempt 2: 100 ms + jitter
attempt 3: 200 ms + jitter
attempt 4: dừng, trả lỗi
```

Giới hạn thời gian chờ tối đa và tổng deadline của request. Retry không nên kéo dài quá thời gian client còn chờ hoặc quá SLA của dịch vụ.

### 11.2. Retry cần có giới hạn

Không retry vô hạn. Cần cấu hình:

- Số lần thử tối đa.
- Backoff tối thiểu/tối đa và jitter.
- Tổng thời gian cho phép của request.
- Danh sách lỗi được retry theo DBMS/driver.
- Metric về số lần retry, lỗi cuối cùng và tỷ lệ thành công sau retry.

Nếu lỗi tăng đột biến, hãy kiểm tra contention, transaction quá dài, thứ tự truy cập tài nguyên, index và tải hệ thống thay vì chỉ tăng số lần retry.

## 12. Đảm bảo rollback trước khi retry

Một điểm khác biệt giữa DBMS là trạng thái transaction sau khi statement thất bại.

| DBMS | Một số hành vi cần lưu ý |
|---|---|
| PostgreSQL | Một statement error thường khiến transaction ở trạng thái aborted; cần `ROLLBACK` hoặc rollback về savepoint trước khi tiếp tục |
| MySQL/InnoDB | Deadlock thường rollback toàn bộ transaction victim; lock wait timeout mặc định thường rollback statement, có thể cấu hình rollback toàn transaction |
| SQL Server | Tùy lỗi và `XACT_ABORT`, transaction có thể còn hoạt động hoặc không thể commit; kiểm tra `XACT_STATE()` |
| Oracle | Nhiều lỗi rollback statement; transaction có thể tiếp tục, nhưng ứng dụng vẫn cần chọn rollback/savepoint phù hợp |

Vì khác biệt này, một lớp truy cập dữ liệu không nên giả định “có exception nghĩa là transaction đã rollback”. Hãy dùng transaction manager/framework đúng cách, kiểm tra trạng thái khi cần và đảm bảo connection không được trả về pool trong trạng thái transaction lỗi hoặc còn khóa ngoài ý muốn.

Nếu một lỗi constraint xảy ra bên trong transaction nhiều bước, rollback toàn transaction thường là lựa chọn an toàn nếu ứng dụng không có savepoint được thiết kế trước. Savepoint cho phép rollback một phần công việc trong một số trường hợp, nhưng không thể dùng để biến mọi lỗi thành có thể tiếp tục; đặc biệt cần hiểu quy tắc của DBMS và transaction manager.

## 13. Kết quả COMMIT không rõ và lỗi kết nối

Một trường hợp cần tách riêng là client mất kết nối đúng lúc gửi `COMMIT`. Ứng dụng có thể không biết transaction đã commit ở server hay chưa. Đây không đơn giản là lỗi đồng thời có thể retry ngay.

```text
Client gửi COMMIT
       |
       v
Database commit thành công
       |
       +---- phản hồi bị mất trên mạng
       |
       v
Client nhận lỗi kết nối / timeout
```

Nếu client chạy lại transaction mà lần trước thực sự đã commit, thao tác có thể bị thực hiện hai lần. Với các thao tác tạo đơn hàng, thu tiền hoặc phát hành giao dịch, điều này có thể gây hậu quả lớn.

Hướng xử lý:

1. Dùng idempotency key duy nhất cho mỗi yêu cầu nghiệp vụ.
2. Ghi kết quả xử lý và idempotency key trong cùng transaction với thay đổi nghiệp vụ.
3. Khi kết quả commit không rõ, truy vấn lại trạng thái bằng idempotency key để xác định transaction trước đã được ghi nhận chưa.
4. Chỉ chạy lại thao tác nếu có thể chứng minh lần trước chưa được áp dụng hoặc thao tác được thiết kế idempotent.
5. Với tác dụng phụ ngoài database, dùng transactional outbox và idempotent consumer để tránh phát trùng sự kiện.

Không phân loại mọi lỗi network/timeout thành transient concurrency error. Có lỗi hạ tầng có thể retry, nhưng kết quả commit không rõ cần reconciliation trước khi thực hiện lại.

## 14. Ranh giới transaction và tác dụng phụ ngoài database

Retry toàn bộ transaction có nghĩa phần code bên trong transaction có thể chạy nhiều lần. Nếu code đó gửi email, gọi API thanh toán hoặc ghi file bên ngoài trước khi commit, lần retry có thể lặp tác dụng phụ.

Ví dụ không an toàn:

```text
BEGIN
  cập nhật đơn hàng
  gọi dịch vụ gửi email
  deadlock -> rollback

RETRY
  cập nhật đơn hàng
  gọi dịch vụ gửi email lần nữa
  commit
```

Email có thể đã được gửi ở lần đầu dù transaction database rollback. Khi retry, khách hàng nhận hai email.

Nên lưu ý định phát sự kiện trong cùng transaction:

```sql
BEGIN;

UPDATE orders
SET status = 'PAID'
WHERE order_id = :order_id;

INSERT INTO outbox_event (event_id, event_type, payload, created_at)
VALUES (:event_id, 'ORDER_PAID', :payload, CURRENT_TIMESTAMP);

COMMIT;
```

Một worker riêng đọc outbox sau commit và gửi sự kiện. Consumer vẫn cần idempotency vì message có thể được giao lại. Cách này giúp transaction retry không gửi email/message trước khi dữ liệu được commit.

## 15. Thiết kế bộ ánh xạ lỗi ở tầng ứng dụng

Một kiến trúc dễ bảo trì thường tách ba lớp:

| Lớp | Trách nhiệm |
|---|---|
| Database/driver adapter | Đọc SQLSTATE, vendor code, constraint name và trạng thái transaction |
| Transaction policy | Quyết định lỗi nào retry, rollback, backoff hoặc dừng |
| Application/domain layer | Ánh xạ lỗi thành mã nghiệp vụ và phản hồi API |

Ví dụ về kiểu phân loại nội bộ:

```java
enum FailureKind {
    BUSINESS,
    CONSTRAINT,
    TRANSIENT_CONCURRENCY,
    UNKNOWN
}
```

Một adapter PostgreSQL có thể ánh xạ `23505` thành `CONSTRAINT`, `40001` và `40P01` thành `TRANSIENT_CONCURRENCY`. Adapter SQL Server có thể dùng vendor code `1205` hoặc `3960` cho lỗi đồng thời, còn `2601`/`2627` cho unique violation. Không nên đưa toàn bộ mã vendor vào domain layer; hãy giữ logic đặc thù DBMS trong adapter.

Lớp nghiệp vụ có thể ánh xạ một constraint cụ thể thành lỗi dễ hiểu:

```text
PostgreSQL 23505 + constraint uq_customer_email
        |
        v
Application error: EMAIL_ALREADY_REGISTERED
        |
        v
HTTP 409 Conflict
```

Một constraint khác có thể được ánh xạ sang lỗi khác. Chỉ mã `23505` chưa đủ để kết luận đó là email; cần xác định constraint/index thực sự gây lỗi.

## 16. Ghi log và metric phục vụ chẩn đoán

Log nên giúp xác định nguyên nhân mà không làm lộ dữ liệu nhạy cảm. Các trường hữu ích:

- Mã transaction/request và idempotency key đã được che hoặc băm phù hợp.
- Tên thao tác nghiệp vụ và loại câu lệnh.
- DBMS, phiên bản, SQLSTATE và vendor error code.
- Constraint name hoặc resource/index liên quan nếu có.
- Transaction attempt, số lần retry và thời gian backoff.
- Transaction state sau lỗi và kết quả rollback.
- Thời gian giữ transaction, lock wait duration và blocker nếu DBMS cung cấp.
- Kết quả cuối: thành công sau retry, lỗi nghiệp vụ, lỗi constraint hay hết số lần retry.

Metric nên phân tách:

| Metric | Điều cần quan sát |
|---|---|
| `business_rejection_count` | Yêu cầu bị từ chối theo quy tắc nghiệp vụ |
| `constraint_violation_count` | Unique/FK/CHECK/NOT NULL violation theo constraint |
| `deadlock_count` | Số transaction bị chọn làm deadlock victim |
| `serialization_failure_count` | Số transaction bị hủy do serialization |
| `lock_timeout_count` | Số lần chờ khóa vượt timeout |
| `transaction_retry_count` | Tổng số lần retry và số lần retry trên mỗi request |
| `retry_success_rate` | Tỷ lệ lần chạy lại thành công |
| `unknown_commit_outcome_count` | Số request mất kết nối hoặc timeout trong lúc commit |

Nếu gộp tất cả thành một metric `database_error_count`, đội vận hành khó biết cần sửa validation, schema, query, transaction duration hay chính sách retry.

## 17. Các lỗi phân loại thường gặp

**Retry mọi exception.** Điều này làm lặp các lỗi nghiệp vụ và constraint không thể tự biến mất. Hãy retry đúng danh sách lỗi đồng thời tạm thời.

**Coi mọi duplicate key là deadlock hoặc lỗi tạm thời.** Unique violation thường là kết quả xác định của dữ liệu hiện tại. Chỉ xử lý theo UPSERT/idempotency nếu nghiệp vụ cho phép.

**Coi mọi timeout là lock timeout.** Timeout có thể đến từ client, query execution, network hoặc thời gian chờ khóa. Cần xác định nguồn timeout trước khi retry.

**Chỉ retry câu SQL phát sinh exception.** Các lần đọc trước đó có thể đã lỗi thời. Với serialization failure/deadlock, thường phải rollback và chạy lại toàn bộ transaction.

**Giả định statement error luôn rollback transaction.** Quy tắc khác nhau giữa PostgreSQL, MySQL, SQL Server và Oracle. Phải kiểm tra trạng thái transaction và rollback phù hợp.

**Chuyển mọi constraint violation thành lỗi 400 chung.** Một số lỗi có thể là xung đột tài nguyên hiện có (409), dữ liệu không hợp lệ (422) hoặc lỗi nội bộ do ứng dụng vi phạm invariant. Cần ánh xạ theo ý nghĩa API.

**Retry sau khi COMMIT có kết quả không rõ.** Nếu lần trước đã commit, thao tác chạy lại có thể tạo tác dụng phụ trùng. Dùng idempotency key và reconciliation.

## 18. Quy trình quyết định trong thực tế

Khi transaction thất bại, có thể áp dụng trình tự sau:

1. Thu thập SQLSTATE, vendor code, constraint/resource name và trạng thái transaction.
2. Nếu lỗi được ứng dụng chủ động phát ra do quy tắc nghiệp vụ, trả mã nghiệp vụ; không retry tự động.
3. Nếu lỗi thuộc nhóm constraint, xác định constraint cụ thể và kiểm tra dữ liệu đầu vào hoặc trạng thái hiện có. Chỉ dùng UPSERT/đọc lại khi đó là hành vi nghiệp vụ được định nghĩa.
4. Nếu lỗi là deadlock, serialization failure hoặc xung đột snapshot, rollback transaction và chạy lại toàn bộ logic trong transaction mới với số lần giới hạn.
5. Nếu lỗi là lock timeout hoặc lock unavailable, kiểm tra blocker, timeout policy và transaction state trước khi quyết định retry.
6. Nếu kết nối mất trong lúc commit, xác định kết quả bằng idempotency key/reconciliation trước khi chạy lại.
7. Nếu không nhận diện được lỗi, không tự động retry vô hạn; ghi log đầy đủ và chuyển sang xử lý lỗi chung.
8. Theo dõi metric theo từng nhóm để điều chỉnh schema, query, transaction duration và retry policy.

## 19. Nguyên tắc ghi nhớ

Lỗi nghiệp vụ cho biết yêu cầu không thỏa quy tắc của ứng dụng; thường cần trả kết quả có ý nghĩa để người gọi thay đổi yêu cầu hoặc chờ điều kiện nghiệp vụ thay đổi. Lỗi ràng buộc cho biết database đã bảo vệ tính toàn vẹn và từ chối dữ liệu; cần xác định constraint cùng dữ liệu liên quan, sau đó trả lỗi hoặc xử lý conflict có chủ đích. Lỗi đồng thời tạm thời cho biết lần chạy hiện tại không thể hoàn tất trong trạng thái cạnh tranh đó; có thể retry sau rollback, backoff và đọc lại dữ liệu trong transaction mới.

Phân loại đúng giúp ứng dụng không retry những việc chắc chắn thất bại, không bỏ cuộc quá sớm với xung đột tạm thời và không thực hiện một giao dịch hai lần khi kết quả commit chưa rõ. Đây là nền tảng để xây dựng transaction policy ổn định và phản hồi lỗi nhất quán cho người dùng.
