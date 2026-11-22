# Phối hợp với bảo mật, hiệu năng, trải nghiệm và bên thứ ba

Chất lượng của một hệ thống không chỉ được quyết định bởi việc chức năng có chạy đúng hay không. Một thay đổi có thể đáp ứng yêu cầu nghiệp vụ nhưng vẫn làm lộ dữ liệu, phản hồi quá chậm, khó sử dụng với một nhóm người dùng hoặc không tương thích với dịch vụ do nhà cung cấp bên ngoài vận hành. Những rủi ro này thường nằm ở các ranh giới giữa nhóm phát triển, kiểm thử, bảo mật, vận hành, thiết kế trải nghiệm và đối tác.

Vì vậy, chiến lược kiểm thử cần xác định cách các bên phối hợp từ lúc phân tích yêu cầu đến khi phát hành và theo dõi sau triển khai. Mỗi bên mang đến một góc nhìn và bằng chứng khác nhau: bảo mật đánh giá cách hệ thống chống lại hành vi lạm dụng; hiệu năng đánh giá khả năng đáp ứng tải và mục tiêu dịch vụ; trải nghiệm đánh giá khả năng người dùng hoàn thành công việc; bên thứ ba xác định hợp đồng, giới hạn và hành vi của phụ thuộc bên ngoài. Nhóm sản phẩm và kỹ thuật kết hợp các kết quả này để đưa ra quyết định chất lượng.

## 1. Vì sao cần phối hợp liên chức năng?

Một rủi ro thường không dừng ở ranh giới của một nhóm. Ví dụ:

- Thêm bước xác thực mạnh có thể giảm rủi ro chiếm tài khoản nhưng làm hành trình đăng nhập khó hoàn thành hơn.
- Mã hóa hoặc kiểm tra quyền bổ sung có thể ảnh hưởng latency và CPU.
- Tối ưu cache có thể cải thiện tốc độ nhưng tạo nguy cơ dữ liệu nhạy cảm bị dùng chung giữa tenant.
- Thay đổi API tích hợp có thể cải thiện nội bộ nhưng phá vỡ consumer của nhà cung cấp hoặc đối tác.
- Thêm CAPTCHA hoặc giới hạn tốc độ có thể chống bot nhưng ngăn người dùng hợp lệ hoàn tất giao dịch.

Nếu các nhóm chỉ kiểm tra phần việc của mình vào cuối dự án, xung đột thường được phát hiện muộn, khi chi phí thay đổi cao và ít thời gian để xử lý. Phối hợp sớm giúp làm rõ tiêu chí chấp nhận, dữ liệu cần dùng, môi trường, phụ thuộc và trách nhiệm trước khi xây dựng giải pháp.

### 1.1. Kết quả mong đợi

Phối hợp tốt cần tạo ra:

- Mục tiêu chất lượng chung và tiêu chí đo được.
- Rủi ro liên chức năng được nhận diện từ sớm.
- Phạm vi kiểm thử và bằng chứng phù hợp với từng rủi ro.
- Người chịu trách nhiệm cho mỗi kiểm tra và mỗi phụ thuộc.
- Môi trường, dữ liệu và quyền truy cập sẵn sàng.
- Quy trình xử lý phát hiện, xung đột và ngoại lệ.
- Quyết định phát hành có thể giải thích và truy vết.

Phối hợp không có nghĩa mọi nhóm phải tham gia mọi cuộc họp hoặc phê duyệt mọi thay đổi. Mức tham gia cần dựa trên rủi ro, phạm vi ảnh hưởng và chuyên môn cần thiết.

## 2. Các bên liên quan và đóng góp của họ

| Bên liên quan | Góc nhìn chính | Đóng góp cho chiến lược kiểm thử |
|---|---|---|
| Product owner/nghiệp vụ | Giá trị, quy tắc và ưu tiên sản phẩm | Mục tiêu, hành trình, tiêu chí chấp nhận và mức rủi ro nghiệp vụ |
| Engineering/development | Thiết kế và triển khai hệ thống | Kiến trúc, testability, unit/component test, xử lý lỗi và khắc phục |
| QA/test engineering | Chất lượng và bằng chứng kiểm thử | Phân tích rủi ro, test design, điều phối test, báo cáo và đánh giá |
| Security | Bảo mật, quyền riêng tư và lạm dụng | Threat model, security requirement, kiểm thử và đánh giá lỗ hổng |
| Performance/SRE/platform | Năng lực, độ tin cậy và vận hành | SLO, workload, capacity, quan sát hệ thống và kiểm thử phục hồi |
| UX/UI/research/accessibility | Khả năng sử dụng và tính bao trùm | Nghiên cứu người dùng, usability test, accessibility và nội dung |
| Data/privacy/compliance | Dữ liệu và nghĩa vụ quản trị | Phân loại dữ liệu, quyền sử dụng, lưu giữ, ẩn danh và tuân thủ |
| Nhà cung cấp/đối tác | Dịch vụ, API hoặc nền tảng bên ngoài | Tài liệu hợp đồng, sandbox, giới hạn, thông báo thay đổi và hỗ trợ |
| Release/operations/support | Triển khai và phản hồi vận hành | Readiness, runbook, giám sát, hỗ trợ người dùng và phản ứng sự cố |

Một cá nhân có thể đảm nhiệm nhiều vai trò trong nhóm nhỏ. Dù cơ cấu tổ chức khác nhau, cần chỉ rõ ai đưa ra yêu cầu, ai thực hiện kiểm tra, ai đánh giá bằng chứng và ai có quyền chấp nhận rủi ro.

## 3. Thiết lập cách phối hợp ngay từ giai đoạn phân tích

### 3.1. Xác định mục tiêu và ranh giới

Khi một tính năng hoặc thay đổi được đề xuất, nhóm cần cùng nhau làm rõ:

- Người dùng và quy trình nghiệp vụ bị ảnh hưởng.
- Dữ liệu được thu thập, lưu trữ, truyền hoặc chia sẻ.
- Các dịch vụ và đối tác tham gia vào hành trình.
- Mục tiêu hiệu năng và độ tin cậy.
- Các yêu cầu bảo mật, quyền riêng tư và accessibility.
- Điều kiện môi trường, nền tảng và thiết bị được hỗ trợ.
- Những thay đổi có thể ảnh hưởng đến người dùng hoặc consumer hiện hữu.

Vẽ sơ đồ luồng dữ liệu và luồng tương tác để xác định ranh giới tin cậy, điểm tích hợp và các thành phần có trách nhiệm. Một sơ đồ đơn giản cũng giúp phát hiện sớm việc dữ liệu đi qua bên thứ ba hoặc một thao tác người dùng phụ thuộc vào nhiều dịch vụ.

### 3.2. Chuyển yêu cầu thành tiêu chí có thể kiểm chứng

Các yêu cầu như "an toàn", "nhanh", "dễ sử dụng" hoặc "tương thích" quá rộng nếu không có tiêu chí đo.

| Yêu cầu chung | Cách cụ thể hóa |
|---|---|
| An toàn | Người dùng không có quyền không thể đọc dữ liệu tenant khác; phiên hết hạn bị từ chối; dữ liệu nhạy cảm được bảo vệ khi truyền và lưu |
| Nhanh | Phân vị latency của hành trình quan trọng không vượt ngưỡng ở workload và quy mô dữ liệu đã xác định |
| Dễ sử dụng | Người dùng mục tiêu hoàn thành tác vụ đại diện với tỷ lệ thành công, thời gian và mức trợ giúp trong giới hạn |
| Dễ tiếp cận | Các thao tác chính dùng được bằng bàn phím, có tên accessible và thông tin không chỉ truyền qua màu sắc |
| Tích hợp ổn định | API đáp ứng hợp đồng, timeout/retry có giới hạn và xử lý được thay đổi hoặc gián đoạn của đối tác |

Tiêu chí nên nêu điều kiện đo, môi trường, dữ liệu, mức tải, nhóm người dùng và cách lưu bằng chứng. Khi chưa thể đặt một ngưỡng chính xác, ghi rõ giả định và người cần xác nhận.

### 3.3. Đưa chuyên gia vào đúng thời điểm

- Security tham gia khi xác định dữ liệu, danh tính, quyền, ranh giới tin cậy và luồng nhạy cảm.
- Performance/SRE tham gia khi có mục tiêu latency, throughput, capacity, độ sẵn sàng hoặc thay đổi kiến trúc ảnh hưởng tài nguyên.
- UX/accessibility tham gia khi thay đổi hành trình, tương tác, nội dung, thiết bị hoặc nhóm người dùng.
- Bên thứ ba tham gia khi cần xác nhận API, sandbox, quota, hợp đồng dịch vụ, thời gian bảo trì hoặc kế hoạch thay đổi.

Mời chuyên gia trước khi thiết kế đã bị cố định giúp họ tác động vào giải pháp, thay vì chỉ đánh giá một sản phẩm gần hoàn tất.

## 4. Phối hợp với bảo mật

Bảo mật cần được tích hợp vào vòng đời phát triển và kiểm thử. Mục tiêu là xác minh hệ thống bảo vệ tài sản, dữ liệu và hành vi quan trọng trước các mối đe dọa phù hợp với bối cảnh.

### 4.1. Xác định tài sản và mối đe dọa

Nhóm phát triển, QA và security cùng lập danh sách:

- Dữ liệu nhạy cảm, thông tin cá nhân, bí mật và token.
- Tài khoản, vai trò, quyền và cơ chế xác thực.
- API công khai, endpoint nội bộ và giao diện quản trị.
- Luồng dữ liệu giữa client, server, database và bên thứ ba.
- Các thao tác quan trọng như thanh toán, thay đổi quyền, xuất dữ liệu và xóa tài khoản.
- Tác nhân có thể lạm dụng, cấu hình sai hoặc truy cập ngoài dự kiến.

Có thể dùng threat modeling để xem xét spoofing, tampering, repudiation, information disclosure, denial of service và elevation of privilege. Đây là các nhóm câu hỏi gợi ý; mô hình cần điều chỉnh theo kiến trúc và mối đe dọa thực tế.

### 4.2. Chuyển threat model thành kiểm thử

| Rủi ro | Kiểm tra gợi ý | Bằng chứng |
|---|---|---|
| Truy cập trái phép | Kiểm tra quyền theo vai trò, tenant và tài nguyên | Kết quả request hợp lệ/bị từ chối, audit log |
| Chiếm hoặc giả mạo phiên | Kiểm tra vòng đời token, hết hạn, thu hồi và cookie | Test report và cấu hình bảo mật |
| Injection hoặc dữ liệu đầu vào độc hại | Kiểm thử validation, encoding và truy vấn | Kết quả test và log an toàn |
| Lộ dữ liệu | Kiểm tra response, log, cache, export và dữ liệu truyền | Báo cáo kiểm tra dữ liệu và quyền |
| Lạm dụng API | Kiểm tra rate limit, quota và xử lý burst | Metric, response và alert |
| Thay đổi dữ liệu trái phép | Kiểm tra authorization tại từng thao tác và tính toàn vẹn | Trạng thái trước/sau và audit trail |
| Dependency có lỗ hổng | Quét dependency, xác minh đường sử dụng và kiểm tra bản vá | SBOM/scan report và quyết định xử lý |

Security test cần có phạm vi được phép, môi trường phù hợp và dữ liệu thử nghiệm. Không thực hiện kiểm thử xâm nhập trên hệ thống hoặc dịch vụ bên thứ ba nếu chưa có quyền và kế hoạch phối hợp.

### 4.3. Phối hợp khi phát hiện lỗ hổng

Khi phát hiện vấn đề:

1. Lưu bằng chứng đủ để tái hiện nhưng tránh ghi thêm dữ liệu nhạy cảm.
2. Xác định mức độ nghiêm trọng, điều kiện khai thác và phạm vi ảnh hưởng.
3. Thông báo theo kênh bảo mật đã thống nhất.
4. Phân công owner khắc phục và thời hạn theo mức rủi ro.
5. Xây dựng test hồi quy cho điều kiện gây lỗi.
6. Xác minh bản sửa trong môi trường phù hợp.
7. Cập nhật trạng thái rủi ro và quyết định phát hành.

Không đưa chi tiết khai thác nhạy cảm vào kênh công khai hoặc ticket có quyền truy cập quá rộng. Báo cáo cần đủ thông tin cho người có trách nhiệm điều tra, theo nguyên tắc quyền truy cập tối thiểu.

### 4.4. Quyền riêng tư và dữ liệu kiểm thử

Security, privacy/data owner và QA cần thống nhất:

- Dữ liệu nào được phép dùng trong môi trường test.
- Khi nào phải dùng dữ liệu tổng hợp hoặc ẩn danh.
- Ai được truy cập dữ liệu và secret.
- Cách lưu, truyền, chia sẻ và xóa dữ liệu.
- Thời gian lưu artifact, log, video và bản chụp.
- Cách xử lý dữ liệu trong báo cáo lỗi.

Dữ liệu đã giả danh vẫn có thể có nguy cơ tái nhận dạng. Không mặc định rằng dữ liệu biến đổi là vô hại; cần tuân theo chính sách và đánh giá của chủ sở hữu dữ liệu.

## 5. Phối hợp với hiệu năng và độ tin cậy

Hiệu năng là thuộc tính của toàn hành trình và các phụ thuộc, không chỉ là thời gian chạy của một endpoint. Performance/SRE, development và QA cần cùng xác định mục tiêu, workload, môi trường và cách diễn giải.

### 5.1. Thống nhất SLI, SLO và ngưỡng

Các bên cần thống nhất:

- SLI nào phản ánh trải nghiệm hoặc năng lực cần quan tâm.
- SLO hoặc ngưỡng chấp nhận cho latency, availability, error rate và throughput.
- Phân vị cần theo dõi như p50, p95 hoặc p99.
- Hành trình, nhóm người dùng và khu vực cần đo.
- Tải bình thường, cao điểm, burst và tải kéo dài.
- Quy mô dữ liệu, cache và trạng thái phụ thuộc.

Không dùng trung bình latency làm chỉ số duy nhất. Một số ít request rất chậm có thể ảnh hưởng nghiêm trọng đến trải nghiệm dù trung bình vẫn thấp.

### 5.2. Thiết kế workload cùng nhóm sản phẩm

Product và analytics giúp xác định hành trình và tỷ lệ thao tác. Performance/SRE xác định tải, môi trường và giới hạn. Development cung cấp kiến trúc và phụ thuộc. QA xây dựng kịch bản và xác minh kết quả.

Workload nên nêu:

- Arrival rate, concurrency và think time.
- Request mix và tỷ lệ đọc/ghi.
- Payload và phân bố dữ liệu.
- Số tenant, người dùng và tài nguyên nóng.
- Tải nền từ scheduler, queue hoặc tích hợp.
- Thời lượng warm-up, steady state và soak.

Các con số cần dựa trên dữ liệu sử dụng hoặc dự báo đã được xác nhận. Nếu chỉ có giả định, ghi rõ và chạy phân tích độ nhạy.

### 5.3. Phân biệt nút thắt và nguyên nhân

Khi test tải thất bại, các bên cùng phân tích:

- Generator có tạo đủ tải hay bị bão hòa?
- Ứng dụng có cạn CPU, memory, thread hoặc connection không?
- Database có lock, truy vấn chậm hoặc I/O cao không?
- Cache có miss, eviction hoặc hot key bất thường không?
- Broker có backlog hoặc consumer lag không?
- Dịch vụ bên thứ ba có tăng latency hoặc trả rate limit không?
- Môi trường test có cấu hình khác đáng kể so với môi trường mục tiêu không?

Performance/SRE giúp đọc metric và trace; development phân tích đường xử lý; QA xác minh kịch bản và tính đúng của workload. Không nên quy lỗi cho một dịch vụ chỉ dựa vào một biểu đồ đơn lẻ.

### 5.4. Kiểm tra khả năng phục hồi

Ngoài tải bình thường, có thể cần kiểm tra:

- Tăng tải đột ngột và giảm tải.
- Một instance hoặc phụ thuộc bị gián đoạn.
- Timeout, retry và circuit breaker.
- Backlog tăng rồi được xử lý sau khi phục hồi.
- Hạn mức quota và hành vi khi bị từ chối.
- Khả năng quay về mức dịch vụ mục tiêu sau sự cố.

Các thử nghiệm gây gián đoạn cần được lập kế hoạch, có giới hạn và được phê duyệt cho môi trường phù hợp.

## 6. Phối hợp với UX, usability và accessibility

Kiểm thử trải nghiệm cần xác minh người dùng có thể hoàn thành mục tiêu trong bối cảnh sử dụng thực tế. Một chức năng đúng về logic vẫn có thể khó tìm, khó hiểu, không phù hợp thiết bị hoặc không sử dụng được với công nghệ hỗ trợ.

### 6.1. Xác định hành trình và nhóm người dùng

UX/research, product và QA cùng xác định:

- Nhóm người dùng mục tiêu và nhu cầu của họ.
- Công việc cần hoàn thành và điểm bắt đầu/kết thúc.
- Ngữ cảnh sử dụng, thiết bị và môi trường.
- Các bước dễ nhầm lẫn hoặc có hậu quả cao.
- Ngôn ngữ, nội dung, trạng thái và thông báo lỗi.
- Những rào cản có thể ảnh hưởng người dùng khuyết tật.

Không chỉ kiểm thử với người thiết kế hoặc người đã biết cách sử dụng sản phẩm. Người tham gia cần đại diện phù hợp cho nhóm người dùng mà tính năng phục vụ.

### 6.2. Kết hợp phương pháp đánh giá

| Phương pháp | Mục tiêu | Vai trò phối hợp |
|---|---|---|
| Usability test có người tham gia | Quan sát người dùng hoàn thành tác vụ | UX thiết kế nghiên cứu; QA ghi nhận lỗi và tái hiện; product xác nhận mục tiêu |
| Heuristic review | Phát hiện vấn đề theo nguyên tắc usability | UX và chuyên gia đánh giá |
| Accessibility audit | Kiểm tra bàn phím, semantic, contrast, screen reader và cấu trúc | Accessibility specialist, UX và development |
| Analytics/funnel | Phát hiện bước rơi rụng hoặc hành vi bất thường | Product/data phân tích; QA tái tạo hành trình |
| A/B hoặc experiment | So sánh tác động của các phương án | Product/research xác định giả thuyết và chỉ số |
| UI automation | Kiểm tra hồi quy hành trình ổn định | QA/development tự động hóa các trạng thái quan trọng |

UI automation không thay thế nghiên cứu usability. Một test script có thể hoàn thành hành trình vì nó biết chính xác selector và thứ tự thao tác, trong khi người dùng thật không tìm thấy nút hoặc không hiểu nội dung.

### 6.3. Tiêu chí trải nghiệm có thể kiểm chứng

Ví dụ:

- Tỷ lệ người tham gia hoàn thành tác vụ trong giới hạn thời gian.
- Số lỗi hoặc lần cần trợ giúp trong một hành trình.
- Tỷ lệ bỏ dở ở từng bước.
- Khả năng hoàn thành bằng bàn phím.
- Trạng thái focus được hiển thị rõ.
- Thành phần giao diện có tên và vai trò accessible.
- Thông báo lỗi giải thích vấn đề và bước tiếp theo.
- Nội dung không phụ thuộc duy nhất vào màu sắc, âm thanh hoặc vị trí.

Các chỉ số nghiên cứu người dùng cần được diễn giải theo cỡ mẫu, nhóm tham gia và phương pháp. Không khái quát kết quả của vài người tham gia thành kết luận thống kê cho toàn bộ người dùng.

### 6.4. Xử lý xung đột giữa bảo mật và trải nghiệm

Một biện pháp bảo mật có thể tạo thêm bước hoặc hạn chế hành vi. Khi có xung đột:

1. Xác định mục tiêu bảo mật không thể thương lượng và mức rủi ro cần giảm.
2. Xác định tác động đến người dùng và nhóm bị ảnh hưởng.
3. Cùng thiết kế phương án thay thế như xác thực theo rủi ro, thông báo rõ hoặc cơ chế phục hồi tài khoản an toàn.
4. Kiểm thử cả khả năng chống lạm dụng và khả năng hoàn thành tác vụ hợp lệ.
5. Đánh giá bằng chứng trước khi quyết định.

Không nên hy sinh một yêu cầu bảo mật bắt buộc chỉ để giảm số bước. Cũng không nên giả định một biện pháp bảo mật có thể chấp nhận được chỉ vì nó hoạt động đúng về kỹ thuật.

## 7. Phối hợp với bên thứ ba và nhà cung cấp

Bên thứ ba có thể cung cấp thanh toán, định danh, email/SMS, bản đồ, lưu trữ, phân tích, API dữ liệu hoặc nền tảng cloud. Hành vi của họ ảnh hưởng trực tiếp đến chất lượng hệ thống, nhưng nhóm phát triển không kiểm soát toàn bộ implementation và lịch vận hành.

### 7.1. Xác định hợp đồng tích hợp

Trước khi kiểm thử, thống nhất:

- API/schema và phiên bản được hỗ trợ.
- Cơ chế xác thực, quyền và vòng đời credential.
- Timeout, retry, idempotency và thứ tự sự kiện.
- Rate limit, quota và giới hạn kích thước.
- Mã lỗi, thông báo và hành vi khi dịch vụ không sẵn sàng.
- Webhook, callback, chữ ký và cách xác minh.
- Sandbox, dữ liệu thử nghiệm và các giới hạn khác production.
- SLA/SLO, lịch bảo trì và kênh hỗ trợ.
- Chính sách thay đổi, deprecation và thông báo trước.

Tài liệu API là một nguồn tham khảo; khi cần, xác nhận các giả định quan trọng với nhà cung cấp và lưu phiên bản hợp đồng đã dùng.

### 7.2. Thiết kế test cho phụ thuộc bên ngoài

Nên kết hợp nhiều lớp:

- **Contract test:** xác minh request, response, schema và hành vi đã thỏa thuận.
- **Component test với stub/mock:** kiểm tra logic ứng dụng khi phụ thuộc trả kết quả cụ thể.
- **Sandbox integration test:** xác minh giao tiếp thực tế với môi trường thử nghiệm của nhà cung cấp.
- **Resilience test:** kiểm tra timeout, retry, rate limit, lỗi tạm thời và gián đoạn.
- **Production synthetic monitoring:** nếu được phép, thực hiện giao dịch tổng hợp an toàn để theo dõi sau triển khai.

Mock không chứng minh dịch vụ thật hoạt động. Sandbox cũng có thể khác production về dữ liệu, quota hoặc khả năng. Báo cáo cần nêu rõ lớp kiểm tra đã chạy và phần nào vẫn chưa được xác minh.

### 7.3. Quản lý quota và chi phí

Kiểm thử tích hợp có thể tiêu thụ quota hoặc phát sinh chi phí. Cần:

- Dùng tài khoản và project dành riêng cho test.
- Đặt giới hạn request và lịch chạy.
- Tạo dữ liệu có thể dọn và tránh gửi giao dịch thật.
- Theo dõi quota, rate limit và chi phí.
- Phối hợp với nhà cung cấp khi cần tăng hạn mức.
- Không chạy stress test trên dịch vụ bên ngoài nếu chưa được cho phép.

### 7.4. Thay đổi và sự cố từ nhà cung cấp

Khi nhà cung cấp thay API, chứng chỉ, quota hoặc lịch bảo trì:

1. Ghi nhận thông báo và phiên bản bị ảnh hưởng.
2. Đánh giá consumer và hành trình nội bộ liên quan.
3. Cập nhật contract test hoặc test fixture.
4. Kiểm thử tương thích trên sandbox.
5. Lập kế hoạch rollout và rollback/roll-forward.
6. Theo dõi sau thay đổi và xác nhận hành vi thực tế.

Khi phụ thuộc gặp sự cố, cần phân biệt lỗi bên ngoài với lỗi xử lý của ứng dụng. Ứng dụng vẫn phải xử lý timeout, retry, fallback hoặc thông báo người dùng theo thiết kế.

## 8. Thiết lập ma trận phối hợp và trách nhiệm

Ma trận RACI giúp xác định ai thực hiện (Responsible), ai chịu trách nhiệm cuối cùng (Accountable), ai cần tham vấn (Consulted) và ai cần được thông báo (Informed). Mỗi hoạt động nên có một vai trò Accountable rõ ràng.

Ví dụ minh họa:

| Hoạt động | Product | Development | QA | Security | Performance/SRE | UX | Bên thứ ba |
|---|---|---|---|---|---|---|---|
| Xác định mục tiêu và tiêu chí chấp nhận | A | C | R | C | C | C | I |
| Threat model và yêu cầu bảo mật | C | R | C | A | C | I | C |
| Workload và SLO | C | R | R | I | A | C | C |
| Nghiên cứu usability/accessibility | A | C | R | C | I | R | I |
| Contract và sandbox tích hợp | I | R | R | C | C | I | A/C |
| Thực hiện test hồi quy | I | R | A/R | C | C | C | I |
| Đánh giá readiness phát hành | A | R | R | C | C | C | I |
| Xử lý sự cố liên quan phụ thuộc | I | R | C | C | A/R | I | R/C |

Ma trận cần được điều chỉnh theo cơ cấu thực tế. Với nhà cung cấp, trách nhiệm cuối cùng đối với sản phẩm vẫn thuộc tổ chức sử dụng dịch vụ; hợp đồng hoặc SLA không thay thế việc kiểm soát rủi ro tích hợp.

## 9. Quy trình phối hợp từ yêu cầu đến phát hành

### Bước 1: Khởi tạo và xác định bên liên quan

Product mô tả mục tiêu và hành trình. Engineering lập sơ đồ kiến trúc và phụ thuộc. QA xác định rủi ro kiểm thử. Các chuyên gia security, performance, UX và vendor được mời theo phạm vi ảnh hưởng.

### Bước 2: Phân tích yêu cầu liên chức năng

Chuyển các mục tiêu chung thành tiêu chí đo được. Xác định dữ liệu, môi trường, thiết bị, workload, hợp đồng và nghĩa vụ liên quan.

### Bước 3: Lập kế hoạch kiểm thử tích hợp

Xác định lớp test, thứ tự, dữ liệu, công cụ, owner, thời gian và phụ thuộc. Ghi rõ kiểm tra nào chạy tự động, kiểm tra nào cần chuyên gia hoặc người tham gia.

### Bước 4: Chuẩn bị môi trường và quyền

Provision môi trường, sandbox, tài khoản, secret và dữ liệu. Xác minh quyền truy cập, quota, khả năng quan sát và quy trình dọn dữ liệu.

### Bước 5: Thực hiện và trao đổi kết quả

Chạy test theo kế hoạch. Chia sẻ report có run ID, phiên bản, cấu hình, log và bằng chứng. Khi phát hiện vấn đề, phân loại theo tác động và thông báo đúng owner.

### Bước 6: Xử lý phát hiện và xung đột

Nhóm liên quan đánh giá nguyên nhân, mức độ rủi ro và lựa chọn khắc phục. Nếu có trade-off, ghi các phương án, bằng chứng, người quyết định và rủi ro còn lại.

### Bước 7: Đánh giá readiness

Tổng hợp bằng chứng bảo mật, hiệu năng, trải nghiệm và tích hợp. Xác minh các tiêu chí bắt buộc, ngoại lệ còn hiệu lực, kế hoạch phục hồi và giám sát.

### Bước 8: Theo dõi sau triển khai

Quan sát metric, alert, phản hồi người dùng và tình trạng phụ thuộc. Chuyển phát hiện thành backlog hoặc incident có owner; cập nhật test để ngăn lỗi tái diễn.

~~~mermaid
flowchart TD
    A["Mục tiêu sản phẩm và thay đổi"]
    B["Xác định ranh giới, dữ liệu và bên liên quan"]
    C["Thống nhất tiêu chí security, performance, UX và vendor"]
    D["Lập kế hoạch test, môi trường và trách nhiệm"]
    E["Thực hiện kiểm tra và thu thập bằng chứng"]
    F["Phân loại phát hiện và giải quyết trade-off"]
    G{"Các tiêu chí bắt buộc đạt?"}
    H["Đánh giá readiness và quyết định phát hành"]
    I["Khắc phục, kiểm tra lại hoặc xử lý ngoại lệ hợp lệ"]
    J["Theo dõi sau triển khai và cập nhật chiến lược"]
    A --> B --> C --> D --> E --> F --> G
    G -->|Có| H --> J
    G -->|Không| I --> E
    J -. "Phản hồi và thay đổi mới" .-> B
~~~

## 10. Quản lý xung đột giữa các mục tiêu chất lượng

Các mục tiêu có thể xung đột:

- Mã hóa mạnh hơn có thể tăng chi phí xử lý.
- Kiểm tra chống bot có thể làm người dùng hợp lệ gặp khó khăn.
- Cache rộng có thể cải thiện latency nhưng làm tăng rủi ro rò rỉ dữ liệu.
- Retry giúp tăng khả năng hoàn tất nhưng có thể tạo giao dịch trùng.
- Thêm telemetry giúp điều tra nhưng có thể thu thập dữ liệu nhạy cảm.
- Tích hợp trực tiếp với nhà cung cấp giúp cập nhật tức thời nhưng làm hệ thống phụ thuộc vào availability bên ngoài.

Khi có xung đột, dùng quy trình:

1. Nêu mục tiêu và ràng buộc của từng bên.
2. Phân biệt yêu cầu bắt buộc với lựa chọn có thể điều chỉnh.
3. Đưa ra các phương án thiết kế thay thế.
4. Đánh giá tác động bằng test, prototype, dữ liệu hoặc nghiên cứu người dùng.
5. So sánh lợi ích, rủi ro và chi phí vòng đời.
6. Ghi quyết định, người chịu trách nhiệm và rủi ro còn lại.
7. Đặt điều kiện xem xét lại khi dữ liệu vận hành thay đổi.

Không giải quyết xung đột chỉ bằng ý kiến của nhóm có tiếng nói lớn hơn. Quyết định cần dựa trên bằng chứng và thẩm quyền phù hợp. Các yêu cầu pháp lý, bảo mật hoặc an toàn không thể bị bỏ qua chỉ để tối ưu một chỉ số khác.

## 11. Quản lý phát hiện và bằng chứng liên nhóm

Một phát hiện liên chức năng cần có thông tin đủ để các bên cùng điều tra:

- Mã phát hiện và mức độ ưu tiên.
- Yêu cầu, rủi ro hoặc tiêu chí liên quan.
- Thành phần, phiên bản, môi trường và run ID.
- Các bước tái hiện và điều kiện xảy ra.
- Kết quả mong đợi và kết quả thực tế.
- Log, metric, trace, screenshot hoặc dữ liệu hỗ trợ.
- Tác động đến người dùng, dữ liệu và phụ thuộc.
- Owner điều tra, owner khắc phục và người cần tham vấn.
- Hành động, thời hạn và tiêu chí xác minh bản sửa.

Không sao chép secret, token, dữ liệu cá nhân hoặc payload nhạy cảm vào ticket thông thường. Dùng liên kết đến kho bằng chứng có kiểm soát quyền và che dữ liệu không cần thiết.

### 11.1. Phân loại nguyên nhân

Một lỗi có thể thuộc nhiều nhóm:

- Lỗi logic hoặc thiết kế của ứng dụng.
- Lỗi cấu hình, hạ tầng hoặc môi trường.
- Lỗi hợp đồng hoặc hành vi của bên thứ ba.
- Lỗi dữ liệu hoặc quyền truy cập.
- Lỗi test, fixture hoặc công cụ đo.
- Vấn đề usability hoặc nội dung.
- Vấn đề hiệu năng do tải, tài nguyên hoặc phụ thuộc.

Tránh đóng issue với kết luận "lỗi vendor" hoặc "lỗi môi trường" nếu chưa có bằng chứng. Cần xác định trách nhiệm của ứng dụng trong việc xử lý lỗi phụ thuộc và cung cấp trải nghiệm phù hợp.

## 12. Lập lịch và quản lý phụ thuộc

Các nhóm có thể có lịch phát hành, chu kỳ kiểm thử và mức ưu tiên khác nhau. Cần lập kế hoạch cho:

- Thời điểm security review và kiểm thử chuyên sâu.
- Cửa sổ performance test để tránh nhiễu.
- Lịch usability study và tuyển người tham gia.
- Thời gian sandbox hoặc hỗ trợ của nhà cung cấp.
- Thời điểm có dữ liệu, môi trường và credential.
- Thời hạn xử lý lỗ hổng hoặc thay đổi hợp đồng.
- Mốc đóng băng phát hành và thời gian rollback.

Phụ thuộc cần được ghi thành đầu việc có owner và ngày cần hoàn thành. Nếu một nhà cung cấp chưa cấp sandbox hoặc UX study chưa có người tham gia, tác động đến kế hoạch cần được thể hiện sớm thay vì đợi đến cuối sprint.

## 13. Ví dụ: thay đổi luồng đăng nhập có xác thực đa yếu tố

Giả sử sản phẩm bổ sung xác thực đa yếu tố (MFA) cho tài khoản quản trị. Thay đổi này ảnh hưởng đồng thời đến bảo mật, hiệu năng, trải nghiệm và dịch vụ gửi mã OTP của bên thứ ba.

### 13.1. Phân tích chung

- Product xác định nhóm tài khoản bắt buộc MFA, hành trình đăng nhập và trường hợp khôi phục.
- Security xác định threat model, thời hạn OTP, giới hạn thử sai, chống replay và chính sách phiên.
- UX nghiên cứu cách người dùng nhập mã, xử lý hết hạn, mất thiết bị và sử dụng công nghệ hỗ trợ.
- Performance/SRE đánh giá tải tăng khi phát OTP, latency nhà cung cấp, quota và tác động lên đăng nhập.
- Vendor xác nhận API, giới hạn gửi, callback, mã lỗi, SLA và sandbox.
- Development thiết kế adapter, lưu trạng thái, retry, rate limit và khả năng quan sát.
- QA lập test cho luồng thành công, thất bại, hết hạn, gửi lại, khóa tạm thời và gián đoạn vendor.

### 13.2. Ma trận kiểm tra

| Góc nhìn | Kịch bản | Bằng chứng |
|---|---|---|
| Security | OTP hết hạn, dùng lại, brute force, chiếm phiên, đổi thiết bị | Test report, audit log và kết quả kiểm tra quyền |
| Performance | Nhiều quản trị viên đăng nhập đồng thời, vendor chậm hoặc rate limit | p95/p99, throughput, quota và error rate |
| UX | Người dùng nhập mã, yêu cầu gửi lại, xử lý mất thiết bị và lỗi | Tỷ lệ hoàn thành, thời gian, lỗi và quan sát nghiên cứu |
| Accessibility | Nhập mã bằng bàn phím/screen reader, thông báo lỗi và focus | Kết quả audit và test với công nghệ hỗ trợ |
| Vendor | Timeout, 429, 5xx, callback trễ và sandbox gián đoạn | Contract/sandbox test và log tích hợp |
| Vận hành | Theo dõi gửi OTP, alert quota, fallback và hỗ trợ người dùng | Dashboard, runbook và diễn tập xử lý |

### 13.3. Quyết định phát hành

Nhóm không chỉ hỏi MFA có hoạt động hay không. Cần xác minh người không có quyền không thể vượt qua kiểm soát, người dùng hợp lệ có thể hoàn thành hành trình, hệ thống chịu được tải dự kiến và ứng dụng xử lý được giới hạn hoặc gián đoạn của vendor. Nếu sandbox không xác minh được một tình huống, cần ghi rõ phần bằng chứng còn thiếu, biện pháp thay thế và người có thẩm quyền quyết định.

## 14. Những sai lầm thường gặp

- **Chỉ mời chuyên gia ở cuối dự án:** phát hiện muộn các yêu cầu bảo mật, hiệu năng hoặc trải nghiệm.
- **Không có tiêu chí đo được:** các bên hiểu "an toàn", "nhanh" và "dễ dùng" theo cách khác nhau.
- **Cho rằng QA chịu trách nhiệm cho mọi chất lượng:** bỏ qua trách nhiệm của product, development, security, SRE và vendor owner.
- **Dựa hoàn toàn vào mock:** không xác minh hành vi thực tế của phụ thuộc bên ngoài.
- **Dùng sandbox như production:** bỏ qua khác biệt quota, dữ liệu, cấu hình và SLA.
- **Để một nhóm quyết định trade-off thay tất cả:** không xem xét đầy đủ tác động liên chức năng.
- **Không có owner cho phát hiện:** issue chuyển qua nhiều nhóm nhưng không ai chịu trách nhiệm đến cùng.
- **Chia sẻ bằng chứng thiếu kiểm soát:** làm lộ secret, dữ liệu cá nhân hoặc chi tiết lỗ hổng.
- **Chỉ kiểm tra trước phát hành:** bỏ lỡ cơ hội phát hiện và xử lý sớm.
- **Không theo dõi sau triển khai:** không phát hiện thay đổi của vendor, tải thực tế hoặc phản hồi người dùng.
- **Không cập nhật test sau sự cố:** lỗi tương tự có thể tái diễn.

## 15. Checklist phối hợp liên chức năng

- [ ] Các bên liên quan được xác định theo kiến trúc, dữ liệu và rủi ro.
- [ ] Mục tiêu chất lượng được chuyển thành tiêu chí có thể kiểm chứng.
- [ ] Security tham gia threat model, quyền, dữ liệu và kiểm thử phù hợp.
- [ ] Performance/SRE thống nhất SLI/SLO, workload, môi trường và cách đo.
- [ ] UX/accessibility xác định nhóm người dùng, hành trình và phương pháp đánh giá.
- [ ] Bên thứ ba xác nhận hợp đồng, sandbox, quota, SLA và quy trình thay đổi.
- [ ] Mỗi hoạt động có owner và người chịu trách nhiệm cuối cùng.
- [ ] Môi trường, dữ liệu, quyền truy cập và lịch kiểm thử đã sẵn sàng.
- [ ] Test bao gồm hành vi bình thường, lỗi, giới hạn và phục hồi.
- [ ] Bằng chứng có run ID, phiên bản, cấu hình và quyền truy cập phù hợp.
- [ ] Phát hiện có mức độ, owner, thời hạn và tiêu chí xác minh bản sửa.
- [ ] Xung đột giữa mục tiêu được giải quyết bằng bằng chứng và quyết định có truy vết.
- [ ] Ngoại lệ có phạm vi, biện pháp giảm thiểu và thời hạn theo chính sách.
- [ ] Readiness bao gồm bảo mật, hiệu năng, trải nghiệm, tích hợp và vận hành.
- [ ] Có theo dõi sau triển khai và cập nhật chiến lược từ phản hồi thực tế.

## 16. Đánh giá hiệu quả phối hợp

Có thể theo dõi:

- Tỷ lệ rủi ro liên chức năng được phát hiện trước khi triển khai.
- Thời gian từ phát hiện đến khi có owner và kế hoạch xử lý.
- Số lỗi liên quan bảo mật, hiệu năng, UX hoặc vendor lọt đến production.
- Tỷ lệ test tích hợp có dữ liệu và môi trường ổn định.
- Tỷ lệ thay đổi API bên thứ ba được phát hiện trước khi ảnh hưởng production.
- Thời gian xử lý phụ thuộc và sự cố vendor.
- Tỷ lệ phát hiện được đóng đúng hạn và có test hồi quy.
- Số ngoại lệ đang mở, thời gian tồn tại và số lần gia hạn.
- Mức độ hoàn thành các tiêu chí usability/accessibility.
- Chất lượng phản hồi từ vận hành và người dùng sau phát hành.

Không nên dùng số lượng cuộc họp hoặc số lượng test làm thước đo duy nhất. Giá trị của phối hợp nằm ở việc giảm rủi ro, tăng chất lượng quyết định và rút ngắn thời gian giải quyết vấn đề.

## 17. Luồng phối hợp và trách nhiệm

~~~mermaid
flowchart TD
    A["Yêu cầu và mục tiêu sản phẩm"]
    B["Product, Engineering và QA xác định phạm vi"]
    C["Security: threat model và dữ liệu"]
    D["Performance/SRE: SLO và workload"]
    E["UX: hành trình và accessibility"]
    F["Vendor owner: hợp đồng và sandbox"]
    G["QA/Engineering tích hợp kế hoạch và test"]
    H["Chạy kiểm tra, thu thập bằng chứng"]
    I["Đánh giá phát hiện và trade-off liên chức năng"]
    J{"Tiêu chí và rủi ro được chấp nhận?"}
    K["Readiness, phát hành và giám sát"]
    L["Khắc phục hoặc quyết định ngoại lệ có kiểm soát"]
    A --> B
    B --> C
    B --> D
    B --> E
    B --> F
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H --> I --> J
    J -->|Có| K
    J -->|Không| L --> G
    K -. "Phản hồi vận hành và người dùng" .-> B
~~~

Phối hợp với bảo mật, hiệu năng, trải nghiệm và bên thứ ba giúp chiến lược kiểm thử bao quát các rủi ro nằm ngoài chức năng đơn lẻ. Khi các bên cùng xác định tiêu chí từ sớm, có trách nhiệm rõ ràng, kiểm tra bằng chứng ở đúng thời điểm và theo dõi sau phát hành, nhóm có thể đưa ra quyết định chất lượng cân bằng, có căn cứ và truy vết được.
