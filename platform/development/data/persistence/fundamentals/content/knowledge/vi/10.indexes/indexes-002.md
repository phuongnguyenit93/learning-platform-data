# Đánh đổi giữa tốc độ đọc, tốc độ ghi và dung lượng khi thiết kế chỉ mục

## Mục tiêu học tập

Sau bài này, người học có thể:

- Giải thích vì sao thêm chỉ mục có thể giảm thời gian truy vấn nhưng làm tăng công việc khi ghi và chi phí lưu trữ.
- Phân tích ảnh hưởng của số lượng, loại, thứ tự cột và kích thước chỉ mục đối với ứng dụng Java sử dụng cơ sở dữ liệu.
- Chọn chỉ mục theo truy vấn thực tế, tỷ lệ đọc/ghi, độ chọn lọc, ngân sách lưu trữ và yêu cầu nhất quán dữ liệu.
- Đo kết quả bằng kế hoạch thực thi, độ trễ, thông lượng ghi và dung lượng trước khi quyết định triển khai.

Bài thuộc chương **Chỉ mục** của module **DATA_PERSISTENCE_FUNDAMENTALS**. Trong thiết kế persistence cho ứng dụng Java, chỉ mục là một phần của lược đồ và chiến lược vận hành: quyết định này ảnh hưởng đến truy vấn, giao dịch, độ trễ ghi, sao lưu, khôi phục và việc tiến hóa schema.

## 1. Vì sao có sự đánh đổi?

Một chỉ mục là cấu trúc dữ liệu phụ giúp hệ quản trị cơ sở dữ liệu tìm hàng cần thiết mà thường không phải đọc toàn bộ bảng. Với chỉ mục B-tree, các khóa được tổ chức trong những trang có cấu trúc để hỗ trợ tra cứu, truy vấn khoảng và duyệt theo thứ tự. Đổi lại, hệ quản trị phải **lưu cấu trúc phụ này và duy trì nó khi dữ liệu thay đổi**.

Với một bảng nhiều triệu bản ghi, một truy vấn lọc rất ít hàng có thể giảm đáng kể số trang cần đọc nhờ chỉ mục. Tuy nhiên, khi thêm một hàng mới, cơ sở dữ liệu có thể phải thêm khóa vào từng chỉ mục liên quan; khi sửa cột đã được lập chỉ mục, cơ sở dữ liệu có thể phải cập nhật hoặc tạo phiên bản mục chỉ mục tương ứng. Các thao tác đó tiêu thụ CPU, bộ nhớ, I/O, tài nguyên ghi log giao dịch và đôi khi tạo thêm tranh chấp.

Ba mục tiêu chính thường xung đột:

| Mục tiêu | Điều gì giúp cải thiện? | Chi phí dễ phát sinh |
| --- | --- | --- |
| Đọc nhanh | Chỉ mục có chọn lọc, phù hợp điều kiện lọc, sắp xếp và cột trả về | Thêm trang chỉ mục, tăng áp lực bộ nhớ đệm |
| Ghi nhanh | Ít cấu trúc phụ phải bảo trì; ghi tuần tự thuận lợi | Truy vấn đọc có thể phải quét nhiều hàng hơn |
| Dung lượng nhỏ | Ít chỉ mục, khóa gọn, chỉ lập chỉ mục cho tập dữ liệu cần thiết | Giảm số đường truy cập nhanh cho truy vấn |

Đây là sự đánh đổi theo **khối lượng công việc cụ thể**, không phải quy luật rằng có chỉ mục thì mọi truy vấn đều nhanh. Nếu câu truy vấn trả về phần lớn bảng, đọc tuần tự có thể rẻ hơn việc đi qua chỉ mục rồi truy cập ngẫu nhiên nhiều trang dữ liệu. Bộ tối ưu truy vấn sẽ ước lượng chi phí và có thể chủ động không dùng chỉ mục.

### 1.1. Chi phí đọc: tránh đọc thừa, nhưng có thêm bước tra cứu

Ví dụ, truy vấn tìm 50 đơn hàng mới nhất của một khách thuê dữ liệu (*tenant*) trong hàng triệu đơn hàng:

- **Không có chỉ mục phù hợp:** hệ quản trị có thể phải đọc rất nhiều hàng, lọc rồi sắp xếp.
- **Có chỉ mục phù hợp:** có thể tìm nhanh vùng khóa thuộc tenant, trạng thái đơn hàng và duyệt 50 khóa đầu theo đúng thứ tự.
- **Chỉ mục không chứa đủ cột cần trả về:** sau khi tìm khóa, cơ sở dữ liệu vẫn có thể phải truy cập bảng để lấy các cột còn thiếu.

Ở mức trực giác, B-tree giảm khối lượng tìm kiếm xuống một số ít trang chỉ mục cộng với các trang của hàng kết quả. Nhưng tốc độ thực tế phụ thuộc phân bố dữ liệu, thống kê, bộ nhớ đệm, độ lớn hàng kết quả và số lần truy cập bảng. Một chỉ mục tốt cho truy vấn có chọn lọc không nhất thiết tốt cho báo cáo đọc gần hết bảng.

### 1.2. Chi phí ghi: mỗi chỉ mục cần được duy trì

Xét các thao tác thông dụng:

- **INSERT:** tạo hàng và thêm mục vào các chỉ mục liên quan, có thể cần tách trang chỉ mục (*page split*).
- **UPDATE:** nếu khóa được lập chỉ mục thay đổi, hệ quản trị cần bảo đảm đường truy cập mới trỏ tới phiên bản dữ liệu hợp lệ; cả cơ chế MVCC và chi tiết cập nhật phụ thuộc engine.
- **DELETE:** mục chỉ mục tương ứng cần được vô hiệu hóa hoặc dọn dẹp theo cơ chế của hệ quản trị; việc thu hồi không gian có thể diễn ra sau.
- **COMMIT và ghi log:** với hệ quản trị có WAL/redo log, nhiều thay đổi chỉ mục có thể làm tăng lượng log và I/O, ảnh hưởng độ trễ commit, khôi phục và sao chép dữ liệu.

Một bảng có năm chỉ mục phụ không có nghĩa mỗi lần ghi chậm chính xác năm lần. Chi phí phụ thuộc cột thay đổi, loại chỉ mục, vị trí trang trong cache, mức độ đồng thời, cách engine thực thi và đặc điểm phần cứng. Tuy nhiên, **mỗi chỉ mục không cần thiết đều là một nghĩa vụ bảo trì tiềm năng**.

### 1.3. Chi phí dung lượng: vượt ra ngoài dung lượng trên đĩa

Chỉ mục chiếm các trang lưu trữ riêng. Khóa dài, nhiều cột, nhiều bản ghi và các cột mang theo để phục vụ truy vấn (*covering*) đều có thể tăng kích thước. Không gian trống trong trang để phục vụ ghi, bloat do cập nhật/xóa, hệ thống log, bản sao và bản sao lưu cũng là một phần của chi phí vận hành.

Chỉ mục lớn hơn cũng có thể đẩy các trang dữ liệu hữu ích khỏi RAM. Vì thế, chỉ mục giúp một truy vấn nhanh hơn nhưng đôi khi khiến các truy vấn khác chậm hơn do giảm tỷ lệ cache hit.

## 2. Ví dụ xuyên suốt: hệ thống đơn hàng nhiều tenant

Giả sử ứng dụng Java lưu đơn hàng trong PostgreSQL. Bảng tối giản:

~~~sql
CREATE TABLE orders (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id    BIGINT NOT NULL,
    customer_id  BIGINT NOT NULL,
    status       VARCHAR(16) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount NUMERIC(14, 2) NOT NULL
);
~~~

Khóa chính đã tạo đường truy cập theo `id` trong PostgreSQL; không cần tạo thêm một chỉ mục giống hệt. API thường hiển thị 50 đơn hàng đã thanh toán gần nhất:

~~~sql
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Một ứng viên chỉ mục là:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Ý nghĩa của thứ tự cột ở truy vấn này:

1. `tenant_id` và `status` là các điều kiện bằng, giúp khoanh vùng khóa.
2. `created_at DESC, id DESC` khớp thứ tự kết quả, giúp lấy những bản ghi đầu tiên mà không nhất thiết phải sắp xếp toàn bộ tập phù hợp.
3. `id` ở cuối cung cấp thứ tự ổn định khi nhiều đơn hàng có cùng thời điểm tạo, có ích cho phân trang.

Nếu chỉ tạo chỉ mục `(status)`, số lượng giá trị trạng thái thường nhỏ, nên `status = 'PAID'` có thể khớp quá nhiều hàng. PostgreSQL có thể chọn quét bảng thay vì dùng chỉ mục đó. Tương tự, chỉ mục `(tenant_id, status, created_at)` thường không tối ưu bằng cho truy vấn chỉ lọc `created_at` mà không có điều kiện ở những cột đứng trước. Tính hữu ích của quy tắc tiền tố còn phụ thuộc bộ tối ưu, engine và hình dạng câu truy vấn.

### 2.1. Hai cách tối ưu với chi phí khác nhau

**Cách A — chỉ mục B-tree đa cột:** chỉ mục vừa tạo có thể phục vụ nhiều truy vấn lọc theo tenant và status, nhưng lưu mục cho mọi đơn hàng ở mọi trạng thái. Khi trạng thái thay đổi, cấu trúc này phải được cập nhật phù hợp.

**Cách B — chỉ mục một phần kèm cột dữ liệu**, khi phần lớn truy vấn quan trọng luôn tìm đơn hàng `PAID` (cú pháp PostgreSQL):

~~~sql
CREATE INDEX idx_orders_paid_recent
ON orders (tenant_id, created_at DESC, id DESC)
INCLUDE (customer_id, total_amount)
WHERE status = 'PAID';
~~~

Ở cách B, chỉ những hàng thỏa điều kiện `status = 'PAID'` thuộc chỉ mục. Do đó, nếu số đơn hàng `PAID` là tỷ lệ nhỏ, chỉ mục có thể nhỏ hơn đáng kể so với chỉ mục toàn bảng. Hai cột trong `INCLUDE` giúp truy vấn có cơ hội đọc dữ liệu trực tiếp từ chỉ mục; **index-only scan không được bảo đảm** vì PostgreSQL vẫn xét khả năng hiển thị phiên bản hàng thông qua visibility map. Những cột được mang theo cũng làm mỗi mục chỉ mục lớn hơn.

Nếu phần lớn đơn hàng đều đã thanh toán, lợi ích về dung lượng của chỉ mục một phần sẽ nhỏ. Nếu truy vấn truyền `status` dưới dạng tham số thay đổi, một prepared statement dùng kế hoạch tổng quát có thể không chứng minh được điều kiện của chỉ mục một phần; cần đo với kiểu truy vấn và chế độ thực thi thực tế.

Đây là **hai ứng viên để so sánh**, không phải khuyến nghị mặc định tạo cả hai. Giữ cả hai làm tăng chi phí ghi và dung lượng, trong khi chúng có thể trùng nhiều khả năng phục vụ truy vấn.

## 3. Các lựa chọn chỉ mục và ba loại chi phí

| Lựa chọn | Khi nào đọc có lợi? | Ảnh hưởng ghi | Ảnh hưởng dung lượng |
| --- | --- | --- | --- |
| Không thêm chỉ mục phụ | Quét bảng nhỏ, truy vấn đọc phần lớn hàng hoặc ghi rất nhiều | Ít bảo trì chỉ mục phụ | Thấp nhất về chỉ mục phụ |
| B-tree một cột | Tra cứu bằng hoặc khoảng trên cột có ích cho việc lọc | Duy trì thêm một cấu trúc theo khóa | Tăng theo số hàng và kích thước khóa |
| B-tree đa cột | Cụm điều kiện lọc và sắp xếp thường xuất hiện cùng nhau | Tăng chi phí khi các khóa thay đổi | Mục chỉ mục thường rộng hơn |
| Chỉ mục một phần (*partial index*) | Truy vấn luôn phù hợp với điều kiện lọc của chỉ mục | Ít hàng thuộc chỉ mục hơn; thay đổi khiến hàng vào/ra tập lọc vẫn có chi phí | Có thể nhỏ hơn đáng kể nếu tập lọc nhỏ |
| Chỉ mục có `INCLUDE` | Có thể tránh một phần truy cập bảng khi dữ liệu và điều kiện cho phép | Duy trì thêm các giá trị mang theo | Mỗi mục rộng hơn; có thể ảnh hưởng mật độ trang |
| BRIN (PostgreSQL) | Quét khoảng trên dữ liệu có tương quan với thứ tự vật lý, như log tăng theo thời gian | Thường nhẹ vì lưu tóm tắt vùng trang | Rất nhỏ nhưng phải lọc lại hàng phù hợp |
| GIN (PostgreSQL) | Điều kiện tìm trong mảng, JSONB, văn bản và tập phần tử | Có thể tốn nhiều công việc cập nhật mục đảo ngược | Có thể lớn đáng kể tùy dữ liệu |

Không thể xếp hạng tuyệt đối loại nào nhanh nhất. Ví dụ, BRIN không thay thế B-tree cho tra cứu chính xác 1 hàng, nhưng có thể đáng giá với dữ liệu sự kiện rất lớn, ghi chủ yếu theo thứ tự thời gian, và ngân sách dung lượng nghiêm ngặt. Các loại như Hash, GiST, GIN, BRIN và những cơ chế tương đương khác có cú pháp/giới hạn phụ thuộc hệ quản trị.

### 3.1. Số lượng chỉ mục là một tham số thiết kế

Hãy tưởng tượng bảng `orders` có các nhu cầu:

- API đọc đơn hàng theo `id`: đã được phục vụ bởi khóa chính.
- API đọc đơn hàng vừa thanh toán theo tenant: ứng viên chỉ mục đa cột hoặc một phần.
- Báo cáo doanh thu theo tháng cần phần lớn hàng: có thể phù hợp hơn với quét tuần tự, tổng hợp theo lô, bảng kết quả định kỳ hoặc phân vùng.
- Một chức năng hiếm dùng tìm theo `customer_id`: phải cân nhắc tần suất và độ trễ mong muốn trước khi thêm chỉ mục chỉ dành cho nó.

Thêm một chỉ mục cho mọi cột riêng lẻ thường gây lãng phí. Chỉ mục đa cột cũng không đồng nghĩa với tổng các chỉ mục một cột: thứ tự khóa quyết định những bộ lọc và cách sắp xếp nào được phục vụ hiệu quả.

### 3.2. Kích thước khóa và độ rộng hàng

Một ước lượng sơ bộ:

`Dung lượng chỉ mục ≈ số mục × số byte trung bình mỗi mục / tỷ lệ lấp đầy`

Giả sử **tình huống minh họa**, không phải phép đo của PostgreSQL: 8 triệu mục, trung bình 32 byte/mục và tỷ lệ lấp đầy 80% thì cần khoảng `8.000.000 × 32 / 0,8 = 320.000.000` byte, tức xấp xỉ 305 MiB. Con số thực tế còn phụ thuộc header trang, con trỏ hàng, metadata, deduplication/compression của engine, phiên bản dữ liệu, phân bố khóa và phân mảnh.

Nếu thêm nhiều chỉ mục rộng trên bảng lớn, tổng dung lượng tăng nhanh. Cần tính cả đĩa để xây dựng chỉ mục, WAL, backup và replica; không chỉ đếm kích thước file chính ở một thời điểm.

## 4. Vì sao một chỉ mục tốt khi đọc có thể làm ghi chậm?

Xét vòng đời một đơn hàng:

1. `INSERT` đơn hàng với `status = 'NEW'`: B-tree toàn bảng nhận thêm mục; chỉ mục một phần `WHERE status = 'PAID'` chưa nhận mục này.
2. `UPDATE` trạng thái `NEW → PAID`: cơ sở dữ liệu cần duy trì khóa hoặc mục chỉ mục tương ứng; đơn hàng bắt đầu xuất hiện trong chỉ mục một phần.
3. `UPDATE` trường `total_amount`: nếu cột nằm trong phần `INCLUDE`, thay đổi có thể buộc cập nhật dữ liệu chỉ mục; tùy engine/MVCC, cập nhật cột không nằm trong bất kỳ chỉ mục nào đôi khi có đường ghi rẻ hơn.
4. `DELETE` đơn hàng: phải xử lý trạng thái hợp lệ và dọn dẹp các mục chỉ mục liên quan.

Với PostgreSQL, khả năng thực hiện HOT update phụ thuộc việc không làm thay đổi cột được các chỉ mục liên quan tham chiếu và việc có đủ chỗ trên trang dữ liệu. Một chỉ mục không cần thiết có thể vô tình làm mất cơ hội tối ưu cập nhật. Cơ chế này không nên suy diễn nguyên xi sang MySQL InnoDB hoặc một engine khác.

Nhiều ghi đồng thời còn có thể làm tăng tranh chấp trên trang chỉ mục hoặc chi phí chờ I/O. Trên hệ thống dùng nhân bản, WAL bổ sung có thể gây tăng lưu lượng truyền và độ trễ replica. Khi triển khai, vì vậy cần đo thông lượng **và** độ trễ ghi p95/p99, không chỉ tốc độ của một truy vấn SELECT riêng lẻ.

## 5. Chọn theo workload và ràng buộc dịch vụ

Một quyết định có ích bắt đầu từ **câu truy vấn thực, lưu lượng thực và mục tiêu đo được**:

1. **Lập danh sách truy vấn trọng yếu:** câu SQL cụ thể, điều kiện `WHERE`, `JOIN`, `ORDER BY`, `LIMIT`, số hàng trả về, tần suất và độ trễ p95/p99.
2. **Mô tả ghi:** tỷ lệ INSERT/UPDATE/DELETE, cột thường thay đổi, số giao dịch mỗi giây, kích thước batch, mức đồng thời và đường đi của một transaction.
3. **Kiểm tra phân bố:** số hàng mỗi tenant, tỷ lệ `PAID`, số giá trị khác nhau của các cột, độ lệch dữ liệu theo tenant/thời gian. Cùng một câu truy vấn có thể tốt với tenant nhỏ và xấu với tenant rất lớn.
4. **Xác định ngân sách:** mức tăng dung lượng, giới hạn RAM/cache, thời gian backup/restore, thông lượng tối thiểu và độ trễ ghi tối đa.
5. **Chọn ít ứng viên có cơ sở**, rồi kiểm tra với dữ liệu và tỷ lệ truy vấn gần sản xuất.

Có thể mô tả trực giác tổng chi phí của một workload bằng:

`C = w_doc × cost_doc + w_ghi × cost_ghi + w_dungluong × cost_dungluong`

Trong đó các trọng số phản ánh mức độ quan trọng của mỗi mục tiêu, còn các `cost` phải được **chuẩn hóa cùng cách** trước khi so sánh. Công thức là công cụ suy nghĩ, không phải phương trình tối ưu sẵn có. Trong thực tế, thường có thêm ràng buộc cứng: mọi truy vấn API chủ chốt phải dưới một ngưỡng p95, tốc độ ghi không được thấp hơn một mức tối thiểu, và dung lượng phải nằm trong ngân sách.

Ví dụ **giả định**: thêm một chỉ mục đưa p95 đọc từ 120 ms xuống 25 ms, nhưng làm thông lượng ghi giảm từ 10.000 xuống 8.000 bản ghi/s và tăng 320 MB. Nếu SLO là p95 đọc dưới 50 ms, ghi ít nhất 7.000 bản ghi/s và còn đủ ngân sách lưu trữ, đây có thể là đánh đổi chấp nhận được. Nếu dịch vụ cần ghi tối thiểu 9.000 bản ghi/s, cùng phương án đó không đáp ứng yêu cầu; cần thử chỉ mục một phần, batch ghi hoặc thay đổi thiết kế truy cập dữ liệu.

**Không bỏ qua chỉ mục phục vụ ràng buộc dữ liệu.** Chỉ mục hỗ trợ PRIMARY KEY/UNIQUE thường bảo vệ tính đúng đắn và quan hệ dữ liệu, ngoài công dụng tăng tốc. Không được xóa chúng chỉ vì một báo cáo cho thấy tần suất đọc thấp.

## 6. Đo trước khi quyết định với PostgreSQL

Nên tiến hành thử nghiệm trong môi trường gần sản xuất, cùng kích thước bảng, phân bố dữ liệu, phiên bản engine, bộ tham số và tỷ lệ đọc/ghi tương đương. So sánh trạng thái **trước và sau** khi thêm từng ứng viên chỉ mục, kể cả chi phí xây dựng chỉ mục.

### 6.1. Kiểm tra kế hoạch truy vấn và lượng trang đọc

~~~sql
ANALYZE orders;

EXPLAIN (ANALYZE, BUFFERS)
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, id DESC
LIMIT 50;
~~~

Đọc các thông tin chủ yếu:

- `Seq Scan`, `Index Scan`, `Bitmap Heap Scan` hay `Index Only Scan`: hệ quản trị chọn đường truy cập nào.
- `actual time` và `rows`: thời gian và số hàng thực tế; so sánh với số hàng ước lượng để phát hiện thống kê lệch.
- `shared hit/read` trong `BUFFERS`: mức độ sử dụng trang từ cache hay phải đọc thêm.
- `Sort`, `Sort Method`: liệu vẫn phải sắp xếp và có dùng bộ nhớ/đĩa tạm hay không.

`EXPLAIN ANALYZE` **thực thi thật** truy vấn. Ví dụ trên là SELECT nên phù hợp để đo đọc; không chạy phiên bản UPDATE/DELETE trên dữ liệu sản xuất nếu chưa có biện pháp kiểm soát tác động. Thời gian đo lần đầu, lúc cache ấm và khi nhiều người dùng đồng thời có thể khác nhau.

### 6.2. Đo dung lượng và mức sử dụng chỉ mục

~~~sql
SELECT pg_size_pretty(pg_relation_size('idx_orders_tenant_status_created_id'))
       AS index_size;

SELECT pg_size_pretty(pg_indexes_size('orders')) AS all_indexes_size,
       pg_size_pretty(pg_total_relation_size('orders')) AS table_with_indexes;

SELECT indexrelname, idx_scan, idx_tup_read, idx_tup_fetch
FROM pg_stat_user_indexes
WHERE relname = 'orders'
ORDER BY indexrelname;
~~~

`pg_indexes_size` trả tổng dung lượng các chỉ mục của bảng; `pg_total_relation_size` gồm cả bảng, TOAST nếu có và các chỉ mục. Các bộ đếm sử dụng như `idx_scan` chỉ có ý nghĩa khi xét **khoảng thời gian thu thập, thời điểm reset thống kê và loại workload**; một chỉ mục phục vụ ràng buộc có thể vẫn bắt buộc dù số lần quét thấp.

Đối với truy vấn của ứng dụng, có thể dùng `pg_stat_statements` nếu extension được bật; đo thêm p95/p99 ở phía Java, throughput/transaction, thời gian commit, WAL phát sinh, CPU, bộ nhớ, cache hit, bloat, I/O và độ trễ replica. Đo SELECT đơn lẻ nhanh lên chưa đủ chứng minh toàn bộ dịch vụ nhanh hơn.

### 6.3. Thí nghiệm có thể tái lập

| Hạng mục đo | Trước khi thêm | Sau khi thêm | Cách đánh giá |
| --- | --- | --- | --- |
| SELECT trọng yếu: p50/p95/p99 | Lưu baseline | Đo cùng tham số và dữ liệu | Có đạt SLO và ổn định dưới tải? |
| INSERT/UPDATE: giao dịch/s, p95 | Lưu baseline | Chạy cùng tỷ lệ cập nhật trạng thái | Ghi có rơi dưới ngưỡng dịch vụ? |
| Số buffer đọc/hit và plan | Lưu kết quả `EXPLAIN` | So sánh từng truy vấn | Có thật sự giảm công việc? |
| Dung lượng bảng/chỉ mục, WAL | Ghi kích thước và tốc độ tăng | Theo dõi cả sau thời gian cập nhật/xóa | Có đủ đĩa và ngân sách backup? |
| CPU, I/O, lock/độ trễ replica | Quan sát dưới tải hỗn hợp | Lặp lại tải | Có chuyển nút thắt sang nơi khác? |

Hãy thử trên dữ liệu đại diện cho **tenant nhỏ, tenant lớn và các trạng thái có tỷ lệ phân bố khác nhau**. Với dữ liệu lớn, một chỉ mục có thể làm kế hoạch truy vấn thay đổi khi lượng hàng tăng; kết quả trên bảng vài nghìn hàng thường không đủ tin cậy.

## 7. Liên hệ với ranh giới persistence trong Java

Lớp repository/DAO phải tạo câu truy vấn thống nhất với chỉ mục đã chọn. Ví dụ sau dùng JDBC và `DataSource` để giữ phép lọc và thứ tự ổn định:

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public final class OrderQueries {
    public record OrderView(long id, long customerId,
                            BigDecimal totalAmount, Instant createdAt) {}

    public static List<OrderView> latestPaid(
            DataSource dataSource, long tenantId, int requestedLimit)
            throws SQLException {

        int limit = Math.max(1, Math.min(requestedLimit, 100));
        String sql = """
            SELECT id, customer_id, total_amount, created_at
            FROM orders
            WHERE tenant_id = ? AND status = 'PAID'
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """;

        List<OrderView> orders = new ArrayList<>();
        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement = connection.prepareStatement(sql)) {
            statement.setLong(1, tenantId);
            statement.setInt(2, limit);
            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    orders.add(new OrderView(
                        rs.getLong("id"),
                        rs.getLong("customer_id"),
                        rs.getBigDecimal("total_amount"),
                        rs.getTimestamp("created_at").toInstant()));
                }
            }
        }
        return orders;
    }
}
~~~

Cùng một `PreparedStatement` hỗ trợ an toàn tham số cho `tenant_id` và `LIMIT`. Giữ `status = 'PAID'` là điều kiện cố định phù hợp với chỉ mục một phần đã minh họa; nếu API chuyển sang lọc trạng thái tùy ý, phải xem lại thiết kế chỉ mục và kế hoạch thực thi. Giới hạn số hàng trả về bảo vệ cả database lẫn ứng dụng, nhưng cũng cần chỉ mục phù hợp để tránh quét và sắp xếp quá nhiều dữ liệu.

Khi phân trang sâu, `OFFSET` lớn có thể khiến database duyệt và bỏ qua nhiều hàng. Phân trang theo khóa (*keyset pagination*) với `(created_at, id)` là ứng viên tốt hơn cho luồng đơn hàng gần nhất:

~~~sql
SELECT id, customer_id, total_amount, created_at
FROM orders
WHERE tenant_id = ?
  AND status = 'PAID'
  AND (created_at, id) < (?, ?)
ORDER BY created_at DESC, id DESC
LIMIT ?;
~~~

Với PostgreSQL và khóa thời gian không NULL, cặp so sánh này tương ứng việc tìm các hàng cũ hơn con trỏ phân trang theo thứ tự giảm dần. Mọi API tiếp tục phải áp dụng điều kiện tenant để tránh truy cập chéo dữ liệu.

## 8. Vận hành và tiến hóa lược đồ

Thêm chỉ mục trong môi trường đang phục vụ giao dịch là thay đổi schema có chi phí riêng. Với PostgreSQL có thể cân nhắc:

~~~sql
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created_id
ON orders (tenant_id, status, created_at DESC, id DESC);
~~~

Lệnh này được thiết kế để giảm thời gian chặn ghi so với cách tạo thông thường nhưng thường tốn thêm thời gian/tài nguyên, có giới hạn giao dịch và cần theo dõi khi lỗi. `CREATE INDEX CONCURRENTLY` không chạy bên trong transaction block; khi dùng Flyway/Liquibase hoặc migration tự động, phải cấu hình cách thực thi tương ứng. Dự trù dung lượng trong quá trình xây dựng và kiểm tra cả tác động CPU/I/O.

Để loại bỏ chỉ mục trùng lặp, cần kiểm tra các câu truy vấn phụ thuộc, tính năng UNIQUE/PRIMARY KEY và kế hoạch rollback trước khi triển khai. Có thể dùng `DROP INDEX CONCURRENTLY` ở PostgreSQL trong tình huống phù hợp, nhưng không được tự động xóa chỉ mục ràng buộc hay giả định mọi engine có cùng tính năng.

Ngoài ra, nhớ rằng:

- Nhiều chỉ mục kéo dài thời gian backup vật lý và khôi phục tùy phương thức; backup logic có thể xây dựng lại chỉ mục và chịu chi phí ở giai đoạn restore.
- Cập nhật/xóa thường xuyên có thể gây bloat; theo dõi bảo trì, VACUUM/autovacuum và xem xét REINDEX nếu có chứng cứ, thay vì định kỳ xây lại vô điều kiện.
- Dữ liệu nhạy cảm có thể xuất hiện trong trang chỉ mục, WAL, backup và replica; chính sách phân quyền/mã hóa/retention phải áp dụng cho toàn bộ persistence, không chỉ hàng trong bảng.
- Trong MySQL InnoDB, khóa chính là clustered index và các secondary index lưu khóa chính để định vị hàng. Điều này làm cho chi phí chỉ mục phụ khác PostgreSQL; phải đo trên chính engine triển khai.
- Với các engine dùng LSM-tree (như RocksDB), quyết định đọc/ghi/dung lượng còn phụ thuộc memtable, SSTable, compaction, Bloom filter và write/read amplification; không thể áp nguyên công thức B-tree.

## 9. Những sai lầm thường gặp

**“Truy vấn chậm thì thêm chỉ mục.”** Trước tiên xác định nút thắt: truy vấn không dùng index vì lọc quá nhiều hàng, JOIN sai, thống kê cũ, thiếu giới hạn kết quả, N+1 query trong ORM, hoặc chờ khóa/I/O. Chỉ mục không sửa được mọi nguyên nhân.

**“Mỗi cột nên có một chỉ mục.”** Nhiều chỉ mục đơn cột có thể không thay thế được một chỉ mục đa cột phù hợp với điều kiện lọc và sắp xếp; đồng thời chúng tăng công việc khi ghi.

**“Index-only scan luôn nhanh nhất.”** Thêm cột vào `INCLUDE` có thể làm chỉ mục phình to, giảm khả năng giữ trong cache và tăng ghi; PostgreSQL còn phụ thuộc visibility map.

**“Chỉ mục có idx_scan bằng 0 thì xóa ngay.”** Bộ đếm có thể mới reset, chỉ mục phục vụ truy vấn hiếm nhưng quan trọng, hoặc phục vụ ràng buộc toàn vẹn dữ liệu. Cần xét đủ chu kỳ hoạt động.

**“EXPLAIN tốt là đủ.”** Phải kiểm tra hiệu năng hỗn hợp, biến động độ trễ, tốc độ ghi, ổ đĩa, WAL và thay đổi sau khi dữ liệu lớn lên.

## 10. Bài tập tư duy

Một hệ thống Java nhận nhiều sự kiện mới mỗi giây, bảng `events(tenant_id, event_time, severity, payload)` có hàng trăm triệu bản ghi. Người dùng thường xem sự kiện gần nhất của một tenant, trong khi báo cáo theo tháng quét phần lớn dữ liệu. Đội vận hành muốn tối ưu chi phí lưu trữ.

Hãy đề xuất **hai phương án** (ví dụ B-tree theo `tenant_id, event_time` và BRIN theo `event_time` khi tương quan thứ tự vật lý đủ tốt). Với mỗi phương án, xác định truy vấn hưởng lợi, tác động đối với ingest, dung lượng dự đoán và các phép đo cần thực hiện. Có nên giữ cả hai chỉ mục không? Câu trả lời phụ thuộc tỷ lệ truy vấn và SLO, vì vậy cần nêu điều kiện để ra quyết định thay vì chỉ trả lời có hoặc không.

### Ghi nhớ

**Chỉ mục là khoản đầu tư vào đường đọc, được trả bằng chi phí bảo trì khi ghi và dung lượng lưu trữ.** Thiết kế tốt bắt đầu từ truy vấn thật, kiểm tra kế hoạch thực thi, so sánh chi phí dưới tải đọc/ghi hỗn hợp, rồi giữ số lượng chỉ mục ít nhất có thể mà vẫn đáp ứng SLO và ràng buộc toàn vẹn dữ liệu.
