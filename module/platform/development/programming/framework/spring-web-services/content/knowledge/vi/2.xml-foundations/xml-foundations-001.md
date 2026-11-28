# Tài liệu XML, phần tử, thuộc tính, nội dung văn bản và tính hợp lệ cú pháp

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện cấu trúc một tài liệu XML và phân biệt phần tử gốc, phần tử con, thuộc tính, nội dung văn bản.
- Tạo XML đúng cú pháp: đóng thẻ, lồng thẻ, đặt tên, dùng dấu nháy và mã hóa ký tự đặc biệt.
- Hiểu cách namespace xác định phần tử trong bản tin SOAP, đặc biệt khi hai hệ thống dùng cùng tên phần tử.
- Phân biệt XML **well-formed** (đúng cấu trúc cú pháp) với XML **valid** (tuân thủ DTD hoặc XSD).
- Đọc và tự kiểm tra một payload XML trước khi đưa vào hợp đồng XSD/WSDL, ánh xạ JAXB hay endpoint Spring Web Services.

## 1. XML là gì và có vai trò gì trong Spring Web Services?

**XML (Extensible Markup Language)** là định dạng văn bản có cấu trúc phân cấp, trong đó các thẻ mô tả ý nghĩa dữ liệu. XML không quy định sẵn các thẻ nghiệp vụ như `orderId` hay `customer`; ứng dụng và hợp đồng dữ liệu quyết định chúng.

Trong **Spring Web Services (Spring-WS)**, bản tin SOAP là XML. Khi phát triển dịch vụ SOAP theo hướng **contract-first**, nhóm thường thiết kế cấu trúc dữ liệu bằng **XSD**, đưa nó vào hợp đồng **WSDL**, sinh hoặc sử dụng lớp **JAXB** để ánh xạ XML với đối tượng Java, rồi xử lý payload trong endpoint hay SOAP client. Nếu XML bị sai cú pháp, quá trình đọc bản tin có thể thất bại trước khi logic nghiệp vụ được chạy. Nếu XML đúng cú pháp nhưng không khớp XSD, việc xác thực hợp đồng cũng có thể thất bại.

Ví dụ một tài liệu XML biểu diễn đơn hàng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<order id="ORD-001" priority="high">
    <customer>Nguyễn An</customer>
    <item sku="BK-100" quantity="2">Sách XML</item>
    <note>Giao trước 17:00 &amp; gọi trước khi đến</note>
</order>
```

Tài liệu này có khai báo XML ở đầu, một phần tử gốc `order`, hai thuộc tính của `order`, các phần tử con và nội dung văn bản. Dấu `&` trong lời nhắn được ghi thành `&amp;` để không bị hiểu là điểm bắt đầu của tham chiếu thực thể XML.

## 2. Cấu trúc của một tài liệu XML

Một tài liệu XML thường gồm **khai báo XML tùy chọn**, có thể kèm chú thích hoặc chỉ thị xử lý, và **đúng một phần tử gốc** bao bọc nội dung tài liệu.

```text
Tài liệu XML
├── Khai báo <?xml ... ?> (tùy chọn)
└── Phần tử gốc: <order> ... </order>
    ├── Thuộc tính: id="ORD-001"
    ├── Phần tử con: <customer> ... </customer>
    └── Phần tử con: <item ...> ... </item>
```

### 2.1. Khai báo XML

```xml
<?xml version="1.0" encoding="UTF-8"?>
```

- `version="1.0"` cho biết phiên bản XML; XML 1.0 là phiên bản phổ biến trong tích hợp SOAP.
- `encoding="UTF-8"` mô tả cách mã hóa byte của tài liệu; nội dung byte thực tế phải phù hợp với khai báo và cách truyền tải.
- Đây là **khai báo**, không phải phần tử dữ liệu và không có thẻ đóng.
- Nếu sử dụng, khai báo phải nằm ngay đầu tài liệu (ngoại trừ dấu BOM nếu có); XML vẫn có thể hợp lệ về cú pháp khi không có khai báo.

### 2.2. Phần tử gốc và cây phần tử

Trong ví dụ, `order` là **root element**. `customer`, `item` và `note` là các phần tử con. Một phần tử con cũng có thể chứa các phần tử cháu:

```xml
<order>
    <shippingAddress>
        <city>Đà Nẵng</city>
        <country>VN</country>
    </shippingAddress>
</order>
```

XML mô tả cây có thứ bậc. **Không thể** có hai phần tử gốc đứng cạnh nhau trong cùng một tài liệu XML:

```xml
<!-- Sai: hai phần tử gốc -->
<order>...</order>
<customer>...</customer>
```

Trong một hệ thống SOAP, phần tử gốc của **toàn bản tin** thường là `Envelope`; phần tử gốc của **payload nghiệp vụ** nằm bên trong `Body`. Cần phân biệt hai cấp này khi đọc XML hoặc kiểm thử hợp đồng.

## 3. Phần tử XML: thẻ mở, thẻ đóng và lồng nhau

Phần tử thông thường có dạng:

```xml
<customer>Nguyễn An</customer>
```

Trong đó `<customer>` là **thẻ mở**, `</customer>` là **thẻ đóng**, và `Nguyễn An` là **nội dung văn bản**. Phần tử rỗng có thể dùng cú pháp tự đóng:

```xml
<remark/>
```

`<remark/>` tương đương `<remark></remark>` xét về cấu trúc phần tử rỗng. Phần tử rỗng có thể được phép hoặc bị cấm bởi XSD tùy kiểu dữ liệu và ràng buộc của hợp đồng.

Các quy tắc quan trọng:

1. **Mỗi thẻ mở phải được đóng đúng tên**; trừ khi đã dùng dạng tự đóng `/>`.
2. **Các thẻ phải lồng đúng thứ tự**: phần tử được mở sau cùng phải được đóng trước.
3. **Tên thẻ phân biệt chữ hoa và chữ thường**: `Order`, `order` là hai tên khác nhau.
4. **Tên phần tử không được chứa khoảng trắng**; không bắt đầu bằng chữ số. Chữ cái, dấu gạch dưới và nhiều ký tự Unicode được phép theo quy tắc tên XML; dấu hai chấm được dành cho namespace.
5. XML không tự quy định thứ tự của các phần tử con, nhưng **XSD có thể quy định** thứ tự, chẳng hạn qua `xs:sequence`.

Ví dụ lồng thẻ sai:

```xml
<!-- Sai: item chưa đóng nhưng order đã đóng -->
<order>
    <item>Sách</order>
</item>
```

Sửa lại:

```xml
<order>
    <item>Sách</item>
</order>
```

Một phần tử cũng có thể có **nội dung hỗn hợp** (văn bản xen với phần tử con):

```xml
<message>Đơn hàng <strong>ưu tiên</strong> cần xử lý sớm.</message>
```

Tuy nhiên, payload SOAP theo hợp đồng XSD thường dùng cấu trúc dữ liệu rõ ràng thay cho nội dung hỗn hợp, để ánh xạ JAXB ổn định và dễ kiểm tra.

## 4. Thuộc tính XML: dữ liệu đi kèm phần tử

**Attribute** nằm trong thẻ mở, có dạng `tên="giá trị"` hoặc `tên='giá trị'`:

```xml
<item sku="BK-100" quantity="2" available='true'>Sách XML</item>
```

Ở đây `sku`, `quantity`, `available` là thuộc tính; `Sách XML` là văn bản nằm trong phần tử `item`.

| Thuộc tính | Phần tử con |
| --- | --- |
| Viết ngay trong thẻ mở, ví dụ `sku="BK-100"`. | Có thẻ riêng, ví dụ `<sku>BK-100</sku>`. |
| Giá trị được viết dưới dạng chuỗi trong tài liệu XML; XSD có thể quy định kiểu số, boolean, ngày, v.v. | Có thể chứa văn bản, phần tử con hoặc nội dung hỗn hợp. |
| Không có cấu trúc phần tử con bên trong giá trị thuộc tính. | Dùng được cho dữ liệu nghiệp vụ có cấu trúc hoặc cần mở rộng. |
| Các thuộc tính trên cùng một phần tử không có thứ tự mang ý nghĩa. | Thứ tự phần tử con có thể mang ý nghĩa theo XSD. |

Chọn thuộc tính hay phần tử phải dựa vào **hợp đồng XSD và yêu cầu nghiệp vụ**. Ví dụ `orderId` có thể là thuộc tính hoặc phần tử tùy hợp đồng; client và server không thể tự thay đổi qua lại. Trong SOAP contract-first, các dữ liệu nghiệp vụ có cấu trúc thường được mô tả bằng phần tử con.

Các lỗi thuộc tính thường gặp:

```xml
<!-- Sai: giá trị thiếu dấu nháy -->
<item quantity=2/>

<!-- Sai: trùng tên thuộc tính trên cùng phần tử -->
<item sku="BK-100" sku="BK-200"/>

<!-- Đúng -->
<item quantity="2" sku="BK-100"/>
```

**Lưu ý:** Một thuộc tính ghi `quantity="2"` không tự động trở thành số nguyên trong XML thuần; XSD/JAXB hoặc ứng dụng sẽ quyết định kiểu và xử lý giá trị đó.

## 5. Nội dung văn bản, ký tự đặc biệt và CDATA

Text content là các ký tự nằm giữa thẻ mở và thẻ đóng. XML coi một số ký tự là cú pháp đánh dấu, nên khi muốn lưu chúng như dữ liệu, phải dùng **tham chiếu thực thể** thích hợp.

| Ký tự muốn biểu diễn | Cách viết trong XML | Ghi chú |
| --- | --- | --- |
| `&` | `&amp;` | Phải escape trong nội dung văn bản và giá trị thuộc tính. |
| `<` | `&lt;` | Phải escape khi là dữ liệu, để không bị hiểu là mở thẻ. |
| `>` | `&gt;` | Thường được phép ghi trực tiếp; cần escape để tránh chuỗi cấm `]]>`. |
| `"` | `&quot;` | Cần escape khi nằm trong thuộc tính được bao bằng `"`. |
| `'` | `&apos;` | Cần escape khi nằm trong thuộc tính được bao bằng `'`. |

Ví dụ:

```xml
<note>Giá trị A &lt; B &amp; B &gt; 0</note>
<customer name="Lan &quot;QA&quot;"/>
```

Khi parser XML đọc nội dung này, ứng dụng nhận văn bản `Giá trị A < B & B > 0` và giá trị thuộc tính `Lan "QA"`. Không được viết trực tiếp `A & B` vào text XML vì `&` bắt đầu một tham chiếu thực thể.

### 5.1. CDATA

**CDATA section** cho phép đưa phần văn bản có chứa `<` hoặc `&` mà không cần escape từng ký tự:

```xml
<note><![CDATA[Điều kiện: amount < 100 & status = NEW]]></note>
```

Về dữ liệu ký tự, đoạn trên tương đương:

```xml
<note>Điều kiện: amount &lt; 100 &amp; status = NEW</note>
```

CDATA **không biến nội dung thành các phần tử XML con**; parser vẫn cung cấp nó như dữ liệu ký tự. CDATA không được chứa chuỗi kết thúc `]]>` bên trong. Không dùng CDATA để bỏ qua cấu trúc do XSD quy định.

### 5.2. Chú thích và khoảng trắng

```xml
<order>
    <!-- Thông tin hiển thị cho người xử lý -->
    <note>Giao buổi sáng</note>
</order>
```

Chú thích có dạng `<!-- ... -->`, không được chứa chuỗi `--` ở bên trong. Khoảng trắng trong nội dung văn bản có thể là dữ liệu có ý nghĩa; không nên mặc định rằng mọi khoảng trắng hoặc dấu xuống dòng đều bị loại bỏ bởi XML parser/JAXB. Quy tắc xử lý còn phụ thuộc schema và ứng dụng.

## 6. Namespace: xác định chính xác phần tử trong SOAP

Hai hệ thống có thể cùng đặt tên phần tử `Request` nhưng biểu diễn hai loại dữ liệu khác nhau. **XML namespace** cung cấp định danh cho tên phần tử. Tên đầy đủ về mặt ngữ nghĩa được xác định bởi cặp **namespace URI + local name**.

```xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>42</ord:orderId>
</ord:GetOrderRequest>
```

- `xmlns:ord="urn:example:orders:v1"` khai báo namespace cho tiền tố `ord`.
- `ord:GetOrderRequest` có **local name** là `GetOrderRequest`, namespace URI là `urn:example:orders:v1`.
- `ord` chỉ là tên tiền tố do người viết chọn; thay `ord` bằng `o` mà vẫn trỏ cùng URI thì phần tử vẫn có cùng tên mở rộng.
- URI namespace đóng vai trò **định danh**; không cần là một địa chỉ web có thể truy cập.

Có thể sử dụng **namespace mặc định** cho phần tử:

```xml
<GetOrderRequest xmlns="urn:example:orders:v1">
    <orderId>42</orderId>
</GetOrderRequest>
```

Trong đoạn trên, cả `GetOrderRequest` và `orderId` đều thuộc namespace mặc định. Nhưng namespace mặc định **không tự áp dụng cho thuộc tính không có tiền tố**:

```xml
<GetOrderRequest xmlns="urn:example:orders:v1" requestId="REQ-1"/>
```

Thuộc tính `requestId` ở đây không thuộc namespace mặc định. Đây là điểm dễ gây nhầm lẫn khi đọc hợp đồng XSD hoặc viết thông điệp SOAP thủ công.

### 6.1. Ví dụ một bản tin SOAP 1.1

```xml
<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>42</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
```

Đọc bản tin theo thứ tự: `soap:Envelope` là gốc XML của bản tin; `soap:Header` là phần header rỗng; `soap:Body` chứa **payload** `ord:GetOrderRequest`, với dữ liệu `ord:orderId`.

Ví dụ này dùng namespace **SOAP 1.1**. SOAP 1.2 sử dụng namespace Envelope khác (`http://www.w3.org/2003/05/soap-envelope`); chúng không thể tráo đổi tùy ý. Ở phía Spring-WS, một endpoint dùng `@PayloadRoot(namespace = "urn:example:orders:v1", localPart = "GetOrderRequest")` sẽ phân biệt payload dựa trên namespace và tên phần tử, chứ không dựa trên tiền tố `ord`.

## 7. Well-formed khác gì valid?

Trong ngữ cảnh XML, cần phân biệt hai câu hỏi:

1. **Well-formed (đúng cấu trúc cú pháp):** Tài liệu có tuân thủ quy tắc XML về thẻ, lồng nhau, dấu nháy, tham chiếu thực thể, ký tự hợp lệ, phần tử gốc, v.v. không?
2. **Valid (hợp lệ theo hợp đồng):** Tài liệu đã well-formed có tuân thủ các khai báo/ràng buộc trong **DTD hoặc XSD** tương ứng không?

Một tài liệu có thể well-formed nhưng **không valid**. XSD cho phép quy định tên, namespace, thứ tự và số lần xuất hiện phần tử, kiểu dữ liệu, các ràng buộc về giá trị, thuộc tính bắt buộc, v.v.

Ví dụ hợp đồng XSD cho payload `GetOrderRequest`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:positiveInteger"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Payload phù hợp với XSD trên:

```xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>42</ord:orderId>
</ord:GetOrderRequest>
```

Payload dưới đây **vẫn well-formed** nhưng **không valid theo XSD trên**, vì `abc` không phải số nguyên dương:

```xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:orderId>abc</ord:orderId>
</ord:GetOrderRequest>
```

Ngoài kiểu dữ liệu, việc đổi tên `ord:orderId` thành `ord:id`, thay namespace URI, thêm phần tử không được phép hoặc đảo thứ tự phần tử trong `xs:sequence` (nếu có nhiều phần tử) đều có thể khiến payload sai hợp đồng. **Well-formedness không bảo đảm tương thích SOAP contract-first.**

Lưu ý: XSD mẫu trên mô tả **payload nghiệp vụ**, không mô tả toàn bộ `soap:Envelope`. Khi xác thực bản tin SOAP, cần dùng cơ chế xác thực thích hợp cho payload và/hoặc cấu trúc SOAP.

## 8. Các lỗi cú pháp phổ biến và cách sửa

| XML lỗi | Vấn đề | Cách sửa |
| --- | --- | --- |
| `<Order></order>` | Tên thẻ phân biệt hoa/thường. | `<Order></Order>` |
| `<a><b></a></b>` | Thẻ lồng sai thứ tự. | `<a><b></b></a>` |
| `<a/><b/>` | Có hai phần tử gốc. | Dùng một phần tử bao ngoài, ví dụ `<root><a/><b/></root>`. |
| `<item qty=2/>` | Thiếu dấu nháy cho giá trị thuộc tính. | `<item qty="2"/>` |
| `<item id="1" id="2"/>` | Trùng tên thuộc tính. | Chỉ giữ một `id`. |
| `<note>A & B</note>` | Dấu `&` chưa escape. | `<note>A &amp; B</note>` |
| `<note>1 < 2</note>` | Dấu `<` bị hiểu là mở thẻ. | `<note>1 &lt; 2</note>` |
| `<p:Request/>` | Tiền tố `p` chưa được khai báo namespace. | Khai báo `xmlns:p="urn:example:orders:v1"` trong phạm vi sử dụng. |

Một lỗi khác ít nhìn thấy hơn là **khai báo encoding không khớp với byte thực tế**. Hãy lưu và truyền XML với mã hóa thống nhất (thường là UTF-8); khi dùng HTTP/SOAP, kiểm tra thêm thông tin mã hóa của tầng truyền tải.

Với dữ liệu XML nhận từ nguồn không tin cậy, cần cấu hình parser an toàn, đặc biệt quanh DTD và external entities để tránh **XML External Entity (XXE)**. Đây là vấn đề cấu hình bảo mật parser, khác với việc tài liệu có well-formed hay không.

## 9. Cách kiểm tra XML trước khi tích hợp SOAP

Một quy trình kiểm tra thực tế:

1. **Kiểm tra cú pháp:** tài liệu có đúng một root, các thẻ đóng khớp, mọi thuộc tính có dấu nháy và các ký tự đặc biệt được escape đúng không?
2. **Kiểm tra namespace:** namespace URI, local name và phiên bản SOAP có trùng hợp đồng không? Đừng chỉ so sánh tiền tố hiển thị.
3. **Kiểm tra XSD:** xác thực payload theo schema đã thỏa thuận; lưu ý thứ tự phần tử, kiểu dữ liệu và ràng buộc bắt buộc.
4. **Kiểm tra ánh xạ:** với JAXB, thử chuyển XML thành đối tượng Java và ngược lại theo cấu hình dự án.
5. **Kiểm tra tích hợp:** gửi bản tin qua SOAP client/endpoint và quan sát lỗi parse, validation hoặc SOAP Fault nếu có.

Nếu môi trường đã cài `xmllint` (thuộc libxml2), bạn có thể thử với một **payload XML độc lập** lưu trong `request.xml` và XSD tương ứng lưu trong `order.xsd`:

```bash
# Chỉ kiểm tra XML well-formed
xmllint --noout request.xml

# Kiểm tra thêm hợp đồng XSD
xmllint --noout --schema order.xsd request.xml
```

Hai thao tác trả lời **hai câu hỏi khác nhau**: đọc được XML không, và dữ liệu có tuân thủ schema không. Đối với SOAP Envelope hoàn chỉnh, không dùng trực tiếp XSD chỉ mô tả `GetOrderRequest` để xác thực cả tài liệu; cần trích payload hoặc dùng công cụ có hỗ trợ SOAP.

## 10. Bài tập tự kiểm tra

**Bài 1 — Sửa tài liệu sai cú pháp.** Tìm tất cả lỗi trong đoạn sau:

```xml
<GetOrderRequest>
    <orderId>42</orderId>
    <note>A & B</note>
</GetOrderResponse>
```

**Đáp án:** Đổi thẻ đóng cuối thành `</GetOrderRequest>` và đổi `A & B` thành `A &amp; B`.

**Bài 2 — Phân loại lỗi.** Giả sử hợp đồng XSD yêu cầu `orderId` kiểu `xs:positiveInteger`. `<orderId>0</orderId>` có đúng cú pháp XML không, và có đúng XSD không?

**Đáp án:** XML này well-formed nếu được dùng như một tài liệu độc lập; nhưng giá trị `0` không hợp lệ đối với `xs:positiveInteger`, nên không valid theo ràng buộc XSD đã nêu.

**Bài 3 — Hiểu namespace.** Hai payload dùng tiền tố `ord:GetOrderRequest` và `o:GetOrderRequest`, cùng khai báo tiền tố về `urn:example:orders:v1`. Chúng có cùng tên phần tử không?

**Đáp án:** Có. Cả hai cùng namespace URI và local name `GetOrderRequest`. Ngược lại, cùng tiền tố `ord` nhưng trỏ đến namespace URI khác sẽ là các phần tử khác nhau.

**Bài 4 — Gắn với Spring-WS.** Vì sao XML well-formed vẫn có thể bị endpoint hoặc tầng validation từ chối?

**Đáp án:** Payload có thể sai namespace, local name, cấu trúc hoặc kiểu dữ liệu so với XSD; endpoint có thể không khớp `@PayloadRoot`, hoặc bộ xác thực schema có thể báo lỗi. Khả năng đọc XML đúng cú pháp chỉ là điều kiện đầu tiên của một bản tin SOAP tương thích.

## Ghi nhớ

XML được đọc như **cây phần tử có đúng một root**, trong đó thuộc tính nằm ở thẻ mở và nội dung văn bản nằm trong phần tử. Đóng thẻ đúng, lồng đúng, escape ký tự đặc biệt và khai báo namespace chính xác giúp tài liệu **well-formed**. Muốn dịch vụ SOAP Spring-WS hoạt động đúng theo thiết kế **contract-first**, payload còn phải **valid theo XSD** và khớp tên phần tử/namespace mà hợp đồng cùng endpoint mong đợi.
