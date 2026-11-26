# Thông báo vận hành

*Thiết kế cảnh báo và thông báo sự cố cho luồng application event trong Spring Modulith*

Một hệ thống dùng application event có thể tiếp tục nhận yêu cầu nghiệp vụ ngay cả khi một listener đang lỗi, nhưng điều đó không có nghĩa sự cố có thể bị bỏ qua. Publication có thể tồn đọng, retry có thể tăng, consumer có thể chậm dần hoặc message có thể rơi vào dead-letter queue. Nếu không có thông báo vận hành phù hợp, nhóm hỗ trợ chỉ phát hiện vấn đề khi người dùng báo dữ liệu thiếu hoặc một quy trình nghiệp vụ bị đình trệ.

**Thông báo vận hành** là tín hiệu có ngữ cảnh được gửi đến người hoặc hệ thống chịu trách nhiệm khi luồng event vượt khỏi trạng thái hoạt động bình thường. Một thông báo tốt cho biết điều gì đang xảy ra, phạm vi ảnh hưởng, mức độ khẩn cấp, nơi cần kiểm tra và hành động tiếp theo. Mục tiêu là giúp người trực xử lý đúng vấn đề, không tạo thêm nhiễu từ mọi exception đơn lẻ.

## 1. Phân biệt log, metric, trace và alert

Các tín hiệu quan sát phục vụ những câu hỏi khác nhau. Thông báo vận hành nên được tạo từ tín hiệu có thể đo lường và đối chiếu, không chỉ từ một dòng log bất kỳ.

| Tín hiệu | Trả lời câu hỏi | Ví dụ trong event flow |
|---|---|---|
| Log | Một lần xử lý cụ thể đã xảy ra điều gì? | Listener `InvoiceProjectionListener` lỗi với `eventId` nào và exception gì? |
| Metric | Tình trạng tổng thể đang thay đổi ra sao? | Số publication chưa hoàn tất, retry rate, tuổi publication lâu nhất |
| Trace | Một luồng xử lý đi qua những thành phần nào? | Từ command, publisher, listener đến broker và consumer |
| Alert | Có điều kiện nào cần người chịu trách nhiệm hành động? | Publication tồn đọng quá lâu và vượt ngưỡng ảnh hưởng SLO |
| Incident notification | Ai cần biết, mức độ nào và cần làm gì tiếp? | On-call nhận cảnh báo backlog tăng, kèm runbook và dashboard |

Log giúp điều tra một event; metric cho thấy xu hướng; trace nối các bước xử lý; alert chuyển một điều kiện bất thường thành hành động. Không gửi thông báo cho mọi log lỗi vì retry một lần có thể là hành vi bình thường. Cũng không nên chỉ dựa vào metric tổng hợp nếu người trực không thể tìm ra event hoặc listener cụ thể gây ra vấn đề.

## 2. Xác định những gì cần thông báo

Trong Spring Modulith, event publication registry theo dõi publication cho các transactional listener và hỗ trợ nhận diện publication chưa hoàn tất. Đây là nguồn tín hiệu quan trọng, nhưng trạng thái publication cần được đặt trong bối cảnh vận hành của ứng dụng.

Những tín hiệu thường cần theo dõi:

- **Publication chưa hoàn tất:** số lượng và tuổi của publication còn chờ theo listener hoặc externalization target.
- **Listener thất bại:** tỷ lệ lỗi, số lần retry và nhóm exception lặp lại.
- **Độ trễ xử lý:** thời gian từ lúc event xảy ra hoặc commit đến khi listener hoàn tất.
- **Retry bất thường:** một event hoặc một nhóm event liên tục thất bại, hoặc số lần thử tăng nhanh.
- **Dead-letter:** message bị chuyển sang luồng cần điều tra thủ công.
- **Consumer lag hoặc queue backlog:** consumer không theo kịp tốc độ phát event.
- **Lỗi hạ tầng:** broker, database, scheduler hoặc dịch vụ phụ thuộc không sẵn sàng.
- **Lỗi hợp đồng:** payload không giải mã được, thiếu schema hoặc xuất hiện event type chưa được hỗ trợ.

Không phải mọi tín hiệu đều cần đánh thức on-call. Một lần retry thành công trong thời gian ngắn có thể chỉ cần metric và log. Một publication chưa hoàn tất vượt thời gian xử lý cho phép, hoặc backlog tiếp tục tăng, mới có thể cần cảnh báo. Hãy xác định ngưỡng theo SLO, lưu lượng và thời gian phục hồi thực tế.

## 3. Đặt SLI và SLO cho event processing

Trước khi cấu hình alert, hãy xác định dịch vụ cần duy trì điều gì. Với event flow, các chỉ số cấp dịch vụ có thể gồm:

- **Delivery completion:** tỷ lệ publication hoàn tất trong cửa sổ thời gian đã cam kết.
- **Processing latency:** thời gian từ lúc event commit đến khi consumer hoàn tất.
- **Backlog age:** tuổi của publication hoặc message chưa xử lý lâu nhất.
- **Recovery time:** thời gian từ khi phát hiện lỗi đến khi backlog trở lại mức bình thường.
- **Dead-letter rate:** tỷ lệ message cần can thiệp thủ công.

Ví dụ, một read model báo cáo có thể chấp nhận độ trễ vài phút; một luồng xác nhận thanh toán có thể cần ngưỡng ngắn hơn nhiều. Không dùng chung một ngưỡng cho mọi listener chỉ vì chúng nằm trong cùng ứng dụng.

Một SLO có thể diễn đạt: “99,5% event của projection hóa đơn được xử lý trong vòng 60 giây trong cửa sổ 30 ngày”. Các con số chỉ là ví dụ minh họa; nhóm sản phẩm và vận hành phải xác định mục tiêu dựa trên yêu cầu nghiệp vụ. Alert nên cảnh báo khi error budget hoặc độ trễ đang tiêu thụ nhanh, thay vì chỉ khi có một exception.

## 4. Phân cấp mức độ nghiêm trọng

Mức độ alert cần phản ánh ảnh hưởng và thời gian cần hành động. Một phân cấp đơn giản:

| Mức | Ý nghĩa | Ví dụ | Phản ứng |
|---|---|---|---|
| Critical / P1 | Luồng trọng yếu ngừng hoạt động hoặc dữ liệu nghiệp vụ có nguy cơ mất nhất quán nghiêm trọng | Publication thanh toán tồn đọng diện rộng; broker không nhận message và không có đường phục hồi | Đánh thức on-call ngay, mở incident và cập nhật tình hình |
| High / P2 | Một nhóm consumer quan trọng suy giảm vượt SLO | Listener hóa đơn lỗi liên tục, backlog tăng nhanh | On-call xử lý trong thời gian phản hồi đã quy định |
| Warning / P3 | Có dấu hiệu bất thường nhưng chưa ảnh hưởng rõ đến người dùng | Retry tăng nhẹ hoặc một publication chậm hơn bình thường | Gửi đến kênh vận hành, theo dõi xu hướng và kiểm tra trong giờ làm việc |
| Info | Thông tin trạng thái hoặc tác vụ bảo trì | Rebuild projection hoàn tất, backlog trở về bình thường | Ghi nhận trên dashboard hoặc kênh thông tin |

Không nâng mọi lỗi listener thành Critical. Nếu alert luôn ở mức khẩn cấp, người trực sẽ khó nhận ra sự cố thật sự. Mức độ nên xét phạm vi consumer, tuổi backlog, SLO, khả năng retry và tác động nghiệp vụ.

## 5. Thiết kế điều kiện alert có thể hành động

Alert cần có điều kiện rõ ràng, thời gian duy trì và ngưỡng phục hồi. Một số ví dụ về logic:

- Cảnh báo khi publication chưa hoàn tất của listener trọng yếu có tuổi vượt ngưỡng xử lý trong nhiều chu kỳ liên tiếp.
- Cảnh báo khi số publication chưa hoàn tất tăng liên tục và tốc độ hoàn tất thấp hơn tốc độ phát.
- Cảnh báo khi tỷ lệ listener failure vượt ngưỡng trong một cửa sổ đủ dài, thay vì một lỗi đơn lẻ.
- Cảnh báo khi consumer lag hoặc queue depth vượt mức mà thời gian xử lý dự kiến không thể bắt kịp trước deadline nghiệp vụ.
- Cảnh báo ngay khi có message vào dead-letter queue của luồng trọng yếu.
- Cảnh báo khi không có heartbeat hoặc metric của consumer trong thời gian dài.

Ví dụ cấu trúc rule minh họa, không gắn với cú pháp của một nền tảng alert cụ thể:

```yaml
alert: CriticalEventPublicationBacklog
scope:
  application: orders
  listener: invoice-projection
condition:
  incomplete_publications: above_expected_limit
  oldest_publication_age: exceeds_processing_slo
for: sustained_window
severity: high
route_to: application-events-oncall
runbook: event-publication-backlog
```

Các tên `above_expected_limit`, `exceeds_processing_slo` và `sustained_window` là placeholder mô tả ý nghĩa. Khi triển khai, thay bằng biểu thức, ngưỡng và thời lượng cụ thể của hệ thống giám sát đang dùng.

Dùng cả ngưỡng tuyệt đối và xu hướng. Một backlog 100 event có thể bình thường với luồng lớn nhưng nghiêm trọng với luồng chỉ phát vài event mỗi giờ. Tuổi event thường phản ánh tác động tốt hơn chỉ số đếm đơn thuần.

## 6. Gắn thông báo với đúng ngữ cảnh event

Thông báo cần giúp người trực xác định phạm vi và truy ra dữ liệu gốc. Các trường hữu ích gồm:

- Tên ứng dụng, môi trường và module phát event.
- Listener hoặc externalization target bị ảnh hưởng.
- Event type, `eventId`, aggregate ID và correlation ID.
- Thời điểm event xảy ra, thời điểm xử lý gần nhất và tuổi publication.
- Trạng thái hiện tại, attempt count và nguyên nhân lỗi gần nhất.
- Số lượng event đang chờ và xu hướng tăng/giảm.
- Link đến dashboard, log/trace và runbook tương ứng.

Ví dụ nội dung alert:

```text
Severity: HIGH
Service: orders
Consumer: invoice-projection
Event type: OrderCompleted
Event ID: 6d947d20-5b1c-45c6-a6d6-87c7c96d9f12
Condition: oldest incomplete publication exceeded processing SLO
Backlog: 184 publications; trend: increasing
Last error: database connection timeout
Action: inspect the runbook and verify database availability before resubmitting
```

Thông báo nên có một event hoặc một nhóm event đại diện, không đính kèm toàn bộ payload. Tránh đưa token, thông tin thanh toán, dữ liệu cá nhân hoặc nội dung nhạy cảm vào chat, email hay hệ thống ticket. Dùng ID và liên kết có phân quyền để người trực mở chi tiết khi cần.

## 7. Chống thông báo trùng và alert storm

Một sự cố có thể làm hàng nghìn event cùng lỗi. Nếu gửi một thông báo cho từng event, kênh vận hành sẽ bị ngập và che mất thông tin quan trọng. Cần gom nhóm và khử trùng lặp theo nguyên nhân hoặc phạm vi:

- Nhóm theo ứng dụng, listener, exception class, destination hoặc dependency bị lỗi.
- Dùng fingerprint ổn định để các alert cùng nguyên nhân cập nhật một incident thay vì tạo incident mới.
- Đặt khoảng thời gian suppression khi incident đang mở và đã có người nhận xử lý.
- Giới hạn tần suất gửi nhắc lại; chỉ nhắc khi mức độ hoặc số liệu thay đổi đáng kể.
- Gửi một thông báo phục hồi khi điều kiện đã trở lại bình thường trong khoảng thời gian ổn định.

Khử trùng lặp alert không được làm mất event lỗi. Log, metric và publication registry vẫn phải giữ đủ dữ liệu để điều tra từng event. Chỉ gộp thông báo gửi người trực; không xóa trạng thái nghiệp vụ hoặc dấu vết giao event.

## 8. Chọn kênh thông báo và người nhận

Kênh gửi cần phù hợp với mức độ khẩn cấp và quy trình làm việc của tổ chức:

| Kênh | Phù hợp khi | Lưu ý |
|---|---|---|
| On-call paging | Sự cố P1/P2 cần phản ứng ngoài giờ | Cần lịch trực, escalation và xác nhận đã nhận |
| Chat vận hành | Cảnh báo P2/P3, cập nhật incident và phối hợp | Dùng channel có phân quyền, tránh gửi bí mật |
| Email | Báo cáo, cảnh báo không cần phản hồi tức thì | Không dùng email làm kênh duy nhất cho sự cố nghiêm trọng |
| Incident/ticket system | Theo dõi người phụ trách, trạng thái và lịch sử xử lý | Tạo ticket có deduplication và liên kết alert gốc |
| Dashboard | Theo dõi sức khỏe và xu hướng | Dashboard không thay thế paging khi cần hành động ngay |

Định tuyến theo ownership. Lỗi listener của module hóa đơn nên đến nhóm sở hữu luồng hóa đơn; lỗi broker hoặc database có thể cần phối hợp với nhóm nền tảng. Nếu nhiều nhóm cùng chịu trách nhiệm, xác định một primary owner và nhóm hỗ trợ để tránh tình trạng mọi người đều nghĩ người khác đang xử lý.

## 9. Runbook phải đi cùng alert

Một alert không có hướng dẫn xử lý thường chỉ làm người trực biết rằng hệ thống đang lỗi. Runbook cần cung cấp các bước kiểm tra theo thứ tự và tiêu chí kết thúc.

Với cảnh báo publication backlog, runbook có thể hướng dẫn:

1. Xác nhận môi trường, ứng dụng, listener và thời điểm bắt đầu sự cố.
2. Kiểm tra dashboard backlog, tuổi publication lâu nhất, retry rate và số listener đang hoạt động.
3. Đọc log/trace của một số event đại diện để xác định lỗi nằm ở handler, database, broker hay dịch vụ phụ thuộc.
4. Xác nhận dependency đã phục hồi và nguyên nhân gốc đã được xử lý.
5. Kiểm tra handler có idempotent và side effect trước đó có thể đã xảy ra chưa.
6. Chọn phạm vi retry/resubmission phù hợp; bắt đầu với một nhóm nhỏ nếu có thể.
7. Theo dõi publication hoàn tất, backlog giảm và read model hoặc kết quả nghiệp vụ đã nhất quán.
8. Ghi nhận nguyên nhân, hành động, thời gian phục hồi và việc cần cải thiện sau incident.

Không nên hướng dẫn người trực xóa publication, purge queue hoặc reset offset như bước đầu tiên. Những thao tác này có thể làm mất dấu vết hoặc tạo duplicate. Runbook phải giải thích điều kiện, quyền hạn và ảnh hưởng trước khi thực hiện hành động có rủi ro.

## 10. Tích hợp thông báo với Spring Modulith

Spring Modulith cung cấp event publication registry để theo dõi publication của transactional listener và externalization target. Ứng dụng có thể dùng thông tin publication chưa hoàn tất để xây dựng metric, dashboard và alert. Cách lấy dữ liệu cụ thể phụ thuộc persistence implementation và phiên bản Spring Modulith; không giả định mọi phiên bản đều cung cấp sẵn một metric tên cố định.

Với listener dùng `@ApplicationModuleListener`, exception có thể khiến publication chưa hoàn tất theo cơ chế transaction và registry. Hệ thống giám sát nên quan sát trạng thái publication, tuổi và xu hướng thay vì chỉ đếm exception trong log. Khi cần resubmit, hãy thực hiện theo quy trình có kiểm soát sau khi dependency và handler đã sẵn sàng.

Không nên phát thông báo vận hành bằng chính listener đang gặp lỗi mà không có đường giao độc lập. Nếu mọi alert đều phải đi qua cùng broker hoặc database đang hỏng, thông báo có thể thất bại cùng sự cố. Kênh cảnh báo quan trọng nên có đường vận chuyển và giám sát độc lập đủ để báo khi event pipeline chính không hoạt động.

Nếu ứng dụng tạo operational event nội bộ để tổng hợp cảnh báo, cần tránh vòng lặp: lỗi của alert handler không được liên tục phát ra alert mới cùng loại. Dùng suppression, dead-letter hoặc một kênh fallback tách biệt cho chính thành phần thông báo.

## 11. Phân biệt thông báo vận hành và thông báo nghiệp vụ

Thông báo vận hành hướng đến người chịu trách nhiệm duy trì hệ thống. Thông báo nghiệp vụ hướng đến người dùng hoặc hệ thống nghiệp vụ để thông tin về trạng thái giao dịch. Hai loại có yêu cầu khác nhau:

| Tiêu chí | Thông báo vận hành | Thông báo nghiệp vụ |
|---|---|---|
| Người nhận | On-call, SRE, nhóm sở hữu module | Người dùng, nhân viên nghiệp vụ, hệ thống tích hợp |
| Nội dung | Nguyên nhân, mức độ, phạm vi, runbook | Trạng thái đơn hàng, thanh toán hoặc quy trình |
| Tần suất | Theo incident và mức độ ảnh hưởng | Theo sự kiện hoặc tùy chọn người nhận |
| Bảo đảm | Đến đúng người trực trong thời gian phản hồi | Theo chính sách giao thông báo của sản phẩm |
| Kênh | Paging, chat vận hành, ticket | Email, push, SMS hoặc giao diện ứng dụng |

Không gửi stack trace, tên bảng hoặc thông tin hạ tầng cho người dùng cuối. Ngược lại, không dùng thông báo nghiệp vụ như “đơn hàng đã hoàn tất” để thay thế cảnh báo khi listener hoặc broker đang gặp sự cố.

## 12. Kiểm thử quy tắc thông báo

Kiểm thử cần xác nhận cả điều kiện kích hoạt, nội dung, định tuyến và cơ chế phục hồi:

1. **Ngưỡng backlog:** alert chỉ kích hoạt khi số lượng/tuổi publication vượt ngưỡng và thời gian duy trì đã cấu hình.
2. **Lỗi đơn lẻ:** một lần retry thành công không tạo paging nghiêm trọng nếu chưa vi phạm SLO.
3. **Tăng trưởng backlog:** cảnh báo phát hiện consumer không theo kịp producer dù số lỗi tức thời thấp.
4. **Dead-letter:** message vào DLQ tạo cảnh báo đúng owner và có runbook.
5. **Deduplication:** nhiều event cùng nguyên nhân được gộp thành một incident có cập nhật số liệu.
6. **Escalation:** alert không được xác nhận sẽ chuyển đến người hoặc nhóm tiếp theo theo lịch trực.
7. **Recovery notification:** khi backlog trở về bình thường, incident được cập nhật hoặc đóng theo điều kiện ổn định.
8. **Kênh cảnh báo độc lập:** kiểm tra cảnh báo vẫn đến được người trực khi broker chính không hoạt động.
9. **Bảo mật:** nội dung alert không chứa payload nhạy cảm hoặc secret.
10. **Runbook:** link và hướng dẫn trong alert dẫn đến đúng quy trình xử lý.

Nên kiểm thử alert rule bằng dữ liệu mô phỏng hoặc môi trường staging. Không tạo lỗi giả trên production chỉ để kiểm tra kênh paging nếu chưa có quy trình diễn tập được phê duyệt.

## 13. Quy trình xử lý incident và đóng cảnh báo

Khi nhận alert, người trực cần xác nhận quyền sở hữu, đánh giá phạm vi ảnh hưởng và xác định bước điều tra tiếp theo. Trong quá trình xử lý, cập nhật incident theo các mốc quan trọng: phát hiện, xác định nguyên nhân, giảm tác động, phục hồi và xác nhận dữ liệu.

Sau khi sửa nguyên nhân, không đóng incident ngay khi metric giảm trong một chu kỳ. Hãy chờ backlog ổn định, publication tiếp tục hoàn tất, consumer lag giảm về mức bình thường và dữ liệu read model được xác nhận. Nếu phải resubmit hoặc replay, ghi lại phạm vi và kết quả để hỗ trợ đối soát.

Sau incident, xem xét liệu alert có phát hiện đủ sớm, có gửi đúng người, có gây nhiễu hoặc thiếu thông tin không. Điều chỉnh ngưỡng, dashboard và runbook dựa trên dữ liệu thực tế. Mục tiêu là giảm thời gian phát hiện và phục hồi, đồng thời giữ số alert có thể hành động ở mức hợp lý.

## 14. Những điểm cần nhớ

- Log, metric và trace cung cấp bằng chứng; alert chuyển điều kiện bất thường thành hành động vận hành.
- Theo dõi publication chưa hoàn tất, tuổi backlog, retry, listener failure, consumer lag và dead-letter.
- Đặt SLI/SLO và mức độ nghiêm trọng theo tác động nghiệp vụ, không paging cho mọi exception đơn lẻ.
- Thông báo cần có owner, event/listener context, xu hướng, runbook và hành động tiếp theo.
- Deduplicate và group alert để tránh alert storm nhưng vẫn giữ nguyên dấu vết từng event.
- Kênh cảnh báo trọng yếu cần có đường vận chuyển độc lập với event pipeline có thể đang lỗi.
- Phân biệt thông báo vận hành với thông báo nghiệp vụ; kiểm thử routing, escalation, recovery và bảo mật.

Khi cảnh báo được xây dựng từ tín hiệu đáng tin cậy, gửi đúng người và đi kèm runbook có thể thực hiện, nhóm vận hành có thể phát hiện sớm publication bị kẹt, listener lỗi hoặc consumer tụt lại. Kết hợp event publication registry, metric, log và trace giúp hệ thống Spring Modulith duy trì giao sự kiện đáng tin cậy và phục hồi có kiểm soát.
