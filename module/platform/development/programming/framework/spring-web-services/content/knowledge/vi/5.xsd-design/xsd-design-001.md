# `xs:schema`, `targetNamespace` và `elementFormDefault`

## 1. Vì sao ba khái niệm này quan trọng trong SOAP contract-first?

Trong **Spring Web Services (Spring-WS)**, một cách phát triển dịch vụ SOAP phổ biến là **contract-first**: trước tiên thiết kế XSD và WSDL, sau đó sinh hoặc ánh xạ lớp JAXB và triển khai endpoint cùng SOAP client. XSD xác định **phần tử XML nào được phép xuất hiện**, tên đầy đủ của phần tử, kiểu dữ liệu và cấu trúc request/response.

Ba thành phần thường xuất hiện ngay ở đầu XSD:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="qualified">
    <!-- Các khai báo kiểu dữ liệu và phần tử -->
</xs:schema>
~~~

Chúng giải quyết ba câu hỏi khác nhau:

| Thành phần | Câu hỏi mà nó trả lời |
| --- | --- |
| `xs:schema` | Tài liệu này là một XML Schema, chứa những khai báo và định nghĩa nào? |
| `targetNamespace` | Các thành phần **toàn cục** được khai báo trong schema thuộc namespace nào? |
| `elementFormDefault` | Các **phần tử cục bộ** được khai báo trong schema có mặc định thuộc target namespace hay không? |

Ví dụ, hai payload trông gần như giống nhau sau đây **không tương đương về tên phần tử**:

~~~xml
<!-- customerId thuộc urn:example:customer:v1 -->
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <c:customerId>C-101</c:customerId>
</c:GetCustomerRequest>
~~~

~~~xml
<!-- customerId không thuộc namespace nào -->
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <customerId>C-101</customerId>
</c:GetCustomerRequest>
~~~

Nếu schema khai báo `elementFormDefault="qualified"`, ví dụ thứ nhất phù hợp quy tắc namespace, còn ví dụ thứ hai không phù hợp với khai báo cục bộ `customerId` của cùng schema. Lỗi này thường xuất hiện khi tích hợp client Java với .NET, ESB hoặc hệ thống tạo XML thủ công.

**Mục tiêu bài học:** hiểu và tự thiết kế được namespace XSD, phân biệt phần tử toàn cục với cục bộ, đọc đúng tên XML trên dây, tránh lỗi không khớp WSDL/JAXB và kiểm thử tương thích cho SOAP service.

## 2. Nền tảng: namespace và tên mở rộng (expanded name)

Trong XML, tên đầy đủ của một phần tử không chỉ là phần chữ sau dấu hai chấm. Nó được xác định bởi cặp:

`{namespace URI}localName`

Ví dụ:

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1"/>
~~~

Tên mở rộng của phần tử là:

`{urn:example:customer:v1}GetCustomerRequest`

Trong tài liệu khác, có thể dùng prefix khác:

~~~xml
<customer:GetCustomerRequest
    xmlns:customer="urn:example:customer:v1"/>
~~~

Hai phần tử trên có **cùng tên mở rộng**, vì prefix `c` và `customer` đều ánh xạ tới cùng namespace URI. Prefix là bí danh cục bộ trong tài liệu XML; **URI và local name mới xác định danh tính phần tử**.

Ngược lại:

~~~xml
<GetCustomerRequest/>
~~~

Khi không có default namespace, phần tử này có tên mở rộng `{}GetCustomerRequest`, nên khác `{urn:example:customer:v1}GetCustomerRequest`.

Một namespace URI là **định danh**, không bắt buộc là URL có thể mở trên trình duyệt. Chẳng hạn `urn:example:customer:v1` và `https://schemas.example.test/customer/v1` đều có thể được dùng làm namespace. Nếu chọn namespace dạng HTTP URL, không có nghĩa bên nhận phải tự tải schema ở URL đó.

### 2.1. Namespace mặc định và prefix

XML có thể khai báo một namespace mặc định:

~~~xml
<GetCustomerRequest xmlns="urn:example:customer:v1">
    <customerId>C-101</customerId>
</GetCustomerRequest>
~~~

Trong ví dụ này, **cả** `GetCustomerRequest` và `customerId` đều thuộc `urn:example:customer:v1`, dù không có prefix. Namespace mặc định áp dụng cho tên phần tử không có prefix.

**Thuộc tính không có prefix là trường hợp riêng:** default namespace **không tự áp dụng** cho tên thuộc tính không có prefix. Ví dụ:

~~~xml
<GetCustomerRequest xmlns="urn:example:customer:v1"
                    requestId="REQ-001">
    <customerId>C-101</customerId>
</GetCustomerRequest>
~~~

Tên phần tử gốc là `{urn:example:customer:v1}GetCustomerRequest`; tên thuộc tính `requestId` là `{}requestId`. Quy tắc này quan trọng khi schema có cả `elementFormDefault` và `attributeFormDefault`.

## 3. Vai trò của `xs:schema`

`xs:schema` là **phần tử gốc của tài liệu XML Schema Definition (XSD)**. Prefix `xs` chỉ là một lựa chọn phổ biến; điều quan trọng là nó được liên kết tới namespace chuẩn:

`http://www.w3.org/2001/XMLSchema`

Trong một tài liệu XSD, có thể tìm thấy:

- `xs:element`: khai báo phần tử XML.
- `xs:complexType`: mô tả cấu trúc có phần tử con hoặc thuộc tính.
- `xs:simpleType`: mô tả giá trị đơn giản và ràng buộc của chúng.
- `xs:sequence`, `xs:choice`, `xs:all`: mô tả cấu trúc các phần tử con theo những quy tắc khác nhau.
- `xs:attribute`: khai báo thuộc tính.
- `xs:import`, `xs:include`: tổ chức và tái sử dụng schema.

Ví dụ tối giản:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="ping" type="xs:string"/>
</xs:schema>
~~~

Schema trên **không khai báo `targetNamespace`**, nên phần tử toàn cục `ping` có tên không thuộc namespace ứng dụng. Một XML instance phù hợp là:

~~~xml
<ping>Hello</ping>
~~~

Với dịch vụ SOAP tích hợp nhiều hệ thống, thường nên thiết kế namespace cụ thể để tránh xung đột tên giữa các loại thông điệp.

### 3.1. Phân biệt namespace của XSD và namespace nghiệp vụ

Hai namespace sau phục vụ hai mục đích hoàn toàn khác nhau:

| Namespace | Vai trò |
| --- | --- |
| `http://www.w3.org/2001/XMLSchema` | Namespace chứa **ngôn ngữ định nghĩa schema**, gồm `schema`, `element`, `string`, `int`,... |
| `urn:example:customer:v1` | Namespace do nhóm thiết kế hợp đồng đặt ra để định danh phần tử và kiểu dữ liệu nghiệp vụ |

Trong khai báo:

~~~xml
<xs:element name="customerId" type="xs:string"/>
~~~

`xs:element` là cú pháp của ngôn ngữ XSD và `xs:string` là kiểu dữ liệu XSD có sẵn. Chuỗi `customerId` là tên phần tử nghiệp vụ; namespace thực tế của phần tử được xác định theo vị trí khai báo và các quy tắc form trong schema.

## 4. `targetNamespace` xác định không gian tên của hợp đồng

Thuộc tính `targetNamespace` trên `xs:schema` chọn namespace cho các **khai báo và định nghĩa toàn cục** của schema, chẳng hạn global element, global complex type và global simple type có tên.

Ví dụ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1">

    <xs:complexType name="CustomerType">
        <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="Customer" type="tns:CustomerType"/>
</xs:schema>
~~~

Tại đây:

- Global type `CustomerType` có tên `{urn:example:customer:v1}CustomerType`.
- Global element `Customer` có tên `{urn:example:customer:v1}Customer`.
- `tns:CustomerType` trong thuộc tính `type` là một **QName tham chiếu** tới kiểu toàn cục đã định nghĩa.
- Phần tử con `customerId` là **local element**; namespace của nó còn phụ thuộc `elementFormDefault` hoặc thuộc tính `form` trên khai báo cục bộ.

**`targetNamespace` không tự động làm tất cả phần tử con đều có namespace đó.** Đây chính là lý do tồn tại `elementFormDefault`.

### 4.1. `targetNamespace` khác `xmlns:tns`

Hai khai báo thường có cùng URI nhưng không làm cùng việc:

~~~xml
targetNamespace="urn:example:customer:v1"
xmlns:tns="urn:example:customer:v1"
~~~

- `targetNamespace` khai báo các thành phần toàn cục **thuộc namespace nào**.
- `xmlns:tns` ràng buộc prefix `tns`, để các giá trị QName như `type="tns:CustomerType"` hay `ref="tns:Customer"` **tham chiếu tới** namespace đó.

`tns` không phải từ khóa đặc biệt: có thể đổi thành `customer` hoặc `c` mà không đổi danh tính QName, miễn URI giữ nguyên.

Ngược lại, đổi giá trị URI của `targetNamespace` có thể làm các QName toàn cục thay đổi, và là **thay đổi hợp đồng** ảnh hưởng đến WSDL, JAXB và các hệ thống đối tác. Không nên coi việc đổi namespace chỉ là sửa nhãn hiển thị.

### 4.2. Khi schema không có `targetNamespace`

Không khai báo `targetNamespace` nghĩa là schema không xác lập namespace ứng dụng cho các global declarations của nó. Ví dụ `<ping>Hello</ping>` không cần prefix hoặc default namespace khi global element `ping` không có namespace.

Thiếu `targetNamespace` là **hợp lệ theo XSD** trong nhiều trường hợp, nhưng có thể làm việc phân biệt các hợp đồng SOAP trở nên khó hơn. Với contract-first, nên thống nhất cách đặt namespace cho từng miền nghiệp vụ và phiên bản hợp đồng.

## 5. `elementFormDefault` chỉ kiểm soát phần tử cục bộ

`elementFormDefault` có hai giá trị:

| Giá trị | Tác động lên **local element declarations** |
| --- | --- |
| `qualified` | Tên phần tử instance thuộc `targetNamespace` của schema |
| `unqualified` | Tên phần tử instance **không thuộc namespace** ứng dụng |

Giá trị mặc định khi **không viết** `elementFormDefault` là **`unqualified`**.

Điểm mấu chốt: thuộc tính này điều khiển các phần tử được khai báo **cục bộ**, chẳng hạn `xs:element name="customerId"` nằm trong `xs:sequence` của một complex type. Nó **không làm thay đổi namespace của global element** khai báo trực tiếp dưới `xs:schema`.

### 5.1. Ví dụ `qualified`

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="qualified">

    <xs:element name="GetCustomerRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

XML instance **hợp lệ về namespace và cấu trúc**:

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <c:customerId>C-101</c:customerId>
</c:GetCustomerRequest>
~~~

Tại đây, global element `GetCustomerRequest` và local element `customerId` đều mang namespace `urn:example:customer:v1`.

Một cách viết khác cũng hợp lệ:

~~~xml
<GetCustomerRequest xmlns="urn:example:customer:v1">
    <customerId>C-101</customerId>
</GetCustomerRequest>
~~~

Cả hai đều có cùng expanded names. Schema validator so khớp namespace URI và local name, **không** đòi một prefix cố định.

XML sau **không hợp lệ với schema trên**:

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <customerId>C-101</customerId>
</c:GetCustomerRequest>
~~~

Ở đây `customerId` không có prefix và không có default namespace, nên thuộc namespace rỗng, khác tên phần tử mà XSD yêu cầu.

### 5.2. Ví dụ `unqualified`

Giữ nguyên thiết kế, chỉ thay:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="unqualified">

    <xs:element name="GetCustomerRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Instance hợp lệ về namespace là:

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <customerId>C-101</customerId>
</c:GetCustomerRequest>
~~~

**Phần tử gốc vẫn có namespace**, vì nó là global element. Phần tử con `customerId` **không có namespace**, vì nó được khai báo cục bộ và `elementFormDefault="unqualified"`.

Trong trường hợp này, nếu thay phần tử con bằng `<c:customerId>` thì XML không còn khớp khai báo cục bộ. Việc tài liệu XML có cú pháp well-formed **không đảm bảo** nó valid theo XSD.

### 5.3. So sánh hai cấu hình

| Thành phần | `qualified` | `unqualified` |
| --- | --- | --- |
| Global `GetCustomerRequest` | `{urn:example:customer:v1}GetCustomerRequest` | `{urn:example:customer:v1}GetCustomerRequest` |
| Local `customerId` | `{urn:example:customer:v1}customerId` | `{}customerId` |
| Ví dụ phần tử gốc | `<c:GetCustomerRequest>` | `<c:GetCustomerRequest>` |
| Ví dụ phần tử con | `<c:customerId>` | `<customerId>` |
| Prefix có bắt buộc là `c`? | Không | Không |
| Default namespace có ảnh hưởng? | Có, với tên phần tử không prefix | Có, vì có thể vô tình biến phần tử cần unqualified thành qualified |

Nếu dùng `elementFormDefault="unqualified"` nhưng lại đặt `xmlns="urn:example:customer:v1"` trên phần tử gốc, các phần tử con không prefix sẽ **mặc định thuộc namespace đó**, trừ khi hủy default namespace bằng `xmlns=""`. Vì vậy mẫu XML dùng prefix trên root và tên không prefix trên local element thường dễ đọc hơn trong mô hình unqualified.

## 6. Phần tử toàn cục, phần tử cục bộ và tham chiếu `ref`

Một khai báo `xs:element` là **global** khi đặt trực tiếp dưới `xs:schema`:

~~~xml
<xs:element name="CustomerId" type="xs:string"/>
~~~

Một khai báo là **local** khi đặt trong cấu trúc của complex type:

~~~xml
<xs:complexType name="RequestType">
    <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
    </xs:sequence>
</xs:complexType>
~~~

Khi local element có tên riêng bằng `name`, `elementFormDefault` điều khiển việc nó qualified hay unqualified. Tuy nhiên nếu một nội dung cục bộ **tham chiếu global element bằng `ref`**, phần tử thực tế có tên của **global element được tham chiếu**.

Ví dụ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="unqualified">

    <xs:element name="CustomerId" type="xs:string"/>

    <xs:complexType name="RequestType">
        <xs:sequence>
            <xs:element ref="tns:CustomerId"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="GetCustomerRequest" type="tns:RequestType"/>
</xs:schema>
~~~

Mặc dù `elementFormDefault="unqualified"`, phần tử `CustomerId` trong instance vẫn phải thuộc `urn:example:customer:v1` vì `ref="tns:CustomerId"` tham chiếu một **global element**.

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1">
    <c:CustomerId>C-101</c:CustomerId>
</c:GetCustomerRequest>
~~~

Hãy nhớ: **local declaration bằng `name`** và **local reference bằng `ref`** không giống nhau. Không cố gắn `form` để đổi namespace của global element được tham chiếu; danh tính của nó đã được xác định ở khai báo toàn cục.

## 7. Ghi đè `elementFormDefault` cho từng phần tử với `form`

Trong một schema, có thể quy định ngoại lệ trên **local element** bằng thuộc tính `form`:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="qualified">

    <xs:element name="ExampleRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
                <xs:element name="legacyCode" type="xs:string"
                            form="unqualified"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Payload phù hợp:

~~~xml
<c:ExampleRequest xmlns:c="urn:example:customer:v1">
    <c:customerId>C-101</c:customerId>
    <legacyCode>OLD-10</legacyCode>
</c:ExampleRequest>
~~~

`customerId` tuân theo mặc định qualified, còn `legacyCode` được ghi đè thành unqualified. Cơ chế `form` cũng có thể dùng theo chiều ngược lại: trong schema mặc định unqualified, một local element đặt `form="qualified"` sẽ thuộc target namespace.

Mặc dù hợp lệ, việc pha trộn nhiều kiểu form có thể khiến client và người đọc WSDL khó nhận diện. Nên chọn một quy ước nhất quán, chỉ dùng ngoại lệ khi có nhu cầu tích hợp hoặc tương thích thực sự.

## 8. Phân biệt `elementFormDefault` và `attributeFormDefault`

`elementFormDefault` chỉ áp dụng cho **phần tử** cục bộ. Với **thuộc tính** cục bộ, schema có cơ chế riêng: `attributeFormDefault`, mặc định là `unqualified`.

Ví dụ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="qualified"
           attributeFormDefault="unqualified">

    <xs:element name="GetCustomerRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
            </xs:sequence>
            <xs:attribute name="requestId" type="xs:string"
                          use="optional"/>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Instance phù hợp:

~~~xml
<c:GetCustomerRequest xmlns:c="urn:example:customer:v1"
                      requestId="REQ-001">
    <c:customerId>C-101</c:customerId>
</c:GetCustomerRequest>
~~~

Trong ví dụ trên:

- `GetCustomerRequest` và `customerId` là phần tử **qualified**.
- `requestId` là thuộc tính **unqualified**, vì `attributeFormDefault="unqualified"`.
- `c:requestId` sẽ **không khớp** với khai báo thuộc tính cục bộ đó.

Giống phần tử, thuộc tính cục bộ có thể đặt `form="qualified"` hoặc `form="unqualified"` để ghi đè mặc định; global attribute có tên namespace của khai báo toàn cục, không điều khiển bằng `attributeFormDefault`.

## 9. Ví dụ XSD hoàn chỉnh cho SOAP request

Ta xây dựng hợp đồng truy vấn khách hàng theo hướng contract-first. Schema định nghĩa một kiểu mã khách hàng, một kiểu request và một phần tử gốc request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:customer:v1"
    targetNamespace="urn:example:customer:v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:simpleType name="CustomerIdType">
        <xs:restriction base="xs:string">
            <xs:minLength value="1"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="GetCustomerRequestType">
        <xs:sequence>
            <xs:element name="customerId" type="tns:CustomerIdType"/>
            <xs:element name="includeHistory" type="xs:boolean"
                        minOccurs="0"/>
        </xs:sequence>
        <xs:attribute name="requestId" type="xs:string"
                      use="optional"/>
    </xs:complexType>

    <xs:element name="GetCustomerRequest"
                type="tns:GetCustomerRequestType"/>
</xs:schema>
~~~

**Tại sao schema này hợp lý?**

1. `xmlns:xs` cho phép dùng cú pháp `xs:schema`, `xs:element` và các kiểu `xs:string`/`xs:boolean`.
2. `targetNamespace` định danh các global type `CustomerIdType`, `GetCustomerRequestType` và global element `GetCustomerRequest`.
3. `xmlns:tns` cho phép tham chiếu hai type nghiệp vụ bằng `tns:CustomerIdType` và `tns:GetCustomerRequestType`.
4. `elementFormDefault="qualified"` yêu cầu các local element `customerId`, `includeHistory` cũng thuộc namespace nghiệp vụ.
5. `attributeFormDefault="unqualified"` giữ `requestId` là thuộc tính không có namespace.

### 9.1. XML request hợp lệ

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<c:GetCustomerRequest
    xmlns:c="urn:example:customer:v1"
    requestId="REQ-001">
    <c:customerId>C-101</c:customerId>
    <c:includeHistory>true</c:includeHistory>
</c:GetCustomerRequest>
~~~

`includeHistory` có thể bỏ vì `minOccurs="0"`; `customerId` bắt buộc phải có và không được rỗng theo `xs:minLength value="1"`.

### 9.2. SOAP 1.1 Envelope mang request

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:c="urn:example:customer:v1">
    <soap:Header/>
    <soap:Body>
        <c:GetCustomerRequest requestId="REQ-001">
            <c:customerId>C-101</c:customerId>
            <c:includeHistory>true</c:includeHistory>
        </c:GetCustomerRequest>
    </soap:Body>
</soap:Envelope>
~~~

Hai namespace ở đây độc lập:

| Cụm phần tử | Namespace |
| --- | --- |
| `soap:Envelope`, `soap:Header`, `soap:Body` | `http://schemas.xmlsoap.org/soap/envelope/` |
| `c:GetCustomerRequest`, `c:customerId`, `c:includeHistory` | `urn:example:customer:v1` |
| Thuộc tính `requestId` | Không có namespace |

**Đừng gán namespace SOAP Envelope cho phần tử nghiệp vụ.** SOAP namespace mô tả vỏ giao thức; target namespace của XSD mô tả nội dung thông điệp thuộc hợp đồng dịch vụ.

## 10. Liên hệ với WSDL và Spring Web Services

Trong WSDL 1.1, schema thường nằm trong hoặc được tham chiếu từ `wsdl:types`. Một phần tử gốc của request có thể được dùng trong `wsdl:message` qua một `wsdl:part`:

~~~xml
<wsdl:message name="GetCustomerInput">
    <wsdl:part name="parameters" element="c:GetCustomerRequest"/>
</wsdl:message>
~~~

Đây là **đoạn trích WSDL**, giả định prefix `wsdl` được khai báo cho namespace WSDL 1.1 và `c` đã được ánh xạ tới `urn:example:customer:v1` ở phần `wsdl:definitions`.

Thuộc tính `element="c:GetCustomerRequest"` tham chiếu **global XSD element** bằng QName. Prefix `c` không phải yêu cầu cố định đối với SOAP client; điều phải trùng là expanded name `{urn:example:customer:v1}GetCustomerRequest`.

### 10.1. Phân biệt namespace của WSDL và XSD

`targetNamespace` có thể xuất hiện ở cả `wsdl:definitions` và `xs:schema`, nhưng thuộc **hai tài liệu/khái niệm khai báo khác nhau**:

- Trong **XSD**, nó định danh global elements và named types thuộc schema.
- Trong **WSDL**, nó định danh các thành phần WSDL như message, portType, binding và service.

Hai URI **có thể trùng nhau**, nhưng không bắt buộc phải trùng. Đừng sử dụng namespace của `wsdl:definitions` thay cho namespace XSD của `GetCustomerRequest` nếu chúng khác nhau. Khi tra cứu lỗi tích hợp, hãy đọc đúng `wsdl:part element="..."`, `wsdl:types` và XSD tham chiếu.

### 10.2. `@PayloadRoot` khớp QName của phần tử gốc

Spring-WS có thể chọn endpoint dựa trên namespace và local name của phần tử gốc SOAP Body:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;

@Endpoint
public class CustomerEndpoint {
    private static final String NAMESPACE_URI =
            "urn:example:customer:v1";

    @PayloadRoot(
        namespace = NAMESPACE_URI,
        localPart = "GetCustomerRequest"
    )
    public void handleGetCustomer() {
        // Minh họa ánh xạ QName đến endpoint.
        // Endpoint thực tế cần khai báo tham số/giá trị trả về
        // và logic SOAP phù hợp với contract.
    }
}
~~~

Ví dụ chỉ minh họa **cách nhận diện root QName**. Khi triển khai thực tế, endpoint thường nhận `@RequestPayload` cùng DTO JAXB sinh từ schema và trả `@ResponsePayload` theo hợp đồng.

Nếu phía gửi dùng `<GetCustomerRequest>` **không có namespace**, annotation trên sẽ không khớp, mặc dù local name đúng. Một lỗi “không tìm được endpoint mapping” vì vậy có thể do **sai QName**, chứ không nhất thiết do thiếu Java method.

## 11. Tác động tới JAXB và các SOAP client

Trong một quy trình contract-first, các lớp Java thường được sinh từ XSD bằng công cụ JAXB/XJC. Namespace có thể xuất hiện ở annotation cấp lớp, phần tử, trường hoặc cấu hình package, ví dụ:

~~~java
@jakarta.xml.bind.annotation.XmlSchema(
    namespace = "urn:example:customer:v1",
    elementFormDefault =
        jakarta.xml.bind.annotation.XmlNsForm.QUALIFIED
)
package example.customer.ws;
~~~

Đây là nội dung minh họa của file `package-info.java`, áp dụng cho package `example.customer.ws`. Dự án dùng JAXB API cũ có thể sử dụng package `javax.xml.bind.annotation`; dự án Jakarta dùng `jakarta.xml.bind.annotation`. **Mã sinh thực tế phụ thuộc phiên bản công cụ và binding configuration**, vì vậy không nên sửa annotation sinh ra chỉ để che lỗi XSD mà chưa kiểm tra hợp đồng.

Những hiện tượng thường gặp:

- JAXB marshaller tạo `<customerId>` thay vì `<c:customerId>`: kiểm tra namespace và form của local element trong XSD cùng mapping JAXB được sinh.
- Một SOAP client sinh từ WSDL không deserialize được phản hồi: kiểm tra QName của response element và tên các local elements trong Body.
- Client A dùng prefix `c`, client B dùng prefix `ns2`: thông thường **không phải lỗi tương thích** nếu expanded names giống nhau.
- Root QName khác nhau: có thể làm Spring-WS không chọn đúng endpoint, dù payload chứa trường dữ liệu tương tự.

**Điểm cần kiểm thử là XML được marshal ra trên dây**, vì object Java không thể hiện trực quan các prefix và ranh giới namespace. Việc đổi prefix do JAXB tự chọn không nhất thiết là lỗi; XML schema validation theo namespace URI và local name mới là căn cứ chính.

## 12. Nhiều XSD, nhiều namespace: `xs:include` và `xs:import`

Trong dự án doanh nghiệp, mô hình khách hàng có thể dùng các kiểu chung cho địa chỉ, tiền tệ hoặc mã quốc gia. Cần biết cách kết hợp XSD đúng namespace.

### 12.1. `xs:include` cho schema cùng target namespace

Ví dụ:

~~~xml
<xs:include schemaLocation="customer-types.xsd"/>
~~~

`include` dùng để kết hợp schema có **cùng target namespace** với schema hiện tại; trong một số trường hợp, schema được include không có `targetNamespace` và các khai báo có thể được đưa vào namespace của schema bao ngoài (thường gọi là *chameleon schema*). Không dùng include trực tiếp để ghép hai schema có target namespace khác nhau.

### 12.2. `xs:import` cho namespace khác

Giả sử hợp đồng khách hàng muốn dùng `AddressType` ở namespace `urn:example:common:v1`:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:example:customer:v1"
           xmlns:common="urn:example:common:v1"
           targetNamespace="urn:example:customer:v1"
           elementFormDefault="qualified">

    <xs:import namespace="urn:example:common:v1"
               schemaLocation="common-types.xsd"/>

    <xs:element name="CustomerAddress" type="common:AddressType"/>
</xs:schema>
~~~

Đây là ví dụ **phụ thuộc** vào schema ngoài thực sự có global type `{urn:example:common:v1}AddressType`. `xmlns:common` chỉ ràng buộc prefix; `xs:import` thông báo tham chiếu namespace khác, và `schemaLocation` là gợi ý vị trí tài liệu cho bộ xử lý schema. Cần cấu hình resolver hoặc catalog phù hợp trong thực tế; không giả định mọi hệ thống sẽ truy cập trực tiếp một URL từ thông tin namespace.

Khi cho phép tải XSD từ vị trí ngoài, cần kiểm soát nguồn schema tin cậy và cấu hình giới hạn truy cập tài nguyên bên ngoài để tránh rủi ro tải tài liệu ngoài ý muốn. Với Spring-WS, nên đóng gói các schema cần thiết cùng ứng dụng hoặc quản lý chúng theo cơ chế triển khai được kiểm soát.

## 13. Những lỗi thường gặp và cách xác định nguyên nhân

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| XSD validator báo thiếu `customerId` dù nhìn XML thấy trường này | Local element có sai namespace | Đối chiếu expanded name trong instance với `elementFormDefault` |
| SOAP Body có `GetCustomerRequest` nhưng không vào endpoint | Root thiếu namespace hoặc khác local name | Kiểm tra `@PayloadRoot` và QName root của payload |
| Thay prefix `ns2` thành `c` mới hoạt động | Hệ thống đang xử lý prefix bằng chuỗi, hoặc có chênh lệch namespace URI đi kèm | So sánh URI namespace thực tế; không phụ thuộc prefix khi thiết kế |
| Thêm `xmlns="urn:..."` làm bản tin unqualified bị lỗi | Default namespace khiến local elements trở thành qualified | Xem `elementFormDefault`; dùng prefix trên root và local unprefixed khi phù hợp |
| JAXB xuất thuộc tính `c:requestId` nhưng XSD yêu cầu `requestId` | Nhầm `attributeFormDefault` hoặc mapping JAXB | Kiểm tra thuộc tính có prefix và form của local attribute |
| `type="tns:CustomerType"` không tìm thấy kiểu | URI của `tns` không trùng target namespace, kiểu không tồn tại hoặc chưa import | Kiểm tra QName, global type và import/include |
| Mới đổi namespace XSD thì client cũ không gọi được | Đã đổi danh tính các global elements/types trong hợp đồng | Rà soát WSDL, mã JAXB sinh và chiến lược version |
| XML parse được nhưng schema validation thất bại | Well-formed chưa đồng nghĩa XSD-valid | Chạy validation theo đúng bộ XSD/WSDL được công bố |

Một lỗi kinh điển là nhầm **“có dấu hai chấm”** với **“có namespace”**: một phần tử không có prefix vẫn có thể thuộc namespace thông qua `xmlns="..."`, còn một phần tử có prefix nhưng prefix được ánh xạ sai URI sẽ không tương thích dù chữ phần tử trông giống nhau.

## 14. Kiểm thử contract-first cho namespace

Với schema của mục 9, nên kiểm thử cả XML hợp lệ và XML sai. Đây là các ca có ý nghĩa trực tiếp đối với Spring-WS endpoint và SOAP client:

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Root `c:GetCustomerRequest`, child `c:customerId` | Hợp lệ khi các giá trị và thứ tự đúng |
| Đổi prefix `c` thành `ns1`, giữ nguyên URI | Vẫn hợp lệ |
| Dùng default namespace đúng URI cho cả root và child | Vẫn hợp lệ |
| Root qualified, child `customerId` không namespace | Bị XSD từ chối |
| Root `GetCustomerRequest` không namespace | Bị XSD từ chối |
| Root có namespace khác dù cùng local name | Bị XSD từ chối |
| Thuộc tính `requestId` không prefix | Hợp lệ theo `attributeFormDefault="unqualified"` |
| Thuộc tính `c:requestId` | Không khớp khai báo thuộc tính cục bộ |
| `includeHistory` bỏ hẳn | Hợp lệ vì `minOccurs="0"` |
| `customerId` rỗng | Bị từ chối vì `minLength="1"` |
| JAXB marshal rồi unmarshal request | Giữ đúng QName root và các local elements |
| Client khác công nghệ đọc WSDL và gọi endpoint | Gửi đúng URI namespace, kiểu dữ liệu và thứ tự theo XSD |

Có thể kiểm tra payload bằng bộ xác thực **W3C XML Schema** trong Java hoặc tích hợp xác thực XSD vào chuỗi xử lý Spring-WS qua cơ chế phù hợp, chẳng hạn `PayloadValidatingInterceptor`. Không mặc định rằng mọi endpoint Spring-WS tự động kiểm tra XSD nếu chưa cấu hình.

Khi kiểm thử, **không so sánh chuỗi XML thô theo prefix hoặc khoảng trắng** làm tiêu chí duy nhất. Nên phân tích XML theo namespace và kiểm tra cấu trúc, tên phần tử, thuộc tính, giá trị. Với XML chữ ký số/WS-Security, việc thay đổi serialization có thể ảnh hưởng quá trình ký/xác minh tùy cấu hình canonicalization và nội dung được ký; đừng tùy tiện sửa payload đã ký chỉ để đổi prefix.

## 15. Quy tắc thiết kế và versioning

Khi bắt đầu thiết kế XSD cho một SOAP service có nhiều client:

1. **Chọn target namespace ổn định** cho miền hợp đồng. Có thể quy ước phiên bản trong URI, nhưng cần thống nhất với chính sách versioning của tổ chức.
2. **Khai báo rõ `elementFormDefault`** thay vì dựa vào mặc định `unqualified`. Trong nhiều dự án SOAP document/literal, `qualified` giúp các phần tử nghiệp vụ có namespace nhất quán.
3. **Khai báo global element cho root của request/response**, rồi tham chiếu nó trong `wsdl:part` và triển khai endpoint theo QName đó.
4. **Dùng prefix rõ ràng trong XSD** như `xs` cho schema language, `tns` cho target namespace, và prefix riêng cho các namespace import. Không bắt client phải dùng cùng prefix.
5. **Phân biệt thuộc tính và phần tử:** cân nhắc `attributeFormDefault` độc lập với `elementFormDefault`.
6. **Tái sử dụng kiểu bằng include/import đúng phạm vi namespace**, quản lý đường dẫn schema và nguồn tài liệu tin cậy.
7. **Kiểm thử XML do JAXB/SOAP client thực sự tạo ra** với XSD công bố, cùng các tình huống thiếu hoặc sai namespace.
8. **Đánh giá tính tương thích trước khi đổi URI hoặc form**: đổi target namespace hay chuyển local element giữa qualified và unqualified làm thay đổi tên XML, thường là thay đổi phá vỡ client đã triển khai.

Không cần nâng phiên bản namespace chỉ vì thay prefix hoặc sửa cách định dạng XSD mà không đổi ngữ nghĩa contract. Ngược lại, thay URI namespace thực sự có thể thay đổi định danh phần tử/kiểu và cần phương án chuyển đổi, công bố WSDL mới hoặc hỗ trợ nhiều phiên bản nếu có client cũ.

## 16. Tự kiểm tra

Cho schema:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:order:v1"
           elementFormDefault="qualified">
    <xs:element name="CreateOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Hãy thử trả lời:

1. Tên mở rộng của `CreateOrderRequest` là gì?
2. `<o:CreateOrderRequest xmlns:o="urn:example:order:v1"><orderId>O-1</orderId></o:CreateOrderRequest>` có hợp lệ theo XSD trên không?
3. Nếu chuyển `elementFormDefault` thành `unqualified`, có phải bỏ namespace của root không?
4. Nếu chuyển prefix `o` thành `x` nhưng giữ nguyên URI, có phải cập nhật `@PayloadRoot` của Spring-WS không?
5. Nếu thay `targetNamespace` thành `urn:example:order:v2` nhưng vẫn dùng local name cũ, contract có còn cùng QName không?

**Đáp án:**

1. `{urn:example:order:v1}CreateOrderRequest`.
2. **Không**: `orderId` trong instance không thuộc namespace nào, nhưng XSD đòi qualified.
3. **Không**: root là global element nên vẫn mang target namespace; chỉ quy tắc form của local element `orderId` thay đổi.
4. **Không**: Spring-WS so khớp namespace URI và local name, không so khớp một prefix cố định.
5. **Không**: URI khác tạo expanded name khác, thường kéo theo thay đổi WSDL/JAXB và yêu cầu cập nhật client.

## 17. Ghi nhớ

- `xs:schema` khai báo một **XML Schema**; namespace `http://www.w3.org/2001/XMLSchema` là namespace của ngôn ngữ XSD.
- `targetNamespace` định danh **global elements** và **named types** của schema; nó không tự động áp namespace cho mọi local element.
- `elementFormDefault="qualified"` khiến **local elements** thuộc target namespace; `"unqualified"` khiến chúng không có namespace, trừ khi được ghi đè phù hợp. Mặc định của thuộc tính này là **`unqualified`**.
- **Global element luôn mang target namespace của schema** nếu schema có namespace đó, bất kể `elementFormDefault`. Một local `xs:element ref="..."` dùng QName của global element được tham chiếu.
- **Prefix không định danh phần tử**; expanded name `{namespace URI}localName` mới quyết định sự tương thích XML.
- **Namespace mặc định áp dụng cho phần tử không prefix**, nhưng không tự áp dụng cho tên thuộc tính không prefix; `attributeFormDefault` là quy tắc riêng cho local attributes.
- Với **Spring-WS contract-first**, hãy thống nhất namespace giữa XSD, WSDL, JAXB và `@PayloadRoot`; xác thực payload XML thật trước khi tích hợp doanh nghiệp.
