# Chọn mô hình tải và dữ liệu phù hợp với nhu cầu sử dụng

Một bài kiểm thử hiệu năng chỉ có ý nghĩa khi tải tạo ra gần với cách hệ thống được sử dụng và dữ liệu phản ánh được những đặc điểm ảnh hưởng đến xử lý. Chạy hàng nghìn yêu cầu giống hệt nhau trên một bộ dữ liệu nhỏ có thể tạo ra con số thông lượng đẹp, nhưng không cho biết hệ thống sẽ hoạt động thế nào khi nhiều người dùng thực hiện các hành trình khác nhau, dữ liệu tăng lên, có giờ cao điểm hoặc một số bản ghi được truy cập thường xuyên hơn phần còn lại.

Vì vậy, trước khi chọn công cụ hoặc tăng số người dùng ảo, nhóm cần xây dựng **mô hình tải (workload model)** và **mô hình dữ liệu kiểm thử (test data model)** dựa trên nhu cầu sử dụng. Mô hình tải mô tả ai đang dùng hệ thống, làm gì, với tần suất nào và trong điều kiện nào. Mô hình dữ liệu mô tả quy mô, cấu trúc, phân bố, quan hệ và vòng đời của dữ liệu mà các hành động đó đọc hoặc ghi.

Hai mô hình cần được thiết kế cùng nhau. Một luồng truy vấn tìm kiếm với tải cao sẽ có kết quả rất khác khi dữ liệu chỉ có vài trăm bản ghi so với hàng chục triệu bản ghi, hoặc khi mọi yêu cầu đều truy cập cùng một khóa so với khi truy cập phân bố rộng.

## 1. Mô hình tải và dữ liệu là gì?

### 1.1. Mô hình tải

Mô hình tải mô tả cách người dùng, hệ thống hoặc tác vụ nền tạo ra công việc đối với hệ thống trong một khoảng thời gian. Nó thường xác định:

- Nhóm người dùng hoặc tác nhân tạo tải.
- Hành trình và loại thao tác được thực hiện.
- Tỷ lệ phân bố giữa các thao tác.
- Tốc độ yêu cầu đến, số phiên đồng thời và thời gian suy nghĩ giữa các thao tác.
- Thời lượng phiên và nhịp hoạt động theo thời gian.
- Mức tải bình thường, cao điểm, đột biến và tải kéo dài.
- Kích thước request/response, dữ liệu đọc/ghi và các phụ thuộc được gọi.
- Điều kiện mạng, vùng địa lý, thiết bị hoặc cấu hình có ảnh hưởng.

Mô hình tải không chỉ là một con số như "1.000 người dùng đồng thời". Hai hệ thống có cùng số người dùng đồng thời nhưng hành vi rất khác nếu một nhóm chỉ xem trang tĩnh, còn nhóm kia liên tục tìm kiếm, tạo giao dịch và tải báo cáo.

### 1.2. Mô hình dữ liệu kiểm thử

Mô hình dữ liệu kiểm thử xác định dữ liệu cần có để mô phỏng đúng điều kiện mà workload sẽ gặp. Các yếu tố thường gồm:

- Số lượng bản ghi và tốc độ tăng dữ liệu.
- Phân bố giá trị, độ đa dạng và độ lệch giữa các nhóm.
- Quan hệ giữa các bảng, đối tượng và tài khoản.
- Kích thước bản ghi, payload và tệp đính kèm.
- Dữ liệu mới, cũ, hoạt động, lưu trữ và hết hạn.
- Các khóa thường được truy cập, dữ liệu nóng và dữ liệu lạnh.
- Số lượng người dùng, tenant, sản phẩm, đơn hàng hoặc tài nguyên.
- Ràng buộc toàn vẹn, dữ liệu trùng, thiếu hoặc ở trạng thái biên.

Mục tiêu không phải tạo dữ liệu ngẫu nhiên thật nhiều. Dữ liệu cần đủ đại diện để kích hoạt các đường xử lý, chỉ mục, cache, phân vùng, ràng buộc và hành vi lưu trữ giống điều kiện sử dụng dự kiến.

## 2. Bắt đầu từ nhu cầu sử dụng và mục tiêu chất lượng

Mô hình tải nên xuất phát từ câu hỏi nghiệp vụ: hệ thống phục vụ ai, các tác vụ nào quan trọng, khi nào nhu cầu tăng và mức dịch vụ nào người dùng cần. Không nên bắt đầu bằng một con số tải tùy ý chỉ vì công cụ có thể tạo ra con số đó.

### 2.1. Thu thập thông tin về cách sử dụng

Nguồn thông tin có thể gồm:

- Số người dùng hoạt động theo ngày, giờ hoặc mùa vụ.
- Số phiên đồng thời và thời lượng phiên.
- Số giao dịch hoặc tác vụ theo từng loại.
- Tỷ lệ đọc/ghi và tỷ lệ giữa các hành trình.
- Phân bố request theo endpoint, dịch vụ và nhóm khách hàng.
- Thời điểm cao điểm, sự kiện khuyến mãi, chốt sổ hoặc nhập dữ liệu hàng loạt.
- Kích thước dữ liệu và mức tăng trưởng theo thời gian.
- Log, metric, trace và báo cáo sử dụng từ hệ thống hiện tại.
- Dự báo tăng trưởng, chiến dịch mới hoặc thay đổi sản phẩm.

Nếu sản phẩm chưa có dữ liệu vận hành, hãy làm việc với chủ sản phẩm, nghiệp vụ, kiến trúc sư và vận hành để đưa ra giả định có căn cứ. Ghi rõ giả định, nguồn, thời điểm và người xác nhận. Khi có dữ liệu thật, cập nhật mô hình thay vì tiếp tục dùng giả định ban đầu.

### 2.2. Xác định mục tiêu chất lượng

Mục tiêu hiệu năng và năng lực cần gắn với trải nghiệm hoặc nhu cầu vận hành. Ví dụ:

- 95% yêu cầu tìm kiếm hoàn tất trong ngưỡng thời gian đã cam kết ở tải bình thường.
- Luồng tạo đơn duy trì tỷ lệ lỗi dưới ngưỡng khi có đợt cao điểm.
- Hệ thống xử lý được lượng giao dịch dự báo trong một khoảng thời gian mà không làm backlog tăng liên tục.
- Sau một đợt tăng tải đột biến, hàng đợi và độ trễ trở lại mức bình thường trong thời gian mục tiêu.
- Dữ liệu tăng theo quy mô dự kiến không làm truy vấn hoặc tác vụ nền vượt ngưỡng vận hành.

Mục tiêu nên chỉ rõ:

1. Hành trình hoặc chức năng nào được đo.
2. Mức tải và phân bố thao tác.
3. Quy mô và trạng thái dữ liệu.
4. Môi trường, cấu hình và thời lượng đo.
5. Chỉ số, phân vị và ngưỡng chấp nhận.
6. Điều kiện thất bại và người quyết định khi có rủi ro còn lại.

### 2.3. Phân biệt nhu cầu hiện tại và năng lực mục tiêu

Nhu cầu hiện tại mô tả cách hệ thống đang được sử dụng. Năng lực mục tiêu có thể cao hơn để chuẩn bị tăng trưởng, mùa vụ hoặc chiến dịch. Hai giá trị này cần được ghi riêng.

Ví dụ, nếu lưu lượng giờ cao điểm hiện tại là 400 yêu cầu/giây, mục tiêu năng lực có thể cần hỗ trợ 600 yêu cầu/giây để có dự phòng tăng trưởng. Con số mục tiêu cần dựa trên dự báo và quyết định kinh doanh, không phải chỉ nhân một hệ số tùy ý.

## 3. Những đại lượng quan trọng trong mô hình tải

### 3.1. Tốc độ yêu cầu đến (arrival rate)

Arrival rate là số yêu cầu hoặc công việc mới đến hệ thống trong một đơn vị thời gian, thường biểu diễn bằng request/second, transaction/minute hoặc job/hour.

Đại lượng này mô tả nhịp công việc hệ thống phải tiếp nhận. Với hệ thống nhận sự kiện hoặc tác vụ nền, cần đo cả tốc độ sự kiện đến và tốc độ xử lý.

### 3.2. Số người dùng hoặc phiên đồng thời (concurrency)

Concurrency là số người dùng, phiên hoặc thao tác đang hoạt động cùng lúc. Nó ảnh hưởng đến số kết nối, bộ nhớ phiên, khóa, tài nguyên ứng dụng và khả năng tranh chấp dữ liệu.

Không thể mặc định 1.000 người dùng đồng thời tương đương 1.000 request mỗi giây. Người dùng có thể đọc một trang, chờ vài giây rồi mới thực hiện thao tác tiếp theo.

### 3.3. Thông lượng (throughput)

Throughput là lượng công việc hệ thống hoàn tất trong một đơn vị thời gian, ví dụ request/second, giao dịch/phút hoặc bản ghi/giây.

Arrival rate và throughput có thể khác nhau. Nếu công việc đến nhanh hơn khả năng xử lý, hàng đợi và độ trễ tăng. Khi hệ thống ổn định, throughput có thể xấp xỉ arrival rate; khi hệ thống bão hòa hoặc lỗi, throughput có thể chững lại trong khi backlog tiếp tục tăng.

### 3.4. Thời gian suy nghĩ và thời lượng phiên

Think time là khoảng thời gian người dùng chờ hoặc đọc trước khi thực hiện thao tác tiếp theo. Session duration là thời gian một phiên hoạt động. Hai đại lượng này giúp mô phỏng hành vi người dùng thực tế thay vì gửi request liên tục không nghỉ.

Ví dụ, người dùng có thể mở danh mục, đọc sản phẩm trong 10–30 giây, thêm sản phẩm vào giỏ, rồi chuyển sang thanh toán. Một kịch bản chỉ gọi API thêm giỏ hàng liên tục sẽ không phản ánh hành trình này.

### 3.5. Tỷ lệ thao tác và kích thước dữ liệu

Workload cần chỉ rõ tỷ lệ giữa các thao tác, chẳng hạn 60% đọc danh mục, 20% tìm kiếm, 15% xem chi tiết và 5% tạo đơn. Tỷ lệ phải dựa trên dữ liệu sử dụng hoặc giả định đã xác nhận.

Kích thước payload cũng ảnh hưởng đến CPU, mạng, bộ nhớ và thời gian xử lý. Cần mô phỏng nhiều kích thước hợp lý, không chỉ một request nhỏ cố định.

### 3.6. Quan hệ giữa concurrency, arrival rate và thời gian đáp ứng

Trong một hệ thống ổn định, có thể dùng định luật Little để ước lượng quan hệ:

\[
L = \lambda W
\]

Trong đó:

- \(L\): số công việc trung bình đang ở trong hệ thống.
- \(\lambda\): tốc độ công việc hoàn tất hoặc đến trong điều kiện ổn định.
- \(W\): thời gian trung bình một công việc ở trong hệ thống.

Ví dụ, nếu hệ thống xử lý trung bình 100 request/giây và thời gian một request ở trong hệ thống là 0,5 giây, số request trung bình đang được xử lý hoặc chờ có thể vào khoảng 50. Đây là quan hệ trung bình trong điều kiện ổn định; không dùng công thức này để thay thế đo lường phân vị hoặc phân tích hệ thống đang tăng backlog.

## 4. Chọn mô hình phát tải phù hợp

### 4.1. Mô hình tải mở (open workload)

Trong mô hình tải mở, bộ phát tải tạo yêu cầu theo tốc độ đến đã định, tương đối độc lập với thời gian phản hồi của hệ thống. Nếu hệ thống chậm, yêu cầu vẫn tiếp tục đến theo lịch.

Mô hình này phù hợp để mô phỏng hệ thống nhận sự kiện, API công khai hoặc lưu lượng đến từ lượng người dùng bên ngoài. Nó giúp phát hiện khả năng hệ thống chịu tải khi arrival rate tăng và backlog hình thành.

Cần bảo đảm công cụ phát tải đủ năng lực tạo tải. Nếu chính load generator bị bão hòa, kết quả đo có thể thấp hơn workload dự kiến.

### 4.2. Mô hình tải đóng (closed workload)

Trong mô hình tải đóng, số người dùng ảo hoặc phiên đồng thời được giữ ở một mức xác định. Mỗi người dùng thực hiện thao tác, chờ phản hồi và think time rồi mới tiếp tục.

Mô hình này phù hợp khi muốn mô phỏng một nhóm người dùng có số lượng phiên hoạt động giới hạn, chẳng hạn nhân viên nội bộ hoặc người dùng đăng nhập trong một hệ thống nghiệp vụ.

Một điểm cần lưu ý: khi hệ thống chậm, người dùng ảo trong mô hình đóng cũng gửi yêu cầu mới chậm hơn. Vì vậy, arrival rate có thể giảm theo thời gian phản hồi và che khuất tình trạng quá tải nếu chỉ nhìn vào số phiên đồng thời.

### 4.3. Khi nào dùng từng mô hình?

| Nhu cầu | Mô hình phù hợp | Lưu ý |
|---|---|---|
| API nhận lưu lượng bên ngoài theo tốc độ thay đổi | Open | Kiểm soát arrival rate và backlog |
| Hệ thống xử lý sự kiện hoặc message queue | Open | Mô phỏng tốc độ phát sinh sự kiện và burst |
| Ứng dụng có nhóm phiên đăng nhập giới hạn | Closed | Mô phỏng think time và hành trình |
| Portal nội bộ với số nhân viên đồng thời dự kiến | Closed hoặc kết hợp | Xem xét thời gian làm việc và tác vụ nền |
| Nền tảng vừa có người dùng vừa có tác vụ nền | Kết hợp | Phát tải riêng cho tương tác và công việc nền |

Trong thực tế có thể kết hợp mô hình mở và đóng: một phần tải mô phỏng phiên người dùng, phần khác mô phỏng webhook, sự kiện hoặc batch job đến theo lịch.

## 5. Các hồ sơ tải thường dùng

Không có một bài kiểm thử duy nhất trả lời mọi câu hỏi về hiệu năng. Hãy chọn hồ sơ tải theo mục tiêu:

| Hồ sơ | Mục tiêu | Cách tạo tải |
|---|---|---|
| Baseline/normal | Xác định hành vi ở mức sử dụng bình thường | Tải ổn định theo hồ sơ người dùng thường gặp |
| Peak | Kiểm tra mức cao điểm dự kiến | Tăng đến tải cao điểm đã dự báo và giữ ổn định |
| Stress | Tìm giới hạn và cách hệ thống suy giảm | Tăng tải vượt mức mục tiêu đến khi đạt điểm bão hòa hoặc điều kiện dừng |
| Spike/burst | Kiểm tra phản ứng với tải tăng đột ngột | Tăng nhanh từ mức thấp lên mức cao trong thời gian ngắn |
| Soak/endurance | Phát hiện rò rỉ bộ nhớ, tích tụ backlog hoặc suy giảm dài hạn | Duy trì tải đại diện trong nhiều giờ hoặc lâu hơn |
| Scalability | Đánh giá khả năng tăng năng lực khi thêm tài nguyên | Tăng tải và thay đổi số instance hoặc tài nguyên theo kế hoạch |
| Capacity | Xác định năng lực tối đa đáp ứng ngưỡng dịch vụ | Tăng dần tải và ghi nhận ngưỡng đạt mục tiêu |
| Recovery | Xác minh khả năng trở lại sau quá tải hoặc gián đoạn | Giảm tải hoặc khôi phục phụ thuộc sau khi tạo sự cố |

Các bài stress hoặc spike cần có điều kiện dừng và môi trường được kiểm soát để tránh ảnh hưởng hệ thống khác. Không nên thực hiện tải vượt mức trên production nếu chưa có kế hoạch, phê duyệt và cơ chế bảo vệ phù hợp.

### 5.1. Ví dụ đường tải

Một hồ sơ peak có thể gồm:

1. Warm-up: bắt đầu ở tải thấp để khởi tạo kết nối và cache.
2. Ramp-up: tăng dần đến mức cao điểm.
3. Steady state: giữ tải trong khoảng đo đủ dài.
4. Ramp-down: giảm tải có kiểm soát.
5. Cool-down: quan sát backlog và tài nguyên trở lại bình thường.

~~~mermaid
flowchart LR
    A["Warm-up"] --> B["Ramp-up"] --> C["Steady state"] --> D["Ramp-down"] --> E["Cool-down"]
~~~

## 6. Xây dựng phân bố hành vi thay vì lặp một request

Một mô hình tải đại diện cần thể hiện hỗn hợp hành vi và tần suất của từng hành trình.

Ví dụ cho một cửa hàng trực tuyến, giả sử số liệu sử dụng cho thấy phần lớn phiên tập trung vào xem và tìm kiếm sản phẩm, một phần nhỏ hơn thêm hàng vào giỏ và một tỷ lệ nhỏ hoàn tất đơn:

| Hành trình | Tỷ lệ giả định trong workload | Tác động chính |
|---|---:|---|
| Xem trang chủ/danh mục | 35% | Cache, truy vấn danh mục, phân phối nội dung |
| Tìm kiếm và lọc | 25% | Search index, CPU, truy vấn và cache |
| Xem chi tiết sản phẩm | 20% | Đọc dữ liệu, hình ảnh và tồn kho |
| Thêm/cập nhật giỏ hàng | 12% | Ghi dữ liệu, session và tính toán |
| Tạo đơn và thanh toán thử nghiệm | 6% | Ghi giao dịch, tích hợp và nhất quán |
| Xem lịch sử đơn | 2% | Truy vấn dữ liệu theo người dùng |

Các tỷ lệ trên chỉ là ví dụ minh họa, không phải chuẩn chung. Nhóm cần lấy tỷ lệ thực tế từ analytics hoặc xác nhận với chủ sản phẩm. Nếu không có dữ liệu, ghi rõ giả định và chạy phân tích độ nhạy với một số phân bố khác nhau.

Mỗi hành trình cần xác định:

- Số bước và thứ tự thao tác.
- Think time giữa các bước.
- Tỷ lệ hoàn tất, bỏ dở và thử lại.
- Tỷ lệ lỗi nghiệp vụ được kỳ vọng.
- Kích thước request và response.
- Phụ thuộc được gọi và các tác vụ nền phát sinh.
- Dữ liệu được đọc, tạo mới hoặc cập nhật.

Không nên tạo mọi phiên giống hệt nhau. Người dùng thực tế có thể tìm sản phẩm khác nhau, truy cập các danh mục khác nhau, dùng các vai trò và tenant khác nhau, hoặc có tỷ lệ bỏ dở khác nhau.

## 7. Chọn dữ liệu kiểm thử đại diện

### 7.1. Quy mô dữ liệu

Dữ liệu cần đủ lớn để phản ánh chi phí xử lý ở quy mô dự kiến:

- Số lượng bản ghi trong bảng hoặc collection chính.
- Số quan hệ giữa các đối tượng.
- Số lượng người dùng, tenant, sản phẩm và giao dịch.
- Kích thước bản ghi và payload.
- Số lượng tệp, kích thước tệp và loại nội dung.
- Tốc độ tăng dữ liệu theo ngày, tháng hoặc năm.

Một cơ sở dữ liệu chỉ có vài trăm bản ghi không thể đại diện cho hệ thống dự kiến có hàng chục triệu bản ghi nếu truy vấn, chỉ mục, phân vùng hoặc dung lượng lưu trữ phụ thuộc vào quy mô.

### 7.2. Phân bố và độ lệch dữ liệu

Không chỉ số lượng, phân bố dữ liệu cũng ảnh hưởng mạnh đến hiệu năng:

- Một số người dùng hoặc tenant tạo phần lớn lưu lượng.
- Một số sản phẩm hoặc bản ghi được truy cập thường xuyên hơn phần còn lại.
- Có bản ghi chứa nhiều quan hệ hoặc lịch sử dài.
- Có giá trị null, trường tùy chọn, văn bản dài hoặc danh sách lớn.
- Có nhóm dữ liệu cũ, ít được truy cập và nhóm dữ liệu mới, thường xuyên thay đổi.
- Một số khóa có thể trở thành điểm nóng khi nhiều thao tác đồng thời.

Nếu dữ liệu kiểm thử phân bố đều trong khi production có độ lệch lớn, nhóm có thể bỏ sót hot key, tranh chấp khóa hoặc vấn đề phân vùng.

### 7.3. Quan hệ và tính toàn vẹn

Dữ liệu cần giữ các quan hệ nghiệp vụ hợp lệ: người dùng thuộc tenant, đơn hàng có dòng hàng, giao dịch liên kết với đơn, sản phẩm có danh mục và tồn kho. Đồng thời cần có một số tình huống biên có kiểm soát để kiểm tra truy vấn và xử lý dữ liệu bất thường.

Không tạo dữ liệu lớn bằng cách nhân bản bản ghi mà không điều chỉnh khóa, quan hệ hoặc phân bố. Cách nhân bản đơn giản có thể làm chỉ mục và cache có đặc tính khác thực tế, hoặc tạo dữ liệu không hợp lệ.

### 7.4. Thời gian và vòng đời

Một hệ thống có thể xử lý khác nhau với dữ liệu mới và cũ. Cần xem xét:

- Bản ghi mới được tạo trong lúc kiểm thử.
- Bản ghi cũ có lịch sử hoặc nhiều phiên bản.
- Dữ liệu hết hạn và tác vụ dọn dẹp.
- Dữ liệu lưu trữ lâu dài và truy vấn lịch sử.
- Timestamp, múi giờ, ngày chốt sổ và thời điểm hiệu lực.
- Cache nóng/lạnh và chỉ mục được làm mới.

Ví dụ, truy vấn lịch sử đơn hàng của một khách có 3 đơn khác với khách có 20.000 đơn. Cần có dữ liệu cho cả nhóm phổ biến và nhóm có lịch sử lớn nếu đó là tình huống cần hỗ trợ.

## 8. Kết hợp mô hình tải và dữ liệu

Mô hình tải và mô hình dữ liệu cần được thiết kế đồng bộ. Với mỗi hành trình, xác định thao tác đọc/ghi và tập dữ liệu mà nó sử dụng.

| Hành trình | Dữ liệu cần có | Điều cần mô phỏng |
|---|---|---|
| Tìm kiếm sản phẩm | Danh mục lớn, phân bố từ khóa, sản phẩm phổ biến và ít phổ biến | Tỷ lệ cache hit, độ dài từ khóa, bộ lọc và phân trang |
| Xem chi tiết | Sản phẩm, hình ảnh, biến thể, tồn kho và đánh giá | Bản ghi nóng/lạnh, payload và quan hệ |
| Thêm giỏ hàng | Nhiều người dùng, giỏ hàng khác nhau, số lượng và giá | Cập nhật đồng thời, session và xung đột |
| Tạo đơn | Khách hàng, địa chỉ, giá, khuyến mãi và tồn kho | Ghi dữ liệu, transaction, kiểm tra ràng buộc |
| Thanh toán | Đơn hàng và giao dịch thử nghiệm | Callback, retry, trạng thái và idempotency |
| Xem lịch sử | Khách có số lượng đơn khác nhau và lịch sử dài | Truy vấn phân trang, chỉ mục và dữ liệu cũ |

Khi tất cả người dùng ảo cùng đọc một bản ghi hoặc ghi vào một khóa, kết quả có thể phản ánh điểm nóng nhân tạo. Ngược lại, nếu mỗi người dùng có dữ liệu riêng biệt hoàn toàn, nhóm có thể bỏ qua tranh chấp và cache hit thực tế. Chọn phân bố dựa trên hành vi thật hoặc giả định đã được xác nhận.

## 9. Thiết kế dữ liệu cho cache và trạng thái lưu trữ

Dữ liệu kiểm thử có thể làm thay đổi mạnh tỷ lệ cache hit và hiệu năng:

- **Cache nóng:** một nhóm khóa nhỏ được truy cập thường xuyên.
- **Cache lạnh:** dữ liệu chưa được nạp hoặc đã hết hạn.
- **Cache hỗn hợp:** phân bố truy cập gồm cả khóa phổ biến và khóa ít dùng.
- **Cache invalidation:** dữ liệu thay đổi và cache cần được cập nhật hoặc vô hiệu hóa.
- **Cache stampede:** nhiều yêu cầu đồng thời cùng làm mới một khóa hết hạn.

Nếu mọi lượt chạy đều dùng cùng một khóa đã nằm trong cache, kết quả có thể lạc quan hơn thực tế. Hãy xác định rõ mục tiêu là đo cache warm, cold hay hỗn hợp, và kiểm soát bước warm-up.

Với cơ sở dữ liệu, cần chú ý kích thước bảng, độ chọn lọc của chỉ mục, số quan hệ, phân bố giá trị, transaction và cạnh tranh cập nhật. Dữ liệu phải đủ lớn để truy vấn đi qua các đường xử lý tương tự điều kiện mục tiêu.

## 10. Chuẩn bị, tạo và quản lý dữ liệu kiểm thử

### 10.1. Các cách tạo dữ liệu

- **Dữ liệu tổng hợp (synthetic data):** sinh từ quy tắc và phân bố đã xác định; phù hợp để tạo quy mô lớn và dữ liệu biên.
- **Dữ liệu đã ẩn danh hoặc giả danh:** chuyển đổi dữ liệu từ nguồn thật theo quy trình được phép để giữ một số đặc điểm phân bố.
- **Bộ dữ liệu tham chiếu:** tập dữ liệu nhỏ, ổn định để xác minh tính đúng đắn.
- **Dữ liệu được tạo theo hành trình:** chuẩn bị người dùng, đơn hàng, giao dịch và trạng thái theo kịch bản.
- **Dữ liệu phát sinh trong lúc chạy:** workload tạo bản ghi mới để mô phỏng tăng trưởng và ghi đồng thời.

Không dùng dữ liệu production có thông tin cá nhân hoặc bí mật nếu chưa có quyền, mục đích và biện pháp bảo vệ phù hợp. Dữ liệu giả danh vẫn có thể cần được quản lý như dữ liệu nhạy cảm tùy khả năng tái nhận dạng và chính sách tổ chức.

### 10.2. Tái lập và làm sạch

Để các lần chạy có thể so sánh:

- Dùng seed cố định cho dữ liệu ngẫu nhiên khi cần tái lập.
- Ghi phiên bản script tạo dữ liệu và cấu hình workload.
- Dùng định danh riêng cho từng lần chạy.
- Tạo snapshot hoặc quy trình reset có thể kiểm soát.
- Xác minh số lượng, quan hệ và phân bố sau khi tạo.
- Xác định dữ liệu nào được giữ lại và dữ liệu nào phải dọn.
- Tách dữ liệu giữa các bài kiểm thử để tránh tác động lẫn nhau.

Với dữ liệu lớn, nên chuẩn bị trước hoặc dùng snapshot để tránh thời gian tạo dữ liệu làm sai kết quả đo. Nếu mục tiêu bao gồm tốc độ nạp dữ liệu, hãy đo riêng giai đoạn đó.

### 10.3. Kiểm tra chất lượng dữ liệu

Trước khi chạy tải, xác minh:

- Số lượng bản ghi theo nhóm đúng với mô hình.
- Phân bố giá trị, tenant, người dùng và trạng thái gần với mục tiêu.
- Khóa ngoại và quan hệ hợp lệ.
- Các trường tùy chọn, giá trị biên và kích thước payload có đại diện.
- Dữ liệu nóng/lạnh và trạng thái cache đúng điều kiện.
- Dữ liệu không bị trùng ngoài dự kiến.
- Không có dữ liệu nhạy cảm ngoài phạm vi được phép.

Một bộ dữ liệu lớn nhưng sai quan hệ hoặc phân bố không giúp kiểm thử đáng tin cậy.

## 11. Xây dựng một workload profile có thể tái lập

Workload profile nên ghi lại các tham số chính để nhóm khác có thể chạy lại:

| Thành phần | Nội dung cần ghi |
|---|---|
| Mục tiêu | Câu hỏi hiệu năng hoặc năng lực cần trả lời |
| Hành trình | Các thao tác và tỷ lệ phân bố |
| Mô hình tải | Open, closed hoặc kết hợp |
| Arrival rate/concurrency | Mức tải theo từng giai đoạn |
| Think time/session | Khoảng chờ và thời lượng phiên |
| Ramp-up/steady/ramp-down | Cách thay đổi tải và thời gian giữ |
| Payload | Kích thước và phân bố request/response |
| Dữ liệu | Quy mô, phân bố, trạng thái và cách tạo |
| Môi trường | Phiên bản, cấu hình, tài nguyên và phụ thuộc |
| Chỉ số/ngưỡng | Latency, throughput, error rate, saturation và tiêu chí đạt |
| Điều kiện dừng | Ngưỡng lỗi, tài nguyên hoặc tác động cần dừng bài chạy |

Ví dụ một cấu hình minh họa có thể ghi dưới dạng:

~~~yaml
profile: ecommerce_peak_example
workload:
  model: mixed
  duration: 30m
  warmup: 5m
  steady_state: 20m
  ramp_down: 5m
  target_arrival_rate_rps: 250
  concurrent_sessions: 800
journeys:
  browse_catalog: 35
  search: 25
  view_product: 20
  update_cart: 12
  checkout: 6
  order_history: 2
data:
  users: 50000
  products: 200000
  orders: 5000000
  distribution: representative_skew
~~~

Các con số trong ví dụ chỉ nhằm minh họa cách ghi profile. Chúng không phải mức tải khuyến nghị cho mọi cửa hàng. Khi dùng thực tế, thay bằng số liệu sử dụng, dự báo và mục tiêu đã được chủ sở hữu xác nhận.

## 12. Đo lường kết quả và xác định ngưỡng

Trong khi chạy tải, không chỉ quan sát thời gian phản hồi trung bình. Cần kết hợp nhiều chỉ số:

- **Latency:** thời gian phản hồi ở p50, p90, p95, p99 hoặc phân vị phù hợp.
- **Throughput:** số request, giao dịch hoặc tác vụ hoàn tất trong một đơn vị thời gian.
- **Error rate:** tỷ lệ lỗi kỹ thuật và lỗi nghiệp vụ.
- **Concurrency và queue depth:** số phiên hoạt động và lượng công việc chờ.
- **Resource utilization:** CPU, bộ nhớ, disk I/O, network, connection pool và GC.
- **Database:** truy vấn chậm, lock, deadlock, connection, cache hit và I/O.
- **Cache:** hit ratio, miss, eviction, thời gian làm mới và stampede.
- **Background processing:** độ trễ hàng đợi, tốc độ xử lý và backlog.
- **Saturation:** dấu hiệu tài nguyên hoặc giới hạn đã đạt ngưỡng.

Ngưỡng chấp nhận nên dựa trên SLO/SLA, yêu cầu sản phẩm, mục tiêu năng lực và dữ liệu vận hành. Cần ghi rõ ngưỡng áp dụng trong giai đoạn steady state hay toàn bộ bài chạy, và cách xử lý outlier.

Một bài kiểm thử có thể có throughput cao nhưng p99 quá lớn; hoặc latency thấp nhưng tỷ lệ lỗi tăng. Đọc các chỉ số cùng nhau để tránh kết luận sai.

## 13. Quy trình xây dựng và thực hiện mô hình tải/dữ liệu

### Bước 1: Xác định câu hỏi cần trả lời

Ví dụ: hệ thống có chịu được lưu lượng cao điểm không, dữ liệu tăng lên có làm truy vấn chậm không, hay hàng đợi có xử lý kịp sự kiện trong giờ cao điểm?

### Bước 2: Thu thập hành vi sử dụng

Lấy số liệu analytics, log, metric, trace, dự báo và thông tin từ chủ sản phẩm. Nếu thiếu dữ liệu, ghi giả định và xác nhận với các bên liên quan.

### Bước 3: Chọn workload profile

Xác định hành trình, tỷ lệ thao tác, arrival rate, concurrency, think time, session, tải nền và các giai đoạn tăng/giảm tải. Chọn open, closed hoặc kết hợp.

### Bước 4: Xác định quy mô và phân bố dữ liệu

Chọn số lượng, quan hệ, độ lệch, kích thước, tuổi dữ liệu, hot/cold và dữ liệu biên. Đảm bảo dữ liệu phù hợp với các hành trình và truy vấn trong workload.

### Bước 5: Chuẩn bị môi trường và công cụ

Kiểm tra cấu hình ứng dụng, database, cache, broker, mạng và load generator. Ghi phiên bản, tài nguyên, giới hạn và khác biệt với production.

### Bước 6: Chạy thử và hiệu chỉnh

Chạy ở tải thấp để xác minh kịch bản, dữ liệu và chỉ số. Tăng tải từng bước, kiểm tra load generator có đủ năng lực và xác định hệ thống đang bị giới hạn ở đâu.

### Bước 7: Chạy profile mục tiêu

Thực hiện baseline, peak, spike, stress hoặc soak theo mục tiêu. Thu thập metric, log, trace và trạng thái dữ liệu trong toàn bộ quá trình.

### Bước 8: Phân tích và báo cáo

So sánh với ngưỡng, phân biệt lỗi ứng dụng với giới hạn môi trường hoặc công cụ. Ghi lại profile, dữ liệu, phiên bản, kết quả, điểm bão hòa và giới hạn của kết luận.

### Bước 9: Cập nhật mô hình

Khi có dữ liệu sử dụng mới, thay đổi sản phẩm hoặc dự báo tăng trưởng, cập nhật workload và dataset. Không để profile cũ trở thành chuẩn mặc định khi hành vi người dùng đã thay đổi.

## 14. Ví dụ: chọn tải và dữ liệu cho cửa hàng trực tuyến

Giả sử cửa hàng có nhu cầu bình thường trong ngày, giờ cao điểm buổi tối và các đợt khuyến mãi. Nhóm cần đánh giá khả năng tìm kiếm, xem sản phẩm, cập nhật giỏ hàng và thanh toán.

### 14.1. Xây dựng hồ sơ tải

| Kịch bản | Mục tiêu | Hồ sơ tải |
|---|---|---|
| Bình thường | Xác định hiệu năng cơ sở | Hỗn hợp hành trình theo tỷ lệ sử dụng trong ngày |
| Giờ cao điểm | Xác minh mục tiêu dịch vụ | Tăng dần đến arrival rate và concurrency cao điểm dự báo |
| Flash sale | Kiểm tra burst | Lượng truy cập tăng nhanh vào một nhóm sản phẩm phổ biến |
| Duy trì dài | Phát hiện suy giảm | Giữ workload đại diện trong nhiều giờ |
| Vượt tải | Xác định giới hạn và hành vi suy giảm | Tăng tải theo bậc đến khi ngưỡng dừng hoặc mục tiêu thất bại |

### 14.2. Chuẩn bị dữ liệu

- Tạo danh mục sản phẩm đủ lớn với phân bố giá, loại, trạng thái và mức phổ biến khác nhau.
- Tạo một nhóm sản phẩm nóng được nhiều phiên truy cập trong flash sale.
- Tạo người dùng và giỏ hàng riêng để mô phỏng hành vi đa dạng.
- Tạo lịch sử đơn hàng với phân bố từ ít đến rất nhiều đơn mỗi khách.
- Tạo dữ liệu tồn kho có mặt hàng sắp hết và mặt hàng có số lượng lớn.
- Tạo mã khuyến mãi hợp lệ, hết hạn, giới hạn lượt dùng và điều kiện áp dụng khác nhau.
- Chuẩn bị dữ liệu thanh toán thử nghiệm và trạng thái callback theo kịch bản.

### 14.3. Kiểm tra tính đại diện

Nếu flash sale chỉ có một sản phẩm nóng, nhóm cần xem xét liệu đó có đúng với chiến dịch dự kiến hay không. Nếu người dùng thực tế tập trung vào 10 sản phẩm phổ biến, workload cần phản ánh mức độ tập trung đó. Nếu mọi phiên đều dùng một tài khoản hoặc một giỏ hàng, kết quả có thể bị ảnh hưởng bởi khóa nóng và cache theo cách không đại diện.

Nhóm cần so sánh tỷ lệ truy cập, phân bố sản phẩm, số lượng bản ghi và tỷ lệ đọc/ghi với số liệu thực tế hoặc dự báo. Khi chưa có dữ liệu, nên chạy thêm profile nhạy cảm để hiểu kết quả thay đổi thế nào khi mức độ tập trung tăng hoặc giảm.

### 14.4. Kết quả cần quan sát

- p95/p99 của tìm kiếm và xem chi tiết.
- Tỷ lệ lỗi khi thêm giỏ và tạo đơn.
- Throughput giao dịch hoàn tất.
- CPU, bộ nhớ, database connection và cache hit.
- Lock hoặc tranh chấp tồn kho ở sản phẩm nóng.
- Độ trễ và backlog của tác vụ nền.
- Tỷ lệ giao dịch trùng hoặc trạng thái đơn không nhất quán.
- Thời gian hệ thống phục hồi sau burst.

## 15. Những sai lầm thường gặp

- **Chỉ dùng số người dùng đồng thời:** không mô tả được tốc độ yêu cầu, think time và hỗn hợp hành vi. Cần ghi cả concurrency, arrival rate và phân bố hành trình.
- **Lặp một request đơn giản:** bỏ qua hành trình, đọc/ghi, payload và phụ thuộc thực tế.
- **Dùng dữ liệu quá nhỏ:** cache và chỉ mục hoạt động khác với quy mô dự kiến.
- **Tạo dữ liệu hoàn toàn đồng đều:** không phản ánh hot key, tenant lớn hoặc phân bố lệch.
- **Chỉ kiểm tra tải trung bình:** bỏ qua peak, burst, soak và tăng trưởng.
- **Nhầm arrival rate với throughput:** hệ thống có thể tiếp nhận nhiều yêu cầu nhưng không xử lý kịp.
- **Không kiểm tra load generator:** công cụ phát tải có thể trở thành nút thắt.
- **Không ghi phiên bản profile và dataset:** kết quả giữa các lần chạy không thể so sánh đáng tin.
- **Bỏ qua cache warm/cold:** kết quả có thể chỉ phản ánh một trạng thái cache.
- **Dùng dữ liệu thật không kiểm soát:** tạo rủi ro quyền riêng tư và ảnh hưởng dữ liệu production.
- **Đặt ngưỡng không có căn cứ:** kết quả pass/fail không phản ánh nhu cầu sử dụng.
- **Không cập nhật mô hình:** workload và dữ liệu nhanh chóng lỗi thời khi sản phẩm tăng trưởng.

## 16. Checklist trước khi chạy kiểm thử tải

- [ ] Mục tiêu hiệu năng hoặc năng lực gắn với nhu cầu sử dụng và SLO/SLA.
- [ ] Nguồn số liệu và giả định về người dùng, giao dịch, mùa vụ đã được ghi.
- [ ] Workload xác định hành trình và tỷ lệ thao tác.
- [ ] Arrival rate, concurrency, think time và session duration được phân biệt rõ.
- [ ] Mô hình open/closed/kết hợp phù hợp với kiểu lưu lượng.
- [ ] Có profile bình thường, peak và các dạng tải khác theo rủi ro.
- [ ] Dữ liệu đủ quy mô, phân bố và quan hệ.
- [ ] Dữ liệu nóng/lạnh, tuổi dữ liệu và trạng thái cache phù hợp mục tiêu.
- [ ] Script tạo dữ liệu có phiên bản, seed và cách reset.
- [ ] Môi trường, cấu hình và load generator đã được kiểm tra.
- [ ] Có chỉ số latency theo phân vị, throughput, error rate và saturation.
- [ ] Có ngưỡng đạt, điều kiện dừng và kế hoạch thu thập bằng chứng.
- [ ] Dữ liệu nhạy cảm và tác động đến hệ thống thật được kiểm soát.
- [ ] Profile và dataset có thể tái lập và cập nhật khi nhu cầu thay đổi.

## 17. Luồng xây dựng mô hình tải và dữ liệu

~~~mermaid
flowchart TD
    A["Nhu cầu sử dụng và mục tiêu chất lượng"]
    B["Thu thập số liệu, dự báo và giả định"]
    C["Xây dựng workload<br/>Hành trình, tỷ lệ, arrival rate, concurrency"]
    D["Xây dựng dataset<br/>Quy mô, phân bố, quan hệ, vòng đời"]
    E["Đối chiếu workload với dữ liệu và môi trường"]
    F["Chạy thử và hiệu chỉnh"]
    G["Chạy profile tải mục tiêu"]
    H["Đo latency, throughput, lỗi và saturation"]
    I["Đánh giá ngưỡng và cập nhật mô hình"]
    A --> B --> C --> D --> E --> F --> G --> H --> I
    I -. "Số liệu sử dụng mới" .-> B
~~~

Một mô hình tải và dữ liệu tốt phản ánh được cách người dùng thực hiện công việc, nhịp công việc hệ thống phải tiếp nhận và đặc điểm dữ liệu mà các thao tác truy cập. Khi các giả định được ghi rõ, dữ liệu có thể tái lập và ngưỡng được liên kết với nhu cầu sử dụng, kết quả kiểm thử hiệu năng sẽ giúp nhóm hiểu năng lực thực tế, phát hiện điểm bão hòa và lập kế hoạch cải thiện có căn cứ.
