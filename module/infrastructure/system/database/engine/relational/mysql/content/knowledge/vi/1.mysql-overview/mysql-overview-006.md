# Đặc điểm tải giao dịch OLTP, báo cáo và tải hỗn hợp

Một hệ thống bán hàng có thể nhận hàng nghìn yêu cầu đặt hàng trong giờ cao điểm, đồng thời cho phép nhân viên xem doanh thu theo ngày, sản phẩm và khu vực. Cả hai nhóm yêu cầu đều đọc dữ liệu từ MySQL, nhưng cách chúng sử dụng tài nguyên rất khác nhau. Đặt hàng cần xử lý nhanh một vài bản ghi và hoàn tất giao dịch an toàn; báo cáo có thể phải đọc hàng triệu bản ghi rồi nhóm và tính tổng. Khi hai nhóm chạy trên cùng máy chủ, chúng tạo thành **tải hỗn hợp**.

Hiểu đặc điểm của từng loại tải giúp chọn cấu trúc bảng và chỉ mục, tổ chức transaction, đánh giá kế hoạch thực thi, phân bổ tài nguyên và quyết định khi nào nên tách tải sang máy chủ đọc hoặc hệ thống phân tích.

## 1. Nhận diện ba kiểu tải

### 1.1. Tải giao dịch OLTP

OLTP (Online Transaction Processing) phục vụ các thao tác nghiệp vụ trực tuyến như tạo đơn hàng, trừ tồn kho, ghi nhận thanh toán, cập nhật hồ sơ hoặc chuyển trạng thái đơn. Mỗi yêu cầu thường làm việc với một tập dữ liệu tương đối nhỏ và cần trả kết quả trong thời gian ngắn.

Các đặc điểm thường gặp:

- **Giao dịch ngắn và có ranh giới rõ ràng:** một thao tác nghiệp vụ gồm một hoặc vài câu lệnh, sau đó `COMMIT` hoặc `ROLLBACK`. Ví dụ, tạo đơn hàng và trừ tồn kho phải thành công hoặc thất bại cùng nhau.
- **Nhiều phiên đồng thời:** nhiều người dùng hoặc dịch vụ cùng đọc và cập nhật các hàng dữ liệu. Khả năng xử lý đồng thời và thời gian chờ khóa ảnh hưởng trực tiếp đến trải nghiệm.
- **Đọc và ghi có tính chọn lọc:** truy vấn thường tìm theo khóa chính, mã khách hàng, mã đơn hàng hoặc một điều kiện có chỉ mục; thao tác ghi thường tác động đến một số hàng.
- **Độ trễ quan trọng:** hệ thống quan tâm đến thời gian phản hồi của từng yêu cầu, đặc biệt là các phân vị p95 và p99 trong giờ cao điểm, chứ không chỉ thời gian trung bình.
- **Tính đúng đắn và độ bền dữ liệu:** ràng buộc, tính nguyên tử, tính nhất quán, cô lập và độ bền của InnoDB phải được giữ trong các tình huống cạnh tranh và lỗi.

Ví dụ, một giao dịch bán hàng có thể kiểm tra và trừ tồn kho, sau đó ghi chi tiết đơn hàng. Điều kiện cập nhật tồn kho nên được đặt ngay trong câu lệnh để tránh kiểu đọc số lượng trước rồi cập nhật dựa trên một giá trị đã lỗi thời:

```sql
START TRANSACTION;

UPDATE inventory
SET available_qty = available_qty - 2
WHERE product_id = 42
  AND available_qty >= 2;

-- Ứng dụng kiểm tra số hàng bị ảnh hưởng.
-- Nếu bằng 0, hết hàng hoặc sản phẩm không tồn tại: ROLLBACK.
-- Nếu bằng 1, tiếp tục ghi đơn hàng và chi tiết đơn hàng.

INSERT INTO order_items (order_id, product_id, quantity)
VALUES (9001, 42, 2);

COMMIT;
```

Ví dụ rút gọn này giả định ứng dụng đã có đơn hàng hợp lệ và kiểm tra kết quả `UPDATE` trước khi chạy `INSERT`. Trong mã thực tế, nếu không trừ được đúng một hàng thì phải `ROLLBACK`; không được tiếp tục ghi chi tiết đơn hàng. Các câu lệnh thuộc cùng một nghiệp vụ phải nằm trong cùng transaction để không tạo ra trạng thái nửa chừng.

### 1.2. Tải báo cáo và phân tích

Tải báo cáo (reporting workload) trả lời câu hỏi tổng hợp như doanh thu theo ngày, số đơn theo trạng thái, nhóm khách hàng có giá trị mua cao hoặc xu hướng bán hàng theo tháng. Đây là các truy vấn thiên về đọc và thường phải kết hợp nhiều hàng, nhiều bảng.

Các đặc điểm thường gặp:

- **Phạm vi đọc rộng:** truy vấn lọc theo khoảng thời gian, quét nhiều bản ghi hoặc kết hợp dữ liệu từ nhiều bảng.
- **Tính toán tổng hợp:** sử dụng `GROUP BY`, `COUNT`, `SUM`, `AVG`, `DISTINCT`, hàm cửa sổ hoặc các phép nối lớn.
- **Thời gian chạy dài hơn:** một báo cáo có thể chạy vài giây hoặc vài phút, tùy kích thước dữ liệu và độ phức tạp.
- **Số lượng yêu cầu có thể thấp nhưng chi phí mỗi yêu cầu cao:** một dashboard được làm mới liên tục hoặc một truy vấn tổng hợp lớn có thể tiêu tốn nhiều CPU, bộ nhớ và I/O hơn nhiều giao dịch OLTP nhỏ.
- **Độ mới dữ liệu có thể linh hoạt:** báo cáo tài chính cuối ngày có thể chấp nhận dữ liệu được tổng hợp theo lịch; màn hình giám sát vận hành có thể cần dữ liệu gần thời gian thực.

Ví dụ truy vấn doanh thu theo ngày trong một tháng:

```sql
SELECT
    DATE(created_at) AS sales_day,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
GROUP BY DATE(created_at)
ORDER BY sales_day;
```

Điều kiện thời gian dùng khoảng nửa mở (`>=` ngày đầu và `<` ngày kế tiếp) để bao phủ đầy đủ thời điểm trong tháng, kể cả khi cột có phần thời gian. Cách lọc này cũng cho phép bộ tối ưu xem xét chỉ mục trên `created_at`; bọc cột trong `DATE(created_at)` ở phần `WHERE` thường làm giảm khả năng sử dụng chỉ mục thông thường. Tuy vậy, `GROUP BY DATE(created_at)` vẫn có thể cần bảng tạm hoặc sắp xếp. Cần xem kế hoạch thực thi thực tế thay vì suy luận chỉ từ câu SQL.

### 1.3. Tải hỗn hợp

Tải hỗn hợp (mixed workload) xuất hiện khi giao dịch OLTP và truy vấn báo cáo cùng sử dụng một máy chủ MySQL, một cụm lưu trữ hoặc một tập tài nguyên có giới hạn. Chẳng hạn, hệ thống vẫn tiếp nhận đơn hàng trong khi dashboard chạy báo cáo doanh thu theo 12 tháng.

Đây là tình huống phổ biến ở hệ thống vừa và nhỏ. Một máy chủ có thể đáp ứng tốt cả hai loại tải khi dữ liệu, số người dùng và mức độ phức tạp còn vừa phải. Vấn đề xuất hiện khi các truy vấn báo cáo chiếm tài nguyên hoặc kéo dài trạng thái đọc, khiến giao dịch cần độ trễ thấp phải chờ đợi.

Không thể đánh giá tải hỗn hợp chỉ bằng tỷ lệ đọc/ghi. Hai hệ thống đều có 90% thao tác đọc nhưng có thể khác xa nhau: một hệ thống chủ yếu tra cứu theo khóa chính; hệ thống kia chạy các phép nối và tổng hợp trên hàng triệu bản ghi. Cần xem kích thước dữ liệu được chạm tới, độ đồng thời, thời gian chạy, mức sử dụng tài nguyên và yêu cầu độ mới dữ liệu.

## 2. So sánh đặc điểm của từng loại tải

| Khía cạnh | OLTP | Báo cáo | Tải hỗn hợp |
|---|---|---|---|
| Mục tiêu | Hoàn tất nghiệp vụ chính xác | Khai thác và tổng hợp dữ liệu | Đáp ứng nghiệp vụ và phân tích cùng lúc |
| Mẫu truy cập | Nhiều lần đọc/ghi nhỏ, có chọn lọc | Đọc phạm vi rộng, nối và tổng hợp | Đan xen truy vấn nhỏ và truy vấn tốn tài nguyên |
| Transaction | Thường ngắn, cần commit nhanh | Có thể là truy vấn dài hoặc snapshot đọc | Transaction ngắn phải chia sẻ tài nguyên với truy vấn dài |
| Ưu tiên | Độ trễ thấp, thông lượng ổn định, tính đúng đắn | Thời gian hoàn tất, tính đầy đủ và độ mới dữ liệu | Giữ SLA nghiệp vụ trong khi đáp ứng báo cáo |
| Điểm nghẽn thường gặp | Chờ khóa, nhiều lần truy cập ngẫu nhiên, chỉ mục ghi nặng | Quét nhiều trang, sort, bảng tạm, phép nối lớn | Cạnh tranh CPU, bộ nhớ, I/O và độ trễ do truy vấn dài |
| Cách tối ưu | Transaction ngắn, chỉ mục phù hợp, truy cập theo khóa | Giảm dữ liệu phải quét, tổng hợp trước hoặc chuyển tải | Giới hạn truy vấn nặng, tách luồng đọc khi cần |

Đây là các khuynh hướng, không phải quy tắc tuyệt đối. Một truy vấn báo cáo có bộ lọc rất chọn lọc có thể chạy nhanh; một giao dịch OLTP thiết kế kém có thể quét cả bảng. Phân loại theo hành vi thực tế của truy vấn quan trọng hơn tên gọi của màn hình hay API.

## 3. Vì sao các loại tải cạnh tranh trong MySQL/InnoDB?

### 3.1. Buffer pool và I/O lưu trữ

InnoDB dùng buffer pool để lưu các trang dữ liệu và chỉ mục được truy cập thường xuyên trong bộ nhớ. OLTP thường có một tập dữ liệu nóng gồm các hàng và chỉ mục được truy cập lặp lại. Một báo cáo quét phạm vi lớn có thể đưa nhiều trang khác vào buffer pool, làm các trang nóng bị đẩy ra. Khi giao dịch quay lại cần các trang đó, InnoDB phải đọc từ thiết bị lưu trữ và độ trễ tăng lên.

Truy vấn báo cáo cũng có thể đọc tuần tự một lượng dữ liệu lớn, cạnh tranh băng thông I/O với các lần đọc ngẫu nhiên và thao tác ghi của OLTP. Vì vậy, tăng kích thước buffer pool có thể hữu ích nếu máy chủ còn đủ RAM, nhưng không thay thế việc giảm lượng dữ liệu phải quét hoặc tách tải khi mức cạnh tranh đã vượt khả năng máy chủ.

### 3.2. CPU, sắp xếp và bảng tạm

Các phép nối nhiều bảng, nhóm dữ liệu, loại trùng và sắp xếp có thể tiêu tốn CPU đáng kể. Khi kết quả trung gian lớn, MySQL có thể phải dùng bảng tạm; một phần xử lý có thể chuyển xuống đĩa tùy kích thước và cấu hình. Trong lúc đó, các câu lệnh OLTP cũng cần CPU để thực hiện kiểm tra chỉ mục, cập nhật hàng, duy trì ràng buộc và mã hóa/giải mã dữ liệu.

Một truy vấn báo cáo đơn lẻ không nhất thiết gây vấn đề. Nhiều dashboard cùng làm mới, mỗi dashboard chạy nhiều truy vấn tổng hợp, có thể tạo ra đỉnh tải đồng thời. Giới hạn số truy vấn báo cáo chạy cùng lúc và tránh làm mới toàn bộ dashboard quá thường xuyên thường đem lại hiệu quả rõ rệt.

### 3.3. Redo log, ghi đĩa và checkpoint

Mỗi thay đổi dữ liệu của InnoDB được ghi nhận qua cơ chế redo log để hỗ trợ phục hồi. Các giao dịch ghi OLTP cần hoàn tất theo yêu cầu độ bền đã cấu hình. Những đợt ghi hàng loạt, cập nhật nhiều hàng hoặc thao tác nhập dữ liệu lớn có thể làm tăng lượng redo và áp lực ghi, khiến giao dịch nhỏ phải cạnh tranh I/O hoặc chờ điều kiện checkpoint thích hợp.

Khi nạp dữ liệu lớn, nên chia batch có kích thước hợp lý, theo dõi tốc độ ghi và tránh chạy đồng thời với giờ cao điểm nếu không cần thiết. Không nên tùy tiện tắt cơ chế bảo đảm độ bền để làm benchmark nhanh hơn rồi xem kết quả đó là năng lực vận hành thực tế.

### 3.4. MVCC, undo và transaction đọc kéo dài

InnoDB sử dụng MVCC (Multi-Version Concurrency Control) để cung cấp ảnh chụp nhất quán cho các truy vấn đọc thông thường. Một câu `SELECT` nhất quán thường không khóa các hàng mà nó đọc, vì vậy đọc và ghi có thể tiến hành đồng thời ở nhiều trường hợp.

Tuy nhiên, transaction đọc mở quá lâu có thể giữ read view cũ. Khi đó, InnoDB có thể phải giữ lại các phiên bản hàng cũ trong undo log vì vẫn có transaction cần nhìn thấy chúng. Purge không thể dọn các phiên bản đó cho đến khi không còn read view phù hợp. Hệ quả có thể là undo history tăng, tốn không gian và làm công việc dọn dẹp khó theo kịp.

Điểm này cần phân biệt với truy vấn khóa. `SELECT ... FOR UPDATE` và `SELECT ... FOR SHARE` là các locking read, có thể lấy khóa và ảnh hưởng đến giao dịch khác. Một báo cáo `SELECT` thông thường không tự động khóa mọi hàng được đọc, nhưng vẫn có thể gây áp lực tài nguyên và kéo dài read view nếu nằm trong transaction dài.

### 3.5. Khóa và thứ tự truy cập

OLTP có thể bị chậm khi nhiều giao dịch cập nhật cùng một hàng nóng, cùng một phạm vi chỉ mục hoặc lấy khóa theo thứ tự khác nhau. Truy vấn báo cáo chỉ đọc thường không phải nguồn gây khóa hàng trực tiếp, nhưng các báo cáo có locking read, quy trình cập nhật bảng tổng hợp hoặc transaction quản trị có thể tham gia vào cạnh tranh khóa.

Deadlock là một khả năng trong hệ thống đồng thời; InnoDB sẽ chọn một transaction làm nạn nhân để rollback. Ứng dụng cần có chiến lược thử lại có giới hạn cho lỗi deadlock, giữ transaction ngắn và truy cập các hàng theo thứ tự nhất quán khi có thể.

### 3.6. Sao chép và độ trễ dữ liệu

Nếu báo cáo chạy trên replica, truy vấn nặng chủ yếu cạnh tranh tài nguyên với các truy vấn đọc khác trên replica. Tuy nhiên, replica phải nhận và áp dụng thay đổi từ nguồn; khi tốc độ áp dụng không theo kịp, dữ liệu đọc có thể bị trễ. Truy vấn báo cáo dài cũng có thể làm replica thiếu tài nguyên để xử lý các công việc khác.

Replication bất đồng bộ không bảo đảm replica luôn có dữ liệu mới nhất ngay sau khi primary commit. Những luồng nghiệp vụ cần đọc lại dữ liệu vừa ghi, xác nhận thanh toán hoặc hiển thị trạng thái tức thời phải có chiến lược đọc nhất quán, chẳng hạn đọc từ primary trong khoảng thời gian cần thiết hoặc dùng cơ chế chờ replica bắt kịp phù hợp với cấu hình triển khai.

## 4. Thiết kế truy vấn và dữ liệu theo mục đích sử dụng

### 4.1. Giữ đường đi OLTP ngắn và có thể dự đoán

- Dùng khóa chính và chỉ mục phù hợp để tìm đúng hàng; tránh quét bảng khi nghiệp vụ chỉ cần một bản ghi.
- Giữ transaction ngắn. Không giữ transaction mở trong lúc chờ người dùng, gọi dịch vụ bên ngoài hoặc thực hiện công việc không liên quan đến cơ sở dữ liệu.
- Chỉ đọc các cột cần thiết thay vì luôn dùng `SELECT *`, nhất là với bảng có cột lớn.
- Kiểm tra điều kiện cập nhật trong chính câu lệnh SQL khi có thể, như ví dụ trừ tồn kho ở trên.
- Giữ số lượng chỉ mục ở mức có chủ đích. Mỗi chỉ mục phụ làm tăng dung lượng và công việc cần thực hiện khi `INSERT`, `UPDATE` hoặc `DELETE`.
- Khi cập nhật nhiều hàng, cố gắng truy cập theo một thứ tự ổn định để giảm nguy cơ deadlock.

Ví dụ, trang lịch sử đơn hàng của một khách hàng có thể cần lọc theo `customer_id`, giới hạn khoảng thời gian và sắp xếp theo thời điểm tạo:

```sql
SELECT id, status, total_amount, created_at
FROM orders
WHERE customer_id = 120
  AND created_at >= '2026-11-01'
  AND created_at <  '2026-12-01'
ORDER BY created_at DESC
LIMIT 50;
```

Một chỉ mục ghép có thứ tự `(customer_id, created_at)` là ứng viên hợp lý cho mẫu truy vấn này: điều kiện bằng trên khách hàng đứng trước, tiếp theo là phạm vi thời gian. InnoDB có thể duyệt chỉ mục theo chiều ngược để đáp ứng thứ tự giảm dần. Dù vậy, cần xác nhận bằng dữ liệu thật và `EXPLAIN`; chỉ mục phù hợp phụ thuộc vào độ chọn lọc, phân bố dữ liệu và các truy vấn khác.

### 4.2. Giảm chi phí của truy vấn báo cáo

- Lọc theo khoảng trên cột gốc, nhất là cột ngày giờ; tránh áp dụng hàm lên cột trong `WHERE` nếu muốn tận dụng chỉ mục B-tree thông thường.
- Chỉ chọn cột cần dùng. Tránh đọc dữ liệu lớn rồi chuyển toàn bộ sang ứng dụng để tính tổng nếu MySQL có thể tổng hợp hiệu quả.
- Xem xét chỉ mục ghép cho điều kiện lọc và nối. Thứ tự cột phải dựa trên mẫu truy vấn và độ chọn lọc; không có một thứ tự dùng tốt cho mọi báo cáo.
- Giới hạn khoảng thời gian, phân trang hoặc chia báo cáo thành các phần có thể kiểm soát. Với phân trang sâu, cân nhắc phân trang theo khóa (keyset pagination) thay cho `OFFSET` rất lớn.
- Nếu báo cáo được chạy lặp lại và phép tổng hợp tốn kém, cân nhắc bảng tổng hợp được cập nhật theo lịch hoặc theo luồng sự kiện.
- Không giả định `COUNT(*)`, `DISTINCT` hoặc `GROUP BY` luôn rẻ. Hãy đo lượng dữ liệu thực sự phải đọc và xử lý.

MySQL không cung cấp materialized view tự động theo kiểu một số hệ quản trị khác. Nếu dùng bảng tổng hợp, ứng dụng hoặc pipeline ETL/CDC phải chịu trách nhiệm cập nhật, xử lý dữ liệu đến muộn, chạy lại an toàn và đối soát với dữ liệu gốc. Cần xác định rõ báo cáo chấp nhận trễ bao lâu và cách sửa số liệu khi đơn hàng bị hủy hoặc điều chỉnh sau đó.

### 4.3. Tránh tối ưu một truy vấn bằng cách làm chậm mọi giao dịch ghi

Thêm chỉ mục có thể giảm số trang phải đọc cho báo cáo, nhưng mọi thay đổi trên bảng phải duy trì chỉ mục đó. Một bảng OLTP có quá nhiều chỉ mục có thể làm `INSERT` và `UPDATE` chậm hơn, tăng dung lượng và làm buffer pool chứa ít dữ liệu hữu ích hơn.

Vì vậy, hãy đánh giá cả hai phía: truy vấn báo cáo giảm được bao nhiêu chi phí, và luồng ghi phải trả thêm bao nhiêu chi phí để duy trì chỉ mục. Với báo cáo rất nặng nhưng ít quan trọng về độ mới, bảng tổng hợp hoặc replica có thể là lựa chọn tốt hơn việc thêm nhiều chỉ mục vào bảng giao dịch chính.

## 5. Đo tải trước khi quyết định tối ưu

Không nên kết luận máy chủ thiếu CPU, RAM hay IOPS chỉ từ cảm giác ứng dụng chậm. Hãy thu thập số liệu trong khung giờ bình thường và giờ cao điểm, đồng thời phân biệt truy vấn OLTP với truy vấn báo cáo.

### 5.1. Các chỉ số cần theo dõi

| Nhóm | Chỉ số hoặc dấu hiệu | Ý nghĩa cần kiểm tra |
|---|---|---|
| Trải nghiệm | p50, p95, p99 của thời gian phản hồi | Xác định giao dịch đuôi dài, không để trung bình che khuất vấn đề |
| Thông lượng | TPS, QPS, số yêu cầu hoàn tất | Biết hệ thống xử lý được bao nhiêu công việc trong cùng khoảng thời gian |
| Đồng thời | Số kết nối hoạt động, hàng đợi connection pool, thread đang chạy | Phân biệt thiếu kết nối với truy vấn thực sự chậm |
| Khóa | Lock wait, deadlock, transaction mở lâu | Tìm tranh chấp hàng nóng hoặc transaction kéo dài |
| Bộ nhớ và I/O | Buffer pool reads, lượng đọc/ghi đĩa, độ trễ lưu trữ | Phát hiện quét dữ liệu lớn hoặc cạnh tranh I/O |
| Truy vấn | Slow query, digest, số hàng đọc so với số hàng trả về | Tìm truy vấn có chi phí cao hoặc chạy quá thường xuyên |
| InnoDB | Undo history, trạng thái purge, áp lực redo/checkpoint | Phát hiện transaction đọc lâu hoặc tải ghi lớn |
| Replica | Độ trễ áp dụng log và độ mới của dữ liệu | Xác định báo cáo có đang đọc dữ liệu cũ hay không |

Không có một chỉ số đơn lẻ đủ để kết luận. Ví dụ, tỷ lệ buffer pool hit cao không chứng minh mọi truy vấn đều hiệu quả; một truy vấn có thể đọc hàng triệu trang đã nằm sẵn trong RAM và vẫn tiêu tốn CPU đáng kể. Hãy kết hợp thời gian phản hồi, lượng hàng đọc, CPU, I/O và độ đồng thời.

### 5.2. Công cụ quan sát trong MySQL

- **Slow query log:** ghi lại các truy vấn vượt ngưỡng thời gian hoặc tiêu chí cấu hình. Dùng nó để tìm truy vấn chậm, sau đó nhóm theo mẫu truy vấn và tần suất. Không nên bật general query log liên tục trên hệ thống tải cao nếu chưa đánh giá chi phí ghi log.
- **Performance Schema:** cung cấp thống kê theo câu lệnh, sự kiện chờ, khóa và hoạt động của máy chủ. Các view trong `sys` schema giúp đọc một số thống kê thường dùng dễ hơn.
- **`EXPLAIN`:** xem kế hoạch mà bộ tối ưu dự kiến sử dụng, gồm thứ tự nối, chỉ mục, loại truy cập và ước lượng số hàng.
- **`EXPLAIN ANALYZE`:** trên các phiên bản MySQL hỗ trợ, thực thi truy vấn `SELECT` và trả về thời gian cùng số hàng thực tế ở các iterator. Vì câu lệnh được chạy thật, hãy thận trọng với truy vấn rất nặng và chọn môi trường hoặc thời điểm phù hợp.
- **`SHOW ENGINE INNODB STATUS`:** cung cấp thông tin chẩn đoán về transaction, deadlock, I/O và trạng thái InnoDB tại thời điểm xem.

Khi phân tích một truy vấn, so sánh số hàng ước lượng với số hàng thực tế, xem bước nào đọc nhiều dữ liệu, có dùng đúng chỉ mục hay không, và thời gian tập trung ở bước nào. Sau khi thay đổi chỉ mục hoặc SQL, đo lại cùng một mẫu dữ liệu và tải. Tránh chỉ benchmark một truy vấn cô lập rồi suy ra toàn bộ hệ thống sẽ nhanh hơn.

## 6. Chọn nơi chạy báo cáo

Không phải hệ thống nào cũng cần kiến trúc nhiều tầng ngay từ đầu. Quyết định nên dựa trên mức cạnh tranh tài nguyên, yêu cầu độ mới dữ liệu, quy mô báo cáo và chi phí vận hành.

| Phương án | Phù hợp khi | Điểm cần cân nhắc |
|---|---|---|
| Chạy chung trên primary | Dữ liệu và báo cáo còn nhỏ, truy vấn đã tối ưu, giờ chạy không gây ảnh hưởng đáng kể | Báo cáo nặng có thể làm tăng độ trễ giao dịch; cần giới hạn tần suất và thời gian chạy |
| Chuyển báo cáo sang read replica | Báo cáo chủ yếu đọc, có thể chấp nhận độ trễ sao chép và cần tách CPU/I/O đọc khỏi primary | Replica có thể đọc dữ liệu cũ; phải theo dõi lag, tài nguyên và khả năng áp dụng log |
| Bảng tổng hợp hoặc pipeline ETL/CDC | Nhiều báo cáo lặp lại, phép tổng hợp tốn kém, có thể xác định SLA về độ mới | Cần quy trình đồng bộ, xử lý cập nhật/xóa, chạy lại và đối soát |
| Kho dữ liệu phân tích riêng | Phân tích lịch sử lớn, nhiều chiều, quét và tổng hợp trên khối lượng dữ liệu cao | Phát sinh thêm hệ thống, pipeline, chi phí và độ trễ đồng bộ |

### 6.1. Chạy chung trên primary

Đây là lựa chọn đơn giản và có thể hợp lý nếu truy vấn báo cáo nhẹ, số người dùng ít và số liệu phải mới ngay. Dù chạy chung, nên dùng tài khoản chỉ đọc cho luồng báo cáo, giới hạn truy vấn và tránh cho dashboard tự do chạy truy vấn tùy ý trên bảng lớn.

Theo dõi p95/p99 của các giao dịch nghiệp vụ khi báo cáo bắt đầu chạy. Nếu độ trễ tăng cùng thời điểm với truy vấn tổng hợp, cần xem xét giảm tần suất, thu hẹp phạm vi, tổng hợp trước hoặc chuyển tải.

### 6.2. Dùng read replica

Read replica tạo một nơi đọc riêng để giảm cạnh tranh trực tiếp với truy vấn OLTP trên primary. Tài khoản báo cáo trên replica nên chỉ có quyền `SELECT` đối với schema và bảng cần thiết. Ứng dụng cần phân loại rõ truy vấn nào được phép đọc từ replica.

Vì sao phải quan tâm replication lag? Giả sử khách hàng vừa thanh toán thành công và ngay sau đó mở trang lịch sử đơn hàng. Nếu truy vấn được gửi đến replica chưa áp dụng giao dịch thanh toán, giao diện có thể hiển thị trạng thái cũ. Có thể định tuyến các lần đọc cần tính nhất quán về primary, hoặc dùng cơ chế chờ đồng bộ phù hợp với topology. Không nên giả định mọi replica đều đọc ngay được dữ liệu vừa commit.

Replica cũng cần được giám sát. Một báo cáo quét toàn bộ dữ liệu có thể làm chậm các truy vấn khác trên replica hoặc khiến quá trình áp dụng thay đổi không theo kịp. Tách máy chủ giúp cô lập một phần tài nguyên, nhưng không loại bỏ nhu cầu tối ưu truy vấn.

### 6.3. Dùng bảng tổng hợp hoặc kho dữ liệu

Với dashboard truy vấn cùng một phép tổng hợp liên tục, có thể tạo bảng tổng hợp theo ngày, sản phẩm hoặc khu vực. Ví dụ, thay vì mỗi lần mở dashboard đều nhóm hàng triệu đơn, pipeline có thể cập nhật tổng doanh thu theo ngày và dashboard chỉ đọc các dòng đã tổng hợp.

Thiết kế này cần trả lời các câu hỏi: dữ liệu cập nhật theo sự kiện hay theo lịch; độ trễ cho phép là bao lâu; đơn hàng bị hủy hoặc hoàn tiền được điều chỉnh ra sao; pipeline chạy lại có tạo số liệu trùng không; và làm thế nào đối soát tổng hợp với bảng giao dịch. Nếu không giải quyết các câu hỏi này, dashboard có thể nhanh nhưng số liệu sai.

Khi nhu cầu phân tích cần quét lịch sử rất lớn, nhiều chiều hoặc nhiều phép tổng hợp phức tạp, hãy cân nhắc kho dữ liệu chuyên cho phân tích. MySQL vẫn có thể là nguồn giao dịch, còn dữ liệu được chuyển qua ETL hoặc CDC sang hệ thống phù hợp hơn với truy vấn phân tích.

## 7. Quy trình xử lý khi OLTP chậm trong lúc báo cáo chạy

Giả sử thời gian tạo đơn tăng từ 80 ms lên 900 ms mỗi khi dashboard doanh thu mở. Có thể xử lý theo trình tự sau:

1. **Xác định tương quan thời gian:** đối chiếu p95/p99 của API đặt hàng với thời điểm báo cáo chạy; kiểm tra số lượng báo cáo đồng thời và lịch làm mới dashboard.
2. **Tìm truy vấn gây tải:** dùng slow query log và thống kê digest trong Performance Schema để xác định mẫu SQL, tần suất, thời gian và số hàng đọc.
3. **Kiểm tra kế hoạch thực thi:** dùng `EXPLAIN`, và khi phù hợp dùng `EXPLAIN ANALYZE`, để tìm quét bảng, nối tốn kém, sort hoặc bảng tạm.
4. **Giảm công việc phải làm:** thu hẹp khoảng thời gian, sửa điều kiện lọc, chọn ít cột hơn, thêm chỉ mục có căn cứ hoặc tạo bảng tổng hợp.
5. **Giới hạn cạnh tranh:** giảm tần suất refresh, giới hạn số báo cáo chạy đồng thời, đặt timeout phù hợp và tách tài khoản/kết nối cho luồng báo cáo.
6. **Đánh giá tách tải:** chuyển báo cáo sang replica hoặc kho dữ liệu nếu sau tối ưu vẫn ảnh hưởng đến SLA OLTP và yêu cầu độ mới dữ liệu cho phép.
7. **Đo lại trên tải gần thực tế:** xác nhận giao dịch nghiệp vụ phục hồi, báo cáo vẫn trả đúng số liệu và replica không phát sinh độ trễ vượt ngưỡng.

Đừng vội tăng số kết nối để xử lý tình trạng chậm. Nếu nguyên nhân là CPU hoặc I/O đã bão hòa, tăng kết nối có thể làm nhiều truy vấn tranh tài nguyên cùng lúc và khiến thời gian chờ dài hơn. Cần tìm nguyên nhân ở truy vấn, khóa, tài nguyên hoặc giới hạn connection pool trước khi điều chỉnh.

## 8. Những cách hiểu sai thường gặp

- **“Đọc không ảnh hưởng ghi.”** Đọc nhất quán thông thường có thể không khóa hàng, nhưng vẫn dùng CPU, buffer pool và I/O; transaction đọc dài còn có thể giữ read view và làm chậm purge.
- **“Tách replica là báo cáo sẽ luôn mới.”** Replication bất đồng bộ có độ trễ; cần xác định truy vấn nào chấp nhận dữ liệu trễ và truy vấn nào phải đọc từ primary.
- **“Thêm chỉ mục luôn làm truy vấn nhanh hơn.”** Chỉ mục có chi phí lưu trữ và bảo trì khi ghi. Chỉ thêm sau khi xác định mẫu truy vấn và kiểm chứng bằng kế hoạch thực thi.
- **“QPS cao nghĩa là tải nặng.”** Một lượng lớn tra cứu theo khóa chính có thể rẻ hơn một vài truy vấn quét và tổng hợp hàng triệu hàng. Cần xem chi phí mỗi truy vấn.
- **“Tăng RAM giải quyết mọi vấn đề.”** RAM giúp cache dữ liệu, nhưng không loại bỏ phép nối tốn CPU, sort lớn, transaction kéo dài, khóa nóng hoặc truy vấn phải đọc quá nhiều hàng.
- **“Dùng partition là tự động tăng tốc.”** Partition có ích khi thiết kế phù hợp với cách lọc và bảo trì dữ liệu; nó không tự thay thế chỉ mục hoặc sửa một kế hoạch truy vấn kém.

## 9. Checklist đánh giá tải của một hệ thống MySQL

Khi thiết kế hoặc điều tra hiệu năng, hãy trả lời được các câu hỏi sau:

- Giao dịch nghiệp vụ quan trọng nhất là gì, cần độ trễ p95/p99 và thông lượng bao nhiêu?
- Những bảng và hàng nào được đọc/ghi thường xuyên? Có hàng nóng hoặc khóa tranh chấp không?
- Báo cáo nào quét nhiều dữ liệu, chạy bao lâu, chạy bao nhiêu lần và có thể chấp nhận dữ liệu trễ bao lâu?
- Truy vấn có dùng chỉ mục đúng với điều kiện lọc, phép nối và thứ tự sắp xếp không?
- Có transaction đọc hoặc ghi nào mở quá lâu không? Undo history và lock wait có tăng trong giờ báo cáo không?
- CPU, buffer pool, I/O, redo và connection pool đang chịu áp lực ở đâu?
- Báo cáo nên chạy trên primary, replica, bảng tổng hợp hay kho dữ liệu riêng?
- Sau khi tách tải, ứng dụng xử lý read-after-write và dữ liệu replica trễ như thế nào?
- Có số liệu trước/sau để xác nhận thay đổi cải thiện cả hiệu năng lẫn tính đúng đắn không?

## Kết luận

OLTP ưu tiên giao dịch ngắn, chính xác và phản hồi ổn định; báo cáo ưu tiên khả năng đọc, kết hợp và tổng hợp lượng dữ liệu lớn; tải hỗn hợp phải đáp ứng cả hai trong cùng môi trường tài nguyên. Với MySQL/InnoDB, khác biệt này thể hiện qua cách sử dụng buffer pool, CPU, I/O, redo/undo, MVCC và khóa. Hãy đo hành vi truy vấn trong tải thực tế, tối ưu đường truy cập dữ liệu, giới hạn truy vấn nặng và chọn primary, replica hoặc pipeline phân tích theo yêu cầu độ trễ và độ mới dữ liệu của nghiệp vụ.
