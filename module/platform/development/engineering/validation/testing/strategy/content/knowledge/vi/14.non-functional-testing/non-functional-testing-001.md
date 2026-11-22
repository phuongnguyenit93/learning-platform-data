# Chuyển mục tiêu tốc độ và công suất thành phạm vi kiểm thử hiệu năng

## Mục tiêu học tập

Sau bài học này, người học có thể:

- Phân biệt mục tiêu độ trễ, thông lượng, năng lực xử lý và mức tải mà hệ thống cần đáp ứng.
- Chuyển yêu cầu tốc độ và công suất thành chỉ số, ngưỡng, điều kiện tải và phạm vi kiểm thử đo được.
- Xây dựng mô hình tải từ hành trình người dùng, tỷ lệ giao dịch, dữ liệu và thời điểm cao điểm.
- Lựa chọn loại kiểm thử hiệu năng phù hợp: baseline, load, stress, spike, soak, scalability và capacity test.
- Xác định thành phần, ranh giới, môi trường, dữ liệu và chỉ số cần quan sát trong phạm vi kiểm thử.
- Đặt tiêu chí đạt/không đạt có xét đến độ trễ phân vị, throughput thành công, tỷ lệ lỗi và mức sử dụng tài nguyên.
- Phân tích kết quả để xác định điểm nghẽn, giới hạn năng lực và rủi ro còn lại.

## 1. Vì sao cần chuyển mục tiêu thành phạm vi kiểm thử?

Trong phạm vi **VALIDATION_TESTING_STRATEGY**, kiểm thử hiệu năng xác minh hệ thống có đáp ứng được tốc độ và công suất đã thống nhất trong những điều kiện sử dụng xác định hay không. Một yêu cầu như “trang phải nhanh” hoặc “dịch vụ chịu được nhiều người dùng” chưa đủ để lập kế hoạch kiểm thử. Nhóm cần biết thao tác nào phải nhanh, bao nhiêu yêu cầu hoặc giao dịch xảy ra đồng thời, dữ liệu có quy mô ra sao, thời gian đo được tính từ đâu đến đâu và điều kiện nào được xem là đạt.

Nếu phạm vi chỉ đo một endpoint với dữ liệu nhỏ, kết quả có thể không đại diện cho hành trình thật. Nếu chỉ tạo tải lớn mà không kiểm tra kết quả nghiệp vụ, hệ thống có thể đạt số yêu cầu mỗi giây nhưng trả lỗi hoặc ghi dữ liệu sai. Nếu chỉ nhìn thời gian phản hồi trung bình, những yêu cầu chậm mà người dùng thường xuyên gặp có thể bị che khuất.

Một phạm vi kiểm thử hiệu năng tốt nối được chuỗi sau:

1. **Mục tiêu nghiệp vụ và trải nghiệm**: người dùng cần hoàn thành thao tác nào, vào thời điểm nào và với mức dịch vụ nào?
2. **Chỉ số và ngưỡng**: độ trễ, throughput, tỷ lệ lỗi, mức đồng thời hoặc thời gian hoàn tất được đo ra sao?
3. **Mô hình tải**: số người dùng, tốc độ gửi yêu cầu, phân bố hành trình, dữ liệu và thời gian tải như thế nào?
4. **Phạm vi hệ thống**: thành phần, phụ thuộc, môi trường và ranh giới nào được đưa vào phép đo?
5. **Phương pháp và bằng chứng**: loại kiểm thử, cách quan sát, tiêu chí đạt và báo cáo kết quả là gì?

Mục tiêu là chứng minh năng lực trong bối cảnh đã xác định, không phải tạo ra một con số tải lớn tách rời nhu cầu sử dụng.

## 2. Phân biệt độ trễ, thông lượng và công suất

Các mục tiêu hiệu năng thường liên quan với nhau nhưng đo những khía cạnh khác nhau.

- **Độ trễ (latency)** là thời gian một yêu cầu hoặc thao tác cần để hoàn tất theo điểm đo đã định. Độ trễ ảnh hưởng trực tiếp đến cảm nhận tốc độ của người dùng.
- **Thông lượng (throughput)** là số yêu cầu hoặc giao dịch được xử lý trong một đơn vị thời gian, chẳng hạn request/second (RPS) hoặc transaction/second (TPS).
- **Công suất (capacity)** là mức tải hoặc khối lượng công việc mà hệ thống có thể xử lý trong khi vẫn đáp ứng các điều kiện chất lượng đã đặt ra.
- **Đồng thời (concurrency)** là số thao tác hoặc yêu cầu đang được xử lý cùng lúc. Nó không đồng nghĩa với số người dùng đang đăng nhập.
- **Tỷ lệ lỗi (error rate)** là tỷ lệ yêu cầu thuộc phạm vi đo không hoàn tất đúng theo định nghĩa thành công.

Một hệ thống có thể đạt throughput cao nhưng độ trễ p99 quá lớn; cũng có thể phản hồi nhanh khi tải thấp nhưng bắt đầu lỗi khi số yêu cầu tăng. Vì vậy, mục tiêu công suất thường phải đi kèm giới hạn độ trễ và tỷ lệ lỗi.

### 2.1. Độ trễ trung bình không đủ

Thời gian trung bình có thể che khuất một nhóm yêu cầu rất chậm. Các phân vị thường được dùng để mô tả phân bố:

- **p50**: 50% số quan sát có độ trễ không lớn hơn giá trị này.
- **p90**: 90% số quan sát có độ trễ không lớn hơn giá trị này.
- **p95**: 95% số quan sát có độ trễ không lớn hơn giá trị này.
- **p99**: 99% số quan sát có độ trễ không lớn hơn giá trị này.

Ví dụ, p95 bằng 800 ms có nghĩa là 95% quan sát nằm trong hoặc dưới 800 ms và khoảng 5% còn lại chậm hơn. Cần xem xét số lượng mẫu và cửa sổ đo: p99 từ một tập rất nhỏ có thể không ổn định. Khi tổng hợp dữ liệu từ nhiều máy phát tải hoặc nhiều khoảng thời gian, cần dùng histogram hoặc cách tổng hợp phân vị phù hợp; không lấy trung bình các giá trị p95 riêng lẻ để suy ra p95 toàn hệ thống.

### 2.2. Throughput phải tính trên công việc thành công

Số yêu cầu gửi đi không đồng nghĩa số yêu cầu được xử lý thành công. Một hệ thống có thể nhận 1.000 RPS nhưng chỉ hoàn tất 700 RPS và trả lỗi hoặc timeout cho phần còn lại. Báo cáo cần phân biệt:

- Lưu lượng được tạo ra.
- Lưu lượng hệ thống tiếp nhận.
- Số yêu cầu hoàn tất thành công.
- Số yêu cầu lỗi, timeout, bị từ chối hoặc còn tồn trong hàng đợi.

Với hệ thống nghiệp vụ, throughput nên được đo theo giao dịch có ý nghĩa, chẳng hạn số đơn hàng được tạo thành công mỗi giây, thay vì chỉ đếm request HTTP nếu một giao dịch cần nhiều request.

### 2.3. Công suất là một điểm vận hành có điều kiện

Không nên mô tả công suất chỉ bằng “tối đa 5.000 người dùng”. Cần xác định:

- Tải được tạo ra theo mô hình nào.
- Tỷ lệ các loại thao tác và kích thước dữ liệu.
- Độ trễ và tỷ lệ lỗi tối đa cho phép.
- Mức tài nguyên và cấu hình triển khai.
- Khoảng thời gian hệ thống phải duy trì tải.

Ví dụ, “dịch vụ xử lý 500 giao dịch đặt hàng mỗi phút” chỉ có ý nghĩa khi nêu rõ tỷ lệ đọc/ghi, cách xác định giao dịch thành công, thời gian duy trì và ngưỡng độ trễ. Công suất đạt được trong một phút có thể không duy trì được trong một giờ nếu hàng đợi hoặc bộ nhớ tăng dần.

## 3. Chuyển yêu cầu thành mục tiêu có thể đo

Một mục tiêu hiệu năng cần đủ rõ để người thiết kế tải, người vận hành và người đánh giá hiểu cùng một phép đo.

### 3.1. Các thành phần của một mục tiêu

Mỗi mục tiêu nên nêu:

1. **Hành trình hoặc thao tác**: chức năng, API hoặc giao dịch nào thuộc phạm vi.
2. **Chỉ số**: latency, throughput, concurrency, error rate hoặc thời gian hoàn tất.
3. **Ngưỡng**: giá trị tối đa, tối thiểu hoặc khoảng cho phép.
4. **Điều kiện tải**: số người dùng, RPS/TPS, tỷ lệ thao tác, tốc độ tăng tải và thời gian duy trì.
5. **Điều kiện môi trường**: cấu hình ứng dụng, hạ tầng, database, cache, mạng và phụ thuộc.
6. **Cửa sổ đo**: thời gian warm-up, thời gian ổn định, khoảng đo và cách xử lý mẫu.
7. **Định nghĩa thành công**: điều kiện nào được tính là hoàn tất đúng, loại lỗi nào được tính vào mẫu số.
8. **Nguồn bằng chứng**: công cụ tạo tải, metric, log, trace và kiểm tra trạng thái nghiệp vụ.

Có thể dùng mẫu câu:

> Với **[hành trình/thao tác]**, trong điều kiện **[mô hình tải và môi trường]**, hệ thống phải đạt **[ngưỡng latency và throughput]**, với **[giới hạn lỗi]**, duy trì trong **[khoảng thời gian]**, được đo tại **[điểm đo]**.

### 3.2. Ví dụ chuyển đổi từ câu mơ hồ

| Yêu cầu ban đầu | Những điểm cần làm rõ | Mục tiêu có thể kiểm thử |
|---|---|---|
| Trang danh mục phải nhanh. | Trang nào, dữ liệu bao nhiêu, tải ra sao, đo từ đâu? | p95 thời gian tải nội dung chính không vượt ngưỡng đã thống nhất ở mức tải người dùng dự kiến. |
| API phải chịu tải cao. | API nào, lưu lượng thành công, tỷ lệ lỗi và thời gian duy trì? | API tra cứu hoàn tất ít nhất mức RPS mục tiêu, p95/p99 và tỷ lệ lỗi nằm trong giới hạn trong cửa sổ đo. |
| Hệ thống hỗ trợ 10.000 người dùng. | Người dùng đồng thời hay tài khoản đăng ký? Mỗi người tạo bao nhiêu thao tác? | Duy trì số phiên đồng thời với mô hình hành vi và tỷ lệ giao dịch được mô tả, đồng thời đạt mục tiêu latency và throughput. |
| Báo cáo không được mất quá lâu. | Kích thước dữ liệu, độ mới, thời hạn hoàn tất? | 95% tác vụ báo cáo thuộc phạm vi hoàn tất trong thời hạn xác định với kích thước dữ liệu đại diện. |

Các ngưỡng cần được thống nhất từ nhu cầu người dùng, dữ liệu vận hành, kiến trúc, chi phí và cam kết dịch vụ. Không tự lấy số minh họa làm SLO chính thức.

### 3.3. Xác định điểm đo và ranh giới thời gian

Thời gian phản hồi có thể được đo ở nhiều điểm:

- **Client-perceived time**: từ khi người dùng bắt đầu thao tác đến khi nội dung hoặc kết quả cần thiết có thể sử dụng.
- **API response time**: từ lúc gateway hoặc service nhận request đến khi gửi response.
- **Server processing time**: thời gian xử lý bên trong một thành phần, không bao gồm một số độ trễ mạng bên ngoài.
- **Background completion time**: từ lúc tiếp nhận tác vụ bất đồng bộ đến khi trạng thái cuối được ghi nhận.

Các điểm đo này trả lời câu hỏi khác nhau. Nếu mục tiêu là trải nghiệm người dùng, chỉ đo thời gian xử lý nội bộ có thể bỏ qua DNS, TLS, mạng, tải tài nguyên hoặc render giao diện. Nếu mục tiêu là hiệu năng của một API, cần xác định điểm bắt đầu và kết thúc ở ranh giới API và không trộn với thời gian phía client.

## 4. Xây dựng mô hình tải từ hành vi thực tế

Mô hình tải (workload model) mô tả cách người dùng hoặc hệ thống tạo công việc. Đây là một trong những phần quan trọng nhất của phạm vi kiểm thử: tải không giống thực tế có thể tạo ra kết quả đẹp nhưng ít giá trị dự báo.

### 4.1. Xác định nhóm người dùng và hành trình

Hãy liệt kê các nhóm người dùng hoặc client chính, hành trình họ thực hiện và tỷ lệ tương đối. Ví dụ với cửa hàng trực tuyến:

- Khách truy cập xem danh mục và tìm kiếm.
- Người dùng xem chi tiết sản phẩm.
- Người dùng đăng nhập và xem giỏ hàng.
- Người mua tạo đơn và thanh toán.
- Nhân viên tra cứu và cập nhật đơn hàng.

Không phải mọi nhóm đều tạo cùng mức tải. Hành trình xem danh mục có thể chiếm phần lớn request, trong khi đặt hàng ít hơn nhưng có nhiều thao tác ghi và phụ thuộc dịch vụ.

### 4.2. Xác định tỷ lệ thao tác

Một workload profile cần mô tả tỷ lệ hoặc tần suất của từng loại hành vi. Ví dụ minh họa:

| Hành trình | Tỷ trọng giao dịch |
|---|---:|
| Xem danh mục / tìm kiếm | 55% |
| Xem chi tiết sản phẩm | 25% |
| Đăng nhập / xem giỏ hàng | 12% |
| Tạo đơn hàng | 6% |
| Tra cứu đơn hàng | 2% |

Tỷ trọng trên chỉ là ví dụ. Hãy dùng log, analytics, dữ liệu nghiệp vụ hoặc phỏng vấn chủ sở hữu sản phẩm để xây dựng tỷ lệ đại diện. Cần nêu rõ tỷ trọng được tính theo phiên, giao dịch hay request; ba cách tính có thể cho kết quả khác nhau.

### 4.3. Xác định thời gian nghĩ và nhịp gửi yêu cầu

Người dùng thường không gửi request liên tục như máy. Họ đọc nội dung, suy nghĩ, nhập dữ liệu và chuyển trang. **Think time** mô tả khoảng thời gian giữa các thao tác của một người dùng ảo. Bỏ qua think time có thể tạo tải quá dày so với thực tế; đặt quá dài có thể không đạt mục tiêu concurrency hoặc throughput.

Hãy chọn mô hình phù hợp:

- **Closed workload model**: số người dùng ảo được giữ cố định; mỗi người hoàn tất một chu kỳ rồi mới bắt đầu chu kỳ tiếp theo. Mô hình này phù hợp khi người dùng có thời gian phản hồi và think time.
- **Open workload model**: yêu cầu hoặc giao dịch mới được đưa vào theo tốc độ xác định, độc lập với thời gian phản hồi của hệ thống. Mô hình này phù hợp để mô phỏng tốc độ đến của công việc và phát hiện hệ thống không theo kịp lưu lượng.

Nếu hệ thống chậm, mô hình closed có thể tự giảm tốc độ gửi vì người dùng ảo đang chờ phản hồi; điều này có thể che khuất tình trạng backlog khi lưu lượng đến từ bên ngoài không giảm theo. Mô hình open cần kiểm soát lịch gửi và đo chính xác số yêu cầu thực sự phát ra, tránh máy phát tải không theo kịp lịch mà vẫn báo tải mục tiêu.

### 4.4. Ước lượng concurrency bằng định luật Little

Định luật Little mô tả quan hệ giữa số công việc trung bình trong hệ thống, tốc độ đến và thời gian lưu lại:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số yêu cầu hoặc công việc trung bình đang ở trong hệ thống.
- \(\lambda\) là tốc độ đến trung bình (ví dụ request/second).
- \(W\) là thời gian trung bình một yêu cầu ở trong hệ thống (giây).

Ví dụ, nếu một API nhận trung bình 100 request/giây và mỗi request ở trong hệ thống trung bình 0,2 giây, số request đang được xử lý hoặc chờ trung bình xấp xỉ 20. Đây là ước lượng cho trạng thái ổn định và cần dùng đúng ranh giới đo; nó không thay thế việc đo concurrency thực tế hoặc đánh giá phân phối độ trễ.

Đối với người dùng ảo, có thể dùng mô hình chu kỳ thao tác và think time để ước lượng số phiên cần thiết. Không nên đồng nhất số phiên đang mở với số request đang xử lý.

### 4.5. Xem xét thời điểm cao điểm và tính mùa vụ

Tải có thể tăng theo giờ, ngày, mùa, chiến dịch hoặc sự kiện. Phạm vi cần xác định:

- Mức tải bình thường.
- Mức tải cao điểm dự kiến.
- Tốc độ tăng tải khi bắt đầu chiến dịch.
- Đợt tăng đột biến do thông báo hoặc sự kiện.
- Tác vụ nền trùng thời điểm với lưu lượng người dùng.
- Tăng trưởng dự kiến trong thời gian tới.

Không chỉ lấy mức trung bình ngày để thiết kế test nếu hệ thống thường có đỉnh tải ngắn nhưng rất cao.

## 5. Chọn loại kiểm thử hiệu năng

Mỗi loại kiểm thử trả lời một câu hỏi khác nhau. Phạm vi có thể kết hợp nhiều loại tùy mục tiêu và rủi ro.

| Loại kiểm thử | Câu hỏi chính | Cách tạo tải | Kết quả cần quan sát |
|---|---|---|---|
| Baseline | Hệ thống hoạt động thế nào ở mức tải chuẩn? | Tải thấp hoặc mức chuẩn lặp lại | Độ trễ, throughput, lỗi và tài nguyên làm mốc so sánh. |
| Load test | Hệ thống có đáp ứng tải dự kiến không? | Tăng đến mức tải bình thường hoặc cao điểm và duy trì | Latency, throughput thành công, error rate, saturation. |
| Stress test | Hệ thống suy giảm và thất bại ra sao khi vượt tải? | Tăng tải vượt mức dự kiến đến khi chạm giới hạn | Điểm bão hòa, kiểu lỗi, hành vi từ chối và phục hồi. |
| Spike test | Hệ thống phản ứng thế nào với tăng/giảm tải đột ngột? | Tạo bước nhảy tải nhanh | Thời gian ổn định, backlog, lỗi và khả năng phục hồi. |
| Soak / endurance test | Hệ thống có duy trì ổn định trong thời gian dài không? | Giữ tải ổn định trong thời lượng dài | Rò rỉ bộ nhớ, tăng hàng đợi, suy giảm throughput và tài nguyên. |
| Scalability test | Thêm tài nguyên có cải thiện năng lực không? | Thay đổi số instance hoặc tài nguyên theo từng mức | Năng lực tăng thêm, hiệu quả mở rộng và điểm nghẽn mới. |
| Capacity test | Mức công suất tối đa đáp ứng SLO là bao nhiêu? | Tăng tải có kiểm soát và tìm mức cao nhất còn đạt tiêu chí | Throughput tối đa trong ngưỡng latency/error và giới hạn tài nguyên. |

Không nên gọi một lần chạy ở tải mục tiêu là stress test nếu không có bước vượt tải. Cũng không thể kết luận công suất tối đa từ một lần load test ở một mức cố định.

## 6. Xác định phạm vi hệ thống và ranh giới đo

Kiểm thử hiệu năng cần làm rõ những thành phần nào tham gia vào kết quả. Một hành trình có thể đi qua client, CDN, gateway, nhiều dịch vụ, database, cache, message broker và nhà cung cấp bên ngoài.

### 6.1. Phạm vi bao gồm và loại trừ

Ghi rõ:

- Ứng dụng, endpoint, giao diện hoặc hành trình được đo.
- Dịch vụ, database, cache, queue và hạ tầng tham gia.
- Thành phần bên ngoài được gọi thật, dùng sandbox hay mô phỏng.
- Những phần không nằm trong phạm vi và lý do loại trừ.
- Điểm đặt máy phát tải và đường mạng đi đến hệ thống.
- Cấu hình phiên bản, số instance, tài nguyên và autoscaling.

Nếu dùng mock cho một nhà cung cấp, phép đo không bao gồm độ trễ và giới hạn thực tế của nhà cung cấp đó. Báo cáo cần nêu rõ giới hạn này và có thể cần một phép đo tích hợp riêng với sandbox hoặc môi trường được cho phép.

### 6.2. Chọn mức kiểm thử

- **API hoặc service-level test** phù hợp để đo một dịch vụ hoặc endpoint và xác định năng lực của thành phần.
- **Component performance test** phù hợp để đo một thành phần cùng các phụ thuộc nội bộ cần thiết.
- **End-to-end performance test** phù hợp để đo trải nghiệm của hành trình xuyên nhiều thành phần.
- **Capacity test ở cấp nền tảng** phù hợp để hiểu giới hạn tổng thể và khả năng mở rộng.

Không nên chỉ dùng một phép đo E2E để tìm mọi điểm nghẽn. Khi E2E chậm, cần có metric và trace ở các thành phần để xác định phần thời gian nằm ở đâu.

### 6.3. Kiểm tra tải nền và tác vụ đồng thời

Trong môi trường thật, tác vụ nền như batch, backup, đồng bộ, reindex, consumer queue hoặc job báo cáo có thể chạy cùng lúc với lưu lượng người dùng. Nếu chúng ảnh hưởng đáng kể đến SLO, cần đưa vào mô hình tải hoặc chạy một kịch bản riêng để đánh giá tương tác.

## 7. Thiết kế kịch bản và pha chạy

Một kịch bản hiệu năng cần mô tả rõ tải được tạo ra như thế nào và dữ liệu nào được dùng.

### 7.1. Các pha thường có

1. **Precondition**: xác nhận môi trường, dữ liệu, phiên bản, cấu hình và trạng thái phụ thuộc.
2. **Warm-up**: tăng hoạt động để hệ thống khởi tạo cache, JIT, connection pool hoặc các tài nguyên cần thiết.
3. **Ramp-up**: tăng tải dần đến mức mục tiêu hoặc mức thử nghiệm.
4. **Steady state**: duy trì tải đủ lâu để đo trong điều kiện ổn định.
5. **Ramp-down**: giảm tải có kiểm soát.
6. **Cool-down và cleanup**: chờ hàng đợi xử lý xong nếu phù hợp, thu thập dữ liệu và giải phóng tài nguyên.

Warm-up không nên bị gộp vào cửa sổ đo nếu mục tiêu là đo trạng thái ổn định. Tuy nhiên, nếu mục tiêu là đánh giá thời gian khởi động hoặc hành vi ngay sau deploy, warm-up chính là một phần cần đo. Phạm vi phải nêu rõ lựa chọn này.

### 7.2. Mô tả kịch bản

Một kịch bản nên có:

- Tên, mục tiêu và yêu cầu/SLO liên quan.
- Điểm bắt đầu và kết thúc phép đo.
- Loại workload (open/closed), tốc độ đến hoặc số người dùng ảo.
- Tỷ lệ thao tác, think time và thời gian phiên.
- Dữ liệu đầu vào, kích thước bản ghi và trạng thái ban đầu.
- Pha warm-up, ramp-up, steady state và ramp-down.
- Số lần lặp và cách xử lý kết quả bất thường.
- Chỉ số thu thập và tiêu chí dừng.

### 7.3. Dữ liệu phải đại diện

Dữ liệu quá nhỏ có thể làm cache luôn nóng hoặc truy vấn chỉ đi qua một nhánh dễ. Dữ liệu quá lớn nhưng không giống thực tế cũng có thể tạo ra hành vi khác. Cần xem xét:

- Số lượng người dùng, sản phẩm, đơn hàng hoặc bản ghi.
- Phân bố dữ liệu phổ biến và dữ liệu hiếm.
- Tỷ lệ đọc/ghi và cập nhật đồng thời.
- Kích thước request/response và tệp tải lên/xuống.
- Mức độ trùng lặp khóa, tenant hoặc phân vùng dữ liệu.
- Cache hit/miss và độ mới dữ liệu.

Không sử dụng dữ liệu cá nhân hoặc bí mật thật nếu chưa được phép và chưa có biện pháp bảo vệ phù hợp. Ưu tiên dữ liệu tổng hợp hoặc dữ liệu đã được xử lý an toàn.

## 8. Chỉ số cần thu thập

Một kết quả hiệu năng có ý nghĩa cần kết hợp chỉ số từ phía tải, ứng dụng và hạ tầng.

### 8.1. Chỉ số từ máy phát tải

- Số request hoặc giao dịch được lên lịch và thực sự gửi.
- Throughput tổng và throughput thành công.
- Latency p50, p90, p95, p99 và tối đa khi có ý nghĩa.
- Tỷ lệ lỗi, timeout, kết nối thất bại và request bị từ chối.
- Số người dùng ảo hoặc request đang hoạt động.
- Thời gian của từng hành trình và từng bước quan trọng.

Máy phát tải phải đủ năng lực để tạo tải yêu cầu. Nếu CPU hoặc mạng của máy phát tải bão hòa trước hệ thống, kết quả không đại diện cho công suất của ứng dụng. Với nhiều máy phát, cần đồng bộ thời gian và tổng hợp dữ liệu đúng cách.

### 8.2. Chỉ số ứng dụng và dịch vụ

- Thời gian xử lý theo endpoint hoặc transaction.
- Số request đang xử lý, thread/worker đang hoạt động và connection pool.
- Tỷ lệ lỗi theo loại, timeout và retry.
- Thời gian truy vấn, lock wait và connection wait.
- Độ sâu hàng đợi, tuổi thông điệp và tốc độ consumer xử lý.
- Cache hit ratio, eviction và thời gian truy cập cache.
- Thời gian gọi dịch vụ phụ thuộc và tỷ lệ lỗi theo dependency.

### 8.3. Chỉ số hạ tầng

- CPU, memory, garbage collection và số lần pause.
- Disk I/O, IOPS, dung lượng và độ trễ lưu trữ.
- Network throughput, connection, retransmission và packet loss khi có thể quan sát.
- Số instance, autoscaling event và mức sử dụng từng node.
- Database CPU, active connection, lock, slow query và replication lag.
- Container restart, throttling, quota hoặc giới hạn tài nguyên.

### 8.4. Chỉ số nghiệp vụ

Không chỉ đo máy chủ. Hãy theo dõi số giao dịch nghiệp vụ hoàn tất, số đơn được tạo, tỷ lệ thanh toán thành công, số tác vụ chờ và tính đúng đắn của dữ liệu sau khi chạy tải. Một hệ thống có thể phản hồi nhanh nhưng không tạo được kết quả nghiệp vụ hợp lệ.

## 9. Xác định tiêu chí đạt và điều kiện dừng

Tiêu chí đạt cần phản ánh đồng thời tốc độ, công suất và tính đúng đắn. Ví dụ về một tiêu chí tổng hợp:

- Throughput thành công đạt tối thiểu mức mục tiêu trong cửa sổ steady state.
- p95 và p99 của hành trình nằm trong ngưỡng đã thống nhất.
- Tỷ lệ lỗi thuộc phạm vi đo không vượt giới hạn.
- Không có sai lệch dữ liệu hoặc vi phạm bất biến nghiệp vụ.
- Hàng đợi và tài nguyên không tăng liên tục đến mức gây suy giảm sau cửa sổ đo.
- Hệ thống phục hồi về trạng thái ổn định sau khi giảm tải.

Các ngưỡng phải được lấy từ yêu cầu hoặc được chủ sở hữu dịch vụ thống nhất trước khi chạy. Không thay đổi ngưỡng sau khi thấy kết quả chỉ để biến một lần chạy không đạt thành đạt.

### 9.1. Điều kiện dừng an toàn

Đối với stress, spike hoặc load test trên môi trường có thể ảnh hưởng đến người khác, cần xác định trước ngưỡng dừng, chẳng hạn:

- Tỷ lệ lỗi vượt ngưỡng an toàn trong khoảng thời gian quy định.
- Độ trễ vượt mức có thể phục hồi hoặc hệ thống ngừng đáp ứng.
- Database, queue, CPU hoặc memory đạt giới hạn nguy hiểm.
- Có nguy cơ ảnh hưởng đến tenant, dịch vụ hoặc nhóm khác.
- Phát sinh giao dịch hoặc side effect ngoài phạm vi cho phép.

Người theo dõi phải biết cách dừng tải, thông báo và xác nhận hệ thống trở lại trạng thái bình thường. Không chạy tải lớn trên production hoặc dịch vụ của bên thứ ba khi chưa có phạm vi và sự cho phép phù hợp.

### 9.2. Không đánh giá đạt nếu chỉ có một chỉ số tốt

Ví dụ, throughput đạt nhưng p99 vượt ngưỡng thì mục tiêu chưa đạt. Latency thấp nhưng tỷ lệ lỗi cao cũng chưa đạt. Tài nguyên thấp nhưng hàng đợi tăng liên tục có thể cho thấy hệ thống đang tích lũy công việc chưa xử lý. Hãy đánh giá toàn bộ tiêu chí đã định nghĩa.

## 10. Chuẩn bị môi trường kiểm thử hiệu năng

Môi trường có thể làm thay đổi kết quả đáng kể. Cần ghi lại cấu hình để so sánh và tái hiện.

### 10.1. Mức độ tương đồng với production

Môi trường lý tưởng nên gần với production về:

- Kiến trúc, phiên bản ứng dụng và cấu hình runtime.
- Loại máy, CPU, memory, storage và network.
- Số instance, autoscaling, load balancer và cache.
- Database, schema, chỉ mục và kích thước dữ liệu.
- Dịch vụ phụ thuộc, phiên bản API và chính sách giới hạn.
- Cấu hình bảo mật, TLS và cơ chế xác thực có ảnh hưởng đến hiệu năng.

Nếu môi trường nhỏ hơn production, cần ghi rõ khác biệt và tránh ngoại suy tuyến tính một cách máy móc. Năng lực không luôn tăng tỷ lệ thuận với CPU hoặc số instance do lock, network, database và điểm nghẽn dùng chung.

### 10.2. Kiểm soát nhiễu

- Hạn chế các tác vụ không liên quan trong thời gian đo.
- Ghi nhận lịch backup, batch, deploy hoặc hoạt động của nhóm khác.
- Xác nhận máy phát tải không bị giới hạn tài nguyên.
- Kiểm tra đồng bộ đồng hồ giữa các thành phần cần đối chiếu.
- Dùng cùng cấu hình và dữ liệu khi so sánh hai phiên bản.
- Chạy lặp lại đủ số lần để nhận biết biến động.

Nếu không thể loại bỏ nhiễu, báo cáo cần mô tả ảnh hưởng và giới hạn kết luận.

### 10.3. Làm nóng cache và trạng thái ban đầu

Cache lạnh và cache nóng có thể tạo kết quả rất khác. Hãy xác định mục tiêu là đo trạng thái nào. Nếu người dùng thường truy cập dữ liệu mới sau deploy, cần có kịch bản cache lạnh. Nếu mục tiêu là tải ổn định hàng ngày, cần warm-up trước cửa sổ đo. Tương tự, connection pool, JIT và autoscaling có thể cần thời gian ổn định.

Không trộn kết quả của trạng thái cache khác nhau vào một số liệu duy nhất nếu chúng đại diện cho những điều kiện sử dụng khác nhau.

## 11. Phân tích kết quả và tìm điểm nghẽn

Khi một mục tiêu không đạt, không nên kết luận ngay rằng cần thêm máy chủ. Cần xác định thành phần giới hạn và quan hệ giữa tải, độ trễ, throughput và tài nguyên.

### 11.1. Đọc xu hướng theo mức tải

Quan sát khi tăng tải:

- Throughput thành công có tăng tương ứng không?
- Latency tăng từ từ hay tăng đột ngột sau một điểm tải?
- Error rate và timeout bắt đầu tăng ở mức nào?
- Hàng đợi có tăng nhanh hơn tốc độ consumer xử lý không?
- CPU, memory, disk, network hoặc database có bão hòa không?
- Khi giảm tải, hệ thống có trở lại trạng thái ổn định không?

Nếu throughput không tăng dù tải tiếp tục tăng, hệ thống có thể đã chạm điểm bão hòa. Nếu latency tăng mạnh và hàng đợi dài ra, có thể thành phần downstream không theo kịp tốc độ đến.

### 11.2. Các dạng điểm nghẽn thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| CPU cao và throughput không tăng | Thuật toán tốn CPU, serialization, contention hoặc thread hoạt động quá nhiều | Profiling CPU, flame graph, kiểm tra lock và số worker. |
| Memory tăng liên tục | Rò rỉ bộ nhớ, cache không giới hạn hoặc giữ object quá lâu | Heap profile, GC log, cache eviction và soak test. |
| Database chậm | Truy vấn thiếu index, lock, connection pool hoặc I/O | Slow query, execution plan, lock wait, connection và storage. |
| Hàng đợi tăng liên tục | Consumer thiếu năng lực hoặc dependency chậm | Queue depth, tuổi message, throughput producer/consumer và retry. |
| p99 cao nhưng p50 tốt | Một số đường đi chậm, phân bố dữ liệu lệch, GC pause hoặc dependency tail latency | Phân tích trace theo request, dữ liệu và dependency. |
| Lỗi tăng khi tải cao | Quá tải connection, thread, quota hoặc giới hạn dịch vụ | Error code, resource saturation, rate limit và timeout chain. |
| Máy phát tải bão hòa | Số worker, CPU hoặc mạng của generator không đủ | Chạy nhiều generator, theo dõi generator và kiểm tra lịch phát tải. |

Các dấu hiệu chỉ gợi ý nguyên nhân. Cần kết hợp metric, log, trace và profiling để xác nhận.

### 11.3. Truy vết thời gian qua nhiều thành phần

Với hành trình nhiều dịch vụ, distributed tracing giúp phân rã thời gian thành các span. Ví dụ, tổng thời gian API là 1,2 giây có thể gồm gateway 30 ms, Order service 100 ms, truy vấn database 700 ms và gọi Payment provider 300 ms. Những con số này chỉ minh họa cách phân tích; cần tránh cộng các span song song như thể chúng luôn chạy tuần tự.

Correlation ID hoặc trace ID cần được truyền qua các thành phần để nối một giao dịch. Không ghi dữ liệu nhạy cảm vào span hoặc log chỉ để thuận tiện điều tra.

## 12. Báo cáo kết quả và giới hạn kết luận

Một báo cáo hiệu năng nên giúp người đọc hiểu điều kiện thử, kết quả và mức độ đại diện của phép đo.

Nội dung tối thiểu:

1. Mục tiêu, SLO và phạm vi hành trình/API.
2. Phiên bản ứng dụng, cấu hình hạ tầng và môi trường.
3. Mô hình tải, dữ liệu, số generator, tốc độ đến và thời gian chạy.
4. Các pha warm-up, ramp-up, steady state và ramp-down.
5. Latency p50/p90/p95/p99, throughput gửi và thành công, error rate.
6. Metric ứng dụng, database, queue, cache và hạ tầng.
7. Kết quả đối chiếu nghiệp vụ và dữ liệu.
8. Điểm nghẽn, giả thuyết đã xác minh và vấn đề chưa rõ.
9. Tiêu chí đạt/không đạt và sai lệch so với mục tiêu.
10. Giới hạn môi trường, nhiễu, phụ thuộc mô phỏng và rủi ro còn lại.

Kết luận nên nói rõ hệ thống đạt mục tiêu nào, trong điều kiện nào và chưa chứng minh được điều gì. Một lần chạy thành công ở 100 RPS không chứng minh hệ thống có thể xử lý 500 RPS. Một phép đo trên sandbox không chứng minh độ trễ của nhà cung cấp production.

## 13. Ví dụ xuyên suốt: xác định phạm vi hiệu năng cho cửa hàng trực tuyến

Giả sử cửa hàng muốn bảo đảm hành trình xem sản phẩm và đặt hàng hoạt động tốt trong đợt khuyến mại. Nhóm đã thống nhất mục tiêu minh họa sau:

- API tìm kiếm: p95 không quá 400 ms tại 300 RPS.
- API xem chi tiết: p95 không quá 500 ms tại 200 RPS.
- Hành trình xác nhận đơn hàng: p95 không quá 2 giây tại 40 giao dịch/giây.
- Tỷ lệ lỗi kỹ thuật thuộc phạm vi đo không vượt quá ngưỡng đã được chủ sở hữu dịch vụ phê duyệt.
- Các giao dịch đặt hàng thành công phải tạo đúng một đơn, đúng tổng tiền và trạng thái thanh toán phù hợp.

Các con số trên là ví dụ để minh họa cách xác định phạm vi, không phải khuyến nghị mặc định.

### 13.1. Mô hình tải

Nhóm dùng dữ liệu analytics để xây dựng tỷ trọng hành trình, sau đó xác định workload gồm tìm kiếm, xem chi tiết, đăng nhập, xem giỏ hàng và đặt hàng. Tải được tăng dần đến mức cao điểm, duy trì trong cửa sổ đo và có một kịch bản spike riêng khi bắt đầu chương trình khuyến mại.

Nhóm cũng xác định kích thước danh mục sản phẩm, tỷ lệ truy vấn cache hit/miss, số lượng đơn hàng lịch sử và phân bố khách hàng. Các dữ liệu dùng trong test là dữ liệu tổng hợp, có thể tái tạo và không chứa thông tin cá nhân thật.

### 13.2. Các loại kiểm thử

1. **Baseline**: chạy ở tải thấp để xác nhận môi trường và thu số liệu tham chiếu.
2. **Load test**: tăng đến tải cao điểm và xác minh latency, throughput thành công, error rate.
3. **Spike test**: tăng lưu lượng tìm kiếm và xem sản phẩm nhanh trong thời gian ngắn, quan sát autoscaling và queue.
4. **Stress test**: tăng tải vượt mục tiêu để xác định điểm bão hòa và hành vi từ chối.
5. **Soak test**: duy trì tải đại diện đủ lâu để phát hiện memory leak hoặc queue tăng dần.
6. **Capacity test**: tăng tải từng bước để xác định mức cao nhất vẫn đáp ứng các SLO đã đặt.

### 13.3. Phạm vi quan sát

- Generator: số request thực gửi, latency phân vị, throughput và lỗi.
- Gateway và service: thời gian theo endpoint, connection, thread, timeout và retry.
- Database: query latency, connection pool, lock và I/O.
- Cache: hit ratio, eviction và độ trễ.
- Payment provider: thời gian phản hồi, lỗi và giới hạn sandbox; nếu mô phỏng thì ghi rõ.
- Nghiệp vụ: số đơn tạo thành công, tổng tiền, giao dịch trùng và trạng thái cuối.

### 13.4. Tiêu chí kết luận

Nhóm chỉ kết luận đạt khi từng mục tiêu latency và throughput đều đạt trong cửa sổ đo, tỷ lệ lỗi nằm trong ngưỡng, dữ liệu nghiệp vụ đúng và hệ thống không có dấu hiệu suy giảm kéo dài. Nếu API tìm kiếm đạt nhưng hành trình đặt hàng không đạt vì database lock, báo cáo phải nêu riêng kết quả và điểm nghẽn đó thay vì kết luận chung rằng hệ thống đã đạt hiệu năng.

## 14. Những sai lầm thường gặp

- **Mục tiêu chỉ có từ “nhanh” hoặc “chịu tải cao”**: không thể thiết kế phép đo nhất quán. Hãy xác định chỉ số, ngưỡng và điều kiện.
- **Đồng nhất người dùng đăng nhập với người dùng đồng thời**: số phiên không cho biết tốc độ thao tác. Hãy mô tả hành vi, think time và tốc độ đến.
- **Chỉ đo request gửi đi**: tải phát ra có thể cao nhưng hệ thống không hoàn tất công việc. Hãy đo throughput thành công và error rate.
- **Chỉ nhìn độ trễ trung bình**: trải nghiệm chậm ở p95/p99 bị che khuất. Hãy theo dõi phân vị và số lượng mẫu.
- **Tạo tải không giống thực tế**: dữ liệu, tỷ lệ thao tác và thời điểm cao điểm không đại diện. Hãy xây workload từ analytics hoặc nghiệp vụ.
- **Không kiểm tra máy phát tải**: generator bão hòa khiến kết quả sai lệch. Hãy quan sát tài nguyên và tốc độ gửi thực tế.
- **Dùng môi trường khác biệt nhưng không công bố**: kết quả bị ngoại suy sai. Hãy ghi cấu hình và giới hạn môi trường.
- **Bỏ qua dữ liệu nghiệp vụ**: throughput cao nhưng đơn hàng hoặc trạng thái sai. Hãy xác minh hậu điều kiện và bất biến.
- **Chạy stress test mà không có ngưỡng dừng**: có thể ảnh hưởng môi trường dùng chung hoặc dịch vụ bên ngoài. Hãy lập kế hoạch an toàn trước khi chạy.
- **Kết luận công suất từ một mức tải duy nhất**: chưa xác định được điểm bão hòa. Hãy tăng tải có kiểm soát và đo mức cao nhất còn đạt SLO.
- **Thay ngưỡng sau khi thấy kết quả**: làm mất tính khách quan của phép kiểm tra. Hãy thống nhất tiêu chí trước khi thực thi.

## 15. Quy trình chuyển mục tiêu thành phạm vi kiểm thử hiệu năng

Nhóm có thể áp dụng trình tự sau:

1. **Làm rõ mục tiêu nghiệp vụ**: xác định hành trình quan trọng, thời điểm cao điểm và ảnh hưởng nếu chậm hoặc không xử lý được.
2. **Định nghĩa chỉ số**: chọn latency, throughput, concurrency, error rate và thời gian hoàn tất; nêu điểm đo và cách tính.
3. **Đặt ngưỡng và điều kiện**: thống nhất SLO, tải, dữ liệu, môi trường và cửa sổ đo.
4. **Xây workload model**: mô tả nhóm người dùng, tỷ lệ thao tác, think time, tốc độ đến và tính mùa vụ.
5. **Chọn loại kiểm thử**: baseline, load, stress, spike, soak, scalability hoặc capacity theo câu hỏi cần trả lời.
6. **Chốt ranh giới và phụ thuộc**: xác định thành phần thật, sandbox, mô phỏng và phần nằm ngoài phạm vi.
7. **Chuẩn bị môi trường và quan sát**: kiểm tra generator, cấu hình, dữ liệu, metric, log, trace và điều kiện dừng.
8. **Thực thi theo pha**: warm-up, ramp-up, steady state, ramp-down và cleanup theo kế hoạch.
9. **Đánh giá đa chiều**: đối chiếu latency, throughput thành công, lỗi, tài nguyên và kết quả nghiệp vụ.
10. **Báo cáo và cải tiến**: nêu điểm nghẽn, giới hạn kết luận, rủi ro còn lại và kiểm thử lại sau tối ưu.

## 16. Tự kiểm tra

Trước khi phê duyệt phạm vi kiểm thử hiệu năng, hãy tự hỏi:

- Mục tiêu tốc độ và công suất có gắn với hành trình hoặc API cụ thể không?
- Chỉ số, ngưỡng, điểm đo và cửa sổ đo đã được định nghĩa chưa?
- Throughput có tính trên công việc thành công không?
- Mô hình tải có phản ánh tỷ lệ thao tác, think time và thời điểm cao điểm không?
- Đã phân biệt concurrency với số người dùng đăng nhập chưa?
- Loại kiểm thử được chọn có trả lời đúng câu hỏi về tải, stress, spike, soak hoặc capacity không?
- Môi trường, dữ liệu và máy phát tải có đủ đại diện và được ghi nhận không?
- Có thu thập metric ứng dụng, hạ tầng và kết quả nghiệp vụ không?
- Tiêu chí đạt và điều kiện dừng đã được thống nhất trước khi chạy chưa?
- Báo cáo có nêu giới hạn và phần chưa được chứng minh không?

## Kết luận

Để kiểm thử hiệu năng có giá trị, mục tiêu tốc độ và công suất phải được chuyển thành chỉ số, ngưỡng, mô hình tải, ranh giới hệ thống và điều kiện đo cụ thể. Phạm vi cần phản ánh hành vi người dùng, phân biệt độ trễ với throughput và công suất, đồng thời theo dõi lỗi, tài nguyên và kết quả nghiệp vụ. Khi chọn đúng loại kiểm thử, chuẩn bị môi trường đại diện, đặt tiêu chí trước khi chạy và báo cáo rõ giới hạn, nhóm có thể đánh giá đáng tin cậy hệ thống đáp ứng nhu cầu hiệu năng đến đâu.
