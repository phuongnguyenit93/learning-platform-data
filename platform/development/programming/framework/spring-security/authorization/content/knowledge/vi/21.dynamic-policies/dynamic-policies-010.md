# Lưu lý do quyết định và giải thích quyền mà không lộ dữ liệu nhạy cảm

## 1. Bài toán: vì sao bị từ chối, nhưng không được tiết lộ điều gì?

Trong một ứng dụng Spring Security có chính sách động, người dùng có thể gặp các kết quả như:

- Không được sửa tài liệu vì role trong tenant hiện tại không đủ.
- Không được đọc tài liệu vì không phải owner và không có grant READ.
- Không được xuất dữ liệu vì tài liệu đang ở trạng thái hạn chế.
- Không được sử dụng một tác vụ vì chính sách vừa thay đổi hoặc membership bị thu hồi.
- Hệ thống không thể kiểm tra quyền vì Policy Decision Point (PDP) đang gặp lỗi.

Người dùng, đội hỗ trợ và đội an toàn thông tin đều cần **giải thích quyết định**. Nhưng câu trả lời quá chi tiết có thể chính là một lỗ hổng mới:

~~~text
GET /tenants/north/documents/9843

Không an toàn:
"Bạn không phải chủ sở hữu. Chủ sở hữu là
 alice@private-company.example; tài liệu thuộc tenant secret-merger;
 2 người trong nhóm finance-exec đã được cấp READ."

An toàn hơn đối với caller chưa có quyền:
"Không tìm thấy tài nguyên trong phạm vi bạn được phép truy cập."
~~~

Thông báo đầu tiên xác nhận tài liệu tồn tại, tiết lộ owner, tên tenant, thành viên được cấp quyền và cấu trúc tổ chức. Một đối tượng tấn công có thể đổi ID liên tục để **liệt kê dữ liệu** dù không bao giờ được đọc nội dung tài liệu.

Ngược lại, nếu mọi nơi chỉ ghi `DENY`, nhóm vận hành sẽ khó biết rule nào gây lỗi, policy version nào đang chạy, có phải race giữa grant/revoke hay không. Cần phân biệt ba đầu ra:

1. **Quyết định thực thi:** ALLOW, DENY, ERROR/INDETERMINATE, cùng phạm vi áp dụng.
2. **Bản ghi audit nội bộ:** lý do theo mã chuẩn, policy revision, event/decision ID và những metadata **được phép lưu**.
3. **Lời giải thích ra ngoài:** thông điệp tối thiểu, phù hợp quyền được biết của người nhận và không xác nhận tài nguyên nằm ngoài scope.

**Nguyên tắc xuyên suốt:** một lời giải thích không được cung cấp nhiều thông tin hơn chính quyền truy cập đã được xác minh. Audit cũng là **một tập dữ liệu nhạy cảm**, phải có phân quyền, hạn lưu, che dữ liệu và khả năng kiểm chứng riêng.

## 2. Phân biệt policy decision, reason code và user-facing message

Một ví dụ:

~~~text
Internal policy evaluation:
    effect          = DENY
    reasonCode      = RESOURCE_NOT_IN_AUTHORIZED_SCOPE
    policyVersion   = document-policy-v17
    decisionId      = 36c1...   (correlation only)
    resourceType    = Document
    action          = DOCUMENT_READ

External API:
    HTTP 404
    code            = RESOURCE_NOT_AVAILABLE
    message         = "Tài nguyên không khả dụng trong phạm vi truy cập."
    requestId       = req-7814
~~~

**Reason code nội bộ** mô tả nhánh policy. **Public code** mô tả điều caller được phép biết. Hai code không nhất thiết ánh xạ một-một. Nhiều nguyên nhân như “ID không tồn tại”, “resource thuộc tenant khác” và “không có ACL READ” có thể cố tình cùng tạo một public response.

Bảng so sánh:

| Loại dữ liệu | Phục vụ ai? | Độ chi tiết | Lưu/hiển thị ở đâu? |
|---|---|---|---|
| Effect | PEP, service | ALLOW/DENY/ERROR | Kết quả kiểm tra quyền |
| Internal reason | PDP, đội hỗ trợ có quyền | Mã rule/nhánh bị chặn | Audit store hạn chế |
| Policy revision | Vận hành, kiểm toán | Version/hàm policy | Audit/observability |
| Decision/request ID | Cả nội bộ và client | Mã tra cứu không phải secret | Log, response nếu an toàn |
| Public explanation | Caller | Tối thiểu, không nêu object ngoài quyền | HTTP body/UI |
| Diagnostic detail | Nhân sự được cấp quyền | Có thể chứa nhiều thông tin nhạy cảm hơn | Công cụ hỗ trợ có xác thực/audit |
| Raw rule input | Thường không nên lưu | Có thể chứa token, PII, ACL | Chỉ xử lý tạm theo policy dữ liệu |

**Lý do quyết định không phải lời kể nguyên văn của exception.** Không dùng `exception.getMessage()` làm response hoặc audit reason vì exception từ JPA, HTTP client hay policy engine có thể chứa SQL, URL, tên tài khoản hoặc dữ liệu nghiệp vụ.

## 3. Ba mức tiết lộ: public, support và restricted security

Một mô hình có thể phân tầng:

### Mức 1 — Caller thông thường

Chỉ thông báo quyền chức năng đã được phép nhìn thấy, hoặc một thông điệp chung:
- `AUTHENTICATION_REQUIRED`.
- `ACTION_NOT_AVAILABLE`.
- `RESOURCE_NOT_AVAILABLE`.
- `AUTHORIZATION_TEMPORARILY_UNAVAILABLE`.
- `requestId` để liên hệ hỗ trợ.

Không cho caller chưa có quyền biết owner thật, tên tenant thật, role của người khác, phân loại SECRET, grant đang có, rule nội bộ hay chính sách chống gian lận.

### Mức 2 — Chủ tài nguyên/người quản trị tenant đã được kiểm tra quyền

Một owner đã được xác minh đôi khi có thể thấy nguyên nhân chi tiết hơn, chẳng hạn:
- “Tài liệu của bạn đang bị khóa, không thể sửa.”
- “Bạn cần quyền DOCUMENT_SHARE trong workspace này.”
- “Lượt tải xuống vượt giới hạn theo chính sách workspace.”

**Điều kiện:** trước khi hiển thị giải thích chi tiết, hệ thống phải **kiểm tra một quyền độc lập để xem chi tiết tài nguyên/chính sách**. Không coi người gửi yêu cầu READ bị từ chối tự động có quyền xem owner/ACL.

### Mức 3 — Vận hành/an toàn thông tin

Nhân sự có quyền xử lý sự cố có thể truy cập audit reason, policy version, revocation sequence, tenant/actor reference và decision trace **đã tối thiểu hóa**. Quyền đọc audit phải theo need-to-know, có xác thực mạnh khi phù hợp, log lại truy cập và hạn chế export.

**Không dùng một endpoint `GET /why-denied?id=...` tự do** để trả reason chi tiết cho mọi user. Endpoint giải thích cũng là **một điểm thực thi chính sách** (PEP) cần bảo vệ, rate limit và chống dò ID.

## 4. Threat model cho “giải thích quyền”

Đối tượng tấn công có thể lợi dụng:

| Kênh | Dữ liệu có thể rò | Kịch bản |
|---|---|---|
| HTTP 403/404 body | Existence, owner, tenant, classification | Đoán ID để liệt kê object |
| Different response time | Object existence, số ACL rule | Phân biệt ID không tồn tại với có tồn tại nhưng bị cấm |
| Log search UI | Token, email, địa chỉ nội bộ, policy input | Nhân viên không đủ quyền tìm dữ liệu |
| Log forwarding | Header, raw JSON, secret | Gửi nhầm đến SIEM/vendor thứ ba |
| Exception stack trace | SQL, schema, internal endpoint, role name | Bị đưa vào error response |
| Tracing attributes | URL chứa token, resource ID nhạy cảm | Collector cho nhiều nhóm xem |
| Metrics labels | User ID, tenant, document ID | Cardinality cao và rò identifier |
| OPA decision logs | Toàn bộ `input`/`result` | Decision logging bật mà không mask |
| Support chatbot/ticket | Nội dung audit chép nguyên | Người nhận ticket không được phép biết |
| CSV export | Full decision history, ACL graph | Export không scope theo người xem |
| Cache reason | Explain của actor A được dùng cho B | Key thiếu subject/tenant/action |
| Multi-tenant admin UI | Log của tenant khác | Filter theo tenant chỉ ở frontend |

Bảo vệ dữ liệu không dừng ở response. **Logs, traces, metrics, dashboards, backups, tickets và export** đều nằm trong phạm vi kiểm soát truy cập của dữ liệu audit.

## 5. Thiết kế reason code ổn định, tránh dùng thông điệp tự do

Nên dùng enum/tập mã ngắn, được quản trị và version hóa:

~~~text
ALLOW_OWNER
ALLOW_ACTIVE_SHARE
ALLOW_TENANT_ADMIN

DENY_UNAUTHENTICATED
DENY_TENANT_MEMBERSHIP
DENY_ACTION_NOT_ALLOWED
DENY_RESOURCE_NOT_VISIBLE
DENY_OBJECT_PERMISSION
DENY_RESOURCE_RESTRICTED
DENY_POLICY_CONSTRAINT
DENY_EXPLICIT_RULE

ERROR_POLICY_UNAVAILABLE
ERROR_POLICY_INPUT_INVALID
ERROR_POLICY_VERSION_UNSUPPORTED
ERROR_EVALUATION_FAILED
~~~

Danh sách trên **là thiết kế ứng dụng minh họa**, không phải enum mặc định của Spring Security. Tách `ERROR` khỏi `DENY` để phân biệt thiếu quyền với lỗi vận hành, nhưng cả hai đều **không cho hành động nhạy cảm tiếp tục**.

Một mã tốt nên:
- Có ngữ nghĩa ổn định và không chứa dữ liệu động.
- Mô tả **loại nguyên nhân**, không mô tả chủ thể/tài nguyên cụ thể.
- Gắn policy/rule revision để có thể diễn giải theo thời gian.
- Đủ để nhóm được cấp quyền điều tra nhưng không tiết lộ raw ACL.
- Có bảng ánh xạ public code được review bảo mật.
- Không gắn exception message, SQL fragment hoặc tên tài liệu vào chính code.
- Có contract về precedence khi nhiều rule từ chối.

**Không đặt code là `DENY_OWNER_alice@example.com` hoặc `TENANT_acquisition_2026_LOCKED`.** Chính tên code đã rò dữ liệu.

## 6. Khi nhiều rule cùng từ chối, lưu nguyên nhân nào?

Một PDP có thể gặp đồng thời:
- Actor không có membership tenant.
- Actor thiếu role DOCUMENT_WRITE.
- Document bị khóa.
- Share WRITE đã bị revoke.

Có ba cách:
1. **First-failure:** lưu reason của điều kiện bắt buộc đầu tiên thất bại, theo thứ tự policy đã định.
2. **Primary + secondary:** lưu một mã chính và tập mã phụ **đã được kiểm soát** cho audit nội bộ.
3. **Decision trace hạn chế:** lưu các rule IDs và kết quả nếu nghiệp vụ/điều tra cần, với phân quyền/hạn lưu riêng.

Không đòi PDP phải **truy vấn thêm thông tin nhạy cảm** chỉ để giải thích cho một caller chưa đủ quyền. Ví dụ membership tenant đã thất bại thì có thể trả `DENY_TENANT_MEMBERSHIP` và **không** đi tra tên owner hay danh sách grant trên document kia.

Thứ tự kiểm tra cũng giúp chống lộ thông tin: xác thực → tenant membership → role/action → resource tenant → ACL/object → business state. Nếu caller không được biết tài nguyên, dừng sớm thay vì ghi trace “tài liệu SECRET do CEO sở hữu”.

Một thay đổi thứ tự policy có thể thay reason code dù effect vẫn DENY. Hãy gắn policy version và test, tránh giả định reason code là định danh bất biến của một sự kiện kinh doanh.

## 7. Audit schema tối thiểu: đủ điều tra nhưng không chứa payload

Một record có thể thiết kế:

~~~json
{
  "eventSchemaVersion": 1,
  "eventType": "AUTHORIZATION_DECISION",
  "eventId": "evt-2026-7f13",
  "requestId": "req-7814",
  "decisionId": "dec-a9f2",
  "occurredAt": "2026-11-05T05:30:00Z",
  "outcome": "DENY",
  "reasonCode": "DENY_OBJECT_PERMISSION",
  "policyId": "documents-access",
  "policyVersion": "v17",
  "actorRef": "pseudonymized-actor-42",
  "tenantRef": "tenant-ref-08",
  "resourceType": "Document",
  "resourceRef": "opaque-doc-ref",
  "action": "DOCUMENT_READ",
  "enforcementPoint": "DocumentQueryService.read",
  "decisionSource": "local-pdp",
  "executionOutcome": "BLOCKED"
}
~~~

**Đây là schema minh họa, không phải object Spring/OPA mặc định.** Trong production:
- `occurredAt` lấy từ đồng hồ server, ghi timezone rõ.
- `eventId`/`decisionId` không được xem là credential.
- `actorRef` có thể cần pseudonymization nếu user ID là PII.
- `tenantRef` và `resourceRef` có thể cũng là dữ liệu nhạy cảm; mức độ chi tiết phụ thuộc access control của audit store.
- `resourceType`, `action`, `policyVersion` thường hữu ích cho thống kê và debugging.
- `executionOutcome` phân biệt **quyết định** với **việc có thực thi/commit được không**.
- Có thể thêm `durationMs`, `serviceName`, `traceId` hoặc ACL revision khi cần, nhưng không đưa mọi field “cho tiện”.

**Không mặc định lưu** full `Authentication`, `SecurityContext`, `HttpServletRequest`, toàn bộ `Document`, request/response body, access token hoặc full policy input. Các object này có thể chứa secret và PII; thêm vào audit sẽ tạo một bản sao dữ liệu khó kiểm soát.

## 8. JSON structured logging và chuẩn hóa giá trị

Ưu tiên các field cố định thay vì nối chuỗi:

~~~json
{
  "event": "authz.decision",
  "outcome": "DENY",
  "reason": "DENY_ACTION_NOT_ALLOWED",
  "policyVersion": "v17",
  "action": "DOCUMENT_WRITE",
  "resourceType": "Document",
  "requestId": "req-7814"
}
~~~

Cách này dễ query, alert và thống kê hơn chuỗi “Alice không có quyền vì…”. Một số nguyên tắc:
- Danh sách field cho phép (**allowlist**) và kiểu dữ liệu cố định.
- Enum cho outcome/reason/action; validate dữ liệu từ PDP trước khi log.
- Giới hạn chiều dài, ký tự điều khiển và Unicode control cho field từ request.
- Logger/encoder escape newline, tab, dấu nháy và delimiter; không tự nối raw dữ liệu user vào log line.
- Tránh duplicate keys/schema drift khiến pipeline SIEM đọc nhầm.
- Không cho client tự quyết định `eventType`, `reasonCode` hoặc `policyVersion`.
- Phân biệt reason của PDP với exception của network; không gắn `error.getMessage()` tùy ý.

Nếu cần metadata động, dùng whitelist và classification theo từng trường. Với chuỗi input không tin cậy như URL path, user agent hoặc request ID từ header, cần **giới hạn và sanitize**; không giả định logger JSON tự kiểm soát lượng dữ liệu hoặc độ tin cậy.

## 9. Redact, mask, pseudonymize: không phải một thao tác

| Kỹ thuật | Cách làm | Khi nào phù hợp? | Giới hạn |
|---|---|---|---|
| **Omit/allowlist** | Không tạo field nhạy cảm | Mặc định tốt nhất | Cần chọn schema trước |
| **Redaction** | Loại bỏ nguyên field | Token, mật khẩu, nội dung bí mật | Mất khả năng điều tra field đó |
| **Mask** | Thay bằng `[REDACTED]` | Muốn chứng minh field đã được xử lý | Dữ liệu có thể rò qua field khác |
| **Pseudonymization** | Mã tham chiếu có thể đối chiếu theo cơ chế hạn chế | Audit actor/resource khi không cần tên thật | Vẫn có thể là dữ liệu cá nhân và cần bảo vệ |
| **Keyed HMAC** | Mã giả ổn định từ ID qua khóa bí mật | Join audit theo actor mà không lưu ID gốc | Phải bảo vệ/rotate key, tránh replay/leak mapping |
| **Encryption at rest** | Mã hóa dữ liệu lưu | Audit store có trường nhạy cảm hợp lệ | Không thay phân quyền/retention |
| **Hash thường** | SHA-256 raw email/user ID | Thường **không đủ** để ẩn ID đoán được | Dễ dictionary/brute-force khi miền ID nhỏ |

**Hash không tự đồng nghĩa ẩn danh.** Email, mã tenant và user ID có thể có tập giá trị dễ đoán; SHA-256 của chúng vẫn có thể bị dò. Nếu cần alias ổn định, cân nhắc HMAC với secret lưu trong KMS/Vault và thiết kế key rotation/version, nhưng HMAC cũng có khả năng liên kết hành vi của cùng actor, nên vẫn cần hạn chế truy cập.

Không mask bằng cách **chỉ thay 4 ký tự cuối** của một token/ID dài rồi coi là an toàn. Kết hợp nhiều field như IP, thời gian, tenant, action có thể nhận diện lại một người.

**Bảo vệ tốt nhất là không tạo và không truyền trường không cần thiết**, thay vì ghi đầy đủ rồi hy vọng pipeline downstream sẽ xóa.

## 10. Dữ liệu thường phải loại khỏi audit và logs

Theo OWASP Logging Cheat Sheet, cần đặc biệt chú ý những loại dữ liệu như:
- Mật khẩu, OTP, recovery code, API key, token phiên, OAuth access/refresh token.
- Cookie, session identifier hoặc presigned URL có chữ ký.
- Private keys, secret, database credentials và connection strings.
- Dữ liệu tài chính, thẻ thanh toán, số tài khoản, thông tin sức khỏe.
- Hồ sơ cá nhân hoặc định danh nhạy cảm; địa chỉ/email khi không có nhu cầu hợp pháp.
- Internal-only file paths, internal service hostnames, schema/SQL query có thể tiết lộ cấu trúc.
- Nội dung tài liệu, tên folder SECRET, chủ sở hữu, danh sách ACL/SID.
- Dữ liệu phân loại cao hơn mức mà hệ thống log được phép lưu.

Không có nghĩa **mọi actor ID đều phải bỏ**: audit điều tra có thể cần một ID có kiểm soát. Nhưng quyết định phải theo **mục đích, phân loại, hợp pháp và access control**; hạn lưu và truy cập log phải phù hợp nghĩa vụ của tổ chức.

Một quyết định DENY liên quan document nhạy cảm **không cho phép** ghi bản sao document vào log chỉ để “giải thích dễ hơn”.

## 11. Cần giải thích được điều gì mà không cần raw data?

Một hồ sơ điều tra có thể đủ nếu chứa:
- Policy ID/version và reason code.
- Action/resource type, resource opaque reference.
- Subject/tenant reference đã được bảo vệ.
- Decision time, request/trace/decision ID.
- PEP name và enforcement outcome.
- Membership/ACL revision khi hợp lý.
- Trust/freshness indicator của dữ liệu đánh giá.
- Error category **nếu** evaluation không hoàn thành.

Ví dụ:

~~~text
decisionId=dec-a9f2
outcome=DENY
reason=DENY_ACTION_NOT_ALLOWED
policy=documents-access@v17
action=DOCUMENT_DELETE
resourceType=Document
pep=DocumentCommandService.delete
execution=BLOCKED
~~~

Đội hỗ trợ đủ quyền có thể kết luận “policy v17 từ chối action DELETE” mà không cần đọc tên chủ sở hữu, nội dung document hoặc role của những người khác.

Nếu cần điều tra cụ thể hơn, dùng một **hệ tra cứu có xác thực và audit** để giải mã opaque references khi được phép. Đừng lưu tất cả raw attributes vào log chung để tránh bước tra cứu có kiểm soát.

## 12. Spring Security: Authorization Events hỗ trợ quan sát nhưng không thay audit nghiệp vụ

Spring Security cung cấp `AuthorizationEventPublisher` và `SpringAuthorizationEventPublisher` để phát authorization events, bao gồm `AuthorizationDeniedEvent`. Theo tài liệu Spring Security, event cấp quyền `AuthorizationGrantedEvent` **không được publish mặc định** vì có thể rất nhiều; nếu cần, phải cấu hình có chọn lọc.

Ví dụ cấu hình:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authorization.AuthorizationEventPublisher;
import org.springframework.security.authorization.SpringAuthorizationEventPublisher;

@Configuration
class AuthorizationEventsConfiguration {

    @Bean
    AuthorizationEventPublisher authorizationEventPublisher(
            ApplicationEventPublisher applicationEventPublisher) {
        return new SpringAuthorizationEventPublisher(
                applicationEventPublisher);
    }
}
~~~

Đây là **snippet tích hợp Spring Security**, không phải chương trình Java 17 standalone. Cần cấu hình security thích hợp trong project và đối chiếu API theo version.

Lắng nghe event:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.security.authorization.event.AuthorizationDeniedEvent;

@Component
class AuthorizationDeniedObserver {

    @EventListener
    public void onDenied(AuthorizationDeniedEvent<?> event) {
        // Đưa tín hiệu DENY vào metric/telemetry đã thiết kế.
        // KHÔNG logger.info("{}", event.getObject());
        // KHÔNG logger.info("{}", event.getAuthentication().get());
        // Nếu cần audit, chuyển sang schema allowlist và reason
        // do policy domain trả về qua kênh đã kiểm soát.
    }
}
~~~

**Hai điểm quan trọng:**
1. Event cho biết một authorization check đã bị từ chối, nhưng **không tự chứa reason code nghiệp vụ của mọi custom PDP**. Nếu cần `DENY_OWNER_SCOPE` hoặc policy revision, phải thiết kế kênh metadata domain/decision record riêng, không bịa rằng Spring event tự biết nguyên nhân.
2. `getObject()` có thể là secured object, method invocation hoặc request/context; `getAuthentication()` có thể mang principal/authorities/credentials. **Không log nguyên object** qua `toString()`. Hãy chỉ trích xuất field đã được allowlist hoặc ghi một event tổng quát.

Nếu bật granted events cho mọi request sẽ dễ gây nhiễu, tốn tài nguyên và tăng số dữ liệu audit. Chọn lọc theo nghiệp vụ, ví dụ grant quyền quản trị, export nhạy cảm hoặc hành động break-glass; test phiên bản API vì cấu hình predicate phát event có thể thay đổi giữa các version.

## 13. Authentication events khác authorization events

Phân biệt:
- **Authentication success/failure:** đăng nhập, token/credential validation; có các event như `AuthenticationSuccessEvent`, `AuthenticationFailureEvent` trong cấu hình tương ứng.
- **Authorization allow/deny:** một actor đã hoặc chưa được phép làm action trên resource.
- **Business execution:** PEP cho phép nhưng transaction có thành công, có ghi file, commit hay rollback?

Một lần HTTP 403 có thể do method policy, thiếu CSRF ở route yêu cầu bảo vệ hoặc một ràng buộc khác; đừng gắn mọi 403 thành `DENY_OBJECT_PERMISSION` mà không có nguồn quyết định rõ.

**Không lấy mật khẩu, token hoặc authentication exception message làm audit authorization reason.** Authentication và authorization có mục đích truy vết khác nhau. Có thể liên kết chúng bằng request/trace ID và subject alias an toàn, nhưng quyền đọc log cũng có thể khác.

## 14. PDP và PEP cần hai kết quả, không chỉ một log

Tách:
- **PDP Decision record:** “với input đã xác minh, policy v17 trả DENY vì `DENY_ACTION_NOT_ALLOWED`”.
- **PEP Enforcement record:** “service đã chặn, không gọi repository.update”.
- **Business outcome:** “transaction đã commit” hoặc “rolled back” khi quyết định ALLOW.

Ví dụ:

~~~json
{
  "decisionId": "dec-123",
  "policyVersion": "v17",
  "effect": "ALLOW",
  "reasonCode": "ALLOW_OWNER"
}
~~~

và:

~~~json
{
  "decisionId": "dec-123",
  "pep": "DocumentCommandService.rename",
  "action": "DOCUMENT_WRITE",
  "executionOutcome": "ROLLED_BACK",
  "errorCategory": "OPTIMISTIC_CONFLICT"
}
~~~

PDP trả ALLOW **không chứng minh mutation đã commit**. PEP có thể chặn do obligation, database version conflict, transaction rollback hoặc lỗi lưu trữ. Khi phân tích incident, cần biết cả decision và enforcement.

Không log nội dung title cũ/mới chỉ vì update thất bại. Sử dụng stable action/resource ref và error category.

## 15. Giải thích ở API: ánh xạ lỗi một chiều, không lộ sự tồn tại object

Một bảng ánh xạ:

| Kết quả nội bộ | Public HTTP/code gợi ý | Điều cần tránh |
|---|---|---|
| Chưa xác thực | 401 / `AUTHENTICATION_REQUIRED` | Tiết lộ user nào tồn tại |
| Role chức năng không đủ, action đã biết | 403 / `ACTION_NOT_AVAILABLE` | Liệt kê role của người khác |
| Không tìm thấy resource **trong scope được phép** | 404 / `RESOURCE_NOT_AVAILABLE` | Xác nhận resource có thật ở tenant khác |
| Object ACL DENY trên tài nguyên không được xem | 404 / `RESOURCE_NOT_AVAILABLE` | Nói tên owner/classification |
| Resource bị khóa, caller đã có quyền xem | Có thể 409 / `RESOURCE_NOT_EDITABLE` | Trả status chi tiết cho người không được thấy resource |
| PDP timeout / error | 503 / `AUTHORIZATION_UNAVAILABLE` | Fallback ALLOW; trả stack trace |
| Rule không áp dụng/abstain | Từ chối theo policy tổng hợp | Coi `null` là ALLOW |

Đây là **thiết kế API gợi ý**, không phải mapping mặc định của Spring Security. Trong một số domain, 403 cho resource ACL DENY là phù hợp nếu caller đã được phép biết resource tồn tại. Cần threat model: mục tiêu chính là **không xác nhận sự tồn tại hoặc thuộc tính của tài nguyên ngoài scope**.

Một response dạng Problem Details:

~~~json
{
  "type": "https://api.example/problems/resource-not-available",
  "title": "Resource not available",
  "status": 404,
  "code": "RESOURCE_NOT_AVAILABLE",
  "requestId": "req-7814"
}
~~~

Nếu dùng Spring Framework `ProblemDetail`, những field ngoài chuẩn như `code`, `requestId` được cấu hình như extensions của ứng dụng. Không gửi `reasonCode=DENY_TENANT_MISMATCH` hoặc tên tenant thật vào response khi điều đó cho biết object tồn tại ở tenant kia.

## 16. Không chỉ nội dung: HTTP status, timing và kích thước cũng có thể rò

Ngay cả khi message giống nhau, caller có thể thử nhiều ID và đo:
- 404 trả trong 5ms cho ID không tồn tại, 403 trong 150ms cho ID có ACL.
- JSON error khác số field hoặc độ dài theo từng reason.
- Rate limit hoặc cache hit pattern thay đổi khi resource tồn tại.
- Endpoint chi tiết có redirect/challenge khác nhau khi object thuộc tenant khác.

Không phải lúc nào cũng cần constant-time authorization; điều này phụ thuộc độ nhạy của tài nguyên và kịch bản enumeration. Nhưng với đối tượng bí mật, nên:
- Trả cùng lớp public response cho “không tồn tại” và “ngoài scope”.
- Không tải/serialize resource ngoài quyền.
- Không làm timing cố ý phụ thuộc vào owner/ACL graph nếu tránh được.
- Rate limit theo identity/IP/service context với chính sách phù hợp.
- Kiểm thử enumeration bằng tập ID tồn tại và không tồn tại, kiểm tra response/body/headers và phân bố latency.
- Không đưa bí mật trong `Location`, `WWW-Authenticate` detail hoặc custom error headers.

**Che nội dung nhưng để status khác nhau vẫn có thể là leak.** Ngược lại, không nên tuyên bố timing không có gì để lộ nếu chưa đo.

## 17. Decision ID và request ID: giúp hỗ trợ mà không phải đưa raw reason

Một mẫu giao tiếp:

~~~text
Người dùng:
  "Không thể mở tài liệu."
UI:
  "Tài nguyên không khả dụng trong phạm vi truy cập."
  "Mã yêu cầu: req-7814"
Support có quyền:
  tra req-7814 -> dec-a9f2 ->
  effect=DENY, reason=DENY_ACTION_NOT_ALLOWED,
  policy=documents-access@v17
~~~

Mã yêu cầu nên:
- Được tạo bằng cơ chế khó đoán hoặc ít nhất không chứa PII/secret.
- Không mang quyền truy cập; chỉ dùng tra cứu theo chính sách.
- Không cho phép user suy đoán ID của request khác rồi đọc audit.
- Tránh reuse ở nhiều request hoặc quy trình có trust khác.
- Có thời gian/hạn lưu và index phù hợp để hỗ trợ.
- Có khả năng nối giữa HTTP, service, PDP và background worker khi cần.

**Một correlation ID không phải capability để xem log.** Dịch vụ support luôn phải kiểm tra agent/tenant/ticket entitlement trước khi tra cứu. Không tạo endpoint “biết requestId là xem được toàn bộ decision JSON”.

## 18. Pseudonymize actor/resource để có thể nối log

Lưu toàn bộ email, userId và documentId gốc trong log thường không cần thiết. Khi phải phân tích tần suất DENY của cùng actor, có thể dùng actor reference ổn định.

Các hướng:
1. **Internal opaque ID:** mapping user account → random ID, bảng mapping có quyền riêng.
2. **Keyed HMAC:** tính token theo secret server, tenant namespace và canonical identifier.
3. **One-time alias:** ngẫu nhiên theo request, tốt cho privacy nhưng không thể group theo actor dài hạn.
4. **Encrypted identifier:** mã hóa có key management nếu cần giải mã theo quy trình điều tra.

Với HMAC, cần:
- Khóa đủ mạnh, lưu trong KMS/secret manager, không trong source code/log.
- Dùng canonical byte representation, namespace issuer/tenant để tránh collision/đánh đồng user.
- Version của key để hỗ trợ rotation và thay đổi alias.
- Kiểm soát nhu cầu theo dõi xuyên thời gian và giới hạn ai được truy vấn.
- Không dùng hash plain với dữ liệu dễ đoán như email hay số account.
- Không tuyên bố pseudonymized data là dữ liệu “không còn tính cá nhân” theo mọi quy định.

Có thể giữ raw identifiers trong một audit store kiểm soát chặt nếu có cơ sở và nhu cầu điều tra; vấn đề là **hạn quyền và hạn lưu**, không phải ép mọi hệ thống dùng cùng một phương pháp giả danh.

## 19. OPA decision logs: đừng bật rồi gửi nguyên input

Open Policy Agent có thể xuất **decision logs** chứa thông tin về policy query, input, result, bundle metadata và decision ID. Nếu PEP gửi principal email, JWT-derived claims, resource owner hoặc classification trong input, một bản decision log mặc định có thể chứa các thuộc tính đó.

OPA cung cấp cơ chế masking policy ở `data.system.log.mask` để loại bỏ hoặc thay trường trong event **trước khi log được gửi**. Ví dụ Rego minh họa:

~~~rego
package system.log

mask contains "/input/accessToken"

mask contains "/input/resource/confidentialTitle"

mask contains {
    "op": "upsert",
    "path": "/input/subject/email",
    "value": "[REDACTED]"
}
~~~

Cú pháp trên dùng **Rego v1-style**, cần test với OPA version và cấu trúc decision event thực tế. Các JSON Pointers trong OPA masking có giới hạn đường dẫn được hỗ trợ; kiểm tra tài liệu chính thức trước khi đưa vào production.

Nguyên tắc vận hành:
- **Không gửi token vào PDP input nếu có thể tránh**; PDP nhận subject/attributes tối thiểu đã xác minh.
- Nếu cần policy-specific attributes, dùng masked input/trace theo data classification.
- Mask cả `input` **và** `result` nếu result có sensitive explanation/obligation.
- Kiểm thử masking với nested arrays, optional fields, field rename và policy version mới.
- Không chỉ bảo vệ remote upload: nếu bật console logging/custom plugins, cần kiểm tra mọi kênh.
- Áp quyền cho collector, retention, TLS và log routing của OPA.
- Không coi `decision_id` tự động là secret hay token; nó chủ yếu để correlate, nhưng audit lookup vẫn phải kiểm soát quyền.

OPA hỗ trợ các thao tác remove/upsert trong masking policy và ghi nhận đường dẫn bị erased/masked. **Không suy luận rằng chỉ bật decision logging là đã tự che sensitive input.** Cần cấu hình mask đúng schema.

Tham khảo: [OPA Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs) và [OPA Configuration](https://www.openpolicyagent.org/docs/configuration).

## 20. Debug logging của Spring Security cần kiểm soát

Mức DEBUG/TRACE trong Spring Security rất hữu ích để chẩn đoán security filter chain, method invocation và rule matching, nhưng **không nên bật tràn lan ở production** chỉ để biết vì sao DENY.

Rủi ro có thể gồm:
- Thông tin request path/query chứa dữ liệu nhạy cảm.
- Principal/authority hoặc exception detail được log qua thư viện/ứng dụng.
- Mức log lớn gây quá tải lưu trữ, làm lộ cấu trúc chính sách.
- Debug bị quên bật sau incident, dẫn đến thu thập dữ liệu lâu dài.

Thực hành tốt:
1. Mặc định dùng structured decision logs tối thiểu và metrics.
2. Chỉ bật DEBUG có chọn lọc theo service/category và thời hạn đã phê duyệt.
3. Kiểm tra nội dung thực tế bằng test/staging trước khi bật production.
4. Chặn headers như `Authorization`, `Cookie`, `Set-Cookie`, URL có signed token.
5. Có runbook tự tắt debug, cơ chế kiểm soát truy cập và audit ai bật.
6. Không dùng `Authentication.toString()` hay `HttpServletRequest.toString()` như giải thích cho user.
7. Không log full JPA entity, danh sách ACL/GrantedAuthority hoặc exception object không cần thiết.

**Spring Authorization Events không tự thay một hệ thống audit có reason code.** Nếu cần lý do nghiệp vụ, thiết kế decision model/metadata của PDP và PEP trước.

## 21. Mối liên hệ với PEP–PDP và chính sách động

Đối với chính sách động:
- **PDP** biết những rule nào cho ALLOW/DENY, policy revision và data sources.
- **PEP** biết quyết định ấy đã được áp dụng ở endpoint/service nào, có thực thi side effect không, và công khai được gì.
- **PIP** biết nguồn thuộc tính (owner, membership, ACL, trạng thái), nhưng không nên gửi toàn bộ object ra logs.
- **PAP** biết ai sửa, duyệt, phát hành, rollback policy.

Có thể tách:
~~~text
PDP:
  EvaluationResult(effect, internalReasonCode, ruleVersion, decisionId)

PEP:
  check effect == ALLOW
  enforce obligations and resource/action binding
  publish safe enforcement event
  map public explanation from internal result

Audit sink:
  store allowed schema, with retention/access control
~~~

Đừng đưa reason mapping public vào từng controller một cách rải rác. Một **ExplanationMapper** dùng chung theo resource class và caller disclosure level giúp tránh mỗi endpoint rò một lượng thông tin khác nhau.

Nhưng cũng không đẩy toàn bộ user-facing content sang PDP: PDP quyết định theo policy; PEP/API gateway hiểu **đối tượng nhận thông điệp và quyền xem lời giải thích**. Một remote PDP có thể trả reason chi tiết cho caller là service, nhưng không đồng nghĩa caller HTTP được xem reason đó.

## 22. Đặt điểm audit ở đâu để vừa có nguyên nhân vừa có kết quả?

Ba điểm có giá trị:
1. **Sau policy evaluation:** event chứa effect/reason/version, chưa có execution outcome.
2. **Sau enforcement gate:** event cho biết request đã bị chặn hay được cho tiếp tục.
3. **Sau transaction/side effect:** event cho biết commit/rollback, download/export/queue status.

Có thể kết nối bằng decisionId/traceId nhưng không bắt buộc ghi mọi event ở mọi request nếu lưu lượng rất lớn. Chọn mức độ theo rủi ro, business need, luật áp dụng và performance. Ví dụ chỉ lưu DENY đầy đủ ở operation nhạy cảm, sampling ALLOW thường, nhưng luôn audit grant/revoke hoặc break-glass theo chính sách.

Nếu event được ghi bằng transaction/outbox, cần hiểu:
- Audit policy DENY có thể diễn ra **ngoài transaction nghiệp vụ** do không có transaction nào bắt đầu.
- Audit ALLOW nhưng transaction rollback phải phản ánh `ROLLED_BACK`, không dùng ALLOW làm bằng chứng thay đổi DB thành công.
- Nếu audit là điều kiện bắt buộc theo policy, outage audit sink có thể khiến operation bị chặn hoặc dùng durable local outbox theo contract.
- Ghi raw log trong cùng thread có thể làm tăng latency; async logging có rủi ro mất dữ liệu, cần mô hình reliability.
- Queue consumer phải bảo vệ dữ liệu audit và tránh duplicate khi retry/idempotency.

Không ghi “effect=ALLOW, status=SUCCESS” ngay lúc PDP trả ALLOW nếu repository còn chưa chạy.

## 23. Transaction, TOCTOU và độ tươi của reason

Một quyết định:

~~~text
T1: policy v17 -> ALLOW vì actor là owner
T2: owner được chuyển sang người khác
T3: PEP vẫn WRITE theo quyết định T1
~~~

Audit từ T1 có thể **giải thích đúng quá khứ**, nhưng không chứng minh thao tác T3 hợp lệ theo dữ liệu hiện thời. Để tránh hiểu lầm:
- Ghi decision time và resource/ACL revision nếu cần.
- Với owner-only WRITE, dùng guarded SQL theo actor+tenant+owner+status+version tại mutation boundary.
- Với grant/ACL ở bảng khác, xác định transaction/isolation, lock/revision protocol.
- Recheck khi action chạy qua queue/batch và policy có thể thay đổi.
- Không dùng cached ALLOW ngoài TTL/revocation semantics được công bố.
- Ghi actual execution status và optimistic conflict riêng với reason của PDP.

Nếu ghi reason “ALLOW_OWNER” rồi sau đó thao tác bị chặn do version stale, audit phải cho thấy **một authorization ALLOW ban đầu nhưng operation không commit**. Không sửa lại log lịch sử cho trùng trạng thái cuối; nên có event liên kết phản ánh tiến trình.

## 24. Bảo mật chính audit store

Audit store là mục tiêu hấp dẫn vì có thể chứa bản đồ quyền, cấu trúc tenant, hành vi truy cập và hành động admin.

Thiết kế tối thiểu:
- **RBAC/ABAC** cho quyền đọc audit, theo tenant/role/case/ticket.
- Principle of least privilege cho collector và người tra cứu.
- Encryption in transit và at rest, quản lý khóa.
- Retention/destruction theo mục đích, chính sách pháp lý/contract; tránh giữ vô hạn.
- Tamper resistance/integrity theo yêu cầu: append-only, signed records, digest chain hoặc immutable storage phù hợp.
- Tách quyền đọc, sửa cấu hình retention, xóa hoặc export audit.
- Audit **chính hành động truy cập audit**; alert truy vấn hàng loạt hoặc cross-tenant.
- Backup, export, replica, search index và third-party SIEM cũng tuân thủ classification.
- Có cơ chế correction/masking nếu log lỡ chứa sensitive data, bao gồm bản sao và backups theo chính sách.

Không coi “audit chỉ dành cho nội bộ” là đủ. Một support agent có thể được xem reason của ticket trong tenant A nhưng không được query toàn bộ policy decisions của tenant B.

### Retention theo mục đích

Các event có giá trị khác nhau:
- DENY thông thường có thể cần giữ ngắn hơn event grant/revoke vai trò quản trị.
- Security incident events có thể được lưu theo quy định điều tra riêng.
- Authz metrics aggregated có thể giữ lâu hơn chi tiết actor-level.
- Raw debug logs nên có TTL ngắn và bị loại khỏi export thông thường.

**Không đưa ra con số retention cố định** khi chưa có chính sách pháp lý của tổ chức. Thiết kế pipeline để áp dụng retention khác nhau theo category và hỗ trợ deletion/hold khi được yêu cầu hợp lệ.

## 25. Metrics và tracing: đừng biến identifier thành label

Một metric tốt:

~~~text
authorization_decisions_total{
  service="documents",
  action="READ",
  effect="DENY",
  reason="DENY_OBJECT_PERMISSION"
} 1284
~~~

Một metric không nên dùng:

~~~text
authorization_decisions_total{
  email="alice@company.example",
  documentId="123456789",
  accessToken="eyJ..."
} 1
~~~

Thêm user ID/resource ID vào metric labels tạo **cardinality cao**, chi phí lớn và khả năng rò dữ liệu sang dashboard. Hãy dùng enum/rule group/service/action/effect có số giá trị hữu hạn. Phân tích theo actor/resource chi tiết chỉ trong audit store có quyền riêng.

Với OpenTelemetry tracing:
- Không đưa raw `Authorization` header vào span attributes.
- Chỉ đưa `decisionId`/policy version hoặc outcome/reason code đã phân loại.
- Bảo đảm baggage không bị dùng để truyền secret và không tự lan sang service không đáng tin.
- Khi error, status và exception event không được chứa payload bí mật.
- Trace sampling phải được tính tới khi audit yêu cầu không bỏ sót event; **trace sampling không thay audit guarantee**.

## 26. Java 17 độc lập: lưu reason nội bộ, giải thích bên ngoài an toàn

Demo này sử dụng Java 17 thuần. Nó có một PDP nhỏ trả effect/reason, một PEP chỉ cho phép khi effect là ALLOW, một audit formatter **allowlist** trường được phép, và một public explanation mapper không tiết lộ owner/tenant trong thông điệp từ chối.

**Đây là ví dụ cơ chế**, không có Spring, database, logger thật hay xác thực danh tính. Trong production, các đối tượng actor/resource phải đến từ trusted authentication/PIP; ví dụ dùng hard-coded fixture để chứng minh logic.

Tạo file `SafeDecisionAuditDemo.java`:

~~~java
import java.util.Set;

public class SafeDecisionAuditDemo {
    enum Action { READ, WRITE }
    enum Effect { ALLOW, DENY, ERROR }

    enum Reason {
        OWNER_MATCH,
        ROLE_INSUFFICIENT,
        RESOURCE_NOT_VISIBLE,
        RESOURCE_RESTRICTED,
        PDP_UNAVAILABLE
    }

    record Actor(String id, String tenant, Set<Action> actions) { }
    record Resource(long id, String tenant, String owner, boolean locked) { }
    record Input(Actor actor, Resource resource, Action action) { }
    record Decision(Effect effect, Reason reason, String policyVersion) { }

    @FunctionalInterface
    interface Pdp {
        Decision decide(Input input);
    }

    static final class LocalPdp implements Pdp {
        @Override
        public Decision decide(Input input) {
            if (input == null || input.actor() == null
                    || input.resource() == null || input.action() == null) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
            }

            Actor actor = input.actor();
            Resource resource = input.resource();

            if (actor.tenant() == null
                    || resource.tenant() == null
                    || !actor.tenant().equals(resource.tenant())) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
            }
            if (actor.actions() == null
                    || !actor.actions().contains(input.action())) {
                return new Decision(
                        Effect.DENY, Reason.ROLE_INSUFFICIENT, "docs-v3");
            }
            if (resource.locked() && input.action() == Action.WRITE) {
                return new Decision(
                        Effect.DENY, Reason.RESOURCE_RESTRICTED, "docs-v3");
            }
            if (actor.id() != null && actor.id().equals(resource.owner())) {
                return new Decision(
                        Effect.ALLOW, Reason.OWNER_MATCH, "docs-v3");
            }
            return new Decision(
                    Effect.DENY, Reason.RESOURCE_NOT_VISIBLE, "docs-v3");
        }
    }

    static final class Pep {
        private final Pdp policy;
        private int executed;

        Pep(Pdp policy) {
            this.policy = policy;
        }

        String attempt(Input input) {
            Decision decision;
            try {
                decision = policy.decide(input);
                if (decision == null
                        || decision.effect() == null
                        || decision.reason() == null
                        || decision.policyVersion() == null) {
                    decision = new Decision(
                            Effect.ERROR, Reason.PDP_UNAVAILABLE, "unknown");
                }
            } catch (RuntimeException failure) {
                decision = new Decision(
                        Effect.ERROR, Reason.PDP_UNAVAILABLE, "unknown");
            }

            // Audit chỉ dùng allowlisted enums và metadata cố định.
            String audit = "audit outcome=" + decision.effect()
                    + " reason=" + decision.reason()
                    + " policy=" + decision.policyVersion();
            System.out.println(audit);

            String publicResponse;
            if (decision.effect() == Effect.ALLOW) {
                executed++;
                publicResponse = "public status=200 code=OK";
            } else if (decision.effect() == Effect.ERROR) {
                publicResponse =
                        "public status=503 code=AUTHORIZATION_UNAVAILABLE";
            } else {
                // Mọi DENY đều trả thông điệp chung trong demo.
                publicResponse =
                        "public status=404 code=RESOURCE_NOT_AVAILABLE";
            }
            System.out.println(publicResponse);
            return audit + "|" + publicResponse;
        }

        int executed() {
            return executed;
        }
    }

    public static void main(String[] args) {
        Actor owner = new Actor("an", "north",
                Set.of(Action.READ, Action.WRITE));
        Actor reader = new Actor("binh", "north",
                Set.of(Action.READ));
        Resource doc = new Resource(42, "north", "an", false);
        Resource otherTenant =
                new Resource(42, "south", "alice@example.com", false);
        Resource locked = new Resource(43, "north", "an", true);

        Pep pep = new Pep(new LocalPdp());
        pep.attempt(new Input(owner, doc, Action.READ));
        pep.attempt(new Input(reader, doc, Action.WRITE));
        pep.attempt(new Input(owner, otherTenant, Action.READ));
        pep.attempt(new Input(owner, locked, Action.WRITE));

        Pep errorPep = new Pep(input -> {
            throw new IllegalStateException(
                    "Sensitive backend detail must not be returned");
        });
        String result = errorPep.attempt(
                new Input(owner, doc, Action.READ));

        System.out.println("no-secret-exposed="
                + !result.contains("Sensitive backend detail"));
        System.out.println("executed-count=" + pep.executed());
    }
}
~~~

Chạy:

~~~bash
javac SafeDecisionAuditDemo.java
java SafeDecisionAuditDemo
~~~

Stdout chính xác:

~~~text
audit outcome=ALLOW reason=OWNER_MATCH policy=docs-v3
public status=200 code=OK
audit outcome=DENY reason=ROLE_INSUFFICIENT policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=DENY reason=RESOURCE_NOT_VISIBLE policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=DENY reason=RESOURCE_RESTRICTED policy=docs-v3
public status=404 code=RESOURCE_NOT_AVAILABLE
audit outcome=ERROR reason=PDP_UNAVAILABLE policy=unknown
public status=503 code=AUTHORIZATION_UNAVAILABLE
no-secret-exposed=true
executed-count=1
~~~

Phân tích:
- Với chủ tài liệu và action READ hợp lệ, PEP thực thi một lần.
- Thiếu role/action, sai tenant và document locked đều có **reason nội bộ khác nhau**.
- Cả ba DENY hiển thị **cùng một public code** để không tiết lộ chính sách hoặc tồn tại tài liệu trong demo.
- Lỗi PDP bị chuyển thành ERROR, không chạy action và không đưa exception message ra ngoài.
- Biến `executed` cuối chỉ bằng 1, khẳng định những request DENY/ERROR không tạo side effect minh họa.

**Giới hạn và điều chỉnh production:**
- Trong demo, `Actor` được dựng từ code chứ không qua Spring Authentication; không dùng các giá trị do client tự khai làm actor đáng tin.
- Audit formatter trong demo in console cho dễ thấy. Thực tế cần structured logger, correlation ID, sink bảo vệ và retention.
- `Decision.policyVersion` là string nội bộ; nếu nhận từ remote PDP, phải **validate/allowlist/limit** nó trước khi log. Không tự tin bất kỳ string nào do remote service trả.
- Một `null` decision hoặc một response malformed không được biến thành ALLOW.
- Việc trả HTTP 404 cho mọi DENY ở demo là lựa chọn chống enumeration, không phải chuẩn bắt buộc của mọi API; khi caller đã được phép xem resource có thể chọn code/message cụ thể khác theo policy.
- Quyết định ALLOW không đủ để ghi DB nếu owner/ACL thay đổi sau check; transaction/guard vẫn cần.

## 27. Ví dụ Spring: mapper giải thích quyền an toàn

Có thể định nghĩa một mapper thuộc lớp API:

~~~java
public record PublicAuthorizationError(
        String code, String message, String requestId) { }

public final class AuthorizationExplanationMapper {

    private AuthorizationExplanationMapper() { }

    public static PublicAuthorizationError denied(
            String requestId) {
        return new PublicAuthorizationError(
                "RESOURCE_NOT_AVAILABLE",
                "Tài nguyên không khả dụng trong phạm vi truy cập.",
                requestId);
    }

    public static PublicAuthorizationError unavailable(
            String requestId) {
        return new PublicAuthorizationError(
                "AUTHORIZATION_UNAVAILABLE",
                "Không thể xác minh quyền lúc này.",
                requestId);
    }
}
~~~

Đây là **snippet class Java**, không phải controller/exception handler hoàn chỉnh. Request ID cần đến từ correlation context đã kiểm soát và được validate, không lấy chuỗi vô hạn từ client.

Một `@RestControllerAdvice` hoặc Spring Security `AccessDeniedHandler` tùy vị trí phát sinh exception có thể sử dụng mapper. Cần lưu ý:
- Exception do method security ở service có thể được xử lý khác exception từ servlet filter.
- `ExceptionTranslationFilter` không phải catch-all cho mọi lỗi JPA/PDP.
- Một `AccessDeniedException` không tự nói được lý do nghiệp vụ; reason nên đến từ decision domain hoặc event correlation.
- Không đưa raw exception message làm public explanation.
- Với endpoint JSON, thống nhất mã lỗi, content type và response size để chống rò qua sự khác biệt không cần thiết.

## 28. Audit reason khi PDP quyết định qua nhiều nguồn

Nếu PDP sử dụng role, ACL, tenant membership, project policy và resource status, nguyên nhân có thể là:
- Input invalid.
- Membership không có/không còn active.
- Role/action không phù hợp.
- Resource không thuộc tenant đang xét.
- Grant bị thu hồi/hết hạn.
- Document locked/legal hold.
- Rule thời gian hoặc classification không đạt.
- PIP/DB timeout, không đủ dữ liệu để đánh giá.

Một bảng kết quả hợp lý:

| Tình huống | Effect | Reason nội bộ | Public response cho caller ngoài quyền |
|---|---|---|---|
| Không có membership tenant | DENY | `DENY_TENANT_MEMBERSHIP` | Chung, không xác nhận tenant |
| Sai action role | DENY | `DENY_ACTION_NOT_ALLOWED` | Action unavailable hoặc chung |
| Document khác tenant | DENY | `DENY_RESOURCE_NOT_VISIBLE` | 404 chung |
| Share READ bị revoke | DENY | `DENY_OBJECT_PERMISSION` | 404 chung |
| Resource LOCKED | DENY | `DENY_RESOURCE_RESTRICTED` | Chung; chi tiết chỉ cho người có quyền xem |
| Rule classification | DENY | `DENY_POLICY_CONSTRAINT` | Chung |
| PIP unavailable | ERROR | `ERROR_PIP_UNAVAILABLE` | 503 chung |
| Input thiếu trường đáng tin | ERROR hoặc DENY theo contract | `ERROR_POLICY_INPUT_INVALID` | Không lộ field nội bộ |
| ALLOW qua owner | ALLOW | `ALLOW_OWNER` | Không cần giải thích rộng |
| ALLOW qua share | ALLOW | `ALLOW_ACTIVE_SHARE` | Chỉ cho caller biết quyền của chính mình nếu phù hợp |

Nên tránh tách lý do quá chi tiết nếu bản thân reason code đã giúp suy luận những tài nguyên không được phép. Reason code chỉ được gửi cho đối tượng có quyền xem đúng mức.

## 29. Tính toàn vẹn và khả năng diễn giải audit theo thời gian

Chính sách động thay đổi liên tục. Một event v17 có thể khác v18 ngay cả khi action/actor/resource không đổi. Audit cần đủ để tái dựng **ngữ cảnh được phép lưu** và hiểu phiên bản lịch sử.

Các metadata có thể hữu ích:
- Policy ID + immutable revision/hash.
- Deployment/build version của PEP và PDP.
- Resource/ACL/membership version hoặc timestamp đã xác minh nếu liên quan.
- Decision timestamp, enforcement timestamp, commit status.
- Data source identifier (không phải secret DSN).
- Reason code schema version.
- Policy bundle revision của OPA nếu sử dụng.
- Mức consistency của PIP hoặc cache freshness khi decision phụ thuộc dữ liệu động.

**Không hứa rằng có policyVersion thì có thể replay nguyên quyết định** nếu không giữ input/data snapshot đúng hoặc dữ liệu PIP đã thay đổi. Việc lưu toàn bộ snapshot để replay lại có thể gây rò PII và vượt nhu cầu; cân nhắc môi trường kiểm thử policy với synthetic fixtures và trace đã giảm dữ liệu.

Audit record cần chống chỉnh sửa không được phép theo yêu cầu nghiệp vụ. Một hệ log có thể dùng immutable storage, append-only, audit writer separation, integrity hashes; nhưng phải kiểm tra quyền và bảo vệ key. Không giả định một file log text là “bằng chứng pháp lý” đủ mạnh chỉ vì nó có timestamp.

## 30. Kiểm thử: đúng quyết định và không rò thông tin

Ma trận bắt buộc:

| Trường hợp | Audit nội bộ | Public output / enforcement |
|---|---|---|
| ALLOW owner | Reason `ALLOW_OWNER` | Action chạy đúng; không lộ metadata thừa |
| DENY role/action | Reason `DENY_ACTION_NOT_ALLOWED` | Không chạy; message an toàn |
| DENY khác tenant | Reason `DENY_RESOURCE_NOT_VISIBLE` | Không xác nhận tài nguyên tồn tại |
| DENY ACL READ | Reason object permission | Không lộ tên owner/danh sách SID |
| DENY document SECRET/LOCKED | Reason restricted | Không gửi classification cho caller ngoài quyền |
| Resource ID không tồn tại | Reason not visible/not found theo policy | Cùng public response với resource ngoài scope khi cần |
| PDP timeout | ERROR category | Không chạy; 5xx/503, không stack trace |
| Missing/null result | ERROR/abstain theo contract | Không mặc định ALLOW |
| Exception chứa secret | Không log raw message | Secret không trong response, logs, traces |
| Log injection | Field newline/Unicode control | Event không tạo dòng log giả |
| AuthorizationDeniedEvent | Event được phát khi cấu hình | Listener không log full auth/object |
| Granted event | Sampling/config có chủ đích | Không tăng vô hạn dữ liệu |
| OPA input chứa nested PII | Mask/remove kiểm chứng | Remote/console logs không có PII |
| Mask policy thiếu đường dẫn | Test thất bại | Không cho rollout chưa an toàn |
| Tenant A xem audit tenant B | Bị chặn | Không xem reason/detail tenant khác |
| Export audit nhiều dòng | Đúng scope và rate limit | Không lộ token/ACL ngoài quyền |
| Policy v17 vs v18 | Version được lưu | Mapping public vẫn ổn định/chính xác |
| Audit sink outage | Có telemetry/fallback theo contract | Không vi phạm mandatory audit obligation |
| ACL revoke và cache stale | Có revision/decision trace | Không reuse ALLOW vượt SLA |
| Retry same request | Correlation/idempotency rõ | Không nhân bản side effect |
| Read/list/export/download | Audit theo rủi ro | Không làm lộ dữ liệu qua kênh phụ |

### Test chống enumeration

Tạo ít nhất ba loại ID:
1. ID không tồn tại.
2. ID tồn tại nhưng thuộc tenant khác.
3. ID tồn tại trong tenant nhưng actor không có ACL.

Với caller chưa có quyền biết ba đối tượng đó, kiểm tra response code, body, headers, redirection và nội dung lỗi **không tiết lộ khác biệt không được phép**. Đo timing distribution nếu threat model yêu cầu. Không dùng một script dò thông tin production không được cho phép; thực hiện trong test environment kiểm soát.

### Test logging/redaction

Capture output từ logger test:
- Không chứa `Authorization: Bearer`, cookie/session, email giả, title bí mật hoặc raw body.
- Event có reason enum, policy revision và request ID hợp lệ.
- Giá trị chứa `\n`, `\r`, dấu nháy, Unicode control được encode/giới hạn đúng.
- Khi exception được ném, không serialize `Throwable.toString()` vào audit chung.
- Đã kiểm tra **cả console logs, remote collector, traces và decision logs** thay vì chỉ kiểm tra app log.

## 31. Quy trình review một thay đổi reason code hoặc lời giải thích

Khi thay chính sách hoặc thêm lý do:
1. Xác định **ai được đọc** reason mới (public, tenant admin, security ops).
2. Kiểm tra reason có thể tiết lộ resource existence, owner, tenant, group hoặc rule chống gian lận không.
3. Thêm mã vào enum/contract, không dùng string động tùy ý.
4. Quy định precedence khi nhiều rule cùng từ chối.
5. Cập nhật public mapping; test 403/404 và xử lý ERROR.
6. Chỉ thêm audit fields thật sự cần, có classification và retention.
7. Kiểm tra OPA mask/schema/log collector cho field mới.
8. Cập nhật security review, unit tests, integration tests, data leakage tests.
9. Triển khai theo policy version, theo dõi tỷ lệ DENY và logging volume.
10. Khi cần rollback, audit cũ vẫn được giải thích theo reason schema version cũ.

Một change tưởng như vô hại từ “Không thể truy cập” sang “Tài liệu này thuộc phòng tài chính và bạn chưa được chia sẻ” có thể làm tăng đáng kể khả năng dò dữ liệu. Review nội dung lỗi cũng quan trọng như review SQL access predicate.

## 32. Checklist triển khai

- [ ] Có sự khác biệt rõ giữa effect, internal reason, public message và execution outcome.
- [ ] Mọi public explanation theo quyền được biết của caller, không lộ owner/tenant/ACL trái quyền.
- [ ] Internal reason code là enum/allowlist, không chứa PII, SQL hay exception text.
- [ ] Đã xác định precedence khi nhiều policy/rule cùng từ chối.
- [ ] Audit schema tối thiểu, versioned, có action/resource type/policy revision và correlation.
- [ ] Không log full Authentication, SecurityContext, request body, token, entity hoặc ACL graph.
- [ ] Redaction/masking được test ở **mọi kênh**: application, OPA, console, SIEM, traces, exports.
- [ ] Actor/resource reference có pseudonymization hoặc quyền truy cập phù hợp, không dùng hash yếu cho ID đoán được.
- [ ] Không coi requestId/decisionId là quyền truy cập vào audit.
- [ ] API giải thích lý do có authentication, authorization, rate limiting và tenant scope.
- [ ] Phân biệt 401, 403, 404 và lỗi PDP/PIP theo policy không tiết lộ object existence.
- [ ] Spring AuthorizationDeniedEvent được dùng đúng; granted events bật có chọn lọc nếu cần.
- [ ] Custom PDP reason được lưu bởi domain contract, không bịa rằng event của Spring tự biết rule.
- [ ] PEP không thực thi nếu PDP trả DENY, ERROR, null, timeout hoặc malformed response.
- [ ] Quyết định ALLOW được gắn đúng actor–tenant–action–resource và có freshness/TOCTOU guard khi cần.
- [ ] Decision và enforcement/commit logs được liên kết nhưng không đánh đồng.
- [ ] Log store mã hóa, có quyền đọc theo tenant/role/case, retention, audit access và kiểm soát export.
- [ ] Metric labels không chứa user ID/document ID/token và không gây high cardinality.
- [ ] Test enumeration, log injection, cross-tenant audit, revoke/cache stale và incident rollback.
- [ ] Có quy trình policy versioning, review reason codes và kiểm tra data leakage trước release.

**Kết luận:** Một hệ thống phân quyền tốt không chỉ biết **cho hay không cho**, mà còn biết **vì sao** để kiểm thử, vận hành và điều tra. Tuy nhiên, “giải thích tốt” **không đồng nghĩa “tiết lộ tối đa”**. Hãy lưu internal reason code và policy revision trong audit store được bảo vệ, liên kết decision với enforcement, ánh xạ sang thông điệp public tối thiểu theo quyền được biết của caller, và kiểm tra toàn bộ kênh logs/traces/OPA/exports. Khi không có quyết định ALLOW hợp lệ, PEP phải fail closed; khi có ALLOW, vẫn phải bảo vệ đúng tài nguyên và trạng thái tại thời điểm thực hiện.

## Tài liệu tham khảo

- [Spring Security — Authorization Events](https://docs.spring.io/spring-security/reference/servlet/authorization/events.html): cấu hình `AuthorizationEventPublisher`/`SpringAuthorizationEventPublisher`, denied events và chính sách publishing granted events.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager`, authorization results và điểm interception.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@PreAuthorize`, custom policy beans, method enforcement và proxy.
- [Spring Security — Authentication Events](https://docs.spring.io/spring-security/reference/servlet/authentication/events.html): phân biệt authentication success/failure với authorization decisions.
- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): exception translation/filter chain và security boundaries.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu không nên log, chuẩn hóa, log injection, bảo vệ truyền/lưu/truy cập/retention.
- [OPA — Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs): decision_id, input/result, masking/redaction và sink.
- [OPA — Configuration](https://www.openpolicyagent.org/docs/configuration): log reporting, masking/drop decisions.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): nguy cơ dò ID và truy cập tài nguyên ngoài quyền.
