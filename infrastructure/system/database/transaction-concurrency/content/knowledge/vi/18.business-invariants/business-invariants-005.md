# Lịch trực và lựa chọn bảo vệ bất biến tồn tại ít nhất một người

Giả sử một hệ thống quản lý lịch trực có nhiều người được phân công cho mỗi ca. Quy tắc nghiệp vụ yêu cầu **mỗi ca luôn phải có ít nhất một người đang trực**. Khi hai quản trị viên cùng thao tác, một người có thể tắt trạng thái trực của bác sĩ A trong khi người kia tắt trạng thái trực của bác sĩ B. Mỗi thao tác riêng lẻ có vẻ hợp lệ, nhưng nếu cả hai cùng thành công thì ca trực không còn ai phụ trách.

Đây là một bất biến nghiệp vụ liên quan đến nhiều dòng dữ liệu. Nó cho thấy vì sao chỉ kiểm tra điều kiện trong ứng dụng hoặc khóa riêng dòng đang sửa có thể chưa đủ.

Có một số cách bảo vệ:

- Dùng **SERIALIZABLE** để database ngăn lịch thực thi đồng thời tạo ra trạng thái không thể tuần tự hóa.
- Dùng **guard row** hoặc advisory lock để buộc mọi thay đổi của cùng một ca trực đi qua một điểm điều phối chung.
- Lưu **bộ đếm người đang trực** trên một dòng đại diện cho ca và cập nhật bộ đếm cùng dữ liệu phân công trong một transaction.
- Thiết kế lại mô hình dữ liệu để biểu diễn người chịu trách nhiệm bắt buộc bằng một quan hệ mà database có thể bảo vệ.

Mỗi cách có chi phí và giả định khác nhau. Lựa chọn phụ thuộc vào database engine, tần suất cập nhật cùng một ca, khả năng kiểm soát mọi đường ghi và yêu cầu về throughput.

## 1. Xác định bất biến nghiệp vụ

Giả sử dữ liệu được lưu trong bảng phân công:

~~~sql
CREATE TABLE shift_assignments (
    shift_id BIGINT NOT NULL,
    doctor_id BIGINT NOT NULL,
    on_call BOOLEAN NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
~~~

Một ca trực có thể có nhiều dòng. Cột on_call cho biết người đó có đang trực hay không.

Bất biến cần giữ là:

~~~text
Với mọi shift_id:
    COUNT(assignment WHERE on_call = true) >= 1
~~~

Ví dụ trạng thái hợp lệ:

| shift_id | doctor_id | on_call |
|---:|---:|---|
| 10 | 101 | true |
| 10 | 102 | true |
| 10 | 103 | false |

Ca 10 có hai người đang trực, nên có thể cho một người nghỉ.

Trạng thái sau đây không hợp lệ:

| shift_id | doctor_id | on_call |
|---:|---:|---|
| 10 | 101 | false |
| 10 | 102 | false |
| 10 | 103 | false |

Không còn người nào trực. Nếu hệ thống lưu trạng thái này, lịch trực vi phạm quy tắc nghiệp vụ dù từng câu UPDATE đều có thể đã thực hiện thành công.

### Vì sao CHECK constraint trên một dòng chưa đủ?

Một CHECK constraint thông thường đánh giá giá trị của dòng đang INSERT hoặc UPDATE. Nó không thể trực tiếp đếm các dòng khác trong cùng ca trực.

Ví dụ:

~~~sql
CHECK (on_call = true)
~~~

sẽ cấm mọi dòng có on_call = false, không diễn đạt được quy tắc cần ít nhất một người trực.

Còn biểu thức kiểu:

~~~sql
CHECK (
    (SELECT COUNT(*) FROM shift_assignments
     WHERE shift_id = shift_assignments.shift_id
       AND on_call = true) >= 1
)
~~~

không phải cách khai báo CHECK hợp lệ trong nhiều hệ quản trị quan hệ, và ngay cả khi dùng trigger hoặc logic tương tự để đếm, việc kiểm tra vẫn phải được bảo vệ trước các transaction đồng thời. Hai transaction có thể cùng đọc một trạng thái hợp lệ rồi cùng ghi các dòng khác nhau.

Vì vậy, bài toán không chỉ là viết câu kiểm tra COUNT. Cần bảo vệ cả **điểm kiểm tra và thay đổi dữ liệu** trước cạnh tranh.

## 2. Write skew: vì sao khóa riêng từng dòng vẫn có thể sai?

Giả sử ca trực đang có hai người A và B. Hai transaction cùng đọc số người trực và cùng muốn cho một người nghỉ.

~~~text
Trạng thái ban đầu: A = ON, B = ON

T1                                      T2
----------------------------------      ----------------------------------
BEGIN                                   BEGIN
Đọc: có 2 người trực                    Đọc: có 2 người trực
Kiểm tra: nếu còn > 1 thì cho A nghỉ     Kiểm tra: nếu còn > 1 thì cho B nghỉ
UPDATE A = OFF                          UPDATE B = OFF
COMMIT                                  COMMIT
~~~

Mỗi transaction ghi một dòng khác nhau. Nếu isolation level cho phép cả hai cùng commit dựa trên snapshot đã đọc, kết quả là A và B đều OFF.

Hiện tượng này là **write skew**: các transaction đọc những dữ liệu có liên quan đến nhau nhưng cập nhật các dòng khác nhau, nên không nhất thiết có write-write conflict trực tiếp trên cùng một dòng.

Khóa riêng dòng A trong T1 và dòng B trong T2 không giải quyết được vấn đề. T1 không chờ lock trên A do T2 giữ, và T2 cũng không chờ lock trên B do T1 giữ. Điều cần bảo vệ là bất biến ở cấp ca trực, không phải riêng từng dòng phân công.

Đây là lý do phải chọn một cơ chế đồng bộ chung hoặc một isolation guarantee đủ mạnh.

## 3. Cách 1: SERIALIZABLE isolation

SERIALIZABLE yêu cầu kết quả của các transaction đồng thời tương đương với một thứ tự thực thi tuần tự hợp lệ. Nếu database phát hiện hai transaction có phụ thuộc đọc/ghi khiến cả hai cùng commit sẽ tạo ra kết quả không tuần tự hóa được, engine phải ngăn kết quả đó.

Một transaction có thể thực hiện:

~~~sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_count
FROM shift_assignments
WHERE shift_id = 10
  AND on_call = true;

-- Chỉ cho phép tắt một người nếu active_count > 1.
UPDATE shift_assignments
SET on_call = false
WHERE shift_id = 10
  AND doctor_id = 101
  AND on_call = true;

COMMIT;
~~~

Đoạn SQL trên là minh họa PostgreSQL. Ứng dụng phải kiểm tra số người trực trước khi UPDATE và xác nhận câu UPDATE tác động đúng một dòng. Nếu điều kiện không còn hợp lệ, transaction không thực hiện thay đổi.

Với PostgreSQL, SERIALIZABLE dùng Serializable Snapshot Isolation (SSI) để theo dõi các phụ thuộc đọc/ghi. Một transaction có thể bị hủy với SQLSTATE 40001 nếu database phát hiện nguy cơ serialization anomaly. Với hai thao tác write skew ở trên, database có thể cho một transaction commit và hủy transaction còn lại.

Sau khi retry toàn bộ transaction bị hủy:

1. Transaction đọc lại số người đang trực.
2. Nó thấy chỉ còn một người.
3. Điều kiện active_count > 1 không còn đúng.
4. Ứng dụng từ chối yêu cầu cho người cuối cùng nghỉ.

### Retry phải chạy lại toàn bộ transaction

Không được chỉ chạy lại câu UPDATE cuối cùng. Các lần đọc trước đó đã dựa trên snapshot cũ. Khi nhận serialization failure, ứng dụng cần rollback transaction cũ, bắt đầu transaction mới, đọc lại số người trực và kiểm tra lại điều kiện.

Pseudocode:

~~~text
for attempt in 1..MAX_ATTEMPTS:
    BEGIN SERIALIZABLE

    active_count = COUNT(on_call = true for shift)

    if active_count <= 1:
        ROLLBACK
        return CANNOT_REMOVE_LAST_ON_CALL_PERSON

    updated = UPDATE selected assignment to OFF

    if updated != 1:
        ROLLBACK
        return ASSIGNMENT_CHANGED

    COMMIT
    return SUCCESS

catch serialization_failure:
    ROLLBACK
    retry whole transaction with bounded backoff

return TEMPORARY_CONFLICT
~~~

Một số database dùng locking để thực thi SERIALIZABLE, một số dùng snapshot isolation kèm cơ chế phát hiện xung đột. Không nên giả định tất cả engine sẽ chặn transaction theo cùng cách. Kết quả có thể là chờ lock, serialization failure hoặc một loại lỗi concurrency khác.

### Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
|---|---|
| Bảo vệ các phụ thuộc giữa nhiều dòng mà không cần tự thiết kế một guard row cho từng quy tắc | Có thể tăng serialization failure và số lần retry |
| Logic nghiệp vụ có thể giữ gần với cách đọc và kiểm tra tự nhiên | Phải xử lý retry toàn bộ transaction |
| Có thể bảo vệ nhiều loại bất biến đọc/ghi phức tạp | Cần hiểu chính xác cách engine triển khai SERIALIZABLE |
| Không cần tạo một điểm điều phối riêng cho từng ca trong mô hình đơn giản | Transaction dài và truy vấn đọc rộng có thể làm tăng xung đột |

SERIALIZABLE là lựa chọn tốt khi quy tắc liên quan đến nhiều dòng và hệ thống có thể xử lý retry đúng cách. Nếu một ca trực bị thay đổi liên tục, tỷ lệ transaction bị hủy có thể cao; khi đó guard row hoặc bộ đếm có thể dễ dự đoán hơn.

## 4. Cách 2: Khóa một guard row chung cho mỗi ca trực

Guard row là một dòng đại diện cho tài nguyên nghiệp vụ cần được điều phối. Mọi transaction thay đổi lịch trực của cùng một ca phải khóa hoặc cập nhật dòng guard trước khi đọc số người trực và thay đổi phân công.

Ví dụ tạo bảng:

~~~sql
CREATE TABLE shift_guard (
    shift_id BIGINT PRIMARY KEY,
    revision BIGINT NOT NULL DEFAULT 0
);
~~~

Mỗi ca trực có đúng một dòng guard. Với PostgreSQL ở READ COMMITTED, transaction có thể dùng SELECT FOR UPDATE:

~~~sql
BEGIN;

-- Luôn lấy guard trước khi đọc hoặc sửa phân công của ca.
SELECT shift_id
FROM shift_guard
WHERE shift_id = 10
FOR UPDATE;

-- Sau khi có guard lock, đọc trạng thái mới nhất.
SELECT COUNT(*) AS active_count
FROM shift_assignments
WHERE shift_id = 10
  AND on_call = true;

-- Nếu active_count > 1, mới được cho một người nghỉ.
UPDATE shift_assignments
SET on_call = false
WHERE shift_id = 10
  AND doctor_id = 101
  AND on_call = true;

COMMIT;
~~~

Giả sử T1 và T2 cùng muốn cho A và B nghỉ:

~~~text
T1                                      T2
----------------------------------      ----------------------------------
BEGIN                                   BEGIN
Lock guard của shift 10                 Xin lock guard của shift 10
Đếm: 2 người trực                      Chờ T1
Tắt A
COMMIT, nhả guard
                                        Lấy được guard
                                        Đếm lại: 1 người trực
                                        Từ chối tắt B
                                        ROLLBACK
~~~

T2 phải đợi T1 hoàn tất. Khi T2 tiếp tục đọc trạng thái sau khi đã lấy guard, nó thấy kết quả T1 đã commit và không thể cùng dựa trên số đếm ban đầu là 2.

### Điều kiện bắt buộc của guard row

Guard row chỉ bảo vệ được bất biến nếu **mọi đường ghi có thể thay đổi trạng thái on_call đều tuân thủ cùng giao thức**:

- Cho một người nghỉ.
- Thêm người trực.
- Hủy phân công.
- Chuyển người sang ca khác.
- Tác vụ nền hoặc batch sửa lịch.
- Công cụ quản trị hoặc service khác cập nhật trực tiếp bảng.

Nếu một đường ghi bỏ qua guard, nó có thể phá vỡ bất biến.

Cần thống nhất thứ tự lấy lock. Nếu một transaction thay đổi nhiều ca trực, tất cả transaction nên lấy guard theo thứ tự shift_id tăng dần để giảm nguy cơ deadlock.

### Dùng UPDATE guard để tạo điểm tuần tự hóa

Một số engine có snapshot theo transaction hoặc cần bảo đảm transaction cạnh tranh thực sự xung đột trên cùng dòng guard. Có thể cập nhật revision thay vì chỉ đọc khóa:

~~~sql
BEGIN;

UPDATE shift_guard
SET revision = revision + 1
WHERE shift_id = 10;

-- Kiểm tra đúng một dòng guard đã được cập nhật.
-- Sau đó đọc số người trực và cập nhật assignment.

COMMIT;
~~~

Việc UPDATE cùng một dòng tạo write-write conflict rõ ràng giữa các transaction. Với PostgreSQL ở REPEATABLE READ hoặc SERIALIZABLE, transaction có snapshot cũ có thể nhận serialization failure khi cố cập nhật một dòng đã được transaction khác thay đổi; ứng dụng phải retry toàn bộ transaction.

Với các engine dùng snapshot hoặc current read khác nhau, cần bảo đảm truy vấn đếm sau khi lấy guard nhìn thấy commit của transaction trước. Một cách triển khai đơn giản là lấy guard trước mọi consistent read trong transaction và chọn isolation level phù hợp. Hãy kiểm tra semantics của engine đang dùng.

### Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
|---|---|
| Cách hiểu và triển khai trực quan | Mọi writer phải tuân thủ giao thức guard |
| Có thể chỉ tuần tự hóa thay đổi của cùng một ca | Các thay đổi trên cùng ca phải chờ nhau |
| Không cần dùng SERIALIZABLE cho mọi transaction nếu READ COMMITTED và guard được áp dụng đúng | Guard có thể trở thành điểm nóng nếu một ca có tần suất cập nhật rất cao |
| Dễ quan sát và điều tra qua lock trên dòng guard | Phải xử lý thứ tự lock khi một transaction thay đổi nhiều ca |

Guard row phù hợp khi bất biến có phạm vi rõ ràng, ví dụ một ca trực, một phòng, một lớp học hoặc một tài khoản tổng hợp. Nó cho phép các ca khác nhau vẫn được cập nhật đồng thời vì mỗi ca có guard riêng.

## 5. Cách 3: Dùng bộ đếm trên dòng đại diện cho ca trực

Một cách khác là lưu số người đang trực trên chính dòng shift. Database có thể bảo vệ điều kiện bằng một CHECK constraint đơn giản trên dòng đó.

~~~sql
CREATE TABLE shifts (
    shift_id BIGINT PRIMARY KEY,
    on_call_count INTEGER NOT NULL,
    CONSTRAINT ck_shift_has_on_call
        CHECK (on_call_count >= 1)
);
~~~

Khi cho một người nghỉ, ứng dụng giảm bộ đếm với điều kiện chỉ giảm nếu số người đang trực lớn hơn 1:

~~~sql
UPDATE shifts
SET on_call_count = on_call_count - 1
WHERE shift_id = 10
  AND on_call_count > 1;
~~~

Nếu affected rows bằng 1, hệ thống đã dành được quyền giảm bộ đếm. Nếu bằng 0, ca không tồn tại hoặc chỉ còn một người trực.

Cập nhật bảng phân công phải nằm trong cùng transaction:

~~~sql
BEGIN;

UPDATE shifts
SET on_call_count = on_call_count - 1
WHERE shift_id = 10
  AND on_call_count > 1;

-- Ứng dụng kiểm tra affected rows.
-- Nếu không phải 1, ROLLBACK và báo không thể cho người cuối cùng nghỉ.

UPDATE shift_assignments
SET on_call = false
WHERE shift_id = 10
  AND doctor_id = 101
  AND on_call = true;

-- Nếu UPDATE assignment không tác động đúng một dòng,
-- ROLLBACK để hoàn tác cả thay đổi bộ đếm.

COMMIT;
~~~

Hai transaction cùng giảm số người trực sẽ tranh chấp trên dòng shifts của ca đó. Database tuần tự hóa các UPDATE trên dòng này. Nếu bộ đếm đang là 2:

- Transaction đầu giảm thành 1.
- Transaction sau chờ, sau đó điều kiện on_call_count > 1 không còn đúng.
- UPDATE thứ hai ảnh hưởng 0 dòng.
- Không thể giảm bộ đếm xuống 0.

CHECK constraint là lớp bảo vệ bổ sung: ngay cả một đường ghi cố đặt on_call_count thành 0 cũng bị database từ chối.

### Bộ đếm phải luôn khớp với bảng phân công

Bộ đếm chỉ đáng tin khi được duy trì cùng mọi thay đổi phân công:

- Thêm một người vào trạng thái on_call: tăng bộ đếm.
- Cho một người nghỉ: giảm bộ đếm.
- Xóa hoặc chuyển một người đang trực: giảm bộ đếm của ca cũ.
- Chuyển người vào ca mới: tăng bộ đếm của ca mới.
- Hủy phân công hoặc khôi phục phân công: cập nhật tương ứng.

Các thay đổi cần nằm trong cùng transaction. Có thể dùng stored procedure, trigger được thiết kế có khóa phù hợp hoặc một lớp service duy nhất có quyền ghi. Nếu một đường ghi sửa assignment nhưng quên cập nhật bộ đếm, hai bảng sẽ lệch nhau.

Một tác vụ đối soát có thể định kỳ so sánh bộ đếm với COUNT thực tế để phát hiện lỗi dữ liệu. Đối soát không thay thế bảo vệ đồng thời, nhưng giúp phát hiện sai lệch do migration hoặc đường ghi ngoài dự kiến.

### Ưu điểm và giới hạn

| Ưu điểm | Giới hạn |
|---|---|
| Điều kiện ít nhất một người trực được biểu diễn bằng CHECK trên một dòng | Phải duy trì bộ đếm chính xác |
| UPDATE có điều kiện tạo ra điểm đồng bộ rõ ràng | Dòng shifts trở thành điểm tranh chấp cho mọi thay đổi cùng ca |
| Có thể tránh truy vấn COUNT trên nhiều assignment trong mỗi lần thay đổi | Cần xử lý đúng các thao tác thêm, xóa, chuyển ca và phục hồi |
| Dễ kiểm tra invariant bằng dữ liệu tổng hợp | Có thể cần migration và đối soát dữ liệu hiện có |

Bộ đếm phù hợp khi quy tắc được truy cập thường xuyên và số lượng liên quan có thể duy trì đáng tin cậy. Nó đặc biệt hữu ích nếu hệ thống vốn đã có một dòng tổng hợp đại diện cho mỗi ca.

## 6. Cách 4: Dùng advisory lock hoặc application lock

Một số database cung cấp khóa logic do ứng dụng đặt tên hoặc gắn với một khóa định danh, thay vì khóa một dòng dữ liệu cụ thể.

Ví dụ PostgreSQL có transaction-level advisory lock:

~~~sql
BEGIN;

SELECT pg_advisory_xact_lock(10);

-- Kiểm tra số người đang trực của shift 10.
-- Nếu còn hơn một người, cập nhật phân công.

COMMIT;
~~~

Ví dụ trên dùng một khóa số để minh họa. Trong ứng dụng thực tế, cần ánh xạ shift_id thành khóa advisory ổn định, tránh đụng độ với các loại khóa logic khác. Transaction-level advisory lock tự nhả khi transaction kết thúc.

SQL Server có application lock qua sp_getapplock. Các sản phẩm khác có cơ chế tương tự hoặc có thể dùng một bảng guard row.

Advisory/application lock hữu ích khi tài nguyên cần điều phối là một khái niệm nghiệp vụ không tương ứng trực tiếp với một dòng. Nhưng chúng có cùng một điều kiện quan trọng như guard row: mọi đường ghi phải dùng cùng khóa logic. Nếu một service cập nhật bảng mà không lấy advisory lock, cơ chế không bảo vệ được bất biến.

Không nên giữ advisory lock trong lúc gọi HTTP API hoặc chờ người dùng. Khóa logic vẫn là tài nguyên đồng bộ; giữ nó quá lâu sẽ làm các transaction cùng tài nguyên phải chờ.

## 7. Có thể dùng trigger để bảo vệ bất biến không?

Trigger có thể tự động chạy khi INSERT, UPDATE hoặc DELETE, giúp gom quy tắc ở database thay vì dựa vào từng service. Tuy nhiên, trigger chỉ giải quyết việc mọi đường ghi đều đi qua logic kiểm tra; nó không tự động giải quyết race condition.

Một trigger kiểu:

~~~text
Khi một assignment chuyển ON -> OFF:
    COUNT số assignment đang ON
    Nếu count <= 1:
        từ chối UPDATE
~~~

vẫn có thể gặp write skew nếu hai transaction cùng chạy trigger, mỗi transaction đếm snapshot thấy hai người đang trực rồi cập nhật hai dòng khác nhau. Trigger cần lấy guard lock, cập nhật bộ đếm có điều kiện hoặc chạy dưới cơ chế isolation có bảo vệ phù hợp.

Nếu dùng trigger, cần thiết kế rõ:

- Trigger chạy trên INSERT, UPDATE và DELETE nào.
- Cách xử lý chuyển assignment giữa hai shift.
- Thứ tự lấy guard khi một thao tác tác động nhiều shift.
- Kiểm tra cuối transaction hay ngay tại statement.
- Hành vi khi trigger phát hiện vi phạm.
- Cách migration và batch update tương tác với trigger.

Trigger có thể là nơi thực thi tốt cho quy tắc, nhưng concurrency control vẫn phải được thiết kế và kiểm chứng.

## 8. So sánh các lựa chọn

| Tiêu chí | SERIALIZABLE | Guard row | Bộ đếm + CHECK | Advisory/application lock |
|---|---|---|---|---|
| Cơ chế | Database phát hiện hoặc ngăn lịch không tuần tự hóa được | Khóa dòng đại diện cho ca | UPDATE có điều kiện trên dòng tổng hợp | Khóa logic theo định danh ca |
| Bảo vệ write skew | Có, nếu engine và transaction sử dụng đúng SERIALIZABLE | Có, nếu mọi writer lấy guard trước khi kiểm tra/sửa | Có, nếu bộ đếm được cập nhật nguyên tử cùng assignment | Có, nếu mọi writer lấy cùng khóa logic |
| Cách xử lý cạnh tranh | Có thể chờ hoặc abort/retry | Transaction cùng ca chờ nhau | UPDATE trên dòng tổng hợp tuần tự hóa | Transaction cùng khóa logic chờ nhau |
| Chi phí triển khai | Thấp đến trung bình, cần retry đúng | Trung bình, cần giao thức chung | Cao hơn vì phải duy trì bộ đếm | Trung bình, phụ thuộc API của engine |
| Điểm nóng | Phụ thuộc phạm vi xung đột và SSI/locking | Một guard cho mỗi ca | Một dòng counter cho mỗi ca | Một khóa logic cho mỗi ca |
| Khả năng áp dụng | Quy tắc nhiều dòng và phụ thuộc phức tạp | Bất biến có phạm vi rõ ràng | Bất biến có thể biểu diễn bằng bộ đếm | Tài nguyên logic không có dòng đại diện |
| Rủi ro chính | Retry nhiều hoặc lỗi serialization | Writer bỏ qua guard | Counter lệch với dữ liệu chi tiết | Writer bỏ qua advisory lock |

Không có lựa chọn tốt nhất cho mọi hệ thống. Nếu database đã hỗ trợ SERIALIZABLE tốt và ứng dụng có retry đáng tin cậy, đây là cách tổng quát. Nếu chỉ cần tuần tự hóa thay đổi của từng ca, guard row thường dễ vận hành. Nếu số người trực là dữ liệu tổng hợp được dùng thường xuyên, counter cùng CHECK có thể biểu diễn bất biến rõ ràng. Advisory lock phù hợp khi cần khóa một tài nguyên nghiệp vụ mà không muốn tạo dòng guard riêng.

## 9. Các lỗi triển khai thường gặp

### 9.1. Chỉ kiểm tra trong Java rồi UPDATE

~~~java
if (repository.countOnCall(shiftId) > 1) {
    repository.markOff(shiftId, doctorId);
}
~~~

Hai request có thể cùng nhận kết quả count = 2 trước khi một request cập nhật. Kiểm tra ở ứng dụng không tạo ra một vùng nguyên tử giữa COUNT và UPDATE.

Cần đưa kiểm tra vào transaction có cơ chế bảo vệ, như SERIALIZABLE, guard row hoặc bộ đếm.

### 9.2. Chỉ khóa dòng bác sĩ đang sửa

T1 khóa dòng A, T2 khóa dòng B. Vì hai dòng khác nhau, cả hai có thể tiếp tục. Bất biến lại nằm ở tổng số người trực của ca, nên phải khóa hoặc điều phối một tài nguyên chung.

### 9.3. Guard row nhưng một đường ghi bỏ qua

Nếu màn hình quản trị dùng guard nhưng batch job cập nhật trực tiếp assignment, batch job có thể phá vỡ invariant. Cần gom quyền ghi qua một service/stored procedure hoặc kiểm soát quyền database để mọi đường ghi tuân thủ cùng giao thức.

### 9.4. Retry serialization failure nhưng không đọc lại dữ liệu

Retry chỉ câu UPDATE hoặc giữ lại kết quả COUNT cũ không giải quyết được write skew. Phải chạy lại toàn bộ transaction và kiểm tra điều kiện trên trạng thái mới.

### 9.5. Bộ đếm và assignment cập nhật ở hai transaction khác nhau

Nếu giảm counter commit trước nhưng cập nhật assignment thất bại, dữ liệu tổng hợp không còn khớp. Hai thay đổi phải cùng commit hoặc cùng rollback.

### 9.6. Giữ lock trong khi thực hiện công việc bên ngoài

Không gọi dịch vụ thông báo, gửi email hoặc chờ người dùng trong lúc giữ guard/row lock. Hãy commit thay đổi lịch trước, ghi sự kiện Outbox cùng transaction nếu cần gửi thông báo, rồi để worker xử lý sau commit.

## 10. Kiểm thử bất biến dưới tải đồng thời

Một kiểm thử đơn luồng chỉ chứng minh logic cơ bản; nó không chứng minh invariant được giữ khi có cạnh tranh. Cần tạo hai transaction thực sự chạy đồng thời.

Kịch bản kiểm thử:

1. Tạo ca trực có đúng hai người A và B đang trực.
2. Mở hai transaction ở hai connection độc lập.
3. T1 đọc và yêu cầu cho A nghỉ.
4. T2 đọc và yêu cầu cho B nghỉ.
5. Dùng barrier để cả hai cùng đi qua thời điểm đọc trước khi cho phép ghi.
6. Cho cả hai transaction tiếp tục và commit hoặc xử lý lỗi theo cơ chế đã chọn.
7. Đọc lại dữ liệu sau khi cả hai kết thúc.
8. Xác nhận COUNT(on_call = true) vẫn lớn hơn hoặc bằng 1.

Kết quả mong đợi tùy chiến lược:

| Chiến lược | Kết quả mong đợi |
|---|---|
| Không có bảo vệ phù hợp | Có thể tái hiện trạng thái 0 người trực |
| SERIALIZABLE | Một transaction có thể bị abort; sau retry, yêu cầu cho người cuối cùng nghỉ bị từ chối |
| Guard row | Hai thao tác được tuần tự hóa; thao tác thứ hai thấy chỉ còn một người |
| Counter + CHECK | Một UPDATE giảm counter thành công; UPDATE còn lại không khớp điều kiện |
| Advisory lock | Chỉ một transaction cùng ca đi qua vùng kiểm tra tại một thời điểm |

Ngoài trường hợp hai người cùng nghỉ, cần kiểm thử các thao tác cạnh tranh khác:

- Thêm người trực trong lúc một người đang được cho nghỉ.
- Chuyển người từ ca A sang ca B.
- Hủy phân công cùng lúc với thao tác nghỉ.
- Hai request cùng cho một người nghỉ.
- Batch update nhiều ca theo thứ tự khác nhau.
- Transaction bị timeout hoặc crash trước COMMIT.
- Retry sau serialization failure hoặc deadlock.

Với counter, kiểm tra cả hai điều kiện sau khi test:

~~~sql
-- Không có ca nào có counter dưới 1.
SELECT shift_id
FROM shifts
WHERE on_call_count < 1;

-- Đối soát counter với số assignment đang trực.
SELECT s.shift_id,
       s.on_call_count,
       COUNT(a.doctor_id) AS actual_count
FROM shifts s
LEFT JOIN shift_assignments a
       ON a.shift_id = s.shift_id
      AND a.on_call = true
GROUP BY s.shift_id, s.on_call_count
HAVING s.on_call_count <> COUNT(a.doctor_id);
~~~

Hai truy vấn trên dùng cú pháp SQL phổ biến. Điều kiện dữ liệu và kiểu boolean có thể cần điều chỉnh theo engine.

## 11. Chọn chiến lược theo yêu cầu hệ thống

Có thể dùng các câu hỏi sau để chọn cách bảo vệ:

- **Bất biến có liên quan đến nhiều dòng không?** Nếu có, row lock riêng lẻ thường chưa đủ.
- **Mọi transaction có thể dùng SERIALIZABLE không?** Nếu có và retry được kiểm soát tốt, đây là lựa chọn tổng quát.
- **Có một đơn vị nghiệp vụ rõ ràng như shift_id không?** Guard row cho mỗi đơn vị giúp tuần tự hóa chính xác phạm vi cần thiết.
- **Số lượng tổng hợp có thể duy trì trong cùng transaction không?** Nếu có, counter và CHECK có thể tạo một điều kiện nguyên tử dễ kiểm tra.
- **Tài nguyên cần khóa không có dòng đại diện?** Có thể dùng advisory/application lock nếu engine hỗ trợ.
- **Có writer nào bỏ qua giao thức không?** Nếu có, cần gom quyền ghi, dùng quyền database hoặc một cơ chế cưỡng chế khác.
- **Tần suất cập nhật cùng một ca cao đến đâu?** Guard/counter sẽ tuần tự hóa các thay đổi cùng ca; nếu đây là điểm nóng, cần đánh giá throughput và có thể phân chia đơn vị điều phối.

Một hệ thống thường có thể kết hợp nhiều lớp. Ví dụ, dùng guard row để tuần tự hóa thay đổi của một ca, CHECK để bảo vệ bộ đếm không xuống dưới 1, và một tác vụ đối soát để phát hiện counter không khớp assignment.

## Kết luận

Bất biến “mỗi ca trực luôn có ít nhất một người” là quy tắc liên quan đến nhiều dòng. Chỉ kiểm tra COUNT trong ứng dụng hoặc khóa riêng dòng bác sĩ đang sửa có thể không ngăn được write skew khi hai transaction cùng đọc trạng thái ban đầu rồi cập nhật các dòng khác nhau.

SERIALIZABLE có thể ngăn lịch không tuần tự hóa được và yêu cầu retry toàn bộ transaction khi engine phát hiện xung đột. Guard row hoặc advisory lock tạo một điểm điều phối chung cho từng ca, còn bộ đếm trên dòng shift kết hợp UPDATE có điều kiện và CHECK giúp biểu diễn điều kiện tối thiểu bằng một thao tác ghi nguyên tử. Dù chọn cách nào, mọi đường ghi liên quan phải tuân thủ cùng giao thức và các thao tác cập nhật liên quan phải nằm trong cùng transaction.

Hãy kiểm thử bằng các transaction chạy đồng thời thực sự, bao gồm thêm, xóa, chuyển ca và retry. Kết quả cần được xác nhận bằng dữ liệu sau commit: không có ca nào có số người trực nhỏ hơn một.
