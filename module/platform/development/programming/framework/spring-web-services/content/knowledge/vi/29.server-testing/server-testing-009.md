# Kiểm thử xác thực, phân quyền và đường đi bị từ chối

## 1. Vì sao cần kiểm thử cả đường đi bị từ chối?

Trong module **SPRING_WEB_SERVICES**, SOAP service được xây dựng theo hướng contract-first với XSD/WSDL, JAXB, Spring-WS endpoint/client, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Một endpoint xử lý đúng request hợp lệ vẫn có thể không an toàn nếu chấp nhận caller không xác thực, cho phép truy cập tenant khác hoặc xử lý XML sai chính sách.

Kiểm thử máy chủ cần chứng minh hai nhóm hành vi:

- **Được phép:** caller có identity hợp lệ, quyền phù hợp, đúng resource scope và payload hợp đồng.
- **Bị từ chối:** thiếu/sai credentials, signer không trust, không có quyền, tenant không khớp, operation sai, message không đúng security policy hoặc XML không an toàn.

Không chỉ assert HTTP status hay exception. Phải xác minh đúng tầng từ chối, SOAP Fault/HTTP mapping, endpoint không thực hiện side effect và response/log không tiết lộ thông tin nhạy cảm.

### Mục tiêu học tập

1. Phân biệt authentication, authorization, message integrity và schema validation.
2. Xác định điểm kiểm soát trong Spring-WS server pipeline.
3. Kiểm thử UsernameToken, X.509 signature, TLS/mTLS và trust policy.
4. Kiểm tra quyền theo operation, role, partner, tenant và resource.
5. Xác minh request bị từ chối không tạo side effect.
6. Dùng MockWebServiceClient và integration tests đúng phạm vi.
7. Kiểm tra SOAP Fault, HTTP mapping, SOAP version và action dispatch.
8. Kiểm thử XXE, signature wrapping, replay và error leakage.
9. Xây security test matrix và CI gates.

## 2. Authentication, authorization và validation là các câu hỏi riêng

| Lớp | Câu hỏi | Ví dụ | Khi thất bại |
|---|---|---|---|
| Authentication | Caller là ai? | UsernameToken, certificate, mTLS | Unauthenticated |
| Authorization | Caller được làm gì trên resource nào? | Role, partner scope, tenant | Forbidden |
| Message security | Message có được bảo vệ đúng không? | Signature, Timestamp, Encryption | Security validation failure |
| Schema validation | XML có đúng contract? | XSD, QName, required fields | Schema/client fault |
| Business validation | Dữ liệu có hợp lệ nghiệp vụ? | Order state, limit | Business fault |

Signature hợp lệ không cấp quyền gọi mọi operation. Password đúng không chứng minh Body không bị sửa nếu policy yêu cầu XML Signature. XML hợp XSD không chứng minh caller được đọc order tenant khác.

### 2.1. Ví dụ phân loại lỗi

Với operation GetOrder:

- Không gửi credential: authentication failure.
- Credential hợp lệ nhưng signer certificate không trust: security/trust failure.
- Principal hợp lệ nhưng thiếu authority orders:read: authorization failure.
- Có quyền đọc nhưng order thuộc tenant khác: resource-level authorization failure.
- Có quyền nhưng orderId sai định dạng: schema/business validation failure.
- Message bị sửa sau khi ký: integrity failure trước domain handling.

Nên giữ error categories khác nhau cho audit và vận hành; public Fault vẫn cần tuân disclosure policy.

## 3. Spring-WS request pipeline và vị trí test

~~~mermaid
flowchart TD
    A["HTTP/JMS transport"] --> B["TLS / mTLS"]
    B --> C["SOAP message factory / XML parser"]
    C --> D["Endpoint mapping and dispatch"]
    D --> E["Endpoint interceptors"]
    E --> F["WS-Security validation"]
    F --> G["Principal resolution"]
    G --> H["Authorization"]
    H --> I["XSD/JAXB/business validation"]
    I --> J["Endpoint method"]
    J --> K["DB/JMS/remote side effects"]
    K --> L["SOAP response or Fault"]
~~~

Đây là cách phân rã khái niệm. Thứ tự thật phụ thuộc Spring-WS, WSS4J, Spring Security và cách register interceptors. Test phải xác minh application pipeline đang chạy, không coi sơ đồ là thứ tự mặc định bắt buộc.

### 3.1. Điểm từ chối có thể ở trước endpoint

WSS4J có thể reject message trước endpoint method. SOAP dispatch có thể fail trước interceptor theo operation. XML parser có thể reject payload trước JAXB. Với request phải bị reject trước nghiệp vụ, assert endpoint/business service invocation count bằng 0.

### 3.2. Fail closed

Nếu trust service, policy store hoặc authorization provider unavailable, operation yêu cầu bảo vệ không được tự động allow. Test timeout/unavailable và mapping lỗi đã định nghĩa. Không mặc định fallback allow vì dependency lỗi.

### 3.3. TLS khác WS-Security

TLS/mTLS bảo vệ transport connection; WS-Security có thể bảo vệ identity và XML parts end-to-end. HTTPS thành công không chứng minh SOAP Signature hợp lệ.

## 4. Threat model

| Asset | Threat | Kiểm soát cần test |
|---|---|---|
| SOAP payload | Tampering/unauthorized read | Signature, encryption, authorization |
| Credentials | Theft/replay | TLS, secret handling, nonce/TTL |
| Partner identity | Certificate spoofing | Trust và identity mapping |
| Tenant data | Cross-tenant access | Resource authorization |
| Operation | Unauthorized invocation | Authentication + operation policy |
| XML parser | XXE/entity expansion | Secure parser, limits |
| Audit trail | Missing/forged identity | Trusted principal, audit integrity |
| Error response | Information disclosure | Fault mapping, redaction |

Không cần dùng payload production nhạy cảm để test; tạo fixtures synthetic và test identities riêng.

## 5. Kiểm thử UsernameToken

Nếu service dùng WS-Security UsernameToken, policy có thể yêu cầu PasswordText/PasswordDigest, nonce, Created, TTL, callback validation và replay detection. Test theo đúng policy đã cấu hình.

### 5.1. Happy path

- Username thuộc principal đăng ký.
- Credential được kiểm tra đúng.
- Created/Nonce đáp ứng timestamp/replay policy.
- Principal được đưa vào security context/request context nếu ứng dụng yêu cầu.
- Endpoint chỉ được gọi sau validation.
- Audit ghi identity đã chuẩn hóa, không ghi password/token.

### 5.2. Negative cases

| Case | Đầu vào | Kỳ vọng |
|---|---|---|
| U1 | Thiếu Security header | Reject nếu policy bắt buộc |
| U2 | Thiếu UsernameToken | Authentication failure |
| U3 | Username không tồn tại | Authentication failure |
| U4 | Password sai | Authentication failure |
| U5 | Password type không hỗ trợ | Policy failure |
| U6 | Created quá hạn | Reject theo TTL |
| U7 | Clock skew vượt ngưỡng | Reject theo policy |
| U8 | Nonce dùng lại | Replay reject nếu replay cache bật |
| U9 | User disabled/locked | Reject |
| U10 | Callback/credential store lỗi | Fail closed |

### 5.3. PasswordDigest không thay TLS

PasswordDigest không thay HTTPS. Nonce/Created phải được kiểm tra; chỉ tìm thấy chuỗi PasswordDigest trong XML không chứng minh authentication an toàn.

## 6. Kiểm thử X.509 signature và trust

Tách các điều kiện cần xác minh:

1. Chữ ký có đúng về mặt mật mã không?
2. Certificate có được trust không?
3. Certificate có hiệu lực và đúng KeyUsage/EKU không?
4. Signer identity map đến partner/principal nào?
5. Signer có quyền gọi operation và truy cập resource không?
6. Body, Timestamp và headers bắt buộc có nằm trong signed references không?

### 6.1. Signature đúng nhưng signer không trust

Tạo test signer C, ký bằng private key C, trong khi server chỉ trust identities A/B. Chữ ký có thể verify bằng public key C, nhưng trust validation phải reject.

### 6.2. Certificate hết hạn/sai usage

Dùng certificate fixtures hết hạn hoặc sai KeyUsage/EKU. Không sửa system clock toàn test process dùng chung; dùng fixtures hoặc clock abstraction nếu implementation hỗ trợ.

### 6.3. Certificate chain hợp lệ nhưng identity không được phép

Một CA có thể cấp nhiều certificates. Chain hợp lệ không chứng minh certificate đại diện đúng partner. Test certificate cùng CA nhưng partner identity khác.

### 6.4. Signed parts thiếu

Tạo message có Body signature nhưng bỏ Timestamp hoặc WS-Addressing Action trong khi policy yêu cầu ký chúng. Server phải reject. Không chỉ assert có ds:Signature element.

## 7. TLS/mTLS authentication

mTLS xác thực client certificate ở transport layer; mapping identity và authorization vẫn là bước riêng.

| Test | Tình huống | Kết quả |
|---|---|---|
| T1 | Client cert trusted | TLS handshake pass |
| T2 | Không có cert khi listener yêu cầu mTLS | Handshake reject |
| T3 | Self-signed/untrusted cert | Reject |
| T4 | Cert hết hạn | Reject theo trust policy |
| T5 | Cert revoked | Reject nếu revocation checking cấu hình |
| T6 | TLS cert trusted nhưng thiếu operation role | TLS pass, application authorization reject |
| T7 | Client không trust server cert/hostname | Client từ chối trước SOAP |
| T8 | TLS cert khác WS-Security signer cert | Verify từng identity và mapping |

MockWebServiceClient không thực hiện TLS handshake. Dùng HTTPS server/container thật hoặc test deployment tương ứng để kiểm mTLS.

## 8. Authorization theo operation, role và resource

| Principal | GetOrder | SubmitOrder | CancelOrder |
|---|---:|---:|---:|
| partner-reader | Allow trong tenant mình | Deny | Deny |
| partner-writer | Allow trong tenant mình | Allow trong tenant mình | Theo scope |
| partner-admin | Allow trong scope | Allow | Theo policy |
| unknown-partner | Deny | Deny | Deny |

### 8.1. Operation-level authorization

Principal đã authenticate có thể được phép GetOrder nhưng không được CancelOrder. Test mỗi operation/role pair; một test đại diện không chứng minh cả service policy đúng.

### 8.2. Resource-level authorization

Có authority orders:read không có nghĩa được đọc tất cả orders. Test same tenant, other tenant, other owner, missing resource và deleted resource. Tránh IDOR/BOLA qua orderId.

### 8.3. Tenant isolation

Caller A có thể đổi tenantId trong payload để thử đọc B. Server nên xác định authorized tenant từ authenticated principal/claims/policy rồi đối chiếu payload. Không dùng tenantId do caller khai báo làm nguồn authorization duy nhất.

### 8.4. Deny by default

Principal/role/operation không có policy rõ ràng phải bị reject. Test unknown roles, missing rules và policy provider unavailable. Không allow khi không tìm thấy policy.

## 9. Kiểm tra object ownership và BOLA/IDOR

Ví dụ endpoint chỉ lookup theo ID là chưa đủ:

~~~java
@PayloadRoot(
    namespace = "urn:example:orders:v1",
    localPart = "GetOrderRequest"
)
@ResponsePayload
public GetOrderResponse getOrder(
        @RequestPayload GetOrderRequest request) {
    Order order = orderService.getById(request.getOrderId());
    return mapper.toResponse(order);
}
~~~

Nếu không kiểm owner/tenant, caller có thể đọc resource ngoài scope.

### 9.1. Enforce ở service boundary

~~~java
public Order getReadableOrder(
        AuthenticatedPartner principal,
        String orderId) {

    Order order = repository.findById(orderId)
        .orElseThrow(OrderNotFoundException::new);

    authorization.requireCanRead(
        principal, order.getTenantId(), order.getOwnerId()
    );
    return order;
}
~~~

Đây là pseudocode; dự án có thể dùng Spring Security method authorization, policy service hoặc tenant-scoped repository query.

### 9.2. Test cross-tenant

- A đọc order tenant A: allow.
- A đọc order tenant B: deny.
- B đọc order tenant B: allow.
- Principal không có tenant mapping: deny.
- Payload khai tenant B nhưng principal A: deny.
- Response/Fault không tiết lộ dữ liệu tenant khác.

## 10. SOAP dispatch, QName và actions

SOAP dispatch phụ thuộc SOAP version, payload root QName, endpoint mapping, Action và cấu hình.

### 10.1. QName là namespace cộng local name

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-100</ord:orderId>
</ord:GetOrderRequest>
~~~

Test namespace đúng, namespace version khác, prefix khác nhưng cùng namespace, local name sai và element không namespace. Prefix thay đổi nhưng URI/local name giữ nguyên thì QName không đổi.

### 10.2. SOAPAction và WS-Addressing Action

Test SOAPAction đúng, thiếu/rỗng, không khớp Body QName; WS-Addressing Action không khớp operation; Action bị sửa sau ký; SOAP 1.1 headers gửi vào SOAP 1.2 endpoint.

Expected behavior phải theo WSDL/binding và contract. Không dispatch Action giả mạo nếu policy yêu cầu Action khớp hoặc phải được ký.

### 10.3. Unknown operation

Request không map đến endpoint phải bị từ chối. Không fallback sang generic handler hoặc endpoint có quyền rộng hơn.

## 11. Đường đi từ chối phải không tạo side effect

~~~mermaid
flowchart TD
    A["Invalid or unauthorized SOAP request"] --> B["Security / authorization checks"]
    B --> C{"Allowed?"}
    C -->|"No"| D["Controlled SOAP Fault"]
    D --> E["Endpoint invocation = 0"]
    E --> F["No DB write / JMS publish / remote SOAP call"]
    C -->|"Yes"| G["Endpoint and business service"]
~~~

### 11.1. Assertions

Với mỗi negative test, kiểm:

- SOAP Fault/HTTP result đúng contract.
- Endpoint/business service không chạy nếu reject trước đó.
- Repository không insert/update/delete.
- JmsTemplate không publish.
- Partner SOAP client không được gọi.
- Không phát email/payment/file side effect.
- Audit/security event có theo policy.
- Fault/log không chứa credential/token/raw sensitive payload.

### 11.2. Spy và integration assertions

Dùng mock/spy cho business service, repository, JmsTemplate và partner client trong component tests. Integration tests kiểm DB và broker state sau request. Chỉ assert exception không đủ vì side effect có thể đã xảy ra trước exception.

### 11.3. Authorization trước side effects

Nếu endpoint ghi DB trước khi check authorization, test sẽ phát hiện. Đặt authorization ở boundary trước operation side effect. Transaction rollback không bảo vệ external effects như JMS publish hoặc remote SOAP call nếu chúng đã thoát khỏi DB transaction.

## 12. SOAP Fault và HTTP mapping

| Lỗi | Mapping có thể dùng | Cần xác minh |
|---|---|---|
| Không authentication | Security/auth fault theo policy | Không tiết lộ thông tin credential |
| Không đủ quyền | Authorization/client fault theo contract | Không trả resource data |
| Signature invalid | Security fault | Endpoint không chạy |
| Timestamp/replay | Security fault | Message cũ không được chấp nhận |
| XSD invalid | Schema/client fault | Field/QName an toàn |
| Unknown operation | Dispatch fault | Không fallback |
| Internal failure | Server fault | Không stack trace |
| Dependency unavailable | Retryable fault/status theo policy | Client phân loại retry |

Mapping cụ thể phụ thuộc SOAP version, exception resolver, interceptor và contract. Không gán cùng HTTP status cho mọi lỗi một cách máy móc.

### 12.1. SOAP 1.1 và SOAP 1.2

Test Envelope namespace, Fault structure, content type và HTTP response theo binding: SOAP 1.1 có faultcode/faultstring/detail; SOAP 1.2 có Code/Reason/Detail.

### 12.2. Fault detail không chứa secrets

Không trả password, UsernameToken, private key, keystore path, SQL, stack trace hoặc internal hostnames. Dùng public error code/message và correlation ID; giữ cause trong log nội bộ được kiểm soát.

### 12.3. Security fault khác business fault

Một caller được authenticate/authorize có thể bị business reject vì order không thể cancel. Không dùng security fault cho business rule vì client sẽ retry/điều tra sai hướng.

## 13. Chọn đúng công cụ test

| Công cụ | Phạm vi | Dùng cho |
|---|---|---|
| MockWebServiceClient | Spring-WS server trong test context | Endpoint mapping, interceptors, SOAP response/Fault |
| MockWebServiceServer | WebServiceTemplate client | Outbound SOAP request/response |
| Spring Security test support | SecurityContext/method authorization | Principal, roles, policy |
| WSS4J crypto fixtures | XML security | Signature, trust, token, Timestamp |
| Embedded HTTPS server | Transport | TLS/mTLS |
| Broker/provider integration | Messaging transport | SOAP over JMS/async |
| End-to-end environment | Stack thực tế | Identity, routing, cert, partner behavior |

### 13.1. MockWebServiceClient skeleton

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = SoapServerTestConfig.class)
class OrdersEndpointTest {

    @Autowired
    private ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void returnsOrderForAuthorizedCaller() {
        Source request = new StringSource("""
            <ord:GetOrderRequest
                xmlns:ord="urn:example:orders:v1">
              <ord:orderId>ORD-100</ord:orderId>
            </ord:GetOrderRequest>
            """);

        client.sendRequest(withPayload(request))
            .andExpect(payload(new StringSource("""
                <ord:GetOrderResponse
                    xmlns:ord="urn:example:orders:v1">
                  <ord:orderId>ORD-100</ord:orderId>
                  <ord:status>PROCESSING</ord:status>
                </ord:GetOrderResponse>
                """)));
    }
}
~~~

Skeleton minh họa; imports/matchers/security context và setup phụ thuộc Spring-WS version/test configuration.

### 13.2. Mock không thay TLS

MockWebServiceClient không tạo HTTPS socket hoặc TLS handshake. Dùng embedded/container HTTPS server và test client cert riêng.

### 13.3. MockWebServiceServer là phía client

Không dùng MockWebServiceServer để kết luận server enforce authorization; công cụ chủ yếu kiểm WebServiceTemplate gửi request và parse response.

## 14. Test identities và fixtures

Tạo identities test có tên rõ ràng:

~~~text
partner-a-reader
partner-a-writer
partner-b-admin
unknown-partner
revoked-partner
expired-partner
untrusted-signer
wrong-tenant-principal
~~~

Mỗi fixture ghi mechanism, expected principal/partner, roles/tenant, certificate dates/issuer/key usage và test owner. Không dùng production credentials hoặc private keys thật.

### 14.1. Identity mapping

Không map chỉ theo CN nếu có thể trùng. Dùng Subject/SAN/fingerprint/issuer/serial hoặc partner registry theo policy. Test certificate cùng CN nhưng khác issuer/key.

### 14.2. Rotation

Giữ cert v1/v2 để test transition; signer cũ được chấp nhận đúng thời gian policy rồi bị từ chối sau retire. Không đưa private key vào fixture chia sẻ cho consumer.

## 15. Ma trận authentication/authorization

| ID | Authentication | Authorization | Resource | Expected |
|---|---|---|---|---|
| A01 | Valid A | Read allowed | Tenant A order | Success |
| A02 | Missing | N/A | Valid request | Reject before endpoint |
| A03 | Wrong password | N/A | Valid request | Reject |
| A04 | Expired token | N/A | Valid request | Reject |
| A05 | Trusted signer A | Read allowed | Tenant A order | Success |
| A06 | Untrusted signer C | N/A | Signed message | Security reject |
| A07 | Valid A | Read denied | Tenant A | Authorization reject |
| A08 | Valid reader A | Submit denied | Submit | Authorization reject |
| A09 | Valid A | Read allowed | Tenant B order | Cross-tenant reject |
| A10 | Valid A | Read allowed | Missing resource | Safe not-found |
| A11 | Valid A | Policy unavailable | Valid request | Fail closed |
| A12 | Valid A | Read allowed | Tampered signed Body | Signature reject |
| A13 | Valid A | Read allowed | Unsigned required Action | Security reject |
| A14 | Valid A | Read allowed | Expired Timestamp | Reject |
| A15 | Valid A | Read allowed | Replayed nonce/message | Replay reject |
| A16 | Valid A | Read allowed | Wrong SOAPAction | Dispatch reject |
| A17 | Valid A | Read allowed | Unknown QName | Dispatch reject |
| A18 | mTLS absent | N/A | Valid SOAP | TLS handshake reject |
| A19 | mTLS trusted | Read denied | Valid SOAP | TLS pass, app reject |
| A20 | Valid A | Read allowed | XXE/DTD | Parser reject |

Mỗi case cần xác định layer, expected Fault/HTTP result, endpoint invocation count, side effects và audit evidence.

## 16. XML parser, XXE và resource exhaustion

WS-Security không tự làm XML parser an toàn. SOAP server phải xử lý XML không tin cậy với parser configuration phù hợp.

### 16.1. XXE negative fixture

~~~xml
<?xml version="1.0"?>
<!DOCTYPE foo [
  <!ENTITY xxe SYSTEM "file:///not-a-real-secret">
]>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
      <ord:orderId>&xxe;</ord:orderId>
    </ord:GetOrderRequest>
  </soap:Body>
</soap:Envelope>
~~~

Không dùng file nhạy cảm thật. Dùng sentinel file hoặc controlled external endpoint để xác minh parser không truy cập external resource và request bị reject theo policy.

### 16.2. Entity expansion và payload limits

Test XML deeply nested, oversized text, excess elements và attachments lớn nếu hỗ trợ. Giới hạn message size, nesting, parser work và processing time.

### 16.3. Không thử DoS trên production

Resource-exhaustion tests cần giới hạn và chạy trong môi trường biệt lập. Đo rejection, CPU/memory bounds và recovery.

## 17. XML Signature Wrapping và verified node binding

Signature chỉ bảo vệ references cụ thể. Attacker có thể cố tạo duplicate Body/header hoặc chuyển signed node để business code đọc node khác.

Test:

- Body đúng được ký và endpoint đọc đúng verified element.
- Duplicate Body hoặc duplicate ID: reject.
- Signed element ở node khác, unsigned node được endpoint chọn: reject.
- wsa:Action bị sửa sau ký: signature fail nếu policy yêu cầu ký.
- Reference ID ambiguous/invalid: reject.
- Signature hợp lệ nhưng business QName không phải operation được dispatch: reject.

Không chỉ verify DOM rồi tìm element theo local name không namespace-qualified. Security validation và JAXB/business binding phải dùng đúng SOAP structure, QName và verified node.

## 18. Replay, Timestamp và idempotency

Message có chữ ký hợp lệ vẫn có thể bị phát lại. Timestamp TTL, nonce cache và message replay detection giúp giảm replay; business idempotency vẫn cần riêng.

### 18.1. Replay tests

1. Gửi request ký hợp lệ lần đầu.
2. Gửi lại nguyên message trong TTL.
3. Gửi lại sau TTL.
4. Dùng lại nonce với Timestamp mới.
5. Gửi business idempotency key giống nhau trong message ký mới.
6. Gửi cùng message ID nhưng payload thay đổi.

Expected behavior phụ thuộc policy. WS-Security replay protection không thay business duplicate handling nếu client tạo request mới cho cùng operation.

### 18.2. Read-only và side-effecting operations

GetOrder thường an toàn để retry hơn SubmitOrder/ChargePayment, nhưng read có thể có audit/usage side effects. Idempotency policy phải theo business semantics.

## 19. SOAP Fault và information disclosure

Fault phải giúp client xử lý nhưng không tiết lộ password, UsernameToken, authorization headers, private key, keystore path, SQL, stack trace, internal hostname hoặc payload tenant khác.

Public Fault có thể gồm stable error code, safe message và correlation ID. Internal cause được ghi ở log bảo vệ, access-controlled và redacted.

### 19.1. Authentication enumeration

Caller không nên dễ dàng phân biệt account tồn tại nhưng password sai với account không tồn tại nếu điều đó tạo account enumeration risk. Internal audit có thể phân loại sâu hơn; public Fault theo disclosure policy.

### 19.2. Audit event

~~~json
{
  "eventType": "SOAP_AUTHORIZATION_DENIED",
  "service": "orders",
  "operation": "GetOrder",
  "principal": "partner-a",
  "resourceTenant": "tenant-b",
  "reasonCode": "TENANT_SCOPE_MISMATCH",
  "correlationId": "test-correlation-100",
  "decision": "DENY"
}
~~~

JSON chỉ là ví dụ. Chỉ ghi fields được phép; không lưu raw payload, credentials, PII không cần thiết hoặc key material.

### 19.3. Metrics

Theo dõi counters theo service/operation/fault category. Tránh raw user IDs/order IDs/correlation IDs làm metric labels có cardinality lớn.

## 20. Spring Security method authorization

Nếu ứng dụng dùng Spring Security, policy có thể enforce ở service layer:

~~~java
@Service
public class OrderQueryService {

    @PreAuthorize("hasAuthority('orders:read')")
    public OrderView getOrder(String orderId) {
        return repository.findViewById(orderId)
            .orElseThrow(OrderNotFoundException::new);
    }
}
~~~

Authority trên chưa enforce tenant ownership. Cần policy nhận principal và resource tenant hoặc repository query có tenant predicate.

### 20.1. Method security phải được bật

Test context cần enable method security theo Spring Security version. Unit test gọi new service không đi qua Spring proxy sẽ không test annotation enforcement.

### 20.2. Self-invocation

Một method trong cùng class gọi method có annotation có thể không đi qua proxy theo proxy-based configuration. Test path thật từ SOAP endpoint đến Spring-managed service bean.

### 20.3. Policy ở đúng boundary

Nếu service còn được gọi từ JMS listener, REST hoặc scheduler, chỉ authorize tại SOAP endpoint có thể bị bypass qua entry point khác. Enforce policy ở service boundary phù hợp và test mọi caller path.

## 21. Endpoint interceptors và chain order

### 21.1. WSS4J validation

Test interceptor reject signature/token invalid trước endpoint. Kiểm actions, Crypto/truststore, Timestamp TTL, replay cache và signed parts.

### 21.2. Custom EndpointInterceptor

Kiểm:

- handleRequest trả true để tiếp tục, false để dừng theo interceptor contract.
- Exception đi qua intended fault resolver.
- Security context được dọn giữa requests.
- Thread-local/request context không rò principal.
- handleResponse/handleFault không log payload nhạy cảm.

### 21.3. Interceptor order

Logging interceptor trước WS-Security có thể ghi payload chưa validate; authorization sau endpoint side effect là quá muộn. Test chain order trong application context, không suy từ tên bean.

## 22. Response authorization và data minimization

- Reader có thể đọc status nhưng không được xem payment details.
- Partner chỉ thấy fields thuộc tenant/scope.
- Fault detail không chứa resource data nhạy cảm.
- List/search operations áp tenant scope cho từng row.
- Bulk request với mixed allowed/denied resources phải có policy all-or-nothing hoặc partial result rõ.

Test response DTO mapping và SOAP XML thực tế; không marshal trực tiếp entity nội bộ nếu có fields không được phép lộ.

## 23. Negative-test anti-patterns

| Anti-pattern | Vì sao không đủ | Cải thiện |
|---|---|---|
| Chỉ assert HTTP 500 | Không chứng minh đúng Fault/layer | Assert SOAP Fault và no side effects |
| Chỉ test wrong password | Bỏ authorization/tenant | Role/resource matrix |
| Mock toàn WSS4J | Không test crypto | Signed SOAP fixtures + real validation |
| Mock TLS handshake | Không test mTLS | HTTPS integration |
| Assert exception, không assert endpoint count | Endpoint có thể đã chạy | Verify zero invocation |
| Dùng production credentials | Secret exposure | Test identities riêng |
| Trust-all test store | Test vô nghĩa | Truststore chỉ gồm expected issuers |
| Chỉ test Body signature | Header/routing có thể bị sửa | Test signed parts |
| Bỏ replay tests | Message hợp lệ có thể phát lại | TTL/nonce/duplicate tests |
| Chỉ test một tenant | Bỏ sót BOLA | Cross-tenant matrix |
| Fault có stack trace | Information disclosure | Safe fault mapper |

## 24. CI và release gates

| Tầng | Test | Khi chạy |
|---|---|---|
| Unit | Policy/principal mapping/business rules | Mỗi commit |
| Component | Endpoint mapping, interceptors, Fault, no side effect | Mỗi PR |
| Crypto integration | WSS4J signature/trust/token/Timestamp | PR/security pipeline |
| TLS integration | mTLS/certificate chain/expiry | Trước release |
| DB/broker integration | Audit/outbox effects không chạy khi deny | Integration pipeline |
| End-to-end | Identity, WSDL, WS-Security, TLS, partner behavior | Staging |
| Adversarial regression | XXE, wrapping, replay, tenant isolation | Security cadence |

### 24.1. Fail the gate khi

- Unauthorized request tạo side effect.
- Untrusted signer được chấp nhận.
- Cross-tenant resource bị lộ.
- Required signed parts bị bỏ qua.
- Replay policy bị bypass.
- Parser resolve external entities trái policy.
- Fault lộ secrets hoặc internal details.
- mTLS-required endpoint chấp nhận client không certificate.
- Security test quan trọng bị skip mà không có exception owner.

### 24.2. Test fixture hygiene

Dùng test certificates riêng, expiry kiểm soát, deterministic clock/nonce fixtures khi phù hợp và sanitized payloads. Không đưa production private keys vào source hoặc CI artifacts. Fixture có owner và rotation policy nếu credential còn hiệu lực.

## 25. Bài thực hành: bảo vệ Orders SOAP server

Contract test environment:

~~~text
SOAP 1.1 over HTTPS
Namespace: urn:example:orders:v1

Authentication:
  X.509 WS-Security signature or UsernameToken
Authorization:
  orders:read, orders:submit
Tenant:
  derived from authenticated partner identity
Signed parts:
  SOAP Body + Timestamp + WS-Addressing Action
~~~

### Nhiệm vụ

1. Thiết kế WSDL/XSD cho GetOrder, SubmitOrder và Fault.
2. Cấu hình endpoint mapping và WSS4J validation interceptor.
3. Tạo test identities cho partner A/B, reader/writer và untrusted signer.
4. Tạo truststore chỉ chứa expected certificates.
5. Map validated identity thành application principal.
6. Implement operation-level authorization.
7. Implement resource/tenant-level authorization.
8. Test GetOrder trong tenant mình được allow.
9. Test GetOrder tenant khác bị deny.
10. Test reader gọi SubmitOrder bị deny.
11. Test token thiếu/sai/hết hạn và signature invalid.
12. Test required WS-Addressing Action không ký.
13. Test SOAPAction/QName mismatch và unknown operation.
14. Test XXE, duplicate ID/signature wrapping và replay.
15. Assert denied requests không gọi DB writes/JMS/partner client.
16. Assert Fault không lộ password/token/stack trace/tenant data.
17. Test TLS/mTLS qua HTTPS integration.
18. Ghi audit principal/operation/reason/correlation.
19. Test principal contexts song song để phát hiện context leakage.
20. Thêm suite vào CI và định nghĩa release gates.

**Tiêu chí đạt:** Principal xác định đúng; role/tenant scope được enforce trước side effect; denied path trả Fault an toàn; không có unauthorized DB/JMS/remote SOAP operation; crypto/TLS test chạy ở đúng layer.

### 25.1. Tình huống

**A:** Partner A có certificate trusted và quyền orders:read nhưng yêu cầu order thuộc tenant B. Server reject ở đâu, và cần chứng minh gì?

**B:** MockWebServiceClient trả Fault khi thiếu UsernameToken. Vì sao vẫn cần mTLS integration test?

**C:** Body ký đúng nhưng WS-Addressing Action không ký theo policy. Vì sao kiểm một Signature element chưa đủ?

**D:** Fault là Forbidden nhưng repository đã ghi row nghiệp vụ và JmsTemplate đã publish. Test nào phát hiện lỗi, và authorization nên đặt ở boundary nào?

## 26. Checklist trước khi release

- [ ] Authentication và authorization được test độc lập.
- [ ] UsernameToken: missing, invalid, expired, nonce/replay.
- [ ] X.509 signature: valid, untrusted, expired, wrong identity/key usage.
- [ ] TLS/mTLS được test bằng HTTPS integration.
- [ ] Operation role/scope được bao phủ.
- [ ] Resource/tenant ownership và IDOR/BOLA được kiểm.
- [ ] Deny-by-default và policy failure fail closed.
- [ ] SOAP version, QName, SOAPAction, WS-Addressing Action được kiểm.
- [ ] Signed parts, Timestamp và anti-replay được xác minh.
- [ ] XML parser chống XXE/entity expansion và có resource limits.
- [ ] Duplicate ID/Signature Wrapping scenarios được kiểm.
- [ ] Negative requests không thực hiện DB/JMS/remote side effects.
- [ ] Fault/HTTP mapping đúng contract, không lộ secrets.
- [ ] Audit có identity, operation, decision và correlation.
- [ ] Security context không rò giữa requests/threads.
- [ ] Response mapping không lộ tenant data ngoài scope.
- [ ] Unit/component/crypto/TLS/E2E tests phân lớp.
- [ ] Test fixtures không dùng production credentials.
- [ ] CI blocks unauthorized success và regressions.

## 27. Ghi nhớ

- **Authentication xác định caller; authorization quyết định caller được làm gì trên resource nào.**
- WS-Security Signature hợp lệ không tự cấp quyền; HTTPS không tự bảo vệ SOAP Body ở message level.
- Test bao phủ UsernameToken, X.509 trust, mTLS, role, tenant, operation và resource.
- Denied path phải kiểm Fault, endpoint invocation count, DB/JMS/remote effects và audit.
- MockWebServiceClient phù hợp server component tests nhưng không thay TLS/mTLS hoặc provider integration.
- SOAPAction, WS-Addressing Action và QName dispatch là bề mặt cần kiểm.
- XML Signature Wrapping, XXE, replay và resource exhaustion cần negative fixtures an toàn.
- Fault/log không tiết lộ credentials, private details hoặc tenant data khác.
- Security tests phải là release gates với owner cho mọi exception.

**Câu hỏi tự kiểm tra:** Một client có certificate trusted và Signature hợp lệ nhưng principal chỉ có orders:read, trong khi request muốn SubmitOrder và khai tenant khác. Hãy phân biệt authentication, message validation và authorization; xác định Fault theo contract; liệt kê assertions chứng minh endpoint không chạy, DB/JMS/partner không có side effect, audit ghi đúng decision; giải thích vì sao MockWebServiceClient không đủ kiểm mTLS.

## 28. Tài liệu tham khảo để đối chiếu

- Spring Web Services Reference: server-side testing, endpoint interceptors, dispatch và SOAP Fault.
- Spring Security Reference: authentication, authorization, method security và test support.
- Apache WSS4J documentation: UsernameToken, X.509, XML Signature/Encryption, replay/Timestamp.
- OASIS Web Services Security specifications and profiles.
- W3C SOAP 1.1/1.2, WS-Addressing và XML Signature specifications.
- OWASP Web Service Security guidance: authorization, parser hardening, XXE và XML Signature Wrapping.
- Jakarta XML Binding/Servlet và TLS provider documentation tương ứng dependencies của dự án.

API/package, Fault mapping và security defaults khác nhau theo Spring-WS, Spring Security, WSS4J và servlet-container versions. Pin dependencies và xác minh bằng integration tests trên stack triển khai thực tế.

