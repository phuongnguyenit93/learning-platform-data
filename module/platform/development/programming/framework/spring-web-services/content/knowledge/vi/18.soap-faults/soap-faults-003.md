# Fault code, reason, detail, actor, role và subcode

Trong dịch vụ **Spring Web Services (Spring-WS)** theo hướng **contract-first**, một lỗi SOAP không chỉ là một exception Java hay HTTP status. Lỗi được biểu diễn bằng **SOAP Fault** — phần tử XML thuộc SOAP Envelope, có cấu trúc riêng để client nhận biết loại lỗi, đọc thông tin dành cho người vận hành và, nếu hợp đồng cho phép, giải mã chi tiết nghiệp vụ có kiểu dữ liệu xác định.

Sự khác nhau giữa **SOAP 1.1** và **SOAP 1.2** rất quan trọng. SOAP 1.1 dùng `faultcode`, `faultstring`, `faultactor` và `detail`. SOAP 1.2 dùng `Code`, `Reason`, `Node`, `Role` và `Detail`, đồng thời hỗ trợ **chuỗi `Subcode` lồng nhau**. Không thể đổi tên tag theo cảm tính hoặc sử dụng cùng XML Fault cho hai phiên bản.

Bài thuộc chương **SOAP Fault** của module `SPRING_WEB_SERVICES`. Ta nối cấu trúc Fault với XSD/WSDL, JAXB/OXM, `@Endpoint`, `EndpointExceptionResolver`, SOAP client, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích. Một nguyên tắc xuyên suốt: **fault code là phân loại giao thức, fault reason là giải thích cho con người, detail là dữ liệu lỗi có hợp đồng; actor/node/role mô tả ngữ cảnh của nút SOAP; subcode tinh chỉnh phân loại trong SOAP 1.2.**

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Đọc một SOAP Fault và phân biệt fault code, reason/string, detail, actor, node, role và subcode.
2. Nêu những phần tử bắt buộc, tùy chọn và thứ tự của SOAP Fault 1.1 so với SOAP Fault 1.2.
3. Giải thích QName trong fault code/subcode và vì sao không nên so chuỗi XML prefix.
4. Phân biệt **nguồn tạo lỗi** (actor/node) với **vai trò đang xử lý** (role).
5. Chọn đúng phân loại `Client/Sender`, `Server/Receiver`, `VersionMismatch` và `MustUnderstand` trong ngữ cảnh phù hợp.
6. Tạo/đọc SOAP Fault bằng `SoapBody`, `SoapFault`, `Soap12Fault` và `SoapFaultDetail` của Spring-WS.
7. Thiết kế fault detail có XSD/WSDL, ánh xạ lỗi nghiệp vụ và kiểm soát những gì được công bố ra client.
8. Kiểm thử cả SOAP 1.1/1.2, fault code/subcode, đa ngôn ngữ, WS-Security và chính sách retry.

## 1. Bối cảnh: SubmitOrder không thể hoàn thành

Hợp đồng SOAP có thao tác `SubmitOrder` với payload root:

~~~text
{urn:example:orders:v1}SubmitOrderRequest
~~~

Một yêu cầu có thể thất bại theo nhiều cách:

- `quantity=0` dù XSD yêu cầu số nguyên dương → lỗi **schema/request**.
- `requestId` đã dùng với nội dung khác → lỗi **business/idempotency conflict**.
- Database tạm thời không kết nối được → lỗi **server/infrastructure**.
- Header `mustUnderstand` hướng tới node nhưng node không hiểu → lỗi **SOAP protocol**.
- Chữ ký WS-Security không hợp lệ → lỗi **security**, có thể được security interceptor chuyển thành fault.

Phía client cần ít nhất hai mức thông tin: lỗi này **có liên quan tới bên gửi hay bên nhận**, và mã nghiệp vụ nào giúp quyết định **sửa dữ liệu, xác thực lại, retry an toàn hay liên hệ hỗ trợ**. SOAP Fault hỗ trợ chuyển tải các mức thông tin đó, nhưng mỗi phiên bản SOAP có hình dạng khác nhau.

### 1.1. SOAP Fault không phải response nghiệp vụ bình thường

~~~mermaid
flowchart TD
    A["SOAP request SubmitOrderRequest"] --> B{"Có thể xử lý?"}
    B -- "Có" --> C["SOAP Body: SubmitOrderResponse"]
    B -- "Không" --> D["SOAP Body: Fault"]
    D --> E["SOAP fault code + reason"]
    D --> F["Fault detail: public error model nếu phù hợp"]
    D --> G["Actor/Node/Role + Subcode theo SOAP version"]
~~~

Trong SOAP 1.2, `Fault` là **phần tử con duy nhất** của `Body` khi mang lỗi SOAP. Vì vậy không gửi một `SubmitOrderResponse` thành công **cùng cấp** với `Fault`. Với SOAP 1.1, Fault là một body entry được tiêu chuẩn định nghĩa; thiết kế ứng dụng cũng nên phát một Fault rõ ràng thay vì trộn payload thành công với lỗi.

## 2. Cấu trúc SOAP 1.1: faultcode, faultstring, faultactor, detail

Namespace của SOAP 1.1 Envelope:

~~~text
http://schemas.xmlsoap.org/soap/envelope/
~~~

Ví dụ server gặp lỗi nghiệp vụ khi nhận request:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:ord="urn:example:orders:fault:v1">
  <env:Body>
    <env:Fault>
      <faultcode>env:Client</faultcode>
      <faultstring>Yêu cầu đặt hàng không hợp lệ</faultstring>
      <faultactor>urn:example:orders:gateway</faultactor>
      <detail>
        <ord:OrderFault>
          <ord:code>INVALID_QUANTITY</ord:code>
          <ord:message>Số lượng phải lớn hơn 0</ord:message>
          <ord:correlationId>corr-1052</ord:correlationId>
        </ord:OrderFault>
      </detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

Đây là ví dụ **một nút gateway đã tạo Fault** và tự nhận diện bằng URI `urn:example:orders:gateway`. Nếu backend là ultimate destination phát lỗi, `faultactor` có thể được bỏ qua. Giá trị URI ở đây là **định danh nút SOAP trong message path**, không tự động là URL gọi endpoint hay người dùng gây lỗi.

Một chi tiết XML dễ bỏ sót: trong SOAP 1.1, các phần tử con `faultcode`, `faultstring`, `faultactor`, `detail` ở mẫu trên **không mang prefix `env`**; chúng không giống `env:Code`/`env:Reason` của SOAP 1.2. Mẫu của tiêu chuẩn dùng các tên phần tử này theo cấu trúc SOAP 1.1, không sao chép hình thức SOAP 1.2.

### 2.1. Bảng ý nghĩa bốn thành phần

| Thành phần SOAP 1.1 | Bắt buộc? | Ý nghĩa | Không nên dùng để |
| --- | --- | --- | --- |
| `faultcode` | **Có** | QName phân loại lỗi; phục vụ chương trình | Đặt raw Java exception name |
| `faultstring` | **Có** | Chuỗi giải thích cho con người | Quyết định luồng nghiệp vụ bằng so text |
| `faultactor` | Tùy trường hợp | URI của SOAP node phát lỗi; trung gian không phải đích cuối **phải có** | Thay bằng tên user hoặc trace ID |
| `detail` | Có điều kiện | Chi tiết ứng dụng liên quan **SOAP Body**; theo SOAP 1.1, phải có khi nội dung Body không được xử lý thành công | Chứa lỗi của **Header** hoặc stack trace |

Theo SOAP 1.1, `detail` **không dùng để chứa lỗi thuộc các Header entries**; thông tin lỗi chi tiết của Header phải được biểu diễn theo quy tắc Header. **Vắng `detail`** mang ý nghĩa lỗi không liên quan đến việc xử lý Body. Đây là điểm đặc thù SOAP 1.1, **không được áp cùng diễn giải cho `Detail` của SOAP 1.2**.

### 2.2. Bốn mã chuẩn của SOAP 1.1

| Fault code chuẩn | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `env:VersionMismatch` | Envelope không đúng phiên bản SOAP mà node hỗ trợ | SOAP namespace sai |
| `env:MustUnderstand` | Node không hiểu Header được đánh dấu bắt buộc cho nó | Header extension mới không được hỗ trợ |
| `env:Client` | Message/request không đủ điều kiện để xử lý | XML không hợp XSD, thiếu thông tin yêu cầu |
| `env:Server` | Lỗi xử lý không do nội dung thông điệp đơn thuần | Hạ tầng database/backend unavailable |

QName của `faultcode` gồm namespace và local name. `env:Client` không phải chuỗi magic gồm bốn ký tự `env:`: prefix `env` được bind tới namespace SOAP 1.1. Khi client parse XML, kiểm tra **QName đầy đủ**, không chỉ so `"env:Client"`.

SOAP 1.1 có thể sử dụng mã mở rộng theo quy tắc của hệ sinh thái, nhưng nó **không có cấu trúc `Code/Subcode` phân cấp chuẩn như SOAP 1.2**. Trong ứng dụng contract-first, thường ổn định hơn nếu giữ mã SOAP cấp cao và đặt business error code có namespace vào `detail`; nếu dùng custom fault codes, phải thống nhất kỹ với đối tác.

## 3. Cấu trúc SOAP 1.2: Code, Reason, Node, Role, Detail

Namespace của SOAP 1.2 Envelope:

~~~text
http://www.w3.org/2003/05/soap-envelope
~~~

Ví dụ cùng lỗi `INVALID_QUANTITY`, lần này có **Subcode**, **Reason đa ngôn ngữ**, **Node** và **Role**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope
    xmlns:env="http://www.w3.org/2003/05/soap-envelope"
    xmlns:ord="urn:example:orders:fault:v1">
  <env:Body>
    <env:Fault>
      <env:Code>
        <env:Value>env:Sender</env:Value>
        <env:Subcode>
          <env:Value>ord:InvalidOrder</env:Value>
          <env:Subcode>
            <env:Value>ord:InvalidQuantity</env:Value>
          </env:Subcode>
        </env:Subcode>
      </env:Code>
      <env:Reason>
        <env:Text xml:lang="vi">Yêu cầu đặt hàng không hợp lệ</env:Text>
        <env:Text xml:lang="en">Invalid order request</env:Text>
      </env:Reason>
      <env:Node>urn:example:orders:gateway</env:Node>
      <env:Role>http://www.w3.org/2003/05/soap-envelope/role/next</env:Role>
      <env:Detail>
        <ord:OrderFault>
          <ord:code>INVALID_QUANTITY</ord:code>
          <ord:message>Số lượng phải lớn hơn 0</ord:message>
          <ord:correlationId>corr-1052</ord:correlationId>
        </ord:OrderFault>
      </env:Detail>
    </env:Fault>
  </env:Body>
</env:Envelope>
~~~

Giả định nút gateway trong ví dụ thực sự xử lý thông điệp ở SOAP role `next`; `Role` **phải** là một role mà node đó đảm nhiệm tại thời điểm lỗi. Nếu không có lý do nghiệp vụ/protocol rõ để xác định role, đừng tự tạo URI tùy ý cho `Role`. `Node` và `Role` là **tùy chọn** đối với ultimate receiver theo các quy tắc tiêu chuẩn; node trung gian tạo fault phải khai báo `Node`.

### 3.1. Thứ tự và tính bắt buộc của các phần tử

SOAP 1.2 quy định các child trực tiếp của `env:Fault` **theo thứ tự**:

1. `env:Code` — **bắt buộc**, chứa `env:Value` và `env:Subcode` tùy chọn.
2. `env:Reason` — **bắt buộc**, có ít nhất một `env:Text` với `xml:lang`.
3. `env:Node` — **tùy chọn**, URI của SOAP node **đã tạo lỗi**; node không phải đích cuối phải nêu `Node`.
4. `env:Role` — **tùy chọn**, URI vai trò node đang thực hiện tại thời điểm lỗi.
5. `env:Detail` — **tùy chọn**, chứa chi tiết ứng dụng nếu phù hợp.

Thứ tự này thuộc **SOAP 1.2 message construct**, không phải cách đặt tên tự do của serializer. `Code` và `Reason` thuộc namespace Envelope; các detail entries ứng dụng thường thuộc namespace của hợp đồng nghiệp vụ.

### 3.2. Các SOAP 1.2 fault codes chuẩn

| `env:Code/env:Value` | Diễn giải | Tình huống |
| --- | --- | --- |
| `env:VersionMismatch` | Phiên bản Envelope không tương thích | Sender gửi SOAP 1.1 vào node chỉ hỗ trợ 1.2 |
| `env:MustUnderstand` | Header bắt buộc không được hiểu/xử lý | Node nhận header mới với mustUnderstand |
| `env:DataEncodingUnknown` | Node không nhận biết encoding được chỉ định | Nội dung dùng encodingStyle không hỗ trợ |
| `env:Sender` | Request/message chứa lỗi hoặc thiếu thông tin cần thiết | Invalid XML, auth/request issue |
| `env:Receiver` | Node xử lý thất bại do tình trạng bên nhận/hạ tầng | Backend unavailable |

`Sender` không đồng nghĩa HTTP 400 trong mọi môi trường; `Receiver` không hứa retry sẽ thành công. Client cần kết hợp **fault detail đã định nghĩa, tính idempotent của thao tác, timeout và trạng thái nghiệp vụ**, không chỉ nhìn một QName lỗi.

### 3.3. QName là danh tính cho Code/Subcode

`env:Code/env:Value` dùng QName của **nhóm lỗi SOAP chuẩn**. Các `env:Subcode/env:Value` dùng `xs:QName` cho phân loại chi tiết, thường thuộc namespace tính năng/ứng dụng. Hai giá trị:

~~~xml
<env:Value xmlns:a="urn:example:orders:fault:v1">a:InvalidQuantity</env:Value>
~~~

và

~~~xml
<env:Value xmlns:b="urn:example:orders:fault:v1">b:InvalidQuantity</env:Value>
~~~

là **cùng QName**, dù prefix `a` và `b` khác nhau. Ngược lại, cùng local name `InvalidQuantity` trong namespace v1 và v2 là hai mã khác nhau.

## 4. Actor, Node và Role: ba thông tin dễ bị nhầm

### 4.1. Fault actor trong SOAP 1.1

`faultactor` định danh bằng URI **SOAP node đã tạo lỗi** trong message path. Một SOAP intermediary như gateway có thể thực hiện nhiệm vụ chuyển tiếp, xử lý header hoặc ghi log, và có thể là nguồn phát fault. Trong SOAP 1.1, node trung gian **không phải ultimate destination** phải cung cấp `faultactor` khi tạo Fault. Ultimate destination **có thể** cung cấp nhưng không bắt buộc.

`faultactor` **không phải**:

- Người dùng, actor trong UML hay tên business role.
- Một `correlationId` hoặc `requestId`.
- Tên method `@Endpoint`.
- Giá trị SOAPAction.
- Đương nhiên là URL công khai của server.

Giá trị chỉ nên được công bố nếu định danh URI phù hợp với kiến trúc và chính sách tiết lộ topology của hệ thống.

### 4.2. SOAP 1.2 chia thành Node và Role

SOAP 1.2 làm rõ hai khái niệm:

| Trường | Câu hỏi trả lời | Điều kiện |
| --- | --- | --- |
| `env:Node` | **Nút SOAP nào** tạo Fault? | URI của SOAP node; bắt buộc với node không phải ultimate receiver |
| `env:Role` | Nút đó đang hành động với **SOAP role nào** khi lỗi xảy ra? | URI role thuộc tập vai trò node đã nhận |
| `env:Code` | Lỗi thuộc **nhóm nào**? | QName chuẩn `Sender`/`Receiver`/... |
| `env:Subcode` | Lỗi thuộc **phân nhóm nào** trong bối cảnh Code? | QName phân cấp, tùy chọn |
| `env:Detail` | Có **dữ liệu lỗi ứng dụng** nào phù hợp để client sử dụng? | Contract/public disclosure policy |

`Role` có quan hệ với quy tắc nhắm đích SOAP Header qua role URI, nhưng **không phải thuộc tính `env:role` trên Header**: đây là **một phần tử con của Fault** mô tả role của node lúc lỗi phát sinh. `Node` và `Role` cũng **không tự xác thực danh tính** hoặc chứng chỉ của node; chúng là thông tin do phía gửi Fault công bố và chỉ đáng tin trong phạm vi các cơ chế bảo mật tương ứng.

### 4.3. Một ví dụ với gateway và backend

~~~mermaid
flowchart LR
    A["SOAP Client"] --> B["SOAP Gateway<br/>Node A"]
    B --> C["Orders Backend<br/>Node B"]
    B -. "Header không hiểu<br/>MustUnderstand Fault" .-> A
    C -. "Business rule Fault<br/>hoặc Receiver Fault" .-> B
    B -. "Chuyển Fault theo hợp đồng" .-> A
~~~

Nếu **gateway** tạo Fault do không hiểu Header bắt buộc, URI nguồn nên chỉ đến gateway (theo policy). Nếu **backend** tạo Fault sau khi xử lý Body, backend có thể là Node phát lỗi; gateway không nên sửa nguồn phát một cách gây nhầm. Nếu gateway tự tạo một Fault mới từ lỗi backend, đó lại là một quyết định thiết kế có thể thay đổi Node/Role và Detail, phải được review.

## 5. Subcode: phân cấp lỗi trong SOAP 1.2

SOAP 1.2 cho phép `Code` chứa một `Subcode`; mỗi `Subcode` lại có thể chứa `Subcode` khác. Các giá trị sâu hơn **làm rõ** mã ở tầng trước.

~~~text
env:Sender                         ← top-level Code
  └── ord:InvalidOrder            ← Subcode #1
        └── ord:InvalidQuantity   ← Subcode #2
~~~

XML tương ứng:

~~~xml
<env:Code xmlns:env="http://www.w3.org/2003/05/soap-envelope"
          xmlns:ord="urn:example:orders:fault:v1">
  <env:Value>env:Sender</env:Value>
  <env:Subcode>
    <env:Value>ord:InvalidOrder</env:Value>
    <env:Subcode>
      <env:Value>ord:InvalidQuantity</env:Value>
    </env:Subcode>
  </env:Subcode>
</env:Code>
~~~

### 5.1. Khi nào nên dùng subcode?

Phù hợp khi nhiều bên cùng dùng SOAP 1.2 và muốn mô tả **phân loại lỗi có namespace, phân cấp**:

- `Sender → InvalidOrder → InvalidQuantity`.
- `Sender → SecurityPolicy → TokenExpired`, nếu security profile cho phép công bố.
- `Receiver → DependencyUnavailable`, nếu muốn client nhận một nhóm lỗi hạ tầng có nghĩa.

Không phải lúc nào cũng nên đưa toàn bộ lỗi nội bộ vào subcode. Subcode là **thông tin trên đường truyền**: client/gateway có thể dùng để quyết định luồng xử lý và nó có thể làm lộ cấu trúc hệ thống. Chỉ công bố các mã đã được duyệt, có chính sách versioning.

### 5.2. Vì sao subcode không thay cho detail?

| Mục tiêu | Subcode | Detail |
| --- | --- | --- |
| Xác định phân loại lỗi | Rất phù hợp | Có thể chứa thêm mã |
| Truyền ID/correlation ID | Không phù hợp | Có thể chứa trường đã schema hóa |
| Truyền nhiều field violations | Không phù hợp | Phù hợp với mô hình lỗi có cấu trúc |
| Client làm branching theo mã | Có thể dùng QName subcode | Có thể dùng `code` trong detail |
| Chứa dữ liệu nghiệp vụ nhiều trường | Không | Có |
| Có trong SOAP 1.1? | **Không có cấu trúc Subcode chuẩn** | Có `detail` |

Trong hệ thống phải hỗ trợ **cả SOAP 1.1 và 1.2**, thường hợp lý khi **public business error code vẫn nằm trong `detail`/`Detail`**, và dùng SOAP 1.2 Subcode như một lớp phân loại bổ sung. Như vậy client 1.1 không bị thiếu mã ứng dụng quan trọng.

### 5.3. Lưu ý về tính tương thích

Khi một client chưa biết `ord:InvalidQuantity`, nó vẫn có thể hiểu nhóm `env:Sender` nếu xử lý theo contract đã thống nhất. Tuy nhiên, SOAP 1.2 quy định một node phải hiểu các fault codes trong chuỗi trước khi diễn giải `Detail` đúng bối cảnh. Vì vậy:

- Công bố danh sách subcodes mà client cần hiểu.
- Có chính sách xử lý subcode mới/không nhận diện, thay vì âm thầm coi mọi lỗi giống nhau.
- Không thêm subcode bắt buộc mới vào hợp đồng đang chạy nếu chưa kiểm thử client cũ.
- Giữ top-level `Code` đúng nhóm lỗi.
- Dùng QName-aware XML handling, không so chữ `ord:InvalidQuantity`.

## 6. Reason và faultstring không phải mã máy đọc được

Trong SOAP 1.1, `faultstring` là một chuỗi giải thích bắt buộc. Trong SOAP 1.2, `Reason` chứa **ít nhất một** `Text`, mỗi `Text` có thuộc tính `xml:lang` bắt buộc; nhiều `Text` có thể cung cấp các ngôn ngữ khác nhau.

Ví dụ SOAP 1.2:

~~~xml
<env:Reason xmlns:env="http://www.w3.org/2003/05/soap-envelope">
  <env:Text xml:lang="vi">Đơn hàng không hợp lệ</env:Text>
  <env:Text xml:lang="en">Invalid order request</env:Text>
</env:Reason>
~~~

`Reason`/**`faultstring`** dành cho người đọc, **không dành cho việc phân nhánh thuật toán**. Không nên viết client:

~~~java
// KHÔNG NÊN: thay ngôn ngữ hoặc câu chữ là logic hỏng.
if (fault.getFaultStringOrReason().contains("không hợp lệ")) {
    retryWithDifferentData();
}
~~~

Thay vào đó, dùng fault `Code`/`Subcode` hoặc mã ứng dụng trong detail, theo mức cam kết của hợp đồng.

### 6.1. Quy tắc viết thông điệp có thể công bố

Một reason tốt:

- Ngắn, đủ để người vận hành nhận biết **nhóm lỗi**.
- Không chứa stack trace, SQL, địa chỉ nội bộ, private key, token hoặc PII.
- Không echo raw XML validation messages chưa qua duyệt.
- Có chính sách localization; client **không** dựa trên wording.

Một reason an toàn cho lỗi server có thể là “Dịch vụ tạm thời không thể xử lý yêu cầu”. Log nội bộ (được phân quyền) giữ diagnostic chi tiết và correlation ID để truy vết, không phải public Fault.

### 6.2. SOAP 1.1 và ngôn ngữ

SOAP 1.1 `faultstring` không có cấu trúc `Reason/Text` đa ngôn ngữ như SOAP 1.2. Ứng dụng có thể dùng convention về ngôn ngữ hoặc attribute tùy lựa chọn interoperable, nhưng **không mặc định** client 1.1 hiểu cách SOAP 1.2 cung cấp nhiều translations. Nếu yêu cầu đa ngôn ngữ nghiêm ngặt, hãy định nghĩa cách chọn ngôn ngữ trong contract và test client thật.

## 7. Detail: thông tin lỗi nghiệp vụ có cấu trúc

`detail` trong SOAP 1.1 và `env:Detail` trong SOAP 1.2 là nơi đặt **các phần tử lỗi thuộc hợp đồng ứng dụng**, ví dụ mã lỗi, trường không hợp lệ và correlation ID. Nếu đã định nghĩa trong XSD/WSDL, client có thể giải mã chi tiết lỗi bằng JAXB hoặc một SOAP stack khác, thay vì so text của `faultstring` hay `Reason`.

### 7.1. XSD minh họa cho fault detail

Một dịch vụ Orders có thể thống nhất một global element:

~~~xml
<ord:OrderFault xmlns:ord="urn:example:orders:fault:v1">
  <ord:code>INVALID_QUANTITY</ord:code>
  <ord:message>Số lượng phải lớn hơn 0</ord:message>
  <ord:correlationId>corr-1052</ord:correlationId>
</ord:OrderFault>
~~~

Trong SOAP 1.1, element nằm bên trong `<detail>`; trong SOAP 1.2, nằm bên trong `<env:Detail>`. **QName của `OrderFault` không đổi** giữa hai phiên bản. XSD cho fragment này:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:ord="urn:example:orders:fault:v1"
    targetNamespace="urn:example:orders:fault:v1"
    elementFormDefault="qualified">

  <xs:simpleType name="PublicFaultCodeType">
    <xs:restriction base="xs:string">
      <xs:enumeration value="INVALID_QUANTITY"/>
      <xs:enumeration value="REQUEST_ID_CONFLICT"/>
      <xs:enumeration value="ORDER_NOT_AVAILABLE"/>
      <xs:enumeration value="DEPENDENCY_UNAVAILABLE"/>
      <xs:enumeration value="UNEXPECTED_ERROR"/>
    </xs:restriction>
  </xs:simpleType>

  <xs:element name="OrderFault">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="code" type="ord:PublicFaultCodeType"/>
        <xs:element name="message" type="xs:string"/>
        <xs:element name="correlationId" type="xs:string"
                    minOccurs="0"/>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
~~~

Trong production, hãy giới hạn độ dài `message`/`correlationId`, kiểm soát những mã được phép xuất bản và có chính sách mở rộng enum tương thích. Ví dụ mô tả **public fault model**, không phải nơi lưu toàn bộ dữ liệu nội bộ để debug.

### 7.2. Detail không phải “dump exception”

Một exception nội bộ có thể chứa:

~~~text
org.hibernate.exception.ConstraintViolationException:
unique index orders_buyer_request failed at db-internal-03
~~~

Không nên marshal chuỗi đó vào SOAP Fault. Nếu lỗi có ý nghĩa nghiệp vụ đã xác định, hãy ánh xạ thành `REQUEST_ID_CONFLICT` và một thông điệp công khai đã duyệt. Nếu lỗi chưa phân loại, dùng mã chung như `UNEXPECTED_ERROR`, lưu diagnostic (đã che dữ liệu) vào telemetry bảo vệ và cung cấp correlation ID.

**Điểm khác biệt quan trọng:** SOAP 1.1 có quy tắc `detail` liên quan việc xử lý Body; theo tiêu chuẩn, `detail` phải có khi nội dung Body không xử lý thành công và không dùng cho lỗi thuộc Header. Trong SOAP 1.2, `Detail` là tùy chọn và **sự có mặt hoặc vắng mặt không nói được những phần nào của message đã được xử lý**. Không suy diễn trạng thái transaction từ việc có `Detail`.

### 7.3. Detail so với Header

SOAP Header có thể mang `wsse:Security`, `wsa:Action` hoặc `CorrelationId`, còn `Detail` nằm dưới SOAP Fault trong **Body**. Với lỗi WS-Security, không được công bố raw token, certificate private material hoặc thông điệp parser chỉ để “giải thích detail”. Hãy tôn trọng policy bảo mật và quy tắc xử lý Header của phiên bản SOAP đang dùng.

## 8. Công bố WSDL fault khi dùng contract-first

XSD có `OrderFault` **không tự khiến server phát lỗi theo element này**. Nếu đối tác cần typed fault, WSDL 1.1 có thể khai báo:

~~~xml
<!-- Fragment: wsdl, soap, tns, ord đã được khai báo đúng namespace. -->
<wsdl:message name="OrderFaultMessage">
  <wsdl:part name="fault" element="ord:OrderFault"/>
</wsdl:message>

<wsdl:portType name="OrdersPortType">
  <wsdl:operation name="SubmitOrder">
    <wsdl:input message="tns:SubmitOrderInput"/>
    <wsdl:output message="tns:SubmitOrderOutput"/>
    <wsdl:fault name="OrderFault"
                message="tns:OrderFaultMessage"/>
  </wsdl:operation>
</wsdl:portType>

<wsdl:binding name="OrdersSoap11Binding" type="tns:OrdersPortType">
  <!-- Đã lược soap:binding và input/output binding. -->
  <wsdl:operation name="SubmitOrder">
    <wsdl:fault name="OrderFault">
      <soap:fault name="OrderFault" use="literal"/>
    </wsdl:fault>
  </wsdl:operation>
</wsdl:binding>
~~~

Đây là fragment **không phải WSDL hoàn chỉnh**. Khi triển khai, phải có `wsdl:definitions`, `wsdl:types`/`xs:import` cho fault namespace, request/response messages, SOAP binding và service port tương ứng.

| Thành phần | Công việc | Không tự thực hiện |
| --- | --- | --- |
| XSD `OrderFault` | Mô tả QName và kiểu XML trong Detail | Không bắt exception Java |
| `wsdl:fault` / `soap:fault` | Công bố lỗi trong interface/binding | Không tạo Fault ở runtime |
| `InvalidOrderException` | Biểu diễn lỗi ở application layer | Không quyết định SOAP code |
| `EndpointExceptionResolver` | Ánh xạ exception thành SOAP Fault | Cần customization để tạo typed Detail |
| `SoapFaultDetail` + JAXB | Viết XML detail theo schema | Không tự quyết định retry/security policy |

Với SOAP 1.2 trong WSDL 1.1, extension binding dùng `soap12:binding`/`soap12:fault` của SOAP 1.2, không copy nguyên SOAP 1.1 binding rồi chỉ đổi Envelope ở runtime.

### 8.1. WSDL tĩnh và WSDL sinh động

`DefaultWsdl11Definition` có thể suy ra operation dựa trên các global elements có hậu tố `Request`/`Response`. Việc thêm `OrderFault` vào XSD **không bảo đảm** framework tự tạo mọi `wsdl:fault` và `soap:fault` theo chính sách exception nghiệp vụ của bạn. Nếu hợp đồng đã được đối tác duyệt, cân nhắc WSDL tĩnh hoặc kiểm thử tự động nội dung WSDL sinh động để phát hiện thay đổi khi nâng phiên bản.

### 8.2. Versioning fault contract

Các thay đổi có thể phá vỡ client cũ: đổi namespace hoặc local name của `OrderFault`, đổi mã public `INVALID_QUANTITY`, biến field tùy chọn thành bắt buộc, đổi SOAP fault classification hoặc thêm `Subcode` mà client chưa hỗ trợ. Hãy kiểm thử **client cũ → server mới** và client mới → server cũ theo chính sách khả năng tương thích.

## 9. Spring-WS API: tạo và đọc Fault theo SOAP version

Spring-WS cung cấp các abstraction:

| API | Trách nhiệm |
| --- | --- |
| `SoapMessage.getSoapBody()` | Lấy SOAP Body |
| `SoapBody.hasFault()` / `getFault()` | Kiểm tra/lấy Fault hiện có |
| `SoapBody.addClientOrSenderFault(reason, locale)` | Tạo `Client` (1.1) hoặc `Sender` (1.2) |
| `SoapBody.addServerOrReceiverFault(reason, locale)` | Tạo `Server` (1.1) hoặc `Receiver` (1.2) |
| `SoapBody.addMustUnderstandFault(...)` | Tạo lỗi `MustUnderstand` |
| `SoapBody.addVersionMismatchFault(...)` | Tạo lỗi `VersionMismatch` |
| `SoapFault.getFaultCode()` | QName fault code cấp trên |
| `SoapFault.getFaultStringOrReason()` | Chuỗi 1.1 hoặc reason mặc định 1.2 |
| `SoapFault.getFaultActorOrRole()` | Actor 1.1 hoặc Role 1.2 |
| `SoapFault.setFaultActorOrRole(uri)` | Gán Actor hoặc Role theo phiên bản |
| `SoapFault.getFaultDetail()` / `addFaultDetail()` | Đọc/tạo Detail |
| `Soap12Fault.addFaultSubcode(QName)` | Thêm một Subcode SOAP 1.2 |
| `Soap12Fault.getFaultSubcodes()` | Các Subcode theo thứ tự từ trên xuống |
| `Soap12Fault.setFaultNode(uri)` | Đặt Node SOAP 1.2 |
| `Soap12Fault.setFaultReasonText(locale, text)` | Thêm/sửa một Reason/Text theo ngôn ngữ |

`Soap12Fault` kế thừa `SoapFault` nhưng mở rộng API cho Node và Subcode. `Soap11Fault` không có các trường SOAP 1.2 này. Trong Java, `QName` vẫn nằm ở `javax.xml.namespace.QName` kể cả khi JAXB API của Spring Boot 3+ là `jakarta.xml.bind`.

### 9.1. Ví dụ tạo Fault bằng `SoapBody`

Giả sử `response` là một `SoapMessage` chưa có payload thành công:

~~~java
import java.util.Locale;
import javax.xml.namespace.QName;

import org.springframework.ws.soap.SoapBody;
import org.springframework.ws.soap.SoapFault;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.soap12.Soap12Fault;

public final class OrderFaultWriter {

    private static final String FAULT_NS =
        "urn:example:orders:fault:v1";

    public static SoapFault createInvalidOrderFault(
            SoapMessage response) {
        SoapBody body = response.getSoapBody();

        if (body.hasFault()) {
            throw new IllegalStateException("Fault already exists");
        }

        SoapFault fault = body.addClientOrSenderFault(
            "Yêu cầu đặt hàng không hợp lệ",
            Locale.forLanguageTag("vi"));

        if (fault instanceof Soap12Fault soap12) {
            soap12.addFaultSubcode(
                new QName(FAULT_NS, "InvalidOrder"));
            soap12.addFaultSubcode(
                new QName(FAULT_NS, "InvalidQuantity"));

            soap12.setFaultReasonText(
                Locale.ENGLISH, "Invalid order request");

            // Chỉ đặt khi biết đúng node URI và SOAP role.
            // soap12.setFaultNode("urn:example:orders:gateway");
            // soap12.setFaultActorOrRole(
            //   "http://www.w3.org/2003/05/soap-envelope/role/next");
        }
        return fault;
    }
}
~~~

`addClientOrSenderFault` chọn fault code chuẩn cho phiên bản SOAP hiện tại. Việc gọi `addFaultSubcode` hai lần chỉ áp dụng khi đối tượng thực là `Soap12Fault`, giúp biểu diễn phân cấp lỗi; kiểm tra XML thực tế vì provider có thể dùng prefix khác nhau.

Ví dụ này minh họa **API tạo fault trực tiếp**, không khuyến nghị endpoint nghiệp vụ nào cũng tự dựng Fault. Trong `@Endpoint` contract-first, thường để endpoint trả JAXB response hoặc ném exception, và tầng exception resolver/interceptor xử lý fault.

### 9.2. Viết Detail bằng JAXB/OXM

Giả sử `OrderFault` là JAXB root class (hoặc `JAXBElement<OrderFaultType>`), đúng XSD mục 7:

~~~java
import org.springframework.oxm.jaxb.Jaxb2Marshaller;
import org.springframework.ws.soap.SoapFault;
import org.springframework.ws.soap.SoapFaultDetail;

public void writeDetail(
        SoapFault fault,
        Object orderFaultRoot,
        Jaxb2Marshaller marshaller) {

    SoapFaultDetail detail = fault.addFaultDetail();

    // Marshal root {urn:example:orders:fault:v1}OrderFault
    // vào nội dung của SOAP 1.1 detail / SOAP 1.2 Detail.
    marshaller.marshal(orderFaultRoot, detail.getResult());
}
~~~

`orderFaultRoot` phải được JAXB context nhận diện và có QName đúng schema. Không marshal SOAP Envelope vào `Detail`. Một cách khác là `SoapFaultDetail.addFaultDetailElement(QName)` và viết nội dung vào `SoapFaultDetailElement`. **Chọn một cách sinh root**: tránh tạo `OrderFault` trước rồi marshal thêm một `OrderFault` lồng trong nó.

### 9.3. Đọc Fault qua API chung

~~~java
import java.util.Iterator;
import java.util.Locale;
import javax.xml.namespace.QName;

import org.springframework.ws.soap.SoapFault;
import org.springframework.ws.soap.SoapFaultDetail;
import org.springframework.ws.soap.SoapFaultDetailElement;
import org.springframework.ws.soap.SoapMessage;
import org.springframework.ws.soap.soap12.Soap12Fault;

public void inspectFault(SoapMessage message) {
    if (!message.getSoapBody().hasFault()) {
        return;
    }

    SoapFault fault = message.getSoapBody().getFault();

    QName mainCode = fault.getFaultCode();
    String reason = fault.getFaultStringOrReason();
    String actorOrRole = fault.getFaultActorOrRole();

    if (fault instanceof Soap12Fault soap12) {
        String nodeUri = soap12.getFaultNode();
        String enReason = soap12.getFaultReasonText(Locale.ENGLISH);

        Iterator<QName> subcodes = soap12.getFaultSubcodes();
        while (subcodes.hasNext()) {
            QName subcode = subcodes.next();
            // So QName theo URI + localPart, không so prefix.
        }
    }

    SoapFaultDetail detail = fault.getFaultDetail();
    if (detail != null) {
        Iterator<SoapFaultDetailElement> entries =
            detail.getDetailEntries();

        while (entries.hasNext()) {
            SoapFaultDetailElement entry = entries.next();
            QName detailRoot = entry.getName();
            // Unmarshal entry.getSource() khi QName đúng contract.
        }
    }

    // mainCode, reason, actorOrRole phục vụ error policy/trace.
}
~~~

`getFaultCode()` ở SOAP 1.2 trả **top-level `Code/Value`**, còn các Subcodes cần đọc qua `getFaultSubcodes()`. `getFaultStringOrReason()` của SOAP 1.2 lấy reason theo locale mặc định; dùng `getFaultReasonText(Locale)` để truy cập bản dịch cụ thể.

### 9.4. Dùng `SoapFaultMappingExceptionResolver`

Thay vì tạo Fault thủ công trong handler, có thể ánh xạ exception nghiệp vụ:

~~~java
import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.soap.server.endpoint.SoapFaultDefinition;
import org.springframework.ws.soap.server.endpoint.SoapFaultMappingExceptionResolver;

@Configuration
public class FaultResolutionConfiguration {

    @Bean
    public SoapFaultMappingExceptionResolver faultResolver() {
        SoapFaultMappingExceptionResolver resolver =
            new SoapFaultMappingExceptionResolver();

        Properties mappings = new Properties();
        mappings.setProperty(
            InvalidOrderException.class.getName(),
            "CLIENT,Yêu cầu đặt hàng không hợp lệ");
        resolver.setExceptionMappings(mappings);

        SoapFaultDefinition fallback = new SoapFaultDefinition();
        fallback.setFaultCode(SoapFaultDefinition.SERVER);
        fallback.setFaultStringOrReason(
            "Dịch vụ tạm thời không thể xử lý yêu cầu");
        resolver.setDefaultFault(fallback);

        return resolver;
    }
}
~~~

`InvalidOrderException` là custom exception của ứng dụng. Mã `CLIENT`/`SERVER` trong mapping sẽ được biểu diễn phù hợp SOAP version; hãy xác minh fault XML sau serializer. Resolver này chưa tự thêm `OrderFault` vào `Detail`. Khi cần thêm detail, subcode hoặc Node/Role theo policy, subclass resolver và override `customizeFault(Object endpoint, Exception ex, SoapFault fault)` của `AbstractSoapFaultDefinitionExceptionResolver`.

Một hệ thống có thể có **nhiều nguồn tạo Fault**: `PayloadValidatingInterceptor` tự phát fault với request sai XSD, `Wss4jSecurityInterceptor` phát lỗi security, `EndpointExceptionResolver` xử lý exception nghiệp vụ, hoặc gateway từ chối request trước khi Spring-WS endpoint mapping. **Không phải mọi lỗi đều đi qua cùng resolver**. Hãy định nghĩa fault policy cho từng nhánh và tránh công bố raw parser/WS-Security diagnostics.


## 10. SOAP client: nhận Fault khác nhận response thành công

Một SOAP client dùng `WebServiceTemplate` thường mong unmarshal `SubmitOrderResponse` với lời gọi thành công. Khi server trả SOAP Fault, đường xử lý **khác** và theo cấu hình thường có thể ném `SoapFaultClientException`.

~~~java
import javax.xml.namespace.QName;
import org.springframework.ws.soap.client.SoapFaultClientException;

public SubmitOrderResult submitSafely(SubmitOrderRequest request) {
    try {
        Object rawResponse =
            webServiceTemplate.marshalSendAndReceive(request);
        return mapSuccessfulResponse(rawResponse);

    } catch (SoapFaultClientException ex) {
        QName code = ex.getFaultCode();
        String reason = ex.getFaultStringOrReason();

        // Đọc ex.getSoapFault().getFaultDetail() nếu có,
        // xác định QName {urn:example:orders:fault:v1}OrderFault
        // rồi dùng JAXB unmarshal theo schema/binding tương ứng.
        throw mapToIntegrationException(code, reason, ex);
    }
}
~~~

`SubmitOrderResult`, `mapSuccessfulResponse` và `mapToIntegrationException` là application types/methods cần tự hiện thực; đoạn code là khung tích hợp, không phải ví dụ có thể biên dịch độc lập. Nếu XJC sinh `JAXBElement<T>` thay vì `@XmlRootElement`, điều chỉnh request/response wrapper phù hợp.

**Không** ép SOAP Fault thành `SubmitOrderResponse(status="ERROR")` nếu XSD/WSDL quy định Fault là luồng lỗi độc lập. Cũng không phân nhánh dựa trên `reason.contains("Invalid")` vì ngôn ngữ và câu chữ có thể thay đổi.

### 10.1. Lỗi SOAP và lỗi mạng cần chính sách khác nhau

| Client quan sát được | Thông tin thường có | Điều cần làm |
| --- | --- | --- |
| `Client`/`Sender` Fault | Nhóm lỗi phía message/client | Sửa request/chính sách gọi; xem public fault code |
| `Server`/`Receiver` Fault | Nhóm lỗi xử lý phía nhận | Retry có kiểm soát nếu operation an toàn |
| Business `OrderFault.code` | Mã ứng dụng có hợp đồng | Hành động theo error catalog |
| SOAP 1.2 `Subcode` | Phân loại chi tiết theo QName | Chỉ dựa vào mã đã được định nghĩa |
| Timeout/connection reset | **Không có kết quả SOAP đáng tin** | Tra cứu trạng thái, retry theo idempotency |
| TLS/certificate handshake failure | Lỗi transport/trust | Sửa certificate/trust policy, không chờ SOAP Fault |

`Receiver` không chứng minh DB đã rollback. Một `SubmitOrder` có thể commit, sau đó gặp lỗi marshalling hoặc đường truyền khiến client chỉ thấy Fault hoặc timeout. Đối với command có tác dụng phụ, phải có `requestId`/idempotency key và operation tra cứu trạng thái theo hợp đồng. **Không tạo requestId mới chỉ vì timeout**.

### 10.2. Client xử lý subcodes không biết trước

Một client SOAP 1.2 nhận `Sender → InvalidOrder → NewBusinessRule` mà chỉ biết `InvalidOrder` cần có chính sách rõ:

- Nếu `NewBusinessRule` là mã bắt buộc phải hiểu để xử lý detail, cần nâng client hoặc báo unsupported subcode theo hợp đồng.
- Nếu hợp đồng cho phép fallback theo nhóm lỗi đã biết, xử lý **không tự động retry nguy hiểm**, và ghi trace để hỗ trợ.
- Đừng bỏ qua namespace: `InvalidOrder` trong v1 và v2 có thể khác nghĩa.

Việc thêm subcode là thay đổi **wire contract**; hãy test backward compatibility trước khi phát hành.

## 11. Fault, bảo mật XML và WS-Security

SOAP Fault có thể trở thành kênh lộ thông tin nếu ứng dụng copy thẳng Java exception, XML parser diagnostics hoặc dữ liệu xác thực ra client. Cần review **mọi trường**:

| Vị trí Fault | Nên công bố | Tránh |
| --- | --- | --- |
| Top-level fault code | Mã SOAP chuẩn đúng version | Lỗi mơ hồ hoặc custom code không có contract |
| `Subcode` | QName phân loại đã công bố/version hóa | Internal Java package/class name |
| `faultstring`/`Reason` | Thông báo chung, không nhạy cảm | `exception.getMessage()`, SQL, stack trace |
| `detail`/`Detail` | Public code, field được whitelist, correlation ID | Token, dữ liệu thanh toán, PII, raw SOAP |
| `faultactor`/`Node` | URI định danh nút theo policy | Hostname/IP nội bộ không cần thiết |
| `Role` | SOAP role URI thực sự đang thực hiện | “admin”, “buyer” hoặc quyền ứng dụng |
| Telemetry nội bộ | Diagnostic đã che dữ liệu, phân quyền, retention | Raw private keys hoặc credentials |

### 11.1. XSD validation không phải xác thực

Một SOAP Body đúng XSD vẫn có thể mang chữ ký giả mạo, timestamp hết hạn hoặc token sai. `Wss4jSecurityInterceptor` và các thành phần WS-Security phải xác minh signature, token, timestamp và chính sách mã hóa; không coi việc nhìn thấy `wsse:Security` hoặc `Signature` trong XML là đã xác thực.

Nếu XML Signature được sử dụng, **node đã được xác minh chữ ký phải là node được JAXB/endpoint xử lý**. Tránh các XPath quá rộng như `//*[local-name()='SubmitOrderRequest']` làm tăng rủi ro signature wrapping và nhầm namespace.

### 11.2. Không lộ raw validation diagnostics

`PayloadValidatingInterceptor` có thể thêm validation error detail với thông báo từ parser tùy cấu hình. Với API SOAP công bố cho đối tác, cân nhắc `setAddValidationErrorDetail(false)` để không phát raw `SAXParseException` messages. Nếu client cần field-level violations, hãy tạo các lỗi được whitelist, giới hạn số lượng và độ dài, rồi serialize thành fault detail theo XSD.

Với SOAP 1.1 nhớ `detail` có quy tắc gắn với lỗi xử lý Body; với SOAP 1.2 `Detail` tùy chọn và không chứng minh phần Body đã được xử lý hay chưa.

### 11.3. TLS/mTLS, parser và lỗi trước endpoint

- **TLS/mTLS:** chain chứng chỉ, hostname, client certificate, truststore và rotation thuộc transport. TLS handshake thất bại có thể xảy ra **trước khi có SOAP message**, nên không có SOAP Fault.
- **XML parser:** tắt DTD/external entities theo provider, chống XXE, giới hạn size/depth/time để tránh DoS trước validation.
- **SOAP Header `mustUnderstand`:** SOAP infrastructure có thể tạo protocol fault trước khi vào business endpoint; với SOAP 1.1 không nhét Header-specific diagnostics vào Body `detail`.
- **Authorization:** dùng principal đã xác thực và resource policy, không dựa trên SOAP `Role`, `Node` hoặc business field caller tự khai.

`EndpointInterceptor` thường chạy **sau khi endpoint mapping tìm được endpoint**. Request sai transport/parse hoặc không có mapping có thể không đi qua interceptor hay business exception resolver. Hãy cấu hình gateway/filter/transport độc lập và kiểm tra từng nhánh fault.

## 12. Kiểm thử SOAP Fault và khả năng tương thích

### 12.1. Ma trận kiểm thử

| Tình huống | SOAP 1.1 | SOAP 1.2 | Điều cần kiểm tra |
| --- | --- | --- | --- |
| XSD request sai | `Client` | `Sender` | Không vào business service |
| Backend unavailable | `Server` | `Receiver` | Reason chung, không lộ SQL |
| Header bắt buộc không hiểu | `MustUnderstand` | `MustUnderstand` | SOAP protocol fault |
| SOAP Envelope phiên bản sai | `VersionMismatch` nếu tạo được Fault | `VersionMismatch` nếu tạo được Fault | Không nhầm với lỗi XSD |
| Business `INVALID_QUANTITY` | `detail/OrderFault` | `Detail/OrderFault` | QName detail theo XSD |
| Subcode `InvalidOrder` | Không có Subcode kiểu 1.2 | `Subcode/Value` | Không giả vờ hỗ trợ trong 1.1 |
| Subcode nested `InvalidQuantity` | Không áp dụng | `Subcode/Subcode/Value` | Thứ tự phân cấp |
| Reason tiếng Việt/Anh | `faultstring` theo policy | `Text xml:lang` | Locale/encoding |
| Gateway phát Fault | `faultactor` theo policy | `Node` và `Role` nếu phù hợp | Nguồn và vai trò |
| Ultimate receiver phát Fault | Actor có thể vắng | Node/Role có thể vắng | Tính tùy chọn |
| Detail rò token, SQL, nội bộ | Không được có | Không được có | Disclosure/security |
| Đổi XML prefix, giữ QName | Vẫn đọc đúng | Vẫn đọc đúng | Namespace-aware |
| Client dùng sai SOAP binding | Fault/transport theo thực tế | Fault/transport theo thực tế | Interoperability |
| DB commit nhưng response thất lạc | Client có thể timeout | Tương tự | Retry idempotent |
| Java và .NET client từ WSDL | Đọc business detail | Đọc theo binding 1.2 nếu hỗ trợ | Contract consistency |

### 12.2. Mock server dispatch bằng `MockWebServiceClient`

Spring-WS Test có response matchers `clientOrSenderFault(...)` và `serverOrReceiverFault(...)` để kiểm tra fault group không cần hardcode SOAP 1.1 hay 1.2:

~~~java
// Khung test: static imports/JUnit/Spring-WS Test được lược bớt.
MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

client.sendRequest(
        withPayload(new StringSource(invalidSubmitOrderPayload)))
      .andExpect(
        clientOrSenderFault("Yêu cầu đặt hàng không hợp lệ"));
~~~

`invalidSubmitOrderPayload` là **XML payload root**, không phải cả SOAP Envelope khi dùng `withPayload`. Cần cấu hình endpoint mapping, validator/resolver và message factory trong test context. Matcher này **không đủ** để kiểm tra `Subcode`, `Role`, `Node`, `Reason` đa ngôn ngữ hoặc `Detail`; thêm kiểm tra SOAP-aware trên message trả về.

### 12.3. So QName, không so prefix trong raw text

Đừng làm:

~~~java
// Dễ lỗi giả nếu serializer đổi prefix ord thành ns2.
assertTrue(xml.contains("<env:Value>ord:InvalidQuantity</env:Value>"));
~~~

Hãy parse XML bằng parser an toàn, dùng namespace-aware DOM/XPath và xác nhận:

1. `Fault` nằm trong **đúng SOAP Body**; SOAP 1.2 không có response success body entry cùng cấp.
2. `faultcode` hoặc `Code/Value` được giải thành QName đúng SOAP namespace.
3. SOAP 1.2 `Subcode/Value` có QName đúng và thứ tự nested parent/child đúng.
4. `Reason/Text` có `xml:lang` khi dùng SOAP 1.2.
5. `Node`/`Role` chỉ xuất hiện khi policy yêu cầu, là URI đúng ý nghĩa.
6. `Detail/OrderFault` có đúng global element QName, dữ liệu theo XSD.
7. Không có Java stack, database hostname, password, token, private key hoặc raw XML chứa PII.

### 12.4. Kiểm thử client với `MockWebServiceServer`

Mock SOAP server cho `WebServiceTemplate` các ca:

- SOAP 1.1 Client/Server fault và SOAP 1.2 Sender/Receiver fault theo message factory.
- Fault có/không có Detail; client không được crash khi detail optional vắng.
- SOAP 1.2 có Subcode lồng và hai ngôn ngữ Reason.
- Detail có mã lỗi chưa biết trước, client fallback theo policy.
- Transport timeout không có SOAP Fault.
- Lệnh có idempotency key bị gửi lại sau response thất lạc.

Client phải đọc `SoapFaultClientException`/fault handler riêng, không cố JAXB-unmarshal thành success response.

### 12.5. Thử với công cụ khác nền tảng

Tải WSDL từ URL công bố thực tế, kiểm tra `wsdl:fault`/`wsdl:message`/`soap:fault` hoặc `soap12:fault`, rồi sinh client Java và .NET. Với cùng một business fault, so sánh **wire XML** chứ không chỉ exception type nội bộ.

Không phải mọi client generator đều biểu diễn SOAP 1.2 Subcodes thành cùng cấu trúc Java/.NET. Nếu Subcode là điều kiện bắt buộc để client hoạt động, phải kiểm tra đúng client stack/phiên bản đang sử dụng.

## 13. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách tránh |
| --- | --- | --- |
| Copy Fault SOAP 1.1 sang Envelope 1.2 | Sai cấu trúc/namespace | Dùng Code/Reason/Node/Role/Detail đúng version |
| Coi `faultactor` = `Role` | Nhầm node tạo lỗi với vai trò xử lý | SOAP 1.2 phân biệt Node và Role |
| Đặt `Role` bằng business user role | Sai nghĩa SOAP | SOAP role URI node thực sự đảm nhiệm |
| Client parse `faultstring` để retry | Vỡ vì text/locale thay đổi | Dùng public error code/QName |
| Dùng Subcode SOAP 1.2 trong SOAP 1.1 | Không có cấu trúc chuẩn tương ứng | Dùng public code trong detail |
| So prefix `ord`/`env` cứng | Kết quả sai khi prefix thay | So QName mở rộng |
| Đưa `exception.getMessage()` ra Fault | Có thể lộ SQL/stack/PII | Public error catalog + redaction |
| Sinh detail root hai lần bằng JAXB | XML bị lồng sai | Một chủ sở hữu root element |
| Tưởng XSD `OrderFault` tự sinh Fault | WSDL/runtime lệch nhau | Resolver + serializer + test |
| Coi `Receiver` nghĩa DB rollback | Có thể lỗi sau commit | Idempotency/tra trạng thái |
| Không kiểm `getFaultDetail()==null` | Null pointer phía client | Xử lý detail tùy chọn |
| Chỉ thấy `wsse:Security` là coi xác thực | Có thể giả mạo | WSS4J/WS-Security policy |
| Xuất internal node hostname | Lộ topology | URI công bố an toàn |
| Chỉ test Java exception class | Bỏ qua binding/wire semantics | SOAP-aware + interoperability tests |

## 14. Checklist thiết kế một SOAP Fault

~~~mermaid
flowchart TD
    A["Liệt kê failure modes"] --> B["Phân loại Sender/Client hoặc Receiver/Server"]
    B --> C["Chọn binding SOAP 1.1 hoặc 1.2"]
    C --> D["Định nghĩa Reason và mã lỗi công khai"]
    D --> E{"Cần typed fault detail?"}
    E -- "Có" --> F["XSD OrderFault + WSDL fault"]
    E -- "Không" --> G["Thông điệp an toàn, tối thiểu"]
    F --> H["Exception resolver / security / validator policy"]
    G --> H
    H --> I["SOAP 1.2 Subcode, Node, Role khi phù hợp"]
    I --> J["Security disclosure review"]
    J --> K["Wire tests, client compatibility, retry rules"]
~~~

Trước khi phát hành, trả lời đủ các câu hỏi:

1. SOAP binding của mỗi endpoint là 1.1 hay 1.2? Có hai binding riêng không?
2. Các lỗi có top-level code đúng nhóm và đúng phiên bản không?
3. `faultstring`/`Reason` có an toàn để công bố cho toàn bộ nhóm caller không?
4. Client cần mã nghiệp vụ nào trong `OrderFault` detail?
5. Subcode SOAP 1.2 nào cần được hiểu để xử lý detail đúng bối cảnh?
6. Node/Role/faultactor có thực sự cần không? URI có làm lộ topology không?
7. WS-Security/validation/transport có thể tạo Fault ngoài exception resolver không?
8. WSDL có mô tả typed fault và schema import đúng namespace không?
9. Hệ thống có kiểm tra absence của detail, đa ngôn ngữ, QName và SOAP version không?
10. Client có idempotency strategy khi commit thành công nhưng response thất lạc không?

### Bài tập tự kiểm tra

**Bài 1.** `faultactor` của SOAP 1.1 biểu thị điều gì? Vì sao không được dùng `buyerId` thay nó?

**Bài 2.** Trong SOAP 1.2, `Node` và `Role` khác gì nhau? Có phải mọi server đều được tự đặt `Role=role/next` không?

**Bài 3.** Vì sao `Code` và `Reason` bắt buộc? Nếu SOAP 1.2 `Detail` vắng, có kết luận Body chưa được xử lý không?

**Bài 4.** Viết XML `Sender → InvalidOrder → InvalidQuantity`. Tại sao `Subcode` lồng nhau mà không đặt hai siblings cạnh `Code`?

**Bài 5.** Một SOAP 1.1 client muốn biết `INVALID_QUANTITY`, nhưng server đang dùng SOAP 1.2 Subcode. Bạn thiết kế fault detail thế nào để hỗ trợ cả hai?

**Bài 6.** Vì sao không dùng `Reason/Text` để branch retry, và vì sao `getFaultCode()` chưa trả toàn bộ Subcodes?

**Bài 7.** Response chứa `QName {urn:example:orders:fault:v1}InvalidOrder` với prefix `a` thay vì `ord`. Mã lỗi có thay đổi không?

**Bài 8.** Nếu `SQLException.getMessage()` có internal hostname, làm sao công bố lỗi an toàn và vẫn cho hỗ trợ truy vết?

**Bài 9.** Request `SubmitOrder` đã commit nhưng client chỉ thấy timeout. Có được retry bằng requestId mới để tránh Fault không?

**Bài 10.** Nêu test để bảo đảm `Role` thật sự là SOAP role, `Node` đúng URI nguồn phát và Detail khớp XSD.

## Tài liệu tham khảo

- [W3C — SOAP 1.1, mục 4.4 SOAP Fault](https://www.w3.org/TR/soap11/): faultcode, faultstring, faultactor, detail và mã chuẩn.
- [W3C — SOAP 1.2 Part 1, mục 5.4 SOAP Fault](https://www.w3.org/TR/soap12/): Code, Reason, Node, Role, Detail, Subcode và QName.
- [Spring-WS API — SoapFault](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/SoapFault.html): fault code, reason, actor/role và detail.
- [Spring-WS API — Soap12Fault](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/soap12/Soap12Fault.html): Subcode, Node và Reason theo Locale.
- [Spring-WS API — SoapBody](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/SoapBody.html): tạo Client/Sender, Server/Receiver, VersionMismatch và MustUnderstand faults.
- [Spring-WS API — SoapFaultDetail](https://docs.spring.io/spring-ws/docs/4.1.x/api/org/springframework/ws/soap/SoapFaultDetail.html): detail entries và Result để marshal.
- [Spring Web Services Reference 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/): exception resolver, interceptor và test web services.

**Ghi nhớ:** **SOAP Fault là thông điệp protocol có cấu trúc, không phải chuỗi Java exception.** SOAP 1.1 dùng `faultcode/faultstring/faultactor/detail`, còn SOAP 1.2 dùng `Code/Reason/Node/Role/Detail` và `Subcode` phân cấp. Trong Spring-WS, dùng đúng API theo SOAP version, giữ Detail phù hợp XSD/WSDL, đọc QName thay vì prefix, không lộ thông tin nội bộ và kiểm thử cả lỗi SOAP lẫn lỗi transport.
