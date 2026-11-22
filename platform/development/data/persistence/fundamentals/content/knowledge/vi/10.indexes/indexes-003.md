# Quét toàn bộ dữ liệu so với truy cập qua chỉ mục

Trong hệ thống lưu trữ bền vững, cùng một câu truy vấn SQL có thể được thực thi theo nhiều cách: đọc lần lượt các trang chứa dữ liệu của bảng, hoặc tra một cấu trúc chỉ mục để xác định những hàng cần lấy. Sự khác biệt này ảnh hưởng trực tiếp đến độ trễ, lượng I/O, bộ nhớ đệm và khả năng phục vụ đồng thời của ứng dụng Java. Có chỉ mục **không đồng nghĩa** với việc cơ sở dữ liệu sẽ sử dụng chỉ mục, và sử dụng chỉ mục cũng **không mặc nhiên nhanh hơn** quét toàn bảng.

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích cơ chế `full table scan` (`sequential scan`) và truy cập qua chỉ mục (`index scan`).
- So sánh chi phí đọc tuần tự với chi phí dò chỉ mục rồi truy cập các hàng dữ liệu.
- Nhận diện khi nào bộ tối ưu truy vấn có lý do chọn quét toàn bảng dù đã tồn tại chỉ mục.
- Đọc các dấu hiệu quan trọng trong kế hoạch `EXPLAIN` của PostgreSQL, rồi kiểm chứng bằng số liệu thực tế.
- Đề xuất chỉ mục phù hợp cho truy vấn từ tầng persistence của ứng dụng Java mà không đánh đổi quá mức hiệu năng ghi.

## 1. Hai con đường để tìm dữ liệu

Giả sử hệ thống bán hàng lưu đơn hàng trong bảng `orders`. Một API Java cần lấy 20 đơn gần nhất của một khách hàng, còn một báo cáo cuối ngày cần xử lý hầu hết đơn đã thanh toán.

Hai nhu cầu đều đọc từ một bảng nhưng khác nhau về **tỷ lệ hàng cần lấy**, **thứ tự đầu ra** và **số trang dữ liệu phải truy cập**. Bộ tối ưu (`query optimizer`) cân nhắc những yếu tố đó để chọn *đường truy cập* (`access path`).

### 1.1. Quét toàn bộ bảng: đọc dữ liệu rồi lọc

Với quét toàn bảng, hệ quản trị đọc các trang dữ liệu của bảng, kiểm tra điều kiện `WHERE` trên các hàng được đọc và chỉ trả lại những hàng thỏa điều kiện.

~~~text
Bảng orders trên đĩa / trong bộ nhớ đệm
[Trang 1][Trang 2][Trang 3] ... [Trang N]
    |       |       |             |
    +-------+-------+-------------+
           đọc và kiểm tra WHERE
                    |
             các hàng phù hợp
~~~

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Nếu gần như toàn bộ đơn hàng có trạng thái `PAID`, đọc bảng một lượt có thể rẻ hơn dò một chỉ mục rồi liên tục quay lại bảng để lấy từng hàng.

**Điểm quan trọng:**

- Từ “toàn bộ” mô tả *đường truy cập*: cơ sở dữ liệu phải xem xét phần lớn hoặc tất cả các trang của bảng. Điều này **không** có nghĩa mọi hàng đều được trả về.
- Đọc tuần tự thường tận dụng tốt việc đọc trước (`read-ahead`), bộ nhớ đệm và I/O theo lô. Quét toàn bảng có thể được chia cho nhiều tiến trình thực thi.
- Với bảng rất nhỏ, chi phí khởi động và lần theo chỉ mục có thể lớn hơn việc đọc thẳng vài trang.
- Trong PostgreSQL, toán tử tương ứng thường mang tên `Seq Scan` hoặc `Parallel Seq Scan`. Tên gọi và cách tổ chức vật lý khác nhau giữa các hệ quản trị.

### 1.2. Truy cập qua chỉ mục: tìm vị trí trước, lấy dữ liệu sau

Một chỉ mục B-tree thường tổ chức khóa tìm kiếm trong cấu trúc nhiều tầng, từ nút gốc tới các trang lá. Trang lá chứa khóa và thông tin định vị hàng, hoặc dữ liệu cần thiết tùy loại chỉ mục và hệ quản trị.

~~~text
                 Chỉ mục B-tree
                    [gốc]
                   /     \
             [nhánh]     [nhánh]
              /   \       /   \
           [lá]  [lá]   [lá]  [lá]
                    |
             định vị hàng phù hợp
                    |
                Bảng orders
            [các trang dữ liệu]
~~~

Khi tìm đơn của một khách hàng, hệ quản trị có thể:

1. Dò cây tới vùng khóa `customer_id = 4242`.
2. Đọc những mục chỉ mục thuộc khách hàng đó.
3. Truy cập hàng trong bảng nếu những cột cần trả về chưa có đủ trong chỉ mục, hoặc cần xác minh tính hiển thị của hàng.
4. Dừng sau khi tìm đủ 20 hàng nếu điều kiện lọc và thứ tự chỉ mục cho phép.

Đường này thường lợi thế khi số hàng cần lấy nhỏ. Tuy vậy, nếu kết quả trải rộng trên nhiều trang bảng, việc truy cập dữ liệu theo vị trí rời rạc (`random access`) có thể đắt hơn một lượt đọc tuần tự.

**Lưu ý về thuật ngữ:** `index scan` không bảo đảm rằng chỉ vài mục chỉ mục được đọc. Một kế hoạch có thể duyệt cả một dải rất dài, thậm chí gần hết chỉ mục. Điều cần quan sát là *lượng dữ liệu thực tế được chạm tới*, không chỉ tên toán tử.

### 1.3. Sơ đồ lựa chọn đường truy cập

~~~mermaid
flowchart TD
    A["Truy vấn SQL và tham số"] --> B["Bộ tối ưu ước lượng số hàng, I/O, CPU, thứ tự"]
    B --> C{"Đường truy cập ước tính rẻ hơn?"}
    C -->|"Đọc bảng"| D["Sequential / full table scan"]
    C -->|"Tra chỉ mục"| E["Index scan / index-only / bitmap"]
    D --> F["Lọc, sắp xếp, trả kết quả"]
    E --> F
    F --> G["Tầng persistence Java nhận dữ liệu"]
~~~

Sơ đồ thể hiện nguyên tắc lựa chọn theo *chi phí ước tính*. Kế hoạch cụ thể phụ thuộc hệ quản trị, chỉ mục đang có, thống kê và dữ liệu tại thời điểm thực thi.

## 2. So sánh chi phí: tại sao “dùng index” chưa chắc nhanh?

Giả sử bảng có `N` hàng và truy vấn trả `k` hàng. Tỷ lệ chọn lọc (`selectivity`, theo nghĩa tỷ lệ khớp) là:

~~~text
tỷ lệ hàng khớp = k / N
~~~

Ví dụ, bảng có 10 triệu đơn mà một khách hàng chỉ sở hữu 50 đơn thì tỷ lệ hàng khớp rất thấp. Ngược lại, nếu 9 triệu đơn có trạng thái `PAID`, tỷ lệ hàng khớp rất cao.

Ở mức trực giác:

- **Quét bảng:** chi phí chủ yếu đến từ đọc các trang bảng và đánh giá điều kiện trên các hàng.
- **Truy cập chỉ mục:** chi phí gồm việc dò/duyệt chỉ mục **cộng** với đọc các trang bảng cần thiết; có thể tiết kiệm phần đọc bảng nếu chỉ mục đã chứa đủ dữ liệu.
- **Trả ít hàng không luôn rẻ:** một điều kiện có thể khớp ít hàng nhưng phải quét cả bảng nếu không có đường truy cập hiệu quả.
- **Trả nhiều hàng không luôn đắt:** các hàng nằm sát nhau và được đọc tuần tự có thể tiết kiệm I/O.

Có thể hình dung độ phức tạp của một lần lọc toàn bảng là khoảng `O(N)` theo số hàng, còn dò B-tree có thành phần tìm khóa khoảng `O(log N)` rồi đọc các mục phù hợp. **Đây chỉ là trực giác về thuật toán**; thời gian thực tế chịu ảnh hưởng mạnh của số trang, cache, sự phân bố vị trí hàng, CPU và chi phí trả kết quả. Không được dùng biểu thức độ phức tạp này để suy ra một ngưỡng chọn chỉ mục cố định.

| Tiêu chí | Quét toàn bảng | Truy cập qua chỉ mục |
|---|---|---|
| Đường đọc chủ yếu | Các trang dữ liệu của bảng | Trang chỉ mục, có thể kèm các trang bảng |
| Thường có lợi | Bảng nhỏ; đọc phần lớn dữ liệu; lọc kém chọn lọc | Điều kiện chọn lọc tốt; truy vấn tìm vài hàng; `ORDER BY ... LIMIT` khớp thứ tự chỉ mục |
| Mẫu I/O | Thường có tính tuần tự, có thể đọc trước | Có thể phát sinh nhiều lần truy cập bảng rời rạc |
| Sắp xếp | Có thể cần bước `Sort` | Có thể tránh `Sort` nếu chỉ mục cung cấp đúng thứ tự |
| Chi phí duy trì khi ghi | Không tạo thêm chi phí cập nhật chỉ mục cho đường quét | Bản thân chỉ mục phải được duy trì khi `INSERT`, `UPDATE`, `DELETE` |
| Rủi ro hiểu sai | Thấy `Seq Scan` là kết luận truy vấn lỗi | Thấy `Index Scan` là kết luận truy vấn đã tối ưu |

Không tồn tại quy tắc phổ quát kiểu “truy vấn trả dưới 10% dữ liệu thì luôn dùng index”. Ngưỡng thực tế thay đổi theo độ rộng hàng, số trang cần đọc, cách bố trí dữ liệu, hệ quản trị, bộ nhớ đệm và thiết bị lưu trữ.

## 3. Ví dụ thực hành với PostgreSQL

Phần này dùng **cú pháp PostgreSQL** để quan sát hai đường truy cập. Hệ quản trị khác có công cụ và tên toán tử riêng, nhưng các nguyên lý vẫn áp dụng. Hãy thực hiện trên cơ sở dữ liệu thử nghiệm với dữ liệu đủ lớn và có phân bố đại diện; không suy ra hiệu năng từ một bảng chỉ có vài chục dòng.

### 3.1. Lược đồ và truy vấn cần tối ưu

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  BIGINT NOT NULL,
    placed_at    TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

-- Giả định sau đó đã nạp lượng lớn đơn hàng thử nghiệm.
ANALYZE orders;
~~~

API lấy 20 đơn gần nhất của khách hàng 4242:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, placed_at, total_amount
FROM orders
WHERE customer_id = 4242
ORDER BY placed_at DESC, id DESC
LIMIT 20;
~~~

Trước khi tạo chỉ mục theo `customer_id`, kế hoạch có thể cần đọc toàn bảng rồi sắp xếp hoặc dùng phương án quét song song. Chỉ mục khóa chính trên `id` **không tự động giúp** lọc hiệu quả theo `customer_id`.

Tạo chỉ mục phù hợp với điều kiện và thứ tự:

~~~sql
CREATE INDEX idx_orders_customer_time_id
    ON orders (customer_id, placed_at DESC, id DESC);

ANALYZE orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, placed_at, total_amount
FROM orders
WHERE customer_id = 4242
ORDER BY placed_at DESC, id DESC
LIMIT 20;
~~~

Với phân bố dữ liệu phù hợp, PostgreSQL có thể chọn kế hoạch có dạng rút gọn:

~~~text
Limit
  -> Index Scan using idx_orders_customer_time_id on orders
       Index Cond: (customer_id = 4242)
~~~

Đây là **minh họa hình dạng kế hoạch**, không phải kết quả đo hoặc cam kết rằng PostgreSQL luôn chọn kế hoạch này. Chỉ mục giúp tìm vùng đơn của một khách hàng theo thời gian giảm dần; `LIMIT 20` giúp dừng sớm. Do `total_amount` không nằm trong chỉ mục trên, kế hoạch `Index Scan` có thể phải đọc hàng từ bảng.

Cột `id` được đặt cuối khóa chỉ mục để tạo thứ tự ổn định khi nhiều đơn có cùng `placed_at`. Nếu muốn phân trang theo con trỏ (`keyset pagination`), có thể dùng cùng thứ tự khóa:

~~~sql
SELECT id, placed_at, total_amount
FROM orders
WHERE customer_id = 4242
  AND (placed_at, id) < (
      TIMESTAMPTZ '2026-11-20 10:00:00+07',
      900001
  )
ORDER BY placed_at DESC, id DESC
LIMIT 20;
~~~

Ví dụ giả định cặp thời gian–ID ở điều kiện trên là khóa cuối của trang trước. Điều kiện con trỏ phải khớp chính xác với quy tắc sắp xếp và phạm vi lọc của API.

### 3.2. Có chỉ mục nhưng quét toàn bảng vẫn có thể tốt hơn

Xét báo cáo đọc tất cả đơn có trạng thái `PAID`. Giả sử `PAID` chiếm khoảng 90% bảng:

~~~sql
CREATE INDEX idx_orders_status ON orders (status);
ANALYZE orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Một kế hoạch hợp lý trong tình huống này có thể là:

~~~text
Seq Scan on orders
  Filter: (status = 'PAID'::text)
~~~

Vì truy vấn cần gần như mọi hàng và mọi cột, dùng chỉ mục `status` có thể dẫn tới rất nhiều lần lấy dữ liệu từ bảng. Quét các trang bảng một lượt có thể ít tốn kém hơn. Việc đã tạo `idx_orders_status` không buộc optimizer chọn chỉ mục.

Chỉ mục trên `status` ở đây dùng để **thử nghiệm**. Trong thiết kế thật, chỉ giữ nó nếu có các truy vấn được hưởng lợi đủ nhiều để bù chi phí lưu trữ và cập nhật; chẳng hạn điều kiện tìm một trạng thái hiếm, tùy phân bố dữ liệu.

### 3.3. Đọc kế hoạch thực thi đúng cách

Trong PostgreSQL, chú ý các trường sau:

| Dấu hiệu `EXPLAIN` | Cách hiểu và câu hỏi cần đặt |
|---|---|
| `Seq Scan` / `Parallel Seq Scan` | Bảng được quét; kết quả cần nhiều hàng hay thiếu chỉ mục phù hợp? |
| `Index Scan` | Dò chỉ mục và có thể lấy thêm hàng từ bảng; số trang bảng thực tế là bao nhiêu? |
| `Index Only Scan` | Những cột cần đọc có thể lấy từ chỉ mục; có `Heap Fetches` do kiểm tra hiển thị hàng hay không? |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Thu thập vị trí hàng qua chỉ mục rồi đọc trang bảng theo lô; thường là phương án trung gian khi có tương đối nhiều hàng phù hợp |
| `Index Cond` | Điều kiện dùng để giới hạn phần chỉ mục phải duyệt |
| `Filter` / `Rows Removed by Filter` | Điều kiện/hàng vẫn được kiểm tra sau đường truy cập; có đang đọc quá nhiều dữ liệu? |
| `Sort` | Có bước sắp xếp riêng hay không? Nó tốn bao nhiêu thời gian/bộ nhớ? |
| `cost=... rows=...` | Ước lượng của planner, **không** phải mili-giây; số hàng ước lượng có lệch lớn so với thực tế? |
| `actual time=... rows=... loops=...` | Đo khi thực thi với `ANALYZE`; các trị số thường được báo theo từng lần lặp, cần chú ý `loops` |
| `Buffers: shared hit/read` | Trang bộ đệm được chạm tới/được nạp vào bộ nhớ dùng chung; `shared read` không mặc nhiên là một lần đọc đĩa vật lý |

`EXPLAIN` không có `ANALYZE` chỉ đưa ra kế hoạch **ước tính**. `EXPLAIN (ANALYZE, BUFFERS)` **thực sự chạy truy vấn** để đo thời gian và bộ đệm; với câu lệnh ghi dữ liệu, điều này còn có thể gây thay đổi dữ liệu. Chỉ dùng trên môi trường và thời điểm thích hợp. Truy vấn đo cũng có thể chậm vì cache lạnh, tài nguyên cạnh tranh hoặc dữ liệu phân bố khác sản xuất.

Khi đánh giá, so sánh ít nhất: tổng thời gian thực thi, lượng trang bị chạm, số hàng thực tế, sai số ước lượng, và có phát sinh `Sort` không. Đừng nhìn riêng một dòng `Index Scan`.

## 4. Những yếu tố khiến optimizer chọn đường khác dự đoán

### 4.1. Tỷ lệ chọn lọc và vị trí vật lý của các hàng

Hai truy vấn đều trả 10.000 hàng nhưng có chi phí khác nhau nếu:

- 10.000 hàng nằm gần nhau trên một số trang dữ liệu.
- 10.000 hàng nằm rải rác trên hàng nghìn trang khác nhau.

Một chỉ mục chứa khóa đã sắp xếp **không nhất thiết** đồng nghĩa dữ liệu trong bảng được lưu liên tiếp theo khóa đó. Sự tương quan giữa thứ tự khóa và vị trí vật lý của hàng có thể thay đổi sau nhiều đợt ghi, cập nhật và xóa.

### 4.2. Điều kiện có dùng được cấu trúc chỉ mục không?

Với chỉ mục B-tree thông thường trên `placed_at`, bộ tối ưu thường tận dụng tốt một khoảng thời gian có giới hạn rõ:

~~~sql
-- Thường thuận lợi cho B-tree trên placed_at:
WHERE placed_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-11-02 00:00:00+07'
~~~

Trong khi điều kiện dùng hàm lên cột có thể ngăn việc dùng **chỉ mục thông thường trên cột gốc** để giới hạn vùng tìm kiếm:

~~~sql
-- Dễ làm chỉ mục B-tree thông thường trên placed_at kém hữu ích:
WHERE placed_at::date = DATE '2026-11-01'
~~~

Ngoài hiệu năng, kiểu `TIMESTAMPTZ` còn khiến phép đổi sang `date` phụ thuộc múi giờ phiên làm việc. Cần xác định rõ ranh giới ngày theo nghiệp vụ. Một số hệ quản trị hỗ trợ chỉ mục trên biểu thức phù hợp; không nên mặc định chỉ mục đó đã tồn tại.

Tương tự, tìm chuỗi theo mẫu `LIKE '%abc'` thường không dùng hiệu quả B-tree thông thường để xác định điểm bắt đầu, trong khi tìm theo tiền tố như `LIKE 'abc%'` có thể tận dụng chỉ mục phù hợp với kiểu dữ liệu, collation và cấu hình của hệ quản trị. Tìm kiếm chứa chuỗi có thể cần kiểu chỉ mục chuyên dụng.

### 4.3. Thứ tự cột trong chỉ mục ghép

Với:

~~~sql
CREATE INDEX idx_orders_customer_time_id
    ON orders (customer_id, placed_at DESC, id DESC);
~~~

Truy vấn `WHERE customer_id = ? ORDER BY placed_at DESC, id DESC` là một trường hợp phù hợp vì lọc theo cột đầu rồi dùng tiếp thứ tự các cột sau.

Trái lại, một truy vấn chỉ lọc theo `placed_at` thường **không khai thác hiệu quả như nhau** chỉ mục này vì thiếu điều kiện trên `customer_id`. Một số phiên bản/hệ quản trị có kỹ thuật đặc biệt để khai thác chỉ mục trong vài trường hợp thiếu cột đầu; vì vậy phải kiểm tra kế hoạch, không suy luận tuyệt đối.

### 4.4. Truy vấn lấy quá nhiều cột

`SELECT *` có thể buộc cơ sở dữ liệu quay lại bảng để lấy các cột không có trong chỉ mục. Một truy vấn chỉ cần vài cột có thể trở thành ứng viên cho `index-only scan` hoặc chỉ mục bao phủ (`covering index`).

Ví dụ PostgreSQL có cú pháp `INCLUDE`:

~~~sql
-- Phương án thay thế chỉ mục trước nếu số đo chứng minh có lợi:
CREATE INDEX idx_orders_customer_time_cover
    ON orders (customer_id, placed_at DESC, id DESC)
    INCLUDE (total_amount);
~~~

Chỉ mục này lưu thêm `total_amount` để phục vụ truy vấn mẫu. Tuy nhiên, `Index Only Scan` của PostgreSQL vẫn có thể phải kiểm tra trang bảng để xác minh tính hiển thị hàng theo MVCC. Ngoài ra, chỉ mục bao phủ lớn hơn và tốn công bảo trì hơn. **Đừng giữ cả hai chỉ mục gần trùng nhau chỉ vì chúng đều giúp đọc**; chọn bằng số liệu về tải đọc và ghi.

### 4.5. Thống kê, tham số và dữ liệu thay đổi

Optimizer dựa vào thống kê về số hàng, phân bố giá trị và tương quan để ước lượng chi phí. Sau đợt nạp dữ liệu lớn hoặc khi phân bố giá trị thay đổi nhiều, thống kê chưa cập nhật có thể khiến ước lượng số hàng sai lệch. Trong PostgreSQL, `ANALYZE` cập nhật thống kê cho bộ lập kế hoạch; cơ chế tự động có thể thực hiện việc này theo cấu hình.

Cùng câu SQL với tham số khác nhau cũng có thể cần đường truy cập khác nhau. Ví dụ `status = 'FAILED'` khớp rất ít hàng nhưng `status = 'PAID'` khớp đa số. Với prepared statements, việc sử dụng kế hoạch chung hay riêng cho từng giá trị tham số phụ thuộc hệ quản trị và thiết lập; khi phân tích phải dùng giá trị tham số đại diện, thay vì giả định kế hoạch sẽ luôn giống nhau.

## 5. Từ truy vấn đến tầng persistence trong Java

Ứng dụng Java thường truy cập dữ liệu qua JDBC, JPA hoặc một thư viện persistence. Những công cụ này xây dựng/thực thi câu truy vấn; **đường truy cập vật lý cuối cùng vẫn do hệ quản trị lựa chọn**. Vì vậy, đánh giá hiệu năng phải bắt đầu từ SQL thực được gửi xuống cơ sở dữ liệu và kế hoạch của nó.

Ví dụ một repository đơn giản dùng JDBC:

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<Long> findRecentOrderIds(long customerId) throws SQLException {
        String sql =
            "SELECT id FROM orders " +
            "WHERE customer_id = ? " +
            "ORDER BY placed_at DESC, id DESC " +
            "LIMIT 20";

        List<Long> ids = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    ids.add(rs.getLong("id"));
                }
            }
        }

        return ids;
    }
}
~~~

Ở đây:

- `PreparedStatement` truyền tham số theo kiểu dữ liệu và tránh ghép trực tiếp đầu vào người dùng vào SQL. Nó không tự tạo chỉ mục.
- `WHERE customer_id = ?`, `ORDER BY placed_at DESC, id DESC` và `LIMIT 20` làm rõ mẫu truy cập mà chỉ mục ghép có thể hỗ trợ.
- `try-with-resources` đóng `ResultSet`, câu lệnh và trả `Connection` về pool (nếu dùng pool). Quản lý kết nối đúng giúp ứng dụng ổn định nhưng không sửa được truy vấn đọc quá nhiều trang.
- Với JPA/Hibernate, cần quan sát SQL thực tế sinh ra, bao gồm bộ lọc, `ORDER BY`, giới hạn trang và các lần truy vấn bổ sung. Tên phương thức repository không phải bằng chứng cơ sở dữ liệu đang sử dụng chỉ mục.

Nếu API cần 20 hàng nhưng mã Java tải toàn bộ danh sách rồi mới cắt 20 phần tử trong bộ nhớ, chỉ mục không thể bù toàn bộ chi phí truyền và tạo đối tượng. Nên giới hạn số hàng ở SQL khi quy tắc nghiệp vụ cho phép.

## 6. Quy trình ra quyết định khi tối ưu truy vấn

Không bắt đầu bằng yêu cầu “thêm index cho cột này”. Hãy bắt đầu bằng truy vấn cụ thể và công việc mà ứng dụng đang thực hiện:

1. **Xác định nhu cầu:** truy vấn nằm trên đường gọi API nào, yêu cầu độ trễ bao nhiêu, trả mấy hàng, có cần sắp xếp hay phân trang không?
2. **Lấy SQL thực và tham số đại diện:** lưu ý các giá trị phổ biến và hiếm, độ lớn dữ liệu hiện tại và tăng trưởng dự kiến.
3. **Đo kế hoạch cơ sở:** kiểm tra `EXPLAIN`, thời gian, số trang, số hàng, `Sort` và độ lệch giữa số hàng ước lượng với thực tế.
4. **Phân tích ứng viên:** cân nhắc thay điều kiện lọc, giảm cột lấy về, thêm `LIMIT`, điều chỉnh thứ tự cột trong chỉ mục ghép hoặc tạo chỉ mục mới.
5. **Đo lại trong điều kiện so sánh được:** thử trên dữ liệu và tải đại diện; so sánh cả khi cache ấm/lạnh nếu có liên quan.
6. **Đánh giá tổng chi phí vận hành:** chỉ mục tốn dung lượng, thời gian xây dựng, tài nguyên khi cập nhật dữ liệu, bảo trì và sao lưu. Kiểm tra ảnh hưởng tới `INSERT`/`UPDATE`/`DELETE` trước khi đưa vào hệ thống thật.
7. **Theo dõi sau thay đổi:** đo p95/p99 thời gian truy vấn, thông lượng, đọc trang và các truy vấn bị chậm đi; rà lại khi dữ liệu hoặc lược đồ thay đổi.

| Tình huống | Hướng phân tích ban đầu |
|---|---|
| Một khách hàng có vài chục đơn trong bảng hàng triệu đơn, cần 20 đơn gần nhất | Xem chỉ mục bắt đầu bằng `customer_id`, tiếp theo là cột sắp xếp |
| Báo cáo cần 90% số hàng với nhiều cột | Quét toàn bảng có thể hợp lý; so sánh kế hoạch thực tế trước khi thêm index |
| Bảng cấu hình có vài trăm hàng, đọc gần hết bảng | Chi phí quét nhỏ; tránh tối ưu chỉ dựa trên tên `Seq Scan` |
| Lọc theo ngày bằng hàm trên cột thời gian | Xem lại điều kiện thành khoảng thời gian và ngữ nghĩa múi giờ |
| Có chỉ mục nhưng kế hoạch ước lượng quá ít hàng | Kiểm tra thống kê, phân bố tham số và dữ liệu thực |
| Truy vấn phân trang càng về sau càng chậm | Xem xét phân trang theo con trỏ với thứ tự ổn định và chỉ mục phù hợp |

## 7. Bài tập vận dụng

**Bài 1.** Bảng `orders` có 5 triệu hàng. API lấy 10 đơn mới nhất của một khách hàng; một khách hàng thông thường chỉ có 30 đơn. Chưa có chỉ mục trên `customer_id`. Đường truy cập nào đáng thử đầu tiên và tại sao?

**Bài 2.** Sau khi tạo chỉ mục trên `status`, PostgreSQL vẫn dùng `Seq Scan` cho `SELECT * FROM orders WHERE status = 'PAID'`. `PAID` chiếm 95% bảng. Đây có nhất thiết là lỗi tối ưu không?

**Bài 3.** Một truy vấn có `Index Scan` nhưng rất chậm và số trang `shared hit/read` cao. Bạn cần kiểm tra những gì trước khi kết luận chỉ mục hiệu quả?

**Bài 4.** Hai câu lọc đơn đặt vào ngày 01/11/2026, một câu dùng `placed_at::date`, câu còn lại dùng khoảng `TIMESTAMPTZ`. Vì sao câu thứ hai thường phù hợp hơn với B-tree thông thường, và phải chú ý điều gì về múi giờ?

### Gợi ý đáp án

1. Thử chỉ mục ghép theo `(customer_id, placed_at DESC, id DESC)` để tìm ít hàng, giữ đúng thứ tự và dừng ở `LIMIT 10`; xác minh bằng `EXPLAIN` và số liệu đo.
2. Không. Đọc 95% hàng và tất cả cột thường khiến quét tuần tự rẻ hơn truy cập hàng rải rác qua chỉ mục. Cần dựa vào đo đạc và đặc tính dữ liệu.
3. So sánh số hàng ước lượng/thực tế, số trang bảng bị chạm, số hàng bị lọc sau khi quét, độ chọn lọc, `Sort`, số vòng lặp, điều kiện bộ nhớ đệm và tham số thực tế.
4. Khoảng thời gian giữ nguyên cột làm khóa so sánh, cho phép khoanh vùng B-tree tốt hơn trong nhiều trường hợp. Phải tính ranh giới ngày theo múi giờ nghiệp vụ và dùng khoảng nửa mở `[bắt đầu, ngày kế tiếp)`.

## 8. Ghi nhớ

**Quét toàn bảng và truy cập qua chỉ mục là hai chiến lược đọc dữ liệu, không phải hai mức chất lượng cố định.** Chỉ mục có lợi khi nó giúp tránh đủ nhiều lần đọc dữ liệu, hỗ trợ thứ tự trả kết quả hoặc giới hạn tìm kiếm hiệu quả. Quét tuần tự có lợi khi phải đọc phần lớn bảng hoặc khi bảng nhỏ. Trong thiết kế persistence cho Java, hãy làm rõ mẫu truy vấn, kiểm chứng kế hoạch thực thi, đo dưới tải đại diện và tính cả chi phí ghi, bảo trì chỉ mục. Đó là cách cân bằng độ bền vững, tính đúng đắn và hiệu năng lâu dài.
