# Marshalling, unmarshalling và cấu hình JAXB phù hợp phiên bản Java

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối HTTP client, cơ sở dữ liệu, cache, message broker và các adapter Spring Integration thành các luồng nghiệp vụ có hợp đồng rõ ràng. Nhiều hệ thống ERP, ngân hàng và đối tác lâu năm vẫn sử dụng **SOAP/XML** với WSDL/XSD. Dữ liệu trao đổi không chỉ cần là XML hợp lệ về cú pháp: tên element, namespace, kiểu dữ liệu, thứ tự và ý nghĩa nghiệp vụ phải khớp hợp đồng.

**JAXB** (Java Architecture for XML Binding, hiện thuộc Jakarta XML Binding) hỗ trợ hai chiều:

- **Marshalling:** chuyển object Java thành XML theo binding metadata.
- **Unmarshalling:** đọc XML và tạo object Java theo binding metadata.

Trong Spring, `Jaxb2Marshaller` của **Spring OXM** bọc JAXB để kết nối với `WebServiceTemplate` hoặc một luồng tích hợp XML. Dù tên có chữ “2”, class này vẫn tồn tại trong Spring hiện đại và làm việc với hệ JAXB/Jakarta XML Binding phù hợp phiên bản framework.

Bài thuộc chương **SOAP và XML**, đề mục **Marshalling, unmarshalling và cấu hình JAXB phù hợp phiên bản Java**. Bài tập trung vào mapping DTO, lựa chọn API/runtime theo Java 8, 11, 17 và các phiên bản mới; namespace và XSD, bảo mật parsing XML, SOAP transport, lỗi, timeout, idempotency, kiểm thử và observability.

Sau bài học, bạn có thể:

1. Phân biệt JAXB API, implementation/runtime, XJC và các API XML thuộc JDK.
2. Chọn đúng `javax.xml.bind` hoặc `jakarta.xml.bind` theo Java/Spring Boot.
3. Tạo DTO với `@XmlRootElement`, `@XmlAccessorType`, `@XmlElement` và `@XmlType`.
4. Marshall và unmarshal bằng JAXB thuần hoặc Spring `Jaxb2Marshaller`.
5. Sử dụng `JAXBElement`/`ObjectFactory` cho generated classes không có root annotation.
6. Cấu hình Spring-WS SOAP client và hiểu ranh giới SOAP Envelope/Body.
7. Validation với XSD, chống XXE, phân loại SOAP Fault và lỗi mapping.
8. Kiểm thử XML contract độc lập với server và vận hành adapter có retry/idempotency.

> **Ranh giới:** JAXB biến đổi object ↔ XML, không tự tạo SOAP Envelope, ký WS-Security, xác thực đối tác, chạy database transaction hay bảo đảm xử lý một lần duy nhất.

## 1. JAXB nằm ở đâu trong luồng tích hợp?

~~~mermaid
flowchart LR
    A["HTTP/Broker Order event"] --> B["Order service"]
    B --> C["Business DTO → SOAP DTO"]
    C --> D["JAXB marshalling"]
    D --> E["SOAP Body"]
    E --> F["Spring WebServiceTemplate"]
    F --> G["ERP SOAP endpoint"]
    G --> H["SOAP response / Fault"]
    H --> I["JAXB unmarshalling"]
    I --> J["Response DTO → Business result"]
    B -.-> K["SQL inbox/outbox + transaction"]
    F -.-> L["Tracing, metrics, retry"]
~~~

Ba lớp có trách nhiệm riêng:

| Lớp | Đầu vào/đầu ra | Trách nhiệm |
| --- | --- | --- |
| **XML contract** | XSD/WSDL | QName, element order, minOccurs, types, schema version |
| **Object/XML mapping** | Java ↔ XML payload | JAXB, annotations, `Jaxb2Marshaller` |
| **SOAP/HTTP transport** | Envelope, header, action, TLS, response/fault | Spring-WS, message sender, security |

JAXB có thể sử dụng cho **XML không phải SOAP**, ví dụ file import, payload trên message broker hoặc HTTP endpoint trả XML. Một class JAXB không tự mở endpoint server hoặc phát HTTP request.

## 2. Java version và JAXB: chọn đúng thế hệ

### 2.1. Tại sao Java 17 không tìm thấy JAXB?

Một thay đổi lịch sử quan trọng là JAXB đã từng có trong JDK, nhưng bị loại khỏi JDK kể từ Java 11.

| Nền tảng | Tình trạng JAXB trong JDK | Package thường dùng |
| --- | --- | --- |
| **Java 8** | Có JAXB 2.x tích hợp | `javax.xml.bind.*` |
| **Java 9–10** | Module `java.xml.bind` bị deprecated và không được resolve mặc định theo cách giống Java 8 | `javax.xml.bind.*` |
| **Java 11+** | Module JAXB đã **bị loại bỏ** | Phải dùng thư viện JAXB ngoài JDK |
| **Spring Boot 2.x / Framework 5.x** | Theo JDK/build; hệ JAXB cũ | Chủ yếu `javax.xml.bind.*` |
| **Spring Boot 3.x / Framework 6.x** | Boot 3 yêu cầu Java 17+ | `jakarta.xml.bind.*` |
| **Spring Boot 4.x / Framework 7.x** | Hệ Spring hiện đại | `jakarta.xml.bind.*` |

Những điểm dễ nhầm:

- `jakarta.xml.bind-api` có các bản chuyển tiếp 2.3.x mà package Java vẫn là `javax.xml.bind`; **tên artifact không đủ** để xác nhận namespace.
- Từ **Jakarta XML Binding 3.0**, package JAXB chuyển sang `jakarta.xml.bind`; JAXB 4.x tiếp tục dùng package mới.
- `javax.xml.parsers`, `javax.xml.transform`, `javax.xml.namespace.QName` và `javax.xml.validation` **vẫn** thuộc module `java.xml` trong JDK mới. Không thay tất cả `javax.xml` thành `jakarta.xml`.
- Thêm flag `--add-modules java.xml.bind` không thể lấy lại JAXB trên JDK 17 vì module này không còn tồn tại.
- JAXB API và runtime là hai phần riêng: **compile được không có nghĩa tìm thấy provider khi chạy**.

### 2.2. Dependency theo hệ Jakarta, ví dụ Boot 3 + Java 17

Gradle Groovy DSL khi tích hợp SOAP bằng Spring Web Services:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web-services'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'
}
~~~

Với ứng dụng chỉ cần OXM mà không cần SOAP transport:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-oxm'
    implementation 'jakarta.xml.bind:jakarta.xml.bind-api'
    runtimeOnly 'org.glassfish.jaxb:jaxb-runtime'
}
~~~

Đây là **minh họa cho thế hệ Jakarta**. Một số starter có thể đã kéo các thư viện JAXB transitively; nên kiểm tra dependency tree thực tế và sử dụng BOM/plugin dependency management của Spring Boot thay vì tự ghép version không tương thích.

Trong project cũ Boot 2/JAXB 2, imports là:

~~~java
// Java/Spring legacy, JAXB 2.x:
import javax.xml.bind.JAXBContext;
import javax.xml.bind.Marshaller;
import javax.xml.bind.Unmarshaller;
~~~

Trong Boot 3/4:

~~~java
// Jakarta XML Binding 3/4:
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import jakarta.xml.bind.Unmarshaller;
~~~

**Không trộn** annotation `javax.xml.bind.annotation.XmlRootElement` từ code cũ với `jakarta.xml.bind.JAXBContext` của runtime mới. Java xem chúng là các kiểu annotation khác nhau; mapping có thể không nhận diện class đúng.

### 2.3. Quy trình quyết định version an toàn

1. Xác nhận **Java runtime** của container/server, không chỉ source level khi compile.
2. Xác nhận dòng **Spring Boot + Spring Framework + Spring-WS** đang triển khai.
3. Chọn JAXB API/runtime **cùng thế hệ**, ví dụ Jakarta JAXB 4 API/runtime 4 phù hợp BOM.
4. Nếu dùng XJC sinh mã, chọn **XJC cùng thế hệ JAXB** để generated imports đúng.
5. Kiểm tra thư viện cũ kéo `javax.xml.bind` và thư viện mới kéo `jakarta.xml.bind`, tránh một model chạy qua hai cơ chế khác nhau.
6. Có contract tests chạy trên đúng JDK và dependency graph của production.

Không tự pin JAXB version cao hơn BOM chỉ vì đó là bản mới nhất. Với Boot 3 hoặc Boot 4, cần đối chiếu Jakarta/JAXB và transport version thực sự được hỗ trợ.

## 3. XML contract, namespace và QName

Giả sử ERP yêu cầu payload:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<m:SubmitOrderRequest xmlns:m="urn:example:orders:v1">
  <m:orderId>ORD-100</m:orderId>
  <m:amountMinor>1890000</m:amountMinor>
  <m:currency>VND</m:currency>
</m:SubmitOrderRequest>
~~~

Các điểm cần tôn trọng:

- Root element có local name `SubmitOrderRequest` và namespace URI `urn:example:orders:v1`.
- Child elements được namespace-qualified theo XSD này.
- Thứ tự child elements có thể bắt buộc vì XSD dùng `xs:sequence`.
- Prefix `m` chỉ là bí danh của namespace URI; prefix khác vẫn có thể là **cùng QName** nếu URI và local name không thay đổi.
- `amountMinor` dùng số nguyên theo đơn vị tiền nhỏ nhất do hợp đồng tự định nghĩa, không tự động đồng nghĩa `xs:decimal`.
- Encoding XML và HTTP charset phải nhất quán; UTF-8 phù hợp nội dung tiếng Việt.

**Không so sánh XML đúng/sai chỉ bằng chuỗi byte hoặc prefix.** Nên parse bằng parser an toàn, so expanded QName và validate XSD.

## 4. DTO JAXB với annotation

Một class thể hiện payload:

~~~java
// SubmitOrderRequest.java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
        name = "SubmitOrderRequest",
        namespace = "urn:example:orders:v1")
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(
        name = "SubmitOrderRequestType",
        namespace = "urn:example:orders:v1",
        propOrder = {"orderId", "amountMinor", "currency"})
public class SubmitOrderRequest {

    @XmlElement(
            name = "orderId",
            namespace = "urn:example:orders:v1",
            required = true)
    private String orderId;

    @XmlElement(
            name = "amountMinor",
            namespace = "urn:example:orders:v1",
            required = true)
    private Long amountMinor;

    @XmlElement(
            name = "currency",
            namespace = "urn:example:orders:v1",
            required = true)
    private String currency;

    public SubmitOrderRequest() { }

    public SubmitOrderRequest(
            String orderId,
            Long amountMinor,
            String currency) {
        this.orderId = orderId;
        this.amountMinor = amountMinor;
        this.currency = currency;
    }

    public String getOrderId() { return orderId; }
    public Long getAmountMinor() { return amountMinor; }
    public String getCurrency() { return currency; }

    public void setOrderId(String value) { this.orderId = value; }
    public void setAmountMinor(Long value) { this.amountMinor = value; }
    public void setCurrency(String value) { this.currency = value; }
}
~~~

| Annotation | Vai trò |
| --- | --- |
| `@XmlRootElement` | Định danh XML root QName của object |
| `@XmlAccessorType(FIELD)` | Map các fields, tránh phụ thuộc public getters |
| `@XmlType(propOrder=...)` | Đặt thứ tự elements theo complex type |
| `@XmlElement(name, namespace)` | Xác định element tương ứng với field |
| `@XmlElement(required=true)` | Thông tin ràng buộc cho schema/binding metadata |

**Cảnh báo:** `required=true` không có nghĩa JAXB runtime **tự động fail** khi XML thiếu field. Một XML thiếu `amountMinor` vẫn có thể unmarshall thành object có giá trị `null` nếu không bật schema validation. Cần XSD validation và business validation.

Dùng constructor không tham số (public hoặc protected theo yêu cầu binding), mutable fields/setters phù hợp giúp tránh những bất ngờ với reflection. Không mặc định một Java `record` immutable có thể được JAXB mọi phiên bản deserialize mà không có adapter tùy biến.

### 4.1. Namespace mặc định tại package-info.java

Nếu một package gồm nhiều DTO cùng namespace:

~~~java
// package-info.java
@jakarta.xml.bind.annotation.XmlSchema(
        namespace = "urn:example:orders:v1",
        elementFormDefault =
                jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED)
package com.example.integration.erp.xml;
~~~

Khi dùng schema package-level, không cần lặp namespace trên mọi child element nếu cấu hình annotation đủ rõ. Tuy nhiên, chỉ dùng `QUALIFIED` khi XSD thật quy định tương ứng; các schema có element unqualified cần xử lý khác.

Tên package Java không quyết định namespace URI. Đổi `urn:example:orders:v1` sang `urn:example:orders:v2` có thể là breaking change ngay cả khi tên class/field Java không đổi.

## 5. JAXB thuần: marshalling Java → XML

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Marshaller;
import java.io.StringWriter;

public class BasicMarshalExample {

    public String marshal(
            SubmitOrderRequest request) throws Exception {

        JAXBContext context =
                JAXBContext.newInstance(SubmitOrderRequest.class);

        Marshaller marshaller =
                context.createMarshaller();

        marshaller.setProperty(
                Marshaller.JAXB_FORMATTED_OUTPUT, Boolean.TRUE);
        marshaller.setProperty(
                Marshaller.JAXB_ENCODING, "UTF-8");

        StringWriter output = new StringWriter();
        marshaller.marshal(request, output);
        return output.toString();
    }
}
~~~

JAXB có thể tạo XML tương đương với prefix/whitespace khác; điều đó không nhất thiết vi phạm XML contract.

**Thread safety và hiệu năng:**

- `JAXBContext` được thiết kế để dùng lại; tạo context liên tục tốn thời gian phân tích metadata.
- `Marshaller` và `Unmarshaller` **không thread-safe**. Đừng lưu một instance duy nhất rồi chia sẻ cho nhiều HTTP requests/broker workers.
- Với JAXB thuần, cache `JAXBContext` và tạo Marshaller/Unmarshaller mới theo thao tác.
- Với Spring, cấu hình `Jaxb2Marshaller` làm singleton bean để wrapper quản lý việc tạo mapper phù hợp.

Marshalling là **chuyển đổi cấu trúc**, không kiểm tra business rule. Ví dụ `amountMinor=-50` không trở thành hợp lệ chỉ vì JAXB phát XML thành công.

## 6. Unmarshalling XML → Java

Ví dụ XML tin cậy trong unit test:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;

public class BasicUnmarshalExample {

    public SubmitOrderRequest parseTrusted(
            String xml) throws Exception {

        JAXBContext context =
                JAXBContext.newInstance(SubmitOrderRequest.class);

        Unmarshaller unmarshaller =
                context.createUnmarshaller();

        return (SubmitOrderRequest)
                unmarshaller.unmarshal(new StringReader(xml));
    }
}
~~~

**Không dùng nguyên cách này cho XML không đáng tin cậy** nếu chưa kiểm soát DTD/external entity, kích thước, độ sâu và validation. Một số JAXB provider tạo XML parser theo cấu hình khác nhau; cần biết parser nào xử lý dữ liệu ngay từ đầu.

Sau unmarshal, kiểm tra `null`, giá trị bắt buộc, giới hạn độ dài, enum và các business invariants. Đừng truyền raw JAXB DTO trực tiếp làm domain aggregate nếu chưa validate/map.

### 6.1. JAXBElement khi không có XmlRootElement

Một số class do XJC sinh từ XSD có `@XmlType` nhưng không có `@XmlRootElement`. Global element được biểu diễn bằng `JAXBElement<T>` có QName.

Đọc với declared type:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import javax.xml.transform.stream.StreamSource;

JAXBContext context =
        JAXBContext.newInstance(SubmitOrderRequest.class);

Unmarshaller unmarshaller =
        context.createUnmarshaller();

JAXBElement<SubmitOrderRequest> element =
        unmarshaller.unmarshal(
                new StreamSource(new StringReader(xml)),
                SubmitOrderRequest.class);

SubmitOrderRequest request = element.getValue();
~~~

Biến `xml` ở ví dụ này là XML **đã tin cậy** hoặc đã được parse/validate an toàn. Cách gọi có declared type giúp map vào class mong muốn, nhưng **không tự xác minh root QName**. Cần đối chiếu `element.getName()` với QName trong hợp đồng.

Khi marshal một object không có root annotation:

~~~java
import jakarta.xml.bind.JAXBElement;
import javax.xml.namespace.QName;

JAXBElement<SubmitOrderRequest> root =
        new JAXBElement<>(
                new QName(
                        "urn:example:orders:v1",
                        "SubmitOrderRequest"),
                SubmitOrderRequest.class,
                request);
~~~

`javax.xml.namespace.QName` vẫn thuộc JDK mới, không bị chuyển thành `jakarta`. Nếu dùng generated classes, `ObjectFactory` thường có `create...(...)` để tạo wrapper đúng namespace; nên dùng method đó thay vì tự ghép QName.

## 7. XSD, WSDL và generated Java classes

Khi payload lớn hoặc nhiều kiểu phức tạp, nên sinh binding từ XSD/WSDL chính thức thay vì tự viết mọi annotation:

~~~text
WSDL + XSD (versioned)
    ↓
JAXB/XJC code generation
    ↓
@Generated package + ObjectFactory + XmlSchema
    ↓
Jaxb2Marshaller / JAXBContext
    ↓
SOAP XML payload
~~~

Một XSD mẫu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1"
    xmlns:tns="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="amountMinor" type="xs:long"/>
        <xs:element name="currency" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="accepted" type="xs:boolean"/>
        <xs:element name="reference" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Mục đích của code generation:

- Bảo toàn tên element/attribute, namespace và thứ tự theo XSD.
- Map các loại như enum, choice, extension, lists và generated factories.
- Giảm nguy cơ manual DTO không theo kịp hợp đồng đối tác.

**Version XJC phải tương thích với runtime:**

- Project Jakarta JAXB mới cần XJC sinh imports `jakarta.xml.bind.annotation.*`.
- Project JAXB 2 cũ dùng `javax.xml.bind.annotation.*`.
- Trên Java 11+, công cụ `xjc` không còn là một phần sẵn có của JDK; cài/build plugin phù hợp.
- Không sửa generated sources trực tiếp. Pin WSDL/XSD và binding customization (`.xjb`) trong build, tạo version mới có kiểm soát.
- Kiểm tra XML fixtures từ đối tác; một DTO round-trip thành công có thể chỉ chứng minh hai chiều của **cùng mapping sai**.

### 7.1. Các thay đổi XSD có thể breaking

| Thay đổi | Ảnh hưởng |
| --- | --- |
| Đổi targetNamespace hoặc root element | QName không khớp |
| Đổi minOccurs từ 0 sang 1 | XML cũ thiếu field |
| Đổi thứ tự xs:sequence | XSD validation fail |
| Đổi xs:decimal sang xs:long | Mất khả năng biểu diễn giá trị có phần thập phân |
| Đổi timezone constraint | Timestamp có thể bị diễn giải sai |
| Thêm enum value | Client cũ có thể không parse được |
| Thay nillable/optional | Khác biệt giữa null, absent và empty element |

Các thay đổi phải được kiểm tra bằng contract tests và kế hoạch compatibility, không chỉ biên dịch Java thành công.

## 8. Spring OXM Jaxb2Marshaller

`Jaxb2Marshaller` là một adapter OXM từ JAXB sang interface `Marshaller`/`Unmarshaller` của Spring:

~~~java
import org.springframework.oxm.Marshaller;
import org.springframework.oxm.Unmarshaller;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
~~~

Tạo bean cho DTO đã khai báo:

~~~java
// ErpXmlConfiguration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration(proxyBeanMethods = false)
public class ErpXmlConfiguration {

    @Bean
    Jaxb2Marshaller erpJaxbMarshaller() {
        Jaxb2Marshaller m = new Jaxb2Marshaller();
        m.setClassesToBeBound(
                SubmitOrderRequest.class,
                SubmitOrderResponse.class);

        m.setSupportDtd(false);
        m.setProcessExternalEntities(false);
        return m;
    }
}
~~~

`SubmitOrderResponse` là DTO phản hồi tương ứng, do ứng dụng viết hoặc XJC generate theo XSD. Bean wrapper được chia sẻ trong Spring; JAXB context được chuẩn bị theo cấu hình, không có nghĩa `Unmarshaller` không thread-safe được chia sẻ trực tiếp.

### 8.1. Ba cách tạo JAXB context

| Cách | Phù hợp với | Lưu ý |
| --- | --- | --- |
| `setClassesToBeBound(...)` | Một số JAXB DTO được chỉ định rõ | Dễ kiểm soát phạm vi |
| `setContextPath("com.example.erp.generated")` | Generated package chứa `ObjectFactory` hoặc `jaxb.index` | Thường dùng với XJC |
| `setPackagesToScan("com.example.erp.xml")` | Tìm annotated classes trong package | Có chi phí scan và yêu cầu package hợp lệ |

Thông thường chọn **một** cơ chế chính cho một marshaller context. Khi nhiều SOAP partner dùng các XSD khác nhau, tạo bean riêng theo adapter thay vì trộn mọi generated class không liên quan.

Ví dụ thay thế:

~~~java
@Bean
Jaxb2Marshaller generatedErpMarshaller() {
    Jaxb2Marshaller m = new Jaxb2Marshaller();
    m.setContextPath("com.example.erp.generated");
    m.setSupportDtd(false);
    m.setProcessExternalEntities(false);
    return m;
}
~~~

Đây là một **lựa chọn khác**, không có nghĩa phải đăng ký cả hai bean trong cùng context.

### 8.2. Marshal vào Result và unmarshal từ Source

Các API JAXP như `javax.xml.transform.Source`/`Result` vẫn có trong JDK:

~~~java
import java.io.StringReader;
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

public class XmlPayloadMapper {

    private final Jaxb2Marshaller mapper;

    public XmlPayloadMapper(Jaxb2Marshaller mapper) {
        this.mapper = mapper;
    }

    public String toXml(SubmitOrderRequest request) {
        StringWriter output = new StringWriter();
        mapper.marshal(request, new StreamResult(output));
        return output.toString();
    }

    public Object fromTrustedXml(String xml) {
        return mapper.unmarshal(
                new StreamSource(new StringReader(xml)));
    }
}
~~~

`fromTrustedXml` chỉ minh họa API với **XML tin cậy**. Không dùng `StreamSource` chưa kiểm soát parser cho XML không tin cậy; xem phần chống XXE. Spring có thể có các bảo vệ DTD/external entity, nhưng một `DOMSource` đã dựng bằng parser không an toàn có thể bị resolve từ trước khi đến JAXB.

## 9. JAXB trong WebServiceTemplate và SOAP

Spring-WS `WebServiceTemplate` nhận một marshaller/unmarshaller để chuyển XML payload, còn SOAP message factory và message sender xử lý Envelope/transport.

~~~java
// ErpSoapClientConfiguration.java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration(proxyBeanMethods = false)
public class ErpSoapClientConfiguration {

    @Bean
    WebServiceTemplate erpWebServiceTemplate(
            @Qualifier("erpJaxbMarshaller")
            Jaxb2Marshaller marshaller) {

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
        template.setDefaultUri(
                "https://erp.example.org/soap/orders");
        return template;
    }
}
~~~

`https://erp.example.org/soap/orders` là địa chỉ minh họa. Trong production, nên lấy URL từ externalized configuration và cấu hình transport/TLS/credentials/timeouts theo Spring-WS version. Code trên chỉ cho thấy JAXB được nối với template.

Gateway gọi:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

@Component
public class ErpSoapGateway {

    private final WebServiceTemplate template;

    public ErpSoapGateway(WebServiceTemplate template) {
        this.template = template;
    }

    public Object submit(SubmitOrderRequest request) {
        return template.marshalSendAndReceive(
                request,
                new SoapActionCallback("urn:SubmitOrder"));
    }
}
~~~

Gateway thực tế nên kiểm tra/cast `SubmitOrderResponse` hoặc unwrap `JAXBElement<SubmitOrderResponse>`, xác minh namespace/kiểu và chuyển thành business result. Ví dụ trả `Object` ở đây để không giả định dạng response binding.

**SOAPAction** liên quan binding và SOAP version, không tự suy ra từ JAXB root element. Với SOAP 1.2, action/content type có đặc điểm khác SOAP 1.1; phải theo đúng WSDL. Không hard-code action nếu đối tác dùng giá trị khác.

### 9.1. XML payload nằm trong SOAP Body

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:m="urn:example:orders:v1">
  <soapenv:Header/>
  <soapenv:Body>
    <m:SubmitOrderRequest>
      <m:orderId>ORD-100</m:orderId>
      <m:amountMinor>1890000</m:amountMinor>
      <m:currency>VND</m:currency>
    </m:SubmitOrderRequest>
  </soapenv:Body>
</soapenv:Envelope>
~~~

`Jaxb2Marshaller` chịu trách nhiệm phần `SubmitOrderRequest`, không tự thêm Header, ký số, WS-Security UsernameToken hoặc SOAP Envelope. Tầng Spring-WS/message factory/WS-Security phải xử lý những phần đó.

### 9.2. Timeout và bảo mật SOAP transport

Trước khi deploy:

- Kiểm tra HTTPS/TLS, trust store, hostname và chính sách chứng chỉ.
- Cấu hình HTTP connect/read timeout theo client message sender tương thích version.
- Phân biệt HTTP 401/403, HTTP 503, SOAP Fault, JAXB parse/schema error.
- Nếu dùng WS-Security, xác minh timestamp, signature, certificate, replay protection.
- Không log SOAP payload chứa token, PII hoặc dữ liệu tài chính.
- Kiểm soát số request song song, retry và trạng thái downstream.

JAXB không tạo transaction phân tán hay authentication policy chỉ vì DTO đúng XSD.

## 10. XSD validation và business validation

XML dưới đây **well-formed** nhưng thiếu một element bắt buộc:

~~~xml
<m:SubmitOrderRequest xmlns:m="urn:example:orders:v1">
  <m:orderId>ORD-100</m:orderId>
  <m:currency>VND</m:currency>
</m:SubmitOrderRequest>
~~~

`@XmlElement(required=true)` không thay thế XSD validation. Spring `Jaxb2Marshaller` có thể gắn schema tin cậy:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

public Jaxb2Marshaller validatedMapper() {
    Jaxb2Marshaller m = new Jaxb2Marshaller();
    m.setClassesToBeBound(
            SubmitOrderRequest.class,
            SubmitOrderResponse.class);
    m.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd"));
    m.setSupportDtd(false);
    m.setProcessExternalEntities(false);
    return m;
}
~~~

Trong ví dụ này, file `xsd/orders-v1.xsd` phải tồn tại và chứa các root elements mà mapper cần validate. Với nhiều XSD imports, phải kiểm soát resolver/các tài nguyên được phép. Nên dùng schema đã phê duyệt và đóng gói cùng build.

### 10.1. SchemaFactory với giới hạn tài nguyên ngoài

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.InputStream;
import java.util.Objects;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;

SchemaFactory factory =
        SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);

factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_DTD, "");
factory.setProperty(
        XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

Schema schema;
try (InputStream in = Objects.requireNonNull(
        getClass().getResourceAsStream(
                "/xsd/orders-v1.xsd"))) {
    schema = factory.newSchema(new StreamSource(in));
}

JAXBContext context =
        JAXBContext.newInstance(SubmitOrderRequest.class);

Unmarshaller unmarshaller =
        context.createUnmarshaller();
unmarshaller.setSchema(schema);
~~~

Đây là snippet trong method instance (vì dùng `getClass()`). Nếu JAXP provider không hỗ trợ các thuộc tính bảo mật, cần xử lý fail-fast hoặc chọn parser/provider đáp ứng được, không âm thầm bỏ qua lỗi. Schema validation cần kết hợp **parser đầu vào an toàn** và giới hạn kích thước/độ sâu.

Schema chỉ kiểm tra những gì được khai báo. Nếu `currency` là string không giới hạn hoặc số tiền không có `minInclusive`, các quy tắc nghiệp vụ vẫn phải được kiểm tra sau khi unmarshal.

## 11. Chống XXE và XML parser không tin cậy

XML là input có thể gây nguy hiểm nếu parser cho phép DTD và external entities. Ví dụ về dạng **phải từ chối** khi hợp đồng không dùng DTD:

~~~xml
<?xml version="1.0"?>
<!DOCTYPE payload [
  <!ENTITY external SYSTEM "file:///internal/secret">
]>
<payload>&external;</payload>
~~~

Không chạy payload này để đọc file thật. Mục tiêu là parser **không bao giờ resolve entity ngoài** và không mở rộng DTD nguy hiểm.

Một `SAXSource` an toàn hơn khi đọc XML ngoài:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import java.io.StringReader;
import javax.xml.parsers.SAXParserFactory;
import javax.xml.transform.sax.SAXSource;
import org.xml.sax.InputSource;
import org.xml.sax.XMLReader;

public class SecureOrderXmlReader {

    private final JAXBContext context;

    public SecureOrderXmlReader() throws Exception {
        context =
                JAXBContext.newInstance(
                        SubmitOrderRequest.class);
    }

    public SubmitOrderRequest parse(String xml)
            throws Exception {

        SAXParserFactory factory =
                SAXParserFactory.newInstance();
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
        factory.setFeature(
                "http://apache.org/xml/features/nonvalidating/load-external-dtd",
                false);

        XMLReader reader =
                factory.newSAXParser().getXMLReader();

        SAXSource source = new SAXSource(
                reader,
                new InputSource(new StringReader(xml)));

        Unmarshaller unmarshaller =
                context.createUnmarshaller();

        return (SubmitOrderRequest)
                unmarshaller.unmarshal(source);
    }
}
~~~

Quan trọng:

- **Không bắt rồi bỏ qua** exception khi đặt security features. Nếu parser không hỗ trợ, bảo mật không được bảo đảm.
- Đặt byte limit **trước khi** XML được đọc vào `String` để tránh RAM bị chiếm bởi payload lớn.
- Cần giới hạn độ sâu XML, số elements/attributes và tổng thời gian xử lý theo workload.
- `Jaxb2Marshaller.setSupportDtd(false)` và `setProcessExternalEntities(false)` là lớp bảo vệ hữu ích, nhưng parser tạo `DOMSource` ở nơi khác có thể đã xử lý external entities từ trước.
- Không tải XSD từ URL do người dùng gửi; dùng schema tin cậy và giới hạn external imports.

**Bảo mật phải bắt đầu tại điểm parse XML đầu tiên**, không chỉ ở nơi gọi JAXB.

## 12. Các kiểu dữ liệu khó: decimal, thời gian và enum

### 12.1. Decimal và số tiền

XSD `xs:decimal` thường map sang `BigDecimal`. Không dùng `double` để tính tiền nếu hợp đồng yêu cầu độ chính xác thập phân.

~~~java
import jakarta.xml.bind.annotation.XmlElement;
import java.math.BigDecimal;

// Field snippet trong một DTO:
@XmlElement(name = "amount", required = true)
private BigDecimal amount;
~~~

Ví dụ này chỉ minh họa field; cần đặt namespace đúng với package/XSD. Với số tiền, nghiệp vụ vẫn phải kiểm tra sign, precision, scale, loại tiền và quy tắc rounding.

### 12.2. XMLGregorianCalendar và OffsetDateTime

XSD có `xs:date`, `xs:dateTime`, `xs:time`. Generated JAXB types có thể sử dụng `XMLGregorianCalendar`, trong khi domain model muốn `Instant`, `OffsetDateTime` hoặc `LocalDate`.

Không tự gán `LocalDateTime` cho timestamp có timezone mà bỏ offset. Khi cần custom mapping, dùng `XmlAdapter` phù hợp lexical representation:

~~~java
import jakarta.xml.bind.annotation.adapters.XmlAdapter;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;

public class OffsetDateTimeAdapter
        extends XmlAdapter<String, OffsetDateTime> {

    @Override
    public OffsetDateTime unmarshal(String value) {
        return value == null
                ? null
                : OffsetDateTime.parse(
                        value,
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }

    @Override
    public String marshal(OffsetDateTime value) {
        return value == null
                ? null
                : value.format(
                        DateTimeFormatter.ISO_OFFSET_DATE_TIME);
    }
}
~~~

Gắn adapter vào field:

~~~java
@XmlJavaTypeAdapter(OffsetDateTimeAdapter.class)
@XmlElement(name = "processedAt")
private OffsetDateTime processedAt;
~~~

Snippet field cần imports `jakarta.xml.bind.annotation.adapters.XmlJavaTypeAdapter` và `jakarta.xml.bind.annotation.XmlElement`. Không phải mọi dạng `xs:dateTime` của đối tác đều chứa offset; adapter cần phù hợp contract thực tế và được kiểm thử với UTC/DST.

### 12.3. Enum và versioning

~~~java
import jakarta.xml.bind.annotation.XmlEnum;
import jakarta.xml.bind.annotation.XmlEnumValue;

@XmlEnum
public enum ErpResult {
    @XmlEnumValue("ACCEPTED") ACCEPTED,
    @XmlEnumValue("REJECTED") REJECTED
}
~~~

Nếu đối tác thêm giá trị `PENDING_REVIEW`, JAXB/mapper cũ có thể không xử lý như mong đợi. Cần hợp đồng về unknown enum và compatibility, không tự đổi giá trị lạ thành trạng thái thành công.

## 13. Phân loại lỗi XML và SOAP

| Nhóm lỗi | Ví dụ | Chính sách |
| --- | --- | --- |
| **Classpath/runtime** | `JAXBException` do không có provider | Sửa dependency/version, không retry request |
| **Mapping** | `@XmlRootElement` thiếu, property trùng | Sửa annotation, JAXBElement hoặc generated model |
| **XML namespace/schema** | Unexpected element, wrong QName, thiếu required field | Sửa contract/payload; không retry mù |
| **SOAP Fault nghiệp vụ** | Invalid amount, unknown customer | Map domain result, không retry vô hạn |
| **SOAP Fault server** | ERP temporarily unavailable | Retry giới hạn nếu side effect an toàn |
| **HTTP/TLS transport** | 401/403, timeout, certificate | Kiểm tra auth, network, deadline |
| **Kết quả chưa rõ** | Timeout sau khi request gửi | Reconcile/idempotency để tránh gửi trùng |
| **Semantic validation** | Currency không hợp lệ dù XSD cho phép | Kiểm tra quy tắc nghiệp vụ |

Spring OXM thường chuyển lỗi JAXB sang các lỗi kiểu `XmlMappingException`. Spring-WS có `SoapFaultClientException` hoặc các lỗi transport tương ứng; không gộp tất cả vào `catch(Exception)` rồi retry.

### 13.1. SOAP Fault không phải response DTO

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <soap:Fault>
      <faultcode>soap:Client</faultcode>
      <faultstring>Invalid order amount</faultstring>
    </soap:Fault>
  </soap:Body>
</soap:Envelope>
~~~

Đây là SOAP 1.1 Fault, không phải `SubmitOrderResponse`. Hãy dùng fault resolver của Spring-WS, phân biệt lỗi nghiệp vụ và lỗi hạ tầng. SOAP 1.2 có cấu trúc Fault khác. Không log toàn bộ fault details chứa dữ liệu bí mật hoặc hiển thị trực tiếp lên API public.

## 14. Transaction, retry và idempotency

Giả sử service ghi SQL rồi gọi ERP SOAP:

~~~text
DB COMMIT thành công
      |
      +-- SOAP request timeout
              |
              +-- ERP có thể đã xử lý nhưng response bị mất
~~~

JAXB chỉ tạo XML. `@Transactional` của JDBC/JPA không tự bao gồm request SOAP, Redis cache hoặc broker publish trong một transaction ACID.

Một pipeline đáng tin cậy:

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Order row"]
    B --> D["Integration outbox"]
    D --> E["Outbox relay / broker"]
    E --> F["SOAP adapter"]
    F --> G["ERP endpoint"]
    F -.-> H["Retry / reconciliation"]
~~~

Thiết kế:

1. Trong cùng SQL transaction, ghi business state và outbox event có operation ID ổn định.
2. Worker đọc outbox, map JAXB request rồi gửi SOAP.
3. Nếu ERP hỗ trợ idempotency key/operationId, dùng **cùng key** qua các retry/redelivery.
4. Nếu timeout sau khi gửi, thử **tra cứu trạng thái** thay vì lập tức gửi lại thao tác tạo giao dịch.
5. Lưu attempt/outcome/nextRetryAt, có backoff/jitter và DLQ hoặc xử lý thủ công.
6. Acknowledge message khi trạng thái xử lý thỏa hợp đồng; consumer phải chịu được duplicate.

**Không có exactly-once SOAP mặc định.** Một lần gửi thành công nhưng mất response có thể bị retry và tạo tác động trùng nếu ERP không hỗ trợ deduplication/reconciliation.

| Tình huống | Retry? | Giải thích |
| --- | --- | --- |
| XML sai XSD hoặc QName | Không | Phải sửa hợp đồng/dữ liệu |
| SOAP Fault invalid data | Không | Lỗi nghiệp vụ |
| HTTP 401/403 | Không liên tục | Credential/quyền sai |
| HTTP 503, lỗi connect tạm thời | Có giới hạn | Backoff và deadline |
| Timeout sau request ghi | Cần idempotency/reconcile | Kết quả không xác định |
| ERP trả pending | Theo dõi workflow | Không đồng nghĩa thất bại |

Đặt **retry budget cho toàn luồng**; không để HTTP transport, broker consumer và Quartz job cùng retry lũy thừa không kiểm soát.

## 15. Performance, resource và observability

### 15.1. JAXBContext đắt, payload XML có thể lớn

- Cache `JAXBContext` hoặc dùng singleton `Jaxb2Marshaller`; đừng build context mỗi event.
- Không dùng chung JAXB `Marshaller`/`Unmarshaller` qua nhiều thread.
- Giới hạn byte size và depth XML trước khi tạo object graph lớn.
- Với XML cực lớn hoặc cần stream, cân nhắc SAX/StAX thay vì unmarshalling toàn bộ vào RAM.
- Không mutate schema/context settings trên bean dùng chung trong lúc traffic đang diễn ra.
- Cấu hình thread pool, HTTP timeout và backpressure cho SOAP adapter.

### 15.2. Quan sát nhiều ranh giới

| Metric | Ý nghĩa |
| --- | --- |
| XML marshal/unmarshal duration | CPU và mapping overhead |
| XSD validation failure count | Hợp đồng dữ liệu lỗi |
| SOAP request latency p95/p99 | Network + server + (có thể) mapping |
| SOAP fault rate | Phân biệt business/server faults |
| HTTP connect/read timeout count | Transport không đáp ứng |
| Retry/duplicate count | Khả năng phục hồi và idempotency |
| Outbox oldest age/queue lag | Độ trễ xử lý tích hợp |
| Business confirmation lag | Từ SQL commit đến ERP confirmed |

Ví dụ observation quanh lời gọi SOAP:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.ws.client.core.WebServiceTemplate;

public Object submitObserved(
        WebServiceTemplate template,
        ObservationRegistry registry,
        SubmitOrderRequest request) {

    return Observation.createNotStarted(
                    "integration.soap.submit", registry)
            .lowCardinalityKeyValue("partner", "erp")
            .lowCardinalityKeyValue("operation", "submitOrder")
            .observe(() ->
                    template.marshalSendAndReceive(request));
}
~~~

Observation có thể tạo timer/span khi handler được cấu hình. Nó đo lời gọi đồng bộ, **không tự xác nhận giao dịch cuối cùng ở ERP đã commit**.

Dùng low-cardinality tags như `partner`, `operation` và `outcome`. Không gắn `orderId`, `eventId`, raw XML, credential hoặc mã khách hàng vào metric labels. Các ID có thể vào audit/log được bảo vệ khi cần đối soát.

## 16. Kiểm thử XML binding và SOAP client

Một test round-trip object → XML → object chưa chứng minh đúng contract vì **cùng một lỗi annotation** có thể tồn tại ở cả hai chiều. Nên dùng XML fixture/XSD chính thức của đối tác.

### 16.1. Unit test marshalling

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import java.io.StringWriter;
import javax.xml.transform.stream.StreamResult;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JaxbMappingTest {

    @Test
    void writesOrderXml() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setClassesToBeBound(
                SubmitOrderRequest.class);
        mapper.afterPropertiesSet();

        SubmitOrderRequest request =
                new SubmitOrderRequest(
                        "ORD-100", 1890000L, "VND");

        StringWriter writer = new StringWriter();
        mapper.marshal(
                request,
                new StreamResult(writer));

        String xml = writer.toString();
        assertTrue(xml.contains("SubmitOrderRequest"));
        assertTrue(xml.contains("ORD-100"));
    }
}
~~~

Test này là smoke test; contract test nên parse XML bằng parser an toàn rồi assert **root QName, namespace, child order và XSD validation**. So chuỗi bằng `contains` không phát hiện được sai namespace.

### 16.2. Kiểm thử SOAP payload không cần server thật

Spring-WS có `MockWebServiceServer` để mock message transport. Ví dụ test phần request payload:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.test.client.MockWebServiceServer;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.client.RequestMatchers.payload;
import static org.springframework.ws.test.client.ResponseCreators.withPayload;

class ErpSoapClientTest {

    @Test
    void submitsOrderPayload() throws Exception {
        Jaxb2Marshaller mapper = new Jaxb2Marshaller();
        mapper.setClassesToBeBound(
                SubmitOrderRequest.class,
                SubmitOrderResponse.class);
        mapper.afterPropertiesSet();

        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(mapper);
        template.setUnmarshaller(mapper);
        template.setDefaultUri("https://erp.test/soap/orders");

        MockWebServiceServer server =
                MockWebServiceServer.createServer(template);

        String requestXml =
                "<m:SubmitOrderRequest "
                + "xmlns:m=\"urn:example:orders:v1\">"
                + "<m:orderId>ORD-100</m:orderId>"
                + "<m:amountMinor>1890000</m:amountMinor>"
                + "<m:currency>VND</m:currency>"
                + "</m:SubmitOrderRequest>";

        String responseXml =
                "<m:SubmitOrderResponse "
                + "xmlns:m=\"urn:example:orders:v1\">"
                + "<m:accepted>true</m:accepted>"
                + "<m:reference>ERP-200</m:reference>"
                + "</m:SubmitOrderResponse>";

        server.expect(payload(new StringSource(requestXml)))
                .andRespond(
                        withPayload(new StringSource(responseXml)));

        template.marshalSendAndReceive(
                new SubmitOrderRequest(
                        "ORD-100", 1890000L, "VND"));

        server.verify();
    }
}
~~~

Đoạn này giả định `SubmitOrderResponse` JAXB annotated/generate theo XSD và có dependency `spring-ws-test` ở test scope. Đây là ví dụ kiểm tra payload; test production nên assert response, SOAPAction, headers, SOAP Fault và lỗi transport. Nếu version Spring-WS khác, đối chiếu matcher APIs tương ứng.

### 16.3. Ma trận test quan trọng

| Tình huống | Kỳ vọng |
| --- | --- |
| Object → XML | Đúng QName, element order và encoding |
| XML fixture → object | Không mất trường, đúng kiểu |
| JAXBElement/generated root | Đúng QName và unwrap |
| Missing required/invalid type | Schema validation fail |
| Unknown namespace/schema version | Phản ứng theo chính sách tương thích |
| UTF-8 tiếng Việt | Không hỏng dấu |
| XML có DTD/XXE | Bị từ chối, không đọc URL/file ngoài |
| XML cực lớn | Bị chặn trước khi chiếm RAM |
| SOAP Fault | Mapping lỗi đúng |
| HTTP timeout/503 | Retry có giới hạn, đúng idempotency |
| Broker redelivery | Không lặp side effect |
| Mapping trên Java 17/21 | Không dùng nhầm javax/Jakarta |
| SQL commit + SOAP failure | Outbox đảm bảo ý định gửi còn để retry |

## 17. Chẩn đoán lỗi phiên bản và cấu hình

| Triệu chứng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `package javax.xml.bind does not exist` | Dùng JAXB cũ trên JDK mới không có module | Dependency JAXB 2 tương thích hoặc migrate Jakarta |
| `ClassNotFoundException jakarta.xml.bind.JAXBContext` | Thiếu Jakarta JAXB API | Thêm API đúng version |
| JAXB API provider not found | Có API nhưng thiếu implementation/runtime | Thêm JAXB runtime phù hợp |
| `NoClassDefFoundError javax/xml/bind/...` | Dependency hoặc generated code legacy trong hệ Jakarta | Chọn/regen JAXB đúng namespace |
| No root element / unexpected element | Thiếu `@XmlRootElement`, sai QName, JAXBElement | Kiểm tra XSD, ObjectFactory và annotations |
| XML hợp cú pháp nhưng business fields null | Không có schema validation hoặc thiếu field | Bật XSD và business validation |
| `IllegalAnnotationsException` | Trùng field/getter, access strategy sai | Chọn `@XmlAccessorType` phù hợp |
| Java 17 compile pass nhưng run fail | Runtime classpath/JAXB provider không đúng | Kiểm tra dependency runtime và container JDK |
| XJC sinh imports javax trên Boot 3 | Codegen tool đời cũ | Regenerate bằng Jakarta XJC |
| SOAP Fault bị hiểu là mapping error | Unmarshal Fault vào response DTO | Dùng Spring-WS fault resolver |
| XXE vulnerability | XML parser cho phép DTD/external entities | Chặn parser từ điểm parse đầu |
| Timeout sau SOAP gửi giao dịch | ERP có thể đã thực hiện | Idempotency/reconciliation |
| Memory/CPU tăng khi XML lớn | Materialize object graph, JAXBContext tạo nhiều lần | Giới hạn input, reuse context, streaming |

Thứ tự chẩn đoán: xác nhận JDK → Spring/WS/JAXB versions → runtime classpath → JAXB namespace/annotations → XSD/QName → SOAP/HTTP faults → business retry/idempotency. Không chữa lỗi bằng cách tắt validation, cho phép DTD hoặc retry mọi request vô hạn.

## 18. Checklist triển khai SOAP/JAXB

- [ ] Đã xác nhận đúng Java runtime và hệ JAXB `javax`/`jakarta`.
- [ ] JAXB API/runtime/XJC/generated source phù hợp Spring Boot/Framework version.
- [ ] WSDL/XSD được version hóa, XML QName/namespace/thứ tự đúng hợp đồng.
- [ ] Biết khi nào class cần `@XmlRootElement`, khi nào dùng `JAXBElement`/`ObjectFactory`.
- [ ] Chia sẻ `JAXBContext`/Spring `Jaxb2Marshaller`, không chia sẻ mapper JAXB không thread-safe.
- [ ] Có XSD validation và business validation riêng, không chỉ `required=true`.
- [ ] XML từ ngoài đi qua parser chặn DTD/external entities, giới hạn byte và độ sâu.
- [ ] SOAP Envelope, SOAP version, action, WS-Security được xử lý ở Spring-WS đúng WSDL.
- [ ] TLS, auth, connect/read timeout, retry budget được cấu hình theo môi trường.
- [ ] Phân biệt SOAP Fault, XML mapping error, transport error và business rejection.
- [ ] SQL transaction/outbox không bị nhầm với SOAP transaction.
- [ ] Idempotency/reconciliation được thiết kế cho timeout sau khi gửi.
- [ ] Có unit/XSD/fixture và MockWebServiceServer integration tests.
- [ ] Có metrics cho mapping latency, SOAP fault, retry, outbox lag; không lộ payload/PII.

**Kết luận:** JAXB là công cụ **marshalling/unmarshalling giữa Java và XML**. Để dùng hiệu quả trong Spring Boot, cần cấu hình JAXB đúng **phiên bản Java và hệ `javax`/`jakarta`**, ánh xạ đúng XSD, xử lý `JAXBElement`/generated models và bảo vệ XML parser. `Jaxb2Marshaller` nối JAXB với Spring OXM/Spring-WS; transport, bảo mật, retry, transaction và idempotency vẫn là các trách nhiệm riêng của luồng tích hợp.

## Tài liệu tham khảo

- [Spring Framework — O/X Mapping](https://docs.spring.io/spring-framework/reference/data-access/oxm.html): `Jaxb2Marshaller`, Spring OXM và binding.
- [Spring Web Services — Reference](https://docs.spring.io/spring-ws/docs/current/reference/html/): `WebServiceTemplate`, SOAP clients và faults.
- [Spring Boot — Web Services](https://docs.spring.io/spring-boot/reference/io/webservices.html): Boot/Spring-WS integration.
- [Jakarta XML Binding — Specifications](https://jakarta.ee/specifications/xml-binding/): API và JAXB/Jakarta version.
- [JAXB Reference Implementation](https://eclipse-ee4j.github.io/jaxb-ri/): JAXB runtime và XJC code generation.
- [JEP 320 — Remove the Java EE and CORBA Modules](https://openjdk.org/jeps/320): module JAXB bị loại khỏi JDK 11.
- [Java XMLConstants](https://docs.oracle.com/en/java/javase/21/docs/api/java.xml/javax/xml/XMLConstants.html): hạn chế external DTD/XSD.
- [OWASP — XML External Entity Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/XML_External_Entity_Prevention_Cheat_Sheet.html): secure parsing và XXE mitigation.
- [Spring-WS MockWebServiceServer](https://docs.spring.io/spring-ws/docs/current/api/org/springframework/ws/test/client/MockWebServiceServer.html): kiểm thử SOAP client cô lập.
