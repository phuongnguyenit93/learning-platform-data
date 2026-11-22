# Đối chiếu mức cô lập theo bất thường và bất biến cần bảo vệ

Chọn mức cô lập (isolation level) không nên bắt đầu bằng câu hỏi “mức nào mạnh nhất?” mà nên bắt đầu từ **bất biến nghiệp vụ nào phải luôn đúng khi nhiều giao dịch chạy đồng thời**. Sau đó mới xác định những lịch giao dịch nào có thể phá vỡ bất biến, mức cô lập nào loại bỏ được lịch đó, và có cần bổ sung constraint, câu lệnh cập nhật nguyên tử hay khóa tường minh hay không.

Một mức cô lập mô tả DBMS cho phép giao dịch quan sát và tương tác với thay đổi đồng thời như thế nào. Những bất thường như dirty read, non-repeatable read, phantom read, lost update và write skew giúp nhận diện nguy cơ. Nhưng **không có ánh xạ một-một đơn giản từ một bất thường sang một isolation level**: cùng anomaly có thể được xử lý khác nhau giữa DBMS, và một bất biến nghiệp vụ có thể cần nhiều cơ chế cùng lúc.

Bài học này cung cấp cách đối chiếu có hệ thống: mô tả bất biến, tạo lịch phản ví dụ, xác định anomaly, chọn mức cô lập, bổ sung ràng buộc và kiểm chứng bằng các transaction đồng thời.

## 1. Bắt đầu từ bất biến nghiệp vụ

**Bất biến (invariant)** là điều kiện phải đúng đối với trạng thái dữ liệu ở những thời điểm mà hệ thống cam kết là hợp lệ. Bất biến có thể liên quan một hàng, nhiều hàng, một tập dữ liệu theo điều kiện, hoặc cả quy trình đi qua nhiều dịch vụ.

Ví dụ:

| Nghiệp vụ | Bất biến cần bảo vệ | Phạm vi |
|---|---|---|
| Kho hàng | Số lượng khả dụng không âm: `available >= 0` | Một hàng sản phẩm |
| Chuyển tiền | Số dư khả dụng không âm; khoản trừ và cộng cùng được xác nhận | Hai hoặc nhiều hàng tài khoản |
| Đặt ghế | Mỗi ghế chỉ có tối đa một booking đang hiệu lực cho một chuyến | Nhiều yêu cầu cùng một khóa ghế/chuyến |
| Nhân sự trực | Luôn có ít nhất một người trực trong ca | Tập hàng nhân viên theo ca |
| Hạn mức tín dụng | Tổng dư nợ của khách hàng không vượt hạn mức | Nhiều khoản vay/giao dịch theo khách hàng |
| Xử lý đơn hàng | Một đơn chỉ chuyển trạng thái theo các cạnh hợp lệ của state machine | Một hàng đơn hàng, đôi khi nhiều bảng |
| Checkout | Cùng một ý định request không tạo nhiều đơn hoặc thanh toán lặp | Nhiều lần gọi API và hệ thống ngoài DB |

Bất biến cần được diễn đạt đủ cụ thể để có thể kiểm tra. “Dữ liệu phải nhất quán” chưa đủ. “Không có hai booking CONFIRMED cùng trip_id và seat_id” hoặc “tổng số tiền đã phân bổ không vượt số dư” có thể chuyển thành điều kiện kiểm thử và đôi khi thành constraint.

### 1.1. Bất biến trên một hàng

Một số quy tắc chỉ phụ thuộc trạng thái một hàng:

```text
inventory.available >= 0
account.balance >= 0
order.total_amount >= 0
```

Những điều kiện này thường có thể bảo vệ bằng `NOT NULL`, `CHECK` và câu lệnh cập nhật có điều kiện. Mức cô lập mạnh nhất không phải lúc nào cũng cần thiết nếu một câu lệnh nguyên tử và constraint đã bảo vệ đúng bất biến.

### 1.2. Bất biến trên nhiều hàng hoặc một predicate

Các quy tắc như “ít nhất một bác sĩ trực”, “không vượt 100 ghế”, hoặc “tổng dư nợ nhỏ hơn hạn mức” liên quan tới tập hàng. Việc hai transaction cập nhật những hàng khác nhau vẫn có thể phá vỡ bất biến chung.

Đây là nơi cần đặc biệt xem xét:

- Predicate/range: tập hàng thỏa điều kiện truy vấn có thể thay đổi.
- Write skew: giao dịch đọc chung một trạng thái rồi sửa các hàng khác nhau.
- Tổng hợp: kết quả SUM/COUNT có thể bị thay đổi giữa lúc kiểm tra và cập nhật.
- Phụ thuộc xuyên bảng: tính đúng của một hàng phụ thuộc dữ liệu ở bảng khác.

Một `CHECK` thông thường chỉ đánh giá một hàng; không thể mặc định dùng nó để bảo vệ tổng nhiều hàng. Cần xem constraint đặc thù của DBMS, schema, locking protocol hoặc `SERIALIZABLE` phù hợp.

## 2. Ma trận anomaly: mỗi mức cô lập bảo vệ điều gì?

Bốn mức SQL truyền thống thường được giới thiệu qua ba hiện tượng: dirty read, non-repeatable read và phantom read.

| Isolation level theo mô hình SQL | Dirty read | Non-repeatable read | Phantom read |
|---|---|---|---|
| `READ UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ COMMITTED` | Ngăn | Có thể | Có thể |
| `REPEATABLE READ` | Ngăn | Ngăn | Có thể theo mô hình chuẩn |
| `SERIALIZABLE` | Ngăn | Ngăn | Ngăn |

Đây là ma trận khái niệm dựa trên các anomaly kinh điển. Nó **không mô tả hết lost update, write skew, mọi serialization anomaly hay cách triển khai thực tế**.

### 2.1. Dirty read

T1 thay đổi dữ liệu nhưng chưa commit. T2 đọc giá trị đó. Nếu T1 rollback, T2 đã dùng một giá trị không bao giờ được xác nhận.

```text
T1: BEGIN
T1: UPDATE account SET balance = 0
T2:                         SELECT balance -> 0
T1: ROLLBACK
T2:                         tiếp tục dùng giá trị đã đọc
```

Nếu nghiệp vụ không được phép dựa trên thay đổi chưa commit, cần isolation ngăn dirty read. `READ COMMITTED` thường đã đủ cho mục tiêu cụ thể này; không cần suy ra bắt buộc phải dùng `SERIALIZABLE`.

### 2.2. Non-repeatable read

T1 đọc một hàng hai lần. Giữa hai lần, T2 cập nhật hàng đó và commit. T1 nhìn thấy hai giá trị khác nhau.

```text
T1: SELECT status -> PENDING
T2: UPDATE status = CONFIRMED; COMMIT
T1: SELECT status -> CONFIRMED
```

Nếu logic T1 đòi hỏi một giá trị ổn định trong cả transaction, cần isolation hoặc snapshot bảo đảm tính đọc lặp lại. Nếu T1 chỉ cần biết trạng thái mới nhất tại mỗi câu truy vấn, `READ COMMITTED` có thể phù hợp hơn.

### 2.3. Phantom read

T1 truy vấn tập hàng theo điều kiện. T2 thêm, xóa hoặc sửa một hàng khiến nó thỏa điều kiện rồi commit. Khi T1 chạy lại truy vấn, số hàng hoặc tập kết quả thay đổi.

Ví dụ:

```sql
-- T1
SELECT *
FROM bookings
WHERE trip_id = 50
  AND status = 'CONFIRMED';

-- T2
INSERT INTO bookings(id, trip_id, seat_no, status)
VALUES (900, 50, 'A10', 'CONFIRMED');
COMMIT;

-- T1 chạy lại truy vấn
SELECT *
FROM bookings
WHERE trip_id = 50
  AND status = 'CONFIRMED';
```

Nếu nghiệp vụ cần bảo vệ một predicate, cần xem DBMS có dùng range/predicate lock hoặc cơ chế serializable để ngăn lịch không hợp lệ không. Khóa những hàng đã đọc không nhất thiết ngăn hàng mới xuất hiện trong khoảng tìm kiếm.

## 3. Lost update và write skew cần được đối chiếu riêng

Ba anomaly ở ma trận SQL không đủ để thiết kế các nghiệp vụ ghi đồng thời. Hai nguy cơ quan trọng khác là lost update và write skew.

### 3.1. Lost update

Giá trị ban đầu `quantity = 10`. T1 và T2 cùng đọc 10, sau đó mỗi bên tính giảm một và ghi 9:

```text
T1: READ quantity -> 10
T2: READ quantity -> 10
T1: WRITE quantity = 9
T2: WRITE quantity = 9
T1: COMMIT
T2: COMMIT
```

Kỳ vọng sau hai lần xuất hàng là 8, nhưng kết quả là 9. Một lần cập nhật đã bị ghi đè.

Hướng bảo vệ thường hợp lý:

```sql
UPDATE inventory
SET quantity = quantity - 1
WHERE product_id = 42
  AND quantity >= 1;
```

Cập nhật điều kiện được thực thi nguyên tử ở DBMS. Ứng dụng kiểm tra số hàng ảnh hưởng: `1` là cập nhật thành công; `0` là không đủ tồn hoặc không tìm thấy hàng. Nếu phải đọc nhiều thuộc tính rồi tính toán, có thể dùng `SELECT ... FOR UPDATE` hoặc cột version cho optimistic locking. Cách DBMS phát hiện lost update ở từng isolation level vẫn cần kiểm chứng.

### 3.2. Write skew

Quy tắc: mỗi ca trực luôn có ít nhất một bác sĩ. T1 và T2 cùng đọc hai bác sĩ A và B đều đang trực. T1 tắt A; T2 tắt B. Vì hai transaction ghi hai hàng khác nhau, một số hệ thống dùng snapshot isolation có thể cho cả hai commit.

```text
Ban đầu: A.on_call = TRUE; B.on_call = TRUE

T1: đọc A, B -> thấy 2 người trực
T2: đọc A, B -> thấy 2 người trực
T1: UPDATE A.on_call = FALSE
T2: UPDATE B.on_call = FALSE
T1: COMMIT
T2: COMMIT

Kết quả: không còn ai trực
```

Giữ snapshot ổn định không đồng nghĩa bảo vệ được điều kiện trên tập hàng. Hướng xử lý có thể là:

- Dùng `SERIALIZABLE` và retry toàn bộ transaction khi có serialization failure.
- Khóa một hàng điều phối chung cho từng ca trước khi kiểm tra và thay đổi; tất cả đường cập nhật phải tuân thủ cùng giao thức.
- Tái mô hình hóa quy tắc để có thể dùng constraint DBMS phù hợp.

Chỉ khóa riêng hàng A cho T1 và hàng B cho T2 không bảo vệ bất biến “ít nhất một người trực”.

## 4. Đối chiếu theo loại bất biến

Bảng dưới đây là điểm khởi đầu khi chọn cơ chế. Kết quả cuối cùng phụ thuộc DBMS, truy vấn, index, transaction boundary và workload.

| Bất biến | Nguy cơ chính | Bảo vệ thường phù hợp | Isolation cần cân nhắc |
|---|---|---|---|
| Số lượng một sản phẩm không âm | Lost update, hai giao dịch cùng trừ | `UPDATE ... WHERE quantity >= :n` + `CHECK` | `READ COMMITTED` có thể đủ nếu câu lệnh nguyên tử; khóa/version nếu logic nhiều bước |
| Mỗi email chỉ thuộc một người dùng | Hai transaction cùng kiểm tra “chưa tồn tại” | `UNIQUE(email)` | Constraint là bảo vệ chính; xử lý conflict |
| Một ghế chỉ đặt một lần | Phantom / insert cạnh tranh | Unique key theo chuyến-ghế-trạng thái hoặc cơ chế constraint phù hợp | Isolation theo DBMS; kiểm tra constraint tại insert/commit |
| Số bác sĩ trực tối thiểu là một | Write skew | Khóa chung, constraint phù hợp hoặc kiểm soát transaction trên tập hàng | `SERIALIZABLE` thường cần xem xét |
| Tổng phân bổ không vượt hạn mức | Write skew, predicate change, lost update | Hàng tổng hợp/ledger, khóa hạn mức hoặc kiểm soát serializable | `SERIALIZABLE` hoặc cơ chế điều phối rõ |
| Báo cáo cần snapshot thống nhất | Non-repeatable read, phantom giữa các truy vấn | Một read-only transaction dùng snapshot chung | Transaction snapshot / `REPEATABLE READ` tùy DBMS |
| Chuyển tiền hai tài khoản | Partial update, xung đột cùng hàng | Cùng transaction, khóa/cập nhật điều kiện, constraint | Mức phù hợp với thao tác; `SERIALIZABLE` khi có phụ thuộc rộng |
| Đơn hàng chuyển trạng thái hợp lệ | Lost update, transition race | Cập nhật có điều kiện theo trạng thái hoặc version | `READ COMMITTED` kèm conditional update có thể đủ |
| Request retry không tạo hai đơn | Duplicate request | Idempotency key + UNIQUE | Không giải quyết chỉ bằng isolation; cần thiết kế ở API và DB |

### 4.1. Vì sao constraint thường mạnh hơn một lần SELECT kiểm tra?

Giả sử tạo user với email duy nhất. Mẫu sau dễ có race:

```sql
SELECT COUNT(*)
FROM users
WHERE email = 'a@example.test';

-- Nếu COUNT = 0 thì INSERT.
```

Hai transaction có thể cùng nhận 0 rồi cùng insert. Constraint:

```sql
ALTER TABLE users
ADD CONSTRAINT uq_users_email UNIQUE (email);
```

đưa quy tắc duy nhất về DBMS, nơi các lần ghi cạnh tranh được kiểm soát. Ứng dụng vẫn có thể truy vấn trước để hiển thị thông báo thuận tiện, nhưng phải xử lý lỗi unique violation khi insert/commit.

Không cần chọn `SERIALIZABLE` chỉ để bảo vệ một giá trị duy nhất nếu unique constraint đã diễn đạt chính xác bất biến.

### 4.2. Vì sao một câu UPDATE nguyên tử có thể đủ?

Câu lệnh:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :account_id
  AND balance >= :amount;
```

cho DBMS thực hiện kiểm tra điều kiện và thay đổi như một thao tác cập nhật. Khi nhiều transaction cùng tác động một hàng, DBMS điều phối xung đột ghi theo semantics của nó. Ứng dụng kiểm tra số hàng ảnh hưởng và đưa ra kết quả nghiệp vụ tương ứng.

Nếu nghiệp vụ còn phụ thuộc tổng của nhiều tài khoản, hạn mức chung hoặc trạng thái ở dịch vụ ngoài, câu lệnh đơn lẻ này chưa đủ. Phải mở rộng bất biến và phạm vi bảo vệ.

## 5. Đối chiếu theo bốn mức SQL

### 5.1. READ UNCOMMITTED: chấp nhận khả năng đọc dữ liệu chưa xác nhận

Có thể cân nhắc cho một số tác vụ phân tích tạm thời hoặc dữ liệu không nhạy cảm **nếu** DBMS thực sự triển khai dirty read và ứng dụng chấp nhận kết quả không xác định sau rollback. Trong nhiều hệ quản trị, mức này bị ánh xạ lên mức mạnh hơn hoặc có hành vi riêng.

Không phù hợp khi quyết định ảnh hưởng số dư, tồn kho, thanh toán, đặt chỗ hoặc trạng thái nghiệp vụ mà dữ liệu chưa commit có thể dẫn đến hành động sai.

### 5.2. READ COMMITTED: điểm cân bằng cho nhiều thao tác thông thường

READ COMMITTED ngăn đọc dữ liệu chưa commit, nhưng mỗi câu truy vấn có thể thấy một snapshot khác nhau. Nó thường phù hợp khi:

- Mỗi câu lệnh cần dữ liệu đã xác nhận tại thời điểm câu lệnh.
- Không yêu cầu nhiều truy vấn trong transaction cùng nhìn một snapshot.
- Bất biến ghi được bảo vệ bằng conditional update, constraint, khóa tường minh hoặc giao thức rõ.

Nó không tự ngăn non-repeatable read, phantom, write skew hoặc mọi lost update.

### 5.3. REPEATABLE READ / snapshot: nhiều truy vấn cần cùng góc nhìn

Có ích khi transaction đọc cùng hàng nhiều lần hoặc tạo báo cáo qua nhiều câu truy vấn dựa trên cùng snapshot. Tuy nhiên:

- Phantom được xử lý khác nhau giữa DBMS.
- Snapshot isolation có thể cho write skew.
- Snapshot có thể cũ khi transaction kéo dài.
- Ghi trên dữ liệu đã bị thay đổi có thể chờ hoặc nhận lỗi tùy DBMS.

Không chọn REPEATABLE READ chỉ vì tên nghe “an toàn hơn” mà chưa phân tích ràng buộc nhiều hàng.

### 5.4. SERIALIZABLE: khi bất biến phụ thuộc lịch nhiều giao dịch

Đây là mức cần cân nhắc khi một transaction đọc tập dữ liệu, ra quyết định rồi cập nhật và mọi lịch nguy hiểm phải tương đương một thứ tự tuần tự. Ví dụ điển hình là “ít nhất một người trực”, hạn mức tổng hoặc điều kiện tổng hợp nhiều hàng.

Chi phí có thể là chờ khóa, deadlock, serialization failure hoặc retry. Cần viết logic retry toàn bộ transaction có giới hạn; không retry vô hạn và không lặp tác dụng ngoài DB như thanh toán hoặc gửi email nếu không có idempotency/outbox.

## 6. Cùng tên isolation, hành vi giữa DBMS có thể khác

Ma trận anomaly là cơ sở lý thuyết; DBMS có thể bảo đảm mạnh hơn mức tối thiểu hoặc dùng cơ chế khác nhau.

| DBMS / chế độ phổ biến | Đặc điểm cần lưu ý |
|---|---|
| **PostgreSQL** | `READ UNCOMMITTED` được xử lý như `READ COMMITTED`. `READ COMMITTED` dùng snapshot theo câu lệnh; `REPEATABLE READ` dùng snapshot ổn định và ngăn phantom trong truy vấn thông thường nhưng vẫn có thể có write skew; `SERIALIZABLE` dùng Serializable Snapshot Isolation để phát hiện phụ thuộc nguy hiểm và có thể báo serialization failure. |
| **MySQL InnoDB** | Mặc định thường là `REPEATABLE READ` (cần xác minh cấu hình). Consistent reads dùng MVCC; locking reads và các range access có thể dùng record/gap/next-key locks. Hành vi cụ thể phụ thuộc câu SQL, index, engine và isolation level. |
| **SQL Server** | `READ COMMITTED` có thể dùng khóa hoặc row versioning khi bật `READ_COMMITTED_SNAPSHOT`. `SNAPSHOT` là một lựa chọn riêng; `SERIALIZABLE` dùng khóa phạm vi phù hợp. Cần phân biệt session/database options. |
| **Oracle Database** | `READ COMMITTED` là mặc định phổ biến với read consistency theo câu lệnh; `SERIALIZABLE` có snapshot transaction và có thể báo lỗi khi dữ liệu bị sửa đồng thời theo điều kiện của Oracle. |
| **SQLite** | Mô hình locking/journaling hoặc WAL và chế độ transaction có ảnh hưởng mạnh đến concurrency; không suy diễn trực tiếp từ hành vi PostgreSQL/InnoDB. |

Đừng chỉ so sánh tên. Khi vận hành, phải kiểm tra phiên bản DBMS, cấu hình, engine, autocommit, isolation đang thực sự áp dụng trên connection, và loại truy vấn là consistent read hay locking read.

### 6.1. Ví dụ PostgreSQL về READ COMMITTED và REPEATABLE READ

Giả sử T1 và T2 dùng hai connection. Ban đầu số dư `100`.

T1 ở READ COMMITTED:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance FROM accounts WHERE id = 1;
-- 100
```

T2:

```sql
BEGIN;
UPDATE accounts SET balance = 80 WHERE id = 1;
COMMIT;
```

T1 đọc lại:

```sql
SELECT balance FROM accounts WHERE id = 1;
-- Có thể thấy 80 trong PostgreSQL READ COMMITTED.
COMMIT;
```

Nếu đổi transaction T1 sang `REPEATABLE READ` và snapshot đã được thiết lập ở lần đọc đầu, T1 tiếp tục thấy `100` cho các consistent read trong transaction. Điều đó minh họa khác biệt về snapshot, không khẳng định T1 được phép ghi thành công trên mọi dữ liệu đã bị T2 sửa.

## 7. Chọn cơ chế bằng cây quyết định

Có thể sử dụng luồng suy luận sau khi đã nêu bất biến:

```text
Bắt đầu: Bất biến cần bảo vệ là gì?
       |
       v
Chỉ nằm trên một hàng?
       |
       +-- Có --> Có thể diễn đạt bằng CHECK/UNIQUE?
       |            |
       |            +-- Có --> Dùng constraint.
       |            |
       |            +-- Không --> Conditional UPDATE,
       |                         khóa hàng hoặc version check.
       |
       +-- Không --> Phụ thuộc nhiều hàng/predicate?
                    |
                    v
          Có thể mô hình hóa bằng constraint,
          một hàng điều phối hoặc khóa chung?
                    |
             +------+------+
             |             |
            Có            Không
             |             |
       Dùng constraint/    Xem xét SERIALIZABLE
       cơ chế điều phối    và xử lý retry
             |             |
             +------+------+
                    |
                    v
       Transaction có cần snapshot ổn định
       cho nhiều lần đọc/báo cáo không?
                    |
                    v
       Chọn snapshot/isolation theo DBMS,
       xác minh replica/cache nằm trong phạm vi nào
                    |
                    v
       Kiểm thử hai hoặc nhiều transaction
       và đo lock wait / abort / latency
```

Đây không phải thuật toán tự động chọn isolation. Nó là thứ tự câu hỏi để tránh dùng mức cô lập thay cho constraint, hoặc dùng constraint đơn hàng để giải quyết ràng buộc tổng hợp.

## 8. Ví dụ tổng hợp: đặt ghế và giữ sức chứa

Một chuyến có 100 ghế. Hệ thống cần bảo vệ:

1. Một ghế không được xác nhận cho hai booking.
2. Tổng số ghế đã xác nhận không vượt 100.
3. Cùng request checkout không tạo hai booking.
4. Trạng thái booking phải chuyển theo luồng hợp lệ.

### 8.1. Quy tắc theo khóa ghế

Nếu mỗi ghế có một hàng inventory riêng:

```sql
CREATE TABLE trip_seats (
    trip_id BIGINT NOT NULL,
    seat_no VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL,
    booking_id BIGINT,
    PRIMARY KEY (trip_id, seat_no)
);
```

Cập nhật có điều kiện:

```sql
UPDATE trip_seats
SET status = 'CONFIRMED',
    booking_id = :booking_id
WHERE trip_id = :trip_id
  AND seat_no = :seat_no
  AND status = 'AVAILABLE';
```

Chỉ một transaction được coi là thành công khi số hàng cập nhật là 1. Nếu hàng đã được giữ hoặc xác nhận, số hàng bằng 0; ứng dụng trả kết quả xung đột ghế.

### 8.2. Quy tắc tổng sức chứa

Nếu hệ thống chỉ dùng một hàng counter:

```sql
UPDATE trips
SET confirmed_count = confirmed_count + 1
WHERE trip_id = :trip_id
  AND confirmed_count < capacity;
```

Hàng trip trở thành tài nguyên điều phối; các transaction tăng counter cạnh tranh trên cùng hàng. Cập nhật và booking cần cùng transaction để nếu insert booking lỗi, counter cũng rollback. Constraint `CHECK (confirmed_count <= capacity)` bổ sung bảo vệ trạng thái hàng.

Nếu đếm `COUNT(*)` trên toàn bộ bookings rồi insert một hàng mới mà không khóa/phối hợp đúng, nhiều transaction có thể cùng thấy còn chỗ cuối cùng. Đây là loại vấn đề predicate/aggregate mà READ COMMITTED đơn thuần không tự giải quyết.

### 8.3. Idempotency của request

Unique key cho request:

```sql
CREATE TABLE booking_requests (
    request_key VARCHAR(100) PRIMARY KEY,
    booking_id BIGINT,
    status VARCHAR(20) NOT NULL
);
```

Cùng request key phải trả lại kết quả cũ hoặc trạng thái xử lý phù hợp, không tăng counter/giữ ghế thêm lần nữa. Đây là bảo vệ chống request trùng, không phải một tác dụng trực tiếp của isolation level.

### 8.4. Đặt ranh giới transaction

```text
BEGIN

1. Ghi nhận/kiểm tra idempotency key.
2. Chiếm hàng trip_seats bằng conditional UPDATE.
3. Tăng trips.confirmed_count nếu vẫn dưới capacity.
4. Tạo booking.
5. Ghi outbox event nếu cần gửi thông báo.

COMMIT

Ngoài transaction:
6. Publisher gửi event; consumer xử lý trùng an toàn.
```

Khi có lỗi ở bước 2, 3 hoặc 4, rollback toàn bộ phần DB. Khi có serialization/deadlock, có thể retry toàn bộ giao dịch; khi ghế đã bị chiếm, đây là kết quả nghiệp vụ, không retry mù quáng. Khi publish thông điệp lỗi, outbox giữ công việc để tiến trình khác thử lại.

## 9. Cách xây dựng bài kiểm thử dựa trên anomaly

Một bài kiểm thử tốt phải xác định **trạng thái ban đầu, lịch phối hợp, kết quả mong đợi và DBMS cụ thể**.

| Kiểm thử | Lịch cần tạo | Điều cần quan sát |
|---|---|---|
| Dirty read | A update chưa commit; B đọc | B có nhìn thấy giá trị chưa commit không? |
| Non-repeatable read | A đọc; B update+commit; A đọc lại | A có thấy giá trị khác không? |
| Phantom | A query predicate; B insert thỏa predicate+commit; A query lại | Tập kết quả thay đổi hay được bảo vệ? |
| Lost update | A và B cùng đọc một giá trị; cả hai ghi kết quả tính từ giá trị đó | Thay đổi có bị ghi đè, chờ hoặc một transaction bị hủy không? |
| Write skew | A và B đọc cùng điều kiện nhiều hàng; mỗi bên ghi một hàng khác | Cả hai có thể commit và phá bất biến không? |
| Capacity race | Nhiều session cùng giành chỗ cuối | Có vượt sức chứa hoặc tạo hai booking cho cùng ghế không? |

### 9.1. Dùng nhiều session thật

Mở ít nhất hai connection độc lập. Điều phối bằng các điểm dừng có chủ đích:

1. A bắt đầu và đọc dữ liệu.
2. Giữ A chưa commit.
3. B bắt đầu và chạy câu lệnh xung đột.
4. Quan sát B chờ, thành công hay báo lỗi.
5. Cho A commit/rollback.
6. Quan sát kết quả cuối từ connection mới.

Không chạy các câu lệnh nối tiếp trong một session rồi kết luận đã kiểm tra concurrency.

### 9.2. Ghi nhận lỗi như kết quả của isolation

Ở mức serializable, một transaction bị hủy có thể là kết quả đúng theo hợp đồng. Test không nên chỉ coi “tất cả đều commit” là thành công. Cần xác định:

- Transaction nào dự kiến thành công.
- Transaction nào có thể nhận serialization failure/deadlock.
- Khi retry, kết quả cuối cùng phải giữ bất biến nào.
- Retry có lặp tác dụng phụ ngoài DB hay không.
- Số lần thử tối đa và kết quả khi hết retry.

### 9.3. Kiểm tra cả trạng thái cuối và lịch sự kiện

Một giá trị cuối đúng chưa chứng minh mọi lịch đều đúng. Ví dụ tồn kho vẫn bằng 0 nhưng hai đơn đã bán cùng một sản phẩm cuối. Kiểm thử cần đối chiếu số order, số ghế, ledger, request key và event, không chỉ một cột counter.

## 10. Những sai lầm khi chọn mức cô lập

| Cách chọn sai | Vấn đề | Điều chỉnh |
|---|---|---|
| Chọn SERIALIZABLE cho tất cả mà không đo | Có thể tăng chờ hoặc tỷ lệ retry không cần thiết | Bắt đầu từ bất biến, constraint và lịch xung đột thực tế |
| Dùng READ COMMITTED vì đó là default | Có thể bỏ lọt non-repeatable/phantom/write skew cần ngăn | Viết test cho những anomaly liên quan tới nghiệp vụ |
| Dùng REPEATABLE READ để xử lý mọi write skew | Snapshot ổn định không nhất thiết serializable | Bảo vệ điều kiện nhiều hàng bằng SERIALIZABLE hoặc cơ chế phối hợp |
| Chỉ dùng SELECT kiểm tra tồn tại rồi INSERT | Có race giữa kiểm tra và insert | Unique constraint và xử lý lỗi vi phạm |
| Chỉ khóa từng hàng đang đọc | Không nhất thiết bảo vệ predicate hoặc hàng sẽ được thêm | Range/predicate lock hoặc tài nguyên điều phối |
| Chỉ xem isolation của primary | Replica/cache có thể trả dữ liệu cũ | Đặc tả consistency cho từng endpoint |
| Retry một câu lệnh thay vì cả transaction | Các quyết định dựa trên snapshot cũ còn nguyên | Rollback và chạy lại toàn bộ logic khi lỗi serialization |
| Coi lỗi conflict là lỗi hệ thống bất thường | Xung đột là điều được dự kiến trong concurrency control | Phân loại business conflict, retryable conflict và lỗi vận hành |

## 11. Checklist diễn đạt quyết định isolation trong thiết kế

Một tài liệu kỹ thuật hoặc code review nên trả lời rõ:

1. **Bất biến:** điều kiện nào phải đúng, ở phạm vi hàng, predicate hay nhiều dịch vụ?
2. **Tác nhân đồng thời:** những API, job, consumer hoặc người dùng nào có thể cùng thay đổi dữ liệu?
3. **Anomaly cần loại bỏ:** dirty read, non-repeatable read, phantom, lost update, write skew hay serialization anomaly nào có thể phá bất biến?
4. **Cơ chế chính:** constraint, conditional update, unique key, khóa pessimistic, version optimistic, snapshot hay serializable?
5. **Isolation thực tế:** DBMS/phiên bản nào, isolation nào đang áp dụng cho connection và transaction?
6. **Phạm vi đọc:** primary, replica, cache và endpoint stale-read có cùng cam kết hay không?
7. **Hành vi lỗi:** block, timeout, deadlock, serialization failure và business conflict được phân loại thế nào?
8. **Retry:** toàn bộ transaction có thể chạy lại an toàn không, có idempotency cho tác dụng phụ không?
9. **Kiểm thử:** lịch đồng thời nào chứng minh bất biến vẫn đúng? Test có quan sát nhiều bảng/tác dụng liên quan không?
10. **Vận hành:** theo dõi lock wait, deadlock, tỷ lệ serialization failure, thời gian transaction và số lần retry ra sao?

Nếu chưa thể trả lời câu hỏi về anomaly, chưa nên kết luận mức isolation đã đủ.

## 12. Ghi nhớ

**Chọn isolation theo bất biến trước, theo anomaly sau, và theo semantics DBMS cuối cùng.** Dirty read thường được loại bỏ bằng READ COMMITTED trở lên; nhu cầu đọc lặp lại hoặc snapshot ổn định dẫn tới REPEATABLE READ/Snapshot phù hợp; điều kiện nhiều hàng có nguy cơ write skew hoặc predicate race có thể cần SERIALIZABLE, khóa chung hoặc constraint được thiết kế đúng. Các quy tắc trên một hàng thường được bảo vệ hiệu quả bằng CHECK, UNIQUE và cập nhật có điều kiện.

Không có một ma trận anomaly chung thay thế được phân tích nghiệp vụ. Hãy xây dựng lịch phản ví dụ cho từng bất biến, chọn cơ chế đủ mạnh trong phạm vi transaction thực tế, rồi kiểm chứng bằng nhiều connection trên đúng DBMS và cấu hình sẽ vận hành.
