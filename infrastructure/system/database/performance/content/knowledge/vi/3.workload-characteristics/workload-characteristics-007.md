# Xây dựng tải đại diện từ luồng nghiệp vụ và dữ liệu thực tế

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Chuyển các luồng nghiệp vụ thành nhóm giao dịch và thao tác cơ sở dữ liệu có thể đo.
- Mô tả workload bằng tỷ lệ thao tác, tốc độ đến, mức đồng thời, đặc điểm dữ liệu và tính biến động theo thời gian.
- Tạo tập dữ liệu kiểm thử phản ánh quy mô, phân bố và mức tranh chấp của môi trường thực tế.
- Chọn mô hình phát tải phù hợp, nhận biết sai lệch do công cụ tạo tải và xây dựng kịch bản có thể tái lập.
- Dùng cùng một workload đại diện để tìm nút thắt và kiểm chứng thay đổi tối ưu cơ sở dữ liệu.

## 1. Workload đại diện là gì?

Workload (khối lượng công việc) là tập hợp các thao tác mà hệ thống phải xử lý trong một khoảng thời gian, cùng với cách các thao tác xuất hiện, dữ liệu chúng truy cập và mức độ cạnh tranh tài nguyên giữa chúng. Với cơ sở dữ liệu, workload gồm các câu truy vấn đọc, ghi, cập nhật, xóa, các giao dịch nhiều câu lệnh và tác vụ nền như đồng bộ, tổng hợp hoặc dọn dữ liệu.

Một workload đại diện mô phỏng được những đặc điểm quan trọng của hoạt động thật: luồng nghiệp vụ, tỷ lệ giao dịch, tốc độ yêu cầu, mức đồng thời, phân bố tham số, kích thước và độ lệch của dữ liệu, cũng như các đợt tăng tải. Mục tiêu là tạo điều kiện đủ gần với môi trường cần phục vụ để kết quả đo có thể dùng ra quyết định.

Chạy lặp đi lặp lại một câu `SELECT` đơn giản có thể hữu ích để kiểm tra một đường truy cập cụ thể, nhưng thường không đại diện cho tải của ứng dụng. Trong thực tế, một yêu cầu của người dùng có thể thực hiện nhiều truy vấn, cập nhật một số bảng, giữ khóa trong suốt giao dịch và cạnh tranh với các yêu cầu khác. Một workload thiếu các tương tác này có thể cho kết quả rất đẹp nhưng không dự đoán được hiệu năng khi vận hành.

Trong phạm vi DATABASE_PERFORMANCE, xây dựng workload là bước nền để đo tải, đọc kế hoạch thực thi, thống kê truy vấn và cơ chế truy cập dữ liệu. Chỉ khi đầu vào đo đủ sát hoạt động thực tế, ta mới có cơ sở đáng tin cậy để đánh giá chỉ mục, SQL, tranh chấp giao dịch, I/O và bộ nhớ.

## 2. Bắt đầu từ luồng nghiệp vụ

Không nên bắt đầu bằng cách chọn ngẫu nhiên một số câu SQL trong log. Hãy xác định người dùng và hệ thống đang làm gì, sau đó lần theo các thao tác dữ liệu được thực hiện trong mỗi luồng.

Ví dụ với một hệ thống bán hàng, các luồng có thể gồm:

1. **Duyệt và tìm sản phẩm:** đọc danh mục, lọc theo thuộc tính, sắp xếp và phân trang.
2. **Xem chi tiết sản phẩm:** đọc một sản phẩm, giá, tồn kho hiển thị và thông tin liên quan.
3. **Quản lý giỏ hàng:** đọc giỏ, thêm hoặc đổi số lượng mặt hàng, tính lại tổng tiền.
4. **Đặt hàng:** kiểm tra tồn kho, tạo đơn và chi tiết đơn, ghi nhận thanh toán hoặc trạng thái, cập nhật tồn kho trong các giao dịch phù hợp.
5. **Xử lý nền:** gửi sự kiện, cập nhật chỉ mục tìm kiếm, tổng hợp báo cáo hoặc đối soát.

Mỗi luồng cần được mô tả ở hai cấp:

- **Giao dịch nghiệp vụ:** hành động có ý nghĩa với người dùng hoặc hệ thống, chẳng hạn `place_order`.
- **Thao tác cơ sở dữ liệu:** các câu SQL hoặc nhóm câu lệnh thực tế phát sinh trong giao dịch đó, chẳng hạn đọc tồn kho, chèn đơn hàng, chèn các dòng hàng và cập nhật số lượng.

Phân biệt hai cấp này rất quan trọng. Tỷ lệ 10% giao dịch đặt hàng không có nghĩa chỉ 10% câu SQL là thao tác ghi. Một lần đặt hàng có thể tạo nhiều câu lệnh và giữ khóa lâu hơn một lần xem chi tiết. Khi phân tích, hãy theo dõi cả tỷ lệ giao dịch nghiệp vụ lẫn số lượng và loại thao tác cơ sở dữ liệu phát sinh từ chúng.

### Lập bản đồ luồng nghiệp vụ

Với mỗi luồng, ghi lại:

- Điều kiện bắt đầu và kết thúc của giao dịch.
- Các bước đọc, ghi, cập nhật và xóa theo thứ tự.
- Bảng hoặc nhóm dữ liệu được truy cập.
- Ranh giới transaction, mức cô lập và thời điểm commit.
- Tham số đầu vào và cách chúng được chọn.
- Các nhánh điều kiện, ví dụ sản phẩm còn hàng hoặc hết hàng.
- Tác vụ bất đồng bộ được kích hoạt và thời điểm chúng chạy.

Thông tin này giúp phát hiện các tương tác có ảnh hưởng lớn đến hiệu năng. Chẳng hạn, hai luồng đặt hàng cùng cập nhật một mặt hàng bán chạy có thể tranh chấp trên cùng một hàng tồn kho, trong khi hai luồng xem chi tiết sản phẩm chủ yếu đọc dữ liệu.

## 3. Mô tả workload bằng các chiều chính

Không có một con số duy nhất mô tả đầy đủ tải. Một workload nên được xác định bằng nhiều chiều bổ sung cho nhau.

| Chiều workload | Cần mô tả | Vì sao quan trọng với cơ sở dữ liệu |
| --- | --- | --- |
| Thành phần giao dịch | Tỷ lệ tìm kiếm, đọc chi tiết, ghi, thanh toán, báo cáo và tác vụ nền | Quyết định tỷ lệ đọc/ghi và các đường truy cập cần tối ưu |
| Tốc độ đến | Số giao dịch hoặc yêu cầu đến mỗi giây, theo thời gian | Quyết định áp lực xử lý và khả năng hình thành hàng đợi |
| Mức đồng thời | Số giao dịch đang chạy cùng lúc và thời gian mỗi giao dịch giữ tài nguyên | Ảnh hưởng khóa, connection pool, bộ nhớ và tranh chấp |
| Đặc điểm dữ liệu | Số dòng, kích thước hàng, số lượng giá trị phân biệt và phân bố dữ liệu | Ảnh hưởng lựa chọn kế hoạch, số trang đọc và kích thước chỉ mục |
| Phân bố tham số | Giá trị phổ biến, hiếm, nóng, lạnh, khoảng truy vấn và độ sâu phân trang | Quyết định độ chọn lọc của bộ lọc và mức tập trung truy cập |
| Mẫu truy cập | Thứ tự đọc/ghi, phạm vi khóa, tính lặp lại và locality | Ảnh hưởng cache, I/O, deadlock và thời gian giữ khóa |
| Biến động thời gian | Giờ cao điểm, burst, chu kỳ ngày/tuần và tác vụ định kỳ | Giúp kiểm tra tải đỉnh và sự cạnh tranh giữa tác vụ trực tuyến, nền |

### Thành phần giao dịch và tỷ lệ đọc/ghi

Ước lượng tỷ lệ theo luồng nghiệp vụ trước, rồi đo số câu SQL phát sinh từ mỗi luồng để tính tỷ lệ thao tác cơ sở dữ liệu. Ví dụ, một profile minh họa có thể gồm 55% tìm kiếm, 25% xem chi tiết, 12% thao tác giỏ hàng, 6% đặt hàng và 2% tác vụ nền. Đây chỉ là số liệu giả định để minh họa cách mô tả; tỷ lệ thực tế phải lấy từ telemetry, log đã chuẩn hóa hoặc phân tích nghiệp vụ.

Không nên chỉ ghi `80% read / 20% write` nếu chưa biết cách phân loại. Một giao dịch đọc có thể gọi nhiều truy vấn; một giao dịch ghi có thể vừa đọc vừa cập nhật. Hãy quy định rõ đang tính tỷ lệ theo yêu cầu nghiệp vụ, transaction hay câu lệnh SQL.

### Tốc độ đến và tải đồng thời

Tốc độ đến (arrival rate) cho biết có bao nhiêu yêu cầu bắt đầu trong một đơn vị thời gian, thường là yêu cầu/giây hoặc giao dịch/giây. Mức đồng thời cho biết có bao nhiêu yêu cầu đang được xử lý tại cùng thời điểm. Hai đại lượng có liên quan nhưng không thể thay thế nhau.

Theo định luật Little, trong một hệ thống ổn định, số yêu cầu trung bình đang ở trong hệ thống xấp xỉ tốc độ đến trung bình nhân với thời gian lưu lại trung bình: `L = λ × W`. Ví dụ, nếu hệ thống nhận 100 giao dịch/giây và mỗi giao dịch ở trong hệ thống trung bình 0,2 giây, số giao dịch đang xử lý trung bình xấp xỉ 20. Đây là quan hệ trung bình trong điều kiện ổn định, không phải công thức dự báo chính xác hành vi ở thời điểm quá tải hoặc khi hàng đợi tăng liên tục.

Với cùng tốc độ đến, giao dịch lâu hơn làm tăng số giao dịch đồng thời. Khi mức đồng thời tăng, cơ sở dữ liệu có thể phải giữ nhiều kết nối, bộ nhớ làm việc và khóa hơn. Vì vậy, cần ghi nhận cả tốc độ đến và thời gian hoàn tất, thay vì chỉ cấu hình một số virtual users cố định rồi giả định tải đã đúng.

### Phân bố tham số và tính lệch

Dữ liệu thực tế thường không phân bố đều. Một số khách hàng, sản phẩm, tài khoản hoặc khóa có thể được truy cập thường xuyên hơn hẳn phần còn lại. Đây là phân bố lệch (skew) và có thể tạo ra điểm nóng (hotspot).

Ví dụ, nếu workload chọn ngẫu nhiên đều 1 triệu sản phẩm, mỗi sản phẩm gần như có xác suất truy cập như nhau. Nhưng trong thực tế, một số sản phẩm bán chạy có thể nhận phần lớn lượt đọc và cập nhật tồn kho. Mô hình đều có thể bỏ lỡ tranh chấp trên các hàng nóng và cho kết quả cache tốt hơn thực tế.

Hãy mô tả ít nhất:

- Tỷ lệ truy cập vào nhóm giá trị phổ biến so với nhóm hiếm.
- Phân bố theo tenant, khách hàng, sản phẩm hoặc tài khoản nếu hệ thống có phân vùng logic.
- Tỷ lệ truy vấn theo khóa chính, theo khoảng, theo nhiều điều kiện và theo tìm kiếm.
- Phân bố độ sâu trang, kích thước kết quả và phạm vi thời gian.
- Mức độ lặp lại của tham số và khoảng thời gian giữa các lần truy cập cùng một khóa.

## 4. Tạo dữ liệu kiểm thử phản ánh dữ liệu thật

Workload chỉ có ý nghĩa khi dữ liệu nền cũng đủ đại diện. Cùng một câu SQL có thể chạy rất khác nhau khi bảng có 10 nghìn dòng so với 100 triệu dòng, khi một cột có vài giá trị phân biệt so với hàng triệu giá trị, hoặc khi dữ liệu tập trung vào một số khoảng.

Khi xây dựng tập dữ liệu, hãy xem xét:

- **Quy mô:** số dòng của các bảng lớn, số bản ghi liên quan và tổng dung lượng dữ liệu.
- **Cardinality:** số lượng giá trị phân biệt của các cột thường dùng để lọc, nối và nhóm.
- **Skew:** tỷ lệ các giá trị xuất hiện nhiều, giá trị hiếm và nhóm dữ liệu nóng.
- **Tính tương quan:** mối quan hệ giữa các cột, ví dụ trạng thái đơn hàng thường đi cùng khoảng thời gian hoặc tenant cụ thể.
- **Phân bố quan hệ:** số dòng con trên mỗi dòng cha, số mặt hàng trong một đơn, số giao dịch trên một tài khoản.
- **Kích thước bản ghi:** độ dài văn bản, payload, trường nullable và dữ liệu lớn như JSON hoặc BLOB.
- **Tuổi dữ liệu:** tỷ lệ bản ghi mới/cũ, dữ liệu đã lưu trữ và các khoảng thời gian thường được truy vấn.

Nếu dùng dữ liệu tổng hợp, hãy tạo các phân bố và quan hệ gần với dữ liệu cần mô phỏng. Sinh số ngẫu nhiên độc lập cho từng cột có thể phá vỡ tương quan giữa các trường và tạo ra những tổ hợp không xuất hiện trong nghiệp vụ.

Nếu dùng bản sao dữ liệu thật, cần xử lý thông tin nhạy cảm theo quy định của môi trường và thay thế hoặc ẩn danh các trường định danh. Sau khi biến đổi, hãy kiểm tra rằng số dòng, quan hệ khóa ngoại, phân bố giá trị và độ lệch quan trọng vẫn được bảo toàn. Tập dữ liệu đã ẩn danh nhưng làm mất các khóa nóng hoặc phân bố tenant vẫn có thể tạo ra workload sai lệch.

### Dữ liệu cần đủ lớn so với bộ nhớ

Nếu toàn bộ tập dữ liệu kiểm thử vừa trong cache của máy chủ, kết quả chủ yếu phản ánh đường đọc bộ nhớ. Điều đó có thể phù hợp với một hệ thống có working set thực sự nhỏ, nhưng không đại diện cho hệ thống mà dữ liệu hoạt động lớn hơn bộ nhớ khả dụng.

Hãy phân biệt tổng dung lượng dữ liệu với working set — phần dữ liệu được truy cập thường xuyên trong một khoảng thời gian. Có thể kiểm thử nhiều profile: working set nằm trong bộ nhớ, working set lớn hơn cache và profile có tỷ lệ truy cập dữ liệu lạnh đáng kể. Mỗi profile trả lời một câu hỏi hiệu năng khác nhau.

## 5. Mô hình hóa thứ tự truy cập và tranh chấp

Không chỉ giá trị truy vấn quan trọng; thứ tự và thời điểm truy cập cũng ảnh hưởng kết quả. Workload có thể tạo ra các tình huống như:

- Nhiều transaction cùng đọc rồi cập nhật một hàng.
- Nhiều transaction cập nhật các hàng khác nhau nhưng cùng một trang hoặc cùng một chỉ mục.
- Một giao dịch giữ khóa lâu vì thực hiện nhiều bước trước khi commit.
- Truy vấn báo cáo quét dữ liệu lớn cùng lúc với giao dịch ghi trực tuyến.
- Nhiều worker xử lý cùng một hàng đợi hoặc cùng một phân vùng dữ liệu.

Để mô phỏng đúng, cần tái tạo phạm vi truy cập, thời gian giữ transaction và tỷ lệ va chạm trên khóa. Một bài benchmark chỉ cập nhật khóa ngẫu nhiên phân bố đều có thể không tạo ra mức tranh chấp giống hệ thống mà một số khóa được truy cập dày đặc.

Đồng thời, không phải mọi truy vấn đọc đều độc lập. Một luồng nghiệp vụ có thể đọc dữ liệu rồi dùng kết quả để quyết định câu lệnh tiếp theo. Giữ thứ tự này giúp phản ánh phụ thuộc thực tế và thời gian transaction. Nếu chỉ phát lại từng câu SQL tách rời, ta có thể làm mất ngữ nghĩa giao dịch, thứ tự khóa và tác động của commit/rollback.

## 6. Chọn mô hình phát tải

Có hai cách mô hình hóa phổ biến:

### Mô hình đóng (closed workload)

Một số lượng người dùng hoặc worker cố định gửi yêu cầu mới sau khi yêu cầu trước hoàn tất, thường có thêm thời gian suy nghĩ (think time). Khi hệ thống chậm, mỗi worker hoàn tất ít yêu cầu hơn nên tốc độ đến tự giảm.

Mô hình này phù hợp khi muốn mô phỏng một nhóm phiên hoặc người dùng có hành vi tuần tự. Tuy nhiên, khi hệ thống gần bão hòa, tốc độ đến giảm theo thời gian đáp ứng. Kết quả có thể che khuất lượng yêu cầu mà hệ thống sẽ nhận nếu nguồn gửi vẫn tiếp tục phát tải.

### Mô hình mở (open workload)

Yêu cầu được phát theo lịch hoặc tốc độ đến mục tiêu, tương đối độc lập với thời gian hoàn tất của yêu cầu trước. Ví dụ, bộ phát tải cố gắng bắt đầu 200 giao dịch mỗi giây dù một số giao dịch đang chậm.

Mô hình này phù hợp để kiểm tra khả năng đáp ứng một tốc độ đến đã xác định và quan sát hàng đợi khi hệ thống quá tải. Khi máy chủ không theo kịp, cần ghi nhận yêu cầu bị xếp hàng, bị bỏ lỡ lịch phát hoặc bị từ chối; không được chỉ báo cáo độ trễ của những yêu cầu thực sự bắt đầu.

| Tiêu chí | Mô hình đóng | Mô hình mở |
| --- | --- | --- |
| Cách phát yêu cầu | Worker chờ yêu cầu trước hoàn tất rồi mới gửi tiếp | Phát theo tốc độ đến hoặc lịch đã định |
| Khi hệ thống chậm | Tốc độ phát thường giảm theo | Tốc độ đến mục tiêu vẫn được duy trì cho đến khi bộ phát tải hoặc hệ thống đạt giới hạn |
| Phù hợp để | Mô phỏng nhóm phiên/người dùng tuần tự | Kiểm tra tải theo tốc độ đến và khả năng hình thành hàng đợi |
| Rủi ro khi diễn giải | Có thể không tạo đủ áp lực khi độ trễ tăng | Bộ phát tải có thể tự quá tải; cần đo cả yêu cầu dự kiến và thực sự phát |

Hiện tượng bỏ sót các yêu cầu đáng lẽ đã được phát trong lúc hệ thống chậm có thể làm độ trễ đo được thấp hơn thực tế; trong kiểm thử hiệu năng hiện tượng này thường được gọi là coordinated omission. Hãy dùng bộ phát tải có khả năng ghi nhận thời điểm dự kiến, thời điểm bắt đầu thực tế và thời điểm hoàn tất, hoặc hiệu chỉnh kết quả theo phương pháp đã công bố.

## 7. Xây dựng một profile workload có thể tái lập

Một profile nên ghi rõ cấu hình và giả định để người khác có thể chạy lại. Ví dụ dưới đây là profile minh họa cho hệ thống bán hàng; các tỷ lệ và con số phải được thay bằng số liệu đo thực tế trước khi dùng để đánh giá.

```yaml
workload: online_store_peak
duration: 30m
arrival_model: open
target_rate_per_second: 200
transaction_mix:
  search_products: 55
  view_product: 25
  update_cart: 12
  place_order: 6
  background_jobs: 2
data_profile:
  products: 1000000
  customers: 250000
  orders: 5000000
  hot_product_share: 0.05
  hot_product_request_share: 0.60
  tenant_distribution: measured
concurrency:
  checkout_overlap: measured
  background_workers: 8
parameters:
  search_term_distribution: measured
  page_depth_distribution: measured
  order_line_count_distribution: measured
warmup: 5m
measurement_window: 20m
```

Profile này ghi nhận thời lượng, mô hình phát, tốc độ đến, tỷ lệ luồng, quy mô dữ liệu, độ nóng và các phân bố tham số. `measured` có nghĩa là giá trị phải được lấy từ số liệu quan sát; nó không phải cấu hình mà công cụ tự hiểu. Khi chuyển profile sang công cụ kiểm thử, hãy ánh xạ các trường này sang cấu hình thực tế và lưu phiên bản script cùng dữ liệu sinh.

Để tái lập, cũng cần ghi phiên bản ứng dụng, phiên bản hệ quản trị, cấu hình máy chủ, cấu hình connection pool, trạng thái cache, kích thước dữ liệu, seed sinh dữ liệu và mã phiên bản workload. Nếu bất kỳ yếu tố nào thay đổi giữa hai lần chạy, hãy ghi lại để giải thích khác biệt.

## 8. Quy trình xây dựng workload từ dữ liệu thực tế

1. **Chọn mục tiêu đo.** Xác định câu hỏi cần trả lời: hệ thống chịu được bao nhiêu giao dịch/giây, p95 của luồng đặt hàng là bao nhiêu, hay chỉ mục mới có giảm I/O cho nhóm tìm kiếm không.
2. **Thu thập dấu vết hoạt động.** Dùng số liệu request, log ứng dụng, thống kê truy vấn và thông tin transaction trong khoảng thời gian đại diện. Chuẩn hóa câu SQL theo mẫu, loại bỏ bí mật và dữ liệu định danh trước khi phân tích.
3. **Nhóm theo luồng nghiệp vụ.** Nối request với các câu SQL phát sinh, xác định thứ tự, số lần gọi, ranh giới transaction và tác vụ nền.
4. **Ước lượng tỷ lệ và tốc độ đến.** Tính tỷ lệ từng luồng, phân bố theo thời gian, giờ cao điểm và burst. Phân biệt tỷ lệ request với tỷ lệ câu lệnh SQL.
5. **Phân tích tham số và dữ liệu.** Xác định giá trị phổ biến/hiếm, khóa nóng, cardinality, tương quan cột, kích thước kết quả và working set.
6. **Tạo tập dữ liệu kiểm thử.** Dùng dữ liệu đã ẩn danh hoặc dữ liệu tổng hợp có bảo toàn phân bố và quan hệ cần thiết. Xác minh quy mô và phân bố trước khi chạy tải.
7. **Chọn mô hình phát.** Chọn closed hoặc open theo hành vi cần mô phỏng; xác định tốc độ đến, số worker, think time và cách ghi nhận yêu cầu bị trễ lịch hoặc bị bỏ.
8. **Chạy thử và kiểm tra bộ phát tải.** Bảo đảm máy tạo tải còn dư CPU, bộ nhớ và mạng; kiểm tra nó có thể phát đúng tốc độ mục tiêu và ghi nhận đủ số mẫu.
9. **Chạy workload và lưu kết quả.** Ghi throughput, latency, p50/p95/p99, lỗi, timeout, số kết nối, transaction đang chạy, lock wait, CPU, bộ nhớ, I/O và thống kê truy vấn.
10. **Hiệu chỉnh profile.** So sánh kết quả với hành vi thực tế. Nếu tỷ lệ truy vấn, phân bố tham số hoặc mức tranh chấp khác xa, điều chỉnh profile rồi chạy lại.

## 9. Đọc kết quả và xác nhận workload đủ đại diện

Workload không trở nên đại diện chỉ vì nó tạo ra CPU cao hoặc đạt một con số giao dịch mỗi giây. Cần so sánh nhiều đặc điểm của lần chạy với hệ thống mục tiêu.

| Đặc điểm cần đối chiếu | Câu hỏi kiểm chứng |
| --- | --- |
| Tỷ lệ luồng | Tỷ lệ tìm kiếm, đọc, ghi và tác vụ nền có gần với hoạt động cần mô phỏng không? |
| Tốc độ đến | Số yêu cầu bắt đầu mỗi giây có đúng profile, kể cả lúc burst không? |
| Thời gian giao dịch | Số bước, thời gian giữ transaction và thời gian chờ có tương tự không? |
| Phân bố dữ liệu | Cardinality, skew, khóa nóng và working set có đủ gần không? |
| Tỷ lệ lỗi | Lỗi nghiệp vụ, timeout, deadlock và retry có được ghi nhận đúng không? |
| Tài nguyên | CPU, I/O, cache, kết nối và hàng đợi có thể hiện đúng kiểu áp lực dự kiến không? |
| Độ trễ | Phân bố p50, p95, p99 theo từng nhóm giao dịch có hợp lý so với đường cơ sở không? |

Không nhất thiết mọi chỉ số của một môi trường kiểm thử phải giống hệt sản xuất; mục tiêu là giữ những đặc điểm quyết định câu hỏi đang kiểm tra. Ví dụ, khi chỉ kiểm tra lựa chọn chỉ mục cho một truy vấn, có thể cố định các luồng khác. Nhưng khi kiểm tra sức chịu tải toàn hệ thống, phải tái tạo tương tác giữa các luồng và tài nguyên dùng chung.

### Tránh để bộ phát tải trở thành nút thắt

Nếu máy tạo tải hết CPU, hết cổng mạng hoặc không mở đủ kết nối, tốc độ đến thực tế sẽ thấp hơn profile. Hệ thống cơ sở dữ liệu khi đó có vẻ còn dư năng lực dù bộ phát tải đã chạm giới hạn.

Hãy theo dõi CPU, bộ nhớ, mạng và hàng đợi của máy phát tải; kiểm tra số yêu cầu dự kiến, đã phát, đang chờ, hoàn tất và thất bại. Khi cần, phân tán tải trên nhiều máy phát và xác minh rằng việc phân tán không làm thay đổi phân bố tham số hoặc thứ tự giao dịch.

## 10. Dùng workload để kiểm chứng tối ưu cơ sở dữ liệu

Sau khi có workload ổn định, dùng cùng profile trước và sau mỗi thay đổi. Ví dụ:

- **Thêm hoặc điều chỉnh chỉ mục:** kiểm tra p95/p99 và số trang đọc của nhóm truy vấn mục tiêu; đồng thời đo thời gian ghi, dung lượng chỉ mục và chi phí bảo trì.
- **Viết lại SQL:** so sánh kế hoạch thực thi, số dòng ước lượng/thực tế, số lần gọi, lượng dữ liệu đọc và độ trễ ở cùng phân bố tham số.
- **Giảm tranh chấp:** giữ nguyên tốc độ đến và phân bố khóa nóng, sau đó so sánh lock wait, deadlock, thời gian transaction và thông lượng.
- **Điều chỉnh bộ nhớ hoặc cache:** giữ working set và tỷ lệ truy cập nóng/lạnh ổn định; quan sát cache hit, I/O vật lý và phân vị độ trễ.
- **Điều chỉnh connection pool:** giữ profile tốc độ đến, theo dõi thời gian chờ lấy kết nối, số kết nối hoạt động và áp lực lên máy chủ.

Không thay đổi nhiều yếu tố cùng lúc nếu mục tiêu là xác định tác động của từng thay đổi. Nếu phải thay đổi đồng thời, hãy ghi rõ và dùng phép thử riêng để tách ảnh hưởng khi có thể.

Đo trước và sau cần có thời lượng đủ dài để thu thập số mẫu đại diện, có giai đoạn warm-up nhất quán và điều kiện tải tương đương. So sánh thêm throughput, lỗi, timeout và các nhóm giao dịch không phải mục tiêu để phát hiện việc cải thiện một luồng nhưng làm suy giảm luồng khác.

## 11. Những sai lầm thường gặp

- **Chỉ phát một câu SQL lặp lại.** Cách này không phản ánh transaction, thứ tự nghiệp vụ, cạnh tranh và tỷ lệ đọc/ghi của ứng dụng.
- **Chọn tham số ngẫu nhiên đều.** Dữ liệu thực thường lệch; bỏ qua khóa nóng có thể che giấu tranh chấp và làm sai kết quả cache.
- **Dùng tập dữ liệu quá nhỏ.** Toàn bộ dữ liệu nằm trong cache có thể khiến I/O và kế hoạch truy cập khác xa môi trường mục tiêu.
- **Chỉ cấu hình số virtual users.** Con số này không cho biết tốc độ đến thực tế, đặc biệt khi thời gian đáp ứng thay đổi.
- **Bỏ qua transaction và think time.** Điều này có thể làm sai mức đồng thời, thời gian giữ khóa và áp lực connection pool.
- **Gộp tỷ lệ nghiệp vụ với tỷ lệ câu SQL.** Một giao dịch có thể phát sinh nhiều truy vấn; cần ghi rõ mẫu số đang sử dụng.
- **Không đo bộ phát tải.** Bộ phát tải bị giới hạn có thể khiến cơ sở dữ liệu nhận ít yêu cầu hơn dự kiến.
- **Dùng dữ liệu ẩn danh nhưng mất phân bố.** Thay đổi khóa nóng, quan hệ hoặc cardinality có thể làm workload không còn đại diện.
- **So sánh hai lần chạy khác điều kiện.** Khác cache, dữ liệu, phiên bản, cấu hình hoặc tốc độ đến làm kết luận tối ưu thiếu tin cậy.

## 12. Danh sách kiểm tra trước khi chạy

- [ ] Đã chọn rõ câu hỏi hiệu năng cần trả lời và nhóm giao dịch liên quan.
- [ ] Đã mô tả các luồng nghiệp vụ cùng thứ tự thao tác và ranh giới transaction.
- [ ] Đã ghi tỷ lệ theo giao dịch nghiệp vụ và số thao tác SQL phát sinh.
- [ ] Đã xác định tốc độ đến, mức đồng thời, think time và biến động theo thời gian.
- [ ] Tập dữ liệu có quy mô, cardinality, skew, tương quan và working set phù hợp.
- [ ] Các khóa nóng và mẫu truy cập cạnh tranh được mô phỏng khi chúng quan trọng.
- [ ] Mô hình open/closed phù hợp với mục tiêu đo và giới hạn của nó đã được hiểu.
- [ ] Bộ phát tải đủ khả năng phát đúng tốc độ và có telemetry riêng.
- [ ] Đã ghi phiên bản, cấu hình, seed dữ liệu, thời gian warm-up và thời gian đo.
- [ ] Có throughput, phân vị độ trễ, lỗi, timeout và chỉ số tài nguyên để phân tích.
- [ ] Có thể chạy lại cùng profile để so sánh trước và sau tối ưu.

## Kết luận

Xây dựng workload đại diện bắt đầu từ luồng nghiệp vụ và kết thúc bằng một profile có thể tái lập. Profile cần thể hiện thành phần giao dịch, tốc độ đến, mức đồng thời, phân bố tham số, quy mô và độ lệch dữ liệu, thứ tự truy cập cùng biến động theo thời gian. Khi các đặc điểm này gần với hoạt động cần phục vụ, phép đo mới giúp nhận diện đúng nút thắt của SQL, chỉ mục, khóa, I/O, bộ nhớ và kết nối. Hãy giữ workload ổn định khi so sánh trước và sau tối ưu, đồng thời ghi nhận cả độ trễ, thông lượng, lỗi và chi phí phát sinh ở các luồng khác.
