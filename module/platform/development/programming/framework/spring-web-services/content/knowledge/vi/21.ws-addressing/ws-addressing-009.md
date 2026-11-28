# Kiểm soát đích ReplyTo, FaultTo do bên gửi thông điệp cung cấp

> **Chương:** WS-Addressing  
> **Module:** SPRING_WEB_SERVICES — phát triển dịch vụ SOAP contract-first với Spring Web Services (Spring-WS), XSD/WSDL, JAXB/OXM, SOAP endpoint và client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích với hệ thống doanh nghiệp.

## 1. Mục tiêu: ai được quyết định nơi nhận phản hồi SOAP?

Trong tích hợp SOAP bất đồng bộ, một client có thể gửi thông điệp đến endpoint A nhưng muốn nhận kết quả tại endpoint B. **WS-Addressing** định nghĩa các thuộc tính định tuyến ở mức **SOAP message**, trong đó `ReplyTo` chỉ đích phản hồi và `FaultTo` chỉ đích thông điệp lỗi.

Điều này hữu ích cho hàng đợi, callback, tích hợp qua ESB/gateway và các quy trình xử lý kéo dài. Nhưng nếu server **tin ngay địa chỉ do caller cung cấp**, một request SOAP có thể khiến server kết nối tới một URL bất kỳ: nội bộ, metadata service, tài nguyên của tenant khác hoặc máy chủ ngoài tổ chức. Đây là một ranh giới tin cậy quan trọng, liên quan **SSRF (Server-Side Request Forgery)**, lộ dữ liệu qua callback, replay và chuyển hướng SOAP Fault.

### Kết quả học tập

Sau bài, bạn cần có thể:

1. Đọc `wsa:ReplyTo`, `wsa:FaultTo` và cấu trúc Endpoint Reference (EPR) từ SOAP Header.
2. Phân biệt `anonymous`, `none` và một callback URL thực; hiểu các giá trị mặc định.
3. Biết vì sao **địa chỉ callback là dữ liệu đầu vào chưa tin cậy**, dù XML hợp lệ theo XSD.
4. Thiết kế policy **từ chối mặc định** và chỉ cho phép destination đã được đăng ký/xác thực.
5. Phân biệt xác minh certificate/hostname TLS với quyền sử dụng một URL làm `ReplyTo`/`FaultTo`.
6. Tổ chức xử lý bất đồng bộ, correlation, queue, retry và SOAP Fault mà không làm lộ dữ liệu.
7. Viết test dương tính và âm tính cho cả WS-Addressing headers, Spring-WS runtime và network egress.

**Ý chính:** WS-Addressing mô tả **đích mà bên gửi mong muốn**; nó không tự cấp phép cho server gọi ra đích đó. Quyền được nhận response/Fault phải được quyết định theo hợp đồng và chính sách tin cậy của phía phục vụ.

## 2. WS-Addressing là gì và khác HTTP URL ra sao?

SOAP message có thể được gửi bằng HTTP, JMS hoặc transport khác. `wsa:To`, `wsa:Action`, `wsa:MessageID`, `wsa:ReplyTo`, `wsa:FaultTo` và `wsa:RelatesTo` là các thuộc tính addressing dùng để diễn đạt **ngữ nghĩa thông điệp**, không đơn thuần là một bản sao của HTTP request line.

Ví dụ SOAP 1.2 với **WS-Addressing 2005/08**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope
    xmlns:s="http://www.w3.org/2003/05/soap-envelope"
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:ord="urn:example:orders:v1">
  <s:Header>
    <wsa:To>https://soap.example.org/ws/orders</wsa:To>
    <wsa:Action>urn:example:orders:v1/SubmitOrder</wsa:Action>
    <wsa:MessageID>urn:uuid:5c0cb8c0-6c96-41b6-9d39-b83042d904b9</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>https://callback.partner.example/soap/orders</wsa:Address>
    </wsa:ReplyTo>
    <wsa:FaultTo>
      <wsa:Address>https://callback.partner.example/soap/faults</wsa:Address>
    </wsa:FaultTo>
  </s:Header>
  <s:Body>
    <ord:SubmitOrderRequest>
      <ord:orderId>ORD-1001</ord:orderId>
    </ord:SubmitOrderRequest>
  </s:Body>
</s:Envelope>
~~~

Đây là **một SOAP Envelope minh họa**, không phải request được cam kết phù hợp mọi WSDL, WS-Addressing Metadata hoặc WS-SecurityPolicy. URL `example.org`/`partner.example` là địa chỉ dành cho tài liệu; phải thay bằng endpoint đã được cấp phép trong môi trường thực.

| Thuộc tính | Vai trò | Nguồn sự thật cần kiểm tra |
|---|---|---|
| HTTP POST URL | Địa chỉ kết nối tới SOAP receiver | Cấu hình client/transport/gateway |
| `wsa:To` | Đích logic của message | WSDL/addressing policy và receiver identity |
| `wsa:Action` | Loại hành động SOAP/WS-Addressing | WSDL/WS-A metadata và operation mapping |
| `wsa:MessageID` | Định danh message phục vụ correlation | Cú pháp, uniqueness và replay policy |
| `wsa:ReplyTo` | EPR mà sender muốn nhận non-fault reply | Callback authorization và delivery policy |
| `wsa:FaultTo` | EPR mà sender muốn nhận fault | **Policy độc lập** cho thông tin lỗi |
| `wsa:RelatesTo` | Liên hệ message trả về với message trước | Correlation state do hệ thống đã lưu |

### 2.1. EPR không chỉ là một chuỗi URL

Một `wsa:EndpointReference` thường có `wsa:Address` và có thể có `wsa:ReferenceParameters`, `wsa:Metadata` hoặc extension elements:

~~~xml
<wsa:ReplyTo
    xmlns:wsa="http://www.w3.org/2005/08/addressing"
    xmlns:m="urn:example:callbacks:meta:v1">
  <wsa:Address>https://callback.partner.example/soap/orders</wsa:Address>
  <wsa:ReferenceParameters>
    <m:RouteToken>route-001</m:RouteToken>
  </wsa:ReferenceParameters>
</wsa:ReplyTo>
~~~

**Không coi ReferenceParameters do caller gửi là token xác thực.** Trong các kiến trúc hỗ trợ EPR đầy đủ, reference parameters có thể được đưa vào thông điệp phản hồi dưới dạng SOAP headers. Nếu sao chép chúng mà chưa kiểm soát, server có thể vô tình truyền dữ liệu chưa xác thực, ảnh hưởng namespace/header processing hoặc gây lộ thông tin.

Một policy đơn giản, an toàn nên **từ chối ReferenceParameters/Metadata không được khai báo trước**, chỉ chấp nhận danh sách QName/shape cụ thể khi contract thật sự cần.

### 2.2. Prefix và phiên bản WS-Addressing

Các ví dụ dùng namespace chuẩn:

~~~text
http://www.w3.org/2005/08/addressing
~~~

Một số hệ thống legacy dùng phiên bản khác, chẳng hạn:

~~~text
http://schemas.xmlsoap.org/ws/2004/08/addressing
~~~

Hai namespace này **không tương đương**. XML prefix `wsa` có thể đổi tên; điều quyết định là namespace URI và local name. Các URI đặc biệt `anonymous`/`none` cũng gắn với **phiên bản**. Không đổi mỗi prefix hoặc chỉ sửa một URI rồi giả định client/server tương thích; phải kiểm tra WSDL binding và implementation Spring-WS đối tác dùng.

## 3. ReplyTo, FaultTo và các giá trị đặc biệt

### 3.1. `ReplyTo`: đường phản hồi bình thường

`ReplyTo` cung cấp endpoint reference mà **sender yêu cầu** cho non-fault response. Với WS-Addressing 2005/08, một địa chỉ đặc biệt phổ biến:

~~~text
http://www.w3.org/2005/08/addressing/anonymous
~~~

Nó biểu thị *anonymous endpoint*: response được gửi qua một cơ chế phản hồi ẩn danh do transport/binding quy định, ví dụ dùng HTTP request-response channel hiện tại khi binding cho phép.

Một địa chỉ khác:

~~~text
http://www.w3.org/2005/08/addressing/none
~~~

đại diện endpoint **không nhận message** theo semantics của WS-Addressing. Không nhầm `none` với URL do hệ thống vận hành; với một operation bắt buộc có response, việc caller đặt `none` phải được kiểm tra đối chiếu MEP/policy trước khi chấp nhận.

### 3.2. `FaultTo`: đường riêng cho SOAP Fault

`FaultTo` có thể hướng **fault message** tới một endpoint khác với response thành công.

Ví dụ:

~~~xml
<wsa:ReplyTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>
    https://callback.partner.example/soap/results
  </wsa:Address>
</wsa:ReplyTo>

<wsa:FaultTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  <wsa:Address>
    https://callback.partner.example/soap/faults
  </wsa:Address>
</wsa:FaultTo>
~~~

Trong XML thật, `wsa:Address` thường nên chứa URI không có whitespace thừa ngoài cách serialize được đối tác hỗ trợ. Với security profile yêu cầu WS-Security chữ ký, **không tự trim/mutate signed XML sau xác minh**. Ví dụ trên chỉ ngắt dòng cho dễ đọc.

**Nguy cơ đặc thù:** SOAP Fault có thể chứa thông tin về contract, trạng thái xử lý hoặc detail nghiệp vụ. Vì vậy gửi Fault tới một URL tùy ý cũng là **đường rò rỉ thông tin**, không kém phản hồi thành công.

### 3.3. Giá trị mặc định không có nghĩa được phép gửi ra ngoài

Trong mô hình WS-Addressing 2005/08 thường gặp:

- Nếu `ReplyTo` không được khai báo, reply endpoint được hiểu là anonymous endpoint.
- Nếu `FaultTo` không được khai báo, fault endpoint kế thừa reply endpoint theo semantics chuẩn.
- Binding/MEP (request-response, one-way, asynchronous) có thể có ràng buộc riêng về anonymous/non-anonymous và cách gửi trả.
- Giá trị `none` có semantics đặc biệt, không phải callback URL.

**Cần kiểm tra SOAP binding/WS-Addressing specification đúng phiên bản** trước khi áp dụng mặc định vào code. Đặc biệt, không tự “fallback FaultTo về một URL cố định” nếu policy của đối tác hoặc quy định về faulting bị vi phạm.

### 3.4. Ma trận đích ở mức nghiệp vụ

| ReplyTo gửi lên | FaultTo gửi lên | Quyết định khuyến nghị |
|---|---|---|
| Vắng | Vắng | Áp dụng default anonymous **nếu binding cho phép** |
| anonymous | Vắng | Reply/fault dùng anonymous response theo binding |
| URL callback đã đăng ký | Vắng | Có thể dùng callback cho reply và mặc định fault theo policy |
| URL callback đã đăng ký | URL fault đã đăng ký | Chỉ chấp nhận khi **cả hai** đều được authorize |
| URL chưa đăng ký | Bất kỳ | Từ chối, **không kết nối thử** địa chỉ đó |
| anonymous | URL fault chưa đăng ký | Từ chối hoặc xử lý theo lỗi policy, không gửi fault ra URL lạ |
| none | Bất kỳ | Kiểm tra MEP; không tự hủy response bắt buộc |
| Giá trị schema/URI không hợp lệ | Bất kỳ | Reject trước khi lập outbound callback job |

**Không** coi “HTTPS URL” là đủ điều kiện được gọi: HTTPS chỉ cho biết có thể dùng TLS với một host, không xác thực rằng host đó **được phép nhận dữ liệu của tenant này**.

## 4. Spring-WS xử lý WS-Addressing ở tầng nào?

Spring-WS có khả năng làm việc với WS-Addressing ở phía client/server tùy phiên bản và cấu hình. Các khái niệm liên quan:

- **Client:** `WebServiceTemplate`, `ActionCallback` và hạ tầng addressing thích hợp cho việc sinh headers.
- **Server:** `MessageDispatcherServlet`, endpoint mappings/annotations và WS-Addressing support có thể đọc `wsa:Action`, `To` hoặc các headers liên quan theo cấu hình.
- **Security:** WS-Security/WSS4J và TLS client/server là các lớp riêng; header addressing tồn tại **không** chứng minh caller đã xác thực.
- **Out-of-band callback:** có thể cần **một producer/send service/queue riêng** để gửi SOAP tới non-anonymous ReplyTo/FaultTo, tùy runtime và thiết kế tích hợp.

Không được giả định rằng chỉ bật `@EnableWs` là Spring-WS sẽ **tự phát HTTP POST tới mọi ReplyTo/FaultTo**. Bản thân `@Endpoint` xử lý SOAP payload và tạo response; hành vi dispatch bất đồng bộ/outbound message được quyết định bởi framework/configuration, binding và code ứng dụng.

### 4.1. Không nhầm ReplyTo với @PayloadRoot

Ví dụ request Body:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
</ord:SubmitOrderRequest>
~~~

`@PayloadRoot(namespace="urn:example:orders:v1", localPart="SubmitOrderRequest")` giúp chọn **method xử lý request**. Nó không kiểm tra URL ở `wsa:ReplyTo`, không kiểm tra Certificate của callback host và cũng không bảo đảm server sẽ gửi response đến URL đó.

Một request có QName Body đúng và JAXB unmarshal thành công vẫn có thể có **ReplyTo/FaultTo độc hại**.

### 4.2. Callback policy nên đặt ở biên giới tin cậy

Không chỉ đọc các headers rồi giao ngay cho business service để mở kết nối. Đường xử lý được khuyến nghị:

~~~mermaid
flowchart TD
    A["SOAP request + WS-A headers"] --> B["Parser limits + SOAP binding"]
    B --> C["Authentication / WS-Security verify"]
    C --> D["XSD + WS-A semantic checks"]
    D --> E["Policy: ReplyTo/FaultTo allowlist cho principal/tenant"]
    E -->|Được phép| F["Business operation"]
    E -->|Bị từ chối| G["Fault/HTTP policy error không rò rỉ"]
    F --> H["Outbox job: approved destination key"]
    H --> I["Egress transport chỉ nhận target từ registry"]
    I --> J["TLS verify + callback SOAP response"]
~~~

Thứ tự cụ thể của authentication, decryption, signature verification và schema validation phụ thuộc WS-SecurityPolicy/binding. Sơ đồ thể hiện **ranh giới trách nhiệm**, không khẳng định mỗi Spring-WS version tự thực hiện các bước trên. Quan trọng nhất: **quyết định authorize destination xảy ra trước khi hệ thống gửi message ra ngoài**.

## 5. Threat model: tại sao địa chỉ callback là dữ liệu nhạy cảm?

Một địa chỉ outbound do caller đề xuất có thể dẫn tới:

1. **SSRF:** server kết nối tới host nội bộ mà attacker không gọi trực tiếp được.
2. **Data exfiltration:** response chứa thông tin đơn hàng/khách hàng gửi tới domain của attacker.
3. **Fault exfiltration:** thông tin lỗi, stack/message metadata hoặc dữ liệu nghiệp vụ bị gửi tới `FaultTo` khác.
4. **Cross-tenant delivery:** tenant A ép server gửi kết quả của A/B đến endpoint do tenant khác kiểm soát.
5. **DNS rebinding / redirect bypass:** URL ban đầu trông hợp lệ, nhưng DNS hoặc HTTP redirect dẫn tới IP/host cấm.
6. **Connection exhaustion:** attacker cung cấp host chậm/không phản hồi, chiếm threads, pools, retries và đĩa của queue.
7. **Log injection:** URI hoặc ReferenceParameters được ghi vào logs/metrics nguyên dạng, làm tăng cardinality hoặc đưa dữ liệu nhạy cảm vào hệ giám sát.
8. **Message integrity failure:** header addressing đã ký bị sửa sau verify; hoặc callback được ký gửi đi sai signed references/policy.
9. **Protocol confusion:** sai WS-Addressing namespace, SOAP version, HTTP binding hoặc `anonymous`/`none` dẫn tới gửi nhầm message.

### 5.1. Ví dụ URL không được dùng làm callback

Các chuỗi sau chỉ dùng trong **tình huống kiểm thử chính sách**, không phải gợi ý triển khai:

~~~text
http://127.0.0.1:8080/admin
http://[::1]:8080/metrics
http://169.254.169.254/latest/meta-data/
http://service.namespace.svc.cluster.local/internal
file:///etc/passwd
https://unregistered-attacker.example/collect
https://approved.partner.example/redirect-to-other-host
~~~

Một số URL dùng địa chỉ link-local hoặc hostname nội bộ để minh họa **những đích cần ngăn**, không nhất thiết khả dụng từ môi trường test hiện tại.

Chỉ kiểm tra bằng `startsWith("https://approved.partner.example")` là **sai**: nó có thể cho phép các URL như `https://approved.partner.example.attacker.example`. Thậm chí kiểm tra **hostname chính xác** cũng chưa đủ nếu hệ thống cho phép mọi path/query/port/redirect của hostname và endpoint đó không kiểm soát quyền nhận dữ liệu.

### 5.2. Tin HTTPS không đồng nghĩa tin nơi nhận

Một attacker có thể sở hữu một domain công khai có certificate TLS hoàn toàn hợp lệ. HTTPS hostname verification chỉ chứng minh client đang nói chuyện với domain đó, **không chứng minh domain nằm trong danh sách đối tác được phép**.

Do đó cần **hai lớp kiểm tra**:

- **Business destination authorization:** principal/tenant, operation, callback registration, URI đầy đủ và loại message (reply hoặc fault).
- **Transport identity verification:** TLS certificate chain, DNS/IP SAN matching, mTLS credentials, SNI và egress restrictions.

Chỉ một trong hai lớp là chưa đủ.

## 6. Chính sách đích phản hồi: mặc định từ chối, không “URL nào cũng được”

Một thiết kế an toàn nên phân biệt **ba loại destination**:

1. **Anonymous:** trả qua HTTP request-response channel theo SOAP/WS-Addressing binding.
2. **None:** không gửi một loại message nhất định, **chỉ khi** MEP/contract/policy cho phép.
3. **Preapproved callback:** gửi đến endpoint đã được **đăng ký và ràng buộc với một identity/tenant/operation** mà server tin cậy.

Không nên có loại “arbitrary user-supplied URL”. Nếu sản phẩm buộc đối tác tự quản lý callback URL, cần một **quy trình đăng ký/verify ownership/phê duyệt** tách khỏi mỗi SOAP invocation.

### 6.1. Dữ liệu cần lưu trong callback registry

Một bản ghi được quản trị có thể chứa:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| Partner ID | `PARTNER_A` | Được xác định sau authentication, không lấy trực tiếp từ Body |
| Tenant ID | `TENANT_42` | Cách ly dữ liệu giữa các tenant |
| Operation code | `SUBMIT_ORDER` | Không phải operation nào cũng được dùng callback |
| Allowed reply URI | `https://cb.partner-a.example/ws/results` | Exact destination do tổ chức duyệt |
| Allowed fault URI | `https://cb.partner-a.example/ws/faults` | Có thể khác reply endpoint |
| Allowed auth mode | mTLS, WS-Security signed callback | Kiểm soát peer/authentication |
| Response schema/policy | `OrdersResult v1` | Biết payload nào được phép gửi |
| Callback SLA | timeout, retry budget, expiry | Tránh gửi vô hạn |
| Status | active, suspended, pending verification | Ngăn gọi endpoint chưa phê duyệt |
| Network egress policy | Route/egress gateway ID | Chặn vượt mạng nội bộ và SSRF |

Registry phải được quản lý bởi **kênh có xác thực và audit**, không được tự ghi mới từ `wsa:ReplyTo` của request SOAP. Nếu URL được thay đổi, áp dụng lại xác minh DNS, TLS, quyền sở hữu, policy và version.

### 6.2. Policy theo message type

Ví dụ:

| Principal | Operation | ReplyTo hợp lệ | FaultTo hợp lệ |
|---|---|---|---|
| `PARTNER_A` | `SUBMIT_ORDER` | anonymous hoặc `/ws/results` đã đăng ký | anonymous hoặc `/ws/faults` đã đăng ký |
| `PARTNER_A` | `GET_ORDER` | anonymous | anonymous |
| `PARTNER_B` | `SUBMIT_ORDER` | callback riêng của B | fault callback riêng của B |
| Không xác thực | Bất kỳ | Từ chối các non-anonymous callbacks | Từ chối các non-anonymous callbacks |

**Không suy luận quyền từ giá trị `wsa:To`, `MessageID` hay `ReplyTo`.** Identity phải xuất phát từ TLS client certificate, WS-Security token được xác minh hoặc cơ chế authentication được chấp thuận. Với cùng partner có nhiều tenant, phải ràng buộc authorization ở **cả hai chiều**: tenant nào được gửi request và tenant nào sở hữu callback target.

### 6.3. Tiêu chí URL nên kiểm tra

Đối với HTTP(S) callback, nếu contract chỉ cho phép HTTPS:

- URI tuyệt đối, scheme `https`; không dùng `http`, `file`, `ftp` hoặc custom URI schemes.
- Host là FQDN đã được tổ chức phê duyệt, không chứa userinfo/password.
- Hostname được quản lý ở registry; có DNS SAN và certificate trust phù hợp.
- Port theo cấu hình đã duyệt, không cho caller quét port tùy ý.
- Path **chính xác** được duyệt; không dùng allowlist theo prefix path.
- Query và fragment **không được** tự thêm từ request nếu contract không cho phép.
- Không cho HTTP redirect tự ý đưa request sang host/path khác.
- Chặn dải IP nội bộ, loopback, link-local, metadata và địa chỉ không được phép qua **egress controls tại thời điểm kết nối**, kể cả khi DNS thay đổi.
- Không cho caller tự chọn proxy, HTTP Host, SNI, certificate alias hoặc TLS verifier.
- Không sử dụng credentials/Authorization token của một đối tác để gọi endpoint của đối tác khác.

**Bắt buộc:** kiểm tra URL trong code **không thay** network egress controls. Việc tra DNS khi nhận request rồi tin IP đó mãi về sau có thể bị DNS rebinding/TOCTOU; phải kiểm soát kết nối thực bằng chính sách của HTTP client/egress proxy/firewall.

## 7. Quy trình quyết định an toàn cho ReplyTo/FaultTo

Nên thiết kế một hàm **quyết định** thuần, không gửi network request. Hàm chỉ biến dữ liệu chưa tin cậy thành **approved routing decision**, rồi transport service dùng đối tượng đã được phê duyệt để thực thi.

~~~mermaid
flowchart TD
  A["SOAP Header: ReplyTo / FaultTo"] --> B["Giới hạn kích thước + parse namespace-aware"]
  B --> C{"EPR/URI/headers đúng profile?"}
  C -->|Không| R["Reject, không gọi outbound URL"]
  C -->|Có| D["Lấy trusted partner/tenant từ authenticated context"]
  D --> E["Áp dụng default ReplyTo và FaultTo theo WS-A version"]
  E --> F{"MEP cho anonymous/none/external?"}
  F -->|Không| R
  F -->|Có| G{"URI nằm trong exact allowlist đúng identity/operation?"}
  G -->|Không| R
  G -->|Có| H["ApprovedRouting: reply ID + fault ID"]
  H --> I["Persist job + trusted destination key"]
  I --> J["Egress sender: TLS/mTLS + allowlisted network"]
~~~

Các kiểm soát semantic cần diễn ra **trước tạo callback job**. Với response trực tiếp anonymous, có thể không có HTTP outbound call thứ hai. Với external callback, phải phân biệt "được phép" và "đã gửi thành công".

### 7.1. Cách xử lý khi chỉ một đích hợp lệ

Giả sử `ReplyTo` hợp lệ nhưng `FaultTo` không hợp lệ. Không nên:

- Gửi success reply như thường rồi lén bỏ qua FaultTo mà không có policy rõ.
- Thử gọi FaultTo sai để “kiểm tra có phải endpoint thật không”.
- Fallback FaultTo về một URL do caller đề xuất khác.
- Ghi nguyên URL độc hại vào log hoặc SOAP Fault detail.

Cách đơn giản là **reject toàn bộ request theo routing policy**, không xếp lịch xử lý nghiệp vụ có side effect. Nếu chuẩn/binding quy định cách phát thông điệp lỗi addressing, phải dùng **kênh an toàn đã biết**, ví dụ HTTP response channel hoặc cơ chế protocol-specific, tránh trả lỗi cho chính URL chưa được authorize.

### 7.2. Từ chối không được tạo vòng lặp Fault

Nếu chính `FaultTo` bị từ chối, tạo một SOAP Fault rồi cố gửi Fault ấy tới `FaultTo` là **tự biến lỗi validation thành một SSRF**. Tương tự, nếu callback fault handler gặp lỗi và tiếp tục gửi lỗi của lỗi tới một `FaultTo` khác, có nguy cơ vòng lặp retry/fault storm.

Hãy xác định rõ *fault-on-fault policy*: có thể chấm dứt tại transport response hiện tại, ghi log tối thiểu, hoặc chuyển sang dead-letter/internal incident; **không bao giờ** dùng đích đã bị reject.

## 8. Java 17: xây bộ kiểm tra đích mà không thực hiện HTTP

Đoạn mã dưới đây minh họa **policy thuần Java**: nhận identity **đã xác thực** và địa chỉ được trích từ WS-Addressing header, áp dụng mặc định anonymous/FaultTo, phân biệt `none` và chỉ cho phép exact HTTPS callbacks đã đăng ký.

Mã tập trung vào **địa chỉ**, không tự triển khai WS-Addressing EPR XML parser, WS-Security hay HTTP sending. Nó giả định một tầng trước đã bảo đảm `ReplyTo/FaultTo` mỗi loại xuất hiện tối đa một lần, namespace đúng, không có unsupported `ReferenceParameters`/`Metadata` và request hợp lệ về kích thước/header policy.

~~~java
package com.example.soap.addressing;

import java.net.URI;
import java.util.Map;
import java.util.Set;

public final class CallbackDestinationPolicy {

    public static final String ANONYMOUS =
            "http://www.w3.org/2005/08/addressing/anonymous";
    public static final String NONE =
            "http://www.w3.org/2005/08/addressing/none";

    public enum Kind {
        ANONYMOUS, NONE, APPROVED_CALLBACK
    }

    public record Destination(Kind kind, String exactUri) {}

    public record Routing(Destination reply, Destination fault) {}

    public record PolicyKey(String trustedPartner, String operation) {}

    private final Map<PolicyKey, Set<String>> allowedReplies;
    private final Map<PolicyKey, Set<String>> allowedFaults;

    public CallbackDestinationPolicy(
            Map<PolicyKey, Set<String>> allowedReplies,
            Map<PolicyKey, Set<String>> allowedFaults) {
        // Production: deep-copy/freeze registry và version hóa chính sách.
        this.allowedReplies = Map.copyOf(allowedReplies);
        this.allowedFaults = Map.copyOf(allowedFaults);
    }

    public Routing authorize(
            PolicyKey trustedKey,
            String replyTo,
            String faultTo,
            boolean externalReplyAllowed,
            boolean suppressReplyAllowed) {

        if (trustedKey == null
                || trustedKey.trustedPartner() == null
                || trustedKey.operation() == null) {
            throw new IllegalArgumentException(
                    "Missing authenticated routing context");
        }

        String effectiveReply =
                replyTo == null ? ANONYMOUS : replyTo;
        String effectiveFault =
                faultTo == null ? effectiveReply : faultTo;

        Destination reply = authorizeOne(
                effectiveReply,
                allowedReplies.getOrDefault(trustedKey, Set.of()),
                externalReplyAllowed,
                suppressReplyAllowed);

        Destination fault = authorizeOne(
                effectiveFault,
                allowedFaults.getOrDefault(trustedKey, Set.of()),
                externalReplyAllowed,
                false); // Ví dụ strict policy: không cho suppress fault.

        return new Routing(reply, fault);
    }

    private static Destination authorizeOne(
            String raw,
            Set<String> approved,
            boolean externalAllowed,
            boolean noneAllowed) {

        if (ANONYMOUS.equals(raw)) {
            return new Destination(Kind.ANONYMOUS, null);
        }

        if (NONE.equals(raw)) {
            if (!noneAllowed) {
                throw new IllegalArgumentException(
                        "None destination not allowed");
            }
            return new Destination(Kind.NONE, null);
        }

        if (!externalAllowed || raw == null
                || raw.length() > 1024) {
            throw new IllegalArgumentException(
                    "External callback not allowed");
        }

        URI uri;
        try {
            uri = URI.create(raw);
        } catch (IllegalArgumentException ex) {
            throw new IllegalArgumentException(
                    "Malformed callback URI", ex);
        }

        if (!"https".equals(uri.getScheme())
                || uri.getHost() == null
                || uri.getRawUserInfo() != null
                || uri.getRawQuery() != null
                || uri.getRawFragment() != null
                || (uri.getPort() != -1 && uri.getPort() != 443)
                || !raw.equals(uri.toASCIIString())
                || !approved.contains(raw)) {
            throw new IllegalArgumentException(
                    "Callback destination not approved");
        }

        return new Destination(Kind.APPROVED_CALLBACK, raw);
    }
}
~~~

**Giới hạn có chủ ý của ví dụ:**

- `trustedPartner` và `operation` **phải đến từ authenticated context và mapping đã được kiểm chứng**, không lấy trực tiếp từ SOAP headers chưa verify.
- `Map.copyOf` **không deep-copy** các `Set` bên trong; trong production phải sao chép thành các `Set.copyOf(...)` và bảo vệ policy registry không bị chỉnh khi chạy.
- `externalReplyAllowed` và `suppressReplyAllowed` chỉ là cấu hình của operation/MEP từ server, **không được caller tự truyền giá trị**.
- So URI theo **chuỗi chính xác** khiến những representation tương đương cú pháp nhưng không trong allowlist bị reject. Đây là quyết định bảo thủ, thuận lợi cho audit.
- Các ký tự percent-encoding, IPv6, IDN, redirect và DNS rebinding còn phải chịu **network egress policy**; allowlist trong Java không phải tường lửa.
- Khi `FaultTo` vắng, policy dùng reply target như semantics WS-A 2005/08 thông dụng, rồi **vẫn authorize lại** nó theo allowlist fault. Không mặc nhiên cho phép callback reply cũng được nhận fault.
- Mẫu strict policy từ chối `FaultTo=none`. Hệ thống one-way hoặc profile khác có thể cần chính sách rõ ràng khác; không copy cứng hành vi này cho mọi MEP.

### 8.1. Khởi tạo policy từ cấu hình đã duyệt

~~~java
import java.util.Map;
import java.util.Set;

var partnerA = new CallbackDestinationPolicy.PolicyKey(
        "PARTNER_A", "SUBMIT_ORDER");

var policy = new CallbackDestinationPolicy(
        Map.of(partnerA, Set.of(
                "https://cb.partner-a.example/ws/results")),
        Map.of(partnerA, Set.of(
                "https://cb.partner-a.example/ws/faults")));

var routing = policy.authorize(
        partnerA,
        "https://cb.partner-a.example/ws/results",
        "https://cb.partner-a.example/ws/faults",
        true,
        false);
~~~

Một `PARTNER_A` khác không được dùng lại callback của A nếu registry không cho phép; không tự điền khóa `partnerA` bằng trường `tenantId` từ SOAP Body. Ví dụ trên chỉ tạo **routing decision**. Nó không mở socket hoặc gửi SOAP, nên có thể kiểm thử bằng unit tests trước khi triển khai transport.

### 8.2. Tách destination key khỏi request XML khi gửi thật

Một hệ thống production nên lưu callback job như sau:

~~~text
messageId = urn:uuid:...
authenticatedPartner = PARTNER_A
operationCode = SUBMIT_ORDER
approvedReplyDestinationId = PARTNER_A_RESULTS_V1
approvedFaultDestinationId = PARTNER_A_FAULTS_V1
replyPayloadRef = internal-storage-key
expiresAt = ...
status = PENDING
~~~

Job chỉ lưu **destination ID** tham chiếu registry tin cậy, không chuyển URI chưa xác thực từ SOAP Header thẳng cho HTTP client. Khi worker gửi, nó lookup destination theo ID, áp lại egress controls/TLS policy và kiểm tra job còn hợp lệ. Cần lưu **policy version** hoặc xử lý thay đổi registration cho job đã xếp hàng theo quy tắc nghiệp vụ.

## 9. Đọc WS-Addressing headers an toàn trong Spring-WS

Trước khi gọi policy ở mục 8, một thành phần adapter phải trích được thông tin từ SOAP Header. Việc này cần tôn trọng **namespace, EPR shape, SOAP actor/role, header cardinality và message integrity**.

### 9.1. Không dùng regex hoặc so tên thẻ theo prefix

Đừng parse SOAP XML bằng:

~~~java
// Phản ví dụ: không dùng cách tìm tag trong XML string.
String replyUrl = soapXml.split("<wsa:Address>")[1]
                         .split("</wsa:Address>")[0];
~~~

Client có thể dùng prefix `a` thay `wsa`, khai báo default namespace, thay whitespace hoặc có nhiều `wsa:Address` trong các EPR khác nhau. Regex không thể phân biệt `ReplyTo/Address` với `FaultTo/Address` và dễ bỏ qua XML namespace/security semantics.

Nếu truy cập SOAP Header bằng API Spring-WS, nên phân biệt **QName đầy đủ**:

~~~text
{http://www.w3.org/2005/08/addressing}ReplyTo
{http://www.w3.org/2005/08/addressing}FaultTo
{http://www.w3.org/2005/08/addressing}Address
~~~

Chỉ sau khi xác định đúng parent EPR và đúng namespace, mới đọc text của Address. `Address` trong một EPR khác không thể thay `ReplyTo`.

### 9.2. Khi dùng SOAP Header API

Spring-WS cung cấp `org.springframework.ws.soap.SoapMessage` và `SoapHeader` để thao tác với các phần tử header. Các implementation cũng có WS-Addressing abstractions trong package `org.springframework.ws.soap.addressing`; hãy ưu tiên chúng khi phiên bản đang dùng hỗ trợ và phù hợp WSDL/binding.

Quy trình adapter nên:

1. Xác minh request đã được parser SOAP xử lý và giới hạn XML resource.
2. Xác định **namespace WS-Addressing đúng version**; nếu hỗ trợ nhiều versions, tách policy và test cho từng version.
3. Chỉ lấy các header được hướng tới receiver/role phù hợp; tuân thủ `mustUnderstand` và SOAP actor/role semantics.
4. Kiểm tra **tối đa một** `ReplyTo` và **tối đa một** `FaultTo` theo profile; duplicate hay headers xung đột phải bị từ chối.
5. Mỗi EPR phải có một `wsa:Address` hợp lệ; kiểm tra thuộc tính/extension mà contract cho phép.
6. Giới hạn chiều dài URI và kích thước `ReferenceParameters`/`Metadata`.
7. Nếu có WS-Security signing policy cho addressing headers, **xác minh** trước khi tin nội dung.
8. Truyền **địa chỉ dạng dữ liệu** và trusted context vào policy; không cho parser tự HTTP GET/POST đến URL đó.

Với Java DOM hoặc XPath tự viết, bật xử lý namespace; tuyệt đối không cho tự parse lại SOAP raw XML bằng XML parser cho phép XXE/DTD/external entities. Một callback address chỉ là **text/URI**, không phải đường dẫn schema cần tải về.

### 9.3. Ví dụ tách dữ liệu khỏi transport

Một DTO nội bộ sau parsing có thể là:

~~~java
public record UntrustedAddressingInput(
        String messageId,
        String action,
        String replyToAddress,
        String faultToAddress,
        boolean hasUnsupportedReferenceParameters) {
}
~~~

Đây là lớp dữ liệu **chưa được authorize**. Nó không nên có method `send()`, `openConnection()` hoặc giữ `HttpClient`. Một lớp policy khác xác minh `authenticatedPrincipal`, operation, EPR semantics rồi tạo `ApprovedRouting`.

Nếu `hasUnsupportedReferenceParameters` là true, **từ chối** khi contract không định nghĩa extension. Không âm thầm bỏ chúng nếu phía gửi kỳ vọng chúng được chuyển tiếp, vì điều đó tạo sự khác biệt giữa request và callback; nhưng cũng không sao chép chúng tùy ý khi chưa tin.

### 9.4. Không dùng XPath local-name() bỏ qua namespace

Một biểu thức như:

~~~xpath
//*[local-name()='ReplyTo']/*[local-name()='Address']
~~~

có thể chọn XML có tên tương tự ở namespace khác. Nếu dùng XPath, phải ràng buộc URI:

~~~xpath
./s:Header/wsa:ReplyTo/wsa:Address
~~~

với `s` là namespace SOAP version hiện tại, `wsa` trỏ tới `http://www.w3.org/2005/08/addressing` và context là SOAP Envelope. Nếu context đã là `SoapHeader` hoặc một Node Header, đường dẫn phải tương ứng; không dùng `s:Header` nếu nó không nằm trong context. XPath chỉ giúp **đọc XML**, không thay xác minh WS-Security, authorization hoặc outbound URL controls.

## 10. Trust boundary: caller, tenant và chữ ký addressing headers

### 10.1. Một địa chỉ được ký vẫn chưa chắc được phép

Giả sử client có certificate được CA đối tác tin cậy và ký SOAP Body/Headers. Việc chữ ký hợp lệ chỉ nói rằng message do principal có khóa phù hợp tạo ra và phần được ký **không bị thay đổi** theo validation policy. Nó **không tự cấp quyền** cho principal đó yêu cầu callback tới IP nội bộ hoặc callback của tenant khác.

Một authorization decision tối thiểu phải kiểm tra:

~~~text
verified identity
+ tenant binding
+ SOAP operation / Action
+ message exchange pattern
+ allowed ReplyTo destination
+ allowed FaultTo destination
+ valid registration status
+ transport/certificate/egress policy
= approved routing decision
~~~

Không lấy `partnerId` hoặc `tenantId` từ một SOAP Header không được xác thực làm danh tính tin cậy. Ngay cả header đã ký cũng cần mapping tới quyền của **principal đang ký** và policy ở phía server.

### 10.2. Signature wrapping và header tampering

WS-Security chữ ký có thể bảo vệ SOAP Body, `wsa:To`, `wsa:Action`, `wsa:ReplyTo`, `wsa:FaultTo`, `wsa:MessageID` tùy profile. Nếu addressing headers **không nằm trong phần được ký**, một trung gian hoặc actor không tin cậy có thể sửa địa chỉ mà Body signature vẫn hợp lệ.

Do đó với callback bất đồng bộ có thông tin nhạy cảm:

- Quy định **những WS-A headers nào phải được ký** trong WS-SecurityPolicy, nếu message-level integrity cần bảo vệ chúng.
- Dùng thư viện WSS4J/WS-Security với xác minh reference IDs và policy, không tự tin một thẻ `ds:Signature` có mặt.
- Kiểm tra dấu hiệu XML Signature Wrapping: phần được verify có phải đúng phần mà routing parser thực sự sử dụng?
- Không sửa signed `ReplyTo/FaultTo` sau verify để “chuẩn hóa” URL rồi tiếp tục xử lý như thể chữ ký vẫn nguyên vẹn.
- Tránh log raw signatures, token, certificate chain và SOAP payload; chỉ ghi kết quả policy ở mức metadata.

Đặc biệt, dùng HTTP TLS **không** ngăn một client đã được xác thực gửi `ReplyTo` độc hại. Callback authorization vẫn bắt buộc ngay cả với mTLS.

### 10.3. MessageID, replay và correlation

`wsa:MessageID` là định danh do sender cung cấp, **không phải mật khẩu hoặc bằng chứng quyền sở hữu**. Một callback response có thể có `wsa:RelatesTo` để liên hệ request gốc:

~~~xml
<wsa:MessageID xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:ba2a34d4-efbd-4622-b786-5a55d9943382
</wsa:MessageID>

<wsa:RelatesTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:5c0cb8c0-6c96-41b6-9d39-b83042d904b9
</wsa:RelatesTo>
~~~

Trong hệ thống xử lý bất đồng bộ:

- Áp dụng định dạng/giới hạn độ dài của MessageID theo contract; không lưu ID tùy ý làm đường dẫn file hoặc metric label.
- Gắn ID với **trusted principal/tenant**, operation và request state.
- Có chính sách phát hiện replay/duplicate và TTL; không dùng MessageID đơn lẻ làm authorization.
- Khi tạo callback, `RelatesTo` phải tham chiếu request **đã được chấp nhận và lưu**, không phải một ID do caller gợi ý ngoài phạm vi.
- Đảm bảo request từ hai tenants trùng MessageID không bị trộn kết quả.
- Khi nhận callback từ đối tác, cũng phải xác thực **callback sender** và correlation, không chỉ tìm một ID khớp trong database.

## 11. Đồng bộ và bất đồng bộ: không phải ReplyTo nào cũng tạo HTTP call thứ hai

### 11.1. Anonymous reply

Với SOAP-over-HTTP request-response truyền thống, `ReplyTo=anonymous` có thể được đáp ứng qua **HTTP response hiện tại**, theo cách binding hỗ trợ. Lợi ích:

- Client nhận SOAP response/Fault trực tiếp.
- Không cần server tạo outbound connection tới URL do caller khai báo.
- Đơn giản hơn trong timeout/correlation và ranh giới mạng.

Tuy nhiên, operation kéo dài có thể cần thiết kế asynchronous rõ ràng. Không lấy `anonymous` làm lý do giữ HTTP connection mở vô hạn nếu business workflow kéo dài hàng giờ.

### 11.2. Non-anonymous reply

Với callback URL đã duyệt:

~~~mermaid
sequenceDiagram
    participant C as Partner SOAP sender
    participant S as Spring-WS receiver
    participant DB as Internal outbox
    participant W as Callback worker
    participant R as Approved reply endpoint

    C->>S: SOAP request + ReplyTo/FaultTo
    S->>S: Authenticate, validate contract, authorize EPR
    S->>DB: Persist accepted request + approved target ID
    S-->>C: Transport acknowledgment theo binding
    DB-->>W: Durable callback task
    W->>W: Resolve approved endpoint + egress/TLS policy
    W->>R: SOAP response + RelatesTo
    R-->>W: Callback transport/protocol acknowledgment
    W->>DB: Delivered / retryable / dead-letter state
~~~

**Không khẳng định mọi WS-Addressing implementation trả HTTP 202 trong tình huống này.** Transport acknowledgment/status và xử lý response tùy SOAP 1.1/1.2 HTTP binding, WSDL MEP và thỏa thuận hai bên. Phải xác minh behavior thực.

### 11.3. Outbox và idempotency

Nếu business operation commit nhưng HTTP connection bị mất trước khi client nhận acknowledgment, client có thể retry. Một thiết kế tốt dùng:

- **Transactional outbox:** ghi trạng thái nghiệp vụ và callback job trong một transaction khi có thể.
- **Deduplication key:** gắn authenticated principal + operation + request/message identity theo quy tắc đã thống nhất.
- **Retry budget và exponential backoff:** tránh gửi vô hạn hoặc dồn tải vào callback endpoint.
- **Deadline/TTL:** không gửi kết quả nhạy cảm quá lâu sau khi request hết hiệu lực.
- **Dead-letter queue:** khi không thể chuyển message, giữ nội bộ và xử lý vận hành theo quyền hạn.
- **No raw URI in job:** dùng destination ID + policy registry, kiểm tra registration vẫn active trước khi gửi.
- **Correlation:** callback chứa `RelatesTo` đúng request, và client callback receiver kiểm tra uniqueness/trusted sender.

Không gửi một callback có side effect rồi retry mù mà không có cơ chế idempotency phía nhận. SOAP response bất đồng bộ thường cần contract riêng cho việc xác nhận đã nhận callback hoặc xử lý trùng.

### 11.4. Hết hạn hoặc thay đổi registration giữa chừng

Một request có ReplyTo đã được duyệt lúc tiếp nhận, nhưng trước khi callback gửi đi partner thay URL hoặc bị suspend. Worker cần có chính sách:

1. Gửi theo **snapshot approved destination** đã đóng băng tại thời điểm chấp nhận, chỉ nếu còn được phép và policy/expiry cho phép; hoặc
2. Resolve lại destination ID ở thời điểm gửi, bảo đảm identity/tenant và phiên bản policy còn phù hợp.

Không âm thầm dùng URL **mới nhất** trong một trường do caller tự sửa mà không audit. Với dữ liệu nhạy cảm, nếu registration bị suspend hoặc trust policy thay đổi, nên dừng callback và chuyển sang xử lý lỗi nội bộ có kiểm soát.

## 12. FaultTo: dữ liệu lỗi cũng cần kiểm soát quyền nhận

### 12.1. Fault không phải “log công khai”

Một SOAP Fault có thể chứa:

- SOAP fault code/reason, operation/action.
- Error correlation ID hoặc mã nghiệp vụ.
- Modeled fault detail từ XSD/WSDL.
- Giá trị không hợp lệ hoặc thông tin về resource mà caller yêu cầu.
- Dữ liệu nhạy cảm nếu exception handling bị cấu hình sai.

**Không gửi stack trace, đường dẫn hệ thống, certificate/private key, raw token, SQL error, raw SOAP Body hoặc thông tin tenant khác** trong SOAP Fault. Ngay cả khi `FaultTo` được đăng ký, chỉ gửi dữ liệu fault theo contract và data classification.

### 12.2. Lỗi khi chuẩn bị hoặc gửi FaultTo

Cần phân biệt:

| Tình huống | Hành vi nên có |
|---|---|
| `FaultTo` không được phép | Reject policy; tuyệt đối không HTTP POST tới URL đó |
| Request WS-A sai header/URI | Trả addressing/protocol fault qua kênh an toàn theo binding; không dùng EPR sai |
| Business error và FaultTo đã duyệt | Có thể gửi modeled fault tới approved fault endpoint theo contract |
| Fault callback trả HTTP 401/403 | Xem auth/certificate policy; không fallback tới bất kỳ URL mới |
| Fault callback timeout | Retry có giới hạn theo profile, không tạo fault-of-fault loop |
| Callback đã hết hạn | Dead-letter/incident nội bộ; không gửi dữ liệu quá hạn |
| Fault chứa PII | Redact/minimize detail trước khi gửi; audit data classification |
| FaultTo vắng, ReplyTo external | Áp dụng default theo WS-A và authorize **riêng** quyền nhận fault |

### 12.3. ReplyTo và FaultTo có thể thuộc những quyền khác nhau

Đối tác có thể dùng một endpoint nhận **kết quả nghiệp vụ** và endpoint khác nhận **lỗi vận hành**. Hai endpoint này không nhất thiết do cùng đội quản lý, có cùng ACL hoặc cùng mức bảo vệ dữ liệu.

Ví dụ đơn hàng có customer details trong success response nhưng error Fault có mã kiểm tra tín dụng. Không thể suy ra một callback được phép nhận success đồng nghĩa được phép nhận Fault. Policy nên có **reply destination registry** và **fault destination registry** hoặc một phân quyền rõ loại message được gửi.

### 12.4. Fault của WS-Addressing khác Fault nghiệp vụ

WS-Addressing/transport errors có thể phát sinh trước khi endpoint business xử lý, ví dụ `wsa:Action` không khớp, EPR không hợp lệ hoặc không hỗ trợ non-anonymous response. Business faults như `OrderNotFound` hoặc `InvalidOrderState` nằm ở cấp contract nghiệp vụ.

Đối với SOAP 1.2, Fault format khác SOAP 1.1. Để tương thích, cần kiểm tra **SOAP version, WS-Addressing namespace và fault subcodes** theo profile thực. Không hardcode `soapenv:Client` cho SOAP 1.2 hoặc assume tất cả faults đều được xử lý bởi `SoapFaultMappingExceptionResolver`.

## 13. Egress transport: kiểm tra HTTP/TLS ở thời điểm thật sự gửi

### 13.1. Không chỉ validate URL trên giấy

Sau khi policy chấp nhận callback URI, hệ thống còn phải đảm bảo HTTP client **không bị redirect/DNS/proxy** đưa tới một destination khác:

- Chỉ dùng **HTTPS** cho các callback đã được quy định.
- Bật default **certificate chain** và **hostname verification**, không dùng trust-all.
- Không dùng HTTP redirect tự động cho SOAP POST; nếu policy cho phép redirect, mỗi hop phải được **authorize lại** đầy đủ, và kiểm soát credentials/Body.
- Dùng egress proxy/firewall hoặc HTTP client network controls để giới hạn destinations/netblocks thực tế.
- Chặn loopback, link-local, private networks và metadata endpoints theo network policy; để ý IPv4/IPv6, DNS resolution và host aliases.
- Không chuyển user-supplied `Host` header hoặc SNI override sang HTTP client.
- Không để client tự cấu hình proxy URL qua SOAP Header.
- Có connection/read timeout, size limits và giới hạn số redirects (tốt nhất bằng 0 cho callback SOAP cố định).

**DNS rebinding:** một domain trong exact allowlist vẫn cần được vận hành bởi đối tác đã xác minh; DNS hoặc cấu hình mạng bị chiếm có thể đưa IP tới vùng cấm. Network egress policy cần được áp dụng **lúc mở connection**, không chỉ khi request được nhận.

### 13.2. HTTPS được xác minh nhưng vẫn phải authorize recipient

TLS trả lời: “Có phải endpoint thực sở hữu DNS hostname/certificate phù hợp không?” Nó **không** trả lời: “Partner A có được phép nhận kết quả của tenant B không?” Thử:

~~~text
https://cb.partner-a.example/ws/results
https://cb.partner-b.example/ws/results
~~~

Cả hai có thể có chứng chỉ CA hợp lệ. Nhưng nếu request được xác thực là `PARTNER_A`, policy không được cho phép gửi response đến `PARTNER_B` chỉ vì TLS thành công.

### 13.3. mTLS, WS-Security và ký callback response

Nếu callback endpoint yêu cầu mTLS:

- Dùng client certificate/keystore của **integration partner tương ứng**, không dùng một identity cho mọi đích khi policy khác nhau.
- Xác minh server certificate chain/SAN và kiểm soát truststore/hostname.
- Rotate certificates, giữ secret ngoài source code/log.
- Phân biệt TLS identity và **WS-Security signing identity** cho callback SOAP message.

Nếu callback response phải được ký, security interceptor tạo WS-Security headers/chữ ký theo WSDL/policy. `wsa:Action`, `wsa:To`, `wsa:RelatesTo` và các ReferenceParameters được cho phép phải được xử lý **trước khi ký** khi chúng nằm trong signed references. Không tự tạo `<ds:Signature>` bằng nối XML.

### 13.4. Payload và attachment lớn

Response bất đồng bộ có thể chứa binary/MTOM. Chỉ vì ReplyTo đã được duyệt không có nghĩa được gửi dữ liệu không giới hạn:

- Xác định **loại dữ liệu và kích thước** được phép gửi tới callback registry.
- Áp dụng resource limits với MTOM/XOP, MIME parts và decoded bytes.
- Không serialize toàn SOAP để log, tránh buffering và lộ dữ liệu.
- Ký/encrypt attachments nếu policy yêu cầu, kiểm chứng checksum.
- Giới hạn retries và tổng dữ liệu gửi; ngăn callback trở thành kênh phát tán file lớn.

Với thông tin cực kỳ nhạy cảm, cân nhắc **trả một opaque retrieval token hoặc trạng thái**, rồi yêu cầu đối tác truy xuất qua API đã xác thực, thay vì gửi toàn dữ liệu tới callback URL do sender khai báo. Thiết kế này vẫn phải có authorization, expiry và chống replay riêng.

## 14. WSDL, WS-Addressing metadata và hợp đồng callback

### 14.1. XSD không tự mô tả tất cả addressing semantics

XSD quy định cấu trúc SOAP payload, ví dụ:

~~~xml
<ord:SubmitOrderRequest xmlns:ord="urn:example:orders:v1">
  <ord:orderId>ORD-1001</ord:orderId>
</ord:SubmitOrderRequest>
~~~

Nhưng bản thân XSD này không nói kết quả được gửi qua HTTP response hay callback URL nào; đó là phần của **message exchange pattern, WS-Addressing metadata/policy và hợp đồng giao tiếp**. Vì vậy, một client sinh JAXB classes thành công không đủ chứng minh nó đã biết cách xử lý `ReplyTo`/`FaultTo`.

### 14.2. Những điều cần thỏa thuận trước với đối tác

| Câu hỏi hợp đồng | Quyết định phải được ghi rõ |
|---|---|
| SOAP version | SOAP 1.1 hay SOAP 1.2, media type và binding |
| WS-A version | W3C 2005/08 hay profile legacy |
| MEP | Đồng bộ request-response, one-way hay asynchronous callback |
| Anonymous/non-anonymous | Giá trị nào được phép với operation nào |
| Action | URI action cho request, normal reply và fault |
| MessageID/RelatesTo | Sinh, giới hạn, uniqueness, correlation và replay policy |
| ReplyTo/FaultTo | Registrations, allowlist, quyền theo principal/tenant |
| ReferenceParameters | QNames nào hợp lệ, có được forward không |
| HTTP acknowledgment | Status/Body cho việc tiếp nhận request async |
| Callback authentication | TLS/mTLS, WS-Security keys, identity mapping |
| Data classification | Trường dữ liệu/Fault detail nào được phép gửi |
| Retry/expiry | Attempt budget, timeout, dead-letter, cancellation |
| Version migration | Thay URL/certificate/namespace và backward compatibility |

Không dựa duy nhất vào `wsdl:soap:address` để xác định callback destination. `soap:address` chỉ địa chỉ phục vụ service port; `ReplyTo/FaultTo` là thuộc tính addressing của request được gửi.

### 14.3. SOAP headers phải phù hợp namespace và chữ ký

Một implementation có thể yêu cầu:

~~~xml
<wsa:Action xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:example:orders:v1/SubmitOrderResponse
</wsa:Action>
<wsa:RelatesTo xmlns:wsa="http://www.w3.org/2005/08/addressing">
  urn:uuid:5c0cb8c0-6c96-41b6-9d39-b83042d904b9
</wsa:RelatesTo>
~~~

Đây chỉ là **mảnh SOAP Header phản hồi**. Với callback thực, cần SOAP Envelope/Body, WSDL response global element, action theo contract và security headers đúng policy. Không tự gửi một HTTP POST chỉ chứa hai thẻ này.

### 14.4. Không phải mọi callback đều có một SOAP response chờ tiếp

Một ứng dụng gửi SOAP callback có thể cần nhận HTTP acknowledgment hoặc một SOAP acknowledgment, tùy contract. Nếu phía gọi callback lại coi response acknowledgment như một **new ReplyTo**, có thể tạo message loop.

Nên xác định rõ operation nào là **terminal notification**, operation nào có reply, có cho `none` không và cách phân biệt callback delivery success với **business success**. Một HTTP 200 từ callback endpoint chỉ chứng minh transport/application receiver đã phản hồi theo cách của nó, không tự chứng minh đối tác đã áp dụng kết quả nghiệp vụ.

## 15. Kiểm thử policy, SOAP dispatch và network egress

Một test chỉ kiểm tra callback URL có cú pháp hợp lệ là **chưa đủ**. Cần kiểm tra danh tính caller, allowlist cho từng loại message, xử lý SOAP headers và **không mở kết nối outbound tới đích đã từ chối**.

### 15.1. JUnit test policy thuần Java

Giả sử `CallbackDestinationPolicy` ở mục 8 nằm trong test classpath:

~~~java
package com.example.soap.addressing;

import static org.junit.jupiter.api.Assertions.*;

import java.util.Map;
import java.util.Set;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CallbackDestinationPolicyTest {
    private static final String RESULTS =
            "https://cb.partner-a.example/ws/results";
    private static final String FAULTS =
            "https://cb.partner-a.example/ws/faults";

    private CallbackDestinationPolicy policy;
    private CallbackDestinationPolicy.PolicyKey key;

    @BeforeEach
    void init() {
        key = new CallbackDestinationPolicy.PolicyKey(
                "PARTNER_A", "SUBMIT_ORDER");
        policy = new CallbackDestinationPolicy(
                Map.of(key, Set.of(RESULTS)),
                Map.of(key, Set.of(FAULTS)));
    }

    @Test
    void acceptsRegisteredReplyAndFault() {
        var routing = policy.authorize(
                key, RESULTS, FAULTS, true, false);

        assertEquals(
                CallbackDestinationPolicy.Kind.APPROVED_CALLBACK,
                routing.reply().kind());
        assertEquals(RESULTS, routing.reply().exactUri());
        assertEquals(FAULTS, routing.fault().exactUri());
    }

    @Test
    void rejectsUnknownReply() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, "https://other.example/collect",
                    FAULTS, true, false));
    }

    @Test
    void rejectsUnknownFaultEvenIfReplyIsValid() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, RESULTS, "https://other.example/faults",
                    true, false));
    }

    @Test
    void rejectsHttpAndExtraQuery() {
        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, "http://cb.partner-a.example/ws/results",
                    FAULTS, true, false));

        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, RESULTS + "?next=/internal",
                    FAULTS, true, false));
    }

    @Test
    void defaultsMissingDestinationsToAnonymous() {
        var routing = policy.authorize(
                key, null, null, false, false);

        assertEquals(
                CallbackDestinationPolicy.Kind.ANONYMOUS,
                routing.reply().kind());
        assertEquals(
                CallbackDestinationPolicy.Kind.ANONYMOUS,
                routing.fault().kind());
    }

    @Test
    void defaultFaultStillRequiresSeparateAuthorization() {
        // FaultTo vắng sẽ kế thừa ReplyTo theo chính sách này.
        // RESULTS chưa được cấp quyền nhận Fault nên phải từ chối.
        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, RESULTS, null, true, false));
    }

    @Test
    void rejectsDifferentPartnerAndNoneInStrictMode() {
        var other = new CallbackDestinationPolicy.PolicyKey(
                "PARTNER_B", "SUBMIT_ORDER");

        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    other, RESULTS, FAULTS, true, false));

        assertThrows(IllegalArgumentException.class,
                () -> policy.authorize(
                    key, CallbackDestinationPolicy.NONE,
                    FAULTS, true, false));
    }
}
~~~

Đây là **unit tests của policy ví dụ**, không chứng minh framework đã parse EPR đúng hoặc có outbound HTTP. Các tham số `externalReplyAllowed`/`suppressReplyAllowed` trong thực tế phải do server xác lập theo operation/MEP, không cho caller tự chọn.

### 15.2. Ma trận kiểm thử SOAP Header và callback

| Đầu vào / tình huống | Kỳ vọng |
|---|---|
| Vắng ReplyTo và FaultTo | Default anonymous khi binding cho phép |
| ReplyTo/FaultTo anonymous | Phản hồi theo anonymous binding, không mở callback URL |
| ReplyTo none ở operation cần reply | Reject theo operation policy |
| Reply và Fault cùng đúng registry | Hai loại message được phép theo phân quyền riêng |
| Reply hợp lệ, Fault không hợp lệ | Reject cả routing; không gửi lỗi tới FaultTo lạ |
| ReplyTo là URL link-local/loopback | Reject; không kết nối |
| URL có prefix hostname giả | Exact allowlist không khớp |
| URL có port/path/query khác | Reject nếu không nằm trong registry |
| URI có userinfo/fragment | Reject theo profile callback |
| Registered callback HTTP redirect tới IP nội bộ | Không follow tự động; egress chặn |
| Registered hostname resolve thành private IP | Network policy chặn tại connect |
| Duplicate ReplyTo/FaultTo headers | Từ chối semantic/WS-A error |
| WS-A namespace legacy khi server chỉ hỗ trợ 2005 | Không diễn giải như 2005 EPR |
| EPR có ReferenceParameters chưa được duyệt | Reject; không chuyển tiếp tùy ý |
| WS-Security signature thiếu hoặc bị sửa trên header bắt buộc ký | Reject trước business |
| MessageID bị replay | Deduplicate/reject theo identity/TTL |
| Callback receiver trả lỗi 503 | Retry có giới hạn, không đổi đích |
| Callback receiver certificate SAN sai | TLS reject; không tắt hostname verifier |
| SOAP callback có MTOM | Bytes đúng, resource limits và attachment security áp dụng |

Để chứng minh không có SSRF, test cần một **outbound transport spy hoặc egress gateway**. Một SOAP Fault trả về client không chứng minh server chưa mở connection tới URL độc hại trong quá trình xử lý.

### 15.3. MockWebServiceClient và test network có phạm vi khác nhau

`MockWebServiceClient` hữu ích để kiểm tra `@Endpoint`, `@PayloadRoot`, SOAP Header/Body và response trong Spring application context. Nhưng nó không tự mở TLS connection hoặc gửi callback HTTP thật, nên chưa thử được DNS rebinding, redirect, hostname verification hoặc egress rules.

Một integration test đầy đủ cần HTTPS test receiver với chứng chỉ test có SAN đúng, registry đích do test sở hữu và network policy không cho gọi hosts khác. Kiểm tra:

1. Request hợp lệ tạo **một** outbox job với approved destination ID.
2. Worker gửi SOAP callback chỉ tới registered receiver.
3. `wsa:Action`, `To`, `RelatesTo`, payload QName và SOAP Fault đúng hợp đồng.
4. Chữ ký WS-Security của callback được xác minh khi policy yêu cầu.
5. Retry không tạo callback trùng ngoài idempotency policy.
6. Raw `ReplyTo`/`FaultTo` và secret không xuất hiện trong log/metrics.
7. Với đích bị reject, network spy ghi nhận **không có outbound attempt**.

Không thử SSRF bằng cách gọi thật metadata service hoặc host nội bộ production. Chỉ dùng địa chỉ giả và test network cô lập đã được phép.

## 16. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Kiểm tra đầu tiên |
|---|---|---|
| Reply không tới caller | Receiver chỉ hỗ trợ response đồng bộ, không có callback worker | WSDL MEP và hạ tầng async |
| Gửi ReplyTo nhưng server vẫn trả HTTP response | Binding yêu cầu anonymous hoặc policy cấm external | WS-A policy, anonymous/non-anonymous |
| ReplyTo không được nhận diện | Namespace WS-A sai, EPR shape sai | QName và WS-A version |
| Reply hợp lệ, Fault bị policy từ chối | FaultTo vắng và mặc định kế thừa ReplyTo chưa có quyền nhận Fault | Fault destination registry |
| Server gửi Fault tới URL lạ | Error handler đọc raw FaultTo mà không authorize | Chặn egress và sửa fault-on-fault path |
| Header chứa duplicate ReplyTo | Parser bỏ qua một header thay vì reject | Validate cardinality và actor/role |
| Callback bị HTTP 301/302 | Endpoint đổi URL hoặc proxy redirect | Tắt auto-follow, cập nhật registration có review |
| Chỉ lỗi ở một region | DNS, TLS cert, egress firewall khác nhau | Host/SNI/IP/policy theo region |
| Callback TLS/hostname lỗi | SAN/chain/truststore sai | Xác minh CA, cert SAN, mTLS |
| WS-Security signature lỗi | WS-A Header bị mutate sau signing | Signed references, interceptor order |
| MessageID không correlate | ID thiếu/trùng hoặc tenant mapping sai | `RelatesTo`, principal và TTL |
| Duplicate callback | Retry/queue không idempotent | Outbox ID, deduplication |
| SOAP Fault bị lộ detail | Fault payload chứa exception/PII | Data classification, fault resolver |
| Callback MTOM gây memory pressure | Interceptor buffer attachment | Streaming, limits, spool/cleanup |

Quy trình điều tra nên đi từ **SOAP binding/WS-A version → authenticated identity → policy decision → outbox job → actual egress network → TLS/callback SOAP response**. Không sửa XSD, SOAPAction hoặc truststore ngẫu nhiên để che lỗi phân quyền đích.

## 17. Tình huống thực tế: FaultTo bị đổi sang đích chưa đăng ký

Một dịch vụ xử lý đơn hàng bất đồng bộ đã đăng ký cho `PARTNER_A`:

~~~text
Reply:
https://cb.partner-a.example/ws/results

Fault:
https://cb.partner-a.example/ws/faults
~~~

Request mới có ReplyTo đúng nhưng FaultTo là:

~~~text
https://unregistered.example/collect
~~~

Code cũ chỉ kiểm tra ReplyTo. Khi business service gặp exception, fault handler lấy nguyên `FaultTo` để gửi SOAP Fault. Điều này vừa tạo **outbound connection ngoài chính sách**, vừa có thể làm lộ nội dung lỗi.

### 17.1. Phân tích nguyên nhân

- Chỉ authorize đường reply thành công, bỏ qua đường fault.
- Transport nhận raw URI từ SOAP Header thay vì destination ID đã duyệt.
- Fault serialization có thể chứa data nhạy cảm.
- Không chặn outbound network tới URL chưa đăng ký.
- WS-A Header có thể bị sửa nếu không nằm trong signed references bắt buộc.
- Logging có thể chứa raw URL hoặc exception do caller kiểm soát.

### 17.2. Phương án khắc phục

1. Chặn mọi outbound destination không được duyệt ở egress proxy/firewall.
2. Kiểm tra cả ReplyTo và FaultTo trước khi business transaction có side effects.
3. Áp dụng policy theo authenticated principal/tenant/operation.
4. Lưu destination IDs trong outbox, không lưu URI chưa xác minh làm chỉ dẫn transport.
5. Tối thiểu hóa SOAP Fault detail; không echo exception nội bộ.
6. Không tạo vòng lặp fault-of-fault hoặc retry vô hạn.
7. Nếu cần integrity qua intermediaries, xác minh signed WS-A headers theo WS-SecurityPolicy.
8. Kiểm tra lại redirect, DNS, TLS/hostname/mTLS của callback sender.
9. Thử test malformed/duplicated EPR, fault URI lạ, replay và tenant mismatch.
10. Audit dữ liệu đã gửi nhầm theo quy trình xử lý sự cố của tổ chức.

### 17.3. Tiêu chí nghiệm thu

| Tiêu chí | Bằng chứng |
|---|---|
| Unknown ReplyTo/FaultTo bị từ chối | Unit + SOAP tests |
| Không gửi network request tới URI lạ | Egress spy/traffic logs của test |
| Callback hợp lệ vẫn hoạt động | HTTPS receiver + WSDL-compatible client |
| Fault không lộ PII/token/stack trace | Synthetic-secret tests |
| WS-A headers bị sửa sau signing sẽ bị phát hiện khi policy yêu cầu | Tampered-message tests |
| Retry/expiry không phát tán message quá hạn | Outbox, deadline và DLQ tests |

**Bài học:** `FaultTo` cũng là một destination có khả năng nhận dữ liệu; phải bảo vệ nghiêm ngặt như `ReplyTo`, không được xem là chi tiết phụ của error handler.

## 18. Bài tập thực hành, checklist và tổng kết

### 18.1. Bài tập kèm đáp án

**Bài 1 — Vắng ReplyTo và FaultTo**

Một SOAP 1.2 request dùng WS-Addressing 2005/08 không khai báo `ReplyTo` hoặc `FaultTo`. Có phải server tự tìm callback URL từ `wsa:To` không?

*Đáp án:* Không. Trong mô hình chuẩn thường gặp, reply endpoint mặc định là **anonymous** và fault endpoint mặc định theo reply endpoint. Cách sử dụng transport response còn phụ thuộc binding/MEP. `To` là đích của request, không tự trở thành nơi nhận reply.

**Bài 2 — ReplyTo hợp lệ, FaultTo độc hại**

Request của `PARTNER_A` có ReplyTo đúng registry nhưng FaultTo trỏ đến `https://other.example/collect`. Có nên xử lý nghiệp vụ rồi chỉ chặn khi phát sinh Fault?

*Đáp án:* Không nên. Authorize **cả hai EPR trước** khi bắt đầu business operation có side effect. Nếu FaultTo không được phép, reject routing và không mở HTTP connection tới nó, kể cả khi kết quả nghiệp vụ sẽ thành công.

**Bài 3 — HTTPS URL bất kỳ**

Một caller gửi `ReplyTo=https://attacker-controlled.example/receive` có TLS certificate hợp lệ từ public CA. Có thể gửi dữ liệu nghiệp vụ tới đó không?

*Đáp án:* Không chỉ vì TLS thành công. Certificate/hostname verification và authorization recipient là **hai việc khác nhau**. URL phải nằm trong registry được duyệt cho authenticated partner, tenant, operation và message type.

**Bài 4 — Sự khác biệt giữa anonymous và none**

Hai giá trị `http://www.w3.org/2005/08/addressing/anonymous` và `.../none` có cùng nghĩa là “không có callback URL” không?

*Đáp án:* Không. Anonymous biểu thị endpoint reply ẩn danh theo binding (thường dùng HTTP response channel). None biểu thị không có endpoint nhận message theo semantics WS-A. Chấp nhận none hay không phải dựa trên MEP và contract.

**Bài 5 — Đường dẫn URL có vẻ đúng**

Allowlist dùng `startsWith("https://cb.partner-a.example")`. Input `https://cb.partner-a.example.evil.example/ws` có thể vượt qua không?

*Đáp án:* Có thể. Prefix string không kiểm tra hostname. Phải dùng **exact approved URI** hoặc parser chuẩn cùng các ràng buộc host/port/path/query chặt chẽ, cộng với egress policy.

**Bài 6 — DNS thay đổi sau lúc validate**

Một callback hostname nằm trong allowlist, nhưng sau khi tạo job DNS trỏ tới IP nội bộ. Chỉ kiểm tra domain khi nhận SOAP request có đủ không?

*Đáp án:* Không. Cần egress controls **khi mở connection**, không tin DNS resolution cũ; chặn private, loopback, link-local, metadata và những network đích ngoài policy, đồng thời chống redirect bypass.

**Bài 7 — Header đã ký có được phép gửi tới mọi nơi?**

Sender dùng mTLS và ký SOAP Body, nhưng không ký `wsa:FaultTo`. Client có được coi là đã xác thực đường FaultTo không?

*Đáp án:* Chưa. mTLS xác thực peer ở tầng transport; Body signature không tự bảo vệ header chưa ký. Ngay cả khi FaultTo có chữ ký hợp lệ, server vẫn phải kiểm tra quyền dùng destination theo partner/tenant/operation.

**Bài 8 — ReferenceParameters do caller gửi**

Một EPR ReplyTo có `ReferenceParameters` chứa routing token tự do. Server nên copy mọi parameter vào outbound response không?

*Đáp án:* Không. Chỉ chấp nhận các QNames và dạng dữ liệu đã được contract cho phép. Kiểm tra kích thước, nguồn tin cậy, signature policy và khả năng token đó bị dùng làm header control. Unsupported extensions nên bị reject.

**Bài 9 — MessageID được tái sử dụng**

Cùng `MessageID` được gửi hai lần và lần thứ hai có ReplyTo khác. Cần xử lý thế nào?

*Đáp án:* Xét identity/tenant và deduplication/replay policy. Không để lần thứ hai thay callback target của một request đã được xử lý. Nếu là retry hợp lệ, giữ correlation/delivery policy rõ ràng và không nhân đôi side effects.

**Bài 10 — SOAP Fault gặp lỗi khi gọi FaultTo**

Callback fault endpoint trả HTTP 500. Server có nên tạo một SOAP Fault mới rồi gửi tiếp tới chính FaultTo đến khi thành công không?

*Đáp án:* Không. Dùng retry có giới hạn, backoff, expiry và dead-letter/internal alert. Tránh vòng lặp fault-of-fault và không tự đổi đích sang một URI do sender gợi ý.

**Bài 11 — MockWebServiceClient pass**

Một unit test Spring-WS pass khi ReplyTo chứa một URL đã duyệt. Có thể kết luận hệ thống chống SSRF hoàn toàn không?

*Đáp án:* Chưa. Cần test **network outbound** với redirect, DNS/private IP, TLS hostname, callback receiver và assert không có HTTP attempt tới unapproved URL. Mock SOAP chỉ kiểm tra một phần pipeline.

**Bài 12 — ReplyTo của tenant khác**

Partner A được xác thực, đưa ReplyTo đã đăng ký hợp lệ nhưng thuộc tenant B của cùng partner. Có được gửi không?

*Đáp án:* Không nếu policy không cấp quyền liên tenant. Registry phải ràng buộc **trusted identity + tenant + operation + destination**, không chỉ partner hostname chung.

### 18.2. Checklist thiết kế contract

- [ ] WSDL/binding/WS-Addressing version và MEP được ghi rõ cho từng operation.
- [ ] `wsa:Action` cho request, response và fault nhất quán theo hợp đồng.
- [ ] Phân biệt `wsa:To`, `ReplyTo`, `FaultTo` và `RelatesTo`.
- [ ] Áp dụng default anonymous/FaultTo đúng WS-A profile được hỗ trợ.
- [ ] Quy định khi nào `none`/non-anonymous được phép, không tự suy diễn.
- [ ] Mọi `ReferenceParameters`/extension elements có schema và policy rõ.
- [ ] Có version/correlation/retry/acknowledgment contract với đối tác.
- [ ] Fault code/reason/detail và data classification được thỏa thuận.

### 18.3. Checklist nhận và quyết định ReplyTo/FaultTo

- [ ] XML parser và SOAP message factory được giới hạn tài nguyên, chống XXE/DTD.
- [ ] Parse Header theo **QName namespace URI + local name**, không regex.
- [ ] Reject duplicate/conflicting WS-A headers và unsupported EPR shape.
- [ ] Chỉ sử dụng **trusted principal/tenant/operation** từ authentication đã verify.
- [ ] Kiểm tra WS-Security signature protection cho WS-A headers khi policy yêu cầu.
- [ ] Cả ReplyTo **và** FaultTo được authorize độc lập.
- [ ] Exact callback URI thuộc registry theo identity/tenant/operation.
- [ ] Không chấp nhận userinfo, scheme/port/path/query ngoài chính sách.
- [ ] Không gọi network URL chỉ để “thử xem callback có hợp lệ”.
- [ ] Nếu một đích không hợp lệ, reject trước khi business có side effect.
- [ ] Không gửi Fault tới chính FaultTo bị từ chối hoặc tạo fault-of-fault loop.
- [ ] Các lỗi policy không echo raw URI/secret/sensitive SOAP detail ra ngoài.

### 18.4. Checklist outbound delivery và bảo mật

- [ ] Outbox lưu **approved destination ID**, không raw URI chưa được kiểm chứng.
- [ ] Transport giới hạn egress network và ngăn private/link-local/metadata access.
- [ ] HTTP redirects bị tắt hoặc mọi hop được authorize lại.
- [ ] HTTPS certificate chain, SAN/hostname verification và SNI hoạt động đúng.
- [ ] mTLS, WS-Security signing/encryption và truststore theo đúng destination policy.
- [ ] Header `To`/`Action`/`RelatesTo` và signed references đúng contract.
- [ ] Response/Fault được tối thiểu hóa dữ liệu; MTOM/attachments có size limits.
- [ ] Retry có budget, backoff, TTL, deduplication và dead-letter handling.
- [ ] Registration suspension/rotation được kiểm soát cả với pending jobs.
- [ ] Audit metadata dùng operation code/destination ID; không ghi raw SOAP Body/Header.
- [ ] Callback receiver xác minh sender và correlation; không chỉ tin MessageID.

### 18.5. Checklist kiểm thử và tương thích

- [ ] Test anonymous, none, callback hợp lệ và callback không hợp lệ.
- [ ] Test ReplyTo hợp lệ nhưng FaultTo không hợp lệ.
- [ ] Test cross-tenant/cross-partner unauthorized destinations.
- [ ] Test duplicate headers, sai WS-A version, unsupported ReferenceParameters.
- [ ] Test tampered signatures và unsigned required addressing headers.
- [ ] Test URL prefix spoofing, encoded URI, unexpected port/path/query.
- [ ] Test DNS rebinding simulation, HTTP redirect, TLS wrong SAN/CA.
- [ ] Xác minh **không có outbound connection** khi policy từ chối request.
- [ ] Test callback acknowledgment, retry, crash recovery, TTL và duplicate delivery.
- [ ] Test SOAP 1.1/1.2, modeled faults, response QName và WS-Addressing Actions.
- [ ] Test MTOM và WS-Security interoperability với client/receiver độc lập.
- [ ] Test synthetic secrets không xuất hiện ở logs, Fault detail, tracing hoặc metrics.

**Ghi nhớ:** `wsa:ReplyTo` và `wsa:FaultTo` là **đề xuất điểm nhận message do bên gửi cung cấp**, không phải quyền điều khiển network của server. Với Spring Web Services, hãy xác minh WS-Addressing EPR đúng version, xác thực caller, kiểm soát **hai destination độc lập** bằng registry/allowlist, ngăn SSRF ở HTTP egress và giữ SOAP Fault ở mức dữ liệu được phép công bố. Tích hợp doanh nghiệp ổn định cần thêm WS-Security, HTTPS/mTLS, idempotent outbox, correlation và các bài kiểm thử âm tính chứng minh **đích chưa được duyệt không bao giờ được gọi**.
