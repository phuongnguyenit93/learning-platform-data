# Khác biệt giữa tải giao dịch (OLTP), tải phân tích (OLAP) và tải hỗn hợp

## Mục tiêu bài học

Khi tối ưu cơ sở dữ liệu, cần hiểu hệ thống đang phục vụ loại công việc nào. Một thao tác cập nhật đơn hàng có yêu cầu khác hẳn một truy vấn tổng hợp doanh thu của nhiều tháng. Nếu áp dụng cùng một cách thiết kế chỉ mục, lưu trữ và phân bổ tài nguyên cho cả hai, hệ thống có thể nhanh với tác vụ này nhưng chậm với tác vụ khác.

Sau bài học, bạn có thể:

- Phân biệt tải giao dịch trực tuyến (OLTP), tải phân tích trực tuyến (OLAP) và tải hỗn hợp (HTAP) theo mục đích, kiểu truy cập và yêu cầu hiệu năng.
- Nhận diện đặc điểm của truy vấn và giao dịch trong từng loại tải.
- Giải thích vì sao chỉ mục, cấu trúc lưu trữ, mức đồng thời và cách phân bổ tài nguyên cần được lựa chọn theo tải thực tế.
- Chọn các chỉ số phù hợp để đo, so sánh và kiểm chứng hiệu năng trước và sau khi điều chỉnh.

Chủ đề này thuộc chương **Nền tảng hiệu năng** của module **DATABASE_PERFORMANCE**. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Vì vậy, các khái niệm dưới đây cần được gắn với hành vi thực tế của hệ thống, thay vì chỉ ghi nhớ tên gọi OLTP hay OLAP.

## 1. Vì sao cần phân biệt các loại tải?

Một cơ sở dữ liệu có thể đồng thời nhận hàng nghìn yêu cầu nhỏ từ ứng dụng và một số truy vấn lớn để lập báo cáo. Hai nhóm công việc này tiêu thụ tài nguyên theo cách khác nhau:

- Yêu cầu giao dịch thường truy cập một số ít bản ghi, cần phản hồi nhanh và phải bảo đảm tính đúng đắn khi nhiều người dùng cùng thao tác.
- Yêu cầu phân tích thường đọc lượng dữ liệu lớn, tính toán tổng hợp hoặc kết hợp nhiều tập dữ liệu. Thời gian chạy có thể dài hơn, nhưng cần xử lý được khối lượng dữ liệu lớn một cách hiệu quả.
- Tải hỗn hợp phải đáp ứng cả hai nhóm trên cùng một nền tảng hoặc trong một kiến trúc dữ liệu phối hợp. Khi đó, việc một truy vấn phân tích tiêu thụ CPU, bộ nhớ hay I/O có thể ảnh hưởng đến giao dịch đang chạy.

Phân loại tải giúp xác định đúng mục tiêu tối ưu. Với OLTP, độ trễ của từng giao dịch và khả năng phục vụ đồng thời thường quan trọng. Với OLAP, thông lượng quét và xử lý dữ liệu, thời gian hoàn tất truy vấn và độ mới của dữ liệu thường quan trọng hơn. Với HTAP, phải đánh giá thêm mức độ ảnh hưởng giữa hai nhóm và độ trễ đồng bộ dữ liệu.

Không nên phân loại chỉ dựa vào câu lệnh bắt đầu bằng `SELECT`, `INSERT` hay `UPDATE`. Một câu `SELECT` tìm một đơn hàng theo mã có thể là OLTP; một câu `SELECT` tổng hợp doanh thu trên hàng tỷ dòng thường là OLAP. Mục đích nghiệp vụ, số dòng được truy cập, hình dạng truy vấn, tần suất và yêu cầu thời gian phản hồi mới là căn cứ hữu ích.

## 2. Tải giao dịch trực tuyến (OLTP)

### 2.1. Khái niệm

OLTP (Online Transaction Processing) là kiểu tải phục vụ các giao dịch nghiệp vụ phát sinh liên tục từ ứng dụng hoặc người dùng. Mỗi giao dịch thường thực hiện một nhóm thao tác nhỏ và có ranh giới rõ ràng, chẳng hạn đăng nhập, tạo đơn hàng, trừ tồn kho, chuyển tiền hoặc cập nhật hồ sơ.

Một giao dịch OLTP thường phải bảo đảm các thuộc tính ACID:

- **Atomicity (tính nguyên tử):** các thay đổi trong giao dịch cùng thành công hoặc cùng bị hủy.
- **Consistency (tính nhất quán):** giao dịch đưa dữ liệu từ một trạng thái hợp lệ sang trạng thái hợp lệ khác theo các ràng buộc đã đặt ra.
- **Isolation (tính cô lập):** các giao dịch đồng thời không được làm lộ ra những trạng thái trung gian trái với mức cô lập đã chọn.
- **Durability (tính bền vững):** khi giao dịch đã được xác nhận thành công, thay đổi được lưu bền vững theo cam kết của hệ quản trị.

### 2.2. Đặc điểm thường gặp

| Khía cạnh | Đặc điểm của OLTP |
|---|---|
| Mục đích | Hoàn thành thao tác nghiệp vụ hiện tại |
| Kiểu truy cập | Đọc hoặc ghi một số ít dòng; tra cứu theo khóa hoặc điều kiện chọn lọc |
| Giao dịch | Ngắn, có ranh giới rõ, thường gồm nhiều câu lệnh liên quan |
| Đồng thời | Nhiều phiên hoặc nhiều người dùng cùng đọc và ghi |
| Độ trễ | Thường cần thấp và ổn định; p95, p99 có ý nghĩa lớn |
| Dữ liệu | Dữ liệu chi tiết, cập nhật thường xuyên |
| Điểm nghẽn thường gặp | Chờ khóa, tranh chấp trên dòng nóng, I/O ghi, thiếu chỉ mục, quá nhiều kết nối |

Ví dụ, khi khách hàng đặt một sản phẩm, ứng dụng có thể cần giảm tồn kho và tạo đơn hàng trong cùng một giao dịch. Đoạn SQL dưới đây minh họa luồng đơn giản theo cú pháp PostgreSQL; ứng dụng cần kiểm tra số dòng được cập nhật để biết còn đủ hàng hay không.

```sql
BEGIN;

UPDATE inventory
SET available = available - 1
WHERE sku = 'SKU-01'
  AND available >= 1;

-- Ứng dụng kiểm tra số dòng UPDATE đã tác động.
-- Nếu không có dòng nào được cập nhật, hủy giao dịch.

INSERT INTO orders (customer_id, status, created_at)
VALUES (42, 'PENDING', CURRENT_TIMESTAMP);

COMMIT;
```

Trong hệ thống thực tế, phần tạo đơn hàng có thể gồm nhiều bảng và cần lấy mã đơn vừa tạo. Ví dụ trên chỉ minh họa yêu cầu giữ các thay đổi liên quan trong một giao dịch. Điều kiện `available >= 1` được kiểm tra ngay trong câu `UPDATE`, giúp tránh quy trình đọc tồn kho rồi ghi lại theo hai bước dễ phát sinh lỗi khi có nhiều yêu cầu đồng thời.

Một truy vấn đọc thường gặp khác là lấy các đơn hàng mới nhất của một khách hàng:

```sql
SELECT order_id, status, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC
LIMIT 20;
```

Nếu đây là đường truy cập thường xuyên, chỉ mục ghép bắt đầu bằng `customer_id` và tiếp theo là `created_at` có thể hỗ trợ lọc và sắp xếp. Cấu trúc cụ thể còn phụ thuộc hệ quản trị, thứ tự tăng/giảm được hỗ trợ, độ chọn lọc, kích thước bảng và các truy vấn khác. Cần xem kế hoạch thực thi và đo trên dữ liệu đại diện trước khi quyết định tạo chỉ mục.

### 2.3. Hướng tối ưu cho OLTP

1. **Giữ giao dịch ngắn:** chỉ thực hiện các thao tác cần thiết trong transaction; tránh giữ khóa trong lúc gọi dịch vụ bên ngoài hoặc chờ người dùng.
2. **Tối ưu truy cập có chọn lọc:** dùng khóa chính, khóa ngoại và chỉ mục phù hợp với điều kiện lọc, phép nối và thứ tự sắp xếp thường gặp.
3. **Kiểm soát chi phí ghi:** mỗi chỉ mục bổ sung có thể làm tăng công việc khi `INSERT`, `UPDATE` và `DELETE`. Không tạo chỉ mục chỉ vì một cột xuất hiện trong câu truy vấn.
4. **Giảm tranh chấp:** xem các giao dịch có cùng cập nhật một dòng, một dải khóa hoặc một tài nguyên hay không; cân nhắc cách phân chia công việc và thứ tự lấy khóa.
5. **Quản lý kết nối:** dùng connection pool với giới hạn phù hợp. Tăng số kết nối vô hạn có thể làm tăng chuyển ngữ cảnh, bộ nhớ và tranh chấp mà không tăng thông lượng.
6. **Đo độ trễ theo phân vị:** p50 thể hiện trải nghiệm điển hình, còn p95 và p99 giúp phát hiện nhóm giao dịch chậm do chờ khóa, I/O hoặc tải đột biến.

Với OLTP, một truy vấn trung bình nhanh chưa đủ chứng minh hệ thống tốt. Nếu phần lớn giao dịch mất 10 ms nhưng một tỷ lệ nhỏ thường xuyên mất vài giây, người dùng vẫn có thể gặp tình trạng hệ thống chập chờn. Vì vậy cần theo dõi cả phân vị độ trễ, tỷ lệ lỗi, timeout và thông lượng ở mức đồng thời thực tế.

## 3. Tải phân tích trực tuyến (OLAP)

### 3.1. Khái niệm

OLAP (Online Analytical Processing) là kiểu tải phục vụ phân tích, tổng hợp và hỗ trợ ra quyết định. Người dùng thường đặt câu hỏi trên tập dữ liệu lớn, ví dụ doanh thu theo tháng, tỷ lệ hoàn hàng theo khu vực, xu hướng mua hàng hoặc hiệu quả của từng chiến dịch.

Truy vấn OLAP thường đọc nhiều dòng, chọn một số cột, kết hợp dữ liệu từ nhiều bảng rồi thực hiện các phép tổng hợp như `SUM`, `COUNT`, `AVG`, `GROUP BY` hoặc phân tích theo cửa sổ. Dữ liệu có thể được nạp theo lô hoặc theo luồng từ hệ thống giao dịch, nên độ mới của dữ liệu là một yêu cầu cần xác định rõ.

### 3.2. Ví dụ truy vấn phân tích

Giả sử nhóm kinh doanh cần tổng hợp doanh thu theo ngày và danh mục sản phẩm trong tháng 10 năm 2026. Ví dụ dùng cú pháp PostgreSQL:

```sql
SELECT
    DATE_TRUNC('day', o.created_at) AS order_day,
    p.category,
    SUM(oi.quantity * oi.unit_price) AS revenue,
    COUNT(DISTINCT o.order_id) AS order_count
FROM orders AS o
JOIN order_items AS oi ON oi.order_id = o.order_id
JOIN products AS p ON p.product_id = oi.product_id
WHERE o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
  AND o.status = 'COMPLETED'
GROUP BY DATE_TRUNC('day', o.created_at), p.category
ORDER BY order_day, p.category;
```

Khác với truy vấn lấy 20 đơn hàng của một khách hàng, truy vấn này có thể phải đọc và kết hợp rất nhiều dòng trước khi trả về số nhóm nhỏ. Thời gian chạy phụ thuộc vào số dòng cần quét, cách nối bảng, thống kê của bộ tối ưu, khả năng đọc dữ liệu từ bộ nhớ hoặc thiết bị lưu trữ, và việc tổng hợp có phải ghi dữ liệu tạm ra đĩa hay không.

Điều kiện thời gian dùng khoảng nửa mở (`>=` ngày đầu và `<` ngày kế tiếp) để tránh bỏ sót hoặc tính trùng dữ liệu ở ranh giới thời gian. Cách viết này cũng tránh bọc cột `created_at` trong hàm ở phần `WHERE`, nhờ đó bộ tối ưu có cơ hội sử dụng chỉ mục hoặc phân vùng theo thời gian. Khả năng sử dụng thực tế vẫn phải được xác nhận bằng kế hoạch thực thi.

### 3.3. Đặc điểm và hướng tối ưu cho OLAP

| Khía cạnh | Đặc điểm của OLAP |
|---|---|
| Mục đích | Hiểu xu hướng, so sánh và tổng hợp dữ liệu |
| Kiểu truy cập | Quét nhiều dòng, thường chỉ cần một phần cột |
| Truy vấn | Nhiều phép nối, lọc phạm vi, nhóm và tổng hợp |
| Đồng thời | Có thể ít phiên hơn OLTP nhưng mỗi truy vấn tiêu thụ nhiều tài nguyên |
| Độ trễ | Thường chấp nhận lâu hơn giao dịch, tùy SLA của báo cáo |
| Dữ liệu | Lịch sử, dữ liệu tích hợp hoặc dữ liệu đã được biến đổi |
| Điểm nghẽn thường gặp | Quét I/O lớn, nối dữ liệu tốn CPU, thiếu bộ nhớ, tràn dữ liệu tạm, thống kê sai |

Các hướng tối ưu thường dùng:

- **Đọc đúng phần dữ liệu cần thiết:** chỉ chọn các cột cần dùng; đặt điều kiện lọc có thể tận dụng chỉ mục hoặc partition pruning; tránh quét toàn bộ lịch sử nếu báo cáo chỉ cần một khoảng thời gian.
- **Chọn cấu trúc lưu trữ phù hợp:** hệ thống phân tích thường hưởng lợi từ lưu trữ dạng cột vì có thể đọc ít cột trên nhiều dòng và nén dữ liệu hiệu quả. Đây là lựa chọn kiến trúc, không phải mặc định phù hợp cho mọi cơ sở dữ liệu giao dịch.
- **Tổ chức dữ liệu theo truy vấn:** phân vùng theo thời gian hoặc khóa phù hợp có thể giảm phạm vi quét. Phân vùng quá nhỏ hoặc quá nhiều lại làm tăng chi phí quản lý và lập kế hoạch.
- **Duy trì thống kê:** bộ tối ưu dựa vào thống kê để ước lượng số dòng và chọn thứ tự nối. Thống kê cũ hoặc thiếu có thể khiến kế hoạch thực thi kém.
- **Kiểm soát phép nối và tổng hợp:** kiểm tra số dòng đầu vào, thứ tự nối, thuật toán nối, sắp xếp và việc dùng bộ nhớ. Nếu thao tác tràn ra vùng lưu trữ tạm, cần tìm nguyên nhân và đánh giá cấu hình bộ nhớ cũng như hình dạng truy vấn.
- **Cân nhắc dữ liệu tổng hợp:** bảng tổng hợp, materialized view hoặc mô hình dữ liệu chiều có thể giảm công việc lặp lại. Cần tính cả chi phí cập nhật, độ trễ làm mới và yêu cầu nhất quán.

Với OLAP, chỉ nhìn thời gian phản hồi của một lần chạy cũng có thể gây hiểu nhầm do dữ liệu đã nằm trong cache hoặc do tải hệ thống khác nhau. Nên đo nhiều lần trong điều kiện có thể lặp lại, ghi nhận số dòng/byte đọc, CPU, I/O, bộ nhớ và dữ liệu tạm theo khả năng quan sát của hệ quản trị.

## 4. Tải hỗn hợp (HTAP)

### 4.1. Khái niệm

HTAP (Hybrid Transactional/Analytical Processing) mô tả hệ thống hoặc kiến trúc kết hợp xử lý giao dịch và phân tích. Mục tiêu là cho phép tổ chức vừa thực hiện giao dịch nghiệp vụ, vừa khai thác dữ liệu phục vụ phân tích với độ trễ dữ liệu phù hợp.

Tải hỗn hợp có thể được triển khai theo nhiều cách:

1. **Cùng một hệ quản trị và cùng tài nguyên:** giao dịch và truy vấn phân tích chạy trên một cụm hoặc một cơ sở dữ liệu. Cách này có thể cho phép đọc dữ liệu mới nhanh, nhưng hai nhóm tải cạnh tranh CPU, bộ nhớ, I/O, cache và khóa.
2. **Tách bản sao đọc hoặc nút phân tích:** dữ liệu được sao chép từ hệ thống giao dịch sang nơi phục vụ truy vấn nặng. Việc tách tải giúp bảo vệ đường giao dịch, nhưng kết quả phân tích có thể trễ do độ trễ sao chép.
3. **Đưa dữ liệu qua luồng CDC hoặc pipeline:** thay đổi từ hệ thống giao dịch được ghi nhận rồi chuyển tới kho dữ liệu hoặc nền tảng phân tích. Cách này linh hoạt khi khối lượng phân tích lớn, nhưng cần quản lý thứ tự sự kiện, xử lý lặp, lỗi đồng bộ và thời gian làm mới.

Tên HTAP không bảo đảm rằng mọi truy vấn phân tích đều chạy tức thời hoặc không ảnh hưởng giao dịch. Hiệu quả phụ thuộc vào công nghệ, cấu hình, mô hình dữ liệu, khối lượng tải và yêu cầu nhất quán.

### 4.2. Những đánh đổi cần đánh giá

| Vấn đề | Câu hỏi cần trả lời |
|---|---|
| Độ mới dữ liệu | Báo cáo cần dữ liệu mới ngay lập tức, sau vài giây hay theo lô mỗi giờ? |
| Nhất quán | Có chấp nhận dữ liệu đọc trễ hoặc trạng thái chưa đồng bộ không? |
| Cạnh tranh tài nguyên | Truy vấn quét lớn có làm tăng p95/p99 của giao dịch không? |
| Đồng bộ | Độ trễ sao chép, lỗi pipeline và khả năng phát lại sự kiện được theo dõi thế nào? |
| Cô lập | Có thể giới hạn CPU, bộ nhớ, I/O hoặc chuyển truy vấn phân tích sang nút riêng không? |
| Chi phí vận hành | Độ phức tạp của bản sao, pipeline và mô hình dữ liệu có tương xứng với lợi ích không? |

Một kiến trúc HTAP cần được kiểm thử bằng tải hỗn hợp. Chạy riêng benchmark OLTP và benchmark OLAP có thể cho kết quả tốt, nhưng không thể hiện được việc một truy vấn báo cáo lớn làm tăng thời gian chờ của giao dịch trong giờ cao điểm.

## 5. So sánh nhanh OLTP, OLAP và HTAP

| Tiêu chí | OLTP | OLAP | HTAP |
|---|---|---|---|
| Câu hỏi chính | Giao dịch này có hoàn tất đúng và nhanh không? | Dữ liệu cho thấy xu hướng hay kết quả gì? | Có thể vừa xử lý giao dịch vừa phân tích với độ mới cần thiết không? |
| Đơn vị công việc | Giao dịch nhỏ | Truy vấn phân tích | Cả giao dịch và phân tích |
| Truy cập dữ liệu | Ít dòng, chọn lọc | Nhiều dòng, nhiều phép tổng hợp | Pha trộn hai kiểu truy cập |
| Mẫu hiệu năng | Độ trễ thấp, ổn định, nhiều giao dịch đồng thời | Thông lượng đọc và xử lý tập dữ liệu lớn | Độ trễ giao dịch, thời gian phân tích và mức cô lập tải |
| Thiết kế thường gặp | Chỉ mục theo đường truy cập, giao dịch ngắn, dữ liệu chuẩn hóa | Lưu trữ dạng cột, phân vùng, dữ liệu tổng hợp, mô hình phân tích | Tài nguyên dùng chung có kiểm soát hoặc kiến trúc sao chép/tách tải |
| Rủi ro nổi bật | Chờ khóa, deadlock, quá tải kết nối | Quét dữ liệu lớn, tràn bộ nhớ, kế hoạch nối kém | Tranh chấp tài nguyên hoặc dữ liệu phân tích bị trễ |

Đây là các khuynh hướng phổ biến, không phải quy tắc tuyệt đối. Một hệ thống có thể có truy vấn đọc lớn trong đường nghiệp vụ, hoặc có tác vụ ghi theo lô trong nền tảng phân tích. Hãy phân loại từng luồng công việc dựa trên yêu cầu và dữ liệu đo được.

## 6. Cách nhận diện loại tải trong một hệ thống thực tế

Có thể dùng quy trình sau khi khảo sát một ứng dụng:

**Bước 1 — Xác định mục đích nghiệp vụ.** Truy vấn đang phục vụ một hành động cần hoàn tất ngay, hay đang trả lời câu hỏi tổng hợp cho người vận hành và nhà phân tích?

**Bước 2 — Quan sát hình dạng truy cập.** Ghi nhận số dòng ước lượng và thực tế, số bảng tham gia, điều kiện lọc, cột được đọc, số dòng ghi, kích thước giao dịch và tần suất chạy.

**Bước 3 — Xác định yêu cầu thời gian.** Hỏi rõ thời gian phản hồi mục tiêu, phân vị cần bảo đảm, thông lượng giờ cao điểm, mức đồng thời và độ trễ dữ liệu có thể chấp nhận.

**Bước 4 — Đo tải nền.** Thu thập p50/p95/p99, TPS hoặc QPS, timeout, lỗi, CPU, bộ nhớ, IOPS, thông lượng và độ trễ I/O, thời gian chờ khóa, deadlock, dữ liệu tạm và độ trễ sao chép nếu có. Tên và cách tính metric khác nhau giữa các hệ quản trị, vì vậy cần hiểu định nghĩa của công cụ đang dùng.

**Bước 5 — Kiểm tra kế hoạch và thống kê.** Dùng công cụ giải thích kế hoạch thực thi của hệ quản trị để kiểm tra đường truy cập, số dòng ước lượng so với số dòng thực tế, kiểu nối, thao tác sắp xếp, quét dữ liệu và chi phí I/O. Đối chiếu với thống kê hiện hành trước khi kết luận cần thêm chỉ mục hay đổi cấu trúc dữ liệu.

**Bước 6 — Kiểm thử đúng kiểu tải.** Với OLTP, mô phỏng giao dịch ngắn và mức đồng thời tương tự giờ cao điểm. Với OLAP, dùng kích thước dữ liệu và phạm vi thời gian đại diện. Với HTAP, chạy hai nhóm cùng lúc và đo ảnh hưởng qua lại.

## 7. Ví dụ: hệ thống bán hàng

Một nền tảng bán hàng có ba luồng công việc:

| Luồng công việc | Phân loại gần đúng | Điều cần ưu tiên |
|---|---|---|
| Khách đặt hàng, cập nhật tồn kho và thanh toán | OLTP | Giao dịch đúng, độ trễ thấp, xử lý đồng thời an toàn |
| Nhân viên xem 20 đơn gần nhất của một khách | OLTP | Lọc chọn lọc, chỉ mục phù hợp, phản hồi ổn định |
| Quản lý xem doanh thu theo tháng, khu vực và danh mục | OLAP | Đọc và tổng hợp dữ liệu lớn, kế hoạch nối hiệu quả |
| Trang vận hành hiển thị doanh thu gần thời gian thực trong khi khách vẫn đặt hàng | HTAP hoặc kiến trúc tải hỗn hợp | Độ mới dữ liệu và mức ảnh hưởng của phân tích lên giao dịch |

Giả sử báo cáo doanh thu làm p99 của thao tác đặt hàng tăng mạnh vào đầu mỗi giờ. Không nên kết luận ngay rằng cần thêm chỉ mục cho bảng đơn hàng. Hãy kiểm tra đồng thời CPU, I/O, bộ nhớ, chờ khóa, kế hoạch truy vấn báo cáo và thời điểm chạy. Nếu báo cáo quét dữ liệu lịch sử lớn trên cùng tài nguyên, giải pháp có thể là giới hạn tài nguyên truy vấn, chuyển báo cáo sang bản sao đọc, hoặc đưa dữ liệu sang kho phân tích. Chọn phương án sau khi so sánh độ trễ dữ liệu, chi phí và kết quả benchmark.

Sau điều chỉnh, chạy lại cùng kịch bản và cùng mức tải. So sánh ít nhất p95/p99 của giao dịch, thông lượng, thời gian báo cáo, CPU, I/O, mức sử dụng bộ nhớ và độ trễ đồng bộ. Nếu báo cáo nhanh hơn nhưng p99 của giao dịch xấu đi, thay đổi chưa đáp ứng mục tiêu của hệ thống hỗn hợp.

## 8. Những nhầm lẫn thường gặp

- **“OLTP chỉ đọc ít dòng, OLAP chỉ đọc nhiều dòng.”** Đây là xu hướng, không phải định nghĩa duy nhất. Mục đích nghiệp vụ, ranh giới giao dịch, yêu cầu nhất quán và SLA cũng quan trọng.
- **“Mọi câu `SELECT` đều là OLAP.”** Một truy vấn tra cứu đơn hàng có thể là phần cốt lõi của OLTP.
- **“Thêm nhiều chỉ mục luôn làm truy vấn nhanh hơn.”** Chỉ mục có thể tăng tốc đọc phù hợp nhưng làm tăng dung lượng, chi phí ghi và công việc bảo trì.
- **“Dùng chung một cơ sở dữ liệu nghĩa là đã có HTAP hiệu quả.”** Hệ thống vẫn có thể bị tranh chấp tài nguyên và chưa chắc đáp ứng được yêu cầu độ mới dữ liệu.
- **“Tách báo cáo sang bản sao đọc thì dữ liệu luôn mới.”** Bản sao có thể có replication lag; ứng dụng phải xác định và giám sát mức trễ chấp nhận được.
- **“Một lần benchmark là đủ.”** Kết quả có thể bị ảnh hưởng bởi cache, dữ liệu thử, mức đồng thời và tải nền. Cần kịch bản lặp lại được và dữ liệu đại diện.

## 9. Checklist khi đánh giá tải cơ sở dữ liệu

- [ ] Đã xác định mục đích nghiệp vụ của từng nhóm truy vấn.
- [ ] Đã ghi nhận tần suất, mức đồng thời, kích thước dữ liệu và tỷ lệ đọc/ghi.
- [ ] Đã xác định mục tiêu độ trễ, thông lượng và độ mới dữ liệu.
- [ ] Đã đo p50, p95, p99, lỗi và timeout cho các luồng quan trọng.
- [ ] Đã kiểm tra CPU, bộ nhớ, I/O, chờ khóa, dữ liệu tạm và độ trễ sao chép phù hợp với loại tải.
- [ ] Đã xem kế hoạch thực thi và đối chiếu số dòng ước lượng với thực tế.
- [ ] Đã thử nghiệm bằng dữ liệu và mức tải đại diện, bao gồm tải đồng thời nếu là HTAP.
- [ ] Đã đo lại sau điều chỉnh và xác nhận cả mục tiêu chính lẫn ảnh hưởng phụ.

## Kết luận

OLTP tập trung hoàn tất các giao dịch nghiệp vụ nhỏ, chính xác và nhanh. OLAP tập trung khai thác dữ liệu lớn để phân tích và tổng hợp. HTAP kết hợp hai nhu cầu, đồng thời đặt ra bài toán về cạnh tranh tài nguyên, độ mới và tính nhất quán của dữ liệu.

Trong công việc tối ưu hiệu năng cơ sở dữ liệu, việc phân loại tải là bước đầu để đặt đúng câu hỏi. Tiếp theo cần đo tải thực tế, đọc kế hoạch thực thi, kiểm tra thống kê và xác định cơ chế truy cập dữ liệu gây tốn kém. Chỉ mục, phân vùng, lưu trữ dạng cột, bản sao đọc hay pipeline dữ liệu đều là lựa chọn cần được kiểm chứng bằng cùng một kịch bản đo trước và sau thay đổi.
