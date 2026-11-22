# Tin input nội bộ hoặc response third-party mặc định

## 1. Vì sao “nội bộ” và “đến từ đối tác” không đồng nghĩa với đáng tin?

Một API thường nhận dữ liệu từ nhiều nguồn: browser, mobile app, service nội bộ, message queue, batch job, webhook, hệ thống đối tác và SaaS provider. Một anti-pattern nguy hiểm là áp dụng mức tin cậy chỉ dựa trên vị trí mạng hoặc tên hệ thống gửi dữ liệu:

- Request đến từ private network thì được coi là hợp lệ.
- Header do API gateway hoặc service khác chuyển tiếp thì được coi là identity đã xác minh.
- Message trong queue nội bộ thì được coi là event đúng schema và đúng tenant.
- Response từ payment, identity, shipping hoặc data provider thì được coi là dữ liệu nghiệp vụ chính xác.
- JSON/XML do đối tác trả về thì được parse và dùng trực tiếp cho database, workflow hoặc lệnh gọi service tiếp theo.

Những giả định này tạo ra một trust boundary quá rộng. Service nội bộ có thể bị compromise, cấu hình route có thể sai, workload identity có thể bị cấp quyền quá mức, message có thể bị giả mạo hoặc phát lại. Đối tác có thể gặp lỗi, bị tấn công, trả dữ liệu cũ, sai schema hoặc bị lợi dụng để đưa nội dung độc hại vào hệ thống của bạn.

Trong API security, mọi dữ liệu đi qua ranh giới process, network, queue, storage hoặc tổ chức đều cần được xác định nguồn, xác thực khi cần, kiểm tra schema và ngữ nghĩa, giới hạn tài nguyên, rồi mới được dùng cho quyết định nghiệp vụ. “Internal” và “third-party” là mô tả nguồn; chúng không phải kết quả của một quyết định authorization.

## 2. Phân biệt authenticity, integrity, validity và authorization

Một dữ liệu có thể đến từ đúng hệ thống nhưng vẫn không hợp lệ hoặc không được phép dùng trong ngữ cảnh hiện tại.

| Thuộc tính | Câu hỏi cần trả lời | Ví dụ |
|---|---|---|
| Provenance | Dữ liệu đến từ đâu và qua những hop nào? | Event được phát bởi `billing-service` hay client giả danh service đó? |
| Authenticity | Có bằng chứng caller/source là identity đã được xác minh không? | mTLS hoặc access token có issuer/audience đúng. |
| Integrity | Dữ liệu có bị sửa trong quá trình truyền hoặc lưu không? | TLS, signature hoặc MAC hợp lệ theo contract. |
| Freshness | Dữ liệu có còn mới, chưa hết hạn hoặc chưa bị replay không? | `issuedAt`, sequence/version, nonce hoặc event ID. |
| Schema validity | Dữ liệu có đúng cấu trúc và miền giá trị không? | `amount` là số dương, `currency` thuộc allowlist. |
| Semantic validity | Dữ liệu có hợp lý với trạng thái nghiệp vụ hiện tại không? | Payment thuộc đúng order và số tiền khớp invoice. |
| Authorization | Principal này có được phép thực hiện action trên object/tenant này không? | `shipping-service` được cập nhật shipment được giao, không được hoàn tiền. |
| Resource safety | Việc đọc/parse/xử lý có nằm trong giới hạn không? | Response nhỏ hơn byte limit và parser depth limit. |

TLS giúp xác thực endpoint và bảo vệ dữ liệu trên đường truyền theo trust store đã cấu hình; nó không chứng minh response đúng nghiệp vụ. Chữ ký hợp lệ chứng minh dữ liệu được ký bởi key tương ứng và chưa bị thay đổi theo cơ chế ký; nó cũng không chứng minh event còn mới, đúng tenant hoặc được phép thực hiện action.

Hãy coi các thuộc tính này là những kiểm tra riêng. Một response chỉ được dùng khi các kiểm tra cần thiết cho use case đều đạt.

## 3. Threat model cho input nội bộ

“Nội bộ” có thể là traffic từ VPC, Kubernetes cluster, service mesh, private DNS, VPN hoặc message broker. Các môi trường này vẫn có những rủi ro:

- Một service bị chiếm quyền có thể gọi service khác bằng workload identity hợp lệ nhưng vượt mục đích ban đầu.
- SSRF ở một service có thể trở thành pivot vào endpoint nội bộ hoặc metadata service.
- Một route cũ, internal ingress hoặc management port có thể bị expose nhầm.
- Header `X-User-ID`, `X-Tenant-ID`, `X-Authenticated-User` hoặc `X-Forwarded-For` có thể bị caller tự gửi nếu proxy không strip/overwrite.
- Token service-to-service có thể có audience quá rộng, thời hạn dài hoặc scope lớn hơn nhu cầu.
- Message queue có thể nhận event từ producer không đúng, event cũ được replay hoặc consumer xử lý cùng event nhiều lần.
- Dữ liệu từ database, cache, file import hoặc batch job có thể đã được ghi bởi nguồn không đáng tin ở bước trước.
- Service account dùng chung làm mất khả năng xác định workload thực sự đã thực hiện request.

Vì vậy, network segmentation là một lớp giảm bề mặt tấn công, không phải bằng chứng duy nhất về identity hoặc quyền. Mỗi service nên có identity riêng, quyền tối thiểu và authorization ở ranh giới dữ liệu.

## 4. Threat model cho response third-party

Response từ đối tác có thể bị lỗi hoặc độc hại ngay cả khi request được gửi qua HTTPS tới hostname đúng:

- Schema thay đổi, field bị thiếu, field có kiểu dữ liệu khác hoặc giá trị vượt miền.
- Response chứa ID, tenant, amount, currency hoặc trạng thái không khớp request ban đầu.
- Nội dung có HTML/JavaScript, URL, filename, XML entity hoặc chuỗi được dùng ở SQL/shell/template.
- Redirect dẫn tới hostname khác, địa chỉ private, loopback, link-local hoặc cloud metadata endpoint.
- DNS record thay đổi giữa lúc validate và lúc kết nối (DNS rebinding).
- Body rất lớn, JSON nesting sâu, XML entity expansion, archive bomb hoặc compressed response phình lớn.
- Response cũ, duplicate, replay hoặc sai thứ tự làm rollback trạng thái nghiệp vụ.
- Provider timeout sau khi đã thực hiện side effect, khiến retry tạo thao tác trùng.
- API key hoặc bearer token bị gửi tới redirect host hoặc xuất hiện trong log/error message.
- Đối tác bị compromise hoặc tài khoản integration bị cấp quyền quá rộng.

Một response `200 OK` chỉ nói rằng HTTP exchange đã thành công theo protocol; nó không có nghĩa dữ liệu bên trong được phép tin hoặc có thể ghi thẳng vào domain model.

## 5. Lập trust boundary và inventory nguồn dữ liệu

Với mỗi nguồn, ghi lại identity, đường truyền, schema, quyền và cách xử lý khi lỗi.

| Nguồn | Bằng chứng nguồn | Kiểm tra bắt buộc trước khi sử dụng |
|---|---|---|
| Browser/mobile client | User authentication, session hoặc access token. | DTO validation, authorization theo object/tenant/property, size/rate limit. |
| Internal service | Workload identity, mTLS, OAuth client credentials hoặc service mesh identity. | Token issuer/audience/expiry/scope, schema, tenant/object authorization và request budget. |
| Message queue | Broker ACL, producer identity, topic/consumer policy. | Schema version, event ID, signature nếu contract yêu cầu, freshness, idempotency và tenant binding. |
| Third-party REST API | TLS hostname validation, credential riêng, response signature nếu có. | Status/content type, body limit, schema, semantic checks, timeout, redirect/SSRF policy. |
| Webhook | Signature/MAC theo provider contract và timestamp. | Raw-body signature, replay window, event ID, schema, tenant binding, idempotency. |
| File/import/batch | Upload identity, source metadata và storage provenance. | File type/content checks, parser limits, schema, row-level authorization và quarantine. |
| Database/cache | Service/database identity và quyền truy cập. | Data ownership, migration/version, tenant scope, integrity và freshness. |

Không chỉ phân loại theo tên hệ thống. Một integration có thể nhận cả request đã xác thực và dữ liệu do người dùng cuối kiểm soát; cần biết chính xác field nào do ai tạo. Ví dụ, `partnerAccountId` có thể được provider xác thực nhưng `displayName` bên trong payload vẫn là nội dung do khách hàng của provider nhập.

## 6. Xác thực service-to-service đúng cách

Không dùng private IP, DNS suffix `.internal`, Kubernetes namespace hoặc một header tên `X-Internal-Request: true` làm bằng chứng authentication.

Các lựa chọn thường dùng:

- **mTLS/workload identity:** xác minh client certificate hoặc identity do service mesh/platform cấp; ánh xạ SAN/workload identity vào service cụ thể.
- **OAuth 2.0 client credentials:** service lấy access token có thời hạn ngắn, audience đúng resource server và scope tối thiểu.
- **Signed request:** dùng khi protocol/integration yêu cầu signature, timestamp và replay protection.
- **Broker identity/ACL:** giới hạn producer được publish topic nào và consumer được subscribe queue nào.

Khi xác minh JWT từ service khác, kiểm tra signature bằng key thuộc issuer được tin cậy, thuật toán được allowlist, `iss`, `aud`, `exp`, `nbf` và token type theo contract. Không chỉ decode Base64 rồi tin claims. Không chấp nhận audience chung chung như `internal` nếu token có thể dùng cho nhiều service không liên quan.

Ví dụ policy:

```text
Caller workload: shipping-service
Resource server: orders-api
Token audience: orders-api
Allowed scope: shipment:read shipment:status:update
Denied scope: order:refund order:admin
Token lifetime: short-lived
```

Mỗi workload nên có identity riêng. Tránh dùng một service account chung cho toàn bộ microservice; nếu một service bị compromise, shared credential làm tăng blast radius và khó điều tra.

## 7. Identity của service không tự động là identity của user

Khi `gateway-service` gọi `orders-api`, service đích cần biết request được thực hiện bởi gateway nào. Nếu gateway đang thay mặt Alice, cần phân biệt:

- **Actor/workload:** service nào thực sự gửi request?
- **Subject/end user:** user nào khởi tạo hành động?
- **Delegation:** service có được phép hành động thay user đó không, trên audience/resource nào?
- **Tenant context:** user và resource thuộc tenant nào theo mapping đã xác minh?

Không tin `X-User-ID` hoặc `X-Tenant-ID` do service gọi tự đặt nếu các header không được ràng buộc với authenticated workload/delegation. Dùng token delegation hoặc cơ chế context propagation được ký/xác minh, có audience và thời hạn phù hợp. Giữ cả actor và subject trong audit log.

Ngay cả khi service identity hợp lệ, API vẫn phải kiểm tra quyền trên object cụ thể. `shipping-service` có thể cập nhật trạng thái shipment được giao nhưng không được truy cập toàn bộ customer profile hoặc thực hiện refund chỉ vì nó nằm trong private network.

## 8. Validate input nội bộ như dữ liệu qua trust boundary

Áp dụng cùng nguyên tắc validation cho internal API và public API, điều chỉnh schema theo contract:

- Dùng request DTO có field allowlist; không bind trực tiếp request vào JPA entity/domain entity.
- Kiểm tra required, type, length, numeric range, enum, format và nested collection.
- Giới hạn body bytes, header size, list/batch count, JSON depth và processing cost.
- Xác minh quan hệ giữa object ID, owner, tenant và caller identity.
- Không nhận tenant/owner/role/permission từ input nếu các giá trị đó phải do server xác định.
- Kiểm tra business state và transition trong service/domain layer.
- Dùng parameterized SQL, safe template/output encoding và allowlist cho command/path theo đúng ngữ cảnh.
- Chuẩn hóa dữ liệu một lần theo contract; tránh nhiều tầng normalize khác nhau làm thay đổi ý nghĩa.

Internal caller không được miễn validation chỉ vì “đội mình viết”. Một service có thể có bug, phiên bản cũ hoặc dữ liệu upstream sai. Validation nhất quán giúp giới hạn lỗi lan truyền giữa các service.

## 9. Không tin header nội bộ nếu chưa xác minh proxy

Các header như `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Authenticated-User`, `X-Client-ID`, `X-Tenant-ID` và `X-Internal-Role` thường được proxy hoặc gateway thêm vào. Chúng chỉ đáng tin khi đường truyền và hop tạo header đã được xác thực.

Gateway/reverse proxy cần:

1. Xóa hoặc ghi đè header cùng tên do caller bên ngoài gửi.
2. Thêm giá trị từ authentication context đã xác minh, không sao chép mù từ request.
3. Chỉ forward qua upstream đã được xác thực bằng network policy/mTLS.
4. Backend chỉ tin header từ proxy/workload cụ thể trong trust configuration.
5. Từ chối hoặc bỏ qua header identity khi request đến qua đường không tin cậy.

Nếu backend có thể được gọi trực tiếp, không được giả định header do gateway thêm luôn hiện diện hoặc không thể giả mạo. Cần bảo vệ origin và xác thực service-to-service ở backend.

## 10. Xác minh response third-party trước khi dùng

Một response từ đối tác nên đi qua các bước:

1. Kết nối tới endpoint đã được cấu hình/allowlist, xác minh TLS certificate và hostname.
2. Dùng credential riêng cho integration, gửi đúng audience/scope và không forward credential tới host khác.
3. Kiểm tra HTTP status, content type, content encoding và response headers cần thiết.
4. Áp timeout, response byte limit, connection limit và redirect policy.
5. Parse bằng thư viện an toàn với schema/version đã xác định.
6. Validate từng field, collection size, nested depth và các miền giá trị.
7. Kiểm tra ngữ nghĩa với request gốc và domain state hiện tại.
8. Kiểm tra freshness, sequence/version, signature hoặc event identity theo contract.
9. Chỉ map field được phép vào domain command/model; giữ provenance nếu dữ liệu được lưu.
10. Ghi nhận lỗi có cấu trúc, không log secret hoặc toàn bộ payload nhạy cảm.

Không cập nhật domain entity bằng cách deserialize response trực tiếp rồi `repository.save(entity)`. Hãy map qua một adapter/anti-corruption layer có schema và policy riêng cho provider.

## 11. Kiểm tra ngữ nghĩa, không chỉ schema

Một response có thể đúng JSON schema nhưng sai về nghiệp vụ. Ví dụ:

- Payment provider trả `status=PAID` nhưng `paymentId` không thuộc order đang xử lý.
- `amount` khác invoice hoặc `currency` không khớp contract.
- Identity provider trả user ID hợp lệ nhưng tenant mapping không thuộc organization hiện tại.
- Shipping provider trả `delivered=true` cho shipment đã bị hủy hoặc ID không khớp.
- Inventory service trả số lượng âm hoặc version cũ hơn trạng thái đã lưu.
- Partner trả callback URL/redirect URL trỏ tới host không được phép.

Các invariant nên được kiểm tra ở service/domain boundary:

| Field/condition | Kiểm tra |
|---|---|
| Object identity | ID trong response phải khớp request hoặc mapping đã lưu. |
| Tenant/account | Account/tenant phải được liên kết với integration đã xác thực. |
| Amount/currency | Giá trị và đơn vị phải khớp transaction/invoice theo contract. |
| Status transition | Chỉ transition hợp lệ mới được áp dụng; status không biết không được map thành success. |
| Version/sequence | Event cũ không được ghi đè state mới hơn. |
| Timestamp/expiry | Dữ liệu nằm trong freshness window; clock skew được xử lý rõ. |
| Relationship | Child/resource phải thuộc parent và tenant được yêu cầu. |
| Quantity/limit | Số lượng và giá trị nằm trong miền nghiệp vụ. |

Không tự động biến giá trị không biết thành default thuận lợi như `APPROVED`, `ACTIVE`, `PAID`, `isAdmin=true` hoặc `risk=0`. Với trạng thái không nhận diện, từ chối/quarantine và yêu cầu xử lý tương thích có chủ đích.

## 12. Bảo vệ outbound request khỏi SSRF và redirect abuse

Response third-party thường được lấy từ URL cấu hình hoặc URL xuất hiện trong payload. Nếu caller có thể điều khiển URL, hoặc service tự follow redirect không giới hạn, một integration có thể trở thành SSRF proxy.

Nguyên tắc:

- Dùng base URL cố định do operator cấu hình cho mỗi integration; không ghép hostname từ input người dùng.
- Chỉ cho phép scheme cần thiết, thường là HTTPS; từ chối `file:`, `ftp:`, `gopher:` và scheme không được hỗ trợ.
- Allowlist hostname và port theo integration; không cho phép URL tùy ý chỉ vì nó có cú pháp hợp lệ.
- Tắt automatic redirects hoặc kiểm tra từng redirect target trước khi follow; không chuyển Authorization/API key sang host khác.
- Chặn loopback, link-local, private, multicast, reserved và metadata IP theo IPv4 lẫn IPv6 khi use case yêu cầu public destination.
- Xử lý DNS rebinding: kiểm tra kết quả A/AAAA ở thời điểm kết nối, tránh validate một IP rồi resolver lại sang IP khác; cân nhắc egress proxy kiểm soát DNS/địa chỉ đích.
- Đặt egress firewall để service chỉ kết nối tới dependency cần thiết.
- Không coi hostname thuộc suffix nội bộ hoặc URL HTTPS là an toàn mặc định.

Nếu tích hợp bắt buộc gọi tới private partner endpoint, định nghĩa endpoint đó trong allowlist hạ tầng có owner, port, certificate và route cụ thể; không mở toàn bộ private address space.

## 13. Giới hạn response size, timeout và tài nguyên parse

Response từ provider có thể quá lớn hoặc mất quá nhiều thời gian. Cần kiểm soát:

- Connection timeout, response/read timeout và overall deadline.
- Maximum response bytes, kể cả khi `Content-Length` thiếu hoặc không đáng tin.
- Maximum header size và số lượng header.
- Compressed bytes và expanded/decompressed bytes.
- JSON nesting depth, string length, number length, array/map count và parser token count nếu thư viện hỗ trợ.
- XML DTD/external entity, entity expansion và external schema access.
- Archive entry count, extraction size, path và recursion depth nếu response chứa file/archive.
- Retry count, concurrency, queue backlog và downstream calls.

Không chỉ dựa vào `Content-Length`: response chunked/streaming có thể không khai báo trước. Codec/stream reader cần dừng khi bytes thực tế vượt limit. Nếu response lớn hợp lệ, dùng streaming parser và xử lý từng phần có giới hạn thay vì buffer toàn bộ vào heap.

## 14. Parse và deserialize dữ liệu đối tác an toàn

### JSON

- Dùng DTO/schema cụ thể, giới hạn field và collection.
- Tránh polymorphic deserialization từ type/class name do payload điều khiển.
- Không bật Jackson default typing cho dữ liệu không tin cậy nếu không có allowlist subtype an toàn.
- Quy định rõ unknown field: reject nếu contract cần strict versioning, hoặc ignore nhưng tuyệt đối không bind vào domain field ngoài allowlist.
- Kiểm tra trailing tokens, duplicate keys và parser limits theo thư viện/phiên bản.
- Không gọi `toString()` hoặc log toàn bộ object response vì có thể chứa PII/secret.

### XML

- Tắt DTD và external entities (XXE).
- Không tải external schema/resource tùy ý trong lúc parse.
- Giới hạn entity expansion, document size, depth và thời gian parse.

### HTML, Markdown và rich text

- Không render response trực tiếp bằng `innerHTML` hoặc template không escape.
- Encode theo output context; nếu cần HTML rich text, sanitize bằng allowlist parser đã được duy trì.
- Cân nhắc phục vụ nội dung không tin cậy từ origin riêng, cookie isolation và Content Security Policy.

### File, archive và binary

- Không tin filename, extension hoặc MIME type do provider khai báo.
- Kiểm tra signature/content, size và checksum; quarantine/scan theo use case.
- Giới hạn decompression ratio, số entry và extraction path.
- Không ghi file vào webroot hoặc path được tạo từ filename response.

## 15. Dùng response trong SQL, shell, template và URL

Sau khi validate schema, field vẫn là dữ liệu không tin cậy khi đi vào một output context khác:

- **SQL:** dùng parameterized query/ORM binding; không nối chuỗi SQL từ response.
- **Shell/process:** tránh shell interpolation; dùng process API với argument array và allowlist command/argument.
- **HTML/template:** output encode hoặc sanitize theo context; không coi JSON string là HTML an toàn.
- **URL/redirect:** parse URI, kiểm tra scheme/host/port/path theo allowlist; không redirect browser tới URL đối tác tùy ý.
- **Filesystem:** dùng storage key do server tạo; không dùng filename/path do response quyết định.
- **Log:** structured logging, giới hạn length và redaction; không log token, cookie, signature hoặc payload đầy đủ.
- **Authorization:** không dùng field `role`, `tenantId`, `isAdmin` trong response đối tác làm quyền nội bộ nếu chưa có trust mapping và policy riêng.

Validation là kiểm tra dữ liệu theo contract; encoding/safe API là biện pháp bảo vệ theo ngữ cảnh sử dụng. Một chuỗi có thể hợp lệ như tên hiển thị nhưng không an toàn để ghép vào HTML, SQL hoặc shell.

## 16. Webhook và message: xác minh nguồn, freshness và idempotency

Webhook inbound và message queue là các trust boundary riêng. Với webhook:

- Xác minh signature trên raw body đúng theo provider contract.
- Kiểm tra timestamp/replay window và key rotation.
- Ràng buộc provider account/integration với endpoint đang nhận.
- Dùng event ID ổn định và durable deduplication để chống delivery lặp.
- Validate schema và semantic relationship trước khi cập nhật domain state.
- Chỉ acknowledge sau khi event đã được lưu bền vững hoặc xử lý đồng bộ thành công.

Với message queue:

- Broker ACL xác định workload nào được publish/consume topic.
- Consumer xác minh event type/version, producer context và tenant binding.
- Kiểm tra event ID, sequence/version, freshness và idempotency.
- Không tin actor/tenant trong payload nếu không được ràng buộc với authenticated producer.
- Dùng DLQ/quarantine cho event sai schema hoặc không thể xử lý; không bỏ qua validation để giữ queue chạy.

Một message nằm trong broker nội bộ vẫn có thể là dữ liệu do upstream không tin cậy tạo ra. Broker authentication không tự xác minh tính đúng đắn của từng field.

## 17. Failure handling: không chuyển lỗi thành quyền hoặc trạng thái mặc định

Khi internal dependency hoặc third-party provider lỗi, fallback phải bảo toàn security invariant.

- Nếu authentication/authorization service không thể xác minh identity, không mặc định allow.
- Nếu tenant mapping không tìm thấy, không gán tenant mặc định hoặc tenant đầu tiên.
- Nếu provider trả status không biết, không map thành `SUCCESS`/`APPROVED`.
- Nếu response thiếu amount/currency/identity bắt buộc, không tự điền giá trị có lợi cho giao dịch.
- Nếu signature không hợp lệ, không đưa event vào luồng xử lý bình thường.
- Nếu timeout sau một thao tác có side effect, kiểm tra trạng thái hoặc dùng idempotency key trước khi retry.
- Nếu dữ liệu nghi ngờ, quarantine và yêu cầu reconciliation/manual review theo quy trình.

Có thể dùng circuit breaker, retry với exponential backoff/jitter, timeout, bulkhead và queue để bảo vệ availability. Chỉ retry lỗi tạm thời theo contract; không retry vô hạn lỗi validation, signature hoặc authorization. Khi degraded mode, chỉ cho phép thao tác an toàn đã được xác định trước, ví dụ đọc cache có freshness policy; không tự mở rộng quyền ghi.

## 18. Ví dụ Spring WebClient gọi partner API có giới hạn

Ví dụ dưới đây minh họa fixed base URL, không follow redirect tự động, response timeout và codec memory limit. Endpoint không lấy URL từ user input:

```java
@Configuration
public class PartnerClientConfig {
    @Bean
    WebClient partnerWebClient(WebClient.Builder builder) {
        HttpClient httpClient = HttpClient.create()
            .followRedirect(false)
            .responseTimeout(Duration.ofSeconds(3));

        return builder
            .baseUrl("https://api.partner.example")
            .clientConnector(new ReactorClientHttpConnector(httpClient))
            .codecs(codecs -> codecs.defaultCodecs()
                .maxInMemorySize(256 * 1024))
            .build();
    }
}
```

`maxInMemorySize` giới hạn dữ liệu codec buffer trong các trường hợp áp dụng; nó không thay thế egress firewall, timeout tổng thể hoặc giới hạn cho streaming path. Cần kiểm thử với đúng connector/codec và phiên bản Spring/Reactor Netty đang dùng.

DTO response cần giới hạn field và giá trị:

```java
public record PartnerQuote(
    @NotBlank @Size(max = 64) String quoteId,
    @NotNull @Positive @Digits(integer = 10, fraction = 2)
        BigDecimal amount,
    @NotBlank @Pattern(regexp = "USD|EUR") String currency,
    @NotNull Instant expiresAt
) {}
```

Sau khi parse, chạy Bean Validation và kiểm tra quan hệ với request/domain:

```java
private PartnerQuote validatePartnerQuote(
        PartnerQuote quote,
        String expectedQuoteId,
        String expectedCurrency) {

    Set<ConstraintViolation<PartnerQuote>> violations =
        validator.validate(quote);
    if (!violations.isEmpty()) {
        throw new InvalidPartnerResponseException();
    }

    if (!quote.quoteId().equals(expectedQuoteId)
            || !quote.currency().equals(expectedCurrency)
            || !quote.expiresAt().isAfter(Instant.now())) {
        throw new InvalidPartnerResponseException();
    }
    return quote;
}
```

Gọi client với deadline tổng thể:

```java
Mono<PartnerQuote> getQuote(String quoteId, String currency) {
    return partnerWebClient.get()
        .uri("/v1/quotes/{id}", quoteId)
        .accept(MediaType.APPLICATION_JSON)
        .retrieve()
        .bodyToMono(PartnerQuote.class)
        .switchIfEmpty(Mono.error(new InvalidPartnerResponseException()))
        .timeout(Duration.ofSeconds(4))
        .map(quote -> validatePartnerQuote(quote, quoteId, currency));
}
```

Ví dụ rút gọn, cần inject `WebClient` và Jakarta `Validator`, xử lý HTTP status/error theo contract, xác minh TLS mặc định của client, giới hạn response headers và đảm bảo codec mapper có policy unknown-field phù hợp. Với integration yêu cầu strict JSON schema, cấu hình dedicated `ObjectMapper`/codec để reject unknown fields và trailing tokens; không bật polymorphic default typing cho response không tin cậy. `Instant.now()` trong code minh họa nên được thay bằng `Clock` có thể kiểm thử.

Không log raw response hoặc exception body từ provider. Chỉ ghi provider ID, request/correlation ID, response status, error code đã chuẩn hóa và fingerprint cần thiết.

## 19. Kiểm thử internal input và third-party response

Test cần bao gồm cả nguồn đúng identity nhưng payload sai, và payload đúng schema nhưng sai ngữ nghĩa.

| Ca kiểm thử | Input/response giả lập | Kết quả mong đợi |
|---|---|---|
| Internal caller identity | Request từ workload không có certificate/token hợp lệ. | Bị từ chối trước business handler. |
| Wrong audience | Token service hợp lệ nhưng audience dành cho service khác. | Resource server từ chối. |
| Spoofed identity header | Client gửi `X-Authenticated-User`/`X-Tenant-ID` giả. | Proxy strip/overwrite; backend không tin giá trị giả. |
| Overprivileged service | Service có scope read thử gọi refund/admin action. | Authorization deny. |
| Internal schema invalid | Service gửi field sai kiểu, thiếu required hoặc batch quá lớn. | Validation/limit từ chối, không có side effect. |
| Cross-tenant input | Token tenant A gửi resource/tenant B. | Bị từ chối ở object/tenant authorization. |
| Queue replay/duplicate | Phát lại event ID cũ hoặc gửi cùng event nhiều lần. | Replay/freshness policy và idempotency ngăn xử lý trùng. |
| Partner TLS failure | Certificate hết hạn/sai hostname trong test environment. | Request fail; không tắt TLS verification để tiếp tục. |
| Partner redirect | Provider trả redirect tới host khác hoặc private IP. | Không follow hoặc redirect target bị kiểm tra và từ chối. |
| SSRF/DNS rebinding | Host resolve từ public IP sang private/metadata IP trong test harness. | Egress policy chặn; không kết nối tới địa chỉ cấm. |
| Oversized response | `Content-Length` lớn, chunked body hoặc response nén phình lớn. | Reader/codec dừng ở limit, không cạn memory. |
| Malformed JSON/XML | Unknown field, wrong type, deep nesting, XXE hoặc trailing token. | Parse/validation fail an toàn, không truy cập external entity. |
| Semantic mismatch | Quote ID, tenant, amount, currency hoặc status không khớp request. | Quarantine/fail; domain state không đổi. |
| Stale/out-of-order event | Version cũ đến sau version mới. | Không rollback trạng thái mới. |
| Unsafe content | HTML/filename/URL chứa payload độc hại. | Encode/sanitize/allowlist theo output context; không thực thi. |
| Timeout after side effect | Provider đã xử lý nhưng response timeout. | Kiểm tra trạng thái/idempotency trước retry. |
| Log redaction | Response chứa token/PII hoặc secret test. | Không xuất hiện trong log, trace hoặc error response. |

Ngoài status code, kiểm tra database, outbox, queue, email, payment sandbox và downstream call count. Với lỗi bị từ chối, xác minh không có partial update. Dùng mock server/test container để mô phỏng redirect, chunked response, malformed payload và timeout; không phụ thuộc provider production để tạo tình huống lỗi.

## 20. Giám sát và lưu provenance

Khi dữ liệu được nhận từ service hoặc provider, giữ metadata đủ để điều tra mà không sao chép toàn bộ payload:

- Source/workload/provider ID đã xác minh.
- Integration/config version và endpoint logical name.
- Request ID, trace ID, provider request/event ID.
- Schema version, event type và content type.
- Validation result, semantic decision và policy ID.
- Received/issued/expiry timestamp và sequence/version nếu có.
- Response status, duration, byte count và retry count.
- Quarantine reason hoặc normalized error code.

Theo dõi tỷ lệ schema mismatch, unknown status, invalid signature, wrong audience, redirect reject, SSRF egress deny, oversized response, timeout, retry, DLQ và semantic mismatch. Alert khi một provider thay đổi schema bất thường, một service gọi endpoint ngoài scope hoặc một tenant nhận dữ liệu không khớp.

Không log access token, API key, client secret, private key, cookie, signature đầy đủ hoặc raw body nhạy cảm. Nếu cần lưu payload để điều tra, dùng quarantine store riêng với encryption, access control, retention và redaction phù hợp.

## 21. Anti-pattern và cách thay thế

| Anti-pattern | Rủi ro | Cách thay thế |
|---|---|---|
| Tin request vì đến từ private IP | Workload bị compromise hoặc route sai vẫn có thể gọi. | Workload identity, mTLS/token và authorization. |
| Dùng một shared service account | Blast radius lớn, khó quy trách nhiệm. | Identity riêng và scope tối thiểu cho từng workload. |
| Tin `X-User-ID`/`X-Tenant-ID` do caller gửi | Giả mạo principal hoặc cross-tenant access. | Proxy strip/overwrite, signed delegation và tenant mapping. |
| Gateway đã auth nên backend bỏ qua authz | Direct path hoặc route drift bypass gateway. | Backend xác minh identity/delegation và object policy. |
| Parse JWT mà không verify | Claims giả có thể được tin. | Verify signature, issuer, audience, time và token type. |
| Tin JSON từ provider vì HTTPS | Dữ liệu có thể sai schema, cũ hoặc bị provider compromise. | Schema + semantic validation và provenance. |
| Deserialize response thẳng vào entity | Mass assignment và field ngoài contract. | External DTO/adapter rồi map field allowlist. |
| Follow mọi redirect | Credential leak hoặc SSRF tới private endpoint. | Tắt redirect hoặc validate từng target; egress control. |
| Không giới hạn response size | Memory/CPU exhaustion và parser abuse. | Byte, depth, count, timeout và decompression limits. |
| Status không biết được map thành success | Workflow có thể approve/settle sai. | Unknown state fail closed/quarantine. |
| Retry vô hạn sau timeout | Duplicate payment/action và retry storm. | Idempotency, retry budget, backoff và reconciliation. |
| Log toàn bộ payload đối tác | Lộ PII/secret và tăng dữ liệu lưu giữ. | Structured metadata, redaction và quarantine có kiểm soát. |

## 22. Checklist trước khi tin dữ liệu từ nguồn khác

- [ ] Đã xác định chính xác source, owner, data provenance và các hop trung gian?
- [ ] Internal caller có workload identity riêng, mTLS/token và scope/audience phù hợp?
- [ ] Gateway/proxy strip hoặc overwrite identity/forwarded headers do client gửi?
- [ ] Service identity và end-user delegation được phân biệt?
- [ ] Authorization được kiểm tra theo action, object, tenant và property?
- [ ] Input nội bộ có DTO/schema, semantic validation và resource limits?
- [ ] Third-party TLS hostname/certificate được xác minh; không tắt verification?
- [ ] URL/redirect được allowlist và egress policy ngăn SSRF tới private/metadata endpoints?
- [ ] Response có timeout, byte limit, header limit, parser depth và decompression limit?
- [ ] JSON/XML/file được parse an toàn; không bật unsafe polymorphic deserialization hoặc XXE?
- [ ] ID, tenant, amount, currency, status, version và timestamp khớp nghiệp vụ?
- [ ] Unknown/missing value không tự chuyển thành allow/success/default đặc quyền?
- [ ] Webhook/message có signature hoặc producer authentication, replay protection và idempotency khi cần?
- [ ] Retry, circuit breaker, quarantine và reconciliation có policy rõ?
- [ ] Log giữ source/request/schema/decision metadata nhưng không chứa secret hoặc raw payload nhạy cảm?
- [ ] Có test identity giả, wrong audience, cross-tenant, malformed/oversized response, redirect, timeout và semantic mismatch?

Input nội bộ và response third-party đều là dữ liệu đi qua trust boundary. Hãy xác minh nguồn và identity, kiểm tra schema lẫn ngữ nghĩa, áp authorization trên object/tenant/property, giới hạn tài nguyên và xử lý lỗi theo hướng không tự mở quyền hoặc tự xác nhận nghiệp vụ. Một service đáng tin có thể gửi dữ liệu sai; một provider hợp lệ có thể trả response không an toàn. Chỉ sử dụng dữ liệu sau khi các kiểm tra phù hợp với rủi ro của endpoint và luồng nghiệp vụ đã hoàn tất.
