# Những điều ACID không tự bảo đảm cho quy tắc nghiệp vụ

ACID là tập hợp các thuộc tính nền tảng giúp hệ quản trị cơ sở dữ liệu (DBMS) thực thi giao dịch đáng tin cậy. Tuy nhiên, **một giao dịch đáp ứng ACID vẫn có thể tạo ra kết quả sai về nghiệp vụ**. Lý do là DBMS chỉ bảo vệ những thao tác, ràng buộc và mức cô lập mà hệ thống thực sự khai báo hoặc thực thi; nó không tự biết toàn bộ ý nghĩa của “đặt chỗ hợp lệ”, “không bán quá tồn kho” hay “không thu tiền hai lần”.

Hãy phân biệt ba loại câu hỏi:

1. **Cơ sở dữ liệu làm gì với giao dịch?** Ví dụ: toàn bộ các câu lệnh trong giao dịch được commit hoặc rollback; ghi nhận thay đổi theo cơ chế bền vững của DBMS.
2. **Giao dịch được phép quan sát và thay đổi dữ liệu đồng thời như thế nào?** Điều này phụ thuộc isolation level, khóa, MVCC và cơ chế phát hiện xung đột.
3. **Kết quả có đúng quy tắc nghiệp vụ và đúng xuyên suốt các hệ thống hay không?** Điều này còn phụ thuộc cách viết câu lệnh, ranh giới giao dịch, ràng buộc dữ liệu, logic ứng dụng, thiết kế tích hợp và xử lý lỗi.

Bài học tập trung vào những **giới hạn của ACID đối với quy tắc nghiệp vụ** và cách bổ sung bảo vệ phù hợp.

## 1. ACID thực sự cam kết điều gì?

| Thuộc tính | Cam kết chính | Điều không được tự suy ra |
|---|---|---|
| **Atomicity — tính nguyên tử** | Các thay đổi thuộc **cùng giao dịch** được xác nhận hoặc hủy như một đơn vị. | Mọi bước của một quy trình nghiệp vụ, kể cả gọi API, gửi email hoặc hai cơ sở dữ liệu độc lập, đều được rollback cùng nhau. |
| **Consistency — tính nhất quán** | Giao dịch chuyển dữ liệu giữa các trạng thái hợp lệ theo **những ràng buộc mà DBMS thực thi**; phần còn lại phụ thuộc logic giao dịch. | DBMS tự hiểu và tự kiểm tra mọi bất biến nghiệp vụ chưa được mô hình hóa. |
| **Isolation — tính cô lập** | DBMS kiểm soát tương tác giữa các giao dịch theo **mức cô lập được chọn**. | Mọi giao dịch luôn tương đương chạy tuần tự, hoặc mọi quyết định dựa trên việc đọc trước đều an toàn. |
| **Durability — tính bền vững** | Sau khi `COMMIT` thành công, thay đổi được DBMS bảo vệ theo cam kết độ bền và cấu hình của hệ thống. | Mọi dịch vụ bên ngoài đã xử lý thành công, không có mất mát do cấu hình vận hành sai, hay đã có bản sao lưu có thể khôi phục. |

Ví dụ, một bảng `orders` có ràng buộc `CHECK(total_amount >= 0)` sẽ được DBMS bảo vệ khỏi giá trị tổng âm trong những thao tác chịu ràng buộc đó. Nhưng nếu nghiệp vụ còn yêu cầu “giá đã áp dụng đúng chương trình khuyến mãi tại thời điểm khách xác nhận”, DBMS không thể xác minh điều này chỉ nhờ ACID, khi không có cấu trúc và logic tương ứng.

**Consistency trong ACID không đồng nghĩa với việc mọi yêu cầu nghiệp vụ đều tự được giữ đúng.** Một giao dịch có thể commit thành công và lưu trạng thái sai mà không hề vi phạm constraint nào đang tồn tại.

## 2. Atomicity chỉ bao phủ đúng ranh giới giao dịch

Giả sử quy trình đặt hàng cần:

1. Trừ số lượng hàng trong kho.
2. Tạo bản ghi đơn hàng.
3. Gửi yêu cầu thanh toán tới nhà cung cấp bên ngoài.
4. Gửi email xác nhận.

Nếu bước 1 và 2 nằm trong **cùng một database transaction**, DBMS có thể commit hoặc rollback hai bước đó cùng nhau. Tuy nhiên, nếu bước 3 gọi qua HTTP và bước 4 gửi email, rollback cơ sở dữ liệu **không tự hoàn tác** việc nhà cung cấp thanh toán đã trừ tiền hoặc email đã được gửi.

```text
Ứng dụng
  |
  +-- BEGIN transaction DB
  |      UPDATE inventory ...
  |      INSERT orders ...
  |      |
  |      +-- Gọi payment API ------> Hệ thống thanh toán độc lập
  |      |
  |      +-- COMMIT / ROLLBACK
  |
  +-- Gửi email ---------------> Hệ thống email độc lập
```

Ngay cả khi mã nguồn bao bọc cả hàm bằng annotation giao dịch, lời gọi tới dịch vụ bên ngoài không tự động tham gia cơ chế commit của cơ sở dữ liệu.

### 2.1. Một “nghiệp vụ” không nhất thiết là một giao dịch

Ranh giới transaction có thể kết thúc sớm hơn dự kiến bởi:

- Mỗi câu SQL đang chạy trong chế độ **autocommit**, không có giao dịch bao quanh chuỗi thao tác.
- Thao tác được thực hiện ở **nhiều kết nối hoặc nhiều transaction độc lập**.
- Framework mở giao dịch ở một phương thức nhưng một phần code chạy ngoài phạm vi đó; lời gọi bất đồng bộ hoặc cơ chế truyền transaction context cũng có thể làm thay đổi phạm vi.
- Các bước trải qua nhiều cơ sở dữ liệu hay hệ thống khác nhau mà chưa có giao thức phối hợp giao dịch thích hợp.

Ví dụ, hai câu lệnh này chỉ cùng atomic khi thực sự chạy trên cùng transaction:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;

COMMIT;
```

Nếu từng `UPDATE` được commit riêng, lỗi sau câu thứ nhất có thể để lại một giao dịch chuyển tiền thực hiện dở.

### 2.2. Tính nguyên tử không kiểm tra tính hợp lệ của phép chuyển

Ví dụ trên có thể commit thành công dù tài khoản 1 chỉ còn 50, nếu schema và câu lệnh không ngăn số dư âm. Để bảo vệ quy tắc “không được chi vượt số dư” ở mức cập nhật hàng:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE id = 1 AND balance >= 100;
-- Ứng dụng phải xác nhận số hàng được cập nhật là 1.
-- Nếu là 0: ROLLBACK và báo không đủ số dư.

UPDATE accounts
SET balance = balance + 100
WHERE id = 2;
-- Ứng dụng cũng phải xác nhận tài khoản nhận tồn tại.

COMMIT;
```

Ví dụ trên giả định hai tài khoản cùng đơn vị tiền tệ, số tiền hợp lệ và hai cập nhật cùng giao dịch. Nó **chưa tự kiểm tra** trạng thái phong tỏa, hạn mức giao dịch, quyền chủ tài khoản, phí, tỷ giá, số dư khả dụng hay những quy tắc khác. Các điều kiện cần được mô hình hóa và kiểm tra cụ thể.

## 3. Isolation không có nghĩa mọi lịch chạy đồng thời đều an toàn

Isolation là thuộc tính của giao dịch nhưng **mức độ bảo đảm không giống nhau**. Các mức quen thuộc gồm `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. DBMS có thể triển khai chúng bằng khóa, đa phiên bản (MVCC), kiểm tra xung đột hoặc kết hợp nhiều kỹ thuật; hành vi chi tiết thay đổi theo sản phẩm và cấu hình.

Bảng sau mô tả các hiện tượng trong mô hình chuẩn SQL thường được dùng để giới thiệu isolation:

| Mức cô lập | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Ngăn | Có thể | Có thể |
| `REPEATABLE READ` | Ngăn | Ngăn | Có thể theo mô hình chuẩn |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn |

Bảng này **không phải bảng kiểm đầy đủ mọi lỗi đồng thời**. Một số DBMS có hành vi mạnh hơn yêu cầu tối thiểu; các khái niệm `lost update`, `write skew` và `snapshot isolation` cần được đánh giá riêng theo DBMS cụ thể.

### 3.1. Lost update: hai giao dịch cùng đọc rồi ghi kết quả cũ

Ban đầu `inventory(quantity = 10)`. Hai yêu cầu bán hàng cùng thực hiện quy trình: đọc tồn kho, trừ một ở ứng dụng, sau đó ghi giá trị mới.

| Thời điểm | Transaction T1 | Transaction T2 |
|---|---|---|
| 1 | Đọc `quantity = 10` | |
| 2 | | Đọc `quantity = 10` |
| 3 | Ghi `quantity = 9` | |
| 4 | | Ghi `quantity = 9` |
| 5 | Commit | Commit |

Nếu cơ chế và mức cô lập cho phép lịch trên, hai sản phẩm đã bán nhưng tồn kho chỉ giảm một. Mỗi thao tác ghi có thể hoàn tất bình thường và dữ liệu vẫn không âm; **ACID của riêng từng transaction không đủ để chứng minh phép đếm tồn kho đúng**.

Một cách xử lý tốt khi cần trừ đúng một đơn vị là để DBMS đánh giá điều kiện và thay đổi **trong cùng một câu lệnh**:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity >= 1;
```

Ứng dụng chỉ xác nhận bán thành công khi số hàng được cập nhật đúng `1`. Nếu ảnh hưởng `0` hàng, xử lý “không tìm thấy sản phẩm” hoặc “không đủ tồn” theo dữ liệu thực tế. Nếu còn cần tạo order, lệnh trừ kho và lệnh tạo order phải cùng transaction.

Có thể dùng `SELECT ... FOR UPDATE` hoặc optimistic locking với cột `version` nếu logic bắt buộc phải đọc rồi quyết định, nhưng vẫn cần xử lý xung đột và trạng thái thất bại. DBMS cụ thể có thể tự phát hiện và hủy một số lịch lost update; **không nên dựa vào giả định chung rằng ACID luôn tự làm điều đó**.

### 3.2. Write skew: các hàng khác nhau vẫn có thể phá vỡ quy tắc chung

Quy tắc: **mỗi ca trực phải luôn còn ít nhất một bác sĩ trực**. Có hai bác sĩ A và B, đều có `on_call = true`.

Hai giao dịch cùng đọc trạng thái “có hai người trực”. T1 tắt trạng thái của A; T2 tắt trạng thái của B.

```text
Snapshot ban đầu:  A = true, B = true

T1: đọc A và B -> thấy 2 người trực
T2: đọc A và B -> thấy 2 người trực

T1: UPDATE doctor SET on_call = false WHERE id = 'A'
T2: UPDATE doctor SET on_call = false WHERE id = 'B'

Nếu cả hai commit:
    A = false, B = false
    -> Vi phạm "phải còn ít nhất một người trực"
```

Đây là **write skew**: T1 và T2 sửa **hai hàng khác nhau** nên không nhất thiết có xung đột ghi cùng hàng. Trên một số cơ chế snapshot isolation, cả hai có thể commit dù từng giao dịch đọc một snapshot nhất quán. Không thể khắc phục hiện tượng này chỉ bằng việc bảo đảm “mỗi giao dịch đều đọc dữ liệu đã commit”.

Hướng xử lý có thể là:

- Chạy toàn bộ thao tác kiểm tra và cập nhật trong `SERIALIZABLE`, đồng thời chuẩn bị xử lý serialization failure rồi thử lại giao dịch.
- Thiết kế một tài nguyên chung (chẳng hạn hàng điều phối theo ca trực) để các giao dịch tranh quyền cập nhật/khóa khi ra quyết định. Cần đảm bảo **mọi đường ghi** đều tuân thủ cơ chế này.
- Mô hình hóa quy tắc thành ràng buộc DB nếu có thể, chẳng hạn thay đổi cấu trúc dữ liệu hoặc dùng cơ chế constraint đặc thù phù hợp.

Khóa riêng hàng A cho T1 và hàng B cho T2 chưa đủ để bảo vệ bất biến trải rộng trên cả A và B.

### 3.3. SERIALIZABLE vẫn không sửa được logic nghiệp vụ sai

`SERIALIZABLE` bảo đảm hiệu ứng của các giao dịch **đã commit** tương đương với một thứ tự thực thi tuần tự hợp lệ. Đây là mức bảo vệ rất mạnh cho tương tác giữa các transaction, nhưng chỉ áp dụng với **những thao tác thật sự thực hiện trong transaction**.

Xét quy tắc “không cho tạo đơn hàng có tổng tiền âm”. Nếu ứng dụng cố ý hoặc vô tình ghi tổng âm, không có constraint `CHECK` và không có kiểm tra trong logic, một giao dịch `SERIALIZABLE` vẫn có thể commit giá trị âm. Lịch chỉ có **một giao dịch** đã là tuần tự, nhưng nghiệp vụ vẫn sai.

Tương tự, nếu một chương trình kiểm tra điều kiện trước khi bắt đầu transaction, rồi vào transaction chỉ ghi dữ liệu, `SERIALIZABLE` của phần ghi không thể tự đưa phép đọc **ở ngoài transaction** vào phạm vi bảo vệ.

Nguyên tắc cần nhớ:

> Serializable bảo vệ tính tương đương tuần tự của lịch giao dịch. Tính hợp lệ của một lịch tuần tự vẫn phụ thuộc nghiệp vụ được kiểm tra và thực thi đúng.

## 4. CHECK, UNIQUE và FOREIGN KEY bảo vệ những gì?

ACID không đồng nghĩa mọi bảng đều có constraint cần thiết. Một thiết kế mạnh thường đưa những bất biến **có thể diễn đạt trong cơ sở dữ liệu** về gần dữ liệu nhất.

Ví dụ một schema đơn giản:

```sql
CREATE TABLE accounts (
    id           BIGINT PRIMARY KEY,
    balance      DECIMAL(18, 2) NOT NULL,
    CONSTRAINT ck_balance_nonnegative CHECK (balance >= 0)
);

CREATE TABLE bookings (
    id           BIGINT PRIMARY KEY,
    room_id      BIGINT NOT NULL,
    booking_date DATE NOT NULL,
    status       VARCHAR(20) NOT NULL,
    CONSTRAINT uq_room_booking UNIQUE (room_id, booking_date)
);
```

Các ràng buộc này bảo vệ:

- `CHECK (balance >= 0)`: từ chối trạng thái có `balance` âm trong bảng, kể cả khi một đoạn code quên kiểm tra đủ số dư.
- `UNIQUE (room_id, booking_date)`: ngăn trùng tổ hợp phòng/ngày trên toàn bảng theo ngữ nghĩa `UNIQUE` của DBMS.
- `PRIMARY KEY` và `FOREIGN KEY` (khi được khai báo, bật và dùng đúng): bảo vệ định danh và quan hệ tham chiếu theo các quy tắc tương ứng.

Nhưng cần chú ý **mô hình nghiệp vụ**:

- Ví dụ `UNIQUE (room_id, booking_date)` phù hợp với giả định một phòng chỉ có **một** đặt chỗ trên cả ngày. Nó sẽ quá chặt nếu hệ thống cho thuê theo khung giờ. Ngược lại, nếu chỉ cấm các khoảng thời gian **chồng lấn**, UNIQUE theo ngày không biểu diễn được quy tắc đó; có thể cần constraint theo khoảng hoặc cơ chế khóa/phát hiện xung đột phù hợp.
- Nếu chỉ những đặt chỗ có trạng thái `CONFIRMED` mới chiếm phòng, constraint phải phản ánh chính xác điều kiện ấy. Một UNIQUE áp dụng cho cả bản ghi đã hủy có thể chặn đặt lại không mong muốn.
- `CHECK` thường phù hợp với điều kiện **trên một hàng**. Các quy tắc như “tổng số vé đã bán không vượt sức chứa”, “phải còn một bác sĩ trực” hoặc “tổng dư nợ trên mọi tài khoản thuộc khách hàng không vượt hạn mức” cần một chiến lược cho nhiều hàng hoặc mô hình dữ liệu khác.

### 4.1. Kiểm tra rồi INSERT không thay thế UNIQUE

Hai yêu cầu đăng ký đồng thời cùng kiểm tra tên người dùng:

```sql
SELECT COUNT(*)
FROM users
WHERE username = 'alice';
-- Cả T1 và T2 cùng thấy 0.
```

Sau đó cả hai chạy `INSERT`. Nếu không có `UNIQUE (username)` hay cơ chế đồng thời thích hợp, dữ liệu trùng có thể xuất hiện. Nếu có UNIQUE, DBMS sẽ quyết định xung đột ở thời điểm ghi/commit theo cơ chế của nó; ứng dụng phải bắt lỗi trùng và trả về thông điệp phù hợp.

Vì thế, **đọc trước để thông báo “còn trống” chỉ là một kiểm tra tiện dụng cho UX**. Ràng buộc hoặc giao thức ghi có tính cạnh tranh đúng đắn mới là phần bảo vệ cuối cùng.

## 5. MVCC và bản snapshot không bảo đảm dữ liệu luôn mới nhất

Cơ sở dữ liệu sử dụng **Multi-Version Concurrency Control (MVCC)** có thể giữ thông tin nhiều phiên bản logic của một hàng. Một giao dịch đọc snapshot để nhìn thấy một trạng thái nhất quán, thay vì luôn đọc giá trị mới nhất tại mỗi thời điểm.

Ví dụ T1 bắt đầu snapshot khi đơn hàng ở trạng thái `PENDING`. Sau đó T2 xác nhận đơn thành `CONFIRMED` và commit. T1 có thể vẫn đọc `PENDING` khi đang dùng snapshot giao dịch cũ. Đây có thể là **hành vi đúng** của isolation level đã chọn, nhưng nếu ứng dụng từ đó quyết định “đơn chưa được xác nhận nên có thể hủy ngay” mà không bảo vệ điều kiện cập nhật, nghiệp vụ dễ xảy ra tranh chấp.

Một phép cập nhật có điều kiện diễn đạt rõ điểm chuyển trạng thái hợp lệ:

```sql
UPDATE orders
SET status = 'CANCELLED'
WHERE id = 1001 AND status = 'PENDING';
-- Chỉ coi là hủy thành công khi số hàng ảnh hưởng = 1.
```

Với nhiều trạng thái và hành động, cần định nghĩa **state machine** và điều kiện chuyển trạng thái tương ứng. Chỉ đọc trạng thái rồi cập nhật không điều kiện có thể làm ghi đè một chuyển trạng thái vừa xảy ra.

Đặc biệt:

- **MVCC không có nghĩa là không có khóa**: các thao tác ghi cùng hàng vẫn có thể tranh chấp; locking read vẫn có thể dùng khóa.
- **Snapshot nhất quán không đồng nghĩa snapshot là trạng thái mới nhất**.
- **Optimistic locking** ở ứng dụng, ví dụ `WHERE id = ? AND version = ?` rồi tăng `version`, giúp phát hiện cập nhật dựa trên phiên bản cũ; nó không tự bảo vệ ràng buộc trải trên nhiều hàng.
- Khi dữ liệu được đọc từ **replica bất đồng bộ, cache hoặc search index**, kết quả có thể cũ ngay cả sau khi giao dịch ở cơ sở dữ liệu chính đã commit. ACID tại primary không tự cung cấp bảo đảm “đọc được ngay giá trị mới” trên mọi bản sao và mọi tầng cache.

## 6. Không chỉ chọn mức cô lập: còn phải xử lý transaction bị hủy

Giao dịch đồng thời không phải lúc nào cũng commit thành công. Khi có deadlock, timeout, serialization failure hoặc optimistic lock conflict, DBMS hoặc ứng dụng có thể hủy một giao dịch để bảo vệ tính đúng đắn.

Ví dụ T1 khóa bản ghi A và chờ B, trong khi T2 khóa B và chờ A. Đây là **deadlock**. DBMS thường chọn một giao dịch làm nạn nhân để cắt vòng chờ. Lúc đó, kết quả đúng là **một transaction thất bại**, không phải mọi yêu cầu đều thành công.

Ứng dụng cần phân biệt:

| Tình huống | Hướng xử lý |
|---|---|
| Deadlock / serialization failure có thể thử lại | Rollback, **chạy lại toàn bộ transaction**, đọc lại điều kiện và tính toán từ trạng thái mới. |
| Không đủ tồn kho, không đủ số dư, chuyển trạng thái không hợp lệ | Trả kết quả nghiệp vụ có ý nghĩa; không tự retry vô hạn. |
| Vi phạm UNIQUE do thao tác trùng | Xác định có phải yêu cầu đã xử lý trước đó hay dữ liệu thật sự xung đột; phản hồi theo contract API. |
| Hết thời gian chờ trong khi commit hoặc kết nối mất ở thời điểm nhạy cảm | Kết quả commit có thể **chưa rõ** từ phía client; xác minh bằng định danh nghiệp vụ/idempotency key thay vì gửi lại thao tác gây tác dụng kép một cách mù quáng. |

Pseudo-code minh họa mẫu retry:

```text
for attempt = 1..MAX_ATTEMPTS:
    begin transaction
    try:
        đọc lại dữ liệu cần thiết
        kiểm tra toàn bộ điều kiện nghiệp vụ
        ghi các thay đổi trong cùng transaction
        commit
        return SUCCESS
    catch retryable_concurrency_error:
        rollback nếu transaction vẫn còn hiệu lực
        nếu hết lượt thử: báo lỗi có thể retry
        chờ một khoảng ngắn có giới hạn, rồi thử từ đầu
    catch business_rule_violation:
        rollback
        return BUSINESS_FAILURE
```

Trong thực tế, sau một số loại lỗi, DBMS đã tự đánh dấu transaction thất bại hoặc rollback, nên cách cleanup phụ thuộc driver/framework. Chỉ nên retry khi toàn bộ thao tác có thể chạy lại an toàn và hệ thống có giới hạn lượt thử. Nếu luồng có lời gọi thanh toán, gửi thông báo hoặc ghi vào hệ thống ngoài, phải xử lý **idempotency** trước khi bật retry.

## 7. Durability không tự giải quyết tính nhất quán xuyên dịch vụ

Giả sử API bán vé chạy theo thứ tự:

1. Ghi `payment.status = PAID` vào database.
2. Commit thành công.
3. Gửi thông điệp “vé đã thanh toán” đến message broker.
4. Một dịch vụ khác phát hành vé.

Nếu tiến trình dừng giữa bước 2 và bước 3, database đã lưu `PAID` nhưng message chưa được gửi. Durability chỉ bảo vệ những gì đã được commit trong database; nó **không tự làm cho broker nhận thông điệp**.

Trường hợp ngược lại cũng có thể xảy ra khi ứng dụng gửi thông điệp trước rồi transaction database rollback: dịch vụ khác có thể đã hành động dựa trên một trạng thái chưa xác nhận.

### 7.1. Transactional outbox

Một kỹ thuật phổ biến là ghi **cả thay đổi nghiệp vụ lẫn bản ghi sự kiện cần phát** vào cùng database transaction:

```sql
BEGIN;

UPDATE payments
SET status = 'PAID'
WHERE payment_id = 9001
  AND status = 'PENDING';

-- Chỉ ghi sự kiện khi điều kiện chuyển trạng thái hợp lệ.
INSERT INTO outbox_events(event_id, aggregate_id, event_type, payload)
VALUES (:event_id, 9001, 'PaymentConfirmed', :payload);

COMMIT;
```

Ví dụ giả định ứng dụng đã kiểm tra một hàng payment được chuyển trạng thái thành công trước khi thêm sự kiện; nếu điều kiện không thỏa, giao dịch phải kết thúc theo nhánh nghiệp vụ tương ứng, không phát `PaymentConfirmed`.

Một tiến trình riêng đọc `outbox_events` và gửi tới broker. Nếu tiến trình dừng trước khi gửi, dữ liệu outbox còn để thử lại. **Tuy nhiên, bản thân outbox không mặc nhiên bảo đảm mỗi thông điệp chỉ được xử lý đúng một lần**: nếu broker nhận sự kiện nhưng tiến trình gửi lỗi trước khi đánh dấu đã gửi, thông điệp có thể được phát lại. Consumer nên xử lý trùng bằng mã `event_id` hoặc một khóa nghiệp vụ ổn định.

```text
        Cùng một database transaction
       +----------------------------------+
       | UPDATE nghiệp vụ                 |
       | INSERT outbox event              |
       +----------------------------------+
                      |
                    COMMIT
                      |
               Outbox publisher
                      |
                 Message broker
                      |
             Consumer có deduplication
                      |
              Hệ thống downstream
```

### 7.2. Saga, bù trừ và giới hạn của rollback

Một quy trình trải qua nhiều dịch vụ, ví dụ đặt vé, thu tiền và phát hành vé, có thể dùng **Saga**: mỗi dịch vụ xác nhận giao dịch local của riêng mình; nếu bước tiếp theo thất bại, hệ thống thực hiện hành động **bù trừ** (ví dụ hoàn tiền, giải phóng chỗ).

Hành động bù trừ không phải rollback DB xuyên mọi hệ thống. Hoàn tiền có thể mất thời gian, bị từ chối hoặc cần đối soát; email đã gửi không thể “thu hồi” chắc chắn. Vì vậy thiết kế còn cần trạng thái trung gian rõ ràng (`PENDING_PAYMENT`, `PAYMENT_CONFIRMED`, `REFUND_PENDING`...), khả năng chạy lại và quy trình xử lý lỗi kéo dài.

### 7.3. Durability không đồng nghĩa không cần backup

Bảo đảm durability còn phụ thuộc cách DBMS được cấu hình và vận hành, hệ thống lưu trữ, replication/synchronous commit, chế độ ghi log và tình huống sự cố. Nó không có nghĩa rằng:

- Xóa nhầm dữ liệu đã commit có thể tự hoàn tác.
- Mọi replica đã bắt kịp ngay lập tức.
- Mọi thảm họa phá hủy dữ liệu ở nhiều vị trí đều không ảnh hưởng.
- Không cần backup, phục hồi theo thời điểm, kiểm thử khôi phục hoặc chiến lược dự phòng.

ACID là nền tảng **giao dịch**, không thay thế chính sách phục hồi dữ liệu và vận hành hệ thống.

## 8. Idempotency: ACID không ngăn cùng một yêu cầu nghiệp vụ được gửi hai lần

Client gửi yêu cầu mua hàng, server xử lý và commit, nhưng phản hồi HTTP bị mất trên đường về. Client timeout rồi gửi lại. Hai yêu cầu có thể tạo **hai transaction hoàn toàn hợp lệ**, mỗi transaction đều ACID, nhưng khách hàng bị đặt hai đơn hoặc bị trừ tiền hai lần.

Một cách bảo vệ là gắn **idempotency key** ổn định cho *một ý định nghiệp vụ*, có unique constraint lưu khóa đó trong database:

```sql
CREATE TABLE checkout_requests (
    request_key VARCHAR(100) PRIMARY KEY,
    order_id    BIGINT,
    status      VARCHAR(30) NOT NULL
);
```

Khi xử lý một key mới, ứng dụng tạo/bảo vệ bản ghi yêu cầu và thực hiện nghiệp vụ cần thiết trong ranh giới phù hợp. Khi nhận lại **cùng key**, nó tìm kết quả đã ghi hoặc trạng thái đang xử lý rồi trả về cùng kết quả hợp lệ, thay vì tạo thêm đơn. Có thể cần thêm fingerprint của tham số để từ chối việc dùng lại cùng key cho **nội dung yêu cầu khác**.

Ví dụ chuỗi xử lý:

```text
POST /checkout
Idempotency-Key: order-req-abc-001

Lần 1:
  nhận key -> xử lý đơn -> commit -> response bị mất

Lần 2:
  nhận cùng key -> phát hiện đã xử lý
               -> trả lại kết quả đơn cũ
               -> không trừ kho/thanh toán lần nữa
```

Nếu quá trình có cổng thanh toán bên ngoài, cần tận dụng **idempotency key của cổng thanh toán** (nếu hỗ trợ) và cơ chế đối soát trạng thái. Chỉ đặt unique key ở database nội bộ không thể tự ngăn phía cổng thanh toán thực hiện lại tác dụng của một lời gọi API trước đó.

## 9. Ví dụ tổng hợp: bán sản phẩm cuối cùng

Xét yêu cầu: **mỗi sản phẩm có tồn kho không âm, một yêu cầu checkout chỉ tạo tối đa một đơn, và sau khi đơn tạo thành công hệ thống sẽ gửi thông báo**.

Một thiết kế sơ bộ có thể sử dụng các biện pháp ở những phạm vi khác nhau:

| Quy tắc / nguy cơ | Biện pháp | Vì sao ACID riêng lẻ chưa đủ |
|---|---|---|
| Không bán khi hết hàng | `UPDATE inventory SET available = available - :qty WHERE available >= :qty`; kiểm tra số hàng ảnh hưởng | Transaction vẫn có thể thực hiện một phép ghi không hợp lệ nếu không kiểm tra điều kiện. |
| Không để số lượng âm | `CHECK (available >= 0)` | DBMS chỉ kiểm tra ràng buộc thật sự tồn tại. |
| Trừ kho và tạo đơn cùng thành công hoặc cùng thất bại | Một database transaction bao quanh hai thay đổi | Hai lệnh chạy autocommit riêng sẽ không atomic như một đơn vị. |
| Client gửi lại checkout sau timeout | Idempotency key với unique constraint và tra cứu kết quả cũ | Hai transaction hợp lệ không tự được nhận diện là cùng một ý định. |
| Gửi thông báo sau khi đơn đã commit | Outbox ghi cùng transaction với đơn, publisher riêng | Commit database không commit message broker hay email. |
| Có deadlock hoặc serialization failure | Retry toàn bộ giao dịch theo quy tắc có giới hạn | Một số transaction cần bị hủy để bảo vệ cô lập; không phải mọi yêu cầu đều commit. |
| Trạng thái hiển thị ở cache/replica kịp thời | Chính sách đọc từ primary hoặc đồng bộ/invalidate cache phù hợp | Durability trên primary không đồng nghĩa replica và cache đã cập nhật ngay. |

Ví dụ giả lập luồng lưu đơn:

```text
BEGIN TRANSACTION

1. Đăng ký request_key mới theo unique constraint.
   Nếu key đã tồn tại, rẽ sang nhánh tra cứu kết quả cũ.

2. UPDATE inventory
      SET available = available - requested_quantity
      WHERE product_id = ... AND available >= requested_quantity
   Yêu cầu đúng 1 hàng được cập nhật; ngược lại ROLLBACK.

3. INSERT orders(..., request_key, status = 'CREATED')

4. INSERT outbox_events(..., event_type = 'OrderCreated')

COMMIT

Ngoài transaction:
5. Publisher gửi OrderCreated; consumer xử lý trùng an toàn.
```

Trong một triển khai thực tế, nhánh trùng khóa, lỗi commit chưa xác định, trạng thái request đang xử lý và thao tác thanh toán ngoài DB đều phải có contract xử lý rõ ràng. **Các biện pháp này bổ sung cho ACID để bảo vệ điều kiện nghiệp vụ cụ thể; chúng không phải một “mức ACID cao hơn”.**

## 10. Cách lập luận khi thiết kế giao dịch cho nghiệp vụ

Trước khi khẳng định “đã bọc transaction nên an toàn”, hãy lần lượt phân tích:

1. **Viết bất biến thành mệnh đề kiểm tra được.** Ví dụ “`inventory.available >= 0`” khác với “số đơn đã xác nhận không vượt số ghế thực có”; hai quy tắc có phạm vi dữ liệu khác nhau.
2. **Xác định ai có thể thay đổi dữ liệu.** Hai request HTTP, background job, batch import, webhook hay một dịch vụ khác đều có thể tạo đồng thời.
3. **Xác định ranh giới transaction thực tế.** Các phép đọc, kiểm tra, cập nhật có nằm trên cùng kết nối và trong cùng giao dịch không? Có thao tác nào ở ngoài DB không?
4. **Chọn cơ chế đặt bất biến gần dữ liệu.** Dùng `NOT NULL`, `CHECK`, `UNIQUE`, `FOREIGN KEY` khi biểu diễn được; dùng cập nhật nguyên tử, locking hoặc phiên bản để bảo vệ thay đổi có điều kiện; dùng `SERIALIZABLE` khi cần bảo đảm tương đương tuần tự.
5. **Đặt mức cô lập trên hành vi DBMS thực tế.** Tên mức cô lập không đủ để suy ra mọi tương tác giữa snapshot, khóa đọc, khóa ghi và range lock.
6. **Định nghĩa kết quả của xung đột.** Không đủ hàng, trùng yêu cầu, serialization failure và commit chưa xác định phải có nhánh xử lý khác nhau. Retry phải có giới hạn và an toàn với tác dụng phụ.
7. **Phân biệt nhất quán nội bộ DB với nhất quán xuyên hệ thống.** Thanh toán, message, email, cache và replica cần thêm giao thức thích hợp; có thể phải chấp nhận nhất quán cuối cùng với trạng thái trung gian và cơ chế đối soát.
8. **Đánh giá một lịch đồng thời cụ thể.** Thử hình dung T1 và T2 cùng đọc điều kiện hợp lệ, sau đó mỗi bên ghi một phần dữ liệu. Nếu cả hai commit, bất biến có còn đúng không?

Một câu hỏi rất hữu ích là: **nếu chạy giao dịch này một mình, kết quả đã đúng chưa?** Nếu chưa, `SERIALIZABLE` cũng không giải quyết được. Nếu đã đúng khi chạy một mình, tiếp tục hỏi: **khi hai giao dịch chạy đồng thời, có thể tồn tại lịch commit khiến quy tắc bị vi phạm không?** Câu trả lời dẫn đến việc chọn isolation, khóa, cập nhật có điều kiện và constraint phù hợp.

## 11. Kết luận

**ACID bảo đảm những thuộc tính quan trọng của giao dịch, nhưng không tự định nghĩa sự đúng đắn của nghiệp vụ.** Atomicity chỉ áp dụng cho những thay đổi thuộc một transaction; consistency cần những ràng buộc và logic được khai báo đúng; isolation có nhiều mức bảo đảm và có thể khiến giao dịch phải hủy; durability không bao trùm các dịch vụ ngoài DB hay mọi tình huống vận hành.

Để xây dựng quy trình đáng tin cậy, cần phối hợp **transaction boundary rõ ràng**, **constraint phù hợp**, **cập nhật nguyên tử hoặc kiểm soát xung đột**, **mức cô lập tương ứng với bất biến**, cùng **idempotency và cơ chế giao tiếp xuyên dịch vụ**. Chỉ khi từng quy tắc nghiệp vụ được diễn đạt và bảo vệ bằng cơ chế cụ thể, hệ thống mới có cơ sở để khẳng định kết quả đúng trong điều kiện truy cập đồng thời và xảy ra lỗi.
