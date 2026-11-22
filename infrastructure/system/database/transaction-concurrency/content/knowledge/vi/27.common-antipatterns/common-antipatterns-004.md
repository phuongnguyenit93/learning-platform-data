# Cho rằng snapshot isolation luôn bảo đảm khả tuần tự

Snapshot isolation (cô lập bằng ảnh chụp) cho mỗi transaction một góc nhìn nhất quán về dữ liệu đã commit tại một thời điểm. Cách đọc này tránh dirty read và thường cho phép reader không phải chờ writer trên các hàng dữ liệu thông thường. Nhiều hệ quản trị cũng phát hiện xung đột khi hai transaction cùng sửa một hàng dựa trên phiên bản cũ.

Những đặc điểm đó rất hữu ích, nhưng **snapshot isolation không đồng nghĩa với serializable isolation**. Hai transaction có thể đọc cùng một snapshot, ghi các hàng khác nhau và cùng COMMIT, trong khi trạng thái cuối vi phạm một quy tắc nghiệp vụ liên quan đến nhiều hàng. Hiện tượng này thường được gọi là **write skew**.

Sai lầm phổ biến là nhìn thấy mỗi transaction đều đọc dữ liệu nhất quán, không có dirty read và không ghi đè cùng một hàng, rồi kết luận lịch thực thi tương đương với việc chạy tuần tự. Kết luận đó không đúng trong mọi trường hợp.

Bài học này giải thích khác biệt giữa snapshot isolation và khả tuần tự, cách write skew tạo ra một chu trình phụ thuộc đọc-ghi, các ví dụ thực tế, cách bảo vệ bất biến bằng constraint/guard row/atomic update/SERIALIZABLE, và cách viết test để chứng minh hệ thống không dựa vào một giả định sai.

## 1. Phân biệt snapshot isolation và serializability

### 1.1. Snapshot isolation là gì?

Trong snapshot isolation (SI), một transaction đọc các phiên bản dữ liệu đã commit thuộc snapshot của nó. Các thay đổi do chính transaction thực hiện cũng được nhìn thấy bên trong transaction theo quy tắc của DBMS.

Ở mức khái niệm:

- Transaction xác lập mốc snapshot theo thời điểm DBMS quy định, thường khi transaction bắt đầu truy cập dữ liệu.
- Các câu đọc nhìn dữ liệu đã commit tại mốc đó.
- Writer tạo phiên bản mới thay vì làm reader nhìn thấy dữ liệu chưa commit.
- Nếu hai transaction cạnh tranh cập nhật cùng một hàng, nhiều triển khai SI phát hiện xung đột và hủy một transaction.
- Các transaction có write set khác nhau vẫn có thể cùng commit, dù chúng đã đọc những dữ liệu ảnh hưởng lẫn nhau.

Snapshot tạo ra một góc nhìn nhất quán về quá khứ. Nó không tự động khóa mọi điều kiện hoặc predicate mà transaction đã đọc.

### 1.2. Serializable isolation là gì?

Một lịch thực thi được gọi là serializable nếu kết quả của các transaction đã commit tương đương với một lịch trong đó từng transaction chạy trọn vẹn theo một thứ tự tuần tự nào đó.

Ví dụ, lịch đồng thời của T1 và T2 phải tương đương với một trong hai thứ tự:

~~~text
T1 chạy xong -> T2 chạy xong
hoặc
T2 chạy xong -> T1 chạy xong
~~~

Không cần transaction thực sự chạy lần lượt. Database có thể cho chúng chạy đồng thời, miễn kết quả đã commit tương đương với một thứ tự tuần tự hợp lệ.

Điều kiện này mạnh hơn việc mỗi transaction chỉ nhìn một snapshot nhất quán. Một snapshot có thể hợp lệ tại thời điểm bắt đầu nhưng các quyết định dựa trên snapshot đó có thể xung đột theo cách không thể sắp xếp thành một thứ tự tuần tự.

### 1.3. Serializable không có nghĩa là không có lỗi

Ngay cả ở SERIALIZABLE, một transaction có thể:

- Chờ khóa.
- Bị deadlock victim.
- Bị hủy do serialization failure.
- Phải retry.
- Thất bại vì UNIQUE, CHECK hoặc FOREIGN KEY.
- Hết timeout.

Cam kết của mức cô lập này là các transaction được commit phải tuân theo semantics serializable của DBMS. Database có thể từ chối một transaction để giữ cam kết đó.

Vì vậy, ứng dụng vẫn cần xử lý lỗi, rollback, retry toàn transaction và idempotency.

### 1.4. Đừng đồng nhất serializable với strict serializable

Serializable yêu cầu kết quả tương đương một thứ tự tuần tự. Strict serializable còn yêu cầu thứ tự đó tôn trọng quan hệ thời gian thực giữa các transaction đã hoàn tất trước khi transaction khác bắt đầu.

Hai khái niệm liên quan nhưng không giống nhau. Khi một hệ thống phân tán cần bảo đảm thứ tự theo thời gian thực, phải xác định rõ DBMS hoặc dịch vụ lưu trữ cung cấp mức cam kết nào.

## 2. Vì sao snapshot nhất quán vẫn có thể tạo kết quả sai?

### 2.1. Snapshot bảo vệ góc nhìn đọc, không khóa mọi quy tắc nghiệp vụ

Giả sử một phòng trực có hai bác sĩ. Quy tắc là luôn phải có ít nhất một bác sĩ trực.

Ban đầu:

| Bác sĩ | Trạng thái |
|---|---|
| A | ON |
| B | ON |

Hai transaction bắt đầu gần như đồng thời:

- T1 đọc thấy A và B đều đang trực.
- T2 cũng đọc thấy A và B đều đang trực.
- T1 quyết định tắt A.
- T2 quyết định tắt B.
- T1 và T2 cập nhật hai hàng khác nhau.
- Cả hai cùng COMMIT.

Kết quả:

| Bác sĩ | Trạng thái cuối |
|---|---|
| A | OFF |
| B | OFF |

Mỗi transaction đều đọc snapshot nhất quán. Mỗi transaction chỉ cập nhật một hàng. Không có hai writer cùng ghi một hàng. Tuy nhiên, bất biến “ít nhất một bác sĩ trực” đã bị phá.

### 2.2. Lịch xen kẽ

~~~text
Trạng thái ban đầu: A=ON, B=ON

T1: BEGIN SNAPSHOT
T2: BEGIN SNAPSHOT

T1: đọc A=ON, B=ON
T2: đọc A=ON, B=ON

T1: UPDATE A SET status='OFF'
T2: UPDATE B SET status='OFF'

T1: COMMIT
T2: COMMIT

Trạng thái cuối: A=OFF, B=OFF
~~~

Nếu chỉ có một transaction, nó sẽ thấy bác sĩ còn lại đang trực và có thể từ chối thao tác. Nhưng khi cả hai cùng đọc trạng thái cũ, quyết định của mỗi transaction đều có vẻ hợp lệ.

### 2.3. Đây là write skew

Write skew xảy ra khi:

1. Các transaction đọc một tập dữ liệu có liên quan đến cùng một bất biến.
2. Mỗi transaction ghi một tập hàng khác nhau.
3. Các lần ghi riêng lẻ không xung đột theo cơ chế write-write của SI.
4. Khi kết hợp các lần ghi, trạng thái cuối vi phạm bất biến.

Điểm quan trọng là **các transaction không cần cập nhật cùng một hàng để tạo ra xung đột logic**.

### 2.4. Cùng snapshot không có nghĩa cùng quyết định là an toàn

Snapshot isolation giúp T1 và T2 đọc cùng một trạng thái lịch sử. Điều đó có thể làm cả hai cùng đưa ra một quyết định dựa trên điều kiện đã đúng ở snapshot, nhưng điều kiện ấy không còn đúng khi hai transaction cùng commit.

Một quyết định kiểu “chỉ làm nếu tổng hiện tại còn dưới giới hạn” phụ thuộc vào tập dữ liệu, không chỉ một hàng. Nếu database không bảo vệ predicate hoặc một hàng đại diện cho giới hạn, hai transaction có thể cùng vượt qua bước kiểm tra.

## 3. Xung đột ghi và xung đột đọc-ghi

### 3.1. Write-write conflict

Hai transaction cùng sửa một hàng:

~~~text
T1 đọc hàng A
T2 đọc hàng A

T1 cập nhật A
T2 cập nhật A

T1 COMMIT
T2 cố COMMIT
~~~

Nhiều triển khai snapshot isolation dùng quy tắc first-updater-wins hoặc first-committer-wins. Một transaction có thể bị hủy vì hàng đã thay đổi kể từ snapshot của nó.

Cơ chế này giúp ngăn một số lost update trên cùng hàng.

### 3.2. Read-write dependency

T1 đọc hàng B. Sau đó T2 ghi hàng B. Nếu T1 đọc phiên bản cũ và T2 commit phiên bản mới, quyết định của T1 phụ thuộc vào một giá trị mà T2 đã thay đổi.

Đây là quan hệ phụ thuộc đọc-ghi. Một số tài liệu gọi nó là read-write anti-dependency.

### 3.3. Write skew không cần write-write conflict

Trong ví dụ bác sĩ trực:

- T1 đọc A và B, nhưng chỉ ghi A.
- T2 đọc A và B, nhưng chỉ ghi B.

Write set của hai transaction không giao nhau. Cơ chế phát hiện xung đột trên cùng hàng không có lý do rõ ràng để hủy một transaction.

Nhưng T1 đã đọc B mà T2 thay đổi; T2 đã đọc A mà T1 thay đổi. Hai phụ thuộc đọc-ghi tạo thành vòng.

### 3.4. Đồ thị serialization

Một lịch có thể được phân tích bằng serialization graph. Mỗi nút là transaction; cạnh biểu diễn quan hệ phụ thuộc giữa hai transaction.

Với write skew:

- T1 đọc phiên bản A/B cũ.
- T2 ghi B sau snapshot T1.
- T2 đọc phiên bản A/B cũ.
- T1 ghi A sau snapshot T2.

Có hai cạnh anti-dependency:

~~~text
T1 --rw--> T2
T2 --rw--> T1
~~~

Đồ thị có chu trình. Không thể chọn T1 trước T2 vì có cạnh T2 -> T1; cũng không thể chọn T2 trước T1 vì có cạnh T1 -> T2.

Lịch đã commit không tương đương với một thứ tự tuần tự. Đây là lý do SI không bảo đảm serializability nói chung.

## 4. Ví dụ 1: quy tắc luôn phải có người trực

### 4.1. Schema và dữ liệu

~~~sql
CREATE TABLE dbo.DoctorShift (
    DoctorId INT PRIMARY KEY,
    IsOnCall BIT NOT NULL
);

INSERT INTO dbo.DoctorShift (DoctorId, IsOnCall)
VALUES (1, 1), (2, 1);
~~~

Bất biến:

~~~sql
SELECT COUNT(*)
FROM dbo.DoctorShift
WHERE IsOnCall = 1;
~~~

Kết quả sau mỗi transaction đã commit phải lớn hơn hoặc bằng 1.

### 4.2. Session A

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT DoctorId, IsOnCall
FROM dbo.DoctorShift
WHERE IsOnCall = 1;

-- Tại đây T1 thấy cả hai bác sĩ đang trực.
-- Đồng bộ với Session B trước khi cập nhật.

UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE DoctorId = 1;

COMMIT TRANSACTION;
~~~

### 4.3. Session B

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

SELECT DoctorId, IsOnCall
FROM dbo.DoctorShift
WHERE IsOnCall = 1;

-- Tại đây T2 cũng thấy cả hai bác sĩ đang trực.
-- Đồng bộ với Session A trước khi cập nhật.

UPDATE dbo.DoctorShift
SET IsOnCall = 0
WHERE DoctorId = 2;

COMMIT TRANSACTION;
~~~

Để tái hiện write skew, hai session phải đọc xong trước khi bất kỳ session nào cập nhật. Có thể dùng test harness với barrier; không dựa vào việc chạy hai cửa sổ SQL cùng lúc một cách ngẫu nhiên.

### 4.4. Vì sao cả hai có thể commit?

T1 ghi DoctorId=1. T2 ghi DoctorId=2. Hai hàng khác nhau nên không có write-write conflict trực tiếp trên cùng hàng.

Cả hai đều kiểm tra điều kiện từ snapshot ban đầu. Nếu không có cơ chế bảo vệ bất biến liên hàng, cả hai có thể commit và tắt toàn bộ người trực.

### 4.5. Oracle

Sau khi cả hai transaction kết thúc, mở connection mới:

~~~sql
SELECT COUNT(*) AS OnCallCount
FROM dbo.DoctorShift
WHERE IsOnCall = 1;
~~~

Oracle phải xác nhận OnCallCount >= 1. Không chỉ kiểm tra rằng hai lệnh UPDATE không phát sinh exception.

## 5. Ví dụ 2: vượt giới hạn tổng quota

### 5.1. Quy tắc

Một nhóm có tổng quota 100. Các thành viên đã sử dụng 90. Hai request đồng thời muốn tăng mức sử dụng thêm 7 và 8.

Mỗi request riêng lẻ đọc tổng 90 và thấy:

- 90 + 7 <= 100.
- 90 + 8 <= 100.

Nếu hai transaction ghi hai hàng thành viên khác nhau, cả hai có thể commit. Tổng cuối là 105.

### 5.2. Lịch

~~~text
Initial total used = 90, limit = 100

T1 snapshot: SUM(used) = 90
T2 snapshot: SUM(used) = 90

T1: tăng member A thêm 7
T2: tăng member B thêm 8

T1 COMMIT
T2 COMMIT

Final total used = 105
~~~

Không có lost update trên một hàng. Lỗi nằm ở bất biến tổng hợp.

### 5.3. Vì sao kiểm tra tổng trong ứng dụng không đủ?

Hai transaction có thể cùng chạy SELECT SUM từ snapshot của mình. Việc kiểm tra đúng tại thời điểm đọc không khóa toàn bộ tập hàng hoặc predicate để ngăn transaction khác thay đổi tổng trước khi ghi.

Nếu giới hạn là một con số toàn nhóm, hãy cân nhắc lưu bộ đếm đã sử dụng trên một hàng quota đại diện và cập nhật nguyên tử.

## 6. Ví dụ 3: hai lịch đặt chồng lấn

### 6.1. Quy tắc

Trong cùng một phòng, không được có hai reservation ACTIVE có khoảng thời gian giao nhau.

Với khoảng nửa mở [start, end), hai khoảng giao nhau khi:

~~~text
A.start < B.end AND B.start < A.end
~~~

### 6.2. Lịch cạnh tranh

~~~text
T1 kiểm tra không có lịch giao với 10:00-11:00
T2 kiểm tra không có lịch giao với 10:30-11:30

T1 chưa INSERT
T2 chưa INSERT

Cả hai đều thấy không có reservation

T1 INSERT 10:00-11:00
T2 INSERT 10:30-11:30

Cả hai COMMIT
~~~

Hai transaction chèn hai hàng mới khác nhau. Nếu chỉ dựa vào snapshot read và không có cơ chế bảo vệ predicate, cả hai có thể cùng thành công.

### 6.3. Đây là predicate anomaly

Transaction không chỉ dựa vào một hàng cụ thể. Nó dựa vào điều kiện “không tồn tại hàng nào có khoảng giao nhau”.

Một transaction khác có thể tạo ra hàng mới khiến điều kiện đó không còn đúng. Snapshot của transaction đầu không tự động biến predicate thành một khóa độc quyền trên mọi giá trị có thể được chèn.

## 7. Phân biệt SI với các hiện tượng khác

### 7.1. Dirty read

Dirty read là đọc dữ liệu chưa commit của transaction khác. Snapshot isolation tránh dirty read bằng cách đọc phiên bản đã commit.

### 7.2. Non-repeatable read

Non-repeatable read xảy ra khi một transaction đọc cùng hàng hai lần và thấy giá trị khác nhau. Snapshot transaction thường giữ cùng phiên bản qua các statement, nên tránh dạng anomaly này trong phạm vi snapshot.

### 7.3. Phantom

Phantom là một hàng mới hoặc thay đổi xuất hiện trong kết quả truy vấn predicate giữa các lần đọc.

Snapshot transaction thường giữ cùng snapshot, vì vậy các statement đọc trong transaction không thấy phantom được commit sau snapshot. Tuy nhiên, điều đó không có nghĩa predicate được khóa để ngăn transaction khác chèn hàng thỏa điều kiện.

Transaction khác vẫn có thể chèn một hàng khiến bất biến nghiệp vụ bị vi phạm trong trạng thái cuối. Đây là một dạng vấn đề write skew/predicate anomaly.

### 7.4. Lost update

Lost update thường liên quan đến hai transaction cùng cập nhật cùng một giá trị dựa trên dữ liệu cũ. SI có thể phát hiện xung đột cùng hàng và hủy một transaction.

Nhưng việc ngăn lost update trên cùng hàng không đồng nghĩa ngăn write skew trên nhiều hàng.

### 7.5. Write skew

Write skew là trường hợp các transaction đọc một tập dữ liệu chung nhưng ghi các phần khác nhau. Mỗi transaction không nhất thiết ghi đè thay đổi của transaction khác, nhưng kết hợp các thay đổi làm sai bất biến.

Đây là anomaly tiêu biểu để chứng minh SI không tương đương serializable.

## 8. RCSI cũng không phải transaction-level serializability

### 8.1. READ_COMMITTED_SNAPSHOT trong SQL Server

RCSI là tùy chọn database làm cho các truy vấn READ COMMITTED thông thường đọc phiên bản tại thời điểm bắt đầu mỗi statement.

Nó khác với SNAPSHOT isolation:

| Đặc điểm | RCSI | SNAPSHOT |
|---|---|---|
| Snapshot | Mỗi statement | Cả transaction |
| Hai SELECT trong một transaction | Có thể thấy commit mới giữa hai câu | Cùng góc nhìn snapshot |
| Database option | READ_COMMITTED_SNAPSHOT ON | ALLOW_SNAPSHOT_ISOLATION ON |
| Session isolation | READ COMMITTED | SNAPSHOT |

RCSI giảm blocking reader-writer cho các SELECT thông thường, nhưng không cung cấp một snapshot ổn định xuyên suốt nhiều statement.

### 8.2. Read-then-write dưới RCSI

Vì mỗi statement có snapshot riêng, một transaction có thể đọc một điều kiện, rồi transaction khác thay đổi dữ liệu trước khi transaction đầu ghi.

Nếu logic chỉ dựa vào câu SELECT trước đó mà không dùng atomic UPDATE, constraint hoặc locking phù hợp, race condition vẫn có thể xảy ra.

RCSI không nên được coi là cơ chế bảo vệ một bất biến nghiệp vụ liên hàng.

### 8.3. SQL Server SNAPSHOT

SQL Server cho phép SNAPSHOT isolation khi database bật ALLOW_SNAPSHOT_ISOLATION. Transaction có snapshot nhất quán ở cấp transaction và có thể nhận update conflict khi cố sửa hàng đã bị transaction khác thay đổi kể từ snapshot.

Điều này vẫn không ngăn write skew nếu hai transaction ghi các hàng khác nhau.

### 8.4. Đừng suy luận từ tên isolation level giữa các DBMS

Các DBMS có thể đặt tên mức cô lập giống nhau nhưng triển khai khác nhau.

Ví dụ:

- PostgreSQL REPEATABLE READ dùng snapshot isolation và có thể cho phép write skew.
- PostgreSQL SERIALIZABLE bổ sung Serializable Snapshot Isolation (SSI) để phát hiện các cấu trúc phụ thuộc có thể dẫn đến anomaly và hủy transaction cần thiết.
- SQL Server SNAPSHOT và RCSI có phạm vi snapshot khác nhau; SERIALIZABLE dựa trên khóa và key-range protection.
- InnoDB REPEATABLE READ có consistent reads, locking reads, gap/next-key locks và semantics riêng; không nên gắn nhãn SI chỉ từ tên.

Luôn đọc tài liệu của đúng DBMS và phiên bản. Test trên engine production thay vì giả định cùng một tên có cùng hành vi.

## 9. PostgreSQL: REPEATABLE READ và SERIALIZABLE

### 9.1. REPEATABLE READ dùng snapshot transaction

PostgreSQL REPEATABLE READ cung cấp một snapshot ổn định cho transaction. Các câu SELECT trong transaction nhìn cùng một trạng thái dữ liệu đã commit theo snapshot đó.

Hai transaction có thể đọc cùng snapshot rồi cập nhật các hàng khác nhau. Vì không có xung đột ghi trên cùng hàng, cả hai có thể commit trong tình huống write skew.

### 9.2. Ví dụ kiểm tra bằng hai session

~~~sql
-- Session A
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM doctor_shift
WHERE is_on_call;

-- Sau khi Session B cũng đọc xong:
UPDATE doctor_shift
SET is_on_call = false
WHERE doctor_id = 1;

COMMIT;
~~~

~~~sql
-- Session B
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM doctor_shift
WHERE is_on_call;

-- Sau khi Session A cũng đọc xong:
UPDATE doctor_shift
SET is_on_call = false
WHERE doctor_id = 2;

COMMIT;
~~~

Nếu không có cơ chế bảo vệ bổ sung, cả hai có thể commit. Kết quả phải được xác minh bằng truy vấn bất biến sau khi hai session kết thúc.

### 9.3. SERIALIZABLE dùng SSI

PostgreSQL SERIALIZABLE sử dụng Serializable Snapshot Isolation. Nó theo dõi các phụ thuộc đọc-ghi có thể tạo ra lịch không serializable. Khi phát hiện cấu trúc nguy hiểm, PostgreSQL có thể hủy một transaction với SQLSTATE 40001.

Cơ chế này không cần biến mọi SELECT thành shared lock giữ lâu như locking SERIALIZABLE truyền thống. PostgreSQL dùng predicate-lock information để theo dõi phụ thuộc; các predicate locks này không hoạt động giống khóa độc quyền chặn writer thông thường.

### 9.4. Ứng dụng phải retry serialization failure

Khi PostgreSQL báo serialization_failure, transaction đã thất bại. Ứng dụng cần:

1. Rollback transaction.
2. Bắt đầu transaction mới.
3. Đọc lại dữ liệu.
4. Tính lại quyết định.
5. Thực hiện lại toàn bộ đơn vị nghiệp vụ.
6. Giới hạn số lần retry và dùng backoff phù hợp.

Không retry riêng câu UPDATE cuối dựa trên snapshot cũ.

### 9.5. Serializable có thể hủy transaction dù không có deadlock

SSI có thể phát hiện một chu trình phụ thuộc mà không cần một chu trình chờ khóa. Vì vậy, serialization failure không phải deadlock.

Hãy phân loại SQLSTATE và log riêng deadlock_detected (40P01) với serialization_failure (40001).

## 10. SQL Server: SNAPSHOT và SERIALIZABLE

### 10.1. Bật SNAPSHOT

Database cần cho phép:

~~~sql
ALTER DATABASE YourDatabase
SET ALLOW_SNAPSHOT_ISOLATION ON;
~~~

Session sử dụng:

~~~sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;
BEGIN TRANSACTION;

-- Các truy vấn đọc từ snapshot transaction.

COMMIT TRANSACTION;
~~~

### 10.2. Xung đột cùng hàng không phải bảo vệ predicate

SQL Server SNAPSHOT có thể hủy transaction khi phát hiện hàng được cập nhật sau snapshot. Nhưng hai transaction cập nhật hai hàng khác nhau vẫn có thể cùng commit.

Vì vậy, test cùng một hàng không đủ để chứng minh bất biến liên hàng được bảo vệ.

### 10.3. SERIALIZABLE và key-range locks

SQL Server SERIALIZABLE dùng khóa để bảo vệ dữ liệu và phạm vi predicate theo access path. Key-range locks có thể ngăn transaction khác chèn hàng vào khoảng mà transaction đang kiểm tra.

Khả năng khóa phạm vi phụ thuộc index và plan. Một truy vấn scan rộng có thể tạo khóa phạm vi rộng hơn mong đợi và tăng blocking/deadlock.

### 10.4. Dùng UPDLOCK/HOLDLOCK có chủ đích

Có thể dùng UPDLOCK để tuần tự hóa read-then-update trên hàng đại diện, hoặc HOLDLOCK để áp dụng semantics SERIALIZABLE cho table reference cụ thể.

Các hint phải được dùng với hiểu biết về resource và transaction scope. Không thêm hint tùy tiện vì chúng có thể tạo blocking hoặc deadlock mới.

## 11. Các cách bảo vệ bất biến liên hàng

### 11.1. Ưu tiên constraint khi quy tắc biểu diễn được

Nếu quy tắc có thể biểu diễn bằng constraint, hãy để database bảo vệ nó ở nơi mọi writer đều phải đi qua.

Ví dụ:

- UNIQUE cho khóa nghiệp vụ.
- Filtered/partial unique index cho một hàng ACTIVE.
- CHECK cho điều kiện trong cùng hàng.
- FOREIGN KEY cho quan hệ tham chiếu.
- Exclusion constraint trong PostgreSQL cho các khoảng không được chồng lấn khi mô hình phù hợp.

Constraint có lợi thế là batch, API, worker và admin tool đều phải tuân thủ.

Không phải mọi bất biến tổng hợp đều biểu diễn được bằng CHECK. Chẳng hạn, CHECK không phải công cụ tổng quát để đếm các hàng khác trong bảng. Hãy kiểm tra giới hạn của DBMS trước khi chọn constraint.

### 11.2. Atomic conditional UPDATE

Nếu quota được lưu trên một hàng:

~~~sql
UPDATE dbo.GroupQuota
SET Used = Used + @Amount
WHERE GroupId = @GroupId
  AND Used + @Amount <= LimitValue;
~~~

Nếu row count bằng 1, quota được cấp. Nếu bằng 0, không đủ quota hoặc group không tồn tại.

Câu lệnh kiểm tra và cập nhật cùng một hàng trong một thao tác nguyên tử. Hai request cạnh tranh trên cùng hàng phải được DBMS tuần tự hóa bằng cơ chế ghi.

Đây thường là cách đơn giản hơn so với SELECT tổng rồi UPDATE nhiều hàng.

### 11.3. Materialize bất biến vào một hàng đại diện

Nếu quy tắc là tổng quota của cả nhóm, có thể lưu một hàng quota chứa:

- LimitValue.
- Used.
- Version.
- UpdatedAt.

Mọi thao tác tăng/giảm quota phải cập nhật hàng đại diện trong cùng transaction với các hàng chi tiết.

Ví dụ:

~~~sql
BEGIN TRANSACTION;

UPDATE dbo.GroupQuota
SET Used = Used + @Amount
WHERE GroupId = @GroupId
  AND Used + @Amount <= LimitValue;

IF @@ROWCOUNT <> 1
BEGIN
    ROLLBACK TRANSACTION;
    THROW 50001, 'Quota exceeded', 1;
END;

INSERT INTO dbo.GroupUsage (GroupId, MemberId, Amount)
VALUES (@GroupId, @MemberId, @Amount);

COMMIT TRANSACTION;
~~~

Cần bảo đảm mọi đường ghi đều cập nhật hàng quota. Nếu batch import bỏ qua bước này, bất biến lại có thể bị phá.

### 11.4. Guard row

Guard row là một hàng đại diện được mọi transaction liên quan khóa hoặc cập nhật trước khi kiểm tra bất biến.

Ví dụ PostgreSQL dùng khóa hàng:

~~~sql
BEGIN;

SELECT guard_id
FROM invariant_guard
WHERE guard_id = 1
FOR UPDATE;

-- Đọc các hàng chi tiết sau khi đã lấy guard.
-- Kiểm tra bất biến và thực hiện thay đổi.

COMMIT;
~~~

Ví dụ SQL Server:

~~~sql
BEGIN TRANSACTION;

SELECT GuardId
FROM dbo.InvariantGuard WITH (UPDLOCK, HOLDLOCK)
WHERE GuardId = 1;

-- Đọc dữ liệu chi tiết, kiểm tra và ghi.

COMMIT TRANSACTION;
~~~

Mọi transaction có thể ảnh hưởng cùng bất biến phải dùng cùng guard row. Nếu một writer bỏ qua guard, nó có thể phá bảo đảm.

### 11.5. Guard row dưới snapshot isolation cần tạo xung đột ghi

Có một chi tiết quan trọng: chỉ đọc hoặc chỉ chờ khóa trên guard row chưa chắc đủ nếu transaction vẫn giữ snapshot cũ.

Trong các triển khai SI, một transaction có thể đợi khóa rồi vẫn tiếp tục đọc từ snapshot đã xác lập trước đó. Nếu chỉ lấy khóa mà không tạo xung đột phiên bản, transaction thứ hai có thể tiếp tục dùng dữ liệu cũ.

Một cách thiết kế là cập nhật một version/counter trên guard row trong cùng transaction:

~~~sql
UPDATE invariant_guard
SET version = version + 1
WHERE guard_id = 1;
~~~

Nếu hai transaction cùng cập nhật guard row từ cùng snapshot, cơ chế write conflict của DBMS có thể hủy một transaction. Transaction bị hủy phải retry toàn bộ nghiệp vụ với snapshot mới.

Cách này biến xung đột predicate thành xung đột ghi trên một hàng chung. Cần kiểm tra semantics chính xác của DBMS và bảo đảm mọi writer đều cập nhật guard row.

### 11.6. SERIALIZABLE cho predicate

Nếu bất biến phụ thuộc vào điều kiện trên nhiều hàng hoặc sự tồn tại của hàng trong một khoảng, SERIALIZABLE có thể là lựa chọn trực tiếp.

Ví dụ: kiểm tra không có reservation giao với khoảng thời gian trước khi INSERT. SERIALIZABLE phải bảo vệ predicate theo semantics của DBMS, không chỉ khóa những hàng đã tìm thấy.

Tùy engine, cơ chế có thể là key-range locks, predicate tracking/SSI hoặc phương pháp tương ứng. Kiểm tra plan, index và lỗi serialization/deadlock khi tải đồng thời.

### 11.7. Khóa ứng dụng hoặc advisory lock

Có thể dùng application lock/advisory lock theo business key, chẳng hạn room_id hoặc group_id. Cơ chế này hữu ích khi predicate không có một hàng đại diện tự nhiên.

Cần xác định:

- Lock nằm trong database hay service phân tán.
- Phạm vi session hay transaction.
- Cách giải phóng khi connection mất.
- Timeout và deadlock behavior.
- Tất cả writer có tuân thủ cùng quy ước không.
- Có fencing token nếu dùng lease ở hệ thống phân tán không.

Một mutex trong bộ nhớ của một JVM không bảo vệ được nhiều instance ứng dụng.

## 12. Chọn cơ chế theo loại bất biến

| Loại bất biến | Cơ chế nên xem xét | Lưu ý |
|---|---|---|
| Khóa nghiệp vụ duy nhất | UNIQUE/partial unique | Chuẩn hóa key và phạm vi tenant |
| Điều kiện trong một hàng | CHECK hoặc atomic UPDATE | Đặt điều kiện ngay trong UPDATE |
| Quota/tổng số lượng | Counter/guard row + conditional UPDATE | Mọi writer phải cập nhật cùng hàng |
| Không có khoảng thời gian chồng lấn | Exclusion constraint hoặc SERIALIZABLE/guard | Xác định rõ biên khoảng |
| Ít nhất một hàng còn ACTIVE | Guard row, SERIALIZABLE hoặc mô hình hóa lại | Write skew điển hình |
| Tổng số dư/ledger cân bằng | Một transaction nguyên tử, constraint/ledger design | Kiểm tra cả debit và credit |
| Một job chỉ có một owner | Atomic claim, lease và fencing token | Chống worker cũ tiếp tục ghi |
| Nhiều statement cần cùng snapshot | SNAPSHOT/REPEATABLE READ | Không tự bảo vệ predicate |
| Lịch phải serializable | SERIALIZABLE/SSI | Ứng dụng phải xử lý retry |

## 13. Thiết kế retry đúng khi serializable hủy transaction

### 13.1. Retry toàn transaction

Serialization failure cho biết transaction hiện tại không thể được chấp nhận theo mức cô lập yêu cầu. Các quyết định đọc trước đó có thể không còn hợp lệ.

Mẫu retry:

~~~text
for attempt in 1..maxAttempts:
    BEGIN transaction at SERIALIZABLE
    try:
        read current state
        validate business invariant
        perform all writes
        COMMIT
        return success
    catch serialization/deadlock:
        ROLLBACK if transaction still active
        if attempts exhausted:
            return retryable conflict
        wait with bounded backoff and jitter
~~~

Không chỉ retry statement cuối. Phải đọc lại và tính lại toàn bộ transaction.

### 13.2. Phân biệt lỗi retryable và lỗi nghiệp vụ

Có thể retry:

- Serialization failure.
- Deadlock victim nếu thao tác an toàn.
- Một số transient lock conflict theo chính sách.

Không nên retry mù quáng:

- UNIQUE violation thể hiện một request khác đã tạo tài nguyên.
- CHECK/FOREIGN KEY violation.
- Validation failure.
- Cùng idempotency key nhưng payload khác.
- Business rule rejection.

Ứng dụng cần phân loại SQLSTATE/vendor code và exception cause.

### 13.3. Backoff và giới hạn

Dùng:

- Số lần retry tối đa.
- Backoff tăng dần.
- Jitter.
- Deadline tổng.
- Metric số lần retry.
- Log operation ID và attempt number.

Retry không có giới hạn có thể tạo retry storm và làm contention nặng hơn.

### 13.4. Side effect ngoài database

Nếu transaction gửi email, gọi payment provider hoặc publish message trước khi commit, retry có thể lặp tác dụng phụ.

Dùng transactional outbox, idempotency key ở provider và inbox/dedup ở consumer. Chỉ phát tác dụng phụ theo một giao thức có thể phục hồi.

### 13.5. Ambiguous COMMIT là trường hợp riêng

Nếu connection mất khi COMMIT đang được gửi, client có thể không biết transaction đã commit hay chưa. Không xử lý trường hợp này như serialization failure thông thường.

Dùng operation ID/idempotency key để truy vấn kết quả đã commit trước khi quyết định chạy lại.

## 14. Test để chứng minh SI không tự bảo đảm serializability

### 14.1. Test cùng một hàng

Tạo hai transaction cùng cập nhật một hàng dựa trên snapshot cũ.

Mục tiêu:

- Xác nhận DBMS có phát hiện write-write conflict theo semantics của nó.
- Xác nhận một transaction bị hủy hoặc chờ theo đúng engine.
- Xác nhận ứng dụng rollback và retry đúng.

Test này không đủ để kiểm tra write skew.

### 14.2. Test hai hàng khác nhau

Dùng bất biến “ít nhất một bác sĩ trực”.

Dữ liệu ban đầu:

~~~sql
INSERT INTO doctor_shift (doctor_id, is_on_call)
VALUES (1, true), (2, true);
~~~

Hai actor dùng connection riêng:

~~~text
Actor A:
  BEGIN SNAPSHOT
  SELECT cả hai hàng
  Signal read-complete
  Wait barrier
  UPDATE doctor A thành OFF
  COMMIT

Actor B:
  BEGIN SNAPSHOT
  SELECT cả hai hàng
  Signal read-complete
  Wait barrier
  UPDATE doctor B thành OFF
  COMMIT
~~~

Barrier phải bảo đảm cả hai transaction đọc xong trước khi ghi.

### 14.3. Oracle sau test

~~~sql
SELECT COUNT(*)
FROM doctor_shift
WHERE is_on_call = true;
~~~

Kết quả phải >= 1.

Chạy test ở SI để chứng minh write skew có thể xuất hiện với thiết kế không bảo vệ. Sau đó chạy lại với cơ chế bảo vệ và xác nhận bất biến được giữ.

### 14.4. Test SERIALIZABLE

Chạy cùng lịch ở SERIALIZABLE. DBMS có thể:

- Chặn một transaction.
- Phát hiện chu trình phụ thuộc.
- Chọn transaction để abort.
- Trả serialization/deadlock error.

Không assert transaction cụ thể nào phải thắng. Assert rằng trạng thái cuối giữ bất biến và ứng dụng xử lý transaction bị hủy đúng cách.

### 14.5. Test guard row

Thêm thao tác cập nhật guard row trong mỗi transaction trước khi đọc/kiểm tra dữ liệu chi tiết.

Xác nhận:

- Cả hai transaction không thể cùng hoàn tất dựa trên cùng guard version.
- Transaction thua được rollback/conflict.
- Retry đọc lại trạng thái mới.
- Bất biến cuối cùng vẫn đúng.

### 14.6. Test writer bỏ qua guard

Cố tình tạo một đường ghi không cập nhật guard row, chẳng hạn batch import hoặc admin path. Xác nhận test phát hiện bất biến bị phá.

Test này chứng minh guard row chỉ có hiệu lực khi mọi writer tuân thủ giao thức.

### 14.7. Test predicate insert

Dùng hai transaction cùng kiểm tra không có reservation giao nhau rồi INSERT các khoảng chồng lấn. Chạy dưới SI và SERIALIZABLE/constraint để so sánh.

Oracle phải tìm cặp khoảng ACTIVE giao nhau. Không chỉ kiểm tra số lượng INSERT thành công.

## 15. Tạo lịch test xác định trong Java

### 15.1. Dùng connection độc lập

Mỗi actor phải có connection riêng và transaction riêng. Không chia sẻ một connection giữa hai thread.

~~~java
ExecutorService executor = Executors.newFixedThreadPool(2);
CyclicBarrier afterRead = new CyclicBarrier(2);

Callable<Void> actorA = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        // Cấu hình isolation theo test.
        readBothDoctors(connection);
        afterRead.await(5, TimeUnit.SECONDS);
        turnDoctorOff(connection, 1);
        connection.commit();
    }
    return null;
};

Callable<Void> actorB = () -> {
    try (Connection connection = dataSource.getConnection()) {
        connection.setAutoCommit(false);
        // Cấu hình isolation theo test.
        readBothDoctors(connection);
        afterRead.await(5, TimeUnit.SECONDS);
        turnDoctorOff(connection, 2);
        connection.commit();
    }
    return null;
};
~~~

Đây là khung minh họa. Cần rollback trong finally khi transaction chưa commit và thu thập exception của từng actor.

### 15.2. Không dùng sleep

Thread.sleep không bảo đảm cả hai transaction đã đọc xong hoặc đang giữ đúng trạng thái cần test.

Dùng barrier/latch để điều khiển điểm đồng bộ. Dùng timeout trên barrier để test không treo vô hạn, nhưng timeout harness không phải bằng chứng database đã rollback.

### 15.3. Oracle dùng connection mới

Sau khi actor kết thúc, dùng connection độc lập đọc trạng thái đã commit. Đừng đọc từ transaction của một actor còn mở hoặc từ cache của ORM.

### 15.4. Ghi nhận outcome từng actor

Ghi rõ:

- Commit thành công.
- Serialization failure.
- Deadlock victim.
- Constraint violation.
- Timeout.
- Connection loss.
- Rollback failure.

Test có thể pass dù một actor bị hủy, miễn kết quả đó thuộc hợp đồng và bất biến cuối được giữ.

## 16. Các câu hỏi cần hỏi trước khi chọn SNAPSHOT

- Transaction đọc một hàng hay một tập dữ liệu?
- Quy tắc nghiệp vụ phụ thuộc tổng, count, range hoặc “không tồn tại” không?
- Hai transaction có thể ghi hai hàng khác nhau nhưng cùng ảnh hưởng một quy tắc không?
- Có guard row hoặc aggregate counter không?
- Mọi writer có tuân thủ cùng giao thức không?
- Database có phát hiện xung đột ghi cùng hàng không?
- Isolation level có phát hiện chu trình đọc-ghi hay chỉ write-write conflict?
- Cần snapshot cho từng statement hay cả transaction?
- Có thể biểu diễn bất biến bằng UNIQUE/CHECK/exclusion constraint không?
- Có thể chuyển logic thành atomic conditional UPDATE không?
- SERIALIZABLE của DBMS sử dụng locking hay SSI?
- Ứng dụng đã retry toàn transaction chưa?
- Side effect có idempotency/outbox không?
- Test có mô phỏng hai transaction đọc cùng snapshot và ghi khác hàng không?

## 17. Các hiểu nhầm thường gặp

**“Snapshot nhất quán nghĩa là transaction tương đương chạy một mình.”**

Sai. Snapshot là góc nhìn đọc ổn định. Các transaction khác vẫn có thể ghi các hàng khác nhau làm quyết định của transaction hiện tại trở nên không hợp lệ.

**“Không có lost update thì không có anomaly.”**

Sai. SI có thể ngăn xung đột ghi cùng hàng nhưng vẫn cho phép write skew trên nhiều hàng.

**“Nếu mỗi transaction kiểm tra điều kiện trước khi ghi thì điều kiện luôn được giữ.”**

Sai. Hai transaction có thể cùng kiểm tra từ snapshot cũ. Điều kiện phải được bảo vệ bằng constraint, khóa, atomic update hoặc serializable mechanism.

**“Mỗi transaction đọc cùng snapshot thì kết quả cuối phải giống một thứ tự tuần tự.”**

Sai. Write skew tạo chu trình phụ thuộc đọc-ghi, khiến không tồn tại thứ tự tuần tự phù hợp.

**“RCSI và SNAPSHOT giống nhau.”**

Sai. RCSI thường tạo snapshot cho mỗi statement; SNAPSHOT tạo snapshot ở cấp transaction. Cả hai vẫn cần bảo vệ bất biến ghi.

**“REPEATABLE READ luôn tương đương SI ở mọi DBMS.”**

Sai. Tên isolation level không đủ để suy ra semantics. Phải đọc tài liệu của engine và phiên bản.

**“SERIALIZABLE không bao giờ hủy transaction.”**

Sai. DBMS có thể chặn, phát hiện deadlock hoặc abort serialization conflict để giữ cam kết serializable.

**“Chỉ cần khóa các hàng đã đọc.”**

Sai. Bất biến có thể phụ thuộc predicate hoặc hàng chưa tồn tại. Cần bảo vệ range/predicate hoặc dùng guard row/constraint phù hợp.

**“Guard row chỉ cần SELECT FOR UPDATE.”**

Không phải lúc nào cũng đủ dưới snapshot isolation. Nếu transaction giữ snapshot cũ sau khi chờ khóa, nó có thể tiếp tục dùng dữ liệu cũ. Thiết kế guard cần tạo xung đột ghi hoặc dùng SERIALIZABLE theo semantics của DBMS.

**“Retry một câu UPDATE là đủ.”**

Sai. Dữ liệu đọc và quyết định trước đó có thể đã cũ. Retry thường phải chạy lại toàn bộ transaction.

**“Chạy test tuần tự là đủ.”**

Sai. Write skew chỉ xuất hiện khi các transaction cùng đọc snapshot trước khi ghi. Cần test đồng thời có barrier.

**“Mọi DBMS đều xử lý write skew như nhau.”**

Sai. Cơ chế và tên isolation level khác nhau. Chạy test trên DBMS production và ghi rõ cấu hình.

## 18. Quy trình chọn mức cô lập và bảo vệ bất biến

1. **Viết bất biến nghiệp vụ.** Xác định điều kiện phải đúng sau mọi transaction đã commit.
2. **Xác định phạm vi dữ liệu.** Một hàng, nhiều hàng, tổng hợp, predicate hay khoảng thời gian.
3. **Liệt kê các writer.** API, batch, worker, trigger, consumer và admin tool.
4. **Tìm lịch write skew.** Hai transaction cùng đọc trạng thái rồi ghi các hàng khác nhau.
5. **Kiểm tra constraint.** Dùng UNIQUE, CHECK, FK hoặc exclusion constraint nếu biểu diễn được.
6. **Ưu tiên atomic update.** Gộp kiểm tra và thay đổi vào một câu lệnh có điều kiện khi phù hợp.
7. **Cân nhắc guard row.** Mọi writer phải cập nhật/khóa cùng hàng đại diện.
8. **Cân nhắc SERIALIZABLE.** Dùng khi cần bảo vệ predicate hoặc toàn bộ lịch thực thi.
9. **Thiết kế retry.** Retry toàn transaction, giới hạn số lần và backoff.
10. **Bảo vệ side effect.** Dùng idempotency và outbox/inbox.
11. **Viết deterministic test.** Ép hai transaction đọc cùng snapshot trước khi ghi.
12. **Chạy trên engine thực tế.** Đúng phiên bản, isolation, index, driver và connection pool.
13. **Đối soát oracle.** Kiểm tra bất biến sau khi mọi transaction kết thúc.
14. **Theo dõi production.** Đo serialization failure, deadlock, retry, lock wait và vi phạm bất biến.

## 19. Ma trận quyết định

| Yêu cầu | Snapshot isolation | Serializable |
|---|---|---|
| Đọc dữ liệu đã commit nhất quán | Có | Có |
| Tránh dirty read | Có | Có |
| Giữ góc nhìn ổn định qua nhiều statement | Thường có ở SI transaction-level | Có theo semantics transaction |
| Phát hiện xung đột ghi cùng hàng | Thường có | Có |
| Ngăn mọi write skew | Không | Có, nếu transaction chạy đúng trong phạm vi serializable |
| Bảo vệ predicate/range | Không tự động | Có theo semantics DBMS |
| Có thể abort transaction | Có khi write conflict | Có khi deadlock/serialization conflict |
| Chi phí version/lock | Có version store và conflict handling | Tùy cơ chế engine: range locks hoặc SSI/predicate tracking |
| Retry có thể cần | Có | Có |

Bảng này là định hướng khái niệm. Cần kiểm tra semantics của DBMS cụ thể, vì snapshot isolation và serializable được triển khai khác nhau.

## 20. Kết luận

Snapshot isolation cung cấp một góc nhìn nhất quán và thường ngăn các xung đột ghi trực tiếp trên cùng hàng. Nhưng một bất biến nghiệp vụ có thể phụ thuộc nhiều hàng hoặc một predicate. Hai transaction cùng đọc snapshot cũ rồi ghi hai hàng khác nhau có thể cùng commit và tạo write skew.

Muốn bảo vệ những quy tắc đó, hãy xác định bất biến trước, tìm các lịch đọc-ghi cạnh tranh và chọn cơ chế phù hợp: constraint, atomic conditional update, guard row có xung đột ghi, hoặc SERIALIZABLE. Khi database hủy transaction vì serialization conflict, ứng dụng phải retry toàn bộ đơn vị nghiệp vụ với dữ liệu mới. Cuối cùng, hãy kiểm tra bằng test đồng thời xác định trên đúng DBMS và cấu hình production; một test chỉ cập nhật cùng một hàng không đủ để chứng minh snapshot isolation là serializable.
