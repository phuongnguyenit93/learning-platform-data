# Khởi động máy chủ và client với HTTP transport thực tế

> **Chương:** Kiểm thử tích hợp  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP theo hướng contract-first với Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích trong tích hợp doanh nghiệp.

## 1. Vì sao cần kiểm thử với HTTP transport thật?

Unit test endpoint và MockWebServiceServer rất hữu ích, nhưng chúng không chứng minh toàn bộ SOAP application hoạt động qua HTTP. Endpoint có thể pass khi gọi trực tiếp nhưng server chưa đăng ký đúng MessageDispatcherServlet; client mock có thể marshal payload đúng nhưng HTTP message sender gửi Content-Type sai; WSDL có thể tồn tại trong classpath nhưng URL công bố không truy cập được.

Integration test với HTTP transport thực tế khởi động Spring application context, tạo SOAP servlet và gửi request qua socket HTTP tới server đang chạy. Nhờ đó, test bao phủ:

- Server startup, servlet mapping và endpoint discovery.
- WSDL/XSD publication và URL truy cập.
- HTTP request/response, SOAP version, Content-Type và SOAPAction.
- MessageFactory, JAXB marshalling/unmarshalling và interceptors.
- Request validation, response serialization và SOAP Fault mapping.
- Error handling và business side effects khi request sai.

Sau bài này, bạn có thể khởi động Spring-WS server trên random port, tạo WebServiceTemplate dùng HTTP sender thật, kiểm tra WSDL và SOAP messages qua HTTP, test Fault/validation/transport errors, và phân biệt mock tests với end-to-end integration tests.

**Nguyên tắc:** Test chỉ là HTTP integration test khi request đi qua HTTP stack thật tới server được khởi động cho test. Gọi endpoint method trực tiếp hoặc dùng MockWebServiceServer không đáp ứng mục tiêu này.

## 2. Kiến trúc kiểm thử end-to-end

~~~mermaid
flowchart LR
    T["JUnit integration test"] --> C["WebServiceTemplate"]
    C --> H["HTTP message sender"]
    H --> S["Embedded servlet container: random port"]
    S --> M["MessageDispatcherServlet"]
    M --> I["Endpoint interceptors"]
    I --> E["@Endpoint"]
    E --> B["Business service"]
    B --> E
    E --> M
    M --> S
    S --> H
    H --> C
    C --> T
~~~

Đây là server thật trong cùng JVM/process test, không phải production server hay remote vendor. Client mở kết nối TCP loopback tới port do container cấp. Test bao phủ servlet/filter/HTTP/message sender behavior của application, nhưng có thể chưa bao gồm reverse proxy, gateway, production TLS termination hoặc network policies.

| Thành phần | Được kiểm tra? |
|---|---|
| Spring application context và bean wiring | Có |
| Embedded servlet container và HTTP socket | Có |
| MessageDispatcherServlet mapping | Có |
| Endpoint mapping/interceptors | Có |
| HTTP message sender thật của client | Có |
| SOAP parsing và marshalling | Có |
| HTTP headers/status/content type | Có |
| Proxy/load balancer bên ngoài | Không, trừ khi đưa vào test environment |
| TLS/mTLS production topology | Không tự động |
| SOAP implementation độc lập của vendor | Không, cần cross-vendor test riêng |

## 3. Cấu trúc server contract-first

Một server Spring-WS contract-first thường gồm XSD, WSDL, MessageDispatcherServlet, endpoint mappings, JAXB/OXM binding, interceptors và business service.

~~~text
src/main/resources/
  xsd/
    orders.xsd

src/main/java/
  config/
    SoapWebServiceConfiguration.java
  endpoint/
    OrdersEndpoint.java
  service/
    OrderService.java
~~~

Integration test nên dùng đúng schema/WSDL mà server phát hành. Không tạo một schema khác chỉ dành cho test vì test sẽ không còn chứng minh contract production được đóng gói đúng.

## 4. Cấu hình MessageDispatcherServlet và WSDL

### 4.1. Đăng ký servlet

~~~java
import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.DefaultWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class SoapWebServiceConfiguration {

    @Bean
    ServletRegistrationBean<MessageDispatcherServlet>
    messageDispatcherServlet(ApplicationContext context) {
        MessageDispatcherServlet servlet =
                new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    XsdSchema ordersSchema() throws Exception {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean(name = "orders")
    DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("OrdersPort");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:orders:v1");
        definition.setSchema(ordersSchema);
        return definition;
    }
}
~~~

Đây là cấu hình minh họa phổ biến; method signatures và servlet registration cần khớp Spring Boot/Spring-WS version của dự án. WSDL có thể được công bố ở đường dẫn như /ws/orders.wsdl; hãy xác minh URL thực tế do application tạo ra.

### 4.2. Vì sao cần tải WSDL qua HTTP?

Đọc XSD từ classpath chỉ chứng minh file tồn tại trong artifact. GET WSDL qua URL server mới kiểm tra servlet mapping, WSDL transformation, soap:address, imports/includes và HTTP publication.

Không hardcode port 8080. Port đó có thể đang bị process khác dùng hoặc làm tests song song xung đột.

## 5. Endpoint và business service

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrdersEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return service.getOrder(request.getOrderId());
    }
}
~~~

DTOs là JAXB-generated/application classes. Dùng Spring-managed endpoint và business service thật để kiểm tra wiring, endpoint mapping và marshalling. Database có thể là test database hoặc repository fake tùy mục tiêu.

Với operation ghi dữ liệu, assert thành công tạo đúng một record/event; payload XSD-invalid không ghi record; security-invalid không gọi protected service; business-invalid không ghi trạng thái thành công. HTTP 500 không chứng minh transaction đã rollback.

## 6. WebServiceTemplate dùng HTTP transport thật

Client adapter:

~~~java
public class OrdersSoapClient {
    private final WebServiceTemplate template;

    public OrdersSoapClient(WebServiceTemplate template) {
        this.template = template;
    }

    public GetOrderResponse getOrder(String endpoint, String orderId) {
        GetOrderRequest request = new GetOrderRequest();
        request.setOrderId(orderId);
        return (GetOrderResponse)
                template.marshalSendAndReceive(endpoint, request);
    }
}
~~~

Cấu hình JAXB:

~~~java
@Bean
Jaxb2Marshaller ordersMarshaller() {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.schema");
    return marshaller;
}
~~~

Tạo template trong test:

~~~java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.orders.schema");
marshaller.afterPropertiesSet();

WebServiceTemplate template = new WebServiceTemplate(marshaller);
template.setDefaultUri(endpointUrl);
~~~

Dùng HTTP message sender thật của ứng dụng/Spring-WS version; không thay bằng mock và không bind MockWebServiceServer. Nếu cần connect/read timeout hoặc connection pooling, cấu hình sender tương ứng dependency version rồi giữ cấu hình đó trong integration tests.

Để kiểm tra adapter production, nên inject đúng WebServiceTemplate bean mà adapter sử dụng. Tránh tạo template test riêng rồi kết luận production client được cấu hình tương tự.

## 7. Spring Boot test với random port

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class SoapHttpIntegrationTest {

    @LocalServerPort
    int port;

    @Test
    void publishesWsdlOverHttp() {
        String wsdlUrl =
                "http://localhost:" + port + "/ws/orders.wsdl";

        String body = RestClient.create()
                .get()
                .uri(wsdlUrl)
                .retrieve()
                .body(String.class);

        assertNotNull(body);
        assertTrue(body.contains("urn:example:orders:v1"));
        assertTrue(body.contains("OrdersPort"));
    }
}
~~~

Chọn đúng package LocalServerPort theo Spring Boot version; các version khác nhau có thể dùng package annotation khác. Ví dụ này kiểm tra WSDL HTTP publication, không thay contract parser tests để resolve toàn bộ imports/includes.

RANDOM_PORT tránh port conflict và cho phép test lấy URL runtime. Spring TestContext có thể cache application context; không assume mỗi test method luôn khởi động server mới.

## 8. Gọi SOAP endpoint đang chạy

Một helper có thể tạo WebServiceTemplate dùng endpoint HTTP thật:

~~~java
private WebServiceTemplate createHttpSoapTemplate()
        throws Exception {
    Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
    marshaller.setContextPath("com.example.orders.schema");
    marshaller.afterPropertiesSet();

    WebServiceTemplate template =
            new WebServiceTemplate(marshaller);
    template.setDefaultUri(
            "http://localhost:" + port + "/ws");
    return template;
}
~~~

Test request/response:

~~~java
@Test
void callsRunningSoapEndpointOverHttp() throws Exception {
    WebServiceTemplate template = createHttpSoapTemplate();

    GetOrderRequest request = new GetOrderRequest();
    request.setOrderId("ORD-1001");

    GetOrderResponse response =
            (GetOrderResponse)
            template.marshalSendAndReceive(request);

    assertEquals("ORD-1001", response.getOrderId());
    assertEquals("PAID", response.getStatus());
}
~~~

Đây là ví dụ rút gọn. Trong dự án thực tế, dùng adapter production với endpoint URI được override qua test property/constructor để kiểm cả callback, interceptors, marshaller và error mapping đang được triển khai.

## 9. Kiểm tra HTTP và SOAP wire behavior

Capture hoặc quan sát request tại server test để assert HTTP method POST, path đúng servlet mapping, Content-Type đúng SOAP version, charset, SOAPAction/action parameter, Envelope namespace, Header/Body QNames, HTTP status và response Content-Type.

Nếu dùng test-only servlet filter/interceptor để ghi nhận headers, chỉ lưu metadata an toàn. Redact credentials, WS-Security token, signature values, PII và payload nhạy cảm.

SOAP 1.1 và SOAP 1.2 có Envelope namespace, HTTP media type, action convention và Fault model khác nhau. Nếu hỗ trợ cả hai, có test profile riêng. Không chỉ đổi Content-Type của SOAP 1.1 request để giả thành SOAP 1.2.

SOAPAction là routing/binding metadata, không phải authentication hoặc authorization.

## 10. Request validation và payload không hợp lệ

Dùng raw fixtures qua HTTP để kiểm:
- Payload đúng XSD.
- Thiếu element required.
- Sai sequence.
- Datatype không hợp lệ.
- Facets/range vi phạm.
- Vượt maxOccurs.
- Sai QName/namespace.
- Nil khi không nillable.
- Unknown element khi schema không cho extension.

Assertion quan trọng: payload không hợp XSD bị từ chối trước khi business service tạo side effects. Kiểm cả Fault/status theo contract và không echo raw XML.

~~~java
@Test
void rejectsPayloadThatViolatesSchema() {
    // Gửi raw SOAP XML qua HTTP client.
    // Assert rejection/Fault và business invocation count = 0.
}
~~~

Đây là skeleton. Khi dùng JAXB, object invalid có thể bị marshaller ngăn trước khi request tới server; để test server-side validator, gửi raw SOAP XML bằng HTTP client.

## 11. SOAP Fault qua HTTP thật

Kiểm cả SOAP Body Fault structure và HTTP status/headers. Tạo test cho modeled business fault, sender/client fault, receiver/server fault, security fault, validation fault và response serialization failure.

Không hardcode mọi Fault thành HTTP 500 nếu SOAP binding/framework configuration có behavior khác; nhưng phải bảo đảm không trả success body giả. Assert client nhận đúng exception/domain error và Fault detail không lộ stack trace hoặc secret.

## 12. Raw HTTP client cho payload chính xác

Với malformed XML hoặc XSD-invalid request, java.net.http.HttpClient giúp gửi đúng bytes:

~~~java
HttpClient httpClient = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("http://localhost:" + port + "/ws"))
    .header("Content-Type", "text/xml; charset=UTF-8")
    .header("SOAPAction", "\"urn:example:orders:v1/SubmitOrder\"")
    .POST(HttpRequest.BodyPublishers.ofString(rawSoapXml))
    .build();

HttpResponse<String> response = httpClient.send(
    request, HttpResponse.BodyHandlers.ofString());
~~~

Import java.net.http và java.net. Content-Type/SOAPAction phải phù hợp SOAP version/binding. Raw client phù hợp malformed XML, wrong Envelope namespace hoặc XSD-invalid payload; WebServiceTemplate phù hợp workflow JAXB của client.

## 13. Timeout, connection errors và retries

HTTP integration tests có thể kiểm connection refused, endpoint sai path, SOAP Fault, response chậm, timeout và connection close. Đặt timeout hữu hạn trên sender, dùng endpoint test có delay được kiểm soát và giới hạn test duration.

Không dùng sleep tùy tiện hoặc dựa tốc độ CI. Retry policy phải phân biệt transport error tạm thời với business Fault không retryable. Với operation có side effects, timeout không chứng minh server chưa commit; dùng idempotency key và reconciliation để tránh duplicate.

MockWebServiceServer phù hợp test retry logic nhanh; HTTP integration test kiểm transport thật. Không tạo retries vào remote production endpoint trong test.

## 14. TLS và mTLS

HTTP loopback cơ bản thường dùng plain HTTP. Nếu production dùng HTTPS:
- Khởi động test server HTTPS với test certificate.
- Client truststore chỉ chứa CA/test server certificate cần thiết.
- Kiểm hostname/SAN.
- Với mTLS, server yêu cầu client certificate.
- Test certificate hợp lệ, thiếu certificate và sai CA.
- Kiểm certificate-to-principal mapping nếu dùng Spring Security X.509.
- Không trust-all hoặc disable hostname verification để test pass.

TLS test dùng random HTTPS port và test keys. Không dùng private keys production. TLS handshake chỉ kiểm transport identity; WS-Security signature vẫn cần tests riêng nếu policy yêu cầu.

## 15. WS-Security và interceptors

Nếu endpoint yêu cầu WS-Security, dùng WSS4J client interceptor thật để ký/mã hóa request theo policy; server chạy inbound validation thật. Test signer tin cậy, signature sai, thiếu required header, Timestamp hết hạn và Body không được ký đúng. Assert request invalid không gọi business method.

Kiểm response signing/encryption nếu contract yêu cầu. Dùng test keystore/truststore riêng. Không mock WSS4J thành công rồi kết luận cryptographic interoperability; khi cần, kiểm bằng implementation/tool độc lập. Redact SOAP Security Header khỏi logs.

## 16. Test data, database và lifecycle

Dùng H2/testcontainers hoặc repository doubles tùy mục tiêu. Nếu cần kiểm transaction/locking/database dialect, chọn DB gần production hơn.

Mỗi test nên seed data xác định, gọi SOAP qua HTTP, assert response và database state, rồi cleanup hoặc dùng unique IDs/database reset.

Lưu ý test transaction trên JUnit thread không nhất thiết rollback writes do HTTP request xử lý trên server thread khác. Không giả định @Transactional test bao trùm server request. Dùng cleanup explicit, unique IDs hoặc database reset strategy.

## 17. Tránh flaky tests và rò rỉ tài nguyên

- Dùng random port.
- Không chia sẻ mutable test data giữa tests chạy song song.
- Đặt connect/read timeout hữu hạn.
- Để embedded server đóng theo Spring context lifecycle.
- Đóng HTTP clients/connection pools khi API yêu cầu.
- Dựa vào application test lifecycle để chờ readiness, không dùng sleep.
- Không gọi remote production endpoint.
- Không phụ thuộc thứ tự test.
- Dùng unique IDs và dọn database.
- Thu logs/captures đã redaction.

Chỉ dùng @DirtiesContext khi thực sự cần vì nó làm tăng chi phí startup. Reuse Spring TestContext có thể nhanh nếu state được cô lập đúng.

## 18. Ma trận kiểm thử tích hợp

| Kịch bản | Transport | Kỳ vọng |
|---|---|---|
| GET WSDL | HTTP GET | 200, WSDL truy cập được |
| SOAP valid request | HTTP POST | Response đúng |
| Wrong path | HTTP | Routing rejection |
| Wrong Content-Type | HTTP | Reject theo protocol |
| Invalid Envelope | HTTP | SOAP protocol rejection |
| XSD-invalid payload | HTTP SOAP | Reject trước side effect |
| Business-invalid request | HTTP SOAP | Modeled business Fault |
| Unknown operation/QName | HTTP SOAP | Dispatch rejection |
| Response serialization fail | HTTP SOAP | Fault/error, không success giả |
| SOAP 1.2 request | HTTP | Pass nếu endpoint hỗ trợ |
| WS-Security invalid | HTTP SOAP | Security rejection |
| Client certificate absent | HTTPS mTLS | Denial theo TLS config |
| Timeout/connection close | HTTP | Client error/retry đúng |

## 19. Quy trình xây dựng integration test đáng tin

1. Chọn contract/WSDL version và endpoint.
2. Khởi động Spring Boot server trên random port.
3. Tải WSDL/XSD qua HTTP.
4. Tạo WebServiceTemplate HTTP-backed và marshaller phù hợp.
5. Gọi operation bằng adapter production.
6. Capture request/response khi cần.
7. Assert SOAP response/Fault và business state.
8. Gửi negative fixtures qua raw HTTP client.
9. Chạy TLS/WS-Security profile riêng nếu production yêu cầu.
10. Cleanup database/test resources và lưu diagnostics redacted.

Mỗi test chứng minh một rủi ro cụ thể. Không thay đổi SOAP version, schema, authentication và database state cùng lúc trong một test lớn vì khó khoanh vùng lỗi.

## 20. Case study: client mock pass nhưng HTTP endpoint không hoạt động

### 20.1. Triệu chứng

MockWebServiceServer test của client pass; DTO marshal thành XML mong đợi và response giả unmarshal thành công. Khi gọi server thực, client nhận HTTP 404 hoặc 415.

### 20.2. Nguyên nhân có thể

- MessageDispatcherServlet chưa đăng ký hoặc mapping sai.
- Client dùng URI khác server mapping.
- WSDL soap:address sai sau deploy.
- Content-Type không khớp SOAP 1.1/1.2.
- SOAPAction hoặc Body QName sai.
- Endpoint bean tồn tại nhưng mapping/config chưa hoạt động.
- Client gọi sai port.
- Reverse proxy/context path production khác local.

### 20.3. Điều tra

~~~mermaid
flowchart TD
 A["Mock client pass, HTTP call fail"] --> B["GET WSDL từ random port"]
 B --> C{"WSDL truy cập được?"}
 C -->|Không| D["Kiểm servlet mapping/context"]
 C -->|Có| E["Kiểm address và binding"]
 E --> F["Capture HTTP request"]
 F --> G["Kiểm path/content-type/action"]
 G --> H["Kiểm Envelope và Body QName"]
 H --> I["Kiểm endpoint mapping/interceptor"]
 I --> J["Assert business call và server logs"]
~~~

### 20.4. Tiêu chí đóng

WSDL tải qua HTTP, imports resolve; client gọi đúng random port/path; content type, action, namespace và payload phù hợp; server dispatch đúng endpoint; response/Fault parse được; business side effect đúng số lần; regression test chạy trong CI.

## 21. Bài tập tự luyện

**Bài 1 — Mock pass:** MockWebServiceServer pass có chứng minh servlet mapping đúng?

**Đáp án:** Không. Cần khởi động HTTP server và gọi qua port thật.

**Bài 2 — Port cố định:** Vì sao dùng RANDOM_PORT?

**Đáp án:** Tránh conflict và tests song song; URL phải lấy port runtime.

**Bài 3 — WSDL classpath:** Đọc WSDL từ classpath có chứng minh consumer tải được?

**Đáp án:** Không. GET WSDL qua HTTP kiểm servlet/publication/address.

**Bài 4 — DTO invalid:** JAXB ngăn object invalid trước khi gửi. Đã test server-side validation?

**Đáp án:** Chưa. Gửi raw SOAP XML qua HTTP.

**Bài 5 — HTTP 415:** Nguyên nhân thường gặp?

**Đáp án:** Content-Type/SOAP version không khớp; kiểm request capture và WSDL binding.

**Bài 6 — Test transaction:** Vì sao @Transactional JUnit test không chắc rollback server write?

**Đáp án:** HTTP request có thể chạy ở server thread/transaction khác; dùng cleanup/unique IDs/DB reset.

**Bài 7 — Timeout:** Client timeout nghĩa server không xử lý?

**Đáp án:** Không. Server có thể commit trước khi response mất; cần idempotency/reconciliation.

**Bài 8 — TLS:** HTTP test thành công chứng minh mTLS production?

**Đáp án:** Không nếu test dùng plain HTTP; cần HTTPS server/client với test certificates.

**Bài 9 — WS-Security:** TLS pass có thay SOAP signature verification?

**Đáp án:** Không; đó là hai lớp khác nhau.

**Bài 10 — Side effects:** XSD-invalid request trả Fault. Assertion quan trọng?

**Đáp án:** Business method không được gọi và database/event side effects bằng zero.

## 22. Checklist nghiệm thu

### Server và publication
- [ ] Spring context khởi động SOAP servlet.
- [ ] MessageDispatcherServlet mapping đúng.
- [ ] Endpoint beans/mappings được phát hiện.
- [ ] WSDL/XSD tải được qua HTTP runtime port.
- [ ] WSDL service address đúng port/context path.
- [ ] Imports/includes resolve từ consumer boundary.

### HTTP client thực
- [ ] WebServiceTemplate dùng HTTP sender thật, không gắn MockWebServiceServer.
- [ ] Adapter production sử dụng template/config được kiểm thử.
- [ ] URL lấy từ random port, không hardcode.
- [ ] Content-Type, SOAP version, SOAPAction và path đúng.
- [ ] Request/response QName, namespace và validation đúng.
- [ ] Connect/read timeout hữu hạn.

### Response và side effects
- [ ] Happy path response đúng contract.
- [ ] SOAP Fault/business fault được xử lý đúng.
- [ ] XSD-invalid request bị từ chối trước side effects.
- [ ] Business-invalid được phân loại riêng.
- [ ] Database/event state đúng số lần.
- [ ] Timeout/retry có idempotency và duplicate protection.

### Security và vận hành
- [ ] TLS/mTLS được test riêng nếu production yêu cầu.
- [ ] WS-Security signing/encryption test bằng cấu hình thật.
- [ ] Invalid security message không gọi protected business method.
- [ ] XML parser hardening/XXE và size limits được test.
- [ ] Không log credentials, tokens, private keys hoặc raw PII.
- [ ] Test data, server lifecycle và DB cleanup được cô lập.
- [ ] HTTP integration tests chạy trong CI với captures redacted.

**Ghi nhớ:** HTTP integration test của Spring Web Services phải khởi động server trong test lifecycle và gọi qua HTTP socket bằng WebServiceTemplate/message sender thật. Kiểm tra WSDL publication, servlet mapping, SOAP version, Content-Type, SOAPAction, QName, validation, Fault và business side effects. MockWebServiceServer vẫn hữu ích ở tầng client unit test, nhưng không thay thế việc chứng minh server và client trao đổi qua transport. TLS/mTLS, WS-Security, proxy và interoperability liên vendor cần được kiểm tra bằng cấu hình tương ứng, với test credentials và evidence có thể tái lập.
