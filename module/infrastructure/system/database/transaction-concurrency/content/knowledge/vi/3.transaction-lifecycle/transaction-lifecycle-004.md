# Trạng thái giao dịch sau lỗi câu lệnh hoặc lỗi kết nối

Trong hệ thống có nhiều giao dịch đồng thời, một lỗi SQL không chỉ làm hỏng câu lệnh hiện tại: nó còn có thể ảnh hưởng đến **toàn bộ giao dịch**, các khóa đang giữ, những thay đổi chưa commit và quyền tiếp tục sử dụng kết nối. Đặc biệt, khi kết nối bị đứt đúng lúc gửi `COMMIT`, ứng dụng có thể **không biết giao dịch đã commit hay chưa**. Nhầm lẫn giữa “có exception”, “đã rollback” và “chưa nhận phản hồi commit” có thể gây mất dữ liệu, ghi trùng đơn hàng hoặc thanh toán hai lần.

Bài học này đặt vấn đề trong **vòng đời giao dịch** (*transaction lifecycle*) của cơ sở dữ liệu, tập trung vào hai tình huống:

- **Lỗi câu lệnh:** SQL sai cú pháp, vi phạm ràng buộc, deadlock, serialization failure, timeout hoặc một lỗi thực thi khác khi kết nối vẫn tồn tại.
- **Lỗi kết nối:** mất mạng, database đóng session, process bị dừng, kết nối trong pool không còn hợp lệ hoặc client mất phản hồi trong khi transaction đang chạy/commit.

Điều cốt lõi là phải tách biệt **trạng thái phía database** và **những gì client biết chắc**. Hai phía đôi khi không còn đồng bộ nhận thức về kết quả cuối cùng.

## 1. Nhắc lại các mốc trong vòng đời transaction

Một giao dịch thông thường trải qua các bước:

```text
Kết nối sẵn sàng
      |
      | BEGIN / setAutoCommit(false)
      v
Đang thực thi transaction
      |
      +-- Câu lệnh thành công --> tiếp tục đọc/ghi
      |
      +-- ROLLBACK ------------> hủy các thay đổi chưa commit
      |
      +-- COMMIT thành công ---> thay đổi được xác nhận
      |
      +-- Có lỗi --------------> cần biết database đã xử lý trạng thái ra sao
```

Trước `COMMIT`, các thay đổi thông thường chưa trở thành kết quả bền vững của giao dịch. Nếu transaction bị rollback, toàn bộ thay đổi của transaction đó được hủy (ngoại trừ các hiệu ứng bên ngoài hệ quản trị giao dịch như gọi HTTP hoặc gửi email; chúng không tự bị hoàn tác).

Với một transaction đang mở, cần phân biệt những trạng thái sau:

| Trạng thái / góc nhìn | Ý nghĩa |
|---|---|
| **Chưa có transaction** (*idle*) | Kết nối sẵn sàng thực thi thao tác hoặc bắt đầu giao dịch mới. |
| **Transaction đang hoạt động** (*active / in transaction*) | Đã mở transaction; có thể đọc/ghi và có những thay đổi chưa commit. |
| **Transaction bị lỗi** (*failed / aborted*) | Database đánh dấu transaction không thể tiếp tục thực thi lệnh thông thường; phải rollback hoặc quay về savepoint hợp lệ, tùy database. |
| **Đã commit** (*committed*) | Database xác nhận giao dịch; dữ liệu được giữ theo bảo đảm của hệ quản trị. |
| **Đã rollback** (*rolled back*) | Các thay đổi chưa commit thuộc phạm vi rollback bị hủy. |
| **Kết quả chưa xác định với client** (*outcome unknown / in doubt*) | Client không có đủ bằng chứng để kết luận transaction đã commit hay rollback, thường do mất phản hồi khi commit. |

**“Outcome unknown” không nhất thiết là một trạng thái nội bộ của database.** Database có thể đã commit hoặc rollback xong, trong khi ứng dụng chỉ biết rằng không nhận được phản hồi. Sự phân biệt này là trọng tâm khi xử lý lỗi kết nối.

### Statement, transaction và connection là ba phạm vi khác nhau

- **Statement:** một câu SQL được thực thi. Câu lệnh thất bại không nhất thiết buộc toàn bộ transaction thất bại trên mọi hệ quản trị.
- **Transaction:** đơn vị phải commit hoặc rollback cùng nhau. Một transaction có thể gồm nhiều câu lệnh trên cùng kết nối.
- **Connection/session:** kênh giao tiếp với database, có thể mang một transaction đang mở. Khi session bị đóng thực sự, transaction chưa commit thông thường được database rollback; nhưng thời điểm database phát hiện mất kết nối có thể muộn hơn thời điểm client phát hiện sự cố.

Vì thế, khi nghe “câu `UPDATE` lỗi”, câu hỏi tiếp theo cần là: **đang dùng database nào, có mở transaction tường minh không, loại lỗi nào đã xảy ra và kết nối còn sử dụng được không?**

## 2. Sau lỗi SQL, giao dịch có thể ở trạng thái nào?

Không nên đưa ra quy tắc chung rằng “mỗi lỗi SQL chỉ rollback câu lệnh” hoặc “mỗi lỗi SQL tự rollback cả transaction”. Hai hệ quản trị có thể xử lý khác nhau; thậm chí cùng một hệ quản trị cũng xử lý khác nhau tùy loại lỗi.

### 2.1. PostgreSQL: một lỗi thông thường làm transaction tường minh thành `aborted`

Trong PostgreSQL, sau lỗi câu lệnh khi đang ở transaction tường minh (`BEGIN ...`), transaction thường chuyển sang trạng thái **failed**. Database từ chối các câu SQL thông thường tiếp theo cho đến khi ứng dụng `ROLLBACK` hoặc, nếu đã đặt savepoint thích hợp, `ROLLBACK TO SAVEPOINT`.

Thông báo quen thuộc:

```text
ERROR: current transaction is aborted,
commands ignored until end of transaction block
SQLSTATE: 25P02
```

Mã `25P02` (*in_failed_sql_transaction*) biểu thị rằng **transaction đã hỏng từ một lỗi trước đó**. Nó thường không phải nguyên nhân ban đầu. Cần xem lỗi đầu tiên, chẳng hạn `23505` khi vi phạm unique constraint.

Một kết nối PostgreSQL vẫn còn sống sau lỗi này có thể sử dụng lại **sau khi transaction được rollback**. Ngược lại, việc tiếp tục gửi `SELECT` hoặc `UPDATE` trong transaction failed chỉ sinh thêm `25P02`.

### 2.2. Transaction tự động cho từng lệnh khác transaction nhiều lệnh

Khi dùng *autocommit*, mỗi câu SQL độc lập được database xử lý như một transaction riêng (theo mô hình sử dụng thông thường):

```text
Statement 1 thành công → transaction 1 đã commit
Statement 2 thất bại  → transaction 2 bị hủy/thất bại
Statement 3           → transaction 3 độc lập
```

**Lệnh 2 thất bại không tự động hủy lệnh 1 đã commit.** Điều này rất quan trọng nếu nghiệp vụ cần nhiều lệnh cùng thành công hoặc cùng thất bại: bạn phải mở transaction bao quanh chúng.

Với JDBC, `Connection` mặc định thường ở chế độ `autoCommit = true`; khi gọi `setAutoCommit(false)`, các câu lệnh tiếp theo thuộc một transaction cho đến khi `commit()` hoặc `rollback()`. Không nên suy luận ranh giới transaction từ việc các câu lệnh cùng được gọi trong một hàm Java.

### 2.3. MySQL InnoDB có thể chỉ rollback câu lệnh bị lỗi

Ví dụ trong MySQL InnoDB, lỗi duplicate key thường làm **câu `INSERT` đang lỗi** bị hủy, trong khi transaction vẫn có thể tiếp tục. Deadlock lại thường khiến InnoDB chọn một transaction làm nạn nhân và rollback **cả transaction đó**. Với lock wait timeout, cấu hình mặc định InnoDB thường chỉ rollback **statement** bị timeout; tùy cấu hình `innodb_rollback_on_timeout`, hành vi có thể khác.

| Tình huống minh họa | PostgreSQL trong transaction tường minh | MySQL InnoDB (hành vi thường gặp) |
|---|---|---|
| Duplicate key khi `INSERT` | Transaction vào trạng thái failed; cần rollback hoặc xử lý qua savepoint | Thường hủy statement, transaction vẫn hoạt động |
| Deadlock | Transaction bị hủy; cần bắt đầu transaction mới | Transaction nạn nhân thường bị rollback toàn bộ |
| Lỗi chờ khóa quá lâu | Statement có thể bị hủy và transaction vào failed state | Mặc định thường rollback statement, có thể cấu hình rollback toàn transaction |
| Lệnh sau lỗi có chạy ngay không? | Không, nếu transaction đang failed và chưa được phục hồi | Tùy loại lỗi và trạng thái transaction |

Bảng chỉ mô tả các trường hợp phổ biến. Khi viết mã đa cơ sở dữ liệu, cần tra đúng tài liệu phiên bản, cấu hình và driver của hệ quản trị đang dùng. **Cách an toàn ở tầng nghiệp vụ** thường là: nếu một bước bắt buộc thất bại, chủ động rollback toàn transaction và quyết định retry hoặc trả lỗi tại một nơi rõ ràng.

## 3. Thí nghiệm PostgreSQL: lỗi một lệnh ảnh hưởng các lệnh sau

Tạo bảng ví dụ trong PostgreSQL, chạy một lần trên database thử nghiệm:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0)
);

INSERT INTO accounts (id, balance)
VALUES (1, 1000.00), (2, 500.00);
```

Giả sử nghiệp vụ cần chuyển 100 từ tài khoản 1 sang tài khoản 2. Thử cố tình tạo lỗi unique constraint trong cùng transaction.

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;
-- Thành công trong transaction: số dư id=1 hiện là 900.

INSERT INTO accounts (id, balance)
VALUES (2, 999.00);
-- ERROR: duplicate key value violates unique constraint
-- SQLSTATE 23505

SELECT balance
FROM accounts
WHERE id = 1;
-- ERROR: current transaction is aborted
-- SQLSTATE 25P02
```

Lúc này:

1. `UPDATE` đầu tiên đã chạy thành công **trong phạm vi transaction**, nhưng chưa commit.
2. `INSERT` lỗi do `id = 2` đã tồn tại.
3. Transaction PostgreSQL chuyển sang failed; `SELECT` tiếp theo không được chạy bình thường.
4. `UPDATE` thành công trước lỗi **không tự trở thành dữ liệu đã commit**.

Kết thúc đúng cách:

```sql
ROLLBACK;

SELECT id, balance
FROM accounts
ORDER BY id;
-- id=1: 1000.00
-- id=2:  500.00
```

Sau `ROLLBACK`, kết nối trở lại trạng thái sẵn sàng và các thay đổi chưa commit đều được hủy.

### Nếu thử `COMMIT` trong transaction PostgreSQL đang failed?

Khi transaction đang ở aborted state, `COMMIT` **không làm các thay đổi trước lỗi được commit**. PostgreSQL kết thúc bằng rollback (trong `psql` thường thấy nhãn kết quả `ROLLBACK`). Vì vậy không được coi “ứng dụng đã gọi `commit()`” là bằng chứng dữ liệu đã được commit; phải dựa trên kết quả thực sự từ database.

Thói quen tốt: nếu không thể hoàn thành đúng tất cả bước nghiệp vụ, **chủ động gọi `ROLLBACK`** và trả lỗi có ngữ cảnh, thay vì dựa vào cách database diễn giải `COMMIT` sau một transaction hỏng.

### Lỗi do hủy câu lệnh hoặc timeout

PostgreSQL có thể báo `SQLSTATE 57014` (*query_canceled*) khi câu lệnh bị hủy, chẳng hạn do `statement_timeout`. Trong transaction tường minh, lỗi này cũng có thể làm transaction thành failed state:

```sql
BEGIN;

SET LOCAL statement_timeout = '200ms';

SELECT pg_sleep(2);
-- ERROR: canceling statement due to statement timeout

SELECT 1;
-- ERROR: current transaction is aborted

ROLLBACK;
```

`statement_timeout` giới hạn thời gian thực thi câu lệnh; nó **không thay thế** việc quản lý thời hạn cho toàn bộ transaction hoặc cho quá trình kết nối ở tầng ứng dụng. Những cấu hình khác như `lock_timeout` và `idle_in_transaction_session_timeout` xử lý các vấn đề khác nhau. Phải biết chính xác cơ chế timeout nào đã kích hoạt trước khi xác định phạm vi cần phục hồi.

## 4. Savepoint: xử lý lỗi cục bộ mà vẫn giữ giao dịch lớn

Đôi khi một thao tác là tùy chọn: cần bỏ qua lỗi ở bước phụ mà vẫn giữ các bước chính đã thực hiện. PostgreSQL hỗ trợ **savepoint** như một điểm có thể quay lại *bên trong* transaction.

```sql
BEGIN;

-- Bước chính: trừ 50 khỏi tài khoản 1.
UPDATE accounts
SET balance = balance - 50
WHERE id = 1;

-- Đánh dấu trước một bước có thể thất bại.
SAVEPOINT optional_step;

INSERT INTO accounts (id, balance)
VALUES (2, 123.00);
-- Lỗi duplicate key, transaction đang failed.

-- Hủy các thay đổi kể từ savepoint, phục hồi khả năng chạy lệnh.
ROLLBACK TO SAVEPOINT optional_step;

-- Tiếp tục bước hợp lệ.
UPDATE accounts
SET balance = balance + 50
WHERE id = 2;

RELEASE SAVEPOINT optional_step;

COMMIT;
```

Kết quả nếu mọi bước còn lại thành công: tài khoản 1 giảm 50 và tài khoản 2 tăng 50; phép `INSERT` lỗi không được giữ lại.

Các điểm cần hiểu:

- `SAVEPOINT` **không tạo một transaction độc lập**. Nếu transaction cha cuối cùng rollback, toàn bộ thay đổi của transaction cha (kể cả các bước đã thành công sau khi quay về savepoint) đều bị hủy.
- `ROLLBACK TO SAVEPOINT` chỉ hoàn tác các thay đổi sau savepoint và phục hồi trạng thái cho phép tiếp tục, nếu lỗi và trạng thái kết nối còn hỗ trợ điều đó.
- `RELEASE SAVEPOINT` bỏ điểm đánh dấu; nó **không commit** dữ liệu.
- Phải tạo savepoint **trước** câu lệnh có nguy cơ lỗi. Nếu chưa có savepoint và transaction PostgreSQL đã failed, không thể bổ sung savepoint ở thời điểm đó để cứu transaction.
- Một số lỗi nghiêm trọng làm mất kết nối hoặc buộc toàn transaction kết thúc; savepoint không thể phục hồi session đã mất.

Savepoint hữu ích cho những bước có thể chấp nhận thất bại cục bộ. Nhưng đừng dùng nó để che một lỗi bắt buộc của nghiệp vụ: nếu ghi nhật ký chuyển tiền hoặc cập nhật số dư là bắt buộc, nên rollback cả giao dịch khi một bước đó thất bại.

## 5. Lỗi do concurrency: deadlock và serialization failure

Khi nhiều giao dịch cùng chạy, có những lỗi không xuất phát từ SQL sai mà từ **xung đột giữa các transaction**.

### Deadlock

Giả sử T1 cập nhật tài khoản A rồi muốn khóa B, còn T2 cập nhật B rồi muốn khóa A:

```text
T1: giữ khóa A ----------------------> đợi khóa B
                                      ^
                                      |
                                      |
T2: giữ khóa B ----------------------> đợi khóa A

Mỗi transaction đợi khóa do transaction kia nắm giữ.
```

Hệ quản trị có thể phát hiện vòng chờ và chọn một transaction để hủy nhằm giải phóng khóa. PostgreSQL báo `SQLSTATE 40P01` (*deadlock_detected*). Transaction bị hủy phải được chạy lại **từ đầu** nếu nghiệp vụ còn cần thực hiện.

Cách giảm deadlock gồm cập nhật các tài nguyên theo một thứ tự ổn định (chẳng hạn ID tăng dần), giữ transaction ngắn và hạn chế những bước chờ không cần thiết khi đang giữ khóa. Nhưng ngay cả thiết kế tốt vẫn cần xử lý lỗi có thể xảy ra.

### Serialization failure

Ở mức `SERIALIZABLE`, database có thể phát hiện các giao dịch đồng thời mà việc cùng commit sẽ phá vỡ bảo đảm tương đương một lịch tuần tự. PostgreSQL có thể hủy một giao dịch với `SQLSTATE 40001` (*serialization_failure*).

Ví dụ, cả T1 và T2 đều đọc cùng một trạng thái lịch trực rồi cập nhật **hai hàng khác nhau**, làm mất người trực cuối cùng. Trường hợp này có thể không xuất hiện xung đột ghi trực tiếp trên cùng một hàng, nhưng vẫn có xung đột về **điều kiện nghiệp vụ đã đọc**.

Khi gặp `40001`, không chỉ lặp lại lệnh `UPDATE` cuối. Cần retry **toàn transaction**, bao gồm các phép đọc và quyết định nghiệp vụ, vì dữ liệu dùng để đưa ra quyết định trước đó đã không còn đáng tin cậy cho lần thử mới.

```text
Lần thử 1:
  BEGIN → đọc dữ liệu → kiểm tra quy tắc → ghi → 40001 → ROLLBACK

Lần thử 2 (transaction mới):
  BEGIN → đọc lại dữ liệu → kiểm tra lại → ghi → COMMIT
```

Retry cần giới hạn số lần, có thể thêm backoff ngắn có jitter khi tải tranh chấp cao, và phải đảm bảo các tác động ngoài database không bị lặp. Không phải exception SQL nào cũng có thể giải quyết bằng retry: duplicate key do đầu vào thực sự trùng thường là lỗi nghiệp vụ cần trả về cho người gọi.

## 6. Mất kết nối: tại sao client không luôn biết kết quả cuối cùng?

Khi kết nối bị cắt, ứng dụng có thể gặp `SQLException`, timeout, EOF hoặc lỗi từ driver/pool. Nhưng **thấy lỗi kết nối không chứng minh giao dịch đã rollback**.

Xét một transaction chuyển tiền:

```text
Client/JDBC                           Database
     |                                    |
     | BEGIN ---------------------------> |
     | UPDATE account A ----------------> |
     | UPDATE account B ----------------> |
     | COMMIT --------------------------> |
     |                          xử lý COMMIT
     |       X mất mạng / mất phản hồi     |
     |                                    |
     | SQLException / timeout             |
```

Ở thời điểm client mất kết nối, có ít nhất hai khả năng:

- Database **chưa nhận hoặc chưa hoàn tất `COMMIT`**, rồi rollback transaction khi session thực sự kết thúc.
- Database **đã commit thành công**, nhưng thông điệp xác nhận không đến được client.

Cả hai có thể tạo ra một exception trông tương tự ở phía ứng dụng. Vì thế không được tự động kết luận “commit thất bại nên chắc chắn chưa thay đổi dữ liệu”.

### Phân biệt các mốc mất kết nối

| Sự cố | Điều có thể biết | Điều chưa nên kết luận |
|---|---|---|
| Mất kết nối khi đang giữ transaction, **chưa gửi commit** | Thông thường DB rollback transaction chưa commit khi xác định session đóng | Đừng giả định khóa được giải phóng ngay tức thì nếu DB chưa nhận ra kết nối đã chết |
| Mất kết nối **trong lúc gửi/đợi commit** | Client không nhận xác nhận chắc chắn | Chưa thể suy ra transaction đã commit hay rollback |
| `COMMIT` đã trả về thành công rõ ràng | Client có xác nhận commit theo giao thức/đảm bảo của DB | Không cần coi transaction là chưa xác định chỉ vì sau đó kết nối hỏng |
| Connection pool báo kết nối lỗi | Cần loại bỏ/khôi phục kết nối theo chính sách pool | Pool phát hiện socket hỏng không cho biết kết quả của commit đang dở |
| Lỗi kết nối ở chế độ autocommit khi đang thực thi một câu SQL | Kết quả của statement/transaction ngầm có thể chưa rõ | Không được mặc định vì chỉ một câu SQL nên chắc chắn chưa có tác động |

Một điểm tinh tế: **client có thể phát hiện ngắt mạng trước server**. Nếu server còn coi session là sống, transaction chưa commit có thể còn giữ khóa hoặc tài nguyên cho đến khi server phát hiện kết nối chết hoặc timeout liên quan kích hoạt. Do đó timeout phía client và cleanup phía server không phải lúc nào cũng xảy ra cùng thời điểm.

### “Đã gọi rollback” có phải là bằng chứng không?

Nếu `rollback()` trả về thành công trên **kết nối còn hợp lệ và đúng transaction**, đó là phản hồi hữu ích. Nhưng nếu `commit()` vừa ném exception do đứt mạng, việc ứng dụng gọi thêm `rollback()` thường cũng thất bại hoặc không tới được session ban đầu. Dù lệnh rollback sau đó có được phát đi, **nó không thể đảo ngược một commit đã hoàn tất**.

Đặc biệt, mở **kết nối mới** rồi gọi `ROLLBACK` không thể rollback transaction cũ: transaction cũ thuộc session khác. Kết nối mới chỉ giúp **đối soát trạng thái dữ liệu**, hoặc thực hiện một thao tác bù trừ độc lập nếu nghiệp vụ cho phép.

## 7. Cách xử lý khi không rõ `COMMIT` đã thành công hay chưa

Đối với yêu cầu có thể được gửi lại, ví dụ “chuyển 200.000 đồng” hoặc “tạo đơn hàng”, một cách làm nguy hiểm là:

```text
Gửi yêu cầu → timeout lúc commit → lập tức tạo yêu cầu khác tương đương
```

Nếu yêu cầu đầu đã commit nhưng mất phản hồi, yêu cầu thứ hai có thể ghi trùng. Đây là vấn đề **idempotency** (*tính an toàn khi thực hiện lại cùng một yêu cầu*).

### Dùng một định danh nghiệp vụ ổn định

Giả sử mỗi thao tác chuyển tiền mang `request_id` duy nhất do ứng dụng hoặc client tạo. Database giữ một bản ghi nghiệp vụ có khóa duy nhất đó:

```sql
CREATE TABLE transfer_requests (
    request_id UUID PRIMARY KEY,
    from_account BIGINT NOT NULL,
    to_account BIGINT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    status TEXT NOT NULL
);
```

Trong **một transaction**, ứng dụng thực hiện:

1. Ghi nhận `request_id` với một bản ghi yêu cầu được ràng buộc duy nhất.
2. Kiểm tra các điều kiện chuyển tiền và cập nhật các tài khoản.
3. Ghi kết quả nghiệp vụ tương ứng trong cùng transaction.
4. `COMMIT`.

Nếu phản hồi commit bị mất, ứng dụng có thể kết nối lại và **tra cứu trên nguồn dữ liệu có thẩm quyền** bằng đúng `request_id`. Nếu bản ghi đã commit, trả về kết quả đã ghi nhận. Nếu thao tác cũ chưa hoàn tất, một lần thử mới dùng **cùng `request_id`**, để ràng buộc duy nhất ngăn tạo hai giao dịch nghiệp vụ thành công.

Cần xử lý thêm các trường hợp thực tế:

- Một `request_id` phải gắn với **cùng nội dung yêu cầu**; nếu ID giống nhau nhưng số tiền/người nhận khác nhau thì trả lỗi xung đột, không coi như retry hợp lệ.
- Bản ghi “chưa thấy tồn tại” ngay sau timeout **không đủ chứng minh** transaction trước chắc chắn chưa commit: có thể transaction cũ chưa kết thúc hoặc truy vấn đi qua replica trễ. Cần thiết kế đồng bộ hóa/retry với unique key, đọc từ primary hoặc nguồn nhất quán phù hợp, và có chính sách chờ/đối soát.
- Unique constraint chỉ bảo vệ định danh có lưu trong **cùng phạm vi giao dịch với tác động cần chống trùng**. Ghi request ID ở transaction khác rồi trừ tiền mà không có giao thức rõ ràng vẫn có thể để lại trạng thái dở dang.
- Với API thanh toán ngoài database, một transaction SQL không thể tự rollback hành động phía nhà cung cấp. Hãy dùng idempotency key mà đối tác hỗ trợ, kết quả nghiệp vụ có thể đối soát và một quy trình trạng thái phù hợp.

### Transactional outbox và tác động ngoài DB

Giả sử sau khi tạo đơn hàng, hệ thống phải gửi sự kiện `OrderCreated` cho service khác. Nếu gửi sự kiện **trước commit**, transaction sau đó rollback có thể khiến service khác xử lý “đơn hàng ma”. Nếu gửi sự kiện **sau commit**, process có thể chết trước khi kịp gửi.

Một mô hình phổ biến là *transactional outbox*: ghi đơn hàng và bản ghi sự kiện cần phát trong **cùng transaction**, commit chúng cùng nhau; một tiến trình khác đọc outbox để phát sự kiện sau đó. Bên nhận vẫn cần xử lý lặp/idempotent vì việc phát lại có thể xảy ra. Mô hình này giải quyết khoảng trống giữa ghi DB và gửi sự kiện, nhưng không biến hệ thống phân tán thành một transaction SQL duy nhất.

## 8. JDBC: quản lý transaction và exception đúng ranh giới

Trong Java/JDBC, `SQLException` là tín hiệu lỗi, nhưng bản thân exception **không nói đủ trạng thái transaction**. Hãy đặt transaction rõ ràng và có xử lý rollback khi lỗi trước commit.

Ví dụ minh họa một nghiệp vụ đơn giản với `DataSource`:

```java
public void transfer(DataSource dataSource,
                     long fromId,
                     long toId,
                     BigDecimal amount) throws SQLException {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    """
                    UPDATE accounts
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """)) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromId);
                debit.setBigDecimal(3, amount);

                if (debit.executeUpdate() != 1) {
                    throw new SQLException("Source account missing or insufficient funds");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    """
                    UPDATE accounts
                    SET balance = balance + ?
                    WHERE id = ?
                    """)) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toId);

                if (credit.executeUpdate() != 1) {
                    throw new SQLException("Destination account missing");
                }
            }

            connection.commit();
        } catch (SQLException original) {
            try {
                connection.rollback();
            } catch (SQLException rollbackFailure) {
                original.addSuppressed(rollbackFailure);
            }
            throw original;
        }
    }
}
```

Điều quan trọng trong ví dụ:

- `setAutoCommit(false)` đặt hai lệnh cập nhật trong cùng transaction trên cùng connection.
- `UPDATE ... WHERE balance >= ?` bảo vệ điều kiện số dư ngay ở database; kiểm tra số hàng bị cập nhật để nhận biết giao dịch không đủ điều kiện.
- `rollback()` là bước cleanup hợp lý khi có lỗi; nếu chính `commit()` mất phản hồi, **rollback trong catch không chứng minh giao dịch đã được hủy**. Với nghiệp vụ thực, cần bổ sung `request_id` và quy trình đối soát ở mục 7.
- `try-with-resources` đóng tài nguyên kể cả khi exception xảy ra. Tuy nhiên, với connection pool, `close()` trên handle thường là **trả kết nối về pool**, không đồng nghĩa ngắt TCP ngay. Dùng pool/transaction manager đáng tin cậy để làm sạch trạng thái trước khi tái sử dụng connection.

Ví dụ trên tập trung vào ranh giới transaction; ứng dụng thật còn cần kiểm soát tham số đầu vào, xác thực, giới hạn retry, bất biến tổng thể và kết quả khi commit không chắc chắn.

### Đọc mã SQLSTATE đúng cách

JDBC cho phép lấy SQLSTATE từ exception:

```java
catch (SQLException ex) {
    String sqlState = ex.getSQLState();
    // Phân loại theo database/driver cụ thể,
    // rồi quyết định rollback, retry, đối soát hoặc trả lỗi.
    throw ex;
}
```

Một số mã đáng nhớ trong PostgreSQL:

| SQLSTATE | Ý nghĩa | Hướng xử lý |
|---|---|---|
| `23505` | Vi phạm unique constraint | Kiểm tra trùng nghiệp vụ; rollback hoặc trở về savepoint trong transaction PostgreSQL |
| `23514` | Vi phạm check constraint | Sửa dữ liệu/logic; không retry mù quáng |
| `25P02` | Transaction đang ở trạng thái failed | Tìm lỗi gốc; rollback hoặc rollback về savepoint hợp lệ |
| `40P01` | Deadlock detected | Rollback và cân nhắc retry toàn transaction |
| `40001` | Serialization failure | Retry toàn transaction với dữ liệu mới |
| `57014` | Query canceled, có thể do statement timeout | Xác định nguyên nhân hủy; phục hồi transaction theo semantics của PostgreSQL |
| Lớp `08` (ví dụ `08006`) | Lỗi kết nối | Xác minh kết nối; nếu mất phản hồi lúc commit, coi kết quả chưa rõ cho đến khi đối soát |

**SQLSTATE là manh mối để phân loại, không phải giấy xác nhận commit/rollback.** Driver có thể bọc exception trong nhiều lớp, mã lỗi là đặc thù từng engine, và lỗi mạng đôi khi khiến không còn đủ thông tin SQLSTATE. Log nên ghi lỗi gốc, request ID, giai đoạn transaction và thông tin có thể quan sát, đồng thời tránh log dữ liệu nhạy cảm.

### Đừng sử dụng lại connection đã hỏng

Nếu driver hoặc pool đánh dấu connection là không còn hợp lệ, cần để pool loại bỏ hoặc tái tạo nó. Với connection PostgreSQL còn sống nhưng transaction đang failed, cần rollback trước khi dùng lại. Không được coi hai trường hợp là giống nhau:

```text
Connection còn sống + transaction failed
    → ROLLBACK / ROLLBACK TO SAVEPOINT nếu có thể
    → tiếp tục trên connection hợp lệ

Connection hỏng / session không còn
    → bỏ connection đó
    → tạo transaction mới trên connection khác
    → đối soát nếu kết quả commit trước đó chưa xác định
```

## 9. Spring `@Transactional`: exception có thể khiến rollback hay commit?

Trong ứng dụng Spring, transaction manager quản lý ranh giới transaction thay JDBC thủ công:

```java
@Service
public class TransferService {

    @Transactional
    public void transferOnce(/* request id, account ids, amount */) {
        // Đọc/ghi database trong transaction do Spring quản lý.
        // Nếu thao tác bắt buộc thất bại, để exception đi ra ngoài
        // hoặc đánh dấu rollback-only một cách rõ ràng.
    }
}
```

Theo cấu hình mặc định thường gặp của Spring, một exception kiểu `RuntimeException` hoặc `Error` đi qua ranh giới phương thức `@Transactional` làm transaction bị rollback; **checked exception** không mặc định gây rollback, trừ khi cấu hình `rollbackFor` hoặc quy tắc tương đương. Chính sách này có thể tùy chỉnh.

Ví dụ cần rollback cả với checked exception:

```java
@Transactional(rollbackFor = Exception.class)
public void applyOperation() throws Exception {
    // Các bước nghiệp vụ phải cùng thành công hoặc cùng thất bại.
}
```

Một lỗi dễ gặp là bắt exception bên trong phương thức transactional rồi **nuốt lỗi**:

```java
@Transactional
public void incorrectFlow() {
    try {
        repository.save(/* ... */);
    } catch (RuntimeException ex) {
        log.warn("SQL failed", ex);
        // Trả về bình thường mà không quyết định transaction có còn hợp lệ không.
    }
}
```

Nếu database là PostgreSQL và statement làm transaction bị failed, các lệnh tiếp theo sẽ gặp `25P02`; tại thời điểm kết thúc, transaction không thể commit các thay đổi đã bị abort. Trường hợp khác, nếu database vẫn cho transaction hoạt động, việc nuốt lỗi có thể khiến các thay đổi trước đó được commit **dù nghiệp vụ muốn hủy tất cả**.

Nếu muốn hủy giao dịch, hãy truyền exception phù hợp ra ranh giới transaction hoặc đánh dấu **rollback-only** có chủ đích. Nếu muốn bỏ qua lỗi của một bước tùy chọn, phải dùng savepoint hoặc thiết kế transaction con đúng với khả năng của transaction manager, thay vì giả định catch exception là đủ.

Ngoài ra, nếu retry transaction, mỗi lần thử phải đi qua một **ranh giới transaction mới**. Với cơ chế proxy `@Transactional` thông thường, gọi nội bộ trực tiếp từ một phương thức của cùng object có thể không kích hoạt interception như mong đợi. Cách tổ chức dễ kiểm soát là đặt vòng retry ở tầng ngoài và gọi dịch vụ có method transactional cho **mỗi lần thử**.

### Trạng thái commit chưa rõ ở Spring

Ngay cả khi framework ném exception khi commit, câu hỏi “server đã commit trước khi mất kết nối hay chưa?” vẫn tồn tại. Framework không thể suy luận chắc chắn điều mà giao thức mạng đã làm mất. Các operation có nguy cơ trùng vẫn cần thiết kế idempotent và cách đối soát bằng khóa nghiệp vụ ổn định.

## 10. Chiến lược khôi phục theo giai đoạn phát sinh lỗi

Thay vì chỉ phân loại theo tên exception, hãy ghi nhận **lỗi xuất hiện tại giai đoạn nào**.

| Giai đoạn | Ví dụ | Hành động hợp lý |
|---|---|---|
| Chưa bắt đầu transaction | Không lấy được connection từ pool | Báo lỗi hoặc retry kết nối theo chính sách; chưa có transaction nghiệp vụ của lần thử đó |
| Đang chạy SQL, connection còn sống | Vi phạm ràng buộc, SQL sai | Dựa vào DB semantics: rollback cả transaction hoặc `ROLLBACK TO SAVEPOINT` nếu phù hợp |
| Đang tranh chấp/đợi khóa | Deadlock, serialization failure | Rollback và cân nhắc retry toàn transaction với dữ liệu đọc lại |
| Mất kết nối trước khi xác nhận commit | Socket timeout, server đóng connection | Loại bỏ connection hỏng; xác định liệu commit đã được gửi hoặc có thể hoàn tất; dùng request ID để đối soát |
| Sau khi đã gửi `COMMIT`, chưa nhận xác nhận | Network failure/timeout | Coi là **outcome unknown**; đối soát trước khi tạo một tác động nghiệp vụ mới |
| `COMMIT` đã xác nhận thành công | Mất mạng ở request kế tiếp | Xem giao dịch đã commit; không rollback transaction cũ qua connection mới |
| Rollback cũng thất bại | Connection chết giữa lúc cleanup | Ghi nhận lỗi cleanup, loại bỏ connection và đối soát nếu commit từng được thử |

### Quy trình ứng dụng có thể triển khai

```text
Bắt đầu yêu cầu với request_id ổn định
                 |
                 v
          Mở transaction mới
                 |
                 v
     Đọc + kiểm tra + cập nhật dữ liệu
                 |
       +---------+----------+
       |                    |
  Statement lỗi         Đủ điều kiện commit
       |                    |
       v                    v
  Phân loại lỗi          Gửi COMMIT
       |                    |
       |             +------+------+
       |             |             |
       v          ACK thành công   Không có ACK
  Rollback (nếu         |             |
  còn làm được)         v             v
       |           Thành công    Outcome unknown
       |                            |
       v                            v
  Retry toàn tx            Đối soát theo request_id
  hoặc trả lỗi             hoặc retry idempotent
```

Có ba nhóm kết quả khác nhau cần thể hiện rõ với người gọi/API:

1. **Thành công đã được xác nhận:** có bằng chứng commit và có thể trả kết quả.
2. **Thất bại đã xác định:** transaction bị rollback/không được thực hiện; có thể báo lỗi hoặc cho phép tạo thao tác mới.
3. **Kết quả đang cần đối soát:** không thể khẳng định thành công hay thất bại. Giữ cùng request ID để tra cứu hoặc retry an toàn; đừng tự động tạo một lệnh nghiệp vụ độc lập mới.

Đối với API tài chính hoặc thao tác không thể tùy tiện thực hiện hai lần, cách biểu diễn “đang xử lý/chưa rõ kết quả” là một yêu cầu nghiệp vụ quan trọng, không đơn thuần là lỗi hạ tầng.

## 11. Vấn đề vận hành: lock còn giữ, pool tái sử dụng và timeout

Lỗi transaction có thể kéo theo hệ quả với các request khác, kể cả khi request gặp lỗi đã dừng.

### Transaction mở quá lâu

Nếu một ứng dụng giữ connection trong transaction rồi chờ IO ngoài, người dùng thao tác hoặc một truy vấn bị treo, nó có thể giữ khóa và phiên bản dữ liệu cũ lâu hơn cần thiết. Những transaction khác có thể phải chờ hoặc bị deadlock. Mất mạng một chiều còn khiến server chưa biết client đã bỏ cuộc.

Trong PostgreSQL, có thể giám sát các session đang ở trạng thái như `idle in transaction`, thời gian tồn tại transaction và các phiên đang chờ khóa. Các thiết lập như `idle_in_transaction_session_timeout` giúp giới hạn session bỏ không trong transaction; nhưng cần cấu hình phù hợp với ứng dụng vì timeout có thể đóng session và buộc các request liên quan phải phục hồi.

### Trả connection về pool

Một connection pool thường giữ các **kết nối vật lý** và phát cho ứng dụng các handle tạm thời. Gọi `close()` trên handle thường có nghĩa trả về pool. Pool/transaction manager cần bảo đảm transaction chưa kết thúc được cleanup, trạng thái auto-commit, isolation, read-only, session settings... được trả về trạng thái phù hợp trước khi connection được cấp cho request khác.

Nếu tự quản lý connection mà quên rollback một transaction lỗi, request tiếp theo có thể gặp lỗi `25P02` hoặc trạng thái phiên bất ngờ. Đó là một lý do phải dùng ranh giới transaction nhất quán và không nuốt exception thiếu kiểm soát.

### Log để điều tra

Một bản ghi lỗi hữu ích thường cho biết:

- **Request/operation ID** để đối soát và chống ghi trùng.
- **Giai đoạn**: đã BEGIN, đang đọc/ghi, đang gửi COMMIT, đã nhận commit ACK hay đang rollback.
- **Database và SQLSTATE/vendor code**, exception gốc và các lỗi cleanup bị thêm dưới dạng suppressed exception.
- **Khả năng kết nối còn sử dụng được** và transaction có bị đánh dấu rollback-only không.
- **Số lần retry**, thời điểm bắt đầu/kết thúc, và thông tin wait/timeout liên quan.

Không log mật khẩu, thông tin kết nối có secret, dữ liệu tài chính nhạy cảm hoặc toàn bộ tham số SQL không cần thiết. Mục đích log là truy vết trạng thái và lựa chọn hồi phục đúng, không phải nhân bản dữ liệu riêng tư.

## 12. Các ngộ nhận thường gặp

**“Có SQLException là database đã rollback hết.”** Sai: lỗi có thể chỉ ảnh hưởng một statement; các statement autocommit trước đó đã commit; một commit mất phản hồi thậm chí có thể đã thành công.

**“Lỗi `25P02` là nguyên nhân gốc.”** Thường sai: nó thông báo rằng transaction PostgreSQL đã lỗi từ trước. Cần tìm exception đầu tiên làm transaction failed.

**“Catch exception rồi chạy tiếp là được.”** Chỉ đúng khi đã biết trạng thái transaction và cơ chế phục hồi. Với PostgreSQL, transaction failed phải rollback hoặc phục hồi về savepoint.

**“`ROLLBACK` sau lỗi `commit()` chắc chắn hủy dữ liệu.”** Sai nếu commit đã hoàn tất trước khi phản hồi mất. Rollback không thể đảo ngược commit đã xong.

**“Mở kết nối mới là có thể tiếp tục transaction cũ.”** Sai với transaction SQL thông thường. Transaction cũ thuộc session đã mở; trên kết nối mới phải tạo transaction mới, với dữ liệu và quyết định được xác lập lại.

**“Tăng isolation là hết các lỗi.”** Sai: mức cô lập mạnh có thể chủ động từ chối một giao dịch cạnh tranh và yêu cầu retry. Isolation giúp bảo đảm tính đúng đắn của những giao dịch commit thành công, không hứa mọi giao dịch đều commit ngay lần đầu.

**“Không tìm thấy bản ghi yêu cầu sau timeout nghĩa là lần trước chắc chắn thất bại.”** Chưa chắc: transaction trước có thể vẫn đang xử lý, chưa commit hoặc bản đọc đến từ replica chậm. Đối soát phải đi cùng cơ chế unique/idempotency và hiểu rõ nguồn đọc.

## 13. Bài tập suy luận

### Bài 1: Một lỗi, hai cách xử lý

Trong PostgreSQL, transaction thực hiện:

```sql
BEGIN;
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
INSERT INTO accounts (id, balance) VALUES (2, 200);
SELECT balance FROM accounts WHERE id = 1;
COMMIT;
```

Giả sử `id = 2` đã tồn tại. Hãy mô tả trạng thái transaction sau `INSERT`, kết quả của `SELECT` và liệu lần `UPDATE` đầu có được commit hay không. Sau đó thay đổi kịch bản bằng một savepoint được tạo ngay trước `INSERT` và giải thích những câu lệnh cần thêm để tiếp tục an toàn.

### Bài 2: Lỗi cùng loại nhưng khác hệ quản trị

Trong MySQL InnoDB, một duplicate key error có thể chỉ rollback statement. Nếu nghiệp vụ gồm năm câu SQL đều bắt buộc thành công, ứng dụng có nên tiếp tục chạy ba câu cuối rồi commit hay không? Phân biệt **database cho phép transaction tiếp tục** với **nghiệp vụ cho phép transaction tiếp tục**.

### Bài 3: Transfer timeout tại `COMMIT`

Một request chuyển tiền có `request_id = R123`. Hai tài khoản đã được cập nhật; client gọi `COMMIT` và nhận lỗi kết nối trước khi thấy phản hồi. Viết hai lịch có thể xảy ra: một lịch transaction đã commit và một lịch rollback. Vì sao việc gửi lại yêu cầu mới với `request_id = R124` có nguy cơ làm chuyển tiền hai lần?

### Bài 4: Serialization retry

Hai transaction `SERIALIZABLE` cùng đọc lịch trực và chọn cho các bác sĩ nghỉ. Một transaction bị PostgreSQL hủy với `SQLSTATE 40001`. Vì sao chỉ gọi lại câu `UPDATE` cuối là sai? Những phép đọc và kiểm tra điều kiện nào phải chạy lại trong transaction mới?

### Bài 5: Spring và rollback

Một phương thức `@Transactional` bắt `RuntimeException` do repository ném, ghi log và trả về bình thường. Hãy phân tích hai tình huống: PostgreSQL transaction đã failed, và hệ quản trị khác vẫn để transaction hoạt động sau lỗi statement. Cần sửa luồng xử lý thế nào để bảo đảm một thao tác nghiệp vụ bắt buộc thất bại sẽ không commit nửa chừng?

## Kết luận

Xử lý transaction sau lỗi phải bắt đầu bằng câu hỏi **“trạng thái nào đã thực sự được xác nhận, ở phía nào?”**. Lỗi statement có thể làm hỏng toàn transaction hoặc chỉ câu lệnh, tùy database và loại lỗi. Với PostgreSQL, một transaction tường minh đã failed thường cần `ROLLBACK` hoặc `ROLLBACK TO SAVEPOINT` trước khi tiếp tục. Deadlock và serialization failure có thể cần retry **toàn bộ** transaction mới.

Lỗi kết nối, đặc biệt khi mất phản hồi của `COMMIT`, là bài toán khác: database có thể đã commit mà client chưa biết. Vì vậy thiết kế đúng cần ranh giới transaction rõ ràng, cleanup connection, phân loại lỗi theo database, retry có giới hạn, **định danh yêu cầu idempotent** và quy trình đối soát. Những biện pháp đó giúp hệ thống giữ đúng bất biến nghiệp vụ ngay cả khi giao dịch đồng thời, câu lệnh lỗi hoặc mạng bị gián đoạn.
