# minOccurs, maxOccurs và mô hình hóa danh sách

Trong module **SPRING_WEB_SERVICES**, hợp đồng SOAP được thiết kế theo hướng **contract-first**: XSD định nghĩa cấu trúc XML trước khi Spring Web Services (Spring-WS) nhận payload vào endpoint hoặc SOAP client tạo request bằng JAXB. Một quyết định có ảnh hưởng lớn đến hợp đồng là **mỗi phần tử được phép xuất hiện bao nhiêu lần**. Hai thuộc tính XSD `minOccurs` và `maxOccurs` thể hiện quy tắc đó, đồng thời quyết định cách biểu diễn **trường bắt buộc, trường tùy chọn và danh sách**.

Nếu chọn sai cardinality, một client có thể tạo XML hợp lệ theo cách hiểu của mình nhưng bị server từ chối; JAXB có thể sinh kiểu khác dự kiến; và khi nâng phiên bản hợp đồng, những thay đổi tưởng như nhỏ có thể phá vỡ tích hợp với Java, .NET hoặc nền tảng khác. Bài này đi từ các khái niệm XSD đến mẫu thiết kế, JAXB, validation, SOAP Fault, XML security và kiểm thử tương thích.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích miền số lần xuất hiện `minOccurs..maxOccurs`, giá trị mặc định và vị trí được phép khai báo.
2. Thiết kế danh sách với phần tử `item` lặp trong một phần tử `items` bao, và phân biệt danh sách bắt buộc, tùy chọn, được phép rỗng.
3. Phân biệt **không xuất hiện**, **xuất hiện nhưng rỗng**, **`xsi:nil="true"`** và **phần tử lặp**.
4. Hiểu ảnh hưởng của `xs:sequence`, `xs:choice`, QName/namespace và type của phần tử lên XML hợp lệ.
5. Dự đoán cách JAXB biểu diễn danh sách; tổ chức validate request/response và xử lý lỗi trong Spring-WS.
6. Xây dựng ma trận kiểm thử các giá trị biên và đánh giá rủi ro tương thích khi thay đổi XSD.

## 1. Khái niệm cardinality: một phần tử có thể lặp mấy lần?

Trong XSD, mỗi **particle** (thành phần của content model như khai báo phần tử con hoặc nhóm) có khoảng số lần xuất hiện hợp lệ. Với một phần tử con:

~~~xml
<xs:element name="item" type="ord:OrderItemType"
            minOccurs="1" maxOccurs="100"/>
~~~

ý nghĩa là khi phần tử cha xuất hiện, bên trong nó phải có từ **1 đến 100** phần tử `item` ở vị trí mà content model cho phép.

- `minOccurs`: số lần xuất hiện tối thiểu, là số nguyên không âm.
- `maxOccurs`: số lần xuất hiện tối đa, là số nguyên không âm không nhỏ hơn `minOccurs`, hoặc từ khóa `unbounded`.
- Khi **không ghi** hai thuộc tính, trong các vị trí khai báo hợp lệ, XSD mặc định `minOccurs="1"` và `maxOccurs="1"`: phần tử xuất hiện **đúng một lần**.
- `minOccurs="0"` cho phép vắng mặt; nó không có nghĩa rằng phần tử có thể chứa giá trị tùy ý khi đã xuất hiện.
- `maxOccurs="unbounded"` cho phép lặp không giới hạn **ở mức schema**; môi trường triển khai vẫn cần giới hạn kích thước và tài nguyên xử lý.

### 1.1. Những khoảng thường dùng

| Khai báo trên một phần tử con | Khoảng hợp lệ | Cách hiểu thực tế |
| --- | --- | --- |
| Không khai báo `minOccurs/maxOccurs` | 1..1 | Bắt buộc, đúng một phần tử |
| `minOccurs="0"` | 0..1 | Trường tùy chọn, xuất hiện tối đa một lần |
| `minOccurs="0" maxOccurs="unbounded"` | 0..∞ | Danh sách có thể không có phần tử |
| `minOccurs="1" maxOccurs="unbounded"` | 1..∞ | Danh sách bắt buộc có ít nhất một phần tử |
| `minOccurs="1" maxOccurs="100"` | 1..100 | Danh sách không rỗng với số lượng tối đa |
| `minOccurs="2" maxOccurs="5"` | 2..5 | Bắt buộc có ít nhất hai phần tử |

Ký hiệu `∞` trong bảng là cách giải thích cho từ khóa `unbounded`, không phải giá trị viết vào XSD.

Một hiểu lầm thường gặp: `maxOccurs="unbounded"` không tự làm phần tử **tùy chọn**. Nếu không khai báo `minOccurs`, mặc định vẫn là 1. Muốn danh sách có thể không có phần tử, phải ghi rõ `minOccurs="0"`.

### 1.2. Vị trí đặt `minOccurs` và `maxOccurs`

Hai thuộc tính dùng trên các khai báo **phần tử cục bộ trong content model** và một số nhóm như `xs:sequence`, `xs:choice`, `xs:group ref` ở nơi schema cho phép. Chúng không phải thuộc tính để gắn tùy tiện lên **global element** tại cấp schema.

Ví dụ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <!-- Global element: không đặt minOccurs/maxOccurs ở đây. -->
  <xs:element name="Catalog">
    <xs:complexType>
      <xs:sequence>
        <!-- Local element: được khai báo cardinality. -->
        <xs:element name="code" type="xs:string"
                    minOccurs="1" maxOccurs="1"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Một global element là phần tử có thể dùng làm root của tài liệu XML, chẳng hạn SOAP Body payload `SubmitOrderRequest`; việc payload root có bắt buộc khi gọi thao tác nào là vấn đề của WSDL/protocol và thiết kế thông điệp. Cardinality cho các trường bên trong root nằm trong content model của XSD.

## 2. Kịch bản xuyên suốt: danh sách mặt hàng trong SOAP request

Giả sử client gửi `SubmitOrderRequest` đến một endpoint Spring-WS. Yêu cầu nghiệp vụ:

- `requestId` bắt buộc, dùng theo dõi và phát hiện thao tác gửi lại.
- `items` bắt buộc; bên trong phải có **ít nhất 1 và nhiều nhất 100** dòng `item`.
- Mỗi `item` có đúng một `sku` và một `quantity`; quantity thuộc 1..999.
- `tag` là nhãn nghiệp vụ bổ sung, có thể có **0 đến 10** phần tử.
- `requestedDeliveryDate` là ngày giao mong muốn, có thể bị bỏ.
- Response trả `orderId`, `acceptedItemCount` và `status`. Việc server nhận yêu cầu không đồng nghĩa đơn đã được giao.

Dạng XML thành công mong đợi:

~~~xml
<ord:SubmitOrderRequest
    xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-2026-0001</ord:requestId>
  <ord:items>
    <ord:item>
      <ord:sku>SKU-01</ord:sku>
      <ord:quantity>2</ord:quantity>
    </ord:item>
    <ord:item>
      <ord:sku>SKU-02</ord:sku>
      <ord:quantity>1</ord:quantity>
    </ord:item>
  </ord:items>
  <ord:tag>priority</ord:tag>
  <ord:tag>gift</ord:tag>
  <ord:requestedDeliveryDate>2026-12-05</ord:requestedDeliveryDate>
</ord:SubmitOrderRequest>
~~~

Có ba cấp cần phân biệt:

1. Cặp phần tử **request root**: `SubmitOrderRequest` xuất hiện như payload trong một SOAP Body.
2. Phần tử bao **`items`**: ở ví dụ này xuất hiện đúng một lần trong request.
3. Phần tử con **`item`**: lặp từ 1 đến 100 lần **trong một `items`**.

Đặt `maxOccurs` trên `item` và trên `items` dẫn đến hai hợp đồng khác nhau. Chúng ta chọn một wrapper duy nhất, bên trong chứa các dòng lặp.

## 3. Một XSD hoàn chỉnh cho request và response

File minh họa `orders.xsd` dưới đây sử dụng XSD 1.0 và một namespace hợp đồng duy nhất.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:v1"
    targetNamespace="urn:example:orders:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="QuantityType">
    <xs:restriction base="xs:positiveInteger">
      <xs:maxInclusive value="999"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="OrderItemType">
    <xs:sequence>
      <xs:element name="sku" type="xs:string"/>
      <xs:element name="quantity" type="ord:QuantityType"/>
    </xs:sequence>
  </xs:complexType>

  <!-- Một tập items gồm từ 1 đến 100 dòng item. -->
  <xs:complexType name="OrderItemsType">
    <xs:sequence>
      <xs:element name="item" type="ord:OrderItemType"
                  minOccurs="1" maxOccurs="100"/>
    </xs:sequence>
  </xs:complexType>

  <!-- Payload request: global element -->
  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="xs:string"/>

        <xs:element name="items" type="ord:OrderItemsType"
                    minOccurs="1" maxOccurs="1"/>

        <xs:element name="tag" type="xs:string"
                    minOccurs="0" maxOccurs="10"/>

        <xs:element name="requestedDeliveryDate" type="xs:date"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <!-- Payload response: global element -->
  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="orderId" type="xs:string"/>
        <xs:element name="acceptedItemCount"
                    type="xs:nonNegativeInteger"/>
        <xs:element name="status" type="xs:string"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

XSD trên định nghĩa **cấu trúc và một số giới hạn miền giá trị**; đó chưa phải toàn bộ hợp đồng nghiệp vụ. Ví dụ, `requestId` và `sku` là `xs:string`, vì vậy XSD chưa cấm chuỗi rỗng, chưa kiểm tra `sku` tồn tại và chưa phát hiện đơn gửi trùng. `acceptedItemCount` chỉ được kiểm tra không âm; XSD 1.0 trong ví dụ không kiểm tra nó bằng số lượng `item` đã gửi ở một thông điệp khác. Những điều này cần quy tắc và kiểm thử nghiệp vụ riêng.

### 3.1. Vì sao có cả `items` và `item`?

Wrapper `items` cho cấu trúc ổn định để nhóm các dòng hàng:

~~~text
SubmitOrderRequest
├── requestId               1..1
├── items                   1..1
│   └── item                1..100
│       ├── sku             1..1
│       └── quantity        1..1
├── tag                     0..10
└── requestedDeliveryDate   0..1
~~~

Đây là ký hiệu mô tả cây, không phải cú pháp XSD. Số lần xuất hiện là **cục bộ trong phần tử cha**. Một `item` chỉ có ý nghĩa trong `items` đang chứa nó; `item` không tự trở thành một SOAP operation hay một thông điệp gốc.

Lợi ích của wrapper:

- SOAP client/JAXB và người đọc XML thấy ranh giới danh sách rõ.
- Có nơi hợp lý để mở rộng metadata thuộc **cả danh sách** sau này, nếu kế hoạch versioning cho phép.
- Tránh lẫn các dòng hàng với những phần tử lặp khác, như `tag`.
- Dễ kiểm tra tổng số dòng trong một nơi xác định.

Tuy nhiên wrapper cũng là một phần hợp đồng: thay đổi từ `<item>...` trực tiếp dưới request sang `<items><item>...</item></items>` là thay đổi cấu trúc XML và có thể làm client hiện tại không tương thích.

### 3.2. Namespace và thứ tự vẫn phải chính xác

`elementFormDefault="qualified"` khiến các phần tử cục bộ `items`, `item`, `sku`, `quantity` cũng thuộc `urn:example:orders:v1`. Prefix `ord` có thể đổi, nhưng namespace URI và local name phải đúng.

`xs:sequence` yêu cầu thứ tự các nhóm: `requestId` → `items` → các `tag` (nếu có) → `requestedDeliveryDate` (nếu có). Trong `items`, mọi `item` xuất hiện liên tiếp; trong `item`, `sku` đứng trước `quantity`. Request đảo `quantity` lên trước `sku` sẽ không hợp lệ theo schema, dù có đủ cả hai trường.

## 4. Đếm bao nhiêu phần tử mới đúng?

### 4.1. Ví dụ hợp lệ

**Một dòng duy nhất** và không có phần tử tùy chọn:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-1</ord:requestId>
  <ord:items>
    <ord:item>
      <ord:sku>A</ord:sku>
      <ord:quantity>1</ord:quantity>
    </ord:item>
  </ord:items>
</ord:SubmitOrderRequest>
~~~

**Hai dòng hàng, ba nhãn, có ngày giao**:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-2</ord:requestId>
  <ord:items>
    <ord:item><ord:sku>A</ord:sku><ord:quantity>3</ord:quantity></ord:item>
    <ord:item><ord:sku>B</ord:sku><ord:quantity>5</ord:quantity></ord:item>
  </ord:items>
  <ord:tag>new-customer</ord:tag>
  <ord:tag>promotion</ord:tag>
  <ord:tag>gift</ord:tag>
  <ord:requestedDeliveryDate>2026-12-05</ord:requestedDeliveryDate>
</ord:SubmitOrderRequest>
~~~

**Không có `tag`** là hợp lệ vì `tag` có `minOccurs=0`. **Không có ngày giao** cũng hợp lệ. Nhưng `items` và ít nhất một `item` luôn phải có.

### 4.2. Ví dụ không hợp lệ

**Thiếu wrapper `items`**:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-3</ord:requestId>
</ord:SubmitOrderRequest>
~~~

**Wrapper xuất hiện nhưng không chứa `item`**:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-4</ord:requestId>
  <ord:items/>
</ord:SubmitOrderRequest>
~~~

**Có `item` trực tiếp dưới request, bỏ wrapper**:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-5</ord:requestId>
  <ord:item><ord:sku>A</ord:sku><ord:quantity>1</ord:quantity></ord:item>
</ord:SubmitOrderRequest>
~~~

Ngoài ra, có **101** `item`, có **11** `tag`, `quantity=0` hoặc thiếu `sku` đều vi phạm schema. Các lỗi này không giống lỗi nghiệp vụ “SKU không tồn tại”: XSD có thể kiểm tra số lượng và kiểu khai báo; hệ thống nghiệp vụ phải kiểm tra mã hàng có thực, còn bán hay không.

### 4.3. Ba biến thể mô hình danh sách hay gặp

Giả sử một tài liệu chỉ có một vùng `items`; cách khai báo các phần tử con ảnh hưởng đến việc chấp nhận danh sách rỗng:

| Mẫu | Khai báo wrapper | Khai báo item bên trong | Ý nghĩa |
| --- | --- | --- | --- |
| A: Bắt buộc, không rỗng | `items 1..1` | `item 1..100` | Luôn có wrapper và ít nhất một item |
| B: Wrapper tùy chọn, mỗi wrapper không rỗng | `items 0..1` | `item 1..100` | Có thể bỏ wrapper; đã có thì ít nhất một item |
| C: Wrapper bắt buộc, danh sách có thể rỗng | `items 1..1` | `item 0..100` | Luôn có wrapper; `<items/>` hợp lệ |
| D: Wrapper tùy chọn và có thể rỗng | `items 0..1` | `item 0..unbounded` | Có thể bỏ wrapper, hoặc có wrapper rỗng |

**Không nên chọn B, C, D chỉ theo sở thích code.** Hãy hỏi nghiệp vụ: “Không có danh sách” có khác “Danh sách rỗng được gửi có chủ ý” không? Nếu server xử lý hai trạng thái khác nhau (ví dụ PATCH-like semantics trong một thao tác có tác dụng thay đổi), hợp đồng phải mô tả chính xác điều đó.

## 5. Phân biệt phần tử vắng mặt, rỗng và `xsi:nil`

Đây là nguồn lỗi tích hợp thường thấy khi XML được chuyển qua Java/JAXB.

### 5.1. Vắng mặt không đồng nghĩa phần tử rỗng

Với phần tử `clientNote` tùy chọn:

~~~xml
<xs:element name="clientNote" type="xs:string" minOccurs="0"/>
~~~

Hai trường hợp:

~~~xml
<!-- 1: không có thẻ clientNote -->
<!-- 2: có thẻ clientNote, giá trị là chuỗi rỗng -->
<ord:clientNote xmlns:ord="urn:example:orders:v1"/>
~~~

đều có thể hợp lệ theo schema trên. Nhưng **ngữ nghĩa nghiệp vụ** có thể khác: “không cung cấp ghi chú” so với “cung cấp ghi chú rỗng”. Với `xs:string`, phần tử rỗng là chuỗi độ dài 0; nếu muốn cấm rỗng, dùng `xs:minLength` phù hợp.

### 5.2. `minOccurs=0` không tự cho phép `xsi:nil`

~~~xml
<xs:element name="clientNote" type="xs:string"
            minOccurs="0" nillable="true"/>
~~~

khi khai báo như trên, dữ liệu có thể **vắng mặt** hoặc xuất hiện với `xsi:nil="true"`:

~~~xml
<ord:clientNote
    xmlns:ord="urn:example:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

Nếu không khai báo `nillable="true"`, giá trị mặc định là `false`, và biểu thức `xsi:nil="true"` sẽ vi phạm schema. Nói cách khác:

- `minOccurs` kiểm soát **số phần tử**;
- `nillable` kiểm soát **một phần tử đã xuất hiện có thể mang trạng thái nil hay không**;
- **Giá trị rỗng** được quyết định thêm bởi kiểu và ràng buộc XSD.

Không nên bật `nillable` trên mọi trường cho tiện: JAXB và client khác nền tảng có thể phân biệt `null`, node vắng mặt và nil không hoàn toàn giống nhau; phải có lý do nghiệp vụ và test rõ ràng.

### 5.3. Danh sách rỗng khác phần tử lặp có giá trị nil

Với mẫu C ở mục 4, `<ord:items/>` nghĩa là wrapper có mặt nhưng danh sách có **0 item**. Nếu cho phép `item nillable="true"`, một `<ord:item xsi:nil="true"/>` vẫn **được tính là một lần xuất hiện** của `item` dù không có dữ liệu item. Về nghiệp vụ, “một dòng hàng nil” thường vô nghĩa; trong ví dụ đặt hàng, không nên bật `nillable` cho `item`.

### 5.4. `maxOccurs` giới hạn số nút, không giới hạn nội dung

`maxOccurs="100"` giới hạn tối đa 100 phần tử `item` trong wrapper, nhưng không giới hạn độ dài của chuỗi `sku`, tổng kích thước tài liệu hoặc số lớp XML lồng nhau ở các nhánh khác. Hãy phối hợp:

- `xs:maxLength`/`xs:pattern` cho mã hàng.
- `xs:minInclusive`/`xs:maxInclusive` cho số lượng.
- `maxOccurs` hữu hạn cho các collection phù hợp nghiệp vụ.
- Hạn mức SOAP request, parser, số node/độ sâu XML, timeout và bộ nhớ ở hạ tầng.

Tăng `maxOccurs` lên `unbounded` không phải “nới giới hạn cho an toàn”; khi nhận XML không tin cậy, nó có thể tạo rủi ro tiêu thụ tài nguyên.

## 6. Các cách mô hình danh sách: chọn kiểu nào?

### 6.1. Danh sách với wrapper và phần tử lặp

~~~xml
<xs:element name="items">
  <xs:complexType>
    <xs:sequence>
      <xs:element name="item" type="ord:OrderItemType"
                  minOccurs="1" maxOccurs="100"/>
    </xs:sequence>
  </xs:complexType>
</xs:element>
~~~

Đây là lựa chọn chính cho danh sách đối tượng phức hợp trong SOAP. XML tạo cấu trúc `<items><item>...</item></items>`, thuận lợi cho XSD validation và JAXB.

### 6.2. Danh sách không có wrapper

~~~xml
<xs:sequence>
  <xs:element name="requestId" type="xs:string"/>
  <xs:element name="item" type="ord:OrderItemType"
              minOccurs="1" maxOccurs="100"/>
</xs:sequence>
~~~

XML hợp lệ:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:requestId>REQ-6</ord:requestId>
  <ord:item><ord:sku>A</ord:sku><ord:quantity>2</ord:quantity></ord:item>
  <ord:item><ord:sku>B</ord:sku><ord:quantity>4</ord:quantity></ord:item>
</ord:SubmitOrderRequest>
~~~

Đoạn XSD ở đầu mục là **phần content model minh họa thay thế** cho request ở mục 3, không được áp dụng đồng thời với wrapper `items` trong cùng khai báo. Dạng không wrapper có thể phù hợp với XML ngắn gọn hoặc hợp đồng đã chốt như vậy, nhưng khi cần metadata cho cả danh sách, phải lên phương án thay đổi cấu trúc và kiểm tra tương thích.

### 6.3. `xs:list` không phải danh sách phần tử XML

XSD còn có `xs:list`:

~~~xml
<xs:simpleType name="CodesType">
  <xs:list itemType="xs:token"/>
</xs:simpleType>

<xs:element name="codes" type="ord:CodesType"/>
~~~

Giá trị XML có dạng:

~~~xml
<ord:codes xmlns:ord="urn:example:orders:v1">A B C</ord:codes>
~~~

Đây là một **phần tử đơn** chứa danh sách lexical được phân tách bằng khoảng trắng; nó khác hoàn toàn với ba phần tử `<ord:code>A</ord:code>`, `<ord:code>B</ord:code>`, `<ord:code>C</ord:code>`. Không nên dùng `xs:list` cho danh sách đối tượng phức tạp như order items. Nếu chọn `xs:list`, phải hiểu quy tắc whitespace, kiểu item đơn giản, JAXB binding và các hạn chế phân tích/biểu diễn của đối tác.

### 6.4. `xs:choice` và nhóm lặp

Đôi khi mỗi vị trí trong danh sách có thể là một trong nhiều lựa chọn:

~~~xml
<xs:choice minOccurs="1" maxOccurs="3">
  <xs:element name="email" type="xs:string"/>
  <xs:element name="phone" type="xs:string"/>
</xs:choice>
~~~

Content model này yêu cầu **tổng số lựa chọn** từ 1 đến 3, mỗi lần chọn `email` **hoặc** `phone`. Nó **không** có nghĩa “tối đa ba email và tối đa ba phone riêng rẽ”; cả nhóm `choice` được lặp. JAXB có thể sinh kiểu và collection khác biệt so với `xs:sequence` có từng trường lặp; cần thử sinh code và kiểm tra XML wire thực tế.

Một lỗi khác: khai báo `<xs:sequence minOccurs="0" maxOccurs="unbounded">...` làm cả **nhóm** lặp, nên số lượng từng phần tử phụ thuộc mẫu lặp của nhóm. Hãy đặt cardinality đúng nơi biểu diễn yêu cầu nghiệp vụ, đồng thời tránh cấu trúc nhập nhằng để các validator và client khác nhau xử lý nhất quán.

## 7. Từ XSD sang JAXB: vì sao collection có hình dạng đó?

Spring-WS theo hướng contract-first thường sinh lớp JAXB từ XSD (ví dụ bằng XJC hoặc plugin build thích hợp) rồi dùng `Jaxb2Marshaller` trong endpoint/client. Đối với một khai báo có `maxOccurs > 1` hoặc `unbounded`, JAXB thường tạo thuộc tính dạng `List<T>`.

Ví dụ Java thường thấy ở lớp JAXB sinh từ `OrderItemsType` (lược bỏ annotation và chi tiết sinh code):

~~~java
public class OrderItemsType {
    protected List<OrderItemType> item;

    public List<OrderItemType> getItem() {
        if (item == null) {
            item = new ArrayList<>();
        }
        return this.item;
    }
}
~~~

Đây là **mẫu code minh họa**, không bảo đảm mọi phiên bản XJC, binding file hay cấu hình plugin sinh mã y hệt. Nhiều JAXB generated class cung cấp **live list** qua getter mà không sinh `setItem(List<...>)`.

Cách thêm dòng hàng:

~~~java
OrderItemsType items = new OrderItemsType();

OrderItemType first = new OrderItemType();
first.setSku("SKU-01");
// Kiểu Java thực tế của quantity phụ thuộc JAXB binding.
first.setQuantity(BigInteger.valueOf(2));

items.getItem().add(first);

SubmitOrderRequest request = new SubmitOrderRequest();
request.setRequestId("REQ-2026-0001");
request.setItems(items);
~~~

`BigInteger` trong ví dụ tương ứng với cách JAXB phổ biến ánh xạ từ `xs:positiveInteger`; cần kiểm tra kiểu đã sinh thực tế. Tên class/getter/setter ở đây dựa trên XSD ví dụ và được dùng để diễn giải, không phải lời hứa về output của một generator/version cụ thể.

### 7.1. `null`, collection rỗng và schema có thể không khớp

Một số tình huống:

| Trạng thái trong Java | XML có thể tạo ra | Hợp đồng ví dụ ở mục 3 |
| --- | --- | --- |
| `request.setItems(null)` | Không có `items` | **Không hợp lệ**: wrapper 1..1 |
| `request.setItems(new OrderItemsType())` với list rỗng | `<items/>` | **Không hợp lệ**: item 1..100 |
| `items.getItem().add(first)` | Có một `item` | Hợp lệ nếu các trường khác đúng |
| Thêm 101 phần tử vào list | 101 thẻ `item` | **Không hợp lệ**: quá `maxOccurs=100` |
| Đặt quantity bằng 0 | `<quantity>0</quantity>` | **Không hợp lệ**: kiểu `QuantityType` |

**Điều quan trọng:** JAXB marshal/unmarshal thành công chưa tự chứng minh dữ liệu thỏa mọi ràng buộc XSD. Khi cần contract validation, phải cấu hình schema validation trên payload hoặc JAXB marshaller/unmarshaller theo cách phù hợp và kiểm thử lỗi thực tế. Ngay cả khi trong Java không có setter hạn chế size của list, XSD vẫn quy định maxOccurs trên XML được trao đổi.

### 7.2. Trường tùy chọn và danh sách lặp dễ tạo khác biệt Java/.NET

Một phần tử `minOccurs=0` không lặp thường ánh xạ thành nullable reference hoặc cơ chế biểu diễn sự hiện diện tùy công cụ. Với kiểu primitive, một số code generator dùng cặp value + “specified flag” để phân biệt vắng mặt. Với `maxOccurs>1`, Java thường dùng `List<T>`, còn đối tác có thể dùng array/collection khác.

Do đó **hợp đồng nguồn là XSD/WSDL và XML thực tế**, không phải định nghĩa field trong Java. Nếu sinh client từ WSDL, hãy xác minh các trường hợp thiếu wrapper, list rỗng, đúng 100 phần tử, phần tử nil và thứ tự `xs:sequence` trước khi chấp nhận tích hợp.

## 8. Spring-WS kiểm tra số lần xuất hiện ở bước nào?

Một endpoint SOAP có thể được định tuyến theo QName của phần tử gốc trong Body:

~~~java
@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        // Giả định các kiểu JAXB đã được sinh từ orders.xsd.
        // Kiểm tra quyền buyer, SKU tồn tại, idempotency ở tầng nghiệp vụ.
        return new SubmitOrderResponse();
    }
}
~~~

Đây là ví dụ chữ ký endpoint: muốn triển khai chạy được cần điền logic nghiệp vụ, tạo response hợp schema, cấu hình JAXB và exception resolver. **`@PayloadRoot` chỉ hỗ trợ định tuyến theo QName; nó không tự xác nhận `items` có 1..100 phần tử.**

Để kiểm tra XML request ở ranh giới, Spring-WS hỗ trợ `PayloadValidatingInterceptor`. Một ví dụ cấu hình interceptor (giả sử đã cấu hình Spring-WS và `orders.xsd` có trong classpath):

~~~java
@Configuration
@EnableWs
public class OrderValidationConfig implements WsConfigurer {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
            new ClassPathResource("orders.xsd"));
    }

    @Bean
    public PayloadValidatingInterceptor payloadValidator(
            XsdSchema ordersSchema) {
        PayloadValidatingInterceptor interceptor =
            new PayloadValidatingInterceptor();
        interceptor.setXsdSchema(ordersSchema);
        interceptor.setValidateRequest(true);
        return interceptor;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        interceptors.add(payloadValidator(ordersSchema()));
    }
}
~~~

Ví dụ trên lược bỏ các `import` và cấu hình servlet/dependency để tập trung vào luồng validation. `@Configuration` thông thường dùng cơ chế quản lý bean của Spring để gọi lại bean method; nếu không muốn phụ thuộc hành vi đó hoặc dùng cấu hình khác, có thể truyền bean interceptor qua một cấu hình khác phù hợp.

Điểm cần nhớ:

1. XSD phải mô tả đúng payload XML; validator chạy trên request trước khi nghiệp vụ nhận dữ liệu theo cấu hình tương ứng.
2. Request chứa 0 hoặc 101 `item` có thể bị từ chối **ở validation** khi interceptor được bật; nếu không bật, endpoint vẫn cần đảm bảo dữ liệu hợp lệ bằng các lớp kiểm tra thích hợp.
3. Spring-WS có cơ chế xử lý lỗi validation và `EndpointExceptionResolver` để tạo SOAP Fault theo tình huống. Không mặc định mọi lỗi đều có một mã fault/detail giống nhau; hãy kiểm thử và cấu hình contract lỗi.
4. Validation response cũng có thể được cấu hình, đặc biệt hữu ích để phát hiện server tạo XML response sai XSD trong test. Không đưa tài liệu debug nhạy cảm vào SOAP Fault.

Trong môi trường tích hợp, một SOAP client sử dụng `WebServiceTemplate` có thể marshal request bằng JAXB. Nếu client gửi list quá dài, lỗi có thể xuất hiện từ validation phía client **nếu được cấu hình**, hoặc từ validator phía server. Việc `marshalSendAndReceive` thực hiện được không phải bằng chứng request đúng schema.

### 8.1. Lỗi cardinality và SOAP Fault

Ví dụ request có `<items/>` theo schema mục 3. XSD sẽ báo thiếu phần tử `item`; server có thể trả SOAP Fault thuộc nhóm lỗi request. Với SOAP 1.1, lỗi request thường tương ứng `Client`; SOAP 1.2 dùng `Sender` và có cấu trúc Fault khác. Client nên xử lý SOAP Fault qua luồng fault của Spring-WS, thay vì mong nó là `SubmitOrderResponse`.

Các lỗi nghiệp vụ như `SKU_NOT_FOUND` hoặc `DUPLICATE_REQUEST_ID` vẫn cần ánh xạ exception/fault detail riêng. Tính hợp lệ của XML không chứng minh một đơn hàng được phép tạo.

## 9. Tính tương thích khi thay đổi `minOccurs`/`maxOccurs`

Schema thường là hợp đồng giữa nhiều hệ thống triển khai và phát hành độc lập. Thay đổi cardinality có thể làm những client đang hoạt động bị từ chối hoặc hiểu sai dữ liệu.

| Thay đổi trong XSD | Hậu quả điển hình | Cần kiểm tra |
| --- | --- | --- |
| `minOccurs=1` → `0` cho một field | Server mới chấp nhận field bị thiếu; code cũ có thể giả định luôn có giá trị | Logic `null`, business rule, client sinh từ schema |
| `minOccurs=0` → `1` | Request cũ thiếu field trở nên không hợp lệ | Tất cả client cũ |
| `maxOccurs=100` → `200` | Client mới có thể gửi >100 item mà server cũ từ chối | Hai chiều client/server và giới hạn hạ tầng |
| `maxOccurs=unbounded` → `100` | Dữ liệu cũ có >100 item bị từ chối | Log sử dụng thực tế, phương án phân trang/chia lô |
| `maxOccurs=1` → `unbounded` | Kiểu JAXB có thể chuyển một field thành `List<T>` | Code sinh client/server, serialization, WSDL |
| Thêm wrapper `items` quanh `item` | Đường dẫn XML và lớp JAXB thay đổi | Client cũ và mapping payload |
| Bật `nillable=true` | Có thể tạo giá trị nil mà client cũ chưa xử lý | Các nền tảng và trường hợp null |
| Thêm phần tử tùy chọn trong `xs:sequence` | Validator dùng schema cũ có thể từ chối XML mới | Thử client cũ nhận response mới |
| Đổi namespace URI | QName của mọi phần tử có thể thay đổi | Endpoint mapping, JAXB/WSDL, XPath, policy bảo mật |

Không mặc định “nới schema thì luôn tương thích”: nếu client hiện tại dùng XSD cố định, nó có thể không chấp nhận XML mới; nếu kiểu mã sinh thay đổi từ đơn thành list, code Java cũng có thể cần sửa.

Để nâng phiên bản an toàn, hãy xác định **ai tạo XML, ai xác thực, ai xử lý** ở từng chiều. Thử ít nhất hai tổ hợp:

- **Client cũ → server mới**: XML cũ có vẫn hợp lệ và giữ nguyên ý nghĩa?
- **Client mới → server cũ**: XML mới có làm server cũ từ chối hoặc hiểu sai?

Nếu phá vỡ hợp đồng hiện hành, cân nhắc công bố namespace/version/operation mới, đặt quy tắc chuyển đổi và lộ trình di trú rõ ràng.

## 10. Cardinality và XML security

Giới hạn số phần tử là một phần nhỏ trong thiết kế XML an toàn:

- **Giới hạn collection:** một `items` chứa tối đa 100 dòng giúp loại bỏ request quá lớn về số dòng trong danh sách này, nhưng không giới hạn mọi nhánh XML.
- **Giới hạn hạ tầng:** server và SOAP client cần cấu hình giới hạn HTTP body, XML parser, độ sâu, timeout và bộ nhớ; tránh XML quá lớn hoặc cấu trúc bất thường.
- **Phòng XXE:** cấu hình parser an toàn, hạn chế truy cập DTD/external entity và không xử lý XML không tin cậy bằng parser mặc định thiếu biện pháp bảo vệ.
- **WS-Security:** chữ ký XML, timestamp, token và mã hóa phải được xác minh bằng thành phần chuyên trách như tích hợp WSS4J; đếm số phần tử bằng XPath không chứng minh chữ ký hợp lệ.
- **TLS/chứng chỉ:** kiểm tra chain tin cậy, hostname và hiệu lực chứng chỉ khi gọi SOAP qua HTTPS; TLS bảo vệ kênh còn WS-Security (nếu áp dụng) bảo vệ thông điệp theo chính sách.
- **SOAP Fault:** trả mã lỗi rõ ràng cho client nhưng không đưa stack trace, token, private key hoặc toàn bộ XML chứa dữ liệu nhạy cảm vào fault/log.

Một tình huống nguy hiểm là một thành phần bảo mật xác minh nút XML này nhưng endpoint lại xử lý nút khác có cùng local name. Khi thiết kế XSD và validation, cần bảo đảm QName, cấu trúc cha/con và đúng phần tử được xác thực khớp với phần tử nghiệp vụ thực sự sử dụng. Hạn chế các lối chọn XPath quá rộng như `//*[local-name()='item']`.

## 11. Ma trận kiểm thử giá trị biên

Hợp đồng `SubmitOrderRequest` trong bài có `items 1..1`, `item 1..100`, `tag 0..10`, `requestedDeliveryDate 0..1`.

| Ca kiểm thử | Kỳ vọng XSD | Giải thích |
| --- | --- | --- |
| Có 1 `items` với 1 `item` | Hợp lệ | Sát biên dưới |
| Có 1 `items` với 100 `item` | Hợp lệ | Sát biên trên |
| Có `<items/>` với 0 `item` | Không hợp lệ | Thiếu 1 `item` bắt buộc |
| Có 1 `items` với 101 `item` | Không hợp lệ | Vượt `maxOccurs=100` |
| Không có `items` | Không hợp lệ | Wrapper bắt buộc |
| Có 2 `items` wrapper | Không hợp lệ | Wrapper 1..1 |
| Không có `tag` | Hợp lệ | Cho phép 0 |
| Có 10 `tag` | Hợp lệ | Đúng giới hạn |
| Có 11 `tag` | Không hợp lệ | Vượt giới hạn |
| Không có `requestedDeliveryDate` | Hợp lệ | Field 0..1 |
| Có 2 `requestedDeliveryDate` | Không hợp lệ | Vượt giới hạn |
| `quantity=0` | Không hợp lệ | Không thỏa `xs:positiveInteger` |
| `quantity=1000` | Không hợp lệ | Vượt `maxInclusive=999` |
| `item` thiếu `sku` | Không hợp lệ | Field con mặc định 1..1 |
| `tag` đứng trước `items` | Không hợp lệ | Sai thứ tự `xs:sequence` |
| Đổi prefix `ord` nhưng giữ URI namespace | Hợp lệ nếu còn đúng cấu trúc | Prefix không làm thay đổi QName |
| Đổi URI namespace hoặc bỏ namespace của `item` | Không hợp lệ | Sai QName theo schema |

Đây là các ca kiểm tra **hợp lệ cấu trúc**. Cần thêm test nghiệp vụ: SKU tồn tại, buyer có quyền, requestId được xử lý chống trùng, quantity đáp ứng quy tắc tồn kho. Nếu dùng WS-Security, thêm test chữ ký sai, timestamp hết hạn hoặc chứng chỉ không được tin cậy.

### 11.1. Kiểm thử trước và sau khi viết endpoint

Trước khi có endpoint, có thể lưu những XML fixtures, chạy XSD validation và thử sinh JAXB client từ XSD/WSDL. Sau khi triển khai Spring-WS:

- Dùng `MockWebServiceClient` gửi request XML vào endpoint test; xác minh 0/101 item bị từ chối khi bật schema validation.
- Dùng `MockWebServiceServer` mô phỏng server để kiểm tra XML mà SOAP client gửi, đặc biệt cấu trúc wrapper, namespace, đúng thứ tự phần tử và cách xử lý SOAP Fault.
- Kiểm tra response được marshal từ JAXB thực sự thỏa XSD và `acceptedItemCount` có đúng với số item đã tiếp nhận theo logic nghiệp vụ.
- Kiểm thử tương thích với client sinh từ WSDL của nền tảng đối tác; không chỉ kiểm tra object Java trong unit test.

### 11.2. Bài tập vận dụng

**Bài 1.** Viết content model XSD cho `attachments` tùy chọn, nhưng **nếu wrapper xuất hiện thì phải có từ 1 đến 5** `attachment`. Gợi ý: wrapper 0..1, phần tử con 1..5. Hãy liệt kê ba XML hợp lệ/không hợp lệ.

**Bài 2.** Nếu `items` buộc phải tồn tại nhưng danh sách hàng có thể rỗng để thể hiện thao tác “xóa toàn bộ”, bạn thay đổi đúng dòng `minOccurs` nào? Vì sao không chỉ thay `minOccurs` trên wrapper?

**Bài 3.** Bạn đổi `quantity` từ một số thành danh sách các mức `quantity` lặp. Điều gì thay đổi ở JAXB và semantics nghiệp vụ? Đây có phải thay đổi tương thích ngược không?

**Bài 4.** Client gửi 150 `item` trong một yêu cầu, server quy định tối đa 100. Bạn sẽ xử lý ở XSD validation, SOAP Fault và tài liệu retry như thế nào? Có nên tự động chia thành hai đơn không?

**Bài 5.** Với cấu trúc `xs:choice minOccurs="1" maxOccurs="3"` chứa `email` và `phone`, XML gồm hai `email` và một `phone` có thể hợp lệ không? Nếu nghiệp vụ yêu cầu “đúng một email, tối đa hai phone” thì cần mô hình lại ra sao?

**Ghi nhớ:** `minOccurs` và `maxOccurs` mô tả **số lần xuất hiện của một particle trong ngữ cảnh cha**, không trực tiếp biểu diễn “list Java”. Thiết kế đúng wrapper và các phần tử lặp, kết hợp QName, `xs:sequence`, nullability, XSD validation, JAXB và kiểm thử SOAP, sẽ giúp hợp đồng Spring-WS rõ ràng và ổn định khi nhiều hệ thống tích hợp với nhau.
