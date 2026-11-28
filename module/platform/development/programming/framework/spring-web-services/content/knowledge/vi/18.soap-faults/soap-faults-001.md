# Cấu trúc SOAP Fault trong SOAP 1.1 và SOAP 1.2

Khi một dịch vụ SOAP không thể xử lý thông điệp theo hợp đồng, phản hồi lỗi phù hợp thường là **SOAP Fault**: một cấu trúc XML chuẩn nằm trong `SOAP Body`. SOAP Fault giúp bên gửi phân biệt lỗi do thông điệp yêu cầu, lỗi tại bên nhận, Header bắt buộc chưa được hiểu hoặc lỗi phiên bản SOAP. Khác với chuỗi exception Java hay một HTTP status đơn lẻ, nó là **một phần của giao thức SOAP** và có cấu trúc khác nhau giữa **SOAP 1.1** và **SOAP 1.2**.

Ví dụ, một client gọi `GetOrder` nhưng gửi `orderId` không hợp lệ. Server có thể báo SOAP Fault với mã nhóm lỗi do yêu cầu không hợp lệ và phần `detail` chứa mã nghiệp vụ `INVALID_ORDER_ID`. Khi database không hoạt động, server có thể trả nhóm lỗi máy chủ; khi một `wsse:Security` Header bắt buộc không được xử lý đúng, Fault có thể thuộc nhóm bảo mật hoặc `MustUnderstand` theo SOAP processing model. **Không phải mọi exception đều có cùng nguyên nhân và không nên trả cùng một thông điệp lỗi cho mọi trường hợp.**

Bài học thuộc chương **SOAP Fault** của module **SPRING_WEB_SERVICES**. Trong module, chúng ta phát triển dịch vụ SOAP theo hướng **contract-first** bằng XSD/WSDL, JAXB và Spring-WS endpoint/client; đồng thời xử lý interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Bài này tập trung vào **cấu trúc Fault chuẩn của hai phiên bản SOAP**, cách đọc đúng Fault, mô tả lỗi bằng WSDL/XSD và những hệ quả khi triển khai Spring-WS.

## 1. SOAP Fault là gì và nằm ở đâu?

Một SOAP message điển hình có `Envelope`, `Header` tùy chọn và `Body`. **Fault là một phần tử trong Body**, không phải Header tùy chỉnh hay một trường `error` trong JSON.

~~~mermaid
flowchart TD
    A["SOAP Envelope"] --> H["SOAP Header<br/>metadata, WS-Security..."]
    A --> B["SOAP Body"]
    B --> C{"Kết quả xử lý"}
    C -->|Thành công| R["Response payload<br/>GetOrderResponse"]
    C -->|Lỗi| F["SOAP Fault<br/>mã lỗi, lý do, chi tiết"]
~~~

Với pattern request–response thông thường, Body phản hồi mang **payload thành công hoặc Fault**, không đặt một `GetOrderResponse` thành công bên cạnh `Fault` để client tự đoán. SOAP Fault được tạo theo **phiên bản SOAP của message**, không tùy ý trộn hai định dạng.

| Khái niệm | Vai trò | Có tự tương đương SOAP Fault không? |
| --- | --- | --- |
| Java `Exception` | Biểu thị lỗi trong chương trình | **Không**; cần cơ chế ánh xạ |
| HTTP `400`, `500`, `502` | Trạng thái tầng HTTP | **Không**; body có thể không phải SOAP |
| SOAP Fault | Cấu trúc lỗi SOAP trên dây | **Có**; tuân schema/processing model SOAP |
| WSDL `wsdl:fault` | Mô tả lỗi operation ở mức hợp đồng | Không phải message đã được tạo tại runtime |
| XSD element cho fault detail | Hợp đồng dữ liệu của chi tiết lỗi | Không tự quyết định Fault Code |
| `MessageContext` property `error` | Metadata nội bộ một lượt xử lý | **Không**; client không tự thấy property |

**Lỗi SOAP không nhất thiết là lỗi nghiệp vụ.** Nó cũng có thể phát sinh khi SOAP Header không xử lý được, Envelope sai phiên bản hoặc SOAP security policy bị vi phạm. Ngược lại, một lỗi TLS handshake hoặc reverse proxy trả `502` có thể xảy ra **trước khi** Spring-WS có cơ hội tạo SOAP Fault.

## 2. Hai namespace SOAP phải phân biệt ngay từ đầu

| Đặc điểm | SOAP 1.1 | SOAP 1.2 |
| --- | --- | --- |
| Namespace Envelope | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| Root Fault | `soapenv:Fault` trong Body | `env:Fault` trong Body |
| Cấu trúc bắt buộc của Fault | `faultcode`, `faultstring` | `env:Code`, `env:Reason` |
| Cách thể hiện mã lỗi mở rộng | QName trong `faultcode` hoặc chi tiết theo thỏa thuận | `env:Subcode` lồng nhau |
| Lý do có nhiều ngôn ngữ | `faultstring`, có thể gắn thông tin ngôn ngữ | `env:Reason` chứa một hoặc nhiều `env:Text xml:lang` |
| Node gây lỗi | `faultactor` (khi áp dụng) | `env:Node` và `env:Role` |
| Chi tiết ứng dụng | `detail` | `env:Detail` |

Đừng chỉ đổi prefix XML `soapenv` thành `env` để chuyển phiên bản. **Namespace URI thay đổi và các tên/quan hệ phần tử bên trong Fault cũng thay đổi.**

~~~xml
<!-- SOAP 1.1 -->
xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"

<!-- SOAP 1.2 -->
xmlns:env="http://www.w3.org/2003/05/soap-envelope"
~~~

**Prefix không quyết định phiên bản**. Một SOAP Envelope dùng prefix `s` vẫn là SOAP 1.1 nếu URI là namespace SOAP 1.1. Ngược lại, dùng prefix `soapenv` với URI SOAP 1.2 vẫn là SOAP 1.2.

## 3. Cấu trúc SOAP Fault trong SOAP 1.1

Ví dụ Fault cho một request đơn hàng sai dữ liệu:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>orderId không hợp lệ</faultstring>
            <detail>
                <ord:InvalidOrderFault>
                    <ord:errorCode>INVALID_ORDER_ID</ord:errorCode>
                    <ord:message>Thiếu mã đơn hàng</ord:message>
                </ord:InvalidOrderFault>
            </detail>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Trong SOAP 1.1, `Fault` là phần tử trong namespace SOAP 1.1, nhưng **`faultcode`, `faultstring`, `faultactor` và `detail` là các phần tử con không có namespace SOAP** trong cú pháp chuẩn. Đây là khác biệt dễ mắc lỗi khi tự dựng XML.

### 3.1. Bốn phần tử chính

| Thành phần SOAP 1.1 | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `faultcode` | Có | QName cho **phân loại lỗi ở tầng SOAP** |
| `faultstring` | Có | Lời giải thích có thể đọc được bằng con người, không phải mã máy ổn định |
| `faultactor` | Không phải mọi trường hợp | URI xác định SOAP node gây ra Fault; có ý nghĩa đặc biệt khi message qua trung gian |
| `detail` | Tùy tình huống | Dữ liệu ứng dụng bổ sung về lỗi xử lý Body; xem quy tắc SOAP 1.1 |

**Lưu ý `faultcode` là QName có namespace**, dù thẻ chứa nó là thẻ không namespace. Giá trị `soapenv:Client` tham chiếu namespace Envelope. Với một mã do ứng dụng định nghĩa, prefix của QName phải được khai báo và việc client hiểu mã đó cần dựa trên thỏa thuận.

### 3.2. Các faultcode chuẩn của SOAP 1.1

| Mã chuẩn | Khi nào dùng |
| --- | --- |
| `VersionMismatch` | SOAP node gặp Envelope namespace không thuộc phiên bản được hỗ trợ |
| `MustUnderstand` | Header block hướng đến node đó có `mustUnderstand` nhưng node không xử lý được |
| `Client` | Thông điệp yêu cầu không đủ hoặc không hợp lệ theo yêu cầu xử lý; thường phải sửa request |
| `Server` | Server không xử lý được do lỗi/trạng thái phía nhận, không nhất thiết do request sai |

Ví dụ `soapenv:Client` **không phải HTTP 400 viết dưới dạng XML**; đó là SOAP faultcode. HTTP binding có thể dùng status khác tùy phiên bản SOAP và triển khai. Đừng dùng tên `Client` làm lời bảo đảm lỗi sẽ được retry hay không: còn phải xét mã chi tiết, tính idempotent và chính sách client.

### 3.3. `faultactor` mô tả nơi xảy ra lỗi

Khi một thông điệp đi qua SOAP intermediary, node tạo Fault có thể khai báo URI:

~~~xml
<faultactor>urn:example:gateway:validation</faultactor>
~~~

SOAP 1.1 quy định thông tin này quan trọng khi node tạo Fault **không phải đích cuối** của thông điệp. Không đặt một URL ngẫu nhiên hoặc IP nội bộ vào `faultactor` như dữ liệu debug nếu hợp đồng không cần. URI này nói **node phát sinh lỗi**, không mặc nhiên là HTTP URL có thể gọi hoặc danh tính đã được xác thực.

### 3.4. `detail` không phải vùng chứa exception Java

`detail` dùng để mang thông tin lỗi **cụ thể với ứng dụng khi xử lý Body**. SOAP 1.1 có quy tắc về việc sử dụng `detail` cho lỗi liên quan đến Body; thông tin lỗi xử lý Header không nhất thiết được mô tả ở đây. Một cấu trúc detail hợp đồng nên chứa **mã lỗi ổn định** và dữ liệu tối thiểu để client xử lý:

~~~xml
<detail>
    <ord:OrderNotFoundFault xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
        <ord:errorCode>ORDER_NOT_FOUND</ord:errorCode>
    </ord:OrderNotFoundFault>
</detail>
~~~

**Không trả stack trace, SQL query, internal hostname, private key, raw token hoặc certificate secrets** trong detail. Lỗi bảo mật không nên tiết lộ thông tin giúp kẻ tấn công đoán truststore, tài khoản hoặc chính sách xác thực.

## 4. Cấu trúc SOAP Fault trong SOAP 1.2

SOAP 1.2 thay thế các trường phẳng của SOAP 1.1 bằng một mô hình có cấu trúc rõ hơn:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:v1">
    <env:Body>
        <env:Fault>
            <env:Code>
                <env:Value>env:Sender</env:Value>
                <env:Subcode>
                    <env:Value>ord:InvalidOrderId</env:Value>
                </env:Subcode>
            </env:Code>
            <env:Reason>
                <env:Text xml:lang="vi">
                    orderId không hợp lệ
                </env:Text>
                <env:Text xml:lang="en">
                    Invalid order ID
                </env:Text>
            </env:Reason>
            <env:Detail>
                <ord:InvalidOrderFault>
                    <ord:errorCode>INVALID_ORDER_ID</ord:errorCode>
                    <ord:message>Thiếu mã đơn hàng</ord:message>
                </ord:InvalidOrderFault>
            </env:Detail>
        </env:Fault>
    </env:Body>
</env:Envelope>
~~~

Ở SOAP 1.2, các thành phần `env:Code`, `env:Reason` và `env:Detail` **đều thuộc namespace SOAP 1.2**. Điều này khác rõ so với tên con `faultcode`/`detail` không namespace của SOAP 1.1.

### 4.1. Các phần tử của `env:Fault`

| Thành phần SOAP 1.2 | Bắt buộc? | Ý nghĩa |
| --- | --- | --- |
| `env:Code` | Có | Gồm `env:Value` bắt buộc và `env:Subcode` tùy chọn |
| `env:Reason` | Có | Một hoặc nhiều `env:Text`, mỗi `Text` có `xml:lang` |
| `env:Node` | Tùy chọn | URI nhận diện SOAP node tạo Fault |
| `env:Role` | Tùy chọn | URI nhận diện role mà node đang thực hiện khi Fault xảy ra |
| `env:Detail` | Tùy chọn | Thông tin bổ sung hướng tới ứng dụng khi xử lý thông điệp |

Trình tự các child của `env:Fault` theo cấu trúc SOAP 1.2 là **`Code` → `Reason` → `Node` → `Role` → `Detail`**, trong đó các phần tử tùy chọn có thể vắng mặt. Không dùng thứ tự phần tử SOAP 1.1 để dựng Fault 1.2.

### 4.2. Các mã chuẩn trong SOAP 1.2

| `env:Value` | Nội dung |
| --- | --- |
| `env:VersionMismatch` | Envelope không dùng phiên bản SOAP mà node hỗ trợ |
| `env:MustUnderstand` | Node đích không hiểu một Header block bắt buộc |
| `env:DataEncodingUnknown` | SOAP node không hỗ trợ một mã hóa dữ liệu được chỉ định theo mô hình SOAP |
| `env:Sender` | Thông điệp không có đủ thông tin hoặc có thông tin sai để xử lý |
| `env:Receiver` | Không xử lý được do nguyên nhân phía node nhận, thường có thể thành công sau khi tình trạng được sửa |

**Cặp tương ứng gần đúng:** SOAP 1.1 `Client` ↔ SOAP 1.2 `Sender`; SOAP 1.1 `Server` ↔ SOAP 1.2 `Receiver`. Đây là tương ứng **về ý nghĩa phân loại**, không phải việc thay thế tên một cách cơ học trong XML.

### 4.3. `env:Subcode` cho mã ứng dụng

Một `env:Code` trong SOAP 1.2 phải có `env:Value` chứa QName mã chính. Khi cần phân loại chi tiết hơn:

~~~xml
<env:Code xmlns:env="http://www.w3.org/2003/05/soap-envelope"
          xmlns:ord="urn:example:orders:v1">
    <env:Value>env:Sender</env:Value>
    <env:Subcode>
        <env:Value>ord:ValidationError</env:Value>
        <env:Subcode>
            <env:Value>ord:InvalidOrderId</env:Value>
        </env:Subcode>
    </env:Subcode>
</env:Code>
~~~

`env:Subcode` **có thể lồng nhiều cấp**; mỗi cấp chỉ mang một `Value` và tối đa một `Subcode` tiếp theo. Các giá trị QName `ord:ValidationError`, `ord:InvalidOrderId` là mã ứng dụng minh họa; cần được công bố/ổn định theo hợp đồng, không tự hiểu giống tên Java exception.

Nếu client cũ chỉ xem `env:Sender` mà bỏ Subcode, nó có thể xử lý lỗi chung. Nếu client cần xử lý `ord:InvalidOrderId`, server phải cam kết mã đó và test interoperability. Đừng dùng Subcode để chứa message tự do hoặc exception stack trace.

### 4.4. `env:Reason` hỗ trợ nhiều ngôn ngữ

~~~xml
<env:Reason xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Text xml:lang="vi">Đơn hàng không tồn tại</env:Text>
    <env:Text xml:lang="en">Order not found</env:Text>
</env:Reason>
~~~

Mỗi `env:Text` cần `xml:lang` theo cấu trúc SOAP 1.2, có thể cung cấp thông điệp cho nhiều ngôn ngữ. **Reason là mô tả để con người đọc**, không phải giao thức phân loại ổn định cho client. Client nên xử lý bằng `Code`/`Subcode` và phần `Detail` theo hợp đồng, không dùng `reason.contains("not found")` hoặc so chuỗi tiếng Việt.

### 4.5. `env:Node` và `env:Role` khác nhau

~~~xml
<env:Node xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    urn:example:gateway:orders
</env:Node>
<env:Role xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    http://www.w3.org/2003/05/soap-envelope/role/next
</env:Role>
~~~

- **Node** xác định **SOAP node** sinh Fault.
- **Role** thể hiện **vai trò SOAP** mà node thực hiện khi phát sinh lỗi.
- Chúng là các URI trong processing model, không tự chứng minh danh tính/certificate hoặc quyền truy cập.
- Không nên để URI chứa thông tin nội bộ nhạy cảm nếu phản hồi đi ra mạng đối tác.

### 4.6. `env:Detail` có cấu trúc XML riêng

~~~xml
<env:Detail xmlns:env="http://www.w3.org/2003/05/soap-envelope"
            xmlns:ord="urn:example:orders:v1">
    <ord:OrderNotFoundFault>
        <ord:orderId>ORD-1024</ord:orderId>
        <ord:errorCode>ORDER_NOT_FOUND</ord:errorCode>
    </ord:OrderNotFoundFault>
</env:Detail>
~~~

Đây là chi tiết XML của ứng dụng, không phải nơi trả mọi lỗi nội bộ. Có thể dùng cùng một **global XSD element** cho dữ liệu chi tiết lỗi trên SOAP 1.1 và SOAP 1.2, nhưng **phần wrapper SOAP** khác: `detail` so với `env:Detail`.

## 5. Bảng đối chiếu SOAP 1.1 và SOAP 1.2

| Nội dung cần biểu diễn | SOAP 1.1 | SOAP 1.2 | Ghi nhớ |
| --- | --- | --- | --- |
| Phần tử Fault | `soapenv:Fault` | `env:Fault` | Cùng nằm trong Body nhưng namespace khác |
| Mã lỗi chính | `faultcode` | `env:Code/env:Value` | Giá trị là QName |
| Mã con có cấu trúc | Không có `Subcode` chuẩn tương đương | `env:Subcode` có thể lồng | Dùng khi cần taxonomy máy đọc |
| Lỗi do request | `Client` | `Sender` | Không tự đồng nhất với HTTP 400 |
| Lỗi phía server | `Server` | `Receiver` | Không tự xác định retry policy |
| Lời giải thích | `faultstring` | `env:Reason/env:Text` | Không parse để quyết định workflow |
| Node phát sinh | `faultactor` | `env:Node` | Không nhầm với địa chỉ HTTPS endpoint |
| Role khi lỗi | Thể hiện trong SOAP processing/faultactor | `env:Role` | Rõ hơn trong SOAP 1.2 |
| Chi tiết ứng dụng | `detail` | `env:Detail` | Các element chi tiết do XSD riêng xác định |
| MustUnderstand | `soapenv:MustUnderstand` | `env:MustUnderstand` | Phụ thuộc node/role nhận Header |
| VersionMismatch | `soapenv:VersionMismatch` | `env:VersionMismatch` | Sai Envelope namespace |

Hai điều cần ghi nhớ khi viết code hoặc test:

1. **Không cố đổi SOAP 1.1 thành SOAP 1.2 bằng string replace**. Phải dùng SOAP message factory/binding đúng phiên bản, XML namespaces và Fault model tương ứng.
2. **Không nhầm lỗi protocol với lỗi nghiệp vụ**. Cả hai có thể biểu diễn bằng SOAP Fault, nhưng mã phân loại, XSD detail, bảo mật và cách client phản ứng cần khác nhau.

## 6. SOAP Fault trong các tình huống thực tế

Ví dụ một dịch vụ SOAP `GetOrder` có thể gặp:

| Tình huống | Hướng phân loại thường phù hợp | Điều cần cẩn trọng |
| --- | --- | --- |
| Request sai XSD, thiếu `orderId` | SOAP 1.1 `Client` hoặc SOAP 1.2 `Sender` | Schema validation phải bật thực sự |
| `orderId` đúng cấu trúc nhưng không tồn tại | Business Fault theo hợp đồng; nhóm Sender/Client nếu policy chọn | Không làm lộ đơn hàng thuộc tenant khác |
| Client gửi SOAP version không hỗ trợ | `VersionMismatch` | Parser/transport phải đủ khả năng trả Fault phù hợp |
| Header `mustUnderstand` nhắm đến node chưa được xử lý | `MustUnderstand` | Xét actor/role, không phải cứ Header lạ là lỗi |
| SOAP security signature/token không hợp lệ | Security Fault theo WS-Security policy | Không tiết lộ chi tiết khóa/truststore |
| Database unavailable | SOAP 1.1 `Server` hoặc SOAP 1.2 `Receiver` | Không khẳng định retry an toàn với operation có side effect |
| JAXB marshal response thiếu element bắt buộc | Lỗi server/response contract | Validate outbound, không trả response sai schema |
| Proxy trả 502, TLS handshake thất bại | **Không nhất thiết có SOAP Fault** | Phân biệt gateway/transport với SOAP runtime |

Một mapping nghiệp vụ như `ORDER_NOT_FOUND` nên được định nghĩa một lần trong **contract**, rồi sử dụng nhất quán giữa SOAP 1.1/1.2. Không để tên Java exception hoặc ngôn ngữ của `faultstring` thành API công khai.

## 7. Định nghĩa Fault detail bằng XSD: hợp đồng dữ liệu cho lỗi

Trong thiết kế **contract-first**, ứng dụng có thể định nghĩa **global element** cho chi tiết lỗi để client sinh JAXB classes hoặc loại dữ liệu tương ứng.

XSD minh họa:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:complexType name="OrderNotFoundFaultType">
        <xs:sequence>
            <xs:element name="errorCode" type="xs:string"/>
            <xs:element name="orderId" type="xs:string"
                        minOccurs="0"/>
            <xs:element name="correlationId" type="xs:string"
                        minOccurs="0"/>
        </xs:sequence>
    </xs:complexType>

    <xs:element name="OrderNotFoundFault"
                type="ord:OrderNotFoundFaultType"/>
</xs:schema>
~~~

Với SOAP 1.1, dữ liệu này có thể nằm trong:

~~~xml
<detail>
    <ord:OrderNotFoundFault xmlns:ord="urn:example:orders:v1">
        <ord:errorCode>ORDER_NOT_FOUND</ord:errorCode>
        <ord:orderId>ORD-1024</ord:orderId>
        <ord:correlationId>req-8f21</ord:correlationId>
    </ord:OrderNotFoundFault>
</detail>
~~~

Với SOAP 1.2, cùng element XML nằm trong `env:Detail`. Trong cả hai trường hợp, **trình tự các child** bên trong `ord:OrderNotFoundFault` phải khớp `xs:sequence`, và `QName` của các child phải đúng namespace `urn:example:orders:v1`.

### Dùng detail để máy đọc, Reason/faultstring để người đọc

| Dữ liệu | Khuyến nghị |
| --- | --- |
| `errorCode` | Ổn định, có tài liệu, không phụ thuộc ngôn ngữ |
| `correlationId` | Có thể dùng để đối soát log; kiểm tra nguồn và tránh để lộ định danh nhạy cảm |
| `orderId` | Chỉ trả khi caller được phép biết identifier đó |
| `faultstring` / `Reason` | Văn bản ngắn, dễ hiểu; có thể bản địa hóa và thay đổi |
| `stackTrace` | **Không trả** trong SOAP Fault công khai |
| Chi tiết certificate/trust/token | **Không trả** trong lỗi security |

**Chú ý về lỗi phân quyền:** `OrderNotFoundFault` có thể làm lộ rằng một order cụ thể tồn tại hoặc không tồn tại. Với caller chưa được phép xem tài nguyên, nhiều hệ thống chọn mã lỗi chung, tránh tiết lộ trạng thái nội bộ.

## 8. Mô tả operation Fault trong WSDL 1.1

XSD định nghĩa chi tiết lỗi, nhưng **WSDL** mới nói operation nào có thể công bố lỗi đó. Ví dụ các đoạn rút gọn dưới đây là **mảnh ghép** của một WSDL document/literal đầy đủ, không phải tệp WSDL hoàn chỉnh.

~~~xml
<!-- Giả định definitions có wsdl, soap, ord và tns. -->
<wsdl:message name="OrderNotFoundFaultMessage">
    <wsdl:part name="fault"
               element="ord:OrderNotFoundFault"/>
</wsdl:message>

<wsdl:portType name="OrdersPortType">
    <wsdl:operation name="GetOrder">
        <wsdl:input message="tns:GetOrderInput"/>
        <wsdl:output message="tns:GetOrderOutput"/>
        <wsdl:fault name="OrderNotFoundFault"
                    message="tns:OrderNotFoundFaultMessage"/>
    </wsdl:operation>
</wsdl:portType>
~~~

Và trong SOAP 1.1 binding của cùng operation:

~~~xml
<!-- Trích đoạn wsdl:binding, không gồm phần binding/service đầy đủ. -->
<wsdl:operation name="GetOrder">
    <soap:operation soapAction="urn:example:orders:GetOrder"/>
    <wsdl:input>
        <soap:body use="literal"/>
    </wsdl:input>
    <wsdl:output>
        <soap:body use="literal"/>
    </wsdl:output>
    <wsdl:fault name="OrderNotFoundFault">
        <soap:fault name="OrderNotFoundFault"
                    use="literal"/>
    </wsdl:fault>
</wsdl:operation>
~~~

Để phát hành thực sự, WSDL còn cần definitions, namespace imports, message input/output, binding/port/service, `soap:address` và schema dependencies resolve được. SOAP 1.2 trong WSDL 1.1 thường dùng các extension binding khác (ví dụ namespace SOAP 1.2 WSDL binding) chứ **không** chỉ thay `SOAP Envelope namespace` của ví dụ SOAP 1.1.

### Những giới hạn quan trọng của WSDL Fault

- `wsdl:fault` mô tả lỗi **được công bố trong hợp đồng**, thường để client sinh exception/binding type thích hợp.
- Một lỗi SOAP cấp giao thức như `VersionMismatch`, `MustUnderstand` hoặc lỗi security có thể xảy ra **mà không được mô hình hóa thành từng `wsdl:fault` nghiệp vụ**.
- Mỗi phần tử Fault detail nên có **global XSD element** và QName có thể tham chiếu theo binding được chọn.
- WSDL không tự khiến một Java exception thành SOAP Fault; server cần **exception resolver** và logic tạo detail.
- Khi thêm/xóa/đổi Fault detail, phải kiểm thử client đã sinh từ WSDL cũ, vì kiểu lỗi thay đổi có thể là **breaking change**.

## 9. Spring-WS tạo SOAP Fault ở đâu?

Trong Spring-WS, luồng xử lý lỗi khái quát:

~~~mermaid
flowchart TD
    A["SOAP request"] --> B["Transport / SOAP parsing"]
    B --> C["Endpoint mapping + interceptors"]
    C --> D["JAXB / endpoint / domain service"]
    D --> E{"Kết quả"}
    E -->|OK| F["SOAP success response"]
    E -->|Exception| G["EndpointExceptionResolver<br/>mapping exception"]
    G --> H["SoapFault trong response Body"]
    C -->|"Security / schema fault"| H
    H --> I["SOAP response theo version"]
    B -.->|"Lỗi trước SOAP processing"| J["HTTP / gateway error<br/>có thể không có SOAP Fault"]
~~~

Sơ đồ chỉ mô tả trách nhiệm, **không khẳng định** mọi lỗi security/parser/transport đều đi qua cùng một `EndpointExceptionResolver`. Lỗi có thể được xử lý bởi validator, security interceptor hoặc tầng khác trước khi endpoint chạy.

Một số thành phần Spring-WS liên quan:

| Thành phần | Công dụng |
| --- | --- |
| `@SoapFault` | Khai báo mapping tĩnh từ exception type sang Fault code/reason bằng annotation |
| `SoapFaultAnnotationExceptionResolver` | Đọc annotation `@SoapFault` để tạo SOAP Fault |
| `SoapFaultMappingExceptionResolver` | Ánh xạ exception classes sang fault definition qua cấu hình |
| `SoapFaultDefinition` | Chứa fault code, fault string/reason, locale của định nghĩa Fault |
| `SoapFault` / `SoapFaultDetail` | Abstraction để làm việc với Fault trong SOAP message |
| `PayloadValidatingInterceptor` | Kiểm tra payload theo XSD ở điểm được cấu hình |
| `Wss4jSecurityInterceptor` | Thực thi chính sách WS-Security tương ứng với cấu hình |

**Quan trọng:** các mapping trên phụ thuộc Spring-WS version, SOAP version và thứ tự resolver/interceptor. Nếu có nhiều resolver áp dụng, cần chủ đích xác định thứ tự và dùng integration test để xác minh Fault thực tế.

### 9.1. Khai báo exception với `@SoapFault`

Ví dụ dành cho dịch vụ **SOAP 1.1**:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Yêu cầu không hợp lệ")
public class InvalidOrderRequestException extends RuntimeException {
    public InvalidOrderRequestException(String message) {
        super(message);
    }
}
~~~

Khi resolver tương ứng được đăng ký và chọn exception này, ứng dụng có thể trả Fault với phân loại `Client` cùng lý do đã khai báo. **Đây là mapping tĩnh**: `faultStringOrReason` không tự lấy nội dung động từ `ex.getMessage()`. Không gửi exception message nội bộ ra client bằng cách ghép chuỗi tùy ý.

Với SOAP 1.2, phân loại tương ứng thường là **`Sender`/`Receiver`**; cấu hình annotation/resolver phải phù hợp SOAP version chứ không giả định `Client` và `Sender` là cùng QName. Hãy xác nhận mapping trên runtime/version dự án.

### 9.2. Ánh xạ exception qua `SoapFaultMappingExceptionResolver`

Ví dụ cấu hình cho môi trường **SOAP 1.1**:

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.server.endpoint.SoapFaultDefinition;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;

@Configuration
public class SoapFaultResolverConfig {
    @Bean
    public SoapFaultMappingExceptionResolver soapFaultResolver() {
        SoapFaultMappingExceptionResolver resolver =
                new SoapFaultMappingExceptionResolver();

        Properties mappings = new Properties();
        mappings.setProperty(
                InvalidOrderRequestException.class.getName(),
                "CLIENT,Yêu cầu không hợp lệ");
        mappings.setProperty(
                OrderNotFoundException.class.getName(),
                "CLIENT,Đơn hàng không tồn tại");
        resolver.setExceptionMappings(mappings);

        SoapFaultDefinition fallback = new SoapFaultDefinition();
        fallback.setFaultCode(SoapFaultDefinition.SERVER);
        fallback.setFaultStringOrReason("Dịch vụ tạm thời không sẵn sàng");
        resolver.setDefaultFault(fallback);
        resolver.setOrder(1);
        return resolver;
    }
}
~~~

Ví dụ giả định `InvalidOrderRequestException` và `OrderNotFoundException` là các loại exception do ứng dụng định nghĩa, đồng thời không có resolver khác ưu tiên hơn làm thay đổi kết quả. Chuỗi mapping như `CLIENT,reason` cần được đối chiếu với cú pháp hỗ trợ của phiên bản Spring-WS sử dụng; một mapping `Client` trên SOAP 1.1 không được bê nguyên sang SOAP 1.2 khi chưa kiểm tra.

**Resolver không tự sinh typed Fault detail từ tên exception.** Nếu WSDL công bố `OrderNotFoundFault` với các trường `errorCode`/`orderId`, cần cấu hình/customize logic để tạo **XML detail đúng XSD**. Không dùng mỗi `faultstring` rồi tuyên bố đã thực hiện đủ hợp đồng typed fault.

### 9.3. Tạo chi tiết Fault có kiểm soát

Một bản triển khai có thể dùng `SoapFault` và `SoapFaultDetail` từ SOAP response mà framework tạo ra để thêm phần tử detail. Về mặt cấu trúc:

~~~text
Java exception đã được phân loại
  ↓
Exception resolver chọn SOAP Fault Code/Reason
  ↓
SoapFaultDetail được bổ sung theo XSD
  ↓
SOAP 1.1: <detail> ... </detail>
SOAP 1.2: <env:Detail> ... </env:Detail>
  ↓
Client đọc QName của detail và mã nghiệp vụ
~~~

Logic bổ sung detail có thể được đặt trong exception resolver tùy chỉnh/điểm extension mà phiên bản Spring-WS hỗ trợ. Khi dùng JAXB, hãy marshal **global element** `ord:OrderNotFoundFault` vào vùng detail thích hợp; không marshal **toàn bộ Envelope** hoặc tự tạo một `Fault` lồng bên trong `Fault`.

Tách **mã lỗi máy đọc** khỏi **nội dung Reason/faultstring**. Tránh lộ `Exception.toString()`, raw SQL hoặc thông điệp thư viện third-party cho client.

## 10. Client Spring-WS đọc SOAP Fault thế nào?

Khi phía server trả SOAP Fault, `WebServiceTemplate` có cơ chế phát hiện và xử lý Fault. Theo cấu hình mặc định thường gặp, lỗi từ SOAP response có thể được biểu diễn thành exception thuộc họ `WebServiceFaultException`, cụ thể có thể gặp `SoapFaultClientException`.

Ví dụ đọc mã và lý do (đoạn minh họa client đã cấu hình `WebServiceTemplate`):

~~~java
import org.springframework.ws.soap.client.SoapFaultClientException;

try {
    GetOrderResponse result = (GetOrderResponse)
            webServiceTemplate.marshalSendAndReceive(request);
    // Xử lý thành công.
} catch (SoapFaultClientException ex) {
    var faultCode = ex.getFaultCode();
    String reason = ex.getFaultStringOrReason();

    // Ghi log đã lọc, phân loại theo SOAP version và contract.
    // Không retry mù quáng chỉ vì thấy mã Server/Receiver.
    handleSoapFault(faultCode, reason);
}
~~~

Đây là ví dụ về **đọc thông tin cơ bản**, giả định method `handleSoapFault` tự viết và client dùng JAXB root binding thích hợp. Với typed Fault detail, client có thể cần logic unmarshal `SoapFaultDetail` sang generated JAXB type, hoặc dùng proxy/client binding công cụ khác đã sinh exception riêng.

### Không dùng chuỗi `faultstring` để điều khiển nghiệp vụ

**Không nên:**

~~~java
if (reason.contains("không tồn tại")) {
    // Quyết định tạo lại đơn...
}
~~~

Vì `Reason` có thể đổi ngôn ngữ hoặc câu chữ, `faultstring` không phải mã ổn định. Hãy dùng QName của `Code`/`Subcode`, QName của detail element và `errorCode` trong XSD fault detail theo hợp đồng.

### Xử lý lỗi transport riêng

Client có thể gặp:

- Kết nối TLS/mTLS không thành công.
- Timeout, mất kết nối hoặc proxy trả 502/504.
- HTTP response không chứa SOAP Envelope hợp lệ.
- SOAP Envelope sai version.
- SOAP Fault chuẩn của đối tác.

Các tình huống này không cùng loại exception, không có cùng dữ liệu để đọc và không nên chung một retry rule. Một HTTP 502 của gateway **không tự trở thành `SoapFaultClientException`**.

## 11. HTTP status và SOAP Fault: hai tầng liên hệ nhưng không đồng nhất

Với SOAP qua HTTP, cả HTTP status lẫn SOAP Envelope đều quan trọng.

| Tình huống | Điểm cần hiểu |
| --- | --- |
| SOAP 1.1 xử lý lỗi SOAP qua HTTP | SOAP 1.1 HTTP binding mô tả việc trả HTTP **500** kèm SOAP Fault khi gặp lỗi SOAP lúc xử lý request |
| SOAP 1.2 xử lý Fault qua HTTP | HTTP binding của SOAP 1.2 có mapping status theo lỗi, thường phân biệt các nhóm như `Sender`/`Receiver`; cần đối chiếu binding cụ thể |
| Gateway/proxy `502`/`504` | Không bảo đảm có SOAP Fault hợp lệ |
| Client nhận HTTP status khác kỳ vọng | Có thể do SOAP version/binding, proxy rewrite, container hoặc security filter |
| SOAP Fault chứa mã `Client`/`Sender` | Không có nghĩa lúc nào cũng tương ứng HTTP 400 trong mọi môi trường |

Không thiết kế client chỉ kiểm `status >= 400` rồi bỏ qua SOAP Body; cũng không thiết kế client bỏ qua HTTP error nếu SOAP parser không đọc được nội dung. Với tích hợp doanh nghiệp, phải kiểm thử **response thực qua gateway**, bao gồm Content-Type, HTTP status, Envelope namespace và Fault detail.

### SOAP 1.1 và SOAP 1.2 có Content-Type khác nhau

Một SOAP 1.1 request/response qua HTTP thường sử dụng `text/xml` và header `SOAPAction` theo binding; SOAP 1.2 HTTP binding thường sử dụng `application/soap+xml`, có thể mang tham số `action`.

**Không tự chuyển từ 1.1 sang 1.2 bằng việc thay Content-Type** mà bỏ qua phiên bản Envelope, WSDL binding, Fault model và client message factory. Một lỗi do Content-Type/Envelope không khớp có thể xảy ra **trước cả endpoint**.

## 12. SOAP Fault, interceptor và thứ tự kiểm tra bảo mật

Trong một dịch vụ contract-first có WS-Security, lỗi có thể xuất hiện trước khi method `@Endpoint` được gọi:

~~~mermaid
flowchart TD
    A["SOAP request"] --> B["Transport / TLS / XML parser"]
    B --> C["SOAP security<br/>signature, token, decrypt"]
    C --> D["XSD validation / JAXB"]
    D --> E["@Endpoint / business service"]
    E --> F["SOAP success response"]
    B -.->|Lỗi| G["Transport error<br/>hoặc SOAP Fault nếu có context"]
    C -.->|Lỗi| H["Security Fault theo policy"]
    D -.->|Lỗi| I["Schema / data Fault"]
    E -.->|Lỗi| J["Business / server Fault"]
    H --> K["Response SOAP được tạo nếu có thể"]
    I --> K
    J --> K
~~~

Sơ đồ là **luồng trách nhiệm**, không cam kết thứ tự chính xác của interceptor trong mọi dự án. Spring-WS có thể phải định tuyến endpoint để xác định interceptor chain; XML parser phải chạy trước khi security engine đọc được Header; giải mã/xác minh có thứ tự theo policy.

Một số nguyên tắc:

1. **Chữ ký không hợp lệ phải bị từ chối trước tác dụng phụ nghiệp vụ.** Không ghi đơn vào database rồi mới trả security Fault.
2. **Không tiết lộ chi tiết nội bộ trong security Fault.** Lý do quá cụ thể có thể làm lộ certificate trust, tài khoản hoặc thuật toán.
3. **Không dùng `faultstring` để thay thế security audit.** Audit nội bộ cần thông tin đã lọc như correlation ID, loại chính sách thất bại và thời điểm.
4. **Không hạ tiêu chuẩn XML parser để đọc Fault hoặc request.** Cả client và server đều phải bảo vệ XML parser khỏi dữ liệu không tin cậy.
5. **Không xem `mustUnderstand` là authentication.** Nó là một phần của SOAP processing model, không phải chứng minh token/chữ ký.

### Khi một Header không được hiểu

SOAP Header có thể chứa `mustUnderstand` và `actor` (SOAP 1.1) hoặc `role` (SOAP 1.2). Nếu Header block **được nhắm đến SOAP node hiện tại** và buộc phải hiểu nhưng node không xử lý được, `MustUnderstand` là phân loại lỗi phù hợp. Một Header lạ **không nhắm đến node này** không mặc nhiên gây `MustUnderstand` Fault tại node đó.

Đối với `wsse:Security`, cần xử lý đúng mô hình Header lẫn chính sách WS-Security. Một request có Header Security không hợp lệ có thể sinh Fault theo security stack; không phải mọi lỗi như vậy đều được biểu diễn bằng cùng một mã `MustUnderstand`.

## 13. Quy tắc versioning và khả năng tương thích Fault

Thay đổi Fault có thể phá vỡ client ngay cả khi request/response “happy path” không đổi.

| Thay đổi | Rủi ro | Cách quản lý |
| --- | --- | --- |
| Đổi SOAP 1.1 sang 1.2 | Mọi tên phần tử Fault và binding thay đổi | Version/binding rõ, test client sinh từ WSDL |
| Đổi `ord:OrderNotFoundFault` sang namespace mới | QName detail khác, JAXB/client có thể không nhận | Chính sách versioning XSD/WSDL |
| Xóa trường `errorCode` | Client không phân loại lỗi được | Giữ contract hoặc phát hành version mới |
| Đổi giá trị `ORDER_NOT_FOUND` thành text tùy ý | Logic client dựa mã ổn định bị hỏng | Mã lỗi có tài liệu và regression tests |
| Chỉ đổi `faultstring` hoặc ngôn ngữ Reason | Client so chuỗi có thể hỏng | Dạy client dùng machine code/detail |
| Thêm SOAP 1.2 Subcode mới | Client strict có thể cần cập nhật | Công bố taxonomy lỗi và fallback hợp lý |
| Trả stack trace mới trong `Detail` | Rò rỉ bảo mật và lộ implementation | Lọc chi tiết, chỉ public fields |
| Đổi cách ánh xạ HTTP status | HTTP client/gateway có thể xử lý khác | Test binding qua proxy thực |

Với operation có **side effects** (ví dụ `PlaceOrder`), một Fault `Receiver`/`Server` không đủ để biết liệu server đã ghi dữ liệu hay chưa. Client nên sử dụng **idempotency key**, correlation ID, truy vấn trạng thái hoặc cơ chế xác nhận nghiệp vụ đã định nghĩa, thay vì retry vô hạn.

## 14. Kiểm thử SOAP Fault bằng Spring-WS

Không nên chỉ test `OrderService` ném exception, vì điều đó **không chứng minh** Spring-WS tạo Fault đúng QName/version/Detail. Phải kiểm thử trên **SOAP message thực tế**.

### 14.1. Kiểm thử phía server bằng `MockWebServiceClient`

Với một Spring test application context có endpoint và exception resolver:

~~~java
import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.serverOrReceiverFault;

import org.springframework.xml.transform.StringSource;
import org.springframework.ws.test.server.MockWebServiceClient;

String requestXml = """
    <ord:GetOrderRequest xmlns:ord="urn:example:orders:v1">
        <ord:orderId>ORD-1024</ord:orderId>
    </ord:GetOrderRequest>
    """;

MockWebServiceClient client =
        MockWebServiceClient.createClient(applicationContext);

client.sendRequest(withPayload(new StringSource(requestXml)))
      .andExpect(serverOrReceiverFault());
~~~

Đây là **ví dụ minh họa** cho trường hợp service stub/fixture ném lỗi phía server. Method matcher cụ thể và overload có thể phụ thuộc phiên bản Spring-WS Test; cần xác nhận API trên dependency dự án. Java text block yêu cầu Java 15+. Với lỗi input `Client/Sender`, hãy chọn matcher tương ứng, không khẳng định mọi exception đều là lỗi server.

Khi muốn kiểm tra **Fault detail**, hãy bổ sung assertion namespace-aware trên SOAP Body và phần XML detail, không chỉ kiểm tra có một Fault. Một Fault có `Code` đúng nhưng thiếu `ord:OrderNotFoundFault` vẫn có thể vi phạm hợp đồng WSDL.

### 14.2. Ma trận kiểm thử bắt buộc

| Nhóm | Input/điều kiện | Kỳ vọng |
| --- | --- | --- |
| SOAP 1.1 input invalid | Thiếu `orderId`, validation bật | `faultcode` thuộc nhóm lỗi phù hợp; `faultstring` và detail theo contract |
| SOAP 1.2 input invalid | Cùng request, SOAP 1.2 binding | `env:Code/env:Value` là `env:Sender`; `Reason` chứa `Text xml:lang` |
| Order không tồn tại | `ORD-1024` không tìm được | Detail QName `ord:OrderNotFoundFault`, `errorCode` ổn định |
| Lỗi hệ thống | DB unavailable | Server/Receiver Fault; không lộ stack trace |
| SOAP version mismatch | Envelope 1.2 gửi tới stack chỉ 1.1 | Xử lý lỗi phiên bản theo khả năng SOAP stack |
| MustUnderstand | Header bắt buộc nhắm node không được hiểu | MustUnderstand Fault theo version |
| WS-Security | Chữ ký/token/timestamp không hợp lệ | Bị từ chối, không gọi nghiệp vụ, Fault theo security policy |
| Không được quyền | Caller không được xem order | Fault đã chuẩn hóa, không lộ dữ liệu tenant khác |
| HTTP proxy error | Gateway trả 502 | Client không giả định có SOAP Fault |
| Localized Reason | SOAP 1.2 `vi` và `en` | Client không dựa vào câu chữ |
| Schema detail invalid | `errorCode` thiếu/namespace sai | Test từ chối hoặc phát hiện response không hợp contract |
| Compatibility | Java/.NET/ESB dùng WSDL công bố | Đọc được Fault code và typed detail như nhau |

### 14.3. Kiểm thử SOAP client bằng `MockWebServiceServer`

`MockWebServiceServer` phù hợp kiểm tra phía `WebServiceTemplate`: client gửi XML đúng, nhận SOAP Fault từ fixture và phân loại exception. Hãy test riêng:

- SOAP Fault hợp lệ trong SOAP 1.1/1.2.
- Typed detail `OrderNotFoundFault` theo QName đã công bố.
- HTTP transport error không phải SOAP Fault.
- Fault không có detail hoặc detail không biết trước: client xử lý fallback an toàn.
- Retry/idempotency khi operation có thể đã thực hiện tác dụng phụ.

**Đừng nhầm hai công cụ:** `MockWebServiceClient` kiểm tra endpoint server; `MockWebServiceServer` kiểm tra phía SOAP client. Cả hai đều không thay thế kiểm thử thật qua proxy/TLS, certificate và WS-Security policy.

## 15. Chẩn đoán lỗi khi client nói “không hiểu Fault”

| Triệu chứng | Nguyên nhân khả dĩ | Cách xác minh |
| --- | --- | --- |
| Client không parse được Fault | SOAP 1.1/1.2 namespace hoặc cấu trúc bị trộn | So Envelope/Fault child QNames |
| Server trả `<faultcode>` trong SOAP 1.2 | Dùng schema 1.1 cho SOAP 1.2 | Phải dùng `env:Code/env:Value` |
| Server trả `<env:Detail>` trong SOAP 1.1 | Dùng wrapper SOAP 1.2 sai version | SOAP 1.1 dùng `detail` không namespace |
| Client báo Fault không có code | Thiếu `faultcode` hoặc `env:Code`, SOAP Body không hợp SOAP | Validate cấu trúc SOAP |
| Client không đọc được typed detail | Sai QName, thứ tự trường, namespace hoặc WSDL part | So global XSD element + actual XML |
| Server trả Reason tiếng Việt rồi client không phân loại được | Client so `faultstring` thay cho machine code | Dùng Code/Subcode/errorCode |
| Fault có stack trace | Resolver công khai nội bộ | Lọc thông điệp, tùy chỉnh exception mapping |
| Nhận HTTP 502 nhưng không có Fault | Proxy/gateway lỗi, backend chưa tạo SOAP response | Quan sát HTTP và gateway logs |
| Fault báo MustUnderstand dù Header tồn tại | SOAP node đích chưa xử lý mandatory header | Kiểm actor/role, mustUnderstand, interceptor |
| SOAP Fault phát ra nhưng client timeout | Kết nối/truyền tải fail sau khi tạo response | Kiểm transport log, idempotency/status |
| XSD request hợp lệ nhưng security Fault | Chữ ký/identity/timestamp sai | Xem policy và audit đã lọc |
| Fault đúng code nhưng thiếu response header | Exception xảy ra trước interceptor bổ sung Header | Kiểm nhánh error/response lifecycle |

### Quy trình phân lớp nguyên nhân

~~~mermaid
flowchart TD
    A["Client nhận lỗi"] --> B{"Có HTTP response?"}
    B -->|Không| C["TLS / timeout / network"]
    B -->|Có| D{"Body có SOAP Envelope hợp lệ?"}
    D -->|Không| E["Proxy / HTTP error / Content-Type"]
    D -->|Có| F{"SOAP version đúng binding?"}
    F -->|Không| G["Message factory / WSDL binding"]
    F -->|Có| H{"SOAP Body chứa Fault?"}
    H -->|Không| I["Kiểm normal response / transport"]
    H -->|Có| J{"Code và Reason hợp cấu trúc?"}
    J -->|Không| K["Sửa Fault serializer/mapper"]
    J -->|Có| L{"Detail QName và XSD đúng?"}
    L -->|Không| M["Sửa typed Fault contract"]
    L -->|Có| N["Kiểm chính sách client/fallback/retry"]
~~~

Khi xử lý sự cố, hãy ghi **QName của Fault**, SOAP version, mã máy, correlation ID đã được lọc và HTTP status. Không dump toàn bộ security Header, private keys, chứng chỉ nhạy cảm hoặc raw payload chứa PII.

## 16. Những sai lầm cần tránh

1. **Ném exception Java và kỳ vọng client tự đọc được như SOAP Fault.** Phải có exception resolver/soap stack tạo Fault đúng format.
2. **Xem HTTP 500 là đủ.** SOAP client cần SOAP Body đúng giao thức để hiểu lỗi; HTTP 500 do proxy có thể không có Fault.
3. **Trộn phần tử SOAP 1.1 và 1.2.** `faultstring` không thay thế `env:Reason`; `detail` không phải `env:Detail`.
4. **Dùng `faultstring` làm mã lỗi ổn định.** Text có thể được bản địa hóa hoặc sửa câu chữ.
5. **Để lộ stack trace và SQL trong detail.** Chỉ đưa dữ liệu an toàn, có ích theo XSD/WSDL.
6. **Suy ra mọi lỗi là `Client/Sender`.** Lỗi database/response marshalling cần phân loại khác.
7. **Suy ra SOAP 1.2 Subcode tự sinh từ exception class.** Phải công bố taxonomy và cấu hình tạo Subcode.
8. **Coi `MustUnderstand` là lỗi business field.** Nó liên quan đến SOAP Header targeting/processing.
9. **Bật XSD validation rồi cho rằng mọi Fault detail tự hợp schema.** Phải test và nếu cần, validate XML detail outbound riêng.
10. **Retry không giới hạn với Fault `Receiver/Server`.** Cần biết có side effect xảy ra chưa và có idempotency policy không.
11. **Xử lý security Fault như lỗi nhập liệu thông thường.** Không bỏ qua xác minh token/chữ ký hoặc trả quá nhiều thông tin về security internals.
12. **Chỉ test Java method, không test SOAP XML.** Contract thực nằm ở QName, binding và message trên dây.

## 17. Bài thực hành tự đánh giá

### Bài A — Đọc cấu trúc SOAP 1.1

Cho một SOAP 1.1 `Fault` có `faultcode=soapenv:Client`, `faultstring="Đơn hàng không tồn tại"` và `detail` chứa `ord:OrderNotFoundFault`. Hãy chỉ ra namespace của từng phần tử, QName của faultcode và phần dữ liệu client nên dùng để phân loại lỗi.

### Bài B — Chuyển cấu trúc thành SOAP 1.2

Từ SOAP 1.1 Fault ở bài A, hãy thiết kế SOAP 1.2 Fault:

- `env:Code/env:Value=env:Sender`.
- `env:Subcode/env:Value=ord:OrderNotFound`.
- `env:Reason` có `Text` tiếng Việt và tiếng Anh với `xml:lang`.
- `env:Detail` giữ nguyên `ord:OrderNotFoundFault` theo XSD.

Giải thích vì sao không thể chỉ đổi `soapenv` thành `env`.

### Bài C — Định nghĩa typed Fault trong WSDL

Viết `wsdl:message` và `wsdl:fault` cho `OrderNotFoundFault`, tham chiếu global element XSD. Tạo một SOAP 1.1 binding fault `use="literal"` và giải thích cách client từ WSDL có thể sinh kiểu dữ liệu của lỗi.

### Bài D — Cấu hình Spring-WS

Tạo một `@SoapFault` exception cho lỗi request không hợp lệ và một `SoapFaultMappingExceptionResolver` có fallback lỗi server. Kiểm thử bằng `MockWebServiceClient` để xác nhận Fault code thực sự đúng phiên bản SOAP được dùng. Khi cần `Detail` động, hãy thiết kế custom exception resolver/binding thay vì trả `ex.getMessage()`.

### Bài E — Security và lỗi transport

So sánh ba trường hợp: SOAP Header có `mustUnderstand` nhưng không được node đích xử lý; signature WS-Security không hợp lệ; và TLS handshake thất bại. Tình huống nào có thể tạo SOAP Fault, tình huống nào không đi đến Spring-WS SOAP processing?

### Bài F — Interoperability và retry

Cho một SOAP `PlaceOrder` bị timeout sau khi server có thể đã ghi đơn. Giải thích vì sao chỉ thấy Fault `Receiver` hoặc lỗi transport không đủ quyết định retry. Đề xuất idempotency key, truy vấn trạng thái và cách client phân biệt lỗi an toàn.

## 18. Checklist khi công bố SOAP Fault

| Hạng mục | Điều kiện hoàn thành |
| --- | --- |
| **Version** | SOAP 1.1 và/hoặc SOAP 1.2 được quyết định rõ trong WSDL/binding |
| **Fault structure** | SOAP 1.1 có `faultcode`/`faultstring`; SOAP 1.2 có `Code`/`Reason` |
| **QName** | Mã lỗi chuẩn, Subcode, detail element có namespace đúng |
| **Detail** | Typed XML detail theo XSD, không tiết lộ stack trace/bí mật |
| **WSDL** | `wsdl:fault`/`soap:fault` khi công bố lỗi nghiệp vụ |
| **Spring-WS** | Exception resolver/annotation/interceptor được cấu hình và kiểm thử |
| **Validation** | Request và response hợp đồng; Fault detail được kiểm tra theo schema khi cần |
| **Security** | WS-Security faults không lộ certificate/token/secret; không bỏ qua xác minh |
| **HTTP** | Kiểm tra status + Content-Type + SOAP Body qua proxy thực tế |
| **Client** | Phân loại bằng QName/errorCode, không parse faultstring/Reason |
| **Retry** | Có quy tắc idempotency và recovery cho operation có side effect |
| **Interoperability** | Test Java/.NET/ESB, SOAP 1.1/1.2, typed detail, lỗi transport |

**Kết luận:** **SOAP Fault** là phần tử lỗi chuẩn trong **SOAP Body**, nhưng **cấu trúc SOAP 1.1 và SOAP 1.2 không giống nhau**. SOAP 1.1 dùng `faultcode`, `faultstring`, `faultactor` và `detail`; SOAP 1.2 dùng `Code` (có thể có `Subcode`), `Reason`, `Node`, `Role` và `Detail`. Trong dịch vụ **SPRING_WEB_SERVICES** contract-first, hãy công bố lỗi nghiệp vụ bằng XSD/WSDL, cấu hình Spring-WS resolver/interceptor để tạo Fault đúng phiên bản, không tiết lộ thông tin nhạy cảm, và kiểm thử cả SOAP response lẫn HTTP/WS-Security qua client độc lập. **Mã lỗi máy đọc và dữ liệu detail có hợp đồng mới là nền tảng xử lý tự động ổn định**, còn `faultstring`/`Reason` giúp con người hiểu sự cố.
