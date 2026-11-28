# Sinh lớp Java từ XSD và quản lý mã đầu ra được tạo tự động

Trong tích hợp SOAP theo hướng **contract-first**, các bên thống nhất trước cấu trúc thông điệp XML bằng **XSD** và giao diện dịch vụ bằng **WSDL**. Lập trình viên Java sau đó cần đọc/ghi các thông điệp đó một cách an toàn và có kiểu dữ liệu rõ ràng. **JAXB (Jakarta XML Binding)** giải quyết phần ánh xạ XML ↔ đối tượng Java; công cụ sinh mã **XJC** giúp tạo các lớp Java từ hợp đồng XSD mà không cần viết thủ công từng annotation XML.

Sinh mã chỉ là một nửa bài toán. Nửa còn lại là **quản lý nguồn sinh mã, đầu ra được tạo tự động, phiên bản plugin/runtime, namespace và quá trình tái sinh mã** để mỗi lần build cho kết quả có thể dự đoán. Nếu chỉnh trực tiếp lớp được sinh, bỏ sót schema import, trộn `javax` với `jakarta` hoặc giữ lại mã cũ sau khi XSD thay đổi, ứng dụng vẫn có thể biên dịch nhưng không còn tuân thủ SOAP contract với đối tác.

Bài thuộc chương **Sinh mã JAXB** của module **SPRING_WEB_SERVICES**. Nó đặt JAXB vào toàn bộ chuỗi XSD/WSDL → SOAP endpoint/client → SOAP Fault/interceptor → XML security/WS-Security/chứng chỉ → kiểm thử tương thích, nhưng tập trung sâu vào việc **sinh lớp Java từ XSD và quản lý generated sources**.

## 1. XSD là nguồn sự thật, Java là sản phẩm được sinh

Ở cách tiếp cận contract-first:

~~~mermaid
flowchart LR
    X["XSD đã phê duyệt<br/>global elements/types"] --> G["XJC / JAXB code generation"]
    G --> J["Java classes<br/>ObjectFactory / package-info"]
    J --> M["JAXB marshal / unmarshal"]
    M --> S["Spring-WS endpoint<br/>và SOAP client"]
    W["WSDL<br/>operation / binding / port"] --> S
~~~

**XSD** quy định XML hợp lệ. **XJC** đọc XSD, tạo lớp Java và metadata binding. **JAXB runtime** đọc các annotation/metadata đó để biến XML thành object graph và ngược lại. **Spring-WS** sử dụng các đối tượng này để làm việc với payload SOAP.

| Thành phần | Trách nhiệm | Điều nó không tự làm |
| --- | --- | --- |
| **XSD** | Định nghĩa QName, kiểu dữ liệu, phần tử bắt buộc, thứ tự, tập giá trị | Không thực hiện nghiệp vụ hay gửi SOAP |
| **XJC** | Tạo Java source từ XSD và quy tắc binding | Không thay thế SOAP endpoint hoặc SOAP client transport |
| **JAXB API/runtime** | Marshal/unmarshal XML ↔ đối tượng Java | Không tự quyết định operation WSDL hoặc xử lý WS-Security |
| **WSDL** | Mô tả service, operation, message, binding và endpoint | Không phải lớp Java triển khai nghiệp vụ |
| **Spring-WS** | Nhận/gửi SOAP, định tuyến endpoint, interceptor và SOAP Fault | Không có nghĩa tất cả payload được validate XSD tự động |

Sinh JAXB **từ XSD** khác với sinh một SOAP client đầy đủ **từ WSDL**. Các công cụ WSDL-to-Java có thể sinh thêm service/port/proxy và cũng sinh JAXB types; còn XJC thuần túy chỉ xử lý phần hợp đồng XML Schema.

## 2. Ví dụ XSD: hợp đồng truy vấn đơn hàng

Giả sử đối tác gửi `GetOrderRequest` để lấy trạng thái đơn hàng. Tệp `src/main/resources/xsd/orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
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
                <xs:element name="status" type="ord:OrderStatusType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Trong schema này:

- `GetOrderRequest` và `GetOrderResponse` là **global elements** thuộc namespace `urn:example:orders:v1`.
- Các local elements `orderId` và `status` cũng thuộc namespace đó vì `elementFormDefault="qualified"`.
- `OrderStatusType` hạn chế `status` vào ba giá trị; JAXB thường sinh enum tương ứng.
- `xs:sequence` yêu cầu `orderId` đứng trước `status` trong response.

Payload request hợp schema:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:GetOrderRequest>
~~~

Việc thay tiền tố `ord` bằng `o` không làm đổi QName nếu cùng namespace URI; nhưng bỏ namespace của `orderId` hoặc thay namespace v1 bằng v2 sẽ làm XML không khớp schema ví dụ.

## 3. Một lần sinh mã JAXB tạo những gì?

Tùy phiên bản XJC, cấu trúc schema và tùy chỉnh binding, kết quả có thể có dạng:

~~~text
target/generated-sources/jaxb/
└── org/example/orders/v1/
    ├── GetOrderRequest.java
    ├── GetOrderResponse.java
    ├── OrderStatusType.java
    ├── ObjectFactory.java
    └── package-info.java
~~~

Đường dẫn và tên package trên **chỉ là minh họa**; XJC có quy tắc suy package từ namespace và có thể được cấu hình package khác. Không nên suy luận package chỉ từ tên thư mục XSD hoặc từ prefix `ord`.

### Lớp payload

Một lớp được sinh từ `GetOrderRequest` có thể trông giống ví dụ rút gọn:

~~~java
// MINH HỌA kết quả XJC; không sửa trực tiếp file generated.
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "", propOrder = {"orderId"})
@XmlRootElement(name = "GetOrderRequest")
public class GetOrderRequest {
    @XmlElement(required = true)
    protected String orderId;

    public String getOrderId() { return orderId; }
    public void setOrderId(String value) { this.orderId = value; }
}
~~~

Các annotation minh họa cách JAXB biết **tên phần tử**, **thứ tự field** và **cách truy cập**. Namespace của root và local elements cũng có thể được khai báo thông qua `package-info.java`:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED)
package org.example.orders.v1;
~~~

Đừng sao chép lớp minh họa thành “mã chuẩn”: việc XJC sinh `@XmlRootElement`, `@XmlElementRef` hay `JAXBElement` phụ thuộc phần tử và kiểu của XSD. **File sinh thực tế là kết quả ràng buộc của công cụ và schema cụ thể.**

### Enum được sinh từ enumeration

XJC có thể ánh xạ `OrderStatusType` thành một enum:

~~~java
@XmlType(name = "OrderStatusType")
@XmlEnum
public enum OrderStatusType {
    PENDING, CONFIRMED, CANCELLED
}
~~~

Ví dụ giả định đã import các annotation Jakarta JAXB. Tên hằng và các annotation bổ sung phụ thuộc bộ sinh; nếu tên XML không hợp lệ làm identifier Java, công cụ có thể dùng `@XmlEnumValue` để giữ nguyên giá trị XML.

### `ObjectFactory` và `package-info.java`

- **`ObjectFactory`** thường chứa các phương thức factory và có thể chứa `@XmlElementDecl` để mô tả **global XML elements** bằng `JAXBElement<T>`.
- **`package-info.java`** có thể chứa `@XmlSchema` để định nghĩa namespace mặc định và chính sách qualified/unqualified cho các lớp cùng package.
- **Lớp type riêng** được sinh cho named complex type/simple type; một global element sử dụng named type đôi khi được biểu diễn qua `JAXBElement<T>` thay vì một class có `@XmlRootElement`.

Vì thế, khi không thấy `@XmlRootElement` trên lớp type, đừng tự thêm annotation vào file sinh; hãy kiểm tra `ObjectFactory` và cách marshalling mà schema yêu cầu.

## 4. Chọn đúng hệ JAXB cho phiên bản Spring

Có hai họ namespace Java dễ nhầm:

| Ngăn xếp thường gặp | API JAXB trong mã Java | Hướng lựa chọn công cụ sinh |
| --- | --- | --- |
| Ứng dụng Java EE / Jakarta EE cũ, nhiều dự án dùng Spring Boot 2 | `javax.xml.bind.*` | XJC/JAXB API và runtime thuộc hệ `javax` tương thích |
| Ứng dụng Jakarta hiện đại, nhiều dự án dùng Spring Boot 3 và Spring Framework 6 | `jakarta.xml.bind.*` | XJC/JAXB API và runtime thuộc hệ `jakarta` tương thích |

**Không trộn lẫn hai hệ trên.** Mã được sinh chứa annotation `javax.xml.bind.annotation.*` không trở thành JAXB Jakarta chỉ nhờ đổi dependency runtime sang `jakarta.xml.bind-api`. Ngược lại, một endpoint Spring-WS dùng ngăn xếp Jakarta có thể không ánh xạ được đúng các classes được sinh bởi XJC Javax cũ.

Từ JDK 11, JAXB/XJC **không còn được cung cấp sẵn trong JDK** như cách một số dự án Java 8 từng sử dụng. Hãy khai báo rõ **plugin/code-generation tool** ở build time và **JAXB API + runtime** phù hợp ở application runtime. Không dựa vào `xjc` có sẵn trong `JAVA_HOME/bin`.

### Phụ thuộc Maven theo ứng dụng Jakarta

Ví dụ khai báo dependencies (phiên bản có thể do dependency management của dự án quản lý):

~~~xml
<dependencies>
    <dependency>
        <groupId>jakarta.xml.bind</groupId>
        <artifactId>jakarta.xml.bind-api</artifactId>
    </dependency>
    <dependency>
        <groupId>org.glassfish.jaxb</groupId>
        <artifactId>jaxb-runtime</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn này giả định BOM/parent đã cung cấp version. Nếu không có dependency management, Maven sẽ yêu cầu pin version tương thích rõ ràng. **Phụ thuộc runtime không tự tạo lớp từ XSD**; cần một plugin sinh mã riêng.

## 5. Tự động sinh mã trong Maven: nguyên tắc triển khai

Một cấu hình build đáng tin cậy phải xác định:

1. **Nguồn vào:** XSD gốc và toàn bộ import/include của nó; không chọn nhầm các schema khác không thuộc contract.
2. **Phiên bản tool:** plugin và XJC tương thích với runtime Jakarta/Javax của ứng dụng.
3. **Đầu ra:** một thư mục generated sources dưới `target/` hoặc output build tương đương.
4. **Thời điểm chạy:** generate trước `compile`, ví dụ phase `generate-sources`.
5. **Tính lặp lại:** sau `clean` và chạy build trên CI, cùng hợp đồng + cấu hình phải tạo mã đúng như dự kiến.

Ví dụ cho dự án **Jakarta JAXB** sử dụng Maven và họ plugin XJC của JAXB Tools:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.jvnet.jaxb</groupId>
      <artifactId>jaxb-maven-plugin</artifactId>
      <version>4.0.8</version>
      <executions>
        <execution>
          <id>generate-jaxb-contract</id>
          <phase>generate-sources</phase>
          <goals>
            <goal>generate</goal>
          </goals>
          <configuration>
            <schemaDirectory>src/main/resources/xsd</schemaDirectory>
            <schemaIncludes>
              <include>orders.xsd</include>
            </schemaIncludes>
            <generateDirectory>
              ${project.build.directory}/generated-sources/jaxb
            </generateDirectory>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Đây là **cấu hình minh họa cho một họ plugin và phiên bản được pin cụ thể**; plugin, các tham số và phiên bản XJC cần được đối chiếu với tài liệu của phiên bản dự án đang dùng trước khi đưa vào pipeline thật. Ví dụ chỉ chọn **XSD root `orders.xsd`**; schema được root include/import phải được công cụ resolve theo `schemaLocation` hoặc resolver. Không sinh cùng một định nghĩa nhiều lần chỉ vì nó xuất hiện dưới nhiều XSD phụ thuộc.

Khi plugin thêm `target/generated-sources/jaxb` vào compile source roots, Maven sẽ biên dịch generated classes trong bước compile. Hãy xác nhận điều này bằng output build/IDE; không sao chép chúng bằng tay sang `src/main/java` để IDE “nhìn thấy” lớp.

Ở một số dự án, việc chọn **package mặc định cho mọi schema** làm các namespace khác nhau bị gom vào một package và có thể trùng tên lớp. Khi schema có nhiều namespace, trước tiên nên để tool tạo mapping package tương ứng hoặc sử dụng file binding (`.xjb`) có kiểm soát.

### Chạy build và biết điều gì phải xuất hiện

Trong thư mục dự án Maven (lệnh minh họa, không thực thi trong bài này):

~~~bash
mvn clean generate-sources
mvn test
~~~

Sau `generate-sources`, cần xác nhận tệp Java được sinh vào thư mục đã cấu hình, chứa annotation của đúng họ JAXB và được đưa vào classpath biên dịch. Khi XJC báo không tìm thấy XSD dependency, sửa **schemaLocation, base URI, resolver/catalog**; không đổi `targetNamespace` của hợp đồng chỉ để vượt lỗi tải file.

> **Ranh giới trách nhiệm:** mã nguồn do con người viết ở `src/main/java`; mã do XJC tạo ở thư mục generated sources. Việc tổ chức này giúp xoá và tái tạo generated output an toàn qua `clean`.

## 6. Mapping XML Schema sang Java: các quy tắc cần chú ý

| XSD | Kiểu Java thường gặp | Điểm cần thẩm định |
| --- | --- | --- |
| `xs:string` | `String` | Pattern, length, enumeration không tự thành mọi phép kiểm tra nghiệp vụ |
| `xs:int`, `xs:long` | primitive hoặc wrapper Java | Optional/nillable và binding có thể ảnh hưởng lựa chọn |
| `xs:decimal` | `BigDecimal` | Dùng kiểu thập phân chính xác cho tiền; không ép sang `double` tùy tiện |
| `xs:dateTime` | `XMLGregorianCalendar` theo mặc định phổ biến | Timezone, XML lexical form, các custom binding sang `java.time` |
| `xs:boolean` | `boolean` hoặc `Boolean` | Phân biệt “vắng mặt” với false khi schema cho phép |
| `xs:base64Binary` | `byte[]` hoặc kiểu tùy binding/attachment | Cần kiểm tra payload lớn và MTOM nếu có |
| `xs:enumeration` | `enum` hoặc ánh xạ khác tùy cấu trúc | Client cũ có thể không biết giá trị enum bổ sung |
| `maxOccurs="unbounded"` | `List<T>` | Thường là live list; có thể không có setter cho toàn bộ danh sách |
| `xs:choice` | Nhiều biến thể binding như `JAXBElement`/`@XmlElements` | Cần kiểm tra các nhánh hợp lệ |
| `minOccurs="0"` và `nillable` | Có thể là nullable hoặc `JAXBElement<T>` | **Absent**, **nil** và **empty** không đồng nghĩa |

Generated classes chỉ phản ánh một phần ràng buộc. Ví dụ `orderId` dùng `String` dù XSD có `xs:pattern`; gọi `setOrderId("invalid")` **không mặc định ném lỗi ngay**. Muốn xác nhận XML đầu ra hợp XSD, phải cấu hình schema validation và kiểm thử.

### Danh sách JAXB thường là live list

Với `maxOccurs="unbounded"`, XJC thường sinh getter dạng:

~~~java
// Minh họa generated style:
public List<OrderItem> getItem() {
    if (item == null) {
        item = new ArrayList<>();
    }
    return this.item;
}
~~~

Người gọi thêm phần tử bằng `request.getItem().add(item)`, thay vì chờ setter `setItem(List<...>)` không phải lúc nào cũng được sinh. Vì trả về danh sách có thể chỉnh sửa trực tiếp, tránh chia sẻ một đối tượng JAXB mutable giữa nhiều request/thread.

### Absent, nil và empty

Ba trường hợp sau có thể khác nhau:

~~~xml
<!-- 1. Không có phần tử -->

<ord:note xmlns:ord="urn:example:orders:v1"/>

<ord:note xmlns:ord="urn:example:orders:v1"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:nil="true"/>
~~~

- **Absent:** hợp lệ khi khai báo cho phép vắng mặt (ví dụ `minOccurs="0"`).
- **Empty:** phần tử tồn tại với nội dung rỗng; có thể hợp lệ hoặc sai kiểu dữ liệu.
- **Nil:** phần tử tồn tại và đánh dấu nil; chỉ hợp lệ khi khai báo `nillable="true"`.

Nếu ứng dụng phải phân biệt cả ba trạng thái, kiểm tra chính xác mapping XJC/JAXB sinh ra (có thể cần `JAXBElement<T>` cùng trạng thái nil). Không coi mọi giá trị Java `null` là một kiểu XML giống nhau trong mọi schema.

## 7. Generated package, namespace và `ObjectFactory`

Một project có thể cần nhiều namespace XSD:

~~~text
urn:example:orders:v1       → ...orders.v1
urn:example:common:v1       → ...common.v1
urn:example:billing:v1      → ...billing.v1
~~~

Khi root XSD dùng `xs:include` (cùng namespace) hoặc `xs:import` (khác namespace), XJC phải thấy **toàn bộ graph dependency**. Công cụ có thể sinh nhiều package Java; **Java package không phải QName của XML**. Có thể đổi Java package mà vẫn giữ namespace XML nếu binding được cấu hình đúng và lớp sinh giữ metadata phù hợp.

### Khi thiếu `@XmlRootElement`

Với một named complex type được gắn vào global element, công cụ có thể tạo class mô tả type và một factory method cho global element. Khi đó cần marshal **`JAXBElement<T>`**:

~~~java
// Minh họa cho schema/toolchain sinh factory tương ứng.
ObjectFactory factory = new ObjectFactory();
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1024");

JAXBElement<GetOrderRequest> root =
        factory.createGetOrderRequest(request);
marshaller.marshal(root, outputStream);
~~~

Không mặc định mọi XSD đều sinh phương thức factory với tên trên. Hãy xem **`ObjectFactory` thực tế**. Nếu class đã có `@XmlRootElement` phù hợp, có thể marshal trực tiếp class. Mục tiêu là bảo đảm root element được xuất đúng **QName**, không phải ép công cụ sinh ra đúng một dạng Java theo sở thích.

### Dùng file `.xjb` để tùy chỉnh, thay vì sửa Java sinh mã

Trong trường hợp cần đổi Java package, tên property trùng từ khóa Java hoặc ánh xạ kiểu thời gian, hãy cân nhắc **external binding file**. Quy tắc binding nên được lưu, review và version cùng XSD; plugin được cấu hình đọc file đó trước khi sinh mã.

Điểm cần thận trọng:

- Cú pháp và namespace của binding file khác giữa JAXB/XJC `javax` đời cũ và Jakarta đời mới.
- Tùy chỉnh package hoặc property name **không được âm thầm đổi QName** của hợp đồng công bố.
- Với hai schema khác namespace, gom vào cùng package có thể tạo trùng tên `ObjectFactory`, `package-info` hoặc classes.
- Khi thay công cụ sinh mã, kiểm thử cả mã sinh, XML runtime và compatibility; không chỉ dựa vào việc build Java thành công.

## 8. Tích hợp JAXB classes với Spring-WS endpoint

Giả sử các lớp JAXB đã được sinh tương ứng với XSD ở phần 2 và endpoint Spring-WS được cấu hình hỗ trợ JAXB payload:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService orderService;

    public OrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        GetOrderResponse response = new GetOrderResponse();
        response.setOrderId(request.getOrderId());
        response.setStatus(orderService.findStatus(request.getOrderId()));
        return response;
    }
}
~~~

Ở đây:

1. `@PayloadRoot` tìm method theo **namespace + local name của root XML trong SOAP Body**, không theo package Java.
2. JAXB binding biến request payload thành đối tượng Java để endpoint xử lý.
3. Service nghiệp vụ quyết định trạng thái đơn hàng, tách khỏi lớp JAXB được sinh.
4. Response được marshal thành XML theo schema và cấu hình JAXB; application phải bảo đảm dữ liệu hợp lệ, không chỉ gán được vào setter.

Mã là ví dụ rút gọn: chưa có dependency, imports cho generated classes, cấu hình schema validation, servlet, WSDL, SOAP Fault và security interceptor.

### JAXB không thay thế WSDL

Ngay cả khi XML được tạo bởi lớp `GetOrderRequest`, client vẫn cần biết **operation và binding SOAP**, `SOAPAction` nếu hợp đồng yêu cầu, địa chỉ endpoint, SOAP version và các header bảo mật. Những thông tin đó thuộc **WSDL và chính sách tích hợp**, không được XJC từ XSD đơn lẻ tạo ra đầy đủ.

## 9. Dùng `Jaxb2Marshaller` trong SOAP client

Spring-WS cung cấp `Jaxb2Marshaller` để tích hợp JAXB vào Spring. Ví dụ minh họa trong ứng dụng Jakarta đã có generated package `org.example.orders.v1`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class SoapClientConfig {
    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("org.example.orders.v1");
        return marshaller;
    }

    @Bean
    public WebServiceTemplate ordersTemplate(Jaxb2Marshaller ordersMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(ordersMarshaller);
        template.setUnmarshaller(ordersMarshaller);
        template.setDefaultUri("https://partner.example.org/soap/orders");
        return template;
    }
}
~~~

`setContextPath` phù hợp khi generated package có metadata JAXB như `ObjectFactory`. Nếu dùng cách scan package hoặc nhiều namespace, cần cấu hình đúng các package/classes mà runtime hiểu; không nên đặt context path thành namespace URI của XSD vì hai khái niệm khác nhau.

Gửi request (giả định generated root dùng `@XmlRootElement`):

~~~java
GetOrderRequest request = new GetOrderRequest();
request.setOrderId("ORD-1024");

GetOrderResponse result = (GetOrderResponse)
    ordersTemplate.marshalSendAndReceive(request);
~~~

Nếu root phải được biểu diễn bằng `JAXBElement`, hãy tạo request qua `ObjectFactory` và xử lý kiểu giá trị phản hồi theo binding thực tế; kiểu Java trả về có thể là `JAXBElement<GetOrderResponse>`. Khi cần SOAPAction trong SOAP 1.1, gửi callback thích hợp (ví dụ `SoapActionCallback`) theo WSDL.

**`WebServiceTemplate` xử lý gửi SOAP, còn JAXB xử lý payload XML**; cả hai đều cần cấu hình bảo mật và transport riêng cho những dịch vụ dùng TLS/mTLS, WS-Security, timeout hoặc chứng chỉ.

## 10. Quy tắc quản lý generated sources

Đây là nguyên tắc cốt lõi của bài:

> **Không sửa trực tiếp file Java do XJC sinh ra.** Mọi thay đổi hợp đồng phải bắt đầu từ XSD hoặc binding configuration, sau đó sinh lại mã.

Mô hình thư mục thường dùng:

~~~text
project/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── resources/xsd/orders.xsd
│   │   └── java/org/example/service/OrderService.java
│   └── test/
│       └── ...
└── target/
    └── generated-sources/jaxb/...  # Do build tạo; không sửa tay
~~~

**Tệp cần version control:** XSD/WSDL gốc, binding (`.xjb`) nếu có, build plugin/config, code Java tự viết, tests và mẫu SOAP XML đã được kiểm tra. **Thư mục đầu ra `target/`:** thường là build artifact, không commit.

### Commit generated code hay không?

| Chiến lược | Lợi ích | Rủi ro/cách kiểm soát |
| --- | --- | --- |
| **Không commit generated Java** (ưu tiên khi build tái sinh được) | Tránh diff lớn và bất đồng giữa XSD với Java | CI phải có plugin/dependencies; mọi developer phải sinh được |
| **Commit generated Java** khi có ràng buộc phân phối/toolchain | Người dùng không cần chạy XJC để tiêu thụ source | Phải có quy trình regeneration và kiểm tra diff; tránh sửa thủ công |
| **Phát hành JAR model riêng** chứa classes JAXB | Nhiều ứng dụng dùng cùng artifact đã versioned | Quản lý version API, JAXB runtime và XML namespace, không dùng chung tùy tiện giữa v1/v2 |

Không có chính sách duy nhất cho mọi tổ chức. Nhưng nếu commit mã được sinh, phải xác định một **quy trình authoritative**: ai thay đổi XSD, cách regenerate, phiên bản tool và bước CI xác nhận mã sinh không bị lệch.

### Tách model JAXB khỏi domain model

JAXB class thường có getter/setter mutable, annotation XML và cấu trúc phụ thuộc trực tiếp vào schema của đối tác. Không nên để các lớp này lan rộng thành domain model hoặc DTO REST của toàn hệ thống.

Ví dụ:

~~~text
SOAP XML
    ↓ JAXB unmarshal
GetOrderRequest (generated contract model)
    ↓ adapter / validation
GetOrderQuery (application DTO)
    ↓ service
Order (domain model)
    ↓ response mapper
GetOrderResponse (generated contract model)
    ↓ JAXB marshal
SOAP XML
~~~

Khi đối tác thêm một trường optional vào SOAP response, adapter có thể đổi nhưng thuật toán nghiệp vụ và API nội bộ không nhất thiết đổi theo. Điều này đặc biệt hữu ích khi doanh nghiệp duy trì song song nhiều phiên bản SOAP contract.

## 11. Quy trình tái sinh mã khi XSD thay đổi

Khi contract được cập nhật, đừng mở class generated để sửa annotation hoặc setter:

1. **Xác định thay đổi ở XSD/WSDL**: đổi QName, thêm phần tử, đổi type, thay enum hay nillable/optional.
2. **Đánh giá tương thích** với client hiện hữu; nhận diện thay đổi có thể phá vỡ contract trước khi codegen.
3. **Cập nhật XSD và binding file** theo quy trình phê duyệt; đảm bảo mọi `xs:include`/`xs:import` resolve được.
4. **Chạy clean generation** bằng toolchain đã pin (JDK, plugin, XJC), không ghép mã cũ với mã mới.
5. **Kiểm tra generated diff**: tên class, namespace, `ObjectFactory`, `@XmlType(propOrder)`, enum, type Java, nullability.
6. **Sửa adapter/service code tự viết** để thích ứng với thay đổi hợp đồng; không chỉnh file trong `target/generated-sources`.
7. **Kiểm thử XML thực tế và client tương thích**, sau đó version/publish cùng XSD/WSDL.

### Tránh file “mồ côi” sau khi đổi tên type

Giả sử XSD v1 sinh `OldOrderType.java`, sau đó v2 đổi thành `OrderType.java`. Nếu XJC sinh chồng vào thư mục cũ mà không xóa output, lớp `OldOrderType` có thể vẫn nằm đó và được biên dịch dù contract mới không còn type này.

Vì vậy, pipeline nên sinh vào **đầu ra sạch** hoặc dùng cơ chế clear output của plugin một cách có chủ đích. Không xóa nhầm thư mục chứa mã tự viết. Bước `mvn clean generate-sources` trong ví dụ Maven giúp phát hiện tình trạng mã cũ còn sót.

### XJC cùng version vẫn có thể phụ thuộc môi trường

Để build lặp lại, nên pin:

- JDK/toolchain và Maven wrapper hoặc môi trường build tương đương.
- Phiên bản plugin, XJC và dependencies cần thiết.
- XSD/WSDL, external binding files, resolver/catalog và đường dẫn import/include.
- Cài đặt tạo tên package, encoding, thông số sinh mã và các plugin XJC mở rộng.

Khi kiểm tra diff, chú ý những header hoặc metadata có timestamp do phiên bản công cụ tạo ra. Nếu công cụ có tùy chọn suppress timestamp/header, có thể sử dụng để giữ output ổn định; phải xác nhận tính năng và tên tham số của plugin thực tế.

## 12. Nhiều namespace, package collision và quản lý phiên bản

Đây là một số trường hợp thường gặp:

| Thay đổi/đặc điểm XSD | Rủi ro JAXB | Cách xử lý |
| --- | --- | --- |
| Hai namespace cùng định nghĩa `StatusType` | Đụng tên nếu ép chung package | Tách package theo namespace hoặc external binding rõ ràng |
| `xs:include` cùng namespace | Sinh lặp định nghĩa khi cấu hình cả root và included file như hai input độc lập | Sinh từ root, xác nhận import/include graph |
| `xs:import` đến namespace chung | Thiếu class khi schemaLocation/resolver không tìm được | Đóng gói đủ dependency và kiểm thử codegen từ môi trường sạch |
| Thay `urn:example:orders:v1` thành v2 | `package-info`/QName và endpoint mapping có thể đổi | Quản lý version, không thay namespace tùy ý |
| Bổ sung enum value | Client đã sinh enum cũ không nhận biết giá trị mới | Kiểm thử backward compatibility, có thể cần contract v2 |
| Đổi field từ required sang optional hoặc nillable | Kiểu Java/`JAXBElement` và cách marshal có thể đổi | Kiểm thử absent/nil/empty; cập nhật mapper |
| Đổi XML type `xs:decimal` sang `xs:double` | Mất độ chính xác khi dùng tiền | Đánh giá hợp đồng và quy tắc nghiệp vụ |

Tránh giải pháp “thêm annotation bằng tay vào generated class để client chạy được”. Lỗi QName nên được sửa ở XSD/binding/toolchain hoặc adapter phù hợp, rồi **tái sinh và kiểm chứng**.

## 13. Schema validation, kiểm thử JAXB và SOAP interoperability

**JAXB unmarshal thành công không có nghĩa XML đã hợp lệ với XSD.** Mặc định, nhiều tình huống unmarshalling không tự áp dụng toàn bộ ràng buộc schema. Một lớp có `@XmlElement(required = true)` không bảo đảm setter sẽ từ chối `null`.

Với JAXB trực tiếp, có thể cấu hình `Unmarshaller` dùng `Schema`:

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.Unmarshaller;
import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import java.nio.file.Path;

public class JAXBValidationExample {
    public static Object read(Path schemaPath, Path xmlPath) throws Exception {
        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");

        // Minh họa schema độc lập không có xs:include/xs:import
        // cần truy cập tài nguyên bên ngoài.
        Schema schema = factory.newSchema(schemaPath.toFile());
        JAXBContext context = JAXBContext.newInstance(
                "org.example.orders.v1");
        Unmarshaller unmarshaller = context.createUnmarshaller();
        unmarshaller.setSchema(schema);

        // Khi dùng input không tin cậy, parse với SAX/StAX/DOM
        // được cấu hình chống XXE, và giới hạn kích thước payload.
        return unmarshaller.unmarshal(xmlPath.toFile());
    }
}
~~~

Đây là ví dụ **khái niệm**, dùng XML file trong môi trường được kiểm soát, không phải parser production cho payload không tin cậy. Với schema có include/import, phải dùng resolver/catalog hoặc cấu hình quyền truy cập phù hợp để nạp dependency đáng tin cậy, thay vì mở mọi URL bên ngoài. Với input untrusted, cần bảo vệ parser thực sự đọc XML (DOCTYPE, external entities, DTD), giới hạn kích thước và chi phí xử lý. Cũng cần cấu hình `Marshaller` hoặc schema-validating interceptor khi muốn kiểm tra XML **đi ra**.

### Ma trận kiểm thử nên có

| Nhóm | Ví dụ | Mục tiêu |
| --- | --- | --- |
| **Codegen** | XJC chạy từ XSD root trong clean build | Sinh đầy đủ class, `ObjectFactory`, metadata package |
| **Marshal** | Java request `ORD-1024` → XML | Root QName, namespace, element order khớp XSD |
| **Unmarshal** | XML mẫu → `GetOrderRequest` | Các giá trị được đọc đúng |
| **Round trip** | Object → XML → Object | Dữ liệu không bị mất; không dùng round trip thay schema validation |
| **Sai schema** | Thiếu `orderId`, `status=UNKNOWN`, namespace v2 | Validator từ chối |
| **Optional/nil** | Vắng `note`, `note/`, `xsi:nil="true"` | Java binding phân biệt đúng nếu hợp đồng yêu cầu |
| **Multi-namespace** | Payload tham chiếu type từ XSD import | QName và generated package đúng |
| **SOAP endpoint** | `MockWebServiceClient` gửi SOAP Body | Dispatch đúng `@PayloadRoot`, response/Fault đúng |
| **SOAP client** | `MockWebServiceServer` kiểm tra request | Marshal đúng, SOAPAction khi cần, đọc phản hồi/Fault |
| **Interop** | Client Java và .NET/ESB từ WSDL đã phát hành | Các bên hiểu giống nhau về XML và SOAP binding |
| **Security** | SOAP Body ký, chứng chỉ sai, header bị thay | WS-Security interceptor áp dụng đúng; JAXB không phá chữ ký |

Không nên chỉ so sánh XML byte-by-byte vì prefix và thứ tự thuộc tính không luôn quyết định tính tương đương XML. Hãy đối chiếu **QName, giá trị, schema validation và behavior thực tế**. Riêng chữ ký SOAP cần dùng chuẩn canonicalization và chính sách WS-Security tương ứng; không đơn giản hóa thành phép so sánh chuỗi.

## 14. Hiệu năng và an toàn khi dùng JAXB generated classes

- **`JAXBContext`** thường tốn chi phí tạo và có thể tái sử dụng có kiểm soát. `Marshaller` và `Unmarshaller` thông thường **không thread-safe**; tạo instance riêng cho luồng/giao dịch hoặc dùng cơ chế quản lý phù hợp.
- **Generated classes thường mutable**. Không giữ một request object làm singleton rồi tái sử dụng giữa nhiều SOAP request.
- **Payload XML lớn** có thể gây chi phí bộ nhớ khi tạo object graph; cần giới hạn kích thước, kiểm tra attachment/MTOM và bảo vệ parser.
- **Dữ liệu từ XML bên ngoài không đáng tin cậy**. XSD validation, schema/DTD resolver an toàn và kiểm tra nghiệp vụ là những lớp kiểm soát khác nhau.
- **WS-Security** được xử lý bằng SOAP security stack/interceptor (ví dụ giải pháp WSS4J khi áp dụng), không phải bằng annotation JAXB. Nếu cần ký/mã hóa, hoàn thiện nội dung SOAP message trước các bước bảo mật phù hợp.
- **Chứng chỉ TLS/mTLS** và chứng chỉ ký SOAP message là cấu hình vận hành/bảo mật riêng; generated Java model không chứa private key hay thay thế truststore.

Khi nâng cấp JAXB runtime, plugin hoặc bộ công cụ XJC, hãy kiểm thử từ schema tới SOAP message thực tế. Tương thích ở mức chữ ký method Java **không đủ** để khẳng định XML contract và WS-Security vẫn tương thích.

## 15. Lỗi thường gặp và hướng chẩn đoán

| Hiện tượng | Nguyên nhân khả dĩ | Bước kiểm tra đầu tiên |
| --- | --- | --- |
| `package jakarta.xml.bind.annotation does not exist` | Thiếu Jakarta JAXB API khi compile | Dependency management / API runtime |
| `package javax.xml.bind.annotation does not exist` | Generated classes thuộc hệ Javax nhưng app dùng Jakarta | Phiên bản XJC và stack Spring/JAXB đang dùng |
| `JAXBException: class ... is not known to this context` | Context path/packages/classes chưa bao gồm generated type | `ObjectFactory`, `@XmlRegistry`, JAXBContext và cấu hình marshaller |
| `unable to marshal ... missing @XmlRootElement` | Class không định nghĩa global element root trực tiếp | Dùng `ObjectFactory`/`JAXBElement` đúng QName |
| `Cannot find the declaration of element ...` | XML root sai namespace hoặc schema không nạp dependency | QName runtime, XSD root và import/include |
| `Two declarations cause a collision in the ObjectFactory class` | Mô hình XSD dẫn đến trùng tên factory/package | Binding customizations, schema namespace |
| Generated code vẫn có lớp đã bị xóa khỏi XSD | Đầu ra sinh mã không được dọn | Clean generated directory rồi codegen |
| Mã build được nhưng `@PayloadRoot` không dispatch | Namespace/localPart của payload khác endpoint mapping | SOAP Body QName so với XSD và `@PayloadRoot` |
| JAXB marshal ra `xsi:nil` khác kỳ vọng | Optional/nillable hoặc JAXBElement được xử lý sai | XSD declaration, binding code và test XML |
| Client đối tác từ chối response enum mới | XSD thay enum, client cũ chưa tương thích | Contract version và kiểm thử interop |
| Generate thành công local nhưng CI báo thiếu XSD | Phụ thuộc vào absolute path, catalog hoặc file chưa commit | Schema graph và nguồn artifact đầu vào |

### Những sai lầm dễ tránh

1. **Sửa generated Java rồi commit:** lần sinh kế tiếp sẽ ghi đè; cần sửa hợp đồng hoặc external binding và tái sinh.
2. **Sinh Java theo XSD mới nhưng phát hành WSDL cũ:** client sinh từ WSDL có thể không khớp payload server phát thực tế.
3. **Ép mọi namespace vào cùng package:** dễ trùng tên và tạo mapping khó hiểu.
4. **Trộn `javax` và `jakarta`:** annotation/serializer không thuộc cùng ngăn xếp.
5. **Cho rằng `@XmlElement(required=true)` là validation đầy đủ:** phải kiểm tra theo XSD và quy tắc nghiệp vụ.
6. **Dùng XJC như một SOAP client:** XJC sinh model XML; SOAP transport và binding cần client stack phù hợp.
7. **Cho rằng test getter/setter đủ bảo đảm tương thích:** cần kiểm tra XML trên dây, SOAP binding, Fault và security.

## 16. Bài thực hành tự kiểm tra

Với `orders.xsd` ở phần 2, hãy thực hiện các bước sau trên một dự án Maven nhỏ đã chọn đúng thế hệ JAXB:

1. Cấu hình XJC để đọc `orders.xsd` và sinh Java vào `target/generated-sources/jaxb`; xác định những file đã được tạo và phân biệt `ObjectFactory` với `package-info.java`.
2. Kiểm tra generated class cho `GetOrderRequest`: QName root đến từ đâu? Khi nào cần `JAXBElement<GetOrderRequest>`?
3. Viết một đoạn marshal request và unmarshal response; kiểm tra `orderId` và `status` giữ nguyên giá trị.
4. Đổi enum `OrderStatusType` bằng cách thêm `REFUNDED` vào XSD, chạy codegen sạch và so sánh generated diff. Giải thích vì sao client cũ có thể bị ảnh hưởng dù Java server đã compile.
5. Thêm phần tử optional `note` và thử ba dạng absent, empty, nil (nếu cấu hình XSD cho phép). Xác minh Java binding và XML marshal.
6. Chuyển namespace `urn:example:orders:v1` sang `urn:example:orders:v2` trong bản thử riêng; kiểm tra `package-info`, root QName, endpoint `@PayloadRoot` và WSDL phải thay đổi những gì.
7. Cố tình sinh mã Javax rồi dùng trong ứng dụng Jakarta; ghi lại lỗi và cách sửa bằng cách chọn đúng toolchain thay vì sửa annotations thủ công.
8. Thêm một `xs:import` sang namespace tài chính; bảo đảm XJC resolve được dependency trong clean CI và không sinh class trùng tên.
9. Kiểm thử request qua Spring-WS endpoint và SOAP client, gồm SOAP Fault, WS-Security khi hợp đồng yêu cầu và XML schema validation.

## 17. Quy tắc áp dụng vào dự án Spring Web Services

Một dự án SOAP contract-first có thể vận hành lâu dài nếu giữ được chuỗi trách nhiệm:

~~~mermaid
flowchart TD
    A["XSD/WSDL versioned<br/>+ optional binding files"] --> B["XJC cố định phiên bản<br/>generated Java vào build output"]
    B --> C["JAXB model<br/>đúng QName và type"]
    C --> D["Application adapter / service"]
    D --> E["Spring-WS endpoint / client"]
    E --> F["SOAP XML kiểm thử contract<br/>Fault + security + interop"]
    F -->|"Phát hiện sai lệch"| A
~~~

**XSD/WSDL là hợp đồng công bố, còn Java do XJC sinh là sản phẩm của quy trình build.** Hãy version hóa nguồn sinh và cấu hình, tái sinh mã khi hợp đồng thay đổi, kiểm thử XML thực tế và giữ mã nghiệp vụ bên ngoài lớp generated. Đó là cách dùng JAXB hiệu quả để triển khai dịch vụ **SPRING_WEB_SERVICES** có SOAP endpoint/client ổn định, xử lý đúng SOAP Fault, interceptor và chính sách WS-Security/chứng chỉ, đồng thời giảm rủi ro lệch hợp đồng giữa các hệ thống doanh nghiệp.
