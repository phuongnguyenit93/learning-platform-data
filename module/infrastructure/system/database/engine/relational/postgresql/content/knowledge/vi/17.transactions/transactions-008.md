# Write skew và kiểm chứng bất biến nghiệp vụ trong PostgreSQL

## 1. Vấn đề: từng transaction có vẻ đúng, dữ liệu cuối cùng lại sai

Một hệ thống trực bệnh viện quy định: **mỗi ca trực phải luôn có ít nhất một bác sĩ đang trực**.

Ca tối có hai bác sĩ, An và Bình. An kiểm tra và thấy còn hai bác sĩ nên tự cho phép mình ngừng trực. Cùng thời điểm đó, Bình cũng kiểm tra và thấy hai bác sĩ nên tự cho phép mình ngừng trực. Mỗi người chỉ sửa bản ghi của chính mình. Nếu cả hai giao dịch commit thành công, ca tối không còn bác sĩ nào trực.

Đây là **write skew**: các transaction đồng thời cùng đọc một tập dữ liệu liên quan để quyết định, sau đó ghi những hàng khác nhau; kết quả commit có thể vi phạm một **bất biến nghiệp vụ xuyên hàng** (*cross-row business invariant*).

PostgreSQL có MVCC và nhiều mức cô lập transaction, nhưng:

- `READ COMMITTED` có thể xảy ra write skew.
- `REPEATABLE READ` của PostgreSQL, triển khai dựa trên **snapshot isolation**, vẫn có thể xảy ra write skew.
- `SERIALIZABLE` dùng cơ chế phát hiện các phụ thuộc nguy hiểm để ngăn những giao dịch thành công tạo ra kết quả không thể tuần tự hóa; một transaction có thể bị hủy với SQLSTATE `40001` và phải retry toàn bộ.

Điểm quan trọng không phải một câu `UPDATE` riêng lẻ có sai hay không, mà là **quy tắc chung có được duy trì trong mọi tổ hợp giao dịch đồng thời hay không**.

### Mục tiêu bài học

Sau bài này, bạn sẽ:

1. Phát biểu bất biến nghiệp vụ bằng một điều kiện kiểm chứng được.
2. Tái hiện write skew trong hai session PostgreSQL độc lập.
3. Giải thích vì sao snapshot ổn định ở `REPEATABLE READ` chưa đủ.
4. Phân biệt write skew với lost update, phantom và deadlock.
5. Hiểu cách `SERIALIZABLE`/SSI phát hiện phụ thuộc đọc–ghi.
6. Retry **toàn bộ transaction** khi gặp lỗi `40001`.
7. Dùng khóa một hàng điều phối chung tại `READ COMMITTED`.
8. Nhận biết giới hạn của `FOR UPDATE`, advisory lock, CHECK, UNIQUE, trigger và foreign key.
9. Kiểm chứng bất biến sau commit bằng SQL, kể cả ca không có hàng phân công.
10. Thiết kế bài test concurrency có barrier và tiêu chí nghiệm thu.
11. Đưa vấn đề vào bối cảnh hệ thống đặt chỗ, tồn kho, quyền quản trị và ứng dụng Java.

## 2. Bất biến nghiệp vụ cần được định nghĩa chính xác

Một **bất biến** là điều kiện phải đúng ở các trạng thái dữ liệu đã commit hợp lệ.

Trong lab, gọi:

- `S` là tập các ca trực hiện có.
- `D(s)` là tập các bác sĩ được phân công vào ca `s`.
- `active_count(s)` là số bác sĩ trong `D(s)` có `is_on_call = TRUE`.

Bất biến:

```text
Với mọi ca s thuộc S:
    active_count(s) >= 1
```

Một trạng thái hợp lệ:

```text
Ca 1:
    DR_A: TRUE
    DR_B: TRUE
    active_count = 2
```

Một trạng thái vẫn hợp lệ:

```text
Ca 1:
    DR_A: FALSE
    DR_B: TRUE
    active_count = 1
```

Một trạng thái không hợp lệ:

```text
Ca 1:
    DR_A: FALSE
    DR_B: FALSE
    active_count = 0  <-- VI PHẠM
```

Cần phân biệt **điều kiện trên một hàng** và **bất biến trên nhiều hàng**. `CHECK (stock >= 0)` có thể bảo vệ một giá trị tồn kho trong một hàng. Nhưng `COUNT(*) FILTER (WHERE is_on_call) >= 1` đòi xem nhiều hàng và có thể bị ảnh hưởng bởi những transaction cập nhật các hàng khác nhau.

### 2.1. Tại sao viết bất biến trước SQL?

Bởi vì nếu chỉ nhìn từng câu:

```sql
UPDATE doctors
SET is_on_call = FALSE
WHERE doctor_id = 'DR_A';
```

câu SQL hoàn toàn có thể hợp lệ về cú pháp, kiểu dữ liệu, khóa ngoại và quyền truy cập. Điều sai là trạng thái **kết hợp sau các giao dịch**, không phải bản thân thao tác sửa boolean.

Việc viết rõ invariant giúp xác định:

- Tập hàng nào phải được đọc để ra quyết định.
- Các transaction nào có thể tương tác.
- Điều kiện nào phải đúng sau commit.
- Cơ chế khóa hoặc isolation phải bảo vệ **đơn vị nghiệp vụ** nào.
- Bài test cần kiểm tra trạng thái nào.

## 3. Chuẩn bị hai bảng lab

Chỉ thực hành trong database được phép thay đổi. Bạn cần **hai connection riêng biệt**, không chỉ hai cửa sổ dùng chung một connection.

### 3.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS ws218;

CREATE TABLE ws218.shifts (
    shift_id integer PRIMARY KEY,
    shift_name text NOT NULL,
    version bigint NOT NULL DEFAULT 0
);

CREATE TABLE ws218.shift_doctors (
    shift_id integer NOT NULL
        REFERENCES ws218.shifts(shift_id),
    doctor_id text NOT NULL,
    is_on_call boolean NOT NULL,
    PRIMARY KEY (shift_id, doctor_id)
);
```

`shifts` lưu một hàng đại diện cho mỗi ca. Cột `version` sẽ được dùng khi nói đến **hàng khóa điều phối**.

`shift_doctors` có khóa chính kép `(shift_id, doctor_id)` để một bác sĩ chỉ có một hàng phân công trong cùng ca.

### 3.2. Dữ liệu ban đầu

```sql
INSERT INTO ws218.shifts(shift_id, shift_name)
VALUES (1, 'Ca tối');

INSERT INTO ws218.shift_doctors(
    shift_id, doctor_id, is_on_call
)
VALUES
    (1, 'DR_A', TRUE),
    (1, 'DR_B', TRUE);
```

Kiểm tra:

```sql
SELECT shift_id, doctor_id, is_on_call
FROM ws218.shift_doctors
ORDER BY shift_id, doctor_id;
```

| shift_id | doctor_id | is_on_call |
|---:|---|---|
| 1 | DR_A | true |
| 1 | DR_B | true |

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả ban đầu: **2**.

Nếu các bảng đã tồn tại do bạn từng chạy lab, đừng tiếp tục chèn trùng khóa. Hãy tạo database/schema thử nghiệm mới hoặc reset fixture theo quy trình được phép. Không tự xóa bảng chưa rõ chủ sở hữu.

## 4. Truy vấn kiểm chứng bất biến: đừng bỏ sót ca rỗng

Một query chỉ nhóm trên bảng `shift_doctors` không trả hàng cho ca hoàn toàn không có bác sĩ. Muốn kiểm tra **mọi ca**, hãy bắt đầu từ `shifts`:

```sql
SELECT
    s.shift_id,
    s.shift_name,
    COUNT(d.doctor_id)
      FILTER (WHERE d.is_on_call IS TRUE)
      AS active_doctors
FROM ws218.shifts AS s
LEFT JOIN ws218.shift_doctors AS d
    ON d.shift_id = s.shift_id
GROUP BY s.shift_id, s.shift_name
ORDER BY s.shift_id;
```

Ban đầu:

| shift_id | shift_name | active_doctors |
|---:|---|---:|
| 1 | Ca tối | 2 |

Lọc riêng các ca vi phạm:

```sql
SELECT
    s.shift_id,
    s.shift_name,
    COUNT(d.doctor_id)
      FILTER (WHERE d.is_on_call IS TRUE)
      AS active_doctors
FROM ws218.shifts AS s
LEFT JOIN ws218.shift_doctors AS d
    ON d.shift_id = s.shift_id
GROUP BY s.shift_id, s.shift_name
HAVING COUNT(d.doctor_id)
         FILTER (WHERE d.is_on_call IS TRUE) = 0
ORDER BY s.shift_id;
```

Khi bất biến đúng, câu này trả **0 hàng**. Khi có ca không người trực, nó trả một hàng với số người trực bằng 0.

Có thể viết cùng mục tiêu bằng `NOT EXISTS`:

```sql
SELECT s.shift_id, s.shift_name
FROM ws218.shifts AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM ws218.shift_doctors AS d
    WHERE d.shift_id = s.shift_id
      AND d.is_on_call IS TRUE
);
```

Cách `NOT EXISTS` cũng tìm được ca không có bất kỳ hàng bác sĩ nào.

**Chú ý:** `COUNT(*)` sau `LEFT JOIN` vẫn đếm một hàng NULL mở rộng cho ca rỗng. Dùng `COUNT(d.doctor_id) FILTER (...)` hoặc `NOT EXISTS` mới đúng yêu cầu.

## 5. Nếu chạy tuần tự, không thể cho cả hai ngừng trực

Giả sử logic nghiệp vụ:

```text
BEGIN
    active_count = SELECT COUNT(*) WHERE is_on_call
    nếu active_count <= 1:
        không cho người hiện tại ngừng trực
    nếu active_count > 1:
        UPDATE hàng của người hiện tại thành FALSE
COMMIT
```

Nếu A hoàn thành trước B:

1. A đọc count=2, đổi DR_A thành FALSE, commit.
2. B đọc count=1, bị từ chối.
3. Kết quả: DR_B vẫn trực.

Nếu B hoàn thành trước A:

1. B đọc count=2, đổi DR_B thành FALSE, commit.
2. A đọc count=1, bị từ chối.
3. Kết quả: DR_A vẫn trực.

**Không có thứ tự chạy tuần tự hợp lệ nào cho phép cả hai rời ca** nếu mỗi transaction đều áp dụng quy tắc “sau khi tôi rời vẫn phải có người trực”.

Vì thế, nếu hai transaction đồng thời đều thành công và để lại count=0, kết quả đó là một **serialization anomaly**.

## 6. Tái hiện write skew ở REPEATABLE READ

Đảm bảo hai hàng DR_A và DR_B đang TRUE và không còn transaction lab cũ đang mở.

Mở hai phiên riêng:

- **Session A** thao tác cho `DR_A`.
- **Session B** thao tác cho `DR_B`.

Chạy **xen kẽ đúng thứ tự**. Nếu chạy hết Session A trước rồi mới Session B thì đó chỉ là thực thi tuần tự, không tái hiện được lỗi.

### Bước 1 — A bắt đầu và đọc

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SHOW transaction_isolation;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả:

```text
transaction_isolation = repeatable read
active_doctors = 2
```

Giữ transaction A mở.

### Bước 2 — B bắt đầu và cũng đọc

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả: **2**.

Bây giờ **cả A và B** đều đã ra quyết định dựa trên trạng thái ban đầu có hai bác sĩ trực.

### Bước 3 — A cập nhật hàng DR_A

**Session A:**

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE
RETURNING shift_id, doctor_id, is_on_call;
```

Kết quả: DR_A đã FALSE trong transaction A.

**Chưa COMMIT.**

### Bước 4 — B cập nhật hàng DR_B

**Session B:**

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
  AND is_on_call IS TRUE
RETURNING shift_id, doctor_id, is_on_call;
```

Kết quả: DR_B đã FALSE trong transaction B.

Hai câu UPDATE ghi **hai hàng khác nhau**, không có xung đột cập nhật trực tiếp lên cùng hàng.

### Bước 5 — Mỗi transaction tự kiểm tra lại

**Session A:**

```sql
SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

A thường thấy:

```text
DR_A = FALSE  (do chính A cập nhật)
DR_B = TRUE   (theo snapshot của A)
active_doctors = 1
```

**Session B:** chạy cùng hai SELECT.

B thường thấy:

```text
DR_A = TRUE   (theo snapshot của B)
DR_B = FALSE  (do chính B cập nhật)
active_doctors = 1
```

**Cả hai đều tự thấy invariant đúng** trong snapshot riêng. Việc chạy thêm SELECT trước COMMIT không sửa được lỗi nếu vẫn dựa trên snapshot cũ.

### Bước 6 — Cả hai COMMIT

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
COMMIT;
```

Với lịch thực thi này ở PostgreSQL `REPEATABLE READ`, **cả hai có thể COMMIT thành công**.

Dùng một kết nối mới sau khi hai phiên kết thúc:

```sql
SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả cuối:

| doctor_id | is_on_call |
|---|---|
| DR_A | false |
| DR_B | false |

`active_doctors = 0`. **Bất biến bị phá vỡ.**

### Lịch thực thi đầy đủ

| Thời điểm | Session A | Session B |
|---:|---|---|
| 1 | BEGIN REPEATABLE READ | — |
| 2 | SELECT count → 2 | — |
| 3 | — | BEGIN REPEATABLE READ |
| 4 | — | SELECT count → 2 |
| 5 | UPDATE DR_A → FALSE | — |
| 6 | — | UPDATE DR_B → FALSE |
| 7 | SELECT count → 1 theo snapshot A | — |
| 8 | — | SELECT count → 1 theo snapshot B |
| 9 | COMMIT | — |
| 10 | — | COMMIT |
| Sau cùng | **0 người trực** | **Invariant sai** |

Điều kiện quyết định để tái hiện là **cả hai SELECT ban đầu phải được thực hiện trước khi một transaction khác commit**.

## 7. Vì sao PostgreSQL cho phép trạng thái đó?

`REPEATABLE READ` của PostgreSQL được triển khai theo **snapshot isolation**:

- Transaction đọc snapshot ổn định, bắt đầu quanh câu truy vấn/thao tác dữ liệu đầu tiên.
- Transaction nhìn thấy thay đổi của **chính nó**.
- Transaction không nhìn thấy thay đổi của giao dịch khác commit sau snapshot.
- PostgreSQL ngăn những kiểu xung đột cập nhật trực tiếp lên **cùng hàng** trong nhiều tình huống.
- Nhưng hai transaction có thể cập nhật **hai hàng khác nhau** và đều commit.

Một snapshot nhất quán không đồng nghĩa các kết quả của **nhiều transaction đồng thời** nhất quán với một lịch tuần tự hợp lệ.

Trong ví dụ, snapshot của A và B đều đúng ở thời điểm đọc. Vấn đề là cả hai **ra quyết định từ thông tin không còn đủ khi các giao dịch kết hợp**.

## 8. Chu trình phụ thuộc đọc–ghi

Trong lịch vừa thử:

- A đọc trạng thái của DR_B là TRUE; B ghi DR_B thành FALSE.
- B đọc trạng thái của DR_A là TRUE; A ghi DR_A thành FALSE.

Có thể biểu diễn:

```text
A đọc DR_B  ----(B viết DR_B)---->  B
 ^                                      |
 |                                      |
 +----(A viết DR_A)---- B đọc DR_A -----+

Các phụ thuộc đọc–ghi tạo thành chu trình:

           A ---- rw ----> B
           ^              |
           |              |
           +---- rw ------+
```

Nếu A tuần tự trước B, B phải thấy DR_A đã FALSE và từ chối rời ca. Nếu B tuần tự trước A, A phải thấy DR_B đã FALSE và từ chối. **Không có thứ tự tuần tự nào tương ứng với hai quyết định “được rời ca” cùng thành công**.

Chính vì vậy write skew được phân loại là một **serialization anomaly**, không phải chỉ là “hai thao tác ghi nhanh quá”.

## 9. Phân biệt write skew với lost update và các hiện tượng khác

| Hiện tượng | Đặc điểm chính | Ví dụ |
|---|---|---|
| Dirty read | Đọc giá trị chưa commit của transaction khác | Đọc số dư từ transaction có thể rollback |
| Nonrepeatable read | Đọc cùng hàng hai lần được giá trị khác do commit xen vào | Xem giá 100 rồi giá 120 |
| Phantom read | Lặp truy vấn điều kiện có thêm/bớt hàng đủ điều kiện | COUNT bookings thay đổi vì INSERT mới |
| Lost update | Những cập nhật cùng một thực thể bị mất/ghi đè | Hai client cùng sửa một số tồn dựa trên số cũ |
| Write skew | Hai transaction đọc điều kiện chung và ghi các hàng khác nhau | Hai bác sĩ cùng ngừng trực |
| Deadlock | Các transaction chờ lock theo vòng | A giữ lock X chờ Y, B giữ Y chờ X |

### 9.1. Tại sao write skew không phải lost update?

Trong lab, A cập nhật DR_A, B cập nhật DR_B. Không có hàng nào bị một câu UPDATE khác ghi đè. **Cả hai thay đổi đều được ghi**, nhưng kết quả tổng hợp lại vi phạm quy tắc.

### 9.2. REPEATABLE READ không có phantom thì sao vẫn write skew?

PostgreSQL `REPEATABLE READ` dùng snapshot ổn định, nên không có phantom read thông thường theo ngữ nghĩa nhiều SELECT trong cùng transaction. Nhưng **serialization anomaly vẫn có thể xảy ra**.

Không có phantom hoặc nonrepeatable read **không đủ chứng minh serializable**.

## 10. Các mức cô lập và rủi ro write skew

PostgreSQL nhận các mức cô lập chuẩn sau:

| Isolation | Cách đọc chính | Write skew kiểu lab |
|---|---|---|
| `READ UNCOMMITTED` | Trong PostgreSQL hoạt động như READ COMMITTED | Có thể |
| `READ COMMITTED` | Snapshot theo từng statement | Có thể |
| `REPEATABLE READ` | Snapshot ổn định trong transaction | Có thể |
| `SERIALIZABLE` | Snapshot + cơ chế bảo vệ tính tuần tự hóa | Không được phép cho cả hai commit với kết quả không tuần tự hóa |

Ở `READ COMMITTED`, hai transaction cùng SELECT count=2 trước khi ai UPDATE vẫn có thể tạo write skew. Nếu B SELECT sau A commit thì B thường thấy count=1 và từ chối, nhưng **tính đúng không được dựa vào may mắn của thứ tự chạy**.

Ở `REPEATABLE READ`, snapshot của B tiếp tục nhìn dữ liệu cũ sau khi A commit nếu snapshot B đã được thiết lập trước đó. Vì thế nguy cơ được thể hiện rất rõ.

### 10.1. Thiết lập isolation trước khi truy vấn

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- SELECT/UPDATE bên trong transaction

COMMIT;
```

Hoặc:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Các query sau đây chạy ở mức đã chọn.

COMMIT;
```

Không thể lấy một snapshot, đưa ra quyết định rồi mới nâng isolation trong cùng transaction để “sửa” quyết định đó. Thiết lập isolation đúng ranh giới giao dịch, trước các truy vấn nghiệp vụ.

## 11. Reset dữ liệu cho thí nghiệm tiếp theo

Chỉ sau khi cả hai transaction thử nghiệm đã kết thúc:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = TRUE
WHERE shift_id = 1
  AND doctor_id IN ('DR_A', 'DR_B');

SELECT doctor_id, is_on_call
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id;
```

Xác nhận hai hàng đều TRUE. Không reset khi có transaction lab còn mở; việc thay trạng thái giữa thí nghiệm khiến kết quả khó diễn giải.

## 12. SERIALIZABLE: chặn write skew bằng SSI

PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để phát hiện những phụ thuộc đọc–ghi khiến kết quả các transaction không còn tuần tự hóa được.

SSI không có nghĩa mọi transaction phải chờ nhau theo kiểu khóa bảng toàn cục. Chúng có thể đọc/ghi đồng thời nhưng một transaction bị **serialization failure** nếu lịch commit không được chấp nhận.

### 12.1. Hai session thực hành

Sau reset, **Session A**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả: 2.

**Session B**:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Kết quả: 2.

**Session A**:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE;
```

**Session B**:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
  AND is_on_call IS TRUE;
```

Sau đó thử COMMIT ở A rồi B:

```sql
COMMIT;
```

### 12.2. Kết quả

PostgreSQL **không cho phép cả hai commit thành công** và để lại một lịch không thể tuần tự hóa.

Một transaction có thể gặp lỗi dạng:

```text
ERROR: could not serialize access due to read/write dependencies among transactions
SQLSTATE: 40001 (serialization_failure)
```

Thông báo cụ thể và vị trí lỗi có thể khác; lỗi có thể xuất hiện khi thực hiện một câu SQL hoặc tại `COMMIT`. **Không cam kết session A hay B chắc chắn bị hủy**.

Transaction lỗi phải bị rollback. Transaction thành công có thể cho một bác sĩ nghỉ; bác sĩ kia vẫn trực.

### 12.3. Vì sao SERIALIZABLE bảo vệ được?

SSI theo dõi phụ thuộc đọc và những thay đổi có thể làm đảo ngược kết quả predicate đã đọc. Trong ví dụ, A và B đọc tập bác sĩ đang trực rồi mỗi người làm thay đổi tập mà người kia đã đọc.

Thay vì chấp nhận cả hai commit, PostgreSQL hủy một giao dịch nguy hiểm, khiến tập các giao dịch đã commit vẫn tương thích với tính tuần tự hóa.

**Lưu ý:** serialization failure không có nghĩa DB bị hỏng; đó là một cơ chế chủ động bảo vệ tính đúng đắn.

## 13. SQLSTATE 40001 và retry toàn transaction

Khi gặp `40001`, không nên chỉ chạy lại `UPDATE`. Phải bắt đầu transaction **mới** và **đọc lại count** để quyết định lại.

Tại sao? Giả sử A commit trước và ngừng trực. Khi B retry:

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1 AND is_on_call IS TRUE;
```

Kết quả hiện tại là **1**, không phải 2. B phải **từ chối ngừng trực**.

Nếu B giữ quyết định cũ “đã thấy count=2” rồi chạy lại UPDATE, invariant có thể bị vi phạm.

### 13.1. Thuật toán retry

```text
MAX_ATTEMPTS = 3

for attempt in 1..MAX_ATTEMPTS:
    BEGIN SERIALIZABLE

    count = đọc số bác sĩ đang trực trong ca

    if count <= 1:
        kết thúc transaction
        return LAST_DOCTOR_CANNOT_LEAVE

    changed = UPDATE bác sĩ hiện tại
              WHERE is_on_call = TRUE

    nếu changed = 0:
        kết thúc transaction
        return NOT_ON_CALL_OR_NOT_FOUND

    COMMIT
    return SUCCESS

    nếu lỗi SQLSTATE 40001:
        ROLLBACK transaction thất bại
        backoff có giới hạn
        retry lại TỪ ĐẦU (kể cả đọc và quyết định)

    nếu lỗi khác:
        ROLLBACK
        xử lý theo nguyên nhân

nếu quá số lần retry:
    trả lỗi cạnh tranh tạm thời cho phía gọi
```

### 13.2. Những lỗi cần phân biệt

| SQLSTATE | Tên | Ý nghĩa |
|---|---|---|
| `40001` | `serialization_failure` | Retry toàn transaction |
| `40P01` | `deadlock_detected` | Có thể retry toàn transaction theo chính sách |
| `55P03` | `lock_not_available` | Không lấy được lock theo NOWAIT/timeout; xử lý riêng |
| `23505` | `unique_violation` | Không tự động retry mọi trường hợp, thường là xung đột dữ liệu |
| `23514` | `check_violation` | Ràng buộc CHECK thất bại; thường cần sửa logic/data |

Hãy kiểm tra **SQLSTATE**, không chỉ tìm câu chữ trong exception, vì thông điệp có thể thay đổi.

### 13.3. Không retry vô hạn

Đặt giới hạn retry, thời gian chờ/backoff (thường có jitter), timeout và metric. Nếu tranh chấp quá cao, người dùng cần được biết thao tác chưa hoàn tất thay vì một request quay vòng vô tận.

## 14. Ví dụ Java/JDBC retry theo transaction

Đây là ví dụ lõi; `DataSource` được cấu hình sẵn. Mỗi lần thử dùng **một connection và transaction mới**.

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import javax.sql.DataSource;

public final class ShiftService {
    private final DataSource dataSource;

    public ShiftService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public boolean stepOff(int shiftId, String doctorId)
            throws SQLException {

        for (int attempt = 1; attempt <= 3; attempt++) {
            try (Connection c = dataSource.getConnection()) {
                c.setTransactionIsolation(
                    Connection.TRANSACTION_SERIALIZABLE);
                c.setAutoCommit(false);

                try {
                    int activeCount;
                    try (PreparedStatement ps =
                             c.prepareStatement("""
                                 SELECT COUNT(*)
                                 FROM ws218.shift_doctors
                                 WHERE shift_id = ?
                                   AND is_on_call IS TRUE
                                 """)) {
                        ps.setInt(1, shiftId);
                        try (ResultSet rs = ps.executeQuery()) {
                            rs.next();
                            activeCount = rs.getInt(1);
                        }
                    }

                    if (activeCount <= 1) {
                        c.commit();
                        return false;
                    }

                    int changed;
                    try (PreparedStatement ps =
                             c.prepareStatement("""
                                 UPDATE ws218.shift_doctors
                                 SET is_on_call = FALSE
                                 WHERE shift_id = ?
                                   AND doctor_id = ?
                                   AND is_on_call IS TRUE
                                 """)) {
                        ps.setInt(1, shiftId);
                        ps.setString(2, doctorId);
                        changed = ps.executeUpdate();
                    }

                    c.commit();
                    return changed == 1;

                } catch (SQLException ex) {
                    try {
                        c.rollback();
                    } catch (SQLException rollbackFailure) {
                        ex.addSuppressed(rollbackFailure);
                    }

                    if ("40001".equals(ex.getSQLState())
                            && attempt < 3) {
                        // Mở transaction mới ở vòng kế tiếp.
                        continue;
                    }
                    throw ex;
                }
            }
        }
        throw new SQLException("Không hoàn tất transaction");
    }
}
```

Ví dụ ưu tiên diễn đạt cơ chế; production cần thêm:

- Xác thực quyền bác sĩ và tenant/shift.
- Phân biệt doctor không tồn tại, đã nghỉ, không đúng ca.
- Không dùng response thành công trước COMMIT.
- Cấu hình transaction manager/pool để isolation được thiết lập đúng trước khi chạy query; phục hồi trạng thái connection khi trả pool theo cơ chế của pool.
- Retry giới hạn, backoff, timeout, metric.
- Xử lý lỗi kết nối hoặc commit outcome không rõ bằng idempotency/đối soát.
- Đảm bảo **mọi đường ghi liên quan** cũng tôn trọng invariant.

Nếu dùng framework transaction, hãy cấu hình isolation/retry tại **ranh giới transaction** của framework, không tự mở transaction chồng lên một transaction đã có.

## 15. Khóa hàng điều phối chung ở READ COMMITTED

Một giải pháp khác là **buộc mọi transaction sửa cùng một ca phải tranh chấp một hàng chung**, thay vì chỉ sửa hàng bác sĩ của mình.

Bảng `ws218.shifts` đã có hàng `shift_id = 1`. Ta dùng hàng này làm **guard row**.

Quy trình:

1. BEGIN ở `READ COMMITTED`.
2. `SELECT ... FOR UPDATE` trên hàng shift 1.
3. Khi đã lấy lock, **đọc lại count trong một SELECT riêng**.
4. Chỉ tắt bác sĩ nếu count > 1 và bác sĩ đang trực.
5. COMMIT hoặc ROLLBACK nhả khóa.

### 15.1. Session A

Reset cả hai bác sĩ về TRUE. A chạy:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM ws218.shifts
WHERE shift_id = 1
FOR UPDATE;
```

A đã khóa guard row. Tiếp tục:

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Count=2. A được phép:

```sql
UPDATE ws218.shift_doctors
SET is_on_call = FALSE
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
  AND is_on_call IS TRUE;

COMMIT;
```

### 15.2. Session B

Trong khi A chưa COMMIT, B chạy:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT shift_id
FROM ws218.shifts
WHERE shift_id = 1
FOR UPDATE;
```

B phải **chờ guard row** do A đang khóa.

Sau khi A COMMIT, B lấy được lock và chạy một câu **SELECT mới**:

```sql
SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;
```

Ở `READ COMMITTED`, SELECT mới sẽ thấy update đã commit của A. Count=1, nên **B không được UPDATE DR_B**.

```sql
ROLLBACK;
```

Kết quả: DR_A=FALSE, DR_B=TRUE. Invariant được giữ.

### 15.3. Vì sao giải pháp này đúng theo protocol?

Hai transaction không thể đồng thời vượt qua cùng guard row lock. B phải chờ A kết thúc, rồi đọc snapshot mới của statement SELECT sau khi lấy lock.

**Điều kiện bắt buộc:** mọi writer ảnh hưởng số bác sĩ trực trong cùng ca phải khóa cùng guard row trước khi ra quyết định. Nếu một batch job khác cập nhật `shift_doctors` mà bỏ qua protocol, invariant vẫn có thể bị phá.

### 15.4. Cẩn trọng khi áp dụng ở REPEATABLE READ

Chỉ khóa hàng chung **không có nghĩa snapshot REPEATABLE READ được làm mới sau khi chờ**. Nếu B đã thiết lập snapshot cũ trước khi A commit, rồi chờ một guard row không bị thay đổi, B có thể tiếp tục nhìn thấy số bác sĩ cũ.

Bởi vậy, mẫu `FOR UPDATE guard → SELECT count` ở trên được thiết kế cụ thể cho **READ COMMITTED**. Với REPEATABLE READ/SERIALIZABLE, cần xét thêm **xung đột ghi hoặc serialization retry**.

## 16. Vì sao khóa riêng DR_A và DR_B không đủ?

Một cách sửa dễ mắc:

**A:**

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND doctor_id = 'DR_A'
FOR UPDATE;
```

**B:**

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND doctor_id = 'DR_B'
FOR UPDATE;
```

A và B đang khóa **hai hàng khác nhau**, không có giao điểm buộc hai transaction chờ nhau. Cả hai vẫn có thể dựa vào việc “bác sĩ kia còn trực” trong snapshot.

Nếu khóa toàn bộ danh sách bác sĩ:

```sql
SELECT doctor_id
FROM ws218.shift_doctors
WHERE shift_id = 1
ORDER BY doctor_id
FOR UPDATE;
```

thì các transaction có thể tranh chấp các hàng giống nhau. Tuy nhiên:

- Phải khóa hàng cơ sở, không phải `SELECT COUNT(*) ... FOR UPDATE` trên aggregate.
- Khi tập bác sĩ có thể INSERT/DELETE, chỉ khóa những hàng hiện tại chưa chắc bảo vệ tất cả predicate.
- Cần thứ tự lock ổn định để hạn chế deadlock.
- Với REPEATABLE READ, vẫn phải hiểu snapshot và lỗi serialization.
- Khóa nhiều hàng có thể tốn chi phí hơn một guard row.

Lựa chọn cơ chế phải phù hợp với **đơn vị của bất biến**.

## 17. Tạo write–write conflict chung bằng guard version

Bảng `shifts` có cột `version`. Thay vì chỉ SELECT FOR UPDATE, mọi writer có thể **thực sự UPDATE** cùng guard row:

```sql
UPDATE ws218.shifts
SET version = version + 1
WHERE shift_id = 1
RETURNING version;
```

Khi dùng ở đầu transaction:

- Ở READ COMMITTED, transaction cạnh tranh phải chờ update cùng hàng; câu SELECT count **sau đó** đọc snapshot mới.
- Ở REPEATABLE READ, nếu snapshot đã cũ và một transaction khác đã sửa hàng guard sau snapshot, PostgreSQL có thể báo `40001`. Ứng dụng phải retry toàn bộ.
- Hai writer cùng ca bị buộc có một điểm xung đột ghi, thay vì chỉ ghi hai hàng bác sĩ riêng.

Ví dụ các bước cho ứng dụng:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE ws218.shifts
SET version = version + 1
WHERE shift_id = 1
RETURNING version;

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;

-- Chỉ khi count > 1 và bác sĩ đang trực:
-- UPDATE ws218.shift_doctors SET is_on_call=FALSE ...

COMMIT;
```

**Không chạy UPDATE bác sĩ vô điều kiện:** ứng dụng phải điều khiển nhánh theo count vừa đọc.

Hạn chế: mọi writer phải theo protocol; hot row có thể gây contention và WAL/bloat. Khóa theo ca thay vì một hàng global để các ca độc lập không chặn nhau.

## 18. Advisory lock là giải pháp gì?

PostgreSQL hỗ trợ **advisory locks** theo khóa logic do application định nghĩa:

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT pg_advisory_xact_lock(218, 1);

SELECT COUNT(*) AS active_doctors
FROM ws218.shift_doctors
WHERE shift_id = 1
  AND is_on_call IS TRUE;

-- Chỉ UPDATE nếu count > 1.
-- COMMIT hoặc ROLLBACK khi hoàn tất.
```

`pg_advisory_xact_lock` là khóa cấp transaction, tự nhả khi transaction kết thúc. Cặp số `(218,1)` chỉ là namespace/ID minh họa; ứng dụng phải quy hoạch lock key không xung đột chức năng khác.

**Quan trọng:**

- Advisory lock mang tính **tự nguyện**. SQL trực tiếp sửa bảng không tự bắt buộc phải lấy lock.
- Session-level advisory lock có vòng đời khác; dùng sai với pool có thể giữ lock lâu hơn mong đợi.
- Advisory lock **không làm mới snapshot REPEATABLE READ cũ**.
- Khi một transaction cần nhiều lock, phải có thứ tự lấy lock nhất quán để giảm deadlock.
- Không sinh số lượng lock không kiểm soát; tài nguyên lock manager có giới hạn.

## 19. Constraint có thể bảo vệ được điều gì?

Mỗi loại constraint có phạm vi riêng:

| Constraint/cơ chế | Thường bảo vệ | Có trực tiếp bảo vệ “ít nhất một bác sĩ trực” không? |
|---|---|---|
| `CHECK` | Điều kiện trên một hàng | Không trực tiếp |
| `NOT NULL` | Một cột không NULL | Không |
| `UNIQUE` | Không trùng khóa, “tối đa một” theo mô hình | Không |
| Partial UNIQUE | Tối đa một bản ghi thỏa predicate | Không |
| Foreign key | Tham chiếu hợp lệ | Không tự bảo đảm trạng thái trực |
| Exclusion constraint | Không có cặp hàng xung đột theo toán tử khai báo | Không trực tiếp |
| Trigger kiểm tra COUNT | Có thể diễn đạt quy tắc trong DB | **Vẫn có race** nếu không đồng bộ |
| SERIALIZABLE + retry | Quyết định nhiều hàng phải tuần tự hóa được | Có thể bảo vệ nếu toàn bộ workflow tuân thủ |

### 19.1. Tại sao CHECK không đủ?

`CHECK (is_on_call IN (TRUE,FALSE))` chỉ bảo đảm giá trị boolean hợp lệ. Nó không biết các hàng khác trong cùng ca.

Một CHECK chứa subquery đếm các hàng khác không phải cách khai báo cross-row constraint thông thường được PostgreSQL hỗ trợ/khuyến nghị. Không giấu truy vấn bảng khác trong một hàm CHECK rồi mặc định nó an toàn dưới concurrent writes.

### 19.2. Tại sao partial UNIQUE không đủ?

Một partial unique index có thể bảo đảm:

> Mỗi ca có **tối đa một** người giữ vai trò chính.

Nhưng nó không tạo ra người giữ vai trò chính khi **không có ai**. “Tối đa một” và “ít nhất một” khác nhau về hướng ràng buộc.

### 19.3. Thiết kế lại dữ liệu

Nếu quy tắc nghiệp vụ thật sự là “mỗi ca phải có một bác sĩ **được chỉ định làm người chịu trách nhiệm**”, có thể đặt một cột tham chiếu bác sĩ không NULL trên bảng `shifts` và dùng khóa ngoại phù hợp.

Tuy nhiên, **có người chịu trách nhiệm** không hoàn toàn đồng nghĩa **có người đang trực**. Nếu bác sĩ được chỉ định có thể bị vô hiệu hóa hoặc rời ca ở bảng khác, mô hình phải bảo vệ thêm mối quan hệ ấy. Chỉ đổi schema mà chưa chứng minh quy tắc tương đương chưa đủ.

## 20. Trigger kiểm tra COUNT cũng có thể mắc write skew

Một người có thể đề xuất:

> “Viết BEFORE UPDATE trigger: nếu sau khi người này ngừng trực vẫn còn ít nhất một người thì cho UPDATE.”

Nếu trigger chỉ SELECT COUNT trên tập bác sĩ ở snapshot của transaction:

- Trigger trong A có thể thấy DR_B còn trực.
- Trigger trong B có thể thấy DR_A còn trực.
- A cập nhật DR_A, B cập nhật DR_B.
- Hai transaction vẫn có thể commit ở REPEATABLE READ và phá invariant.

**Trigger tập trung hóa logic nhưng không tự tạo tính serializable.** Muốn dùng trigger để bảo vệ invariant, phải phối hợp isolation/khóa/thiết kế dữ liệu có tính đúng dưới concurrency; đồng thời kiểm thử cùng lúc nhiều writer.

Một deferred trigger hoặc việc “kiểm tra muộn” cũng không tự chữa được một truy vấn COUNT vẫn dùng snapshot thiếu đồng bộ. Cần chứng minh cơ chế không để hai transaction qua cửa kiểm tra đồng thời.

## 21. Một ví dụ khác: đặt chỗ vượt sức chứa

Giả sử một phòng có `capacity=1`, bảng booking ban đầu trống. Hai request đặt chỗ song song:

```text
T_A: SELECT COUNT(*) confirmed bookings -> 0
T_B: SELECT COUNT(*) confirmed bookings -> 0

T_A: INSERT booking A (id riêng, CONFIRMED)
T_B: INSERT booking B (id riêng, CONFIRMED)

T_A COMMIT
T_B COMMIT

Kết quả: 2 bookings trong phòng capacity=1
```

Hai transaction đọc **predicate** “những booking CONFIRMED của phòng”, rồi INSERT hai hàng khác nhau. Có thể không có xung đột UNIQUE nếu mỗi booking có ID riêng.

Một UNIQUE trên `(resource_id, slot_id)` có thể giải quyết mô hình **một booking mỗi slot đã định danh**. Nhưng bất biến tổng quát “số booking <= capacity” không phải lúc nào biểu diễn được chỉ bằng unique.

### 21.1. Đưa quota về cập nhật nguyên tử trên một hàng

Một thiết kế khác:

```sql
CREATE TABLE ws218.capacity_demo (
    resource_id integer PRIMARY KEY,
    capacity integer NOT NULL CHECK (capacity >= 0),
    occupied integer NOT NULL DEFAULT 0,
    CHECK (occupied >= 0 AND occupied <= capacity)
);

INSERT INTO ws218.capacity_demo(resource_id, capacity, occupied)
VALUES (1, 1, 0);
```

Đặt chỗ:

```sql
UPDATE ws218.capacity_demo
SET occupied = occupied + 1
WHERE resource_id = 1
  AND occupied < capacity
RETURNING occupied, capacity;
```

Hai request tranh chấp **cùng một hàng**. Điều kiện UPDATE giúp kiểm tra và tăng quota nguyên tử theo cơ chế concurrency của PostgreSQL.

Nhưng nếu có bảng booking riêng, **mọi thao tác đặt/hủy chỗ phải cập nhật cả booking và quota trong cùng transaction**. Nếu counter và danh sách booking lệch nhau, CHECK của counter có thể đúng nhưng dữ liệu booking thật sai.

## 22. SSI và predicate/SIREAD locks

PostgreSQL `SERIALIZABLE` thường dùng SSI để theo dõi những **phụ thuộc đọc–ghi** nguy hiểm, kể cả khi một transaction đọc một tập hàng theo điều kiện và transaction khác làm thay đổi tập ấy.

Cần phân biệt:

- **MVCC snapshot:** những phiên bản dữ liệu mà transaction được thấy.
- **Row-level lock/FOR UPDATE:** khóa xung đột có thể khiến transaction khác chờ khi cố khóa/sửa cùng hàng.
- **SIREAD/predicate locks của SSI:** theo dõi những phạm vi đọc để phát hiện mối phụ thuộc gây serialization anomaly; không đồng nghĩa luôn chặn ngay mọi writer.

Vì vậy, ở SERIALIZABLE có thể xảy ra:

```text
A SELECT -> B SELECT -> A UPDATE -> B UPDATE
-> một transaction gặp 40001
```

thay vì mọi SELECT đều đợi transaction kia.

### 22.1. Quan sát SIREAD lock

Khi đang có session SERIALIZABLE phù hợp, có thể xem:

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name
FROM pg_locks
WHERE mode = 'SIReadLock'
ORDER BY pid, relation_name;
```

Kết quả phụ thuộc thời điểm, plan, quyền xem và cấp độ lock. **Không coi việc có/không thấy một dòng SIREAD là phép kiểm chứng invariant.** Phép kiểm chứng thực tế vẫn phải đánh giá trạng thái đã commit.

### 22.2. Chi phí và false positives

SSI có thể phát sinh `40001` ngay cả khi người đọc log thấy một tình huống “có vẻ không nguy hiểm”. Đó là chi phí của cơ chế ngăn lịch không tuần tự hóa. Ứng dụng không được bỏ qua lỗi chỉ vì truy vấn kiểm chứng tình cờ vẫn thấy dữ liệu hợp lệ.

## 23. Kiểm thử concurrency bằng hai connection và barrier

Một bài test tuần tự không đủ để tái hiện write skew. Hãy dùng hai kết nối độc lập:

```text
Test runner
   |
   +---- Connection A: BEGIN
   |
   +---- Connection B: BEGIN
   |
   +---- A: SELECT count -> 2 ----+
   |                              |
   +---- B: SELECT count -> 2 ----+--> BARRIER
                                          |
                               Cho cả hai UPDATE
                                          |
                     A: UPDATE DR_A   B: UPDATE DR_B
                           |               |
                        COMMIT          COMMIT
                           \               /
                         Đọc lại dữ liệu
                               |
                      assert active_count >= 1
```

### 23.1. Với REPEATABLE READ

Mục tiêu học tập là **tái hiện được một lịch hai transaction cùng commit** để chứng minh invariant có thể sai. Truy vấn cuối có thể trả active_count=0.

### 23.2. Với SERIALIZABLE

Mục tiêu là **không có lịch cả hai transaction commit thành công làm count=0**. Có thể một transaction thành công, transaction kia nhận `40001`. Khi retry, transaction thua phải đọc count mới và từ chối rời ca nếu chỉ còn một bác sĩ.

### 23.3. Vì sao không chỉ dùng pg_sleep?

`pg_sleep` giúp làm chậm, nhưng không chứng minh cả hai transaction đã **đọc xong** trước khi writer chạy. Test dựa vào sleep cố định dễ flaky. Barrier có xác nhận các mốc “đã đọc” và “được phép ghi” cho kết quả đáng tin hơn.

### 23.4. Ghi những thông tin gì?

```text
A:
  isolation:
  count trước update:
  update row count:
  commit outcome:
  SQLSTATE nếu lỗi:

B:
  isolation:
  count trước update:
  update row count:
  commit outcome:
  SQLSTATE nếu lỗi:

Sau khi cả hai kết thúc:
  active_count đã commit:
  invariant_holds:
```

Một test đúng không chỉ assert mã HTTP hoặc số hàng update; nó assert **bất biến sau commit**.

## 24. Test những tình huống biên

Ngoài hai bác sĩ cùng rời ca, nên có:

- Một ca chỉ có **một** bác sĩ trực từ đầu → phải từ chối rời ca.
- Một ca không có hàng bác sĩ → kiểm chứng phải báo vi phạm, không bỏ sót do GROUP BY.
- Hai request cùng một bác sĩ → phân biệt no-op, không tồn tại và thành công.
- Một request đổi một bác sĩ, request khác thêm bác sĩ mới.
- Một tác vụ admin hạ trạng thái nhiều bác sĩ một lúc.
- Một job batch không đi qua service thông thường.
- Giao dịch bị rollback sau UPDATE.
- Một transaction nhận `40001`, retry và ra quyết định **khác** lần đầu.
- Hai ca độc lập xử lý đồng thời → không nên chịu khóa global không cần thiết.
- Một transaction gặp deadlock/lock timeout.
- Retry HTTP sau khi client không nhận được response commit.
- RLS/tenant filter có thể làm thay đổi tập bác sĩ mà một role được phép đọc.

Mục tiêu không phải chỉ tìm một lịch gây lỗi, mà là kiểm tra **mọi đường thay đổi có thể tác động tới bất biến**.

## 25. Kiểm chứng trong transaction khác kiểm chứng sau commit

Ở REPEATABLE READ, A tự thấy count=1 và B tự thấy count=1. Nhưng sau khi cả hai commit, một session mới thấy count=0.

Đó là hai góc nhìn khác nhau:

1. Snapshot riêng của transaction dùng để quyết định.
2. Trạng thái đã commit chung sau khi các transaction kết thúc.

Vì vậy:

- Thêm một SELECT COUNT ngay trước COMMIT ở REPEATABLE READ **không đủ ngăn write skew**.
- Kiểm tra định kỳ sau commit có thể **phát hiện** dữ liệu sai, nhưng không tự **ngăn** dữ liệu sai.
- Cần cơ chế bảo vệ trong quá trình ghi, rồi dùng kiểm chứng sau commit để đánh giá hiệu quả.

Một câu kiểm tra dạng boolean:

```sql
SELECT NOT EXISTS (
    SELECT 1
    FROM ws218.shifts AS s
    LEFT JOIN ws218.shift_doctors AS d
        ON d.shift_id = s.shift_id
    GROUP BY s.shift_id
    HAVING COUNT(d.doctor_id)
             FILTER (WHERE d.is_on_call IS TRUE) = 0
) AS invariant_holds;
```

Kết quả `true` có nghĩa không tìm thấy ca vi phạm trong snapshot của truy vấn kiểm tra. Đây là quan sát tại một thời điểm, không phải khóa bảo vệ cho mọi thay đổi tương lai.

## 26. Quan sát lỗi, lock và giao dịch

Với production, các log/metric nên có:

- Request/correlation ID và tài nguyên/shift ID phù hợp quyền riêng tư.
- Isolation level.
- Số lần retry và kết quả COMMIT.
- SQLSTATE `40001` hoặc `40P01`.
- Thời gian transaction và lock wait.
- Các giao dịch giữ lock quá lâu.
- Tỷ lệ invariant violation được phát hiện bởi truy vấn đối soát.

Truy vấn chẩn đoán phiên chờ:

```sql
SELECT
    pid,
    usename,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    left(query, 120) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY pid;
```

Kết quả phụ thuộc quyền xem hệ thống và thời điểm. Không nên log nguyên dữ liệu nhạy cảm của transaction.

### 26.1. Đừng nhầm deadlock với write skew

- **Deadlock:** có vòng chờ lock; PostgreSQL phát hiện và có thể hủy một transaction.
- **Write skew:** có thể không chờ lock trực tiếp vì mỗi transaction sửa một hàng khác; **không có deadlock vẫn có thể sai invariant**.
- **Serialization failure:** cơ chế SSI không chấp nhận lịch commit không tuần tự hóa được, có thể xảy ra không kèm lock wait dài.

### 26.2. Giữ transaction ngắn

Không giữ transaction mở trong lúc chờ người dùng, gọi API thanh toán dài hoặc gửi email đồng bộ. Transaction dài làm tăng tranh chấp, lock wait, snapshot cũ và chi phí retry.

Với side effect ngoài database, cân nhắc transactional outbox và xử lý sau COMMIT; không gửi thông báo “đã ngừng trực” trước khi giao dịch thực sự thành công.

## 27. Retry và idempotency là hai bài toán liên quan nhưng khác nhau

Retry `40001` nghĩa là transaction bị hủy và cần làm lại.

Retry HTTP do mất kết nối hoặc timeout gần COMMIT phức tạp hơn: client có thể **không biết transaction đã commit hay chưa**.

Vì vậy hệ thống cần:

- Một idempotency key cho request nghiệp vụ khi phù hợp.
- Gắn key với tài nguyên/tenant và payload.
- Phân biệt lần đầu, lần lặp lại và payload khác trên cùng key.
- Không lặp lại side effect đã commit.
- Sau serialization failure, chạy lại toàn bộ đọc–quyết định–ghi trong transaction mới.
- Chỉ xuất bản event hoặc xác nhận thành công khi kết quả commit được xác định.

Một UNIQUE trên idempotency key có thể là thành phần bảo vệ, nhưng không tự thay thế mọi logic điều phối transaction.

## 28. Bảo mật và nhiều tenant

Nếu bảng dùng cho nhiều tổ chức:

```text
tenant_id, shift_id, doctor_id, is_on_call
```

thì invariant thực tế là:

```text
Với mỗi (tenant_id, shift_id) đang hoạt động:
    active_count >= 1
```

Truy vấn kiểm tra và cập nhật phải dùng **đúng cặp khóa tenant + shift**. Nếu chỉ `WHERE shift_id=1`, dữ liệu của hai tenant có cùng shift_id có thể bị cộng chung, khiến bất biến được kiểm chứng sai hoặc lộ dữ liệu.

Cần bảo đảm:

- Tenant ID đến từ ngữ cảnh xác thực.
- Khóa chính/khóa ngoại và JOIN chứa đủ cột tenant khi cần.
- Guard lock/advisory key được thiết kế theo từng tenant + shift.
- RLS là lớp bảo vệ truy cập, **không tự ngăn write skew**.
- Mọi đường ghi, kể cả admin/batch, tuân thủ protocol của bất biến.

## 29. Những lỗi thường gặp

### Lỗi 1. Nghĩ REPEATABLE READ chắc chắn an toàn

PostgreSQL REPEATABLE READ dùng snapshot isolation và vẫn có write skew.

**Sửa:** SERIALIZABLE+retry hoặc cơ chế khóa/constraint phù hợp.

### Lỗi 2. Chỉ khóa hàng bác sĩ hiện tại

Hai giao dịch khóa hai hàng khác nhau nên vẫn có thể quyết định từ cùng snapshot cũ.

**Sửa:** đồng bộ trên đơn vị invariant, ví dụ một guard row của cả ca.

### Lỗi 3. Chạy SELECT COUNT hai lần rồi tưởng không thể sai

Trong REPEATABLE READ, cả hai lần có thể đọc snapshot ổn định, không thấy thay đổi của transaction khác.

**Sửa:** thay cơ chế concurrency, không chỉ tăng số lần SELECT.

### Lỗi 4. Dùng SELECT FOR UPDATE trên kết quả COUNT

Aggregate COUNT không phải hàng cơ sở để khóa như một row; phải khóa hàng thực hoặc guard phù hợp.

### Lỗi 5. Dùng guard lock ở REPEATABLE READ rồi giả định snapshot mới

Lock không tự làm mới snapshot. Cần write conflict/retry hoặc dùng protocol READ COMMITTED đúng cách.

### Lỗi 6. Nghĩ partial UNIQUE bảo đảm ít nhất một bác sĩ

UNIQUE bảo vệ giới hạn **tối đa**, không tự tạo sự tồn tại **tối thiểu**.

### Lỗi 7. Trigger đếm COUNT mà không đồng bộ

Trigger cũng có thể dựa vào snapshot cũ và cùng cho qua hai transaction.

### Lỗi 8. SERIALIZABLE nhưng nuốt lỗi 40001

Transaction thất bại không được trả là thành công. Cần rollback và retry toàn bộ quyết định.

### Lỗi 9. Chỉ retry UPDATE, không retry SELECT

Điều kiện count=2 từ lần trước có thể không còn đúng.

### Lỗi 10. Không kiểm tra trạng thái sau commit

Một test chỉ assert `UPDATE 1` hoặc HTTP 200 có thể bỏ sót lỗi xuyên hàng.

### Lỗi 11. Chỉ test tuần tự

Không có lịch interleaving thì không thấy write skew.

### Lỗi 12. Dùng pg_sleep như một barrier chắc chắn

Sleep cố định không bảo đảm hai phiên đã cùng hoàn thành bước đọc.

### Lỗi 13. Đếm trên bảng con và bỏ qua ca rỗng

GROUP BY trên `shift_doctors` không có hàng cho ca không phân công ai.

**Sửa:** `shifts LEFT JOIN shift_doctors` hoặc `NOT EXISTS`.

### Lỗi 14. Gửi email trước COMMIT

Giao dịch có thể rollback sau khi gửi, tạo thông báo sai.

### Lỗi 15. Một job khác bỏ qua protocol

Chỉ một endpoint an toàn không đủ nếu batch script hoặc admin tool ghi thẳng.

### Lỗi 16. Dùng một khóa global cho mọi ca

Các ca độc lập bị chặn không cần thiết.

**Sửa:** chọn khóa theo đơn vị invariant.

## 30. Bài tập thực hành có lời giải

### Bài 1. Viết điều kiện đúng

**Yêu cầu:** mỗi ca phải có ít nhất một bác sĩ TRUE.

**Lời giải:** `COUNT(doctor_id) FILTER (WHERE is_on_call IS TRUE) >= 1` cho mọi ca thuộc phạm vi nghiệp vụ.

### Bài 2. Vì sao chạy tuần tự không để cả A và B nghỉ?

**Lời giải:** sau transaction đầu, count=1, transaction thứ hai phải từ chối.

### Bài 3. Hai UPDATE có sửa cùng hàng không?

**Lời giải:** không. A sửa DR_A, B sửa DR_B. Vì thế không có xung đột write–write trực tiếp trên cùng hàng.

### Bài 4. Chạy hai transaction dưới REPEATABLE READ cần xen kẽ thế nào?

**Lời giải:** A SELECT count=2, B SELECT count=2, A UPDATE DR_A, B UPDATE DR_B, rồi cả hai COMMIT. Hai session phải độc lập và snapshot ban đầu có hai TRUE.

### Bài 5. Vì sao mỗi phiên tự SELECT sau UPDATE đều thấy count=1?

**Lời giải:** mỗi phiên thấy thay đổi của mình và vẫn nhìn bác sĩ kia TRUE trong snapshot cũ.

### Bài 6. Tìm ca không còn người trực

```sql
SELECT s.shift_id
FROM ws218.shifts AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM ws218.shift_doctors AS d
    WHERE d.shift_id = s.shift_id
      AND d.is_on_call IS TRUE
);
```

**Lời giải:** query trả các ca không có bác sĩ TRUE, kể cả ca hoàn toàn không có hàng phân công.

### Bài 7. Vì sao không có deadlock vẫn có write skew?

**Lời giải:** hai UPDATE ghi các hàng khác nhau, không phải đợi khóa nhau. Bất biến vẫn có thể sai.

### Bài 8. SERIALIZABLE bảo vệ bằng cách nào?

**Lời giải:** SSI phát hiện phụ thuộc đọc–ghi không thể tuần tự hóa, từ chối một transaction bằng serialization failure khi cần.

### Bài 9. Sau 40001 phải retry gì?

**Lời giải:** rollback, bắt đầu transaction mới, SELECT lại count, ra quyết định lại, rồi mới UPDATE và COMMIT nếu còn hợp lệ.

### Bài 10. Khóa hàng guard đúng trình tự nào?

**Lời giải:** BEGIN READ COMMITTED → SELECT shift FOR UPDATE → SELECT COUNT trong statement riêng → quyết định → UPDATE doctor → COMMIT/ROLLBACK.

### Bài 11. Nếu guard row chỉ bị khóa nhưng không UPDATE ở REPEATABLE READ?

**Lời giải:** snapshot có thể vẫn cũ sau khi chờ. Đừng suy luận cơ chế READ COMMITTED áp dụng nguyên xi; cần protocol đảm bảo xung đột/serialization retry.

### Bài 12. Trigger đếm bác sĩ có tự an toàn không?

**Lời giải:** không. Trigger không tự ngăn hai snapshot đồng thời cùng nhìn người còn lại TRUE.

### Bài 13. Một ca có 0 hàng phân công, query GROUP BY bảng con trả gì?

**Lời giải:** không có nhóm ca đó. Phải bắt đầu từ shifts/NOT EXISTS để phát hiện ca rỗng.

### Bài 14. Chỉ cần “tối đa một bác sĩ chính” có dùng UNIQUE được không?

**Lời giải:** có thể dùng partial unique index theo ca cho quy tắc tối đa một. Nhưng đó **không phải** quy tắc ít nhất một người trực.

### Bài 15. Hai booking cùng INSERT với ID khác nhau khi capacity=1 là lỗi gì?

**Lời giải:** một dạng serialization anomaly dựa trên predicate count; hai transaction đọc count=0 rồi chèn hàng khác nhau khiến tổng vượt 1.

### Bài 16. Nếu quota lưu trên một hàng, cập nhật ra sao?

```sql
UPDATE ws218.capacity_demo
SET occupied = occupied + 1
WHERE resource_id = 1
  AND occupied < capacity
RETURNING occupied;
```

**Lời giải:** điều kiện kiểm tra và tăng quota cùng thao tác trên hàng chung. Phải đồng bộ với dữ liệu booking thật trong transaction.

### Bài 17. Một transaction có SQLSTATE 40P01 thì đó có phải write skew?

**Lời giải:** `40P01` là deadlock_detected. Nó là lỗi tranh chấp khóa, không đồng nghĩa dữ liệu đã trải qua write skew. Có thể retry toàn transaction theo chính sách.

### Bài 18. Dựa vào pg_locks có chứng minh invariant luôn đúng không?

**Lời giải:** không. pg_locks phục vụ chẩn đoán lock; invariant phải được kiểm chứng trên trạng thái dữ liệu và bảo vệ bằng protocol ghi đúng.

### Bài 19. Một job nội bộ sửa bác sĩ mà không lấy guard lock?

**Lời giải:** nó có thể phá bảo đảm mà service đã thiết kế. Mọi đường ghi liên quan phải tuân thủ invariant.

### Bài 20. Retry HTTP khác retry serialization thế nào?

**Lời giải:** sau 40001 transaction không commit; sau mất kết nối quanh COMMIT, trạng thái thành công có thể chưa xác định với client. Trường hợp sau cần idempotency/đối soát.

## 31. Checklist trước khi triển khai

| Câu hỏi | Tại sao quan trọng? |
|---|---|
| Bất biến đã được viết thành câu điều kiện chính xác chưa? | Biết thế nào là dữ liệu đúng |
| Có nhiều hàng cùng quyết định một điều kiện không? | Nhận diện write skew |
| Đã xác định mọi endpoint/job có thể sửa tập hàng chưa? | Một writer bỏ protocol có thể phá dữ liệu |
| Isolation thực tế là gì? | Không nhầm REPEATABLE READ với SERIALIZABLE |
| Đã test bằng hai connection độc lập chưa? | Kiểm thử tuần tự không phát hiện anomaly |
| Đã đồng bộ hai bước SELECT trước UPDATE chưa? | Tái hiện đúng lịch cạnh tranh |
| Nếu dùng SERIALIZABLE, có retry 40001 toàn transaction không? | Không dùng quyết định cũ |
| Nếu dùng guard lock, mọi writer có tranh cùng lock key không? | Đảm bảo đồng bộ thực sự |
| Ở READ COMMITTED, count được SELECT sau khi có lock chưa? | Tránh snapshot đọc trước lock |
| Có đường insert/delete khiến tập hàng thay đổi không? | Lock hàng có sẵn chưa chắc bảo vệ predicate |
| Có constraint DB nào biểu diễn trực tiếp được invariant không? | Ưu tiên bảo vệ mọi đường ghi khi khả thi |
| Có giới hạn retry/backoff và logging SQLSTATE không? | Tránh request treo và khó điều tra |
| Đã đọc lại trạng thái sau tất cả COMMIT/ROLLBACK chưa? | Đo kết quả đã commit |
| Ca không có hàng bác sĩ có bị bỏ sót khi kiểm chứng không? | Tránh false negative |
| Transaction có side effect ngoài DB trước commit không? | Tránh thông báo sai |
| Lock có đúng phạm vi tenant/shift không? | Tránh nhầm dữ liệu và contention thừa |

## 32. So sánh giải pháp

| Phương án | Nguyên lý | Ưu điểm | Hạn chế |
|---|---|---|---|
| `SERIALIZABLE + retry` | SSI chặn lịch không tuần tự hóa | Bảo vệ phụ thuộc xuyên hàng | Cần retry 40001; quản lý mọi writer |
| `READ COMMITTED + guard FOR UPDATE` | Mọi writer cùng khóa một hàng trước khi đọc | Dễ lý giải | Phải tuân thủ protocol, có lock wait |
| `UPDATE guard version` | Tạo xung đột write–write chung | Có thể phát hiện stale snapshot | Thêm contention và cần retry RR |
| Advisory lock cấp transaction | Khóa logic theo ca | Không cần hàng guard vật lý | Tự nguyện, không làm mới snapshot |
| Atomic single-row quota update | Đưa kiểm tra và ghi vào cùng hàng | Tốt cho counter/capacity | Giữ counter đồng bộ dữ liệu liên quan |
| Constraint phù hợp | DB từ chối trạng thái vi phạm | Bảo vệ ngay cả writer ngoài app | Không biểu diễn được mọi quy tắc đa hàng |
| Trigger + protocol đúng | Kiểm soát logic tại DB | Gom quy tắc về một chỗ | Trigger COUNT đơn thuần vẫn race |
| Kiểm chứng định kỳ | Phát hiện bất biến sai | Hỗ trợ monitoring/đối soát | **Không ngăn** sai lệch xuất hiện |

## 33. Tài liệu tham khảo PostgreSQL

- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html): so sánh READ COMMITTED, REPEATABLE READ và SERIALIZABLE, cơ chế snapshot/SSI.
- [Serialization Failure Handling](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html): retry transaction và SQLSTATE `40001`.
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): row locks, deadlock, advisory locks và các lựa chọn khóa.
- [SET TRANSACTION](https://www.postgresql.org/docs/current/sql-set-transaction.html): thiết lập mức cô lập đúng ranh giới giao dịch.
- [Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): phạm vi CHECK, UNIQUE, khóa ngoại và ràng buộc dữ liệu.

Khi áp dụng trong môi trường thật, kiểm tra đúng phiên bản server:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

## 34. Tổng kết

Write skew là trường hợp **hai transaction đọc cùng một điều kiện nghiệp vụ, cập nhật các hàng khác nhau, rồi cùng commit khiến điều kiện không còn đúng**.

Với hai bác sĩ:

```text
Ban đầu:   DR_A=TRUE,  DR_B=TRUE   -> active_count=2
T_A đọc:   active_count=2
T_B đọc:   active_count=2
T_A ghi:   DR_A=FALSE
T_B ghi:   DR_B=FALSE

REPEATABLE READ:
    Hai transaction có thể COMMIT
    DR_A=FALSE, DR_B=FALSE
    active_count=0 -> VI PHẠM

SERIALIZABLE:
    Không thể chấp nhận cả hai COMMIT với lịch bất hợp lệ
    Một transaction có thể nhận 40001
    Retry toàn transaction -> đọc count mới -> từ chối rời ca
    active_count cuối vẫn >=1
```

Những nguyên tắc cần ghi nhớ:

1. **Định nghĩa invariant trước khi viết transaction.** Nó thường nằm trên nhiều hàng hoặc một tập được lọc bằng predicate.
2. **Snapshot nhất quán không phải serializable.** PostgreSQL REPEATABLE READ vẫn có thể có write skew.
3. **Khóa riêng hàng sửa không đủ** nếu quyết định phụ thuộc hàng khác; khóa phải bảo vệ phạm vi invariant hoặc dùng SERIALIZABLE.
4. **SERIALIZABLE yêu cầu xử lý 40001**, rollback và retry toàn bộ logic đọc–quyết định–ghi.
5. **Một guard row ở READ COMMITTED** có thể tuần tự hóa các quyết định cùng ca nếu mọi writer lấy lock trước và đọc count bằng statement mới sau lock.
6. **Constraint cần đúng ngữ nghĩa.** UNIQUE “tối đa một” không thay thế invariant “ít nhất một”; trigger đếm đơn thuần cũng không tự ngăn race.
7. **Kiểm thử đồng thời phải có barrier**, đồng thời kiểm tra trạng thái đã commit bằng SQL, kể cả các ca rỗng.
8. **Phát hiện khác phòng ngừa.** Truy vấn kiểm chứng và monitoring giúp thấy dữ liệu sai, nhưng chỉ protocol ghi đúng mới ngăn write skew.
9. **Giữ toàn bộ đường ghi nhất quán:** service, API retry, job batch, admin và multi-tenant đều phải theo một thiết kế bảo vệ chung.

**Một câu để nhớ:** write skew không phải hai transaction cùng sửa một hàng, mà là hai transaction cùng tin một điều kiện trên nhiều hàng và cùng sửa các hàng khác nhau, khiến điều kiện đó bị phá vỡ sau COMMIT.

