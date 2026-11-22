# Phối hợp điều kiện bằng, điều kiện phạm vi và thứ tự sắp xếp

Chỉ mục nhiều cột (composite index) có thể giúp cơ sở dữ liệu lọc dữ liệu và trả kết quả theo thứ tự cần thiết trong cùng một đường truy cập. Để thiết kế chỉ mục hiệu quả, cần hiểu cách các điều kiện bằng (equality), điều kiện phạm vi (range) và mệnh đề sắp xếp (ORDER BY) phối hợp với thứ tự các cột trong chỉ mục. Đặt đúng cột ở đúng vị trí có thể giảm số trang phải đọc, tránh bước sort và hỗ trợ phân trang; đặt sai thứ tự có thể khiến chỉ mục chỉ được dùng một phần hoặc buộc hệ quản trị vẫn phải đọc nhiều dữ liệu.

Nội dung thuộc chương **Thiết kế chỉ mục** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, thiết kế chỉ mục cần xuất phát từ mẫu truy vấn và workload thực tế, sau đó được kiểm chứng bằng execution plan, số dòng đọc, độ trễ và tác động lên thao tác ghi.

## 1. Cấu trúc chỉ mục nhiều cột

Với chỉ mục B-tree nhiều cột, các khóa được sắp xếp theo thứ tự từ cột đầu tiên đến cột tiếp theo. Có thể hình dung chỉ mục trên (customer_id, status, created_at) được sắp xếp theo thứ tự từ điển:

1. Trước tiên theo customer_id.
2. Trong các dòng có cùng customer_id, tiếp tục theo status.
3. Trong các dòng có cùng cả customer_id và status, tiếp tục theo created_at.

Thứ tự này tạo ra các vùng khóa liên tiếp. Nếu truy vấn cố định giá trị của cột đầu và cột thứ hai, cơ sở dữ liệu có thể tìm vùng tương ứng rồi đọc theo thứ tự created_at. Nếu chỉ lọc theo status mà không có điều kiện trên customer_id, các giá trị status có thể nằm rải rác trong nhiều vùng, nên chỉ mục thường không hỗ trợ tìm kiếm trực tiếp hiệu quả như chỉ mục bắt đầu bằng status.

Ví dụ tạo chỉ mục:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

Chỉ mục này có thể hữu ích cho các truy vấn có điều kiện trên customer_id, hoặc điều kiện trên cả customer_id và status. Nó cũng có thể cung cấp thứ tự theo created_at khi các cột đứng trước đã được cố định bằng giá trị phù hợp. Hiệu quả cụ thể còn tùy hệ quản trị, thống kê, độ chọn lọc và cách truy vấn sử dụng kết quả.

### Quy tắc tiền tố trái (leftmost prefix)

Với B-tree composite index, các cột ở đầu chỉ mục có vai trò quan trọng trong việc xác định vùng khóa cần đọc. Chỉ mục (A, B, C) thường hỗ trợ tốt các mẫu lọc như:

- A = ...
- A = ... AND B = ...
- A = ... AND B = ... AND C = ...
- A = ... AND B có điều kiện phạm vi, tùy toán tử và thứ tự khóa.

Truy vấn chỉ lọc theo B hoặc C thường không thể tìm một vùng liên tiếp tương đương như khi có điều kiện trên A. Một số hệ quản trị có skip scan hoặc cơ chế khác có thể khai thác chỉ mục trong một số trường hợp, nhưng không nên giả định tính năng đó luôn có sẵn hoặc luôn rẻ.

Quy tắc tiền tố trái là cách tư duy hữu ích cho B-tree; các loại chỉ mục khác như hash, bitmap, full-text, spatial hoặc chỉ mục chuyên biệt có quy tắc khác.

## 2. Điều kiện bằng và điều kiện phạm vi

Điều kiện bằng xác định một giá trị cụ thể của cột, ví dụ:

~~~sql
WHERE customer_id = ?
  AND status = ?
~~~

Điều kiện phạm vi chọn một đoạn giá trị, ví dụ:

~~~sql
WHERE created_at >= ?
  AND created_at < ?
~~~

Điều kiện bằng thường tạo ra tiền tố khóa chính xác. Sau khi các cột đầu đã được cố định bằng equality, hệ quản trị có thể tìm một đoạn liên tiếp trên cột kế tiếp. Vì vậy, một mẫu phổ biến khi thiết kế B-tree là đặt các cột equality ở phần đầu, tiếp theo là cột range, rồi đến các cột có thể phục vụ sắp xếp hoặc bao phủ truy vấn.

Đây là điểm khởi đầu, không phải công thức cứng cho mọi truy vấn. Cần xem các mẫu truy cập khác nhau trong workload, khả năng tái sử dụng tiền tố trái và cách bộ tối ưu thực sự dùng chỉ mục.

### Ví dụ: equality kết hợp range

Xét truy vấn lấy các đơn hàng đã thanh toán của một khách hàng trong một khoảng thời gian:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND status = 'PAID'
  AND created_at >= ?
  AND created_at < ?;
~~~

Một chỉ mục phù hợp để thử nghiệm là:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

Hai cột đầu được tìm theo giá trị bằng; cột created_at xác định đoạn thời gian cần đọc. Hệ quản trị có thể tìm vùng khóa ứng với khách hàng và trạng thái, sau đó quét phần thời gian nằm trong khoảng. Điều này thường giảm số dòng phải đọc so với chỉ mục chỉ có customer_id, hoặc quét toàn bảng.

Điều kiện created_at < ? giúp biểu diễn khoảng nửa mở [from, to). Cách viết này thường thuận tiện cho khoảng thời gian liên tiếp vì không phải tự tính thời điểm cuối ngày với độ chính xác mili giây hoặc micro giây. Kiểu dữ liệu và múi giờ vẫn cần được xử lý nhất quán.

### Cột sau điều kiện phạm vi

Với B-tree, sau khi đã dùng một cột làm điều kiện phạm vi, các cột tiếp theo thường không tiếp tục thu hẹp một vùng khóa liên tiếp theo cách đơn giản như các cột equality đứng trước. Tuy nhiên, tùy hệ quản trị và cấu trúc chỉ mục, chúng vẫn có thể được dùng để kiểm tra điều kiện ngay trên chỉ mục, giảm truy cập bảng hoặc hỗ trợ covering.

Ví dụ chỉ mục:

~~~sql
CREATE INDEX idx_orders_customer_created_status
ON orders (customer_id, created_at, status);
~~~

Chỉ mục này có thể phù hợp cho customer_id = ? cùng khoảng created_at, đồng thời dữ liệu trong vùng đó được sắp xếp theo created_at rồi status. Điều kiện status = 'PAID' có thể được kiểm tra khi đọc các mục chỉ mục, nhưng nếu status không nằm trước cột phạm vi thì nó không nhất thiết giúp giới hạn vùng thời gian phải quét.

Không nên kết luận rằng mọi cột đặt sau range đều vô dụng. Cần phân biệt ba khả năng: cột có giúp xác định điểm bắt đầu/kết thúc vùng quét hay không; cột có thể được kiểm tra trong chỉ mục hay không; và cột có giúp trả kết quả theo thứ tự cần thiết hay không.

## 3. Phối hợp điều kiện bằng với thứ tự cột

Khi truy vấn có nhiều điều kiện equality, thứ tự giữa các cột equality có thể linh hoạt hơn so với vị trí của cột range. Ví dụ hai chỉ mục sau:

~~~sql
CREATE INDEX idx_a
ON orders (customer_id, status, created_at);

CREATE INDEX idx_b
ON orders (status, customer_id, created_at);
~~~

Với truy vấn có cả customer_id = ? và status = ?, cả hai thứ tự có thể xác định một tiền tố gồm hai giá trị bằng rồi tiếp tục theo created_at. Tuy nhiên, chúng không tương đương đối với mọi truy vấn:

| Mẫu truy vấn | Chỉ mục bắt đầu bằng customer_id | Chỉ mục bắt đầu bằng status |
| --- | --- | --- |
| Lọc theo customer_id | Có tiền tố phù hợp | Thường không có tiền tố trái phù hợp |
| Lọc theo status | Thường không có tiền tố trái phù hợp | Có tiền tố phù hợp |
| Lọc cả hai equality | Có thể dùng cả hai cột đầu | Có thể dùng cả hai cột đầu |
| Lọc cả hai và sắp xếp theo created_at | Có thể hỗ trợ thứ tự sau hai equality | Có thể hỗ trợ thứ tự sau hai equality |

Do đó, không nên áp dụng máy móc quy tắc “cột có độ chọn lọc cao nhất luôn đứng đầu”. Hãy xem các truy vấn cần hỗ trợ, cột nào thường xuất hiện độc lập, điều kiện nối, phân vùng dữ liệu, khả năng tái sử dụng tiền tố và chi phí duy trì chỉ mục. Độ chọn lọc vẫn quan trọng với cost model, nhưng không tự quyết định thứ tự cột trong mọi trường hợp.

### Khi một cột equality không luôn có mặt

Giả sử workload có hai mẫu:

~~~sql
-- Mẫu A: khách hàng xem tất cả đơn hàng của mình
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC;

-- Mẫu B: nhân viên tra cứu đơn hàng theo trạng thái
SELECT order_id, created_at
FROM orders
WHERE status = ?
ORDER BY created_at DESC;
~~~

Một chỉ mục (customer_id, status, created_at) không tự động phục vụ tốt mẫu B vì thiếu điều kiện trên cột dẫn đầu. Một chỉ mục (status, customer_id, created_at) cũng không tự động phục vụ tốt mẫu A. Nếu cả hai mẫu quan trọng, có thể cần hai chỉ mục riêng, hoặc cần thay đổi cách truy vấn/thiết kế dữ liệu sau khi đo workload và đánh giá chi phí ghi.

Không nên tạo chỉ mục cho mọi tổ hợp cột có thể nghĩ ra. Mỗi chỉ mục làm tăng dung lượng, chi phí ghi, bảo trì và thời gian cập nhật thống kê. Chọn các mẫu có tác động lớn nhất dựa trên tần suất, tổng thời gian, độ trễ và mức quan trọng nghiệp vụ.

## 4. Phối hợp range với ORDER BY

Điều kiện phạm vi và thứ tự sắp xếp thường xuất hiện cùng nhau trong các màn hình lịch sử, danh sách giao dịch hoặc báo cáo theo thời gian. Thứ tự cột trong chỉ mục quyết định hệ quản trị có thể vừa giới hạn phạm vi vừa trả kết quả theo thứ tự cần thiết hay không.

Xét truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC;
~~~

Chỉ mục:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

Sau khi tìm đúng customer_id, hệ quản trị có thể quét phần khóa created_at theo hướng phù hợp và trả các dòng theo thời gian. Một số hệ quản trị có thể đọc B-tree theo chiều ngược để đáp ứng thứ tự DESC dù chỉ mục được tạo mặc định ASC; khả năng và chi phí cần xác nhận trên nền tảng cụ thể.

### Khi cột sắp xếp đứng sau một cột chưa được cố định

Giả sử chỉ mục là (customer_id, status, created_at) và truy vấn:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC;
~~~

Vì status không được cố định, các mục trong vùng khách hàng được sắp xếp theo status trước rồi mới theo created_at. Kết quả không nhất thiết được sắp xếp toàn cục theo created_at. Hệ quản trị có thể cần sort hoặc chọn một chỉ mục khác.

Nếu truy vấn luôn lọc cả customer_id và status bằng equality, cột created_at đứng sau chúng có thể hỗ trợ ORDER BY. Nhưng khi bỏ điều kiện status, thứ tự sắp xếp có thể không còn được đáp ứng.

### Range trên cột trước và thứ tự trên cột sau

Xét chỉ mục (customer_id, status, created_at) với truy vấn:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
  AND status >= ?
ORDER BY created_at DESC;
~~~

Sau khi cố định customer_id, hệ quản trị phải đọc một khoảng giá trị status. Bên trong khoảng đó, các dòng được nhóm theo status trước rồi mới theo created_at. Vì status thay đổi, thứ tự created_at không phải thứ tự toàn cục của toàn bộ kết quả. Một bước sort có thể vẫn cần thiết.

Nếu yêu cầu nghiệp vụ cần sắp xếp toàn cục theo thời gian trong phạm vi khách hàng, chỉ mục (customer_id, created_at) có thể phù hợp hơn cho đường truy cập và ORDER BY; điều kiện status khi đó có thể được kiểm tra như bộ lọc còn lại. Lựa chọn nào nhanh hơn phụ thuộc tỷ lệ dữ liệu khớp status, lượng trang phải đọc và chi phí sort.

Nguyên tắc cần nhớ: một cột nằm sau cột range có thể giúp kiểm tra hoặc bao phủ truy vấn, nhưng không tự động tạo thứ tự toàn cục theo cột đó.

## 5. Thứ tự ASC, DESC và các cột sắp xếp kết hợp

Chỉ mục có thể khai báo hướng sắp xếp cho từng cột. Hướng này quan trọng khi truy vấn yêu cầu thứ tự hỗn hợp, ví dụ:

~~~sql
ORDER BY created_at DESC, order_id ASC
~~~

Một B-tree có thể được quét xuôi hoặc ngược. Quét ngược thường đảo hướng của toàn bộ thứ tự khóa; nó không phải lúc nào cũng thay thế được một thứ tự hỗn hợp tùy ý. Nếu cần created_at DESC nhưng order_id ASC, chỉ mục có hướng tương ứng trên từng cột có thể giúp tránh sort, tùy hỗ trợ của hệ quản trị.

Ví dụ minh họa:

~~~sql
CREATE INDEX idx_orders_customer_time_id
ON orders (customer_id, created_at DESC, order_id ASC);
~~~

Với điều kiện equality trên customer_id, chỉ mục này có thứ tự tiếp theo phù hợp với created_at DESC, order_id ASC. Cần kiểm tra cú pháp và khả năng hỗ trợ hướng cột của hệ quản trị đang dùng.

### Sắp xếp ổn định khi giá trị bị trùng

Nếu chỉ ORDER BY created_at DESC, nhiều đơn hàng có thể có cùng timestamp. Khi đó, thứ tự giữa các dòng cùng thời điểm không được bảo đảm nếu không có tiêu chí phụ. Với phân trang, điều này có thể khiến dòng xuất hiện lặp hoặc bị bỏ qua giữa các lần gọi khi dữ liệu thay đổi.

Có thể thêm khóa duy nhất làm tiêu chí phụ:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Và thiết kế chỉ mục tương ứng:

~~~sql
CREATE INDEX idx_orders_customer_time_order
ON orders (customer_id, created_at DESC, order_id DESC);
~~~

order_id tạo thứ tự xác định trong nhóm có cùng created_at, miễn là nó thực sự duy nhất trong phạm vi dữ liệu. Quy tắc tie-breaker phải thống nhất với cách phân trang và ngữ nghĩa nghiệp vụ.

### NULL và collation

Thứ tự của NULL (NULLS FIRST/LAST) và cách so sánh chuỗi theo collation có thể khác giữa hệ quản trị hoặc cấu hình. Nếu truy vấn yêu cầu thứ tự cụ thể với NULL hoặc chuỗi, cần kiểm tra chỉ mục có cùng quy tắc sắp xếp hay không. Một chỉ mục có thứ tự khóa không tương thích có thể không loại bỏ được sort.

## 6. Phân trang và truy vấn lấy N dòng đầu

Một workload phổ biến là lấy 20, 50 hoặc 100 bản ghi mới nhất:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Chỉ mục (customer_id, created_at DESC, order_id DESC) có thể cho phép tìm đúng vùng khách hàng rồi đọc các dòng đầu theo thứ tự yêu cầu. Nếu chỉ mục phù hợp và bộ tối ưu chọn sử dụng, hệ quản trị có thể dừng sau khi tìm đủ 50 dòng, giảm lượng dữ liệu phải đọc và tránh sort toàn bộ tập kết quả.

### OFFSET sâu

Với phân trang bằng OFFSET:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 50000;
~~~

Ngay cả khi chỉ mục hỗ trợ thứ tự, hệ quản trị vẫn có thể phải đi qua và bỏ qua hàng chục nghìn dòng trước khi trả 50 dòng tiếp theo. Chi phí tăng theo độ sâu trang.

Keyset pagination (phân trang theo khóa tiếp nối) dùng giá trị cuối cùng của trang trước làm mốc:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
  AND (
    created_at < ?
    OR (created_at = ? AND order_id < ?)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Với chỉ mục phù hợp trên (customer_id, created_at DESC, order_id DESC), truy vấn có thể tiếp tục từ vị trí khóa gần trang trước thay vì bỏ qua toàn bộ các dòng cũ. Cú pháp điều kiện tiếp nối cần khớp hướng sắp xếp, kiểu dữ liệu và cách xử lý NULL. Với nhiều cột, điều kiện lexicographic có thể được viết bằng biểu thức so sánh hàng nếu hệ quản trị hỗ trợ, hoặc khai triển thành các nhánh OR tương đương.

Keyset pagination không phù hợp với mọi giao diện. Nó thường yêu cầu lưu cursor/mốc cuối trang, khó nhảy trực tiếp đến một số trang tùy ý và cần quyết định cách xử lý khi bản ghi mới được thêm trong lúc người dùng duyệt. Chỉ mục và truy vấn phải được thiết kế cùng ngữ nghĩa phân trang.

## 7. IN, OR và nhiều vùng khóa

Điều kiện equality đơn thường xác định một vùng khóa. Điều kiện IN có thể tương ứng với nhiều giá trị bằng:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = ?
  AND status IN ('PAID', 'SHIPPED')
ORDER BY created_at DESC;
~~~

Với chỉ mục (customer_id, status, created_at), hệ quản trị có thể đọc các vùng cho từng status. Tuy nhiên, mỗi vùng được sắp xếp theo created_at riêng; ghép các vùng lại không tự động bảo đảm toàn bộ kết quả có thứ tự created_at toàn cục. Hệ quản trị có thể dùng merge, sort hoặc lựa chọn đường truy cập khác.

Nếu truy vấn cần ORDER BY toàn cục theo created_at và status có nhiều giá trị, chỉ mục (customer_id, created_at) có thể phù hợp hơn về thứ tự, còn status được lọc sau. Phương án nào giảm tổng công việc hơn tùy độ chọn lọc của status và số dòng phải đọc.

Điều kiện OR trên các cột khác nhau cũng có thể dẫn đến nhiều nhánh truy cập, bitmap/index merge hoặc quét bảng. Cách thực hiện tùy bộ tối ưu và hệ quản trị. Không nên suy luận rằng chỉ mục chứa tất cả cột trong OR sẽ luôn tạo một lần seek hiệu quả.

## 8. Bao phủ truy vấn và cột INCLUDE

Ngoài các cột dùng để tìm kiếm và sắp xếp, truy vấn có thể cần thêm cột để trả kết quả. Nếu chỉ mục chứa đủ dữ liệu cần thiết, một số hệ quản trị có thể thực hiện index-only scan hoặc covering index access, giảm số lần truy cập bảng.

Ví dụ:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 50;
~~~

Các cột customer_id, status, created_at có thể làm khóa chỉ mục. order_id và total_amount có thể cần được lấy thêm để trả kết quả. Một số hệ quản trị hỗ trợ cột INCLUDE hoặc payload không tham gia thứ tự khóa để bao phủ truy vấn; cú pháp và điều kiện index-only khác nhau giữa các nền tảng.

Không nên đưa mọi cột SELECT vào phần khóa. Khóa càng rộng thì chỉ mục càng lớn, cache chứa được ít mục hơn và thao tác ghi càng tốn chi phí. Nếu có INCLUDE, hãy đánh giá các cột payload riêng với cột khóa. Một index-only scan cũng có thể cần kiểm tra visibility hoặc đọc bảng trong một số hệ quản trị, nên không bảo đảm luôn không truy cập bảng.

## 9. Cách chọn thứ tự cột cho một workload

Thay vì thiết kế chỉ mục từ một câu SQL riêng lẻ, hãy nhóm các mẫu truy vấn thường gặp và xác định phần cấu trúc chung. Quy trình thực hành:

1. **Thu thập workload:** lấy fingerprint, số lần gọi, tổng thời gian, p95/p99, số dòng đọc, điều kiện lọc và ORDER BY.
2. **Nhóm mẫu truy vấn:** phân loại truy vấn theo các cột equality, cột range, cột sắp xếp, JOIN và LIMIT.
3. **Xác định tiền tố dùng chung:** tìm các cột thường được cố định bằng equality và các truy vấn cần hỗ trợ riêng từng tiền tố.
4. **Đặt cột range:** xác định điều kiện phạm vi chính và xem nó có trùng với cột sắp xếp đầu tiên hay không.
5. **Kiểm tra thứ tự kết quả:** xác định ORDER BY có được hỗ trợ sau các cột đã cố định hay bị phá vỡ bởi cột không được cố định.
6. **Đánh giá độ chọn lọc:** dùng thống kê và phân bố thực tế để ước lượng số dòng cần đọc cho từng nhóm tham số.
7. **Xem xét bao phủ:** chỉ thêm cột trả kết quả khi lợi ích giảm truy cập bảng đủ lớn so với chi phí tăng kích thước.
8. **Đo và so sánh:** kiểm tra execution plan, logical/physical reads, sort, số dòng thực tế, latency và tác động đến ghi.
9. **Theo dõi sau triển khai:** quan sát workload tổng thể, dung lượng, thời gian bảo trì và các truy vấn liên quan.

### Không chọn cột chỉ bằng độ chọn lọc

Độ chọn lọc (selectivity) cho biết một điều kiện lọc giữ lại tỷ lệ dữ liệu nhỏ hay lớn. Điều kiện có độ chọn lọc cao thường loại bỏ nhiều dòng và có thể giúp index access hiệu quả. Nhưng trong composite index, thứ tự cột còn phụ thuộc vào:

- Những truy vấn nào cần dùng riêng từng cột.
- Cột nào thường được cố định bằng equality.
- Cột range nào xác định vùng đọc chính.
- ORDER BY và LIMIT cần được hỗ trợ ra sao.
- JOIN có dùng cột làm khóa tra cứu không.
- Khả năng tái sử dụng tiền tố trái giữa các truy vấn.
- Chi phí cập nhật chỉ mục khi INSERT, UPDATE, DELETE.

Ví dụ, status có thể chỉ có vài giá trị và độ chọn lọc thấp, còn customer_id có nhiều giá trị. Nếu mọi truy vấn quan trọng đều lọc cả hai bằng equality, thứ tự hai cột có thể vẫn dùng được cho mẫu đó. Nhưng nếu nhiều truy vấn chỉ lọc customer_id, đặt customer_id ở đầu thường hữu ích hơn. Quyết định cần dựa trên toàn bộ tập truy vấn, không chỉ số giá trị phân biệt của từng cột.

## 10. Đọc execution plan để xác nhận chỉ mục có được dùng đúng không

Sau khi tạo hoặc thay đổi chỉ mục, hãy kiểm tra kế hoạch thực thi với tham số đại diện. Một chỉ mục tồn tại không có nghĩa truy vấn chắc chắn dùng nó; bộ tối ưu có thể chọn scan hoặc một chỉ mục khác vì cost ước lượng thấp hơn.

Các điểm cần quan sát:

- Chỉ mục có xuất hiện trong đường truy cập hay không.
- Các điều kiện nào được dùng để xác định vùng seek/range scan.
- Điều kiện nào chỉ được áp dụng như residual filter sau khi đọc.
- Có bước Sort hoặc Top-N Sort hay không.
- Có phải truy cập bảng để lấy thêm cột không.
- Estimated rows có gần actual rows không.
- Số trang hoặc logical reads có giảm không.
- Số lần lookup, loops, key lookup hoặc bookmark lookup có tăng không.
- Thời gian CPU, elapsed time và wait thay đổi thế nào.

Ví dụ, nếu kế hoạch dùng chỉ mục (customer_id, status, created_at) nhưng vẫn sort, hãy kiểm tra truy vấn có cố định cả customer_id và status hay không, ORDER BY có khớp thứ tự created_at không, hướng ASC/DESC có tương thích không và có cột khóa nào chưa được cố định đứng trước cột sắp xếp hay không.

Nếu truy vấn dùng chỉ mục nhưng vẫn đọc quá nhiều dòng, xem điều kiện range, residual predicate, độ chọn lọc, thống kê và phân bố dữ liệu. Nếu optimizer không chọn chỉ mục, so sánh chi phí scan với index access; có thể bảng nhỏ hoặc điều kiện trả về phần lớn dữ liệu khiến scan hợp lý hơn.

## 11. Chi phí và rủi ro khi thêm composite index

Chỉ mục nhiều cột có thể cải thiện truy vấn đọc nhưng cũng có chi phí:

- **Dung lượng:** thêm cột khóa làm mỗi mục chỉ mục rộng hơn và tăng kích thước lưu trữ.
- **Ghi dữ liệu:** INSERT phải thêm mục chỉ mục; UPDATE cột khóa có thể phải di chuyển hoặc sửa mục; DELETE phải loại bỏ mục.
- **Cache:** chỉ mục lớn chiếm bộ nhớ đệm, có thể đẩy dữ liệu khác ra khỏi cache.
- **Bảo trì:** tạo, rebuild, vacuum hoặc reorganize chỉ mục tùy hệ quản trị có thể tiêu tốn I/O, CPU và thời gian.
- **Tranh chấp:** cập nhật chỉ mục có thể tăng lock, latch hoặc contention tùy cấu trúc và mức đồng thời.
- **Trùng lặp:** nhiều chỉ mục có tiền tố giống nhau có thể làm tăng chi phí ghi và quản trị mà ít mang lại lợi ích bổ sung.

Không nên giữ chỉ mục chỉ vì nó được dùng trong một truy vấn thử nghiệm. Hãy xem tần suất thực tế, tổng thời gian tiết kiệm, các truy vấn khác được hưởng lợi, chi phí ghi và dung lượng. Một chỉ mục phục vụ báo cáo chạy một lần mỗi ngày có thể không đáng giữ nếu nó làm chậm hàng triệu thao tác ghi, trừ khi báo cáo có yêu cầu nghiệp vụ đặc biệt.

## 12. Ví dụ tổng hợp: danh sách đơn hàng theo khách hàng

Một ứng dụng có ba mẫu truy vấn:

**Mẫu A – Đơn hàng mới nhất của khách hàng**

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

**Mẫu B – Đơn hàng đã thanh toán của khách hàng trong một khoảng thời gian**

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND status = 'PAID'
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC, order_id DESC;
~~~

**Mẫu C – Nhân viên tra cứu đơn hàng theo trạng thái**

~~~sql
SELECT order_id, created_at
FROM orders
WHERE status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 100;
~~~

Một chỉ mục (customer_id, status, created_at, order_id) có thể hỗ trợ mẫu B khi hai cột đầu được cố định bằng equality, nhưng không tự động hỗ trợ ORDER BY của mẫu A vì status không được cố định. Nó cũng không có tiền tố trái phù hợp cho mẫu C vì truy vấn chỉ lọc status.

Một phương án có thể khảo sát là:

~~~sql
CREATE INDEX idx_orders_customer_time
ON orders (customer_id, created_at DESC, order_id DESC);

CREATE INDEX idx_orders_status_time
ON orders (status, created_at DESC, order_id DESC);
~~~

Chỉ mục đầu có thể hỗ trợ mẫu A và mẫu B theo thứ tự thời gian; điều kiện status của mẫu B có thể được kiểm tra thêm. Chỉ mục thứ hai có thể hỗ trợ mẫu C. Một chỉ mục thứ ba bắt đầu bằng (customer_id, status, created_at, order_id) có thể giảm lượng đọc cho mẫu B nếu status rất chọn lọc và workload cho thấy lợi ích đủ lớn, nhưng sẽ làm tăng chi phí ghi và dung lượng.

Không thể quyết định số lượng chỉ mục chỉ từ ba câu SQL. Cần thu thập tần suất, tổng thời gian, p95/p99, số dòng đọc, tỷ lệ đọc/ghi và kế hoạch hiện tại. Sau đó thử từng phương án trên dữ liệu đại diện, đo cả ba mẫu cùng thao tác ghi, rồi chọn cấu hình có lợi ích tổng thể phù hợp.

## 13. Những sai lầm thường gặp

- **Đặt mọi cột vào chỉ mục:** làm chỉ mục rộng, tốn dung lượng và tăng chi phí ghi.
- **Cho rằng cột chọn lọc cao luôn phải đứng đầu:** bỏ qua tiền tố trái và các truy vấn chỉ lọc một phần cột.
- **Đặt cột range trước mọi cột khác:** có thể làm mất khả năng dùng equality phía sau để xác định vùng khóa hẹp.
- **Đặt cột ORDER BY sau một cột chưa được cố định:** chỉ mục có thể sắp xếp theo cột trung gian trước, nên không đáp ứng thứ tự toàn cục mong muốn.
- **Cho rằng cột sau range không có ích:** cột sau range vẫn có thể hỗ trợ residual filtering, covering hoặc thứ tự phụ trong một số mẫu.
- **Cho rằng IN giống một equality đơn:** nhiều vùng khóa có thể cần merge hoặc sort để tạo thứ tự toàn cục.
- **Bỏ qua hướng ASC/DESC, NULL và collation:** kế hoạch có thể vẫn cần bước sort.
- **Không thêm tie-breaker cho phân trang:** thứ tự không ổn định khi nhiều dòng có cùng giá trị sắp xếp.
- **Chỉ kiểm tra truy vấn đọc:** không đo chi phí INSERT, UPDATE, DELETE và bảo trì chỉ mục.
- **Tin rằng index tồn tại thì optimizer sẽ dùng:** lựa chọn cuối cùng vẫn phụ thuộc cost model và thống kê.

## 14. Nguyên tắc cần ghi nhớ

- Composite B-tree được sắp xếp theo thứ tự cột; tiền tố trái quyết định những vùng khóa có thể tìm kiếm hiệu quả.
- Các điều kiện equality thường tạo tiền tố cố định; cột range tiếp theo thường xác định vùng quét.
- Cột sau range vẫn có thể hỗ trợ kiểm tra điều kiện hoặc bao phủ dữ liệu, nhưng không tự động thu hẹp vùng quét hay tạo thứ tự toàn cục.
- ORDER BY được hỗ trợ tốt khi các cột đứng trước đã được cố định và thứ tự cột/hướng sắp xếp tương thích.
- Thứ tự giữa các cột equality cần được chọn theo toàn bộ workload và khả năng tái sử dụng tiền tố, không theo một quy tắc độ chọn lọc đơn giản.
- IN, OR, NULL, collation và thứ tự ASC/DESC có thể làm thay đổi khả năng tránh sort.
- Phân trang sâu nên được đánh giá; keyset pagination có thể giảm chi phí khi có khóa tiếp nối ổn định.
- Chỉ mục bao phủ có thể giảm truy cập bảng nhưng làm tăng kích thước và chi phí ghi.
- Luôn kiểm tra execution plan, estimated/actual rows, số đọc, latency và ảnh hưởng của workload ghi sau khi điều chỉnh.

Phối hợp điều kiện bằng, điều kiện phạm vi và thứ tự sắp xếp là nền tảng để thiết kế composite index đúng với cách ứng dụng truy cập dữ liệu. Khi hiểu thứ tự từ điển của B-tree và xác định rõ các cột được cố định, cột xác định phạm vi cùng thứ tự kết quả cần trả, nhóm phát triển có thể xây dựng chỉ mục có mục tiêu và chứng minh hiệu quả bằng số liệu thực tế.
