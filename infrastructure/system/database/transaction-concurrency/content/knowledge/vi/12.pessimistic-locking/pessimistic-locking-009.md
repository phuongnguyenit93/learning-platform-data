# Giới hạn của khóa hàng khi hàng cần bảo vệ chưa tồn tại

Khóa hàng là cách phổ biến để bảo vệ một bản ghi trong lúc giao dịch đọc rồi cập nhật nó. Tuy nhiên, có một giới hạn quan trọng: **nếu hàng cần bảo vệ chưa tồn tại, truy vấn tìm hàng đó có thể không khóa được hàng nào**. Một giao dịch có thể kiểm tra thấy “chưa có dữ liệu”, trong khi giao dịch khác cũng kiểm tra cùng lúc và cùng quyết định chèn. Cả hai cùng hành động dựa trên trạng thái rỗng mà không có cơ chế bảo vệ khoảng dữ liệu hoặc điều kiện truy vấn.

Đây là một dạng race condition thường gặp trong thao tác “kiểm tra rồi tạo” (*check-then-insert*). Để xử lý đúng, cần phân biệt khóa hàng hiện hữu với khóa khoảng/predicate, và chọn cơ chế phù hợp như constraint duy nhất, khóa hàng điều phối đã tồn tại, advisory lock hoặc isolation level có khả năng bảo vệ predicate.

## 1. Khóa hàng chỉ bảo vệ được hàng mà hệ thống có thể khóa

Giả sử ứng dụng cần tạo một lượt đặt phòng nếu chưa có lượt đặt nào cho phòng 5 vào ngày 20 tháng 11.

Một cách triển khai thường thấy là:

~~~sql
BEGIN;

SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date = DATE '2026-11-20'
FOR UPDATE;

-- Nếu không có hàng, tạo lượt đặt mới.
INSERT INTO room_booking (room_id, booking_date, customer_id)
VALUES (5, DATE '2026-11-20', 101);

COMMIT;
~~~

FOR UPDATE yêu cầu khóa các hàng được truy vấn tìm thấy. Nếu truy vấn trả về một hàng hiện hữu, hệ quản trị có thể khóa hàng hoặc tài nguyên chỉ mục tương ứng theo cơ chế của engine. Nhưng nếu truy vấn trả về **không có hàng nào**, không có tuple hiện hữu để khóa theo cách khóa hàng thông thường.

Hai transaction có thể chạy như sau:

| Thứ tự | T1 | T2 |
|---|---|---|
| 1 | Tìm lượt đặt phòng 5 ngày 20/11, không có kết quả | |
| 2 | | Tìm cùng điều kiện, cũng không có kết quả |
| 3 | Chèn lượt đặt của khách 101 | |
| 4 | | Chèn lượt đặt của khách 202 |
| 5 | Commit | |
| 6 | | Commit |

Nếu không có constraint hoặc cơ chế bảo vệ phạm vi phù hợp, cả hai hàng có thể được chèn. Quy tắc “mỗi phòng chỉ có một lượt đặt cho ngày đó” bị vi phạm dù cả hai transaction đều đã dùng FOR UPDATE.

Vấn đề nằm ở đối tượng cần bảo vệ. Khi hàng chưa tồn tại, ứng dụng thực ra muốn bảo vệ **điều kiện không có hàng nào thỏa predicate**, chứ không phải bảo vệ một hàng cụ thể.

## 2. Phân biệt khóa hàng, khóa khoảng và khóa predicate

Ba khái niệm sau có liên quan nhưng không giống nhau:

- **Row/record lock:** khóa một hàng hoặc bản ghi chỉ mục hiện hữu. Nó ngăn thao tác xung đột trên chính bản ghi đó.
- **Gap/key-range lock:** khóa khoảng giữa các khóa chỉ mục hoặc một phạm vi khóa. Nó có thể ngăn transaction khác chèn khóa mới vào khoảng đang được bảo vệ.
- **Predicate lock:** biểu diễn điều kiện logic mà transaction đã đọc, ví dụ room_id = 5 AND booking_date = ngày X. Cơ chế này bảo vệ ý nghĩa của truy vấn theo tập dữ liệu, kể cả khi hiện tại không có hàng nào thỏa điều kiện.

Không phải hệ quản trị nào cũng triển khai ba loại này theo cùng một cách. Có engine dùng khóa khoảng để chặn thao tác chèn. Có engine theo dõi phụ thuộc đọc–ghi rồi hủy transaction nếu lịch chạy không thể tuần tự hóa. Cũng có cơ chế dùng khóa tường minh trên một tài nguyên logic đã tồn tại.

Điều cần nhớ là: **khóa một hàng hiện hữu không tự động tương đương với bảo vệ mọi hàng có thể xuất hiện trong tương lai để thỏa một điều kiện truy vấn**.

## 3. Hành vi khác nhau giữa các hệ quản trị

### 3.1. PostgreSQL: khóa hàng không khóa vị trí của hàng chưa tồn tại

Trong PostgreSQL, SELECT ... FOR UPDATE khóa các hàng được trả về. Nếu truy vấn không tìm thấy hàng, không có row lock nào được đặt trên một hàng tương lai có thể được chèn vào.

Ví dụ:

~~~sql
BEGIN;

SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date = DATE '2026-11-20'
FOR UPDATE;

-- Nếu kết quả rỗng, câu lệnh không khóa một hàng "trống".
COMMIT;
~~~

Một transaction khác vẫn có thể chèn hàng thỏa điều kiện đó, trừ khi một cơ chế khác ngăn việc chèn.

Ở mức SERIALIZABLE, PostgreSQL dùng **Serializable Snapshot Isolation (SSI)**. Hệ thống theo dõi các lần đọc predicate bằng predicate lock dạng SIREAD. Đây là thông tin để phát hiện phụ thuộc đọc–ghi, không phải khóa chặn transaction khác chèn ngay lập tức. Nếu các phụ thuộc tạo ra lịch không thể tuần tự hóa, PostgreSQL có thể hủy một transaction với lỗi serialization failure.

Điều này có nghĩa:

- FOR UPDATE ở READ COMMITTED không bảo vệ một hàng chưa tồn tại.
- SERIALIZABLE có thể bảo vệ tính đúng đắn của predicate bằng cách phát hiện xung đột và hủy transaction.
- Ứng dụng phải xử lý và retry toàn bộ transaction khi gặp serialization failure.

### 3.2. MySQL InnoDB: gap lock và next-key lock

InnoDB có cơ chế **gap lock** và **next-key lock** để bảo vệ phạm vi chỉ mục.

- Gap lock khóa khoảng giữa các bản ghi chỉ mục, hạn chế transaction khác chèn khóa mới vào khoảng đó.
- Next-key lock kết hợp khóa bản ghi chỉ mục với khóa khoảng ngay trước bản ghi đó.
- Các khóa này thường xuất hiện khi locking read hoặc thao tác tìm kiếm/quét phạm vi ở REPEATABLE READ.

Ví dụ:

~~~sql
START TRANSACTION;

SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date = '2026-11-20'
FOR UPDATE;

-- Tùy chỉ mục và access path, InnoDB có thể bảo vệ
-- phạm vi chỉ mục chứa vị trí của khóa chưa tồn tại.

COMMIT;
~~~

Tuy nhiên, không nên suy luận rằng mọi câu FOR UPDATE đều khóa chính xác khoảng cần thiết. Phạm vi khóa phụ thuộc vào:

- Isolation level.
- Chỉ mục được dùng để tìm kiếm.
- Điều kiện tìm kiếm là phép so sánh bằng trên unique index hay là truy vấn phạm vi.
- Kế hoạch truy cập và các hàng thực tế được quét.

Ở READ COMMITTED, InnoDB thường tắt gap locking cho tìm kiếm và quét chỉ mục thông thường, ngoại trừ một số trường hợp như kiểm tra khóa ngoại và duplicate-key. Vì vậy, cùng một câu truy vấn có thể có khả năng bảo vệ khác nhau khi thay đổi isolation level.

Khi cần dựa vào gap/next-key lock, phải kiểm tra chỉ mục và hành vi thực tế của phiên bản InnoDB đang chạy. Một truy vấn thiếu chỉ mục phù hợp có thể khóa phạm vi rộng hơn mong muốn và làm giảm khả năng chạy đồng thời.

### 3.3. SQL Server: key-range lock ở SERIALIZABLE

SQL Server có thể dùng **key-range lock** ở isolation level SERIALIZABLE để bảo vệ phạm vi chỉ mục được truy vấn đọc. Khóa phạm vi ngăn transaction khác chèn một khóa mới thỏa predicate cho đến khi transaction đang giữ khóa kết thúc.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT BookingId
FROM dbo.RoomBooking
WHERE RoomId = 5
  AND BookingDate = '2026-11-20';

-- Nếu không có hàng, phạm vi chỉ mục vẫn có thể được khóa.
-- Transaction khác không thể chèn khóa thỏa predicate
-- cho đến khi transaction này kết thúc.

COMMIT TRANSACTION;
~~~

Có thể dùng table hint HOLDLOCK để yêu cầu ngữ nghĩa tương đương SERIALIZABLE cho tham chiếu bảng đó. Ví dụ kết hợp UPDLOCK và HOLDLOCK khi muốn khóa phạm vi phục vụ thao tác đọc rồi ghi:

~~~sql
BEGIN TRANSACTION;

SELECT BookingId
FROM dbo.RoomBooking WITH (UPDLOCK, HOLDLOCK)
WHERE RoomId = 5
  AND BookingDate = '2026-11-20';

-- Kiểm tra kết quả và INSERT nếu chưa tồn tại.

COMMIT TRANSACTION;
~~~

UPDLOCK đơn lẻ không nên được xem là bảo đảm đầy đủ cho predicate rỗng. HOLDLOCK hoặc isolation level SERIALIZABLE mới thể hiện yêu cầu giữ bảo vệ phạm vi đến cuối transaction. Hiệu quả và độ rộng của khóa còn phụ thuộc chỉ mục và execution plan; nếu không có chỉ mục phù hợp, hệ thống có thể phải dùng phạm vi khóa rộng hoặc khóa nhiều tài nguyên hơn dự kiến.

## 4. Constraint duy nhất: lựa chọn tốt nhất cho điều kiện không trùng khóa

Nếu quy tắc nghiệp vụ có thể diễn đạt thành “mỗi tổ hợp khóa chỉ được có một hàng”, hãy để database bảo vệ bằng UNIQUE constraint hoặc unique index.

Ví dụ:

~~~sql
ALTER TABLE room_booking
ADD CONSTRAINT uq_room_booking_day
UNIQUE (room_id, booking_date);
~~~

Khi đó, cả T1 và T2 có thể cùng kiểm tra thấy chưa có lượt đặt. Nhưng lúc chèn, hệ quản trị sẽ điều phối các thao tác cạnh tranh trên unique key. Chỉ một hàng có thể được commit; transaction còn lại sẽ nhận lỗi duplicate key hoặc xử lý theo cú pháp upsert của hệ quản trị.

Luồng ứng dụng có thể đơn giản hơn:

~~~sql
INSERT INTO room_booking (room_id, booking_date, customer_id)
VALUES (5, DATE '2026-11-20', 101);
~~~

Ứng dụng xử lý lỗi vi phạm unique constraint như kết quả “lịch đã được đặt”. Không cần dựa vào lần SELECT trước để quyết định tính duy nhất.

Ở PostgreSQL, có thể dùng:

~~~sql
INSERT INTO room_booking (room_id, booking_date, customer_id)
VALUES (5, DATE '2026-11-20', 101)
ON CONFLICT (room_id, booking_date) DO NOTHING;
~~~

Sau đó ứng dụng kiểm tra số hàng được chèn hoặc đọc lại lượt đặt hiện tại theo quy tắc nghiệp vụ.

Constraint là cách mạnh và rõ ràng cho tính duy nhất vì nó được áp dụng cho mọi đường ghi, kể cả khi có nhiều service hoặc tiến trình cùng truy cập. Tuy nhiên, UNIQUE(room_id, booking_date) chỉ bảo vệ đúng tổ hợp đó. Nó không thể diễn đạt trực tiếp mọi điều kiện phức tạp như “không có hai khoảng thời gian giao nhau” hoặc “tổng số lượng của cả nhóm không vượt giới hạn”.

## 5. Dùng hàng điều phối đã tồn tại để bảo vệ một nhóm dữ liệu

Khi không thể biểu diễn bất biến bằng một unique key, có thể khóa một hàng đại diện cho tài nguyên hoặc nhóm dữ liệu. Hàng này phải tồn tại trước khi các transaction cần dùng nó.

Ví dụ, bảng room đã có hàng cho phòng 5. Mọi transaction tạo hoặc thay đổi lượt đặt của phòng phải khóa hàng phòng trước khi kiểm tra các lượt đặt:

~~~sql
BEGIN;

SELECT room_id
FROM room
WHERE room_id = 5
FOR UPDATE;

-- Chỉ sau khi lấy được khóa phòng mới kiểm tra lịch đặt.
SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date = DATE '2026-11-20';

-- Nếu chưa có lịch, tạo lượt đặt.
INSERT INTO room_booking (room_id, booking_date, customer_id)
VALUES (5, DATE '2026-11-20', 101);

COMMIT;
~~~

Nếu T1 đã khóa hàng phòng 5, T2 phải chờ. Khi T1 commit, T2 lấy được khóa rồi mới kiểm tra lượt đặt. Ở READ COMMITTED, lần đọc sau khi lấy khóa sẽ thấy lượt đặt vừa được T1 commit và có thể từ chối thao tác.

Cách này bảo vệ được quy tắc chỉ khi **mọi transaction có thể thay đổi lịch đặt đều khóa cùng hàng điều phối trước khi kiểm tra và ghi**. Một service khác bỏ qua bước khóa vẫn có thể tạo ra race condition.

Ưu điểm là hàng điều phối tồn tại ngay cả khi chưa có lượt đặt nào. Hạn chế là các thao tác trên cùng phòng bị tuần tự hóa, kể cả khi chúng liên quan đến các ngày khác nhau. Có thể tạo hàng điều phối nhỏ hơn theo tổ hợp tài nguyên/ngày nếu cần tăng khả năng chạy đồng thời.

Cũng cần chú ý đến snapshot của transaction. Nếu transaction đã đọc trạng thái lịch trước khi khóa hàng điều phối ở isolation level dùng snapshot cấp transaction, lần đọc sau đó có thể vẫn dùng snapshot cũ. Hãy lấy khóa điều phối trước lần đọc phụ thuộc vào điều kiện và chọn isolation level phù hợp với hệ quản trị.

## 6. Advisory lock: khóa một tài nguyên logic chưa có hàng

Một số hệ quản trị hỗ trợ khóa tư vấn (*advisory lock*). Đây là khóa trên một định danh logic do ứng dụng chọn, không cần có hàng tương ứng trong bảng.

PostgreSQL cung cấp khóa advisory ở cấp session và transaction. Với thao tác cần tự động nhả khóa khi transaction kết thúc, có thể dùng khóa transaction-scoped:

~~~sql
BEGIN;

-- Khóa logic đại diện cho phòng 5 và ngày cần đặt.
SELECT pg_advisory_xact_lock(5005, 20261120);

-- Sau khi có khóa logic, mới kiểm tra dữ liệu.
SELECT booking_id
FROM room_booking
WHERE room_id = 5
  AND booking_date = DATE '2026-11-20';

-- INSERT nếu chưa có.

COMMIT;
~~~

T1 và T2 dùng cùng khóa advisory cho cùng một tài nguyên logic thì chỉ một transaction có thể đi qua vùng kiểm tra–ghi tại một thời điểm. Khóa được giải phóng khi transaction commit hoặc rollback.

Advisory lock hữu ích khi cần khóa một khái niệm chưa có bản ghi, chẳng hạn “phòng 5 vào ngày X”, “tên người dùng đang được đăng ký”, hoặc “tác vụ đồng bộ cho khách hàng Y”.

Tuy nhiên, advisory lock là quy ước phối hợp do ứng dụng chịu trách nhiệm:

- Mọi đường ghi liên quan phải dùng cùng quy tắc ánh xạ tài nguyên sang lock key.
- Hai tiến trình phải tính ra cùng lock key cho cùng một tài nguyên.
- Nếu dùng hàm băm, cần xử lý khả năng va chạm khóa giữa hai tài nguyên khác nhau.
- Khóa advisory không tự ngăn một client khác bỏ qua khóa rồi ghi trực tiếp vào bảng.
- Cần giữ khóa transaction-scoped trong cùng transaction thực hiện kiểm tra và ghi.

Khóa advisory không thay thế constraint dữ liệu. Nếu quy tắc là tính duy nhất, vẫn nên có unique constraint để database bảo vệ ở lớp cuối cùng.

## 7. Bảo vệ điều kiện phức tạp như khoảng thời gian không được giao nhau

Một số quy tắc không chỉ yêu cầu một khóa cụ thể chưa tồn tại, mà yêu cầu không có hàng nào thỏa một predicate phức tạp.

Ví dụ, một phòng không được có hai lượt đặt giao nhau về thời gian. Chỉ dùng UNIQUE(room_id, start_time) là chưa đủ vì hai khoảng có thể chồng lấn dù thời điểm bắt đầu khác nhau.

Có thể dùng một constraint chuyên biệt nếu hệ quản trị hỗ trợ. PostgreSQL có exclusion constraint cho trường hợp khoảng thời gian:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id BIGSERIAL PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
~~~

&& kiểm tra hai range có giao nhau hay không. Constraint yêu cầu cùng một phòng không có hai range thời gian giao nhau. Hệ quản trị sẽ kiểm tra các insert/update cạnh tranh và từ chối thay đổi vi phạm.

Đây là ví dụ dành cho PostgreSQL; cú pháp và loại constraint tương đương không có sẵn giống hệt ở mọi database. Với hệ quản trị khác, có thể cần SERIALIZABLE, key-range lock, hàng điều phối hoặc một thiết kế lưu slot rời rạc có unique key.

Khi điều kiện nghiệp vụ có thể được diễn đạt bằng constraint, nên ưu tiên để database kiểm tra nguyên tử. Nếu phải dùng khóa phạm vi hoặc khóa logic, cần xác định chính xác predicate nào được bảo vệ và mọi đường ghi có tuân thủ cùng giao thức hay không.

## 8. So sánh các cách bảo vệ khi hàng chưa tồn tại

| Cơ chế | Bảo vệ cái gì? | Điểm mạnh | Giới hạn |
|---|---|---|---|
| SELECT ... FOR UPDATE trên hàng | Hàng hiện hữu được truy vấn trả về | Đơn giản, phù hợp khi hàng đã tồn tại | Kết quả rỗng có thể không tạo row lock |
| Gap/next-key lock | Khoảng khóa chỉ mục | Ngăn insert vào khoảng được bảo vệ | Phụ thuộc engine, isolation level, chỉ mục và access path |
| Predicate/key-range lock | Phạm vi thỏa điều kiện truy vấn | Bảo vệ cả trường hợp chưa có hàng | Có thể khóa rộng hoặc làm tăng chờ; cách triển khai khác nhau |
| SERIALIZABLE | Lịch giao dịch và predicate liên quan | Bảo vệ quy tắc phức tạp ở mức transaction | Có thể block hoặc abort; cần retry |
| Unique/exclusion constraint | Quy tắc dữ liệu diễn đạt được bằng constraint | Áp dụng cho mọi đường ghi | Chỉ biểu diễn được loại điều kiện mà constraint hỗ trợ |
| Guard row | Nhóm tài nguyên đại diện bằng một hàng đã tồn tại | Dễ kiểm soát thứ tự đọc–ghi | Mọi writer phải tuân thủ; có thể tạo điểm nóng |
| Advisory lock | Tài nguyên logic do ứng dụng định danh | Khóa được tài nguyên chưa có hàng | Cần quy ước chung; client bỏ qua lock vẫn có thể ghi |

## 9. Những lỗi thiết kế thường gặp

**Chỉ dùng SELECT rồi INSERT**

Hai transaction có thể cùng đọc kết quả rỗng. Nếu không có constraint hoặc khóa phạm vi, cả hai có thể chèn dữ liệu trùng.

**Cho rằng FOR UPDATE luôn khóa cả chỗ trống**

Ý nghĩa và phạm vi của câu lệnh khác nhau giữa PostgreSQL, InnoDB và SQL Server. Phải biết engine đang khóa hàng, khoảng chỉ mục hay predicate nào.

**Tạo hàng guard trong lúc cần khóa nhưng không bảo vệ việc tạo guard**

Nếu hàng điều phối chưa tồn tại, hai transaction có thể cùng thử tạo nó. Hãy tạo trước hoặc dùng unique key/upsert để bảo đảm chỉ có một hàng đại diện.

**Chỉ một service dùng khóa điều phối**

Nếu batch job, admin tool hoặc một service khác ghi trực tiếp mà không lấy cùng khóa, bất biến vẫn có thể bị phá vỡ. Cần gom quyền ghi vào một đường thực thi được kiểm soát hoặc bảo vệ thêm bằng constraint.

**Dùng isolation level thấp hơn nhưng giữ nguyên giả định cũ**

Gap lock, key-range lock và predicate tracking phụ thuộc isolation level. Thay đổi cấu hình transaction có thể làm mất cơ chế bảo vệ mà trước đó truy vấn dựa vào.

**Không xử lý lỗi cạnh tranh như một kết quả nghiệp vụ bình thường**

Khi constraint báo duplicate key hoặc SERIALIZABLE hủy transaction, ứng dụng phải phân biệt “tài nguyên đã được tạo bởi giao dịch khác” với lỗi hệ thống không thể thử lại. Cần rollback và đọc lại trạng thái theo quy tắc nghiệp vụ.

## 10. Quy trình thiết kế an toàn cho thao tác “nếu chưa tồn tại thì tạo”

Khi triển khai thao tác này, hãy thực hiện theo các bước:

1. **Định nghĩa chính xác điều kiện duy nhất hoặc predicate.** Ví dụ: một lượt đặt cho mỗi phòng/ngày, hoặc không có khoảng đặt nào giao nhau.
2. **Chọn cơ chế bảo vệ phù hợp.** Dùng unique/exclusion constraint nếu diễn đạt được; nếu không, cân nhắc SERIALIZABLE, range lock, guard row hoặc advisory lock.
3. **Lấy cơ chế bảo vệ trước khi kiểm tra.** Đối với guard row hoặc advisory lock, lấy khóa trước câu SELECT kiểm tra điều kiện.
4. **Kiểm tra và ghi trong cùng transaction.** Không mở khoảng thời gian giữa kiểm tra và insert mà không được bảo vệ.
5. **Xử lý kết quả cạnh tranh.** Duplicate key, serialization failure hoặc lock timeout phải được phân loại và xử lý rõ ràng.
6. **Retry toàn bộ transaction khi cần.** Đọc lại dữ liệu và đánh giá lại điều kiện; không tái sử dụng quyết định từ snapshot cũ.
7. **Kiểm thử bằng hai transaction đồng thời.** Cả hai phải cùng thực hiện truy vấn kiểm tra trước khi một transaction commit, để tái hiện đúng race condition.

## 11. Checklist khi chọn khóa cho hàng chưa tồn tại

- [ ] Truy vấn có thể trả về rỗng khi tài nguyên logic vẫn cần được bảo vệ không?
- [ ] Câu lệnh khóa đang bảo vệ hàng hiện hữu, khoảng chỉ mục hay predicate?
- [ ] Isolation level có làm thay đổi gap lock hoặc key-range lock không?
- [ ] Điều kiện có thể được biểu diễn bằng UNIQUE, exclusion constraint hoặc constraint khác không?
- [ ] Có hàng cha/guard ổn định để khóa trước khi kiểm tra không?
- [ ] Nếu dùng advisory lock, mọi writer có cùng cách tạo lock key không?
- [ ] Có transaction nào đọc điều kiện trước khi lấy khóa điều phối không?
- [ ] Ứng dụng có xử lý duplicate key, serialization failure và retry đúng ranh giới transaction không?
- [ ] Kiểm thử có tái hiện được hai transaction cùng thấy kết quả rỗng không?

Khóa hàng rất hữu ích khi bản ghi đã tồn tại. Khi bản ghi chưa tồn tại, điều cần bảo vệ thường là vị trí có thể chèn hoặc điều kiện truy vấn xác định tài nguyên logic. Tùy hệ quản trị, có thể dùng gap/next-key lock, key-range lock hoặc predicate tracking; trong thiết kế ứng dụng, unique constraint, hàng điều phối và advisory lock cũng là những lựa chọn quan trọng. Hãy xác định chính xác thứ cần bảo vệ, lấy cơ chế bảo vệ trước khi kiểm tra, và giữ thao tác kiểm tra–ghi trong cùng transaction.
