# Giá trị null, phần tử thiếu và trường có giá trị mặc định

Một request SOAP có thể mang trường `note` không xuất hiện, trường `note` xuất hiện nhưng rỗng, hoặc trường `note` chứa `xsi:nil="true"`. Nếu ứng dụng Java đều diễn giải chúng là `null`, hệ thống có thể mất thông tin mà đối tác cố ý gửi. Ngược lại, khi chuyển đối tượng Java thành XML, một property `null` có thể được **bỏ hẳn** hoặc xuất thành **phần tử nil**, tùy hợp đồng XSD và cấu hình JAXB. Đây là nguyên nhân phổ biến của lỗi tương thích trong những thao tác tạo/cập nhật dữ liệu.

Bài học thuộc chương **Marshalling và OXM** của module **SPRING_WEB_SERVICES**. Module hướng đến phát triển dịch vụ SOAP **contract-first** bằng Spring Web Services (Spring-WS): thiết kế XSD/WSDL, sinh/ánh xạ JAXB, endpoint và SOAP client, rồi xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Trong chuỗi đó, bài này tập trung vào **giá trị thiếu, `null`, rỗng, `xsi:nil`, mặc định (default) và cố định (fixed)** ở cả ba tầng: **XML Schema**, **Java object** và **SOAP message thực tế**.

## 1. Cần phân biệt bốn trạng thái XML

Giả sử schema có một phần tử `note` thuộc namespace `urn:example:orders:v1`. Bốn cách biểu diễn cần phân biệt:

~~~xml
<!-- 1. Vắng mặt: không có thẻ note nào trong request -->

<!-- 2. Có phần tử nhưng nội dung rỗng -->
<ord:note xmlns:ord="urn:example:orders:v1"/>

<!-- 3. Phần tử được đánh dấu nil rõ ràng -->
<ord:note xmlns:ord="urn:example:orders:v1"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:nil="true"/>

<!-- 4. Có giá trị -->
<ord:note xmlns:ord="urn:example:orders:v1">Gọi trước khi giao</ord:note>
~~~

| Trạng thái | XML instance | Ý nghĩa thường dùng trong hợp đồng | Khả năng biểu diễn trong Java |
| --- | --- | --- | --- |
| **Absent** (thiếu) | Không có `note` | Bên gửi không cung cấp trường này | `null`, hoặc property wrapper không tồn tại |
| **Empty** (rỗng) | `<note/>` hoặc `<note></note>` | Có trường, nhưng chuỗi rỗng | `""` nếu kiểu là `String` |
| **Nilled** (nil) | `<note xsi:nil="true"/>` | Bên gửi đánh dấu rõ nội dung là nil | `null` kèm trạng thái “phần tử có mặt”, ví dụ qua `JAXBElement` |
| **Value** (có nội dung) | `<note>abc</note>` | Bên gửi truyền giá trị | `"abc"` hoặc Java type tương ứng |

**Không thể tự ý coi bốn trạng thái là như nhau.** Ví dụ ở một API cập nhật:

- Không có `note`: **không thay đổi** ghi chú đã lưu.
- `note` rỗng: **đặt ghi chú thành chuỗi rỗng**.
- `note xsi:nil="true"`: **xóa giá trị ghi chú** hoặc ghi `null` trong cơ sở dữ liệu.
- `note` có text: **cập nhật ghi chú mới**.

Đây chỉ là **quy ước nghiệp vụ minh họa**. XSD xác định những trạng thái nào hợp lệ, còn ý nghĩa “giữ nguyên”, “xóa” hay “cập nhật” cần được mô tả trong contract nghiệp vụ; SOAP và JAXB không tự quyết định hộ ứng dụng.

## 2. XSD kiểm soát sự có mặt và khả năng nil bằng hai trục riêng

Hai thuộc tính quan trọng nhất là:

- **`minOccurs`**: số lần phần tử phải xuất hiện tối thiểu trong vị trí đang khai báo. Với một phần tử cục bộ trong `xs:sequence`, `minOccurs="0"` cho phép **vắng mặt**; mặc định khi không khai báo thường là `1`.
- **`nillable`**: cho phép phần tử **đã xuất hiện** được đánh dấu `xsi:nil="true"` hay không. Mặc định là `false`.

Chúng **độc lập**: một trường có thể bắt buộc hiện diện nhưng được phép nil, hoặc tùy chọn xuất hiện nhưng cấm nil.

| Khai báo XSD | Thiếu phần tử | Có `xsi:nil="true"` | Có giá trị đúng kiểu |
| --- | --- | --- | --- |
| `minOccurs="1" nillable="false"` | Không hợp lệ | Không hợp lệ | Hợp lệ |
| `minOccurs="0" nillable="false"` | Hợp lệ | Không hợp lệ | Hợp lệ |
| `minOccurs="1" nillable="true"` | Không hợp lệ | Hợp lệ | Hợp lệ |
| `minOccurs="0" nillable="true"` | Hợp lệ | Hợp lệ | Hợp lệ |

Ngoài bảng trên, **phần tử rỗng có hợp lệ hay không còn phụ thuộc kiểu dữ liệu**. `<note/>` có thể hợp lệ với `xs:string`, nhưng `<quantity/>` thường không hợp lệ nếu kiểu là `xs:int` và không có default thích hợp. Một thẻ tự đóng `<note/>` **không tương đương** `<note xsi:nil="true"/>`.

### `xsi:nil` là một thuộc tính của instance XML

Khai báo schema:

~~~xml
<xs:element name="discountCode"
            type="xs:string"
            minOccurs="0"
            nillable="true"/>
~~~

Ví dụ instance hợp lệ:

~~~xml
<ord:discountCode
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Khi `xsi:nil="true"`, phần tử phải **không có nội dung phần tử/text** theo các ràng buộc của XML Schema. Điều này không đồng nghĩa thuộc tính nào khác cũng bị cấm trong mọi trường hợp: với complex type phù hợp, thuộc tính được cho phép vẫn có thể xuất hiện. Tuy vậy, trong payload SOAP nghiệp vụ thông thường, hãy dùng một phần tử nil trống và tránh tự thêm thuộc tính ngoài hợp đồng.

Đặt `xsi:nil="true"` lên phần tử không khai báo `nillable="true"` là lỗi XSD. Nếu schema yêu cầu `minOccurs="1"`, việc bỏ hẳn phần tử cũng là lỗi dù phía Java có cho property bằng `null`.

## 3. Ví dụ xuyên suốt: OrderUpdateRequest

Một hệ thống SOAP nhận yêu cầu cập nhật đơn hàng. Bốn loại dữ liệu được lựa chọn để minh họa các ràng buộc khác nhau:

1. `orderId` bắt buộc, không nil.
2. `note` tùy chọn, không nil.
3. `discountCode` tùy chọn, có thể nil.
4. `priority` tùy chọn, có **default**; attribute `source` có **default** và `schemaRevision` có **fixed**.

XSD mẫu `orders.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="PriorityType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="LOW"/>
            <xs:enumeration value="NORMAL"/>
            <xs:enumeration value="HIGH"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="OrderUpdateRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="note" type="xs:string"
                            minOccurs="0"/>
                <xs:element name="discountCode" type="xs:string"
                            minOccurs="0" nillable="true"/>
                <xs:element name="priority" type="ord:PriorityType"
                            minOccurs="0" default="NORMAL"/>
            </xs:sequence>
            <xs:attribute name="source" type="xs:string"
                          default="WEB"/>
            <xs:attribute name="schemaRevision" type="xs:string"
                          fixed="1"/>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Schema này sử dụng **global element** `OrderUpdateRequest` trong namespace `urn:example:orders:v1`; các local elements cũng được qualified nhờ `elementFormDefault="qualified"`. Hai attribute `source` và `schemaRevision` **không tự động được qualified** bởi `elementFormDefault`; ở ví dụ này chúng **không có namespace**, vì `attributeFormDefault` mặc định là unqualified.

Một payload hợp lệ:

~~~xml
<ord:OrderUpdateRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    source="MOBILE">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:note/>
    <ord:discountCode xsi:nil="true"/>
    <ord:priority/>
</ord:OrderUpdateRequest>
~~~

Giải thích:

- `note` **có mặt**, mang chuỗi rỗng.
- `discountCode` **có mặt** và nil, khác với việc thiếu hẳn.
- `priority` **có mặt nhưng rỗng**; theo XML Schema, default `NORMAL` có thể được áp dụng trong giá trị đã chuẩn hóa sau schema validation.
- `source="MOBILE"` đã có giá trị tường minh nên default `WEB` không thay thế nó.
- `schemaRevision` không xuất hiện; theo quy tắc default/fixed của attribute trong XML Schema, giá trị cố định `1` có thể được cung cấp trong thông tin sau validation.

Hợp lệ về XSD **không có nghĩa** dữ liệu nghiệp vụ hợp lệ: ứng dụng vẫn cần xác minh người gọi được phép cập nhật đơn `ORD-1024`, mã giảm giá có thể bị xóa hay không, và mức ưu tiên có được phép chỉnh sửa hay không.

## 4. Default của element khác default của attribute

Đây là ranh giới hay bị hiểu sai nhất.

### 4.1. Element default: áp dụng khi phần tử có mặt nhưng rỗng

Với khai báo:

~~~xml
<xs:element name="priority" type="ord:PriorityType"
            minOccurs="0" default="NORMAL"/>
~~~

Hãy so sánh:

| XML trong `OrderUpdateRequest` | XSD cho phép? | Giá trị mặc định có được xét áp dụng? |
| --- | --- | --- |
| **Không có** `priority` | Có, vì `minOccurs="0"` | **Không.** XSD không tự chèn một phần tử bị thiếu |
| `<ord:priority/>` | Có | **Có.** Element tồn tại nhưng rỗng nên default `NORMAL` được dùng trong xử lý schema |
| `<ord:priority>NORMAL</ord:priority>` | Có | Không cần áp dụng vì giá trị đã có |
| `<ord:priority>HIGH</ord:priority>` | Có | Không thay `HIGH` bằng `NORMAL` |
| `<ord:priority>URGENT</ord:priority>` | Không | Giá trị không thuộc enumeration |
| `<ord:priority xsi:nil="true"/>` | Không | `priority` không khai báo nillable |

Điểm quan trọng: **`default="NORMAL"` không có nghĩa “nếu người gọi bỏ trường đi thì server tự nhận NORMAL” ở mức XML Schema.** XSD xử lý phần tử rỗng và phần tử thiếu khác nhau. Nếu ứng dụng muốn gán default cho trường **không hiện diện**, hãy định nghĩa rõ chính sách ở service hoặc mapper và kiểm thử bằng input thiếu thật.

XML Schema mô tả giá trị schema-normalized (sau validation), không nhất thiết thay đổi literal text trong tài liệu XML gốc. Việc đối tượng JAXB cuối cùng có giá trị gì còn phụ thuộc binding, cách unmarshalling và cấu hình schema validation.

### 4.2. Attribute default: áp dụng khi attribute vắng mặt

Với khai báo:

~~~xml
<xs:attribute name="source" type="xs:string" default="WEB"/>
~~~

- `source="MOBILE"` → giá trị `MOBILE`.
- Không có attribute `source` → giá trị mặc định `WEB` trong kết quả xử lý XSD/PSVI.
- `source=""` → chuỗi rỗng **đã được cung cấp**, không bị thay bằng `WEB` với kiểu `xs:string` này.

**Khác biệt:** default của **element** được dùng khi element **rỗng nhưng có mặt**; default của **attribute** được dùng khi attribute **không có mặt**. Không chuyển quy tắc của attribute sang element.

### 4.3. `fixed`: giá trị bị ràng buộc, không chỉ là gợi ý mặc định

Khai báo:

~~~xml
<xs:attribute name="schemaRevision" type="xs:string" fixed="1"/>
~~~

Nếu attribute được cung cấp, giá trị phải là `"1"`. Nếu không có, schema processor có thể cung cấp giá trị cố định trong thông tin sau validation tương tự cách xử lý default cho attribute tùy chọn. `schemaRevision="2"` sẽ vi phạm schema.

Với **element** có `fixed`, phần tử hiện diện phải mang giá trị cố định; element rỗng có thể lấy giá trị đó theo quy tắc XML Schema. `fixed` cũng khác default ở chỗ **cấm giá trị khác**. Không khai báo đồng thời `default` và `fixed` trên cùng một element/attribute.

### 4.4. `xsi:nil` không phải nút kích hoạt default

Một element nilled có nghĩa nội dung của nó được đánh dấu là nil; **không xử lý như một element rỗng để gán default**. Ngoài ra, phần tử có fixed value không được nilled theo quy tắc XSD. Nếu muốn có trạng thái “không biết” bên cạnh mức ưu tiên mặc định, thiết kế schema cần mô tả rõ, thay vì lợi dụng `xsi:nil` để kỳ vọng default tự chạy.

## 5. JAXB/OXM chuyển các trạng thái XML sang Java như thế nào?

**Marshalling** là chuyển object → XML; **unmarshalling** là XML → object. **OXM** (Object/XML Mapping) trong Spring cung cấp các abstraction như `Marshaller`, `Unmarshaller`; `Jaxb2Marshaller` là một implementation dùng JAXB.

~~~mermaid
flowchart LR
    XML["SOAP Body payload<br/>XML instance"] -->|"unmarshal"| J["JAXB model<br/>String / enum / JAXBElement"]
    J -->|"application mapping"| D["DTO / domain state"]
    D -->|"response mapping"| R["JAXB response model"]
    R -->|"marshal"| OUT["SOAP Body response"]
    XSD["XSD<br/>minOccurs, nillable,<br/>default, fixed"] -.-> XML
    XSD -.-> OUT
~~~

Java `null` bản thân chỉ nói “reference chưa trỏ tới object”. Nó **không mang sẵn** thông tin XML element có bị thiếu hay đã xuất hiện với `xsi:nil="true"`. Với `String`, một property có thể nhận cả `null` và `""`, nhưng sẽ không biểu diễn được cả ba trạng thái absent/nil/empty nếu không có metadata bổ sung.

### 5.1. Các cách JAXB thường biểu diễn property

| Mô hình Java | Thông tin có thể giữ lại | Giới hạn |
| --- | --- | --- |
| `String note` | `null` so với `""` so với giá trị text | `null` một mình không tách absent và nil |
| `Integer quantity` | `null` so với một số nguyên | Không tự thể hiện element nil/absent riêng biệt |
| `int quantity` | Luôn có một giá trị nguyên Java | Không thể biểu diễn null; primitive default `0` có thể che việc thiếu |
| `JAXBElement<String> discountCode` | Wrapper **có hay không**, `isNil()` và `getValue()` | Phải quản lý đúng QName và element declaration |
| Optional flags/mô hình riêng trong adapter | Lưu rõ `present`, `nil`, `value` | Cần code ánh xạ và quy ước nghiệp vụ tường minh |

**XJC không nhất thiết sinh cùng một hình dạng Java cho mọi XSD.** Chẳng hạn optional+nillable có thể được biểu diễn bằng `JAXBElement<T>` trong nhiều trường hợp; schema, global/local element, external binding và phiên bản công cụ quyết định class thực tế. Luôn đọc generated `ObjectFactory` và annotations thay vì đoán.

### 5.2. `JAXBElement<T>` giữ được danh tính và trạng thái phần tử

`JAXBElement<T>` chứa:

- `QName name`: element thuộc namespace/local name nào.
- `declaredType` và `scope`: loại và phạm vi khai báo element.
- `value`: giá trị nội dung; có thể `null`.
- `isNil()`: trạng thái nội dung nil.

Với một generated property kiểu `JAXBElement<String>`, ta có thể kiểm tra:

~~~java
JAXBElement<String> code = request.getDiscountCode();

if (code == null) {
    // Không có wrapper: element không hiện diện theo binding này.
} else if (code.isNil()) {
    // Element đã xuất hiện ở trạng thái xsi:nil="true".
} else if (code.getValue().isEmpty()) {
    // Element hiện diện, String có nội dung rỗng.
} else {
    // Element hiện diện, có text khác rỗng.
    String actualCode = code.getValue();
}
~~~

Đoạn trên chỉ thích hợp khi **generated getter thật sự trả `JAXBElement<String>`** và dữ liệu thỏa hợp đồng. Theo API `JAXBElement`, nếu `getValue()==null` thì `isNil()` là true; với một số complex type, nilled element vẫn có thể giữ các thuộc tính theo quy tắc JAXB. Vì vậy hãy kiểm tra `isNil()` thay vì coi `null` của wrapper và `null` của value là cùng một trạng thái.

Để tạo thông điệp đầu ra, thường dùng các factory method trong `ObjectFactory` được sinh bởi XJC, thay vì tự tạo `QName` không khớp scope. Mã ý tưởng:

~~~java
// Chỉ là minh họa. Tên factory phụ thuộc XSD và công cụ XJC.
ObjectFactory factory = new ObjectFactory();

request.setDiscountCode(null); // Bỏ phần tử (absent).

request.setDiscountCode(
    factory.createOrderUpdateRequestDiscountCode(null)
); // Phần tử có mặt, nil.

request.setDiscountCode(
    factory.createOrderUpdateRequestDiscountCode("")
); // Phần tử có mặt, chuỗi rỗng.
~~~

Factory method giả định chỉ tồn tại nếu XJC sinh ra dạng property đó; không sửa generated class để ép có một phương thức tên cụ thể. Kiểm chứng XML marshal, đặc biệt `xmlns`, `xsi:nil` và thứ tự theo `xs:sequence`.

### 5.3. `@XmlElement` và các giới hạn của annotation

Trong Java class do XJC sinh, bạn có thể gặp:

~~~java
// Các đoạn annotation minh họa, không phải bản sinh cố định.
@XmlElement(name = "orderId", required = true)
protected String orderId;

@XmlElement(name = "note")
protected String note;

@XmlElement(name = "priority", defaultValue = "NORMAL")
protected PriorityType priority;
~~~

`@XmlElement.required` và `nillable` mô tả binding/schema-related metadata. Chúng **không thay thế validator XSD** khi unmarshalling/marshalling. Ví dụ, việc có `required=true` không bảo đảm một setter Java tự ném exception nếu bạn gán `null`.

`@XmlElement(defaultValue="NORMAL")` biểu diễn thông tin default của element cho JAXB. Nó **không giống** khởi tạo field Java bằng `= PriorityType.NORMAL`; cũng không bảo đảm mọi cách xử lý input thiếu đều tự tạo ra một phần tử hoặc object Java có giá trị này. Phải kiểm thử XML **vắng mặt** và XML **có thẻ rỗng** riêng.

## 6. Marshalling: Java null tạo ra XML nào?

Không thể trả lời chính xác chỉ từ `null`. Cần biết **element declaration + annotation + wrapper + cấu hình marshaller**.

| Property Java trước khi marshal | Binding điển hình | XML thường tạo | Cần kiểm tra |
| --- | --- | --- | --- |
| `note = null` | Optional, `nillable=false` | Không có `note` | Có đúng quy tắc giữ nguyên dữ liệu không? |
| `note = ""` | `String` optional | `<note/>` hoặc open/close rỗng | Có khác biệt với absent không? |
| `discountCode = null` | Property dạng `JAXBElement` | Không có element | Wrapper null có đại diện absent không? |
| `discountCode` là wrapper, `isNil=true` | Optional và nillable | `<discountCode xsi:nil="true"/>` | XSD có nillable và client hiểu nil không? |
| `discountCode` là wrapper chứa `""` | String, non-nil | `<discountCode/>` | Không bị đổi thành nil chứ? |
| `priority = null` | Optional, không nillable | Thường bỏ phần tử | Không được nhầm với default `NORMAL` |
| `priority = NORMAL` | Enum có giá trị | `<priority>NORMAL</priority>` | Đúng namespace, sequence và lexical enum? |

“Thường” ở bảng là mô hình phổ biến, **không phải cam kết thay cho kiểm thử với JAXB provider thực tế**. Đặc biệt nếu class dùng `@XmlElement(nillable=true)` trực tiếp trên một property nullable, marshaller có thể xuất **nil element** thay vì bỏ. Sự khác biệt giữa property Java dạng `String` và `JAXBElement<String>` rất đáng quan tâm.

### Vì sao có thể marshal XML sai XSD dù code Java hợp lệ?

Hãy xét schema:

~~~xml
<xs:element name="orderId" type="xs:string"
            minOccurs="1" nillable="false"/>
~~~

Với một generated Java class có setter `setOrderId(null)`, nhiều runtime JAXB **không tự chặn tại thời điểm gán**. Nếu marshaller bỏ `orderId`, XML đầu ra sẽ sai XSD. Vì vậy cần validation khi sinh XML và kiểm thử negative case, nhất là với request gửi cho đối tác có validator chặt.

Ngoài ra, **Java default của primitive** có thể che lỗi:

~~~java
private int quantity; // Giá trị mặc định của Java là 0.
~~~

Nếu input thiếu `quantity` và binding dùng primitive, Java object có thể giữ `0` mà không thể biết chắc bên gửi thực sự gửi `0` hay không gửi phần tử. XJC thường có quy tắc dùng wrapper cho primitive tùy chọn, nhưng cần xem lớp được sinh. Đối với API cập nhật theo từng trường, hãy dùng mô hình giữ rõ presence khi cần.

## 7. Unmarshalling: XML trống, thiếu, nil và default trong Java

Không nên giả định unmarshalling và schema validation là cùng một thao tác. **Unmarshaller có thể chuyển XML thành object mà không kiểm tra toàn bộ ràng buộc XSD.** Ngược lại, schema validator xác nhận XML hợp schema nhưng không phải công cụ nghiệp vụ hiểu ý nghĩa từng trường.

Ví dụ bốn request riêng biệt:

~~~xml
<!-- A: discountCode vắng mặt -->
<ord:OrderUpdateRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
</ord:OrderUpdateRequest>
~~~

~~~xml
<!-- B: discountCode có mặt nhưng rỗng -->
<ord:OrderUpdateRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:discountCode/>
</ord:OrderUpdateRequest>
~~~

~~~xml
<!-- C: discountCode nil -->
<ord:OrderUpdateRequest
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:discountCode xsi:nil="true"/>
</ord:OrderUpdateRequest>
~~~

~~~xml
<!-- D: discountCode có giá trị -->
<ord:OrderUpdateRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>ORD-1024</ord:orderId>
    <ord:discountCode>WELCOME</ord:discountCode>
</ord:OrderUpdateRequest>
~~~

Nếu generated property là `JAXBElement<String>`, một binding phù hợp có thể giữ các trạng thái A/B/C/D. Nếu JAXB dùng property `String` thông thường, trạng thái A và C có thể đều trở thành `null`. Tính đúng đắn của nghiệp vụ phụ thuộc vào việc bạn **chọn binding giữ đủ thông tin cần thiết**.

### Giá trị mặc định được áp dụng ở giai đoạn nào?

Có ba lớp cần phân biệt:

1. **XSD schema processing:** quy định default của element/attribute cho giá trị hậu validation (PSVI), với quy tắc khác nhau về absent và empty.
2. **JAXB binding/runtime:** có thể sử dụng metadata như `@XmlElement(defaultValue)` và cách mapping của provider để gán giá trị Java trong trường hợp được hỗ trợ; hiệu ứng thực tế phụ thuộc cấu hình và kiểu nguồn.
3. **Business defaulting:** ứng dụng tự quy định, chẳng hạn “nếu request không có priority thì đặt NORMAL” hoặc “nếu thiếu thì giữ priority hiện có”.

Không thay thế (3) bằng kỳ vọng mơ hồ rằng (1) hoặc (2) đã gán mọi default. Điều này đặc biệt nguy hiểm với **partial update**, khi absence có nghĩa “không chỉnh trường này”.

## 8. JAXB validation và Spring OXM

Trong Spring, `Jaxb2Marshaller` được dùng cả ở phía SOAP endpoint và SOAP client. Một cấu hình tối thiểu:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class XmlMappingConfig {
    @Bean
    public Jaxb2Marshaller ordersMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
        marshaller.setContextPath("org.example.orders.v1");
        marshaller.setSchema(new ClassPathResource("xsd/orders.xsd"));
        return marshaller;
    }
}
~~~

Giả định `org.example.orders.v1` là package JAXB thực sự được sinh từ XSD, và `orders.xsd` có thể được nạp cùng tất cả schema phụ thuộc. `setSchema(...)` đưa schema vào cấu hình JAXB marshaller/unmarshaller của Spring; cần kiểm thử version và luồng gọi cụ thể để xác nhận validation hoạt động đúng như mong muốn. Nếu schema dùng `xs:include`/`xs:import`, phải bảo đảm resolver và đường dẫn import hợp lệ, không mở truy cập tài nguyên không đáng tin cậy.

Ở tầng SOAP message, Spring-WS cũng có cơ chế **`PayloadValidatingInterceptor`** để kiểm tra payload request/response theo XSD khi cấu hình. Hai lựa chọn kiểm tra ở **những vị trí khác nhau**; không bật trùng một cách vô thức nếu hiệu năng và thông báo lỗi cần được kiểm soát.

### XML Schema kiểm tra, JAXB chuyển đổi, service quyết định nghiệp vụ

~~~mermaid
flowchart TD
    A["SOAP Body<br/>XML request"] --> B["Kiểm tra SOAP/WS-Security<br/>theo cấu hình"]
    B --> C["XSD validation<br/>minOccurs, nillable, default/fixed"]
    C --> D["JAXB unmarshal<br/>Java property / JAXBElement"]
    D --> E["Adapter chuyển trạng thái<br/>absent / nil / empty / value"]
    E --> F["Domain logic<br/>giữ nguyên / xóa / cập nhật"]
    F --> G["JAXB marshal response"]
    G --> H["Kiểm tra XSD outbound<br/>nếu cấu hình"]
    H --> I["SOAP response / Fault"]
~~~

Đây là sơ đồ **trách nhiệm**, không phải cam kết thứ tự interceptor bất biến cho mọi Spring-WS deployment. Trong hệ thống có WS-Security, việc xác minh chữ ký, giải mã, kiểm tra timestamp và chọn thời điểm validation phải được thiết kế theo chính sách bảo mật thực tế.

### Ví dụ ánh xạ update có giữ thông tin trạng thái

Thay vì truyền một `String discountCode` nullable vào domain service và hy vọng nó tự hiểu:

~~~java
public sealed interface FieldUpdate<T>
        permits FieldUpdate.Unspecified, FieldUpdate.Clear, FieldUpdate.Set {

    record Unspecified<T>() implements FieldUpdate<T> {}
    record Clear<T>() implements FieldUpdate<T> {}
    record Set<T>(T value) implements FieldUpdate<T> {}
}
~~~

Đây là ví dụ dùng **Java 17+**; với Java cũ hơn có thể dùng enum + DTO thông thường. Adapter đọc `JAXBElement<String>` và chuyển thành một trong ba ý định:

~~~java
static FieldUpdate<String> mapDiscount(JAXBElement<String> element) {
    if (element == null) {
        return new FieldUpdate.Unspecified<>();
    }
    if (element.isNil()) {
        return new FieldUpdate.Clear<>();
    }
    return new FieldUpdate.Set<>(element.getValue());
}
~~~

Ở đây `Set<>("")` có ý nghĩa **đặt chuỗi rỗng**; cần xác định trong nghiệp vụ có cho phép mã giảm giá rỗng hay không. Nếu không, service/validator có thể báo lỗi hợp đồng/nghiệp vụ thay vì lặng lẽ đổi `""` thành nil.

**Khi nào nên làm vậy?** Với những operation có ngữ nghĩa partial update hoặc patch, khả năng phân biệt “không gửi”, “xóa” và “đặt giá trị” đặc biệt quan trọng. Với một request đọc dữ liệu đơn giản chỉ yêu cầu toàn bộ trường bắt buộc, mô hình Java có thể đơn giản hơn.

## 9. Giá trị mặc định phía Java không làm đổi hợp đồng XML

Đôi khi developer viết:

~~~java
private PriorityType priority = PriorityType.NORMAL;
~~~

Nếu đây là lớp generated, thay đổi có thể mất sau lần sinh XJC tiếp theo. Ngoài ra, field initializer Java có thể khiến request XML thiếu `priority` được xem như có `NORMAL` ở object ngay khi unmarshal, dù XSD **không tự thêm element bị thiếu**. Điều này có thể được mong muốn ở operation create, nhưng phá vỡ partial update.

Tương tự, constructor, builder, Jackson default hoặc database default **không tự động trở thành XML Schema default**. Các tầng mặc định cần được mô tả riêng:

| Tầng | Ví dụ | Có tác động vào tài liệu XML ban đầu? |
| --- | --- | --- |
| **XSD element default** | `priority default="NORMAL"` | Dùng cho phần tử có mặt nhưng rỗng trong xử lý schema; không tự thêm phần tử thiếu |
| **XSD attribute default** | `source default="WEB"` | Giá trị sau xử lý schema khi attribute vắng mặt; không nhất thiết sửa literal input |
| **JAXB annotation/binding** | `@XmlElement(defaultValue="NORMAL")` | Hướng dẫn mapping của runtime; cần kiểm tra kết quả |
| **Java initializer** | `priority = NORMAL` | Trạng thái object Java; không thay đổi XSD |
| **Business default** | “Không gửi priority → NORMAL khi tạo đơn” | Quy tắc nghiệp vụ cần test riêng |
| **Database default** | Default ở cột lưu trữ | Chỉ có tác dụng ở thao tác lưu phù hợp, không định nghĩa SOAP request |

Để tránh “ngầm hiểu” giữa các hệ thống, với mỗi trường có default cần trả lời: **default xảy ra khi absent, khi empty hay cả hai?**; **xảy ra ở phía client, server hay database?**; **giá trị này có được thể hiện lại trong response không?**

## 10. SOAP endpoint và SOAP Fault khi nhận dữ liệu thiếu

Spring-WS thường chọn endpoint theo QName phần tử gốc của SOAP Body:

~~~java
@Endpoint
public class OrderUpdateEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderService service;

    public OrderUpdateEndpoint(OrderService service) {
        this.service = service;
    }

    @PayloadRoot(namespace = NS, localPart = "OrderUpdateRequest")
    @ResponsePayload
    public OrderUpdateResponse update(
            @RequestPayload OrderUpdateRequest request) {
        // Adapter phân biệt absent, nil và empty trước khi gọi domain.
        return service.applyUpdate(request);
    }
}
~~~

Đoạn trên minh họa endpoint, giả định lớp JAXB `OrderUpdateRequest` và `OrderUpdateResponse`, service, imports và cấu hình Spring-WS đã tồn tại. Không nên đồng nhất **SOAP Body rỗng/thiếu root** với **một trường con optional bị thiếu**: thiếu root có thể khiến endpoint không được dispatch, còn thiếu trường con được đánh giá theo XSD và logic nghiệp vụ.

Các trường hợp sai cần phân loại:

| Request | Phân loại lỗi thường thích hợp |
| --- | --- |
| Bỏ `orderId` bắt buộc | XSD validation lỗi |
| `discountCode xsi:nil="true"` với schema cho phép | Không phải lỗi XSD; nghiệp vụ có thể quyết định xóa |
| `note xsi:nil="true"` khi `nillable=false` | XSD validation lỗi |
| `priority=URGENT` ngoài enum | XSD validation lỗi |
| `priority` vắng mặt trong partial update | Hợp schema; ứng dụng định nghĩa giữ nguyên hay dùng default |
| SOAP Body có root QName không được hỗ trợ | Lỗi dispatch/contract ở tầng SOAP endpoint |

Với SOAP service, các exception thích hợp có thể được chuyển thành **SOAP Fault** qua Spring-WS exception resolver hoặc interceptor, theo version SOAP và chính sách của hợp đồng. Không trả một stack trace Java hay JSON error body không thuộc giao thức SOAP cho client SOAP.

**SOAP Fault và lỗi schema không đồng nghĩa:** một request hợp XSD vẫn có thể bị từ chối vì quyền truy cập, nghiệp vụ hoặc WS-Security. Khi báo lỗi, hạn chế chi tiết nội bộ nhưng cung cấp mã lỗi có thể xử lý theo hợp đồng đã thống nhất.

## 11. Kiểm thử từng trạng thái thay vì một happy path

Một test round-trip “marshal rồi unmarshal vẫn bằng nhau” có ích nhưng **không đủ**: nếu cả hai chiều cùng làm mất khác biệt absent/nil, test vẫn có thể xanh. Cần viết test theo **XML input cố định** và khẳng định trạng thái Java, sau đó kiểm tra chiều Java → XML riêng.

### Ma trận kiểm thử đề xuất

| Tình huống | XML hoặc Java input | Kết quả kỳ vọng |
| --- | --- | --- |
| Trường bắt buộc có giá trị | `<orderId>ORD-1024</orderId>` | PASS XSD; Java có ID |
| Trường bắt buộc bị thiếu | Không có `orderId` | FAIL XSD khi bật validation |
| Optional không nil bị thiếu | Không có `note` | PASS; mapper biết absent |
| Optional không nil rỗng | `<note/>` | PASS nếu `xs:string`; Java giữ `""` |
| Optional không nil được đánh dấu nil | `<note xsi:nil="true"/>` | FAIL XSD |
| Optional+nillable bị thiếu | Không có `discountCode` | PASS; wrapper không hiện diện theo binding tương ứng |
| Optional+nillable rỗng | `<discountCode/>` | PASS; phải phân biệt với nil |
| Optional+nillable có nil | `<discountCode xsi:nil="true"/>` | PASS; wrapper nil theo binding phù hợp |
| Optional+nillable có giá trị | `<discountCode>WELCOME</discountCode>` | PASS; Java giữ đúng text |
| Element default vắng mặt | Không có `priority` | PASS; XSD **không thêm phần tử** |
| Element default rỗng | `<priority/>` | Default `NORMAL` theo XSD; kiểm tra mapping JAXB thực tế |
| Element default có giá trị hợp lệ | `<priority>HIGH</priority>` | Giữ `HIGH` |
| Attribute default vắng mặt | Không có `source` | Default `WEB` trong xử lý schema; kiểm tra JAXB |
| Attribute fixed sai | `schemaRevision="2"` | FAIL XSD |
| Sai namespace | `<priority>` không thuộc `urn:example:orders:v1` | FAIL XSD hoặc không map đúng |

### Gợi ý kiểm thử bằng Spring-WS

- **`MockWebServiceClient`** kiểm tra SOAP endpoint nhận XML cố định, trả đúng payload/Fault, đặc biệt khi dữ liệu bắt buộc bị thiếu.
- **`MockWebServiceServer`** kiểm tra SOAP client dùng `WebServiceTemplate` marshal thành XML có phân biệt absent/nil/empty và xử lý response phù hợp.
- Với các cấu hình **`Jaxb2Marshaller`**, tạo test riêng cho cả bật và tắt schema validation để xác định rõ hành vi; đừng nhầm một runtime có validation với một runtime chỉ unmarshal.
- Với XSD có `xs:include`/`xs:import`, chạy test từ artifact đóng gói để chắc chắn resolve được schema dependency.
- Khi tích hợp với hệ thống .NET, ESB hoặc công cụ SOAP độc lập, dùng chính WSDL/XSD phát hành và các mẫu XML này để xác nhận hai phía diễn giải giống nhau.

### Kiểm tra XML theo cấu trúc

Không chỉ so sánh string `"<note/>"` với `"<note></note>"`: hai cách viết có thể biểu diễn cùng phần tử rỗng. Cũng đừng coi thay prefix `ord` thành `o` là đổi QName nếu namespace URI giữ nguyên. Hãy kiểm tra bằng parser XML hiểu namespace, XSD validation và assertion về trạng thái nil/element presence.

Riêng test chữ ký SOAP cần dùng chuẩn canonicalization và chính sách bảo mật đã chọn; không nên thay việc kiểm tra WS-Security bằng so sánh chuỗi XML.

## 12. Các bẫy khi thay đổi hợp đồng

Thay đổi một annotation Java không đủ để bảo đảm client cũ còn tương thích. Với contract-first, cần xét **XSD, generated JAXB, WSDL và XML trên dây**.

| Thay đổi XSD | Rủi ro | Điều cần làm |
| --- | --- | --- |
| `minOccurs="1"` → `0` | Client/server không thống nhất về vắng mặt | Test input thiếu và cơ chế default nghiệp vụ |
| `nillable="false"` → `true` | Bên nhận cũ có thể không xử lý nil | Test SOAP client cũ và định nghĩa clear semantics |
| `nillable="true"` → `false` | Payload nil trước đây hợp lệ trở thành lỗi | Đánh giá breaking change |
| Thêm `default="NORMAL"` | Đầu vào element rỗng có ngữ nghĩa khác | So sánh absent/empty có validation và không validation |
| Đổi default của attribute | Khi attribute thiếu, thông tin sau validation đổi | Test behavior và config clients |
| Đổi kiểu `String` → `Integer` | Empty string không còn hợp lệ như trước | Test serialization và xử lý lỗi |
| Đổi namespace v1 → v2 | QName của payload thay đổi | Cập nhật WSDL, JAXB binding, endpoint mapping, quản lý version |
| Đổi `fixed` hoặc enum | Các giá trị trước đây được phép có thể bị từ chối | Thử client đã triển khai |

Đặc biệt, **thêm một field optional** chưa chắc luôn an toàn nếu phía nhận dùng schema validation rất chặt hoặc generated bindings không bỏ qua element lạ. Hãy kiểm tra với client thực tế trước khi kết luận là backward-compatible.

## 13. Bảo mật XML và WS-Security khi xử lý null/nil

Trạng thái nil và các XML attributes là **dữ liệu từ bên ngoài**, không phải dấu hiệu rằng request đã được xác thực.

- XML parser/unmarshaller phải xử lý input không đáng tin cậy với giới hạn kích thước, số phần tử và cơ chế chống **XXE/DTD hoặc external entities** phù hợp. XSD validation không thay thế các giới hạn tài nguyên này.
- Với **WS-Security**, SOAP Body có thể nằm trong vùng được ký. Thay `<note/>` thành `<note xsi:nil="true"/>` hoặc thêm phần tử mặc định **sau khi ký** có thể làm chữ ký không còn hợp lệ.
- Nếu service xác minh chữ ký trước khi unmarshal, cần giữ đúng chuỗi xử lý theo chính sách WS-Security: header, timestamp, token, chữ ký, giải mã và payload validation theo cấu hình.
- **TLS/mTLS** dùng để bảo vệ/xác thực kết nối, còn WS-Security bảo vệ thông điệp theo chính sách. Chứng chỉ không quyết định ý nghĩa của `null` hoặc `xsi:nil`.
- Không log toàn bộ SOAP payload chứa dữ liệu nhạy cảm chỉ để debug “thiếu hay nil”. Có thể log tên element, QName, trạng thái presence/nil và mã lỗi đã được lọc, theo chính sách vận hành.

Khi một middleware XML tự điền default hoặc chuẩn hóa lại payload, cần biết liệu nó đang xử lý **thông điệp đã ký** hay chưa ký. Đừng dùng phép biến đổi XML tùy ý để “sửa” chữ ký sai.

## 14. Những nhầm lẫn thường gặp

1. **“Java `null` luôn có nghĩa element không tồn tại.”** Sai: marshaller có thể phát ra `xsi:nil="true"`, tùy binding.
2. **“`<tag/>` và `<tag xsi:nil="true"/>` giống nhau.”** Sai: một bên có nội dung rỗng, bên kia tuyên bố nil.
3. **“`minOccurs=0` nghĩa là được phép nil.”** Sai: `minOccurs` chỉ liên quan đến sự có mặt; `nillable` kiểm soát nil.
4. **“`nillable=true` nghĩa là có thể bỏ phần tử.”** Sai: nếu `minOccurs=1` thì element vẫn phải xuất hiện.
5. **“Element default sẽ tự thêm phần tử vắng mặt.”** Sai ở mức XSD: element default áp dụng khi phần tử **có mặt và rỗng**.
6. **“Attribute default chỉ có hiệu lực khi attribute rỗng.”** Sai: attribute default áp dụng khi **attribute vắng mặt**.
7. **“Có `@XmlElement(required=true)` là đủ validate XML.”** Sai: cần cấu hình schema validation/kiểm thử cụ thể.
8. **“`JAXBElement<String>` chỉ bọc thêm String, không có lợi ích.”** Sai: wrapper mang QName/scope và trạng thái nil của element.
9. **“Mọi generated class có cùng annotation.”** Sai: XJC, XSD global/local declarations và custom binding ảnh hưởng mô hình Java.
10. **“SOAP Fault do JAXB tự tạo khi Java field null.”** Sai: Fault thuộc SOAP stack, exception handling và chính sách service; JAXB chủ yếu ánh xạ XML.

## 15. Bài thực hành tự kiểm tra

Với XSD `OrderUpdateRequest` ở phần 3:

1. Tạo bốn request XML thể hiện `discountCode` absent, empty, nil và `"WELCOME"`. Xác nhận cả bốn hợp lệ theo schema.
2. Thử `note xsi:nil="true"` và giải thích vì sao schema từ chối, dù Java `String note` có thể nhận `null`.
3. Xóa `orderId`, thử marshal/unmarshal với và không có schema validation. Nêu vì sao một object Java được tạo thành công không chứng minh XML hợp đồng đã đúng.
4. So sánh `<priority/>`, `<priority>HIGH</priority>` và không có `priority`. Dự đoán XSD default được áp dụng khi nào và kiểm tra object Java thật của JAXB provider đang dùng.
5. Đưa `source=""` và bỏ `source` khỏi XML. Kiểm tra sự khác nhau với default attribute `WEB`.
6. Cho `schemaRevision="2"` và giải thích quy tắc `fixed="1"`.
7. Sinh JAXB classes từ XSD, đọc `ObjectFactory`/`package-info.java` và xác định cách binding cho `discountCode`. Viết adapter phân biệt absent/nil/empty.
8. Gửi các payload qua `MockWebServiceClient`, cấu hình schema validation ở Spring-WS, kiểm tra response/Fault và cách domain cập nhật đơn hàng.
9. Thử thay phần tử nil bằng phần tử rỗng **sau khi SOAP Body đã ký** trong một bài test WS-Security; giải thích tác động tới chữ ký và lý do không nên làm vậy.

## 16. Nguyên tắc áp dụng trong dự án thực tế

Để một hợp đồng SOAP ổn định, cần làm rõ **ba quyết định độc lập** cho từng field:

| Câu hỏi | Quyết định thuộc tầng nào? |
| --- | --- |
| Element có thể vắng mặt, rỗng hoặc nil không? | **XSD**: `minOccurs`, `nillable`, `type`, `default`/`fixed` |
| Trạng thái đó được ánh xạ sang Java như thế nào? | **JAXB/XJC và Spring OXM**: property, `JAXBElement`, annotations, validation |
| Absent, empty, nil có nghĩa gì đối với dữ liệu nghiệp vụ? | **Application/domain contract**: giữ nguyên, xóa, đặt chuỗi rỗng, gán default |

**Kết luận:** Trong marshalling và OXM, `null` của Java không đủ để mô tả mọi trạng thái của XML. **Phần tử thiếu**, **phần tử rỗng**, **phần tử nil** và **phần tử có giá trị** cần được thiết kế, ánh xạ và kiểm thử riêng. `minOccurs` và `nillable` kiểm soát hai khía cạnh khác nhau; default của element khác default của attribute; JAXB chuyển đổi dữ liệu nhưng không tự thay thế schema validation hay quy tắc nghiệp vụ. Phân biệt chính xác các tầng này giúp dịch vụ **SPRING_WEB_SERVICES** tránh mất dữ liệu, xử lý đúng SOAP Fault, giữ nguyên tính toàn vẹn WS-Security và tương thích tốt với client doanh nghiệp.

### Tài liệu chuẩn để đối chiếu

- [W3C XML Schema 1.1 – Structures](https://www.w3.org/TR/xmlschema11-1/): định nghĩa phần tử nilled, value constraint, default/fixed và validation.
- [Jakarta XML Binding Specification – Binding XML Schema](https://github.com/jakartaee/jaxb-api/blob/main/spec/src/main/asciidoc/ch06-binding_xml_schema.adoc): quy tắc liên hệ XSD element declarations với generated properties/annotations.
- [Jakarta XML Binding API – JAXBElement](https://javadoc.io/static/jakarta.xml.bind/jakarta.xml.bind-api/3.0.1/jakarta/xml/bind/JAXBElement.html): `getValue()`, `isNil()`, QName và scope.
- [Jakarta XML Binding API – XmlElement](https://javadoc.io/static/jakarta.xml.bind/jakarta.xml.bind-api/4.0.5/jakarta/xml/bind/annotation/XmlElement.html): `required`, `nillable` và `defaultValue`.
