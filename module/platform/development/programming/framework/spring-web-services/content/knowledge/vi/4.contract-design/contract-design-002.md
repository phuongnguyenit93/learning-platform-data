# Thiết kế thông điệp yêu cầu, phản hồi trước khi viết endpoint

Trong **Spring Web Services (Spring-WS)**, một endpoint Java chỉ là một cách triển khai hợp đồng dịch vụ. Với hướng **contract-first**, nhóm tích hợp cần thống nhất **thông điệp yêu cầu (request)**, **thông điệp phản hồi (response)**, ý nghĩa các trường, quy tắc lỗi và khả năng tương thích **trước khi** viết phương thức gắn `@Endpoint` hoặc sinh lớp JAXB. Nếu bắt đầu bằng chữ ký phương thức Java rồi “đẩy” kiểu dữ liệu ra XML, hợp đồng dễ mang các chi tiết nội bộ, khó ổn định khi tích hợp nhiều hệ thống.

Bài này thuộc phần **Thiết kế hợp đồng** của module `SPRING_WEB_SERVICES`: tập trung vào cách ra quyết định và hiện thực XSD/WSDL cho một thao tác SOAP. Các chủ đề liên quan như JAXB, SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích sẽ được gắn vào đúng điểm mà thiết kế thông điệp ảnh hưởng đến chúng.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân tích yêu cầu nghiệp vụ thành một cặp thông điệp request/response có ý nghĩa rõ ràng cho cả client lẫn server.
- Thiết kế phần tử gốc, QName, namespace, thứ tự trường, kiểu XSD, cardinality và quy tắc `minOccurs`/`nillable`.
- Tách dữ liệu nghiệp vụ khỏi metadata giao tiếp và bảo mật; định nghĩa phản hồi thành công và tình huống phải tạo SOAP Fault.
- Viết XSD có thể dùng để công bố WSDL, sinh mã JAXB và định tuyến endpoint Spring-WS theo payload root.
- Lập ví dụ XML, bảng trường, quy tắc tương thích và kịch bản kiểm thử **trước khi có endpoint**.

## 1. Bắt đầu từ trao đổi nghiệp vụ, không bắt đầu từ Java

Xét một hệ thống mua hàng (client) gửi đơn đến hệ thống xử lý đơn hàng (server). Hai bên cần thao tác `SubmitOrder`. Yêu cầu nghiệp vụ giả định:

1. Client gửi **mã yêu cầu riêng** (`requestId`) để server nhận biết lần gửi lại khi mất kết nối.
2. Client cung cấp `buyerId`, danh sách mặt hàng, mỗi dòng có `sku` và `quantity`.
3. Client có thể gửi ngày giao mong muốn (`requestedDeliveryDate`) và ghi chú (`clientComment`).
4. Server tự sinh `orderId`, xác định trạng thái tiếp nhận và thời điểm nhận; client không được tự đặt `orderId`.
5. Server trả phản hồi khi **đã tiếp nhận**, không có nghĩa hàng đã giao hoặc thanh toán thành công.
6. Nếu dữ liệu không hợp lệ, người mua không có quyền, hoặc hệ thống gặp lỗi, client cần nhận lỗi có ý nghĩa và biết có nên thử lại hay không.
7. Các trường đã công bố cần ổn định đối với client Java, .NET hoặc các nền tảng SOAP khác.

Trước khi viết code, hãy quyết định **đâu là một thao tác, dữ liệu nào do ai sở hữu, lúc nào thao tác được coi là hoàn tất**.

| Câu hỏi thiết kế | Quyết định cho ví dụ | Tác động lên hợp đồng |
| --- | --- | --- |
| Tên thao tác là gì? | `SubmitOrder` | Hai phần tử gốc `SubmitOrderRequest`, `SubmitOrderResponse` |
| Dữ liệu nào client chịu trách nhiệm? | `requestId`, `buyerId`, danh sách hàng | Trường bắt buộc ở request |
| Dữ liệu nào server chịu trách nhiệm? | `orderId`, `status`, `acceptedAt` | Trường ở response |
| Bao nhiêu dòng hàng? | Ít nhất một | XSD quy định `item` lặp, `minOccurs=1` |
| Quantity hợp lệ? | Từ 1 đến 999 mỗi dòng | Kiểu hạn chế `xs:positiveInteger` và `maxInclusive` |
| Ngày giao có bắt buộc không? | Không | `minOccurs=0` |
| Server trả gì khi tiếp nhận? | Mã đơn và trạng thái | Response rõ nghĩa, không trả boolean `success` |
| Khi yêu cầu bị lỗi? | SOAP Fault kèm mã lỗi hợp đồng khi thích hợp | Chính sách fault tách khỏi response thành công |

Một quyết định quan trọng: **giá sản phẩm không nằm trong request** của ví dụ này vì server có trách nhiệm xác định giá tại thời điểm xử lý. Nếu nghiệp vụ yêu cầu giá đã được báo trước, cần bổ sung thiết kế về báo giá, tiền tệ, độ chính xác số thập phân và cơ chế xác nhận giá; không nên tùy tiện thêm `double price` vào payload.

## 2. Phác thảo request/response ở mức XML trước

Ta chọn namespace hợp đồng `urn:example:procurement:orders:v1`, ký hiệu trong các ví dụ là `ord`.

### 2.1. Request dự kiến

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:procurement:orders:v1">
  <ord:requestId>REQ-2026-0001</ord:requestId>
  <ord:buyerId>BUYER-15</ord:buyerId>
  <ord:items>
    <ord:item>
      <ord:sku>SKU-001</ord:sku>
      <ord:quantity>2</ord:quantity>
    </ord:item>
    <ord:item>
      <ord:sku>SKU-009</ord:sku>
      <ord:quantity>1</ord:quantity>
    </ord:item>
  </ord:items>
  <ord:requestedDeliveryDate>2026-12-05</ord:requestedDeliveryDate>
  <ord:clientComment>Giao trong gio hanh chinh</ord:clientComment>
</ord:SubmitOrderRequest>
~~~

### 2.2. Response dự kiến

~~~xml
<ord:SubmitOrderResponse xmlns:ord="urn:example:procurement:orders:v1">
  <ord:requestId>REQ-2026-0001</ord:requestId>
  <ord:orderId>ORD-8742</ord:orderId>
  <ord:status>ACCEPTED</ord:status>
  <ord:acceptedAt>2026-11-27T02:00:00Z</ord:acceptedAt>
  <ord:estimatedDeliveryDate>2026-12-05</ord:estimatedDeliveryDate>
</ord:SubmitOrderResponse>
~~~

Ở ví dụ này, `ACCEPTED` nghĩa là yêu cầu đã tạo bản ghi tiếp nhận; `PENDING_REVIEW` (sẽ được định nghĩa trong XSD) nghĩa là yêu cầu đã được ghi nhận nhưng cần xét duyệt. Cả hai đều không hứa việc giao hàng đã hoàn tất. `estimatedDeliveryDate` là ước tính của server, có thể vắng mặt. `requestedDeliveryDate` là **mong muốn** của client, không phải cam kết của server.

Hai XML trên là **payload bên trong SOAP Body**. Ở tầng truyền tin, Spring-WS sẽ đặt chúng trong SOAP Envelope. XSD quy định cấu trúc payload; WSDL quy định thao tác và binding. Một SOAP request không phải đính kèm tệp XSD/WSDL trong mỗi lần gọi.

### 2.3. Chốt danh sách trường bằng bảng hợp đồng

| Thông điệp | Trường | Kiểu logic | Bắt buộc? | Ai quyết định? |
| --- | --- | --- | --- | --- |
| Request | `requestId` | Mã 8–64 ký tự theo mẫu | Có | Client |
| Request | `buyerId` | Mã tối đa 64 ký tự | Có | Client |
| Request | `items.item` | Danh sách từ 1 phần tử | Có | Client |
| Request | `item.sku` | Mã hàng | Có | Client |
| Request | `item.quantity` | Số nguyên từ 1 đến 999 | Có | Client |
| Request | `requestedDeliveryDate` | `xs:date` | Không | Client |
| Request | `clientComment` | Chuỗi tối đa 500 ký tự | Không | Client |
| Response | `requestId` | Mã request được liên hệ | Có | Server phản hồi mã đã nhận |
| Response | `orderId` | Mã đơn do server cấp | Có | Server |
| Response | `status` | `ACCEPTED` hoặc `PENDING_REVIEW` | Có | Server |
| Response | `acceptedAt` | `xs:dateTime` | Có | Server |
| Response | `estimatedDeliveryDate` | `xs:date` | Không | Server |

Ngoài kiểu dữ liệu, cần ghi rõ **ngữ nghĩa**: mã có phân biệt chữ hoa/thường không, `buyerId` thuộc miền định danh nào, thời gian lưu `requestId`, thế nào là một lần gửi trùng, trạng thái nào có thể chuyển sang trạng thái nào, và client nên xử lý kết quả như thế nào. XSD không thể diễn tả hết các quy tắc nghiệp vụ đó.

## 3. Hiện thực hợp đồng bằng XSD

Sau khi hai bên chốt bản phác thảo, tạo `orders.xsd` (ví dụ UTF-8):

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:procurement:orders:v1"
    targetNamespace="urn:example:procurement:orders:v1"
    elementFormDefault="qualified">

  <!-- Các mã được truyền qua biên hệ thống. -->
  <xs:simpleType name="CodeType">
    <xs:restriction base="xs:string">
      <xs:minLength value="1"/>
      <xs:maxLength value="64"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="RequestIdType">
    <xs:restriction base="xs:string">
      <xs:minLength value="8"/>
      <xs:maxLength value="64"/>
      <xs:pattern value="[A-Za-z0-9._-]+"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="QuantityType">
    <xs:restriction base="xs:positiveInteger">
      <xs:maxInclusive value="999"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:simpleType name="CommentType">
    <xs:restriction base="xs:string">
      <xs:maxLength value="500"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:complexType name="OrderItemType">
    <xs:sequence>
      <xs:element name="sku" type="ord:CodeType"/>
      <xs:element name="quantity" type="ord:QuantityType"/>
    </xs:sequence>
  </xs:complexType>

  <xs:complexType name="OrderItemsType">
    <xs:sequence>
      <xs:element name="item" type="ord:OrderItemType"
                  minOccurs="1" maxOccurs="unbounded"/>
    </xs:sequence>
  </xs:complexType>

  <xs:simpleType name="AcceptanceStatusType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="ACCEPTED"/>
      <xs:enumeration value="PENDING_REVIEW"/>
    </xs:restriction>
  </xs:simpleType>

  <!-- Phần tử gốc của request. -->
  <xs:element name="SubmitOrderRequest">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="ord:RequestIdType"/>
        <xs:element name="buyerId" type="ord:CodeType"/>
        <xs:element name="items" type="ord:OrderItemsType"/>
        <xs:element name="requestedDeliveryDate"
                    type="xs:date" minOccurs="0"/>
        <xs:element name="clientComment"
                    type="ord:CommentType" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

  <!-- Phần tử gốc của response. -->
  <xs:element name="SubmitOrderResponse">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="requestId" type="ord:RequestIdType"/>
        <xs:element name="orderId" type="ord:CodeType"/>
        <xs:element name="status" type="ord:AcceptanceStatusType"/>
        <xs:element name="acceptedAt" type="xs:dateTime"/>
        <xs:element name="estimatedDeliveryDate"
                    type="xs:date" minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>

</xs:schema>
~~~

Đây là XSD 1.0 minh họa: có hai **global elements** tương ứng hai thông điệp root. Những `complexType` dùng lại được cho nhiều thao tác khác trong cùng namespace nếu cần. Việc để request/response root có `complexType` ẩn danh trong ví dụ giúp mã JAXB sinh ra thường ánh xạ trực tiếp theo phần tử gốc; kết quả chính xác phụ thuộc công cụ sinh JAXB.

### 3.1. Đọc đúng từng quyết định XSD

**Một QName gồm namespace URI và local name.** `{urn:example:procurement:orders:v1}SubmitOrderRequest` khác `{urn:example:procurement:orders:v2}SubmitOrderRequest`, cho dù cả hai có cùng local name. Tiền tố `ord` chỉ là cách viết trong tài liệu.

**`elementFormDefault="qualified"`** yêu cầu các phần tử con được khai báo cục bộ trong ví dụ mang namespace hợp đồng. Nếu phía gửi bỏ namespace của `quantity`, tài liệu không còn phù hợp với XSD, dù mắt thường vẫn thấy thẻ tên `quantity`.

**`xs:sequence` quy định thứ tự.** `requestId` phải đi trước `buyerId`; `items` phải đi trước `requestedDeliveryDate`. SOAP client tự xây XML bằng string dễ sai thứ tự này. Client sinh từ XSD/JAXB giúp giảm lỗi nhưng vẫn phải kiểm thử XML phát ra.

**`minOccurs` là tần suất xuất hiện.** Mặc định `minOccurs=1`, `maxOccurs=1`; `minOccurs=0` nghĩa là phần tử có thể vắng mặt; `maxOccurs="unbounded"` cho phép lặp không giới hạn theo XSD. Ở đây `items` bắt buộc và mỗi `items` phải có ít nhất một `item`. Trong hệ thống thực, nên thỏa thuận giới hạn tổng số dòng và kích thước thông điệp ngoài XSD để tránh request quá lớn.

**Kiểu XSD xác định miền giá trị XML.** `QuantityType` yêu cầu số nguyên dương tối đa 999; `AcceptanceStatusType` chỉ cho hai giá trị xác định. `CodeType` hạn chế độ dài nhưng **không tự bảo đảm mã tồn tại trong cơ sở dữ liệu**; một chuỗi toàn khoảng trắng vẫn có thể qua `minLength`. Nếu không được phép, thêm ràng buộc XSD thích hợp và kiểm tra nghiệp vụ.

### 3.2. Vắng mặt, rỗng và `xsi:nil` khác nhau

Một trường tùy chọn:

~~~xml
<!-- Hợp lệ: clientComment bị lược bỏ. -->
<ord:items xmlns:ord="urn:example:procurement:orders:v1">...</ord:items>

<!-- Hợp lệ với CommentType: phần tử có mặt, chuỗi rỗng. -->
<ord:clientComment xmlns:ord="urn:example:procurement:orders:v1"></ord:clientComment>
~~~

Hai đoạn trên chỉ minh họa ý nghĩa **vắng mặt** và **rỗng**; chúng chưa tạo thành request hoàn chỉnh. Trong XSD hiện tại, `clientComment` có `minOccurs="0"` nhưng `nillable` mặc định là `false`, vì vậy:

~~~xml
<!-- KHÔNG hợp lệ theo XSD này: thiếu nillable="true". -->
<ord:clientComment
    xmlns:ord="urn:example:procurement:orders:v1"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:nil="true"/>
~~~

là không hợp lệ. Nếu hệ thống thực sự cần phân biệt “không gửi”, “gửi rỗng” và “chủ động đặt null”, hãy định nghĩa semantics cùng `minOccurs`/`nillable` ngay từ đầu. Với thông điệp nhiều đối tác, tùy chọn **bỏ hẳn phần tử** thường đơn giản hơn khi không cần ba trạng thái.

### 3.3. Quy tắc thời gian

`xs:date` có dạng như `2026-12-05`, còn `xs:dateTime` có dạng như `2026-11-27T02:00:00Z`. Với `acceptedAt`, hợp đồng nên nói rõ server luôn trả UTC, hoặc bắt buộc có offset thời gian trong quy ước triển khai. **Chỉ dùng `xs:dateTime` trong XSD 1.0 chưa bắt buộc mọi giá trị có timezone.** Các hệ thống khác múi giờ sẽ khó xác định cùng một thời điểm nếu không có quy ước bổ sung.

## 4. Thiết kế ý nghĩa thông điệp để tránh lỗi tích hợp

### 4.1. Request là một lệnh nghiệp vụ, response là kết quả có nghĩa

Request `SubmitOrderRequest` phải nói được client đang yêu cầu gì. Response `SubmitOrderResponse` cần cho client thông tin **đủ để xử lý tiếp**: yêu cầu nào, đơn hàng nào được tạo, được tiếp nhận ở trạng thái nào và lúc nào.

Không trả chỉ:

~~~xml
<success>true</success>
~~~

vì client không biết mã đơn vừa tạo, không thể đối chiếu khi timeout hoặc điều tra lỗi. Cũng không nên đưa tất cả kết quả vào một chuỗi tự do kiểu `resultText` rồi bắt client phân tích tiếng Việt/tiếng Anh. Các mã máy đọc được nên là kiểu XSD/enumeration đã thống nhất; thông điệp diễn giải chỉ phục vụ người vận hành.

### 4.2. Định nghĩa hành vi gửi trùng trước khi triển khai

Vì `SubmitOrder` có tác dụng phụ, lỗi mạng dễ dẫn đến tình huống **server đã nhận đơn nhưng client không nhận được response**. Nếu client gửi lại vô điều kiện, hệ thống có thể tạo hai đơn cho cùng một yêu cầu.

Quy tắc tích hợp đề xuất cho `requestId`:

- Định danh một ý định tạo đơn trong phạm vi một buyer, ví dụ khóa duy nhất `(buyerId, requestId)`.
- Nếu cùng khóa và **cùng dữ liệu nghiệp vụ** được gửi lại trong thời hạn lưu, server trả lại cùng kết quả tiếp nhận (`orderId`, trạng thái và `acceptedAt` phù hợp với giao ước), không tạo đơn mới.
- Nếu cùng khóa nhưng **payload khác**, từ chối như một xung đột gửi trùng; không âm thầm cập nhật đơn cũ.
- Hai bên phải thống nhất thời hạn lưu khóa chống trùng, phạm vi định danh, cách so payload và chính sách retry.

Đây là **quy tắc nghiệp vụ/triển khai**, XSD không tự tạo cơ chế idempotency. Nếu áp dụng thao tác khác, như `GetOrderStatus` chỉ đọc, hợp đồng sẽ có đặc điểm idempotency khác.

### 4.3. Tách metadata khỏi payload

Trong SOAP, cùng một trường có thể được đặt sai chỗ nếu không xác định trách nhiệm:

| Dữ liệu | Vị trí nên cân nhắc | Lý do |
| --- | --- | --- |
| `buyerId`, `items`, `requestId` | SOAP Body theo XSD nghiệp vụ | Là nội dung, định danh và ngữ nghĩa của lệnh `SubmitOrder` |
| Correlation ID kỹ thuật | SOAP Header hoặc cơ chế tracing theo chính sách | Liên kết log giữa các dịch vụ |
| Token xác thực, chữ ký, timestamp WS-Security | SOAP Header theo WS-Security | Là cơ chế bảo vệ thông điệp |
| Địa chỉ đích, endpoint URL | Cấu hình client / WSDL / hạ tầng | Không phải trường nghiệp vụ |
| Mã lỗi khi thất bại | SOAP Fault, có thể thêm structured detail | Theo semantics lỗi SOAP |

Không cho client tự khai báo `acceptedAt`, quyền truy cập hoặc kết quả xác minh chữ ký trong Body rồi coi đó là dữ liệu tin cậy. WS-Security, chứng chỉ và TLS cần cấu hình/chính sách được xác minh độc lập với XSD nghiệp vụ.

## 5. Quyết định lỗi trước khi viết endpoint

Một bản hợp đồng chỉ có happy path là chưa hoàn chỉnh. Trong SOAP, **SOAP Fault** là cơ chế thông báo lỗi ở cấp giao thức; response nghiệp vụ thành công không nên bị dùng như một túi lỗi tùy tiện.

Bảng quy tắc minh họa:

| Tình huống | Lỗi được phát hiện ở đâu | Biểu diễn đề xuất |
| --- | --- | --- |
| Request thiếu `buyerId`, quantity bằng 0, sai thứ tự phần tử | XSD validation | SOAP Fault do request không hợp lệ |
| `buyerId` đúng kiểu nhưng không tồn tại | Xử lý nghiệp vụ | SOAP Fault với mã nghiệp vụ có cấu trúc |
| Buyer không được phép tạo đơn | Authentication/authorization | Từ chối theo chính sách bảo mật, không lộ thông tin nhạy cảm |
| Cùng `requestId`, payload khác | Kiểm tra idempotency | SOAP Fault với mã xung đột |
| Server chưa xử lý được do phụ thuộc tạm ngưng | Hạ tầng/nghiệp vụ | SOAP Fault phía server, retry theo chính sách |
| Đơn đã nhận nhưng cần xét duyệt | Kết quả nghiệp vụ hợp lệ | Response thành công với `PENDING_REVIEW` |

Với SOAP 1.1, `Client` thường được dùng cho lỗi request và `Server` cho lỗi xử lý; SOAP 1.2 dùng khái niệm `Sender`/`Receiver` và XML Fault khác. Lỗi nghiệp vụ có thể cần `detail` theo schema riêng, chẳng hạn mã `UNKNOWN_BUYER`, `INVALID_ITEM`, `DUPLICATE_REQUEST_ID`. Tuy nhiên, **muốn công bố WSDL fault tường minh thì phải thiết kế các khai báo message/fault và binding tương ứng**; không mặc định `DefaultWsdl11Definition` sẽ tự biểu diễn mọi exception Java thành WSDL fault.

Ví dụ SOAP 1.1 Fault minh họa phần payload:

~~~xml
<soap:Fault xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <faultcode>soap:Client</faultcode>
  <faultstring>Order request conflicts with an existing requestId</faultstring>
  <detail>
    <ord:OrderFault xmlns:ord="urn:example:procurement:orders:v1">
      <ord:code>DUPLICATE_REQUEST_ID</ord:code>
      <ord:requestId>REQ-2026-0001</ord:requestId>
    </ord:OrderFault>
  </detail>
</soap:Fault>
~~~

`OrderFault` trong đoạn trên là **đề xuất hợp đồng lỗi bổ sung**, chưa được khai báo trong `orders.xsd` mẫu ở mục 3. Nếu sử dụng trong hệ thống thật, cần khai báo schema của fault detail, WSDL fault nếu đối tác yêu cầu, và ánh xạ exception/fault resolver để response thực tế đúng hợp đồng. `faultstring` chỉ là thông điệp diễn giải: client nên phân nhánh dựa trên mã lỗi ổn định, không so khớp câu chữ.

## 6. Từ XSD request/response đến WSDL và endpoint Spring-WS

### 6.1. XSD và WSDL giải quyết những câu hỏi khác nhau

- **XSD**: `SubmitOrderRequest`/`SubmitOrderResponse` gồm những phần tử gì, kiểu nào, namespace nào, có thể thiếu/lặp không?
- **WSDL 1.1**: thao tác `SubmitOrder` có thông điệp đầu vào/đầu ra nào, SOAP binding ra sao, client gửi đến địa chỉ nào?
- **JAXB**: ánh xạ phần tử XSD thành lớp/đối tượng Java tương ứng.
- **Spring-WS endpoint**: nhận payload root theo QName, unmarshal rồi gọi nghiệp vụ.
- **SOAP client**: tạo XML đúng hợp đồng, đóng thành SOAP message và đọc response/fault.

WSDL 1.1 thường có `types` tham chiếu XSD, `message`, `portType`, `binding` và `service`. Một mô tả logic tương đương:

~~~text
Service: OrdersService
Port/Binding: OrdersPort (SOAP 1.1, document/literal)
Operation: SubmitOrder
  Input:  {urn:example:procurement:orders:v1}SubmitOrderRequest
  Output: {urn:example:procurement:orders:v1}SubmitOrderResponse
Endpoint URI (môi trường local): http://localhost:8080/ws
~~~

Đây là mô tả khái niệm, **không phải file WSDL XML hoàn chỉnh**. Dịch vụ triển khai cần công bố WSDL thực tế và kiểm tra chính xác QName, binding, operation, địa chỉ và chính sách bảo mật. Với SOAP 1.1 document/literal, mỗi Body thường mang một phần tử gốc theo thông điệp đã thiết kế.

### 6.2. Cấu hình WSDL từ XSD

Spring-WS hỗ trợ `DefaultWsdl11Definition`; ví dụ cấu hình minh họa (giả định `MessageDispatcherServlet` được ánh xạ tới `/ws/*`, và `orders.xsd` có trên classpath):

~~~java
@Configuration
@EnableWs
public class OrdersWsdlConfiguration {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("orders.xsd"));
    }

    @Bean(name = "orders")
    public DefaultWsdl11Definition ordersWsdl(XsdSchema ordersSchema) {
        DefaultWsdl11Definition wsdl = new DefaultWsdl11Definition();
        wsdl.setPortTypeName("OrdersPort");
        wsdl.setLocationUri("/ws");
        wsdl.setTargetNamespace(
                "urn:example:procurement:orders:v1");
        wsdl.setSchema(ordersSchema);
        return wsdl;
    }
}
~~~

Với cách sinh WSDL theo hậu tố `Request`/`Response`, hai global elements `SubmitOrderRequest` và `SubmitOrderResponse` có thể được ghép thành operation `SubmitOrder`. Kiểm tra file WSDL được công bố, thông thường qua `/ws/orders.wsdl` với đường dẫn servlet phù hợp, thay vì giả định operation và địa chỉ luôn giống ý định thiết kế. Với hợp đồng WSDL đã ký với đối tác, công bố WSDL cố định có thể phù hợp hơn việc tái sinh WSDL khi chạy.

Lưu ý: phần `MessageDispatcherServlet`/Spring Boot autoconfiguration, dependency starter, version JAXB và cấu hình servlet phải được hoàn thiện trong ứng dụng thật; đoạn trên cố ý tập trung vào **mối nối giữa XSD và WSDL**.

### 6.3. Chỉ sau khi ổn định hợp đồng mới viết endpoint

Giả sử đã sinh kiểu Java từ XSD bằng JAXB trong package `com.example.orders.schema`; Spring-WS có thể định tuyến bằng payload root:

~~~java
@Endpoint
public class SubmitOrderEndpoint {

    private static final String NS =
            "urn:example:procurement:orders:v1";

    private final SubmitOrderApplicationService service;
    private final SubmitOrderResponseMapper responseMapper;

    public SubmitOrderEndpoint(
            SubmitOrderApplicationService service,
            SubmitOrderResponseMapper responseMapper) {
        this.service = service;
        this.responseMapper = responseMapper;
    }

    @PayloadRoot(namespace = NS, localPart = "SubmitOrderRequest")
    @ResponsePayload
    public SubmitOrderResponse submit(
            @RequestPayload SubmitOrderRequest request) {
        // Business service kiểm tra buyer, SKU và idempotency.
        SubmissionResult result = service.submit(request);
        return responseMapper.from(result);
    }
}
~~~

Các kiểu `SubmitOrderApplicationService`, `SubmissionResult` và `SubmitOrderResponseMapper` là abstraction minh họa, do ứng dụng tự hiện thực. Chữ ký JAXB chính xác phụ thuộc mã được sinh: đôi khi cần `JAXBElement`/factory thay vì đối tượng root trực tiếp. Cấu hình marshaller/unmarshaller và endpoint adapter phải phù hợp với Spring-WS/JAXB đang dùng; các bản Spring Boot 3+/Spring Framework 6+ dùng JAXB Jakarta (`jakarta.xml.bind`) thay cho hệ `javax.xml.bind` cũ.

**Điểm mấu chốt:** QName trong `@PayloadRoot` xuất phát từ hợp đồng XSD đã thiết kế, không phải tên class Java. Đổi namespace hoặc tên phần tử gốc ở XSD sẽ ảnh hưởng mapping endpoint và client, dù code nghiệp vụ không đổi.

### 6.4. Máy khách phải tạo XML khớp hợp đồng

Một SOAP client có thể dùng `WebServiceTemplate` và `Jaxb2Marshaller`:

~~~java
// Giả định template đã cấu hình URI, JAXB marshaller,
// unmarshaller và chính sách timeout / bảo mật.
SubmitOrderRequest request = new SubmitOrderRequest();
request.setRequestId("REQ-2026-0001");
request.setBuyerId("BUYER-15");

// Bộ sưu tập item do JAXB sinh có thể có live list.
// Các mục item, quantity, ngày và ghi chú cần điền theo schema.

SubmitOrderResponse response =
    (SubmitOrderResponse) template.marshalSendAndReceive(request);
~~~

Đoạn mã cho thấy cách sử dụng, **chưa phải chương trình hoàn chỉnh có thể chạy ngay**. Các kiểu XJC có thể khác nhau về getter, `JAXBElement`, ánh xạ `xs:date` và `xs:dateTime`; nên sinh client từ XSD/WSDL thực tế và kiểm tra SOAP đã marshal. Khi client nhận SOAP Fault, `WebServiceTemplate` có luồng xử lý fault riêng; không ép fault thành `SubmitOrderResponse`.

## 7. Thiết kế để tương thích giữa các phiên bản và nền tảng

Thiết kế hợp đồng cho tích hợp doanh nghiệp phải cân nhắc tương thích **ngay khi chọn tên, namespace và optionality**.

| Thay đổi hợp đồng | Rủi ro | Hướng xử lý |
| --- | --- | --- |
| Đổi local name `SubmitOrderRequest` | Endpoint cũ không chọn đúng payload | Tạo operation/version mới hoặc migration có kiểm soát |
| Đổi namespace `...:v1` sang `...:v2` | Toàn bộ QName thay đổi | Version rõ ràng, client và mapping cập nhật đồng bộ |
| Thêm trường request bắt buộc | Client cũ không gửi đủ trường | Tránh trong cùng contract version |
| Thêm trường request `minOccurs=0` | Server mới phải chấp nhận vắng mặt; server cũ có thể từ chối trường lạ | Kiểm thử hai chiều và quy tắc xử lý |
| Thêm trường response tùy chọn | Client cũ có thể schema-validate nghiêm ngặt rồi từ chối XML mới | Test với các client phát sinh từ WSDL cũ |
| Đổi enum status | Client cũ có thể không hiểu giá trị mới | Đánh giá versioning/chiến lược enum extensibility |
| Đổi thứ tự trong `xs:sequence` | XML cũ không còn phù hợp XSD mới | Tránh nếu không có kế hoạch chuyển đổi |
| Đổi SOAP 1.1 ↔ SOAP 1.2 | Namespace Envelope, content type, fault khác | Công bố binding mới và kiểm thử toàn bộ |
| Đổi `xs:integer` sang `xs:string` | Kiểu sinh JAXB/khả năng validation thay đổi | Đánh giá migration, thường cần version mới |

Không có quy tắc chung rằng “thêm trường optional luôn tương thích”: **client dùng schema cố định có thể từ chối ngay trường mới**. Phải kiểm thử cả `client cũ → server mới` và `client mới → server cũ` theo phiên bản chính thức đang hỗ trợ.

Một số quy ước nên chốt trước:

- Tên namespace và quy tắc versioning; prefix XML có thể thay đổi nhưng URI là một phần QName.
- Quy ước mã lỗi và giá trị trạng thái, tính mở rộng của các enum.
- Múi giờ/độ chính xác thời gian, tiền tệ và số thập phân nếu nghiệp vụ sử dụng.
- Độ dài tối đa của chuỗi, danh sách, tệp đính kèm và kích thước SOAP message.
- Quy tắc xử lý unknown fields, duplicate requests, timeout, retry, logging và dữ liệu nhạy cảm.

## 8. Thiết kế thông điệp liên quan thế nào đến bảo mật?

Trong Spring-WS, XSD/WSDL và endpoint mới chỉ là một phần của tích hợp. Khi chốt contract, cần viết riêng **giao ước bảo mật**:

1. Client/server dùng HTTPS/TLS như thế nào; có yêu cầu mTLS không; CA và quy trình thay chứng chỉ ra sao.
2. Có dùng WS-Security cho chữ ký XML, timestamp, token hoặc mã hóa SOAP không; thuật toán và phần tử cần bảo vệ được định nghĩa ở đâu.
3. Trường `buyerId` là tham số nghiệp vụ, **không tự chứng minh danh tính của người gọi**. Danh tính và quyền tạo đơn phải lấy từ cơ chế xác thực/ủy quyền đáng tin cậy rồi so với `buyerId`.
4. Server kiểm tra XML an toàn: chặn XXE theo parser/provider, giới hạn kích thước/depth, xác thực XSD, tránh XPath injection và xử lý chữ ký đúng phần tử thực sự được dùng trong nghiệp vụ.
5. Log requestId, correlation ID và mã lỗi để truy vết; tránh ghi token, private key, dữ liệu nhạy cảm hoặc toàn bộ SOAP payload khi không cần.

**WS-Security không thể được thực hiện chỉ bằng việc thêm một trường `signature` vào request XSD.** Việc xác minh chữ ký/timestamp thuộc thư viện và interceptor chuyên trách như tích hợp WSS4J; tài liệu chính sách, WSDL/WS-Policy nếu sử dụng và test với đối tác phải thống nhất.

## 9. Kiểm thử hợp đồng trước khi viết logic endpoint

Nên tạo **fixtures XML** đúng/sai và chạy XSD validation, review XML với bên tích hợp, kiểm tra WSDL dự kiến, và thử sinh client bằng công cụ của các nền tảng dự kiến. Có thể thực hiện nhiều bước trước khi triển khai nghiệp vụ.

### 9.1. Ma trận kiểm thử dữ liệu

| Input/điều kiện | Kỳ vọng | Kiểu kiểm tra |
| --- | --- | --- |
| Request mẫu có 2 `item`, quantity 2 và 1 | Hợp lệ | XSD và sample payload |
| Thiếu `buyerId` | Không hợp lệ | XSD validation |
| `quantity=0` hoặc `1000` | Không hợp lệ | XSD validation |
| `items` không có `item` | Không hợp lệ | XSD validation |
| `requestedDeliveryDate` bị bỏ | Hợp lệ | `minOccurs=0` |
| `clientComment` dài hơn 500 ký tự | Không hợp lệ | XSD validation |
| `requestId` chứa khoảng trắng | Không hợp lệ | XSD pattern |
| Đổi prefix `ord` nhưng giữ namespace URI | Vẫn hợp lệ nếu cấu trúc y nguyên | QName |
| Đổi namespace URI của request | Không còn hợp lệ theo schema v1 | Namespace/QName |
| Sai thứ tự `buyerId` và `requestId` | Không hợp lệ | `xs:sequence` |
| Cùng `requestId`, cùng nội dung gửi lại | Trả lại cùng kết quả, không tạo đơn mới | Integration test idempotency |
| Cùng `requestId`, nội dung khác | Fault mã xung đột theo hợp đồng | Integration test |
| Buyer không tồn tại | Fault nghiệp vụ đúng mã | Application/SOAP fault test |
| Signature/timestamp không hợp lệ nếu bật WS-Security | Từ chối, không chạy nghiệp vụ | Security test |

**XSD validation không kiểm tra được** buyer tồn tại, SKU đã được bán hay chưa, quyền truy cập, idempotency và chữ ký số. Đó là những kiểm thử ở lớp tương ứng.

### 9.2. Kiểm thử Spring-WS sau khi có mã triển khai

Khi endpoint được viết, dùng `MockWebServiceClient` để đưa XML request vào hạ tầng Spring-WS và kiểm tra response/fault; với SOAP client dùng `MockWebServiceServer`. Các assertion quan trọng:

- Phần tử gốc Body có đúng namespace và local name; endpoint có khớp `@PayloadRoot`?
- Phản hồi có `requestId` tương ứng, `orderId` hợp lệ, enum và timestamp đúng hợp đồng?
- XML response thực sự hợp lệ theo XSD, kể cả thứ tự phần tử?
- Khi lỗi, có đúng SOAP Fault code/detail và không lộ stack trace?
- Client sinh từ WSDL có marshal/unmarshal được với XML của server hay không?
- Trên reverse proxy, `soap:address` trong WSDL có phải địa chỉ dùng được từ bên ngoài?
- Trường hợp retry sau timeout có tạo trùng đơn không?

Với đối tác khác nền tảng, nên kiểm thử **wire XML**, không chỉ kiểm tra đối tượng Java. JAXB có thể tạo được đối tượng hợp lệ trong Java nhưng XML trên mạng sai namespace, thứ tự, optionality hoặc SOAP version.

## 10. Quy trình thiết kế contract-first có thể áp dụng ngay

~~~mermaid
flowchart TD
    A["Thu thập yêu cầu nghiệp vụ"] --> B["Chốt operation và semantics"]
    B --> C["Liệt kê request/response và dữ liệu sở hữu"]
    C --> D["Chọn QName, namespace, kiểu, optionality"]
    D --> E["Viết XSD và XML mẫu"]
    E --> F["Xác định SOAP Fault, retry, security"]
    F --> G["Công bố/kiểm tra WSDL dự kiến"]
    G --> H["Validate XML và thử sinh client JAXB/.NET"]
    H --> I{"Hai bên chấp thuận hợp đồng?"}
    I -- "Chưa" --> D
    I -- "Rồi" --> J["Viết endpoint và SOAP client"]
    J --> K["Kiểm thử XSD, WSDL, fault và tương thích"]
~~~

Trước khi bắt tay vào `@Endpoint`, bộ bàn giao tối thiểu nên có: XSD version hóa, WSDL mẫu hoặc WSDL đã chốt, request/response XML thành công, bảng trường và semantics, bảng lỗi, quy tắc idempotency/timeout, chính sách bảo mật và ma trận tương thích. Tài liệu này giúp nhà phát triển Java, QA và đối tác SOAP khác nền tảng cùng hiểu **một** hợp đồng thay vì suy diễn từ mã nguồn.

### Câu hỏi tự kiểm tra

1. Vì sao request `SubmitOrderRequest` không nên chứa `orderId` do client tự đặt trong bài toán này?
2. Với `xs:sequence`, điều gì xảy ra nếu client gửi `buyerId` trước `requestId`?
3. `minOccurs="0"` khác gì `nillable="true"`? Có thể thay thế hai thuộc tính cho nhau không?
4. Tại sao `SubmitOrderResponse` có `status=ACCEPTED` vẫn chưa đồng nghĩa đơn đã giao?
5. Client gửi lại cùng `requestId` sau timeout thì server cần đáp ứng quy tắc gì để tránh tạo trùng?
6. Một SOAP Fault về `UNKNOWN_BUYER` cần được định nghĩa và kiểm thử ở những lớp nào?
7. Tại sao thay namespace URI và thêm enum value có thể phá vỡ client dù phương thức Java không đổi?
8. Vì sao XML hợp lệ theo XSD vẫn có thể bị từ chối bởi WS-Security hoặc nghiệp vụ?

**Ghi nhớ:** Contract-first bắt đầu bằng **cặp thông điệp và ngữ nghĩa ổn định trên đường truyền**. Khi request/response, schema, lỗi, bảo mật và quy tắc tương thích được thống nhất, endpoint Spring-WS và SOAP client mới có một mục tiêu triển khai có thể kiểm chứng.
