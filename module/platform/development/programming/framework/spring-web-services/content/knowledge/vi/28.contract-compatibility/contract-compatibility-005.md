# Chiến lược version theo namespace, endpoint hoặc hợp đồng công bố

Một dịch vụ SOAP thường tồn tại lâu hơn một bản phát hành ứng dụng. Client có thể được triển khai tại nhiều đối tác, trên những nền tảng và lịch nâng cấp khác nhau. Khi thêm trường vào request, thay cấu trúc response, đổi ý nghĩa một operation hoặc loại bỏ một kiểu dữ liệu trong XSD, **client cũ và server mới có thể không còn hiểu nhau**. Nếu chỉ đổi code Java rồi triển khai đè WSDL cũ, lỗi có thể xuất hiện ở JAXB unmarshalling, endpoint mapping, SOAP Action, validation hoặc business semantics.

Bài **“Chiến lược version theo namespace, endpoint hoặc hợp đồng công bố”** thuộc chương **Tương thích hợp đồng** của module `SPRING_WEB_SERVICES`. Module tập trung phát triển dịch vụ SOAP theo hướng **contract-first**: thiết kế XSD/WSDL, ánh xạ JAXB, xây dựng `@Endpoint` và SOAP client; xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích để tích hợp hệ thống doanh nghiệp ổn định.

Mục tiêu của bài là giúp người thiết kế chọn một chiến lược version có thể vận hành lâu dài, phân biệt ba phạm vi thường bị đánh đồng:

- **Version trong XML namespace:** định danh phiên bản contract ở cấp XML vocabulary và QName.
- **Version trong endpoint/address:** phân tách đường truy cập/điểm triển khai của service, thường thể hiện qua URL.
- **Version của hợp đồng được công bố:** định danh một bộ WSDL/XSD/policy cụ thể, có thể được lưu giữ và phân phối như một artifact bất biến.

Ba cách này có thể kết hợp. Ví dụ, endpoint `/soap/orders/v2` có thể công bố WSDL dùng target namespace `urn:example:orders:v2`; nhưng chúng trả lời ba câu hỏi khác nhau. **Namespace nói XML vocabulary nào đang được dùng; endpoint nói request được gửi đến đâu; WSDL/XSD nói client được lập trình theo contract nào.**

Các ví dụ dùng Spring-WS 4.x theo phong cách annotation endpoint, WSDL 1.1 và SOAP 1.1/1.2. Tên miền, operation, URL và package trong bài là giả định. Khi triển khai phải đối chiếu phiên bản Spring-WS, SOAP binding, WSDL thực tế, các XSD import và WS-Policy đang công bố. `SPECIAL_NOTE` của bài được truyền rỗng.

> **Quy tắc chính:** Hãy chọn version theo ranh giới hợp đồng mà client cần nhận diện và vận hành, sau đó bảo đảm namespace, endpoint, WSDL/XSD, actions và security policy mô tả cùng một version.

## 1. Vì sao SOAP contract cần version strategy?

Trong kiến trúc contract-first, WSDL và các XSD import là giao diện mà client dùng để generate hoặc viết mã. Khi server thay contract mà vẫn giữ cùng địa chỉ và cùng namespace, client cũ có thể:

- Không parse được phần tử mới hoặc nhận kiểu dữ liệu thay đổi.
- Không hiểu QName của request/response sau khi namespace đổi.
- Gửi một SOAP Action cũ nhưng server không còn mapping.
- Unmarshal response thất bại do cấu trúc/kiểu dữ liệu không tương thích.
- Parse thành công nhưng hiểu sai ý nghĩa nghiệp vụ, ví dụ trường `amount` đổi từ tổng trước thuế sang tổng sau thuế.
- Không xử lý được SOAP Fault mới hoặc WS-Addressing/WS-Security policy thay đổi.

**Một thay đổi XML hợp lệ về cú pháp chưa chắc tương thích về contract.** Ví dụ, thay ý nghĩa của `status` từ `APPROVED` thành `ACCEPTED` có thể làm client vẫn unmarshal thành công nhưng logic nghiệp vụ không còn đúng.

### 1.1. Ví dụ thay đổi contract

Contract ban đầu:

~~~xml
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v1">
  <ord:clientOrderId>WEB-42</ord:clientOrderId>
  <ord:amount>1200.00</ord:amount>
</ord:CreateOrderRequest>
~~~

Contract mới muốn thêm currency và quy tắc làm tròn. Có nhiều cách làm:

- Thêm element optional `currency` và giữ semantics cũ của `amount`.
- Tạo operation mới có request type mới.
- Tạo namespace v2 và endpoint v2.
- Công bố bộ WSDL/XSD v2 riêng, trong khi tiếp tục vận hành v1.
- Chuyển logic chung về application service và duy trì hai adapter contract v1/v2.

Nếu thay `amount` sang nghĩa mới nhưng không đổi tên, namespace hoặc tài liệu, client có thể không phát hiện sai khác. Đây là **semantic breaking change**, dù XSD không đổi.

### 1.2. Contract là một giao kèo nhiều thành phần

Một SOAP contract thực tế thường bao gồm:

| Thành phần | Vai trò trong tương thích |
| --- | --- |
| WSDL `definitions`, `portType`, `binding`, `service`, `port` | Operation, message, binding và address. |
| XSD `targetNamespace`, element, type, occurrence | Cấu trúc dữ liệu request/response/Fault. |
| SOAP version và binding | Envelope namespace, HTTP media type, SOAP Fault model. |
| SOAPAction / WS-Addressing Action | Định danh action theo binding và addressing metadata. |
| WS-Policy / WS-Security | Yêu cầu token, signature, encryption, timestamp và bảo mật. |
| Endpoint URL / service discovery | Nơi client gửi request và lifecycle truy cập. |
| Tài liệu semantics | Đơn vị, quy tắc null/omission, idempotency, error model và side effects. |
| JAXB mapping/generator settings | Cách XML contract trở thành Java types và ngược lại. |

Version chỉ một phần mà không kiểm tra các thành phần còn lại dễ tạo ra **hybrid contract**: Body v2 nhưng SOAP Action v1, WSDL v1 import XSD đã đổi, hoặc endpoint v2 lại dùng security policy v1 không tương thích.

### 1.3. Mục tiêu của version strategy

Một chiến lược tốt nên:

1. Cho client nhận diện contract đang dùng một cách rõ ràng.
2. Cho phép v1 và v2 cùng hoạt động trong khoảng migration nếu các đối tác không thể nâng cấp đồng thời.
3. Không khiến request của version này bị xử lý nhầm theo schema/semantics của version khác.
4. Có một nguồn contract được công bố và kiểm soát.
5. Xác định được ai sở hữu migration, thời hạn hỗ trợ và điều kiện sunset.
6. Kiểm thử cả request, response, Fault, addressing và security.
7. Có cách rollback hoặc route lại traffic khi rollout thất bại.

## 2. Ba trục version khác nhau

### 2.1. Version theo XML namespace

Ví dụ:

~~~text
urn:example:orders:v1
urn:example:orders:v2
~~~

Trong XML, namespace URI tham gia vào **QName** của element và type. Prefix chỉ là cách viết tắt; thay `ord` thành `o` không tạo version mới nếu namespace URI vẫn giữ nguyên.

~~~xml
<!-- v1 -->
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v1"/>

<!-- v2 -->
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v2"/>
~~~

QName của hai root element lần lượt là:

~~~text
{urn:example:orders:v1}CreateOrderRequest
{urn:example:orders:v2}CreateOrderRequest
~~~

Chúng là hai tên XML khác nhau, do đó có thể được mapping thành hai endpoint methods/types riêng. Đây là cách phân biệt **XML vocabulary version** trực tiếp trong message.

### 2.2. Version theo endpoint/address

Ví dụ:

~~~text
https://api.example.test/soap/orders/v1
https://api.example.test/soap/orders/v2
~~~

Endpoint version cho phép routing và vận hành hai contract trên hai URL khác nhau. Có thể dùng cùng namespace hoặc namespace khác, nhưng **giữ namespace v1 trên endpoint v2** làm người đọc khó biết XML vocabulary có thay đổi hay không. Nếu endpoint mới phục vụ đúng cùng contract v1 nhưng chỉ thay hạ tầng/hostname, namespace v1 vẫn có thể phù hợp.

Endpoint path version thường tiện cho:

- Deploy song song các servlet/service instances.
- Route qua API gateway/reverse proxy.
- Áp dụng TLS, rate limit, authentication và monitoring theo version.
- Tạo WSDL address riêng.
- Chuyển traffic theo đối tác hoặc môi trường.

Nhưng endpoint path **không thay thế QName**: một URL `/v2` vẫn có thể nhận XML QName v1 nếu server được cấu hình như vậy.

### 2.3. Version theo contract được công bố

Ví dụ, ứng dụng phân phối các artifact:

~~~text
contracts/
  orders/
    v1/
      orders-v1.wsdl
      orders-types-v1.xsd
      common-v1.xsd
      security-policy-v1.xml
    v2/
      orders-v2.wsdl
      orders-types-v2.xsd
      common-v2.xsd
      security-policy-v2.xml
~~~

Mỗi thư mục là một **contract release** được đóng gói, kiểm duyệt và có thể phân phối cho đối tác. Contract release có thể ghi thêm metadata ngoài WSDL như changelog, supported-until, endpoint address theo môi trường và checksum của từng artifact.

Một WSDL công bố tại `/ws/orders.wsdl` nếu nội dung thay đổi tùy thời điểm không tự tạo thành versioned contract. Client cũ có thể tải cùng URL nhưng nhận XSD mới. Cần phân phối URL bất biến theo version hoặc bảo đảm contract cũ luôn được giữ nguyên ở địa chỉ cũ trong thời gian hỗ trợ.

### 2.4. So sánh nhanh

| Tiêu chí | Namespace version | Endpoint version | Published contract version |
| --- | --- | --- | --- |
| Phân biệt XML QName | **Có, trực tiếp.** | Không tự có. | Chỉ khi artifacts dùng namespace khác. |
| Phân tách network routing | Không tự có. | **Có.** | Không tự có. |
| Lưu giữ WSDL/XSD bất biến | Không tự có. | Không tự có. | **Là mục tiêu chính.** |
| Cần đổi client URL | Không bắt buộc. | Thường có. | Tùy endpoint được ghi trong WSDL. |
| Có thể cùng tồn tại v1/v2 | Có nếu server mapping hỗ trợ. | Có qua nhiều routes. | Có qua nhiều bộ contract artifacts. |
| Điểm yếu thường gặp | Namespace bị đổi quá thường xuyên hoặc giữ nguyên cho breaking change. | Nhiều URL nhưng payload vẫn mơ hồ. | Artifact immutable nhưng endpoint/policy thực tế không khớp. |
| Phù hợp | XML vocabulary thay đổi có ý nghĩa. | Cần tách route/rollout/access. | Cần quản lý tương thích đối tác và lịch sử contract. |

**Không có lựa chọn nào tự giải quyết tất cả.** Một hệ thống enterprise thường dùng namespace để định danh payload version, endpoint để quản lý routing, và WSDL/XSD package bất biến để phát hành hợp đồng.

## 3. Phân loại thay đổi trước khi quyết định version

Không nên đổi namespace hoặc URL chỉ vì có một commit mới. Hãy đánh giá **tác động tới client**: client cũ có thể tiếp tục gửi request hợp lệ không, có đọc được response không, và kết quả nghiệp vụ có giữ nguyên semantics không?

### 3.1. Additive change chưa chắc luôn backward-compatible

Các thay đổi sau **thường có khả năng tương thích cao hơn**, nhưng phụ thuộc schema và cách client được generate:

| Thay đổi | Tác động có thể xảy ra | Cách đánh giá |
| --- | --- | --- |
| Thêm element mới với `minOccurs="0"` vào request/response | Client cũ có thể bỏ qua hoặc không serialize element; parser strict có thể từ chối. | Test JAXB clients cũ và schema validation hai chiều. |
| Thêm operation mới vào WSDL | Client đã generate từ WSDL cũ thường không gọi operation mới; nhưng generator/stack strict có thể phản ứng với WSDL thay đổi. | Kiểm tra code generation và client runtime. |
| Thêm optional response field | Client permissive có thể bỏ qua; JAXB strict/unmapped event handler có thể khác. | Dùng fixtures của client chính thức. |
| Mở rộng enum/XSD enumeration | Client có enum Java closed set có thể không parse được giá trị mới. | Đánh giá unknown enum handling; có thể là breaking change. |
| Thêm SOAP Fault detail code mới | Client switch exhaustive hoặc mapping cũ có thể lỗi. | Kiểm tra error handling và fallback. |
| Thêm header SOAP optional | Intermediary/client có thể bỏ qua nếu role/`mustUnderstand` phù hợp. | Kiểm tra `mustUnderstand`, SOAP role và WS-Policy. |

**Optional trong XSD không đồng nghĩa client cũ chắc chắn tương thích.** Một ứng dụng có thể dùng parser strict, generated enums hoặc logic kiểm tra toàn bộ field; chỉ integration test mới xác nhận được.

### 3.2. Những thay đổi thường là breaking

Các tình huống sau nên được coi là breaking cho tới khi có bằng chứng ngược lại:

- Đổi namespace URI của request/response element hoặc type đang công bố.
- Đổi QName hoặc kiểu dữ liệu của element hiện có.
- Đổi `minOccurs` từ 0 sang 1, thêm trường bắt buộc.
- Đổi `maxOccurs`, `nillable`, choice/sequence, base type hoặc restriction theo cách client cũ không xử lý.
- Đổi đơn vị, format hoặc semantics của một trường dù kiểu XSD vẫn giống.
- Xóa/đổi tên operation, message, binding, SOAPAction hoặc WS-Addressing Action.
- Đổi SOAP 1.1 sang SOAP 1.2, thay endpoint, security policy hoặc thuật toán bắt buộc mà không có giai đoạn chuyển tiếp.
- Đổi quy tắc authentication, certificate trust, signed parts, encryption recipient hoặc timestamp policy.
- Đổi business Fault semantics khiến client phân loại sai retry/compensation.

### 3.3. Đặt change budget cho từng major version

Một cách quản trị là phân loại thay đổi thành:

| Mức | Ví dụ | Quyết định |
| --- | --- | --- |
| Patch/documentation | Sửa mô tả, ví dụ hoặc WSDL annotation không đổi wire behavior. | Giữ contract version; phát hành tài liệu/build artifact mới có kiểm soát. |
| Minor/additive | Thêm optional field/operation được kiểm chứng. | Có thể giữ namespace major hiện tại nếu policy cho phép; publish artifact revision có changelog. |
| Major/breaking | Đổi required field, QName, semantics hoặc security behavior. | Tạo version contract mới và chạy song song/migration. |

Đây là **quy ước quản lý**, không phải một tiêu chuẩn versioning bắt buộc của SOAP/WSDL. Không có thuộc tính WSDL `version="2"` chung khiến mọi SOAP stacks tự hiểu major/minor. Team phải công bố quy tắc của chính mình và áp dụng nhất quán.

**Không phát hành version mới cho mỗi lần build.** Nếu namespace hoặc endpoint nhảy version liên tục vì thay implementation nội bộ, client sẽ phải nâng cấp thường xuyên dù contract không đổi. Ngược lại, không giữ v1 chỉ để tránh đổi URL khi semantics đã breaking.

## 4. Quy tắc đặt namespace version ổn định

Namespace URI là định danh, không phải URL bắt buộc phải tải được. Nó có thể dùng URI dạng URN hoặc HTTP(S) URI; quan trọng nhất là tính ổn định và ownership.

### 4.1. Một số kiểu đặt namespace

~~~text
urn:example:orders:v1
urn:example:orders:2026
https://schemas.example.test/orders/v1
http://example.test/contracts/orders/1
~~~

Mỗi kiểu có ưu/nhược điểm:

- `urn` ngắn gọn, không yêu cầu server web tại URI đó, nhưng không tự cung cấp trang documentation.
- HTTPS namespace có thể trỏ đến tài liệu schema/docs theo convention, nhưng URI vẫn là **định danh** trong XML; không phải yêu cầu parser luôn fetch URL.
- Version theo major (`v1`, `v2`) dễ quản trị compatibility hơn version theo patch date.
- Version theo ngày có thể hữu ích cho schema snapshot, nhưng client không nên phải nâng cấp chỉ vì ngày phát hành thay đổi mà contract semantics không đổi.

### 4.2. Namespace không nên đổi vì prefix hoặc implementation

Những thay đổi sau **không tạo version mới**:

~~~xml
<a:CreateOrderRequest xmlns:a="urn:example:orders:v1"/>
<ord:CreateOrderRequest xmlns:ord="urn:example:orders:v1"/>
~~~

Hai element có cùng QName. Thay package Java `com.example.orders.v1` sang `com.example.orders.api` cũng không bắt buộc thay XML namespace. Ngược lại, giữ tên class `CreateOrderRequest` nhưng đổi namespace URI sẽ tạo QName khác và có thể yêu cầu JAXB mapping khác.

### 4.3. Phạm vi namespace: một namespace cho cả service hay nhiều schema?

Có hai mô hình thường gặp:

**Một namespace cho một contract/service major:**

~~~text
urn:example:orders:v1
  CreateOrderRequest
  CreateOrderResponse
  CancelOrderRequest
  OrderFault
  OrderType
~~~

Dễ hiểu khi các types cùng vòng đời release. Tuy nhiên, shared types có thể bị nhân bản nếu nhiều bounded contexts cùng sử dụng.

**Namespace riêng theo domain/shared vocabulary:**

~~~text
urn:example:orders:v1
urn:example:money:v1
urn:example:common-identifiers:v1
~~~

Có thể tái sử dụng types giữa services, nhưng shared schema trở thành dependency contract cần quản trị riêng. Thay `Money` hoặc `Identifier` trong shared namespace có thể ảnh hưởng nhiều partner/services.

Không nên tạo namespace shared chỉ vì muốn tránh copy vài XSD types. Chỉ tách khi có **ownership, semantics, version policy và release cadence** đủ rõ.

### 4.4. Không tái sử dụng QName với semantics khác

Giả sử v1:

~~~xml
<ord:amount currency="VND">1200.00</ord:amount>
~~~

và v2 muốn `amount` biểu diễn số tiền sau thuế thay vì trước thuế. Giữ QName và type nhưng đổi semantics là phá vỡ contract ở cấp nghiệp vụ. Nên tạo element/operation/namespace thể hiện rõ thay đổi, ví dụ `netAmount`/`grossAmount`, hoặc major namespace mới với tài liệu mapping cụ thể.

**QName là tên của cấu trúc XML, không tự mô tả đầy đủ ý nghĩa nghiệp vụ.** Documentation và semantics phải được version cùng contract.

## 5. Version theo endpoint: khi nào nên tách URL?

Endpoint version là lựa chọn mạnh khi cần phân tách deployment hoặc security boundary. Ví dụ:

~~~text
/ws/orders/v1
/ws/orders/v2
~~~

Một `MessageDispatcherServlet` có thể được map ở servlet path chung như `/ws/*`, trong khi Spring-WS endpoint hoặc reverse proxy chọn URL cụ thể. Cũng có thể triển khai hai ứng dụng/servlet riêng. **Không bắt buộc** một URL path version tương ứng một process hay một server riêng.

### 5.1. Ưu điểm của endpoint version

- Dễ route v1 và v2 qua gateway, load balancer hoặc service discovery.
- Có thể áp chính sách rate limit, allowlist đối tác, mTLS, authentication riêng.
- Cho phép v1 giữ WSDL cũ trong khi v2 nâng dependency hoặc runtime.
- Hỗ trợ canary/traffic shifting theo endpoint.
- Dễ thống kê traffic theo version mà không cần chỉ parse SOAP Body.

### 5.2. Nhược điểm và chi phí

- Tạo nhiều URL, WSDL address và cấu hình TLS/authentication phải duy trì.
- Client cần đổi endpoint, certificate pinning/firewall/allowlist có thể cần cập nhật.
- Cùng một endpoint version có thể bị cấu hình nhận nhầm schema/action nếu adapter không kiểm tra.
- Có thể nhân bản deployment và monitoring, tốn tài nguyên.
- Reverse proxy path rewrite, context path hoặc servlet mapping dễ làm endpoint behavior không như WSDL công bố.

### 5.3. Endpoint version không thay contract version

Một endpoint `/v2` có thể vẫn công bố `targetNamespace="urn:example:orders:v1"`. Điều này đôi khi đúng nếu chỉ đổi địa chỉ do hạ tầng, nhưng gây hiểu sai nếu XML structures và business semantics đã đổi.

Quyết định nên được ghi rõ:

| Endpoint | Namespace | WSDL package | Ý nghĩa |
| --- | --- | --- | --- |
| `/soap/orders` | `urn:example:orders:v1` | orders-v1.wsdl | Legacy route giữ contract v1. |
| `/soap/orders/v2` | `urn:example:orders:v2` | orders-v2.wsdl | Contract v2 với cấu trúc/semantics mới. |
| `/soap/orders/blue` | `urn:example:orders:v1` | orders-v1.wsdl | Có thể chỉ là deployment/traffic alias của v1, không phải schema v2. |

Tên route như `blue` trong ví dụ là deployment alias, không phải version contract. Không suy version từ URL khi namespace/WSDL/policy nói điều khác.

### 5.4. Version bằng query parameter hoặc HTTP header?

Các mẫu như:

~~~text
POST /ws?version=2
X-Contract-Version: 2
Accept: application/vnd.example.orders-v2+xml
~~~

có thể dùng khi thiết kế gateway/protocol riêng, nhưng **không phải cơ chế version SOAP phổ quát tự động**. SOAP stacks có thể không hỗ trợ negotiation đó; intermediary có thể loại bỏ header; proxy cache/routing phải hiểu chính sách.

Đặc biệt, dùng custom HTTP header để chọn schema nhưng WSDL/namespace/Action vẫn giống nhau làm request khó tự mô tả khi log/replay. Nếu dùng, cần công bố rõ trong contract, reject version không hỗ trợ và đảm bảo mọi thành phần routing/monitoring hiểu cùng một quy tắc. Không tự chọn v2 khi thiếu header theo kiểu fallback mơ hồ.

## 6. Version theo hợp đồng WSDL/XSD được công bố

Trong tích hợp enterprise, **WSDL không chỉ là file để IDE đọc**. Nó là artifact contract mà đối tác dùng để generate stub, xác định endpoint, SOAP binding, operation, fault và đôi khi policy. Vì vậy cần có quy tắc phát hành WSDL/XSD giống như phát hành một API package.

### 6.1. Contract release nên bất biến

Một contract version đã phát hành nên giữ nội dung không đổi tại địa chỉ phân phối version đó:

~~~text
/contracts/orders/v1/orders.wsdl
/contracts/orders/v1/xsd/orders-types.xsd
/contracts/orders/v1/xsd/common-types.xsd

/contracts/orders/v2/orders.wsdl
/contracts/orders/v2/xsd/orders-types.xsd
/contracts/orders/v2/xsd/common-types.xsd
~~~

Nếu cần sửa lỗi tài liệu mà không đổi wire behavior, hãy phát hành revision tài liệu có changelog rõ hoặc sửa trước khi công bố. **Không thay âm thầm XSD đã public** trong khi URL vẫn giữ nguyên, vì client build lại có thể generate types khác so với client đang chạy.

Mỗi release nên lưu:

- WSDL entry point và tất cả import/include closure.
- XSD files cùng target namespaces, version và dependencies.
- WS-Policy/security profile hoặc tài liệu security contract.
- Endpoint addresses theo môi trường (dev/test/prod) hoặc quy tắc discovery.
- SHA-256 checksum, version label, ngày phát hành và owner.
- Compatibility notes, changelog, deprecation và supported-until.
- Test fixtures request/response/Fault đã loại bỏ dữ liệu nhạy cảm.

### 6.2. WSDL 1.1 không tự tạo semantic versioning

WSDL 1.1 mô tả `definitions`, `types`, `message`, `portType`, `binding`, `service` và `port`; nó **không cung cấp một cơ chế universal** để mọi SOAP tools tự nâng major/minor theo một trường version. Có thể dùng metadata/documentation, namespace, URL và release registry để quản lý version; client generators vẫn cần đọc đúng WSDL/XSD.

Ví dụ targetNamespace của WSDL:

~~~xml
<wsdl:definitions
    xmlns:wsdl="http://schemas.xmlsoap.org/wsdl/"
    xmlns:tns="urn:example:orders:wsdl:v2"
    xmlns:ord="urn:example:orders:v2"
    targetNamespace="urn:example:orders:wsdl:v2">

  <!-- types, messages, portType, binding, service ... -->

</wsdl:definitions>
~~~

Trong ví dụ, namespace của WSDL definitions và namespace của payload schema được phân biệt. Đây là một lựa chọn thiết kế; có dự án dùng cùng URI cho cả WSDL definitions và XSD target namespace. **Điều quan trọng là `wsdl:message` tham chiếu đúng element QName** và tài liệu công bố không để lẫn v1/v2.

### 6.3. XSD import/include phải có version closure rõ

Một WSDL có thể import XSD theo URI tương đối:

~~~xml
<xs:import
    namespace="urn:example:common:v2"
    schemaLocation="xsd/common-v2.xsd"/>
~~~

Contract release không đầy đủ nếu `orders.wsdl` là v2 nhưng `common-v2.xsd` bị ghi đè bởi shared schema v3 mà không tương thích. Phải version hóa và khóa dependency closure, hoặc ghi rõ shared schema nào được phép evolve mà không phá client.

Đối với import bên ngoài organization, pin bản schema đã được duyệt và phân phối offline theo policy; không để một WSDL v2 phụ thuộc URI `latest/common.xsd` có thể thay nội dung sau ngày phát hành. Điều này còn giúp JAXB code generation tái lập được.

### 6.4. WSDL service address có thể khác URL phân phối WSDL

WSDL có thể được lưu tại contract registry hoặc tài liệu tĩnh, trong khi `soap:address` chứa endpoint service. Một WSDL v2 có thể được publish tại:

~~~text
https://contracts.example.test/orders/v2/orders.wsdl
~~~

và khai báo endpoint:

~~~xml
<soap:address
    location="https://api.example.test/soap/orders/v2"/>
~~~

Hai URL phục vụ vai trò khác nhau: một nơi tải **contract**, một nơi gửi **SOAP message**. Nếu WSDL chứa hostname nội bộ hoặc dev URL khi partner tải, client generator có thể ghi cứng endpoint sai. Có thể phát hành WSDL theo môi trường, rewrite address tại gateway một cách có kiểm soát hoặc dùng cấu hình endpoint runtime ở client; **không để address rewrite thay đổi schema/QName**.

### 6.5. WSDL/XSD diff phải được review như source code

Mỗi pull request thay contract nên hiển thị diff và phân loại:

- QName và namespace URI nào được thêm/xóa/đổi?
- Element/attribute nào đổi type, occurrence, nillable hoặc order?
- Enumeration/facets/pattern/min/max có đổi?
- Operation, input/output, Fault, SOAPAction có đổi?
- SOAP version/binding/address có đổi?
- WS-Addressing/WS-Policy/WS-Security assertions có đổi?
- Có reference import/include nào trỏ tới version khác?
- Java/JAXB generated sources có thay đổi đáng kể?
- Client cũ có thể serialize request và parse response mới không?

**Diff XML thuần có thể bỏ sót semantic breaking change.** Cần review tài liệu nghiệp vụ và compatibility tests cùng với schema diff.

## 7. Tổ chức code Spring-WS để phục vụ nhiều contract versions

Spring-WS endpoint mapping dựa vào message/payload metadata. Một kiến trúc an toàn thường giữ **adapter riêng theo contract version**, chuyển về application service/domain model chung khi semantics tương thích.

### 7.1. PayloadRoot theo namespace là một ranh giới định tuyến tự nhiên

Ví dụ v1 và v2 có hai root QName:

~~~xml
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v1">
  <ord:clientOrderId>WEB-42</ord:clientOrderId>
</ord:CreateOrderRequest>
~~~

~~~xml
<ord:CreateOrderRequest
    xmlns:ord="urn:example:orders:v2">
  <ord:clientOrderId>WEB-42</ord:clientOrderId>
  <ord:currency>VND</ord:currency>
</ord:CreateOrderRequest>
~~~

Spring-WS `@PayloadRoot` chọn endpoint dựa trên namespace URI và local part. Có thể duy trì hai handler:

~~~java
import org.springframework.ws.server.endpoint.annotation.Endpoint;
import org.springframework.ws.server.endpoint.annotation.PayloadRoot;
import org.springframework.ws.server.endpoint.annotation.RequestPayload;
import org.springframework.ws.server.endpoint.annotation.ResponsePayload;

@Endpoint
public class OrdersV1Endpoint {

    private static final String NS = "urn:example:orders:v1";
    private final OrderApplicationService application;

    public OrdersV1Endpoint(OrderApplicationService application) {
        this.application = application;
    }

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderV1Response create(
            @RequestPayload CreateOrderV1Request request) {
        CreateOrderCommand command = OrderV1Mapper.toCommand(request);
        return OrderV1Mapper.fromResult(application.create(command));
    }
}
~~~

~~~java
@Endpoint
public class OrdersV2Endpoint {

    private static final String NS = "urn:example:orders:v2";
    private final OrderApplicationService application;

    public OrdersV2Endpoint(OrderApplicationService application) {
        this.application = application;
    }

    @PayloadRoot(namespace = NS, localPart = "CreateOrderRequest")
    @ResponsePayload
    public CreateOrderV2Response create(
            @RequestPayload CreateOrderV2Request request) {
        CreateOrderCommand command = OrderV2Mapper.toCommand(request);
        return OrderV2Mapper.fromResult(application.create(command));
    }
}
~~~

Các lớp `CreateOrderV1Request`, `CreateOrderV2Request`, response và mapper là **DTO được giả định generate từ hai XSD riêng**. `OrderApplicationService` nhận domain command trung lập với SOAP. Ví dụ không chứa toàn bộ JAXB/configuration; cần khai báo marshaller có thể nhận biết packages/object factories của các contract versions.

### 7.2. Đừng để version-specific DTO rò vào domain model

Một cách tổ chức:

~~~text
soap/
  v1/
    endpoint/OrdersV1Endpoint.java
    dto/                 (JAXB từ XSD v1)
    mapping/OrderV1Mapper.java
  v2/
    endpoint/OrdersV2Endpoint.java
    dto/                 (JAXB từ XSD v2)
    mapping/OrderV2Mapper.java

application/
  CreateOrderCommand.java
  CreateOrderResult.java
  OrderApplicationService.java

domain/
  Order.java
  Money.java
  OrderStatus.java
~~~

Mục tiêu là adapter version xử lý XML/contract differences, còn domain/application chứa business rules chung. Tuy nhiên, **không ép v1/v2 vào cùng model nếu semantics thật sự khác**; khi đó cần transformation/use case rõ hoặc domain service riêng. Mapper phải phát hiện mất thông tin, không lặng lẽ đặt default làm thay đổi ý nghĩa giao dịch.

### 7.3. Nếu cùng một URL nhận nhiều namespace versions

Có thể cùng `/ws` phục vụ nhiều QName versions. Khi đó phải đảm bảo:

- Payload root mapping v1/v2 không mơ hồ.
- JAXB marshaller/unmarshaller biết cả hai packages hoặc được cấu hình theo endpoint/version.
- WSDL metadata đúng cho endpoint và action mapping.
- Validation áp dụng đúng schema của request version.
- Output QName, SOAP Fault và WS-Addressing Action thuộc version tương ứng.
- WS-Security policy giống hay khác được xác định rõ theo request route/contract.

Một endpoint URL duy nhất không buộc toàn bộ message phải cùng namespace, nhưng có thể làm **security policy và contract discovery khó hơn**. Nếu gateway hoặc partner chỉ có thể quản lý một contract/endpoint tại một thời điểm, path version có thể đơn giản hơn.

### 7.4. Route theo endpoint và mapping theo payload có thể cùng tồn tại

Ví dụ:

~~~text
POST /soap/orders/v1 → servlet/gateway route v1 → v1 payload namespace
POST /soap/orders/v2 → servlet/gateway route v2 → v2 payload namespace
~~~

Ở đây endpoint route chọn vùng phục vụ, còn QName mapping kiểm tra payload đúng version. Đây là **defense-in-depth chống nhầm contract**: client gửi payload v1 tới URL v2 phải bị từ chối hoặc xử lý theo policy rõ ràng, không âm thầm fallback sang v1.

Có thể triển khai bằng hai servlet mappings/applications, hai endpoint URL sau proxy hoặc một dispatcher với interceptors kiểm tra path/version. Cách triển khai cụ thể phụ thuộc servlet mapping và Spring configuration, không nên giả định `@PayloadRoot` tự kiểm tra HTTP path.

### 7.5. SOAPAction và WS-Addressing Action cũng phải version hóa nhất quán

Ví dụ:

~~~text
v1: urn:example:orders:v1/CreateOrder
v2: urn:example:orders:v2/CreateOrder
~~~

Nếu Body QName v2 nhưng SOAPAction/WS-A Action v1, mapping hoặc policy có thể chọn sai operation hoặc từ chối message. Tùy stack, action có thể được dùng ở transport binding, WS-Addressing header hoặc cả hai. Phải so với WSDL binding và metadata; **không mặc định SOAPAction, WS-A Action, operation name và Body QName là một giá trị**.

### 7.6. Endpoint adapters không phải hai implementation nghiệp vụ độc lập

Hai endpoint classes nên gọi các application use cases có định nghĩa rõ, thay vì copy/paste transaction logic. Điều này giúp:

- Fix business bug một lần mà không tạo drift giữa v1/v2.
- Tập trung compatibility mapping ở adapter.
- Đánh giá version cũ có còn được hỗ trợ mà không giữ toàn bộ domain code cũ.
- Test mapping độc lập với SOAP stack.
- Ghi metrics theo version và client identity.

Nếu behavior khác vì v2 có semantics mới, hãy thể hiện khác biệt trong command/use case hoặc application policy; không giấu trong mapper bằng những defaults không được contract mô tả.

## 8. JAXB và code generation trong chiến lược version

JAXB biến XML theo schema thành Java object. Khi có nhiều contract versions, **mỗi namespace/type set có thể sinh ra một Java model riêng**. Điều đó là bình thường; không nên cố giữ một DTO Java duy nhất nếu XML contract đã phân kỳ.

### 8.1. Tách package JAXB theo namespace/version

Một cách tổ chức codegen:

~~~text
generated/
  orders/
    v1/
      ObjectFactory.java
      CreateOrderRequest.java
      CreateOrderResponse.java
    v2/
      ObjectFactory.java
      CreateOrderRequest.java
      CreateOrderResponse.java
~~~

Các package khác nhau giúp tránh xung đột class name và cho phép cả hai schema versions cùng được load. Dùng binding customization để đặt package ổn định, thay vì dựa vào cách JAXB generator tự suy từ namespace khi có nhiều schema.

### 8.2. JAXBContext phải biết đúng các model

Với JAXB 2/Jakarta JAXB, ứng dụng có thể tạo context theo package hoặc classes được khai báo rõ. Ví dụ theo package context path (cần chọn API namespace khớp dependency thực tế):

~~~java
import jakarta.xml.bind.JAXBContext;
import jakarta.xml.bind.JAXBException;

public final class OrdersJaxbContexts {

    private OrdersJaxbContexts() {}

    public static JAXBContext create() throws JAXBException {
        return JAXBContext.newInstance(
            "com.example.orders.v1:com.example.orders.v2");
    }
}
~~~

Đây là ví dụ dùng `jakarta.xml.bind` cho runtime Jakarta JAXB. Dự án Spring-WS/JAXB đời cũ có thể còn dùng `javax.xml.bind`; **không trộn `javax` và `jakarta` generated classes trong cùng context**. Phải kiểm tra dependency graph và generated source namespace trước khi copy.

Trong Spring-WS, `Jaxb2Marshaller` có thể cấu hình `contextPath` hoặc `classesToBeBound`. Khi nhiều versions cùng được xử lý, hãy test unmarshalling theo từng root QName và xác nhận endpoint method nhận đúng DTO. Cũng có thể dùng marshaller riêng cho từng boundary nếu muốn tách schema/validation chặt hơn.

### 8.3. JAXB package không phải XML namespace version policy

Đổi Java package từ `com.example.orders.v1` sang `com.example.orders.v2` không tự đổi `targetNamespace`; ngược lại, hai package có thể được bind vào cùng namespace nếu mapping cho phép. **Nguồn xác định XML contract vẫn là XSD/WSDL đã công bố.**

Đừng dùng package name để chọn endpoint version, và đừng để `ObjectFactory` của v1 tạo element QName v2 chỉ vì code reuse. Kiểm tra `@XmlElementDecl`, `@XmlType(namespace=...)`, `@XmlRootElement` hoặc `JAXBElement` QName khi debug.

### 8.4. Không dùng một generated class cho hai semantics

Nếu v1 `amount` là decimal trước thuế và v2 `amount` là decimal sau thuế, class Java có cùng field `BigDecimal amount` vẫn compile nhưng ý nghĩa khác nhau. Mapper phải chuyển semantics rõ ràng, ví dụ:

~~~java
CreateOrderCommand toCommand(CreateOrderV2Request request) {
    return new CreateOrderCommand(
        request.getClientOrderId(),
        request.getGrossAmount(),
        request.getCurrency());
}
~~~

Code trên chỉ minh họa mapping, DTO/domain constructor được giả định. **Không gán v2 `amount` vào domain `netAmount` theo suy đoán**. Mỗi field cần quy tắc mapping có unit, rounding, nullability, default và compatibility được mô tả/test.

### 8.5. JAXB code generation phải tái lập

Khi phát hành v1/v2:

- Pin phiên bản JAXB/XJC plugin và binding files.
- Dùng đúng WSDL/XSD artifact release; không generate trực tiếp từ URI `latest`.
- Lưu generated code hoặc đảm bảo build có thể tái sinh cùng kết quả.
- So sánh generated diff khi schema thay đổi.
- Test round-trip marshal/unmarshal và fixture XML do đối tác gửi.
- Kiểm soát catalog/resolver cho XSD imports; build không được tải schema chưa duyệt từ mạng.
- Theo dõi thay đổi namespace/package do nâng JAXB generator.

JAXB model thay đổi không nhất thiết contract thay đổi, nhưng **contract thay đổi có thể tác động generated model**. Pull request nên review cả hai chiều.

## 9. Chọn chiến lược nào? Ma trận quyết định theo tình huống

### 9.1. Cây quyết định thực dụng

~~~mermaid
flowchart TD
    A["Có thay đổi contract SOAP?"] --> B{"Có breaking change về XML/semantics/security?"}
    B -- "Không" --> C["Giữ major contract version; publish revision/changelog"]
    B -- "Có" --> D{"Client cần chạy v1 và v2 song song?"}
    D -- "Có" --> E["Namespace v2 + WSDL/XSD release v2"]
    E --> F{"Cần tách routing/deployment/security?"}
    F -- "Có" --> G["Thêm endpoint /v2 hoặc route gateway riêng"]
    F -- "Không" --> H["Có thể cùng endpoint, map theo QName và policy"]
    D -- "Không" --> I["Có thể coordinated cutover, nhưng publish contract v2 bất biến"]
    G --> J["Test interoperability + rollout/sunset"]
    H --> J
    I --> J
    C --> J
~~~

Cây quyết định là hướng dẫn, không phải công thức cứng. Nếu security boundary thay đổi độc lập với XML body, có thể cần endpoint riêng ngay cả khi namespace giữ nguyên. Nếu namespace mới nhưng traffic không thể chạy song song, endpoint cũ có thể được thay sau coordinated cutover.

### 9.2. Bảng chọn theo nhu cầu

| Bối cảnh | Chiến lược thường phù hợp | Lý do |
| --- | --- | --- |
| Thêm optional field, không đổi semantics | Giữ namespace major và endpoint; phát hành contract revision có changelog. | Tránh migration không cần thiết; vẫn phải test client strict. |
| Đổi QName/required structure/semantics | Namespace major mới + WSDL/XSD release mới. | Message tự nhận diện được version. |
| Cần v1/v2 chạy đồng thời qua nhiều đối tác | Namespace version + contract release bất biến; thêm endpoint version nếu cần. | Tách payload và phân phối contract rõ. |
| Chỉ đổi hạ tầng/hostname, payload không đổi | Có thể giữ namespace/contract; đổi endpoint hoặc discovery alias có kế hoạch. | Không tạo XML major version giả tạo. |
| Cần security/rate limit/tenant isolation khác | Endpoint/gateway route riêng; namespace tùy contract change. | Phân tách access policy độc lập với schema. |
| Shared XSD dùng bởi nhiều services | Quản trị shared vocabulary có version và compatibility policy riêng. | Tránh một thay đổi ảnh hưởng bất ngờ nhiều consumers. |
| Partner legacy nâng cấp chậm | Duy trì v1 adapter và v2 adapter song song. | Cho từng partner migration theo lịch, tránh big-bang. |
| Một đối tác duy nhất có cutover đồng bộ | Có thể triển khai contract v2 và switch theo cửa sổ thống nhất. | Giảm chi phí chạy hai versions, nhưng vẫn cần rollback. |

### 9.3. Ví dụ kiến trúc được khuyến nghị cho B2B SOAP

~~~text
                       Contract Registry
                  ┌─────────────────────────┐
                  │ orders/v1 WSDL + XSD   │
                  │ orders/v2 WSDL + XSD   │
                  └────────────┬────────────┘
                               │
Partner A (v1) ── HTTPS ──> /soap/orders/v1
                               │
                         OrdersV1Endpoint
                               │
                         OrderV1Mapper
                               │
Partner B (v2) ── HTTPS ──> /soap/orders/v2
                               │
                         OrdersV2Endpoint
                               │
                         OrderV2Mapper
                               │
                       Application Service
                               │
                         Domain / Database
~~~

Mô hình này cung cấp ba đặc điểm: artifacts contract có version riêng; endpoint phân tách rõ; business/application logic có thể được chia sẻ có kiểm soát. Có thể triển khai endpoints trong cùng một application hoặc các deployments độc lập. Quyết định phụ thuộc lượng traffic, isolation/security requirement và vòng đời partner.

**Không nhất thiết mỗi contract version phải có một database schema riêng.** Version SOAP contract là boundary integration; database evolution phải được quản lý riêng bằng migration/backward compatibility, đặc biệt khi v1 và v2 cùng thao tác dữ liệu trong giai đoạn overlap.

## 10. Quy trình rollout v2 khi v1 vẫn đang hoạt động

Nâng contract không kết thúc khi merge XSD. Một rollout B2B an toàn nên đi theo chuỗi có điều kiện rõ ràng.

### 10.1. Giai đoạn 1 — Design và công bố

1. Ghi rõ thay đổi nào breaking và vì sao v1 không thể hấp thụ theo cách tương thích.
2. Thiết kế namespace v2, XSD types/elements và semantics.
3. Thiết kế WSDL messages, binding, SOAPAction/WS-A Action, Fault và WS-Policy.
4. Chọn endpoint v2 hoặc chiến lược cùng endpoint có QName routing.
5. Tạo contract artifact bất biến, import closure đầy đủ và changelog.
6. Tạo JAXB generated model/package v2.
7. Review security requirements, certificate identities, algorithms và partner capabilities.

Ở giai đoạn này client có thể bắt đầu generate stub và thử tích hợp trên sandbox trước khi service production được bật.

### 10.2. Giai đoạn 2 — Server support song song

- Deploy v2 endpoint/handler nhưng chưa chuyển partner production.
- Giữ v1 WSDL/XSD và v1 behavior như hiện tại.
- Route request đúng endpoint + namespace + action.
- Không cho request v1 vào v2 hoặc ngược lại khi hợp đồng không cho phép.
- Áp validation và security policy tương ứng cho từng version.
- Theo dõi metrics theo version, endpoint và partner identity.

Nếu v1 và v2 chia sẻ application service, kiểm thử regression của v1 trước khi mở v2. Một thay đổi mapper v2 không được làm thay semantics v1.

### 10.3. Giai đoạn 3 — Partner certification và canary

Mỗi partner nên có bộ chứng cứ:

- WSDL/XSD version và checksum đã tải.
- Client runtime/generator version.
- SOAP request/response fixtures đã test.
- WS-Security certificates/fingerprints, mTLS chain nếu có.
- Kết quả negative tests: sai QName, sai Action, cert hết hạn, schema lỗi.
- Operation/Fault behavior và retry/idempotency.
- Endpoint address được allowlist và môi trường kết nối.

Bật production từng partner hoặc nhóm traffic nhỏ; kiểm tra fault rate, latency, payload validation errors, authentication failures và business results. Không chuyển toàn bộ partner chỉ vì một client nội bộ đã thành công.

### 10.4. Giai đoạn 4 — Chuyển traffic và giữ rollback

- Xác nhận partner v2 đã sẵn sàng trước khi đổi endpoint/configuration.
- Chuyển đúng identity/tenant tới v2.
- Duy trì v1 route trong thời gian overlap theo cam kết.
- Có khả năng chuyển partner về v1 nếu regression được xác nhận và data semantics cho phép.
- Không rollback nếu v2 đã tạo side effects không thể đảo ngược mà không có reconciliation plan.
- Lưu logs/metrics theo contract version để điều tra.

**Rollback code không tự undo business data.** Nếu v2 thay đổi quy tắc tiền tệ, trạng thái đơn hoặc side effects, cần thiết kế compatibility/reconciliation trước rollout.

### 10.5. Giai đoạn 5 — Deprecation và sunset v1

Khi v1 giảm traffic, cần thông báo partner qua kênh quản trị hợp đồng:

- Ngày bắt đầu deprecation.
- Ngày dự kiến sunset và điều kiện gia hạn.
- Endpoint v2/WSDL/XSD và tài liệu migration.
- Những thay đổi semantics và security.
- Kênh hỗ trợ/certification test.
- Bằng chứng partner đã chuyển.
- Quy trình exception cho đối tác chưa hoàn tất.

Không xóa v1 chỉ vì metrics trong một tuần bằng 0; có thể partner gọi theo chu kỳ quý, mùa vụ hoặc DR/failover. Xác minh contract owner và thời gian lưu giữ theo thỏa thuận.

## 11. Kiểm thử tương thích contract versions

Một contract version chỉ được coi là sẵn sàng khi có bằng chứng từ **cả client lẫn server**. Việc WSDL compile, endpoint khởi động hoặc một request v2 trả HTTP 200 không đủ để chứng minh v1 vẫn hoạt động và partner stacks tương thích.

### 11.1. Test matrix theo chiều request/response

| Test | Client | Server | Câu hỏi phải trả lời |
| --- | --- | --- | --- |
| v1 baseline | Client v1 | Server v1 | Hành vi cũ vẫn đúng như contract đã công bố? |
| v1 sau deploy v2 | Client v1 | Server có v1+v2 | Không có regression do code shared hoặc mapping mới? |
| v2 baseline | Client v2 | Server v2 | Request/response/Fault đúng WSDL/XSD mới? |
| Wrong namespace | Client gửi QName v1 tới route v2 | Server v2 | Bị từ chối hoặc hành xử theo policy rõ ràng, không xử lý nhầm? |
| Wrong endpoint | Client gửi payload v2 tới route v1 | Server v1 | Không fallback âm thầm sang v2? |
| Wrong SOAPAction | Action v1 với Body v2 | Server | Mapping/action policy phát hiện mismatch? |
| Unknown enum/value | Client gửi giá trị chưa biết | Server/client | Parser và business logic xử lý theo chính sách rõ ràng? |
| Missing required field | Payload thiếu element required | Server | Validation từ chối trước business side effect? |
| Optional extension | Payload có/không có optional v2 field | Server | Default/omission semantics được xử lý đúng? |
| Response parsing | Server response v2 | Client v1 và v2 | Client cũ có đọc được không; nếu không, version boundary có ngăn gọi sai? |
| SOAP Fault | Fault v1/v2 | Client đúng version | Fault code/detail/action được phân loại đúng? |
| WS-Addressing | Action/To/RelatesTo theo v1/v2 policy | Server/client | Header version và URI mapping khớp? |
| WS-Security | Signature/encryption policy từng version | Server/client | Signed parts, certificates, algorithms và trust đúng? |
| mTLS | Client certificate theo route | Gateway/server | Trust, identity mapping và access policy đúng? |
| Retry/timeout | Client cũ/mới | Server | Side effect idempotent theo contract? |
| Concurrent versions | Nhiều partner v1/v2 | Server | Không lẫn JAXB context, tenant, alias, endpoint hoặc metrics? |

### 11.2. Positive tests và negative tests có mục tiêu khác nhau

**Positive tests** chứng minh request hợp lệ được chấp nhận và response đúng contract:

- WSDL/XSD version đúng và import closure có đủ.
- SOAP Envelope version đúng binding.
- Body root QName đúng.
- SOAPAction/WS-A Action đúng operation.
- WS-Security/mTLS theo policy được chấp nhận.
- JAXB round-trip không mất dữ liệu.
- Response và SOAP Fault serialize đúng version.

**Negative tests** chứng minh server từ chối sai version hoặc sai policy:

- Namespace không được hỗ trợ.
- Body QName v1 gửi tới route v2.
- Action không khớp operation hoặc WSDL.
- Required field thiếu/sai format.
- Certificate/signature không trust hoặc sai recipient key.
- WS-Addressing version không được phép.
- SOAP 1.1 request gửi vào binding chỉ nhận SOAP 1.2.
- Unknown version header hoặc URL không tồn tại.
- Request tạo side effect không được xử lý khi validation/security thất bại.

Không chỉ assert HTTP status: cần xác nhận **business service không được gọi** với các request bị từ chối và không có dữ liệu giao dịch bị ghi một phần.

### 11.3. Test contract v1 sau khi code v2 đã được thêm

Một lỗi phổ biến là test v2 kỹ nhưng không test regression v1. Giữ lại fixture bất biến:

~~~text
src/test/resources/contracts/orders/v1/
  create-order-request.xml
  create-order-response.xml
  create-order-invalid.xml
  create-order-fault.xml

src/test/resources/contracts/orders/v2/
  create-order-request.xml
  create-order-response.xml
  create-order-invalid.xml
  create-order-fault.xml
~~~

Các fixtures cần che thông tin nhạy cảm và có expected result rõ. Khi thay XSD, test server serializer/unmarshaller, client code generated và lỗi tương thích theo phiên bản. Nếu một fixture v1 bắt đầu thất bại sau commit v2, phải điều tra trước khi release.

### 11.4. Test Spring-WS endpoint bằng MockWebServiceClient

`MockWebServiceClient` có thể kiểm tra payload dispatch và response tại ApplicationContext. Ví dụ skeleton:

~~~java
import org.springframework.ws.test.server.MockWebServiceClient;
import org.springframework.xml.transform.StringSource;

import static org.springframework.ws.test.server.RequestCreators.withPayload;
import static org.springframework.ws.test.server.ResponseMatchers.noFault;

MockWebServiceClient client =
    MockWebServiceClient.createClient(applicationContext);

String request = """
    <ord:CreateOrderRequest
        xmlns:ord="urn:example:orders:v2">
      <ord:clientOrderId>WEB-42</ord:clientOrderId>
      <ord:currency>VND</ord:currency>
    </ord:CreateOrderRequest>
    """;

client.sendRequest(withPayload(new StringSource(request)))
      .andExpect(noFault());
~~~

Đây là **test skeleton**, giả định `applicationContext` có endpoint v2, marshaller và service test double phù hợp. `noFault()` chỉ xác nhận không có Fault; test hoàn chỉnh cần matcher/assertion để kiểm tra response QName, values, action/header và đúng endpoint được gọi. Dùng spy/fake service để xác nhận namespace v1 không vô tình gọi handler v2.

`MockWebServiceClient` không kiểm tra reverse proxy, TLS/mTLS, HTTP security chain, URL routing thực hoặc contract WSDL GET. Cần kết hợp tests ở những tầng đó.

### 11.5. Test SOAP clients bằng MockWebServiceServer và fixture response

Ở client side, `MockWebServiceServer` có thể kiểm tra `WebServiceTemplate` gửi đúng payload và xử lý response/Fault giả lập. Bộ test nên:

- Assert SOAP Body QName theo namespace version.
- Assert SOAPAction/WS-Addressing Action nếu dùng.
- Assert WS-Security header/key references trong cấu hình test được phép.
- Trả fixture response v1/v2 và xác nhận JAXB unmarshal.
- Trả SOAP Fault và xác nhận client map error đúng version.
- Kiểm tra timeout/retry không thay payload version hoặc correlation semantics.

Mock sender không chứng minh interoperability với Java/.NET/Axis/CXF hay gateway thật. Các partner integration tests phải chạy với message captures và endpoint tương thích được kiểm soát.

### 11.6. WSDL/XSD compatibility gate trong CI

Một pipeline có thể kiểm tra:

~~~text
1. Resolve WSDL và toàn bộ import/include offline.
2. Validate tất cả XSD files theo XML Schema processor.
3. Generate JAXB sources với tool version đã pin.
4. Diff WSDL/XSD với release trước và phân loại breaking changes.
5. Compile client v1 và client v2 fixtures.
6. Run endpoint v1/v2 positive/negative tests.
7. Run request/response/Fault wire compatibility tests.
8. Run WS-Security/TLS test profile trong môi trường an toàn.
9. Fail pipeline nếu v1 regressions hoặc dependency contract bị thay âm thầm.
~~~

Bước 4 cần công cụ diff có hiểu schema hoặc quy trình review thủ công; `git diff` thuần không tự xác định mọi breaking changes. Bước 8 dùng test keys/certificates, không đưa private keys production vào CI fixtures.

## 12. WS-Security, WS-Addressing và SOAP Fault cũng phải đi theo contract version

Version hóa chỉ Body XSD mà bỏ quên SOAP Header là nguồn mismatch phổ biến.

### 12.1. WS-Addressing Action

Nếu v1/v2 có action URIs riêng:

~~~text
v1 request: urn:example:orders:v1/CreateOrder
v2 request: urn:example:orders:v2/CreateOrder
~~~

WSDL và client phải khai báo/gửi đúng giá trị. Với WS-Addressing 1.0, SOAP Header QName của `wsa:Action` dùng namespace `http://www.w3.org/2005/08/addressing`; không nhầm namespace của header với namespace của payload. Nếu service đồng thời hỗ trợ WS-Addressing August 2004, phải công bố rõ version addressing được chấp nhận. **Contract version của payload và WS-Addressing version là hai trục khác nhau.**

### 12.2. WS-Security policy

v1 và v2 có thể cần policy khác nhau, ví dụ:

- v1 chấp nhận certificate cũ trong cửa sổ migration; v2 bắt buộc cert mới.
- v2 yêu cầu ký thêm SOAP Header/Body parts.
- v2 nâng algorithm suite hoặc yêu cầu timestamp/replay protection.
- recipient encryption certificate đổi theo key rotation.
- mTLS trust/identity mapping thay đổi khi partner thay tổ chức hoặc certificate.

Không để client chọn security profile bằng một header tùy ý mà server không xác thực. Nên gắn policy với endpoint/partner identity/contract configuration và test policy negotiation/validation.

### 12.3. SOAP Fault là phần của contract

Không chỉ response success cần version. Mỗi version phải quy định:

- Fault code/QName và sender/receiver semantics.
- Detail schema và các fields có thể xuất hiện.
- Những lỗi nào retry được và lỗi nào không.
- Mapping từ validation/security/business exception sang SOAP Fault.
- SOAP 1.1 `faultcode/faultstring/detail` hay SOAP 1.2 `Code/Reason/Detail`.
- Action của Fault nếu WS-Addressing được yêu cầu.

Nếu v2 đổi Fault code mà client v1 vẫn gọi nhầm endpoint, retry logic có thể hoạt động sai hoặc lặp giao dịch. Test lỗi theo đúng contract version, không chỉ test success.

### 12.4. WS-Policy không tự thay version registry

Một policy assertion có thể mô tả addressing/security requirement, nhưng không tự quản lý lịch sử WSDL/XSD hay deprecation schedule. Đảm bảo policy được phân phối cùng đúng WSDL release và không bị thay đổi âm thầm dưới cùng URL. Nếu partner tải policy riêng, phải có cách gắn policy vào contract release/checksum tương ứng.

## 13. Troubleshooting: phát hiện contract version mismatch

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| HTTP 404 trên endpoint v2 | URL chưa được deploy, proxy route sai hoặc WSDL address không đúng. | So sánh public URL, servlet mapping, gateway route và `soap:address`. |
| SOAP Fault không tìm thấy endpoint | Payload root QName/namespace không có mapping. | Đọc QName đầy đủ `{namespace}localPart`; so `@PayloadRoot` v1/v2. |
| Body đúng nhưng `ActionNotSupported` | SOAPAction/WS-A Action sai hoặc mapping dùng action version khác. | So WSDL binding, action URI và Header namespace. |
| JAXB `UnmarshalException` | Client/server dùng model/schema khác, root QName sai hoặc required field thiếu. | Lưu fixture đã redacted, xác minh schema version và `JAXBContext`. |
| `unexpected element` ở response | Server trả namespace v2 cho client chỉ biết v1. | Kiểm tra response QName, `ObjectFactory` và endpoint route. |
| Client v1 tự nhiên fail sau deploy v2 | XSD/import chung bị thay đổi, mapper shared regressions hoặc endpoint route trỏ nhầm. | Chạy fixture v1, diff WSDL/XSD closure và xác nhận deployment route. |
| WSDL v2 lại import XSD v1 | `schemaLocation` hoặc catalog mapping chưa được cập nhật. | Resolve toàn bộ import/include và đọc target namespace từng schema. |
| WSDL tải được nhưng client gọi sai host | `soap:address` chứa dev/internal hostname hoặc proxy rewrite sai. | Inspect WSDL công bố từ mạng partner và URL runtime thực tế. |
| JAXB generated packages trùng class names | Binding customization không tách package v1/v2. | Inspect XJC output, `ObjectFactory` và context path. |
| Request v1 bị handler v2 xử lý | Endpoint mapping thiếu namespace guard hoặc route fallback mơ hồ. | Test QName exact, servlet route và mapping precedence. |
| Request v2 tới route v1 vẫn thành công | V1 endpoint nhận rộng hoặc schema/namespace bị giữ nguyên ngoài ý định. | Kiểm tra root QName/validation; reject version mismatch tường minh. |
| WS-Security v1 pass, v2 fail | Policy, key identifier, certificate, signed parts hoặc algorithms khác. | So WS-Policy, WSS4J config, cert trust và message capture. |
| mTLS v2 fail nhưng v1 pass | Gateway v2 có trust/issuer/hostname policy khác hoặc endpoint cert đổi. | TLS handshake logs, chain/SAN, client cert identity và trust anchors. |
| WS-Addressing response không correlate | `RelatesTo`/output Action không thuộc version hoặc request MessageID không được giữ. | Capture request/response Header, so namespace và relationship. |
| Client parse được response nhưng kết quả nghiệp vụ sai | Semantic version mismatch: field giữ type/QName nhưng đổi meaning. | Kiểm tra unit, rounding, currency, default và mapping semantics. |
| Fault v2 bị client retry vô hạn | Fault code/detail mới không được map vào retry categories. | Review error contract, retryability và idempotency. |
| Client lấy nhầm contract từ cache | Contract URL không versioned/cache policy không rõ. | Kiểm tra URL, ETag/checksum, cache-control và registry release. |
| Import XSD phụ thuộc Internet | Contract release thiếu dependency closure hoặc URI `latest`. | Bundle schema đã duyệt, pin version và kiểm thử offline. |
| Endpoint v1 bị xóa sớm | Sunset chỉ dựa traffic ngắn hạn. | Đối chiếu partner inventory, chu kỳ batch/DR và owner sign-off. |
| v2 rollback nhưng data đã thay semantics | Không có migration/reconciliation plan. | Đối chiếu writes, idempotency, compensation và dữ liệu đã phát sinh. |

### 13.1. Quy trình điều tra theo thứ tự

~~~text
1. Xác định client đang dùng WSDL/XSD release nào (version + checksum).
2. Xác định HTTP URL thật, context path, servlet mapping và gateway route.
3. Capture SOAP Envelope đã redacted: SOAP version, Body QName, Action, headers.
4. So namespace URI và localPart với endpoint mapping.
5. Kiểm tra SOAPAction/WS-Addressing Action và WSDL binding.
6. Xác nhận XSD import/include closure và JAXB generated package/context.
7. Xem WS-Security, certificate/trust, mTLS và WS-Policy của đúng version.
8. Phân biệt HTTP error, SOAP Fault, JAXB validation và business error.
9. Chạy fixture regression v1/v2 và xác minh side effects.
10. Chỉ điều chỉnh đúng ranh giới contract bị mismatch.
~~~

Không sửa đồng thời namespace, URL, SOAPAction, XSD, JAXB package và security policy chỉ để “thử cho chạy”. Thay một trục tại một thời điểm, ghi lại request/response thực và kiểm tra lại client tương ứng.

## 14. Bài tập tình huống có đáp án gợi ý

### Tình huống A — Chỉ thêm optional currency

v1 có `amount` decimal, v2 muốn bổ sung `currency` nhưng semantics `amount` không đổi. Tất cả client đã biết cách bỏ qua element lạ; một đối tác dùng parser strict.

**Đáp án:** Không thể kết luận additive change tương thích chỉ từ `minOccurs="0"`. Kiểm thử parser của đối tác strict. Có thể giữ major namespace nếu chính sách contract cho phép, nhưng phát hành revision/changelog và xác nhận client cụ thể. Nếu không có bằng chứng tương thích, cung cấp contract v2 song song.

### Tình huống B — Thay URL nhưng không đổi XML

Hệ thống chuyển từ hostname cũ sang API gateway mới. XSD, QName, SOAPAction, Fault và security profile không đổi.

**Đáp án:** Có thể giữ namespace và contract release; cập nhật endpoint/discovery hoặc phát hành address riêng theo môi trường. Đây là thay đổi transport/deployment, không nhất thiết là XML major version. Kiểm tra DNS, TLS SAN, mTLS, firewall/allowlist và WSDL `soap:address`.

### Tình huống C — Giữ URL, đổi namespace

Server muốn dùng cùng `/ws` nhưng thêm namespace v2 và `@PayloadRoot` mapping v2.

**Đáp án:** Có thể nếu gateway/partner chấp nhận cùng endpoint phục vụ nhiều payload versions. Phải route đúng QName, JAXB context, schema, action, Fault và security policy cho từng version; test v1/v2 đồng thời. Nếu một số intermediary không phân biệt được message/contract, dùng endpoint riêng sẽ rõ hơn.

### Tình huống D — Endpoint /v2 vẫn dùng namespace v1

Một nhóm thêm `/soap/orders/v2` nhưng vẫn copy nguyên WSDL/XSD v1. Họ nói đây là contract version mới.

**Đáp án:** Chưa chắc là contract v2. Nếu chỉ đổi route, đó có thể là deployment alias của v1. Nếu semantics/XML thay đổi, nên dùng namespace/schema major mới hoặc ghi rõ lý do giữ namespace và cách partner nhận diện contract. Không để tên URL thay thế thông tin contract thật.

### Tình huống E — Namespace mới nhưng WSDL cũ

WSDL v1 vẫn được publish ở URL cũ, nhưng file XSD import cùng tên bị thay bằng schema v2.

**Đáp án:** Đây là contract release không bất biến. Client tải lại WSDL v1 có thể nhận schema v2. Khôi phục schema v1 tại location cũ, publish dependency path/version riêng cho v2, kiểm tra checksum/import closure và cache policy.

### Tình huống F — JAXB CreateOrderRequest trùng class name

v1/v2 đều generate `CreateOrderRequest.java` trong cùng package vì không có binding customization. Build lỗi hoặc marshaller không phân biệt version.

**Đáp án:** Tách generated packages theo namespace/contract, tạo `JAXBContext` phù hợp hoặc marshaller riêng. Không đổi XML namespace chỉ để chữa lỗi Java package; namespace version được quyết định bởi contract.

### Tình huống G — Thêm enum value nhưng client cũ không parse

Server v2 thêm `ON_HOLD` vào status enum. Một client v1 dùng Java enum closed set và throw khi nhận giá trị lạ.

**Đáp án:** Đây có thể là breaking change dù XSD chỉ thêm enumeration. Giữ semantics/status set v1 ổn định hoặc dùng v2 contract cho client hiểu giá trị mới; test generated client thật, không chỉ XML validator.

### Tình huống H — WSDL v2 dùng SOAPAction v1

Payload namespace và XSD là v2, nhưng SOAP binding copy `soapAction` của v1. Client v2 nhận `ActionNotSupported`.

**Đáp án:** Đồng bộ input/output/fault action trong WSDL với endpoint mapping và client. Phân biệt HTTP SOAPAction với WS-Addressing `wsa:Action`; sửa đúng layer và thêm fixture test cho request/response.

### Tình huống I — WS-Security policy đổi nhưng namespace không đổi

v2 yêu cầu chữ ký thêm header và certificate mới, nhưng nhóm giữ endpoint và namespace vì Body không đổi.

**Đáp án:** XML payload có thể giữ namespace nếu vocabulary không thay, nhưng security contract đã đổi. Cần version hóa/publish policy rõ, cân nhắc endpoint riêng để phân tách trust/cert rollout, đồng thời test partner capabilities. Không để một endpoint âm thầm bắt mọi client nâng cấp security cùng lúc.

### Tình huống J — Client v1 gửi nhầm tới endpoint v2

Client cấu hình URL v2 nhưng vẫn serialize payload v1. V2 endpoint cố fallback sang v1 mapper để “tăng tương thích”.

**Đáp án:** Fallback ngầm che lỗi cấu hình và làm version routing khó audit. Mặc định từ chối route/payload mismatch bằng lỗi contract phù hợp. Chỉ chấp nhận alias/compatibility adapter khi được thiết kế, công bố và test rõ, không dựa vào tự suy version.

### Tình huống K — Sunset v1 khi traffic bằng 0

Metrics không thấy request v1 trong 10 ngày. Một đối tác gửi batch cuối tháng và DR endpoint chỉ dùng khi failover.

**Đáp án:** Không xóa dựa khoảng im lặng ngắn. Xác nhận danh sách partner, lịch batch, DR/failover, người chịu trách nhiệm và thời hạn retention; thông báo sunset theo thỏa thuận và có sign-off.

### Tình huống L — Rollback server v1 nhưng database đã ghi v2

v2 cho phép trạng thái đơn mới mà code v1 không biết; rollback application về v1 khiến client cũ không parse trạng thái đó.

**Đáp án:** Rollback binary không đảo ngược contract/data. Trước rollout cần compatibility policy cho database/domain values, translation hoặc hạn chế feature v2 cho đến khi migration có thể rollback an toàn. Thiết kế reconciliation/compensation nếu đã có side effects.

## 15. Checklist review và phát hành contract version

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Phân loại change | Xác định patch/additive hay breaking theo XML, semantics và security, không chỉ theo diff code. |
| Namespace | QName của request/response/types/Fault thể hiện đúng contract major; không đổi prefix để giả version. |
| Endpoint | URL v1/v2, servlet mapping, proxy route, address và service discovery thống nhất. |
| WSDL artifact | Contract release có entry WSDL, checksum, changelog, owner và địa chỉ công bố. |
| XSD closure | Mọi import/include được pin; không có tham chiếu `latest` hoặc file bị overwrite âm thầm. |
| SOAP binding | SOAP 1.1/1.2, Content-Type, SOAPAction và binding đúng từng version. |
| WS-Addressing | Action/To/RelatesTo/ReplyTo và addressing version nhất quán khi contract yêu cầu. |
| WS-Policy/WS-Security | Token, signature, encryption, algorithm, certificate và timestamp policy đúng version. |
| JAXB | Packages/context paths tách rõ; generated code tái lập từ đúng XSD release. |
| Spring-WS mapping | `@PayloadRoot`, action mapping, endpoint URL và validation schema không route nhầm. |
| Application mapping | Version-specific DTO được map rõ về use case/domain; không mất semantics. |
| Fault contract | Fault code/detail/action và retryability được định nghĩa, test theo từng version. |
| Positive tests | Fixture v1/v2 hợp lệ pass; request/response round-trip đúng. |
| Negative tests | Wrong namespace/action/endpoint, schema invalid, security invalid bị từ chối trước side effects. |
| Regression | Client v1 tiếp tục hoạt động khi server v2 được deploy. |
| Partner certification | Client runtime, certificate, endpoint, WSDL checksum và test evidence được partner xác nhận. |
| Rollout | Canary theo partner/traffic, metrics theo version và rollback có điều kiện. |
| Deprecation | Sunset v1 có ngày, thông báo, owner, partner sign-off và xác minh batch/DR traffic. |
| Operations | Logs/metrics không lộ secrets; có alert cho fault rate, validation errors và version mismatch. |

### 15.1. Quyết định cuối trước khi phát hành

Trước khi merge/release, nhóm cần trả lời bằng văn bản:

1. Breaking change nào khiến contract cũ không thể tiếp tục?
2. Client có cần chạy v1/v2 song song không?
3. Namespace, endpoint và published WSDL/XSD đang nói cùng một version không?
4. Bộ import/include của contract đã cố định và có thể build offline không?
5. Client v1 có regression test trên server mới không?
6. Client v2 đã qua partner certification ở SOAP binding/security thực tế chưa?
7. Nếu lỗi xảy ra sau khi chuyển traffic, rollback kỹ thuật và dữ liệu có an toàn không?
8. Ai chịu trách nhiệm partner migration, deprecation và sunset?

Nếu không trả lời được một câu hỏi ảnh hưởng production, chưa nên coi version mới sẵn sàng chỉ vì build thành công.

## 16. Tài liệu tham khảo và nguyên tắc áp dụng

Các tài liệu chính thức sau giúp xác nhận cấu trúc contract và API:

- **W3C — [Web Services Description Language (WSDL) 1.1](https://www.w3.org/TR/wsdl.html)**: definitions, types, messages, portType, binding, service và port.
- **W3C — [XML Schema Part 1: Structures](https://www.w3.org/TR/xmlschema-1/)**: schema composition, element/type declarations và validation structure.
- **W3C — [XML Schema Part 2: Datatypes](https://www.w3.org/TR/xmlschema-2/)**: built-in types, facets và datatype semantics.
- **W3C — [Namespaces in XML](https://www.w3.org/TR/xml-names/)**: namespace URI, prefix và expanded names/QName.
- **W3C — [SOAP 1.1](https://www.w3.org/TR/SOAP/)** và **[SOAP 1.2 Part 1](https://www.w3.org/TR/soap12-part1/)**: Envelope, processing model, binding và Fault.
- **W3C — [WS-Addressing 1.0 Core](https://www.w3.org/TR/ws-addr-core/)** và **[SOAP Binding](https://www.w3.org/TR/ws-addr-soap/)**: addressing properties, Action và SOAP Header processing.
- **Spring Web Services — [Reference Documentation 4.1.4](https://docs.spring.io/spring-ws/docs/4.1.4/reference/html/)**: contract-first, endpoint mapping, WSDL publication, JAXB và testing.
- **Spring Web Services — [@PayloadRoot API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/server/endpoint/annotation/PayloadRoot.html)**: namespace/localPart mapping.
- **Spring Web Services — [DefaultWsdl11Definition API](https://docs.spring.io/spring-ws/docs/4.1.4/api/org/springframework/ws/wsdl/wsdl11/DefaultWsdl11Definition.html)**: WSDL 1.1 generation configuration.
- **Spring Web Services — [Jaxb2Marshaller API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/oxm/jaxb/Jaxb2Marshaller.html)**: JAXB context path/classes configuration and marshalling.

Tên API, artifact versions và package `javax`/`jakarta` có thể khác giữa các Spring-WS/JAXB generations. Hãy pin dependency và đọc Javadoc đúng version đang chạy. Các quy tắc major/minor trong bài là **governance convention do tổ chức chọn**, không phải một version negotiation protocol tự có trong SOAP.

### Ghi nhớ

- **Namespace version** xác định XML vocabulary/QName; **endpoint version** xác định đường routing/deployment; **published contract version** giữ WSDL/XSD/policy như một artifact có thể kiểm tra lại. Ba trục có thể kết hợp nhưng không thay thế nhau.
- Phân loại thay đổi theo **wire compatibility và semantics**, không chỉ theo việc XSD còn validate. Thêm enum, đổi đơn vị hoặc đổi Fault semantics vẫn có thể phá client.
- Khi thay đổi breaking, công bố namespace/WSDL/XSD major mới; cân nhắc endpoint riêng nếu cần isolation, routing hoặc security boundary. Giữ bộ contract cũ bất biến trong thời gian hỗ trợ.
- Spring-WS có thể map nhiều namespaces bằng `@PayloadRoot`; nên dùng adapter/JAXB DTO riêng cho từng version rồi map về application service khi semantics phù hợp.
- SOAPAction, WS-Addressing Action, SOAP binding, WS-Security policy và Fault model đều là phần của contract version. Không chỉ version hóa Body.
- Rollout an toàn cần **server hỗ trợ song song, partner certification, canary, metrics, rollback và sunset**. Không tắt v1 dựa trên traffic ngắn hạn hoặc kỳ vọng tất cả đối tác nâng cấp cùng lúc.
- **Compatibility tests phải hai chiều và có negative cases**: request/response/Fault, sai QName/action/endpoint, certificate/security, và regression v1 trên server mới.







