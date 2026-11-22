# Chèn đồng thời vào khoảng đang được bảo vệ

Khi một transaction truy vấn một khoảng dữ liệu, ví dụ tất cả đơn hàng đang mở hoặc mọi lịch đặt phòng giao nhau với một khung giờ, transaction có thể cần bảo vệ **điều kiện truy vấn (predicate)** chứ không chỉ những dòng đang tồn tại. Nếu transaction khác chèn một dòng mới thỏa điều kiện trong lúc transaction đầu đang kiểm tra, kết quả truy vấn có thể thay đổi. Dòng mới xuất hiện này thường được gọi là **phantom row**.

Một số hệ quản trị ngăn phantom bằng khóa khoảng (range lock), khóa khoảng trống (gap lock) hoặc khóa next-key. PostgreSQL dùng Serializable Snapshot Isolation (SSI) để theo dõi phụ thuộc đọc/ghi và có thể hủy một transaction khi phát hiện nguy cơ không tuần tự hóa. Vì vậy, khái niệm "bảo vệ khoảng" không phải lúc nào cũng có nghĩa là chặn lệnh INSERT.

Chỉ mục có ảnh hưởng lớn đến cách hệ quản trị xác định khoảng cần bảo vệ. Một chỉ mục phù hợp giúp database định vị các khóa nằm trong khoảng và kiểm soát vùng chèn liên quan. Khi không có chỉ mục phù hợp, phạm vi khóa hoặc phạm vi theo dõi có thể rộng hơn, làm tăng blocking hay số lần transaction bị hủy.

## 1. Phantom row là gì?

Giả sử bảng Booking lưu lịch đặt phòng. Transaction T1 kiểm tra xem phòng 10 có lịch nào giao với khoảng thời gian yêu cầu hay không:

~~~sql
SELECT BookingId
FROM Booking
WHERE RoomId = 10
  AND StartTime < '2026-12-01 11:00'
  AND EndTime > '2026-12-01 10:00';
~~~

T1 thấy không có dòng nào. Trong khi T1 vẫn đang xử lý, T2 thêm một lịch đặt phòng thỏa điều kiện rồi COMMIT. Nếu T1 chạy lại câu SELECT và nhìn thấy dòng mới, kết quả đã thay đổi dù T1 không sửa dòng nào trong tập kết quả ban đầu.

~~~text
Ban đầu: không có lịch giao với 10:00–11:00

T1                                  T2
--                                  --
BEGIN
SELECT khoảng 10:00–11:00
Kết quả: 0 dòng
                                    INSERT lịch 10:30–11:30
                                    COMMIT
SELECT lại cùng điều kiện
Có một dòng mới xuất hiện
COMMIT
~~~

Dòng được T2 chèn là phantom đối với truy vấn của T1. Phantom khác với non-repeatable read:

- **Non-repeatable read:** một dòng đã đọc bị transaction khác cập nhật hoặc xóa; đọc lại cùng dòng cho kết quả khác hoặc không còn dòng.
- **Phantom read:** tập dòng thỏa một điều kiện truy vấn thay đổi vì transaction khác chèn hoặc cập nhật dòng làm nó thuộc tập kết quả, hoặc xóa dòng khiến nó rời tập.

Phantom thường liên quan đến predicate hoặc khoảng khóa. Transaction có thể cần bảo đảm rằng không có dòng mới nào xuất hiện trong phạm vi đã kiểm tra trước khi nó hoàn tất thao tác nghiệp vụ.

### 1.1. Vì sao phantom có thể phá vỡ quy tắc nghiệp vụ?

Hãy xét quy tắc: cùng một phòng không được có hai lịch đặt giao nhau.

Hai request đồng thời cùng kiểm tra khoảng 10:00–11:00:

- T1 thấy chưa có lịch giao nhau và chuẩn bị tạo Booking A.
- T2 cũng thấy chưa có lịch giao nhau và chuẩn bị tạo Booking B.
- T1 chèn Booking A.
- T2 chèn Booking B.

Nếu hai transaction không có cơ chế bảo vệ predicate hoặc constraint phù hợp, cả hai có thể commit. Kết quả là hai lịch cùng chiếm một phòng trong một khoảng thời gian.

~~~text
T1                                  T2
--                                  --
Kiểm tra: không có lịch             Kiểm tra: không có lịch
INSERT Booking A                    INSERT Booking B
COMMIT                              COMMIT

Kết quả: hai booking giao nhau
~~~

Mỗi transaction tự thấy quyết định của mình hợp lệ trên snapshot riêng. Nhưng quy tắc cần bảo vệ áp dụng cho toàn bộ tập lịch của phòng, bao gồm cả dòng mà transaction kia vừa chèn.

## 2. Bảo vệ dòng hiện có khác với bảo vệ khoảng

Một khóa trên dòng hiện có bảo vệ giá trị của dòng đó. Nó không nhất thiết ngăn transaction khác chèn một dòng mới thỏa điều kiện truy vấn.

Ví dụ, nếu T1 khóa tất cả booking hiện có của RoomId 10, nhưng hiện tại không có booking nào trong khoảng yêu cầu, không có dòng nào để khóa. T2 vẫn có thể chèn một booking mới vào khoảng đó nếu DBMS không có cơ chế bảo vệ khoảng tương ứng.

~~~text
Chỉ khóa các dòng đang tồn tại

Index theo thời gian:
... 09:00          12:00 ...
       [ khoảng trống ]
          ^
          |
      T1 không tìm thấy dòng để khóa

T2 có thể chèn key mới vào khoảng trống
nếu isolation/lock strategy không bảo vệ predicate.
~~~

Để ngăn phantom, hệ quản trị cần bảo vệ cả vùng giữa các khóa chỉ mục hoặc theo dõi điều kiện truy vấn đã đọc. Cách thực hiện phụ thuộc DBMS:

- SQL Server có key-range locks ở isolation level SERIALIZABLE.
- MySQL InnoDB dùng gap locks và next-key locks trong các thao tác locking phù hợp.
- PostgreSQL SERIALIZABLE dùng SIREAD predicate locks và SSI để phát hiện phụ thuộc; SIREAD không chặn INSERT theo kiểu khóa khoảng truyền thống.

Không nên giả định một câu SELECT thông thường luôn bảo vệ khoảng. Cần xác định isolation level, loại truy vấn, chỉ mục được dùng và cơ chế cụ thể của hệ quản trị.

## 3. Chỉ mục quyết định phạm vi khoảng được bảo vệ như thế nào

Range lock thường được gắn với thứ tự khóa trong chỉ mục. Chỉ mục sắp xếp các giá trị thành một dãy, giúp hệ quản trị xác định các khóa nằm trước, nằm trong và nằm sau khoảng truy vấn.

Giả sử có chỉ mục theo (RoomId, StartTime):

~~~text
Index keys cho RoomId = 10

(10, 09:00)
(10, 09:30)
(10, 11:30)
(10, 13:00)

Một truy vấn lọc RoomId = 10 và StartTime trong khoảng 10:00–12:00
có thể định vị vùng khóa giữa hai giá trị lân cận.
~~~

Tùy DBMS, transaction có thể khóa hoặc theo dõi cả khoảng trống giữa các key, nơi một key mới có thể được chèn.

Chỉ mục phù hợp có thể giúp:

- Giới hạn số trang và key cần quét.
- Xác định ranh giới khoảng rõ ràng.
- Giảm phạm vi khóa hoặc phạm vi predicate cần theo dõi.
- Hạn chế việc một truy vấn phải quét toàn bộ bảng và vô tình bảo vệ phạm vi rộng.

Chỉ mục không tự tạo ra bảo đảm serializable. Nếu isolation level không yêu cầu bảo vệ khoảng, một index seek vẫn có thể cho phép phantom. Ngược lại, khi dùng SERIALIZABLE nhưng không có index phù hợp, database vẫn phải bảo vệ điều kiện truy vấn bằng một cách khác, có thể tạo phạm vi khóa rộng và giảm concurrency.

### 3.1. Thứ tự cột trong chỉ mục

Với truy vấn:

~~~sql
WHERE RoomId = @roomId
  AND StartTime < @requestedEnd
  AND EndTime > @requestedStart
~~~

Một chỉ mục như:

~~~sql
CREATE INDEX IX_Booking_Room_Start
ON Booking (RoomId, StartTime);
~~~

có thể hỗ trợ điều kiện equality trên RoomId và range trên StartTime. Điều kiện EndTime vẫn có thể được kiểm tra sau khi tìm các ứng viên. Đây là ví dụ minh họa; khả năng sử dụng index còn tùy thống kê, kiểu dữ liệu, độ chọn lọc và optimizer.

Nếu predicate chứa nhiều điều kiện, không phải lúc nào một index cũng biểu diễn chính xác toàn bộ hình dạng khoảng. Hệ quản trị có thể bảo vệ rộng hơn vùng mà truy vấn cuối cùng trả về. Hãy đọc execution plan để biết index scan/seek thực tế và phạm vi tài nguyên được truy cập.

### 3.2. Không có index phù hợp

Nếu không có index theo cột lọc, database có thể phải quét nhiều dòng. Ở chế độ SERIALIZABLE, việc bảo vệ phantom có thể đòi hỏi khóa hoặc theo dõi phạm vi rộng hơn, thậm chí gần như toàn bảng tùy DBMS và kế hoạch thực thi.

Hậu quả có thể là:

- INSERT vào những giá trị không thực sự giao với nghiệp vụ vẫn bị chặn.
- Nhiều transaction độc lập phải chờ nhau.
- Số lần deadlock hoặc serialization failure tăng.
- Thời gian giữ khóa và chi phí kiểm tra phụ thuộc tăng.

Vì vậy, index là một phần của thiết kế đồng thời, không chỉ là công cụ tăng tốc SELECT. Tuy nhiên, index bổ sung cũng làm tăng chi phí INSERT/UPDATE vì database phải duy trì thêm cấu trúc chỉ mục.

## 4. SQL Server: key-range locks ở SERIALIZABLE

SQL Server dùng **key-range locks** để bảo vệ khoảng khóa trong index khi transaction chạy ở isolation level SERIALIZABLE. Cơ chế này ngăn transaction khác chèn key mới vào phạm vi mà transaction hiện tại cần giữ ổn định.

Khác biệt quan trọng:

- REPEATABLE READ giữ khóa trên những dòng đã đọc, nhưng không bảo vệ toàn bộ khoảng để ngăn phantom insert.
- SERIALIZABLE bổ sung bảo vệ khoảng khóa, nhờ đó các dòng mới thỏa predicate không thể xuất hiện trong phạm vi đang được bảo vệ trước khi transaction kết thúc.

### 4.1. Ví dụ hai session

Giả sử bảng Booking có index hỗ trợ tìm theo RoomId và StartTime:

~~~sql
CREATE INDEX IX_Booking_Room_Start
ON dbo.Booking (RoomId, StartTime);
~~~

Session A bắt đầu transaction SERIALIZABLE và kiểm tra khoảng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
BEGIN TRANSACTION;

SELECT BookingId
FROM dbo.Booking
WHERE RoomId = 10
  AND StartTime >= '2026-12-01 10:00'
  AND StartTime <  '2026-12-01 11:00';

-- Giữ transaction mở để quan sát range lock.
~~~

Trong lúc A chưa COMMIT, Session B thử chèn một key thuộc phạm vi:

~~~sql
INSERT INTO dbo.Booking
    (BookingId, RoomId, StartTime, EndTime)
VALUES
    (9001, 10, '2026-12-01 10:30', '2026-12-01 11:30');
~~~

Nếu execution plan và phạm vi khóa của A bao phủ key mới, INSERT của B phải chờ đến khi A COMMIT hoặc ROLLBACK. Sau khi A kết thúc, B mới có thể tiếp tục nếu không còn xung đột khác.

~~~text
Session A (SERIALIZABLE)             Session B
-------------------------             ---------
SELECT khoảng
Giữ key-range lock
                                      INSERT key trong khoảng
                                      WAIT
COMMIT
Giải phóng range lock
                                      INSERT tiếp tục
                                      COMMIT
~~~

Ví dụ này mô tả hành vi khi truy vấn sử dụng index và range lock thực sự bao phủ key chèn. Kết quả khóa cụ thể phụ thuộc index, execution plan, isolation level và các khóa khác đang tồn tại.

### 4.2. Một số chế độ key-range lock

SQL Server biểu diễn khóa khoảng bằng các chế độ kết hợp giữa loại khóa phạm vi và khóa key. Một số tên có thể thấy trong công cụ chẩn đoán:

| Chế độ | Ý nghĩa khái quát |
|---|---|
| RangeS-S | Khóa chia sẻ trên khoảng và key |
| RangeS-U | Khóa chia sẻ trên khoảng với khóa cập nhật ở key |
| RangeI-N | Khóa kiểm tra insert trên khoảng |
| RangeX-X | Khóa độc quyền trên khoảng và key |

Không cần tự chọn một chế độ bằng tay trong truy vấn thông thường. SQL Server quyết định loại khóa dựa trên câu lệnh, isolation level, hint và execution plan. Các tên trên hữu ích khi đọc DMV hoặc deadlock graph.

### 4.3. Check-then-insert và nguy cơ deadlock

Một mẫu phổ biến là hai transaction cùng kiểm tra khoảng trống rồi cùng chèn. Cả hai có thể lấy khóa đọc khoảng tương thích, sau đó cùng muốn chuyển sang quyền ghi. Quá trình chuyển đổi khóa có thể tạo deadlock.

Nếu nghiệp vụ cần tuần tự hóa các lần kiểm tra/chèn, có thể dùng UPDLOCK kết hợp HOLDLOCK trong SQL Server để lấy update range lock cho vùng truy vấn:

~~~sql
BEGIN TRANSACTION;

IF NOT EXISTS
(
    SELECT 1
    FROM dbo.Booking WITH (UPDLOCK, HOLDLOCK)
    WHERE RoomId = @roomId
      AND StartTime < @requestedEnd
      AND EndTime > @requestedStart
)
BEGIN
    INSERT INTO dbo.Booking
        (BookingId, RoomId, StartTime, EndTime)
    VALUES
        (@bookingId, @roomId, @requestedStart, @requestedEnd);
END
ELSE
BEGIN
    THROW 50010, 'The requested time range is unavailable.', 1;
END;

COMMIT TRANSACTION;
~~~

HOLDLOCK áp dụng ngữ nghĩa SERIALIZABLE cho tham chiếu bảng; UPDLOCK yêu cầu khóa cập nhật thay vì chỉ khóa chia sẻ trong quá trình kiểm tra. Cách này có thể giúp tuần tự hóa các transaction check-then-insert, nhưng vẫn cần index phù hợp và xử lý deadlock. Không thêm hint theo thói quen nếu chưa kiểm tra kế hoạch truy vấn và các luồng truy cập khác.

Nếu phạm vi cần bảo vệ là một phòng cụ thể, một cách dễ hiểu hơn đôi khi là khóa dòng đại diện của Room trước khi kiểm tra booking. Mọi thao tác tạo hoặc thay đổi booking của cùng phòng phải khóa cùng dòng guard. Cách này chủ động tuần tự hóa theo phòng, đổi lại các booking của cùng phòng phải chờ nhau.

## 5. MySQL InnoDB: gap lock và next-key lock

InnoDB dùng chỉ mục clustered/secondary để tìm bản ghi và quản lý khóa. Với các thao tác locking phù hợp ở REPEATABLE READ, InnoDB có thể dùng:

- **Record lock:** khóa một record/index entry hiện có.
- **Gap lock:** khóa khoảng trống giữa các index record, ngăn chèn key vào khoảng đó.
- **Next-key lock:** kết hợp record lock với gap lock ngay trước record đó, bảo vệ một đoạn của thứ tự index.

Mục tiêu của gap/next-key lock là ngăn phantom insert trong những phạm vi cần được bảo vệ bởi locking read hoặc thao tác ghi.

### 5.1. Locking read khác với consistent read

Trong InnoDB, một câu SELECT thông thường ở REPEATABLE READ thường là consistent read theo MVCC. Nó đọc snapshot và không lấy row/gap lock như một locking read.

Để khóa phạm vi, thường cần locking read:

~~~sql
START TRANSACTION;

SELECT BookingId
FROM Booking
WHERE RoomId = 10
  AND StartTime >= '2026-12-01 10:00'
  AND StartTime <  '2026-12-01 11:00'
FOR UPDATE;

-- Thực hiện kiểm tra/chèn trong cùng transaction.
COMMIT;
~~~

Nếu có index hỗ trợ điều kiện, InnoDB có thể lấy next-key locks trên các index record và gap tương ứng. INSERT của transaction khác vào vùng gap đang bị khóa có thể phải chờ.

Ở REPEATABLE READ, next-key locking thường được dùng cho locking reads và các thao tác UPDATE/DELETE theo range. Ở READ COMMITTED, gap locking cho search/index scan thường được tắt, ngoại trừ một số trường hợp cần bảo vệ ràng buộc khóa ngoại hoặc kiểm tra duplicate key. Chi tiết phụ thuộc phiên bản và loại câu lệnh.

### 5.2. Ví dụ hai session

Session A:

~~~sql
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;
START TRANSACTION;

SELECT BookingId
FROM Booking FORCE INDEX (idx_booking_room_start)
WHERE RoomId = 10
  AND StartTime >= '2026-12-01 10:00'
  AND StartTime <  '2026-12-01 11:00'
FOR UPDATE;
~~~

Session B:

~~~sql
INSERT INTO Booking
    (BookingId, RoomId, StartTime, EndTime)
VALUES
    (9002, 10, '2026-12-01 10:30', '2026-12-01 11:30');
~~~

Nếu index range mà A khóa bao gồm vị trí chèn của B, B sẽ chờ cho đến khi A COMMIT hoặc ROLLBACK. Khi A kết thúc, B có thể tiếp tục.

FORCE INDEX trong ví dụ chỉ nhằm làm rõ index được dùng khi minh họa. Trong ứng dụng thực tế, chỉ nên ép index khi đã đo và xác nhận optimizer cần được hướng dẫn; thông thường hãy thiết kế index phù hợp và kiểm tra EXPLAIN.

### 5.3. Gap lock có thể làm phát sinh deadlock

Gap lock có tính chất khác record lock: nhiều transaction có thể cùng giữ gap lock trên một khoảng, nhưng insert intention của một transaction vẫn bị ngăn bởi gap lock của transaction khác.

Nếu T1 và T2 cùng khóa một gap rồi cả hai muốn INSERT vào đó, chúng có thể tạo tình huống deadlock khi mỗi transaction chờ transaction còn lại giải phóng gap. InnoDB phát hiện deadlock và chọn một transaction làm victim; ứng dụng cần rollback và thử lại toàn bộ transaction nếu nghiệp vụ cho phép.

Nếu cần bảo vệ một tài nguyên logic duy nhất, khóa một dòng cha/guard row có thể dễ kiểm soát hơn việc để nhiều transaction cùng lấy gap lock rồi chuyển sang insert.

## 6. PostgreSQL: predicate tracking bằng SSI

PostgreSQL dùng MVCC và có cách bảo vệ SERIALIZABLE khác với range lock truyền thống.

Ở isolation level SERIALIZABLE, PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** và các dấu vết đọc SIREAD để theo dõi predicate mà transaction đã đọc. Khi một transaction khác INSERT hoặc UPDATE một dòng làm thay đổi tập kết quả, PostgreSQL có thể ghi nhận một read-write antidependency.

Điểm quan trọng:

- SIREAD không chặn INSERT như gap lock của InnoDB hoặc key-range lock của SQL Server.
- Transaction ghi có thể tiếp tục.
- PostgreSQL theo dõi các phụ thuộc rw giữa transaction.
- Nếu phụ thuộc tạo dangerous structure có nguy cơ dẫn đến serialization anomaly, PostgreSQL hủy một transaction.
- Ứng dụng nhận SQLSTATE 40001 và phải retry toàn bộ transaction trên snapshot mới.

### 6.1. Ví dụ hai transaction cùng kiểm tra khoảng trống

Giả sử mỗi phòng không được có lịch đặt trùng giờ. Hai transaction cùng chạy ở SERIALIZABLE:

Session A:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT BookingId
FROM Booking
WHERE RoomId = 10
  AND StartTime < TIMESTAMP '2026-12-01 11:00'
  AND EndTime > TIMESTAMP '2026-12-01 10:00';

-- Không có dòng giao nhau.

INSERT INTO Booking
    (BookingId, RoomId, StartTime, EndTime)
VALUES
    (9003, 10, TIMESTAMP '2026-12-01 10:00',
             TIMESTAMP '2026-12-01 11:00');

COMMIT;
~~~

Session B chạy đồng thời với khoảng tương tự nhưng BookingId khác:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT BookingId
FROM Booking
WHERE RoomId = 10
  AND StartTime < TIMESTAMP '2026-12-01 11:00'
  AND EndTime > TIMESTAMP '2026-12-01 10:00';

-- Snapshot của B cũng chưa thấy dòng A vừa chèn.

INSERT INTO Booking
    (BookingId, RoomId, StartTime, EndTime)
VALUES
    (9004, 10, TIMESTAMP '2026-12-01 10:15',
             TIMESTAMP '2026-12-01 11:15');

COMMIT;
~~~

Mỗi transaction đọc predicate và transaction kia chèn một dòng làm predicate đó đúng. Có thể hình thành hai cạnh rw ngược chiều. Nếu để cả hai commit, cả hai đều tin rằng khoảng trống còn tồn tại, dẫn đến hai booking giao nhau. SSI phát hiện nguy cơ write skew và một transaction có thể bị hủy với serialization failure.

Không nên khẳng định session nào luôn thất bại. Kết quả phụ thuộc lịch chạy và thời điểm commit. Ứng dụng phải xử lý lỗi 40001 ở ranh giới toàn transaction.

### 6.2. REPEATABLE READ không đồng nghĩa SERIALIZABLE

Trong PostgreSQL, REPEATABLE READ giữ snapshot ổn định trong transaction và ngăn phantom read theo định nghĩa isolation chuẩn. Tuy nhiên, nó vẫn có thể gặp write skew và các serialization anomaly khác.

SERIALIZABLE bổ sung SSI để phát hiện các phụ thuộc nguy hiểm. Vì vậy, nếu nghiệp vụ cần bảo đảm không có hai transaction đồng thời cùng kết luận một predicate còn trống rồi cùng ghi dữ liệu xung đột, cần lựa chọn SERIALIZABLE hoặc một cơ chế bảo vệ invariant khác.

## 7. So sánh cách bảo vệ khoảng giữa các DBMS

| DBMS | Cơ chế liên quan | Khi transaction khác chèn vào khoảng |
|---|---|---|
| SQL Server | Key-range lock ở SERIALIZABLE | INSERT vào vùng bị khóa có thể phải chờ đến khi transaction bảo vệ kết thúc |
| MySQL InnoDB | Gap/next-key lock trong locking read và thao tác range phù hợp | INSERT vào gap bị khóa có thể phải chờ; cạnh tranh có thể dẫn đến deadlock |
| PostgreSQL | SIREAD predicate lock và SSI ở SERIALIZABLE | INSERT không bị SIREAD chặn trực tiếp; transaction có thể bị hủy nếu hình thành dangerous structure |
| PostgreSQL REPEATABLE READ | Snapshot cấp transaction | Đọc lại vẫn dùng snapshot cũ; không có SSI để ngăn mọi write skew |
| MySQL InnoDB READ COMMITTED | MVCC snapshot theo câu lệnh; gap locking bị hạn chế cho search/index scan | Không nên dựa vào một SELECT thông thường để khóa khoảng |

Tên isolation level giống nhau không bảo đảm các DBMS triển khai cùng một cơ chế. Khi chuyển ứng dụng từ SQL Server sang PostgreSQL hoặc InnoDB, phải kiểm tra lại cách bảo vệ predicate và cách xử lý transaction bị hủy.

## 8. Khi nào nên dùng constraint thay vì chỉ dựa vào range lock?

Nếu quy tắc có thể biểu diễn bằng constraint, hãy để database bảo vệ nó tại nơi dữ liệu được ghi. Constraint áp dụng cho mọi luồng ghi tuân thủ schema, kể cả API, batch job và công cụ quản trị.

### 8.1. Trường hợp khóa duy nhất

Nếu yêu cầu chỉ là không có hai dòng cùng RoomId và cùng StartTime, có thể dùng unique index:

~~~sql
CREATE UNIQUE INDEX UX_Booking_Room_Start
ON dbo.Booking (RoomId, StartTime);
~~~

Hai transaction cùng chèn một key trùng sẽ không thể cùng commit thành công. Một bên có thể chờ hoặc nhận lỗi duplicate key tùy thời điểm và DBMS.

Unique index không giải quyết được mọi trường hợp lịch giao nhau. Ví dụ 10:00–11:00 và 10:30–11:30 có StartTime khác nhau nhưng vẫn overlap.

### 8.2. Trường hợp khoảng thời gian không được giao nhau

PostgreSQL có exclusion constraint với range type và GiST, phù hợp để biểu diễn quy tắc các khoảng đặt phòng không được overlap:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE booking (
    booking_id bigint PRIMARY KEY,
    room_id    integer NOT NULL,
    during     tstzrange NOT NULL,
    EXCLUDE USING gist
        (room_id WITH =, during WITH &&)
);
~~~

Toán tử && kiểm tra hai range có giao nhau hay không. Exclusion constraint bảo vệ quy tắc ở database khi các transaction đồng thời chèn khoảng thời gian xung đột. Một transaction có thể phải chờ transaction khác và sau đó nhận lỗi constraint nếu khoảng bị trùng.

Đây là ví dụ PostgreSQL; cú pháp, kiểu range và extension phụ thuộc môi trường. Với DBMS không có constraint tương đương, có thể dùng SERIALIZABLE, khóa guard row theo RoomId hoặc một mô hình dữ liệu khác.

### 8.3. Khi dùng guard row

Nếu quy tắc liên quan đến một phòng, tài khoản, ca trực hoặc nhóm tài nguyên, có thể tạo một dòng cha đại diện. Mọi transaction cần kiểm tra/chèn vào phạm vi đó đều khóa cùng dòng trước khi đọc:

~~~sql
-- Ví dụ PostgreSQL
BEGIN;

SELECT room_id
FROM room
WHERE room_id = 10
FOR UPDATE;

-- Kiểm tra lịch giao nhau.
-- Nếu không có lịch, INSERT booking.

COMMIT;
~~~

Với SQL Server có thể dùng UPDLOCK trên dòng Room trong transaction. Với InnoDB có thể dùng SELECT ... FOR UPDATE. Điểm quan trọng là tất cả đường ghi có thể tạo xung đột phải tuân thủ cùng giao thức.

Guard row đơn giản hóa việc tuần tự hóa theo một khóa nghiệp vụ, nhưng giảm concurrency: hai booking cho cùng phòng sẽ phải lần lượt kiểm tra. Nếu hệ thống có nhiều phòng độc lập, khóa riêng từng RoomId cho phép các phòng khác nhau xử lý song song.

## 9. Deadlock, blocking và serialization failure khác nhau ra sao?

Khi chèn vào khoảng đang được bảo vệ, ứng dụng có thể quan sát nhiều kết quả khác nhau:

- **Blocking:** INSERT phải chờ một transaction đang giữ khóa khoảng. Khi transaction đó kết thúc, INSERT có thể tiếp tục.
- **Deadlock:** hai hoặc nhiều transaction chờ nhau theo chu trình. Database chọn một transaction làm victim và rollback.
- **Serialization failure:** DBMS phát hiện lịch chạy có nguy cơ không thể tuần tự hóa và hủy transaction. Không nhất thiết có session nào đang chờ khóa.
- **Constraint violation:** transaction cố ghi dữ liệu vi phạm UNIQUE, exclusion hoặc constraint khác. Đây là lỗi dữ liệu/điều kiện ràng buộc, không nhất thiết là deadlock.

Ứng dụng phải phân loại lỗi để xử lý đúng:

| Kết quả | Xử lý thường gặp |
|---|---|
| Lock wait/blocking | Chờ trong timeout hợp lý; kiểm tra transaction giữ khóa |
| Deadlock victim | Rollback và retry toàn bộ transaction nếu thao tác an toàn |
| Serialization failure | Rollback và retry toàn bộ transaction trên snapshot mới |
| Unique/exclusion violation | Trả kết quả nghiệp vụ như tài nguyên đã được đặt; chỉ retry nếu có lý do cụ thể |

Không retry vô hạn. Nếu nhiều request cùng retry ngay lập tức, chúng có thể tiếp tục va chạm và tạo một đợt tải mới.

## 10. Chẩn đoán khóa khoảng và phạm vi predicate

### 10.1. SQL Server

Có thể xem các khóa hiện hành trong database:

~~~sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_description
FROM sys.dm_tran_locks
WHERE resource_database_id = DB_ID();
~~~

Khi điều tra key-range locking, chú ý resource type KEY và các request mode bắt đầu bằng Range. Ghép session đang chờ với session giữ khóa và execution plan của câu truy vấn.

Để biết INSERT có bị chặn bởi transaction nào, có thể xem:

~~~sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource,
    status
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
~~~

Các DMV là ảnh chụp tại thời điểm truy vấn. Nếu sự cố xảy ra ngắn, cần thu thập Extended Events hoặc log phù hợp.

### 10.2. MySQL InnoDB

Trong các phiên bản hỗ trợ Performance Schema data lock tables, có thể xem lock hiện tại:

~~~sql
SELECT
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks;
~~~

Để tìm quan hệ chờ giữa request và blocker, xem bảng data_lock_waits:

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Kết hợp với EXPLAIN để xác định index được dùng và vùng index scan. Khi có deadlock, xem thông tin từ InnoDB engine status hoặc log tương ứng.

### 10.3. PostgreSQL

Có thể xem dấu vết SIREAD:

~~~sql
SELECT
    pid,
    locktype,
    relation::regclass AS relation,
    page,
    tuple,
    mode,
    granted
FROM pg_locks
WHERE mode = 'SIReadLock';
~~~

SIREAD không phải khóa chặn INSERT. Nếu một transaction bị hủy với SQLSTATE 40001, cần xem log ứng dụng, các câu SELECT/INSERT/UPDATE của transaction và thứ tự thực thi để hiểu phụ thuộc rw. pg_locks không hiển thị một serialization graph hoàn chỉnh.

## 11. Quy trình thiết kế thao tác kiểm tra rồi chèn

Khi một nghiệp vụ cần kiểm tra khoảng trước khi INSERT, hãy làm rõ các bước:

1. **Xác định predicate.** Liệt kê đầy đủ điều kiện quyết định một dòng có thuộc khoảng hay không. Ví dụ RoomId, thời gian bắt đầu và kết thúc, trạng thái booking.
2. **Chọn cơ chế bảo vệ.** Dùng key-range lock, gap/next-key lock, SERIALIZABLE SSI, constraint hoặc guard row theo DBMS và invariant.
3. **Thiết kế index.** Chọn thứ tự cột hỗ trợ điều kiện lọc và kiểm tra execution plan. Tránh quét rộng không cần thiết.
4. **Đặt kiểm tra và INSERT trong cùng transaction.** Không kiểm tra trong một transaction rồi chèn ở transaction khác nếu không có cơ chế xác nhận lại.
5. **COMMIT sớm.** Không gọi mạng hoặc chờ người dùng trong lúc giữ range lock hay guard lock.
6. **Xử lý cạnh tranh.** Phân biệt blocking, deadlock, serialization failure và constraint violation.
7. **Retry đúng cách.** Nếu transaction bị hủy vì deadlock hoặc serialization failure, rollback rồi chạy lại toàn bộ logic kiểm tra và chèn.
8. **Bảo vệ mọi đường ghi.** API, worker, batch job và công cụ quản trị đều phải tuân thủ cùng invariant.

## 12. Những nguyên tắc cần ghi nhớ

- Phantom xuất hiện khi tập dòng thỏa một predicate thay đổi do INSERT hoặc UPDATE từ transaction khác.
- Khóa các dòng hiện có chưa chắc bảo vệ được khoảng trống nơi một dòng mới có thể xuất hiện.
- SQL Server SERIALIZABLE dùng key-range locks để ngăn chèn vào phạm vi được bảo vệ.
- InnoDB dùng gap/next-key locks trong locking read và thao tác range phù hợp; SELECT consistent read thông thường không tự khóa gap.
- PostgreSQL SERIALIZABLE dùng SIREAD và SSI để phát hiện phụ thuộc; INSERT có thể không bị block nhưng một transaction có thể bị hủy.
- Chỉ mục quyết định phạm vi index được quét và có ảnh hưởng đến phạm vi khóa hoặc predicate được theo dõi.
- REPEATABLE READ không có cùng ngữ nghĩa giữa các DBMS; cần kiểm tra tài liệu của sản phẩm cụ thể.
- Unique hoặc exclusion constraint là lựa chọn mạnh khi quy tắc có thể biểu diễn trực tiếp trong schema.
- Guard row giúp tuần tự hóa theo tài nguyên nghiệp vụ, đổi lại các thao tác cùng nhóm phải chờ nhau.
- Khi gặp deadlock hoặc serialization failure, retry toàn bộ transaction và đọc lại trạng thái hiện hành.

Chèn đồng thời vào một khoảng đang được kiểm tra là một bài toán về bảo vệ predicate, không chỉ là khóa những dòng đã tìm thấy. Chỉ mục giúp database xác định vùng dữ liệu liên quan; isolation level và cơ chế của DBMS quyết định transaction khác bị chặn, được phép tiếp tục hay phải thử lại để giữ quy tắc nghiệp vụ.

