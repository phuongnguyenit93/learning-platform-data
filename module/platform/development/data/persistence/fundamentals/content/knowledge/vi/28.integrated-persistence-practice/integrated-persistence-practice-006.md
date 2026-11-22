# Tái hiện mất cập nhật rồi áp dụng cập nhật có điều kiện

Hai nhân viên cùng đặt hàng từ một kho còn 10 sản phẩm. Nhân viên A đặt 3 sản phẩm, nhân viên B đặt 4 sản phẩm. Cả hai đọc được `available_qty = 10`; A tính còn 7, B tính còn 6. Nếu hai thao tác lần lượt ghi **giá trị đã tính từ dữ liệu cũ**, kho có thể còn 6 thay vì 3: thay đổi của A đã bị thao tác B **ghi đè**. Đây là dạng **mất cập nhật (*lost update*) do read–modify–write ở ứng dụng**, thường bị bỏ qua khi mỗi câu `SELECT` và `UPDATE` riêng lẻ đều chạy thành công.

Bài thuộc chương **Thực hành tổng hợp** của mô-đun **DATA_PERSISTENCE_FUNDAMENTALS**. Mô-đun bao quát nguyên lý lưu trữ bền vững: mô hình dữ liệu, schema, truy vấn, chỉ mục, transaction, isolation, kiểm soát đồng thời và ranh giới persistence trong Java; đồng thời xử lý lỗi kết nối, tiến hóa schema, bảo mật, sao lưu và tối ưu hiệu năng. Trong bài, người học thực hành **tạo race condition, đo bất biến bị vi phạm, sửa bằng cập nhật có điều kiện và chứng minh sửa đúng dưới cạnh tranh thực tế**.

Các lệnh được thiết kế cho **PostgreSQL và hai phiên `psql` độc lập**, kèm ví dụ Spring JDBC/JPA. Chỉ chạy trên **database hoặc schema thử nghiệm đã được phép**, không chạy thao tác đặt lại dữ liệu trên production. `READ COMMITTED` trong PostgreSQL có semantics riêng; không mặc định mọi DBMS hoặc mọi isolation level diễn xử giống hệt nhau.

## 1. Mục tiêu và tiêu chí hoàn thành bài thực hành

Sau bài này, người học cần làm được:

1. **Tái hiện được** mất cập nhật với hai connection, ghi rõ thứ tự đọc/ghi/commit, quan sát giá trị cuối cùng sai.
2. **Giải thích đúng nguyên nhân:** hai bên đọc cùng một phiên bản rồi dùng giá trị cũ để ghi đè; transaction/statement thành công **không** bảo đảm read–modify–write ở Java được tuần tự hóa.
3. **Sửa bằng optimistic concurrency control:** dùng `version` trong điều kiện `WHERE`, kiểm tra `rows affected`, phát hiện stale read và thử lại toàn chuỗi đọc–tính–ghi theo quy tắc.
4. **Sửa bằng thao tác nguyên tử có điều kiện:** để PostgreSQL cập nhật `available_qty = available_qty - :qty` và kiểm tra `available_qty >= :qty` **trong một câu `UPDATE`**.
5. **So sánh** với khóa bi quan (`SELECT ... FOR UPDATE`) và isolation `SERIALIZABLE`; biết trường hợp nào phù hợp.
6. **Kiểm thử cạnh tranh và sự cố:** tối thiểu hai tác vụ đồng thời, cạn hàng, retry, ghi trùng, commit outcome chưa rõ và lỗi khi side effect nằm ngoài database.

### 1.1. Bất biến nghiệp vụ phải kiểm chứng

Giả sử một dòng tồn kho ứng với một SKU và **không có nhập kho** trong bài thử:

\[
\text{available}_{\mathrm{final}} = \text{available}_{\mathrm{initial}} - \sum\text{qty của các đặt hàng đã được nhận thành công}
\]

Đồng thời:

\[
\text{available}_{\mathrm{final}}\ge 0
\]

Nếu ban đầu có 10, hai lần đặt 3 và 4 đều thực sự thành công, **kết quả đúng là 3**. Nếu cả hai cùng đặt 7, chỉ **một** lần được nhận thành công, kết quả đúng là **3** và lần còn lại phải bị từ chối hoặc chờ theo hợp đồng. Kiểm tra `available_qty >= 0` **một mình không đủ**: hệ lỗi có thể chấp nhận cả hai lần đặt 7 nhưng vẫn lưu `available_qty = 3`, tức đã hứa bán 14 món từ 10 món.

Trong hệ thực, bất biến phải bao gồm **bản ghi đơn/reservation** và idempotency của yêu cầu; nếu chỉ sửa đúng số tồn kho mà vẫn ghi hai đơn trùng nhau do client retry, hệ chưa đúng về nghiệp vụ.

## 2. Chuẩn bị môi trường và dữ liệu tái lập

Yêu cầu: PostgreSQL có thể mở ít nhất **hai connection độc lập**, tài khoản được phép tạo bảng trong schema test, và một công cụ như `psql`. Các ví dụ sử dụng SKU `BOOK-001` như một khóa duy nhất, `available_qty` kiểu `INTEGER` và `version` dùng cho optimistic locking.

Chạy **một lần** ở connection chuẩn bị (không phải connection A/B đang giữ transaction):

```sql
-- Chỉ tạo trong database/schema thử nghiệm, không chạy trên production.
CREATE TABLE IF NOT EXISTS practice_inventory (
    sku TEXT PRIMARY KEY,
    available_qty INTEGER NOT NULL CHECK (available_qty >= 0),
    version BIGINT NOT NULL DEFAULT 0 CHECK (version >= 0)
);

INSERT INTO practice_inventory (sku, available_qty, version)
VALUES ('BOOK-001', 10, 0)
ON CONFLICT (sku) DO UPDATE
SET available_qty = EXCLUDED.available_qty,
    version = EXCLUDED.version;

SELECT sku, available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- BOOK-001 | 10 | 0
```

Ở production, `ON CONFLICT ... DO UPDATE` như trên **có thể ghi đè dữ liệu thật**. Đây là bước **reset dành riêng cho bài lab** và chỉ chạy khi không còn transaction thực hành đang mở. Không chia sẻ cùng một connection giữa hai người dùng `psql` nếu muốn tái hiện đúng race.

### 2.1. Hai terminal, hai transaction

Mở terminal A và terminal B, mỗi terminal kết nối database test bằng `psql` độc lập. Có thể dùng `SELECT pg_backend_pid();` để xác minh hai phiên có `pid` khác nhau:

```sql
SELECT pg_backend_pid(), current_setting('transaction_isolation');
-- Ghi lại pid của từng phiên để phân biệt A và B.
```

Mặc định PostgreSQL thường là `READ COMMITTED`; trong bài sẽ đặt rõ mức cô lập. **Không dùng transaction mặc định của test framework đã bao ngoài tất cả thao tác** mà không kiểm tra, vì nó có thể thay đổi thời điểm commit và khiến kết quả khác kịch bản.

## 3. Tái hiện lỗi bằng lịch chạy A/B có kiểm soát

Mục tiêu: hai client đều đọc số tồn 10 trước khi bất kỳ client nào hoàn tất cập nhật. Mỗi client tính số tồn mới **ở phía ứng dụng** dựa trên bản đọc đó.

**Bước A1 — Terminal A:**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- A thấy qty=10, version=0; A muốn giữ 3, nên tính new_qty=7.
-- Giữ transaction A mở, chưa UPDATE.
```

**Bước B1 — Terminal B (trước khi A ghi):**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- B cũng thấy qty=10, version=0; B muốn giữ 4, nên tính new_qty=6.
-- Giữ transaction B mở, chưa UPDATE.
```

**Bước A2 — Terminal A ghi số đã tính rồi commit:**

```sql
UPDATE practice_inventory
SET available_qty = 7
WHERE sku = 'BOOK-001';
-- UPDATE 1
COMMIT;
```

**Bước B2 — Terminal B vẫn dùng kết quả đọc cũ 10:**

```sql
UPDATE practice_inventory
SET available_qty = 6
WHERE sku = 'BOOK-001';
-- UPDATE 1
COMMIT;
```

**Bước kiểm chứng — Connection chuẩn bị hoặc connection mới:**

```sql
SELECT sku, available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- Kết quả điển hình: BOOK-001 | 6 | 0
-- Đúng theo nghiệp vụ phải là 10 - 3 - 4 = 3.
```

`version` không đổi vì hai câu `UPDATE` sai ở ví dụ **không sử dụng hoặc tăng** cột version. Đây là dấu hiệu ứng dụng chưa có optimistic concurrency control. Không coi `version` tự bảo vệ chỉ vì nó tồn tại trong schema.

### 3.1. Tại sao `READ COMMITTED` không ngăn được lịch này?

Trong PostgreSQL `READ COMMITTED`, mỗi statement lấy snapshot phù hợp với thời điểm bắt đầu statement. Khi A và B đọc, cả hai đều thấy 10. Sau khi A commit, B thực thi một `UPDATE ... SET available_qty = 6` với **hằng số đã tính từ snapshot cũ**, nên nó có thể ghi đè kết quả A. PostgreSQL đảm bảo một bản cập nhật hàng được thực thi với cơ chế khóa/nhìn thấy phiên bản phù hợp; **DB không biết 6 bắt nguồn từ phép tính `10 - 4` ở Java** và không tự suy ra phải trừ tiếp từ giá trị 7.

Lỗi không đòi A và B phải thực thi `UPDATE` đúng cùng một microsecond. Chỉ cần **hai phép đọc cũ cùng xảy ra trước những phép ghi** và sau đó cùng ghi giá trị đã tính sẵn. Nếu hai lệnh update tranh đúng một row cùng lúc, một lệnh có thể đợi row lock của lệnh kia; việc đợi khóa không làm hằng số `6` tự biến thành `3`.

### 3.2. Kết quả cần ghi vào sổ tay thực hành

| Thời điểm | A | B | Giá trị đã commit trong DB |
|---|---|---|---:|
| T0 | — | — | 10 |
| T1 | Đọc 10, dự định trừ 3 | — | 10 |
| T2 | — | Đọc 10, dự định trừ 4 | 10 |
| T3 | `UPDATE qty=7; COMMIT` | — | 7 |
| T4 | — | `UPDATE qty=6; COMMIT` | 6 |
| T5 | Cả hai yêu cầu được báo thành công | — | **6 (sai; phải 3)** |

**Đầu ra yêu cầu:** ghi lại số row được `UPDATE`, số cuối và lý do hai transaction đều thành công mà bất biến nghiệp vụ bị phá. Phải giải thích bằng **một bản đọc cũ được dùng lại để ghi đè**, không kết luận tùy tiện rằng PostgreSQL "không hỗ trợ khóa hàng".

## 4. Phân biệt những kiểu UPDATE nhìn giống nhau nhưng có semantics khác

| Câu lệnh | Đọc giá trị nào để tính? | Dưới cạnh tranh |
|---|---|---|
| `UPDATE ... SET available_qty = 6 WHERE sku = ...` | Giá trị cố định do Java tính từ lần đọc cũ | Có thể ghi đè thay đổi khác, **lost update** |
| `UPDATE ... SET available_qty = available_qty - 4 WHERE sku = ...` | PostgreSQL tính từ giá trị hàng phù hợp khi statement cập nhật | Tránh ghi đè kiểu read–modify–write của ví dụ, **nhưng có thể cho âm** nếu thiếu điều kiện/ràng buộc |
| `UPDATE ... SET available_qty = available_qty - 4 WHERE sku = ... AND available_qty >= 4` | Giá trị hiện thời được DB kiểm tra và trừ trong một statement | Có thể bảo vệ **không đặt quá số tồn** với PostgreSQL `READ COMMITTED` |
| `UPDATE ... SET available_qty = 6, version = version+1 WHERE sku=... AND version=0` | Vẫn tính trước, nhưng có **precondition phiên bản** | Phát hiện stale read; lần ghi thứ hai cập nhật 0 hàng |
| `SELECT ... FOR UPDATE` rồi tính và ghi trong **cùng transaction** | Đọc hàng sau khi giành row lock thích hợp | Tuần tự hóa những writer tuân thủ khóa cho hàng đó |

Không đánh đồng `UPDATE ... SET column = column + 1` với `SELECT column; UPDATE SET column = old + 1`. Phép cập nhật dựa trên cột trong một SQL statement có hành vi đồng thời khác với phép tính đã tách ra Java. Và `CHECK (available_qty >= 0)` giúp chặn kết quả âm, **không chứng minh hai reservation đã được ghi nhận đúng** trong phép read–modify–write sai ở phần 3.

## 5. Cách sửa thứ nhất: optimistic locking với `version`

Khi nghiệp vụ cần đọc một entity, tính toán phức tạp trong Java rồi ghi lại, có thể dùng **compare-and-set (CAS)**: *chỉ cập nhật nếu phiên bản hiện tại vẫn đúng bằng phiên bản đã đọc*. Nếu row đã bị writer khác thay đổi, lệnh `UPDATE` phải trả về **0 hàng** và caller cần xử lý xung đột.

### 5.1. Reset dữ liệu ở connection chuẩn bị

Đảm bảo terminal A/B đã `COMMIT` hoặc `ROLLBACK`, sau đó:

```sql
UPDATE practice_inventory
SET available_qty = 10, version = 0
WHERE sku = 'BOOK-001';
```

### 5.2. Hai phiên đọc cùng phiên bản 0

**Terminal A:**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- A: 10, 0. Đặt 3; new_qty = 7, expected_version = 0.
```

**Terminal B:**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- B: 10, 0. Đặt 4; new_qty = 6, expected_version = 0.
```

**Terminal A cập nhật có điều kiện và commit:**

```sql
UPDATE practice_inventory
SET available_qty = 7,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND version = 0
  AND available_qty >= 3
RETURNING sku, available_qty, version;
-- A nhận 1 hàng: BOOK-001 | 7 | 1.
COMMIT;
```

**Terminal B cố ghi từ bản đọc cũ:**

```sql
UPDATE practice_inventory
SET available_qty = 6,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND version = 0
  AND available_qty >= 4
RETURNING sku, available_qty, version;
-- B nhận 0 hàng vì DB đã là version=1.
ROLLBACK; -- Kết thúc transaction thử không cập nhật được hàng nào.
```

**Kiểm tra:**

```sql
SELECT sku, available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- BOOK-001 | 7 | 1 (chỉ A thành công).
```

Điểm quan trọng: **0 hàng cập nhật không phải thành công**. Với `UPDATE ... WHERE version = :expectedVersion`, một kết quả 0 có thể nghĩa là **row đã bị xóa, không tồn tại hoặc phiên bản đã thay đổi**; nếu câu SQL còn điều kiện nghiệp vụ như `available_qty >= :qty`, có thể còn nguyên nhân **không đủ tồn kho**. Phải trả thông tin lỗi phù hợp hợp đồng hoặc đọc lại trạng thái dưới transaction mới; không lập tức diễn giải mọi kết quả 0 là deadlock hay lỗi hạ tầng.

### 5.3. B đọc lại rồi tính lại từ trạng thái mới

Sau `ROLLBACK`, ở **terminal B** bắt đầu transaction mới, đọc **giá trị 7, version 1** và tính lại `7 - 4 = 3`:

```sql
BEGIN;
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- 7, 1

UPDATE practice_inventory
SET available_qty = 3,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND version = 1
  AND available_qty >= 4
RETURNING sku, available_qty, version;
-- BOOK-001 | 3 | 2
COMMIT;
```

**Kết quả:**

```sql
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- 3 | 2
```

**Không retry bằng cách gửi lại `SET available_qty = 6` với version mới**. Làm vậy sẽ lách cơ chế phát hiện xung đột nhưng vẫn dựa trên giá trị cũ 10. Phải retry **đọc lại → kiểm tra điều kiện nghiệp vụ → tính lại → cập nhật có điều kiện**. Giới hạn số lần retry, có backoff/jitter phù hợp và đừng giữ transaction cũ trong lúc chờ.

### 5.4. Tại sao `version` phải được tăng bởi mọi writer?

Version chỉ phát hiện xung đột nếu mọi đường ghi có khả năng thay đổi trạng thái cần bảo vệ đều **tăng version nhất quán**. Nếu một batch script chạy:

```sql
-- Phản ví dụ: thay tồn kho nhưng KHÔNG tăng version.
UPDATE practice_inventory
SET available_qty = 1
WHERE sku = 'BOOK-001';
```

Một writer khác từng đọc `version=2` có thể vẫn cập nhật với `WHERE version=2` và vô tình ghi đè giá trị `1`. Trong hệ thật phải kiểm kê **application instances, scripts, jobs, importers, ORM bulk updates và triggers**. Có thể áp chính sách mọi writer dùng một API/SQL thống nhất, hoặc bảo vệ tại DB khi phù hợp; chỉ thêm cột `version` mà không kiểm soát đường ghi là chưa đủ.

## 6. Cách sửa thứ hai: một câu `UPDATE` nguyên tử có điều kiện

Với phép trừ tồn kho đơn giản, cách thường trực tiếp hơn là **để PostgreSQL vừa kiểm tra số tồn hiện tại vừa trừ số lượng trong cùng statement**:

```sql
UPDATE practice_inventory
SET available_qty = available_qty - 3,
    version = version + 1
WHERE sku = 'BOOK-001'
  AND available_qty >= 3
RETURNING sku, available_qty, version;
```

Không cần đọc số tồn vào Java trước để tính giá trị mới. Row được PostgreSQL khóa khi cập nhật; với các `UPDATE` cạnh tranh trên cùng hàng trong `READ COMMITTED`, statement đến sau có thể phải đợi transaction trước rồi **kiểm tra lại điều kiện `WHERE` trên phiên bản hàng mới** theo semantics PostgreSQL. Đó là điểm giúp điều kiện `available_qty >= :qty` bảo vệ bất biến.

### 6.1. Thí nghiệm đặt 3 và 4 từ tồn kho 10

Reset trong connection chuẩn bị:

```sql
UPDATE practice_inventory
SET available_qty = 10, version = 0
WHERE sku = 'BOOK-001';
```

**Terminal A:**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE practice_inventory
SET available_qty = available_qty - 3,
    version = version + 1
WHERE sku = 'BOOK-001' AND available_qty >= 3
RETURNING available_qty, version;
-- 7 | 1; giữ transaction A mở, chưa COMMIT.
```

**Terminal B (chạy trong khi A đang giữ row lock):**

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE practice_inventory
SET available_qty = available_qty - 4,
    version = version + 1
WHERE sku = 'BOOK-001' AND available_qty >= 4
RETURNING available_qty, version;
-- B có thể đang CHỜ row lock; không giả định đã có kết quả ngay.
```

**Terminal A:**

```sql
COMMIT;
```

Sau khi A commit, lệnh ở terminal B có thể tiếp tục, kiểm tra điều kiện trên hàng đã cập nhật và trả `3 | 2`; sau đó **terminal B** chạy `COMMIT`. Dùng connection thứ ba kiểm tra:

```sql
SELECT available_qty, version
FROM practice_inventory WHERE sku = 'BOOK-001';
-- 3 | 2
```

Nếu A rollback thay vì commit, B sẽ tính từ trạng thái hàng trước thay đổi của A và trả kết quả phù hợp; điều này đúng vì thao tác A chưa phải một reservation thành công. **Thành công của câu `UPDATE` B vẫn chưa là thành công nghiệp vụ cuối cùng trước `COMMIT`**.

### 6.2. Thí nghiệm chống bán quá số tồn: hai lần đặt 7

Reset qty=10, version=0. Mỗi phiên chạy câu lệnh tương tự:

```sql
UPDATE practice_inventory
SET available_qty = available_qty - 7,
    version = version + 1
WHERE sku = 'BOOK-001' AND available_qty >= 7
RETURNING available_qty, version;
```

Trong một lịch mà cả hai transaction lần lượt đi đến kết thúc và không có nhập kho, **đúng một update trả 1 hàng** và giảm tồn xuống 3; update còn lại trả **0 hàng** vì tồn 3 không còn đáp ứng `>= 7`. Nếu transaction thứ nhất rollback, transaction thứ hai vẫn có thể được chấp nhận; vì vậy kết luận phải xét **những transaction thực sự commit**.

Ở tầng API, 0 hàng có thể được ánh xạ thành `OUT_OF_STOCK` hoặc `NOT_FOUND` tùy việc row có tồn tại; phải phân biệt bằng một bước đọc phù hợp hoặc định nghĩa response gộp rõ ràng. Không trả thành công chỉ vì câu SQL chạy mà không ném exception.

### 6.3. Phân biệt precondition và constraint

`CHECK (available_qty >= 0)` là **lớp bảo vệ cuối cùng** tại database. Nhưng nếu chỉ dùng:

```sql
UPDATE practice_inventory
SET available_qty = available_qty - 7
WHERE sku = 'BOOK-001';
```

Lần thứ hai có thể gây lỗi `CHECK` và rollback statement/transaction, thay vì trả về **0 hàng** như một nhánh nghiệp vụ không đủ tồn. Câu có điều kiện `WHERE available_qty >= :qty` cho phép **diễn đạt rõ precondition** và phân loại kết quả; vẫn nên giữ `CHECK` để bảo vệ trước lỗi code/đường ghi khác.

## 7. Cách sửa thứ ba: khóa bi quan `SELECT ... FOR UPDATE`

Nếu business rule cần đọc nhiều thuộc tính rồi quyết định một thay đổi phức tạp, có thể khóa hàng trước khi đọc:

```sql
BEGIN;

SELECT available_qty, version
FROM practice_inventory
WHERE sku = 'BOOK-001'
FOR UPDATE;
-- Đọc giá trị sau khi đã giữ row lock thích hợp.

-- Ứng dụng kiểm tra available_qty >= requested_qty,
-- rồi ghi UPDATE trong cùng transaction.

COMMIT;
```

Khi A đã giữ khóa qua `SELECT ... FOR UPDATE` và chưa commit, B chạy `SELECT ... FOR UPDATE` cùng hàng thường **phải đợi**. Sau A commit, B đọc phiên bản đã cập nhật dưới `READ COMMITTED` và tính trên số tồn mới. Muốn an toàn phải **giữ khóa đến hết transaction ghi**; `SELECT FOR UPDATE` trong một transaction rồi `UPDATE` ở transaction khác không bảo vệ được khoảng giữa.

### 7.1. Khi nào dùng khóa bi quan?

| Tiêu chí | CAS bằng `version` | Atomic conditional `UPDATE` | `SELECT FOR UPDATE` |
|---|---|---|---|
| Business logic | Có thể tính trong Java, kiểm tra version lúc ghi | Tốt cho phép toán/điều kiện biểu diễn trong một SQL statement | Hữu ích khi cần đọc nhiều trường rồi quyết định trong transaction |
| Khi có contention | Một số writer bị xung đột và phải retry | Writer đợi khóa ngắn rồi đánh giá lại điều kiện | Writer đợi từ thời điểm `SELECT FOR UPDATE` |
| Thời gian giữ khóa | Thường ở giai đoạn ghi/transaction | Thường ngắn nếu statement và transaction ngắn | Có thể dài hơn nếu logic xử lý nhiều bước |
| Tránh mất cập nhật | Có, khi mọi writer cập nhật version đúng | Có cho bất biến biểu diễn ngay trong SQL | Có, nếu các writer cùng tuân thủ locking protocol |
| Rủi ro | Retry nhiều, writer ngoài không tăng version | Điều kiện SQL thiếu, nghiệp vụ nhiều hàng phức tạp | Deadlock, timeout, giữ khóa qua HTTP, throughput giảm |

Không gọi dịch vụ HTTP chậm, chờ người dùng nhập liệu hoặc thực hiện xử lý tốn nhiều giây **khi đang giữ khóa DB**. Với nhiều hàng, khóa theo thứ tự nhất quán nhằm giảm deadlock; vẫn cần timeout và khả năng retry phù hợp. `FOR UPDATE SKIP LOCKED` dùng tốt cho một số job queue, nhưng **không phải phương án thay thế mặc định** cho kiểm tra tồn kho: bỏ qua hàng bị khóa có thể làm một SKU trông như không tồn tại.

## 8. Isolation level không thay thế việc xác định bất biến

PostgreSQL có các mức isolation và cơ chế xử lý cập nhật cạnh tranh khác nhau. Ở `READ COMMITTED`, hai lần `SELECT` riêng có thể quan sát trạng thái khác nhau; một phép read–modify–write tính ở Java rồi ghi giá trị cũ như phần 3 dễ xảy ra lost update. Ở `REPEATABLE READ`/`SERIALIZABLE` của PostgreSQL, một số cập nhật tranh chấp sau khi transaction đã đọc snapshot cũ có thể gây `serialization_failure` (`40001`) thay vì ghi đè im lặng.

Nhưng nâng isolation **không phải thuốc thay cho thiết kế đúng**:

- Giao dịch `SERIALIZABLE` phải có **retry toàn transaction** khi nhận `40001`, không chỉ retry riêng câu UPDATE với dữ liệu tính từ snapshot cũ.
- Không thể chỉ bật isolation cao rồi bỏ kiểm tra `available_qty >= :qty` nếu ứng dụng có các đường ghi khác nhau hoặc business invariant trải qua nhiều bảng.
- Với nghiệp vụ chỉ cần trừ một SKU, atomic conditional `UPDATE` thường đơn giản hơn và tránh thêm retry không cần thiết.
- Isolation của một local database transaction không giải quyết tính nguyên tử với broker, HTTP hoặc một database khác.
- Những sự kiện đã gửi ra ngoài trước khi transaction commit **không được DB rollback**; phải dùng outbox/idempotency và trạng thái nghiệp vụ phù hợp.

Khi gặp `40P01` (deadlock) hoặc `40001` (serialization failure), hãy xem chính xác SQLSTATE và đường dữ liệu, giới hạn lần retry và backoff có jitter; không retry vô hạn khi hệ thống đang quá tải. `23505` (unique violation) có thể là tín hiệu request idempotent đã được xử lý, cũng có thể là lỗi nghiệp vụ khác; không phân loại mọi exception thành transient.

## 9. Java/Spring JDBC: triển khai cập nhật có điều kiện

Nếu thao tác chỉ là giữ số lượng từ một SKU, mẫu `JdbcTemplate.update(...)` với câu SQL nguyên tử dễ kiểm chứng hơn đọc tồn kho rồi tính trong Java. Ví dụ service sau **không gửi HTTP, không đọc từ replica** và trả kết quả dựa vào đúng số hàng cập nhật:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class StockReservationService {
    private final JdbcTemplate jdbc;

    public StockReservationService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public boolean tryReserve(String sku, int requestedQty) {
        if (sku == null || sku.isBlank() || requestedQty <= 0) {
            throw new IllegalArgumentException("Invalid SKU or quantity");
        }

        int updated = jdbc.update("""
                UPDATE practice_inventory
                   SET available_qty = available_qty - ?,
                       version = version + 1
                 WHERE sku = ? AND available_qty >= ?
                """, requestedQty, sku, requestedQty);

        if (updated == 0) {
            return false; // SKU không tồn tại hoặc không đủ số tồn tại thời điểm UPDATE.
        }
        if (updated != 1) {
            throw new IllegalStateException("Expected exactly one inventory row");
        }
        return true;
    }
}
```

**Những điều kiện phải đúng để đoạn mã an toàn:**

- `sku` có **khóa duy nhất/primary key**. Nếu không, một `UPDATE` có thể trừ nhiều hàng và `updated != 1` không phải tình huống bình thường.
- `@Transactional` được áp dụng qua **Spring proxy** và `JdbcTemplate` kết nối đúng datasource được transaction manager quản lý. Trong ví dụ một SQL statement, chính tính nguyên tử của statement đã xử lý cập nhật hàng; transaction đặc biệt cần thiết nếu sau đó còn tạo reservation/order trong cùng DB.
- Nếu `tryReserve` là method được gọi qua proxy và không tham gia **outer transaction** có sẵn, caller chỉ nhận `true` sau khi transaction interceptor đã commit thành công. Nếu đã có outer transaction, `true` từ method con **chưa** phải commit cuối cùng; caller không được gửi xác nhận bền vững dựa riêng vào nó.
- `false` **không phân biệt chính xác** SKU không tồn tại với thiếu hàng. Nếu hợp đồng API cần phân biệt, thực hiện bước đọc phù hợp và xử lý race trong việc đưa ra thông tin; tránh dùng một `SELECT` không khóa trước `UPDATE` làm ranh giới bảo vệ chính.
- Kết quả success của câu SQL chưa bảo đảm durability xuyên mất region, failover hoặc external side effects; cần chính sách commit/replication và đối soát phù hợp.

### 9.1. Nếu cần trừ kho và ghi một reservation thì sao?

**Cả việc trừ kho và tạo reservation phải nằm trong một local transaction** nếu nghiệp vụ yêu cầu hai thay đổi cùng thành công. Không viết kiểu:

```text
UPDATE inventory và commit
process crash
INSERT reservation chưa thực hiện
```

Thiết kế này có thể làm kho giảm nhưng không có bằng chứng đơn nào chiếm số hàng đó. Một giao thức trong cùng transaction có thể là:

```sql
BEGIN;

UPDATE practice_inventory
SET available_qty = available_qty - 4,
    version = version + 1
WHERE sku = 'BOOK-001' AND available_qty >= 4
RETURNING sku, available_qty;

-- Chỉ khi UPDATE trả đúng 1 hàng, mới INSERT reservation/order.
-- Nếu UPDATE trả 0, rollback hoặc kết thúc nhánh từ chối hợp lệ.
-- Nếu INSERT reservation lỗi, rollback cả transaction để hoàn tồn kho.

COMMIT;
```

Đoạn trên là **khung điều phối**, không phải script tự động hoàn chỉnh vì chưa có schema reservation. Cần kiểm tra số hàng UPDATE trong **ứng dụng** trước khi quyết định chạy `INSERT`. Có thể phát sinh outbox event **trong cùng transaction** để dispatcher gửi thông báo sau; không gửi email/broker message trước commit chỉ vì UPDATE trả một hàng.

## 10. Java/JPA: `@Version` ngăn cập nhật dựa trên entity cũ

JPA hỗ trợ optimistic locking thông qua `@Version`. Với PostgreSQL table đã tạo, entity có thể ánh xạ:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "practice_inventory")
public class InventoryItem {
    @Id
    private String sku;

    @Column(name = "available_qty", nullable = false)
    private int availableQty;

    @Version
    @Column(name = "version", nullable = false)
    private long version;

    protected InventoryItem() {} // JPA

    public void reserve(int requestedQty) {
        if (requestedQty <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (availableQty < requestedQty) {
            throw new IllegalStateException("Out of stock");
        }
        availableQty -= requestedQty;
    }
}
```

Và service ứng dụng sử dụng persistence context trong transaction:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JpaInventoryService {
    @PersistenceContext
    private EntityManager em;

    @Transactional
    public void reserveOnce(String sku, int quantity) {
        InventoryItem item = em.find(InventoryItem.class, sku);
        if (item == null) {
            throw new IllegalArgumentException("SKU not found");
        }
        item.reserve(quantity);
        // Provider thực thi UPDATE với version check khi flush/commit.
        // Không cần em.flush() chỉ để làm transaction được commit.
    }
}
```

Với Hibernate và các provider tuân thủ optimistic locking, SQL update tương ứng sẽ dùng **giá trị version đã đọc trong điều kiện** và cập nhật version; nếu một writer khác đã đổi row/version, update có thể ảnh hưởng 0 hàng và provider phát sinh lỗi optimistic lock (lúc flush hoặc commit). Tên exception có thể là `OptimisticLockException` của JPA hoặc loại chuyển đổi tương ứng trong Spring như `ObjectOptimisticLockingFailureException`.

### 10.1. Xử lý optimistic conflict ở bên ngoài transaction thất bại

Phần đọc/tính/ghi phải **chạy lại trong transaction mới**, không tiếp tục dùng cùng `EntityManager` và entity đã stale sau khi transaction gặp optimistic locking failure. Một orchestrator ngoài transaction proxy có thể thực hiện tối đa vài lần theo chính sách:

```text
reserveWithRetry(sku, qty, operationId):
  repeat tối đa N attempts:
    gọi transactional bean reserveOnce(...) bằng transaction mới
    nếu commit thành công: trả SUCCESS
    nếu optimistic conflict: backoff nhỏ có jitter, đọc lại ở lần sau
    nếu OUT_OF_STOCK: trả kết quả nghiệp vụ, không retry mù
    nếu commit outcome unknown: ngừng retry và đối soát operationId
  quá retry budget: trả lỗi contention/deadline theo hợp đồng
```

`@Transactional` trên một method và tự gọi `this.reserveOnce()` **không bảo đảm transaction proxy được áp dụng** khi self-invocation. Cần tách orchestrator và transactional bean hoặc dùng transaction manager thích hợp, đồng thời chắc chắn outer transaction không khiến các lần retry cùng tham gia một transaction đã lỗi.

### 10.2. Cẩn thận với bulk/native updates bỏ qua `@Version`

Một câu JPQL bulk update hoặc SQL native có thể **không tự áp dụng cơ chế version check/increment** của entity manager. Nếu nơi khác sửa `practice_inventory.available_qty` nhưng không tăng `version`, writer JPA không nhất thiết phát hiện trạng thái đã thay đổi. Tất cả writer phải tuân thủ cùng hợp đồng version và ranh giới transaction. Khi kết hợp JPA entity đang managed với native UPDATE trực tiếp, cân nhắc persistence context stale: cần reload/clear/refresh có kiểm soát, không tin entity cũ phản ánh ngay DB mới.

### 10.3. `saveAndFlush()` không thay cho `COMMIT`

Một optimistic conflict có thể được phát hiện khi provider flush, nhưng transaction **vẫn có thể lỗi ở commit** vì deferred constraints, I/O hoặc rollback-only. Spring `@Transactional` thường thực hiện commit **sau khi thân service method return**; timer hoặc `try/catch` nằm trong thân method có thể không thấy lỗi commit do interceptor ném ra. Nếu API cần bảo đảm ghi đã được xác nhận, quan sát kết quả **sau ranh giới transaction được sở hữu thật**.

## 11. Từ concurrency-safe tới retry-safe: khóa idempotency

Conditional `UPDATE` ngăn hai writer trừ tồn dựa trên dữ liệu cũ; nó **không tự ngăn cùng một yêu cầu được gửi hai lần**. Giả sử client gửi `reserve 3`, DB commit thành công nhưng response mất trên mạng. Client retry nguyên yêu cầu với operation ID mới; một câu `UPDATE qty = qty - 3 WHERE qty >= 3` khác có thể tiếp tục trừ thêm 3. Đúng ở cấp statement nhưng **sai ở cấp nghiệp vụ**.

Vì vậy, tạo **operation ID ổn định** cho một ý định đặt hàng và lưu kết quả nghiệp vụ trong cùng local transaction. Ví dụ bảng ghi nhận reservation:

```sql
CREATE TABLE practice_reservations (
    operation_id UUID PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES practice_inventory(sku),
    reserved_qty INTEGER NOT NULL CHECK (reserved_qty > 0),
    request_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Một giao thức đơn giản trong transaction trên primary:

```text
Nhận (operationId, sku, qty, requestHash):
  BEGIN;
  INSERT practice_reservations(...) ON CONFLICT (operation_id) DO NOTHING;
  nếu INSERT trả 0 hàng:
    đọc reservation đã commit theo operationId
    nếu payload/hash khác: từ chối dùng lại ID với yêu cầu khác
    nếu trùng: trả kết quả đã lưu, KHÔNG trừ kho lần nữa
  nếu INSERT trả 1 hàng:
    UPDATE practice_inventory
      SET available_qty=available_qty-qty, version=version+1
      WHERE sku=? AND available_qty>=qty
    nếu UPDATE trả 0: ROLLBACK cả reservation vừa tạo; trả OUT_OF_STOCK
    nếu UPDATE trả 1: COMMIT; trả RESERVED
```

`INSERT ... ON CONFLICT` là cơ chế khử trùng lặp dựa trên unique key; khi hai transaction tranh cùng operation ID, PostgreSQL có thể phải đợi kết quả transaction còn lại để quyết định conflict. **Không được xem row `reservation` đã chèn là thành công trước khi inventory update và transaction commit.** Với business rejection cần được tái phát nhất quán sau retry, có thể thiết kế trạng thái `REJECTED` được lưu có chủ đích trong transaction riêng theo hợp đồng, thay vì rollback rồi quên kết quả; mô hình tối giản ở trên chỉ bảo vệ các reservation đã được nhận thành công.

Một thiết kế production cũng cần chính sách cho timeout/connection loss ngay tại `COMMIT`, hash payload có phiên bản, chống trùng event, audit và giới hạn retry. Không đặt toàn bộ dữ liệu cá nhân của request vào metric label hoặc log chỉ để gỡ lỗi idempotency.

## 12. Kiểm thử đồng thời có điều khiển bằng hai connection Java

Thực hành hai terminal ở phần 3 đủ để chứng minh lỗi, nhưng kiểm thử tích hợp cần lặp lại với hai thread **đọc cùng giá trị trước khi một thread ghi**. Dùng `CyclicBarrier` giúp đồng bộ lịch chạy thay vì phụ thuộc `Thread.sleep` ngẫu nhiên. Các ví dụ sau yêu cầu **`DataSource` trỏ đến database test**, pool có ít nhất 2 connection, PostgreSQL và bảng `practice_inventory` đã được chuẩn bị.

### 12.1. Chạy hai writer sai với barrier sau lúc đọc

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public final class LostUpdateProbe {
    private LostUpdateProbe() {}

    static void unsafeReserve(DataSource ds, int amount, CyclicBarrier bothRead)
            throws Exception {
        try (Connection c = ds.getConnection()) {
            c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);
            try {
                int seen;
                try (PreparedStatement s = c.prepareStatement("""
                        SELECT available_qty
                        FROM practice_inventory WHERE sku = ?
                        """)) {
                    s.setString(1, "BOOK-001");
                    try (ResultSet r = s.executeQuery()) {
                        if (!r.next()) throw new IllegalStateException("Missing SKU");
                        seen = r.getInt(1);
                    }
                }

                // Hai thread đã đọc xong trước khi cho phép bất kỳ UPDATE nào.
                bothRead.await(10, TimeUnit.SECONDS);

                if (seen < amount) throw new IllegalStateException("Out of stock");
                int desired = seen - amount; // Giá trị tính từ bản đọc cũ.
                try (PreparedStatement s = c.prepareStatement("""
                        UPDATE practice_inventory
                        SET available_qty = ?
                        WHERE sku = ?
                        """)) {
                    s.setInt(1, desired);
                    s.setString(2, "BOOK-001");
                    if (s.executeUpdate() != 1) {
                        throw new IllegalStateException("Missing row");
                    }
                }
                c.commit();
            } catch (Exception e) {
                try { c.rollback(); }
                catch (SQLException rollbackError) { e.addSuppressed(rollbackError); }
                throw e;
            }
        }
    }
}
```

Hai thread lần lượt truyền `amount=3` và `amount=4` cùng **một** `CyclicBarrier(2)`. Cả hai sẽ đọc 10 trước khi thực thi `UPDATE`; kết quả cuối có thể là **6 hoặc 7** tùy writer commit sau cùng, nhưng **không phải 3** nếu cả hai thành công. Đó là test chứng minh read–modify–write sai theo lịch cạnh tranh, không phải cách triển khai cần sử dụng trong production.

### 12.2. Thay bằng writer an toàn, không dùng giá trị đã đọc trước

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

public final class ConditionalUpdateProbe {
    private ConditionalUpdateProbe() {}

    static int reserve(DataSource ds, int amount, CyclicBarrier sameStart)
            throws Exception {
        try (Connection c = ds.getConnection()) {
            c.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
            c.setAutoCommit(false);
            try {
                sameStart.await(10, TimeUnit.SECONDS);
                int changed;
                try (PreparedStatement s = c.prepareStatement("""
                        UPDATE practice_inventory
                           SET available_qty = available_qty - ?,
                               version = version + 1
                         WHERE sku = ? AND available_qty >= ?
                        """)) {
                    s.setInt(1, amount);
                    s.setString(2, "BOOK-001");
                    s.setInt(3, amount);
                    changed = s.executeUpdate();
                }
                c.commit();
                return changed;
            } catch (Exception e) {
                try { c.rollback(); }
                catch (SQLException rollbackError) { e.addSuppressed(rollbackError); }
                throw e;
            }
        }
    }
}
```

`CyclicBarrier` ở đây chỉ đưa hai request đến gần nhau về thời điểm; **tính đúng đắn thuộc về câu SQL có điều kiện**, không phụ thuộc barrier. Kiểm thử cả `amount=(3,4)` và `(7,7)`. Nếu dùng `ExecutorService`, code điều phối có thể là:

```java
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.sql.DataSource;

// Hàm được gọi bởi integration test sau khi reset qty=10, version=0.
static void verifyTwoSevenRequests(DataSource ds) throws Exception {
    ExecutorService pool = Executors.newFixedThreadPool(2);
    CyclicBarrier start = new CyclicBarrier(2);
    try {
        Future<Integer> a = pool.submit(() -> ConditionalUpdateProbe.reserve(ds, 7, start));
        Future<Integer> b = pool.submit(() -> ConditionalUpdateProbe.reserve(ds, 7, start));
        int changed = a.get(20, java.util.concurrent.TimeUnit.SECONDS)
                    + b.get(20, java.util.concurrent.TimeUnit.SECONDS);
        if (changed != 1) throw new AssertionError("Expected exactly one reservation");
        // Dùng một connection độc lập đọc lại qty=3 và version=1.
    } finally {
        pool.shutdownNow();
    }
}
```

Đoạn điều phối là **minh họa cho method trong test class** có `DataSource` được cấp bằng dependency injection. Để thành integration test hoàn chỉnh, thêm helper reset trong transaction test riêng, đọc lại số tồn bằng connection độc lập và assert kết quả; không dùng `@Transactional` trên toàn bộ test method nếu nó che ranh giới commit thực của hai worker. `Future.get()` giúp test chờ cả hai tác vụ kết thúc; test nên có deadline tổng thể để không treo vô hạn khi có lỗi hoặc pool quá nhỏ.

### 12.3. Những điều một test có `sleep` có thể bỏ sót

- Nếu scheduler cho thread A chạy hết trước khi B `SELECT`, lỗi lost update **không xảy ra** dù code vẫn sai; test chỉ chạy một lần và PASS là bằng chứng yếu.
- Nếu chỉ assert `available_qty >= 0`, hai yêu cầu đặt 7 có thể cùng được báo thành công mà tồn kho vẫn 3. Phải assert **số yêu cầu được chấp nhận và số tồn cuối**.
- Nếu test mở một `@Transactional` lớn bọc các task rồi framework rollback cuối test, có thể che lỗi commit hoặc làm readback sai trạng thái.
- Nếu cả hai thread dùng cùng một `Connection` hoặc datasource có pool size 1, test có thể vô tình tuần tự hóa các thao tác.
- Nếu DB đang ở `SERIALIZABLE` thay vì `READ COMMITTED`, một worker có thể gặp `40001` và biểu hiện khác; ghi rõ isolation thực tế của test.

## 13. Xử lý rollback, commit chưa rõ và side effect ngoài DB

**Có ba mức kết quả cần phân biệt:**

1. **SQL update trả 0 hàng:** precondition không đúng ở thời điểm cập nhật; không có reservation thành công từ câu đó.
2. **SQL update trả 1 hàng nhưng transaction rollback:** số tồn cuối không bị trừ bởi transaction đó; caller không được báo đặt hàng thành công.
3. **Mất kết nối trong lúc `COMMIT`:** caller **chưa biết** DB đã commit hay chưa; không được suy exception đồng nghĩa chắc chắn rollback.

Trong trường hợp thứ ba, một transaction idempotent gắn `operation_id` và reservation là **nguồn có thẩm quyền để đối soát**. Ví dụ nếu database primary đã hoạt động và tra cứu cho thấy operation ID tồn tại với payload khớp, có thể trả kết quả đã lưu; nếu hệ đang failover hoặc replica còn lag, không kết luận thất bại từ một lần SELECT chưa đủ tin cậy.

### 13.1. Không gọi HTTP hoặc gửi message trước commit dựa trên kết quả UPDATE

Phản ví dụ:

```text
BEGIN
UPDATE inventory ... WHERE qty>=requested  -> trả 1 hàng
Gửi event OrderReserved tới broker             -> thành công
INSERT order/reservation                       -> lỗi unique/FK
ROLLBACK database

Broker đã báo reserved, nhưng database không commit reservation.
```

Gửi broker sau commit bằng callback trong memory lại có một **crash window** khác: DB commit thành công nhưng process chết trước khi publish. Với event quan trọng, dùng **transactional outbox**: cùng transaction ghi inventory, reservation và outbox record; một worker dispatcher sau đó phát event với `event_id` ổn định, consumer khử trùng lặp vì delivery thường có thể lặp. Outbox giải quyết atomicity của **ý định phát event với dữ liệu DB**, không tự biến HTTP hoặc broker thành một phần của local SQL transaction.

### 13.2. Retry cần biết loại lỗi và ranh giới

| Kết quả | Có nên retry? | Điều kiện |
|---|---|---|
| Optimistic version mismatch | Có thể | Đọc lại/tính lại trong transaction mới, giới hạn attempts |
| `40001` serialization failure | Thường có thể | Retry **toàn transaction**, xử lý side effects idempotent |
| `40P01` deadlock | Thường có thể | Retry có backoff, điều tra thứ tự khóa/hotspot |
| Không đủ hàng (`UPDATE` trả 0) | Không tự retry vô hạn | Tùy chính sách hàng mới nhập; trả business rejection |
| `23505` unique violation | Không retry mù | Có thể là duplicate `operation_id` hoặc lỗi dữ liệu khác; kiểm tra payload |
| Mất kết nối trước/sau commit | Không thể mặc định | Dựa vào operation ID và kết quả đối soát trước khi tái thực hiện |

Một retry loop sai có thể gây **retry amplification**: nhiều client tranh cùng một SKU, bị xung đột rồi retry không giới hạn khiến pool/DB quá tải. Đặt max attempts, deadline, jitter và metric `retry_exhausted`; khi tranh chấp quá cao, cần admission control hoặc thay thiết kế phân chia hotspot.

## 14. Đối soát và quan sát tính đúng đắn dưới tải

Khi không có reservation ledger, thí nghiệm phần 3 chỉ quan sát được **số tồn kho cuối**, còn việc hai thao tác đã được nhận thành công phải ghi lại tại client/test. Với hệ thống có bảng `practice_reservations` và một **mốc initial stock = 10** được kiểm soát, có thể kiểm tra tổng lượng đã giữ và số tồn:

```sql
SELECT i.sku,
       i.available_qty,
       COALESCE(SUM(r.reserved_qty), 0) AS reserved_total,
       10 - COALESCE(SUM(r.reserved_qty), 0) AS expected_qty
FROM practice_inventory AS i
LEFT JOIN practice_reservations AS r ON r.sku = i.sku
WHERE i.sku = 'BOOK-001'
GROUP BY i.sku, i.available_qty;
```

Chỉ dùng công thức này khi bài lab **không có nhập hàng, hủy đơn, trả hàng hoặc reservation từ những lượt thử cũ**. Trước lượt thử cần reset có kiểm soát **cả số tồn và bảng reservation thử nghiệm** sau khi các connection khác đã đóng transaction. Production phải dùng ledger biến động tồn kho đầy đủ (`+ nhập`, `- giữ`, `+ trả`, `- xuất`, ...), không dùng hằng số `10` để suy tồn kho thực.

### 14.1. Metrics nên gắn vào business outcome và điểm contention

| Số đo | Ý nghĩa | Dấu hiệu bất thường |
|---|---|---|
| `reservation_attempts_total` | Số yêu cầu/attempt đến service theo định nghĩa | Cao hơn business operations quá nhiều do retry |
| `reservation_success_total` | Số reservation commit và được xác nhận theo contract | Counter success không trùng với số row SQL update |
| `reservation_rejected_total{reason="out_of_stock"}` | Kết quả từ chối nghiệp vụ hợp lệ | Tăng khi hot SKU thiếu hàng, không nhất thiết là DB outage |
| `reservation_conflict_total{strategy="version"}` | Số lần update không đổi hàng do version mismatch được xác nhận | Tăng đột biến báo hotspot/retry pressure |
| `reservation_retry_total` / `retry_exhausted` | Tần suất retry và cạn ngân sách | Retry storm có thể làm pool/DB tệ hơn |
| `db_pool_pending` / acquire latency | Chờ connection | Pool có thể bị nghẽn vì transaction giữ lock quá lâu |
| DB lock wait / deadlocks | Cạnh tranh transaction trên hàng | Hot row, thứ tự khóa hoặc transaction kéo dài |
| `commit_unknown_pending` | Yêu cầu đã gửi commit nhưng kết quả chưa biết | Cần đối soát, không tự thực hiện lại |
| `outbox_backlog_age` | Độ trễ phát event sau commit | Dữ liệu DB đúng nhưng downstream chưa nhận |

Không dùng `sku` của hàng triệu sản phẩm, `operation_id`, `customer_id` hay raw SQL parameters làm **metric labels** vì gây cardinality lớn và có thể lộ dữ liệu. Nếu cần điều tra một đơn hàng cụ thể, đặt correlation ID được bảo vệ trong logs/traces thay vì trong một metric series riêng cho mỗi ID.

### 14.2. PostgreSQL có thể cho thấy writer đang chờ khóa

Trong lúc terminal A đang giữ transaction mở còn terminal B đợi UPDATE, dùng một connection giám sát (với quyền phù hợp):

```sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST;
```

Nếu `wait_event_type = 'Lock'`, đó là một dấu hiệu của session đang đợi khóa tại thời điểm snapshot. Cần kết hợp lock owner, statement/transaction duration và error rate; **một ảnh chụp** không phải thống kê lịch sử đầy đủ. Không tự kill session hoặc tăng connection pool chỉ vì nhìn thấy khóa: thao tác atomic update đúng có thể **cần chờ hàng đang được cập nhật**; vấn đề vận hành là khóa kéo dài vượt ngân sách và tail latency.

### 14.3. Kiểm thử performance không được phá tính đúng đắn

Với SKU nóng, cả CAS, row lock và atomic UPDATE đều có thể giới hạn throughput bởi việc nhiều writer tranh **cùng một hàng**. Để đo năng lực, ghi rõ số client, tỉ lệ SKU nóng, số lượng requested, timeout, p95/p99 và aborted/retried transactions. Không kết luận một phương án tốt hơn chỉ từ throughput nếu nó **bỏ qua số lượng hàng đã bị trừ sai** hoặc báo thành công trước commit.

Khi tăng tải, không tắt khóa, bỏ `WHERE available_qty >= qty`, giảm độ bền commit hoặc tăng retry vô hạn để lấy con số QPS đẹp. Đó là đánh đổi tính đúng đắn dữ liệu lấy một phép đo hiệu năng không còn phản ánh yêu cầu nghiệp vụ.

## 15. Bảng kết quả mong đợi và các lỗi thiết kế thường gặp

Đây là **bảng nghiệm thu** sau khi reset trạng thái đúng cách giữa các ca. `version` tăng một lần cho **mỗi cập nhật thành công** ở các ví dụ đã dùng version; kịch bản lỗi ban đầu cố ý không tăng version.

| Phương án | Lịch đặt hàng | Kết quả dự kiến sau các transaction đã commit | PASS/FAIL |
|---|---|---|---|
| Read–modify–write sai, `SET qty = old - amount` | A=3, B=4, cả hai đọc 10 | Tồn cuối 6 hoặc 7; hai lời gọi đều trả thành công | **FAIL**, mất cập nhật |
| CAS `WHERE version=0`, chưa retry | A=3, B=4 cùng đọc version 0 | A thành công: 7/version1; B 0 hàng | PASS về phát hiện xung đột, **chưa hoàn tất B** |
| CAS, B đọc lại và retry trong transaction mới | A=3, B=4 | Cuối 3/version2, cả hai có kết quả thành công | **PASS** |
| Atomic conditional UPDATE | A=3, B=4 | Cả hai cập nhật 1 hàng; cuối 3/version2 | **PASS** |
| Atomic conditional UPDATE | A=7, B=7 | Một cập nhật 1 hàng, một cập nhật 0 hàng; cuối 3/version1 | **PASS** |
| Khóa `SELECT FOR UPDATE` đúng transaction | A=3, B=4 | Hai writer được tuần tự hóa, cuối 3 | **PASS**, nếu logic tính sau lock |
| JPA `@Version`, cùng đọc bản cũ | A=3, B=4 | Một transaction nhận optimistic failure; sau retry đúng cuối 3 | **PASS** khi caller retry/đối soát đúng |
| Retry cùng `operation_id` đã commit | Hai request cho cùng reservation 3 | Chỉ một reservation, tồn cuối 7 | **PASS** khi idempotency thực sự hoạt động |

### 15.1. Những nhầm lẫn cần nhận diện khi review code

- **“Hai SQL trong `@Transactional` thì không thể lost update.”** Sai: transaction chỉ xác định atomicity; một giá trị tính từ bản đọc cũ vẫn có thể bị writer sau ghi đè dưới isolation phù hợp.
- **“Có `CHECK (stock >= 0)` là hết oversell.”** Sai nếu hai reservation đều được chấp nhận nhưng chỉ một phép trừ được phản ánh ở số tồn cuối.
- **“`SELECT` rồi `UPDATE` trong một transaction là nguyên tử.”** Chúng là hai statement trong transaction, **không tự trở thành một phép đọc–kiểm tra–ghi được bảo vệ** dưới `READ COMMITTED`.
- **“Có cột version thì JPA/JDBC tự ngăn mất cập nhật.”** Sai nếu `WHERE` không kiểm tra version hoặc đường ghi khác không tăng version.
- **“Cứ retry câu UPDATE với version mới là được.”** Sai nếu new quantity vẫn tính từ giá trị cũ; phải đọc lại và đánh giá nghiệp vụ từ đầu.
- **“Cập nhật 0 hàng nhưng không ném exception nghĩa là thành công.”** Sai: rowcount là một phần của hợp đồng SQL có điều kiện.
- **“`UPDATE stock = stock - qty` luôn an toàn cho nghiệp vụ.”** Chưa đủ nếu không có điều kiện đủ hàng, ledger/order atomicity và idempotency.
- **“Mọi lỗi optimistic phải retry vô hạn.”** Sai: giới hạn retry, deadline, cancellation và fallback nghiệp vụ là cần thiết.
- **“`saveAndFlush()` là đã commit.”** Sai: JPA flush đồng bộ SQL trong transaction, commit có thể lỗi sau đó.
- **“Exception ở commit nghĩa là chắc chắn DB không ghi.”** Sai: mất phản hồi trong lúc commit có thể dẫn tới outcome chưa rõ.
- **“Bọc HTTP/email vào transaction DB làm các hệ thống commit cùng nhau.”** Sai: local transaction không rollback tác dụng bên ngoài.
- **“Một test concurrency chạy PASS một lần là đủ.”** Sai nếu test không đồng bộ lịch đọc để tái tạo race hoặc chỉ assert stock không âm.

## 16. Quy trình thực hành đầy đủ và checklist nghiệm thu

### 16.1. Thứ tự thực hành đề nghị

1. **Chuẩn bị:** tạo `practice_inventory` trên database test; mở hai `psql` độc lập, ghi lại `pg_backend_pid()` và isolation level.
2. **Chạy lỗi:** reset 10/version0, A/B đều `SELECT` trước khi ai cập nhật; A ghi 7, B ghi 6. Ghi lại số tồn cuối và giải thích vì sao **mất một lần trừ**.
3. **Thử CAS:** reset, A/B cùng đọc version0, A cập nhật version1, B bị từ chối 0 hàng; B bắt đầu transaction mới, đọc 7/version1 rồi cập nhật 3/version2.
4. **Thử atomic UPDATE:** reset, A trừ 3 giữ khóa, B trừ 4 đang chờ, A commit; B tiếp tục rồi commit. Đối chiếu tồn cuối 3/version2.
5. **Thử cạn hàng:** reset, chạy hai yêu cầu trừ 7; kiểm tra **chỉ một** yêu cầu được nhận và tồn cuối 3/version1.
6. **Thử JPA/JDBC:** triển khai `@Version` hoặc `JdbcTemplate.update` đúng nơi, bảo đảm ranh giới `@Transactional` được áp dụng và rowcount/optimistic exception được xử lý.
7. **Thử đồng thời tự động:** dùng hai connection và barrier ở integration test; không dùng mock repository để tuyên bố đã tái tạo row-lock race.
8. **Thử idempotency:** thêm `operation_id`; gửi lại cùng yêu cầu sau khi đã commit, phải trả kết quả cũ mà không trừ hàng lần nữa.
9. **Thử rollback và outcome chưa rõ:** cố ý làm transaction lỗi sau UPDATE, kiểm tra inventory khôi phục; với mất kết nối khi commit, không retry mù và đối soát với nguồn có thẩm quyền.
10. **Đo vận hành:** quan sát row-lock waits, optimistic conflicts, retry count, pool acquisition và p95/p99; báo cáo throughput kèm **số reservation đúng**.

### 16.2. Checklist trước khi áp dụng lên nghiệp vụ thật

1. **Bất biến đã được viết thành điều kiện kiểm chứng chưa?** Không chỉ `stock >= 0`, mà còn đối chiếu stock với mọi reservation/ledger đã commit?
2. **Phép read–modify–write nằm ở đâu?** Có Java code dùng `setStock(oldStock - qty)` mà không có version/lock/atomic SQL không?
3. **Cập nhật có điều kiện kiểm tra đúng trạng thái hiện thời chưa?** Có `WHERE available_qty >= :qty` hoặc `WHERE version = :expected` với số hàng cập nhật được kiểm tra không?
4. **Mọi writer tuân thủ cùng giao thức chưa?** API, job, bulk JPQL, native SQL, migration và batch có cùng quy tắc tăng version không?
5. **Bản ghi reservation/order có cùng commit với số tồn không?** Nếu một bước lỗi, cả hai có rollback cùng nhau không?
6. **Client retry có được khử trùng lặp chưa?** Operation ID, unique key, request hash và kết quả cũ có tồn tại tại nguồn có thẩm quyền không?
7. **Lỗi optimistic/serialization có transaction mới để retry không?** Có backoff/jitter, deadline, max attempts và không retry business rejection vô hạn?
8. **Có xử lý outcome chưa rõ ở COMMIT không?** Không kết luận rollback chỉ từ lỗi kết nối hoặc replica lag?
9. **Đã kiểm tra hai connection thật chưa?** Có barrier, kết quả hàng cuối, số request được nhận, rollback/commit và điều kiện cạn hàng?
10. **Có giới hạn tài nguyên khi contention tăng không?** Không giữ row lock trong lúc gọi HTTP, không tăng pool hoặc retry một cách mù quáng?
11. **Có telemetry không lộ dữ liệu nhạy cảm không?** Đo conflicts, retry, errors, lock wait, idempotency nhưng không gắn ID riêng lẻ vào metric labels?
12. **Đã chọn đúng cơ chế cho bài toán chưa?** SQL update nguyên tử cho phép trừ đơn giản; version check cho read–modify–write; row lock hoặc isolation cao khi nghiệp vụ phức tạp hơn?

**Kết luận:** Mất cập nhật không nhất thiết do database bỏ qua transaction, mà thường do **ứng dụng đọc một trạng thái, tính trên dữ liệu đã cũ rồi ghi đè bằng một giá trị cố định**. Với PostgreSQL `READ COMMITTED`, hai giao dịch đều có thể commit thành công trong khi bất biến nghiệp vụ bị sai. Để sửa, hãy **đưa điều kiện của giá trị hiện tại vào chính câu `UPDATE`** hoặc kiểm tra `version` và retry toàn phép đọc–tính–ghi khi xung đột; nếu cần, dùng row lock trong transaction đúng phạm vi. Sau đó kiểm chứng bằng hai kết nối thật, ledger/order atomicity và idempotency — vì **đúng dưới cạnh tranh** mới là tiêu chí của persistence đáng tin cậy.




