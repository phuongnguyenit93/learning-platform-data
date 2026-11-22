# Tranh chấp trên điều kiện tổng hợp và hàng chưa tồn tại

Snapshot Isolation (cô lập ảnh chụp) cho phép mỗi giao dịch đọc một ảnh chụp nhất quán của dữ liệu tại một thời điểm. Nhờ đó, các câu lệnh đọc thường không phải chờ giao dịch khác ghi dữ liệu. Khi hai giao dịch cùng cập nhật một hàng, nhiều hệ quản trị dùng quy tắc xung đột ghi: chỉ một giao dịch được commit, giao dịch còn lại phải rollback hoặc nhận lỗi xung đột.

Tuy nhiên, không phải mọi tranh chấp đều thể hiện bằng việc hai giao dịch ghi cùng một hàng. Một giao dịch có thể kiểm tra `COUNT`, `SUM`, `MIN`, `MAX` hoặc một điều kiện trên cả tập hàng, rồi cập nhật một hàng riêng. Một giao dịch khác có thể đọc cùng điều kiện và cập nhật một hàng khác. Hai lần ghi không đụng nhau, nhưng kết quả kết hợp của chúng có thể làm sai quy tắc nghiệp vụ. Tình huống tương tự xảy ra khi một truy vấn không tìm thấy hàng nào và nhiều giao dịch cùng quyết định chèn hàng mới.

Bài học này giải thích vì sao Snapshot Isolation có thể bỏ sót các xung đột dạng tổng hợp và predicate, cách chúng xuất hiện trên hàng chưa tồn tại, cũng như các cách bảo vệ điều kiện nghiệp vụ.

## 1. Snapshot Isolation phát hiện loại xung đột nào?

Trong mô hình Snapshot Isolation phổ biến, một giao dịch đọc dữ liệu từ snapshot của nó. Những thay đổi được giao dịch khác commit sau thời điểm snapshot được thiết lập thường không xuất hiện trong các lần đọc tiếp theo của giao dịch hiện tại. Khi ghi, hệ thống kiểm tra xung đột với các thay đổi đồng thời. Một quy tắc thường gặp là **first-committer-wins**: nếu hai giao dịch cùng sửa một phiên bản hàng, giao dịch commit trước có thể thành công và giao dịch còn lại bị hủy do write-write conflict.

Ví dụ hai giao dịch cùng cập nhật số dư của tài khoản `A`:

```text
T1: đọc A = 100 từ snapshot
T2: đọc A = 100 từ snapshot
T1: ghi A = 90
T2: ghi A = 80
T1: COMMIT thành công
T2: COMMIT bị từ chối do xung đột ghi trên A
```

Hệ thống có thể nhận ra xung đột vì cả T1 và T2 đều ghi cùng một hàng A. Nhưng nếu T1 ghi hàng A còn T2 ghi hàng B, hệ thống có thể không thấy write-write conflict nào, dù hai giao dịch cùng dựa trên một điều kiện tổng hợp liên quan đến cả A và B.

Đó là giới hạn quan trọng: Snapshot Isolation ngăn nhiều dạng xung đột ghi trực tiếp, nhưng bản thân nó không bảo đảm mọi lịch thực thi đều tương đương với một thứ tự chạy tuần tự. Một bất thường nổi bật là **write skew** (lệch ghi): hai giao dịch đọc dữ liệu liên quan từ cùng một snapshot, sau đó ghi các hàng khác nhau, khiến một bất biến nghiệp vụ bị phá vỡ.

> Lưu ý: thời điểm tạo snapshot, cách xử lý xung đột ghi và tên isolation level cụ thể phụ thuộc hệ quản trị. Phần dưới mô tả hành vi theo mô hình Snapshot Isolation; khi áp dụng, cần đối chiếu tài liệu của hệ cơ sở dữ liệu đang dùng.

## 2. Tranh chấp trên điều kiện tổng hợp

Điều kiện tổng hợp là điều kiện được tính từ nhiều hàng hoặc từ một tập kết quả, ví dụ:

- Số bác sĩ đang trực phải luôn lớn hơn hoặc bằng 1.
- Tổng số lượng đã đặt không được vượt quá sức chứa.
- Tổng số tiền phân bổ cho các hạng mục không được vượt ngân sách.
- Phải còn ít nhất một người quản trị đang hoạt động.
- Số chỗ đã giữ trong một chuyến bay phải nhỏ hơn số ghế được phép bán.

Các điều kiện này thường được kiểm tra bằng `COUNT`, `SUM` hoặc một truy vấn lọc theo predicate. Chúng phụ thuộc vào cả tập hàng thỏa mãn điều kiện, chứ không chỉ một hàng cụ thể.

### Ví dụ: luôn phải có ít nhất một bác sĩ trực

Giả sử bảng `doctor_shift` lưu trạng thái trực của bác sĩ:

| doctor_id | on_call |
| --- | --- |
| 10 | TRUE |
| 20 | TRUE |

Quy tắc nghiệp vụ là luôn phải có ít nhất một bác sĩ trực. T1 muốn cho bác sĩ 10 nghỉ trực; T2 muốn cho bác sĩ 20 nghỉ trực. Mỗi giao dịch kiểm tra số bác sĩ đang trực trước khi cập nhật.

```sql
-- T1
BEGIN;
SELECT COUNT(*)
FROM doctor_shift
WHERE on_call = TRUE;
-- Kết quả theo snapshot của T1: 2

UPDATE doctor_shift
SET on_call = FALSE
WHERE doctor_id = 10;
COMMIT;
```

```sql
-- T2 chạy đồng thời với T1
BEGIN;
SELECT COUNT(*)
FROM doctor_shift
WHERE on_call = TRUE;
-- Kết quả theo snapshot của T2: 2

UPDATE doctor_shift
SET on_call = FALSE
WHERE doctor_id = 20;
COMMIT;
```

Lịch thực thi có thể diễn ra như sau:

| Bước | T1 | T2 |
| --- | --- | --- |
| 1 | Đọc snapshot: có 2 bác sĩ trực | |
| 2 | | Đọc cùng snapshot: có 2 bác sĩ trực |
| 3 | Cập nhật bác sĩ 10 thành không trực | |
| 4 | | Cập nhật bác sĩ 20 thành không trực |
| 5 | COMMIT | |
| 6 | | COMMIT |

Hai giao dịch ghi hai hàng khác nhau. Theo Snapshot Isolation, nếu không có cơ chế bổ sung phát hiện predicate conflict, cả hai có thể commit. Kết quả cuối cùng là không còn bác sĩ nào trực, dù mỗi giao dịch riêng lẻ đều đã nhìn thấy hai bác sĩ trực khi kiểm tra.

Đây là write skew. Mỗi giao dịch đều thỏa điều kiện trên snapshot mà nó đọc, nhưng khi kết hợp hai lần ghi thì điều kiện toàn cục bị vi phạm. Việc kiểm tra `COUNT(*)` không tự động khóa tất cả hàng liên quan hoặc tạo ra một điểm ghi chung cho hai giao dịch.

### Ví dụ: tổng số lượng đặt vượt sức chứa

Giả sử một phòng có sức chứa 10 người. Bảng `reservation` lưu các lượt đặt chỗ. Hai giao dịch đồng thời muốn thêm 6 người mỗi giao dịch.

```sql
-- T1 và T2 cùng đọc tổng số người đã đặt từ snapshot
SELECT COALESCE(SUM(guest_count), 0)
FROM reservation
WHERE room_id = 7;
-- Cả hai đều thấy tổng hiện tại là 0

-- T1 chèn một hàng mới
INSERT INTO reservation(room_id, guest_count)
VALUES (7, 6);

-- T2 chèn một hàng khác
INSERT INTO reservation(room_id, guest_count)
VALUES (7, 6);
```

Hai giao dịch chèn hai hàng mới với khóa chính khác nhau. Không có hàng cũ nào bị cả hai cùng cập nhật, nên kiểm tra write-write conflict trên từng hàng không nhất thiết phát hiện vấn đề. Nếu cả hai commit, tổng số người đặt là 12, vượt sức chứa 10.

Điểm chung của hai ví dụ là quyết định ghi dựa trên một điều kiện liên quan đến nhiều hàng, nhưng mỗi giao dịch lại ghi vào một hàng riêng. Điều kiện tổng hợp cần được bảo vệ ở cấp tập dữ liệu hoặc chuyển thành một điểm xung đột chung.

## 3. Tranh chấp trên predicate và hàng chưa tồn tại

Predicate là điều kiện xác định một tập hàng, ví dụ `email = 'a@example.com'`, `status = 'OPEN'` hoặc `start_time < :end AND end_time > :start`. Một truy vấn có thể trả về một hoặc nhiều hàng, hoặc không trả về hàng nào.

Với Snapshot Isolation dựa trên MVCC, truy vấn đọc thường nhìn thấy các hàng phù hợp với snapshot. Nếu không có hàng nào thỏa predicate, điều đó chỉ có nghĩa là snapshot hiện tại không chứa hàng phù hợp. Nó không có nghĩa rằng hệ thống đã khóa một vị trí trống để ngăn giao dịch khác chèn hàng thỏa điều kiện đó.

### Ví dụ: hai giao dịch cùng tạo một người dùng

Giả sử ứng dụng kiểm tra email đã tồn tại hay chưa rồi mới tạo tài khoản:

```sql
-- T1
BEGIN;
SELECT user_id
FROM app_user
WHERE email = 'linh@example.com';
-- Không có hàng nào

-- T2
BEGIN;
SELECT user_id
FROM app_user
WHERE email = 'linh@example.com';
-- Cũng không có hàng nào trong snapshot của T2

-- Cả hai giao dịch đều thử chèn
INSERT INTO app_user(email) VALUES ('linh@example.com');
```

Nếu bảng không có ràng buộc duy nhất trên `email`, hai hàng có thể được tạo. Ứng dụng đã kiểm tra trước khi chèn, nhưng hai lần kiểm tra cùng nhìn thấy trạng thái chưa có người dùng.

Nếu có `UNIQUE(email)`, chỉ một giá trị email đó được chấp nhận. Một giao dịch có thể chèn thành công; giao dịch còn lại nhận lỗi vi phạm unique constraint hoặc lỗi tương đương khi hệ quản trị kiểm tra chỉ mục duy nhất. Chi tiết thời điểm báo lỗi tùy hệ quản trị, nhưng ràng buộc ở cơ sở dữ liệu mới là hàng rào bảo vệ tính duy nhất.

Ví dụ khai báo ràng buộc:

```sql
ALTER TABLE app_user
ADD CONSTRAINT uq_app_user_email UNIQUE (email);
```

Kiểm tra bằng `SELECT` trước khi `INSERT` vẫn hữu ích để đưa ra thông báo thân thiện, nhưng không thay thế được ràng buộc duy nhất. Ứng dụng phải xử lý trường hợp giao dịch khác chèn cùng giá trị trong khoảng thời gian giữa hai câu lệnh.

### Ví dụ: không có hàng đặt phòng nào trong khoảng thời gian

Giả sử một phòng họp được đặt theo khoảng thời gian. T1 kiểm tra xem đã có cuộc họp nào giao với khoảng 10:00–11:00 hay chưa. T2 cũng kiểm tra cùng điều kiện. Cả hai đều thấy không có hàng phù hợp, rồi chèn hai cuộc họp khác nhau nhưng có thời gian giao nhau.

```sql
SELECT booking_id
FROM room_booking
WHERE room_id = 3
  AND start_time < TIMESTAMP '2026-11-15 11:00:00'
  AND end_time   > TIMESTAMP '2026-11-15 10:00:00';
```

Điều kiện trên tìm các khoảng thời gian giao nhau. Khi kết quả rỗng, không tồn tại một hàng cụ thể để `SELECT ... FOR UPDATE` khóa. Hai giao dịch vẫn có thể chèn hai hàng mới, mỗi hàng mang một `booking_id` khác nhau, trong khi vi phạm quy tắc không được đặt phòng trùng giờ.

Ràng buộc `UNIQUE(room_id, start_time)` chỉ ngăn hai hàng có cùng thời điểm bắt đầu; nó không ngăn mọi trường hợp khoảng thời gian giao nhau. Cần một ràng buộc biểu diễn đúng điều kiện không chồng lấn, hoặc một cơ chế tuần tự hóa việc đặt phòng theo `room_id`.

## 4. Vì sao khóa hàng hiện có chưa đủ?

Khóa hàng thông thường bảo vệ những hàng đã được tìm thấy. Nhưng một predicate có thể mô tả cả những hàng chưa tồn tại. Ví dụ:

```sql
SELECT *
FROM reservation
WHERE room_id = 7;
```

Nếu kết quả rỗng, không có hàng `reservation` cụ thể nào để khóa bằng row lock. Một giao dịch khác có thể chèn hàng `room_id = 7` trong lúc giao dịch đầu vẫn đang mở.

Một số hệ quản trị và isolation level có cơ chế khóa phạm vi, khóa khoảng trống hoặc predicate lock. Các cơ chế đó bảo vệ phạm vi mà điều kiện truy vấn mô tả, bao gồm cả vị trí mà hàng mới có thể được chèn. Tên gọi và cách triển khai khác nhau:

- **Key-range lock:** khóa một khoảng giá trị trong chỉ mục, ngăn thao tác chèn vào khoảng đó khi xung đột.
- **Gap lock:** khóa khoảng trống giữa các khóa chỉ mục, tùy hệ quản trị và isolation level.
- **Predicate lock:** ghi nhận điều kiện truy vấn để phát hiện hoặc ngăn thao tác làm thay đổi tập kết quả của predicate.
- **Serializable Snapshot Isolation (SSI):** có thể theo dõi quan hệ đọc/ghi và hủy một giao dịch khi phát hiện cấu trúc phụ thuộc có nguy cơ tạo lịch không tuần tự, thay vì nhất thiết chặn mọi thao tác ngay từ đầu.

Không phải mọi hệ quản trị đều dùng cùng cơ chế. Một hệ thống dùng MVCC có thể cho phép truy vấn đọc tiếp tục mà không khóa hàng theo cách truyền thống; một hệ thống khác có thể dùng range lock ở mức cô lập cao hơn. Vì vậy, không nên suy ra hành vi khóa chỉ từ câu SQL hoặc tên `REPEATABLE READ`; cần đọc tài liệu của sản phẩm cụ thể.

## 5. Các cách bảo vệ điều kiện tổng hợp và predicate

Không có một cách xử lý phù hợp cho mọi điều kiện. Hãy chọn cơ chế dựa trên loại quy tắc cần giữ, khả năng của hệ quản trị và mức tranh chấp.

### Dùng Serializable khi cần tính đúng đắn trên toàn bộ điều kiện

Nếu điều kiện nghiệp vụ phụ thuộc vào một tập hàng hoặc kết quả tổng hợp, Serializable là lựa chọn trực tiếp khi ứng dụng cần mọi giao dịch có kết quả tương đương với một thứ tự chạy tuần tự.

Ở mức Serializable, hệ quản trị phải ngăn hoặc phát hiện các phụ thuộc khiến lịch thực thi không thể tuần tự hóa. Cách thực hiện có thể là khóa phạm vi/predicate, hoặc theo dõi phụ thuộc rồi hủy một giao dịch có nguy cơ. Với SSI, giao dịch vẫn có thể chạy đồng thời và đọc snapshot, nhưng một giao dịch có thể kết thúc bằng serialization failure khi hệ thống phát hiện cấu trúc phụ thuộc nguy hiểm.

Ứng dụng cần sẵn sàng chạy lại **toàn bộ transaction** khi nhận lỗi serialization. Không nên chỉ chạy lại câu lệnh cuối trong transaction cũ vì snapshot và các quyết định trước đó có thể đã không còn hợp lệ.

### Dùng ràng buộc ở cơ sở dữ liệu

Với quy tắc có thể biểu diễn bằng constraint, hãy để cơ sở dữ liệu kiểm tra tại nơi dữ liệu được ghi:

- `PRIMARY KEY` hoặc `UNIQUE` cho tính duy nhất.
- `FOREIGN KEY` cho quan hệ tham chiếu.
- `CHECK` cho điều kiện trên một hàng.
- Exclusion constraint hoặc cơ chế tương đương để ngăn các khoảng giá trị giao nhau, nếu hệ quản trị hỗ trợ.

Ràng buộc duy nhất là cách phù hợp cho ví dụ email. Với khoảng đặt phòng, exclusion constraint có thể biểu diễn rằng hai khoảng của cùng một phòng không được giao nhau trên hệ quản trị hỗ trợ loại ràng buộc này.

Không nên giả định một `CHECK` thông thường có thể an toàn kiểm tra `SUM` hoặc `COUNT` trên các hàng khác. Nhiều hệ quản trị giới hạn CHECK ở biểu thức của hàng hiện tại; ngay cả khi dùng trigger để tính tổng, trigger vẫn cần cơ chế đồng bộ hóa phù hợp để tránh hai giao dịch cùng tính trên snapshot cũ.

### Tạo một hàng điều phối làm điểm xung đột chung

Nếu nhiều giao dịch cần bảo vệ cùng một quy tắc, có thể tạo một hàng đại diện cho tài nguyên hoặc nhóm dữ liệu. Mọi giao dịch thay đổi nhóm đó phải cập nhật hàng điều phối trong cùng transaction. Nhờ vậy, các giao dịch tạo ra write-write conflict trên cùng một hàng.

Ví dụ bảng `room_capacity` lưu số chỗ đã dùng và sức chứa:

```sql
UPDATE room_capacity
SET reserved_count = reserved_count + 6
WHERE room_id = 7
  AND reserved_count + 6 <= capacity;
```

Ứng dụng kiểm tra số hàng được cập nhật:

- Nếu cập nhật được một hàng, số chỗ đã được giữ thành công.
- Nếu không cập nhật hàng nào, phòng không tồn tại hoặc không còn đủ chỗ theo điều kiện.
- Nếu hai giao dịch cập nhật đồng thời cùng một hàng, hệ quản trị phải đồng bộ hóa chúng bằng khóa ghi hoặc báo xung đột theo isolation level.

Hàng `room_capacity` trở thành điểm điều phối chung cho mọi giao dịch đặt chỗ của phòng 7. Cần bảo đảm mọi đường ghi đều cập nhật hàng này; nếu một luồng chèn `reservation` mà bỏ qua bộ đếm, điều kiện tổng vẫn có thể bị phá vỡ. Việc cập nhật bộ đếm và chèn chi tiết đặt chỗ phải nằm trong cùng transaction để tránh lệch dữ liệu.

Một cách tương tự là cập nhật cột `version` của hàng cha hoặc hàng guard. Việc cập nhật hàng guard tạo xung đột ghi chung, giúp một giao dịch bị từ chối hoặc phải thử lại thay vì cả hai cùng commit trên các hàng chi tiết khác nhau. Chỉ khóa guard mà không tạo thay đổi xung đột có thể chưa đủ nếu transaction-level snapshot đã được thiết lập trước lúc chờ; phải kiểm tra semantics của hệ quản trị và cách lấy snapshot.

### Dùng khóa tường minh trên hàng cha hoặc khóa ứng dụng

Một phương án khác là khóa một hàng cha đã tồn tại, chẳng hạn hàng phòng họp, trước khi kiểm tra và chèn lịch đặt. Mọi giao dịch đặt cùng phòng phải tuân theo cùng quy ước khóa. Có thể dùng `SELECT ... FOR UPDATE` trên hàng cha, hoặc advisory lock theo mã phòng nếu hệ quản trị hỗ trợ.

Khóa điều phối chỉ có tác dụng nếu tất cả các luồng ghi cùng tuân thủ. Ngoài ra, với Snapshot Isolation, cần chú ý thời điểm snapshot được tạo: một giao dịch đã lấy snapshot cũ rồi chờ khóa có thể tiếp tục đọc dữ liệu cũ sau khi được cấp khóa, tùy hệ quản trị. Để bảo đảm, có thể kết hợp việc khóa với cập nhật hàng guard, lấy snapshot sau khi có khóa trong mô hình cho phép, hoặc dùng Serializable. Hãy kiểm tra chính xác hành vi của hệ quản trị trước khi dựa vào mẫu này.

### Chuyển điều kiện tập hợp thành một tài nguyên có thể cập nhật nguyên tử

Nếu điều kiện tổng hợp được dùng thường xuyên, có thể duy trì một hàng tổng hợp như `reserved_count`, `active_admin_count` hoặc `allocated_amount`. Cập nhật giá trị tổng hợp bằng một câu lệnh có điều kiện sẽ tạo ra điểm ghi chung mà cơ sở dữ liệu có thể đồng bộ hóa.

Ví dụ ngân sách:

```sql
UPDATE project_budget
SET allocated_amount = allocated_amount + :amount
WHERE project_id = :project_id
  AND allocated_amount + :amount <= budget_limit;
```

Nếu câu lệnh cập nhật không tác động hàng nào, ứng dụng từ chối khoản phân bổ. Nếu cập nhật thành công, ứng dụng chèn chi tiết phân bổ trong cùng transaction. Nếu chèn chi tiết thất bại, rollback sẽ hoàn tác cả thay đổi tổng hợp.

Mẫu này làm cho mọi lần phân bổ của cùng dự án cạnh tranh trên cùng hàng `project_budget`. Nó giảm việc phải tính lại `SUM` trên toàn bộ bảng, nhưng cần giữ hàng tổng hợp đồng nhất với các hàng chi tiết và có thể trở thành điểm nóng khi lượng ghi cao.

## 6. Chọn cách xử lý theo loại điều kiện

| Tình huống | Rủi ro với Snapshot Isolation | Cơ chế thường phù hợp |
| --- | --- | --- |
| Email phải duy nhất | Hai giao dịch cùng thấy email chưa tồn tại rồi cùng chèn | `UNIQUE(email)` và xử lý lỗi vi phạm constraint |
| Không được đặt trùng một thời điểm duy nhất | Hai giao dịch cùng thấy khóa nghiệp vụ chưa có | `UNIQUE` trên khóa nghiệp vụ phù hợp |
| Các khoảng đặt phòng không được giao nhau | Hai giao dịch cùng thấy không có khoảng giao nhau rồi chèn khoảng mới | Exclusion constraint, range/predicate locking hoặc Serializable |
| Tổng số chỗ không vượt sức chứa | Hai giao dịch cùng tính tổng cũ rồi thêm các hàng khác nhau | Hàng bộ đếm cập nhật nguyên tử, hàng guard có xung đột ghi hoặc Serializable |
| Luôn phải còn ít nhất một người trực | Hai giao dịch cùng đọc số người trực rồi tắt trạng thái ở hai hàng khác nhau | Serializable, khóa điều phối chung hoặc mô hình dữ liệu có điểm cập nhật chung |
| Một predicate phức tạp trên nhiều bảng | Các giao dịch đọc cùng tập dữ liệu nhưng ghi những hàng khác nhau | Serializable và kiểm thử các luồng ghi liên quan |

Ràng buộc ở cơ sở dữ liệu thường là lớp bảo vệ cuối cùng vì mọi ứng dụng kết nối đều phải tuân thủ. Khóa ở tầng ứng dụng có thể hữu ích để điều phối, nhưng dễ bị bỏ qua nếu có một luồng ghi khác không dùng cùng quy ước. Serializable phù hợp khi quy tắc khó chuyển thành constraint hoặc điểm ghi chung.

## 7. Xử lý lỗi và thử lại transaction

Khi cơ sở dữ liệu từ chối transaction vì serialization failure, deadlock hoặc unique constraint, ứng dụng cần phân biệt loại lỗi để phản hồi phù hợp.

1. **Serialization failure:** rollback transaction hiện tại và thử lại toàn bộ transaction với snapshot mới, nếu thao tác có thể retry an toàn.
2. **Unique constraint violation:** thường có nghĩa một giao dịch khác đã tạo giá trị duy nhất trước. Có thể thông báo tài nguyên đã tồn tại, lấy bản ghi hiện có hoặc áp dụng quy tắc nghiệp vụ phù hợp; không phải lúc nào cũng nên retry mù quáng.
3. **Deadlock victim:** transaction được chọn làm nạn nhân phải rollback. Ứng dụng có thể retry toàn bộ transaction với giới hạn số lần và backoff.
4. **Điều kiện cập nhật không còn đúng:** nếu câu `UPDATE ... WHERE ...` không cập nhật hàng nào, xử lý như một kết quả nghiệp vụ thất bại, chẳng hạn hết chỗ hoặc vượt ngân sách.

Retry cần có giới hạn và độ trễ ngẫu nhiên phù hợp để tránh nhiều giao dịch thất bại rồi đồng loạt thử lại. Nếu transaction có tác dụng phụ bên ngoài cơ sở dữ liệu như gửi email hoặc gọi dịch vụ thanh toán, cần thiết kế idempotency hoặc chỉ thực hiện tác dụng phụ sau khi transaction commit thành công.

## 8. Cách kiểm tra một bất thường write skew

Khi điều tra một lỗi dữ liệu có vẻ không thể xảy ra, hãy tìm xem các giao dịch có cùng kiểm tra một điều kiện tập hợp nhưng ghi vào các hàng khác nhau hay không.

Một bài kiểm tra có thể thực hiện bằng hai phiên làm việc:

1. Tạo dữ liệu ban đầu sao cho điều kiện tổng hợp đang đúng, ví dụ hai bác sĩ đều đang trực.
2. Mở hai transaction ở isolation level Snapshot Isolation hoặc mức tương đương.
3. Trong cả hai transaction, đọc cùng `COUNT(*)` hoặc `SUM(...)` trước khi ghi.
4. Cho T1 cập nhật một hàng và T2 cập nhật một hàng khác.
5. Commit cả hai theo lịch xen kẽ có kiểm soát.
6. Đọc lại dữ liệu bằng transaction mới và kiểm tra bất biến nghiệp vụ.

Nếu cả hai commit và điều kiện bị phá vỡ, đó là dấu hiệu của write skew hoặc một predicate anomaly. Sau đó lặp lại bài kiểm tra khi bật Serializable hoặc cơ chế điều phối đã chọn. Kết quả mong muốn là một transaction bị chặn hoặc bị từ chối, hoặc một transaction phải retry, để trạng thái cuối vẫn thỏa quy tắc.

Khi kiểm thử hàng chưa tồn tại, hãy cho hai transaction cùng truy vấn một khóa nghiệp vụ và cùng nhận kết quả rỗng trước khi cả hai thử chèn. Kiểm tra cả trường hợp có và không có constraint. Đối với predicate khoảng thời gian, tạo hai khoảng bắt đầu khác nhau nhưng giao nhau để xác nhận ràng buộc thực sự bao phủ quy tắc, thay vì chỉ kiểm tra trùng giá trị `start_time`.

## 9. Những điểm cần ghi nhớ

- Snapshot Isolation cho các giao dịch đọc từ snapshot nhất quán và thường phát hiện xung đột khi chúng cùng ghi một hàng.
- Một điều kiện `COUNT`, `SUM` hoặc predicate có thể liên quan đến nhiều hàng; hai giao dịch ghi các hàng khác nhau vẫn có thể cùng phá vỡ một bất biến nghiệp vụ.
- Write skew xảy ra khi các giao dịch đọc cùng trạng thái rồi ghi vào các hàng khác nhau, khiến kết quả kết hợp không còn hợp lệ.
- Truy vấn không trả về hàng nào không có nghĩa là đã khóa một vị trí trống. Giao dịch khác vẫn có thể chèn hàng thỏa predicate.
- `UNIQUE` phù hợp với tính duy nhất; điều kiện khoảng thời gian, tổng sức chứa hoặc số lượng tối thiểu cần constraint hoặc cơ chế đồng bộ hóa biểu diễn đúng quy tắc.
- Serializable có thể ngăn hoặc phát hiện các phụ thuộc nguy hiểm; ứng dụng phải xử lý serialization failure bằng cách rollback và retry toàn bộ transaction khi phù hợp.
- Hàng guard hoặc hàng tổng hợp có thể tạo điểm ghi chung, nhưng mọi luồng cập nhật phải tuân theo cùng giao thức và phải được kiểm tra theo semantics của hệ quản trị.
- Không nên dựa vào một lần `SELECT` kiểm tra trước khi ghi để bảo đảm một điều kiện toàn cục trong môi trường có giao dịch đồng thời.
