# Đưa yêu cầu về khả năng kiểm thử vào thiết kế và rà soát kiến trúc

Khả năng kiểm thử (testability) là mức độ dễ dàng mà nhóm có thể kiểm tra, quan sát và xác minh hành vi của một hệ thống. Một sản phẩm có khả năng kiểm thử tốt cho phép tạo trạng thái cần thiết, điều khiển đầu vào và phụ thuộc, quan sát kết quả, tái hiện lỗi và thu thập bằng chứng mà không phải dựa vào thao tác thủ công phức tạp hoặc thay đổi tạm thời trong production.

Khả năng kiểm thử không nên chỉ được xem là trách nhiệm của người viết test sau khi chức năng đã hoàn thành. Nó cần được đưa vào yêu cầu, thiết kế thành phần, kiến trúc, giao diện giữa dịch vụ, mô hình dữ liệu và cách vận hành. Nếu kiến trúc không cho phép quan sát trạng thái, cô lập phụ thuộc hoặc tái tạo điều kiện lỗi, nhóm có thể phải xây dựng nhiều giải pháp kiểm thử tốn kém, dễ hỏng và khó duy trì.

Bài học này trình bày cách xác định yêu cầu về khả năng kiểm thử, chuyển chúng thành tiêu chí có thể xác minh và rà soát kiến trúc để phát hiện trở ngại trước khi triển khai.

## 1. Hiểu khả năng kiểm thử như một thuộc tính thiết kế

Một hệ thống dễ kiểm thử khi nhóm có thể:

- Đưa hệ thống vào trạng thái cần kiểm tra bằng dữ liệu và thao tác có kiểm soát.
- Cung cấp đầu vào và mô phỏng điều kiện phụ thuộc một cách xác định.
- Quan sát kết quả qua giao diện, API, trạng thái dữ liệu, log, metric hoặc trace.
- Phân biệt lỗi của sản phẩm với lỗi môi trường và lỗi của chính bài kiểm thử.
- Cô lập thành phần để kiểm tra hành vi riêng và tương tác qua ranh giới.
- Tái tạo một tình huống lỗi và xác minh hệ thống phục hồi đúng.
- Làm sạch hoặc khôi phục trạng thái để các lần chạy không ảnh hưởng lẫn nhau.
- Thu thập bằng chứng gắn với phiên bản, cấu hình và dữ liệu đã kiểm tra.

Khả năng kiểm thử không đồng nghĩa với việc phải mở mọi chi tiết nội bộ ra bên ngoài. Cần cung cấp những điểm quan sát và điều khiển phù hợp với ranh giới kiến trúc, quyền truy cập và yêu cầu bảo mật.

Ví dụ, một dịch vụ xử lý đơn hàng có thể nhận request qua API, lưu trạng thái trong cơ sở dữ liệu và gửi sự kiện sang dịch vụ thanh toán. Nếu không có cách truy vấn trạng thái theo mã tương quan, không thể kiểm soát callback hoặc không thể tạo dữ liệu đơn hàng lặp lại, việc kiểm thử sẽ khó xác định liệu giao dịch đã hoàn tất hay chưa. Bổ sung API truy vấn có kiểm soát, mã tương quan, cơ chế sandbox và dữ liệu tạo lại được sẽ cải thiện khả năng kiểm thử ngay từ thiết kế.

## 2. Xác định yêu cầu testability từ nhu cầu kiểm thử

Không nên thêm yêu cầu kỹ thuật chung chung như “hệ thống phải dễ kiểm thử”. Hãy bắt đầu từ những câu hỏi mà nhóm cần trả lời trong suốt vòng đời:

- Làm sao xác minh một yêu cầu đã được xử lý đúng?
- Làm sao biết dịch vụ phụ đã nhận hoặc từ chối một thông điệp?
- Làm sao tái hiện timeout, lỗi mạng hoặc phản hồi không hợp lệ?
- Làm sao tạo dữ liệu cho trường hợp biên và dữ liệu lớn?
- Làm sao xác định request nào tạo ra một thay đổi dữ liệu?
- Làm sao kiểm tra quyền của từng vai trò mà không dùng tài khoản production?
- Làm sao biết một bản triển khai đã dùng đúng cấu hình?
- Làm sao xác minh tác vụ nền đã hoàn tất hoặc thất bại?
- Làm sao khôi phục trạng thái sau khi kiểm thử?

Từ các câu hỏi đó, xác định thuộc tính testability cần có. Ví dụ, nếu cần kiểm tra xử lý thông điệp lặp, thiết kế phải cho phép gửi lại cùng một thông điệp hoặc cùng một khóa idempotency và quan sát kết quả. Nếu cần kiểm tra thời gian xử lý, hệ thống phải cung cấp timestamp, metric hoặc trace có độ chính xác và đồng bộ phù hợp.

Mỗi yêu cầu nên gắn với một rủi ro, một khả năng kiểm thử cụ thể và cách xác minh. Nhờ vậy, nhóm có thể ưu tiên những cải tiến mang lại giá trị thực thay vì bổ sung điểm móc kỹ thuật không có mục đích rõ ràng.

## 3. Các thuộc tính chính của một hệ thống dễ kiểm thử

Có thể đánh giá testability theo nhiều chiều. Các chiều này liên quan với nhau và không nhất thiết phải tối đa hóa riêng lẻ.

| Thuộc tính | Ý nghĩa | Ví dụ thiết kế hỗ trợ |
|---|---|---|
| Khả năng quan sát (observability) | Nhìn thấy trạng thái và kết quả bên trong qua tín hiệu phù hợp | Log có cấu trúc, metric, trace, mã tương quan, health endpoint |
| Khả năng điều khiển (controllability) | Đưa hệ thống vào trạng thái hoặc điều kiện cần kiểm tra | API quản trị an toàn, cấu hình, test fixture, clock abstraction |
| Tính xác định (determinism) | Cùng điều kiện đầu vào tạo kết quả có thể dự đoán | Tiêm clock, seed dữ liệu, kiểm soát thứ tự và ngẫu nhiên |
| Khả năng cô lập (isolation) | Kiểm tra một thành phần mà không bị ảnh hưởng ngoài ý muốn | Interface rõ, dependency injection, namespace hoặc tenant riêng |
| Khả năng tái tạo (reproducibility) | Lặp lại một tình huống và thu được bằng chứng tương đương | Cấu hình có phiên bản, dữ liệu tạo lại được, script triển khai |
| Khả năng chẩn đoán (diagnosability) | Khoanh vùng nguyên nhân khi kết quả sai | Error code, trace xuyên dịch vụ, log theo request |
| Khả năng phục hồi trạng thái | Dọn dữ liệu và đưa môi trường về trạng thái sạch | Transaction rollback, fixture teardown, reset test environment |
| Khả năng truy cập kiểm thử | Công cụ và người kiểm thử có thể tương tác qua ranh giới được phép | API test, tài khoản theo vai trò, sandbox, tài liệu giao diện |
| Khả năng mở rộng kiểm thử | Tăng số lượng kịch bản hoặc tải mà không làm mất kiểm soát | Chạy song song, dữ liệu độc lập, môi trường có thể cấp phát |

Không phải mọi thuộc tính đều cần cùng mức đầu tư. Một thư viện tính toán thuần có thể cần tính xác định và khả năng cô lập hơn là dashboard vận hành. Một hệ thống phân tán cần khả năng quan sát, điều khiển phụ thuộc và tái tạo lỗi mạng ở mức cao hơn.

## 4. Đưa yêu cầu quan sát vào kiến trúc

Khả năng quan sát giúp nhóm biết hệ thống đã làm gì và vì sao. Nếu chỉ nhìn thấy kết quả cuối cùng, việc điều tra lỗi xuyên nhiều dịch vụ có thể rất khó.

### 4.1. Log có cấu trúc

Thiết kế log để ghi nhận sự kiện có ý nghĩa, mức độ, thời điểm, thành phần và ngữ cảnh cần thiết. Với hệ thống phân tán, dùng request ID, correlation ID hoặc trace ID để nối các bước xử lý.

Log nên giúp trả lời:

- Yêu cầu đi qua thành phần nào?
- Hành động nào đã xảy ra?
- Kết quả là thành công, thất bại hay đang chờ?
- Lỗi bắt nguồn từ thành phần nào?
- Có mã lỗi hoặc mã giao dịch nào để truy vết?

Tránh ghi mật khẩu, token, khóa bí mật hoặc toàn bộ dữ liệu cá nhân. Cần thiết kế che dữ liệu, kiểm soát quyền truy cập và thời hạn lưu ngay từ đầu.

### 4.2. Metrics và traces

Metrics cho biết xu hướng và mức độ hoạt động, chẳng hạn số request, tỷ lệ lỗi, độ trễ hoặc độ sâu hàng đợi. Distributed traces giúp quan sát một request đi qua nhiều dịch vụ và thời gian tiêu tốn ở từng đoạn.

Nếu mục tiêu kiểm thử cần xác minh p95 latency hoặc thời gian hoàn tất tác vụ nền, hệ thống phải phát ra chỉ số và span phù hợp. Không thể đo đáng tin nếu mỗi dịch vụ dùng cách định nghĩa thời gian khác nhau hoặc không có điểm bắt đầu/kết thúc thống nhất.

### 4.3. Trạng thái và health checks

Thiết kế endpoint hoặc cơ chế báo trạng thái để phân biệt tiến trình còn sống, sẵn sàng nhận việc và phụ thuộc đang suy giảm. Không nên dùng một tín hiệu “healthy” duy nhất để che giấu việc một chức năng quan trọng không hoạt động.

Ví dụ, một worker có thể đang chạy nhưng không xử lý được thông điệp vì mất kết nối database. Health check cần phản ánh đúng mục đích: kiểm tra liveness để phát hiện tiến trình treo, readiness để quyết định có nhận traffic, và các chỉ số phụ để quan sát phụ thuộc.

## 5. Đưa khả năng điều khiển vào thiết kế

Khả năng điều khiển giúp nhóm tạo ra điều kiện kiểm thử mà không cần can thiệp thủ công hoặc sửa mã nguồn mỗi lần.

Các cơ chế hữu ích:

- API hoặc giao diện quản trị có kiểm soát để tạo dữ liệu, truy vấn trạng thái hoặc kích hoạt tác vụ.
- Cấu hình có thể thay đổi theo môi trường mà không sửa mã.
- Dependency injection để thay thế dịch vụ bên ngoài bằng fake hoặc stub trong kiểm thử.
- Clock abstraction để kiểm tra thời hạn, lịch và timeout mà không phải chờ thời gian thực.
- Cơ chế seed hoặc fixture để tạo dữ liệu có quan hệ nhất quán.
- Feature flag để bật/tắt chức năng theo phạm vi và kiểm tra trạng thái chuyển tiếp.
- Sandbox của nhà cung cấp để thử giao dịch hoặc callback.
- Khả năng phát lại thông điệp trong môi trường thử nghiệm.

Các cơ chế này cần được bảo vệ. API quản trị chỉ nên hoạt động trong môi trường phù hợp hoặc yêu cầu xác thực và phân quyền nghiêm ngặt. Không tạo một endpoint reset dữ liệu có thể truy cập công khai. Không để test hook làm thay đổi hành vi production ngoài chủ đích.

## 6. Thiết kế tính xác định và khả năng tái tạo

Một bài kiểm thử khó tin cậy nếu cùng đầu vào nhưng kết quả thay đổi vì thời gian, số ngẫu nhiên, thứ tự xử lý, trạng thái dùng chung hoặc phụ thuộc bên ngoài.

Một số nguồn không xác định thường gặp:

- Dùng thời gian hiện tại trực tiếp trong logic.
- Sinh ID hoặc dữ liệu ngẫu nhiên mà không có seed.
- Phụ thuộc thứ tự thực thi giữa các test.
- Dùng dữ liệu chung bị test khác thay đổi.
- Phụ thuộc dịch vụ bên ngoài có trạng thái hoặc phản hồi biến động.
- Có race condition hoặc tác vụ nền chưa hoàn tất khi assertion chạy.
- Phụ thuộc timezone, locale hoặc cấu hình máy chạy.

Các cách cải thiện:

- Tiêm clock hoặc nguồn thời gian để kiểm soát ngày giờ trong test.
- Dùng seed xác định cho dữ liệu ngẫu nhiên khi cần tái hiện.
- Tạo dữ liệu riêng cho từng test hoặc nhóm test.
- Chờ theo điều kiện trạng thái thay vì sleep cố định.
- Dùng fake server hoặc sandbox cho phụ thuộc bên ngoài.
- Ghi phiên bản, cấu hình và seed cùng kết quả chạy.
- Làm rõ thứ tự và tính nhất quán của tác vụ bất đồng bộ.

Ví dụ, thay vì chờ 24 giờ để kiểm tra tác vụ hết hạn, thiết kế cho phép cấp một clock giả trong test để chuyển thời gian đến thời điểm cần xác minh. Trong production, clock thật vẫn được sử dụng. Cơ chế này giúp kiểm tra nhiều mốc thời gian nhanh và lặp lại được.

## 7. Tách thành phần và định nghĩa ranh giới dễ kiểm thử

Kiến trúc có coupling quá chặt khiến việc kiểm tra một quy tắc nhỏ phải khởi động nhiều dịch vụ hoặc truy cập hệ thống thật. Ranh giới thành phần rõ giúp nhóm kiểm thử logic độc lập và xác minh tích hợp ở những điểm cần thiết.

Các nguyên tắc thiết kế hữu ích:

- Mỗi thành phần có trách nhiệm rõ và giao diện công khai ổn định.
- Logic nghiệp vụ không phụ thuộc trực tiếp vào chi tiết hạ tầng khi không cần thiết.
- Dùng interface hoặc abstraction cho database, clock, queue và dịch vụ bên ngoài.
- Tách phần tính toán thuần khỏi thao tác I/O và tác dụng phụ.
- Tránh singleton hoặc global state khó reset.
- Xác định rõ ai sở hữu dữ liệu và trạng thái.
- Đặt quy tắc timeout, retry và lỗi tại ranh giới phụ thuộc.

Ví dụ, logic tính phí vận chuyển nên nhận đầu vào là địa chỉ, trọng lượng và quy tắc giá; trả kết quả mà không tự gọi API bản đồ hoặc database. Việc này giúp unit test các trường hợp biên dễ dàng. Tích hợp với dịch vụ địa chỉ và lưu đơn hàng được kiểm tra riêng ở lớp phù hợp.

Không nên tách thành quá nhiều interface chỉ để test có thể mock mọi thứ. Abstraction cần phản ánh ranh giới có ý nghĩa trong kiến trúc và giúp thay thế phụ thuộc thực sự cần kiểm soát.

## 8. Thiết kế khả năng kiểm thử cho hệ thống bất đồng bộ và phân tán

Hệ thống dùng queue, event, scheduler hoặc nhiều dịch vụ thường khó kiểm tra vì kết quả không xuất hiện ngay và thông điệp có thể đến trễ, lặp hoặc sai thứ tự.

Các yêu cầu testability nên xem xét:

- Mỗi thông điệp có ID và metadata truy vết.
- Có thể quan sát trạng thái nhận, xử lý, retry, dead-letter và hoàn tất.
- Có cơ chế phát lại thông điệp trong môi trường thử nghiệm.
- Có cách tạo thông điệp lỗi, trùng hoặc đến sai thứ tự.
- Tác vụ có idempotency hoặc quy tắc chống xử lý lặp.
- Timeout và retry có cấu hình rõ, có giới hạn.
- Có cách xác định khi nào hệ thống đã đạt trạng thái cuối.
- Có thể cô lập queue, topic hoặc consumer group theo test run.

Tránh viết test chờ một khoảng thời gian tùy ý rồi kiểm tra kết quả. Nên có điều kiện chờ dựa trên trạng thái, event hoặc truy vấn có timeout rõ. Nếu một tác vụ nền thất bại, cần có dấu vết để phân biệt chưa chạy, đang chạy, retry hay đã chuyển dead-letter.

Với eventual consistency, tiêu chí kiểm thử cần xác định khoảng thời gian hội tụ hoặc điều kiện kết thúc hợp lý. Không nên đòi hỏi mọi dịch vụ cập nhật tức thời nếu kiến trúc không cam kết điều đó.

## 9. Đưa yêu cầu testability vào dữ liệu và cấu hình

Dữ liệu và cấu hình ảnh hưởng trực tiếp đến khả năng tái hiện hành vi. Thiết kế tốt cần giúp tạo, kiểm tra và dọn dữ liệu mà không phụ thuộc vào trạng thái ngẫu nhiên.

Các yêu cầu cần xem xét:

- Có cách tạo dữ liệu hợp lệ, biên, không hợp lệ và dữ liệu lớn không?
- Dữ liệu có thể được seed, reset hoặc tạo lại theo phiên bản không?
- Quan hệ và ràng buộc dữ liệu có thể kiểm tra được không?
- Có thể cô lập dữ liệu theo test run, tenant hoặc namespace không?
- Cấu hình có nguồn chuẩn, phiên bản và cách xác minh không?
- Có thể biết giá trị cấu hình thực tế khi test chạy không?
- Bí mật có được cấp an toàn và tách khỏi dữ liệu test không?
- Dữ liệu nhạy cảm có được che hoặc thay bằng dữ liệu tổng hợp không?

Một hệ thống không nên buộc người kiểm thử chèn trực tiếp bản ghi vào database để đạt trạng thái cần thiết nếu thao tác đó bỏ qua quy tắc nghiệp vụ. Khi cần seed nhanh, cung cấp fixture hoặc factory sử dụng cùng quy tắc và có thể ghi nhận nguồn tạo dữ liệu.

Cấu hình nên được quản lý ngoài mã nguồn, có schema hoặc validation và có thể kiểm tra trước khi triển khai. Khi test thất bại do cấu hình sai, log cần cho biết cấu hình nào có hiệu lực mà không tiết lộ secret.

## 10. Thiết kế testability cho lỗi, timeout và phục hồi

Kiểm thử độ tin cậy cần tạo ra tình huống lỗi có kiểm soát. Nếu kiến trúc không có cách mô phỏng lỗi, nhóm thường chỉ kiểm tra đường đi thành công.

Hãy xem xét khả năng:

- Mô phỏng timeout, mất kết nối và phản hồi chậm.
- Trả lỗi có chủ đích từ dịch vụ phụ.
- Gửi lại request hoặc thông điệp.
- Dừng và khởi động lại worker.
- Tạo tình trạng đầy queue hoặc cạn tài nguyên trong giới hạn an toàn.
- Kích hoạt circuit breaker hoặc fallback.
- Kiểm tra rollback, retry và phục hồi trạng thái.
- Đối chiếu dữ liệu sau khi một bước của quy trình thất bại.

Có thể dùng fake server, proxy thử nghiệm, fault injection framework hoặc cơ chế cấu hình dành cho môi trường test. Các cơ chế này phải có giới hạn, ghi log và không thể vô tình kích hoạt trong production.

Ví dụ, để kiểm tra retry khi dịch vụ thanh toán timeout, môi trường thử nghiệm cần điều khiển được phản hồi của sandbox: phản hồi thành công, từ chối, chậm hoặc không trả lời. Nhóm đồng thời cần truy vấn được trạng thái giao dịch để xác minh retry không tạo khoản thu trùng.

## 11. Đưa khả năng kiểm thử vào yêu cầu phi chức năng

Testability có thể được thể hiện thành yêu cầu chất lượng có thể xác minh, không chỉ là nguyên tắc thiết kế.

| Nhóm yêu cầu | Ví dụ nội dung yêu cầu | Cách xác minh |
|---|---|---|
| Quan sát | Mỗi request xuyên dịch vụ có mã tương quan có thể truy vết | Gửi request thử và xác minh log/trace tại các thành phần |
| Chẩn đoán | Lỗi phụ thuộc có mã lỗi và thành phần nguồn rõ ràng | Mô phỏng lỗi và kiểm tra thông tin chẩn đoán |
| Điều khiển | Có thể tạo dữ liệu thử theo vai trò và phạm vi được phép | Dùng fixture/API test và xác minh quyền |
| Tái tạo | Một test run có thể tái tạo bằng phiên bản, cấu hình và dữ liệu đã lưu | Chạy lại cùng bộ đầu vào và so sánh kết quả |
| Cô lập | Test run không làm thay đổi dữ liệu của tenant hoặc test run khác | Chạy song song và xác minh ranh giới dữ liệu |
| Bất đồng bộ | Có thể quan sát trạng thái cuối của tác vụ nền | Gửi tác vụ và chờ điều kiện hoàn tất có timeout |
| Phục hồi | Có thể kiểm tra retry và phục hồi sau lỗi phụ | Fault injection và đối chiếu trạng thái sau phục hồi |
| Bảo mật | Công cụ kiểm thử chỉ truy cập tài nguyên trong phạm vi được cấp | Rà soát quyền, audit log và thử truy cập ngoài phạm vi |

Các tiêu chí cần được cụ thể hóa theo sản phẩm. Ví dụ, yêu cầu “mọi request có correlation ID” cần xác định ID được tạo ở đâu, truyền qua thành phần nào, có xuất hiện trong log và trace không, và cách xử lý khi consumer không gửi ID.

## 12. Rà soát kiến trúc theo góc nhìn testability

Rà soát kiến trúc nên đặt câu hỏi về cách kiểm tra và thu thập bằng chứng trước khi thiết kế được cố định.

Một buổi rà soát có thể đi qua các chủ đề:

### 12.1. Ranh giới và phụ thuộc

- Thành phần có trách nhiệm và giao diện rõ không?
- Có thể kiểm thử logic riêng mà không khởi động toàn bộ hệ thống không?
- Phụ thuộc bên ngoài có abstraction hoặc sandbox phù hợp không?
- Có điểm lỗi đơn hoặc coupling khiến test khó cô lập không?

### 12.2. Trạng thái và dữ liệu

- Có thể tạo trạng thái ban đầu và dọn trạng thái sau test không?
- Có thể truy vấn trạng thái cuối mà không đọc trực tiếp dữ liệu nội bộ không?
- Dữ liệu có thể tạo lại và cô lập giữa các test không?
- Migration có thể được kiểm tra và khôi phục trong môi trường thử nghiệm không?

### 12.3. Quan sát và chẩn đoán

- Có log, metric và trace cho luồng quan trọng không?
- Có correlation ID xuyên dịch vụ không?
- Lỗi có đủ thông tin để khoanh vùng mà không lộ dữ liệu nhạy cảm không?
- Có thể phân biệt lỗi ứng dụng với lỗi phụ thuộc hoặc môi trường không?

### 12.4. Điều khiển và lỗi

- Có thể điều khiển clock, random, timeout và phản hồi phụ thuộc không?
- Có thể mô phỏng lỗi mạng, lỗi dịch vụ và thông điệp lặp không?
- Có thể kiểm tra retry, idempotency và phục hồi không?
- Cơ chế test hook có bị giới hạn và bảo vệ không?

### 12.5. Triển khai và vận hành

- Môi trường có thể được tạo lại từ cấu hình có phiên bản không?
- Có thể triển khai cùng artifact và cấu hình đã xác minh không?
- Có thể quan sát phiên bản thực tế của từng dịch vụ không?
- Có cơ chế dừng, rollback và khôi phục sau kiểm thử không?

Mỗi phát hiện kiến trúc nên được ghi thành quyết định hoặc hành động có chủ sở hữu. Ví dụ, nếu một tác vụ nền không có trạng thái quan sát, hành động có thể là bổ sung trạng thái job và mã tương quan; tiêu chí xác minh là test có thể phân biệt pending, running, succeeded và failed.

## 13. Ví dụ: rà soát testability cho dịch vụ đặt hàng

Giả sử hệ thống đặt hàng gồm API tiếp nhận yêu cầu, dịch vụ quản lý đơn hàng, database, queue và dịch vụ thanh toán bên ngoài. Nhóm cần kiểm tra tạo đơn, tính tiền, retry và callback.

Một số câu hỏi thiết kế:

| Rủi ro hoặc câu hỏi kiểm thử | Thiếu sót kiến trúc có thể gặp | Yêu cầu testability đề xuất |
|---|---|---|
| Đơn hàng có được tạo đúng một lần không? | Không có khóa idempotency hoặc mã giao dịch truy vết | Hỗ trợ idempotency key, lưu trạng thái xử lý và truy vấn theo mã |
| Callback đến trễ hoặc lặp được xử lý ra sao? | Không quan sát được callback đã nhận và trạng thái xử lý | Log có correlation ID, trạng thái callback và khả năng phát lại trong sandbox |
| Tác vụ nền có hoàn tất không? | Không có trạng thái job hoặc chỉ biết qua thời gian chờ | Cung cấp trạng thái tác vụ và điều kiện truy vấn cuối |
| Dịch vụ thanh toán timeout thì sao? | Không thể điều khiển phản hồi phụ thuộc | Dùng sandbox/fake server có thể cấu hình timeout và lỗi |
| Test có ảnh hưởng dữ liệu lẫn nhau không? | Dữ liệu dùng chung và không có quy tắc dọn | Tạo dữ liệu theo test run hoặc tenant riêng, có cleanup |
| Có thể truy nguyên lỗi xuyên dịch vụ không? | Log mỗi dịch vụ dùng mã riêng không liên kết | Truyền trace/correlation ID xuyên các thành phần |

Một tiêu chí cụ thể có thể là: “Với một request tạo đơn có idempotency key xác định, khi gửi lại cùng request nhiều lần trong thời gian hiệu lực, hệ thống chỉ tạo một đơn hàng và trả về cùng mã đơn; kết quả có thể được truy vấn bằng mã tương quan.”

Nhóm có thể xác minh bằng cách gửi request lặp tuần tự và đồng thời, mô phỏng timeout, khởi động lại worker và đối chiếu bản ghi đơn hàng cùng mã giao dịch. Nếu không thể quan sát số lượng đơn đã tạo hoặc không thể kiểm soát timeout, thiết kế chưa cung cấp đủ khả năng kiểm thử cho rủi ro này.

## 14. Quản lý yêu cầu testability trong vòng đời thay đổi

Yêu cầu testability cần được theo dõi giống các yêu cầu chất lượng khác. Khi kiến trúc hoặc phụ thuộc thay đổi, khả năng kiểm thử có thể suy giảm dù chức năng vẫn hoạt động.

Hãy đưa rà soát testability vào:

- Refinement yêu cầu và tiêu chí chấp nhận.
- Architecture review và design review.
- Pull request có thay đổi ranh giới, dữ liệu hoặc phụ thuộc.
- Đánh giá tích hợp dịch vụ mới.
- Thay đổi logging, monitoring, cấu hình hoặc quyền.
- Chuẩn bị release và diễn tập phục hồi.
- Phân tích sự cố và lỗi khó tái hiện.

Duy trì danh sách yêu cầu và khoảng trống testability với các trường: mã yêu cầu, rủi ro được hỗ trợ, thành phần, tiêu chí xác minh, chủ sở hữu, trạng thái và bằng chứng. Khi một yêu cầu bị loại bỏ hoặc thay đổi, ghi lý do và đánh giá ảnh hưởng đến test suite.

Không nên coi testability là khoản đầu tư chỉ làm một lần. Mỗi thay đổi có thể thêm phụ thuộc mới, tạo trạng thái khó kiểm soát hoặc làm mất điểm quan sát. Đưa câu hỏi testability vào review thường xuyên giúp phát hiện vấn đề trước khi chúng trở thành chi phí bảo trì lớn.

## 15. Checklist đưa testability vào thiết kế và kiến trúc

Trước khi chốt thiết kế hoặc chấp nhận một thay đổi kiến trúc, hãy kiểm tra:

- Các rủi ro và câu hỏi cần kiểm thử đã được xác định chưa?
- Có thể quan sát trạng thái và kết quả của luồng quan trọng không?
- Log, metric và trace có đủ ngữ cảnh nhưng không lộ dữ liệu nhạy cảm không?
- Có thể tạo và kiểm soát đầu vào, dữ liệu, thời gian và phụ thuộc không?
- Test có thể chạy độc lập mà không phụ thuộc thứ tự hoặc trạng thái dùng chung không?
- Các thành phần có ranh giới và interface đủ rõ để kiểm thử riêng không?
- Hệ thống bất đồng bộ có trạng thái, mã tương quan và cách quan sát kết quả cuối không?
- Có thể mô phỏng timeout, lỗi mạng, thông điệp lặp và phục hồi không?
- Cấu hình, artifact và dữ liệu có thể tái tạo theo phiên bản không?
- Có cách dọn dữ liệu và khôi phục môi trường sau test không?
- Test hook, API quản trị và sandbox có được bảo vệ đúng quyền không?
- Yêu cầu testability có tiêu chí chấp nhận và người sở hữu không?
- Bằng chứng xác minh có thể truy vết đến build, cấu hình và dữ liệu không?
- Các thay đổi kiến trúc có kích hoạt rà soát testability không?

Sơ đồ sau tóm tắt cách đưa testability vào quyết định thiết kế:

~~~mermaid
flowchart TD
    A["Yêu cầu và rủi ro chất lượng"] --> B["Xác định câu hỏi cần kiểm thử"]
    B --> C["Xác định thuộc tính testability"]
    C --> D["Thiết kế quan sát, điều khiển và cô lập"]
    D --> E["Định nghĩa tiêu chí chấp nhận testability"]
    E --> F["Rà soát kiến trúc và phụ thuộc"]
    F --> G{"Có thể tạo, chạy và xác minh test?"}
    G -->|Có| H["Triển khai và thu thập bằng chứng"]
    G -->|Chưa| I["Ghi khoảng trống và điều chỉnh thiết kế"]
    I --> D
    H --> J["Theo dõi thay đổi và rà soát lại"]
    J --> A
~~~

Đưa yêu cầu về khả năng kiểm thử vào thiết kế giúp nhóm tránh những trở ngại khó sửa sau khi hệ thống đã lớn và có nhiều phụ thuộc. Một kiến trúc dễ kiểm thử cho phép tạo trạng thái, điều khiển điều kiện, quan sát kết quả, tái hiện lỗi và thu thập bằng chứng trong phạm vi an toàn. Khi các khả năng đó được mô tả thành yêu cầu có tiêu chí xác minh và được rà soát cùng kiến trúc, chất lượng kiểm thử trở thành thuộc tính được xây dựng ngay trong sản phẩm.

