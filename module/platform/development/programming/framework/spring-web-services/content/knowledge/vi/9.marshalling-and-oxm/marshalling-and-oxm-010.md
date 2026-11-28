# Kiểm tra chuyển đổi hai chiều bằng bộ dữ liệu biên của hợp đồng

## 1. Mục tiêu: chứng minh dữ liệu giữ đúng ý nghĩa sau mỗi lần chuyển đổi

Trong Spring Web Services (Spring-WS), **marshalling** chuyển đối tượng Java thành XML, còn **unmarshalling** chuyển XML thành đối tượng Java. Với SOAP theo hướng **contract-first**, chúng ta thường dùng XSD/WSDL làm nguồn xác định hợp đồng, dùng JAXB làm công cụ ánh xạ và `Jaxb2Marshaller` của Spring OXM làm cầu nối với endpoint và SOAP client.

Điều dễ nhầm là: **marshalling thành công không có nghĩa XML hợp XSD**, và **unmarshalling thành công không có nghĩa mọi thông tin của thông điệp vẫn được bảo toàn**. Một `BigDecimal` có thể bị xử lý sai scale; trạng thái “element vắng mặt” có thể bị gộp với `xsi:nil`; thời gian có offset có thể vô tình mất múi giờ; danh sách Java có thể rỗng mặc dù XSD yêu cầu ít nhất một phần tử.

Vì vậy, ngoài kiểm thử “một đối tượng đơn giản chuyển qua lại được”, cần xây dựng **bộ dữ liệu biên bám sát XSD** và kiểm tra theo cả hai chiều.

Bài thuộc chương **Marshalling và OXM** trong module **SPRING_WEB_SERVICES**. Nội dung tập trung vào JAXB, `Jaxb2Marshaller`, XML Schema validation, endpoint/client và kiểm thử tương thích để tích hợp SOAP ổn định với hệ thống doanh nghiệp.

Sau bài học, bạn có thể:

- Phân biệt kiểm thử **Java → XML → Java** và **XML → Java → XML**, cùng những giới hạn của mỗi chiều.
- Trích xuất các trường hợp biên từ XSD: `minOccurs`, `maxOccurs`, `nillable`, `default`, `fixed`, `enumeration`, `pattern`, `fractionDigits`, `totalDigits`, ngày giờ và namespace.
- Viết test sử dụng JAXB binding sinh từ XSD và Spring OXM, kiểm tra kết quả về mặt **giá trị và QName**.
- Kiểm tra dữ liệu **không hợp lệ** phải bị từ chối, kể cả chiều Java → XML.
- Phân biệt thay đổi cách biểu diễn XML hợp lệ với **mất ngữ nghĩa**.
- Mở rộng test lên tầng SOAP, SOAP Fault và client độc lập với Java.

## 2. Hai chiều round-trip kiểm tra những điều khác nhau

### 2.1. Chiều A: Java → XML → Java

Khởi tạo một đối tượng JAXB, marshal thành XML, rồi unmarshal XML đó về Java.

~~~mermaid
flowchart LR
    A["JAXB object J"] --> B["marshal"]
    B --> C["XML X"]
    C --> D["Kiểm tra XSD và QName"]
    D --> E["unmarshal"]
    E --> F["JAXB object J'"]
    F --> G["So sánh giá trị và ý nghĩa"]
~~~

Bất biến mong muốn là:

~~~text
unmarshal(marshal(J)) ≈ J
~~~

Dấu `≈` ở đây là **tương đương theo ngữ nghĩa hợp đồng**: các trường có ý nghĩa phải giữ nguyên, gồm root QName, danh sách, giá trị tiền tệ, trường optional/nil và thông tin ngày giờ quan trọng.

Chiều này phát hiện lỗi như marshal sai element root, mất phần tử, dùng kiểu số không phù hợp, hoặc chuyển đổi ngày giờ không đối xứng.

Tuy nhiên, **test chỉ có các object do chính Java tạo ra chưa đủ**: object có thể không tạo được trạng thái XML đặc biệt hoặc không phản ánh cách client bên ngoài thực sự gửi XML.

### 2.2. Chiều B: XML → Java → XML

Lấy một XML fixture được thiết kế **độc lập từ XSD**, unmarshal sang Java, rồi marshal lại thành XML.

~~~mermaid
flowchart LR
    A["XML fixture X"] --> B["Kiểm tra XSD"]
    B --> C["unmarshal"]
    C --> D["JAXB object J"]
    D --> E["marshal"]
    E --> F["XML X'"]
    F --> G["Kiểm tra XSD + so sánh ngữ nghĩa XML"]
~~~

Bất biến mong muốn:

~~~text
marshal(unmarshal(X)) ≈ X
~~~

Ở chiều này, **không nên đòi hỏi XML sau round-trip giống từng byte**. Prefix namespace, dấu nháy thuộc tính, thứ tự attribute, indentation, CDATA và cách viết số/ngày giờ có thể thay đổi hợp lệ.

Mục tiêu đúng là kiểm tra:

1. Root QName và các QName con được giữ đúng.
2. Giá trị dữ liệu có cùng ý nghĩa theo XSD/ứng dụng.
3. Không mất phần tử/attribute mà hợp đồng yêu cầu bảo toàn.
4. Thứ tự phần tử vẫn hợp `xs:sequence`.
5. XML tạo ra tiếp tục hợp lệ với XSD.
6. Những trạng thái mà nghiệp vụ phân biệt như **absent/nil/empty** không bị gom lại trái ý định.

### 2.3. Chiều thứ ba: dữ liệu sai phải bị chặn

Ngoài hai round-trip thành công, cần kiểm tra cả hai đường đi:

| Dữ liệu sai | Kiểm thử cần làm |
|---|---|
| XML từ đối tác không hợp XSD | Unmarshal có bật schema validation phải từ chối hoặc trả lỗi được ứng dụng xử lý |
| Java object thiếu trường required hoặc vi phạm facet | Marshal có bật schema validation phải từ chối, hoặc pipeline trước/sau marshal phải phát hiện |
| SOAP Body sai QName/namespace | SOAP endpoint không được âm thầm xử lý như request hợp lệ |
| Thông điệp có dữ liệu nghiệp vụ không hợp lệ nhưng đúng XSD | Domain validation xử lý và sinh SOAP Fault nghiệp vụ thích hợp |

**Điểm cần nhớ:** JAXB là công cụ binding. Nếu không cấu hình schema validation, JAXB có thể đọc hoặc ghi XML không thỏa hết các ràng buộc của XSD.

## 3. Tạo hợp đồng XSD làm cơ sở sinh bộ dữ liệu biên

Hãy xây dựng một dịch vụ `SubmitOrder` đơn giản. Request có các thuộc tính khiến kiểm thử biên trở nên cần thiết:

- `customerId` là chuỗi bắt buộc.
- `amount` là số thập phân tiền tệ, có giới hạn min/max và hai chữ số phần thập phân.
- `currency` chỉ nhận `VND` hoặc `USD`.
- `requestedAt` là `xs:dateTime`.
- `note` optional và nillable, giới hạn chiều dài 80 ký tự.
- `item` xuất hiện ít nhất một, tối đa ba lần.
- `correlationId` là attribute bắt buộc.

XSD minh họa, lưu tại `src/main/resources/xsd/orders-v1.xsd`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified"
    attributeFormDefault="unqualified">

    <xs:simpleType name="AmountType">
        <xs:restriction base="xs:decimal">
            <xs:totalDigits value="12"/>
            <xs:fractionDigits value="2"/>
            <xs:minInclusive value="0.01"/>
            <xs:maxInclusive value="9999999999.99"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="CurrencyType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="VND"/>
            <xs:enumeration value="USD"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="NoteType">
        <xs:restriction base="xs:string">
            <xs:maxLength value="80"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="QuantityType">
        <xs:restriction base="xs:positiveInteger">
            <xs:maxInclusive value="50"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="OrderItemType">
        <xs:sequence>
            <xs:element name="sku" type="xs:string"/>
            <xs:element name="quantity" type="ord:QuantityType"/>
        </xs:sequence>
    </xs:complexType>

    <xs:complexType name="SubmitOrderRequestType">
        <xs:sequence>
            <xs:element name="customerId" type="xs:string"/>
            <xs:element name="amount" type="ord:AmountType"/>
            <xs:element name="currency" type="ord:CurrencyType"/>
            <xs:element name="requestedAt" type="xs:dateTime"/>
            <xs:element name="note"
                        type="ord:NoteType"
                        minOccurs="0"
                        nillable="true"/>
            <xs:element name="item"
                        type="ord:OrderItemType"
                        minOccurs="1"
                        maxOccurs="3"/>
        </xs:sequence>
        <xs:attribute name="correlationId"
                      type="xs:string"
                      use="required"/>
    </xs:complexType>

    <xs:element name="SubmitOrderRequest"
                type="ord:SubmitOrderRequestType"/>
</xs:schema>
~~~

Hợp đồng này cố tình giữ các ràng buộc dễ kiểm chứng. Trong hệ thống thực, cần thêm kiểm tra nghiệp vụ như quyền đặt hàng, SKU tồn tại, tiền tệ được hỗ trợ hay ngưỡng giao dịch.

### 3.1. XML hợp lệ làm ca chuẩn

~~~xml
<ord:SubmitOrderRequest
    xmlns:ord="urn:example:orders:v1"
    correlationId="REQ-001">
    <ord:customerId>C-1001</ord:customerId>
    <ord:amount>125000.50</ord:amount>
    <ord:currency>VND</ord:currency>
    <ord:requestedAt>2026-11-27T09:30:00+07:00</ord:requestedAt>
    <ord:note>Giao hàng trước 17 giờ</ord:note>
    <ord:item>
        <ord:sku>BOOK-01</ord:sku>
        <ord:quantity>2</ord:quantity>
    </ord:item>
</ord:SubmitOrderRequest>
~~~

Các đặc điểm nên assert:

| Trường | Kỳ vọng |
|---|---|
| Root QName | `{urn:example:orders:v1}SubmitOrderRequest` |
| `correlationId` | Attribute không namespace với giá trị `REQ-001` |
| `amount` | Giá trị thập phân `125000.50` |
| `currency` | `VND` |
| `requestedAt` | Có offset `+07:00` |
| `note` | Chuỗi Unicode tiếng Việt |
| `item` | Một phần tử, quantity bằng 2 |

**Chú ý:** Ký tự tiếng Việt phải được xử lý bằng UTF-8 nhất quán. Không so sánh byte XML nếu marshaller thay đổi entity escaping, ví dụ `&amp;` thay cho `&` ở cùng giá trị chuỗi sau parse.

## 4. Sinh bộ dữ liệu biên trực tiếp từ từng ràng buộc

Một test tốt không chỉ thử dữ liệu trung bình. Với mỗi constraint, hãy có ca ở **ranh giới hợp lệ**, ca **ngay ngoài ranh giới** và ca **thiếu hoặc hiện diện khác kỳ vọng**.

### 4.1. Ma trận trường bắt buộc và namespace

| Trường hợp | Dữ liệu | Kỳ vọng schema |
|---|---|---|
| Đủ trường required | `customerId`, `amount`, `currency`, `requestedAt`, ít nhất một `item` | Hợp lệ |
| Thiếu `customerId` | Bỏ element | Không hợp lệ |
| Thiếu `correlationId` | Bỏ attribute | Không hợp lệ |
| `customerId` rỗng | `<customerId/>` với `xs:string` không giới hạn | Hợp lệ **theo XSD minh họa**, có thể sai nghiệp vụ |
| Sai namespace của root | `urn:example:orders:v2` | Không khớp global element v1 |
| Đổi prefix nhưng giữ URI | `a:SubmitOrderRequest` với cùng namespace | Hợp lệ |
| Sai thứ tự `xs:sequence` | `currency` trước `amount` | Không hợp lệ |
| `amount xsi:nil="true"` | Element không khai báo `nillable` | Không hợp lệ |

Không nên viết test rằng `customerId=""` luôn sai nếu XSD chỉ khai báo `xs:string`. Muốn cấm chuỗi rỗng, phải thêm `xs:minLength` hoặc quy tắc nghiệp vụ tương ứng.

### 4.2. Ma trận số tiền, precision và scale

XSD sử dụng `xs:decimal` với `minInclusive=0.01`, `maxInclusive=9999999999.99`, `totalDigits=12` và `fractionDigits=2`.

| Ca | Giá trị `amount` | Kỳ vọng |
|---|---:|---|
| M1 | `0.01` | Hợp lệ, bằng min |
| M2 | `0.02` | Hợp lệ |
| M3 | `125000.50` | Hợp lệ |
| M4 | `9999999999.99` | Hợp lệ, bằng max |
| M5 | `0` | Không hợp lệ, dưới min |
| M6 | `-1.00` | Không hợp lệ, dưới min |
| M7 | `10000000000.00` | Không hợp lệ, vượt max |
| M8 | `1.231` | Không hợp lệ, vượt hai chữ số thập phân |
| M9 | `abc` | Không phải lexical form của `xs:decimal` |

Trong Java, ưu tiên `BigDecimal` cho tiền tệ; tránh `double` khi yêu cầu độ chính xác thập phân.

~~~java
BigDecimal exact = new BigDecimal("125000.50");

// Không nên tạo số tiền thập phân bằng new BigDecimal(0.1):
BigDecimal fromBinary = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` nhận giá trị nhị phân của `double`, không tạo chính xác số thập phân 0.1. Trong test, dùng chuỗi hoặc `BigDecimal.valueOf(...)` phù hợp.

**Đặc biệt:** `BigDecimal.equals()` so cả `scale`; `new BigDecimal("1.0")` và `new BigDecimal("1.00")` có giá trị số bằng nhau theo `compareTo() == 0` nhưng `equals()` là false. Hãy quyết định contract cần **bảo toàn giá trị** hay **bảo toàn quy ước scale nội bộ**. XSD `fractionDigits` kiểm soát số chữ số thập phân theo value space, không nhất thiết đảm bảo giữ cách viết ban đầu sau JAXB round-trip.

### 4.3. Ma trận danh sách và số lần xuất hiện

Với `item minOccurs="1" maxOccurs="3"`:

| Ca | Số `item` | Kỳ vọng |
|---|---:|---|
| L1 | 0 | Không hợp lệ |
| L2 | 1 | Hợp lệ, biên dưới |
| L3 | 2 | Hợp lệ |
| L4 | 3 | Hợp lệ, biên trên |
| L5 | 4 | Không hợp lệ |

Với `quantity` kiểu `positiveInteger` và `maxInclusive=50`, cần thêm:

| Ca | `quantity` | Kỳ vọng |
|---|---:|---|
| Q1 | 1 | Hợp lệ, biên dưới |
| Q2 | 50 | Hợp lệ, biên trên |
| Q3 | 0 | Không hợp lệ |
| Q4 | -1 | Không hợp lệ |
| Q5 | 51 | Không hợp lệ |

XJC thường sinh một **live list** từ `maxOccurs > 1`:

~~~java
request.getItem().add(orderItem);
~~~

Danh sách Java tự nó thường không cấm 0 hoặc 4 phần tử. Nếu không bật schema validation ở chiều marshal, có thể tạo ra XML vi phạm cardinality mà marshaller vẫn ghi được.

### 4.4. Optional, nil, empty và có giá trị

Element `note` có:

~~~xml
<xs:element name="note"
            type="ord:NoteType"
            minOccurs="0"
            nillable="true"/>
~~~

Bốn mẫu khác nhau:

**Không gửi `note`:**

~~~xml
<!-- Trong SubmitOrderRequest không xuất hiện element note -->
~~~

**Có `note` với nil:**

~~~xml
<ord:note
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

**Có `note` rỗng:**

~~~xml
<ord:note xmlns:ord="urn:example:orders:v1"/>
~~~

**Có `note` chứa Unicode:**

~~~xml
<ord:note xmlns:ord="urn:example:orders:v1">Giao trước 17 giờ</ord:note>
~~~

Với `NoteType` chỉ hạn chế `maxLength=80`, các trạng thái này đều hợp lệ về XSD. Chúng **có thể mang ngữ nghĩa khác nhau** nếu contract nghiệp vụ quy định absent = giữ nguyên, nil = xóa, empty = đặt chuỗi rỗng.

Lúc nhận XML, một binding `String` nullable có thể gộp một số trạng thái thành `null`. XJC có thể sinh `JAXBElement<String>` hoặc một cấu trúc khác để giữ trạng thái element hiện diện và nil, tùy schema và cấu hình binding.

Đừng mặc định `getNote() == null` cho biết dữ liệu nguồn vắng mặt hay nil. Cần kiểm tra object thực sự sinh ra và, nếu có yêu cầu giữ phân biệt, viết test đọc XML rồi kiểm tra trạng thái sau JAXB và sau mapper nghiệp vụ.

### 4.5. Enumeration và giá trị không biết

Với `CurrencyType` giới hạn hai giá trị:

| Đầu vào | XSD |
|---|---|
| `VND` | Hợp lệ |
| `USD` | Hợp lệ |
| `vnd` | Không hợp lệ vì enum phân biệt chữ hoa/thường |
| `EUR` | Không hợp lệ theo hợp đồng hiện tại |
| Element `currency` vắng mặt | Không hợp lệ |

Khi JAXB tạo enum Java, việc dùng một enum value không có trong Java là không thể theo kiểu thông thường. Vì vậy, để kiểm tra đầu vào lạ như `EUR`, phải dùng **fixture XML bên ngoài**, không chỉ xây object Java bằng generated class.

Khi thêm một currency code mới vào XSD, kiểm thử tương thích phải đánh giá client cũ: nó có thể không giải mã được giá trị enum mới trong response dù server mới chấp nhận.

### 4.6. Ngày giờ và múi giờ

XSD dùng `xs:dateTime`, có thể mang offset hoặc không mang timezone tùy giá trị:

~~~xml
<ord:requestedAt>2026-11-27T09:30:00+07:00</ord:requestedAt>
<ord:requestedAt>2026-11-27T02:30:00Z</ord:requestedAt>
<ord:requestedAt>2026-11-27T09:30:00</ord:requestedAt>
~~~

Hai giá trị đầu biểu diễn **cùng một thời điểm tuyệt đối**. Giá trị thứ ba không cung cấp timezone và **không thể tự coi là UTC**.

JAXB sinh từ `xs:dateTime` thường dùng `XMLGregorianCalendar`; một số dự án có `XmlAdapter` chuyển sang `OffsetDateTime`, `Instant` hoặc `LocalDateTime`. Các adapter phải có chính sách rõ ràng về timezone và precision.

Nên kiểm thử:

- Thời điểm có offset dương và âm.
- Mốc giao ngày khi chuyển sang UTC.
- Thời điểm có `Z`.
- Thời điểm không có timezone, nếu contract cho phép.
- Phần giây thập phân.
- Giá trị sai lexical form, ví dụ tháng 13.

Không so sánh hai `xs:dateTime` bằng chuỗi khi mục tiêu là cùng một instant. Nhưng cũng **không dùng `Instant` để gộp dữ liệu không có timezone** nếu chưa có quy tắc nghiệp vụ cho trường hợp đó.

### 4.7. Chuỗi Unicode, whitespace và ký tự XML

Kiểm thử chuỗi nên có:

- Dấu tiếng Việt, ví dụ `Giao hàng tại Đà Nẵng`.
- Ký tự phải escape như `&` và `<`.
- Chuỗi chỉ gồm khoảng trắng.
- Chuỗi rỗng.
- Chuỗi dài đúng 80 ký tự và 81 ký tự.
- Ký tự Unicode ngoài BMP, nếu hợp đồng cần, để xác định cách đo độ dài theo code point và cách ứng dụng Java xử lý surrogate pairs.

Ví dụ XML:

~~~xml
<ord:note xmlns:ord="urn:example:orders:v1">
    Giao hàng &amp; gửi hóa đơn điện tử
</ord:note>
~~~

Unmarshaller trả về chuỗi chứa dấu `&` thật, không giữ nguyên biểu diễn entity `&amp;`. Cần so **giá trị sau parse**. Khi dùng `xs:maxLength`, số ký tự theo XML Schema không luôn bằng `String.length()` của Java đối với ký tự Unicode biểu diễn bằng surrogate pair. Nếu dữ liệu này quan trọng, thiết kế phép đo và test nhất quán.

## 5. Tổ chức fixture để test có thể lặp lại

Một bộ fixture nên phản ánh XSD đã công bố, không chỉ những object dễ tạo trong Java.

Bố cục ví dụ:

~~~text
src/test/resources/contract/orders-v1/
├── valid/
│   ├── basic.xml
│   ├── amount-min.xml
│   ├── amount-max.xml
│   ├── items-min.xml
│   ├── items-max.xml
│   ├── note-absent.xml
│   ├── note-nil.xml
│   ├── note-empty.xml
│   ├── unicode.xml
│   └── datetime-offset.xml
└── invalid/
    ├── amount-below-min.xml
    ├── amount-fraction-overflow.xml
    ├── quantity-zero.xml
    ├── items-zero.xml
    ├── items-four.xml
    ├── currency-unknown.xml
    ├── missing-correlation-id.xml
    ├── wrong-namespace.xml
    ├── wrong-sequence.xml
    └── nil-required-field.xml
~~~

Đây là **cấu trúc gợi ý cho dự án thực tế**, không phải các file được tạo ra bởi bài học. Mỗi file nên đi kèm kỳ vọng rõ ràng: hợp lệ hay không hợp lệ, và trường nào phải được giữ sau round-trip.

### 5.1. Tránh tạo fixture chỉ từ JAXB rồi dùng nó tự kiểm tra JAXB

Nếu mọi XML fixture được sinh bằng chính marshaller đang kiểm thử, một lỗi cấu hình QName hoặc adapter có thể xuất hiện ở cả hai chiều và khiến test vẫn “xanh”.

Hãy có một số XML fixture **viết độc lập dựa trên hợp đồng XSD/WSDL**, lưu trong version control. Với SOAP service đã công bố, có thể lấy thêm payload đại diện (đã loại bỏ dữ liệu nhạy cảm) của các đối tác và đóng băng chúng làm regression fixtures.

### 5.2. Ma trận test thay vì thử mọi tổ hợp

Một schema có hàng chục field, mỗi field vài trạng thái biên, sẽ tạo quá nhiều tổ hợp nếu lấy toàn bộ Cartesian product.

Cách tiếp cận thực tế:

1. Chọn một fixture **baseline hợp lệ**.
2. Mỗi lần thay đổi đúng một đặc tính để kiểm tra boundary rõ ràng.
3. Thêm một số ca kết hợp rủi ro cao, ví dụ note nil + nhiều item + amount max.
4. Dùng pairwise hoặc property-based testing khi có nhiều quy tắc tương tác.
5. Ưu tiên các ca liên quan tiền, thời gian, nillability, cấu trúc XML và data conversion của đối tác.

## 6. Cấu hình Spring OXM với JAXB và schema validation

Spring OXM cung cấp abstraction `Marshaller` và `Unmarshaller`. `Jaxb2Marshaller` là implementation thường dùng cho JAXB.

Ví dụ cấu hình bằng Java:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

@Configuration
public class OrderXmlBindingConfig {

    @Bean
    public Jaxb2Marshaller orderMarshaller() {
        Jaxb2Marshaller marshaller = new Jaxb2Marshaller();

        marshaller.setContextPath(
            "com.example.contract.orders.v1"
        );

        marshaller.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );

        return marshaller;
    }
}
~~~

Ở đây giả định XJC đã sinh các lớp `SubmitOrderRequestType`, `ObjectFactory` và enum liên quan vào package `com.example.contract.orders.v1`. Import phù hợp hệ JAXB Jakarta; dự án Java EE cũ có thể dùng JAXB `javax.xml.bind` và phiên bản Spring tương ứng.

Vai trò của từng cấu hình:

- `setContextPath(...)`: khởi tạo JAXBContext cho package binding, gồm các khai báo phần tử từ `ObjectFactory`.
- `setSchema(...)`: cung cấp XSD để kiểm tra khi JAXB marshal/unmarshal theo cách implementation hỗ trợ.
- Khi dùng schema có `xs:import`/`xs:include`, cần thêm schema resources hoặc schema resolver phù hợp để bộ biên dịch schema tìm được toàn bộ phụ thuộc.

**Quan trọng:** `Jaxb2Marshaller` không tự tạo JAXB class từ XSD ở runtime. XJC là bước **sinh mã tại thời gian build**. `Jaxb2Marshaller` chỉ chuyển đổi dựa trên những lớp và metadata đã có.

### 6.1. Không nhập nhằng giữa validation ở OXM và validation ở endpoint

Trong Spring-WS, `PayloadValidatingInterceptor` có thể kiểm tra XML tại ranh giới SOAP, còn `Jaxb2Marshaller#setSchema` cung cấp validation khi trực tiếp marshal/unmarshal.

Hai cơ chế phục vụ những vị trí khác nhau. Nếu test muốn xác nhận **marshaller không tạo ra XML sai**, hãy cấu hình schema cho marshaller hoặc validate XML đầu ra bằng schema validator độc lập. Nếu test muốn xác nhận **HTTP SOAP request sai không vào nghiệp vụ**, hãy viết integration test với interceptor và endpoint.

Không nên kết luận server đã kiểm tra schema chỉ vì client-side `Jaxb2Marshaller` được bật validation.

## 7. Viết test XML → JAXB → XML bằng JUnit 5

Giả định generated JAXB package có `ObjectFactory`, `SubmitOrderRequestType` và các accessors theo XSD.

Một ví dụ test để sử dụng trực tiếp `Jaxb2Marshaller`:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.io.StringReader;
import java.io.StringWriter;
import java.math.BigDecimal;

import javax.xml.namespace.QName;
import javax.xml.transform.stream.StreamResult;
import javax.xml.transform.stream.StreamSource;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.oxm.jaxb.Jaxb2Marshaller;

import jakarta.xml.bind.JAXBElement;

import com.example.contract.orders.v1.SubmitOrderRequestType;

class OrderBindingRoundTripTest {

    private static final String NS = "urn:example:orders:v1";

    private static Jaxb2Marshaller oxm;

    private static final String VALID_XML = """
        <ord:SubmitOrderRequest
            xmlns:ord="urn:example:orders:v1"
            correlationId="REQ-001">
            <ord:customerId>C-1001</ord:customerId>
            <ord:amount>125000.50</ord:amount>
            <ord:currency>VND</ord:currency>
            <ord:requestedAt>2026-11-27T09:30:00+07:00</ord:requestedAt>
            <ord:note>Giao trước 17 giờ</ord:note>
            <ord:item>
                <ord:sku>BOOK-01</ord:sku>
                <ord:quantity>2</ord:quantity>
            </ord:item>
        </ord:SubmitOrderRequest>
        """;

    @BeforeAll
    static void setUp() throws Exception {
        oxm = new Jaxb2Marshaller();
        oxm.setContextPath("com.example.contract.orders.v1");
        oxm.setSchema(
            new ClassPathResource("xsd/orders-v1.xsd")
        );
        oxm.afterPropertiesSet();
    }

    private static Object unmarshal(String xml) {
        return oxm.unmarshal(
            new StreamSource(new StringReader(xml))
        );
    }

    private static String marshal(Object value) {
        StringWriter out = new StringWriter();
        oxm.marshal(value, new StreamResult(out));
        return out.toString();
    }

    @Test
    void xmlRoundTripPreservesContractMeaning() {
        Object decoded = unmarshal(VALID_XML);

        assertInstanceOf(JAXBElement.class, decoded);

        JAXBElement<?> root = (JAXBElement<?>) decoded;
        assertEquals(
            new QName(NS, "SubmitOrderRequest"),
            root.getName()
        );

        assertInstanceOf(
            SubmitOrderRequestType.class,
            root.getValue()
        );

        SubmitOrderRequestType first =
            (SubmitOrderRequestType) root.getValue();

        assertEquals("C-1001", first.getCustomerId());
        assertEquals("REQ-001", first.getCorrelationId());
        assertEquals(1, first.getItem().size());

        // So sánh giá trị tiền, không buộc BigDecimal scale giống.
        assertEquals(
            0,
            new BigDecimal("125000.50")
                .compareTo(first.getAmount())
        );

        String xmlAgain = marshal(root);

        Object decodedAgain = unmarshal(xmlAgain);
        JAXBElement<?> rootAgain =
            (JAXBElement<?>) decodedAgain;

        assertEquals(root.getName(), rootAgain.getName());

        SubmitOrderRequestType second =
            (SubmitOrderRequestType) rootAgain.getValue();

        assertEquals(first.getCustomerId(), second.getCustomerId());
        assertEquals(first.getCorrelationId(), second.getCorrelationId());
        assertEquals(first.getItem().size(), second.getItem().size());
        assertEquals(
            0,
            first.getAmount().compareTo(second.getAmount())
        );
    }
}
~~~

Test này minh họa cách gọi API OXM. Khi đưa vào dự án thật, cần đặt đúng generated package, dependency Spring OXM/JUnit, và xác nhận tên accessor do XJC tạo ra. Với XSD dùng named complex type cho global root, cách ánh xạ `JAXBElement<SubmitOrderRequestType>` là trường hợp thường gặp, nhưng output cụ thể có thể chịu ảnh hưởng bởi binding customization.

**Điểm cần cải thiện trước khi dùng làm regression test chính thức:** kiểm tra cả currency, requestedAt, note, từng item và nil/presence; validate XML sau marshal như ở phần tiếp theo. Chỉ so `customerId` và amount chưa đủ để chứng minh toàn bộ hợp đồng được bảo toàn.

### 7.1. Vì sao không assert chuỗi XML giống hệt?

Có thể XML đầu vào dùng prefix `ord` nhưng XML sau marshal dùng prefix `ns2`. Hai trường hợp vẫn hợp đồng nếu namespace URI giống nhau.

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

~~~xml
<ns2:SubmitOrderRequest xmlns:ns2="urn:example:orders:v1"/>
~~~

Đừng dùng:

~~~java
assertEquals(originalXml, marshalledXml);
~~~

để kết luận hợp đồng XML đúng hoặc sai. Hãy parse XML, xác nhận QName, đường dẫn phần tử, giá trị; đồng thời validate bằng XSD. Có thể dùng XMLUnit hoặc DOM namespace-aware để so ngữ nghĩa cây XML theo yêu cầu test.

### 7.2. Kiểm thử một root QName độc lập

Khi global element được XJC biểu diễn bằng `JAXBElement`, factory gắn tên:

~~~java
ObjectFactory factory = new ObjectFactory();

SubmitOrderRequestType request =
    factory.createSubmitOrderRequestType();

JAXBElement<SubmitOrderRequestType> root =
    factory.createSubmitOrderRequest(request);
~~~

Đoạn này chỉ khởi tạo kiểu và wrapper, **chưa tạo object hợp lệ theo XSD** vì các field bắt buộc vẫn có thể rỗng. Khi test Java → XML, phải gán đủ dữ liệu trước khi marshal.

Nếu marshal trực tiếp `SubmitOrderRequestType` và lớp không có `@XmlRootElement`, JAXB có thể báo thiếu root mapping. Đó là lỗi metadata element QName, khác với lỗi facet XSD.

## 8. Viết test Java → XML → Java từ dữ liệu biên

Ta cần kiểm tra một object do Java tạo ra, không chỉ object unmarshal từ fixture.

Ví dụ xây request ở các giá trị biên hợp lệ:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;

import javax.xml.datatype.DatatypeFactory;
import jakarta.xml.bind.JAXBElement;

import com.example.contract.orders.v1.ObjectFactory;
import com.example.contract.orders.v1.OrderItemType;
import com.example.contract.orders.v1.SubmitOrderRequestType;
import com.example.contract.orders.v1.CurrencyType;

ObjectFactory f = new ObjectFactory();

SubmitOrderRequestType order = f.createSubmitOrderRequestType();

order.setCustomerId("C-EDGE");
order.setAmount(new BigDecimal("0.01"));
order.setCurrency(CurrencyType.VND);
order.setRequestedAt(
    DatatypeFactory.newInstance().newXMLGregorianCalendar(
        "2026-11-27T09:30:00+07:00"
    )
);
order.setCorrelationId("REQ-EDGE");

OrderItemType line = f.createOrderItemType();
line.setSku("SKU-1");
line.setQuantity(BigInteger.ONE);

order.getItem().add(line);

JAXBElement<SubmitOrderRequestType> root =
    f.createSubmitOrderRequest(order);
~~~

Giả định XJC sinh tên `CurrencyType`, các getter/setter và factory method như minh họa. Kiểu `xs:positiveInteger` thường tương ứng `BigInteger`, còn `xs:dateTime` thường tương ứng `XMLGregorianCalendar` khi không có customization. Với dự án có `XmlAdapter`, chữ ký sẽ khác.

Tiếp tục:

~~~java
String xml = marshal(root);
Object decoded = unmarshal(xml);

assertInstanceOf(JAXBElement.class, decoded);

JAXBElement<?> resultRoot = (JAXBElement<?>) decoded;
assertEquals(
    new QName("urn:example:orders:v1", "SubmitOrderRequest"),
    resultRoot.getName()
);

SubmitOrderRequestType result =
    (SubmitOrderRequestType) resultRoot.getValue();

assertEquals(
    0,
    new BigDecimal("0.01").compareTo(result.getAmount())
);
assertEquals(1, result.getItem().size());
assertEquals(
    BigInteger.ONE,
    result.getItem().get(0).getQuantity()
);
~~~

Đây là phần thực hành chiều Java → XML → Java. Dữ liệu chính là trường hợp **amount bằng min, quantity bằng min, item count bằng min**.

### 8.1. Đừng nhầm “marshal thành công” với “object hợp lệ”

Một object có:

~~~java
order.setAmount(new BigDecimal("0.001"));
order.getItem().clear();
~~~

vi phạm cả `fractionDigits=2` và `minOccurs=1`. JAXB binding class thông thường vẫn cho phép gán những giá trị này. Nếu `Jaxb2Marshaller` không gắn `Schema`, marshalling có thể vẫn ghi ra XML.

Khi đã cấu hình `setSchema(...)`, cần viết test xác nhận thao tác marshal bị từ chối hoặc validation báo lỗi. Trong production, ngoài schema validation nên có domain validation trước khi xây response.

## 9. Test XML sai bằng ma trận negative cases

Trong Java, dùng XML fixture độc lập để gửi những giá trị không thể hoặc khó biểu diễn qua generated enum/class.

Ví dụ ba XML sai, mỗi đoạn cần nằm trong một `SubmitOrderRequest` đầy đủ những trường khác:

~~~xml
<!-- Sai minInclusive -->
<ord:amount xmlns:ord="urn:example:orders:v1">0</ord:amount>
~~~

~~~xml
<!-- Sai fractionDigits -->
<ord:amount xmlns:ord="urn:example:orders:v1">1.231</ord:amount>
~~~

~~~xml
<!-- Sai enumeration -->
<ord:currency xmlns:ord="urn:example:orders:v1">EUR</ord:currency>
~~~

JUnit 5 có thể dùng parameterized test nếu muốn kiểm thử nhiều fixture:

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.oxm.XmlMappingException;

class InvalidContractXmlTest {

    // Sử dụng chung helper đọc XML và Jaxb2Marshaller
    // đã cấu hình Schema từ bộ test bên trên.

    @ParameterizedTest
    @ValueSource(strings = {
        "invalid/amount-below-min.xml",
        "invalid/amount-fraction-overflow.xml",
        "invalid/currency-unknown.xml",
        "invalid/items-four.xml",
        "invalid/wrong-namespace.xml"
    })
    void rejectsXmlOutsideContract(String fixtureName) {
        String xml = readFixture(fixtureName);

        assertThrows(
            XmlMappingException.class,
            () -> unmarshal(xml)
        );
    }
}
~~~

**Đoạn mã trên là skeleton minh họa**, giả định test class có helper `readFixture(...)`, `unmarshal(...)` dùng chung và đúng `XmlMappingException` của Spring OXM. Chưa phải một class chạy độc lập nguyên xi. Trong dự án thật, hãy cấu hình fixture loader và kiểm tra exception thực tế với phiên bản Spring/JAXB đang dùng. Nếu lỗi xuất hiện trước tầng OXM (ví dụ XML parser), loại exception có thể khác; một integration test nên kiểm tra loại lỗi ở đúng lớp mà ứng dụng cam kết.

Không nên chỉ assert “có exception bất kỳ”: sau khi ổn định framework, hãy xác nhận lỗi thực sự do **vi phạm XSD được nhắm tới**, không phải do thiếu file, sai classpath hoặc cấu hình JAXB sai.

### 9.1. Kiểm thử Java object sai ở chiều marshal

Ngoài test negative XML, hãy kiểm tra những object Java không thể xuất hiện trong dữ liệu hợp đồng hợp lệ.

Ví dụ:

~~~java
SubmitOrderRequestType invalid =
    factory.createSubmitOrderRequestType();

invalid.setCustomerId("C-1001");
invalid.setAmount(new BigDecimal("0.001")); // Sai fractionDigits
invalid.setCurrency(CurrencyType.VND);
// Giả định requestedAt/correlationId đã gán hợp lệ
// nhưng danh sách item vẫn rỗng.

JAXBElement<SubmitOrderRequestType> root =
    factory.createSubmitOrderRequest(invalid);
~~~

Khi schema validation ở chiều marshal được bật, một test nên yêu cầu rejection. Cần đảm bảo các trường còn lại hợp lệ nếu mục tiêu là **chẩn đoán riêng** lỗi fractionDigits; việc cố tình để nhiều trường sai phù hợp với test tích hợp tổng hợp nhưng khó biết constraint nào đã chặn đầu tiên.

### 9.2. Kiểm tra đúng thứ tự phần tử

Với `xs:sequence`, XML đầu vào phải theo thứ tự đã khai báo. Ví dụ thiếu schema validation có thể khiến ứng dụng đọc và tạo object mà không phát hiện sự khác biệt về thứ tự trong một số cấu hình binding.

Khi test contract:

- Đưa fixture XML có thứ tự đúng, assert hợp lệ.
- Đưa fixture XML hoán đổi `currency` và `amount`, assert không hợp lệ.
- Marshal một object có tất cả field và assert XML đầu ra hợp `xs:sequence`.
- Nếu dùng custom adapters hoặc JAXB class viết tay, kiểm tra `@XmlType(propOrder=...)` tương ứng.

## 10. So sánh ngữ nghĩa thay vì so byte

Mục tiêu một bộ round-trip test là phát hiện **mất dữ liệu thực sự**. Tùy loại dữ liệu, phép so sánh hợp lý khác nhau.

| Loại dữ liệu | Nên kiểm tra | Tránh giả định |
|---|---|---|
| QName | Namespace URI + local name | Prefix phải giống |
| `xs:decimal` | Giá trị `BigDecimal.compareTo()==0` | `equals()` phải true nếu scale khác |
| DateTime có offset | Instant hoặc offset theo chính sách contract | Chuỗi định dạng phải giống |
| DateTime không có timezone | Thành phần ngày giờ và trạng thái thiếu timezone | Tự gán UTC |
| `xs:sequence` | Thứ tự element hợp schema | Thứ tự field của Java class tự đúng |
| Danh sách | Số phần tử, thứ tự và dữ liệu từng item | Set/Map thay cho List mà vẫn giữ duplicate/order |
| `minOccurs=0` | Trạng thái absent nếu nghiệp vụ phân biệt | `null` luôn nghĩa absent |
| `nillable=true` | Trạng thái nil nếu nghiệp vụ phân biệt | Nil luôn giống chuỗi rỗng |
| String | Chuỗi Unicode sau parse | Entity escaping/CDATAs phải y hệt |
| Attribute | QName và giá trị attribute | Thứ tự attribute phải giữ nguyên |
| Namespace | URI đúng cho root và child elements | Mọi child dùng cùng prefix |

### 10.1. Cách so XML về mặt cấu trúc

Một lựa chọn là dùng thư viện XMLUnit với namespace-aware comparison. Tuy nhiên, vẫn phải quy định rõ điều gì được bỏ qua: whitespace giữa các element thường có thể bỏ qua khi không phải mixed content; **whitespace bên trong text có ý nghĩa** không nên bị xóa tùy tiện.

Ví dụ hai XML có thể tương đương về QName:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1" correlationId="REQ-1">
    <!-- Nội dung các phần tử con -->
</ord:SubmitOrderRequest>
~~~

~~~xml
<r:SubmitOrderRequest xmlns:r="urn:example:orders:v1" correlationId="REQ-1">
    <!-- Nội dung các phần tử con -->
</r:SubmitOrderRequest>
~~~

Khi test `xsi:nil`, đừng loại bỏ attribute `xsi:nil` khỏi phép so nếu đó là thông tin có ý nghĩa nghiệp vụ. Khi test chữ ký XML/WS-Security, phải dùng các quy tắc canonicalization và kiểm chứng chữ ký cụ thể thay vì so ngữ nghĩa thông thường.

### 10.2. Chú ý default/fixed có thể thay đổi cách quan sát

Trong XSD, `default` và `fixed` ảnh hưởng đến giá trị hiệu lực (PSVI) khi schema-aware processing. Một element optional **vắng mặt không tự được thêm vào XML** chỉ vì có `default`. Một element có mặt nhưng rỗng có thể nhận giá trị mặc định; với attribute optional có `default`, giá trị hiệu lực có thể được cung cấp khi attribute vắng mặt.

Do đó, khi test round-trip cần làm rõ:

- Muốn giữ **XML occurrence** hay chỉ giữ **giá trị hiệu lực**?
- Có bước schema validation cung cấp PSVI cho JAXB hay không?
- Generated binding và adapter có materialize default trong Java hay không?

Không nên giả định bật `Jaxb2Marshaller#setSchema` luôn khiến tất cả default/fixed được đưa vào object theo cùng cách ở mọi runtime. Hãy viết fixture riêng cho trường vắng mặt và trường hiện diện nhưng rỗng.

## 11. Khi nào kiểm thử ở tầng SOAP?

Các test OXM trực tiếp xử lý XML payload hoặc JAXB object. Chúng không tự kiểm tra toàn bộ SOAP Envelope, HTTP Content-Type, SOAP Action, interceptor, SOAP Fault hay WS-Security.

Ở tầng Spring-WS endpoint, luồng đầy đủ thường là:

~~~mermaid
flowchart TD
    A["SOAP client gửi XML"] --> B["MessageDispatcherServlet"]
    B --> C["Envelope / Header / QName"]
    C --> D["PayloadValidatingInterceptor"]
    D --> E["JAXB unmarshal"]
    E --> F["Spring-WS @Endpoint"]
    F --> G["Domain validation"]
    G --> H["JAXB marshal response"]
    H --> I["SOAP Envelope / HTTP response"]
~~~

Với request hợp lệ:

1. SOAP version của Envelope phải đúng cấu hình.
2. Payload root QName phải khớp `@PayloadRoot`.
3. XML payload phải hợp XSD.
4. JAXB phải giữ các giá trị quan trọng.
5. Nghiệp vụ trả dữ liệu đúng.
6. Response được marshal thành XML đúng QName/XSD và SOAP binding.

Với request không hợp lệ, cần kiểm tra **SOAP Fault** phù hợp với phiên bản SOAP và cơ chế exception resolver/interceptor. Ví dụ, SOAP 1.1 có `faultcode`/`faultstring`; SOAP 1.2 có `Code`/`Reason`. Không nên lấy trực tiếp exception Java rồi expose stack trace hoặc secret trong Fault.

### 11.1. Một ca test phải xác nhận nghiệp vụ không chạy khi request sai schema

Nếu dùng `PayloadValidatingInterceptor`, một acceptance test quan trọng là gửi request thiếu element bắt buộc và xác nhận:

- Nhận lỗi SOAP/schema phù hợp.
- Endpoint không xử lý lệnh sai.
- Service không ghi đơn hàng hoặc thực hiện side effect.
- Không có response thành công giả khiến client hiểu nhầm.

Đây là giá trị khác với unit test marshaller chỉ assert exception.

### 11.2. Kiểm thử với client độc lập

Nếu client và server đều dùng **cùng generated JAXB classes**, hai phía có thể cùng mang một lỗi mapping mà round-trip vẫn qua.

Để tránh kết luận sai, hãy:

- Giữ XML fixtures viết từ hợp đồng XSD/WSDL đã công bố.
- Dùng client .NET, JAX-WS độc lập hoặc một công cụ SOAP khác Java để gửi request và đọc response.
- Kiểm tra namespace, nil, danh sách, enum, tiền và ngày giờ ở cả hai phía.
- Xác nhận behavior khi client cũ tương tác với server mới.
- Nếu có WS-Security, kiểm tra chữ ký/chứng chỉ và cách canonicalize XML sau khi thay đổi binding.

## 12. Bộ kiểm thử nên được chia thành những lớp nào?

Một chiến lược cân bằng cho dự án Spring-WS:

| Tầng | Kiểm thử | Mục tiêu |
|---|---|---|
| XSD | Compile schema và validate fixtures | Hợp đồng tự nhất quán; nhận đúng và từ chối sai |
| JAXB/OXM | Java → XML → Java | Bảo toàn field, QName, precision, list và nil |
| JAXB/OXM | XML → Java → XML | Bảo toàn ý nghĩa XML bên ngoài và tính hợp lệ XSD |
| Mapper/domain | JAXB binding ↔ domain command | Bảo toàn business intent, đặc biệt absent/nil/empty |
| Spring-WS endpoint | SOAP XML qua dispatcher/interceptors | Định tuyến, validation, Fault, response hợp contract |
| SOAP client | WebServiceTemplate + transport | Media type, action, timeouts, XML response, lỗi |
| Interoperability | Client thuộc stack khác | Tránh phụ thuộc đặc thù JAXB hoặc cùng implementation |

Không cần chạy mọi test qua HTTP thật. Unit/integration test ở lớp OXM có thể rất nhanh và bao phủ nhiều biên. Một tập smoke/integration test nhỏ qua SOAP endpoint sẽ bắt lỗi binding, interceptor và WSDL mà OXM test không kiểm tra được.

## 13. Khi test thất bại, đọc lỗi theo đúng lớp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xác minh |
|---|---|---|
| Missing `@XmlRootElement` | Marshal named type không có root QName | Dùng `ObjectFactory` tạo `JAXBElement` hoặc root class phù hợp |
| Unexpected element | Root namespace/local name sai | So QName, JAXBContext, XSD version |
| Unmarshal thành công nhưng amount sai | Adapter dùng `double`, quy tắc scale/rounding | Đọc kiểu generated, so `BigDecimal` |
| Note absent/nil bị gộp | Binding không lưu presence | Kiểm tra XJC output, `JAXBElement`, mapper |
| Item rỗng vẫn marshal | Không bật validation hoặc XSD chưa được nạp | Xác nhận `setSchema`, validate output |
| Đổi prefix làm test fail | Test so raw XML | So QName và XML semantic |
| DateTime lệch ngày | Chuyển offset/UTC sai | So instant, offset và timezone policy |
| Schema báo type chưa định nghĩa | Import/include không phân giải | Xác minh các XSD và schema resolver |
| Client gửi enum mới, server không đọc | XSD/binding hai phía khác phiên bản | Kiểm tra WSDL/XSD và migration |
| JAXB test pass, SOAP vẫn lỗi | SOAP Envelope/Content-Type/Action/Fault | Test qua MessageDispatcherServlet và transport |
| XML đúng XSD nhưng sai quyền | XSD không xác thực nghiệp vụ/bảo mật | Kiểm tra domain validation và WS-Security |

### 13.1. Lỗi có thể do dữ liệu, không phải marshaller

Nếu request có `currency=EUR` nhưng XSD chỉ cho VND/USD, việc unmarshal thất bại khi bật validation là **hành vi đúng**. Đừng tắt schema validation để làm test qua, trừ khi hợp đồng thực sự thay đổi và đã được quản lý phiên bản.

### 13.2. Lỗi có thể do test quá chặt

Nếu XML sau marshal thay prefix `ord` thành `ns2` nhưng QName vẫn đúng, một test so byte thất bại là lỗi của **tiêu chí kiểm thử**. Test nên khẳng định contract semantics và XML Schema validity, không ép implementation giữ định dạng tùy ý.

### 13.3. Lỗi có thể do test quá lỏng

Nếu bạn chỉ assert `unmarshal(marshal(object))` không ném exception, một object có `item` rỗng hoặc `amount` sai scale có thể vẫn vượt qua nếu không validate XSD.

Thêm kiểm tra giá trị từng trường, cấu trúc QName và negative cases mới phân biệt được “binding chạy được” với “binding đúng hợp đồng”.

## 14. Cách vận hành kiểm thử trong quy trình phát hành

Một bộ contract regression nên được chạy khi:

- XSD/WSDL được chỉnh sửa.
- XJC/JAXB runtime hoặc phiên bản Spring-WS thay đổi.
- Mapper, `XmlAdapter`, validation interceptor hoặc `ObjectFactory`/binding customization thay đổi.
- SOAP client được nâng phiên bản hoặc chuyển sang một công cụ tích hợp mới.
- Cách xử lý tiền tệ, timezone, nil/optional hoặc enum thay đổi.

Khi xem kết quả CI:

1. Kiểm tra XSD compile được và không bị thiếu import.
2. Chạy toàn bộ fixture hợp lệ/không hợp lệ.
3. Chạy round-trip hai chiều và so ngữ nghĩa.
4. Chạy test SOAP endpoint/response/Fault.
5. Chạy một tập interoperability tests đại diện khi thay đổi giao thức hoặc binding.
6. Nếu phát hiện breaking change, quản lý namespace/WSDL version và migration thay vì điều chỉnh test để bỏ qua lỗi.

Nên lưu **WSDL/XSD đã công bố** cùng bộ fixtures để phát hiện việc code mới vô tình thay đổi hợp đồng mà client cũ phụ thuộc. Với dữ liệu sản xuất dùng làm test, cần ẩn danh hóa thông tin khách hàng và không lưu token, chữ ký hay khóa riêng vào fixture.

## 15. Bài thực hành tổng hợp

Cho XSD `SubmitOrderRequest` ở phần 3, hãy xây một bộ test tối thiểu gồm:

1. **Baseline:** đầy đủ các trường required, một item, note có Unicode.
2. **Amount boundaries:** 0.01, 9999999999.99, 0, -1, 1.231.
3. **List boundaries:** 0, 1, 3, 4 items; quantity 1, 50, 0, 51.
4. **Optional/nil:** note vắng mặt, nil, rỗng và có dữ liệu.
5. **DateTime:** một giá trị `+07:00`, một giá trị `Z` cùng instant, một giá trị không có offset nếu contract cho phép.
6. **QName:** đổi prefix vẫn pass; đổi target namespace sang v2 phải fail với schema v1.
7. **Schema structure:** bỏ correlationId, đổi thứ tự element, gửi nil cho amount.
8. **Hai chiều:** tạo object Java ở biên hợp lệ rồi marshal/unmarshal; dùng XML fixture độc lập rồi unmarshal/marshal.
9. **SOAP integration:** gửi request sai XSD qua Spring-WS; xác nhận SOAP Fault và endpoint không xử lý nghiệp vụ.
10. **Client độc lập:** dùng công cụ không dùng chính JAXB classes của server để nhận được response hợp lệ.

Với mỗi ca, ghi ba thông tin: **dữ liệu đầu vào**, **kỳ vọng theo XSD**, **kỳ vọng sau JAXB/domain mapper**. Kết quả “pass” phải được định nghĩa rõ, tránh test chỉ kiểm tra không phát sinh exception.

## 16. Checklist trước khi chấp nhận một thay đổi OXM

- [ ] Đã compile và cố định đúng version XSD/WSDL cần kiểm thử.
- [ ] Có XML fixtures độc lập từ contract, không chỉ do chính marshaller sinh.
- [ ] Đã test cả **Java → XML → Java** và **XML → Java → XML**.
- [ ] Root QName và namespace của child elements đúng.
- [ ] Min/max, enum, pattern, precision/scale, cardinality đều có positive/negative cases.
- [ ] Trạng thái absent/nil/empty được bảo toàn nếu nghiệp vụ phân biệt.
- [ ] Thời gian có/không offset được xử lý theo chính sách rõ ràng.
- [ ] XML sau marshal tiếp tục hợp XSD.
- [ ] Java object vi phạm XSD bị phát hiện trước khi phát hành SOAP response.
- [ ] Không dùng so chuỗi XML từng byte thay cho semantic comparison.
- [ ] Đã kiểm tra SOAP validation/Fault và ít nhất một client độc lập ở các điểm tích hợp trọng yếu.
- [ ] Không thay đổi hợp đồng công khai âm thầm chỉ vì refactor JAXB hoặc Java domain model.

## 17. Ghi nhớ

- **Round-trip hai chiều là phép kiểm tra dữ liệu đi qua ranh giới Java–XML**, nhưng không tự chứng minh tất cả quy tắc XSD đã được bảo vệ nếu không có validation.
- **Kiểm thử từ XML fixture độc lập** là cách tốt để phát hiện các tình huống mà Java object dễ bỏ qua, nhất là namespace, enum lạ và absent/nil/empty.
- **Giá trị tương đương không đòi XML giống byte-for-byte.** So QName, cấu trúc, datatype và ý nghĩa theo hợp đồng.
- **BigDecimal, XMLGregorianCalendar/adapter, JAXBElement và live List** cần những phép assert phù hợp với kiểu và semantics riêng.
- **Spring OXM, XSD validation, Spring-WS endpoint và SOAP client** là các lớp khác nhau; cần kiểm thử tương ứng.
- **Contract-first** yêu cầu giữ WSDL/XSD làm nguồn sự thật khi tích hợp nhiều hệ thống và kiểm tra tính tương thích trước khi thay đổi JAXB binding.

**Câu hỏi tự kiểm tra:** Một test `unmarshal(marshal(request))` chạy thành công, nhưng `request.getItem()` rỗng dù XSD quy định `minOccurs="1"`. Vì sao test này chưa chứng minh XML hợp đồng đúng? Bạn sẽ thêm những kiểm tra nào ở tầng JAXB, XML Schema và Spring-WS để chắc chắn request sai bị từ chối và không được xử lý nghiệp vụ?

