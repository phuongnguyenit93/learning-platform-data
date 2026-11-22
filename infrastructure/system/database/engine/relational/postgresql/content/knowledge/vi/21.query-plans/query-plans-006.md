# Index-only scan và số lần phải đọc heap trong PostgreSQL

## 1. Vì sao tên “Index Only Scan” có thể gây hiểu lầm?

Hãy xét truy vấn tìm các đơn hàng gần nhất của một cửa hàng:

```sql
SELECT sale_id, sold_at, amount_cents
FROM sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Nếu đã có một B-tree index chứa toàn bộ cột cần tìm, lọc, sắp xếp và trả kết quả, ta có thể kỳ vọng PostgreSQL đọc **chỉ index** mà không cần tìm từng hàng trong bảng.

PostgreSQL có một node thực thi mang tên **`Index Only Scan`** để thực hiện ý tưởng đó. Tuy nhiên, PostgreSQL dùng cơ chế **MVCC (Multi-Version Concurrency Control)**. Một mục trong B-tree không tự chứng minh phiên bản hàng tương ứng có được phép nhìn thấy theo snapshot của transaction đang đọc hay không.

Vì vậy, một kế hoạch mang tên `Index Only Scan` **vẫn có thể đọc heap**. Trong `EXPLAIN (ANALYZE, BUFFERS)`, số lần phải tra heap thường thể hiện qua:

```text
Heap Fetches: N
```

Hai trường hợp minh họa:

```text
Index Only Scan ...
  Heap Fetches: 0

Index Only Scan ...
  Heap Fetches: 187
```

Cả hai đều là `Index Only Scan`. Khác biệt là ở thời điểm thực thi, PostgreSQL có thể bỏ qua việc kiểm tra heap cho bao nhiêu mục index nhờ **visibility map**.

**Thông điệp trọng tâm của bài:** Có đủ cột trong index là điều kiện cần để tránh đọc dữ liệu hàng, nhưng **visibility của heap page** mới quyết định có thể bỏ qua heap trong từng lần kiểm tra hay không.

### Mục tiêu học tập

Sau bài, bạn sẽ:

1. Phân biệt `Index Scan`, `Index Only Scan`, `Bitmap Heap Scan` và `Seq Scan`.
2. Biết điều kiện để planner có thể cân nhắc Index Only Scan.
3. Hiểu một **covering index** và vai trò của `INCLUDE`.
4. Giải thích vì sao index không lưu trực tiếp toàn bộ thông tin MVCC cần thiết.
5. Hiểu **visibility map (VM)**, bit *all-visible* và bit *all-frozen*.
6. Đọc đúng `Heap Fetches`, `Buffers`, `Index Cond` và `actual rows`.
7. Thực hành quan sát thay đổi sau `INSERT`, `VACUUM` và `UPDATE`.
8. Hiểu vì sao một UPDATE không thay đổi cột khóa index vẫn có thể làm tăng Heap Fetches.
9. Đánh giá hiệu quả theo tỷ lệ trang all-visible, số hàng, heap I/O và chi phí index.
10. Biết những giới hạn của expression index, partial index, index `INCLUDE`, MVCC và query planner.
11. Áp dụng hiểu biết khi tối ưu các truy vấn Java/JDBC và hệ thống thực tế.

---

## 2. Bốn con đường đọc dữ liệu quen thuộc

Khi truy vấn bảng có index, PostgreSQL không có một đường thực thi duy nhất.

| Node | Ý tưởng thực thi | Có thể đọc heap không? |
|---|---|---|
| `Seq Scan` | Đọc tuần tự các trang bảng | Có; đó là nguồn dữ liệu chính |
| `Index Scan` | Dò khóa index, truy cập các bản ghi phù hợp trong heap | Thông thường có |
| `Index Only Scan` | Dò index; lấy các cột từ index, chỉ đọc heap khi cần kiểm tra visibility | Có thể có hoặc bằng 0 |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Lấy các vị trí ứng viên từ index rồi đọc các heap pages theo bitmap | Có ở bước Bitmap Heap Scan |

### 2.1. Index Scan

Sơ đồ:

```text
B-tree index
    |
    | tìm store_id = 42
    v
Các index entries + heap TIDs
    |
    v
Truy cập các heap tuples tương ứng
    |
    v
Kiểm tra visibility, đọc cột, trả kết quả
```

Node `Index Scan` phù hợp khi index giúp tìm nhanh tập hàng, nhưng vẫn cần đọc heap vì truy vấn cần cột không nằm trong index hoặc vì cấu trúc scan không được chọn để tránh heap.

### 2.2. Index Only Scan

Sơ đồ:

```text
B-tree index
    |
    | tìm phạm vi khóa và lấy payload
    v
Index entry -> heap TID
    |
    v
Visibility map của heap page chứa TID
    |
    +-- all-visible = 1 --> không cần đọc heap để xác minh tuple
    |
    +-- all-visible = 0 --> phải tra heap để kiểm tra MVCC
    |
    v
Trả các cột lấy từ index
```

Tên *Only* diễn tả mục tiêu **lấy giá trị cột từ index**. Nó không bảo đảm số lần tra heap tuyệt đối bằng 0.

### 2.3. Bitmap Heap Scan

Với điều kiện trả nhiều hàng phân tán, planner có thể chọn:

```text
Bitmap Index Scan
      |
      v
Bitmap của heap TIDs/pages
      |
      v
Bitmap Heap Scan
      |
      v
Đọc các trang heap theo kế hoạch bitmap
```

Bitmap plan có thể giảm random I/O nhưng không giữ thứ tự các mục giống quét B-tree tuyến tính. Nếu truy vấn có `ORDER BY`, có thể cần `Sort`.

### 2.4. Seq Scan không luôn là kế hoạch tệ

Nếu bảng rất nhỏ hoặc query trả phần lớn các hàng, đọc tuần tự có thể nhanh hơn đi qua index rồi xác minh nhiều vị trí.

Không nên đánh giá “tốt/xấu” chỉ dựa vào tên node. Cần xem **chi phí, rows, buffers, timing và workload thực tế**.

## 3. Phân biệt index entry và hàng trong heap

PostgreSQL thông thường lưu các phiên bản bản ghi của bảng trong **heap**. Khi INSERT/UPDATE/DELETE, cơ chế MVCC có thể tạo hoặc thay đổi khả năng nhìn thấy của các **phiên bản tuple**.

B-tree index thông thường lưu:

- Giá trị **khóa index**.
- Các cột payload nếu index có `INCLUDE`.
- Thông tin để dẫn tới hàng/phiên bản hàng, thường là **heap TID**.

Một tuple trong heap còn chứa metadata quan trọng đối với MVCC, như thông tin transaction tạo/xóa phiên bản. Index entry **không tự chứa mọi thông tin visibility** để quyết định chắc chắn tuple có được phép nhìn thấy trong snapshot hay không.

### 3.1. Vì sao không đơn giản lấy kết quả từ index?

Hãy hình dung:

```text
T1: UPDATE sale 100 từ status='NEW' thành 'PAID'
T1: chưa COMMIT

T2: SELECT theo index
```

T2 không được coi phiên bản chưa commit của T1 là bản ghi đã commit và được phép nhìn thấy theo mọi snapshot. Việc tìm thấy một index entry không đủ xác định điều đó.

### 3.2. Index Only Scan không bỏ qua MVCC

Dù các cột cần trả nằm trong index, PostgreSQL vẫn phải đảm bảo:

- Hàng phù hợp với snapshot của transaction đang đọc.
- Một phiên bản chưa commit hoặc không hợp lệ không bị trả sai.
- Các quy tắc visibility của transaction được duy trì.

**Visibility map** là cơ chế giúp PostgreSQL biết khi nào có thể bỏ qua việc tới heap để kiểm tra từng tuple.

## 4. Visibility map: chìa khóa tránh heap fetch

Mỗi heap relation có một **visibility map** (thường viết tắt *VM*) theo dõi trạng thái khả năng nhìn thấy ở cấp **heap page**.

Trong cơ chế thông dụng của PostgreSQL, VM có các bit quan trọng:

- **All-visible:** mọi tuple trên heap page được coi là hiển thị đối với mọi transaction phù hợp; index-only scan có thể tránh phải kiểm tra từng tuple trong heap page đó.
- **All-frozen:** mọi tuple liên quan trên page được coi là frozen theo cơ chế VACUUM, phục vụ quản lý transaction ID/tuple freezing và các tối ưu liên quan.

**Đối với Index Only Scan, bit all-visible là tín hiệu mấu chốt.** Đừng đánh đồng all-frozen với điều kiện bắt buộc của Index Only Scan.

### 4.1. Visibility map tính theo page, không theo hàng

Giả sử một heap page chứa nhiều hàng:

```text
Heap page P
   tuple 1
   tuple 2
   tuple 3
   tuple 4
   ...

VM[P].all_visible = 1
    -> các tuple phù hợp trên page có thể được index-only scan
       xác minh visibility mà không đọc lại page P

VM[P].all_visible = 0
    -> khi cần kiểm tra một entry chỉ tới P,
       index-only scan phải tới heap để kiểm tra visibility
```

Một lần UPDATE một hàng trên page có thể khiến bit all-visible của **cả page** bị xóa. Điều đó tác động đến index-only scans của **nhiều hàng khác cùng page**, dù các hàng ấy không trực tiếp được sửa.

### 4.2. Vì sao thiết kế theo page có lợi?

VM nhỏ hơn rất nhiều so với một cấu trúc lưu visibility chi tiết cho từng tuple, nên có thể được đọc hiệu quả. PostgreSQL thường kiểm tra VM trước; nếu page all-visible thì không cần fetch heap tuple để xác minh visibility.

### 4.3. VM được cập nhật khi nào?

Ở mức ý tưởng:

- `INSERT` mới làm xuất hiện các tuple chưa thể mặc định được coi là all-visible ngay lập tức.
- `UPDATE`/`DELETE` có thể khiến một page trước đó all-visible không còn đáp ứng điều kiện và cần xóa bit tương ứng.
- `VACUUM` có thể xác minh, dọn dẹp và đánh dấu những pages đủ điều kiện thành all-visible.
- Các giao dịch chưa kết thúc, phiên bản còn cần cho snapshot cũ và tình trạng dữ liệu khác có thể khiến VACUUM chưa đánh dấu được một số pages.

**Đừng suy luận “vừa COMMIT xong thì VM tự trở thành all-visible ngay”.** COMMIT không đồng nghĩa VACUUM đã quét và đánh dấu các pages.

### 4.4. VACUUM không phải một công tắc bảo đảm Heap Fetches = 0

Ngay sau khi VACUUM thành công, một giao dịch khác có thể tiếp tục sửa bảng và làm mất các bit all-visible trên pages liên quan. Ngoài ra, có thể tồn tại các pages chưa đủ điều kiện để đánh dấu.

Vì vậy, kết quả quan sát Heap Fetches phụ thuộc **thời điểm thực thi và trạng thái dữ liệu**, không chỉ lịch VACUUM.

## 5. Điều kiện 1: index phải chứa dữ liệu truy vấn cần

Một `Index Only Scan` chỉ khả thi khi PostgreSQL có thể lấy các dữ liệu cần cho phần truy cập từ index thích hợp, thay vì phải lấy một cột không được index lưu.

Ví dụ bảng:

```sql
CREATE TABLE sales (
    sale_id bigint PRIMARY KEY,
    store_id integer NOT NULL,
    sold_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL,
    status text NOT NULL,
    note text NOT NULL
);
```

Index:

```sql
CREATE INDEX ON sales(store_id, sold_at);
```

Query:

```sql
SELECT store_id, sold_at
FROM sales
WHERE store_id = 42;
```

Các cột được truy vấn thuộc index, nên **khả năng dùng Index Only Scan** tồn tại nếu các điều kiện khác phù hợp.

Nhưng:

```sql
SELECT store_id, sold_at, note
FROM sales
WHERE store_id = 42;
```

Cột `note` không có trong index. Với **index này**, PostgreSQL phải lấy `note` từ heap hoặc tìm một plan khác. Không thể coi Index Only Scan của index `(store_id,sold_at)` là đủ cho truy vấn trả `note`.

### 5.1. Cột trong WHERE cũng cần được xét

Nếu query đọc `note` chỉ để lọc:

```sql
SELECT store_id, sold_at
FROM sales
WHERE store_id = 42
  AND note = 'urgent';
```

thì chỉ mục `(store_id,sold_at)` không chứa `note` để kiểm tra predicate ấy. Planner có thể phải lấy heap hoặc chọn cách thực thi khác.

### 5.2. ORDER BY và biểu thức cũng có vai trò

Cần tính đến cột dùng trong:

- `SELECT`.
- `WHERE`.
- `ORDER BY`.
- Một số biểu thức/điều kiện khác mà node thực thi cần đánh giá.

Có một index “chứa các cột SELECT” nhưng thiếu cột cần lọc/sắp xếp có thể vẫn không đủ cho kế hoạch hoàn toàn index-only theo query cụ thể.

### 5.3. Không phải mọi index access method đều hỗ trợ

B-tree là trường hợp điển hình hỗ trợ index-only scan vì index lưu các giá trị khóa phù hợp.

Những index access methods khác có khả năng khác nhau:

- Một số GiST/SP-GiST operator classes có thể hỗ trợ.
- GIN thường không thể phục vụ index-only scan theo cách B-tree làm, vì các mục index của nó không chứa giá trị gốc đầy đủ của từng hàng theo yêu cầu.
- Khả năng thực tế phụ thuộc phương pháp/operator class và phiên bản PostgreSQL.

Đừng suy luận “có bất kỳ index nào” là planner đều có thể chọn Index Only Scan.

## 6. Điều kiện 2: chi phí kế hoạch phải hợp lý

Ngay khi index chứa đủ cột và B-tree hỗ trợ index-only scan, PostgreSQL **không bắt buộc** sử dụng nó.

Planner ước lượng:

- Có bao nhiêu hàng có khả năng khớp predicate?
- Chúng phân bố thế nào trong index và heap?
- Tỷ lệ heap pages dự kiến all-visible là bao nhiêu?
- Truy vấn cần đọc bao nhiêu index entries?
- Chi phí đọc index so với Seq Scan, Bitmap Scan?
- Có cần Sort không?
- `LIMIT` có giúp dừng sớm không?
- Một plan khác đã tận dụng index tốt hơn chưa?

Ví dụ:

```sql
SELECT COUNT(*)
FROM sales;
```

Dù một index có thể cung cấp thông tin về entries, một Seq Scan hoặc kế hoạch song song khác vẫn có thể rẻ hơn khi phải xét phần lớn bảng.

### 6.1. Tỷ lệ all-visible là một yếu tố chi phí

Nếu phần lớn heap pages all-visible, Index Only Scan có cơ hội bỏ qua nhiều heap fetches. Nếu bảng bị UPDATE liên tục khiến nhiều VM bits bị xóa, planner có thể dự đoán cần đọc heap thường xuyên và chọn plan khác.

Một plan được chọn lúc bảng đọc nhiều, sửa ít có thể khác plan lúc bảng đang có tải ghi lớn.

## 7. Chuẩn bị môi trường lab độc lập

Các ví dụ sau dùng schema riêng `ios270` trong một database PostgreSQL thử nghiệm. Chúng sẽ **tạo bảng, index và sửa dữ liệu**, nên không chạy trên production.

### 7.1. Tạo bảng sales

```sql
CREATE SCHEMA IF NOT EXISTS ios270;

CREATE TABLE ios270.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id integer NOT NULL,
    sold_at timestamptz NOT NULL,
    amount_cents bigint NOT NULL CHECK (amount_cents >= 0),
    status text NOT NULL
        CHECK (status IN ('NEW', 'PAID', 'CANCELLED')),
    note text NOT NULL DEFAULT ''
);
```

### 7.2. Tạo dữ liệu có nhiều trang heap

```sql
INSERT INTO ios270.sales (
    store_id, sold_at, amount_cents, status, note
)
SELECT
    (g.n % 1000) + 1,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + (g.n % 180) * INTERVAL '1 day'
        + (g.n % 86400) * INTERVAL '1 second',
    (g.n % 5000 + 1)::bigint * 100,
    CASE
        WHEN g.n % 10 IN (0, 1) THEN 'CANCELLED'
        WHEN g.n % 10 IN (2, 3, 4) THEN 'PAID'
        ELSE 'NEW'
    END,
    repeat('x', 120)
FROM generate_series(1, 200000) AS g(n);
```

Dữ liệu gồm 200.000 sales được phân tán trên 1.000 store IDs. Cột `note` có độ dài tương đối để bảng không quá nhỏ, giúp dễ quan sát chi phí đọc heap.

Lưu ý:

- Chỉ chạy câu INSERT một lần trên fixture trống; chạy lại sẽ thêm 200.000 hàng.
- Hàng `store_id=42` có thể được chọn bằng predicate trong các ví dụ sau.
- Timestamp, số lượng hàng và phần trăm phân bố chỉ là dữ liệu mô phỏng.
- Trong môi trường thực tế, kế hoạch thực thi và số fetches không được bảo đảm theo con số cụ thể.

### 7.3. Tạo một index ghép có payload

```sql
CREATE INDEX idx_ios270_sales_store_time_cover
ON ios270.sales (
    store_id,
    sold_at DESC,
    sale_id DESC
)
INCLUDE (amount_cents, status);
```

Index lưu:

- **Key columns:** `store_id`, `sold_at`, `sale_id`.
- **INCLUDE payload:** `amount_cents`, `status`.

Cột `note` cố ý **không nằm trong index**.

### 7.4. Cập nhật thống kê

```sql
ANALYZE ios270.sales;
```

`ANALYZE` giúp planner ước lượng dữ liệu. Nó **không đồng nghĩa đã đánh dấu tất cả heap pages all-visible**. Phần sau sẽ dùng `VACUUM` riêng.

### 7.5. Query nghiên cứu

```sql
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
  AND sold_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND sold_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Cột lọc, sắp xếp và trả về đều có trong index. Index này là **ứng viên** cho Index Only Scan; việc planner thực sự chọn gì phụ thuộc môi trường.

### 7.6. Kiểm tra số lượng dữ liệu

```sql
SELECT COUNT(*) AS total_sales
FROM ios270.sales;

SELECT COUNT(*) AS store_42_sales
FROM ios270.sales
WHERE store_id = 42;
```

Nếu chỉ chèn đúng một lần, total_sales là 200.000; store_42_sales dự kiến là khoảng 200. Không tự dùng những con số mô phỏng làm kết quả cho một database đã tồn tại trước đó.

## 8. Đọc EXPLAIN (ANALYZE, BUFFERS)

Chạy truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
  AND sold_at >= TIMESTAMPTZ '2026-02-01 00:00:00+00'
  AND sold_at <  TIMESTAMPTZ '2026-06-01 00:00:00+00'
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Một dạng kế hoạch **minh họa**, không phải log đo thực tế:

```text
Limit  (cost=... rows=50 ...)
  (actual time=... rows=50 loops=1)
  -> Index Only Scan using idx_ios270_sales_store_time_cover
       on sales
       (cost=... rows=...)
       (actual time=... rows=50 loops=1)
       Index Cond: ((store_id = 42) AND (...))
       Heap Fetches: 0
       Buffers: shared hit=... read=...
Planning Time: ...
Execution Time: ...
```

Ở môi trường khác, có thể thấy `Index Scan`, `Bitmap Heap Scan` hoặc các con số Heap Fetches khác. Bài không giả định đã chạy PostgreSQL để sinh output cụ thể.

### 8.1. Index Only Scan

`Index Only Scan using idx_ios270_sales_store_time_cover` cho biết executor dùng index ấy để lấy các giá trị mà query cần, với cơ chế kiểm tra VM/heap khi cần.

### 8.2. Index Cond

`Index Cond` hiển thị những predicate mà index node có thể dùng trong bước tìm/duyệt index. Trong ví dụ, điều kiện equality trên `store_id` kết hợp khoảng `sold_at` phù hợp với thứ tự khóa index.

### 8.3. Heap Fetches

`Heap Fetches: 0` nghĩa là trong quá trình thực thi node Index Only Scan này, PostgreSQL **không cần tra heap để kiểm tra visibility cho các index entries đã xử lý theo cách được đếm**.

Nếu `Heap Fetches: 50`, nó đã phải tra heap để xác minh visibility 50 lần trong quá trình node thực hiện.

Đây **không phải**:

- Số heap pages vật lý duy nhất đã đọc.
- Số lần I/O từ ổ đĩa.
- Số hàng được trả về.
- Số index entries được đọc theo mọi phép đếm.
- Chỉ số “số lỗi” của index.

### 8.4. Buffers

`Buffers: shared hit=... read=...` cho biết buffer accesses ở các loại như shared hit/read. Số hit là dữ liệu đã có trong buffer cache, **không có nghĩa không có xử lý CPU hoặc visibility check**.

Một Index Only Scan có thể phải đọc:

- Index pages.
- Visibility map pages.
- Heap pages khi VM chưa xác nhận all-visible.

Do đó, ngay khi `Heap Fetches=0`, query **vẫn cần đọc index/visibility map pages**; nó không phải một truy vấn “không đọc trang nào”.

### 8.5. Actual rows và loops

`actual rows` là số hàng mà node thực thi trả lên node cha theo quy tắc hiển thị của EXPLAIN; `loops` là số lần node được gọi. Khi một node chạy nhiều lần, EXPLAIN có những số liệu hiển thị theo vòng lặp và số tổng cần diễn giải đúng từng loại thuộc tính.

Không mặc định so `Heap Fetches` với số hàng ở node `Limit` như một tỷ lệ cố định.

## 9. Heap Fetches có phải số heap pages đã đọc không?

**Không.** Đây là nhầm lẫn rất phổ biến.

Giả sử 100 index entries dẫn tới các tuple trong **cùng một heap page**, và VM bit cho page đó không all-visible.

Executor có thể cần kiểm tra visibility cho nhiều tuple trên cùng page. Khi đó:

```text
Heap Fetches: 100
```

không có nghĩa đã phải đọc 100 heap pages **khác nhau** từ ổ cứng. Một heap page có thể được lấy trong shared buffers rồi tiếp tục được truy cập nhiều lần.

Ngược lại, một truy vấn đọc nhiều index/VM pages vẫn có thể có:

```text
Heap Fetches: 0
Buffers: shared hit=... read=...
```

### 9.1. Ví dụ diễn giải

| Tình huống | Heap Fetches | Cách hiểu |
|---|---:|---|
| 50 tuples từ pages all-visible | 0 | Không cần tra heap cho visibility |
| 50 tuples từ pages chưa all-visible | Có thể tới 50 hoặc hơn tùy đường thực thi | Có những lần tra heap cho visibility |
| 1.000 tuples nằm trên 20 heap pages chưa all-visible | Có thể hàng trăm/hàng nghìn lần | Không đồng nghĩa từng ấy pages vật lý |
| 10 tuples cần trả, node kiểm tra thêm ứng viên | Có thể lớn hơn 10 | Fetches không phải số hàng kết quả |
| Index Only Scan xuất hiện dưới Nested Loop nhiều lần | Có thể cộng dồn qua các lần gọi | Phải xem loops và cấu trúc toàn plan |

Những số trên là **kịch bản giả định**, không phải kết quả một phép đo.

### 9.2. Vì sao Heap Fetches đôi khi lớn hơn số hàng trả về?

Node có thể phải xét nhiều ứng viên trước khi lọc, có `LIMIT` ở tầng trên, hoặc được gọi lặp bởi Nested Loop. Các lần tra heap phục vụ xác minh visibility có thể nhiều hơn số hàng cuối cùng của query.

Một index entry dẫn đến phiên bản tuple không phù hợp snapshot có thể vẫn khiến executor kiểm tra heap mà **không trả một hàng kết quả**.

## 10. Thí nghiệm A: sau INSERT, chưa VACUUM

Sau khi tạo dữ liệu và index, chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

**Điều cần quan sát:**

- Planner có chọn Index Only Scan không?
- Nếu có, `Heap Fetches` là bao nhiêu?
- Buffers hit/read thế nào?
- Thời gian và số hàng thực tế ra sao?

Ngay sau khi INSERT lớn, nhiều pages có thể chưa được đánh dấu all-visible. Bởi vậy Index Only Scan **có thể** có Heap Fetches đáng kể.

Nhưng nếu autovacuum đã chạy, môi trường có các giao dịch khác hoặc planner chọn node khác, kết quả có thể khác. Đây là thí nghiệm quan sát, **không phải phép thử yêu cầu luôn có Heap Fetches dương**.

### 10.1. Tại sao CREATE INDEX không mặc nhiên khiến VM all-visible?

`CREATE INDEX` xây dựng cấu trúc index cần cho truy vấn, nhưng không có nghĩa tất cả heap pages được chứng minh all-visible cho các snapshot đang hoạt động. Điều kiện all-visible có vòng đời/bảo trì riêng, chủ yếu liên quan VACUUM và các hoạt động MVCC.

### 10.2. ANALYZE có thay VACUUM không?

Không. `ANALYZE` thu thập thống kê cho planner. `VACUUM` xử lý bảo trì tuple và visibility map theo những quy tắc phù hợp.

Một index có thống kê tốt **vẫn có thể phải tra heap nhiều lần** do pages chưa all-visible.

## 11. Thí nghiệm B: VACUUM ANALYZE rồi đo lại

Sau khi kết thúc transaction INSERT và bảo đảm lệnh đang ở môi trường lab phù hợp, chạy riêng:

```sql
VACUUM (ANALYZE) ios270.sales;
```

**Quan trọng:** `VACUUM` thông thường không được chạy bên trong explicit transaction block. Chạy trực tiếp với autocommit khi thực hành; không viết:

```sql
BEGIN;
VACUUM ios270.sales;
COMMIT;
```

để mong VACUUM hoạt động trong transaction.

Sau khi VACUUM:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

### 11.1. Điều gì có thể thay đổi?

Nếu VACUUM đánh dấu được những heap pages chứa các tuple phù hợp thành **all-visible**, một Index Only Scan có thể báo `Heap Fetches: 0` hoặc giảm đáng kể.

Dưới cùng plan, cùng dữ liệu và sau khi VM được cập nhật, việc giảm heap fetches thường giúp giảm công việc xác minh tuple.

### 11.2. Đừng coi tốc độ thay đổi là bằng chứng duy nhất

Lần chạy thứ hai có thể nhanh hơn vì:

- Dữ liệu/index pages đã được đưa vào buffer cache.
- Visibility map tốt hơn.
- Thống kê mới dẫn tới plan khác.
- Workload hệ thống tại thời điểm đó nhẹ hơn.
- Các trang heap/index bị tác động bởi tác vụ khác.

Muốn phân tích đúng, xem đồng thời:

- Tên node.
- `Heap Fetches`.
- `Buffers`.
- `actual rows`.
- `Execution Time`.
- Dữ liệu/transaction và điều kiện cache tương ứng.

### 11.3. Nếu Heap Fetches vẫn cao?

Các khả năng gồm:

- Có transaction cũ còn giữ snapshot làm một số pages chưa thể all-visible.
- Có DML mới sau VACUUM.
- VACUUM chưa thể đánh dấu mọi page.
- Planner hoặc đường thực thi khác với kỳ vọng.
- Query truy cập những pages vừa bị sửa thường xuyên.

Không kết luận VACUUM bị lỗi chỉ từ một con số. Phải xem trạng thái MVCC, VM và hoạt động ghi thực tế.

## 12. Thí nghiệm C: UPDATE cột không nằm trong index

Đây là điểm rất quan trọng: **không cần đổi khóa index mới ảnh hưởng Index Only Scan**.

Sau khi VACUUM và đo baseline, chạy:

```sql
UPDATE ios270.sales
SET note = note || ' reviewed'
WHERE store_id = 42;
```

Cột `note` **không** nằm trong index `idx_ios270_sales_store_time_cover`. Từ góc nhìn các cột mà query SELECT ở phần trước cần, các giá trị khóa/payload vẫn giống cũ.

Tuy nhiên UPDATE đã tạo tác động tới các phiên bản tuple trong heap. Các heap pages bị ảnh hưởng có thể mất bit **all-visible** trong VM.

Đo lại:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

Nếu planner tiếp tục dùng Index Only Scan, `Heap Fetches` **có thể tăng** so với sau VACUUM, vì VM chưa còn chứng nhận các pages liên quan all-visible.

### 12.1. Vì sao đây là bài học quan trọng?

Một người có thể lập luận:

> “Chúng ta chỉ sửa note, còn sale_id, sold_at, status và amount_cents không đổi. Index vẫn chứa mọi cột query. Vậy không cần heap.”

Lập luận thiếu một bước: **visibility của phiên bản hàng trong heap đã thay đổi**. Index-only scan có thể cần kiểm tra heap để tránh trả phiên bản không phù hợp.

### 12.2. HOT update có làm mất nhu cầu heap fetch không?

PostgreSQL có **HOT (Heap-Only Tuple)** updates trong các điều kiện thích hợp, nhằm tránh phải cập nhật index entries khi những cột liên quan index không thay đổi và điều kiện về trang/không gian thỏa mãn.

Nhưng:

- HOT là tối ưu **đường ghi/index maintenance**.
- Nó **không bảo đảm** heap page giữ bit all-visible sau UPDATE.
- Một index-only scan vẫn có thể phải tới heap để xử lý visibility đối với các trang bị sửa.
- Query planner có thể đổi từ Index Only Scan sang plan khác sau khi thống kê/chi phí thay đổi.

Vì vậy “UPDATE có thể HOT” **không** có nghĩa “Index Only Scan vẫn luôn có Heap Fetches = 0”.

### 12.3. Sau đó VACUUM lại

Khi các transaction liên quan đã hoàn tất và không còn hoạt động ghi mới ảnh hưởng đến cùng pages:

```sql
VACUUM (ANALYZE) ios270.sales;
```

Chạy lại EXPLAIN. Nếu các pages đủ điều kiện all-visible, Heap Fetches có thể giảm trở lại.

**Dòng thời gian minh họa:**

```text
INSERT 200.000 rows
    |
    v
Nhiều pages chưa all-visible
    |
    v
VACUUM
    |
    v
Nhiều pages all-visible
    |
    v
Index Only Scan có thể ít/0 Heap Fetches
    |
    v
UPDATE note của store 42
    |
    v
Các pages liên quan mất all-visible bit
    |
    v
Index Only Scan có thể tăng Heap Fetches
    |
    v
VACUUM khi đủ điều kiện
    |
    v
All-visible có thể được thiết lập lại
```

Đây là xu hướng thiết kế để quan sát, không cam kết tất cả các bước cho ra con số cụ thể trên mọi PostgreSQL server.

## 13. Thí nghiệm D: cập nhật cột có trong index

Bây giờ xét:

```sql
UPDATE ios270.sales
SET status = 'PAID'
WHERE store_id = 42
  AND status = 'NEW';
```

Khác với UPDATE note, cột `status` được **INCLUDE** trong index. Thay đổi status có thể đòi hỏi duy trì index entries chứa payload mới.

Hệ quả tiềm năng:

- Tăng lượng ghi/WAL và chi phí duy trì index.
- MVCC tạo phiên bản mới của hàng.
- Heap pages liên quan có thể mất all-visible.
- Truy vấn Index Only Scan sau đó có thể phải fetch heap.
- HOT update thường không khả thi nếu cột thay đổi được index tham chiếu, kể cả đó là cột INCLUDE.

### 13.1. INCLUDE không miễn phí khi UPDATE

Cột INCLUDE không dùng để định vị khóa theo thứ tự B-tree, nhưng nó **vẫn nằm trong index tuple**. Khi giá trị payload đổi, index cần được duy trì theo quy tắc cập nhật.

Một cột status thay đổi rất thường xuyên có thể khiến covering index lớn/tốn chi phí hơn lợi ích tiết kiệm heap reads trong workload ghi cao.

### 13.2. Quan sát đúng hiệu năng ghi

Ngoài `EXPLAIN SELECT`, khi đánh giá INCLUDE nên đo:

- Latency UPDATE/INSERT.
- WAL generation.
- Kích thước index.
- Tần suất HOT update.
- Autovacuum work.
- Heap Fetches của các truy vấn đọc.
- Hiệu năng tổng thể dưới concurrency.

Không thêm INCLUDE chỉ để làm đẹp plan ở một truy vấn SELECT đơn lẻ.

## 14. Giải thích vì sao VACUUM đôi khi không tạo all-visible

Một heap page được coi all-visible khi PostgreSQL có đủ cơ sở để xác nhận tất cả các tuples liên quan có khả năng nhìn thấy thích hợp cho các transaction; điều này phụ thuộc trạng thái commit và những snapshots đang hoạt động.

Các tình huống đáng chú ý:

### 14.1. Transaction ghi chưa commit

Nếu transaction A vừa INSERT/UPDATE và chưa commit, PostgreSQL không thể coi các phiên bản tuple chưa commit là hiển thị với mọi transaction.

### 14.2. Transaction dài còn giữ snapshot cũ

Một transaction đọc lâu có thể vẫn cần một phiên bản hàng cũ. Việc dọn dẹp phiên bản và đánh dấu visibility có thể bị ảnh hưởng bởi mốc giao dịch cũ.

### 14.3. DML liên tục

Một trang vừa được VACUUM đánh dấu all-visible có thể bị một UPDATE sau đó làm mất bit. Trong bảng ghi rất nhiều, tỷ lệ pages all-visible không ổn định.

### 14.4. VACUUM chưa quét/đánh dấu được tất cả pages

VACUUM có nhiều quy tắc vận hành, điều kiện bỏ qua trang và giới hạn theo trạng thái dữ liệu. Không thể chỉ dựa vào dòng “VACUUM” hoàn thành để suy ra mọi page all-visible.

### 14.5. Replica và long-running snapshots

Các tình huống sao chép hoặc giữ snapshot lâu có thể ảnh hưởng vòng đời tuple/cleanup trong những cấu hình nhất định. Khi chẩn đoán trên production, cần xem bối cảnh transaction và replication thực tế, không mặc định chỉ là vấn đề “thiếu VACUUM”.

## 15. Quan sát tỷ lệ all-visible từ pg_class

Có thể xem những số liệu catalog/ước lượng liên quan heap relation:

```sql
SELECT
    c.relname,
    c.relpages,
    c.relallvisible,
    ROUND(
        100.0 * c.relallvisible
        / NULLIF(c.relpages, 0),
        2
    ) AS pct_pages_all_visible_estimate
FROM pg_class AS c
WHERE c.oid = 'ios270.sales'::regclass;
```

Các cột:

- `relpages`: số heap pages được ghi nhận/ước lượng trong thống kê relation.
- `relallvisible`: số pages được ghi nhận là all-visible theo thông tin được duy trì cho planner.
- Phần trăm: một **ước lượng** hỗ trợ hiểu lý do planner kỳ vọng index-only scan có hoặc không có ích.

### 15.1. relallvisible không phải số Heap Fetches

`relallvisible` là thông tin về **pages của cả relation**, còn `Heap Fetches` là số lần kiểm tra heap thực tế **trong một node thực thi cụ thể**.

Hai số khác cấp độ:

```text
relallvisible:
    mô tả các trang trên toàn bảng theo catalog/ước lượng

Heap Fetches:
    mô tả hoạt động thực thi trong một Index Only Scan
```

Không lấy:

```text
Heap Fetches = relpages - relallvisible
```

Đây là công thức **sai**. Một page chưa all-visible có thể chứa rất nhiều index entries được query chọn, hoặc không chứa entry nào của query.

### 15.2. Các con số catalog có thể chưa cập nhật

`relpages`/`relallvisible` không phải đồng hồ giám sát chính xác từng microsecond. Chúng phục vụ ước lượng và có thể được cập nhật bởi các hoạt động như VACUUM/ANALYZE theo cơ chế PostgreSQL.

Muốn kiểm tra trực tiếp trạng thái VM chi tiết hơn, có thể dùng extension chuyên dụng nếu có quyền phù hợp.

## 16. Xem visibility map bằng pg_visibility

PostgreSQL có extension **`pg_visibility`** hỗ trợ quan sát visibility map/visibility của relation.

Trong môi trường lab có quyền thích hợp:

```sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
```

Sau đó có thể kiểm tra:

```sql
SELECT
    COUNT(*) AS heap_pages_in_map,
    COUNT(*) FILTER (WHERE all_visible)
        AS all_visible_pages,
    COUNT(*) FILTER (WHERE NOT all_visible)
        AS not_all_visible_pages,
    COUNT(*) FILTER (WHERE all_frozen)
        AS all_frozen_pages
FROM pg_visibility_map('ios270.sales'::regclass);
```

Hàm `pg_visibility_map(regclass)` cung cấp thông tin theo từng block, gồm `blkno`, `all_visible` và `all_frozen` khi extension/phiên bản hỗ trợ.

### 16.1. Nếu không có quyền CREATE EXTENSION

Không cố thay đổi cấu hình production hoặc xin đặc quyền hệ thống chỉ để hoàn thành ví dụ. Dùng `pg_class.relallvisible`, `EXPLAIN`, các view thống kê và nhờ DBA hỗ trợ nếu cần.

### 16.2. Không dùng pg_visibility để “chữa” VM

`pg_visibility` chủ yếu là công cụ **quan sát/chẩn đoán**, không phải một thao tác VACUUM thay thế.

Khi thấy nhiều pages chưa all-visible, cần tìm nguyên nhân: hoạt động ghi, transaction dài, vacuum scheduling, snapshot retention; không chỉ ép một thao tác maintenance bất kỳ.

### 16.3. Quan sát trước và sau UPDATE

Lịch thực hành:

1. Chạy VACUUM.
2. Đọc số `all_visible_pages`.
3. Chạy UPDATE trên store_id=42.
4. Đọc lại.
5. Chạy EXPLAIN và so sánh Heap Fetches.
6. VACUUM sau khi mọi transaction liên quan kết thúc.
7. Đọc VM và EXPLAIN lần nữa.

Không cần kỳ vọng all_visible_pages giảm **đúng bằng số hàng được UPDATE**. VM theo page, một page có thể chứa nhiều hàng.

## 17. Index Scan và Index Only Scan khác nhau ở đâu trong plan?

Cùng query logic có thể có hai dạng:

**Dạng Index Scan:**

```text
Index Scan using idx_ios270_sales_store_time_cover on sales
  Index Cond: (store_id = 42)
```

**Dạng Index Only Scan:**

```text
Index Only Scan using idx_ios270_sales_store_time_cover on sales
  Index Cond: (store_id = 42)
  Heap Fetches: 0
```

Ở dạng Index Scan, PostgreSQL dùng index để tìm hàng rồi lấy dữ liệu/visibility từ heap theo cơ chế node đó. Dạng Index Only Scan cố lấy dữ liệu từ index và dùng VM để quyết định có bỏ qua heap hay không.

### 17.1. Không so sánh thiếu ngữ cảnh

Đừng chỉ nhìn:

```text
Index Scan 30 ms
Index Only Scan 40 ms
```

rồi kết luận Index Only Scan luôn chậm hơn. Cần biết:

- Các query có thật sự giống nhau?
- Số hàng có giống nhau?
- Dữ liệu có thay đổi?
- Cache/buffers khác nhau?
- Có Sort/Nested Loop/parallel workers khác?
- Tỷ lệ all-visible và Heap Fetches khác?
- Plan được chọn dưới cùng thống kê/cấu hình không?

### 17.2. Index Scan có thể nhanh hơn khi nào?

Một Index Scan có thể được chọn nếu phải trả cột không nằm trong index, hoặc planner ước lượng một kế hoạch đọc heap trực tiếp rẻ hơn Index Only Scan hiện có.

“Index Only” là **tùy chọn thực thi**, không phải lời bảo đảm về thời gian chạy.

## 18. Thêm SELECT *: cách vô tình làm mất covering index

Giả sử truy vấn:

```sql
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Index được thiết kế bao phủ tất cả các cột cần thiết.

Đổi thành:

```sql
SELECT *
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50;
```

Bây giờ `*` bao gồm cả cột `note` không nằm trong index. Vì thế **index đó không còn bao phủ query**. PostgreSQL có thể chọn Index Scan hoặc kế hoạch khác để lấy `note`.

### 18.1. SELECT * còn ảnh hưởng ngoài indexing

Ngoài việc mất khả năng index-only:

- Truyền nhiều dữ liệu qua mạng hơn.
- Phụ thuộc vào schema khi bảng thêm cột.
- Làm tăng chi phí decode/serialization trong driver.
- Có nguy cơ vô tình trả dữ liệu nhạy cảm qua API.

Chỉ lấy những cột mà ứng dụng thực sự cần.

### 18.2. Nhưng không nên cắt cột cần thiết chỉ để được Index Only Scan

Nếu nghiệp vụ cần `note`, query phải trả đúng dữ liệu. Có thể cân nhắc:

- Index INCLUDE(note) nếu note nhỏ, ít đổi và query đủ quan trọng.
- Một query khác được tổ chức theo workload.
- Chấp nhận Index Scan vì heap access vẫn đủ nhanh.

Tối ưu không được đánh đổi tính đúng của dữ liệu trả về.

## 19. INCLUDE: cột payload có lợi gì?

B-tree index có thể khai báo:

```sql
CREATE INDEX idx_example
ON some_table (key_a, key_b)
INCLUDE (payload_c);
```

Trong đó:

- `key_a` và `key_b` quyết định **thứ tự/tìm kiếm B-tree**.
- `payload_c` được lưu trong index tuple để có thể trả dữ liệu mà không đọc heap khi VM cho phép.
- `payload_c` không dùng như một thành phần khóa để thu hẹp phạm vi quét theo thứ tự B-tree.
- Với unique index, tính duy nhất áp dụng cho **key columns**, không phải INCLUDE payload.

### 19.1. Ví dụ truy vấn theo store và thời điểm

```sql
CREATE INDEX idx_ios270_sales_store_time_cover
ON ios270.sales (
    store_id,
    sold_at DESC,
    sale_id DESC
)
INCLUDE (amount_cents, status);
```

Đối với query của cửa hàng:

```sql
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 50
```

index có key phù hợp và chứa payload cần trả.

### 19.2. Nếu WHERE chỉ lọc amount_cents?

```sql
SELECT sale_id, amount_cents
FROM ios270.sales
WHERE amount_cents > 100000;
```

Ở index hiện tại, `amount_cents` là INCLUDE, không phải key dẫn đường. PostgreSQL không thể coi nó giống một B-tree key được sắp thứ tự để định vị trực tiếp khoảng `> 100000`.

Nếu query loại này rất phổ biến, có thể cần index khác trên `amount_cents` hoặc key tuple phù hợp.

### 19.3. Payload lớn có rủi ro

Một index INCLUDE nhiều cột lớn có thể:

- Tăng đáng kể kích thước index.
- Làm giảm số index entries trên mỗi page.
- Tăng WAL và chi phí INSERT/UPDATE.
- Gây lỗi vượt giới hạn kích thước index tuple trong trường hợp dữ liệu lớn.
- Hạn chế tối ưu deduplication của B-tree khi có non-key columns.

Không nên INCLUDE cột `note` dài chỉ vì muốn đạt Heap Fetches=0 ở một dashboard hiếm dùng.

## 20. MVCC, HOT update và visibility map

Hai khái niệm dễ bị trộn lẫn:

**HOT (Heap-Only Tuple)** tập trung tối ưu update khi có thể tránh tạo index entries mới.

**All-visible** tập trung đánh dấu rằng các tuples trên heap page không cần kiểm tra visibility riêng khi đọc qua index-only scan.

### 20.1. Ví dụ UPDATE note

```sql
UPDATE ios270.sales
SET note = 'checked'
WHERE sale_id = 100;
```

Nếu note không tham gia index và còn chỗ trong heap page, HOT update có thể khả thi. Nhưng dù index entries không phải cập nhật vì HOT:

- Heap tuple vẫn đã thay đổi.
- VM all-visible bit của page có thể bị xóa.
- Một Index Only Scan trên hàng liên quan có thể phải đọc heap cho visibility.

### 20.2. UPDATE status trong INCLUDE

```sql
UPDATE ios270.sales
SET status = 'PAID'
WHERE sale_id = 100;
```

Nếu `status` được INCLUDE, nó là thuộc tính tham gia index. UPDATE có thể cần duy trì index và thông thường không thỏa điều kiện HOT nếu giá trị status thực sự thay đổi.

### 20.3. Vì sao ảnh hưởng có thể lan ra nhiều query?

Một heap page lưu nhiều hàng. Sửa một hàng có thể xóa all-visible bit của page, khiến các index-only scans tìm những hàng khác cùng page cũng phải tra heap.

Do đó, tỷ lệ UPDATE của bảng và phân bố vật lý của dữ liệu có thể ảnh hưởng hiệu quả index-only scan ngoài phạm vi những hàng trực tiếp bị sửa.

## 21. Thống kê HOT và hoạt động ghi

Có thể xem thông tin tổng hợp ở `pg_stat_user_tables`:

```sql
SELECT
    schemaname,
    relname,
    n_tup_ins,
    n_tup_upd,
    n_tup_hot_upd,
    n_tup_del,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    last_analyze,
    last_autoanalyze
FROM pg_stat_user_tables
WHERE schemaname = 'ios270'
  AND relname = 'sales';
```

Diễn giải:

- `n_tup_upd`: số cập nhật được ghi nhận theo thống kê.
- `n_tup_hot_upd`: số update được ghi nhận là HOT.
- `n_dead_tup`: ước lượng dead tuples.
- `last_vacuum`/`last_autovacuum`: thời điểm hoạt động VACUUM tương ứng.
- `last_analyze`/`last_autoanalyze`: thời điểm thu thập thống kê.

### 21.1. HOT ratio không xác định Heap Fetches trực tiếp

Một bảng có HOT ratio cao vẫn có thể có nhiều pages chưa all-visible do cập nhật liên tục.

Ngược lại, bảng gần như read-only có thể cho Index Only Scan rất hiệu quả dù dữ liệu lịch sử từng có nhiều non-HOT updates.

Hai nhóm số liệu nên được xem cùng nhau để hiểu **ghi/index maintenance** và **đọc/visibility**, nhưng không có công thức đơn giản biến `n_tup_hot_upd` thành `Heap Fetches`.

### 21.2. Các counters có thời điểm reset

Không kết luận chính xác tốc độ cập nhật từ counters tích lũy khi chưa xem thời điểm thống kê được reset. Công cụ monitoring nên thu thập delta theo thời gian và gắn với workload.

## 22. VACUUM, autovacuum và công việc bảo trì

### 22.1. VACUUM giúp hai việc quan trọng liên quan bài

- Xử lý dead tuples/khả năng tái sử dụng không gian theo quy tắc MVCC.
- Cập nhật visibility map, gồm đánh dấu all-visible khi an toàn.

Nhờ đó, một bảng ít thay đổi sau VACUUM có thể có tỷ lệ all-visible cao, tạo điều kiện tốt cho Index Only Scan.

### 22.2. Autovacuum

PostgreSQL có cơ chế autovacuum để bảo trì bảng tự động theo ngưỡng và cấu hình. Vì vậy trên production, sự thay đổi của `Heap Fetches` có thể đi cùng các đợt autovacuum mà application không trực tiếp khởi chạy.

Không tự tắt autovacuum để “ổn định benchmark”; tắt hoặc cấu hình sai có thể gây dead tuples, bloat, rủi ro transaction ID wraparound và nhiều tác động nghiêm trọng.

### 22.3. Nếu bảng đang ghi nhiều

Autovacuum có thể đánh dấu all-visible một phần, nhưng các UPDATE tiếp theo lại xóa bits. Một bảng hot có thể giữ tỷ lệ all-visible thấp dù autovacuum hoạt động bình thường.

Trong workload như vậy, thiết kế covering index khổng lồ chưa chắc hiệu quả. Cần đo chi phí ghi và heap fetches thực tế.

### 22.4. VACUUM FULL có phải cách “đạt Index Only Scan” không?

`VACUUM FULL` viết lại bảng với cơ chế/khóa khác và không phải công cụ thông thường để làm Heap Fetches giảm. Trên production nó có thể chặn nhiều hoạt động và cần kế hoạch vận hành.

Để cải thiện VM thông thường, hãy đánh giá VACUUM/autovacuum trước, không dùng VACUUM FULL chỉ vì muốn một node plan đẹp.

## 23. Heap Fetches và buffer cache

Câu hỏi:

> Nếu `Heap Fetches: 1000` nhưng `Buffers: shared read=0`, có vấn đề hiệu năng không?

Có thể các heap pages đã nằm trong shared buffers nên không cần đọc từ ổ đĩa. Tuy nhiên, executor vẫn phải thực hiện các lần truy cập/kiểm tra visibility tại heap, tiêu thụ CPU và cache/buffer operations.

### 23.1. Hit không nghĩa là miễn phí

`shared hit` nghĩa là PostgreSQL truy cập block đã có trong shared buffer cache. Nó vẫn phát sinh công việc xử lý, nhưng thường rẻ hơn một read I/O chậm từ storage.

### 23.2. Heap Fetches không đủ để đo tổng I/O

Một query có Heap Fetches=0 vẫn cần index pages và VM pages. Nếu các trang ấy chưa ở cache, có thể có disk reads.

Một query có Heap Fetches cao nhưng nhiều shared hits cũng có thể nhanh trong điều kiện cache ấm.

Vì vậy, đo cùng:

- `Heap Fetches`.
- `Buffers`.
- `Execution Time`.
- Số hàng và vòng lặp.
- Tần suất thực thi trên workload.
- Đặc điểm storage/cache.

### 23.3. Thử nghiệm cold vs warm cache

Không nên xoá cache hệ điều hành hoặc khởi động lại production chỉ để so sánh. Có thể chạy query nhiều lần trong lab, xem xu hướng buffer hits và đo đa lần, nhưng phải ghi rõ trạng thái cache và môi trường.

## 24. Heap Fetches trong Nested Loop

Một `Index Only Scan` có thể nằm bên trong `Nested Loop`:

```text
Nested Loop
  -> Seq Scan on stores
  -> Index Only Scan on sales
       Index Cond: (store_id = stores.store_id)
       Heap Fetches: ...
```

Trong trường hợp đó, index node có thể chạy nhiều lần cho nhiều giá trị store_id từ phía ngoài.

### 24.1. Tại sao loops quan trọng?

Nếu inner node được gọi 100 lần, số rows và timing hiển thị của EXPLAIN cần được diễn giải theo quy tắc tổng/average của loại chỉ số. Không so trực tiếp mọi con số như thể node chạy một lần duy nhất.

`Heap Fetches` là thống kê truy cập heap của node trong quá trình thực thi, có thể tích lũy qua nhiều lần probe.

### 24.2. Một số hàng được truy vấn lặp đi lặp lại

Nếu inner scan nhiều lần tìm các index entries trỏ tới cùng heap pages chưa all-visible, việc kiểm tra visibility có thể lặp lại. Việc truy cập page trong cache không đồng nghĩa lần kiểm tra heap được loại bỏ.

### 24.3. Tối ưu có thể là giảm số probes

Trong một số workload, tối ưu join cardinality, giảm số dòng outer, chọn join khác hoặc bổ sung điều kiện truy cập có thể đem lại lợi ích lớn hơn chỉ cố làm `Heap Fetches` về 0.

## 25. SELECT COUNT(*) có thể dùng Index Only Scan không?

Có thể, nếu index phù hợp với điều kiện và planner thấy có lợi.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM ios270.sales
WHERE store_id = 42;
```

Câu SELECT trả **một dòng COUNT**, nhưng executor có thể phải kiểm tra nhiều index entries. Nếu VM không all-visible, `Heap Fetches` có thể lớn hơn 1 rất nhiều.

### 25.1. COUNT(*) không phải metadata chính xác không cần scan

Đối với một bảng PostgreSQL thông thường có MVCC, `COUNT(*)` chính xác phải xét các hàng có thể nhìn thấy theo snapshot. Database không thể chỉ nhìn một con số số lượng tổng hàng cập nhật toàn cục và trả ngay cho mọi transaction.

Một index-only scan có thể giảm heap I/O nhưng **vẫn phải duyệt những index entries phù hợp và xử lý visibility**.

### 25.2. COUNT(*) toàn bảng

```sql
SELECT COUNT(*)
FROM ios270.sales;
```

Planner có thể chọn Seq Scan, Parallel Seq Scan, Index Only Scan hoặc kế hoạch khác tùy chi phí. Đừng kỳ vọng vì bảng có PRIMARY KEY index mà `COUNT(*)` toàn bảng luôn được thực thi bằng index-only.

## 26. Partial index và khả năng Index Only Scan

Xét index chỉ cho những đơn PAID:

```sql
CREATE INDEX idx_ios270_sales_paid_time
ON ios270.sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents)
WHERE status = 'PAID';
```

Query:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE status = 'PAID'
  AND store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Vì query có predicate `status='PAID'`, planner có thể xem xét partial index khi chứng minh được query chỉ yêu cầu những hàng nằm trong index. Các cột cần **trả** ở query này cũng nằm trong index.

### 26.1. Tại sao không nên giả định planner luôn dùng partial index?

- Query phải hàm ý predicate của index.
- Prepared statement dùng generic plan có thể không chứng minh được điều kiện với tham số trạng thái thay đổi.
- Dữ liệu/query có thể không đủ chọn lọc.
- Index khác có thể rẻ hơn.
- Tỷ lệ all-visible thấp có thể làm giảm lợi ích index-only.

### 26.2. Partial index không tự chứa mọi dữ liệu có trong bảng

Index chỉ có những hàng thỏa predicate `status='PAID'`. Một query tìm cả trạng thái NEW/CANCELLED không thể chỉ đọc partial index này để lấy đầy đủ kết quả.

### 26.3. Partial index và UPDATE status

Nếu một sale đổi từ NEW sang PAID hoặc ngược lại, nó có thể đi vào/ra partial index và làm phát sinh index maintenance; đồng thời các heap pages bị ảnh hưởng có thể mất bit all-visible.

## 27. Expression index và giới hạn covering

Ví dụ:

```sql
CREATE TABLE ios270.contacts (
    contact_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email text NOT NULL,
    display_name text NOT NULL
);

CREATE INDEX idx_ios270_contacts_lower_email
ON ios270.contacts(lower(email));
```

Query:

```sql
SELECT lower(email)
FROM ios270.contacts
WHERE lower(email) = 'an@example.test';
```

Về ý tưởng, giá trị biểu thức `lower(email)` được lưu trong index. Tuy nhiên khả năng tạo kế hoạch index-only cho **expression indexes** còn phụ thuộc cách planner nhận ra biểu thức và các cột gốc cần thiết theo từng phiên bản/biểu thức.

### 27.1. Đừng suy luận index biểu thức tự bao phủ email gốc

Index `lower(email)` lưu giá trị biểu thức chuẩn hóa, không mặc nhiên đủ để trả lại **email nguyên bản**:

```sql
SELECT email, display_name
FROM ios270.contacts
WHERE lower(email) = 'an@example.test';
```

Với index chỉ chứa `lower(email)`, hai cột `email` và `display_name` cần xem lại yêu cầu covering/heap access. Nếu thật sự cần chúng và workload đáng giá, cân nhắc một thiết kế index khác; đừng thêm payload quá mức.

### 27.2. Một ví dụ covering bằng INCLUDE

Trong những phiên bản và kiểu dữ liệu hỗ trợ:

```sql
CREATE INDEX idx_ios270_contacts_lower_email_cover
ON ios270.contacts(lower(email))
INCLUDE (email, display_name);
```

Index này lưu thêm email gốc và tên để có thể phục vụ query cần các cột ấy. Nhưng nó lớn hơn, tăng chi phí ghi và vẫn cần VM để tránh heap fetches.

Việc expression index có được planner sử dụng hiệu quả theo dự đoán hay không cần kiểm tra với `EXPLAIN` trên server mục tiêu.

## 28. ORDER BY, LIMIT và khả năng dừng sớm

B-tree có thứ tự nên index-only scan rất phù hợp với một số query top-N:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 10;
```

Với index `(store_id,sold_at DESC,sale_id DESC) INCLUDE (amount_cents,...)`, PostgreSQL có thể:

1. Định vị nhóm store_id=42.
2. Duyệt entries theo sold_at/sale_id giảm dần.
3. Kiểm tra visibility qua VM, tra heap khi cần.
4. Trả đủ 10 hàng rồi dừng sớm.

### 28.1. LIMIT nhỏ không bảo đảm Heap Fetches nhỏ hơn 10

Nếu một số index entries trỏ tới tuples không phù hợp snapshot hoặc query có bộ lọc khác, executor có thể cần xét thêm ứng viên trước khi trả đủ 10 hàng. Số lần tra heap có thể vượt số rows cuối.

### 28.2. ORDER BY có thể đổi kế hoạch

Nếu query yêu cầu sắp thứ tự khác với index, planner có thể phải Sort. Một index-only scan không tự làm mọi cách sắp xếp trở nên miễn phí.

### 28.3. Pagination và keyset

Ví dụ:

```sql
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
  AND (sold_at, sale_id) <
      (TIMESTAMPTZ '2026-05-01 12:00:00+00', 10000)
ORDER BY sold_at DESC, sale_id DESC
LIMIT 20;
```

Điều kiện tuple có thể tận dụng B-tree theo khóa phù hợp cho keyset pagination. Các giá trị cursor phải lấy từ hàng cuối trang trước; hai literal trên chỉ là ví dụ.

Index-only vẫn phụ thuộc all-visible của heap pages.

## 29. Ảnh hưởng của RLS và quyền đọc

Khi PostgreSQL bật **Row-Level Security (RLS)**, các hàng một role được phép nhìn thấy/sửa phụ thuộc policy. Index-only scan không được vượt qua kiểm tra quyền và chính sách truy cập.

Ví dụ hệ thống nhiều tenant có:

```text
tenant_id, sale_id, sold_at, amount_cents
```

Query chỉ được đọc tenant hiện tại:

```sql
SELECT sale_id, sold_at, amount_cents
FROM tenant_sales
WHERE tenant_id = :authenticated_tenant_id
ORDER BY sold_at DESC
LIMIT 20;
```

Placeholder ở trên là cú pháp ứng dụng, không phải cú pháp tham số trực tiếp trong psql.

### 29.1. Index phục vụ đúng phạm vi tenant

Một index như:

```sql
CREATE INDEX ...
ON tenant_sales(tenant_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents);
```

có thể hữu ích vì tenant_id ở cột dẫn đầu, query có equality rồi sắp theo thời gian.

### 29.2. Không thiết kế index thay cho bảo mật

Index chỉ là cấu trúc truy cập; nó không tự đặt quy tắc tenant nào được thấy hàng nào. RLS, quyền SQL và ngữ cảnh tenant đáng tin cậy vẫn phải được thiết kế đúng.

Nếu RLS policy có thêm biểu thức/cột cần đánh giá, planner có thể cần kế hoạch khác hoặc việc đánh giá không còn hoàn toàn được phục vụ từ một index đơn giản.

## 30. Index Only Scan trong Java/JDBC

Ứng dụng Java không phải yêu cầu một loại index scan cụ thể. Nó gửi SQL; PostgreSQL planner chọn kế hoạch phù hợp.

Ví dụ JDBC:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;

public final class RecentSaleRepository {
    public record Sale(
        long id,
        OffsetDateTime soldAt,
        long amountCents,
        String status
    ) {}

    public List<Sale> findRecentByStore(
            Connection connection,
            int storeId,
            int limit) throws SQLException {

        if (limit <= 0 || limit > 500) {
            throw new IllegalArgumentException("limit ngoài phạm vi");
        }

        String sql = """
            SELECT sale_id, sold_at, amount_cents, status
            FROM ios270.sales
            WHERE store_id = ?
            ORDER BY sold_at DESC, sale_id DESC
            LIMIT ?
            """;

        List<Sale> result = new ArrayList<>();

        try (PreparedStatement ps = connection.prepareStatement(sql)) {
            ps.setInt(1, storeId);
            ps.setInt(2, limit);

            try (ResultSet rs = ps.executeQuery()) {
                while (rs.next()) {
                    result.add(new Sale(
                        rs.getLong("sale_id"),
                        rs.getObject(
                            "sold_at", OffsetDateTime.class),
                        rs.getLong("amount_cents"),
                        rs.getString("status")
                    ));
                }
            }
        }

        return result;
    }
}
```

Các điểm chính:

- Query **liệt kê các cột cần trả**, không `SELECT *`.
- `WHERE store_id=?` và ORDER BY khớp thứ tự key của index mẫu.
- `LIMIT` giúp tránh truyền quá nhiều dữ liệu.
- Driver không bảo đảm server dùng `Index Only Scan`; phải quan sát kế hoạch trên database.
- Khả năng dùng Index Only Scan phụ thuộc VM, không phụ thuộc một cấu hình đặc biệt trong JDBC.

### 30.1. Prepared statements và generic plans

Một prepared statement có thể được PostgreSQL lập kế hoạch dưới dạng custom/generic tùy hoàn cảnh. Nếu tham số có phân bố không đều giữa các store, plan phù hợp cho một store có thể khác store khác.

Không mặc định cùng SQL dạng `store_id = ?` sẽ luôn chọn cùng node hoặc cùng số Heap Fetches cho mọi tham số.

### 30.2. Đừng tối ưu bằng cách thêm payload không cần thiết

Nếu API thật chỉ cần `sale_id`, `sold_at` và `amount_cents`, không nên thêm `status` hoặc `note` vào INCLUDE chỉ để “dự phòng”. Mỗi payload có chi phí index maintenance.

## 31. Bài toán thiết kế: index nhỏ hay covering index?

Giả sử hai index khả dĩ:

**Index A — nhỏ:**

```sql
CREATE INDEX idx_a
ON sales(store_id, sold_at DESC);
```

**Index B — bao phủ hơn:**

```sql
CREATE INDEX idx_b
ON sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents, status);
```

So sánh:

| Tiêu chí | Index A | Index B |
|---|---|---|
| Kích thước index | Thường nhỏ hơn | Thường lớn hơn |
| Khóa để tìm store/time | Có | Có |
| Thứ tự tie-break sale_id | Không lưu như key tường minh | Có |
| Trả amount/status từ index | Không | Có |
| Cơ hội Index Only Scan cho query trả amount/status | Thấp với index này | Có |
| Chi phí update amount/status | Ít ảnh hưởng trực tiếp đến index này | Phải duy trì payload liên quan |
| Lợi ích khi VM all-visible cao | Có thể vẫn cần heap để lấy payload | Có thể bỏ nhiều heap fetches |
| Lợi ích khi VM all-visible thấp | Index Scan có thể phù hợp | Covering index không tránh được nhiều visibility heap fetches |

### 31.1. Đừng chỉ đếm số Heap Fetches để quyết định

Một covering index có Heap Fetches ít hơn nhưng lớn hơn nhiều, làm truy vấn khác và update chậm hơn, chưa chắc tốt hơn cho toàn hệ thống.

Nên đánh giá:

- P95/P99 read latency.
- Throughput query.
- P95/P99 write latency.
- Storage và WAL.
- Autoanalyze/vacuum behavior.
- Tỷ lệ index-only thực tế theo workload.
- Mức all-visible và HEAP fetches.
- Khả năng duy trì khi schema thêm cột.

### 31.2. Một index không phục vụ mọi đường truy vấn

Truy vấn lọc `amount_cents > ?` có thể cần amount làm key. Truy vấn lọc store và sắp thời gian cần store/time. Truy vấn đọc note có thể chấp nhận heap access.

Không nên cố tạo một index khổng lồ chứa mọi cột cho mọi API.

## 32. Cách đo thử có kiểm soát

### 32.1. Ghi baseline

Chạy:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;
```

Ghi:

```text
Bước A: Sau INSERT
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Bước B: Sau VACUUM
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Bước C: Sau UPDATE note
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:

Bước D: Sau VACUUM lần hai
  Plan:
  Heap Fetches:
  Buffers:
  Actual rows:
  Execution Time:
```

### 32.2. Nếu planner không chọn Index Only Scan?

Điều đó là kết quả có ý nghĩa. Trước hết xem:

- Query có được index bao phủ không?
- Điều kiện và ORDER BY có khớp keys?
- Bảng có quá nhỏ hoặc query trả nhiều hàng?
- Statistics có đủ mới?
- VM có nhiều pages all-visible không?
- Có index khác rẻ hơn?

Trong lab, có thể dùng tham số planner **tạm thời** để so sánh, ví dụ:

```sql
BEGIN;
SET LOCAL enable_seqscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents, status
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 100;

ROLLBACK;
```

`enable_seqscan=off` chỉ làm Seq Scan kém được ưu tiên, **không buộc** Index Only Scan và không bảo đảm một kế hoạch hợp lệ dùng index sẽ xuất hiện. Không chỉnh cờ planner toàn production như một giải pháp lâu dài.

### 32.3. Vì sao không nên “benchmark” trong một transaction chứa VACUUM?

`VACUUM` thông thường không chạy trong explicit transaction block. Thí nghiệm nên tách:

1. Câu DML hoàn tất/commit.
2. VACUUM độc lập.
3. EXPLAIN SELECT.
4. UPDATE độc lập/commit.
5. EXPLAIN SELECT.

Điều này cũng giúp tránh chính transaction thử nghiệm đang mở cản trở việc đánh dấu pages all-visible.

### 32.4. Không đo bằng một lần chạy duy nhất

Buffer cache và tải hệ thống có thể khiến timing dao động. Khi cần kết luận hiệu năng, chạy nhiều lần trên dữ liệu đại diện và ghi điều kiện môi trường, đồng thời giữ nguyên SQL/result semantics.

**Đây là hướng dẫn phương pháp quan sát**, không phải bước QA nội dung hoặc kết quả benchmark đã được thực thi.

## 33. Các lỗi diễn giải thường gặp

### Lỗi 1 — “Index Only Scan thì Heap Fetches phải bằng 0”

Sai. VM pages chưa all-visible có thể buộc executor tra heap để xác minh visibility.

### Lỗi 2 — “Tôi tạo INCLUDE đủ cột rồi, chắc chắn không cần heap”

Chưa đủ. Cần support từ index method, planner chọn Index Only Scan và VM xác nhận visibility phù hợp.

### Lỗi 3 — “Heap Fetches=100 nghĩa 100 lần đọc đĩa”

Sai. Có thể 100 lần tra tuple trên ít heap pages, nhiều lần gặp page đã có trong shared buffers.

### Lỗi 4 — “Heap Fetches là số rows trả về”

Sai. Visibility checks có thể cần thiết cả cho ứng viên không được trả và qua các loops.

### Lỗi 5 — “VACUUM luôn làm Heap Fetches=0”

Không chắc. DML mới, transaction dài, pages chưa đủ điều kiện hoặc plan khác có thể khiến kết quả không như kỳ vọng.

### Lỗi 6 — “ANALYZE có tác dụng như VACUUM lên VM”

Sai. ANALYZE thu thập thống kê; VACUUM đảm nhiệm việc liên quan dead tuples/visibility map.

### Lỗi 7 — “UPDATE cột không ở index không ảnh hưởng index-only scan”

Sai. UPDATE thay đổi heap/MVCC và có thể xóa bit all-visible.

### Lỗi 8 — “HOT update bảo đảm không còn heap fetch”

Sai. HOT tối ưu index maintenance, không tự giữ all-visible cho pages được sửa.

### Lỗi 9 — “Có Heap Fetches=0 thì query không đọc trang nào”

Sai. Nó vẫn cần index/VM pages và có thể cần các node khác đọc dữ liệu.

### Lỗi 10 — “Buffers shared hit là không có chi phí”

Sai. Shared hit là truy cập buffer cache, vẫn có CPU và memory access.

### Lỗi 11 — “Index Only Scan lúc nào cũng nhanh hơn Index Scan”

Sai. Plan chi phí phụ thuộc dữ liệu, visibility, index size và các thao tác khác.

### Lỗi 12 — “Tạo index trên (a,b) INCLUDE(c) nghĩa c dùng cho range scan”

Sai. INCLUDE payload không tham gia thứ tự khóa của B-tree.

### Lỗi 13 — “SELECT * không ảnh hưởng chỉ mục bao phủ”

Sai. Một cột không có trong index làm query không được index đó bao phủ.

### Lỗi 14 — “COUNT(*) trả một hàng nên Heap Fetches không vượt 1”

Sai. Aggregate trả một hàng nhưng node index dưới nó có thể kiểm tra hàng nghìn tuples.

### Lỗi 15 — “relallvisible là số Heap Fetches tối đa”

Sai. relallvisible đếm/ước lượng pages toàn relation, Heap Fetches là những lần kiểm tra visibility ở node.

### Lỗi 16 — “Index Only Scan trên expression index luôn được planner tối ưu như index cột thường”

Không bảo đảm. Khả năng xác định các cột/biểu thức có đủ trong index phụ thuộc phiên bản và cấu trúc query.

### Lỗi 17 — “Partial index PAID dùng được cho mọi prepared query status=$1”

Không chắc. Planner phải chứng minh WHERE hàm ý predicate và generic plan không biết mọi giá trị tham số đều PAID.

### Lỗi 18 — “Nhiều INCLUDE luôn tốt hơn”

Sai. Index lớn hơn, tốn ghi và có thể giảm lợi ích của HOT/deduplication.

### Lỗi 19 — “EXPLAIN ANALYZE chỉ dự đoán, không chạy query”

Sai. Nó **thực thi** query để đo. Với DML có tác dụng thay đổi dữ liệu, phải rất cẩn trọng.

### Lỗi 20 — “Để giảm Heap Fetches thì tắt autovacuum”

Sai. Điều đó thường khiến visibility maintenance kém hơn và gây rủi ro nghiêm trọng.

## 34. Bài tập thực hành có lời giải

Bài tập giả định đã có schema `ios270`. Các ví dụ UPDATE/VACUUM chỉ chạy trong database lab; dữ liệu có thể khác nếu đã thực hiện các bài trước.

### Bài 1. Index Only Scan có nghĩa là không đọc heap tuyệt đối?

**Đáp án:** Không. Nó lấy cột từ index, nhưng vẫn có thể tra heap để kiểm tra MVCC khi heap page không all-visible.

### Bài 2. Vì sao một index entry không đủ quyết định visibility?

**Đáp án:** Index không lưu đầy đủ thông tin về transaction/phiên bản tuple cần cho snapshot; MVCC visibility thuộc heap, trừ khi VM xác nhận cả page all-visible.

### Bài 3. Bit VM nào là then chốt?

**Đáp án:** `all-visible`. Bit `all-frozen` phục vụ các mục đích freezing khác, không phải điều kiện bắt buộc để skip heap trong index-only scan.

### Bài 4. VM theo hàng hay theo page?

**Đáp án:** theo heap page. Một UPDATE có thể khiến nhiều hàng cùng page phải tra heap khi thực thi index-only scans sau đó.

### Bài 5. Có index `(store_id,sold_at)`; query trả `note` có index-only được không?

**Đáp án:** không qua index ấy nếu `note` không được lưu trong index. Cần heap hoặc một index/plan khác.

### Bài 6. Viết covering index cho query store/time/amount

```sql
CREATE INDEX idx_ios270_exercise_cover
ON ios270.sales(store_id, sold_at DESC, sale_id DESC)
INCLUDE (amount_cents);
```

**Giải thích:** index chứa key dùng cho WHERE/ORDER BY và amount để trả. Nếu query còn trả `status`, index bài tập này chưa chứa status.

### Bài 7. Truy vấn xem Heap Fetches

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT sale_id, sold_at, amount_cents
FROM ios270.sales
WHERE store_id = 42
ORDER BY sold_at DESC, sale_id DESC
LIMIT 25;
```

**Đáp án:** nếu planner chọn Index Only Scan, đọc dòng `Heap Fetches: ...` trong node tương ứng.

### Bài 8. Nếu plan là Index Scan, tại sao không thấy dòng Heap Fetches?

**Đáp án:** `Heap Fetches` là thuộc tính quan sát đặc trưng của node Index Only Scan; với Index Scan, cách hiển thị và truy cập heap khác, không nên suy luận không có heap access khi không thấy dòng ấy.

### Bài 9. Sau VACUUM, Heap Fetches giảm vì sao?

**Đáp án:** VACUUM có thể đánh dấu thêm heap pages all-visible, nên Index Only Scan không cần kiểm tra riêng các tuples ở những pages ấy.

### Bài 10. Vì sao sau UPDATE note Heap Fetches lại tăng?

**Đáp án:** UPDATE tác động heap/MVCC, có thể xóa all-visible bit của các pages chứa hàng được sửa dù note không nằm trong index.

### Bài 11. HOT update có làm Heap Fetches chắc chắn về 0?

**Đáp án:** không. HOT và VM giải quyết các vấn đề khác nhau.

### Bài 12. Heap Fetches=500 có phải 500 disk reads?

**Đáp án:** không. Có thể nhiều lần kiểm tra tuple ở cùng page đã cache; cần xem BUFFERS để hiểu I/O.

### Bài 13. Heap Fetches=0 có thể có shared read=5 không?

**Đáp án:** có. Index/VM pages có thể cần được đọc, dù không cần tra heap cho visibility.

### Bài 14. COUNT(*) WHERE store_id=42 trả mấy hàng?

**Đáp án:** một hàng COUNT; node quét index bên dưới vẫn có thể xử lý nhiều entries và nhiều heap fetches.

### Bài 15. Nếu SELECT * thì chuyện gì xảy ra?

**Đáp án:** cột `note` không nằm trong covering index, nên index hiện tại không còn chứa đủ dữ liệu trả; planner phải dùng heap hoặc lựa chọn khác.

### Bài 16. INCLUDE khác key column ra sao?

**Đáp án:** INCLUDE là payload, không tham gia thứ tự tìm khóa; key columns dùng để định vị/sắp xếp theo B-tree.

### Bài 17. Xem relallvisible

```sql
SELECT relpages, relallvisible
FROM pg_class
WHERE oid = 'ios270.sales'::regclass;
```

**Đáp án:** hai số ở cấp page của relation; không phải số hàng trả về hay heap fetches của một query.

### Bài 18. Xem VM bằng extension

```sql
SELECT
    COUNT(*) FILTER (WHERE all_visible) AS visible_pages,
    COUNT(*) FILTER (WHERE NOT all_visible) AS other_pages
FROM pg_visibility_map('ios270.sales'::regclass);
```

**Đáp án:** cần extension `pg_visibility` đã được cài và quyền thích hợp; số đếm là pages, không phải tuples.

### Bài 19. Một page chứa 80 tuple, một tuple bị UPDATE thì sao?

**Đáp án:** bit all-visible của page có thể bị xóa; index-only scans các tuple khác trong cùng page có thể cũng phải kiểm tra heap.

### Bài 20. Tại sao một bảng read-mostly phù hợp Index Only Scan hơn?

**Đáp án:** những pages ít bị thay đổi có cơ hội được VACUUM đánh dấu all-visible và giữ trạng thái đó lâu hơn.

### Bài 21. Có nên INCLUDE cột note dài để tránh mọi heap read?

**Đáp án:** không mặc định. Index có thể phình to/tăng chi phí ghi, và VM vẫn có thể bắt phải đọc heap. Cần đo workload trước.

### Bài 22. Parallel Index Only Scan có thể có Heap Fetches không?

**Đáp án:** có. Song song hóa không loại điều kiện MVCC; các workers vẫn cần kiểm tra visibility phù hợp.

### Bài 23. Partial index chỉ PAID có dùng cho query status='NEW' không?

**Đáp án:** không. Index chỉ chứa tập PAID nên không thể cung cấp mọi hàng NEW.

### Bài 24. Prepared generic plan có chắc dùng partial index status='PAID' khi status=$1 không?

**Đáp án:** không. Generic plan phải đúng cho mọi giá trị tham số, nên không tự chứng minh $1 luôn là PAID.

### Bài 25. Nếu Heap Fetches giảm nhưng Execution Time tăng thì sao?

**Đáp án:** phân tích buffers, cache, plans, loops, rows, hệ thống đang tải và chi phí index; không kết luận Index Only Scan sai chỉ từ hai con số.

### Bài 26. Vì sao VACUUM nên chạy sau COMMIT trong lab?

**Đáp án:** VACUUM thông thường không chạy trong explicit transaction block; dữ liệu chưa commit/transaction đang mở cũng có thể ảnh hưởng việc đánh dấu VM.

### Bài 27. Một query có Index Only Scan nhưng Filter bỏ nhiều rows

**Đáp án:** node vẫn có thể đọc nhiều index entries hoặc kiểm tra thêm visibility cho các ứng viên. Cần xem Index Cond vs Filter, cấu trúc index và dữ liệu; không chỉ đếm rows cuối.

### Bài 28. Cách nào chứng minh cover index thực sự có lợi cho hệ thống?

**Đáp án:** đo EXPLAIN ANALYZE BUFFERS và latency đọc trên dữ liệu đại diện, đồng thời đo storage, WAL, update throughput, autovacuum và tác động tới query khác.

### Bài 29. Vì sao không nên dựa duy nhất vào relallvisible?

**Đáp án:** đó là thông tin cấp relation/ước lượng, còn query chỉ truy cập một tập pages; tỷ lệ all-visible toàn bảng không phản ánh chính xác mọi nhóm store_id.

### Bài 30. Lựa chọn nào khi workload UPDATE liên tục và Heap Fetches luôn cao?

**Đáp án:** đánh giá sự phù hợp của covering index, giảm payload/chi phí cập nhật nếu cần, điều chỉnh maintenance theo dữ liệu thực, phân tách workload read-mostly và hot data khi nghiệp vụ cho phép. Không cố ép Index Only Scan bằng mọi giá.

## 35. Sơ đồ chẩn đoán nhanh

```text
Query chậm hoặc vẫn đọc heap nhiều
                |
                v
        EXPLAIN (ANALYZE, BUFFERS)
                |
         +------+-------+
         |              |
      Index Only       Không dùng
         Scan          Index Only
         |              |
         v              v
    Heap Fetches?    Cột/biểu thức của query
         |           có đủ trong index không?
    +----+----+         |
    |         |         +-- Không --> cân nhắc index/key/INCLUDE
    0        Cao        |
    |         |         +-- Có ----> kiểm tra planner cost,
    |         v                     selectivity, statistics,
    |    VM all-visible?            ORDER BY, index method
    |         |
    |    +----+----+
    |    |         |
    |   Thấp      Cao trên toàn bảng
    |    |         |
    |    v         v
    |  Xem hoạt động DML,    Query có tập pages
    |  transaction dài,       đặc thù? Thống kê
    |  VACUUM/autovacuum      có phản ánh đúng không?
    |         |
    +---------+
              |
              v
    So sánh rows, loops, BUFFERS,
    latency, cache và chi phí ghi
              |
              v
    Quyết định tối ưu theo workload,
    không theo một dòng EXPLAIN
```

## 36. Checklist thực tế khi tối ưu Index Only Scan

| Câu hỏi | Vì sao phải kiểm tra? |
|---|---|
| Query có thật sự cần mọi cột đang SELECT không? | SELECT * có thể làm mất covering |
| B-tree index có đủ khóa/payload không? | Không đủ cột thì phải lấy từ heap |
| Key columns có phù hợp WHERE/ORDER BY? | Khả năng định vị và dừng sớm |
| INCLUDE có quá lớn/đổi thường xuyên không? | Chi phí ghi và kích thước index |
| Planner có chọn Index Only Scan? | Khả năng kỹ thuật chưa đủ để bảo đảm kế hoạch |
| Heap Fetches là bao nhiêu? | Mức phải kiểm tra heap thực tế |
| Heap Fetches thay đổi sau VACUUM/UPDATE thế nào? | Đánh giá tác động visibility map |
| relallvisible và VM đang ở trạng thái gì? | Đánh giá tỷ lệ pages all-visible |
| Có long-running transactions không? | Có thể ảnh hưởng cleanup/visibility |
| Tỷ lệ HOT update có thay đổi sau INCLUDE không? | Index maintenance trade-off |
| Buffers shared hit/read thế nào? | Không đánh đồng fetches với disk reads |
| Query có nhiều loops không? | Tránh so nhầm số fetches và rows |
| Cache đã ấm hay lạnh? | Tránh kết luận timing sai |
| Statistics có mới và đại diện không? | Planner cost/row estimates |
| Có partial predicate/expression không? | Query phải khớp index logic |
| Có tác động RLS/tenant filter không? | Tính đúng và khả năng covering |
| Có đang cố ép planner bằng cờ enable_* không? | Không nên dùng làm giải pháp production |
| Read latency có đáng kể so với write overhead? | Đánh giá lợi ích thực tế |
| Có kế hoạch VACUUM/autovacuum phù hợp không? | Duy trì visibility và sức khỏe bảng |
| Đã test trên workload thực, không chỉ fixture bé? | Tránh tối ưu sai môi trường |

## 37. Các tài liệu PostgreSQL nên đọc

Các nguồn tham khảo chính thức theo phiên bản server:

- [Index-Only Scans and Covering Indexes](https://www.postgresql.org/docs/current/indexes-index-only-scans.html): điều kiện Index Only Scan, visibility map, INCLUDE, MVCC và hạn chế.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): các node và thống kê `EXPLAIN ANALYZE`.
- [Routine Vacuuming](https://www.postgresql.org/docs/current/routine-vacuuming.html): vòng đời VACUUM, cập nhật thống kê, dead tuples và bảo trì.
- [MVCC Introduction](https://www.postgresql.org/docs/current/mvcc-intro.html): vì sao nhiều phiên bản hàng có thể tồn tại.
- [Visibility Map](https://www.postgresql.org/docs/current/storage-vm.html): cấu trúc visibility map trong lưu trữ.
- [pg_visibility](https://www.postgresql.org/docs/current/pgvisibility.html): quan sát visibility map khi extension/permission cho phép.
- [Index Types](https://www.postgresql.org/docs/current/indexes-types.html): khả năng của các phương pháp index khác nhau.
- [CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html): cú pháp key columns, INCLUDE, partial/expression indexes.
- [Monitoring Statistics](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_user_tables` và các counters.
- [HOT Updates](https://www.postgresql.org/docs/current/storage-hot.html): cách HOT giảm một phần chi phí duy trì index.

Một số khả năng và cách hiển thị plan có thể khác theo phiên bản. Kiểm tra:

```sql
SHOW server_version;
SHOW transaction_isolation;
```

trước khi áp dụng đặc điểm vào hệ thống thật.

## 38. Tổng kết

Một `Index Only Scan` tốt không đơn giản là “đã thêm đầy đủ cột vào index”.

Nó cần một chuỗi điều kiện:

```text
Query chỉ yêu cầu các cột index có thể cung cấp
                     |
                     v
Index method/opclass hỗ trợ lấy giá trị từ index
                     |
                     v
Planner đánh giá index-only scan đủ rẻ để chọn
                     |
                     v
Executor đọc index entry và kiểm tra VM
                     |
          +----------+-----------+
          |                      |
    all-visible = 1        all-visible = 0
          |                      |
          v                      v
    Không tra heap        Phải tra heap
    để kiểm tra           để kiểm tra
    visibility            visibility
          |                      |
          +----------+-----------+
                     |
                     v
             Trả hàng phù hợp
```

Các nguyên tắc cần nhớ:

1. **Index Only Scan vẫn có thể đọc heap.** Tên node không bảo đảm `Heap Fetches: 0`.
2. **Covering index là điều kiện về dữ liệu cột.** Key columns và INCLUDE payload có vai trò khác nhau.
3. **Visibility map quyết định việc bỏ qua heap cho MVCC.** Bit all-visible theo heap page là then chốt.
4. **VACUUM có thể làm giảm Heap Fetches**, nhưng DML và transaction đang hoạt động có thể khiến bits all-visible không được thiết lập hoặc bị xóa.
5. **UPDATE cột không nằm trong index vẫn ảnh hưởng hiệu quả index-only** vì heap visibility thay đổi.
6. **HOT update không đồng nghĩa all-visible.** HOT tối ưu đường ghi index, không tự loại heap fetch.
7. **Heap Fetches không phải số heap pages hay disk reads.** Hãy xem BUFFERS, rows, loops và thời gian thực thi.
8. **COUNT(*) một hàng kết quả không có nghĩa chỉ xét một tuple.** Executor vẫn phải duyệt tập phù hợp với snapshot.
9. **Index lớn có chi phí duy trì.** Không INCLUDE mọi cột chỉ để giảm một chỉ số.
10. **Planner có quyền chọn Seq Scan/Index Scan/Bitmap Scan** nếu tổng chi phí tốt hơn.
11. **Benchmark phải có điều kiện rõ ràng**: trước/sau VACUUM/UPDATE, cùng query, dữ liệu phù hợp, buffers/cache và write overhead.
12. **Mục tiêu cuối cùng là hiệu năng workload và tính đúng**, không phải một kế hoạch EXPLAIN trông “đẹp”.

**Một câu để nhớ:** *Index Only Scan* có thể lấy dữ liệu từ index, nhưng chỉ khi visibility map xác nhận heap page đã **all-visible** thì PostgreSQL mới bỏ qua được lần tra heap để kiểm tra phiên bản hàng; số lần chưa bỏ qua được chính là tín hiệu cần đọc ở **`Heap Fetches`**.

