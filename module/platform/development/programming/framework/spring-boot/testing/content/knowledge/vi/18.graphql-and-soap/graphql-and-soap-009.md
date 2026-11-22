# Spring Boot testing — @WebServiceServerTest và MockWebServiceClient theo phiên bản hỗ trợ

## 1. Bài toán: kiểm thử SOAP endpoint mà không phải mở HTTP server

Khi ứng dụng Spring Boot **cung cấp** SOAP Web Service bằng Spring Web Services (Spring-WS), chúng ta cần kiểm chứng một request XML có được chuyển tới đúng `@Endpoint`, đúng namespace, đúng business collaborator, và sinh ra response XML/SOAP đúng hợp đồng hay không.

Với REST, nhiều người quen `@WebMvcTest` + `MockMvc`. Với **SOAP server-side**, cặp công cụ tương ứng là:

- **`@WebServiceServerTest`:** test slice của Spring Boot tập trung vào các `@Endpoint`/`EndpointInterceptor` liên quan Spring-WS.
- **`MockWebServiceClient`:** client giả lập gửi SOAP message tới Spring-WS `MessageDispatcher` **trong Spring context**, không gọi HTTP socket thật.
- **`RequestCreators`:** tạo SOAP request từ phần XML **payload** (thường bằng `StringSource` hoặc resource).
- **`ResponseMatchers`:** kiểm tra response payload, SOAP Fault, XPath, schema XSD hoặc SOAP header.

Một câu test điển hình:

```java
client.sendRequest(
          RequestCreators.withPayload(
              new StringSource("<g:GreetRequest xmlns:g='urn:demo:greeting:v1'>...</g:GreetRequest>")))
      .andExpect(ResponseMatchers.noFault())
      .andExpect(ResponseMatchers.payload(expectedPayload));
```

Đoạn trên chỉ minh họa API, chưa có đầy đủ payload và các biến. Project Java 17 **runnable** ở mục 9–13 sẽ bao gồm mọi file, imports và dependency.

### Mục tiêu học tập

1. Phân biệt Spring-WS SOAP **server tests** với SOAP **client tests** và Spring GraphQL tests.
2. Chọn dependency, package annotation phù hợp **Spring Boot 3.5** so với **Spring Boot 4**.
3. Hiểu `@Endpoint` + `@PayloadRoot` + `@RequestPayload` + `@ResponsePayload`.
4. Dùng `MockWebServiceClient` assert **namespace**, nội dung XML, escaping và XSD.
5. Dùng `@MockitoBean` cho service collaborator khi test slice không quét bean thông thường.
6. Hiểu cách test SOAP Fault, SOAP 1.1/1.2, headers, SOAPAction và WS-Security khi có yêu cầu.
7. Khi cần full application wiring, chuyển sang `@SpringBootTest + @AutoConfigureMockWebServiceClient`.
8. Khi cần wire-level HTTP, TLS, WSDL endpoint hoặc gateway, chuyển sang **real HTTP integration test**.
9. Tránh các test “xanh giả” vì gửi sai namespace, chỉ assert non-null, hoặc lẫn server/client mock.

## 2. Chọn đúng công cụ: SOAP, GraphQL, REST hay SOAP outbound?

| Ứng dụng đang làm gì? | API hoặc annotation test | Mô phỏng gì? | Bằng chứng |
| --- | --- | --- | --- |
| **Cung cấp SOAP endpoint Spring-WS** | `@WebServiceServerTest` + `MockWebServiceClient` | SOAP request đến Spring-WS dispatcher trong context | Mapping theo payload QName, XML response/fault |
| **Gọi SOAP endpoint ở hệ thống ngoài** | `@WebServiceClientTest` + `MockWebServiceServer` | SOAP server ở **phía ngoài** trả giả định cho `WebServiceTemplate` | Client tạo XML request và parse response đúng |
| Cung cấp REST/MVC controller | `@WebMvcTest` + `MockMvc` | Servlet MVC request | HTTP mapping/status/JSON |
| Cung cấp GraphQL resolver | `@GraphQlTest` + `GraphQlTester` | GraphQL execution | Query/mutation schema, data và GraphQL errors |
| Full Spring-WS application wiring | `@SpringBootTest` + `@AutoConfigureMockWebServiceClient` | Full context nhưng SOAP dispatcher vẫn được mock-bound | Endpoint + service/config beans thực |
| SOAP qua HTTP socket thật | `@SpringBootTest(RANDOM_PORT)` + HTTP/SOAP client thật | Embedded server + `MessageDispatcherServlet` | URL, SOAP envelope, Content-Type, HTTP status |
| WSDL/XSD/WS-Security contract deployment | Integration test có schema, cert, proxy, gateway | Hạ tầng tương ứng | Compatibility và security trên môi trường thật |

Điểm cần nhấn mạnh: **`MockWebServiceClient` khác `MockWebServiceServer`.**

- `org.springframework.ws.test.server.MockWebServiceClient` dùng để **test server endpoint** của ứng dụng.
- `org.springframework.ws.test.client.MockWebServiceServer` dùng để **mock server** phục vụ ứng dụng của ta đóng vai **SOAP client**.
- Hai class đều đến từ artifact `org.springframework.ws:spring-ws-test`, nhưng package, API và hướng mô phỏng ngược nhau.

`MockWebServiceClient` không phải một HTTP client có base URL hay port; request có thể được dispatch trực tiếp đến endpoint mà không mở Tomcat/Jetty/Netty. Một test PASS với nó **chưa chứng minh** route URL `/services`, network, TLS, HTTP headers hoặc gateway production.

## 3. Version support — phần bắt buộc phải xác minh trước khi copy import

### 3.1. Spring Boot 3.5.x

Test annotation:

```java
import org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest;
import org.springframework.boot.test.autoconfigure.webservices.server.AutoConfigureMockWebServiceClient;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Các dependencies Maven thường dùng:

```xml
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
```

- `spring-boot-starter-web-services` có dấu gạch giữa `web` và `services` trong **dòng Boot 3.x**.
- `spring-ws-test` đưa `MockWebServiceClient`, `RequestCreators`, `ResponseMatchers` vào test classpath; khai báo **tường minh** để ví dụ không phụ thuộc một starter khác vô tình kéo transitively.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Boot test và Mockito.
- `@WebServiceServerTest` có từ **Spring Boot 2.6**; nếu dự án dùng phiên bản cũ hơn, cần dựng Spring test context và `MockWebServiceClient.createClient(...)` thủ công (xem mục 16).
- `@MockitoBean` đến từ **Spring Framework 6.2+**, phù hợp Boot 3.4/3.5. `@MockBean` cũ của Boot bị deprecated từ 3.4; với Boot 3.5 nên viết ví dụ mới bằng `@MockitoBean`.

**Không** dùng `org.springframework.boot.webservices.test.autoconfigure...` trong project 3.5: đó là package thuộc cấu trúc modular của Boot 4.

### 3.2. Spring Boot 4.x

Các test infrastructure modules được tách theo công nghệ:

```java
import org.springframework.boot.webservices.test.autoconfigure.server.WebServiceServerTest;
import org.springframework.boot.webservices.test.autoconfigure.server.AutoConfigureMockWebServiceClient;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

Tên starters trong Boot 4:

```xml
<!-- Đoạn cấu hình định hướng Boot 4; không ghép vào POM Boot 3.5. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webservices</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webservices-test</artifactId>
    <scope>test</scope>
</dependency>
```

- Tên `spring-boot-starter-webservices` **không** có dấu gạch giữa `web` và `services`.
- `spring-boot-starter-webservices-test` là focused test starter Boot 4, hỗ trợ Spring Web Services test.
- Annotation chuyển package từ `org.springframework.boot.test.autoconfigure.webservices.server` sang `org.springframework.boot.webservices.test.autoconfigure.server`.
- `MockWebServiceClient`, `RequestCreators`, `ResponseMatchers` vẫn ở namespace Spring-WS `org.springframework.ws.test.server`.
- Chọn parent/BOM và dependencies theo **cùng major version**; không ghép POM Boot 3.5 với một Boot 4 test starter.
- Spring Boot 4 còn có module `spring-boot-webservices-test`; với dự án Maven phổ thông, dùng focused starter thay vì tự ghép nhiều module thiếu dependency.

**Phiên bản 2.5 trở về trước:** `@WebServiceServerTest` chưa được cung cấp như Boot 2.6+, nên không thể import chỉ bằng cách thêm `spring-ws-test`. Trong trường hợp đó dùng `@SpringJUnitConfig`/`@ContextConfiguration` với cấu hình Spring-WS phù hợp, sau đó gọi `MockWebServiceClient.createClient(context)` nếu cần duy trì legacy project.

### 3.3. Bảng tra cứu nhanh

| Dòng Boot | Annotation server test | Test dependencies | Mocking collaborator |
| --- | --- | --- | --- |
| Boot 2.5 trở về trước | Không có slice `@WebServiceServerTest` kiểu 2.6+ | `spring-ws-test` + Spring test, cấu hình thủ công | Mockito `@Mock`/bean test hoặc công cụ theo version |
| Boot 2.6–3.3 | `org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest` | Starter test + `spring-ws-test` | `@MockBean` nếu dòng đó hỗ trợ |
| Boot 3.4–3.5 | Cùng package 3.x | `spring-boot-starter-test` + `spring-ws-test` | Ưu tiên `@MockitoBean` |
| Boot 4.x | `org.springframework.boot.webservices.test.autoconfigure.server.WebServiceServerTest` | `spring-boot-starter-webservices-test` | `@MockitoBean` |

Khi project lỗi `package ...WebServiceServerTest does not exist`, trước tiên xem **Boot parent/BOM, dependencies, package**; không thử đoán bằng cách trộn imports của hai dòng. Nếu starter POM có artifact name khác phiên bản, kiểm tra dependency tree và tài liệu tham chiếu đúng version.

## 4. Cơ chế SOAP endpoint và những gì slice thực sự kiểm tra

Spring Web Services dùng **payload root QName** để chọn endpoint. Một QName gồm **namespace URI** và **local name**:

```xml
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Ở đây:

- Namespace URI = `urn:demo:greeting:v1`.
- Local name = `GreetRequest`.
- Prefix `g` là cú pháp rút gọn của XML document; đổi thành `x` nhưng giữ **cùng namespace URI** sẽ không đổi QName.
- `g:name` là child element thuộc **cùng namespace**, khác với `<name>` không có namespace.

Một endpoint:

```java
@Endpoint
public class GreetingEndpoint {
    @PayloadRoot(
        namespace = "urn:demo:greeting:v1",
        localPart = "GreetRequest")
    @ResponsePayload
    public Element greet(@RequestPayload Element payload) {
        // Tạo XML response.
    }
}
```

Spring-WS `MessageDispatcher` xác định method theo `@PayloadRoot`, chuyển request payload thành `org.w3c.dom.Element` (hoặc JAXB/Source type phù hợp), và ghi return value có `@ResponsePayload` vào SOAP Body.

**Không dùng `@RestController`/`@PostMapping` để thay `@Endpoint`/`@PayloadRoot` trong một SOAP contract-first server test.** Spring MVC và Spring-WS có mô hình mapping/serialization khác nhau, dù có thể cùng chạy trong Servlet container.

### @WebServiceServerTest chọn những bean gì?

`@WebServiceServerTest(GreetingEndpoint.class)` cấu hình phần Spring-WS server phục vụ endpoint test và tự tạo `MockWebServiceClient`. Nó giới hạn scanning ở các components phù hợp (đặc biệt `@Endpoint` và `EndpointInterceptor`), không tự tải toàn bộ repository/service/controller/broker của ứng dụng.

Hệ quả thực tế:

- Endpoint constructor phụ thuộc `GreetingService` thì test slice phải cung cấp collaborator đó bằng `@MockitoBean` hoặc `@Import` một config/bean test.
- Không nên thêm `@SpringBootTest` vào **cùng class** với `@WebServiceServerTest`: hai kiểu bootstrap không cùng mục tiêu.
- Nếu muốn bean thật và toàn bộ auto-config, dùng `@SpringBootTest + @AutoConfigureMockWebServiceClient` (mục 13).
- Slice không bảo đảm URL/Servlet HTTP bên ngoài; nếu yêu cầu thật là `/ws/*` hay `/services`, cần real HTTP integration riêng.
- Một mock business service trả kết quả đúng không chứng minh truy cập database hay SOAP outbound call hoạt động.

### Quy trình của MockWebServiceClient

```mermaid
flowchart LR
    A[JUnit test] --> B[RequestCreators.withPayload]
    B --> C[MockWebServiceClient]
    C --> D[MessageDispatcher trong Spring context]
    D --> E[Endpoint mapping theo QName]
    E --> F[@Endpoint method]
    F --> G[Mock hoặc bean thật]
    G --> H[Spring-WS response message]
    H --> I[ResponseMatchers: payload, XSD, XPath, Fault]
```

**Không có HTTP socket** trong chuỗi này. Dữ liệu đi qua Spring-WS message processing, không đi qua browser hay remote SOAP service.

## 5. Phân biệt XML payload và SOAP envelope

Một SOAP 1.1 message đầy đủ có dạng:

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Header/>
    <soap:Body>
        <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
            <g:name>Lan</g:name>
        </g:GreetRequest>
    </soap:Body>
</soap:Envelope>
```

Nhưng `RequestCreators.withPayload(new StringSource(...))` **chỉ cần phần payload**:

```xml
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Spring-WS test message factory tạo SOAP message/envelope và chèn payload vào body. Nếu nhét nguyên `<soap:Envelope>` vào `withPayload`, SOAP Envelope sẽ bị coi là **payload root**, gây mapping sai (hoặc một SOAP message lồng envelope). Đây là lỗi rất phổ biến.

| Thứ test | Matcher phù hợp | Cần chú ý |
| --- | --- | --- |
| XML payload root/children | `ResponseMatchers.payload(Source)` | Namespace URI/QName và giá trị phải đúng |
| XML child node/value | `ResponseMatchers.xpath(...)` | Namespace map cần đúng; tránh phụ thuộc prefix |
| SOAP 1.1/1.2 envelope | `ResponseMatchers.soapEnvelope(...)` | Kiểm tra đúng SOAP version và headers nếu contract yêu cầu |
| SOAP header tồn tại | `ResponseMatchers.soapHeader(QName)` | Không tự chứng minh chữ ký/WS-Security hợp lệ |
| Payload hợp lệ theo XSD | `ResponseMatchers.validPayload(Resource)` | XSD đã thực sự được nạp, đúng targetNamespace |
| Không có SOAP Fault | `ResponseMatchers.noFault()` | Chỉ loại trừ SOAP Fault, chưa chứng minh payload đúng |
| Fault từ client/sender | `ResponseMatchers.clientOrSenderFault()` | Cần exception-to-fault mapping đúng |
| Fault từ server/receiver | `ResponseMatchers.serverOrReceiverFault()` | Tùy resolver và SOAP version |

`ResponseMatchers.payload` so sánh XML payload theo XML semantics/matcher, không phải so sánh HTTP status 200 hay raw JSON. `noFault` có thể PASS kể cả payload sai, vì thế nên **chaining ít nhất hai matcher**.

### Chú ý SOAP 1.1 và SOAP 1.2

- SOAP 1.1 dùng namespace envelope `http://schemas.xmlsoap.org/soap/envelope/` và thường `Content-Type: text/xml` trên HTTP.
- SOAP 1.2 dùng namespace `http://www.w3.org/2003/05/soap-envelope` và thường `Content-Type: application/soap+xml`.
- Fault code SOAP 1.1 `Client`/`Server` tương ứng với SOAP 1.2 `Sender`/`Receiver` trong các matchers Spring-WS.
- `MockWebServiceClient` test message factory đang cấu hình; **không tự chứng minh** HTTP client/proxy bên ngoài negotiation đúng SOAP 1.1/1.2.
- Nếu production contract quy định SOAPAction, MIME attachments, WS-Addressing hoặc WS-Security, thêm test riêng thay vì chỉ so sánh payload XML.

## 6. Cách tạo request và kiểm tra response

Cách ngắn nhất:

```java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

// Trong một test đã inject MockWebServiceClient client:
client.sendRequest(
          RequestCreators.withPayload(
              new StringSource(requestXml)))
      .andExpect(ResponseMatchers.noFault())
      .andExpect(ResponseMatchers.payload(
              new StringSource(expectedResponseXml)));
```

Đây là **trích đoạn** cần biến `requestXml`, `expectedResponseXml` và client đã cấu hình.

### Với XPath

```java
client.sendRequest(RequestCreators.withPayload(
        new StringSource(requestXml)))
      .andExpect(
          ResponseMatchers.xpath(
                  "/g:GreetResponse/g:message",
                  Map.of("g", "urn:demo:greeting:v1"))
              .evaluatesTo("Xin chào, Lan"));
```

XPath dùng namespace mapping do test cung cấp. Đừng dùng XPath không khai namespace để tìm một element thuộc namespace khác rỗng, vì XPath mặc định có thể không match như bạn tưởng. Hoặc có thể dùng `local-name()` và `namespace-uri()` khi muốn assert namespace không phụ thuộc tiền tố.

### Với XSD

```java
client.sendRequest(RequestCreators.withPayload(
        new StringSource(requestXml)))
      .andExpect(ResponseMatchers.validPayload(
              new ClassPathResource("greeting.xsd")));
```

XSD validation ở response giúp bắt lỗi cấu trúc/ký tự/nested elements. Nó không thay kiểm chứng business value: schema cho phép một string bất kỳ thì response `"sai tên"` vẫn có thể đúng XSD. Dùng **cả `payload`/`xpath` và `validPayload`** khi schema là contract bắt buộc.

### Khi nào nên kiểm tra raw SOAP envelope?

Chỉ so sánh `soapEnvelope` khi contract yêu cầu SOAP header/mustUnderstand/fault code hoặc SOAP version cụ thể. Với thông điệp nghiệp vụ, việc so sánh payload thường rõ ràng và ít phụ thuộc vào serialization format hơn.

## 7. SOAP Fault: cần cấu hình resolver, không mặc định “mọi exception đều là Client Fault”

SOAP Fault là phản hồi lỗi **ở tầng SOAP**; HTTP status có thể khác theo SOAP version và transport. Một lỗi business input như thiếu tên có thể được ánh xạ thành Client/Sender Fault, còn lỗi server bất ngờ thành Server/Receiver Fault.

Ví dụ matcher:

```java
client.sendRequest(
        RequestCreators.withPayload(
                new StringSource(invalidRequestXml)))
      .andExpect(ResponseMatchers.clientOrSenderFault());
```

Đây là **trích đoạn minh họa**, chỉ đúng khi ứng dụng đã cấu hình exception-to-SOAP-Fault mapping (ví dụ `SoapFaultAnnotationExceptionResolver`, `SoapFaultMappingExceptionResolver`, hoặc resolver riêng), và payload sai đã đi tới đoạn code/resolver tương ứng.

**Không đoán:** một `IllegalArgumentException` tùy framework/resolver/config có thể thành Server/Receiver fault, không phải luôn Client/Sender. Nếu muốn chính xác, khai báo một loại domain exception riêng và cấu hình mapping ổn định; sau đó test fault code, reason text, detail structure và không leak stack trace.

### Một cách cấu hình fault theo annotation

Đoạn định hướng (cần imports và integration vào Spring context):

```java
@SoapFault(
        faultCode = FaultCode.CLIENT,
        faultStringOrReason = "Invalid greeting request")
public class InvalidGreetingRequestException
        extends RuntimeException {
    public InvalidGreetingRequestException() {
        super("invalid greeting");
    }
}
```

Để annotation này thực sự có hiệu lực, cần có Spring-WS resolver như `SoapFaultAnnotationExceptionResolver` đăng ký trong context và thứ tự resolver không làm mất mapping. Nếu không, test chỉ có annotation trên class chưa thể bảo đảm Client Fault.

**Không dùng HTTP REST `@RestControllerAdvice` như một giả định xử lý SOAP faults:** SOAP endpoint dispatch/exception resolution đi qua Spring-WS, không đồng nhất với MVC controller exception resolver.

### Fault không thay XSD/schema tests

Một request thiếu element `<g:name>` vẫn có thể tới endpoint và gây runtime exception nếu server **không** bật schema validation inbound. Chỉ định XSD trong `ResponseMatchers.validPayload` kiểm tra **response**, không tự cấu hình validation cho **incoming request**. Để xác minh inbound validation, cần cấu hình interceptor như `PayloadValidatingInterceptor` hoặc cơ chế validation khác rồi test invalid request và fault đúng.

## 8. Cách kiểm tra namespace: URI mới là định danh, không phải prefix

Ba payload này có ý nghĩa khác nhau:

```xml
<!-- 1. Đúng namespace -->
<g:GreetRequest xmlns:g="urn:demo:greeting:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

```xml
<!-- 2. Vẫn đúng namespace dù prefix thay đổi -->
<x:GreetRequest xmlns:x="urn:demo:greeting:v1">
    <x:name>Lan</x:name>
</x:GreetRequest>
```

```xml
<!-- 3. Sai namespace URI, nên không trùng @PayloadRoot -->
<g:GreetRequest xmlns:g="urn:demo:other:v1">
    <g:name>Lan</g:name>
</g:GreetRequest>
```

Test nên có một happy path với prefix khác nhau và cùng namespace, để tránh logic phụ thuộc text `"g:"`. Trường hợp namespace sai thường khiến không tìm được endpoint mapping; đó không phải một request “hợp lệ nhưng response sai”, và test cần xác định exception/fault mapping theo cấu hình thực tế.

Nếu dùng JAXB code generation từ XSD, namespace, `elementFormDefault`, local name và root element annotations cần thống nhất giữa schema và DTO classes. Với DOM như bài mẫu, `getElementsByTagNameNS` có thể đọc đúng field theo namespace thay vì tìm bằng prefix string.

## 9. Dự án Maven/Java 17 hoàn chỉnh (Spring Boot 3.5)

Ví dụ này có một **SOAP greeting endpoint** và một business service:

- `GreetRequest` chứa một `name`.
- `GreetingService.greet(name)` tạo nội dung `"Xin chào, <name>"` (trim whitespace).
- `GreetResponse` chứa một `message`.
- `@WebServiceServerTest` mock service để kiểm tra routing/XML contract.
- `@SpringBootTest + @AutoConfigureMockWebServiceClient` dùng service thật để kiểm tra wiring nhưng vẫn **không gọi HTTP socket**.
- XSD test schema xác nhận response XML có dạng mong muốn.

Không dùng JAXB classes trong project này: Spring-WS cho phép `org.w3c.dom.Element` làm request/response payload, phù hợp bài học về test client/namespace mà không cần code generator.

### 9.1. Cây tệp

```text
soap-slice-demo/
├── pom.xml
└── src/
    ├── main/java/example/soapdemo/
    │   ├── SoapDemoApplication.java
    │   ├── GreetingService.java
    │   └── GreetingEndpoint.java
    └── test/
        ├── resources/greeting.xsd
        └── java/example/soapdemo/
            ├── GreetingEndpointSliceTest.java
            ├── GreetingEndpointFullContextTest.java
            └── GreetingServiceUnitTest.java
```

### 9.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>soap-slice-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
</project>
```

Spring Boot parent/BOM quản lý version của Spring-WS, JUnit, Mockito và Spring Framework. Không tự chọn `spring-ws-test` version thuộc major Spring-WS khác với `spring-ws-core` mà Boot quản lý.

### 9.3. SoapDemoApplication.java

`src/main/java/example/soapdemo/SoapDemoApplication.java`:

```java
package example.soapdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SoapDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SoapDemoApplication.class, args);
    }
}
```

Spring Boot tự cấu hình một số Spring-WS infrastructure khi starter có mặt. Để cung cấp WSDL trên HTTP trong ứng dụng thực, bạn còn cần schema/WSDL definitions và endpoint URL mapping phù hợp với contract; test slice bài này **không tự tạo hay kiểm tra WSDL publication**.

### 9.4. GreetingService.java

`src/main/java/example/soapdemo/GreetingService.java`:

```java
package example.soapdemo;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank");
        }
        return "Xin chào, " + name.strip();
    }
}
```

Test slice sẽ thay service bằng `@MockitoBean`. Full-context test sẽ dùng service thực. Cách phân lớp này giúp tránh lỗi “tôi chỉ thấy XML response nên tưởng business logic đã được test”.

### 9.5. GreetingEndpoint.java

`src/main/java/example/soapdemo/GreetingEndpoint.java`:

```java
package example.soapdemo;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class GreetingEndpoint {

    static final String NAMESPACE = "urn:demo:greeting:v1";

    private final GreetingService service;

    public GreetingEndpoint(GreetingService service) {
        this.service = service;
    }

    @PayloadRoot(
            namespace = NAMESPACE,
            localPart = "GreetRequest")
    @ResponsePayload
    public Element greet(@RequestPayload Element request)
            throws ParserConfigurationException {

        NodeList names = request.getElementsByTagNameNS(
                NAMESPACE, "name");

        if (names.getLength() != 1) {
            throw new IllegalArgumentException(
                    "exactly one name element required");
        }

        String greeting = service.greet(
                names.item(0).getTextContent());

        // Tạo DOM response mới, không parse XML không đáng tin.
        Document document = DocumentBuilderFactory
                .newInstance()
                .newDocumentBuilder()
                .newDocument();

        Element response = document.createElementNS(
                NAMESPACE, "g:GreetResponse");
        document.appendChild(response);

        Element message = document.createElementNS(
                NAMESPACE, "g:message");
        message.setTextContent(greeting);
        response.appendChild(message);

        return response;
    }
}
```

Điểm cần nhớ:

- `@Endpoint` đánh dấu class là endpoint của Spring-WS.
- `@PayloadRoot` chọn method theo QName `{urn:demo:greeting:v1}GreetRequest`.
- `@RequestPayload Element` nhận **root element của SOAP Body payload**, không phải `SOAP Envelope`.
- `@ResponsePayload` ghi Element trả về thành payload XML trong SOAP response.
- `getElementsByTagNameNS` dùng **namespace URI** và local name, không phụ thuộc prefix g/x.
- `setTextContent` xử lý nội dung như **text node**, nên dấu `&` sẽ được XML serializer escape đúng; không dùng string concatenation của XML để tránh injection.
- `DocumentBuilderFactory.newDocumentBuilder().newDocument()` **chỉ tạo** DOM trống; đoạn này không parse tài liệu từ nguồn không tin cậy. Nếu sau này parse XML bên ngoài, cần cấu hình XML parser phòng XXE/DTD và giới hạn tài nguyên riêng.

Việc ném `IllegalArgumentException` ở nhánh thiếu `name` chưa được ánh xạ Client Fault riêng trong ví dụ. Để test HTTP/SOAP fault “đầu vào sai” có contract ổn định, thêm exception resolver trước khi viết assertions về loại fault; xem mục 7 và 15.

### 9.6. greeting.xsd

`src/test/resources/greeting.xsd`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:g="urn:demo:greeting:v1"
    targetNamespace="urn:demo:greeting:v1"
    elementFormDefault="qualified">

    <xs:element name="GreetRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="name" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GreetResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="message" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

</xs:schema>
```

Đặt `elementFormDefault="qualified"` nghĩa là các child elements như `g:name` và `g:message` cũng thuộc namespace `urn:demo:greeting:v1`. XML `<name>Lan</name>` không namespace sẽ **không đúng XSD** này.

XSD ở `src/test/resources` được test load qua `ClassPathResource("greeting.xsd")`. Để công bố WSDL thực tế trong production, schema nên được đặt vào cấu trúc resource/config của ứng dụng và version theo contract; không coi việc test có XSD là server đã public WSDL.

## 10. @WebServiceServerTest: kiểm tra SOAP endpoint slice

`src/test/java/example/soapdemo/GreetingEndpointSliceTest.java`:

```java
package example.soapdemo;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoMoreInteractions;
import static org.mockito.Mockito.when;

import java.io.IOException;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.server.WebServiceServerTest;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@WebServiceServerTest(GreetingEndpoint.class)
class GreetingEndpointSliceTest {

    private static final String NS = "urn:demo:greeting:v1";

    @Autowired
    MockWebServiceClient client;

    @MockitoBean
    GreetingService service;

    @Test
    void routesSoapPayloadAndReturnsExpectedXml() {
        when(service.greet("Lan"))
                .thenReturn("Xin chào, Lan");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>Lan</g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Xin chào, Lan</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));

        verify(service).greet("Lan");
        verifyNoMoreInteractions(service);
    }

    @Test
    void prefixDoesNotChangeNamespaceMapping() {
        when(service.greet("Minh"))
                .thenReturn("Xin chào, Minh");

        // Prefix x khác g, nhưng namespace URI giống nhau.
        String request = """
            <x:GreetRequest xmlns:x="urn:demo:greeting:v1">
                <x:name>Minh</x:name>
            </x:GreetRequest>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.xpath(
                      "/g:GreetResponse/g:message",
                      Map.of("g", NS))
                      .evaluatesTo("Xin chào, Minh"));

        verify(service).greet("Minh");
    }

    @Test
    void xmlSpecialCharactersAreEscapedAsData() {
        when(service.greet("An & Binh"))
                .thenReturn("Xin chào, An & Binh");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>An &amp; Binh</g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Xin chào, An &amp; Binh</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));

        verify(service).greet("An & Binh");
    }

    @Test
    void responsePayloadConformsToXsd() throws IOException {
        when(service.greet("Linh"))
                .thenReturn("Xin chào, Linh");

        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>Linh</g:name>
            </g:GreetRequest>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.validPayload(
                      new ClassPathResource("greeting.xsd")))
              .andExpect(ResponseMatchers.xpath(
                      "/g:GreetResponse/g:message",
                      Map.of("g", NS))
                      .evaluatesTo("Xin chào, Linh"));

        verify(service).greet("Linh");
    }
}
```

**Có 4 JUnit methods** trong slice test. Hành vi được chứng minh:

1. SOAP request payload đúng QName được dispatch tới `GreetingEndpoint`.
2. Service mock được gọi đúng argument; XML response có namespace và payload đúng.
3. Prefix khác nhưng namespace URI giống không làm mất mapping.
4. Chữ `&` trong business text không bị ghép thành XML sai; payload được escape theo XML.
5. XML response phù hợp XSD và đồng thời có giá trị nghiệp vụ đúng qua XPath.

Lưu ý về `verifyNoMoreInteractions`: chỉ dùng sau khi đã `verify` các call thuộc contract; test này không giả định số tương tác giữa các **test methods** vì Spring TestContext/Mockito reset mocks theo cơ chế test.

### Vì sao service được mock?

`@WebServiceServerTest` không nạp mọi bean `@Service` thông thường. Nếu endpoint constructor yêu cầu `GreetingService` mà không có bean cung cấp, Spring báo `NoSuchBeanDefinitionException`/`UnsatisfiedDependencyException` ngay khi tạo test context. `@MockitoBean` giải quyết dependency bằng mock **trong Spring context**, khác `@Mock` chỉ tạo field Java của test mà endpoint không tự nhận được.

`@WebServiceServerTest(GreetingEndpoint.class)` là slicing có chủ đích, không nên dùng `@Import(WholeApplicationConfiguration.class)` chỉ để “cho pass”: điều đó có thể nạp database/scheduler/external clients ngoài mục tiêu.

## 11. Test business logic thuần: không dùng Spring khi chưa cần

`src/test/java/example/soapdemo/GreetingServiceUnitTest.java`:

```java
package example.soapdemo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class GreetingServiceUnitTest {

    private final GreetingService service =
            new GreetingService();

    @Test
    void trimsNameWithoutSpringContext() {
        assertEquals("Xin chào, Lan",
                service.greet("  Lan  "));
    }

    @Test
    void rejectsBlankName() {
        IllegalArgumentException exception =
                assertThrows(IllegalArgumentException.class,
                        () -> service.greet("   "));
        assertEquals("name must not be blank",
                exception.getMessage());
    }
}
```

Có **2 pure unit tests**. Chúng chứng minh quy tắc chuẩn hóa text và validation ở service. Những tests này **không chứng minh** SOAP dispatcher, XML namespace hoặc SOAP Fault mapping. Sự phân công rõ giữa unit và slice tránh phải khởi động context chỉ để kiểm tra một thao tác `strip()`.

## 12. Full context + MockWebServiceClient: vẫn không mở HTTP socket

Khi endpoint cần bean thật, properties, repositories, interceptors hoặc Boot auto-config nằm ngoài slice, dùng:

```java
@SpringBootTest
@AutoConfigureMockWebServiceClient
class FullSoapTest {
    @Autowired
    MockWebServiceClient client;
}
```

Trong Boot 3.5, `@AutoConfigureMockWebServiceClient` thuộc `org.springframework.boot.test.autoconfigure.webservices.server`; ở Boot 4 thuộc `org.springframework.boot.webservices.test.autoconfigure.server`.

**Quan trọng:** `@SpringBootTest` mặc định `WebEnvironment.MOCK` nên không tự mở server TCP. `MockWebServiceClient` vẫn dispatch trong context. Nếu mục tiêu là thử HTTP transport thật, **không gọi đây là real-server test**.

### Project: GreetingEndpointFullContextTest.java

`src/test/java/example/soapdemo/GreetingEndpointFullContextTest.java`:

```java
package example.soapdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.webservices.server.AutoConfigureMockWebServiceClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.ws.test.server.RequestCreators;
import org.springframework.ws.test.server.ResponseMatchers;
import org.springframework.xml.transform.StringSource;

@SpringBootTest
@AutoConfigureMockWebServiceClient
class GreetingEndpointFullContextTest {

    @Autowired
    MockWebServiceClient client;

    @Test
    void fullApplicationUsesRealGreetingService() {
        String request = """
            <g:GreetRequest xmlns:g="urn:demo:greeting:v1">
                <g:name>  Hoa  </g:name>
            </g:GreetRequest>
            """;

        String expected = """
            <g:GreetResponse xmlns:g="urn:demo:greeting:v1">
                <g:message>Xin chào, Hoa</g:message>
            </g:GreetResponse>
            """;

        client.sendRequest(
                RequestCreators.withPayload(
                        new StringSource(request)))
              .andExpect(ResponseMatchers.noFault())
              .andExpect(ResponseMatchers.payload(
                      new StringSource(expected)));
    }
}
```

Có **1 full-context test**. Nó gọi `GreetingService` thật, không cần `@MockitoBean`, chứng minh Boot bean wiring và SOAP dispatch cùng nhau. Nhưng như đã nhấn mạnh: đây chưa phải test về URL/WSDL/HTTP/Security TLS thực.

### Khi nào chuyển sang RANDOM_PORT?

Nếu cần xác nhận:

- SOAP servlet được map đến `spring.webservices.path` như dự kiến.
- HTTP POST tới `/services` thực sự nhận SOAP 1.1/1.2 envelope.
- `Content-Type`, HTTP status, SOAPAction, authentication hoặc CORS/proxy routing.
- WSDL document thực sự truy cập được qua đường dẫn đã công bố.
- Client certificate, TLS hoặc WS-Security qua hạ tầng thực.

Khi đó dùng `@SpringBootTest(webEnvironment=RANDOM_PORT)`, `@LocalServerPort` và HTTP client/SOAP client thật. Test cần dựng **full SOAP Envelope** theo version phù hợp — không dùng `RequestCreators.withPayload` như một HTTP request. Các yếu tố như path và authentication phải lấy từ cấu hình thật của ứng dụng. Không hard-code port 8080 trong CI.

## 13. Chạy Maven và kết quả mong đợi

Cần JDK 17+, Maven và quyền tải dependencies lần đầu. Từ thư mục `soap-slice-demo`:

```bash
mvn test
```

Chạy từng class:

```bash
mvn test -Dtest=GreetingEndpointSliceTest
mvn test -Dtest=GreetingEndpointFullContextTest
mvn test -Dtest=GreetingServiceUnitTest
```

Số phương thức test:

| Class | Số test | Điều thực sự được kiểm chứng |
| --- | ---: | --- |
| `GreetingEndpointSliceTest` | 4 | SOAP QName mapping, XML response, escaping, XSD |
| `GreetingEndpointFullContextTest` | 1 | Full context, service thật, SOAP response |
| `GreetingServiceUnitTest` | 2 | Business string normalization và reject blank |
| **Tổng** | **7** | Không cần HTTP server thật, DB, Docker |

**Kỳ vọng 7 PASS, 0 FAIL, 0 SKIPPED** khi project/build environment phù hợp. Đây là outcome dự kiến của ví dụ; cần thực sự chạy `mvn test` để xác nhận. Java code không gọi `System.out.println` nên **không có stdout ứng dụng cố định**; Maven/Spring-WS có thể ghi logs khác nhau. Xem `target/surefire-reports` để xác nhận số test executed và root cause khi có failure.

Ví dụ đoạn XML kỳ vọng từ service thực:

```xml
<g:GreetResponse xmlns:g="urn:demo:greeting:v1">
    <g:message>Xin chào, Hoa</g:message>
</g:GreetResponse>
```

SOAP message thực có Envelope và Body do Spring-WS message factory tạo. Không khẳng định raw byte, XML prefix formatting hoặc whitespace của message luôn giống snippet trên. Test sử dụng XML payload matcher thích hợp để đối chiếu theo contract.

## 14. Test XSD, WSDL và SOAP Fault theo hợp đồng lớn hơn

### XSD validation của response

`ResponseMatchers.validPayload(schema)` kiểm tra response XML theo XSD. Nó không tự động bảo đảm:

- Request input được server validate theo XSD.
- WSDL đang public đúng URL hoặc đúng schema.
- Endpoint đã khai báo đúng SOAPAction.
- Authentication/WS-Security headers được xử lý.
- Service thực sự đọc/ghi database.

Nếu schema là nguồn chân lý, hãy phát triển contract-first: đưa XSD/WSDL vào versioned resources, generate DTO/JAXB artifacts khi phù hợp, rồi test endpoint responses và WSDL publication riêng.

### Request validation

Muốn kiểm tra incoming request XSD:

1. Cấu hình Spring-WS `PayloadValidatingInterceptor` hoặc inbound schema-validation strategy phù hợp.
2. Chọn invalid payload (missing required element, sai kiểu, sai namespace).
3. Assert policy xử lý fault/client error của interceptor và **business service không được gọi**.
4. Với payload hợp lệ, assert service call và response.

Không cho rằng `validPayload` trên **response** là đủ để bảo vệ server khỏi invalid inbound XML.

### SOAP Fault detail

Khi production yêu cầu SOAP Fault cho invalid input, nên kiểm tra:

- SOAP 1.1 Client hoặc SOAP 1.2 Sender theo version.
- `faultstring`/`Reason` ổn định và không chứa internal stack trace.
- `Detail` có mã lỗi contract riêng, không trả secrets.
- Interceptor hoặc resolver thật sự được đăng ký trong **test slice** hoặc full context.
- Sai SOAPAction/namespace có được map thành loại fault quy định hay bị xử lý như unmapped endpoint.

`ResponseMatchers.clientOrSenderFault("...")` có thể so cả reason text nếu contract quy định. Đừng gắn expected reason bằng tiếng Anh chung chung khi localization có thể đổi theo locale.

### WS-Security và headers

Security của SOAP bao gồm nhiều lớp:

- HTTPS/TLS cho vận chuyển; có thể kèm client certificate.
- SOAP Header chứa UsernameToken, Timestamp, Signature hoặc Encryption theo WS-Security.
- EndpointInterceptor xác minh security policy trước business method.
- Authorization theo tenant/user và anti-replay cho signed requests.

`MockWebServiceClient` có thể dùng để kiểm tra interceptors/header processing với mock message, nhưng **không thay** thử TLS/certificate/HTTP/gateway thực. Trong unit/slice tests, dùng request/header creators phù hợp và tránh in credentials thật trong test fixtures hay logs.

## 15. Troubleshooting: các lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Không import được `@WebServiceServerTest` | Boot quá cũ, thiếu test auto-config hoặc sai package Boot 3/4 | Kiểm tra parent/BOM, dependency tree, version table |
| Không tìm thấy `MockWebServiceClient` | Thiếu `spring-ws-test` ở test classpath | Boot 3.x thêm `spring-ws-test` test scope |
| `NoSuchBeanDefinitionException` cho service | Slice không scan `@Service` thông thường | `@MockitoBean`/`@Import` collaborator cần thiết |
| `MockWebServiceClient` không auto-wire trong full context | Chỉ gắn `@SpringBootTest` | Thêm `@AutoConfigureMockWebServiceClient` |
| SOAP request không khớp endpoint | QName namespace/localPart khác `@PayloadRoot` | Kiểm tra URI + local name; prefix có thể thay đổi |
| Đưa `<soap:Envelope>` vào `withPayload` | Nhầm envelope với payload | Chỉ đưa inner XML payload vào `withPayload` |
| Test XSD fail dù text đúng | Schema targetNamespace/elementFormDefault khác XML | Sửa XSD/payload theo contract |
| `xpath` không tìm được element | XPath namespace mapping trống/sai | `Map.of("g", NS)` cho namespace |
| SOAP Fault không phải Client | Chưa cấu hình resolver/mapping hoặc lỗi là server exception | Kiểm tra `SoapFault...Resolver`, SOAP version |
| Chỉ assert `noFault` nhưng payload sai | Matcher quá yếu | Thêm `payload`/`xpath` và `validPayload` |
| `@MockitoBean` test compile lỗi trên Boot 3.3 | Spring Framework chưa có annotation mới | Dùng API version đó hỗ trợ, đừng trộn test dependencies |
| Full context load DB không cần thiết | Dùng `@SpringBootTest` cho endpoint slice | Chuyển `@WebServiceServerTest` |
| Slice bị kéo nhiều auto-config | Import app config quá rộng hoặc custom component scan | Giữ endpoint-specific config, kiểm tra bean graph |
| WSDL URL 404 nhưng slice PASS | Slice không chạy servlet/network layer | Thêm HTTP integration với random port |
| Test sai SOAP version | SOAP 1.1/1.2 message factory và envelope khác | Kiểm tra namespace, Content-Type, SOAPAction |
| SOAP Fault text leak internal info | Resolver trả exception message/raw stack | Map fault reason/detail an toàn |
| Test HTTP 200 nhưng SOAP body lỗi | Chỉ assert HTTP status | Parse và assert SOAP Body/Fault |
| Bị XXE/XML entity abuse | XML parser/marshaller xử lý input không an toàn | Secure parser, tắt external DTD/entity và giới hạn size/depth |
| SOAP outbound test fail dù endpoint test PASS | Hai hướng client/server khác nhau | Dùng `@WebServiceClientTest` + `MockWebServiceServer` |
| Không thấy GraphQL query chạy | Nhầm SOAP stack với GraphQL | Dùng `@GraphQlTest` và `GraphQlTester` |
| Test green nhưng không chạy | Maven/JUnit filter/test naming sai | Xem Surefire reports/test count |
| Boot 4 “package does not exist” | Test module được reorganize | Dùng focused `webservices-test` starter + import mới |

### Quy trình debug có thứ tự

1. Đọc Maven/JDK/Spring Boot version thực tế và dependency tree.
2. Xác minh chọn đúng **SOAP server test** hay **SOAP client test**.
3. Xác nhận `@Endpoint` được scan và collaborator được cung cấp.
4. Gửi **payload root đúng namespace** qua `withPayload`, không gửi envelope lồng.
5. Dùng `noFault` cộng `payload` hoặc `xpath` để xác nhận business data.
6. Nếu cần XSD, test `validPayload` với đúng schema resource.
7. Nếu cần SOAP Fault, xác nhận resolver/interceptor đã được nạp trước khi assert fault type.
8. Nếu chỉ fail ở HTTP socket, tách cấu hình servlet path/TLS/auth/proxy khỏi slice logic.
9. Với version mismatch, thay imports/starters theo bảng version; không tắt SOAP tests để build PASS.
10. Kiểm tra tất cả test methods đã được phát hiện và chạy thực trong `target/surefire-reports`.

## 16. Fallback không dùng @WebServiceServerTest

Trong dự án legacy hoặc cấu hình Spring-WS tùy chỉnh không tương thích slice, vẫn có thể khởi tạo client thủ công:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.ws.test.server.MockWebServiceClient;

class ManualSoapTest {

    @Autowired
    ApplicationContext applicationContext;

    private MockWebServiceClient client;

    @BeforeEach
    void setUp() {
        client = MockWebServiceClient.createClient(
                applicationContext);
    }
}
```

Đây là **trích đoạn**, chưa có test bootstrap/context configuration. Để chạy được, cần bổ sung `@ContextConfiguration`/`@SpringJUnitConfig` hoặc `@SpringBootTest` và các Spring-WS endpoint mappings/adapters/message factory thật sự có trong context.

`createClient(ApplicationContext)` là API Spring-WS, không phụ thuộc việc Boot có `@WebServiceServerTest` hay không. Nó không tự động scan endpoint hoặc đăng ký SOAP adapter. Nếu context không được setup đúng, bạn có thể thấy lỗi không có dispatcher/endpoint mapping.

Có thể dùng `MockWebServiceClient.createClient(WebServiceMessageReceiver, WebServiceMessageFactory)` khi cần kiểm soát trực tiếp receiver/factory; đó là cách nâng cao, không phải yêu cầu của bài nhập môn.

## 17. Checklist nghiệm thu

- [ ] Đã xác định ứng dụng là **SOAP server** chứ không phải SOAP outbound client?
- [ ] Đã chọn `@WebServiceServerTest` thay vì `@WebMvcTest`/`@GraphQlTest`?
- [ ] Spring Boot major và import annotation khớp bảng Boot 3.x/4.x?
- [ ] Test classpath có Spring-WS test support, JUnit và Mockito đúng phiên bản?
- [ ] `@Endpoint`, `@PayloadRoot`, `@RequestPayload`, `@ResponsePayload` đúng hợp đồng XML?
- [ ] Test chọn endpoint theo **namespace URI + local name**, không hard-code prefix?
- [ ] Gửi payload XML qua `RequestCreators.withPayload`, không nhét cả envelope?
- [ ] Test inject `MockWebServiceClient` hoặc tạo thủ công đúng lifecycle?
- [ ] Constructor collaborator được cung cấp bằng `@MockitoBean` hoặc `@Import`?
- [ ] Có test happy path, escaped XML characters và namespace prefix khác?
- [ ] Assert `noFault` **và** payload hoặc XPath theo nội dung?
- [ ] XSD response được validate nếu contract quy định?
- [ ] Không coi response XSD validation là đã bật **request validation**?
- [ ] SOAP Fault mapping/interceptor được xác minh trước khi assert Client/Sender?
- [ ] Không nhầm `MockWebServiceClient` với `MockWebServiceServer`?
- [ ] Biết khi nào cần `@SpringBootTest + @AutoConfigureMockWebServiceClient`?
- [ ] Biết những gì slice không kiểm: WSDL URL, HTTP/TLS, SOAPAction, gateway và DB thật?
- [ ] SOAP 1.1/1.2 và SOAP header security có test phù hợp nếu hệ thống yêu cầu?
- [ ] Không dùng XML parser cho untrusted input mà thiếu bảo vệ XXE/DTD?
- [ ] Build/JUnit reports xác nhận đủ tests thực thi và không có hidden skips?
- [ ] Nếu nâng cấp Boot, kiểm tra test starters và package trước khi sửa logic?

## 18. Tài liệu chính thức

1. [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): mục **Auto-configured Spring Web Services Server Tests** với imports `@WebServiceServerTest` và `MockWebServiceClient` của Boot 3.x.
2. [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): mục SOAP client/server testing và imports mới cho Boot 4.x.
3. [Spring Boot 4 — @WebServiceServerTest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/webservices/test/autoconfigure/server/WebServiceServerTest.html): scope `@Endpoint`, collaborator và lựa chọn full context.
4. [Spring Boot 4 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide): thay đổi module/test starter/package.
5. [Spring-WS — MockWebServiceClient API](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/test/server/MockWebServiceClient.html): cách tạo client và gọi sendRequest/andExpect.
6. [Spring-WS — ResponseMatchers API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/test/server/ResponseMatchers.html): payload, xpath, validPayload, noFault, fault matchers.
7. [Spring-WS — Reference Documentation](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): `@Endpoint`, QName mapping, SOAP message factory và server-side testing.
8. [Spring-WS Project](https://spring.io/projects/spring-ws/): contract-first SOAP service, XML stack và testing.
9. [XML Schema Primer — W3C](https://www.w3.org/TR/xmlschema-0/): element namespaces, XSD structure và qualified elements.
10. [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html): phiên bản managed của Spring-WS và Spring Framework theo Boot 3.5.

**Điểm nhớ:** `@WebServiceServerTest` kiểm tra **SOAP server slice**, `MockWebServiceClient` gửi SOAP payload **trong Spring context**, không phải HTTP client thật. Với Boot 3.5 và Boot 4, **package annotation và tên starter khác nhau**; hãy khóa version, dùng đúng imports, rồi khẳng định kết quả bằng **namespace + payload/XPath + XSD/Fault expectations** đúng contract. Khi cần HTTP/WSDL/TLS/database thật, dùng tầng integration bổ sung thay vì gán cho test slice một bằng chứng mà nó không cung cấp.
