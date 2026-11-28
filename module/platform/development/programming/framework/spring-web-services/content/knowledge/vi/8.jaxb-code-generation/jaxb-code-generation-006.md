# ObjectFactory, JAXBElement và phần tử toàn cục

## 1. Vì sao sinh Java từ XSD lại xuất hiện ObjectFactory và JAXBElement?

Khi phát triển SOAP theo hướng **contract-first** với Spring Web Services (Spring-WS), ta thường thiết kế XSD/WSDL trước rồi dùng JAXB/XJC sinh các lớp Java. Ngoài những lớp quen thuộc như `GetOrderRequestType` hoặc `OrderSummaryType`, mã sinh ra thường có `ObjectFactory`, `package-info.java` và các phương thức trả về `JAXBElement<T>`.

Người mới dễ nghĩ rằng `JAXBElement<T>` chỉ là một wrapper thừa, có thể bỏ đi để truyền trực tiếp `T`. Trong nhiều trường hợp, làm vậy sẽ khiến marshaller không biết **tên element gốc**, hoặc làm mất khả năng phân biệt những element **có cùng Java type nhưng khác QName**.

Hãy tách hai khái niệm ngay từ đầu:

- **XML Schema type** mô tả dữ liệu có cấu trúc và kiểu gì. JAXB thường ánh xạ named complex type thành một **Java class**.
- **XML element declaration** mô tả phần tử tên gì, thuộc namespace nào, sử dụng type nào và có các đặc điểm như nillable, default hay phạm vi khai báo. JAXB có thể biểu diễn một element declaration bằng `@XmlRootElement` hoặc `@XmlElementDecl` cùng `JAXBElement<T>`.

Một object Java có thể chứa đủ field của request nhưng vẫn **thiếu thông tin để marshal thành phần tử XML chính xác**. Phần tử gốc bên trong SOAP Body cần một QName, không chỉ một kiểu Java.

Bài thuộc chương **Sinh mã JAXB** của module **SPRING_WEB_SERVICES**. Bạn sẽ học cách đọc kết quả XJC, hiểu nhiệm vụ của `ObjectFactory`, tạo và nhận `JAXBElement`, dùng binding trong `@Endpoint` và SOAP client, đồng thời kiểm thử hợp đồng XSD/WSDL để bảo đảm tích hợp ổn định.

Sau bài học, bạn có thể:

1. Phân biệt **global element**, **named complex type** và **QName**.
2. Giải thích vì sao một số lớp sinh ra có `@XmlRootElement` còn một số cần `ObjectFactory.create...(...)`.
3. Sử dụng `JAXBElement<T>` đúng với `@XmlElementDecl`, hiểu `name`, `declaredType`, `scope`, `value` và `nil`.
4. Marshal/unmarshal một SOAP payload và kiểm tra QName trước khi xử lý nghiệp vụ.
5. Ánh xạ binding sinh ra sang domain model mà không sửa trực tiếp generated code.
6. Chẩn đoán những lỗi như “missing `@XmlRootElement`”, sai namespace và sai `JAXBContext`.
7. Kiểm thử cả JAXB binding lẫn endpoint/client Spring-WS theo cách **contract-first**.

## 2. Khác biệt giữa global element và named complex type

### 2.1. Global element có danh tính XML riêng

Xét XSD `orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

    <xs:complexType name="GetOrderRequestType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:complexType name="GetOrderResponseType">
        <xs:sequence>
            <xs:element name="orderId" type="xs:string"/>
            <xs:element name="status" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="GetOrderRequest"
                type="ord:GetOrderRequestType"/>

    <xs:element name="CheckOrderRequest"
                type="ord:GetOrderRequestType"/>

    <xs:element name="GetOrderResponse"
                type="ord:GetOrderResponseType"/>
</xs:schema>
~~~

Schema này khai báo **hai phần tử toàn cục dùng cùng một named complex type**:

~~~text
Global element QName: {urn:example:orders:v1}GetOrderRequest
Global element QName: {urn:example:orders:v1}CheckOrderRequest

Named type QName:      {urn:example:orders:v1}GetOrderRequestType
~~~

Hai global elements có cấu trúc giống nhau nhưng **không phải cùng một tên XML**.

Ví dụ thứ nhất:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Ví dụ thứ hai:

~~~xml
<ord:CheckOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:CheckOrderRequest>
~~~

Cả hai có thể chứa cùng một object Java với field `orderId`. Nhưng một SOAP operation chờ `GetOrderRequest` sẽ không tự coi `CheckOrderRequest` là cùng root element. **Kiểu dữ liệu giống nhau không làm QName giống nhau.**

### 2.2. Thế nào là global element?

Trong XSD, global element declaration là `xs:element` được khai báo **trực tiếp bên dưới `xs:schema`**:

~~~xml
<xs:schema ...>
    <xs:element name="GetOrderRequest"
                type="ord:GetOrderRequestType"/>
</xs:schema>
~~~

Một global element có QName thuộc `targetNamespace` của schema. Nó có thể được WSDL tham chiếu để mô tả root element trong SOAP Body.

Ngược lại, `orderId` ở bên trong `xs:sequence` là một **local element declaration**:

~~~xml
<xs:complexType name="GetOrderRequestType">
    <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
    </xs:sequence>
</xs:complexType>
~~~

Với `elementFormDefault="qualified"`, local element `orderId` cũng có namespace trong XML instance, nhưng nó không tự trở thành một global element để các message WSDL tham chiếu độc lập.

### 2.3. Type QName và element QName phục vụ các vai trò khác nhau

| Đối tượng | QName ví dụ | Vai trò |
|---|---|---|
| Named XSD type | `{urn:example:orders:v1}GetOrderRequestType` | Cấu trúc dữ liệu gồm `orderId` |
| Global request element | `{urn:example:orders:v1}GetOrderRequest` | Phần tử gốc của request |
| Global element khác dùng cùng type | `{urn:example:orders:v1}CheckOrderRequest` | Phần tử gốc mang ý nghĩa khác |
| Global response element | `{urn:example:orders:v1}GetOrderResponse` | Phần tử gốc của response |

Phần **namespace URI + local name** quyết định QName. Prefix `ord`, `o` hay default namespace chỉ là cách viết XML; prefix khác nhau nhưng trỏ cùng URI sẽ tạo cùng QName.

## 3. Từ XSD đến Java: nhìn vào kết quả XJC

XJC là công cụ sinh JAXB binding từ XML Schema. Công cụ và cách gọi phụ thuộc phiên bản Jakarta/Javax, Maven/Gradle và môi trường build, nhưng nguyên lý ánh xạ giữ nguyên.

Một lệnh XJC mang tính minh họa:

~~~bash
# Giả định đã cài XJC phù hợp và thư mục đầu ra tồn tại
xjc -d generated-sources \
    -p com.example.integration.orders.v1 \
    src/main/resources/xsd/orders-v1.xsd
~~~

Từ XSD ví dụ, một bộ binding có thể gồm:

~~~text
com/example/integration/orders/v1/
├── GetOrderRequestType.java
├── GetOrderResponseType.java
├── ObjectFactory.java
└── package-info.java
~~~

**Đây là dạng cấu trúc minh họa**, không phải cam kết chính xác từng file/method của mọi phiên bản XJC. Kết quả có thể khác khi dùng custom binding, external binding file hoặc XSD có anonymous complex type.

Trong dự án Spring-WS hiện đại dùng Jakarta JAXB, import thường là `jakarta.xml.bind.*`. Dự án cũ dùng Java EE/JAXB có thể dùng `javax.xml.bind.*`. Cần chọn đúng phiên bản API/runtime và XJC; không tự trộn hai hệ package.

### 3.1. Lớp Java biểu diễn named complex type

Một kết quả sinh mã điển hình:

~~~java
package com.example.integration.orders.v1;

import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlType;

@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(
    name = "GetOrderRequestType",
    propOrder = {"orderId"}
)
public class GetOrderRequestType {

    @XmlElement(required = true)
    protected String orderId;

    public String getOrderId() {
        return orderId;
    }

    public void setOrderId(String value) {
        this.orderId = value;
    }
}
~~~

Lớp này biểu diễn dữ liệu của **type**. Trong tình huống đang xét, XJC có thể **không gắn `@XmlRootElement`** vào `GetOrderRequestType`, bởi cùng một type được sử dụng bởi cả `GetOrderRequest` và `CheckOrderRequest`. Không có một tên root duy nhất để gắn cứng vào class.

Nếu viết:

~~~java
GetOrderRequestType request = new GetOrderRequestType();
request.setOrderId("ORD-1001");
~~~

object đã có dữ liệu, nhưng chưa chỉ ra người gọi muốn root XML `GetOrderRequest` hay `CheckOrderRequest`. Đây là lúc **ObjectFactory và JAXBElement** trở nên cần thiết.

### 3.2. package-info.java nắm thông tin package-level XML

XJC thường sinh `package-info.java` có metadata namespace:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:orders:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package com.example.integration.orders.v1;
~~~

Namespace XML không cần trùng với tên package Java. Package là cách tổ chức code; QName là giao diện tích hợp công khai. Thay đổi package binding có thể thực hiện bằng cấu hình XJC nếu vẫn bảo toàn đúng namespace và các annotation liên quan.

## 4. ObjectFactory là gì?

`ObjectFactory` do XJC sinh ra là một **registry/factory thuộc JAXB binding package**, thường có annotation `@XmlRegistry`. Nó có thể cung cấp hai nhóm phương thức:

1. Tạo instance của các lớp Java tương ứng với XSD complex type.
2. Tạo `JAXBElement<T>` chứa QName và metadata của một XML element declaration.

Ví dụ rút gọn:

~~~java
package com.example.integration.orders.v1;

import javax.xml.namespace.QName;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.annotation.XmlElementDecl;
import jakarta.xml.bind.annotation.XmlRegistry;

@XmlRegistry
public class ObjectFactory {

    private static final QName GET_ORDER_REQUEST_QNAME =
        new QName(
            "urn:example:orders:v1",
            "GetOrderRequest"
        );

    private static final QName CHECK_ORDER_REQUEST_QNAME =
        new QName(
            "urn:example:orders:v1",
            "CheckOrderRequest"
        );

    private static final QName GET_ORDER_RESPONSE_QNAME =
        new QName(
            "urn:example:orders:v1",
            "GetOrderResponse"
        );

    public ObjectFactory() {
    }

    public GetOrderRequestType createGetOrderRequestType() {
        return new GetOrderRequestType();
    }

    public GetOrderResponseType createGetOrderResponseType() {
        return new GetOrderResponseType();
    }

    @XmlElementDecl(
        namespace = "urn:example:orders:v1",
        name = "GetOrderRequest"
    )
    public JAXBElement<GetOrderRequestType> createGetOrderRequest(
            GetOrderRequestType value) {

        return new JAXBElement<>(
            GET_ORDER_REQUEST_QNAME,
            GetOrderRequestType.class,
            null,
            value
        );
    }

    @XmlElementDecl(
        namespace = "urn:example:orders:v1",
        name = "CheckOrderRequest"
    )
    public JAXBElement<GetOrderRequestType> createCheckOrderRequest(
            GetOrderRequestType value) {

        return new JAXBElement<>(
            CHECK_ORDER_REQUEST_QNAME,
            GetOrderRequestType.class,
            null,
            value
        );
    }

    @XmlElementDecl(
        namespace = "urn:example:orders:v1",
        name = "GetOrderResponse"
    )
    public JAXBElement<GetOrderResponseType> createGetOrderResponse(
            GetOrderResponseType value) {

        return new JAXBElement<>(
            GET_ORDER_RESPONSE_QNAME,
            GetOrderResponseType.class,
            null,
            value
        );
    }
}
~~~

Tên constant và chi tiết constructor có thể khác trong file thật do XJC sinh. Điều cần hiểu là **cặp phương thức**:

~~~java
createGetOrderRequestType()          // tạo object chứa dữ liệu
createGetOrderRequest(requestType)    // tạo XML element mang QName đúng
~~~

Đừng nhầm `ObjectFactory` JAXB với `org.springframework.beans.factory.ObjectFactory`, là interface factory/provider cho Spring bean. Hai loại cùng tên nhưng thuộc các hệ API và mục đích hoàn toàn khác nhau.

### 4.1. @XmlRegistry giúp JAXB phát hiện những khai báo nào?

`@XmlRegistry` đánh dấu class chứa các phương thức factory phục vụ JAXB. Còn `@XmlElementDecl` là metadata liên kết **QName của element declaration** với phương thức tạo `JAXBElement`.

Khi tạo JAXBContext theo package chứa `ObjectFactory`, runtime có thể dùng các khai báo này để biết:

- Element toàn cục `{urn:example:orders:v1}GetOrderRequest` tồn tại.
- Giá trị bên trong thuộc declared type `GetOrderRequestType`.
- Element `CheckOrderRequest` tuy có cùng declared type nhưng là một khai báo khác.
- Những scoped element declarations nếu có sẽ chỉ có hiệu lực trong phạm vi kiểu tương ứng.

Đó là lý do khi cấu hình JAXBContext hoặc Spring `Jaxb2Marshaller`, chọn đúng context path của binding package thường quan trọng hơn chỉ đưa một lớp dữ liệu lẻ vào.

### 4.2. Vì sao không sửa trực tiếp ObjectFactory được sinh ra?

Các file generated có thể được tạo lại mỗi lần XSD hoặc cấu hình XJC thay đổi. Nếu chỉnh tay `@XmlElementDecl` hoặc QName trong đó, lần build tiếp theo có thể ghi đè sửa đổi hoặc khiến file Java và XSD không còn nhất quán.

Thay vào đó:

- Chỉnh **XSD** nếu thay đổi contract là có chủ đích.
- Chỉnh **binding customization** và cấu hình XJC nếu cần thay đổi cách sinh Java.
- Viết **adapter/mapper riêng** để chuyển giữa JAXB binding và domain model.
- Giữ generated code trong ranh giới tích hợp, tránh đưa nó thành domain API ở mọi tầng.

## 5. JAXBElement<T> biểu diễn những thông tin gì?

`JAXBElement<T>` là kiểu Java biểu diễn một XML element declaration và giá trị của nó. Không nên coi nó là “một hộp chứa T” đơn thuần.

Một `JAXBElement<GetOrderRequestType>` chứa các thông tin chính:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| `getName()` | `{urn:example:orders:v1}GetOrderRequest` | QName của element |
| `getDeclaredType()` | `GetOrderRequestType.class` | Kiểu khai báo của element |
| `getScope()` | Global scope | Phạm vi khai báo element |
| `getValue()` | Object `GetOrderRequestType` | Dữ liệu của element |
| `isNil()` | true/false | Trạng thái nil biểu diễn bởi JAXB |

Ví dụ:

~~~java
ObjectFactory factory = new ObjectFactory();

GetOrderRequestType data = factory.createGetOrderRequestType();
data.setOrderId("ORD-1001");

JAXBElement<GetOrderRequestType> root =
    factory.createGetOrderRequest(data);

System.out.println(root.getName());
// {urn:example:orders:v1}GetOrderRequest

System.out.println(root.getDeclaredType());
// class com.example.integration.orders.v1.GetOrderRequestType

System.out.println(root.getValue().getOrderId());
// ORD-1001
~~~

Nếu dùng cùng object `data` nhưng gọi phương thức factory khác:

~~~java
JAXBElement<GetOrderRequestType> other =
    factory.createCheckOrderRequest(data);
~~~

thì:

~~~java
root.getValue() == other.getValue()  // true
root.getName().equals(other.getName()) // false
~~~

**Cùng một Java object có thể xuất hiện dưới hai root element khác nhau**, nhờ wrapper chứa QName riêng.

### 5.1. QName là danh tính của element

QName có hai phần quyết định việc so khớp:

~~~java
QName requestName =
    new QName("urn:example:orders:v1", "GetOrderRequest");
~~~

Prefix là thông tin trình bày có thể được XML writer chọn. Hai XML sau có cùng element QName:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<x:GetOrderRequest xmlns:x="urn:example:orders:v1"/>
~~~

JAXB thường có thể thay prefix trong quá trình marshal mà vẫn tạo XML đúng contract. Trong kiểm thử, so QName và schema thay vì so chuỗi prefix.

### 5.2. Declared type khác runtime type

`getDeclaredType()` cho biết kiểu được khai báo cho element. Trong trường hợp đa hình được hỗ trợ, runtime value có thể là một kiểu phái sinh hợp lệ. XML có thể cần `xsi:type` hoặc cơ chế XSD tương ứng để diễn đạt type cụ thể.

Do đó:

- QName trả lời “đây là element nào?”.
- Declared type trả lời “element được khai báo với type nào?”.
- Runtime value trả lời “đang có object dữ liệu nào?”.

Không dùng duy nhất `value.getClass()` để suy ra QName hoặc WSDL operation.

### 5.3. Scope: global và local element declaration

Một element có thể được khai báo toàn cục trong schema, hoặc được khai báo cục bộ trong một complex type. `@XmlElementDecl` có thể chỉ định `scope` đối với local element.

Ví dụ metadata minh họa:

~~~java
@XmlElementDecl(
    namespace = "urn:example:orders:v1",
    name = "deliveryNote",
    scope = UpdateOrderRequestType.class
)
public JAXBElement<String> createUpdateOrderRequestTypeDeliveryNote(
        String value) {
    // Phương thức cụ thể do XJC sinh có thể khác.
    return new JAXBElement<>(
        DELIVERY_NOTE_QNAME,
        String.class,
        UpdateOrderRequestType.class,
        value
    );
}
~~~

Một scoped element `deliveryNote` không đồng nghĩa với global element có local name giống hệt. Scope giúp JAXB liên kết declaration ở đúng nơi khi parse hoặc serialize.

## 6. @XmlRootElement và @XmlElementDecl: hai cách biểu diễn XML root

### 6.1. Khi class có @XmlRootElement

Với một global element dùng **anonymous complex type**:

~~~xml
<xs:element name="PingRequest">
    <xs:complexType>
        <xs:sequence>
            <xs:element name="message" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:element>
~~~

XJC thường có thể sinh một class mang trực tiếp root metadata:

~~~java
@XmlRootElement(
    name = "PingRequest",
    namespace = "urn:example:orders:v1"
)
public class PingRequest {
    // Field, getter/setter và JAXB metadata.
}
~~~

Khi class đã có `@XmlRootElement` phù hợp, có thể marshal trực tiếp instance của nó:

~~~java
PingRequest ping = new PingRequest();
ping.setMessage("hello");

marshaller.marshal(ping, System.out);
~~~

### 6.2. Khi named complex type có nhiều global element sử dụng

Với XSD ở phần đầu:

~~~xml
<xs:complexType name="GetOrderRequestType">...</xs:complexType>

<xs:element name="GetOrderRequest"
            type="ord:GetOrderRequestType"/>

<xs:element name="CheckOrderRequest"
            type="ord:GetOrderRequestType"/>
~~~

không có một root name duy nhất cho `GetOrderRequestType`. XJC thường dùng `@XmlElementDecl` và `JAXBElement<GetOrderRequestType>` thay vì gắn một `@XmlRootElement` duy nhất vào class type.

Đây là kết quả hợp lý về mặt XML, không phải lỗi code generation.

| Tình huống | Cách binding thường gặp |
|---|---|
| Global element có anonymous complex type | Class mang `@XmlRootElement` |
| Global element dùng named complex type | Named type class + `ObjectFactory`/`JAXBElement` |
| Nhiều global elements dùng một named type | Cần phân biệt QName; `JAXBElement` là lựa chọn tự nhiên |
| Local element có scope/nil/element reference phức tạp | Có thể dùng `@XmlElementRef` và `JAXBElement` |
| Custom JAXB binding | Kết quả có thể thay đổi theo customization và generator |

**Cẩn thận:** Đây là xu hướng thông dụng của XJC, không phải quy tắc “mọi global element luôn sinh JAXBElement” hoặc “mọi anonymous type luôn có @XmlRootElement”. Hãy đọc code sinh ra thay vì đoán.

### 6.3. Có nên thêm @XmlRootElement thủ công cho dễ marshal?

Không nên tự chỉnh generated class chỉ để né việc dùng `ObjectFactory`. Trong trường hợp hai global elements dùng chung type, thêm root name cứng vào class có thể khiến code luôn marshal cùng một tên, làm mất ý nghĩa của element declaration khác.

Cách đúng thường là tạo đúng wrapper qua factory, rồi dùng marshaller nhận `JAXBElement`.

## 7. Thực hành marshal thành XML có đúng root element

Giả sử package binding là `com.example.integration.orders.v1` và có `ObjectFactory` như phần trước.

~~~java
import java.io.StringWriter;

import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.Marshaller;

import com.example.integration.orders.v1.GetOrderRequestType;
import com.example.integration.orders.v1.ObjectFactory;

public class MarshalExample {

    public static void main(String[] args) throws Exception {
        ObjectFactory factory = new ObjectFactory();

        GetOrderRequestType request =
            factory.createGetOrderRequestType();
        request.setOrderId("ORD-1001");

        JAXBElement<GetOrderRequestType> root =
            factory.createGetOrderRequest(request);

        JAXBContext context = JAXBContext.newInstance(
            "com.example.integration.orders.v1"
        );

        Marshaller marshaller = context.createMarshaller();
        marshaller.setProperty(
            Marshaller.JAXB_FORMATTED_OUTPUT,
            Boolean.TRUE
        );

        StringWriter xml = new StringWriter();
        marshaller.marshal(root, xml);

        System.out.println(xml);
    }
}
~~~

Ví dụ output (prefix/format có thể thay đổi theo JAXB implementation):

~~~xml
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<ns2:GetOrderRequest xmlns:ns2="urn:example:orders:v1">
    <ns2:orderId>ORD-1001</ns2:orderId>
</ns2:GetOrderRequest>
~~~

Điều cần kiểm tra là:

~~~text
Root QName = {urn:example:orders:v1}GetOrderRequest
Child QName = {urn:example:orders:v1}orderId
Value      = ORD-1001
~~~

Không nên coi prefix `ns2` là lỗi: prefix không phải một phần của QName. Cũng không nên dùng exact string comparison để yêu cầu namespace declaration hoặc thứ tự thuộc tính giống từng byte nếu contract không quy định.

### 7.1. Nếu marshal trực tiếp GetOrderRequestType thì sao?

Ví dụ:

~~~java
GetOrderRequestType request = new GetOrderRequestType();
request.setOrderId("ORD-1001");

// Có thể phát sinh MarshalException nếu class không có root mapping:
marshaller.marshal(request, System.out);
~~~

Một lỗi thường gặp có thông điệp tương tự:

~~~text
unable to marshal type "...GetOrderRequestType"
as an element because it is missing an @XmlRootElement annotation
~~~

**Nguyên nhân:** `GetOrderRequestType` là một JAXB type class mà runtime không biết phải dùng root QName nào khi marshal trực tiếp.

**Cách khắc phục:** Tạo `JAXBElement` từ đúng phương thức factory:

~~~java
JAXBElement<GetOrderRequestType> root =
    new ObjectFactory().createGetOrderRequest(request);

marshaller.marshal(root, System.out);
~~~

Đừng giải quyết bằng cách tự ý sửa XSD hoặc bỏ qua namespace. Chỉ thay contract khi có thay đổi nghiệp vụ/hợp đồng được phê duyệt.

## 8. Unmarshal: phải nhận ra cả root QName lẫn value

Giả sử nhận XML:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:GetOrderRequest>
~~~

Có thể giải mã bằng JAXBContext của package:

~~~java
import java.io.StringReader;

import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBElement;
import jakarta.xml.bind.Unmarshaller;

import javax.xml.namespace.QName;
import javax.xml.transform.stream.StreamSource;

import com.example.integration.orders.v1.GetOrderRequestType;

public class UnmarshalExample {

    public static void main(String[] args) throws Exception {
        String xml =
            "<ord:GetOrderRequest " +
            "xmlns:ord=\"urn:example:orders:v1\">" +
            "<ord:orderId>ORD-1001</ord:orderId>" +
            "</ord:GetOrderRequest>";

        JAXBContext context = JAXBContext.newInstance(
            "com.example.integration.orders.v1"
        );

        Unmarshaller unmarshaller = context.createUnmarshaller();
        Object decoded = unmarshaller.unmarshal(
            new StreamSource(new StringReader(xml))
        );

        if (!(decoded instanceof JAXBElement<?> element)) {
            throw new IllegalArgumentException(
                "Kết quả không phải JAXBElement"
            );
        }

        QName expected = new QName(
            "urn:example:orders:v1",
            "GetOrderRequest"
        );

        if (!expected.equals(element.getName())) {
            throw new IllegalArgumentException(
                "Sai root QName: " + element.getName()
            );
        }

        Object value = element.getValue();
        if (!(value instanceof GetOrderRequestType request)) {
            throw new IllegalArgumentException(
                "Sai type cho GetOrderRequest"
            );
        }

        System.out.println(request.getOrderId());
    }
}
~~~

Đoạn mã dùng pattern matching for `instanceof` của Java hiện đại; có thể thay bằng cast thông thường nếu dự án dùng Java cũ.

Trong tình huống XSD ví dụ, với package context nhận diện `@XmlElementDecl`, kết quả thường là `JAXBElement<GetOrderRequestType>`. Nếu schema và binding thực tế dùng class có `@XmlRootElement`, `Unmarshaller.unmarshal(...)` có thể trả chính instance class. Do vậy, kiểm tra kết quả theo binding thực sự được sinh ra.

### 8.1. Vì sao cần kiểm tra QName?

Nếu SOAP Body gửi:

~~~xml
<ord:CheckOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1001</ord:orderId>
</ord:CheckOrderRequest>
~~~

JAXB có thể giải mã giá trị thành **cùng class `GetOrderRequestType`** nhưng wrapper mang `CheckOrderRequest`. Nếu nghiệp vụ chỉ cast `getValue()` rồi bỏ qua `getName()`, một operation có thể nhận nhầm thông điệp của operation khác.

Trong Spring-WS, `@PayloadRoot` thường xử lý bước định tuyến bằng QName. Tuy nhiên, khi tự viết SOAP client, XML adapter hoặc endpoint dùng raw JAXB/unmarshaller, vẫn nên xác nhận QName theo contract.

### 8.2. Unmarshal với declared type không tự xác thực root

JAXB còn hỗ trợ cách:

~~~java
JAXBElement<GetOrderRequestType> parsed =
    unmarshaller.unmarshal(
        new StreamSource(new StringReader(xml)),
        GetOrderRequestType.class
    );
~~~

Overload này hữu ích khi caller biết declared type nhưng XML root không có element declaration đã đăng ký. Kết quả trả về vẫn mang QName từ XML. Tuy nhiên, **chọn declared type không phải kiểm tra rằng root QName được công bố trong XSD**. Cần kiểm tra `parsed.getName()` và cấu hình schema validation nếu muốn từ chối XML sai hợp đồng.

## 9. JAXBElement và sự khác biệt giữa absent, nil, empty

Một lý do khác khiến JAXB sử dụng `JAXBElement` là cần biểu diễn những trạng thái XML mà một field Java đơn giản không giữ đủ thông tin.

Xét element:

~~~xml
<xs:element name="deliveryNote"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Trong một complex type, các trường hợp sau có thể khác nhau về ngữ nghĩa:

**Không xuất hiện:**

~~~xml
<!-- Không có deliveryNote trong request -->
~~~

**Xuất hiện với nil:**

~~~xml
<ord:deliveryNote
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

**Xuất hiện với chuỗi rỗng:**

~~~xml
<ord:deliveryNote xmlns:ord="urn:example:orders:v1"/>
~~~

**Xuất hiện với dữ liệu:**

~~~xml
<ord:deliveryNote xmlns:ord="urn:example:orders:v1">
    Giao hàng trong giờ hành chính
</ord:deliveryNote>
~~~

Tùy XSD và cách sinh binding, một property có thể là `JAXBElement<String>` với `@XmlElementRef`, cho phép phân biệt:

- **Property không có wrapper**: element không xuất hiện, theo binding hiện tại.
- **Có wrapper và `isNil()`**: element có trạng thái nil.
- **Có wrapper, không nil, value = `""`**: element hiện diện với chuỗi rỗng.
- **Có wrapper và value thường**: element có dữ liệu.

Nhưng `JAXBElement.isNil()` không được suy diễn chỉ từ giá trị Java `null` mà không xem cách unmarshal đã xử lý XML. Một `JAXBElement` có thể chứa value `null` hoặc được đánh dấu nil, trong khi một field `String` đơn giản có thể gộp absent và nil thành `null`. **Hãy xác nhận trạng thái trên file XML mẫu với đúng binding/runtime**.

Đây là yếu tố quan trọng khi triển khai update operation:

| Trạng thái XML | Ý nghĩa nghiệp vụ có thể quy định |
|---|---|
| Vắng mặt | Không thay đổi dữ liệu |
| `xsi:nil="true"` | Xóa dữ liệu |
| Element rỗng | Đặt chuỗi rỗng |
| Có text | Đặt giá trị mới |

XSD/JAXB không tự áp đặt quy ước nghiệp vụ này. Endpoint/mapper phải diễn giải nhất quán với tài liệu contract-first.

## 10. ObjectFactory trong Spring-WS endpoint

Spring-WS thường định tuyến message dựa trên QName của root payload. Với XSD ở phần đầu, một endpoint có thể dùng binding class và `JAXBElement` như sau:

~~~java
import jakarta.xml.bind.JAXBElement;

import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

import com.example.integration.orders.v1.GetOrderRequestType;
import com.example.integration.orders.v1.GetOrderResponseType;
import com.example.integration.orders.v1.ObjectFactory;

@Endpoint
public class GetOrderEndpoint {

    private static final String NS = "urn:example:orders:v1";

    private final OrderApplicationService orderService;
    private final ObjectFactory factory = new ObjectFactory();

    public GetOrderEndpoint(OrderApplicationService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public JAXBElement<GetOrderResponseType> getOrder(
            @RequestPayload
            JAXBElement<GetOrderRequestType> requestElement) {

        GetOrderRequestType request =
            requestElement.getValue();

        String status =
            orderService.findStatus(request.getOrderId());

        GetOrderResponseType response =
            factory.createGetOrderResponseType();

        response.setOrderId(request.getOrderId());
        response.setStatus(status);

        return factory.createGetOrderResponse(response);
    }
}
~~~

Ví dụ giả định ứng dụng đã cấu hình JAXB payload processors/marshaller tương thích và `OrderApplicationService` có phương thức `findStatus(String)`. Spring-WS có thể hỗ trợ `JAXBElement` qua các method argument/return value processors phù hợp; cấu hình thực tế phụ thuộc phiên bản framework và cách sử dụng JAXB. Nếu endpoint dùng `@XmlRootElement` class hoặc `@RequestPayload Source`, chữ ký sẽ khác.

Điều quan trọng:

1. `@PayloadRoot` định tuyến theo QName `{urn:example:orders:v1}GetOrderRequest`.
2. JAXB unmarshal request XML sang object hoặc JAXBElement theo binding.
3. Nghiệp vụ xử lý dữ liệu trong `GetOrderRequestType`.
4. `ObjectFactory.createGetOrderResponse(...)` gắn đúng root QName cho response.
5. Spring-WS marshal thành SOAP Body và đưa vào SOAP Envelope tương ứng phiên bản SOAP.

Nếu chỉ trả `GetOrderResponseType` nhưng class không có `@XmlRootElement` phù hợp, response có thể thất bại khi marshalling. Factory giúp tránh lỗi đó.

### 10.1. Vì sao không truyền nguyên JAXBElement sâu vào domain?

`JAXBElement` mang metadata của XML contract: QName, scope và nil. Domain service thường chỉ cần các khái niệm nghiệp vụ như `OrderId`, `OrderStatus` hoặc lệnh truy vấn đơn hàng.

Một cách tổ chức rõ ràng:

~~~text
SOAP XML (GetOrderRequest element)
                |
Spring-WS @PayloadRoot + JAXB
                |
JAXBElement<GetOrderRequestType>
                |
Endpoint/mapper
                |
Application service / domain
                |
GetOrderResponseType
                |
ObjectFactory.createGetOrderResponse(...)
                |
SOAP XML (GetOrderResponse element)
~~~

Giữ JAXB generated code ở tầng tích hợp giúp thay đổi nội bộ mà không ảnh hưởng đến QName hoặc WSDL đã công bố.

## 11. Dùng JAXBElement với Spring WebServiceTemplate

SOAP client Spring-WS thường dùng `WebServiceTemplate` cùng `Jaxb2Marshaller`.

Một bean JAXB marshaller:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class SoapClientBindingConfig {

    @Bean
    public Jaxb2Marshaller orderMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();

        marshaller.setContextPath(
            "com.example.integration.orders.v1"
        );

        return marshaller;
    }
}
~~~

Context path trỏ đến package có JAXB generated classes và `ObjectFactory`. Nếu dùng các package binding khác nhau, cấu hình context path/packages/classes cần phù hợp với toàn bộ namespace/type được sử dụng.

Một SOAP client minh họa:

~~~java
import jakarta.xml.bind.JAXBElement;

import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;
import org.springframework.ws.soap.client.core.SoapActionCallback;

import com.example.integration.orders.v1.GetOrderRequestType;
import com.example.integration.orders.v1.GetOrderResponseType;
import com.example.integration.orders.v1.ObjectFactory;

public class OrderSoapClient {

    private final WebServiceTemplate template;
    private final ObjectFactory factory = new ObjectFactory();

    public OrderSoapClient(Jaxb2Marshaller marshaller) {
        template = new WebServiceTemplate();
        template.setMarshaller(marshaller);
        template.setUnmarshaller(marshaller);
    }

    public String getStatus(String orderId) {
        GetOrderRequestType data =
            factory.createGetOrderRequestType();
        data.setOrderId(orderId);

        JAXBElement<GetOrderRequestType> request =
            factory.createGetOrderRequest(data);

        Object raw = template.marshalSendAndReceive(
            "https://api.example.test/ws",
            request,
            new SoapActionCallback(
                "urn:example:orders:actions:GetOrder"
            )
        );

        if (!(raw instanceof JAXBElement<?> root)) {
            throw new IllegalStateException(
                "Phản hồi không phải JAXBElement"
            );
        }

        if (!(root.getValue() instanceof GetOrderResponseType value)) {
            throw new IllegalStateException(
                "Kiểu phản hồi không đúng hợp đồng"
            );
        }

        return value.getStatus();
    }
}
~~~

Ví dụ dùng `SoapActionCallback` trong bối cảnh **SOAP 1.1** và giả định action URI, URL, message factory, TLS và JAXB marshaller đã được cấu hình nhất quán với WSDL. Với SOAP 1.2, media type và cơ chế action khác; không sao chép máy móc SOAPAction header kiểu 1.1. Client production nên kiểm tra cả **root QName** của response trước khi xử lý và có chính sách xử lý SOAP Fault, timeout và bảo mật.

### 11.1. Không tự tạo tên response dựa trên tên Java class

Nếu response class là `GetOrderResponseType` mà global element là `GetOrderResponse`, cách đúng là sử dụng factory:

~~~java
GetOrderResponseType response =
    factory.createGetOrderResponseType();

JAXBElement<GetOrderResponseType> root =
    factory.createGetOrderResponse(response);
~~~

Không nên suy ra tên root bằng cách bỏ hậu tố `Type` bằng chuỗi trong runtime. Trong một contract khác, element có thể tên khác class hoàn toàn hoặc có namespace khác.

## 12. ObjectFactory và WSDL: điều gì là nguồn sự thật?

Giả sử WSDL document/literal tham chiếu đến:

~~~xml
<wsdl:message name="GetOrderInput"
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:ord="urn:example:orders:v1">

    <wsdl:part
        name="parameters"
        element="ord:GetOrderRequest"/>
</wsdl:message>
~~~

Trong contract-first:

~~~mermaid
flowchart TD
    A["XSD global element: GetOrderRequest"] --> B["WSDL message part: ord:GetOrderRequest"]
    A --> C["XJC: ObjectFactory @XmlElementDecl"]
    D["XSD named type: GetOrderRequestType"] --> E["XJC: GetOrderRequestType.java"]
    C --> F["JAXBElement<GetOrderRequestType>"]
    E --> F
    B --> G["Spring-WS SOAP Body QName"]
    F --> G
~~~

WSDL và XSD quyết định **element nào thuộc contract**. XJC sinh Java để phục vụ contract đó. `ObjectFactory` không phải nơi tự nghĩ ra SOAP operation mới hoặc đổi namespace cho thuận tiện.

Nếu đổi global element `GetOrderRequest` thành `FindOrderRequest`, XJC có thể sinh phương thức factory mới và WSDL cũng có thể thay message/operation. Đó là **thay đổi hợp đồng**, có thể phá vỡ generated client cũ. Nếu chỉ đổi package hoặc class Java ở phía server nhưng giữ QName, schema và hành vi SOAP, có thể giữ tương thích thông qua binding/mapping.

## 13. Các lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| MarshalException: missing `@XmlRootElement` | Đang marshal named type instance thay vì XML root | Dùng phương thức `ObjectFactory.create...(...)` để tạo đúng `JAXBElement` |
| Unmarshal báo “unexpected element” | Root QName không khớp khai báo JAXBContext/XSD | Đối chiếu URI namespace và local name; kiểm tra ObjectFactory/XmlElementDecl |
| Cùng type nhưng request tới sai operation | Bỏ qua `JAXBElement.getName()` | Kiểm tra QName hoặc dùng Spring-WS `@PayloadRoot` chính xác |
| JAXBContext không biết global element | Chỉ đăng ký một type class, bỏ package/ObjectFactory declaration | Dùng context path hoặc cấu hình binding đăng ký đầy đủ |
| Prefix XML khác mẫu nên test thất bại | So raw string thay vì QName | So QName và schema validation |
| `JAXBElement` chứa nil nhưng mapper coi như chuỗi rỗng | Không phân biệt nil/empty/absent | Kiểm thử `isNil()`, presence và value theo binding |
| Response được tạo nhưng SOAP Body rỗng/sai root | Response không được marshal với element QName đúng | Trả object có `@XmlRootElement` phù hợp hoặc `JAXBElement` từ factory |
| Đổi XSD nhưng generated classes cũ | XJC chưa chạy lại hoặc cache build | Đồng bộ schema và binding generation; kiểm tra artifact dùng đúng version |
| Jakarta JAXB runtime không nhận `javax` annotations | Trộn API/runtime hai thế hệ | Dùng dependencies/XJC tương thích với stack Spring |
| Client cũ không đọc được XML mới | Đổi global element QName hoặc type/namespace | Version contract và kiểm thử từ WSDL đã phát hành |

### 13.1. “Unexpected element” không nhất thiết do dữ liệu sai

Giả sử client có khai báo:

~~~text
Expected: {urn:example:orders:v1}GetOrderResponse
Actual:   {urn:example:orders:v2}GetOrderResponse
~~~

Hai local names giống nhau nhưng namespace khác. JAXB có lý do để từ chối; code generated từ XSD v1 không tự tương thích với QName v2. Không nên khắc phục bằng cách bỏ kiểm tra namespace; cần đối chiếu phiên bản WSDL/XSD và kế hoạch migration.

### 13.2. Đừng bắt mọi exception từ JAXB và trả HTTP 200

Trong dịch vụ SOAP, payload không hợp schema hoặc không thể unmarshal nên được xử lý theo cơ chế SOAP Fault thích hợp và contract của dịch vụ. Trả một XML thành công giả có thể khiến client không nhận ra lỗi.

Việc `ObjectFactory` tạo được Java object không chứng minh object đã hợp XSD: field `orderId` có thể vẫn null. Cần schema validation khi nhận/gửi thông điệp và kiểm tra nghiệp vụ riêng.

## 14. Kiểm thử contract-first cho ObjectFactory/JAXBElement

Các ca kiểm thử có giá trị nhất là những ca xác nhận **QName** và **ngữ nghĩa của XML**, không chỉ field Java.

### 14.1. Kiểm thử hai global elements dùng cùng type

Với `GetOrderRequestType`, tạo hai wrapper:

~~~java
ObjectFactory f = new ObjectFactory();

GetOrderRequestType value = f.createGetOrderRequestType();
value.setOrderId("ORD-1001");

JAXBElement<GetOrderRequestType> a = f.createGetOrderRequest(value);
JAXBElement<GetOrderRequestType> b = f.createCheckOrderRequest(value);
~~~

Assert:

~~~java
assert !a.getName().equals(b.getName());
assert a.getValue() == b.getValue();
assert a.getDeclaredType().equals(b.getDeclaredType());
~~~

Test này chứng minh type/value và element QName là những khái niệm khác nhau.

### 14.2. Kiểm thử marshal/unmarshal round-trip

Một test tích hợp đơn giản:

1. Tạo `GetOrderRequestType` và wrap bằng `createGetOrderRequest`.
2. Marshal thành XML.
3. Parse XML theo namespace-aware XML parser/schema validator.
4. Assert root QName là `{urn:example:orders:v1}GetOrderRequest`.
5. Unmarshal và assert `JAXBElement.getName()`, `getDeclaredType()`, `getValue().getOrderId()`.
6. Dùng wrapper `createCheckOrderRequest` và xác nhận QName root đã đổi.

Không bắt buộc hai XML round-trip phải giống nhau từng byte: prefix namespace, whitespace và cách trình bày có thể thay đổi hợp lệ.

### 14.3. Kiểm thử trường hợp absent/nil/empty

Nếu một property trong schema có `minOccurs="0" nillable="true"`, tạo ba payload:

~~~xml
<!-- A: Không có deliveryNote -->
~~~

~~~xml
<ord:deliveryNote
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

~~~xml
<ord:deliveryNote xmlns:ord="urn:example:orders:v1"/>
~~~

Kiểm tra output của XJC/JAXB có phân biệt những trường hợp mà nghiệp vụ cần hay không. Nếu binding chỉ còn một `String` nullable, cần điều chỉnh cách binding/mapper hoặc kiểm tra XML ban đầu để không làm mất ngữ nghĩa.

### 14.4. Gắn XML Schema để kiểm tra cấu trúc

JAXB có thể marshal/unmarshal object nhưng không có nghĩa mọi facet hay occurrence của XSD luôn được thực thi. Với trường hợp cần validation khi dùng JAXB trực tiếp, có thể gắn `Schema` vào marshaller/unmarshaller theo API tương ứng:

~~~java
import java.io.File;

import javax.xml.XMLConstants;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;

import jakarta.xml.bind.Unmarshaller;

SchemaFactory factory =
    SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI
    );

Schema schema =
    factory.newSchema(new File("orders-v1.xsd"));

Unmarshaller unmarshaller = context.createUnmarshaller();
unmarshaller.setSchema(schema);
~~~

Đoạn này chỉ minh họa cách đăng ký schema. Trong dịch vụ thực tế nên nạp schema từ tài nguyên đã đóng gói, cấu hình import/include resolver và kiểm soát truy cập external entities/schema để tránh tải tài nguyên không tin cậy. Trên Spring-WS, `PayloadValidatingInterceptor` là một lựa chọn kiểm tra SOAP payload ở tầng endpoint.

### 14.5. Kiểm thử với SOAP client độc lập

Đối tác có thể dùng .NET/WCF, một ESB hoặc JAX-WS khác JAXB binding của server. Do đó cần kiểm tra:

- WSDL message part tham chiếu đúng global element QName.
- Client sinh từ WSDL có thể tạo `GetOrderRequest` đúng namespace.
- Response được gửi dưới root `GetOrderResponse`, không phải tên type Java.
- SOAP Fault/HTTP binding đúng phiên bản và hợp đồng.
- Schema validation bắt các trường hợp thiếu field bắt buộc, sai kiểu hoặc sai QName.
- Header WS-Security, chữ ký và chứng chỉ (nếu có) không bị ảnh hưởng bởi việc sinh hoặc thay đổi payload.

**Kiểm thử chỉ hai phía dùng chung generated classes có thể bỏ lỡ lỗi tương thích** nếu cả hai vô tình cùng cập nhật QName. Hãy giữ fixture XML/WSDL của các bản đã phát hành để chạy regression.

## 15. Những lựa chọn thiết kế nên ghi nhớ

### 15.1. Coi global element là thông điệp, named type là cấu trúc

Khi đặt tên XSD:

~~~text
Element: GetOrderRequest
Type:    GetOrderRequestType

Element: GetOrderResponse
Type:    GetOrderResponseType
~~~

Cách tách này giúp QName của message được biểu diễn rõ trong WSDL, đồng thời type có thể được tái sử dụng khi cần. Tuy nhiên, không phải mọi schema đều phải tạo hai tên cho mỗi request; anonymous type cũng là một lựa chọn hợp lệ khi không cần tái sử dụng.

### 15.2. Ưu tiên ObjectFactory do XJC sinh ra

Có thể tự tạo `new JAXBElement<>(qName, type, value)`, nhưng nếu XJC đã cung cấp phương thức factory đúng declaration, dùng factory giúp tránh lỗi chính tả namespace, local name và scope.

Ví dụ:

~~~java
JAXBElement<GetOrderRequestType> request =
    new ObjectFactory().createGetOrderRequest(data);
~~~

được ưu tiên hơn việc viết lại QName trong nhiều lớp client/server. Nếu cần đóng gói truy cập factory, hãy viết adapter mỏng trong tầng tích hợp.

### 15.3. Đừng cho Java method name quyết định SOAP contract

Một endpoint có thể đổi method `getOrder()` thành `loadOrder()` mà giữ `@PayloadRoot`, XSD/WSDL và response QName như cũ. Ngược lại, đổi global element hoặc namespace là thay đổi giao diện XML mà bên ngoài có thể thấy ngay.

### 15.4. JAXB binding không thay thế XSD/WSDL validation

`@XmlElement(required=true)`, `@XmlElementDecl`, `@XmlRootElement` và `ObjectFactory` hỗ trợ ánh xạ XML–Java. Chúng không tự bảo đảm mọi trạng thái Java được tạo ra đều thỏa `minOccurs`, `pattern`, `fractionDigits`, `xs:choice` hay quy tắc nghiệp vụ.

### 15.5. Hãy hiểu rõ version JAXB của dự án

Spring-WS trong hệ Jakarta thường dùng `jakarta.xml.bind`, trong khi ví dụ lịch sử Java EE dùng `javax.xml.bind`. `QName` vẫn thuộc `javax.xml.namespace.QName`, vì đây là API XML namespace của Java SE, không phải lớp JAXB cần chuyển sang Jakarta.

Khi gặp lỗi classpath hoặc runtime, kiểm tra API, implementation, XJC và phiên bản Spring-WS trước khi đổ lỗi cho schema.

## 16. Bài thực hành tự làm

Bạn có XSD với:

~~~xml
<xs:complexType name="IdentifierType">
    <xs:sequence>
        <xs:element name="id" type="xs:string"/>
    </xs:sequence>
</xs:complexType>

<xs:element name="FindCustomerRequest"
            type="tns:IdentifierType"/>

<xs:element name="FindSupplierRequest"
            type="tns:IdentifierType"/>
~~~

Giả sử `tns` đã được khai báo cho targetNamespace của schema.

Hãy làm các việc sau:

1. Giải thích vì sao một class `IdentifierType` không xác định duy nhất tên SOAP request.
2. Dự đoán các phương thức mà `ObjectFactory` có thể sinh cho hai global elements.
3. Tạo một `IdentifierType` với `id="C-102"`, lần lượt wrap thành `FindCustomerRequest` và `FindSupplierRequest`.
4. Marshal cả hai wrapper; xác nhận root QName khác nhau dù field bên trong giống nhau.
5. Unmarshal hai XML và kiểm tra `getName()` trước khi xử lý.
6. Tạo hai Spring-WS endpoint handlers có `@PayloadRoot` khác localPart hoặc tách version/namespace phù hợp; xác nhận mỗi message đến đúng handler.
7. Bật XSD validation, gửi request thiếu `id` và kiểm tra lỗi SOAP.
8. Nếu sau này đổi namespace từ v1 sang v2, mô tả kế hoạch sinh lại binding và giữ tương thích cho client v1.

**Tiêu chí đạt:** Bạn có thể chỉ ra từ XSD đâu là type, đâu là element, JAXB lấy QName từ đâu và tại sao `JAXBElement` là cần thiết trong trường hợp nhiều element cùng type.

## 17. Checklist khi làm việc với generated JAXB code

- [ ] XSD có global elements cho những message mà WSDL cần tham chiếu.
- [ ] Đã hiểu sự khác nhau giữa element QName và named type QName.
- [ ] Đã xem `ObjectFactory`, `@XmlElementDecl` và `package-info.java` do XJC sinh.
- [ ] Đã xác định class nào có `@XmlRootElement`, class nào cần `JAXBElement`.
- [ ] Khi marshal, đã chọn phương thức `ObjectFactory.create...(...)` đúng element.
- [ ] Khi unmarshal, đã kiểm tra root QName và kiểu dữ liệu thực tế nếu cần.
- [ ] Đã kiểm thử nil/absent/empty đối với các element optional/nillable.
- [ ] `Jaxb2Marshaller`/JAXBContext nạp đầy đủ binding package và declarations.
- [ ] Spring-WS endpoint/client dùng đúng QName, SOAP binding, action và XSD đã công bố.
- [ ] Không sửa trực tiếp generated files; mọi customization có thể tái sinh.
- [ ] Có validation và interoperability test với client độc lập.

## 18. Ghi nhớ

- **Named complex type** mô tả dữ liệu, còn **global element** có QName xác định root XML trong SOAP Body.
- **ObjectFactory** do XJC sinh cung cấp cả phương thức tạo Java type instance và phương thức tạo element wrapper dựa trên `@XmlElementDecl`.
- **JAXBElement<T>** gắn `value` với QName, declared type, scope và nil; nó cần thiết khi một Java type có thể xuất hiện dưới nhiều tên element.
- **@XmlRootElement** và **@XmlElementDecl** là hai cách JAXB diễn đạt root/element declaration; cách sinh phụ thuộc cấu trúc XSD và binding customization.
- **Spring-WS @PayloadRoot** định tuyến dựa trên QName payload, còn `ObjectFactory` bảo đảm response/client tạo đúng element XML.
- **Contract-first** nghĩa là XSD/WSDL là nguồn sự thật cho hợp đồng công khai; generated Java binding chỉ là cầu nối để ứng dụng xử lý dữ liệu.

**Câu hỏi tự kiểm tra:** XSD khai báo hai global elements `GetOrderRequest` và `CheckOrderRequest` cùng sử dụng `GetOrderRequestType`. Vì sao chỉ marshal một instance `GetOrderRequestType` có thể thất bại, trong khi `ObjectFactory.createGetOrderRequest(instance)` marshal thành công? Hãy giải thích cụ thể vai trò của QName, `@XmlElementDecl`, `JAXBElement` và cách Spring-WS lựa chọn endpoint.

