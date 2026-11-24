# Recovery metrics collection — Thu thập số liệu cho luồng khôi phục tài khoản

## 1. Metrics cần giúp trả lời câu hỏi nào?

**Recovery metrics collection** là việc đo, tổng hợp và chuyển các số liệu về quá trình khôi phục tài khoản để hiểu tải, độ tin cậy, độ trễ và những dấu hiệu bất thường của hệ thống.

Trong một dịch vụ hỗ trợ người dùng mất mật khẩu, MFA, passkey hoặc thiết bị xác thực, những câu hỏi thường gặp là:

- Hệ thống đang nhận bao nhiêu yêu cầu và lưu lượng thay đổi ra sao?
- Bước kiểm tra bằng chứng có hoạt động ổn định không?
- Người dùng đang chờ ở hàng đợi nào?
- Bao lâu một thao tác kỹ thuật kết thúc, và bao lâu một giao dịch khôi phục được giải quyết?
- Thay đổi sau triển khai là do lỗi hệ thống, chính sách bảo mật hay cơ cấu lưu lượng?
- Hệ thống quan sát có đang mất dữ liệu khiến dashboard trông bình thường giả tạo không?

Metrics là tín hiệu tổng hợp. Chúng không tự chứng minh danh tính người yêu cầu, không thay thế audit của một giao dịch và không cấp quyền khôi phục.

| Nguồn quan sát | Phù hợp để trả lời | Giới hạn |
| --- | --- | --- |
| Metrics | Bao nhiêu, nhanh hay chậm, tăng hay giảm | Không giải thích đầy đủ lịch sử của một tài khoản |
| Trace | Một lần xử lý đi qua những thành phần nào | Có thể được lấy mẫu hoặc thiếu đoạn |
| Log vận hành | Chi tiết kỹ thuật của một lỗi hoặc hoạt động | Có chi phí và yêu cầu bảo vệ dữ liệu riêng |
| Audit | Sự kiện nhạy cảm nào đã xảy ra, do đâu, với kết quả nào | Không phải mọi truy vấn phân tích đều phù hợp trên kho audit |
| Dữ liệu trạng thái | Request hiện ở đâu, còn điều kiện nào | Không tự biểu diễn được toàn bộ lịch sử |

Thiết kế trong bài dùng tên metric và enum minh họa. Đây là hợp đồng đề xuất để giải thích cách thu thập, không phải schema mặc định của một thư viện hay nền tảng cụ thể.

## 2. Định nghĩa đơn vị đếm trước khi gắn instrumentation

Một HTTP request, một recovery request, một lần kiểm tra token và một lần thay MFA là các đơn vị khác nhau. Nếu dùng một counter chung mang tên “recovery attempts”, người vận hành rất khó biết nó thực sự đang đếm gì.

Ví dụ, cùng một người dùng có thể:

1. Gửi ba HTTP request do bấm lại hoặc client thử lại.
2. Chỉ tạo một recovery request nhờ cơ chế idempotency.
3. Thực hiện hai lần kiểm tra bằng chứng.
4. Nhận một quyết định cho phép thực hiện tác vụ.
5. Hoàn tất một lần đăng ký yếu tố mới.

Trong ví dụ đó, các số đếm đúng có thể lần lượt là 3, 1, 2, 1 và 1. Không có mâu thuẫn nếu từng metric được định nghĩa rõ.

Một bản mô tả metric cần ít nhất:

- Câu hỏi mà metric phục vụ.
- Đơn vị quan sát và loại instrument.
- Điểm bắt đầu hoặc điểm tăng.
- Ý nghĩa của từng kết quả.
- Tập nhãn được phép.
- Chủ thể chịu trách nhiệm phát metric.
- Cách xử lý retry, rollback, restart và dữ liệu đến muộn.

Không đếm giao dịch đã tạo chỉ vì endpoint trả HTTP 200 hoặc 202. Phản hồi công khai có thể cố ý giống nhau giữa nhiều nhánh để hạn chế dò tài khoản. Kết quả HTTP và kết quả nghiệp vụ nội bộ cần có số liệu riêng.

## 3. Danh mục số liệu theo các bước của luồng

Một bộ metric ban đầu có thể gồm:

| Metric minh họa | Loại | Đơn vị được đo |
| --- | --- | --- |
| recovery_http_requests_total | Counter | Mỗi HTTP request được endpoint xử lý |
| recovery_requests_created_total | Counter | Mỗi recovery request mới đã được lưu thành công |
| recovery_operations_total | Counter | Mỗi lần thực hiện một thao tác nội bộ có kết quả xác định |
| recovery_authorization_decisions_total | Counter | Mỗi quyết định cấp hoặc từ chối quyền tác vụ |
| recovery_actions_completed_total | Counter | Mỗi tác vụ được bảo vệ đã commit thành công |
| recovery_requests_closed_total | Counter | Mỗi request chuyển hợp lệ tới trạng thái kết thúc |
| recovery_operation_duration_seconds | Histogram | Thời gian xử lý một lần thao tác |
| recovery_request_resolution_duration_seconds | Histogram | Thời gian từ tạo request đến kết thúc request |
| recovery_pending_requests | Gauge | Số request đang chờ trong một phạm vi tại thời điểm quan sát |
| recovery_oldest_pending_age_seconds | Gauge | Tuổi của request đang chờ lâu nhất trong phạm vi |
| recovery_notification_delivery_attempts_total | Counter | Mỗi lần gọi chuyển phát, bao gồm lần thử lại |

Điểm đếm cần gắn với sự kiện thực tế:

- requests_created tăng khi tạo mới đã commit, không tăng khi trả lại cùng request cho một lần gọi idempotent.
- authorization_decisions phản ánh một quyết định cụ thể, không suy từ việc mở màn hình xác nhận.
- actions_completed tăng khi tác vụ thay mật khẩu, yếu tố hoặc trạng thái session tương ứng đã commit.
- requests_closed chỉ tăng cho một chuyển kết thúc hợp lệ, không tăng lại mỗi khi đọc thấy request đã đóng.
- delivery_attempts tăng cho từng lần gửi; nó không phải số thông báo duy nhất hoặc số người đã nhận.

Nếu một recovery request cho phép nhiều tác vụ, số actions_completed có thể khác số requests_closed. Hợp đồng cần nói rõ một tác vụ nào được coi là một đơn vị, thay vì ép hai số phải bằng nhau.

Với passkey, “hoàn tất khôi phục” phải gắn với hành vi cụ thể mà hệ thống thực hiện, chẳng hạn cho phép đăng ký credential mới sau xác minh. Không đặt metric ngụ ý đã lấy lại khóa riêng bị mất nếu hệ thống không thực hiện được điều đó.

## 4. Counter, gauge và histogram có vai trò khác nhau

**Counter** phù hợp với số lần sự kiện xảy ra. Giá trị thường tăng trong vòng đời tiến trình và có thể reset khi tiến trình khởi động lại. Muốn biết tốc độ, cần tính thay đổi theo thời gian với cơ chế hiểu reset; không dùng giá trị tích lũy hiện tại làm số yêu cầu trong phút vừa qua.

**Gauge** phù hợp với trạng thái tại một thời điểm: số công việc đang chờ, số tác vụ đang xử lý hoặc tuổi của công việc cũ nhất. Giá trị có thể tăng hoặc giảm.

**Histogram** phù hợp với phân bố: thời gian kiểm tra bằng chứng, thời gian gọi nhà cung cấp hoặc thời gian chờ giải quyết request. Trung bình riêng lẻ có thể che những giao dịch rất chậm.

[Prometheus — Instrumentation](https://prometheus.io/docs/practices/instrumentation/) phân biệt các loại instrument và lưu ý chi phí của mỗi tập nhãn. Với bài này, lựa chọn instrument bắt đầu từ ý nghĩa của đại lượng thay vì chọn theo tên hàm có sẵn.

Không dùng gauge tích lũy thủ công thay counter rồi tự reset theo phút. Cũng không dùng counter để biểu diễn số request đang chờ nếu chỉ tăng lúc tạo mà không có mô hình giảm hoặc đối soát.

Một gauge về số tác vụ đang thực thi trong tiến trình có thể được tăng khi bắt đầu và giảm trong khối finally. Nhưng nó chỉ mô tả tiến trình đó. Nó không thay thế gauge về số recovery request bền vững đang chờ trong cơ sở dữ liệu.

## 5. Phân loại kết quả theo ngữ nghĩa bảo mật

Một bằng chứng sai không nhất thiết là lỗi kỹ thuật. Một quyết định từ chối đúng chính sách có thể là hành vi bảo vệ mong muốn.

Với recovery_operations_total, có thể dùng tập result hữu hạn:

| result | Ý nghĩa minh họa |
| --- | --- |
| success | Thao tác được định nghĩa đã hoàn thành thành công |
| denied | Thao tác kết thúc bằng quyết định không cho phép |
| error | Thao tác không hoàn thành do lỗi kỹ thuật |
| timeout | Không có kết quả cuối trong thời hạn của lần xử lý |
| cancelled | Lần xử lý bị hủy theo hợp đồng đã định nghĩa |

Danh sách này không bắt buộc áp dụng nguyên vẹn cho mọi thao tác. Cần xác định result hợp lệ cho từng operation và không gán cùng một ý nghĩa cho hai mã khác nhau.

Ví dụ:

- Token sai hoặc hết hạn có thể là denied khi bộ kiểm tra đã đưa ra quyết định đó.
- Cơ sở dữ liệu không truy cập được là error.
- Nhà cung cấp chưa trả lời kịp là timeout; điều này không luôn chứng minh tác động bên ngoài chưa xảy ra.
- Một request không đủ bằng chứng bị từ chối là kết quả nghiệp vụ, không tự là service outage.

Các mã lý do, nếu cần đưa vào metric, phải được nhóm thành danh mục có giới hạn. Không dùng nguyên exception message hoặc nội dung đầu vào làm reason.

Không gọi mọi lần kiểm tra sai là “fraud”. Có thể đó là người dùng nhầm mã, mã đã được dùng hoặc một đợt tấn công. Metrics giúp nhận biết xu hướng; kết luận cần thêm ngữ cảnh và dữ liệu được truy cập đúng quyền.

## 6. Đặt điểm đo đúng ranh giới xử lý

Instrumentation nên có một chủ thể chịu trách nhiệm cho mỗi sự kiện. Nếu controller, service và consumer cùng tăng requests_created cho một giao dịch, dashboard sẽ đếm nhiều lần.

Có thể phân chia:

- HTTP middleware đo mỗi lần endpoint xử lý.
- Thành phần kiểm tra bằng chứng đo từng lần verifier thực sự chạy.
- Thành phần ra quyết định đo quyết định policy.
- Nguồn sự kiện sau commit hoặc bộ tổng hợp tương ứng đo tác vụ đã hoàn tất.
- Worker chuyển phát đo từng lần gọi nhà cung cấp.
- Job đọc trạng thái bền vững đo backlog theo phạm vi.

Mã giả đo một thao tác kỹ thuật:

~~~text
start = monotonicClock()
result = error

try:
    decision = executeOperation()
    result = mapToBoundedResult(decision)
    return decision
catch OperationTimeout:
    result = timeout
    throw
finally:
    increment operation counter once with operation and result
    observe elapsed monotonic duration with the same dimensions
~~~

Mã giả này chỉ mô tả số lần thực thi thao tác. Nó không chứng minh một thay đổi nghiệp vụ đã commit. Counter tác vụ hoàn tất phải có điểm ghi nhận riêng.

Cần tránh hai lỗi đối xứng:

1. Tăng metric thành công trước commit, rồi giao dịch rollback.
2. Chỉ đo nhánh thành công, khiến lỗi, timeout và hủy biến mất khỏi thống kê độ trễ.

Khi retry diễn ra, mỗi lần thực thi kỹ thuật có thể được đếm riêng. Nhưng số request mới hoặc số tác vụ nghiệp vụ duy nhất không được tự tăng theo mỗi retry. Nếu cần phân biệt, dùng một nhãn hữu hạn như attempt_kind với giá trị initial hoặc retry; không gắn số lần thử không giới hạn vào nhãn.

## 7. Metrics trong tiến trình và số liệu suy ra từ sự kiện

Counter trong bộ nhớ thường phục vụ quan sát vận hành với độ trễ thấp. Nó không phải sổ cái giao dịch.

Có thể xảy ra khoảng hở:

- Giao dịch commit nhưng tiến trình dừng trước khi tăng counter.
- Counter đã tăng nhưng chưa được thu thập thì tiến trình dừng.
- Consumer xử lý lại cùng sự kiện và tăng counter thêm lần nữa.
- Một đoạn dữ liệu bị thiếu khi exporter hoặc collector gặp lỗi.

Vì vậy cần phân biệt hai nguồn:

| Nguồn | Ưu điểm | Giới hạn cần công bố |
| --- | --- | --- |
| Instrumentation trực tiếp trong tiến trình | Nhanh, phản ánh lỗi và độ trễ kỹ thuật | Có thể mất quan sát khi crash hoặc mất thu thập |
| Tổng hợp từ sự kiện bền vững | Có thể đối soát, xử lý sự kiện đến muộn và loại trùng | Có độ trễ và cần trạng thái tổng hợp đáng tin |
| Đọc trạng thái hiện tại | Phù hợp với backlog và trạng thái còn tồn tại | Không tự tái dựng toàn bộ chuyển trạng thái trong quá khứ |

Nếu cần số liệu nghiệp vụ có thể đối soát, có thể xây một projection từ sự kiện đã commit. Bộ tổng hợp dùng event ID để nhận biết trùng, nhưng event ID chỉ là dữ liệu xử lý nội bộ, không phải label của time series.

Việc “tăng tổng rồi đánh dấu đã xử lý” vẫn có thể đếm trùng nếu tiến trình dừng giữa hai bước. Trạng thái nhận biết sự kiện và thay đổi tổng cần có cơ chế nhất quán phù hợp. Sau đó mới xuất các giá trị tổng hợp theo hợp đồng metric.

Không cộng số đếm trực tiếp và số đếm projection vào nhau nếu chúng đang mô tả cùng một tập sự kiện. Nếu giữ cả hai để đối soát, đặt tên hoặc nguồn rõ ràng và giải thích độ trễ khác nhau.

Metrics có thể được suy ra từ audit hoặc sự kiện nghiệp vụ, nhưng sự tồn tại của một điểm metric không thay thế việc kiểm tra lịch sử audit khi điều tra một request cụ thể.

## 8. Labels phải có tập giá trị hữu hạn

Mỗi tổ hợp label tạo thêm time series. Nếu dùng account ID, request ID hoặc email làm nhãn, số series có thể tăng theo số người dùng, đồng thời biến hệ thống metrics thành nơi chứa dữ liệu định danh.

Những nhãn có thể cân nhắc khi có ngân sách rõ:

| Nhãn | Ví dụ tập giá trị hữu hạn |
| --- | --- |
| operation | initiate, challenge_verify, authorize, execute |
| purpose | password_reset, mfa_replace, passkey_rebind |
| result | success, denied, error, timeout |
| channel | email, sms, push |
| method_family | recovery_code, enrolled_factor, manual_review |
| queue | notification, review, audit_forwarding |

Không cần gắn tất cả nhãn vào mọi metric. Chỉ giữ những chiều phân tích thực sự dùng.

Không đưa vào labels:

- Account ID, recovery request ID, event ID hoặc session ID.
- Email, số điện thoại, token, OTP hoặc mã dự phòng.
- IP, user agent đầy đủ, URL có query string.
- Trace ID hoặc một timestamp mới cho mỗi quan sát.
- Exception message và lý do tự do do client cung cấp.

[Prometheus — Metric and label naming](https://prometheus.io/docs/practices/naming/) khuyến nghị tránh những chiều có số giá trị rất lớn hoặc không giới hạn, gồm user ID và email.

Hash email hoặc request ID không làm giảm số giá trị. Nó cũng không tự loại bỏ khả năng nhận dạng hoặc đối chiếu dữ liệu.

Một phép tính ngân sách minh họa: nếu một metric có 5 operation, 4 result và 3 purpose thì có thể tạo tới 60 tổ hợp trên mỗi tập resource. Nếu nhân thêm 20 instance và nhiều bucket histogram, số series tăng tiếp. Đây là giới hạn lý thuyết để lập ngân sách, không có nghĩa mọi tổ hợp đều thực sự tồn tại hoặc hợp lệ.

Tenant ID cũng cần được cân nhắc như một chiều có thể tăng mạnh. Nếu cần phân tích sâu từng tenant, có thể dùng hệ thống phân tích có quyền truy cập và mô hình chi phí phù hợp thay vì mặc định gắn mọi tenant vào mọi metric.

## 9. Thu thập và bảo vệ đường đi telemetry

Một kiến trúc có thể gồm:

~~~mermaid
flowchart LR
    A[Recovery Service và workers] --> B[Metrics SDK hoặc endpoint metrics]
    B --> C[Collector hoặc hệ thống scrape]
    C --> D[Kho time series]
    D --> E[Dashboard và cảnh báo]
    F[Sự kiện đã commit] --> G[Bộ tổng hợp có nhận biết trùng]
    G --> C
    H[Trạng thái request và hàng đợi] --> I[Job đo backlog theo phạm vi]
    I --> C
~~~

Sơ đồ là các lựa chọn nguồn bổ sung. Không bắt buộc thu cùng một metric qua mọi đường, vì điều đó có thể tạo writer trùng.

Cần xác định:

- Metric được push hay scrape, tại ranh giới nào.
- Resource nào phân biệt instance, môi trường và phiên bản triển khai.
- Độ trễ, kích thước buffer và giới hạn tài nguyên chấp nhận được.
- Ai có quyền đọc endpoint, collector và dashboard.
- Cách bảo vệ thông tin khi truyền và cấu hình kết nối.
- Cách xử lý khi backend không khả dụng.

Instrumentation không nên gọi đồng bộ một backend chậm trong lúc đang giữ khóa request hoặc tài khoản. Đường đi metrics cần có giới hạn tài nguyên để không làm hỏng luồng khôi phục khi hệ thống quan sát gặp sự cố.

Metrics riêng tư vẫn có thể tiết lộ hoạt động: một nhóm rất ít người dùng, một nhánh xem xét nhạy cảm hoặc thời điểm thay đổi yếu tố. Dashboard và API truy vấn cần quyền truy cập phù hợp; số liệu tổng hợp không mặc nhiên là dữ liệu công khai.

Nếu dùng exemplar để liên kết quan sát tới trace, áp dụng chính sách bảo vệ riêng. Không biến exemplar thành cách đưa token hoặc dữ liệu định danh vào metric, và không thêm trace ID thành label thường xuyên.

## 10. Temporality, restart và nhiều instance

Một giá trị tổng hợp chỉ có ý nghĩa khi biết khoảng thời gian nó bao phủ.

- Cumulative biểu diễn tổng kể từ một thời điểm bắt đầu của stream.
- Delta biểu diễn thay đổi trong một khoảng thời gian.

[OpenTelemetry — Metrics Data Model](https://opentelemetry.io/docs/specs/otel/metrics/data-model/) mô tả các kiểu temporality, thời điểm bắt đầu stream và nguyên tắc một writer cho mỗi stream. Đây là cơ sở để hiểu đúng reset, các khoảng thu thập và việc chuyển đổi ở collector.

Không coi một tổng delta là giá trị cumulative rồi áp dụng công thức rate như thể nó tăng liên tục. Nếu có bước chuyển đổi, cần cấu hình và định tuyến giữ được trạng thái của stream theo hợp đồng.

Mỗi instance phải được phân biệt ở lớp resource trước khi tổng hợp. Nếu hai writer ghi cùng một stream mà không phân biệt nguồn, dữ liệu có thể chồng lấn. Ngược lại, khi truy vấn toàn dịch vụ cần tổng hợp các instance đúng cách.

Đối với gauge đọc trạng thái dùng chung, phải biết có bao nhiêu nguồn đang xuất cùng một giá trị:

- Mỗi worker báo số công việc cục bộ không trùng nhau: có thể cộng theo phạm vi phù hợp.
- Mười instance cùng đọc tổng backlog của một queue dùng chung: cộng cả mười sẽ nhân sai backlog lên mười lần.
- Nhiều queue partition rời nhau: có thể cộng snapshot khi phạm vi và thời điểm được định nghĩa phù hợp.

Một lựa chọn là chỉ có một publisher cho một snapshot dùng chung. Nếu có chuyển quyền publisher, cần bảo đảm bên tiêu thụ không vô tình cộng cả giá trị cũ và mới.

Dữ liệu thiếu không được tự hiểu là số không. Counter về một kết quả hiếm gặp có thể cần được khởi tạo khi hợp lý; nhưng một target không được scrape hoặc exporter ngừng hoạt động cần được nhận diện bằng tín hiệu sức khỏe riêng.

## 11. Đo độ trễ kỹ thuật và thời gian giải quyết request

Hai đại lượng này có bản chất khác nhau:

| Đại lượng | Điểm bắt đầu và kết thúc | Điều cần lưu ý |
| --- | --- | --- |
| Độ trễ thao tác | Bắt đầu và kết thúc một lần xử lý trong tiến trình | Dùng đồng hồ monotonic cho elapsed time |
| Độ trễ phụ thuộc | Trước và sau một lần gọi dịch vụ ngoài | Ghi rõ timeout và retry |
| Thời gian chờ queue | Khi đủ điều kiện vào queue đến khi được nhận xử lý | Cần timestamp và ngữ nghĩa đồng nhất |
| Thời gian giải quyết request | Tạo request đến chuyển kết thúc hợp lệ | Có thể bao gồm chờ người dùng hoặc xem xét thủ công |

Đối với phép đo qua nhiều tiến trình, timestamp cần nguồn và giả định đồng bộ đồng hồ rõ ràng. Giá trị âm hoặc bất thường cần được nhận diện, không âm thầm biến thành số không để dashboard đẹp hơn.

Bucket của histogram phải phù hợp với đại lượng. Một cấu hình mili giây tới vài giây có thể phù hợp với thao tác kỹ thuật, nhưng không đủ để mô tả request chờ xem xét hàng giờ. Dùng đơn vị nhất quán, chẳng hạn seconds, và thiết kế biên bucket theo câu hỏi cần trả lời.

Histogram thời gian giải quyết chỉ chứa request đã kết thúc sẽ bỏ qua những request còn đang chờ. Nếu số request mắc kẹt tăng, độ trễ của phần đã kết thúc vẫn có thể trông tốt. Cần xem thêm:

- Số lượng đang chờ theo trạng thái có giới hạn.
- Tuổi của request chờ lâu nhất.
- Phân bố tuổi backlog nếu có nguồn đo phù hợp.
- Số request kết thúc theo outcome.
- Độ mới của snapshot backlog.

Tuổi request chờ lâu nhất có thể tăng cả khi hệ thống vẫn xử lý công việc khác. Không diễn giải nó như độ trễ trung bình, và không dùng nó thay toàn bộ phân bố.

## 12. Truy vấn minh họa và giới hạn diễn giải

Các ví dụ dưới dùng tên xuất theo kiểu Prometheus và giả định đã lọc đúng job, môi trường cùng phạm vi triển khai. Chúng không phải lệnh cần chạy để viết bài này.

### 12.1. Tốc độ HTTP request vào endpoint khởi tạo

~~~promql
sum(
  rate(recovery_http_requests_total{
    job="account-recovery",
    route="initiate"
  }[5m])
)
~~~

Metric này đếm HTTP request, bao gồm những lần gọi không tạo recovery request mới. Nó không phải số tài khoản duy nhất đang mất quyền truy cập.

### 12.2. Tỷ trọng lỗi kỹ thuật của thao tác kiểm tra challenge

~~~promql
sum(
  rate(recovery_operations_total{
    job="account-recovery",
    operation="challenge_verify",
    result=~"error|timeout"
  }[5m])
)
/
sum(
  rate(recovery_operations_total{
    job="account-recovery",
    operation="challenge_verify"
  }[5m])
)
~~~

Mẫu số gồm những lần thực thi đã được ghi nhận theo hợp đồng, kể cả từ chối hợp lệ. Đây là tỷ trọng lỗi kỹ thuật trong các lần kiểm tra, không phải xác suất tài khoản bị chiếm đoạt.

Khi mẫu số bằng không hoặc dữ liệu không đủ, cần hiển thị trạng thái không đủ quan sát. Không ép thành 0% rồi kết luận hệ thống khỏe. Với lưu lượng thấp, cần nhìn thêm số quan sát để đánh giá mức ý nghĩa.

### 12.3. P95 độ trễ thao tác từ classic histogram

~~~promql
histogram_quantile(
  0.95,
  sum by (le, operation) (
    rate(recovery_operation_duration_seconds_bucket{
      job="account-recovery"
    }[5m])
  )
)
~~~

Ví dụ yêu cầu các instance dùng biên bucket tương thích cho metric được tổng hợp. Kết quả là một ước lượng theo bucket và dữ liệu trong cửa sổ, không phải giới hạn chắc chắn cho mọi request.

[Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/) giải thích việc tổng hợp histogram rồi tính quantile. Không lấy trung bình P95 của từng instance để gọi đó là P95 toàn dịch vụ.

Khi thay đổi cách chia bucket hoặc loại histogram, cần kế hoạch chuyển đổi và truy vấn tương ứng. Không trộn dữ liệu không tương thích rồi coi biểu đồ sau triển khai là liên tục về ngữ nghĩa.

## 13. Tỷ lệ hoàn tất phải có quần thể và cửa sổ rõ

Công thức “số hoàn tất trong giờ chia số tạo mới trong giờ” thường không phải tỷ lệ hoàn tất của nhóm request được tạo trong giờ đó.

Ví dụ, một giờ có 100 request mới. Cùng giờ, 120 request hoàn tất, gồm 70 request mới và 50 request tạo từ trước. Phép chia cho kết quả 120%, nhưng không có nghĩa hệ thống có tỷ lệ hoàn tất trên 100%; tử và mẫu đang thuộc hai quần thể khác nhau.

Có thể phân biệt:

1. **Tỷ trọng outcome trong các request đã đóng:** số đóng với outcome completed chia tổng request đóng trong cùng phạm vi. Nó mô tả cơ cấu kết quả được giải quyết trong cửa sổ.
2. **Tỷ lệ hoàn tất của một nhóm khởi tạo:** chọn các request được tạo trong cùng khoảng thời gian, rồi theo dõi kết quả của chính nhóm đó sau một khoảng quan sát phù hợp.
3. **Thông lượng hoàn tất:** số request hoặc tác vụ hoàn tất trên một đơn vị thời gian.

Phân tích theo nhóm khởi tạo thường cần dữ liệu sự kiện hoặc trạng thái có khả năng nối theo request trong hệ thống phân tích được bảo vệ. Không cần đưa request ID vào labels để làm việc đó.

Những request vẫn đang chờ ở cuối khoảng quan sát phải được biểu diễn đúng. Không loại chúng khỏi mẫu số rồi gọi kết quả còn lại là tỷ lệ hoàn tất của tất cả người dùng.

Tỷ lệ từ chối tăng có thể do tấn công, thay policy, lỗi sử dụng hoặc thay đổi cơ cấu luồng. Không tối ưu chỉ để “success rate” tăng bằng cách bỏ kiểm soát bằng chứng hoặc giảm điều kiện xác minh.

## 14. Quan sát chính đường thu thập metrics

Một dashboard yên lặng có thể là hệ thống không có hoạt động hoặc hệ thống đã ngừng phát số liệu. Cần nhìn được sức khỏe đường telemetry.

Những tín hiệu có thể theo dõi:

- Target có được scrape hoặc exporter có đang gửi thành công không.
- Độ trễ xuất metric và tuổi của snapshot cuối.
- Buffer hoặc queue telemetry có tồn đọng không.
- Có quan sát bị bỏ do giới hạn tài nguyên hoặc số tổ hợp nhãn không.
- Collector có đang từ chối dữ liệu hoặc gặp lỗi định dạng không.
- Bộ tổng hợp từ sự kiện đã xử lý tới đâu và còn backlog bao nhiêu.
- Một metric có đột ngột tăng số series sau thay đổi cấu hình không.

Độ trễ đường metrics cần được phân biệt với độ trễ phục hồi tài khoản. Một biểu đồ giảm thông lượng có thể do dữ liệu chưa tới, không phải do luồng nghiệp vụ ngừng hoàn toàn.

Việc lấy mẫu trace không nên vô tình trở thành cơ chế chọn những lần được tăng counter nếu mục tiêu là đếm mọi lần thực thi. Nếu metric được suy từ trace đã lấy mẫu, phải nêu rõ đó là ước lượng và hiểu cơ chế lấy mẫu trước khi so sánh với số liệu đầy đủ.

Quy trình điều tra có thể liên kết metric tổng hợp với log, trace và audit theo quyền phù hợp. Metrics chỉ cung cấp tín hiệu để khoanh vùng; không tự là lý do đủ để thu hồi mọi session hoặc khóa một nhóm tài khoản.

## 15. Tình huống vận dụng

Sau một lần triển khai, số recovery request mới gần như không đổi, nhưng P95 của challenge_verify tăng. Đồng thời, timeout tăng, hàng đợi thông báo già hơn và tỷ trọng request còn chờ tăng.

Cách đọc dữ liệu cần giữ từng ý nghĩa:

1. So sánh lỗi kỹ thuật với denied để phân biệt phụ thuộc bị chậm và quyết định bảo mật hợp lệ.
2. Xem độ trễ của từng thao tác để xác định phần tăng nằm ở kiểm tra bằng chứng, chuyển phát hay bước khác.
3. Kiểm tra sức khỏe collector và độ mới snapshot trước khi tin rằng backlog hoặc thông lượng thay đổi.
4. Đọc số lần chuyển phát riêng với số thông báo duy nhất, vì retry có thể làm attempts tăng.
5. Xem request đang chờ cùng thời gian giải quyết của request đã kết thúc để tránh bỏ qua phần mắc kẹt.
6. Dùng dữ liệu có quyền truy cập phù hợp để điều tra giao dịch cụ thể, thay vì thêm email hoặc request ID vào label.
7. Đối soát số liệu nghiệp vụ từ sự kiện bền vững nếu counter trong tiến trình có thể bị mất qua restart.

Mỗi metric cần giữ rõ **đang đếm đối tượng nào, tại điểm nào, với tập nhãn nào và trong phạm vi thời gian nào**. Chỉ khi các định nghĩa đó nhất quán, số liệu thu thập mới giúp đánh giá luồng khôi phục mà không làm lộ bí mật hoặc tạo kết luận sai về hiệu quả kiểm soát bảo mật.
