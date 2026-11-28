# SOAP 1.1 và SOAP 1.2: namespace, kiểu nội dung và cách biểu diễn lỗi

## Mục tiêu bài học

SOAP (Simple Object Access Protocol) là giao thức nhắn tin dựa trên XML, thường dùng trong tích hợp hệ thống doanh nghiệp. Với Spring Web Services (Spring-WS), lựa chọn **SOAP 1.1** hay **SOAP 1.2** ảnh hưởng trực tiếp đến cách xây dựng HTTP request/response, namespace của Envelope, kiểu nội dung HTTP và cấu trúc SOAP Fault. Một XML payload nghiệp vụ có thể giống nhau ở cả hai phiên bản nhưng thông điệp SOAP bao ngoài lại khác, khiến client và server không tương thích nếu cấu hình sai.

Sau bài học, bạn có thể:

- Nhận biết phiên bản SOAP qua **namespace của Envelope**, không dựa vào prefix tùy ý.
- Phân biệt `text/xml`, `application/soap+xml`, `SOAPAction` header và tham số `action`.
- Đọc, xây dựng và phân loại SOAP Fault của hai phiên bản.
- Hiểu vai trò của `actor`/`role`, `mustUnderstand`, WSDL/XSD và cách cấu hình phiên bản trong Spring-WS.
- Thiết kế kiểm thử tương thích SOAP client/server theo hướng **contract-first**.

## 1. Hai phiên bản SOAP khác nhau ở đâu?

SOAP 1.1 và SOAP 1.2 cùng có ba thành phần quen thuộc: `Envelope` bao bọc thông điệp, `Header` tùy chọn cho metadata điều khiển, và `Body` chứa payload hoặc SOAP Fault. Tuy nhiên, **SOAP 1.2 là một phiên bản giao thức riêng**, có namespace và các quy tắc binding/processing được chuẩn hóa lại.

| Đặc điểm | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Envelope namespace | `http://schemas.xmlsoap.org/soap/envelope/` | `http://www.w3.org/2003/05/soap-envelope` |
| HTTP `Content-Type` thường dùng | `text/xml; charset=utf-8` | `application/soap+xml; charset=utf-8` |
| Thông tin hành động qua HTTP | Header `SOAPAction` trong SOAP 1.1 HTTP binding | Tham số `action` tùy chọn của `application/soap+xml`; không dùng quy tắc `SOAPAction` của SOAP 1.1 |
| Element biểu diễn lỗi | `env:Fault` chứa `faultcode`, `faultstring`, `faultactor`, `detail` | `env:Fault` chứa `env:Code`, `env:Reason`, tùy chọn `env:Node`, `env:Role`, `env:Detail` |
| Nhóm mã lỗi phía gửi/nhận | `Client`, `Server` | `Sender`, `Receiver` |
| Mã lỗi bổ sung | `VersionMismatch`, `MustUnderstand` | `VersionMismatch`, `MustUnderstand`, `DataEncodingUnknown` |
| Địa chỉ xử lý header | `actor` | `role`, bổ sung cơ chế `relay` |
| Chuỗi đa ngôn ngữ cho Fault | `faultstring`, có thể kèm `xml:lang` | `Reason` chứa một hoặc nhiều `Text xml:lang="..."` |
| HTTP status khi có lỗi SOAP | SOAP 1.1 HTTP binding quy định dùng HTTP 500 cho lỗi xử lý SOAP | HTTP binding của SOAP 1.2 phân biệt trường hợp tương ứng, thường HTTP 400 cho lỗi phía gửi và HTTP 500 cho lỗi phía nhận |

**Lưu ý:** Đây là những khác biệt tiêu biểu khi SOAP được truyền qua HTTP. SOAP là mô hình thông điệp; mỗi transport binding có những quy tắc riêng. Không được lấy một header HTTP cụ thể làm đặc điểm cố hữu cho mọi cách truyền SOAP.

## 2. Namespace của SOAP Envelope xác định phiên bản

Một XML namespace được nhận diện bằng **URI namespace**, còn tiền tố `soap`, `soapenv`, `s` hay `env` chỉ là tên viết tắt do tài liệu chọn. Ví dụ, `env:Envelope` và `s:Envelope` biểu diễn cùng một element nếu cả hai prefix đều trỏ đến cùng namespace URI.

### SOAP 1.1: Envelope namespace

~~~xml
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Header/>
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

### SOAP 1.2: Envelope namespace

~~~xml
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:v1">
    <env:Header/>
    <env:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

Cùng một payload nghiệp vụ `ord:GetOrderRequest` được giữ nguyên; thứ thay đổi là **namespace của các element SOAP** (`Envelope`, `Header`, `Body`). Đây là ví dụ rõ ràng cho việc cần tách **hợp đồng nghiệp vụ** (XSD) khỏi **giao thức bao bọc** (SOAP version/binding).

Trong hai ví dụ:

- `{http://schemas.xmlsoap.org/soap/envelope/}Envelope` là QName của Envelope SOAP 1.1.
- `{http://www.w3.org/2003/05/soap-envelope}Envelope` là QName của Envelope SOAP 1.2.
- `{urn:example:orders:v1}GetOrderRequest` là QName của payload nghiệp vụ, độc lập với namespace Envelope.

**Sai lầm thường gặp:** Chỉ thay tiền tố `soapenv:` thành `env:` rồi cho rằng đã chuyển SOAP 1.1 thành SOAP 1.2. Cách đó không thay đổi phiên bản. Phải thay **URI namespace Envelope** và các quy tắc truyền thông điệp đi kèm.

### Namespace của SOAP khác namespace của XSD/WSDL

Trong kiến trúc contract-first, XSD định nghĩa root element `GetOrderRequest`, kiểu dữ liệu và các ràng buộc của nó; WSDL mô tả operation, message, port và binding. Namespace `urn:example:orders:v1` của XSD không bắt buộc phải thay khi đổi phiên bản SOAP.

Đừng nhầm lẫn:

| Namespace | Mục đích |
|---|---|
| SOAP 1.1 Envelope: `http://schemas.xmlsoap.org/soap/envelope/` | Các element cấu trúc của thông điệp SOAP 1.1 |
| SOAP 1.2 Envelope: `http://www.w3.org/2003/05/soap-envelope` | Các element cấu trúc của thông điệp SOAP 1.2 |
| Ví dụ nghiệp vụ: `urn:example:orders:v1` | Request/response và kiểu dữ liệu do XSD của hệ thống định nghĩa |
| WSDL 1.1: `http://schemas.xmlsoap.org/wsdl/` | Ngôn ngữ mô tả dịch vụ; **số phiên bản WSDL không phải phiên bản SOAP** |
| WSDL 1.1 SOAP binding extension: `http://schemas.xmlsoap.org/wsdl/soap/` | Khai báo binding SOAP 1.1 trong WSDL 1.1 |
| WSDL 1.1 SOAP 1.2 binding extension thường dùng: `http://schemas.xmlsoap.org/wsdl/soap12/` | Khai báo binding SOAP 1.2 trong WSDL 1.1; khả năng hỗ trợ phụ thuộc công cụ |

WSDL 1.1 có thể được sử dụng với SOAP 1.2 thông qua extension tương ứng nếu công cụ và đối tác tích hợp hỗ trợ. Không được suy ra “WSDL 1.1 nghĩa là SOAP 1.1”.

## 3. HTTP Content-Type và cách chỉ định hành động

Bản thân SOAP thông báo cấu trúc XML, còn HTTP binding quyết định cách mang thông điệp qua HTTP. Đây là điểm dễ gây lỗi **HTTP 415 Unsupported Media Type**, lỗi không định tuyến được operation, hoặc lỗi phiên bản dù Body hoàn toàn đúng XSD.

### 3.1. SOAP 1.1: `text/xml` và HTTP `SOAPAction`

Ví dụ HTTP request SOAP 1.1:

~~~http
POST /services/orders HTTP/1.1
Host: api.example.test
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"

<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </soap:Body>
</soap:Envelope>
~~~

Trong SOAP 1.1 HTTP binding:

- Body được truyền đi dưới dạng XML và thường mang media type `text/xml`.
- Header HTTP `SOAPAction` cung cấp ý định của request và có thể được một số gateway/server dùng khi định tuyến.
- Theo SOAP 1.1 HTTP binding, client phải gửi header `SOAPAction` (giá trị có thể là URI được đặt trong dấu nháy kép, chuỗi rỗng `""`, hoặc trường hợp không có giá trị theo quy định binding). Hành vi kiểm tra thực tế của các server có thể khác nhau.
- **`SOAPAction` là HTTP header, không phải một element thuộc SOAP Body hay một namespace XML.**

Các trường hợp sau có thể có ý nghĩa khác nhau trong SOAP 1.1:

~~~http
SOAPAction: "urn:example:orders:v1/GetOrder"
SOAPAction: ""
SOAPAction:
~~~

Giá trị `""` cho biết ý định được chỉ ra bởi chính HTTP Request-URI; header không có giá trị chỉ ra không có dấu hiệu cho biết ý định. Trong thực tế, không nên tự thay đổi giá trị action nếu WSDL hoặc nhà cung cấp dịch vụ đã yêu cầu giá trị cụ thể.

### 3.2. SOAP 1.2: `application/soap+xml` và tham số `action`

Ví dụ SOAP 1.2 qua HTTP:

~~~http
POST /services/orders HTTP/1.1
Host: api.example.test
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1/GetOrder"

<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:v1">
    <env:Body>
        <ord:GetOrderRequest>
            <ord:orderId>ORD-1001</ord:orderId>
        </ord:GetOrderRequest>
    </env:Body>
</env:Envelope>
~~~

Media type `application/soap+xml` được định nghĩa cho SOAP 1.2. Tham số `action` trong `Content-Type` là **tùy chọn theo định nghĩa media type** và không phải cơ chế đồng nghĩa hoàn toàn với header `SOAPAction` của SOAP 1.1.

Điều cần phân biệt:

~~~http
# SOAP 1.1
Content-Type: text/xml; charset=utf-8
SOAPAction: "urn:example:orders:v1/GetOrder"

# SOAP 1.2
Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1/GetOrder"
~~~

Với SOAP 1.2, đừng mặc định thêm header `SOAPAction` kiểu SOAP 1.1. Hãy làm theo HTTP binding/WSDL và yêu cầu cụ thể của đối tác; nếu action được dùng, cần kiểm tra client có đặt đúng tham số media type hay không. **Giá trị `action` không quyết định phiên bản SOAP**: phiên bản vẫn được biểu diễn bằng namespace Envelope và quy tắc binding tương ứng.

### 3.3. Vì sao Content-Type quan trọng nếu XML giống nhau?

Một server được cấu hình nhận SOAP 1.2 có thể từ chối:

~~~http
Content-Type: text/xml; charset=utf-8
~~~

kể cả khi Body chứa `GetOrderRequest` hợp lệ theo XSD. Ngược lại, SOAP 1.1 endpoint có thể không chấp nhận `application/soap+xml`.

Một số lỗi có thể xuất hiện ở lớp HTTP/dispatcher **trước khi Spring-WS đến được `@Endpoint`**. Vì vậy, khi chẩn đoán, phải kiểm tra đủ ba lớp:

1. **HTTP:** `Content-Type`, `SOAPAction`/action, URL, mã trạng thái phản hồi.
2. **SOAP:** QName của `Envelope`, `Header`, `Body`, `Fault`.
3. **Nghiệp vụ:** QName và XSD của phần tử con đầu tiên trong `Body` (ví dụ `GetOrderRequest`).

## 4. SOAP Fault 1.1: các trường đơn giản

SOAP Fault là cách biểu diễn lỗi của giao thức SOAP. Trong SOAP 1.1, `Fault` là element đặc biệt nằm bên trong `Body`. Một ví dụ lỗi xác thực dữ liệu:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/xml; charset=utf-8

<soap:Envelope
    xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:v1">
    <soap:Body>
        <soap:Fault>
            <faultcode>soap:Client</faultcode>
            <faultstring xml:lang="vi">Mã đơn hàng không hợp lệ</faultstring>
            <detail>
                <ord:ValidationError>
                    <ord:field>orderId</ord:field>
                    <ord:message>Không tìm thấy đơn hàng</ord:message>
                </ord:ValidationError>
            </detail>
        </soap:Fault>
    </soap:Body>
</soap:Envelope>
~~~

Bốn trường chính:

| Trường | Bắt buộc? | Ý nghĩa |
|---|---|---|
| `faultcode` | Có | QName mô tả loại lỗi, chẳng hạn `soap:Client` hoặc `soap:Server` |
| `faultstring` | Có | Mô tả lỗi để con người đọc; có thể dùng `xml:lang` |
| `faultactor` | Không | URI xác định nút SOAP gây lỗi trong một đường xử lý có nhiều nút |
| `detail` | Có điều kiện | Chi tiết lỗi liên quan đến xử lý `Body`; khi nội dung Body không được xử lý thành công, `detail` phải hiện diện theo quy định SOAP 1.1 |

Các mã lỗi chuẩn của SOAP 1.1:

- `VersionMismatch`: namespace Envelope không phù hợp phiên bản SOAP mà nút xử lý nhận.
- `MustUnderstand`: một header được đánh dấu bắt buộc hiểu nhưng nút nhận không xử lý được.
- `Client`: thông điệp có vấn đề thuộc về phía gửi; ví dụ cấu trúc hoặc thông tin không đáp ứng yêu cầu.
- `Server`: lỗi do phía xử lý; ví dụ phụ thuộc hệ thống không sẵn sàng.

Chú ý `soap:Client` là một **QName**, vì prefix `soap` được liên kết với namespace SOAP 1.1. Kết hợp `faultcode` với chi tiết nghiệp vụ giúp phía gọi phân biệt lỗi dữ liệu có thể sửa với lỗi hệ thống cần xử lý lại.

Trong SOAP 1.1 qua HTTP, khi có lỗi xử lý SOAP, HTTP binding yêu cầu trả HTTP 500 cùng SOAP Fault. Tuy nhiên, với hệ thống tích hợp thực tế, cần đọc **cả HTTP status lẫn nội dung Fault** vì gateway, proxy hoặc implementation có thể có hành vi riêng; HTTP 500 cũng có thể là một lỗi HTML không phải SOAP Fault.

## 5. SOAP Fault 1.2: cấu trúc tường minh và có thể mở rộng

SOAP 1.2 thay đổi tên và cấu trúc các trường lỗi, dùng element nằm trong namespace SOAP 1.2. Cùng một lỗi dữ liệu có thể được biểu diễn như sau:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/soap+xml; charset=utf-8

<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:v1">
    <env:Body>
        <env:Fault>
            <env:Code>
                <env:Value>env:Sender</env:Value>
                <env:Subcode>
                    <env:Value>ord:InvalidOrder</env:Value>
                </env:Subcode>
            </env:Code>
            <env:Reason>
                <env:Text xml:lang="vi">Mã đơn hàng không hợp lệ</env:Text>
            </env:Reason>
            <env:Detail>
                <ord:ValidationError>
                    <ord:field>orderId</ord:field>
                    <ord:message>Không tìm thấy đơn hàng</ord:message>
                </ord:ValidationError>
            </env:Detail>
        </env:Fault>
    </env:Body>
</env:Envelope>
~~~

Trong SOAP 1.2, `Code` và `Reason` là hai thành phần **bắt buộc** của Fault. Những thành phần sau có cấu trúc rõ ràng hơn:

| Thành phần | Ý nghĩa |
|---|---|
| `env:Code/env:Value` | Mã lỗi chính dạng QName; thường là `env:Sender` hoặc `env:Receiver` |
| `env:Code/env:Subcode` | Mã lỗi chi tiết hơn, có thể lồng nhiều cấp theo định nghĩa SOAP 1.2 |
| `env:Reason/env:Text` | Mô tả dễ đọc; mỗi `Text` phải có `xml:lang`, có thể có nhiều ngôn ngữ |
| `env:Node` | URI nhận dạng nút SOAP nơi lỗi xuất hiện |
| `env:Role` | Vai trò của nút SOAP trong lúc xảy ra lỗi |
| `env:Detail` | Nội dung chi tiết dạng XML ứng dụng |

SOAP 1.2 quy định các mã Fault chính sau:

- `env:VersionMismatch`: không nhận được phiên bản Envelope phù hợp.
- `env:MustUnderstand`: không xử lý được một header bắt buộc mà nút hiện tại phải hiểu.
- `env:DataEncodingUnknown`: gặp giá trị `encodingStyle` bắt buộc hiểu nhưng không hỗ trợ.
- `env:Sender`: thông điệp sai hoặc thiếu thông tin cần thiết; phía gửi thường phải sửa request.
- `env:Receiver`: lỗi ở phía nhận hoặc quá trình xử lý, không nhất thiết cần sửa nội dung request.

Ví dụ SOAP 1.2 cho một sự cố backend:

~~~xml
<env:Fault xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Code>
        <env:Value>env:Receiver</env:Value>
    </env:Code>
    <env:Reason>
        <env:Text xml:lang="vi">Không thể xử lý đơn hàng lúc này</env:Text>
        <env:Text xml:lang="en">Order service is temporarily unavailable</env:Text>
    </env:Reason>
</env:Fault>
~~~

Với một endpoint SOAP 1.2 qua HTTP, lỗi `Sender` thường gắn với HTTP 400; lỗi `Receiver` thường gắn với HTTP 500 theo binding. Các lỗi tầng HTTP như sai media type, xác thực, proxy hoặc kết nối có thể tạo phản hồi không phải SOAP Fault, nên không được giả định mọi HTTP 4xx/5xx đều có `env:Fault`.

### 5.1. Đối chiếu Fault 1.1 và 1.2

| Nhu cầu | SOAP 1.1 | SOAP 1.2 |
|---|---|---|
| Lỗi do request không hợp lệ | `soap:Client` | `env:Sender` |
| Lỗi phía xử lý | `soap:Server` | `env:Receiver` |
| Mô tả dễ đọc | `faultstring` | `env:Reason/env:Text` |
| Lỗi chi tiết cho client | `detail` | `env:Detail` |
| Lỗi phân cấp/mã nghiệp vụ | Có thể tạo QName mã riêng hoặc khai thác `detail` | `env:Subcode` lồng nhau và `env:Detail` |
| Nút gây lỗi | `faultactor` | `env:Node` và `env:Role` |
| Khả năng đa ngôn ngữ | `faultstring` với `xml:lang` | Nhiều `env:Text` với `xml:lang` tương ứng |

SOAP 1.2 Fault **không chỉ đổi tên** `faultcode` thành `Code`: nó tạo cấu trúc lồng nhau và ràng buộc khác. Một client chỉ biết tìm `faultstring` hoặc `detail` theo cấu trúc SOAP 1.1 có thể không đọc được Fault SOAP 1.2.

### 5.2. Chi tiết lỗi nên là hợp đồng ổn định

Với service contract-first, hãy thiết kế payload lỗi nghiệp vụ `ord:ValidationError` trong XSD, gồm mã lỗi, trường vi phạm và thông điệp phù hợp. Phần này có thể được giữ nhất quán qua các phiên bản SOAP, dù **wrapper Fault** khác nhau.

Chẳng hạn:

~~~xml
<ord:ValidationError xmlns:ord="urn:example:orders:v1">
    <ord:code>ORDER_NOT_FOUND</ord:code>
    <ord:field>orderId</ord:field>
    <ord:message>Không tìm thấy đơn hàng</ord:message>
</ord:ValidationError>
~~~

Không gửi stack trace, đường dẫn nội bộ, access token, thông tin chứng chỉ hay chi tiết hệ thống nhạy cảm trong Fault trả cho client. Với lỗi bảo mật như chữ ký không hợp lệ hoặc thiếu WS-Security token, mã lỗi và nội dung phản hồi còn cần tuân theo đặc tả WS-Security và chính sách tích hợp tương ứng.

## 6. Header xử lý bắt buộc: `actor`, `role`, `mustUnderstand`

SOAP không chỉ bao bọc Body. Trong tích hợp doanh nghiệp, Header thường mang correlation ID, thông tin định tuyến hoặc WS-Security. SOAP có quy tắc chỉ rõ **nút nào phải xử lý header** và xử lý ra sao nếu không hiểu.

### SOAP 1.1

~~~xml
<soap:Header xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"
             xmlns:sec="urn:example:security:v1">
    <sec:SecurityInfo soap:mustUnderstand="1">
        <sec:requestId>req-009</sec:requestId>
    </sec:SecurityInfo>
</soap:Header>
~~~

Trong SOAP 1.1, `actor` có thể được dùng để xác định nút SOAP mục tiêu. Nếu không có `actor`, header hướng tới điểm nhận cuối cùng theo mô hình xử lý của SOAP 1.1. `mustUnderstand="1"` có nghĩa nút nhận được nhắm tới phải hiểu và xử lý header theo quy tắc; nếu không, phải phát sinh Fault `MustUnderstand`.

### SOAP 1.2

~~~xml
<env:Header
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:sec="urn:example:security:v1">
    <sec:SecurityInfo
        env:mustUnderstand="true"
        env:role="http://www.w3.org/2003/05/soap-envelope/role/ultimateReceiver">
        <sec:requestId>req-009</sec:requestId>
    </sec:SecurityInfo>
</env:Header>
~~~

SOAP 1.2 dùng `role` thay cho `actor`, có thêm `relay` để quy định cách chuyển tiếp header chưa được xử lý trong một số tình huống. Giá trị boolean cho `mustUnderstand` có thể dùng `true`/`false` hoặc `1`/`0` theo kiểu XML Schema boolean của SOAP 1.2.

**Đừng sao chép nguyên header 1.1 sang 1.2.** Nếu Header được ký số theo WS-Security/XML Signature, thay namespace, vị trí node hoặc nội dung cũng có thể ảnh hưởng chữ ký. Cần cấu hình và kiểm thử lại cả SOAP processing lẫn XML security khi đổi version.

## 7. SOAP version, WSDL và Spring Web Services

Spring-WS là framework xây SOAP service tập trung vào XML payload và hợp đồng XSD/WSDL. Một endpoint thông thường định tuyến dựa trên **QName của payload đầu tiên trong Body**, trong khi việc chấp nhận SOAP 1.1 hay SOAP 1.2 phụ thuộc vào SOAP message factory, cấu hình transport và binding được công bố.

~~~mermaid
flowchart TD
    A["HTTP request"] --> B{"Content-Type phù hợp?"}
    B -- "Không" --> X["Lỗi tầng HTTP / media type"]
    B -- "Có" --> C{"Envelope namespace / SOAP version đúng?"}
    C -- "Không" --> Y["Lỗi version hoặc bị từ chối khi parse"]
    C -- "Có" --> D["Xử lý Header và mustUnderstand"]
    D --> E["Đọc Body, xác định QName payload"]
    E --> F["XSD validation nếu bật"]
    F --> G["Spring-WS @Endpoint"]
    G --> H["Response hoặc SOAP Fault đúng version"]
~~~

Sơ đồ thể hiện các điểm quyết định quan trọng; thứ tự kiểm tra chi tiết tùy stack và cấu hình triển khai. Ví dụ, implementation có thể từ chối Content-Type trước khi đọc XML.

### 7.1. Chọn SOAP version cho SAAJ message factory

Với ứng dụng Spring-WS dùng `SaajSoapMessageFactory`, có thể cấu hình phiên bản SOAP được tạo/đọc:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.soap.SoapVersion;
import org.springframework.ws.soap.saaj.SaajSoapMessageFactory;

@Configuration
@EnableWs
public class SoapWebServiceConfig {

    @Bean(name = "messageFactory")
    public SaajSoapMessageFactory messageFactory() {
        SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
        factory.setSoapVersion(SoapVersion.SOAP_12);
        return factory;
    }
}
~~~

Ví dụ trên minh họa cấu hình **SOAP 1.2** trong một ứng dụng Spring-WS tương thích. Nếu cần SOAP 1.1, dùng `SoapVersion.SOAP_11` và công bố binding 1.1 phù hợp. Ở các dự án khác phiên bản thư viện/SAAJ, cách khởi tạo message factory và cấu hình servlet có thể cần điều chỉnh; nên xác nhận qua integration test.

Không có nghĩa chỉ đổi một dòng cấu hình là đã hoàn thành chuyển đổi giao thức. Client, server, WSDL và thành phần trung gian phải cùng thống nhất phiên bản.

### 7.2. WSDL binding phải phù hợp phiên bản

Trong WSDL 1.1, `soap:binding` thường chỉ binding SOAP 1.1, còn `soap12:binding` trong extension tương ứng có thể chỉ SOAP 1.2:

~~~xml
<!-- Trích đoạn WSDL 1.1: minh họa SOAP 1.1 binding -->
<wsdl:binding name="OrderSoap11Binding" type="tns:OrderPortType"
              xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
              xmlns:tns="urn:example:orders:v1"
              xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/">
    <soap:binding style="document"
                  transport="http://schemas.xmlsoap.org/soap/http"/>
    <!-- wsdl:operation và soap:operation/soap:body tương ứng -->
</wsdl:binding>

<!-- Trích đoạn WSDL 1.1: minh họa SOAP 1.2 binding extension -->
<wsdl:binding name="OrderSoap12Binding" type="tns:OrderPortType"
              xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
              xmlns:tns="urn:example:orders:v1"
              xmlns:soap12="http://schemas.xmlsoap.org/wsdl/soap12/">
    <soap12:binding style="document"
                    transport="http://schemas.xmlsoap.org/soap/http"/>
    <!-- wsdl:operation và soap12:operation/soap12:body tương ứng -->
</wsdl:binding>
~~~

Hai đoạn chỉ minh họa điểm phân biệt namespace binding; **chưa phải WSDL hoàn chỉnh**. Trong một WSDL thực tế cần đầy đủ `types`, `message`, `portType`, `binding`, `service` và operation/input/output phù hợp.

Khi tạo WSDL từ XSD bằng Spring-WS hoặc công bố WSDL viết sẵn, cần kiểm tra:

- SOAP version được khai báo ở **binding/port** có trùng cấu hình runtime không.
- Namespace và tên phần tử request/response có khớp XSD không.
- Action URI, endpoint address và document/literal style có phù hợp với client được yêu cầu hỗ trợ không.
- Công cụ sinh client (JAX-WS, .NET/WCF hoặc sản phẩm tích hợp khác) có thực sự hỗ trợ SOAP 1.2 binding extension đang dùng không.

**Document/literal** là lựa chọn phổ biến với contract-first, giúp payload mô tả rõ bằng XSD. Nó là một kiểu cách biểu diễn và binding, **không phải tên gọi khác của SOAP 1.1 hay SOAP 1.2**.

### 7.3. Endpoint định tuyến theo QName payload

Ví dụ endpoint xử lý `GetOrderRequest`:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class GetOrderEndpoint {

    private static final String NAMESPACE = "urn:example:orders:v1";
    private final OrderService orderService;

    public GetOrderEndpoint(OrderService orderService) {
        this.orderService = orderService;
    }

    @PayloadRoot(namespace = NAMESPACE, localPart = "GetOrderRequest")
    @ResponsePayload
    public GetOrderResponse getOrder(@RequestPayload GetOrderRequest request) {
        return orderService.getOrder(request);
    }
}
~~~

Đây là mã minh họa giả định `GetOrderRequest` và `GetOrderResponse` đã được tạo/ánh xạ bởi JAXB và cấu hình marshalling phù hợp. Việc định tuyến bằng `@PayloadRoot` chỉ xét QName payload, vì vậy **không tự phát hiện hoặc sửa lỗi SOAP version**. Sai Content-Type hay Envelope namespace có thể khiến request bị từ chối trước khi endpoint nhận được.

### 7.4. Ánh xạ exception sang SOAP Fault

Spring-WS cung cấp cơ chế exception resolver để đổi exception thành SOAP Fault. Chẳng hạn, một exception nghiệp vụ được đánh dấu:

~~~java
import org.springframework.ws.soap.server.endpoint.annotation.FaultCode;
import org.springframework.ws.soap.server.endpoint.annotation.SoapFault;

@SoapFault(
    faultCode = FaultCode.CLIENT,
    faultStringOrReason = "Yêu cầu đơn hàng không hợp lệ"
)
public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String message) {
        super(message);
    }
}
~~~

Khi `SoapFaultAnnotationExceptionResolver` được đăng ký và xử lý exception này, framework có thể tạo mã lỗi phía gửi tương ứng với phiên bản SOAP của message, chẳng hạn `Client` (SOAP 1.1) hoặc `Sender` (SOAP 1.2). Cần cấu hình riêng nếu muốn payload `detail`/`Detail` có cấu trúc lỗi nghiệp vụ; annotation chỉ minh họa cách chọn mã và thông điệp Fault cơ bản.

Đối với lỗi hạ tầng, nên chọn lỗi phía nhận (`Server`/`Receiver`) và thông điệp an toàn cho client. Không nên trả lỗi nghiệp vụ dạng HTTP 200 cộng một payload thành công giả, vì như vậy làm client khó phân biệt kết quả thật và lỗi.

### 7.5. SOAP client phải dùng factory và headers phù hợp

Một client Spring-WS dùng `WebServiceTemplate` cần marshal/unmarshal XML theo JAXB binding, đồng thời gửi SOAP version đúng:

~~~java
SaajSoapMessageFactory factory = new SaajSoapMessageFactory();
factory.setSoapVersion(SoapVersion.SOAP_12);
factory.afterPropertiesSet();

WebServiceTemplate template = new WebServiceTemplate(factory);
template.setMarshaller(jaxbMarshaller);
template.setUnmarshaller(jaxbMarshaller);

Object response = template.marshalSendAndReceive(
    "https://api.example.test/services/orders",
    getOrderRequest
);
~~~

Ví dụ giả định `jaxbMarshaller` đã được cấu hình và `getOrderRequest` là object/JAXB element có thể marshal. Đối với SOAP 1.1, một service có yêu cầu `SOAPAction` cụ thể có thể dùng callback:

~~~java
Object response = template.marshalSendAndReceive(
    "https://api.example.test/services/orders",
    getOrderRequest,
    new SoapActionCallback("urn:example:orders:v1/GetOrder")
);
~~~

Đoạn thứ hai áp dụng trong ngữ cảnh client đã cấu hình SOAP 1.1 message factory và import callback Spring-WS tương ứng. Với SOAP 1.2, phải đối chiếu cách SOAP library/transport tạo tham số `action` trong media type theo WSDL và yêu cầu đối tác, không sao chép máy móc quy tắc header `SOAPAction` của SOAP 1.1.

## 8. Tình huống chẩn đoán lỗi tích hợp

### Tình huống A: SOAP Body hợp XSD nhưng server trả HTTP 415

**Hiện tượng:** Request gửi `GetOrderRequest` đúng cấu trúc nghiệp vụ nhưng server báo unsupported media type.

**Kiểm tra:** So sánh phiên bản contract mà endpoint công bố với `Content-Type` thực tế. Nếu server chỉ nhận SOAP 1.2 nhưng client đang gửi `text/xml`, cần chuyển sang `application/soap+xml` và dùng Envelope SOAP 1.2 tương ứng.

**Điểm học:** XSD validation thành công (nếu thử riêng payload) chưa chứng minh được SOAP/HTTP request hợp lệ.

### Tình huống B: Client đã đổi `Content-Type` nhưng vẫn bị VersionMismatch

**Hiện tượng:** HTTP header ghi `application/soap+xml`, nhưng XML vẫn chứa:

~~~xml
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
~~~

**Nguyên nhân:** Envelope namespace vẫn thuộc SOAP 1.1. Cần tạo lại SOAP message đúng phiên bản, bao gồm `Envelope`, `Header`, `Body` và cơ chế Fault.

### Tình huống C: SOAP 1.2 server trả lỗi nhưng client tìm `faultstring`

**Hiện tượng:** Client không đọc được nội dung lỗi vì chỉ trích xuất `/Envelope/Body/Fault/faultstring`.

**Nguyên nhân:** SOAP 1.2 dùng `env:Reason/env:Text`, không có `faultstring` kiểu SOAP 1.1. Cần dùng SOAP library hiểu version hoặc parser chọn biểu thức XPath/QName theo namespace phù hợp.

### Tình huống D: Request có WS-Security Header và xuất hiện MustUnderstand

**Hiện tượng:** Server trả Fault `MustUnderstand`.

**Kiểm tra:** Header nào được gắn `mustUnderstand`, role/actor nhắm đến nút nào, interceptor WS-Security đã được bật chưa và phiên bản Envelope có khớp pipeline bảo mật không. Nếu ký số, cần kiểm tra việc canonicalize và validate XML Signature cùng với chứng chỉ/trust configuration của đối tác.

**Điểm học:** Một SOAP endpoint có thể parse Body hoàn toàn đúng mà vẫn phải từ chối thông điệp vì header bắt buộc không được xử lý.

### Tình huống E: SOAP Fault bị proxy thay bằng trang HTML

**Hiện tượng:** Client nhận HTTP 500 và HTML body thay vì một `soap:Fault`/`env:Fault`.

**Nguyên nhân có thể:** Reverse proxy, load balancer, web server hoặc servlet container trả lỗi trước khi SOAP stack xây Fault. Cần kiểm tra status, `Content-Type`, mã phản hồi thực tế và log phía hạ tầng. Không thể ép parser SOAP đọc HTML như SOAP Fault.

## 9. Kiểm thử tương thích SOAP 1.1/1.2

Một bộ kiểm thử hữu ích nên gồm cả **success path**, **fault path** và **lỗi kết hợp version/header**. Đừng chỉ kiểm tra Java endpoint bằng unit test; cần gửi và nhận HTTP message như một hệ thống ngoài.

| Ca kiểm thử | Request | Kỳ vọng |
|---|---|---|
| Thành công SOAP 1.1 | Envelope 1.1, `text/xml`, SOAPAction phù hợp | SOAP response 1.1 và payload đúng XSD nếu dịch vụ hỗ trợ 1.1 |
| Thành công SOAP 1.2 | Envelope 1.2, `application/soap+xml` | SOAP response 1.2 và payload đúng XSD nếu dịch vụ hỗ trợ 1.2 |
| Sai media type | Envelope 1.2 nhưng `text/xml` | Bị từ chối hoặc báo lỗi tương ứng; không coi là success |
| Sai namespace Envelope | SOAP 1.1 namespace trên endpoint chỉ nhận 1.2 | Bị từ chối/VersionMismatch theo cách xử lý của stack |
| Lỗi dữ liệu | Gửi orderId không hợp lệ | SOAP Fault tương ứng, có code, reason và detail nhất quán |
| Lỗi backend | Giả lập dependency không sẵn sàng | SOAP Fault phía nhận; không lộ stack trace/credential |
| Header không được hiểu | Header nhắm tới endpoint, `mustUnderstand` bật nhưng không có handler | Fault `MustUnderstand` |
| Kiểm tra QName | Đổi prefix nhưng giữ namespace | Hành vi không đổi khi QName không đổi |
| Client độc lập | Client .NET hoặc client SOAP khác Java | Gửi/nhận được thông điệp và giải mã Fault đúng |
| WSDL compatibility | Sinh client từ WSDL công bố | Binding và operation thực sự khớp runtime |

Có thể dùng `curl` để kiểm tra thô HTTP headers và SOAP response (ví dụ các file `request-soap11.xml`/`request-soap12.xml` là fixture của bài kiểm thử, không phải file được tạo bởi đoạn lệnh):

~~~bash
# SOAP 1.1
curl -i -X POST "https://api.example.test/services/orders" \
  -H "Content-Type: text/xml; charset=utf-8" \
  -H 'SOAPAction: "urn:example:orders:v1/GetOrder"' \
  --data-binary @request-soap11.xml

# SOAP 1.2
curl -i -X POST "https://api.example.test/services/orders" \
  -H 'Content-Type: application/soap+xml; charset=utf-8; action="urn:example:orders:v1/GetOrder"' \
  --data-binary @request-soap12.xml
~~~

Đối với kiểm thử tự động trong Spring-WS, có thể dùng các thư viện kiểm thử request/response SOAP mà dự án hỗ trợ, đồng thời khẳng định **namespace Envelope, SOAP version, HTTP Content-Type, fault code, payload XSD và nội dung Fault**. Lựa chọn HTTP status phải dựa trên binding và điều kiện kiểm thử thực tế, đặc biệt với lỗi do infrastructure trả về trước SOAP stack.

## 10. Checklist thiết kế khi triển khai contract-first

Khi xây dựng service SOAP doanh nghiệp với Spring-WS, mỗi quyết định ở lớp giao thức nên được ghi rõ trong hợp đồng triển khai:

1. Chọn SOAP 1.1 hoặc SOAP 1.2 dựa trên yêu cầu đối tác và khả năng client/server; nếu cần hỗ trợ cả hai, thiết kế rõ binding/port và cách triển khai cho từng phiên bản.
2. Công bố WSDL/XSD thống nhất: payload QName, action, endpoint URI, XML Schema, document/literal binding và lỗi nghiệp vụ.
3. Cấu hình message factory phù hợp với SOAP version, không phó mặc cho giá trị mặc định.
4. Xử lý SOAP Fault qua exception resolver, phân biệt lỗi phía gửi với lỗi phía nhận; mô tả chi tiết nghiệp vụ bằng cấu trúc XML ổn định.
5. Kiểm tra schema và namespace ở ranh giới SOAP; xử lý header `mustUnderstand` bằng interceptor thích hợp.
6. Với WS-Security, chứng chỉ, chữ ký và mã hóa XML, kiểm tra chính xác XML namespace/element mà pipeline bảo mật thực sự xử lý.
7. Chạy interoperability test với client đại diện của đối tác, gồm cả tình huống lỗi và các response HTTP không phải SOAP.

### Ghi nhớ

- **Namespace của SOAP Envelope** mới xác định phiên bản: `http://schemas.xmlsoap.org/soap/envelope/` cho SOAP 1.1 và `http://www.w3.org/2003/05/soap-envelope` cho SOAP 1.2.
- SOAP 1.1 qua HTTP thường dùng **`text/xml` + `SOAPAction` header**; SOAP 1.2 dùng **`application/soap+xml`**, với tham số `action` tùy chọn.
- SOAP 1.1 Fault dùng `faultcode`/`faultstring`/`detail`; SOAP 1.2 Fault dùng `Code`/`Reason`/`Detail` và có thể thêm `Subcode`.
- WSDL/XSD mô tả hợp đồng, JAXB ánh xạ payload, Spring-WS xử lý SOAP message; **cả ba phải khớp phiên bản và binding** để tích hợp ổn định.

**Câu hỏi tự kiểm tra:** Một đối tác gửi `Content-Type: application/soap+xml`, SOAP Envelope thuộc namespace SOAP 1.1 và payload nghiệp vụ đúng XSD. Bạn sẽ kiểm tra và sửa những gì trước tiên? Nếu xử lý thất bại do lỗi dữ liệu, SOAP Fault trả lại sẽ khác nhau thế nào giữa SOAP 1.1 và SOAP 1.2?

