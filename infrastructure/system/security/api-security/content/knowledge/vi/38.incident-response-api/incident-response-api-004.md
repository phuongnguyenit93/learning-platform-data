# Bảo toàn request, audit và dependency evidence

Khi API gặp sự cố bảo mật, nhóm ứng cứu cần trả lời được những câu hỏi cơ bản: request nào đã xảy ra, ai hoặc workload nào gửi request, gateway và application đã quyết định gì, dữ liệu nào bị đọc hoặc thay đổi, dependency nào đã tham gia và credential/policy nào có hiệu lực tại thời điểm đó. Nếu log bị ghi đè, trace bị sampling mất, queue message bị xóa, cấu hình gateway đã thay đổi hoặc secret version không còn truy vết được, việc xác định phạm vi và nguyên nhân sẽ khó khăn hơn nhiều.

Bảo toàn evidence là một phần của incident response API. Mục tiêu là giữ lại dữ liệu đủ tin cậy để dựng timeline, xác định tác động, kiểm chứng giả thuyết và hỗ trợ khắc phục. Evidence phải có nguồn gốc, tính toàn vẹn, quyền truy cập và thời hạn lưu rõ ràng. Việc thu thập cũng cần bảo vệ dữ liệu cá nhân, token, API key và nội dung nghiệp vụ nhạy cảm.

Không phải mọi log đều là bằng chứng hoàn chỉnh. Access log có thể thiếu body; trace có thể bị sampling; application log có thể bị sửa bởi workload bị xâm nhập; timestamp giữa các region có thể lệch; provider bên ngoài có thể chỉ giữ request ID trong thời gian ngắn. Cần kết hợp nhiều nguồn độc lập, ghi rõ giới hạn và giữ nguyên dữ liệu gốc khi có thể.

## 1. Evidence trong sự cố API là gì?

Evidence là dữ liệu hoặc artifact giúp xác minh một sự kiện, quyết định bảo mật hoặc thay đổi trạng thái. Trong hệ thống API, evidence có thể đến từ edge, gateway, identity provider, application, database, queue, service mesh, cloud control plane và hệ thống bên ngoài.

| Nhóm evidence | Ví dụ | Câu hỏi có thể hỗ trợ trả lời |
|---|---|---|
| Request/response | Method, route, timestamp, status, request ID, body hash | Request nào đã đến và server phản hồi ra sao? |
| Authentication | Issuer, client ID, token ID đã giả danh hóa, kết quả xác minh | Credential nào được chấp nhận hoặc từ chối? |
| Authorization | Principal, action, object reference, tenant, policy version, decision | Vì sao request được phép hoặc bị chặn? |
| Gateway/WAF | Route, rule ID, decision, upstream, rate limit | Request đi qua lớp edge nào và bị rule nào xử lý? |
| Application | Trace ID, operation ID, validation result, state transition | Logic nghiệp vụ đã thực hiện điều gì? |
| Database | Audit record, transaction ID, commit time, row/version reference | Dữ liệu nào đã thay đổi và transaction có commit không? |
| Queue/event | Topic, partition, offset, message ID, retry/DLQ metadata | Event nào được phát, nhận, retry hoặc xử lý? |
| Dependency | Provider request ID, DNS, TLS, JWKS, secret version metadata | Thành phần bên ngoài hoặc cấu hình nào đã tham gia? |
| Deployment/config | Image digest, release ID, config/policy hash, feature flag version | Code và policy nào đang chạy? |
| Cloud/control plane | IAM event, security group, KMS event, workload identity | Hạ tầng hoặc quyền nào đã thay đổi? |

### 1.1. Phân biệt log, trace, metric và audit

- **Log** ghi sự kiện hoặc thông điệp tại một thành phần. Log có thể thiếu ngữ cảnh và dễ bị ghi quá nhiều dữ liệu nhạy cảm.
- **Trace** liên kết các span của một request qua nhiều service. Trace hữu ích để hiểu đường đi và latency, nhưng thường có sampling và không phải lúc nào cũng đầy đủ.
- **Metric** tổng hợp số lượng, tỷ lệ hoặc độ trễ. Metric tốt để phát hiện bất thường nhưng thường không đủ để xác định một request cụ thể.
- **Audit record** ghi hành động có ý nghĩa bảo mật hoặc nghiệp vụ với actor, action, target, thời điểm và kết quả. Audit cần kiểm soát sửa/xóa và quyền đọc chặt hơn log vận hành thông thường.

Không dùng trace thay audit cho thao tác nhạy cảm. Nếu trace sampling bỏ mất request hoặc span bị rút gọn, audit record vẫn cần tồn tại cho action được quy định phải audit.

## 2. Xác định phạm vi và thứ tự bảo toàn

Trong incident response, evidence có thể biến mất nhanh do log rotation, retention ngắn, queue acknowledgement, cache eviction, autoscaling, pod restart hoặc provider retention. Cần ưu tiên nguồn dễ mất và có giá trị cao.

Thứ tự tham khảo:

1. Ghi nhận thời điểm phát hiện, người phát hiện, incident ID và phạm vi nghi ngờ.
2. Xác định các service, endpoint, tenant, credential và dependency có liên quan.
3. Bảo toàn log/trace/audit đang có nguy cơ bị xoay vòng hoặc xóa.
4. Chụp snapshot phù hợp của queue, database, workload hoặc cấu hình trước khi thay đổi nếu điều đó không làm chậm containment nguy cấp.
5. Ghi lại trạng thái runtime, deployment, policy, secret version metadata và hạ tầng.
6. Yêu cầu provider hoặc đối tác giữ evidence theo request ID và khoảng thời gian cụ thể.
7. Sau khi evidence quan trọng được giữ, tiến hành containment, revoke credential, vá lỗi hoặc cô lập hệ thống theo mức độ khẩn cấp.
8. Ghi lại mọi thao tác ứng cứu vì chính các thao tác đó cũng làm thay đổi trạng thái hệ thống.

An toàn con người, dữ liệu và hệ thống đang bị tấn công luôn được ưu tiên. Không trì hoãn việc chặn hành vi gây hại chỉ để thu thập một artifact không thiết yếu. Khi cần containment ngay, ghi rõ dữ liệu nào chưa thể thu thập và vì sao.

### 2.1. Xác định cửa sổ thời gian

Không chỉ lấy vài phút quanh alert. Một sự cố có thể bắt đầu từ lần credential bị lộ, request dò tìm đầu tiên hoặc thay đổi policy trước khi có alert.

Xác định:

- Thời điểm sớm nhất có dấu hiệu đáng tin.
- Thời điểm phát hiện và thời điểm bắt đầu containment.
- Khoảng thời gian credential/key có thể đã bị lộ.
- Thời hạn lưu của từng nguồn log.
- Thời điểm deploy, config change, key rotation hoặc policy change gần sự cố.
- Khoảng thời gian sau containment để xác nhận hành vi đã dừng.

Khi chưa biết chính xác thời điểm bắt đầu, lấy cửa sổ rộng hơn theo retention và thu hẹp bằng correlation. Ghi rõ giả định và lý do chọn cửa sổ.

### 2.2. Phạm vi theo request và dependency

Một request API có thể đi qua nhiều lớp:

~~~mermaid
flowchart LR
    C[Client] --> E[CDN / WAF / Edge]
    E --> G[API Gateway]
    G --> I[Identity / Policy]
    G --> A[Application]
    A --> D[Database]
    A --> Q[Queue / Event bus]
    A --> U[Upstream provider]
    A --> S[Secret manager / KMS]
    E --> L[Central evidence store]
    G --> L
    I --> L
    A --> L
    D --> L
    Q --> L
    U --> P[Provider evidence request]
    S --> L
~~~

Danh sách nguồn cần bảo toàn phụ thuộc vào đường đi thực tế. Ví dụ, request bị WAF chặn có thể chưa đến application; webhook có thể đi vào queue rồi mới xử lý; service-to-service call có thể dùng mTLS và không đi qua public gateway.

## 3. Bảo toàn request và response evidence

Request evidence giúp dựng lại caller, endpoint, thời điểm, context và kết quả. Tuy nhiên, lưu toàn bộ request/response body vô thời hạn có thể tạo thêm một kho dữ liệu nhạy cảm. Thiết kế cần xác định trước trường nào được ghi, trường nào phải redact và khi nào cần giữ raw artifact có kiểm soát.

### 3.1. Metadata request tối thiểu

Các trường thường hữu ích:

| Trường | Mục đích | Lưu ý |
|---|---|---|
| Timestamp và time source | Đặt request vào timeline | Lưu UTC và nguồn timestamp |
| Request/correlation/trace ID | Liên kết các thành phần | ID phải được truyền qua gateway và service |
| HTTP method và route template | Xác định action | Ưu tiên route template thay vì path chứa ID nhạy cảm |
| Host/service/environment | Xác định đích xử lý | Không lộ topology nội bộ ra response |
| Source IP/network | Điều tra nguồn | Chỉ tin forwarded IP từ proxy được cấu hình |
| TLS metadata | Xác định kết nối | Ghi protocol, peer identity hoặc certificate fingerprint phù hợp |
| Content type và body size | Phân tích request | Tránh lưu body không cần thiết |
| Body hash | Đối chiếu tính toàn vẹn | Hash không thay thế bằng chứng nguồn |
| Authentication result | Biết credential có được chấp nhận | Không ghi token nguyên văn |
| Principal/client reference | Liên kết caller | Dùng ID nội bộ hoặc giá trị giả danh hóa |
| Tenant/object reference | Xác định phạm vi dữ liệu | Chỉ ghi mức cần thiết, tuân thủ privacy policy |
| Authorization decision | Giải thích quyết định | Ghi action, policy version và reason code |
| Response status và size | Biết kết quả HTTP | Không ghi response body nhạy cảm mặc định |
| Upstream/operation ID | Liên kết downstream | Không ghi credential trong URL/header |

### 3.2. Header cần giữ và header cần loại bỏ

Có thể cần giữ các header như request ID, content type, user agent, forwarded metadata từ proxy tin cậy và provider event ID. Các header thường cần redact hoặc tuyệt đối không ghi nguyên văn:

- `Authorization`.
- `Cookie` và `Set-Cookie`.
- API key header.
- Proxy authorization.
- Header chứa session token, password hoặc client secret.
- Header nội bộ mang dữ liệu cá nhân không cần thiết.

Nên dùng allowlist header được phép ghi thay vì log toàn bộ header rồi cố gắng redact về sau. Redaction cần được kiểm thử vì header có thể thay đổi tên, viết hoa/thường hoặc xuất hiện lặp.

### 3.3. Body và raw request

Với nhiều API, metadata và body hash là đủ cho điều tra ban đầu. Khi cần bảo toàn raw body, ví dụ webhook signature hoặc giao dịch có tranh chấp:

- Chỉ thu thập trong phạm vi và thời gian cần thiết.
- Mã hóa khi truyền và khi lưu.
- Tách quyền đọc raw payload khỏi quyền đọc metadata.
- Ghi hash SHA-256 của đúng byte sequence được lưu.
- Ghi content type, encoding, size và thời điểm capture.
- Không sửa hoặc normalize bản gốc.
- Tạo bản làm việc đã redact riêng nếu analyst cần phân tích.
- Đặt retention và legal hold theo quy định.

Không ghi access token, password, API secret hoặc private key vào evidence body. Nếu raw body có credential hoặc PII không thể loại bỏ mà vẫn giữ giá trị chứng cứ, lưu trong vùng evidence restricted, kiểm soát truy cập theo case và ghi audit mọi lần mở.

### 3.4. Hash body trong ứng dụng Java

Ví dụ tính SHA-256 trên raw bytes đã được capture:

~~~java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(rawRequestBody);

String bodySha256 = HexFormat.of().formatHex(digest);
~~~

Hash giúp phát hiện artifact thay đổi khi đối chiếu. Nó không chứng minh ai đã gửi request hoặc artifact được capture ở đâu. Cần liên kết hash với request ID, capture source, timestamp, người/agent thu thập và manifest được bảo vệ. Không hash một JSON đã parse/serialize lại nếu mục tiêu là đối chiếu với raw bytes ban đầu.

### 3.5. Response evidence

Ghi status, response timestamp, response size, response header được allowlist, error code và operation state. Với thao tác ghi, cần ghi thêm transaction/operation ID và kết quả commit. Không lưu response chứa PII hoặc secret đầy đủ nếu không cần. Nếu cần giữ artifact gốc, áp dụng cùng yêu cầu mã hóa, hash, access control và retention như request body.

## 4. Bảo toàn authentication và authorization audit

Trong sự cố API, câu hỏi “ai đã gửi request?” và “vì sao request được phép?” cần được trả lời độc lập. Token có thể đã được xác minh nhưng policy sai; principal có thể đúng nhưng tenant context bị giả; gateway có thể ghi nhận 200 nhưng application đã từ chối object-level authorization.

### 4.1. Authentication evidence

Nên lưu:

- Authentication mechanism và issuer/provider.
- Client ID hoặc workload identity.
- Token ID (`jti`) hoặc fingerprint đã giả danh hóa nếu phù hợp.
- Key ID (`kid`) hoặc certificate fingerprint.
- Kết quả validation và reason code nội bộ.
- Thời điểm xác thực và policy/config version.
- Trạng thái revocation/introspection nếu có.
- Gateway/application instance xử lý request.

Không lưu raw access token, refresh token, API key hoặc private key. Nếu cần chứng minh một credential cụ thể đã được dùng, hãy dùng identifier/fingerprint được thiết kế để không thể dùng lại như credential.

### 4.2. Authorization evidence

Với action nhạy cảm, audit record nên có:

- Actor hoặc service principal.
- Tenant context đã được xác minh.
- Action/function được yêu cầu.
- Object reference hoặc loại resource.
- Policy/role/scope version.
- Decision: allow/deny.
- Reason code ở mức có thể điều tra.
- Request ID, operation ID và thời điểm.
- Kết quả side effect hoặc transaction.

Tránh lưu toàn bộ object data vào audit. Dùng object ID nội bộ hoặc reference phù hợp và áp dụng quyền truy cập theo mức nhạy cảm.

### 4.3. Bảo toàn bằng chứng policy

Một quyết định authorization chỉ có thể hiểu đúng nếu biết policy nào đang có hiệu lực. Giữ:

- Policy bundle/version/hash.
- Role/permission mapping version.
- Tenant membership version hoặc trạng thái liên quan.
- Feature/config version nếu có ảnh hưởng đến endpoint.
- Gateway route/WAF rule version.
- Thời điểm policy được nạp vào instance.

Không chỉ giữ policy hiện tại sau sự cố. Cần giữ version đã có hiệu lực tại thời điểm request, vì policy có thể đã thay đổi trong quá trình containment.

## 5. Bảo toàn log, trace và audit trail

Log, trace và audit cần được thu thập từ nhiều lớp nhưng phải giữ nguyên nguồn và ngữ cảnh. Khi một service bị nghi xâm nhập, log ngay trên service đó có thể không còn đáng tin tuyệt đối; hãy đối chiếu với gateway, broker, cloud audit hoặc hệ thống lưu trữ độc lập.

### 5.1. Log vận hành

Giữ log của:

- CDN/WAF/edge.
- API gateway/load balancer.
- Identity provider/token service.
- Application và worker.
- Service mesh/sidecar.
- Database, cache và message broker.
- Secret manager/KMS.
- Cloud control plane và deployment platform.

Thu thập file/log stream gốc khi có thể, kèm nguồn, log group, partition, time range, filter/query và thời điểm export. Không chỉ lưu ảnh chụp dashboard hoặc kết quả grep đã lọc mà không giữ truy vấn và nguồn gốc.

### 5.2. Distributed trace

Trace giúp liên kết request qua gateway, service và upstream. Bảo toàn:

- Trace ID và span ID.
- Parent/child relationship.
- Service name, version và instance.
- Start/end timestamp và duration.
- Status/error attributes.
- Peer service và dependency target đã được chuẩn hóa.
- Sampling decision và collector/exporter metadata.

Trace có thể bị sampling hoặc span bị mất khi collector quá tải. Ghi rõ trace completeness; không suy luận “không có span” nghĩa là “không có request”. Nếu action nhạy cảm cần audit đầy đủ, tạo audit event độc lập với tracing.

### 5.3. Audit trail bất biến

Với audit quan trọng, dùng kho lưu trữ có kiểm soát sửa/xóa, ví dụ append-only, write-once retention hoặc object lock phù hợp. Bảo vệ:

- Quyền ghi audit tách khỏi quyền đọc/xóa.
- Workload không thể xóa audit của chính nó.
- Admin thay đổi retention/lock phải được audit.
- Replication sang vùng/tài khoản bảo vệ độc lập khi phù hợp.
- Hash/checksum hoặc cơ chế integrity verification.
- Monitoring khi audit pipeline dừng hoặc có gap.

Không tuyên bố log là “immutable” chỉ vì nó nằm trong object storage. Cần kiểm tra retention lock, quyền quản trị, khả năng xóa bởi account cấp cao và quy trình kiểm toán.

## 6. Bảo toàn dependency evidence

API thường phụ thuộc vào nhiều hệ thống khác nhau. Một sự cố có thể xuất phát từ dependency hoặc bị khuếch đại bởi dependency. Cần giữ bằng chứng của các thành phần đã tham gia, kể cả khi chúng không nằm trong quyền quản trị trực tiếp của đội API.

### 6.1. Gateway, WAF và edge

Thu thập:

- Route và upstream mapping có hiệu lực.
- WAF rule ID, action và version.
- Rate-limit decision, bucket dimension ở dạng không nhạy cảm.
- TLS termination metadata và certificate version.
- Request ID, edge location và timestamp.
- Config deployment/rollback event.
- IP allowlist, origin access rule và security group liên quan.

Nếu gateway đã đổi config sau incident, giữ snapshot/version cũ và thời điểm thay đổi. Không chỉ export cấu hình hiện tại.

### 6.2. Identity provider, JWKS và key management

Giữ:

- Issuer metadata và JWKS document version/hash.
- `kid` được dùng để xác minh token.
- Thời điểm publish/remove public key.
- JWKS cache age/refresh result của resource server nếu có.
- Token introspection result metadata, không gồm token.
- Signing key rotation/revoke event.
- KMS/HSM key ID, version, operation metadata và access audit.

Không export private key hoặc secret value để “giữ bằng chứng”. Thay vào đó, bảo toàn key identifier, version, policy, access event và kết quả thao tác. Nếu private key đã bị compromise, việc xử lý key phải theo incident procedure và quyền quản trị chuyên biệt.

### 6.3. Secret manager

Evidence hữu ích gồm:

- Secret path/reference và version ID.
- Workload identity đọc secret.
- Thời điểm, action và kết quả allow/deny.
- Token/lease issue, renew, revoke metadata.
- Policy/auth method/role version.
- Secret rotation event và change reference.
- Audit sink status.

Không ghi secret value, AppRole SecretID, Vault token hoặc cloud credential vào evidence package. Nếu cần xác định credential nào đã được dùng, liên kết secret version với outbound request ID và provider account reference mà không sao chép giá trị secret.

### 6.4. Database và data store

Thu thập:

- Database audit log và authentication event.
- Transaction ID, commit/rollback result và thời điểm.
- Query template hoặc operation name; redact literal chứa PII/secret.
- Object ID/tenant reference cần thiết.
- Row/version hoặc change data capture reference nếu có.
- Backup/snapshot/WAL/binlog metadata theo khả năng.
- Database role, grants và thay đổi schema/permission.

Không chạy truy vấn điều tra có thể thay đổi dữ liệu. Nếu cần snapshot, ghi rõ snapshot ID, consistency point và cách tạo. Cân nhắc dữ liệu đang thay đổi trong lúc capture; snapshot không nhất thiết đại diện cho trạng thái tại thời điểm request.

### 6.5. Queue và event bus

Giữ:

- Topic/queue, partition và offset/sequence.
- Message ID, event ID, correlation ID.
- Producer/consumer identity.
- Publish/consume/ack timestamp.
- Delivery count, retry schedule và DLQ reason.
- Schema version, payload hash và verification metadata.
- Broker ACL/config change và retention setting.

Nếu message chứa raw webhook hoặc PII, lưu theo quyền restricted. Không replay message trong quá trình thu thập chỉ để xem handler hoạt động; replay có thể tạo side effect. Dùng bản sao cách ly hoặc môi trường phân tích không có quyền ghi production.

### 6.6. Upstream provider và đối tác

Ghi nhận:

- Provider name, account reference và API version.
- Provider request/correlation ID.
- Endpoint/operation, timestamp và response status.
- TLS peer/certificate metadata khi cần.
- Retry/timeout/response body hash.
- Webhook event ID, delivery ID và signature key ID.
- Ticket hoặc yêu cầu preservation gửi provider, người nhận và thời điểm.

Provider có thể có retention ngắn. Gửi yêu cầu giữ evidence sớm, nêu rõ request ID, account, khoảng thời gian và loại log cần bảo toàn. Không gửi token, secret hoặc dữ liệu khách hàng không cần thiết trong yêu cầu hỗ trợ.

### 6.7. DNS, TLS và network evidence

Với sự cố liên quan routing, SSRF, certificate hoặc giả mạo upstream, giữ:

- DNS query/response, resolver và TTL.
- Record trước/sau thay đổi và thời điểm propagation.
- TLS version, cipher, certificate chain/fingerprint và SNI.
- mTLS client identity hoặc peer certificate metadata.
- Firewall/security group/network flow log.
- Proxy egress destination và policy decision.
- Service mesh route/identity/authorization event.

DNS và certificate có thể thay đổi nhanh. Lưu snapshot hoặc metadata tại thời điểm liên quan; truy vấn DNS hiện tại không chứng minh hostname đã resolve ra cùng IP trong quá khứ.

## 7. Đồng bộ thời gian và dựng timeline

Distributed system có nhiều clock: client, edge, gateway, container, database, broker và provider. Timestamp không đồng bộ có thể khiến điều tra đảo ngược thứ tự sự kiện.

### 7.1. Chuẩn hóa thời gian

- Lưu timestamp chuẩn UTC, có timezone rõ ràng.
- Giữ timestamp gốc từ source; không ghi đè bằng thời điểm ingest.
- Ghi thêm collector/ingest timestamp khi nhận dữ liệu.
- Theo dõi NTP source và clock offset của node.
- Ghi monotonic duration cho latency nếu hệ thống hỗ trợ.
- Không giả định timestamp của client đáng tin.
- Ghi rõ độ chính xác và giới hạn clock skew.

### 7.2. Timeline có nguồn và mức tin cậy

Một timeline tốt ghi:

| Thời điểm UTC | Sự kiện | Nguồn | Correlation | Độ tin cậy/ghi chú |
|---|---|---|---|---|
| 10:00:01.120 | Edge nhận request | WAF log | request ID | Timestamp edge |
| 10:00:01.145 | Gateway xác minh token | Gateway audit | request ID | `kid` và issuer đã giả danh hóa |
| 10:00:01.170 | Authorization allow | Policy audit | request ID | Policy version 42 |
| 10:00:01.220 | Database commit | DB audit | transaction ID | Commit đã xác nhận |
| 10:00:01.250 | Provider timeout | Outbound trace | operation ID | Kết quả phía provider chưa rõ |

Các giá trị trên chỉ là ví dụ. Nếu một nguồn có clock lệch 500 ms, ghi độ lệch đó thay vì tự điều chỉnh timestamp mà không giữ bản gốc. Timeline có thể biểu diễn khoảng thời gian hoặc thứ tự tương đối khi không thể xác định chính xác.

### 7.3. Correlation ID không phải bằng chứng danh tính

Request ID, trace ID và correlation ID giúp liên kết record nhưng có thể do client gửi hoặc bị tái sử dụng nếu hệ thống không tạo lại ở trust boundary. Gateway nên tạo hoặc xác minh ID theo quy tắc, đồng thời ghi cả ID client gửi và ID nội bộ đã cấp nếu cần. Không dùng correlation ID làm authorization credential.

## 8. Chain of custody và tính toàn vẹn evidence

Chain of custody ghi lại evidence được tạo, thu thập, chuyển giao, truy cập, phân tích và lưu trữ bởi ai, khi nào và bằng công cụ nào. Mục tiêu là chứng minh artifact không bị thay đổi ngoài kiểm soát và có thể truy vết mọi thao tác.

### 8.1. Thông tin cần có cho mỗi artifact

- Evidence ID duy nhất.
- Incident/case ID.
- Tên và mô tả artifact.
- Hệ thống/source, tenant hoặc account liên quan.
- Khoảng thời gian và timezone.
- Collector identity và người phê duyệt nếu cần.
- Tool/version và query/filter dùng để export.
- Thời điểm capture và ingest.
- Kích thước, định dạng và SHA-256 hash.
- Storage location và classification.
- Access history, transfer và analysis copy reference.
- Retention/legal hold state.

### 8.2. Manifest mẫu

~~~json
{
  "incidentId": "INC-2026-0042",
  "evidenceId": "EV-00017",
  "source": "api-gateway-audit",
  "sourceAccount": "prod-platform",
  "timeRange": {
    "from": "2026-11-18T02:00:00Z",
    "to": "2026-11-18T02:30:00Z"
  },
  "capturedAt": "2026-11-18T03:10:00Z",
  "collector": "incident-response-role",
  "tool": "approved-log-exporter",
  "artifact": "gateway-audit-part-01.ndjson",
  "sizeBytes": 184320,
  "sha256": "example-digest-placeholder",
  "classification": "restricted",
  "original": true
}
~~~

Digest trong ví dụ là placeholder, không phải hash thực. Manifest nên được lưu cùng artifact hoặc trong evidence registry có kiểm soát. Hash cần được tính trên đúng file bytes sau export; nếu file được nén/chuyển đổi, giữ hash của cả bản gốc và bản dẫn xuất.

### 8.3. Hash, signature và timestamp

SHA-256 giúp phát hiện file thay đổi khi so sánh với digest đã ghi nhận. Tuy nhiên, attacker có thể sửa cả file lẫn manifest nếu cùng có quyền ghi. Tăng độ tin cậy bằng cách:

- Lưu manifest ở kho tách quyền hoặc append-only.
- Ký manifest bằng signing identity riêng.
- Dùng trusted timestamp hoặc hệ thống audit độc lập khi yêu cầu.
- Bảo vệ key ký manifest trong KMS/HSM.
- Kiểm tra hash khi ingest, khi chuyển giao và trước phân tích.
- Giữ bản gốc read-only; phân tích trên working copy.

Không dùng hash như bằng chứng duy nhất về nguồn gốc. Hash chỉ chứng minh tính nhất quán của bytes so với digest đã tin cậy; nguồn, thời điểm và chain of custody cần được ghi riêng.

### 8.4. Bản gốc và bản phân tích

Giữ nguyên artifact gốc sau khi thu thập. Nếu cần parse, redact, normalize hoặc enrich:

1. Tạo working copy.
2. Ghi parent evidence ID và hash của bản gốc.
3. Ghi công cụ/version và thao tác biến đổi.
4. Tính hash cho bản dẫn xuất.
5. Không ghi đè bản gốc.

Điều này giúp analyst có thể lặp lại phân tích và phân biệt dữ liệu source với diễn giải của nhóm ứng cứu.

## 9. Bảo vệ dữ liệu cá nhân và secret trong evidence

Evidence có thể chứa dữ liệu khách hàng, dữ liệu thanh toán, token, API key, session cookie hoặc thông tin định danh. Việc bảo toàn không có nghĩa thu thập không giới hạn.

### 9.1. Data minimization

- Thu thập đúng endpoint, tenant, thời gian và field cần điều tra.
- Dùng principal/object reference đã giả danh hóa nếu không cần giá trị trực tiếp.
- Redact PII khỏi working copy và dashboard.
- Chỉ giữ raw payload khi có lý do cụ thể.
- Tách metadata ít nhạy cảm khỏi artifact raw restricted.
- Áp dụng retention và deletion theo policy/legal hold.

### 9.2. Không làm lộ credential

Không đưa các giá trị sau vào manifest, ticket, chat hoặc log thông thường:

- Access/refresh token.
- API key và client secret.
- Password, session cookie.
- Private signing key.
- Vault token, AppRole SecretID.
- Database password hoặc cloud credential.

Khi điều tra credential usage, dùng token ID, key ID, certificate fingerprint, secret version ID hoặc hash/fingerprint an toàn. Nếu phải bảo toàn credential bị lộ như artifact, lưu trong restricted evidence store với quyền đặc biệt; không sao chép sang report thông thường.

### 9.3. Encryption và access control

Evidence cần được mã hóa khi truyền và lưu. Quyền đọc nên theo incident role và case assignment. Tách quyền:

- Collector có thể export nhưng không tự xóa evidence.
- Analyst có thể đọc working copy nhưng không sửa bản gốc.
- Incident commander phê duyệt phạm vi truy cập.
- Custodian quản lý retention, transfer và legal hold.
- Auditor có thể kiểm tra access history mà không cần đọc raw secret.

Mọi lần truy cập artifact restricted cần audit. Không dùng một bucket hoặc share chung có quyền rộng cho toàn bộ engineering team.

## 10. Quy trình thu thập evidence theo giai đoạn

### 10.1. Giai đoạn phát hiện và triage

1. Mở incident/case ID và chỉ định incident commander.
2. Ghi thời điểm phát hiện, alert source và người báo cáo.
3. Xác định API/service/tenant/credential có khả năng liên quan.
4. Ghi lại request ID, trace ID, provider event ID hoặc transaction ID từ alert.
5. Kiểm tra retention để xác định nguồn sắp mất.
6. Chỉ định evidence custodian và nơi lưu artifact.

### 10.2. Giai đoạn bảo toàn

1. Export log/audit từ nguồn độc lập trước khi hết retention.
2. Ghi query, filter, time range, source và export time.
3. Capture config/policy/deployment version có hiệu lực.
4. Snapshot queue/database/workload khi cần và được phép.
5. Yêu cầu provider giữ log theo request ID.
6. Tính hash, tạo manifest và xác minh artifact.
7. Đặt bản gốc vào kho read-only/retention lock phù hợp.
8. Ghi mọi lần transfer và truy cập.

### 10.3. Giai đoạn containment và recovery

1. Chặn route, account, key hoặc source đang gây hại theo mức cần thiết.
2. Revoke token/key/certificate hoặc secret ở hệ thống phát hành.
3. Cập nhật gateway/WAF/policy và ghi lại change ID/version.
4. Cô lập workload/tenant bị ảnh hưởng nếu cần.
5. Giữ evidence của thao tác containment và kết quả.
6. Khôi phục service theo canary và kiểm tra security invariant.
7. Đối chiếu transaction, queue và provider state để tránh side effect trùng.

### 10.4. Giai đoạn phân tích và đóng incident

1. Dựng timeline từ nguồn độc lập.
2. Xác định actor, endpoint, object, tenant và operation bị ảnh hưởng.
3. Phân biệt điều đã xác minh với giả thuyết.
4. Đánh giá dữ liệu bị đọc/sửa/xóa hoặc credential bị lộ.
5. Ghi giới hạn evidence và khoảng trống quan sát.
6. Kiểm tra remediation bằng test hoặc telemetry.
7. Xác định legal hold, retention và quyền truy cập sau incident.
8. Hoàn thiện report, lessons learned và action owner.

## 11. Evidence theo một số kịch bản API phổ biến

### 11.1. Nghi ngờ BOLA hoặc truy cập chéo tenant

Giữ:

- Request ID, method, route template và object reference.
- Principal/tenant context đã xác minh.
- Authentication result và token ID đã giả danh hóa.
- Authorization decision, policy version và reason code.
- Database transaction/audit record.
- Response status/size và operation state.
- List/search/bulk request liên quan.

Đối chiếu gateway, application và database. Một 200 ở gateway không chứng minh dữ liệu đã được trả; một 403 ở application không chứng minh query chưa đọc object. Cần xem thứ tự truy vấn, response serialization và transaction.

### 11.2. Nghi ngờ token/API key bị lộ

Giữ:

- Key/token ID, issuer, client, scope và thời hạn.
- Authentication success/failure theo endpoint.
- Secret manager access audit và secret version metadata.
- API key last-used, source network và provider request ID.
- Rotation/revocation event và propagation status.
- CI/CD, repository, artifact hoặc log access event liên quan.

Không đưa credential gốc vào report. Thu hồi ở issuer/provider và xác minh mọi instance đã nhận trạng thái revoke. Với JWT offline, kiểm tra JWKS cache, denylist hoặc session state thay vì chỉ nhìn log logout.

### 11.3. Nghi ngờ SSRF qua outbound integration

Giữ:

- Request input đã được redact nhưng đủ chứng minh URL/hostname được gửi.
- URL validation decision và allowlist/policy version.
- DNS query/answer tại thời điểm request.
- Egress proxy/firewall flow và destination IP/port.
- TLS SNI, peer certificate fingerprint và hostname verification result.
- Service identity và outbound credential reference/version (không phải value).
- Provider response/request ID và timeout/retry.

Không chỉ dùng DNS lookup hiện tại để kết luận destination lịch sử. Cần flow log hoặc resolver log tại thời điểm sự cố. Nếu có nhiều redirect, bảo toàn từng hop và kết quả validation.

### 11.4. Nghi ngờ webhook giả mạo hoặc replay

Giữ:

- Raw body restricted hoặc hash của đúng raw bytes.
- Signature header metadata, timestamp và key ID.
- Verification result/reason code và policy version.
- Provider account, event ID và delivery ID.
- Queue topic/partition/offset, message hash, retry/DLQ history.
- Inbox/idempotency record và domain transaction.

Không ghi signing secret. Nếu cần xác minh lại, dùng key trong môi trường điều tra được kiểm soát; không đưa secret vào evidence package.

### 11.5. Nghi ngờ abuse hoặc credential stuffing

Giữ:

- Request rate theo IP/network, principal, client và endpoint.
- Authentication failure reason code.
- Rate-limit bucket decision và policy version.
- WAF/bot/challenge decision.
- Account lockout, password reset hoặc MFA event.
- Retry pattern và source distribution.

Giảm dữ liệu cá nhân trong dashboard; dùng aggregate và pseudonymous identifier khi có thể. Không dùng IP đơn lẻ làm bằng chứng chắc chắn về danh tính cá nhân.

## 12. Database, queue và side effect không xác định

Trong sự cố, timeout có thể xảy ra sau khi database commit hoặc provider đã thực hiện giao dịch nhưng response không về. Cần bảo toàn bằng chứng để tránh kết luận sai và tránh replay gây side effect trùng.

### 12.1. Transaction evidence

Ghi:

- Operation ID và idempotency key reference đã giả danh hóa.
- Database transaction ID và commit/rollback state.
- Outbox event ID và publish result.
- Provider request ID và response/timeout.
- Current business state và state transition history.

Không giả định HTTP timeout đồng nghĩa transaction thất bại. Tra cứu operation/idempotency record và đối soát provider trước khi retry thao tác tài chính.

### 12.2. Queue evidence

Giữ message gốc, offset, delivery count, ack state và retry schedule. Nếu cần replay để kiểm tra, tạo bản sao trong môi trường cách ly, bỏ quyền ghi production và dùng provider/database stub. Replay trực tiếp vào production có thể làm thay đổi bằng chứng và tạo giao dịch trùng.

## 13. Evidence collection khi workload hoặc control plane bị xâm nhập

Nếu attacker có quyền trên pod, VM, gateway hoặc cloud account, log tại chính thành phần đó có thể đã bị xóa/sửa. Ưu tiên nguồn độc lập:

- Central log/trace collector với identity riêng.
- Cloud audit trail được lưu ở account bảo vệ độc lập.
- Gateway/WAF log ngoài cluster application.
- Database audit do managed database phát ra.
- Broker audit và immutable topic archive nếu có.
- KMS/secret manager audit.
- CI/CD audit, image registry digest và deployment controller history.
- Network flow log hoặc egress proxy.

### 13.1. Snapshot runtime

Snapshot filesystem, container image, pod metadata hoặc memory có thể hữu ích nhưng chứa secret, token và dữ liệu người dùng. Cần phê duyệt, giới hạn phạm vi, mã hóa và lưu restricted. Ghi rõ snapshot được tạo trước hay sau khi isolate/restart; thao tác capture có thể thay đổi trạng thái runtime.

### 13.2. Image và deployment provenance

Giữ:

- Image digest và registry reference.
- Source commit/build ID.
- CI workflow/run ID và actor.
- SBOM/signature/attestation nếu có.
- Deployment event, rollout history và rollback.
- Runtime config/policy hash.
- Admission/security policy decision.

Tag image có thể bị di chuyển; digest mới là reference bất biến hơn để xác định artifact đã chạy. Không chỉ ghi tag như latest hoặc production.

## 14. Evidence manifest và registry

Một incident có nhiều artifact từ nhiều nguồn. Evidence registry giúp biết artifact nào đã thu thập, ai giữ, mức nhạy cảm và trạng thái kiểm tra.

Trường gợi ý:

| Trường | Nội dung |
|---|---|
| evidence_id | ID duy nhất |
| incident_id | Case liên quan |
| source_system | Gateway, app, DB, queue, provider... |
| source_reference | Log group, partition, transaction hoặc request reference |
| time_range | Khoảng thời gian gốc và timezone |
| collected_by | Collector identity |
| collected_at | Thời điểm capture |
| artifact_hash | SHA-256 của file bytes |
| integrity_status | Kết quả verify hash/signature |
| classification | Internal, confidential, restricted... |
| storage_reference | URI/ID trong evidence store |
| parent_evidence_id | Artifact gốc nếu đây là bản dẫn xuất |
| access_history | Tham chiếu audit truy cập |
| retention/legal_hold | Ngày hết hạn hoặc trạng thái giữ |

Không đưa secret value hoặc dữ liệu nhạy cảm trực tiếp vào registry metadata. Metadata cũng cần access control vì tên tenant, object hoặc provider account có thể là dữ liệu nhạy cảm.

## 15. Kiểm thử khả năng bảo toàn evidence

Evidence process cần được diễn tập trước incident. Kiểm thử cả việc thu thập thành công và các trường hợp hệ thống quan sát bị lỗi.

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Request correlation | Request qua gateway, app, DB và queue | Có thể liên kết bằng request/operation IDs |
| Header redaction | Request chứa Bearer token/cookie/API key | Artifact thông thường không chứa credential |
| Body integrity | Capture raw body và tính hash | Hash ổn định khi verify bản gốc |
| Transformation | Tạo bản redact/normalized | Bản gốc giữ nguyên; manifest liên kết bản dẫn xuất |
| Clock skew | Node lệch đồng hồ | Timeline giữ timestamp gốc và ghi offset |
| Trace sampling | Trace bị sample hoặc collector mất span | Audit vẫn có record cho action bắt buộc |
| Log rotation | Incident cần cửa sổ dài hơn retention mặc định | Có export/retention process và alert |
| Audit tampering | Workload cố xóa log của chính nó | Bị chặn hoặc có bản sao độc lập |
| Evidence access | Người không thuộc case mở raw payload | Access bị từ chối và được audit |
| Hash verification | Sửa artifact sau capture | Integrity check thất bại |
| Provider retention | Provider sắp xóa log | Có quy trình preservation request |
| Secret evidence | Thu thập secret manager audit | Có path/version/actor, không có secret value |
| Queue replay | Analyst thử xử lý message | Dùng bản sao cách ly, không tạo production side effect |
| Containment record | Revoke key và đổi policy | Có actor, change ID, version và thời điểm |
| Restore | Khôi phục evidence backup | Hash, manifest, ACL và retention được xác minh |

### 15.1. Tabletop exercise

Một kịch bản diễn tập có thể là: API trả 200 cho request đọc invoice của tenant khác; sau đó gateway được cập nhật policy, pod được restart và provider giữ log trong thời gian ngắn.

Nhóm ứng cứu cần:

1. Tìm request ID và mở incident.
2. Giữ gateway/app/DB audit trước khi retention xóa.
3. Xác định principal, tenant và policy version tại thời điểm request.
4. Kiểm tra database query/response serialization.
5. Xác định dữ liệu nào có thể đã bị trả.
6. Ghi lại policy update, pod restart và thời điểm containment.
7. Tạo manifest, hash và chain of custody.
8. Nêu rõ evidence còn thiếu và mức độ chắc chắn của kết luận.

Đánh giá thời gian thu thập, độ đầy đủ, khả năng truy vết và việc có lộ thêm dữ liệu nhạy cảm hay không.

## 16. Vai trò và quyền truy cập trong incident

Tách vai trò giúp tránh một người vừa thu thập, chỉnh sửa, phân tích và xóa evidence mà không có kiểm soát.

| Vai trò | Trách nhiệm |
|---|---|
| Incident commander | Quyết định phạm vi, ưu tiên containment và điều phối |
| Evidence custodian | Quản lý registry, bản gốc, manifest và chain of custody |
| Collector | Export từ nguồn được phê duyệt, tạo hash và ghi metadata |
| Analyst | Phân tích working copy, ghi giả thuyết và kết quả |
| Service owner | Cung cấp kiến trúc, dependency và giải thích nghiệp vụ |
| Security/platform operator | Thực hiện containment, revoke, policy/deployment change |
| Legal/privacy | Hướng dẫn preservation, disclosure, retention và legal hold |

Quyền break-glass cần có thời hạn, approval và audit. Không dùng shared admin account không thể truy vết. Khi incident kết thúc, thu hồi quyền tạm thời và kiểm tra access history.

## 17. Những sai lầm thường gặp

- **Chỉ giữ log application:** bỏ sót gateway, identity, database, queue hoặc provider.
- **Chỉ lưu dashboard screenshot:** mất raw source, query và metadata.
- **Ghi toàn bộ request header/body:** tạo thêm kho token, PII và secret.
- **Redact bản gốc:** mất khả năng xác minh raw evidence.
- **Chỉ giữ hash:** không còn artifact để phân tích; hash cũng không chứng minh nguồn.
- **Không ghi collector/time range:** không thể tái tạo cách export.
- **Tin timestamp của client:** timeline có thể bị làm sai.
- **Không ghi clock offset:** sự kiện phân tán bị xếp sai thứ tự.
- **Coi trace đầy đủ:** sampling và collector loss có thể bỏ mất span.
- **Để workload xóa audit của chính nó:** attacker có thể xóa dấu vết.
- **Export secret value để điều tra:** tạo thêm rủi ro compromise.
- **Không giữ policy/config version:** chỉ biết quyết định nhưng không biết rule nào có hiệu lực.
- **Replay queue trong production:** thay đổi trạng thái và tạo side effect trùng.
- **Chỉ tra DNS hiện tại:** không chứng minh destination tại thời điểm incident.
- **Quên provider retention:** evidence bên ngoài biến mất trước khi yêu cầu giữ.
- **Không ghi thao tác containment:** timeline không phân biệt hành vi attacker với hành động responder.
- **Không kiểm tra restore:** backup có thể thiếu artifact hoặc mất integrity.
- **Giữ evidence vô thời hạn:** tăng rủi ro privacy và vi phạm retention policy.

## 18. Checklist trước khi phát hành

- [ ] Có inventory nguồn evidence cho edge, gateway, identity, app, DB, queue và dependency.
- [ ] Request ID/trace ID/operation ID được liên kết xuyên service.
- [ ] Route template và metadata được ghi mà không làm lộ object/PII không cần thiết.
- [ ] Authorization, authentication và policy version có audit riêng cho action nhạy cảm.
- [ ] Header nhạy cảm được allowlist/redact trước khi log.
- [ ] Raw body chỉ được giữ khi có lý do, có encryption và access control.
- [ ] Hash được tính trên đúng artifact gốc; bản dẫn xuất có liên kết parent.
- [ ] Timestamp UTC, ingest time và clock offset được lưu riêng.
- [ ] Trace sampling được phân biệt với audit completeness.
- [ ] Gateway/WAF, JWKS, secret manager, KMS và provider evidence có quy trình export.
- [ ] Database transaction và queue offset/retry/DLQ có thể truy vết.
- [ ] Policy, config, deployment image digest và key version tại thời điểm request được bảo toàn.
- [ ] Evidence manifest có source, collector, time range, hash và classification.
- [ ] Bản gốc read-only; phân tích trên working copy.
- [ ] Evidence store có encryption, retention lock/legal hold và audit truy cập.
- [ ] Quyền collector, analyst, custodian và break-glass được tách.
- [ ] Có preservation request cho provider với request ID và time range.
- [ ] Không lưu token, API key, private key hoặc secret value vào report thông thường.
- [ ] Có test hash integrity, redaction, clock skew, log rotation và restore.
- [ ] Có tabletop exercise và runbook thu thập trước/sau containment.

Bảo toàn request, audit và dependency evidence giúp đội ứng cứu dựng lại điều gì đã xảy ra và chứng minh vì sao kết luận được đưa ra. Khi nguồn dữ liệu được xác định trước, artifact gốc được giữ nguyên, hash/manifest và chain of custody được quản lý, còn secret và dữ liệu cá nhân được bảo vệ theo quyền và retention, quá trình điều tra API sẽ đáng tin cậy hơn và ít tạo thêm rủi ro trong lúc xử lý sự cố.
