# Danh sách, kiểu liệt kê, kiểu số và dữ liệu ngày giờ trong lớp JAXB được sinh

## 1. Bối cảnh trong quy trình SOAP contract-first

Trong **Spring Web Services (Spring-WS)**, một dịch vụ SOAP theo hướng **contract-first** thường được xây dựng theo luồng **XSD/WSDL → sinh lớp Java bằng JAXB/XJC → triển khai `@Endpoint` hoặc SOAP client → marshal/unmarshal XML**. Việc chọn kiểu dữ liệu trong XSD ảnh hưởng trực tiếp đến API Java được sinh và khả năng trao đổi thông tin chính xác với hệ thống đối tác.

Một trường đơn giản như `quantity` có thể được sinh thành `int` hoặc `BigInteger` tùy kiểu XSD. Một phần tử lặp `line` có thể thành `List<InvoiceLineType>`, một tập giá trị `status` có thể thành `enum`, còn `xs:dateTime` thường thành `XMLGregorianCalendar` thay vì `LocalDateTime`. Nếu không hiểu các quy tắc này, lập trình viên dễ gặp lỗi làm tròn tiền, sai múi giờ, mất thông tin phần tử vắng mặt hoặc gửi danh sách XML sai cấu trúc.

Bài học thuộc chương **Sinh mã JAXB**, tập trung vào bốn nhóm thường có trong hợp đồng doanh nghiệp:

- **Danh sách**: `minOccurs`, `maxOccurs` và cách thao tác với getter `List`.
- **Kiểu liệt kê**: `xs:enumeration`, Java enum và khả năng tương thích khi thêm trạng thái.
- **Kiểu số**: ánh xạ số nguyên, số thập phân, độ chính xác, giới hạn dữ liệu.
- **Ngày giờ**: `xs:date`, `xs:time`, `xs:dateTime`, múi giờ và chuyển đổi sang Java Time API.

Cuối bài, chúng ta kết nối các loại dữ liệu đó với **JAXB marshalling, endpoint Spring-WS và kiểm thử XSD/WSDL**. Các tên lớp và phương thức do XJC tạo ra trong ví dụ là **minh họa theo ánh xạ JAXB thông dụng**; mã chính xác phải được đối chiếu với output của công cụ, phiên bản JAXB và các binding customization đang dùng.

## 2. XSD mẫu: yêu cầu tạo hóa đơn

Giả sử hợp đồng SOAP yêu cầu gửi mã hóa đơn, trạng thái, thời điểm phát hành, ngày đến hạn, nhiều dòng hàng và tổng tiền. Ta định nghĩa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:tns="urn:example:invoice:v1"
    targetNamespace="urn:example:invoice:v1"
    elementFormDefault="qualified">

    <xs:simpleType name="InvoiceStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="DRAFT"/>
            <xs:enumeration value="SUBMITTED"/>
            <xs:enumeration value="PAID"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="MoneyType">
        <xs:restriction base="xs:decimal">
            <xs:totalDigits value="15"/>
            <xs:fractionDigits value="2"/>
            <xs:minInclusive value="0"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="InvoiceLineType">
        <xs:sequence>
            <xs:element name="sku" type="xs:string"/>
            <xs:element name="quantity" type="xs:positiveInteger"/>
            <xs:element name="unitPrice" type="tns:MoneyType"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="CreateInvoiceRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="invoiceId" type="xs:string"/>
                <xs:element name="status" type="tns:InvoiceStatusType"/>
                <xs:element name="issuedAt" type="xs:dateTime"/>
                <xs:element name="dueDate" type="xs:date"
                            minOccurs="0"/>
                <xs:element name="line" type="tns:InvoiceLineType"
                            minOccurs="1" maxOccurs="unbounded"/>
                <xs:element name="totalAmount" type="tns:MoneyType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Đọc từng ràng buộc trước khi sinh mã:

| Trường XSD | Ý nghĩa hợp đồng | Java thường được sinh |
| --- | --- | --- |
| `invoiceId: xs:string` | Một mã hóa đơn bắt buộc | `String` |
| `status: InvoiceStatusType` | Một trong ba trạng thái | `InvoiceStatusType` enum |
| `issuedAt: xs:dateTime` | Ngày giờ phát hành | `XMLGregorianCalendar` |
| `dueDate: xs:date, minOccurs=0` | Ngày đến hạn tùy chọn | `XMLGregorianCalendar` có thể null |
| `line: InvoiceLineType, maxOccurs=unbounded` | Một hoặc nhiều dòng hàng | `List<InvoiceLineType>` |
| `quantity: xs:positiveInteger` | Số nguyên dương không giới hạn ở 32 bit theo XSD | `BigInteger` |
| `unitPrice / totalAmount: MoneyType` | Số thập phân với giới hạn chữ số | `BigDecimal` |

Ví dụ XML hợp lệ về cấu trúc và dữ liệu:

~~~xml
<inv:CreateInvoiceRequest
    xmlns:inv="urn:example:invoice:v1">
    <inv:invoiceId>INV-1001</inv:invoiceId>
    <inv:status>SUBMITTED</inv:status>
    <inv:issuedAt>2026-11-27T09:30:00+07:00</inv:issuedAt>
    <inv:dueDate>2026-12-27</inv:dueDate>
    <inv:line>
        <inv:sku>SKU-001</inv:sku>
        <inv:quantity>2</inv:quantity>
        <inv:unitPrice>159.90</inv:unitPrice>
    </inv:line>
    <inv:line>
        <inv:sku>SKU-002</inv:sku>
        <inv:quantity>1</inv:quantity>
        <inv:unitPrice>80.00</inv:unitPrice>
    </inv:line>
    <inv:totalAmount>399.80</inv:totalAmount>
</inv:CreateInvoiceRequest>
~~~

Thứ tự các phần tử phải theo `xs:sequence`; `line` có thể lặp nhưng `totalAmount` phải đứng sau toàn bộ các dòng hàng. XML trên là **payload thuộc SOAP Body**, chưa bao gồm lớp vỏ SOAP Envelope. Chỉ khi toàn bộ thông điệp được đóng gói đúng phiên bản SOAP và gửi tới endpoint hợp lệ thì nó mới là một request SOAP hoàn chỉnh.

## 3. Từ XSD sang cấu trúc Java: điều gì là quy ước, điều gì là hợp đồng?

JAXB là cơ chế ánh xạ XML ↔ Java. Công cụ **XJC** hoặc plugin sử dụng XJC đọc schema để sinh class, enum, `ObjectFactory` và các annotation. Spring-WS có thể dùng những lớp này trong `@RequestPayload`, `@ResponsePayload` hoặc qua `Jaxb2Marshaller` và `WebServiceTemplate`.

~~~mermaid
flowchart TD
    A["XSD: maxOccurs / enumeration / decimal / dateTime"] --> B["XJC hoặc JAXB code generation"]
    B --> C["Java: List / enum / BigDecimal / XMLGregorianCalendar"]
    C --> D["JAXB marshaller / unmarshaller"]
    D <--> E["SOAP Body XML"]
    E <--> F["Spring-WS endpoint / SOAP client"]
    A --> G["XSD validation"]
    G --> E
~~~

Phân biệt:

- **XSD** định nghĩa dữ liệu hợp lệ trên dây; đối tác không cần biết lớp Java nội bộ của bạn.
- **JAXB code generation** chọn cách biểu diễn hợp đồng trong Java. Một số chi tiết thay đổi theo phiên bản, compiler option và file binding.
- **JAXB marshalling/unmarshalling** thực hiện chuyển đổi XML ↔ object. Thao tác này **không mặc nhiên xác thực đầy đủ mọi facet XSD** nếu không bật schema validation.
- **Spring-WS** nhận/gửi thông điệp SOAP và chọn endpoint; nó không biến một `BigDecimal` sai giá trị nghiệp vụ thành hợp lệ.

Khi dự án dùng Spring hiện đại, thường gặp API annotation `jakarta.xml.bind.annotation.*`; các dự án cũ có thể dùng `javax.xml.bind.annotation.*`. Tuy nhiên `BigDecimal` và `BigInteger` luôn thuộc `java.math`, còn `XMLGregorianCalendar` thuộc **`javax.xml.datatype`**, kể cả khi annotation JAXB là `jakarta.xml.bind.*`.

## 4. Phần tử lặp `maxOccurs` được sinh thành `List<T>`

Đây là khai báo then chốt của XSD mẫu:

~~~xml
<xs:element name="line" type="tns:InvoiceLineType"
            minOccurs="1" maxOccurs="unbounded"/>
~~~

`maxOccurs="unbounded"` cho phép nhiều phần tử `line` xuất hiện liên tiếp. Với ánh xạ mặc định phổ biến, XJC sinh một thuộc tính có kiểu danh sách:

~~~java
@XmlElement(name = "line", required = true)
protected List<InvoiceLineType> line;

public List<InvoiceLineType> getLine() {
    if (line == null) {
        line = new ArrayList<>();
    }
    return this.line;
}
~~~

Đoạn trên minh họa cấu trúc getter sinh tự động; các `import`, annotation cụ thể và tên thuộc tính thực tế có thể thay đổi. **Nhiều lớp JAXB được sinh chỉ có getter cho danh sách, không có setter `setLine(List<...>)`.** Getter trả về **danh sách sống (live list)**: thêm/xóa phần tử trên danh sách đó làm thay đổi object sẽ được marshal.

### 4.1. Thêm phần tử đúng cách

~~~java
CreateInvoiceRequest request = new CreateInvoiceRequest();

InvoiceLineType first = new InvoiceLineType();
first.setSku("SKU-001");
first.setQuantity(new BigInteger("2"));
first.setUnitPrice(new BigDecimal("159.90"));

InvoiceLineType second = new InvoiceLineType();
second.setSku("SKU-002");
second.setQuantity(BigInteger.ONE);
second.setUnitPrice(new BigDecimal("80.00"));

request.getLine().add(first);
request.getLine().add(second);
~~~

Hai lần `add` thường được marshal thành hai phần tử cùng tên trong XML:

~~~xml
<inv:line>
    <inv:sku>SKU-001</inv:sku>
    <inv:quantity>2</inv:quantity>
    <inv:unitPrice>159.90</inv:unitPrice>
</inv:line>
<inv:line>
    <inv:sku>SKU-002</inv:sku>
    <inv:quantity>1</inv:quantity>
    <inv:unitPrice>80.00</inv:unitPrice>
</inv:line>
~~~

Đoạn XML này được trích từ phần bên trong `CreateInvoiceRequest`, nên khai báo prefix `inv` nằm ở phần tử cha như ví dụ mục 2.

**Không nên viết `request.setLine(lines)` nếu class thực tế không có setter.** Để thay toàn bộ nội dung, có thể dùng `request.getLine().clear()` rồi `addAll(newLines)`. Đó là thao tác trực tiếp lên trạng thái của object.

### 4.2. Danh sách trống khác danh sách bắt buộc có ít nhất một phần tử

Trong XSD mẫu, `minOccurs="1"` nghĩa là **phải có ít nhất một `line`**. Tuy nhiên getter Java vẫn có thể tạo ra một `ArrayList` rỗng:

~~~java
List<InvoiceLineType> lines = request.getLine();
System.out.println(lines.isEmpty()); // true khi chưa thêm dòng nào
~~~

Điều này **không chứng minh object hợp lệ theo XSD**. Nếu marshal object mà không bật validation, JAXB có thể tạo XML thiếu `line`; bộ xác thực schema sẽ từ chối XML đó. Vì vậy các ràng buộc `minOccurs`/`maxOccurs` phải được kiểm tra ở tầng XML validation hoặc bằng validation nghiệp vụ nhất quán.

Với `maxOccurs="3"`, schema cho tối đa ba dòng; ánh xạ `List<T>` thông thường **không tự giới hạn kích thước list khi gọi `add`**. Dùng XSD validator để phát hiện phần tử thứ tư, hoặc kiểm tra trước khi gửi.

### 4.3. Không có phần tử và danh sách rỗng

Với `minOccurs="0"`, payload có thể không chứa bất kỳ phần tử `line` nào. Trong object JAXB sinh mặc định, trường list ban đầu có thể là `null` nhưng getter sẽ tạo list rỗng; sau unmarshal, cũng thường chỉ quan sát được danh sách không có phần tử.

Nếu hợp đồng cần phân biệt **không gửi danh sách** với **gửi một phần tử danh sách rỗng**, bạn phải thiết kế cấu trúc khác, chẳng hạn wrapper element có thể vắng mặt hoặc nillable. Một live list đơn thuần không tự mang đủ ngữ nghĩa ba trạng thái absent/empty/nil.

## 5. `maxOccurs="unbounded"` khác `xs:list`

XSD có **hai khái niệm dễ trùng tên** nhưng tạo XML rất khác:

### 5.1. Nhiều phần tử cùng tên

~~~xml
<xs:element name="code" type="xs:string"
            minOccurs="0" maxOccurs="unbounded"/>
~~~

XML tương ứng:

~~~xml
<inv:code>A</inv:code>
<inv:code>B</inv:code>
<inv:code>C</inv:code>
~~~

Đây là **ba node phần tử**; JAXB thường dùng `List<String>`.

### 5.2. Một phần tử mang kiểu `xs:list`

~~~xml
<xs:simpleType name="CodeListType">
    <xs:list itemType="xs:string"/>
</xs:simpleType>

<xs:element name="codes" type="tns:CodeListType"/>
~~~

XML có dạng:

~~~xml
<inv:codes>A B C</inv:codes>
~~~

Đây là **một node phần tử duy nhất**, có nội dung lexical là các mục phân tách bằng khoảng trắng theo quy tắc của XSD list type. JAXB cũng có thể ánh xạ thành `List<String>`, nhưng thường đi kèm ý tưởng `@XmlList` và **cách biểu diễn XML khác**. Không được thay `xs:list` và `maxOccurs="unbounded"` cho nhau chỉ vì cùng thấy `List` trong Java.

| Khía cạnh | Phần tử lặp `maxOccurs` | Simple type `xs:list` |
| --- | --- | --- |
| XML | Nhiều phần tử cùng tên | Một phần tử có danh sách lexical |
| Java thường gặp | `List<T>` | `List<T>` với ánh xạ list value |
| Chứa complex type làm mỗi mục? | Có | Không, item type của `xs:list` là simple type |
| Thứ tự | Theo thứ tự xuất hiện các node | Theo thứ tự token trong chuỗi |
| Cách validate | Số phần tử, kiểu của từng phần tử | Số item, kiểu lexical của từng item và facet |

Trong các SOAP contract doanh nghiệp, danh sách đối tượng thường dùng **phần tử lặp** hoặc wrapper chứa phần tử lặp để cấu trúc rõ ràng.

## 6. Kiểu liệt kê `xs:enumeration` thành Java `enum`

XSD mẫu định nghĩa:

~~~xml
<xs:simpleType name="InvoiceStatusType">
    <xs:restriction base="xs:string">
        <xs:enumeration value="DRAFT"/>
        <xs:enumeration value="SUBMITTED"/>
        <xs:enumeration value="PAID"/>
    </xs:restriction>
</xs:simpleType>
~~~

Đây là danh sách **giá trị lexical được phép trên XML**, không phải Java source code. Một ánh xạ JAXB thường sinh enum tương tự:

~~~java
@XmlType(name = "InvoiceStatusType")
@XmlEnum
public enum InvoiceStatusType {
    @XmlEnumValue("DRAFT")
    DRAFT("DRAFT"),

    @XmlEnumValue("SUBMITTED")
    SUBMITTED("SUBMITTED"),

    @XmlEnumValue("PAID")
    PAID("PAID");

    private final String value;

    InvoiceStatusType(String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }

    public static InvoiceStatusType fromValue(String value) {
        for (InvoiceStatusType item : values()) {
            if (item.value.equals(value)) {
                return item;
            }
        }
        throw new IllegalArgumentException(value);
    }
}
~~~

Đây là **mẫu minh họa**; XJC có thể tạo annotation, tên hằng và helper khác. Không nên sửa trực tiếp enum được sinh nếu project tái sinh code trong build, vì thay đổi thủ công có thể bị ghi đè.

### 6.1. Dùng enum thay vì chuỗi tự do

~~~java
CreateInvoiceRequest request = new CreateInvoiceRequest();
request.setStatus(InvoiceStatusType.SUBMITTED);
~~~

Khi marshal, trạng thái được biểu diễn theo giá trị XML đã định nghĩa:

~~~xml
<inv:status>SUBMITTED</inv:status>
~~~

Nếu giá trị XML có dấu gạch nối, dấu cách hoặc cách viết không hợp lệ cho Java identifier, compiler có thể sinh một tên Java khác và dùng `@XmlEnumValue` để giữ đúng lexical value. **Tên hằng Java và giá trị XML không được giả định là giống nhau trong mọi trường hợp.**

### 6.2. Thêm enum mới có thể phá vỡ client cũ

Nếu phía server bổ sung `CANCELLED` vào schema và trả:

~~~xml
<inv:status>CANCELLED</inv:status>
~~~

Một client có enum cũ chỉ biết `DRAFT`/`SUBMITTED`/`PAID` có thể không xử lý được. Với schema validation, giá trị mới bị từ chối theo XSD cũ. Nếu không validation, biểu hiện khi JAXB unmarshal có thể tùy implementation và code sinh; không nên kỳ vọng mặc định sẽ có enum `UNKNOWN`.

Trong thiết kế hợp đồng:

- Thảo luận khả năng tiến hóa enum với đối tác ngay từ đầu.
- Nếu tập trạng thái thực sự mở, cân nhắc sử dụng `xs:string` kèm tài liệu mã giá trị/định nghĩa mở rộng thay vì `xs:enumeration` đóng.
- Khi bắt buộc thay đổi tập giá trị enum đóng, đánh giá versioning, khả năng sinh lại JAXB client và test tương thích.
- Không gán một trạng thái không nhận diện được thành `PAID` hoặc `SUCCESS` để bỏ qua lỗi; điều đó làm sai nghiệp vụ.

## 7. Kiểu số trong XSD và Java

Đặc biệt trong thanh toán, kế toán và dữ liệu đo lường, không nên chỉ chọn kiểu Java vì nó “đủ lớn” trong một vài ví dụ. Kiểu dữ liệu XSD xác định miền giá trị mà đối tác có quyền gửi.

### 7.1. Ánh xạ thông dụng

| Kiểu XSD | Java thường gặp | Ghi chú |
| --- | --- | --- |
| `xs:byte` | `byte` / `Byte` | Số nguyên 8 bit có dấu |
| `xs:short` | `short` / `Short` | Số nguyên 16 bit có dấu |
| `xs:int` | `int` / `Integer` | Số nguyên 32 bit có dấu |
| `xs:long` | `long` / `Long` | Số nguyên 64 bit có dấu |
| `xs:integer` | `BigInteger` | Số nguyên với miền không giới hạn theo precision cố định của Java primitive |
| `xs:positiveInteger`, `xs:nonNegativeInteger` | `BigInteger` | Có ràng buộc dấu theo XSD |
| `xs:decimal` | `BigDecimal` | Thập phân chính xác, thường dùng cho tiền |
| `xs:float` | `float` / `Float` | Số dấu phẩy động độ chính xác đơn |
| `xs:double` | `double` / `Double` | Số dấu phẩy động độ chính xác kép |
| `xs:unsignedInt` | `long` / `Long` | Cần phạm vi lớn hơn signed int |

Các kiểu nguyên thủy hay wrapper phụ thuộc **`minOccurs`, `nillable`, binding và compiler**. Với trường bắt buộc, một công cụ có thể dùng primitive; với trường tùy chọn, thường cần wrapper để biểu diễn giá trị không xuất hiện. Đây là bảng ánh xạ thông dụng, **không phải cam kết rằng mọi plugin sẽ sinh đúng một kiểu Java cố định**.

### 7.2. Vì sao tiền nên dùng `BigDecimal`?

Schema:

~~~xml
<xs:simpleType name="MoneyType">
    <xs:restriction base="xs:decimal">
        <xs:totalDigits value="15"/>
        <xs:fractionDigits value="2"/>
        <xs:minInclusive value="0"/>
    </xs:restriction>
</xs:simpleType>
~~~

Với mapping mặc định thường gặp, Java sinh:

~~~java
protected BigDecimal totalAmount;

public BigDecimal getTotalAmount() {
    return totalAmount;
}
~~~

`BigDecimal` mô tả thập phân theo giá trị chính xác, trong khi `double` là biểu diễn nhị phân xấp xỉ. Ví dụ:

~~~java
BigDecimal unitPrice = new BigDecimal("159.90");
BigInteger quantity = new BigInteger("2");

BigDecimal lineAmount = unitPrice.multiply(
        new BigDecimal(quantity));

System.out.println(lineAmount); // 319.80
~~~

**Nên tạo số tiền từ chuỗi thập phân hoặc nguồn giá trị đã có độ chính xác phù hợp**, không dùng `new BigDecimal(0.1)` khi muốn biểu diễn chính xác số thập phân `0.1`. Nếu phải chia, cần chỉ định quy tắc làm tròn cụ thể để tránh `ArithmeticException` khi kết quả thập phân vô hạn:

~~~java
BigDecimal average = new BigDecimal("10.00")
        .divide(new BigDecimal("3"), 2, RoundingMode.HALF_UP);
// 3.33 — quy tắc làm tròn chỉ là ví dụ.
~~~

Quy tắc `HALF_UP` trong ví dụ **không phải mặc định áp dụng cho mọi nghiệp vụ**. Hệ thống tài chính phải dùng scale, precision và rounding được quy định bởi hợp đồng và quy tắc nghiệp vụ.

### 7.3. `equals` và `compareTo` của `BigDecimal`

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

`equals` xét cả biểu diễn scale; `compareTo` so sánh giá trị số. Khi so sánh tiền theo giá trị, thường dùng `compareTo`. Nếu hệ thống cần giữ đúng số chữ số thập phân biểu diễn, phải quyết định riêng chính sách scale và serialization.

### 7.4. XSD facet không tự trở thành Java validation

Với `MoneyType`, các facet `totalDigits="15"`, `fractionDigits="2"` và `minInclusive="0"` có tác dụng khi **xác thực XML với schema**.

~~~java
request.setTotalAmount(new BigDecimal("-1.234"));
~~~

Object Java trên vẫn có thể được tạo dù vi phạm ràng buộc XSD. **JAXB marshalling mặc định không bảo đảm toàn bộ facet được kiểm tra**, nên cần bật schema validation ở client/server hoặc kiểm tra nghiệp vụ trước khi gửi.

XML cho `xs:decimal` dùng dấu chấm làm dấu thập phân, ví dụ `159.90`; không dùng dấu phẩy ngăn hàng nghìn hoặc định dạng địa phương như `1.599,90`. Phép ghi `1E2` theo kiểu số mũ không phải lexical representation hợp lệ cho `xs:decimal` thông thường; số mũ thuộc miền biểu diễn số dấu phẩy động.

### 7.5. Số nguyên lớn, âm, số không và overflow

Trong schema mẫu, `quantity` dùng `xs:positiveInteger`, nên số `0` và số âm không hợp lệ theo XSD. Vì JAXB có thể dùng `BigInteger`, code phải viết:

~~~java
line.setQuantity(new BigInteger("2"));
~~~

Không ép `BigInteger` về `int` bằng `intValue()` nếu chưa kiểm tra giới hạn, vì có thể mất thông tin. Khi thực sự cần `int`, dùng:

~~~java
int quantity = line.getQuantity().intValueExact();
~~~

`intValueExact()` phát sinh `ArithmeticException` nếu giá trị ngoài phạm vi `int`. Với nghiệp vụ có giới hạn số lượng thực tế, hãy khai báo `maxInclusive` hoặc kiểu XSD phù hợp để client/server cùng xác thực được, thay vì dựa vào giới hạn ngầm của Java.

## 8. XSD ngày, giờ và timestamp

Các kiểu thời gian thường gặp:

| Kiểu XSD | XML hợp lệ minh họa | Java JAXB thường gặp |
| --- | --- | --- |
| `xs:date` | `2026-12-27` hoặc có offset tùy hợp đồng | `XMLGregorianCalendar` |
| `xs:time` | `09:30:00+07:00` | `XMLGregorianCalendar` |
| `xs:dateTime` | `2026-11-27T09:30:00+07:00` | `XMLGregorianCalendar` |
| `xs:gYearMonth` | `2026-11` | `XMLGregorianCalendar` |
| `xs:duration` | `P2DT3H` | `javax.xml.datatype.Duration` |

JAXB mặc định thường ánh xạ các kiểu lịch XML sang **`javax.xml.datatype.XMLGregorianCalendar`**. Đây là lớp do Java XML Datatype API cung cấp, hỗ trợ các thành phần và quy tắc lexical của XML Schema, kể cả các trường hợp **không khai báo timezone**.

Phần lớn lập trình Java nghiệp vụ hiện đại thích `LocalDate`, `LocalDateTime`, `OffsetDateTime` hoặc `Instant`. Tuy nhiên, các kiểu Java Time API không phải ánh xạ mặc định bắt buộc của XJC cho XSD date/time. Nếu muốn dùng chúng trực tiếp, cần xác định **binding customization/`XmlAdapter`** và quy tắc timezone, không chỉ đổi tên kiểu trường.

### 8.1. `xs:dateTime` có và không có timezone

Hai giá trị:

~~~xml
<inv:issuedAt>2026-11-27T09:30:00+07:00</inv:issuedAt>
<inv:issuedAt>2026-11-27T02:30:00Z</inv:issuedAt>
~~~

Mỗi ví dụ là một cách biểu diễn **đơn lẻ** của `issuedAt`; nếu XSD quy định `maxOccurs=1` thì không được gửi đồng thời hai phần tử như vậy.

Hai giá trị trên đại diện **cùng một thời điểm**. `+07:00` là UTC offset; `Z` là UTC. Nhưng:

~~~xml
<inv:issuedAt>2026-11-27T09:30:00</inv:issuedAt>
~~~

không kèm timezone. Với `xs:dateTime` của XML Schema 1.0/1.1, có những giá trị hợp lệ không có offset, nên **không thể tự coi chúng là UTC hoặc giờ địa phương của server**. Nếu hợp đồng yêu cầu thời điểm tuyệt đối, hãy quy định rõ rằng offset/timezone phải có, và thiết kế cách xác thực quy ước đó; không chỉ dựa vào kiểu `xs:dateTime` thông thường.

### 8.2. Tạo `XMLGregorianCalendar` từ giá trị lexical

~~~java
import javax.xml.datatype.DatatypeFactory;
import javax.xml.datatype.XMLGregorianCalendar;

XMLGregorianCalendar issuedAt =
        DatatypeFactory.newInstance()
                .newXMLGregorianCalendar(
                        "2026-11-27T09:30:00+07:00");

request.setIssuedAt(issuedAt);
~~~

Chuỗi truyền vào tuân thủ lexical form của `xs:dateTime` với offset. `XMLGregorianCalendar` có thể xuất lại bằng:

~~~java
String xmlValue = issuedAt.toXMLFormat();
// 2026-11-27T09:30:00+07:00
~~~

Khi dùng công cụ JAXB để marshal, annotation kiểu schema và context phải đúng để nó viết phần tử `issuedAt` theo dạng `xs:dateTime`. Không nên tự biến timestamp thành chuỗi theo định dạng UI như `27/11/2026 09:30`.

### 8.3. Kết nối với Java Time API

Nếu XML timestamp **có offset**, có thể chuyển lexical representation sang `OffsetDateTime`:

~~~java
import java.time.OffsetDateTime;

String wireValue = issuedAt.toXMLFormat();
OffsetDateTime businessTime = OffsetDateTime.parse(wireValue);
~~~

Ví dụ này áp dụng cho một giá trị `xs:dateTime` hoàn chỉnh có offset như `2026-11-27T09:30:00+07:00`. Không dùng nó cho `xs:date` hay `xs:time` đơn lẻ, và không giả định một `dateTime` không timezone luôn parse được dưới dạng `OffsetDateTime`.

Nếu chỉ cần thời điểm tuyệt đối:

~~~java
Instant instant = businessTime.toInstant();
~~~

Khi chuyển ngược từ một `OffsetDateTime` sang `XMLGregorianCalendar`, có thể dùng:

~~~java
String lexical = businessTime.toString();
XMLGregorianCalendar xmlDateTime =
        DatatypeFactory.newInstance()
                .newXMLGregorianCalendar(lexical);
~~~

Trong ứng dụng thực tế, cần xác nhận serialization đối với fractional seconds, timezone và độ chính xác theo hợp đồng. Nếu dùng `LocalDateTime`, hãy xác định timezone/offset nghiệp vụ trước khi chuyển thành `Instant`; bản thân `LocalDateTime` **không chứa timezone**.

### 8.4. Ngày thuần túy không đồng nghĩa timestamp

`xs:date` như:

~~~xml
<inv:dueDate>2026-12-27</inv:dueDate>
~~~

thường biểu diễn **ngày lịch**, chẳng hạn ngày đến hạn thanh toán. Với dữ liệu kiểu này, `LocalDate` thích hợp ở tầng nghiệp vụ hơn một `Instant` nếu hợp đồng không đề cập thời điểm trong ngày. Đừng tự thêm `00:00:00Z` để chuyển thành timestamp vì có thể thay đổi ngày khi hiển thị ở múi giờ khác.

Đối với giá trị `xs:date` có timezone, cần quyết định xem timezone có ý nghĩa nghiệp vụ hay không trước khi chỉ giữ `LocalDate`; việc bỏ offset có thể làm mất thông tin của payload gốc.

### 8.5. Các tình huống thời gian cần thử nghiệm

- Timestamp có `Z` và có `+07:00`, xác minh hai giá trị tương đương về instant.
- Timestamp **không có offset**, đảm bảo không bị tự chuyển thành UTC hoặc timezone máy chủ.
- Giây thập phân, ví dụ `2026-11-27T09:30:00.123+07:00`.
- Ngày 29/02 ở năm nhuận, ngày không hợp lệ và thời điểm qua ranh giới ngày.
- Dịch vụ chạy ở máy chủ timezone khác hoặc qua hệ thống đối tác dùng UTC.
- Hệ thống có **DST** (giờ mùa hè) và nghiệp vụ đòi chuyển giữa zone ID với offset.

Với tích hợp liên quốc gia, nên phân biệt rõ **instant**, **offset** và **time zone region** (ví dụ `Asia/Ho_Chi_Minh`). XML dateTime có offset không tự mang một zone ID với quy tắc DST lịch sử.

## 9. Một đoạn Java dựng request đầy đủ

Giả sử XJC đã sinh các kiểu `CreateInvoiceRequest`, `InvoiceLineType` và `InvoiceStatusType` đúng với schema mục 2, mã gọi có thể có dạng:

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import javax.xml.datatype.DatatypeFactory;

CreateInvoiceRequest request = new CreateInvoiceRequest();
request.setInvoiceId("INV-1001");
request.setStatus(InvoiceStatusType.SUBMITTED);
request.setIssuedAt(
        DatatypeFactory.newInstance().newXMLGregorianCalendar(
                "2026-11-27T09:30:00+07:00"));
request.setDueDate(
        DatatypeFactory.newInstance().newXMLGregorianCalendarDate(
                2026, 12, 27,
                javax.xml.datatype.DatatypeConstants.FIELD_UNDEFINED));

InvoiceLineType line1 = new InvoiceLineType();
line1.setSku("SKU-001");
line1.setQuantity(BigInteger.valueOf(2));
line1.setUnitPrice(new BigDecimal("159.90"));

InvoiceLineType line2 = new InvoiceLineType();
line2.setSku("SKU-002");
line2.setQuantity(BigInteger.ONE);
line2.setUnitPrice(new BigDecimal("80.00"));

request.getLine().add(line1);
request.getLine().add(line2);
request.setTotalAmount(new BigDecimal("399.80"));
~~~

Đoạn code minh họa cách sử dụng API của **lớp được sinh**:

- `getLine().add(...)` cập nhật live list.
- `InvoiceStatusType.SUBMITTED` ánh xạ lexical enum value trong schema.
- `BigInteger` phù hợp `xs:positiveInteger`.
- `BigDecimal` giữ độ chính xác thập phân của tiền.
- `XMLGregorianCalendar` được tạo với timezone rõ ràng cho `issuedAt`; `dueDate` không bị gán múi giờ bất kỳ.

Với global element và cách sinh lớp cụ thể, JAXB root có thể được biểu diễn bởi `@XmlRootElement` hoặc cần wrapper `JAXBElement<CreateInvoiceRequest>` từ `ObjectFactory`. Hãy kiểm tra mã XJC thực tế; không mặc định mọi lớp `CreateInvoiceRequest` đều có `@XmlRootElement`.

## 10. Phần tử tùy chọn, `nillable` và Java `null`

Ba cách biểu diễn XML dưới đây có thể mang ý nghĩa nghiệp vụ khác nhau:

~~~xml
<!-- Không xuất hiện phần tử dueDate -->
~~~

~~~xml
<inv:dueDate/>
~~~

~~~xml
<inv:dueDate
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Với `xs:date`, phần tử rỗng `<inv:dueDate/>` **không hợp lệ theo kiểu dữ liệu** (nếu không có một cơ chế default hợp lệ đặc biệt). Trong XSD mẫu, `dueDate` có `minOccurs="0"` nhưng **không** có `nillable="true"`, nên bỏ hẳn phần tử là hợp lệ; gửi `xsi:nil="true"` thì không hợp lệ.

Nếu hợp đồng muốn phân biệt “không gửi” với “gửi nil”, khai báo:

~~~xml
<xs:element name="dueDate" type="xs:date"
            minOccurs="0" nillable="true"/>
~~~

JAXB có thể biểu diễn trường vừa optional vừa nillable bằng `JAXBElement<XMLGregorianCalendar>` hoặc cơ chế annotation/binding tương đương để giữ thông tin **có xuất hiện phần tử không**. Một property Java chỉ có giá trị `null` có thể không đủ để phân biệt absent với nil. Với danh sách `List<T>`, vấn đề tương tự có thể xuất hiện khi cần biểu diễn trạng thái của wrapper chứa danh sách.

| Trạng thái XML | Cần lưu ý trong JAXB |
| --- | --- |
| Không có phần tử | Java property có thể null hoặc list rỗng; tùy mapping |
| Có một giá trị hợp lệ | Java property mang giá trị đã ánh xạ |
| Có `xsi:nil="true"` | Chỉ hợp lệ nếu XSD cho `nillable=true`; có thể cần wrapper để giữ trạng thái |
| Có phần tử rỗng | Có thể hợp lệ với `xs:string`, thường không hợp lệ với kiểu số/ngày |

Đừng dùng `null` như một định nghĩa chung cho mọi trường hợp mà không xem XSD và XML marshalling thực tế.

## 11. Đưa các lớp JAXB sinh ra vào Spring-WS

Trong Spring-WS, endpoint có thể nhận request object đã được JAXB unmarshal khi các adapter/argument resolver thích hợp được cấu hình:

~~~java
@Endpoint
public class InvoiceEndpoint {
    private static final String NS = "urn:example:invoice:v1";
    private final InvoiceService invoiceService;

    public InvoiceEndpoint(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    @PayloadRoot(
        namespace = NS,
        localPart = "CreateInvoiceRequest"
    )
    @ResponsePayload
    public CreateInvoiceResponse create(
            @RequestPayload CreateInvoiceRequest request) {
        return invoiceService.createInvoice(request);
    }
}
~~~

`CreateInvoiceResponse` và `InvoiceService` chỉ là **các kiểu ứng dụng giả định** trong đoạn endpoint này; schema mẫu mục 2 chưa định nghĩa response nên một implementation hoàn chỉnh phải **bổ sung response element/type vào XSD/WSDL** rồi sinh lại lớp tương ứng. Ngoài ra, lớp request thực tế có thể được sinh với một dạng wrapper/annotation khác, nên signature endpoint cũng cần chỉnh theo mã JAXB sinh ra.

Ở phía SOAP client, `Jaxb2Marshaller` có thể chuyển object thành payload XML để `WebServiceTemplate` gửi đi:

~~~java
Jaxb2Marshaller marshaller = new Jaxb2Marshaller();
marshaller.setContextPath("example.invoice.ws.schema");
marshaller.afterPropertiesSet();

WebServiceTemplate template = new WebServiceTemplate();
template.setMarshaller(marshaller);
template.setUnmarshaller(marshaller);

// request là object được tạo ở mục 9.
Object response = template.marshalSendAndReceive(
        "https://partner.example.test/ws/invoices",
        request);
~~~

`example.invoice.ws.schema` là **package minh họa** chứa lớp JAXB do XJC sinh; `https://partner.example.test/ws/invoices` là URL giả định. Một ứng dụng thực tế còn phải cấu hình đúng SOAP version, WSDL action, HTTP sender, timeout, TLS và WS-Security theo hợp đồng. Nếu JAXB root cần `JAXBElement`, truyền wrapper tạo bởi `ObjectFactory` thay vì truyền bean không có root element.

**Marshaller không thay thế validation.** Với contract-first, nên xác thực SOAP payload theo XSD ở client, endpoint hoặc cả hai nơi tùy chính sách. Spring-WS có thể dùng `PayloadValidatingInterceptor` cho validation trong chuỗi xử lý; không mặc định tính năng này đã bật chỉ vì có `@Endpoint` hoặc đã sinh Java từ XSD.

## 12. Kiểm thử round-trip và tương thích XML

Trong tích hợp doanh nghiệp, cần kiểm tra **XML thực tế** hơn là chỉ assert giá trị object Java. Một round-trip hữu ích gồm:

~~~mermaid
flowchart LR
    A["Java object"] --> B["JAXB marshal"]
    B --> C["SOAP payload XML"]
    C --> D["XSD validation"]
    D --> E["JAXB unmarshal"]
    E --> F["Java object so sánh ngữ nghĩa"]
~~~

Với schema mục 2, hãy có các test sau:

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| `line` có một mục | Hợp lệ vì `minOccurs=1` |
| `line` có hai mục | JAXB tạo hai node `line` đúng thứ tự |
| `line` rỗng | XSD validation từ chối vì thiếu phần tử bắt buộc |
| Một mục có `quantity=0` | XSD từ chối do `xs:positiveInteger` |
| `status=SUBMITTED` | JAXB đọc/ghi đúng enum và lexical value |
| `status=CANCELLED` theo schema cũ | XSD từ chối; client không được tự bỏ qua một giá trị lạ |
| `unitPrice=159.90` | Đọc/ghi bằng `BigDecimal`, không đổi sang số thực nhị phân |
| `totalAmount=-1` | XSD từ chối do `minInclusive=0` |
| Quá `totalDigits` hoặc `fractionDigits` | XSD từ chối theo facet |
| `issuedAt` có `Z` / `+07:00` | Bảo toàn ý nghĩa instant sau chuyển đổi phù hợp |
| `issuedAt` không timezone | Không tự áp mặc định UTC khi nghiệp vụ chưa quyết định |
| `dueDate` bỏ hẳn | Hợp lệ theo `minOccurs=0` |
| `dueDate xsi:nil=true` | Không hợp lệ theo schema hiện tại |
| SOAP request với QName root sai | Spring-WS mapping/validator phát hiện sai |
| Marshal → validate → unmarshal | Không mất phần tử, thứ tự, giá trị và ý nghĩa theo contract |

Khi so sánh XML, **không so khớp prefix một cách cứng nhắc**: `inv:line` và `ns2:line` có thể là cùng expanded name nếu cùng namespace URI. Cần kiểm tra namespace, local name, kiểu dữ liệu và cấu trúc. Cũng đừng so sánh các giá trị ngày giờ khác offset bằng chuỗi đơn thuần khi ý nghĩa nghiệp vụ cần so sánh **instant**.

### 12.1. Ví dụ bật schema validation khi dùng JAXB trực tiếp

Với một JAXB `Unmarshaller`, có thể gắn schema:

~~~java
SchemaFactory schemaFactory = SchemaFactory.newInstance(
        XMLConstants.W3C_XML_SCHEMA_NS_URI);
Schema schema = schemaFactory.newSchema(
        new File("src/main/resources/xsd/invoice.xsd"));

JAXBContext context = JAXBContext.newInstance(
        CreateInvoiceRequest.class);
Unmarshaller unmarshaller = context.createUnmarshaller();
unmarshaller.setSchema(schema);
~~~

Đoạn minh họa giả định các lớp `SchemaFactory`, `Schema`, `XMLConstants`, `File`, `JAXBContext` và `Unmarshaller` đã được import; đường dẫn XSD phải được thay bằng đường dẫn resource thực tế khi đóng gói ứng dụng. API JAXB `JAXBContext`/`Unmarshaller` sử dụng package `jakarta.xml.bind` hoặc `javax.xml.bind` theo thế hệ runtime, còn `javax.xml.validation` và `javax.xml.XMLConstants` vẫn là các API Java XML tiêu chuẩn.

Trong ứng dụng đóng gói thành JAR/WAR, nên lấy XSD qua classpath/resource thay vì dựa vào đường dẫn file source chỉ tồn tại lúc phát triển. Khi dùng `SchemaFactory`, giới hạn external entity/schema access phù hợp môi trường để tránh tải tài nguyên bên ngoài không mong muốn.

## 13. Những lỗi phát sinh phổ biến

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không có `setLine(List<...>)` | XJC sinh live list getter | Dùng `getLine().add(...)` hoặc `addAll(...)` |
| Gửi list rỗng nhưng XSD yêu cầu ít nhất một mục | `minOccurs=1` không được kiểm tra khi tạo object | Validate XSD hoặc kiểm tra kích thước trước marshal |
| XML ra một chuỗi `A B C` thay vì ba node `code` | Dùng `xs:list` thay vì repeated element | Sửa đúng mô hình schema, sinh lại Java |
| Không parse được enum mới | Client chỉ có enum cũ | Kiểm tra thay đổi hợp đồng và versioning |
| `BigDecimal.equals` cho false dù số tiền tương đương | Scale khác nhau | So sánh bằng `compareTo` nếu cần so giá trị số |
| Số thập phân có sai số sau tính toán | Chuyển trung gian sang `double` hoặc tạo BigDecimal từ double | Giữ `BigDecimal` xuyên suốt |
| Số lớn thành âm hoặc bị cắt | Ép `BigInteger` sang `int`/`long` sai cách | Dùng kiểu phù hợp hoặc `intValueExact`/`longValueExact` |
| Timestamp lệch vài giờ | Tự thêm timezone hoặc mặc định timezone server | Giữ offset, dùng `OffsetDateTime`/`Instant` khi có offset |
| `xs:date` thành ngày hôm trước | Biến ngày lịch thành instant rồi đổi múi giờ | Dùng `LocalDate` cho nghiệp vụ ngày lịch |
| `XMLGregorianCalendar` xuất hiện trong class Jakarta | Nhầm rằng mọi `javax.*` đều phải đổi sang `jakarta.*` | Giữ `javax.xml.datatype`; đổi đúng JAXB annotations/API |
| Marshal được object nhưng XSD từ chối | Facet, order, minOccurs hoặc nillable sai | Bật XSD validation và sửa object/contract |
| Server không chọn endpoint | QName root sai dù tên Java class giống nhau | Kiểm tra `@PayloadRoot`, namespace URI và SOAP Body |

## 14. Thực hành có hướng dẫn

Hãy mở rộng schema hóa đơn và code sinh của bạn với các yêu cầu:

1. Thêm `currency` có kiểu liệt kê `VND`, `USD`, `EUR`; xem class enum được sinh ra và giá trị XML tương ứng.
2. Thay `line` từ `maxOccurs="unbounded"` sang `maxOccurs="5"`; xác định xem API Java có thay đổi không, rồi xác minh trường hợp sáu dòng bằng schema validation.
3. Đặt `totalAmount=399.80` bằng `BigDecimal` và kiểm tra phép so sánh với `399.8` bằng `equals` và `compareTo`.
4. Thử `quantity` bằng số vượt `Integer.MAX_VALUE`; so sánh hành vi `BigInteger` với phép ép sang `int`.
5. Dựng `issuedAt` có offset `+07:00` rồi chuyển sang `Instant`; kiểm tra tương đương với giá trị có `Z`.
6. Bỏ `dueDate`, sau đó gửi `xsi:nil="true"`; giải thích khác biệt theo `minOccurs` và `nillable` của schema.
7. Dùng JAXB marshal request, chạy validator XSD, rồi unmarshal lại; so sánh ý nghĩa nghiệp vụ của các trường.
8. Đặt request trong SOAP Body và kiểm tra QName gốc khớp `@PayloadRoot` của Spring-WS. Nếu dùng WSDL công bố, xác nhận request message tham chiếu đúng global element.

**Tiêu chí hoàn thành:** các lớp sinh ra xử lý danh sách, enum, số và ngày giờ theo đúng XML contract; hệ thống phát hiện dữ liệu vi phạm schema; các phép tính thập phân và chuyển đổi timezone không làm sai nghĩa dữ liệu.

## 15. Ghi nhớ

- `maxOccurs>1` hoặc `unbounded` thường dẫn đến **live list `List<T>`** trong JAXB; `getLine().add(...)` là cách thao tác phổ biến. `minOccurs` vẫn phải được kiểm tra bằng schema hoặc logic riêng.
- **Nhiều phần tử lặp** khác **`xs:list`**: một bên là nhiều XML nodes, bên kia là một giá trị lexical chứa nhiều mục.
- `xs:enumeration` thường thành **Java enum**; giá trị XML có thể khác tên hằng Java. Thêm enum mới cần đánh giá tương thích client.
- `xs:decimal` thường thành **`BigDecimal`**, `xs:integer` và các biến thể lớn thường thành **`BigInteger`**. Không dùng `double` cho phép tính tiền cần chính xác.
- `xs:date`, `xs:time` và `xs:dateTime` thường thành **`XMLGregorianCalendar`**. Phải phân biệt ngày lịch, timestamp có offset và giá trị không timezone.
- **JAXB object hợp lệ về kiểu Java chưa chắc hợp lệ theo XSD**. Bật validation để kiểm tra facet, minOccurs/maxOccurs, enum và kiểu lexical.
- Trong **Spring-WS contract-first**, giữ nhất quán XSD, WSDL, lớp JAXB được sinh, SOAP Body, `@Endpoint`/`WebServiceTemplate` và chính sách SOAP Fault/bảo mật để tích hợp doanh nghiệp ổn định.
