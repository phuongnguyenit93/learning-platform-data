# Serializable Snapshot Isolation (SSI) và quan hệ phụ thuộc nguy hiểm

**Serializable Snapshot Isolation (SSI)** là một kỹ thuật kiểm soát đồng thời kết hợp ảnh chụp MVCC với việc theo dõi quan hệ đọc/ghi để bảo đảm các transaction đã commit có thể được xem như đã chạy theo một thứ tự tuần tự hợp lệ. PostgreSQL triển khai SSI cho isolation level **SERIALIZABLE**.

SSI giữ lợi ích đọc không chặn ghi của snapshot isolation trong nhiều trường hợp. Khi phát hiện các quan hệ phụ thuộc có thể tạo ra chu trình trong đồ thị tuần tự hóa, hệ quản trị hủy một transaction để ngăn kết quả không thể tuần tự hóa. Vì vậy, ứng dụng dùng SSI phải chấp nhận rằng một transaction có thể thất bại khi COMMIT và cần được chạy lại từ đầu.

Để hiểu SSI, cần nắm ba khái niệm: đồ thị phụ thuộc (serialization graph), phụ thuộc đọc-ghi (read-write antidependency) và cấu trúc phụ thuộc nguy hiểm (dangerous structure).

## 1. Vì sao snapshot isolation vẫn chưa đủ?

MVCC cho phép transaction đọc phiên bản phù hợp với snapshot của nó trong khi transaction khác tiếp tục ghi. Với snapshot isolation, các transaction thường tránh dirty read và có góc nhìn ổn định. Hệ quản trị cũng có thể phát hiện hai transaction cùng cập nhật một dòng và từ chối một bên.

Tuy nhiên, chỉ phát hiện hai transaction ghi cùng một dòng là chưa đủ để bảo vệ mọi quy tắc nghiệp vụ. Hai transaction có thể đọc cùng một tập dữ liệu, sau đó cập nhật hai dòng khác nhau. Write set của chúng không giao nhau nên cả hai vẫn có thể commit, dù kết quả tổng thể vi phạm một quy tắc.

Ví dụ, một ca trực phải luôn có ít nhất một bác sĩ đang trực. Ban đầu bác sĩ A và B đều đang trực:

~~~text
Trạng thái ban đầu:
Doctor A: on_call = TRUE
Doctor B: on_call = TRUE

Transaction T1                    Transaction T2
----------------                    ----------------
Đọc A và B: cả hai đang trực       Đọc A và B: cả hai đang trực
Cho A nghỉ                          Cho B nghỉ
UPDATE A = FALSE                   UPDATE B = FALSE
COMMIT                              COMMIT

Trạng thái cuối:
Doctor A: on_call = FALSE
Doctor B: on_call = FALSE
Không còn ai trực
~~~

T1 ghi dòng A, T2 ghi dòng B. Nếu chỉ kiểm tra xung đột ghi trên cùng dòng, database không thấy hai transaction cùng sửa một bản ghi. Nhưng quyết định của mỗi transaction lại phụ thuộc vào dữ liệu mà transaction kia thay đổi.

Hiện tượng này là **write skew**. Snapshot isolation cho từng transaction một góc nhìn nhất quán, nhưng không tự bảo đảm rằng mọi transaction commit đều tương đương với một thứ tự thực thi tuần tự.

SSI được thiết kế để phát hiện các phụ thuộc đọc/ghi có thể tạo ra kiểu bất thường này.

## 2. Đồ thị tuần tự hóa và các loại phụ thuộc

Để kiểm tra khả năng tuần tự hóa, có thể biểu diễn các transaction bằng một đồ thị có hướng. Mỗi nút là một transaction; mỗi cạnh biểu diễn một quan hệ phụ thuộc buộc thứ tự logic giữa hai transaction.

Một số loại cạnh thường được nhắc đến:

- **Read-write (rw) antidependency:** một transaction đọc dữ liệu cũ hoặc đọc một tập kết quả, sau đó transaction khác ghi thay đổi làm cho kết quả đọc đó khác đi nếu transaction ghi được xếp trước transaction đọc.
- **Write-read (wr) dependency:** transaction đọc nhìn thấy giá trị do transaction khác ghi.
- **Write-write (ww) dependency:** các transaction ghi cùng một dữ liệu theo thứ tự phiên bản.

Trong SSI, cạnh rw đặc biệt quan trọng vì nó có thể hình thành chu trình tuần tự hóa ngay cả khi các transaction không ghi cùng một dòng.

### 2.1. Hướng của cạnh rw

Trong bài này, ký hiệu:

\[
T_1 \xrightarrow{rw} T_2
\]

có nghĩa là **T1 đọc một phiên bản hoặc một tập kết quả mà thay đổi của T2 làm cho việc đọc đó trở nên cũ**. Để giữ nguyên kết quả mà T1 đã quan sát, thứ tự tuần tự tương ứng phải đặt T1 trước T2.

Ví dụ:

1. T1 đọc balance = 100.
2. T2 cập nhật balance = 80 và commit.
3. T1 vẫn dựa trên phiên bản 100 trong snapshot của nó.

T1 đã đọc trạng thái trước thay đổi của T2. Đồ thị có cạnh:

\[
T_1 \xrightarrow{rw} T_2
\]

Cạnh này không có nghĩa T1 đang chờ T2. Đây là quan hệ phụ thuộc logic dùng để suy ra thứ tự tuần tự, không phải một yêu cầu khóa đang block.

### 2.2. Phụ thuộc trên một predicate

Phụ thuộc rw không chỉ xuất hiện khi hai transaction truy cập cùng một dòng. Nó còn có thể liên quan đến một điều kiện truy vấn (predicate).

Giả sử T1 chạy:

~~~sql
SELECT *
FROM Orders
WHERE Status = 'OPEN';
~~~

Tại thời điểm đọc, T1 thấy 5 đơn hàng đang mở. Trong khi T1 còn chạy, T2 thêm một đơn hàng mới với Status = 'OPEN' rồi commit.

T1 không nhìn thấy đơn hàng mới trong snapshot của mình. Nếu T2 được xếp trước T1 trong thứ tự tuần tự, kết quả truy vấn của T1 phải bao gồm đơn hàng đó. Vì vậy, có thể hình thành quan hệ:

\[
T_1 \xrightarrow{rw} T_2
\]

Đây là lý do SSI cần theo dõi cả những vùng dữ liệu hoặc predicate đã đọc, bao gồm trường hợp transaction đọc một tập kết quả mà sau đó có transaction khác chèn hoặc cập nhật dòng để nó thuộc tập đó.

## 3. Cấu trúc phụ thuộc nguy hiểm (dangerous structure)

Một **dangerous structure** trong SSI là chuỗi hai phụ thuộc rw liên tiếp:

\[
T_{in} \xrightarrow{rw} T_{pivot} \xrightarrow{rw} T_{out}
\]

Trong chuỗi này:

- T_in là transaction ở đầu chuỗi.
- T_pivot là transaction ở giữa, nhận một phụ thuộc rw và tạo ra một phụ thuộc rw khác.
- T_out là transaction ở cuối chuỗi.

Transaction ở giữa được gọi là **pivot transaction**. Nó có vai trò quan trọng vì hai phía của nó cùng tạo nên một chuỗi phụ thuộc có khả năng tham gia vào chu trình tuần tự hóa.

Một dangerous structure là điều kiện cần để xuất hiện serialization anomaly trong mô hình snapshot isolation, nhưng **không phải mọi dangerous structure đều đã là một chu trình thực sự**. Muốn có chu trình, đồ thị còn phải có một đường phụ thuộc quay từ T_out về T_in.

### 3.1. Từ hai cạnh đến chu trình

Hãy xét ba transaction:

- T1 đọc A và ghi C.
- T2 ghi A và đọc B.
- T3 ghi B và đọc C.

Giả sử các thao tác diễn ra trên snapshot và những thay đổi ghi không nhìn thấy trong snapshot của transaction đọc:

~~~text
T1                              T2                              T3
--                              --                              --
Đọc A
                                Ghi A
                                Đọc B
                                                                Ghi B
                                                                Đọc C
Ghi C
~~~

Các quan hệ phụ thuộc:

1. T1 đọc A trước khi T2 ghi A:

   \[
   T_1 \xrightarrow{rw} T_2
   \]

2. T2 đọc B trước khi T3 ghi B:

   \[
   T_2 \xrightarrow{rw} T_3
   \]

3. T3 đọc C trước khi T1 ghi C:

   \[
   T_3 \xrightarrow{rw} T_1
   \]

Đồ thị trở thành:

~~~text
       rw             rw
  T1 -------> T2 ---------> T3
   ^                         |
   |                         |
   +-------------------------+
                rw
~~~

Có chu trình T1 → T2 → T3 → T1. Không thể sắp xếp ba transaction thành một thứ tự tuần tự duy nhất mà vẫn bảo toàn tất cả kết quả đọc và ghi quan sát được.

Chuỗi T1 →rw T2 →rw T3 là dangerous structure với T2 là pivot; cạnh T3 →rw T1 khép kín chu trình. Nếu để tất cả transaction commit trong tình huống này, database sẽ chấp nhận một kết quả không thể tuần tự hóa.

### 3.2. Write skew hai transaction

Ví dụ hai bác sĩ trực ở đầu bài có thể tạo chu trình với hai transaction:

- T1 đọc dòng B rồi ghi dòng A.
- T2 đọc dòng A rồi ghi dòng B.

Do T1 đọc phiên bản B trước thay đổi của T2:

\[
T_1 \xrightarrow{rw} T_2
\]

Do T2 đọc phiên bản A trước thay đổi của T1:

\[
T_2 \xrightarrow{rw} T_1
\]

Đồ thị có chu trình hai cạnh:

~~~text
       rw
  T1 -------> T2
   ^           |
   |           |
   +-----------+
       rw
~~~

Đây là trường hợp đầu và cuối của dangerous structure có thể là cùng một transaction: T1 →rw T2 →rw T1. SSI phải phát hiện được cả các chu trình phụ thuộc kiểu này.

## 4. SSI phát hiện dangerous structure như thế nào?

PostgreSQL triển khai SSI trên nền MVCC và theo dõi các quan hệ đọc/ghi giữa những transaction SERIALIZABLE đang chồng lấn thời gian.

Ở mức khái niệm, quá trình gồm:

1. Transaction SERIALIZABLE lấy snapshot và đọc dữ liệu.
2. Database ghi nhận vùng dữ liệu hoặc predicate mà transaction đã đọc.
3. Khi transaction khác ghi vào dữ liệu có liên quan, hệ quản trị ghi nhận phụ thuộc rw.
4. Các cạnh phụ thuộc được dùng để xác định chuỗi hai cạnh có thể tạo dangerous structure.
5. PostgreSQL áp dụng thêm các điều kiện về trạng thái và thứ tự commit để quyết định có cần hủy transaction hay không.
6. Nếu không thể bảo đảm tính tuần tự hóa, một transaction bị hủy và nhận lỗi serialization failure.

SSI không cần chờ đến khi tất cả transaction commit rồi mới dựng toàn bộ đồ thị. PostgreSQL theo dõi các phụ thuộc trong khi transaction chạy và giữ thông tin cần thiết trong khoảng thời gian có thể phát sinh xung đột.

### 4.1. Không phải mọi dangerous structure đều tạo anomaly

Hai cạnh rw liên tiếp là dấu hiệu cần quan tâm, nhưng có thể tồn tại mà không tạo chu trình. Ví dụ, T1 →rw T2 →rw T3 có thể không có bất kỳ đường phụ thuộc nào quay về T1.

Nếu hủy mọi transaction chỉ vì nhìn thấy hai cạnh rw, hệ thống sẽ từ chối nhiều lịch thực thi vốn vẫn có thể tuần tự hóa. PostgreSQL sử dụng các điều kiện bổ sung, trong đó thứ tự commit và các transaction đã kết thúc có vai trò quan trọng, để giảm số lần hủy không cần thiết.

Tuy vậy, SSI có thể đưa ra một số quyết định bảo thủ. Một transaction đôi khi nhận serialization failure dù lịch thực thi thực tế cuối cùng vẫn có thể được sắp xếp tuần tự. Điều này là đánh đổi có chủ đích: hủy một transaction và cho ứng dụng thử lại an toàn hơn việc chấp nhận một kết quả có nguy cơ vi phạm SERIALIZABLE.

## 5. SIREAD predicate locks: theo dõi lượt đọc mà không chặn ghi

PostgreSQL sử dụng **predicate locking** để ghi nhận dữ liệu mà transaction SERIALIZABLE đã đọc. Trong triển khai SSI, các dấu vết này thường được gọi là **SIREAD locks**.

SIREAD có một số đặc điểm quan trọng:

- Ghi nhận dòng, trang, quan hệ hoặc phạm vi dữ liệu mà transaction đã đọc.
- Giúp nhận ra transaction khác ghi vào vùng dữ liệu đã được đọc.
- Không phải khóa chia sẻ thông thường dùng để chặn writer.
- Không buộc transaction ghi phải đợi transaction đọc kết thúc.
- Được dùng làm thông tin phát hiện phụ thuộc, không phải cơ chế trực tiếp ngăn thay đổi dữ liệu.

Ví dụ:

~~~text
T1 (SERIALIZABLE)                 T2
------------------                 --
Đọc Orders WHERE Status='OPEN'
Database ghi nhận SIREAD
                                   INSERT Order(Status='OPEN')
                                   COMMIT
T1 tiếp tục dùng snapshot cũ
Database ghi nhận rw dependency
~~~

T2 không phải chờ SIREAD như khi gặp một khóa S thông thường. Thay vào đó, PostgreSQL ghi nhận rằng kết quả đọc của T1 có thể đã trở nên cũ nếu T2 được xếp trước T1. Khi các phụ thuộc kết hợp thành dangerous structure, SSI có thể hủy một transaction.

### 5.1. Predicate lock có thể ở nhiều mức

Tùy kế hoạch truy vấn và dữ liệu được đọc, PostgreSQL có thể ghi nhận SIREAD ở mức tuple, page hoặc relation. Nếu cần bảo vệ một predicate rộng, hệ quản trị phải theo dõi đủ phạm vi để nhận ra các dòng được thêm vào hoặc thay đổi để thỏa điều kiện đó.

Nếu số lượng dấu vết đọc tăng cao, PostgreSQL có thể gộp thông tin khóa ở mức chi tiết thành mức rộng hơn để giới hạn bộ nhớ. Phạm vi theo dõi rộng có thể làm hệ thống nhận diện thêm những phụ thuộc bảo thủ, từ đó tăng khả năng serialization failure ngoài những xung đột thật sự cần thiết.

Chỉ mục phù hợp có thể giúp truy vấn đọc một phạm vi hẹp hơn thay vì quét rộng, qua đó có thể giảm phạm vi predicate được theo dõi. Tuy nhiên, không nên giả định cứ thêm index là SSI sẽ hết serialization failure. Cần xem kế hoạch truy vấn, dữ liệu và lỗi thực tế.

### 5.2. Quan sát SIREAD trong PostgreSQL

Có thể xem một phần thông tin SIREAD đang được giữ qua pg_locks:

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

Kết quả giúp nhận biết process nào đang giữ dấu vết đọc và phạm vi tài nguyên liên quan. Đây là thông tin chẩn đoán, không phải bản đồ đầy đủ của serialization graph. Một dòng trong pg_locks không tự cho biết transaction nào sẽ bị hủy hoặc dangerous structure nào đã hình thành.

Nên kết hợp với:

- Log ứng dụng ghi nhận SQLSTATE và nội dung lỗi serialization.
- pg_stat_activity để xem transaction đang chạy, thời gian mở transaction và câu lệnh hiện tại.
- Kế hoạch thực thi để hiểu phạm vi dữ liệu mà truy vấn đọc.
- Mã nghiệp vụ và thứ tự các thao tác đọc/ghi trong transaction.

## 6. Ví dụ write skew được PostgreSQL SERIALIZABLE phát hiện

Giả sử bảng doctor_on_call lưu trạng thái trực theo ca:

~~~sql
CREATE TABLE doctor_on_call (
    shift_id  integer NOT NULL,
    doctor_id integer NOT NULL,
    on_call   boolean NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);

INSERT INTO doctor_on_call (shift_id, doctor_id, on_call)
VALUES
    (10, 1, TRUE),
    (10, 2, TRUE);
~~~

Quy tắc nghiệp vụ: mỗi ca phải có ít nhất một bác sĩ đang trực.

Hai session cùng bắt đầu transaction ở mức SERIALIZABLE.

### Session A

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10
  AND on_call = TRUE;

-- Ứng dụng thấy có 2 bác sĩ đang trực.

UPDATE doctor_on_call
SET on_call = FALSE
WHERE shift_id = 10
  AND doctor_id = 1;

COMMIT;
~~~

### Session B chạy đồng thời

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT count(*)
FROM doctor_on_call
WHERE shift_id = 10
  AND on_call = TRUE;

-- Snapshot của B cũng có thể thấy 2 bác sĩ đang trực.

UPDATE doctor_on_call
SET on_call = FALSE
WHERE shift_id = 10
  AND doctor_id = 2;

COMMIT;
~~~

Nếu hai transaction chồng lấn và cùng đọc trạng thái ban đầu, mỗi transaction có thể tạo một phụ thuộc rw đối với transaction kia:

- A đọc dòng bác sĩ 2; B thay đổi dòng bác sĩ 2.
- B đọc dòng bác sĩ 1; A thay đổi dòng bác sĩ 1.

Nếu để cả hai commit, ca trực không còn bác sĩ nào. PostgreSQL SSI nhận diện chuỗi phụ thuộc tạo nguy cơ write skew và hủy một transaction. Ứng dụng nhận lỗi serialization failure thay vì cả hai thay đổi cùng được chấp nhận.

Lịch chạy thực tế quyết định transaction nào bị hủy và lỗi xuất hiện ở thời điểm nào. Không nên dựa vào thứ tự gửi câu lệnh từ hai client để khẳng định session A hay B luôn là bên thất bại.

**Lưu ý:** ví dụ minh họa logic của SSI. Để kiểm chứng, cần chạy hai session đồng thời với transaction mở chồng lấn; chạy tuần tự từng session sẽ không tạo cùng tình huống phụ thuộc.

## 7. Xử lý serialization failure trong ứng dụng

PostgreSQL báo serialization failure với SQLSTATE **40001**. Một thông báo thường gặp là:

~~~text
ERROR: could not serialize access due to read/write dependencies among transactions
SQLSTATE: 40001
~~~

Khi gặp lỗi này, ứng dụng phải rollback transaction và cân nhắc chạy lại **toàn bộ transaction**.

Quy trình đúng:

1. Bắt đầu transaction SERIALIZABLE mới.
2. Đọc lại toàn bộ dữ liệu cần thiết trên snapshot mới.
3. Tính toán lại các quyết định nghiệp vụ.
4. Thực hiện các thao tác ghi.
5. Commit.
6. Nếu tiếp tục gặp lỗi serialization, retry theo chính sách giới hạn.

Không chỉ chạy lại câu UPDATE cuối cùng. Kết quả tính toán trước đó có thể dựa trên snapshot cũ; nếu giữ nguyên kết quả cũ rồi ghi lại, ứng dụng có thể tái tạo chính anomaly mà SSI vừa ngăn chặn.

### 7.1. Mẫu retry ở tầng ứng dụng

Pseudocode:

~~~text
for attempt = 1..MAX_RETRIES:
    begin SERIALIZABLE transaction

    try:
        read required data
        validate business rules
        calculate changes
        write changes
        commit
        return success

    catch error:
        rollback transaction

        if SQLSTATE == 40001 and attempt < MAX_RETRIES:
            wait with bounded backoff and jitter
            continue

        raise error
~~~

Một số nguyên tắc khi triển khai:

- Retry toàn bộ đơn vị nghiệp vụ nằm trong transaction.
- Giới hạn số lần thử để tránh vòng lặp vô hạn.
- Có backoff và jitter để nhiều transaction cùng lỗi không lập tức va chạm lại.
- Chỉ retry lỗi tạm thời đã nhận diện, không retry lỗi validation nghiệp vụ hoặc dữ liệu không hợp lệ.
- Mỗi lần retry phải đọc lại dữ liệu và tính toán lại.
- Không phát sinh side effect bên ngoài database trước khi commit nếu side effect đó không có cơ chế idempotency.

Ví dụ, nếu transaction gửi email hoặc gọi cổng thanh toán rồi mới gặp lỗi 40001, retry toàn bộ transaction có thể gửi email hoặc thanh toán hai lần. Hãy dùng outbox, idempotency key hoặc một cơ chế phối hợp tương ứng để bảo vệ side effect.

Serialization failure là một phần bình thường trong mô hình SSI dưới tải cạnh tranh. Ứng dụng dùng SERIALIZABLE phải xem đây là kết quả có thể xảy ra và xử lý ngay từ thiết kế.

## 8. Transaction chỉ đọc và safe snapshot

Một số transaction chỉ đọc báo cáo, không cập nhật dữ liệu. PostgreSQL hỗ trợ chế độ:

~~~sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE
    READ ONLY
    DEFERRABLE;

SELECT ...
FROM ...;

COMMIT;
~~~

Với SERIALIZABLE READ ONLY DEFERRABLE, transaction có thể phải chờ trước khi lấy snapshot cho đến khi PostgreSQL xác định được một **safe snapshot**. Khi đã có snapshot an toàn, transaction chỉ đọc có thể chạy mà không có nguy cơ bị hủy do serialization failure.

Đánh đổi là thời gian bắt đầu transaction có thể dài hơn. Chế độ này hữu ích cho báo cáo dài hoặc tác vụ phân tích chỉ đọc, nơi việc chờ một chút trước khi bắt đầu dễ chấp nhận hơn việc bị hủy giữa chừng.

Không nên bật DEFERRABLE cho transaction có ghi. Đây là lựa chọn dành cho transaction READ ONLY ở isolation level SERIALIZABLE.

## 9. SSI khác gì với khóa hai pha nghiêm ngặt?

Một cách bảo đảm serializability khác là Strict Two-Phase Locking (Strict 2PL). Cả hai hướng đều có thể bảo đảm thứ tự tuần tự hợp lệ, nhưng cách phối hợp transaction khác nhau.

| Khía cạnh | Strict 2PL | SSI |
|---|---|---|
| Cách phối hợp | Dùng khóa để ngăn các lịch truy cập xung đột | Dùng snapshot và theo dõi phụ thuộc đọc/ghi |
| Reader và writer | Có thể block nhau khi yêu cầu khóa không tương thích | SIREAD không block writer; nhiều lượt đọc có thể tiếp tục trên snapshot |
| Xử lý xung đột | Transaction có thể phải chờ khóa | Transaction có thể bị hủy khi có nguy cơ không tuần tự hóa |
| Chi phí chính | Thời gian chờ, deadlock và quản lý khóa | Theo dõi predicate/dependency, serialization failure và retry |
| Phù hợp | Workload cần phối hợp bằng khóa và có thể chấp nhận blocking | Workload đọc nhiều, muốn giảm blocking nhưng có thể xử lý retry |

SSI không có nghĩa database không dùng khóa. PostgreSQL vẫn sử dụng khóa cho các mục đích khác, bao gồm cập nhật dữ liệu, DDL và các thao tác khóa tường minh. Khác biệt ở đây là cách SERIALIZABLE phát hiện phụ thuộc rw để bảo đảm tính tuần tự hóa mà không cần chặn mọi lượt đọc theo kiểu khóa chia sẻ.

## 10. Điều kiện để nhận được bảo đảm SERIALIZABLE

Để bảo vệ một invariant nghiệp vụ, cần xem xét toàn bộ các transaction có thể tác động đến invariant đó.

Nếu một luồng cập nhật dùng SERIALIZABLE nhưng một luồng khác cập nhật cùng dữ liệu ở isolation level yếu hơn mà không có constraint hoặc cơ chế phối hợp bổ sung, không nên mặc định toàn bộ workload đều được bảo vệ như một nhóm transaction SERIALIZABLE.

Các thao tác liên quan đến cùng một quy tắc cần có chiến lược nhất quán:

- Dùng SERIALIZABLE cho tất cả transaction tham gia vào invariant cần bảo vệ; hoặc
- Bảo vệ invariant bằng constraint, khóa tường minh, guard row hay cập nhật nguyên tử mà mọi luồng ghi đều tuân thủ.

Ví dụ, nếu quy tắc là mỗi ca có ít nhất một người trực, mọi API, batch job và tác vụ quản trị có thể thay đổi on_call đều phải đi qua cơ chế bảo vệ đó. Một API dùng SERIALIZABLE không thể tự sửa lỗi cho một batch job khác ghi dữ liệu tùy ý ngoài quy tắc.

## 11. Khi nào cần điều tra serialization failure?

Không phải cứ có lỗi 40001 là thiết kế database sai. SSI có thể hủy transaction để bảo vệ serializability; điều cần điều tra là tần suất và nguyên nhân của các lần hủy.

Các dấu hiệu nên theo dõi:

- Tỷ lệ serialization failure trên tổng số transaction.
- Transaction hoặc câu truy vấn thường xuyên xuất hiện trong các lỗi 40001.
- Thời gian transaction mở và mức độ chồng lấn giữa các transaction.
- Các truy vấn quét phạm vi rộng hoặc thiếu index phù hợp.
- Các invariant được kiểm tra bằng nhiều câu SELECT trước khi cập nhật các dòng khác nhau.
- Số lần retry và tỷ lệ retry thành công.
- Thời gian chờ trước khi commit và thời gian xử lý lại sau khi retry.

Có thể xem các SIREAD lock hiện hành bằng pg_locks, nhưng không nên chỉ dựa vào số lượng SIReadLock để kết luận nguyên nhân. Serialization graph là quan hệ logic giữa nhiều transaction; một ảnh chụp pg_locks tại một thời điểm không thể hiện đầy đủ lịch sử phụ thuộc.

### Các nguyên nhân thường gặp và hướng xử lý

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| Nhiều transaction cùng kiểm tra một điều kiện rồi sửa các dòng khác nhau | Write skew trên invariant nhiều dòng | Xem lại các lượt đọc, tập ghi và dangerous structure |
| Truy vấn đọc quét toàn bảng | Predicate được theo dõi ở phạm vi rộng | Kiểm tra execution plan và index phù hợp |
| Transaction mở lâu | Nhiều transaction chồng lấn, giữ thông tin phụ thuộc lâu hơn | Rút ngắn transaction và bỏ thao tác ngoài database khỏi transaction |
| Retry liên tục thất bại | Nhiều request cùng tranh chấp và retry đồng thời | Dùng backoff/jitter, giới hạn retry hoặc tuần tự hóa theo nhóm nghiệp vụ |
| Lỗi xuất hiện sau khi thêm một luồng ghi mới | Luồng mới thay đổi dữ liệu thuộc predicate mà transaction khác đọc | Kiểm tra toàn bộ writer và isolation level của chúng |

Không nên giải quyết serialization failure bằng cách hạ toàn bộ transaction xuống READ COMMITTED nếu transaction đó đang bảo vệ một invariant quan trọng. Trước tiên phải xác định quy tắc nghiệp vụ nào đang cần bảo vệ và lựa chọn cơ chế phối hợp phù hợp.

## 12. Giảm chi phí SSI mà vẫn giữ tính đúng đắn

Một số thay đổi có thể giảm phạm vi đọc và số lần xung đột bảo thủ:

**Giữ transaction ngắn.** Không giữ transaction SERIALIZABLE trong lúc chờ người dùng, gọi dịch vụ ngoài hoặc thực hiện công việc không liên quan đến database. Thời gian chồng lấn càng dài thì càng có cơ hội xuất hiện quan hệ phụ thuộc với transaction khác.

**Tối ưu truy vấn đọc.** Điều kiện lọc rõ ràng và index phù hợp có thể giúp database đọc phạm vi hẹp hơn. Điều này vừa giảm chi phí truy vấn vừa có thể giảm phạm vi predicate cần theo dõi.

**Giảm số lần đọc không cần thiết.** Không đọc lại cùng dữ liệu nhiều lần nếu kết quả có thể được dùng trong cùng transaction. Tuy nhiên, phải giữ nguyên ý nghĩa nghiệp vụ và không loại bỏ lượt đọc cần thiết để bảo vệ invariant.

**Chia công việc theo khóa nghiệp vụ.** Nếu các thao tác thuộc những ca trực, tài khoản hoặc nhóm tài nguyên độc lập, có thể tổ chức xử lý theo từng nhóm. Cần bảo đảm các transaction giao nhau vẫn được phối hợp đúng.

**Đặt retry ở đúng ranh giới.** Retry phải bao trọn thao tác đọc, kiểm tra và ghi. Không retry từng câu lệnh rời rạc bằng dữ liệu cũ.

**Đo trước khi thay đổi cấu hình predicate lock.** PostgreSQL có các thiết lập giới hạn bộ nhớ dành cho predicate lock. Tăng giới hạn có thể giảm việc phải gộp thông tin theo dõi ở mức rộng, nhưng tiêu thụ thêm bộ nhớ. Không nên thay đổi chỉ vì thấy một vài lỗi 40001; trước tiên hãy kiểm tra truy vấn, transaction và tỷ lệ lỗi thực tế.

Không thể loại bỏ mọi serialization failure mà vẫn giữ nguyên mức bảo đảm SERIALIZABLE dưới workload có xung đột thực sự. Mục tiêu là giảm xung đột không cần thiết và làm cho retry an toàn, nhanh chóng.

## 13. So sánh các mức cô lập liên quan

Trong PostgreSQL, các isolation level có hành vi khác nhau:

| Isolation level | Cách đọc chính | Bảo đảm tuần tự hóa |
|---|---|---|
| READ COMMITTED | Snapshot mới cho mỗi câu lệnh | Không bảo đảm toàn transaction tuần tự hóa |
| REPEATABLE READ | Snapshot ổn định trong transaction | Tương đương snapshot isolation; vẫn có thể xảy ra write skew |
| SERIALIZABLE | Snapshot cùng theo dõi phụ thuộc rw bằng SSI | Các transaction SERIALIZABLE commit được bảo đảm tương đương một thứ tự tuần tự |

REPEATABLE READ trong PostgreSQL không nên được hiểu là SERIALIZABLE chỉ vì nó giữ snapshot ổn định. Một snapshot cố định bảo đảm tính nhất quán của lượt đọc, nhưng không tự phát hiện mọi chu trình phụ thuộc giữa các transaction.

SERIALIZABLE bổ sung cơ chế SSI để phát hiện các dangerous structure. Đổi lại, ứng dụng cần xử lý serialization failure.

## 14. Những nguyên tắc cần ghi nhớ

- Snapshot isolation có thể gặp write skew khi các transaction đọc dữ liệu liên quan nhưng ghi vào những dòng khác nhau.
- Đồ thị tuần tự hóa biểu diễn các quan hệ phụ thuộc giữa transaction; chu trình trong đồ thị cho thấy lịch thực thi không thể sắp xếp thành thứ tự tuần tự hợp lệ.
- Cạnh rw biểu diễn việc một transaction đọc dữ liệu hoặc predicate trước thay đổi của transaction khác.
- Dangerous structure có dạng \(T_{in} \xrightarrow{rw} T_{pivot} \xrightarrow{rw} T_{out}\); transaction ở giữa là pivot.
- Dangerous structure là dấu hiệu cần kiểm tra, chưa chắc tự nó đã tạo thành chu trình. SSI dùng thêm điều kiện để quyết định hủy transaction.
- PostgreSQL dùng SIREAD predicate locks để theo dõi lượt đọc; chúng không hoạt động như khóa thông thường chặn writer.
- SERIALIZABLE có thể hủy transaction với SQLSTATE 40001 để bảo vệ tính tuần tự hóa.
- Khi retry, phải rollback và chạy lại toàn bộ transaction trên snapshot mới.
- SERIALIZABLE READ ONLY DEFERRABLE phù hợp với một số tác vụ đọc dài có thể chấp nhận chờ safe snapshot lúc bắt đầu.
- Mọi luồng ghi có thể ảnh hưởng đến cùng invariant cần tuân thủ một chiến lược bảo vệ nhất quán.

SSI cho phép hệ quản trị giữ lợi ích của snapshot read trong nhiều tình huống đồng thời, đồng thời phát hiện những quan hệ phụ thuộc có thể phá vỡ tính tuần tự hóa. Hiểu dangerous structure giúp giải thích vì sao một transaction không hề bị block vẫn có thể bị hủy khi commit: vấn đề nằm ở thứ tự logic giữa các lần đọc và ghi, không chỉ ở việc hai transaction có khóa cùng một dòng hay không.

