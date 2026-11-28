# Phân biệt ghi payload với ghi toàn bộ SOAP envelope

Khi vận hành hệ thống SOAP, log XML giúp điều tra lỗi tích hợp: request có đúng QName không, endpoint nhận Header nào, client gửi action gì, server trả SOAP Fault nào và hai hệ thống có cùng hiểu contract không. Tuy nhiên, log càng nhiều XML thì nguy cơ lộ dữ liệu cá nhân, thông tin nghiệp vụ, token xác thực và dữ liệu mật càng lớn.

Trong Spring Web Services (Spring-WS), cần phân biệt hai phạm vi:

- **Payload logging** ghi nội dung nghiệp vụ trong SOAP Body, thường là XML request/response của operation.
- **Full SOAP Envelope logging** ghi cả Envelope gồm Header và Body. Tùy cơ chế capture, logger còn có thể ghi transport metadata hoặc MIME attachments bên ngoài XML Envelope.

Payload phù hợp để kiểm cấu trúc nghiệp vụ; Envelope hữu ích khi điều tra SOAP Header, WS-Addressing, WS-Security và interoperability. Không nên bật toàn bộ Envelope trong production chỉ vì nó chứa nhiều thông tin hơn.

Bài thuộc chương **Quan sát và chẩn đoán** của module **SPRING_WEB_SERVICES**. Mục tiêu là chọn đúng lớp dữ liệu cần ghi, che dữ liệu nhạy cảm trước khi ghi, liên kết log với trace/request ID và kiểm soát sampling, quyền truy cập, retention cùng tác động hiệu năng.

> **Nguyên tắc:** ưu tiên metadata và correlation trước; chỉ ghi XML khi có nhu cầu chẩn đoán cụ thể, đã phân loại dữ liệu và có redaction. Log không được trở thành một đường xuất dữ liệu SOAP thứ hai.

## 1. SOAP message gồm những phần nào?

SOAP message có Envelope, gồm Header tùy chọn và Body bắt buộc. SOAP Fault cũng nằm trong Body. Message có thể kèm MIME attachments theo SwA/MTOM; attachment không phải element XML trong Envelope.

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <soap:Header>
    <wsa:Action>https://example.test/orders/GetOrder</wsa:Action>
    <wsa:MessageID>urn:uuid:...</wsa:MessageID>
    <!-- WS-Security header may be present -->
  </soap:Header>
  <soap:Body>
    <ord:GetOrderRequest xmlns:ord="https://example.test/orders/v1">
      <ord:orderId>42</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
```

| Lớp | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Transport metadata | HTTP method, path, status, Content-Type | Vận chuyển |
| SOAP Envelope | Namespace, Header, Body | Cấu trúc SOAP |
| SOAP Header | Action, MessageID, security token | Routing, addressing, security |
| SOAP Body | Request/response/Fault payload | Nội dung operation |
| MIME attachments | File, binary, MTOM parts | Dữ liệu ngoài XML Envelope |
| Runtime context | Trace ID, duration, retry count | Vận hành/quan sát |

Logging toàn Envelope không tự động có nghĩa đã ghi MIME attachments. Điều đó tùy message factory, transport và logger. Ngược lại, HTTP wire dump có thể chứa MIME boundary, attachment headers hoặc dữ liệu nhị phân.

## 2. Payload logging là gì?

Payload là XML nằm trong SOAP Body. Ví dụ:

```xml
<ord:GetOrderRequest xmlns:ord="https://example.test/orders/v1">
  <ord:orderId>42</ord:orderId>
</ord:GetOrderRequest>
```

Payload logging giúp kiểm QName/namespace, element/attribute, field bắt buộc, JAXB marshal/unmarshal, response mapping và lỗi business validation. Nó thường không cho thấy SOAP Header, WS-Addressing Action/To/MessageID, WS-Security token/signature, HTTP SOAPAction/Content-Type/Authorization hay TLS/connection timing.

Payload có thể chứa tên, địa chỉ, account number, payment reference, tài liệu hoặc free-text. "Chỉ ghi Body" không đồng nghĩa "an toàn để ghi".

## 3. Full SOAP Envelope logging là gì?

Full Envelope logging ghi SOAP Envelope gồm Header và Body:

```xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <soap:Header>
    <wsa:Action>https://example.test/orders/GetOrder</wsa:Action>
    <wsa:MessageID>urn:uuid:masked-message-id</wsa:MessageID>
  </soap:Header>
  <soap:Body>
    <ord:GetOrderRequest xmlns:ord="https://example.test/orders/v1">
      <ord:orderId>42</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
```

Envelope logging hữu ích khi điều tra routing theo SOAPAction/WS-Addressing, lỗi security interceptor, custom Header, mustUnderstand/role, SOAP version mismatch và Fault detail. Header có thể chứa UsernameToken, BinarySecurityToken, nonce, certificate metadata, signatures, timestamp và tenant identity. Vì vậy Envelope logging cần redaction theo cấu trúc XML và kiểm soát chặt hơn.

## 4. So sánh payload và Envelope logging

| Tiêu chí | Payload-only | Full Envelope |
| --- | --- | --- |
| SOAP Body | Có | Có |
| SOAP Header | Không | Có |
| WS-Addressing | Không, trừ capture riêng | Có nếu nằm trong Envelope |
| WS-Security header | Không | Có thể có; phải mask |
| HTTP headers | Không tự có | Không tự có |
| MIME attachments | Không tự có | Không tự có nếu logger chỉ serialize Envelope |
| Serialization cost | Thường thấp hơn | Thường cao hơn |
| Risk lộ secret | Có | Cao hơn do Header |
| Dùng để | Debug payload/schema | Điều tra header/protocol/security |

Đặt tên field rõ như **soap.payload.redacted**, **soap.envelope.redacted** hoặc **soap.header.metadata**. Không gọi log chỉ ghi Body là "full SOAP request".

## 5. Metadata-first: ghi thông tin cần trước XML

Nhiều lỗi production được khoanh vùng mà không cần lưu payload.

| Field | Ví dụ | Mục đích |
| --- | --- | --- |
| timestamp | UTC | Sắp xếp sự kiện |
| service/operation | orders/GetOrder | Xác định operation |
| direction | inbound/outbound | Hướng message |
| destination group | partner-orders | Đích logic |
| SOAP version | 1.1/1.2 | Chẩn đoán binding |
| HTTP status | 200/500/401/415 | Transport result |
| Content-Type | text/xml | Media type |
| action | URI đã chuẩn hóa | Định tuyến |
| correlation ID | Opaque ID | Ghép request/response |
| trace/span ID | Trace context | Distributed tracing |
| duration | Milliseconds | Latency |
| outcome | success/fault/timeout | Phân loại |
| fault code | Sender/Receiver | Chẩn đoán Fault |
| contract version | orders-v2 | Đối chiếu schema |
| retry attempt | 1/2/3 | Điều tra retry |

Không cần log Body để ghi các thông tin này. Metadata cũng cần giới hạn cardinality; không đưa customer ID hoặc raw URL có tenant parameter vào metric labels.

## 6. Chọn cơ chế logging trong Spring-WS

Spring-WS có logging/tracing ở các lớp khác nhau; cấu hình cụ thể phụ thuộc version và transport:

1. **Message/transport tracing:** logger framework có thể ghi message trace theo category và log level. Xác minh logger của version đang dùng ghi request, response hay cả hai.
2. **EndpointInterceptor:** ghi metadata trước/sau xử lý endpoint.
3. **ClientInterceptor:** ghi metadata outbound/inbound quanh WebServiceTemplate.
4. **HTTP client instrumentation:** ghi HTTP status, allowlisted headers, duration và connection metrics.
5. **Custom message logging layer:** khi cần redaction XML-aware, size limit hoặc policy riêng.

Không mặc định bật DEBUG ở package rộng là chỉ ghi payload. Có logger có thể ghi Envelope/message bytes. Thử bằng token giả trong môi trường test, kiểm output thực rồi mới dùng dữ liệu thật.

## 7. Metadata logging bằng EndpointInterceptor

Một EndpointInterceptor phía server có thể ghi metadata ở lifecycle callbacks. API đọc payload/header thay đổi theo Spring-WS version; tránh serialize toàn message chỉ để lấy operation name.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ws.context.MessageContext;
import org.springframework.ws.server.EndpointInterceptor;

public class SoapMetadataInterceptor implements EndpointInterceptor {
    private static final Logger log =
            LoggerFactory.getLogger(SoapMetadataInterceptor.class);

    @Override
    public boolean handleRequest(MessageContext messageContext, Object endpoint) {
        log.info("soap.inbound stage=request");
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext, Object endpoint) {
        log.info("soap.inbound stage=response");
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext, Object endpoint) {
        log.warn("soap.inbound stage=fault");
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext messageContext, Object endpoint, Exception ex) {
        if (ex != null) {
            log.warn("soap.inbound result=exception type={}",
                    ex.getClass().getSimpleName());
        }
    }
}
```

Đây là skeleton minh họa; imports/callback signatures phải khớp Spring-WS API của project. Bản production bổ sung correlation ID, operation và elapsed time từ context đã xác minh. Không ghi toàn bộ MessageContext hoặc exception message nếu chúng chứa payload/credentials.

## 8. Metadata logging ở client với ClientInterceptor

ClientInterceptor có lifecycle gửi request và nhận response/Fault. Có thể dùng để liên kết outbound call với correlation ID.

```java
public class SoapClientMetadataInterceptor implements ClientInterceptor {
    @Override
    public boolean handleRequest(MessageContext messageContext) {
        // Log operation/correlation metadata only.
        return true;
    }

    @Override
    public boolean handleResponse(MessageContext messageContext) {
        // Log response outcome and duration.
        return true;
    }

    @Override
    public boolean handleFault(MessageContext messageContext) {
        // Log fault category after redaction.
        return true;
    }

    @Override
    public void afterCompletion(MessageContext messageContext, Exception ex) {
        // Finish client span; do not serialize raw message here.
    }
}
```

Đây là pseudocode; xác minh interface signatures theo Spring-WS version. Client interceptor không nhất thiết nhìn được HTTP headers/TLS timing; các phần đó thuộc sender/HTTP client instrumentation.

## 9. Envelope logging cần cơ chế riêng

Khi cần Header và Body, dùng message tracer/logger đã xác nhận ghi Envelope hoặc custom capture. Trước khi bật, trả lời:
- Capture trước hay sau WS-Security processing?
- Signature/encryption đã áp dụng chưa?
- Header nào chứa token/PII?
- Có capture outbound plaintext trước encryption?
- Có capture decrypted inbound content?
- Fault detail có stack trace/internal data?
- Attachment có vào log stream?
- XML bị truncate giữa document?

Vị trí capture ảnh hưởng nội dung. Logger trước security interceptor có thể thấy encrypted XML; logger sau decryption có thể thấy plaintext. Cả hai đều cần threat analysis.

## 10. WS-Security: trường không được ghi nguyên trạng

WS-Security Header có thể chứa UsernameToken/password digest, Nonce/Created, BinarySecurityToken, SecurityTokenReference, KeyIdentifier, SignatureValue, DigestValue, EncryptedKey, EncryptedData và timestamp.

Không ghi password, token, signature material hoặc private key. Public certificate không phải private key nhưng subject/issuer/serial có thể định danh; nếu cần, chỉ ghi fingerprint/identifier được policy duyệt.

Nếu XML Signature được kiểm tra, masking trực tiếp message sẽ làm chữ ký mất hiệu lực. **Redact bản sao dành cho log**, không sửa message đang xử lý. Giữ original trong request processing path và không mutate trước endpoint/security processing.

## 11. Redaction dựa trên cấu trúc XML

Regex trên toàn XML có thể match sai namespace/prefix, xóa nhầm element cùng local name, bỏ sót CDATA/attribute/nested token hoặc làm XML malformed.

Quy trình redaction:
1. Parse một copy XML bằng parser hardening.
2. Chọn node theo namespace URI + local name hoặc XPath namespace-aware.
3. Thay text/attribute bằng marker [REDACTED].
4. Dùng allowlist field được giữ và denylist bổ sung.
5. Giới hạn depth, size và thời gian xử lý.
6. Serialize bản copy đã mask.
7. Nếu redaction lỗi, bỏ payload và ghi metadata redaction_failed=true.
8. Không fallback sang raw XML.

Ví dụ:

```xml
<!-- Before -->
<sec:UsernameToken xmlns:sec="urn:example:security">
  <sec:Username>partner-user</sec:Username>
  <sec:Password>very-secret</sec:Password>
</sec:UsernameToken>

<!-- Redacted log copy -->
<sec:UsernameToken xmlns:sec="urn:example:security">
  <sec:Username>[REDACTED]</sec:Username>
  <sec:Password>[REDACTED]</sec:Password>
</sec:UsernameToken>
```

Áp dụng policy cho Body, Header, Fault detail, attributes, attachment metadata và custom fields đã phân loại.

## 12. PII và dữ liệu nghiệp vụ trong Body

SOAP Body có thể chứa tên, địa chỉ, email, số điện thoại, customer/account/order IDs, giá, payment references, hợp đồng, tài liệu, business notes hoặc dữ liệu thuộc nhóm hạn chế.

Phân loại field ở contract/domain layer. Nếu cần debug cấu trúc, log tên field, kiểu dữ liệu, độ dài hoặc hash phù hợp thay vì giá trị. Hash identifier vẫn có thể liên kết lại cùng chủ thể; không tự động biến dữ liệu thành anonymous. Nếu cần pseudonymization, dùng secret/salt và policy phù hợp.

## 13. Allowlist và denylist

| Cách | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Allowlist field được ghi | Schema thêm field mặc định không lộ | Có thể thiếu dữ liệu debug |
| Denylist field cần che | Dễ bắt đầu | Schema mới có thể thêm secret chưa liệt kê |

Khuyến nghị allowlist cho production payload capture; denylist là defense-in-depth. Với Header/security, mặc định không ghi token/certificate content. Với Body, chỉ giữ field không nhạy cảm đã được owner duyệt.

Mỗi contract version mới cần review redaction policy. Free-text fields như comment/description/notes thường chứa dữ liệu không dự đoán được.

## 14. Sampling, size limit và retention

Không phải mọi request cần log XML:
- Chỉ capture trong profile/test hoặc diagnostic flag có thời hạn.
- Sampling thấp cho success path; tăng có kiểm soát trong incident.
- Error-based sampling vẫn phải redaction vì Fault có thể chứa dữ liệu nhạy cảm.
- Giới hạn bytes cho payload/Envelope.
- Truncate an toàn sau redaction và đánh dấu truncated=true.
- Không ghi binary attachments vào application log.
- Retention ngắn, quyền truy cập tối thiểu.
- Có quy trình xóa/hold và audit access.

Cắt XML bằng substring có thể tạo fragment malformed. Nếu cần XML hợp lệ, cắt theo node hoặc chỉ ghi metadata kích thước/element hiện diện. Không truncate trước redaction rồi giả định phần bỏ đi không chứa secret.

## 15. Tách audit log khỏi diagnostic log

Không dùng raw SOAP Envelope làm audit record.

| Loại log | Nội dung | Yêu cầu |
| --- | --- | --- |
| Audit | Actor, action, resource, outcome, timestamp | Integrity/access/retention |
| Diagnostic | Operation, duration, status, trace/correlation | Searchability, bounded cardinality |
| Payload sample | XML đã redaction | Sampling, size limit, short retention |
| Security event | Auth/signature/trust result | Không secret, audit access |
| Transport metric | Latency, pool/status/timeout | Không payload |

Audit cần event schema ổn định. Nếu cần payload evidence, dùng evidence store riêng có encryption/access/audit controls; không đẩy vào application log.

## 16. Correlation ID và trace context

Khi client gửi SOAP request, tạo hoặc propagate correlation ID theo policy. Có thể dùng HTTP trace headers, WS-Addressing MessageID hoặc custom SOAP Header; ba giá trị này không nhất thiết cùng ID.

Log có thể liên kết inbound HTTP request ID, MessageID/RelatesTo, outbound partner call ID, W3C trace/span context, retry attempt và contract version.

Không tin mù correlation ID từ external caller; validate length/format, sanitize và giữ internal trace ID riêng. Không dùng external ID làm log format string.

## 17. Logging failure không được phá SOAP processing

Diagnostic logger/parser/redactor lỗi thường không nên làm business request fail; nhưng tuyệt đối không fallback ghi raw sensitive XML.

- Redaction exception: bỏ payload, ghi metadata + redaction_failed.
- Logging queue đầy: drop/sample có metric, không block vô hạn.
- Log backend down: không giữ SOAP thread quá lâu.
- Bounded buffer và async appender có backpressure policy.
- Security audit event có thể cần durable path riêng; không dùng drop policy của debug log.
- Tránh recursive logging khi appender lỗi.

Kiểm logger không làm mất response hoặc che exception gốc. Logging error không được thay business error.

## 18. Cấu hình theo môi trường

| Môi trường | Payload logging | Envelope logging |
| --- | --- | --- |
| Local development | Có thể bật với synthetic data | Có thể bật để học protocol |
| CI/integration | Capture giới hạn, dữ liệu giả | Bật để kiểm Header/version khi cần |
| Staging | Mặc định tắt hoặc redacted/sampled | Diagnostic window có kiểm soát |
| Production | Metadata-first, XML opt-in | Tắt mặc định; incident-only |

Không đặt DEBUG toàn package production thường trực. Diagnostic window phải có scope partner/operation/trace, expiry, sampling, redaction, access control, byte limit và bước tắt/xác nhận sau incident.

## 19. Ví dụ log event có cấu trúc

Thay vì raw Envelope, ghi metadata:

```json
{
  "event": "soap.client.exchange",
  "service": "orders",
  "operation": "GetOrder",
  "direction": "outbound",
  "soapVersion": "1.2",
  "contentType": "application/soap+xml",
  "action": "https://example.test/orders/GetOrder",
  "correlationId": "7bb4...masked",
  "traceId": "0af7...masked",
  "contractVersion": "orders-v2",
  "durationMs": 184,
  "httpStatus": 200,
  "outcome": "success",
  "payloadCaptured": false
}
```

Đây là schema minh họa. Normalize action/URI, tránh query string có secret; không đưa correlation/customer IDs vào metric labels có cardinality cao.

Nếu capture payload, ghi metadata capture riêng:

```json
{
  "event": "soap.message.capture",
  "scope": "payload",
  "redacted": true,
  "truncated": false,
  "bytes": 836,
  "redactionPolicyVersion": "orders-log-policy-v3",
  "captureReason": "incident-sample"
}
```

Raw XML không nên nằm trong event metadata mặc định.

## 20. Kiểm tra logger và redaction

Dùng canary value như SECRET_CANARY_123 rồi xác nhận canary không xuất hiện trong output log. Kiểm Body, Header token/password, attributes, Fault detail, prefix alternate, CDATA, attachment metadata, exception message và HTTP headers.

Không chỉ test redactor helper; test quanh interceptor/logger để chắc chắn logger khác không ghi raw message.

## 21. Ma trận 40 ca kiểm thử payload và Envelope logging

| Mã | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| O01 | Payload logging bật | Chỉ Body theo scope |
| O02 | Envelope logging bật | Header và Body được capture |
| O03 | Metadata-only mode | Không XML content |
| O04 | WS-Addressing Action trong Envelope | Header metadata đúng |
| O05 | Payload-only mode | Không lộ SOAP Header |
| O06 | UsernameToken trong Header | Username/password bị mask hoặc bỏ |
| O07 | BinarySecurityToken | Không log raw token/certificate |
| O08 | SignatureValue/DigestValue | Không log cryptographic material |
| O09 | Custom Header có PII | Redaction áp dụng |
| O10 | Body có customer name/email | Sensitive field được mask |
| O11 | Account/payment reference | Field theo policy được mask |
| O12 | Free-text notes có canary | Canary không xuất hiện |
| O13 | XML attribute nhạy cảm | Attribute được redacted |
| O14 | Namespace prefix đổi | Redaction vẫn hoạt động |
| O15 | Namespace khác, local name trùng | Không mask nhầm namespace |
| O16 | Nested secret element | Deep redaction đúng |
| O17 | CDATA chứa secret | Secret không lọt log |
| O18 | Fault detail có PII/stack | Detail được sanitize |
| O19 | MIME attachment | Không dump binary |
| O20 | Attachment filename nhạy cảm | Metadata được mask |
| O21 | XML vượt size limit | Truncate/drop theo policy |
| O22 | Truncation giữa element | Không xuất fragment nguy hiểm |
| O23 | Redactor ném exception | Không fallback raw XML |
| O24 | XML malformed | Metadata/error category an toàn |
| O25 | Logging backend unavailable | SOAP flow không block vô hạn |
| O26 | Async queue đầy | Drop/sample + metric |
| O27 | DEBUG ngoài dự kiến | Config test phát hiện |
| O28 | Production profile | Envelope capture tắt mặc định |
| O29 | Diagnostic flag hết hạn | Capture tự dừng |
| O30 | Success sampling | Rate trong limit |
| O31 | Error sampling | Fault payload vẫn redacted |
| O32 | External correlation ID | Length/format sanitize |
| O33 | Trace ID và WS-A MessageID | Liên kết đúng, giữ nghĩa riêng |
| O34 | HTTP Authorization | Không log credential |
| O35 | Content-Type/action metadata | Chỉ allowlisted metadata |
| O36 | Concurrent SOAP calls | Không trộn payload |
| O37 | Logging tăng latency | Overhead đo/giới hạn |
| O38 | Audit event | Không dùng raw Envelope |
| O39 | Retention expiry | Data hết hạn được xóa |
| O40 | Access audit | Truy cập diagnostic payload được ghi |

## 22. Chẩn đoán log thiếu thông tin hoặc lộ dữ liệu

| Triệu chứng | Nguyên nhân có thể | Điều tra |
| --- | --- | --- |
| Có Body nhưng thiếu Action | Payload-only logger | Thêm metadata/header capture giới hạn |
| Envelope không thấy HTTP SOAPAction | Logger ở message layer | Thêm transport instrumentation |
| Không thấy attachment | Logger chỉ serialize Envelope | Kiểm MIME capture |
| Token xuất hiện trong log | Redaction thiếu security nodes | Tắt capture, xử lý credential incident, sửa policy |
| Prefix khác làm mask thất bại | Regex/string matching | Namespace-aware parser |
| XML log malformed | Mutate message gốc/serialize lỗi | Redact bản sao |
| Payload log gây timeout | Synchronous IO/serialization | Async bounded logger, size limit |
| SOAP call fail khi backend down | Logging exception propagate | Isolate diagnostic path |
| Không correlate request/response | ID không propagate | Trace/MessageID/client interceptor |
| Production bật DEBUG dài hạn | Thiếu expiry guardrail | Diagnostic flag TTL |
| Metric cardinality tăng | ID/URL đưa vào tags | Normalize/aggregate |
| Audit thiếu evidence | Dùng diagnostic log thay audit | Event audit riêng |

Quy trình điều tra:
1. Xác định logger capture transport, Envelope, Header hay Body.
2. Ghi operation/version, chưa dump raw XML ngay.
3. Kiểm WS-Addressing và correlation metadata.
4. Capture synthetic fixture qua đúng logger.
5. Kiểm redaction bằng canary values.
6. Kiểm backend/queue/latency và sampling.
7. Xác định attachment capture layer.
8. Tắt hoặc giới hạn capture nếu phát hiện secret.
9. Sửa policy và thêm regression tests.
10. Kiểm retention/access audit sau incident.

## 23. Bài tập: điều tra lỗi action nhưng không lộ WS-Security token

**Bối cảnh:** partner báo GetOrder không được route. Payload-only log cho thấy Body đúng QName nhưng thiếu Action. Team bật full Envelope DEBUG production và phát hiện log chứa UsernameToken cùng BinarySecurityToken.

**Yêu cầu:** đề xuất phương án quan sát để điều tra mà không tiếp tục lưu secret.

**Hướng giải quyết:**
1. Tắt full Envelope capture không kiểm soát và xác minh logger không ghi security Header raw.
2. Giữ metadata event cho operation, SOAP version, Content-Type, HTTP SOAPAction, WS-Addressing Action, destination, status và correlation ID.
3. Nếu cần xem Header XML, tạo redacted copy bằng namespace-aware parser; mask UsernameToken, BinarySecurityToken, SignatureValue, DigestValue và custom sensitive headers.
4. Capture synthetic request để kiểm logger ghi đúng scope.
5. So SOAPAction, action parameter nếu SOAP 1.2, wsa:Action và Body QName với WSDL/endpoint mapping.
6. Assert không business side effect khi action mismatch.
7. Kiểm proxy không drop/rewrite Content-Type/action.
8. Nếu token có khả năng đã lộ trong log rộng, xử lý theo credential/certificate incident procedure.
9. Giới hạn diagnostic flag theo operation/correlation, expiry và sampling.
10. Tắt capture sau điều tra; kiểm access/retention.

**Tiêu chí đạt:** xác định action mismatch; token/certificate material không xuất hiện; diagnostic event đủ liên kết request/response; logging không làm thay đổi SOAP processing.

## 24. Checklist triển khai SOAP logging an toàn

1. **Phân biệt payload, Envelope, transport headers và MIME attachments** trong logger/event.
2. **Ưu tiên metadata-first** cho production.
3. **Chỉ bật payload/Envelope capture có mục đích, scope và expiry**.
4. **Không log WS-Security token, password, signature value hoặc private key**.
5. **Redact XML trên bản sao**, không sửa message đang xử lý.
6. **Dùng namespace-aware parser**, không regex đơn giản cho XML security fields.
7. **Áp policy cho Body, Header, Fault, attributes và attachment metadata**.
8. **Dùng allowlist production fields**; review khi schema/version mới.
9. **Giới hạn payload size, sampling và retention**.
10. **Không dump binary attachments vào application log**.
11. **Sanitize correlation ID và action URI** từ external input.
12. **Tách audit, diagnostic, security event và metrics**.
13. **Redaction failure thì drop payload**; logging failure không làm fail SOAP request.
14. **Dùng async logging bounded**, không block vô hạn.
15. **Test canary secrets** qua toàn interceptor/logger chain.
16. **Kiểm production profile không bật DEBUG/message tracing rộng**.
17. **Bảo vệ log store bằng least privilege, encryption và access audit**.
18. **Thiết lập retention/deletion theo policy**.
19. **Theo dõi logging overhead và queue saturation**.
20. **Tách HTTP SOAPAction với WS-Addressing Action** khi điều tra routing.
21. **Capture raw wire chỉ trong diagnostic window có kiểm soát**.
22. **Đồng bộ redaction policy với WSDL/contract version**.
23. **Ghi payload capture status/truncated/redaction policy version**.
24. **Sau incident, tắt flag và kiểm tra dữ liệu hết hạn**.

**Kết luận:** Payload logging trả lời câu hỏi về nội dung operation; full Envelope logging bổ sung SOAP Header để điều tra action, addressing và WS-Security. Nhưng Envelope có thể chứa token, certificate, chữ ký và metadata nhạy cảm, còn Body cũng có PII/business data. Với Spring-WS, nên bắt đầu từ metadata/correlation, dùng payload capture đã redaction khi cần và chỉ mở Envelope trong phạm vi có thời hạn. Redaction phải dựa trên XML structure, áp dụng cho bản sao, có size/sampling/retention controls và fail-safe. Đội vận hành có đủ tín hiệu chẩn đoán mà không biến log thành bản sao không kiểm soát của SOAP traffic.
