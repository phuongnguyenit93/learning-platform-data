# Tính nhất quán (Consistency): bất biến dữ liệu và trách nhiệm của ứng dụng

Trong ACID, **Consistency (tính nhất quán)** nói về việc một transaction đưa cơ sở dữ liệu từ **một trạng thái hợp lệ sang một trạng thái hợp lệ khác**. “Hợp lệ” không có nghĩa đơn giản là câu SQL chạy thành công; nó có nghĩa dữ liệu vẫn thỏa những quy tắc mà hệ thống phải duy trì, gọi là **bất biến dữ liệu (data invariants)**.

Ví dụ, một hệ thống chuyển tiền có thể có các quy tắc sau:

- Số dư của mỗi tài khoản không được âm.
- Mỗi yêu cầu chuyển tiền chỉ được thực hiện một lần.
- Tiền ghi giảm ở tài khoản nguồn và tiền ghi tăng ở tài khoản đích phải thuộc cùng một lần chuyển, với cùng số tiền.
- Không thể chuyển tiền đến một tài khoản không tồn tại.

Một transaction chỉ nên được **commit** khi mọi quy tắc liên quan vẫn đúng. Cơ sở dữ liệu giúp cưỡng chế những quy tắc đã được khai báo và cung cấp cơ chế transaction, nhưng **ứng dụng phải xác định quy tắc nghiệp vụ, thực hiện thao tác đúng và xử lý cạnh tranh đồng thời**.

## 1. Hiểu chính xác chữ C trong ACID

Giả sử S là một trạng thái của cơ sở dữ liệu, I là tập hợp các bất biến, và T là một transaction. Mục tiêu là:

> Nếu I(S) đúng trước khi thực hiện T, thì I(T(S)) cũng phải đúng khi T được commit thành công.

Có ba điều kiện ẩn trong phát biểu này:

1. **Phải biết trạng thái nào là hợp lệ.** Cơ sở dữ liệu không tự biết “một ca trực phải còn ít nhất một bác sĩ” nếu ứng dụng không biểu diễn hoặc thực thi quy tắc đó.
2. **Transaction phải được lập trình đúng.** Một transaction có thể cập nhật sai cả hai tài khoản rồi vẫn commit nguyên vẹn nếu không có ràng buộc nào phát hiện lỗi nghiệp vụ.
3. **Các transaction đồng thời phải được phối hợp phù hợp.** Hai transaction riêng lẻ có vẻ đúng vẫn có thể kết hợp thành trạng thái sai nếu chỉ kiểm tra theo ảnh chụp dữ liệu cũ.

Các trạng thái *trung gian* trong một transaction đôi khi chưa thỏa toàn bộ quy tắc nghiệp vụ. Điều quan trọng là trạng thái được commit phải hợp lệ; tuy vậy, một số ràng buộc của hệ quản trị cơ sở dữ liệu được kiểm tra ngay khi thực hiện từng câu lệnh, nên không phải mọi trạng thái trung gian đều được cho phép. Chẳng hạn, PostgreSQL thường kiểm tra CHECK ngay khi câu lệnh được thực thi; chỉ một số loại ràng buộc hỗ trợ kiểm tra trì hoãn.

### Consistency khác gì ba thuộc tính ACID còn lại?

| Thuộc tính | Câu hỏi chính | Vai trò đối với bất biến |
|---|---|---|
| **Atomicity** | Các thay đổi trong transaction có cùng thành công hoặc cùng bị hoàn tác không? | Ngăn việc chỉ ghi một phần thao tác, nhưng không tự xác định thao tác đó có đúng nghiệp vụ hay không. |
| **Consistency** | Trạng thái đã commit có tuân thủ các quy tắc dữ liệu không? | Mục tiêu về tính hợp lệ của trạng thái. |
| **Isolation** | Các transaction chạy đồng thời có ảnh hưởng đến nhau ra sao? | Cung cấp cơ chế ngăn những lịch chạy đồng thời làm hỏng bất biến, tùy mức cô lập và cách truy cập dữ liệu. |
| **Durability** | Dữ liệu đã commit có tồn tại sau sự cố theo bảo đảm của hệ quản trị không? | Bảo toàn kết quả đã commit; không biến kết quả sai nghiệp vụ thành kết quả đúng. |

Vì vậy, **atomicity và isolation là công cụ quan trọng để đạt consistency**, chứ không đồng nghĩa với consistency.

Cũng cần phân biệt chữ C của ACID với những khái niệm khác như *strong consistency*, *eventual consistency* hay *read-after-write consistency* trong hệ phân tán. Các khái niệm đó chủ yếu nói về khả năng quan sát phiên bản dữ liệu giữa các bản sao hoặc các dịch vụ; Consistency trong ACID tập trung vào **bất biến của trạng thái giao dịch**.

## 2. Bất biến dữ liệu xuất hiện ở những cấp nào?

Bất biến có thể đơn giản như “giá không âm”, nhưng cũng có thể bao trùm nhiều hàng dữ liệu, nhiều bảng hoặc cả luồng nghiệp vụ.

| Phạm vi | Ví dụ bất biến | Cơ chế thường dùng |
|---|---|---|
| Một cột | Số lượng phải dương; mã khách hàng không rỗng | NOT NULL, CHECK, kiểm tra đầu vào |
| Một hàng | Ngày kết thúc không trước ngày bắt đầu | CHECK, logic miền nghiệp vụ |
| Nhiều hàng trong một bảng | Không có hai lượt đặt cùng một ghế của cùng sự kiện | UNIQUE hoặc unique index thích hợp |
| Quan hệ giữa các bảng | Mọi đơn hàng phải thuộc về một khách hàng tồn tại | FOREIGN KEY |
| Nhiều hàng hoặc nhiều bảng | Tổng số ghế đã giữ không vượt sức chứa; một ca luôn có người trực | Khóa, thiết kế dữ liệu thích hợp, transaction với mức cô lập phù hợp |
| Trạng thái nghiệp vụ | Đơn đã hủy không được chuyển thẳng sang đã giao | Máy trạng thái và cập nhật có điều kiện |
| Nhiều hệ thống | Thanh toán thành công phải dẫn tới giao hàng đúng một lần về mặt nghiệp vụ | Giao thức phối hợp, outbox, xử lý idempotent và cơ chế bù trừ khi cần |

**Bất biến phải được viết rõ thành mệnh đề có thể kiểm tra**, thay vì chỉ ghi “dữ liệu cần chính xác”. Ví dụ:

- Mơ hồ: “Không được bán quá nhiều vé”.
- Cụ thể: “Đối với mỗi sự kiện, số vé giữ chỗ còn hiệu lực không vượt quá sức chứa được phép”.
- Cụ thể hơn nếu có ghế định danh: “Mỗi cặp (event_id, seat_no) chỉ có tối đa một đặt chỗ còn hiệu lực”.

Hai quy tắc cuối có thể cần những cách thực thi khác nhau. Chọn cách lưu dữ liệu tốt có thể biến một quy tắc nhiều hàng phức tạp thành ràng buộc UNIQUE dễ bảo vệ hơn.

## 3. Lớp cơ sở dữ liệu: biến bất biến thành ràng buộc

Ví dụ dưới đây dùng cú pháp **PostgreSQL**. Hệ quản trị khác có thể khác về cú pháp, khả năng trì hoãn ràng buộc và hành vi khi cạnh tranh đồng thời.

~~~sql
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    balance NUMERIC(19, 2) NOT NULL DEFAULT 0,
    CONSTRAINT accounts_balance_nonnegative CHECK (balance >= 0)
);

CREATE TABLE transfers (
    request_id UUID PRIMARY KEY,
    source_account_id BIGINT NOT NULL REFERENCES accounts(id),
    destination_account_id BIGINT NOT NULL REFERENCES accounts(id),
    amount NUMERIC(19, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT transfers_amount_positive CHECK (amount > 0),
    CONSTRAINT transfers_distinct_accounts
        CHECK (source_account_id <> destination_account_id)
);
~~~

Những khai báo này cung cấp các bảo đảm cụ thể:

- **PRIMARY KEY** xác định duy nhất từng tài khoản và từng yêu cầu chuyển tiền; request_id còn có thể làm khóa chống xử lý lặp.
- **NOT NULL** ngăn thiếu các giá trị bắt buộc. Nếu bỏ NOT NULL, điều kiện CHECK có thể không loại được NULL vì kết quả biểu thức là UNKNOWN.
- **CHECK** bảo vệ bất biến trên từng hàng, ví dụ balance ≥ 0 và amount > 0.
- **FOREIGN KEY** ngăn bản ghi chuyển tiền tham chiếu đến tài khoản không tồn tại.
- **NUMERIC(19, 2)** thích hợp hơn kiểu dấu phẩy động nhị phân khi biểu diễn số tiền ở đơn vị có hai chữ số thập phân. Quy tắc tiền tệ và làm tròn vẫn cần được xác định rõ.

Với đặt chỗ theo ghế, một ràng buộc cấu trúc có thể là:

~~~sql
CREATE TABLE seat_reservations (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id BIGINT NOT NULL,
    seat_no VARCHAR(20) NOT NULL,
    CONSTRAINT one_reservation_per_seat UNIQUE (event_id, seat_no)
);
~~~

Trong thiết kế này, bảng chỉ chứa những ghế đã được giữ và một cặp sự kiện–ghế không được xuất hiện hai lần. Nếu hệ thống giữ cả lịch sử hủy trong cùng bảng thì UNIQUE trên toàn bộ bảng có thể quá chặt; khi đó cần thay đổi mô hình hoặc dùng **partial unique index** cho các trạng thái còn hiệu lực, theo quy tắc nghiệp vụ đã định nghĩa.

Điểm đáng chú ý: hai yêu cầu đồng thời đều có thể thực hiện câu hỏi “ghế này còn trống không?” và cùng nhận được kết quả “có”. Nhưng khi cùng cố ghi, ràng buộc UNIQUE tại cơ sở dữ liệu vẫn là lớp bảo vệ quyết định. Kiểm tra trước bằng SELECT chỉ cải thiện thông báo cho người dùng, không thay thế ràng buộc.

### Giới hạn của constraint

CHECK thông thường xử lý biểu thức của **hàng hiện tại**; nó không phải công cụ đáng tin cậy để đếm hoặc cộng dữ liệu ở nhiều hàng khác nhau. Ví dụ quy tắc “phải còn ít nhất một bác sĩ trực trong ca” không thể chỉ giải quyết bằng CHECK trên cột on_duty của từng bác sĩ.

Cần chọn giữa việc **thiết kế lại cấu trúc dữ liệu**, **khóa một tài nguyên chung**, **dùng mức cô lập phù hợp**, hoặc **cơ chế chuyên dụng khác**. Trigger có thể hỗ trợ một số nghiệp vụ, nhưng trigger tự đọc rồi kiểm tra số lượng cũng phải xử lý cạnh tranh đồng thời; thêm trigger không tự động loại bỏ race condition.

## 4. Ví dụ đầy đủ: chuyển tiền với một transaction

Giả sử hai tài khoản cùng một loại tiền, số dư lần lượt là 500 và 200; người dùng muốn chuyển 120.

Trạng thái hợp lệ mong đợi:

| Tài khoản | Trước | Sau |
|---|---:|---:|
| Nguồn | 500 | 380 |
| Đích | 200 | 320 |
| **Tổng** | **700** | **700** |

Đây là hai bất biến khác nhau: **từng số dư không âm** và **tổng số tiền không đổi đối với riêng thao tác chuyển nội bộ này**. CHECK(balance >= 0) có thể hỗ trợ bất biến đầu tiên. Bất biến thứ hai phụ thuộc vào cách ứng dụng thực hiện cả hai cập nhật.

Một luồng xử lý có thể được viết như sau:

~~~sql
BEGIN;

-- request_id do bên gọi giữ ổn định qua các lần thử lại.
-- Dòng này cũng kiểm tra tài khoản tồn tại, số tiền dương
-- và hai tài khoản khác nhau.
INSERT INTO transfers (
    request_id, source_account_id, destination_account_id, amount
) VALUES (
    :request_id, :source_account_id, :destination_account_id, :amount
);

-- Trừ tiền khi số dư hiện tại còn đủ.
UPDATE accounts
SET balance = balance - :amount
WHERE id = :source_account_id
  AND balance >= :amount
RETURNING balance;

-- Ứng dụng PHẢI xác nhận đúng 1 hàng được cập nhật.
-- Nếu không: ROLLBACK, báo thiếu tiền hoặc tài khoản không hợp lệ.

UPDATE accounts
SET balance = balance + :amount
WHERE id = :destination_account_id
RETURNING balance;

-- Ứng dụng PHẢI xác nhận đúng 1 hàng được cập nhật.
-- Nếu không: ROLLBACK, không COMMIT một chuyển tiền dở dang.

COMMIT;
~~~

Đây là **mẫu luồng xử lý có điểm kiểm tra từ ứng dụng**, không phải một script SQL được chạy mù từ đầu đến cuối. Khi bước nào không đạt điều kiện, ứng dụng phải dừng và rollback transaction. Quyền sở hữu tài khoản, hạn mức chuyển, loại tiền, quyền truy cập và chính sách chống gian lận còn phải được kiểm tra theo nghiệp vụ.

Tại PostgreSQL với isolation level **READ COMMITTED**, một UPDATE như trên sẽ khóa hàng cần sửa và đánh giá lại điều kiện WHERE khi gặp cập nhật đồng thời trên cùng hàng. Vì vậy, hai lệnh trừ tiền cạnh tranh trên **cùng tài khoản** không thể cùng dựa vào số dư cũ để vượt qua điều kiện balance >= amount. Ràng buộc CHECK tiếp tục chặn số dư âm nếu một nhánh code khác cố ghi trực tiếp.

Mặt khác:

- Nếu ứng dụng **quên cập nhật tài khoản đích**, việc commit bản ghi transfers và trừ tiền vẫn có thể qua các constraint đã định nghĩa. Database không tự suy ra “tổng tiền phải được bảo toàn”.
- Nếu ứng dụng **không kiểm tra số hàng bị ảnh hưởng**, một UPDATE ghi 0 hàng vẫn không nhất thiết làm transaction thất bại.
- Nếu hai lần gọi dùng **cùng request_id**, PRIMARY KEY ngăn lần INSERT thứ hai; ứng dụng cần lấy kết quả lần xử lý trước, đối chiếu payload và trả phản hồi phù hợp. Tạo request_id mới ở mỗi lần retry sẽ làm mất đặc tính idempotency.
- Nếu hai chuyển tiền cùng khóa các tài khoản theo thứ tự ngược nhau, có thể xuất hiện **deadlock**. Ứng dụng cần có chính sách retry cho lỗi tạm thời; thiết kế khóa các tài khoản theo thứ tự cố định có thể giảm khả năng gặp deadlock.

Như vậy, transaction cho phép các bước được commit hoặc rollback cùng nhau; **logic thực hiện, kết quả từng bước và các kiểm tra nghiệp vụ vẫn là trách nhiệm của ứng dụng**.

## 5. Vì sao transaction đúng khi chạy riêng vẫn có thể sai khi chạy đồng thời?

Xét lịch trực với quy tắc:

> Mỗi ca phải có ít nhất một bác sĩ đang trực.

Ban đầu, bác sĩ A và B đều trực. Mỗi người có thể xin nghỉ nếu hệ thống thấy vẫn còn ít nhất một người khác.

~~~sql
CREATE TABLE on_call (
    shift_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,
    on_duty BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
~~~

Hai transaction cùng chạy trong PostgreSQL ở mức **REPEATABLE READ** (dựa trên snapshot isolation):

| Thời điểm | Transaction T1: bác sĩ A xin nghỉ | Transaction T2: bác sĩ B xin nghỉ |
|---|---|---|
| 1 | Đọc số người trực: 2 | |
| 2 | | Đọc số người trực: 2 |
| 3 | Thấy có thể cho A nghỉ | Thấy có thể cho B nghỉ |
| 4 | Cập nhật hàng A thành on_duty = FALSE | |
| 5 | | Cập nhật hàng B thành on_duty = FALSE |
| 6 | COMMIT | COMMIT |

**Kết quả: 0 bác sĩ trực**, vi phạm bất biến mặc dù mỗi transaction đã kiểm tra điều kiện bằng dữ liệu mà nó nhìn thấy. Hai transaction ghi vào hai hàng khác nhau, nên không nhất thiết phát sinh xung đột ghi trực tiếp. Hiện tượng này là **write skew**.

Đây cũng là lý do không thể khẳng định “đã dùng transaction” hoặc “đã đặt REPEATABLE READ” thì mọi quy tắc liên quan nhiều hàng đều an toàn.

### Cách bảo vệ bất biến nhiều hàng

**Cách 1 — SERIALIZABLE và retry toàn bộ transaction.** PostgreSQL SERIALIZABLE sử dụng cơ chế phát hiện những mẫu phụ thuộc có thể dẫn đến kết quả không thể tuần tự hóa. Trong ví dụ hai bác sĩ, một transaction có thể bị hủy với lỗi serialization failure; ứng dụng phải retry **từ đầu**, bao gồm bước đọc và kiểm tra điều kiện.

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*)
FROM on_call
WHERE shift_id = :shift_id AND on_duty = TRUE;

-- Chỉ cho bác sĩ hiện tại nghỉ nếu kết quả còn ít nhất 2.
-- Việc kiểm tra và UPDATE phải nằm trong CÙNG transaction.

UPDATE on_call
SET on_duty = FALSE
WHERE shift_id = :shift_id
  AND doctor_id = :doctor_id
  AND on_duty = TRUE;

COMMIT;
~~~

Nếu SELECT trả về 1, ứng dụng không được thực hiện UPDATE. Nếu COMMIT báo lỗi serialization, transaction không thành công: cần bắt đầu transaction mới và kiểm tra lại. Việc retry chỉ riêng câu UPDATE bằng kết quả SELECT cũ sẽ không đúng.

**Cách 2 — khóa một hàng đại diện chung cho ca.** Nếu mô hình có bảng shifts với một hàng cho mỗi ca, tất cả thao tác đổi người trực có thể theo cùng giao thức: khóa hàng shifts trước, sau đó đếm người trực rồi cập nhật. Ví dụ câu lệnh đầu tiên:

~~~sql
SELECT id
FROM shifts
WHERE id = :shift_id
FOR UPDATE;
~~~

Khóa đó đóng vai trò điểm phối hợp cho các giao dịch sửa cùng một ca. Cách làm chỉ an toàn nếu **mọi đường ghi liên quan đều tuân thủ giao thức khóa** và thứ tự thao tác nhất quán.

**Cách 3 — thay đổi mô hình dữ liệu.** Trong một số bài toán, có thể ghi trực tiếp tài nguyên độc quyền hoặc số lượng còn lại trong một hàng rồi dùng UPDATE có điều kiện. Khi đó xung đột cạnh tranh tập trung vào cùng một hàng, dễ bảo vệ hơn việc nhiều giao dịch cùng đếm một tập các hàng.

Chọn biện pháp dựa trên **bất biến và kiểu cạnh tranh thực tế**. Isolation level cao hơn có thể làm tăng retry hoặc chi phí; khóa có thể làm giảm song song; ràng buộc cấu trúc thường đơn giản hơn nếu mô hình nghiệp vụ cho phép.

## 6. Trách nhiệm của database và ứng dụng

Một thiết kế tốt dùng **phòng vệ nhiều lớp**. Hai lớp không thay thế hoàn toàn cho nhau.

| Việc cần làm | Database | Ứng dụng |
|---|---|---|
| Không cho giá trị âm, rỗng, khóa ngoại sai | Cưỡng chế bằng NOT NULL, CHECK, FK | Kiểm tra sớm để phản hồi rõ ràng |
| Không cho trùng khóa nghiệp vụ | Cưỡng chế bằng UNIQUE/index | Xác định phạm vi duy nhất và xử lý xung đột |
| Chuyển tiền đủ bước | Cung cấp atomic transaction | Xác định thứ tự thao tác và kiểm tra kết quả từng bước |
| Không bán quá sức chứa | Cung cấp lock, isolation, cập nhật có điều kiện | Chọn chiến lược đồng thời bảo vệ bất biến |
| Kiểm tra người dùng có quyền thao tác | Không tự hiểu đầy đủ chính sách ứng dụng | Xác thực, phân quyền, kiểm tra sở hữu |
| Tránh xử lý lại yêu cầu | Lưu unique request key và kết quả liên quan | Giữ khóa idempotency, đối chiếu request và trả kết quả cũ |
| Phát thông báo cho hệ thống khác | Chỉ bảo đảm transaction trong phạm vi DB của nó | Điều phối tác vụ bên ngoài, retry và chống xử lý lặp |

### Phân biệt ba loại kiểm tra

1. **Validation đầu vào:** “Số tiền người dùng gửi lên có lớn hơn 0 không?” Có thể thực hiện trước transaction để trả thông báo dễ hiểu; vẫn cần constraint vì dữ liệu có thể đến từ luồng khác.
2. **Kiểm tra trạng thái hiện tại:** “Tài khoản còn đủ tiền ngay lúc ghi không?” Phải gắn với thao tác ghi an toàn như UPDATE có điều kiện hoặc cơ chế khóa; kiểm tra trước rồi ghi sau mà không phối hợp sẽ có race condition.
3. **Kiểm tra bất biến toàn cục:** “Sau khi cho người này nghỉ, cả ca còn người trực không?” Phải xét cả phạm vi dữ liệu liên quan và chiến lược transaction đồng thời.

Không nên đặt quy tắc nghiệp vụ cốt lõi chỉ trong controller hoặc giao diện. Những đường ghi khác như batch job, message consumer, admin script hay một service mới có thể bỏ qua validation ở giao diện.

## 7. Trạng thái hợp lệ cần được giữ qua vòng đời nghiệp vụ

Bất biến thường gắn với **trạng thái**. Ví dụ đơn hàng có các trạng thái CREATED, PAID, SHIPPED và CANCELLED. Hệ thống có thể quy định:

- Chỉ đơn CREATED mới được thanh toán.
- Đơn PAID mới được giao.
- Đơn CANCELLED không được chuyển sang SHIPPED.

Một cách thực thi là cập nhật kèm điều kiện trên **trạng thái hiện tại**:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE id = :order_id
  AND status = 'PAID'
RETURNING id;
~~~

Nếu 0 hàng được cập nhật, ứng dụng cần xác định nguyên nhân: không có đơn hàng, trạng thái đã thay đổi, hoặc yêu cầu đã được xử lý trước đó. Điều kiện trong UPDATE làm bước “kiểm tra rồi đổi trạng thái” diễn ra gắn với cùng một lệnh ghi, tránh cửa sổ cạnh tranh giữa SELECT và UPDATE riêng rẽ.

Một cột CHECK hoặc tập giá trị ENUM có thể giới hạn **các trạng thái hợp lệ** nhưng thường không đủ để diễn đạt mọi **chuyển trạng thái hợp lệ** theo lịch sử. Ứng dụng phải bảo vệ luật chuyển trạng thái, và với yêu cầu phức tạp có thể cần lưu phiên bản, nhật ký sự kiện hoặc cơ chế kiểm soát riêng.

## 8. Khi transaction gặp lỗi: từ database đến hành vi ứng dụng

Trong PostgreSQL, một số SQLSTATE hữu ích là:

| SQLSTATE | Tình huống | Cách phản ứng điển hình |
|---|---|---|
| 23505 | unique_violation | Xem là xung đột hoặc yêu cầu lặp; tra kết quả cũ khi dùng idempotency key |
| 23503 | foreign_key_violation | Không thể tạo liên kết tới dữ liệu không tồn tại hoặc thực hiện thao tác phá quan hệ |
| 23514 | check_violation | Dữ liệu không đạt bất biến đã khai báo; sửa đầu vào hoặc logic |
| 40001 | serialization_failure | Retry **toàn bộ transaction** với lần đọc mới |
| 40P01 | deadlock_detected | Có thể retry transaction với chính sách giới hạn và giảm tranh chấp |

Đây là cách phân loại ở mức database; ứng dụng nên chuyển thành lỗi nghiệp vụ/API phù hợp thay vì trả nguyên thông báo SQL cho người dùng.

Khi retry, cần phân biệt:

- **Lỗi nghiệp vụ xác định:** số dư không đủ, dữ liệu vi phạm CHECK, trùng ghế đã bán. Không nên retry vô hạn với cùng điều kiện.
- **Lỗi đồng thời tạm thời:** serialization failure hoặc deadlock. Retry có giới hạn, có backoff khi phù hợp, và phải chạy lại toàn bộ luồng đọc–kiểm tra–ghi.
- **Kết quả commit chưa rõ vì mất kết nối:** bên gọi có thể không biết transaction đã commit hay chưa. Khóa idempotency ổn định giúp kiểm tra và tránh lặp lại tác động.

Đặc biệt, đừng đặt lời gọi tới dịch vụ thanh toán ngoài, gửi email hoặc đẩy message trực tiếp giữa các bước mà bạn giả định database rollback sẽ hoàn tác được. **Rollback trong một database không đảo ngược tác động đã thành công ở hệ thống khác.** Một phương án phổ biến là lưu sự kiện vào **outbox cùng transaction** với dữ liệu nghiệp vụ; worker phát sự kiện sau khi commit, và phía nhận xử lý idempotent vì giao nhận có thể lặp.

## 9. Các hiểu lầm thường gặp

| Hiểu lầm | Giải thích đúng |
|---|---|
| “Dùng BEGIN/COMMIT là dữ liệu sẽ tự đúng.” | Transaction gom các thao tác theo bảo đảm ACID; ứng dụng vẫn có thể commit một chuỗi thao tác sai nghiệp vụ. |
| “Có validation trong code thì không cần constraint.” | Các request đồng thời và những đường ghi khác có thể vượt qua kiểm tra riêng lẻ. Constraint cần là tuyến phòng vệ cuối cho quy tắc có thể biểu diễn ở DB. |
| “Đã dùng REPEATABLE READ thì không thể còn lỗi đồng thời.” | Snapshot isolation ở PostgreSQL vẫn có thể gặp write skew đối với bất biến nhiều hàng. |
| “Cứ thêm trigger kiểm tra COUNT là đủ.” | Trigger cũng cần cách phối hợp với các transaction cạnh tranh; kiểm tra trên snapshot cũ có thể sai. |
| “COMMIT thành công nghĩa là mọi service đã đồng bộ.” | Một transaction DB chỉ bao phủ những thao tác nằm trong phạm vi transaction của hệ đó. |
| “Consistency đồng nghĩa mọi reader thấy dữ liệu mới nhất.” | Đó là vấn đề khả năng quan sát trong concurrency hoặc hệ phân tán, khác với bất biến ACID. |

## 10. Cách phân tích một bài toán thực tế

Khi thiết kế một thao tác có nhiều bước, hãy trả lời lần lượt:

1. **Bất biến là gì?** Viết thành điều kiện có thể kiểm tra được, ví dụ “số ghế đã bán ≤ sức chứa”, “số dư ≥ 0”, “mỗi request_id được áp dụng nhiều nhất một lần”.
2. **Bất biến liên quan dữ liệu nào?** Một cột, một hàng, cặp khóa duy nhất, nhiều hàng, nhiều bảng hay nhiều hệ thống?
3. **Phần nào có thể biểu diễn bằng schema?** Ưu tiên NOT NULL, CHECK, UNIQUE, FK và thiết kế mô hình phù hợp cho quy tắc ổn định.
4. **Điều gì xảy ra nếu có hai request cùng lúc?** Mô phỏng lịch xen kẽ giữa các bước đọc, kiểm tra và ghi. Xác định liệu chúng có cập nhật cùng một hàng hay các hàng khác nhau.
5. **Transaction bao trùm những bước nào?** Đặt việc kiểm tra trạng thái, cập nhật và lưu idempotency key trong một ranh giới giao dịch thích hợp.
6. **Khi xung đột thì làm gì?** Kiểm tra số hàng được cập nhật, rollback khi bất biến không đạt, retry đúng loại lỗi và giữ khóa yêu cầu ổn định.
7. **Có tác động ngoài database không?** Nếu có, xác định giao thức phối hợp, idempotency, outbox hoặc xử lý bù trừ phù hợp.

### Bài tập tư duy

Một hệ thống bán 100 vé không có số ghế cụ thể. Mỗi request thực hiện SELECT COUNT(*) để đếm số vé đã bán; nếu nhỏ hơn 100 thì INSERT một vé mới.

- Nếu hai request cùng thấy COUNT(*) = 99, kết quả có thể là gì dưới isolation cho phép hai lần INSERT cùng commit?
- Vì sao CHECK trên hàng ticket riêng lẻ không mô tả được sức chứa toàn sự kiện?
- Có thể chuyển quy tắc đó thành một UPDATE có điều kiện trên hàng event với cột remaining_tickets không? Nếu làm vậy, ứng dụng cần kiểm tra điều gì khi số hàng cập nhật bằng 0?
- Khi chuyển sang SERIALIZABLE, nếu một giao dịch báo serialization failure, cần thực hiện lại bước nào?

Bài học chính của Consistency là: **bất biến xác định trạng thái hợp lệ; database cưỡng chế những bất biến đã biểu diễn được; transaction và isolation tạo cơ chế giữ chúng khi nhiều thao tác cùng diễn ra; ứng dụng chịu trách nhiệm về quy tắc nghiệp vụ, cách tổ chức giao dịch và cách xử lý lỗi.**
