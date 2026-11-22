# Đặt chỗ có giới hạn và tranh chấp trên tài nguyên dùng chung

Khi nhiều người cùng đặt một tài nguyên có số lượng giới hạn, database phải bảo đảm tổng số chỗ đã giữ hoặc đã xác nhận không vượt quá sức chứa. Tài nguyên có thể là ghế trong rạp, phòng họp, phòng khách sạn, vé sự kiện, khung giờ tư vấn, thiết bị dùng chung hoặc số lượng hàng trong kho.

Thách thức xuất hiện khi nhiều transaction cùng đọc một trạng thái còn chỗ, rồi đồng thời quyết định đặt chỗ. Nếu mỗi transaction chỉ kiểm tra bằng một câu SELECT thông thường và sau đó INSERT ở bước riêng, nhiều request có thể cùng nhìn thấy một chỗ trống cuối cùng và cùng xác nhận thành công. Kết quả là overselling hoặc overbooking.

Thiết kế cần bảo vệ một **invariant về sức chứa** tại database: tổng lượng tài nguyên đã được giữ hợp lệ và đã xác nhận luôn nằm trong giới hạn. Cách thường dùng là cập nhật có điều kiện trong một câu lệnh nguyên tử, khóa một dòng đại diện cho tài nguyên, dùng constraint phù hợp hoặc chọn isolation level đủ mạnh. Với quy trình cần chờ thanh toán hay người dùng, hãy lưu reservation có thời hạn và kết thúc transaction trước khi chờ.

## 1. Bài toán sức chứa và invariant

Giả sử một sự kiện có sức chứa 100 vé. Hệ thống đã xác nhận 98 vé và còn 2 vé. Hai request đến gần như đồng thời, mỗi request muốn mua 2 vé.

Nếu cả hai request đều đọc Available = 2 trước khi có transaction nào ghi thay đổi, mỗi request có thể tự kết luận rằng còn đủ chỗ:

~~~text
Trạng thái ban đầu: Available = 2

Request A                         Request B
---------                         ---------
Đọc Available = 2
                                  Đọc Available = 2
Kiểm tra: đủ 2 vé
                                  Kiểm tra: đủ 2 vé
Ghi đặt 2 vé
                                  Ghi đặt 2 vé
COMMIT
                                  COMMIT

Kết quả sai nếu cả hai cùng được chấp nhận:
Đã đặt thêm 4 vé trong khi chỉ còn 2 vé.
~~~

Đây là race condition kiểu check-then-act: thao tác kiểm tra và thao tác thay đổi dữ liệu không được phối hợp như một đơn vị nguyên tử.

Có thể mô hình hóa sức chứa bằng các đại lượng:

- Capacity: tổng sức chứa của tài nguyên.
- Confirmed: số lượng đã xác nhận.
- Held: số lượng đang được giữ tạm thời, chưa hết hạn.
- Available: lượng còn có thể phân bổ.

Một invariant phổ biến là tổng Confirmed và Held không vượt quá Capacity. Nếu database lưu Available trực tiếp, invariant tương ứng là Available phải nằm trong khoảng từ 0 đến Capacity.

Điều quan trọng là định nghĩa rõ reservation nào chiếm chỗ. Ví dụ, trạng thái HELD còn hạn và CONFIRMED đều tiêu thụ sức chứa; EXPIRED, CANCELLED và REJECTED thì không. Nếu quy tắc trạng thái không rõ ràng, các transaction có thể tính sức chứa khác nhau.

### 1.1. Sức chứa theo tổng số và sức chứa theo từng đơn vị

Có hai kiểu tài nguyên thường gặp:

**Tài nguyên theo số lượng:** sự kiện có 100 vé cùng loại, kho có 50 sản phẩm, một dịch vụ có 8 nhân viên có thể nhận lịch. Hệ thống cần kiểm soát tổng số đã phân bổ.

**Tài nguyên có đơn vị cụ thể:** rạp có ghế A1, A2; phòng có các khung giờ; thiết bị có serial number. Mỗi đơn vị chỉ được gán cho tối đa một reservation hợp lệ tại một thời điểm.

Kiểu thứ nhất phù hợp với một dòng capacity counter được cập nhật nguyên tử. Kiểu thứ hai thường cần khóa duy nhất hoặc constraint trên từng đơn vị, kết hợp với quy tắc thời gian nếu đơn vị được đặt theo khoảng.

## 2. Cập nhật có điều kiện trong một câu lệnh

Với tài nguyên theo số lượng, cách trực tiếp thường là để database kiểm tra sức chứa ngay trong câu UPDATE. Không đọc Available trước rồi gửi một giá trị tuyệt đối đã tính ở ứng dụng.

Giả sử bảng ResourceCapacity có các cột ResourceId, Capacity và Reserved. Có thể thêm constraint:

~~~sql
ALTER TABLE dbo.ResourceCapacity
ADD CONSTRAINT CK_ResourceCapacity_Valid
CHECK
(
    Capacity >= 0
    AND Reserved >= 0
    AND Reserved <= Capacity
);
~~~

Khi muốn giữ thêm một số lượng, thực hiện:

~~~sql
UPDATE dbo.ResourceCapacity
SET Reserved = Reserved + @quantity
WHERE ResourceId = @resourceId
  AND @quantity > 0
  AND Reserved <= Capacity - @quantity;
~~~

Sau câu lệnh, kiểm tra số dòng bị ảnh hưởng:

- Một dòng được cập nhật: database đã chấp nhận giữ chỗ.
- Không có dòng nào được cập nhật: tài nguyên không tồn tại, số lượng yêu cầu không hợp lệ hoặc sức chứa còn lại không đủ.

Điều kiện và phép tăng được thực hiện trong cùng câu lệnh. Khi hai transaction cùng cập nhật một dòng capacity, database phối hợp quyền ghi trên dòng đó. Transaction thứ hai phải đánh giá điều kiện với trạng thái hiện hành sau khi transaction cạnh tranh nhả khóa hoặc hoàn tất. Nó không thể cùng dùng một giá trị Available cũ để vượt qua điều kiện một cách độc lập.

Điều kiện Reserved <= Capacity - @quantity cũng tránh phép cộng có thể vượt giới hạn số nguyên trước khi so sánh. Cần kiểm tra @quantity dương và kiểu dữ liệu đủ lớn cho quy mô sức chứa.

### 2.1. Ghi reservation cùng transaction

Chỉ tăng Reserved mà không tạo reservation tương ứng sẽ khiến hệ thống khó biết ai đang giữ chỗ, khi nào hết hạn và cần giải phóng bao nhiêu. Vì vậy, thay đổi capacity và INSERT reservation phải nằm trong cùng transaction:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.ResourceCapacity
SET Reserved = Reserved + @quantity
WHERE ResourceId = @resourceId
  AND @quantity > 0
  AND Reserved <= Capacity - @quantity;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Not enough capacity or invalid request.', 1;
END;

INSERT INTO dbo.Reservation
    (ReservationId, ResourceId, Quantity, Status, ExpiresAt)
VALUES
    (@reservationId, @resourceId, @quantity, 'HELD',
     DATEADD(minute, 10, SYSUTCDATETIME()));

COMMIT TRANSACTION;
~~~

Nếu INSERT reservation thất bại, transaction rollback cả phần tăng Reserved. Nếu UPDATE không tìm được dòng capacity phù hợp, không tạo reservation. Nhờ vậy, hai phần dữ liệu không bị lệch nhau do một nửa thao tác thành công.

Ví dụ dùng cú pháp SQL Server. Với PostgreSQL, có thể dùng UPDATE ... RETURNING để xác nhận dòng capacity đã được cập nhật. Với MySQL InnoDB, dùng UPDATE trong transaction rồi kiểm tra ROW_COUNT() trên cùng connection. Cú pháp cụ thể khác nhau nhưng nguyên tắc là cập nhật có điều kiện và ghi reservation trong cùng transaction.

### 2.2. PostgreSQL với RETURNING

Một phiên bản minh họa trên PostgreSQL:

~~~sql
BEGIN;

UPDATE resource_capacity
SET reserved = reserved + $2
WHERE resource_id = $1
  AND $2 > 0
  AND reserved <= capacity - $2
RETURNING resource_id;

-- Chỉ khi UPDATE trả về một dòng:
-- INSERT reservation với trạng thái HELD.

COMMIT;
~~~

Ứng dụng hoặc stored procedure phải kiểm tra kết quả RETURNING. Nếu không có dòng trả về, không được INSERT reservation. Nếu INSERT thất bại, rollback transaction để phần tăng reserved cũng bị hoàn tác.

### 2.3. Vì sao UPDATE nguyên tử thường tốt hơn SELECT rồi UPDATE?

Mẫu dễ gây lỗi:

~~~sql
SELECT Capacity - Reserved AS Available
FROM ResourceCapacity
WHERE ResourceId = @resourceId;

-- Ứng dụng kiểm tra Available >= @quantity.

UPDATE ResourceCapacity
SET Reserved = @newReserved
WHERE ResourceId = @resourceId;
~~~

Giữa SELECT và UPDATE, transaction khác có thể thay đổi Reserved. Giá trị @newReserved được tính từ một trạng thái đã cũ.

Mẫu UPDATE có điều kiện gộp việc kiểm tra và thay đổi:

~~~sql
UPDATE ResourceCapacity
SET Reserved = Reserved + @quantity
WHERE ResourceId = @resourceId
  AND Reserved + @quantity <= Capacity;
~~~

Database kiểm tra điều kiện cùng lúc với việc lấy quyền cập nhật dòng. Với nghiệp vụ chỉ phụ thuộc một dòng capacity, cách này thường đơn giản và hiệu quả hơn việc tự điều phối nhiều bước đọc/ghi.

## 3. Khóa dòng đại diện hoặc guard row

Một cách khác là khóa dòng đại diện cho tài nguyên trước khi đọc số lượng còn lại. Dòng này được gọi là guard row hoặc resource row. Tất cả transaction đặt chỗ cho cùng tài nguyên phải tuân theo cùng giao thức.

Ví dụ PostgreSQL:

~~~sql
BEGIN;

SELECT capacity, reserved
FROM resource_capacity
WHERE resource_id = 42
FOR UPDATE;

-- Kiểm tra capacity - reserved >= requested.
-- Nếu đủ, tăng reserved và INSERT reservation.

COMMIT;
~~~

SELECT ... FOR UPDATE khóa dòng capacity để transaction khác muốn khóa hoặc cập nhật cùng dòng phải chờ. Sau khi lấy được khóa, transaction đọc trạng thái đã được phối hợp, kiểm tra sức chứa và ghi reservation.

SQL Server có thể dùng UPDLOCK trên dòng ResourceCapacity; InnoDB có thể dùng SELECT ... FOR UPDATE. Isolation level và cú pháp khác nhau, nhưng dòng guard tạo một điểm phối hợp rõ ràng cho các thao tác cùng tài nguyên.

### 3.1. Guard row phải được mọi writer sử dụng

Guard row chỉ bảo vệ invariant nếu mọi đường ghi liên quan đều khóa cùng dòng trước khi kiểm tra và thay đổi dữ liệu.

Nếu API đặt vé khóa ResourceCapacity nhưng một batch job khác INSERT reservation trực tiếp mà không cập nhật hoặc khóa dòng capacity, invariant vẫn có thể bị phá vỡ.

Cần áp dụng giao thức cho:

- API đặt chỗ.
- Worker xử lý reservation hết hạn.
- Luồng xác nhận hoặc hủy.
- Công cụ quản trị thay đổi sức chứa.
- Batch import hoặc đồng bộ từ hệ thống ngoài.
- Tác vụ sửa dữ liệu hoặc hoàn vé.

Một guard row không phải rào chắn tự động cho mọi bảng liên quan. Nó là một giao thức mà tất cả writer phải tuân thủ; constraint và quyền truy cập database có thể giúp ngăn các đường ghi bỏ qua giao thức.

### 3.2. Phạm vi khóa và mức đồng thời

Nếu mỗi sự kiện có một dòng capacity riêng, các request đặt vé cho cùng sự kiện phải phối hợp trên cùng dòng. Nhưng request của sự kiện khác có thể cập nhật dòng khác và tiếp tục song song.

~~~text
ResourceCapacity
  Event 10: một dòng guard
  Event 11: một dòng guard
  Room 20: một dòng guard
  Room 21: một dòng guard

Request cùng Event 10 -> phối hợp với nhau
Request Event 10 và Event 11 -> có thể chạy song song
~~~

Đây là lý do nên khóa theo tài nguyên nghiệp vụ nhỏ nhất có thể: ResourceId, EventId, RoomId hoặc một khóa tương ứng. Nếu khóa một dòng tổng hợp cho toàn bộ hệ thống, mọi request có thể bị dồn vào một điểm tranh chấp.

## 4. Dùng constraint để bảo vệ sức chứa

Constraint là lớp bảo vệ ở database, giúp mọi luồng ghi phải tuân thủ những quy tắc có thể biểu diễn trực tiếp trong schema.

### 4.1. CHECK constraint trên một dòng capacity

Với bảng lưu Capacity và Reserved cùng một dòng, CHECK có thể bảo vệ:

~~~sql
CHECK
(
    Capacity >= 0
    AND Reserved >= 0
    AND Reserved <= Capacity
)
~~~

Constraint này ngăn một câu lệnh ghi trạng thái vượt sức chứa vào dòng capacity.

Tuy nhiên, CHECK trên ResourceCapacity không tự đối chiếu tổng Quantity của toàn bộ Reservation nếu ứng dụng lưu capacity và reservation ở hai bảng riêng. Một CHECK thông thường không tính SUM trên bảng khác. Cần duy trì counter trong cùng transaction, dùng trigger được thiết kế đúng hoặc mô hình dữ liệu khác.

### 4.2. UNIQUE constraint cho từng ghế hoặc từng đơn vị

Nếu mỗi ghế chỉ được có một reservation hoạt động, có thể mô hình hóa mỗi ghế thành một dòng và bảo vệ bằng unique key.

Ví dụ đơn giản khi một ghế chỉ có một bản ghi phân bổ trong một sự kiện:

~~~sql
CREATE TABLE SeatAllocation
(
    EventId bigint NOT NULL,
    SeatNo varchar(20) NOT NULL,
    ReservationId bigint NOT NULL,
    PRIMARY KEY (EventId, SeatNo)
);
~~~

Hai transaction cùng INSERT ghế A10 cho cùng sự kiện không thể cùng commit vì khóa chính không cho phép trùng.

Nếu cần giữ lịch sử các reservation đã hủy, không thể dùng unique key trên toàn bộ lịch sử theo cách trên mà vẫn cho đặt lại ghế. Khi đó có thể tách bảng ghế hiện tại khỏi lịch sử, hoặc dùng filtered/partial unique index theo trạng thái hoạt động ở DBMS hỗ trợ.

### 4.3. Khoảng thời gian không được giao nhau

Với phòng hoặc tài nguyên được đặt theo khoảng thời gian, invariant có dạng: hai reservation đang hoạt động của cùng tài nguyên không được overlap.

Một UNIQUE(ResourceId, StartTime) không đủ để bảo vệ vì hai khoảng có StartTime khác nhau vẫn có thể giao nhau. PostgreSQL hỗ trợ exclusion constraint với range type để biểu diễn quy tắc này:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking
(
    booking_id bigint PRIMARY KEY,
    room_id integer NOT NULL,
    during tstzrange NOT NULL,
    status text NOT NULL,
    EXCLUDE USING gist
    (
        room_id WITH =,
        during WITH &&
    )
    WHERE (status IN ('HELD', 'CONFIRMED'))
);
~~~

Toán tử && kiểm tra hai khoảng có giao nhau hay không. Constraint này minh họa cách bảo vệ các booking đang hoạt động trong PostgreSQL. Với schema thực tế, cần xác định chính xác ranh giới khoảng, ví dụ start-inclusive và end-exclusive, và cách chuyển trạng thái khi reservation hết hạn.

DBMS khác có thể cần SERIALIZABLE, key-range lock, gap/next-key lock hoặc guard row theo ResourceId. Constraint phù hợp là lựa chọn mạnh vì nó bảo vệ dữ liệu ở nơi ghi, nhưng phải đúng với mô hình nghiệp vụ.

## 5. Optimistic concurrency và version check

Với tài nguyên có mức cạnh tranh thấp, có thể dùng version để phát hiện một request đang cập nhật trạng thái cũ.

Giả sử ResourceCapacity có cột Version. Ứng dụng đọc:

~~~text
ResourceId = 42
Capacity   = 20
Reserved   = 17
Version    = 8
~~~

Khi đặt 2 chỗ, câu UPDATE chỉ thành công nếu version vẫn là 8 và sức chứa vẫn đủ:

~~~sql
UPDATE ResourceCapacity
SET Reserved = Reserved + @quantity,
    Version = Version + 1
WHERE ResourceId = @resourceId
  AND Version = @versionRead
  AND @quantity > 0
  AND Reserved <= Capacity - @quantity;
~~~

Nếu không có dòng nào được cập nhật, request phải tải lại trạng thái và quyết định lại. Có thể tài nguyên đã hết chỗ hoặc một request khác vừa cập nhật version.

Version check tránh ghi đè trạng thái cũ. Nhưng khi nhiều request cùng tranh chấp một capacity row, một số request sẽ thất bại và phải retry. Với điểm nóng có nhiều request, atomic conditional UPDATE hoặc khóa dòng thường dễ tận dụng hơn vì database tự phối hợp cập nhật.

Optimistic concurrency không tự bảo vệ invariant trải qua nhiều dòng nếu các request sửa các dòng khác nhau. Khi quy tắc liên quan tổng số reservation, cần một counter/guard row, SERIALIZABLE, constraint phù hợp hoặc một cơ chế khác bảo vệ toàn bộ phạm vi.

## 6. Reservation có thời hạn: giữ chỗ mà không giữ transaction

Trong nhiều quy trình, người dùng cần một khoảng thời gian để nhập thông tin hoặc thanh toán. Không nên mở transaction và giữ khóa trong suốt thời gian đó.

Hãy tạo reservation có thời hạn với trạng thái rõ ràng:

~~~text
AVAILABLE
    |
    | giữ chỗ thành công
    v
HELD
    | \
    |  \ thanh toán thất bại hoặc hết hạn
    |   \
    |    v
    |  EXPIRED / RELEASED
    |
    | thanh toán thành công
    v
CONFIRMED
    |
    | hủy theo chính sách
    v
CANCELLED
~~~

Một transaction ngắn thực hiện:

1. Kiểm tra và giữ capacity.
2. Tạo reservation ở trạng thái HELD.
3. Ghi thời điểm hết hạn.
4. COMMIT.

Sau COMMIT, người dùng có thể thanh toán trong khi database không còn giữ khóa của transaction đặt chỗ. Nếu thanh toán thành công, một transaction khác chuyển HELD sang CONFIRMED. Nếu người dùng không hoàn tất trước thời hạn, worker giải phóng reservation.

Ví dụ giữ chỗ 10 phút:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.ResourceCapacity
SET Reserved = Reserved + @quantity
WHERE ResourceId = @resourceId
  AND @quantity > 0
  AND Reserved <= Capacity - @quantity;

IF @@ROWCOUNT = 0
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50002, 'Resource is full.', 1;
END;

INSERT INTO dbo.Reservation
    (ReservationId, ResourceId, Quantity, Status, ExpiresAt)
VALUES
    (@reservationId, @resourceId, @quantity, 'HELD',
     DATEADD(minute, 10, SYSUTCDATETIME()));

COMMIT TRANSACTION;
~~~

Không có khóa database nào cần được giữ trong 10 phút. Trạng thái HELD và ExpiresAt là thông tin bền vững để các transaction sau kiểm tra.

### 6.1. Xác nhận reservation bằng chuyển trạng thái có điều kiện

Khi thanh toán thành công, chỉ xác nhận reservation còn HELD và chưa hết hạn:

~~~sql
UPDATE dbo.Reservation
SET Status = 'CONFIRMED',
    ConfirmedAt = SYSUTCDATETIME()
WHERE ReservationId = @reservationId
  AND Status = 'HELD'
  AND ExpiresAt > SYSUTCDATETIME();
~~~

Ứng dụng kiểm tra số dòng bị ảnh hưởng:

- Một dòng: reservation đã chuyển sang CONFIRMED.
- Không có dòng: reservation đã hết hạn, đã được xử lý hoặc không tồn tại.

Việc chuyển trạng thái cần nằm trong transaction cùng các thay đổi liên quan. Nếu phải cập nhật capacity counter, bảo đảm quy tắc đếm không bị cộng/trừ hai lần.

### 6.2. Giải phóng reservation hết hạn đúng một lần

Một worker có thể tìm reservation HELD đã quá hạn. Nhưng nhiều worker có thể cùng nhìn thấy một reservation. Vì vậy, thao tác giải phóng phải là chuyển trạng thái có điều kiện và chỉ điều chỉnh capacity nếu transaction thực sự chuyển được trạng thái.

Mẫu SQL Server minh họa:

~~~sql
BEGIN TRANSACTION;

DECLARE @released TABLE
(
    ResourceId bigint,
    Quantity int
);

UPDATE dbo.Reservation
SET Status = 'EXPIRED'
OUTPUT DELETED.ResourceId, DELETED.Quantity
INTO @released
WHERE ReservationId = @reservationId
  AND Status = 'HELD'
  AND ExpiresAt <= SYSUTCDATETIME();

UPDATE rc
SET rc.Reserved = rc.Reserved - r.Quantity
FROM dbo.ResourceCapacity AS rc
JOIN @released AS r
  ON r.ResourceId = rc.ResourceId;

COMMIT TRANSACTION;
~~~

Nếu reservation đã được CONFIRMED hoặc worker khác đã chuyển sang EXPIRED, UPDATE đầu tiên không trả dòng nào. Khi đó @released rỗng và capacity không bị giảm lần thứ hai.

Trong triển khai thật, cần xử lý trường hợp một batch giải phóng nhiều reservation, khóa các dòng theo thứ tự ổn định và bảo đảm Reserved không âm. Có thể thêm CHECK constraint để phát hiện sai lệch.

### 6.3. Race giữa xác nhận và hết hạn

Có thể xảy ra tình huống worker hết hạn và callback thanh toán đến gần như đồng thời:

- Worker muốn chuyển HELD sang EXPIRED.
- Callback muốn chuyển HELD sang CONFIRMED.

Cả hai phải dùng UPDATE có điều kiện trên cùng reservation row. Chỉ một transaction có thể chuyển trạng thái từ HELD thành công; transaction còn lại sau khi chờ sẽ thấy trạng thái đã đổi và không cập nhật được dòng.

Quy tắc thời gian phải được định nghĩa rõ: reservation có còn hợp lệ nếu callback đến đúng thời điểm ExpiresAt hay không? Ví dụ trên dùng điều kiện xác nhận ExpiresAt lớn hơn thời gian database hiện tại và hết hạn khi ExpiresAt nhỏ hơn hoặc bằng thời gian hiện tại. Dùng đồng hồ database giúp các application instance không tự quyết định theo đồng hồ lệch nhau.

Nếu provider đã thu tiền nhưng reservation đã hết hạn trước khi callback được ghi nhận, cần quy trình nghiệp vụ bù trừ như hoàn tiền hoặc cấp reservation mới nếu còn chỗ. Không tự chuyển EXPIRED trở lại CONFIRMED mà không kiểm tra capacity hiện hành.

## 7. Idempotency khi request đặt chỗ được gửi nhiều lần

Người dùng có thể nhấn nút nhiều lần, trình duyệt retry sau timeout hoặc gateway gửi lại cùng request. Nếu mỗi lần tạo một ReservationId mới, một ý định đặt chỗ có thể chiếm nhiều capacity.

Dùng một idempotency key ổn định cho một ý định đặt chỗ và đặt unique constraint:

~~~sql
CREATE TABLE dbo.Reservation
(
    ReservationId bigint NOT NULL PRIMARY KEY,
    IdempotencyKey varchar(100) NOT NULL UNIQUE,
    ResourceId bigint NOT NULL,
    Quantity int NOT NULL,
    Status varchar(20) NOT NULL,
    ExpiresAt datetime2 NOT NULL
);
~~~

Khi nhận request:

1. Tìm reservation theo IdempotencyKey.
2. Nếu đã có, trả trạng thái hoặc kết quả hiện tại của reservation đó.
3. Nếu chưa có, thực hiện cập nhật capacity và INSERT reservation trong cùng transaction.
4. Nếu hai request đồng thời cùng key, unique constraint chỉ cho một bản ghi. Transaction thua cuộc phải rollback phần tăng capacity rồi đọc lại kết quả đã được tạo.

Key phải đại diện cho cùng một ý định nghiệp vụ qua mọi lần retry. Nếu người dùng thực sự muốn đặt thêm một lần mới, request đó cần key mới.

Idempotency key không thay thế kiểm tra sức chứa. Nó ngăn cùng một ý định bị thực hiện nhiều lần; atomic capacity update vẫn cần ngăn các ý định khác nhau cùng vượt sức chứa.

## 8. Khi nào dùng SERIALIZABLE hoặc khóa khoảng?

Một số invariant không thể bảo vệ chỉ bằng một dòng counter. Ví dụ, một phòng không được có hai booking giao nhau theo thời gian, hoặc một nhóm tài nguyên phải luôn có ít nhất một thành viên khả dụng.

Các lựa chọn phụ thuộc DBMS:

| DBMS | Cơ chế có thể dùng |
|---|---|
| SQL Server | SERIALIZABLE với key-range locks; UPDLOCK/HOLDLOCK cho check-then-insert; guard row |
| PostgreSQL | SERIALIZABLE với SSI và retry SQLSTATE 40001; exclusion constraint cho một số quy tắc khoảng; guard row |
| MySQL InnoDB | Locking read FOR UPDATE với gap/next-key locks trong phạm vi phù hợp; guard row; constraint |
| Oracle | SERIALIZABLE hoặc SELECT FOR UPDATE; constraint và thiết kế dữ liệu phù hợp |

SERIALIZABLE giúp bảo vệ các điều kiện liên quan đến nhiều dòng hoặc predicate, nhưng có thể tạo blocking hoặc serialization failure. Ứng dụng phải rollback và retry toàn bộ transaction khi DBMS yêu cầu.

Không nên mặc định REPEATABLE READ luôn bảo vệ phantom theo cùng cách trên mọi DBMS. Cần kiểm tra đúng semantics của sản phẩm, isolation level, index và câu lệnh.

Nếu chỉ cần giữ một lượng trong một dòng capacity, atomic conditional UPDATE thường dễ hiểu và ít tốn công hơn việc dùng SERIALIZABLE cho toàn bộ transaction. Dùng cơ chế mạnh hơn khi invariant thực sự trải qua nhiều dòng hoặc khoảng dữ liệu.

## 9. Tranh chấp trên tài nguyên nóng (hot resource)

Một sự kiện nổi tiếng, một phòng duy nhất hoặc một sản phẩm sắp hết hàng có thể nhận hàng nghìn request cùng lúc. Tất cả request phải phối hợp trên cùng một capacity row hoặc guard row. Đây là hot resource.

Khi contention cao:

- Nhiều transaction xếp hàng chờ cùng một khóa.
- Latency tăng dù câu UPDATE rất ngắn.
- Connection pool có thể đầy vì connection đang chờ khóa.
- Retry đồng loạt có thể tạo thêm tải.
- Worker hết hạn và request đặt chỗ có thể tranh chấp cùng dòng.
- Một counter tập trung có thể giới hạn throughput của toàn bộ tài nguyên.

### 9.1. Giảm phạm vi tranh chấp

**Tách counter theo tài nguyên.** Mỗi EventId hoặc ResourceId có dòng capacity riêng. Các tài nguyên độc lập có thể xử lý song song.

**Giữ transaction ngắn.** Chỉ thực hiện kiểm tra và cập nhật cần thiết trong transaction. Không gọi payment gateway hoặc chờ người dùng khi đang giữ khóa.

**Đặt index đúng.** Index trên ResourceId, ReservationId, Status và ExpiresAt có thể giúp truy vấn tìm reservation nhanh hơn. Index không loại bỏ xung đột trên cùng một dòng capacity, nhưng giảm thời gian transaction giữ khóa cho các bước phụ.

**Dùng hàng đợi cho điểm nóng.** Với tài nguyên có lưu lượng cực cao, có thể đưa request vào queue và xử lý theo một consumer hoặc một nhóm partition theo ResourceId. Hàng đợi giúp kiểm soát tốc độ và thứ tự xử lý, nhưng database vẫn phải kiểm tra capacity cuối cùng vì message có thể trùng, đến muộn hoặc được xử lý lại.

**Áp dụng admission control.** Giới hạn số request đồng thời cho một resource key, trả trạng thái đang chờ hoặc từ chối sớm khi hệ thống quá tải. Điều này giúp giảm số session cùng tranh chấp một khóa.

**Không retry tức thì vô hạn.** Dùng giới hạn retry, backoff và jitter cho lỗi deadlock hoặc serialization failure. Nếu một tài nguyên luôn nóng, cần thay đổi thiết kế hoặc điều tiết tải.

### 9.2. Chia nhỏ counter có được không?

Có thể chia sức chứa thành các bucket hoặc shard để giảm contention, nhưng phải bảo đảm tổng phân bổ không vượt tổng capacity.

Ví dụ, chia 100 vé thành 10 bucket, mỗi bucket có capacity 10. Request chọn một bucket và cập nhật counter của bucket đó. Nếu mỗi bucket có giới hạn riêng, tổng sức chứa tối đa vẫn là 100.

Đổi lại, một bucket có thể hết chỗ trong khi bucket khác còn chỗ. Có thể thử bucket khác, nhưng việc phân bổ và retry phức tạp hơn. Nếu capacity không chia đều hoặc cần tối ưu phân phối, phải có chiến lược chọn bucket và quy tắc tổng hợp rõ ràng.

Không thể chỉ nhân bản counter thành nhiều bản ghi rồi để mọi request tự tăng một bản bất kỳ mà không kiểm soát tổng. Làm vậy sẽ biến một điểm tranh chấp thành nguy cơ oversell.

## 10. Không giữ khóa trong lúc chờ thanh toán hoặc dịch vụ ngoài

Một luồng đặt chỗ có thể cần thanh toán trước khi xác nhận. Không nên giữ transaction mở từ lúc khóa capacity đến khi payment provider phản hồi.

Thiết kế phù hợp hơn:

~~~text
Transaction A — tạo reservation
  BEGIN
    Cập nhật capacity có điều kiện
    INSERT Reservation(status=HELD, expires_at=...)
    INSERT Outbox(PaymentRequested) nếu dùng worker
  COMMIT

Bên ngoài transaction
  Gọi payment provider với idempotency key
  Chờ phản hồi hoặc xử lý callback

Transaction B — hoàn tất
  BEGIN
    Kiểm tra Reservation vẫn HELD và chưa hết hạn
    Ghi PaymentAttempt result
    Chuyển Reservation sang CONFIRMED
  COMMIT

Nếu thất bại hoặc hết hạn
  Transaction C giải phóng reservation đúng một lần
~~~

Nếu dùng Outbox, worker đọc sự kiện và gọi provider sau khi transaction A commit. Consumer hoặc callback phải idempotent vì sự kiện có thể được gửi lại.

Một timeout từ payment provider không chứng minh thanh toán thất bại. Provider có thể đã thu tiền nhưng response bị mất. Hãy tra cứu giao dịch bằng idempotency key trước khi gửi lại hoặc giải phóng reservation. Nếu đã thu tiền nhưng chỗ không còn hợp lệ, quy trình phải có hành động bù trừ như hoàn tiền.

## 11. Các lỗi và cách xử lý

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Hai request cùng lấy chỗ cuối | Check-then-act không nguyên tử | Atomic conditional UPDATE, khóa guard row hoặc constraint |
| Capacity bị âm hoặc Reserved lớn hơn Capacity | Một đường ghi bỏ qua giao thức hoặc cập nhật sai | CHECK constraint, cập nhật cùng transaction và rà soát mọi writer |
| Reservation hết hạn nhưng capacity không được trả lại | Worker lỗi hoặc chuyển trạng thái và counter không cùng transaction | Giải phóng trạng thái và capacity trong cùng transaction; retry idempotent |
| Capacity được cộng lại hai lần | Nhiều worker cùng giải phóng một reservation | Chuyển trạng thái có điều kiện; chỉ cộng khi một dòng thực sự đổi trạng thái |
| Thanh toán thành công nhưng reservation đã hết hạn | Callback đến muộn hoặc timeout không xác định | Tra cứu provider, kiểm tra capacity và thực hiện xác nhận hoặc bù trừ |
| Request retry tạo nhiều reservation | Không có idempotency key ổn định | Unique idempotency key và đọc lại kết quả cũ |
| Nhiều request chờ cùng một dòng | Hot resource và contention cao | Queue/admission control, transaction ngắn, phân vùng theo resource key |
| Deadlock giữa confirm và expire | Hai luồng khóa nhiều dòng theo thứ tự khác nhau | Chuẩn hóa thứ tự khóa, giữ transaction ngắn và retry toàn bộ transaction |

## 12. Theo dõi sức chứa và contention

Để biết hệ thống có đang bảo vệ invariant đúng và chịu tải tốt hay không, cần theo dõi cả dữ liệu nghiệp vụ lẫn trạng thái database.

Các chỉ số nghiệp vụ:

- Capacity, Confirmed, Held và Available theo ResourceId.
- Số reservation đang HELD và tuổi reservation lâu nhất.
- Số reservation hết hạn nhưng chưa được giải phóng.
- Tỷ lệ request thành công, hết chỗ và bị từ chối.
- Số request trùng được xử lý bằng idempotency key.
- Số lần thanh toán thành công nhưng reservation không được xác nhận.
- Chênh lệch giữa counter và tổng reservation đang hoạt động.

Các chỉ số đồng thời:

- Lock wait duration và số session bị block.
- Deadlock và serialization failure.
- Thời gian transaction mở.
- Số lần retry và tỷ lệ retry thành công.
- Throughput theo ResourceId.
- Connection pool đang hoạt động, đang chờ và đã sử dụng tối đa.
- Thời gian xử lý queue và số message tồn đọng.

Có thể dùng truy vấn tổng hợp để đối chiếu counter với reservation:

~~~sql
SELECT
    rc.ResourceId,
    rc.Capacity,
    rc.Reserved,
    COALESCE(SUM(
        CASE
            WHEN r.Status IN ('HELD', 'CONFIRMED')
             AND (r.Status = 'CONFIRMED' OR r.ExpiresAt > SYSUTCDATETIME())
            THEN r.Quantity
            ELSE 0
        END
    ), 0) AS CalculatedReserved
FROM dbo.ResourceCapacity AS rc
LEFT JOIN dbo.Reservation AS r
    ON r.ResourceId = rc.ResourceId
GROUP BY
    rc.ResourceId,
    rc.Capacity,
    rc.Reserved;
~~~

Đây là ví dụ SQL Server để kiểm tra chênh lệch; cần điều chỉnh theo chính sách reservation và trạng thái của ứng dụng. Nếu CONFIRMED không có ExpiresAt hoặc schema lưu thời gian khác, hãy sửa biểu thức cho phù hợp. Truy vấn đối chiếu nên chạy như công cụ giám sát hoặc reconciliation, không thay thế cơ chế cập nhật nguyên tử khi đặt chỗ.

## 13. Quy trình thiết kế một thao tác đặt chỗ

Khi xây dựng tính năng đặt chỗ có giới hạn, hãy xác định tuần tự:

1. **Định nghĩa invariant.** Xác định trạng thái nào chiếm capacity, đơn vị đo là gì và giới hạn áp dụng theo tài nguyên nào.
2. **Chọn mô hình dữ liệu.** Dùng capacity counter cho số lượng; dùng từng slot/seat và unique constraint cho đơn vị cụ thể; dùng range constraint hoặc khóa khoảng cho booking theo thời gian.
3. **Chọn cơ chế đồng thời.** Ưu tiên atomic conditional UPDATE khi invariant nằm trên một dòng; dùng guard row, SERIALIZABLE hoặc constraint khi cần bảo vệ nhiều dòng hay predicate.
4. **Tạo reservation trong cùng transaction.** Không cập nhật counter rồi tạo reservation ở một transaction khác.
5. **Đặt idempotency key.** Một ý định đặt chỗ chỉ tạo một reservation, kể cả khi request được gửi lại.
6. **COMMIT trước khi chờ.** Dùng trạng thái HELD và thời hạn thay vì giữ transaction mở trong lúc thanh toán.
7. **Chuyển trạng thái có điều kiện.** Confirm, expire, cancel và release phải chỉ thành công khi trạng thái hiện tại cho phép.
8. **Bảo đảm giải phóng đúng một lần.** Cập nhật reservation và capacity trong cùng transaction.
9. **Xử lý lỗi và retry.** Phân biệt hết chỗ, duplicate request, deadlock, serialization failure, timeout và kết quả thanh toán chưa xác định.
10. **Đối chiếu và quan sát.** Theo dõi capacity counter, reservation hoạt động, lock wait và retry để phát hiện sai lệch.

## 14. Những nguyên tắc cần ghi nhớ

- Đặt chỗ có giới hạn phải bảo vệ invariant tổng số đã giữ và xác nhận không vượt sức chứa.
- SELECT kiểm tra còn chỗ rồi INSERT riêng rẽ có thể tạo race condition và overbooking.
- Atomic conditional UPDATE gộp kiểm tra và tăng số lượng trong một câu lệnh; kiểm tra số dòng bị ảnh hưởng để biết có giữ được chỗ hay không.
- Cập nhật capacity và tạo reservation phải nằm trong cùng transaction.
- Guard row giúp các request cùng tài nguyên phối hợp; mọi đường ghi phải tuân thủ cùng giao thức.
- CHECK, UNIQUE và exclusion constraint bảo vệ những quy tắc có thể biểu diễn trực tiếp trong schema.
- Version check phát hiện dữ liệu cũ nhưng không tự bảo vệ invariant trải qua nhiều dòng.
- Reservation HELD có thời hạn cho phép ứng dụng chờ thanh toán mà không giữ transaction database mở.
- Confirm và expire phải là chuyển trạng thái có điều kiện; chỉ một luồng được phép giải phóng capacity.
- Idempotency key ngăn một request retry tạo nhiều reservation; nó không thay thế kiểm tra capacity.
- Hot resource có thể gây blocking và giảm throughput; dùng transaction ngắn, queue, admission control hoặc phân vùng theo resource key khi phù hợp.
- Khi thanh toán có kết quả không xác định, tra cứu provider bằng idempotency key trước khi retry hoặc giải phóng chỗ.
- Theo dõi counter và reservation thực tế để phát hiện sai lệch, nhưng luôn dùng cơ chế đồng thời ở database làm lớp bảo vệ chính.

Một hệ thống đặt chỗ đáng tin cậy phải quyết định việc giữ chỗ tại thời điểm database cập nhật trạng thái có kiểm soát đồng thời. Mỗi request cần nhận một kết quả rõ ràng: giữ được chỗ, hết chỗ, đã xử lý trước đó hoặc cần thử lại. Khi capacity, reservation và trạng thái nghiệp vụ được cập nhật cùng transaction, hệ thống có thể phục vụ nhiều request đồng thời mà vẫn giữ tổng phân bổ trong giới hạn.

