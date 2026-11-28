# Lát cắt kiểm thử Spring Boot và cấu hình theo phiên bản đang dùng

Ứng dụng SOAP xây dựng bằng **Spring Boot và Spring Web Services (Spring-WS)** có nhiều lớp cần kiểm tra: endpoint mapping, JAXB, XSD validation, interceptor, SOAP Fault, HTTP security, servlet, TLS và đôi khi JMS broker. Khởi động toàn bộ hệ thống cho mọi test khiến vòng phản hồi chậm; thu nhỏ context quá mức lại có thể bỏ sót cấu hình production.

**Test slice** tạo Spring test context tập trung vào một phần chức năng. Spring Boot cung cấp các slice cho một số công nghệ; Spring-WS cung cấp công cụ message testing như **MockWebServiceClient**. Hai loại công cụ này có mục tiêu khác nhau. Không nên giả định mọi project có annotation slice auto-config riêng cho SOAP server hoặc cấu hình giống nhau qua mọi major version.

Bài thuộc chương **Kiểm thử máy chủ** của module **SPRING_WEB_SERVICES**. Ta chọn giữa unit test, focused context, Boot test slice, Spring-WS message test và integration test theo transport. Đồng thời, bài giải thích cách khóa dependency/version, profiles, properties, JAXB namespace và security configuration để test phản ánh đúng hệ thống đang deploy.

> **Nguyên tắc:** chọn test theo ranh giới cần chứng minh. Kiểm SOAP endpoint, HTTP Basic filter và TLS handshake là ba việc khác nhau. Một test slice hẹp không chứng minh được tất cả.

## 1. Test slice giải quyết vấn đề gì?

| Mục tiêu | Phạm vi phù hợp |
| --- | --- |
| Business logic thuần Java | Unit test |
| SOAP payload tới endpoint | MockWebServiceClient với endpoint/interceptor cần thiết |
| JAXB/XML serialization | Marshaller và schema test |
| HTTP filter/security chain | HTTP request test qua filter |
| Wiring SOAP của ứng dụng | Focused context hoặc @SpringBootTest |
| HTTP servlet/path/filter | Random-port integration test |
| TLS/mTLS | HTTPS test server/certificate fixtures |
| JMS selector/redelivery/DLQ | Broker integration test |

Slice giúp giảm số bean, thời gian khởi tạo và phạm vi lỗi. Tuy nhiên, context nhỏ có thể khác production. Ví dụ test import endpoint nhưng quên import WS-Security interceptor khiến test pass dù server thật không có policy đó.

## 2. Phân biệt các dạng test context

1. **Boot-provided slice:** annotation có sẵn cho công nghệ cụ thể, ví dụ @WebMvcTest, @DataJpaTest hoặc @JsonTest tùy release.
2. **Framework test utility:** công cụ Spring-WS như MockWebServiceClient, tập trung vào SOAP message processing.
3. **Custom focused context:** test tự chọn bean bằng @ContextConfiguration, @Import, @TestConfiguration hoặc @ImportAutoConfiguration.

Với SOAP server, cần xác minh Spring-WS version cung cấp những test utilities nào. MockWebServiceClient có thể đưa SOAP message qua message processing infrastructure, nhưng **không tự khởi động HTTP servlet container, TLS handshake hay JMS broker**.

| Cách test | Có thể chứng minh | Không tự chứng minh |
| --- | --- | --- |
| Unit test | Logic class | Spring bean wiring |
| Focused context | Wiring của bean đã import | Bean bị bỏ ngoài context |
| MockWebServiceClient | Endpoint mapping, interceptor trong chain, payload/Fault | HTTP/TLS transport |
| Boot slice | Auto-config của subsystem được hỗ trợ | SOAP dispatcher nếu ngoài slice |
| @SpringBootTest | Application context và wiring | Network/broker nếu không khởi động |
| Random-port integration | HTTP server, path, filter | Production proxy/certificate nếu fixture khác |
| Broker integration | Destination, selector, redelivery theo provider | Broker khác provider |

## 3. Phiên bản quyết định API và auto-configuration

Trước khi viết test, xác định Spring Boot major/minor, BOM, Spring Framework, Spring-WS, Spring Security, JAXB API/runtime, XJC, servlet container/API, JMS API/provider và JDK.

| Nhóm API | Stack cũ thường gặp | Stack Jakarta mới thường gặp |
| --- | --- | --- |
| Servlet | javax.servlet.* | jakarta.servlet.* |
| JMS | javax.jms.* | jakarta.jms.* |
| JAXB | javax.xml.bind.* | jakarta.xml.bind.* |

Đây là xu hướng namespace, không phải compatibility matrix đầy đủ. Dùng dependency management của Boot BOM; không tự override Spring Framework/Security để sửa lỗi compile. Kiểm dependency tree, generated JAXB imports, test annotations và class có trong classpath.

## 4. @SpringBootTest và focused context

@SpringBootTest phù hợp khi cần xác minh component scanning, Boot auto-configuration, endpoint registration, properties và wiring nhiều bean. Nhưng test phải có assertion; chỉ khởi tạo context thành công không chứng minh SOAP message đã được xử lý đúng.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OrdersContextTest {
    @Autowired
    private OrdersEndpoint ordersEndpoint;

    @Test
    void endpointBeanIsRegistered() {
        assertThat(ordersEndpoint).isNotNull();
    }
}
```

Ví dụ chỉ kiểm tra bean; class endpoint cần tồn tại trong application. Test chưa kiểm payload, servlet, security filter hay transport. Focused context khởi tạo nhanh hơn nhưng cần import đúng configuration; giữ wiring test rộng hơn để phát hiện bean/interceptor bị bỏ sót.

## 5. MockWebServiceClient cho SOAP message processing

Spring-WS test module cung cấp MockWebServiceClient để gửi message vào message processing infrastructure và kiểm response. Test có thể xác minh payload root, mapping, interceptor, response XML và SOAP Fault.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;
import static org.springframework.ws.test.server.ResponseMatchers.payload;

class OrdersMessageTest {
    @Autowired
    private ApplicationContext applicationContext;
    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(applicationContext);
    }

    @Test
    void mapsGetOrderPayload() {
        StringSource request = new StringSource(
            "<ord:GetOrderRequest xmlns:ord='https://example.com/orders/v1'>" +
            "<ord:orderId>42</ord:orderId>" +
            "</ord:GetOrderRequest>");
        StringSource expected = new StringSource(
            "<ord:GetOrderResponse xmlns:ord='https://example.com/orders/v1'>" +
            "<ord:orderId>42</ord:orderId>" +
            "<ord:status>CONFIRMED</ord:status>" +
            "</ord:GetOrderResponse>");

        client.sendRequest(withPayload(request))
              .andExpect(noFault())
              .andExpect(payload(expected));
    }
}
```

Đây là API style minh họa; imports và matcher overload cần xác minh theo Spring-WS version. Context phải có endpoint mapping, endpoint adapter, endpoint và interceptor cần test.

Test này có thể xác minh request QName được định tuyến, endpoint tạo response, Fault có/không xuất hiện và interceptor trong chain chạy. Nó không tự kiểm tra HTTP Basic, servlet mapping, TLS/mTLS, public WSDL URL hoặc broker JMS.

## 6. Focused SOAP test context

Có thể tạo cấu hình tập trung:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.ws.config.annotation.EnableWs;

@Configuration
@EnableWs
@Import({
    OrdersEndpoint.class,
    OrdersSoapConfiguration.class,
    OrdersTestDependencies.class
})
class OrdersSoapTestConfiguration {
}
```

Các configuration/dependency classes là thành phần ứng dụng. Kiểm endpoint bean, mapping namespace/localPart/action, endpoint adapter, marshaller, schema, interceptor và Fault resolver. Mock business dependency nếu cần, nhưng giữ mapping/marshaller/interceptor thật khi kiểm SOAP contract/security.

## 7. @WebMvcTest không tự đồng nghĩa SOAP test

@WebMvcTest tập trung Spring MVC controllers và một phần MVC infrastructure. Nó phù hợp cho REST/MVC controllers cạnh SOAP servlet, nhưng không nên mặc định nó khởi tạo Spring-WS MessageDispatcherServlet và đăng ký toàn bộ SOAP endpoints.

Nếu SOAP endpoint phục vụ qua servlet riêng, MVC slice có thể không nạp mapping, adapter, servlet mapping hoặc interceptor. Dùng MockWebServiceClient/focused SOAP context cho message processing và HTTP integration cho servlet behavior.

**Không kết luận SOAP server đã được test chỉ vì @WebMvcTest pass.**

## 8. Mock business dependency, giữ thật contract plumbing

Ví dụ cung cấp service stub:

```java
import org.mockito.Mockito;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration
class OrdersStubConfiguration {
    @Bean
    @Primary
    OrderQueryService orderQueryService() {
        OrderQueryService stub = Mockito.mock(OrderQueryService.class);
        Mockito.when(stub.findOrder(42L))
               .thenReturn(new OrderView(42L, "CONFIRMED"));
        return stub;
    }
}
```

Import test configuration chỉ trong test cần dùng. Không mock EndpointInterceptor khi cần chứng minh security validation; không mock marshaller khi kiểm schema; không để @Primary stub thay bean trong integration test toàn ứng dụng.

## 9. JAXB và XSD validation

XML well-formed không đồng nghĩa payload hợp lệ theo XSD. Test nên gồm payload đúng schema/namespace; thiếu element bắt buộc; sai QName; sai thứ tự xs:sequence; giá trị vượt pattern/length/range; xsi:nil trên element không nillable; optional field vắng mặt và decimal/date/time/binary mapping.

```java
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

class OrdersJaxbTest {
    @Test
    void marshalsExpectedNamespace() throws Exception {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.v1");
        marshaller.afterPropertiesSet();

        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(42L);
        StringWriter output = new StringWriter();
        marshaller.marshal(request, new StreamResult(output));

        org.assertj.core.api.Assertions.assertThat(output.toString())
            .contains("https://example.com/orders/v1");
    }
}
```

Package/class phải thay theo XJC output. Trong application, để Spring quản lý lifecycle marshaller bean. Muốn kiểm schema validation, cấu hình schema resource và validation handler theo API version rồi gửi payload sai để khẳng định bị reject. Dùng XML-aware assertion để so QName; substring chỉ là smoke check.

## 10. Endpoint mapping: PayloadRoot, SOAPAction và WS-Addressing

| Cơ chế | Điều cần kiểm |
| --- | --- |
| @PayloadRoot | Namespace URI và localPart |
| @SoapAction | SOAPAction URI, binding và SOAP version |
| @Action | WS-Addressing Action URI |
| Custom mapping | Priority, fallback, supported message và route coverage |

Không test một request nếu production chấp nhận nhiều route. SOAPAction alias hoặc legacy mapping có thể gọi cùng business service nhưng thiếu interceptor/security chain. Test route được hỗ trợ và route không hợp lệ.

## 11. EndpointInterceptor và SOAP Fault

Kiểm qua message processing chain:
- Request hợp lệ đi qua interceptor.
- Thiếu token/header bắt buộc bị chặn.
- Interceptor reject/throw theo contract.
- Exception resolver tạo Fault code/detail đúng.
- Fault không lộ token, password hoặc stack trace.
- Endpoint method không chạy khi security validation fail.
- Outbound interceptor xử lý response/Fault theo policy.

```java
// Pseudocode assertion for the test harness
client.sendRequest(withPayload(invalidSoap))
      .andExpect(expectedSecurityFault());
verify(orderService, never()).cancelOrder(...);
```

Matcher cụ thể tùy SOAP version và test API. Cần assert business side effect không xảy ra, không chỉ kiểm một method interceptor.

## 12. HTTP Security là lớp test riêng

Nếu SOAP endpoint được bảo vệ bằng Spring Security SecurityFilterChain, cần gửi HTTP request qua servlet filter chain. MockWebServiceClient không chạy HTTP Basic filter.

Các case:
- Không Authorization → HTTP 401 khi policy yêu cầu Basic.
- Basic sai → 401 và endpoint không chạy.
- Basic đúng → request tới SOAP dispatcher.
- Authenticated nhưng thiếu authority → 403/access-denied policy.
- Legacy URL/method không match chain → bị từ chối.
- CSRF được đánh giá nếu browser/session credentials áp dụng.
- Header pre-auth giả không tạo principal.

**HTTP 401 có thể không chứa SOAP Envelope.** Không dùng SOAP Fault matcher cho response bị filter từ chối trước parser.

## 13. HTTP integration với random port

Khi cần chứng minh servlet, URL và filter chain cùng hoạt động, có thể khởi động server random port:

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class OrdersHttpIntegrationTest {
    // Send SOAP Envelope to the actual servlet path with an HTTP test client.
}
```

Test cần Content-Type đúng SOAP 1.1/1.2, SOAPAction/WS-A nếu cần, Basic credentials, parse HTTP status riêng SOAP response và kiểm side effect. Random-port kiểm server trong process test nhưng chưa chứng minh production load balancer, TLS certificate hay reverse proxy.

## 14. @Import, @TestConfiguration và auto-configuration

| Cơ chế | Dùng khi | Cẩn trọng |
| --- | --- | --- |
| @Import | Bổ sung configuration/component | Có thể làm context rộng |
| @TestConfiguration | Cung cấp test bean/stub | Import đúng scope |
| @ImportAutoConfiguration | Nạp auto-config cụ thể của Boot | Class/condition thay đổi theo version |
| @ActiveProfiles | Chọn profile test | Không bỏ policy production cần kiểm |
| @TestPropertySource | Override properties | Có thể che lỗi production |
| @DynamicPropertySource | Cấp port/URI runtime của container | Quản lifecycle |

Không import mọi auto-configuration chỉ để test khởi động. Xác định bean nào thiếu và vì sao slice không tạo nó.

## 15. Profiles, properties và conditional beans

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties = {
    "orders.contract.validation-enabled=true",
    "spring.webservices.path=/ws"
})
class OrdersConfigurationTest {
}
```

Tên property chỉ minh họa; thay bằng key thật của project. Profile test không nên vô tình tắt schema validation hoặc security interceptor. Dùng test credentials/certificate fixtures, không lấy secret production. Test default config khi cần bảo đảm ứng dụng fail fast nếu thiếu property bắt buộc.

Conditional bean phụ thuộc classpath, property hoặc bean khác; focused context có thể làm condition khác production. Kiểm condition report khi auto-config không tạo bean. ApplicationContextRunner hữu ích khi phát triển custom Boot auto-configuration, với API theo version.

## 16. Spring Security version và authentication tests

Spring Security DSL/matcher/test support thay đổi giữa các thế hệ. Dùng BOM đúng version và test behavior qua request thực.

- @WithMockUser thiết lập test principal cho authorization; **không chứng minh HTTP Basic verifier**.
- HTTP Basic integration gửi Authorization credentials và xác minh filter/provider thực.
- Method security cần enable và gọi qua proxy phù hợp.
- SecurityContext không rò giữa requests.
- SOAP username chỉ được map principal sau khi WSS4J verify nếu có bridge.
- Fault không lộ credential/secret.

Kiểm namespace servlet và spring-security-test khớp major version.

## 17. WSDL publishing và schema imports

WSDL cần test riêng với SOAP message:
- GET đúng URL sau servlet mapping.
- Root namespace và XML encoding.
- Service/port/binding/operation/SOAPAction.
- Resolve XSD imports/includes và policy references.
- Relative URI hoạt động dưới context path/proxy.
- soap:address không trỏ localhost/internal host.
- Snapshot/checksum khớp contract artifact.
- Catalog/offline resolution trong codegen.

MockWebServiceClient không chứng minh WSDL public URL hoạt động. Dùng HTTP GET integration test.

## 18. XML security và parser hardening

Parser chạy trước endpoint. Kiểm:
- DTD/external entity bị chặn theo policy.
- Entity expansion không gây resource exhaustion.
- Payload size/depth có giới hạn.
- xsi:schemaLocation không khiến server tải schema tùy ý.
- Malformed namespace/schema bị từ chối.
- Attachment/MTOM có size limits nếu bật.

Test harness phải dùng cùng message factory/parser config production. Test parser độc lập với config khác không chứng minh runtime servlet an toàn.

## 19. WS-Security và certificate tests

Dùng SOAP fixtures được tạo bởi thư viện và certificate test; không chỉ nối XML string thủ công. Kiểm UsernameToken PasswordText/Digest, Nonce/Created/Timestamp, replay, certificate chain/key usage/trust, XML Signature đúng SOAP parts, signature wrapping defense, encryption/decryption nếu dùng, Fault khi token/chữ ký sai, endpoint không chạy khi validation fail và log không chứa secret.

MockWebServiceClient có thể test interceptor message security khi interceptor có trong context, nhưng không thực hiện TLS handshake. TLS trust/hostname/mTLS cần HTTPS integration test riêng.

## 20. JMS transport tests

Với SOAP-over-JMS, mock context có thể kiểm correlation logic nhưng không chứng minh broker semantics. Broker integration test kiểm request destination, JMSReplyTo, correlation pattern A/B, temporary destination lifecycle, selector, redelivery/ack/transaction, TTL/DLQ, broker authentication/ACL, failover/reconnect và concurrent requests.

Nếu dùng Testcontainers/broker test instance, pin provider/image version. Kiểm JMS namespace javax.jms/jakarta.jms đồng bộ với application và adapter.

## 21. Ma trận lựa chọn test theo mục tiêu

| Mục tiêu | Test chính | Bổ sung |
| --- | --- | --- |
| Business logic | Unit test | Persistence integration |
| JAXB/XSD | Marshaller/schema test | Old-client fixture |
| SOAP payload routing | MockWebServiceClient | HTTP servlet test |
| SOAP Fault | Message test | SOAP 1.1/1.2 wire test |
| Endpoint interceptor | Message test với chain thật | Wiring test |
| HTTP Basic | HTTP/security filter test | Random-port nếu servlet riêng |
| TLS/mTLS | HTTPS integration | Certificate rotation/negative chain |
| WSDL endpoint | HTTP GET integration | Proxy/environment snapshot |
| JMS correlation | Unit/message test | Broker integration |
| App wiring | @SpringBootTest | External infrastructure |
| Cross-stack | Consumer/provider integration | Java/.NET fixtures |

## 22. Ma trận 40 ca kiểm thử server testing

| Mã | Tình huống | Kết quả cần xác minh |
| --- | --- | --- |
| S01 | Unit service input hợp lệ | Domain result đúng |
| S02 | Business validation | Domain error có cấu trúc |
| S03 | Focused context import endpoint | Endpoint bean tạo được |
| S04 | Context thiếu endpoint mapping | Test fail rõ |
| S05 | MockWebServiceClient QName đúng | Endpoint được chọn |
| S06 | Payload namespace sai | Không route nhầm |
| S07 | Request XSD hợp lệ | Unmarshal/process thành công |
| S08 | Thiếu required element | Validation từ chối |
| S09 | Sequence order sai | Schema reject |
| S10 | xsi:nil ở element không nillable | Reject |
| S11 | JAXB marshal namespace | QName đúng |
| S12 | JAXB restriction invalid | Validator báo lỗi |
| S13 | SOAPAction đúng | Mapping đúng |
| S14 | SOAPAction sai | Không route nhầm |
| S15 | WS-Addressing Action đúng | Mapping đúng khi bật |
| S16 | Unknown Action | Fault/route failure đúng policy |
| S17 | Endpoint interceptor đăng ký | Interceptor chạy |
| S18 | Interceptor reject request | Business method không gọi |
| S19 | SOAP exception | Fault code/detail đúng |
| S20 | Fault serialization | Không lộ stack/secret |
| S21 | Basic thiếu credential | HTTP 401 trước SOAP |
| S22 | Basic sai | 401, không side effect |
| S23 | Basic đúng | SOAP dispatcher nhận request |
| S24 | Thiếu authority | 403/access denied |
| S25 | Legacy servlet path | Không bypass security |
| S26 | Hai request riêng | SecurityContext không rò |
| S27 | GET WSDL public URL | WSDL XML hợp lệ |
| S28 | XSD import location sai | HTTP contract test phát hiện |
| S29 | soap:address internal host | Release check phát hiện |
| S30 | WS-Security token hợp lệ | Message validation pass |
| S31 | UsernameToken/signature sai | Reject trước business |
| S32 | XML external entity | Parser chặn |
| S33 | Payload quá lớn | Size limit áp dụng |
| S34 | TLS server cert không trust | Handshake fail |
| S35 | Hostname certificate mismatch | Client từ chối |
| S36 | mTLS cert thiếu/sai | TLS peer policy từ chối |
| S37 | JMS correlation đúng | Request/reply match |
| S38 | JMS redelivery sau rollback | Idempotency/recovery đúng |
| S39 | Boot dependency/namespace mismatch | Build/test fail rõ |
| S40 | Full context test profile | Wiring/properties đúng |

## 23. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Cách sửa |
| --- | --- | --- |
| Mọi test dùng @SpringBootTest | Chậm, phụ thuộc nhiều hạ tầng | Unit/focused/message tests |
| Chỉ dùng MockWebServiceClient | Bỏ HTTP filter/TLS/WSDL servlet | Thêm transport tests |
| Context thiếu interceptor | Pass giả, production khác | Import chain và wiring test |
| Mock toàn bộ Spring-WS | Không kiểm contract plumbing | Giữ mapping/marshaller/interceptor thật |
| Profile test tắt validation | Che lỗi production | Giữ policy cần kiểm |
| Copy annotation từ Boot khác | API/auto-config lệch | Pin BOM và verify dependency |
| @WithMockUser chứng minh Basic | Không chạy credential verification | HTTP Basic integration |
| Parse Fault bằng substring | Fragile namespace/version | XML-aware assertions |
| Test parser khác config | Bỏ sót runtime parser | Test message factory production |
| Mock JMS chứng minh broker | Bỏ selector/redelivery/ACL | Broker integration |
| Trust-all TLS test | Không kiểm chain/hostname | PKI fixtures đúng policy |

## 24. Chẩn đoán lỗi test slice

| Triệu chứng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| Endpoint bean không tồn tại | Context chưa scan/import | ContextConfiguration/Import |
| MockWebServiceClient không route | Mapping/adapter thiếu hoặc QName sai | Namespace/localPart |
| SOAP test pass, production HTTP 401 | Message test không qua filter | HTTP integration |
| Basic đúng nhưng SOAP không tới | Sai servlet mapping/matcher | Effective URL/filter order |
| WebMvcTest không tìm SOAP endpoint | MVC slice ngoài Spring-WS | SOAP message test |
| Boot condition không tạo bean | Classpath/property/bean condition | Condition report/BOM |
| JAXB javax/jakarta error | Namespace dependency lệch | Generated imports/runtime |
| Local pass, CI fail | JDK/plugin/property khác | Pin toolchain |
| Fault khác expected | Resolver/SOAP version | Fault code/namespace |
| Interceptor không chạy | Chưa đăng ký chain | Actual context |
| HTTP pass, TLS fail | Trust/SAN/cert config | Certificate chain |
| Mock JMS pass, broker fail | Provider semantics | ACL/selector/transaction |

Quy trình điều tra:
1. Xác nhận Boot, Framework, Spring-WS và JDK version.
2. Kiểm dependency tree: JAXB, servlet, JMS, security.
3. Xác định test dùng slice, focused hay full context.
4. Kiểm bean và auto-configuration conditions.
5. Xác minh endpoint mapping, interceptor và marshaller.
6. Phân biệt lỗi SOAP message với HTTP/TLS/JMS transport.
7. Kiểm test profile có tắt policy không.
8. Chạy với BOM/toolchain giống CI/deployment.
9. Bổ sung test tại đúng ranh giới lỗi.
10. Giữ regression assertion về side effect và failure layer.

## 25. Bài tập: test SOAP server nhiều lớp

**Bối cảnh:** Orders service dùng Spring Boot, Spring-WS, JAXB và Spring Security. CancelOrder có WSS4J interceptor, HTTP Basic trong SecurityFilterChain, XSD validation và database service. Team chỉ có một @SpringBootTest chậm cùng một mock gửi payload trực tiếp; lỗi gần đây cho thấy Basic bị bypass qua legacy servlet path.

**Yêu cầu:** xây test strategy phân tầng.

**Hướng giải quyết:**
1. Unit test business service cho authorization/idempotency với fixture giả.
2. JAXB/XSD test cho QName, sequence, required/optional/nillable.
3. MockWebServiceClient test routing, SOAP Fault và WSS4J interceptor thật.
4. Focused/full-context wiring test cho endpoint, marshaller, mapping và chain.
5. HTTP integration qua servlet path thật cho Basic thiếu/sai/đúng, legacy path và filter order.
6. Assert business method không chạy khi authentication/security fail.
7. TLS/mTLS test riêng nếu endpoint yêu cầu client certificate.
8. Broker test thật nếu có JMS transport; không dùng mock để tuyên bố selector/redelivery đúng.
9. Giữ một số @SpringBootTest kiểm complete configuration.
10. Pin Boot/Spring-WS/JAXB/JMS namespace và JDK trong CI.

**Tiêu chí đạt:** message tests nhanh; Basic không bypass legacy path; token invalid không có side effect; full-context test chứng minh production wiring/config đúng.

## 26. Checklist chọn lát cắt kiểm thử Spring Boot/Spring-WS

1. Xác định behavior cần chứng minh trước khi chọn annotation.
2. Dùng unit test cho logic không phụ thuộc Spring.
3. Dùng MockWebServiceClient cho SOAP message, mapping, interceptor và Fault.
4. Không coi mock message client là HTTP/TLS test.
5. Chỉ dùng Boot slice được hỗ trợ trong dependency/version hiện tại.
6. Không giả định @WebMvcTest tự cấu hình SOAP dispatcher.
7. Dùng focused context và import đúng SOAP configuration.
8. Giữ wiring/full-context test cho auto-config quan trọng.
9. Test HTTP SecurityFilterChain qua request đi qua servlet filter thật.
10. Phân biệt mock principal test với HTTP Basic credential verification.
11. Test WSDL public URL qua HTTP.
12. Test JAXB/XSD theo contract version đã phát hành.
13. Giữ WSS4J interceptor thật khi test security behavior.
14. Test parser hardening với message factory production.
15. Test TLS/mTLS và JMS/broker ở integration layer tương ứng.
16. Pin Boot BOM, Spring-WS, JDK, JAXB/XJC và JMS namespace.
17. Không override framework version tùy tiện để compile test.
18. Đảm bảo profiles/properties không tắt validation/security ngoài ý muốn.
19. Dùng secret/certificate fixture, không dùng credential production.
20. Assert side effects không chạy khi auth/schema/interceptor fail.
21. Bao gồm legacy routes và mapping aliases.
22. Dùng XML-aware assertions cho QName, Fault và payload.
23. Kiểm condition report nếu auto-configuration thiếu bean.
24. Dùng broker test thật cho provider-specific semantics.
25. Tổ chức test matrix theo rủi ro, không buộc mọi test boot toàn ứng dụng.

**Kết luận:** Test slice giúp Spring Boot kiểm tra nhanh và tập trung, nhưng cần chọn theo ranh giới cần xác minh. Trong Spring-WS, MockWebServiceClient phù hợp cho SOAP message processing; Boot slices chỉ kiểm subsystem mà chúng được thiết kế hỗ trợ; HTTP Basic, TLS/mTLS, WSDL publishing và JMS broker cần kiểm ở transport layer tương ứng. Luôn cố định Spring Boot/Spring-WS/JAXB/JMS versions, nạp đúng configuration và giữ integration tests chứng minh wiring gần production. Chiến lược nhiều lớp giúp phát hiện lỗi contract, security, servlet routing và sai khác cấu hình theo phiên bản.
