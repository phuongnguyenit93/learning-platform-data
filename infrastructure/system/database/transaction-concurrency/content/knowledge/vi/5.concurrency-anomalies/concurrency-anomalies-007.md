# Ghi lệch (write skew) khi các giao dịch cập nhật những hàng khác nhau

**Write skew (ghi lệch)** là một bất thường đồng thời trong đó hai hoặc nhiều giao dịch cùng đọc một trạng thái chung, mỗi giao dịch tự thấy thay đổi của mình là hợp lệ, rồi cập nhật **những hàng khác nhau**. Vì chúng không ghi đè trực tiếp cùng một hàng, hệ quản trị có thể cho tất cả cùng commit ở một mức cô lập dựa trên snapshot. Tuy nhiên, trạng thái cuối lại vi phạm một quy tắc nghiệp vụ vốn đúng trước khi các giao dịch bắt đầu.

Điểm khó của write skew là từng câu UPDATE có thể hợp lệ, từng hàng sau cập nhật cũng có thể hợp lệ theo constraint cục bộ, và không có lost update trên cùng một cột. Lỗi chỉ xuất hiện khi nhìn **quan hệ giữa nhiều hàng**.

Bài học này thuộc chương **Bất thường đồng thời** của **Database Transaction Concurrency**. Mục tiêu là nhận diện invariant đa hàng, viết ra lịch xen kẽ có thể phá invariant, hiểu vì sao snapshot/repeatable read chưa chắc đủ, rồi chọn cơ chế bảo vệ và kiểm chứng có chủ đích.

## 1. Ví dụ trực quan: luôn phải có ít nhất một bác sĩ trực

Giả sử có hai bác sĩ A và B đang trực. Quy tắc nghiệp vụ là trong mọi thời điểm vận hành, phải có ít nhất một bác sĩ ở trạng thái trực.

| Bác sĩ | Trạng thái ban đầu |
| --- | --- |
| A | Đang trực |
| B | Đang trực |
| Tổng | 2 |

Hai yêu cầu nghỉ trực đến gần như cùng lúc. Yêu cầu của A kiểm tra “còn người khác trực không?” và thấy B đang trực. Yêu cầu của B cũng kiểm tra cùng điều kiện và thấy A đang trực. Mỗi yêu cầu kết luận mình có thể rời ca:

- T1 đổi A thành nghỉ trực.
- T2 đổi B thành nghỉ trực.

Hai transaction cập nhật hai hàng khác nhau. Cả hai có thể commit; cuối cùng không ai trực.

~~~text
Ban đầu:
  A = ON
  B = ON
  invariant: A = ON OR B = ON

T1 đọc: B đang ON  -> cho A nghỉ
T2 đọc: A đang ON  -> cho B nghỉ

T1 ghi: A = OFF
T2 ghi: B = OFF

Sau commit:
  A = OFF
  B = OFF
  invariant bị vi phạm
~~~

Đây là lỗi về **quyết định dựa trên snapshot cũ**, không phải lỗi cú pháp SQL. Câu lệnh T1 chỉ cập nhật hàng A; câu lệnh T2 chỉ cập nhật hàng B. Nếu chỉ xem từng hàng, cả hai trạng thái mới đều có vẻ hợp lệ. Quy tắc “ít nhất một người trực” chỉ đánh giá được khi xét tập hàng.

## 2. Mô hình hóa write skew

### 2.1 Invariant đa hàng

Invariant là điều kiện phải luôn đúng tại trạng thái được hệ thống chấp nhận. Với ví dụ trên:

\[
\text{onCallCount} = \sum_{d \in Doctors} \mathbf{1}(d.isOnCall)
\]

\[
\boxed{\text{onCallCount} \ge 1}
\]

Mỗi transaction thay đổi một hàng, nhưng quyết định của nó phụ thuộc vào tổng số hàng đang trực. Phạm vi invariant có thể là:

- **Một hàng:** ví dụ số dư của một tài khoản không âm.
- **Duy nhất:** ví dụ một ghế chỉ có một booking hiệu lực.
- **Nhiều hàng:** ví dụ phải còn ít nhất một bác sĩ trực, tổng ngân sách phân bổ không vượt hạn mức.
- **Một tập kết quả/predicate:** ví dụ số nhân viên đang trực trong một bộ phận phải ít nhất là một, kể cả khi hàng có thể được thêm/xóa trong lúc transaction đang chạy.

Write skew thường xuất hiện ở các invariant nhiều hàng hoặc predicate, nơi các transaction đọc cùng một điều kiện nhưng ghi các hàng riêng biệt.

### 2.2 Schema và logic của hai giao dịch

~~~sql
CREATE TABLE on_call (
    doctor_id text PRIMARY KEY,
    is_on_call boolean NOT NULL
);

INSERT INTO on_call(doctor_id, is_on_call)
VALUES ('A', true), ('B', true);
~~~

Logic đơn giản của hai transaction:

~~~text
T1:
  BEGIN
  count = SELECT count(*) FROM on_call WHERE is_on_call
  if count > 1:
      UPDATE on_call SET is_on_call = false WHERE doctor_id = 'A'
  COMMIT

T2:
  BEGIN
  count = SELECT count(*) FROM on_call WHERE is_on_call
  if count > 1:
      UPDATE on_call SET is_on_call = false WHERE doctor_id = 'B'
  COMMIT
~~~

Nếu T1 và T2 bắt đầu trong lúc cả A và B đều trực, mỗi snapshot có thể trả về count = 2. T1 không biết quyết định của T2; T2 cũng không biết quyết định của T1. Cả hai điều kiện đều đúng theo snapshot mà transaction đã đọc.

### 2.3 Lịch xen kẽ tạo ra lỗi

| Thứ tự | Transaction T1 | Transaction T2 | Quan sát |
| --- | --- | --- | --- |
| 1 | BEGIN REPEATABLE READ | | T1 bắt đầu |
| 2 | | BEGIN REPEATABLE READ | T2 bắt đầu |
| 3 | Đếm số người trực → 2 | | T1 thấy hai người trực |
| 4 | | Đếm số người trực → 2 | T2 cũng thấy hai người trực |
| 5 | UPDATE hàng A | | T1 chỉ ghi hàng A |
| 6 | | UPDATE hàng B | T2 chỉ ghi hàng B |
| 7 | COMMIT | | T1 commit |
| 8 | | COMMIT | T2 commit |
| 9 | Kiểm tra tổng | | Kết quả = 0, invariant bị phá |

~~~text
T1: R(A=ON, B=ON) -------- W(A=OFF) ---- COMMIT
T2:       R(A=ON, B=ON) -------- W(B=OFF) ---- COMMIT
~~~

Việc T1 và T2 đọc cùng snapshot không buộc chúng ghi cùng một hàng. Các khóa ghi trên A và B không xung đột, do đó cơ chế chỉ phát hiện hai lần ghi cùng hàng không đủ để nhận ra lỗi.

## 3. Phân biệt write skew với lost update

Hai khái niệm thường bị nhầm vì đều bắt nguồn từ việc nhiều giao dịch đọc dữ liệu cũ rồi ghi kết quả.

### 3.1 Lost update

Hai giao dịch cùng đọc và cùng ghi một dữ liệu:

~~~text
Ban đầu: counter = 10

T1: đọc counter = 10
T2: đọc counter = 10
T1: ghi counter = 11
T2: ghi counter = 11

Kết quả: counter = 11
Kỳ vọng nếu cộng hai lần: counter = 12
~~~

Cập nhật của một transaction đã làm mất cập nhật của transaction kia. Cả hai có tranh chấp trực tiếp trên cùng một hàng/giá trị.

### 3.2 Write skew

Hai giao dịch đọc cùng tập dữ liệu nhưng ghi các hàng khác nhau:

~~~text
Ban đầu: A=ON, B=ON

T1: đọc A, B; ghi A=OFF
T2: đọc A, B; ghi B=OFF

Kết quả: A=OFF, B=OFF
Invariant A=ON OR B=ON bị phá
~~~

| Khía cạnh | Lost update | Write skew |
| --- | --- | --- |
| Dữ liệu đọc | Thường cùng một hàng/giá trị | Thường cùng nhiều hàng hoặc predicate |
| Dữ liệu ghi | Cùng hàng/giá trị | Các hàng khác nhau |
| Dấu hiệu cuối | Một cập nhật biến mất | Từng cập nhật còn nguyên nhưng invariant tổng thể sai |
| Chỉ phát hiện xung đột cùng hàng có đủ không? | Có thể phát hiện/giải quyết tùy cơ chế | Không; không có cùng hàng được ghi |
| Ví dụ | Hai lượt tăng số đếm cùng ghi 11 | Hai bác sĩ cùng rời ca |

Không phải mọi cập nhật khác hàng đều là write skew. Cần có ba yếu tố:

1. Các transaction đọc cùng dữ liệu, điều kiện hoặc một trạng thái chung có liên quan.
2. Mỗi transaction dựa trên thông tin đó để quyết định cập nhật.
3. Các cập nhật riêng rẽ khi cùng được chấp nhận làm vi phạm invariant hoặc tạo kết quả không tương đương thực thi tuần tự.

“Ghi khác hàng” một mình chưa đủ kết luận write skew.

## 4. Vì sao REPEATABLE READ dựa trên snapshot vẫn có thể mắc write skew?

### 4.1 Repeatable read bảo vệ điều gì?

Tên REPEATABLE READ có thể khiến người học nghĩ mọi giao dịch đều được thực thi như chạy tuần tự. Nhưng ý nghĩa cụ thể phụ thuộc DBMS.

Trong PostgreSQL, REPEATABLE READ cung cấp snapshot ổn định cho các truy vấn của transaction. Những lần đọc lặp lại không tự nhìn thấy các commit mới được tạo sau snapshot. PostgreSQL cũng phát hiện và từ chối một số xung đột khi transaction muốn ghi một hàng đã bị transaction khác sửa sau snapshot.

Tuy nhiên, snapshot ổn định **không ngăn hai giao dịch cập nhật các hàng khác nhau** dựa trên cùng một điều kiện chung. Đó chính là cửa ngõ của write skew.

### 4.2 Hai hàng khác nhau nên không có write-write conflict trực tiếp

- T1 đọc A và B, ghi A.
- T2 đọc A và B, ghi B.

Đồ thị phụ thuộc có hai cạnh:

- T1 đọc B trước khi T2 ghi B: T1 → T2.
- T2 đọc A trước khi T1 ghi A: T2 → T1.

~~~mermaid
flowchart LR
    A["T1"] -->|"T1 đọc B trước khi T2 ghi B"| B["T2"]
    B -->|"T2 đọc A trước khi T1 ghi A"| A
~~~

Chu trình T1 → T2 → T1 cho thấy không có thứ tự tuần tự nào giải thích cả hai quyết định đọc/ghi. Nhưng nếu chỉ kiểm tra các lần ghi có đụng cùng một hàng hay không, ta sẽ không thấy xung đột.

### 4.3 So sánh mức cô lập trong PostgreSQL

| Isolation level | Snapshot và hành vi liên quan | Write skew có thể xảy ra? |
| --- | --- | --- |
| READ COMMITTED | Mỗi câu SELECT có snapshot riêng; hai transaction có thể đọc cùng trạng thái trước khi ghi | Có thể, nếu logic đọc-kiểm-tra-ghi không được bảo vệ |
| REPEATABLE READ | Truy vấn nhìn snapshot ổn định; xung đột ghi trên cùng hàng có thể làm một transaction lỗi | **Có**, khi hai transaction cập nhật hàng khác nhau và phụ thuộc hai chiều |
| SERIALIZABLE | Theo dõi phụ thuộc để bảo đảm các transaction commit tương đương một lịch tuần tự | Không để cả hai cùng commit lịch không serializable; một bên có thể nhận lỗi serialization |

Không nên suy luận tên isolation level có cùng hành vi trên mọi DBMS. PostgreSQL gọi mức snapshot isolation là REPEATABLE READ, trong khi hệ quản trị khác có cách triển khai và bảo đảm khác.

## 5. Thực hành PostgreSQL: tái hiện write skew

Dùng database thử nghiệm và hai session psql độc lập A, B; không chạy hai transaction trên cùng một connection.

### 5.1 Tạo dữ liệu

~~~sql
DROP TABLE IF EXISTS on_call;

CREATE TABLE on_call (
    doctor_id text PRIMARY KEY,
    is_on_call boolean NOT NULL
);

INSERT INTO on_call(doctor_id, is_on_call)
VALUES ('A', true), ('B', true);

SELECT * FROM on_call ORDER BY doctor_id;
~~~

Trạng thái đầu có hai người trực.

### 5.2 Session A

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM on_call
WHERE is_on_call;
-- Kết quả: 2. Giữ transaction mở.
~~~

### 5.3 Session B

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT count(*)
FROM on_call
WHERE is_on_call;
-- Kết quả: 2. Giữ transaction mở.
~~~

### 5.4 Cập nhật các hàng khác nhau

Quay lại Session A:

~~~sql
UPDATE on_call
SET is_on_call = false
WHERE doctor_id = 'A';

-- Chưa commit, chuyển sang B.
~~~

Session B:

~~~sql
UPDATE on_call
SET is_on_call = false
WHERE doctor_id = 'B';

COMMIT;
~~~

Quay lại Session A:

~~~sql
COMMIT;
~~~

Kiểm tra:

~~~sql
SELECT
    count(*) FILTER (WHERE is_on_call) AS active_doctors
FROM on_call;
-- Kết quả: 0
~~~

Cả hai transaction có thể commit dưới PostgreSQL REPEATABLE READ, trong khi invariant “ít nhất một bác sĩ còn trực” đã bị phá.

Điều chứng minh write skew ở đây: hai session đều đọc 2 trước các lần ghi; A chỉ sửa hàng A, B chỉ sửa hàng B; không transaction nào ghi đè cập nhật của transaction còn lại; cả hai commit làm số người trực thành 0.

## 6. Sửa bằng SERIALIZABLE và xử lý lỗi serialization

### 6.1 Chạy lại cùng lịch ở SERIALIZABLE

Reset dữ liệu:

~~~sql
UPDATE on_call SET is_on_call = true;
~~~

Chạy Session A:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT count(*) FROM on_call WHERE is_on_call;
-- 2
~~~

Chạy Session B:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT count(*) FROM on_call WHERE is_on_call;
-- 2
~~~

Tiếp tục cùng lịch: Session A đổi A thành false; Session B đổi B thành false; commit hai session.

Trong PostgreSQL, cơ chế Serializable Snapshot Isolation (SSI) phát hiện cấu trúc phụ thuộc không thể đồng thời tồn tại trong một kết quả tuần tự hợp lệ. **Ít nhất một giao dịch sẽ không thể commit thành công với lịch xung đột này**; nó có thể nhận SQLSTATE 40001 (serialization_failure).

Kết quả có thể là một bên commit, bên kia rollback. Khi ứng dụng retry transaction thua, nó đọc trạng thái mới. Nếu chỉ còn một bác sĩ đang trực, giao dịch retry sẽ thấy điều kiện không còn thỏa và từ chối cho người cuối cùng rời ca.

Đừng phụ thuộc vào việc session nào luôn thắng. Kết quả cụ thể phụ thuộc lịch và thời điểm thao tác. Điều quan trọng là không để cả hai transaction commit cùng lịch phá invariant.

### 6.2 Retry phải chạy lại toàn bộ transaction

Sai:

~~~text
try:
    COMMIT
catch serialization_failure:
    retry COMMIT
~~~

Cũng sai nếu chỉ chạy lại lệnh UPDATE từ quyết định cũ. Quyết định count > 1 đã được tạo từ snapshot cũ, nên phải đọc lại và tính lại.

Mẫu đúng:

~~~text
function leaveOnCall(doctorId):
    for attempt in 1..MAX_ATTEMPTS:
        try:
            BEGIN ISOLATION LEVEL SERIALIZABLE

            activeCount = SELECT COUNT(*)
                          FROM on_call
                          WHERE is_on_call = true

            if activeCount <= 1:
                ROLLBACK
                return "Không thể rời ca: cần ít nhất một người trực"

            UPDATE on_call
            SET is_on_call = false
            WHERE doctor_id = doctorId
              AND is_on_call = true

            COMMIT
            return "Đã rời ca"

        catch sqlState == "40001":
            ROLLBACK nếu transaction còn mở
            nếu hết MAX_ATTEMPTS: báo lỗi có thể retry cho caller
            đợi backoff có jitter rồi chạy lại từ BEGIN
~~~

Một transaction retry phải bao gồm: mở transaction mới, đọc lại trạng thái, kiểm tra invariant, tính lại quyết định, cập nhật và commit. Retry cần giới hạn số lần, backoff có jitter và phân loại lỗi. 40001 là lỗi có thể retry theo chiến lược; lỗi nghiệp vụ “đây là người cuối cùng còn trực” phải trả về cho caller chứ không retry vô hạn.

Nếu giao dịch có side effect ngoài DB, cần bảo đảm idempotency hoặc dùng outbox để tránh lặp tác động.

## 7. Các cách phòng tránh write skew

SERIALIZABLE là cách bảo vệ tổng quát, nhưng không phải phương án duy nhất. Chọn cơ chế tùy phạm vi invariant, mức tranh chấp, chi phí khóa và cách dữ liệu được mô hình hóa.

### 7.1 Khóa một hàng đại diện (guard row)

Tạo một hàng đại diện cho quy tắc “nhóm này phải còn ít nhất một người trực”. Mọi transaction muốn thay đổi trạng thái trực phải khóa hàng đại diện **trước khi đọc invariant**.

~~~sql
CREATE TABLE on_call_guard (
    team_id text PRIMARY KEY,
    lock_version bigint NOT NULL DEFAULT 0
);

INSERT INTO on_call_guard(team_id)
VALUES ('ER');
~~~

Luồng mỗi transaction:

~~~sql
BEGIN;

-- Tất cả thao tác thay đổi lịch trực của nhóm ER đều khóa cùng hàng.
SELECT team_id
FROM on_call_guard
WHERE team_id = 'ER'
FOR UPDATE;

-- Chỉ đọc invariant sau khi đã lấy được khóa.
SELECT count(*)
FROM on_call
WHERE is_on_call = true;

-- Nếu count > 1 thì mới cho bác sĩ hiện tại nghỉ.
UPDATE on_call
SET is_on_call = false
WHERE doctor_id = 'A';

COMMIT;
~~~

Khi A giữ khóa guard, transaction B phải chờ trước khi kiểm tra. Sau khi A commit, B nhận khóa và đọc trạng thái đã cập nhật; nếu chỉ còn một người trực thì B phải từ chối.

Guard row không tự động có ý nghĩa nếu có đường ghi khác bỏ qua giao thức. Mọi đường thay đổi ảnh hưởng invariant đều phải khóa hàng đại diện theo cùng quy tắc, cùng thứ tự. Có thể đóng gói logic trong stored procedure hoặc giới hạn quyền ghi trực tiếp để giảm nguy cơ code khác quên khóa.

### 7.2 Khóa tập hàng bằng SELECT FOR UPDATE

Với tập dữ liệu nhỏ và đã biết, có thể khóa những hàng sẽ tham gia quyết định:

~~~sql
BEGIN;

SELECT doctor_id, is_on_call
FROM on_call
ORDER BY doctor_id
FOR UPDATE;

-- Tính lại số người trực sau khi đã khóa tập hàng.
SELECT count(*)
FROM on_call
WHERE is_on_call;

-- Chỉ cập nhật nếu invariant vẫn đúng.
COMMIT;
~~~

Hai transaction cùng cần khóa hai hàng này sẽ bị tuần tự hóa ở bước lấy khóa. ORDER BY tạo thứ tự lấy khóa ổn định, giúp giảm nguy cơ deadlock khi transaction khóa nhiều hàng.

Nhược điểm: khóa tập hàng rộng có thể giảm concurrency; khóa các hàng hiện có chưa chắc khóa được những hàng mới thỏa predicate sẽ được thêm vào sau. Với invariant trên tập động, guard row hoặc SERIALIZABLE thường dễ lập luận hơn.

### 7.3 Constraint hoặc cách mô hình hóa dữ liệu

Nếu invariant có thể biến thành constraint, nên để DB cưỡng chế ở điểm lưu dữ liệu.

Ví dụ mỗi nhóm có một hàng primary_on_call_doctor_id trỏ tới bác sĩ hiện đang chịu trách nhiệm. Có thể thiết kế để một nhóm luôn có đúng một chủ thể trực; cập nhật người trực phải thay thế người phụ trách trong một transaction.

Không phải mọi invariant đều biểu diễn trực tiếp bằng CHECK. Trong PostgreSQL, CHECK constraint được thiết kế cho biểu thức trên **mỗi hàng**, không thể an toàn dùng subquery để đếm các hàng khác trong bảng. Cần chọn mô hình dữ liệu, khóa, unique/exclusion constraint hoặc trigger với cơ chế đồng thời đúng. Một trigger chỉ SELECT COUNT(*) mà không khóa/tuần tự hóa cũng có thể mắc write skew tương tự.

### 7.4 Atomic update trên một hàng tổng hợp

Nếu nghiệp vụ có thể chuyển invariant về một hàng tổng hợp, việc giảm bộ đếm có điều kiện sẽ đơn giản hơn:

~~~sql
CREATE TABLE team_on_call_state (
    team_id text PRIMARY KEY,
    active_count integer NOT NULL CHECK (active_count >= 1)
);
~~~

Mỗi lần một người rời ca, transaction cập nhật hàng tổng hợp:

~~~sql
UPDATE team_on_call_state
SET active_count = active_count - 1
WHERE team_id = 'ER'
  AND active_count > 1
RETURNING active_count;
~~~

Chỉ một transaction tại một thời điểm có thể cập nhật hàng team_on_call_state cho cùng team; điều kiện được đánh giá lại khi cạnh tranh trên cùng hàng. Tuy nhiên, bộ đếm phải luôn đồng bộ với các hàng bác sĩ. Vì vậy cập nhật bảng tổng hợp và đổi trạng thái bác sĩ phải cùng transaction; mọi đường ghi phải giữ cùng quy ước.

### 7.5 Optimistic concurrency bằng version trên guard

Một hàng version dùng compare-and-swap có thể phát hiện một transaction đã thay đổi quy tắc chung:

~~~sql
UPDATE on_call_guard
SET lock_version = lock_version + 1
WHERE team_id = 'ER'
  AND lock_version = 10
RETURNING lock_version;
~~~

Nếu không có hàng trả về, một transaction khác đã cập nhật version. Để an toàn, việc kiểm tra invariant và thay đổi version phải nằm trong cùng transaction; transaction thua phải đọc lại và quyết định lại. Version riêng trên **từng bác sĩ** không đủ nếu hai transaction cập nhật hai version khác nhau mà invariant lại liên quan cả nhóm. Điểm tuần tự hóa phải nằm trên **phạm vi invariant**, chẳng hạn một guard version chung.

### 7.6 So sánh phương án

| Cơ chế | Bảo vệ write skew thế nào? | Ưu điểm | Chi phí/giới hạn |
| --- | --- | --- | --- |
| SERIALIZABLE | DB phát hiện phụ thuộc không thể tuần tự hóa, hủy một bên | Mã ứng dụng tự nhiên; bao phủ nhiều quan hệ đọc/ghi | Có serialization failure, cần retry; chi phí tracking |
| Guard row FOR UPDATE | Tuần tự hóa giao dịch cùng invariant trên một hàng đại diện | Rõ ràng, dễ quan sát và kiểm soát | Tranh chấp trên guard; mọi writer phải tuân thủ |
| Khóa tập hàng | Đảm bảo writer không cùng kiểm tra tập trạng thái chưa khóa | Phù hợp tập nhỏ, rõ ràng | Khóa rộng; không tự chặn phantom/row mới |
| Constraint/mô hình dữ liệu | Cưỡng chế invariant ở nơi ghi | Bảo vệ nhiều đường ghi | Không phải invariant đa hàng nào cũng biểu diễn trực tiếp |
| Guard counter/atomic update | Đưa quyết định về một hàng tuần tự hóa | Một thao tác có điều kiện | Phải giữ counter đồng bộ với dữ liệu chi tiết |
| Optimistic version chung | Phát hiện thay đổi trên phạm vi invariant | Hạn chế khóa dài | Xung đột phải retry; version từng hàng không đủ |

## 8. Write skew trong bài toán thực tế

### 8.1 Phân bổ nhân sự trực ca

Invariant: luôn có ít nhất một nhân viên đang trực trong mỗi nhóm. Hai nhân viên cùng xin nghỉ có thể cùng đọc active_count = 2, rồi tắt trạng thái của mỗi người.

Cách thiết kế: guard row theo team_id; một hàng trạng thái tổng hợp active_count cập nhật atomic; hoặc SERIALIZABLE với retry toàn transaction.

Nếu mỗi nhóm có invariant riêng, khóa theo team để các nhóm khác nhau vẫn thay đổi độc lập.

### 8.2 Giới hạn tổng ngân sách phân bổ

Một phòng ban có hạn mức 100. Các khoản phân bổ hiện tại tổng 90. Hai transaction lần lượt thêm khoản 8 cho hai dự án khác nhau. Mỗi transaction đều đọc tổng 90 và thấy 90 + 8 <= 100. Nếu hai hàng dự án khác nhau, cả hai có thể commit để tổng thành 106.

Invariant:

\[
\sum_{p \in Projects(department)} allocation(p)
\le department.limit
\]

CHECK (allocation <= 100) trên từng hàng không đủ vì từng khoản riêng lẻ vẫn nhỏ hơn 100; điều kiện vi phạm nằm ở tổng.

Phương án: khóa hàng department, cập nhật bộ đếm allocated_total có điều kiện, hoặc chạy SERIALIZABLE. Chỉ SELECT SUM rồi INSERT trong READ COMMITTED mà không có điểm tuần tự hóa là không đủ.

### 8.3 Đặt lịch bảo trì hoặc tài nguyên

Hai yêu cầu đặt hai khoảng thời gian khác nhau nhưng chồng lấn trên cùng máy. Nếu hai transaction đọc “không có lịch nào chồng lấn” trên snapshot, rồi ghi các hàng booking riêng biệt, cả hai có thể commit.

Invariant là các khoảng thời gian trên cùng tài nguyên không được chồng lấn. Với PostgreSQL, có thể cân nhắc range type kết hợp exclusion constraint để DB từ chối các khoảng chồng lấn, cùng transaction ghi dữ liệu. Với quy tắc phức tạp hơn, có thể tuần tự hóa theo resource ID bằng guard row hoặc dùng SERIALIZABLE.

### 8.4 Nhóm ghế hoặc phân bổ quota

Hai request cấp quota cho hai người dùng khác nhau, mỗi request đọc tổng quota còn lại nhưng ghi hàng quota riêng. Tương tự write skew nếu tổng phân bổ cuối vượt hạn mức. Nếu quota là một tài nguyên chung, mô hình thành một hàng số dư/quota và cập nhật trừ có điều kiện thường đơn giản hơn.

### 8.5 Một job đang chạy

Quy tắc: mỗi tenant chỉ được có một job RUNNING. Hai worker cùng query NOT EXISTS rồi insert hai job ID khác nhau. Nếu yêu cầu chỉ một job active, cần unique partial index/constraint phù hợp (nếu mô hình trạng thái và DB hỗ trợ) hoặc guard row; kiểm tra NOT EXISTS rồi insert đơn thuần dễ mắc race condition.

Điểm chung: bất cứ khi nào điều kiện kiểm tra là truy vấn COUNT, SUM, NOT EXISTS, kiểm tra khoảng thời gian hoặc trạng thái nhiều hàng mà transaction sau đó ghi một hàng khác, hãy cân nhắc write skew.

## 9. Kiểm chứng write skew bằng test có điều khiển

Một test chạy 1.000 lần mà không thấy lỗi không chứng minh invariant được bảo vệ. Scheduler có thể chưa tạo được lịch hai transaction cùng đọc trạng thái cũ trước khi ghi.

### 9.1 Dùng barrier

Test cần hai connection DB độc lập và một barrier ở phía ứng dụng:

~~~text
reset state: A=ON, B=ON

worker A: begin repeatable read; read count; wait at barrier
worker B: begin repeatable read; read count; wait at barrier

release barrier only when both have read count=2

worker A: update A=OFF; commit
worker B: update B=OFF; commit

assert active_count >= 1
~~~

Với bản lỗi, assertion phải thất bại một cách tái lập. Với bản dùng guard hoặc SERIALIZABLE, lịch tương tự phải dẫn tới một transaction đợi/abort và trạng thái cuối giữ invariant.

Không dùng sleep thay cho barrier khi cần lịch xác định: độ trễ không bảo đảm hai thread đã đọc xong trước khi thread đầu ghi.

### 9.2 Assertion đúng

Một test chỉ kiểm tra UPDATE trả về một hàng là chưa đủ. Cần kiểm tra:

- Số người trực cuối cùng >= 1.
- Số request được chấp nhận và từ chối.
- Có transaction bị 40001 hay bị chặn tại guard lock không.
- Nếu retry, transaction retry có đọc lại và từ chối quyết định vi phạm không.
- Các thay đổi phụ thuộc có nằm trong cùng transaction không.

~~~text
assert active_doctors_after_all_commits >= 1
assert accepted_leave_requests <= initial_active_doctors - 1
assert rejected_or_retried_requests_are_reported_correctly
~~~

### 9.3 Ma trận kiểm thử

| Kịch bản | Kỳ vọng |
| --- | --- |
| Một bác sĩ xin nghỉ khi có hai người trực | Có thể chấp nhận, còn một người |
| Hai bác sĩ cùng xin nghỉ từ trạng thái hai người trực | Chỉ một yêu cầu thành công; cuối vẫn còn một |
| Hai bác sĩ ở hai team khác nhau cùng xin nghỉ | Cả hai có thể thành công độc lập nếu invariant mỗi team vẫn đúng |
| Request retry sau 40001 | Đọc lại trạng thái; không cho người cuối cùng nghỉ |
| Hai giao dịch dùng cùng guard row | Một bên phải đợi và kiểm tra lại sau bên kia |
| Một đường ghi bỏ qua guard | Test phải phát hiện nguy cơ; cần kiểm soát đường ghi |
| Transaction chết trước commit | Thay đổi chưa commit rollback; invariant vẫn được giữ |

### 9.4 Kiểm thử đúng đắn và hiệu năng

Sau khi xác nhận invariant, mới đo chi phí:

- Thời gian chờ guard lock.
- Số serialization failure và retry.
- Throughput khi các request cùng team và khác team.
- P95/P99 latency.
- Tỷ lệ retry hết giới hạn.
- Số transaction mở lâu.

Không đánh đổi correctness để giảm số lần abort. Nếu một team có nhiều hoạt động cạnh tranh, có thể phân vùng guard theo tài nguyên độc lập hơn, nhưng chỉ khi chứng minh invariant thực sự tách được theo phân vùng đó.

## 10. Deadlock và write skew là hai hiện tượng khác nhau

Write skew có thể xảy ra **không cần deadlock**. Hai transaction cập nhật hai hàng khác nhau và cùng commit là tình huống điển hình.

Deadlock là vòng chờ tài nguyên: T1 giữ khóa mà T2 cần, đồng thời T2 giữ khóa mà T1 cần. DB phải hủy ít nhất một transaction để phá vòng.

| Thuộc tính | Write skew | Deadlock |
| --- | --- | --- |
| Cơ chế | Phụ thuộc đọc/ghi trên invariant chung | Vòng chờ giữa khóa/tài nguyên |
| Có thể cả hai commit? | Có ở isolation không bảo vệ invariant | Không thể cả hai tiếp tục khi deadlock bị phát hiện; một bên bị hủy |
| Dữ liệu bị ghi | Thường các hàng khác nhau | Có thể cùng hoặc khác hàng/tài nguyên |
| Tín hiệu lỗi | Có thể không có lỗi; invariant sai sau commit | Thường SQLSTATE 40P01 trong PostgreSQL |
| Cách phòng | Serializable, guard row, constraint, mô hình invariant | Thứ tự lấy khóa nhất quán, transaction ngắn, retry |

Guard row và khóa tập hàng có thể biến một lịch write skew thành tình huống chờ khóa. Nếu các transaction lấy nhiều khóa theo thứ tự khác nhau, giải pháp khóa lại có thể làm tăng deadlock; hãy thống nhất thứ tự lấy khóa.

## 11. Giới hạn và lưu ý khi triển khai

### 11.1 Mọi writer phải tuân theo cùng một cơ chế

Guard row chỉ hiệu lực nếu mọi code path thay đổi dữ liệu có ảnh hưởng invariant đều khóa guard. Một tác vụ batch, admin script hoặc worker cũ cập nhật trực tiếp on_call mà bỏ qua guard có thể phá quy tắc.

Giảm nguy cơ bằng cách:

- Đóng gói logic thay đổi vào service/stored procedure chung.
- Giới hạn quyền UPDATE trực tiếp của tài khoản ứng dụng nếu phù hợp.
- Có test concurrency cho mọi đường ghi quan trọng.
- Dùng constraint hoặc mô hình dữ liệu để cưỡng chế ở DB khi có thể.

### 11.2 Không khóa một hàng quá rộng

Nếu toàn công ty chỉ có một guard row, mọi thay đổi của các nhóm độc lập đều chờ nhau. Guard nên có phạm vi chính xác, ví dụ team_id, resource_id hoặc department_id, miễn là không tách một invariant cần được bảo vệ chung thành nhiều khóa rời rạc.

### 11.3 Serializable không có nghĩa không có lỗi

SERIALIZABLE bảo vệ tính khả tuần tự hóa cho các transaction commit theo mô hình DB, nhưng ứng dụng vẫn phải xử lý 40001. Một giao dịch đơn lẻ có logic sai, hoặc bỏ sót invariant không nằm trong transaction, vẫn có thể commit kết quả sai. Cũng cần bảo vệ idempotency khi retry tạo side effect ngoài DB.

### 11.4 Snapshot và thời điểm đọc

Ở READ COMMITTED, mỗi câu lệnh có thể nhìn một snapshot khác; ở REPEATABLE READ PostgreSQL, snapshot ổn định. Khi phân tích write skew, ghi rõ mức isolation và thời điểm đọc snapshot. Đừng chỉ nhìn timestamp BEGIN để kết luận dữ liệu mà transaction đã quan sát.

### 11.5 Dữ liệu ngoài DB

Nếu transaction ghi ra message broker, gọi API, gửi email hoặc cập nhật cache ngay trong lúc quyết định, retry sau serialization failure có thể thực hiện side effect hai lần. Nên chỉ phát side effect sau commit, hoặc ghi sự kiện vào transactional outbox trong transaction rồi worker phát sau; consumer cần idempotent.

## 12. Quy trình thiết kế khi invariant phụ thuộc nhiều hàng

1. **Viết invariant thành biểu thức.** Ví dụ active_doctors >= 1, allocated_total <= limit, no overlapping reservation.
2. **Liệt kê tất cả hàng/predicate ảnh hưởng đến biểu thức.** Xác định phạm vi nhóm, tài nguyên, thời gian hoặc tenant.
3. **Tìm mọi quyết định đọc-kiểm-tra-ghi.** Đặc biệt truy vấn COUNT, SUM, NOT EXISTS, kiểm tra khoảng thời gian hoặc trạng thái các hàng liên quan.
4. **Dựng hai transaction cạnh tranh.** Cho cả hai đọc trạng thái ban đầu trước khi một bên ghi.
5. **Xác định các hàng ghi.** Nếu các transaction ghi các hàng khác nhau, kiểm tra kỹ nguy cơ write skew.
6. **Chọn điểm tuần tự hóa.** Constraint, guard row, tổng hợp trên một hàng, khóa tập hàng hoặc SERIALIZABLE.
7. **Đặt chính sách conflict.** Bên thua sẽ đợi, nhận lỗi, từ chối nghiệp vụ hay retry toàn transaction?
8. **Test với barrier và invariant assertion.** Đừng phụ thuộc may rủi scheduler.
9. **Đo contention và retry.** Tách traffic độc lập bằng guard phù hợp nếu chứng minh được phạm vi invariant cho phép.
10. **Bảo vệ mọi đường ghi.** Bao gồm API, background job, admin tool, migration và consumer.

## 13. Bài tập tự luyện

### Bài 1 — Phân bổ ngân sách

Phòng ban có hạn mức 100; đã dùng 90. Hai dự án khác nhau cùng xin thêm 8. Mỗi transaction đọc SUM(allocation)=90 rồi insert một hàng riêng.

- Viết invariant.
- Dựng lịch hai transaction.
- Giải thích vì sao CHECK (allocation <= 100) trên từng hàng không đủ.
- Đề xuất guard row hoặc atomic counter.

Gợi ý: tổng cuối 106; không có hàng đơn nào vượt 100.

### Bài 2 — Một job đang chạy

Quy tắc: mỗi tenant chỉ được có một job ở trạng thái RUNNING. Hai worker cùng query NOT EXISTS rồi insert hai job ID khác nhau.

- Xác định predicate được đọc.
- Nêu hai hàng được ghi.
- Chọn unique partial index (nếu mô hình trạng thái và DB hỗ trợ), guard row hoặc serializable.
- Tái hiện bằng hai connection.

### Bài 3 — Lịch trực ba người

Ban đầu A, B, C đều trực; quy tắc cần ít nhất hai người trực. T1 xin A nghỉ, T2 xin B nghỉ, T3 xin C nghỉ. Hãy tìm các lịch xen kẽ làm invariant sai và cơ chế bảo vệ.

Gợi ý: mỗi transaction có thể đọc tổng bằng 3; chỉ một người được nghỉ nếu quyết định tuần tự, nhưng nhiều transaction có thể cùng dựa trên snapshot cũ.

### Bài 4 — Phân biệt lỗi

Hai transaction cùng đọc một hàng counter=10, rồi đều cập nhật counter=11. Một bài khác, hai transaction đọc hai bác sĩ và lần lượt tắt mỗi người. Phân loại lost update hay write skew, nêu bằng chứng.

### Bài 5 — Retry sai cách

Ứng dụng dưới SERIALIZABLE nhận 40001, chỉ chạy lại câu UPDATE, không chạy lại câu SELECT đếm nhân sự.

- Tại sao sai?
- Những bước nào phải chạy lại?
- Nếu đã gửi email trong lần thử đầu thì có nguy cơ gì?
- Dùng outbox/idempotency ra sao?

### Bài 6 — Phân vùng guard

Một công ty có 100 nhóm, invariant áp dụng riêng từng nhóm. So sánh một guard toàn công ty với guard theo team_id. Trường hợp nào có thể cho phép các nhóm thay đổi đồng thời mà vẫn an toàn?

## 14. Tự đánh giá sau bài học

| Mức | Khả năng thể hiện |
| --- | --- |
| Chưa đạt | Chỉ nhớ “hai transaction update khác hàng” nhưng chưa nêu được điều kiện chung bị phá |
| Cơ bản | Dựng được ví dụ bác sĩ trực và mô tả hai lần đọc snapshot cũ |
| Khá | Phân biệt write skew với lost update; giải thích vì sao repeatable read có thể chưa đủ |
| Vững | Chọn và triển khai guard/constraint/serializable; xử lý conflict và retry đúng phạm vi |
| Áp dụng thực tế | Có test barrier tái hiện lỗi, assertion invariant, đo contention và kiểm soát tất cả đường ghi |

---

## Điều cần nhớ

Write skew xảy ra khi nhiều transaction cùng quyết định dựa trên một trạng thái chung nhưng cập nhật các hàng khác nhau. Không có xung đột ghi trực tiếp nên cơ chế chỉ phát hiện hai lần ghi cùng hàng có thể bỏ sót; trạng thái cuối cùng vẫn phá invariant đa hàng.

Để xử lý, hãy xác định **phạm vi invariant**, tạo một điểm tuần tự hóa thích hợp và kiểm thử lịch hai giao dịch cùng đọc trước khi ghi. Với PostgreSQL, SERIALIZABLE là lựa chọn tổng quát nhưng đòi hỏi retry toàn transaction khi gặp 40001; guard row, khóa tập hàng hoặc mô hình hóa invariant thành một hàng/constraint có thể phù hợp hơn khi muốn kiểm soát chi phí tranh chấp. Việc bảo vệ chỉ hoàn chỉnh khi mọi đường ghi tuân theo cùng quy tắc và các side effect ngoài DB chịu được retry.
