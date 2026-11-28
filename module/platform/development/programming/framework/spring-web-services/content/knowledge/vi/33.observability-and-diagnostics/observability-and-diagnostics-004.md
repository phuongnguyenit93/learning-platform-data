# Che dữ liệu cá nhân, token, thông tin xác thực và nội dung nhạy cảm

Observability giúp đội vận hành hiểu một SOAP request đi qua hệ thống như thế nào, mất bao lâu, lỗi ở tầng nào và có ảnh hưởng đến đối tác nào. Nhưng log, trace, metric, exception và công cụ hỗ trợ cũng có thể trở thành nơi **tập trung bản sao của dữ liệu nhạy cảm**. Một access token chỉ cần xuất hiện trong log HTTP một lần có thể được dùng lại; một SOAP Envelope có thể chứa PII, thông tin tài chính, UsernameToken hoặc tài liệu đính kèm mà nhiều hệ thống downstream tiếp tục lưu trữ.

Bài học thuộc chương **Quan sát và chẩn đoán** của module `SPRING_WEB_SERVICES`. Module phát triển SOAP theo hướng contract-first bằng Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và client; đồng thời xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Vì thế, việc bảo vệ dữ liệu phải bao phủ **HTTP transport, SOAP Header/Body, attachments, security processing, application logs và telemetry**.

**Nguyên tắc chính:** chỉ ghi những trường thật sự cần cho vận hành; dùng allowlist thay cho việc ghi toàn bộ payload rồi cố che bằng regex; loại bỏ hoàn toàn secret có thể dùng lại; giảm/ẩn định danh cá nhân; kiểm tra output cuối cùng bằng test tự động.

Ví dụ hướng tới Java 17+, Spring Boot/Spring Security 6+, Spring-WS 4.1.x và Micrometer/OpenTelemetry. Tên package/config có thể khác theo version và logging stack. Bài không định nghĩa một bộ luật tuân thủ pháp lý cụ thể; tổ chức cần đối chiếu retention, data residency, consent và chính sách ngành của mình. Không có SPECIAL_NOTE bổ sung cho bài này.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân loại PII, dữ liệu nhạy cảm, authentication secrets, cryptographic material và operational metadata.
2. Thiết kế allowlist log an toàn cho SOAP operation mà không ghi nguyên Envelope.
3. Che Bearer/Basic credentials, cookies, UsernameToken, X.509 material, XML signature/encryption và dữ liệu attachment.
4. Phân biệt mask, redact, truncate, tokenize và pseudonymize/hash; chọn đúng thao tác theo mục đích.
5. Kiểm soát SOAP Fault, exception, tracing baggage, metrics labels, audit events và support bundles.
6. Thiết kế retention, access control, encryption và data deletion cho observability storage.
7. Xây test phát hiện secret/PII rò rỉ trong logs/traces/errors.
8. Debug production bằng correlation IDs, metadata và quy trình truy cập có kiểm soát mà không yêu cầu đối tác gửi credentials hoặc payload nhạy cảm.

## 1. Dữ liệu nào nhạy cảm trong SOAP integration?

Một SOAP request không chỉ có dữ liệu nghiệp vụ ở Body. Thông tin có thể nằm trong HTTP headers, SOAP Headers, XML attributes, text nodes, MIME attachments, exception messages và cả URL.

### 1.1. Phân loại dữ liệu theo cách xử lý

| Nhóm | Ví dụ trong SOAP service | Xử lý mặc định |
| --- | --- | --- |
| Authentication secrets | `Authorization: Bearer`, Basic password, API key, refresh token, session cookie | **Không log**; loại bỏ hoàn toàn |
| Password/credential material | Raw password, password hash, WS-Security PasswordText/PasswordDigest, client secret | Không log; hash lưu trữ cũng không đưa vào telemetry |
| Cryptographic private material | Private key, keystore password, HSM PIN, symmetric key, decrypted session key | **Tuyệt đối không log/export** |
| Personal data (PII) | Tên, email, phone, địa chỉ, ngày sinh, government ID | Không log theo mặc định; mask/tokenize nếu có use case được duyệt |
| Sensitive business data | Account/order details, giá, hợp đồng, medical/financial records, nội dung tài liệu | Chỉ log mã nghiệp vụ không nhạy cảm/aggregate cần thiết |
| Security metadata | Issuer, auth mechanism, cert fingerprint, validation outcome | Có thể ghi có kiểm soát; không ghi credential/token bytes |
| Operational metadata | Operation QName, SOAP version, status, latency, payload size, fault category | Thường có thể ghi nếu không kèm định danh nhạy cảm |

Không phải mọi giá trị ID đều là PII, nhưng `customerId`, `buyerId`, `accountNumber`, `orderId` có thể liên kết về cá nhân hoặc tiết lộ hành vi. Cần phân loại dựa vào khả năng liên kết và chính sách nội bộ, không dựa vào tên field trông “kỹ thuật”.

### 1.2. Secret có thể dùng lại khác PII

- **Secret có thể dùng lại:** kẻ khác cầm giá trị là có thể xác thực/giải mã/ký. Ví dụ access token còn hạn, refresh token, password, API key, private key. Xóa khỏi log là lựa chọn mặc định.
- **PII:** có thể cần cho nghiệp vụ, nhưng observability thường chỉ cần biết “đã xử lý khách hàng nào?” ở mức pseudonymous hoặc aggregate.
- **Business confidential:** không nhất thiết là PII nhưng vẫn có thể gây thiệt hại nếu tiết lộ, ví dụ mức giá hợp đồng, số dư, nội dung đơn hàng.

Đối với secret, `[REDACTED]` là thay thế trong log; **không lưu một bản hash của bearer token như field log mặc định**. Nếu cần correlate token trong security analytics, thiết kế một fingerprint riêng có khóa, giới hạn quyền truy cập và thời hạn; không dùng fingerprint để xác thực hoặc chia sẻ ngoài phạm vi được duyệt.

### 1.3. Data flow có nhiều điểm rò rỉ

~~~mermaid
flowchart LR
    A["HTTP request\nAuthorization/Cookie"] --> B["Servlet filters"]
    B --> C["SOAP message factory"]
    C --> D["SOAP Header/Body"]
    D --> E["WSS4J/interceptors"]
    E --> F["JAXB/endpoint/service"]
    F --> G["Database/downstream"]
    A -.-> L["Access logs/APM"]
    D -.-> X["Payload logger"]
    E -.-> Y["Security exceptions"]
    F -.-> Z["Application logs"]
    G -.-> M["SQL/audit traces"]
    L --> O["Log/trace storage"]
    X --> O
    Y --> O
    Z --> O
    M --> O
~~~

Mỗi thành phần có thể tự tạo bản ghi độc lập. Che dữ liệu ở `@Endpoint` không bảo vệ HTTP access log đã ghi Authorization trước đó; filter che Header không che SOAP Body logger; application logger không kiểm soát exception reporter hoặc APM agent.

## 2. Chính sách ghi log: allowlist thay vì blacklist

### 2.1. Log metadata, không log toàn SOAP Envelope

Một bản ghi request có ích thường chỉ cần:

~~~json
{
  "event": "soap.request.completed",
  "service": "orders",
  "operation": "{urn:example:orders:v1}SubmitOrder",
  "soapVersion": "1.2",
  "correlationId": "c-7f31a2",
  "partnerRef": "partner-17",
  "httpStatus": 200,
  "outcome": "SUCCESS",
  "durationMs": 84,
  "requestBytes": 1832,
  "responseBytes": 924
}
~~~

Giá trị trên là dữ liệu giả. `partnerRef` chỉ nên được dùng nếu là mã kỹ thuật không tiết lộ PII và quyền truy cập phù hợp. Không ghi Authorization, token, full URL có query string, SOAP Body, UsernameToken, certificate content hoặc attachment content.

### 2.2. Xây event từ các trường cho phép

Ví dụ application event với SLF4J:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public final class SoapAuditLogger {
    private static final Logger log =
        LoggerFactory.getLogger(SoapAuditLogger.class);

    public void completed(
            String operation,
            String correlationId,
            String partnerRef,
            int status,
            long durationMs,
            long requestBytes,
            String outcome) {

        // Chỉ nhận các field metadata đã duyệt.
        log.atInfo()
            .addKeyValue("event", "soap.request.completed")
            .addKeyValue("operation", safeOperation(operation))
            .addKeyValue("correlationId", safeId(correlationId))
            .addKeyValue("partnerRef", safePartnerRef(partnerRef))
            .addKeyValue("httpStatus", status)
            .addKeyValue("durationMs", Math.max(0, durationMs))
            .addKeyValue("requestBytes", Math.max(0, requestBytes))
            .addKeyValue("outcome", safeOutcome(outcome))
            .log("SOAP exchange completed");
    }

    private String safeOperation(String value) {
        return OperationNames.allowedOrUnknown(value);
    }

    private String safeId(String value) {
        return IdentifierPolicy.safeCorrelationId(value);
    }

    private String safePartnerRef(String value) {
        return PartnerRegistry.knownNonSensitiveRefOrUnknown(value);
    }

    private String safeOutcome(String value) {
        return OutcomeNames.allowedOrUnknown(value);
    }
}
~~~

`OperationNames`, `IdentifierPolicy`, `PartnerRegistry` và `OutcomeNames` là application helpers cần triển khai; `safeId` nên kiểm charset/length và nguồn sinh correlation ID. Không coi structured logging tự động làm an toàn: **giá trị field vẫn cần allowlist và kiểm soát**.

### 2.3. Tránh log theo kiểu string concatenation

~~~java
// KHÔNG an toàn:
log.info("SOAP request: {}", soapEnvelope);
log.debug("Authorization={}", authorizationHeader);
log.error("Failed request " + requestXml, exception);
~~~

Ngay cả khi log level hiện tại tắt, expression hoặc serialization có thể vẫn được tạo trước khi logger bỏ qua; dùng `isDebugEnabled()` không giải quyết vấn đề secret. Thay vào đó log operation, fault category, duration và correlation ID.

### 2.4. Không dựa vào blacklist field names

Một blacklist có thể che `password`, `token`, `secret`, nhưng bỏ sót:
- `credential`, `assertion`, `saml`, `jwt`, `apiKey`, `clientSecret`.
- SOAP namespace-specific field như `wsse:Password`, `wsse:BinarySecurityToken`.
- Alias nghiệp vụ như `nationalIdentity`, `taxNo`, `bankAccount`.
- Dữ liệu nhạy cảm trong nested arrays, Base64 text hoặc attachment.
- URL/query parameter có tên khác như `sig`, `code`, `access_key`.

Allowlist log fields dễ kiểm chứng hơn: chỉ những trường đã duyệt mới được serialize vào event. Blacklist có thể làm defense-in-depth nhưng không thay allowlist.

## 3. Che dữ liệu ở HTTP transport và Servlet layer

### 3.1. Những HTTP headers cần loại khỏi access log

SOAP qua HTTP thường mang credential ngoài Envelope:

~~~http
POST /ws/orders HTTP/1.1
Authorization: Bearer eyJ...<SECRET>
Cookie: JSESSIONID=...
X-Api-Key: ...
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:SubmitOrder"
X-Correlation-ID: c-7f31a2
~~~

Không ghi toàn bộ request headers. Thiết lập access log/reverse proxy để **chỉ chọn** method, route template, status, bytes, duration, user-agent đã kiểm soát và correlation ID do hệ thống sinh/validate. Loại tối thiểu:

- `Authorization`, `Proxy-Authorization`.
- `Cookie`, `Set-Cookie`.
- API key/custom auth headers: `X-Api-Key`, `X-Auth-Token`, `X-Client-Secret`.
- Các header chứa credential do đối tác tự định nghĩa.
- Query string nếu có thể chứa `token`, `code`, `signature` hoặc dữ liệu người dùng.

Đặt rule ở **mọi hop**: CDN/WAF, load balancer, ingress, reverse proxy, servlet container, APM agent và application. Che ở app không xóa bản ghi đã tạo ở proxy phía trước.

### 3.2. Tránh filter tự đọc request body để log

Một servlet filter nếu gọi `request.getInputStream()` để log SOAP XML có thể consume stream trước `MessageDispatcherServlet`. Wrapper có caching body có thể cho phép đọc lại nhưng sẽ buffer toàn payload và tăng heap; wrapper không tự động safe với MTOM/multipart hoặc payload lớn.

Nếu cần đo bytes, dùng transport/container metrics hoặc bounded counting stream không giữ nội dung. Nếu cần operation QName, lấy metadata ở một component được thiết kế trong Spring-WS pipeline, sau khi đã xác định trust/security order. Không log raw Body trong filter.

### 3.3. URL và query parameters

Access log thường ghi request target. Nếu WSDL URL hoặc SOAP endpoint nhận query parameter cho routing, đừng để secret/PII xuất hiện trong query string. Dùng path template thay raw path khi path segment có customer/order IDs nhạy cảm; log route name `/ws/orders/{orderId}` thay giá trị thực.

Không tự động ghi `Referer`, `Forwarded` hoặc `X-Forwarded-*` như dữ liệu đáng tin; có thể chứa URL nội bộ hoặc được caller giả mạo nếu proxy trust chưa cấu hình.

## 4. Che SOAP Envelope và WS-Security

### 4.1. Vì sao regex trên XML thường không an toàn?

~~~java
xml.replaceAll("<Password>.*?</Password>", "<Password>[REDACTED]</Password>");
~~~

Nó có thể bỏ sót prefix/namespace khác, attribute, whitespace, CDATA, nested elements, encoding khác, comments và XML entities. Regex đơn giản không xử lý namespace semantics đáng tin; payload attacker-controlled có thể làm logging/redaction code tốn CPU hoặc cắt sai vùng. Nếu chữ ký số áp dụng lên XML, sửa DOM/String để redact trước hoặc sau verify có thể làm signature verification sai và thay đổi evidence.

### 4.2. Xác định vùng nhạy cảm theo QName và vị trí

| Vị trí | Ví dụ | Quy tắc |
| --- | --- | --- |
| SOAP Header | Custom auth header, session key, customer identifiers | Allowlist header fields; drop credential-bearing nodes |
| WS-Security | `wsse:UsernameToken/wsse:Password` | Không serialize giá trị |
| BinarySecurityToken | X.509 certificate bytes | Không ghi token/certificate body; có thể ghi fingerprint đã duyệt |
| XML Signature | SignatureValue, KeyInfo, references | Không log toàn khối; chỉ security result + algorithm code được phép |
| XML Encryption | CipherValue, EncryptedKey | Không log ciphertext theo mặc định; metadata cũng cần phân loại |
| SOAP Body | PII, financial, business records | Không log body; field allowlist ở mapper nếu có need |
| Fault Detail | Internal IDs, SQL, validation values | Map thành error code an toàn |
| MTOM/SwA | Document, image, binary attachment | Không đọc/copy vào log |

QName gồm namespace URI + local name; đừng match prefix text như `wsse:` vì prefix có thể thay bằng alias. Dùng parser namespace-aware khi thực sự cần structural inspection, với parser hardening và giới hạn resource. Tuy nhiên, **đối với logging, tốt nhất không parse toàn Body để tìm thứ cần che**; chỉ tạo safe event metadata ở ranh giới có typed fields.

### 4.3. UsernameToken không được log dù là digest

`wsse:PasswordText` có thể chứa password hoặc password-equivalent; `wsse:PasswordDigest` chứa digest, nonce/timestamp phối hợp theo profile. Digest không phải plaintext nhưng vẫn là authentication material trong một số threat models và không cần thiết cho telemetry. Loại bỏ Password, Nonce và các token identifier nhạy cảm. Có thể log outcome đã chuẩn hóa như `wssec.validation=SUCCESS/FAILED`, mechanism `USERNAME_TOKEN` và failure category đã allowlist.

### 4.4. X.509: fingerprint khác certificate bytes

Không ghi toàn bộ `BinarySecurityToken`, PEM, DER, private key hoặc keystore. Nếu vận hành cần xác định certificate đối tác, có thể log fingerprint SHA-256/serial/issuer **sau khi certificate đã parse và được policy cho phép**, kèm partner ref đã đăng ký. Fingerprint vẫn là security metadata có thể liên kết đối tác; hạn chế quyền/retention. Không log `KeyInfo` hoặc certificate chain nguyên vẹn trong exception.

### 4.5. Signature/encryption không phải lý do để log raw XML

WS-Security signature giúp kiểm integrity/authentication của phần được ký, còn XML Encryption bảo vệ confidentiality trên wire. Khi diagnostics bật payload logging sau decrypt, plaintext có thể xuất hiện trong log và mất lớp bảo vệ ở storage. Khi log trước decrypt, ciphertext, token identifiers và metadata vẫn có thể nhạy cảm. **Không log toàn SOAP message ở cả hai phía**; log outcome/algorithm/reference count nếu được duyệt, không log SignatureValue/CipherValue hay plaintext.

### 4.6. Không thay đổi message chỉ để redaction log

Redaction chỉ dành cho bản sao telemetry, không chỉnh SOAP message thật trước khi endpoint xử lý hoặc trước khi WSS4J verify. Không mutate message tree để “làm sạch” rồi tiếp tục gửi; điều đó có thể phá chữ ký, canonicalization, audit evidence và contract semantics. Safe logging event nên được tạo **song song từ metadata đã chọn**, độc lập với message bytes.

## 5. Redaction strategy: redact, mask, truncate, tokenize

| Kỹ thuật | Hành vi | Ví dụ | Dùng khi |
| --- | --- | --- | --- |
| Redact/drop | Không ghi giá trị; thay marker | `[REDACTED]` | Token, password, private material |
| Mask | Giữ một phần để người có quyền nhận diện | `PAN ending 1234` | PII cần hỗ trợ có giới hạn |
| Truncate | Chỉ giữ phần đầu/đuôi hoặc giới hạn byte | 128 bytes đầu | Safe diagnostics sau allowlist; không áp mù cho secrets |
| Tokenize | Thay bằng token ngẫu nhiên có mapping ở vault | `cust_ref_8f...` | Correlation cần join mà không lộ identity |
| Pseudonymize/hash | Biến đổi ổn định/khó đảo theo thuật toán | HMAC của customer key | Thống kê, liên kết sự kiện có kiểm soát |
| Aggregate | Chỉ lưu số liệu nhóm | Count theo operation/result | Metrics và capacity planning |

### 5.1. Mask không phù hợp với bearer tokens

Đối với PAN hoặc số điện thoại, mask có thể giữ vài ký tự nếu chính sách cho phép. Đối với bearer token/password/API key, mask một phần vẫn có thể lộ token prefix/metadata, hỗ trợ khôi phục nếu entropy yếu, tạo giá trị gần giống token bị copy sang ticket/chat hoặc làm nhân viên nhầm bản log là credential có thể dùng lại.

Secret nên **drop hoàn toàn**, kể cả prefix/suffix, trừ fingerprint độc lập do security design phê duyệt.

### 5.2. Hash thường không đồng nghĩa ẩn danh

Hash email, phone hoặc ID với SHA-256 không salt có thể bị dò bằng dictionary vì không gian giá trị nhỏ. Nếu cần pseudonymous stable join, dùng HMAC với key riêng được quản lý trong KMS, scope/rotation rõ và chỉ log tag không thể dùng để authenticate. HMAC vẫn là pseudonymous personal data khi có thể liên kết/tái nhận diện thông qua key; không mặc định nó đã anonymous.

~~~java
byte[] digest = hmacSha256(
    telemetryKey,
    normalizedCustomerReference.getBytes(StandardCharsets.UTF_8));

String pseudonymousRef = HexFormat.of().formatHex(digest);
~~~

`hmacSha256` và `telemetryKey` là helper/key management giả định. Key phải nằm trong KMS/secret manager, không đặt trong source/log config; quyền truy cập tách khỏi người xem logs. Khi xoay key, quyết định có duy trì correlation cross-version hay tạo namespace/version riêng.

### 5.3. Truncate không thể bảo vệ secret

Không ghi “100 bytes đầu” của payload để debug nếu phần đầu thường là SOAP Header chứa token. Byte truncation không nhận biết XML element boundaries hoặc encoding, có thể cắt giữa UTF-8/XML token. Nếu có approved sample, dùng parser/typed mapper có allowlist rồi serialize một **diagnostic projection** giới hạn, không phải prefix bytes của request.

## 6. SOAP Fault, exception và error reporting

### 6.1. Public Fault khác internal diagnostic

Một lỗi nội bộ có thể chứa stack trace, SQL, filesystem path, keystore alias, partner endpoint, payload fragment hoặc cause chain. Không serialize nguyên exception vào SOAP Fault Detail hay response HTTP. Tạo fault contract ổn định gồm:

- Fault code/reason đã chuẩn hóa, không chứa internal class/message.
- Application error code và correlation ID do server kiểm soát.
- Detail tối thiểu mà client cần để sửa request hoặc quyết định retry.
- Không có token, password, PII không cần thiết, SQL, stack trace hoặc server path.

Ví dụ Fault Detail an toàn:

~~~xml
<ord:ServiceError xmlns:ord="urn:example:orders:fault:v1">
  <ord:code>ORDER_VALIDATION_FAILED</ord:code>
  <ord:correlationId>c-7f31a2</ord:correlationId>
</ord:ServiceError>
~~~

Correlation ID không phải authentication token; nó chỉ dùng tra cứu bản ghi vận hành có quyền. Client không được dùng correlation ID làm quyền truy cập ticket hoặc dữ liệu khác.

### 6.2. Phân loại lỗi ở server

| Lớp lỗi | Ví dụ internal | Client-facing result | Log phù hợp |
| --- | --- | --- | --- |
| Transport | TLS handshake, timeout, connection reset | HTTP/transport error, có thể không có SOAP Fault | Error category, peer alias đã allowlist, duration |
| SOAP parse | Malformed XML, unsupported encoding | Sender/Client Fault nếu stack tạo được response | Parser error category, line/column nếu an toàn |
| WS-Security | Invalid signature, untrusted cert, expired token | Security Fault/HTTP response theo stack | Validation outcome, mechanism, failure code |
| Contract validation | XSD missing element/type invalid | SOAP Client/Sender Fault | Schema version, QName, validation code |
| Authentication | Missing/invalid bearer | Thường HTTP 401 trước SOAP dispatcher | Auth mechanism + reason code; không log token |
| Authorization | Scope/tenant/resource denial | HTTP 403 hoặc SOAP Fault theo boundary | Policy code, operation, pseudonymous principal ref nếu duyệt |
| Business | Order state conflict | Typed SOAP Fault | Domain error code, correlation ID |
| Internal | DB unavailable, bug | Generic Receiver/Server Fault | Exception class + stack trace trong protected sink, đã scrub |

Không gom mọi lỗi thành một event SUCCESS/FAILED chung; nhưng cũng không để raw exception message thoát ra public logs. Phân loại vừa đủ để điều tra xu hướng, không tiết lộ secret.

### 6.3. Stack trace cũng có thể chứa secrets

Exception message có thể chèn raw XML, URL query, SQL bind value, header hoặc token. Stack trace itself thường là code location, nhưng cause/suppressed exceptions và message rất có thể chứa data. Không giả định `log.error("operation failed", ex)` an toàn nếu exception do parser/HTTP client/vendor tạo và nhúng response content.

Thiết kế error handler theo hai đường:

1. **Client response:** fault code/reason/detail đã allowlist và correlation ID.
2. **Internal diagnostic sink:** exception đã scrub hoặc exception metadata an toàn, chỉ nhóm được cấp quyền đọc.

Nếu không thể bảo đảm scrub exception object một cách đáng tin, chỉ log class/category, stack location và correlation ID; giữ raw exception trong secure debugger/session tạm thời theo quy trình incident, không đưa vào log tập trung.

### 6.4. Exception mapping không được làm mất nguyên nhân nhưng phải bảo vệ nội dung

Spring-WS có exception resolvers và `@SoapFault`/`SoapFaultMappingExceptionResolver` theo cấu hình. Hãy map application exceptions thành fault contract rõ. Với lỗi trước endpoint (TLS, Servlet authentication, parser hoặc WSS4J), business fault resolver có thể không được gọi; observability phải phân biệt HTTP failure với SOAP Fault. Không trả chi tiết WSS4J, cryptographic provider hoặc DB ra client.

## 7. Correlation ID, distributed tracing và baggage

### 7.1. Correlation ID không được caller tự do định nghĩa

Correlation ID giúp nối một SOAP request qua gateway, service, database và downstream. Có thể nhận external request ID nếu có trust rule, nhưng nên tạo internal trace/correlation ID riêng. Validate độ dài/charset, giới hạn giá trị, loại CR/LF và không cho caller dùng nó để chèn log lines.

Có thể duy trì cả hai:

| Identifier | Nguồn | Mục đích |
| --- | --- | --- |
| Internal trace ID | Tracing SDK/gateway | Distributed trace |
| Internal request ID | Application/edge | Tra log event trong một service |
| External partner reference | Partner, qua validation | Đối soát; coi là untrusted input |
| SOAP `wsa:MessageID` | SOAP caller | Protocol correlation; không phải identity |
| Business idempotency key | Client contract | Chống side effect trùng; tránh log raw nếu nhạy cảm |

Không nhầm correlation ID với `wsa:MessageID`, request ID nghiệp vụ hoặc credential. Mỗi giá trị có lifecycle, trust và retention khác nhau.

### 7.2. W3C Trace Context và HTTP propagation

HTTP services thường dùng `traceparent`/`tracestate` theo W3C Trace Context. Các giá trị này là metadata tracing, không phải secret, nhưng caller có thể gửi trace context giả để gây trace confusion, sampling manipulation hoặc log injection. Trust gateway policy, validate format, giới hạn kích thước và không sử dụng trace ID làm authorization.

Không chuyển `baggage` bất kỳ từ bên ngoài vào toàn bộ downstream calls nếu chưa lọc. Baggage có thể được propagate tới nhiều vendor/service, làm PII lan rộng hơn request ban đầu.

### 7.3. Baggage và span attributes phải allowlist

Nên ghi span attributes như:

- `rpc.system=soap`, service/operation QName đã allowlist.
- SOAP version, transport protocol và response status class.
- Payload size bucket thay payload bytes hoặc filename.
- Fault category, validation result và auth mechanism.
- Internal correlation ID, nếu đã được sinh/validate.

Không đưa vào span attributes hoặc baggage:

- Authorization header, JWT, cookies, UsernameToken, API keys.
- Name/email/phone, account number, customer ID thô hoặc SOAP Body fields.
- Raw URL query, request/response XML, SQL bind values.
- Certificate PEM/private key, signature/cipher values hoặc attachment name có PII.

Span events cũng là telemetry: không đính exception message nguyên trạng hoặc raw SOAP payload. Khi ghi exception, dùng exception type/category, stack trace đã scrub theo policy và không tạo event chứa nội dung nhạy cảm.

### 7.4. Sampling không phải kiểm soát bảo mật

Head-based hoặc tail-based sampling quyết định trace nào được giữ, không bảo đảm secret đã bị loại khỏi trace được chọn. Không coi 1% sampling nghĩa là 99% payload logs an toàn. Scrub/allowlist phải diễn ra **trước khi telemetry exporter gửi dữ liệu**, ở instrumentation point có thể kiểm soát.

## 8. Metrics labels và audit events

### 8.1. Metrics phải tránh high cardinality

Metrics nên tổng hợp theo route/operation, status class, fault category và payload size bucket. Đừng thêm mỗi customer ID/order ID/request ID vào label: cardinality tăng, query chậm và tạo kho định danh cá nhân dễ tìm kiếm.

| Tốt | Tránh |
| --- | --- |
| `soap_requests_total{operation='SubmitOrder', outcome='SUCCESS'}` | `soap_requests_total{customerId='...'}` |
| `soap_request_duration_seconds{operation='GetOrder'}` | `soap_request_duration_seconds{orderId='...'}` |
| `soap_faults_total{category='VALIDATION'}` | `soap_faults_total{faultDetail='...'}` |
| `soap_payload_bytes{size_bucket='1-10MiB'}` | Label có filename hoặc document ID |

Metric label phải có tập giá trị giới hạn và không chứa dữ liệu user-controlled tùy ý. Dù label là operation, nếu QName có dynamic path/tenant, normalize về route/operation template.

### 8.2. Audit event khác application debug log

Audit log ghi hành động có ý nghĩa bảo mật/nghiệp vụ: ai (principal đã xác minh), làm gì, trên resource nào, kết quả nào, khi nào và correlation nào. Audit cần integrity/access/retention riêng; không đơn giản bật DEBUG cho SOAP Body.

Ví dụ audit event an toàn:

~~~json
{
  "event": "order.cancel.denied",
  "principalRef": "prn_hmac_3c81",
  "operation": "CancelOrder",
  "resourceRef": "ord_ref_84a2",
  "policyCode": "TENANT_BOUNDARY",
  "correlationId": "c-7f31a2",
  "outcome": "DENIED"
}
~~~

`principalRef`/`resourceRef` là pseudonymous reference, chỉ ghi nếu được chính sách duyệt. Không ghi toàn bộ authorization claims/token hoặc object fields để “chứng minh” audit.

## 9. Retention, access control và lưu trữ telemetry

### 9.1. Log storage là một data store cần bảo vệ

Ngay cả khi application đã redact đúng, observability backend vẫn cần:

- TLS khi truyền và encryption at rest theo security baseline.
- RBAC theo vai trò: developer, operator, security responder, auditor.
- Tách tenant/project/index để partner không đọc log của nhau.
- Audit việc tìm kiếm, export, download và thay đổi retention.
- Retention tối thiểu đáp ứng mục đích vận hành/audit; tự động expire/delete.
- Hạn chế export ra laptop, email, chat, issue tracker hoặc vendor support portal.
- Backup/snapshot cũng phải áp dụng encryption, access và deletion policy tương đương.

Không dùng một index debug rộng cho tất cả đội ngũ chỉ vì tiện tìm kiếm. Audit/security events có thể cần quyền append-only/tamper-evident và retention khác application debug logs.

### 9.2. Retention cần theo data class và mục đích

| Loại telemetry | Nội dung | Nguyên tắc retention |
| --- | --- | --- |
| Metrics aggregate | Counts, latency histograms, size buckets | Có thể giữ dài hơn nếu không định danh cá nhân |
| Application logs | Operation, status, duration, correlation ID | Giới hạn theo thời gian troubleshooting và policy |
| Security/audit events | Auth outcome, policy decisions, admin actions | Theo audit/legal policy; access chặt, integrity cao |
| Sample diagnostics | Diagnostic projection đã allowlist | TTL ngắn, approve rõ, xóa tự động |
| Raw payload capture | Toàn SOAP/attachment | Tắt mặc định; nếu exception-approved thì isolated, encrypted, TTL rất ngắn |

Retention không nên kéo dài chỉ vì storage rẻ. Càng lâu, phạm vi ảnh hưởng của credential/PII bị ghi nhầm càng lớn.

### 9.3. Quy trình debug có kiểm soát

Khi không đủ thông tin để xử lý sự cố:

1. Bắt đầu bằng trace ID/correlation ID và event metadata đã scrub.
2. Thu thập SOAP fault code, operation QName, schema version, latency và auth mechanism.
3. Kiểm tra server-side validation/security category và downstream dependency status.
4. Nếu cần payload sample, tạo diagnostic projection chỉ chứa field được duyệt ở staging riêng.
5. Yêu cầu approval, giới hạn người truy cập, TTL, encryption và ghi audit access.
6. Xóa sample và bản export sau khi đóng incident; giữ lại kết luận không nhạy cảm.

Không yêu cầu đối tác gửi production bearer token, password, private key hoặc full SOAP payload qua email/chat để debug. Có thể yêu cầu họ gửi sanitized fixture, correlation ID, timestamp, partner reference và request shape không chứa dữ liệu thật.

## 10. Cấu hình và code để bảo vệ logs

### 10.1. Tắt raw header/body logging ở production

Logback/Log4j hoặc access log config cần được kiểm theo version và appender thực tế. Không bật logger category debug cho HTTP client, servlet container, SOAP message tracing hoặc WSS4J rồi mặc định output đã được redacted.

Với cấu hình proxy/container, chọn allowlist header fields và route template; không serialize toàn request headers/body. Với application, dùng logger riêng cho structured audit metadata. Không đặt token vào MDC.

### 10.2. MDC chỉ chứa identifier đã kiểm soát

Ví dụ với SLF4J MDC:

~~~java
import org.slf4j.MDC;

try (var ignored = MDC.putCloseable(
        "correlationId", correlationPolicy.validateOrCreate(inboundId))) {
    service.process(command);
}
~~~

`correlationPolicy.validateOrCreate` là helper ứng dụng giả định. MDC thường theo thread; trong async executor cần propagation/cleanup rõ. Không đặt `Authorization`, username/email, customerId thô hoặc SOAP Body fields vào MDC; giá trị có thể tự động được append vào mọi log event trong thread.

### 10.3. Redaction ở exporter là lớp bảo vệ phụ

Collector/exporter có thể scrub attributes trước khi gửi log/trace tới vendor; đây là defense-in-depth hữu ích nếu upstream instrumentation không thể đảm bảo. Nhưng dữ liệu có thể đã được ghi vào local file, buffer, queue hoặc collector trước filter. Vì vậy:

- Ngăn phát sinh sensitive field ở source trước.
- Lọc tại instrumentation/application boundary.
- Lọc bổ sung tại collector/exporter.
- Kiểm cả dead-letter queues, retry buffers, local files và crash dumps.

Không dựa duy nhất vào regex exporter để che SOAP XML; exporter thường không hiểu schema/QName và có thể cắt sai.

## 11. Kiểm thử redaction và ngăn rò rỉ

### 11.1. Seed canary values trong test

Đưa các giá trị giả dễ nhận biết vào request fixtures:

~~~text
Bearer token: TEST_BEARER_SECRET_9f8c
Password: TEST_PASSWORD_DO_NOT_LOG
API key: TEST_API_KEY_123456
Email: alice.private@example.test
Phone: +84-900-000-111
WSSE Password: TEST_WSSE_PASSWORD
Attachment marker: TEST_PRIVATE_DOCUMENT_CONTENT
~~~

Chạy request qua filter, SOAP message factory, interceptor, endpoint, exception handler và trace exporter test. Sau đó thu thập tất cả output sink và assert canary secrets/PII **không xuất hiện** ở logs, trace attributes/events, SOAP Fault, HTTP response hoặc metrics labels.

### 11.2. Test phải bao phủ nhiều biến thể XML

- Prefix namespace đổi từ `wsse` sang prefix khác nhưng cùng namespace URI.
- Element/attribute có whitespace, line breaks, nested nodes hoặc CDATA.
- HTTP Bearer và Cookie được cung cấp ở header thật.
- UsernameToken PasswordText/PasswordDigest, Nonce và Created.
- X.509 BinarySecurityToken và KeyInfo.
- SOAP Fault có internal exception cause.
- MTOM attachment có filename/content nhạy cảm.
- XML invalid/malformed, parser exception chứa input excerpt.
- Request lớn hoặc nested sâu để redaction không tạo DoS.

Không chỉ test helper regex; test toàn pipeline bằng logging configuration và exporter tương tự production.

### 11.3. Test với JUnit và Logback ListAppender

Ví dụ đơn giản kiểm một event được tạo qua logger allowlist:

~~~java
@Test
void auditEventDoesNotContainCredentialOrPersonalData() {
    String token = "TEST_BEARER_SECRET_9f8c";
    String email = "alice.private@example.test";

    auditLogger.completed(
        "SubmitOrder",
        "c-test-001",
        "partner-17",
        200,
        84,
        1024,
        "SUCCESS");

    String renderedLogs = listAppender.list.toString();
    assertFalse(renderedLogs.contains(token));
    assertFalse(renderedLogs.contains(email));
    assertTrue(renderedLogs.contains("SubmitOrder"));
}
~~~

Đây là skeleton; `listAppender` phải gắn vào logger/appender trong test và event phải đi qua đúng encoder/layout production. Test minh họa allowlist metadata; thêm test toàn pipeline dùng raw SOAP fixture có các canary values, sau đó kiểm mọi sink. Không chỉ assert một appender nếu app còn gửi telemetry tới console, file, OTLP hoặc queue.

### 11.4. Negative tests và fail-safe behavior

- Nếu redaction component lỗi, **không fallback sang log raw request**.
- Nếu QName/field không nhận diện, drop entire payload section khỏi telemetry.
- Nếu correlation ID sai format, tạo ID nội bộ mới; không log input thô.
- Nếu exception message chứa canary, không append nguyên exception vào public log.
- Nếu diagnostic projection vượt size limit, truncate theo field đã allowlist hoặc drop sample; không cắt raw bytes.
- Kiểm cấu hình production không bật payload trace/debug ngoài approval window.

## 12. Incident response khi phát hiện secret/PII đã bị log

Phát hiện credential trong log là một security incident, không chỉ là việc chỉnh format logger. Xử lý theo thứ tự:

1. **Containment:** khóa truy cập index/file/trace liên quan, dừng payload logging hoặc exporter bị lỗi, ngăn tiếp tục ingest.
2. **Classification:** xác định loại dữ liệu, thời gian xuất hiện, hệ thống/region/backup/queue đã nhận và phạm vi người có quyền đọc.
3. **Credential response:** revoke access/refresh token, rotate API key/password/client secret/cert hoặc key phù hợp; đánh giá sessions và downstream credentials.
4. **Data handling:** xóa/expire bản ghi và bản sao theo incident/legal process; nếu immutable backup không thể xóa ngay, hạn chế restore/access và ghi rõ expiry.
5. **Investigation:** dùng access audit để xác định ai đã xem/export; không copy secret sang ticket mới khi điều tra.
6. **Prevention:** sửa source logger, proxy/APM config, exporter filters và bổ sung canary tests cho regression.
7. **Communication:** thông báo security/privacy owner, data owner và partner theo quy trình tổ chức; giữ timeline và quyết định xử lý.

Không chỉ xóa dòng log trên dashboard rồi coi incident kết thúc. Cần xem index replicas, object storage, snapshots, collector buffers, SIEM exports, alert payloads và support bundles.

### 12.1. Khi nào phải rotate credential?

Nếu access token/password/API key/private key hoặc password-equivalent đã lộ ở nơi không được phép, đánh giá như credential compromise. Rotate/revoke theo loại credential và khả năng sử dụng lại. Với certificate, xem private key có lộ hay chỉ public certificate; public certificate/fingerprint thường không tương đương private key compromise, nhưng vẫn cần kiểm tra policy.

Đối với PII/business confidential, containment và deletion/access review vẫn cần thiết dù không có credential để revoke.

## 13. Checklist production

### Logging

- Có allowlist event fields cho từng SOAP operation?
- Raw SOAP Envelope/Body/attachments bị tắt trong production logging mặc định?
- HTTP Authorization/Cookie/API keys và query secrets đã bị loại ở proxy, container và app?
- Exception messages/cause chains được scrub hoặc chỉ log category/class/location?
- Redaction failure fail closed?

### WS-Security và SOAP

- UsernameToken PasswordText/PasswordDigest, Nonce, BinarySecurityToken, KeyInfo và Signature/Cipher values không bị serialize vào logs?
- Private keys, keystore passwords, HSM PINs và decrypted session keys không vào logs/config dump?
- Redaction không mutate SOAP message thật hoặc phá signature verification?
- SOAP Fault chỉ chứa contract error code/reason/detail an toàn?
- MTOM/SwA attachment content và filenames được bảo vệ?

### Tracing và metrics

- Trace attributes/baggage dùng allowlist và không chứa token/PII?
- Trace context bên ngoài được validate; không dùng trace ID để authorize?
- Metric labels không có customer/order/request IDs hoặc arbitrary XML values?
- Audit events có integrity, access và retention riêng?

### Storage và vận hành

- Log/trace storage có TLS, encryption at rest, RBAC và access audit?
- Retention ngắn nhất phù hợp mục đích; backup/export cũng được kiểm soát?
- Có quy trình debug production bằng correlation ID và sanitized fixture?
- Canary tests chạy qua toàn pipeline và mọi sink?
- Có runbook revoke/rotate credentials và xử lý bản sao telemetry?

## 14. Bài tập tự kiểm tra

**Bài 1.** Một SOAP request mang HTTP Bearer token và PII trong Body. Vì sao che ở `@Endpoint` chưa đủ nếu reverse proxy đã log toàn headers?

**Bài 2.** Vì sao allowlist log fields an toàn hơn ghi toàn XML rồi dùng regex blacklist?

**Bài 3.** WS-Security `PasswordDigest` không chứa raw password. Vì sao vẫn nên redact cả digest, Nonce và Created?

**Bài 4.** Một XML Signature hợp lệ. Có thể sửa DOM để xóa PII rồi tiếp tục xử lý message đó không? Vì sao?

**Bài 5.** Phân biệt redact, mask, truncate, tokenize và pseudonymize. Cách nào phù hợp access token còn hạn?

**Bài 6.** Vì sao SHA-256 không salt của email/phone chưa đủ để ẩn danh? Khi cần join pseudonymous events thì HMAC giúp gì và còn rủi ro gì?

**Bài 7.** Vì sao raw exception message từ WSS4J/HTTP client có thể làm lộ dữ liệu dù application không log SOAP Body?

**Bài 8.** Tracing baggage chứa customer email được propagate sang ba downstream services. Hãy nêu cách containment và prevention.

**Bài 9.** Một metric có label `orderId`. Những rủi ro về cardinality và privacy là gì? Hãy đề xuất label thay thế.

**Bài 10.** Client gửi correlation ID chứa CR/LF và nội dung giả dạng log entry. Cần kiểm tra/chuẩn hóa thế nào?

**Bài 11.** Khi nào có thể log certificate fingerprint? Những certificate fields/private material nào không được log?

**Bài 12.** Production log đã chứa refresh token. Nêu các bước containment, revoke/rotate, access audit và xử lý replicas/backups.

**Bài 13.** Viết test canary để chứng minh token/PII không xuất hiện trong logs, trace spans, SOAP Fault và metrics.

**Bài 14.** Một redaction library lỗi giữa request. Hệ thống nên fallback bằng cách nào để vừa debug được vừa không phát raw payload?

**Bài 15.** Thiết kế quy trình support một partner bị `InvalidSecurity` mà không yêu cầu họ gửi private key, password hoặc full production SOAP Envelope.

### Gợi ý trả lời cốt lõi

- **1–2:** Redaction phải áp dụng ở mọi hop; allowlist giảm số field được phép phát ra.
- **3–4:** Digest/nonce có thể là authentication material; sửa XML thật có thể làm sai chữ ký/canonicalization.
- **5–6:** Drop secret hoàn toàn; HMAC hỗ trợ pseudonymous join nhưng vẫn là dữ liệu có thể liên kết.
- **7–8:** Exception/baggage là telemetry sinks; scrub tại nguồn và giới hạn propagation.
- **9–10:** Dùng operation/status bucket; validate length/charset và loại CR/LF cho external IDs.
- **11–12:** Fingerprint public cert có thể được duyệt; credential/private key leak cần containment và rotation; xóa cả bản sao.
- **13–15:** Test toàn pipeline và mọi sink; fail closed; debug bằng correlation ID, failure category, timestamp và sanitized fixture.

## Tài liệu tham khảo

- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — dữ liệu không nên log, sanitization, access và retention.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html) — lưu trữ, rotation và quản lý secrets.
- [OWASP Logging Vocabulary Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Vocabulary_Cheat_Sheet.html) — phân loại sự kiện và dữ liệu logging.
- [OWASP API Security Top 10](https://owasp.org/API-Security/) — rủi ro dữ liệu/API và authorization.
- [W3C Trace Context](https://www.w3.org/TR/trace-context/) — `traceparent`, `tracestate` và propagation.
- [W3C Baggage](https://www.w3.org/TR/baggage/) — propagation baggage và giới hạn metadata tracing.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/) — trace context, baggage và propagation boundaries.
- [OpenTelemetry — Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/) — span attributes/events và conventions.
- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/) — SOAP message processing, interceptors, faults và WS-Security.
- [Spring Security Reference](https://docs.spring.io/spring-security/reference/) — HTTP authentication, security filters và error handling.
- [OASIS WS-Security UsernameToken Profile 1.1.1](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-UsernameTokenProfile-v1.1.1-os.html) — UsernameToken và password digest semantics.

**Ghi nhớ:** log, trace, metric, fault và support bundle đều là nơi lưu dữ liệu. Hãy **không ghi secret**, dùng allowlist cho metadata, pseudonymize PII khi cần join, không sửa SOAP message thật để redact, lọc baggage/labels, kiểm soát retention/access và chạy canary tests trên mọi sink. Khi phát hiện secret đã bị log, xử lý như incident: containment, revoke/rotate, access audit và xử lý cả replicas/backups.
