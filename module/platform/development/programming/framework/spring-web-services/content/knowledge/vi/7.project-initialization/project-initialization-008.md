# Đóng gói WSDL, XSD và tài nguyên ánh xạ vào ứng dụng

Trong một dự án **Spring Web Services (Spring-WS)** theo hướng **contract-first**, việc có file WSDL và XSD trong thư mục mã nguồn chưa đủ để dịch vụ SOAP chạy ổn định sau khi đóng gói. Ứng dụng phải tìm được schema và metadata JAXB từ **classpath của bản phân phối**, máy khách phải tải được WSDL cùng những XSD được tham chiếu, còn các thành phần endpoint, SOAP client, interceptor và bảo mật phải cùng sử dụng một phiên bản hợp đồng.

Bài học thuộc chương **Khởi tạo dự án** của module `SPRING_WEB_SERVICES`. Ta sẽ đóng gói một dịch vụ tra cứu đơn hàng SOAP, công bố WSDL/XSD, tạo các class JAXB từ XSD, nhận request qua endpoint, đồng thời chuẩn bị ranh giới để bổ sung SOAP Fault, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Trọng tâm là **đường dẫn, vòng đời và tính sẵn có của tài nguyên khi chạy trong JAR/WAR**.

## Mục tiêu học tập

Sau khi học xong, bạn có thể:

1. Phân biệt tài nguyên nguồn, đầu ra sinh mã và tài nguyên cần có khi chạy.
2. Tổ chức `src/main/resources`, WSDL/XSD, tệp tùy biến JAXB `.xjb` và package Java được sinh mà không nhầm đường dẫn filesystem với classpath.
3. Đóng gói và công bố WSDL tĩnh hoặc WSDL được sinh từ XSD qua `MessageDispatcherServlet`.
4. Giải thích cách `wsdl:types`, `xs:include`, `xs:import`, `schemaLocation` và URL công bố liên hệ với nhau.
5. Cấu hình `Jaxb2Marshaller` để ứng dụng tìm đúng JAXB classes/metadata sau khi đóng gói.
6. Kiểm tra nội dung JAR/WAR, thực hiện thử nghiệm tải WSDL/XSD và gửi SOAP request từ bên ngoài.
7. Tránh các lỗi tài nguyên phổ biến, lộ khóa bí mật hoặc thay đổi hợp đồng ngoài ý muốn.

## 1. Ba thời điểm của một hợp đồng SOAP

Cần hiểu rõ **tệp nào được sử dụng ở thời điểm nào**.

| Thời điểm | Hoạt động | Đầu vào/đầu ra điển hình |
| --- | --- | --- |
| **Thiết kế** | Xây dựng XSD, WSDL, quy tắc request/response và fault | `orders-v1.xsd`, `orders.wsdl`, XML mẫu |
| **Build** | Sinh Java từ XSD, biên dịch, copy resources, đóng gói | Source JAXB sinh trong `target/generated-sources/...`, class và resource trong artifact |
| **Runtime** | Nạp WSDL/XSD, marshal/unmarshal JAXB, công bố hợp đồng và xử lý SOAP | `ClassPathResource`, `SimpleWsdl11Definition`, `XsdSchema`, `Jaxb2Marshaller` |

Một luồng tổng quát:

~~~mermaid
flowchart LR
    A["XSD/WSDL trong source"] --> B["Build: XJC sinh Java"]
    B --> C["Compile JAXB classes"]
    A --> D["Copy tài nguyên"]
    C --> E["JAR/WAR"]
    D --> E
    E --> F["Ứng dụng Spring-WS chạy"]
    F --> G["GET WSDL/XSD"]
    F --> H["POST SOAP: JAXB + endpoint"]
~~~

Từ `.xsd` sang Java là **bước build**, còn từ request XML sang object JAXB là **bước runtime**. Đừng lẫn hai công việc này: đã sinh code thành công không có nghĩa WSDL được công bố qua HTTP, và tải được WSDL không bảo đảm JAXB marshalling hoạt động.

## 2. Cấu trúc thư mục đề xuất cho dự án Maven

Ví dụ một ứng dụng Spring Boot chạy Java 17+ với Spring-WS và JAXB Jakarta (hướng phù hợp Spring Boot 3.x/Spring Framework 6.x):

~~~text
orders-soap/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/
│   │   │       ├── OrdersSoapApplication.java
│   │   │       ├── config/SoapConfiguration.java
│   │   │       ├── endpoint/OrderEndpoint.java
│   │   │       ├── service/OrderService.java
│   │   │       └── client/OrderSoapClient.java
│   │   ├── resources/
│   │   │   ├── application.yml
│   │   │   ├── wsdl/
│   │   │   │   └── orders.wsdl
│   │   │   └── xsd/
│   │   │       └── orders-v1.xsd
│   │   └── jaxb/
│   │       └── bindings.xjb
│   └── test/
│       └── resources/
│           ├── soap/get-order-request.xml
│           └── soap/get-order-response.xml
└── target/
    ├── generated-sources/jaxb/    # do plugin sinh khi build
    ├── classes/                   # kết quả compile + resources
    └── orders-soap.jar             # tên minh họa
~~~

Đây là **cấu trúc đề xuất**, không phải yêu cầu bắt buộc của Spring-WS. Với Gradle, các thư mục thông dụng là `build/generated/...`, `build/resources/main` và `build/libs` thay vì `target`.

### 2.1. Từng nhóm tệp có trách nhiệm gì?

| Đường dẫn | Trách nhiệm | Có cần nằm trong artifact runtime? |
| --- | --- | --- |
| `src/main/resources/xsd/orders-v1.xsd` | Schema nghiệp vụ, dùng để validate và/hoặc công bố cho client | **Có**, nếu ứng dụng đọc/công bố/validate từ classpath |
| `src/main/resources/wsdl/orders.wsdl` | WSDL tĩnh đã chốt với đối tác | **Có**, nếu dùng `SimpleWsdl11Definition` |
| `src/main/jaxb/bindings.xjb` | Tùy chỉnh cách XJC sinh class/package/kiểu | Thường **không**; chỉ cần cho **build** |
| `target/generated-sources/jaxb/...` | Mã Java do XJC sinh, không chỉnh tay | Không cần đóng gói **source**; cần **class đã biên dịch** |
| `target/classes/com/.../ObjectFactory.class` | Metadata JAXB sinh và biên dịch | **Có**, nếu marshaller dùng package đó |
| `jaxb.index` / `jaxb.properties` (nếu có) | Metadata hỗ trợ JAXB context/provider theo cấu hình dùng | **Có**, nếu ứng dụng JAXB thực sự phụ thuộc |
| `src/test/resources/...` | XML fixtures kiểm thử | Không cần trong bản phân phối production |
| Keystore/truststore/private key | Vật liệu TLS, mTLS hoặc WS-Security | Thường nên **cấp từ môi trường bảo mật bên ngoài** |

Hai điểm dễ nhầm:

- `.xjb` là **JAXB external binding file** dùng lúc sinh code; nó **không** phải lớp chuyển đổi XML runtime. Không cần đưa `bindings.xjb` vào JAR để JAXB marshal.
- `.xsd` có thể cần ở runtime cho `PayloadValidatingInterceptor` và để công bố XSD cho đối tác. Khi đã sinh class JAXB, **không vì thế mà luôn có thể bỏ XSD**; quyết định phụ thuộc nhu cầu validation/công bố thực tế.

### 2.2. Đặt tên/version tài nguyên có chủ đích

Ví dụ dùng đường dẫn nguồn `xsd/orders-v1.xsd`, namespace `urn:example:orders:v1` và WSDL public `/ws/orders.wsdl`. Đường dẫn file, URL HTTP, namespace URI và tên operation là **bốn khái niệm khác nhau**:

- `xsd/orders-v1.xsd`: nơi Spring tìm tài nguyên trong classpath.
- `/ws/orders-v1.xsd`: URL giả định để client tải schema từ server.
- `urn:example:orders:v1`: namespace nhận diện phần tử XML trong XSD.
- `GetOrder`: operation WSDL; payload thực tế mang QName `{urn:example:orders:v1}GetOrderRequest`.

Đổi một khái niệm không tự làm những khái niệm khác thay đổi. Đây là cơ sở để tránh lỗi khi chuyển môi trường, cập nhật contract hoặc xây SOAP client.

## 3. Ví dụ XSD đóng gói với ứng dụng

Tạo file nguồn `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="OrderStateType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="CREATED"/>
      <xs:enumeration value="SHIPPED"/>
      <xs:enumeration value="CANCELLED"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="state" type="tns:OrderStateType"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Hai **global elements** `GetOrderRequest` và `GetOrderResponse` là những phần tử root mà client và endpoint sử dụng. Các trường `orderId`, `state` là phần tử con, không tạo operation riêng. `elementFormDefault="qualified"` yêu cầu các phần tử con thuộc namespace `urn:example:orders:v1`.

Mô hình dữ liệu này là tối giản cho mục tiêu đóng gói. Khi thiết kế hợp đồng doanh nghiệp thật, cần bổ sung giới hạn độ dài, mã lỗi, versioning, quy tắc authorization và khả năng tương thích.

## 4. WSDL tĩnh tham chiếu XSD: cần đóng gói và công bố cả hai

Một WSDL công bố cho đối tác phải mô tả operation và cách lấy schema cho XML request/response. Có thể **nhúng schema vào `wsdl:types`** hoặc **tham chiếu schema bên ngoài**. Phần này chọn cách tham chiếu để thấy rõ bài toán đóng gói.

File `src/main/resources/wsdl/orders.wsdl` minh họa WSDL 1.1 document/literal SOAP 1.1:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    name="OrdersService">

  <wsdl:types>
    <xs:schema targetNamespace="urn:example:orders:v1">
      <xs:include schemaLocation="orders-v1.xsd"/>
    </xs:schema>
  </wsdl:types>

  <wsdl:message name="GetOrderInput">
    <wsdl:part name="parameters" element="tns:GetOrderRequest"/>
  </wsdl:message>

  <wsdl:message name="GetOrderOutput">
    <wsdl:part name="parameters" element="tns:GetOrderResponse"/>
  </wsdl:message>

  <wsdl:portType name="OrdersPortType">
    <wsdl:operation name="GetOrder">
      <wsdl:input message="tns:GetOrderInput"/>
      <wsdl:output message="tns:GetOrderOutput"/>
    </wsdl:operation>
  </wsdl:portType>

  <wsdl:binding name="OrdersSoap11Binding"
                type="tns:OrdersPortType">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <wsdl:operation name="GetOrder">
      <soap:operation soapAction="urn:example:orders:v1:GetOrder"/>
      <wsdl:input>
        <soap:body use="literal"/>
      </wsdl:input>
      <wsdl:output>
        <soap:body use="literal"/>
      </wsdl:output>
    </wsdl:operation>
  </wsdl:binding>

  <wsdl:service name="OrdersService">
    <wsdl:port name="OrdersSoap11Port"
               binding="tns:OrdersSoap11Binding">
      <soap:address location="http://localhost:8080/ws"/>
    </wsdl:port>
  </wsdl:service>

</wsdl:definitions>
~~~

Ở đây `wsdl:types` khai báo một schema có cùng `targetNamespace` với XSD đích nên dùng `xs:include`. Với tài liệu XSD ở **namespace khác**, dùng `xs:import namespace="..." schemaLocation="..."` theo quy tắc XML Schema. Dùng nhầm `include` khi namespace khác nhau là lỗi hợp đồng, không phải lỗi riêng của Spring-WS.

### 4.1. Vì sao `schemaLocation="orders-v1.xsd"` là điểm quan trọng?

Nếu WSDL được tải từ:

~~~text
http://localhost:8080/ws/orders.wsdl
~~~

thì một công cụ WSDL/XSD thường giải quyết `schemaLocation="orders-v1.xsd"` tương đối với URL WSDL thành:

~~~text
http://localhost:8080/ws/orders-v1.xsd
~~~

Điều đó có nghĩa **cả hai URL phải tồn tại và phục vụ đúng XML**, không chỉ có hai file nằm trong JAR.

Một số sai lầm phổ biến:

- Đặt WSDL ở `src/main/resources/wsdl/orders.wsdl`, XSD ở `src/main/resources/xsd/orders-v1.xsd`, rồi giả định đường dẫn filesystem tương đối được giữ nguyên trên web.
- Viết `schemaLocation="../xsd/orders-v1.xsd"` mà không có HTTP mapping thực tế tương ứng.
- Chỉ kiểm tra `GET /ws/orders.wsdl` thành công; client generator sau đó thất bại khi tải XSD.
- Dùng `classpath:xsd/orders-v1.xsd` làm `schemaLocation` trong WSDL công bố: đây là cách định vị tài nguyên **nội bộ Java**, không phải URL chuẩn để máy khách bên ngoài giải quyết.

### 4.2. `xs:include` và `xs:import` khi có nhiều schema

| Tình huống | Cách liên kết | Ví dụ |
| --- | --- | --- |
| Các tệp cùng namespace target | `xs:include` | `orders-v1.xsd` include `orders-types-v1.xsd` |
| Tệp thuộc namespace khác, ví dụ customer | `xs:import` với `namespace` tương ứng | Orders XSD import Customer XSD |
| Hai WSDL tham chiếu nhau | `wsdl:import` | Một WSDL phụ có service/type riêng |

Khi bundle nhiều tài liệu, bạn phải kiểm tra **toàn bộ cây tham chiếu**. Một WSDL chính tải được nhưng một `xs:import` ở cấp sâu hơn trả 404 vẫn khiến việc sinh client hoặc schema validation thất bại.

## 5. Công bố WSDL/XSD từ tài nguyên classpath trong Spring-WS

Tạo `SoapConfiguration.java`. Cấu hình dưới đây chọn cách **WSDL tĩnh**: ứng dụng nạp file đã chốt từ classpath và công bố qua `MessageDispatcherServlet`.

~~~java
package com.example.orders.config;

import org.springframework.boot.web.servlet.ServletRegistrationBean;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.transport.http.MessageDispatcherServlet;
import org.springframework.ws.wsdl.wsdl11.SimpleWsdl11Definition;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class SoapConfiguration {

    @Bean
    public ServletRegistrationBean<MessageDispatcherServlet> soapServlet(
            ApplicationContext applicationContext) {

        MessageDispatcherServlet servlet = new MessageDispatcherServlet();
        servlet.setApplicationContext(applicationContext);
        servlet.setTransformWsdlLocations(true);

        return new ServletRegistrationBean<>(servlet, "/ws/*");
    }

    @Bean(name = "orders-v1")
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));
    }

    @Bean(name = "orders")
    public SimpleWsdl11Definition ordersWsdl() {
        return new SimpleWsdl11Definition(
            new ClassPathResource("wsdl/orders.wsdl"));
    }
}
~~~

Cấu hình dự kiến cung cấp các đường dẫn:

| URL (môi trường local) | Loại request | Nguồn nội bộ |
| --- | --- | --- |
| `http://localhost:8080/ws/orders.wsdl` | HTTP GET | Bean `orders` → `wsdl/orders.wsdl` |
| `http://localhost:8080/ws/orders-v1.xsd` | HTTP GET | Bean `orders-v1` → `xsd/orders-v1.xsd` |
| `http://localhost:8080/ws` | HTTP POST | SOAP request tới dispatcher/endpoint |

Tên bean đóng vai trò trong **URL công bố** của `MessageDispatcherServlet`. `@Bean(name="orders")` khác với `OrdersService` trong WSDL hoặc `GetOrder` operation. File nguồn cũng không nhất thiết phải trùng đường dẫn public, miễn cấu hình ánh xạ rõ ràng.

**Lưu ý về cấu hình tự động:** Spring Boot có thể tự cấu hình `MessageDispatcherServlet` tùy starter và phiên bản. Nếu đã tự đăng ký servlet như trên, cần kiểm tra cấu hình Boot hiện có để không vô tình tạo hai servlet mapping khác nhau. Đoạn mã là một chiến lược đăng ký rõ ràng, không phải yêu cầu bắt buộc cho mọi dự án Boot.

### 5.1. `setTransformWsdlLocations(true)` không thay thế việc kiểm tra public URL

Tùy cách cấu hình và URL request, Spring-WS có thể biến đổi giá trị `soap:address/@location` trong WSDL được phục vụ để phản ánh địa chỉ truy cập. Tuy nhiên:

- Reverse proxy có thể thay đổi host, port, scheme, context path và servlet mapping.
- Header forwarded/proxy phải được cấu hình đúng; nếu không WSDL có thể công bố `http://localhost:8080/ws` thay vì HTTPS public.
- Biến đổi `soap:address` **không đồng nghĩa** mọi `xs:include`, `xs:import` hoặc `wsdl:import` đều được chỉnh đúng.
- Cần tải WSDL **từ nơi client thực sự kết nối** rồi kiểm tra tất cả URL tham chiếu và SOAP address.

WSDL trong ví dụ chứa địa chỉ localhost để học; không dùng nguyên địa chỉ đó như hợp đồng production.

### 5.2. Nếu dùng WSDL sinh tự động thay vì tĩnh

Spring-WS cũng hỗ trợ `DefaultWsdl11Definition` tạo WSDL 1.1 từ XSD:

~~~java
@Bean(name = "orders")
public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
    DefaultWsdl11Definition definition =
        new DefaultWsdl11Definition();

    definition.setPortTypeName("OrdersPort");
    definition.setTargetNamespace("urn:example:orders:v1");
    definition.setLocationUri("/ws");
    definition.setSchema(ordersSchema);
    return definition;
}
~~~

Cấu hình này **thay thế** `SimpleWsdl11Definition` bean cùng tên, không khai báo cả hai cùng lúc. Với quy ước mặc định, bộ sinh WSDL nhận diện các global elements có hậu tố `Request` và `Response`; từ `GetOrderRequest` + `GetOrderResponse` có thể suy ra operation `GetOrder`.

Đối với WSDL sinh động, việc biểu diễn schema trong WSDL có thể khác cách file WSDL tĩnh ở mục 4 tham chiếu XSD. **Kiểm tra tài liệu WSDL thật**; không giả định mọi cấu hình đều phục vụ cùng một cây URL/schema. Khi WSDL đã được đối tác phê duyệt, cân nhắc lưu bản WSDL đã chốt và công bố tĩnh để kiểm soát diff khi nâng framework.

## 6. Sinh mã JAXB: phân biệt `.xjb` với dữ liệu runtime

JAXB liên kết XML schema với kiểu Java. Cần hai phần độc lập:

1. **XJC hoặc công cụ tương đương ở build time** đọc XSD (và tùy chọn `.xjb`), sinh mã Java.
2. **JAXB runtime** tạo context và marshal/unmarshal giữa XML với object Java đã biên dịch.

Nếu dùng Spring Boot 3+/Spring-WS 4.x, hãy chọn bộ XJC và JAXB thuộc **Jakarta XML Binding** (`jakarta.xml.bind`); tránh trộn source sinh kiểu `javax.xml.bind` từ stack Java EE cũ vào ứng dụng Jakarta nếu không có kế hoạch chuyển đổi rõ ràng.

### 6.1. Vai trò của file binding `bindings.xjb`

Một file `.xjb` có thể ảnh hưởng:

- Tên package Java được sinh từ một hoặc nhiều namespace.
- Tên class/property trong những trường hợp cần tương thích với mã hiện hữu.
- Chuyển đổi kiểu dữ liệu XML sang Java qua binding adapter tùy cấu hình.
- Cách xử lý phần tử và kiểu khi XSD quá phức tạp hoặc tên không phù hợp Java.

Nhưng file `.xjb` **không phải cấu hình endpoint mapping** và không thay đổi WSDL được công bố nếu XSD/WSDL giữ nguyên. Ví dụ, đổi package JAXB từ `com.example.orders.ws.v1` sang `com.example.orders.generated` ảnh hưởng code Java, import và `Jaxb2Marshaller`, nhưng QName `{urn:example:orders:v1}GetOrderRequest` vẫn giữ nguyên nếu không sửa XSD.

Đặt `bindings.xjb` tại `src/main/jaxb/bindings.xjb` và cấu hình plugin XJC đọc đúng tệp đó. Cấu trúc XML của `.xjb` khác nhau theo version JAXB; file binding cũ dùng namespace `http://java.sun.com/xml/ns/jaxb` có thể cần chuyển khi nâng lên Jakarta, không nên chỉ đổi dependency rồi kỳ vọng công cụ sinh mã vẫn hiểu.

### 6.2. Maven: các dependency ở mức ý tưởng triển khai

Dự án sử dụng Spring Boot dependency management có thể thêm:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web-services</artifactId>
  </dependency>

  <!-- Khi môi trường cần JAXB runtime implementation. -->
  <dependency>
    <groupId>org.glassfish.jaxb</groupId>
    <artifactId>jaxb-runtime</artifactId>
    <scope>runtime</scope>
  </dependency>

  <dependency>
    <groupId>org.springframework.ws</groupId>
    <artifactId>spring-ws-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

Đây là **đoạn dependency minh họa**, không phải một file `pom.xml` đầy đủ. Version của starter/JAXB cần được quản lý nhất quán bằng Spring Boot parent/BOM. Công cụ sinh JAXB (ví dụ một Maven XJC plugin tương thích Jakarta) phải được cấu hình ở **build plugins** riêng; chỉ thêm `jaxb-runtime` không làm Maven tự sinh class.

Một quy trình build thông dụng:

~~~text
validate
   ↓
generate-sources (XJC đọc orders-v1.xsd + bindings.xjb nếu dùng)
   ↓
process-resources (copy WSDL/XSD/application.yml...)
   ↓
compile (biên dịch cả class viết tay và JAXB generated)
   ↓
test
   ↓
package (đóng gói class + runtime resources)
~~~

Trong Maven lifecycle thông dụng, `generate-sources` diễn ra trước `process-resources`, và `process-resources` diễn ra trước `compile`. Các plugin XJC có thể tùy chỉnh execution, nhưng đầu ra cuối cùng cần có **JAXB classes đã biên dịch và WSDL/XSD resources** trước bước `package`.

Để thiết lập XJC cụ thể, đảm bảo plugin:

- Đọc schema từ `src/main/resources/xsd/orders-v1.xsd`.
- Đọc `src/main/jaxb/bindings.xjb` nếu đã có binding tùy biến.
- Gắn thư mục generated sources vào compile source roots.
- Tạo các kiểu JAXB thuộc package đã chọn, dùng namespace Jakarta phù hợp.
- Không cần sửa tay mã nằm trong `target/generated-sources`; hãy sửa XSD/binding rồi sinh lại.

Đường dẫn generated-sources, version plugin và cú pháp goal/configuration khác nhau giữa Maven XJC plugins. Không sao chép một plugin block từ stack JAXB cũ mà chưa kiểm tra khả năng tương thích của dự án hiện tại.

### 6.3. Các tệp JAXB thật sự phải có trong bản đóng gói

Sau khi compile, runtime cần những class JAXB có annotation và metadata thích hợp, ví dụ:

~~~text
BOOT-INF/classes/com/example/orders/ws/v1/GetOrderRequest.class
BOOT-INF/classes/com/example/orders/ws/v1/GetOrderResponse.class
BOOT-INF/classes/com/example/orders/ws/v1/ObjectFactory.class
BOOT-INF/classes/com/example/orders/ws/v1/package-info.class
~~~

Đây là đường dẫn mẫu cho **Spring Boot executable JAR**; tên class cụ thể do công cụ sinh quyết định. `ObjectFactory` và `package-info.class` thường chứa thông tin cần thiết để JAXB context hiểu phần tử/namespace. Một số binding tạo ra `JAXBElement` làm phần tử root; trong trường hợp đó client/endpoint cần sử dụng wrapper tương ứng.

`jaxb.index` là **tệp text liệt kê tên class** dùng trong một số kiểu khởi tạo JAXBContext theo context path; nếu package được cấu hình dựa vào nó, hãy đảm bảo tài nguyên này được đưa vào classpath. Không tự tạo `jaxb.index` khi không cần; JAXB context từ XJC-generated `ObjectFactory` thường đã có metadata phù hợp.

## 7. Đọc classpath resource đúng cách khi chạy JAR/WAR

Trong IDE, tệp `src/main/resources/xsd/orders-v1.xsd` tồn tại dưới dạng file trên đĩa. Trong executable JAR, nó thường nằm ở:

~~~text
BOOT-INF/classes/xsd/orders-v1.xsd
~~~

và được classloader đọc từ bên trong archive. **Không dùng đường dẫn filesystem nguồn ở runtime**:

~~~java
// Dễ chạy ở IDE nhưng sai khi đóng gói/triển khai.
File xsd = new File("src/main/resources/xsd/orders-v1.xsd");
~~~

Thay bằng classpath:

~~~java
ClassPathResource schemaResource =
    new ClassPathResource("xsd/orders-v1.xsd");

// Có thể đọc stream kể cả khi file ở trong JAR.
try (InputStream stream = schemaResource.getInputStream()) {
    // Truyền cho parser/validator phù hợp.
}
~~~

Hoặc khởi tạo Spring bean với resource:

~~~java
@Bean
public XsdSchema ordersSchema() {
    return new SimpleXsdSchema(
        new ClassPathResource("xsd/orders-v1.xsd"));
}
~~~

**Đừng gọi `getFile()`** để đòi đường dẫn vật lý cho resource nằm trong nested JAR, vì tệp có thể không tồn tại như một file riêng trên filesystem. Khi một thư viện cần URL/stream, dùng API resource phù hợp; nếu thư viện chỉ chấp nhận file vật lý thì cần cách chuẩn bị tệp triển khai có kiểm soát, không suy luận từ source tree.

### 7.1. Maven resource filtering và tệp hợp đồng XML

Mặc định Maven copy các tệp trong `src/main/resources` vào output classpath. **Không bật filtering vô điều kiện** trên WSDL/XSD:

- Các placeholder cấu hình như `${...}` hoặc thuộc tính mang ý nghĩa XML có thể bị quá trình filtering thay thế.
- WSDL/XSD đã ký duyệt cần ổn định byte/content giữa các bản build.
- Giá trị cấu hình theo môi trường nên đi qua `application.yml`, biến môi trường hoặc cơ chế triển khai phù hợp, thay vì viết đè nội dung contract một cách khó kiểm soát.

Nếu cần biến đổi endpoint address khi publish WSDL, hãy dùng cơ chế công bố/triển khai đã kiểm thử và so sánh WSDL thực tế; tránh làm hỏng schema do thay thế chuỗi thiếu kiểm soát.

### 7.2. Cấu trúc JAR và WAR khác nhau

| Hình thức đóng gói | Vị trí resources thường gặp | Ghi chú |
| --- | --- | --- |
| Spring Boot executable JAR | `BOOT-INF/classes/wsdl/...`, `BOOT-INF/classes/xsd/...` | Nạp qua classpath |
| Spring Boot WAR | `WEB-INF/classes/wsdl/...`, `WEB-INF/classes/xsd/...` | Phụ thuộc servlet container/cấu hình |
| JAR thường | `wsdl/...`, `xsd/...` ở root archive | Phụ thuộc quy tắc packaging/classpath |

Không cố hardcode đường dẫn bên trong archive. `ClassPathResource("wsdl/orders.wsdl")` giúp cùng một cấu hình có thể làm việc trên nhiều hình thức phân phối.

## 8. Kết nối JAXB với endpoint và SOAP client

Tài nguyên hợp đồng chỉ có giá trị khi ứng dụng thật sự dùng đúng namespace và model.

### 8.1. Cấu hình `Jaxb2Marshaller`

Giả sử XJC sinh các class vào package `com.example.orders.ws.v1`, có `ObjectFactory` hoặc metadata JAXB phù hợp:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class JaxbConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.ws.v1");
        return marshaller;
    }
}
~~~

Khi dùng `setContextPath`, JAXB phải tìm được context trong package đó. Nếu đổi package lúc sinh mã nhưng không đổi cấu hình, có thể gặp lỗi kiểu “package doesn't contain ObjectFactory.class or jaxb.index” hoặc không marshal được phần tử gốc.

Tùy dự án, có thể dùng `setClassesToBeBound(...)` hoặc `setPackagesToScan(...)` thay cho context path. Chọn **một cơ chế khởi tạo tương thích với model**, tránh quét package quá rộng làm startup chậm hoặc vô tình liên kết nhiều namespace/version.

### 8.2. Endpoint định tuyến theo QName, không theo tên file

~~~java
@Endpoint
public class OrderEndpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrderEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {

        OrderInfo order = service.getById(request.getOrderId());
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(order.id());
        response.setState(order.state());
        return response;
    }
}
~~~

`OrderService` và `OrderInfo` là kiểu nghiệp vụ minh họa. Đoạn code giả định JAXB generator sinh các lớp có thể marshal làm phần tử root; nếu kiểu cần `JAXBElement`, chữ ký endpoint hoặc mã chuyển đổi cần điều chỉnh. Trong Spring-WS thực tế cần đảm bảo endpoint adapter/marshaller được cấu hình đúng.

Spring-WS chọn method theo `@PayloadRoot(namespace, localPart)` trên phần tử gốc trong SOAP Body. Kể cả `orders.wsdl` được công bố thành công, request sai namespace vẫn không khớp endpoint. Tương tự, tên file `orders-v1.xsd` không phải điều kiện định tuyến.

### 8.3. Máy khách dùng cùng hợp đồng

~~~java
@Bean
public WebServiceTemplate ordersWebServiceTemplate(
        Jaxb2Marshaller ordersMarshaller) {
    WebServiceTemplate template = new WebServiceTemplate();
    template.setMarshaller(ordersMarshaller);
    template.setUnmarshaller(ordersMarshaller);
    template.setDefaultUri("http://localhost:8080/ws");
    return template;
}
~~~

Client có thể dùng `marshalSendAndReceive(request)` để gửi payload JAXB, rồi đọc response. Nếu XJC sinh `JAXBElement` thay vì class root trực tiếp, hãy tạo request bằng `ObjectFactory` phù hợp. Với SOAP 1.1, WSDL có thể yêu cầu `SOAPAction`; cần cấu hình callback `SoapActionCallback` hoặc cơ chế tương đương nếu đối tác thực sự yêu cầu.

Không hardcode URL localhost cho production. Đưa endpoint URL, timeout, TLS/truststore và chính sách WS-Security vào cấu hình triển khai. Các tham số này thuộc runtime, khác với hợp đồng XSD/WSDL version hóa.

## 9. Kiểm tra nội dung artifact và URL công bố

Bước kiểm tra quan trọng không phải chỉ “build không lỗi” mà là **artifact thật chứa đủ tệp và dịch vụ khởi động từ artifact đó**.

### 9.1. Kiểm tra classpath trong JAR

Ví dụ lệnh tham khảo khi dùng Maven/Java, chọn tên file thực tế của dự án:

~~~bash
./mvnw clean package
jar tf target/orders-soap.jar
~~~

Trên Windows có thể dùng `mvnw.cmd package` và `jar tf ...`. **Không cần chạy những lệnh này để đọc bài**; đây là hướng dẫn kiểm tra trong dự án của bạn.

Với Spring Boot executable JAR, danh sách nên có các mục tương đương:

~~~text
BOOT-INF/classes/wsdl/orders.wsdl
BOOT-INF/classes/xsd/orders-v1.xsd
BOOT-INF/classes/com/example/orders/ws/v1/ObjectFactory.class
BOOT-INF/classes/com/example/orders/ws/v1/GetOrderRequest.class
BOOT-INF/classes/com/example/orders/ws/v1/GetOrderResponse.class
~~~

Các class và đường dẫn cụ thể tùy công cụ sinh. Nếu artifact thiếu XSD/WSDL, hãy kiểm tra quy tắc resource copy và packaging; nếu thiếu JAXB classes, hãy kiểm tra plugin XJC, generated source roots và phase compile.

Một smoke test hữu ích là **chạy chính JAR/WAR đã đóng gói ở môi trường sạch**, thay vì chỉ chạy từ IDE với filesystem mã nguồn.

### 9.2. Kiểm tra WSDL và XSD qua HTTP

Khi dịch vụ đang chạy với base URL local như ví dụ:

~~~bash
curl -i http://localhost:8080/ws/orders.wsdl
curl -i http://localhost:8080/ws/orders-v1.xsd
~~~

Kiểm tra:

1. HTTP status thành công, body có XML thực sự chứ không phải HTML trang lỗi.
2. WSDL chứa operation `GetOrder`, input/output và binding SOAP 1.1 đúng.
3. WSDL chứa `soap:address` mà client truy cập được.
4. `xs:include schemaLocation="orders-v1.xsd"` giải quyết thành URL XSD tải được.
5. XSD và WSDL cùng namespace, kiểu, tên root, phiên bản.
6. Client generator đọc được WSDL **cùng toàn bộ các import/include**.

Với reverse proxy, lặp lại các bước trên qua **public HTTPS URL**, vì cùng một ứng dụng có thể hoạt động nội bộ nhưng công bố địa chỉ không đúng cho bên ngoài.

### 9.3. Thử một SOAP request end-to-end

Ví dụ request SOAP 1.1:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderRequest>
      <ord:orderId>ORD-42</ord:orderId>
    </ord:GetOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Response thành công theo hợp đồng:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
  <soapenv:Body>
    <ord:GetOrderResponse>
      <ord:orderId>ORD-42</ord:orderId>
      <ord:state>CREATED</ord:state>
    </ord:GetOrderResponse>
  </soapenv:Body>
</soapenv:Envelope>
~~~

Đối với hệ thống thật, test thêm dữ liệu không hợp lệ để thấy rõ cách schema validation/interceptor và exception resolver trả **SOAP Fault**. Đừng coi HTTP 200 hoặc việc đọc WSDL thành công là bằng chứng endpoint xử lý đúng.

## 10. Lỗi đóng gói và triển khai thường gặp

| Triệu chứng | Nguyên nhân có khả năng | Cách kiểm tra hoặc khắc phục |
| --- | --- | --- |
| Chạy trong IDE được, chạy JAR báo không tìm thấy XSD | Dùng `File("src/main/resources/...")` hoặc resource bị exclude | Kiểm tra artifact, dùng `ClassPathResource` |
| `getFile()` lỗi khi chạy Boot JAR | Tệp nằm trong archive, không có file path vật lý | Dùng `getInputStream()` hoặc Resource API |
| `GET /ws/orders.wsdl` trả 404 | WSDL bean name, servlet mapping/context path hoặc config autoconfiguration lệch | Kiểm tra bean, servlet và URL thực |
| WSDL tải được, công cụ sinh client báo thiếu XSD | `schemaLocation` tham chiếu URL không tồn tại; thiếu XsdSchema bean | Mở URL schema thực từ WSDL |
| XSD được đưa vào JAR nhưng không tải qua HTTP | Classpath không tự tạo static URL cho Spring-WS | Công bố bằng `XsdSchema` bean hoặc HTTP handler có chủ đích |
| JAXB không tạo context được | Package sai, thiếu `ObjectFactory`/`jaxb.index`, class thiếu trong artifact | Kiểm tra generated sources và classpath |
| JAXB dùng `javax.xml.bind` với runtime Jakarta | Sai thế hệ dependency/plugin sinh mã | Dùng XJC/JAXB tương thích Spring Boot 3+/Spring-WS 4.x |
| Client gửi đúng class Java nhưng endpoint không chạy | Payload XML sai namespace/local name | So QName trên wire với `@PayloadRoot` |
| WSDL dùng HTTPS ở ngoài nhưng address là HTTP nội bộ | Proxy/forwarded headers hoặc location transform sai | Tải WSDL qua public URL và sửa cấu hình |
| Một `xs:import` ở tầng sâu trả 404 | Cây schema liên kết chưa được công bố đủ | Duyệt toàn bộ include/import và kiểm thử client generator |
| Build xanh nhưng một branch không có generated JAXB | Plugin chỉ chạy ở profile IDE/local, không nằm trong lifecycle CI | Kiểm tra Maven/Gradle build config, generated source roots |
| SOAP Fault chứa chi tiết nhạy cảm | Logging/fault resolver chưa được cấu hình đúng | Che dữ liệu, dùng lỗi hợp đồng rõ ràng |
| WSDL thay đổi bất ngờ sau nâng phiên bản | Sinh WSDL động phụ thuộc framework/config | Diff WSDL, cân nhắc công bố tĩnh |

### 10.1. Một chẩn đoán theo thứ tự

Khi client thông báo “không gọi được SOAP service”, hãy kiểm tra theo hướng từ **artifact đến network**:

~~~mermaid
flowchart TD
    A["Artifact có WSDL/XSD/JAXB classes?"] --> B{"Có đủ?"}
    B -- "Không" --> C["Sửa resource copy / XJC / packaging"]
    B -- "Có" --> D["GET WSDL từ public URL"]
    D --> E{"WSDL tải được?"}
    E -- "Không" --> F["Kiểm tra servlet / bean name / routing"]
    E -- "Có" --> G["Giải quyết mọi XSD include/import"]
    G --> H{"Mọi XSD tải được?"}
    H -- "Không" --> I["Sửa HTTP mapping và schemaLocation"]
    H -- "Có" --> J["POST SOAP theo hợp đồng"]
    J --> K["Kiểm tra QName, JAXB, validation, security và Fault"]
~~~

Cách này giúp tách lỗi thiếu tài nguyên với lỗi XML, protocol hoặc nghiệp vụ. Chẳng hạn một lỗi “endpoint không tìm thấy” có thể bắt nguồn từ QName sai, trong khi một lỗi “schema not found” do URL XSD 404 là vấn đề công bố hợp đồng.

## 11. Bảo mật và quản lý tài nguyên theo môi trường

WSDL/XSD là **tài liệu hợp đồng** và thường có thể được cung cấp cho đối tác đã được phép. Nhưng keystore, private key và password phục vụ WS-Security hoặc TLS là **tài nguyên nhạy cảm**, cần một quy trình cấp phát khác.

- **TLS/mTLS:** cấu hình truststore, keystore và chứng chỉ bằng secret manager, volume hoặc cơ chế phân phối bí mật của hạ tầng. Quản lý quyền đọc, gia hạn và thay thế chứng chỉ.
- **WS-Security:** dùng interceptor/thư viện chuyên trách như WSS4J để xử lý XML Signature, encryption, token và timestamp; không chỉ đưa file chứng chỉ vào classpath rồi coi bảo mật đã hoàn chỉnh.
- **XML parser:** chặn XXE/đọc DTD bên ngoài theo parser/provider sử dụng, giới hạn kích thước/depth và thời gian xử lý tài liệu.
- **Validation:** dùng `PayloadValidatingInterceptor` hoặc cơ chế schema validation tương đương để từ chối payload sai XSD; vẫn phải kiểm tra nghiệp vụ và quyền truy cập.
- **WSDL public endpoint:** cân nhắc chính sách truy cập tài liệu hợp đồng, tránh để URL nội bộ hoặc metadata nhạy cảm lọt vào tài liệu phát hành.
- **SOAP Fault và logging:** trả mã lỗi rõ ràng, không lộ stack trace, credential, token hay toàn bộ payload nhạy cảm.

Không nên bundle private key vào JAR chung cho mọi môi trường. Nếu cần nhúng một **chứng chỉ công khai** hoặc schema để xác thực danh tính đối tác, đó là quyết định triển khai có kiểm soát, cần cơ chế cập nhật khi certificate rotation diễn ra.

## 12. Kiểm thử khả năng tương thích sau đóng gói

Các bài test unit chỉ chạy trên class Java có thể bỏ sót lỗi WSDL/XSD nằm trong archive hoặc URL HTTP không khớp. Nên chia kiểm thử theo lớp:

| Lớp kiểm thử | Trọng tâm | Ví dụ |
| --- | --- | --- |
| **Build artifact** | Tệp WSDL/XSD và JAXB classes có trong JAR/WAR | Kiểm tra nội dung archive sau package |
| **Resource startup** | `ClassPathResource` đọc được tài nguyên từ artifact | Smoke test chạy packaged app |
| **WSDL/XSD publication** | GET WSDL, mọi schemaLocation đều giải quyết được | HTTP integration test |
| **SOAP server** | Request đúng root QName được định tuyến và trả response hợp XSD | `MockWebServiceClient` |
| **SOAP client** | JAXB marshal đúng XML và đọc response/Fault | `MockWebServiceServer` |
| **Fault handling** | Lỗi schema, lỗi nghiệp vụ sinh SOAP Fault theo hợp đồng | Fault code/detail assertions |
| **Security** | TLS/WS-Security được xác thực với chứng chỉ và timestamp | Test certificate, signature, policy |
| **Interoperability** | Client khác nền tảng sinh từ WSDL công bố gọi được | .NET/Java client thực tế |

Các ca tối thiểu:

1. `orders.wsdl` và `orders-v1.xsd` có mặt trong artifact; class JAXB cần thiết cũng tồn tại.
2. Ứng dụng khởi động từ JAR/WAR mà không phụ thuộc đường dẫn `src/main/resources` trên máy build.
3. Tải WSDL qua đúng domain/path public; mọi `xs:include` và `xs:import` đều không lỗi.
4. Client sinh từ WSDL tạo request `{urn:example:orders:v1}GetOrderRequest`, endpoint nhận đúng và trả `GetOrderResponse`.
5. Request thiếu `orderId` bị từ chối khi bật XSD validation; lỗi nghiệp vụ trả SOAP Fault thay vì response thành công.
6. Nâng phiên bản XSD/WSDL có kiểm thử client cũ → server mới và client mới → server cũ theo cam kết tương thích.
7. Khi bật WS-Security/TLS, thông điệp sai chữ ký, timestamp hoặc chứng chỉ không được tin cậy bị từ chối.

Kiểm tra **XML trên đường truyền** quan trọng hơn việc chỉ xác minh object JAXB trong Java, bởi đối tác .NET hoặc nền tảng khác dùng WSDL, XSD và SOAP XML chứ không dùng class của bạn.

## 13. Quy trình thực hiện trong một dự án mới

Một quy trình thực dụng có thể áp dụng:

1. **Khóa hợp đồng dữ liệu:** viết XSD với QName, request/response, type, cardinality, rule/fault; quyết định dùng WSDL tĩnh hay sinh động.
2. **Đặt tài nguyên theo quy ước:** XSD dưới `src/main/resources/xsd`; WSDL tĩnh dưới `src/main/resources/wsdl`; `.xjb` trong thư mục build-time riêng.
3. **Cấu hình XJC Jakarta tương thích:** sinh Java từ XSD, giữ generated sources trong build output, không sửa tay.
4. **Đăng ký Spring-WS:** cấu hình servlet, bean WSDL, bean XSD, JAXB marshaller, endpoint và SOAP client theo cùng QName/namespace.
5. **Kiểm thử từ classpath:** đọc WSDL/XSD bằng Resource API, không truy cập dựa trên source directory.
6. **Đóng gói rồi chạy artifact:** xác minh các entry WSDL/XSD/JAXB trong JAR/WAR và khởi động môi trường sạch.
7. **Kiểm tra URL công bố:** tải WSDL, giải quyết include/import, kiểm tra soap:address qua tuyến truy cập thật.
8. **Kiểm tra trao đổi SOAP:** gửi request hợp lệ/sai, xác nhận response, SOAP Fault, interceptor/WS-Security và chứng chỉ theo chính sách.
9. **Chốt phiên bản phát hành:** lưu WSDL/XSD đã xác minh, diff các thay đổi và thử client đối tác trước triển khai.

### Bài tập vận dụng

**Bài 1.** Một file `orders.xsd` nằm trong `src/main/resources/xsd`, nhưng ứng dụng tìm bằng `new File("src/main/resources/xsd/orders.xsd")`. Giải thích vì sao chạy từ IDE được nhưng có thể lỗi trong Boot JAR; viết API thay thế.

**Bài 2.** WSDL được tải từ `https://api.example.com/ws/orders.wsdl` và tham chiếu `schemaLocation="orders-v1.xsd"`. Client sẽ thử lấy XSD từ URL nào? Bean nào trong Spring-WS có thể công bố tài nguyên tại URL đó?

**Bài 3.** Đối tác thay `urn:example:orders:v1` bằng `urn:example:orders:v2` nhưng giữ nguyên tên file `orders.wsdl`. Những cấu hình và kiểm thử nào cần cập nhật, kể cả `@PayloadRoot`, JAXB package, schema và phiên bản client?

**Bài 4.** Sau build, archive có `orders.wsdl` và `orders-v1.xsd` nhưng không có `ObjectFactory.class`. Hãy chỉ ra các bước của build liên quan và lý do `Jaxb2Marshaller.setContextPath(...)` có thể thất bại.

**Bài 5.** Khi deploy sau reverse proxy, WSDL trả `soap:address` trỏ `http://localhost:8080/ws` dù endpoint public là HTTPS. Vì sao có thể xảy ra? Cần kiểm tra cấu hình servlet, transform, forwarded headers và WSDL như thế nào?

**Bài 6.** Nhóm dự án muốn đưa private key WS-Security vào `src/main/resources` vì “cần có trong JAR”. Hãy mô tả giải pháp cấp phát bí mật bằng môi trường triển khai và phân biệt với XSD/WSDL công bố cho đối tác.

**Ghi nhớ:** Đóng gói Spring-WS đúng nghĩa là bảo đảm **tài nguyên contract trên classpath, mã JAXB đã biên dịch, URL WSDL/XSD công bố và SOAP endpoint thực tế** cùng nói một ngôn ngữ. `.xjb` chủ yếu phục vụ build; `ClassPathResource` phục vụ runtime; WSDL/XSD có trong JAR vẫn cần ánh xạ HTTP; và chỉ kiểm thử artifact chạy thật mới xác nhận tích hợp SOAP ổn định.
