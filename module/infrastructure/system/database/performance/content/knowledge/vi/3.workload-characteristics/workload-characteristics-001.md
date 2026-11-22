# Thu thập tập truy vấn và nhóm truy vấn theo mẫu (query fingerprint)

Muốn tối ưu hiệu năng cơ sở dữ liệu, trước hết cần biết hệ thống đang thực hiện những truy vấn nào, chúng xuất hiện với tần suất ra sao và tiêu tốn tài nguyên ở mức nào. Một hệ thống thực tế có thể phát sinh hàng nghìn câu lệnh SQL khác nhau do ứng dụng, ORM, tác vụ nền và người dùng vận hành gửi đến. Nếu chỉ đọc từng dòng log riêng lẻ, nhóm phát triển khó nhận ra mẫu truy cập lặp lại và khó xác định phần tải nào đóng góp nhiều nhất vào tổng chi phí.

Thu thập tập truy vấn (query workload collection) là quá trình ghi nhận có kiểm soát các hoạt động truy cập cơ sở dữ liệu trong một khoảng thời gian đại diện. Sau đó, nhóm truy vấn theo mẫu (query fingerprint) giúp nhận diện những câu lệnh có cùng cấu trúc dù giá trị tham số khác nhau. Từ các nhóm này, có thể tổng hợp số lần thực thi, độ trễ, lượng dữ liệu đọc, mức sử dụng CPU, thời gian chờ và tỷ lệ lỗi để hiểu đặc điểm workload trước khi thay đổi SQL, chỉ mục hoặc cấu hình.

Nội dung này thuộc chương **Khối lượng công việc** của module DATABASE_PERFORMANCE. Module rèn phương pháp tối ưu hiệu năng dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy, dữ liệu truy vấn cần được thu thập theo cách có thể đối chiếu, phân tích và kiểm chứng.

## 1. Tập truy vấn phản ánh điều gì?

Workload cơ sở dữ liệu là tập hợp các thao tác đọc, ghi và giao dịch mà ứng dụng thực sự gửi đến hệ quản trị trong một khoảng thời gian. Workload có thể thay đổi theo giờ trong ngày, ngày trong tuần, mùa kinh doanh, đợt nhập dữ liệu hoặc sự kiện bất thường. Một lần quan sát ngắn vào giờ thấp điểm có thể không phản ánh tải cao điểm; một lần chạy thử bằng dữ liệu nhỏ cũng không đại diện cho phân bố dữ liệu và mức đồng thời ngoài môi trường thật.

Một tập truy vấn hữu ích cần cho biết ít nhất:

- **Câu lệnh hoặc mẫu câu lệnh:** cấu trúc truy vấn, loại thao tác và các bảng hoặc đối tượng dữ liệu liên quan.
- **Tần suất:** số lần một mẫu được gọi trong khoảng thời gian quan sát.
- **Thời gian:** tổng thời gian tiêu tốn, thời gian trung bình và phân bố độ trễ của từng lần thực thi.
- **Khối lượng dữ liệu:** số dòng được đọc, số dòng trả về, số dòng bị cập nhật hoặc xóa, lượng dữ liệu tạm và hoạt động đọc/ghi.
- **Mức đồng thời:** số phiên hoặc giao dịch cùng thực hiện, thời gian chờ khóa và các dạng chờ tài nguyên.
- **Kết quả:** số lần thành công, lỗi, timeout, deadlock hoặc bị hủy.
- **Ngữ cảnh:** ứng dụng, endpoint, người dùng dịch vụ, cơ sở dữ liệu, schema, loại giao dịch và khoảng thời gian phát sinh.

Không phải nguồn thu thập nào cũng cung cấp đầy đủ mọi trường. Có thể kết hợp thống kê của hệ quản trị, log truy vấn, công cụ theo dõi ứng dụng và trace để bổ sung ngữ cảnh. Cần ghi rõ nguồn và phạm vi của từng số liệu để tránh so sánh những đại lượng được đo theo cách khác nhau.

## 2. Query fingerprint là gì?

Query fingerprint là định danh đại diện cho cấu trúc của một câu lệnh truy vấn sau khi đã chuẩn hóa. Các câu SQL có cùng cấu trúc nhưng khác giá trị literal hoặc giá trị bind parameter thường được gom vào cùng một nhóm. Công cụ thu thập có thể tạo chuỗi SQL đã chuẩn hóa rồi tính mã băm (hash) để dùng làm khóa nhóm. Một số hệ quản trị gọi mã đại diện này là query digest hoặc statement digest; cách chuẩn hóa và phạm vi nhóm phụ thuộc vào từng nền tảng.

Ví dụ, ứng dụng có thể phát sinh các câu lệnh:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = 101
  AND status = 'PAID';

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 205
  AND status = 'PENDING';

SELECT order_id, total_amount
FROM orders
WHERE customer_id = 876
  AND status = 'PAID';
~~~

Nếu chuẩn hóa các giá trị literal thành tham số, ba câu lệnh có thể được biểu diễn bằng một mẫu:

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE customer_id = ?
  AND status = ?;
~~~

Như vậy, thay vì xem ba câu SQL như ba truy vấn độc lập, nhóm phân tích có thể xem chúng là ba lần thực thi của cùng một fingerprint. Nhóm đó có thể trả lời các câu hỏi như: mẫu này được gọi bao nhiêu lần, tổng thời gian thực thi là bao nhiêu, có thường xuyên đọc nhiều dòng không và có phát sinh chờ khóa hay không.

### Phân biệt câu SQL gốc, mẫu chuẩn hóa và fingerprint

| Khái niệm | Ý nghĩa | Mục đích |
| --- | --- | --- |
| SQL gốc (raw statement) | Câu lệnh được gửi đến cơ sở dữ liệu, có thể chứa literal hoặc tham số | Điều tra một lần thực thi cụ thể và tái hiện vấn đề khi được phép |
| Mẫu chuẩn hóa (normalized statement) | Câu lệnh đã được chuẩn hóa về khoảng trắng, cách viết và giá trị literal theo quy tắc của công cụ | Đại diện cho cấu trúc truy vấn |
| Query fingerprint/digest | Mã định danh được tạo từ mẫu chuẩn hóa hoặc cấu trúc truy vấn | Nhóm, đếm và tổng hợp số liệu hiệu năng |

Fingerprint không phải là bản ghi đầy đủ của một lần chạy. Nó không nhất thiết giữ lại giá trị tham số, thời điểm, người gọi, kết quả trả về hay trạng thái giao dịch. Những thông tin đó cần được ghi nhận ở các trường riêng khi có nhu cầu và khi chính sách dữ liệu cho phép. Vì fingerprint thường được tạo bằng mã băm, hệ thống thu thập nên giữ mẫu chuẩn hóa để kiểm tra; nếu hai mẫu khác nhau tình cờ có cùng mã băm, không được nhập chúng thành một nhóm chỉ dựa trên hash.

## 3. Chuẩn hóa truy vấn để nhóm đúng mẫu

Chuẩn hóa là bước quyết định những câu lệnh nào được gom vào cùng một nhóm. Một quy trình khái quát có thể gồm các thao tác:

1. Phân tích câu lệnh theo cú pháp SQL để nhận biết từ khóa, tên đối tượng, toán tử, biểu thức và giá trị literal.
2. Chuẩn hóa cách trình bày như khoảng trắng, xuống dòng và cách viết từ khóa theo quy tắc nhất quán.
3. Thay các giá trị literal như số, chuỗi hoặc ngày giờ bằng placeholder khi chúng chỉ đóng vai trò tham số.
4. Giữ lại cấu trúc có ý nghĩa như loại lệnh, bảng, cột, điều kiện, phép nối, phép sắp xếp và hình dạng biểu thức.
5. Tạo fingerprint từ biểu diễn chuẩn hóa; lưu mẫu chuẩn hóa đi kèm để có thể kiểm tra nhóm khi cần.

Ví dụ, hai câu lệnh sau thường có thể được gom cùng mẫu:

~~~sql
SELECT * FROM customers WHERE customer_id = 10;
SELECT * FROM customers WHERE customer_id = 20;
~~~

Mẫu chuẩn hóa tương ứng:

~~~sql
SELECT * FROM customers WHERE customer_id = ?;
~~~

Tuy nhiên, chuẩn hóa cần dựa trên bộ phân tích cú pháp hoặc cơ chế digest của hệ quản trị. Thay thế chuỗi bằng biểu thức tìm kiếm đơn giản có thể làm hỏng câu SQL, nhầm literal bên trong chuỗi, bỏ qua comment có ý nghĩa hoặc xử lý sai cú pháp đặc thù của từng nền tảng.

### Không chuẩn hóa quá mức

Hai câu lệnh chỉ nên nằm chung một nhóm khi cấu trúc của chúng thực sự tương đương theo quy tắc của công cụ. Chẳng hạn, truy vấn đọc một khách hàng theo khóa chính và truy vấn đọc toàn bộ khách hàng có thể có chi phí rất khác nhau, vì vậy không được xóa điều kiện lọc khi chuẩn hóa.

Các yếu tố cần cân nhắc:

- Giữ tên bảng, cột, phép nối và cấu trúc điều kiện có ý nghĩa. Không biến mọi câu SELECT thành một fingerprint chung.
- Phân biệt loại câu lệnh và hình dạng truy vấn, ví dụ SELECT, INSERT, UPDATE, DELETE, truy vấn có phép nối và truy vấn tổng hợp.
- Xem xét cách xử lý danh sách IN. Một số công cụ chuẩn hóa danh sách giá trị thành cùng dạng, trong khi công cụ khác giữ thông tin về số phần tử hoặc cấu trúc tham số.
- Chú ý truy vấn có tên bảng hoặc cột được sinh động. Nếu tên đối tượng thay đổi theo tenant hoặc theo bảng phân vùng, có thể tạo nhiều fingerprint dù logic ứng dụng tương tự.
- Kiểm tra comment được ORM hoặc thư viện chèn vào. Comment chứa request ID duy nhất có thể làm các chuỗi SQL khác nhau dù cấu trúc giống nhau, nếu công cụ không loại bỏ phần đó.
- Không tự ý bỏ ORDER BY, LIMIT, điều kiện phân trang hoặc biểu thức tính toán; chúng có thể làm thay đổi lượng dữ liệu và chi phí thực thi.

Quy tắc cụ thể khác nhau giữa các hệ quản trị. Khi sử dụng digest có sẵn của nền tảng, cần đọc tài liệu để biết cách xử lý literal, comment, danh sách tham số, schema và câu lệnh đặc thù. Không nên giả định fingerprint từ hai hệ quản trị khác nhau có thể so sánh trực tiếp.

## 4. Thu thập dữ liệu truy vấn từ đâu?

Có nhiều nguồn để xây dựng tập truy vấn. Việc chọn nguồn phụ thuộc vào hệ quản trị, yêu cầu quan sát, mức chi tiết cần thiết và ngân sách tài nguyên.

### Thống kê tích hợp trong hệ quản trị

Nhiều hệ quản trị cung cấp thống kê câu lệnh đã tổng hợp theo mẫu hoặc digest. Ví dụ:

- PostgreSQL có extension **pg_stat_statements** để theo dõi thống kê các câu lệnh SQL, với dữ liệu tổng hợp theo định danh truy vấn và các bộ đếm tương ứng.
- MySQL cung cấp các bảng trong **Performance Schema**, trong đó có thống kê câu lệnh theo digest.
- Microsoft SQL Server có **Query Store** để lưu thông tin truy vấn, kế hoạch và số liệu hiệu năng theo khoảng thời gian.

Đây là các ví dụ theo nền tảng, không phải một giao diện chung cho mọi hệ quản trị. Cần kiểm tra phiên bản, cấu hình bật/tắt, quyền truy cập, cách reset thống kê, thời gian lưu dữ liệu và giới hạn dung lượng. Một số thống kê chỉ giữ số liệu tổng hợp, không giữ toàn bộ từng lần thực thi hoặc không giữ đầy đủ ngữ cảnh ứng dụng.

### Log truy vấn và slow query log

Log truy vấn có thể cung cấp câu lệnh, thời điểm, thời gian thực thi, lỗi và một số thông tin về phiên. Slow query log giúp tập trung vào những lần chạy vượt ngưỡng thời gian đã cấu hình. Tuy nhiên, chỉ thu thập truy vấn chậm sẽ bỏ sót những truy vấn rất ngắn nhưng được gọi hàng triệu lần; những truy vấn đó có thể chiếm phần lớn tổng thời gian tiêu tốn.

General query log hoặc chế độ ghi mọi câu lệnh có thể tạo lượng log rất lớn và làm tăng chi phí I/O, dung lượng, luân chuyển file cũng như xử lý log. Chỉ bật khi có lý do rõ ràng, trên phạm vi và thời gian phù hợp; cần theo dõi tác động của chính hoạt động thu thập.

### Theo dõi từ ứng dụng và APM

Ứng dụng có thể ghi nhận thời gian gọi cơ sở dữ liệu, số lượt gọi trong mỗi request, tên endpoint, loại thao tác và trace ID. APM hoặc distributed tracing giúp nối một truy vấn với đường đi của yêu cầu người dùng, nhờ đó phân biệt thời gian chờ pool, thời gian gửi/nhận và thời gian xử lý ở ứng dụng.

Nguồn này hữu ích khi cần biết fingerprint nào gắn với chức năng nghiệp vụ nào. Tuy nhiên, tên truy vấn do ORM sinh ra có thể khác nhau giữa phiên bản thư viện hoặc cách cấu hình. Nên lưu thêm thông tin ứng dụng và phiên bản triển khai để giải thích thay đổi workload sau mỗi lần phát hành.

### Proxy, gateway hoặc công cụ quan sát chuyên dụng

Trong một số kiến trúc, proxy cơ sở dữ liệu hoặc hệ thống quan sát có thể thu thập câu lệnh, gom digest và thống kê thời gian. Nguồn này giúp quan sát tập trung nhiều dịch vụ, nhưng có thể không nhìn thấy toàn bộ ngữ cảnh nội bộ của ứng dụng hoặc có thể biến đổi câu lệnh trước khi ghi nhận. Cần xác định điểm thu thập nằm trước hay sau proxy và liệu có bỏ sót kết nối trực tiếp nào hay không.

## 5. Những trường nên ghi nhận cho mỗi lần thực thi và mỗi nhóm

Để phân tích hiệu năng, dữ liệu cần đủ để trả lời cả hai câu hỏi: một lần chạy tốn bao nhiêu chi phí và cả nhóm truy vấn đóng góp bao nhiêu vào workload.

| Trường dữ liệu | Mức ghi nhận | Ý nghĩa |
| --- | --- | --- |
| Fingerprint/digest | Theo nhóm | Khóa gom các câu lệnh cùng mẫu |
| Mẫu SQL chuẩn hóa | Theo nhóm | Giúp con người kiểm tra cấu trúc truy vấn |
| Thời điểm hoặc khoảng thời gian | Theo lần chạy hoặc bucket thời gian | Nhận biết giờ cao điểm và biến động |
| Số lần thực thi | Theo nhóm và khoảng thời gian | Đo tần suất |
| Tổng thời gian thực thi | Theo nhóm và khoảng thời gian | Ước lượng chi phí tích lũy |
| Trung bình, p50, p95, p99, lớn nhất | Theo nhóm và khoảng thời gian | Hiểu phân bố độ trễ |
| Số dòng đọc và trả về | Theo lần chạy hoặc bộ đếm tổng hợp | Nhận biết truy vấn đọc nhiều nhưng trả ít |
| CPU, logical/physical reads, I/O | Theo lần chạy hoặc nhóm | Phân tích tài nguyên tiêu thụ |
| Thời gian chờ khóa và loại wait | Theo lần chạy hoặc nhóm | Nhận diện tranh chấp |
| Lỗi, timeout, deadlock | Theo lần chạy hoặc nhóm | Đánh giá độ tin cậy |
| Database, schema, ứng dụng, endpoint | Theo ngữ cảnh | Tách workload theo nguồn phát sinh |
| Plan ID hoặc phiên bản kế hoạch | Nếu hệ quản trị cung cấp | Nhận biết thay đổi kế hoạch thực thi |

Không phải mọi nền tảng đều cung cấp phân vị hoặc số liệu theo từng lần chạy. Nếu nguồn chỉ có tổng thời gian và số lần thực thi, có thể tính trung bình bằng tổng thời gian chia số lần chạy, nhưng không thể suy ra p95 chính xác từ giá trị trung bình. Muốn có phân vị, cần histogram, mẫu từng lần thực thi hoặc công cụ giữ phân bố độ trễ.

Nên phân biệt **chi phí trên mỗi lần chạy** với **chi phí tích lũy của cả nhóm**. Truy vấn mất 5 ms nhưng chạy 200.000 lần có thể tiêu tốn tổng cộng 1.000 giây. Truy vấn mất 2 giây nhưng chỉ chạy 2 lần có tổng thời gian 4 giây. Nhóm truy vấn đầu tiên có thể là mục tiêu cải thiện tổng tải tốt hơn, trong khi truy vấn thứ hai vẫn cần xem xét nếu ảnh hưởng trực tiếp đến một chức năng quan trọng.

## 6. Tạo nhóm và xếp hạng workload

Sau khi thu thập, cần gom các lần thực thi theo fingerprint và khoảng thời gian. Một báo cáo cơ bản có thể gồm:

| Fingerprint | Số lần gọi | Thời gian trung bình | Tổng thời gian | Đặc điểm |
| --- | ---: | ---: | ---: | --- |
| Q-A | 200.000 | 5 ms | 1.000 s | Truy vấn ngắn, tần suất rất cao |
| Q-B | 2.000 | 80 ms | 160 s | Truy vấn thường xuyên, độ trễ vừa |
| Q-C | 2 | 2.000 ms | 4 s | Truy vấn hiếm, mỗi lần chạy lâu |

Các số liệu trên chỉ minh họa cách xếp hạng. Tổng thời gian là tích lũy thời gian thực thi của các lần chạy trong cùng phạm vi đo; cần bảo đảm cách tính của nguồn thống kê đã được hiểu đúng. Nếu các truy vấn chạy song song, tổng thời gian CPU hoặc elapsed time tích lũy có thể lớn hơn thời gian đồng hồ thực tế của khoảng quan sát.

Có thể xếp hạng theo nhiều góc nhìn:

- **Tổng thời gian:** tìm nhóm truy vấn đóng góp lớn vào chi phí thực thi tích lũy.
- **Độ trễ cao:** tìm truy vấn ảnh hưởng đến các yêu cầu có thời gian đáp ứng dài.
- **Tần suất cao:** tìm truy vấn được gọi lặp lại nhiều lần, kể cả khi mỗi lần chạy nhanh.
- **Đọc dữ liệu lớn:** tìm truy vấn đọc nhiều trang hoặc nhiều dòng nhưng trả về ít dữ liệu.
- **Chờ khóa hoặc tài nguyên:** tìm nhóm có thời gian chờ cao, deadlock hoặc timeout.
- **Tỷ lệ lỗi:** tìm mẫu có nhiều lần thất bại hoặc bị hủy.

Không nên dùng một bảng xếp hạng duy nhất để quyết định mọi tối ưu hóa. Tổng thời gian giúp ưu tiên chi phí toàn hệ thống; p95/p99 phản ánh trải nghiệm yêu cầu chậm; tần suất cho thấy cơ hội giảm số lượt gọi; số dòng đọc và thời gian chờ giúp định hướng nguyên nhân. Cần đặt từng chỉ số trong bối cảnh SLA, mức quan trọng nghiệp vụ và loại tải.

### Phân tích theo thời gian

Một fingerprint có thể bình thường vào giờ thấp điểm nhưng trở thành nút thắt khi tải tăng. Nên tổng hợp theo các bucket thời gian phù hợp, ví dụ mỗi phút, mỗi 5 phút hoặc mỗi giờ tùy mục đích. So sánh giờ cao điểm với giờ bình thường, ngày làm việc với cuối tuần và trước/sau một lần phát hành.

Nếu thống kê của hệ quản trị là bộ đếm tích lũy kể từ lúc khởi động hoặc reset, hãy chụp hai mốc và tính chênh lệch trong khoảng quan sát. Cần ghi nhận thời điểm reset, khởi động lại hoặc làm mới thống kê; nếu không, số liệu chênh lệch có thể âm hoặc bị hiểu sai. Tránh so sánh tổng thời gian của một nhóm trong một ngày với nhóm khác chỉ được thu thập trong vài phút.

## 7. Chú ý độ lệch tham số và kế hoạch thực thi

Fingerprint giúp gom cấu trúc truy vấn, nhưng các giá trị tham số khác nhau có thể dẫn đến khối lượng dữ liệu và kế hoạch thực thi khác nhau đáng kể.

Ví dụ, cùng mẫu truy vấn tìm đơn hàng theo trạng thái:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE status = ?;
~~~

Giá trị trạng thái phổ biến có thể khớp với phần lớn bảng, trong khi một trạng thái hiếm chỉ khớp với rất ít dòng. Cùng một fingerprint vì thế có thể có độ trễ và số dòng đọc rất khác nhau. Nếu chỉ xem số trung bình, nhóm phân tích có thể bỏ lỡ nhóm tham số gây ra phần lớn độ trễ.

Khi có thể, hãy phân tích thêm theo các chiều an toàn như:

- Plan ID hoặc biến thể kế hoạch thực thi.
- Nhóm độ chọn lọc của tham số, chẳng hạn phổ biến, trung bình và hiếm.
- Khoảng kích thước kết quả hoặc số dòng đọc.
- Loại thao tác nghiệp vụ hoặc endpoint gọi truy vấn.
- Thời điểm, mức tải và số phiên đồng thời.

Không cần lưu giá trị tham số thô để tạo các nhóm này. Có thể dùng phân loại, khoảng giá trị hoặc thống kê tổng hợp đã loại bỏ dữ liệu nhạy cảm. Với truy vấn có bind parameter, kế hoạch có thể được tái sử dụng cho nhiều giá trị; hành vi này phụ thuộc vào cơ chế tối ưu hóa của hệ quản trị. Khi nghi ngờ độ lệch tham số, cần kiểm tra kế hoạch thực tế và thống kê dữ liệu thay vì kết luận chỉ từ fingerprint.

Fingerprint cũng không thể hiện đầy đủ quan hệ giữa nhiều câu lệnh trong một giao dịch. Một câu UPDATE có thể chờ khóa do câu lệnh trước đó trong cùng giao dịch đã khóa bản ghi hoặc giữ khóa quá lâu; ví dụ một thao tác SELECT ... FOR UPDATE có thể khóa dòng tùy hệ quản trị và mức cô lập. Vì vậy, khi điều tra tranh chấp, cần kết hợp fingerprint với transaction ID, session, trace hoặc thông tin giao dịch phù hợp để tái dựng chuỗi thao tác.

## 8. Bảo vệ dữ liệu và kiểm soát chi phí thu thập

Log truy vấn có thể chứa dữ liệu cá nhân, thông tin tài khoản, địa chỉ, mã định danh, nội dung tìm kiếm hoặc dữ liệu nghiệp vụ nhạy cảm. Nếu ghi cả giá trị bind parameter, log có thể trở thành nơi lưu trữ dữ liệu nhạy cảm ngoài dự kiến.

Khi thiết kế thu thập:

- Ưu tiên lưu fingerprint và mẫu SQL đã loại bỏ literal; không ghi giá trị tham số thô nếu không có nhu cầu được phê duyệt.
- Nếu cần phân tích độ lệch tham số, dùng nhóm hoặc khoảng giá trị đã khử định danh thay vì lưu nguyên giá trị.
- Che hoặc loại bỏ token, mật khẩu, khóa truy cập và dữ liệu nhạy cảm khỏi log.
- Giới hạn quyền đọc log và dashboard theo vai trò; ghi nhận truy cập khi phù hợp.
- Đặt thời hạn lưu trữ, cơ chế luân chuyển và xóa dữ liệu theo chính sách của tổ chức.
- Bảo vệ dữ liệu thu thập khi truyền và khi lưu trữ.
- Theo dõi dung lượng log, CPU, I/O và ảnh hưởng đến độ trễ do chính công cụ quan sát tạo ra.

Mức chi tiết càng cao thường càng tốn tài nguyên và dung lượng. Có thể dùng thống kê tổng hợp liên tục, còn log chi tiết hoặc sampling theo yêu cầu chỉ bật trong khoảng thời gian điều tra. Cần thử cấu hình thu thập trên môi trường phù hợp và quan sát tác động trước khi mở rộng phạm vi.

## 9. Những sai lệch thường gặp khi xây dựng tập truy vấn

Một số lỗi có thể khiến kết quả phân tích workload không phản ánh thực tế:

1. **Chỉ thu thập truy vấn chậm:** bỏ qua truy vấn nhanh nhưng có tần suất rất cao, khiến tổng chi phí bị đánh giá thấp.
2. **Quan sát trong thời gian quá ngắn:** không thấy giờ cao điểm, tác vụ định kỳ hoặc workload cuối tuần.
3. **Không ghi phạm vi thời gian:** so sánh các bộ đếm được thu thập trong những khoảng thời gian khác nhau.
4. **Gom fingerprint quá rộng:** chuẩn hóa mất điều kiện lọc hoặc cấu trúc phép nối, khiến các truy vấn khác chi phí bị nhập làm một.
5. **Gom fingerprint quá hẹp:** comment, literal hoặc tên định danh động khiến một mẫu bị tách thành nhiều nhóm.
6. **Chỉ nhìn trung bình:** bỏ qua p95/p99 và độ lệch tham số.
7. **Nhầm tổng thời gian với thời gian đồng hồ:** cộng thời gian thực thi của các truy vấn song song rồi coi đó là thời gian toàn hệ thống đã trôi qua.
8. **Bỏ qua ngữ cảnh ứng dụng:** không biết truy vấn đến từ endpoint, tác vụ nền hay dịch vụ nào.
9. **Ghi tham số nhạy cảm:** tạo rủi ro bảo mật và quyền riêng tư không cần thiết.
10. **Bỏ qua overhead thu thập:** log hoặc tracing quá chi tiết làm tăng tải và ảnh hưởng chính workload đang đo.

Khi thấy số liệu bất thường, hãy kiểm tra nguồn, cách chuẩn hóa, khoảng thời gian và trạng thái reset trước khi đưa ra kết luận. Một fingerprint có số lần gọi bằng không hoặc giảm đột ngột có thể do ứng dụng ngừng phát sinh truy vấn, nhưng cũng có thể do bộ đếm vừa bị reset hoặc dữ liệu bị loại khỏi cửa sổ lưu trữ.

## 10. Quy trình thực hành từ thu thập đến ưu tiên tối ưu

Có thể áp dụng quy trình sau để xây dựng tập truy vấn phục vụ điều tra hiệu năng:

1. **Xác định phạm vi:** chọn cơ sở dữ liệu, dịch vụ, schema, endpoint hoặc loại giao dịch cần quan sát; xác định giờ cao điểm và thời lượng thu thập.
2. **Chọn nguồn dữ liệu:** ưu tiên thống kê digest hoặc query store của hệ quản trị nếu phù hợp; bổ sung slow log, APM hoặc trace để có ngữ cảnh.
3. **Thiết lập mức thu thập:** chọn khoảng lấy mẫu, ngưỡng log và trường dữ liệu cần thiết; kiểm tra quyền truy cập, thời hạn lưu và tác động tài nguyên.
4. **Chuẩn hóa và tạo fingerprint:** xác minh một số câu SQL gốc đại diện được gom đúng mẫu; kiểm tra những trường hợp literal, comment, danh sách IN và SQL động.
5. **Tổng hợp theo khoảng thời gian:** tính số lần chạy, tổng thời gian, độ trễ, số dòng đọc, lỗi và thời gian chờ; ghi rõ thời điểm reset hoặc thay đổi cấu hình.
6. **Phân nhóm theo ngữ cảnh:** tách theo ứng dụng, endpoint, database, plan ID hoặc nhóm tham số khi có bằng chứng cho thấy cần thiết.
7. **Xếp hạng workload:** xem đồng thời tổng thời gian, p95/p99, tần suất, lượng dữ liệu đọc, lỗi và thời gian chờ.
8. **Chọn mẫu cần điều tra:** đọc kế hoạch thực thi, thống kê và dữ liệu liên quan cho các fingerprint ưu tiên; đưa ra giả thuyết có thể kiểm chứng.
9. **Đo lại sau thay đổi:** thu thập lại trong điều kiện tương đương và so sánh cùng các chiều đo; xác nhận kết quả nghiệp vụ và tải của các truy vấn liên quan.

### Ví dụ: chọn truy vấn cần điều tra

Một dịch vụ bán hàng có hai fingerprint nổi bật trong một giờ cao điểm:

| Mẫu | Số lần gọi | Trung bình mỗi lần | Tổng thời gian tích lũy |
| --- | ---: | ---: | ---: |
| Tìm đơn hàng theo khách hàng | 30.000 | 12 ms | 360 s |
| Báo cáo tổng hợp doanh thu | 20 | 3.000 ms | 60 s |

Mẫu tìm đơn hàng có tổng thời gian tích lũy cao hơn vì được gọi thường xuyên. Nhóm phát triển có thể kiểm tra số lượt gọi trên mỗi request, khả năng dùng chỉ mục và số dòng phải đọc. Mẫu báo cáo có độ trễ mỗi lần cao hơn; nếu đây là chức năng có SLA nghiêm ngặt, vẫn cần điều tra kế hoạch tổng hợp, phạm vi dữ liệu và lịch chạy.

Tiếp theo, nhóm kiểm tra phân vị và thời gian chờ của từng fingerprint. Nếu truy vấn tìm đơn hàng có p99 cao khi một số khách hàng có lượng đơn rất lớn, cần phân tích độ lệch tham số. Nếu báo cáo chậm do I/O hoặc tạo bảng tạm, cần xem kế hoạch và tài nguyên. Việc ưu tiên cuối cùng phụ thuộc vào ảnh hưởng nghiệp vụ, mục tiêu dịch vụ và khả năng cải thiện có thể đo được.

## 11. Kết quả cần có sau khi thu thập

Một đợt thu thập workload tốt nên tạo ra được các đầu ra có thể dùng lại:

- Danh mục fingerprint cùng mẫu SQL chuẩn hóa và mô tả nguồn phát sinh.
- Thống kê theo khoảng thời gian về tần suất, tổng thời gian, phân vị độ trễ, lượng dữ liệu đọc/ghi, lỗi và thời gian chờ.
- Danh sách các fingerprint đứng đầu theo từng tiêu chí ưu tiên.
- Thông tin về plan ID, nhóm tham số hoặc ngữ cảnh giao dịch khi cần giải thích khác biệt.
- Ghi chú về phạm vi thu thập, nguồn dữ liệu, thời điểm reset, sampling và giới hạn của số liệu.
- Quy tắc bảo vệ dữ liệu, quyền truy cập và thời hạn lưu log.

Những đầu ra này tạo đường cơ sở để các bước sau kiểm tra kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Khi thay đổi chỉ mục, SQL hoặc cấu hình, có thể thu thập lại cùng phạm vi để xác định fingerprint nào được cải thiện, nhóm nào bị ảnh hưởng và liệu chi phí có chuyển sang một phần khác của workload hay không.

## 12. Nguyên tắc cần ghi nhớ

- Thu thập workload trong khoảng thời gian đại diện và ghi rõ phạm vi, nguồn cùng thời điểm đo.
- Dùng query fingerprint để gom các câu lệnh cùng cấu trúc, đồng thời giữ mẫu chuẩn hóa để kiểm tra cách nhóm.
- Chọn quy tắc chuẩn hóa phù hợp với hệ quản trị; giữ lại các thành phần SQL có ảnh hưởng đến hình dạng và chi phí truy vấn.
- Đánh giá cả tần suất, tổng thời gian, phân vị độ trễ, lượng dữ liệu đọc, tài nguyên, lỗi và thời gian chờ.
- Tách nhóm theo plan ID, độ chọn lọc tham số hoặc ngữ cảnh khi một fingerprint có hành vi không đồng nhất.
- Bảo vệ giá trị tham số và dữ liệu nhạy cảm; giới hạn chi phí của hoạt động quan sát.
- Dùng số liệu đã thu thập để hình thành giả thuyết, sau đó kiểm tra bằng kế hoạch thực thi và phép đo trước/sau.

Nhóm truy vấn theo fingerprint biến hàng loạt câu SQL rời rạc thành bức tranh workload có thể phân tích. Khi biết mẫu nào xuất hiện thường xuyên, mẫu nào tiêu tốn nhiều thời gian và mẫu nào gây chờ tài nguyên, nhóm phát triển có cơ sở để chọn đúng truy vấn cần điều tra và đánh giá kết quả tối ưu một cách nhất quán.
