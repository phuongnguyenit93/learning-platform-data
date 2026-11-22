# Lỗi và sự cố: Xác định dữ liệu cần có để tái hiện và đánh giá tác động

## 1. Vì sao cần thu thập dữ liệu có cấu trúc?

Khi một defect hoặc incident được báo cáo, mô tả như “ứng dụng bị lỗi”, “đơn hàng không cập nhật” hoặc “một số người dùng không đăng nhập được” chưa đủ để nhóm kỹ thuật tái hiện và đánh giá phạm vi. Muốn hiểu chuyện gì đã xảy ra, nhóm cần dữ liệu về điều kiện ban đầu, hành động, thời điểm, phiên bản, môi trường, danh tính liên quan và kết quả quan sát được.

Thu thập dữ liệu có cấu trúc phục vụ hai mục tiêu liên quan nhưng khác nhau:

- **Tái hiện:** xác định điều kiện và chuỗi thao tác đủ để tạo lại hành vi lỗi, từ đó kiểm tra giả thuyết về nguyên nhân.
- **Đánh giá tác động:** xác định ai hoặc thành phần nào bị ảnh hưởng, trong khoảng thời gian nào, dữ liệu hay giao dịch nào bị tác động và mức độ nghiêm trọng ra sao.

Một bộ dữ liệu đủ để tái hiện có thể chưa đủ để định lượng tác động. Ví dụ, một request mẫu có thể tái tạo lỗi phân quyền, nhưng để đánh giá incident cần biết endpoint, tenant, phiên bản, thời gian tồn tại và số lượng tài khoản hoặc bản ghi có nguy cơ bị truy cập.

Trong **VALIDATION_TESTING_STRATEGY**, dữ liệu defect và incident cần giúp nhóm đi từ báo cáo ban đầu đến một kết luận có thể kiểm chứng: điều kiện nào tạo ra lỗi, hành vi mong đợi là gì, hành vi thực tế là gì, phạm vi ảnh hưởng ra sao và bằng chứng nào còn thiếu.

## 2. Phân biệt dữ liệu tái hiện và dữ liệu đánh giá tác động

### 2.1. Dữ liệu để tái hiện

Dữ liệu tái hiện tập trung vào một trường hợp hoặc chuỗi sự kiện cụ thể:

- Phiên bản ứng dụng và cấu hình liên quan.
- Môi trường và phụ thuộc.
- Vai trò, quyền và danh tính đã được thay thế an toàn.
- Đầu vào, request, event hoặc thao tác người dùng.
- Trạng thái ban đầu và quan hệ dữ liệu.
- Thời điểm, timezone và thứ tự sự kiện.
- Kết quả mong đợi và kết quả thực tế.
- Log, trace, error code và correlation ID.

Mục tiêu là tạo ra một trường hợp nhỏ, có thể lặp lại, để phân tích.

### 2.2. Dữ liệu để đánh giá tác động

Dữ liệu đánh giá tác động tập trung vào phạm vi và hậu quả:

- Các phiên bản, môi trường và thành phần bị ảnh hưởng.
- Khoảng thời gian bắt đầu, kết thúc hoặc thời gian chưa xác định.
- Nhóm người dùng, tenant, khu vực hoặc loại thiết bị.
- Số lượng request, giao dịch, tài khoản hoặc bản ghi liên quan.
- Loại dữ liệu bị sai, mất, trùng, lộ hoặc không truy cập được.
- Ảnh hưởng tới doanh thu, hoạt động, SLA, bảo mật hoặc tuân thủ.
- Biện pháp giảm thiểu đã thực hiện và tác động còn tồn tại.
- Mức độ tin cậy của số liệu và phần chưa biết.

Đánh giá tác động có thể cần truy vấn tổng hợp, log đã lọc, metric hoặc báo cáo từ nhiều nguồn. Không nên chỉ suy rộng từ một trường hợp tái hiện đơn lẻ.

### 2.3. Bảng so sánh

| Khía cạnh | Tái hiện | Đánh giá tác động |
| --- | --- | --- |
| Câu hỏi chính | Làm thế nào tạo lại lỗi? | Lỗi ảnh hưởng tới đâu và hậu quả gì? |
| Phạm vi dữ liệu | Một trường hợp hoặc chuỗi tối thiểu | Tập hợp người dùng, request, giao dịch hoặc tài nguyên |
| Dữ liệu trọng tâm | Input, state, thứ tự, phiên bản và cấu hình | Thời gian, số lượng, phạm vi, mức độ và hậu quả |
| Phương pháp | Thực hiện lại có kiểm soát, test harness, replay an toàn | Truy vấn, phân tích log/metric, đối chiếu dữ liệu và xác minh với chủ sở hữu |
| Kết quả | Bước tái hiện và bằng chứng lỗi | Phạm vi ảnh hưởng, severity, rủi ro còn lại |

Một quy trình xử lý tốt giữ liên kết giữa hai nhóm dữ liệu. Trường hợp tái hiện giúp giải thích cơ chế; dữ liệu tác động cho biết cơ chế đó đã ảnh hưởng tới hệ thống hoặc người dùng ở mức nào.

## 3. Bộ thông tin tối thiểu cho một báo cáo defect hoặc incident

### 3.1. Nhận diện sự việc

Mỗi báo cáo cần có định danh và mô tả ngắn:

- ID defect hoặc incident.
- Tiêu đề thể hiện triệu chứng.
- Người hoặc hệ thống báo cáo.
- Thời điểm phát hiện và thời điểm xảy ra nếu biết.
- Môi trường nơi quan sát.
- Mức độ khẩn cấp ban đầu và trạng thái xử lý.
- Người/nhóm chịu trách nhiệm điều phối.

Không dùng tiêu đề chỉ ghi “bug”, “lỗi hệ thống” hoặc “không chạy”. Một tiêu đề tốt nêu thành phần và hành vi, ví dụ: “Booking API trả trạng thái CONFIRMED dù payment callback bị từ chối”.

### 3.2. Phiên bản và cấu hình

Ghi lại:

- Release, build number, commit SHA hoặc image tag.
- Phiên bản client, browser, mobile app hoặc SDK.
- Schema/database migration đang hoạt động.
- Feature flag và cấu hình có liên quan.
- Phiên bản dependency hoặc provider nếu có thể xác định.
- Thời điểm triển khai và lịch sử thay đổi gần nhất.

Không giả định mọi instance đều chạy cùng phiên bản. Với hệ thống triển khai từng phần, cần biết request đi qua instance hoặc region nào nếu thông tin đó ảnh hưởng đến kết quả.

### 3.3. Môi trường và điều kiện vận hành

Thông tin có thể gồm:

- Local, CI, test, staging hoặc production.
- Region, zone, tenant hoặc namespace.
- Hệ điều hành, thiết bị và browser.
- Network path, proxy, DNS hoặc VPN nếu liên quan.
- Database, cache, queue và dịch vụ phụ thuộc.
- Tải nền, concurrency và tài nguyên tại thời điểm lỗi.
- Trạng thái health/readiness và cảnh báo đang hoạt động.

Chỉ thu thập chi tiết có ích cho phạm vi điều tra. Không đưa secret, credential hoặc thông tin nhạy cảm vào báo cáo.

### 3.4. Danh tính, vai trò và quyền

Đối với lỗi liên quan truy cập hoặc hành vi theo người dùng, cần biết:

- Loại actor: người dùng, admin, service account, worker hoặc hệ thống bên ngoài.
- Vai trò, scope, permission và tenant.
- Trạng thái tài khoản, session hoặc token tại thời điểm xảy ra.
- Cách xác thực và cơ chế ủy quyền có liên quan.
- Tài nguyên mà actor đã cố truy cập hoặc thay đổi.

Trong báo cáo dùng mã tham chiếu đã được phê duyệt thay cho mật khẩu, token hoặc định danh cá nhân trực tiếp. Không yêu cầu người báo cáo gửi credential để tái hiện lỗi.

### 3.5. Đầu vào, hành động và trạng thái ban đầu

Ghi lại:

- Request method, endpoint, header không nhạy cảm và payload đã được làm sạch.
- Event/message, schema và metadata liên quan.
- Dữ liệu form hoặc tham số đầu vào.
- Trạng thái ban đầu của đối tượng và các bản ghi liên quan.
- Thứ tự các thao tác hoặc sự kiện.
- Điều kiện thời gian, timezone, locale hoặc concurrency.
- Kết quả mong đợi và kết quả thực tế.

Nếu dữ liệu đầu vào lớn, lưu một mẫu tối thiểu hoặc tham chiếu tới artifact có quyền truy cập phù hợp. Không dán toàn bộ dữ liệu sản xuất vào ticket hoặc chat.

## 4. Xây dựng timeline đáng tin cậy

### 4.1. Vì sao timeline quan trọng?

Nhiều defect chỉ xuất hiện khi các sự kiện xảy ra theo thứ tự hoặc trong một khoảng thời gian nhất định. Ví dụ:

- Callback đến trước khi đơn hàng được tạo xong.
- Hai request cập nhật cùng một bản ghi gần như đồng thời.
- Token hết hạn giữa một chuỗi thao tác.
- Worker nhận event sau khi trạng thái đã đổi.
- Một lần triển khai diễn ra giữa các request.

Timeline giúp phân biệt nguyên nhân, thứ tự và hệ quả. Mỗi mốc nên có timestamp, timezone, nguồn và mã tham chiếu.

### 4.2. Những mốc nên ghi

| Mốc | Dữ liệu cần có |
| --- | --- |
| Lần cuối hệ thống hoạt động bình thường | Thời điểm và nguồn xác nhận |
| Thay đổi gần nhất | Deploy, config, migration, feature flag hoặc dependency |
| Lần đầu quan sát lỗi | Timestamp, actor, request/event ID |
| Các bước dẫn tới lỗi | Thứ tự hành động và trạng thái sau từng bước |
| Thời điểm cảnh báo | Alert, dashboard hoặc báo cáo người dùng |
| Thời điểm giảm thiểu | Rollback, disable feature, chặn traffic hoặc workaround |
| Thời điểm phục hồi | Health check và bằng chứng hành vi trở lại bình thường |
| Phần ảnh hưởng còn lại | Giao dịch tồn đọng, dữ liệu cần sửa hoặc người dùng cần hỗ trợ |

Nếu thời điểm bắt đầu chưa rõ, ghi một khoảng ước lượng và căn cứ. Không tạo timestamp chính xác giả từ một log chỉ có độ phân giải phút.

### 4.3. Đồng bộ thời gian và timezone

Khi kết hợp log từ nhiều dịch vụ:

- Ưu tiên timestamp có timezone hoặc UTC.
- Ghi nhận độ lệch đồng hồ nếu đã biết.
- Phân biệt thời điểm client gửi, server nhận, event được phát và consumer xử lý.
- Không so sánh timestamp từ các hệ thống không đồng bộ mà không nêu giới hạn.
- Ghi rõ timestamp là thời điểm xảy ra, thời điểm ghi log hay thời điểm ingest.

Với lỗi phụ thuộc deadline, expiration hoặc ngày nghiệp vụ, lưu cả instant chuẩn và timezone hiển thị nếu cần. Một ngày giờ địa phương có thể mơ hồ khi chuyển đổi DST hoặc khi nhiều khu vực dùng chung dữ liệu.

## 5. Thu thập log, trace, metric và bằng chứng kỹ thuật

### 5.1. Log

Log có thể giúp xác định:

- Thành phần đã nhận request hoặc event.
- Nhánh xử lý được thực hiện.
- Exception, error code hoặc validation failure.
- Thông tin dependency và retry.
- Trạng thái trước/sau nếu hệ thống ghi nhận an toàn.

Nên có timestamp, severity, service name, version và correlation ID. Log thiếu ngữ cảnh hoặc chỉ ghi “operation failed” thường khó sử dụng trong điều tra.

### 5.2. Distributed trace

Trace giúp nối các span qua nhiều dịch vụ. Với mỗi trace liên quan, lưu:

- Trace ID và span ID.
- Service/version xử lý từng span.
- Thời lượng và thứ tự span.
- Error status và dependency call.
- Bối cảnh request đã được làm sạch.

Trace có thể bị sampling nên không phải request nào cũng có trace. Việc không tìm thấy trace không chứng minh request chưa xảy ra. Cần kiểm tra sampling policy và thời hạn lưu.

### 5.3. Metric

Metric cung cấp góc nhìn tổng hợp:

- Request rate, error rate và latency percentile.
- Queue depth, consumer lag và retry count.
- CPU, memory, connection pool và saturation.
- Số giao dịch thành công/thất bại.
- Tỷ lệ đăng nhập, timeout hoặc tác vụ bị bỏ lỡ.

Metric giúp xác định thời điểm và quy mô bất thường nhưng thường không chỉ ra bản ghi hoặc request cụ thể. Kết hợp metric với log, trace và dữ liệu nghiệp vụ khi cần.

### 5.4. Bằng chứng từ client

Với lỗi UI hoặc thiết bị, có thể cần:

- Screenshot hoặc video ngắn.
- Browser console và network request đã làm sạch.
- Browser/device/OS version.
- Viewport, locale, timezone và accessibility setting.
- Thao tác chính xác trước khi lỗi xuất hiện.
- Trạng thái UI và thông báo hiển thị.

Ảnh chụp cần có thời điểm hoặc mã phiên liên quan. Trước khi chia sẻ, loại bỏ thông tin cá nhân, token, dữ liệu thanh toán và nội dung riêng tư.

### 5.5. Đối chiếu nhiều nguồn

Không nên kết luận chỉ dựa vào một log nếu có thể xác minh qua nguồn độc lập. Ví dụ, khi đánh giá thanh toán:

- API response cho biết yêu cầu được tiếp nhận.
- Payment provider sandbox hoặc báo cáo giao dịch cho biết kết quả phía provider.
- Ledger/database cho biết tác dụng phụ tài chính đã được ghi.
- Event log cho biết callback đã được phát và xử lý.

Các nguồn có thể có độ trễ hoặc ngữ nghĩa khác nhau. Ghi rõ nguồn nào là hệ thống ghi nhận có thẩm quyền cho từng trạng thái.

## 6. Tái hiện defect một cách có kiểm soát

### 6.1. Từ báo cáo ban đầu đến bước tái hiện

Chuyển mô tả thành kịch bản có cấu trúc:

1. **Điều kiện trước:** phiên bản, môi trường, actor, quyền và trạng thái dữ liệu.
2. **Hành động:** các bước hoặc request theo thứ tự.
3. **Điều kiện đồng thời/thời gian:** nếu lỗi phụ thuộc concurrency, delay hoặc deadline.
4. **Kết quả mong đợi:** hợp đồng hoặc bất biến cần được giữ.
5. **Kết quả thực tế:** điều gì xảy ra khác với mong đợi.
6. **Bằng chứng:** log, trace, ID và dữ liệu đầu ra.

Ví dụ:

~~~text
Điều kiện trước:
- Booking service build R42
- Hai khách hàng test độc lập
- Một slot đang AVAILABLE
- Database và broker sẵn sàng

Hành động:
1. Gửi hai yêu cầu booking gần như đồng thời cho cùng slot.
2. Chờ cả hai request hoàn tất.
3. Đọc trạng thái cuối của slot và booking.

Mong đợi:
- Chỉ một booking được CONFIRMED.
- Slot không bị cấp cho hai khách hàng.

Quan sát:
- Hai response đều báo thành công.
- Có hai booking CONFIRMED cho cùng slot.
- Hai request có correlation ID riêng.
~~~

Kịch bản này cho biết cần dữ liệu concurrency và trạng thái cuối. Chỉ lưu một response thành công sẽ không đủ để chứng minh lỗi tranh chấp.

### 6.2. Thu nhỏ trường hợp tái hiện

Sau khi tái hiện được, giảm dần dữ liệu và bước không cần thiết:

- Bỏ các trường không ảnh hưởng.
- Dùng một actor hoặc số lượng bản ghi tối thiểu cần thiết.
- Giữ lại đúng phiên bản/config gây lỗi.
- Giữ nguyên thứ tự và timing quan trọng.
- Thay dữ liệu nhạy cảm bằng dữ liệu tổng hợp có cùng đặc điểm cần kiểm tra.

Mục tiêu là tìm trường hợp nhỏ nhất vẫn tái hiện lỗi. Trường hợp tối thiểu giúp viết regression test nhanh, dễ hiểu và ít phụ thuộc.

### 6.3. Khi lỗi không ổn định

Với lỗi intermittent hoặc race condition:

- Ghi số lần thử và số lần xuất hiện.
- Ghi concurrency, tải nền và thời gian giữa các thao tác.
- Lưu seed hoặc lịch sự kiện nếu có randomization.
- Thu thập trace của cả lần thành công và thất bại để so sánh.
- Kiểm tra ảnh hưởng từ test khác hoặc dữ liệu dùng chung.
- Tránh tăng timeout hoặc retry đến mức che mất điều kiện lỗi.

Nếu chưa tái hiện được, vẫn có thể đánh giá tác động từ telemetry và dữ liệu vận hành. Ghi riêng “chưa tái hiện” và “chưa xác định tác động”; hai trạng thái này không đồng nghĩa.

## 7. Đánh giá phạm vi và mức độ tác động

### 7.1. Xác định đối tượng bị ảnh hưởng

Đánh giá theo nhiều chiều:

- Người dùng, tài khoản, tenant hoặc nhóm quyền.
- Khu vực địa lý, region hoặc cluster.
- Phiên bản ứng dụng, API, SDK hoặc thiết bị.
- Tính năng, endpoint, workflow hoặc loại giao dịch.
- Dữ liệu, bản ghi hoặc tài nguyên.
- Khoảng thời gian và tần suất xảy ra.
- Dependency hoặc provider liên quan.

Một lỗi xảy ra trên một tenant có thể có tác động khác với lỗi xảy ra trên mọi tenant. Cần có truy vấn hoặc bằng chứng để xác định phạm vi, không suy luận từ một báo cáo riêng lẻ.

### 7.2. Định lượng quy mô

Các chỉ số có thể cần thu thập:

| Loại | Ví dụ chỉ số |
| --- | --- |
| Người dùng | Số tài khoản/tenant bị ảnh hưởng, số người không thể hoàn tất tác vụ |
| Request | Tổng request, request lỗi, tỷ lệ lỗi theo endpoint |
| Giao dịch | Số đơn, thanh toán, hoàn tiền hoặc booking bị ảnh hưởng |
| Dữ liệu | Số bản ghi mất, trùng, sai trạng thái hoặc có nguy cơ lộ |
| Thời gian | Thời lượng gián đoạn, thời gian phục hồi, độ trễ xử lý tồn đọng |
| Vận hành | Số job thất bại, queue backlog, số lần retry |
| Tài chính | Giá trị giao dịch bị giữ, thất bại hoặc cần đối soát |

Ghi cả số tuyệt đối và mẫu số khi có thể. “500 lỗi” khó diễn giải nếu không biết tổng có 600 hay 5 triệu request.

### 7.3. Đánh giá tác động chức năng và phi chức năng

Không chỉ đếm số người bị ảnh hưởng. Xem xét:

- **Chức năng:** người dùng có hoàn tất tác vụ không, trạng thái có sai không?
- **Dữ liệu:** có mất, hỏng, trùng hoặc không nhất quán không?
- **Bảo mật/quyền riêng tư:** dữ liệu có bị truy cập hoặc tiết lộ trái phép không?
- **Hiệu năng/khả dụng:** latency, error rate, downtime và queue lag thay đổi thế nào?
- **Tài chính:** có giao dịch sai, tính phí sai hoặc thất thoát không?
- **Tuân thủ:** có nghĩa vụ thông báo, lưu trữ hoặc báo cáo nào bị ảnh hưởng không?
- **Danh tiếng và vận hành:** có gián đoạn quy trình hoặc hỗ trợ khách hàng không?

Đối với bảo mật và quyền riêng tư, cần đánh giá cả nguy cơ và dữ liệu thực tế đã bị truy cập hay chưa. Không có bằng chứng truy cập không đồng nghĩa không có nguy cơ; phải ghi rõ mức độ quan sát được.

### 7.4. Phân biệt severity và priority

- **Severity (mức độ nghiêm trọng):** mức độ hậu quả hoặc tổn hại do lỗi gây ra.
- **Priority (mức ưu tiên):** thứ tự xử lý dựa trên urgency, rủi ro, thời hạn và nguồn lực.

Một lỗi severity cao có thể cần ưu tiên tức thời. Một lỗi ít nghiêm trọng nhưng ảnh hưởng tới đợt phát hành sắp tới có thể được nâng priority. Hai giá trị này không nên dùng thay thế cho nhau.

### 7.5. Khung đánh giá mức độ nghiêm trọng

Ví dụ về khung phân loại có thể điều chỉnh theo chính sách tổ chức:

| Mức | Dấu hiệu tham khảo | Hướng phản ứng |
| --- | --- | --- |
| Critical | Nguy cơ mất an toàn, lộ dữ liệu nhạy cảm diện rộng, mất dữ liệu nghiêm trọng hoặc hệ thống cốt lõi ngừng hoạt động | Kích hoạt quy trình incident khẩn cấp, containment và điều phối liên nhóm |
| High | Chức năng quan trọng bị gián đoạn hoặc nhiều người dùng/giao dịch bị ảnh hưởng, chưa có workaround phù hợp | Ưu tiên xử lý sớm, xác định phạm vi và giảm thiểu |
| Medium | Chức năng bị suy giảm trong phạm vi giới hạn hoặc có workaround khả thi | Lập kế hoạch sửa theo mức rủi ro và mốc phát hành |
| Low | Ảnh hưởng nhỏ, ít gặp, không làm sai dữ liệu hoặc chặn quy trình chính | Xử lý theo backlog và chính sách |

Severity phải dựa trên tác động đã biết và rủi ro hợp lý. Nếu chưa đủ dữ liệu, ghi mức đánh giá tạm thời cùng giả định và thời điểm xem xét lại.

## 8. Đánh giá mức độ tin cậy và khoảng chưa biết

### 8.1. Gắn kết luận với chất lượng bằng chứng

Mỗi kết luận nên nêu:

- Nguồn dữ liệu.
- Khoảng thời gian và phạm vi truy vấn.
- Số lượng mẫu và mẫu số.
- Phương pháp lọc/tính toán.
- Giới hạn telemetry hoặc sampling.
- Mức độ tin cậy và giả định.

Ví dụ: “Ít nhất 120 request trên 40 tài khoản bị ảnh hưởng theo log gateway trong 14:00–14:30 UTC; con số có thể thấp hơn thực tế vì một phần request không có correlation ID.”

### 8.2. Phân biệt không thấy với không xảy ra

Không có log, trace hoặc alert có thể do:

- Collector bị dừng.
- Sampling loại bỏ sự kiện.
- Retention đã hết.
- Log level không ghi nhận nhánh xử lý.
- Request đi qua một đường chưa được instrument.
- Bộ lọc truy vấn sai.

Do đó, câu “không có log lỗi” chỉ là mô tả nguồn log đã truy vấn, không tự chứng minh sự kiện không xảy ra.

### 8.3. Dùng khoảng ước lượng khi chưa thể đếm chính xác

Nếu số lượng chính xác chưa thể xác định, có thể báo:

- Số tối thiểu đã xác minh.
- Khoảng ước lượng dựa trên nguồn hiện có.
- Số tối đa có thể bị ảnh hưởng theo phạm vi kỹ thuật.
- Các giả định và lý do chưa thể thu hẹp khoảng.

Không trình bày ước lượng như số liệu chính xác. Cập nhật khi có dữ liệu mới và giữ lịch sử các lần đánh giá.

## 9. Bảo toàn bằng chứng và bảo vệ dữ liệu nhạy cảm

### 9.1. Bảo toàn bằng chứng

Khi điều tra incident, dữ liệu có thể bị ghi đè, cleanup hoặc hết hạn. Cần:

- Lưu artifact liên quan theo chính sách retention.
- Ghi hash hoặc checksum khi cần xác nhận tính toàn vẹn.
- Giữ timestamp, nguồn và người thu thập.
- Ghi truy vấn hoặc cách tạo báo cáo để có thể lặp lại.
- Giới hạn quyền sửa/xóa bằng chứng.
- Ghi rõ mọi biến đổi đã thực hiện trên bản sao dữ liệu.

Nếu cần snapshot hoặc export từ môi trường production, thực hiện theo quy trình được phép và chỉ lấy phạm vi tối thiểu cần thiết.

### 9.2. Giảm thiểu dữ liệu nhạy cảm

Không đưa vào ticket, chat hoặc file test:

- Mật khẩu, access token, private key hoặc session cookie.
- Số thẻ thanh toán đầy đủ hoặc thông tin xác thực tài chính.
- Dữ liệu cá nhân không cần thiết.
- Nội dung riêng tư của người dùng.
- Secret trong header hoặc URL.

Thay bằng ID giả, dữ liệu tổng hợp hoặc giá trị đã được làm sạch. Nếu cần tham chiếu bản ghi thật, dùng mã định danh nội bộ có quyền truy cập kiểm soát và lưu ở hệ thống được phê duyệt.

### 9.3. Giữ tính hữu ích khi làm sạch dữ liệu

Khi thay dữ liệu nhạy cảm, cần giữ những đặc điểm liên quan tới lỗi:

- Kiểu và độ dài dữ liệu.
- Quan hệ khóa ngoại.
- Thứ tự thời gian.
- Ký tự đặc biệt hoặc encoding gây lỗi.
- Phân phối và giá trị biên.
- Vai trò và quyền tương ứng.

Không làm sạch theo cách xóa mất điều kiện gây lỗi. Ví dụ, nếu lỗi chỉ xảy ra với tên có Unicode tổ hợp, dữ liệu thay thế cần giữ đặc tính Unicode đó nhưng không giữ tên thật.

### 9.4. Phân quyền và lưu trữ

- Chỉ cấp quyền cho người cần điều tra.
- Dùng kênh lưu trữ được phê duyệt.
- Mã hóa khi truyền và lưu theo yêu cầu của môi trường.
- Đặt thời hạn lưu và quy trình xóa.
- Không sao chép dữ liệu nhạy cảm sang máy cá nhân hoặc môi trường test không được phép.
- Ghi nhận việc truy cập/export nếu quy trình yêu cầu.

## 10. Từ dữ liệu sự cố đến regression test và đánh giá lại

### 10.1. Chuyển dữ liệu thành trường hợp kiểm thử

Sau khi hiểu nguyên nhân:

1. Chọn các trường dữ liệu tối thiểu cần cho lỗi.
2. Tạo dữ liệu tổng hợp hoặc đã làm sạch theo quy tắc được phép.
3. Xác định trạng thái ban đầu và chuỗi hành động.
4. Chọn oracle thể hiện hợp đồng hoặc bất biến bị vi phạm.
5. Chạy test trên phiên bản có lỗi nếu có thể.
6. Xác nhận test pass sau bản sửa.
7. Lưu liên kết defect, test, phiên bản và bằng chứng.

Không biến toàn bộ log production thành fixture. Chỉ đưa vào test những dữ liệu cần thiết, an toàn và có thể duy trì.

### 10.2. Kiểm tra phạm vi sau khi sửa

Sau khi fix, không chỉ chạy test tái hiện:

- Chạy test ở tầng chứa nguyên nhân.
- Kiểm tra các nhánh và trường hợp lân cận.
- Xác nhận dữ liệu bị ảnh hưởng đã được sửa hoặc đối soát nếu cần.
- Kiểm tra không còn giao dịch/job tồn đọng.
- Theo dõi metric và log sau triển khai.
- Xác nhận workaround hoặc biện pháp containment có thể được gỡ an toàn.

Một regression test pass chứng minh một trường hợp đã được xử lý; nó không tự chứng minh mọi dữ liệu bị ảnh hưởng trong incident đã được khôi phục.

## 11. Ví dụ tổng hợp: incident thanh toán bị xử lý lặp

### 11.1. Triệu chứng

Một số đơn hàng được ghi nhận thanh toán hai lần sau khi provider gửi callback lặp. Khách hàng báo có hai ledger entry cho cùng payment reference.

### 11.2. Dữ liệu cần thu thập để tái hiện

- Build ID của payment adapter và order service.
- Event type, payload đã làm sạch và provider reference giả.
- Idempotency key và trạng thái xử lý ban đầu.
- Timestamp nhận từng callback và thứ tự xử lý.
- Correlation ID của request, event ID và transaction ID.
- Log của consumer và trạng thái database trước/sau.
- Cấu hình retry, timeout và concurrency.

Trường hợp tái hiện có thể gửi cùng một callback hai lần, bao gồm một lần gần đồng thời, rồi kiểm tra ledger và trạng thái đơn.

### 11.3. Dữ liệu cần để đánh giá tác động

- Khoảng thời gian callback lặp bắt đầu và kết thúc.
- Số payment reference xuất hiện nhiều hơn một ledger entry.
- Số đơn và tài khoản liên quan.
- Tổng giá trị bị ghi nhận trùng.
- Phiên bản adapter/consumer đang triển khai.
- Các region hoặc queue partition bị ảnh hưởng.
- Giao dịch đã được hoàn/đối soát hay còn chờ xử lý.
- Những nguồn dữ liệu đã dùng để đếm và giới hạn của chúng.

Không thể suy ra số lượng giao dịch bị ảnh hưởng chỉ từ một callback mẫu. Cần truy vấn phạm vi giao dịch theo provider reference, idempotency key và cửa sổ thời gian.

### 11.4. Đánh giá và hành động

1. Xác định nguyên nhân: consumer không kiểm tra idempotency trước khi ghi ledger.
2. Đánh giá severity theo giá trị giao dịch, phạm vi tài khoản và nghĩa vụ tài chính.
3. Giảm thiểu: chặn xử lý lặp hoặc tạm dừng consumer theo quy trình an toàn.
4. Đối soát các ledger entry bị trùng và xử lý theo quy trình tài chính.
5. Thêm regression test cho callback lặp và callback đồng thời.
6. Xác minh số liệu sau fix và theo dõi metric callback duplicate.

## 12. Mẫu thu thập dữ liệu defect/incident

~~~text
ID / tiêu đề:
Loại: defect / incident / nghi vấn
Người báo cáo / owner:
Thời điểm phát hiện:
Thời điểm xảy ra hoặc khoảng ước lượng:
Trạng thái hiện tại:

Triệu chứng:
Kết quả mong đợi:
Kết quả thực tế:
Các bước hoặc sự kiện dẫn tới lỗi:

Phiên bản / build / commit:
Môi trường / region / tenant:
Feature flag / cấu hình:
Dependency và trạng thái:

Actor / role / scope:
Tài nguyên hoặc đối tượng liên quan:
Input / request / event đã làm sạch:
Trạng thái dữ liệu ban đầu:
Timezone / concurrency / thứ tự:

Log / trace / metric:
Correlation ID / request ID / event ID:
Artifact và vị trí lưu:

Phạm vi ảnh hưởng:
- Nhóm người dùng / tenant:
- Phiên bản / thành phần:
- Khoảng thời gian:
- Số request / giao dịch / bản ghi:
- Hậu quả chức năng / dữ liệu / tài chính / bảo mật:

Mức severity:
Priority:
Mức tin cậy và giới hạn dữ liệu:
Biện pháp giảm thiểu:
Hành động điều tra tiếp theo:
Regression test liên quan:
~~~

## 13. Checklist dữ liệu cần có để tái hiện và đánh giá tác động

- [ ] Báo cáo có ID, tiêu đề mô tả triệu chứng, thời điểm và owner.
- [ ] Phiên bản, build, commit và cấu hình liên quan được ghi lại.
- [ ] Môi trường, region, tenant và dependency được xác định.
- [ ] Actor, role, scope và trạng thái xác thực được mô tả an toàn.
- [ ] Input, request, event, trạng thái ban đầu và thứ tự thao tác được lưu.
- [ ] Timestamp có timezone và nguồn; độ lệch đồng hồ được ghi nếu liên quan.
- [ ] Log, trace, metric và bằng chứng client có correlation ID phù hợp.
- [ ] Kết quả mong đợi được phân biệt với kết quả thực tế.
- [ ] Trường hợp tái hiện tối thiểu vẫn giữ các điều kiện gây lỗi.
- [ ] Phạm vi ảnh hưởng được đánh giá theo người dùng, tenant, thành phần, phiên bản và thời gian.
- [ ] Số lượng có mẫu số, nguồn và giới hạn rõ ràng.
- [ ] Severity được phân biệt với priority.
- [ ] Kết luận nêu mức độ tin cậy và khoảng chưa biết.
- [ ] Bằng chứng được bảo toàn theo chính sách và có kiểm soát truy cập.
- [ ] Dữ liệu nhạy cảm được loại bỏ hoặc thay thế mà không làm mất đặc tính gây lỗi.
- [ ] Regression test và hành động khôi phục/đối soát được liên kết với defect hoặc incident.

Thu thập đúng dữ liệu giúp nhóm tái hiện lỗi mà không phụ thuộc vào trí nhớ hoặc mô tả mơ hồ, đồng thời đánh giá tác động bằng bằng chứng thay vì suy đoán. Khi trường hợp tái hiện, phạm vi ảnh hưởng, timeline và giới hạn dữ liệu được ghi tách bạch, nhóm có thể điều tra nhanh hơn, ưu tiên đúng mức và tạo regression test bảo vệ nguyên nhân đã xác định.
