# Ngày giờ, decimal, dữ liệu nhị phân và adapter tùy chỉnh

> **Chương:** Marshalling và OXM  
> **Ngữ cảnh:** SPRING_WEB_SERVICES – xây dựng dịch vụ SOAP theo hướng **contract-first** bằng Spring Web Services, thiết kế XSD/WSDL, ánh xạ JAXB, endpoint và SOAP client, đồng thời kiểm soát SOAP Fault, interceptor, XML security, WS-Security và tính tương thích doanh nghiệp.

## 1. Vì sao các kiểu này đặc biệt quan trọng?

**Marshalling** là chuyển đối tượng Java thành XML theo hợp đồng; **unmarshalling** là chuyển XML nhận được thành dữ liệu Java. OXM (*Object/XML Mapping*) là cách tổ chức quá trình ánh xạ đó. Với SOAP, “Java đọc được XML” chưa đủ: XML phải đúng **kiểu, namespace, cú pháp giá trị và ràng buộc của XSD/WSDL** mà hai bên đã thống nhất.

Ngày giờ, tiền tệ và file đính kèm là ba nhóm dữ liệu dễ gây sai lệch nhất:

- Một timestamp không có múi giờ có thể bị các máy hiểu thành những thời điểm khác nhau.
- `BigDecimal` cần bảo toàn độ chính xác thập phân; dùng `double` cho tiền dễ gây sai số biểu diễn nhị phân.
- `xs:base64Binary` làm XML lớn hơn dữ liệu gốc; tài liệu dung lượng lớn có thể cần **MTOM/XOP** và xử lý tài nguyên phù hợp.
- Một `XmlAdapter` có thể chuyển sang kiểu Java tiện dụng hơn, nhưng cũng có thể âm thầm thay đổi ý nghĩa dữ liệu hoặc chấp nhận ít giá trị hơn XSD.
- Một client JAXB thành công không có nghĩa XML đã qua **schema validation** hoặc tuân thủ chính sách bảo mật.

Mục tiêu của bài là chọn kiểu XSD phù hợp, hiểu ánh xạ JAXB mặc định, viết adapter có kiểm soát, thiết kế xử lý binary theo dung lượng và kiểm thử hợp đồng SOAP ở ranh giới tích hợp.

## 2. Bản đồ kiểu XSD ↔ Java/JAXB

| XSD | Ý nghĩa trên wire | Ánh xạ JAXB thường gặp | Điểm cần quyết định |
|---|---|---|---|
| `xs:date` | Ngày theo ISO, có thể có timezone | `XMLGregorianCalendar` | Ngày nghiệp vụ không nên tự đổi sang một thời điểm UTC |
| `xs:time` | Giờ trong ngày, timezone có thể tùy chọn | `XMLGregorianCalendar` | Giờ địa phương gắn với khu vực hay giờ có offset? |
| `xs:dateTime` | Ngày + giờ; XML Schema 1.0 cho phép có hoặc không có timezone | `XMLGregorianCalendar` | Có bắt buộc offset/UTC hay không? |
| `xs:decimal` | Số thập phân chính xác | `BigDecimal` | Độ chính xác, scale, làm tròn, currency |
| `xs:integer`, `xs:long` | Số nguyên, có ràng buộc miền giá trị khác nhau | `BigInteger`, `Long`/`long` tùy kiểu | Không thay thập phân bằng integer khi hợp đồng chứa phần lẻ |
| `xs:base64Binary` | Byte mã hóa base64 dưới dạng text XML | `byte[]`; có thể dùng `DataHandler` khi có MIME mapping | Dung lượng, MTOM, giới hạn giải mã |
| `xs:hexBinary` | Byte biểu diễn bằng các cặp chữ số hex | `byte[]` | Hex dùng cho mã băm, khóa/định danh khi contract yêu cầu |
| Kiểu Java cần chuyển đổi | Không nhất thiết có một XSD primitive tương ứng | `XmlAdapter<ValueType, BoundType>` | Chuẩn lexical, null, timezone, lỗi chuyển đổi |

Đây là **ánh xạ phổ biến**, không phải cam kết mọi công cụ sinh mã tạo cùng class và annotation. Phiên bản JAXB, binding customization, namespace và quy tắc sinh mã có thể thay đổi kết quả. Ở ứng dụng Jakarta hiện đại, JAXB dùng `jakarta.xml.bind.*`; API thời Java EE cũ dùng `javax.xml.bind.*`. Trong khi đó `javax.xml.datatype.XMLGregorianCalendar` thuộc JAXP trong JDK và vẫn mang tên `javax` trên Java mới.

~~~mermaid
flowchart LR
  A["XSD/WSDL contract"] --> B["XML payload"]
  B --> C["Unmarshaller / JAXB"]
  C --> D["Boundary model"]
  D --> E["Chuyển sang domain model"]
  E --> F["Business service"]
  F --> G["Tạo response model"]
  G --> H["Marshaller / JAXB"]
  H --> I["SOAP response đúng schema"]
~~~

Quyết định tốt thường là **giữ model biên theo XSD** và chuyển sang domain model theo quy tắc nghiệp vụ ở một lớp rõ ràng. Không nên ép entity database, `Instant` và kiểu tiền nội bộ xuất thẳng ra XML nếu như vậy làm đổi contract.

## 3. Xây XSD contract-first cho một receipt SOAP

Giả sử SOAP operation `GetReceipt` trả về một biên nhận: thời điểm xử lý, ngày hạch toán, giờ đóng sổ, số tiền và nội dung tài liệu.

Tạo file `receipt.xsd` minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="urn:demo:receipt:v1"
           xmlns:xmime="http://www.w3.org/2005/05/xmlmime"
           targetNamespace="urn:demo:receipt:v1"
           elementFormDefault="qualified">

  <xs:simpleType name="AmountType">
    <xs:restriction base="xs:decimal">
      <xs:totalDigits value="18"/>
      <xs:fractionDigits value="2"/>
      <xs:minInclusive value="0"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="CurrencyCodeType">
    <xs:restriction base="xs:string">
      <xs:pattern value="[A-Z]{3}"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="GetReceiptRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="receiptId" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <xs:element name="GetReceiptResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="processedAt" type="xs:dateTime"/>
        <xs:element name="postingDate" type="xs:date"/>
        <xs:element name="cutoffTime" type="xs:time"/>
        <xs:element name="amount" type="tns:AmountType"/>
        <xs:element name="currency" type="tns:CurrencyCodeType"/>
        <xs:element name="document" type="xs:base64Binary"
                    minOccurs="0"
                    xmime:expectedContentTypes="application/pdf"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Giải thích các quyết định:

1. `processedAt` biểu diễn **thời điểm xử lý**; quy tắc nghiệp vụ của ví dụ là server luôn ghi offset hoặc `Z` (UTC). XSD 1.0 `xs:dateTime` tự nó **không bắt buộc phải có timezone**; cần kiểm tra quy tắc này tại boundary hoặc thiết kế validation bổ sung.
2. `postingDate` là **ngày hạch toán**. Không chuyển một ngày thuần túy sang UTC midnight rồi đổi lại theo timezone khác nếu nghiệp vụ không yêu cầu.
3. `cutoffTime` biểu diễn giờ đóng sổ; muốn xác định một *instant* duy nhất còn cần thông tin ngày và múi giờ/ngữ cảnh kinh doanh.
4. `AmountType` mô tả số không âm, nhiều nhất 18 chữ số tổng cộng và 2 chữ số phần thập phân theo quy tắc XSD. `CurrencyCodeType` kiểm soát hình thức mã ba ký tự viết hoa, **không xác thực** mã đó có thuộc danh sách ISO 4217 đang áp dụng hay không.
5. `document` là tùy chọn; `xmime:expectedContentTypes` là **gợi ý về MIME mapping** cho các công cụ hỗ trợ, không phải phép bảo đảm rằng byte thực sự là PDF hợp lệ.

Một response **về cấu trúc** theo XSD trên (bỏ trường document vì tùy chọn):

~~~xml
<r:GetReceiptResponse xmlns:r="urn:demo:receipt:v1">
  <r:processedAt>2026-11-27T09:18:00+07:00</r:processedAt>
  <r:postingDate>2026-11-27</r:postingDate>
  <r:cutoffTime>17:30:00</r:cutoffTime>
  <r:amount>125000.50</r:amount>
  <r:currency>VND</r:currency>
</r:GetReceiptResponse>
~~~

Trong WSDL 1.1 document/literal, `wsdl:message` tham chiếu đến **global element** `tns:GetReceiptResponse` qua `wsdl:part/@element`. Spring-WS thường định tuyến tới `@Endpoint` bằng QName của root trong SOAP Body. Kiểu Java dùng bên trong không được làm thay đổi QName hoặc thứ tự con của payload.

## 4. Ngày giờ: phân biệt calendar date, wall time và instant

### 4.1. Ba ý nghĩa khác nhau

| Câu hỏi nghiệp vụ | Kiểu phù hợp | Ví dụ | Java domain type thường dùng |
|---|---|---|---|
| Đơn hàng được ghi nhận vào **ngày nào**? | `xs:date` | `2026-11-27` | `LocalDate` |
| Quầy ngừng nhận giao dịch lúc **mấy giờ trong ngày**? | `xs:time` | `17:30:00` | `LocalTime` hoặc `OffsetTime` tùy contract |
| Sự kiện xảy ra tại **thời điểm chính xác nào**? | `xs:dateTime` với offset rõ | `2026-11-27T09:18:00+07:00` | `Instant` hoặc `OffsetDateTime` |

Một timezone như `Asia/Ho_Chi_Minh` mang thông tin **vùng thời gian** cùng quy tắc lịch sử/chính sách; offset `+07:00` là độ lệch tại một thời điểm. `xs:dateTime` có offset **không trực tiếp lưu ZoneId IANA**. Nếu hệ thống cần biết lịch/zone nguyên gốc, hãy thiết kế thêm field `zoneId` có quy tắc xác thực riêng.

### 4.2. Đầu vào hợp lệ và rủi ro diễn giải

Các lexical form dưới đây có thể hợp lệ với `xs:dateTime` trong XSD 1.0:

~~~text
2026-11-27T09:18:00Z
2026-11-27T09:18:00+07:00
2026-11-27T09:18:00
2026-11-27T09:18:00.123Z
~~~

Dòng **không có timezone** không xác định duy nhất một instant toàn cầu. Nếu code dùng timezone mặc định của JVM để chuyển nó, cùng XML có thể trở thành hai kết quả khác nhau ở hai server.

JAXB thường ánh xạ `xs:date`, `xs:time`, `xs:dateTime` sang `XMLGregorianCalendar`. Ví dụ đọc timezone:

~~~java
import javax.xml.datatype.DatatypeConstants;
import javax.xml.datatype.XMLGregorianCalendar;

XMLGregorianCalendar xmlTime = response.getProcessedAt();

if (xmlTime.getTimezone() == DatatypeConstants.FIELD_UNDEFINED) {
    throw new IllegalArgumentException(
            "processedAt phải có UTC offset theo hợp đồng nghiệp vụ");
}

// Khi đã xác định offset, mới chuyển có chủ đích sang Instant.
java.time.Instant instant = xmlTime
        .toGregorianCalendar()
        .toZonedDateTime()
        .toInstant();
~~~

`getTimezone()` trả số **phút lệch UTC** hoặc `FIELD_UNDEFINED`. Đoạn code chỉ xử lý trường `processedAt` theo policy bắt buộc offset; với `postingDate`, không nên dùng cùng cách chuyển sang instant chỉ để dễ thao tác. Với `cutoffTime`, nếu muốn biết instant thì phải ghép thêm một ngày và timezone/offset đã thống nhất.

### 4.3. Chú ý thay đổi múi giờ và tính tương thích

- **Không chuẩn hóa tất cả giá trị thời gian thành `LocalDateTime`.** Nó không chứa offset, dễ làm mất ý nghĩa thời điểm.
- **Không tự thêm `Z`** cho timestamp thiếu offset. Đó là một giả định nghiệp vụ, không phải chuyển đổi an toàn.
- **Không gộp ngày hạch toán với thời điểm xử lý.** Một giao dịch xử lý lúc 00:15 ở nước A có thể hạch toán theo ngày kinh doanh khác ở nước B.
- **Không dùng format theo locale của máy** như `dd/MM/yyyy HH:mm` làm wire format; cần tuân thủ lexical XML Schema.
- Nếu cần quy định **bắt buộc có timezone** một cách máy kiểm tra được, XSD 1.1 có `explicitTimezone` nhưng hỗ trợ trên các stack SOAP có thể không đồng đều. Với XSD 1.0, nên kết hợp schema và kiểm tra policy nghiệp vụ hoặc ràng buộc lexical được thiết kế cẩn thận.

## 5. Decimal: giữ chính xác và kiểm soát làm tròn

### 5.1. Vì sao dùng BigDecimal?

`xs:decimal` là số thập phân chính xác, không sử dụng biểu diễn dấu phẩy động nhị phân như Java `double`. Cách ánh xạ JAXB phổ biến là `java.math.BigDecimal`:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal amount = new BigDecimal("125000.50");
BigDecimal taxRate = new BigDecimal("0.10");
BigDecimal tax = amount.multiply(taxRate);

// Chỉ làm tròn khi quy tắc nghiệp vụ thực sự yêu cầu.
BigDecimal taxRounded = tax.setScale(2, RoundingMode.HALF_UP);
~~~

Không khởi tạo `new BigDecimal(0.1)` khi cần giá trị thập phân chính xác theo chữ số người dùng nhập. Dùng constructor nhận **chuỗi** hoặc `BigDecimal.valueOf(...)` khi nguồn dữ liệu đã là double và bạn hiểu hệ quả. Với tiền tệ, tốt hơn lấy chính giá trị thập phân nguyên thủy từ contract/DB.

### 5.2. Scale, precision và fractionDigits không phải một thứ

- **Precision** của `BigDecimal` là số chữ số của *unscaled value* (không tính dấu và dấu thập phân theo cách thể hiện object).
- **Scale** là số chữ số vị trí phần thập phân theo cách biểu diễn Java, có thể là âm.
- **`xs:totalDigits`** và **`xs:fractionDigits`** là ràng buộc XSD trên giá trị số thập phân; không nên đồng nhất máy móc với thuộc tính precision/scale của một instance `BigDecimal`, đặc biệt khi có số 0 cuối hoặc dạng biểu diễn khác nhau.
- `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` là `false` do khác scale, nhưng `compareTo(...) == 0` vì cùng giá trị số học.

Ví dụ kiểm soát scale mà **không âm thầm làm tròn**:

~~~java
BigDecimal input = new BigDecimal("123.456");
try {
    BigDecimal normalized = input.setScale(2, RoundingMode.UNNECESSARY);
    // Nếu thành công, giá trị đã có thể biểu diễn chính xác với 2 số lẻ.
} catch (ArithmeticException ex) {
    // Reject hoặc đưa vào quy trình làm tròn đã được thỏa thuận.
}
~~~

Trong bài này `AmountType` có `fractionDigits="2"` nên giá trị thập phân có phần lẻ khác 0 quá hai vị trí không phù hợp. Tuy vậy, XML `125000.500` và `125000.50` có thể biểu diễn **cùng một giá trị số**; cách một validator áp dụng facet phụ thuộc quy tắc giá trị của XML Schema, không chỉ việc đếm ký tự sau dấu chấm. Đừng dùng một regex tự viết thay cho validator XSD rồi coi là tương đương.

### 5.3. Decimal khác currency

`125000.50` không cho biết số tiền theo đơn vị nào, có cần làm tròn theo đơn vị tiền hay không hoặc có thể âm trong giao dịch hoàn tiền không. XSD nên mô tả rõ ý nghĩa của field và có currency ở nơi phù hợp, nhưng:

- `fractionDigits="2"` là quyết định **contract**, không phải quy tắc phù hợp cho mọi đồng tiền.
- Làm tròn thuế, phí, số dư phải dựa trên **quy tắc nghiệp vụ**, không mặc định dùng HALF_UP hay HALF_EVEN.
- Nếu tiền bị chuyển sang double ở bất kỳ lớp nào, có thể mất tính chính xác dù SOAP message dùng `xs:decimal`.
- Khi serialize, `BigDecimal.toPlainString()` hữu ích để tránh dạng exponent trong các đường chuyển đổi thủ công; hãy để JAXB serializer tạo lexical form đúng `xs:decimal` và kiểm tra XML thực tế.

Bảng smoke test giá trị:

| Trường hợp | Mong đợi |
|---|---|
| `0` hoặc `0.00` | Hợp lệ vì `minInclusive="0"` |
| `125000.50` | Hợp lệ |
| `-0.01` | Không hợp lệ |
| `123.456` | Không hợp lệ do phần lẻ vượt giới hạn |
| Số có quá 18 chữ số có nghĩa | Không hợp lệ do `totalDigits` |
| `1.2E3` | Không phải lexical form hợp lệ của `xs:decimal` |

Một hệ thống SOAP contract-first cần test cả **giá trị biên** và **XML lexical form**, không chỉ kết quả phép cộng/trừ Java.

## 6. Dữ liệu nhị phân: base64Binary, hexBinary và MTOM

### 6.1. XML không truyền byte tùy ý như text thông thường

XML là định dạng văn bản. Khi cần mang byte tùy ý trong một phần tử, XSD có hai kiểu phổ biến:

- **`xs:base64Binary`:** biểu diễn byte thành ký tự Base64. Ví dụ 5 byte của chuỗi ASCII `Hello` được biểu diễn thành `SGVsbG8=`.
- **`xs:hexBinary`:** biểu diễn mỗi byte bằng hai ký tự hex. Cùng 5 byte sẽ thành `48656C6C6F`.

~~~xml
<xs:element name="inlineData" type="xs:base64Binary"/>
<xs:element name="digest" type="xs:hexBinary"/>
~~~

Instance tương ứng:

~~~xml
<r:inlineData xmlns:r="urn:demo:receipt:v1">SGVsbG8=</r:inlineData>
<r:digest xmlns:r="urn:demo:receipt:v1">48656C6C6F</r:digest>
~~~

Trong Java/JAXB, cả hai có thể ánh xạ sang `byte[]`. Nhưng phần **lexical XML** hoàn toàn khác; nếu sai loại encoder hoặc khai báo XSD thì receiver có thể từ chối.

Ở ví dụ XSD phần 3, `document` là `xs:base64Binary`. Một SOAP payload nhỏ có thể gửi inline:

~~~xml
<r:document xmlns:r="urn:demo:receipt:v1">SGVsbG8=</r:document>
~~~

Đây chỉ là **5 byte demo "Hello"**, không phải một PDF. Không suy ra file đúng định dạng PDF từ tên trường, MIME type hoặc giá trị Base64. Với tài liệu thực tế cần xác thực kiểu file, định dạng, dung lượng, malware policy và tính toàn vẹn theo yêu cầu nghiệp vụ.

### 6.2. Kích thước và chi phí của Base64

Base64 mã hóa mỗi 3 byte thành 4 ký tự, nên phần nội dung đã mã hóa dài xấp xỉ **4/3 dữ liệu gốc** (chưa tính XML, header, dấu xuống dòng và chi phí parser). Với file 12 MiB, phần base64 nguyên thủy sẽ khoảng 16 MiB.

Một số hệ quả:

1. SOAP Envelope lớn hơn và tốn băng thông hơn.
2. Parser XML có thể giữ chuỗi và dữ liệu giải mã trong bộ nhớ cùng lúc.
3. `byte[]` có thể khiến ứng dụng nạp toàn bộ tài liệu vào heap.
4. Schema validation, canonicalization và chữ ký XML có thể làm tăng CPU và bộ nhớ.
5. Một request hợp lệ về cú pháp vẫn có thể gây quá tải nếu không đặt giới hạn dung lượng.

Với blob lớn, **MTOM (Message Transmission Optimization Mechanism)** và **XOP (XML-binary Optimized Packaging)** cho phép tối ưu việc truyền phần binary ra thành MIME attachment, tránh nhúng toàn bộ Base64 text trong XML body.

### 6.3. MTOM/XOP không phải một schema type mới

Hợp đồng XSD vẫn khai báo `xs:base64Binary`. Khi giao thức và hai đầu tương thích MTOM, SOAP request/response trên dây có thể là **MIME multipart**, trong đó SOAP XML chứa tham chiếu:

~~~xml
<r:document xmlns:r="urn:demo:receipt:v1"
            xmlns:xop="http://www.w3.org/2004/08/xop/include">
  <xop:Include href="cid:receipt-pdf-1@example.test"/>
</r:document>
~~~

Đây chỉ là **mảnh XML được trích ra từ MTOM/XOP package**, không phải toàn bộ request hợp lệ để gửi bằng `curl -H "Content-Type: text/xml"`. MIME package thực còn có root part, boundary, content ID và các part binary; content type thường là `multipart/related` với thông tin `application/xop+xml` và SOAP version tương ứng.

- Ở **mô hình XML**, element `document` vẫn tương ứng nội dung nhị phân `xs:base64Binary`.
- Ở **mô hình đóng gói**, binary có thể nằm trong một MIME part bên ngoài SOAP XML.
- Không phải cứ bật MTOM thì **mọi** blob đều thành attachment: runtime có thể inline các dữ liệu nhỏ hoặc áp dụng tiêu chí tối ưu riêng.
- MTOM không tự tạo ra chữ ký hay encryption. Nếu đối tác dùng WS-Security, phải cấu hình profile/policy có xử lý attachments và XOP đúng cách.

### 6.4. Khi nào dùng byte[] và khi nào dùng DataHandler?

| Nhu cầu | Kiểu Java thường chọn | Đánh đổi |
|---|---|---|
| Payload rất nhỏ, dễ test | `byte[]` | Đơn giản, nhưng dữ liệu thường nằm trong heap |
| File tương đối lớn, cần MIME/MTOM | `jakarta.activation.DataHandler` hoặc abstraction stream phù hợp | Có thể tránh giữ toàn bộ trong một `byte[]`; mức streaming thực phụ thuộc runtime |
| Hash/digest nhị phân | `byte[]` + XSD `hexBinary`/`base64Binary` được chốt | Phải thống nhất thuật toán và encoding |
| Tài liệu không được phép xuất ra SOAP Body | Giao thức tải file riêng + metadata/tham chiếu | Thêm giao thức/lifecycle, nhưng có thể dễ giới hạn hơn với file lớn |

Khi sử dụng `DataHandler`, hãy xem cấu hình spool file/threshold, thời gian sống input stream, kiểm tra kích thước **trước và sau giải mã** và dọn dữ liệu tạm. **MTOM không bảo đảm zero-copy** và không đảm bảo server không đọc file vào RAM; điều đó phụ thuộc đường triển khai cụ thể.

## 7. JAXB adapter tùy chỉnh: khi schema đúng nhưng domain model khác

### 7.1. XmlAdapter làm việc ở ranh giới nào?

Trong JAXB/Jakarta XML Binding, `XmlAdapter<ValueType, BoundType>` biến giá trị mà JAXB hiểu trên wire (`ValueType`) thành đối tượng Java muốn dùng (`BoundType`) và ngược lại.

~~~mermaid
flowchart LR
    XML["XML theo XSD"] --> JAXB["JAXB lexical value"]
    JAXB -->|unmarshal| AD["XmlAdapter"]
    AD --> JAVA["Java domain value"]
    JAVA -->|marshal| AD
    AD --> JAXB
    JAXB --> XML
~~~

Ví dụ chuyển `xs:dateTime` thành `Instant`. Contract yêu cầu timestamp phải có timezone/offset và muốn quy về một thời điểm tuyệt đối. Ta dùng adapter không phụ thuộc timezone hệ thống.

~~~java
package com.example.receipt.xml;

import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import jakarta.xml.bind.annotation.adapters.XmlAdapter;

public final class InstantOffsetAdapter
        extends XmlAdapter<String, Instant> {

    @Override
    public Instant unmarshal(String text) {
        if (text == null) {
            return null;
        }
        // Bắt buộc Z hoặc +/-HH:MM; không tự gán timezone mặc định.
        return OffsetDateTime.parse(
                text, DateTimeFormatter.ISO_OFFSET_DATE_TIME)
                .toInstant();
    }

    @Override
    public String marshal(Instant instant) {
        if (instant == null) {
            return null;
        }
        // Quy ước đầu ra: UTC ISO-8601 với hậu tố Z.
        return DateTimeFormatter.ISO_INSTANT.format(instant);
    }
}
~~~

Annotation ở trường JAXB-bound (minh họa một DTO có accessor theo field):

~~~java
import java.time.Instant;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlSchemaType;
import jakarta.xml.bind.annotation.adapters.XmlJavaTypeAdapter;

@XmlAccessorType(XmlAccessType.FIELD)
public class ReceiptXmlModel {

    @XmlElement(name = "processedAt", required = true)
    @XmlSchemaType(name = "dateTime")
    @XmlJavaTypeAdapter(InstantOffsetAdapter.class)
    private Instant processedAt;

    public Instant getProcessedAt() {
        return processedAt;
    }
    public void setProcessedAt(Instant processedAt) {
        this.processedAt = processedAt;
    }
}
~~~

**Phạm vi ví dụ:** adapter + field này minh họa cách chuyển một giá trị. Class trên không phải JAXB model hoàn chỉnh của `GetReceiptResponse` ở phần 3 (còn nhiều field và namespace), không được dùng để công bố lại WSDL code-first. Với mô hình sinh từ XSD, cần cấu hình **external binding customization** hoặc cơ chế cấu hình JAXB thích hợp để giữ adapter qua các lần regenerate; đừng sửa trực tiếp generated source rồi hy vọng thay đổi còn nguyên.

**Giới hạn có chủ đích:** `xs:dateTime` cho phép timestamp không offset, trong khi `InstantOffsetAdapter` từ chối loại đó. Đây là quy tắc ứng dụng được đưa ra bởi contract nghiệp vụ, chưa được XSD 1.0 `xs:dateTime` nguyên thủy biểu đạt hết. Nếu đối tác gửi dạng không offset nhưng vẫn coi là hợp lệ, adapter này sẽ lỗi; cần thống nhất policy với bên gửi hoặc dùng `XMLGregorianCalendar` để giữ nguyên semantics.

### 7.2. Adapter cho LocalDate chỉ khi đã rõ policy

Với `xs:date` không có timezone, Java `LocalDate` là kiểu domain tự nhiên. Nhưng `xs:date` có thể bao gồm timezone offset; adapter đơn giản sau **chỉ phù hợp** với hợp đồng quy định rõ ngày dạng `yyyy-MM-dd`, không offset:

~~~java
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import jakarta.xml.bind.annotation.adapters.XmlAdapter;

public final class IsoLocalDateAdapter
        extends XmlAdapter<String, LocalDate> {
    @Override
    public LocalDate unmarshal(String text) {
        return text == null ? null :
                LocalDate.parse(text, DateTimeFormatter.ISO_LOCAL_DATE);
    }

    @Override
    public String marshal(LocalDate date) {
        return date == null ? null :
                date.format(DateTimeFormatter.ISO_LOCAL_DATE);
    }
}
~~~

Không dùng adapter này cho mọi `xs:date` tùy ý: XSD có thể cho phép timezone và các trường hợp năm đặc biệt mà `LocalDate.parse` theo ISO_DATE thông thường không bao phủ. Với đối tác yêu cầu mọi lexical form hợp lệ của XSD, giữ `XMLGregorianCalendar` hoặc viết bộ chuyển đổi/kiểm chứng tương thích đúng profile đã chốt.

### 7.3. Adapter không nên sửa dữ liệu âm thầm

Nguyên tắc cho một `XmlAdapter` chất lượng:

1. **Xác định rõ policy:** input nào hợp lệ, timezone có bắt buộc, định dạng đầu ra có canonicalization hay không.
2. **Chuyển đổi hai chiều ổn định:** marshal/unmarshal round-trip không làm mất thông tin nghiệp vụ quan trọng.
3. **Tôn trọng null và optional:** phân biệt vắng mặt, `xsi:nil="true"` và chuỗi rỗng nếu contract có ý nghĩa khác nhau.
4. **Báo lỗi rõ:** sai định dạng thì tạo lỗi conversion được ánh xạ SOAP Fault có kiểm soát, không im lặng đổi sang default.
5. **Không giấu rounding:** nếu decimal vượt fractionDigits, từ chối hoặc áp dụng luật làm tròn đã chốt với nghiệp vụ.
6. **Không phụ thuộc máy:** tránh `ZoneId.systemDefault()`, `Locale.getDefault()` và format theo cài đặt vùng khi đang xử lý wire format.
7. **Không nhúng dữ liệu nhạy cảm vào exception/log:** đặc biệt số tài khoản, ngày sinh, tài liệu và token.

### 7.4. Có nên adapter BigDecimal thành String?

Thường **không cần**: JAXB đã ánh xạ `xs:decimal` sang `BigDecimal`. Chỉ viết adapter nếu thật sự cần domain type riêng như `Money` mang currency và quy tắc nghiệp vụ, và nhớ rằng XSD của hai field `amount` + `currency` không được tự biến thành một XML text value. Adapter JAXB một field không thể tùy tiện thay đổi cấu trúc của hai sibling elements trên wire.

Nếu muốn `Money` trong domain layer, một hướng dễ kiểm soát hơn là:

~~~java
// Boundary JAXB model vẫn có amount và currency.
BigDecimal amount = xmlResponse.getAmount();
String currency = xmlResponse.getCurrency();

// Chuyển thành domain object theo một chính sách riêng.
Money money = Money.of(amount, currency);
~~~

Đoạn này là ý tưởng tích hợp domain model: `Money` và `xmlResponse` phải được định nghĩa trong ứng dụng. Nó giữ XSD làm nguồn sự thật, đồng thời tách validation XML khỏi business rules về tiền tệ.

## 8. Cấu hình OXM và MTOM trong Spring Web Services

### 8.1. Jaxb2Marshaller cho SOAP client

Spring OXM cung cấp `org.springframework.oxm.jaxb.Jaxb2Marshaller`. Với `WebServiceTemplate`, có thể dùng một marshaller cho request và response:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.client.core.WebServiceTemplate;

@Configuration
public class ReceiptSoapClientConfig {

    @Bean
    public Jaxb2Marshaller receiptMarshaller() {
        Jaxb2Marshaller m = new Jaxb2Marshaller();
        // Package phải chứa lớp đã sinh từ XSD.
        m.setContextPath("com.example.receipt.contract");
        m.setMtomEnabled(true);
        return m;
    }

    @Bean
    public WebServiceTemplate receiptWebServiceTemplate(
            Jaxb2Marshaller receiptMarshaller) {
        WebServiceTemplate template = new WebServiceTemplate();
        template.setMarshaller(receiptMarshaller);
        template.setUnmarshaller(receiptMarshaller);
        return template;
    }
}
~~~

Để chạy được, cần JAXB API/runtime tương thích với phiên bản Spring; package `com.example.receipt.contract` thực sự chứa model mà JAXB nhận diện (`ObjectFactory` hoặc `jaxb.index` phù hợp); SOAP message factory/transport hỗ trợ attachments. `setMtomEnabled(true)` bật hỗ trợ MTOM ở JAXB marshaller; **không tự động bảo đảm server, gateway và đối tác đã hỗ trợ MTOM**.

Đối với Spring-WS `@Endpoint` ở server, method argument và return adapter có cơ chế JAXB riêng. **Không mặc định bean client `receiptMarshaller` cũng đang được mọi endpoint adapter sử dụng**. Nếu có custom `XmlAdapter` và MTOM, hãy xác minh cả chiều server/client.

### 8.2. Gọi dịch vụ với WebServiceTemplate

Ví dụ giả định `GetReceiptRequest` và `GetReceiptResponse` đã được sinh từ XSD:

~~~java
GetReceiptRequest request = new GetReceiptRequest();
request.setReceiptId("REC-1001");

GetReceiptResponse response = (GetReceiptResponse)
        receiptWebServiceTemplate.marshalSendAndReceive(
            "https://partner.example.test/soap/receipt", request);

BigDecimal amount = response.getAmount();
XMLGregorianCalendar processedAt = response.getProcessedAt();
~~~

Đoạn này minh họa luồng gọi, không phải chương trình Java độc lập. Cần import, bean injection, endpoint thực, bảo mật, timeout và fault handling. Một số schema sinh `JAXBElement<GetReceiptRequest>` và `JAXBElement<GetReceiptResponse>` qua `ObjectFactory` thay vì tạo class có root annotation; lúc đó phải marshal/unmarshal đúng root object.

### 8.3. DataHandler thay cho byte[]

Một JAXB-bound model có thể mang binary bằng `DataHandler`:

~~~java
import jakarta.activation.DataHandler;
import jakarta.xml.bind.annotation.XmlElement;
import jakarta.xml.bind.annotation.XmlMimeType;

@XmlElement(name = "document")
@XmlMimeType("application/pdf")
private DataHandler document;
~~~

Đây là **mảnh field**, không phải toàn bộ lớp JAXB. Nếu model được sinh từ XSD có `xmime:expectedContentTypes`, một số JAXB tools có thể chọn `DataHandler` thay `byte[]`; kết quả tùy tooling và binding configuration. Phải xem mã sinh thật.

Đặt nguồn file đáng tin cậy cho DTO ví dụ:

~~~java
import jakarta.activation.DataHandler;
import jakarta.activation.FileDataSource;
import java.io.File;

File file = new File("receipt.pdf");
DataHandler content = new DataHandler(new FileDataSource(file));
response.setDocument(content);
~~~

`setDocument` chỉ tồn tại nếu DTO có accessor phù hợp. Không xây đường dẫn file từ input chưa tin cậy; kiểm tra quyền, path traversal, dung lượng, content type thực và thời gian sống stream. MIME type hay phần mở rộng `.pdf` không chứng minh nội dung an toàn.

### 8.4. Vai trò các tầng với MTOM

| Tầng | Trách nhiệm |
|---|---|
| XSD/WSDL | Quy định `xs:base64Binary`, MIME hints và policy theo contract |
| JAXB model | Biểu diễn nhị phân bằng `byte[]` hoặc `DataHandler` |
| OXM | Marshal/unmarshal XML, dùng attachment khi MTOM được hỗ trợ |
| SOAP message factory | Tạo SOAP package, MIME parts và Content-ID |
| HTTP/gateway | Chuyển tiếp và giới hạn `multipart/related` |
| WS-Security | Xử lý chữ ký/mã hóa và attachments theo profile phù hợp |
| Ứng dụng | Kiểm tra kích thước, file thực, quyền truy cập và cleanup |

Một đối tác có thể hiểu **inline Base64** nhưng không hỗ trợ **MTOM**. Một bên khác có thể yêu cầu MTOM khi file lớn. Vì thế, phải kiểm tra contract và chạy test end-to-end trên tuyến HTTP/gateway thực tế.

## 9. Conversion, XSD validation và business validation là ba trách nhiệm

| Input | Conversion | XSD validation | Kiểm tra nghiệp vụ |
|---|---|---|---|
| `2026-02-30T10:00:00Z` | Parser ngày giờ có thể lỗi | Ngày không tồn tại ⇒ không hợp lệ | Không xử lý |
| `2026-11-27T09:18:00` | `XMLGregorianCalendar` đọc được; `InstantOffsetAdapter` từ chối | `xs:dateTime` thuần túy cho phép không offset | Quy tắc yêu cầu offset ⇒ từ chối |
| `123.456` | `BigDecimal` đọc được | Không thỏa `fractionDigits=2` | Không hạch toán |
| `-10.00` | `BigDecimal` đọc được | Không thỏa `minInclusive=0` | Hoàn tiền có thể cần contract khác |
| `SGVsbG8=` | Giải mã thành 5 byte | `base64Binary` hợp lệ | Không phải PDF hợp lệ |
| PDF vượt quota | Byte có thể giải mã hợp lệ | XSD có thể chưa đặt giới hạn byte | Từ chối do dung lượng |

Spring-WS có `PayloadValidatingInterceptor` để kiểm tra payload theo XSD đã cấu hình; JAXB cũng có cơ chế validation riêng tùy cách tích hợp. **Chỉ có XSD hoặc class được sinh từ XSD không tự bảo đảm runtime validate đầy đủ.**

~~~mermaid
flowchart TD
  A["SOAP request"] --> B["HTTP/MIME size và resource limits"]
  B --> C["SOAP/XML parser được bảo vệ"]
  C --> D["XSD validation"]
  D --> E["JAXB unmarshal + XmlAdapter"]
  E --> F["Business validation"]
  F --> G["Business service"]
  G --> H["Response JAXB marshal"]
  H --> I["SOAP response"]
~~~

Đây là mô hình trách nhiệm, không khẳng định chính xác thứ tự interceptor/adapter cho mọi cấu hình. Dữ liệu chưa tin cậy phải được giới hạn và kiểm tra trước khi đưa vào tầng nghiệp vụ hoặc lưu trữ.

### 9.1. Phân biệt omitted, nil và empty

- **Bỏ phần tử** chỉ hợp lệ khi `minOccurs="0"` hoặc content model cho phép.
- **`xsi:nil="true"`** chỉ hợp lệ nếu element có `nillable="true"`.
- **Element rỗng** như `<amount/>` không phải decimal hợp lệ; `<processedAt/>` không phải dateTime hợp lệ. Với `xs:base64Binary`, chuỗi rỗng có thể biểu diễn mảng byte 0 phần tử, vẫn cần business validation.

Vì vậy không nên adapter mọi trường hợp “vắng, nil, rỗng” thành giá trị mặc định giống nhau nếu contract có phân biệt.

## 10. SOAP Fault, XML security và chứng chỉ

### 10.1. Các lỗi thường gặp

Một số lỗi có thể xuất hiện **trước khi endpoint được gọi**:

- SOAP Envelope sai namespace/version hoặc XML không well-formed.
- Lỗi lexical ngày giờ, decimal, Base64 hoặc vi phạm facet/occurrence của XSD.
- `XmlAdapter` từ chối timezone thiếu hoặc định dạng không được phép.
- MIME part lỗi, Content-ID không tồn tại, kích thước vượt giới hạn.
- Chữ ký SOAP không hợp lệ, chứng chỉ không được tin cậy hoặc timestamp hết hạn.

Lỗi cần được ánh xạ thành SOAP Fault phù hợp contract, tránh đưa stack trace, local path, token hoặc raw file vào response. Spring-WS có `EndpointExceptionResolver` và SOAP fault resolver; lỗi từ parser/transport/security có thể đi qua đường xử lý khác nên phải thử cả pipeline.

### 10.2. XML parser và tài nguyên

Cần kiểm soát:

1. Giới hạn tổng HTTP body, số part MIME, kích thước từng attachment, thời gian đọc và tải CPU.
2. Cấu hình parser chống XXE/external entities; không tự tải schema/DTD chưa tin cậy.
3. Giới hạn byte **sau giải mã** Base64; kiểm tra kích thước raw XML thôi chưa đủ.
4. Không giữ tất cả file lớn vào `byte[]` nếu có nhu cầu streaming; xác minh khả năng spool/temp file/cleanup của runtime.
5. Kiểm tra file thực tế, không dựa duy nhất vào tên, extension, MIME header hoặc `@XmlMimeType`.
6. Bảo vệ quá trình xác minh XML signature, canonicalization và attachments trước payload phức tạp độc hại.

### 10.3. WS-Security khi dùng MTOM

TLS/HTTPS bảo vệ kênh truyền; WS-Security có thể bảo vệ các phần của SOAP message bằng chữ ký, mã hóa, token, timestamp. Với MTOM/XOP:

- Biểu diễn optimized attachment khác inline Base64; chữ ký và canonicalization phải xử lý theo profile/transform tương thích.
- Cần kiểm tra chính sách attachment security và hỗ trợ thực tế của Spring-WS/CXF, gateway và đối tác.
- Không giả định bật MTOM giữ nguyên hành vi chữ ký SOAP Body; chạy kiểm thử xác minh chữ ký hai chiều.
- Keystore, truststore, certificate chain, rotation, chống replay và ủy quyền nghiệp vụ độc lập với JAXB/OXM.
- Không log toàn bộ SOAP Body/attachment nếu chứa tài liệu hoặc dữ liệu nhạy cảm.

Nếu đối tác không hỗ trợ MTOM hoặc profile WS-Security được yêu cầu, các bên phải thống nhất phương án khác. Không tự đổi XSD/WSDL chính thức chỉ để phù hợp một runtime.

## 11. Kiểm thử marshalling/unmarshalling có ý nghĩa

Không chỉ kiểm tra object được tạo. Với SOAP, cần so cả **giá trị Java** và **XML phát sinh** theo hợp đồng. Một ma trận tối thiểu:

| Nhóm | Input kiểm thử | Kết quả cần chứng minh |
|---|---|---|
| Ngày giờ | `2026-11-27T09:18:00+07:00` và `2026-11-27T02:18:00Z` | Hai giá trị cùng instant dù lexical khác |
| Ngày giờ | `2026-11-27T09:18:00` không offset | Adapter theo policy từ chối, hoặc xử lý theo contract khác đã thống nhất |
| Ngày giờ | Ngày không tồn tại, thời điểm có phần giây thập phân | XSD/parser chấp nhận hoặc từ chối đúng |
| Ngày nghiệp vụ | `2026-11-27` ở server timezone khác | `LocalDate`/calendar date không bị dịch sang ngày khác |
| Decimal | `0`, `125000.50`, giới hạn `totalDigits` | Không mất precision, XSD validation đúng |
| Decimal | `-1.00`, `123.456`, `1.2E3` | Trả lỗi lexical/facet, không tự làm tròn |
| Binary inline | `SGVsbG8=` | Giải mã đúng 5 byte của chuỗi `Hello` |
| Binary sai | Base64 chứa ký tự/độ dài không hợp lệ | Bị xử lý như input không hợp lệ |
| MTOM | Tệp lớn với MIME/XOP attachment | SOAP + attachment round-trip, bytes và checksum không đổi |
| Compatibility | Client Java/CXF hoặc .NET sinh từ WSDL | Interoperability thực tế với namespace, SOAP Fault và policy |

### 11.1. Test adapter theo giá trị tuyệt đối

Với `InstantOffsetAdapter` ở phần 7, một bài test JUnit 5 minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import org.junit.jupiter.api.Test;

class InstantOffsetAdapterTest {
    private final InstantOffsetAdapter adapter =
            new InstantOffsetAdapter();

    @Test
    void convertsDifferentOffsetsToSameInstant() {
        Instant fromHcm =
                adapter.unmarshal("2026-11-27T09:18:00+07:00");
        Instant fromUtc =
                adapter.unmarshal("2026-11-27T02:18:00Z");

        assertEquals(fromUtc, fromHcm);
        assertEquals("2026-11-27T02:18:00Z",
                adapter.marshal(fromHcm));
    }

    @Test
    void rejectsTimestampWithoutOffset() {
        assertThrows(DateTimeParseException.class,
                () -> adapter.unmarshal("2026-11-27T09:18:00"));
    }
}
~~~

Bài test này xác minh **quy tắc adapter**; chưa kiểm tra annotation JAXB được gắn đúng property hay có ảnh hưởng đến WSDL. Cần thêm bài test marshal/unmarshal JAXB, validate XML với XSD và integration test qua SOAP.

### 11.2. Test BigDecimal

Đối chiếu:

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

assert a.compareTo(b) == 0;
assert !a.equals(b);

BigDecimal amount = new BigDecimal("125000.50");
assert amount.compareTo(new BigDecimal("125000.50")) == 0;
~~~

Trong thực tế nên dùng JUnit assertions thay cho Java `assert` nếu không muốn phụ thuộc JVM flag `-ea`. Code trên chỉ minh họa semantics. Để test XSD facet, hãy tạo XML với `amount` hợp lệ và không hợp lệ rồi chạy **schema validator**; test `BigDecimal` riêng không thay thế được.

### 11.3. Test binary đúng dữ liệu gốc

Với file nhị phân, so sánh **mảng byte hoặc SHA-256 của byte gốc** giữa trước gửi và sau nhận, thay vì so MIME boundary hoặc chuỗi Base64, vì các cách biểu diễn trên wire có thể khác nhau nhưng dữ liệu nhị phân tương đương.

Ví dụ so SHA-256, chỉ nhằm kiểm chứng tính toàn vẹn dữ liệu trong bài test:

~~~java
import java.security.MessageDigest;
import java.util.Arrays;

byte[] before = ...;  // Byte gốc đọc trong test fixture.
byte[] after = ...;   // Byte được nhận và giải mã qua SOAP.

byte[] digestBefore =
        MessageDigest.getInstance("SHA-256").digest(before);
byte[] digestAfter =
        MessageDigest.getInstance("SHA-256").digest(after);

if (!Arrays.equals(digestBefore, digestAfter)) {
    throw new AssertionError("Binary payload changed during SOAP transfer");
}
~~~

Đây không phải chữ ký số hay cơ chế xác thực người gửi; SHA-256 được dùng ở đây như phương tiện kiểm tra dữ liệu trong test. Với yêu cầu an ninh, dùng signature/MAC hoặc WS-Security theo chính sách được thỏa thuận.

## 12. Tương thích và versioning khi thay đổi ánh xạ

Một thay đổi ở Java có thể là thay đổi nội bộ **hoặc** có thể vô tình làm đổi XML phát ra. Hãy phân biệt:

| Thay đổi | Ảnh hưởng cần kiểm tra |
|---|---|
| Đổi `XMLGregorianCalendar` sang `Instant` + adapter, vẫn phát XML theo schema cũ | Có thể an toàn nếu nhận đúng toàn bộ giá trị đối tác gửi và không đổi semantics |
| Tự động chuyển dateTime không timezone sang UTC | Có nguy cơ đổi **ý nghĩa thời điểm**, không an toàn nếu chưa thỏa thuận |
| Đổi `xs:decimal` sang `xs:double` | Thay contract và precision, có thể phá client |
| Thêm `fractionDigits` chặt hơn | Giá trị trước đây hợp lệ có thể bị từ chối |
| Đổi `xs:base64Binary` sang `xs:hexBinary` | Thay lexical XML và cấu trúc hợp đồng |
| Bật MTOM nhưng XSD giữ base64Binary | Schema type không đổi, nhưng transport/package/policy phải được client hỗ trợ |
| Đổi field optional thành required | Client cũ có thể thiếu field |
| Thay JAXB-generated class/namespace | Có thể đổi QName root hoặc child elements nếu mapping không được giữ ổn định |

Không tuyên bố tương thích chỉ vì mã Java biên dịch hoặc cùng một service trả HTTP 200. Kiểm tra các phần tử XML thực, namespace, offset, decimal text, binary bytes, SOAP Fault và bảo mật trong môi trường đối tác.

### Một ca lỗi thường gặp

Hệ thống lưu `processedAt` bằng Java `LocalDateTime`; adapter dùng timezone mặc định trên máy. Ở Việt Nam, một timestamp không offset được hiểu là `09:18 +07:00`; trên máy chủ đặt UTC, nó bị hiểu thành `09:18Z`. Cùng một XML tạo hai thời điểm cách nhau bảy giờ. Đây là **lỗi semantics tại lớp ánh xạ**, không phải lỗi Java parser. Giải pháp là chốt chính sách timezone trong contract và từ chối đầu vào thiếu thông tin nếu nghiệp vụ yêu cầu instant.

Một ca khác: tiền `125000.50` được chuyển qua `double` rồi ghi database dưới dạng decimal. Dữ liệu có thể bị sai khi qua các phép tính hoặc thao tác làm tròn; SOAP sử dụng `xs:decimal` không cứu được precision đã mất ở Java. Giữ `BigDecimal` xuyên suốt pipeline tiền tệ là biện pháp thiết kế căn bản.

## 13. Bài tập thực hành có gợi ý

### Bài 1 — Cùng thời điểm hay không?

Hai giá trị:

~~~text
2026-11-27T09:18:00+07:00
2026-11-27T02:18:00Z
~~~

**Câu hỏi:** Chúng có cùng instant không? Adapter `InstantOffsetAdapter` sẽ trả gì?

**Gợi ý:** Có, cả hai bằng `2026-11-27T02:18:00Z`. Nếu cần lưu offset nguyên gốc để hiển thị hợp đồng, `Instant` không giữ thông tin đó; cân nhắc `OffsetDateTime` hoặc trường riêng.

### Bài 2 — XSD chấp nhận nhưng adapter từ chối

`xs:dateTime` trong XSD 1.0 có thể chấp nhận `2026-11-27T09:18:00`. Tại sao adapter ví dụ từ chối?

**Gợi ý:** Bởi ứng dụng đặt policy **bắt buộc offset** để chuyển thành instant duy nhất. Đây là một hạn chế bổ sung so với kiểu XSD cơ sở; phải được công bố/thống nhất và kiểm thử tương thích.

### Bài 3 — Decimal và làm tròn

Input XML ghi `<amount>123.456</amount>` cho XSD `fractionDigits="2"`. Có nên tự làm tròn thành `123.46` khi unmarshalling?

**Gợi ý:** Không làm âm thầm. Đây là một input không thỏa contract. Nếu nghiệp vụ muốn cho phép ba chữ số rồi làm tròn, phải định nghĩa quy tắc và schema tương ứng.

### Bài 4 — Binary và MTOM

Một SOAP client gửi PDF 15 MiB bằng Base64 inline và server dùng `byte[]` để nhận. Những vấn đề nào cần kiểm tra trước khi chuyển sang MTOM?

**Gợi ý:** Dung lượng request/decoded bytes, quota MIME, memory/streaming, XOP support ở server/gateway/client, chính sách WS-Security attachments, xử lý Content-ID và kiểm thử checksum byte gốc.

### Bài 5 — Kiểm thử fault

Đối tác gửi chuỗi `abc` vào element `amount` khai báo `xs:decimal`. Endpoint không được gọi. Đây là loại lỗi nào?

**Gợi ý:** Lỗi cú pháp/kiểu XML ở ranh giới OXM/XSD. Cần trả SOAP Fault được kiểm soát qua stack, không kết luận business service xử lý sai và không phơi stack trace.

## 14. Checklist trước khi công bố SOAP contract

- [ ] XSD dùng đúng `xs:date`, `xs:time`, `xs:dateTime`, `xs:decimal` và binary type theo ý nghĩa dữ liệu.
- [ ] Quy tắc timezone/offset được thống nhất cho từng field; không tự áp dụng timezone mặc định.
- [ ] `BigDecimal` giữ precision; rounding, scale và currency là quy tắc có chủ đích.
- [ ] Mọi `XmlAdapter` xử lý null, input không hợp lệ, round-trip và thông tin bị mất.
- [ ] JAXB model và namespace được sinh từ đúng XSD, không sửa generated code tùy tiện.
- [ ] Có test cả XML lexical form và schema validation, ngoài test Java object.
- [ ] Đã xác định ngưỡng dung lượng và chọn inline Base64/MTOM phù hợp.
- [ ] MIME attachments được giới hạn, kiểm tra nội dung thật, xử lý stream/temp file an toàn.
- [ ] Client Spring-WS và client độc lập xác nhận payload QName, SOAP Fault và binary bytes.
- [ ] WS-Security, TLS/chứng chỉ, XML parser security và chính sách attachment được kiểm thử.
- [ ] Có bộ mẫu XML/MTOM và test hồi quy để phát hiện thay đổi sau nâng JAXB/Spring-WS/CXF.
- [ ] Không nhầm marshalling/unmarshalling thành công với contract, business hay security validation thành công.

**Ghi nhớ:** Thiết kế OXM tốt trong Spring Web Services giữ **XSD/WSDL làm hợp đồng**, dùng `XMLGregorianCalendar` hoặc adapter có chính sách rõ cho ngày giờ, giữ `BigDecimal` cho decimal, chọn `byte[]`/`DataHandler` và MTOM theo dung lượng, đồng thời kiểm thử XML, SOAP Fault và bảo mật bằng client thực. Mục tiêu là bảo toàn ý nghĩa dữ liệu và khả năng tương thích xuyên hệ thống, chứ không chỉ chuyển đổi Java object thành công.
