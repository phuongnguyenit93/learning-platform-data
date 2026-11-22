# Đọc kế hoạch thực thi để kiểm chứng giả thuyết tối ưu

Trong ứng dụng Java, một truy vấn chậm có thể xuất phát từ nhiều nguyên nhân: thiếu chỉ mục, dùng sai thứ tự cột trong chỉ mục ghép, lọc quá nhiều bản ghi, phép nối tốn kém, thống kê dữ liệu chưa phù hợp, hoặc ứng dụng thực thi cùng một truy vấn quá nhiều lần. Việc thêm chỉ mục theo trực giác có thể không giải quyết được vấn đề, thậm chí làm tăng chi phí ghi và bảo trì dữ liệu.

Bài này hướng dẫn cách **đặt giả thuyết, đọc kế hoạch thực thi (execution plan), kiểm tra bằng số liệu thực tế và quyết định có nên giữ tối ưu hay không**. Ví dụ dùng cú pháp PostgreSQL; tên toán tử và cách đo đạc ở MySQL, SQL Server, Oracle có thể khác, nhưng phương pháp kiểm chứng vẫn tương tự.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

- Phân biệt kế hoạch dự kiến với kế hoạch đã thực thi và biết lúc nào cần dùng từng loại.
- Đọc những thông tin quan trọng: loại quét, điều kiện dùng chỉ mục, số hàng ước lượng và thực tế, số vòng lặp, thao tác sắp xếp, số trang bộ đệm và thời gian thực thi.
- Nêu một giả thuyết tối ưu có thể bác bỏ hoặc xác nhận bằng dữ liệu.
- So sánh kế hoạch trước và sau khi thay đổi chỉ mục hoặc truy vấn, tránh kết luận chỉ dựa trên một lần chạy.
- Liên hệ kết quả với ranh giới persistence của Java: truy vấn tham số hóa, phân trang, số lần truy cập cơ sở dữ liệu, thời gian phản hồi và tính đúng đắn.

## 2. Bắt đầu bằng một truy vấn và một câu hỏi đo được

Giả sử dịch vụ truy xuất lịch sử đơn hàng theo khách hàng trong một tenant. Bảng có cấu trúc tối giản:

~~~sql
CREATE TABLE orders (
    id           bigint PRIMARY KEY,
    tenant_id    bigint NOT NULL,
    customer_id  bigint NOT NULL,
    status       text NOT NULL,
    created_at   timestamptz NOT NULL,
    total_amount numeric(12, 2) NOT NULL
);
~~~

Màn hình cần hiển thị 20 đơn đã thanh toán gần nhất, ưu tiên đơn mới hơn. Truy vấn minh họa với tham số thực tế được thay bằng giá trị thử nghiệm:

~~~sql
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 918
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Điều kiện tenant_id là một phần của ranh giới dữ liệu nhiều tenant; không được xóa điều kiện này chỉ vì có vẻ khiến truy vấn chạy nhanh hơn. Cột id ở cuối ORDER BY giúp kết quả có thứ tự xác định khi nhiều đơn cùng created_at.

Một giả thuyết hữu ích có đủ **triệu chứng → nguyên nhân dự đoán → can thiệp → dấu hiệu kiểm chứng**:

> Truy vấn lấy 20 đơn gần nhất đang đọc rất nhiều hàng không phù hợp và phải sắp xếp trước khi trả kết quả. Nếu tạo chỉ mục ghép theo các điều kiện bằng và thứ tự sắp xếp, bộ máy có thể đọc trực tiếp các hàng phù hợp theo đúng thứ tự, giảm lượng dữ liệu phải duyệt. Giả thuyết được chấp nhận chỉ khi kế hoạch và thời gian đo thực tế xác nhận điều đó.

Đặt tiêu chí trước khi sửa: chẳng hạn giảm số trang đọc, loại bỏ bước Sort lớn và cải thiện độ trễ p95 của thao tác trong ứng dụng dưới tải đại diện. Thời gian 1 truy vấn SQL không phải toàn bộ thời gian của HTTP request.

## 3. Ba cách xem kế hoạch thực thi trong PostgreSQL

### 3.1. Kế hoạch dự kiến, không chạy truy vấn

~~~sql
EXPLAIN
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 918
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

EXPLAIN thông thường cho biết cách bộ tối ưu *dự định* thực thi: quét tuần tự hay chỉ mục, phép nối, sắp xếp và chi phí ước lượng. Nó phù hợp để xem sơ bộ trên dữ liệu thật khi không muốn thực thi một truy vấn nặng.

### 3.2. Kế hoạch đã chạy, có thời gian và số hàng thực tế

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 918
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

- **ANALYZE** thực sự thực thi truy vấn để thu thập thời gian, số hàng và số vòng lặp. Đừng nhầm nó với lệnh ANALYZE cập nhật thống kê cho bộ lập kế hoạch.
- **BUFFERS** bổ sung thống kê trang bộ đệm; nó giúp kiểm tra liệu truy vấn đọc nhiều trang hơn kỳ vọng hay không.
- Với truy vấn ghi, EXPLAIN ANALYZE **cũng thực thi thay đổi dữ liệu**. Không chạy tùy tiện với INSERT, UPDATE, DELETE hoặc câu lệnh có tác dụng phụ. Ngay cả khi thử trong transaction rồi ROLLBACK, một số tác dụng bên ngoài giao dịch vẫn có thể xảy ra.
- Ưu tiên môi trường thử nghiệm có quy mô dữ liệu, thống kê và đặc điểm tải giống sản xuất. Chạy ANALYZE trên production chỉ sau khi đã đánh giá ảnh hưởng về tải và quyền truy cập.

Trong lúc khảo sát, có thể lấy đầu ra có cấu trúc để so sánh bằng công cụ:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)
SELECT id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND customer_id = 918
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

FORMAT JSON hữu ích khi lập báo cáo tự động, nhưng định dạng văn bản dễ đọc bằng mắt hơn khi bắt đầu.

## 4. Cách đọc một cây kế hoạch

Mỗi dòng có thụt lề là một nút trong cây thực thi. Nút con cung cấp dữ liệu cho nút cha. Khi giải thích **luồng dữ liệu**, đọc từ các lá đi lên; khi xác định **mục tiêu truy vấn**, bắt đầu từ nút gốc (ví dụ Limit) và lần theo những nút con tạo ra chi phí lớn.

Ví dụ mô phỏng một nhánh của kế hoạch:

~~~text
Limit  (cost=101.00..101.05 rows=20 width=30)
       (actual time=18.40..18.41 rows=20 loops=1)
  -> Sort  (cost=101.00..102.20 rows=480 width=30)
           (actual time=18.39..18.40 rows=20 loops=1)
       Sort Key: created_at DESC, id DESC
       Sort Method: top-N heapsort  Memory: 28kB
       -> Seq Scan on orders  (cost=0.00..90.00 rows=480 width=30)
                              (actual time=0.07..18.21 rows=530 loops=1)
            Filter: (status = 'PAID'::text)
            Rows Removed by Filter: 125470
Planning Time: 0.40 ms
Execution Time: 18.48 ms
~~~

Các số trên chỉ minh họa, không phải kết quả đo từ cơ sở dữ liệu của người học.

| Trường | Ý nghĩa | Cách diễn giải đúng |
|---|---|---|
| cost=a..b | Chi phí khởi động và tổng chi phí **ước lượng**, theo đơn vị nội bộ của PostgreSQL | Không phải mili giây; dùng để hiểu lựa chọn của planner |
| rows (ước lượng) | Số hàng planner dự đoán nút sẽ trả | Sai lệch lớn so với thực tế có thể làm chọn nhầm chiến lược |
| width | Kích thước trung bình ước lượng của một hàng, tính theo byte | Ảnh hưởng ước tính chi phí truyền, nối, sắp xếp |
| actual time=a..b | Thời gian thực tế đến hàng đầu tiên và đến khi nút hoàn thành, tính bằng ms; là số trung bình mỗi lần khi có nhiều loops | Không cộng thời gian các nút cha/con vì có phần thời gian chồng nhau |
| actual rows | Số hàng thực tế trả về **trung bình mỗi lần thực thi nút** | Khi loops lớn, xét cả hai giá trị để hiểu tổng công việc |
| loops | Số lần nút được thực thi | Một nhánh nhanh nhưng lặp lại hàng nghìn lần vẫn có thể tốn kém |
| Filter | Điều kiện được kiểm tra sau khi lấy hàng từ đường quét hiện tại | Khác với điều kiện đã dùng để định vị trong chỉ mục |
| Index Cond | Điều kiện dùng để thu hẹp phạm vi tìm kiếm trong chỉ mục | Thường là tín hiệu chỉ mục phù hợp với WHERE |
| Rows Removed by Filter | Hàng bị loại bởi Filter tại nút đó | Nhiều hàng bị loại có thể gợi ý điều kiện chưa được đẩy xuống đường truy cập |
| Buffers: shared hit/read | Số trang dữ liệu tìm thấy trong shared buffer / cần nạp vào shared buffer | hit không đồng nghĩa miễn phí; read không luôn bằng số lần đọc đĩa vật lý |
| Planning Time / Execution Time | Thời gian lập kế hoạch / thực thi phía máy chủ | Chưa phản ánh đầy đủ truyền mạng, ánh xạ đối tượng và xử lý Java |

**Lưu ý với loops:** nếu một Index Scan ghi actual rows=3 loops=1.000 thì nút này tạo khoảng 3.000 hàng qua 1.000 lần gọi. Các con số có thể làm tròn; đừng nhân hoặc cộng máy móc để ra thời gian chính xác.

**Lưu ý với Buffers:** số trang ghi ở nút cha thường đã bao gồm hoạt động của nút con. Không cộng các dòng Buffers trong toàn cây như thể chúng là các phần độc lập. Một trang PostgreSQL thông thường có kích thước 8 KiB nhưng không nên suy ra trực tiếp dung lượng I/O vật lý từ hit/read.

## 5. Nhận diện các nút quan trọng

| Nút kế hoạch | Nó làm gì? | Khi nào cần xem kỹ? |
|---|---|---|
| Seq Scan | Đọc tuần tự bảng | Khi điều kiện rất chọn lọc mà lại quét phần lớn bảng; tuy nhiên thường hợp lý với bảng nhỏ hoặc truy vấn trả nhiều hàng |
| Index Scan | Tra cứu qua chỉ mục rồi có thể lấy thêm dữ liệu từ heap | Khi số bản ghi cần đọc lớn, truy cập heap ngẫu nhiên có thể đắt |
| Index Only Scan | Lấy các cột cần thiết từ chỉ mục nếu điều kiện cho phép | Kiểm tra Heap Fetches: PostgreSQL vẫn có thể phải đọc heap để xác minh tính hiển thị MVCC |
| Bitmap Index Scan / Bitmap Heap Scan | Gom vị trí hàng từ chỉ mục rồi đọc các trang heap liên quan | Thường hữu ích khi cần nhiều hàng phân tán; vẫn có thể tốn chi phí đọc heap |
| Sort / Incremental Sort | Sắp xếp toàn bộ hoặc một phần dữ liệu | Kiểm tra Sort Key, Sort Method, Memory; sắp xếp ra đĩa thường đáng chú ý |
| Nested Loop | Với mỗi hàng phía ngoài, thực thi nhánh phía trong | Xem loops của nhánh trong; rất tốt với tập nhỏ và truy cập chỉ mục hiệu quả |
| Hash Join | Tạo bảng băm để nối hai nguồn | Kiểm tra số hàng, kích thước hash, batches và khả năng tràn bộ nhớ |
| Merge Join | Nối hai nguồn theo thứ tự khóa | Kiểm tra nhu cầu Sort và chi phí chuẩn bị nguồn đã sắp |
| Aggregate / HashAggregate | Gom nhóm, tính tổng hợp | Xem số nhóm, bộ nhớ và lượng hàng đầu vào |
| Gather / Parallel Seq Scan | Kết hợp kết quả của các worker song song | Cần xem số worker thực chạy, độ lệch tải và chi phí phối hợp |

Không có quy tắc “Seq Scan luôn xấu” hay “Index Scan luôn tốt”. Planner có thể chủ động quét tuần tự vì phần lớn bảng phù hợp, bảng nhỏ hoặc dùng chỉ mục còn tốn hơn.

Một số câu hỏi cần trả lời trước khi quy lỗi cho chỉ mục:

1. Truy vấn trả ra bao nhiêu hàng, nhưng phải đọc hoặc loại bỏ bao nhiêu hàng?
2. Có nút Sort, Hash, Materialize hoặc nhiều vòng Nested Loop bất thường không?
3. Số hàng ước lượng và thực tế có sai lệch theo bội số lớn không?
4. Điều kiện lọc nằm trong Index Cond hay chỉ xuất hiện ở Filter?
5. Thời gian lớn là do đọc dữ liệu, tính toán, chờ khóa, hay thực thi cùng truy vấn nhiều lần? Kế hoạch chỉ trả lời một phần câu hỏi cuối.

## 6. Tình huống thực hành: xác minh chỉ mục ghép

### 6.1. Kế hoạch trước tối ưu

Giả định bảng orders có khoảng 1,2 triệu dòng và chưa có chỉ mục phù hợp với bộ lọc cùng thứ tự sắp xếp. EXPLAIN (ANALYZE, BUFFERS) có thể cho kết quả *giả lập* sau:

~~~text
Limit  (cost=30200.00..30200.05 rows=20 width=30)
       (actual time=148.300..148.305 rows=20 loops=1)
  Buffers: shared hit=2400 read=9500
  -> Sort  (cost=30200.00..30200.46 rows=186 width=30)
           (actual time=148.298..148.302 rows=20 loops=1)
       Sort Key: created_at DESC, id DESC
       Sort Method: top-N heapsort  Memory: 28kB
       Buffers: shared hit=2400 read=9500
       -> Seq Scan on orders  (cost=0.00..30195.00 rows=186 width=30)
                              (actual time=0.800..148.000 rows=233 loops=1)
            Filter: ((tenant_id = 42) AND (customer_id = 918)
                     AND (status = 'PAID'::text))
            Rows Removed by Filter: 1199767
            Buffers: shared hit=2400 read=9500
Planning Time: 0.41 ms
Execution Time: 148.36 ms
~~~

Phân tích theo chứng cứ:

- Limit chỉ trả 20 hàng nhưng Seq Scan phải xét khoảng 1,2 triệu hàng mới tìm thấy 233 hàng hợp lệ.
- Sort chọn 20 hàng đầu bằng top-N heapsort; phép sắp xếp bản thân không nhất thiết là điểm nghẽn chính. Phần quét bảng mới là ứng viên cần cải thiện.
- Bộ lập kế hoạch dự đoán 186 hàng, thực tế 233 hàng: chênh lệch không quá lớn, nên ví dụ này chưa chứng minh rằng thống kê bị sai nghiêm trọng.
- Nhiều shared read cho thấy truy vấn nạp nhiều trang vào bộ đệm. Số lần read cụ thể sẽ thay đổi theo trạng thái cache.

**Giả thuyết H1:** chỉ mục bắt đầu bằng ba cột so sánh bằng (tenant_id, customer_id, status), sau đó đến cột sắp xếp (created_at DESC, id DESC), sẽ cho phép đọc một vùng chỉ mục nhỏ theo đúng thứ tự mong muốn.

### 6.2. Can thiệp có kiểm soát

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_customer_status_recent
ON orders (tenant_id, customer_id, status, created_at DESC, id DESC);
~~~

Thứ tự này có lý do:

- tenant_id, customer_id, status là các điều kiện bằng của truy vấn được kiểm chứng.
- created_at DESC, id DESC khớp ORDER BY, giúp bộ máy dừng sau khi lấy đủ 20 hàng nếu đường truy cập phù hợp.
- id giúp thứ tự ổn định khi created_at bằng nhau.

Trong PostgreSQL, CREATE INDEX CONCURRENTLY giảm mức chặn ghi của quá trình tạo chỉ mục so với cách thông thường, nhưng vẫn tiêu thụ I/O, CPU và thời gian; nó **không được chạy trong một transaction block**. Công cụ migration cần hỗ trợ bước migration không bọc giao dịch nếu sử dụng tùy chọn này. Chỉ chọn tạo chỉ mục sau khi đánh giá chi phí lưu trữ và ghi tăng thêm.

### 6.3. Kế hoạch sau tối ưu

Chạy lại cùng câu SQL, cùng loại tham số và điều kiện tải tương đương. Kết quả *giả lập* có thể trông như sau:

~~~text
Limit  (cost=0.43..46.20 rows=20 width=30)
       (actual time=0.070..1.180 rows=20 loops=1)
  Buffers: shared hit=16 read=5
  -> Index Scan using idx_orders_tenant_customer_status_recent on orders
       (cost=0.43..456.30 rows=199 width=30)
       (actual time=0.069..1.174 rows=20 loops=1)
       Index Cond: ((tenant_id = 42) AND (customer_id = 918)
                    AND (status = 'PAID'::text))
       Buffers: shared hit=16 read=5
Planning Time: 0.22 ms
Execution Time: 1.21 ms
~~~

Ta quan sát được:

- Planner chọn chỉ mục mới; điều kiện lọc chính nằm ở Index Cond.
- Không còn nút Sort vì thứ tự từ chỉ mục phù hợp với ORDER BY.
- Đường quét trả đủ 20 hàng rồi dừng, thay vì xét toàn bảng.
- Số trang bộ đệm và Execution Time đều thấp hơn trong phép đo minh họa.

Kết quả trên **phù hợp với H1**, nhưng chưa đủ để tuyên bố tốc độ tăng bao nhiêu phần trăm trên hệ thống thật: các số hoàn toàn giả lập. Cần đo lặp lại trên cơ sở dữ liệu thực, dưới dữ liệu và tải đại diện, đồng thời xác nhận kết quả trả về vẫn đúng.

### 6.4. Bảng đối chiếu trước – sau

| Yếu tố kiểm chứng | Trước (minh họa) | Sau (minh họa) | Ý nghĩa |
|---|---|---|---|
| Đường truy cập | Seq Scan | Index Scan | Chỉ mục mới được planner chọn |
| Hàng phải xét | Khoảng 1,2 triệu | Dừng ở 20 hàng hợp lệ | Giảm công việc truy xuất |
| Sắp xếp | Sort top-N | Không có Sort riêng | Chỉ mục đáp ứng thứ tự |
| shared hit/read | 2.400 / 9.500 | 16 / 5 | Ít truy cập trang hơn trong lần chạy mẫu |
| Execution Time | 148,36 ms | 1,21 ms | Có tín hiệu cải thiện; phải đo lặp lại |
| Chi phí ghi dữ liệu | Chưa có chỉ mục mới | Duy trì thêm chỉ mục khi ghi | Phải đánh đổi chi phí đọc và ghi |

Đừng suy diễn từ kế hoạch rằng chỉ mục này tối ưu cho **mọi** câu SQL trên orders. Ví dụ truy vấn thống kê tất cả đơn của một tháng hoặc lọc chỉ theo status có thể cần chiến lược khác.

## 7. Khi kế hoạch không xác nhận giả thuyết

### 7.1. Có chỉ mục nhưng vẫn Seq Scan

Ví dụ:

~~~sql
SELECT *
FROM orders
WHERE status = 'PAID';
~~~

Nếu phần lớn bảng có status = 'PAID', quét bảng có thể rẻ hơn tra cứu qua chỉ mục rồi lấy nhiều hàng từ heap. Chỉ mục ghép ở mục 6 cũng bắt đầu bằng tenant_id và customer_id nên không nhất thiết hữu ích cho truy vấn chỉ lọc status.

Cách kiểm tra: xem tỷ lệ hàng phù hợp, khối lượng dữ liệu trả về, cột SELECT, thống kê ước lượng và Buffers. Không ép sử dụng index trước khi có bằng chứng nó nhanh hơn.

### 7.2. Có Index Scan nhưng lọc vẫn tốn

Ví dụ:

~~~sql
SELECT id, created_at
FROM orders
WHERE tenant_id = 42
  AND customer_id = 918
  AND status = 'PAID'
  AND total_amount > 1000000
ORDER BY created_at DESC, id DESC
LIMIT 20;
~~~

Chỉ mục ở mục 6 có thể dùng ba điều kiện bằng để tìm hàng nhưng vẫn phải kiểm tra total_amount như Filter. Nếu điều kiện về giá tiền loại bỏ phần lớn đơn, bộ máy có thể quét sâu hơn trong chỉ mục mới đủ 20 hàng.

Tín hiệu cần tìm là Index Cond, Filter, Rows Removed by Filter và số hàng/quãng đọc thực tế. Có thể cân nhắc chỉ mục khác nếu mô hình truy cập lặp lại đủ phổ biến và hiệu quả ghi vẫn chấp nhận được. Tránh tạo chỉ mục mới chỉ để phản ứng với một kế hoạch đơn lẻ.

### 7.3. Biểu thức làm mất khả năng tận dụng chỉ mục thông thường

Ví dụ lọc theo ngày:

~~~sql
-- Có thể cần tính biểu thức cho nhiều hàng.
SELECT id
FROM orders
WHERE tenant_id = 42
  AND created_at::date = DATE '2026-11-22';
~~~

Nếu mục tiêu là một ngày theo múi giờ đã xác định, thường nên đưa về khoảng nửa mở:

~~~sql
SELECT id
FROM orders
WHERE tenant_id = 42
  AND created_at >= TIMESTAMPTZ '2026-11-22 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-23 00:00:00+07';
~~~

Điều kiện khoảng thường dễ tận dụng chỉ mục B-tree trên (tenant_id, created_at). Tuy nhiên việc chuyển ngày theo múi giờ phải **giữ nguyên ý nghĩa nghiệp vụ**: phép ép kiểu trên timestamptz phụ thuộc múi giờ phiên, còn giới hạn khoảng phải được tính theo múi giờ yêu cầu và quy tắc giờ mùa hè nếu có.

### 7.4. Sai lệch lớn giữa ước lượng và thực tế

Một nhánh ước lượng rows=10 nhưng thực tế rows=200000 có thể khiến planner chọn Nested Loop thay vì một chiến lược nối phù hợp hơn. Các nguyên nhân thường gặp:

- Thống kê đã cũ sau khi dữ liệu thay đổi mạnh.
- Phân bố dữ liệu lệch, chẳng hạn vài tenant rất lớn.
- Các cột có tương quan mà thống kê đơn cột chưa mô tả đủ.
- Giá trị tham số truy vấn không có tính đại diện cho các lần gọi còn lại.

Có thể kiểm tra thời điểm cập nhật thống kê và cân nhắc chạy lệnh ANALYZE orders theo quy trình vận hành. Với truy vấn nhiều cột tương quan, PostgreSQL có khả năng thu thập thống kê mở rộng, nhưng cần chọn đúng loại và kiểm tra hiệu quả thực tế. **Cập nhật thống kê không bảo đảm planner sẽ chọn một kế hoạch nhất định.**

### 7.5. Join hoặc vòng lặp gây chi phí lớn

Một Nested Loop có Index Scan ở nhánh trong lặp 50.000 lần có thể tốn hơn dự đoán, dù mỗi lần tra cứu rất nhanh. Xem cả cardinality của nhánh ngoài và loops của nhánh trong.

Ngược lại, Nested Loop trên 20 khách hàng, mỗi khách có vài đơn, có thể là lựa chọn tốt nhất. Mục tiêu là phát hiện tổng công việc bất thường, không phải loại bỏ tên toán tử.

### 7.6. Truy vấn SQL nhanh nhưng ứng dụng Java vẫn chậm

EXPLAIN của một câu SQL không phản ánh:

- **N+1 queries:** tầng ORM tải danh sách khách hàng rồi phát thêm một truy vấn cho mỗi khách hàng.
- Chi phí chờ kết nối trong connection pool, mạng, ánh xạ entity và tuần tự hóa JSON.
- Chờ khóa, giao dịch kéo dài, mức cô lập hoặc xung đột ghi.
- Một truy vấn chạy nhanh riêng lẻ nhưng được gọi hàng nghìn lần mỗi request.

Khi đó cần đối chiếu trace, số truy vấn, độ trễ p95/p99 ở ứng dụng, metrics pool và quan sát hoạt động DB. Đọc một execution plan chỉ là một phần của chẩn đoán.

## 8. Một quy trình kiểm chứng có thể lặp lại

### Bước 1. Chọn đúng truy vấn gây tác động

Lấy SQL thực sự được persistence layer phát ra, kể cả điều kiện tenant, ORDER BY, LIMIT và các kiểu tham số. Xác nhận triệu chứng từ log, trace hoặc thống kê truy vấn tổng hợp; ghi rõ tần suất, độ trễ và lượng dữ liệu thực tế.

Nếu Java dùng JPA/Hibernate, kiểm tra SQL đã tạo chứ không chỉ đọc tên phương thức repository. Cân nhắc sự khác nhau giữa truy vấn đơn lẻ và cả chuỗi truy vấn của một request.

### Bước 2. Ghi lại đường cơ sở

Lưu kế hoạch trước thay đổi, thông tin số hàng, loại truy cập, Index Cond/Filter, Buffers, Execution Time, quy mô bảng, môi trường và giá trị tham số đại diện. Nên đo nhiều lần vì cache nóng/lạnh, tải đồng thời và nền hệ thống có thể làm số đo thay đổi.

Ví dụ bảng ghi nhận:

| Thông tin | Giá trị cần lưu |
|---|---|
| Câu SQL / nhóm request | Định danh truy vấn, đường gọi từ Java |
| Mục tiêu | Ví dụ lấy 20 đơn gần nhất của một khách hàng |
| Bộ tham số | Trường hợp thường gặp và trường hợp nặng |
| Quy mô dữ liệu | Tổng hàng, tỷ lệ hàng lọc được, phân bố tenant |
| Plan | File kế hoạch trước/sau hoặc output text/JSON |
| Quan sát | Loại scan/join, rows, loops, filter, buffers, sort |
| Hiệu năng | Median, p95 khi đủ số mẫu; số lần gọi, tài nguyên DB |
| Tính đúng đắn | Tập kết quả, thứ tự, phân quyền tenant |
| Tác động khác | Tốc độ ghi, kích thước chỉ mục, chi phí migration |

### Bước 3. Nêu rõ giả thuyết và tiêu chí bác bỏ

Chẳng hạn: “Nếu chỉ mục ghép phù hợp, kế hoạch sẽ dùng Index Scan, không còn Sort riêng, ít page access hơn và độ trễ truy vấn giảm trong đa số lần đo”. Nếu sau khi thêm chỉ mục, plan vẫn Seq Scan hoặc độ trễ không cải thiện dưới tải đại diện, phải xem lại giả thuyết.

### Bước 4. Thay đổi một nguyên nhân mỗi lần

Có thể thử viết lại điều kiện WHERE, tránh trả cột không cần thiết, điều chỉnh ORDER BY/LIMIT, thêm chỉ mục hoặc cập nhật thống kê khi có cơ sở. Thay quá nhiều yếu tố cùng lúc khiến không biết nguyên nhân cải thiện.

### Bước 5. Đo lại cùng workload

So sánh SQL và semantics giống nhau, dữ liệu gần tương đương, cùng tập tham số và cấu hình phù hợp. Báo cáo ít nhất tình huống thường gặp và trường hợp nhiều hàng; không chỉ chọn lần nhanh nhất. Nếu dùng prepared statement, để ý PostgreSQL có thể chọn kế hoạch generic hoặc custom tùy bối cảnh và giá trị bind.

Cần phân biệt thời gian thực thi trên máy chủ trong EXPLAIN với thời gian toàn request. Kiểm tra cả độ trễ p95, tải DB, chi phí cập nhật và dung lượng chỉ mục. Một cải thiện ở truy vấn đọc không nhất thiết tốt nếu làm đường ghi quan trọng suy giảm đáng kể.

### Bước 6. Chấp nhận, điều chỉnh hoặc quay lại

- **Chấp nhận** khi kế hoạch xác nhận cơ chế dự đoán, hiệu năng được cải thiện ổn định, dữ liệu trả về đúng và chi phí duy trì hợp lý.
- **Điều chỉnh** khi kế hoạch chỉ cải thiện một nhóm tham số; đánh giá chỉ mục, thứ tự cột hoặc cách viết SQL theo phân bố thực tế.
- **Quay lại** nếu lợi ích không đạt mục tiêu hoặc làm tăng chi phí toàn hệ thống. Ghi lại bằng chứng để tránh lặp lại phép thử thiếu hiệu quả.

Trong triển khai thật, việc tạo chỉ mục, thu thập thống kê và thay đổi schema cần theo quy trình migration, quan sát tải và phương án khôi phục của hệ thống.

## 9. Ví dụ tích hợp với persistence trong Java

Trong mã ứng dụng, **truy vấn được chạy bình thường phải dùng tham số hóa**. Đo plan chỉ nên là thao tác chẩn đoán có chủ đích, không thực thi EXPLAIN ANALYZE mỗi khi người dùng mở trang.

Ví dụ dùng JDBC trên môi trường thử nghiệm:

~~~java
String planSql = """
    EXPLAIN (ANALYZE, BUFFERS)
    SELECT id, created_at, total_amount
    FROM orders
    WHERE tenant_id = ?
      AND customer_id = ?
      AND status = ?
    ORDER BY created_at DESC, id DESC
    LIMIT ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(planSql)) {

    statement.setLong(1, 42L);
    statement.setLong(2, 918L);
    statement.setString(3, "PAID");
    statement.setInt(4, 20);

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            System.out.println(result.getString(1));
        }
    }
}
~~~

Đoạn mã giả định dataSource đã được cấu hình và chỉ dùng trên môi trường được phép kiểm tra. Nó thực thi SELECT một lần để đo. Với bản chạy sản xuất, repository chỉ thực thi SELECT tham số hóa và chuyển kết quả sang kiểu dữ liệu phù hợp.

Khi theo dõi kế hoạch của truy vấn dùng tham số, cần dùng các bộ giá trị đại diện: một khách hàng có 5 đơn và một khách hàng có 500.000 đơn có thể dẫn tới hành vi khác nhau. Chỉ dựa trên plan của khách ít đơn sẽ bỏ sót trường hợp nặng.

**Tại ranh giới persistence**, cần giữ nguyên các bảo đảm nghiệp vụ dù tối ưu: phân quyền theo tenant, tính đúng đắn của số tiền, thứ tự ổn định khi phân trang, semantics của thời gian, và giới hạn transaction. Không đưa SQL nối chuỗi từ dữ liệu đầu vào để tạo nhanh một câu EXPLAIN.

## 10. Những hiểu lầm thường gặp

| Nhận định vội | Cách hiểu chính xác hơn |
|---|---|
| “Có Seq Scan là thiếu index.” | Seq Scan có thể tối ưu khi đọc phần lớn bảng hoặc bảng nhỏ. |
| “cost=1000 nghĩa là chạy 1.000 ms.” | Cost là thước đo tương đối do planner ước lượng, không phải thời gian. |
| “Đã dùng Index Scan nên truy vấn chắc nhanh.” | Có thể vẫn tốn rất nhiều heap fetch, filter hoặc loops. |
| “Thấy Sort thì luôn phải tạo index.” | Sort nhỏ trong bộ nhớ có thể rất rẻ; cần xét tổng chi phí và workload. |
| “Execution Time giảm ở một lần đo tức là đã tối ưu xong.” | Cache, tải, phân bố tham số và độ nhiễu đòi hỏi đo nhiều lần. |
| “Index Only Scan sẽ không đọc heap.” | MVCC có thể buộc truy cập heap; xem Heap Fetches. |
| “BUFFERS read chính là số lần đọc ổ đĩa.” | Read ghi nhận nạp trang vào shared buffer, có thể đến từ cache của hệ điều hành. |
| “Chỉ cần tối ưu SQL là request Java sẽ nhanh.” | Còn N+1, pool, mạng, ORM, khóa, giao dịch và số lần gọi. |
| “Thêm index không có tác dụng phụ.” | Index tiêu tốn lưu trữ và phải được duy trì khi dữ liệu thay đổi. |

## 11. Bài tập tự kiểm tra

**Bài tập A.** Bảng cấu hình có khoảng 200 hàng. Kế hoạch cho truy vấn lấy 30 hàng là Seq Scan, Execution Time 0,08 ms. Có nên lập tức thêm chỉ mục để loại bỏ Seq Scan?

**Bài tập B.** Một truy vấn nối hai bảng có đoạn kế hoạch:

~~~text
Nested Loop  (actual time=0.2..320.0 rows=12000 loops=1)
  -> Seq Scan on customers  (actual time=0.1..9.0 rows=12000 loops=1)
  -> Index Scan using orders_customer_idx on orders
       (actual time=0.01..0.02 rows=1 loops=12000)
~~~

Những thông tin nào khiến bạn muốn kiểm tra nhánh Index Scan phía trong trước khi đề xuất thay đổi? Có thể khẳng định Nested Loop sai không?

**Bài tập C.** Sau khi thêm chỉ mục ghép, một lần chạy giảm từ 100 ms xuống 4 ms. Nhưng p95 của API gần như không đổi. Cần kiểm tra điều gì?

### Gợi ý trả lời

**A:** Chưa có lý do. Với bảng rất nhỏ và thời gian cực thấp, Seq Scan có thể tối ưu hơn chi phí đi qua chỉ mục. Cần xét tần suất gọi, tác động thực tế và kế hoạch dưới tải tương ứng.

**B:** Nhánh trong lặp 12.000 lần, nên tổng chi phí của các lần tra cứu cần được xét. Kiểm tra số hàng ở mỗi vòng, Buffers, tỷ lệ ước lượng/thực tế và khả năng nối khác. Không thể kết luận chỉ từ tên Nested Loop; nếu mỗi vòng rất rẻ và trả ít hàng, đó vẫn có thể là chiến lược tốt.

**C:** Kiểm tra liệu truy vấn đã tối ưu có nằm trên đường xử lý p95 hay không; số truy vấn mỗi request, thời gian chờ connection pool, N+1, mạng, ORM, khóa và các trường hợp tham số nặng. So sánh nhiều lần ở cùng tải và xác nhận kế hoạch được dùng trong thực tế.

## 12. Checklist khi đọc một kế hoạch mới

- [ ] Xác định SQL thực tế, mục tiêu nghiệp vụ, kiểu tham số và quy mô dữ liệu.
- [ ] Đo baseline đủ đại diện trước khi can thiệp.
- [ ] Đọc từ lá đến gốc để hiểu đường đi dữ liệu; kiểm tra nút tốn chi phí và số vòng lặp.
- [ ] So sánh rows ước lượng/thực tế; xem Index Cond, Filter và Rows Removed by Filter.
- [ ] Xem Sort, Join, Buffers, Heap Fetches và khả năng truy vấn phải đọc nhiều hàng hơn kết quả cần trả.
- [ ] Viết giả thuyết có dấu hiệu xác nhận/bác bỏ rõ ràng.
- [ ] Thay đổi có kiểm soát, đọc plan lại và đo lặp với nhiều nhóm tham số.
- [ ] Kiểm chứng thứ tự, phân quyền, dữ liệu trả về và tác động lên đường ghi.
- [ ] Đối chiếu thời gian SQL với p95 của chức năng Java; ghi lại quyết định và bằng chứng.

**Điểm cốt lõi:** kế hoạch thực thi không phải một bảng xếp hạng để tìm tên toán tử “xấu”. Nó là bằng chứng về cách cơ sở dữ liệu truy cập, lọc, nối và sắp xếp dữ liệu. Người tối ưu giỏi dùng kế hoạch để **kiểm chứng giả thuyết**, sau đó xác nhận giá trị bằng kết quả đúng và hiệu năng đo được trên workload thực.
