# `xs:sequence`, `xs:choice`, `xs:all` và ràng buộc thứ tự phần tử

Trong thiết kế XSD cho dịch vụ SOAP **contract-first**, không chỉ tên và kiểu dữ liệu của phần tử mới tạo thành hợp đồng. **Thứ tự phần tử con**, số lần xuất hiện và các nhánh cấu trúc được phép cũng là những quy tắc mà client và server phải thống nhất. Một XML hoàn toàn hợp khuôn dạng (*well-formed*) vẫn có thể **không hợp lệ theo XSD** khi gửi các trường theo thứ tự khác, thiếu trường bắt buộc hoặc chọn sai nhánh.

Bài thuộc chương **Thiết kế XSD** của module **SPRING_WEB_SERVICES**. Trong Spring Web Services (Spring-WS), những quyết định này lan từ XSD sang phần tử payload trong WSDL, mô hình JAXB, endpoint, SOAP client, interceptor xác thực và kiểm thử tương thích giữa các hệ thống doanh nghiệp. Bài tập trung vào cách thiết kế ba nhóm nội dung `xs:sequence`, `xs:choice` và `xs:all`, đồng thời liên hệ với SOAP Fault và XML/WS-Security khi triển khai thực tế.

## 1. Từ XML có thứ tự đến bộ quy tắc của XSD

XML giữ **thứ tự các nút con**. Ví dụ:

```xml
<order>
    <customerId>C-100</customerId>
    <quantity>2</quantity>
</order>
```

và:

```xml
<order>
    <quantity>2</quantity>
    <customerId>C-100</customerId>
</order>
```

đều là XML well-formed. Nhưng liệu cả hai có đúng hợp đồng hay không phải căn cứ vào **content model** của `order` trong XSD. Nếu dùng `xs:sequence` với `customerId` rồi đến `quantity`, chỉ cách viết đầu hợp lệ. Nếu dùng `xs:all` cho hai phần tử có tối đa một lần xuất hiện, cả hai thứ tự đều có thể hợp lệ.

Không nên nhầm **thứ tự phần tử con** với **thứ tự thuộc tính**. Trong XML, `<item sku="A" unit="piece"/>` và `<item unit="piece" sku="A"/>` có cùng tập thuộc tính; thứ tự thuộc tính không mang ý nghĩa theo mô hình XML. Ngược lại, thứ tự phần tử con có thể ảnh hưởng đến tính hợp lệ, ánh xạ JAXB và chữ ký XML.

Một hợp đồng XSD thường kết hợp:

| Thành phần | Ràng buộc |
| --- | --- |
| `xs:sequence` | Các hạt nội dung xuất hiện theo thứ tự khai báo |
| `xs:choice` | Chọn một nhánh của nhóm trong mỗi lần xuất hiện của nhóm |
| `xs:all` | Các phần tử thành viên có thể xuất hiện không theo thứ tự, trong giới hạn của `all` |
| `minOccurs` | Số lần xuất hiện tối thiểu của phần tử hoặc nhóm |
| `maxOccurs` | Số lần xuất hiện tối đa; có thể là `unbounded` khi được phép |
| `xs:element type=...` | Kiểu giá trị hoặc kiểu phức hợp của phần tử |
| `elementFormDefault` / `form` | Quy tắc namespace cho các phần tử được khai báo cục bộ |

**Mặc định** khi `minOccurs` và `maxOccurs` được phép nhưng không ghi: cả hai bằng `1`. Không được suy luận rằng “trường chưa khai báo số lần thì tự động optional”.

## 2. `xs:sequence`: cấu trúc theo đúng trình tự

### 2.1. Ví dụ XSD hoàn chỉnh

Dịch vụ tạo đơn hàng nhận mã khách hàng, một hoặc nhiều dòng hàng, một lựa chọn giao nhận và ghi chú tùy chọn:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:tns="https://example.org/orders/v1"
           targetNamespace="https://example.org/orders/v1"
           elementFormDefault="qualified">

    <xs:complexType name="OrderLineType">
        <xs:sequence>
            <xs:element name="sku" type="xs:string"/>
            <xs:element name="quantity" type="xs:positiveInteger"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="CreateOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
                <xs:element name="line" type="tns:OrderLineType"
                            minOccurs="1" maxOccurs="unbounded"/>
                <xs:choice>
                    <xs:element name="shipTo" type="xs:string"/>
                    <xs:element name="pickupAt" type="xs:string"/>
                </xs:choice>
                <xs:element name="note" type="xs:string"
                            minOccurs="0"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="CreateOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="xs:string"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Đây là XSD theo cách viết tương thích **XML Schema 1.0**. Các phần tử con được khai báo cục bộ nằm trong namespace đích do `elementFormDefault="qualified"`.

Với request, có thể đọc cấu trúc như sau:

```text
CreateOrderRequest
  1. customerId                 đúng 1 lần
  2. line                       từ 1 lần trở lên
       2.1 sku                  đúng 1 lần
       2.2 quantity             đúng 1 lần
  3. (shipTo HOẶC pickupAt)     chọn đúng 1 nhánh
  4. note                       0 hoặc 1 lần
```

Payload **hợp lệ**:

```xml
<o:CreateOrderRequest xmlns:o="https://example.org/orders/v1">
    <o:customerId>C-100</o:customerId>
    <o:line>
        <o:sku>BOOK-01</o:sku>
        <o:quantity>2</o:quantity>
    </o:line>
    <o:line>
        <o:sku>PEN-03</o:sku>
        <o:quantity>5</o:quantity>
    </o:line>
    <o:shipTo>12 Nguyen Hue</o:shipTo>
    <o:note>Giao giờ hành chính</o:note>
</o:CreateOrderRequest>
```

Ba tình huống sau **không hợp lệ** theo XSD này:

```xml
<!-- Sai: customerId không ở đầu sequence. -->
<o:CreateOrderRequest xmlns:o="https://example.org/orders/v1">
    <o:line>
        <o:sku>BOOK-01</o:sku>
        <o:quantity>2</o:quantity>
    </o:line>
    <o:customerId>C-100</o:customerId>
    <o:pickupAt>STORE-01</o:pickupAt>
</o:CreateOrderRequest>
```

```xml
<!-- Sai: bên trong mỗi line cũng phải là sku rồi quantity. -->
<o:CreateOrderRequest xmlns:o="https://example.org/orders/v1">
    <o:customerId>C-100</o:customerId>
    <o:line>
        <o:quantity>2</o:quantity>
        <o:sku>BOOK-01</o:sku>
    </o:line>
    <o:pickupAt>STORE-01</o:pickupAt>
</o:CreateOrderRequest>
```

```xml
<!-- Sai: note xuất hiện trước nhánh giao nhận bắt buộc. -->
<o:CreateOrderRequest xmlns:o="https://example.org/orders/v1">
    <o:customerId>C-100</o:customerId>
    <o:line>
        <o:sku>BOOK-01</o:sku>
        <o:quantity>2</o:quantity>
    </o:line>
    <o:note>Nhận tại quầy</o:note>
    <o:pickupAt>STORE-01</o:pickupAt>
</o:CreateOrderRequest>
```

Trong cả ba ví dụ, parser XML vẫn có thể đọc tài liệu. Chính **schema validator** mới xác định thứ tự/số lượng sai hợp đồng. JAXB unmarshal không mặc nhiên xác thực mọi ràng buộc XSD nếu ứng dụng không cấu hình validation.

### 2.2. `minOccurs` và `maxOccurs` không làm thay đổi vị trí

Khi khai báo:

```xml
<xs:sequence xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="id" type="xs:string"/>
    <xs:element name="tag" type="xs:string"
                minOccurs="0" maxOccurs="unbounded"/>
    <xs:element name="description" type="xs:string"
                minOccurs="0"/>
</xs:sequence>
```

Các `tag`, nếu có, phải tạo thành một nhóm liên tiếp **sau `id` và trước `description`**. Không được xen một `tag` vào sau `description` rồi cho rằng `maxOccurs="unbounded"` cho phép nó xuất hiện ở bất kỳ đâu.

Mô hình này chấp nhận `id` đứng riêng, `id + description`, `id + nhiều tag`, hoặc `id + nhiều tag + description`. Nó không chấp nhận `description + id` hoặc `id + description + tag`.

### 2.3. Lặp cả nhóm tuần tự khác với lặp từng trường

Giả sử message chứa nhiều cặp khóa và giá trị, **mỗi cặp phải theo thứ tự key rồi value**:

```xml
<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:sequence>
        <xs:element name="batchId" type="xs:string"/>
        <xs:sequence minOccurs="1" maxOccurs="unbounded">
            <xs:element name="key" type="xs:string"/>
            <xs:element name="value" type="xs:string"/>
        </xs:sequence>
    </xs:sequence>
</xs:complexType>
```

Nhóm này chấp nhận `batchId, key, value, key, value`. Nếu thay nhóm con bằng `key maxOccurs="unbounded"` theo sau bởi `value maxOccurs="unbounded"`, ta sẽ được một hợp đồng **khác**: cho phép nhiều `key` trước rồi nhiều `value`, không giữ mối quan hệ từng cặp.

Trong thiết kế thực tế, cũng có thể định nghĩa một `EntryType` gồm `key` và `value` rồi lặp phần tử `entry`. Cách đó thường dễ tạo đối tượng JAXB và diễn đạt đơn vị dữ liệu nghiệp vụ hơn.

## 3. `xs:choice`: chọn nhánh, không phải sắp xếp tự do

### 3.1. Một lựa chọn duy nhất

Trong XSD tạo đơn hàng ở trên:

```xml
<xs:choice xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="shipTo" type="xs:string"/>
    <xs:element name="pickupAt" type="xs:string"/>
</xs:choice>
```

Vì cả hai thuộc tính occurrence của **nhóm** mặc định là `1`, mỗi request phải chứa **đúng một** trong hai phần tử `shipTo` hoặc `pickupAt`. Gửi cả hai là sai. Không gửi phần tử nào cũng sai.

`xs:choice` chọn **một nhánh của nhóm**, nhưng mỗi nhánh có thể là một nhóm phức tạp hơn một phần tử:

```xml
<xs:choice xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:sequence>
        <xs:element name="bankCode" type="xs:string"/>
        <xs:element name="bankReference" type="xs:string"/>
    </xs:sequence>
    <xs:element name="cardToken" type="xs:string"/>
</xs:choice>
```

Hoặc gửi **`bankCode` rồi `bankReference`**, hoặc gửi **`cardToken`**. Gửi `bankReference` trước `bankCode` vẫn sai vì *bên trong nhánh được chọn* có `xs:sequence`.

### 3.2. Lặp một nhóm `xs:choice`

```xml
<xs:choice xmlns:xs="http://www.w3.org/2001/XMLSchema"
           minOccurs="1" maxOccurs="unbounded">
    <xs:element name="email" type="xs:string"/>
    <xs:element name="phone" type="xs:string"/>
</xs:choice>
```

Cho phép chuỗi như:

```xml
<email>a@example.org</email>
<phone>0900000000</phone>
<email>b@example.org</email>
```

Mỗi **lần lặp của nhóm** chọn một nhánh. Vì vậy `maxOccurs="unbounded"` trên `choice` **không có nghĩa “chọn đúng một loại cho cả request”**. Các nhánh có thể luân phiên; số lần trùng lặp cũng phải xét occurrence. Nếu nghiệp vụ đòi “chỉ một phương thức liên hệ”, giữ `choice` ở `maxOccurs=1`; nếu đòi nhiều địa chỉ email và nhiều số điện thoại riêng biệt, mô hình bằng các container/lists phù hợp sẽ rõ hơn.

### 3.3. `choice` có thể optional

```xml
<xs:choice xmlns:xs="http://www.w3.org/2001/XMLSchema"
           minOccurs="0">
    <xs:element name="voucherCode" type="xs:string"/>
    <xs:element name="loyaltyId" type="xs:string"/>
</xs:choice>
```

Cấu trúc này cho phép **không gửi gì** hoặc chọn một phần tử, nhưng vẫn không cho phép cả `voucherCode` lẫn `loyaltyId` cùng xuất hiện. Phân biệt `minOccurs="0"` của **nhóm choice** với việc chỉ đặt `minOccurs="0"` trên một phần tử trong nhóm; hai cấu trúc có thể khác về trạng thái được phép và độ rõ ràng của schema.

## 4. `xs:all`: độc lập về thứ tự, có giới hạn

Khi các trường đơn lẻ không cần thứ tự cố định, `xs:all` phù hợp:

```xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="https://example.org/customers/v1"
           elementFormDefault="qualified">

    <xs:element name="UpdateContactRequest">
        <xs:complexType>
            <xs:all>
                <xs:element name="customerId" type="xs:string"/>
                <xs:element name="email" type="xs:string" minOccurs="0"/>
                <xs:element name="phone" type="xs:string" minOccurs="0"/>
            </xs:all>
        </xs:complexType>
    </xs:element>
</xs:schema>
```

Hai payload dưới đây đều hợp lệ theo XSD này:

```xml
<c:UpdateContactRequest xmlns:c="https://example.org/customers/v1">
    <c:customerId>C-100</c:customerId>
    <c:email>a@example.org</c:email>
    <c:phone>0900000000</c:phone>
</c:UpdateContactRequest>
```

```xml
<c:UpdateContactRequest xmlns:c="https://example.org/customers/v1">
    <c:phone>0900000000</c:phone>
    <c:customerId>C-100</c:customerId>
</c:UpdateContactRequest>
```

Trường `customerId` bắt buộc; `email` và `phone` có thể thiếu. Nhưng `email` hoặc `phone` **không được lặp** trong cách dùng `xs:all` này.

### 4.1. Giới hạn của `all` ở XML Schema 1.0

- Một **`xs:all` group** trong XSD 1.0 không được lặp tùy ý: `maxOccurs` của nhóm là `1`, `minOccurs` chỉ có thể `0` hoặc `1`; cách đặt nhóm có những hạn chế về vị trí và lồng nhóm.
- Phần tử trực tiếp bên trong `xs:all` của XSD 1.0 chỉ có `minOccurs=0|1` và `maxOccurs=1`. Vì vậy **không thể** viết một danh sách `phone maxOccurs="unbounded"` trực tiếp trong nhóm `all` ở XSD 1.0.
- XML Schema 1.1 có nới một số ràng buộc cho `all`; trước khi dựa vào khả năng đó, cần xác minh trình xác thực XSD và chuỗi công cụ JAXB/Spring-WS của cả hai phía có hỗ trợ **XSD 1.1** hay không. Các bộ xử lý XSD 1.0 phổ biến không tự động nhận các tính năng XSD 1.1.

Đoạn dưới **không hợp lệ như XSD 1.0**:

```xml
<xs:all xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="customerId" type="xs:string"/>
    <xs:element name="phone" type="xs:string"
                maxOccurs="unbounded"/>
</xs:all>
```

Một thiết kế thay thế rõ ràng là `xs:sequence` chứa `customerId`, sau đó phần tử `phones` có kiểu phức hợp chứa nhiều `phone`. Nếu mục tiêu thực sự cần hoán đổi thứ tự của nhiều loại trường lặp, hãy mô hình hóa theo **nhóm choice lặp** hoặc cấu trúc danh sách phù hợp, rồi đánh giá ràng buộc nghiệp vụ về trùng lặp.

### 4.2. `xs:all` không tự thực thi mọi quy tắc nghiệp vụ

Với ví dụ `UpdateContactRequest`, cả `email` và `phone` đều optional. Do đó request chỉ có `customerId` cũng hợp lệ theo XSD, dù nghiệp vụ có thể yêu cầu “cập nhật ít nhất một kênh liên lạc”.

Muốn diễn tả quy tắc “cần một trong hai”, một `xs:choice` là ứng viên tự nhiên nếu hai trường loại trừ nhau. Nếu muốn cho phép **cả hai cùng xuất hiện nhưng ít nhất phải có một**, cần thiết kế content model khác, xem xét biểu đạt bằng XSD 1.0 hoặc kiểm tra nghiệp vụ/XSD 1.1 assertion khi môi trường hỗ trợ. Đừng kỳ vọng `xs:all` tự giải quyết quy tắc tổ hợp không được mô tả trong schema.

## 5. So sánh ba nhóm theo mục tiêu thiết kế

| Tiêu chí | `xs:sequence` | `xs:choice` | `xs:all` |
| --- | --- | --- | --- |
| Ý nghĩa chính | Liệt kê các hạt theo thứ tự | Chọn một nhánh trong mỗi lượt nhóm | Tập trường không phụ thuộc thứ tự |
| Thứ tự phần tử | Ràng buộc chặt theo khai báo | Do nhánh được chọn quyết định; nhánh có thể là sequence | Thứ tự các phần tử thành viên không quan trọng |
| Phần tử lặp | Hỗ trợ `maxOccurs` theo particle | Có thể lặp nhóm lựa chọn | Giới hạn chặt ở XSD 1.0 |
| Trường optional | `minOccurs=0` trên phần tử/nhóm | `minOccurs=0` trên nhóm hoặc trường thích hợp | Các phần tử thành viên có thể `minOccurs=0` |
| Ví dụ | `customerId, line+, note?` | `shipTo` **hoặc** `pickupAt` | `customerId, email?, phone?` bất kể thứ tự |
| Dùng khi | Payload SOAP có quy trình hoặc cấu trúc rõ | Các dạng dữ liệu/thao tác loại trừ nhau | Tập trường đơn lẻ độc lập, không lặp |
| Nguy cơ thiết kế | Khách hàng đổi thứ tự phần tử sẽ lỗi schema | Lặp nhóm có thể cho phép tổ hợp ngoài dự kiến | Không phù hợp danh sách lặp, dễ thiếu quy tắc tổ hợp |

Không có nhóm nào “luôn tốt hơn” nhóm khác. Hợp đồng tốt phải diễn đạt **đúng cấu trúc nghiệp vụ** và có khả năng được các bộ công cụ liên quan hỗ trợ.

## 6. Kết hợp và lồng nhóm cho tình huống thực tế

### 6.1. Sequence chứa choice: đầu chung, giữa chọn nhánh, cuối chung

Ví dụ `CreateOrderRequest` ở mục 2 dùng:

```text
sequence(
  customerId,
  line+,
  choice(shipTo, pickupAt),
  note?
)
```

`shipTo` hoặc `pickupAt` luôn nằm **sau toàn bộ `line`, trước `note`**. Thứ tự tổng thể đến từ `sequence`; loại dữ liệu giao nhận đến từ `choice`.

### 6.2. Choice chứa sequence: mỗi nhánh có bộ trường riêng

Một yêu cầu thanh toán chọn giữa thẻ và chuyển khoản:

```xml
<xs:choice xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:sequence>
        <xs:element name="bankId" type="xs:string"/>
        <xs:element name="transferRef" type="xs:string"/>
    </xs:sequence>
    <xs:sequence>
        <xs:element name="cardToken" type="xs:string"/>
        <xs:element name="cardHolder" type="xs:string"/>
    </xs:sequence>
</xs:choice>
```

Nhánh ngân hàng phải có `bankId` rồi `transferRef`. Nhánh thẻ phải có `cardToken` rồi `cardHolder`. Không được ghép `bankId` với `cardHolder`, và không được đổi thứ tự trong cùng nhánh.

### 6.3. Chọn giữa hai schema gần giống nhau

Cách một:

```text
sequence(header, choice(cardToken, bankReference), total)
```

Cách hai:

```text
choice(
  sequence(header, cardToken, total),
  sequence(header, bankReference, total)
)
```

Về các tên phần tử đơn giản, hai cách có thể chấp nhận cùng những chuỗi. Tuy nhiên, cách hai **lặp định nghĩa** `header` và `total`, dễ gặp ràng buộc phức tạp, quy tắc quyết định nhánh và vấn đề bảo trì khi kiểu dữ liệu phát triển. Hãy ưu tiên tách phần chung khi cấu trúc nghiệp vụ thực sự chung; không phải cứ lồng nhiều lớp là hợp đồng “chặt” hơn.

## 7. Lỗi schema mơ hồ: Unique Particle Attribution (UPA)

XML Schema yêu cầu bộ xác thực có thể quyết định phần tử đầu vào thuộc particle nào mà không dựa vào việc đọc trước phần tử tương lai. Ràng buộc này thường được gọi là **Unique Particle Attribution (UPA)**.

Ví dụ XSD 1.0 dưới đây dễ gây tranh chấp cách khớp khi có một thẻ `code`:

```xml
<xs:complexType xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:sequence>
        <xs:element name="code" type="xs:string" minOccurs="0"/>
        <xs:element name="code" type="xs:string"/>
    </xs:sequence>
</xs:complexType>
```

Một phần tử `<code>A</code>` không cho biết nó nên khớp với particle optional đầu tiên hay particle bắt buộc thứ hai. Đây là ví dụ gây **vi phạm UPA** trong XSD 1.0; lỗi nằm ở **thiết kế schema**, không phải ở một request cụ thể.

Nếu mục tiêu chỉ là cho phép một hoặc hai mã cùng loại, có thể thiết kế đơn giản hơn:

```xml
<xs:element xmlns:xs="http://www.w3.org/2001/XMLSchema"
            name="code" type="xs:string"
            minOccurs="1" maxOccurs="2"/>
```

Nếu hai mã có vai trò khác nhau, nên dùng tên phần tử khác nhau, chẳng hạn `primaryCode` và `secondaryCode`. Với XSD có `choice`, wildcard `xs:any` hoặc các nhóm chồng lấn, phải kiểm tra tính không mơ hồ khi biên dịch schema, không chỉ thử một vài payload thành công.

## 8. QName, namespace và văn bản xen giữa các phần tử

### 8.1. QName thực sự gồm URI namespace và local name

Với `elementFormDefault="qualified"`, những cách sau có thể khác nhau:

```xml
<!-- Đúng namespace mục tiêu -->
<o:customerId xmlns:o="https://example.org/orders/v1">C-100</o:customerId>

<!-- Không namespace: không tương đương phần tử ở trên -->
<customerId>C-100</customerId>
```

Prefix `o` chỉ là bí danh cho URI namespace. Đổi prefix thành `ord` trong khi giữ nguyên URI vẫn biểu thị cùng tên mở rộng. Trong thiết kế hợp đồng, tránh xác thực tên chỉ bằng chuỗi prefix.

### 8.2. Element-only content khác mixed content

Trong XSD ví dụ, `CreateOrderRequest` là kiểu phức hợp chỉ gồm phần tử (*element-only*). Một đoạn văn bản như `Xin chào` giữa hai phần tử không thuộc content model; việc thêm `mixed="true"` chỉ để bỏ qua lỗi sẽ làm thay đổi hợp đồng.

Khoảng trắng do thụt lề trong element-only content thường có thể được bộ xử lý nhận diện là khoảng trắng có vai trò trình bày khi xác thực với schema. Nhưng không suy ra mọi parser đều loại bỏ hoặc giữ giống nhau. Với kiểu `mixed="true"`, văn bản xen giữa các phần tử **là nội dung**, và thứ tự text node cùng element node phải được bảo toàn.

### 8.3. Ràng buộc cấu trúc không đồng nghĩa ràng buộc nghiệp vụ

`xs:sequence` cho phép định nghĩa `quantity` là `xs:positiveInteger`, nhưng không thể tự xác định tồn kho hiện tại. `xs:choice` bảo đảm chọn một nhánh cấu trúc, nhưng không xác minh mã cửa hàng có tồn tại. Cần phân biệt:

1. XML well-formed.
2. XML schema-valid.
3. Dữ liệu business-valid.
4. Thông điệp được xác thực và toàn vẹn theo XML Signature/WS-Security khi có yêu cầu bảo mật.

Các lớp kiểm tra này bổ sung nhau, không thay thế nhau.

## 9. Từ XSD đến JAXB và Spring Web Services

### 9.1. Thứ tự trong JAXB

Trong quy trình contract-first, công cụ JAXB/XJC sinh các lớp Java từ XSD. Ví dụ rút gọn của `CreateOrderRequest` có thể mang annotation:

```java
@XmlAccessorType(XmlAccessType.FIELD)
@XmlType(name = "", propOrder = {
    "customerId",
    "line",
    "shipTo",
    "pickupAt",
    "note"
})
@XmlRootElement(name = "CreateOrderRequest",
                namespace = "https://example.org/orders/v1")
public class CreateOrderRequest {
    @XmlElement(required = true)
    protected String customerId;

    @XmlElement(required = true)
    protected List<OrderLineType> line;

    protected String shipTo;
    protected String pickupAt;
    protected String note;
    // Các getter/setter và annotation thực tế do công cụ sinh mã quyết định.
}
```

Đây là ví dụ **minh họa cấu trúc**, không phải đầu ra bắt buộc của XJC. Tùy JAXB binding và phiên bản công cụ, nhánh `choice` có thể được biểu diễn bằng các trường riêng hoặc cơ chế khác; đừng dùng ví dụ này để suy ra rằng hai trường `shipTo` và `pickupAt` được chặn đồng thời ở mức Java.

Các quy tắc quan trọng:

- `@XmlType(propOrder=...)` thường phản ánh thứ tự khai báo; tự đổi thứ tự field/collection trong mã sinh có thể làm XML marshal khác hợp đồng.
- `maxOccurs="unbounded"` thường ánh xạ thành `List<T>`, giữ thứ tự các phần tử được gửi.
- `minOccurs="0"` không đồng nghĩa với `nillable="true"`. Phần tử vắng mặt, chuỗi rỗng và phần tử có `xsi:nil="true"` là các tình huống khác nhau nếu schema/ứng dụng phân biệt.
- Sinh lại mã từ bản XSD chính thức khi thay đổi hợp đồng; không sửa thủ công file generated rồi bỏ mặc nguồn schema.

Với hệ dùng Jakarta XML Binding, annotation thuộc `jakarta.xml.bind.annotation`; dự án Spring/Java cũ có thể dùng `javax.xml.bind.annotation`. Giữ nhất quán phiên bản framework và JAXB.

### 9.2. SOAP Body mang phần tử do XSD định nghĩa

Với kiểu WSDL **document/literal** thông dụng, một request SOAP 1.1 có thể chứa payload như sau:

```xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
               xmlns:o="https://example.org/orders/v1">
    <soap:Header/>
    <soap:Body>
        <o:CreateOrderRequest>
            <o:customerId>C-100</o:customerId>
            <o:line>
                <o:sku>BOOK-01</o:sku>
                <o:quantity>2</o:quantity>
            </o:line>
            <o:pickupAt>STORE-01</o:pickupAt>
        </o:CreateOrderRequest>
    </soap:Body>
</soap:Envelope>
```

Một endpoint Spring-WS có thể định tuyến bằng phần tử gốc payload:

```java
@Endpoint
public class OrderEndpoint {
    private static final String NS = "https://example.org/orders/v1";

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderResponse create(
            @RequestPayload CreateOrderRequest request) {
        CreateOrderResponse response = new CreateOrderResponse();
        response.setOrderId("ORD-1001");
        response.setStatus("ACCEPTED");
        return response;
    }
}
```

Lớp request/response ở đây mang tính minh họa, cần sinh từ XSD và cấu hình JAXB marshaller/unmarshaller thích hợp. `@PayloadRoot` xác định QName của phần tử payload, **không có trách nhiệm kiểm tra toàn bộ thứ tự phần tử con**.

### 9.3. Xác thực XSD tại biên dịch vụ

Một cấu hình Spring-WS có thể tạo interceptor xác thực schema:

```java
@Bean
public PayloadValidatingInterceptor validatingInterceptor(XsdSchema schema) {
    PayloadValidatingInterceptor interceptor =
            new PayloadValidatingInterceptor();
    interceptor.setXsdSchema(schema);
    interceptor.setValidateRequest(true);
    interceptor.setValidateResponse(true);
    return interceptor;
}
```

Ngoài bean này, cần đăng ký interceptor vào chuỗi xử lý Spring-WS, chẳng hạn qua `WsConfigurer#addInterceptors`, và cấp một `XsdSchema` được tải từ file XSD tương ứng. Đoạn mã minh họa chưa bao gồm các import hoặc toàn bộ cấu hình ứng dụng.

Nếu một request gửi `note` trước nhánh `shipTo/pickupAt`, bộ xác thực có thể báo lỗi kiểu “đã gặp phần tử không mong đợi, đang chờ phần tử ...”. Hình thức SOAP Fault trả về phụ thuộc cấu hình interceptor và exception resolver. Không nên dựa vào một thông điệp lỗi duy nhất cho mọi bản Spring-WS hay mọi trình xác thực.

**Lưu ý:** JAXB unmarshal có thể nhận một XML well-formed ngay cả khi cấu trúc vi phạm XSD, tùy cấu hình. Muốn khẳng định thông điệp đúng hợp đồng, phải xác thực với **đúng bản XSD**. XSD validation cũng không tự xác minh SOAP Header, chứng chỉ hay chữ ký WS-Security.

## 10. Thay đổi sequence/choice/all ảnh hưởng tương thích thế nào?

Trong SOAP contract-first, XSD thường được bên cung cấp công bố cho client. Thay đổi cấu trúc đồng nghĩa thay đổi hợp đồng dữ liệu trên đường truyền.

| Thay đổi XSD | Rủi ro cần kiểm tra |
| --- | --- |
| Đổi thứ tự `customerId` và `line` trong `sequence` | Request đang triển khai có thể không còn hợp lệ |
| Thêm trường bắt buộc vào `sequence` | Client cũ có thể không gửi trường, bị schema mới từ chối |
| Thêm trường tùy chọn ở cuối `sequence` | XML cũ có thể tiếp tục hợp lệ với schema mới; XML mới có trường bổ sung có thể bị client/schema cũ từ chối |
| Đổi `maxOccurs=1` thành `unbounded` | Schema mới nhận nhiều phần tử; mã client cũ có thể chỉ xử lý một |
| Đổi `choice` sang `sequence` | Từ “một nhánh” thành “các phần tử theo thứ tự”, đổi tính bắt buộc và cấu trúc |
| Đổi `sequence` sang `all` | XSD 1.0 có giới hạn về lặp; XML khác thứ tự có thể được chấp nhận, nhưng không bảo đảm client sinh cũ xử lý đúng |
| Thêm nhánh vào `choice` | Client cũ có thể không biết kiểu/nội dung của nhánh mới |
| Đổi `targetNamespace` | QName thay đổi, có thể ảnh hưởng ánh xạ JAXB và định tuyến `@PayloadRoot` |

**Tương thích không chỉ là “schema mới nhận XML cũ”.** Phải kiểm tra cả hai chiều: client cũ gửi request tới server mới, và client cũ nhận response do server mới tạo. Với hợp đồng có WS-Security, mọi chuyển đổi trên XML đã ký còn phải giữ đúng phạm vi ký và quy tắc xác minh.

Khi thay đổi có khả năng phá vỡ tích hợp, nên công bố XSD/WSDL phiên bản mới, chạy contract test giữa các phiên bản và cân nhắc hỗ trợ đồng thời endpoint cũ trong thời gian chuyển đổi.

## 11. Kiểm thử thứ tự và nhóm lựa chọn

Đừng chỉ kiểm thử payload “happy path”. Một ma trận phù hợp với `CreateOrderRequest` ở mục 2:

| Ca thử | Kỳ vọng theo XSD |
| --- | --- |
| `customerId → line → shipTo` | Hợp lệ |
| `customerId → line → pickupAt → note` | Hợp lệ |
| Nhiều `line` liên tiếp, mỗi dòng `sku → quantity` | Hợp lệ |
| `line` xuất hiện trước `customerId` | Không hợp lệ |
| Không có `line` | Không hợp lệ |
| `quantity` xuất hiện trước `sku` trong `line` | Không hợp lệ |
| Có cả `shipTo` và `pickupAt` | Không hợp lệ |
| Không có cả `shipTo` lẫn `pickupAt` | Không hợp lệ |
| `note` trước `shipTo` | Không hợp lệ |
| `note` vắng mặt | Hợp lệ |
| `quantity=0` | Không hợp lệ vì `xs:positiveInteger` |
| `customerId` thiếu namespace mục tiêu | Không hợp lệ với `elementFormDefault="qualified"` |

Đối với `UpdateContactRequest` dùng `xs:all` ở mục 4, kiểm thêm các trường xuất hiện theo nhiều thứ tự và trường hợp lặp `email`; thứ tự đảo là hợp lệ nhưng `email` lặp không hợp lệ theo XSD minh họa.

Kiểm thử nhiều lớp trong Spring-WS:

1. **Biên dịch và validate XSD:** đảm bảo schema tự hợp lệ, không vi phạm UPA và nhận/từ chối đúng các XML mẫu.
2. **JAXB round-trip:** marshal rồi unmarshal các trường lặp và nhánh lựa chọn, so sánh đúng cấu trúc/giá trị.
3. **Endpoint test:** dùng `MockWebServiceClient` để gửi payload đúng và sai; kiểm tra response hoặc SOAP Fault.
4. **Client test:** dùng `MockWebServiceServer` để kiểm tra XML thực sự gửi bởi `WebServiceTemplate`, không chỉ đối tượng Java.
5. **Contract test liên phiên bản:** dùng cả XSD/WSDL cũ và mới, thử hai chiều giao tiếp.
6. **Kiểm thử bảo mật nếu có WS-Security:** xác minh chữ ký/chứng chỉ, bảo đảm quá trình serialize/transform không làm thay đổi dữ liệu đã ký theo cách không được phép.

Nếu cần kiểm tra XML bằng Java thuần, `javax.xml.validation.SchemaFactory` và `Validator` có thể thực hiện XSD validation; khi tải schema/XML từ nguồn không tin cậy cần giới hạn truy cập thực thể và tài nguyên ngoài theo chính sách XML security của hệ thống.

## 12. Bài tập tự kiểm tra

**Câu 1.** XSD khai báo:

```xml
<xs:sequence xmlns:xs="http://www.w3.org/2001/XMLSchema">
    <xs:element name="id" type="xs:string"/>
    <xs:element name="item" type="xs:string"
                minOccurs="1" maxOccurs="unbounded"/>
    <xs:element name="note" type="xs:string" minOccurs="0"/>
</xs:sequence>
```

Chuỗi `id, item, note, item` có hợp lệ không?

**Đáp án:** Không. Các `item` phải nằm liên tiếp sau `id` và trước `note`. `maxOccurs="unbounded"` cho phép lặp tại vị trí khai báo, không cho phép xuất hiện lại sau `note`.

**Câu 2.** `<xs:choice maxOccurs="unbounded">` chứa hai phần tử `email` và `phone`. Một XML có thể gửi `email, phone, email` không?

**Đáp án:** Có, nếu không có ràng buộc bổ sung. Mỗi lượt lặp của nhóm chọn một nhánh; nhóm cho phép nhiều lượt.

**Câu 3.** Khi dùng XSD 1.0, có thể khai báo `xs:all` chứa `phone maxOccurs="unbounded"` không?

**Đáp án:** Không. Trong XSD 1.0, mỗi phần tử trực tiếp trong `all` có `maxOccurs=1`; cần thiết kế danh sách hoặc nhóm khác.

**Câu 4.** `<A/><B/>` và `<B/><A/>` đều được XSD nhận. Có chắc schema sử dụng `xs:all` không?

**Đáp án:** Không. `xs:choice` lặp, các nhánh `xs:sequence` hoặc nhiều mô hình khác cũng có thể chấp nhận cả hai thứ tự; cần đọc schema.

**Câu 5.** Một service nhận XML parse thành công nhưng interceptor trả SOAP Fault khi phần tử `pickupAt` đứng trước `line`. Vì sao?

**Đáp án:** XML well-formed nhưng trái với `xs:sequence` trong XSD. Interceptor xác thực cấu trúc payload, còn parser chỉ đọc cú pháp XML.

**Câu 6.** Hợp đồng mới thêm `couponCode minOccurs="0"` ở cuối request. Client cũ có chắc nhận được mọi response từ server mới không?

**Đáp án:** Không. Việc thêm trường tùy chọn có thể giữ request cũ hợp lệ trên schema mới, nhưng không bảo đảm schema/mã JAXB cũ chấp nhận message mới có trường bổ sung, và còn phải xét các thay đổi khác.

## Ghi nhớ

- **`xs:sequence` quyết định thứ tự.** Số lần lặp của một phần tử không cho phép nó xuất hiện ngoài vị trí đã khai báo.
- **`xs:choice` chọn nhánh.** Lặp cả nhóm choice có thể cho phép chọn nhiều nhánh qua nhiều lượt.
- **`xs:all` bỏ ràng buộc thứ tự cho các trường thành viên**, nhưng ở XSD 1.0 không hỗ trợ lặp các trường đó như một danh sách.
- **Lồng nhóm để biểu diễn đúng nghiệp vụ:** nhóm chung dùng `sequence`; các phương án loại trừ nhau dùng `choice`; các trường đơn lẻ không quan trọng thứ tự có thể dùng `all`.
- **Thiết kế XSD là thiết kế hợp đồng.** Validate schema, JAXB, endpoint/client, SOAP Fault, tương thích phiên bản và WS-Security cần được kiểm chứng độc lập theo hệ thống thực tế.
