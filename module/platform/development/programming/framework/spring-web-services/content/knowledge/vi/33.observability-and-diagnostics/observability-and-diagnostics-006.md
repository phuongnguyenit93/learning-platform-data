# Lỗi JAXB: phần tử không mong đợi, thiếu context và khác namespace

## 1. Tình huống: XML hợp lệ nhưng JAXB vẫn không đọc được

Một Spring-WS client gọi SOAP operation GetOrder. SOAP response là XML well-formed, Envelope/Body parse thành công, nhưng request kết thúc với exception:

```text
jakarta.xml.bind.UnmarshalException:
  unexpected element (uri:"urn:example:orders:v2",
  local:"GetOrderResponse").
  Expected elements are
  <{urn:example:orders:v1}GetOrderResponse>
```

Hoặc log có dạng:

```text
unexpected element (uri:"urn:example:documents:v1",
local:"UploadDocumentResponse").
Expected elements are (none)
```

Hai lỗi có thể trông giống nhau nhưng nguyên nhân khác nhau. Trường hợp đầu thường là QName trong XML không khớp QName JAXB đang mong đợi. Trường hợp thứ hai thường cho thấy JAXB context chưa biết root element/class phù hợp, model không khai báo root element hoặc cần được xử lý qua JAXBElement từ ObjectFactory.

Trong tích hợp SOAP contract-first với Spring Web Services, chẩn đoán JAXB phải đi xuyên suốt các lớp: SOAP Body, root QName, XSD, generated model, JAXBContext, marshaller/unmarshaller, schema validation và phiên bản contract của provider.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc UnmarshalException và phân biệt lỗi XML, QName, JAXB binding và schema validation.
2. Giải thích QName gồm namespace URI và local name; hiểu prefix không phải danh tính của element.
3. Chẩn đoán root element không được biết, class thiếu trong JAXBContext và package namespace sai.
4. Phân biệt @XmlRootElement, @XmlElementDecl, JAXBElement<T> và ObjectFactory.
5. Sửa mapping elementFormDefault, @XmlSchema và package-level namespace.
6. Kiểm tra generated JAXB classes được sinh từ đúng XSD/WSDL và đúng toolchain.
7. Cấu hình Jaxb2Marshaller của Spring-WS nhất quán ở client/server.
8. Tạo test tái hiện và ngăn lỗi namespace/context quay lại.

## 2. Đọc exception trước khi sửa code

### 2.1. Những dạng lỗi thường gặp

| Triệu chứng | Tầng có thể gây lỗi | Câu hỏi đầu tiên |
| --- | --- | --- |
| unexpected element (uri, local) | JAXB root/child element mapping | XML QName nào đến? JAXB mong QName nào? |
| Expected elements are (none) | JAXB context/root registration | Context có root element declaration không? |
| class is not known to this context | JAXBContext | Class/package chứa type đã được thêm vào context chưa? |
| unable to marshal type as an element | Marshal root mapping | Object có @XmlRootElement hoặc được wrap bằng JAXBElement không? |
| class nor any superclass is known | JAXBContext | Generated class có nằm trong context path/packages/classes? |
| unexpected child element | Nested field mapping | Child namespace, element order, type và cardinality có khớp XSD không? |
| cvc-... schema validation error | XSD validator | Payload có vi phạm schema đang được nạp không? |
| SAXParseException | XML parser | XML malformed, encoding hoặc parser configuration có vấn đề? |

Không sửa namespace ngay khi thấy chữ unexpected. Đọc đầy đủ exception, nested cause và vị trí xảy ra: khi parse SOAP, validate payload, unmarshal JAXB hay ở application mapper.

### 2.2. unexpected element nói gì?

Thông báo thường cho biết:

- uri: namespace URI của element nhận được.
- local: local name của element nhận được.
- Expected elements: root/element declarations JAXB có thể nhận ở vị trí đó.

Ví dụ:

```text
Received:
  {urn:example:orders:v2}GetOrderResponse

Expected:
  {urn:example:orders:v1}GetOrderResponse
```

Local name giống nhau không có nghĩa là cùng element. Namespace URI khác nhau thì QName khác nhau, nên JAXB coi đó là hai element khác nhau.

### 2.3. Expected elements are (none) thường không phải “XML không có namespace”

Thông báo (none) có thể xuất hiện khi context không có element declaration hợp lệ ở root. Một generated class có thể tồn tại nhưng không mang @XmlRootElement; nó được sử dụng qua JAXBElement<T> từ ObjectFactory.

Vì vậy, kiểm tra đồng thời:

1. Class có được compile và runtime load không?
2. JAXBContext có biết class/type đó không?
3. Context có biết global root element QName không?
4. Caller đang unmarshal vào JAXBElement<T>, class cụ thể hay Object?

## 3. QName và namespace: nguyên nhân số một

### 3.1. QName là namespace URI + local name

XML:

```xml
<ord:GetOrderResponse
    xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-100</ord:orderId>
</ord:GetOrderResponse>
```

Root QName là:

```text
{urn:example:orders:v1}GetOrderResponse
```

Prefix ord chỉ là alias trong document. Những XML sau có cùng QName:

```xml
<a:GetOrderResponse xmlns:a="urn:example:orders:v1"/>

<GetOrderResponse xmlns="urn:example:orders:v1"/>

<x:GetOrderResponse xmlns:x="urn:example:orders:v1"/>
```

Không nên sửa code vì prefix trong XML khác prefix trong ví dụ. Điều phải so là URI và local name.

### 3.2. Namespace khác nhau là contract khác nhau

```xml
<ord:GetOrderResponse
    xmlns:ord="urn:example:orders:v2"/>
```

Element này có QName {urn:example:orders:v2}GetOrderResponse, khác v1. Nếu generated model được tạo từ XSD v1, unmarshaller không tự hiểu v2 dù tên class và local name giống nhau.

Không đổi package/class name bằng tay để “sửa” namespace. Cần xác định provider đã nâng contract, client đang dùng sai schema hay endpoint được route sang service/version khác.

### 3.3. Default namespace ảnh hưởng element không prefix

```xml
<GetOrderResponse
    xmlns="urn:example:orders:v1">
    <orderId>ORD-100</orderId>
</GetOrderResponse>
```

Root và child không prefix vẫn thuộc default namespace. Ngược lại:

```xml
<GetOrderResponse>
    <orderId>ORD-100</orderId>
</GetOrderResponse>
```

Không có default namespace nghĩa là hai element thuộc namespace rỗng. XML vẫn well-formed nhưng có thể không khớp contract qualified elements.

### 3.4. Namespace của parent không tự áp dụng cho mọi attribute

Trong XML Namespaces, unprefixed attributes không thừa hưởng default namespace của element. Ví dụ:

```xml
<ord:Document
    xmlns:ord="urn:example:documents:v1"
    id="DOC-100"/>
```

Element có namespace urn:example:documents:v1, nhưng attribute id không có namespace. Điều này quan trọng khi XSD quy định attributeFormDefault hoặc attribute reference có namespace.

### 3.5. Cách kiểm tra QName mà không đoán prefix

Một helper DOM/StAX có thể log root QName:

```java
import javax.xml.namespace.QName;
import javax.xml.stream.XMLStreamReader;

public final class XmlNames {

    private XmlNames() {}

    public static QName currentName(XMLStreamReader reader) {
        return reader.hasName()
            ? reader.getName()
            : null;
    }
}
```

Với DOM Element, dùng getNamespaceURI() và getLocalName(). Tránh log XML body thật nếu chứa PII/token; chỉ log QName đã lọc, operation và correlation ID.

## 4. JAXB root mapping: @XmlRootElement và JAXBElement

### 4.1. Class có @XmlRootElement

Một JAXB class có thể khai báo trực tiếp root element:

```java
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlRootElement(
    name = "GetOrderResponse",
    namespace = "urn:example:orders:v1"
)
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(propOrder = {"orderId"})
public class GetOrderResponse {

    private String orderId;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String orderId) {
        this.orderId = orderId;
    }
}
```

Với model này, JAXB có thể dùng class làm root element khi marshal/unmarshal nếu class thuộc JAXBContext.

### 4.2. Class không có @XmlRootElement

XJC thường sinh type class và tạo global element factory method trong ObjectFactory. Khi class không có @XmlRootElement, wrap bằng JAXBElement<T>:

```java
import jakarta.xml.bind.JAXBElement;

ObjectFactory factory = new ObjectFactory();
GetOrderResponse value = new GetOrderResponse();
value.setOrderId("ORD-100");

JAXBElement<GetOrderResponse> root =
    factory.createGetOrderResponse(value);

marshaller.marshal(root, result);
```

Tên method thực tế phụ thuộc schema và package generated; kiểm tra ObjectFactory được XJC sinh ra. Không tự tạo QName tùy tiện nếu XSD đã định nghĩa global element.

### 4.3. @XmlElementDecl mô tả global element

Generated ObjectFactory thường có method tương đương:

```java
@XmlElementDecl(
    namespace = "urn:example:orders:v1",
    name = "GetOrderResponse"
)
public JAXBElement<GetOrderResponse> createGetOrderResponse(
        GetOrderResponse value) {
    return new JAXBElement<>(
        _GetOrderResponse_QNAME,
        GetOrderResponse.class,
        null,
        value
    );
}
```

Đây là dạng minh họa. @XmlElementDecl đăng ký global element mapping và factory tạo JAXBElement. Nếu code chỉ add GetOrderResponse.class vào context mà không có root declaration phù hợp, việc unmarshal root có thể vẫn thất bại.

### 4.4. Unmarshal vào JAXBElement

Khi root model được mô tả bằng element declaration:

```java
JAXBElement<GetOrderResponse> root =
    unmarshaller.unmarshal(
        source,
        GetOrderResponse.class
    );

GetOrderResponse response = root.getValue();
QName actualRootName = root.getName();
```

Overload typed này trả JAXBElement<T> và cho phép kiểm tra QName root thực tế. Nó không bỏ qua namespace validation; XML root vẫn phải phù hợp declaration/model và schema configuration.

### 4.5. Không dùng @XmlRootElement để che sai contract

Thêm annotation vào generated class bằng tay có thể làm local test pass nhưng gây drift với XSD, và lần generate kế tiếp có thể ghi đè. Nếu global element thực sự thuộc XSD, sửa schema/binding và regenerate; nếu muốn dùng type không có root, sử dụng ObjectFactory/JAXBElement đúng cách.

## 5. JAXBContext thiếu class hoặc package

### 5.1. JAXBContext là tập model được biết

JAXBContext không tự quét mọi class trong classpath. Nó được tạo từ:

- Danh sách class cụ thể.
- Package context path với ObjectFactory hoặc jaxb.index phù hợp.
- Cơ chế discovery được provider hỗ trợ.

Nếu response type hoặc type được tham chiếu không nằm trong context, JAXB có thể báo class/type không biết.

### 5.2. Tạo context từ class cụ thể

```java
JAXBContext context = JAXBContext.newInstance(
    GetOrderRequest.class,
    GetOrderResponse.class,
    OrderLine.class
);
```

Ưu điểm: thấy rõ class nào được register. Nhược điểm: dễ quên type mới khi schema thêm element/reference. ObjectFactory có thể giúp đăng ký các global element/type trong package.

### 5.3. Tạo context theo package

```java
JAXBContext context = JAXBContext.newInstance(
    "com.example.orders.v1"
);
```

Context path phải trỏ tới package có JAXB metadata discovery phù hợp. Với generated JAXB packages, ObjectFactory thường được XJC tạo ra; jaxb.index có thể được dùng trong một số cách cấu hình. Kiểm tra generated package thực tế thay vì giả định package name theo folder source.

### 5.4. Spring Jaxb2Marshaller

Spring Jaxb2Marshaller có thể cấu hình context bằng packages hoặc classes. Ví dụ theo package:

```java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("com.example.orders.v1");
marshaller.afterPropertiesSet();
```

Hoặc dùng class list:

```java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setClassesToBeBound(
    GetOrderRequest.class,
    GetOrderResponse.class,
    ObjectFactory.class
);
marshaller.afterPropertiesSet();
```

Ví dụ cho thấy hai cách xác định model. Thông thường chọn một chiến lược nhất quán; không copy cả contextPath, packagesToScan và classesToBeBound vào mọi marshaller. ObjectFactory trong classesToBeBound hữu ích khi element declarations được đặt trong factory.

### 5.5. Nhiều JAXBContext cho nhiều contract version

Nếu service hỗ trợ orders.v1 và orders.v2, không nên trộn generated packages một cách vô thức. Có thể dùng context riêng:

```java
Jaxb2Marshaller v1 = new Jaxb2Marshaller();
v1.setContextPath("com.example.orders.v1");

Jaxb2Marshaller v2 = new Jaxb2Marshaller();
v2.setContextPath("com.example.orders.v2");
```

Route operation/endpoint tới đúng marshaller theo contract version. QName giống local name nhưng namespace khác phải được xử lý như contract khác nhau.

### 5.6. Class loader và duplicate generated classes

Trong Spring Boot app, plugin container, application server hoặc test runtime, class có thể được load từ classloader khác. Các tình huống:

- Hai module cùng chứa generated class trùng FQCN nhưng version khác.
- Dependency cũ kéo XSD-generated artifact cũ.
- JAXBContext được tạo trước khi classloader/plugin module sẵn sàng.
- Package scan không tìm thấy class vì package được relocate/shade.

Khi nghi ngờ, log class name và code source location (không log dữ liệu nhạy cảm), kiểm tra dependency tree/build artifact và classloader identity.

## 6. XSD element qualification và generated namespace

### 6.1. elementFormDefault quyết định namespace của local elements

XSD:

```xml
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">
    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Với elementFormDefault qualified, local element orderId cũng thuộc target namespace. Nếu schema dùng unqualified, local elements có thể thuộc namespace rỗng, dù global root thuộc targetNamespace. Đọc XSD trước khi thêm/bỏ namespace trên child.

### 6.2. @XmlSchema ở package-info.java

XJC thường tạo package-level annotation:

```java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package com.example.orders.v1;
```

Annotation này định nghĩa namespace mặc định cho mapping trong package. XML source namespace v2 không tự động được coi là cùng model v1.

### 6.3. Namespace của type khác namespace của element

XSD có thể import type từ namespace khác. Không suy namespace của child chỉ từ namespace parent; hãy kiểm tra XSD import/include và QName của từng element/type.

### 6.4. Schema catalog và import/include

Generated class hoặc runtime validation có thể lệch nếu XSD import/include resolve sang file cũ, local schema khác remote schema hoặc XML catalog map namespace sai. Pin schema artifact/checksum, dùng catalog/resource resolver rõ ràng và test schema đã đóng gói trong application artifact.

## 7. Generated JAXB model bị lệch contract

### 7.1. Nguyên nhân phổ biến

1. Code chưa regenerate sau khi XSD đổi.
2. Generated sources được commit nhưng build không cập nhật.
3. Dependency chứa generated artifact cũ đang thắng classpath.
4. Hai WSDL cùng local operation nhưng targetNamespace khác nhau.
5. XJC episode/binding file hoặc catalog trỏ sai schema.
6. Runtime classloader nạp class từ JAR khác dự kiến.

### 7.2. Checklist so sánh contract và generated model

| Thành phần | Cần xác minh |
| --- | --- |
| WSDL service/port/binding | Endpoint, SOAP version, operation và imported schema |
| XSD global element | QName root request/response |
| XSD complexType/simpleType | Field names, QName, occurrence và facets |
| package-info.java | Namespace và elementFormDefault |
| ObjectFactory.java | QName constants và @XmlElementDecl |
| Generated classes | Annotation, field type, @XmlRootElement có hay không |
| JAXB plugin/toolchain | XJC/JAXB version và binding files |
| Runtime dependencies | JAXB API/runtime version đồng bộ |
| Resource resolution | XSD/WSDL thực tế nạp tại runtime |

### 7.3. Regenerate có kiểm soát

1. Chốt WSDL/XSD version và checksum.
2. Review diff schema trước khi code generation.
3. Chạy XJC/codegen bằng toolchain đã pin.
4. Review package-info.java, ObjectFactory.java, annotations và package changes.
5. Compile consumer/producer dùng model mới.
6. Chạy contract fixtures cho version cũ và mới.
7. Loại dependency generated cũ chỉ sau khi xác nhận callers đã chuyển.

Không sửa trực tiếp generated code nếu có thể sửa XSD hoặc external binding customization. Đặt custom behavior ở adapter/extension point và có regenerate test.

### 7.4. Không trộn javax và jakarta JAXB

JAXB 2.x thường sử dụng javax.xml.bind; Jakarta XML Binding 3.x/4.x sử dụng jakarta.xml.bind. Nếu generated classes dùng API khác với runtime, có thể gặp ClassNotFoundException, NoSuchMethodError, annotation không được nhận diện hoặc context creation failure. Giữ API/runtime/codegen cùng thế hệ; migrate đồng bộ và regenerate model.

## 8. Chẩn đoán trong Spring-WS client/server

### 8.1. Phân biệt payload mapping và schema validation

Một pipeline điển hình:

```text
HTTP request/response
      |
      v
SOAP message factory parses Envelope
      |
      v
SOAP header/security/interceptors
      |
      v
Endpoint mapping / operation selection
      |
      v
Payload validation (if configured)
      |
      v
JAXB marshaller/unmarshaller
      |
      v
Endpoint method / client application
```

Thứ tự và các layer chính xác phụ thuộc client/server configuration. Schema validator có thể reject payload trước JAXB. Nếu chỉ xem exception cuối, có thể nhầm XSD validation failure thành JAXB mapping error.

### 8.2. Kiểm tra Jaxb2Marshaller context ở client

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class OrdersSoapClientConfiguration {

    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("com.example.orders.v1");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersTemplate(
            Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        template.setDefaultUri(
            "https://partner.example.org/services/orders"
        );
        return template;
    }
}
```

Context path phải trỏ đến package generated đúng version. Nếu context thiếu root element declaration, kiểm tra package có ObjectFactory/jaxb.index phù hợp hoặc cấu hình classesToBeBound có factory.

### 8.3. Server endpoint parameter type phải khớp generated model

```java
@Endpoint
public class OrdersEndpoint {

    @PayloadRoot(
        namespace = "urn:example:orders:v1",
        localPart = "GetOrderRequest"
    )
    @ResponsePayload
    public GetOrderResponse getOrder(
            @RequestPayload GetOrderRequest request) {
        return new GetOrderResponse();
    }
}
```

@PayloadRoot định tuyến theo QName của payload root. Nó không sửa namespace cho JAXB và không thay schema validation. Nếu payload root thuộc v2 nhưng endpoint mapping khai v1, endpoint có thể không được chọn hoặc dispatch khác dự kiến.

### 8.4. Kiểm tra operation và marshaller cùng version

Một lỗi thường gặp là endpoint mapping chọn operation v1 nhưng marshaller sử dụng JAXB package v2 (hoặc ngược lại). Xác minh bộ ba:

- Request/response QName.
- Endpoint mapping/WSDL operation.
- JAXBContext/package version.

Ba thứ này phải thuộc cùng contract boundary, hoặc có adapter conversion rõ ràng giữa versions.

### 8.5. Không tắt schema validation để chữa lỗi JAXB

Nếu payload fail XSD, tắt validator có thể khiến malformed/contract-incompatible XML đi sâu hơn vào application. Nếu validator đã pass nhưng JAXB vẫn fail, kiểm tra model binding/root context. Tách đúng tầng lỗi trước khi thay configuration.

### 8.6. Log có kiểm soát

Trong môi trường chẩn đoán, có thể log:

```text
operation=GetOrder
expectedRoot={urn:example:orders:v1}GetOrderResponse
receivedRoot={urn:example:orders:v2}GetOrderResponse
jaxbContextPackage=com.example.orders.v1
schemaVersion=orders-v1
providerContract=orders-v2
correlationId=req-100
failureLayer=JAXB_UNMARSHAL
```

Không log toàn bộ SOAP Body nếu có dữ liệu cá nhân, tài khoản, token, chứng thư hoặc binary. Dùng fixture đã mask trong môi trường test có kiểm soát.

## 9. Viết test tái hiện lỗi JAXB

### 9.1. Test root QName đúng

```java
@Test
void unmarshalsResponseWithExpectedNamespace() throws Exception {
    String xml = """
        <ord:GetOrderResponse
            xmlns:ord="urn:example:orders:v1">
            <ord:orderId>ORD-100</ord:orderId>
        </ord:GetOrderResponse>
        """;

    JAXBContext context = JAXBContext.newInstance(
        GetOrderResponse.class
    );
    Unmarshaller unmarshaller = context.createUnmarshaller();

    GetOrderResponse result = (GetOrderResponse)
        unmarshaller.unmarshal(new StringReader(xml));

    assertEquals("ORD-100", result.getOrderId());
}
```

Ví dụ giả định class có @XmlRootElement với đúng namespace. Nếu generated type chỉ được khai báo bằng ObjectFactory, dùng typed unmarshal hoặc JAXBElement thay vì ép kiểu Object trực tiếp.

### 9.2. Test namespace sai phải fail

```java
@Test
void rejectsResponseFromDifferentContractNamespace() {
    String xml = """
        <ord:GetOrderResponse
            xmlns:ord="urn:example:orders:v2">
            <ord:orderId>ORD-100</ord:orderId>
        </ord:GetOrderResponse>
        """;

    assertThrows(JAXBException.class, () -> {
        JAXBContext context = JAXBContext.newInstance(
            GetOrderResponse.class
        );
        context.createUnmarshaller().unmarshal(
            new StringReader(xml)
        );
    });
}
```

Test này giả định JAXB model là strict root mapping v1. Nếu context có wildcard/lax mapping hoặc event handler permissive, kiểm tra expected behavior của model cụ thể.

### 9.3. Test root element declaration bằng JAXBElement

```java
@Test
void unmarshalsGlobalElementThroughObjectFactoryContext()
        throws Exception {
    JAXBContext context = JAXBContext.newInstance(
        ObjectFactory.class
    );

    JAXBElement<GetOrderResponse> root =
        context.createUnmarshaller().unmarshal(
            new StreamSource(new StringReader(xml)),
            GetOrderResponse.class
        );

    assertEquals(
        new QName("urn:example:orders:v1", "GetOrderResponse"),
        root.getName()
    );
    assertEquals("ORD-100", root.getValue().getOrderId());
}
```

Fixture xml phải chứa đúng root QName đã được ObjectFactory khai báo. Test đồng thời bảo đảm context biết factory/global element và trả đúng QName thực tế.

### 9.4. Test Spring Jaxb2Marshaller khởi tạo đúng context

Khởi tạo marshaller trong test và gọi afterPropertiesSet. Điều này giúp phát hiện lỗi context path, package hoặc JAXB provider trước integration suite. Sau đó marshal/unmarshal fixture contract đã pin.

### 9.5. Contract fixture regression

```text
src/test/resources/contracts/orders/
  v1/
    get-order-response.xml
    orders.xsd
  v2/
    get-order-response.xml
    orders.xsd
```

Đính kèm version/checksum/nguồn fixture trong test metadata. Không tự tải WSDL/XSD mới nhất từ provider mỗi lần build vì generated model có thể lệch mà không ai review.

### 9.6. Test phân biệt validator với unmarshaller

Viết test riêng cho:

1. XML well-formedness/parser.
2. XSD validation với schema version đã pin.
3. JAXB root/context unmarshalling không bật validator.
4. Spring-WS end-to-end với cấu hình production-like.

Khi test nào fail đầu tiên, đã biết tầng chịu trách nhiệm. Tránh gom tất cả vào một integration test duy nhất rồi chỉ nhận một exception wrapper sâu.

## 10. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân khả dĩ | Hành động xác minh |
| --- | --- | --- |
| URI nhận được là v2, expected là v1 | Provider/client contract version lệch | Kiểm tra WSDL/XSD endpoint và release provider |
| URI nhận được rỗng | XML element không namespace hoặc default namespace thiếu | Đọc xmlns trên root/child, đối chiếu elementFormDefault |
| Prefix khác nhưng URI giống | Prefix alias khác nhau | Không sửa; so QName |
| Root là đúng QName nhưng Expected elements none | Root declaration không được register hoặc context sai | Kiểm tra @XmlRootElement, ObjectFactory, jaxb.index và context path |
| Class tồn tại nhưng không known to context | Class không được đưa vào JAXBContext | Kiểm tra newInstance classes/package và classloader |
| Marshal báo unable to marshal type as element | Object không có root mapping | Dùng ObjectFactory/JAXBElement hoặc model có global root |
| Child element unexpected | Local element qualification/order/cardinality lệch | Đọc XSD sequence, choice, minOccurs và elementFormDefault |
| Root pass nhưng field null | Field annotation/namespace/access strategy mismatch | Kiểm tra @XmlElement, @XmlAccessorType, propOrder và child QName |
| Một operation fail, operation khác pass | Dùng sai package/context version cho một operation | Kiểm tra operation mapping và marshaller tương ứng |
| Test pass, production fail | Runtime schema/classpath khác test | Inspect packaged resources, dependency/classloader, config profile |
| Sau regenerate lỗi xuất hiện | Generated model đã đổi namespace/root API | Review package-info, ObjectFactory, generated diff |
| Context startup failure sau upgrade | javax/jakarta API hoặc runtime không cùng thế hệ | Dependency convergence, generated annotation package |
| Schema validation báo cvc-* trước JAXB | Payload vi phạm XSD | Chạy riêng validator, đọc line/column và schema version |
| SAXParseException | XML malformed/encoding/parser issue | Raw fixture đã mask, encoding declaration, parser cause |
| Wrong operation được chọn | @PayloadRoot QName không khớp payload root | Kiểm tra namespace + localPart và endpoint mapping |
| SOAP Body đúng nhưng response JAXB fail | Client unmarshaller khác contract/version | Kiểm tra response root QName và client context |
| Class từ JAR cũ được load | Dependency conflict/shading/application classloader | Code source location, dependency tree, classloader |
| Một child có namespace, child khác không | elementFormDefault hoặc local form khác | XSD declaration và package-level XmlSchema |
| Attribute không match namespace | Unprefixed attribute không thừa hưởng default namespace | attributeFormDefault, ref/name và QName |
| Không resolve XSD import/include | Catalog/resource path hoặc schema version sai | Resource URL, checksum, resolver mappings |

### 10.1. Trình tự điều tra theo tầng

```text
1. SOAP Envelope parse thành công không?
   -> kiểm tra SOAP version, XML parser và transport.

2. Endpoint mapping nhận đúng operation?
   -> kiểm tra payload root QName.

3. Schema validator có chạy và pass?
   -> kiểm tra schema URL/version và cvc error.

4. XML root QName thực tế là gì?
   -> log namespace URI + local name đã lọc.

5. JAXBContext có type và global element declaration?
   -> kiểm tra classes, context path, ObjectFactory.

6. Generated mapping có cùng namespace với schema?
   -> kiểm tra package-info, annotations, XJC output.

7. Runtime đang load model/schema từ đâu?
   -> kiểm tra class code source và packaged resources.

8. Business layer nhận object đúng và đủ?
   -> kiểm tra field mapping; không sửa XML ngoài hợp đồng.
```

## 11. Quy tắc sửa lỗi an toàn

### 11.1. Sửa source of truth

Nếu XML provider thực sự đã đổi contract, cập nhật XSD/WSDL artifact và regenerate model. Nếu XML chỉ sai so với contract đã thỏa thuận, yêu cầu provider sửa payload hoặc route tới đúng version endpoint.

### 11.2. Không xóa namespace để “cho JAXB nhận”

Xóa default namespace/prefix có thể làm QName thành namespace rỗng, tạo payload khác contract. Không dùng XSLT rewrite namespace trong production nếu không có một adapter contract-versioned và test rõ ràng.

### 11.3. Không bật lax/skip validation như bản sửa mặc định

Wildcard/lax processing có thể hữu ích cho extensibility khi được thiết kế trong XSD/JAXB model. Nó không phải biện pháp chữa lỗi cho namespace sai, schema version cũ hoặc context thiếu. Tách unknown extension khỏi required business payload.

### 11.4. Không chỉnh generated classes bằng tay

Thay namespace constant, thêm @XmlRootElement hoặc chỉnh @XmlElement trong source generated có thể bị ghi đè khi codegen. Sửa XSD/binding customization hoặc viết adapter/mapping ngoài generated package.

### 11.5. Tách contract versions

Nếu v1 và v2 cùng tồn tại, dùng packages/context riêng hoặc adapter conversion ở boundary. Không chọn marshaller dựa trên local element name vì tên giống nhau không chứng minh contract giống nhau.

### 11.6. Tránh catch-all và trả object rỗng

Không catch JAXBException rồi trả DTO mặc định/null để “không làm hỏng flow”. Điều đó có thể biến contract failure thành dữ liệu nghiệp vụ sai. Phân loại lỗi, tạo Fault/application error phù hợp và chặn side effects.

## 12. Bài thực hành có đáp án

### Bài 1. Prefix khác, namespace giống

Provider gửi prefix ns2 thay cho ord, nhưng URI vẫn là urn:example:orders:v1.

**Đáp án:** QName giống nhau. JAXB không nên fail chỉ vì prefix thay đổi.

### Bài 2. Local name giống, namespace khác

Provider trả GetOrderResponse ở namespace v2, client context là v1.

**Đáp án:** Đây là QName khác và có thể là contract version mismatch. Xác minh WSDL/XSD/endpoint version rồi chọn nâng consumer hoặc adapter/version riêng.

### Bài 3. Expected elements are none

Generated class GetOrderResponse tồn tại nhưng không có @XmlRootElement.

**Đáp án:** Kiểm tra ObjectFactory/@XmlElementDecl; unmarshal typed hoặc dùng JAXBElement thay vì giả định class tự là global root.

### Bài 4. Class không known to this context

Type OrderLine được generated nhưng context chỉ chứa GetOrderResponse.

**Đáp án:** Register type qua class list hoặc package context path phù hợp; kiểm tra ObjectFactory và model dependencies.

### Bài 5. Root pass, child unexpected

Root QName đúng nhưng orderId child không namespace trong khi XSD local elements qualified.

**Đáp án:** Kiểm tra elementFormDefault và XML default namespace/prefix ở child. Sửa theo XSD chứ không chỉ đổi root.

### Bài 6. Default namespace thiếu

Response bỏ xmlns trên root và child nhưng document vẫn well-formed.

**Đáp án:** QName thành namespace rỗng. XML well-formed không đồng nghĩa XSD/JAXB compatible.

### Bài 7. Attribute id không có namespace

Element có namespace nhưng attribute id không prefix.

**Đáp án:** Đây là hành vi XML Namespaces bình thường; unprefixed attribute không thừa hưởng default namespace. Kiểm tra attributeFormDefault/ref.

### Bài 8. @PayloadRoot đúng nhưng JAXB fail

Endpoint được route đúng theo payload root nhưng unmarshaller báo unexpected element.

**Đáp án:** @PayloadRoot chỉ chọn endpoint; JAXB mapping/context là bước khác. Kiểm tra generated model/context và child/root annotations.

### Bài 9. XSD validation fail trước JAXB

Log có cvc-complex-type.2.4.a.

**Đáp án:** Đây là schema validation failure; dùng schema version đúng, đọc expected child/order/occurrence. Không gọi đây là JAXB root mapping failure.

### Bài 10. Validator pass nhưng JAXB fail

Payload pass XSD nhưng context không nhận root.

**Đáp án:** Validator và JAXB context là hai cơ chế khác nhau. Kiểm tra @XmlRootElement, ObjectFactory, context path/classes.

### Bài 11. Chỉ một endpoint bị lỗi sau codegen

Các operation dùng hai package v1/v2 nhưng cùng local name.

**Đáp án:** Kiểm tra endpoint mapping, QName và marshaller selection; giữ context riêng cho từng contract version.

### Bài 12. Source XSD đúng nhưng runtime dùng namespace cũ

**Đáp án:** Có thể generated artifact/dependency/resource cũ đang được load. Xác minh class code source, schema resource URL/checksum và dependency tree.

### Bài 13. ObjectFactory thiếu trong context

Type class được add nhưng global element declaration không biết.

**Đáp án:** Thêm ObjectFactory hoặc dùng package context path phù hợp. Với typed unmarshal, kiểm tra QName root.

### Bài 14. Nên thêm @XmlRootElement vào generated class?

**Đáp án:** Không chỉnh generated code bằng tay như bản sửa mặc định. Sửa XSD/binding và regenerate hoặc sử dụng JAXBElement theo global declaration.

### Bài 15. Vì sao không đổi prefix trong XML để sửa lỗi?

**Đáp án:** Prefix không phải danh tính QName. Chỉ đổi prefix mà giữ URI không thay contract; đổi URI mới làm QName khác.

### Bài 16. JAXB 2.x model chạy với Jakarta JAXB 4.x?

**Đáp án:** Không coi là tương thích trực tiếp. Namespace API/annotations khác nhau. Chuyển đồng bộ codegen, generated sources và runtime dependencies.

### Bài 17. Có nên tắt PayloadValidatingInterceptor?

**Đáp án:** Không chỉ để chữa lỗi JAXB. Trước hết xác định validator có phải tầng fail không; giữ schema validation trừ khi có thay đổi contract/policy được review.

### Bài 18. Context path dùng sai package

**Đáp án:** Kiểm tra package generated, ObjectFactory/jaxb.index, classpath và context creation lúc startup. Dùng test gọi afterPropertiesSet.

### Bài 19. Hai XSD cùng namespace nhưng khác version

**Đáp án:** Namespace một mình không đủ version hóa schema artifact. Pin checksum/version, tránh hai resource cùng targetNamespace nhưng structure khác nhau không có rollout plan.

### Bài 20. Làm sao ngăn lỗi tái diễn?

**Đáp án:** Lưu provider fixtures, test QName/XSD/JAXB riêng từng tầng, pin schema/generated toolchain, kiểm tra resource/class origin và chạy end-to-end contract test trong CI.

## 13. Observability khi JAXB thất bại

### 13.1. Structured diagnostic event

Một diagnostic event hữu ích có thể gồm:

```text
event=SOAP_JAXB_UNMARSHAL_FAILED
operation=GetOrder
direction=CLIENT_RESPONSE
expectedQName={urn:example:orders:v1}GetOrderResponse
receivedQName={urn:example:orders:v2}GetOrderResponse
jaxbContext=com.example.orders.v1
schemaArtifact=orders-v1
schemaChecksum=...
providerVersion=...
failureLayer=JAXB_ROOT_MAPPING
exceptionType=UnmarshalException
correlationId=req-100
```

Chỉ ghi các metadata đã lọc. Không log full SOAP payload, username/password, WS-Security token, certificate private material, PII hoặc binary.

### 13.2. Metrics có cardinality thấp

Có thể theo dõi:

```text
soap_jaxb_failures_total{operation,failure_layer}
soap_schema_validation_failures_total{operation}
soap_contract_version_mismatch_total{operation}
soap_unmarshal_duration_seconds{operation}
soap_client_faults_total{operation,fault_category}
```

Không dùng raw QName tùy ý, exception message, document ID hoặc namespace do bên ngoài tùy ý gửi làm metric label; cardinality có thể tăng không giới hạn.

### 13.3. Alert và dashboard

Nên theo dõi:

- Tỷ lệ JAXB unmarshal failure tăng đột biến sau provider release.
- Schema validation failures theo operation.
- Số lỗi QName namespace v1/v2 không khớp.
- Client/server SOAP Fault categories.
- JAXB context startup failure sau deploy.
- Generated artifact/schema checksum của phiên bản đang chạy.
- Tần suất lỗi chỉ xảy ra ở một partner hoặc một endpoint.

Alert cần gắn deployment/provider version và correlation ID để điều tra nhanh; không đưa payload nhạy cảm vào alert.

## 14. Checklist nghiệm thu production

| Nhóm | Câu hỏi kiểm tra |
| --- | --- |
| XML | Payload có well-formed và encoding đúng? |
| QName | Root/child namespace URI + local name có khớp contract? |
| Prefix | Test có độc lập với prefix alias không? |
| Default namespace | Root/child qualified/unqualified đúng XSD? |
| Attributes | attributeFormDefault và unprefixed attributes được hiểu đúng? |
| XSD | Target namespace, imports/includes, sequence, choice và occurrence đúng version? |
| Root mapping | Class có @XmlRootElement hay cần JAXBElement/ObjectFactory? |
| JAXBContext | Context chứa tất cả type và global element declarations cần thiết? |
| Package | package-info.java/@XmlSchema và ObjectFactory được generate đúng? |
| Code generation | XJC/JAXB plugin, binding files và schema inputs được pin? |
| Dependencies | JAXB API/runtime và generated annotations cùng javax hoặc jakarta thế hệ? |
| Runtime classpath | Class/schema đang load từ artifact/resource nào? |
| Client | Jaxb2Marshaller context version khớp response contract? |
| Server | @PayloadRoot namespace/localPart khớp payload root? |
| Validation | Đã phân biệt XSD validator failure với JAXB unmarshalling failure? |
| Fixtures | Có response fixtures v1/v2 đã pin và được review? |
| Regression | Test đúng/sai namespace, root mapping, context và child qualification? |
| Diagnostics | Log QName, operation, context/schema version và correlation ID? |
| Privacy | Không log SOAP body, credentials, token hoặc PII? |
| Rollout | Provider/client contract version đã được rollout đồng bộ hoặc adapter rõ? |

### 14.1. Release gate tối thiểu

```text
Before release:
  [ ] schema and WSDL artifact pinned
  [ ] generated sources diff reviewed
  [ ] JAXBContext created successfully at startup
  [ ] root QName positive and negative tests pass
  [ ] ObjectFactory/JAXBElement tests pass where required
  [ ] child namespace/elementFormDefault fixtures pass
  [ ] validator and unmarshaller tested separately
  [ ] Spring-WS client/server contract tests pass
  [ ] v1/v2 consumer-provider matrix reviewed
  [ ] logs contain correlation metadata and no raw secrets
```

## 15. Tổng kết

Lỗi JAXB không chỉ là lỗi đọc XML. Nó thường nằm ở ranh giới giữa contract, QName, generated model và runtime context:

- XML well-formed không đảm bảo QName phù hợp XSD/JAXB.
- QName là namespace URI + local name; prefix chỉ là alias.
- Root element không được biết thường liên quan @XmlRootElement hoặc global element declaration trong ObjectFactory/@XmlElementDecl.
- Class tồn tại không có nghĩa JAXBContext đã biết class/type/root element.
- elementFormDefault, @XmlSchema và field annotations quyết định namespace qualification của child elements.
- Spring-WS endpoint mapping theo QName khác với XSD validation và JAXB unmarshalling; cần test từng tầng.
- Generated sources, schema imports/resources, context path và classpath phải cùng contract version.
- javax JAXB và jakarta JAXB là hai thế hệ API; không trộn generated model/runtime không tương thích.
- Sửa ở source of truth: XSD/WSDL/binding, regenerate model hoặc route tới context đúng version; không vá generated code và không tắt validation tùy tiện.
- Observability cần QName/version/correlation ID đã lọc, không cần ghi raw SOAP body.

### Mô hình chẩn đoán

```text
SOAP Body XML
     |
     v
Parse XML / identify QName
     |
     v
Endpoint operation mapping
     |
     v
XSD validation?
  | fail -> schema/namespace/element-order issue
  v pass
     |
     v
JAXBContext knows Java type?
  | no -> class/package/context issue
  v yes
     |
     v
JAXB knows root element QName?
  | no -> @XmlRootElement / ObjectFactory / JAXBElement
  v yes
     |
     v
Child elements match namespace/form/order?
  | no -> XSD/generated annotation drift
  v yes
     |
     v
Business mapping and validation
```

**Nguyên tắc thực hành:** không đoán namespace từ prefix hoặc tên class. Đặt cạnh nhau QName XML nhận được, QName XSD, annotations generated và JAXBContext đang chạy; tìm tầng đầu tiên không khớp rồi sửa đúng source of truth.

### Tài liệu tham khảo

- [Jakarta XML Binding 4.0 Specification](https://jakarta.ee/specifications/xml-binding/4.0/).
- [Jakarta XML Binding API — JAXBContext](https://jakarta.ee/specifications/xml-binding/4.0/apidocs/jakarta.xml.bind/jakarta/xml/bind/jaxbcontext).
- [Jakarta XML Binding API — XmlRootElement](https://jakarta.ee/specifications/xml-binding/4.0/apidocs/jakarta.xml.bind/jakarta/xml/bind/annotation/xmlrootelement).
- [Jakarta XML Binding API — JAXBElement](https://jakarta.ee/specifications/xml-binding/4.0/apidocs/jakarta.xml.bind/jakarta/xml/bind/jaxbelement).
- [Eclipse JAXB RI — JAXB/XJC](https://eclipse-ee4j.github.io/jaxb-ri/).
- [Spring Framework — Jaxb2Marshaller API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html).
- [Spring Web Services — Reference Documentation](https://docs.spring.io/spring-ws/docs/current/reference/html/).
- [W3C — XML Namespaces](https://www.w3.org/TR/xml-names/).
- [W3C — XML Schema Part 1: Structures](https://www.w3.org/TR/xmlschema-1/).
- [W3C — XML Schema Part 2: Datatypes](https://www.w3.org/TR/xmlschema-2/).
