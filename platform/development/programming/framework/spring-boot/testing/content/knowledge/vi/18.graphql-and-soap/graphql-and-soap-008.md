# @WebServiceClientTest cho ứng dụng SOAP client trong Spring Boot

## 1. Mục tiêu và vấn đề thực tế

Một ứng dụng Spring Boot có thể cung cấp REST/GraphQL API cho khách hàng nhưng phía sau lại phải gọi hệ thống kế toán, thanh toán, bảo hiểm hoặc ERP qua **SOAP**. Phần giao tiếp này thường được đóng gói trong một client bean dùng Spring Web Services (`Spring-WS`), `WebServiceTemplate` và `WebServiceTemplateBuilder`.

Vấn đề khi kiểm thử:
- Không muốn mỗi lần chạy `mvn test` lại phải truy cập SOAP server của đối tác.
- Cần biết client có tạo **SOAP body** đúng namespace, element và giá trị hay không.
- Cần xác minh client gọi đúng **destination URI**, SOAPAction (nếu đối tác yêu cầu), đọc response thành kết quả domain và xử lý SOAP Fault.
- Cần test ổn định, không phụ thuộc DNS, proxy, mạng VPN, TLS handshake hay dữ liệu thật của đối tác.
- Không muốn `@SpringBootTest` tải toàn bộ database, messaging và web server khi mục tiêu chỉ là một adapter SOAP.

Spring Boot cung cấp **`@WebServiceClientTest`**, một **test slice** dành cho Spring-WS client. Trong Spring Boot **3.5.x**, annotation này tự đưa vào `MockWebServiceServer` và tùy chỉnh `WebServiceTemplateBuilder` dùng trong slice, để bạn kiểm request/response SOAP ngay trong JVM.

Ví dụ ý tưởng:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {

    @Autowired MockWebServiceServer server;
    @Autowired ExchangeRateSoapClient client;

    @Test
    void convertsSoapResponseToDomainValue() {
        server.expect(payload(new StringSource("""
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>USD</fx:currency>
                </fx:GetRateRequest>
                """)))
            .andRespond(withPayload(new StringSource("""
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>1.25</fx:rate>
                </fx:GetRateResponse>
                """)));

        assertThat(client.getRate("USD"))
                .isEqualByComparingTo("1.25");

        server.verify();
    }
}
```

Đây là bản rút gọn; toàn bộ imports, ứng dụng, client thật và test runnable được trình bày ở phần thực hành.

**Sau bài này, bạn phải phân biệt được:**
1. `@WebServiceClientTest` kiểm **SOAP client**; `@WebServiceServerTest` kiểm **SOAP server endpoint**.
2. `MockWebServiceServer` trả lời một `WebServiceTemplate` do client gọi, không phải HTTP server thật.
3. `WebServiceTemplateBuilder` là điểm Spring Boot tùy chỉnh để gắn mock sender; `new WebServiceTemplate()` bên ngoài builder có thể không được can thiệp.
4. `server.expect(...).andRespond(...)` khai báo request/response giả lập; `server.verify()` xác nhận mọi expectation đã được dùng.
5. SOAP **Envelope/Header/Body**, **payload XML**, **WSDL/XSD**, SOAPAction, **SOAP Fault** và lỗi transport là các tầng khác nhau cần kiểm có chủ đích.
6. Test slice PASS không tự chứng minh credential production, WS-Security, TLS, WSDL của đối tác đang triển khai hoặc tương thích thực giữa hai hệ thống.

## 2. Bối cảnh: SOAP và các lớp trong Spring Web Services

### 2.1. SOAP là thông điệp XML, không phải REST JSON

Một SOAP 1.1 request có cấu trúc khái quát:

```xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:fx="urn:example:fx">
  <soapenv:Header>
    <!-- SOAP headers, nếu contract yêu cầu -->
  </soapenv:Header>
  <soapenv:Body>
    <fx:GetRateRequest>
      <fx:currency>USD</fx:currency>
    </fx:GetRateRequest>
  </soapenv:Body>
</soapenv:Envelope>
```

Trong Spring-WS:
- `WebServiceTemplate` vận hành quá trình tạo message, gửi request và nhận response.
- `WebServiceMessageFactory` tạo SOAP message, thường qua SAAJ khi các dependency phù hợp.
- `WebServiceMessageSender` vận chuyển message qua HTTP hoặc transport khác.
- `Marshaller`/`Unmarshaller` chuyển Java objects thành XML và ngược lại nếu dùng `marshalSendAndReceive(...)`.
- `WebServiceTemplateBuilder` là builder Boot auto-configured để tạo và tùy chỉnh template.
- `MockWebServiceServer` thay thế **đường vận chuyển phía client** để bắt request và trả fake response.

Khi viết `RequestMatchers.payload(new StringSource(...))`, bạn đang so **payload dưới SOAP Body**, không nhất thiết so toàn bộ Envelope, HTTP headers, TLS hay WS-Security signature. Đây là lợi thế cho unit/slice test vì không lệ thuộc những chi tiết không thuộc contract test. Nhưng nếu SOAP headers/signature là bắt buộc, phải có thêm matcher và integration tests tương ứng.

### 2.2. Namespace quan trọng hơn prefix

Hai XML snippets sau có thể cùng ý nghĩa về tên phần tử nếu namespace URI giống nhau:

```xml
<fx:GetRateRequest xmlns:fx="urn:example:fx">
  <fx:currency>USD</fx:currency>
</fx:GetRateRequest>
```

```xml
<GetRateRequest xmlns="urn:example:fx">
  <currency>USD</currency>
</GetRateRequest>
```

Tên đầy đủ của element là **`{namespaceURI}localName`**, không đơn thuần chuỗi prefix `fx`. Khi kiểm, dùng XML-aware matcher hoặc namespace-aware XPath/DOM. Không so raw XML string nếu test chỉ quan tâm cấu trúc/ngữ nghĩa; thứ tự XML attributes, namespace prefix hay whitespace có thể thay đổi khi serializer đổi.

**Cảnh báo:** Không nên kết luận mọi XML structural comparer đều bỏ qua toàn bộ whitespace hoặc prefix trong mọi cấu hình; mức so phụ thuộc XMLUnit comparator và matcher. Nếu có yêu cầu whitespace/signature canonicalization, viết phép kiểm chuyên biệt.

### 2.3. SOAP Body khác SOAP Envelope

`<fx:GetRateRequest>` là **payload** nằm trong `soapenv:Body`. `WebServiceTemplate.sendSourceAndReceiveToResult(...)` nhận `Source` của payload và tạo SOAP Envelope thông qua message factory; code client thường không tự lắp thủ công toàn bộ Envelope.

Nếu bạn truyền cả một `<soapenv:Envelope>` vào `StringSource` như thể nó là body payload, có thể tạo message sai (Envelope lồng trong Body). Trước khi viết test, xác định API đang nhận **payload**, SOAP message hay raw HTTP request.

### 2.4. SOAPAction và WS-Addressing không giống nhau

- **SOAPAction** ở SOAP 1.1 là HTTP header với ý nghĩa action theo contract, có thể đặt qua `SoapActionCallback`.
- **WS-Addressing Action** là SOAP header thuộc bộ thông số WS-Addressing; Spring-WS cung cấp `ActionCallback` riêng.
- Hai cơ chế có thể liên quan nhưng không tự đồng nhất; không kiểm WS-Addressing bằng cách chỉ thấy SOAPAction HTTP header.
- SOAP 1.2 có quy tắc action gắn với content type khác SOAP 1.1.

Nếu đối tác cung cấp WSDL/policy, phải đọc đúng **binding**, **SOAP version**, action và header requirements trước khi dựng test.

## 3. @WebServiceClientTest thực sự làm gì?

### 3.1. Đúng annotation và package ở Spring Boot 3.5

```java
import org.springframework.boot.test.autoconfigure.webservices.client.WebServiceClientTest;
import org.springframework.ws.test.client.MockWebServiceServer;
```

Một lớp test điển hình:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {
    @Autowired ExchangeRateSoapClient client;
    @Autowired MockWebServiceServer server;
}
```

Theo Javadoc 3.5, `@WebServiceClientTest` được triển khai bằng các meta-annotations:

```java
@OverrideAutoConfiguration(enabled = false)
@TypeExcludeFilters(WebServiceClientExcludeFilter.class)
@AutoConfigureCache
@AutoConfigureMockWebServiceServer
@AutoConfigureWebServiceClient
@ImportAutoConfiguration
```

Khối trên mô tả thành phần của annotation, không phải một file Java độc lập. Ý nghĩa:
- Tắt broad auto-configuration từ `@EnableAutoConfiguration`.
- Thu hẹp component scan theo quy tắc của slice.
- Nhập bộ auto-configurations phù hợp client, mock server và một số hạ tầng phụ trợ.
- Không cố tạo application context giống đầy đủ production.

**Không** hiểu đây là `@SpringBootTest` “có thêm annotation”. Nó là một **slice với tập bean khác**.

### 3.2. Đúng thành phần cần test

Cú pháp:

```java
@WebServiceClientTest(ExchangeRateSoapClient.class)
```

hoặc:

```java
@WebServiceClientTest(components = ExchangeRateSoapClient.class)
```

`value` và `components` là alias của nhau. Nêu rõ component để test có phạm vi dễ kiểm soát; tránh chỉ đặt `@WebServiceClientTest` rồi mặc định mọi `@Service` hoặc repository trong ứng dụng sẽ được scan. Javadoc cho biết default scanning chủ yếu bao gồm `@JsonComponent` và Jackson `Module`; các bean client cụ thể nên được chọn rõ.

Các thuộc tính khác gồm `properties`, `includeFilters`, `excludeFilters`, `excludeAutoConfiguration` và `useDefaultFilters`. Không mở rộng filter tràn lan chỉ để tránh lỗi thiếu bean: chỉ thêm đúng dependency mà client dưới test cần.

### 3.3. MockWebServiceServer do Boot cung cấp

Spring Boot 3.5 tự cấu hình `MockWebServiceServer` và tùy chỉnh `WebServiceTemplateBuilder` được ứng dụng sử dụng trong slice. Điều này cho phép:

```java
server.expect(payload(new StringSource("<request/>")))
      .andRespond(withPayload(new StringSource("<response/>")));
```

Đây là ví dụ cấu trúc. Khi client dùng template tạo từ builder của Boot, mock sender nhận request; không có TCP connection thực tới đối tác. Nếu request khác expectation, test fail; nếu client không gửi request mong đợi, `verify()` phát hiện còn expectation chưa dùng.

### 3.4. WebServiceTemplateBuilder là mắt xích quan trọng

Spring Boot tự cung cấp **builder**, nhưng thường **không tự đăng ký một bean `WebServiceTemplate` duy nhất** vì các ứng dụng cần nhiều destination/marshaller/interceptors/credentials khác nhau.

Code production nên có dạng:

```java
@Service
public class ExchangeRateSoapClient {
    private final WebServiceTemplate template;

    public ExchangeRateSoapClient(WebServiceTemplateBuilder builder) {
        this.template = builder
                .setDefaultUri("https://soap.partner.test/fx")
                .build();
    }
}
```

Đây là trích đoạn minh họa; lớp đầy đủ ở phần 8. Builder có các khả năng như default URI, message senders, customizers, interceptors, marshaller/unmarshaller, HTTP client settings. Khi test, builder được Boot tùy chỉnh để gắn transport giả lập.

**Phân biệt:** Inject `WebServiceTemplateBuilder` và gọi `build()` khác hẳn `new WebServiceTemplate()` rồi tự cấu hình message sender ngoài hệ thống Boot. Cách thứ hai có thể gửi network thật hoặc không được mock server bắt.

### 3.5. Client inject trực tiếp WebServiceTemplate thì sao?

Javadoc Boot 3.5 ghi rõ nếu client **không dùng builder** mà inject một `WebServiceTemplate` bean, bạn có thể bổ sung:

```java
@WebServiceClientTest(LegacySoapClient.class)
@AutoConfigureWebServiceClient(registerWebServiceTemplate = true)
class LegacySoapClientTest {
    @Autowired MockWebServiceServer server;
    @Autowired LegacySoapClient client;
}
```

`LegacySoapClient` là tên ví dụ, không có trong runnable project mục 8. Import:

```java
import org.springframework.boot.test.autoconfigure.webservices.client.AutoConfigureWebServiceClient;
```

Giá trị mặc định của `registerWebServiceTemplate` là **false**, vì thiết kế ưu tiên tạo template qua builder. Bật flag này khi loại client thực sự inject trực tiếp template. Không thêm nó vô điều kiện khi app có nhiều templates hoặc custom wiring: cần xác định template nào được mock và nguồn bean thực tế.

### 3.6. Điều mà test slice không tự làm

`@WebServiceClientTest` không tự:
- Khởi động SOAP server thật hoặc deploy `MessageDispatcherServlet` của đối tác.
- Đọc WSDL từ URL production và xác minh binding đang hoạt động.
- Tạo mọi `@Service`/`@Repository`/`@ConfigurationProperties` của app.
- Cấp secret, token, truststore/keystore hoặc WS-Security policy của production.
- Mô phỏng chính xác mọi loại SOAP transport, timeout, retry và multi-hop gateway.
- Thay thế end-to-end integration test với sandbox của đối tác.

Đó là giới hạn **cố ý** của slice, không phải bug.

## 4. Luồng MockWebServiceServer kiểm thử client

```text
JUnit @Test
  |
  |  server.expect(connectionTo(...))
  |        .andExpect(payload(...))
  |        .andRespond(withPayload(...))
  |
  v
ExchangeRateSoapClient.getRate("USD")
  |
  v
WebServiceTemplate (được builder tạo)
  |
  v
Mock WebServiceMessageSender / MockWebServiceServer
  |
  +--> so URI, XML payload, SOAP metadata nếu có matcher
  +--> trả SOAP response payload hoặc SOAP Fault giả lập
  |
  v
WebServiceTemplate nhận và xử lý message
  |
  v
Client parse/map response thành BigDecimal/domain result
  |
  v
AssertJ kiểm domain result
  |
  v
server.verify() kiểm đã dùng hết expectations
```

Điểm giá trị nhất: bạn kiểm được **XML được gửi thực sự bởi client**, cách client dùng `WebServiceTemplate` và cách nó parse/unmarshal response, nhưng **không** cần server thật.

### 4.1. Các bước tiêu chuẩn

1. Cấu hình `MockWebServiceServer` đã inject.
2. Khai báo một hoặc nhiều `expect(RequestMatcher)`.
3. Nếu cần, nối thêm `andExpect(RequestMatcher)`.
4. Định nghĩa `andRespond(ResponseCreator)`.
5. Gọi phương thức client đang cần test.
6. Assert kết quả domain hoặc exception.
7. Gọi `server.verify()` để đảm bảo expectations đã được thực hiện.

Nếu dùng cùng mock server qua nhiều methods trong cached Spring context, nên làm mới/reset expectations có kiểm soát theo từng test; phần runnable dùng `@BeforeEach server.reset()`.

### 4.2. Các request matchers tiêu biểu

| Matcher | Kiểm điều gì | Giá trị |
| --- | --- | --- |
| `connectionTo("https://...")` | Destination URI mà client dùng | Phát hiện gọi nhầm sandbox/production endpoint |
| `payload(new StringSource(xml))` | XML payload trong SOAP Body | Namespace, element, business fields |
| `validPayload(resource)` | Payload hợp lệ theo XSD | Contract schema khi có tài nguyên XSD |
| `xpath(expression, ...)` | Node/value theo XPath | Kiểm field động, namespace, path |
| `soapHeader(...)` | Header SOAP có mặt/phù hợp | Kiểm một phần metadata contract |
| `anything()` | Không ràng buộc request cụ thể | Chỉ nên dùng khi input thực sự không là đối tượng test |

`validPayload`/`xpath` có overload và semantics cụ thể theo phiên bản Spring-WS; cần khai báo Resource/namespace context phù hợp và thêm dependency XML test cần thiết. Không copy placeholder matcher rồi tuyên bố đã kiểm đủ toàn bộ WSDL.

### 4.3. Các response creators tiêu biểu

| Creator | Ý nghĩa | Dùng khi |
| --- | --- | --- |
| `withPayload(new StringSource(xml))` | Trả response SOAP có payload XML | Happy path/mapping |
| `withClientOrSenderFault(reason, locale)` | SOAP Client/Sender fault | Input/business validation từ đối tác |
| `withServerOrReceiverFault(reason, locale)` | SOAP Server/Receiver fault | Đối tác có lỗi phía server |
| `withError(message)` | Giả lập lỗi ở transport connection | Đường lỗi kết nối |
| `withException(exception)` | Giả lập exception trong xử lý transport | Fault injection theo loại exception |
| `withVersionMismatchFault(...)` | SOAP version mismatch | Kiểm behavior khi không tương thích SOAP version |

**Không đồng nhất SOAP Fault với HTTP 500:** server SOAP thường có response fault theo SOAP protocol và mã HTTP có thể phụ thuộc SOAP version/transport. Spring-WS mặc định có thể ném `SoapFaultClientException`. `withError` mô phỏng transport error, không có SOAP Fault payload.

## 5. SOAP client test khác SOAP server test

| Câu hỏi | Test client | Test server |
| --- | --- | --- |
| Annotation Boot | `@WebServiceClientTest` | `@WebServiceServerTest` |
| Đối tượng đang test | Bean sử dụng `WebServiceTemplate` để gọi ra ngoài | Spring-WS `@Endpoint` nhận SOAP request |
| Đối tượng giả lập | Đối tác SOAP server | SOAP caller/client |
| Công cụ test | `MockWebServiceServer` | `MockWebServiceClient` |
| Luồng test | Expect outbound SOAP request; giả lập response | Gửi inbound SOAP request; expect server response |
| Client transport có gửi mạng? | Không, với mock builder đúng | Không, endpoint được gọi trong test context |
| Cần SOAP server thật của đối tác? | Không | Không |
| Điểm kiểm trọng tâm | Body/URI/header client tạo và cách client xử lý response/fault | Payload routing, endpoint adapter, marshalling/response/fault của app |

**Lỗi thường gặp:** inject `MockWebServiceClient` trong `@WebServiceClientTest` rồi mong nó nhận được request outbound. Hai lớp có vai trò đảo nhau. `MockWebServiceServer` là tên chính xác cho test **client gọi đi**.

### 5.1. So với REST/GraphQL testing

- REST client của Boot có `@RestClientTest` với `MockRestServiceServer` hoặc builder REST tương ứng.
- Spring MVC controller dùng `@WebMvcTest` + `MockMvc`/`MockMvcTester`.
- Spring WebFlux controller dùng `@WebFluxTest` + `WebTestClient`.
- GraphQL server có `@GraphQlTest` + `GraphQlTester`.
- SOAP client dùng `@WebServiceClientTest` + `MockWebServiceServer`.

Dù các technology cùng nằm trong một ứng dụng, không gắn nhiều slice annotations như `@RestClientTest` và `@WebServiceClientTest` lên cùng một class để “gộp mọi thứ”. Dùng test đúng boundary; nếu thực sự cần nhiều tầng tích hợp, chuyển sang `@SpringBootTest` với các mock integrations tương ứng.

## 6. Phụ thuộc Maven và package của Spring Boot 3.5

### 6.1. Production dependency

Trong Spring Boot **3.5**, artifact Spring Web Services starter chính xác là:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web-services</artifactId>
</dependency>
```

Tên có dấu gạch ngang giữa `web` và `services` trong dòng Boot 3.5. Spring Boot 4 có starter/module naming được sắp xếp lại; dùng tên artifact và package đúng major của dự án, không lấy tài liệu Boot 4 rồi import lại vào 3.5.

### 6.2. Test dependency

`spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Mockito và Spring Boot test support. Thư viện chứa `MockWebServiceServer` là:

```xml
<dependency>
    <groupId>org.springframework.ws</groupId>
    <artifactId>spring-ws-test</artifactId>
    <scope>test</scope>
</dependency>
```

Định nghĩa rõ `spring-ws-test` tránh giả định Spring Boot starter test luôn kéo đúng module Spring-WS testing. Spring Boot BOM 3.5 quản lý version của `spring-ws-test`; không pin version độc lập nếu không có yêu cầu tương thích riêng.

### 6.3. Tên các class quan trọng

| Class/annotation | Package trong Boot 3.5 / Spring-WS |
| --- | --- |
| `@WebServiceClientTest` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `@AutoConfigureWebServiceClient` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `@AutoConfigureMockWebServiceServer` | `org.springframework.boot.test.autoconfigure.webservices.client` |
| `WebServiceTemplateBuilder` | `org.springframework.boot.webservices.client` |
| `WebServiceTemplate` | `org.springframework.ws.client.core` |
| `SoapActionCallback` | `org.springframework.ws.soap.client.core` |
| `SoapFaultClientException` | `org.springframework.ws.soap.client` |
| `MockWebServiceServer` | `org.springframework.ws.test.client` |
| `RequestMatchers` | `org.springframework.ws.test.client` |
| `ResponseCreators` | `org.springframework.ws.test.client` |
| `StringSource` / `StringResult` | `org.springframework.xml.transform` |
| `Jaxb2Marshaller` | `org.springframework.oxm.jaxb` |

Lỗi import thường xảy ra khi trộn ví dụ Spring Boot 4 (package test module mới) với project Spring Boot 3.5.

## 7. Thiết kế bài thực hành

Ví dụ ứng dụng có một client gọi đối tác cung cấp tỷ giá. Client nhận mã tiền tệ như `USD` và trả `BigDecimal` theo XML.

### 7.1. Contract XML dùng trong ví dụ

Outbound request payload:

```xml
<fx:GetRateRequest xmlns:fx="urn:example:fx">
  <fx:currency>USD</fx:currency>
</fx:GetRateRequest>
```

Inbound success payload:

```xml
<fx:GetRateResponse xmlns:fx="urn:example:fx">
  <fx:rate>1.25</fx:rate>
</fx:GetRateResponse>
```

Các thông tin thử nghiệm:
- Destination: `https://soap.partner.test/fx` — chỉ là URI mẫu, **không gọi mạng trong mock test**.
- SOAPAction: `urn:example:fx/GetRate` — đặt bằng `SoapActionCallback`.
- Business input: mã tiền tệ đúng ba chữ cái ASCII viết hoa `[A-Z]{3}`.
- Output: `BigDecimal`; không chuyển tỷ giá qua `double`.
- XML namespace URI: `urn:example:fx`; client kiểm namespace khi parse response.
- Nếu response không có một `<fx:rate>` duy nhất hoặc giá trị không hợp lệ, client ném `IllegalStateException`.
- Nếu SOAP server báo Fault, Spring-WS xử lý theo fault resolver và client test kiểm exception.

### 7.2. Vì sao dùng Source/Result thay vì JAXB trong phần chạy được?

Spring-WS hỗ trợ hai cách phổ biến:
1. `marshalSendAndReceive` với `Jaxb2Marshaller` và classes được sinh từ XSD/WSDL.
2. `sendSourceAndReceiveToResult` với XML `Source` và `Result` trực tiếp.

Bài chọn cách **thứ hai** cho project runnable: ít phụ thuộc mã sinh JAXB, dễ nhìn rõ SOAP payload và vai trò mock server. Không có nghĩa thao tác XML thủ công nên là mặc định production; khi có WSDL/XSD ổn định, contract-first JAXB classes và schema validation thường phù hợp hơn. Phần sau chỉ rõ cách mở rộng theo hướng đó.

## 8. Project Maven hoàn chỉnh: Java 17 + Spring Boot 3.5.16

### 8.1. Cây thư mục

```text
soap-client-test-lab/
├── pom.xml
├── src/main/java/com/example/soaplab/
│   ├── SoapClientLabApplication.java
│   └── ExchangeRateSoapClient.java
└── src/test/java/com/example/soaplab/
    ├── ExchangeRateSoapClientTest.java
    └── ExchangeRateParseTest.java
```

Toàn bộ file Java nằm trong package `com.example.soaplab`; test classes kết thúc bằng `Test` để Maven Surefire nhận diện. Không có controller/endpoint của ứng dụng; đây là **outbound SOAP client**.

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>soap-client-test-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web-services</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.ws</groupId>
            <artifactId>spring-ws-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Giải thích:
- Spring Boot parent/BOM quản lý dependency versions.
- `spring-boot-starter-web-services` kéo Spring-WS, XML support và SOAP runtime thích hợp.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, Spring Test.
- `spring-ws-test` là thư viện client-side mock server.
- Không khai báo database, Spring Data hoặc Kafka vì không cần.
- `spring-boot-maven-plugin` giúp chạy một Spring Boot application, dù unit/slice tests không khởi động server đối tác.

### 8.3. Application class

`src/main/java/com/example/soaplab/SoapClientLabApplication.java`:

```java
package com.example.soaplab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SoapClientLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(SoapClientLabApplication.class, args);
    }
}
```

Trong `@WebServiceClientTest`, Boot có thể dùng application configuration class này để tìm context cấu hình, nhưng **slice filters** quyết định bean nào được đưa vào, không phải toàn bộ component scan được chạy như full production context.

### 8.4. ExchangeRateSoapClient.java

`src/main/java/com/example/soaplab/ExchangeRateSoapClient.java`:

```java
package com.example.soaplab;

import java.io.IOException;
import java.io.StringReader;
import java.math.BigDecimal;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.springframework.boot.webservices.client.WebServiceTemplateBuilder;
import org.springframework.stereotype.Service;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;
import org.springframework.xml.transform.StringResult;
import org.springframework.xml.transform.StringSource;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

@Service
public class ExchangeRateSoapClient {

    private static final String NS = "urn:example:fx";
    private static final String SOAP_URI = "https://soap.partner.test/fx";
    private static final String SOAP_ACTION = "urn:example:fx/GetRate";

    private final WebServiceTemplate template;

    public ExchangeRateSoapClient(WebServiceTemplateBuilder builder) {
        this.template = builder
                .setDefaultUri(SOAP_URI)
                .build();
    }

    public BigDecimal getRate(String currency) {
        // Chỉ cho phép đúng 3 chữ cái ASCII viết hoa, tránh
        // chèn nội dung tùy ý vào XML khi dựng StringSource.
        if (currency == null || !currency.matches("[A-Z]{3}")) {
            throw new IllegalArgumentException(
                    "Currency must contain exactly three uppercase letters");
        }

        String requestXml = """
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>%s</fx:currency>
                </fx:GetRateRequest>
                """.formatted(currency);

        StringResult result = new StringResult();

        boolean responseReceived =
                template.sendSourceAndReceiveToResult(
                        new StringSource(requestXml),
                        new SoapActionCallback(SOAP_ACTION),
                        result);

        if (!responseReceived) {
            throw new IllegalStateException("SOAP response payload is missing");
        }

        return parseRate(result.toString());
    }

    // Package-private để unit test kiểm parser riêng
    // mà không cần tạo Spring context hay SOAP transport.
    static BigDecimal parseRate(String xml) {
        try {
            DocumentBuilderFactory factory =
                    DocumentBuilderFactory.newInstance();
            factory.setNamespaceAware(true);
            factory.setFeature(
                    "http://apache.org/xml/features/disallow-doctype-decl",
                    true);
            factory.setFeature(
                    "http://xml.org/sax/features/external-general-entities",
                    false);
            factory.setFeature(
                    "http://xml.org/sax/features/external-parameter-entities",
                    false);
            factory.setXIncludeAware(false);
            factory.setExpandEntityReferences(false);

            Document document = factory.newDocumentBuilder()
                    .parse(new InputSource(new StringReader(xml)));

            Element root = document.getDocumentElement();
            if (root == null
                    || !"GetRateResponse".equals(root.getLocalName())
                    || !NS.equals(root.getNamespaceURI())) {
                throw new IllegalStateException(
                        "Unexpected SOAP response root or namespace");
            }

            NodeList rates = root.getElementsByTagNameNS(NS, "rate");
            if (rates.getLength() != 1) {
                throw new IllegalStateException(
                        "Expected exactly one rate element");
            }

            String value = rates.item(0).getTextContent().trim();
            if (value.isEmpty()) {
                throw new IllegalStateException(
                        "SOAP rate must not be empty");
            }
            return new BigDecimal(value);
        }
        catch (ParserConfigurationException
                | SAXException
                | IOException
                | NumberFormatException ex) {
            throw new IllegalStateException(
                    "Invalid SOAP rate response", ex);
        }
    }
}
```

**Điều đoạn code chứng minh:**
- Client nhận `WebServiceTemplateBuilder` qua constructor injection. Đây là đường Boot customizer có thể thay transport bằng mock.
- `setDefaultUri` xác định SOAP endpoint. Test sẽ dùng `connectionTo` để xác minh.
- `SoapActionCallback` đặt action theo ví dụ contract; một đối tác thực có thể dùng action khác.
- `sendSourceAndReceiveToResult` gửi **payload Source**, không gửi raw SOAP Envelope.
- `StringResult` nhận response payload do WebServiceTemplate trích từ SOAP Body.
- `parseRate` kiểm root QName (local name + namespace URI), đúng một `rate` và numeric content; không so raw XML text.
- XML parser chặn DOCTYPE và external entities trong ví dụ, giảm rủi ro XXE với dữ liệu XML không đáng tin; production cần kết hợp secure parsing và marshalling/validation theo security requirements.
- Vì input `currency` chỉ được phép `[A-Z]{3}`, không có ký tự `<`, `&` hoặc quote để phá cấu trúc XML. Với input tự do (tên người, address), **không** nối chuỗi XML thủ công; dùng XMLStreamWriter, JAXB marshaller hoặc writer có escape đúng.
- `parseRate` là package-private để kiểm unit riêng; trong production có thể tách XML decoder thành component/module testable.

**Phạm vi bảo mật:** Kiểm đầu vào tránh XML injection và cấu hình parser chống DOCTYPE là cần thiết, nhưng không tự thay thế schema validation, WS-Security signature verification hoặc giới hạn kích thước XML.

### 8.5. ExchangeRateSoapClientTest.java

`src/test/java/com/example/soaplab/ExchangeRateSoapClientTest.java`:

```java
package com.example.soaplab;

import java.util.Locale;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.client.WebServiceClientTest;
import org.springframework.ws.soap.client.SoapFaultClientException;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.ws.test.client.RequestMatchers.connectionTo;
import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;
import static org.springframework.ws.test.client.ResponseCreators.withServerOrReceiverFault;

@WebServiceClientTest(ExchangeRateSoapClient.class)
class ExchangeRateSoapClientTest {

    private static final String DESTINATION =
            "https://soap.partner.test/fx";

    private static final String USD_REQUEST = """
            <fx:GetRateRequest xmlns:fx="urn:example:fx">
              <fx:currency>USD</fx:currency>
            </fx:GetRateRequest>
            """;

    private static final String USD_RESPONSE = """
            <fx:GetRateResponse xmlns:fx="urn:example:fx">
              <fx:rate>1.25</fx:rate>
            </fx:GetRateResponse>
            """;

    @Autowired
    MockWebServiceServer server;

    @Autowired
    ExchangeRateSoapClient client;

    @BeforeEach
    void resetExpectations() {
        server.reset();
    }

    @Test
    void sendsExpectedPayloadToExpectedUri() {
        server.expect(connectionTo(DESTINATION))
                .andExpect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(USD_RESPONSE)));

        assertThat(client.getRate("USD"))
                .isEqualByComparingTo("1.25");

        server.verify();
    }

    @Test
    void mapsDifferentRateWithoutDependingOnWhitespace() {
        String eurRequest = """
                <fx:GetRateRequest xmlns:fx="urn:example:fx">
                  <fx:currency>EUR</fx:currency>
                </fx:GetRateRequest>
                """;
        String eurResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>0.9250</fx:rate>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(eurRequest)))
                .andRespond(withPayload(
                        new StringSource(eurResponse)));

        assertThat(client.getRate("EUR"))
                .isEqualByComparingTo("0.925");

        server.verify();
    }

    @Test
    void propagatesSoapServerFaultAsException() {
        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withServerOrReceiverFault(
                        "Partner temporarily unavailable",
                        Locale.ENGLISH));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(SoapFaultClientException.class)
                .hasMessageContaining("Partner temporarily unavailable");

        server.verify();
    }

    @Test
    void rejectsInvalidCurrencyBeforeSoapCall() {
        assertThatThrownBy(() -> client.getRate("US<"))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("three uppercase letters");

        // Không đăng ký expectation nào; verify() xác nhận
        // không còn request bắt buộc đang chờ.
        server.verify();
    }

    @Test
    void rejectsSuccessPayloadWithoutRate() {
        String invalidResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:status>OK</fx:status>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(invalidResponse)));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Expected exactly one rate element");

        server.verify();
    }

    @Test
    void rejectsNonNumericRate() {
        String invalidResponse = """
                <fx:GetRateResponse xmlns:fx="urn:example:fx">
                  <fx:rate>not-a-number</fx:rate>
                </fx:GetRateResponse>
                """;

        server.expect(payload(new StringSource(USD_REQUEST)))
                .andRespond(withPayload(
                        new StringSource(invalidResponse)));

        assertThatThrownBy(() -> client.getRate("USD"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Invalid SOAP rate response");

        server.verify();
    }
}
```

**Vì sao đây là test của client thật?**
- `ExchangeRateSoapClient` được Spring tạo là bean thật.
- `WebServiceTemplate` được client xây qua Boot builder thật (đã customizer để mock).
- `MockWebServiceServer` kiểm XML outbound, URI và tạo reply/fault theo kịch bản.
- `parseRate` thật chuyển XML response thành `BigDecimal`.
- Assertions xác minh kết quả domain/exception; không mock luôn client dưới test.

Với `@WebServiceClientTest`, các beans khác như repository hoặc service dùng database không cần xuất hiện. Điều này làm test rõ phạm vi và nhanh hơn full integration context trong các app lớn.

**Lưu ý `@BeforeEach server.reset()`:** Reset là phương pháp cô lập expectations khi Spring TestContext cache tái sử dụng cùng instance. Mỗi test vẫn gọi `server.verify()` để xác minh request đã thực thi. Với nhiều test classes dùng chung context, tổ chức suite để không chạy song song chia sẻ một mock server có mutable expectations nếu chưa có cấu hình cách ly.

### 8.6. ExchangeRateParseTest.java: unit test không cần Spring

`src/test/java/com/example/soaplab/ExchangeRateParseTest.java`:

```java
package com.example.soaplab;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ExchangeRateParseTest {

    @Test
    void parsesXmlWithDefaultNamespace() {
        String xml = """
                <GetRateResponse xmlns="urn:example:fx">
                  <rate>1.2500</rate>
                </GetRateResponse>
                """;

        assertThat(ExchangeRateSoapClient.parseRate(xml))
                .isEqualByComparingTo("1.25");
    }

    @Test
    void refusesUnexpectedNamespace() {
        String xml = """
                <GetRateResponse xmlns="urn:wrong:namespace">
                  <rate>1.25</rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("root or namespace");
    }

    @Test
    void refusesDtdAndExternalEntityPayload() {
        String xml = """
                <!DOCTYPE GetRateResponse [
                  <!ENTITY hidden SYSTEM "file:///etc/passwd">
                ]>
                <GetRateResponse xmlns="urn:example:fx">
                  <rate>&hidden;</rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Invalid SOAP rate response");
    }

    @Test
    void refusesEmptyRate() {
        String xml = """
                <GetRateResponse xmlns="urn:example:fx">
                  <rate></rate>
                </GetRateResponse>
                """;

        assertThatThrownBy(
                () -> ExchangeRateSoapClient.parseRate(xml))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("must not be empty");
    }
}
```

Các tests này không kiểm SOAP transport hoặc Spring Boot builder; chúng chỉ kiểm decoder XML. Tách chúng giúp tránh khởi động Spring context cho mọi edge case của response parser và chứng minh chức năng kiểm namespace, empty value, XXE.

### 8.7. Chạy các test

Tại thư mục `soap-client-test-lab`, có JDK 17+, Maven và dependency repository tương ứng:

```bash
mvn -q clean test

mvn -q -Dtest=ExchangeRateSoapClientTest test
mvn -q -Dtest=ExchangeRateParseTest test
```

Kiểm reports:

```text
target/surefire-reports/
```

Các lớp được thiết kế PASS theo contract trong bài. Nếu build không thành công, phải đọc log/compiler/root cause thực tế; không hứa một stdout giống nhau trên mọi máy. **Ví dụ không cần SOAP server đang chạy và không gửi request tới `https://soap.partner.test/fx` trong mock test.**

Có thể chạy application với:

```bash
mvn spring-boot:run
```

Tuy nhiên application demo **không có REST controller hay console runner tự động gọi SOAP**, nên chạy Boot chỉ khởi động context; không tự thực hiện `getRate`. Muốn thử tích hợp với đối tác thật, cần endpoint sandbox do đối tác cung cấp và test integration khác; không dùng địa chỉ ví dụ ở trên cho network test.

## 9. SOAPAction, headers và XSD: nâng dần mức kiểm chứng

### 9.1. Khi đối tác yêu cầu SOAPAction

Ví dụ production client gọi:

```java
template.sendSourceAndReceiveToResult(
        requestSource,
        new SoapActionCallback("urn:example:fx/GetRate"),
        responseResult);
```

Snippet này dùng biến `template`, `requestSource`, `responseResult` đã khai báo. `SoapActionCallback` đặt action theo contract, nhưng `payload(...)` chỉ so body, **không chứng minh action đã được gửi**.

Vì thế với đối tác cần SOAPAction, bổ sung matcher custom ở Spring-WS message level:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andExpect((uri, message) -> {
          if (!(message instanceof SoapMessage soap)) {
              throw new AssertionError("Expected SOAP message");
          }
          assertThat(soap.getSoapAction())
                  .contains("urn:example:fx/GetRate");
      })
      .andRespond(withPayload(
              new StringSource(USD_RESPONSE)));
```

Đây là **snippet mở rộng trong ExchangeRateSoapClientTest**; cần import `org.springframework.ws.soap.SoapMessage` và AssertJ. Dùng `contains` trong ví dụ để tránh phụ thuộc biểu diễn có thể có dấu quote của HTTP SOAPAction; khi cần exact contract, chuẩn hóa representation rồi assert exact, đồng thời kiểm SOAP version. Đừng ngộ nhận SOAPAction là `WS-Addressing Action`.

### 9.2. SOAP headers và WS-Security

Một client thực có thể thêm:
- WS-Security UsernameToken.
- Signed Timestamp.
- X.509 digital signature.
- WS-Addressing To/Action/MessageID.
- Correlation ID hoặc partner-specific SOAP headers.

`MockWebServiceServer` có thể kiểm một phần message/header qua `soapHeader`/custom RequestMatcher, nhưng mock server không tự chứng minh:
- Server thật xác minh chữ ký, certificate chain, timestamp clock skew.
- TLS mutual authentication hoạt động trên môi trường deployment.
- Credentials thực còn hiệu lực và quyền của tài khoản đối tác đúng.
- Proxy/load balancer không thay đổi SOAP envelope/HTTP headers.

Với những rủi ro này, cần integration/contract test dùng sandbox được cấp phép, có fake credentials, key/test truststore và logging đã redact. Không đưa passwords, private keys hoặc token thật vào test fixtures.

### 9.3. XSD validation

Nếu WSDL cung cấp `XSD` ổn định, lưu bản hợp đồng test trong `src/test/resources` và dùng `RequestMatchers.validPayload(...)` hoặc validator tương ứng để kiểm payload.

Ví dụ ý tưởng:

```java
// Minh họa: "schemas/fx.xsd" phải là XSD thật của đối tác
// và method signature phải chọn đúng overload của version Spring-WS.
Resource xsd = new ClassPathResource("schemas/fx.xsd");
server.expect(validPayload(xsd))
      .andRespond(withPayload(new StringSource(USD_RESPONSE)));
```

Đây là **mẫu tùy chọn** không thuộc runnable project ở mục 8 vì không kèm XSD của đối tác. Test XSD chỉ có nghĩa khi schema khớp namespace/element contract. Không lấy một XSD giả hoặc bỏ element bắt buộc để test xanh.

**SOAP body payload** có thể hợp lệ theo XSD nhưng SOAP headers/action vẫn sai. Ngược lại SOAPAction đúng không bảo đảm request XML hợp lệ. Kiểm từng rủi ro riêng.

### 9.4. Namespace-aware XPath

Khi phần tử có giá trị động (requestId, timestamp), so nguyên XML có thể khó bảo trì. Có thể dùng XPath matcher với namespace mapping hoặc tự kiểm DOM; tuyệt đối không bỏ namespace một cách vô thức.

**Ví dụ XPath về mặt ý tưởng:**

```xpath
/fx:GetRateRequest/fx:currency
```

XPath prefix `fx` trong expression phải được gắn namespace URI `urn:example:fx` trong evaluation context. Nếu bỏ namespace mapping, XPath có thể không tìm thấy node dù XML hợp lệ. Với một test có business constant như USD, `payload(...)` thường đơn giản và rõ hơn.

## 10. Kiểm các kịch bản lỗi SOAP

### 10.1. SOAP Fault

SOAP Fault là một thông điệp SOAP hợp lệ mô tả lỗi. Khi server mock trả:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withServerOrReceiverFault(
              "Partner temporarily unavailable",
              Locale.ENGLISH));
```

Theo cấu hình `WebServiceTemplate` mặc định, Spring-WS fault resolver thường phát `SoapFaultClientException`. Test nên kiểm exception và ý nghĩa lỗi, không chỉ giả định mọi Fault trả `null` hoặc `BigDecimal.ZERO`.

Nếu business layer muốn chuyển Fault thành exception riêng như `PartnerUnavailableException`, hãy đặt logic đó trong adapter và viết test xác minh mapping. Không tự retry SOAP Fault không idempotent nếu action có side effect.

### 10.2. Transport error khác SOAP Fault

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withError("Simulated transport failure"));
```

Đoạn này là **snippet minh họa**; Spring-WS có thể phát `WebServiceTransportException` tùy loại giả lập và cấu hình error handling. Đây không phải SOAP Fault XML và không chứng minh timeout thực kéo dài đúng N giây.

Với lỗi DNS/connection timeout/socket reset thật, một integration test ở network level hoặc transport abstraction test riêng sẽ đáng tin hơn. Unit/slice test chỉ cần chứng minh client xử lý exception phù hợp.

### 10.3. XML success response thiếu field

Nếu SOAP server gửi:

```xml
<fx:GetRateResponse xmlns:fx="urn:example:fx">
  <fx:status>OK</fx:status>
</fx:GetRateResponse>
```

Client không được tự coi đó là tỷ giá 0 hoặc “thành công” chỉ vì SOAP không có Fault. Runnable test `rejectsSuccessPayloadWithoutRate` bắt đúng điều này. Phân biệt:
- Message thuộc SOAP protocol nhưng **không có rate**.
- Message XML hợp lệ nhưng **sai business contract**.
- Không có response payload/one-way operation.
- Lỗi transport/timeout.
- SOAP Fault.

Những trường hợp này không nên bị gom thành cùng một `null` khó debug.

### 10.4. XML sai namespace

```xml
<GetRateResponse xmlns="urn:another:fx">
  <rate>1.25</rate>
</GetRateResponse>
```

Cùng local name nhưng namespace URI khác. Nếu API contract yêu cầu `urn:example:fx`, client phải reject hoặc dùng policy version compatibility được định nghĩa tường minh. Runnable `ExchangeRateParseTest` kiểm tình huống này để tránh parser dùng `getElementsByTagName("rate")` lấy nhầm element.

### 10.5. Response có nhiều rate elements

Nếu payload chứa hai `rate`, parser mẫu reject thay vì lấy phần tử đầu tiên. Với SOAP thực, số lượng có thể do schema quy định. Đừng tự chọn phần tử đầu khi contract nói đúng một; nếu response là danh sách, dùng model/collection có validation cardinality rõ.

### 10.6. SOAP request chưa được gửi

Một test có thể set expectation rồi chưa gọi client:

```java
server.expect(payload(new StringSource(USD_REQUEST)))
      .andRespond(withPayload(new StringSource(USD_RESPONSE)));

// Không gọi client.getRate("USD")
server.verify();  // Phải báo expectation chưa được sử dụng
```

Đây là **ví dụ test thất bại có chủ đích**, không thuộc runnable project. Nó minh họa vì sao `verify()` quan trọng: nếu chỉ tạo mock response mà không assert client call hoặc verify, một test có thể pass giả.

### 10.7. Client gửi sai destination URI

Nếu client đổi sang `https://wrong.partner.test/fx`, matcher `connectionTo("https://soap.partner.test/fx")` phải fail. Tuy nhiên nếu client dùng một destination provider, route routing logic, hoặc URI truyền trực tiếp mỗi request, expectation phải dựa vào hành vi cần kiểm, không hard-code production secret URL trong test. Với host cấu hình bằng property, dùng sandbox/placeholder property của test.

## 11. Khi client cần JAXB marshalling

### 11.1. Hướng contract-first

Với partner có WSDL/XSD, thường sinh Java classes từ schema rồi dùng `Jaxb2Marshaller`:

```java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.partner.generated");
marshaller.afterPropertiesSet();

WebServiceTemplate template = builder
        .setMarshaller(marshaller)
        .setUnmarshaller(marshaller)
        .setDefaultUri("https://soap.partner.test/fx")
        .build();
```

Đây là **snippet minh họa**, không thuộc project runnable ở mục 8: package `com.example.partner.generated` và JAXB generated classes phải tồn tại, dependencies JAXB tương thích cần được khai báo. Trong Spring Boot 3.x, JAXB namespaces thường là **`jakarta.xml.bind`**, không dùng Java `javax.xml.bind` cũ lẫn lộn.

Khi sử dụng JAXB, `marshalSendAndReceive(requestDto, new SoapActionCallback(...))` sẽ:
1. Dùng marshaller chuyển DTO thành XML payload.
2. Đóng gói payload vào SOAP Body và thêm SOAP headers/action.
3. Gửi qua configured sender.
4. Nhận SOAP response và unmarshal về DTO.
5. Xử lý Fault theo resolver.

`@WebServiceClientTest` vẫn dùng được nếu builder do Boot cung cấp đã được tùy chỉnh đúng. Matcher `payload(...)` là một cách kiểm XML thực sự tạo từ JAXB, giá trị cao hơn việc chỉ mock `WebServiceTemplate.marshalSendAndReceive(...)` rồi assert method được gọi.

### 11.2. Vì sao không mock hoàn toàn WebServiceTemplate trong mọi test?

Nếu test Mockito thuần viết:

```java
when(template.marshalSendAndReceive(any()))
        .thenReturn(new GetRateResponse());
```

Đoạn này chỉ là **snippet minh họa**, không có generated classes trong project. Nó có thể kiểm cách service xử lý response DTO nhưng **không chứng minh** request XML, namespace, JAXB annotations, SOAPAction, message sender hoặc fault resolver. Khi rủi ro chính nằm ở serialization/protocol, `MockWebServiceServer` tốt hơn.

Một hệ thống lớn có thể dùng cả hai tầng:
- Unit test business service mock SOAP adapter interface.
- SOAP client slice test dùng `MockWebServiceServer` để kiểm XML/headers/fault.
- Integration/contract test dùng sandbox của đối tác cho TLS/WSDL/security interoperability.

### 11.3. @ConfigurationProperties và marshaller beans trong slice

`@WebServiceClientTest` không tự scan mọi `@ConfigurationProperties` hoặc `@Configuration` của app. Nếu client constructor cần một properties class, có thể dùng `@EnableConfigurationProperties(PartnerSoapProperties.class)` cùng `properties=...` của slice. Nếu client cần marshaller bean do custom config cung cấp, dùng `@Import(TestMarshallerConfiguration.class)` hoặc một `@TestConfiguration` được include rõ.

Đừng đưa toàn bộ application config vào slice chỉ để có một properties bean: điều đó kéo DB/messaging dependencies và làm test chậm. Tránh hard-code private endpoint/credentials trong test; use mock URI và test-only values.

## 12. Khi nào dùng @SpringBootTest thay @WebServiceClientTest?

| Nhu cầu | Test slice | Full test / integration |
| --- | --- | --- |
| Client xây request XML đúng | `@WebServiceClientTest` phù hợp | Không cần full |
| Client đọc response và xử lý Fault | `@WebServiceClientTest` phù hợp | Full khi cần phối hợp policy nhiều tầng |
| Client có vài config/properties phụ trợ | Slice + `@Import`/`@EnableConfigurationProperties` | Full nếu graph phức tạp thật sự |
| Service + repository + SOAP adapter wiring thật | Slice không đủ phạm vi | `@SpringBootTest` với fake external dependencies |
| Spring Security/WS-Security interceptor trong app graph | Slice cần import config | Full/contract khi security là một phần trọng tâm |
| TLS/truststore/mTLS với partner sandbox | Mock server không kiểm | Network integration có kiểm soát |
| End-to-end xử lý SOAP endpoint do ứng dụng cung cấp | `@WebServiceServerTest` cho server slice | Full server integration |
| WSDL hiện tại của đối tác và XSD compatibility | Có thể validate bản contract đã lưu | Fetch/check sandbox khi có quyền và ổn định |

Spring Boot reference khuyến nghị `@WebServiceClientTest` cho SOAP client. `@SpringBootTest` không tự có mock server bean; nếu cần mock support trong full context, có thể thêm `@AutoConfigureMockWebServiceServer` khi dự án dùng builder theo đường tương thích, nhưng phải quản lý nhiều templates/customizers và context cache.

**Không** thêm `@WebServiceClientTest` đồng thời với `@SpringBootTest` trên một class để “vừa slice vừa full”. Chúng có bootstrap/auto-configuration semantics riêng; chọn một boundary và thêm test support đúng.

### 12.1. Hai client dùng hai template khác nhau

`@AutoConfigureMockWebServiceServer` mặc định cấu hình **một** mock server. Trong một app có nhiều SOAP clients với các templates, đừng giả định mọi template đều được chặn một cách độc lập bởi cùng server; khi cần kiểm nhiều clients, cấu hình từng mock server cho template cụ thể (ví dụ `MockWebServiceServer.createServer(template)`) hoặc tách test contexts/methods.

Nếu bạn gọi client A nhưng expectation cho client B, test fail; đừng “reset” tất cả để che logic routing sai. Với production cần route theo tenant, data center hoặc version, nên có test riêng xác minh destination selection.

### 12.2. WebServiceGatewaySupport

Legacy SOAP gateway có thể kế thừa `WebServiceGatewaySupport` thay vì inject builder. `MockWebServiceServer` có factory `createServer(WebServiceGatewaySupport)` và `createServer(WebServiceTemplate)` để test thủ công. Trong trường hợp đó, cần chọn cách gắn mock sender đúng đối tượng; chỉ thêm `@WebServiceClientTest` không bảo đảm test vô tình sử dụng template được tạo ngoài Boot builder.

### 12.3. Rest client vs SOAP client

`MockRestServiceServer` dùng cho REST client (`RestTemplate`/`RestClient`) với HTTP method/URI/JSON; `MockWebServiceServer` dùng cho Spring-WS SOAP `WebServiceTemplate` với XML/Envelope/Fault. Hai class có tên gần giống nhau nhưng không hoán đổi.

## 13. Các lỗi thường gặp và cách chẩn đoán

### 13.1. No qualifying bean of type MockWebServiceServer

**Nguyên nhân:**
- Dùng `@SpringBootTest` nhưng quên `@AutoConfigureMockWebServiceServer`.
- Dùng `@WebServiceServerTest` (server slice), không phải client slice.
- Thiếu `spring-ws-test` trên test classpath.
- Test không chạy qua Spring Boot TestContext / Spring Boot version không khớp.
- `@AutoConfigureMockWebServiceServer(enabled=false)` hoặc custom exclusions đã tắt support.

**Hướng xử lý:** Kiểm đúng annotation/package Boot 3.5; `spring-ws-test`; cấu hình test; tránh tự tạo một bean mock server không gắn template đúng chỉ để autowire thành công.

### 13.2. Client bean không được tìm thấy

`@WebServiceClientTest` chỉ load components được chọn theo scope. Nếu client nằm ngoài scan package hoặc `components` không đúng, Spring không tạo bean. Thêm `@WebServiceClientTest(MyClient.class)` hoặc `@Import(MyClient.class)` phù hợp. Nếu client còn phụ thuộc repositories/services khác, dùng `@MockitoBean` hoặc `@Import` collaborator cụ thể; không mở full scan bừa bãi.

### 13.3. No qualifying bean of type WebServiceTemplate

Client constructor inject trực tiếp template nhưng default Boot chỉ tạo builder. Dùng:

```java
@AutoConfigureWebServiceClient(registerWebServiceTemplate = true)
```

trong client test, hoặc cung cấp một `@Bean WebServiceTemplate` phù hợp nếu setup custom. Với client có nhiều named templates, dùng `@Qualifier` rõ ràng. Không đăng ký một template không có marshaller/URI rồi kết luận app SOAP call chạy đúng.

### 13.4. Mock server không nhận request, nhưng có connection refused

Nguyên nhân rất thường gặp: client tạo template bằng `new WebServiceTemplate()`, đã tạo template trước khi mock customizer gắn vào, hoặc inject một template không phải template được mock. Lỗi network cho thấy request có thể đã thoát ra transport thật.

Kiểm:
1. Constructor client nhận `WebServiceTemplateBuilder` do Spring cung cấp?
2. Template có phải builder-created object đúng lifecycle?
3. Mock server có được tạo/gắn vào chính instance `WebServiceTemplate` được sử dụng?
4. Có code tự override `setMessageSender` sau khi mock customizer cấu hình không?
5. Có nhiều templates/beans và client đang gọi nhầm template không?

Không sửa bằng cách bật internet cho CI hoặc gọi đối tác production trong test.

### 13.5. Mock request khác expected XML

Có thể do:
- Sai namespace URI dù local name giống nhau.
- Sai root element, field name hoặc schema order.
- XML marshalling thay đổi `@XmlElement`, `@XmlSchema`/JAXB package context.
- Prefix, whitespace hoặc attribute representation thay đổi cách XML comparator xem xét.
- SOAP Body chứa nhầm cả Envelope.
- Giá trị đầu vào khác do profile/property/clock.

Dùng XML-aware comparator và xem diff cẩn thận; chọn `xpath`/schema validation nếu payload có trường động. Không đổi expected theo actual một cách máy móc khi actual phá contract của đối tác.

### 13.6. SOAPAction đúng trong code nhưng partner trả lỗi

`SoapActionCallback` đặt action, nhưng đối tác có thể đòi:
- Một action URI khác đúng theo WSDL.
- SOAP 1.1 vs 1.2 header semantics.
- WS-Addressing Action riêng.
- Content-Type, authentication hoặc signed headers đúng policy.

Mock server test có thể kiểm client đã đặt action; chỉ sandbox integration mới chứng minh partner chấp nhận toàn bộ wire-level requirements.

### 13.7. server.verify() báo expectation chưa thực thi

Đọc xem client method có thực sự gọi `WebServiceTemplate` không; có return sớm, validation fail, circuit breaker open hoặc cache hit không? Một SOAP client method trả cached value có thể không phát request; điều này có thể hợp lệ theo contract nhưng test expectation phải khớp scenario. Không bỏ `verify` để tránh failure, hãy xác định path cần kiểm.

### 13.8. SOAP Fault bị coi là parse error

`WebServiceTemplate` thường dùng `FaultMessageResolver` để phát exception trước khi bạn parse success body. Nếu code client catch tất cả `Exception` và trả default rate 0, lỗi sẽ bị che; nên phân loại Fault vs transport vs invalid payload. Khi cần custom mapping, dùng exception cụ thể hoặc fault code/detail thay vì catch mù quáng.

### 13.9. Duplicate SOAP expectations khi test chạy song song

`MockWebServiceServer` lưu mutable expectations. Nếu hai test methods dùng cùng context/mock server và chạy song song, `reset`/`expect`/`verify` có thể can thiệp lẫn nhau. Tắt parallel tại những test đó hoặc cô lập contexts/mock server instances, không dùng một singleton mock với shared mutable expectation state mà không có isolation.

### 13.10. @WebServiceClientTest chậm do tải quá nhiều beans

Kiểm custom `@ComponentScan` trên root application, `@Import` lớn, client constructor kéo chuỗi dependencies và những auto-configuration được thêm không cần. Slice chỉ có ích nếu giữ ranh giới; để SOAP adapter chịu trách nhiệm SOAP mapping, và business service test riêng.

### 13.11. XML parser lỗi vì DTD hoặc external entity

Đây có thể là **đúng kỳ vọng bảo mật** nếu XML không đáng tin có DOCTYPE/XXE. Đừng tắt secure features để test “qua”. Nếu đối tác hợp lệ thật sự cần DTD, cần phân tích risk, cấu hình allowlist resolvers phù hợp, không để external entity resolution tùy ý.

### 13.12. JAXB có lỗi javax/jakarta

Spring Boot 3.x/Spring Framework 6 dùng Jakarta APIs hiện đại. Dự án dùng generated classes `javax.xml.bind.*` từ đời cũ có thể không tương thích `jakarta.xml.bind.*` runtime/marshaller. Sinh classes từ XSD bằng plugin JAXB Jakarta-compatible và kiểm Maven dependency tree; không pin bừa JAXB runtime versions xung đột Boot BOM.

### 13.13. Không tìm được XSD hoặc WSDL trong test

`ClassPathResource("schemas/partner.xsd")` chỉ thành công khi file có trong `src/test/resources/schemas/partner.xsd` hoặc đúng path classpath. Không tham chiếu WSDL qua URL production trong unit test nếu không cần. Nếu schema được versioned từ đối tác, lưu bản và checksum/version phù hợp; contract updates cần review.

### 13.14. Test Mockito PASS nhưng SOAP XML sai

Mock `WebServiceTemplate` trả sẵn DTO không kiểm marshaller/SOAP message. Cần thêm `MockWebServiceServer` test cho outbound wire-level XML contract; không coi unit test business logic thay thế client slice test.

### 13.15. Lỗi do endpoint cố định trong test

Nếu client dùng URI từ `partner.soap.uri` mà test không cung cấp property, builder có thể không có default URI; `sendSourceAndReceiveToResult(Source,Result)` yêu cầu một default URI. Cấp property từ `@WebServiceClientTest(properties="partner.soap.uri=https://...")` hoặc cấu hình bean test phù hợp. Đừng hard-code URI production chứa secret vào test sources.

## 14. Kiểm thử negative path và reliability

### 14.1. Input validation trước network

Trong project, `getRate("US<")` ném `IllegalArgumentException` trước khi build XML hoặc gọi template. Điều đó ngăn injection vào raw XML và giảm outbound request vô ích.

Tuy nhiên regex `[A-Z]{3}` chỉ kiểm hình dạng; nó vẫn chấp nhận mã ba chữ không có thật. Nếu domain yêu cầu danh sách ISO 4217 hợp lệ, kiểm whitelist/business rules riêng; đừng hứa regex chứng minh currency code tồn tại.

### 14.2. Retry và idempotency

Đối với SOAP **read-only** operation `GetRate`, retry khi lỗi transient có thể hợp lý; với SOAP **payment/create order** operations, retry mù quáng có thể tạo giao dịch trùng. Nếu áp dụng retry/circuit breaker:
- Test số lần call với mock expectations tương ứng.
- Phân loại lỗi nào retriable.
- Dùng idempotency key nếu partner hỗ trợ.
- Kiểm timeout và backoff với virtual time/test clock khi cần.
- Không suy từ `withError(...)` rằng TLS/network đã được kiểm thật.

Trong `MockWebServiceServer`, nhiều expectations thường được match theo thứ tự thiết lập. Nếu muốn test retry ba lần, khai báo các response/errors theo chuỗi và `verify()`; không dùng một expectation rồi mong nó nhận ba calls.

### 14.3. Circuit breaker và fallback

Nếu circuit breaker open, client có thể không gửi SOAP request. Khi đó một test kỳ vọng outbound call sẽ fail đúng; một test fallback nên **không** tạo expectation cho outbound, hoặc kiểm không có request bằng cơ chế instrument thích hợp. Đừng trộn testing logic của circuit breaker với SOAP payload structure vào một test khó hiểu.

### 14.4. Timeouts có nhiều tầng

Các tầng thời gian khác nhau:
- Connection timeout của HTTP message sender.
- Read/response timeout của message sender.
- Timeout của business operation/future.
- Timeout của test runner.

`@WebServiceClientTest` với mock sender kiểm logic mà **không chạy thời gian mạng thật**. Đặt timeout rất ngắn trong test không tự bảo đảm timeout production đúng; kiểm builder settings và thêm bounded integration test nếu cần.

### 14.5. Logging SOAP và dữ liệu nhạy cảm

SOAP body có thể chứa PII, số tài khoản, mã xác thực, SOAP security tokens. Khi test fail, không log tràn lan toàn bộ XML fixtures chứa secrets thật. Dùng dummy identifiers; redact Authorization/UsernameToken/Signature hoặc request body có dữ liệu riêng tư trước khi lưu CI artifacts.

## 15. Kế hoạch kiểm thử nhiều tầng cho một adapter SOAP

| Tầng | Công cụ | Kiểm chứng | Không kiểm chứng |
| --- | --- | --- | --- |
| Pure domain unit | JUnit/AssertJ | Quy tắc nghiệp vụ, rounding, validation | SOAP request/transport |
| XML parser/marshaller unit | JUnit + XML/JAXB | XML QName, schema fields, Java mapping | Destination URI/network |
| SOAP client slice | `@WebServiceClientTest + MockWebServiceServer` | Outbound request XML/URI/action, response/fault mapping | SOAP server thật, TLS |
| Full Spring wiring | `@SpringBootTest` + fake outbound | Nhiều bean, configuration và adapter phối hợp | Đối tác production thực |
| Contract với đối tác sandbox | HTTP/SOAP client thật, môi trường kiểm soát | TLS, auth, WSDL, policy và compatibility tại sandbox | Không bảo đảm production luôn giống sandbox |
| Production smoke/monitoring | Probe được cấp phép, không gây side effect | Availability cơ bản | Không thay thế test suite và không nên gửi payload nguy hiểm |

Không test side-effect SOAP payment/cancel order trên production trừ khi có môi trường và quyền rất rõ. Dùng sandbox/synthetic test accounts, correlation IDs và cleanup.

### 15.1. Khi nào nên kiểm SOAP Envelope hoàn chỉnh?

`payload(...)` đủ cho nhiều operation contract-first, nhưng không bao quát:
- SOAP 1.1 vs SOAP 1.2 namespace/Content-Type.
- SOAP headers với mustUnderstand/role.
- Attachments/MTOM.
- WS-Security signature/digest/canonicalization.
- WS-Addressing action/to/messageID.
- Transport-level authentication.

Nếu một trong các yếu tố này là rủi ro chính, bổ sung mock message matcher/header assertions và một số integration tests ở đúng tầng. Không yêu cầu mọi unit test phải xác minh toàn bộ Envelope byte-for-byte vì sẽ rất brittle và chậm.

### 15.2. Contract evolution và schema versioning

SOAP tích hợp lâu đời có thể thay namespace `v1` sang `v2`, WSDL thay operation name, đổi element order hoặc optional fields. Khi contract đổi:
1. So sánh WSDL/XSD cũ và mới.
2. Xác định các thay đổi breaking/additive theo schema.
3. Cập nhật JAXB generated sources nếu dùng.
4. Cập nhật request XML fixture theo version.
5. Tạo negative tests cho incompatibilities quan trọng.
6. Chạy slice test trước, sau đó sandbox compatibility test.

Mock server PASS với fixture cũ không thể biết đối tác đã deploy WSDL v2; nếu version drift là rủi ro, có cơ chế contract refresh/approval riêng.

## 16. Anti-pattern và phương án tốt hơn

| Anti-pattern | Hệ quả | Hướng đúng |
| --- | --- | --- |
| `new WebServiceTemplate()` trong client rồi dùng auto mock server | Mock có thể không intercept; gửi HTTP thật | Inject builder do Boot cung cấp hoặc createServer(template) chính xác |
| Dùng `@WebServiceServerTest` cho outbound client | Test endpoint phía server, sai boundary | `@WebServiceClientTest` |
| Mock luôn SOAP client đang test | Không kiểm request XML | Dùng client thật + MockWebServiceServer |
| Chỉ set `andRespond` mà không `verify` | Có thể bỏ sót request không được gọi | Assert kết quả và verify |
| So raw XML string | Fail vì prefix/whitespace không quan trọng | XML-aware payload/XPath/XSD |
| Chỉ assert payload, bỏ URL bắt buộc | Có thể gọi nhầm endpoint | Thêm `connectionTo` |
| Chỉ assert payload, bỏ SOAPAction/policy | Bỏ sót contract header | Custom header/action matcher hoặc sandbox test |
| Dùng real partner server trong `mvn test` | Flaky, chi phí mạng, nguy cơ dữ liệu thật | Mock server trong slice |
| Bật full app context cho mọi SOAP client test | DB/messaging phụ thuộc không liên quan | Slice + collaborators có chọn lọc |
| Bỏ qua SOAP Fault/timeout | Fallback/retry sai khi đối tác hỏng | Test fault + transport error |
| Dùng `String.format` cho XML input tự do | XML injection/malformed request | JAXB/XML writer hoặc escape đúng |
| Parse XML không chặn external entities | Rủi ro XXE | Secure parser + schema validation |
| Dùng JSONPath cho XML | Sai công cụ | XPath/XMLUnit/DOM |
| Đồng nhất SOAPAction với WS-Addressing | Header contract bị sai | Kiểm riêng theo WSDL/policy |
| Trộn JAXB `javax` và `jakarta` | Classloading/marshalling lỗi | Đồng bộ Jakarta APIs với Boot 3.x |
| Cho tests chạy song song cùng mock server | Mutable expectations đè nhau | Cô lập hoặc chạy tuần tự |

## 17. Bài tập thực hành

1. Tạo `@WebServiceClientTest(ExchangeRateSoapClient.class)` và inject `MockWebServiceServer`. Giải thích vì sao không cần chạy server đối tác.
2. Sửa fixture `USD_REQUEST` thành `EUR` nhưng vẫn gọi `client.getRate("USD")`. Quan sát XML matcher fail và lý do.
3. Dùng `connectionTo` kỳ vọng một URL khác; giải thích vì sao test phải fail dù response mock có thể được tạo.
4. Tạo response có namespace `urn:example:fx:v2`. Kiểm client parser phản ứng thế nào và đề xuất cách migrate version.
5. Tạo SOAP Fault với `withClientOrSenderFault` rồi so sánh exception với `withServerOrReceiverFault`.
6. Sửa client để nhận `WebServiceTemplate` trực tiếp, chạy slice và áp dụng `@AutoConfigureWebServiceClient(registerWebServiceTemplate=true)`.
7. Tạo một test có `@MockitoBean` cho một collaborator phụ của client; giải thích tại sao không nên import repository thật.
8. Bổ sung custom matcher kiểm `SoapMessage.getSoapAction()`. Phân biệt SOAPAction và WS-Addressing Action.
9. Thêm XSD vào `src/test/resources`; dùng `validPayload` theo đúng Spring-WS version để kiểm element và namespace.
10. Tạo hai expectations cho hai SOAP calls liên tiếp; kiểm thứ tự và `server.verify()`.
11. Mô phỏng transport error và quyết định exception nào được map thành lỗi business, lỗi nào nên retry.
12. Viết unit test parser cho response có `rate` trống, nhiều `rate`, sai QName, malformed XML, DOCTYPE.
13. Giải thích vì sao `@WebServiceClientTest` PASS không chứng minh truststore/mTLS của partner sandbox hoạt động.
14. Nếu SOAP client dùng JAXB generated classes, hãy kiểm request XML thực sự được marshalling bằng `payload(...)` thay vì chỉ mock `marshalSendAndReceive`.
15. So sánh `MockWebServiceServer` với `MockRestServiceServer`, `MockWebServiceClient` và `MockMvc` về boundary.

Đạt bài khi có thể mô tả chính xác **client/template/mock server/transport**, biết phân loại **payload/header/fault**, và viết test ổn định chỉ phụ thuộc dữ liệu fixtures.

## 18. Checklist trước khi merge

- [ ] Phiên bản Spring Boot/JDK/dependencies được xác định rõ, import `@WebServiceClientTest` đúng package?
- [ ] Test có `spring-ws-test` và `spring-boot-starter-web-services` tương ứng Boot 3.5?
- [ ] Client thật được chỉ định bằng `value`/`components` thay vì mock luôn SUT?
- [ ] Client được xây bằng `WebServiceTemplateBuilder` do Boot cung cấp?
- [ ] Nếu inject trực tiếp `WebServiceTemplate`, đã cân nhắc `registerWebServiceTemplate=true`?
- [ ] Test có `MockWebServiceServer` phù hợp với template đang được dùng?
- [ ] Outbound URI được kiểm nếu là contract?
- [ ] XML payload được kiểm namespace, root và business fields?
- [ ] SOAPAction/WS-Addressing headers được kiểm nếu partner yêu cầu?
- [ ] Response mapping từ XML/JAXB sang domain value được assert?
- [ ] SOAP Fault và transport error được tách thành kịch bản riêng?
- [ ] `server.verify()` được gọi, không bỏ qua unused expectations?
- [ ] Có test invalid input không gửi request không hợp lệ?
- [ ] Không dùng secrets/thông tin khách hàng thật trong XML test fixtures?
- [ ] Không gửi HTTP thật vào production trong unit/slice test?
- [ ] Không kéo DAO/DB/full app context vào SOAP client slice nếu không cần?
- [ ] Có kiểm XML schema/namespace version khi contract yêu cầu?
- [ ] Có dùng secure XML parsing và tránh XML injection?
- [ ] Concurrent test không chia sẻ mock server mutable expectations một cách nguy hiểm?
- [ ] Có tách test XML parser khỏi test SOAP transport để giảm context cost?
- [ ] Các kiểm thử integration sandbox được duy trì riêng cho TLS/WS-Security/interoperability?
- [ ] Đã chạy Maven tests và review failure thực trước khi chốt?

**Kết luận:** `@WebServiceClientTest` là **test slice dành riêng cho Spring-WS SOAP client** trong Spring Boot. Nó làm việc tốt nhất khi client tạo `WebServiceTemplate` từ Boot-provided `WebServiceTemplateBuilder` và test dùng `MockWebServiceServer` để kiểm outbound request XML/URI/header và giả lập response/fault. Kết hợp `server.verify()`, error-path tests và test parsing/XML schema sẽ tạo bộ test vừa cô lập, vừa bảo vệ contract SOAP quan trọng. Khi cần xác minh mTLS, SOAP endpoint thật hoặc tương thích WSDL của đối tác, thêm integration test với sandbox; đừng suy từ mock test PASS rằng network integration đã được kiểm.

## 19. Tài liệu chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications, Auto-configured Spring Web Services Client Tests: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Web Services, Calling Web Services with WebServiceTemplate: https://docs.spring.io/spring-boot/3.5/reference/io/webservices.html
- Spring Boot 3.5 Javadoc — WebServiceClientTest: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/WebServiceClientTest.html
- Spring Boot 3.5 Javadoc — AutoConfigureWebServiceClient: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/AutoConfigureWebServiceClient.html
- Spring Boot 3.5 Javadoc — AutoConfigureMockWebServiceServer: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/webservices/client/AutoConfigureMockWebServiceServer.html
- Spring Boot 3.5 Javadoc — WebServiceTemplateBuilder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/webservices/client/WebServiceTemplateBuilder.html
- Spring Boot 3.5 — Managed dependency coordinates (spring-ws-test, starter): https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html
- Spring Web Services — Reference, Client-side Testing / MockWebServiceServer: https://docs.spring.io/spring-ws/docs/4.0.10/reference/html/
- Spring Web Services — MockWebServiceServer API: https://www.springframework.org/spring-ws/docs/4.0.11/api/org/springframework/ws/test/client/MockWebServiceServer.html
- Spring Web Services — WebServiceTemplate API: https://docs.spring.io/spring-ws/docs/4.0.17/api/org/springframework/ws/client/core/WebServiceTemplate.html
- Spring Boot 4 migration guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
