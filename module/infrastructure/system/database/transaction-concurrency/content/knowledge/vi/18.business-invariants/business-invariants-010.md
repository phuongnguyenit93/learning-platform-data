# So sánh khóa, kiểm tra phiên bản, ràng buộc và SERIALIZABLE cho cùng bài toán

Khi nhiều transaction cùng thay đổi dữ liệu, một quy tắc nghiệp vụ có thể bị phá vỡ dù từng câu SQL riêng lẻ đều chạy thành công. Ví dụ, một phòng chỉ có sức chứa 10 người. Hai transaction cùng đọc tổng số chỗ đã đặt là 6, rồi mỗi transaction thêm 3 người. Nếu cả hai cùng commit, tổng mới là 12 và vượt sức chứa.

Có nhiều cách bảo vệ cùng một quy tắc: khóa bi quan để buộc transaction chờ nhau, khóa lạc quan để phát hiện phiên bản đã thay đổi, constraint để database từ chối trạng thái không hợp lệ, hoặc isolation level `SERIALIZABLE` để bảo đảm kết quả tương đương một thứ tự chạy tuần tự. Các cách này có thể kết hợp, nhưng chúng không có cùng phạm vi bảo vệ và không thay thế lẫn nhau trong mọi tình huống.

Bài học này dùng chung bài toán sức chứa phòng để so sánh bốn phương pháp. Sau đó, bài học mở rộng sang bất biến trên nhiều hàng, hướng dẫn chọn giải pháp và cách kiểm thử dưới tải đồng thời.

## 1. Bài toán chung: số chỗ đặt không được vượt sức chứa

Giả sử một phòng có sức chứa 10 người. Bảng `reservation` lưu các lượt đặt, mỗi lượt có thể gồm nhiều khách:

```sql
CREATE TABLE reservation (
    reservation_id BIGINT PRIMARY KEY,
    room_id        BIGINT NOT NULL,
    guest_count    INTEGER NOT NULL CHECK (guest_count > 0)
);
```

Ứng dụng cần bảo đảm với mỗi phòng:

```text
SUM(reservation.guest_count) <= room.capacity
```

Đây là bất biến nhiều hàng. Tổng số khách được tính từ nhiều reservation, còn sức chứa nằm ở hàng phòng. Hai transaction có thể chèn hai hàng reservation khác nhau nên không nhất thiết có xung đột ghi trực tiếp trên cùng một hàng.

### Lịch thực thi gây lỗi

Giả sử hiện tại phòng 7 đã có 6 chỗ được đặt, còn 4 chỗ trống. T1 muốn thêm 3 khách và T2 cũng muốn thêm 3 khách.

| Bước | Transaction T1 | Transaction T2 |
| --- | --- | --- |
| 1 | Đọc tổng: 6 | |
| 2 | | Đọc tổng: 6 |
| 3 | Kiểm tra 6 + 3 <= 10: đúng | |
| 4 | | Kiểm tra 6 + 3 <= 10: đúng |
| 5 | INSERT reservation 3 khách | |
| 6 | | INSERT reservation 3 khách |
| 7 | COMMIT | |
| 8 | | COMMIT |

Kết quả cuối là 6 + 3 + 3 = 12. Cả hai transaction đều kiểm tra hợp lệ trên dữ liệu mà chúng đọc, nhưng tổng hợp hai lần ghi làm sai bất biến.

Đây là ví dụ điển hình của write skew hoặc predicate anomaly dưới mức cô lập không đủ mạnh. Điểm cần giải quyết là làm sao để hai quyết định đặt chỗ không thể cùng dựa trên tổng cũ 6 rồi cùng được chấp nhận.

## 2. Phương pháp 1: khóa bi quan (pessimistic locking)

Khóa bi quan giả định có thể xảy ra xung đột và lấy khóa trước khi kiểm tra, sau đó mới thay đổi dữ liệu. Transaction khác cần khóa xung đột trên cùng tài nguyên phải chờ.

Một cách triển khai là khóa hàng đại diện cho phòng. Bảng `room` có thể lưu sức chứa:

```sql
CREATE TABLE room (
    room_id  BIGINT PRIMARY KEY,
    capacity INTEGER NOT NULL CHECK (capacity > 0)
);
```

Transaction đặt chỗ khóa hàng phòng bằng locking read:

```sql
BEGIN;

SELECT capacity
FROM room
WHERE room_id = 7
FOR UPDATE;

SELECT COALESCE(SUM(guest_count), 0) AS reserved
FROM reservation
WHERE room_id = 7;

-- Ứng dụng kiểm tra reserved + :new_guest_count <= capacity.

INSERT INTO reservation(reservation_id, room_id, guest_count)
VALUES (:reservation_id, 7, :new_guest_count);

COMMIT;
```

T1 khóa hàng `room_id = 7` trước khi tính tổng. T2 muốn đặt cùng phòng cũng phải khóa chính hàng đó, nên T2 chờ. Sau khi T1 commit, T2 mới lấy được khóa và kiểm tra tổng theo trạng thái đã được cập nhật, rồi quyết định có đủ chỗ hay không. Điều này đòi hỏi câu đọc tổng phải nhìn thấy dữ liệu mới theo semantics của engine. Chẳng hạn, PostgreSQL ở `READ COMMITTED` lấy snapshot mới cho từng statement. Với InnoDB ở `REPEATABLE READ`, consistent read dùng snapshot của transaction; nếu transaction đã tạo snapshot trước khi chờ guard, câu đọc tổng sau đó có thể vẫn thấy dữ liệu cũ. Vì vậy, hãy lấy guard trước mọi consistent read liên quan, hoặc dùng locking/current read hay isolation level phù hợp theo tài liệu engine. Chỉ lấy khóa guard không tự làm mới một snapshot cũ.

### Vì sao cần khóa hàng phòng thay vì chỉ khóa reservation hiện có?

Nếu truy vấn reservation hiện tại trả về một số hàng, khóa từng hàng đó không nhất thiết ngăn transaction khác chèn hàng mới thỏa điều kiện `room_id = 7`. Nếu chưa có reservation nào, không có hàng con nào để khóa. Hàng `room` là một tài nguyên luôn tồn tại, có thể đóng vai trò **guard row** để mọi transaction đặt chỗ cùng tranh chấp.

Quy tắc bắt buộc là mọi đường ghi có thể làm thay đổi tổng sức chứa của phòng đều phải khóa cùng hàng `room` trước khi đọc tổng và chèn, sửa hoặc xóa reservation. Nếu một API, batch job hoặc thao tác quản trị bỏ qua quy tắc này, khóa guard không còn bảo vệ được bất biến.

### Ưu điểm và chi phí

- **Ưu điểm:** cách suy luận trực tiếp; transaction sau đọc trạng thái sau khi transaction trước kết thúc; phù hợp khi xung đột thường xuyên hoặc việc retry tốn kém.
- **Chi phí:** transaction có thể phải chờ; nhiều lượt đặt cùng một phòng bị tuần tự hóa; giữ khóa lâu làm giảm throughput.
- **Rủi ro:** deadlock vẫn có thể xảy ra nếu transaction khóa nhiều tài nguyên theo thứ tự khác nhau. Cần thứ tự khóa thống nhất và transaction ngắn.

### Khi nào dùng?

Chọn khóa bi quan khi tài nguyên nóng, xung đột thường xuyên, hoặc ứng dụng cần kiểm tra dữ liệu sau khi đã giành quyền độc quyền. Mẫu guard row phù hợp khi có một hàng cha đại diện rõ ràng cho nhóm dữ liệu, chẳng hạn phòng, tài khoản, kho hoặc dự án.

Lưu ý: cú pháp `FOR UPDATE` và hành vi snapshot sau khi chờ khác nhau giữa các hệ quản trị. Ví dụ trên là mẫu cho các engine hỗ trợ locking read. Khi dùng SQL Server cần table hints phù hợp; SQLite không có row-level `FOR UPDATE` và thường phải điều phối writer bằng transaction mode riêng. Luôn kiểm tra hành vi của engine đang triển khai.

## 3. Phương pháp 2: khóa lạc quan (optimistic version check)

Khóa lạc quan không giữ khóa trong lúc ứng dụng đọc và tính toán. Thay vào đó, nó dùng cột `version` để phát hiện một transaction khác đã thay đổi tài nguyên kể từ lần đọc trước.

Để bảo vệ bất biến sức chứa, có thể thêm bộ đếm đã đặt và version vào hàng phòng:

```sql
CREATE TABLE room_capacity (
    room_id        BIGINT PRIMARY KEY,
    capacity       INTEGER NOT NULL,
    reserved_count INTEGER NOT NULL DEFAULT 0,
    version        BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT ck_room_capacity
        CHECK (capacity > 0 AND reserved_count >= 0
               AND reserved_count <= capacity)
);
```

Khi đọc phòng, ứng dụng nhận `reserved_count` và `version`. Khi muốn thêm 3 khách, ứng dụng cập nhật có điều kiện:

```sql
UPDATE room_capacity
SET reserved_count = reserved_count + 3,
    version = version + 1
WHERE room_id = 7
  AND version = :expected_version
  AND reserved_count + 3 <= capacity;
```

Nếu câu lệnh cập nhật đúng một hàng, ứng dụng có thể chèn reservation trong cùng transaction. Nếu cập nhật 0 hàng, version đã thay đổi, phòng không tồn tại hoặc không còn đủ chỗ; transaction cần rollback hoặc xử lý kết quả phù hợp.

### Cách phương pháp này ngăn hai lần đặt cùng dùng một phiên bản

Giả sử T1 và T2 cùng đọc `reserved_count = 6`, `version = 12`:

| Bước | Transaction T1 | Transaction T2 |
| --- | --- | --- |
| 1 | Đọc bộ đếm 6, version 12 | |
| 2 | | Đọc bộ đếm 6, version 12 |
| 3 | UPDATE với version 12, tăng bộ đếm lên 9 và version lên 13 | |
| 4 | | UPDATE với version 12, phải chờ hoặc gặp xung đột ghi |
| 5 | COMMIT | |
| 6 | | Điều kiện version 12 không còn hợp lệ hoặc transaction bị báo xung đột |

Chỉ một transaction có thể chuyển hàng guard từ version 12 sang phiên bản mới. Transaction còn lại phải đọc lại trạng thái mới và tính lại. Cả thay đổi bộ đếm lẫn hàng reservation phải nằm trong cùng transaction để nếu INSERT thất bại, bộ đếm cũng được rollback.

### Ưu điểm và chi phí

- **Ưu điểm:** không giữ khóa lâu trong lúc ứng dụng tính toán; phát hiện stale update rõ ràng; phù hợp với dữ liệu ít xung đột và ORM có hỗ trợ version.
- **Chi phí:** transaction có thể thất bại ở bước ghi và phải retry; khi xung đột thường xuyên, chi phí thử lại có thể lớn.
- **Rủi ro:** version của từng hàng chi tiết không bảo vệ bất biến nhiều hàng. Phải tạo một version chung trên hàng guard hoặc hàng tổng hợp mà mọi transaction liên quan cùng cập nhật.

### Điều kiện để optimistic guard có hiệu lực

1. Mọi transaction ảnh hưởng đến sức chứa phòng 7 đều cập nhật cùng hàng `room_capacity`.
2. Câu UPDATE kiểm tra `version` cũ trong `WHERE` và tăng version trong cùng câu lệnh.
3. Ứng dụng kiểm tra số hàng được cập nhật.
4. Cập nhật bộ đếm và chèn/xóa reservation nằm trong cùng transaction.
5. Nếu version không khớp hoặc có serialization/write conflict, rollback toàn bộ và đọc lại trạng thái mới trước khi thử lại.

Với isolation level dựa trên snapshot, hai transaction cùng sửa hàng guard thường tạo write-write conflict; một transaction có thể bị từ chối thay vì chỉ nhận số hàng cập nhật bằng 0. Cần xử lý cả hai kiểu kết quả theo engine và driver. Không được giả định mọi hệ quản trị sẽ báo lỗi theo cùng cách.

### Khi nào dùng?

Chọn optimistic version khi xung đột hiếm, thời gian tính toán ngoài database tương đối dài hoặc ứng dụng có thể tính lại dễ dàng. Nếu mọi lần đặt phòng đều cạnh tranh trên một hàng bộ đếm rất nóng, khóa bi quan hoặc cập nhật nguyên tử có thể hiệu quả hơn.

## 4. Phương pháp 3: constraint ở cơ sở dữ liệu

Constraint diễn đạt những trạng thái dữ liệu mà database không được phép lưu. Nó có ưu điểm là bảo vệ mọi đường ghi, kể cả khi một ứng dụng quên kiểm tra đầu vào.

Trong ví dụ, constraint:

```sql
CHECK (reserved_count >= 0 AND reserved_count <= capacity)
```

bảo đảm hàng `room_capacity` không có bộ đếm âm hoặc vượt sức chứa. Tuy nhiên, nó chỉ kiểm tra các cột trên **một hàng**. Nó không tự tính tổng các hàng trong `reservation`.

### Constraint bảo vệ được gì?

- `PRIMARY KEY` bảo đảm mỗi phòng hoặc reservation có định danh duy nhất.
- `NOT NULL` bảo đảm các trường bắt buộc như `room_id`, `guest_count` và `capacity` không bị bỏ trống.
- `CHECK (guest_count > 0)` bảo đảm mỗi reservation có số khách dương.
- `CHECK (reserved_count <= capacity)` bảo đảm bộ đếm trên hàng phòng không vượt giới hạn.
- `UNIQUE` có thể bảo vệ một khóa nghiệp vụ, chẳng hạn một chỗ ngồi cụ thể chỉ được gán cho một reservation.
- Foreign key bảo đảm reservation tham chiếu đến phòng tồn tại.

Ví dụ schema có thêm khóa ngoại và các constraint hàng:

```sql
CREATE TABLE room (
    room_id  BIGINT PRIMARY KEY,
    capacity INTEGER NOT NULL CHECK (capacity > 0)
);

CREATE TABLE reservation (
    reservation_id BIGINT PRIMARY KEY,
    room_id        BIGINT NOT NULL,
    guest_count    INTEGER NOT NULL CHECK (guest_count > 0),
    FOREIGN KEY (room_id) REFERENCES room(room_id)
);
```

Những constraint này rất hữu ích, nhưng vẫn chưa diễn đạt được:

```text
Tổng guest_count của tất cả reservation thuộc cùng room_id
phải nhỏ hơn hoặc bằng room.capacity.
```

Một `CHECK` thông thường không phải cơ chế an toàn để truy vấn `SUM` trên các hàng khác. Không nên giả định trigger tính tổng cũng tự an toàn dưới concurrency; trigger cần cơ chế khóa hoặc isolation phù hợp để tránh hai transaction cùng tính trên snapshot cũ.

### Kết hợp constraint với hàng tổng hợp

Một thiết kế phổ biến là duy trì `reserved_count` trên hàng phòng và cập nhật nó trong cùng transaction với các hàng reservation. Khi đó:

- Câu UPDATE có điều kiện kiểm tra còn đủ chỗ.
- Database điều phối các cập nhật đồng thời trên cùng hàng `room_capacity`.
- CHECK bảo vệ miền giá trị của bộ đếm.
- Transaction bảo đảm bộ đếm và các hàng reservation cùng commit hoặc cùng rollback.

Ví dụ:

```sql
BEGIN;

UPDATE room_capacity
SET reserved_count = reserved_count + :guests,
    version = version + 1
WHERE room_id = :room_id
  AND reserved_count + :guests <= capacity;

-- Nếu không cập nhật đúng một hàng: ROLLBACK.

INSERT INTO reservation(reservation_id, room_id, guest_count)
VALUES (:reservation_id, :room_id, :guests);

COMMIT;
```

Mẫu này cần mọi luồng hủy hoặc sửa reservation cập nhật bộ đếm theo cùng quy tắc. Cần có cơ chế đối soát để phát hiện bộ đếm bị lệch so với tổng chi tiết do lỗi ứng dụng hoặc dữ liệu cũ.

### Constraint cho khóa duy nhất và khoảng thời gian

Với bài toán khác, constraint có thể giải quyết trực tiếp bất biến:

- Email không được trùng: `UNIQUE(email)`.
- Mỗi sinh viên chỉ đăng ký một lần vào một lớp: `UNIQUE(course_id, student_id)`.
- Một chỗ ngồi chỉ có một người giữ: `UNIQUE(room_id, seat_no)`.
- Các khoảng thời gian không được giao nhau: dùng exclusion constraint hoặc cơ chế tương đương nếu hệ quản trị hỗ trợ.

Constraint thường là lựa chọn mạnh nhất khi quy tắc có thể biểu diễn trực tiếp. Nó không phụ thuộc vào việc mọi service có nhớ gọi cùng một helper hay không. Nhưng không phải mọi bất biến nhiều hàng đều có dạng unique key hoặc biểu thức trên một hàng.

### Ưu điểm và giới hạn

- **Ưu điểm:** database là nơi thực thi quy tắc; bảo vệ dữ liệu từ nhiều ứng dụng; lỗi vi phạm được phát hiện ngay tại nơi ghi.
- **Giới hạn:** CHECK chủ yếu bảo vệ hàng hiện tại; không thể dùng một CHECK đơn giản để bảo vệ tổng nhiều hàng; constraint không thay thế transaction khi nhiều bảng cần cập nhật nguyên tử.
- **Chi phí:** thêm constraint có thể cần migration và xác minh dữ liệu cũ; unique index có thể tạo chờ khi nhiều transaction chèn cùng giá trị.

## 5. Phương pháp 4: SERIALIZABLE

`SERIALIZABLE` là mức cô lập yêu cầu kết quả của các transaction đồng thời phải tương đương với một thứ tự chạy tuần tự nào đó. Đây là lựa chọn tổng quát khi bất biến phụ thuộc vào tập hàng hoặc predicate mà khó biểu diễn bằng một constraint đơn giản.

Với bài toán sức chứa, T1 và T2 đều đọc:

```sql
SELECT COALESCE(SUM(guest_count), 0)
FROM reservation
WHERE room_id = 7;
```

Sau đó mỗi transaction chèn thêm 3 khách. Ở mức Serializable, hệ quản trị phải ngăn hoặc phát hiện phụ thuộc khiến cả hai cùng commit và làm tổng vượt 10. Tùy engine, transaction thứ hai có thể phải chờ, bị từ chối khi ghi hoặc nhận serialization failure tại commit.

Ví dụ khái quát:

```sql
-- Cú pháp SET TRANSACTION cụ thể tùy hệ quản trị.
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COALESCE(SUM(guest_count), 0)
FROM reservation
WHERE room_id = 7;

-- Ứng dụng kiểm tra tổng + số khách mới <= capacity.
INSERT INTO reservation(reservation_id, room_id, guest_count)
VALUES (:reservation_id, 7, :new_guest_count);

COMMIT;
```

Đây là ví dụ về logic cần thực hiện ở Serializable; vị trí và cú pháp khai báo isolation level phải theo driver và hệ quản trị. Một số engine dùng khóa phạm vi/predicate; một số engine dùng MVCC và theo dõi phụ thuộc, sau đó hủy transaction nếu phát hiện lịch không tuần tự hóa được.

### Serialization failure là kết quả hợp lệ

Serializable không có nghĩa mọi transaction đều chắc chắn commit. Khi hai transaction xung đột, database có thể hủy một transaction để giữ bảo đảm tuần tự hóa. Ứng dụng phải:

1. Nhận diện lỗi serialization theo mã lỗi của engine/driver.
2. Rollback transaction thất bại.
3. Bắt đầu transaction mới với snapshot mới.
4. Đọc lại tổng số chỗ và tính lại quyết định nghiệp vụ.
5. Thử lại toàn bộ transaction với số lần giới hạn.

Không chỉ chạy lại câu INSERT cuối cùng. Quyết định chèn đã dựa trên tổng số chỗ đọc từ snapshot cũ; cần đọc và tính lại toàn bộ đơn vị công việc.

### Ưu điểm và chi phí

- **Ưu điểm:** bảo vệ các phụ thuộc phức tạp trên nhiều hàng; giảm nhu cầu tự thiết kế guard cho từng predicate; mô hình đúng đắn dễ diễn đạt.
- **Chi phí:** transaction có thể bị hủy và cần retry; hiệu năng phụ thuộc mức tranh chấp, engine và execution plan; cần theo dõi serialization failure.
- **Rủi ro:** nếu ứng dụng không retry đúng cách, người dùng có thể thấy lỗi tạm thời; nếu thao tác có tác dụng phụ bên ngoài database, retry cần idempotency.

### Khi nào dùng?

Chọn Serializable khi bất biến phụ thuộc vào tập dữ liệu, nhiều luồng ghi phức tạp hoặc không thể bảo đảm mọi đường ghi đều tuân thủ cùng một guard. Đây là lựa chọn rõ ràng về mặt semantics, nhưng cần đo hiệu năng và thiết kế retry ngay từ đầu.

## 6. So sánh bốn phương pháp trên cùng bài toán

| Tiêu chí | Khóa bi quan | Khóa lạc quan | Constraint | SERIALIZABLE |
| --- | --- | --- | --- | --- |
| Cách ngăn lỗi | Khóa guard trước khi đọc và ghi | So sánh version chung khi cập nhật | Từ chối trạng thái vi phạm | Ngăn hoặc phát hiện lịch không tuần tự hóa |
| Thời điểm phát hiện/chặn | Trước hoặc trong lúc lấy khóa | Tại thao tác UPDATE/CAS | Khi kiểm tra constraint | Trong lúc thực thi hoặc tại commit |
| Có thể phải chờ? | Có | Có thể chờ trên write conflict | Có thể chờ khi tranh chấp unique/index | Có thể chờ, tùy engine |
| Có thể phải retry? | Khi deadlock/timeout | Khi version conflict | Khi unique conflict tùy nghiệp vụ | Khi serialization failure |
| Bảo vệ nhiều hàng? | Có nếu khóa đúng guard/range và mọi luồng tuân thủ | Có nếu mọi luồng cập nhật cùng version guard | Chỉ khi quy tắc biểu diễn được bằng constraint phù hợp hoặc dữ liệu được mô hình hóa lại | Có, theo semantics Serializable |
| Điểm mạnh | Điều phối rõ ràng trước khi quyết định | Không giữ khóa dài trong lúc tính toán | Bảo vệ dữ liệu tại database | Tổng quát cho phụ thuộc và predicate |
| Điểm yếu | Lock wait, deadlock, contention | Conflict/retry; cần guard chung cho bất biến nhiều hàng | CHECK không bảo vệ tổng nhiều hàng | Retry và chi phí concurrency tùy workload |

Không có một phương pháp thắng trong mọi trường hợp. Có thể dùng nhiều lớp: `CHECK` để bảo vệ bộ đếm, optimistic version hoặc khóa bi quan để điều phối cập nhật bộ đếm, và Serializable cho các nghiệp vụ khác có predicate phức tạp.

## 7. Chọn phương pháp theo bản chất bất biến

Trước khi chọn cơ chế, hãy xác định bất biến nằm ở phạm vi nào:

### Bất biến chỉ phụ thuộc một hàng

Ví dụ `quantity >= 0`, `start_time < end_time` hoặc `amount > 0`.

- Dùng `NOT NULL` nếu giá trị bắt buộc phải hiện diện.
- Dùng `CHECK` cho biểu thức trên hàng.
- Dùng câu UPDATE có điều kiện để kiểm tra và thay đổi nguyên tử.
- Có thể bổ sung version nếu nhiều người cùng sửa một hàng và cần phát hiện stale update.

Ví dụ:

```sql
UPDATE inventory
SET quantity = quantity - :requested
WHERE product_id = :product_id
  AND quantity >= :requested;
```

Kết hợp với `CHECK (quantity >= 0)` để bảo vệ trạng thái cuối từ mọi đường ghi.

### Bất biến là tính duy nhất

Ví dụ email, mã đơn hàng hoặc cặp `(course_id, student_id)` phải duy nhất.

- Dùng `PRIMARY KEY` hoặc `UNIQUE`.
- Không dựa vào `SELECT` trước INSERT để bảo vệ tính duy nhất.
- Xử lý duplicate/unique violation như một kết quả cạnh tranh bình thường.

### Bất biến phụ thuộc vào tổng hoặc số lượng nhiều hàng

Ví dụ tổng đặt chỗ không vượt sức chứa, luôn có ít nhất một người trực hoặc ngân sách phân bổ không vượt giới hạn.

- Dùng guard row hoặc hàng tổng hợp với khóa bi quan nếu xung đột thường xuyên.
- Dùng version chung nếu xung đột hiếm và có thể retry.
- Dùng Serializable nếu predicate phức tạp hoặc nhiều đường ghi khó điều phối.
- Kết hợp CHECK trên hàng tổng hợp để bảo vệ giới hạn của chính hàng đó.

### Bất biến liên quan đến khoảng hoặc predicate

Ví dụ hai lịch đặt không được giao nhau hoặc không có hàng nào được chèn vào một khoảng đã khóa.

- Ưu tiên exclusion constraint nếu engine hỗ trợ.
- Nếu dùng range/key-range lock, kiểm tra index và isolation level.
- Nếu không thể biểu diễn bằng constraint hoặc khóa phạm vi đáng tin cậy, cân nhắc Serializable.

## 8. Có thể kết hợp các phương pháp như thế nào?

Trong hệ thống thực tế, các phương pháp thường bổ sung cho nhau.

### Constraint + khóa bi quan

Guard row được khóa trước khi đọc tổng. `CHECK` bảo vệ bộ đếm không vượt sức chứa. Transaction chèn reservation và cập nhật bộ đếm trong cùng transaction. Khóa điều phối các lượt đặt; constraint bảo vệ trạng thái của hàng tổng hợp nếu một luồng code mắc lỗi.

### Constraint + khóa lạc quan

Hàng tổng hợp có `version` và `CHECK`. Mỗi transaction cập nhật bằng điều kiện version cũ và điều kiện còn đủ chỗ. Nếu update không tác động hàng nào, rollback. Constraint vẫn bảo vệ miền giá trị khi có một đường ghi khác.

### Serializable + constraint

Serializable bảo vệ quan hệ giữa nhiều hàng. Constraint bảo vệ các điều kiện cục bộ như `guest_count > 0`, khóa chính và khóa ngoại. Khi transaction bị serialization failure, ứng dụng retry toàn bộ transaction; khi dữ liệu vi phạm constraint, ứng dụng xử lý lỗi nghiệp vụ tương ứng.

### Pessimistic lock + Serializable

Có thể dùng khóa tường minh trên tài nguyên nóng để giảm cạnh tranh, trong khi Serializable bảo vệ các predicate phức tạp khác. Tuy nhiên, khóa tường minh không thay thế việc hiểu semantics Serializable; cũng cần tránh khóa dư thừa làm tăng contention.

## 9. Các lỗi thiết kế thường gặp

### Chỉ kiểm tra tổng bằng SELECT rồi INSERT

Hai transaction có thể cùng đọc một tổng cũ và cùng chèn. Kiểm tra trước khi ghi không tự đồng bộ hóa quyết định.

### Chỉ khóa những hàng con đang tồn tại

Nếu truy vấn không tìm thấy hàng, không có row lock nào trên một hàng tương lai. Nếu quy tắc liên quan đến hàng mới, cần khóa guard, range/predicate lock, constraint hoặc Serializable.

### Thêm version vào từng reservation nhưng không có version chung

Hai transaction chèn hai hàng khác nhau hoặc cập nhật hai hàng khác nhau sẽ không đụng version của nhau. Version từng hàng không phát hiện write skew trên tổng.

### Nghĩ rằng CHECK có thể tính tổng các hàng khác

CHECK thường kiểm tra biểu thức của hàng đang ghi. Nó không phải cơ chế an toàn để tính `SUM` trên cả bảng dưới concurrency. Hãy lưu bộ đếm có điều phối hoặc dùng Serializable.

### Dùng guard nhưng có luồng ghi bỏ qua guard

Một batch job hoặc service khác có thể phá vỡ bất biến nếu không cập nhật cùng hàng guard. Quy tắc phải được áp dụng cho mọi đường ghi.

### Retry sai phạm vi

Khi optimistic conflict hoặc serialization failure xảy ra, cần rollback và chạy lại toàn bộ transaction có quyết định phụ thuộc dữ liệu cũ. Không chỉ retry statement cuối.

### Quên kiểm tra số hàng được cập nhật

Với CAS hoặc UPDATE có điều kiện, số hàng cập nhật bằng 0 có thể biểu thị xung đột hoặc điều kiện nghiệp vụ không còn đúng. Nếu ứng dụng bỏ qua kết quả này, các bước tiếp theo có thể tạo dữ liệu không nhất quán.

## 10. Quy trình ra quyết định

Có thể dùng trình tự sau khi thiết kế một transaction:

1. Viết bất biến thành biểu thức rõ ràng. Ví dụ `reserved_count <= capacity` hoặc `COUNT(on_call = TRUE) >= 1`.
2. Xác định phạm vi: một hàng, khóa duy nhất, nhiều hàng, hay predicate/khoảng dữ liệu.
3. Nếu là điều kiện trên một hàng, ưu tiên `NOT NULL`, `CHECK` và UPDATE có điều kiện.
4. Nếu là tính duy nhất, dùng PRIMARY KEY hoặc UNIQUE.
5. Nếu là nhiều hàng nhưng có một tài nguyên đại diện ổn định, cân nhắc guard row hoặc hàng tổng hợp.
6. Chọn khóa bi quan khi xung đột thường xuyên; chọn version lạc quan khi xung đột hiếm và retry rẻ.
7. Chọn Serializable khi cần bảo vệ predicate phức tạp hoặc khó bảo đảm mọi luồng ghi cùng tuân thủ guard.
8. Thiết kế xử lý lỗi: deadlock, lock timeout, optimistic conflict, unique violation và serialization failure.
9. Kiểm thử với nhiều connection và lịch xen kẽ có kiểm soát.
10. Theo dõi lock wait, retry rate, serialization failure và constraint violation sau khi triển khai.

## 11. Kiểm thử cùng một bất biến bằng bốn cách

Để so sánh công bằng, hãy giữ nguyên dữ liệu ban đầu và cùng một lịch hai transaction đặt thêm 3 khách khi đã có 6/10 chỗ.

### Kiểm thử khóa bi quan

1. T1 khóa hàng guard của phòng 7.
2. T2 yêu cầu cùng khóa và phải chờ.
3. T1 đọc tổng 6, thêm 3, cập nhật dữ liệu và commit.
4. T2 lấy được khóa, đọc tổng mới 9.
5. T2 kiểm tra 9 + 3 > 10 và từ chối đặt.

Kết quả mong muốn: chỉ T1 thành công; T2 không thể quyết định dựa trên tổng cũ.

### Kiểm thử version lạc quan

1. T1 và T2 cùng đọc hàng tổng hợp với version 12.
2. T1 CAS version 12 thành 13, tăng bộ đếm lên 9 và commit.
3. T2 thử CAS với version 12.
4. T2 nhận xung đột hoặc cập nhật 0 hàng.
5. T2 rollback, đọc lại bộ đếm 9 và từ chối thêm 3.

Kết quả mong muốn: chỉ một transaction có thể cập nhật version cũ.

### Kiểm thử constraint

1. Cập nhật bộ đếm bằng câu lệnh nguyên tử có điều kiện.
2. Thử một câu lệnh khác cố đặt `reserved_count = 11`.
3. Xác nhận CHECK từ chối giá trị 11.
4. Thử hai transaction đồng thời cập nhật cùng hàng bộ đếm và kiểm tra một transaction không thể làm bộ đếm vượt capacity.

Kết quả mong muốn: CHECK bảo vệ hàng tổng hợp; việc điều phối đồng thời đến từ xung đột cập nhật cùng hàng và điều kiện UPDATE.

### Kiểm thử Serializable

1. T1 và T2 cùng bắt đầu Serializable.
2. Cả hai đọc tổng 6 từ predicate reservation của phòng 7.
3. Cả hai thử chèn thêm 3 khách.
4. Commit theo lịch xen kẽ.
5. Xác nhận database chặn hoặc hủy ít nhất một transaction do xung đột tuần tự hóa.
6. Retry transaction bị hủy bằng snapshot mới; lần kiểm tra lại thấy tổng 9 và từ chối.

Kết quả mong muốn: không có lịch commit cuối cùng nào làm tổng vượt 10.

Kiểm thử cần chạy trên hệ quản trị và isolation level thật. Các engine có cách khóa, phát hiện phụ thuộc và thời điểm báo lỗi khác nhau; một bài test chạy tuần tự không thể chứng minh hành vi đồng thời.

## 12. Những điểm cần ghi nhớ

- Khóa bi quan lấy khóa trước khi kiểm tra và buộc transaction xung đột chờ; phù hợp khi xung đột thường xuyên hoặc cần tuần tự hóa một tài nguyên guard.
- Khóa lạc quan dùng version chung để phát hiện dữ liệu đã thay đổi; phù hợp khi xung đột hiếm và có thể retry toàn bộ transaction.
- Version trên từng hàng không bảo vệ bất biến nhiều hàng nếu các transaction sửa những hàng khác nhau. Cần một version guard chung hoặc cơ chế khác.
- PRIMARY KEY, UNIQUE, NOT NULL và CHECK bảo vệ các quy tắc mà database có thể biểu diễn; CHECK thông thường không tự kiểm tra tổng trên nhiều hàng.
- Hàng tổng hợp kết hợp UPDATE có điều kiện và CHECK có thể biến một bất biến tổng thành một điểm ghi chung, nhưng mọi luồng ghi phải duy trì bộ đếm trong cùng transaction.
- SERIALIZABLE bảo vệ các phụ thuộc trên nhiều hàng và predicate theo ngữ nghĩa tuần tự hóa; ứng dụng phải xử lý serialization failure bằng cách rollback và retry toàn bộ transaction.
- Có thể kết hợp constraint với khóa bi quan, khóa lạc quan hoặc Serializable để tạo nhiều lớp bảo vệ.
- Chọn phương pháp theo phạm vi bất biến, mức tranh chấp, khả năng retry, semantics của hệ quản trị và chi phí vận hành.
