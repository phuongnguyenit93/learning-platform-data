# Phân tích bối cảnh và xác định mục tiêu chất lượng cho một sản phẩm

Trong chiến lược kiểm thử `VALIDATION_TESTING_STRATEGY`, kế hoạch test chỉ có giá trị khi nó bảo vệ đúng những điều quan trọng đối với sản phẩm và người sử dụng. Trước khi chọn test level, công cụ, môi trường hoặc số lượng test case, nhóm cần hiểu sản phẩm được tạo ra cho ai, giải quyết vấn đề nào, vận hành trong điều kiện nào, chịu những giới hạn gì và điều gì sẽ được xem là chất lượng đạt yêu cầu.

Bài thực hành này hướng dẫn cách **phân tích bối cảnh và xác định mục tiêu chất lượng cho một sản phẩm**. Người học sẽ thu thập thông tin từ các bên liên quan, mô tả người dùng và hành trình chính, xác định rủi ro, xem xét môi trường và ràng buộc, chọn các thuộc tính chất lượng quan trọng, chuyển kỳ vọng thành mục tiêu đo lường được và liên kết từng mục tiêu với bằng chứng kiểm thử. Đầu ra là một hồ sơ bối cảnh sản phẩm và một bộ mục tiêu chất lượng có thể dùng làm cơ sở cho chiến lược kiểm thử.

Đây là bài thực hành theo hướng ra quyết định. Không bắt đầu bằng việc viết thật nhiều test case. Hãy bắt đầu từ câu hỏi: **sản phẩm cần làm tốt điều gì, trong hoàn cảnh nào, cho ai và bằng chứng nào đủ để chứng minh điều đó?**

## 1. Mục tiêu học tập và đầu ra cần hoàn thành

Sau bài thực hành, người học có thể:

- Mô tả bối cảnh sản phẩm, mục tiêu kinh doanh và nhóm người dùng.
- Xác định các hành trình nghiệp vụ quan trọng và những hệ thống liên quan.
- Thu thập, phân loại yêu cầu và kỳ vọng chất lượng từ stakeholder.
- Nhận diện rủi ro theo người dùng, dữ liệu, giao dịch, vận hành và phụ thuộc.
- Phân tích giới hạn về công nghệ, môi trường, pháp lý, thời gian và ngân sách.
- Chọn thuộc tính chất lượng phù hợp với bối cảnh thay vì áp dụng một danh sách chung cho mọi sản phẩm.
- Viết mục tiêu chất lượng cụ thể, có thước đo, điều kiện, phạm vi và tiêu chí chấp nhận.
- Xác định bằng chứng, phương pháp kiểm thử và người chịu trách nhiệm cho từng mục tiêu.
- Trình bày các giả định, khoảng trống thông tin và quyết định cần xác nhận.

Kết thúc bài, cần có tối thiểu các đầu ra sau:

| Đầu ra | Nội dung |
|---|---|
| Product context brief | Sản phẩm, mục tiêu, người dùng, phạm vi, hệ thống liên quan và điều kiện vận hành |
| Stakeholder and user map | Nhóm liên quan, nhu cầu, mức ảnh hưởng và trách nhiệm |
| Critical journey map | Các hành trình chính, điểm chạm và hậu quả khi thất bại |
| Constraint and assumption log | Ràng buộc, giả định, phụ thuộc và thông tin chưa rõ |
| Risk register sơ bộ | Tình huống rủi ro, tác động, khả năng và kiểm soát hiện có |
| Quality objective set | Mục tiêu chất lượng có thước đo và tiêu chí chấp nhận |
| Evidence and test mapping | Bằng chứng, phương pháp kiểm thử, môi trường và owner |
| Review decision | Các điểm đã thống nhất, điểm cần xác nhận và rủi ro tồn dư |

## 2. Bối cảnh của bài thực hành

Có thể thực hiện bài này với sản phẩm thật mà nhóm đang phát triển hoặc dùng case study xuyên suốt dưới đây. Nếu dùng sản phẩm thật, thay dữ liệu minh họa bằng thông tin đã được phép chia sẻ; không đưa secret, dữ liệu cá nhân hoặc thông tin nội bộ nhạy cảm vào tài liệu học tập.

### Case study: nền tảng đặt hàng trực tuyến

Một doanh nghiệp bán lẻ muốn phát triển nền tảng đặt hàng trực tuyến gồm website và ứng dụng di động. Người dùng có thể tìm sản phẩm, quản lý giỏ hàng, đặt hàng, thanh toán, theo dõi giao hàng và yêu cầu hỗ trợ. Nhân viên vận hành quản lý danh mục, tồn kho, đơn hàng và hoàn tiền qua giao diện nội bộ.

Các thành phần chính:

- Web frontend và mobile application.
- Identity service cho đăng nhập và phân quyền.
- Catalog/search service cho sản phẩm và tìm kiếm.
- Cart/order service cho giỏ hàng và đơn hàng.
- Payment adapter kết nối một nhà cung cấp thanh toán.
- Inventory service đồng bộ tồn kho.
- Notification service gửi email hoặc thông báo ứng dụng.
- Database, cache và message broker.
- Dashboard vận hành và hệ thống báo cáo.

### Bối cảnh kinh doanh

- Sản phẩm phục vụ khách hàng ở nhiều khu vực và có lưu lượng tăng mạnh trong các chiến dịch khuyến mãi.
- Doanh nghiệp muốn tăng tỷ lệ hoàn tất đơn hàng và giảm số yêu cầu hỗ trợ liên quan đến thanh toán.
- Khách hàng kỳ vọng có thể xem trạng thái đơn hàng chính xác và nhận thông báo kịp thời.
- Nhân viên cần xử lý đơn, hủy đơn và hoàn tiền mà không làm sai lệch dữ liệu.
- Một số chức năng phụ thuộc vào hệ thống đối tác có giới hạn tốc độ và thời gian sẵn sàng riêng.

### Giả định ban đầu để thực hành

Các số liệu sau chỉ phục vụ bài tập, không phải cam kết kỹ thuật cho mọi sản phẩm:

- Mục tiêu ban đầu là hỗ trợ 20.000 người dùng hoạt động trong ngày.
- Lưu lượng cao điểm dự kiến gấp 4 lần mức trung bình trong một số chiến dịch.
- Hệ thống cần phục vụ giao dịch thanh toán và quản lý dữ liệu đơn hàng.
- Nhóm phát triển có thể triển khai nhiều lần trong tháng.
- Staging dùng dữ liệu tổng hợp và một số sandbox của đối tác.
- Sản phẩm có website responsive và ứng dụng trên hai nền tảng di động chính.

Khi thực hiện với sản phẩm thật, phải thay các giả định này bằng dữ liệu hoặc đánh dấu rõ chúng chưa được xác nhận. Không được biến số liệu giả định thành mục tiêu cam kết nếu chưa có người có thẩm quyền phê duyệt.

## 3. Chuẩn bị buổi phân tích bối cảnh

Một buổi phân tích hiệu quả cần có người hiểu nghiệp vụ, kỹ thuật, vận hành và người dùng. Nếu chỉ có QA tự suy đoán, nhiều yêu cầu quan trọng sẽ bị bỏ sót.

### Thành phần tham gia

Tùy quy mô, có thể mời:

- Product Owner hoặc business owner: mục tiêu, phạm vi, ưu tiên và tiêu chí thành công.
- Đại diện người dùng hoặc customer support: nhu cầu, khó khăn và kỳ vọng thực tế.
- Business analyst: quy trình, quy tắc nghiệp vụ và ngoại lệ.
- Engineering lead/architect: kiến trúc, tích hợp, giới hạn kỹ thuật và khả năng thay đổi.
- QA/Test lead: rủi ro kiểm thử, bằng chứng, coverage và testability.
- Operations/SRE: vận hành, monitoring, availability, backup và phục hồi.
- Security/Privacy: dữ liệu, danh tính, quyền truy cập và yêu cầu bảo vệ.
- Data/Analytics: nguồn dữ liệu, chất lượng dữ liệu và định nghĩa metric.
- Procurement/Legal/Compliance khi sản phẩm có nghĩa vụ hợp đồng hoặc quy định liên quan.

Không cần tất cả tham gia mọi buổi. Chọn người phù hợp với quyết định cần đưa ra và ghi lại người đã tham gia để biết góc nhìn nào còn thiếu.

### Tài liệu nên chuẩn bị

- Product brief, roadmap hoặc mục tiêu kinh doanh đã được phê duyệt.
- User story, use case, process flow và acceptance criteria hiện có.
- Kiến trúc hệ thống, sơ đồ tích hợp và data flow nếu có.
- Số liệu traffic, incident, support ticket và hành vi người dùng.
- SLO/SLA, hợp đồng với đối tác và yêu cầu tuân thủ.
- Release plan, môi trường, công cụ và giới hạn nguồn lực.
- Defect backlog, test report và bài học từ các phiên bản trước.

Nếu một tài liệu chưa tồn tại, ghi nhận đó là khoảng trống. Không cần dừng toàn bộ bài thực hành; hãy tiếp tục với giả định được đánh dấu và tạo câu hỏi cần xác minh.

### Nguyên tắc làm việc

1. Phân biệt dữ kiện, ý kiến, giả định và quyết định.
2. Hỏi “vì sao” để hiểu nhu cầu thay vì ghi nguyên văn giải pháp được đề xuất.
3. Ghi rõ phạm vi và điều kiện áp dụng của mỗi phát biểu.
4. Tránh dùng các từ “nhanh”, “an toàn”, “dễ dùng”, “ổn định” nếu chưa định nghĩa cách đo.
5. Không cam kết mục tiêu vượt quá khả năng kiểm soát hoặc chưa có bằng chứng.
6. Ghi người cần xác nhận và thời hạn cho các câu hỏi còn mở.

## 4. Bước 1 — Mô tả sản phẩm và mục tiêu kinh doanh

Trước khi bàn về test, cần xác định sản phẩm tồn tại để giải quyết vấn đề nào và thành công được đo bằng gì.

### Câu hỏi khám phá

- Sản phẩm dành cho nhóm người dùng nào?
- Vấn đề hiện tại của người dùng hoặc doanh nghiệp là gì?
- Sản phẩm tạo ra giá trị nào và khác gì với cách làm hiện tại?
- Những năng lực nào là bắt buộc ở phiên bản đầu?
- Thành công được đo bằng chỉ số nghiệp vụ nào?
- Có mốc phát hành, mùa cao điểm hoặc cam kết hợp đồng nào không?
- Điều gì sẽ khiến doanh nghiệp dừng hoặc thay đổi hướng sản phẩm?

### Viết product statement

Có thể dùng cấu trúc:

> [Tên sản phẩm] giúp [nhóm người dùng] thực hiện [nhu cầu/nhiệm vụ] bằng cách [năng lực chính], nhằm đạt [kết quả kinh doanh hoặc người dùng].

Ví dụ:

> Nền tảng đặt hàng trực tuyến giúp khách hàng tìm, mua và theo dõi sản phẩm trên web hoặc di động, nhằm tăng tỷ lệ hoàn tất đơn hàng và giảm công sức xử lý thủ công của nhân viên vận hành.

### Phân biệt outcome với output

- **Output:** những gì nhóm xây dựng, như trang checkout, API thanh toán hoặc dashboard.
- **Outcome:** kết quả đạt được, như tỷ lệ thanh toán thành công tăng, đơn hàng được xử lý chính xác hoặc thời gian hỗ trợ giảm.

Mục tiêu chất lượng cần hỗ trợ outcome. Có trang checkout không chứng minh checkout dễ sử dụng; có API thanh toán không chứng minh giao dịch được xử lý chính xác trong điều kiện timeout.

### Bài tập ngắn

Viết một product statement không quá ba câu. Sau đó liệt kê ba outcome quan trọng và cách đo sơ bộ. Nếu outcome chưa có baseline, ghi ai sẽ cung cấp hoặc thu thập dữ liệu.

## 5. Bước 2 — Xác định stakeholder và nhóm người dùng

Chất lượng được nhìn khác nhau từ các vai trò khác nhau. Khách hàng quan tâm khả năng hoàn tất giao dịch; nhân viên vận hành quan tâm dữ liệu chính xác và thao tác hiệu quả; security quan tâm quyền truy cập và bảo vệ dữ liệu; SRE quan tâm khả năng giám sát và phục hồi.

### Lập stakeholder map

| Stakeholder | Nhu cầu/kỳ vọng | Mức ảnh hưởng | Câu hỏi cần xác nhận |
|---|---|---|---|
| Khách hàng | Tìm và mua hàng dễ dàng, trạng thái chính xác | Cao | Luồng nào quan trọng nhất? Hành vi nào khiến họ bỏ giỏ? |
| Nhân viên vận hành | Quản lý đơn và tồn kho chính xác | Cao | Quy trình ngoại lệ và hoàn tiền diễn ra thế nào? |
| Product/business | Tăng chuyển đổi và doanh thu | Cao | Metric thành công và ngưỡng chấp nhận là gì? |
| Engineering | Hệ thống có thể thay đổi và tích hợp | Cao | Giới hạn kiến trúc, API và dependency là gì? |
| Operations/SRE | Dịch vụ có thể theo dõi và phục hồi | Cao | SLO, on-call, RTO/RPO và runbook hiện có? |
| Security/Privacy | Bảo vệ danh tính và dữ liệu | Cao | Dữ liệu nào nhạy cảm? Nghĩa vụ nào bắt buộc? |
| Đối tác thanh toán/vận chuyển | Tích hợp theo hợp đồng và quota | Trung bình đến cao | SLA, timeout, retry và sandbox khác production ra sao? |

Mức ảnh hưởng không chỉ là chức danh. Một nhóm người dùng ít nhưng có quyền quyết định hoặc chịu hậu quả lớn có thể có ảnh hưởng cao.

### Phân biệt user segment

Không nên gộp tất cả người dùng thành “khách hàng”. Có thể phân nhóm theo:

- Người dùng mới và người dùng thường xuyên.
- Khách mua một lần và khách có tài khoản.
- Người dùng trợ năng hoặc dùng thiết bị cấu hình thấp.
- Nhân viên vận hành, quản trị viên và nhân viên hỗ trợ.
- Người dùng ở khu vực, ngôn ngữ hoặc múi giờ khác nhau.
- Hệ thống tích hợp tự động thay mặt người dùng.

### Chuyển nhu cầu thành câu hỏi chất lượng

Ví dụ:

- Khách hàng: “Tôi cần biết thanh toán đã thành công chưa.” → trạng thái giao dịch phải nhất quán, có thể quan sát và không tạo xác nhận sai.
- Nhân viên: “Tôi cần tìm đơn nhanh.” → tìm kiếm cần đáp ứng thời gian và độ chính xác đã thống nhất.
- SRE: “Tôi cần biết dịch vụ nào đang lỗi.” → cần health signal, log, trace và cảnh báo có owner.
- Security: “Chỉ người có quyền mới được xem thông tin đơn.” → cần xác thực, phân quyền và kiểm tra truy cập trái phép.

## 6. Bước 3 — Vẽ hành trình và xác định luồng quan trọng

Hành trình người dùng giúp thấy các bước liên tiếp, phụ thuộc và điểm mà lỗi có thể làm mất giá trị của toàn luồng.

### Xác định critical journey

Với nền tảng đặt hàng, các hành trình có thể gồm:

1. Khám phá: mở ứng dụng, tìm kiếm, lọc và xem chi tiết sản phẩm.
2. Chọn mua: thêm vào giỏ, thay đổi số lượng và áp dụng ưu đãi.
3. Checkout: nhập địa chỉ, chọn vận chuyển và xác nhận đơn.
4. Thanh toán: chuyển đến provider, nhận kết quả và xử lý webhook.
5. Theo dõi: xem trạng thái đơn và nhận thông báo.
6. Hậu mãi: hủy, đổi trả hoặc yêu cầu hoàn tiền.
7. Vận hành: nhân viên tra cứu, xử lý ngoại lệ và đối soát.

### Sơ đồ luồng chính

~~~text
Khách hàng
    |
    v
Tìm sản phẩm --> Giỏ hàng --> Checkout
                               |
                               v
                         Tạo đơn chờ thanh toán
                               |
                               v
                         Payment Provider
                               |
                         Kết quả / Webhook
                               |
                               v
                         Cập nhật đơn hàng
                               |
                               v
                       Thông báo và theo dõi
                               |
                               v
                         Giao hàng / Hậu mãi
~~~

### Xác định điểm thất bại quan trọng

Với mỗi bước, hỏi:

- Nếu bước này thất bại, người dùng có thể tiếp tục không?
- Có thể thử lại an toàn không?
- Có nguy cơ tạo giao dịch hoặc dữ liệu trùng không?
- Trạng thái có thể bị lệch giữa hai hệ thống không?
- Người dùng có biết điều gì đã xảy ra không?
- Nhân viên có thể phát hiện và xử lý ngoại lệ không?
- Có cách khôi phục mà không mất dữ liệu không?

Một lỗi ở bước xem ảnh sản phẩm có thể làm giảm trải nghiệm; lỗi ở bước xác nhận thanh toán có thể gây giao dịch trùng hoặc khách hàng đã trả tiền nhưng không nhận đơn. Hậu quả khác nhau nên mục tiêu chất lượng và ưu tiên test cũng khác nhau.

### Đánh dấu luồng trọng yếu

Đánh dấu critical journey dựa trên giá trị kinh doanh, tần suất, tác động nếu thất bại, nghĩa vụ và khả năng phục hồi. Không chỉ chọn luồng được demo thường xuyên; cần hỏi cả những luồng ít dùng nhưng có hậu quả cao như hoàn tiền, xóa tài khoản hoặc phục hồi dữ liệu.

## 7. Bước 4 — Phân tích hệ thống, dữ liệu và phụ thuộc

Sản phẩm không hoạt động độc lập. Một mục tiêu chất lượng cần xét các thành phần và phụ thuộc có thể ảnh hưởng đến kết quả.

### Lập sơ đồ context

Xác định:

- Client: web, mobile, thiết bị hoặc hệ thống gọi API.
- Backend service và ranh giới trách nhiệm.
- Database, cache, queue, search engine và storage.
- Identity provider, payment gateway, shipping provider và dịch vụ ngoài.
- CI/CD, monitoring, logging và công cụ vận hành.
- Data flow giữa các thành phần và nơi lưu dữ liệu nhạy cảm.

### Câu hỏi về tích hợp

- API nào đồng bộ, API nào bất đồng bộ?
- Timeout, retry, idempotency và rate limit được xử lý thế nào?
- Nhà cung cấp có sandbox không? Sandbox khác production ở điểm nào?
- Hệ thống xử lý khi phụ thuộc chậm, lỗi hoặc không phản hồi ra sao?
- Có contract/schema version và quy trình thay đổi không?
- Ai chịu trách nhiệm khi lỗi xảy ra ở ranh giới hai hệ thống?

### Câu hỏi về dữ liệu

- Dữ liệu nào là dữ liệu cá nhân, tài chính hoặc nhạy cảm?
- Nguồn dữ liệu chuẩn (source of truth) của mỗi thuộc tính là gì?
- Có yêu cầu về tính nhất quán, lưu giữ, xóa hoặc đối soát không?
- Migration và rollback được thực hiện thế nào?
- Test dùng dữ liệu tổng hợp, ẩn danh hay dữ liệu thật đã được phê duyệt?
- Có nguy cơ dữ liệu test bị chia sẻ giữa các test run không?

### Ví dụ dependency map

| Thành phần | Phụ thuộc | Rủi ro chất lượng |
|---|---|---|
| Checkout | Catalog, inventory, shipping | Giá/tồn kho/chi phí vận chuyển không nhất quán |
| Order service | Database, payment adapter, broker | Mất hoặc trùng trạng thái đơn, event xử lý sai thứ tự |
| Payment adapter | Provider API/webhook | Timeout, retry, callback trễ hoặc trùng |
| Notification | Email/push provider | Thông báo chậm hoặc gửi trùng |
| Admin portal | Identity, order API | Nhân viên sai quyền hoặc thao tác nhầm |
| Reporting | Database replica/data pipeline | Báo cáo chậm hoặc số liệu không khớp |

## 8. Bước 5 — Xác định ràng buộc và giả định

Ràng buộc xác định điều gì bị giới hạn; giả định là điều nhóm tạm coi đúng để tiếp tục phân tích. Cả hai đều ảnh hưởng đến mục tiêu chất lượng.

### Nhóm ràng buộc

| Nhóm | Ví dụ câu hỏi |
|---|---|
| Thời gian | Có ngày ra mắt cố định? Có mùa cao điểm? |
| Ngân sách | Có giới hạn cloud, license, thiết bị hoặc dịch vụ ngoài? |
| Công nghệ | Runtime, database, browser hoặc nền tảng nào phải hỗ trợ? |
| Tổ chức | Có bao nhiêu team, múi giờ, người trực và chuyên gia? |
| Hạ tầng | Có staging gần production? Có thể tạo môi trường tạm không? |
| Dữ liệu | Có thể dùng dữ liệu thật? Có yêu cầu residency hoặc retention? |
| Pháp lý/hợp đồng | Có nghĩa vụ bảo vệ dữ liệu, accessibility hoặc SLA? |
| Vận hành | RTO/RPO, lịch bảo trì, on-call và rollback có sẵn không? |

### Ghi nhận giả định

Ví dụ:

- “Sandbox provider có hành vi tương đương production đối với webhook retry.” Đây là giả định cần xác minh, không phải dữ kiện.
- “Lưu lượng cao điểm gấp bốn lần trung bình.” Cần kiểm tra bằng analytics hoặc forecast.
- “Có thể rollback database migration.” Cần chứng minh bằng thiết kế và diễn tập.
- “Ứng dụng chỉ hỗ trợ hai phiên bản browser mới nhất.” Cần được Product/Support xác nhận và công bố.

### Quản lý câu hỏi còn mở

Mỗi câu hỏi nên có:

- Nội dung cần xác minh.
- Tác động nếu câu trả lời khác giả định.
- Người hoặc nhóm cung cấp thông tin.
- Ngày cần câu trả lời.
- Cách xử lý nếu không thể xác minh kịp.

Không nên giấu khoảng trống bằng cách chọn một giá trị mặc định. Nếu chưa biết peak traffic, mục tiêu tải cần ghi “chờ xác nhận forecast” và có hành động thu thập dữ liệu.

## 9. Bước 6 — Nhận diện rủi ro theo bối cảnh

Rủi ro giúp xác định thuộc tính chất lượng nào cần ưu tiên và mức bằng chứng cần có.

### Cấu trúc risk statement

Có thể dùng mẫu:

> Do [điều kiện/nguyên nhân], có khả năng [sự kiện không mong muốn], dẫn đến [hậu quả đối với người dùng, dữ liệu, dịch vụ hoặc mục tiêu].

Ví dụ:

- Do payment provider có thể gửi webhook lặp sau timeout, có khả năng một giao dịch được xử lý nhiều lần, dẫn đến trạng thái thanh toán hoặc đơn hàng không nhất quán.
- Do inventory được cập nhật bất đồng bộ, có khả năng nhiều khách hàng mua cùng sản phẩm khi tồn kho thấp, dẫn đến overselling và hủy đơn.
- Do admin portal hỗ trợ nhiều vai trò, có khả năng quyền cấu hình không được kiểm tra đầy đủ, dẫn đến nhân viên truy cập hoặc sửa dữ liệu ngoài phạm vi.
- Do staging dùng dữ liệu nhỏ và traffic thấp, có khả năng test không phát hiện nghẽn khi chiến dịch khuyến mãi, dẫn đến timeout và giảm tỷ lệ checkout.

### Đánh giá likelihood và impact

Likelihood có thể dựa trên tần suất, điều kiện kích hoạt, mức phơi nhiễm và lịch sử. Impact có thể xét số người dùng, giao dịch, dữ liệu, thời gian gián đoạn, chi phí, nghĩa vụ và uy tín.

| Rủi ro | Likelihood sơ bộ | Impact sơ bộ | Lý do cần quan tâm |
|---|---|---|---|
| Thanh toán trùng | Trung bình | Rất cao | Ảnh hưởng tiền và trạng thái đơn |
| Tìm kiếm chậm khi tải cao | Cao trong chiến dịch | Cao | Làm người dùng bỏ luồng mua |
| Nhân viên xem đơn ngoài quyền | Thấp đến trung bình | Rất cao | Liên quan dữ liệu và quyền riêng tư |
| Email thông báo chậm | Trung bình | Trung bình | Ảnh hưởng trải nghiệm, có thể xem trạng thái trên app |
| Báo cáo cập nhật chậm | Trung bình | Thấp đến trung bình | Ảnh hưởng quyết định vận hành nhưng không trực tiếp chặn giao dịch |

Đây là đánh giá ban đầu để thực hành. Với sản phẩm thật, cần bằng chứng và tiêu chí phân loại được tổ chức thống nhất. Không tự kết luận rủi ro thấp chỉ vì chưa có incident.

### Ưu tiên rủi ro

Đưa rủi ro có hậu quả lớn, liên quan tiền/dữ liệu/an toàn/tuân thủ hoặc luồng trọng yếu vào nhóm cần có mục tiêu chất lượng rõ và bằng chứng trước release. Rủi ro thấp hơn vẫn có thể cần kiểm thử định kỳ hoặc monitoring.

## 10. Bước 7 — Chọn thuộc tính chất lượng phù hợp

Có nhiều mô hình phân loại chất lượng phần mềm. Một mô hình như ISO/IEC 25010 có thể dùng làm nguồn tham khảo về các đặc tính chất lượng, nhưng nhóm không nên chọn mọi đặc tính ở mức ưu tiên cao cho mọi sản phẩm. Hãy chọn theo bối cảnh, rủi ro và kỳ vọng người dùng.

### Functional suitability — tính phù hợp chức năng

Sản phẩm có cung cấp chức năng cần thiết, kết quả chính xác và đầy đủ không?

Ví dụ: đơn hàng được tạo đúng; tổng tiền, thuế, giảm giá và phí vận chuyển được tính chính xác; hoàn tiền cập nhật đúng trạng thái.

### Performance efficiency — hiệu quả hiệu năng

Thời gian phản hồi, thông lượng và mức sử dụng tài nguyên có phù hợp với tải dự kiến không?

Ví dụ: tìm kiếm và checkout đáp ứng latency mục tiêu ở mức tải cao điểm; queue không tăng không kiểm soát.

### Compatibility — khả năng tương thích

Sản phẩm có hoạt động đúng khi tương tác với browser, thiết bị, runtime, API hoặc hệ thống khác được hỗ trợ không?

Ví dụ: web hoạt động trên browser được công bố; order service tương thích với schema và phiên bản provider đã thỏa thuận.

### Usability và accessibility — khả năng sử dụng và tiếp cận

Người dùng có thể hoàn thành nhiệm vụ dễ hiểu, ít lỗi và phù hợp với nhu cầu tiếp cận không?

Ví dụ: khách hàng có thể nhận biết lỗi thanh toán và biết cách tiếp tục; form hỗ trợ bàn phím và công nghệ trợ năng theo tiêu chí đã chọn.

### Reliability — độ tin cậy

Sản phẩm có hoạt động ổn định, chịu lỗi, phục hồi và duy trì tính toàn vẹn trong điều kiện dự kiến không?

Ví dụ: retry không tạo giao dịch trùng; service phục hồi sau mất kết nối; backup có thể restore trong giới hạn đã thống nhất.

### Security — bảo mật

Sản phẩm có bảo vệ tính bí mật, toàn vẹn, xác thực, phân quyền và khả năng kiểm toán phù hợp không?

Ví dụ: người dùng không thể xem đơn của người khác; token hết hạn bị từ chối; secret không xuất hiện trong log.

### Maintainability — khả năng bảo trì

Nhóm có thể hiểu, kiểm tra, thay đổi và mở rộng sản phẩm với rủi ro hợp lý không?

Ví dụ: module có ranh giới rõ; test tự động đáng tin; thay đổi schema có migration và kiểm tra tương thích.

### Portability — khả năng chuyển đổi môi trường

Sản phẩm có thể triển khai hoặc vận hành trên các môi trường được hỗ trợ với công sức và rủi ro chấp nhận được không?

Ví dụ: image có thể chạy trên môi trường container mục tiêu; cấu hình được tách khỏi artifact; có thể dựng môi trường kiểm thử từ manifest.

### Operational readiness — mức sẵn sàng vận hành

Đây là góc nhìn thực hành bổ sung thường rất quan trọng: nhóm có thể giám sát, hỗ trợ, triển khai, rollback và khôi phục sản phẩm không?

Ví dụ: dashboard và alert được kiểm tra; runbook có owner; release có artifact traceability; on-call biết cách xử lý tình huống.

## 11. Bước 8 — Chuyển kỳ vọng thành mục tiêu chất lượng đo được

Các từ “nhanh”, “ổn định”, “an toàn” và “dễ dùng” chưa đủ để làm tiêu chí kiểm thử. Cần chuyển chúng thành mục tiêu có thước đo, điều kiện, phạm vi và ngưỡng chấp nhận.

### Cấu trúc mục tiêu

Một quality objective có thể gồm:

1. **Thuộc tính:** khía cạnh chất lượng cần đạt.
2. **Đối tượng/phạm vi:** service, luồng, nhóm người dùng hoặc môi trường.
3. **Thước đo:** metric hoặc tiêu chí quan sát.
4. **Điều kiện:** tải, dữ liệu, cấu hình, thời lượng và trạng thái hệ thống.
5. **Mức mục tiêu:** giá trị mong muốn hoặc ngưỡng chấp nhận.
6. **Nguồn bằng chứng:** test, metric, review hoặc diễn tập.
7. **Owner:** người xác nhận và chịu trách nhiệm.

### Mẫu câu

> Trong [điều kiện/phạm vi], [đối tượng] phải đạt [metric/behavior] ở mức [ngưỡng], được xác minh bằng [phương pháp/bằng chứng] trước [mốc], do [owner] xác nhận.

### Ví dụ chuyển đổi

| Kỳ vọng mơ hồ | Mục tiêu có thể kiểm chứng |
|---|---|
| Website phải nhanh | Ở tải 500 phiên checkout đồng thời trong 15 phút, p95 response time của checkout API không vượt ngưỡng đã thống nhất và error rate dưới mục tiêu |
| Thanh toán phải chính xác | Với cùng idempotency key và cùng giao dịch, retry hoặc webhook lặp không tạo giao dịch thu tiền trùng; trạng thái đơn và thanh toán cuối cùng phải đối soát được |
| Dữ liệu phải an toàn | Người dùng không có quyền không thể đọc hoặc sửa đơn của tenant khác trong bộ test phân quyền; các truy cập bị từ chối được ghi nhận theo policy |
| Hệ thống phải ổn định | Khi một dependency timeout, service áp dụng retry/backoff có giới hạn, không tạo vòng retry vô hạn và phục hồi theo tiêu chí đã xác định |
| Dễ sử dụng | Người tham gia đại diện hoàn thành nhiệm vụ checkout theo tiêu chí hoàn thành và tỷ lệ lỗi thao tác đã thống nhất trong usability test |
| Dễ vận hành | Nhóm trực có thể xác định phiên bản đang chạy, phát hiện lỗi payment/order mismatch và thực hiện runbook trong buổi diễn tập |

Các ngưỡng số cần được xác nhận bằng dữ liệu, SLO, yêu cầu nghiệp vụ và khả năng hạ tầng. Không lấy một giá trị phổ biến trên internet làm tiêu chí cho mọi hệ thống.

## 12. Chọn mục tiêu chất lượng theo ưu tiên

Một sản phẩm có thể có nhiều thuộc tính chất lượng, nhưng không thể đầu tư như nhau cho tất cả trong mọi release.

### Xếp hạng theo bối cảnh

Có thể dùng ba nhóm:

- **Critical:** nếu không đạt, sản phẩm không thể phát hành hoặc vi phạm yêu cầu bắt buộc.
- **High:** ảnh hưởng đáng kể đến người dùng, nghiệp vụ hoặc vận hành; cần bằng chứng mạnh trước release.
- **Normal/Monitor:** cần theo dõi hoặc cải thiện theo roadmap, có thể có workaround và rủi ro chấp nhận được.

Mức ưu tiên phải có tiêu chí và người xác nhận. Không để một nhãn “Normal” che giấu rủi ro bảo mật, dữ liệu hoặc hợp đồng.

### Ma trận thuộc tính – bối cảnh

| Thuộc tính | Tác nhân/bối cảnh | Mức ưu tiên minh họa | Lý do |
|---|---|---|---|
| Functional suitability | Tính tiền, đặt đơn, thanh toán, hoàn tiền | Critical | Sai kết quả có thể gây tổn thất trực tiếp |
| Reliability | Webhook, retry, đồng bộ trạng thái, phục hồi | Critical/High | Trạng thái lệch và giao dịch trùng khó xử lý |
| Security | Đăng nhập, phân quyền, dữ liệu đơn | Critical | Rủi ro dữ liệu và quyền truy cập |
| Performance | Tìm kiếm, checkout trong chiến dịch | High | Ảnh hưởng chuyển đổi và khả năng phục vụ |
| Compatibility | Browser, mobile OS và API đối tác | High | Người dùng và hệ thống tích hợp đa dạng |
| Usability/accessibility | Tìm kiếm, form checkout, thông báo lỗi | High | Ảnh hưởng hoàn tất nhiệm vụ và tiếp cận |
| Maintainability | Thay đổi giá, khuyến mãi và tích hợp | High/Normal | Tác động đến tốc độ và rủi ro thay đổi |
| Operational readiness | Monitoring, rollback, runbook, traceability | High | Cần phát hiện và xử lý sự cố sau release |

### Cân bằng giữa các thuộc tính

Các mục tiêu có thể xung đột. Ví dụ:

- Mã hóa và kiểm tra bảo mật có thể tăng latency.
- Cache cải thiện hiệu năng nhưng tạo thách thức về tính nhất quán.
- Retry tăng khả năng thành công nhưng có thể tạo tải hoặc giao dịch trùng nếu không idempotent.
- Logging chi tiết hỗ trợ điều tra nhưng có thể tăng chi phí và rủi ro dữ liệu.
- Kiểm tra nhiều browser tăng độ bao phủ nhưng tăng thời gian và chi phí.

Ghi nhận trade-off và người có quyền quyết định. Không tối ưu một metric bằng cách âm thầm làm suy giảm thuộc tính quan trọng khác.

## 13. Bước 9 — Liên kết mục tiêu chất lượng với phương pháp kiểm thử

Mục tiêu chỉ có giá trị khi có cách thu thập bằng chứng phù hợp. Một metric có thể cần nhiều phương pháp: test tự động, kiểm tra thủ công, phân tích, diễn tập hoặc dữ liệu vận hành.

### Ma trận mục tiêu – bằng chứng

| Mục tiêu chất lượng | Bằng chứng/phương pháp | Mức kiểm thử phù hợp |
|---|---|---|
| Tính đúng của tính tiền | Unit test giá trị biên, API test, đối chiếu kết quả | Unit, component, API |
| Không xử lý thanh toán trùng | Test idempotency, duplicate webhook, timeout/retry | Component, integration, contract |
| Phân quyền đúng | Positive/negative authorization test, security assessment | API, integration, security |
| Đáp ứng tải checkout | Load/stress test, latency/error/resource metrics | Performance/system |
| Tương thích browser/mobile | Browser/device matrix và exploratory test | Compatibility/UI |
| Phục hồi sau sự cố | Fault injection, failover, backup/restore rehearsal | Resilience/operational |
| Có thể vận hành | Alert test, runbook exercise, release traceability check | Operational acceptance |
| Dễ sử dụng | Usability session, task completion, lỗi thao tác và phản hồi | User acceptance/exploratory |

### Chọn test level phù hợp

Đặt kiểm tra ở mức thấp nhất có thể mà vẫn chứng minh đúng mục tiêu. Quy tắc tính giá nên được kiểm tra chi tiết bằng unit test; việc tích hợp với payment provider cần contract/integration test; hành trình checkout cần một số end-to-end test đại diện. Không cần kiểm tra mọi tổ hợp qua UI nếu có thể chứng minh quy tắc ở tầng thấp và xác nhận phối hợp ở tầng tích hợp.

### Xác định điều kiện kiểm thử

Với mỗi mục tiêu, ghi:

- Build/artifact và phiên bản liên quan.
- Môi trường, cấu hình và service dependency.
- Dữ liệu đầu vào và trạng thái ban đầu.
- Tải, concurrency, thời gian và điều kiện lỗi.
- Tool/test suite và phiên bản.
- Cách thu thập kết quả và tiêu chí pass/fail.
- Giới hạn hoặc điều chưa được xác minh.

## 14. Bước 10 — Xác định baseline, SLI/SLO và tiêu chí chấp nhận

Không phải mọi mục tiêu chất lượng đều cần một SLO vận hành, nhưng với các dịch vụ quan trọng, việc xác định baseline và chỉ số dịch vụ giúp thống nhất kỳ vọng.

### Baseline

Baseline là giá trị hiện tại hoặc dữ liệu tham chiếu để so sánh. Có thể lấy từ:

- Phiên bản hiện tại đang chạy.
- Prototype hoặc benchmark.
- Dữ liệu production đã được phép sử dụng.
- Môi trường thử nghiệm đại diện.
- Đánh giá người dùng hoặc quy trình thủ công.

Nếu chưa có baseline, ghi cách thu thập, thời gian và owner. Không đặt mục tiêu cải thiện 50% khi chưa biết giá trị hiện tại.

### SLI và SLO

- **SLI (Service Level Indicator):** chỉ số đo trải nghiệm hoặc hành vi dịch vụ, ví dụ tỷ lệ request thành công, latency hoặc tính chính xác của xử lý.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho SLI trong một cửa sổ thời gian.
- **SLA (Service Level Agreement):** cam kết dịch vụ có tính hợp đồng với khách hàng hoặc bên liên quan.

Không nên nhầm SLO nội bộ với SLA hợp đồng. Một mục tiêu kiểm thử có thể kiểm tra xem hệ thống đáp ứng SLO dự kiến trong điều kiện tải xác định hay không, nhưng test ngắn hạn không tự chứng minh SLO dài hạn trong production.

### Viết tiêu chí chấp nhận

Ví dụ cho checkout API:

- Phạm vi: endpoint tạo đơn và xác nhận checkout.
- Điều kiện: tải 500 phiên đồng thời, dữ liệu đại diện, môi trường performance được mô tả.
- Metric: p95 latency, error rate, throughput và resource saturation.
- Tiêu chí: đạt ngưỡng đã được Product/Engineering/SRE thống nhất.
- Bằng chứng: report load test, dashboard và log theo build.
- Giới hạn: chưa kiểm tra đỉnh tải theo vùng thứ hai.

Ví dụ cho authorization:

- Phạm vi: khách hàng chỉ đọc được đơn thuộc tài khoản/tenant của mình.
- Điều kiện: nhiều user, nhiều tenant, token hợp lệ và token hết hạn.
- Tiêu chí: mọi truy cập chéo tenant bị từ chối và không tiết lộ dữ liệu qua response hoặc log.
- Bằng chứng: API negative test, security review và audit log.

## 15. Bước 11 — Xác nhận mục tiêu với stakeholder

QA không nên tự quyết định mục tiêu kinh doanh hoặc ngưỡng rủi ro. Mục tiêu cần được review bởi người có kiến thức và thẩm quyền phù hợp.

### Câu hỏi review

- Mục tiêu có hỗ trợ outcome sản phẩm không?
- Metric có đo đúng trải nghiệm hoặc rủi ro cần bảo vệ không?
- Điều kiện đo có đại diện cho môi trường sử dụng không?
- Ngưỡng có dựa trên baseline, forecast, SLO hoặc hợp đồng không?
- Có thể thu thập bằng chứng trong thời gian và ngân sách hiện tại không?
- Ai xác nhận kết quả và ai chịu trách nhiệm nếu không đạt?
- Có thuộc tính quan trọng nào bị bỏ sót?
- Có trade-off hoặc rủi ro tồn dư cần ghi nhận không?

### Ghi nhận quyết định

Với mỗi mục tiêu, ghi trạng thái:

- Proposed: mới đề xuất.
- Reviewed: đã được các nhóm liên quan xem xét.
- Approved: được người có thẩm quyền xác nhận.
- Deferred: cần dữ liệu hoặc quyết định thêm.
- Rejected: không phù hợp, kèm lý do.

Không coi mục tiêu được đề xuất là tiêu chí release bắt buộc cho đến khi được xác nhận. Nếu không đạt đồng thuận, ghi rõ điểm bất đồng và người cần quyết định.

## 16. Bài tập thực hành theo từng bước

Phần này có thể thực hiện trong một workshop 2–4 giờ hoặc chia thành nhiều phiên. Thời lượng tùy độ phức tạp sản phẩm và mức sẵn có của dữ liệu.

### Bài tập A — Product context brief

**Nhiệm vụ:** viết mô tả sản phẩm trong một trang.

1. Nêu vấn đề sản phẩm giải quyết.
2. Nêu nhóm người dùng và stakeholder chính.
3. Liệt kê 3–5 outcome kinh doanh/người dùng.
4. Xác định phạm vi phiên bản hoặc release đang phân tích.
5. Ghi hệ thống và dịch vụ phụ thuộc.
6. Ghi điều kiện vận hành quan trọng.

**Tiêu chí hoàn thành:** người không tham gia workshop có thể hiểu sản phẩm dành cho ai, làm gì, phạm vi nào và thành công được đo ra sao.

### Bài tập B — Critical journey và risk discovery

**Nhiệm vụ:** chọn tối thiểu ba hành trình quan trọng, vẽ các bước và xác định điểm thất bại.

Với mỗi hành trình, ghi:

- Trigger và actor.
- Các bước chính.
- Hệ thống/phụ thuộc tham gia.
- Kết quả mong đợi.
- Điểm có thể thất bại.
- Hậu quả với người dùng/doanh nghiệp.
- Cách phát hiện và phục hồi.

**Tiêu chí hoàn thành:** có ít nhất một rủi ro được mô tả rõ cho mỗi hành trình trọng yếu và có bằng chứng hoặc câu hỏi cần xác minh.

### Bài tập C — Constraint và assumption log

**Nhiệm vụ:** ghi ít nhất năm ràng buộc hoặc giả định.

Phân loại theo thời gian, ngân sách, công nghệ, dữ liệu, bảo mật, hạ tầng, nhà cung cấp và vận hành. Ghi tác động nếu giả định sai, người xác nhận và thời hạn.

**Tiêu chí hoàn thành:** không có giả định quan trọng nào bị trình bày như dữ kiện đã xác nhận.

### Bài tập D — Chọn thuộc tính chất lượng

**Nhiệm vụ:** chọn 5–7 thuộc tính quan trọng nhất cho release đang phân tích. Có thể dùng functional suitability, performance, compatibility, usability/accessibility, reliability, security, maintainability, portability và operational readiness.

Với mỗi thuộc tính, nêu:

- Vì sao quan trọng trong bối cảnh này?
- Rủi ro nào được giảm?
- Ai quan tâm và ai xác nhận?
- Nếu không đạt thì hậu quả là gì?

**Tiêu chí hoàn thành:** mỗi thuộc tính có lý do gắn với người dùng, outcome, rủi ro hoặc nghĩa vụ; không chọn chỉ vì có trong danh sách mẫu.

### Bài tập E — Viết mục tiêu đo được

**Nhiệm vụ:** viết ít nhất một mục tiêu chất lượng cho mỗi thuộc tính ưu tiên.

Mỗi mục tiêu cần có đối tượng, metric/behavior, điều kiện, ngưỡng, bằng chứng, owner và mốc xác nhận. Nếu chưa có ngưỡng, ghi baseline cần thu thập và người phê duyệt.

**Tiêu chí hoàn thành:** một người khác có thể thiết kế cách kiểm tra và xác định pass/fail mà không phải tự đoán ý nghĩa từ ngữ.

### Bài tập F — Lập evidence/test map

**Nhiệm vụ:** ánh xạ từng mục tiêu với unit, component, API, integration, contract, end-to-end, performance, security, usability hoặc operational exercise phù hợp.

Ghi môi trường, dữ liệu, công cụ, phiên bản và giới hạn. Không dùng một loại test cho tất cả mục tiêu.

**Tiêu chí hoàn thành:** mọi mục tiêu quan trọng có ít nhất một phương pháp bằng chứng; các mục tiêu chưa có cách kiểm tra được đánh dấu là gap cần xử lý.

## 17. Bài làm mẫu cho case study thương mại điện tử

Phần dưới đây là ví dụ minh họa cách kết nối bối cảnh, rủi ro và mục tiêu chất lượng. Các ngưỡng số chỉ là giá trị giả định để minh họa cấu trúc; khi áp dụng thật phải xác nhận với Product, Engineering, SRE và các bên liên quan.

### Product context brief mẫu

| Trường | Nội dung mẫu |
|---|---|
| Sản phẩm | Nền tảng đặt hàng trực tuyến web và mobile |
| Người dùng chính | Khách mua hàng, nhân viên vận hành, quản trị viên |
| Outcome | Tăng tỷ lệ hoàn tất đơn, giảm giao dịch sai và giảm hỗ trợ thủ công |
| Critical journey | Tìm sản phẩm, checkout, thanh toán, theo dõi đơn, hoàn tiền |
| Phụ thuộc | Payment provider, inventory, shipping, identity, notification |
| Điều kiện | Cao điểm khuyến mãi, nhiều browser/mobile, webhook bất đồng bộ |
| Ràng buộc | Ngân sách cloud, sandbox quota, thời hạn release, dữ liệu test |
| Khoảng trống | Chưa xác minh forecast đỉnh tải và hành vi webhook dài hạn |

### Risk register sơ bộ

| ID | Risk statement rút gọn | Tác động | Hướng kiểm soát |
|---|---|---|---|
| R-01 | Webhook lặp có thể xử lý thanh toán nhiều lần | Giao dịch sai, đối soát và hỗ trợ | Idempotency, duplicate test, reconciliation |
| R-02 | Inventory cập nhật trễ có thể bán vượt tồn | Hủy đơn, trải nghiệm kém | Concurrency test, reservation rule, monitoring |
| R-03 | Checkout chậm khi traffic tăng | Bỏ giỏ, giảm chuyển đổi | Load test, capacity planning, queue/latency alert |
| R-04 | Phân quyền admin sai có thể lộ dữ liệu | Vi phạm quyền riêng tư | Authorization test, security review, audit |
| R-05 | Provider gián đoạn có thể làm giao dịch không rõ trạng thái | Đơn treo và xử lý thủ công | Timeout policy, status reconciliation, runbook |

### Bộ mục tiêu chất lượng mẫu

| ID | Thuộc tính | Mục tiêu minh họa | Bằng chứng |
|---|---|---|---|
| Q-01 | Functional suitability | Tổng tiền checkout phải khớp quy tắc giá, thuế, giảm giá và vận chuyển trên bộ dữ liệu biên đã xác định | Unit, API, integration test |
| Q-02 | Reliability | Retry cùng idempotency key và webhook lặp không tạo giao dịch thu tiền trùng | Component, contract, integration test |
| Q-03 | Performance | Checkout API đạt p95 dưới ngưỡng đã phê duyệt ở tải đại diện và thời lượng xác định | Load test, metric report |
| Q-04 | Security | Khách hàng không thể đọc/sửa đơn thuộc tài khoản khác; truy cập trái phép không tiết lộ dữ liệu | Authorization test, security assessment |
| Q-05 | Compatibility | Critical journey hoạt động trên browser và mobile OS thuộc ma trận hỗ trợ đã xác nhận | Browser/device matrix |
| Q-06 | Usability/accessibility | Người dùng đại diện hoàn thành checkout theo tiêu chí task success và accessibility đã thống nhất | Usability session, accessibility check |
| Q-07 | Operational readiness | Nhóm trực phát hiện payment/order mismatch và thực hiện runbook trong diễn tập | Alert test, runbook exercise |

### Nhận xét về bộ mục tiêu

- Q-01 và Q-02 bảo vệ tính đúng của giao dịch, nên cần bằng chứng ở tầng thấp và tích hợp.
- Q-03 cần điều kiện tải rõ; không thể kết luận chỉ từ một lần test ngắn hoặc một máy chạy.
- Q-04 có thể là điều kiện bắt buộc; không nên thay thế bằng một vài test UI.
- Q-05 phụ thuộc vào ma trận browser/OS được Product xác nhận.
- Q-06 cần người dùng đại diện và tiêu chí đo, không chỉ đánh giá chủ quan của nhóm phát triển.
- Q-07 xác nhận năng lực vận hành, không chỉ xác nhận code đã có logging.

## 18. Mẫu worksheet để dùng cho sản phẩm thật

Có thể sao chép mẫu dưới đây vào tài liệu workshop hoặc hệ thống quản lý yêu cầu.

```text
PRODUCT CONTEXT
Product / Release:
Product statement:
Business outcomes:
Primary user segments:
Stakeholders:
Critical journeys:
In-scope capabilities:
Out-of-scope capabilities:
Systems / integrations:
Operating conditions:

CONSTRAINTS AND ASSUMPTIONS
Constraint / assumption:
Category:
Evidence / source:
Impact if incorrect:
Owner to confirm:
Due date:
Status:

RISK
Risk ID:
Condition / cause:
Potential event:
Impact:
Likelihood:
Existing controls:
Evidence / uncertainty:
Risk owner:

QUALITY OBJECTIVE
Objective ID:
Quality attribute:
Scope / user journey:
Why it matters:
Metric / observable behavior:
Condition / workload / data:
Target / acceptance threshold:
Baseline / source:
Verification method:
Environment / tool / version:
Evidence artifact:
Owner / approver:
Release gate or review date:
Known limitation / residual risk:
```

## 19. Review chất lượng của chính bộ mục tiêu

Trước khi dùng bộ mục tiêu làm cơ sở cho chiến lược test, hãy kiểm tra tính rõ ràng và tính khả thi.

### SMART như một phép rà soát

Có thể dùng SMART để xem mục tiêu có:

- **Specific:** nói rõ đối tượng và hành vi cần đạt.
- **Measurable:** có metric hoặc bằng chứng quan sát được.
- **Achievable:** có thể đạt trong điều kiện và nguồn lực đã xác định.
- **Relevant:** liên quan outcome, stakeholder hoặc rủi ro.
- **Time-bound:** có mốc hoàn thành hoặc thời điểm review.

SMART là công cụ rà soát, không thay thế phân tích kỹ thuật. Một mục tiêu đo được nhưng không quan trọng vẫn không nên chiếm ưu tiên cao.

### Câu hỏi kiểm tra

- Có mục tiêu nào chỉ lặp lại một yêu cầu chức năng mà chưa xác định chất lượng cần bảo vệ?
- Có thuộc tính nào quan trọng với dữ liệu, giao dịch hoặc vận hành bị bỏ sót?
- Có mục tiêu nào dùng ngưỡng không có nguồn hoặc không có người phê duyệt?
- Điều kiện test có đại diện cho cách sản phẩm được dùng không?
- Có thể thu thập bằng chứng trước mốc quyết định không?
- Mục tiêu có thể kiểm tra lặp lại và cho kết quả nhất quán không?
- Có mục tiêu nào xung đột với mục tiêu khác không?
- Có khoảng trống nào cần chấp nhận, giảm thiểu hoặc dừng phát hành?

### Phát hiện mục tiêu không tốt

| Mục tiêu chưa tốt | Vấn đề | Cách cải thiện |
|---|---|---|
| Hệ thống phải nhanh | Không có endpoint, tải hoặc ngưỡng | Chọn luồng, workload, latency percentile và điều kiện |
| Bảo mật tốt | Không xác định tài sản hoặc threat | Xác định dữ liệu, actor, quyền và kịch bản truy cập |
| Không được có lỗi | Không thực tế và không có phạm vi | Xác định defect class, mức nghiêm trọng và release criteria |
| Test tất cả browser | Không có ma trận hỗ trợ hoặc ưu tiên | Xác nhận browser/device được hỗ trợ và critical journey |
| Có monitoring | Không chứng minh ai nhận và xử lý cảnh báo | Xác định metric, threshold, routing, owner và runbook |
| Dễ bảo trì | Không có tín hiệu hoặc tiêu chí review | Chọn chỉ số phù hợp như change failure, test reliability, module coupling hoặc thời gian sửa lỗi |

## 20. Những sai lầm thường gặp khi phân tích bối cảnh

**Bắt đầu từ công cụ hoặc test case.** Nhóm chọn Selenium, JMeter hoặc một framework trước khi hiểu vấn đề cần giải quyết. Hãy xác định outcome, rủi ro và bằng chứng trước rồi mới chọn công cụ.

**Chỉ hỏi Product Owner.** Product cung cấp mục tiêu nghiệp vụ nhưng có thể không biết giới hạn vận hành, dữ liệu hoặc bảo mật. Mời các vai trò chuyên môn phù hợp.

**Coi giả định là dữ kiện.** Forecast traffic hoặc hành vi sandbox chưa xác minh có thể làm mục tiêu sai. Ghi nguồn và người xác nhận.

**Chọn tất cả thuộc tính chất lượng ở mức cao.** Điều này làm mục tiêu mất khả năng ưu tiên và không phản ánh bối cảnh. Chọn theo tác động, rủi ro và nghĩa vụ.

**Dùng ngưỡng phổ biến mà không có căn cứ.** Một p95 latency phù hợp với ứng dụng này có thể không phù hợp với ứng dụng khác. Dùng baseline, forecast, SLO và stakeholder agreement.

**Đánh giá chỉ từ góc nhìn người dùng cuối.** Nhân viên vận hành, hệ thống tích hợp và đội hỗ trợ cũng có nhu cầu chất lượng. Xem toàn bộ lifecycle.

**Bỏ qua phụ thuộc bên ngoài.** Sandbox có thể khác production và nhà cung cấp có thể giới hạn request. Ghi rõ ranh giới và phần không kiểm soát được.

**Nhầm có test với có bằng chứng.** Một test không có assertion đúng hoặc chạy sai artifact không chứng minh mục tiêu. Liên kết kết quả với điều kiện và phiên bản.

**Không xác định owner.** Mục tiêu không có người xác nhận sẽ khó được chốt hoặc duy trì. Gán owner cho metric, test và quyết định.

**Không cập nhật khi bối cảnh đổi.** Quy mô, người dùng, tích hợp và nghĩa vụ có thể thay đổi. Review mục tiêu sau incident, thay đổi kiến trúc hoặc mở rộng thị trường.

## 21. Checklist hoàn thành bài thực hành

### Bối cảnh sản phẩm

- [ ] Product statement và outcome được mô tả rõ.
- [ ] Phạm vi release và năng lực chính được xác định.
- [ ] Stakeholder và user segment được lập bản đồ.
- [ ] Critical journey và điểm thất bại được mô tả.
- [ ] Hệ thống, dữ liệu và phụ thuộc được nhận diện.

### Ràng buộc và rủi ro

- [ ] Ràng buộc thời gian, ngân sách, công nghệ, dữ liệu và vận hành được ghi.
- [ ] Giả định và câu hỏi còn mở được đánh dấu.
- [ ] Risk statement có điều kiện, sự kiện và hậu quả.
- [ ] Likelihood/impact có căn cứ và owner.
- [ ] Nghĩa vụ bắt buộc được tách khỏi lựa chọn tùy ý.

### Mục tiêu chất lượng

- [ ] Thuộc tính chất lượng được chọn theo bối cảnh.
- [ ] Mỗi mục tiêu có phạm vi, metric/behavior và điều kiện.
- [ ] Ngưỡng có baseline hoặc nguồn xác nhận.
- [ ] Mục tiêu có bằng chứng, owner và thời hạn.
- [ ] Trade-off và giới hạn được ghi nhận.

### Bằng chứng và review

- [ ] Mỗi mục tiêu quan trọng được ánh xạ với phương pháp test phù hợp.
- [ ] Test level và môi trường được chọn có lý do.
- [ ] Build/version, dữ liệu và cấu hình có thể truy vết.
- [ ] Stakeholder có thẩm quyền đã review mục tiêu.
- [ ] Gap và residual risk có kế hoạch xử lý hoặc quyết định rõ.

## 22. Tự kiểm tra mức độ hiểu

**Tình huống 1:** Product Owner yêu cầu “checkout phải thật nhanh” nhưng không có số liệu. Nhóm cần hỏi về người dùng, tải, hành trình, baseline và kỳ vọng nghiệp vụ; sau đó xác định endpoint, percentile, workload, môi trường và ngưỡng được phê duyệt.

**Tình huống 2:** Một ứng dụng có ít người dùng nhưng lưu hồ sơ nhạy cảm. Không nên ưu tiên hiệu năng cao hơn bảo mật chỉ vì traffic thấp. Mức tác động của truy cập trái phép có thể rất lớn; cần mục tiêu security và bằng chứng phù hợp.

**Tình huống 3:** Sandbox payment pass mọi test nhưng provider không cam kết hành vi giống production. Báo cáo cần ghi giới hạn, bổ sung contract/production-like verification được phép và theo dõi phụ thuộc; không kết luận tích hợp hoàn toàn an toàn.

**Tình huống 4:** Nhóm có mục tiêu “không có defect critical” nhưng chưa định nghĩa critical. Cần thống nhất severity criteria, phạm vi release, nguồn phát hiện và điều kiện gate với các bên liên quan.

**Tình huống 5:** Test hiệu năng đạt ngưỡng nhưng môi trường chỉ dùng một instance, trong khi production chạy nhiều vùng. Cần xác định mục tiêu đang kiểm tra thành phần nào, bổ sung kiểm tra topology/failover hoặc ghi rõ giới hạn bằng chứng.

**Tình huống 6:** Một mục tiêu chất lượng không có owner và không có nguồn dữ liệu. Mục tiêu chưa sẵn sàng để làm acceptance criterion. Cần xác định ai cung cấp baseline, ai phê duyệt ngưỡng và ai xác minh kết quả.

**Tình huống 7:** Sau khi mở rộng sang thị trường mới, sản phẩm cần thêm locale, timezone và phương thức thanh toán. Bối cảnh đã thay đổi; cần cập nhật stakeholder, journey, risk register và quality objectives thay vì giữ nguyên bộ mục tiêu của release trước.

Khi hoàn tất bài thực hành, hãy tự hỏi: **mục tiêu chất lượng có xuất phát từ bối cảnh thật, được diễn đạt đủ cụ thể để đo, có bằng chứng phù hợp và được người có trách nhiệm xác nhận không?** Nếu chưa, ghi rõ khoảng trống và hành động tiếp theo thay vì coi mục tiêu đã hoàn tất.

## Kết luận

Phân tích bối cảnh và xác định mục tiêu chất lượng là nền tảng của một chiến lược kiểm thử phù hợp. Nhóm cần hiểu sản phẩm, người dùng, outcome, hành trình, hệ thống phụ thuộc, ràng buộc và rủi ro trước khi chọn thuộc tính chất lượng. Sau đó, chuyển kỳ vọng thành mục tiêu có phạm vi, metric, điều kiện, ngưỡng, bằng chứng, owner và thời hạn; xác nhận với stakeholder và liên kết với phương pháp kiểm thử. Khi các giả định và giới hạn được ghi rõ, chiến lược kiểm thử sẽ tập trung vào điều quan trọng đối với sản phẩm và cung cấp bằng chứng có thể dùng trong quyết định phát hành, vận hành và cải tiến.
