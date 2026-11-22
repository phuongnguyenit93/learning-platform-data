# Thí nghiệm hai phiên để quan sát khả năng nhìn thấy dữ liệu trong PostgreSQL

Khi hai người dùng truy cập cùng một bảng PostgreSQL, điều họ **nhìn thấy** không chỉ phụ thuộc vào giá trị đang được lưu. Nó còn phụ thuộc vào thời điểm transaction bắt đầu, thời điểm lấy snapshot, mức cô lập, transaction nào đã `COMMIT` hoặc `ROLLBACK` và chính transaction đang đọc có tự thay đổi dữ liệu hay không.

Ví dụ đơn giản:

1. Phiên A đang sửa tồn kho từ 10 xuống 7 nhưng **chưa commit**.
2. Phiên B đọc cùng sản phẩm.
3. Phiên B nhìn thấy 10 hay 7? Nếu A rollback thì sao?
4. Nếu B đọc lần nữa **sau khi A commit**, kết quả có đổi trong cùng transaction không?

Những câu hỏi này là cách trực quan để hiểu **Multi-Version Concurrency Control (MVCC)**. PostgreSQL giữ các phiên bản hàng cần thiết để các giao dịch có thể đọc một trạng thái nhất quán mà không phải chờ mọi thao tác ghi. Tuy nhiên, các mức cô lập có quy tắc về snapshot và cập nhật khác nhau.

Bài học thuộc chương **MVCC** của module *Database Engine Relational PostgreSQL*. Nội dung là một phòng thực hành từng bước bằng **hai cửa sổ `psql` độc lập**, kèm giải thích kết quả mong đợi, các giới hạn cần biết và mẫu quan sát khi dùng JDBC.

**Sau bài này, bạn có thể:**

- Giải thích tại sao phiên B không đọc được thay đổi chưa commit từ phiên A.
- Chứng minh một transaction **đọc thấy thay đổi do chính nó thực hiện** dù phiên khác chưa nhìn thấy.
- Quan sát `READ COMMITTED` lấy snapshot mới ở các statement khác nhau.
- Quan sát `REPEATABLE READ` duy trì snapshot ổn định trong transaction, kể cả với bản ghi mới được chèn.
- Phân biệt **non-repeatable read**, **phantom read**, **row-lock blocking** và **serialization failure `40001`**.
- Thấy vì sao `READ UNCOMMITTED` của PostgreSQL thực tế có hành vi như `READ COMMITTED`.
- Đọc `xmin`, `ctid` và các thông tin theo dõi giao dịch như **dấu vết kỹ thuật**, không hiểu nhầm chúng là bản ghi lịch sử nghiệp vụ hoàn chỉnh.
- Thiết kế, dọn dẹp và chạy lại một bài thử hai phiên mà không để transaction mở kéo dài.

> **An toàn:** Các câu `UPDATE`, `INSERT` và `DELETE` trong bài chỉ dành cho schema riêng `mvcc_lab` của database thử nghiệm. Không chạy trên bảng sản xuất. Các phần ghi chú “Session A” và “Session B” cần được thực thi **đan xen bằng hai kết nối độc lập**, không chạy gộp tuần tự trong cùng một cửa sổ rồi kỳ vọng có tính đồng thời.

---

## 1. Một mô hình trực quan về MVCC

Trong hệ quản trị sử dụng MVCC, cập nhật một hàng về mặt logic không nhất thiết đơn giản là “ghi đè ngay một giá trị mà mọi phiên đều đọc cùng lúc”.

Giả sử một hàng có thông tin:

```text
SKU-A | stock = 10
```

Phiên A bắt đầu transaction và cập nhật tồn kho còn 7:

```text
Trước cập nhật:

    phiên bản V1: SKU-A, stock=10

Sau UPDATE trong transaction A, trước COMMIT:

    phiên bản V1: SKU-A, stock=10    <-- có thể vẫn thấy từ snapshot phù hợp
    phiên bản V2: SKU-A, stock=7     <-- thay đổi của A, chưa commit
```

Truy vấn thông thường ở phiên B **không lấy dữ liệu chưa commit** của A. B có thể tiếp tục đọc phiên bản đã commit phù hợp với snapshot của mình. Sau khi A commit, những snapshot mới có thể thấy giá trị 7.

Đây chỉ là **sơ đồ khái niệm**. PostgreSQL quản lý tuple versions, transaction IDs, commit status, snapshot và dọn dẹp phiên bản chết theo những quy tắc nội bộ cụ thể. Không suy ra mỗi `UPDATE` luôn có đúng hai bản vật lý tồn tại vĩnh viễn.

### 1.1. Bốn câu hỏi khác nhau

| Câu hỏi | Cơ chế liên quan |
|---|---|
| Một hàng đã được transaction khác commit chưa? | Transaction visibility / commit status |
| Snapshot của câu lệnh có nhìn thấy phiên bản mới không? | Snapshot và isolation level |
| Chính transaction này vừa sửa hàng, nó đọc lại thấy gì? | Self-visibility / thứ tự statement |
| UPDATE của hai phiên cùng đụng một hàng thì sao? | Row locks, chờ và quy tắc update theo isolation |

**Không đồng nhất “không nhìn thấy phiên bản mới” với “không biết có khóa”.** Một phiên có thể đọc phiên bản cũ bằng `SELECT` thông thường, nhưng khi nó muốn sửa chính hàng đang bị khóa bởi transaction khác, câu `UPDATE` lại phải chờ.

### 1.2. Snapshot là gì?

Snapshot mô tả tập các thay đổi/transaction được coi là đã nhìn thấy tại một mốc logic, theo quy tắc MVCC và isolation. Trong PostgreSQL:

- Ở `READ COMMITTED`, mỗi **statement** thông thường bắt đầu với một snapshot mới.
- Ở `REPEATABLE READ` và `SERIALIZABLE`, các câu đọc thông thường dùng snapshot của transaction, được thiết lập khi snapshot của transaction được lấy lần đầu theo quy tắc isolation.
- Transaction luôn có quy tắc để thấy các thay đổi phù hợp **do chính nó thực hiện** trước đó; “snapshot cố định” không có nghĩa nó không thấy bất kỳ cập nhật nào do chính nó vừa ghi.

**Lưu ý:** Gõ `BEGIN` chưa đồng nghĩa mọi mức cô lập đã chụp snapshot dữ liệu ngay tại đúng dòng `BEGIN`. Với `REPEATABLE READ`, snapshot thường được lấy khi statement đầu tiên cần snapshot chạy. Vì vậy bài lab sắp thứ tự `SELECT` rất rõ.

### 1.3. Tính cô lập và tính đúng đắn không phải một nút bật/tắt

MVCC không tự giải quyết mọi bài toán kinh doanh:

- `READ COMMITTED` cho phép hai lần đọc trong cùng transaction nhìn thấy dữ liệu mới được commit giữa hai câu lệnh.
- `REPEATABLE READ` ổn định việc đọc snapshot, nhưng một giao dịch đọc một số hàng rồi ghi hàng khác vẫn có thể gặp **write skew**.
- `SERIALIZABLE` bảo đảm kết quả commit tương đương một thứ tự giao dịch tuần tự hợp lệ, nhưng có thể từ chối transaction bằng `SQLSTATE 40001` và yêu cầu retry toàn bộ transaction.

Bài này tập trung vào **khả năng nhìn thấy dữ liệu** và chỉ giới thiệu những hệ quả cạnh tranh ghi cần thiết để đọc đúng kết quả thí nghiệm.

---

## 2. Chuẩn bị: hai kết nối và một bảng thực hành

### 2.1. Điều kiện môi trường

Bạn cần:

1. Một PostgreSQL server mà bạn có quyền tạo schema và bảng thực hành.
2. Hai terminal/cửa sổ SQL độc lập, cùng kết nối **một database**.
3. Một công cụ thực thi lệnh SQL, tốt nhất là `psql` vì dễ quan sát transaction và lệnh chờ.
4. Quyền xem/sửa schema `mvcc_lab` do bạn tạo.

Để tránh nhầm:

```text
Terminal A -> Connection A -> PostgreSQL database lab
Terminal B -> Connection B -> PostgreSQL database lab
```

Hai tab trong một IDE có thể dùng **chung connection** tùy cấu hình. Hãy chắc chắn chúng không cùng một session backend trước khi bắt đầu.

### 2.2. Kết nối bằng psql

Ví dụ hai terminal đều chạy:

```bash
psql -h localhost -p 5432 -U lab_user -d lab_database
```

Thay `lab_user` và `lab_database` bằng tài khoản/database của bạn. Không đưa mật khẩu vào lệnh terminal hoặc source code; dùng cơ chế xác thực phù hợp môi trường.

Trong cửa sổ A:

```sql
SELECT pg_backend_pid() AS session_a_pid;
```

Trong cửa sổ B:

```sql
SELECT pg_backend_pid() AS session_b_pid;
```

Hai PID phải **khác nhau**. Có thể đặt tên theo phiên để thuận tiện quan sát:

**Session A:**

```sql
SET application_name = 'mvcc-lab-A';
```

**Session B:**

```sql
SET application_name = 'mvcc-lab-B';
```

### 2.3. Xem trạng thái isolation

Chạy ở cả hai session khi chưa mở transaction:

```sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
SHOW transaction_read_only;
```

Thông thường cấu hình mặc định là `read committed`, nhưng đừng mặc định mọi server đều như nhau. Các phần thí nghiệm sẽ **khai báo isolation rõ trong `BEGIN`**, để không phụ thuộc setting của phiên.

### 2.4. Tạo schema và dữ liệu ban đầu

Chỉ thực thi khối này **một lần**, khi cả hai phiên chưa có transaction đang mở:

```sql
CREATE SCHEMA IF NOT EXISTS mvcc_lab;

CREATE TABLE mvcc_lab.inventory (
    sku TEXT PRIMARY KEY,
    stock INTEGER NOT NULL CHECK (stock >= 0),
    description TEXT NOT NULL
);

CREATE TABLE mvcc_lab.inventory_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL REFERENCES mvcc_lab.inventory(sku),
    event_type TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);

INSERT INTO mvcc_lab.inventory (sku, stock, description)
VALUES ('SKU-A', 10, 'Sản phẩm thử nghiệm MVCC')
ON CONFLICT (sku) DO UPDATE
SET stock = EXCLUDED.stock,
    description = EXCLUDED.description;
```

Bảng thứ nhất có **một sản phẩm** với tồn kho ban đầu 10. Bảng thứ hai chứa các sự kiện để thử việc **đếm hàng vừa được INSERT**.

**Vì sao chỉ một sản phẩm?** Khi số lượng hàng ít và trạng thái rõ, bạn sẽ dễ chứng minh thứ gì đang được nhìn thấy hơn là thử trên một bảng lớn có dữ liệu biến động liên tục.

### 2.5. Quy trình reset trước từng bài

Chỉ reset khi **mọi transaction của cả hai phiên đã kết thúc bằng `COMMIT` hoặc `ROLLBACK`**, nếu không lệnh reset có thể phải chờ lock hoặc tạo trạng thái xen kẽ khó hiểu.

```sql
-- Chạy ở một phiên không nằm trong transaction lab đang mở.
UPDATE mvcc_lab.inventory
SET stock = 10
WHERE sku = 'SKU-A';

DELETE FROM mvcc_lab.inventory_events;
```

Lệnh `DELETE` để trống bảng event; sequence của identity có thể **không quay về 1** sau khi delete. Các bài tập đếm sự kiện chỉ dùng `COUNT(*)` nên **không giả định event_id bắt đầu bằng 1**.

Nếu muốn đặt lại identity trong lab riêng, có thể cân nhắc `TRUNCATE ... RESTART IDENTITY` sau khi đánh giá FK, nhưng **không cần thiết** cho các thí nghiệm này.

### 2.6. Xác nhận trạng thái chuẩn

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
ORDER BY sku;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events;
```

Kết quả chuẩn:

```text
sku   | stock
------+------
SKU-A | 10

event_count = 0
```

### 2.7. Quy tắc vận hành hai phiên

- **Không thực thi liên tiếp toàn bộ phần của A rồi mới đến B.** Dòng “dừng tại đây” nghĩa là giữ transaction mở để phiên khác chạy xen vào.
- Nếu một câu ở B **đang chờ khóa**, hãy quay sang A để `COMMIT` hoặc `ROLLBACK` rồi quan sát B.
- Sau mỗi kịch bản, kết thúc mọi transaction trước khi reset.
- Nếu thấy prompt `psql` có trạng thái transaction lỗi hoặc `current transaction is aborted`, hãy `ROLLBACK` phiên đó trước khi tiếp tục.
- Không dùng công cụ SQL tự động commit từng câu khi thử các kịch bản yêu cầu giữ transaction mở; hãy xác minh cấu hình autocommit/transaction của client.

---

## 3. Thí nghiệm 1 — Phiên B không đọc được thay đổi chưa COMMIT

**Mục tiêu:** quan sát **dirty read bị ngăn** và thấy rằng chính transaction A lại đọc được dữ liệu nó vừa thay đổi.

Trước khi chạy, reset tồn kho về 10.

### Bước 1 — Session A bắt đầu transaction

**Chỉ chạy trong A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Kết quả:

```text
SKU-A | 10
```

### Bước 2 — Session A cập nhật nhưng chưa commit

**Trong A:**

```sql
UPDATE mvcc_lab.inventory
SET stock = 7
WHERE sku = 'SKU-A'
RETURNING sku, stock;
```

Kết quả của A:

```text
SKU-A | 7
```

Tiếp tục đọc ngay trong A:

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

A nhìn thấy **7**. **Chưa chạy `COMMIT` hoặc `ROLLBACK`.**

### Bước 3 — Session B đọc trong lúc A chưa commit

**Chuyển sang B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B nhìn thấy:

```text
SKU-A | 10
```

**Vì sao B vẫn thấy 10?** Phiên bản `stock=7` do A tạo vẫn nằm trong transaction **chưa commit**. Snapshot bình thường ở B không coi bản cập nhật này là dữ liệu đã được xác nhận. Vì vậy PostgreSQL chọn phiên bản cũ `stock=10` còn nhìn thấy được.

### Bước 4 — Session A ROLLBACK

**Trở lại A:**

```sql
ROLLBACK;
```

Bây giờ bản cập nhật `stock=7` của A đã bị hủy.

### Bước 5 — Session B đọc lại và kết thúc

**Trong B:**

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B vẫn nhìn thấy `10`. Sau `ROLLBACK` của A, không có thay đổi nào mới trở thành committed.

### Bảng diễn tiến

| Thời điểm | Session A | Session B | Giá trị B nhìn thấy |
|---|---|---|---|
| T0 | Không có transaction đang mở | Không có transaction đang mở | 10 |
| T1 | `BEGIN`, đọc 10 | — | — |
| T2 | `UPDATE stock=7`, chưa commit | — | — |
| T3 | — | `SELECT` | **10** |
| T4 | `ROLLBACK` | — | — |
| T5 | — | `SELECT` lại | **10** |

**Kết luận:** phiên khác không đọc giá trị **chưa commit**. Chính A nhìn thấy thay đổi do A đã thực hiện trong transaction của mình. Đây là hai quy tắc riêng cần nhớ cùng lúc.

---

## 4. Thí nghiệm 2 — READ COMMITTED có thể nhìn thấy dữ liệu mới ở lần đọc tiếp theo

**Mục tiêu:** quan sát **non-repeatable read** ở mức `READ COMMITTED`: cùng một transaction B đọc **một hàng hai lần**, nhưng giá trị khác nhau vì transaction A đã commit ở giữa.

Reset tồn kho về `10` và đảm bảo A/B không còn transaction mở.

### Bước 1 — Session B bắt đầu và đọc lần đầu

**Trong B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B nhìn thấy `10`. Giữ B đang trong transaction.

### Bước 2 — Session A cập nhật và COMMIT

**Trong A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 6
WHERE sku = 'SKU-A'
RETURNING sku, stock;

COMMIT;
```

A đã commit giá trị `6`. Không phải B đang đọc liên tục; hai câu SELECT của B được tách ra trước và sau commit này.

### Bước 3 — Session B đọc lần thứ hai trong CÙNG transaction

**Trong B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B lần này nhìn thấy `6`, dù nó đã mở transaction từ lúc giá trị còn là 10.

### Bảng diễn tiến

| Bước | Session A | Session B | Kết quả B |
|---|---|---|---|
| 1 | — | `BEGIN READ COMMITTED`, `SELECT` | 10 |
| 2 | `UPDATE 6; COMMIT` | Chưa đọc lại | — |
| 3 | — | `SELECT` lần hai | **6** |
| 4 | — | `COMMIT` | — |

### Tại sao không mâu thuẫn với MVCC?

MVCC không hứa **mọi transaction đều nhìn đúng một snapshot từ đầu đến cuối**. Nó cung cấp cơ chế version visibility, còn **isolation level** xác định snapshot nào sẽ dùng.

Ở PostgreSQL `READ COMMITTED`, mỗi lệnh `SELECT` thông thường nhận snapshot mới khi lệnh bắt đầu. Câu thứ hai của B bắt đầu **sau khi A commit**, nên được phép thấy `stock=6`.

### Khái niệm non-repeatable read

`Non-repeatable read` là tình huống transaction đọc cùng một hàng hai lần và quan sát **giá trị thay đổi** bởi một transaction khác đã commit giữa hai lần đọc.

Không nhầm với:

- **Dirty read:** nhìn thấy dữ liệu transaction khác chưa commit — thí nghiệm 1 cho thấy PostgreSQL không cho phép kiểu đọc đó.
- **Phantom read:** chạy lại truy vấn theo điều kiện và số **hàng phù hợp** thay đổi — thí nghiệm 4 sẽ minh họa.

---

## 5. Thí nghiệm 3 — REPEATABLE READ giữ snapshot cũ trong cùng transaction

**Mục tiêu:** lặp lại kịch bản của thí nghiệm 2 nhưng chuyển B sang `REPEATABLE READ` để thấy khác biệt.

Reset tồn kho về `10` trước khi bắt đầu.

### Bước 1 — B bắt đầu REPEATABLE READ và đọc

**Trong B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B nhìn thấy `10`. Đây là statement đọc đầu tiên cần snapshot dữ liệu của B trong thí nghiệm. **Giữ transaction B mở.**

### Bước 2 — A cập nhật và commit

**Trong A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 4
WHERE sku = 'SKU-A'
RETURNING stock;

COMMIT;
```

A commit giá trị `4` thành công.

### Bước 3 — B đọc lần hai

**Trong B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B **vẫn nhìn thấy `10`**. Dù A đã commit, B vẫn đang dùng snapshot phù hợp với transaction `REPEATABLE READ` của mình, được thiết lập trước lúc A commit.

### Bước 4 — B kết thúc transaction rồi đọc lần mới

**Trong B:**

```sql
COMMIT;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Câu `SELECT` **sau COMMIT** chạy trong transaction mới do autocommit thông thường của `psql`, nên giờ nhìn thấy **4**.

### Bảng đối chiếu kết quả

| Tình huống | B đọc đầu tiên | A commit cập nhật | B đọc lại khi transaction còn mở | B đọc trong transaction mới |
|---|---:|---:|---:|---:|
| `READ COMMITTED` | 10 | 6 | **6** | 6 |
| `REPEATABLE READ` | 10 | 4 | **10** | 4 |

Hai hàng dùng **hai lần reset và hai lần thử riêng**. Không nên so sánh 6 và 4 như thể chúng xuất hiện trong cùng một lịch chạy.

### 5.1. REPEATABLE READ không có nghĩa A không thể commit

A vẫn có thể cập nhật và commit hàng; B chỉ đang **đọc phiên bản cũ phù hợp snapshot**. Một `SELECT` thông thường ở B không tự lấy row lock chặn A như `SELECT ... FOR UPDATE`.

### 5.2. B đọc mới sau commit vì snapshot không sống mãi

Sau khi B `COMMIT`/`ROLLBACK`, transaction cũ và snapshot cũ không còn là ranh giới cho câu đọc mới. Bắt đầu transaction mới là cách đơn giản để quan sát dữ liệu đã commit sau đó.

### 5.3. Transaction B có thấy chính thay đổi của nó không?

**Có**, nếu chính B thực hiện thao tác ghi hợp lệ trong transaction, các statement sau của B có thể thấy thay đổi do nó tạo. `REPEATABLE READ` cố định quan sát những thay đổi **của transaction khác** theo snapshot, không làm transaction bị “mù” trước thao tác của chính mình.

---

## 6. Thí nghiệm 4 — Bản ghi mới được INSERT và hiện tượng phantom

**Mục tiêu:** không chỉ đọc lại một giá trị của cùng hàng, mà chạy lại truy vấn `COUNT(*)` để xem **số hàng thỏa điều kiện** có đổi không.

Bảng `mvcc_lab.inventory_events` đã được tạo từ đầu. Đảm bảo không có transaction đang mở, rồi reset:

```sql
DELETE FROM mvcc_lab.inventory_events;
```

### 6.1. Phần A — READ COMMITTED thấy hàng vừa được COMMIT

**Session B — bắt đầu và đếm:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

Kết quả `0`.

**Session A — thêm một sự kiện và commit:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

INSERT INTO mvcc_lab.inventory_events(sku, event_type)
VALUES ('SKU-A', 'received');

COMMIT;
```

**Session B — đếm lại trong cùng transaction:**

```sql
SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';

COMMIT;
```

Kết quả mới **1**.

### 6.2. Vì sao gọi là phantom?

Lần đầu query “số sự kiện của SKU-A” không có hàng nào. Sau khi A commit, cùng điều kiện lọc trả **một hàng mới**.

```text
READ COMMITTED

B lần 1: WHERE sku='SKU-A'  -> 0 hàng
A:       INSERT + COMMIT
B lần 2: WHERE sku='SKU-A'  -> 1 hàng
```

Hiện tượng **phantom read** được minh họa bằng sự thay đổi tập hàng phù hợp với một predicate, thay vì chỉ thay đổi một giá trị trong hàng đã tồn tại.

### 6.3. Phần B — REPEATABLE READ không thấy phantom từ A

Giữ lại một sự kiện đã commit ở phần trước; không nhất thiết reset, nhưng kiểm tra hiện tại có đúng 1 sự kiện và không có transaction mở trước khi bắt đầu.

**Session B — bắt đầu và đếm:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

Kết quả `1`.

**Session A — thêm sự kiện mới và commit:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

INSERT INTO mvcc_lab.inventory_events(sku, event_type)
VALUES ('SKU-A', 'sold');

COMMIT;
```

**Session B — đếm lại khi transaction REPEATABLE READ còn mở:**

```sql
SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

B **vẫn thấy 1**. Sau đó:

```sql
COMMIT;

SELECT COUNT(*) AS event_count
FROM mvcc_lab.inventory_events
WHERE sku = 'SKU-A';
```

Lần đọc mới thấy **2**.

### 6.4. Lưu ý quan trọng về tên “phantom”

Trong nhiều hệ quản trị, tên isolation level có thể gợi ý các hành vi khác nhau. Với PostgreSQL, mức `REPEATABLE READ` dùng snapshot isolation và **không thấy những hàng mới do transaction khác commit** khi transaction hiện tại đang giữ snapshot.

Tuy nhiên, điều đó **không chứng minh mọi kết quả của hai giao dịch REPEATABLE READ luôn serializable**. Write skew vẫn có thể xảy ra khi hai transaction dựa trên một tập dữ liệu chung rồi ghi các hàng khác nhau.

---

## 7. Thí nghiệm 5 — UPDATE chờ row lock dù SELECT vẫn đọc được phiên bản cũ

**Mục tiêu:** hiểu vì sao **khả năng nhìn thấy dữ liệu** và **khả năng ghi** là hai vấn đề khác nhau.

Reset `stock=10` và kết thúc mọi transaction cũ.

### Bước 1 — Session A sửa hàng và giữ transaction

**Trong A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 2
WHERE sku = 'SKU-A'
RETURNING stock;
```

A thấy `stock=8`. **Chưa commit.**

### Bước 2 — Session B SELECT bình thường

**Trong B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B vẫn thấy **10**, vì `8` của A chưa commit.

### Bước 3 — Session B cố UPDATE cùng hàng

**Trong B, gửi lệnh sau và để nó chạy chờ:**

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
RETURNING stock;
```

Thông thường lệnh **bị chờ** vì A đang giữ khóa ghi trên cùng hàng. Đây không phải là hiện tượng B “đọc dơ”; B đang cố **sửa một hàng mà transaction khác chưa kết thúc thao tác sửa**.

### Bước 4 — Session A COMMIT để giải phóng tranh chấp

**Quay sang A:**

```sql
COMMIT;
```

A commit `stock=8`. B có thể tiếp tục xử lý lệnh `UPDATE` đang chờ.

### Bước 5 — Session B hoàn tất UPDATE

**Quay sang B để xem kết quả của lệnh đang chờ.**

```text
stock
-----
5
```

Trong lịch chạy nêu trên, `READ COMMITTED` cho phép câu `UPDATE` của B làm việc với phiên bản hàng mới sau khi A đã commit, nên từ `8` trừ `3` được **5**. B kết thúc:

```sql
COMMIT;
```

### Bảng diễn tiến

| Thời điểm | Session A | Session B |
|---|---|---|
| T0 | stock=10 | stock=10 |
| T1 | `UPDATE stock=stock-2` → nhìn 8, chưa commit | — |
| T2 | — | `SELECT` thông thường vẫn thấy 10 |
| T3 | — | `UPDATE stock=stock-3` chờ |
| T4 | `COMMIT`, hàng thành 8 | UPDATE được tiếp tục |
| T5 | — | UPDATE tính từ 8 → **5**; `COMMIT` |

**Kết luận:** PostgreSQL không bắt `SELECT` bình thường phải chờ hàng đang bị sửa chỉ để đọc phiên bản đã commit, nhưng một `UPDATE` cạnh tranh trên cùng hàng thường phải phối hợp khóa và xử lý phiên bản sau khi chờ.

### 7.1. Vì sao câu UPDATE trừ 3 không dùng lại “10” cũ?

Ở `READ COMMITTED`, lệnh `UPDATE` có cơ chế xử lý row bị transaction khác thay đổi trong lúc chờ: sau khi transaction kia hoàn tất, PostgreSQL có thể **đánh giá lại điều kiện** trên phiên bản mới phù hợp.

Đây là lý do nên viết thay đổi theo giá trị hiện tại:

```sql
SET stock = stock - 3
```

thay vì:

```sql
SET stock = 7
```

nếu `7` chỉ là số được tính sẵn từ một `SELECT stock=10` cũ. Trường hợp thứ hai có thể dẫn tới **lost update ở tầng logic ứng dụng** nếu bạn tự tính giá trị cuối bằng dữ liệu đã lỗi thời mà không có guard/concurrency control.

### 7.2. Điều kiện WHERE cũng cần được đánh giá lại

Một lệnh chỉ được phép trừ khi đủ hàng:

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

Nếu trong khi chờ, transaction khác đã giảm kho xuống dưới 3 và commit, điều kiện có thể không còn thỏa khi lệnh UPDATE được tiếp tục, vì vậy kết quả có thể là **`UPDATE 0`** thay vì làm tồn kho âm.

Đây là một quy tắc rất hữu ích để thiết kế **cập nhật có điều kiện** trong một statement; vẫn phải kiểm tra số hàng bị thay đổi, constraint và các nghiệp vụ liên quan.

---

## 8. Thí nghiệm 6 — READ COMMITTED recheck WHERE sau khi chờ

**Mục tiêu:** kiểm chứng điều kiện `stock >= 3` trên phiên bản mới của hàng, không chỉ đọc lời giải thích.

Reset `stock=4`:

```sql
UPDATE mvcc_lab.inventory
SET stock = 4
WHERE sku = 'SKU-A';
```

### Bước 1 — A giảm từ 4 xuống 1 và giữ transaction

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

A nhìn thấy `stock=1`. Chưa commit.

### Bước 2 — B cố giảm 3 theo điều kiện giống nhau

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = stock - 3
WHERE sku = 'SKU-A'
  AND stock >= 3
RETURNING stock;
```

B **chờ A** trên cùng hàng.

### Bước 3 — A COMMIT

**Session A:**

```sql
COMMIT;
```

### Bước 4 — B được tiếp tục nhưng không sửa hàng

**Session B:** quan sát kết quả:

```text
UPDATE 0
```

Lúc này giá trị committed mới là 1, nên điều kiện `stock >= 3` **sai**. B không còn hàng phù hợp để cập nhật.

Kết thúc B:

```sql
COMMIT;
```

Trạng thái cuối:

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Kết quả **1**, không âm.

### 8.1. Điều thí nghiệm chứng minh

- **Một câu SELECT trước đó** và một câu UPDATE sau đó có thể thấy trạng thái khác tại `READ COMMITTED`.
- Lệnh UPDATE đang chờ khóa có thể xét lại điều kiện để không sửa hàng không còn hợp lệ.
- `UPDATE 0` là **kết quả statement thành công nhưng không thay đổi hàng**, không tự đồng nghĩa lỗi kết nối/serialization.
- Nếu cần phân biệt “không còn đủ hàng” với “SKU không tồn tại”, ứng dụng có thể cần logic đọc bổ sung theo một transaction hợp lệ.

### 8.2. Không coi câu WHERE là một bất biến toàn database

`WHERE stock >= 3` kiểm soát phép giảm kho của chính lệnh này. Nếu có code path khác được cấp quyền dùng `UPDATE stock=-5`, hoặc bảng không có `CHECK (stock>=0)`, thì không thể suy rằng mọi giao dịch đều bảo vệ quy tắc kho.

Trong bảng lab, `CHECK (stock>=0)` bổ sung một lớp toàn vẹn dữ liệu. Ràng buộc ở database và điều kiện nguyên tử hỗ trợ nhau.

---

## 9. Thí nghiệm 7 — REPEATABLE READ và concurrent UPDATE có thể báo SQLSTATE 40001

**Mục tiêu:** phân biệt “đọc bản cũ theo snapshot” với “cố ghi trên hàng đã bị transaction khác sửa sau snapshot”.

Reset tồn kho về `10` và đóng transaction cũ.

### Bước 1 — B mở REPEATABLE READ và đọc

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B thấy `10`, snapshot của B được thiết lập.

### Bước 2 — A thay đổi cùng hàng và commit

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

UPDATE mvcc_lab.inventory
SET stock = 8
WHERE sku = 'SKU-A';

COMMIT;
```

A commit `8` thành công.

### Bước 3 — B vẫn đọc theo snapshot cũ

**Session B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B vẫn thấy `10`.

### Bước 4 — B cố UPDATE hàng đã bị đổi sau snapshot

**Session B:**

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
RETURNING stock;
```

Trong kịch bản này, PostgreSQL tại `REPEATABLE READ` sẽ không đơn giản làm tiếp phép tính dựa trên snapshot cũ như ở `READ COMMITTED`. Lệnh có thể thất bại với thông báo:

```text
ERROR: could not serialize access due to concurrent update
SQLSTATE: 40001
```

**Quan trọng:** `40001` cũng có thể xảy ra ở `REPEATABLE READ`, không chỉ ở `SERIALIZABLE`.

### Bước 5 — B rollback và thử lại từ transaction mới

**Session B:**

```sql
ROLLBACK;

BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Lần này B nhìn thấy `8`. Nếu nghiệp vụ còn cho phép giảm 1:

```sql
UPDATE mvcc_lab.inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
  AND stock >= 1
RETURNING stock;

COMMIT;
```

Sau retry hợp lệ, tồn kho thành **7**.

### 9.1. Tại sao không retry riêng UPDATE?

Nếu ứng dụng đã kiểm tra tồn kho hoặc các điều kiện khác từ snapshot cũ, những điều kiện đó **phải được đọc và đánh giá lại** trong transaction mới. Không chỉ chạy lại statement gây lỗi rồi giữ quyết định từ lần thử trước.

Ở `SERIALIZABLE`, PostgreSQL còn có thể báo `40001` vì các phụ thuộc đọc–ghi giữa nhiều transaction ngay cả khi không cùng UPDATE một hàng.

### 9.2. Sau lỗi transaction không thể tiếp tục như bình thường

Nếu tiếp tục chạy SELECT ngay trong transaction đã bị abort, bạn có thể nhận:

```text
ERROR: current transaction is aborted,
       commands ignored until end of transaction block
SQLSTATE: 25P02
```

Đây là **trạng thái lỗi của transaction**, không phải lời giải thích ban đầu. Cần `ROLLBACK` và tìm SQLSTATE gốc, chẳng hạn `40001`.

---

## 10. Thí nghiệm 8 — READ UNCOMMITTED trong PostgreSQL không đọc “dơ”

Tiêu chuẩn SQL có mức `READ UNCOMMITTED`, thường được mô tả là có thể cho phép đọc thay đổi chưa commit trong một số hệ quản trị. Nhưng **PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED`** về các hiện tượng quan sát quan trọng của MVCC.

Reset tồn kho về `10`.

### Bước 1 — A UPDATE nhưng chưa commit

**Session A:**

```sql
BEGIN;

UPDATE mvcc_lab.inventory
SET stock = 3
WHERE sku = 'SKU-A';
```

Giữ A mở.

### Bước 2 — B đặt READ UNCOMMITTED và đọc

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;

SHOW transaction_isolation;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

`SHOW transaction_isolation` có thể hiển thị nhãn `read uncommitted` vì bạn đã yêu cầu mức đó, nhưng **hành vi đọc PostgreSQL vẫn giống `READ COMMITTED`**: B nhìn thấy **10**, không thấy `3` chưa commit.

### Bước 3 — A COMMIT, B đọc lại

**Session A:**

```sql
COMMIT;
```

**Session B:**

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B lúc này nhìn thấy **3**, giống thí nghiệm `READ COMMITTED`: câu SELECT mới lấy snapshot mới.

### 10.1. Bài học từ mức cô lập trên giấy

Không chỉ nhìn tên isolation level rồi suy đoán cách server triển khai. PostgreSQL có các quy tắc đặc thù:

- `READ UNCOMMITTED` hoạt động như `READ COMMITTED`.
- `REPEATABLE READ` không cho phép phantom theo cách snapshot của PostgreSQL, dù bảng phân loại isolation chung đôi khi trình bày khác.
- `SERIALIZABLE` dùng Serializable Snapshot Isolation và có thể từ chối transaction tranh chấp bằng `40001`.

---

## 11. Thí nghiệm 9 — DELETE chưa commit và sự xuất hiện/biến mất của hàng

Thí nghiệm trước thay **giá trị** của hàng. Bây giờ thử xóa nguyên hàng để quan sát tính hiển thị khi hàng có thể bị đánh dấu xóa nhưng transaction chưa commit.

Reset inventory: đảm bảo SKU-A vẫn tồn tại, stock=10, không có transaction mở. Nếu đã chạy các phần trước theo thứ tự và chưa xóa nó, chỉ cần:

```sql
UPDATE mvcc_lab.inventory
SET stock = 10
WHERE sku = 'SKU-A';
```

### 11.1. A xóa nhưng không commit

**Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

DELETE FROM mvcc_lab.inventory
WHERE sku = 'SKU-A'
RETURNING sku, stock;
```

Nếu không còn hàng `inventory_events` tham chiếu SKU-A, lệnh xóa có thể chạy thành công. **Nếu còn event rows từ thí nghiệm 4, FK mặc định sẽ từ chối DELETE.** Trong lab, trước bước này phải chạy **`DELETE FROM mvcc_lab.inventory_events;` khi cả hai phiên đều chưa mở transaction**.

A sẽ không còn thấy hàng SKU-A trong kết quả `SELECT` tiếp theo của chính A:

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Kết quả **0 hàng** trong A.

### 11.2. B vẫn thấy hàng chưa bị xóa committed

**Session B:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

B vẫn nhìn thấy **SKU-A, stock=10** vì thao tác `DELETE` của A chưa commit.

### 11.3. A rollback

**Session A:**

```sql
ROLLBACK;
```

**Session B:**

```sql
SELECT sku, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

COMMIT;
```

B vẫn nhìn thấy SKU-A.

### 11.4. Nếu A COMMIT thay vì ROLLBACK?

Với cùng kịch bản nhưng A `COMMIT`, B ở `READ COMMITTED` sẽ thấy:

- `SELECT` trước commit của A: hàng SKU-A còn hiện diện.
- `SELECT` sau commit của A: **0 hàng**.

Đây là khả năng nhìn thấy của thao tác `DELETE`: một hàng bị xóa chưa commit **không biến mất tức thì khỏi mọi snapshot khác**.

### 11.5. Những ràng buộc nào vẫn hoạt động?

Một thao tác `DELETE` có thể:

- Bị từ chối bởi FK nếu còn hàng con tham chiếu.
- Kích hoạt trigger.
- Phải chờ row locks.
- Dẫn tới `40001` nếu transaction dùng snapshot cũ và gặp concurrent update theo mức cô lập tương ứng.

MVCC giải thích một phần visibility, **không bỏ qua các ràng buộc toàn vẹn dữ liệu**.

---

## 12. Thí nghiệm 10 — Một transaction đọc thấy thay đổi của chính nó

“Snapshot cố định” đôi khi làm người học hiểu nhầm transaction không đọc được những gì nó vừa ghi. PostgreSQL cho phép transaction nhìn thấy thay đổi trước đó **của chính nó** theo quy tắc statement visibility.

Đảm bảo SKU-A tồn tại, reset stock=10, không có transaction mở:

```sql
INSERT INTO mvcc_lab.inventory (sku, stock, description)
VALUES ('SKU-A', 10, 'Sản phẩm thử nghiệm MVCC')
ON CONFLICT (sku) DO UPDATE
SET stock = EXCLUDED.stock;
```

### 12.1. Trong cùng một transaction REPEATABLE READ

**Chạy trong Session A:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

UPDATE mvcc_lab.inventory
SET stock = 9
WHERE sku = 'SKU-A'
RETURNING stock;

SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

ROLLBACK;
```

Kết quả lần lượt:

```text
SELECT lần đầu -> 10
UPDATE RETURNING -> 9
SELECT lần sau -> 9
ROLLBACK       -> bên ngoài transaction vẫn là 10
```

### 12.2. Tại sao không mâu thuẫn với REPEATABLE READ?

Snapshot của transaction kiểm soát cái gì **từ transaction khác** được thấy. Những thay đổi do chính transaction thực hiện trong các statement trước vẫn được xem là một phần trạng thái hợp lệ mà transaction phải đọc được.

Nếu điều này không đúng, một giao dịch sẽ không thể thực hiện:

```text
INSERT order
INSERT order_items trỏ tới order vừa chèn
SELECT order vừa chèn
COMMIT
```

một cách trực quan. MVCC không biến các thay đổi trong transaction thành dữ liệu vô hình đối với chính transaction đó.

### 12.3. Lưu ý một statement có nhiều nhánh thay đổi dữ liệu

Không nên mở rộng ví dụ “statement sau thấy write trước” thành khẳng định mọi subquery/câu lệnh ghi trong **cùng một SQL statement phức tạp** đều nhìn thấy thay đổi của nhau theo thứ tự viết. Trong data-modifying CTE, PostgreSQL có quy tắc snapshot/`RETURNING` đặc biệt. Khi cần chuyển hàng vừa ghi sang logic trong cùng statement, ưu tiên dùng `RETURNING` và đọc tài liệu của loại statement đó.

---

## 13. So sánh các kịch bản visibility bằng bảng tổng hợp

Giả sử ở đầu mỗi kịch bản tồn kho là `10`, A đổi nó thành `7`.

| Thời điểm đọc ở B | `READ COMMITTED` | `REPEATABLE READ` có snapshot từ trước commit |
|---|---|---|
| A chưa commit, B SELECT | 10 | 10 |
| A commit, B SELECT mới trong **cùng** transaction B | **7** | **10** |
| B kết thúc transaction, SELECT trong transaction mới | **7** | **7** |
| B tự UPDATE hàng trong transaction hợp lệ rồi SELECT | Thấy thay đổi của B | Thấy thay đổi của B |
| B UPDATE hàng đã bị A đổi sau snapshot | Có thể chờ/recheck theo ngữ nghĩa `READ COMMITTED` | Có thể gặp **`40001`** |

**Điều kiện của bảng:** B ở `REPEATABLE READ` phải đã đọc và thiết lập snapshot **trước khi A commit**. Nếu B chỉ gõ `BEGIN REPEATABLE READ` nhưng chưa thực hiện câu lệnh nào cần snapshot cho tới sau khi A commit, nó có thể thấy dữ liệu đã commit của A ngay từ câu đọc đầu.

### 13.1. Một timeline trực quan

```text
Thời gian ─────────────────────────────────────────────►

Session A:
  BEGIN ── UPDATE stock=7 ─────── COMMIT
                  |                  |
                  |                  +── phiên bản mới committed
                  +── phiên bản mới uncommitted

Session B / READ COMMITTED:
          SELECT -> 10                 SELECT -> 7
          snapshot B1                  snapshot B2

Session B / REPEATABLE READ:
          SELECT -> 10                 SELECT -> 10
          snapshot BRR                 cùng snapshot BRR
                                                   COMMIT
                                                       |
                                                       v
                                                  SELECT -> 7
                                                  snapshot mới
```

### 13.2. Tại sao dùng cụm “có thể” khi nói về UPDATE?

Một `UPDATE` đang cạnh tranh phụ thuộc vào việc hàng có thay đổi, transaction kia commit/rollback, mức cô lập và predicate hiện tại. Chẳng hạn:

- Có transaction khác đang giữ row lock: có thể **chờ**.
- Transaction kia rollback: phiên khác có thể tiếp tục từ trạng thái trước update.
- Transaction kia commit: `READ COMMITTED` có thể **recheck** hàng sau update.
- Snapshot `REPEATABLE READ` cũ gặp hàng đã thay đổi: có thể **bị từ chối bằng 40001**.
- Nếu `NOWAIT`/`lock_timeout` được cấu hình trong tình huống liên quan, hành vi chờ có thể chuyển thành lỗi khác.

Đừng viết test giả định mọi lịch đồng thời đều tạo đúng một kiểu exception mà không khống chế thứ tự các bước.

---

## 14. Xem dấu vết tuple version: xmin, xmax và ctid

PostgreSQL cho phép đọc một số **system columns** của hàng:

- `xmin`: ID của transaction đã chèn phiên bản hàng.
- `xmax`: trường hệ thống liên quan đến transaction xóa/khóa tuple, nhưng **không thể suy trực tiếp “hàng bị xóa” chỉ từ xmax khác 0**.
- `ctid`: vị trí vật lý hiện tại của phiên bản tuple trong bảng.

### 14.1. Đọc thông tin của hàng

```sql
SELECT
    sku,
    stock,
    xmin,
    xmax,
    ctid
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

Ví dụ đầu ra có thể trông như:

```text
sku   | stock | xmin | xmax | ctid
------+-------+------+------+-------
SKU-A | 10    | 8452 | 0    | (0,7)
```

**Các số trong bảng chỉ minh họa**, không phải kết quả cần khớp trên máy bạn.

### 14.2. Quan sát trước và sau UPDATE

Khi mọi transaction khác đã kết thúc:

```sql
BEGIN;

SELECT xmin, xmax, ctid, stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';

UPDATE mvcc_lab.inventory
SET stock = stock + 1
WHERE sku = 'SKU-A'
RETURNING xmin, xmax, ctid, stock;

ROLLBACK;
```

`UPDATE RETURNING` cho phép quan sát tuple version đang được chính transaction tạo/sử dụng. Các giá trị `xmin` và `ctid` có thể khác so với phiên bản trước, phản ánh việc thay đổi phiên bản hàng theo cơ chế MVCC.

### 14.3. Giới hạn rất quan trọng khi đọc system columns

**Không** dùng riêng `xmin`, `xmax` hoặc `ctid` như:

- Một khóa chính nghiệp vụ.
- Một ID lịch sử ổn định qua `VACUUM FULL`/rewrites hoặc thay đổi vật lý.
- Bằng chứng chắc chắn transaction đã commit chỉ vì có `xmin`.
- Cách xác định một hàng đã bị xóa chỉ vì `xmax <> 0`.
- Một nguồn version history lâu dài thay cho audit.

`xmax` có thể phản ánh row locking/MultiXact và những trạng thái nội bộ khác. `ctid` có thể đổi khi hàng được cập nhật hoặc bảng được viết lại. Transaction IDs còn có cơ chế wraparound và freeze. Những trường này hữu ích để **học và chẩn đoán**, không phải cơ chế duy nhất để quyết định hành động nghiệp vụ.

### 14.4. Tại sao không bắt buộc phải dùng xmin để hiểu MVCC?

Thí nghiệm thực dụng có thể chứng minh phần quan trọng bằng chính **giá trị SELECT trả về**, thời điểm `COMMIT` và isolation. System columns chỉ cung cấp góc nhìn bổ sung về phiên bản; người học không cần suy đoán các bit trạng thái tuple từ SQL để hiểu điều gì được nhìn thấy.

---

## 15. Session, transaction và snapshot trong psql

### 15.1. Session không đồng nghĩa transaction

Một **session/connection** có thể chạy nhiều transaction liên tiếp:

```sql
BEGIN;
SELECT ...;
COMMIT;

BEGIN;
SELECT ...;
ROLLBACK;
```

Cùng một `pg_backend_pid()` không có nghĩa những câu ở hai transaction liên tiếp dùng cùng snapshot. Ranh giới transaction là một trong những yếu tố quyết định visibility.

### 15.2. Autocommit của psql

Trong cấu hình thường gặp, khi bạn chạy:

```sql
SELECT stock
FROM mvcc_lab.inventory
WHERE sku = 'SKU-A';
```

mà **không viết `BEGIN`**, client/server thực thi statement trong một transaction ngầm tương ứng và hoàn tất nó. Vì vậy hai lần gõ `SELECT` độc lập có thể thấy snapshot khác nhau.

Khi cần giữ snapshot qua nhiều câu để quan sát `REPEATABLE READ`, phải dùng `BEGIN`/`COMMIT` thật sự và không để IDE tự tách chúng thành transaction riêng.

### 15.3. Xem isolation trong transaction

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SHOW transaction_isolation;

ROLLBACK;
```

Ở ví dụ này, kết quả là `repeatable read`. Thực hiện `SHOW` để kiểm tra setting, nhưng **thứ tự thực thi truy vấn dữ liệu** mới quyết định snapshot thí nghiệm được thiết lập trước hay sau commit của A.

### 15.4. Đặt isolation trước khi chạy truy vấn nghiệp vụ

Có thể dùng:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT ...

COMMIT;
```

`SET TRANSACTION` cần được đặt **trước các câu lệnh truy vấn/sửa dữ liệu** liên quan trong transaction theo quy định PostgreSQL; đừng thử đổi isolation giữa chừng rồi coi các câu đã đọc được đánh giá lại.

### 15.5. Vì sao now() không chứng minh snapshot mới?

Trong PostgreSQL, `now()`/`CURRENT_TIMESTAMP` phản ánh **thời điểm bắt đầu transaction** theo ngữ nghĩa của hàm, còn `clock_timestamp()` trả thời gian đồng hồ tại lúc gọi.

```sql
BEGIN;

SELECT now() AS transaction_time,
       clock_timestamp() AS wall_clock_time;

-- Thử lại sau một khoảng thời gian thao tác trong cùng transaction.
SELECT now() AS transaction_time,
       clock_timestamp() AS wall_clock_time;

ROLLBACK;
```

`now()` có thể giữ nguyên, còn `clock_timestamp()` thay đổi. Nhưng **không** đồng nhất giá trị `now()` hoặc `clock_timestamp()` với “ID snapshot MVCC”. Timestamp của hàm và tập transaction được nhìn thấy là hai thông tin khác nhau.

---

## 16. Quan sát phiên đang giữ transaction và khóa

### 16.1. pg_stat_activity

Trong một phiên quan sát riêng, nếu có đủ quyền, có thể xem:

```sql
SELECT
    pid,
    application_name,
    state,
    xact_start,
    query_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY application_name;
```

Những trường hữu ích:

- `pid`: backend process của session.
- `state`: ví dụ `active`, `idle`, `idle in transaction`.
- `xact_start`: thời điểm bắt đầu transaction hiện tại nếu đang có.
- `wait_event_type` / `wait_event`: hỗ trợ thấy phiên có đang chờ sự kiện/khóa nào không.

**Lưu ý quyền:** Một role có thể không nhìn thấy đầy đủ chi tiết phiên khác. Dùng quyền monitoring phù hợp; không cố thu thập nội dung query nhạy cảm nếu không được phép.

### 16.2. Xem ai chặn ai

Khi B bị chờ ở thí nghiệm UPDATE cùng hàng, từ một phiên quan sát khác có thể dùng:

```sql
SELECT
    pid,
    application_name,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
  AND application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY application_name;
```

`pg_blocking_pids(pid)` giúp xác định PID đang chặn phiên được xét trong những tình huống lock. Kết quả phụ thuộc lịch chạy và loại chờ; nếu A đã commit trước khi quan sát, có thể không còn chặn nào.

### 16.3. pg_locks và loại khóa

```sql
SELECT
    l.pid,
    a.application_name,
    l.locktype,
    l.mode,
    l.granted,
    l.relation::regclass AS relation_name
FROM pg_locks AS l
LEFT JOIN pg_stat_activity AS a ON a.pid = l.pid
WHERE a.application_name IN ('mvcc-lab-A', 'mvcc-lab-B')
ORDER BY a.application_name, l.locktype, l.mode;
```

PostgreSQL sử dụng nhiều loại khóa nội bộ; một wait vào row update không nhất thiết hiển thị đúng như suy đoán ban đầu ở `pg_locks`, vì có thể liên quan chờ transaction ID. Để trả lời “ai đang chặn ai”, `pg_blocking_pids` thường trực quan hơn.

### 16.4. Idle in transaction là một tín hiệu vận hành

Một transaction mở lâu có thể giữ snapshot cũ và làm chậm việc dọn tuple versions mà hệ thống còn phải bảo toàn cho snapshot đó. Vì vậy:

- Không để hai session lab ở `idle in transaction` rồi bỏ quên.
- Kết thúc mọi transaction ở cuối kịch bản.
- Trong ứng dụng, giữ transaction ngắn, không chờ người dùng/HTTP request khi transaction còn mở.
- Dùng giám sát và timeout phù hợp theo chính sách hệ thống.

Không kill backend khác chỉ vì thấy transaction lâu; trước tiên phải hiểu nó đang làm gì và các hậu quả của việc hủy.

---

## 17. MVCC, VACUUM và phiên bản hàng đã hết hiệu lực

Nếu `UPDATE` thường tạo ra phiên bản tuple mới, các phiên bản cũ không thể tồn tại mãi không có giới hạn. PostgreSQL dùng **VACUUM/autovacuum** để thu hồi hoặc đánh dấu vùng lưu trữ có thể tái sử dụng khi không còn snapshot cần những phiên bản đó.

### 17.1. Sơ đồ vòng đời khái quát

```text
INSERT version V1
        |
      COMMIT
        |
      UPDATE
        |
        +--- V1 có thể cần cho snapshot cũ
        |
        +--- V2 mới được tạo
                  |
                COMMIT
                  |
        snapshot cũ lần lượt kết thúc
                  |
          VACUUM có thể thu hồi
          version không còn cần thiết
```

### 17.2. Transaction dài ảnh hưởng việc dọn dẹp

Một session ở `REPEATABLE READ` mở lâu có thể tiếp tục cần đọc phiên bản đã bị thay thế trong khi transaction khác cập nhật bảng. Để giữ khả năng nhìn thấy nhất quán, PostgreSQL có thể phải duy trì phiên bản cũ lâu hơn.

Điều này có thể ảnh hưởng:

- Số lượng dead tuples và table/index bloat.
- Công việc của autovacuum.
- Khối lượng I/O và tính hiệu quả cache.
- Hiệu năng truy vấn trong workload cập nhật nhiều.

Không kết luận một thí nghiệm nhỏ luôn làm bloat đáng kể, nhưng đó là lý do quan trọng để không giữ transaction mở trong môi trường thật.

### 17.3. Thống kê dead tuples chỉ là ước lượng

```sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
ORDER BY relname;
```

`n_dead_tup` là **thống kê/ước lượng**, không phải bảng liệt kê mọi phiên bản chết ngay tức khắc. Số liệu có độ trễ và phụ thuộc cơ chế thống kê.

### 17.4. VACUUM không làm snapshot cũ đọc nhầm dữ liệu mới

PostgreSQL phải giữ những phiên bản còn cần thiết theo quy tắc MVCC. Vacuum không được tự ý phá tính đúng đắn của một transaction còn hợp lệ.

`VACUUM` thường có thể chạy đồng thời với hoạt động thông thường, nhưng không nên thử ép dọn dữ liệu bằng các thao tác bảo trì mạnh khi đang làm lab đồng thời. Các lệnh như `VACUUM FULL` có khác biệt về lock và viết lại bảng, không cần cho bài này.

---

## 18. Từ hai phiên psql sang hai connection JDBC

Về bản chất, “Session A và Session B” tương ứng với **hai connection database khác nhau**. Trong Java, mỗi connection quản lý transaction độc lập.

### 18.1. Ví dụ mở hai connection

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public class MvccConnections {
    public static void showSessionIds(DataSource dataSource)
            throws SQLException {
        try (Connection a = dataSource.getConnection();
             Connection b = dataSource.getConnection()) {

            System.out.println("A PID = " + backendPid(a));
            System.out.println("B PID = " + backendPid(b));
        }
    }

    private static int backendPid(Connection connection)
            throws SQLException {
        try (PreparedStatement ps =
                 connection.prepareStatement(
                     "SELECT pg_backend_pid()"
                 );
             ResultSet rs = ps.executeQuery()) {
            rs.next();
            return rs.getInt(1);
        }
    }
}
```

Hai `Connection` được mở cùng lúc từ pool thường tương ứng hai PostgreSQL backend khác nhau, nhưng cần kiểm tra thực tế PID/driver/proxy trong môi trường ứng dụng. Không dùng cùng một JDBC connection đồng thời từ hai thread rồi gọi đó là hai session độc lập.

### 18.2. Thiết lập isolation và tắt autocommit

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setTransactionIsolation(
        Connection.TRANSACTION_REPEATABLE_READ
    );
    conn.setAutoCommit(false);

    try {
        // SELECT và UPDATE trong cùng transaction.
        conn.commit();
    } catch (SQLException e) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
```

Đặt isolation và transaction boundary trước các câu lệnh nghiệp vụ. Khi dùng framework quản lý transaction, phải tuân thủ quy tắc của framework thay vì tự `commit` một connection do framework sở hữu.

### 18.3. Đọc tồn kho bằng PreparedStatement

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public static int readStock(Connection conn, String sku)
        throws SQLException {
    String sql = """
        SELECT stock
        FROM mvcc_lab.inventory
        WHERE sku = ?
        """;
    try (PreparedStatement ps =
             conn.prepareStatement(sql)) {
        ps.setString(1, sku);
        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                throw new SQLException(
                    "Không có SKU: " + sku
                );
            }
            return rs.getInt("stock");
        }
    }
}
```

Đoạn code là phương thức minh họa có thể đặt bên trong một class Java; nó dùng text blocks (Java 15+). Đầu vào SKU được **bind parameter**, không nối trực tiếp vào SQL.

### 18.4. Đồng bộ hai connection trong integration test

Trong bài kiểm thử Java có thể dùng `CountDownLatch` hoặc `CyclicBarrier`:

```text
Thread A / Connection A:
    BEGIN
    UPDATE stock=7
    signal("A has updated but not committed")
    await("B has read old value")
    COMMIT

Thread B / Connection B:
    BEGIN READ COMMITTED
    await("A has updated but not committed")
    SELECT stock -> expect 10
    signal("B has read old value")
    await("A committed")
    SELECT stock -> expect 7
    COMMIT
```

Đây là **pseudocode điều phối**, không phải chương trình đầy đủ. Test thực phải có timeout cho các barrier, xử lý ngoại lệ ở cả hai thread, rollback/close trong `finally` và không giữ kết nối chờ vô hạn.

### 18.5. Không nhầm transaction của framework với request

Một HTTP request không mặc nhiên tương ứng một PostgreSQL transaction. Một service có thể mở nhiều connection hoặc transaction riêng; framework có thể tự commit trước khi response trả về. Khi cần quan sát visibility, hãy xác định **transaction thực sự bắt đầu/kết thúc ở đâu**, không chỉ tên phương thức Java.

---

## 19. Những nhầm lẫn thường gặp trong thí nghiệm hai phiên

**1. “A UPDATE thì B lập tức thấy giá trị mới.”** Sai nếu A chưa commit. Snapshot B không đọc dữ liệu chưa commit.

**2. “READ COMMITTED chụp snapshot đúng một lần khi BEGIN.”** Sai. Các statement thông thường lấy snapshot mới.

**3. “REPEATABLE READ luôn lấy snapshot ngay tại chữ BEGIN.”** Không hẳn; snapshot được thiết lập khi statement cần snapshot đầu tiên chạy theo quy tắc mức cô lập.

**4. “Một transaction REPEATABLE READ không thấy thay đổi do chính nó tạo.”** Sai. Nó có thể thấy chính các write đã thực hiện trước đó.

**5. “Hai lần SELECT dưới READ COMMITTED luôn trả cùng số.”** Sai nếu có transaction khác commit giữa hai statement.

**6. “READ UNCOMMITTED trong PostgreSQL cho dirty read.”** Sai. PostgreSQL xử lý mức này tương đương READ COMMITTED.

**7. “Một phiên SELECT không chờ UPDATE của phiên khác nên UPDATE của nó cũng không chờ.”** Sai. Đọc thường và ghi cạnh tranh dùng quy tắc khác.

**8. “B UPDATE sẽ chắc chắn dùng stock=10 mà B SELECT trước đó nhìn thấy.”** Không. Ở READ COMMITTED, UPDATE có thể xử lý phiên bản mới sau khi chờ và recheck điều kiện.

**9. “UPDATE 0 nghĩa là transaction bị rollback.”** Không. Đó có thể là statement thành công nhưng không còn hàng thỏa WHERE.

**10. “REPEATABLE READ có thể UPDATE bất kỳ hàng nào dù bị thay đổi sau snapshot.”** Không. Có thể gặp `40001` do concurrent update.

**11. “SQLSTATE 40001 chỉ xảy ra ở SERIALIZABLE.”** Sai. REPEATABLE READ cũng có thể phát sinh.

**12. “Gặp 40001 chỉ cần retry câu UPDATE cuối.”** Sai. Logic đọc/quyết định trong transaction mới có thể thay đổi.

**13. “Một window trong IDE chắc chắn tương ứng một connection.”** Không. Cần kiểm tra PID hoặc cấu hình session.

**14. “Có hai tab giao diện nghĩa là có hai phiên PostgreSQL.”** Không nếu chúng dùng chung connection.

**15. “BEGIN ở READ COMMITTED giữ nguyên mọi dữ liệu cho đến COMMIT.”** Không. Mỗi statement có snapshot riêng.

**16. “Trong REPEATABLE READ, commit của A bị chặn vì B đang SELECT thường.”** Không. SELECT thường không tự giữ row lock ngăn mọi UPDATE; có thể đọc phiên bản cũ.

**17. “Thấy xmax khác 0 nghĩa là hàng chắc chắn đã bị xóa.”** Không. xmax có thể dùng cho row locks/MultiXact và nhiều ngữ nghĩa nội bộ.

**18. “ctid là ID cố định của hàng.”** Sai. Nó là vị trí tuple vật lý có thể thay đổi.

**19. “xmin đủ thay audit log.”** Không. Không lưu được đầy đủ ai đổi gì/vì sao và không ổn định như định danh nghiệp vụ.

**20. “VACUUM phải giữ mọi phiên bản hàng mãi để hỗ trợ MVCC.”** Không. Chỉ giữ những phiên bản còn cần thiết theo quy tắc; các phiên bản chết có thể được thu hồi.

**21. “Cứ mở transaction REPEATABLE READ suốt ngày để được dữ liệu nhất quán.”** Không phù hợp vận hành; transaction dài có thể gây áp lực dọn tuple và tài nguyên.

**22. “Một SELECT COUNT ở snapshot cũ luôn chứng minh dữ liệu hiện tại của toàn database.”** Không. Nó chỉ nói về tập hàng visible với snapshot của câu/transaction đó.

**23. “Có FK thì DELETE của A luôn thành công trong lab.”** Không. Bảng events tham chiếu inventory có thể chặn xóa cha khi còn hàng con.

**24. “READ COMMITTED tự bảo đảm mọi invariant nhiều hàng.”** Không. Có thể cần constraint, row locks, transaction logic hoặc SERIALIZABLE.

**25. “READ ONLY transaction chắc chắn không thể làm tăng tải MVCC.”** Không. Snapshot đọc dài có thể ảnh hưởng việc dọn phiên bản cũ.

**26. “SHOW transaction_isolation bằng read uncommitted chứng minh có dirty read.”** Không. Đây là setting được yêu cầu; hành vi PostgreSQL như READ COMMITTED.

**27. “Giá trị now() đổi nghĩa là snapshot mới.”** Không. Các hàm thời gian và snapshot không đồng nhất.

**28. “COMMIT của B rồi SELECT tiếp vẫn dùng snapshot của B trước đó.”** Không. Câu SELECT mới là transaction mới khi autocommit thông thường.

**29. “Một test chạy hai khối SQL tuần tự cũng là test concurrency.”** Không. Cần hai connection và thứ tự xen kẽ.

**30. “Thí nghiệm thành công trên bảng nhỏ có nghĩa production không bao giờ deadlock/serialize fail.”** Không. Khối lượng, thời gian và lịch truy cập quyết định tranh chấp.

---

## 20. Bài tập thực hành có đáp án

### Bài 1 — Dirty read

Phiên A đã `UPDATE stock=7` nhưng chưa commit. Phiên B `READ COMMITTED` đọc gì nếu giá trị đã commit trước đó là 10?

**Đáp án:** B đọc **10**, vì không thấy thay đổi chưa commit của A.

### Bài 2 — Chính transaction có thấy update của nó?

Phiên A vừa `UPDATE stock=7` và SELECT lại trước COMMIT.

**Đáp án:** A đọc được **7** theo quy tắc self-visibility.

### Bài 3 — A rollback

A chưa commit giá trị 7 rồi `ROLLBACK`. B đọc lại dưới READ COMMITTED.

**Đáp án:** B vẫn đọc **10** nếu không có transaction khác làm thay đổi hàng đó.

### Bài 4 — Non-repeatable read

B `BEGIN READ COMMITTED`, SELECT stock=10. A UPDATE stock=6 rồi COMMIT. B SELECT lần nữa trong cùng transaction.

**Đáp án:** B thấy **6** ở lần thứ hai. READ COMMITTED có snapshot mới cho từng SELECT thông thường.

### Bài 5 — REPEATABLE READ

Cùng kịch bản bài 4, nhưng B dùng REPEATABLE READ và đã SELECT lần đầu trước khi A commit.

**Đáp án:** Lần đọc thứ hai của B vẫn là **10**. B chỉ thấy **6** trong transaction mới sau khi kết thúc transaction cũ.

### Bài 6 — Snapshot bắt đầu khi nào?

B gõ `BEGIN REPEATABLE READ`, **chưa SELECT**, A commit update, sau đó B mới SELECT đầu tiên.

**Đáp án:** B có thể thấy giá trị mới do A đã commit, vì snapshot dùng cho transaction REPEATABLE READ được lấy khi câu lệnh đầu tiên cần snapshot chạy, không nhất thiết đúng thời điểm gõ BEGIN.

### Bài 7 — Phantom ở READ COMMITTED

B đếm sự kiện của SKU-A được 0. A INSERT một sự kiện SKU-A và COMMIT. B đếm lại trong cùng transaction READ COMMITTED.

**Đáp án:** B có thể thấy **1** hàng; đây là ví dụ phantom read.

### Bài 8 — Phantom ở REPEATABLE READ

B đếm được 0 trước khi A INSERT + COMMIT. B đếm lại trong transaction REPEATABLE READ.

**Đáp án:** B vẫn thấy **0** với snapshot cũ; transaction mới sẽ thấy hàng mới đã commit.

### Bài 9 — UPDATE vs SELECT

Tại sao B SELECT vẫn đọc 10 khi A đang UPDATE chưa commit, nhưng B UPDATE cùng hàng lại chờ?

**Đáp án:** SELECT thường có thể đọc phiên bản hàng cũ phù hợp snapshot, còn UPDATE cần phối hợp row locks để tránh hai thao tác ghi cùng hàng không nhất quán.

### Bài 10 — Recheck WHERE

Tồn kho ban đầu 4. A giảm 3 nhưng chưa commit; B cố giảm 3 với `WHERE stock >= 3`. A commit, B tiếp tục.

**Đáp án:** B có thể nhận `UPDATE 0`, vì tồn kho committed mới chỉ còn 1 và không đủ điều kiện giảm thêm.

### Bài 11 — REPEATABLE READ concurrent update

B đã chụp snapshot stock=10. A đổi thành 8 và commit. B UPDATE hàng cùng SKU trong transaction REPEATABLE READ.

**Đáp án:** B có thể nhận `SQLSTATE 40001` (concurrent update). Phải rollback, mở transaction mới và đánh giá lại quyết định.

### Bài 12 — READ UNCOMMITTED

B dùng `BEGIN ISOLATION LEVEL READ UNCOMMITTED` trong PostgreSQL. A chưa commit stock=3.

**Đáp án:** B **không** nhìn thấy 3; PostgreSQL xử lý hành vi của mức này như READ COMMITTED.

### Bài 13 — Trạng thái transaction sau lỗi

B gặp `40001`, sau đó SELECT tiếp bị `25P02`.

**Đáp án:** Transaction đã abort; `25P02` là hậu quả. Cần rollback và xem lỗi gốc `40001`.

### Bài 14 — DELETE chưa commit

A DELETE SKU-A nhưng chưa commit, B SELECT thông thường trong READ COMMITTED.

**Đáp án:** B vẫn có thể thấy SKU-A từ phiên bản committed phù hợp snapshot, với điều kiện A được phép DELETE (không vướng FK/trigger).

### Bài 15 — xmin và xmax

Nếu `xmax` khác 0, có thể kết luận hàng đã bị xóa committed không?

**Đáp án:** Không. xmax có thể phản ánh thông tin khóa/Multixact và trạng thái nội bộ. Không dùng làm bằng chứng duy nhất về xóa committed.

### Bài 16 — ctid

Có thể lưu `ctid` làm mã sản phẩm ổn định không?

**Đáp án:** Không. ctid là vị trí vật lý của tuple version, có thể đổi khi UPDATE hoặc rewrite; dùng khóa nghiệp vụ như `sku`.

### Bài 17 — Isolation qua JDBC

**Yêu cầu:** đặt một JDBC connection ở REPEATABLE READ.

**Đáp án:**

```java
conn.setTransactionIsolation(
    Connection.TRANSACTION_REPEATABLE_READ
);
conn.setAutoCommit(false);
```

Đặt trước câu lệnh nghiệp vụ và kết thúc bằng commit/rollback.

### Bài 18 — Hai tab có phải hai session?

**Đáp án:** Không chắc. Chạy `SELECT pg_backend_pid();` trong mỗi tab. Nếu cùng backend PID trong cùng thời điểm, chúng không phải hai connection PostgreSQL độc lập cần cho bài lab.

### Bài 19 — Giám sát phiên chờ

**Yêu cầu:** xác định phiên đang chặn phiên khác.

**Đáp án gợi ý:**

```sql
SELECT
    pid,
    application_name,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database();
```

Kết quả phụ thuộc quyền giám sát và việc tình huống chờ vẫn đang diễn ra.

### Bài 20 — Vì sao không để transaction lab mở cả giờ?

**Đáp án:** Transaction dài có thể giữ snapshot cũ và làm chậm việc thu hồi tuple versions cần thiết, tăng áp lực lên autovacuum/bloat/tài nguyên. Kết thúc transaction ngay sau thí nghiệm.

### Bài 21 — Phân biệt thời gian và snapshot

Trong transaction dài, `now()` không đổi giữa các câu SELECT, còn `clock_timestamp()` tăng.

**Đáp án:** `now()` gắn với thời điểm bắt đầu transaction; clock_timestamp phản ánh đồng hồ tại thời điểm gọi. Không suy ra snapshot MVCC mới/cũ trực tiếp từ hai giá trị đó.

### Bài 22 — Có thể giữ read snapshot cũ nhưng vẫn viết không?

**Đáp án:** Tùy hàng được ghi và mức cô lập. Một transaction REPEATABLE READ có thể ghi những hàng không xung đột, nhưng nếu cố cập nhật hàng bị thay đổi sau snapshot có thể gặp `40001`. Đọc ổn định không đồng nghĩa mọi write sẽ luôn thành công.

### Bài 23 — Serializable có luôn trả 40001?

**Đáp án:** Không. Transaction SERIALIZABLE có thể commit bình thường nếu lịch đồng thời hợp lệ; `40001` chỉ xuất hiện khi PostgreSQL cần từ chối một giao dịch để giữ bảo đảm serialization.

### Bài 24 — Một câu SELECT chạy ở đâu?

Ứng dụng lần đầu đọc stock trong transaction 1, đóng transaction, sau đó đọc lại trong transaction 2.

**Đáp án:** Hai transaction độc lập có thể có snapshot khác nhau dù dùng cùng connection/session. Đừng nhầm connection identity với transaction snapshot identity.

---

## 21. Checklist tổ chức một buổi lab MVCC hai phiên

### Trước khi thử

1. **Có database thử nghiệm:** không dùng bảng đang chứa dữ liệu sản xuất.
2. **Hai connection độc lập:** kiểm tra `pg_backend_pid()`.
3. **Cùng một database:** tránh nhầm A và B kết nối hai database khác nhau.
4. **Schema riêng:** `mvcc_lab`, tránh tác động bảng người khác.
5. **Dữ liệu ban đầu rõ ràng:** `SKU-A stock=10`, số event đã biết.
6. **Không còn transaction cũ:** kết thúc A và B trước khi reset.
7. **Isolation có chủ đích:** khai báo trong `BEGIN`.
8. **Quy tắc autocommit rõ:** IDE/psql không tự tách transaction muốn giữ mở.

### Khi thử

9. **Chạy đan xen đúng thứ tự:** A giữ transaction thì chuyển qua B.
10. **Ghi lại giá trị và thời điểm COMMIT:** không chỉ chụp câu SQL.
11. **Phân biệt SELECT với UPDATE:** một bên đọc version cũ, một bên có thể chờ khóa.
12. **Đoán trước kết quả:** so dự đoán dirty read, non-repeatable read, phantom.
13. **Nếu B đang chờ:** quay sang A để kết thúc transaction, không mở thêm nhiều transaction khác vô cớ.
14. **Nếu có 40001:** rollback và làm lại quyết định trong transaction mới.
15. **Nếu có 25P02:** tìm lỗi đầu tiên, rollback trước khi thử tiếp.
16. **Nếu DELETE bị FK chặn:** dọn event rows trong lab trước, không tự tắt mọi ràng buộc.
17. **Không dựa vào thứ tự trả hàng khi thiếu ORDER BY.**

### Sau khi thử

18. **COMMIT/ROLLBACK tất cả phiên:** không để idle in transaction.
19. **Reset dữ liệu trước kịch bản mới:** tránh thí nghiệm trước gây kết quả sai.
20. **Ghi nhận isolation và snapshot timing:** đặc biệt với REPEATABLE READ.
21. **Không coi xmin/xmax/ctid là dữ liệu nghiệp vụ:** chỉ dùng học/quan sát.
22. **Phân biệt transaction mới và session cũ:** một session chạy nhiều transaction.
23. **Không giả định một test là bằng chứng mọi lịch đồng thời:** cần nhiều test và điều kiện xung đột có kiểm soát.
24. **Giải phóng tài nguyên:** đóng terminal/connection khi hoàn thành.

---

## 22. Tóm tắt theo bốn quy tắc nhớ lâu

**Quy tắc 1 — Chưa COMMIT thì phiên khác không đọc thấy.** Một transaction có thể đọc lại những gì **nó tự vừa ghi**, nhưng các transaction khác không đọc dirty data qua `SELECT` bình thường trong PostgreSQL.

**Quy tắc 2 — Isolation quyết định snapshot.** `READ COMMITTED` thường có snapshot **mỗi statement**, nên cùng transaction đọc hai lần có thể thấy giá trị khác. `REPEATABLE READ` dùng snapshot ổn định cho các lần đọc thông thường, nên dữ liệu A commit sau snapshot của B chưa xuất hiện trong B cho tới transaction mới.

**Quy tắc 3 — Đọc và ghi có hành vi cạnh tranh khác nhau.** B có thể đọc phiên bản cũ trong khi A giữ khóa, nhưng khi B `UPDATE` cùng hàng nó có thể phải **chờ**, **recheck WHERE** hoặc nhận **`40001`**, tùy isolation và lịch ghi.

**Quy tắc 4 — MVCC là cơ chế nhìn thấy dữ liệu, không phải toàn bộ luật nghiệp vụ.** MVCC cùng isolation hỗ trợ tính nhất quán, nhưng vẫn cần ràng buộc, transaction boundary, xử lý retry, khóa thích hợp và các phép kiểm tra nghiệp vụ để bảo vệ dữ liệu.

Nếu chỉ nhớ một thử nghiệm, hãy nhớ timeline:

```text
A: UPDATE 10 -> 7 (chưa COMMIT)
B: SELECT -> 10
A: COMMIT

B/READ COMMITTED:  SELECT lần hai -> 7
B/REPEATABLE READ: SELECT lần hai -> 10

B kết thúc transaction và đọc mới -> 7
```

Đó là bức tranh căn bản về việc **cùng một hàng có thể được quan sát khác nhau theo snapshot và ranh giới giao dịch** trong PostgreSQL.

### Tài liệu PostgreSQL chính thức

- [Introduction to MVCC](https://www.postgresql.org/docs/current/mvcc-intro.html).
- [Transaction Isolation](https://www.postgresql.org/docs/current/transaction-iso.html).
- [Transaction ID and Snapshot Semantics](https://www.postgresql.org/docs/current/functions-info.html).
- [System Columns: xmin, xmax, ctid](https://www.postgresql.org/docs/current/ddl-system-columns.html).
- [Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html).
- [Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html).
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html).
