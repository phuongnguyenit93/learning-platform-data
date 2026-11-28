# Nhật ký kiểm toán, che dữ liệu nhạy cảm và giới hạn bề mặt tấn công

Một Spring Cloud service broker đứng giữa platform và các hệ thống cung cấp tài nguyên. Broker nhận request để đọc catalog, provision, update, bind, unbind hoặc deprovision service instance; đồng thời giữ thông tin tenant, mapping tới provider resource, credentials và trạng thái operation. Vì vậy, broker cần bảo vệ cả API công khai, dữ liệu nội bộ, thông tin xác thực và các luồng gọi ra bên ngoài.

Ba nhóm kiểm soát bổ trợ cho nhau:

- **Nhật ký kiểm toán (audit log):** ghi lại ai hoặc thành phần nào đã thực hiện hành động gì, trên tài nguyên nào, vào thời điểm nào và kết quả ra sao.
- **Che dữ liệu nhạy cảm (redaction):** ngăn password, token, private key, credential và dữ liệu nhạy cảm xuất hiện trong log, audit event, trace hoặc error response.
- **Giới hạn bề mặt tấn công (attack surface reduction):** chỉ mở những endpoint và quyền cần thiết, giới hạn truy cập mạng, cấu hình, dependency và thao tác mà broker có thể thực hiện.

Audit log giúp điều tra và chứng minh hoạt động; redaction giảm nguy cơ lộ dữ liệu; hardening thu hẹp khả năng kẻ tấn công tiếp cận hoặc khai thác hệ thống. Một broker an toàn cần triển khai cả ba theo cùng một mô hình đe dọa và chính sách vận hành.

## 1. Xác định dữ liệu và tài sản cần bảo vệ

Trước khi thiết kế audit và logging, cần lập danh sách tài sản mà broker đang quản lý. Không phải mọi dữ liệu trong request đều có mức độ nhạy cảm như nhau.

| Tài sản | Ví dụ | Rủi ro khi bị lộ hoặc sửa |
|---|---|---|
| Broker credentials | Basic Auth secret, client secret, API token | Kẻ tấn công gọi API broker trái phép |
| Provider credentials | Cloud access key, client certificate, kubeconfig token | Truy cập hoặc phá hủy tài nguyên hạ tầng |
| Binding credentials | Database password, URI có mật khẩu, access token | Ứng dụng hoặc người không được phép truy cập backing service |
| Tenant context | Organization, space, project, tenant ID | Rò rỉ quan hệ giữa khách hàng và tài nguyên |
| Resource mapping | OSB instance ID, provider resource ID, account, region | Tấn công nhắm vào tài nguyên cụ thể hoặc thao tác nhầm |
| Operation state | Provision, update, deprovision operation | Làm sai lệch trạng thái và vòng đời dịch vụ |
| Audit history | Actor, hành động, thời gian, kết quả | Mất khả năng điều tra hoặc phủ nhận hành động |
| Service parameters | Database name, network setting, user metadata | Có thể chứa dữ liệu cá nhân hoặc secret do người dùng nhập |

Cần phân biệt dữ liệu định danh với dữ liệu xác thực. Instance ID hoặc tenant ID có thể không phải secret, nhưng vẫn có thể là dữ liệu nhạy cảm theo chính sách tổ chức. Provider resource ID có thể giúp người vận hành tìm tài nguyên, do đó cần giới hạn quyền đọc và tránh đưa vào metric label có cardinality cao.

Một nguyên tắc hữu ích là phân loại dữ liệu thành public, internal, confidential và secret. Mỗi mức cần quy định nơi được lưu, ai được đọc, thời gian lưu và cách xuất hiện trong log.

## 2. Phân biệt application log, audit log và security event

Ba loại bản ghi thường được dùng cùng nhau nhưng phục vụ mục đích khác nhau.

| Loại | Mục đích | Ví dụ |
|---|---|---|
| Application log | Chẩn đoán luồng thực thi và lỗi kỹ thuật | Provider call timeout, retry attempt |
| Audit log | Ghi lại hành động có ý nghĩa nghiệp vụ và trách nhiệm | Operator yêu cầu deprovision instance |
| Security event | Ghi nhận sự kiện liên quan tới xác thực, phân quyền hoặc dấu hiệu tấn công | Nhiều lần xác thực thất bại, truy cập bị từ chối |

Một log dòng thông báo "request received" chưa đủ để làm audit record. Audit cần có actor, action, target, thời điểm, kết quả và correlation reference. Ngược lại, audit log không nên trở thành bản sao của toàn bộ application log.

Ví dụ:

- Application log: provider adapter nhận HTTP 503 và sẽ retry sau 2 giây.
- Audit log: platform đã gửi yêu cầu provision cho instance X; broker chấp nhận operation Y.
- Security event: client credential không hợp lệ khi gọi endpoint broker.

Tách các loại bản ghi giúp đặt retention, quyền truy cập và mức chi tiết phù hợp. Application log có thể có khối lượng lớn; audit log thường cần tính toàn vẹn và lưu giữ theo chính sách; security event có thể cần cảnh báo gần thời gian thực.

## 3. Thiết kế audit event có cấu trúc

Audit event nên có schema ổn định để có thể tìm kiếm, tổng hợp và đối chiếu. Một event có thể chứa:

| Trường | Ý nghĩa |
|---|---|
| event_id | ID duy nhất của audit event |
| occurred_at | Thời điểm sự kiện xảy ra |
| actor_type | PLATFORM, USER, OPERATOR, SYSTEM hoặc WORKER |
| actor_id | Định danh actor đã được xác thực |
| action | PROVISION, UPDATE, BIND, UNBIND, DEPROVISION, LOGIN hoặc CONFIG_CHANGE |
| target_type | SERVICE_INSTANCE, SERVICE_BINDING, PLAN hoặc BROKER_CONFIG |
| target_id | ID mục tiêu phù hợp với chính sách dữ liệu |
| tenant_ref | Tham chiếu tenant đã được xác minh |
| outcome | ACCEPTED, SUCCEEDED, FAILED hoặc DENIED |
| reason_code | Mã lý do đã chuẩn hóa |
| operation_id | Operation liên quan nếu có |
| correlation_id | ID nối các log và trace liên quan |
| source | Thành phần hoặc endpoint tạo event |
| schema_version | Phiên bản schema audit |

Ví dụ event đã loại bỏ dữ liệu bí mật:

~~~json
{
  "event_id": "aud-01JQ8N6R",
  "occurred_at": "2026-11-27T10:30:15Z",
  "actor_type": "PLATFORM",
  "actor_id": "platform-prod-01",
  "action": "PROVISION",
  "target_type": "SERVICE_INSTANCE",
  "target_id": "instance-7f2a",
  "tenant_ref": "tenant-hmac-4b91",
  "outcome": "ACCEPTED",
  "reason_code": "ASYNC_OPERATION_ACCEPTED",
  "operation_id": "op-93d1",
  "correlation_id": "corr-a82c",
  "source": "osb-provision-handler",
  "schema_version": 1
}
~~~

Audit event không nên chứa password, token, full request body hoặc toàn bộ provider response. Nếu cần lưu một tham số để điều tra, hãy xác định rõ mục đích, phân loại dữ liệu và giới hạn quyền truy cập.

Actor phải được lấy từ danh tính đã xác thực hoặc từ metadata nội bộ đáng tin cậy. Không dùng trường actor_id do client tự gửi làm bằng chứng danh tính.

## 4. Ghi nhận hành động theo vòng đời OSB

Audit cần phản ánh các thao tác quan trọng của broker, không chỉ request HTTP.

| Hành động | Thời điểm nên ghi nhận |
|---|---|
| Catalog access | Khi cần theo dõi truy cập hoặc phát hiện lạm dụng; tránh ghi mọi lần đọc nếu khối lượng quá lớn |
| Provision | Khi request được chấp nhận, khi provider tạo tài nguyên và khi operation kết thúc |
| Update | Khi bắt đầu thay đổi plan/parameters và khi kết quả được xác minh |
| Bind | Khi binding được tạo và credentials/endpoint được cấp |
| Unbind | Khi quyền truy cập hoặc attachment được thu hồi |
| Deprovision | Khi nhận yêu cầu, khi provider xóa tài nguyên và khi hoàn tất |
| Authentication | Khi xác thực thất bại hoặc có dấu hiệu bất thường |
| Authorization | Khi thao tác bị từ chối do tenant hoặc quyền không phù hợp |
| Configuration change | Khi thay đổi catalog, provider routing, quota hoặc policy |
| Administrative action | Khi operator thực hiện retry, reconcile hoặc can thiệp thủ công |

Với thao tác bất đồng bộ, nên ghi nhận ít nhất hai mốc riêng:

1. Request được broker chấp nhận và operation ID được tạo.
2. Operation hoàn tất hoặc thất bại sau khi worker xử lý.

Có thể ghi thêm các transition quan trọng như provider request submitted, resource ready hoặc recovery required. Không cần ghi từng polling tick nếu không tạo giá trị điều tra; có thể dùng application log và metric cho các bước lặp nhiều lần.

Không ghi audit event SUCCEEDED chỉ vì provider trả HTTP 202. Broker chỉ đánh dấu thành công khi trạng thái tài nguyên đáp ứng tiêu chí hoàn tất.

## 5. Gắn audit với operation journal và transactional outbox

Audit record cần tồn tại ngay cả khi broker restart hoặc worker xử lý lại message. Nếu audit là yêu cầu bắt buộc cho một thay đổi nghiệp vụ, việc ghi audit nên được phối hợp transaction với thay đổi dữ liệu tương ứng.

Ví dụ khi tiếp nhận provision:

~~~text
BEGIN TRANSACTION
  INSERT service_instance (state = PROVISIONING)
  INSERT broker_operation (state = ACCEPTED)
  INSERT audit_event (action = PROVISION, outcome = ACCEPTED)
  INSERT outbox_event (type = ProvisionRequested)
COMMIT
~~~

Sau commit, broker mới trả HTTP 202 nếu platform đã chấp nhận asynchronous operation. Nếu transaction rollback, cả operation, audit event và outbox event đều không được coi là đã tiếp nhận.

Khi worker hoàn tất:

~~~text
BEGIN TRANSACTION
  UPDATE service_instance (state = ACTIVE)
  UPDATE broker_operation (state = SUCCEEDED)
  INSERT audit_event (action = PROVISION, outcome = SUCCEEDED)
COMMIT
~~~

Transactional outbox giúp chuyển event sang queue mà không tạo khoảng trống giữa database commit và publish. Audit event có thể được ghi cùng transaction hoặc được phát qua outbox tới audit sink. Nếu audit sink nằm ngoài database, cần thiết kế retry và dead-letter riêng; không giả định một lời gọi HTTP tới SIEM có thể commit nguyên tử với database broker.

Không để audit bắt buộc chỉ nằm trong một listener in-memory. Process có thể dừng sau commit trước khi listener gửi event. Nếu dùng event listener để đánh thức publisher, database outbox vẫn phải là nguồn dữ liệu bền vững.

## 6. Bảo đảm tính toàn vẹn và khả năng kiểm chứng của audit

Audit log chỉ hữu ích nếu người có quyền vận hành không thể âm thầm sửa hoặc xóa lịch sử mà không để lại dấu vết.

Các biện pháp có thể kết hợp:

- Dùng tài khoản database riêng cho ghi audit; ứng dụng thông thường không có quyền UPDATE hoặc DELETE bản ghi đã ghi.
- Dùng bảng append-only hoặc API chỉ cho phép insert.
- Chuyển bản sao audit tới hệ thống lưu trữ độc lập với quyền quản trị khác.
- Dùng storage có retention lock hoặc WORM khi yêu cầu tuân thủ đòi hỏi.
- Gắn chữ ký hoặc hash chain nếu cần phát hiện chỉnh sửa.
- Đồng bộ thời gian giữa broker, database và hệ thống log.
- Ghi audit cho hành động thay đổi cấu hình, quyền và retention policy.

Hash chain có thể tính từ hash của event hiện tại và hash event trước đó:

~~~text
event_hash = H(previous_hash || canonical_event)
~~~

Cách này giúp phát hiện một số dạng sửa hoặc xóa ở giữa chuỗi nếu bản hash neo được bảo vệ. Tuy nhiên, hash chain không đủ nếu cùng một kẻ tấn công có thể sửa toàn bộ event và tính lại toàn bộ hash. Cần lưu checkpoint hoặc bản sao hash ở một hệ thống có quyền quản trị độc lập.

Không nên tự tuyên bố audit là immutable chỉ vì bảng không có endpoint DELETE. Người có quyền trực tiếp trên database hoặc storage vẫn có thể thay đổi dữ liệu nếu không có lớp bảo vệ bổ sung.

## 7. Đồng bộ thời gian và thứ tự sự kiện

Audit cần thời gian đáng tin cậy để dựng lại trình tự thao tác. Nên:

- Dùng timestamp UTC theo định dạng chuẩn.
- Đồng bộ máy chủ bằng NTP hoặc dịch vụ thời gian được quản trị.
- Lưu thời điểm event xảy ra và thời điểm event được ghi nếu hai mốc khác nhau.
- Dùng operation sequence hoặc aggregate version khi cần xác định thứ tự trên cùng instance.
- Không dựa duy nhất vào timestamp để quyết định thứ tự khi nhiều node ghi đồng thời.

Ví dụ một worker có thể xử lý event muộn hơn nhưng ghi timestamp từ đồng hồ bị lệch. Sequence number hoặc version tăng đơn điệu theo instance giúp xác định transition hợp lệ.

Correlation ID nối các log trong một request; operation ID nối các request và worker trong suốt vòng đời thao tác. Hai ID này không thay thế event ID duy nhất của từng audit record.

## 8. Che dữ liệu nhạy cảm trước khi ghi log

Nguyên tắc quan trọng nhất là không đưa secret vào logging pipeline ngay từ đầu. Redaction là lớp bảo vệ bổ sung, không phải lý do để log toàn bộ request rồi cố che sau.

Các dữ liệu thường phải loại bỏ hoặc che:

- Authorization header, Basic Auth password và bearer token.
- API key, OAuth refresh token, client secret.
- Database password, JDBC URL có credential và connection string.
- Private key, certificate private material và kubeconfig token.
- Binding credentials, access token và signed URL có quyền truy cập.
- Cookie, session ID và CSRF token.
- Request parameter có thể chứa dữ liệu cá nhân hoặc secret.
- Provider response body có thể phản chiếu credential.

Ví dụ redaction:

~~~text
Authorization: Bearer [REDACTED]
password: [REDACTED]
client_secret: [REDACTED]
private_key: [REDACTED]
database_url: jdbc:postgresql://db.internal:5432/orders
~~~

Nếu cần biết một secret có thay đổi hay không, có thể lưu một fingerprint được tạo bằng HMAC với key quản lý riêng. Không dùng hash không khóa cho password hoặc token có entropy thấp, vì người đọc log có thể thử dò giá trị. Thông thường, broker không cần lưu fingerprint của secret trong audit; lưu secret reference hoặc phiên bản secret là đủ.

## 9. Allowlist tốt hơn denylist cho log request

Một cách nguy hiểm là serialize toàn bộ request rồi dùng regex để thay những key có tên password hoặc token. Secret có thể xuất hiện dưới tên khác, nằm sâu trong object, trong URL, nested JSON hoặc message exception.

Ưu tiên allowlist các field được phép ghi:

~~~java
public record SafeProvisionLog(
        String serviceInstanceId,
        String serviceId,
        String planId,
        String correlationId) {
}

SafeProvisionLog safe = new SafeProvisionLog(
        command.serviceInstanceId(),
        command.serviceId(),
        command.planId(),
        correlationId);

log.info("Provision request accepted: {}", safe);
~~~

Ví dụ này chỉ log các trường đã chọn. Không log command gốc nếu command có parameters mở hoặc có thể chứa credential.

Nếu buộc phải dùng redaction theo key, cần xử lý cả nested object, collection, header, query string và exception message. Regex đơn giản trên chuỗi JSON thường không đủ tin cậy. Redaction phải diễn ra trước khi dữ liệu đi tới appender, tracing exporter hoặc external log collector.

## 10. Redaction trong structured logging

Structured logging giúp hệ thống phân tích event theo field thay vì phải parse chuỗi tự do. Tuy nhiên, structured logging không tự làm dữ liệu an toàn.

Một log record phù hợp:

~~~json
{
  "timestamp": "2026-11-27T10:30:15Z",
  "level": "INFO",
  "event": "broker.provision.accepted",
  "service_instance_id": "instance-7f2a",
  "service_id": "postgres-service-id",
  "plan_id": "postgres-production-plan-id",
  "operation_id": "op-93d1",
  "correlation_id": "corr-a82c",
  "provider": "cloud-postgres"
}
~~~

Không nên log:

~~~json
{
  "event": "broker.binding.created",
  "username": "orders_app",
  "password": "actual-database-password",
  "authorization": "Bearer actual-token",
  "full_request": "..."
}
~~~

Các quy tắc nên được áp dụng thống nhất trong logging library hoặc wrapper:

- Chỉ nhận DTO đã được làm sạch cho log.
- Có danh sách field được phép.
- Redact header nhạy cảm ở HTTP client/server logging.
- Tắt body logging ở endpoint có secret nếu không có lý do rõ ràng.
- Kiểm soát exception serialization.
- Kiểm thử log output bằng dữ liệu giả có marker secret.

Không dựa vào cấu hình của log collector để che secret sau khi log đã rời khỏi process. Secret có thể đã được ghi vào file cục bộ, buffer, console hoặc agent trước khi tới collector.

## 11. Bảo vệ binding credentials và secret store

Khi bind database, broker có thể tạo username/password hoặc token rồi trả credentials cho platform. Các giá trị này thường được lưu ở platform hoặc chuyển cho ứng dụng.

Một số nguyên tắc:

- Sinh credential đủ mạnh bằng nguồn ngẫu nhiên an toàn.
- Mỗi binding nên có credential riêng nếu backing service hỗ trợ.
- Chỉ trả credential trong binding response cần thiết.
- Không ghi response binding vào application log hoặc audit.
- Không lưu password dạng rõ trong bảng service_binding.
- Lưu secret trong secret manager và chỉ giữ secret reference trong database.
- Thu hồi credential khi unbind.
- Xoay vòng credential theo chính sách và ghi audit sự kiện rotation mà không ghi giá trị secret.
- Giới hạn quyền đọc secret theo service account và tenant scope.

Ví dụ bản ghi binding chỉ lưu tham chiếu:

~~~json
{
  "binding_id": "binding-456",
  "service_instance_id": "instance-7f2a",
  "secret_reference": "secret://broker/bindings/binding-456",
  "state": "ACTIVE"
}
~~~

Secret reference cũng có thể nhạy cảm nếu nó tiết lộ cấu trúc tenant hoặc naming scheme. Hãy áp dụng quyền đọc phù hợp và không đưa nó vào public response nếu platform không cần.

## 12. Không để error response làm rò rỉ dữ liệu

Khi provider hoặc database lỗi, exception message có thể chứa URL, account, query, request body hoặc credential. Không nên trả nguyên message này cho platform.

Nên tách hai nội dung:

- Public error: mã lỗi ổn định, mô tả ngắn và correlation ID nếu cần.
- Internal diagnostic: exception cause, provider error code, stack trace đã kiểm soát và context không nhạy cảm.

Ví dụ response:

~~~json
{
  "error": "ServiceUnavailable",
  "description": "The service provider is temporarily unavailable. Reference: corr-a82c"
}
~~~

Log nội bộ có thể ghi provider error code và operation ID nhưng vẫn phải redaction. Không đưa stack trace vào trường description, không trả tên host nội bộ hoặc đường dẫn file cấu hình.

Cũng cần kiểm soát dữ liệu trả về từ validation. Nếu error message phản chiếu input do người dùng gửi, input đó có thể chứa secret hoặc dữ liệu độc hại. Hãy tạo message theo field và reason code, không echo toàn bộ giá trị.

## 13. Xác thực và phân quyền trên OSB endpoint

Service broker cần xác thực platform client trước khi cho phép truy cập endpoint. Cơ chế cụ thể phụ thuộc platform và cách triển khai broker; có thể là HTTP Basic Authentication, mTLS hoặc cơ chế xác thực được platform hỗ trợ.

Các nguyên tắc:

- Chỉ cho phép kết nối qua TLS trong môi trường triển khai.
- Lưu broker credential trong secret manager hoặc hệ thống quản lý secret.
- Không dùng chung credential cho môi trường development, staging và production.
- Xoay vòng credential và ghi audit metadata của lần rotation.
- Giới hạn quyền theo client hoặc platform nếu broker phục vụ nhiều platform.
- Áp dụng rate limit và theo dõi xác thực thất bại.
- Trả lỗi xác thực theo contract và chính sách bảo mật, không tiết lộ credential nào sai.

Authentication chỉ xác minh caller. Authorization vẫn phải kiểm tra caller có quyền thao tác service instance, binding hoặc tenant cụ thể hay không. Không được tin tenant ID trong request body như bằng chứng quyền sở hữu.

Với mỗi request vòng đời, broker cần kiểm tra mapping instance, tenant context đã xác minh, service/plan và trạng thái hiện tại. Một instance ID khó đoán không thay thế authorization.

## 14. Giới hạn bề mặt endpoint và management interface

Chỉ công khai những endpoint mà platform hoặc người vận hành thực sự cần.

Đối với OSB API:

- Chỉ expose các route theo phiên bản API được hỗ trợ.
- Bảo vệ catalog và lifecycle endpoint theo yêu cầu của platform.
- Không expose repository, debug controller hoặc internal worker endpoint ra mạng công khai.
- Giới hạn method HTTP theo contract.
- Kiểm tra content type, body size và request parsing.
- Đặt timeout và rate limit phù hợp.
- Không cho phép truy cập trực tiếp provider API thông qua một proxy endpoint tổng quát.

Với Spring Boot Actuator, chỉ expose các endpoint quản trị cần thiết. Các endpoint như env, configprops, heapdump, threaddump hoặc mappings có thể tiết lộ thông tin nhạy cảm hoặc cấu trúc nội bộ. Nếu cần health check, chỉ expose health/info tối thiểu theo chính sách; bảo vệ management port bằng network policy, authentication và firewall riêng.

Không nên chạy management endpoint trên cùng network zone công khai với OSB API nếu có thể tách riêng. Tắt debug mode và endpoint thử nghiệm trước khi triển khai production.

## 15. Bảo vệ provider integration và chống SSRF

Provider adapter thường gọi URL hoặc API của cloud provider, Kubernetes API hoặc hệ thống nội bộ. Đây là vùng cần kiểm soát để tránh Server-Side Request Forgery (SSRF) và truy cập mạng trái phép.

Các nguyên tắc:

- Provider endpoint lấy từ cấu hình đã quản trị, không lấy URL tùy ý từ request parameters.
- Dùng allowlist hostname, scheme và port khi cấu hình provider.
- Không cho người dùng gửi URL callback hoặc image reference rồi broker tự fetch nếu chưa kiểm tra.
- Chặn truy cập tới metadata endpoint hoặc địa chỉ link-local/private không được phép theo kiến trúc.
- Kiểm tra DNS resolution và redirect nếu client HTTP có thể theo redirect.
- Giới hạn egress network theo provider endpoint cần thiết.
- Dùng timeout, response size limit và TLS certificate validation.
- Không tắt hostname verification để "sửa nhanh" lỗi TLS.

Nếu broker hỗ trợ nhiều provider, mỗi adapter nên có cấu hình endpoint và network policy riêng. Một lỗi cấu hình ở adapter không nên cho phép request platform khiến broker gọi tới địa chỉ tùy ý.

## 16. Least privilege cho provider credential

Broker thường cần quyền tạo, cập nhật và xóa tài nguyên ở provider. Không nên cấp quyền quản trị toàn bộ tài khoản cloud nếu chỉ cần quản lý một loại dịch vụ.

Ví dụ:

| Adapter | Quyền nên giới hạn |
|---|---|
| Managed PostgreSQL | Tạo, đọc, sửa và xóa database instance trong project/region được phép |
| Kubernetes database operator | Tạo và quản lý đúng Custom Resource trong namespace cho phép |
| Object storage | Tạo bucket/prefix, cấu hình policy và xóa trong phạm vi được quản lý |
| Log ingestion | Tạo endpoint/token và thu hồi binding tương ứng |

Tách credential theo môi trường, provider và loại workload khi phù hợp. Dùng workload identity hoặc short-lived credential nếu provider hỗ trợ. Không lưu key lâu dài trong application.yml hoặc source control.

Nếu một broker quản lý nhiều tenant, cần xác định có dùng account provider chung hay account riêng theo tenant. Dù dùng mô hình nào, adapter phải kiểm tra tenant-to-provider-scope mapping trước khi gọi provider.

## 17. Giới hạn quyền truy cập database và dữ liệu nội bộ

Database broker chứa instance mapping, operation state, binding reference, audit và có thể chứa metadata tenant. Hãy áp dụng:

- Tài khoản database runtime chỉ có quyền cần thiết trên schema ứng dụng.
- Migration dùng tài khoản riêng, không dùng credential runtime có quyền DDL rộng.
- Audit table có quyền insert riêng và hạn chế update/delete.
- Secret không lưu dạng rõ trong bảng nghiệp vụ.
- Mã hóa kết nối tới database và storage.
- Backup được mã hóa và quyền restore được kiểm soát.
- Phân quyền truy vấn theo tenant ở service layer và, khi phù hợp, database row-level security.
- Dùng prepared statement hoặc ORM parameter binding để tránh SQL injection.

Không chỉ dựa vào việc repository nhận instance ID để bảo đảm phân tách tenant. Truy vấn cần ràng buộc cả instance ID và tenant scope đã xác minh. Với thao tác update/delete, kiểm tra số hàng ảnh hưởng và state transition để tránh thay đổi tài nguyên ngoài quyền.

## 18. Giới hạn request, abuse và resource exhaustion

Broker có thể bị lạm dụng bằng request quá lớn, tần suất cao hoặc thao tác tạo tài nguyên liên tục. Các biện pháp cần cân nhắc:

- Giới hạn kích thước HTTP body và số lượng parameters.
- Giới hạn số binding trên mỗi instance hoặc tenant.
- Rate limit theo client, tenant và loại thao tác.
- Giới hạn concurrency của provider calls và worker.
- Đặt quota cho số operation đang chạy.
- Áp dụng timeout và bulkhead để provider chậm không làm cạn thread/connection pool.
- Dùng backpressure trong reactive pipeline.
- Giới hạn số lần retry và thời gian retry tổng.
- Chặn payload lồng quá sâu hoặc collection quá lớn.
- Giám sát số request thất bại và pattern bất thường.

Rate limit và quota có mục đích khác nhau. Rate limit kiểm soát tốc độ request; quota kiểm soát lượng tài nguyên được cấp. Cần cả hai để giảm nguy cơ một client làm cạn năng lực xử lý hoặc tài nguyên cloud.

Không nên phản hồi lỗi quá chi tiết cho request bị rate limit nếu điều đó giúp kẻ tấn công dò cấu hình nội bộ. Có thể trả thông báo ổn định và ghi reason code trong security log.

## 19. Bảo vệ cấu hình, dependency và chuỗi cung ứng

Bề mặt tấn công còn đến từ cấu hình và dependency.

- Không commit secret vào repository hoặc file cấu hình mẫu.
- Dùng secret manager và phân quyền truy cập.
- Tách cấu hình theo môi trường; production không kế thừa credential development.
- Pin hoặc quản lý dependency qua BOM/lock strategy phù hợp.
- Theo dõi CVE và cập nhật Spring, Reactor, HTTP client, database driver và provider SDK.
- Quét dependency và container image trong CI.
- Dùng base image tối giản, cập nhật và chạy container bằng non-root user.
- Giới hạn Linux capabilities và filesystem write access.
- Ký và kiểm tra nguồn gốc artifact theo chính sách tổ chức.
- Bảo vệ pipeline deploy, registry và quyền thay đổi cấu hình.

Một provider SDK có quyền gọi cloud API rất rộng. Lỗ hổng hoặc dependency bị thay thế có thể biến broker thành điểm truy cập hạ tầng. Vì vậy cần quản lý dependency, quyền build và quyền deploy cùng với bảo mật runtime.

## 20. Bảo vệ log và audit storage

Audit log chứa thông tin về actor, tenant, tài nguyên và hành động. Nếu mọi người vận hành đều có thể đọc mọi audit record, log có thể trở thành nguồn rò rỉ dữ liệu.

Nên áp dụng:

- RBAC cho quyền xem, tìm kiếm, export và quản trị retention.
- Tách quyền ghi audit khỏi quyền xóa hoặc thay đổi retention.
- Mã hóa khi truyền và khi lưu.
- Giới hạn truy cập theo tenant hoặc phạm vi công việc khi phù hợp.
- Ghi audit cho thao tác đọc/export audit nếu yêu cầu.
- Chuyển bản sao tới hệ thống lưu trữ độc lập.
- Đặt retention theo mục đích, quy định và hợp đồng.
- Xóa hoặc ẩn danh dữ liệu khi hết thời hạn hợp lệ.
- Kiểm tra backup và khả năng phục hồi.

Không nên lưu dữ liệu vô thời hạn chỉ vì có thể hữu ích cho điều tra. Cần cân bằng yêu cầu audit với nguyên tắc tối thiểu hóa dữ liệu và chính sách lưu giữ.

## 21. Ví dụ triển khai AuditService trong Spring

Có thể định nghĩa một DTO chỉ chứa các trường audit được phép:

~~~java
public record AuditEvent(
        String eventId,
        Instant occurredAt,
        String actorType,
        String actorId,
        String action,
        String targetType,
        String targetId,
        String tenantReference,
        String outcome,
        String reasonCode,
        String operationId,
        String correlationId) {
}
~~~

Một service ghi event:

~~~java
@Service
public class AuditService {

    private final AuditEventRepository repository;
    private final Clock clock;

    public AuditService(
            AuditEventRepository repository,
            Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }

    public void record(AuditCommand command) {
        AuditEvent event = new AuditEvent(
                UUID.randomUUID().toString(),
                clock.instant(),
                command.actorType(),
                command.actorId(),
                command.action(),
                command.targetType(),
                command.targetId(),
                command.tenantReference(),
                command.outcome(),
                command.reasonCode(),
                command.operationId(),
                command.correlationId());

        repository.save(event);
    }
}
~~~

Đây là ví dụ đơn giản. Trong ứng dụng thực tế, cần quyết định AuditService tham gia transaction nào. Với audit bắt buộc gắn với một thay đổi nghiệp vụ, hãy ghi event cùng transaction hoặc dùng outbox. Nếu AuditService chỉ publish qua một executor in-memory, process có thể dừng trước khi event được lưu.

Clock được inject để kiểm thử thời gian dễ dàng và tránh phụ thuộc trực tiếp vào system clock trong logic nghiệp vụ. Actor và tenant reference phải được tạo từ security context đã xác minh.

## 22. Ví dụ redaction và kiểm thử không lộ secret

Có thể xây dựng log DTO riêng cho request binding:

~~~java
public record SafeBindingLog(
        String serviceInstanceId,
        String bindingId,
        String serviceId,
        String planId,
        String correlationId) {
}

SafeBindingLog safeLog = new SafeBindingLog(
        request.serviceInstanceId(),
        request.bindingId(),
        request.serviceId(),
        request.planId(),
        correlationId);

log.info("Service binding requested: {}", safeLog);
~~~

Không serialize BindingResponse vì response có thể chứa username, password, certificate hoặc URL có token.

Kiểm thử redaction nên dùng marker dễ tìm:

~~~text
password = TEST_SECRET_9f3a
token = TEST_TOKEN_8b21
~~~

Sau khi chạy request test, kiểm tra toàn bộ log output và xác nhận các marker không xuất hiện. Kiểm tra cả:

- Application log.
- HTTP request/response logging.
- Exception message.
- Trace span attributes.
- Audit event.
- Test report và CI artifact.

Không chỉ kiểm tra chuỗi đã được thay thành [REDACTED]; tốt hơn là xác nhận secret gốc hoàn toàn không xuất hiện ở bất kỳ sink nào.

## 23. Quy trình phản ứng khi phát hiện credential bị lộ

Nếu secret xuất hiện trong log hoặc audit, chỉ xóa dòng log không giải quyết được rủi ro vì bản sao có thể đã được gửi tới collector, backup hoặc hệ thống tìm kiếm.

Quy trình xử lý nên gồm:

1. Xác định loại secret, scope và thời gian có khả năng bị lộ.
2. Thu hồi hoặc rotate credential ở provider/platform.
3. Kiểm tra audit và access log để tìm hành vi sử dụng bất thường.
4. Giới hạn quyền truy cập tới log có chứa dữ liệu bị lộ.
5. Xử lý bản sao trong log storage, backup và export theo chính sách incident response.
6. Xác định nguồn ghi secret: request logger, exception, binding response hay provider SDK.
7. Sửa redaction/allowlist và thêm test ngăn tái diễn.
8. Ghi audit về việc rotate/revoke, chỉ lưu secret reference hoặc version, không lưu giá trị secret mới.
9. Đánh giá phạm vi ảnh hưởng tới tenant và tài nguyên.
10. Đóng sự cố sau khi xác minh credential cũ không còn hiệu lực và dữ liệu được xử lý theo quy định.

Không đưa giá trị secret bị lộ vào ticket, chat hoặc báo cáo sự cố. Dùng secret reference, fingerprint có khóa hoặc ID sự cố để trao đổi.

## 24. Threat modeling cho service broker

Một cách thực tế để rà soát bảo mật là liệt kê tài sản, actor, trust boundary và đường tấn công.

| Actor hoặc thành phần | Mối đe dọa | Kiểm soát chính |
|---|---|---|
| Platform client | Credential bị đánh cắp, request giả mạo | TLS, authentication, rotation, rate limit |
| Tenant/user | Truy cập instance tenant khác | Authorization, tenant scoping, audit |
| Application consumer | Lạm dụng binding credential | Credential riêng, secret store, revoke |
| Provider API | Outage, response độc hại hoặc timeout | Adapter validation, timeout, retry có kiểm soát |
| Malicious parameters | SSRF, injection, resource exhaustion | Schema validation, allowlist, size limits |
| Operator | Thay đổi cấu hình hoặc xóa audit | RBAC, separation of duties, audit integrity |
| Compromised dependency | Thực thi mã hoặc đánh cắp provider credential | Dependency scanning, least privilege, image hardening |
| Log pipeline | Rò rỉ hoặc sửa audit | Redaction, encryption, immutable copy, access control |

Có thể dùng STRIDE để đặt câu hỏi:

- Spoofing: caller có thể giả mạo platform hoặc tenant không?
- Tampering: request, operation state hoặc audit record có thể bị sửa không?
- Repudiation: có đủ audit để xác định ai đã thực hiện thao tác không?
- Information disclosure: secret có xuất hiện trong log, response hoặc trace không?
- Denial of service: một tenant có thể làm cạn worker, queue hoặc quota không?
- Elevation of privilege: broker/provider credential có quyền rộng hơn cần thiết không?

Threat model cần được cập nhật khi thêm provider, endpoint, capability hoặc loại binding mới.

## 25. Checklist triển khai production

**Audit và truy vết**

- [ ] Audit event có event ID, actor, action, target, timestamp, outcome và correlation reference.
- [ ] Actor được lấy từ security context đã xác thực.
- [ ] Provision, update, bind, unbind, deprovision và administrative action được ghi nhận.
- [ ] Operation accepted và operation completed/failed được phân biệt.
- [ ] Audit bắt buộc được ghi bền vững cùng transaction hoặc qua outbox.
- [ ] Quyền sửa/xóa audit được tách biệt và có bản sao độc lập.
- [ ] Timestamp được đồng bộ và có sequence/version khi cần.
- [ ] Retention, export và quyền đọc audit được quy định.

**Redaction và secret**

- [ ] Không log Authorization, cookie, password, token hoặc private key.
- [ ] Không log binding response hoặc provider response chứa credential.
- [ ] Dùng allowlist DTO cho structured logging.
- [ ] Redaction áp dụng trước mọi log/trace sink.
- [ ] Error description không chứa stack trace hoặc raw provider body.
- [ ] Secret được lưu trong secret manager; database giữ reference.
- [ ] Có test xác nhận marker secret không xuất hiện trong log, audit và trace.
- [ ] Có quy trình revoke/rotate khi phát hiện lộ secret.

**Attack surface**

- [ ] OSB endpoint được bảo vệ bằng TLS và authentication.
- [ ] Authorization kiểm tra tenant ownership ở mọi thao tác instance/binding.
- [ ] Management endpoint được giới hạn và bảo vệ riêng.
- [ ] Provider endpoint lấy từ cấu hình tin cậy, có egress allowlist.
- [ ] Không cho request tùy ý điều khiển URL mà broker fetch.
- [ ] Provider credentials theo least privilege và tách môi trường.
- [ ] Request size, rate, concurrency và retry có giới hạn.
- [ ] Database runtime có quyền tối thiểu và kết nối được mã hóa.
- [ ] Dependency, container image và deployment pipeline được kiểm soát.
- [ ] Có cảnh báo cho authentication failure, authorization denial và hành vi bất thường.

Audit log, redaction và hardening phải được thiết kế cùng nhau. Audit cung cấp bằng chứng về hành động và kết quả; redaction bảo vệ dữ liệu trong quá trình ghi và phân tích; giới hạn bề mặt tấn công giảm khả năng truy cập trái phép vào broker và provider. Khi các kiểm soát này gắn với operation journal, tenant authorization, secret management và quy trình vận hành, service broker có thể hỗ trợ vòng đời dịch vụ mà vẫn giữ được khả năng truy vết và bảo vệ tài nguyên.

