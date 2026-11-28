# Chính sách logging trong Security Assurance

## 1. Vì sao tổ chức cần chính sách logging?

Giả sử một hệ thống hóa đơn SaaS đã triển khai xác thực, kiểm tra quyền theo tenant, mã hóa và cảnh báo bảo mật. Một ngày, khách hàng báo rằng tài khoản của họ có thể đã tải hóa đơn của doanh nghiệp khác. Đội vận hành mở dashboard và thấy API vẫn chạy bình thường, nhưng log lại thiếu người thực hiện thao tác xuất, thiếu tenant liên quan, không lưu kết quả kiểm tra quyền và chỉ giữ dữ liệu trong hai ngày. Tổ chức khó trả lời **đã xảy ra điều gì, ảnh hưởng tới ai và control nào đã không hoạt động**.

Ngược lại, ghi toàn bộ HTTP request và response để “không bỏ sót bằng chứng” cũng có thể tạo ra rủi ro mới: access token, mật khẩu, thông tin khách hàng và dữ liệu thanh toán bị sao chép hàng loạt vào hệ thống log mà nhiều người có thể truy cập.

**Chính sách logging (logging policy)** là bộ quy tắc được phê duyệt xác định **sự kiện nào phải được ghi, trường thông tin nào được phép ghi, ai chịu trách nhiệm, cách thu thập/bảo vệ/lưu giữ/truy xuất log và cách chứng minh các quy tắc đang hoạt động**. Chính sách phải cân bằng ba nhu cầu:

1. **Khả năng quan sát và điều tra:** có đủ dấu vết để phát hiện hành vi bất thường, tái dựng chuỗi sự kiện và hỗ trợ ứng cứu sự cố.
2. **An toàn và quyền riêng tư:** log không trở thành kho dữ liệu nhạy cảm dễ bị lộ, sửa hoặc sử dụng sai mục đích.
3. **Bằng chứng assurance:** có cơ sở kiểm chứng rằng security controls và các quy trình liên quan được thiết kế và vận hành theo yêu cầu.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là đánh giá có bằng chứng việc đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và controls tới kiểm thử, audit, khắc phục phát hiện và assurance liên tục. Logging policy kết nối các hoạt động đó: log vừa là **một biện pháp kiểm soát hỗ trợ phát hiện và truy vết**, vừa là **một nguồn bằng chứng** để xem xét hiệu quả các controls khác.

> **Có log không đồng nghĩa có bằng chứng đủ tin cậy.** Phải biết log bao phủ sự kiện nào, nguồn danh tính có đáng tin không, thời gian có chính xác không, bản ghi có thể bị sửa/xóa không, có mất sự kiện khi hệ thống lỗi không và người kiểm tra có thể truy xuất đúng phạm vi không.

## 2. Các khái niệm và mục tiêu cần phân biệt

| Thuật ngữ | Ý nghĩa | Điều dễ nhầm |
| --- | --- | --- |
| **Application log** | Bản ghi sự kiện của ứng dụng, trạng thái xử lý và lỗi. | Một stack trace kỹ thuật chưa chắc cho biết ai đã thực hiện hành động bảo mật. |
| **Security event log** | Bản ghi sự kiện có ý nghĩa phát hiện, điều tra hoặc đánh giá bảo mật. | Không phải mọi log có mức ERROR đều là security event; nhiều sự kiện bảo mật hợp lệ có mức INFO. |
| **Audit trail / audit log** | Chuỗi dấu vết về hành động quan trọng, người/đối tượng, thời điểm, tài nguyên, kết quả và khả năng liên kết. | Log không tự động bảo đảm tính không thể chối bỏ (*non-repudiation*) về pháp lý. |
| **Access log** | Bản ghi yêu cầu truy cập dịch vụ/tài nguyên hoặc truy cập tới chính hệ thống log. | Một HTTP 200 chưa chứng minh giao dịch nghiệp vụ hoàn tất hay quyền truy cập hợp lệ. |
| **Telemetry / observability** | Logs, metrics, traces và các tín hiệu dùng để hiểu hành vi hệ thống. | Distributed trace có thể hỗ trợ điều tra nhưng không thay cho audit event nghiệp vụ được thiết kế đúng. |
| **SIEM / log analytics** | Nơi tập trung, tương quan, tìm kiếm và phân tích dữ liệu sự kiện. | Mua SIEM chưa bảo đảm mọi nguồn quan trọng đã được tích hợp và gửi log đầy đủ. |
| **Detection rule / alert** | Điều kiện phát hiện hoạt động đáng ngờ và thông báo cho người xử lý. | Có cảnh báo không đồng nghĩa cảnh báo đã tới đúng người và được phản ứng đúng hạn. |

Logging hỗ trợ nhiều mục tiêu bảo mật:

- **Confidentiality:** phát hiện và truy vết các thao tác đọc/xuất dữ liệu nhạy cảm không phù hợp.
- **Integrity:** ghi nhận thay đổi quan trọng, ai thay đổi, giá trị tham chiếu và kết quả kiểm tra, giúp đối chiếu sai lệch.
- **Availability:** theo dõi thất bại, gián đoạn và hành vi lạm dụng tài nguyên; hỗ trợ điều tra nguyên nhân.
- **Accountability:** biết chủ thể, thao tác và kết quả trong phạm vi có thể chứng minh.
- **Incident response và audit:** tạo hiện vật hỗ trợ xác minh timeline, phạm vi sự cố và hiệu quả khắc phục.

Không có hệ thống logging nào tự chứng minh rằng **không hề có tấn công**. Việc không thấy dấu vết có thể do không xảy ra sự kiện, nhưng cũng có thể do thiếu coverage, lỗi pipeline, thời gian lưu giữ ngắn hoặc mất log.

## 3. Phân biệt policy, standard, procedure và hướng dẫn triển khai

Chính sách nên đặt yêu cầu ở cấp quản trị, không cố viết mọi câu lệnh cấu hình của từng công cụ.

| Tầng tài liệu | Trả lời câu hỏi | Ví dụ về logging |
| --- | --- | --- |
| **Policy – Chính sách** | Tổ chức **phải bảo đảm điều gì**, ai có trách nhiệm và ai được phê duyệt ngoại lệ? | Các hành động đặc quyền, truy cập dữ liệu nhạy cảm và thay đổi security controls phải có audit trail thích hợp. |
| **Standard – Tiêu chuẩn nội bộ** | Yêu cầu tối thiểu và cấu trúc thống nhất là gì? | Trường event, chuẩn timestamp, định danh nguồn, thời hạn giữ theo nhóm dữ liệu, yêu cầu bảo vệ. |
| **Procedure / runbook** | Nhân sự phải làm gì và theo thứ tự nào? | Cách tiếp nhận cảnh báo log pipeline lỗi, truy xuất log phục vụ điều tra, xác minh khôi phục luồng log. |
| **Implementation guide** | Cách hiện thực bằng công nghệ cụ thể? | Cấu hình Spring Boot, API Gateway, Kubernetes audit, cloud audit trail, log forwarding. |
| **Evidence / test plan** | Làm sao biết quy định được thực thi? | Test tạo security event, báo cáo coverage, kết quả kiểm tra RBAC, thử lỗi collector và báo cáo phát hiện. |

Mỗi tầng cần có owner và quản lý phiên bản. Chính sách quá chung (“mọi hệ thống phải ghi log đầy đủ”) khó kiểm chứng; chính sách quá phụ thuộc tên sản phẩm sẽ khó duy trì khi kiến trúc thay đổi.

### Trách nhiệm bắt đầu từ hệ thống và dữ liệu

Người ra chính sách không thể tự biết mọi sự kiện nghiệp vụ quan trọng. **Business/data owner** xác định hành động nào có hậu quả đáng kể; **security và risk owner** xác định các kịch bản cần phát hiện/điều tra; **service/control owner** biến chúng thành yêu cầu và cấu hình; **operator** vận hành pipeline; **assessor** kiểm tra bằng chứng.

## 4. Xác định phạm vi chính sách và nguồn log

Trước khi yêu cầu một event mới, tổ chức phải biết **những nguồn nào thuộc phạm vi và hệ thống nào đang nhận log từ chúng**:

- Ứng dụng giao diện, API và các tác vụ nền xử lý giao dịch nghiệp vụ.
- Identity Provider, hệ thống IAM, quyền quản trị, cấp/thu hồi truy cập.
- Hệ điều hành, container, orchestrator, API Gateway, WAF, DNS và hạ tầng mạng liên quan.
- Database, object storage, message broker, secret manager, key management và các thành phần bảo vệ dữ liệu.
- Hệ thống CI/CD, kho mã, artifact registry, cấu hình, triển khai và thay đổi infrastructure.
- Nền tảng SaaS, cloud provider và dịch vụ của bên thứ ba mà tổ chức dựa vào để thực hiện control.
- **Chính nền tảng logging:** collector, parser, pipeline, chỉ mục lưu trữ, quy tắc cảnh báo, tài khoản truy cập log và hành vi thay đổi cấu hình.

Một **log source inventory** nên ghi: nguồn, owner, dữ liệu/sự kiện quan trọng, môi trường, nơi chuyển đến, mức nhạy cảm, nhóm retention, công cụ giám sát sức khỏe, luồng đối chiếu và trạng thái coverage.

### Kiểm soát điểm mù phạm vi

Giả sử các ứng dụng chính gửi log tới SIEM, nhưng một tác vụ export viết trực tiếp vào object storage không phát sự kiện audit. “100% ứng dụng kết nối SIEM” có thể đúng trên một inventory chưa đầy đủ nhưng **không chứng minh bao phủ 100% các hành động nhạy cảm**. Cần đối chiếu inventory hệ thống, đường dữ liệu và security requirements.

Các môi trường **development, staging, production** có thể dùng yêu cầu chi tiết khác nhau, nhưng mỗi môi trường phải quản lý dữ liệu thử nghiệm và thông tin xác thực phù hợp. Không loại staging khỏi mọi yêu cầu chỉ vì không phải production, đặc biệt khi môi trường đó có quyền truy cập dữ liệu thật hoặc tài sản dùng chung.

## 5. Những sự kiện bảo mật nào phải ghi?

Chính sách nên định nghĩa **nhóm sự kiện tối thiểu theo rủi ro và khả năng kiểm chứng**, sau đó chuẩn hóa event catalog cho từng dịch vụ. Bảng dưới đây là điểm bắt đầu:

| Nhóm sự kiện | Ví dụ nên đánh giá để ghi | Mục tiêu assurance |
| --- | --- | --- |
| **Xác thực (authentication)** | Đăng nhập thành công/thất bại, MFA, token hoặc phiên bị từ chối, khóa/mở khóa tài khoản, thay đổi yếu tố xác thực. | Phát hiện lạm dụng danh tính, kiểm chứng chính sách xác thực. |
| **Phân quyền (authorization)** | Từ chối truy cập đối tượng nhạy cảm, thay đổi vai trò, cấp/thu hồi đặc quyền, vi phạm tenant boundary. | Kiểm chứng thực thi quyền tối thiểu và phát hiện hành vi vượt quyền. |
| **Truy cập dữ liệu nhạy cảm** | Tải/xuất dữ liệu hàng loạt, truy cập chức năng nhạy cảm, truy xuất bất thường theo chính sách. | Xác định ai, khi nào, phạm vi nào được phép đọc/xuất. |
| **Hành động đặc quyền** | Đăng nhập quản trị, thay đổi IAM, tạo khóa, đổi chính sách firewall, cấu hình storage, thao tác break-glass. | Giải trình và phát hiện thay đổi controls quan trọng. |
| **Thay đổi dữ liệu/nghiệp vụ trọng yếu** | Sửa số tiền, trạng thái thanh toán, hủy giao dịch, chuyển quyền sở hữu đối tượng, thay đổi thông tin nhận tiền. | Điều tra tính toàn vẹn và đối soát giao dịch. |
| **Thay đổi cấu hình/triển khai** | Release, rollback, thay bí mật/cert, tắt security scanner, chỉnh sửa logging policy hoặc retention. | Liên hệ thay đổi với rủi ro và bằng chứng vận hành. |
| **Tín hiệu tấn công và kiểm soát** | Quy tắc WAF kích hoạt, giới hạn tốc độ, hành vi bất thường, malware alert, integrity check lỗi. | Hỗ trợ phát hiện và phản ứng với threat scenario. |
| **Sự cố sẵn sàng và phụ thuộc** | Mất kết nối dependency, job quan trọng thất bại, queue backlog, restore/failover, quá tải. | Hỗ trợ điều tra gián đoạn và kiểm chứng phục hồi. |
| **Tình trạng logging** | Agent ngừng gửi, queue đầy, lỗi parser, mất đồng bộ thời gian, backlog, sửa/xóa log, lỗi quyền truy xuất. | Phát hiện **mất khả năng quan sát** và bảo vệ evidence. |

### Ghi cả kết quả thành công và thất bại có chọn lọc

Chỉ ghi lỗi sẽ không thấy **ai đã đọc dữ liệu thành công**. Chỉ ghi thành công sẽ bỏ qua các lần thử quyền trái phép. Chính sách cần xác định cho từng sự kiện: có ghi success, denial, exception hay nhiều trạng thái; trường nào cần cho điều tra; mức khối lượng chấp nhận và kiểm soát bảo mật liên quan.

Không nhất thiết phải log mọi lần đọc dữ liệu không nhạy cảm với cùng độ chi tiết. Một khối lượng log quá lớn có thể tăng chi phí, giảm tín hiệu và gây sự cố sẵn sàng. Lựa chọn phải dựa trên **kịch bản rủi ro, mục đích kiểm tra và yêu cầu bắt buộc**, không dựa trên khẩu hiệu “càng nhiều càng tốt”.

### Điều gì không đủ để đánh giá?

- Một dòng “authentication failed” **không có nguồn, thời gian hoặc lý do đã chuẩn hóa** có thể khó điều tra.
- Một dòng “Invoice exported” **không có actor, tenant và job ID** không đủ truy vết một file xuất.
- Một stack trace với dữ liệu request đầy đủ vừa có thể **lộ bí mật** vừa không cho thấy quyết định phân quyền.
- Một dashboard đếm HTTP 403 không tự biết các request bị từ chối do **kiểm soát quyền đúng** hay do hệ thống cấu hình lỗi.

## 6. Chuẩn hóa schema cho security event

Để liên kết event qua nhiều dịch vụ, chính sách/standard nên đưa ra **trường tối thiểu và ý nghĩa thống nhất**. Không có một schema duy nhất phù hợp mọi tổ chức; có thể ánh xạ sang các định dạng công nghiệp khi cần, nhưng vẫn phải có field contract rõ ràng.

| Trường | Cần trả lời gì? | Gợi ý |
| --- | --- | --- |
| **event_id / event_type** | Đây là loại sự kiện nào? | Tên máy đọc được ổn định, ví dụ AUTHZ_DENIED, INVOICE_EXPORT_REQUESTED. |
| **occurred_at** | Sự kiện thực sự diễn ra lúc nào? | Thời gian chuẩn UTC, định dạng thống nhất; phân biệt với lúc nhận log. |
| **observed_at / ingested_at** | Hệ thống logging nhận thấy sự kiện lúc nào? | Giúp đo trễ pipeline và phát hiện mất kết nối. |
| **source_service / component** | Sự kiện phát sinh ở hệ thống, phiên bản, môi trường nào? | Service ID, environment, release và source instance khi phù hợp. |
| **actor / principal** | Ai hoặc service nào thực hiện? | ID ổn định từ nguồn danh tính tin cậy; không dựa vào header tùy ý. |
| **action** | Thao tác được yêu cầu/thực hiện là gì? | READ_INVOICE, EXPORT_REQUEST, ROLE_GRANTED. |
| **resource_type / resource_id** | Tài nguyên nào bị tác động? | Định danh nội bộ tối thiểu; tránh đưa dữ liệu nhạy cảm vào tên tài nguyên. |
| **tenant / scope** | Thuộc không gian quyền hoặc khách hàng nào? | ID tenant đáng tin, nếu cần và được phép ghi. |
| **outcome** | Thành công, bị từ chối hay lỗi? | SUCCESS, DENIED, FAILED, PENDING theo quy ước được duyệt. |
| **reason_code** | Tại sao xảy ra kết quả đó? | AUTHZ_SCOPE_MISMATCH, TOKEN_EXPIRED, LIMIT_EXCEEDED. |
| **request_id / trace_id / job_id** | Làm sao liên kết các bước trong chuỗi xử lý? | Định danh tương quan không chứa token/PII, lan truyền có kiểm soát. |
| **schema_version** | Cấu trúc của event đang dùng phiên bản nào? | Hỗ trợ thay đổi và tương thích parser/detection. |

Trường **actor** là “người hoặc danh tính dịch vụ đã được hệ thống xác minh”, khác với giá trị username do client tự nhập. Nếu xác thực thất bại, chỉ có thể ghi một **claimed identity** đã kiểm soát độ nhạy và tách biệt khỏi authenticated principal; không đánh đồng chúng.

### Ví dụ một event export đã được chấp thuận

~~~json
{
  "event_type": "INVOICE_EXPORT_REQUESTED",
  "schema_version": "1",
  "occurred_at": "2026-11-28T02:00:00Z",
  "source_service": "invoice-service",
  "environment": "production",
  "release": "2.8",
  "actor_id": "user-482",
  "actor_type": "HUMAN",
  "tenant_id": "tenant-17",
  "action": "EXPORT_INVOICES",
  "resource_type": "EXPORT_JOB",
  "resource_id": "export-job-941",
  "outcome": "ACCEPTED",
  "request_id": "req-f1c5",
  "reason_code": "BUSINESS_EXPORT_AUTHORIZED"
}
~~~

Đây là dữ liệu **giả định dùng để dạy học**, không phải log thực tế. Đối với tác vụ bất đồng bộ, trạng thái **ACCEPTED** chỉ chứng minh yêu cầu đã được tiếp nhận theo điều kiện mô tả; cần event riêng như **EXPORT_COMPLETED/EXPORT_FAILED**, có job ID liên kết, để biết công việc cuối cùng ra sao.

### Về timestamp, thứ tự và đồng bộ thời gian

Nên dùng timestamp có offset rõ ràng hoặc UTC và có hệ thống đồng bộ thời gian phù hợp. Log tập trung cần phân biệt **thời điểm phát sinh**, **thời điểm nhận** và **thời điểm xử lý**; thứ tự bản ghi theo thời điểm nhận không luôn là thứ tự sự kiện đã xảy ra, nhất là khi có queue hoặc mạng chậm. Khi thiết lập timeline điều tra, cần kiểm tra clock skew và các event có thể tới muộn.

## 7. Không ghi bí mật và dữ liệu vượt nhu cầu

Log là dữ liệu được lưu lại, tìm kiếm, xuất, chuyển cho nhà cung cấp và đôi khi lưu lâu hơn dữ liệu nghiệp vụ. Vì vậy, **chính sách logging cũng là chính sách bảo vệ dữ liệu**.

### 7.1. Những dữ liệu mặc định không nên xuất hiện trong log

- Mật khẩu, mã OTP, câu trả lời xác minh, PIN, private key, signing key và bí mật ứng dụng.
- Access token, refresh token, session cookie, header Authorization, API key, client secret hoặc token reset tài khoản.
- Toàn bộ body request/response chứa hồ sơ khách hàng, số thẻ thanh toán, thông tin sức khỏe hoặc dữ liệu nhạy cảm khác.
- Chuỗi kết nối database có mật khẩu, URL chứa token hoặc query parameter bí mật.
- Bản sao đầy đủ file hoặc nội dung hóa đơn để “minh họa” sự kiện truy cập.
- Thông tin cá nhân không cần thiết để thực hiện mục đích logging đã xác định.

Một số thuộc tính như địa chỉ IP, email, định danh người dùng hoặc vị trí có thể là **dữ liệu cá nhân** trong bối cảnh cụ thể. Không mặc định chúng được phép ghi và chia sẻ không giới hạn; phải đánh giá tính cần thiết, chính sách quyền riêng tư và nghĩa vụ áp dụng.

### 7.2. Ghi tối thiểu nhưng vẫn đủ điều tra

Ví dụ khi một người dùng bị từ chối tải hóa đơn:

**Nên ghi:** ID sự kiện, actor ID tin cậy, tenant ID, loại tài nguyên, ID hóa đơn nội bộ đã kiểm soát, thao tác, kết quả DENIED, reason code, thời gian và request ID.

**Không cần ghi:** toàn bộ nội dung hóa đơn, token đăng nhập, mật khẩu, tên và địa chỉ khách hàng, toàn bộ request body.

Khi cần truy vết giá trị nhạy cảm, cân nhắc **tham chiếu tới bản ghi được quản lý quyền**, giá trị được che/mã hóa hoặc identifier một chiều có thiết kế phù hợp. Hash không tự động bảo vệ bí mật nếu đầu vào có entropy thấp, dễ đoán hay có thể đối chiếu từ tập dữ liệu có sẵn.

### 7.3. Redaction, validation và log injection

Không nên phụ thuộc hoàn toàn vào regex che dữ liệu ở cuối pipeline; quy tắc mạnh nhất là **không đưa secret vào event từ đầu**. Chuỗi đầu vào do client kiểm soát có thể chứa dấu xuống dòng, ký tự điều khiển, JSON bị chèn hoặc dữ liệu được chế tạo để đánh lừa parser và người điều tra (*log injection/log forging*).

Vì vậy:

- Sử dụng API logging có trường cấu trúc, escape/serialize đúng và giới hạn độ dài cho trường không đáng tin.
- Không ghép trực tiếp request, header hoặc exception message vào chuỗi log bảo mật khi chúng có thể chứa dữ liệu tùy ý.
- Chuẩn hóa enum và reason code thay vì ghi mô tả lỗi chứa thông tin nội bộ quá mức.
- Kiểm tra và giới hạn dữ liệu đưa vào telemetry, log exception, trace baggage và metadata.
- Thử các đầu vào chứa ký tự xuống dòng, dấu ngoặc, chuỗi dài và giá trị nhạy cảm để xác nhận **không giả tạo thêm event** hoặc phá cấu trúc.

## 8. Kiến trúc thu thập log và ranh giới tin cậy

Đối với hệ thống phân tán, một log event có thể đi qua nhiều điểm trước khi được người kiểm toán đọc:

~~~mermaid
flowchart LR
    A["Application / API"] --> C["Agent / Collector"]
    B["IAM / Cloud / DB audit"] --> C
    C --> Q["Buffer / Transport"]
    Q --> N["Normalization / Filtering"]
    N --> S[("Protected log storage")]
    S --> D["Detection / SIEM"]
    S --> R["Authorized investigation / Audit"]
    D --> O["On-call / Incident response"]
    M["Pipeline health monitoring"] -. "Verify delivery, lag, drops" .-> C
    M -.-> Q
    M -.-> S
~~~

**Các ranh giới cần xác định:** ứng dụng → collector; collector → kênh truyền; bộ xử lý → kho log; kho log → người tìm kiếm/nhà cung cấp; cảnh báo → người trực. Mỗi bước đều có thể làm **mất, sửa, trì hoãn, ghi trùng hoặc tiết lộ** dữ liệu.

### 8.1. Thu thập và chuyển giao

- Thiết kế nguồn event độc lập tối đa với request path; tránh để logging đồng bộ tạo điểm nghẽn hoặc làm rớt giao dịch không cần thiết.
- Bảo vệ đường truyền giữa agent/collector và nơi nhận; xác thực nguồn gửi, giới hạn quyền ghi.
- Khi dùng queue/buffer, xác định dung lượng, hành vi khi đầy, khả năng retry và rủi ro ghi trùng; dùng event ID/deduplication nếu cần.
- Theo dõi **log ingestion lag, queue depth, drop count, agent heartbeat, lỗi parser và độ tươi của dữ liệu**.
- Không chỉ giám sát từng nguồn đã đăng ký; phải có quy trình phát hiện **nguồn mới chưa được kết nối**.

### 8.2. Log pipeline lỗi thì ứng dụng xử lý thế nào?

Không có một câu trả lời “fail-open” hoặc “fail-closed” phù hợp cho mọi nghiệp vụ. Nếu kho log không truy cập được:

- Với event vận hành thông thường, có thể tiếp tục phục vụ và buffer phù hợp, nhưng phải cảnh báo nguy cơ mất chứng cứ.
- Với một thao tác đặc quyền hoặc giao dịch chịu yêu cầu audit bắt buộc, chính sách có thể yêu cầu **không thực hiện thao tác nếu không thể ghi nhận chứng cứ tối thiểu một cách đáng tin**, hoặc chọn cơ chế lưu bền vững tại nguồn trước khi tiếp tục.
- Với hệ thống an toàn hoặc cứu hộ, chặn chức năng khi log lỗi có thể gây hậu quả nghiêm trọng; phải phân tích rủi ro, yêu cầu pháp lý và tính liên tục trước khi quyết định.

**Điều quan trọng:** mô tả quyết định này cho từng lớp sự kiện/trường hợp, kiểm thử tình huống collector bị gián đoạn và lưu evidence. Không viết một tuyên bố chung “logging luôn bất đồng bộ, không ảnh hưởng ứng dụng” rồi giả định mọi audit event được lưu bền vững.

## 9. Bảo vệ log khỏi đọc, sửa, xóa và lạm dụng

Log chứa thông tin có thể nhạy cảm với bảo mật: ai dùng hệ thống, dữ liệu nào được truy cập, sự kiện xác thực, topology, tài khoản quản trị, dấu hiệu đang điều tra. Một log tập trung không được bảo vệ có thể trở thành mục tiêu hấp dẫn.

| Rủi ro với log | Security control | Bằng chứng cần kiểm tra |
| --- | --- | --- |
| Người không có thẩm quyền đọc log. | RBAC/ABAC phù hợp, phân tách nhóm điều tra, kiểm soát truy cập theo nhu cầu, mã hóa khi cần. | Ma trận quyền, test quyền đọc/xuất, log truy cập tới SIEM. |
| Người vận hành hoặc kẻ tấn công sửa/xóa dấu vết. | Quyền ghi và quyền xóa tách biệt, retention protection, lưu trữ bất biến khi thích hợp, giám sát xóa/sửa. | IAM policy, thử quyền xóa, audit thay đổi, kiểm tra retention. |
| Log bị thay đổi trên đường truyền. | Kênh được xác thực và bảo vệ, kiểm soát nguồn, cơ chế bảo đảm toàn vẹn tương ứng. | Cấu hình agent/collector, thử giả nguồn, kiểm tra TLS/chứng chỉ khi áp dụng. |
| Secret bị ghi vào log. | Data minimization, allowlist fields, redaction trước ghi, review thay đổi schema. | Test với input canary/synthetic, kiểm tra mẫu, kết quả secret scanning trong phạm vi được phép. |
| Đường ghi log bị lạm dụng gây DoS. | Quota, buffer, limits, phân loại mức ưu tiên event, capacity planning. | Stress test, telemetry về loss/lag, phản ứng khi queue đầy. |
| Quá nhiều người truy xuất log nhạy cảm. | Phê duyệt truy cập, giới hạn thời hạn, just-in-time access và ghi audit hành vi truy vấn/xuất. | Access review, audit trail tìm kiếm và xuất log, hồ sơ ngoại lệ. |
| Bằng chứng không thể đối chiếu nguồn gốc. | Thời gian chuẩn, source identity, event schema, bảo vệ integrity và lưu hồ sơ thu thập. | Sơ đồ pipeline, log nguồn/kho đích, kiểm tra đồng bộ thời gian, test correlation. |

### Tính bất biến không đồng nghĩa tính đầy đủ

Kho log chỉ-ghi-thêm, immutable storage, chữ ký hoặc chuỗi hash có thể làm khó việc sửa dấu vết **sau khi đã được ghi**, nhưng **không tự chứng minh sự kiện đã được tạo và gửi đầy đủ**. Nếu ứng dụng không phát event hoặc agent bị tắt trước khi ghi, storage bất biến vẫn trống.

Một checksum/hash đơn lẻ có thể phát hiện thay đổi nếu có **giá trị tham chiếu và khóa/nguồn bảo vệ thích hợp**, nhưng không chứng minh người phát sinh sự kiện hay tính đầy đủ của mọi event. Khi cần mức assurance cao, phải kết hợp cơ chế phát sinh tại nguồn, phân tách quyền, forwarding độc lập, giám sát mất log và kiểm toán quy trình.

### Chuỗi lưu giữ bằng chứng (chain of custody)

Trong điều tra nghiêm trọng, cần ghi ai thu thập, thời điểm, phương pháp xuất, phạm vi, kiểm tra tính toàn vẹn, nơi lưu, ai đã tiếp cận và các lần chuyển giao. Bản xuất log phục vụ vụ việc không nên được coi tương đương với việc truy vấn tùy ý trên dashboard mà không có lịch sử và bảo vệ.

## 10. Retention, truy xuất và xóa log

Chính sách cần quy định **giữ log bao lâu, tại sao, ở lớp lưu trữ nào và bằng cách nào bảo đảm xóa đúng hạn**. Không có một số ngày chung đúng cho mọi loại log và mọi tổ chức.

### 10.1. Xác định retention theo mục đích và nghĩa vụ

Các yếu tố cần cân nhắc:

- Thời gian cần thiết để phát hiện sự cố, điều tra, kiểm toán hoặc đối soát.
- Nghĩa vụ pháp lý, hợp đồng và các yêu cầu quản lý hồ sơ có áp dụng; tham vấn pháp chế/privacy.
- Độ nhạy của log, yêu cầu bảo vệ, chi phí và nguy cơ nếu lưu lâu không cần thiết.
- Khả năng tìm kiếm nhanh ở lớp **hot**, phục vụ điều tra ở lớp **warm** hoặc lưu trữ dài hạn ở lớp **archive**.
- Những trường hợp phải tạm giữ bằng chứng (*legal hold/incident hold*) theo thẩm quyền.

Ví dụ mô hình **chỉ minh họa**, các thời hạn phải do tổ chức phê duyệt:

| Nhóm log | Quy tắc quản trị cần nêu | Cơ sở chọn thời hạn |
| --- | --- | --- |
| Audit hành động đặc quyền | Bảo vệ cao, quyền đọc hạn chế, kiểm tra truy xuất định kỳ. | Nhu cầu điều tra và nghĩa vụ kiểm soát đặc quyền. |
| Log truy cập dữ liệu nhạy cảm | Ghi tối thiểu, bảo vệ định danh và truy xuất theo mục đích. | Risk assessment và yêu cầu giải trình theo loại dữ liệu. |
| Log vận hành chi tiết | Tối ưu khối lượng, có thể tổng hợp trước khi hủy theo chính sách. | Cần thiết cho debug/SLO, hạn chế tích tụ dữ liệu. |
| Log an ninh hạ tầng / IAM | Có nguồn gốc và khả năng tương quan với ứng dụng. | Thời gian phát hiện, vòng đời danh tính và phạm vi sự cố. |
| Evidence cho sự cố hoặc audit đang mở | Được giữ và bảo vệ theo quy trình riêng, có ngày/điều kiện kết thúc. | Nghĩa vụ giải trình, lưu giữ chứng cứ và phê duyệt. |

### 10.2. Những câu hỏi phải kiểm tra khi xóa

- Log có ở bản sao, snapshot, archive, backup hoặc hệ thống của nhà cung cấp không?
- Retention có thực thi tại tất cả nơi lưu và bản sao theo đúng quy định không?
- Ai có quyền tạo **hold**, ai duyệt kết thúc hold và ai được phép xóa?
- Có bằng chứng về job xóa, hành vi hết hạn lưu trữ và các ngoại lệ không?
- Cơ chế xóa có khả thi với storage bất biến không, hay cần thiết kế retention/hold ngay từ đầu?

**Không tự động lưu vô hạn “để phòng khi cần điều tra”.** Lưu quá mức có thể tăng thiệt hại khi log bị lộ và mâu thuẫn với nguyên tắc giới hạn mục đích/lưu giữ áp dụng.

## 11. Từ log đến phát hiện và ứng cứu sự cố

Một logging policy tốt không dừng ở việc thu thập. Đối với các kịch bản rủi ro trọng yếu, phải biết **tín hiệu nào kích hoạt cảnh báo và ai chịu trách nhiệm hành động**.

~~~mermaid
flowchart TD
    A["Risk scenario / Security requirement"] --> B["Security event contract"]
    B --> C["Source emission + protected pipeline"]
    C --> D["Normalization, storage, correlation"]
    D --> E{"Detection / alert condition?"}
    E -- "Có" --> F["Triaging by on-call"]
    F --> G["Incident response / investigation"]
    G --> H["Findings + remediation + retest"]
    E -- "Chưa" --> I["Retain for monitoring / audit"]
    H --> J["Update detection and assurance evidence"]
    J --> A
    I --> J
~~~

### Một use case phát hiện cần ghi những gì?

Giả sử mục tiêu là nhận diện truy cập hóa đơn chéo tenant:

- **Kịch bản và mức rủi ro:** user tenant A cố đọc tài nguyên tenant B.
- **Nguồn event:** kết quả kiểm tra authorization trên Invoice Service, không chỉ API Gateway.
- **Điều kiện:** sự kiện AUTHZ_DENIED với reason_code TENANT_SCOPE_MISMATCH; số lượng/tần suất theo actor và tenant được hiệu chuẩn để giảm báo động giả.
- **Liên kết:** actor ID, resource ID, request ID, timestamp, release và source service.
- **Người xử lý:** trực security/on-call, tuyến escalation, cách xác minh tác động, bảo vệ dữ liệu log.
- **Bằng chứng:** test tạo event, kiểm thử quy tắc alert, ghi nhận thông báo, ticket xử lý, kết quả điều tra và retest.

Không phải mọi DENIED event đều là tấn công. Có thể là người dùng mở nhầm liên kết, ứng dụng lỗi quyền hoặc hoạt động test; detection rule cần xem **bối cảnh** và có thể học từ false positive/false negative.

### Kiểm tra cả trường hợp không có cảnh báo

Một hệ thống không phát alert có thể vì không có tấn công; cũng có thể vì agent ngừng hoạt động, sai parser, trường event thay đổi hoặc dashboard không nhận dữ liệu. Do đó cần **alert riêng cho health của logging** và thử nghiệm đường phát hiện đầu cuối từ nguồn tới người nhận.

## 12. Quy định thực thi cho Java/Spring Boot

Ứng dụng Java có thể phát log bảo mật có cấu trúc thông qua SLF4J hoặc cơ chế audit chuyên dụng. Ví dụ sau minh họa **security event ở thời điểm từ chối quyền**. Mục tiêu là cho thấy các trường nghiệp vụ và bảo mật, không phải chỉ log một exception:

~~~java
// Minh họa SLF4J 2.x; các ID phải lấy từ ngữ cảnh đã xác minh.
void recordInvoiceAccessDenied(
        String actorId,
        String tenantId,
        String invoiceId,
        String requestId) {

    securityLogger.atWarn()
        .addKeyValue("event_type", "AUTHZ_DENIED")
        .addKeyValue("schema_version", "1")
        .addKeyValue("action", "READ_INVOICE")
        .addKeyValue("actor_id", actorId)
        .addKeyValue("tenant_id", tenantId)
        .addKeyValue("resource_type", "INVOICE")
        .addKeyValue("resource_id", invoiceId)
        .addKeyValue("request_id", requestId)
        .addKeyValue("outcome", "DENIED")
        .addKeyValue("reason_code", "TENANT_SCOPE_MISMATCH")
        .log("Security authorization decision");
}
~~~

**Lưu ý kỹ thuật:** API fluent logging nêu trên cần SLF4J 2.x và cấu hình backend/encoder tương ứng; các key-value chỉ trở thành **JSON log có cấu trúc đúng** khi encoder và pipeline được cấu hình phù hợp. Đoạn mã không thể hiện toàn bộ xử lý authentication, authorization, cấu hình SecurityContext hay đường gửi sự kiện.

Không lấy **actorId/tenantId** trực tiếp từ header mà client tự kiểm soát rồi coi là danh tính thật. Phải lấy từ principal/context đã được kiểm chứng. ID tài nguyên nếu có thể chứa thông tin nhạy cảm cũng cần được xem xét theo chính sách; không log request body, token hoặc toàn bộ hóa đơn.

### Định nghĩa điểm ghi event để tránh kết luận sai

Đối với thao tác như tạo hoặc xuất hóa đơn, có ít nhất ba giai đoạn cần phân biệt:

1. **REQUESTED / ACCEPTED:** yêu cầu hợp lệ được tiếp nhận hoặc job đã được tạo.
2. **COMPLETED / FAILED:** giao dịch hoặc công việc cuối cùng hoàn tất hay thất bại.
3. **SECURITY_DECISION:** phân quyền cho phép hoặc từ chối, theo điểm ra quyết định.

Nếu ghi “SUCCESS” **trước** khi transaction commit nhưng dữ liệu cuối cùng bị rollback, audit trail có thể sai. Thiết kế cần quy định điểm phát event, mối liên hệ với transaction và cơ chế bền vững khi có lỗi. Trong các luồng phù hợp, **transactional outbox** có thể giúp liên kết bản ghi nghiệp vụ và event cần gửi; tuy nhiên vẫn phải kiểm tra retry, duplicate delivery, độ trễ và xử lý khi hệ thống log không nhận được event.

### Nguyên tắc với exception và debug logging

Không bật debug toàn cục ở production chỉ để điều tra nhanh nếu điều đó làm lộ token, header hoặc payload. Cần quy trình **tăng mức logging có thời hạn, phê duyệt, giới hạn phạm vi, giám sát và hoàn nguyên**, cùng kiểm tra dữ liệu được ghi. Exception message và stack trace chỉ chuyển vào kênh có quyền phù hợp, không gửi nguyên văn sang API response cho người dùng.

## 13. Mẫu nội dung chính sách logging cấp tổ chức

Một chính sách có thể viết theo lối **quy định kiểm chứng được** thay vì liệt kê công nghệ. Mẫu rút gọn dưới đây chỉ để thực hành; các thời hạn/đơn vị và trách nhiệm cụ thể do tổ chức xác định:

> **Phạm vi:** mọi hệ thống xử lý dữ liệu hoặc thực hiện nghiệp vụ nằm trong phạm vi quản trị bảo mật của tổ chức, bao gồm các dịch vụ do bên thứ ba vận hành khi có quyền hoặc nghĩa vụ truy xuất sự kiện.
>
> **Yêu cầu sự kiện:** hệ thống phải ghi các hành động xác thực, thay đổi quyền, sử dụng đặc quyền, thao tác nhạy cảm và sự kiện liên quan rủi ro đã xác định theo event catalog. Mọi ngoại lệ về coverage phải có hồ sơ và quyết định theo thẩm quyền.
>
> **Tính chính xác:** event phải có thời gian, nguồn, định danh chủ thể đáng tin khi có, thao tác, phạm vi, kết quả và correlation ID phù hợp với mục đích.
>
> **Bảo vệ dữ liệu:** không đưa mật khẩu, khóa bí mật, token hay nội dung nhạy cảm không cần thiết vào log. Phân quyền truy xuất và xuất log theo nhu cầu công việc, lưu dấu người truy cập.
>
> **Bảo vệ bằng chứng:** kênh truyền và nơi lưu phải có biện pháp chống đọc/sửa/xóa trái phép; phải theo dõi sự cố thu thập, mất log và thay đổi chính sách logging.
>
> **Retention và xóa:** áp dụng lịch lưu giữ đã phê duyệt theo loại log, nghĩa vụ và mục đích, bao gồm bản sao và hold khi được phép.
>
> **Kiểm chứng:** owner phải cung cấp evidence về coverage, cấu hình, hiệu lực, giám sát pipeline, truy xuất có quyền và retest các phát hiện.
>
> **Ngoại lệ và thay đổi:** thay đổi ảnh hưởng security event, thời hạn lưu hoặc quyền truy xuất phải được đánh giá, phê duyệt, ghi nhận và kiểm tra lại; ngoại lệ có hạn cùng người chịu trách nhiệm theo dõi.

Để mẫu này trở thành văn bản thực thi, tổ chức cần bổ sung **mã chính sách, người phê duyệt, ngày hiệu lực, phiên bản, định nghĩa event catalog, bảng retention, quy trình và thẩm quyền cụ thể**, cùng lịch review.

## 14. Phân công vai trò và trách nhiệm

| Vai trò | Trách nhiệm điển hình |
| --- | --- |
| **Policy owner / security governance** | Soạn, trình phê duyệt, duy trì chính sách/standard, phối hợp kiểm tra áp dụng và theo dõi ngoại lệ. |
| **Data owner / business owner** | Xác định sự kiện có hậu quả nghiệp vụ, dữ liệu nhạy cảm, phạm vi được phép và nhu cầu điều tra. |
| **Service / control owner** | Đảm bảo dịch vụ phát các event bắt buộc, cung cấp bằng chứng và xử lý điểm thiếu coverage. |
| **Developer / service operator** | Triển khai schema, tạo event đúng điểm xử lý, kiểm thử và giám sát ở dịch vụ. |
| **Logging platform / SIEM owner** | Bảo vệ pipeline, quản trị ingestion, retention, access controls, health monitoring và khả năng truy xuất. |
| **SOC / incident response** | Thiết kế/vận hành detection use case, phân loại cảnh báo, điều tra và lưu bằng chứng sự cố. |
| **Legal / privacy / compliance** | Tư vấn nghĩa vụ, thời hạn lưu, giới hạn mục đích, quyền truy cập và hoạt động thông báo khi áp dụng. |
| **Risk owner** | Quyết định xử lý hoặc chấp nhận rủi ro còn lại trong phạm vi thẩm quyền được giao. |
| **Security assurance / auditor** | Đánh giá thiết kế, độ bao phủ, hiệu quả vận hành và bằng chứng; ghi nhận phát hiện. |

**Chủ sở hữu control logging không tự động có quyền chấp nhận rủi ro của việc thiếu log.** Nếu một API quan trọng không thể ghi sự kiện, control owner chịu trách nhiệm điều phối khắc phục và cung cấp sự thật về phạm vi; risk owner hoặc cấp được ủy quyền quyết định theo chính sách, trừ những yêu cầu không được phép miễn trừ.

### Một RACI minh họa cho log truy cập dữ liệu nhạy cảm

| Hoạt động | Service owner | Platform/SIEM | Security governance | Assessor | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| Chốt event contract cho API theo yêu cầu đã duyệt | **A/R** | C | C | C | I |
| Phát security event đúng điểm trong ứng dụng | **A/R** | C | I | I | I |
| Nhận, bảo vệ và duy trì hạ tầng log | C | **A/R** | C | I | I |
| Ban hành chính sách logging chung | C | C | **A/R** | C | I |
| Kiểm tra độc lập coverage, toàn vẹn và truy xuất | C | C | I | **A/R** | I |
| Chấp nhận ngoại lệ residual risk trong thẩm quyền | C | C | C | C | **A/R** |

RACI cần được chỉnh theo mô hình quản trị thực tế. Một số hoạt động phải tách nhỏ nếu có nhiều cấp phê duyệt; tránh để nhiều người mang chữ A cho cùng một quyết định mà không có người chịu trách nhiệm cuối cùng.

## 15. Chứng minh chính sách logging đang được thực thi

Chính sách phải chuyển thành **assurance claims** có thể kiểm tra. Ví dụ dùng mô hình **Claim – Argument – Evidence (CAE)**:

**Claim:** “Các thao tác xuất hóa đơn trong phạm vi Invoice Service release 2.8 được ghi nhận với actor, tenant, job ID, kết quả và thời gian, chuyển tới kho log được bảo vệ, có thể truy xuất khi điều tra theo retention áp dụng.”

**Argument:** “Service phát security events ở các điểm quyết định và hoàn tất, collector được quản lý, các thành phần xử lý log được giám sát; storage kiểm soát quyền đọc/sửa/xóa và retention.”

**Evidence:** danh sách luồng export, event schema, integration tests, log mẫu đã che dữ liệu, cấu hình forwarding và quyền trên production, kết quả thử lỗi collector, báo cáo ingestion lag, access review, retention tests và các phát hiện chưa khắc phục.

### Ma trận assurance cho logging policy

| Claim nhỏ | Bằng chứng cần lấy | Kết quả nào không đủ? |
| --- | --- | --- |
| Mọi đường export nhạy cảm trong phạm vi đều phát audit event. | Inventory endpoint/job; thử thành công, từ chối, lỗi; đối chiếu event tại nguồn và đích. | Một ảnh dashboard chứa vài event export. |
| Security event có danh tính và correlation đúng. | Trace mẫu qua gateway → service → worker; test giả header và thiếu request ID. | Một record có username do client gửi. |
| Log không tiết lộ secret theo tiêu chuẩn. | Test sử dụng token/dữ liệu canary giả, kiểm tra pipeline và export; review logging code. | Chỉ kiểm tra một regex che dữ liệu trên một endpoint. |
| Người không có quyền không xem/xóa được log. | Ma trận quyền, negative tests đọc/xóa/đổi retention, audit của truy cập SIEM. | Lời xác nhận “chúng tôi chỉ có admin truy cập”. |
| Collector lỗi sẽ được phát hiện và xử lý. | Diễn tập agent disconnect, queue full, parser failure; alert và incident timeline. | Agent ở trạng thái Running trong một lần quan sát. |
| Retention và disposal tuân thủ chính sách. | Cấu hình, thử hết hạn/hủy ở phạm vi cho phép, kiểm tra archive/backup, hồ sơ hold. | Số ngày trên một dashboard mà không xét bản sao. |
| Thay đổi policy/schema được quản trị. | Version control, thay đổi được duyệt, regression test rule, evidence qua release. | Pull request đã merge nhưng chưa triển khai hoặc SIEM parser chưa cập nhật. |

### Bằng chứng tốt cần có metadata

- **Claim/control ID** được kiểm chứng, phạm vi dịch vụ và luồng dữ liệu.
- Phiên bản release, cấu hình, rule, schema và thời điểm kiểm tra.
- Người thực hiện, công cụ, môi trường, các trường hợp test và kết quả thực.
- Hiện vật gốc được bảo vệ, cách truy xuất, những phần bị lược bỏ vì bí mật.
- Các phát hiện, ngoại lệ, giới hạn kiểm tra và người chịu trách nhiệm khắc phục.

Để kiểm tra hiệu quả vận hành, chỉ thử event một lần tại staging thường **chưa đủ** chứng minh log production được chuyển và lưu đúng trong khoảng thời gian đang đánh giá. Nên phối hợp test trước release với quan sát/cấu hình production và phép kiểm tra định kỳ hoặc theo sự kiện.

## 16. Kế hoạch kiểm thử logging policy

Trước khi kết luận logging đạt yêu cầu, nhóm có thể thiết kế một bộ kiểm tra theo rủi ro:

| ID | Kịch bản kiểm thử | Kỳ vọng và dấu vết cần đối chiếu |
| --- | --- | --- |
| **LOG-01** | Đăng nhập thành công và thất bại. | Event type, outcome, principal/claimed identity được phân biệt, timestamp và source đúng; không có password/token. |
| **LOG-02** | Người dùng tenant A yêu cầu hóa đơn tenant B. | AUTHZ_DENIED với scope, actor, reason code; không tiết lộ nội dung hóa đơn. |
| **LOG-03** | User được phép tạo job export, worker hoàn tất. | Có event tiếp nhận và hoàn tất, liên kết bởi job/request ID. |
| **LOG-04** | Export thất bại hoặc giao dịch bị rollback. | Kết quả log phản ánh đúng trạng thái cuối cùng; không có SUCCESS giả. |
| **LOG-05** | Client gửi newline, JSON sai và chuỗi rất dài trong trường đầu vào. | Không phá cấu trúc event, không sinh record giả, không lộ payload không cần thiết. |
| **LOG-06** | Đầu vào chứa token/secret canary giả. | Secret không hiện ở nguồn, collector, SIEM, trace hoặc file xuất trong phạm vi test. |
| **LOG-07** | Agent, broker hoặc collector bị gián đoạn có kiểm soát. | Đo mất/trễ event, queue, cảnh báo, hành vi phục hồi và duplicate handling. |
| **LOG-08** | Người dùng thiếu quyền truy vấn/xóa/export log. | Từ chối truy cập, có log của hành động quản trị log, quyền phù hợp. |
| **LOG-09** | Thay đổi rule parser hoặc schema event. | Detection vẫn nhận đúng event hoặc phát hiện lỗi parsing; regression test. |
| **LOG-10** | Log tới thời hạn lưu và có trường hợp hold. | Xử lý theo lịch retention và hold được phê duyệt, có evidence ở nơi lưu liên quan. |

### Chọn chỉ số sức khỏe logging

| Chỉ số | Cách hiểu | Điều phải tránh |
| --- | --- | --- |
| **Source coverage** | Tỷ lệ nguồn/luồng bắt buộc có giám sát và hợp đồng event đã xác nhận. | Chia cho inventory thiếu hệ thống rồi kết luận đạt 100%. |
| **Event delivery completeness** | Mức khớp giữa sự kiện lẽ ra phải phát và số đã đến nơi theo phép đối chiếu đáng tin. | Dùng số event tại SIEM làm mẫu số cho chính nó. |
| **Ingestion lag** | Chênh lệch thời điểm phát sinh và thời điểm nhận/xử lý. | Không kiểm tra clock skew hoặc event đến muộn. |
| **Drop/error rate** | Số/tỷ lệ event bị rớt, lỗi parse, gửi thất bại, bị chặn ngoài dự kiến. | Chỉ nhìn log pipeline mà không phát hiện các nguồn hoàn toàn im lặng. |
| **Alert detection/response** | Thời gian từ event tới alert, người xử lý và hành động. | Coi alert đã phát là đã có ứng cứu hiệu quả. |
| **Retention/access compliance** | Mức tuân thủ quy tắc lưu giữ, quyền truy xuất và ngoại lệ. | Đánh giá chỉ trên storage chính, bỏ qua export/backup. |

Các **ngưỡng/SLO nội bộ** cho logging phải được quyết định theo độ quan trọng nghiệp vụ và rủi ro. Ví dụ giả định “95% event đến trong hai phút” chỉ có ý nghĩa với một loại event cụ thể; đối với thao tác cần audit tức thời, tổ chức có thể cần điều kiện chặt hơn. Không lấy các con số ví dụ làm quy định chung cho mọi hệ thống.

## 17. Tình huống thực hành: dấu vết xuất hóa đơn xuyên tenant

Một nền tảng SaaS cho phép người dùng yêu cầu xuất hóa đơn và gửi link tải qua email. Các bước gồm:

~~~text
User -> API Gateway -> Invoice Service -> Message Broker
                                         |
                                         v
                                    Export Worker
                                         |
                                         v
                                   Object Storage
                                         |
                                         v
                                    Download Link
~~~

Security objective: **chỉ chủ thể được phép thuộc đúng tenant mới được yêu cầu hoặc tải dữ liệu hóa đơn của tenant đó**. Threat modeling xác định nguy cơ request sử dụng sai tenant ID, worker chạy quá quyền và link tải bị chia sẻ trái phép.

### Bước 1 — Xác định event contract theo luồng nghiệp vụ

| Mốc | Event gợi ý | Thuộc tính chính |
| --- | --- | --- |
| Request bị từ chối quyền. | AUTHZ_DENIED | Actor, tenant, loại đối tượng, request ID, reason code, outcome. |
| Yêu cầu tạo export được chấp thuận. | INVOICE_EXPORT_REQUESTED | Actor, tenant, job ID, quyền đã kiểm tra, thời điểm. |
| Worker xử lý job. | INVOICE_EXPORT_STARTED | Service principal, tenant/job ID, thời điểm, correlation. |
| Worker hoàn tất/thất bại. | INVOICE_EXPORT_COMPLETED / FAILED | Job ID, outcome, số bản ghi nếu cần và phù hợp bảo mật, error code không nhạy cảm. |
| Một chủ thể tải file. | INVOICE_EXPORT_DOWNLOADED / DENIED | Chủ thể, tenant, export ID, kết quả quyền và thời gian. |

Với đối tượng không có danh tính người dùng trực tiếp (worker), cần ghi **service principal** cùng job ID, và có chuỗi evidence liên kết tới yêu cầu ban đầu. Không giả định rằng user request ban đầu là danh tính của mọi hành động nội bộ.

### Bước 2 — Phân tách controls và bằng chứng

- **Application control:** kiểm tra tenant/object authorization và phát event quyết định. Bằng chứng: code review, test chéo tenant, log mẫu.
- **Pipeline control:** agent/collector chuyển event đầy đủ với bảo vệ kênh. Bằng chứng: cấu hình, test gửi, lag và lỗi chuyển.
- **Storage control:** log nhạy cảm không public, quyền đọc/xóa tách biệt, retention phù hợp. Bằng chứng: IAM policy, negative access tests, kết quả retention.
- **Detection control:** cảnh báo lặp lại AUTHZ_DENIED hoặc tải dữ liệu bất thường, có người xử lý. Bằng chứng: test rule và ticket.
- **Assurance governance:** claim được duyệt phạm vi, phát hiện có owner và retest. Bằng chứng: risk/control register, report, quyết định.

### Bước 3 — Phát hiện thiếu sót

Trong diễn tập, người dùng tenant A bị chặn khi tải file tenant B, nhưng **không có event AUTHZ_DENIED ở API tải** vì tầng object storage từ chối trực tiếp. Một dashboard báo 0 lần tải trái phép không cho biết kiểm soát hoạt động tốt hay không, vì **hành động từ chối chưa được ghi trong nguồn đang xét**.

Đội service và storage cần xác định **điểm ghi audit thực tế**, bảo đảm đường truy cập trực tiếp tới storage/CDN được theo dõi theo điều kiện chính sách. Có thể kết hợp access log của nền tảng storage với event của ứng dụng, nhưng phải liên kết được chủ thể, request/resource và kết quả ở mức cần thiết; nếu nền tảng chỉ cho biết truy cập từ service principal mà không biết user thật, phải ghi nhận giới hạn và thiết kế tương quan phù hợp.

### Bước 4 — Khắc phục và kiểm chứng lại

Nhóm bổ sung event tại điểm quyết định, tích hợp access logs của storage và cập nhật correlation. Assessor chạy lại các case đúng quyền, sai tenant, link hết hạn và đường tải trực tiếp; so sánh event nguồn–đích, kiểm tra thông tin nhạy cảm và khả năng truy xuất theo quyền.

Nếu việc hoàn thiện audit trail chưa thể xong trước ngày release, phải ghi **risk/evidence gap**, biện pháp tạm, owner và quyết định theo thẩm quyền. Không được tự động hạ residual risk vì endpoint đã trả 403 hoặc vì kế hoạch sửa đã được giao.

### Bước 5 — Kết luận assurance có giới hạn

Một kết luận phù hợp có thể nêu: “Đối với release và các đường tải đã kiểm thử, truy cập sai tenant bị từ chối; event authorization và access log có thể liên kết tới job/actor theo trường bắt buộc. Đường CDN mới chưa được đánh giá độc lập nên chưa kết luận về tính đầy đủ toàn bộ luồng tải.” Cách diễn đạt này cho thấy **claim, bằng chứng và giới hạn**, thay vì gắn nhãn “logging 100% secure”.

## 18. Xử lý ngoại lệ, thay đổi và khắc phục phát hiện

Một số hệ thống cũ không có khả năng phát event theo schema chung; nhà cung cấp SaaS không cho xuất toàn bộ audit logs; hoặc việc log chi tiết có thể gây ảnh hưởng hiệu năng. Những tình huống đó cần **quy trình ngoại lệ**, không được âm thầm bỏ qua.

Một hồ sơ ngoại lệ nên ghi:

1. **Control/requirement ID** và nguồn/luồng sự kiện chưa đạt.
2. Lý do kỹ thuật/nghiệp vụ và **kịch bản rủi ro phát sinh từ thiếu log**.
3. Phạm vi dữ liệu, dịch vụ, người dùng, thời gian và mức hậu quả có căn cứ.
4. Biện pháp bù đắp, ví dụ log tại một điểm kiểm soát khác đủ tin cậy hoặc review thủ công có bằng chứng.
5. Owner khắc phục, hạn, điều kiện kết thúc và lịch kiểm tra lại.
6. Risk owner hoặc cấp có thẩm quyền xem xét quyết định theo chính sách; kiểm tra ràng buộc không được phép miễn trừ.
7. Bằng chứng retest và đánh giá lại residual risk sau sửa.

Không phải control thay thế nào cũng tương đương: access log của gateway có thể ghi request đến, nhưng không chắc biết giao dịch tại worker đã commit, không tự biết authorization theo đối tượng hoặc người nhận cuối cùng của file. Phải đánh giá **claim cụ thể** trước khi chấp nhận bù đắp.

### Khi thay đổi hệ thống phải xem lại chính sách logging

Ví dụ: thêm API export, chuyển từ HTTP đồng bộ sang event queue, bổ sung CDN, đổi Identity Provider, thay cơ chế ủy quyền theo tenant, kết nối cloud/SaaS mới, nâng phiên bản logger/parser, thay quy tắc xóa và mở rộng quyền xem logs.

Mỗi thay đổi có thể ảnh hưởng **event coverage, nguồn danh tính, correlation, nhãn nhạy cảm, retention hoặc quy tắc phát hiện**. Cần cập nhật event catalog, kiểm thử tương ứng và kết luận assurance; không cần làm lại mọi bài test nếu chứng minh được phạm vi không bị tác động.

## 19. Những ngộ nhận thường gặp

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Có log là có đầy đủ bằng chứng.” | Cần kiểm tra coverage, chất lượng event, nguồn gốc, tính toàn vẹn, khả năng truy xuất và thời gian lưu. |
| “Log càng nhiều càng tốt.” | Ghi theo mục đích, sự kiện rủi ro và tối thiểu dữ liệu; ghi thừa có thể lộ bí mật và gây quá tải. |
| “HTTP 200 và access log là audit trail nghiệp vụ.” | Cần event ở đúng điểm quyết định và trạng thái hoàn tất/rollback của nghiệp vụ. |
| “Đã có SIEM nên mọi nguồn đều được giám sát.” | Phải có inventory, kiểm tra phát sinh–nhận, parser và các nguồn im lặng. |
| “Mã hóa kho log nghĩa là không ai sửa được.” | Mã hóa không thay thế phân tách quyền ghi/xóa, lưu giữ bất biến và kiểm tra integrity. |
| “Storage immutable chứng minh tất cả sự kiện đã được ghi.” | Chỉ bảo vệ các event đã tới kho; vẫn phải kiểm tra mất sự kiện ở nguồn/đường truyền. |
| “Không thấy log tấn công nghĩa là không có tấn công.” | Cần xét điểm mù, retention, clock skew và mất pipeline. |
| “Log có username là đủ định danh.” | Phải biết username là claimed identity hay authenticated principal và có cơ sở tin cậy. |
| “Một alert được phát nghĩa là rủi ro đã được xử lý.” | Cần người nhận, phản ứng, điều tra, khắc phục và retest. |
| “Giữ log vô hạn sẽ phục vụ kiểm toán tốt nhất.” | Retention theo nhu cầu, rủi ro và nghĩa vụ; dữ liệu lưu quá mức tạo nguy cơ riêng. |
| “Debug mode an toàn nếu chỉ bật vài phút.” | Phải kiểm soát mức log, dữ liệu nhạy cảm, quyền bật/tắt, thời hạn và bằng chứng hoàn nguyên. |
| “Đóng ticket logging nghĩa là control đạt.” | Cần kiểm chứng trên phiên bản/môi trường liên quan và lưu kết quả retest. |

## 20. Checklist tự đánh giá chính sách logging

Khi chuẩn bị review, audit hoặc triển khai một dịch vụ mới, hãy xác nhận:

1. **Phạm vi:** đã có danh sách hệ thống, dịch vụ, luồng nghiệp vụ và nơi lưu log quan trọng chưa?
2. **Risk-based events:** nhóm hành động bảo mật cần ghi đã được liên kết với threat scenario/security requirement chưa?
3. **Schema:** có ID sự kiện, thời điểm, nguồn, chủ thể đáng tin, hành động, tài nguyên, kết quả và correlation phù hợp không?
4. **Data protection:** có quy tắc cấm secret, tối thiểu PII và kiểm tra log injection không?
5. **Delivery:** có giám sát mất log, trễ, lỗi parser, nguồn ngừng phát và queue đầy không?
6. **Integrity và access:** quyền đọc/ghi/xóa, kiểm soát truy xuất và bảo vệ hiện vật có đủ theo rủi ro không?
7. **Retention:** thời hạn, backup/archive, hold và xóa dữ liệu có được phê duyệt và kiểm chứng không?
8. **Detection:** các use case trọng yếu có quy tắc, đầu mối xử lý và diễn tập end-to-end không?
9. **Evidence:** test và cấu hình có đúng phiên bản, môi trường, phạm vi và thể hiện cả trường hợp thất bại không?
10. **Governance:** owner, ngoại lệ, phát hiện và trigger đánh giá lại đã được ghi và theo dõi chưa?

## 21. Bài tập ứng dụng

### Bài tập A — Log toàn bộ request để điều tra

Đội backend đề xuất ghi mọi request body trong production vì muốn truy ra mọi lỗi. Trong body có access token, địa chỉ khách hàng và dữ liệu đơn hàng.

**Gợi ý:** Không nên ghi toàn bộ body. Xác định mục đích điều tra, thiết kế allowlist trường, event ID, request ID, reason code, metadata tối thiểu; kiểm tra không lộ secret và xử lý trường do client kiểm soát. Với tình huống cần chẩn đoán chuyên sâu, dùng cơ chế truy xuất dữ liệu có quyền và có thời hạn thay vì mở rộng log mặc định.

### Bài tập B — Event đúng ở nguồn nhưng không tới SIEM

Unit test xác nhận ứng dụng phát AUTHZ_DENIED, nhưng sau deploy cấu hình collector sai nên event không tới kho tập trung. Có thể kết luận logging policy đạt không?

**Gợi ý:** Chưa. Test nguồn chỉ chứng minh một mắt xích. Phải kiểm tra đường truyền, parser, lưu trữ, khả năng tìm kiếm, health alert và hành vi khi pipeline lỗi; khắc phục và retest đầu cuối rồi mới đánh giá claim về log tập trung.

### Bài tập C — Lịch sử xuất hóa đơn không xác định người dùng

Trong SIEM có event EXPORT_COMPLETED từ worker với service account hợp lệ, nhưng không có job ID hoặc yêu cầu ban đầu để truy ngược người dùng.

**Gợi ý:** Bằng chứng về worker không đủ để xác nhận người đã yêu cầu export. Cần correlation giữa request–job–worker, principal đáng tin, tenant và trạng thái cuối cùng; kiểm thử cả trường hợp retry/duplicate và lỗi job.

### Bài tập D — Bằng chứng biến mất sau khi đã phê duyệt

Audit cách đây ba tháng báo log đầy đủ; tuần này một nhóm thay đổi parser và bỏ trường actor_id. Dashboard vẫn đếm event bình thường.

**Gợi ý:** Claim cũ có thể mất hiệu lực do thay schema; cần event contract tests, cảnh báo lỗi schema/field required, kiểm tra bản phát hành và cập nhật evidence. Không nên chỉ dựa vào tổng số event để kết luận hệ thống còn khả năng truy vết.

### Bài tập E — Log bất biến nhưng bỏ sót đợt mất kết nối

Kho log có cơ chế bất biến trong 90 ngày; một collector ngừng gửi suốt bốn giờ nhưng không cảnh báo. Người phụ trách kết luận “log luôn không thể bị sửa nên đủ dùng”.

**Gợi ý:** Tính bất biến của các record **đã lưu** không chứng minh tính **đầy đủ và kịp thời**. Cần đo mất kết nối, heartbeat, drop/lag, buffer, phát hiện nguồn im lặng và điều tra phạm vi dữ liệu không còn dấu vết.

## Kết luận

**Chính sách logging** biến yêu cầu “có log” thành một hệ thống trách nhiệm và bằng chứng có thể kiểm chứng: **ghi đúng sự kiện, đúng danh tính và kết quả, đủ để truy vết nhưng không ghi thừa bí mật; bảo vệ đường truyền, kho lưu và quyền truy cập; duy trì retention, detection và kiểm tra cả khi logging bị lỗi**. Trong **SECURITY_SECURITY_ASSURANCE**, log hỗ trợ phát hiện, ứng cứu, audit và chứng minh hiệu quả controls, nhưng chỉ trong phạm vi mà nguồn, schema, coverage và tính toàn vẹn đã được xác minh. Một chương trình logging đáng tin phải có owner, chính sách/tiêu chuẩn rõ ràng, test đầu cuối, bằng chứng vận hành, quy trình khắc phục và đánh giá lại sau mỗi thay đổi quan trọng.
