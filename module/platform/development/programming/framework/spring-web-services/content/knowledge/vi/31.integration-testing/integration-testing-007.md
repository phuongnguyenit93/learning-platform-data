# Kiểm tra từ chối thông điệp sai bảo mật trước khi chạy nghiệp vụ

## 1. Mục tiêu: chứng minh request bị từ chối không chạm tới nghiệp vụ

Trong module **SPRING_WEB_SERVICES**, dịch vụ SOAP được thiết kế theo hướng **contract-first** với XSD/WSDL, JAXB và Spring-WS endpoints. Một dịch vụ tích hợp doanh nghiệp thường có nhiều lớp bảo vệ: HTTPS và xác thực HTTP ở tầng Servlet, WS-Security ở SOAP Header, rồi authorization theo partner, operation và tài nguyên ở tầng ứng dụng.

Một test chỉ khẳng định request sai nhận HTTP 401, HTTP 403 hoặc SOAP Fault vẫn chưa chứng minh đầy đủ rằng bảo mật hoạt động đúng. Cần chứng minh đồng thời:

1. Request bị từ chối ở đúng lớp bảo mật.
2. Endpoint/business service không được gọi khi request không đạt yêu cầu.
3. Không có side effect như ghi database, phát event, gọi hệ thống ngoài hoặc tạo giao dịch.
4. Request hợp lệ vẫn đi qua đúng chuỗi kiểm tra và thực hiện nghiệp vụ bình thường.
5. Retry, replay, sai chữ ký và identity không khớp cũng không tạo side effect.

Tiêu chí cốt lõi là **kiểm tra cả kết quả từ chối lẫn việc business service không được thực thi**. Chỉ kiểm tra exception hoặc status code là chưa đủ.

### Mục tiêu học tập

Sau bài thuộc chương **Kiểm thử tích hợp**, bạn có thể:

- Phân biệt HTTP authentication, WS-Security message validation và authorization ở service layer.
- Xác định request bị từ chối trước endpoint, trước service method hay sau khi nghiệp vụ đã bắt đầu.
- Dùng spy/mock, invocation counter và database assertions để chứng minh business code không chạy.
- Kiểm thử UsernameToken, Timestamp, Signature, replay và sai identity theo security policy.
- Kiểm thử HTTP filter chain cùng SOAP interceptor trên HTTP server đang chạy.
- Phân biệt HTTP 401/403 với SOAP Fault và business Fault.
- Kiểm tra custom EndpointInterceptor dừng endpoint invocation đúng cách.
- Thiết kế test âm và test dương có đối chứng, tránh test pass chỉ vì request chưa tới server.

## 2. Ba ranh giới bảo mật cần kiểm tra riêng

Một SOAP request thường đi qua nhiều tầng. Mỗi tầng có thể từ chối request, nhưng vị trí từ chối và response khác nhau.

~~~mermaid
flowchart TD
    A["SOAP client"] --> B["HTTPS / Servlet container"]
    B --> C["Spring Security FilterChain"]
    C -->|HTTP auth fail| D["HTTP 401 / 403"]
    C -->|Pass| E["MessageDispatcherServlet"]
    E --> F["SOAP parsing / endpoint mapping"]
    F --> G["EndpointInterceptor / WSS4J"]
    G -->|WS-Security fail| H["SOAP Security Fault"]
    G -->|Pass| I["Endpoint adapter"]
    I --> J["Spring-managed application service"]
    J --> K["Method authorization"]
    K -->|Denied| L["AccessDeniedException / mapped Fault"]
    K -->|Allowed| M["Business transaction and side effects"]
~~~

### 2.1. HTTP authentication và authorization

Spring Security Servlet filter chain chạy trước MessageDispatcherServlet. Nếu Basic/Bearer/mTLS policy ở HTTP không đạt, request có thể bị trả HTTP 401/403 trước khi SOAP message được dispatch.

Ở tầng này, test cần xác minh HTTP status và challenge/header phù hợp; SOAP dispatcher hoặc interceptor chưa được gọi; business service không được gọi; và không có transaction hay side effect.

Đây là **HTTP security rejection**, không nhất thiết có SOAP Envelope hoặc SOAP Fault. Đừng viết test mong có SOAP Fault khi request đã bị Servlet filter chặn.

### 2.2. WS-Security validation tại SOAP interceptor

Nếu HTTP authentication đã thành công, SOAP request được parse và đưa qua endpoint mapping/interceptor chain. EndpointInterceptor.handleRequest(...) chạy **sau khi mapping xác định endpoint nhưng trước khi endpoint adapter gọi endpoint**. Interceptor trả true để tiếp tục hoặc false để dừng chain.

Wss4jSecurityInterceptor có thể validate UsernameToken, Timestamp, Signature và các security actions cấu hình. Khi WS-Security validation thất bại, server thường tạo SOAP Fault hoặc trả lỗi theo policy của interceptor/message stack.

Ở tầng này, test phải chứng minh request đã qua HTTP authentication; SOAP interceptor thực sự chạy; security validation từ chối request; endpoint adapter/business service chưa được gọi; và không có business side effect.

### 2.3. Authorization tại service layer

Token hợp lệ không đồng nghĩa caller có quyền xem hoặc cập nhật tài nguyên. Authorization thường cần kiểm tra verified principal, partner/tenant, operation, record ownership và quyền dữ liệu.

Với Spring Security method security, EnableMethodSecurity bật các annotation như PreAuthorize. Method-security interceptor kiểm tra quyền trước khi method body được thực thi. Nếu denied, AccessDeniedException được ném ra; khi không nằm trong HTTP filter request context, ứng dụng có thể phải tự ánh xạ exception đó thành SOAP Fault an toàn.

Test ở tầng này cần chứng minh caller đã xác thực nhưng thiếu quyền, business method bị chặn trước khi body chạy và không có side effect.

### 2.4. Ma trận phân biệt tầng từ chối

| Tầng | Request đã tới | Kết quả thường gặp | Chỉ số quan sát |
| --- | --- | --- | --- |
| HTTP filter | Servlet container | HTTP 401/403 | Filter/dispatcher/interceptor counters |
| SOAP interceptor | MessageDispatcher và endpoint mapping | SOAP Security Fault hoặc processing error theo policy | Interceptor count, endpoint count |
| Method authorization | Endpoint đã được invoke, trước business method body được bảo vệ | SOAP Fault/error mapping theo cấu hình | Service method body count |
| Business validation | Business code đã chạy | Business Fault | Business invocation và domain outcome |

Endpoint adapter có thể đã được chọn trước khi interceptor từ chối. Điều quan trọng là **endpoint method và application service không được chạy**. Nếu muốn chứng minh việc từ chối xảy ra trước endpoint adapter, cần instrumentation ở đúng điểm đó.

## 3. Quy tắc thiết kế test: assert cả denial và zero side effects

Một test âm tốt có hai nhóm assertion.

**Assertion về từ chối:** kiểm tra HTTP status, SOAP Fault category/code hoặc exception mà client nhận được theo contract.

**Assertion về không thực thi nghiệp vụ:** verify service không tương tác, invocation counter bằng 0, database không thay đổi, không phát event và không gọi outbound collaborator.

Ví dụ với Mockito:

~~~java
verify(orderApplicationService, never())
    .cancelOrder(any(CancelOrderCommand.class));
~~~

Dùng verifyNoInteractions(service) khi test scenario kỳ vọng request không được chạm tới bất kỳ phương thức nào của collaborator đó:

~~~java
verifyNoInteractions(orderApplicationService);
~~~

Không dùng verifyNoInteractions với bean có các method hợp lệ được gọi trong quá trình setup/health checks. Hãy spy/mock đúng boundary nghiệp vụ cần bảo vệ.

### 3.1. Đếm lần gọi bằng counter

Với Spring context integration test, spy bean có thể được kiểm tra bằng verify. Nếu cần chứng minh thứ tự và số lần chạy, dùng AtomicInteger trong test fixture hoặc một recording collaborator:

~~~java
final class InvocationRecorder {
    private final AtomicInteger calls = new AtomicInteger();

    void record() {
        calls.incrementAndGet();
    }

    int count() {
        return calls.get();
    }
}
~~~

Test âm phải assert count bằng 0. Test dương phải assert đúng số lần, chẳng hạn 1. Counter là bằng chứng bổ sung; nó không thay database assertions hoặc kiểm tra outbox/event.

### 3.2. Kiểm tra database và event

Với nghiệp vụ có side effect, hãy kiểm tra bản ghi chưa được insert/update; trạng thái order/invoice không đổi; không có outbox event; không có message gửi tới broker; không có outbound HTTP/payment call; và không tạo audit entry nghiệp vụ thành công.

Có thể dùng test database transaction và query trạng thái trước/sau. Đảm bảo assertion nhìn thấy commit/rollback thật: một test luôn rollback ở cuối có thể che mất commit sai nếu không đọc trạng thái trong lúc transaction hoặc kiểm tra qua connection phù hợp.

## 4. Xây dựng ví dụ: hủy đơn hàng bằng SOAP

Giả sử hệ thống có operation:

~~~xml
<ord:CancelOrderRequest
    xmlns:ord="https://example.com/orders/v1">
    <ord:orderId>ORD-1001</ord:orderId>
    <ord:reason>CUSTOMER_REQUEST</ord:reason>
</ord:CancelOrderRequest>
~~~

Caller phải đáp ứng các điều kiện:

1. HTTP Basic hoặc Bearer token hợp lệ theo deployment policy;
2. WS-Security UsernameToken/Signature hợp lệ theo partner policy;
3. HTTP identity và SOAP identity được ánh xạ nhất quán nếu mô hình yêu cầu combined identity;
4. Partner có quyền hủy order thuộc tenant của mình;
5. Order đang ở trạng thái cho phép hủy.

| Kịch bản | HTTP | WS-Security | Quyền tài nguyên | Kết quả mong đợi |
| --- | --- | --- | --- | --- |
| Không có HTTP credentials | Fail | Không cần xét | Không xét | HTTP 401; không dispatch SOAP. |
| HTTP credentials sai | Fail | Không cần xét | Không xét | HTTP 401; không nghiệp vụ. |
| HTTP hợp lệ, thiếu UsernameToken | Pass | Missing | Không xét | SOAP security rejection; không endpoint/service. |
| HTTP hợp lệ, digest sai | Pass | Invalid | Không xét | SOAP security rejection; không nghiệp vụ. |
| HTTP hợp lệ, Timestamp hết hạn | Pass | Expired | Không xét | SOAP security rejection; không nghiệp vụ. |
| HTTP hợp lệ, Signature sai | Pass | Invalid signature | Không xét | SOAP security rejection; không nghiệp vụ. |
| HTTP A, SOAP B | Pass | Token hợp lệ | Identity mismatch | Security/identity rejection; không nghiệp vụ. |
| HTTP A, SOAP A | Pass | Token hợp lệ | Order của B | Authorization denial; không side effect. |
| HTTP A, SOAP A | Pass | Token hợp lệ | Order của A | Thành công nếu trạng thái order cho phép. |

Test cần tách theo tầng. HTTP credentials sai không thể chứng minh WSS4J đã reject, vì interceptor có thể chưa chạy. SOAP security rejection chỉ có ý nghĩa khi request đã được phép qua HTTP filter.

## 5. Cấu hình EndpointInterceptor và WS-Security

### 5.1. EndpointInterceptor chạy trước endpoint adapter

Spring-WS gọi EndpointInterceptor.handleRequest(...) sau endpoint mapping và trước khi adapter invoke endpoint. Interceptor có thể kiểm tra Header/correlation metadata/identity; validate WS-Security; từ chối request bằng cách trả false hoặc tạo Fault; gắn verified identity vào MessageContext; và tránh lặp preprocessing trong mọi endpoint.

~~~java
public final class PartnerIdentityInterceptor
        implements EndpointInterceptor {

    @Override
    public boolean handleRequest(
            MessageContext context, Object endpoint) {
        if (!identityMatches(context.getRequest())) {
            createSafeSecurityFault(context);
            return false;
        }
        return true;
    }

    @Override
    public boolean handleResponse(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public boolean handleFault(
            MessageContext context, Object endpoint) {
        return true;
    }

    @Override
    public void afterCompletion(
            MessageContext context, Object endpoint,
            Exception exception) {
    }
}
~~~

Đây là skeleton minh họa: identityMatches và createSafeSecurityFault phải được triển khai theo SOAP version, security policy và API của project. Khi handleRequest trả false, chain dừng và endpoint không được invoke. Nếu trả true, quá trình tiếp tục.

Với exception được ném trong interceptor, response/Fault phụ thuộc exception resolver và SOAP message stack. Test cần kiểm tra behavior thực tế của cấu hình thay vì giả định mọi exception đều ánh xạ cùng một fault code.

### 5.2. Đăng ký interceptor

Trong Spring-WS, interceptor có thể được đăng ký qua endpoint mapping hoặc WsConfigurer:

~~~java
@Configuration
@EnableWs
class SoapWebServiceConfiguration implements WsConfigurer {
    private final EndpointInterceptor securityInterceptor;

    SoapWebServiceConfiguration(
            EndpointInterceptor securityInterceptor) {
        this.securityInterceptor = securityInterceptor;
    }

    @Override
    public void addInterceptors(
            List<EndpointInterceptor> interceptors) {
        interceptors.add(securityInterceptor);
    }
}
~~~

Ứng dụng thực có thể dùng Wss4jSecurityInterceptor hoặc custom interceptor. Hãy xác minh interceptor thuộc đúng mapping/endpoint group; interceptor được khai báo thành bean nhưng không đăng ký vào mapping sẽ không bảo vệ endpoint.

### 5.3. WSS4J security interceptor

Spring-WS cung cấp Wss4jSecurityInterceptor. Cấu hình inbound validation có thể yêu cầu các action như UsernameToken, Timestamp, Signature theo policy. Callback handler kiểm tra credential/token; trust material và keystore/truststore xác minh chữ ký.

Ví dụ cấu hình minh họa:

~~~java
@Bean
Wss4jSecurityInterceptor wss4jSecurityInterceptor(
        CallbackHandler partnerCallbackHandler) {
    Wss4jSecurityInterceptor interceptor =
        new Wss4jSecurityInterceptor();
    interceptor.setValidationActions(
        "UsernameToken Timestamp Signature");
    interceptor.setValidationCallbackHandler(
        partnerCallbackHandler);
    // Thiết lập trust store, signature verification và
    // timestamp/replay policy theo profile thực tế.
    return interceptor;
}
~~~

Đoạn code này không phải cấu hình hoàn chỉnh cho mọi WSS4J version hoặc Signature profile. Cần đặt đúng verification crypto, certificate alias/trust, signed parts, callback behavior và clock/replay policy theo WSDL/WS-Policy và dependency thực tế. Với UsernameToken PasswordDigest, callback phải có khả năng xác minh digest theo cách WSS4J yêu cầu; không giả định password hash một chiều là đủ cho mọi callback strategy.

**Không đánh đồng các security action:** UsernameToken xác thực token theo policy; Timestamp chống message cũ khi được validate; Signature bảo vệ integrity/authenticity của phần được ký; Encryption bảo vệ confidentiality. Chỉ bật action nào không có nghĩa các thuộc tính còn lại tự động được bảo đảm.

## 6. Chuẩn bị test fixture và business spy

### 6.1. Dùng application context gần production

Test cần load cấu hình thật hoặc test configuration tương đương production về MessageDispatcherServlet và endpoint mapping; SOAP message factory; Wss4jSecurityInterceptor và callback/trust material fixture; exception resolvers; method security nếu test authorization; business service spy/mock; database/outbox test resources nếu có side effect.

Không tạo test context chỉ có endpoint trực tiếp mà bỏ interceptor, rồi kết luận security policy production hoạt động.

### 6.2. Inject spy vào application service

Ví dụ business boundary:

~~~java
@Service
public class OrderApplicationService {
    public CancelOrderResult cancelOrder(
            CancelOrderCommand command) {
        // Kiểm tra domain state và ghi transaction.
        return performCancellation(command);
    }
}
~~~

Trong Spring Boot integration test có thể thay bean bằng spy:

~~~java
@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
class SoapSecurityIntegrationTest {
    @SpyBean
    OrderApplicationService orderApplicationService;

    @Test
    void invalidSoapSecurityDoesNotInvokeBusinessService() {
        // Gửi SOAP request qua HTTP tới server đang chạy.
        // Xác minh Fault/status theo policy.
        verifyNoInteractions(orderApplicationService);
    }
}
~~~

Annotation @SpyBean và cách khai báo có thể khác giữa các thế hệ Spring Boot; với version mới hãy dùng API test bean override tương ứng. Spy phải thay đúng bean được endpoint inject. Nếu endpoint gọi instance khác hoặc service method tự gọi nội bộ bypass proxy, assertion không chứng minh được boundary dự kiến.

### 6.3. Dùng test credentials/certificates

Tạo test-only users, passwords, keys và certificates:

- Không tái sử dụng secret production;
- Đặt fixture trong test resources hoặc test secret mechanism;
- Dùng certificate riêng cho partner A và partner B;
- Có trường hợp certificate trusted, untrusted, expired, wrong key và wrong signature;
- Kiểm soát thời gian test để timestamp expiry không phụ thuộc đồng hồ thực;
- Không ghi UsernameToken, private key hoặc password vào failure log.

## 7. Test WS-Security rejection qua HTTP server thật

### 7.1. Vì sao cần server thực?

MockWebServiceClient là công cụ server-side testing cho dispatcher, endpoints, mappings và SOAP response expectations. Nó không chạy Servlet container HTTP filter chain, không tạo TLS handshake thật và không kiểm tra reverse proxy.

Để xác minh WS-Security rejection trước business invocation, gửi request qua HTTP tới ứng dụng đang chạy (embedded server random port trong test hoặc môi trường integration). Khi đó request đi qua MessageDispatcherServlet, endpoint mappings và EndpointInterceptor thực.

### 7.2. Client test qua WebServiceTemplate

Một SOAP client integration test có thể cấu hình WebServiceTemplate trỏ tới random port:

~~~java
WebServiceTemplate template =
    createTemplateForTestServer(baseUrl + "/ws");

SoapFaultClientException fault =
    assertThrows(
        SoapFaultClientException.class,
        () -> template.marshalSendAndReceive(
            invalidUsernameTokenRequest));

assertThat(fault.getFaultCode()).isNotNull();
verifyNoInteractions(orderApplicationService);
~~~

Đây là khung minh họa. Trong thực tế, lỗi WS-Security có thể được chuyển thành SOAP Fault hoặc protocol error theo message factory, WSS4J và exception resolver. Hãy assert status/Fault contract mà ứng dụng cam kết và đồng thời xác nhận service không chạy.

Nếu client dùng HTTP Basic, cấu hình Basic credentials hợp lệ cho ca test. Khi ấy test đang kiểm tra **WS-Security rejection sau khi HTTP authentication đã pass**.

### 7.3. Test HTTP filter và SOAP interceptor riêng

Với request thiếu HTTP credentials:

~~~java
ResponseEntity<String> response = restTemplate.exchange(
    endpointUrl,
    HttpMethod.POST,
    new HttpEntity<>(soapEnvelope, soapHeadersWithoutBasic),
    String.class);

assertThat(response.getStatusCode())
    .isEqualTo(HttpStatus.UNAUTHORIZED);
verifyNoInteractions(orderApplicationService);
~~~

Với request có HTTP credentials hợp lệ nhưng thiếu UsernameToken, gửi SOAP bằng WebServiceTemplate hoặc HTTP client đã thêm Basic auth, rồi assert SOAP rejection và verifyNoInteractions(...).

Hai test này chứng minh hai tầng khác nhau. Không gộp chúng thành một test thiếu mọi credentials rồi chỉ thấy 401, vì test đó không cho biết WS-Security interceptor có được cấu hình hay không.

## 8. Chứng minh thứ tự bằng counters và probes

Một cách mạnh hơn là thêm các probe nhỏ trong test configuration:

~~~java
final class SecurityProbe {
    final AtomicInteger httpRequestPasses = new AtomicInteger();
    final AtomicInteger soapInterceptorPasses = new AtomicInteger();
    final AtomicInteger endpointInvocations = new AtomicInteger();
}
~~~

Probe có thể được cập nhật bởi test filter đặt sau authentication filter; custom endpoint interceptor đặt sau WSS4J; và test spy ở endpoint/application service.

| Request | HTTP pass | SOAP security pass | Business invocation |
| --- | ---: | ---: | ---: |
| Thiếu HTTP credentials | 0 | 0 | 0 |
| HTTP hợp lệ, thiếu UsernameToken | 1 | 0 | 0 |
| HTTP hợp lệ, token sai digest | 1 | 0 | 0 |
| HTTP hợp lệ, Timestamp hết hạn | 1 | 0 | 0 |
| HTTP hợp lệ, identity mismatch | 1 | 1* | 0 |
| HTTP hợp lệ, thiếu quyền order | 1 | 1 | 0 |
| HTTP, WS-Security và authorization hợp lệ | 1 | 1 | 1 |

*Identity mismatch có thể bị từ chối ngay trong security interceptor sau cryptographic validation hoặc trong identity binding stage. Đặt probe sau chính xác điểm kiểm tra identity để phản ánh vị trí mong muốn.

Không cần thêm probe vào production code chỉ để test. Có thể dùng test-only filter/interceptor, spy hoặc listener. Tránh thay đổi thứ tự interceptor so với production chỉ để làm test thuận tiện.

## 9. Kiểm thử UsernameToken và Timestamp

### 9.1. Ma trận UsernameToken

| Trường hợp | Kỳ vọng |
| --- | --- |
| Header thiếu UsernameToken | Reject |
| Username không tồn tại | Reject |
| Password/digest sai | Reject |
| Password type không được policy chấp nhận | Reject |
| Nonce thiếu/sai format khi policy yêu cầu | Reject |
| Created thiếu khi policy yêu cầu | Reject |
| Token hợp lệ | Pass tới bước authorization |

Mỗi ca reject phải xác minh businessInvocationCount bằng 0 và không có side effect.

### 9.2. Timestamp và cửa sổ thời gian

Timestamp validation cần xem xét Created/Expires hợp lệ; clock skew; message quá cũ; timestamp nằm trong tương lai ngoài tolerance; timestamp thiếu nếu policy bắt buộc; replay cache lưu nonce/message identifier trong thời gian yêu cầu.

Không dùng Thread.sleep(...) để test expiry. Tạo fixture timestamp tương đối với clock kiểm soát hoặc cấu hình clock/fixed time nếu stack hỗ trợ. Test phải xác định timeToLive, future time-to-live và allowed clock skew.

### 9.3. Replay

Gửi lại nguyên UsernameToken/Nonce hoặc signed message theo policy replay cache. Kỳ vọng:

1. Lần đầu hợp lệ được chấp nhận nếu mọi policy khác đạt;
2. Lần thứ hai bị từ chối theo replay policy;
3. Business invocation chỉ xảy ra theo số lần hợp lệ;
4. Replay bị từ chối không tạo thêm order transition/outbox event.

Nếu server chạy nhiều instance, replay cache phải có semantics dùng chung/được thiết kế cho topology đó. Test một instance không chứng minh replay protection phân tán hoạt động.

## 10. Kiểm thử XML Signature và Encryption

### 10.1. Signature

Tạo fixture riêng cho signature hợp lệ từ certificate trusted; signature sai vì body/header bị sửa sau khi ký; certificate không nằm trong truststore; certificate hết hạn hoặc bị revoke nếu PKI policy hỗ trợ; reference URI/signed parts không đúng policy; và thuật toán signature/digest không được phép.

**Kiểm tra business service không được gọi** cho toàn bộ fixture signature thất bại. Đừng chỉ sửa một chuỗi XML tùy ý rồi giả định test đã chứng minh chữ ký; cần thay đổi nội dung nằm trong signed part hoặc dùng key/certificate khác để sinh signature không hợp lệ.

### 10.2. Encryption

Với XML Encryption, kiểm tra encrypted key không giải mã được; certificate/private key không khớp; cipher/algorithm không được policy chấp nhận; encrypted SOAP Body sau decrypt không hợp XSD; decrypt thành công nhưng authorization từ chối resource.

Phân biệt lỗi decrypt/security validation với lỗi XML validation và business Fault. Các lớp này có thể trả những Fault/error khác nhau.

### 10.3. Trust store test fixtures

| Fixture | Server trust | Kỳ vọng |
| --- | --- | --- |
| Partner A certificate | Trusted | Signature có thể pass nếu content đúng. |
| Partner B certificate | Không trusted trong policy A | Reject |
| Expired certificate | Không hợp lệ theo thời gian | Reject nếu certificate validity được kiểm tra. |
| Wrong private key | Không tạo signature hợp lệ theo certificate A | Reject |

Không coi certificate chain hợp lệ về mặt PKI là quyền truy cập nghiệp vụ. Authorization theo partner/tenant vẫn phải chạy sau xác thực.

## 11. Kiểm tra identity binding giữa HTTP và SOAP

Trong mô hình combined authentication, có hai danh tính đã được xác thực:

- HTTP principal đến từ security context của Servlet;
- SOAP principal đến từ WS-Security validation/callback và mapping ứng dụng.

Không ánh xạ danh tính bằng cách tin header văn bản tùy ý. Hãy tạo verified identity từ security context/token đã xác thực và so sánh theo policy.

| HTTP principal | SOAP principal | Kỳ vọng |
| --- | --- | --- |
| Partner A | Partner A | Identity binding pass |
| Partner A | Partner B | Reject trước nghiệp vụ |
| Partner B | Partner A | Reject trước nghiệp vụ |
| Anonymous | Partner A | HTTP chain hoặc combined policy từ chối |
| Partner A | Không có SOAP identity | WS-Security/identity policy từ chối |

Khi binding thất bại, service invocation bằng 0. Nếu token đã được cryptographically validate nhưng identity không khớp, probe SOAP validation có thể tăng nhưng business counter vẫn bằng 0.

Một model đã xác thực có thể biểu diễn như sau:

~~~java
public record VerifiedPartnerIdentity(
        String partnerId,
        String subject,
        Set<String> authorities) {
}
~~~

Chỉ tạo object này sau khi HTTP/SOAP credential được xác minh. Đưa nó qua context đáng tin cậy hoặc truyền tường minh vào application service. Không dựng partnerId từ SOAP Body/Header chưa xác thực.

## 12. Method authorization và việc đảm bảo proxy được gọi

### 12.1. Bật method security

Spring Security không tự bật method authorization chỉ vì có starter security. Cấu hình có thể bật:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Service method được bảo vệ:

~~~java
@Service
public class OrderApplicationService {
    @PreAuthorize(
        "@orderAuthorization.canCancel(authentication, #command.orderId())")
    public CancelOrderResult cancelOrder(
            CancelOrderCommand command) {
        return performCancellation(command);
    }
}
~~~

orderAuthorization là bean kiểm tra quyền; biểu thức chỉ minh họa. Thực tế cần truyền/đọc verified partner identity và xác minh tenant/owner trên dữ liệu được lưu. Không lấy owner chỉ từ request payload.

### 12.2. Kiểm thử trước method body

Khi Spring AOP method-security proxy hoạt động, PreAuthorize được đánh giá trước method invocation. Nếu denied, interceptor ném AccessDeniedException và method body được bảo vệ không chạy.

~~~java
@Test
void partnerCannotCancelAnotherPartnersOrder() {
    assertThrows(
        AccessDeniedException.class,
        () -> orderApplicationService.cancelOrder(
            commandForAnotherPartnerOrder));

    verify(orderRepository, never())
        .markCancelled(anyString());
    verify(eventPublisher, never())
        .publishEvent(any());
}
~~~

Trong unit/integration test, phải gọi Spring-managed proxy thật thay vì new OrderApplicationService(...). Nếu tạo object trực tiếp, AOP interceptor không chạy và test không kiểm tra method security.

### 12.3. Self-invocation và class proxy

Nếu một method trong cùng bean gọi trực tiếp method khác có PreAuthorize, lời gọi nội bộ có thể bypass proxy trong proxy-based AOP. Tách phương thức được bảo vệ thành bean khác hoặc gọi qua proxy theo thiết kế rõ ràng. Test phải invoke qua đường đi thật từ SOAP endpoint tới Spring-managed bean.

Method security có thể ném AccessDeniedException không nằm trong HTTP filter request. Ứng dụng SOAP cần định nghĩa exception resolver/adapter để chuyển nó thành Fault contract an toàn nếu client cần SOAP response.

## 13. Phân biệt SOAP Fault và HTTP status

| Lớp | Response có thể nhận | Test phù hợp |
| --- | --- | --- |
| HTTP authentication | HTTP 401 + WWW-Authenticate | HTTP integration test |
| HTTP authorization | HTTP 403 | HTTP integration test |
| WS-Security validation | SOAP Security Fault hoặc protocol error theo policy | SOAP-over-HTTP integration test |
| Method authorization | Typed SOAP Fault hoặc lỗi được resolver ánh xạ | End-to-end SOAP test |
| Business validation | Business SOAP Fault | Contract test + business integration test |

Không hard-code một status/SOAP fault cho mọi dependency version. Hãy xem đúng security interceptor, SoapFaultMessageResolver, exception resolver và SOAP version. Điều bất biến quan trọng trong test âm là **business side effect không xảy ra**.

Fault không được chứa password, token, digest, private key, truststore path, stack trace hoặc lý do nội bộ có thể giúp dò hệ thống. Public fault code/message cần đủ để client xử lý mà không tiết lộ internals.

## 14. Kiểm tra custom interceptor dừng chain đúng cách

Với custom EndpointInterceptor, có thể dùng unit/integration test riêng để kiểm tra khi request thiếu metadata bắt buộc thì handleRequest trả false; interceptor tạo response/Fault đúng policy; endpoint adapter không gọi endpoint method; afterCompletion/fault handling không phát side effect sai; request hợp lệ trả true và chain tiếp tục.

Ví dụ pseudo-test:

~~~java
boolean proceed = interceptor.handleRequest(
    messageContext,
    endpoint);

assertThat(proceed).isFalse();
assertThat(messageContext.hasResponse()).isTrue();
verifyNoInteractions(orderApplicationService);
~~~

Đây là test trực tiếp interceptor, không chứng minh interceptor đã được đăng ký trong endpoint mapping. Cần ít nhất một integration test gửi SOAP request qua MockWebServiceClient hoặc HTTP server để xác minh wiring.

Đối với WSS4J interceptor, không mô phỏng cryptographic validation bằng cách gọi method private. Hãy gửi SOAP message có token/signature thật theo fixture test, để WSS4J chạy toàn bộ validation pipeline.

## 15. Test qua MockWebServiceClient và HTTP server: dùng đúng công cụ

### 15.1. MockWebServiceClient

MockWebServiceClient kiểm thử MessageDispatcher, endpoint mappings, endpoint interceptors và response trong server-side test:

~~~java
mockWebServiceClient
    .sendRequest(withPayload(requestPayload))
    .andExpect(serverOrReceiverFault());
~~~

Nó phù hợp để xác minh interceptor được wire vào dispatcher; request sai security tạo Fault; endpoint/business service không được gọi; response/Fault theo SOAP contract. Nhưng nó không kiểm tra Servlet filter chain hoặc HTTP TLS thật.

### 15.2. Embedded HTTP server

Dùng Spring Boot RANDOM_PORT, TestRestTemplate, WebTestClient hoặc HTTP client phù hợp để gửi SOAP Envelope tới endpoint HTTP đang chạy. Đây là lựa chọn cho HTTP Basic/Bearer filters; HTTP 401/403 và challenge; MessageDispatcherServlet mapping; WS-Security interceptor trên SOAP message thực; TLS/mTLS nếu test environment cấu hình SSL; và SOAP Fault qua HTTP response thực.

### 15.3. Integration test xuyên các tầng

Bộ test đầy đủ nên có:

1. **HTTP filter test:** request thiếu/sai HTTP credential bị chặn trước SOAP dispatcher.
2. **SOAP security test:** HTTP credential hợp lệ nhưng WS-Security token/signature sai bị chặn trước endpoint/business service.
3. **Authorization test:** HTTP và SOAP credentials hợp lệ nhưng caller không có quyền tài nguyên vẫn bị chặn trước service method body/side effect.
4. **Success test:** mọi lớp đều đạt, nghiệp vụ chỉ chạy đúng một lần.

Một mock test pass là bằng chứng cho dispatcher behavior trong test context; một HTTP test pass là bằng chứng cho đường đi tới servlet trong embedded server. Mỗi test có phạm vi chứng minh riêng.

## 16. Ma trận kiểm thử từ chối và không thực thi nghiệp vụ

| ID | HTTP auth | WS-Security | Authorization | Kết quả dự kiến | Business calls |
| --- | --- | --- | --- | --- | ---: |
| SEC-01 | Missing | Không xét | Không xét | HTTP 401 | 0 |
| SEC-02 | Invalid | Không xét | Không xét | HTTP 401 | 0 |
| SEC-03 | Valid | Missing token | Không xét | SOAP security reject | 0 |
| SEC-04 | Valid | Wrong password/digest | Không xét | SOAP security reject | 0 |
| SEC-05 | Valid | Expired Timestamp | Không xét | SOAP security reject | 0 |
| SEC-06 | Valid | Invalid Signature | Không xét | SOAP security reject | 0 |
| SEC-07 | Valid A | Valid B | Identity mismatch | Identity rejection | 0 |
| SEC-08 | Valid A | Valid A | No permission for order | Authorization denial | 0 |
| SEC-09 | Valid A | Valid A | Permission granted | SOAP success | 1 |
| SEC-10 | Valid A | Replayed token | Previously seen nonce | Replay rejection | 0 on replay attempt |
| SEC-11 | Valid | Malformed SOAP/XML | Không xét | Parser/protocol rejection | 0 |
| SEC-12 | Valid | Valid | Valid nhưng business state conflict | Business Fault | 1 business entry |

SEC-12 giúp phân biệt **security rejection trước nghiệp vụ** với **business rejection sau khi nghiệp vụ đã chạy**. Không phải mọi Fault đều đồng nghĩa business method chưa được gọi.

## 17. Kiểm tra concurrency và retry

### 17.1. Hai request cùng một token

Nếu replay policy yêu cầu nonce chỉ sử dụng một lần, gửi cùng token đồng thời từ hai client. Kỳ vọng chỉ một request được xác thực thành công hoặc policy từ chối cả hai nếu có race/uncertain processing; tuyệt đối không để cả hai cùng thực hiện side effect.

Test dùng barrier/latch để khởi động đồng thời, không dùng sleep tùy tiện. Sau khi hoàn tất, kiểm tra kết quả từng request; business invocation count; database transition count; outbox/event count; replay cache state nếu test adapter cho phép quan sát.

### 17.2. Client retry sau timeout

Một client có thể timeout sau khi server đã commit. Retry không được làm operation chạy hai lần. Đây là vấn đề idempotency và transaction, khác replay token:

- Replay security nhận diện việc tái dùng message/token;
- Idempotency nghiệp vụ nhận diện cùng operation/request key;
- Hai cơ chế bổ sung nhau.

Test cần kiểm tra request đã commit rồi mất response, sau đó client retry với correlation/idempotency key. Kết quả trả lại có thể là receipt/result cũ, nhưng business effect chỉ được ghi một lần.

### 17.3. Nhiều instance

Với nhiều replica, replay cache phải có semantics đồng bộ phù hợp; clock skew/certificate rotation cần nhất quán; authorization data/tenant cache không stale theo cách mở quyền; side effects được bảo vệ bằng unique constraints/idempotency key; test gửi hai lần qua hai instance nếu hạ tầng hỗ trợ.

Một test trên một JVM không chứng minh distributed replay protection hoặc cluster-wide idempotency.

## 18. Các lỗi test bảo mật thường gặp

| Lỗi | Vì sao chưa đủ | Cách sửa |
| --- | --- | --- |
| Chỉ assert HTTP 401 | Request có thể chưa tới WS-Security. | Tách test HTTP filter và SOAP interceptor. |
| Chỉ assert SOAP Fault | Endpoint/service có thể đã chạy trước khi Fault được tạo. | Verify business service không được gọi và kiểm tra side effect. |
| Dùng MockWebServiceClient cho HTTP Basic | Tool không chạy Servlet filter chain. | Dùng embedded HTTP server test. |
| Dùng object service tạo bằng new | Không đi qua Spring proxy/method security. | Gọi bean Spring-managed thật. |
| Chỉ kiểm tra @PreAuthorize bằng reflection | Không xác minh AOP interceptor thực thi. | Invoke qua proxy trong context. |
| Chỉ kiểm tra Header Security tồn tại | Không xác minh token/signature hợp lệ. | Gửi token/signature fixture thật qua WSS4J. |
| Test token sai nhưng HTTP auth cũng sai | Request bị chặn ở HTTP layer trước WSS4J. | Dùng HTTP credential hợp lệ trong WS-Security negative test. |
| Không kiểm tra DB/outbox | Service có thể tạo side effect qua collaborator khác. | Assert domain state, outbox và outbound interactions. |
| Dựa vào rollback cuối test | Có thể che commit/side effect sai. | Quan sát trạng thái trong transaction/test DB đúng cách. |
| Dùng timestamp hard-coded | Kết quả thay đổi theo ngày giờ chạy test. | Dùng clock/timestamp fixture tương đối và tolerance rõ. |
| Replay test tuần tự một instance | Không chứng minh race/shared cache trong cluster. | Test concurrent và multi-instance khi cần. |
| Assert exception message nội bộ | Dễ vỡ theo version và có thể lộ secret. | Assert public fault category/code/status an toàn. |

## 19. Checklist trước khi hoàn tất security integration test

### HTTP layer

- [ ] Test request thiếu/sai HTTP credentials qua Servlet container thật.
- [ ] Assert 401/403 và challenge/header theo policy.
- [ ] Chứng minh SOAP dispatcher/interceptor chưa chạy khi HTTP filter chặn.
- [ ] Chứng minh business service không được gọi.

### SOAP message layer

- [ ] Test HTTP auth hợp lệ nhưng WS-Security Header thiếu.
- [ ] Test UsernameToken sai password/digest hoặc profile.
- [ ] Test Timestamp hết hạn/tương lai và replay policy.
- [ ] Test Signature sai, certificate không trust và signed parts không đúng policy.
- [ ] Xác minh endpoint method/application service chưa chạy khi SOAP security từ chối.
- [ ] Kiểm tra Fault/status an toàn, không lộ nội bộ.

### Authorization và business boundary

- [ ] Test HTTP/SOAP identity mismatch nếu mô hình combined identity yêu cầu.
- [ ] Test caller xác thực hợp lệ nhưng không có quyền tài nguyên.
- [ ] Xác minh Spring-managed proxy/method security thực sự chạy.
- [ ] Assert không thay đổi database, outbox, event hoặc outbound calls khi bị từ chối.
- [ ] Test positive case chạy nghiệp vụ đúng một lần.

### Reliability và topology

- [ ] Test replay và concurrent duplicate.
- [ ] Test retry sau timeout với idempotency key.
- [ ] Test shared replay cache/multi-instance khi deployment có nhiều replica.
- [ ] Test certificate expiry/rotation và clock skew theo policy.
- [ ] Có test riêng cho HTTP, SOAP dispatcher và application authorization.

## 20. Câu hỏi tự kiểm tra

1. Vì sao HTTP 401 không chứng minh WSS4J interceptor đã reject?
2. EndpointInterceptor.handleRequest(...) chạy trước hay sau endpoint adapter?
3. Khi custom interceptor trả false, điều gì phải xảy ra với endpoint invocation?
4. Vì sao một test SOAP Fault phải verify business service không được gọi?
5. verifyNoInteractions(...) phù hợp khi nào và có thể gây false failure khi nào?
6. Làm sao phân biệt WS-Security validation rejection với authorization denial?
7. Vì sao phải dùng HTTP credentials hợp lệ trong test UsernameToken sai?
8. EnableMethodSecurity bật chức năng nào và vì sao phải gọi qua Spring proxy?
9. Self-invocation ảnh hưởng thế nào tới PreAuthorize?
10. Vì sao UsernameToken, Timestamp, Signature và Encryption bảo vệ các thuộc tính khác nhau?
11. Test replay phải chứng minh điều gì ngoài SOAP Fault?
12. Vì sao MockWebServiceClient không đủ cho HTTP filter/TLS integration?
13. Làm sao chứng minh identity HTTP và SOAP đã được binding đúng?
14. Vì sao response Fault có thể được tạo sau khi endpoint method đã chạy?
15. Làm thế nào kiểm tra không có outbox event hoặc outbound side effect?
16. Retry sau timeout khác replay token như thế nào?
17. Một test trên một JVM có chứng minh replay cache dùng chung giữa nhiều instance không?
18. Vì sao không nên assert raw exception message hoặc log SOAP Security Header?

## 21. Bài tập thực hành

**Bối cảnh:** Một Spring-WS service có operation CancelOrder. Để gọi thành công, partner phải xác thực qua HTTP Basic và WS-Security UsernameToken; caller chỉ được hủy order của tenant mình. Hãy tạo bộ integration tests chứng minh request sai bảo mật bị chặn trước business processing.

### Phần A — Instrumentation và test setup

1. Tạo test application context có MessageDispatcherServlet, endpoint, endpoint mapping, WSS4J interceptor và application service.
2. Dùng test HTTP server với random port.
3. Gắn spy vào application service, repository, event publisher/outbox.
4. Tạo test partner A/B và SOAP credentials/certificates độc lập.
5. Thêm test-only probes đếm HTTP pass, SOAP security pass và business method entry.

### Phần B — HTTP rejection

6. Gửi request thiếu HTTP Basic; assert 401/challenge đúng policy.
7. Gửi request có password HTTP sai; assert 401.
8. Assert SOAP security interceptor chưa chạy và business invocation bằng 0.

### Phần C — WS-Security rejection

9. Gửi HTTP Basic hợp lệ nhưng không có UsernameToken; assert security rejection.
10. Gửi UsernameToken sai password/digest; assert reject.
11. Gửi Timestamp expired hoặc future ngoài tolerance; assert reject.
12. Gửi Signature bị sửa, certificate không trusted hoặc signed parts sai policy; assert reject.
13. Gửi token hợp lệ hai lần; kiểm tra replay bị chặn theo policy.
14. Với mọi ca từ chối, assert service, repository mutation, outbox và event publisher không tạo side effect.

### Phần D — Identity và authorization

15. HTTP A + SOAP B; assert identity binding reject trước business.
16. HTTP A + SOAP A nhưng order của B; assert authorization denial và không cập nhật order.
17. HTTP A + SOAP A và order của A; assert success và business invocation đúng một lần.
18. Kiểm tra service gọi qua Spring proxy có PreAuthorize, không gọi trực tiếp object tự tạo.

### Phần E — Recovery và báo cáo

19. Chạy hai request cùng replay token đồng thời; xác minh không có hai business effects.
20. Giả lập server commit nhưng client timeout, sau đó retry cùng idempotency key; xác minh side effect chỉ một lần.
21. Chạy một test qua MockWebServiceClient cho interceptor wiring và một test qua embedded HTTP server cho filter + SOAP pipeline.
22. Ghi bảng kết quả gồm request case, HTTP result, SOAP Fault, probe counters, business calls, DB mutation, outbox events và replay outcome.

**Tiêu chí đạt:** mọi request thiếu/sai credential, timestamp, signature, identity hoặc authorization đều bị từ chối ở đúng tầng và **business service không được thực thi**; không tạo side effect. Request hợp lệ chạy đúng một lần. Bộ test phân biệt rõ HTTP rejection, SOAP security rejection, method authorization và business Fault.

## 22. Tài liệu tham khảo chính thức

- [Spring-WS 4.1.4 Reference — Testing](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): MockWebServiceClient và phạm vi server-side testing.
- [Spring-WS 4.1.x API — EndpointInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/server/EndpointInterceptor.html): vị trí handleRequest, handleResponse, handleFault và việc trả false để dừng endpoint invocation chain.
- [Spring-WS 4.1.x API — AbstractWsSecurityInterceptor](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/security/AbstractWsSecurityInterceptor.html): WS-Security interceptor dùng phía server qua endpoint mapping và phía client qua WebServiceTemplate.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): EnableMethodSecurity, PreAuthorize, before-method authorization và Spring AOP proxy behavior.
- [OASIS WS-Security UsernameToken Profile](https://docs.oasis-open.org/wss-m/wss/v1.1.1/os/wss-UsernameTokenProfile-v1.1.1-os.html): UsernameToken, PasswordDigest, Nonce, Created và security considerations.

Các API Spring-WS được dẫn ở release 4.1.x/4.1.4. Dự án sử dụng Spring-WS, WSS4J, Spring Security hoặc Spring Boot version khác cần đối chiếu đúng dependency/API và chạy integration test trên stack thực tế.

## 23. Tổng kết

**Để chứng minh request sai bảo mật bị từ chối trước nghiệp vụ, test phải xác minh cả kết quả từ chối lẫn việc business service và side effects không xảy ra.** HTTP filter chặn trước SOAP dispatcher; EndpointInterceptor/WSS4J kiểm tra SOAP message trước endpoint adapter; method security kiểm tra authorization trước method body được bảo vệ. Ba tầng này cần test riêng và có các test end-to-end kết hợp.

Với Spring-WS, MockWebServiceClient giúp kiểm tra interceptor và dispatcher, còn embedded HTTP server test chứng minh Servlet filter chain và SOAP pipeline cùng hoạt động. Kết hợp spy/counter, database/outbox assertions, token/signature/replay fixtures và success case để tránh kết luận sai từ một HTTP status hoặc SOAP Fault đơn lẻ.

**Ghi nhớ:** Fault chỉ cho biết server đã trả một dạng lỗi. Bằng chứng security rejection đầy đủ phải cho thấy request bị dừng đúng ranh giới, business code chưa chạy và không có side effect.
