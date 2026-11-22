# SERIALIZABLE và thực thi tương đương một thứ tự tuần tự

`SERIALIZABLE` là mức cô lập đặt ra yêu cầu mạnh: kết quả của các giao dịch được commit phải tương đương với **một cách thực thi tuần tự nào đó**. Mỗi transaction vẫn có thể đọc, ghi và xen kẽ thời gian với transaction khác; hệ quản trị không nhất thiết phải chạy hết giao dịch này rồi mới bắt đầu giao dịch kế tiếp. Điều phải giữ là các quan sát và hiệu ứng đã commit có thể được giải thích bằng một thứ tự tuần tự hợp lệ.

Đây là điểm cốt lõi của chương **Mức cô lập** trong **Database Transaction Concurrency**. Để hiểu và áp dụng đúng `SERIALIZABLE`, cần phân biệt thực thi tuần tự với tương đương tuần tự, nhận diện các phụ thuộc đọc/ghi, hiểu khi nào một lịch có thể sắp xếp thành chuỗi, và chuẩn bị xử lý giao dịch bị hủy do xung đột.

## 1. Vì sao cần SERIALIZABLE?

Xét quy tắc nghiệp vụ: tổng phân bổ cho các dự án trong một phòng ban không vượt ngân sách 100. Hiện tại tổng đã dùng là 90. Hai request đồng thời đề nghị phân bổ thêm 8 cho hai dự án khác nhau.

Mỗi request làm theo logic: đọc tổng phân bổ hiện tại; nếu tổng + 8 không vượt 100 thì tạo phân bổ mới; rồi commit. Nếu cả hai cùng đọc được 90, mỗi request đều tính 98 và cho rằng hợp lệ. Hai hàng phân bổ riêng biệt có thể được ghi; tổng cuối là 106. Mỗi transaction đã thực hiện đúng phép tính trên dữ liệu mà nó thấy, nhưng hai kết quả cùng commit không thể được giải thích như một thứ tự chạy tuần tự theo quy tắc nghiệp vụ.

Điều kiện phải bảo vệ:

\[
\sum_{p \in Projects(department)} allocation(p)
\le department.limit
\]

`SERIALIZABLE` nhằm ngăn một lịch không thể giải thích bằng cách thực thi tuần tự các transaction được commit. Trong PostgreSQL, nếu cấu trúc phụ thuộc cho thấy các giao dịch không thể cùng commit theo cách tuần tự hợp lệ, DB có thể hủy một giao dịch với lỗi serialization; ứng dụng phải chạy lại toàn bộ transaction từ đầu.

## 2. Thực thi tuần tự và thực thi tương đương tuần tự

### 2.1 Lịch tuần tự (serial schedule)

Một lịch tuần tự chạy trọn transaction này trước khi transaction khác bắt đầu:

~~~text
T1: BEGIN
T1: READ X
T1: WRITE X
T1: COMMIT

T2: BEGIN
T2: READ X
T2: WRITE X
T2: COMMIT
~~~

Hoặc thứ tự ngược lại: chạy T2 hoàn tất rồi mới chạy T1. Không có thao tác của hai transaction xen kẽ. Lịch tuần tự dễ lập luận vì mỗi transaction nhìn thấy các hiệu ứng của giao dịch đứng trước nó theo quy tắc đọc của mô hình đang xét, nhưng nếu mọi yêu cầu đều phải đợi nhau hoàn tất thì khả năng xử lý đồng thời sẽ giảm mạnh.

### 2.2 Lịch không tuần tự (concurrent schedule)

Trong lịch đồng thời, thao tác có thể xen kẽ:

~~~text
T1: BEGIN ── READ X ───────────── WRITE Y ── COMMIT
T2:        BEGIN ── WRITE X ─ COMMIT
~~~

Lịch này không phải lịch tuần tự vì T1 và T2 chồng lấn. Tuy vậy, nó có thể tương đương với một thứ tự tuần tự nếu các lần đọc và kết quả ghi giống như khi chạy tuần tự theo một thứ tự phù hợp.

### 2.3 Tương đương tuần tự (serializability)

Một lịch là **serializable** nếu nó tương đương với ít nhất một lịch tuần tự về các hiệu ứng được định nghĩa trong mô hình tương đương đang dùng. Với cách tiếp cận thông dụng trong lý thuyết lịch, ta xét các thao tác đọc/ghi trên dữ liệu và những giá trị chúng quan sát.

Ví dụ, T1 chỉ sửa hàng A và T2 chỉ sửa hàng B, không đọc hoặc ghi dữ liệu liên quan của nhau. Hai giao dịch có thể xen kẽ nhưng thứ tự T1 → T2 và T2 → T1 đều cho cùng kết quả. Lịch đó tương đương với cả hai lịch tuần tự.

Điều quan trọng:

- **Serial execution** mô tả cách DB thực sự xếp thao tác: giao dịch chạy nối tiếp.
- **Serializability** mô tả tính chất của kết quả một lịch đồng thời: kết quả tương đương với một thứ tự chạy nối tiếp.
- **SERIALIZABLE isolation** là lời bảo đảm mà hệ quản trị cung cấp về những transaction được commit, theo ngữ nghĩa triển khai của DBMS.

`SERIALIZABLE` không có nghĩa mọi transaction nhất thiết bắt đầu theo thứ tự commit, cũng không nhất thiết bảo toàn thứ tự thời gian thực của mọi transaction chồng lấn. Đó là yêu cầu bổ sung của strict serializability.

### 2.4 Ví dụ hai giao dịch độc lập

Ban đầu `A=0`, `B=0`:

~~~text
T1: WRITE A=1
T2: WRITE B=1
~~~

Một lịch đồng thời:

~~~text
BEGIN T1
BEGIN T2
T1 WRITE A=1
T2 WRITE B=1
T2 COMMIT
T1 COMMIT
~~~

Hai thứ tự tuần tự đều hợp lệ: T1 rồi T2 hoặc T2 rồi T1. Cả hai cho `A=1, B=1`. Không có phụ thuộc dữ liệu giữa hai transaction. Do đó không cần ép một thứ tự duy nhất; DB có thể cho chúng chạy đồng thời mà kết quả vẫn serializable.

## 3. Các loại tương đương cần phân biệt

Từ “tương đương” phải gắn với tiêu chí rõ ràng. Hai khái niệm thường dùng trong lý thuyết lịch là conflict equivalence và view equivalence.

### 3.1 Conflict equivalence

Hai lịch conflict-equivalent nếu chúng chứa cùng các thao tác của cùng các giao dịch và giữ nguyên thứ tự tương đối của mọi cặp thao tác xung đột giữa hai transaction.

Hai thao tác xung đột khi chúng thuộc hai transaction khác nhau, truy cập cùng một mục dữ liệu, và ít nhất một thao tác là ghi.

| Cặp thao tác trên cùng X | Có xung đột? | Nếu thao tác thứ nhất ở Ti và thứ hai ở Tj |
| --- | --- | --- |
| `r_i(X)` rồi `r_j(X)` | Không | Không tạo cạnh |
| `r_i(X)` rồi `w_j(X)` | Có | Ti → Tj |
| `w_i(X)` rồi `r_j(X)` | Có | Ti → Tj |
| `w_i(X)` rồi `w_j(X)` | Có | Ti → Tj |

Hai lần đọc không xung đột vì cả hai chỉ quan sát dữ liệu. Đọc/ghi và ghi/ghi có thể thay đổi giá trị mà giao dịch kia quan sát hoặc giá trị cuối cùng.

**Conflict serializable** là lịch conflict-equivalent với một lịch tuần tự nào đó. Đây là tiêu chí dễ kiểm tra bằng đồ thị phụ thuộc.

### 3.2 View equivalence

View equivalence xem xét các quan hệ đọc từ đâu và ai là người ghi cuối cùng, thường với ba điều kiện:

1. Nếu một giao dịch đọc giá trị ban đầu của X trong lịch này, nó cũng đọc giá trị ban đầu của X trong lịch kia.
2. Nếu thao tác đọc `r_i(X)` đọc giá trị được tạo bởi `w_j(X)`, nó phải đọc từ cùng thao tác ghi `w_j(X)` ở lịch kia.
3. Với mỗi mục X, giao dịch ghi cuối cùng lên X phải giống nhau trong hai lịch.

View equivalence rộng hơn conflict equivalence. Có lịch view-serializable nhưng không conflict-serializable, thường liên quan đến **blind write** (ghi mà không đọc giá trị cũ). Vì vậy đồ thị xung đột là công cụ kiểm tra một lớp lịch cụ thể; chu trình trong đồ thị chứng minh lịch không conflict-serializable, nhưng không nên tự động suy rộng thành mọi tiêu chí tương đương lý thuyết.

### 3.3 Ví dụ blind write

Giả sử các thao tác chỉ ghi, không đọc:

~~~text
T1: W1(X=1), W1(X=2)
T2: W2(X=3)
~~~

Trong một số lịch có blind write, thứ tự cuối cùng của thao tác ghi và quan hệ đọc-from có thể được giữ dù việc đổi chỗ các thao tác xung đột tạo chu trình conflict. Đây là lý do view serializability là khái niệm rộng hơn. Trong thiết kế ứng dụng, người học có thể bắt đầu bằng conflict graph vì dễ hiểu và có thuật toán kiểm tra đơn giản; khi phân tích lịch phức tạp, cần nhớ giới hạn đó.

## 4. Đồ thị phụ thuộc (precedence graph)

Đối với lịch đọc/ghi một phiên bản, đồ thị phụ thuộc là phương pháp kinh điển để kiểm tra conflict serializability.

### 4.1 Cách dựng

1. Tạo một đỉnh cho mỗi transaction.
2. Tìm mọi cặp thao tác thuộc hai transaction khác nhau, trên cùng mục dữ liệu, có ít nhất một thao tác ghi.
3. Nếu thao tác của Ti đứng trước thao tác xung đột của Tj trong lịch, thêm cạnh có hướng `Ti → Tj`.
4. Lặp lại cho các mục dữ liệu khác.
5. Kiểm tra chu trình.

- Không có chu trình: lịch conflict-serializable.
- Có chu trình: lịch không conflict-serializable.
- Mỗi thứ tự topo của đồ thị không chu trình là một thứ tự tuần tự tương đương theo conflict equivalence.

### 4.2 Ví dụ có một thứ tự bắt buộc

Ban đầu `X=0`:

~~~text
T1: R1(X=0) ---------------- W1(Y=1) -- COMMIT
T2:          W2(X=1) -- COMMIT
~~~

T1 đọc X trước khi T2 ghi X, tạo cạnh T1 → T2. Thứ tự tuần tự phù hợp là T1 rồi T2. Mặc dù T2 commit trước, T2 phải đứng sau T1 trong thứ tự tương đương để T1 đọc được giá trị ban đầu.

### 4.3 Ví dụ có chu trình

Ban đầu `X=0, Y=0`:

~~~text
T1: R1(X=0) -------- W1(Y=1) -- COMMIT
T2:       R2(Y=0) -------- W2(X=1) -- COMMIT
~~~

Phân tích:

- T1 đọc X trước khi T2 ghi X ⇒ cạnh T1 → T2.
- T2 đọc Y trước khi T1 ghi Y ⇒ cạnh T2 → T1.

~~~mermaid
flowchart LR
    T1["T1"] -->|"r1(X) trước w2(X)"| T2["T2"]
    T2 -->|"r2(Y) trước w1(Y)"| T1
~~~

Đồ thị có chu trình. Không thể xếp T1 trước T2 và đồng thời T2 trước T1. Lịch không conflict-serializable; đây là dạng write skew điển hình khi các transaction ghi hai hàng khác nhau.

### 4.4 Thuật toán kiểm tra topo

Với N giao dịch và E cạnh, có thể dùng thuật toán Kahn:

~~~text
input: directed graph G(V, E)
compute indegree[v] for every vertex
queue all vertices with indegree 0
order = []

while queue is not empty:
    v = remove one vertex
    append v to order
    for each edge v -> u:
        indegree[u] -= 1
        if indegree[u] == 0:
            add u to queue

if length(order) == number_of_vertices:
    graph is acyclic
    order is one serial order
else:
    graph has a cycle
    no conflict-equivalent serial order exists
~~~

Thuật toán chạy trong O(V + E). Nếu có nhiều đỉnh indegree 0 ở cùng thời điểm, chọn theo thứ tự nào cũng có thể tạo một thứ tự topo hợp lệ. Điều đó phản ánh thực tế rằng có thể có nhiều lịch tuần tự tương đương.

## 5. SERIALIZABLE trong PostgreSQL

### 5.1 Các mức cô lập thường gặp

PostgreSQL hỗ trợ bốn tên mức cô lập theo SQL, nhưng `READ UNCOMMITTED` được xử lý như `READ COMMITTED`.

| Mức cô lập | Tầm nhìn/đặc điểm chính trong PostgreSQL | Rủi ro cần hiểu |
| --- | --- | --- |
| `READ COMMITTED` | Snapshot mới cho mỗi câu lệnh | Non-repeatable read, phantom và các lịch đọc-kiểm-tra-ghi sai có thể xảy ra |
| `REPEATABLE READ` | Snapshot ổn định của transaction; triển khai theo snapshot isolation | Chặn một số anomaly nhưng write skew vẫn có thể xảy ra |
| `SERIALIZABLE` | Snapshot isolation kết hợp phát hiện phụ thuộc tuần tự hóa (SSI) | Transaction có thể bị hủy với serialization failure; ứng dụng phải retry |

Không nên lấy tên mức cô lập để đoán hành vi của mọi DBMS. Các hệ thống có locking-based repeatable read, snapshot isolation hay MVCC khác nhau có thể đưa ra bảo đảm khác nhau.

### 5.2 PostgreSQL không cần khóa toàn bộ dữ liệu để đạt SERIALIZABLE

PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** cho mức `SERIALIZABLE`. Các giao dịch đọc theo snapshot; DB theo dõi những phụ thuộc đọc/ghi có thể tạo chu trình tuần tự hóa.

Một dạng phụ thuộc quan trọng là *read-write anti-dependency*: T1 đọc một giá trị hoặc điều kiện mà T2 sau đó làm thay đổi. Nếu kết hợp các phụ thuộc tạo thành cấu trúc không thể sắp xếp tuần tự hợp lệ, SSI có thể từ chối một transaction.

Để phát hiện các tương tác theo predicate, PostgreSQL có thể dùng **predicate lock** (hiển thị với chế độ `SIReadLock`). Đây là dấu vết theo dõi đọc phục vụ phát hiện xung đột; không nên hiểu chúng như row lock thông thường luôn chặn writer. SSI có thể cho phép nhiều giao dịch tiếp tục chạy, rồi hủy một bên khi cần để duy trì serializability.

### 5.3 Không đồng nghĩa khóa bi quan

Một triển khai serializable có thể dùng khóa mạnh và buộc giao dịch đợi nhau. PostgreSQL SSI có cách tiếp cận khác: thường không đơn giản khóa toàn bộ dữ liệu mà các transaction đọc. Nó theo dõi phụ thuộc và có thể báo serialization failure.

Do đó:

- `SERIALIZABLE` không phải cú pháp khác của `SELECT FOR UPDATE`.
- Không phải mọi xung đột đều thể hiện bằng thời gian chờ khóa.
- Một transaction có thể chạy gần hết rồi mới bị hủy khi commit.
- Ứng dụng phải xem serialization failure là kết quả có thể xảy ra của giao dịch đồng thời bình thường, không nhất thiết là lỗi DB không thể phục hồi.

### 5.4 Predicate và phantom

Ví dụ transaction T1 đọc:

~~~sql
SELECT count(*)
FROM reservations
WHERE resource_id = 9
  AND starts_at < TIMESTAMP '2026-12-01 11:00'
  AND ends_at > TIMESTAMP '2026-12-01 10:00';
~~~

T2 thêm một reservation mới phù hợp predicate. Dù hai transaction không sửa cùng một hàng đã tồn tại, tập kết quả mà T1 dựa vào có thể bị thay đổi. Nếu chỉ dựng đồ thị trên các row ID đã tồn tại, có thể bỏ sót quan hệ với hàng mới thỏa điều kiện.

SSI theo dõi tương tác đọc/ghi ở mức predicate để phát hiện các phụ thuộc kiểu này. Khi tự phân tích, cần ghi truy vấn và tập hàng mà nó bao phủ, không chỉ các ID cụ thể đã trả về.

## 6. Serialization failure và retry toàn bộ transaction

### 6.1 SQLSTATE 40001

Trong PostgreSQL, lỗi serialization failure thường mang SQLSTATE `40001`. Nó cho biết hệ quản trị không thể cho transaction hoàn tất mà vẫn giữ bảo đảm yêu cầu. Lỗi có thể xuất hiện khi chạy câu lệnh hoặc lúc commit. Không được giả định một transaction đã thực hiện hết các câu UPDATE thì chắc chắn commit thành công.

### 6.2 Vì sao phải chạy lại từ đầu?

Quay lại ví dụ ngân sách. T1 và T2 cùng đọc tổng 90. Nếu T2 bị hủy, chỉ chạy lại câu INSERT phân bổ của T2 vẫn dựa trên quyết định cũ. Nó phải đọc lại tổng sau khi T1 đã commit: lúc này tổng là 98, nên yêu cầu thứ hai phải bị từ chối.

Luồng retry đúng:

~~~text
function allocateBudget(request):
    for attempt in 1..MAX_ATTEMPTS:
        try:
            BEGIN ISOLATION LEVEL SERIALIZABLE

            currentTotal = SELECT SUM(amount)
                           FROM allocations
                           WHERE department_id = request.departmentId

            if currentTotal + request.amount > departmentLimit:
                ROLLBACK
                return BUSINESS_REJECTION

            INSERT INTO allocations(...)
            VALUES (...)

            COMMIT
            return SUCCESS

        catch error:
            if SQLSTATE(error) != "40001":
                ROLLBACK if transaction remains open
                raise error

            ROLLBACK if transaction remains open

            if attempt == MAX_ATTEMPTS:
                return RETRYABLE_FAILURE

            wait(exponentialBackoffWithJitter(attempt))
~~~

Mỗi lần retry phải là transaction mới với snapshot mới, đọc lại mọi dữ liệu ảnh hưởng quyết định, kiểm tra lại invariant và thực hiện lại toàn bộ thao tác DB.

### 6.3 Phân biệt lỗi có thể retry và lỗi nghiệp vụ

| Loại kết quả | Ví dụ | Hành vi ứng dụng |
| --- | --- | --- |
| Serialization failure | SQLSTATE `40001` | Retry toàn bộ transaction có giới hạn |
| Deadlock detected | PostgreSQL SQLSTATE `40P01` | Có thể retry toàn bộ transaction theo chính sách |
| Vi phạm unique | SQLSTATE `23505` | Thường là kết quả nghiệp vụ hoặc lỗi dữ liệu; phân loại trước khi quyết định retry |
| Vi phạm CHECK/FK | SQLSTATE `23514` / `23503` | Thường cần xử lý logic/dữ liệu, không retry mù quáng |
| Không đủ ngân sách | Điều kiện nghiệp vụ không còn thỏa | Từ chối nghiệp vụ, không retry vô hạn |
| Mất kết nối khi commit | Client không chắc DB đã commit hay chưa | Cần idempotency key/đọc lại trạng thái để xác định kết quả |

Có thể xây dựng cơ chế retry dùng chung cho `40001` và một số trường hợp `40P01`, nhưng phải phân loại riêng, ghi log số lần thử và đặt giới hạn. Backoff có jitter giúp giảm tình trạng nhiều transaction retry đồng loạt và lại xung đột cùng lúc.

### 6.4 Side effect ngoài DB cần idempotency

Một transaction bị hủy và retry có thể chạy lại code ứng dụng. Nếu code gửi email, gọi cổng thanh toán, phát message hoặc gọi HTTP API ngay trong lần thử đầu, side effect có thể đã xảy ra dù DB rollback.

Cách tiếp cận thường dùng:

1. Trong transaction serializable, ghi dữ liệu nghiệp vụ và một bản ghi outbox.
2. Commit transaction.
3. Worker đọc outbox và phát sự kiện.
4. Consumer dùng idempotency/deduplication để chịu được gửi lặp.

Retry `40001` chỉ chạy lại phần DB transaction. Side effect nên được trì hoãn tới sau commit hoặc được thiết kế idempotent.

### 6.5 Khi kết quả COMMIT không tới client

Một tình huống khác là DB đã commit nhưng kết nối bị ngắt trước khi ứng dụng nhận phản hồi. Client không biết transaction thành công hay chưa. Không nên coi mọi lỗi mạng lúc commit là serialization failure và cứ tạo nghiệp vụ lại. Hãy dùng request ID/idempotency key có ràng buộc duy nhất và lưu kết quả để cùng một ý định gửi lại không tạo hiệu ứng trùng.

## 7. Thực hành PostgreSQL: so sánh REPEATABLE READ và SERIALIZABLE

Bài thực hành tái hiện write skew với hai bác sĩ. Mục tiêu là chứng minh cả hai có thể commit ở `REPEATABLE READ`, nhưng không thể cùng commit trong lịch không serializable ở `SERIALIZABLE`.

### 7.1 Chuẩn bị

Chỉ chạy trong database thử nghiệm:

~~~sql
DROP TABLE IF EXISTS on_call_lab;

CREATE TABLE on_call_lab (
    doctor_id text PRIMARY KEY,
    is_on_call boolean NOT NULL
);

INSERT INTO on_call_lab(doctor_id, is_on_call)
VALUES ('A', true), ('B', true);
~~~

Mở hai cửa sổ psql độc lập, gọi là Session A và Session B.

### 7.2 Thử ở REPEATABLE READ

Session A:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM on_call_lab WHERE is_on_call;
-- 2; giữ transaction mở
~~~

Session B:

~~~sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT count(*) FROM on_call_lab WHERE is_on_call;
-- 2; giữ transaction mở
~~~

Session A:

~~~sql
UPDATE on_call_lab
SET is_on_call = false
WHERE doctor_id = 'A';
~~~

Session B:

~~~sql
UPDATE on_call_lab
SET is_on_call = false
WHERE doctor_id = 'B';
COMMIT;
~~~

Quay lại Session A:

~~~sql
COMMIT;
~~~

Kiểm tra trạng thái:

~~~sql
SELECT count(*) AS active_doctors
FROM on_call_lab
WHERE is_on_call;
-- Có thể bằng 0: write skew
~~~

### 7.3 Chạy lại với SERIALIZABLE

Reset:

~~~sql
UPDATE on_call_lab SET is_on_call = true;
~~~

Ở cả hai session, bắt đầu:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;
SELECT count(*) FROM on_call_lab WHERE is_on_call;
-- 2
~~~

Giữ cả hai transaction sau bước đọc, rồi cho A cập nhật hàng A và B cập nhật hàng B. Thử commit cả hai. Một transaction có thể nhận serialization failure. Rollback session nhận lỗi nếu transaction còn mở, rồi kiểm tra:

~~~sql
SELECT count(*) AS active_doctors
FROM on_call_lab
WHERE is_on_call;
~~~

Không được để kết quả cuối là 0 nếu cả hai quyết định rời ca đều yêu cầu duy trì ít nhất một người trực. Nếu retry transaction thua từ đầu, truy vấn đếm sẽ thấy kết quả mới; yêu cầu cuối cùng sẽ bị từ chối. Không phụ thuộc transaction A hay B luôn là bên thắng.

### 7.4 Ghi lại bằng chứng

Với từng lần chạy, lưu:

- DBMS và phiên bản.
- Isolation level của từng session.
- Trạng thái ban đầu.
- Thứ tự từng câu lệnh và kết quả SELECT.
- Transaction nào commit hoặc abort; SQLSTATE nếu có.
- Trạng thái cuối và assertion invariant.
- Retry được chạy lại từ đầu hay chỉ chạy lại một câu lệnh.

Chỉ ghi “test pass” mà không giữ timeline sẽ rất khó chứng minh test đã tạo được lịch write skew mong muốn.

## 8. Khi nào nên chọn SERIALIZABLE?

`SERIALIZABLE` hữu ích khi logic phụ thuộc nhiều hàng, predicate hoặc các tương tác khó bảo vệ bằng một khóa cụ thể. Ví dụ:

- Kiểm tra tổng phân bổ so với giới hạn.
- Quy tắc số người tối thiểu theo nhóm.
- Kiểm tra không tồn tại bản ghi thỏa điều kiện rồi mới insert.
- Chọn tài nguyên có điều kiện trên nhiều hàng.
- Workflow gồm nhiều thao tác đọc/ghi mà việc khóa thủ công toàn bộ tập dữ liệu rất dễ bỏ sót.

Ưu điểm: cung cấp mô hình lập luận thống nhất; giảm nhu cầu tự thiết kế khóa cho từng quan hệ khó nhận diện; bắt được tương tác phức tạp giữa đọc và ghi, bao gồm phụ thuộc không thể nhìn như ghi đè cùng hàng.

Chi phí và giới hạn:

- Một transaction hợp lệ về nghiệp vụ có thể bị hủy do xung đột với transaction đồng thời.
- Ứng dụng cần retry toàn bộ transaction, có giới hạn và đo tỷ lệ retry.
- Theo dõi phụ thuộc và predicate có chi phí bộ nhớ/CPU; workload có nhiều xung đột có thể giảm throughput.
- Transaction dài làm cửa sổ tương tác lớn hơn và dễ phát sinh conflict.
- Side effect ngoài DB không tự động hoàn tác cùng transaction.
- Một giao dịch đơn lẻ có lỗi logic vẫn có thể commit; serializable không thay thế constraint và kiểm tra nghiệp vụ.

### 8.1 Khi nào dùng guard row hoặc khóa bi quan?

Nếu invariant có phạm vi rõ, chẳng hạn ngân sách của một phòng ban, một guard row theo department có thể tuần tự hóa đúng phần cần thiết:

~~~sql
BEGIN;

SELECT department_id
FROM department_budget_guard
WHERE department_id = 10
FOR UPDATE;

-- Đọc tổng phân bổ sau khi lấy khóa.
SELECT COALESCE(SUM(amount), 0)
FROM allocations
WHERE department_id = 10;

-- Kiểm tra, INSERT hoặc từ chối.
COMMIT;
~~~

Mọi transaction thay đổi ngân sách phòng ban đó phải dùng cùng guard. Các phòng ban khác nhau vẫn có thể xử lý song song. Guard dễ hiểu, nhưng giao thức phải được mọi đường ghi tuân thủ và thứ tự khóa phải thống nhất để tránh deadlock.

### 8.2 Khi nào constraint phù hợp hơn?

Nếu quy tắc có thể biểu diễn bằng `UNIQUE`, `CHECK`, `FOREIGN KEY` hoặc exclusion constraint, để DB cưỡng chế trực tiếp thường rõ ràng hơn. Ví dụ “một ghế chỉ được đặt một lần” phù hợp với unique constraint. Nhưng CHECK thông thường kiểm tra từng hàng, không phải tổng nhiều hàng; phải chọn mô hình dữ liệu/constraint phù hợp cho invariant đa hàng.

### 8.3 Không nhất thiết chuyển mọi transaction sang SERIALIZABLE

Có thể áp dụng mức serializable cho các nghiệp vụ có invariant phức tạp, còn thao tác đơn giản khác dùng mức phù hợp thấp hơn cùng constraint/atomic update. Việc chọn isolation là quyết định theo transaction và workload, phải kiểm chứng trên DBMS thực tế.

Điều quan trọng là không có đường code nào âm thầm phá invariant mà các transaction khác dựa vào. Một invariant có thể cần nhiều luồng cập nhật dùng chung giao thức, kể cả khi một luồng không khai báo SERIALIZABLE.

## 9. SERIALIZABLE có phải strict serializability?

Không. Hai khái niệm liên quan nhưng khác nhau.

**Serializability** yêu cầu một thứ tự tuần tự tương đương với các quan sát của lịch đồng thời.

**Strict serializability** thêm ràng buộc thời gian thực: nếu transaction T1 hoàn tất trước khi T2 bắt đầu, thứ tự tuần tự phải đặt T1 trước T2. Với hai transaction chồng lấn, thứ tự của chúng vẫn có thể được chọn theo phụ thuộc dữ liệu.

Ví dụ, T1 commit lúc 10:00:00 và client đã nhận thành công. T2 chỉ bắt đầu lúc 10:00:05. Strict serializability buộc T1 đứng trước T2. Còn serializability đơn thuần không tự thêm ràng buộc real-time như vậy.

Vì thế không nên coi `SERIALIZABLE` trong DBMS là đồng nghĩa với linearizability cho mọi API phân tán. Muốn bảo đảm thời gian thực trên toàn hệ thống còn cần xem cache, replica, message, dịch vụ bên ngoài và cách client quan sát kết quả.

## 10. SERIALIZABLE không giải quyết mọi loại lỗi dữ liệu

- **Transaction đơn lẻ sai logic:** nếu một transaction duy nhất cho phép số dư âm vì không kiểm tra điều kiện, nó vẫn có thể commit dưới SERIALIZABLE. Hãy dùng CHECK, atomic update có điều kiện và kiểm tra nghiệp vụ.
- **Ghi dữ liệu ngoài transaction:** email hoặc HTTP call đã gửi không rollback khi transaction bị hủy. Dùng outbox, idempotency và compensation theo nghiệp vụ.
- **Retry không giới hạn:** khi xung đột cao, nhiều transaction retry vô hạn có thể làm tải tăng. Cần giới hạn, backoff, quan sát tỷ lệ lỗi và trả lỗi có thể retry cho caller khi vượt ngưỡng.
- **Đọc từ replica hoặc cache:** transaction ở primary với serializable không có nghĩa mọi lần đọc từ replica/cache cũng có cùng bảo đảm.
- **Tương tác nhiều hệ thống:** transaction serializable trong PostgreSQL không tạo ra transaction toàn cục bao phủ Kafka, Redis, payment gateway và các dịch vụ khác. Cần thiết kế saga/outbox/idempotency phù hợp.

## 11. Quy trình phân tích và thiết kế

1. **Viết invariant:** điều kiện nào phải luôn đúng, gồm hàng nào và predicate nào?
2. **Vẽ lịch hai hoặc nhiều transaction:** xác định các lần đọc, ghi, giá trị đọc và commit/abort.
3. **Kiểm tra phụ thuộc:** thao tác đọc/ghi cùng dữ liệu, predicate và các phụ thuộc giữa phiên bản.
4. **Dựng precedence graph** nếu đang xét conflict serializability; kiểm tra chu trình.
5. **Xác định bảo đảm cần có:** serializability, strict serializability hay chỉ invariant cụ thể.
6. **Chọn cơ chế:** SERIALIZABLE, guard row, khóa tập hàng, constraint hoặc atomic update.
7. **Thiết kế đường conflict:** xử lý 40001, deadlock, từ chối nghiệp vụ và retry toàn transaction.
8. **Tách side effect:** dùng outbox/idempotency cho tác động ngoài DB.
9. **Viết test barrier:** ép hai transaction đọc cùng snapshot trước khi ghi.
10. **Đo vận hành:** retry rate, lock wait, latency, throughput và transaction duration.

## 12. Bài tập tự luyện

### Bài 1 — Hai dự án cùng xin ngân sách

Ngân sách là 100, tổng hiện tại 90. T1 thêm 8 cho dự án A; T2 thêm 8 cho dự án B.

- Viết invariant.
- Cho T1 và T2 cùng đọc tổng 90 rồi ghi hàng khác nhau.
- Giải thích vì sao kết quả cuối 106 không tương đương một thứ tự hợp lệ theo quy tắc cấp ngân sách.
- Nêu cách xử lý bằng SERIALIZABLE và bằng guard row.

Gợi ý: sau khi một transaction commit, transaction còn lại phải đọc lại tổng là 98 và từ chối.

### Bài 2 — Tìm chu trình trong precedence graph

Cho lịch:

~~~text
r1(X), r2(Y), w1(Y), w2(X), c1, c2
~~~

- Các cặp nào xung đột?
- Có cạnh nào?
- Có chu trình không?
- Vì sao hai transaction cùng ghi khác hàng vẫn không thể cùng commit theo lịch này mà tương đương tuần tự?

Gợi ý: T1 đọc X trước khi T2 ghi X; T2 đọc Y trước khi T1 ghi Y.

### Bài 3 — Nhiều thứ tự tuần tự hợp lệ

T1 ghi A; T2 ghi B; T3 đọc C. Không transaction nào khác truy cập cùng dữ liệu.

- Có cạnh phụ thuộc nào?
- Có bao nhiêu thứ tự topo?
- Tại sao serializable không yêu cầu duy nhất một serial order?

Gợi ý: không có phụ thuộc giữa ba transaction nên có thể đổi chỗ tự do.

### Bài 4 — Retry toàn transaction

Một ứng dụng nhận SQLSTATE 40001 sau khi đọc tổng và cập nhật phân bổ.

- Vì sao chạy lại mỗi câu UPDATE không an toàn?
- Vì sao cần đọc lại mọi dữ liệu ảnh hưởng invariant?
- Nếu transaction đã gọi API thanh toán, nên thay đổi thiết kế như thế nào?

### Bài 5 — SERIALIZABLE và real time

T1 bắt đầu trước T2 nhưng hai giao dịch chồng lấn. Log cho thấy thứ tự tương đương có T2 trước T1.

- Điều này có vi phạm serializability không?
- Điều kiện nào mới buộc thứ tự thời gian thực?
- Strict serializability thêm yêu cầu gì?

## 13. Tiêu chí tự đánh giá

| Mức | Kết quả học tập |
| --- | --- |
| Chưa đạt | Đồng nhất SERIALIZABLE với việc mọi transaction chạy nối tiếp thật sự |
| Cơ bản | Phân biệt serial schedule và serializable schedule bằng một ví dụ đọc/ghi |
| Khá | Dựng precedence graph, nhận diện chu trình và nêu một thứ tự topo |
| Vững | Hiểu giới hạn conflict serializability, snapshot isolation và cách PostgreSQL dùng SSI |
| Áp dụng thực tế | Triển khai retry toàn transaction, idempotency/outbox, test concurrency có barrier và đo retry/latency |

---

## Điều cần nhớ

`SERIALIZABLE` cho phép hệ thống chạy transaction đồng thời, nhưng chỉ chấp nhận kết quả có thể giải thích bằng một thứ tự tuần tự tương đương. Đồ thị phụ thuộc giúp phân tích conflict serializability; chu trình cho thấy không thể sắp xếp các giao dịch theo tiêu chí này. PostgreSQL dùng SSI để phát hiện các cấu trúc phụ thuộc nguy hiểm và có thể hủy một transaction bằng SQLSTATE `40001`.

Vì vậy, ứng dụng phải xem serialization failure là một nhánh bình thường của xử lý đồng thời: rollback và chạy lại **toàn bộ transaction**, đọc lại dữ liệu, kiểm tra lại invariant, giới hạn retry và bảo vệ side effect ngoài DB. Chọn SERIALIZABLE khi invariant khó bảo vệ thủ công; với phạm vi hẹp hơn, guard row, constraint hoặc atomic update có điều kiện có thể đem lại cách triển khai dễ kiểm soát hơn.
