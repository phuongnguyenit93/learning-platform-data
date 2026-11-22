# Visibility map, freezing và ý nghĩa với truy vấn trong PostgreSQL

PostgreSQL sử dụng **MVCC (Multi-Version Concurrency Control)** để cho phép nhiều transaction đọc và ghi đồng thời mà không bắt mọi câu `SELECT` phải chờ mọi câu `UPDATE`. Khi một hàng được sửa, PostgreSQL thường tạo một **phiên bản hàng mới** trong heap và giữ phiên bản cũ cho những transaction vẫn có thể cần nhìn thấy nó.

Mô hình này rất hữu ích cho concurrency, nhưng đặt ra ba câu hỏi vận hành quan trọng:

1. Làm cách nào PostgreSQL biết một trang heap có thể được coi là **hiển thị với mọi transaction** mà không phải kiểm tra từng tuple?
2. Làm cách nào PostgreSQL giữ các hàng tồn tại lâu năm mà vẫn an toàn khi **transaction ID (XID)** được tái sử dụng theo vòng?
3. Vì sao một truy vấn có index bao phủ đầy đủ cột vẫn có thể cần đọc **heap**, và tại sao `VACUUM` lại cải thiện tốc độ một số truy vấn `Index Only Scan`?

Hai cơ chế kết nối ba câu hỏi này là **visibility map (VM)** và **freezing**.

- **Visibility map** lưu trạng thái theo **trang heap**: trang có toàn bộ tuple nhìn thấy được với mọi transaction hay không, và các tuple trên trang đã được đóng băng về mặt XID/MultiXact hay chưa.
- **Freezing** là một phần của bảo trì MVCC nhằm ngăn vấn đề **transaction ID wraparound** và giúp các trang ổn định được đánh dấu `all-frozen`.
- **Index-only scan** có thể dựa trên cờ `all-visible` của trang heap để trả dữ liệu từ index mà không phải truy cập heap để kiểm tra visibility cho từng index entry.

Bài học thuộc chương **MVCC**, module **Database Engine Relational PostgreSQL**. Chúng ta sẽ xây dựng trực giác đúng, xem các câu SQL quan sát hệ thống, làm thí nghiệm trên một bảng riêng và hiểu khi nào việc tối ưu `VACUUM` thực sự giúp ích cho truy vấn.

---

## 1. Ôn lại MVCC: một hàng logic có thể có nhiều phiên bản vật lý

Xét bảng:

~~~sql
CREATE TABLE demo_account (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(12, 2) NOT NULL
);

INSERT INTO demo_account(account_id, balance)
VALUES (101, 1000.00);
~~~

Sau khi một transaction chạy:

~~~sql
UPDATE demo_account
SET balance = 1200.00
WHERE account_id = 101;
~~~

PostgreSQL không nhất thiết sửa trực tiếp bytes của một tuple cũ tại đúng chỗ. Thông thường, `UPDATE` tạo phiên bản tuple mới; phiên bản cũ còn tồn tại một thời gian để phục vụ MVCC và được thu dọn khi không transaction nào còn cần.

Mô hình khái niệm:

~~~text
Hàng logic: account_id = 101

Phiên bản cũ: balance=1000
    xmin = transaction đã tạo
    xmax = transaction cập nhật/xóa (khi thích hợp)

Phiên bản mới: balance=1200
    xmin = transaction tạo phiên bản mới
    xmax = chưa bị xóa/cập nhật (khi thích hợp)
~~~

`xmin` và `xmax` là các trường hệ thống liên quan transaction visibility; chúng không phải dữ liệu nghiệp vụ và không nên được dùng thay cho version do ứng dụng quản lý.

Với các snapshot khác nhau, PostgreSQL có thể quyết định phiên bản nào được nhìn thấy. Vì vậy chỉ có **một hàng logic**, nhưng trong heap có thể còn các phiên bản vật lý chưa được thu dọn.

### 1.1. Transaction đã COMMIT không có nghĩa VACUUM đã chạy

Sau khi một UPDATE commit:

- Phiên bản mới trở nên nhìn thấy với những snapshot phù hợp.
- Phiên bản cũ có thể chưa thể thu dọn nếu transaction khác vẫn cần.
- Ngay cả khi đã có thể thu dọn, phiên bản cũ có thể còn chờ `VACUUM` hoặc cơ chế pruning phù hợp.
- Trạng thái visibility map của trang có thể đã bị xóa cờ `all-visible` do thay đổi.

Đây là lý do **commit**, **dọn tuple chết**, **đánh dấu all-visible** và **freeze XID** là những sự kiện khác nhau.

## 2. Trang heap là đơn vị quan trọng của visibility map

PostgreSQL lưu dữ liệu bảng trong các **heap pages**. Kích thước trang phổ biến là **8 KiB** trong bản build mặc định, nhưng nên kiểm tra cấu hình thực tế:

~~~sql
SHOW block_size;
~~~

Một trang có thể chứa nhiều tuple và nhiều phiên bản của các hàng khác nhau.

Ví dụ minh họa:

~~~text
Heap relation: product

Page 0    [tuple A] [tuple B] [tuple C]
Page 1    [tuple D] [tuple E] [tuple F]
Page 2    [tuple G] [tuple H] [tuple I]
...
~~~

Visibility map không lưu một dòng cho từng hàng SQL. Nó lưu **một cặp cờ cho từng trang heap**.

Điều này dẫn đến một hệ quả quan trọng:

> Chỉ một thay đổi vào một tuple trên một trang có thể làm trang đó không còn đủ điều kiện `all-visible`, dù hầu hết tuple còn lại vẫn đã commit và có thể đọc bình thường.

Các index entry trỏ tới tuple trên trang này có thể lại cần kiểm tra visibility trong heap.

## 3. Visibility map là gì?

**Visibility map** là một fork phụ của một heap relation, dùng để ghi trạng thái visibility/freezing theo trang. Trong các phiên bản PostgreSQL hiện đại, nó có **hai bit cho mỗi trang heap**:

1. **`all-visible`**: tất cả tuple liên quan trên trang được biết là nhìn thấy với mọi transaction theo nghĩa MVCC phù hợp; index-only scan có thể tận dụng thông tin này.
2. **`all-frozen`**: những thông tin transaction liên quan trên trang đã đạt trạng thái frozen phù hợp, nên trang không cần xử lý đóng băng bổ sung cho các phiên bản hiện có.

Sơ đồ:

~~~text
                       Heap
             +----------+----------+
             |                     |
          Page 0                 Page 1
             |                     |
             v                     v
        Visibility map (VM)

        Page 0: all_visible = 1
                all_frozen  = 1

        Page 1: all_visible = 0
                all_frozen  = 0
~~~

Một trang **all-frozen** cũng được xem là **all-visible**. Ngược lại, một trang **all-visible** chưa chắc đã **all-frozen**.

### 3.1. Bảng phân biệt hai cờ

| Trạng thái | Nghĩa chính | Hệ quả quan trọng |
|---|---|---|
| `all_visible=0` | Không có bảo đảm trang được nhìn thấy với mọi transaction | Index-only scan có thể phải truy cập heap |
| `all_visible=1, all_frozen=0` | Trang đã đủ điều kiện all-visible nhưng còn thông tin XID/MultiXact cần freeze về sau | Index-only scan có thể tránh heap fetch; VACUUM sau này có thể cần freeze |
| `all_visible=1, all_frozen=1` | Trang all-visible và đã frozen theo quy tắc áp dụng | Hữu ích cho cả index-only scan và tối ưu VACUUM chống wraparound |
| `all_visible=0, all_frozen=1` | Không phải trạng thái VM hợp lệ cần mong đợi | `all-frozen` kéo theo `all-visible` |

**Không đồng nhất hai cờ.** `all-visible` phục vụ câu hỏi về visibility hiện thời cho cả trang; `all-frozen` phục vụ thêm câu hỏi vòng đời transaction ID.

## 4. VM nằm ở đâu và khác gì heap/index?

PostgreSQL lưu một relation qua các fork tệp, phổ biến có:

- **Main fork:** dữ liệu chính của heap hoặc index.
- **FSM (Free Space Map):** thông tin xấp xỉ về không gian trống có thể tái sử dụng trên các trang.
- **VM (Visibility Map):** thông tin `all-visible`/`all-frozen` cho heap pages.

Một tên file vật lý có thể có hậu tố như `_fsm` hoặc `_vm`, nhưng ứng dụng bình thường không nên truy cập trực tiếp những tệp đó. PostgreSQL quản lý chúng và ghi WAL/duy trì tính nhất quán theo cơ chế nội bộ.

### 4.1. VM không phải index

Visibility map:

- Không ánh xạ khóa nghiệp vụ tới vị trí hàng.
- Không giúp tìm SKU, email hay khoảng thời gian theo nghĩa B-tree.
- Không thay thế primary key, unique constraint hoặc một index thực tế.
- Chỉ giúp engine biết **một trang heap có an toàn để bỏ qua một số bước kiểm tra hay không**.

Index và VM phối hợp:

~~~text
B-tree Index
  |
  +--> index entry chứa khóa/cột được INCLUDE
  |
  +--> TID trỏ tới heap page
           |
           +--> Hỏi VM: trang all-visible?
                    |
                    +-- YES -> có thể trả từ index
                    |          mà không truy cập heap
                    |          để xác minh visibility
                    |
                    +-- NO  -> phải đọc heap và
                               kiểm tra tuple visibility
~~~

Điều kiện “có thể trả từ index” chỉ đúng khi index method hỗ trợ index-only scan và index chứa đủ thông tin cho truy vấn. VM không làm một index thiếu cột bỗng trở thành covering index.

## 5. “Visible với mọi transaction” không phải “hàng đã commit”

Một tuple đã commit có thể nhìn thấy với một snapshot, nhưng **không nhất thiết** nhìn thấy với tất cả snapshot còn đang hoạt động.

Ví dụ:

~~~text
T1: transaction A bắt đầu và giữ snapshot cũ.
T2: transaction B INSERT hàng mới.
T3: transaction B COMMIT.
T4: transaction A vẫn có thể không thấy hàng mới,
    tùy isolation/snapshot.
~~~

Vì vậy “B đã commit” không đủ để khẳng định toàn bộ trang chứa hàng mới là `all-visible`.

Cờ VM mang ý nghĩa mạnh hơn: PostgreSQL đã xác định trang thỏa điều kiện an toàn cho việc bỏ qua kiểm tra heap visibility cho các index entry liên quan.

### 5.1. Visibility theo page, không theo truy vấn riêng

`all-visible` không có nghĩa “tất cả hàng trên trang đều thỏa `WHERE price > 100`”. Nó cũng không có nghĩa “session hiện tại nhìn thấy hết các tuple vì quyền truy cập”.

Cờ này là thông tin **MVCC toàn cục ở cấp trang**, độc lập với filter nghiệp vụ và chính sách ủy quyền của một câu SELECT cụ thể.

### 5.2. Row-Level Security không do visibility map xử lý

Nếu bảng có RLS, PostgreSQL vẫn phải áp dụng policy và các điều kiện SQL hợp lệ. VM không cung cấp cơ chế phân quyền và không thể làm người dùng xem hàng họ không được phép xem.

VM chỉ giúp tối ưu bước kiểm tra visibility vật lý/MVCC khi điều kiện an toàn.

## 6. Khi nào cờ all-visible được đặt?

Trong vận hành thông thường, **VACUUM** là cơ chế quan trọng để kiểm tra và đánh dấu những trang đủ điều kiện `all-visible`.

Khái quát:

1. Một trang có tuple đã đủ điều kiện visibility.
2. VACUUM xem xét trạng thái tuple và các điều kiện cần thiết.
3. Khi trang đủ điều kiện, PostgreSQL có thể đánh dấu `all-visible` trong VM.
4. Các truy vấn index-only scan về sau có thể tận dụng cờ đó.

Đây không phải lời hứa rằng `VACUUM` sẽ đánh dấu **mọi trang** all-visible. Trang có tuple còn chịu ảnh hưởng transaction đang mở, phiên bản chưa thể thu dọn hoặc thay đổi đồng thời có thể chưa đáp ứng điều kiện.

### 6.1. Vì sao COMMIT không tự đặt lại all-visible?

Một transaction COMMIT không đồng nghĩa:

- Không còn snapshot cũ đang mở.
- Toàn bộ tuple chết trên trang đã đủ điều kiện xóa.
- Cần/đã thực hiện một lượt kiểm tra an toàn toàn trang.
- VM đã được cập nhật về trạng thái mới.

PostgreSQL không bắt mỗi COMMIT phải kiểm tra lại mọi trang vừa bị thay đổi để đánh dấu VM. Việc duy trì trạng thái đủ an toàn gắn với VACUUM và cơ chế lưu trữ phù hợp.

## 7. Điều gì làm mất cờ all-visible?

Các thao tác ghi lên một trang heap, như INSERT/UPDATE/DELETE có liên quan, có thể khiến trang không còn all-visible và làm PostgreSQL **xóa cờ** đó.

Ví dụ:

~~~text
Trước thay đổi:
Page 42: all_visible=1, all_frozen=1

Transaction cập nhật một hàng trên Page 42:
Page 42: all_visible=0, all_frozen=0

Sau commit:
Page 42 vẫn không tự trở lại all-visible.

VACUUM về sau:
Nếu thỏa điều kiện, all_visible có thể được đặt lại;
all_frozen phụ thuộc trạng thái freezing.
~~~

Cờ bị xóa theo **page**, nên một UPDATE trên vài trăm tuple phân bố rải rác qua nhiều trang có thể làm nhiều VM bits không còn được đặt.

### 7.1. UPDATE và phiên bản tuple mới

UPDATE thường tạo một phiên bản mới trong heap và làm phiên bản cũ không còn là phiên bản hiện hành cho những snapshot sau. Dù UPDATE có thể là HOT (Heap-Only Tuple) trong một số điều kiện, trang bị thay đổi vẫn cần quản lý MVCC/visibility tương ứng.

HOT giúp giảm một số chi phí cập nhật index, nhưng **không có nghĩa một trang HOT-updated lập tức vẫn all-visible**.

### 7.2. Không nên dùng VM để đánh giá tốc độ ghi thuần túy

Một trang mất all-visible không tự có nghĩa thao tác ghi sai. Đó thường là hành vi đúng khi dữ liệu thay đổi. Những bảng có cập nhật thường xuyên có thể có tỷ lệ trang all-visible thấp hơn bảng gần như chỉ đọc.

Mục tiêu không phải ép mọi trang mọi lúc đều all-visible, mà là hiểu **cân bằng giữa write activity, VACUUM và read workload**.

## 8. Index-only scan: vì sao tên gọi có thể gây hiểu nhầm?

Một index-only scan đọc dữ liệu từ index khi index chứa đủ cột mà truy vấn cần.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_cover
ON orders (customer_id, created_at DESC, id DESC)
INCLUDE (total_amount);
~~~

Một truy vấn có thể dùng index này:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Về cột, index có đủ:

- `customer_id` làm điều kiện lọc.
- `created_at` và `id` phục vụ thứ tự.
- `total_amount` nằm trong `INCLUDE` để trả giá trị.

Tuy nhiên index của PostgreSQL thường **không chứa đầy đủ trạng thái MVCC visibility của heap tuple**. Một index entry có thể trỏ tới tuple chưa nhìn thấy được với snapshot hiện tại hoặc phiên bản đã trở thành không hợp lệ.

Do đó, khi thực hiện Index Only Scan, PostgreSQL kiểm tra VM:

- Trang heap `all-visible` → có thể không cần heap lookup cho index entry.
- Trang heap không `all-visible` → phải truy cập heap để xác định tuple có nhìn thấy được hay không.

### 8.1. “Index Only Scan” vẫn có thể có Heap Fetches

Kế hoạch dạng:

~~~text
Index Only Scan using idx_orders_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 350
~~~

không mâu thuẫn. Đây vẫn là node `Index Only Scan`, nhưng có những lần phải tới heap vì VM chưa cho phép bỏ qua visibility check.

Ngược lại:

~~~text
Index Only Scan using idx_orders_cover on orders
  Index Cond: (customer_id = 42)
  Heap Fetches: 0
~~~

cho thấy ở lượt thực thi đó, node đã trả kết quả mà không cần các heap fetch thuộc chỉ số này. Không nhất thiết mọi query trên cùng bảng đều có 0 heap fetch.

### 8.2. Heap Fetches cao nói gì?

Nó gợi ý truy vấn không được hưởng lợi hoàn toàn từ các trang `all-visible` hoặc có yêu cầu kiểm tra visibility qua heap.

Nhưng **không được suy trực tiếp**:

- Số heap fetch = số trang không all-visible.
- Số heap fetch = số hàng chết.
- Heap Fetches cao = cần chạy `VACUUM FULL`.
- Heap Fetches thấp = bảng hoàn toàn không có bloat.

Một trang có thể được truy cập nhiều lần cho các index entries khác nhau; số lần heap fetch còn phụ thuộc index scan, điều kiện và tập dữ liệu.

## 9. Tác động lên truy vấn: trước và sau VACUUM

Xét một bảng gần như chỉ đọc:

~~~text
Bảng lịch sử đã nạp hàng loạt
         |
         v
Nhiều trang đã ổn định
         |
         v
VACUUM đánh dấu all-visible
         |
         v
Index-only scan có thể trả dữ liệu
với rất ít heap fetch
~~~

Ngược lại:

~~~text
Bảng giao dịch UPDATE thường xuyên
         |
         v
Nhiều trang vừa thay đổi
         |
         v
all-visible bị xóa ở các trang đó
         |
         v
Index-only scan cần kiểm tra heap
         |
         v
Heap Fetches có thể tăng
~~~

Đây là một **cơ chế có thể làm thay đổi hiệu năng** mà không cần thay SQL hay index. Cùng một truy vấn, tỷ lệ heap pages all-visible khác nhau có thể dẫn đến thời gian thực thi khác.

Tuy nhiên PostgreSQL planner cũng xét thống kê, cache, loại index, selectivity, kích thước bảng và chi phí khác. Không phải cứ có VM all-visible là chắc chắn planner chọn Index Only Scan.

## 10. Thí nghiệm: tạo bảng và covering index

Các câu SQL dưới đây chỉ dành cho **database lab riêng**. Chúng tạo dữ liệu tổng hợp để quan sát VM và `Index Only Scan`, không phải quy trình chạy trên production.

~~~sql
CREATE SCHEMA mvcc_lab;

CREATE TABLE mvcc_lab.events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    note TEXT
);

CREATE INDEX idx_events_cover
ON mvcc_lab.events (
    account_id,
    occurred_at DESC,
    id DESC
)
INCLUDE (amount);

INSERT INTO mvcc_lab.events (
    account_id,
    occurred_at,
    amount,
    note
)
SELECT
    (g % 20 + 1)::INTEGER,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
        + g * INTERVAL '1 second',
    (10000 + g % 5000)::NUMERIC(12, 2),
    NULL::TEXT
FROM generate_series(1, 20000) AS g;
~~~

Bảng có 20.000 hàng, `account_id` phân bố trên 20 giá trị. `occurred_at` tăng đều theo ID, giúp kiểm soát kết quả thử nghiệm. Index chứa đủ các cột cần dùng cho truy vấn phân trang mẫu:

~~~sql
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

`note` cố ý **không có trong index**, để có thể thay đổi một cột không được index tham chiếu ở thí nghiệm sau.

### 10.1. Chạy EXPLAIN trước VACUUM

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

Các điều cần đọc trong kết quả:

- Planner dùng `Index Only Scan` hay scan khác?
- Có `Heap Fetches` không?
- Số `actual rows` và `Buffers` như thế nào?

Không đoán trước một con số `Heap Fetches` cố định. Ngay sau INSERT, các VM bits có thể chưa phản ánh những trang all-visible; nhưng planner và trạng thái thực tế của database vẫn quyết định kế hoạch.

### 10.2. Chạy VACUUM trong lab

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

`VACUUM` dọn dẹp MVCC và có thể đánh dấu các heap pages all-visible khi đủ điều kiện. `ANALYZE` cập nhật thống kê phục vụ planner.

**VACUUM không được chạy bên trong một explicit transaction block** theo cú pháp thông thường. Thực thi lệnh trên ở session không đang nằm trong `BEGIN ... COMMIT`.

Chạy lại:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

Nếu node Index Only Scan được chọn và các trang liên quan đã all-visible, `Heap Fetches` có thể giảm rõ, thậm chí bằng 0.

### 10.3. Vì sao không nên lấy một lần đo làm kết luận tổng quát?

Hai lượt EXPLAIN cũng khác nhau ở:

- Thống kê planner thay đổi bởi ANALYZE.
- Dữ liệu/cache đã được đọc ở lượt trước.
- Buffer cache và hệ điều hành có thể giữ các trang.
- Số liệu chính xác phụ thuộc PostgreSQL version và môi trường.
- Một bảng nhỏ có thể khiến sequential scan rẻ hơn.

Thí nghiệm minh họa quan hệ giữa **VM, visibility check và index-only scan**, không chứng minh một mức tăng tốc tuyệt đối cho mọi hệ thống.

## 11. Thí nghiệm: UPDATE làm mất lợi ích all-visible

Sau khi đã VACUUM, thử UPDATE một số hàng:

~~~sql
UPDATE mvcc_lab.events
SET note = 'reviewed'
WHERE account_id = 7
  AND id <= 2000;
~~~

Vì cột `note` không có trong index `idx_events_cover`, PostgreSQL **có thể** sử dụng HOT updates nếu các điều kiện khác và không gian trang cho phép. Tuy nhiên, các heap pages liên quan đã thay đổi nên VM có thể mất cờ all-visible.

Chạy lại:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, occurred_at, amount
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 1000;
~~~

Tùy hàng thuộc các trang nào, số `Heap Fetches` có thể tăng. Nếu query chỉ đọc các trang không bị thay đổi hoặc planner chọn đường khác, kết quả có thể không biểu hiện rõ.

Sau đó:

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

và chạy lại EXPLAIN để quan sát sự thay đổi.

### 11.1. Vì sao update một cột không nằm trong index vẫn ảnh hưởng?

Ngay cả khi index entry không phải thay đổi vì `note`, MVCC vẫn phải quản lý phiên bản heap tuple. Một trang vừa bị ghi có thể không còn an toàn để coi mọi tuple nhìn thấy với mọi snapshot.

Đó chính là quan hệ giữa **cơ chế lưu trữ MVCC** và **truy vấn chỉ lấy cột từ index**.

### 11.2. UPDATE trên cột INCLUDE thì sao?

Nếu sửa `amount`, đây là cột được `INCLUDE` trong index. Trong các điều kiện HOT thông thường, cập nhật cột được tham chiếu bởi index có thể ngăn HOT optimization; chi phí cập nhật index và heap vì vậy khác với UPDATE chỉ sửa `note`.

Không nên tạo một thí nghiệm HOT rồi kết luận mọi UPDATE đều có cùng đặc tính.

## 12. Quan sát VM bằng extension pg_visibility

PostgreSQL có extension **`pg_visibility`** cung cấp các hàm quan sát visibility map và trạng thái trang.

Trong database lab, nếu extension được cung cấp và role đủ quyền:

~~~sql
CREATE EXTENSION IF NOT EXISTS pg_visibility;
~~~

Trong môi trường được quản trị, bạn có thể không có quyền tạo extension hoặc đọc một số thông tin page-level. Khi đó yêu cầu DBA hỗ trợ; không tự nâng quyền production chỉ để chạy ví dụ.

### 12.1. Tổng số trang all-visible và all-frozen

~~~sql
SELECT *
FROM pg_visibility_map_summary(
    'mvcc_lab.events'::regclass
);
~~~

Kết quả có hai giá trị quan trọng:

- `all_visible`: số heap pages được VM đánh dấu all-visible.
- `all_frozen`: số heap pages được VM đánh dấu all-frozen.

Không nhầm các giá trị này là **số hàng**. Chúng là **số trang**.

### 12.2. Xem từng trang

~~~sql
SELECT
    blkno,
    all_visible,
    all_frozen
FROM pg_visibility_map(
    'mvcc_lab.events'::regclass
)
ORDER BY blkno
LIMIT 30;
~~~

Có thể thêm điều kiện xem các trang không all-visible:

~~~sql
SELECT blkno, all_visible, all_frozen
FROM pg_visibility_map(
    'mvcc_lab.events'::regclass
)
WHERE NOT all_visible
ORDER BY blkno
LIMIT 30;
~~~

Khi database có ghi đồng thời, trạng thái VM có thể thay đổi sau thời điểm query. Đừng dùng kết quả quan sát như một snapshot bền vững của trạng thái trang mãi về sau.

### 12.3. pg_visibility không phải công cụ sửa VM thông thường

Extension có các hàm kiểm tra, nhưng bài học tập trung **quan sát**. Không tự sửa cờ VM bằng thao tác nội bộ hoặc can thiệp tệp relation.

PostgreSQL phải duy trì VM an toàn cùng WAL, tuple visibility và VACUUM; sửa cờ bằng phương pháp không được quản lý có thể làm truy vấn trả kết quả sai.

## 13. Tính tỷ lệ trang all-visible trên bảng

Có thể kết hợp kích thước main fork và số trang từ extension:

~~~sql
WITH
page_count AS (
    SELECT
        (
            pg_relation_size(
                'mvcc_lab.events'::regclass,
                'main'
            ) / current_setting('block_size')::INTEGER
        )::BIGINT AS heap_pages
),
vm AS (
    SELECT *
    FROM pg_visibility_map_summary(
        'mvcc_lab.events'::regclass
    )
)
SELECT
    p.heap_pages,
    vm.all_visible,
    vm.all_frozen,
    ROUND(
        100.0 * vm.all_visible
        / NULLIF(p.heap_pages, 0),
        2
    ) AS all_visible_percent,
    ROUND(
        100.0 * vm.all_frozen
        / NULLIF(p.heap_pages, 0),
        2
    ) AS all_frozen_percent
FROM page_count AS p
CROSS JOIN vm;
~~~

Kết quả giúp quan sát nhanh tỷ lệ trang được đánh dấu. Với bảng rỗng, `NULLIF` ngăn chia cho 0 và phần trăm có thể NULL.

### 13.1. Các tỷ lệ này không phải tỷ lệ hàng

Một trang chứa 5 tuple và một trang chứa 100 tuple đều được tính là **một trang**. Tỷ lệ 80% all-visible pages không nhất thiết có nghĩa 80% hàng SQL nằm trên trang all-visible.

### 13.2. Một quan sát tại một thời điểm

Các truy vấn `pg_relation_size` và `pg_visibility_map_summary` có thể đọc trạng thái tại những thời điểm hơi khác nhau nếu có ghi đồng thời. Vì vậy đây là chỉ số **vận hành xấp xỉ theo thời điểm**, không phải phép kiểm chứng toàn bộ quan hệ trong một snapshot vật lý nguyên tử.

## 14. pg_class.relallvisible: thông tin cho planner

PostgreSQL cũng lưu metadata thống kê của relation trong `pg_class`:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relpages,
    c.reltuples,
    c.relallvisible,
    ROUND(
        100.0 * c.relallvisible
        / NULLIF(c.relpages, 0),
        2
    ) AS relallvisible_pct
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Ý nghĩa:

- `relpages`: ước lượng số trang relation.
- `reltuples`: ước lượng số tuple.
- `relallvisible`: số trang all-visible theo thông tin được lưu trong catalog cho planner.

Những giá trị này có thể được cập nhật bởi thao tác bảo trì như VACUUM/ANALYZE và **không nhất thiết phản ánh chính xác thời điểm hiện tại**.

### 14.1. Khác gì pg_visibility?

| Nguồn | Mục đích | Độ trực tiếp |
|---|---|---|
| `pg_class.relallvisible` | Thông tin thống kê để planner ước lượng hiệu quả index-only scan | Có thể cũ so với VM thực |
| `pg_visibility_map_summary` | Quan sát bit VM thực theo trang tại thời điểm gọi | Trực tiếp hơn cho trạng thái VM |
| `EXPLAIN (ANALYZE) Heap Fetches` | Đếm heap fetch thực tế của node trong một lần query | Đo hành vi query cụ thể |
| `pg_stat_user_tables` | Thống kê hoạt động/ước lượng dead tuples và VACUUM | Chỉ số vận hành, không phải bản đồ VM |

Đừng dùng riêng `relallvisible` để khẳng định “toàn bộ những trang này đang all-visible chính xác ngay lúc này”.

## 15. VACUUM và ANALYZE làm những việc khác nhau

Hai lệnh thường xuất hiện cùng nhau:

~~~sql
VACUUM (ANALYZE) mvcc_lab.events;
~~~

Nhưng:

- **VACUUM**: thu dọn những tuple đã chết theo điều kiện an toàn, tái sử dụng không gian, duy trì VM và xử lý freezing.
- **ANALYZE**: thu thập thống kê để planner ước lượng selectivity, cardinality và lựa chọn kế hoạch.

`ANALYZE` riêng không phải cơ chế bảo đảm đánh dấu all-visible/freeze pages. Nếu bạn cần xem điều gì đã thay đổi vì cả VACUUM và ANALYZE, hãy tách rõ hai yếu tố.

### 15.1. VACUUM thường không làm tệp bảng nhỏ lại ngay

`VACUUM` thông thường chủ yếu cho phép **tái sử dụng không gian nội bộ**, không nhất thiết trả toàn bộ dung lượng tệp về hệ điều hành. Nó có thể truncate các trang cuối đủ điều kiện trong một số trường hợp, nhưng không nên coi đó là mục tiêu mặc định của mọi VACUUM.

`VACUUM FULL` **rewrite** bảng để thu hồi dung lượng và yêu cầu khóa mạnh, có tính chất khác biệt. Không chạy VACUUM FULL chỉ vì muốn tăng all-visible cho index-only scan.

## 16. Freezing: vấn đề XID wraparound

PostgreSQL sử dụng transaction ID theo vòng; các XID truyền thống thuộc không gian 32-bit. Khi hệ thống hoạt động lâu, giá trị XID tăng và cuối cùng đi vòng.

Nếu giữ nguyên vô hạn những tham chiếu XID cũ mà không có cơ chế bảo vệ, PostgreSQL có thể không phân biệt đúng “cũ” và “mới” khi vòng số quay lại.

**Freezing** giúp xử lý những thông tin transaction cũ trong tuple sao cho PostgreSQL biết phiên bản hàng đã đủ lâu và an toàn để xem là được tạo bởi một transaction đã commit trong quá khứ theo semantics MVCC, không phải tiếp tục phụ thuộc vào các chi tiết XID hữu hạn tuổi thọ.

### 16.1. Không nên hiểu freezing là khóa hàng

Từ “frozen” dễ bị hiểu nhầm là “hàng không thể UPDATE/DELETE”. Điều đó **sai**.

Một tuple đã frozen:

- Vẫn có thể được SELECT bình thường.
- Vẫn có thể bị UPDATE hoặc DELETE nếu người dùng có quyền và ràng buộc cho phép.
- Khi UPDATE, PostgreSQL tạo phiên bản tuple mới theo quy tắc MVCC.
- Trang chứa tuple đó có thể mất cờ all-visible/all-frozen khi có thay đổi.

Freezing là tối ưu/bảo vệ **transaction visibility metadata**, không phải chức năng read-only cho dữ liệu nghiệp vụ.

## 17. Freezing có thật sự viết xmin = FrozenTransactionId?

Trong giải thích cơ bản, người học thường thấy mô hình “thay một XID cũ bằng `FrozenTransactionId`”. Đây là cách diễn đạt **khái niệm** rằng tuple đã được coi là frozen.

Trong các phiên bản PostgreSQL hiện đại, cơ chế vật lý có thể sử dụng **tuple header/infomask bits** để biểu diễn trạng thái frozen thay vì luôn ghi đè giá trị `xmin` bằng một hằng số.

Vì vậy:

- Đừng suy từ việc truy vấn `SELECT xmin` rằng bạn đã nhìn thấy toàn bộ cơ chế freeze.
- Đừng xây ứng dụng dựa trên `xmin` làm version ID bền vững.
- Đừng xem một XID hiển thị ở tuple cũ như bằng chứng freeze chưa chạy nếu không hiểu biểu diễn nội bộ.

Các trường hệ thống phục vụ mục đích MVCC/debug; không phải contract nghiệp vụ dài hạn.

## 18. All-visible khác all-frozen như thế nào?

Một trang được đánh dấu **all-visible** khi PostgreSQL đã xác định tất cả tuple hiện có đủ điều kiện visibility cho mọi transaction theo quy tắc VM.

Một trang được đánh dấu **all-frozen** khi các thông tin XID/MultiXact cần xử lý freezing trên trang đã được xử lý, nhằm không phải quay lại trang đó cho mục đích freeze hiện tại.

Có thể hình dung:

~~~text
Trang có các tuple đã commit, đủ cũ để mọi snapshot thấy
    |
    +--> Có thể all-visible
    |
    +--> Nhưng XID/MultiXact có thể chưa frozen
             |
             v
        VACUUM freezing
             |
             v
        Có thể trở thành all-frozen
~~~

**Quan hệ bao hàm:**

\[
\text{all-frozen} \Rightarrow \text{all-visible}
\]

nhưng:

\[
\text{all-visible} \not\Rightarrow \text{all-frozen}
\]

Đây là một trong những điều quan trọng nhất cần nhớ về visibility map.

## 19. Tại sao all-frozen giúp VACUUM?

Khi PostgreSQL cần chống XID wraparound hoặc đóng băng các transaction cũ, nó cần biết trang nào vẫn có thông tin transaction phải xem xét.

Nếu trang đã được VM đánh dấu `all-frozen`, VACUUM có thể **bỏ qua trang đó trong các lượt cần xử lý freezing**, theo điều kiện an toàn của thuật toán.

Các trang chỉ `all-visible` nhưng chưa `all-frozen` vẫn có thể cần được quét trong một **aggressive vacuum** để freeze transaction metadata.

Công việc tiết kiệm được có thể đáng kể trên bảng lớn gần như chỉ đọc:

~~~text
Bảng lịch sử 500 GB
  |
  +--> Nhiều trang all-frozen
  |       |
  |       +--> Aggressive vacuum có thể skip
  |            các trang không cần freeze lại
  |
  +--> Các trang chưa all-frozen
          |
          +--> Cần xem xét/đóng băng nếu đủ điều kiện
~~~

Không suy rằng all-frozen có nghĩa PostgreSQL sẽ **không bao giờ** đọc lại trang đó cho mục đích khác. Các truy vấn và hoạt động bảo trì khác vẫn có thể cần trang; DML mới còn làm cờ thay đổi.

## 20. Regular VACUUM và aggressive VACUUM

Trong PostgreSQL, VACUUM có thể chạy theo các chế độ/điều kiện khác nhau.

### 20.1. Regular VACUUM

Một lượt VACUUM thông thường ưu tiên thu dọn những tuple không còn cần, cập nhật VM và freeze những tuple phù hợp theo ngưỡng. Nó có thể **bỏ qua nhiều trang all-visible** không cần xử lý ngay, để giảm I/O.

### 20.2. Aggressive VACUUM

Khi tuổi XID của relation đủ lớn, PostgreSQL có thể tiến hành vacuum theo hướng **aggressive**: quét những trang chưa `all-frozen` để xử lý các XID/MultiXact cũ, tránh wraparound.

Aggressive vacuum vẫn có thể **skip trang đã all-frozen**. Nó không có nghĩa đọc lại từng byte của mọi trang nếu VM chứng minh một số trang không cần công việc freezing.

### 20.3. VACUUM (FREEZE) trong lab

PostgreSQL cho phép:

~~~sql
VACUUM (FREEZE, ANALYZE, VERBOSE) mvcc_lab.events;
~~~

Tùy phiên bản, `FREEZE` tương đương một lượt vacuum có thiết lập ngưỡng freeze rất tích cực, khiến PostgreSQL cố xử lý freezing sớm.

**Không chạy `VACUUM (FREEZE)` bừa bãi trên bảng production lớn.** Nó có thể phát sinh I/O, WAL và thời gian bảo trì đáng kể. VACUUM tự động đã có các cơ chế dựa trên tuổi XID và hoạt động bảng để xử lý thông thường.

Lệnh này phải chạy **ngoài explicit transaction block**.

## 21. Các ngưỡng liên quan freezing

Các tham số cấu hình quan trọng có thể xem bằng:

~~~sql
SHOW vacuum_freeze_min_age;
SHOW vacuum_freeze_table_age;
SHOW autovacuum_freeze_max_age;
~~~

Ý nghĩa khái quát:

| Tham số | Vai trò |
|---|---|
| `vacuum_freeze_min_age` | Ngưỡng tuổi thấp nhất để VACUUM thường cân nhắc freeze những XID phù hợp |
| `vacuum_freeze_table_age` | Một ngưỡng giúp quyết định khi VACUUM nên aggressive để xử lý XID cũ |
| `autovacuum_freeze_max_age` | Ngưỡng quan trọng kích hoạt autovacuum chống wraparound khi relation quá cũ |

Các tham số và giới hạn có thể khác theo phiên bản. Một số còn có tùy chọn tương ứng ở cấp bảng qua reloptions. Không tự sao chép một bộ giá trị cấu hình từ hệ thống khác mà chưa xét tuổi XID, throughput transaction, I/O, khối lượng bảng và cửa sổ vận hành.

### 21.1. Đừng tối ưu một tham số tách rời

Giảm mạnh ngưỡng có thể khiến hệ thống freeze sớm hơn, phát sinh nhiều công việc bảo trì.

Tăng ngưỡng quá mức có thể dồn công việc về sau hoặc đưa hệ thống tới tình trạng **anti-wraparound vacuum** khó trì hoãn.

Mục tiêu là duy trì quét/freeze an toàn và đều đặn theo workload, không phải “đặt ngưỡng tối đa để VACUUM càng ít chạy càng tốt”.

## 22. relfrozenxid và tuổi transaction của bảng

PostgreSQL lưu một mốc liên quan XID của từng relation trong `pg_class.relfrozenxid`.

Có thể quan sát:

~~~sql
SELECT
    n.nspname AS schema_name,
    c.relname AS table_name,
    c.relfrozenxid,
    age(c.relfrozenxid) AS xid_age
FROM pg_class AS c
JOIN pg_namespace AS n
    ON n.oid = c.relnamespace
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

`age(re x)` ở đây được viết đúng là `age(c.relfrozenxid)` trong SQL: nó đo độ tuổi transaction tương đối với current transaction ID theo semantics PostgreSQL.

Giá trị tuổi lớn cho thấy relation cần được quan sát trong chiến lược chống wraparound. Nó **không trực tiếp** báo số tuple dead, số index-only heap fetch hay tỷ lệ all-visible.

### 22.1. Tuổi XID không phải tuổi theo ngày

Một bảng được tạo tháng trước có thể có XID age lớn nếu server xử lý rất nhiều transaction. Một bảng tạo nhiều năm trước có thể có tuổi XID thấp nếu được vacuum/freeze phù hợp.

Không đổi `age(relfrozenxid)` thành “số ngày chưa VACUUM” một cách máy móc.

### 22.2. Quan sát tuổi ở cấp database

~~~sql
SELECT
    datname,
    age(datfrozenxid) AS database_xid_age
FROM pg_database
ORDER BY age(datfrozenxid) DESC;
~~~

`datfrozenxid` là mốc ở cấp database liên quan các relation. DBA thường theo dõi nó cùng các mốc quan trọng khác để bảo đảm chống wraparound.

Một vài relation hệ thống hoặc relation không nằm trong danh sách table thông thường cũng có thể ảnh hưởng quá trình vacuum/freeze; không chỉ nhìn một bảng lớn duy nhất.

## 23. MultiXact và freezing

Không chỉ transaction ID thông thường: PostgreSQL còn dùng **MultiXact ID** trong những tình huống nhiều transaction cùng khóa một tuple.

Hệ thống phải quản lý vòng đời MultiXact để tránh wraparound tương tự.

Các thông tin liên quan:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    c.relminmxid,
    mxid_age(c.relminmxid) AS multixact_age
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Tùy PostgreSQL version, các tham số/cơ chế autovacuum MultiXact có ngưỡng riêng. Trong vận hành production, chỉ giám sát `age(relfrozenxid)` mà bỏ qua `mxid_age(relminmxid)` có thể không đủ.

### 23.1. All-frozen giúp cả hai họ metadata

Khi một trang được đánh dấu all-frozen theo quy tắc PostgreSQL, ý nghĩa của cờ bao hàm việc không cần quay lại trang đó chỉ vì còn thông tin XID/MultiXact cần freeze theo điều kiện hiện tại.

Không cần tự sửa `xmin`, `xmax` hay các trường header của tuple để “giảm tuổi” bằng thao tác SQL thủ công. PostgreSQL VACUUM quản lý an toàn việc này.

## 24. Vì sao XID wraparound là vấn đề nghiêm trọng?

Nếu hệ thống không xử lý XID cũ và để vòng XID tiến gần vùng nguy hiểm, PostgreSQL có thể phải ưu tiên bảo trì chống wraparound. Ở mức nghiêm trọng, database có thể từ chối những transaction ghi mới để tránh mất tính đúng của dữ liệu.

Đó là cơ chế bảo vệ, không phải PostgreSQL tự “xóa sạch dữ liệu cũ”.

### 24.1. Không được tắt autovacuum để tránh I/O mà quên wraparound

Tắt autovacuum toàn cục hoặc trên bảng có thể gây:

- Dead tuples tích tụ.
- Index-only scan có ít trang all-visible hơn.
- Planner statistics cũ nếu không có ANALYZE.
- XID/MultiXact age tiến tới ngưỡng rủi ro.
- Lượt vacuum chống wraparound phát sinh ngoài ý muốn.

Ngay cả khi tắt một số cơ chế autovacuum thông thường, PostgreSQL vẫn có các biện pháp đặc biệt cho anti-wraparound, nhưng **không nên dựa vào điều đó để vận hành an toàn**.

Khi có áp lực I/O, cần điều chỉnh tuning autovacuum có căn cứ và theo dõi tuổi XID thay vì bỏ hẳn bảo trì.

## 25. Transaction dài làm ảnh hưởng VACUUM

Giả sử:

~~~text
10:00 - Session A bắt đầu transaction có snapshot cũ.
10:01 - Session B cập nhật nhiều hàng.
10:02 - Session B commit.
10:03 - VACUUM chạy.
10:30 - Session A vẫn giữ transaction.
~~~

Khi một snapshot cũ còn cần những phiên bản tuple cũ, VACUUM không thể thu dọn tùy ý những phiên bản đó. Những trang liên quan có thể chưa thể đạt trạng thái all-visible/all-frozen như khi không có transaction giữ chân.

### 25.1. Hệ quả

- Dead tuples có thể tồn tại lâu hơn.
- Bloat tăng.
- VM không đạt tỷ lệ all-visible như mong đợi.
- Index-only scan cần thêm heap fetch.
- Việc advancing freezing horizons có thể bị hạn chế.
- VACUUM có thể phải lặp lại công việc khi blocker được gỡ.

Không phải mọi transaction dài đều gây mọi hệ quả trên mọi bảng; tác động phụ thuộc snapshot, quan hệ được thay đổi và loại transaction. Nhưng đó là một nguồn điều tra quan trọng.

## 26. Tìm transaction lâu và trạng thái kết nối

Một truy vấn quan sát:

~~~sql
SELECT
    pid,
    usename,
    datname,
    state,
    xact_start,
    now() - xact_start AS transaction_age,
    wait_event_type,
    wait_event,
    left(query, 160) AS query_excerpt
FROM pg_stat_activity
WHERE xact_start IS NOT NULL
ORDER BY xact_start
LIMIT 30;
~~~

Cột `xact_start` là thời điểm transaction bắt đầu, không nhất thiết là thời điểm snapshot được giữ. Để điều tra cụ thể horizon, cần xem thêm metadata transaction và hệ thống liên quan.

### 26.1. Quyền xem query của session khác

Tùy quyền, role thường không thể xem đầy đủ thông tin session của người khác. Những trường query có thể bị ẩn. Không tự cấp quyền rộng hoặc lưu toàn bộ query text có chứa dữ liệu nhạy cảm vào dashboard.

### 26.2. Một transaction idle lâu cũng cần chú ý

`state='idle in transaction'` là tín hiệu đáng điều tra, nhất là khi transaction giữ snapshot/lock hoặc đã làm thay đổi dữ liệu.

Ứng dụng nên:

- Kết thúc transaction sớm.
- Không giữ transaction mở giữa các request người dùng.
- Có timeout phù hợp như `idle_in_transaction_session_timeout` sau khi đánh giá.
- Tránh giữ kết nối pool chỉ để chờ người dùng xem trang.

Đừng tự động kill mọi transaction dài khi chưa xác định tác động tới công việc hợp lệ.

## 27. Replication slots và hot_standby_feedback

Một số cấu hình replication cũng có thể ảnh hưởng việc thu dọn tuple cũ.

Ví dụ:

- Replication slot giữ thông tin phục vụ consumer chậm.
- Logical replication slot có thể giữ `xmin` hoặc `catalog_xmin` trong những điều kiện nhất định.
- `hot_standby_feedback` có thể báo về primary rằng standby còn cần những phiên bản tuple cũ.

Hệ quả có thể là VACUUM trên primary không thể thu dọn sớm một số tuple đã chết theo góc nhìn application. Điều đó gián tiếp ảnh hưởng bloat và tỷ lệ all-visible của các trang đang thay đổi.

### 27.1. Quan sát slot

~~~sql
SELECT
    slot_name,
    slot_type,
    active,
    xmin,
    catalog_xmin
FROM pg_replication_slots;
~~~

Cần phân biệt:

- Một slot giữ WAL chưa được consume có thể gây tăng dung lượng WAL.
- Một slot giữ xmin/catalog_xmin có thể ảnh hưởng dọn tuple.
- Không phải mọi slot đều luôn giữ cả hai loại horizon.
- Kế hoạch xử lý slot phải xét subscriber, CDC, backup và nguy cơ mất dữ liệu.

Không xóa replication slot production chỉ vì thấy nó cũ mà chưa hiểu consumer.

## 28. Theo dõi VACUUM qua pg_stat_user_tables

PostgreSQL cung cấp thống kê hoạt động bảng:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_vacuum,
    last_autovacuum,
    vacuum_count,
    autovacuum_count,
    n_tup_ins,
    n_tup_upd,
    n_tup_del
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
  AND relname = 'events';
~~~

Một số cách đọc:

- `n_live_tup` và `n_dead_tup` thường là **ước lượng thống kê**, không phải phép COUNT chính xác.
- `last_autovacuum` có thể NULL nếu chưa có lượt được ghi nhận kể từ khi thống kê được theo dõi/reset.
- Số UPDATE cao gợi ý bảng có write churn và nhiều VM bits có thể bị xóa theo thời gian.
- `vacuum_count` và `autovacuum_count` giúp biết hoạt động bảo trì, nhưng không chứng minh từng trang đã được freeze.

### 28.1. Quan sát tiến độ VACUUM đang chạy

Khi PostgreSQL đang chạy VACUUM, có thể tham khảo:

~~~sql
SELECT
    pid,
    relid::regclass AS relation_name,
    phase,
    heap_blks_total,
    heap_blks_scanned,
    heap_blks_vacuumed,
    index_vacuum_count
FROM pg_stat_progress_vacuum
ORDER BY pid;
~~~

Không phải lúc nào cũng có dòng; view chỉ thể hiện những VACUUM đang tiến hành theo tính năng phiên bản. Số blocks scanned không tự đồng nghĩa toàn bộ blocks được đọc từ đĩa vì có page skipping và cache.

## 29. Autovacuum được kích hoạt ra sao?

Autovacuum xem nhiều tín hiệu, gồm số lượng tuples bị cập nhật/xóa, số lượng INSERT của các phiên bản hỗ trợ, ngưỡng tỷ lệ theo kích thước bảng và tuổi XID/MultiXact.

Các tham số có thể quan sát:

~~~sql
SHOW autovacuum;
SHOW autovacuum_vacuum_threshold;
SHOW autovacuum_vacuum_scale_factor;
SHOW autovacuum_vacuum_insert_threshold;
SHOW autovacuum_vacuum_insert_scale_factor;
SHOW autovacuum_analyze_threshold;
SHOW autovacuum_analyze_scale_factor;
~~~

Không phải mọi server/major version đều có cùng danh sách hoặc hành vi cấu hình; luôn kiểm tra bản server thực tế.

### 29.1. Vì sao bảng rất lớn cần chú ý scale factor?

Một tỷ lệ trigger dựa trên tổng số hàng của bảng có thể dẫn tới lượng thay đổi rất lớn trước khi autovacuum chạy. Với bảng lớn có UPDATE thường xuyên, việc trì hoãn VACUUM có thể gây:

- Nhiều dead tuples.
- Nhiều trang mất all-visible.
- Index-only scan có nhiều heap fetch.
- Bloat và chi phí IO lớn.

Có thể cân nhắc cấu hình autovacuum **theo bảng** sau khi đo workload, chẳng hạn ngưỡng thấp hơn và cấu hình phù hợp với nguồn lực. Không nên thay một giá trị toàn server theo ví dụ mà chưa quan sát tác động tới các bảng khác.

### 29.2. INSERT-only table cũng cần VACUUM

Một bảng chỉ INSERT và hầu như không UPDATE/DELETE vẫn cần bảo trì để:

- Đánh dấu những trang đủ điều kiện all-visible cho index-only scan.
- Freeze XID khi dữ liệu đủ cũ.
- Quản lý tuổi transaction lâu dài.

Không kết luận “không có dead tuples thì autovacuum không cần chạy”.

## 30. Vì sao bảng chỉ đọc thường có lợi từ all-frozen?

Một bảng lịch sử đã nạp xong, ít thay đổi có đặc tính:

- Các tuple ổn định lâu.
- VACUUM có cơ hội đánh dấu nhiều trang all-visible.
- Freezing có cơ hội tiến dần đến all-frozen.
- Index-only scan có thể giảm heap access nếu index phù hợp.
- Aggressive vacuum có thể skip những trang đã frozen.

Ngược lại, bảng thường xuyên UPDATE từng hàng:

- Các trang liên tục mất all-visible.
- Tuple versions và dead entries cần được xử lý.
- VM bits biến động.
- Index-only scan ít đạt 0 heap fetch trên những trang nóng.
- Freezing có thể phải lặp lại cho những phiên bản mới.

Không có nghĩa cứ bảng “nóng” thì không nên dùng index-only scan; cần xem tỷ lệ trang nóng trong vùng truy vấn và đo trên workload thực tế.

## 31. Visibility map có bảo đảm tránh đọc heap ở mọi index-only scan?

Không.

Ngay cả khi index chứa đủ cột, các điều kiện sau vẫn quan trọng:

1. Index method có hỗ trợ trả giá trị cần thiết cho index-only scan không?
2. Index có đủ key/INCLUDE columns không?
3. Các index entries cần đọc trỏ tới những trang heap nào?
4. Những trang đó có all-visible tại thời điểm kiểm tra không?
5. Planner có thấy index-only scan rẻ hơn index scan hoặc seq scan không?
6. Có filter/biểu thức nào yêu cầu dữ liệu không được index hỗ trợ không?

Ví dụ:

~~~sql
SELECT id, occurred_at, amount, note
FROM mvcc_lab.events
WHERE account_id = 7
ORDER BY occurred_at DESC, id DESC
LIMIT 100;
~~~

Index `idx_events_cover` **không chứa `note`**, nên một index-only scan dựa riêng trên index đó không thể cung cấp toàn bộ dữ liệu SELECT. VM all-visible không thay thế những cột thiếu.

### 31.1. INCLUDE không phải thuốc chữa mọi vấn đề

Có thể thêm mọi cột vào INCLUDE để làm index bao phủ, nhưng index càng rộng:

- Tăng kích thước.
- Tăng chi phí INSERT/UPDATE.
- Có thể giảm khả năng HOT khi cập nhật những cột được index tham chiếu.
- Có nguy cơ vượt giới hạn kích thước index tuple tùy dữ liệu.
- Vẫn có heap fetch nếu VM chưa all-visible.

Chỉ thiết kế covering index cho những query có lợi ích rõ ràng theo đo đạc.

## 32. Những hiểu lầm phổ biến về freezing

### Hiểu lầm 1 — Freeze là nén dữ liệu

Không. Freezing xử lý thông tin transaction visibility, không phải thuật toán nén row.

### Hiểu lầm 2 — Frozen nghĩa là không được UPDATE

Sai. Tuple frozen vẫn thuộc bảng có thể được cập nhật/xóa theo quyền/constraint; phiên bản mới có metadata MVCC mới.

### Hiểu lầm 3 — All-visible đồng nghĩa all-frozen

Sai. All-frozen kéo theo all-visible, không có chiều ngược lại.

### Hiểu lầm 4 — Trang all-visible thì không cần VACUUM bao giờ nữa

Sai. Trang có thể còn cần freezing; dữ liệu ghi mới cũng làm cờ thay đổi.

### Hiểu lầm 5 — Chỉ cần VACUUM FREEZE để index-only scan tối ưu

Không nhất thiết. Index-only scan cần **all-visible**, không trực tiếp yêu cầu **all-frozen**. VACUUM thông thường có thể đủ để đánh dấu all-visible.

### Hiểu lầm 6 — Freeze sẽ giảm relfrozenxid age xuống 0 ngay

Không nên mong chờ mọi VACUUM làm tuổi về 0. Mức tiến của horizon phụ thuộc snapshot, các XID/MultiXact còn cần xử lý và cơ chế tiến mốc.

### Hiểu lầm 7 — Freeze thay thế backup

Không. Freezing không tạo điểm phục hồi dữ liệu, không bảo vệ trước DELETE sai, lỗi phần cứng hay mất bảng.

## 33. Visibility map và PostgreSQL planner

Planner cân nhắc `pg_class.relallvisible` khi ước lượng lợi ích của index-only scan. Nếu thống kê cho thấy nhiều trang all-visible, chi phí heap fetch dự kiến có thể thấp hơn.

Nhưng planner còn xét:

- Index có đáp ứng predicate không.
- Có cần sort không.
- Có LIMIT không.
- Độ chọn lọc của `WHERE`.
- Kích thước relation.
- Các cost parameters như `random_page_cost`, `seq_page_cost`.
- Tỷ lệ cache và tương quan vật lý/logic của dữ liệu.
- Sự khác biệt giữa estimated rows và actual rows.

### 33.1. Truy vấn vẫn có thể chọn Index Scan

Ví dụ một query rất chọn lọc cần cột ngoài index có thể dùng Index Scan thay vì Index Only Scan. Một query trả phần lớn bảng có thể chọn Seq Scan dù có covering index.

Không nên ép planner chọn một node cụ thể chỉ vì muốn thấy `Heap Fetches: 0`. Mục tiêu cuối là latency/throughput và chi phí tổng thể.

### 33.2. Tại sao số liệu relallvisible cũ quan trọng?

Nếu `pg_class.relallvisible` đã cũ so với VM, planner có thể ước lượng khả năng tránh heap kém chính xác. `VACUUM/ANALYZE` và thống kê phù hợp có thể giúp lựa chọn kế hoạch hợp lý hơn.

Không nên dùng extension hay thao tác catalog thủ công để sửa `relallvisible` trực tiếp.

## 34. VACUUM không “dọn sạch mọi dead tuple” khi có blocker

Giả sử một transaction lâu giữ snapshot cần phiên bản cũ. VACUUM không thể xóa bản cũ chỉ vì `n_dead_tup` đang tăng. Những phiên bản còn có khả năng nhìn thấy với snapshot hợp lệ phải được giữ.

Khi blocker biến mất, lượt VACUUM sau có thể thu dọn được nhiều hơn.

Các nguồn blocker cần cân nhắc:

- Transaction dài hoặc idle in transaction có snapshot.
- Prepared transactions chưa hoàn tất.
- Replication slot/standby feedback giữ cleanup horizon trong một số cấu hình.
- Workload có transaction ID/row locks kéo dài.

Không nên xóa tùy tiện tuple bằng cơ chế ngoài VACUUM. MVCC yêu cầu xử lý theo visibility horizon an toàn.

## 35. VM có thể thay đổi dù không có UPDATE không?

Có.

Các thao tác có thể ảnh hưởng VM gồm:

- **INSERT:** trang nhận tuple mới có thể không còn all-visible.
- **DELETE:** thay đổi trạng thái tuple của trang.
- **UPDATE:** tạo phiên bản mới và thay đổi trang.
- **VACUUM:** có thể đánh dấu all-visible/all-frozen khi đủ điều kiện.
- Những thao tác bảo trì và phục hồi theo cơ chế PostgreSQL có thể quản lý lại fork/page state.

Vì vậy tỷ lệ `all_visible_percent` có thể giảm trên một bảng chỉ INSERT với tốc độ cao giữa hai lượt VACUUM. Không cần có DELETE thì VM mới thay đổi.

## 36. Visibility map có được WAL-log không?

PostgreSQL quản lý VM sao cho các thay đổi có tính nhất quán và an toàn với WAL/recovery theo cơ chế của nó. Trong thực thi, việc đánh dấu trang all-visible phải được đồng bộ phù hợp với trạng thái heap.

Vì sao điều này quan trọng?

Nếu VM nói “all-visible” trong khi một tuple thật sự chưa đủ điều kiện và engine bỏ qua kiểm tra heap visibility, câu SELECT có thể trả hàng sai theo MVCC. Do đó VM **không phải bộ đếm tùy ý**; việc đặt cờ có yêu cầu an toàn nghiêm ngặt.

Người vận hành nên dùng các lệnh SQL/VACUUM được PostgreSQL hỗ trợ, không tự sửa tệp `_vm`.

## 37. Observability: đọc đúng chỉ số nào cho đúng câu hỏi

| Câu hỏi cần trả lời | Quan sát hữu ích |
|---|---|
| Một query có đang dùng Index Only Scan? | `EXPLAIN (ANALYZE, BUFFERS)` |
| Query có phải về heap nhiều lần không? | `Heap Fetches` trên node Index Only Scan |
| Bao nhiêu heap pages đang all-visible/all-frozen? | `pg_visibility_map_summary` |
| Trang cụ thể có cờ nào? | `pg_visibility_map` |
| Planner ước lượng all-visible ra sao? | `pg_class.relallvisible`, `relpages` |
| Bảng có nhiều dead tuples ước lượng không? | `pg_stat_user_tables.n_dead_tup` |
| VACUUM/autovacuum đã chạy gần đây chưa? | `last_vacuum`, `last_autovacuum` |
| VACUUM đang xử lý tới đâu? | `pg_stat_progress_vacuum` |
| Tuổi XID của bảng/database cao không? | `age(relfrozenxid)`, `age(datfrozenxid)` |
| MultiXact age cần quan sát không? | `mxid_age(relminmxid)` |
| Có transaction lâu giữ chân cleanup không? | `pg_stat_activity` và giám sát transaction horizon |
| Có replication slot giữ xmin không? | `pg_replication_slots` |

Một chỉ số riêng không đủ để kết luận nguyên nhân. Ví dụ:

- `Heap Fetches` cao không chứng minh autovacuum đã lỗi.
- `n_dead_tup` thấp không bảo đảm mọi trang all-visible.
- `relallvisible` cao không chứng minh query đã dùng index-only scan.
- XID age cao không đồng nghĩa bảng có nhiều dead tuples.
- `all_frozen` thấp không tự có nghĩa có rủi ro wraparound ngay tức thì.

## 38. Case study: báo cáo gần như chỉ đọc nhưng Heap Fetches tăng

Giả sử hệ thống có bảng `event_history` 200 triệu hàng, đa phần chỉ INSERT:

~~~sql
CREATE INDEX idx_event_history_cover
ON event_history (
    tenant_id,
    created_at DESC,
    event_id DESC
)
INCLUDE (event_type);
~~~

Query báo cáo:

~~~sql
SELECT event_id, created_at, event_type
FROM event_history
WHERE tenant_id = 42
ORDER BY created_at DESC, event_id DESC
LIMIT 100;
~~~

Lúc đầu `Index Only Scan` có ít heap fetch. Sau một thời gian ingest tốc độ cao, truy vấn vùng **dữ liệu mới nhất** có thể cần nhiều heap fetch hơn vì những trang mới vừa INSERT chưa được VACUUM đánh dấu all-visible.

### 38.1. Không nên xử lý bằng VACUUM FREEZE toàn bảng ngay

Một hướng điều tra tốt hơn:

1. Xác nhận query vẫn dùng covering index.
2. Xem `Heap Fetches` và buffers theo khoảng thời gian.
3. Quan sát tỷ lệ VM tổng thể và, nếu cần, vùng heap pages liên quan.
4. Xem autovacuum đã chạy chưa và có bị transaction dài giữ chân không.
5. Kiểm tra insert-triggered autovacuum và các ngưỡng theo phiên bản.
6. So sánh độ trễ vùng dữ liệu mới và vùng lịch sử cũ.
7. Chỉ điều chỉnh cấu hình bảo trì khi có bằng chứng.

Một bảng có 95% pages all-visible vẫn có thể có query vùng dữ liệu mới nhất phải heap fetch nhiều, vì phần 5% không all-visible tập trung đúng nơi query thường đọc.

## 39. Case study: bảng cũ cần anti-wraparound vacuum

Giả sử bảng nhật ký cũ ít thay đổi nhưng `age(relfrozenxid)` cao. DBA cần đảm bảo VACUUM có thể xử lý freeze trước ngưỡng an toàn.

Một số bước:

~~~sql
SELECT
    c.oid::regclass AS relation_name,
    age(c.relfrozenxid) AS xid_age,
    mxid_age(c.relminmxid) AS mxid_age
FROM pg_class AS c
WHERE c.oid = 'mvcc_lab.events'::regclass;
~~~

Sau đó kiểm tra cấu hình:

~~~sql
SHOW autovacuum_freeze_max_age;
SHOW vacuum_freeze_table_age;
SHOW vacuum_freeze_min_age;
~~~

và thống kê:

~~~sql
SELECT
    last_autovacuum,
    autovacuum_count,
    n_dead_tup
FROM pg_stat_user_tables
WHERE schemaname = 'mvcc_lab'
  AND relname = 'events';
~~~

Nếu thực sự cần can thiệp, thực hiện VACUUM theo kế hoạch vận hành và quan sát tiến độ, blockers, I/O, locks và tác động replication.

Một bảng **không có dead tuples đáng kể** vẫn có thể cần freezing vì tuổi XID. Đó là lý do anti-wraparound vacuum không phải dấu hiệu PostgreSQL đang “dọn dữ liệu chết quá nhiều”.

## 40. Kịch bản kiểm tra trong môi trường lab

Để nối kết các cơ chế của bài, có thể thực hiện theo thứ tự:

1. Tạo bảng `mvcc_lab.events` và index bao phủ.
2. INSERT dữ liệu tổng hợp.
3. Đọc `pg_visibility_map_summary` nếu có extension.
4. Chạy `EXPLAIN (ANALYZE, BUFFERS)` với query chỉ đọc các cột trong index.
5. Chạy `VACUUM (ANALYZE)` ngoài transaction.
6. Quan sát lại `all_visible` và `Heap Fetches`.
7. UPDATE một nhóm hàng, rồi đo lại.
8. Chạy VACUUM lần nữa và quan sát sự thay đổi.
9. Thử `VACUUM (FREEZE, VERBOSE, ANALYZE)` **chỉ trong lab** để quan sát `all_frozen`.
10. Truy vấn `age(relfrozenxid)` và `mxid_age(relminmxid)` để liên hệ với freezing.

Đây là **lộ trình thực hành**, không phải checklist QA hay runbook production. Kết quả từng bước có thể khác nhau theo trạng thái VM, cache, số transaction và server version.

### 40.1. Vì sao không cần tự tắt autovacuum để thí nghiệm?

Autovacuum có thể chạy xen giữa các bước và thay đổi VM. Đó cũng là một phần hành vi thật của PostgreSQL.

Thay vì tắt autovacuum toàn server, người học nên hiểu rằng hệ thống có bảo trì nền. Nếu cần kết quả hoàn toàn lặp lại, tổ chức một database lab riêng, dataset/transaction timeline có kiểm soát, và ghi rõ giới hạn của thí nghiệm.

## 41. Những sai lầm thường gặp

### Sai lầm 1 — All-visible nghĩa là không có transaction đang hoạt động

Không. Nó chỉ nói trang đủ điều kiện all-visible, không phải toàn database không có transaction.

### Sai lầm 2 — All-visible và all-frozen giống nhau

Không. All-frozen là trạng thái mạnh hơn, có thêm ý nghĩa freezing.

### Sai lầm 3 — Chỉ cần COMMIT thì VM tự chuyển thành all-visible

Không. VACUUM thường cần kiểm tra và đánh dấu trang phù hợp.

### Sai lầm 4 — Index Only Scan luôn không đọc heap

Không. Nếu trang không all-visible, vẫn có thể có Heap Fetches.

### Sai lầm 5 — Heap Fetches bằng số dead tuples

Không. Đây là số lượt truy cập heap phục vụ visibility của scan, không phải số row chết.

### Sai lầm 6 — Cứ nhiều Heap Fetches thì chạy VACUUM FULL

Không. VACUUM FULL rewrite bảng và khóa mạnh; không phải giải pháp mặc định cho VM.

### Sai lầm 7 — ANALYZE tự đánh dấu all-visible

ANALYZE thu thập thống kê; VACUUM mới là cơ chế chính duy trì VM/freezing.

### Sai lầm 8 — Frozen tuple không thể bị sửa

Sai. Freezing không khóa dữ liệu nghiệp vụ.

### Sai lầm 9 — Freeze chỉ cần khi nhiều DELETE

Sai. Bảng chỉ INSERT, giữ lâu vẫn cần chống wraparound.

### Sai lầm 10 — relallvisible là giá trị VM trực tiếp, luôn cập nhật tức thì

Sai. Catalog dùng cho planner và có thể trễ so với VM thực tế.

### Sai lầm 11 — n_dead_tup là COUNT chính xác

Không. Đây thường là số liệu ước lượng.

### Sai lầm 12 — Tỷ lệ all-visible 90% nghĩa query chỉ heap fetch 10% hàng

Không. VM ở cấp trang; query có thể tập trung vào 10% trang nóng.

### Sai lầm 13 — All-frozen nghĩa VACUUM sẽ không bao giờ đụng tới trang

Không. Trang có thể thay đổi, và các hoạt động khác vẫn truy cập nó.

### Sai lầm 14 — Tắt autovacuum để tránh ảnh hưởng hiệu năng

Có thể gây bloat, thiếu visibility map maintenance và rủi ro XID wraparound.

### Sai lầm 15 — XID age tương đương thời gian theo ngày

Không. Tuổi tính theo giao dịch, không phải lịch.

### Sai lầm 16 — Chỉ nhìn relfrozenxid, bỏ qua MultiXact

Có thể bỏ sót áp lực wraparound liên quan `relminmxid`.

### Sai lầm 17 — VACUUM luôn dọn được mọi dead tuple

Transaction/replication horizon có thể giữ phiên bản cũ.

### Sai lầm 18 — Cứ index INCLUDE đủ cột là luôn nhanh

Index rộng có chi phí ghi/lưu trữ, và VM ảnh hưởng số heap fetch.

### Sai lầm 19 — VACUUM FREEZE toàn bảng là tuning mặc định tốt nhất

Có thể tốn I/O/WAL và làm chậm workload; lựa chọn dựa trên tuổi XID và kế hoạch bảo trì.

### Sai lầm 20 — Chỉnh sửa tệp _vm để “cải thiện” index-only scan

Rất nguy hiểm. VM là cấu trúc nội bộ phải được PostgreSQL cập nhật an toàn.

## 42. Bài tập thực hành

### Bài 1 — Hai bit VM

Một trang có `all_visible=true` nhưng `all_frozen=false`. Điều này có thể hợp lệ không? Giải thích.

**Gợi ý:** có; trang có thể đủ visible nhưng còn XID/MultiXact chưa freeze.

### Bài 2 — Quan hệ bao hàm

`all_frozen=true` có kéo theo `all_visible=true` không?

**Gợi ý:** có.

### Bài 3 — COMMIT và VM

Một INSERT vừa commit, trang của nó có chắc đã all-visible không?

**Gợi ý:** không.

### Bài 4 — UPDATE một hàng

Chỉ một hàng trên một trang all-visible bị UPDATE. Vì sao index-only scan của những hàng khác trên cùng trang cũng có thể phải tới heap?

**Gợi ý:** VM đánh dấu theo trang, không theo hàng.

### Bài 5 — Index Only Scan

Một query dùng `Index Only Scan` nhưng EXPLAIN báo `Heap Fetches: 500`. Có mâu thuẫn không?

**Gợi ý:** không; phải kiểm tra heap khi trang không all-visible.

### Bài 6 — Missing column

Index chỉ chứa `(account_id, occurred_at, id) INCLUDE(amount)`. Query SELECT thêm `note`. VM có giúp index đó cung cấp note không?

**Gợi ý:** không.

### Bài 7 — ANALYZE và VACUUM

Phân biệt chức năng chính của `ANALYZE` và `VACUUM`.

**Gợi ý:** planner statistics so với tuple cleanup/VM/freezing.

### Bài 8 — Quan sát VM

Viết SQL đếm trang all-visible và all-frozen của `mvcc_lab.events` bằng extension.

**Gợi ý:** `pg_visibility_map_summary('mvcc_lab.events'::regclass)`.

### Bài 9 — Xem trang chưa all-visible

Viết query lấy 20 `blkno` đầu tiên có `all_visible=false`.

**Gợi ý:** `pg_visibility_map` với WHERE NOT all_visible.

### Bài 10 — Catalog stats

Từ `pg_class`, đọc `relpages`, `reltuples` và `relallvisible`.

**Gợi ý:** lọc theo `oid = 'mvcc_lab.events'::regclass`.

### Bài 11 — Tính tỷ lệ

Một bảng có 1000 heap pages, 700 trang all-visible. Tỷ lệ all-visible pages là bao nhiêu? Có bằng tỷ lệ hàng đã commit không?

**Gợi ý:** 70%; không phải tỷ lệ hàng.

### Bài 12 — Frozen không phải read-only

Có thể UPDATE một tuple đã frozen không?

**Gợi ý:** có, nếu quyền và constraint cho phép.

### Bài 13 — XID age

Viết query xem `age(relfrozenxid)` của một bảng.

**Gợi ý:** `pg_class` và `age(c.relfrozenxid)`.

### Bài 14 — Database horizon

Viết query xếp database theo `age(datfrozenxid)` giảm dần.

**Gợi ý:** `pg_database`.

### Bài 15 — MultiXact

Dùng hàm nào để xem tuổi MultiXact từ `relminmxid`?

**Gợi ý:** `mxid_age(relminmxid)`.

### Bài 16 — Aggressive vacuum

Aggressive vacuum có thể bỏ qua các trang đã all-frozen không?

**Gợi ý:** có, theo điều kiện an toàn.

### Bài 17 — VACUUM FREEZE

Câu `VACUUM (FREEZE)` có phải giải pháp mặc định cho mọi bảng lớn không?

**Gợi ý:** không; cân nhắc I/O, WAL và tuổi XID.

### Bài 18 — Transaction lâu

Một transaction giữ snapshot cũ nhiều giờ. Nó có thể ảnh hưởng VACUUM thế nào?

**Gợi ý:** giữ phiên bản cũ, cản trở cleanup và ảnh hưởng VM/freezing.

### Bài 19 — Replication slot

Một logical slot giữ `catalog_xmin`. Tại sao cần điều tra trước khi xóa slot?

**Gợi ý:** consumer có thể phụ thuộc slot; ảnh hưởng cleanup và khả năng đồng bộ.

### Bài 20 — INSERT-only

Bảng chỉ thêm mới, không sửa/xóa. Có cần VACUUM/freeze không?

**Gợi ý:** có, cho all-visible và XID protection.

### Bài 21 — Heap Fetches sau UPDATE

Tại sao query covering index có thể có nhiều heap fetch hơn sau đợt UPDATE dù chưa đổi SQL/index?

**Gợi ý:** trang mất all-visible.

### Bài 22 — HOT

Cập nhật `note` không có trong index có đảm bảo luôn HOT không? HOT có nghĩa trang vẫn all-visible không?

**Gợi ý:** không cho cả hai; còn điều kiện không gian/trang và visibility.

### Bài 23 — VACUUM FULL

Vì sao không dùng `VACUUM FULL` chỉ để tăng số trang all-visible?

**Gợi ý:** rewrite/lock mạnh, không phải tối ưu mặc định.

### Bài 24 — Planner

Vì sao có `relallvisible` cao nhưng một SELECT vẫn không chọn Index Only Scan?

**Gợi ý:** index thiếu cột, chọn lọc, cost, sort và kế hoạch tổng thể.

### Bài 25 — Bảng lịch sử

Bảng gần như chỉ đọc có tỷ lệ all-frozen cao. Nó có lợi gì với future aggressive vacuum?

**Gợi ý:** skip nhiều trang không cần freeze.

### Bài 26 — Bảng nóng

Một bảng UPDATE liên tục có `all_visible_percent` thấp. Điều này có tự là lỗi cấu hình không?

**Gợi ý:** không; write churn có thể là nguyên nhân tự nhiên.

### Bài 27 — Scope của VM

VM kiểm tra quyền RLS hay tình trạng MVCC visibility?

**Gợi ý:** MVCC; RLS xử lý riêng.

### Bài 28 — Chọn chỉ số

Muốn biết số lần query thật sự phải vào heap khi Index Only Scan, xem `pg_class.relallvisible` hay `EXPLAIN Heap Fetches`?

**Gợi ý:** EXPLAIN ANALYZE Heap Fetches.

### Bài 29 — pg_stat_user_tables

`n_dead_tup` có phải số dead tuple chính xác, luôn cập nhật tức thì không?

**Gợi ý:** thường là ước lượng.

### Bài 30 — Blocker và hành động

VACUUM không thu dọn được nhiều dead tuples vì một transaction lâu. Bạn nên kiểm tra những gì trước khi thay autovacuum settings?

**Gợi ý:** `pg_stat_activity`, snapshot/lock, replication horizons, phiên bản và quyền.

## 43. Tổng kết

- **MVCC** giữ các phiên bản tuple để nhiều transaction có snapshot khác nhau đọc dữ liệu đúng.
- **Visibility map** lưu hai bit theo **trang heap**: `all-visible` và `all-frozen`; nó không phải bảng hay index truy vấn theo khóa.
- **`all-frozen` kéo theo `all-visible`**, nhưng trang all-visible có thể chưa được freeze hoàn toàn.
- **VACUUM** giúp thu dọn tuple chết, duy trì VM và freeze metadata khi đủ điều kiện; **ANALYZE** chủ yếu cập nhật thống kê planner.
- **INSERT/UPDATE/DELETE** có thể xóa cờ VM của những trang bị thay đổi; chỉ COMMIT không bảo đảm trang tự được đánh dấu all-visible trở lại.
- **Index Only Scan** vẫn có thể tới heap khi VM của trang đích không all-visible. Chỉ số **`Heap Fetches`** trong `EXPLAIN (ANALYZE, BUFFERS)` phản ánh công việc thực tế của node.
- **Index bao phủ đủ cột** và **VM all-visible** là hai điều kiện bổ sung nhau; VM không tự cung cấp cột không nằm trong index.
- **Freezing** giúp bảo vệ trước XID/MultiXact wraparound và giảm công việc quét future aggressive vacuum; nó **không làm hàng thành read-only**.
- **`pg_visibility`** cho phép quan sát cờ VM theo trang; **`pg_class.relallvisible`** là thông tin catalog cho planner và có thể không tức thời.
- **`age(relfrozenxid)`**, **`age(datfrozenxid)`**, **`mxid_age(relminmxid)`** và các thống kê autovacuum giúp hiểu sức khỏe freezing lâu dài.
- Transaction dài, replication horizons và write churn có thể ảnh hưởng khả năng cleanup và trạng thái VM.
- Không dùng `VACUUM FULL`, `VACUUM FREEZE` hoặc tắt autovacuum như phản xạ khi thấy Heap Fetches cao; cần kiểm chứng trên workload và giới hạn vận hành thật.

Mối liên hệ cần nhớ:

~~~text
MVCC tạo nhiều phiên bản tuple
           |
           v
VACUUM kiểm tra/thu dọn/freeze khi an toàn
           |
           v
Visibility map ghi nhận trạng thái cấp trang
           |
           +--> all-visible
           |       |
           |       v
           |   Index Only Scan có thể
           |   giảm heap visibility fetches
           |
           +--> all-frozen
                   |
                   v
               Aggressive VACUUM có thể
               bỏ qua những trang đã freeze
~~~

Hiểu đúng ba cơ chế **MVCC – visibility map – freezing** giúp giải thích vì sao cùng một truy vấn PostgreSQL có thể chạy nhanh hoặc chậm khác nhau theo thời điểm, đồng thời cho phép vận hành autovacuum và chỉ mục với những quyết định dựa trên bằng chứng thay vì phỏng đoán.
