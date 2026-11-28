# xs:include, xs:import và phân chia schema theo namespace

Khi một dịch vụ SOAP lớn dần, việc đặt toàn bộ kiểu dữ liệu, request và response vào một tệp XSD duy nhất khiến hợp đồng khó bảo trì. Các hệ thống doanh nghiệp thường có những kiểu dùng chung như mã đơn hàng, số tiền và địa chỉ, nhưng mỗi nhóm dữ liệu có thể có **namespace riêng** và vòng đời phiên bản riêng. XML Schema cung cấp hai cơ chế quan trọng để tổ chức hợp đồng thành nhiều tệp: **`xs:include`** và **`xs:import`**.

Trong module **SPRING_WEB_SERVICES**, chúng ta xây dựng dịch vụ SOAP theo hướng **contract-first**: XSD xác định payload, WSDL mô tả operation và binding, JAXB ánh xạ XML sang Java, Spring-WS cung cấp endpoint/SOAP client. Các phần như SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích đều phụ thuộc vào việc các bên **hiểu cùng một hợp đồng XML**. Vì vậy, chia schema đúng namespace không chỉ để sắp xếp mã nguồn; nó trực tiếp ảnh hưởng đến QName, WSDL, JAXB và khả năng tích hợp.

## 1. Vì sao phải chia XSD thành nhiều tệp?

Giả sử một hệ thống xử lý đơn hàng có:

- `GetOrderRequest` và `GetOrderResponse` dành cho SOAP operation truy vấn đơn hàng.
- `OrderIdType`, `OrderStatusType` dùng lại bởi nhiều thông điệp trong miền đơn hàng.
- `MoneyType` do miền tài chính quản lý, được sử dụng trong đơn hàng, hóa đơn và thanh toán.

Nếu sao chép `MoneyType` vào từng schema, mỗi nhóm có thể tự sửa danh sách đơn vị tiền tệ hoặc kiểu số theo cách khác nhau. Nếu gom mọi định nghĩa vào một tệp khổng lồ, những thay đổi nhỏ sẽ tạo xung đột biên tập và khó quản lý phiên bản.

Một cách chia có chủ đích:

~~~text
xsd/
├── orders.xsd
├── order/
│   └── order-types.xsd
└── finance/
    └── money-types.xsd
~~~

Ở cấu trúc này, `orders.xsd` là **schema gốc** để biên dịch/kiểm tra contract của payload đơn hàng. `order-types.xsd` cùng namespace với schema gốc và được đưa vào bằng `xs:include`; `money-types.xsd` có namespace khác và được tham chiếu bằng `xs:import`.

Lưu ý: **tệp XSD và namespace không phải một-một**. Một namespace có thể được mô tả bởi nhiều tài liệu XSD. Ngược lại, một tài liệu XSD có một `targetNamespace` (hoặc không khai báo target namespace); nó có thể tham chiếu thành phần ở namespace khác qua import.

## 2. Hiểu đúng targetNamespace, QName và prefix

Trước khi phân biệt include/import, cần nắm ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **`targetNamespace`** | Namespace mà các **global declarations/definitions** trong tài liệu XSD thuộc về | `urn:example:orders:v1` |
| **QName** | Danh tính một tên XML gồm **namespace URI + local name** | `{urn:example:orders:v1}GetOrderRequest` |
| **Namespace prefix** | Bí danh ngắn trỏ đến namespace URI trong một tài liệu XML | `ord`, `fin`; có thể đổi tùy tài liệu |

Ví dụ:

~~~xml
<ord:GetOrderRequest xmlns:ord="urn:example:orders:v1"/>
<o:GetOrderRequest xmlns:o="urn:example:orders:v1"/>
~~~

Hai phần tử trên có **cùng QName** dù prefix khác nhau. Trái lại, nếu đổi URI thành `urn:example:orders:v2` thì đã đổi QName, ngay cả khi local name vẫn là `GetOrderRequest`.

Trong XSD, namespace mặc định dùng cho các phần tử cú pháp schema (ví dụ `xs:element`) không tự làm cho mọi giá trị thuộc tính như `type`, `ref` mang namespace mà bạn muốn. Khi tham chiếu global type/element, hãy dùng QName có prefix được khai báo rõ, ví dụ `type="ord:OrderIdType"` hoặc `type="fin:MoneyType"`. Những tên như `xs:string` là kiểu dựng sẵn trong namespace XML Schema.

### `elementFormDefault` không phải `targetNamespace`

Hai thiết lập giải quyết hai việc khác nhau:

- `targetNamespace` xác định namespace của **global element/type** được khai báo trong schema.
- `elementFormDefault="qualified"` yêu cầu những **local element declarations** trong tài liệu XSD đó thuộc target namespace khi xuất hiện trong XML instance, trừ khi có `form` riêng. Nếu không, local elements có thể không thuộc namespace theo cấu hình mặc định.

Do mỗi tệp XSD có thể khai báo `elementFormDefault` khác nhau, nên khi chia schema cần kiểm tra thiết lập này **trong từng tệp**, không giả định nó được “kế thừa” đơn giản từ tệp gốc.

## 3. `xs:include`: ghép các schema cùng namespace

**`xs:include`** cho phép một tài liệu XSD sử dụng các khai báo và định nghĩa từ một tài liệu schema khác có **cùng `targetNamespace`**. Nó phù hợp để chia một miền dữ liệu thành nhiều tệp mà vẫn giữ nguyên namespace.

Ví dụ `orders.xsd`:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:include schemaLocation="order/order-types.xsd"/>
    <!-- Có thể tham chiếu ord:OrderIdType từ tệp được include. -->
</xs:schema>
~~~

Tệp `order/order-types.xsd` được include cũng khai báo:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:pattern value="ORD-[0-9]{4,}"/>
        </xs:restriction>
    </xs:simpleType>
</xs:schema>
~~~

Sau khi công cụ xử lý schema gốc cùng các tài liệu include, `OrderIdType` là một **global simple type** với QName `{urn:example:orders:v1}OrderIdType`, có thể được tham chiếu trong `orders.xsd` bằng `ord:OrderIdType`.

### Quy tắc của `xs:include`

1. `schemaLocation` của `xs:include` là thuộc tính bắt buộc, chỉ ra vị trí tài liệu schema cần ghép. Đường dẫn tương đối được phân giải theo base URI của tài liệu chứa include.
2. Tệp được include có `targetNamespace` **bằng** namespace của tệp chứa include, **hoặc không có `targetNamespace`** trong trường hợp chameleon schema sẽ giải thích ở phần sau.
3. Một schema có namespace khác **không thể** được đưa vào bằng `xs:include`. Đổi prefix không giải quyết sai khác namespace.
4. Các **global components** được ghép vào cùng tập định nghĩa của namespace. Hai khai báo toàn cục mâu thuẫn có cùng QName sẽ gây lỗi schema compilation; chia file không tạo ra các scope tên độc lập.
5. Include là **quan hệ giữa tài liệu schema**, không phải lệnh copy chuỗi XML tại runtime. Một SOAP client thường không gửi các nội dung `xs:include` trong mỗi message.

**Chọn include khi:** bạn đang chia cùng một domain/namespace thành `order-types.xsd`, `order-requests.xsd`, `order-responses.xsd`, hoặc tách kiểu dùng chung trong **chính namespace đó**.

## 4. `xs:import`: tham chiếu thành phần ở namespace khác

**`xs:import`** cho phép tài liệu XSD tham chiếu global components thuộc **namespace khác** (hoặc namespace rỗng theo cách import tương ứng).

Ví dụ đơn hàng sử dụng `MoneyType` do miền tài chính sở hữu:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           xmlns:fin="urn:example:finance:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">
    <xs:import namespace="urn:example:finance:v1"
               schemaLocation="finance/money-types.xsd"/>

    <xs:element name="OrderTotal" type="fin:MoneyType"/>
</xs:schema>
~~~

Tệp `finance/money-types.xsd` phải mô tả `MoneyType` trong **`urn:example:finance:v1`**, ví dụ:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:finance:v1"
           elementFormDefault="qualified">
    <xs:complexType name="MoneyType">
        <xs:sequence>
            <xs:element name="amount" type="xs:decimal"/>
            <xs:element name="currency" type="xs:string"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

Ở đây, phần tử toàn cục `OrderTotal` vẫn thuộc **namespace đơn hàng**. Chỉ **kiểu dữ liệu** của nó là `fin:MoneyType`. Với một XML instance sử dụng `MoneyType`, các phần tử cục bộ `amount` và `currency` thuộc namespace tài chính do `elementFormDefault="qualified"` trong `money-types.xsd`.

### Các quy tắc đặc biệt của `xs:import`

- `namespace` khai báo **namespace sẽ được import**. Nếu import một namespace cụ thể, URI phải khác `targetNamespace` của tài liệu hiện tại.
- `schemaLocation` của `xs:import` là **tùy chọn**: nó là một gợi ý vị trí để trình xử lý tìm schema. Công cụ có thể đã được cung cấp schema từ nơi khác hoặc dùng XML Catalog, resolver hay cấu hình riêng.
- Import namespace **không tự bảo đảm** công cụ đã tìm được tất cả định nghĩa cần tham chiếu. Phải cung cấp/tải đúng schema dependencies và xác minh compile được.
- Khi cần import các thành phần **không thuộc namespace nào**, `xs:import` được dùng **không có thuộc tính `namespace`** theo quy tắc tương ứng.
- Việc khai báo `xmlns:fin="..."` **chỉ gán prefix**, chưa làm cho các kiểu ở namespace đó trở nên có sẵn. Cần import để công cụ schema hiểu quan hệ tham chiếu.
- Namespace URI là **định danh**, không bắt buộc là URL tải tệp. `schemaLocation` mới là gợi ý vị trí tài nguyên; hai giá trị có vai trò khác nhau.

**Chọn import khi:** schema đơn hàng dùng kiểu từ namespace tài chính, từ một hợp đồng chuẩn bên ngoài hoặc từ một phiên bản namespace riêng của đối tác.

## 5. So sánh nhanh `xs:include` và `xs:import`

| Tiêu chí | `xs:include` | `xs:import` |
| --- | --- | --- |
| Namespace của schema được tham chiếu | Cùng namespace; có thể không có targetNamespace ở chameleon schema | Namespace khác, hoặc không có targetNamespace khi import các thành phần không namespace |
| Mục đích | Tách **một** namespace thành nhiều tệp | Dùng định nghĩa từ **namespace khác** |
| Thuộc tính `schemaLocation` | Bắt buộc | Tùy chọn (gợi ý) |
| Thuộc tính `namespace` | Không có | Tùy chọn trong cú pháp; dùng để xác định namespace được import |
| Ví dụ | `orders.xsd` include `order-types.xsd` | `orders.xsd` import `money-types.xsd` |
| Cách tham chiếu kiểu toàn cục | `type="ord:OrderIdType"` | `type="fin:MoneyType"` |
| Lỗi phổ biến | Include schema khác namespace | Import đúng URI nhưng công cụ không resolve được schema |

> **Quy tắc chọn nhanh:** trước hết so sánh **`targetNamespace`** của hai tài liệu. Cùng namespace thì thường dùng `xs:include`; khác namespace thì dùng `xs:import`. Không quyết định dựa trên tên file, số folder hoặc prefix XML.

## 6. Ví dụ hoàn chỉnh: một schema gốc, hai dependency

Để hiểu cách các tệp liên kết, hãy xây dựng bộ contract có thể dùng làm tài nguyên dự án Spring-WS:

~~~text
src/main/resources/
└── xsd/
    ├── orders.xsd
    ├── order/
    │   └── order-types.xsd
    └── finance/
        └── money-types.xsd
~~~

### 6.1. Tệp cùng namespace: `order/order-types.xsd`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="OrderIdType">
        <xs:restriction base="xs:string">
            <xs:pattern value="ORD-[0-9]{4,}"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="PENDING"/>
            <xs:enumeration value="CONFIRMED"/>
            <xs:enumeration value="CANCELLED"/>
        </xs:restriction>
    </xs:simpleType>
</xs:schema>
~~~

Hai kiểu toàn cục này đều thuộc `urn:example:orders:v1`. `ORD-1234` hợp lệ theo pattern; `1234` không hợp lệ. `OrderStatusType` chỉ có ba giá trị được khai báo.

### 6.2. Tệp namespace tài chính: `finance/money-types.xsd`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:fin="urn:example:finance:v1"
           targetNamespace="urn:example:finance:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="CurrencyCodeType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="VND"/>
            <xs:enumeration value="USD"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:complexType name="MoneyType">
        <xs:sequence>
            <xs:element name="amount" type="xs:decimal"/>
            <xs:element name="currency" type="fin:CurrencyCodeType"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

Prefix `fin` cần được khai báo **ngay trong tệp này** để `type="fin:CurrencyCodeType"` có thể resolve. Mỗi tài liệu XSD là một tài liệu XML độc lập: khai báo prefix ở `orders.xsd` **không được kế thừa** vào `money-types.xsd`. Đây là lỗi dễ mắc khi tách một schema lớn thành nhiều file.

### 6.3. Schema gốc: `orders.xsd`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           xmlns:fin="urn:example:finance:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:include schemaLocation="order/order-types.xsd"/>
    <xs:import namespace="urn:example:finance:v1"
               schemaLocation="finance/money-types.xsd"/>

    <xs:element name="GetOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="ord:OrderIdType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="GetOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="ord:OrderIdType"/>
                <xs:element name="status" type="ord:OrderStatusType"/>
                <xs:element name="total" type="fin:MoneyType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

Đọc phần đầu schema gốc theo thứ tự:

1. `xs:include` đưa `OrderIdType` và `OrderStatusType` thuộc cùng namespace đơn hàng vào tập thành phần schema.
2. `xs:import` cho phép tham chiếu `fin:MoneyType` từ namespace tài chính.
3. `GetOrderRequest` và `GetOrderResponse` là **global elements trong namespace đơn hàng**; các local elements `orderId`, `status` và `total` cũng thuộc namespace đơn hàng nhờ `elementFormDefault="qualified"`.
4. Bên trong phần tử `total`, dữ liệu tuân theo cấu trúc của kiểu `fin:MoneyType`. Hai local elements `amount` và `currency` được định nghĩa ở schema tài chính và thuộc namespace tài chính.

### 6.4. XML response hợp lệ cần dùng hai namespace

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<ord:GetOrderResponse
    xmlns:ord="urn:example:orders:v1"
    xmlns:fin="urn:example:finance:v1">
    <ord:orderId>ORD-1234</ord:orderId>
    <ord:status>CONFIRMED</ord:status>
    <ord:total>
        <fin:amount>125000.00</fin:amount>
        <fin:currency>VND</fin:currency>
    </ord:total>
</ord:GetOrderResponse>
~~~

Trong ví dụ:

- `ord:total` có namespace **đơn hàng**, dù kiểu Java/XML của nó được định nghĩa bởi miền tài chính.
- `fin:amount` và `fin:currency` có namespace **tài chính**, do `MoneyType` định nghĩa các local elements thuộc namespace này.
- Số tiền `125000.00` hợp lệ với `xs:decimal`; `VND` có trong `CurrencyCodeType`.

XML dưới đây trông gần giống nhưng **sai schema** vì hai phần tử con của `total` dùng namespace đơn hàng thay vì tài chính:

~~~xml
<ord:total xmlns:ord="urn:example:orders:v1">
    <ord:amount>125000.00</ord:amount>
    <ord:currency>VND</ord:currency>
</ord:total>
~~~

Việc cùng có tên `amount` không làm hai QName tương đương. Đây là tình huống thực tế mà JAXB, schema validator hoặc client .NET có thể không chấp nhận thông điệp do bên khác tạo ra.

## 7. Luồng phụ thuộc và cách tổ chức namespace

Sơ đồ sau tách hai kiểu quan hệ:

~~~mermaid
flowchart TD
    O["orders.xsd<br/>urn:example:orders:v1"]
    T["order/order-types.xsd<br/>urn:example:orders:v1"]
    F["finance/money-types.xsd<br/>urn:example:finance:v1"]
    W["orders.wsdl<br/>SOAP service contract"]
    O -->|"xs:include — cùng namespace"| T
    O -->|"xs:import — khác namespace"| F
    W -->|"WSDL types tham chiếu schema gốc"| O
~~~

Một số nguyên tắc chia schema:

1. **Chia theo sở hữu dữ liệu và vòng đời thay đổi.** Kiểu đơn hàng nằm ở namespace đơn hàng, kiểu tiền tệ ở namespace tài chính nếu hai miền có hợp đồng riêng.
2. **Không tạo namespace mới chỉ để tách file.** Nếu `order-types.xsd` và `orders.xsd` là cùng một hợp đồng dữ liệu, có thể giữ cùng namespace và dùng include.
3. **Tránh dùng namespace làm tên package tùy tiện.** QName XML là hợp đồng công khai; Java package được sinh qua JAXB binding và có thể cấu hình riêng.
4. **Hạn chế vòng phụ thuộc.** Một chuỗi import nhiều chiều khó triển khai, khó kiểm tra tương thích và dễ sinh cấu trúc type phụ thuộc chéo.
5. **Chọn một điểm vào/schema gốc cho mỗi hợp đồng.** Client nên có khả năng biên dịch các global elements công khai từ một bộ tài liệu được phát hành nhất quán.
6. **Không trộn nhiều phiên bản namespace một cách vô ý.** Việc import `urn:example:finance:v2` khi các client đang dùng v1 là thay đổi hợp đồng, không chỉ là đổi đường dẫn.

### Namespace theo miền và phiên bản

Không có một quy tắc bắt buộc namespace phải chứa `v1`, nhưng việc dùng URI versioned như `urn:example:orders:v1` hoặc `https://example.org/schema/orders/v1` có thể giúp nhận diện thay đổi phá vỡ hợp đồng. Quan trọng nhất là:

- Namespace ổn định trong suốt thời gian hợp đồng còn được hỗ trợ.
- Khi đổi namespace, phải đánh giá lại **mọi QName** liên quan, WSDL, endpoint mapping và JAXB.
- Mọi schema dependency của một bản phát hành phải tương thích với nhau; không nên công bố WSDL v1 nhưng import nhầm XSD v2.

## 8. Chameleon schema: include tài liệu không có targetNamespace

Một ngoại lệ quan trọng của quy tắc include là **chameleon schema**: tệp được include **không khai báo `targetNamespace`**. Khi được include vào schema có namespace, những global components phù hợp từ tệp đó có thể được đưa vào namespace của schema đang include.

Ví dụ một tệp `audit-types.xsd` độc lập:

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           elementFormDefault="qualified">
    <xs:complexType name="AuditInfoType">
        <xs:sequence>
            <xs:element name="createdBy" type="xs:string"/>
            <xs:element name="createdAt" type="xs:dateTime"/>
        </xs:sequence>
    </xs:complexType>
</xs:schema>
~~~

Nếu `orders.xsd` với `targetNamespace="urn:example:orders:v1"` include tài liệu này thì kiểu có thể được tham chiếu thành `ord:AuditInfoType`. Nếu một schema ở namespace `urn:example:customers:v1` include tài liệu tương tự, global type tương ứng sẽ thuộc **namespace khách hàng**.

**Cạm bẫy:** một tệp chameleon không cung cấp “một kiểu toàn cục dùng chung qua nhiều namespace”. Nó tạo các schema components mang danh tính namespace khác nhau theo ngữ cảnh include. Nếu bạn muốn một **hợp đồng dùng chung có QName ổn định** được nhiều domain tham chiếu, hãy tạo **namespace độc lập** cho hợp đồng đó và cho các domain **import** namespace đó.

Chameleon cũng dễ gây nhầm khi có tham chiếu QName nội bộ, local elements có cấu hình `form` khác nhau hoặc khi các công cụ sinh mã xử lý binding theo package. Vì thế, với contract SOAP doanh nghiệp, chỉ dùng khi thật sự hiểu và kiểm thử được hành vi; đa số nhóm sẽ dễ bảo trì hơn khi khai báo `targetNamespace` tường minh.

## 9. `schemaLocation`, base URI và tài nguyên khi đóng gói ứng dụng

`xs:include` và `xs:import` không có nghĩa trình xử lý luôn tìm được dependency.

Với `orders.xsd` ở `src/main/resources/xsd/`:

~~~xml
<xs:include schemaLocation="order/order-types.xsd"/>
<xs:import namespace="urn:example:finance:v1"
           schemaLocation="finance/money-types.xsd"/>
~~~

Các đường dẫn tương đối trên được giải theo **base URI của `orders.xsd`**. Nếu loader chỉ đưa một `InputStream` không có system ID/base URI vào validator, trình xử lý có thể không biết `order/order-types.xsd` nằm ở đâu.

### Những lựa chọn phân giải dependency

| Cách triển khai | Ưu điểm | Điều cần chú ý |
| --- | --- | --- |
| Schema files đặt cùng cấu trúc thư mục và nạp qua `File`/`URL` có base URI | Đơn giản khi làm việc với file thực | Cần đưa đúng cả thư mục lên môi trường chạy |
| Schema files đóng trong JAR và nạp qua classpath | Gói chung với ứng dụng | Không giả định đường dẫn file system tồn tại bên trong JAR |
| **`LSResourceResolver`** của JAXP | Kiểm soát import/include dựa trên namespace và system ID | Cần ánh xạ tài nguyên đáng tin cậy và trả base/system ID hợp lý |
| XML Catalog | Ánh xạ URI/schema location ổn định sang bản local | Cấu hình resolver/toolchain có hỗ trợ catalog phù hợp |
| Hợp đồng WSDL/XSD công bố cùng bộ artifact | Client đối tác tải về và sinh mã dễ hơn | Cần kiểm tra mọi đường dẫn import sau publish, proxy hoặc rewrite URL |

**Không nên phụ thuộc vào URL namespace để tải XSD.** URI như `urn:example:finance:v1` không phải địa chỉ tải file. Nếu một hệ thống yêu cầu import từ URL bên ngoài, cần có chính sách mirror/catalog, giới hạn truy cập và khả năng hoạt động khi mạng không sẵn sàng.

### Ví dụ thẩm định schema root bằng Java

Mẫu dưới đây phù hợp với môi trường phát triển, khi ba tệp XSD nằm trong **thư mục file local tin cậy**. Nó cho thấy vì sao nạp `orders.xsd` với base URI hữu ích; khi chạy trong JAR hoặc cần chính sách bảo mật chặt hơn, thay bằng resolver/catalog được kiểm soát.

~~~java
import java.nio.file.Path;
import javax.xml.XMLConstants;
import javax.xml.transform.stream.StreamSource;
import javax.xml.validation.Schema;
import javax.xml.validation.SchemaFactory;
import javax.xml.validation.Validator;

public final class SchemaCheck {
    public static void validate(Path payloadXml) throws Exception {
        // Thư mục schema của chính ứng dụng, không lấy từ đầu vào client.
        Path schemaRoot = Path.of("src/main/resources/xsd")
                              .toAbsolutePath().normalize();

        SchemaFactory factory = SchemaFactory.newInstance(
                XMLConstants.W3C_XML_SCHEMA_NS_URI);
        factory.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        // Cho phép file local để resolve xs:include/xs:import trong ví dụ.
        factory.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "file");

        Schema schema = factory.newSchema(
                schemaRoot.resolve("orders.xsd").toFile());

        Validator validator = schema.newValidator();
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_DTD, "");
        validator.setProperty(XMLConstants.ACCESS_EXTERNAL_SCHEMA, "");
        validator.validate(new StreamSource(payloadXml.toFile()));
    }
}
~~~

Mẫu này **chưa phải cấu hình production**: `ACCESS_EXTERNAL_SCHEMA="file"` cho phép compiler schema đọc file local theo đường dẫn mà các tệp XSD tham chiếu; nó **không giới hạn** import ở thư mục `schemaRoot`. Chỉ dùng với **toàn bộ schema files do ứng dụng kiểm soát**. Với hợp đồng từ nguồn không tin cậy, phải dùng allowlist/catalog/`LSResourceResolver`, vô hiệu hóa truy cập tài nguyên ngoài không cần thiết, giới hạn kích thước XML và từ chối khi cấu hình bảo mật không được hỗ trợ.

`Schema` sau khi biên dịch thường có thể chia sẻ để tạo validator cho các request; **`Validator` không nên được chia sẻ giữa các thread**. Cần quản lý cache schema, nguồn dữ liệu và giới hạn kích thước payload; kiểm thử riêng trường hợp XML chứa DTD/XXE hoặc cấu trúc sâu bất thường.

## 10. Kết nối bộ XSD đã chia với WSDL và Spring-WS

Trong thiết kế **contract-first**, WSDL thường tham chiếu các global elements của schema gốc. Ví dụ một đoạn WSDL 1.1, được đặt trong `wsdl:definitions` có khai báo prefix tương ứng:

~~~xml
<wsdl:types>
    <xs:schema targetNamespace="urn:example:orders:service:v1">
        <xs:import namespace="urn:example:orders:v1"
                   schemaLocation="xsd/orders.xsd"/>
    </xs:schema>
</wsdl:types>

<wsdl:message name="GetOrderInput">
    <wsdl:part name="parameters" element="ord:GetOrderRequest"/>
</wsdl:message>
<wsdl:message name="GetOrderOutput">
    <wsdl:part name="parameters" element="ord:GetOrderResponse"/>
</wsdl:message>
~~~

Trong ví dụ giả định:

- `wsdl:definitions` đã khai báo `xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"`, `xmlns:xs="http://www.w3.org/2001/XMLSchema"` và `xmlns:ord="urn:example:orders:v1"`.
- WSDL `types` import namespace **đơn hàng**, schema gốc `orders.xsd` tiếp tục include schema kiểu đơn hàng và import schema tài chính.
- `wsdl:part` tham chiếu **global elements** `ord:GetOrderRequest` / `ord:GetOrderResponse`, không trỏ trực tiếp vào `fin:MoneyType`, bởi kiểu tài chính được dùng *bên trong* response.
- WSDL vẫn cần các thành phần **`portType`, `binding`, `service/port`** để trở thành một mô tả dịch vụ có thể gọi; đoạn này chỉ minh họa quan hệ giữa WSDL và XSD.

Không nhầm lẫn **`wsdl:import`** (import một tài liệu WSDL khác) với **`xs:import`** (tham chiếu XML Schema thuộc namespace khác). Cả hai dùng từ “import” nhưng hoạt động ở hai lớp hợp đồng.

### Spring-WS và JAXB sử dụng tập schema này như thế nào?

Một endpoint Spring-WS có thể định tuyến request theo QName root payload:

~~~java
@Endpoint
public class OrderEndpoint {
    private static final String NS = "urn:example:orders:v1";

    @PayloadRoot(namespace = NS, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        // Ánh xạ nghiệp vụ và tạo response JAXB theo contract.
        return process(request);
    }
}
~~~

Đây chỉ là **mã minh họa**: lớp JAXB, phương thức `process`, imports, marshaller và cấu hình Spring-WS cần tồn tại trong ứng dụng thật.

Các lớp JAXB thường được sinh từ XSD root và dependency, hoặc sinh qua công cụ SOAP client từ WSDL. Công cụ phải resolve đúng **cả include và import**. Một số toolchain có thể sinh package Java khác nhau theo namespace; việc xử lý JAXB classes không được làm đổi QName của thông điệp bên ngoài.

Khi công bố WSDL qua Spring-WS, cần lựa chọn rõ giữa **WSDL tĩnh đã rà soát** và **WSDL tạo động từ XSD**. Không mặc định một cấu hình chỉ nạp một XSD riêng lẻ sẽ tự công bố đầy đủ mọi dependency trong tất cả trường hợp. Nếu dùng bộ schema nhiều namespace, hãy kiểm tra bộ WSDL được xuất ra, import URL và khả năng code generation từ một client độc lập.

## 11. Namespace ảnh hưởng tới SOAP Fault, WS-Security và khả năng tương thích

Chia XSD không chỉ tác động tới request/response thành công:

**SOAP Fault detail:** Nếu dịch vụ định nghĩa kiểu lỗi nghiệp vụ trong namespace riêng, WSDL có thể tham chiếu phần tử lỗi từ schema đó. Client cần tải được XSD của fault và nhận dạng đúng QName, nếu không việc xử lý typed fault có thể thất bại.

**Schema validation interceptor:** Khi bật cơ chế kiểm tra payload theo XSD trong Spring-WS (ví dụ `PayloadValidatingInterceptor` được cấu hình phù hợp), phải bảo đảm validator biết đầy đủ các kiểu import/include mà endpoint thực sự sử dụng. Việc thiếu `money-types.xsd` có thể khiến schema compilation không hoàn thành, trước khi xử lý request nghiệp vụ.

**WS-Security:** Chữ ký số có thể bảo vệ SOAP Body. Thay đổi tên phần tử, namespace hoặc cấu trúc XML sau khi ký có thể làm chữ ký không xác minh được. Các bước JAXB marshalling, XML transformation, ký và xác minh phải tuân theo pipeline rõ ràng. **`xs:include`/`xs:import` không thay thế WS-Security**; chúng chỉ tổ chức schema.

**Chứng chỉ:** TLS/mTLS và chứng chỉ dùng để ký thông điệp là phần cấu hình bảo mật/vận hành, không do `schemaLocation` xác định. Không lấy các URI namespace hoặc đường dẫn XSD làm nguồn chứng chỉ.

**Tính tương thích Java–.NET/ESB:** Các bộ sinh mã có thể xử lý chameleon schema, import xuyên namespace, optional fields và enum khác nhau. Bởi vậy, hợp đồng cần được kiểm thử trên công cụ thực tế của đối tác, không chỉ bằng một bộ sinh JAXB trong dự án server.

## 12. Lỗi điển hình và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xác minh |
| --- | --- | --- |
| Include báo “different targetNamespace” | Schema con có target namespace khác schema gốc | So sánh URI `targetNamespace`, chuyển sang import nếu khác |
| Không resolve `fin:MoneyType` | Thiếu `xs:import`, sai URI, prefix hoặc tài nguyên import không nạp | Kiểm tra `xmlns:fin`, `namespace` và schema có định nghĩa global type |
| Báo không tìm được `order-types.xsd` | `schemaLocation` tương đối bị resolve sai base URI | Nạp root bằng URL/File có system ID, kiểm tra cấu trúc artifact |
| “Duplicate global type/element” | Các file cùng namespace khai báo trùng QName | Xác định một nguồn sở hữu cho global component |
| JAXB sinh ra nhiều kiểu có tên giống nhau | Tổ chức namespace/package hoặc sinh mã lặp lại, binding conflict | Kiểm tra QName của XSD và cấu hình code generation |
| SOAP payload có đủ field nhưng validator từ chối | Local element dùng sai namespace hoặc sai thứ tự `xs:sequence` | In QName thực tế và đối chiếu XSD |
| WSDL tải được nhưng client sinh mã lỗi | Các XSD import/include phía WSDL không truy cập được | Tải WSDL và mọi dependency bằng đúng URL client nhìn thấy |
| Sau nâng cấp finance v2, request cũ không map | Thay đổi namespace/QName so với v1 | So sánh contract public, JAXB classes và mapping endpoint |
| Validate được trên máy dev nhưng lỗi trong JAR | Import đường dẫn local file không tồn tại hoặc không có base URI trong JAR | Dùng resolver/catalog/classpath strategy và test packaged artifact |

### Ba ví dụ sai thường gặp

**Sai 1 — Include schema khác namespace:**

~~~xml
<!-- orders.xsd: targetNamespace="urn:example:orders:v1" -->
<xs:include schemaLocation="finance/money-types.xsd"/>
~~~

Tệp tài chính có namespace `urn:example:finance:v1` nên phải **import** với `namespace` thích hợp.

**Sai 2 — Khai báo prefix rồi nghĩ rằng đã import:**

~~~xml
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:fin="urn:example:finance:v1"
           targetNamespace="urn:example:orders:v1">
    <xs:element name="total" type="fin:MoneyType"/>
</xs:schema>
~~~

Chưa có `xs:import` và chưa chắc schema compiler biết `MoneyType`. Prefix chỉ gắn URI với bí danh; nó **không nạp định nghĩa**.

**Sai 3 — Đổi namespace để “sửa” lỗi đường dẫn:**

Nếu import bị lỗi không tìm thấy file, đổi `urn:example:finance:v1` thành `urn:example:finance:v2` chỉ làm thay đổi danh tính QName và tạo rủi ro tương thích. Cần sửa cách resolve `schemaLocation`/resolver thay vì tùy tiện sửa hợp đồng.

## 13. Chiến lược kiểm thử schema đã chia nhỏ

Để một bộ XSD có thể phát hành, nên kiểm tra từ cấu trúc file đến thông điệp SOAP hoàn chỉnh.

| Cấp kiểm thử | Input | Kỳ vọng |
| --- | --- | --- |
| **Biên dịch XSD root** | `orders.xsd` và tất cả include/import | Schema compile thành công, không duplicate/undefined QName |
| **Validate XML instance** | `GetOrderResponse` chứa `ord:total` và `fin:amount` | PASS với schema hợp lệ |
| **Sai namespace** | Đổi `fin:amount` thành `ord:amount` | FAIL validation |
| **Sai dữ liệu** | `orderId=foo` hoặc `status=UNKNOWN` | FAIL theo pattern/enumeration |
| **Sai cấu trúc** | Đảo thứ tự `status` và `total` | FAIL theo `xs:sequence` |
| **Đóng gói JAR** | Tải contract từ artifact build | Resolve được dependency, không phụ thuộc path máy phát triển |
| **WSDL/codegen** | Tải WSDL công bố và sinh Java/.NET client | Resolver thấy đủ schema, QName sinh đúng |
| **Spring-WS endpoint** | SOAP Body chứa `GetOrderRequest` | Mapping QName, JAXB unmarshal và response đúng contract |
| **SOAP Fault/security** | Payload lỗi hoặc chữ ký sai | Fault hoặc từ chối theo chính sách, không lộ thông tin nhạy cảm |
| **Regression** | Client v1 với hợp đồng đã thay đổi | Không đứt tương thích nếu công bố là backward-compatible |

Đặc biệt, cần phân biệt:

1. **XSD valid:** payload thỏa cấu trúc XML Schema.
2. **SOAP valid:** Envelope, Header và version/binding phù hợp.
3. **Service compatible:** WSDL, endpoint, operation và WS-Security khớp kỳ vọng client.
4. **Business correct:** quy tắc nghiệp vụ đúng. Một `OrderStatusType` hợp enum vẫn có thể là trạng thái sai cho đơn hàng cụ thể.

Schema validation thành công **không chứng minh** SOAP Fault, TLS, authorization, WS-Security hoặc xử lý nghiệp vụ đã đúng.

## 14. Thực hành: mở rộng bộ schema

Dựa trên ba tệp ở phần 6, hãy thực hiện các yêu cầu sau:

1. Thêm `order/addresses.xsd` chứa `DeliveryAddressType` thuộc `urn:example:orders:v1`. Quyết định schema gốc dùng `xs:include` hay `xs:import`, và giải thích.
2. Tạo `customer/customer-types.xsd` có namespace `urn:example:customers:v1`, định nghĩa `CustomerIdType`. Thêm `customerId` vào `GetOrderResponse` và chỉ ra import/namespace đúng.
3. Viết XML response có `ord:total` nhưng cố tình đặt `amount` và `currency` ở namespace sai. Dự đoán và xác minh kết quả XSD validation.
4. Thử nạp `orders.xsd` bằng một `InputStream` không có system ID rồi quan sát khả năng resolve include/import; so sánh với cách nạp bằng URL có base URI.
5. Đổi namespace tài chính từ v1 sang v2 nhưng không cập nhật `xs:import` và các QName. Liệt kê các lỗi bạn kỳ vọng ở schema compiler, JAXB, WSDL hoặc client.
6. Tạo một tệp `shared-types.xsd` **không có `targetNamespace`**, include nó vào hai root schemas khác namespace và so sánh QName của global type sau khi biên dịch. Giải thích vì sao nó không phải một shared type có QName chung.
7. Kiểm thử WSDL tham chiếu `orders.xsd` và yêu cầu một SOAP client độc lập sinh mã từ WSDL, bao gồm cả `MoneyType` và các kiểu đơn hàng.

## 15. Nguyên tắc mang vào dự án thực tế

- **Dùng `xs:include`** khi phân chia tài liệu bên trong cùng một namespace và **`xs:import`** khi tham chiếu namespace khác.
- **Thiết kế namespace trước khi chia file.** Namespace phản ánh danh tính contract, còn folder phản ánh cách lưu trữ và phát hành.
- **Đảm bảo bộ contract tự chứa và phân giải được.** Phát hành WSDL/XSD cùng toàn bộ dependency, kiểm tra import URL với client ngoài hệ thống.
- **Giữ kiểu dùng chung ổn định.** Thay đổi global type, enum, QName hoặc SOAP payload có thể ảnh hưởng đến JAXB, endpoint mapping, Fault và đối tác.
- **Kiểm thử schema theo XML thực tế**, bao gồm namespace, thứ tự phần tử, dữ liệu không hợp lệ và sự khác nhau giữa môi trường phát triển và artifact đã đóng gói.
- **Giữ ranh giới trách nhiệm:** XSD mô tả dữ liệu; WSDL mô tả giao diện dịch vụ; JAXB ánh xạ Java/XML; Spring-WS thực thi SOAP; WS-Security và chứng chỉ bảo vệ giao tiếp theo chính sách.

**Kết luận:** `xs:include` và `xs:import` là hai cơ chế bổ sung nhau để tạo một bộ XSD có cấu trúc: include **gom các tệp trong cùng namespace**, import **kết nối các namespace khác nhau**. Thiết kế đúng hai quan hệ này giúp hợp đồng SOAP contract-first dễ tái sử dụng, sinh mã được, kiểm thử được và có khả năng tương thích dài hạn khi tích hợp hệ thống doanh nghiệp.
