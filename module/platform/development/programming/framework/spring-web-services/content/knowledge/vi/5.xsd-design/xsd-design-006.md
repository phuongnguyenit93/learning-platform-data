# optional, nillable, default, fixed và sự khác biệt khi nhận dữ liệu

## 1. Vì sao bốn thuộc tính XSD này quyết định ngữ nghĩa của SOAP API?

Trong một dịch vụ SOAP phát triển theo hướng **contract-first** với Spring Web Services (Spring-WS), XSD không chỉ mô tả dữ liệu có kiểu `String`, `Integer` hay `Boolean`. XSD còn định nghĩa **phần tử có được vắng mặt không**, **có được hiện diện nhưng mang `nil` không**, **giá trị nào được dùng khi phần tử rỗng hoặc thuộc tính vắng mặt**, và **giá trị nào bị cố định bởi hợp đồng**.

Bốn khái niệm thường gây nhầm lẫn là:

- **`minOccurs="0"` (optional)**: phần tử có thể không xuất hiện trong vị trí mà schema cho phép.
- **`nillable="true"`**: phần tử có thể xuất hiện và được đánh dấu `xsi:nil="true"`.
- **`default`**: cung cấp ràng buộc giá trị mặc định theo quy tắc XSD, *khác nhau giữa element và attribute*.
- **`fixed`**: ràng buộc giá trị hiệu lực phải bằng một giá trị cố định, với quy tắc áp dụng khi vắng mặt/rỗng tùy loại khai báo.

Phân biệt đúng những trạng thái này giúp xây dựng endpoint và SOAP client ổn định. Ngược lại, nếu JAXB ánh xạ nhiều tình trạng XML về cùng một `null`, tầng nghiệp vụ có thể hiểu sai yêu cầu như “giữ nguyên thông tin” thành “xóa thông tin”, dù XML đã parse thành công.

Bài thuộc chương **Thiết kế XSD** của module **SPRING_WEB_SERVICES**. Sau khi học, bạn cần có khả năng đọc schema, dự đoán trạng thái nhận dữ liệu, thiết kế mapper JAXB sang domain, cấu hình kiểm tra XSD tại Spring-WS, và viết kiểm thử tương thích với các SOAP client độc lập.

## 2. Trước hết: “không có”, “rỗng” và “nil” không đồng nghĩa

Giả sử XSD khai báo một phần tử `displayName`. Ba thông điệp XML sau không mang cùng cấu trúc:

**A. Phần tử vắng mặt:**

~~~xml
<cus:UpdateCustomerRequest xmlns:cus="urn:example:customer:v1">
    <cus:customerId>C-1001</cus:customerId>
    <!-- Không có phần tử displayName -->
</cus:UpdateCustomerRequest>
~~~

**B. Phần tử hiện diện, có giá trị nil:**

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <cus:customerId>C-1001</cus:customerId>
    <cus:displayName xsi:nil="true"/>
</cus:UpdateCustomerRequest>
~~~

**C. Phần tử hiện diện, chứa chuỗi rỗng:**

~~~xml
<cus:UpdateCustomerRequest xmlns:cus="urn:example:customer:v1">
    <cus:customerId>C-1001</cus:customerId>
    <cus:displayName/>
</cus:UpdateCustomerRequest>
~~~

Với `xs:string` không có ràng buộc `minLength`, trường hợp C là một **giá trị chuỗi rỗng**. Còn B là một element có trạng thái **nil được đánh dấu rõ**. Trường hợp A hoàn toàn không có element đó.

Một API cập nhật hồ sơ có thể quy định:

| Trạng thái XML | Ý nghĩa nghiệp vụ đề xuất |
|---|---|
| Không có `displayName` | Giữ nguyên tên hiển thị |
| Có `displayName xsi:nil="true"` | Xóa giá trị hiện tại |
| Có `displayName/>` | Đặt tên thành chuỗi rỗng |
| Có `displayName>An</displayName>` | Đặt tên thành `An` |

Đây là **quy ước nghiệp vụ do hợp đồng xác định**, không phải ý nghĩa tự động do SOAP hoặc XSD áp đặt. Nếu nghiệp vụ không cho phép tên rỗng, hãy khai báo facet XSD hoặc quy tắc kiểm tra thích hợp. Điều quan trọng là không vô tình coi cả bốn trạng thái là một.

### Bốn lớp dữ liệu cần phân biệt

~~~mermaid
flowchart TD
    A["SOAP XML đầu vào"] --> B["Kiểm tra với XSD"]
    B --> C["JAXB unmarshal"]
    C --> D["Binding object"]
    D --> E["Mapper: bảo toàn present / nil / value"]
    E --> F["Lệnh nghiệp vụ"]
    F --> G["Kết quả và SOAP response"]
~~~

Trong hình trên, **bảo toàn ý nghĩa lúc ánh xạ** là nhiệm vụ riêng. JAXB giúp chuyển đổi XML thành Java; XML Schema validation giúp xác định message có hợp hợp đồng không; còn mapper quyết định “vắng mặt”, “nil” hay “giá trị thực” được hiểu thế nào trong nghiệp vụ.

## 3. `minOccurs="0"`: optional nghĩa là phần tử có thể vắng mặt

### 3.1. Cú pháp và phạm vi

Ví dụ một element **cục bộ** trong `xs:sequence`:

~~~xml
<xs:complexType name="UpdateCustomerRequestType">
    <xs:sequence>
        <xs:element name="customerId" type="xs:string"/>
        <xs:element name="displayName"
                    type="xs:string"
                    minOccurs="0"/>
    </xs:sequence>
</xs:complexType>
~~~

Ở đây:

- `customerId` mặc định có `minOccurs="1"`, nên phải xuất hiện đúng một lần nếu không có `maxOccurs` khác.
- `displayName` có thể **không xuất hiện**, nhưng nếu xuất hiện thì phải là một phần tử hợp lệ theo kiểu `xs:string`.
- `minOccurs="0"` chỉ nói về **số lần xuất hiện**, không tự cho phép `xsi:nil="true"`.

`minOccurs` là đặc điểm của **element particle tại vị trí sử dụng**, chẳng hạn phần tử cục bộ trong sequence hoặc phần tử `ref` bên trong content model. Không khai báo `minOccurs` trực tiếp trên global element ở cấp cao nhất của `xs:schema`. Global element có thể được tham chiếu từ một vị trí optional:

~~~xml
<xs:element name="displayName" type="xs:string"/>

<xs:complexType name="ExampleType">
    <xs:sequence>
        <xs:element ref="tns:displayName" minOccurs="0"/>
    </xs:sequence>
</xs:complexType>
~~~

Ví dụ trên giả định prefix `tns` đã được khai báo trỏ đến `targetNamespace` của schema.

### 3.2. Optional không đồng nghĩa `null` trong Java

Một lớp Java có field:

~~~java
private String displayName;
~~~

có thể chứa `null` vì nhiều nguyên nhân: message không có element, object được tạo thủ công, mapper quên gán, hoặc XML có nil nếu schema/binding cho phép. Chỉ nhìn `String == null` không chứng minh được XML gốc thuộc trường hợp nào.

Java `Optional<String>` là công cụ biểu diễn tình trạng có/không trong ứng dụng, nhưng JAXB không tự động biến mọi `minOccurs="0"` thành `Optional<String>`. Khi cần lưu đầy đủ thông tin XML, hãy thiết kế mapping theo binding thực tế hoặc dùng object thể hiện rõ trạng thái nhận được.

### 3.3. Thêm field optional có luôn tương thích?

Giả sử bản v1 có:

~~~xml
<xs:sequence>
    <xs:element name="customerId" type="xs:string"/>
</xs:sequence>
~~~

Bản cập nhật bổ sung:

~~~xml
<xs:sequence>
    <xs:element name="customerId" type="xs:string"/>
    <xs:element name="includeHistory"
                type="xs:boolean"
                minOccurs="0"/>
</xs:sequence>
~~~

Request cũ thiếu `includeHistory` vẫn có thể được **server mới** chấp nhận. Nhưng khi client mới gửi `includeHistory`, **server cũ** dùng XSD cũ và validation chặt có thể từ chối element lạ. Tương tự, thêm element vào response có thể làm client cũ không đọc được nếu kiểm tra đúng schema cũ.

Vì vậy, “optional” chỉ giúp giảm ràng buộc **về sự hiện diện trong một schema cụ thể**; tính tương thích tiến/lùi cần kiểm thử theo từng chiều.

## 4. `nillable="true"`: phần tử được phép hiện diện với nil

### 4.1. `xsi:nil` là thuộc tính trong namespace chuẩn

Ví dụ:

~~~xml
<cus:displayName
    xmlns:cus="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Để hợp lệ theo XSD, element tương ứng phải khai báo `nillable="true"`. Nếu không khai báo, mặc định là `nillable="false"`:

~~~xml
<xs:element name="displayName"
            type="xs:string"
            nillable="true"/>
~~~

Một element được đánh dấu nil không mang nội dung text/child element có giá trị. Với complex type có attribute, một phần tử nil trong một số trường hợp vẫn có thể có **attribute được schema cho phép**; điều quan trọng là nội dung của element phải rỗng khi nil theo quy tắc XSD.

Đừng nhầm:

- `xsi:nil="true"` (hoặc `"1"`) là trạng thái nil theo XML Schema instance.
- `<displayName/>` không có `xsi:nil` là phần tử **rỗng**, có thể là chuỗi `""` với `xs:string`.
- `<displayName> </displayName>` chứa whitespace text và không nhất thiết tương đương với phần tử rỗng; xử lý còn phụ thuộc kiểu/facet của XSD.

### 4.2. Bốn tổ hợp optional/nillable

| `minOccurs` | `nillable` | Có thể vắng mặt? | Có thể xuất hiện với `xsi:nil="true"`? |
|---|---|---|---|
| `1` | `false` | Không | Không |
| `0` | `false` | Có | Không |
| `1` | `true` | Không | Có |
| `0` | `true` | Có | Có |

Ví dụ quan trọng:

~~~xml
<xs:element name="displayName"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Khai báo này cho phép cả **vắng mặt** và **hiện diện với nil**. Nó cũng cho phép `<displayName/>` vì `xs:string` chấp nhận chuỗi rỗng, trừ khi có thêm ràng buộc như `minLength="1"`.

Ngược lại:

~~~xml
<xs:element name="legalName"
            type="xs:string"
            minOccurs="1"
            nillable="true"/>
~~~

`legalName` **phải có element** nhưng có thể là nil. Người viết SOAP client không thể bỏ luôn element chỉ vì giá trị không có.

### 4.3. `nillable` chỉ dành cho element

Attribute XSD không có khái niệm `nillable` như element. Nếu cần thể hiện trạng thái “không gửi” đối với attribute, có thể dùng `use="optional"`. Nếu cần một trạng thái xóa rõ ràng, hãy thiết kế phần tử hoặc giao thức cập nhật phù hợp thay vì cố gửi `xsi:nil` trên attribute.

## 5. `default`: giá trị mặc định áp dụng khác nhau cho element và attribute

Đây là chỗ nhiều ứng dụng SOAP gặp lỗi ngữ nghĩa nhất. Tên thuộc tính cùng là `default`, nhưng **điều kiện áp dụng mặc định cho element và attribute không giống nhau**.

### 5.1. Element có `default`: vắng mặt không được tự tạo thành element

Khai báo:

~~~xml
<xs:element name="preferredLocale"
            type="xs:string"
            minOccurs="0"
            default="vi-VN"/>
~~~

Xét ba đầu vào:

**A. Không gửi element:**

~~~xml
<!-- preferredLocale hoàn toàn vắng mặt -->
~~~

**B. Gửi element rỗng:**

~~~xml
<cus:preferredLocale xmlns:cus="urn:example:customer:v1"/>
~~~

**C. Gửi giá trị tường minh:**

~~~xml
<cus:preferredLocale xmlns:cus="urn:example:customer:v1">en-US</cus:preferredLocale>
~~~

Khi **schema validation/PSVI** được áp dụng theo XML Schema:

- A hợp lệ vì `minOccurs="0"`; XSD **không tự chèn một element bị thiếu**. Không thể suy ra locale là `vi-VN` chỉ từ việc phần tử không tồn tại.
- B có element rỗng; giá trị mặc định `vi-VN` được dùng làm giá trị hiệu lực theo quy tắc value constraint.
- C có dữ liệu tường minh `en-US`; `default` không ghi đè giá trị này.

Đối với element kiểu `xs:string` có default, trường hợp `<preferredLocale/>` **khác** `<preferredLocale></preferredLocale>` về cách viết nhưng cùng biểu diễn element không có nội dung, nên đều áp dụng default khi được xử lý schema-aware. Một phần tử chứa whitespace text không nhất thiết thỏa điều kiện “rỗng”; phụ thuộc nội dung thực tế và quy tắc chuẩn hóa của kiểu.

**Quy tắc nhớ:** Với element optional, `default` **không đồng nghĩa** “nếu người gửi bỏ trường thì tự điền giá trị”. Muốn dịch vụ áp dụng mặc định khi field vắng mặt, hãy quy định và thực thi rõ ràng ở tầng nghiệp vụ, hoặc thiết kế contract phù hợp.

### 5.2. Attribute có `default`: vắng mặt có thể nhận giá trị mặc định trong PSVI

Khai báo:

~~~xml
<xs:attribute name="priority"
              type="xs:string"
              use="optional"
              default="NORMAL"/>
~~~

Nếu XML chứa:

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1">
    ...
</cus:UpdateCustomerRequest>
~~~

thì attribute `priority` **không xuất hiện trong XML nguồn**. Tuy vậy, khi một XML Schema-aware processor kiểm tra và tăng cường infoset (PSVI), nó có thể cung cấp giá trị hiệu lực của attribute là `NORMAL` theo default declaration.

Nếu người gửi ghi:

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1"
    priority="HIGH">
    ...
</cus:UpdateCustomerRequest>
~~~

thì giá trị tường minh `HIGH` được dùng. Với `xs:string`, `priority=""` là chuỗi rỗng hợp lệ nếu không có facet cấm; nó **không được thay bằng** `NORMAL` chỉ vì nội dung rỗng.

Khác biệt cần ghi nhớ:

| Khai báo | Khi dữ liệu bị thiếu | Khi có giá trị rỗng |
|---|---|---|
| Element `minOccurs="0" default="X"` | Không có element để được thêm giá trị mặc định | Element hiện diện nhưng rỗng có giá trị hiệu lực `X` khi schema-aware |
| Attribute `use="optional" default="X"` | Giá trị mặc định `X` được cung cấp trong PSVI | Attribute `attr=""` có giá trị rỗng nếu kiểu cho phép |

PSVI (Post-Schema-Validation Infoset) là tập thông tin được bổ sung sau khi xử lý schema. **XML nguyên bản trên đường truyền không bị sửa thành văn bản mới** chỉ vì validator có thể suy ra giá trị mặc định.

### 5.3. JAXB có tự điền default vào field Java không?

Không nên dựa vào giả định đó. Khi XSD được sinh lớp bằng XJC, có thể xuất hiện `@XmlElement(defaultValue = "...")`, giá trị khởi tạo hoặc metadata binding khác, tùy XSD và công cụ. Kết quả runtime còn phụ thuộc việc unmarshal có dùng schema validation hay không và cách implementation cung cấp thông tin mặc định.

Ví dụ Java:

~~~java
@XmlElement(name = "preferredLocale", defaultValue = "vi-VN")
protected String preferredLocale;
~~~

Annotation mô tả một phần của metadata ánh xạ, nhưng bản thân nó **không thay đổi quy tắc XSD rằng element optional vắng mặt không được tự tạo ra**. Hãy thử thực tế các trường hợp vắng mặt, rỗng và có giá trị với đúng phiên bản JAXB/runtime đang sử dụng.

Nếu nghiệp vụ yêu cầu locale mặc định ngay khi field không được gửi, một cách minh bạch là xử lý ở tầng mapper/service:

~~~java
String effectiveLocale =
    (incomingLocale == null) ? "vi-VN" : incomingLocale;
~~~

Đoạn trên **chỉ đúng khi hợp đồng cố ý coi mọi `null` từ binding là cần default**. Nếu `null` còn có nghĩa “không thay đổi” hoặc “nil để xóa”, phép gộp đó làm mất thông tin. Phải phân biệt các trạng thái trước khi áp dụng mặc định.

## 6. `fixed`: ràng buộc phải bằng một giá trị định trước

### 6.1. Element có `fixed`

Khai báo:

~~~xml
<xs:element name="commandType"
            type="xs:string"
            fixed="UPDATE"/>
~~~

Các ví dụ:

~~~xml
<cus:commandType xmlns:cus="urn:example:customer:v1">UPDATE</cus:commandType>
~~~

Giá trị `UPDATE` hợp lệ.

~~~xml
<cus:commandType xmlns:cus="urn:example:customer:v1"/>
~~~

Một element hiện diện nhưng rỗng nhận giá trị hiệu lực `UPDATE` theo ràng buộc fixed khi schema-aware, tương tự cơ chế value constraint. Tuy nhiên:

~~~xml
<cus:commandType xmlns:cus="urn:example:customer:v1">DELETE</cus:commandType>
~~~

là **không hợp lệ** với khai báo `fixed="UPDATE"`.

Nếu phần tử còn khai báo `minOccurs="0"`, thì việc **vắng mặt vẫn được phép**. `fixed` không biến một element optional thành required. Nếu `minOccurs` mặc định là 1, phần tử vẫn phải hiện diện.

Với những kiểu dữ liệu không phải chuỗi, việc so sánh với `fixed` chịu quy tắc giá trị của datatype và normalization tương ứng; không nhất thiết là so sánh từng ký tự văn bản. Ví dụ các biểu diễn số hoặc boolean có thể khác cú pháp nhưng cùng giá trị trong value space. Không tự triển khai kiểm tra fixed chỉ bằng so sánh raw XML string nếu muốn bám sát XML Schema.

### 6.2. Attribute có `fixed`

Khai báo:

~~~xml
<xs:attribute name="origin"
              type="xs:string"
              use="optional"
              fixed="CRM"/>
~~~

Nếu attribute vắng mặt, XML Schema-aware processor có thể cung cấp giá trị fixed `CRM` trong PSVI. Nếu được gửi, giá trị phải phù hợp `CRM`; ví dụ `origin="ERP"` là không hợp lệ.

Điểm khác với element: attribute optional có value constraint (default hoặc fixed) **có thể được cung cấp giá trị hiệu lực khi vắng mặt**, còn một element optional vắng mặt không được tự tạo ra chỉ vì khai báo `fixed`.

### 6.3. Không dùng `default` và `fixed` đồng thời trên cùng một khai báo

Một khai báo element/attribute chỉ được mang **một loại value constraint**: `default` hoặc `fixed`. Không viết:

~~~xml
<!-- Ví dụ SAI: không dùng đồng thời default và fixed -->
<xs:element name="commandType"
            type="xs:string"
            default="UPDATE"
            fixed="UPDATE"/>
~~~

Ngoài ra, một attribute khai báo `default` cần phù hợp các quy tắc `use` của XSD; thường là `use="optional"`. Không coi `default` là cách hợp lệ để né một attribute bắt buộc.

### 6.4. Khi nào nên dùng `fixed`?

`fixed` hữu ích nếu contract thật sự yêu cầu một giá trị bất biến để nhận dạng một biến thể thông điệp. Nhưng đặt một element `commandType` cố định `UPDATE` trong `UpdateCustomerRequest` cũng có thể là thiết kế dư thừa: QName `UpdateCustomerRequest` đã thể hiện thao tác.

Hãy cân nhắc: liệu giá trị cố định là một **ràng buộc trao đổi dữ liệu có ý nghĩa** hay chỉ được thêm để lặp lại thông tin có sẵn? Quá nhiều phần tử fixed có thể làm client khó sinh dữ liệu hơn mà không cải thiện khả năng tích hợp.

## 7. Ví dụ XSD kết hợp bốn cơ chế

Xét một SOAP operation cập nhật hồ sơ khách hàng. Yêu cầu nghiệp vụ:

1. `customerId` bắt buộc.
2. `displayName` có thể bỏ qua, xóa bằng nil hoặc đặt giá trị mới.
3. `preferredLocale` optional; nếu element được gửi rỗng thì XSD có giá trị mặc định `vi-VN`.
4. `commandType` phải là `UPDATE`.
5. Attribute `priority` optional, mặc định `NORMAL`.
6. Attribute `origin` optional nhưng nếu có thì phải là `CRM`.

XSD minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:cus="urn:example:customer:v1"
    targetNamespace="urn:example:customer:v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:element name="UpdateCustomerRequest"
                type="cus:UpdateCustomerRequestType"/>

    <xs:complexType name="UpdateCustomerRequestType">
        <xs:sequence>
            <xs:element name="customerId"
                        type="xs:string"/>

            <xs:element name="displayName"
                        type="xs:string"
                        minOccurs="0"
                        nillable="true"/>

            <xs:element name="preferredLocale"
                        type="xs:string"
                        minOccurs="0"
                        default="vi-VN"/>

            <xs:element name="commandType"
                        type="xs:string"
                        fixed="UPDATE"/>
        </xs:sequence>

        <xs:attribute name="priority"
                      type="xs:string"
                      use="optional"
                      default="NORMAL"/>

        <xs:attribute name="origin"
                      type="xs:string"
                      use="optional"
                      fixed="CRM"/>
    </xs:complexType>
</xs:schema>
~~~

**Ghi chú về namespace:** Với `elementFormDefault="qualified"`, các child element như `customerId` thuộc `urn:example:customer:v1`. Với `attributeFormDefault="unqualified"`, hai attribute `priority` và `origin` trong ví dụ không có namespace.

### 7.1. Một request có nil và element mang default

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    priority="HIGH">
    <cus:customerId>C-1001</cus:customerId>
    <cus:displayName xsi:nil="true"/>
    <cus:preferredLocale/>
    <cus:commandType>UPDATE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

Phân tích theo XSD:

| Field | Trạng thái trong XML nguồn | Ý nghĩa theo XSD khi có schema processing |
|---|---|---|
| `customerId` | Có `C-1001` | Giá trị `C-1001` |
| `displayName` | Có `xsi:nil="true"` | Có element, giá trị nil |
| `preferredLocale` | Có element rỗng | Giá trị mặc định `vi-VN` |
| `commandType` | Có `UPDATE` | Hợp lệ với fixed |
| `priority` | Có `HIGH` | Dùng giá trị tường minh `HIGH` |
| `origin` | Attribute vắng mặt | Giá trị fixed `CRM` có thể được cung cấp trong PSVI |

Nếu phía nhận chỉ chạy JAXB unmarshal mà không kiểm tra XSD, không thể mặc định rằng mọi ràng buộc sẽ được thực thi hoặc mọi giá trị mặc định/fixed sẽ tự xuất hiện trong object. Nên đọc kỹ binding sinh ra và kiểm tra kết quả thực tế với pipeline dự kiến.

### 7.2. Request bỏ field optional

~~~xml
<cus:UpdateCustomerRequest xmlns:cus="urn:example:customer:v1">
    <cus:customerId>C-1001</cus:customerId>
    <cus:commandType>UPDATE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

Theo hợp đồng:

- `displayName` **vắng mặt**, không có yêu cầu đặt nil hay chuỗi rỗng.
- `preferredLocale` **vắng mặt**; mặc định của element **không tạo ra** `preferredLocale`.
- `priority` và `origin` **vắng mặt dưới dạng attribute nguồn**, nhưng có default/fixed tương ứng ở lớp PSVI.
- `customerId` và `commandType` thỏa yêu cầu về hiện diện.

Đây là ví dụ cốt lõi: **cùng là “không gửi”, element và attribute có thể dẫn tới giá trị hiệu lực khác nhau**.

### 7.3. Một số request bị XSD từ chối

**Không gửi element bắt buộc:**

~~~xml
<cus:UpdateCustomerRequest xmlns:cus="urn:example:customer:v1">
    <cus:displayName>An</cus:displayName>
    <cus:commandType>UPDATE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

Thiếu `customerId`.

**Giá trị không khớp fixed:**

~~~xml
<cus:UpdateCustomerRequest xmlns:cus="urn:example:customer:v1">
    <cus:customerId>C-1001</cus:customerId>
    <cus:commandType>DELETE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

`commandType` khác `UPDATE`.

**Gửi nil cho phần tử không nillable:**

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <cus:customerId>C-1001</cus:customerId>
    <cus:preferredLocale xsi:nil="true"/>
    <cus:commandType>UPDATE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

`preferredLocale` không khai báo `nillable="true"`, nên việc đánh dấu nil như trên vi phạm XSD. Nó khác hoàn toàn với element rỗng `<cus:preferredLocale/>`, vốn dùng default khi schema-aware.

**Attribute vi phạm fixed:**

~~~xml
<cus:UpdateCustomerRequest
    xmlns:cus="urn:example:customer:v1"
    origin="ERP">
    <cus:customerId>C-1001</cus:customerId>
    <cus:commandType>UPDATE</cus:commandType>
</cus:UpdateCustomerRequest>
~~~

Attribute `origin="ERP"` không bằng giá trị fixed `CRM`.

## 8. Bảng quyết định tổng hợp cho người nhận dữ liệu

### 8.1. Khi đối tượng là element

| XSD | Vắng mặt | Hiện diện rỗng `<x/>` | Hiện diện `xsi:nil="true"` | Có giá trị khác |
|---|---|---|---|---|
| `minOccurs="0"`, `nillable="false"`, không constraint | Hợp lệ | Tùy kiểu XSD | Không hợp lệ | Hợp lệ nếu đúng kiểu |
| `minOccurs="1"`, `nillable="true"`, không constraint | Không hợp lệ | Tùy kiểu XSD | Hợp lệ | Hợp lệ nếu đúng kiểu |
| `minOccurs="0"`, `nillable="true"` | Hợp lệ | Tùy kiểu XSD | Hợp lệ | Hợp lệ nếu đúng kiểu |
| `minOccurs="0" default="X"` | Hợp lệ, không tự chèn element | Hiệu lực `X` khi schema-aware | Không hợp lệ nếu không nillable | Dùng giá trị được gửi |
| `minOccurs="0" fixed="X"` | Hợp lệ, không tự chèn element | Hiệu lực `X` khi schema-aware | Không hợp lệ nếu không nillable | Chỉ hợp lệ nếu bằng `X` |

Bảng giả định element có kiểu đơn phù hợp và các khai báo `default`/`fixed` không kết hợp với `nillable="true"`; cần đọc cả constraints khác như `minLength`, `pattern`, datatype và model group. Với `xs:int` không có value constraint, `<x/>` thường không hợp lệ vì chuỗi rỗng không phải số nguyên. Với `xs:string`, nó thường hợp lệ nếu không có facet loại trừ.

### 8.2. Khi đối tượng là attribute

| XSD attribute | Không xuất hiện | Có `name=""` | Có `name="VALUE"` |
|---|---|---|---|
| `use="optional"` | Hợp lệ, không có giá trị từ constraint | Tùy datatype | Hợp lệ nếu đúng datatype |
| `use="required"` | Không hợp lệ | Tùy datatype | Hợp lệ nếu đúng datatype |
| `use="optional" default="X"` | Default `X` trong PSVI | Rỗng nếu datatype cho phép | Dùng giá trị `VALUE` |
| `use="optional" fixed="X"` | Fixed `X` trong PSVI | Chỉ hợp lệ nếu thỏa fixed | Chỉ hợp lệ nếu thỏa fixed |

Attribute **không có `minOccurs`, `maxOccurs` hoặc `nillable`**. Trong XSD, cơ chế quy định hiện diện của attribute là `use` (ví dụ `optional`, `required`, `prohibited`).

## 9. JAXB: khi XML phân biệt nhiều trạng thái nhưng Java chỉ có `null`

### 9.1. Binding class có thể không diễn đạt đầy đủ presence

Khi dùng JAXB/XJC sinh lớp từ XSD, một field đơn giản có thể xuất hiện như:

~~~java
protected String displayName;
~~~

Nhưng với `minOccurs="0" nillable="true"`, XJC cũng có thể tạo mapping dựa trên `JAXBElement<String>`, tùy schema và thiết lập sinh mã:

~~~java
@XmlElementRef(
    name = "displayName",
    namespace = "urn:example:customer:v1",
    type = JAXBElement.class,
    required = false
)
protected JAXBElement<String> displayName;
~~~

Đoạn mã là **minh họa một dạng binding có thể gặp**, không cam kết mọi XJC sẽ sinh đúng property này.

Khi model dùng `JAXBElement<String>`, ứng dụng có thể phân biệt:

- Property `null`: element không xuất hiện, theo cách JAXB binding đang sử dụng.
- Property có `isNil() == true`: element xuất hiện với nil.
- Property có `isNil() == false` và `getValue().equals("")`: element xuất hiện với chuỗi rỗng.
- Property có giá trị thường: element xuất hiện với dữ liệu được gửi.

Cần kiểm tra đúng annotation, `ObjectFactory`, cấu hình XJC và kết quả unmarshal thực tế. Không suy ra trạng thái nguồn chỉ từ tên class hay từ một snippet trên mạng.

### 9.2. Thiết kế tri-state/quad-state tại tầng nghiệp vụ

Với nghiệp vụ cập nhật, chỉ dùng `String` nullable không đủ. Có thể xây một model biểu diễn ý định rõ ràng:

~~~java
public enum UpdateKind {
    UNCHANGED,
    CLEAR,
    SET
}

public record FieldUpdate<T>(UpdateKind kind, T value) {

    public static <T> FieldUpdate<T> unchanged() {
        return new FieldUpdate<>(UpdateKind.UNCHANGED, null);
    }

    public static <T> FieldUpdate<T> clear() {
        return new FieldUpdate<>(UpdateKind.CLEAR, null);
    }

    public static <T> FieldUpdate<T> set(T value) {
        return new FieldUpdate<>(UpdateKind.SET, value);
    }
}
~~~

Giả sử hợp đồng quy định absent = không cập nhật, nil = xóa, element khác nil = đặt giá trị mới, phép chuyển từ `JAXBElement<String>` có thể như sau:

~~~java
public FieldUpdate<String> mapDisplayName(
        JAXBElement<String> incoming) {

    if (incoming == null) {
        return FieldUpdate.unchanged();
    }

    if (incoming.isNil()) {
        return FieldUpdate.clear();
    }

    return FieldUpdate.set(incoming.getValue());
}
~~~

Với mapper này, `FieldUpdate.set("")` được giữ riêng với `FieldUpdate.clear()`. Domain service có thể quyết định tên rỗng có hợp lệ không. Nếu hợp đồng có quy ước khác về nil và chuỗi rỗng, mapper phải đổi theo quy ước đó.

**Giới hạn cần biết:** Cách ánh xạ này chỉ dùng được khi JAXB binding thực tế **bảo toàn được presence và nil** như giả định. Nếu trình unmarshal đã gộp hai trạng thái thành cùng `null`, không có cách suy đoán chính xác từ `null` sau đó. Khi thật sự cần ba/bốn trạng thái, hãy chọn binding phù hợp hoặc kiểm tra DOM/XML trước khi làm mất thông tin.

### 9.3. Tránh kiểu Java primitive cho trường cần vắng mặt

Một `int quantity` trong Java mặc định bằng 0, khó phân biệt “XML không gửi quantity” với “XML gửi quantity = 0”. Nếu XSD cho phép optional, thường cần wrapper `Integer`, binding theo presence hoặc một cấu trúc khác. Nhưng ngay cả `Integer` cũng chỉ phân biệt `null` và có số; nó không tự tách absent khỏi nil.

Tương tự, `boolean` mặc định `false` không có nghĩa là client thực sự gửi `false`.

### 9.4. `@XmlElement(required = true)` không thay thế schema validation

Annotation JAXB:

~~~java
@XmlElement(required = true)
protected String customerId;
~~~

có thể phản ánh ràng buộc của XSD, nhưng không đảm bảo mọi lần unmarshal/marshal ở runtime đều tự kiểm tra đầy đủ `minOccurs`, `nillable`, `fixed`, facet kiểu dữ liệu và thứ tự element. Đừng coi object Java được tạo thành công là bằng chứng SOAP request hợp lệ theo hợp đồng.

## 10. Spring-WS: kiểm tra XSD tại ranh giới SOAP

Một endpoint theo hướng contract-first thường nhận XML, xác thực với XSD, unmarshal JAXB, rồi chuyển tiếp thành lệnh nghiệp vụ.

Ví dụ định tuyến theo QName request:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class CustomerEndpoint {

    private static final String NAMESPACE =
        "urn:example:customer:v1";

    private final CustomerApplicationService service;

    public CustomerEndpoint(CustomerApplicationService service) {
        this.service = service;
    }

    @PayloadRoot(
        namespace = NAMESPACE,
        localPart = "UpdateCustomerRequest"
    )
    @ResponsePayload
    public UpdateCustomerResponse update(
            @RequestPayload UpdateCustomerRequest request) {

        return service.update(request);
    }
}
~~~

Đây là code minh họa: giả định lớp binding request/response và JAXB marshalling đã được cấu hình. Tùy cách XJC sinh global element, tham số thực tế có thể là `JAXBElement<UpdateCustomerRequestType>` thay vì class root `UpdateCustomerRequest`.

### 10.1. Dùng `PayloadValidatingInterceptor`

Ví dụ cấu hình Spring-WS:

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;

import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
@EnableWs
public class CustomerContractConfig implements WsConfigurer {

    @Bean
    public XsdSchema customerSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("xsd/customer-v1.xsd")
        );
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        PayloadValidatingInterceptor validator =
            new PayloadValidatingInterceptor();

        validator.setXsdSchema(customerSchema());
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);
        interceptors.add(validator);
    }
}
~~~

Ví dụ giả định ứng dụng dùng cấu hình Spring-WS tương thích và có schema thực tại `src/main/resources/xsd/customer-v1.xsd`. Với các schema import/include, cần bảo đảm validator có thể phân giải đầy đủ các phụ thuộc. Phần `setValidateResponse(true)` còn yêu cầu XSD chứa schema cho response; nếu mới chỉ định nghĩa request, phải bổ sung response trước khi dùng cấu hình này trong một dịch vụ thật.

**Schema validation** sẽ giúp phát hiện những XML như `commandType=DELETE`, thiếu phần tử required hoặc gửi `xsi:nil` cho phần tử không nillable. Tùy cấu hình resolver và framework, lỗi có thể được chuyển thành SOAP Fault thích hợp. Hãy kiểm tra mã Fault/phản hồi thực tế với phiên bản SOAP của dịch vụ.

### 10.2. Validation và default materialization là hai vấn đề khác nhau

Một pipeline có thể kiểm tra XML hợp lệ mà không đưa đầy đủ thông tin PSVI vào DTO Java. Ví dụ:

1. Interceptor validation kiểm tra rằng `<preferredLocale/>` là hợp lệ.
2. JAXB unmarshal tạo object tương ứng.
3. Cách truy xuất giá trị default trong object phụ thuộc annotation/binding và runtime.

Do vậy, không được viết business logic dựa trên niềm tin rằng “đã bật `PayloadValidatingInterceptor`, nên mọi `default` đã biến thành chuỗi trong DTO”. Để đảm bảo đúng kết quả, phải kiểm thử chính xác luồng nhận dữ liệu đang triển khai. Nếu cần, mapper có thể áp dụng default một cách tường minh nhưng phải phân biệt absent/nil/empty theo hợp đồng.

### 10.3. Quy tắc lỗi nghiệp vụ không thay bằng `default`/`fixed`

XSD không biết khách hàng có tồn tại hay không, người gọi có quyền sửa tên hay không, hay giao dịch có bị khóa hay không. Các quy tắc ấy thuộc application/domain service và có thể tạo SOAP Fault nghiệp vụ.

Ví dụ:

- Sai `commandType` là lỗi cấu trúc/ràng buộc XML theo XSD.
- `customerId` đúng kiểu nhưng không tồn tại là lỗi nghiệp vụ.
- Header WS-Security thiếu chữ ký/chứng chỉ không đáng tin là lỗi xác thực/bảo mật, nằm ngoài bốn thuộc tính XSD đang học.

Phân tầng rõ ràng giúp tạo Fault nhất quán và tránh bỏ qua kiểm tra bảo mật vì “XML đã đúng XSD”.

## 11. Kiểm thử theo ma trận trạng thái đầu vào

Để biết chính xác dữ liệu được nhận ra sao, nên lưu SOAP fixture và kiểm thử qua **cùng đường đi mà sản phẩm sử dụng**: HTTP SOAP → Spring-WS → XSD validation → JAXB → mapper → domain service.

### 11.1. Ma trận cho element optional/nillable

Giả sử `displayName minOccurs="0" nillable="true" type="xs:string"`.

| Mã ca | Input | XSD | Ý nghĩa dự kiến theo quy ước cập nhật |
|---|---|---|---|
| D1 | Không có `displayName` | Hợp lệ | `UNCHANGED` |
| D2 | `<displayName xsi:nil="true"/>` | Hợp lệ | `CLEAR` |
| D3 | `<displayName/>` | Hợp lệ với `xs:string` không cấm rỗng | `SET("")` |
| D4 | `<displayName>An</displayName>` | Hợp lệ | `SET("An")` |
| D5 | `<displayName xsi:nil="true">An</displayName>` | Không hợp lệ | SOAP Fault/validation error |
| D6 | `<displayName xsi:nil="true"/>` khi XSD không `nillable` | Không hợp lệ | SOAP Fault/validation error |

Các đoạn trong bảng là phần tử con của request, giả định có namespace và cấu trúc cha hợp lệ. Đặc biệt cần xác nhận D1/D2/D3 vẫn khác nhau **sau khi đi qua JAXB**.

### 11.2. Ma trận cho element default/fixed

| Mã ca | Đầu vào | Kỳ vọng khi dùng schema |
|---|---|---|
| E1 | Bỏ `preferredLocale` | Hợp lệ; không tự xuất hiện element |
| E2 | `<preferredLocale/>` | Có giá trị hiệu lực `vi-VN` theo default |
| E3 | `<preferredLocale>en-US</preferredLocale>` | `en-US` được giữ |
| E4 | Bỏ `commandType` khi minOccurs=1 | Không hợp lệ |
| E5 | `<commandType/>` | Có giá trị hiệu lực `UPDATE` theo fixed |
| E6 | `<commandType>DELETE</commandType>` | Không hợp lệ |
| E7 | `<commandType>UPDATE</commandType>` | Hợp lệ |

### 11.3. Ma trận cho attribute default/fixed

| Mã ca | Đầu vào | Kỳ vọng theo XSD/PSVI |
|---|---|---|
| A1 | Không có `priority` | Hợp lệ; default `NORMAL` trong PSVI |
| A2 | `priority="HIGH"` | Hợp lệ; giữ `HIGH` |
| A3 | `priority=""` | Hợp lệ khi kiểu là `xs:string` không hạn chế rỗng; không dùng default |
| A4 | Không có `origin` | Hợp lệ; fixed `CRM` trong PSVI |
| A5 | `origin="CRM"` | Hợp lệ |
| A6 | `origin="ERP"` | Không hợp lệ |

### 11.4. Kiểm tra ngữ nghĩa và tương thích

Ngoài việc assert schema valid/invalid, mỗi ca kiểm thử nên đối chiếu thêm:

- Giá trị và trạng thái **thực tế trong JAXB object**.
- Giá trị và **ý định nghiệp vụ** sau mapping.
- Response SOAP hoặc SOAP Fault được xây đúng version SOAP 1.1/1.2 và đúng contract.
- Tác động khi dùng client sinh từ WSDL khác nhau, ví dụ client Java/JAXB và client .NET.
- Cách client cũ phản ứng nếu schema v2 bổ sung element optional hoặc đổi nillability/default/fixed.

Một test chỉ gọi `new UpdateCustomerRequest()` rồi kiểm tra mapper không thể chứng minh runtime SOAP đã giữ đúng trạng thái XML. Ngược lại, một test chỉ kiểm tra XML valid cũng chưa chứng minh domain service không vô tình biến absent thành clear.

## 12. Những lỗi thiết kế và vận hành thường gặp

### Lỗi 1: Dùng `default` để lấp mọi trường bị bỏ qua

Đặt `minOccurs="0" default="vi-VN"` rồi kỳ vọng server nhận vắng mặt sẽ luôn thấy `vi-VN` là hiểu sai quy tắc element default. Nếu muốn vắng mặt có nghĩa “dùng locale của hệ thống”, ghi rõ ý nghĩa đó trong hợp đồng ứng dụng và thực thi trong service.

### Lỗi 2: Coi `nillable="true"` là optional

`minOccurs="1" nillable="true"` yêu cầu element phải có mặt; chỉ cho phép giá trị nil. Nếu client bỏ hẳn element, request không hợp lệ.

### Lỗi 3: Coi `<x/>` và `xsi:nil="true"` là giống nhau

Với `xs:string`, `<x/>` có thể là chuỗi rỗng. `xsi:nil="true"` là một trạng thái riêng. Nếu API dùng nil để xóa và empty để đặt chuỗi rỗng, việc gom cả hai thành `null` sẽ làm sai chức năng cập nhật.

### Lỗi 4: Mong `fixed` tự bảo vệ dữ liệu khi chưa bật validation

Một đối tượng Java có thể nhận `commandType="DELETE"` mà vẫn được khởi tạo. Nếu không kiểm tra schema, không thể khẳng định chỉ vì trong XSD có `fixed="UPDATE"` mà mọi message sai đã bị chặn.

### Lỗi 5: Quên khác biệt element và attribute

Element default không tạo ra một element bị thiếu; attribute default có thể được bổ sung dưới dạng giá trị PSVI khi attribute nguồn vắng mặt. Hai trường hợp cần kiểm thử khác nhau.

### Lỗi 6: Thay đổi ràng buộc trong cùng namespace mà không đánh giá client cũ

Ví dụ đổi:

~~~xml
<xs:element name="displayName"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

thành:

~~~xml
<xs:element name="displayName"
            type="xs:string"
            minOccurs="1"
            nillable="false"/>
~~~

Đây là thay đổi làm các request từng hợp lệ (vắng mặt hoặc nil) trở nên không hợp lệ. Đối với contract đã công bố, phải coi đây là **thay đổi phá vỡ tương thích** và đánh giá versioning, migration cùng đối tác.

### Lỗi 7: Dùng nil cho mọi trường “không biết”

Một schema có thể hỗ trợ nil, nhưng nghiệp vụ cần phân biệt “không có giá trị”, “không được phép biết” và “xóa giá trị”. Không nên chỉ chọn `nillable=true` vì muốn mọi trường Java nullable; phải quyết định ngữ nghĩa và chính sách dữ liệu.

## 13. Hướng dẫn lựa chọn khi thiết kế XSD mới

Khi thiết kế hợp đồng SOAP, hãy trả lời theo thứ tự:

1. **Field bắt buộc hay không?** Nếu bắt buộc có element, dùng `minOccurs="1"` (mặc định); nếu được bỏ qua, cân nhắc `minOccurs="0"`.
2. **Nếu có element nhưng không có giá trị, cần biểu đạt nil không?** Nếu có ý nghĩa nghiệp vụ rõ, cân nhắc `nillable="true"`. Nếu không, thường giữ `false`.
3. **Giá trị rỗng có hợp lệ không?** Với string, cần xem `minLength` hoặc `pattern`; với kiểu số/ngày, chuỗi rỗng thường không hợp lệ khi không có value constraint.
4. **Có cần giá trị mặc định không?** Hiểu chính xác quy tắc element/attribute và ghi rõ nghiệp vụ có áp dụng mặc định khi field bị bỏ qua hay không.
5. **Có giá trị nào phải bất biến không?** Chỉ dùng `fixed` khi đó là quy tắc hợp đồng thật sự, không phải một gợi ý.
6. **Client Java và client khác Java có nhận cùng semantics không?** Kiểm thử bằng XML fixture thực, không dựa vào tên field trong DTO.
7. **Nếu sau này cần đổi các ràng buộc này, có phá vỡ đối tác không?** Đánh giá tương thích trước khi giữ nguyên namespace hoặc phát hành bản mới.

Một hướng dẫn thực tế cho request cập nhật:

| Yêu cầu nghiệp vụ | Biểu diễn gợi ý |
|---|---|
| Trường bắt buộc và phải có giá trị | `minOccurs=1`, `nillable=false` cùng facet kiểu phù hợp |
| Trường có thể không gửi | `minOccurs=0` |
| Trường có thể gửi nil rõ ràng | `nillable=true` |
| Phân biệt “không sửa”, “xóa”, “đặt giá trị” | `minOccurs=0`, `nillable=true` và mapper bảo toàn presence/nil/value |
| Thuộc tính không gửi thì có giá trị mặc định trong PSVI | `xs:attribute use=optional default=...` |
| Element rỗng có giá trị mặc định XSD | `xs:element default=...` cùng kiểu và constraints thích hợp |
| Giá trị bắt buộc bằng hằng xác định | `fixed=...` và schema validation |

Hãy ghi rõ cách xử lý trong tài liệu hợp đồng để các đối tác không phải suy đoán từ `null` hoặc tên annotation JAXB.

## 14. Ví dụ bài tập thực hành

Một dịch vụ SOAP có operation `UpdateEmployee`, nhận các trường:

- `employeeId`: bắt buộc, không nil.
- `middleName`: không gửi nghĩa là giữ nguyên; nil nghĩa là xóa; chuỗi rỗng là một giá trị cần được kiểm tra nghiệp vụ.
- `language`: optional; khi gửi element rỗng dùng default `vi`; khi không gửi thì áp dụng chính sách “giữ nguyên ngôn ngữ hiện tại”.
- `source`: attribute optional có giá trị cố định `HR_SYSTEM`.

Hãy viết XSD phù hợp, sau đó tạo bốn XML:

1. Chỉ chứa `employeeId`: không thay các trường khác.
2. Có `middleName xsi:nil="true"`: yêu cầu xóa tên đệm.
3. Có `language/>`: giá trị mặc định `vi` theo schema processing.
4. Có `source="OTHER"`: phải bị từ chối vì vi phạm fixed.

Cuối cùng, sinh JAXB binding từ XSD và kiểm tra qua Spring-WS endpoint xem cách unmarshalling có bảo toàn khác biệt absent/nil/empty không. Nếu thiếu, điều chỉnh cách binding/mapping trước khi nối vào domain service.

## 15. Checklist và ghi nhớ

- [ ] Đã phân biệt **element vắng mặt**, **element rỗng**, **element nil**, **element có giá trị**.
- [ ] Không coi `minOccurs=0` là đồng nghĩa với `nillable=true`.
- [ ] Không áp dụng quy tắc default của **attribute** cho **element**.
- [ ] Hiểu `fixed` là ràng buộc giá trị, không phải gợi ý mặc định tùy chọn.
- [ ] Đã kiểm tra kiểu XSD/facets để biết element rỗng có hợp lệ hay không.
- [ ] Đã xem binding JAXB sinh ra có bảo toàn presence/nil hay chỉ trả một `null`.
- [ ] Đã bật schema validation ở ranh giới cần thiết và kiểm tra phản hồi SOAP Fault.
- [ ] Đã kiểm thử với XML fixture đại diện cho từng trạng thái và client độc lập.
- [ ] Đã đánh giá ảnh hưởng khi sửa `minOccurs`, `nillable`, `default` hoặc `fixed` của contract đã công bố.

**Điểm cốt lõi:** XSD phân biệt **cấu trúc**, **trạng thái nil**, **giá trị mặc định** và **giá trị cố định**; JAXB không tự bảo đảm rằng tất cả những ý nghĩa ấy được bảo toàn trong domain object. Khi xây dựng dịch vụ Spring-WS theo hướng contract-first, hãy dùng schema validation, ánh xạ dữ liệu có chủ đích và kiểm thử interoperability để thống nhất cách hiểu giữa client và server.

**Câu hỏi tự kiểm tra:** Vì sao `<language/>` có thể dẫn đến giá trị `vi` nếu XSD khai báo `default="vi"`, còn việc bỏ hẳn `language` khi `minOccurs="0"` lại không tự tạo ra giá trị đó? Khi chuyển qua JAXB, bạn sẽ kiểm chứng và bảo toàn sự khác biệt ấy như thế nào?

