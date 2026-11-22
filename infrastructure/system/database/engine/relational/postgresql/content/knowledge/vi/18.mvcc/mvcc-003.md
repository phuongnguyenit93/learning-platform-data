# Snapshot và quy tắc nhìn thấy dữ liệu

Giả sử hai nhân viên cùng mở ứng dụng bán hàng. Người thứ nhất đang xem tồn kho, người thứ hai sửa số lượng rồi lưu. Khi người thứ nhất truy vấn lại, họ có nhìn thấy số mới ngay không? Một giao dịch đang chạy có nhìn thấy dữ liệu chưa `COMMIT` của giao dịch khác không? Vì sao câu `SELECT` chỉ thấy một phiên bản của hàng, trong khi `UPDATE` lại có thể phải chờ một transaction khác? Và vì sao một transaction đọc lâu khiến PostgreSQL chưa thể dọn các phiên bản cũ?

Những câu hỏi này được trả lời bởi **Multi-Version Concurrency Control (MVCC)** và đặc biệt là **snapshot** cùng **quy tắc nhìn thấy dữ liệu** (*visibility rules*) của PostgreSQL.

PostgreSQL không buộc mọi câu lệnh đọc phải chờ mọi câu lệnh ghi. Thay vào đó, nhiều phiên bản của một hàng có thể cùng tồn tại vật lý trong một khoảng thời gian. Truy vấn sử dụng một **snapshot** để quyết định phiên bản nào được xem là hợp lệ trong ngữ cảnh hiện tại. Snapshot không đơn giản là “thời gian hiện tại”; nó phản ánh trạng thái những giao dịch đã hoàn tất, đang chạy hoặc chưa bắt đầu tại mốc chụp theo quy tắc quản lý transaction ID của PostgreSQL.

Bài học giải thích:

- Bản chất MVCC, phiên bản hàng (*tuple version*), các trường hệ thống `xmin`, `xmax` và `ctid`.
- Snapshot chứa gì về mặt khái niệm và quy tắc phân loại một tuple là **visible/invisible**.
- Giao dịch thấy **những thay đổi của chính nó** như thế nào.
- Snapshot **theo từng câu lệnh** trong `READ COMMITTED` và **theo giao dịch** trong `REPEATABLE READ`.
- Điểm khác biệt của `SERIALIZABLE`, cùng các hiện tượng dirty read, non-repeatable read, phantom và write skew.
- Các ngoại lệ cần hiểu khi `UPDATE`, `DELETE`, `SELECT FOR UPDATE` hoặc `INSERT ... ON CONFLICT` gặp thay đổi đồng thời.
- Tác động của snapshot tồn tại lâu đến `VACUUM`, bảng phình to và việc thu hồi phiên bản đã chết.
- Cách quan sát bằng `pg_current_snapshot()`, `pg_stat_activity`, system columns và các kịch bản hai session `psql`.
- Cách ứng dụng Java/JDBC chọn isolation level, quản lý transaction và retry an toàn.

> **Phạm vi:** Nội dung tập trung vào PostgreSQL hiện đại. Các ví dụ thao tác được thiết kế cho database lab và cần thực hiện ở hai connection riêng khi có chỉ dẫn. Trường system column và snapshot internals dùng để học/chẩn đoán, không phải API ổn định thay cho khóa nghiệp vụ. Không dựa vào giá trị transaction ID hay địa chỉ tuple làm định danh dữ liệu lâu dài.

## 1. Tại sao PostgreSQL cần nhiều phiên bản hàng?

Nếu cơ sở dữ liệu chỉ có **một bản vật lý duy nhất cho mỗi hàng**, một transaction đang sửa giá trị có thể khiến những transaction đọc phải chờ hoặc nhìn thấy dữ liệu đang sửa dở. MVCC cho phép tách hai câu hỏi:

1. **Phiên bản nào đang tồn tại vật lý trên page?**
2. **Phiên bản nào được phép xuất hiện trong kết quả của truy vấn này?**

Ví dụ một sản phẩm:

```text
Trước UPDATE:                         Sau UPDATE, chưa dọn VACUUM:

product_id=1                           ┌─────────────────────────────┐
quantity=10                            │ Version A: quantity = 10    │
                                      │ tạo bởi transaction cũ       │
                                      └─────────────────────────────┘
                                      ┌─────────────────────────────┐
                                      │ Version B: quantity = 8     │
                                      │ tạo bởi transaction mới      │
                                      └─────────────────────────────┘

Snapshot của reader cũ  ───────────────► Version A
Snapshot của reader mới ───────────────► Version B (sau khi update commit)
```

Đây là sơ đồ khái niệm. Trong PostgreSQL, `UPDATE` thường tạo một **tuple version mới** thay vì sửa đè payload của phiên bản cũ như một bản ghi duy nhất; storage có thêm những tối ưu như HOT update và liên kết tuple. Không nên suy ra tất cả phiên bản luôn nằm trên cùng page hoặc có định dạng liên kết đơn giản đúng như hình.

### Lợi ích chính

- Reader thường **không phải chờ writer chỉ vì đang đọc một hàng** bằng `SELECT` thông thường.
- Writer có thể cập nhật mà những reader đã có snapshot cũ vẫn nhìn thấy phiên bản thích hợp.
- Transaction có thể được cung cấp cái nhìn nhất quán theo isolation level.
- VACUUM có cơ sở để loại phiên bản cũ khi không còn snapshot nào cần nó.

**Không có nghĩa PostgreSQL “không bao giờ khóa”.** Các thao tác ghi cạnh tranh, `SELECT ... FOR UPDATE`, DDL, khóa bảng và các tình huống đồng thời khác vẫn dùng locking.

## 2. Phân biệt hàng logic và phiên bản tuple vật lý

Trong ứng dụng, `product_id = 1` thường là danh tính của **một hàng logic**. Trong PostgreSQL, một hàng logic có thể trải qua nhiều **tuple version**:

```text
Logic: Product #1
  |
  +-- tuple version V1: quantity=10
  |       INSERT bởi transaction T10
  |
  +-- tuple version V2: quantity=8
  |       UPDATE bởi transaction T20
  |
  +-- tuple version V3: quantity=5
          UPDATE bởi transaction T30
```

Ở một thời điểm, một snapshot hợp lệ thường chọn **phiên bản nhìn thấy được theo quy tắc MVCC**. Transaction mới nhìn thấy V3 sau khi T30 commit; transaction có snapshot trước T30 có thể còn nhìn thấy V2.

Điều cần phân biệt:

| Khái niệm | Ý nghĩa |
|---|---|
| **Khóa nghiệp vụ/primary key** | Danh tính logic do schema quy định, ví dụ `product_id`. |
| **Tuple version** | Một biểu diễn vật lý của hàng tại một trạng thái dữ liệu cụ thể. |
| **`xmin`** | Metadata transaction tạo tuple version. |
| **`xmax`** | Metadata liên quan transaction xóa/thay thế/khóa tuple, cần diễn giải cùng các cờ và trạng thái. |
| **`ctid`** | Vị trí vật lý của một phiên bản tuple trong bảng tại thời điểm hiện tại. |
| **Snapshot** | Ngữ cảnh quyết định tuple version nào hợp lệ đối với truy vấn. |

**Primary key không đổi chỉ vì UPDATE tạo tuple mới.** Ngược lại, `ctid` có thể đổi và không nên dùng như khóa ổn định của đối tượng nghiệp vụ.

## 3. Chuẩn bị dữ liệu thử nghiệm

Tạo schema riêng và hai bảng:

```sql
CREATE SCHEMA IF NOT EXISTS lesson_mvcc;

CREATE TABLE lesson_mvcc.products (
    product_id BIGINT PRIMARY KEY,
    product_name TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE lesson_mvcc.order_lines (
    order_line_id BIGINT PRIMARY KEY,
    product_id BIGINT NOT NULL
        REFERENCES lesson_mvcc.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);

INSERT INTO lesson_mvcc.products (
    product_id, product_name, quantity, price
)
VALUES
    (1, 'Bàn phím', 10, 400000),
    (2, 'Chuột', 20, 120000),
    (3, 'Tai nghe', 15, 800000);

INSERT INTO lesson_mvcc.order_lines(
    order_line_id, product_id, quantity
)
VALUES (100, 1, 2), (101, 2, 1);
```

Các ví dụ tiếp theo sử dụng hai cửa sổ `psql`:

- **Session A**: kết nối thứ nhất.
- **Session B**: kết nối thứ hai, tới **cùng database** và có quyền thao tác trên bảng lab.

Nếu chạy tất cả lệnh nối tiếp trong **một connection**, bạn sẽ không tái hiện được những hiện tượng giữa các transaction độc lập. Khi có transaction đang mở ở một phiên, **đừng tự ý commit/rollback sớm** trước bước chỉ dẫn.

### Kiểm tra hai connection khác nhau

Chạy trên cả A và B:

```sql
SELECT
    current_database(),
    current_user,
    pg_backend_pid();
```

Hai phiên trực tiếp thường có `pg_backend_pid()` khác nhau. Trong môi trường có proxy pooling, cách ánh xạ client/backend có thể phức tạp hơn; để học MVCC, nên dùng hai kết nối PostgreSQL độc lập và giữ đúng transaction.

## 4. Transaction ID (XID) là gì?

PostgreSQL sử dụng **transaction ID**, thường viết là **XID**, trong việc quản lý các thay đổi và xác định trạng thái commit/abort.

Một hình dung:

```text
T10: INSERT hàng mới
T20: UPDATE hàng cũ → phiên bản mới
T30: DELETE hàng
```

Tuples được gắn metadata liên quan tới những transaction tạo, xóa hoặc khóa chúng. Khi truy vấn cần quyết định một tuple có được nhìn thấy hay không, PostgreSQL xét metadata ấy cùng **trạng thái transaction** và **snapshot hiện hành**.

### Không phải mọi BEGIN đều lập tức có XID ghi

Một transaction chỉ đọc có thể lấy snapshot mà **chưa cần được cấp XID theo cùng cách transaction ghi**. Vì vậy, không nên lấy việc một session đã `BEGIN` rồi suy ra nó luôn có một số XID ghi mới tương ứng.

### XID và thứ tự commit khác nhau

Thứ tự cấp transaction ID **không đồng nhất với thứ tự commit**:

```text
T100 bắt đầu ──────────────────────────── COMMIT muộn
           T101 bắt đầu ───── COMMIT sớm
```

T101 có ID được cấp sau nhưng hoàn tất trước T100. Vì thế, quy tắc MVCC không thể chỉ là “tuple có `xmin` nhỏ hơn một số nào đó thì nhìn thấy”. Cần xét **transaction còn đang chạy, đã commit hay đã abort** tại snapshot.

### XID wraparound và đóng băng

Tuple metadata truyền thống chứa các XID với không gian số hữu hạn và PostgreSQL có cơ chế **freeze**/quản lý tuổi transaction để xử lý wraparound an toàn. Không tự so sánh hai XID ở rất xa nhau bằng phép số học thông thường rồi coi đó là thứ tự lịch sử tuyệt đối.

## 5. System columns xmin, xmax và ctid

PostgreSQL cho phép đọc một số system columns của bảng heap:

```sql
SELECT
    product_id,
    product_name,
    quantity,
    xmin,
    xmax,
    ctid
FROM lesson_mvcc.products
ORDER BY product_id;
```

Bạn có thể thấy:

```text
product_id | quantity | xmin | xmax | ctid
-----------+----------+------+------+---------
1          | 10       | ...  | ...  | (...)
2          | 20       | ...  | ...  | (...)
3          | 15       | ...  | ...  | (...)
```

Giá trị cụ thể phụ thuộc lần chạy, database, transaction và layout vật lý. **Không copy một con số minh họa để so với server khác**.

### Ý nghĩa của xmin

`xmin` là metadata cho biết transaction tạo **tuple version**. Với một `UPDATE`, phiên bản mới thường có metadata tạo bởi transaction của UPDATE, còn phiên bản trước được đánh dấu là đã thay thế theo cơ chế tuple header.

### Ý nghĩa của xmax

`xmax` cần được diễn giải cẩn thận:

- Có thể liên quan đến transaction đã xóa hoặc thay thế một tuple.
- Có thể dùng trong các tình huống **khóa hàng**, không nhất thiết tuple đã bị xóa.
- Có thể liên quan **MultiXact** khi nhiều transaction tham gia khóa.
- Một giá trị nonzero không đủ để kết luận tuple không nhìn thấy.

**Sai lầm phổ biến:** `xmax <> 0` không phải điều kiện SQL tổng quát để xác định “hàng đã delete”. Việc nhìn thấy tuple phụ thuộc nhiều cờ metadata, trạng thái transaction và snapshot; PostgreSQL xử lý chúng bên trong executor/heap access.

### Ý nghĩa của ctid

`ctid` biểu diễn địa chỉ vật lý của phiên bản tuple, chẳng hạn block/offset. Nó có thể thay đổi sau `UPDATE` hoặc thao tác tổ chức lại bảng. **Không dùng `ctid` làm ID nghiệp vụ, foreign key, token phân trang ổn định hoặc mốc audit lâu dài**.

## 6. Một snapshot lưu thông tin gì?

Snapshot MVCC về mặt khái niệm mô tả ranh giới transaction ID và **những transaction đang chạy** tại thời điểm snapshot được lấy.

Một dạng biểu diễn hiện đại có các thành phần:

- **`xmin` của snapshot:** ranh giới dưới phục vụ đánh giá transaction còn cần xét trong tập đang hoạt động.
- **`xmax` của snapshot:** ranh giới trên; các XID bằng hoặc sau ranh giới này chưa được xem là đã hoàn tất trước snapshot.
- **Danh sách XID đang chạy:** các transaction đã được cấp ID nhưng chưa hoàn tất tại snapshot, gọi khái quát là **in-progress XIDs**.

Ví dụ **sơ đồ giả định**, không phải output PostgreSQL thực:

```text
Snapshot S
  xmin = 100
  xmax = 106
  in_progress = {101, 104}

T100: committed
T101: still running        ── không thấy thay đổi chưa commit của T101
T102: committed
T103: committed
T104: still running        ── không thấy thay đổi chưa commit của T104
T105: committed
T106: beyond snapshot      ── không thấy thay đổi tạo mới từ T106
```

Trong ví dụ:

- Các thay đổi do transaction **đã commit trước snapshot** có thể nhìn thấy, nếu không bị xóa/thay thế bởi một thay đổi visible khác.
- Các thay đổi từ transaction **đang chạy khi chụp** chưa được nhìn thấy từ snapshot ấy, kể cả khi transaction đó commit sau đó.
- Các thay đổi do transaction **bắt đầu sau ranh giới snapshot** không được xem là tồn tại trong snapshot cũ.

Đây là mô tả đơn giản hóa để học. PostgreSQL còn xét subtransaction, trạng thái commit/abort, command ID, hint bits, MultiXact và những điều kiện riêng của tuple/loại snapshot.

### Snapshot không phải timestamp có thể so sánh đơn giản

Không thể dùng:

```sql
WHERE created_at <= snapshot_time
```

để mô phỏng chính xác MVCC. `created_at` là một cột do ứng dụng/schema quản lý; transaction có thể bắt đầu trước nhưng commit sau, đồng hồ có thể lệch, và các transaction đang chạy làm cho tập visible **không thể chỉ suy ra từ timestamp của hàng**.

## 7. Quy tắc nhìn thấy phiên bản tuple

Với một **snapshot MVCC thông thường**, hình dung quá trình đánh giá như sau:

1. Tìm transaction liên quan tới **việc tạo phiên bản** (`xmin`).
2. Nếu transaction tạo phiên bản đã **abort**, phiên bản đó không được nhìn thấy.
3. Nếu transaction tạo phiên bản **chưa commit ở snapshot**, phiên bản mới chưa được nhìn thấy từ snapshot ấy.
4. Nếu transaction tạo phiên bản đã **commit đủ sớm** và hợp lệ theo snapshot, xét tiếp việc phiên bản có bị thay thế/xóa không.
5. Nếu transaction xóa/thay thế phiên bản **chưa commit hoặc chưa visible theo snapshot**, phiên bản cũ có thể vẫn visible đối với reader ấy.
6. Nếu việc xóa/thay thế đã **commit và visible theo snapshot**, phiên bản cũ thường không còn được đưa vào kết quả của snapshot đó.
7. Các thay đổi **do chính transaction thực hiện** được xử lý bằng quy tắc tự nhìn thấy và command ID, không thể máy móc áp dụng điều kiện “XID của tôi đang chạy nên mọi thay đổi của tôi vô hình”.

Đây là mô hình sư phạm, **không phải đoạn thuật toán đầy đủ có thể tự triển khai để thay thế kiểm tra visibility của PostgreSQL**.

### Bảng tình huống

| Transaction tạo tuple | Transaction xóa/thay thế | Kết quả khái quát |
|---|---|---|
| Committed trước snapshot | Chưa có | Tuple có thể visible. |
| Chưa commit tại snapshot | Chưa có | Tuple **không visible** đối với transaction khác. |
| Aborted | Chưa có | Tuple **không visible**. |
| Committed trước snapshot | Xóa đã commit trước snapshot | Tuple cũ **không visible**; với UPDATE có thể thấy phiên bản kế tiếp nếu hợp lệ. |
| Committed trước snapshot | Xóa đang chạy tại snapshot | Tuple cũ **vẫn có thể visible**. |
| Committed trước snapshot | Xóa commit sau snapshot | Snapshot cũ **vẫn có thể thấy** tuple cũ. |

Vì bảng không bao quát khóa hàng, subtransactions hoặc tối ưu triển khai, đừng lấy nó làm phép kiểm tra dữ liệu bằng tay qua `xmin`/`xmax`.

## 8. Một UPDATE tạo phiên bản mới như thế nào?

Giả sử sản phẩm 1 có số lượng 10:

```text
Version V1:
  product_id = 1
  quantity   = 10
  xmin       = T10
```

Transaction T20:

```sql
UPDATE lesson_mvcc.products
SET quantity = 8
WHERE product_id = 1;
```

Mô hình:

```text
Version V1: quantity = 10
  xmin = T10
  xmax ≈ T20 (đã được thay thế theo metadata tương ứng)
            │
            ▼
Version V2: quantity = 8
  xmin = T20
  xmax = chưa bị thay thế/xóa
```

**Nếu T20 chưa commit:** transaction khác có snapshot thông thường không được thấy V2; nó có thể vẫn thấy V1.

**Nếu T20 commit và reader lấy snapshot sau đó:** reader có thể thấy V2.

**Nếu reader giữ snapshot từ trước T20 commit:** nó có thể tiếp tục thấy V1 theo isolation level.

### UPDATE không nhất thiết ghi đè một tuple duy nhất

Vì cả V1 và V2 có thể cần tồn tại cùng lúc để phục vụ các snapshot khác nhau, MVCC có tác dụng tới dung lượng lưu trữ và công việc dọn dẹp của VACUUM. Đó là lý do khối lượng `UPDATE`/`DELETE` lớn có thể sinh **dead tuples**.

## 9. DELETE và snapshot: vì sao hàng đã xóa vẫn có thể xuất hiện?

Transaction B chạy:

```sql
DELETE FROM lesson_mvcc.products
WHERE product_id = 3;
```

Giả sử chưa có foreign key nào tham chiếu product 3 và thao tác hợp lệ. Sau khi B commit:

- Một query mới ở `READ COMMITTED` có snapshot mới sẽ không thấy hàng đó.
- Một transaction `REPEATABLE READ` với snapshot lấy **trước B commit** có thể vẫn thấy phiên bản cũ của hàng.

Điều đó không phải lỗi “PostgreSQL quên DELETE”. Snapshot cũ vẫn đại diện cho một trạng thái hợp lệ của database trước khi DELETE được commit.

**Lưu ý:** Nếu bạn xóa vĩnh viễn hàng mẫu khi thực hành, các bước sau có thể bị ảnh hưởng. Nên thử:

```sql
BEGIN;
DELETE FROM lesson_mvcc.products WHERE product_id = 3;
ROLLBACK;
```

hoặc dùng các bản sao/dataset thử nghiệm độc lập khi cần quan sát commit đồng thời.

## 10. Không có dirty read trong PostgreSQL

**Dirty read** là đọc dữ liệu của transaction khác **trước khi transaction ấy commit**. PostgreSQL không cho phép dirty read ở các isolation level được hỗ trợ.

### Thực hành hai phiên

**Session A:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 777
WHERE product_id = 1;

-- Chưa COMMIT và chưa ROLLBACK.
```

**Session B**, trong khi A vẫn mở:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
```

B vẫn thấy **giá trị đã commit trước đó** (ví dụ 10), không thấy 777 chưa commit của A.

**Quay lại Session A:**

```sql
ROLLBACK;
```

**Session B:**

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
```

Hàng vẫn mang giá trị cũ vì thay đổi 777 đã rollback.

### READ UNCOMMITTED trong PostgreSQL

PostgreSQL chấp nhận tên mức cô lập `READ UNCOMMITTED` trong cú pháp SQL nhưng **thực thi với ngữ nghĩa của READ COMMITTED** đối với việc nhìn thấy dữ liệu. Do vậy, thử:

```sql
BEGIN ISOLATION LEVEL READ UNCOMMITTED;
SELECT quantity FROM lesson_mvcc.products WHERE product_id = 1;
COMMIT;
```

không cho phép đọc giá trị chưa commit của session khác.

## 11. READ COMMITTED: snapshot mới cho mỗi câu lệnh

**`READ COMMITTED`** là isolation level mặc định thông thường của PostgreSQL, trừ khi server, database, role hoặc session đã cấu hình khác.

Đối với `SELECT` thông thường, **mỗi statement** lấy một snapshot tại thời điểm bắt đầu câu lệnh đó:

```text
Session A                              Session B
----------------------------------     ------------------------
BEGIN READ COMMITTED
SELECT quantity => 10
                                       UPDATE quantity = 8
                                       COMMIT
SELECT quantity => 8
COMMIT
```

Transaction A **vẫn là một transaction**, nhưng hai statement khác nhau có thể nhìn thấy hai trạng thái dữ liệu khác nhau.

### Thực hành từng bước

Đảm bảo product 2 đang tồn tại, đọc giá trị hiện tại. Ví dụ giả sử `quantity = 20`.

**Session A:**

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Ví dụ thấy 20.
```

**Session B**, một kết nối khác:

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 18
WHERE product_id = 2;

COMMIT;
```

**Session A**, vẫn cùng transaction:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Thấy 18 nếu B đã commit trước statement này.

COMMIT;
```

Ở một transaction `READ COMMITTED`, hai lần đọc có thể khác nhau dù A chưa kết thúc giao dịch.

### Non-repeatable read

Hiện tượng “đọc lại cùng hàng nhưng giá trị thay đổi vì transaction khác đã commit” được gọi là **non-repeatable read**. `READ COMMITTED` cho phép trường hợp này.

**Không có nghĩa một câu SELECT đang chạy sẽ tự động đổi snapshot giữa chừng.** Một statement thông thường đọc theo snapshot của statement ấy; câu SELECT *tiếp theo* mới lấy snapshot mới.

## 12. READ COMMITTED và phantom read

**Phantom read** liên quan tới việc lặp lại một truy vấn điều kiện rồi có thêm/bớt hàng phù hợp.

Ví dụ Session A:

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*)
FROM lesson_mvcc.products
WHERE quantity >= 10;
```

Session B chèn sản phẩm mới có số lượng 30 rồi commit:

```sql
BEGIN;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (99, 'Sản phẩm mới', 30, 50000);

COMMIT;
```

Session A chạy lại:

```sql
SELECT COUNT(*)
FROM lesson_mvcc.products
WHERE quantity >= 10;

COMMIT;
```

Số hàng có thể tăng vì snapshot mới thấy sản phẩm 99. Đây là một dạng **phantom**.

Muốn bảo toàn dữ liệu lab, sau bài học dùng transaction mới để xóa product 99 nếu không còn phụ thuộc, hoặc dùng một ID khác cho lần thử mới. Không dùng `ROLLBACK` ở session B sau khi đã `COMMIT` rồi mong xóa được hàng vừa commit.

## 13. REPEATABLE READ: snapshot ổn định trong transaction

Ở `REPEATABLE READ` trong PostgreSQL, các truy vấn thông thường trong cùng transaction sử dụng **cùng một transaction snapshot** đã được thiết lập khi transaction thực sự bắt đầu thực hiện statement cần snapshot.

### Thí nghiệm

Đầu tiên, giả sử product 2 đang có quantity 18 sau ví dụ trước.

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Ví dụ thấy 18 và thiết lập snapshot.
```

**Session B:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 16
WHERE product_id = 2;

COMMIT;
```

**Session A:**

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Vẫn thấy 18 theo snapshot cũ.

COMMIT;
```

**Sau khi A kết thúc**, một transaction mới có thể thấy 16:

```sql
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
```

### Snapshot được lấy khi nào?

Một điểm tinh tế: Trong PostgreSQL, `BEGIN ISOLATION LEVEL REPEATABLE READ` không nhất thiết “đóng băng mọi dữ liệu ngay tại thời điểm client gửi BEGIN”. Snapshot thường được thiết lập ở **statement không phải lệnh điều khiển transaction đầu tiên** cần snapshot, ví dụ câu `SELECT` đầu tiên. Nếu B commit sau `BEGIN` nhưng **trước lần đọc đầu của A**, A có thể nhìn thấy commit của B.

Vì thế, khi viết kịch bản hai session để quan sát snapshot cũ, hãy cho A **thực hiện câu SELECT đầu tiên trước khi B commit**.

## 14. REPEATABLE READ vẫn thấy thay đổi do chính transaction thực hiện

Một hiểu lầm là “snapshot cố định nghĩa là transaction không bao giờ thấy bất cứ giá trị mới nào”. Thực tế, PostgreSQL cho phép transaction nhìn thấy **các thay đổi do chính nó thực hiện** theo quy tắc command IDs, ngay cả trong `REPEATABLE READ`.

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
-- Ví dụ 10.

UPDATE lesson_mvcc.products
SET quantity = quantity - 1
WHERE product_id = 1;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1;
-- Thấy 9: thay đổi của chính transaction.

ROLLBACK;
```

`ROLLBACK` cuối ví dụ hoàn nguyên thay đổi để giữ dữ liệu lab.

### Vì sao không mâu thuẫn với snapshot?

Snapshot loại bỏ những thay đổi **chưa commit của transaction khác** và duy trì ranh giới nhìn thấy theo isolation. Nó không cấm transaction quan sát **ghi của chính mình** sau khi những câu lệnh ghi được hoàn tất.

Trong triển khai, PostgreSQL dùng thêm **command ID** và metadata của tuple để xác định tính nhìn thấy của thao tác trong cùng transaction. Không thể chỉ xét một danh sách transaction IDs mà mô tả đầy đủ self-visibility.

## 15. So sánh READ COMMITTED và REPEATABLE READ

| Tình huống | READ COMMITTED | REPEATABLE READ của PostgreSQL |
|---|---|---|
| Thấy dữ liệu chưa commit của transaction khác? | **Không**. | **Không**. |
| Statement thứ hai thấy commit mới của transaction khác? | **Có thể**. | **Không**, nếu snapshot đã được thiết lập trước commit đó, đối với truy vấn thường. |
| Đọc lại một hàng có thể thấy giá trị khác vì writer khác? | **Có**. | **Không**, với snapshot thông thường và các giả định phù hợp. |
| Truy vấn lại điều kiện có thể thấy phantom do insert mới? | **Có**. | Không theo snapshot cố định của PostgreSQL. |
| Thấy ghi của chính transaction? | **Có**. | **Có**. |
| Writer gặp hàng đã bị thay đổi đồng thời? | Có thể chờ rồi kiểm tra lại hàng. | Có thể bị `40001` nếu hàng mục tiêu đã đổi từ khi snapshot bắt đầu. |
| Bảo đảm serializable tuyệt đối? | Không. | Không; một số bất thường như write skew vẫn có thể xảy ra. |

PostgreSQL `REPEATABLE READ` dựa trên snapshot isolation mạnh hơn một số mô tả tối thiểu của chuẩn SQL về phantom. Nhưng **snapshot ổn định không tự đồng nghĩa tất cả transaction concurrent tương đương lịch tuần tự**.

## 16. SERIALIZABLE: snapshot cộng kiểm soát bất thường đồng thời

`SERIALIZABLE` là mức cô lập mạnh nhất của PostgreSQL. Với những transaction hoàn tất thành công, hệ thống nhằm bảo đảm kết quả tương đương một thứ tự thực thi **tuần tự nào đó**.

PostgreSQL triển khai serializable bằng cơ chế **Serializable Snapshot Isolation (SSI)**, không đơn giản khóa toàn bộ database cho mỗi transaction.

### Vì sao snapshot cố định vẫn chưa đủ?

Giả sử quy tắc là “phải có ít nhất một bác sĩ đang trực”.

```text
Ban đầu:
  Doctor A = on_call
  Doctor B = on_call

Transaction T1 nhìn snapshot: A và B đều trực
  → T1 cho A nghỉ

Transaction T2 nhìn cùng trạng thái ban đầu:
  → T2 cho B nghỉ

Hai transaction ghi hai hàng khác nhau.
Nếu cả hai cùng commit trong snapshot isolation:
  không còn ai trực → vi phạm quy tắc liên hàng.
```

Đó là ví dụ **write skew**. Cả T1 và T2 có thể không cập nhật cùng một row, nên chỉ phát hiện write-write conflict chưa đủ.

Ở `SERIALIZABLE`, SSI theo dõi những dependency nguy hiểm giữa việc đọc và ghi. Trong những lịch có nguy cơ không serializable, PostgreSQL có thể **hủy một transaction bằng SQLSTATE `40001`**, buộc ứng dụng **retry toàn bộ transaction**.

### SERIALIZABLE không có nghĩa không bao giờ phải retry

```sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Đọc dữ liệu và ra quyết định nghiệp vụ.
-- Có thể xảy ra xung đột SSI với transaction khác.

COMMIT;
```

Lỗi `40001` có thể xuất hiện trong quá trình thực thi hoặc tại `COMMIT`, tùy tình huống. Ứng dụng phải sẵn sàng thực hiện lại cả thao tác đọc và quyết định, không chỉ lặp câu UPDATE cuối.

## 17. Các mức cô lập và hiện tượng nhìn thấy dữ liệu

| Hiện tượng | READ UNCOMMITTED (PostgreSQL) | READ COMMITTED | REPEATABLE READ | SERIALIZABLE |
|---|---|---|---|---|
| Dirty read | Không | Không | Không | Không |
| Non-repeatable read do commit khác | Có thể | Có thể | Không theo snapshot | Không với transaction thành công |
| Phantom do commit khác | Có thể | Có thể | Không theo snapshot | Không với transaction thành công |
| Write skew | Có thể | Có thể | Có thể | Được ngăn cho các transaction commit thành công, có thể cần retry `40001` |

`READ UNCOMMITTED` được PostgreSQL thực hiện theo hành vi `READ COMMITTED`. Bảng này mô tả các hành vi khái quát của các truy vấn thông thường; những câu khóa hàng, cập nhật đồng thời và constraint có quy tắc riêng cần tìm hiểu ở phần sau.

## 18. Snapshot có khiến UPDATE không bao giờ nhìn thấy ghi mới?

Không thể áp dụng nguyên xi quy tắc của **`SELECT` thông thường** cho mọi **`UPDATE`/`DELETE`/`SELECT FOR UPDATE`**.

Trong `READ COMMITTED`, nếu một statement muốn sửa một hàng đang bị transaction khác cập nhật/khóa, PostgreSQL có thể:

1. Tìm hàng là ứng viên theo snapshot đầu statement.
2. Chờ transaction khác hoàn tất nếu có lock/conflict.
3. Sau khi transaction kia commit, xem phiên bản hàng mới và **kiểm tra lại điều kiện `WHERE`** theo những quy tắc xử lý cập nhật đồng thời.
4. Nếu hàng vẫn thỏa điều kiện, áp dụng thay đổi lên phiên bản phù hợp; nếu không, bỏ qua hàng.

Cơ chế này thường được giải thích qua việc **recheck/re-evaluate updated tuple**; trong PostgreSQL có cơ chế liên quan tới *EvalPlanQual* (EPQ).

### Ví dụ suy nghĩ

Ban đầu product 1 có quantity 10.

**Session A:**

```sql
BEGIN;

UPDATE lesson_mvcc.products
SET quantity = 3
WHERE product_id = 1;

-- Giữ transaction mở, chưa COMMIT.
```

**Session B**, đang ở `READ COMMITTED`:

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 1
  AND quantity >= 5;
-- Có thể chờ A hoàn tất.
```

**Session A:**

```sql
COMMIT;
```

Sau khi A commit, B có thể kiểm tra lại phiên bản quantity 3. Điều kiện `quantity >= 5` **không còn đúng**, nên B không cập nhật hàng đó.

### Đừng suy ra mọi SELECT trong statement thấy nhất quán tuyệt đối theo một điểm tuần tự

`READ COMMITTED` có những chi tiết khi statement sửa hàng đồng thời: nó có thể thao tác trên phiên bản mới của row mục tiêu dù các phần khác của query vẫn được đánh giá theo snapshot ban đầu. Đó là lý do PostgreSQL docs cảnh báo mức này có thể không đủ cho các thao tác có điều kiện logic phức tạp.

Nếu cần ràng buộc nhất quán mạnh hơn, cân nhắc explicit locking, `REPEATABLE READ`/`SERIALIZABLE`, unique constraints hoặc thiết kế lại giao thức ghi.

## 19. REPEATABLE READ và concurrent UPDATE

Với `REPEATABLE READ`, nếu transaction đã có snapshot và transaction khác sửa một hàng mục tiêu rồi commit, một nỗ lực `UPDATE`/`DELETE`/`SELECT FOR UPDATE` lên phiên bản đã thay đổi có thể kết thúc bằng:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

### Kịch bản minh họa

**Session A:**

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 2;
-- Thiết lập snapshot cũ.
```

**Session B:**

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 2
WHERE product_id = 2;
-- Khi autocommit bật, statement hoàn tất và commit.
```

**Session A:**

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 2;
-- Có thể lỗi 40001 do hàng đã được B thay đổi từ snapshot của A.

ROLLBACK;
```

**`40001` không phải lời mời tiếp tục UPDATE trong transaction ấy.** Transaction đã thất bại; ứng dụng cần rollback rồi, nếu hợp lệ, bắt đầu transaction mới và thử lại toàn bộ logic.

## 20. SELECT FOR UPDATE không giống SELECT thông thường

`SELECT ... FOR UPDATE` là câu đọc có **mục đích khóa hàng**, thường dùng trước khi sửa:

```sql
BEGIN;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 1
FOR UPDATE;

-- Quyết định nghiệp vụ và UPDATE trong cùng transaction.

ROLLBACK;
```

Khác với `SELECT` thuần, câu này yêu cầu khóa row để phối hợp với các writer. Nếu transaction khác giữ lock không tương thích, nó có thể phải chờ hoặc lỗi khi dùng `NOWAIT`.

### NOWAIT

```sql
BEGIN;

SELECT product_id
FROM lesson_mvcc.products
WHERE product_id = 1
FOR UPDATE NOWAIT;

ROLLBACK;
```

Nếu không lấy được lock ngay vì conflict, PostgreSQL có thể trả `55P03`, và transaction tường minh phải xử lý lỗi bằng rollback/savepoint phù hợp.

### SKIP LOCKED

```sql
SELECT product_id
FROM lesson_mvcc.products
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` có thể bỏ qua những hàng đang bị khóa để hỗ trợ kiểu worker queue. Kết quả **không đại diện cho một cái nhìn nhất quán đầy đủ về tất cả hàng cần xử lý**, nên không nên dùng tùy tiện cho báo cáo tổng quát.

**Quan trọng:** Việc `SELECT FOR UPDATE` cần khóa row không bác bỏ MVCC; locking và snapshot visibility là hai cơ chế phối hợp với nhau.

## 21. Unique constraint kiểm tra cả những hàng không visible trong SELECT

Một câu hỏi thường gặp:

> “Tôi không SELECT thấy SKU nào trùng, sao INSERT lại bị unique violation?”

Vì **tính duy nhất phải được bảo vệ trên toàn database**, không chỉ trên những hàng nhìn thấy trong snapshot của một SELECT. Nếu hai transaction cùng chèn một `sku`, PostgreSQL cần điều phối unique index và trạng thái transaction cạnh tranh.

### Ví dụ hai session

Giả sử SKU `SKU-X` chưa tồn tại.

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (101, 'SKU-X', 1, 10000);

-- product_name ở schema lab không UNIQUE; ví dụ này
-- chưa mô phỏng conflict theo SKU.
ROLLBACK;
```

Để thử đúng unique conflict, dùng bảng nhỏ riêng:

```sql
CREATE TABLE lesson_mvcc.unique_demo (
    id BIGINT PRIMARY KEY,
    external_key TEXT NOT NULL UNIQUE
);
```

**Session A:**

```sql
BEGIN;

INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (1, 'same-key');

-- Chưa commit.
```

**Session B**, trong một connection khác:

```sql
SELECT *
FROM lesson_mvcc.unique_demo
WHERE external_key = 'same-key';
-- Chưa thấy hàng của A vì A chưa commit.

INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (2, 'same-key');
-- Có thể phải CHỜ transaction A để quyết định unique conflict.
```

**Session A** commit:

```sql
COMMIT;
```

Khi A commit, lệnh chèn của B có thể kết thúc bằng `23505 unique_violation`. Nếu A rollback thay vì commit, B có thể được phép chèn.

**Điều cần nhớ:** `SELECT không thấy` không phải bằng chứng “key chắc chắn chưa được transaction khác giữ/chèn”. Unique constraint có cơ chế đồng bộ riêng nhằm bảo vệ bất biến dữ liệu dưới concurrency.

## 22. INSERT ... ON CONFLICT dưới READ COMMITTED

`INSERT ... ON CONFLICT` là công cụ để xử lý conflict an toàn hơn so với cặp:

```text
SELECT xem key chưa tồn tại
  ↓
INSERT key
```

vì hai bước trên có thể bị transaction khác chen vào.

Ví dụ:

```sql
INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (3, 'same-key')
ON CONFLICT (external_key) DO NOTHING
RETURNING id;
```

Trong `READ COMMITTED`, `ON CONFLICT DO NOTHING` có thể **không chèn một hàng vì conflict từ transaction khác**, ngay cả khi phiên bản hàng gây conflict không visible trong snapshot thông thường của statement ấy.

Với `ON CONFLICT DO UPDATE`, PostgreSQL cũng có quy tắc đảm bảo hành động INSERT hoặc UPDATE được chọn đối với mỗi hàng đầu vào khi không có lỗi độc lập, kể cả khi hàng bị UPDATE chưa visible theo snapshot SELECT thông thường của statement:

```sql
INSERT INTO lesson_mvcc.unique_demo(id, external_key)
VALUES (3, 'same-key')
ON CONFLICT (external_key)
DO UPDATE SET external_key = EXCLUDED.external_key
RETURNING id, external_key;
```

Đây là trường hợp quan trọng: **visibility dùng cho đọc và việc cưỡng chế ràng buộc/giải quyết conflict có thể liên quan nhau nhưng không đồng nhất**.

Không dùng `ON CONFLICT` để che mọi loại lỗi. Cần định nghĩa đúng unique key và ngữ nghĩa upsert.

## 23. UPDATE dưới READ COMMITTED và lost update ở tầng ứng dụng

Giả sử hàng có quantity 10. Hai request làm:

```text
Request A: SELECT quantity => 10
Request B: SELECT quantity => 10
Request A: UPDATE SET quantity = 11
Request B: UPDATE SET quantity = 11
```

Kết quả có thể là 11, dù hai request đều muốn tăng một đơn vị. Đây là kiểu **lost update** do ứng dụng đọc giá trị rồi gửi lại một **giá trị tuyệt đối đã tính từ dữ liệu cũ**.

### Cách tốt hơn cho phép tăng đơn giản

```sql
UPDATE lesson_mvcc.products
SET quantity = quantity + 1
WHERE product_id = 1;
```

Hai transaction cập nhật cùng hàng sẽ được PostgreSQL đồng bộ qua row locking. Khi dùng biểu thức `quantity = quantity + 1`, thao tác tăng có thể được áp dụng lên phiên bản phù hợp thay vì ghi đè cùng một literal 11.

### Optimistic locking với version column

Nếu nghiệp vụ cần kiểm tra “dữ liệu không đổi kể từ khi tôi đọc”:

```sql
-- Minh họa trên bảng đã có cột version_no:
UPDATE some_business_table
SET
    payload = 'new-value',
    version_no = version_no + 1
WHERE id = 42
  AND version_no = 7
RETURNING version_no;
```

Đây là câu SQL mẫu, bảng `some_business_table` chưa được tạo trong lab. Nếu `UPDATE` trả 0 hàng, có thể record đã bị thay đổi hoặc không tồn tại; ứng dụng cần xử lý conflict phù hợp.

Không coi `xmin` của tuple là một version number nghiệp vụ ổn định lâu dài: transaction ID có wraparound/freeze và không được thiết kế làm hợp đồng API.

## 24. Snapshot và dữ liệu nhìn thấy trong cùng một transaction

Ngay cả với transaction snapshot ổn định, câu lệnh sau thường thấy những thay đổi mà transaction đã làm ở câu lệnh trước:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

INSERT INTO lesson_mvcc.products(
    product_id, product_name, quantity, price
)
VALUES (500, 'Sản phẩm trong transaction', 5, 25000);

SELECT *
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Thấy hàng do chính transaction chèn.

UPDATE lesson_mvcc.products
SET quantity = 7
WHERE product_id = 500;

SELECT quantity
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Thấy 7.

DELETE FROM lesson_mvcc.products
WHERE product_id = 500;

SELECT *
FROM lesson_mvcc.products
WHERE product_id = 500;
-- Không còn hàng, theo thay đổi của chính transaction.

ROLLBACK;
```

Các kết quả này phản ánh self-visibility và thứ tự câu lệnh trong transaction. Ghi nhớ **đọc snapshot cũ đối với giao dịch khác** không đồng nghĩa **mù với ghi của chính mình**.

## 25. Command ID và giới hạn của phép so sánh chỉ theo XID

Ở mức nội bộ, tuple version có thêm thông tin liên quan **command ID** của các thao tác trong cùng transaction.

Ví dụ:

```text
T100:
  Command 0: INSERT product 500
  Command 1: SELECT product 500
  Command 2: UPDATE product 500
  Command 3: SELECT product 500
```

Một cách so sánh “tuple tạo bởi transaction T100, T100 đang running nên invisible” là sai với những thay đổi **do T100 tự tạo**. PostgreSQL phải xét **thứ tự command trong cùng transaction** để tránh:

- Không nhìn thấy INSERT của chính mình ở statement sau.
- Nhìn thấy phiên bản đã được chính transaction thay thế một cách sai.
- Coi những thao tác trong cùng transaction là những transaction độc lập.

Một số tình huống trong **cùng statement** có thêm quy tắc đặc biệt: những phần của một câu SQL không phải được phép tự do nhìn thấy mọi hiệu ứng thay đổi do phần khác của cùng statement tạo ra theo thứ tự bất kỳ. Ví dụ data-modifying CTE có những quy tắc về snapshot và trao đổi dữ liệu bằng `RETURNING`. Đây là nội dung nâng cao, không nên suy ra từ mô hình command ID đơn giản.

## 26. Một transaction dài ảnh hưởng gì tới VACUUM?

Nếu một transaction giữ snapshot cũ, PostgreSQL có thể phải duy trì những tuple version cũ mà snapshot ấy vẫn có quyền nhìn thấy.

```text
T1: BEGIN REPEATABLE READ
    SELECT ...  → snapshot S1
    [giữ transaction mở rất lâu]

T2: UPDATE 10.000 hàng, COMMIT
    → tạo những version mới

VACUUM:
    Có thể chưa dọn được mọi version cũ
    nếu S1 vẫn cần những version ấy.

T1: COMMIT/ROLLBACK
    → snapshot cũ được giải phóng
    → VACUUM về sau có thể thu hồi thêm phiên bản đủ điều kiện
```

Điều này liên quan tới **xmin horizon / visibility horizon** và việc xác định phiên bản nào còn cần cho transaction, replica hoặc consumer khác.

### Những biểu hiện

- `n_dead_tup` tăng trong thống kê bảng.
- Dung lượng bảng/index lớn hơn dự kiến.
- Autovacuum chạy nhưng không thu hồi được hết tuple cũ.
- Transaction dài bị giữ bởi một request/JDBC connection lâu không kết thúc.
- Có backend `idle in transaction`.

**Không nên kết luận “cứ có transaction lâu là giữ tất cả phiên bản của toàn database”**. Snapshot, backend xmin, transaction XID, nhu cầu replication và quy tắc global horizon quyết định những tuple nào thực sự bị giữ lại.

### Reader không khóa writer nhưng vẫn tạo chi phí lưu trữ

Một truy vấn đọc lâu có thể không chặn `UPDATE` thông thường bằng row lock, nhưng snapshot được giữ lâu có thể **trì hoãn việc thu dọn phiên bản cũ**. Đây là một đánh đổi quan trọng của MVCC.

## 27. VACUUM không thay đổi quy tắc visibility của truy vấn

`VACUUM` có mục đích thu hồi những tuple không còn cần thiết, duy trì thông tin visibility và hỗ trợ chống transaction ID wraparound.

Không hiểu rằng:

- `VACUUM` sẽ làm một transaction snapshot cũ “đột nhiên thấy bản mới”.
- `VACUUM` có thể xóa mọi tuple cũ ngay dù snapshot đang cần nó.
- `VACUUM FULL` là bước mặc định cần chạy mỗi khi bảng có `UPDATE`.

PostgreSQL thiết kế `VACUUM` để tôn trọng các ranh giới an toàn về visibility. Một transaction đã có snapshot vẫn tuân theo quy tắc isolation trong phạm vi được hỗ trợ.

### VACUUM và VACUUM FULL

- `VACUUM` thông thường dọn dẹp dead tuples đủ điều kiện và tái sử dụng không gian theo cơ chế PostgreSQL, thường không trả toàn bộ dung lượng file về hệ điều hành.
- `VACUUM FULL` viết lại bảng để thu gọn và cần khóa mạnh hơn; không phải một giải pháp nên dùng bừa bãi trên hệ thống đang hoạt động.

Nếu snapshot dài khiến vacuum bị kẹt, chỉ chạy `VACUUM FULL` không tự giải quyết nguyên nhân lifecycle của transaction và còn có thể gây ảnh hưởng locking đáng kể.

## 28. pg_stat_activity: xem transaction và backend_xmin

Từ **một connection giám sát riêng**, dùng:

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    xact_start,
    query_start,
    backend_xmin,
    wait_event_type,
    wait_event
FROM pg_catalog.pg_stat_activity
WHERE datname = current_database()
ORDER BY xact_start NULLS LAST, pid;
```

Các cột quan trọng:

| Cột | Ý nghĩa |
|---|---|
| `pid` | Process ID của backend. |
| `state` | Trạng thái hoạt động, ví dụ `active`, `idle`, `idle in transaction`. |
| `xact_start` | Thời điểm bắt đầu transaction hiện tại, nếu có. |
| `query_start` | Mốc khởi đầu query được thống kê theo state. |
| `backend_xmin` | XID horizon liên quan snapshot hiện được backend ghi nhận khi có. |
| `wait_event_type`/`wait_event` | Thông tin chờ hiện tại nếu backend đang chờ. |

### Cách sử dụng

Nếu một phiên đọc `REPEATABLE READ` mở hàng giờ:

1. Xác định đúng `pid`/`application_name`.
2. Kiểm tra `xact_start` và trạng thái `idle in transaction`.
3. Kiểm tra `backend_xmin` khi có.
4. Đối chiếu với workload, autovacuum và bảng có nhiều dead tuples.
5. Ưu tiên sửa transaction lifecycle trong ứng dụng.

**Không coi `backend_xmin` là chính snapshot đầy đủ**, và đừng so sánh XID số đơn giản mà bỏ qua wraparound. `backend_xmin` là một chỉ dấu quản trị hữu ích, không phải toàn bộ tập transaction in-progress của snapshot.

### Quyền quan sát

Tùy role, một số cột phiên khác trong `pg_stat_activity` có thể bị hạn chế. Dùng quyền giám sát tối thiểu phù hợp; không cấp superuser chỉ để chẩn đoán snapshot.

## 29. Thống kê dead tuples trong bảng

PostgreSQL cung cấp view thống kê như `pg_stat_user_tables`:

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count
FROM pg_catalog.pg_stat_user_tables
WHERE schemaname = 'lesson_mvcc'
ORDER BY relname;
```

`n_live_tup` và `n_dead_tup` là **ước lượng thống kê**, không phải đếm chính xác từng tuple trong cùng snapshot như một truy vấn `COUNT(*)`.

Để kết luận bảng bị bloat do snapshot:

- Cần nhìn xu hướng qua nhiều thời điểm.
- Xem lượng UPDATE/DELETE, autovacuum và transaction/replication horizon.
- Kiểm tra có lock, long transaction, replication slot hoặc standby feedback ảnh hưởng không.
- Đo dung lượng, workload và tình trạng vacuum thực tế.

Không đoán nguyên nhân duy nhất chỉ từ một con số `n_dead_tup`.

## 30. Replication và snapshot giữ phiên bản cũ

Không chỉ transaction đọc ở primary mới có thể ảnh hưởng việc thu dọn tuple. Một số cơ chế replication, replication slot và **`hot_standby_feedback`** có thể khiến primary cần giữ thông tin/phiên bản lâu hơn để phục vụ consumers hoặc standby.

### Standby có snapshot riêng

Physical standby thực hiện WAL replay, và những truy vấn read-only trên standby có thể nhìn dữ liệu theo một trạng thái replay nhất định. Standby không nhất thiết bắt kịp primary tức thời.

Một ứng dụng:

```text
Ghi vào primary → COMMIT thành công
Đọc ngay ở standby → có thể chưa thấy thay đổi
```

Đây có thể là **replication lag**, không phải cùng hiện tượng với snapshot cũ trong `REPEATABLE READ` trên primary.

### Xung đột recovery với truy vấn dài

Trong một số cấu hình standby, WAL replay cần dọn thông tin gây xung đột với snapshot/truy vấn read-only ở standby. Truy vấn có thể bị hủy theo cơ chế **recovery conflict**, tùy cấu hình delay/feedback. Không tự giả định một snapshot ở standby có thể tồn tại mãi mà không ảnh hưởng replay.

### Đánh đổi khi bật feedback

`hot_standby_feedback` có thể giảm một số snapshot conflict trên standby, nhưng có thể khiến primary giữ dead tuples lâu hơn. Cấu hình cần cân đối độ trễ, bloat, SLA của truy vấn và tài nguyên.

**Đừng gộp replication lag, snapshot visibility và quyền truy cập thành một nguyên nhân duy nhất** khi một truy vấn “không thấy dữ liệu mới”.

## 31. Quan sát snapshot bằng pg_current_snapshot()

PostgreSQL hiện đại cung cấp hàm:

```sql
SELECT pg_current_snapshot() AS snapshot_info;
```

Giá trị trả về có kiểu **`pg_snapshot`**, thường được biểu diễn dạng ba thành phần:

```text
xmin:xmax:xip_list
```

Trong đó `xip_list` biểu diễn những transaction IDs đang thực hiện tại thời điểm snapshot theo format hàm. Đây không phải một con số “thời điểm chụp”; mỗi phần có ý nghĩa đối với visibility.

Ví dụ xem các thành phần:

```sql
WITH s AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    snap::text AS snapshot_text,
    pg_snapshot_xmin(snap) AS snapshot_xmin,
    pg_snapshot_xmax(snap) AS snapshot_xmax
FROM s;
```

Để liệt kê transaction ID đang ở trong snapshot:

```sql
SELECT xid
FROM pg_snapshot_xip(pg_current_snapshot()) AS x(xid)
ORDER BY xid;
```

Truy vấn cuối có thể trả **0 hàng** nếu snapshot không ghi nhận XID đang chạy trong tập đó. Kết quả và số XID phụ thuộc concurrency ở server.

### Những điểm cần nhớ

- `pg_current_snapshot()` trả snapshot theo ngữ cảnh statement/transaction và isolation đang dùng.
- `pg_snapshot_xmin`/`pg_snapshot_xmax` trả các ranh giới XID của snapshot.
- `pg_snapshot_xip` trả các XID thuộc tập in-progress của snapshot.
- **Không dùng snapshot string làm timestamp, ID đơn hàng hoặc hợp đồng “time travel” có thể lưu tùy ý rồi dùng lại mãi.**

Các hàm họ `pg_snapshot` là giao diện hiện đại; tài liệu/ứng dụng cũ có thể dùng các hàm họ `txid_*` và kiểu `txid_snapshot`. Khi bảo trì hệ cũ, cần kiểm tra phiên bản server và API thực tế thay vì trộn tùy tiện hai họ hàm.

## 32. pg_current_xact_id() và việc cấp XID

Khi cần quan sát ID của transaction hiện tại trong PostgreSQL hiện đại, có các hàm như:

```sql
SELECT pg_current_xact_id() AS my_xid;
```

Lời gọi này có thể **buộc cấp XID** nếu transaction chưa được cấp. Vì thế, không nên gọi nó vô tội vạ trong truy vấn đo đạc một transaction chỉ đọc rồi kết luận mọi read-only transaction đều có XID.

Có biến thể kiểm tra nếu đã được cấp:

```sql
SELECT pg_current_xact_id_if_assigned() AS maybe_xid;
```

Biến thể này có thể trả SQL `NULL` nếu chưa có XID gắn với transaction theo ngữ nghĩa hàm.

### XID của transaction không phải snapshot

`pg_current_xact_id()` cho biết định danh transaction đang gọi. `pg_current_snapshot()` cho biết bức tranh các XID visible/in-progress tại snapshot. Một transaction ID đơn lẻ không thể đại diện đầy đủ cho tập dữ liệu visible của query.

## 33. Kiểm tra một XID theo snapshot: chỉ dùng để học và debug

PostgreSQL hiện đại có `pg_visible_in_snapshot(xid8, pg_snapshot)` để xác định **tính nhìn thấy của một transaction ID trong snapshot** theo giao diện hàm.

Ví dụ về cú pháp:

```sql
WITH snapshot_data AS (
    SELECT pg_current_snapshot() AS snap
)
SELECT
    s.snap,
    pg_visible_in_snapshot(
        pg_current_xact_id_if_assigned(),
        s.snap
    ) AS current_xid_visible
FROM snapshot_data AS s
WHERE pg_current_xact_id_if_assigned() IS NOT NULL;
```

Đây là ví dụ thăm dò và **có thể không trả hàng** khi transaction chưa được cấp XID. Không diễn giải boolean trả về như “mọi tuple do transaction ấy tạo đều visible”: tuple visibility còn phụ thuộc xóa/thay thế, subtransactions, tự nhìn thấy và các cờ nội bộ.

**Quan trọng:** `pg_visible_in_snapshot` kiểm tra XID theo snapshot, không thay thế thuật toán kiểm tra một **tuple cụ thể** của PostgreSQL, và không phải cơ chế cấp quyền hay kiểm tra dữ liệu có tồn tại theo khóa nghiệp vụ.

## 34. Export/import snapshot giữa nhiều transaction

Đôi khi hai worker cần thực hiện nhiều truy vấn nhưng **nhìn dữ liệu từ cùng một mốc snapshot**. PostgreSQL hỗ trợ giao diện xuất và nhập snapshot trong những điều kiện nhất định.

### Session A: xuất snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT pg_export_snapshot();
-- Trả một snapshot identifier dạng text, ví dụ:
-- 00000003-0000001A-1

-- Giữ transaction này mở cho tới khi B nhập snapshot.
```

### Session B: nhập snapshot

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SET TRANSACTION SNAPSHOT '00000003-0000001A-1';
-- Thay chuỗi minh họa bằng identifier thực do A trả về.

SELECT COUNT(*)
FROM lesson_mvcc.products;

COMMIT;
```

### Session A: kết thúc sau khi B đã nhập

```sql
COMMIT;
```

Các điều kiện quan trọng:

1. **Transaction xuất snapshot phải còn mở** tại thời điểm transaction kia nhập snapshot.
2. Transaction nhập phải thiết lập isolation phù hợp (thường `REPEATABLE READ` hoặc `SERIALIZABLE` theo các ràng buộc PostgreSQL tương ứng).
3. `SET TRANSACTION SNAPSHOT` phải được thực hiện **trước các câu truy vấn lấy snapshot khác** trong transaction nhập.
4. Snapshot ID là **định danh tạm thời**, không phải backup hoặc token có thể lưu vào DB rồi dùng mọi lúc.
5. Có những hạn chế bổ sung theo isolation, database/session và tính chất transaction. Phải đọc tài liệu đúng phiên bản khi xây công cụ backup/report nhiều connection.

### Export snapshot không thay thế backup

Snapshot dùng để đồng bộ cái nhìn giữa các transaction liên quan. Nó không tự chứa dữ liệu, không lưu trữ các phiên bản hàng vĩnh viễn và không khôi phục database về mốc lịch sử bất kỳ.

## 35. Snapshot và backup nhất quán

Các công cụ dump có thể cần **consistent snapshot** để nhiều bảng được đọc từ cùng một trạng thái logic, tránh kết quả:

```text
Đọc bảng orders tại thời điểm T1
Đọc bảng order_items tại thời điểm T2
→ Có thể lệch nhau nếu transaction khác commit giữa hai mốc.
```

Khi transaction dump dùng snapshot nhất quán, dữ liệu được đọc phản ánh một trạng thái chung theo quy tắc MVCC. Những công cụ như `pg_dump` có thể tổ chức snapshot, và khi dump song song có cơ chế phối hợp snapshot trên các worker trong các điều kiện được hỗ trợ.

Không tự xây backup bằng cách copy những file data directory trong lúc server hoạt động và tin rằng snapshot của một câu SQL đủ bảo đảm tính nhất quán của file vật lý. Logical dump và physical backup là những quy trình riêng.

## 36. Isolation level trong JDBC

JDBC hỗ trợ khai báo isolation cho connection:

```java
int oldIsolation = connection.getTransactionIsolation();
boolean oldAutoCommit = connection.getAutoCommit();

try {
    connection.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement("""
            SELECT product_id, quantity
            FROM lesson_mvcc.products
            WHERE product_id = ?
            """)) {
        ps.setLong(1, 1L);

        try (ResultSet rs = ps.executeQuery()) {
            if (rs.next()) {
                int quantity = rs.getInt("quantity");
                // Dùng quantity trong logic nghiệp vụ.
            }
        }
    }

    connection.commit();
} catch (SQLException | RuntimeException e) {
    try {
        connection.rollback();
    } catch (SQLException rollbackFailure) {
        e.addSuppressed(rollbackFailure);
    }
    throw e;
} finally {
    // Chỉ đổi isolation/autoCommit khi transaction đã kết thúc.
    connection.setAutoCommit(oldAutoCommit);
    connection.setTransactionIsolation(oldIsolation);
}
```

Đây là ví dụ minh họa trong một phương thức có `throws SQLException`, các imports và `Connection connection` hợp lệ. Trong code production, cần thiết kế xử lý lỗi khi restore state cũng thất bại (ví dụ không che exception gốc), tuân thủ hợp đồng của pool và không đổi isolation khi đang có transaction hoạt động.

### Có dùng setTransactionIsolation giữa transaction được không?

Không nên cố đổi mức cô lập **sau khi giao dịch đã bắt đầu thực hiện câu truy vấn**. PostgreSQL yêu cầu xác định isolation tại thời điểm phù hợp trước khi transaction đã lấy snapshot/thực thi phần dữ liệu. Với JDBC, đặt isolation **trước khi bắt đầu transaction** hoặc để transaction manager cấu hình theo hợp đồng framework.

### Transaction isolation không phải chỉ một tham số cấu hình UI

Chọn `REPEATABLE READ`/`SERIALIZABLE` ảnh hưởng tới:

- Tập dữ liệu mà những câu truy vấn sau nhìn thấy.
- Khả năng xuất hiện lỗi đồng thời `40001`.
- Nhu cầu retry toàn bộ transaction.
- Thời gian giữ snapshot và tác động tới phiên bản cũ.
- Chi phí/chế độ locking và các rủi ro hiệu năng tùy workload.

Không tăng isolation level một cách mù quáng chỉ vì có một bug ở màn hình.

## 37. Spring @Transactional và snapshot

Trong Spring, mức cô lập có thể được yêu cầu theo cơ chế transaction manager:

```java
@Service
public class InventoryService {
    private final ProductRepository repository;

    public InventoryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public InventoryDto getInventory(long productId) {
        Product product = repository.findById(productId)
            .orElseThrow();
        return new InventoryDto(product.getId(), product.getQuantity());
    }
}
```

Đây là skeleton minh họa, cần định nghĩa class/import/repository ở dự án thực.

Những điểm cần lưu ý:

- `@Transactional` phải thực sự được áp dụng qua proxy/aspect/transaction manager theo cấu hình Spring.
- Isolation chỉ phát huy đúng khi truy vấn nằm trong **transaction thực** và dùng connection tương ứng.
- Một lời gọi tự gọi nội bộ cùng object có thể không đi qua proxy ở cấu hình Spring phổ biến.
- Transaction dài do remote API call hoặc xử lý lâu có thể giữ snapshot lâu và ảnh hưởng vacuum.
- Entity cache/ORM persistence context có thể tạo hành vi đọc lại dữ liệu khác với một query SQL thuần.

### Persistence context không phải snapshot của PostgreSQL

Hibernate/JPA có **first-level cache**. Đọc entity lần hai có thể trả object đang được quản lý mà không gửi lại câu SQL. Vì vậy, khi kiểm tra MVCC, hãy phân biệt:

1. PostgreSQL snapshot trả dữ liệu gì cho **câu SQL thực sự được gửi**.
2. ORM có gửi SQL không.
3. Cache ở ứng dụng/client có can thiệp không.

Không vội kết luận `REPEATABLE READ` gây “dữ liệu cũ” nếu nguyên nhân là ORM cache hoặc đọc từ standby đang lag.

## 38. Retry transaction bị lỗi 40001 và 40P01

Khi gặp:

- **`40001`**: serialization failure.
- **`40P01`**: deadlock detected.

Ứng dụng có thể có chính sách retry nếu nghiệp vụ **an toàn khi thử lại**.

Một luồng đúng:

```text
Attempt 1
  BEGIN
  SELECT dữ liệu làm căn cứ quyết định
  Tính logic nghiệp vụ
  INSERT/UPDATE
  COMMIT → 40001
  ROLLBACK nếu cần/dựa vào trạng thái transaction

Attempt 2: transaction MỚI
  BEGIN
  SELECT lại dữ liệu
  Tính lại logic
  INSERT/UPDATE
  COMMIT → thành công
```

Nếu lỗi xuất hiện tại `COMMIT`, transaction có thể đã bị kết thúc bằng abort; xử lý cần dựa vào trạng thái connection/driver thực. Không cố dùng lại snapshot cũ để chạy duy nhất câu UPDATE.

### Retry cần idempotency và giới hạn

- Giới hạn số lần thử và dùng backoff/jitter.
- Ghi số attempt cùng SQLSTATE.
- Không gửi email/thanh toán ra ngoài trước commit rồi lặp lại nhiều lần không kiểm soát.
- Dùng idempotency key/transactional outbox với side effects.
- Phân biệt lỗi PostgreSQL cho phép retry với lỗi network **khi kết quả commit chưa chắc chắn**.

## 39. Một query không thấy hàng: sơ đồ chẩn đoán

Khi ứng dụng nói “vừa INSERT nhưng SELECT không thấy”, kiểm tra theo thứ tự:

```text
               Không thấy hàng mới
                        │
                        ▼
              Đang ở database nào?
                        │
                        ▼
              Đúng schema/table không?
                        │
                        ▼
          Hàng mới đã COMMIT hay chưa?
                   │           │
                 Chưa         Rồi
                   │           │
       Reader khác không       ▼
       thấy là hợp lệ      Reader dùng snapshot cũ?
                               │
                        ┌──────┴────────┐
                        │               │
                  REPEATABLE READ   READ COMMITTED
                  snapshot cũ?      statement mới?
                        │               │
                        ▼               ▼
                 Kết thúc txn      Kiểm tra tiếp
                 rồi thử lại       replica lag / RLS /
                                    filter / cache
```

### Những nguyên nhân ngoài snapshot

- **Chưa commit** ở writer; transaction reader không được thấy ghi chưa commit.
- **Đọc từ standby** chưa replay WAL mới.
- **Sai database/schema** hoặc `search_path` khác.
- **RLS** lọc hàng theo role/policy.
- **Query WHERE/JOIN** loại hàng.
- **ORM cache** trả entity cũ.
- **Connection pool** dùng một transaction giữ lâu hơn tưởng tượng.
- **Rollback** ở writer sau lỗi làm hàng không tồn tại thực sự.

Không quy tất cả trường hợp “không thấy hàng” cho lỗi MVCC.

## 40. Dữ liệu cũ và số lượng truy vấn: transaction dài cần được giới hạn

`REPEATABLE READ` rất hữu ích cho báo cáo nhất quán, nhưng nếu request mở transaction rồi thực hiện:

```text
BEGIN REPEATABLE READ
  SELECT nhiều bảng
  gọi HTTP API 30 giây
  chờ người dùng xác nhận 5 phút
  xử lý thêm
COMMIT
```

thì transaction/snapshot có thể bị giữ lâu không cần thiết. Trong thời gian đó:

- Những lần đọc tiếp có thể không thấy dữ liệu đã commit sau snapshot.
- VACUUM có thể bị giới hạn khả năng dọn một số dead tuples.
- Connection bị chiếm.
- Một số thao tác khóa/ghi có thể gây tranh chấp.

### Nguyên tắc thiết kế

1. Giữ transaction ngắn theo công việc database thật sự cần chung một snapshot.
2. Không giữ transaction trong lúc chờ người dùng tương tác.
3. Không làm remote I/O dài trong transaction nếu có thể tách.
4. Đặt timeout theo SLA và xử lý rollback khi lỗi.
5. Đo `xact_start`, `state` và `backend_xmin` để phát hiện long-running snapshots.

## 41. Trường hợp snapshot không có nghĩa “time travel”

PostgreSQL MVCC **không tự cung cấp tính năng truy vấn tùy ý lại dữ liệu ở một thời điểm bất kỳ trong quá khứ**.

Một khi những phiên bản cũ đủ điều kiện được VACUUM thu hồi, ứng dụng không thể kỳ vọng chúng còn trong bảng để đọc lại theo một timestamp đã lưu.

Nếu yêu cầu là:

- Xem lịch sử thay đổi của đơn hàng.
- Audit ai sửa giá tiền, sửa lúc nào.
- Khôi phục một trạng thái nghiệp vụ cũ.
- Trả lời “số lượng tồn kho ở ngày 01/01/2025 là bao nhiêu?”

hãy thiết kế riêng **audit table, temporal model, event sourcing, change data capture hoặc PITR/backup** theo nhu cầu. `xmin`, `xmax` và snapshot thường không thay thế mô hình lịch sử nghiệp vụ.

### Vì sao không lưu pg_current_snapshot() vào app để đọc ngày mai?

Snapshot ID và các XID in-progress không phải một lời hứa PostgreSQL giữ mọi tuple version vĩnh viễn. `pg_export_snapshot()` cũng có vòng đời hữu hạn gắn với transaction xuất. Không xem chúng như token truy vấn lịch sử bền vững.

## 42. Những hiểu nhầm phổ biến

**“PostgreSQL SELECT luôn đọc bản mới nhất trên disk.”** Không. SELECT nhìn **phiên bản visible theo snapshot**, không nhất thiết phiên bản mới nhất đã được transaction khác tạo.

**“Snapshot là một timestamp; so created_at là đủ.”** Không. Snapshot dùng trạng thái transaction và các mốc XID, không chỉ giờ hệ thống.

**“XID lớn hơn luôn commit sau.”** Không. Thứ tự cấp ID khác thứ tự commit.

**“BEGIN luôn lấy ngay snapshot REPEATABLE READ.”** Không nhất thiết; snapshot thường được thiết lập ở statement thực sự cần nó đầu tiên.

**“READ UNCOMMITTED cho phép dirty read trong PostgreSQL.”** Không. PostgreSQL xử lý mức này như READ COMMITTED.

**“READ COMMITTED giữ một snapshot cho cả transaction.”** Không với SELECT thường; mỗi statement nhận snapshot mới.

**“REPEATABLE READ không thấy UPDATE của chính nó.”** Sai. Self-visible writes được xử lý riêng.

**“REPEATABLE READ bảo đảm serializable hoàn toàn.”** Không. Write skew vẫn có thể xảy ra; SERIALIZABLE dùng SSI.

**“SERIALIZABLE là khóa toàn bộ database.”** Không. Nó dùng cơ chế phát hiện dependency và có thể abort bằng 40001.

**“Snapshot cố định nghĩa UPDATE không bao giờ cần chờ.”** Sai. Writer cạnh tranh vẫn có row locks và quy tắc recheck/concurrent update.

**“SELECT không thấy key thì INSERT chắc chắn không conflict.”** Sai. Unique index phải xét transaction đồng thời, kể cả hàng chưa visible theo SELECT snapshot.

**“xmax khác 0 nghĩa đã DELETE.”** Sai. Metadata có thể phản ánh khóa row/MultiXact và cần xét trạng thái/cờ.

**“ctid là ID ổn định.”** Sai. Nó là vị trí vật lý của tuple version có thể đổi.

**“Chỉ cần tăng isolation là hết mọi lỗi.”** Không. Isolation mạnh có thể yêu cầu retry 40001 và có chi phí riêng.

**“VACUUM có thể xóa mọi bản cũ ngay.”** Không. Nó phải tôn trọng visibility horizon và snapshot còn cần dữ liệu.

**“n_dead_tup là số bản dead chính xác của snapshot tôi đang đọc.”** Không. Đây là thống kê ước lượng.

**“Replication standby không thấy dữ liệu là do REPEATABLE READ.”** Có thể là WAL replay lag; cần tách nguyên nhân.

**“Snapshot có thể lưu để truy vấn dữ liệu năm ngoái.”** Không. MVCC snapshot không phải cơ chế temporal history lâu dài.

**“ORM cache và PostgreSQL snapshot là một.”** Không. Cache ứng dụng có thể giữ dữ liệu mà không hề gửi SQL mới.

**“SELECT FOR UPDATE và SELECT thường có cùng hành vi chờ writer.”** Không. FOR UPDATE yêu cầu row locks và xử lý concurrent modification riêng.

## 43. Quy trình giải bài toán snapshot và visibility

Khi thiết kế hoặc chẩn đoán, có thể đi theo trình tự:

1. **Xác định isolation level thật**: `SHOW transaction_isolation` trên connection liên quan.
2. **Xác định transaction đã bắt đầu và đã lấy snapshot chưa**: thứ tự `BEGIN` và statement đầu, đặc biệt trong `REPEATABLE READ`.
3. **Xác định transaction nào tạo/thay đổi/xóa hàng**, và đã commit hay chưa.
4. **Phân biệt câu SELECT thường với locking/modifying statement** như `UPDATE`, `DELETE`, `SELECT FOR UPDATE`, `ON CONFLICT`.
5. **Kiểm tra self-visible writes** khi đang đọc dữ liệu do chính transaction tạo.
6. **Kiểm tra các lớp ngoài MVCC**: schema, RLS, filter, ORM cache, replication lag.
7. **Kiểm tra transaction dài** và khả năng ảnh hưởng tới VACUUM qua `pg_stat_activity`/`pg_stat_user_tables`.
8. **Chọn isolation phù hợp nghiệp vụ**; nếu yêu cầu serializable, xử lý 40001 bằng retry toàn transaction.
9. **Đảm bảo transaction ngắn và được commit/rollback** trước khi trả connection về pool.
10. **Dùng khóa nghiệp vụ và audit riêng**, không dựa vào `ctid` hoặc raw XID cho chức năng lâu dài.

Sơ đồ nhớ nhanh:

```text
          Một tuple version có trên disk
                       │
                       ▼
             Transaction tạo đã
             commit hợp lệ chưa?
                 │          │
                Chưa       Rồi
                 │          │
                 ▼          ▼
           Không visible  Xét việc xóa/thay thế
           (với txn khác)       │
                              ▼
                   Việc xóa có visible
                   theo snapshot không?
                       │         │
                      Có       Không
                       │         │
                       ▼         ▼
                Tuple cũ      Tuple cũ
                bị loại       có thể visible

    + Quy tắc riêng cho self-writes, locks, subtransactions,
      command IDs và cơ chế concurrent modification.
```

Sơ đồ là mô hình giải thích, không thay thế thuật toán MVCC thực tế.

## 44. Bài tập thực hành

### Bài 1 — Quan sát system columns

Trong lab, chạy `SELECT product_id, xmin, xmax, ctid FROM lesson_mvcc.products`. Ghi lại ý nghĩa các trường. Vì sao không được dùng `ctid` hoặc `xmin` làm khóa nghiệp vụ?

### Bài 2 — Dirty read

Session A mở transaction và đặt `quantity = 777` nhưng chưa commit. Session B chạy SELECT cùng hàng. Dự đoán B thấy gì và vì sao. Sau đó A rollback.

### Bài 3 — READ UNCOMMITTED

Lặp lại bài 2 ở session B với `BEGIN ISOLATION LEVEL READ UNCOMMITTED`. PostgreSQL có cho dirty read không?

### Bài 4 — READ COMMITTED hai lần SELECT

Session A mở `READ COMMITTED`, SELECT quantity. Session B UPDATE rồi COMMIT. A SELECT lại trước khi COMMIT. Giải thích tại sao giá trị có thể thay đổi.

### Bài 5 — REPEATABLE READ hai lần SELECT

Lặp lại bài 4 nhưng A dùng `REPEATABLE READ` và phải thực hiện SELECT đầu tiên **trước khi B commit**. Giải thích tại sao A tiếp tục thấy dữ liệu cũ.

### Bài 6 — Thời điểm lấy snapshot

A gửi `BEGIN ISOLATION LEVEL REPEATABLE READ` nhưng chưa SELECT. B UPDATE và COMMIT. A mới SELECT lần đầu. A có nhất thiết thấy dữ liệu cũ từ trước BEGIN không? Giải thích.

### Bài 7 — Self-visible writes

Trong một `REPEATABLE READ` transaction, SELECT sản phẩm, UPDATE quantity rồi SELECT lại. Giải thích vì sao transaction thấy thay đổi của chính nó, sau đó ROLLBACK.

### Bài 8 — Phantom read

A READ COMMITTED đếm sản phẩm quantity >= 10. B chèn sản phẩm phù hợp và COMMIT. A đếm lại. Đây là hiện tượng gì? Trường hợp REPEATABLE READ có gì khác?

### Bài 9 — XID và thứ tự commit

Giả sử T100 bắt đầu trước T101 nhưng T101 commit trước. Một snapshot lấy giữa hai lần commit có nhìn thấy thay đổi của T100 và T101 giống nhau không? Giải thích bằng danh sách transaction in-progress.

### Bài 10 — Tuple mới và cũ

Vẽ hai tuple versions cho một UPDATE từ quantity 10 thành 8. Giải thích snapshot trước và sau commit của writer có thể thấy phiên bản nào.

### Bài 11 — xmax và row locking

Vì sao không thể dùng `WHERE xmax = 0` như quy tắc tổng quát để xác định mọi hàng chưa bị delete? Nêu vai trò row lock, MultiXact và transaction status.

### Bài 12 — SELECT FOR UPDATE

Session A khóa product 1 với `SELECT ... FOR UPDATE` trong transaction. Session B thử `FOR UPDATE NOWAIT` cùng hàng. Dự đoán lỗi có thể nhận và yêu cầu rollback sau lỗi trong transaction tường minh.

### Bài 13 — UPDATE đồng thời ở READ COMMITTED

A sửa quantity 10 thành 3 nhưng chưa commit. B UPDATE với `WHERE quantity >= 5` và có thể phải chờ. Sau khi A commit, PostgreSQL xử lý điều kiện B thế nào? Vì sao không nên coi UPDATE như SELECT snapshot thuần?

### Bài 14 — REPEATABLE READ concurrent update

A lấy snapshot khi product có quantity 10. B đổi quantity rồi COMMIT. A cố UPDATE cùng hàng. Trường hợp nào có thể phát sinh `40001` và ứng dụng cần làm gì?

### Bài 15 — Unique constraint và invisible row

A INSERT key `same-key` nhưng chưa commit. B SELECT không thấy key rồi thử INSERT cùng key. Vì sao B vẫn có thể phải chờ hoặc nhận `23505`?

### Bài 16 — ON CONFLICT và snapshot

Giải thích vì sao `ON CONFLICT DO NOTHING` dưới READ COMMITTED có thể không insert dù hàng gây conflict không visible trong snapshot SELECT thông thường của statement.

### Bài 17 — Lost update

Hai request cùng đọc quantity 10 rồi gửi `UPDATE SET quantity = 11`. Giải thích nguy cơ lost update. Sửa bằng `quantity = quantity + 1` hoặc optimistic locking với version column.

### Bài 18 — Write skew

Hai bác sĩ đều đang trực; hai transaction cùng kiểm tra “ít nhất một người trực” rồi mỗi transaction cho một người nghỉ. Vì sao REPEATABLE READ có thể không bảo vệ bất biến liên hàng? SERIALIZABLE xử lý ra sao?

### Bài 19 — pg_current_snapshot

Đọc `pg_current_snapshot()`, `pg_snapshot_xmin()`, `pg_snapshot_xmax()` và `pg_snapshot_xip()` trên PostgreSQL hiện đại. Giải thích ý nghĩa khái quát của xmin, xmax và tập XID in-progress.

### Bài 20 — Long-running snapshot

A mở REPEATABLE READ, SELECT và giữ transaction mở. B UPDATE nhiều hàng, COMMIT rồi VACUUM ở phiên khác khi phù hợp. Tại sao một số phiên bản cũ có thể chưa được thu hồi? Kết thúc A rồi đối chiếu tình trạng sau những lần VACUUM phù hợp. **Chỉ thực hiện trên lab nhỏ và không chạy thao tác bảo trì nặng trên production.**

### Bài 21 — pg_stat_activity

Từ session giám sát, truy vấn `pid`, `state`, `xact_start` và `backend_xmin`. Tìm transaction dài và phân biệt `xact_start` với thời điểm snapshot thực sự được thiết lập.

### Bài 22 — Snapshot trên standby

Một write commit thành công trên primary nhưng SELECT ngay trên standby chưa thấy hàng. Liệt kê cách phân biệt replication lag với transaction snapshot cũ, RLS và ORM cache.

### Bài 23 — Export/import snapshot

Với hai session thử nghiệm, A `BEGIN REPEATABLE READ` rồi `pg_export_snapshot()`. B `BEGIN REPEATABLE READ` và `SET TRANSACTION SNAPSHOT` bằng ID thật trước khi chạy SELECT. A phải giữ transaction mở tới thời điểm nào?

### Bài 24 — Java/JDBC isolation

Viết ví dụ JDBC đặt `Connection.TRANSACTION_REPEATABLE_READ` trước transaction, chạy SELECT, commit/rollback và phục hồi connection state. Vì sao không được đổi isolation giữa transaction đã có snapshot?

### Bài 25 — Retry SERIALIZABLE

Thiết kế pseudocode retry toàn transaction khi `40001`. Mỗi attempt cần đọc lại dữ liệu và tính lại quyết định. Vì sao chỉ retry câu UPDATE cuối là không đủ?

### Bài 26 — Snapshot không phải time travel

Ứng dụng cần truy vấn số dư từng ngày trong ba năm. Vì sao không thể lưu `pg_current_snapshot()` hàng ngày rồi mặc định dùng nó để xem lại bất kỳ lúc nào? Đề xuất audit/event history hoặc mô hình temporal riêng.

### Bài 27 — Thiết kế API thấy dữ liệu mới

Một API ghi vào primary rồi đọc ngay trên read replica và đôi khi trả trạng thái cũ. Đề xuất lựa chọn đọc từ primary khi cần read-your-writes, theo dõi replay lag, hoặc giao thức chờ replica đạt LSN phù hợp. Nêu rõ vì sao nâng isolation level trên replica không tự giải quyết replication lag.

### Bài 28 — Đánh giá chi phí isolation

Một báo cáo chạy một giờ trong REPEATABLE READ. Hãy phân tích lợi ích snapshot nhất quán và các rủi ro transaction dài: retention dead tuples, connection occupancy và autovacuum. Đề xuất cách giới hạn scope và tách những bước xử lý không cần giữ snapshot.

## Kết luận

**MVCC** cho phép PostgreSQL lưu nhiều phiên bản của một hàng và chọn phiên bản phù hợp cho từng câu truy vấn bằng **snapshot**. Một tuple tồn tại vật lý không có nghĩa mọi transaction đều nhìn thấy nó: việc nhìn thấy phụ thuộc transaction tạo phiên bản đã commit hay chưa, transaction xóa/thay thế đã visible hay chưa, danh sách transaction in-progress và những quy tắc tự nhìn thấy trong transaction hiện tại.

Trong **`READ COMMITTED`**, các câu `SELECT` thông thường nhận **snapshot mới theo từng statement**, nên một transaction có thể thấy giá trị khác nhau giữa hai lần đọc. Trong **`REPEATABLE READ`**, snapshot được duy trì cho transaction sau khi được thiết lập, giúp đọc nhất quán nhưng vẫn thấy các thay đổi của chính mình. **`SERIALIZABLE`** bổ sung cơ chế SSI để ngăn những lịch tương tranh không tương đương thực thi tuần tự, đổi lại ứng dụng phải xử lý lỗi `40001` và retry toàn transaction khi phù hợp.

Không nên đồng nhất snapshot SELECT với mọi thao tác khác: **`UPDATE`/`DELETE`/`SELECT FOR UPDATE`** có khóa và quy tắc xử lý concurrency riêng; **unique constraints** và **`ON CONFLICT`** phải xét conflict kể cả những hàng chưa visible cho SELECT thông thường. Và vì snapshot cũ có thể cần tuple versions cũ, transaction dài có thể trì hoãn khả năng dọn dẹp của **VACUUM**.

Để thiết kế hệ thống đúng, hãy kiểm tra **đúng isolation level, đúng thời điểm lấy snapshot, commit status của writer, self-writes, replication lag, RLS và cache của ứng dụng** trước khi kết luận dữ liệu “không nhất quán”. Dùng `pg_current_snapshot()`, `pg_stat_activity` và thống kê vacuum như công cụ quan sát; dùng primary key, version columns và cơ chế audit riêng cho nghiệp vụ. Hiểu rõ snapshot cùng quy tắc visibility là nền tảng để tận dụng hiệu năng MVCC mà vẫn giữ tính đúng đắn của giao dịch PostgreSQL.
