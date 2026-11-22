# Serialization failure và thử lại toàn bộ giao dịch trong PostgreSQL

Hai người cùng đặt hàng, hai tiến trình cùng cập nhật hạn mức hoặc hai quản trị viên đồng thời thay đổi lịch trực: mỗi giao dịch riêng lẻ có thể “nhìn thấy dữ liệu hợp lệ”, nhưng **kết quả khi chạy đồng thời** lại vi phạm một quy tắc kinh doanh. PostgreSQL có các mức cô lập giao dịch để kiểm soát hiện tượng này. Ở mức `SERIALIZABLE`, hệ quản trị cố gắng bảo đảm kết quả của các giao dịch đã commit tương đương với **một thứ tự thực thi tuần tự hợp lệ**. Nếu không thể bảo đảm điều đó, PostgreSQL có thể **hủy một giao dịch** bằng lỗi:

```text
SQLSTATE 40001 — serialization_failure
ERROR: could not serialize access due to ...
```

Đây không nhất thiết là sự cố database. Nó thường là **cơ chế bảo vệ dữ liệu đúng như thiết kế** khi các giao dịch thực sự cạnh tranh. Nhưng nếu ứng dụng chỉ bắt lỗi rồi thử chạy lại đúng câu `UPDATE`/`INSERT` cuối cùng, ứng dụng vẫn có thể dùng **quyết định được tính từ snapshot cũ** và tạo kết quả sai.

Vì vậy, quy tắc trung tâm của bài là:

> **Gặp `serialization_failure`, hãy `ROLLBACK` giao dịch đã thất bại, bắt đầu một giao dịch mới, rồi thực hiện lại toàn bộ công việc có thể ảnh hưởng đến quyết định ghi: các câu đọc, tính toán, kiểm tra điều kiện và thao tác ghi, kể cả `COMMIT`.**

Bài thuộc chương **Giao dịch** trong module *Database Engine Relational PostgreSQL*. Bạn sẽ học:

- Vì sao PostgreSQL cần báo `40001` và liên hệ với MVCC, `REPEATABLE READ`, `SERIALIZABLE` và Serializable Snapshot Isolation (SSI).
- Thử nghiệm **write skew** trên hai cửa sổ `psql`: hai giao dịch đều thấy “còn đủ bác sĩ trực” nhưng cùng thay đổi những hàng khác nhau.
- Phân biệt lỗi `40001` với deadlock `40P01`, lỗi khóa, lỗi ràng buộc và transaction đã bị đánh dấu thất bại.
- Thiết kế **transaction retry boundary** đúng: làm lại từ lúc đọc dữ liệu, xử lý được cả lỗi ở `COMMIT`, giới hạn số lần và giãn cách có jitter.
- Mẫu Java/JDBC tự chứa sử dụng `DataSource`, `Connection`, `PreparedStatement`, `SQLState`, `rollback` và `commit`.
- Những vấn đề ứng dụng cần giải quyết thêm: idempotency, HTTP/payment/email side effect, transactional outbox, kết quả `COMMIT` không rõ do mất kết nối, timeout, giám sát và kiểm thử đồng thời.

> **Mức phiên bản:** Các ví dụ dùng những tính năng giao dịch và SSI của PostgreSQL hiện đại. Serializable Snapshot Isolation đã được PostgreSQL sử dụng từ phiên bản 9.1. Các ví dụ sử dụng SQL chuẩn của PostgreSQL và Java 17+; không yêu cầu extension. Hãy thử trên một database thực hành, không sửa dữ liệu sản xuất.

---

## 1. Khái niệm: “Serializable” muốn bảo đảm điều gì?

### 1.1. Giao dịch và tính đúng đắn

Một **transaction** gom nhiều bước thành một đơn vị:

```sql
BEGIN;

-- Đọc dữ liệu để quyết định.
SELECT ...;

-- Thay đổi dữ liệu dựa trên quyết định.
UPDATE ...;

COMMIT;
```

Nếu có lỗi:

```sql
ROLLBACK;
```

`COMMIT` xác nhận những thay đổi của transaction thành công; `ROLLBACK` hủy những thay đổi chưa commit của transaction. Trên thực tế, các ranh giới transaction còn điều khiển snapshot, lock, tính hiển thị và các hành vi đồng thời.

### 1.2. Tính serializable không có nghĩa “mọi transaction chạy lần lượt”

**Serializable** là một cam kết về **kết quả tương đương**: các giao dịch được phép thực thi chồng lấn, nhưng kết quả commit phải có thể được giải thích như thể những transaction đó đã chạy theo một thứ tự nối tiếp nào đó.

Không phải mọi transaction bắt đầu trước đều phải commit trước. Không có yêu cầu PostgreSQL khóa toàn bộ database và cho một giao dịch chạy một mình.

Nếu hai giao dịch tranh chấp và không thể cùng nằm trong một lịch chạy tuần tự hợp lệ, PostgreSQL có thể **cho một giao dịch thành công, buộc giao dịch kia thất bại**, sau đó ứng dụng phải quyết định có retry hay không.

### 1.3. Ví dụ quy tắc “luôn còn ít nhất một người trực”

Giả sử có hai bác sĩ An và Bình, cả hai đang trực:

```text
doctor_id | on_duty
----------+--------
1         | true
2         | true
```

Quy tắc: một bác sĩ chỉ được rời ca nếu **vẫn còn ít nhất một người khác đang trực**.

Giao dịch A định cho An nghỉ:

1. Đếm số bác sĩ đang trực → 2.
2. Thấy đủ điều kiện để một người nghỉ.
3. Đặt `on_duty=false` cho bác sĩ An.

Giao dịch B định cho Bình nghỉ:

1. Đếm số bác sĩ đang trực → 2.
2. Thấy đủ điều kiện để một người nghỉ.
3. Đặt `on_duty=false` cho bác sĩ Bình.

Nếu hai giao dịch dùng các snapshot đồng thời, chúng có thể đều thấy **2 người trực** và sửa **hai hàng khác nhau**. Cuối cùng không còn ai trực: **đây là lỗi nghiệp vụ dù không có hai transaction cùng sửa một hàng**.

Hiện tượng này gọi là **write skew**. Serializable isolation được thiết kế để loại bỏ lịch commit có kết quả không tương đương với bất kỳ cách thực thi tuần tự hợp lệ nào.

---

## 2. Các mức cô lập giao dịch liên quan

PostgreSQL hỗ trợ mức cô lập được khai báo theo SQL, nhưng mỗi mức có những quy tắc thực tế riêng.

| Isolation level | Bức tranh tổng quan ở PostgreSQL | Điểm cần nhớ |
|---|---|---|
| `READ COMMITTED` | Mỗi statement thường đọc snapshot mới | Mặc định; đọc rồi quyết định qua nhiều statement có thể thấy dữ liệu thay đổi |
| `READ UNCOMMITTED` | PostgreSQL xử lý về cơ bản như `READ COMMITTED` | Không có dirty read như một số hệ khác |
| `REPEATABLE READ` | Snapshot ổn định trong transaction; triển khai snapshot isolation | Tránh nhiều bất thường, nhưng **write skew** vẫn có thể xảy ra |
| `SERIALIZABLE` | Serializable Snapshot Isolation (SSI) | Ngăn kết quả commit không serializable, có thể phát sinh `40001` |

**Không hiểu nhầm:** `REPEATABLE READ` của PostgreSQL mạnh ở khía cạnh snapshot ổn định, nhưng không đồng nghĩa mọi bất biến nghiệp vụ dựa vào **nhiều hàng** đều được giữ nếu hai transaction cùng ghi những hàng khác nhau.

### 2.1. READ COMMITTED

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT ...;
UPDATE ...;
COMMIT;
```

Ở mức này, một câu `SELECT` và câu `UPDATE` chạy sau có thể dựa trên **những snapshot khác nhau**. Trong nhiều nghiệp vụ CRUD đơn giản, đây là mức phù hợp; khi cần bảo vệ bất biến nhiều hàng, phải thiết kế thêm điều kiện, row locks hoặc mức cô lập phù hợp.

### 2.2. REPEATABLE READ

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SELECT ...;
UPDATE ...;
COMMIT;
```

Các câu lệnh trong transaction thường dùng một snapshot nhất quán được thiết lập theo quy tắc của mức này. Tuy nhiên, **hai giao dịch có thể đọc cùng một trạng thái rồi ghi các hàng khác nhau**, tạo write skew.

PostgreSQL cũng có thể phát sinh **`40001` ở `REPEATABLE READ`**, chẳng hạn khi transaction cố cập nhật hàng đã bị transaction đồng thời thay đổi sau snapshot của nó. Vì thế không được hiểu `40001` chỉ xảy ra ở `SERIALIZABLE`.

### 2.3. SERIALIZABLE

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SELECT ...;
UPDATE ...;
COMMIT;
```

Ở mức này, PostgreSQL theo dõi những phụ thuộc đọc–ghi nguy hiểm giữa các transaction. Nếu có nguy cơ tạo một lịch commit không thể tuần tự hóa, hệ quản trị chọn một giao dịch làm **serialization victim** để báo lỗi.

Hệ quả quan trọng: ứng dụng **phải được thiết kế để nhận và retry `40001`**. Không nên triển khai `SERIALIZABLE` rồi giả định mọi transaction sẽ luôn commit.

### 2.4. Chọn isolation level theo yêu cầu

Không phải tất cả thao tác đều cần `SERIALIZABLE`. Nhiều bài toán có thể bảo vệ ràng buộc bằng:

- `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`.
- Một câu lệnh `UPDATE ... WHERE balance >= amount` nguyên tử.
- `SELECT ... FOR UPDATE` trên những hàng cần khóa.
- Exclusion constraint cho những phạm vi chồng lấn.
- Serializing một tài nguyên nghiệp vụ bằng khóa phù hợp.

Nhưng khi quy tắc phụ thuộc vào **tập hàng hay điều kiện tìm kiếm**, SSI ở `SERIALIZABLE` là một lựa chọn mạnh. Hãy cân nhắc tính đúng đắn, mức tranh chấp, thời gian transaction và khả năng retry của ứng dụng.

---

## 3. MVCC và Serializable Snapshot Isolation (SSI)

### 3.1. MVCC giúp đọc và ghi cùng tồn tại

PostgreSQL dùng **Multi-Version Concurrency Control (MVCC)**. Tùy snapshot, một transaction có thể đọc phiên bản hàng được xem là hợp lệ với nó trong khi một transaction khác đang tạo phiên bản mới.

MVCC cải thiện khả năng đồng thời, nhưng tự nó không chứng minh các quyết định **đọc nhiều hàng rồi ghi** sẽ luôn tương đương tuần tự.

### 3.2. SSI phát hiện phụ thuộc nguy hiểm

SSI theo dõi quan hệ đọc–ghi giữa các giao dịch. Một tình huống nguy hiểm có thể có dạng:

```text
Transaction A đọc tập dữ liệu X
                \
                 \   transaction B sửa dữ liệu mà A đã dựa vào
                  \
Transaction B đọc tập dữ liệu Y
                \
                 \   transaction A sửa dữ liệu mà B đã dựa vào
                  \
      Hai quyết định không thể cùng hợp lệ
      trong một lịch thực thi tuần tự
```

SSI cần phát hiện **các mẫu phụ thuộc có thể dẫn tới bất thường**; nó không nhất thiết khóa mọi hàng đọc rồi chờ. PostgreSQL sử dụng cơ chế predicate/SIREAD locking để ghi nhận phụ thuộc đọc khi cần.

### 3.3. SIREAD không giống FOR UPDATE

Một số loại khóa có thể quan sát trong `pg_locks` với mode `SIReadLock`:

- Chúng phục vụ việc **theo dõi phụ thuộc** của SSI.
- Không nên hiểu đó là row lock thông thường buộc mọi writer chờ như `SELECT FOR UPDATE`.
- Việc PostgreSQL chọn độ hạt theo tuple/page/relation phụ thuộc kế hoạch, tài nguyên và hoạt động nội bộ.
- Điều chỉnh bộ nhớ hoặc kế hoạch truy vấn có thể ảnh hưởng mức độ xung đột được phát hiện, kể cả các false positive có thể dẫn tới abort hợp lệ.

**SSI không hứa mọi transaction chỉ được đọc dữ liệu luôn mới nhất**. Nó hứa những transaction đã commit tạo một kết quả có thể tuần tự hóa. Transaction bị từ chối có thể cần đọc **snapshot mới** khi retry.

### 3.4. Serialization failure không phải deadlock

Deadlock thường là hai hoặc nhiều transaction **chờ khóa lẫn nhau**, không tiến lên được. Serialization failure do SSI là một cơ chế **bảo đảm lịch commit đúng**, có thể xảy ra dù không có deadlock kiểu chờ khóa.

Hai tình huống có SQLSTATE khác nhau:

```text
40001  serialization_failure
40P01  deadlock_detected
```

Chúng thường đều có thể **được xem xét để retry toàn bộ transaction**, nhưng nguyên nhân và chiến lược giảm xung đột không hoàn toàn giống nhau.

---

## 4. Tạo dữ liệu lab về lịch trực bác sĩ

Ta xây một schema nhỏ, chỉ để thử nghiệm hai giao dịch đồng thời.

### 4.1. Tạo bảng

```sql
CREATE SCHEMA IF NOT EXISTS tx_retry_lab;

CREATE TABLE tx_retry_lab.on_call (
    doctor_id INTEGER PRIMARY KEY,
    doctor_name TEXT NOT NULL,
    on_duty BOOLEAN NOT NULL
);
```

Thêm hai bác sĩ:

```sql
INSERT INTO tx_retry_lab.on_call
    (doctor_id, doctor_name, on_duty)
VALUES
    (1, 'An', TRUE),
    (2, 'Bình', TRUE)
ON CONFLICT (doctor_id) DO UPDATE
SET doctor_name = EXCLUDED.doctor_name,
    on_duty = EXCLUDED.on_duty;
```

Việc `ON CONFLICT` ở đây chỉ giúp bạn chạy lại phần nạp dữ liệu nếu đã tạo bảng trước; nó **không** thay thế cơ chế serialization và retry ở phần giao dịch.

### 4.2. Xác nhận trạng thái ban đầu

```sql
SELECT doctor_id, doctor_name, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS on_duty_count
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Kết quả mong đợi:

```text
doctor_id | doctor_name | on_duty
----------+-------------+--------
1         | An          | true
2         | Bình        | true

on_duty_count = 2
```

### 4.3. Quy tắc nghiệp vụ

Một bác sĩ đang trực chỉ được chuyển sang **không trực** khi **còn ít nhất hai người đang trực trước khi chuyển**. Sau khi một người nghỉ, còn lại ít nhất một người.

Logic ứng dụng khái quát:

```text
begin transaction
read number of on-duty doctors
if number < 2:
    do not update; finish transaction
else:
    update chosen doctor to off-duty
commit transaction
```

Một `CHECK (on_duty IN (true,false))` không bảo vệ được quy tắc **trên cả tập hàng**. Đây là bất biến cần phối hợp nhiều row.

### 4.4. Chuẩn bị hai phiên psql độc lập

Mở **hai cửa sổ kết nối PostgreSQL** cùng database:

```text
Terminal A / Session A     Terminal B / Session B
----------------------     ----------------------
psql database_lab          psql database_lab
```

Bạn có thể dùng tên database của môi trường lab thay vì `database_lab`. Hai phiên phải thực sự là **hai connection khác nhau**; chạy hai khối tuần tự trong một session không tạo được xung đột đồng thời.

Không chạy lệnh reset dữ liệu giữa lúc một trong hai session vẫn còn transaction thử nghiệm.

---

## 5. Thử nghiệm write skew dưới REPEATABLE READ

Phần này minh họa **vì sao snapshot ổn định chưa đủ để bảo vệ quy tắc tập hàng**.

### 5.1. Reset trước thử nghiệm

Trong một phiên khác hoặc khi cả hai phiên A/B đều không ở transaction:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE;
```

Sau đó chạy các bước **đúng trình tự xen kẽ**.

### 5.2. Session A: bắt đầu và đọc

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Session A nhìn thấy `count_before = 2`. **Chưa UPDATE và chưa COMMIT**.

### 5.3. Session B: bắt đầu và đọc cùng trạng thái

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Session B cũng nhìn thấy `count_before = 2`. Hai transaction đã có snapshot trước khi bất kỳ bên nào commit thay đổi.

### 5.4. Session A: cho An nghỉ

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1
  AND on_duty = TRUE;
```

Đã cập nhật một hàng, nhưng transaction A **chưa commit**.

### 5.5. Session B: cho Bình nghỉ

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

Đã cập nhật một hàng khác. Vì A và B sửa **những doctor_id khác nhau**, không có row write conflict trực tiếp trên cùng hàng ở ví dụ này.

### 5.6. Session A và Session B lần lượt COMMIT

Session A:

```sql
COMMIT;
```

Session B:

```sql
COMMIT;
```

Trong lịch thực thi mô tả ở `REPEATABLE READ`, cả hai transaction có thể commit thành công vì chúng không cập nhật cùng một row. Xem lại từ transaction mới:

```sql
SELECT doctor_id, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Kết quả có thể là:

```text
doctor_id | on_duty
----------+--------
1         | false
2         | false

remaining = 0
```

**Quy tắc nghiệp vụ đã bị vi phạm**: cả hai bác sĩ đều nghỉ, dù khi từng người đọc dữ liệu thì đều thấy hai người đang trực.

### 5.7. Tại sao đây không phải một thứ tự tuần tự hợp lệ?

Nếu A chạy **trọn vẹn rồi B mới bắt đầu**:

1. A thấy 2 người, cho An nghỉ.
2. B chỉ còn thấy 1 người, **không được** cho Bình nghỉ.

Nếu B chạy trọn vẹn trước A cũng tương tự. Không có lịch tuần tự hợp lệ nào khiến **cả hai** cùng vượt qua điều kiện và nghỉ. Kết quả `remaining=0` là bất thường write skew.

**Kết luận:** `REPEATABLE READ` không tự đảm bảo những bất biến đa hàng dựa trên kết quả `SELECT COUNT(*)`.

---

## 6. Lặp lại cùng thí nghiệm dưới SERIALIZABLE

### 6.1. Reset dữ liệu và đóng transaction cũ

Đảm bảo phiên A và B đã `COMMIT`/`ROLLBACK` kết thúc thử nghiệm trước. Reset:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE;
```

### 6.2. Session A: mở transaction SERIALIZABLE, đếm

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Kết quả `2`. **Giữ session A chưa commit**.

### 6.3. Session B: mở transaction SERIALIZABLE, đếm

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_before
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Kết quả `2`. Cả hai giao dịch đã đọc cùng quy tắc trước khi ghi.

### 6.4. Session A và B cập nhật hai hàng khác nhau

Session A:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1
  AND on_duty = TRUE;
```

Session B:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

Sau đó thử `COMMIT` trên mỗi session:

```sql
COMMIT;
```

### 6.5. Kết quả có thể quan sát

Ở `SERIALIZABLE`, PostgreSQL **không cho phép cả hai transaction cùng commit** với trạng thái cuối cùng không còn người trực.

Thông thường một giao dịch thành công và một giao dịch sẽ nhận:

```text
ERROR: could not serialize access due to
       read/write dependencies among transactions
SQLSTATE: 40001
```

**Không dự đoán trước giao dịch A hay B là bên thất bại.** Cũng không mặc định lỗi chỉ xuất hiện ở `COMMIT`: tùy lịch xen kẽ và loại xung đột, `40001` có thể được phát hiện khi một statement đang thực thi hoặc tại thời điểm commit.

Trong `psql`, thông báo có thể khác theo phiên bản/ngữ cảnh; **`SQLSTATE 40001` mới là dấu hiệu chương trình nên dùng**, không phải một câu lỗi tiếng Anh cố định.

### 6.6. Vì sao phải retry toàn bộ?

Giả sử A đã commit thành công, B bị từ chối. B không thể lấy con số **2** từ snapshot cũ rồi chỉ chạy lại:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2;
```

Nếu làm vậy ngoài giao dịch đã thất bại, B sẽ cho người còn lại nghỉ mà **không kiểm tra lại quy tắc**, tái tạo lỗi đã được SSI ngăn chặn.

Điều đúng là bắt đầu **giao dịch B hoàn toàn mới**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS count_now
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Lúc này, nếu A đã cho An nghỉ, B sẽ nhìn thấy **`count_now = 1`**, quyết định **không UPDATE Bình**, rồi:

```sql
COMMIT;
```

Kết quả cuối cùng vẫn còn một bác sĩ trực.

### 6.7. ROLLBACK sau lỗi

Khi statement trong transaction bị lỗi `40001`, transaction thường chuyển sang trạng thái không thể tiếp tục bình thường. Cần `ROLLBACK` trước khi thực hiện giao dịch mới. Nếu lỗi xảy ra **ở `COMMIT`**, transaction thất bại đã không commit; client vẫn phải dọn sạch trạng thái và mở transaction mới thay vì cố thực thi tiếp logic từ lần cũ.

Trong ứng dụng, nên thực hiện rollback một cách an toàn, đóng/trả connection và retry qua **transaction boundary** rõ ràng.

---

## 7. SQLSTATE 40001: nhận diện lỗi bằng mã, không bằng thông báo

PostgreSQL gửi **SQLSTATE** gồm năm ký tự để định danh loại lỗi. `40001` là **serialization_failure**.

### 7.1. Hai thông báo thường gặp

Ví dụ một số ngữ cảnh:

```text
ERROR: could not serialize access due to concurrent update
```

```text
ERROR: could not serialize access due to read/write dependencies
       among transactions
```

Cùng một mã `40001` có thể có **message/detail/hint khác nhau**. Không viết logic Java:

```java
// Không nên dùng:
// if (e.getMessage().contains("could not serialize")) { ... }
```

Vì message có thể thay đổi theo phiên bản hoặc ngôn ngữ. Thay vào đó:

```java
if ("40001".equals(e.getSQLState())) {
    // Retry toàn bộ giao dịch theo chính sách.
}
```

### 7.2. Xem SQLSTATE trong psql

Trong phiên `psql` tương tác, sau khi có lỗi:

```text
\errverbose
```

Lệnh meta của `psql` hiển thị thêm thông tin lỗi gần nhất, bao gồm SQLSTATE. Khi cần định dạng lỗi chi tiết hơn, có thể cấu hình `VERBOSITY verbose` trong phiên `psql`.

**Lưu ý:** `\errverbose` là lệnh của client `psql`, không phải câu SQL để gửi qua JDBC.

### 7.3. Khi transaction đã bị abort: SQLSTATE 25P02

Giả sử một statement thất bại nhưng ứng dụng tiếp tục gửi câu khác trong cùng transaction:

```text
ERROR: current transaction is aborted,
       commands ignored until end of transaction block
SQLSTATE: 25P02
```

Lỗi `25P02` báo rằng **transaction hiện tại đã thất bại**, không phải nguyên nhân gốc. Hãy tìm SQLSTATE **của lỗi đầu tiên** trước đó, thực hiện `ROLLBACK`, rồi xem có thể retry toàn bộ hay không.

### 7.4. Không tự coi mọi lỗi là serialization failure

| SQLSTATE | Tên thường gặp | Hướng xử lý |
|---|---|---|
| **`40001`** | `serialization_failure` | Thường retry **toàn bộ transaction** |
| **`40P01`** | `deadlock_detected` | Thường cũng có thể retry toàn bộ transaction với backoff |
| `23505` | `unique_violation` | Xem lại tính đúng đắn của khóa/idempotency; **không retry mù quáng** |
| `23P01` | `exclusion_violation` | Xem ràng buộc nghiệp vụ, ví dụ lịch chồng; không mặc định retry |
| `23503` | `foreign_key_violation` | Kiểm tra quan hệ dữ liệu, không mặc định retry |
| `55P03` | `lock_not_available` | Quyết định tùy chính sách lock_timeout/NOWAIT và yêu cầu thao tác |
| `57014` | `query_canceled` | Có thể do timeout/hủy; cần xác định nguyên nhân |
| `25P02` | `in_failed_sql_transaction` | Rollback; tìm lỗi gốc trước |
| Nhóm `08xxx` | Lỗi connection | Kết quả transaction, đặc biệt sau gửi COMMIT, có thể không rõ |

**Chỉ bật retry chung theo một whitelist có chủ đích**, ví dụ `40001` và có thể `40P01`. Những tình huống riêng của `23505`/`23P01` đôi khi phát sinh từ kiểm tra khóa dựa trên snapshot dưới `SERIALIZABLE`, nhưng việc retry chúng chỉ hợp lý nếu ứng dụng chứng minh được mối liên hệ với tranh chấp tạm thời và vẫn xử lý đúng ràng buộc. Không “bắt mọi SQLException rồi thử lại”.

---

## 8. Quy tắc vàng: retry *toàn bộ* giao dịch

### 8.1. Transaction boundary phải bao trùm quyết định

Sai:

```text
SELECT COUNT(*) -> thấy 2

BEGIN
  UPDATE doctor 2 -> lỗi 40001
ROLLBACK

BEGIN
  UPDATE doctor 2 -> retry riêng UPDATE
COMMIT
```

Ở phiên retry, ứng dụng không tính lại điều kiện “còn ít nhất một người trực”. Đây là lỗi logic, dù SQL mới không gặp `40001`.

Đúng:

```text
attempt 1:
    BEGIN SERIALIZABLE
    SELECT COUNT(*)              <-- đọc
    kiểm tra điều kiện            <-- quyết định
    UPDATE                       <-- ghi
    COMMIT                       <-- có thể lỗi 40001

nếu 40001:
    ROLLBACK/dọn transaction
    backoff

attempt 2:
    BEGIN SERIALIZABLE MỚI
    SELECT COUNT(*) LẠI           <-- snapshot mới
    tính lại quyết định
    UPDATE nếu còn hợp lệ
    COMMIT
```

Phần cần retry là **business transaction**, không phải một câu SQL cuối cùng.

### 8.2. Những bước nào phải được làm lại?

Thông thường:

1. Bắt đầu một transaction mới và đặt isolation phù hợp.
2. Đọc toàn bộ dữ liệu quyết định kết quả của transaction.
3. Tính lại các điều kiện nghiệp vụ.
4. Tạo các row/change dựa trên dữ liệu mới.
5. Chạy toàn bộ câu lệnh ghi trong phạm vi đó.
6. Thực hiện `COMMIT` và chỉ coi hoàn tất khi kết quả commit đã xác định thành công.

Nếu quyết định có phụ thuộc **cấu hình bên ngoài** hoặc **trạng thái dịch vụ khác**, cần một hợp đồng nhất quán riêng cho nguồn đó: PostgreSQL không thể bảo đảm serializability của toàn bộ hệ thống phân tán chỉ bằng cách cô lập transaction trong database.

### 8.3. Vì sao một retry thường tạo ra kết quả *khác*?

Điều đó hoàn toàn bình thường. Trong lab bác sĩ:

```text
Attempt 1 của B:
  Đếm 2 -> định cho Bình nghỉ -> 40001

Attempt 2 của B:
  Đếm 1 -> không cho Bình nghỉ -> COMMIT thành công
```

Ý nghĩa của retry **không phải** ép cùng câu trả lời cũ thành công, mà là **đánh giá lại nghiệp vụ trên dữ liệu mới**. Có trường hợp retry thành công với quyết định “không cập nhật”, “đã hết hàng”, “không còn đủ hạn mức”.

### 8.4. SAVEPOINT không thay thế transaction mới

PostgreSQL hỗ trợ `SAVEPOINT` và `ROLLBACK TO SAVEPOINT`, nhưng điều đó không tạo một transaction outer mới với snapshot mới để xử lý lại toàn bộ các phụ thuộc SSI.

Nếu lỗi serialization đã chỉ ra transaction **không thể commit an toàn theo cách hiện tại**, đừng chỉ rollback một statement/nhánh rồi tiếp tục với dữ liệu đã đọc trước đó. Khi `COMMIT` thất bại, không còn lựa chọn “khôi phục savepoint để tiếp tục” trong transaction đã bị từ chối.

**Chiến lược chuẩn:** làm lại toàn bộ transaction tại boundary của ứng dụng.

### 8.5. Mọi lần retry đều là một transaction mới

Không thực hiện:

```sql
-- Không đúng sau một serialization failure:
-- UPDATE ...
-- UPDATE ... (thử lại trong transaction đã bị abort)
```

Trong ứng dụng dùng connection pool, nên xem mỗi attempt là một transaction độc lập, trạng thái connection không bị rò rỉ từ attempt trước (autocommit, isolation, session variables, temporary objects, advisory locks...).

---

## 9. Quy trình retry có giới hạn và backoff

Một ứng dụng production cần chính sách rõ thay vì `while(true)`:

```text
                  +-----------------------+
                  | Bắt đầu attempt mới  |
                  +-----------+-----------+
                              |
                              v
                  BEGIN SERIALIZABLE
                              |
                              v
                   Đọc + kiểm tra nghiệp vụ
                              |
                              v
                        Ghi dữ liệu
                              |
                              v
                           COMMIT
                              |
                 +------------+-------------+
                 |                          |
             Thành công                Lỗi SQLSTATE
                 |                          |
                 v                          v
            Trả kết quả                ROLLBACK / cleanup
                                            |
                                +-----------+------------+
                                |                        |
                     40001 (hoặc 40P01)             Lỗi khác
                                |                        |
                         Còn attempts?                 Báo lỗi
                             /     \
                           Có      Không
                           |         |
                     backoff+jitter   Báo đã hết retry
                           |
                           +------> attempt mới
```

### 9.1. Vì sao không retry ngay không giới hạn?

Nếu hàng trăm client cùng cạnh tranh cùng tài nguyên và đều lập tức retry:

- Chúng có thể đụng nhau nhiều lần.
- Tăng CPU, lock/WAL và kết nối.
- Kéo dài độ trễ của các giao dịch vốn có thể thành công.
- Tạo **retry storm**, làm tình trạng xấu hơn.

Backoff giảm nhịp retry, còn **jitter** (khoảng đợi ngẫu nhiên) giúp các client không đồng loạt thử lại ở cùng một thời điểm.

### 9.2. Exponential backoff với jitter

Một chính sách minh họa:

```text
maxAttempts = 5
baseDelay   = 25 ms
maxDelay    = 400 ms

Sau attempt 1 bị lỗi -> chờ ngẫu nhiên 0..25 ms
Sau attempt 2 bị lỗi -> chờ ngẫu nhiên 0..50 ms
Sau attempt 3 bị lỗi -> chờ ngẫu nhiên 0..100 ms
Sau attempt 4 bị lỗi -> chờ ngẫu nhiên 0..200 ms
Sau attempt 5 -> không retry nữa
```

Những con số này **chỉ là ví dụ**. Cần cân nhắc SLA, thời gian phản hồi API, tỷ lệ tranh chấp, chi phí giao dịch và timeout từ client. Không hứa “5 lần là chắc chắn thành công”.

### 9.3. Đừng giữ connection trong lúc backoff

Nếu đang dùng connection pool, nên:

1. Rollback attempt thất bại.
2. Đóng/trả connection về pool theo chính sách.
3. Chờ backoff **ngoài transaction và ngoài connection**.
4. Lấy connection cho attempt tiếp theo.

Giữ connection đang mở hoặc còn transaction/lock trong lúc ngủ tạo tải không cần thiết.

### 9.4. Cần ngưỡng thời gian tổng

Ngoài `maxAttempts`, có thể cần **deadline** tổng từ HTTP request/job. Nếu còn 50 ms trước khi client timeout mà một attempt thường mất 500 ms, retry tiếp có thể không có ý nghĩa.

Khi deadline hết, trả lỗi có kiểm soát hoặc chuyển sang cơ chế job idempotent theo thiết kế. Không làm “retry không giới hạn” trong thread phục vụ request.

### 9.5. Không retry lỗi nghiệp vụ bình thường

Sau retry, transaction có thể đọc:

```text
remaining_on_duty = 1
```

Ứng dụng nên trả kết quả “không được cho người cuối cùng nghỉ” như một **quyết định nghiệp vụ hợp lệ**, không tự chuyển nó thành `40001` để thử tiếp đến khi phép UPDATE thành công.

---

## 10. Mẫu SQL thủ công cho retry đúng

Khi thực hành trong `psql`, giả sử phiên B gặp `40001` ở statement/`COMMIT`. Việc làm lại nên bắt đầu từ:

```sql
-- Nếu transaction cũ còn ở trạng thái failed:
ROLLBACK;

-- Attempt mới:
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS on_duty_count
FROM tx_retry_lab.on_call
WHERE on_duty;

-- Ứng dụng/người thực hành quyết định dựa trên
-- on_duty_count MỚI.
--
-- Nếu >= 2 mới thực hiện:
-- UPDATE tx_retry_lab.on_call
-- SET on_duty = FALSE
-- WHERE doctor_id = 2
--   AND on_duty = TRUE;

COMMIT;
```

Không dùng câu `UPDATE` bỏ kiểm tra chỉ vì “attempt trước đã kiểm tra rồi”. Mọi quyết định có thể phụ thuộc snapshot cũ cần được kiểm tra lại.

### 10.1. SQL một statement không tự loại bỏ mọi serialization failure

Có thể gói điều kiện vào một `UPDATE`:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

UPDATE tx_retry_lab.on_call AS target
SET on_duty = FALSE
WHERE target.doctor_id = 1
  AND target.on_duty = TRUE
  AND (
      SELECT COUNT(*)
      FROM tx_retry_lab.on_call
      WHERE on_duty
  ) >= 2
RETURNING target.doctor_id;

COMMIT;
```

Điều kiện tổng hợp vẫn phụ thuộc snapshot/quan hệ đọc–ghi. Ở `SERIALIZABLE` có thể phát sinh `40001` và toàn statement phải được thử lại trong transaction mới. Ưu điểm của mẫu một câu là điều kiện nghiệp vụ nằm trong SQL thay vì bị tách rời, nhưng nó **không có nghĩa không thể xảy ra tranh chấp**.

### 10.2. UPDATE 0 không phải SQLSTATE 40001

Nếu phép `UPDATE ... RETURNING` không trả hàng nào do điều kiện không còn đúng, đó là một **kết quả nghiệp vụ**, không mặc định là serialization failure.

```text
UPDATE 0
```

có thể nghĩa là bác sĩ đã nghỉ từ trước hoặc không còn đủ điều kiện. Cần phân biệt **câu lệnh chạy thành công nhưng không đổi hàng** với **transaction bị hủy do tranh chấp**.

---

## 11. Ví dụ Java/JDBC: retry toàn bộ transaction bằng connection mới

Trong Java, khung retry cần đặt **bên ngoài mọi bước đọc và ghi**. Mỗi attempt mở connection/transaction mới, thiết lập isolation, đọc count, kiểm tra nghiệp vụ, update và commit. Nếu gặp `40001`, rollback, đóng connection, chờ backoff rồi làm lại.

Ví dụ dưới dùng Java 17+, JDBC và `javax.sql.DataSource`:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.ThreadLocalRandom;

public final class DoctorScheduleService {
    private static final int MAX_ATTEMPTS = 5;
    private final DataSource dataSource;

    public DoctorScheduleService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    /**
     * true:  đã chuyển bác sĩ sang off-duty.
     * false: không đổi vì điều kiện nghiệp vụ không còn thỏa.
     *
     * Retry toàn bộ transaction khi SQLSTATE 40001.
     */
    public boolean takeOffDuty(int doctorId)
            throws SQLException, InterruptedException {

        for (int attempt = 1;
             attempt <= MAX_ATTEMPTS;
             attempt++) {

            // Mỗi attempt lấy connection và transaction mới.
            try (Connection conn = dataSource.getConnection()) {
                conn.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE
                );
                conn.setAutoCommit(false);

                try {
                    long onDutyCount = countOnDuty(conn);

                    // Điều kiện nghiệp vụ được đọc LẠI
                    // ở từng attempt.
                    if (onDutyCount <= 1) {
                        conn.commit();
                        return false;
                    }

                    int updated =
                        markOffDuty(conn, doctorId);

                    // 40001 vẫn có thể xuất hiện ở commit().
                    conn.commit();
                    return updated == 1;

                } catch (SQLException error) {
                    try {
                        conn.rollback();
                    } catch (SQLException rollbackError) {
                        error.addSuppressed(rollbackError);
                    }

                    boolean isSerializationFailure =
                        "40001".equals(error.getSQLState());

                    if (!isSerializationFailure
                            || attempt == MAX_ATTEMPTS) {
                        throw error;
                    }
                    // Lỗi đã được xử lý ở attempt này.
                    // Sau khi thoát try-with-resources,
                    // connection được đóng/trả pool.
                }
            }

            // Không ngủ khi còn giữ transaction/connection.
            backoff(attempt);
        }

        // Không tới đây vì attempt cuối luôn return/throw.
        throw new IllegalStateException(
            "Unexpected retry loop termination"
        );
    }

    private long countOnDuty(Connection conn)
            throws SQLException {
        String sql = """
            SELECT COUNT(*) AS on_duty_count
            FROM tx_retry_lab.on_call
            WHERE on_duty = TRUE
            """;

        try (PreparedStatement statement =
                 conn.prepareStatement(sql);
             ResultSet rs = statement.executeQuery()) {
            rs.next();
            return rs.getLong("on_duty_count");
        }
    }

    private int markOffDuty(
            Connection conn, int doctorId
    ) throws SQLException {
        String sql = """
            UPDATE tx_retry_lab.on_call
            SET on_duty = FALSE
            WHERE doctor_id = ?
              AND on_duty = TRUE
            """;

        try (PreparedStatement statement =
                 conn.prepareStatement(sql)) {
            statement.setInt(1, doctorId);
            return statement.executeUpdate();
        }
    }

    private static void backoff(int failedAttempt)
            throws InterruptedException {
        // Bản minh họa: 25ms, 50ms, 100ms, 200ms.
        long ceiling = Math.min(
            400L,
            25L << (failedAttempt - 1)
        );
        long millis = ThreadLocalRandom
            .current()
            .nextLong(ceiling + 1);

        try {
            Thread.sleep(millis);
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw interrupted;
        }
    }
}
```

### 11.1. Tại sao đoạn mã này đúng về ranh giới retry?

Đối chiếu:

| Thành phần | Hành vi |
|---|---|
| Vòng `for` ngoài | Tạo một **attempt giao dịch hoàn chỉnh** |
| `dataSource.getConnection()` | Nhận connection cho attempt hiện tại |
| `setTransactionIsolation(SERIALIZABLE)` | Thiết lập mức cô lập trước các câu lệnh nghiệp vụ |
| `setAutoCommit(false)` | Bắt đầu quản lý transaction rõ ràng |
| `countOnDuty(conn)` | **Đọc lại** trong mỗi attempt |
| `markOffDuty(conn, doctorId)` | Chỉ ghi sau khi điều kiện mới còn hợp lệ |
| `conn.commit()` | Có thể ném `40001` và cũng phải được xử lý trong attempt |
| `conn.rollback()` | Hủy attempt thất bại |
| Kiểm tra `getSQLState()` | Chỉ retry loại lỗi được chọn |
| `attempt == MAX_ATTEMPTS` | Chấm dứt retry và báo lỗi |
| `backoff` sau try-with-resources | Không giữ connection khi chờ |

Điểm mấu chốt: **Không đặt `countOnDuty` ngoài vòng retry**. Nếu số liệu được đọc một lần trước vòng `for`, mỗi attempt có thể dùng quyết định lỗi thời dù mỗi transaction có snapshot mới.

### 11.2. Vì sao vẫn cần kiểm tra `updated == 1`?

Một bác sĩ có thể đã `off-duty` từ trước. Khi đó câu `UPDATE ... WHERE on_duty = TRUE` trả **0 hàng**, một trạng thái hợp lệ. Ví dụ đơn giản này trả `false`. API thực tế có thể phân biệt **“không tồn tại bác sĩ”**, **“đã nghỉ”** và **“không được nghỉ vì đang là người cuối”** bằng các câu đọc bổ sung **bên trong transaction** nếu nghiệp vụ cần.

### 11.3. Hạn chế của mẫu JDBC

Mẫu này dạy transaction boundary, không phải bộ thư viện retry production hoàn chỉnh:

- Không có deadline tổng của request.
- Chưa retry `40P01` (có thể bổ sung theo chính sách).
- Không ghi số lần retry/metric/tracing.
- Mỗi attempt dùng connection mới; thực tế pool phải khôi phục isolation/autocommit/session state trước khi tái sử dụng.
- Không xử lý các side effect ngoài database.
- Nếu `COMMIT` gặp lỗi **mất kết nối không rõ kết quả**, không được suy đoán rollback chắc chắn như lỗi `40001`.
- Trong framework quản lý transaction, không tự `commit`/`rollback` một connection do framework sở hữu.

### 11.4. Bắt lỗi ở tầng transaction thích hợp

Đừng đặt retry ngay trong DAO chỉ có một câu SQL nếu business transaction còn các thao tác khác ngoài DAO:

```text
Service:
   query account + query quota + update orders + update inventory
                                                ^
                                                |
                    Retry duy nhất update này là SAI.
```

Retry phải nằm ở **tầng bao trọn tất cả các thao tác** cùng làm nên quyết định nghiệp vụ.

---

## 12. Transaction framework: lỗi retry chỉ đúng khi mở transaction mới

Trong Spring hoặc một framework tương tự, việc đặt annotation retry và transaction sát nhau chưa tự chứng minh ranh giới retry đúng.

### 12.1. Cấu trúc khuyến nghị

```text
Request/API
    |
    v
RetryCoordinator                 <-- vòng attempt ở ngoài
    |
    +-- attempt 1 --> TransactionalBusinessService
    |                    BEGIN SERIALIZABLE
    |                    SELECT + tính toán + UPDATE + COMMIT
    |                    lỗi 40001 -> transaction rollback
    |
    +-- backoff
    |
    +-- attempt 2 --> TransactionalBusinessService
                         BEGIN SERIALIZABLE MỚI
                         SELECT + tính toán lại + UPDATE + COMMIT
```

Điều quan trọng là **mỗi lần retry thực sự đi vào một transaction mới**. Nếu retry bị gọi **bên trong** một transaction outer đang mở, lần thứ hai có thể vẫn dùng snapshot cũ/transaction bị lỗi.

### 12.2. Vấn đề proxy và self-invocation

Trong các framework dùng proxy/AOP, gọi một phương thức được đánh dấu `@Transactional` từ **một phương thức khác của cùng instance** có thể không đi qua proxy, nên transaction annotation không có tác dụng như mong đợi.

Khi thiết kế retry coordinator, cần đảm bảo lời gọi vào transactional service đi qua đúng boundary của framework, hoặc dùng công cụ transaction programmatic như `TransactionTemplate` được cấu hình hợp lệ.

### 12.3. Tránh tình trạng “retry ở trong transaction”

Không muốn cấu trúc:

```text
@Transactional                    <-- mở một transaction
method() {
    retryLoop {
        SELECT ...
        UPDATE ...
        // 40001 đã làm transaction hỏng,
        // nhưng retryLoop vẫn nằm trong transaction cũ!
    }
}
```

Muốn:

```text
retryLoop {
    @Transactional service.call() <-- mỗi call mở transaction mới
}
```

Tên annotation ở đây chỉ minh họa, không phải đoạn source đầy đủ có thể biên dịch độc lập. Trong Spring, còn phải xét thứ tự advice, rollback rules, exception translation và propagation.

### 12.4. Exception translation

Một framework có thể chuyển `SQLException` thành exception riêng. Khi đó:

- Xác định exception nào tương ứng `40001`.
- Đảm bảo retry không làm mất SQLSTATE/causes cần phân tích.
- Đảm bảo transaction đã rollback **trước** khi retry.
- Không retry lỗi nghiệp vụ không được phép.

Chẳng hạn Spring có exception thể hiện serialization/optimistic/pessimistic concurrency theo lớp trừu tượng của nó; logic retry phải dựa trên hợp đồng framework và driver đang dùng, không chỉ `e instanceof SQLException` nếu lớp lỗi đã bị wrap.

---

## 13. Deadlock 40P01 và serialization failure 40001

### 13.1. Ví dụ deadlock do hai transaction khóa hàng ngược thứ tự

Giả sử có hai tài khoản A và B. Transaction T1 cập nhật A trước rồi B; T2 cập nhật B trước rồi A:

```text
T1 giữ lock row A              T2 giữ lock row B
T1 chờ row B                   T2 chờ row A
             \                /
                  DEADLOCK
```

PostgreSQL phát hiện và hủy một transaction với SQLSTATE **`40P01`**. Transaction đó cần rollback và, nếu hợp lệ, retry toàn bộ logic.

### 13.2. Cách giảm deadlock

- Cập nhật nhiều tài nguyên theo **thứ tự khóa nhất quán**, ví dụ `account_id` tăng dần.
- Giữ transaction ngắn; tránh gọi mạng trong lúc giữ row locks.
- Có index cho các phép tìm/khóa quan trọng để giảm scan không cần thiết.
- Tránh giữ lock rồi yêu cầu thêm tài nguyên theo thứ tự khác nhau ở nhiều code path.
- Bắt và retry `40P01` ở **transaction boundary**, không chỉ retry câu lệnh vừa bị deadlock.

### 13.3. 40001 khác nhau ở đâu?

`40001` có thể xuất hiện **ngay cả khi không có chu trình chờ lock** như deadlock. Với write skew, hai giao dịch sửa **hai hàng khác nhau**, nhưng đọc điều kiện liên quan đến nhau; SSI hủy một giao dịch để giữ serializability.

**Tóm lại:** cả hai có thể là lỗi tranh chấp tạm thời, nhưng:

- `40P01`: PostgreSQL phát hiện **deadlock**.
- `40001`: PostgreSQL không thể cho transaction commit mà vẫn đảm bảo **serialization**.

Ứng dụng có thể dùng cùng khung retry nhưng phải giữ phân loại lỗi để phân tích và tối ưu.

---

## 14. UNIQUE, ON CONFLICT và những lỗi không nên retry mù quáng

### 14.1. Không phải mọi concurrent conflict đều là 40001

Nếu hai request cùng chèn một mã đơn hàng đã có ràng buộc unique, một bên có thể nhận:

```text
SQLSTATE 23505 — unique_violation
```

Điều này thường có nghĩa **khóa đã tồn tại** và ứng dụng nên xử lý theo quy tắc nghiệp vụ: trả “đã tồn tại”, dùng idempotency key hoặc `ON CONFLICT` phù hợp.

### 14.2. ON CONFLICT không thay thế SERIALIZABLE

```sql
INSERT INTO some_table(id, value)
VALUES (10, 'demo')
ON CONFLICT (id) DO NOTHING;
```

Lệnh giải quyết **xung đột unique của chính INSERT** theo cách khai báo. Nó không tự đảm bảo các quy tắc đọc–ghi đa hàng của toàn transaction đã serializable.

Trong một transaction SERIALIZABLE có nhiều thao tác, `40001` vẫn có thể xảy ra dù một câu `INSERT ... ON CONFLICT` đã xử lý được một unique conflict.

### 14.3. Trường hợp đặc biệt của unique violation dưới SERIALIZABLE

Tài liệu PostgreSQL lưu ý một số lỗi unique constraint có thể phát sinh từ cạnh tranh mà ứng dụng nhìn nhận như serialization conflict, ví dụ hai transaction **đọc để kiểm tra khóa rồi tự sinh khóa mới** và cùng chèn. Do đó, trong một số thuật toán cụ thể, ứng dụng có thể cần retry toàn bộ transaction ngay cả khi lỗi nhận được là `23505`.

Tuy nhiên:

- Không có nghĩa **mọi `23505` đều retryable**.
- Phải phân biệt khóa người dùng nhập đã tồn tại thật với khóa sinh theo thuật toán có thể thay đổi trong attempt mới.
- Cần constraint ở database để bảo vệ bất biến kể cả khi precheck bị race.
- Với idempotency, có khi **đúng** là trả kết quả của request trước chứ không thử tạo bản ghi khác.

**Chính sách an toàn mặc định:** tự động retry `40001`; thêm những SQLSTATE khác chỉ khi có phân tích/thiết kế nghiệp vụ rõ.

### 14.4. Optimistic concurrency không giống 40001

Một mẫu update version:

```sql
UPDATE accounts
SET balance = balance - 100,
    version = version + 1
WHERE account_id = 5
  AND version = 12
  AND balance >= 100;
```

Nếu `UPDATE 0`, có thể version đã đổi hoặc không đủ số dư. Không tự gọi đó là serialization failure. Ứng dụng cần đọc lại và phân biệt business conflict theo hợp đồng của optimistic locking.

---

## 15. Retry và tác động ra ngoài database

Đây là nơi nhiều hệ thống xử lý `40001` đúng ở SQL nhưng **sai ở nghiệp vụ**.

### 15.1. Vấn đề gửi email/thanh toán giữa transaction

Giả sử:

```text
BEGIN SERIALIZABLE
  UPDATE orders
  CALL payment gateway: thu 500.000đ
  COMMIT -> 40001
ROLLBACK
RETRY
  UPDATE orders
  CALL payment gateway: thu 500.000đ lần nữa
  COMMIT
```

PostgreSQL rollback **thay đổi trong database**, nhưng **không rollback khoản tiền đã thu ở payment gateway**. Retry toàn bộ code một cách máy móc có thể thu tiền hai lần.

Tương tự với:

- Gửi email/SMS.
- Gọi HTTP API có side effect.
- Xuất file hoặc đẩy sự kiện vào queue không gắn transaction.
- Gọi thiết bị vật lý.
- Chuyển tiền, tạo vận đơn, kích hoạt tài khoản ở hệ thống khác.

### 15.2. Phân loại bước theo khả năng retry

| Loại công việc | Ví dụ | Cách thiết kế |
|---|---|---|
| Đọc và ghi trong **cùng PostgreSQL transaction** | SELECT, UPDATE, INSERT, DELETE | Thử lại toàn bộ transaction |
| Tính toán thuần túy, không side effect | Tính hạn mức từ các hàng đã đọc | Có thể tính lại mỗi attempt |
| Gọi dịch vụ ngoài có thể thay đổi trạng thái | Thanh toán, email, API ghi | Dùng idempotency/outbox/orchestration phù hợp |
| Tạo ID ngẫu nhiên hoặc timestamp | request ID, batch time | Quyết định phải giữ cố định hay tạo lại theo ngữ nghĩa |
| Tạo số thứ tự nghiệp vụ | mã hóa đơn, số chứng từ | Cần cơ chế cấp số và chính sách không tái sử dụng phù hợp |

### 15.3. Dời side effect ra sau COMMIT

Một hướng đơn giản là:

```text
BEGIN
  SELECT ...
  UPDATE ...
COMMIT thành công

SAU ĐÓ:
  gửi email/thông báo
```

Điều này tránh gửi email ở một attempt chắc chắn bị rollback. Nhưng lại tạo **khoảng trống độ tin cậy**: nếu ứng dụng chết ngay sau commit trước khi gửi email, email có thể không được gửi.

### 15.4. Transactional outbox

Một cách thường dùng để giảm khoảng trống này:

```text
Trong cùng PostgreSQL transaction:
  1. Đọc + cập nhật dữ liệu nghiệp vụ
  2. INSERT một hàng vào bảng outbox
  3. COMMIT

Sau commit:
  Worker đọc outbox
  Gửi sự kiện/email/API
  Ghi trạng thái phát hành
```

Nếu transaction bị `40001` và rollback, **cả dữ liệu nghiệp vụ và hàng outbox** cùng không commit. Attempt sau có thể tạo outbox mới cùng quyết định nghiệp vụ đã được tính lại.

### 15.5. Ví dụ schema outbox

```sql
CREATE TABLE tx_retry_lab.outbox_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
```

Một transaction có thể ghi sự kiện:

```sql
-- Trong một transaction đang thực hiện thay đổi nghiệp vụ:
-- INSERT INTO tx_retry_lab.outbox_events
--     (event_id, event_type, payload)
-- VALUES (
--     :stable_event_id,
--     'DoctorWentOffDuty',
--     jsonb_build_object('doctorId', :doctor_id)
-- );
```

Các tham số `:stable_event_id` và `:doctor_id` là **ký hiệu minh họa cho bind parameter của client**, không phải cú pháp parameter chuẩn chạy trực tiếp trong `psql`.

Sự kiện được xử lý sau commit bởi worker. Worker cũng phải xử lý **phát lại** vì một sự kiện có thể được gửi thành công nhưng tiến trình chết trước khi ghi `published_at`. Consumer nên idempotent/deduplicate theo `event_id` khi cần.

**Outbox không tự biến toàn hệ thống thành exactly-once delivery**. Nó tạo liên kết transaction giữa dữ liệu nghiệp vụ và việc ghi ý định phát sự kiện; việc phát thực tế vẫn cần cơ chế retry và chống xử lý lặp.

---

## 16. Idempotency: retry không được tạo kết quả trùng

### 16.1. Transaction retry và request retry là hai lớp khác nhau

**Transaction retry:** ứng dụng biết PostgreSQL đã từ chối attempt với `40001`; transaction không commit. Có thể thử lại business transaction mới.

**Request retry:** client gửi lại HTTP request do timeout, proxy retry hoặc người dùng bấm lại. Request trước **có thể đã commit**, dù client không nhận được response.

Hai tình huống cần giải pháp liên quan nhưng không giống hệt nhau.

### 16.2. Idempotency key cố định theo yêu cầu nghiệp vụ

Ví dụ một API tạo đơn nhận:

```text
POST /orders
Idempotency-Key: 8e9c...stable-request-key
```

Server lưu một **request_id** có unique constraint cùng kết quả hoặc định danh đối tượng đã tạo. Nếu client gửi lại cùng key, server xác định **cùng yêu cầu** đã được xử lý chưa, thay vì tạo thêm một đơn khác.

```sql
CREATE TABLE tx_retry_lab.request_results (
    request_id UUID PRIMARY KEY,
    resource_id BIGINT NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Trong production, request_id thường đi kèm **phạm vi tenant**, fingerprint/payload hoặc chính sách ngăn cùng key dùng cho hai nội dung khác nhau. Một bảng demo chỉ có `request_id` và `resource_id` là để minh họa ràng buộc unique, **chưa phải thiết kế idempotency hoàn chỉnh**.

### 16.3. Khóa nên được sinh ở đâu?

Nếu request đến từ client với idempotency key, giữ **cùng key** xuyên các lần retry. Không sinh một key mới cho mỗi attempt, vì khi request đã commit nhưng response thất lạc, key mới sẽ mất tác dụng chống trùng.

Với một event outbox đại diện cho một thay đổi nghiệp vụ cụ thể, có thể dùng event ID được cấp ổn định theo operation hoặc chiến lược deduplication khác. Quyết định phụ thuộc ngữ nghĩa: **một retry của cùng operation** khác **một operation mới**.

### 16.4. Kết quả COMMIT không rõ do lỗi mạng

Trường hợp đặc biệt:

```text
Application gửi COMMIT
    |
Kết nối mạng bị mất trước khi nhận phản hồi
    |
Transaction có thể đã COMMIT hoặc chưa COMMIT
    |
Ứng dụng KHÔNG biết chắc kết quả
```

Không được tự suy luận “không nhận response = rollback”, rồi thực hiện lại một khoản thanh toán/đơn hàng **không có idempotency**.

Đây **không giống** lỗi `40001` được PostgreSQL trả về rõ ràng: với `40001`, transaction đó bị từ chối và không commit; còn mất kết nối trong lúc commit có thể là **unknown outcome**.

Cách xử lý thường cần:

- Idempotency key/operation ID bền vững.
- Truy vấn đối chiếu sau khi khôi phục kết nối.
- Retry yêu cầu chỉ qua logic có khả năng phát hiện **đã xử lý**.
- Không chạy side effect ngoài database không idempotent hai lần.

Một connection error thuộc nhóm SQLSTATE `08xxx` không nên bị gộp mặc định vào cùng nhánh “retry chắc chắn an toàn” với `40001`.

---

## 17. Thực hành phân biệt retryable và non-retryable

### 17.1. Serialization failure 40001

**Nguyên nhân:** PostgreSQL không thể cho transaction commit an toàn dưới mức cô lập của nó.

**Hành động:** rollback transaction lỗi, retry toàn bộ business transaction với snapshot mới, giới hạn attempts.

### 17.2. Deadlock 40P01

**Nguyên nhân:** chu trình chờ khóa.

**Hành động:** rollback và có thể retry toàn bộ transaction; đồng thời điều tra thứ tự khóa/thiết kế truy cập.

### 17.3. Unique violation 23505

**Nguyên nhân:** khóa vi phạm uniqueness.

**Hành động:** thường là lỗi nghiệp vụ hoặc idempotency conflict; xử lý theo rule. Chỉ retry chọn lọc khi có lý do rõ ràng liên quan đến thuật toán sinh khóa và cạnh tranh.

### 17.4. Exclusion violation 23P01

**Nguyên nhân:** ví dụ một lịch hẹn chồng thời gian với lịch đã có theo exclusion constraint.

**Hành động:** thường báo không còn slot/đề nghị chọn slot khác. Retry nguyên yêu cầu với cùng slot **không tự giải quyết** xung đột khi lịch kia vẫn tồn tại.

### 17.5. Statement timeout 57014

**Nguyên nhân:** câu lệnh bị hủy, có thể do `statement_timeout` hoặc một yêu cầu cancel.

**Hành động:** rollback transaction nếu đã lỗi, điều tra thời gian thực thi, query plan, tài nguyên và deadline; retry chỉ khi còn thời gian và có cơ sở hợp lý. Không tự đổi thành `40001`.

### 17.6. Không đủ số dư hoặc điều kiện không còn đúng

**Nguyên nhân:** logic kinh doanh sau retry thấy dữ liệu mới.

**Hành động:** trả kết quả nghiệp vụ như “không đủ hạn mức” hoặc “bác sĩ cuối cùng không thể nghỉ”, không coi đó là lỗi database và không thử cho đến khi thành công.

---

## 18. Giảm serialization failure bằng thiết kế giao dịch

Retry là thành phần bắt buộc của ứng dụng sử dụng `SERIALIZABLE` trong điều kiện tranh chấp, nhưng **giảm xung đột** cũng quan trọng.

### 18.1. Giữ transaction ngắn

Không làm:

```text
BEGIN SERIALIZABLE
SELECT ...
chờ người dùng bấm xác nhận trong 30 giây
gọi API ngoài trong 10 giây
UPDATE ...
COMMIT
```

Transaction dài giữ snapshot và metadata xung đột lâu hơn, có thể tăng rủi ro abort, lock contention và áp lực vận hành.

Nên nhận đầu vào và thực hiện bước chờ người dùng **trước** khi mở transaction, rồi chỉ thực thi các thao tác database cần nhất quán trong transaction ngắn.

### 18.2. Tối ưu truy vấn đọc dùng trong quyết định

SSI có thể theo dõi các vùng dữ liệu được đọc. Truy vấn quét rất rộng do thiếu index/bộ lọc có thể tạo phạm vi phụ thuộc lớn hơn. Chẳng hạn:

```sql
SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Trong lab chỉ có hai hàng nên không thành vấn đề. Với hệ thống thật, một điều kiện theo `tenant_id`, `shift_id` hoặc phòng ban sẽ giảm dữ liệu liên quan nếu nghiệp vụ xác định được một phạm vi nhỏ hơn.

Không thu hẹp query chỉ để ít xung đột mà làm sai quy tắc nghiệp vụ. **Phạm vi đọc phải đúng trước, tối ưu sau**.

### 18.3. Có thể cần index

Ví dụ nếu bảng lịch trực production có các cột `tenant_id` và `shift_id`:

```sql
-- Minh họa trên schema mở rộng có đủ các cột:
-- CREATE INDEX on_call_shift_idx
-- ON on_call (tenant_id, shift_id, on_duty);
```

Index phù hợp có thể giảm chi phí truy vấn/khả năng predicate lock thô trong một số tình huống, nhưng không có bảo đảm chung “có index là hết `40001`”. Tranh chấp nghiệp vụ thực vẫn phải được retry.

### 18.4. Tránh cập nhật cùng tài nguyên không cần thiết

- Không chạy `UPDATE` ghi lại cùng giá trị nếu không cần.
- Tránh một transaction lớn bao trùm nhiều tài nguyên độc lập.
- Nếu nhiều row phải khóa, giữ **thứ tự truy cập nhất quán**.
- Phân chia job theo tenant/shard/khóa khi nghiệp vụ cho phép, giảm hot spot.
- Với counter/hạn mức có thể thiết kế một row đại diện để khóa nguyên tử thay vì đọc toàn bảng, nhưng phải xác định tính đúng đắn và điểm nghẽn.

### 18.5. SELECT FOR UPDATE là lựa chọn khác, không phải “bật lên cho chắc”

```sql
SELECT *
FROM tx_retry_lab.on_call
WHERE on_duty
FOR UPDATE;
```

Khóa các hàng được chọn có thể giúp serialization trong một số thiết kế, nhưng có trade-off:

- Chặn tiến trình khác và có thể tạo deadlock.
- Không nhất thiết bảo vệ **những hàng chưa tồn tại** hoặc mọi predicate phức tạp ở `READ COMMITTED`.
- Có thể làm giảm throughput rõ rệt nếu khóa cả tập lớn.
- Vẫn phải xem snapshot, lock order và khả năng retry.

Không coi `SELECT FOR UPDATE` và `SERIALIZABLE` là hai phép thay thế hoàn toàn tương đương.

### 18.6. SERIALIZABLE không tự sửa logic ứng dụng

Nếu logic bên trong transaction tự viết:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 1;
```

mà **không đọc và kiểm tra** quy tắc “luôn còn ít nhất một người trực”, `SERIALIZABLE` không tự biết phải cấm việc cho người cuối cùng nghỉ. Serializable đảm bảo kết quả tương đương một lịch tuần tự của **những câu lệnh được viết**, không tự tạo constraint nghiệp vụ vắng mặt trong SQL.

---

## 19. Trường hợp đọc đơn thuần: READ ONLY DEFERRABLE

Một số workload chỉ **đọc báo cáo dài** và cần ảnh dữ liệu nhất quán, không ghi.

PostgreSQL hỗ trợ transaction **`SERIALIZABLE READ ONLY DEFERRABLE`**:

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT doctor_id, doctor_name, on_duty
FROM tx_retry_lab.on_call
ORDER BY doctor_id;

COMMIT;
```

Với chế độ này, PostgreSQL có thể **chờ một snapshot an toàn** lúc bắt đầu, rồi transaction đọc có thể tránh nhu cầu abort do SSI theo cách áp dụng cho safe snapshot.

Những điểm cần hiểu:

- `DEFERRABLE` có ý nghĩa đặc biệt khi đi cùng `SERIALIZABLE` và `READ ONLY`.
- Nó không phải cách tăng tốc mọi transaction; có thể phải chờ trước khi bắt đầu đọc.
- Không dùng cho transaction cần `INSERT`/`UPDATE`/`DELETE`.
- Không nên chọn chỉ vì muốn “hết lỗi 40001” ở nghiệp vụ ghi.

Đây là lựa chọn hữu ích cho báo cáo/chụp snapshot chỉ đọc khi thời gian chờ ban đầu được chấp nhận.

---

## 20. Giám sát và chẩn đoán serialization failure

Một hệ thống không nên chỉ ghi log “database error” rồi mất ngữ cảnh. Khi `40001` tăng mạnh, cần phân biệt **tranh chấp tạm thời bình thường** với **thiết kế giao dịch gây xung đột quá nhiều**.

### 20.1. Metrics nên có ở tầng ứng dụng

| Metric | Ý nghĩa |
|---|---|
| Số transaction attempts | Số lần thực hiện, bao gồm retry |
| Số `40001` theo nghiệp vụ | Tỷ lệ serialization failure |
| Số `40P01` theo nghiệp vụ | Tỷ lệ deadlock |
| Số attempt trước khi thành công | Phân bố retry depth |
| Số lần hết retry budget | Giao dịch thất bại sau giới hạn |
| Độ trễ mỗi attempt | Thời gian từng transaction |
| Độ trễ end-to-end | Bao gồm backoff và retry |
| Số transaction đang mở lâu | Nguy cơ giữ snapshot/lock lâu |
| Số lỗi unknown commit outcome | Phải đối chiếu/idempotency |

Mỗi log nên gắn **operation/request ID**, loại nghiệp vụ, attempt number, SQLSTATE và thời gian; không ghi thừa PII, mật khẩu, thông tin thanh toán hay SQL có dữ liệu nhạy cảm.

### 20.2. Quan sát transaction đang chạy

Một truy vấn vận hành tham khảo:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Quyền nhìn thấy thông tin đầy đủ của phiên khác phụ thuộc role/quyền monitoring. Không chạy query này chỉ để thu câu SQL nhạy cảm cho log không được kiểm soát.

### 20.3. Quan sát predicate lock trong bối cảnh SSI

```sql
SELECT
    pid,
    locktype,
    mode,
    relation::regclass AS relation_name,
    page,
    tuple,
    granted
FROM pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
```

Đây là dữ liệu quan sát phục vụ chẩn đoán, **không phải một phép xác định transaction nào chắc chắn sẽ bị 40001**. Kế hoạch truy vấn, thời điểm đọc/ghi và cơ chế nội bộ quyết định phụ thuộc thật.

### 20.4. EXPLAIN không mô phỏng lịch đồng thời

```sql
EXPLAIN
SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;
```

`EXPLAIN` giúp xem kế hoạch đọc, index và ước lượng, nhưng không tự tái tạo write skew của hai transaction cùng thời điểm. Để kiểm thử serialization failure cần **ít nhất hai connection và lịch xen kẽ** như các bước ở phần 5–6.

### 20.5. Không nhầm thống kê replica conflict với 40001 ứng dụng

Một số thống kê hệ thống về **recovery conflicts trên standby** phục vụ quan sát hủy truy vấn ở replica, không trực tiếp là “số serialization failures `40001` trên primary” cho từng business transaction.

Vì vậy, theo dõi **SQLSTATE tại tầng ứng dụng** là cách rõ ràng để biết retry có đang diễn ra nhiều không. Các chỉ số server hỗ trợ phân tích nguyên nhân, nhưng không tự thay log transaction attempt.

---

## 21. Thiết kế kiểm thử đồng thời

Một unit test chỉ gọi service một lần thường không đủ để chứng minh retry đúng. Cần tình huống hai transaction **thật sự chồng lấn**.

### 21.1. Kịch bản nền: hai bác sĩ

1. Reset `on_duty=true` cho hai bác sĩ.
2. Tạo **hai connection** riêng cùng database.
3. Cả hai bắt đầu `SERIALIZABLE`.
4. Cả hai đọc `COUNT(*)=2` trước khi bất kỳ bên nào ghi.
5. Hai transaction cập nhật **hai row khác nhau**.
6. Cố commit cả hai.
7. Xác nhận không thể có cả hai commit tạo `remaining=0`.
8. Nếu có `40001`, rollback và retry **toàn bộ logic**.
9. Sau retry, xác nhận **remaining >= 1**.

### 21.2. Các test case nên có

| Tình huống | Điều cần chứng minh |
|---|---|
| Không tranh chấp | Transaction thành công không retry |
| Write skew ở `REPEATABLE READ` | Có thể vi phạm bất biến đa hàng |
| Write skew ở `SERIALIZABLE` | Một transaction có thể bị `40001` |
| Retry sau 40001 | Có snapshot mới và quyết định mới |
| 40001 tại `COMMIT` | Retry boundary bắt được lỗi |
| 40P01 do lock ngược thứ tự | Rollback/retry nếu được cho phép |
| Hết retry budget | Báo lỗi có kiểm soát, không vòng lặp vô hạn |
| 23505 thật | Không retry mù quáng |
| Client timeout sau COMMIT | Idempotency tránh tạo duplicate |
| External side effect | Không gửi thanh toán/email hai lần do retry |
| Transaction manager/proxy | Mỗi attempt thực sự mở transaction mới |
| Connection pool | Không để lộ trạng thái isolation/autocommit giữa request |

### 21.3. Đồng bộ thread trong test

Trong integration test Java, có thể dùng **`CountDownLatch`** hoặc **`CyclicBarrier`** để đảm bảo cả hai transaction đã đọc `COUNT(*)` trước khi cho phép chúng UPDATE/COMMIT. Điều này giúp tái tạo write skew ổn định hơn là chỉ khởi chạy hai thread và hy vọng chúng tự xen kẽ đúng lúc.

Tuy nhiên, không bao giờ giữ barrier vô hạn trong test khi một thread đã lỗi trước điểm hẹn; cần timeout và cleanup/rollback trong `finally`.

### 21.4. Kiểm tra kết quả thay vì chỉ đếm exception

Kiểm thử đúng cần chứng minh:

```sql
SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Sau tất cả retry/commit hợp lệ, **`remaining >= 1`**. Đếm có một exception `40001` nhưng sau đó dùng logic retry sai vẫn có thể tạo dữ liệu vi phạm. Kết quả nghiệp vụ mới là mục tiêu cuối.

---

## 22. Các lỗi thiết kế thường gặp

**1. “`40001` là database bị hỏng.”** Không. Nó có thể là cơ chế bắt buộc để giữ kết quả serializable.

**2. “Chỉ `SERIALIZABLE` mới phát sinh `40001`.”** Không. `REPEATABLE READ` cũng có thể thất bại khi transaction muốn cập nhật hàng đã đổi sau snapshot.

**3. “`REPEATABLE READ` bảo vệ mọi quy tắc nhiều hàng.”** Không. Write skew có thể xảy ra.

**4. “Chỉ retry câu `UPDATE` vừa lỗi.”** Sai. Phải làm lại **các bước đọc/quyết định/ghi** trong một transaction mới.

**5. “Nếu commit báo 40001 thì thử gọi COMMIT lần nữa.”** Sai. Transaction đó đã bị từ chối; phải bắt đầu transaction khác và thực hiện lại logic.

**6. “Có thể tiếp tục sau 40001 trong transaction cũ.”** Không. Transaction lỗi cần rollback/cleanup trước khi làm lại.

**7. “SAVEPOINT đủ để làm mới snapshot SERIALIZABLE.”** Không. Rollback về savepoint không tự tạo transaction outer mới.

**8. “Retry nên chạy vô hạn cho tới khi thành công.”** Không. Cần số lần tối đa, backoff, jitter và deadline.

**9. “Mọi SQLException đều retry được.”** Không. Lỗi ràng buộc và lỗi nghiệp vụ cần xử lý khác.

**10. “Bắt lỗi bằng chuỗi message tiếng Anh.”** Không. Dựa vào SQLSTATE hoặc exception mapping được định nghĩa rõ.

**11. “`25P02` là nguyên nhân chính của serialization failure.”** Thường là hệ quả của statement trước đã làm transaction thất bại.

**12. “Retry xảy ra bên trong `@Transactional` bao ngoài vẫn mở transaction mới.”** Không chắc. Phải kiểm tra boundary/proxy/propagation.

**13. “Có `SERIALIZABLE` thì không cần ràng buộc PK/UNIQUE/FK.”** Sai. Serializable không thay thế constraint.

**14. “Có `SERIALIZABLE` thì database tự biết quy tắc phải còn một bác sĩ trực.”** Sai. Transaction phải thể hiện phép đọc/kiểm tra có liên quan tới quy tắc.

**15. “200 OK từ API nghĩa là COMMIT nhất định đã thành công nếu JDBC không trả exception.”** Cần xác nhận thực tế commit; việc xử lý exception/transaction manager và lỗi mất kết nối có thể phức tạp.

**16. “Mất kết nối khi COMMIT giống 40001.”** Không. Kết quả commit có thể **không rõ**, cần đối chiếu/idempotency.

**17. “Không sao nếu email được gửi trong transaction rồi rollback.”** Sai. Email không tự bị thu hồi.

**18. “Transactional outbox bảo đảm exactly once cho mọi hệ.”** Không. Consumer vẫn phải xử lý at-least-once/retry/dedup.

**19. “Retry request phải tạo idempotency key mới mỗi lần.”** Sai. Giữ key ổn định cho cùng operation.

**20. “Số lần retry càng cao càng tốt.”** Không. Retry storm có thể làm xung đột và độ trễ tăng.

**21. “Thread.sleep trong lúc giữ connection không có chi phí.”** Không. Nó chiếm connection và có thể kéo dài lock/snapshot.

**22. “SELECT FOR UPDATE là giải pháp miễn phí cho mọi race condition.”** Không. Nó có lock contention, deadlock và giới hạn predicate.

**23. “`UPDATE 0` luôn phải retry.”** Không. Thường là một kết quả nghiệp vụ hoặc optimistic conflict khác.

**24. “`SERIALIZABLE READ ONLY DEFERRABLE` phù hợp cho transaction ghi.”** Không. Nó dành cho read-only.

**25. “EXPLAIN một query có thể chứng minh hệ thống không có write skew.”** Không. Cần kiểm thử đồng thời và kiểm chứng bất biến.

**26. “Lỗi unique 23505 luôn do serialization và cần retry.”** Không. Có nhiều lý do, phải phân loại.

**27. “Chỉ cần bắt 40001 ở statement UPDATE, không cần ở COMMIT.”** Sai. `40001` có thể xuất hiện lúc commit.

**28. “Mỗi attempt dùng snapshot mới nhưng có thể giữ quyết định cũ trong biến Java.”** Sai. Nếu biến phụ thuộc dữ liệu đã đọc, phải tính lại.

**29. “Transaction ngắn không cần kiểm soát timeout/lock.”** Không. Tranh chấp cao vẫn có thể gây vấn đề; cần giám sát.

**30. “Serialization failure chứng minh row-level locking không hoạt động.”** Không. SSI và row locks giải quyết những lớp xung đột khác nhau.

---

## 23. Bài tập thực hành có lời giải

### Bài 1 — Nhận diện lỗi

Một JDBC exception có:

```text
SQLSTATE=40001
Message=could not serialize access due to ...
```

**Câu hỏi:** Đây là lỗi gì và hành động chính?

**Đáp án:** `serialization_failure`. Rollback/dọn transaction cũ, bắt đầu transaction mới rồi thực hiện lại **toàn bộ logic phụ thuộc dữ liệu**, có giới hạn retry/backoff.

### Bài 2 — Có thể chạy lại UPDATE cuối không?

Giao dịch B đếm còn 2 bác sĩ, định cho Bình nghỉ rồi bị `40001`.

**Đáp án:** Không chỉ chạy lại `UPDATE doctor_id=2`. Phải đọc lại số người trực trong transaction mới; nếu hiện còn 1 người, không update.

### Bài 3 — Phân biệt REPEATABLE READ và SERIALIZABLE

**Câu hỏi:** Hai giao dịch đọc cùng tập hai bác sĩ rồi cập nhật hai hàng khác nhau, điều gì có thể xảy ra ở `REPEATABLE READ`?

**Đáp án:** **Write skew**: hai transaction có thể cùng commit và làm cả hai bác sĩ nghỉ. Serializable sẽ không cho cả hai commit kết quả không tuần tự hóa được.

### Bài 4 — SQL thiết lập mức cô lập

**Yêu cầu:** bắt đầu transaction đọc/ghi ở mức `SERIALIZABLE`.

**Đáp án:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- SELECT, business decision, UPDATE ...

COMMIT;
```

Nếu nhận `40001`, rollback/cleanup rồi chạy lại từ `BEGIN`.

### Bài 5 — Vì sao retry phải đọc lại COUNT?

**Đáp án:** Count=2 của attempt cũ thuộc snapshot cũ. Sau khi một transaction khác commit, count có thể là 1. Dùng số cũ sẽ dẫn tới quyết định không còn hợp lệ.

### Bài 6 — Lỗi ở COMMIT

**Câu hỏi:** Câu `UPDATE` thành công nhưng `COMMIT` báo `40001`. Có thể trả kết quả “đã cập nhật” cho client không?

**Đáp án:** Không. Transaction đã bị từ chối; thay đổi chưa commit. Cần retry toàn bộ transaction hoặc báo thất bại sau khi hết retry budget.

### Bài 7 — SQLSTATE deadlock

```text
40P01
```

**Đáp án:** `deadlock_detected`. Rollback và có thể retry toàn bộ transaction; đồng thời kiểm tra thứ tự khóa và giảm thời gian giữ locks.

### Bài 8 — Không retry mọi lỗi

**Câu hỏi:** Client gửi cùng email đã tồn tại trong một unique constraint và nhận `23505`. Có nên lặp lại ngay 10 lần?

**Đáp án:** Không. Cần xử lý bản ghi đã tồn tại hoặc quy tắc idempotency. Retry chỉ khi có một trường hợp cạnh tranh thực sự được phân tích và attempt mới có thể thay đổi kết quả.

### Bài 9 — Transaction bị abort

Một statement trả `40001`, statement kế tiếp trả `25P02`.

**Đáp án:** `25P02` là trạng thái transaction đã hỏng. Tìm lỗi gốc `40001`, thực hiện `ROLLBACK`, mở transaction khác.

### Bài 10 — Retry có backoff

**Yêu cầu:** nêu hai lý do phải có backoff và jitter.

**Đáp án:** Giảm việc các client retry đồng loạt và tránh tạo thêm xung đột/tải tài nguyên khi vừa xảy ra tranh chấp. Cần thêm `maxAttempts` hoặc deadline để không lặp vô hạn.

### Bài 11 — Đặt vòng retry ở đâu?

```text
SELECT account_balance
SELECT promotion
UPDATE wallet
INSERT order
COMMIT
```

**Đáp án:** Bọc **cả năm bước** trong một transaction attempt, rồi đặt vòng retry bên ngoài attempt đó. Không chỉ retry `INSERT order`.

### Bài 12 — Thanh toán ngoài database

Ứng dụng gọi payment gateway trước `COMMIT`; transaction gặp `40001`.

**Đáp án:** PostgreSQL không rollback thao tác charge ở gateway. Phải có idempotency key với gateway hoặc orchestration/compensation/outbox phù hợp; tránh gọi side effect không idempotent trong thân transaction retry.

### Bài 13 — Kết quả COMMIT không rõ

Connection đứt ngay sau khi gửi `COMMIT`.

**Đáp án:** Không thể kết luận chắc transaction đã rollback. Dựa trên operation ID/idempotency và truy vấn đối chiếu để xác định commit hay chưa trước khi làm lại nghiệp vụ có side effect.

### Bài 14 — Vì sao SAVEPOINT không đủ?

**Đáp án:** Savepoint không tạo một transaction outer mới với snapshot và các phụ thuộc SSI mới. Serialization failure yêu cầu retry toàn bộ transaction.

### Bài 15 — READ ONLY DEFERRABLE

**Yêu cầu:** viết transaction chỉ đọc có thể chờ snapshot an toàn.

**Đáp án:**

```sql
BEGIN TRANSACTION
    ISOLATION LEVEL SERIALIZABLE,
    READ ONLY,
    DEFERRABLE;

SELECT COUNT(*)
FROM tx_retry_lab.on_call
WHERE on_duty;

COMMIT;
```

Không dùng cho transaction có thao tác ghi.

### Bài 16 — Chẩn đoán bằng SQLSTATE trong Java

**Yêu cầu:** viết điều kiện nhận diện serialization failure.

**Đáp án:**

```java
if ("40001".equals(exception.getSQLState())) {
    // Rollback và retry toàn bộ transaction.
}
```

Không phụ thuộc chuỗi `exception.getMessage()`.

### Bài 17 — Kiểm thử invariant

**Câu hỏi:** Sau thử nghiệm hai bác sĩ ở mức SERIALIZABLE và retry đúng, câu query nào kiểm tra bất biến?

**Đáp án:**

```sql
SELECT COUNT(*) AS remaining
FROM tx_retry_lab.on_call
WHERE on_duty;
```

Kết quả hợp lệ của nghiệp vụ phải có `remaining >= 1`. Không chỉ kiểm tra “đã có một lỗi 40001”.

### Bài 18 — Vì sao UPDATE 0 không phải luôn là lỗi?

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = FALSE
WHERE doctor_id = 2
  AND on_duty = TRUE;
```

**Đáp án:** `UPDATE 0` có thể do bác sĩ đã `off-duty`; câu SQL vẫn thành công. Business service phải diễn giải kết quả theo yêu cầu thay vì retry kiểu serialization.

### Bài 19 — Khi nào không nên dùng SERIALIZABLE một cách máy móc?

**Đáp án:** Với các thao tác có thể bảo đảm invariant bằng constraint hoặc một cập nhật nguyên tử, `READ COMMITTED` cùng điều kiện/lock phù hợp có thể đơn giản và ít abort hơn. Quyết định theo tính đúng đắn và workload, không theo việc isolation nào nghe “mạnh nhất”.

### Bài 20 — Thiết kế idempotency key

Một request tạo đơn được gửi lại ba lần do timeout.

**Đáp án:** Dùng một request/operation ID ổn định, lưu kết quả gắn với ID đó qua unique constraint và đối chiếu khi request lặp. Không tạo key mới mỗi retry; xác minh payload và phạm vi tenant.

### Bài 21 — So sánh predicate read với row lock

**Câu hỏi:** `SIReadLock` có nghĩa là mọi `UPDATE` khác phải chờ như `FOR UPDATE`?

**Đáp án:** Không. Nó phục vụ theo dõi xung đột SSI và không tương đương row lock thông thường. Có thể có `40001` dù hai transaction không chờ nhau vì cập nhật các hàng khác nhau.

### Bài 22 — Retry thất bại nhiều lần

**Yêu cầu:** thiết kế hành vi sau năm lần bị `40001`.

**Đáp án:** Sau attempt cuối, rollback/cleanup và báo lỗi có thông tin phân loại; không tiếp tục vòng lặp vô hạn. Có thể dùng queue/job retry sau tùy SLA và idempotency, nhưng phải bảo đảm operation không bị thực hiện lặp ngoài ý muốn.

### Bài 23 — RLS và phạm vi tenant

**Câu hỏi:** Bật SERIALIZABLE có tự ngăn transaction tenant 10 cập nhật dữ liệu tenant 20 không?

**Đáp án:** Không. Serializable bảo đảm tính tuần tự hóa của các giao dịch đã commit, **không thay authorization**. Vẫn cần tenant predicates, role/RLS và kiểm soát quyền thích hợp.

### Bài 24 — Reset lab

Sau thử nghiệm, nếu chỉ muốn phục hồi hai bác sĩ:

```sql
UPDATE tx_retry_lab.on_call
SET on_duty = TRUE
WHERE doctor_id IN (1, 2);
```

Khi muốn dọn schema, **chỉ** thực hiện ở database thực hành sau khi xác minh không có dữ liệu khác phụ thuộc:

```sql
-- Không chạy trong database dùng chung nếu chưa kiểm tra:
-- DROP SCHEMA tx_retry_lab CASCADE;
```

---

## 24. Checklist trước khi bật retry ở production

1. **Xác định transaction boundary:** bao gồm mọi phép đọc, quyết định, thay đổi và `COMMIT`.
2. **Xác định isolation:** `READ COMMITTED`, `REPEATABLE READ` hay `SERIALIZABLE` phù hợp với invariant nào?
3. **Nhận diện lỗi bằng SQLSTATE:** ít nhất `40001`, cân nhắc `40P01` theo chính sách.
4. **Không retry một statement:** retry lại toàn bộ business transaction trên snapshot mới.
5. **Rollback và cleanup:** transaction lỗi không được rò lock/trạng thái sang attempt sau.
6. **Không giữ dữ liệu đọc cũ:** các biến Java phụ thuộc snapshot phải được tính lại.
7. **Đảm bảo retry được cả lỗi tại COMMIT:** không chỉ catch lỗi `UPDATE`.
8. **Giới hạn attempts/deadline:** có kế hoạch khi retry budget hết.
9. **Backoff+jitter:** tránh retry storm và tránh ngủ khi còn giữ connection/transaction.
10. **Bảo vệ side effects:** không gửi email, thu tiền hoặc gọi API ghi nhiều lần do retry.
11. **Có idempotency:** cùng operation/request phải được nhận diện qua nhiều lần gọi.
12. **Xử lý unknown commit outcome:** lỗi kết nối không đồng nghĩa chắc chắn rollback.
13. **Không retry mọi lỗi:** constraint violation, business rejection và timeout cần nhánh xử lý riêng.
14. **Gắn metric/log:** SQLSTATE, số attempts, tên nghiệp vụ, độ trễ, tỷ lệ hết retry.
15. **Kiểm thử hai connection:** phải tái tạo write skew và xác minh invariant sau retry.
16. **Tối ưu xung đột:** transaction ngắn, truy vấn đọc đúng phạm vi, index, lock order nhất quán.
17. **Kiểm tra framework proxy:** mỗi attempt thực sự có một transaction mới.
18. **Kiểm tra pool:** isolation/autocommit/session state không bị rò giữa connection reuse.
19. **Phân quyền:** SERIALIZABLE không thay role, tenant scoping hay RLS.
20. **Kiểm tra kết quả nghiệp vụ:** retry có thể trả từ chối hợp lệ sau khi đọc dữ liệu mới.

---

## 25. Tổng kết

`serialization_failure` với **SQLSTATE `40001`** là tín hiệu PostgreSQL **không cho phép một transaction tiếp tục/commit theo lịch đồng thời đã xảy ra** mà vẫn giữ tính đúng đắn của mức cô lập đang dùng.

Những nguyên tắc quan trọng:

- **`REPEATABLE READ` không chặn mọi write skew.** Hai transaction cùng đọc một tập rồi cập nhật các hàng khác nhau có thể làm sai bất biến đa hàng.
- **`SERIALIZABLE` dùng SSI** để phát hiện các lịch không tuần tự hóa được và có thể hủy một transaction bằng `40001`.
- **Retry phải bắt đầu từ transaction mới và thực hiện lại mọi phép đọc/quyết định/ghi**, không chỉ câu SQL cuối hay `COMMIT`.
- **Bắt lỗi ở cả statement lẫn COMMIT**, rollback/cleanup, giới hạn attempt và có backoff+jitter.
- **`40P01` deadlock** có thể cần retry toàn bộ transaction theo chính sách; **`23505`/`23P01`** và lỗi nghiệp vụ không được retry mù quáng.
- **Các side effect ngoài database không rollback cùng PostgreSQL**. Cần idempotency, transactional outbox hoặc thiết kế orchestration an toàn.
- **Mất kết nối khi COMMIT tạo kết quả không rõ**, khác với việc nhận `40001` xác định transaction bị từ chối.
- **Kiểm thử trên nhiều connection và đo bất biến cuối cùng** mới chứng minh cơ chế retry có ý nghĩa, không chỉ bắt được một exception.

**Nguyên tắc cuối cùng:** một serialization failure không phải lời mời “làm cho bằng được” kết quả đã tính trong lần thử cũ. Nó yêu cầu ứng dụng **đọc lại thực tại, đánh giá lại quyết định và chỉ commit nếu quyết định mới vẫn hợp lệ**.

### Tài liệu PostgreSQL chính thức

- [Transaction Isolation — Serializable Isolation Level](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Explicit Locking và Deadlocks](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Error Codes — SQLSTATE 40001 và 40P01](https://www.postgresql.org/docs/current/errcodes-appendix.html).
- [BEGIN](https://www.postgresql.org/docs/current/sql-begin.html), [COMMIT](https://www.postgresql.org/docs/current/sql-commit.html) và [ROLLBACK](https://www.postgresql.org/docs/current/sql-rollback.html).
- [SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
