# Kiểm tra khởi động và thực hiện một trao đổi SOAP tối thiểu

> **Chương:** Khởi tạo dự án  
> **Bối cảnh:** Phát triển dịch vụ SOAP theo hướng **contract-first** với Spring Web Services (Spring-WS). Bài này đi từ dự án Spring Boot tối thiểu, khai báo XSD, công bố WSDL, viết endpoint, chạy ứng dụng đến gửi một SOAP request và kiểm tra response thực tế.

## 1. Mục tiêu và tiêu chí hoàn thành

Khởi động thành công một ứng dụng Spring Boot **chưa đủ** để kết luận SOAP service hoạt động. Muốn có một vòng trao đổi tối thiểu đáng tin cậy, cần chứng minh cả đường đi từ contract đến network:

1. Ứng dụng Spring Boot chạy và `MessageDispatcherServlet` được gắn vào đường dẫn dự kiến.
2. XSD chứa global element cho request/response; WSDL 1.1 được công bố qua HTTP và tham chiếu các phần tử đó.
3. Endpoint Spring-WS nhận đúng **QName** của phần tử đầu tiên trong SOAP Body.
4. Gửi một SOAP 1.1 request qua HTTP POST và nhận SOAP response có payload chính xác.
5. Một request bị sai QName hoặc sai dữ liệu được nhận diện là trường hợp lỗi, không bị hiểu nhầm là thao tác thành công.
6. Có cách chẩn đoán riêng cho lỗi build, không mở được cổng, không tải được WSDL, không tìm được endpoint và lỗi XML/namespace.

Ví dụ dùng nghiệp vụ giả lập **chào người dùng**:

- Request: `GetGreetingRequest` gồm `name`.
- Response: `GetGreetingResponse` gồm `message`.
- Namespace: `urn:example:greeting:v1`.
- URL servlet SOAP: `http://localhost:8080/ws`.
- URL WSDL: `http://localhost:8080/ws/greetings.wsdl`.

Vòng trao đổi thành công mong đợi:

~~~mermaid
sequenceDiagram
    participant Caller as SOAP client
    participant Servlet as MessageDispatcherServlet
    participant Dispatch as MessageDispatcher
    participant Endpoint as GreetingEndpoint
    Caller->>Servlet: POST /ws - SOAP Envelope
    Servlet->>Dispatch: XML message
    Dispatch->>Endpoint: PayloadRoot GetGreetingRequest
    Endpoint-->>Dispatch: GetGreetingResponse
    Dispatch-->>Servlet: SOAP response
    Servlet-->>Caller: HTTP 200 + SOAP Envelope
~~~

Đây là bài **smoke test khởi tạo**, chưa phải hệ thống production. Sau khi có vòng trao đổi này, dự án thực tế mới tích hợp JAXB/XJC, business service, SOAP Fault có cấu trúc, interceptor, XML security, WS-Security và chứng chỉ.

## 2. Chọn bộ công cụ nhất quán

Ví dụ sử dụng **Java 17+ và Spring Boot 3.x**, tức hệ sinh thái Spring hiện đại dùng Jakarta API. `Spring Web Services` xử lý SOAP endpoint; `Spring Boot` hỗ trợ cấu hình và vận hành HTTP. Dùng Spring Boot phiên bản được dự án hỗ trợ và đảm bảo các dependency tương thích với nhau. Tệp POM dưới đây minh họa với Spring Boot 3.5.0; đây là một mốc phiên bản cụ thể để hiểu ví dụ, không phải yêu cầu luôn chọn bản này cho mọi hệ thống.

Điều kiện tối thiểu tại máy phát triển:

- Có JDK 17+ và `JAVA_HOME` trỏ đúng JDK.
- Có Maven hoặc Maven Wrapper `mvnw` của dự án.
- Cổng 8080 đang rảnh; nếu đổi port, phải đổi cả địa chỉ trong lệnh kiểm thử.
- Có công cụ gửi HTTP như `curl`; trên Windows PowerShell nên dùng `curl.exe` để tránh alias khác.
- Có thể tạo và lưu các tệp mã nguồn của ứng dụng ví dụ.

Thư mục minh họa:

~~~text
soap-hello/
├── pom.xml
└── src/main/
    ├── java/com/example/soaphello/
    │   ├── SoapHelloApplication.java
    │   ├── config/WebServiceConfig.java
    │   └── endpoint/GreetingEndpoint.java
    └── resources/
        ├── application.properties
        └── greeting.xsd
~~~

Thêm tệp `request.xml` ở thư mục gốc khi muốn gửi mẫu SOAP với curl. Những đường dẫn này thuộc **dự án mẫu**; nội dung bài học đang đọc không tự tạo ứng dụng ngoài thư mục bài được giao.

### 2.1. Maven dependencies

~~~xml
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

  <groupId>com.example</groupId>
  <artifactId>soap-hello</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web-services</artifactId>
    </dependency>
    <dependency>
      <groupId>wsdl4j</groupId>
      <artifactId>wsdl4j</artifactId>
      <version>1.6.3</version>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
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
~~~

`spring-boot-starter-web-services` cung cấp cơ sở xây dựng Spring-WS qua HTTP. `wsdl4j` phục vụ công bố WSDL 1.1 bằng `DefaultWsdl11Definition` trong ví dụ. Không cần JAX-WS runtime/CXF chỉ để thực hiện endpoint Spring-WS này. Về sau, nếu dùng JAXB-generated classes thì cấu hình thêm plugin sinh mã và JAXB runtime/API tương ứng với phiên bản Jakarta đang dùng.

### 2.2. Entry point và cấu hình ứng dụng

`src/main/java/com/example/soaphello/SoapHelloApplication.java`:

~~~java
package com.example.soaphello;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SoapHelloApplication {
    public static void main(String[] args) {
        SpringApplication.run(SoapHelloApplication.class, args);
    }
}
~~~

`src/main/resources/application.properties`:

~~~properties
server.port=8080
spring.application.name=soap-hello
~~~

Không cần bật logging toàn bộ SOAP Body chỉ để xác nhận service khởi động; ở môi trường thật, thông điệp có thể chứa thông tin nhạy cảm. Khi cần chẩn đoán, nên dùng logging có chọn lọc và che dữ liệu trước khi ghi log.

## 3. Bắt đầu bằng XSD: xác định contract dữ liệu

Tạo `src/main/resources/greeting.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:greeting:v1"
           targetNamespace="urn:example:greeting:v1"
           elementFormDefault="qualified">

  <xs:element name="GetGreetingRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="name" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetGreetingResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="message" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Đây là contract-first ở mức tối thiểu: xác định **cấu trúc request/response trước**, rồi mới viết Java endpoint. XSD hiện mô tả `name` là chuỗi XML; chưa áp đặt giá trị không được rỗng, chưa có mã lỗi nghiệp vụ. Các ràng buộc phức tạp có thể được bổ sung có kiểm soát sau khi luồng tối thiểu hoạt động.

Cần phân biệt:

- `GetGreetingRequest` và `GetGreetingResponse` là **global elements** dùng làm payload root.
- `name` và `message` là **child elements** thuộc cùng namespace vì `elementFormDefault="qualified"`.
- Prefix XML như `g` là tên viết tắt; namespace URI `urn:example:greeting:v1` mới là yếu tố xác định danh tính.
- XSD không chứa địa chỉ HTTP, tên Java class hoặc thông tin chứng chỉ.

### Vì sao đặt hậu tố Request/Response?

`DefaultWsdl11Definition` có thể suy ra operation trong WSDL 1.1 từ các global element theo quy tắc hậu tố request/response. Với `GetGreetingRequest` và `GetGreetingResponse`, operation suy ra thường là `GetGreeting`. Cách đặt tên này giúp ví dụ ngắn nhưng **không thay thế việc kiểm tra WSDL được công bố**.

## 4. Đăng ký MessageDispatcherServlet và công bố WSDL

Tạo `src/main/java/com/example/soaphello/config/WebServiceConfig.java`:

~~~java
package com.example.soaphello.config;

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
public class WebServiceConfig {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet>
            messageDispatcherServlet(ApplicationContext context) {
        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(context);
        servlet.setTransformWsdlLocations(true);
        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean
    public XsdSchema greetingSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("greeting.xsd"));
    }

    @Bean(name = "greetings")
    public DefaultWsdl11Definition greetingWsdl(XsdSchema greetingSchema) {
        DefaultWsdl11Definition definition =
                new DefaultWsdl11Definition();
        definition.setPortTypeName("GreetingPort");
        definition.setLocationUri("/ws");
        definition.setTargetNamespace("urn:example:greeting:v1");
        definition.setSchema(greetingSchema);
        return definition;
    }
}
~~~

Ý nghĩa từng phần:

| Thành phần | Trách nhiệm | Cách kiểm tra |
|---|---|---|
| `@EnableWs` | Bật cấu hình Spring-WS cho endpoint/message adapter | Spring context khởi tạo không báo lỗi cấu hình |
| `MessageDispatcherServlet` | Nhận HTTP SOAP request tại `/ws/*` | HTTP POST `/ws` được xử lý bởi SOAP stack |
| `greetingSchema` | Đọc `greeting.xsd` trong classpath | Không gặp lỗi thiếu schema khi khởi động |
| `@Bean(name="greetings")` | Công bố WSDL có tên `greetings` | GET `/ws/greetings.wsdl` trả WSDL XML |
| `setLocationUri("/ws")` | Chỉ định endpoint SOAP mà WSDL mô tả | `soap:address` có địa chỉ dự kiến |
| `setTransformWsdlLocations(true)` | Có thể cập nhật địa chỉ được công bố theo URL request | Kiểm tra đường dẫn thực qua proxy/TLS |

**Lưu ý:** `setTransformWsdlLocations(true)` không thay thế cấu hình reverse proxy đáng tin cậy. Khi có gateway hoặc HTTPS termination, phải kiểm tra WSDL công bố thực sự chứa host, scheme, path mà client bên ngoài truy cập được. Không tự động tin mọi forwarding header từ nguồn không kiểm soát.

Khi khởi động Spring Boot, servlet và bean định nghĩa WSDL được Spring quản lý. URL `/ws/greetings.wsdl` được suy ra từ servlet mapping và tên bean `greetings`; đây là một GET khác với endpoint POST SOAP `/ws`.

## 5. Endpoint tối thiểu: nhận payload XML và trả payload XML

Để kiểm tra luồng SOAP trước khi thêm build-time JAXB generation, ví dụ đầu tiên dùng DOM `Element` cho request và JAXP `DOMSource` cho response. Đây là cách giữ nguyên trọng tâm ở **XML contract** và tránh phụ thuộc vào DTO chưa được sinh từ XSD; khi phát triển nghiệp vụ thực, có thể chuyển sang JAXB model.

Tạo `src/main/java/com/example/soaphello/endpoint/GreetingEndpoint.java`:

~~~java
package com.example.soaphello.endpoint;

import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.Source;
import javax.xml.transform.dom.DOMSource;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

@Endpoint
public class GreetingEndpoint {
    private static final String NS = "urn:example:greeting:v1";

    @PayloadRoot(namespace = NS, localPart = "GetGreetingRequest")
    @ResponsePayload
    public Source greet(@RequestPayload Element request)
            throws ParserConfigurationException {

        NodeList names = request.getElementsByTagNameNS(NS, "name");
        if (names.getLength() != 1) {
            throw new IllegalArgumentException(
                    "GetGreetingRequest must contain exactly one name");
        }

        String name = names.item(0).getTextContent().trim();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name cannot be blank");
        }

        // Chỉ tạo DOM response mới; không parse XML chưa tin cậy ở đây.
        Document doc = DocumentBuilderFactory.newInstance()
                .newDocumentBuilder().newDocument();

        Element root = doc.createElementNS(NS, "g:GetGreetingResponse");
        doc.appendChild(root);

        Element message = doc.createElementNS(NS, "g:message");
        message.setTextContent("Xin chào, " + name + "!");
        root.appendChild(message);

        return new DOMSource(root);
    }
}
~~~

`@PayloadRoot` định tuyến theo **QName** của phần tử gốc trong SOAP Body; tên Java method `greet` không phải SOAP operation dispatch key. `@RequestPayload Element` cung cấp DOM payload; `@ResponsePayload Source` trả XML payload để Spring-WS đóng gói vào SOAP response.

Gọi `setTextContent` là cách an toàn hơn tự nối chuỗi XML bằng tay: giá trị `name` có ký tự `&` hoặc `<` sẽ được serializer escape đúng khi xuất XML. Điều kiện kiểm tra `name` ở ví dụ giúp tránh response vô nghĩa; với service thực tế, cần schema validation và cơ chế SOAP Fault theo contract, không phụ thuộc vào exception mặc định.

**Đừng nhầm hai nhóm import:** `javax.xml.parsers.*` và `javax.xml.transform.*` là API JAXP có sẵn trong JDK; chúng vẫn mang tên `javax` trong Java 17. Chúng khác với JAXB/JAX-WS API đời cũ `javax.xml.bind.*` hoặc `javax.xml.ws.*`; hệ Jakarta hiện đại dùng `jakarta.xml.bind.*` và `jakarta.xml.ws.*` cho các API đó.

### Điều kiện tối thiểu của ví dụ

- Có Spring-WS endpoint adapter hỗ trợ DOM input và `Source` output (theo stack Spring-WS tương ứng).
- Servlet mapping `/ws/*` khớp request `/ws`.
- Namespace và local name của request trùng `@PayloadRoot`.
- Response DOM thỏa XSD `GetGreetingResponse`.
- Dữ liệu nghiệp vụ ở đây là giả lập, chưa có repository/service bên dưới.

## 6. Khởi động dự án và kiểm tra các lớp theo thứ tự

Chạy tại thư mục `soap-hello` (nơi có `pom.xml`):

~~~bash
java -version
mvn -version
mvn -q -DskipTests package
mvn spring-boot:run
~~~

Lệnh cuối giữ tiến trình server chạy. Hãy mở terminal thứ hai để gửi HTTP request. Nếu dùng Maven Wrapper, thay `mvn` bằng `./mvnw` (Unix) hoặc `mvnw.cmd` (Windows).

### 6.1. Thế nào là “khởi động thành công”?

Khi Spring context khởi tạo và web server lắng nghe cổng dự kiến, log thường có thông tin Tomcat started on port 8080 và Started SoapHelloApplication. Điều này chứng minh **application startup**, chưa chứng minh endpoint nhận đúng SOAP Body. Một ứng dụng có thể khởi động nhưng:

- Không công bố WSDL vì thiếu schema hoặc thiếu WSDL bean.
- Công bố WSDL ở URL khác dự kiến do servlet mapping khác.
- Có WSDL nhưng không có method `@PayloadRoot` tương ứng.
- Endpoint nhận request nhưng trả XML khác schema.
- Service hoạt động tại localhost nhưng WSDL công bố địa chỉ nội bộ không dùng được qua gateway.

Do đó cần kiểm tra theo ba tầng:

| Tầng | Kiểm tra | Kết quả chứng minh |
|---|---|---|
| **Process/startup** | Build và log startup | Spring context và embedded web server chạy |
| **Contract publication** | GET `/ws/greetings.wsdl` | WSDL được servlet công bố với contract và endpoint phù hợp |
| **SOAP exchange** | POST `/ws` với SOAP request | Request đi tới endpoint và response XML được gửi lại |

HTTP GET lên URL WSDL và HTTP POST lên URL SOAP là **hai thao tác khác nhau**; đừng POST request vào `/ws/greetings.wsdl` chỉ vì đã tải WSDL ở đó.

### 6.2. Xem WSDL bằng HTTP GET

Trong terminal thứ hai:

~~~bash
curl -i http://localhost:8080/ws/greetings.wsdl
~~~

Trên Windows PowerShell có thể dùng:

~~~powershell
curl.exe -i "http://localhost:8080/ws/greetings.wsdl"
~~~

Kết quả đúng thường gồm HTTP `200 OK`, XML có `wsdl:definitions` và các thành phần:

- `portType` chứa operation `GetGreeting`.
- Input tham chiếu global element `GetGreetingRequest`.
- Output tham chiếu global element `GetGreetingResponse`.
- SOAP binding là kiểu document/literal.
- `soap:address location` trỏ tới URL SOAP tương ứng `/ws`.

Các tên prefix XML có thể khác `wsdl`/`soap`; hãy so sánh **namespace URI**, các QName và tên operation/element. Nếu HTTP 404 thì chưa thể kết luận Java endpoint sai: đầu tiên kiểm tra servlet mapping, bean name `greetings` và địa chỉ truy cập.

## 7. Thực hiện một trao đổi SOAP 1.1 tối thiểu

### 7.1. Tạo request.xml

Tại thư mục gốc dự án mẫu, tạo `request.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:g="urn:example:greeting:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <g:GetGreetingRequest>
      <g:name>Lan</g:name>
    </g:GetGreetingRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Cấu trúc gồm:

1. `Envelope` của **SOAP 1.1**, xác định bởi namespace `http://schemas.xmlsoap.org/soap/envelope/`.
2. `Header` có thể rỗng; trong SOAP thực tế có thể chứa WS-Security hoặc các metadata khác.
3. `Body` chứa đúng **một** global element payload `GetGreetingRequest` thuộc namespace contract.
4. `name` cũng thuộc namespace `urn:example:greeting:v1` vì XSD dùng `elementFormDefault="qualified"`.

Nếu đổi prefix `g` thành `x` nhưng vẫn giữ namespace URI, contract không thay đổi. Nếu đổi URI thành `urn:example:greeting:v2` hoặc đổi local name thành `getGreetingRequest`, QName khác và endpoint có thể không match.

### 7.2. Gửi request bằng curl

Dùng `curl` thật sự để gửi body từ file (trên PowerShell dùng `curl.exe`):

~~~bash
curl -i -sS \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: ""' \
  --data-binary @request.xml \
  http://localhost:8080/ws
~~~

Phiên bản một dòng chạy được trong Windows PowerShell:

~~~powershell
curl.exe -i -sS -H "Content-Type: text/xml; charset=utf-8" -H 'SOAPAction: ""' --data-binary "@request.xml" "http://localhost:8080/ws"
~~~

**Vì sao chọn các tham số này?**

- `-i` hiện cả HTTP response headers để phân biệt HTTP 200, 404, 415, 500.
- `Content-Type: text/xml` là media type thường dùng cho SOAP **1.1** qua HTTP.
- `SOAPAction: ""` là SOAPAction rỗng cho bài smoke test; với contract có action cụ thể, dùng giá trị WSDL yêu cầu.
- `--data-binary @request.xml` gửi nguyên byte của tệp, tránh việc shell tự dựng hoặc biến đổi XML.
- URL là endpoint POST `/ws`, không phải URL WSDL.

Với SOAP 1.2, envelope namespace và Content-Type thường khác (`application/soap+xml`), nên không trộn HTTP headers SOAP 1.2 với envelope SOAP 1.1 rồi quy lỗi cho endpoint.

### 7.3. Response mong đợi

Một response thành công sẽ có HTTP status khoảng `200 OK` và SOAP Envelope chứa nội dung tương đương:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <g:GetGreetingResponse xmlns:g="urn:example:greeting:v1">
      <g:message>Xin chào, Lan!</g:message>
    </g:GetGreetingResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Thứ tự khai báo namespace, prefix và cách xuống dòng có thể thay đổi theo serializer. Những yếu tố phải kiểm tra là:

- SOAP version/namespace của `Envelope`.
- QName `{urn:example:greeting:v1}GetGreetingResponse`.
- Child element `{urn:example:greeting:v1}message`.
- Nội dung text `Xin chào, Lan!`, đã được escape đúng khi cần.

**Không so sánh response bằng cách yêu cầu hai XML string phải giống từng byte.** XML tương đương về namespace và cấu trúc có thể dùng prefix khác, vị trí xmlns khác hoặc format khác nhau. Trong kiểm thử tự động, so sánh XML qua namespace-aware XPath/XSD hoặc XML-aware matcher.

### 7.4. Ghi nhận kết quả smoke test

Một nhật ký kiểm tra ngắn có thể ghi:

| Check | Bằng chứng cần có |
|---|---|
| Build | Exit code 0, tạo JAR |
| Startup | Ứng dụng lắng nghe cổng 8080, không có exception lúc tạo context |
| WSDL | GET `/ws/greetings.wsdl` trả HTTP 200 và có operation/soap:address đúng |
| SOAP POST | HTTP 200 với response SOAP 1.1 |
| Payload | `GetGreetingResponse/message = "Xin chào, Lan!"` |
| Fault path | Thử request sai QName hoặc dữ liệu sai và ghi nhận response lỗi có thể chẩn đoán |

Bảng này chỉ được đánh dấu PASS khi **đã chạy thực tế** trên dự án mẫu; ví dụ trong tài liệu không tự chứng minh rằng ứng dụng đang được triển khai thành công.

## 8. Kiểm tra lỗi để biết dịch vụ hoạt động đúng ranh giới

Một request chạy tốt chưa đủ để đánh giá pipeline SOAP. Hãy thử các trường hợp lỗi có chủ đích.

### 8.1. Sai namespace hoặc local name

Sửa SOAP Body từ:

~~~xml
<g:GetGreetingRequest>
  <g:name>Lan</g:name>
</g:GetGreetingRequest>
~~~

thành:

~~~xml
<g:GetGreetingRequest xmlns:g="urn:example:greeting:v2">
  <g:name>Lan</g:name>
</g:GetGreetingRequest>
~~~

Server đang map `{urn:example:greeting:v1}GetGreetingRequest`; request dùng `v2` không có method match. Spring-WS có thể trả SOAP Fault kiểu không tìm thấy endpoint, cùng HTTP status lỗi. Nội dung fault cụ thể phụ thuộc phiên bản và cấu hình exception resolver; **không nên phụ thuộc vào một chuỗi lỗi cố định** khi chưa có hợp đồng lỗi.

### 8.2. Thiếu name hoặc name rỗng

XSD mẫu cho phép `name` là string nhưng **không cho phép bỏ element**. Endpoint còn chủ động từ chối text rỗng. Hai lớp kiểm tra khác nhau:

- **Schema validation**, nếu bật, phát hiện thiếu `name` theo XSD.
- **Logic trong endpoint**, như `name.isEmpty()`, từ chối text rỗng sau khi đọc XML.

Trong project mẫu hiện tại, **chưa tự động bật XSD validation interceptor**. Đừng tuyên bố ứng dụng đã chặn mọi request sai schema chỉ vì có file `greeting.xsd`. JAXB cũng không mặc nhiên kiểm tra mọi XSD facet khi unmarshalling.

### 8.3. SOAP Envelope hoặc HTTP Content-Type không phù hợp

Thử dùng SOAP 1.2 namespace trong body nhưng giữ `Content-Type: text/xml` của SOAP 1.1. Tùy message factory và policy, stack có thể từ chối request ngay trước khi gọi endpoint. Lỗi này nằm ở **SOAP protocol/message factory**, khác với lỗi mapping `@PayloadRoot`.

### 8.4. Quan sát Fault mà không rò rỉ thông tin

Trong môi trường tích hợp thật, cần chuyển validation và business exception sang SOAP Fault với fault code/reason/detail có chủ đích, tránh gửi Java stack trace hoặc thông tin nội bộ. Với lỗi kiểm tra request trong ví dụ, exception mặc định chỉ nhằm minh họa đường lỗi tối thiểu; chưa phải thiết kế SOAP Fault hoàn chỉnh.

## 9. Chẩn đoán các lỗi thường gặp khi khởi tạo

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra đầu tiên |
|---|---|---|
| Maven build lỗi | JDK/Maven không phù hợp, dependency không tải được, import sai | `java -version`, `mvn -version`, thông báo compile |
| Ứng dụng không start | Port 8080 bị dùng, bean lỗi, XSD không tìm thấy | Log stack trace đầu tiên, `server.port`, vị trí `resources/greeting.xsd` |
| WSDL GET trả 404 | Sai URL, thiếu bean WSDL hoặc servlet mapping | `@Bean(name="greetings")`, `/ws/*`, `/ws/greetings.wsdl` |
| WSDL trả được nhưng `soap:address` sai | Reverse proxy/forwarded headers hoặc `locationUri` chưa đúng | URL WSDL nhìn từ client, scheme/host/path thực tế |
| SOAP POST trả 404 | POST sai URL, chưa map servlet ở `/ws` | Kiểm tra request URL, context path, mapping |
| SOAP Fault “no endpoint” | Sai QName request Body hoặc thiếu `@Endpoint` | Namespace `urn:example:greeting:v1`, `GetGreetingRequest`, component scan |
| SOAP Fault “failed to invoke” | Method gặp exception, thiếu field, adapter hoặc binding sai | Stack trace server, chữ ký `@RequestPayload`/`@ResponsePayload` |
| SOAP version mismatch | SOAP 1.1/1.2 namespace hoặc Content-Type sai | Envelope namespace và request headers |
| XML không hợp lệ | Thiếu dấu đóng, ký tự chưa escape, sai namespace, sai order | Kiểm tra XML được gửi nguyên vẹn; đối chiếu XSD |
| WSDL tốt nhưng client JAXB thất bại | Mã sinh chưa khớp schema, khác namespace/JAXB version | Generated classes, package `javax.*` vs `jakarta.*` và XML thực |
| HTTP 200 nhưng response không đúng | Endpoint trả payload sai hoặc test chỉ nhìn status | Kiểm tra QName, child element và text của SOAP Body |

**Phân biệt ba loại xác nhận:** server *started*, WSDL *published*, và SOAP request *processed*. Chẩn đoán theo thứ tự đó thường tìm được lỗi nhanh hơn việc thay đổi nhiều cấu hình cùng lúc.

## 10. Gửi SOAP từ Java bằng WebServiceTemplate

`curl` giúp kiểm thử độc lập với mã client. Khi muốn xác minh chính stack Spring-WS phía tiêu thụ, bạn có thể tạo một client Java tối thiểu dùng `WebServiceTemplate`. Khác với `curl`, client truyền **payload XML** vào template; template sẽ đóng gói nó trong SOAP Envelope và gửi qua transport.

Mảnh mã minh họa chạy khi server đã mở tại `http://localhost:8080/ws`:

~~~java
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.xml.transform.StringResult;
import org.springframework.xml.transform.StringSource;

public class MinimalSoapClient {
    public static void main(String[] args) {
        String payload = """
                <g:GetGreetingRequest
                    xmlns:g="urn:example:greeting:v1">
                  <g:name>Lan</g:name>
                </g:GetGreetingRequest>
                """;

        WebServiceTemplate template = new WebServiceTemplate();
        StringResult result = new StringResult();

        boolean received = template.sendSourceAndReceiveToResult(
                "http://localhost:8080/ws",
                new StringSource(payload),
                result);

        if (!received) {
            throw new IllegalStateException("SOAP response has no payload");
        }

        System.out.println(result);
    }
}
~~~

Ví dụ trên cần dependency Spring-WS client và một SOAP message factory/transport hoạt động trong runtime; một project sử dụng starter Spring-WS thông thường sẽ có các thành phần liên quan. Đoạn code chỉ minh họa **payload-based client**, không thay thế mã production với timeout, chứng chỉ, cấu hình fault và logging. Java text block yêu cầu phiên bản Java hỗ trợ tính năng này (Java 17 đáp ứng).

Nếu service contract-first lớn hơn, client có thể sử dụng **JAXB marshaller/unmarshaller**:

~~~java
// Ý tưởng sau khi đã sinh và cấu hình JAXB model đúng XSD:
GetGreetingRequest request = new GetGreetingRequest();
request.setName("Lan");

GetGreetingResponse response = (GetGreetingResponse)
        webServiceTemplate.marshalSendAndReceive(
                "http://localhost:8080/ws", request);
~~~

Đây là **đoạn minh họa**, chưa chạy nguyên vẹn vì bài smoke test ban đầu dùng DOM và chưa có JAXB-generated classes. Với XJC, có schema chỉ sinh `JAXBElement` qua `ObjectFactory`; khi đó phải truyền JAXB root object thích hợp và dùng `Jaxb2Marshaller` cấu hình đúng package/classes. Luôn xác minh XML thực gửi, thay vì chỉ dựa vào chữ ký Java.

### Khi nào dùng curl, khi nào dùng SOAP client?

| Công cụ | Mục đích |
|---|---|
| `curl` hoặc SOAP testing client | Kiểm tra HTTP, Envelope, namespace, SOAPAction, WSDL và payload độc lập với code Java |
| `WebServiceTemplate` | Kiểm tra phía client Spring-WS, transport, marshalling và xử lý response/Fault |
| JAX-WS/CXF proxy sinh từ WSDL | Kiểm tra tương thích với client dựa trên contract, giống một nhóm đối tác tích hợp |
| Tooling của đối tác (.NET, ESB, v.v.) | Bằng chứng mạnh hơn về tương thích liên hệ thống thật |

## 11. Bổ sung validation và kiểm thử tự động sau smoke test

### 11.1. Thêm schema validation một cách có chủ đích

Ở bài tối thiểu, có XSD và WSDL **không tự có nghĩa** toàn bộ XML payload được validate theo XSD trước khi vào method. Nếu ứng dụng phải từ chối request sai schema, dùng `PayloadValidatingInterceptor`, khai báo schema và đăng ký interceptor trong cấu hình Spring-WS, ví dụ về các bước cấu hình cốt lõi:

~~~java
PayloadValidatingInterceptor validator =
        new PayloadValidatingInterceptor();
validator.setXsdSchema(greetingSchema);
validator.setValidateRequest(true);
validator.setValidateResponse(true);

// Đưa validator vào danh sách EndpointInterceptor
// qua cấu hình WsConfigurer#addInterceptors(...) của ứng dụng.
~~~

Đây là mảnh cấu hình minh họa và cần import/đăng ký tương thích với phiên bản Spring-WS. Bật validate response sẽ giúp phát hiện server tạo XML sai schema, nhưng cũng có thể làm lộ lỗi contract của hệ thống hiện tại. Trước khi bật trong production, thống nhất cách chuyển lỗi validation sang SOAP Fault và cách logging dữ liệu an toàn.

Với `name`, muốn schema cũng chặn chuỗi rỗng, có thể thay `type="xs:string"` bằng một **simple type restriction** có `minLength`. Chú ý `minLength="1"` không tự cấm chuỗi chỉ chứa khoảng trắng; cần thiết kế thêm ràng buộc phù hợp hoặc kiểm tra nghiệp vụ. Đồng thời, những thay đổi XSD đã công bố phải được đánh giá tương thích với client cũ.

### 11.2. Kiểm thử endpoint bằng Spring-WS test support

Sau khi vòng gọi thật bằng curl chạy ổn, `MockWebServiceClient` giúp kiểm tra endpoint dispatch và response payload ở mức ứng dụng mà không cần mở cổng HTTP mỗi lần. Muốn dùng test utility này, thêm dependency `spring-ws-test` với scope `test` phù hợp BOM hiện tại:

~~~xml
<dependency>
  <groupId>org.springframework.ws</groupId>
  <artifactId>spring-ws-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Ví dụ test khái niệm (các import được lược bỏ):

~~~java
@SpringBootTest
class GreetingEndpointTest {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void returnsGreetingPayload() {
        MockWebServiceClient client =
                MockWebServiceClient.createClient(applicationContext);

        Source request = new StringSource("""
                <g:GetGreetingRequest xmlns:g="urn:example:greeting:v1">
                  <g:name>Lan</g:name>
                </g:GetGreetingRequest>
                """);

        Source expected = new StringSource("""
                <g:GetGreetingResponse xmlns:g="urn:example:greeting:v1">
                  <g:message>Xin chào, Lan!</g:message>
                </g:GetGreetingResponse>
                """);

        client.sendRequest(withPayload(request))
                .andExpect(payload(expected));
    }
}
~~~

`withPayload` là request creator của `org.springframework.ws.test.server.RequestCreators`, còn `payload` là response matcher từ `org.springframework.ws.test.server.ResponseMatchers`; trong file test thực tế cần static import hai hàm này và import các lớp JUnit/Spring XML/Spring Test tương ứng. Đoạn minh họa mô tả cách test **một request và một response payload**, không mô tả các bài test kết nối mạng hoặc chứng chỉ.

Một chiến lược kiểm thử cân bằng có ba lớp:

- **Unit/endpoint test:** kiểm tra xử lý request và response có cấu trúc như mong đợi.
- **Integration test qua HTTP thật:** thực sự POST SOAP vào `/ws`, thử mapping servlet, Content-Type và SOAP faults.
- **Compatibility test với client độc lập:** sinh/gọi client từ WSDL đã công bố, kiểm thử nghiệp vụ, schema và chính sách bảo mật.

Lớp thứ hai và thứ ba quan trọng vì một MockWebServiceClient test thành công **không chứng minh** mọi chi tiết HTTP, proxy, TLS hoặc WS-Security hoạt động.

## 12. Những thứ chưa thuộc “trao đổi SOAP tối thiểu”

Không nên biến bài smoke test thành một dự án enterprise hoàn chỉnh ngay từ đầu, nhưng cần biết các hạng mục sẽ phải bổ sung:

| Chủ đề | Mức tối thiểu hiện tại | Khi tiến lên tích hợp doanh nghiệp |
|---|---|---|
| **XSD/WSDL** | Một schema nhỏ và WSDL tạo từ XSD | Contract version rõ, quản lý import/include và WSDL đã được duyệt |
| **JAXB** | DOM `Element` + `DOMSource` để kiểm tra wire format | Sinh model từ XSD, cấu hình `Jaxb2Marshaller`, thử namespace và nil/optional |
| **Endpoint** | Một method `@PayloadRoot` trả chuỗi chào | Tách business service, validation, quyền truy cập, transaction |
| **SOAP client** | curl và client `WebServiceTemplate` đơn giản | Timeout, retry/idempotency, Fault handling, certificate trust |
| **SOAP Fault** | Exception tối thiểu có thể dẫn đến Fault | Fault code/reason/detail có cấu trúc, ổn định theo WSDL |
| **Interceptor** | Chưa yêu cầu | `EndpointInterceptor`, `PayloadValidatingInterceptor`, logging an toàn |
| **XML security** | Không tự parse chuỗi XML chưa tin cậy trong endpoint | Chặn XXE/external entity, đặt giới hạn kích thước/depth/tài nguyên |
| **WS-Security** | SOAP Header rỗng | UsernameToken, Timestamp, ký/mã hóa SOAP khi đối tác yêu cầu |
| **Chứng chỉ/TLS** | Gọi localhost HTTP phục vụ phát triển | HTTPS, truststore/keystore, xác minh chuỗi chứng chỉ và rotation |
| **Tương thích** | Một SOAP request/response thành công | XSD validation, client đa công nghệ, error path, contract regression |

**TLS và WS-Security không thay thế nhau.** TLS bảo vệ đường truyền; WS-Security bảo vệ các phần của SOAP message theo policy. Việc một lời gọi localhost HTTP thành công không chứng minh yêu cầu security từ đối tác đã được đáp ứng.

Một hệ thống SOAP dùng WSDL/XSD chính thức có thể chọn công bố **WSDL tĩnh** thay cho WSDL được sinh động từ XSD, để đảm bảo service/binding/operation/address khớp hợp đồng đã chốt. Với `DefaultWsdl11Definition`, mỗi lần đổi XSD cần kiểm tra lại WSDL công bố và mã client sinh ra.

## 13. Quy trình lặp khi tích hợp với service thật

Sau bài chào đơn giản, bạn có thể thay bằng một nghiệp vụ đơn hàng theo trình tự:

1. Chốt global elements `GetOrderRequest` và `GetOrderResponse`, namespace và kiểu dữ liệu ở XSD.
2. Quy định WSDL operation/binding/port, địa chỉ và SOAP version.
3. Sinh JAXB model hoặc dùng XML mapping phù hợp, đảm bảo code tuân thủ schema.
4. Đăng ký endpoint theo QName payload root, gọi tầng nghiệp vụ.
5. Bật schema validation, xử lý SOAP Fault có cấu trúc.
6. Viết client thử qua `WebServiceTemplate` và một client độc lập từ WSDL.
7. Bổ sung WS-SecurityPolicy, chứng chỉ, timeout, correlation ID, retry/idempotency theo nhu cầu.
8. Lưu mẫu request/response/fault và chạy regression sau mỗi thay đổi XSD/WSDL.

Khi lỗi phát sinh, quay lại cách kiểm tra theo lớp: **build → startup → WSDL publication → SOAP dispatch → payload validation → business response → security/policy**. Quy trình giúp xác định đúng tầng chịu trách nhiệm, thay vì chỉnh sửa toàn bộ ứng dụng theo cảm giác.

## 14. Bài tập và checklist hoàn thành

### Bài tập A — Nhận diện lỗi namespace

Bạn gửi:

~~~xml
<g:GetGreetingRequest xmlns:g="urn:example:greeting:v2">
  <g:name>Lan</g:name>
</g:GetGreetingRequest>
~~~

trong khi endpoint dùng `@PayloadRoot(namespace="urn:example:greeting:v1", localPart="GetGreetingRequest")`. **Tại sao WSDL có thể tải được nhưng request vẫn thất bại?**

*Gợi ý:* WSDL được công bố qua GET và hoạt động độc lập với mapping của SOAP POST. QName body hiện dùng `v2`, không khớp `v1` mà endpoint mong đợi.

### Bài tập B — Phân biệt lỗi schema và lỗi nghiệp vụ

Client gửi `<g:GetGreetingRequest/>`. Nếu chưa bật `PayloadValidatingInterceptor`, có chắc SOAP stack sẽ từ chối vì thiếu `name` theo XSD không?

*Đáp án:* Không thể chắc. XSD chỉ được công bố, còn validation phải được cấu hình. Ở mã ví dụ, method có kiểm tra riêng và sẽ ném exception khi thiếu `name`; đây là một hành vi khác với lỗi XSD validation được bật chủ đích.

### Bài tập C — Chẩn đoán HTTP 404

Server log báo đã chạy cổng 8080. GET `/ws/greetings.wsdl` được 404. Đâu là ba thứ cần kiểm tra đầu tiên?

*Đáp án:* Servlet mapping `/ws/*`, tên bean `@Bean(name="greetings")` và vị trí `greeting.xsd`/cấu hình `DefaultWsdl11Definition`. Nếu đang dùng context path, phải cộng đúng tiền tố vào URL.

### Bài tập D — Thêm client JAXB

Bạn muốn thay DOM endpoint bằng JAXB-generated DTO và dùng `marshalSendAndReceive`. Cần giữ nguyên điều gì?

*Đáp án:* Global element QNames, XSD cấu trúc request/response, WSDL, SOAP version và fault/security contract. Mapping Java là chi tiết hiện thực; phải kiểm tra payload XML thực sự được tạo sau khi thay đổi.

### Checklist thực hành

- [ ] JDK và Maven đúng phiên bản, build thành công.
- [ ] Spring Boot startup thành công, cổng 8080 lắng nghe.
- [ ] `greeting.xsd` nằm trong classpath và được dùng để công bố WSDL.
- [ ] GET `/ws/greetings.wsdl` trả HTTP 200 và contract đúng.
- [ ] POST `/ws` gửi SOAP 1.1 Envelope với namespace `urn:example:greeting:v1`.
- [ ] Response chứa `GetGreetingResponse/message` và giá trị `Xin chào, Lan!`.
- [ ] Có thử request sai QName và kiểm tra nó không bị xử lý như request hợp lệ.
- [ ] Đã phân biệt XSD validation với kiểm tra nghiệp vụ và response marshalling.
- [ ] Biết rõ hạng mục production còn thiếu: SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ, timeout và test tương thích.

**Ghi nhớ:** Một dự án Spring Web Services chỉ được coi là hoàn tất **smoke test SOAP tối thiểu** khi bạn đã nhìn thấy **HTTP POST thật mang SOAP Envelope**, request được định tuyến theo **payload QName**, và response XML đúng XSD/WSDL được gửi ngược lại. Startup log và WSDL GET là những kiểm tra cần thiết nhưng chỉ là hai bước đầu của chuỗi này.
