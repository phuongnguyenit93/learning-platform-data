# Đánh giá phân trang bằng dữ liệu lớn và phân bố tham số thực tế

Phân trang thường bắt đầu đơn giản: sắp xếp dữ liệu, bỏ qua một số dòng rồi lấy một trang có kích thước cố định. Cách này hoạt động tốt khi bảng còn nhỏ và người dùng chỉ xem những trang đầu. Khi dữ liệu tăng lên hàng chục hoặc hàng trăm triệu dòng, trang ở vị trí sâu có thể chậm hơn nhiều. Cùng một câu SQL cũng có thể có hiệu năng rất khác giữa tenant nhỏ và tenant lớn, giữa trạng thái hiếm và trạng thái phổ biến, hoặc giữa khoảng thời gian ngắn và khoảng thời gian dài.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Đánh giá phân trang vì vậy phải xem cả chiến lược lấy trang, thứ tự sắp xếp, chỉ mục, độ chọn lọc của tham số, số dòng thực tế phải đọc và hành vi của dữ liệu khi có giao dịch đồng thời.

Bài học này trình bày cách so sánh offset pagination và keyset pagination, thiết kế chỉ mục theo bộ lọc và thứ tự, kiểm tra các nhóm tham số có phân bố khác nhau, xử lý tổng số kết quả và phép nối, rồi xây dựng phép đo có thể lặp lại trên dữ liệu lớn.

## 1. Phân trang là một mẫu truy cập dữ liệu

Một truy vấn phân trang thường có ba phần:

1. **Bộ lọc:** xác định tập dữ liệu người dùng được phép xem, chẳng hạn tenant, trạng thái, loại bản ghi hoặc khoảng thời gian.
2. **Thứ tự:** xác định thứ tự ổn định của các dòng, thường dựa trên thời gian tạo, điểm xếp hạng hoặc tên.
3. **Giới hạn trang:** chọn một đoạn kết quả có kích thước cố định.

Ví dụ danh sách đơn hàng:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size OFFSET :offset;
~~~

Trong ví dụ này:

- tenant_id và status xác định tập dòng cần xét.
- created_at DESC xác định thứ tự chính.
- order_id DESC là khóa phụ để phân biệt các dòng có cùng created_at.
- page_size giới hạn số dòng trả về.
- offset xác định số dòng đầu tiên cần bỏ qua.

Khi đánh giá hiệu năng, cần tách thời gian xử lý của bộ lọc, sắp xếp và lấy trang. Một trang có thể trả về 50 dòng nhưng cơ sở dữ liệu phải đọc, sắp xếp hoặc bỏ qua hàng triệu dòng trước khi tạo được kết quả.

### Vì sao cần thứ tự xác định?

Nếu ORDER BY không tạo ra thứ tự duy nhất, nhiều dòng có cùng giá trị sắp xếp có thể đổi vị trí giữa các lần thực thi. Ví dụ ORDER BY created_at DESC không phân biệt được hai đơn hàng tạo cùng thời điểm.

Hãy thêm một khóa duy nhất làm tie-breaker:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Thứ tự ổn định giúp ranh giới trang rõ ràng, tránh dòng đổi chỗ chỉ vì hệ quản trị chọn một thứ tự nội bộ khác. Nó đặc biệt quan trọng với keyset pagination.

## 2. Offset pagination hoạt động như thế nào?

Offset pagination dùng LIMIT và OFFSET hoặc cú pháp tương đương của hệ quản trị. Ứng dụng tính offset theo số trang:

```text
offset = (page_number - 1) * page_size
```

Ví dụ page_size = 50:

| Trang | OFFSET | Dòng cần trả về |
|---:|---:|---|
| 1 | 0 | 1–50 |
| 2 | 50 | 51–100 |
| 10 | 450 | 451–500 |
| 1.000 | 49.950 | 49.951–50.000 |
| 20.000 | 999.950 | 999.951–1.000.000 |

Câu truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 999950;
~~~

Cơ sở dữ liệu phải xác định các dòng theo thứ tự và bỏ qua gần một triệu dòng trước khi trả về 50 dòng cuối. Nếu có index phù hợp, nó có thể tránh sắp xếp toàn bộ tập dữ liệu, nhưng vẫn phải đi qua phần lớn các entry trước offset. Nếu không có index phù hợp, hệ quản trị còn có thể phải lọc và sắp xếp một tập dữ liệu lớn.

### Chi phí tăng theo độ sâu trang

Với page_size cố định, công việc của offset pagination thường tăng theo offset. Trang đầu có thể chỉ cần đọc một đoạn nhỏ; trang sâu cần đi qua nhiều dòng hơn để bỏ qua kết quả trước đó.

Đây là lý do truy vấn có thể có latency thấp ở trang 1 nhưng rất cao ở trang 10.000, dù cả hai đều trả về 50 dòng.

Tác động thực tế còn phụ thuộc:

- Bộ lọc có chọn lọc hay không.
- Chỉ mục có phục vụ thứ tự không.
- Dữ liệu có nằm trong cache hay phải đọc từ lưu trữ.
- Số dòng phải kiểm tra sau index scan.
- Có bước Sort hoặc spill hay không.
- Kế hoạch thực thi và phiên bản hệ quản trị.

Không phải mọi OFFSET đều chậm. Offset nhỏ trên một tập kết quả vừa phải có thể là lựa chọn đơn giản và phù hợp.

### Ưu điểm và giới hạn

Offset pagination có một số ưu điểm:

- Người dùng có thể nhảy trực tiếp đến số trang bất kỳ.
- Giao diện dễ hiển thị số trang và tổng số trang.
- Câu SQL đơn giản và được nhiều hệ quản trị hỗ trợ.
- Phù hợp với danh sách nhỏ hoặc trang đầu/trang gần đầu.

Các giới hạn cần đánh giá:

- Chi phí có thể tăng mạnh ở trang sâu.
- Thêm hoặc xóa dòng giữa các lần tải trang có thể làm dịch chuyển ranh giới.
- Tổng số dòng phải đếm để hiển thị tổng trang có thể tạo thêm truy vấn đắt.
- Một kế hoạch phù hợp với tham số nhỏ có thể không phù hợp với tham số trả về tập dữ liệu lớn.

## 3. Keyset pagination (seek pagination)

Keyset pagination lấy trang tiếp theo dựa trên giá trị của dòng cuối cùng ở trang hiện tại. Thay vì yêu cầu bỏ qua một số lượng dòng, truy vấn yêu cầu tìm các dòng đứng sau hoặc trước một khóa mốc.

Giả sử thứ tự là:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Trang đầu:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Ứng dụng lưu lại cặp khóa của dòng cuối cùng, gồm last_created_at và last_order_id. Trang tiếp theo:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND order_id < :last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

Điều kiện tiếp tục tìm các dòng đứng sau mốc trong thứ tự giảm dần. Nếu có index phù hợp, hệ quản trị có thể seek đến vị trí khóa mốc rồi đọc tiếp page_size dòng, thay vì đi qua tất cả kết quả của các trang trước.

Một số hệ quản trị hỗ trợ so sánh tuple/row constructor, ví dụ:

~~~sql
AND (created_at, order_id) < (:last_created_at, :last_order_id)
~~~

Cú pháp và khả năng tối ưu tuple comparison phụ thuộc hệ quản trị và phiên bản. Biểu thức OR tường minh ở trên thể hiện quy tắc so sánh từ điển và có thể dùng làm cách viết dễ kiểm tra hơn.

### Keyset cần một thứ tự duy nhất

Nếu chỉ dùng created_at làm cursor mà nhiều dòng có cùng timestamp, trang tiếp theo có thể bỏ sót hoặc lặp lại dòng. Khóa phụ phải tạo ra thứ tự tổng thể duy nhất, thường là primary key:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Cursor phải chứa tất cả các giá trị sắp xếp cần thiết, không chỉ một cột.

### Điều kiện cho chiều tăng dần

Nếu thứ tự là:

~~~sql
ORDER BY created_at ASC, order_id ASC
~~~

thì trang tiếp theo dùng điều kiện lớn hơn mốc:

~~~sql
AND (
     created_at > :last_created_at
     OR (
         created_at = :last_created_at
         AND order_id > :last_order_id
     )
)
ORDER BY created_at ASC, order_id ASC
LIMIT 50;
~~~

Dấu so sánh phải phù hợp với chiều sắp xếp của từng cột. Với thứ tự hỗn hợp, ví dụ created_at DESC nhưng order_id ASC, cần viết điều kiện từ điển tương ứng cho từng nhánh; không thể áp dụng một dấu so sánh chung cho toàn bộ tuple.

### Keyset có thể nhảy đến trang bất kỳ không?

Keyset pagination phù hợp với thao tác tiếp tục từ cursor trước đó. Nó không tự nhiên hỗ trợ “đến trang 10.000” nếu không có mốc khóa của trang đó. Nếu nghiệp vụ bắt buộc nhảy trực tiếp đến số trang, có thể cần offset, bảng đánh dấu mốc, bộ chỉ mục phân trang riêng hoặc một thiết kế tìm kiếm khác.

## 4. So sánh Offset và Keyset

| Tiêu chí | Offset pagination | Keyset pagination |
|---|---|---|
| Cách xác định trang | Số dòng cần bỏ qua | Giá trị khóa của dòng mốc |
| Trang đầu | Thường đơn giản | Thường đơn giản |
| Trang sâu | Có thể phải đi qua nhiều dòng trước offset | Có thể seek từ cursor nếu có index phù hợp |
| Nhảy đến số trang | Hỗ trợ trực tiếp | Không thuận tiện nếu chưa có cursor của trang đích |
| Độ ổn định khi có insert/delete | Ranh giới trang dễ dịch chuyển | Ít bị dịch chuyển do dòng mới ở phía trước cursor |
| Điều kiện thứ tự | Cần ORDER BY ổn định | Cần ORDER BY duy nhất và cursor chứa đủ khóa |
| Phù hợp | Danh sách nhỏ, trang đánh số, báo cáo | Feed, lịch sử, danh sách lớn duyệt liên tục |
| Yêu cầu index | Index hỗ trợ filter/order giúp giảm scan/sort | Cần index phù hợp với filter và khóa cursor để seek hiệu quả |

Keyset không làm mọi truy vấn nhanh một cách tự động. Nếu bộ lọc không chọn lọc, index không phù hợp hoặc khóa sắp xếp không có tương quan với đường truy cập, truy vấn vẫn có thể phải đọc nhiều dữ liệu.

## 5. Thiết kế chỉ mục cho phân trang

Một index tốt cho phân trang thường phải phục vụ cả điều kiện lọc và thứ tự sắp xếp.

Với truy vấn:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT :page_size;
~~~

một index B-tree có thể được cân nhắc:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Các cột tenant_id và status được lọc bằng phép bằng; created_at và order_id xác định thứ tự trang. Index này có thể hỗ trợ cả trang đầu lẫn keyset continuation nếu kế hoạch và hệ quản trị tận dụng được thứ tự.

### Equality filter và sort key

Một nguyên tắc thường hữu ích là đặt các cột được cố định bằng điều kiện equality trước các cột sắp xếp. Khi tenant_id và status đã được cố định, phần index tiếp theo có thể cung cấp thứ tự created_at, order_id trong phạm vi đó.

Tuy nhiên, đây không phải công thức áp dụng máy móc. Cần xét:

- Truy vấn có lọc theo khoảng trên cột nào?
- Có nhiều tổ hợp filter khác nhau không?
- Các cột có phân bố lệch không?
- Index có phục vụ những truy vấn khác không?
- Có cần hỗ trợ sort direction hỗn hợp không?
- Chi phí index rộng ảnh hưởng thế nào đến ghi và cache?

### Range filter và thứ tự

Giả sử truy vấn lọc tenant, trạng thái và một khoảng thời gian:

~~~sql
WHERE tenant_id = :tenant_id
  AND status = :status
  AND created_at >= :from_time
  AND created_at < :to_time
ORDER BY created_at DESC, order_id DESC
~~~

Index (tenant_id, status, created_at DESC, order_id DESC) có thể phục vụ phạm vi thời gian trong tenant/status và thứ tự mong muốn. Nếu range filter nằm trên một cột khác trước sort key, nó có thể làm giảm khả năng cung cấp thứ tự toàn cục theo sort key. Hãy đọc plan để xác định có phải Sort hay không.

### Covering index

Nếu truy vấn chỉ trả một vài cột, có thể cân nhắc lưu thêm cột cần đọc trong index. PostgreSQL hỗ trợ INCLUDE:

~~~sql
CREATE INDEX idx_orders_page_cover
ON orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
)
INCLUDE (total_amount);
~~~

Cột INCLUDE được lưu để có thể phục vụ index-only scan khi điều kiện visibility cho phép; nó không tham gia thứ tự khóa. Các hệ quản trị khác có cách tạo covering index riêng.

Không nên đưa mọi cột của bản ghi vào index. Index quá rộng làm tăng dung lượng, giảm mật độ trang, chiếm cache và làm INSERT/UPDATE/DELETE tốn kém hơn.

### Không tạo index trùng lặp

Trước khi thêm index, kiểm tra các index hiện có và tiền tố của chúng. Một index ghép có thể đã hỗ trợ truy vấn theo các cột đầu. Nhưng index có thứ tự cột khác không nhất thiết thay thế được index hiện có. Hãy đánh giá bằng workload và plan, không chỉ so sánh tên cột.

## 6. Phân bố tham số thực tế làm thay đổi chi phí phân trang

Cùng một câu SQL có thể có số dòng phù hợp rất khác theo tham số. Với dữ liệu lớn, cần phân nhóm các tham số thay vì chỉ đo một giá trị đại diện.

### Tenant nhỏ và tenant lớn

Giả sử bảng orders có 100 triệu dòng:

- Tenant A có 500 đơn.
- Tenant B có 20 triệu đơn.
- Hàng nghìn tenant nhỏ chia nhau phần dữ liệu còn lại.

Truy vấn theo tenant A có thể chỉ đọc vài trang. Truy vấn theo tenant B có thể trả về hàng triệu dòng nếu không có bộ lọc khác. Cùng một index và cùng câu SQL có thể có chi phí rất khác.

Đối với offset pagination, tenant lớn làm các trang sâu có thể phải bỏ qua nhiều dòng hơn. Đối với keyset, seek từ cursor có thể giảm công việc lặp lại nhưng mỗi trang vẫn cần đọc dữ liệu phù hợp với filter.

### Trạng thái hiếm và trạng thái phổ biến

Ví dụ status = 'CANCELLED' chỉ chiếm 1% nhưng status = 'PAID' chiếm 80%. Truy vấn theo CANCELLED có thể chọn lọc cao, còn PAID có thể cần đọc phần lớn tập dữ liệu tenant.

Một index access path tốt cho trạng thái hiếm có thể không phải lựa chọn rẻ nhất cho trạng thái phổ biến. Optimizer có thể chọn index scan cho một nhóm và scan khác cho nhóm còn lại.

### Khoảng thời gian ngắn và dài

Khoảng thời gian một giờ có thể trả về vài trăm dòng; khoảng thời gian một năm có thể trả về hàng triệu dòng. Một truy vấn keyset theo thời gian có thể hiệu quả khi cursor nằm trong vùng dữ liệu phù hợp, nhưng filter khoảng thời gian rộng vẫn có thể dẫn đến lượng đọc lớn.

### Tham số NULL, rỗng và tùy chọn

Ứng dụng thường có filter tùy chọn, ví dụ status có thể NULL để lấy mọi trạng thái. Một câu SQL dạng:

~~~sql
WHERE tenant_id = :tenant_id
  AND (:status IS NULL OR status = :status)
~~~

có thể khiến optimizer khó ước lượng hoặc khó sử dụng index tối ưu trong một số hệ quản trị. Nếu hai chế độ “lọc một status” và “không lọc status” có đặc điểm rất khác nhau, hãy cân nhắc hai mẫu SQL rõ ràng hoặc cơ chế parameter-sensitive plan phù hợp với engine. Chỉ thay đổi sau khi đo plan cho từng nhóm tham số.

### Nhóm tham số nên kiểm tra

| Nhóm tham số | Ví dụ | Điều cần đo |
|---|---|---|
| Tenant | Nhỏ, trung bình, rất lớn | Rows scanned, rows returned, latency |
| Trạng thái | Hiếm, phổ biến, không có kết quả | Selectivity, index/scan choice |
| Thời gian | Một giờ, một ngày, một tháng, một năm | Range size, buffers, sort/spill |
| Từ khóa | Prefix chọn lọc, prefix phổ biến, không khớp | Search access path, rows examined |
| Cursor | Trang đầu, cursor gần đầu, cursor rất sâu | Số dòng phải đọc trước page |
| Kích thước trang | 20, 50, 100, 500 | Throughput, memory, response size |
| Tải đồng thời | Thấp, bình thường, đỉnh | p95/p99, CPU, I/O, queue |

Mục tiêu là xác định các nhóm có hành vi khác nhau. Không cần lưu toàn bộ giá trị tham số thô trong telemetry; có thể phân nhóm hoặc chuẩn hóa để giảm dung lượng và hạn chế ghi nhận dữ liệu nhạy cảm.

## 7. Parameter-sensitive plans và kế hoạch phân trang

Một số hệ quản trị có thể tái sử dụng kế hoạch cho câu SQL đã chuẩn bị. Nếu tham số lần đầu có độ chọn lọc rất khác các lần sau, kế hoạch được chọn có thể không phù hợp với mọi nhóm.

Ví dụ:

- Lần đầu tenant nhỏ, optimizer chọn index seek và nested loop.
- Sau đó tenant lớn, cùng kế hoạch phải lặp nhiều lần hoặc đọc lượng dữ liệu lớn.
- Hoặc kế hoạch scan được chọn cho tenant lớn lại tốn kém với tenant nhỏ.

Hiện tượng và cơ chế xử lý phụ thuộc hệ quản trị, phiên bản và cách chuẩn bị câu lệnh. Một số engine có cơ chế parameter sniffing, adaptive plan hoặc parameter-sensitive plan; không nên mặc định mọi hệ thống xử lý giống nhau.

### Cách kiểm tra

1. Chọn các nhóm tham số đại diện: tenant nhỏ/lớn, status hiếm/phổ biến, khoảng ngày ngắn/dài.
2. Thu thập plan và số liệu thực tế cho từng nhóm.
3. So sánh estimated rows với actual rows.
4. Kiểm tra index scan, table scan, sort, loops và số dòng bị loại.
5. Xem kế hoạch có được tái sử dụng hay có nhiều biến thể.
6. Đánh giá p50, p95, p99 theo từng nhóm thay vì chỉ xem trung bình toàn bộ.

Không dùng một lần chạy với một tham số để kết luận rằng index hoặc keyset luôn nhanh. Một thay đổi có thể cải thiện nhóm này và làm nhóm khác kém đi.

## 8. Phân trang trên dữ liệu có thay đổi đồng thời

Khi người dùng chuyển trang, dữ liệu có thể được thêm, xóa hoặc cập nhật giữa hai request. Điều này ảnh hưởng nội dung trang kế tiếp.

### Offset có thể bị dịch chuyển

Giả sử trang 1 hiển thị các dòng 1–50. Trước khi người dùng lấy trang 2, có 5 dòng mới được thêm vào đầu danh sách. Với OFFSET 50, hệ quản trị bỏ qua 50 dòng đầu của trạng thái mới. Một số dòng đã thấy ở trang 1 có thể xuất hiện lại ở trang 2.

Nếu dòng bị xóa ở phía trước offset, một số dòng có thể bị bỏ qua. Đây là hệ quả của việc mỗi request đánh giá offset trên tập dữ liệu tại thời điểm riêng.

### Keyset giảm dịch chuyển do dòng mới ở phía trước cursor

Keyset tiếp tục từ khóa của dòng cuối cùng đã xem. Nếu có dòng mới được thêm trước cursor trong thứ tự, điều kiện tiếp tục vẫn bắt đầu sau mốc cũ nên dòng mới đó không đẩy các dòng đã có qua ranh giới trang.

Tuy nhiên, keyset không tự bảo đảm snapshot cố định:

- Dòng có sort key được cập nhật có thể di chuyển qua cursor.
- Dòng bị xóa trước khi lấy trang kế tiếp sẽ không còn xuất hiện.
- Dòng mới được thêm sau cursor có thể xuất hiện ở trang sau.
- Thay đổi filter có thể làm tập dữ liệu khác đi.

Nếu nghiệp vụ cần duyệt một tập kết quả nhất quán như ảnh chụp tại một thời điểm, cần xem xét transaction isolation/snapshot phù hợp hoặc tạo một mốc dữ liệu cố định. Giữ một transaction snapshot mở qua nhiều request web có thể gây áp lực tài nguyên và không phải thiết kế phù hợp trong mọi hệ thống.

### Khóa sắp xếp nên ổn định

Keyset hoạt động tốt nhất khi các cột cursor ít hoặc không thay đổi sau khi bản ghi được tạo. Các khóa như created_at và primary key thường ổn định hơn status hoặc priority có thể cập nhật.

Nếu thứ tự dựa trên cột thường xuyên thay đổi, một dòng có thể di chuyển từ phía sau cursor lên phía trước hoặc ngược lại. Cần xác định hành vi nghiệp vụ mong muốn và có thể dùng snapshot hoặc khóa sắp xếp bất biến.

## 9. Cursor cần lưu những gì?

Một cursor cho keyset pagination thường chứa:

- Giá trị của tất cả cột trong ORDER BY tại dòng cuối trang.
- Hướng sắp xếp.
- Phiên bản định dạng cursor.
- Có thể chứa dấu hiệu filter/sort mode để xác định truy vấn tiếp theo.

Ví dụ cursor logic:

~~~json
{
  "version": 1,
  "sort": "created_at_desc_order_id_desc",
  "last_created_at": "2026-04-18T09:30:00Z",
  "last_order_id": 845120
}
~~~

Đây là cấu trúc minh họa. Trong ứng dụng thực tế, cursor có thể được mã hóa thành chuỗi opaque. Nếu cursor được client gửi lại, cần xác thực nội dung hoặc ký số để người dùng không thể tùy ý sửa mốc và chế độ truy vấn. Không đưa thông tin nhạy cảm vào cursor nếu không có bảo vệ phù hợp.

Cursor phải được gắn với ngữ cảnh truy vấn. Nếu người dùng thay tenant, filter hoặc sort order, cursor cũ có thể không còn hợp lệ. Backend cần xác minh quyền truy cập và filter ở mỗi request; không dựa vào cursor để cấp quyền.

## 10. NULL và thứ tự hỗn hợp trong keyset

Các cột sort có thể cho phép NULL. Hành vi NULLS FIRST/LAST và so sánh NULL khác nhau giữa hệ quản trị. Điều kiện so sánh thông thường với NULL cho kết quả UNKNOWN, vì vậy biểu thức cursor đơn giản có thể bỏ sót dòng.

Các cách xử lý:

- Ưu tiên dùng cột sắp xếp NOT NULL nếu mô hình dữ liệu cho phép.
- Xác định rõ NULLS FIRST hoặc NULLS LAST.
- Chia điều kiện tiếp tục thành các nhánh xử lý NULL và non-NULL.
- Dùng biểu thức chuẩn hóa như COALESCE chỉ khi có sentinel an toàn, không thể trùng giá trị hợp lệ, và có index hỗ trợ biểu thức nếu cần.

Với thứ tự hỗn hợp, ví dụ:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id ASC
~~~

điều kiện keyset phải so sánh theo thứ tự từ điển với chiều riêng cho từng cột:

~~~sql
WHERE priority < :last_priority
   OR (
       priority = :last_priority
       AND created_at > :last_created_at
   )
   OR (
       priority = :last_priority
       AND created_at = :last_created_at
       AND order_id > :last_order_id
   )
~~~

Biểu thức này giả định các cột không NULL và thứ tự tương ứng đúng như ORDER BY. Nếu có NULL, cần mở rộng điều kiện theo quy tắc null ordering đã chọn.

## 11. Phân trang kết hợp tìm kiếm

Danh sách thường có ô tìm kiếm theo mã, tên hoặc nội dung. Điều kiện tìm kiếm ảnh hưởng mạnh đến độ chọn lọc và index access path.

### Tìm theo tiền tố

Điều kiện:

~~~sql
WHERE customer_name LIKE 'An%'
~~~

có thể tận dụng B-tree index trong một số collation và hệ quản trị nếu biểu thức phù hợp. Khả năng sử dụng index phụ thuộc collation, kiểu dữ liệu và cấu hình.

### Tìm chuỗi con

Điều kiện:

~~~sql
WHERE customer_name LIKE '%anh%'
~~~

thường không thể dùng B-tree thông thường để tìm một range theo tiền tố vì ký tự wildcard đứng đầu. Có thể cần full-text index, trigram index hoặc cơ chế tìm kiếm riêng tùy hệ quản trị.

### Tìm kiếm full-text

Nếu tìm kiếm theo nội dung văn bản, full-text index có thể giúp truy vấn theo token và relevance score. Khi phân trang theo điểm relevance, cần có tie-breaker duy nhất:

~~~sql
ORDER BY relevance_score DESC, document_id DESC
~~~

Cursor phải chứa cả relevance_score và document_id. Điểm relevance có thể thay đổi khi nội dung hoặc index thay đổi, nên cần xem xét snapshot hoặc giới hạn thời gian của cursor.

### Tìm kiếm kết hợp filter và sort

Ví dụ tìm đơn theo tenant, từ khóa mã đơn và thời gian:

~~~sql
WHERE tenant_id = :tenant_id
  AND order_code LIKE :prefix
ORDER BY created_at DESC, order_id DESC
~~~

Không phải lúc nào một index cũng phục vụ tốt cả prefix search lẫn sort. Cần xem số dòng tìm thấy, thứ tự truy cập và kế hoạch. Với truy vấn phức tạp, hệ thống tìm kiếm chuyên dụng có thể phù hợp hơn, nhưng cần cân nhắc đồng bộ dữ liệu và độ trễ nhất quán.

## 12. Phân trang khi có JOIN

Một truy vấn phân trang có thể nối bảng cha với bảng con:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    i.item_id,
    i.product_id
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.tenant_id = :tenant_id
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT 50;
~~~

Ở đây LIMIT 50 áp dụng trên dòng kết quả sau JOIN. Một đơn có nhiều order_items có thể chiếm nhiều dòng trong trang. Vì vậy, truy vấn có thể trả ít hơn 50 đơn hàng duy nhất và ranh giới phân trang không còn là ranh giới của orders.

Nếu mục tiêu là phân trang đơn hàng, hãy xác định trang ở cấp orders trước, sau đó lấy dữ liệu con cho các đơn đã chọn:

~~~sql
WITH page_orders AS (
    SELECT order_id, created_at
    FROM orders
    WHERE tenant_id = :tenant_id
    ORDER BY created_at DESC, order_id DESC
    LIMIT 50
)
SELECT
    p.order_id,
    p.created_at,
    i.item_id,
    i.product_id
FROM page_orders AS p
LEFT JOIN order_items AS i
    ON i.order_id = p.order_id
ORDER BY p.created_at DESC, p.order_id DESC, i.item_id;
~~~

Cách này bảo đảm chọn 50 đơn trước khi mở rộng thành các dòng chi tiết. Tuy nhiên, kết quả cuối có thể có hơn 50 dòng vì mỗi đơn có nhiều item. Nếu ứng dụng cần một object đơn hàng chứa danh sách item, tầng ứng dụng có thể gom các dòng theo order_id hoặc dùng phép tổng hợp phù hợp.

Nếu điều kiện lọc phụ thuộc bảng con, cần giữ đúng ngữ nghĩa. Có thể dùng EXISTS để xác định đơn hàng có ít nhất một item thỏa điều kiện rồi mới phân trang orders. Không đẩy LIMIT qua JOIN một cách máy móc vì có thể thay đổi kết quả.

## 13. Tổng số kết quả và chi phí COUNT

Giao diện phân trang đánh số thường muốn hiển thị “1–50 trên 2.345.678 kết quả”. Để có tổng số chính xác, hệ thống thường chạy COUNT:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status;
~~~

COUNT có thể phải kiểm tra toàn bộ dòng phù hợp. Index có thể giúp tránh đọc cột dữ liệu rộng, nhưng hệ quản trị vẫn cần xác định số entry phù hợp và visibility theo quy tắc của engine. Với tập kết quả lớn, truy vấn COUNT có thể tốn thời gian đáng kể.

### Các lựa chọn

- **Đếm chính xác mỗi request:** phù hợp khi tập dữ liệu nhỏ hoặc yêu cầu nghiệp vụ cần số chính xác.
- **Đếm riêng và cache ngắn hạn:** giảm lặp công việc nhưng số đếm có thể trễ so với dữ liệu mới.
- **Ước lượng:** phù hợp khi giao diện chỉ cần quy mô gần đúng.
- **Không hiển thị tổng:** chỉ hiển thị “còn kết quả” hoặc nút tiếp theo khi có trang sau.
- **Dùng lookahead:** lấy page_size + 1 dòng để biết còn dữ liệu hay không mà không cần COUNT toàn bộ.

Ví dụ lấy thêm một dòng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC, order_id DESC
LIMIT 51;
~~~

Nếu trả về 51 dòng, ứng dụng hiển thị 50 dòng đầu và đặt has_next = true. Cách này hữu ích cho keyset pagination và feed không cần tổng số chính xác.

Cursor tiếp theo phải lấy theo dòng thứ 50 đã hiển thị, không phải dòng thứ 51 dùng để xác định has_next; nếu dùng dòng lookahead làm mốc, bản ghi đó sẽ bị bỏ qua ở trang kế tiếp.

### COUNT và trang cần nhất quán thế nào?

Nếu COUNT và truy vấn lấy trang chạy ở hai snapshot khác nhau, số tổng và nội dung trang có thể không khớp tuyệt đối khi có ghi đồng thời. Nếu nghiệp vụ yêu cầu một ảnh chụp nhất quán, cần xem xét transaction isolation và cách chạy cả hai câu lệnh trong cùng snapshot. Không nên giữ transaction dài qua nhiều request chỉ để duy trì tổng số trang nếu điều đó tạo áp lực lên database.

## 14. Kích thước trang và giới hạn vận hành

Page size quá nhỏ làm tăng số request, round trip và chi phí xử lý lặp. Page size quá lớn làm tăng:

- Số dòng cần đọc và truyền qua mạng.
- Bộ nhớ ứng dụng để giữ kết quả.
- Thời gian serialize và render.
- Khả năng truy vấn kéo dài hoặc timeout.
- Tác động của một request đến các truy vấn đồng thời khác.

Hãy chọn page size theo nhu cầu giao diện và phép đo. Nên có giới hạn tối đa ở server; không để client yêu cầu tùy ý hàng trăm nghìn dòng trong một request phân trang.

Cần kiểm tra nhiều page size, ví dụ 20, 50, 100 và 500. Một index access path phù hợp với page size 20 có thể không còn tối ưu khi yêu cầu 10.000 dòng.

## 15. Đánh giá bằng execution plan và số liệu thực tế

Không thể kết luận phân trang hiệu quả chỉ từ số dòng trả về. Hãy đọc kế hoạch thực thi và xác định số dòng mà hệ quản trị thực sự phải xử lý.

### Các chỉ số quan trọng

| Chỉ số | Ý nghĩa đối với phân trang |
|---|---|
| Estimated rows / actual rows | Optimizer ước lượng và thực tế có bao nhiêu dòng phù hợp |
| Rows read / rows returned | Có bao nhiêu dòng phải đọc để trả một trang |
| Loops | Index lookup hoặc inner operation lặp bao nhiêu lần |
| Sort method và sort spill | Có phải sắp xếp nhiều dữ liệu hoặc ghi tạm ra đĩa không |
| Buffers hit/read | Mức truy cập cache và lưu trữ |
| Temp read/write | Dữ liệu trung gian có tràn ra vùng tạm không |
| CPU time | Chi phí lọc, so sánh, sort và xử lý |
| p50/p95/p99 | Độ trễ điển hình và các request chậm |
| Throughput | Số trang hoặc request hoàn tất mỗi giây |
| Pool wait / lock wait | Request có bị chờ kết nối hoặc khóa trước/trong truy vấn không |

Một truy vấn trả 50 dòng nhưng đọc 500.000 dòng có thể cần tối ưu. Tỷ lệ rows read/rows returned giúp phát hiện công việc dư thừa, dù cách đo chính xác phụ thuộc hệ quản trị.

### Ví dụ PostgreSQL

Đo offset:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 500000;
~~~

Đo keyset:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = 42
  AND status = 'PAID'
  AND (
       created_at < TIMESTAMP '2026-04-18 09:30:00'
       OR (
           created_at = TIMESTAMP '2026-04-18 09:30:00'
           AND order_id < 845120
       )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
~~~

So sánh:

- Node scan và index được sử dụng.
- Actual rows và Rows Removed by Filter.
- Buffers hit/read.
- Có Sort hay không.
- Execution Time.
- Số dòng đọc trước khi đạt LIMIT.

EXPLAIN ANALYZE thực thi truy vấn. Chỉ chạy với truy vấn phù hợp và môi trường có thể chịu tải. Dữ liệu cache có thể ảnh hưởng đáng kể đến kết quả; hãy lặp lại phép đo và ghi rõ điều kiện.

### Kiểm tra kế hoạch ở nhiều nhóm tham số

Không chỉ đo tenant_id = 42. Hãy chọn tenant nhỏ, tenant lớn, status hiếm/phổ biến và khoảng thời gian ngắn/dài. Nếu hệ quản trị tái sử dụng kế hoạch, xem kế hoạch có thay đổi theo nhóm tham số hay không.

## 16. Thiết kế benchmark phân trang trên dữ liệu lớn

Một benchmark có ích phải mô phỏng cách người dùng thực sự duyệt dữ liệu. Chỉ chạy trang đầu nhiều lần không phản ánh chi phí của trang sâu hoặc keyset cursor ở các vùng dữ liệu khác nhau.

### Chuẩn bị dữ liệu đại diện

Dữ liệu thử nghiệm cần thể hiện:

- Quy mô bảng gần với production.
- Phân bố tenant lệch, có tenant nhỏ và tenant lớn.
- Trạng thái phổ biến và hiếm.
- Dữ liệu theo thời gian có vùng nóng và vùng cũ.
- Mật độ dòng theo khoảng thời gian.
- Tỷ lệ insert/update/delete trong khi người dùng duyệt.
- Tỷ lệ bản ghi có quan hệ con nếu truy vấn có JOIN.

Dữ liệu ngẫu nhiên đồng đều có thể làm benchmark lạc quan hơn thực tế nếu production có hot tenant hoặc giá trị phổ biến.

### Ma trận phép đo

| Trục thử nghiệm | Trường hợp cần đo |
|---|---|
| Chiến lược | Offset và keyset |
| Độ sâu | Trang đầu, trang trung bình, trang sâu |
| Tenant | Nhỏ, trung bình, lớn |
| Filter | Hiếm, phổ biến, không khớp |
| Thời gian | Khoảng hẹp và rộng |
| Page size | Nhỏ, mặc định, lớn |
| Cache | Warm cache và trạng thái cache được kiểm soát |
| Concurrency | Một người dùng, tải bình thường, tải đỉnh |
| Dữ liệu thay đổi | Không ghi, có insert/delete/update đồng thời |

### Cách chạy benchmark

1. Chọn các query và nhóm tham số đại diện.
2. Ghi lại schema, index, thống kê, phiên bản DB và cấu hình liên quan.
3. Chạy warm-up theo quy trình thống nhất.
4. Đo nhiều lần và ghi p50, p95, p99 thay vì chỉ lấy trung bình.
5. Ghi số dòng đọc, buffer, I/O, sort và temp spill.
6. So sánh offset và keyset với cùng tập dữ liệu, cùng page size và cùng thứ tự.
7. Chạy lại dưới concurrency thực tế.
8. Kiểm tra tính đúng của kết quả: không trùng, không thiếu ngoài quy tắc snapshot đã định.
9. Lặp lại sau khi thay index hoặc SQL.
10. Ghi lại tác động phụ lên ghi, dung lượng và truy vấn khác.

Không so sánh một lần chạy cold cache của phương án A với warm cache của phương án B. Cũng không so sánh tenant nhỏ với tenant lớn rồi quy toàn bộ chênh lệch cho thuật toán phân trang.

## 17. Ví dụ tổng hợp: danh sách đơn hàng nhiều tenant

Một ứng dụng quản lý đơn hàng có bảng orders với 200 triệu dòng. Một số tenant có vài nghìn đơn, một số tenant có hàng chục triệu đơn. Người dùng thường lọc theo status và xem đơn mới nhất.

Truy vấn ban đầu:

~~~sql
SELECT order_id, created_at, status, total_amount
FROM orders
WHERE tenant_id = :tenant_id
  AND status = :status
ORDER BY created_at DESC
LIMIT 50 OFFSET :offset;
~~~

### Quan sát ban đầu

- Trang đầu nhanh với tenant nhỏ.
- Trang sâu chậm rõ rệt với tenant lớn.
- Status PAID phổ biến hơn nhiều so với CANCELLED.
- Plan có index scan nhưng số dòng phải đi qua tăng theo offset.
- Một số tham số tạo actual rows cao hơn nhiều estimated rows.

### Các bước cải thiện

1. Bổ sung tie-breaker order_id vào ORDER BY để thứ tự xác định.
2. Đánh giá index (tenant_id, status, created_at DESC, order_id DESC).
3. Với luồng duyệt liên tục, chuyển sang keyset bằng cặp created_at/order_id.
4. Giữ offset cho giao diện cần nhảy số trang trong tập dữ liệu nhỏ hoặc có giới hạn.
5. Dùng page_size + 1 để xác định has_next nếu không cần tổng số chính xác.
6. Đo riêng tenant nhỏ/lớn và status hiếm/phổ biến.
7. Kiểm tra actual rows, buffers, sort và latency sau thay đổi.
8. Đánh giá tác động index lên INSERT/UPDATE và các truy vấn khác.

### Điều cần xác nhận

Keyset giúp giảm công việc bỏ qua các trang trước nếu index phù hợp. Nó không tự làm giảm số dòng phù hợp với một filter phổ biến, không thay thế index cho điều kiện tìm kiếm và không tạo snapshot cố định qua nhiều request. Những yêu cầu này phải được đánh giá riêng.

## 18. Những sai lầm thường gặp

- **Chỉ đo trang đầu:** bỏ qua chi phí offset tăng theo độ sâu.
- **Không có tie-breaker duy nhất:** các dòng cùng sort key có thể đổi vị trí và làm trang không ổn định.
- **Chuyển sang keyset nhưng không tạo index phù hợp:** điều kiện cursor vẫn có thể dẫn đến scan hoặc sort lớn.
- **Dùng cursor chỉ chứa một cột:** bỏ sót hoặc lặp dòng khi giá trị sort không duy nhất.
- **Dùng keyset cho yêu cầu nhảy đến trang tùy ý:** keyset cần cursor tại vị trí bắt đầu.
- **Cho rằng keyset tạo snapshot:** dữ liệu thay đổi và sort key cập nhật vẫn có thể làm kết quả thay đổi.
- **Không kiểm tra phân bố tham số:** tenant lớn, status phổ biến và khoảng ngày dài có thể tạo workload hoàn toàn khác.
- **Đếm COUNT(*) cho mọi request:** tổng chính xác có thể đắt hơn truy vấn lấy trang.
- **Đặt LIMIT sau JOIN một-nhiều:** có thể phân trang theo dòng con thay vì thực thể cha.
- **Dùng page size quá lớn:** làm tăng bộ nhớ, truyền dữ liệu và thời gian request.
- **Không giới hạn offset:** client có thể yêu cầu trang sâu gây tải lớn.
- **So sánh benchmark khác trạng thái cache hoặc tải:** kết luận không phản ánh công bằng hai phương án.
- **Ép index hoặc plan cố định quá sớm:** kế hoạch có thể không phù hợp khi dữ liệu và tham số thay đổi.

## 19. Checklist đánh giá phân trang trên dữ liệu lớn

Trước khi triển khai hoặc thay đổi chiến lược phân trang, hãy trả lời:

1. Tập dữ liệu có quy mô bao nhiêu dòng và tăng trưởng ra sao?
2. Người dùng cần nhảy đến trang bất kỳ hay chủ yếu duyệt tiếp?
3. ORDER BY có tạo thứ tự duy nhất bằng tie-breaker không?
4. Offset lớn nhất trong thực tế là bao nhiêu?
5. Filter có phân bố lệch giữa tenant, trạng thái, thời gian hoặc từ khóa không?
6. Index có hỗ trợ cả điều kiện lọc và thứ tự sắp xếp không?
7. Keyset cursor có chứa đủ mọi cột sort và đúng chiều so sánh không?
8. Các cột sort có NULL hoặc có thể cập nhật làm thay đổi vị trí không?
9. Truy vấn JOIN có phân trang ở đúng cấp thực thể không?
10. Có thật sự cần COUNT chính xác hay có thể dùng lookahead/cached/estimated count?
11. p50, p95, p99 và rows read/returned ra sao ở trang đầu, trang sâu và các nhóm tham số?
12. Có spill, sort, I/O, lock wait hoặc connection pool wait không?
13. Dữ liệu insert/delete/update đồng thời ảnh hưởng thế nào đến tính liên tục của trang?
14. Page size và offset có giới hạn ở server không?
15. Sau thay đổi, throughput và latency có cải thiện ở cùng mức tải mà không làm chi phí ghi tăng quá mức không?

## Kết luận

Offset pagination dễ triển khai và hỗ trợ nhảy đến số trang, nhưng chi phí có thể tăng theo số dòng phải bỏ qua. Keyset pagination tiếp tục từ khóa của dòng cuối cùng và có thể seek hiệu quả ở trang sâu khi có index phù hợp cùng thứ tự duy nhất. Mỗi phương án có yêu cầu và giới hạn riêng về điều hướng, tính nhất quán và cách tạo cursor.

Trên dữ liệu lớn, hiệu năng phân trang còn phụ thuộc mạnh vào phân bố tham số: tenant lớn và nhỏ, trạng thái phổ biến và hiếm, khoảng thời gian rộng và hẹp, cũng như kích thước trang và tải đồng thời. Hãy thiết kế index theo filter và ORDER BY, đo nhiều nhóm tham số, đọc execution plan và so sánh rows read, buffers, sort, I/O cùng p95/p99. Chỉ giữ thay đổi khi benchmark có thể lặp lại xác nhận lợi ích và kết quả phân trang vẫn đúng trong điều kiện dữ liệu thay đổi.
