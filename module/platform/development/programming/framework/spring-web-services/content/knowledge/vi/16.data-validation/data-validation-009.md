# Thứ tự kiểm tra dữ liệu, xác minh bảo mật và thực hiện nghiệp vụ

Trong dịch vụ SOAP, một request có thể **đúng cấu trúc XSD nhưng không đáng tin**, **được ký hợp lệ nhưng sai nghiệp vụ**, hoặc **có dữ liệu hợp lệ nhưng người gửi không có quyền thực hiện thao tác**. Vì vậy, một endpoint không nên chỉ nhận đối tượng JAXB rồi lập tức ghi dữ liệu vào cơ sở dữ liệu. Cần thiết kế rõ thứ tự giữa **kiểm soát kết nối, phân tích XML an toàn, xác minh bảo mật, kiểm tra hợp đồng, xác thực/phân quyền và thực hiện nghiệp vụ**.

Bài học thuộc chương **Kiểm tra dữ liệu** của module **SPRING_WEB_SERVICES**. Module hướng đến phát triển dịch vụ SOAP theo hướng **contract-first** với XSD/WSDL, JAXB, endpoint và SOAP client; các phần xử lý SOAP Fault, interceptor, XML security, WS-Security, chứng chỉ và kiểm thử tương thích giúp dịch vụ tích hợp doanh nghiệp ổn định. Trọng tâm ở đây không phải bật càng nhiều validator càng tốt, mà là **đặt từng kiểm tra đúng ranh giới tin cậy, đúng thời điểm, với lỗi phản hồi thích hợp**.

## 1. Quy tắc nền tảng: không dùng dữ liệu chưa được kiểm tra để gây tác dụng phụ

Hãy xét operation `PlaceOrder`:

- SOAP client cung cấp `customerId`, `sku` và `quantity`.
- XSD xác định `quantity` phải là số nguyên trong một khoảng cho phép.
- WS-Security có thể yêu cầu chữ ký trên SOAP Body và timestamp hợp lệ.
- Danh tính người gọi cần được xác minh bằng token/chứng chỉ phù hợp.
- Người gọi chỉ được đặt hàng cho khách hàng mà họ được ủy quyền.
- Sản phẩm phải được kinh doanh, còn hàng và không vi phạm hạn mức.
- Nếu tất cả điều kiện thỏa mãn, nghiệp vụ mới ghi đơn hàng hoặc phát sự kiện.

Một XML hợp XSD như `quantity=10` **không chứng minh** caller có quyền mua hoặc kho còn 10 sản phẩm. Một SOAP Body được ký đúng về mật mã **không chứng minh** nội dung trong Body hợp XSD hoặc người ký có quyền đặt đơn. Các loại kiểm tra có trách nhiệm khác nhau.

| Câu hỏi cần trả lời | Lớp chịu trách nhiệm | Ví dụ bị từ chối |
| --- | --- | --- |
| Kết nối/request có được nhận và trong giới hạn không? | Gateway, HTTP transport, TLS/mTLS, quotas | Không có TLS bắt buộc, body quá lớn |
| XML có thể parse an toàn không? | SOAP message factory, XML parser | XML hỏng, DTD/entity ngoài bị cấm |
| Thông điệp có đáng tin theo chính sách bảo mật không? | WS-Security stack/interceptor, trust policy | Chữ ký sai, timestamp hết hạn |
| Body có hợp cấu trúc contract không? | XSD validation, SOAP binding | Thiếu field, sai namespace, enum ngoài tập |
| Java object có được ánh xạ đúng không? | JAXB/OXM, endpoint adapter | Không có root binding phù hợp |
| Caller có quyền đối với tài nguyên này không? | Identity/authorization + domain service | Đặt hàng cho khách hàng khác |
| Hành động có hợp quy tắc nghiệp vụ và trạng thái hiện tại không? | Application/domain service, transaction | Hết tồn kho, đơn bị khóa |
| Phản hồi có đúng hợp đồng và bảo mật không? | Response marshalling, XSD, SOAP Fault, security | XML response thiếu field, chữ ký response sai |

**Nguyên tắc an toàn:** một bước kiểm tra không thay thế bước khác; dữ liệu chỉ được chuyển tới tầng có tác dụng phụ khi **các điều kiện tiên quyết** đã được đáp ứng. Không đưa thông điệp SOAP chưa qua xác minh vào nghiệp vụ chỉ để “kiểm tra dữ liệu nhanh hơn”.

## 2. Thứ tự logic và thứ tự gọi interceptor thực tế không hoàn toàn giống nhau

Một luồng xử lý **được khuyến nghị về mặt trách nhiệm** là:

~~~mermaid
flowchart TD
    A["SOAP request từ client"] --> T["1. Transport controls<br/>TLS/mTLS, allowlist, quotas"]
    T --> P["2. XML parse an toàn<br/>có giới hạn tài nguyên"]
    P --> S["3. Xử lý WS-Security<br/>giải mã / xác minh chữ ký, token, timestamp"]
    S --> V["4. Kiểm tra XSD<br/>đối với nội dung đã được chấp nhận"]
    V --> J["5. JAXB/OXM<br/>ánh xạ XML thành Java"]
    J --> Z["6. Authorization & kiểm tra nghiệp vụ"]
    Z --> X["7. Transaction / side effects<br/>idempotency, ghi dữ liệu"]
    X --> R["8. Marshal response + validate"]
    R --> O["9. Áp dụng bảo mật outbound<br/>ký/mã hóa theo policy"]
    O --> H["10. Transport gửi SOAP response"]
    P -.-> E["SOAP Fault / lỗi transport<br/>không lộ bí mật"]
    S -.-> E
    V -.-> E
    Z -.-> E
~~~

Sơ đồ là **thứ tự phụ thuộc về an toàn**, không phải thứ tự bất biến của các callback trong mọi bản Spring-WS. Có những điểm phải phân biệt:

1. **XML parsing tối thiểu xảy ra trước kiểm tra WS-Security:** engine phải đọc Envelope/Header để nhận biết chữ ký hoặc dữ liệu mã hóa. Vì thế parser an toàn và giới hạn kích thước phải được áp dụng **trước cả xác minh chữ ký**.
2. **Giải mã và xác minh chữ ký phụ thuộc policy:** có hệ thống ký trước khi mã hóa, có hệ thống mã hóa trước khi ký; các bước decrypt/verify cần tuân thủ thứ tự và phạm vi bảo vệ đã thỏa thuận, không áp một trình tự chung cho mọi SOAP message.
3. **XSD validation phải kiểm tra đúng phiên bản XML mà nghiệp vụ tiêu thụ.** Nếu Body được mã hóa, không thể validate nội dung nghiệp vụ cho đến khi xử lý giải mã thích hợp. Nếu có chữ ký, tránh sửa XML đã ký trước khi xác minh.
4. **Authentication và authorization là hai quyết định khác nhau:** xác minh caller có danh tính hợp lệ không đồng nghĩa caller được thao tác với `customerId` trong Body. Authorization dựa trên dữ liệu nghiệp vụ thường cần đọc request đã parse/validate.
5. **Endpoint mapping có thể diễn ra trước các `EndpointInterceptor`:** Spring-WS cần tìm endpoint/chuỗi interceptor trước khi chạy chúng. Do đó, một interceptor gắn với endpoint không bảo vệ được mọi request chưa tìm thấy handler.
6. **Phản hồi có thứ tự riêng:** dữ liệu nghiệp vụ cần được marshal và kiểm tra theo contract trước các bước ký/mã hóa phù hợp. Nếu validation response hoặc interceptor khác thay đổi message sau khi ký, chữ ký có thể hỏng.

### Một thứ tự tưởng hợp lý nhưng không an toàn

~~~text
Nhận SOAP → Unmarshal → Ghi đơn hàng → Kiểm tra chữ ký → Trả response
~~~

Trình tự này sai vì đã gây **side effect** trước khi biết request có đáng tin. Kể cả cuối cùng trả SOAP Fault “chữ ký không hợp lệ”, đơn hàng vẫn có thể đã được ghi hoặc sự kiện đã được phát.

Một trình tự khác cũng nguy hiểm:

~~~text
Nhận SOAP → XSD validation → Log toàn bộ Body → Kiểm tra chữ ký
~~~

Nó có thể phơi bày chi tiết lỗi hợp đồng hoặc dữ liệu nhạy cảm của request chưa được xác minh. Với request đã mã hóa, XSD validation sớm có thể không nhìn thấy payload cần kiểm tra. Chỉ nên thực hiện **kiểm tra giao thức/giới hạn tối thiểu** trước security khi thực sự cần để parse message.

## 3. Ví dụ hợp đồng XSD cho PlaceOrder

Ví dụ `orders.xsd` trong một dịch vụ contract-first:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:ord="urn:example:orders:v1"
           targetNamespace="urn:example:orders:v1"
           elementFormDefault="qualified">

    <xs:simpleType name="SkuType">
        <xs:restriction base="xs:string">
            <xs:pattern value="[A-Z0-9-]{3,30}"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="QuantityType">
        <xs:restriction base="xs:int">
            <xs:minInclusive value="1"/>
            <xs:maxInclusive value="1000"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:simpleType name="OrderStatusType">
        <xs:restriction base="xs:string">
            <xs:enumeration value="ACCEPTED"/>
            <xs:enumeration value="REJECTED"/>
        </xs:restriction>
    </xs:simpleType>

    <xs:element name="PlaceOrderRequest">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="customerId" type="xs:string"/>
                <xs:element name="clientRequestId" type="xs:string"/>
                <xs:element name="sku" type="ord:SkuType"/>
                <xs:element name="quantity" type="ord:QuantityType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>

    <xs:element name="PlaceOrderResponse">
        <xs:complexType>
            <xs:sequence>
                <xs:element name="orderId" type="xs:string"/>
                <xs:element name="status" type="ord:OrderStatusType"/>
            </xs:sequence>
        </xs:complexType>
    </xs:element>
</xs:schema>
~~~

WSDL dùng các **global elements** `ord:PlaceOrderRequest` và `ord:PlaceOrderResponse` cho message input/output, đồng thời định nghĩa SOAP binding, endpoint address và chính sách header/security khi cần. Mã endpoint sẽ định tuyến theo **QName root** trong SOAP Body, ví dụ `{urn:example:orders:v1}PlaceOrderRequest`.

SOAP Body hợp cấu trúc:

~~~xml
<ord:PlaceOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:customerId>CUST-001</ord:customerId>
    <ord:clientRequestId>REQ-2026-001</ord:clientRequestId>
    <ord:sku>SKU-42</ord:sku>
    <ord:quantity>3</ord:quantity>
</ord:PlaceOrderRequest>
~~~

XML này có thể vượt qua kiểm tra cấu trúc, nhưng **chưa đủ để thực hiện nghiệp vụ**. Cần biết SOAP message có được xác minh đúng policy hay không, danh tính nào được chứng thực, caller có quyền với `CUST-001` không, `SKU-42` còn hàng không và `REQ-2026-001` có bị gửi lặp không.

### Bốn request có kết quả kiểm tra khác nhau

| Trường hợp | Kết luận chính | Tầng phát hiện |
| --- | --- | --- |
| `quantity=0` | Không hợp XSD vì `minInclusive=1` | XML Schema validation |
| `quantity=3` nhưng chữ ký Body sai | Không đáng tin dù dữ liệu hợp schema | WS-Security |
| `quantity=3`, chữ ký đúng nhưng caller không có quyền với `CUST-001` | Không được thực hiện nghiệp vụ | Authorization |
| `quantity=3`, caller có quyền nhưng kho chỉ còn 2 | Hợp lệ về contract/security, bị từ chối vì trạng thái nghiệp vụ | Domain/transaction |

Một API ổn định phải phân loại được bốn tình huống trên, trả lỗi theo hợp đồng và **không ghi đơn hàng** khi một điều kiện tiên quyết thất bại.

## 4. Bảo vệ trước khi SOAP message thành đối tượng có thể xử lý

### 4.1. Transport: TLS/mTLS, gateway và giới hạn tài nguyên

Trước khi Spring-WS nhận Body:

- **TLS** bảo vệ kết nối giữa client và endpoint/proxy; kiểm tra hostname/chứng chỉ theo vai trò từng phía.
- **mTLS**, khi được yêu cầu, xác thực chứng chỉ client ở tầng kết nối. Nếu TLS kết thúc ở proxy, backend chỉ nên tin identity đã được proxy tin cậy chuyển tiếp bằng cơ chế được bảo vệ và kiểm soát.
- **Gateway** cần giới hạn kích thước request, tốc độ, số kết nối, timeout và các loại media type được phép.
- **Ingress/servlet mapping** cần đưa POST SOAP đúng `MessageDispatcherServlet`, không chỉ phục vụ GET WSDL.
- **Header do client gửi** như `X-Forwarded-*` hoặc `X-Client-Cert` không tự là bằng chứng bảo mật; chỉ tin header đã được một proxy được kiểm soát thiết lập và truyền qua kênh phù hợp.

Những lỗi xảy ra tại TLS/gateway có thể **không tạo SOAP Fault** vì request còn chưa trở thành SOAP message trong Spring-WS. Đừng cố yêu cầu endpoint interceptor xử lý một TLS handshake đã thất bại.

### 4.2. XML parsing: bảo vệ ngay từ lần đọc đầu tiên

Một SOAP message có thể khai báo DTD, external entity hoặc XML cực lớn nhằm tiêu tốn tài nguyên. Parser/message factory cần được làm cứng:

- Chặn hoặc kiểm soát DTD/external entities/XXE; không truy cập tùy tiện file cục bộ, URL hoặc DTD ngoài.
- Giới hạn tổng byte, độ sâu XML, số lượng node và chi phí parse.
- Không chuyển payload thẳng vào DOM nếu kích thước chưa có giới hạn; nếu dùng streaming vẫn cần quota/timeout.
- Nếu cần resolve XSD include/import, ưu tiên schema/catalog **đã đóng gói và tin cậy** thay vì cho request điều khiển `schemaLocation` từ Internet.
- Không log toàn bộ XML thô, đặc biệt phần `wsse:Security`, password/token, PII hay dữ liệu chưa được xác minh.

**Lý do:** kiểm tra chữ ký và schema đều cần parse XML. Một hệ thống chỉ thêm `Wss4jSecurityInterceptor` nhưng để parser mặc định chấp nhận external entities vẫn còn lỗ hổng ở bước sớm hơn.

## 5. Xác minh WS-Security: “có chữ ký” khác với “tin được thông điệp”

WS-Security có thể sử dụng UsernameToken, timestamp, chữ ký XML, X.509 và mã hóa SOAP Body/Header. Một ví dụ requirement trong hợp đồng doanh nghiệp:

> Client gửi SOAP Body được ký; thời gian gửi nằm trong cửa sổ được phép; chữ ký được xác minh bằng certificate thuộc đối tác được tin cậy; nếu sử dụng mã hóa, recipient giải mã trước khi xử lý dữ liệu nghiệp vụ.

Các kiểm tra cần có:

| Kiểm tra | Câu hỏi | Rủi ro nếu thiếu |
| --- | --- | --- |
| Chữ ký mật mã | Signature có hợp lệ với các octet/canonicalization được chỉ định? | Body bị sửa mà không bị phát hiện |
| **Phạm vi ký** | **Đúng Body và Header bắt buộc đang được sử dụng** có được bảo vệ? | XML Signature Wrapping / nhầm node đã ký |
| Trust/identity | Chứng chỉ/token thuộc đối tác được chấp nhận? | Bất kỳ khóa hợp lệ nào cũng có thể ký |
| Timestamp | `Created`/`Expires` hợp lệ theo clock-skew policy? | Replay message cũ |
| Replay detection | Message ID/nonce đã xử lý trước đó chưa, trong phạm vi và thời hạn phù hợp? | Gửi lại một lệnh tạo đơn hợp lệ |
| Cấu hình thuật toán | Thuật toán ký, digest, mã hóa và key length có đúng policy? | Thuật toán yếu hoặc downgrade |
| Targeting | SOAP Header `mustUnderstand`/role/actor có được xử lý đúng? | Bỏ qua security header bắt buộc |

**Không đủ** khi mã endpoint chỉ thấy `wsse:Security` rồi gắn `authenticated=true`. Phải để engine WS-Security xác minh chính sách; mới sau đó các thành phần application được sử dụng một **principal/identity đã tin cậy**.

### Chữ ký đúng vẫn không phải quyền truy cập

Một đối tác A có thể ký request hợp lệ về mật mã nhưng không được đặt hàng cho khách hàng thuộc đối tác B. Việc xác minh signature chỉ xác lập **tính toàn vẹn và nguồn khóa/chủ thể theo chính sách**; bước authorization vẫn phải kiểm tra danh tính đó với `customerId` và tài nguyên cụ thể.

### Giải mã, verify và validate: thứ tự phụ thuộc kiểu bảo vệ

Đừng khái quát thành “luôn decrypt trước verify” hoặc “luôn verify trước decrypt”. Nếu message được **ký rồi mã hóa**, engine có thể phải giải mã phần dữ liệu cần thiết mới xác minh chữ ký nội dung. Nếu **mã hóa rồi ký**, signature có thể được verify trên ciphertext trước khi giải mã. Thực hiện theo **WS-SecurityPolicy và cấu hình WSS4J** của đối tác, bảo đảm application chỉ nhận **Body đã giải mã, được xác minh đầy đủ và đúng scope**.

Không cho interceptor tự biến đổi SOAP Body trước/sau việc xác minh signature một cách tùy ý; canonicalization và tham chiếu chữ ký có thể khiến chữ ký thất bại hoặc, nguy hiểm hơn, kiểm tra nhầm node.

## 6. Kiểm tra XSD nên đặt trước phần nghiệp vụ, nhưng sau ranh giới tin cậy cần thiết

XSD giải quyết những câu hỏi **cấu trúc và kiểu dữ liệu**, ví dụ:

- Root QName đúng namespace và tên element chưa?
- Phần tử bắt buộc có mặt đúng `minOccurs`/`maxOccurs`?
- Thứ tự `xs:sequence` đúng chưa?
- `quantity` có phải số nguyên từ 1 đến 1000?
- `sku` có khớp `xs:pattern`?
- `xsi:nil`, default/fixed và import/include có tuân schema?

XSD **không thể tự biết** caller có quyền với khách hàng nào hoặc tồn kho hiện tại còn bao nhiêu. Nó cũng không giải quyết đầy đủ tất cả giới hạn chống lạm dụng (ví dụ `clientRequestId` ở XSD mẫu chỉ khai báo `xs:string`, chưa có hạn chế độ dài); service vẫn cần kiểm tra theo chính sách.

### Schema validation và JAXB unmarshalling là hai trách nhiệm khác nhau

JAXB chuyển XML thành Java object, nhưng **không mặc định kiểm tra mọi facet của XSD**. Một generated Java setter có thể chấp nhận `quantity=0` dù schema không cho. Nếu không bật validation, unmarshaller cũng có thể đọc một số XML không hợp đồng thành object không hoàn chỉnh.

| Công cụ | Làm gì? | Không nên kỳ vọng |
| --- | --- | --- |
| `PayloadValidatingInterceptor` của Spring-WS | Validate request/response payload theo XSD tại pipeline đã cấu hình | Tự xác thực caller hoặc kiểm tra quyền nghiệp vụ |
| `Jaxb2Marshaller` có schema | Marshal/unmarshal và có thể áp dụng XSD validation | Tự bảo đảm WS-Security đã xác minh |
| `@RequestPayload` / JAXB adapter | Ánh xạ payload XML sang tham số Java | Tự hiểu mọi facet XSD thành validation ở setter |
| Service validator | Kiểm tra điều kiện nghiệp vụ, authorization | Thay thế parser XML an toàn hoặc signature verification |

**Tùy chính sách vận hành**, nên validate XML sau khi security engine đã cung cấp nội dung có thể tin ở mức cần thiết và trước khi thực thi nghiệp vụ. Một số kiểm tra cấu trúc tối thiểu có thể cần thiết sớm để xử lý message hoặc chống lạm dụng; chúng không thay thế xác thực.

### XSD chưa chắc áp dụng lên toàn bộ SOAP Header

`PayloadValidatingInterceptor` chủ yếu được dùng để validate **payload** (SOAP Body) theo schema. Không suy ra chỉ cần bật nó là mọi SOAP Header tùy chỉnh đã được validate. Nếu dùng header `CorrelationId`, `TenantContext` hoặc một header nghiệp vụ khác, cần thiết kế và kiểm tra riêng; còn `wsse:Security` phải xử lý bằng WS-Security stack.

## 7. Thực thi nghiệp vụ: chỉ sau xác thực, authorization và validation

Ở bước này, endpoint đã có một request Java được ánh xạ phù hợp (hoặc Source XML đã qua xử lý/kiểm tra), cùng danh tính được xác minh từ cơ chế bảo mật.

Một nguyên tắc quan trọng: **đừng lấy danh tính caller từ trường do client tự cung cấp trong SOAP Body**. `customerId` là đối tượng nghiệp vụ mà caller muốn thao tác; danh tính và quyền của caller phải đến từ kênh xác thực đáng tin.

Ví dụ một ứng dụng có adapter tự viết `VerifiedCallerProvider`, chỉ trả `VerifiedCaller` sau khi transport/WS-Security stack đã xác minh thành công:

~~~java
@Endpoint
public class PlaceOrderEndpoint {
    private static final String NS = "urn:example:orders:v1";
    private final OrderApplicationService orders;
    private final VerifiedCallerProvider verifiedCallerProvider;

    public PlaceOrderEndpoint(
            OrderApplicationService orders,
            VerifiedCallerProvider verifiedCallerProvider) {
        this.orders = orders;
        this.verifiedCallerProvider = verifiedCallerProvider;
    }

    @PayloadRoot(namespace = NS, localPart = "PlaceOrderRequest")
    @ResponsePayload
    public PlaceOrderResponse place(
            @RequestPayload PlaceOrderRequest request) {
        // VerifiedCallerProvider là abstraction TỰ THIẾT KẾ,
        // không phải API mặc định của Spring-WS.
        VerifiedCaller caller = verifiedCallerProvider.requireVerified();

        // Service kiểm tra caller có quyền với customerId,
        // ràng buộc nghiệp vụ, idempotency và transaction.
        PlaceOrderResult result = orders.place(
                caller, request.getCustomerId(),
                request.getClientRequestId(),
                request.getSku(), request.getQuantity());

        PlaceOrderResponse response = new PlaceOrderResponse();
        response.setOrderId(result.orderId());
        response.setStatus(OrderStatusType.ACCEPTED);
        return response;
    }
}
~~~

Đây là **đoạn endpoint minh họa**, chưa bao gồm imports, generated JAXB classes, application types hoặc wiring security; nó không chạy độc lập. `VerifiedCallerProvider` chỉ là ranh giới ứng dụng để lấy principal đã xác minh từ security context/cơ chế identity thực tế. Nếu chưa có principal đáng tin, phương thức `requireVerified()` phải **từ chối** thay vì trả anonymous caller.

### Authorization nên kiểm tra cả dữ liệu gốc và trạng thái mới

Service nghiệp vụ cần xử lý trong thứ tự có kiểm soát:

1. Lấy danh tính và tenant đã được xác minh, không tin `customerId` như danh tính.
2. Kiểm tra quyền gọi operation `PlaceOrder` và quyền tác động lên khách hàng `CUST-001`.
3. Kiểm tra `sku`, `quantity` theo các quy tắc nghiệp vụ bổ sung (không chỉ XSD).
4. Kiểm tra giới hạn đơn hàng, tồn kho và các trạng thái có thể thay đổi theo thời gian.
5. Bảo vệ thao tác khỏi race condition bằng **transaction/concurrency control** phù hợp.
6. Áp dụng idempotency nếu client được phép retry, rồi ghi đơn hàng và tạo sự kiện một cách nhất quán.

### Transaction không chữa được validation thiếu

Transaction có thể rollback những thao tác database phù hợp, nhưng **không tự undo** email, HTTP call ra ngoài hay sự kiện đã phát nếu thiếu thiết kế transactional outbox/saga. Tránh gọi hệ thống ngoài trước khi chắc chắn authorization và validation đã đạt; với side effects ngoài transaction, cân nhắc outbox và cơ chế xử lý lại an toàn.

## 8. Idempotency và replay: hai vấn đề khác nhau

SOAP client doanh nghiệp có thể retry khi timeout. Một request hợp lệ, được ký và có `clientRequestId` giống trước **có thể là retry chính đáng**, nhưng cũng có thể là replay không mong muốn.

| Khái niệm | Nó ngăn điều gì? | Cần xem thêm |
| --- | --- | --- |
| **WS-Security replay protection** | Ngăn dùng lại token/message/timestamp ngoài chính sách cho phép | Nonce, timestamp, message ID, security cache, clock skew |
| **Business idempotency** | Ngăn cùng một ý định nghiệp vụ được thực hiện hai lần khi retry | Key gắn caller/tenant, fingerprint request, unique constraint và transaction |
| **Authorization** | Ngăn caller tác động vào tài nguyên không thuộc quyền | Principal được xác minh, ownership, scope, policy |

Ví dụ, với `clientRequestId=REQ-2026-001`:

- Hai request **cùng caller, cùng nội dung và cùng idempotency key** có thể được trả cùng kết quả sau khi đã xử lý một lần, nếu hợp đồng quy định như vậy.
- Hai request **khác nội dung nhưng cùng key** cần bị từ chối hoặc giải quyết bằng policy rõ ràng; không lặng lẽ trả kết quả sai.
- Hai đối tác khác nhau dùng cùng chuỗi key không nên va chạm nếu khóa được scope theo danh tính/tenant.
- Một token WS-Security hết hạn hoặc signature không hợp lệ **không được vượt qua security chỉ vì business idempotency cache đã có kết quả trước đó**.

**Phải kiểm tra bảo mật cho từng request mới.** Idempotency chỉ áp dụng ở phía nghiệp vụ sau khi danh tính và thông điệp đã được xác minh theo policy. Nếu chính sách chống replay không cho dùng lại **cùng một SOAP Envelope đã ký**, client retry phải tạo metadata WS-Security mới hợp lệ (ví dụ timestamp/nonce/message ID theo policy) và ký lại message, nhưng **giữ nguyên business idempotency key** để server không tạo đơn thứ hai. Không tắt replay protection để “sửa” lỗi retry.

## 9. Spring-WS: interceptor nằm ở đâu trong pipeline?

Với Spring-WS, `MessageDispatcherServlet` tiếp nhận message và chuyển cho `MessageDispatcher`. Endpoint mapping chọn endpoint; interceptor chain có thể thực hiện security/schema validation; adapter gắn JAXB vào method `@RequestPayload` và marshal `@ResponsePayload`.

~~~mermaid
flowchart LR
    A["MessageDispatcherServlet"] --> B["MessageDispatcher"]
    B --> C["EndpointMapping<br/>chọn handler"]
    C --> D["EndpointInterceptor chain<br/>security / XSD"]
    D --> E["EndpointAdapter<br/>JAXB"]
    E --> F["@Endpoint + service"]
    F --> G["response / Fault"]
    G --> H["response interceptors<br/>validation / security"]
~~~

### Lưu ý thứ tự thật sự của các callback

Đối với `EndpointInterceptor`, `handleRequest` tham gia vào phía inbound, còn `handleResponse`, `handleFault` và `afterCompletion` xử lý các nhánh sau tương ứng. Danh sách interceptor và cách dispatcher gọi các callback **không nên suy ra chỉ từ thứ tự các bean được khai báo**; phải kiểm tra behavior của phiên bản Spring-WS, nhất là khi security interceptor cần verify/decrypt inbound nhưng sign/encrypt outbound.

**Điểm đặc biệt quan trọng:** một interceptor chạy sau **EndpointMapping** không tự bảo vệ những request **không ánh xạ được endpoint**. Nếu kiến trúc yêu cầu từ chối mọi request thiếu TLS/mTLS hoặc quá lớn, enforcement cần ở gateway/container/message parser, trước bước mapping.

### Ví dụ cấu hình thứ tự kiểm tra phía request

Ví dụ dưới đây giả định ứng dụng sử dụng phiên bản Spring-WS có `WsConfigurer` và đã cấu hình sẵn bean `Wss4jSecurityInterceptor` với **WS-Security policy, truststore, algorithms, callback handlers** thích hợp:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.ws.config.annotation.EnableWs;
import org.springframework.ws.config.annotation.WsConfigurer;
import org.springframework.ws.server.EndpointInterceptor;
import org.springframework.ws.soap.security.wss4j2.Wss4jSecurityInterceptor;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;

@EnableWs
@Configuration
public class SoapPipelineConfig implements WsConfigurer {
    private final Wss4jSecurityInterceptor security;
    private final PayloadValidatingInterceptor validation;

    public SoapPipelineConfig(
            Wss4jSecurityInterceptor security,
            PayloadValidatingInterceptor validation) {
        this.security = security;
        this.validation = validation;
    }

    @Override
    public void addInterceptors(List<EndpointInterceptor> interceptors) {
        // Ý định: incoming security verification/decryption
        // trước request payload validation.
        interceptors.add(security);
        interceptors.add(validation);
    }
}
~~~

**Không sao chép đoạn này rồi xem như đã có security.** Một bean `Wss4jSecurityInterceptor` chưa cấu hình cách xác minh chữ ký, truststore, timestamp, replay và policy có thể không bảo vệ được dịch vụ. Ví dụ chỉ minh họa **ý định thứ tự xử lý**, cần xác minh qua integration test trên đúng bản Spring-WS/WSS4J và SOAP policy.

Nếu ứng dụng dùng framework/config khác, có thể có interceptor registration riêng. Ngoài ra, **thứ tự outbound** và việc validator chạy trên message trước/sau securement phải được kiểm tra bằng SOAP response thực tế; không suy ra validation outbound đúng chỉ vì inbound order đã đặt đúng.

### Ví dụ cấu hình XSD validator

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.ws.soap.server.endpoint.interceptor.PayloadValidatingInterceptor;
import org.springframework.xml.xsd.SimpleXsdSchema;
import org.springframework.xml.xsd.XsdSchema;

@Configuration
public class OrdersSchemaValidationConfig {

    @Bean
    public XsdSchema ordersSchema() {
        return new SimpleXsdSchema(
                new ClassPathResource("xsd/orders.xsd"));
    }

    @Bean
    public PayloadValidatingInterceptor ordersPayloadValidator(
            XsdSchema ordersSchema) {
        PayloadValidatingInterceptor validator =
                new PayloadValidatingInterceptor();
        validator.setXsdSchema(ordersSchema);
        validator.setValidateRequest(true);
        validator.setValidateResponse(true);
        return validator;
    }
}
~~~

Đây là **cấu hình minh họa**, giả định XSD ví dụ được đóng gói trong classpath và không có import ngoài chưa được giải quyết. Trong sản xuất, cần thiết kế fault/error response khi validation thất bại, kiểm tra chi phí validate response, và bảo đảm schema graph đủ tài nguyên tin cậy.

### Bảo mật WSS4J cần thiết kế riêng

Một chính sách yêu cầu chữ ký + timestamp phải xác định ít nhất:

- Các validation actions thực sự được bật và cách xử lý thiếu action.
- Crypto/trust material tin cậy, certificate chain, issuer/subject/identity mapping.
- Những SOAP parts/Header nào **bắt buộc được ký** và các thuật toán được chấp nhận.
- Timestamp/replay cache, độ lệch đồng hồ cho phép.
- Cách tạo chữ ký/mã hóa response nếu client yêu cầu.
- Cách trả security Fault mà không phơi bày chi tiết bí mật.

Chỉ thêm `Wss4jSecurityInterceptor` vào danh sách **không tự tạo** các yêu cầu này. Việc bảo vệ đúng còn phải xét trường hợp client gửi chữ ký hợp lệ nhưng không ký **Body đang được endpoint tiêu thụ**.

## 10. Đặt authentication và authorization vào vị trí thích hợp

### Authentication

Authentication trả lời **“người gọi là ai và bằng chứng danh tính có hợp lệ không?”**. Ví dụ:

- TLS/mTLS xác minh identity ở tầng kết nối (nếu kiến trúc dùng).
- WS-Security xác minh token/chứng chỉ/chữ ký theo SOAP policy.
- Một identity adapter của ứng dụng chuyển kết quả đã xác minh thành principal đáng tin cậy.

Ứng dụng không nên đơn giản đọc `<hdr:CustomerId>CUST-001</hdr:CustomerId>` rồi xem đây là danh tính đã xác thực.

### Authorization

Authorization trả lời **“người gọi được làm thao tác này với tài nguyên này không?”**. Nó cần principal tin cậy và dữ liệu nghiệp vụ đã được hiểu đúng. Ví dụ:

~~~text
principal = partner-A (đã xác minh)
operation = PlaceOrder
request.customerId = CUST-001
decision = partner-A có scope 'orders:create'
           và được ủy quyền với CUST-001?
~~~

Đừng quyết định chỉ dựa vào `request.customerId` tự khai báo. Nếu service hỗ trợ nhiều tenant, phải scope tất cả truy vấn/ghi dữ liệu theo tenant được xác thực, và tránh lỗi IDOR: request chứa ID của tài nguyên khác nhưng vẫn lọt qua vì ID đúng định dạng.

### Authorization có thể được kiểm tra nhiều lần

Một bước **coarse-grained** có thể diễn ra sớm, sau authentication, để từ chối caller không có quyền gọi operation nào. Sau khi JAXB và XSD validation đã xác định dữ liệu có thể dùng, một bước **resource-level** kiểm tra quyền trên `customerId` và đơn hàng cụ thể. Với dữ liệu thay đổi nhanh, thực thi nghiệp vụ nên kiểm tra các điều kiện có thể bị race ở cùng transaction/atomic boundary.

Phân quyền không nhất thiết phải đợi kiểm tra đầy đủ tất cả business constraints. Điểm bắt buộc là **không sử dụng dữ liệu chưa được xác minh làm nguồn danh tính**, không gây side effect trước khi đủ quyền và không lộ thông tin nhạy cảm cho caller bị từ chối.

## 11. Sai thứ tự tạo những rủi ro nào?

| Cấu hình sai | Kết quả có thể xảy ra | Cách sửa |
| --- | --- | --- |
| Ghi database rồi mới verify signature | Request giả mạo có tác dụng phụ | Verify theo policy trước side effect |
| Unmarshal XML bằng parser không giới hạn trước security | XXE, tài nguyên bị tiêu thụ trước xác thực | Harden parser/message factory và quotas ngay từ đầu |
| Validate Body đã mã hóa bằng XSD nội dung nghiệp vụ | Không thấy payload đã giải mã, báo lỗi sai | Đưa validation sau xử lý bảo mật cần thiết |
| Normalize/transform Body đã ký trước verify | Chữ ký sai hoặc kiểm tra sai node | Không sửa XML đã ký trái policy |
| Chỉ kiểm tra “có Signature” | Signed data không phải Body xử lý / signer không đáng tin | Verify signature, coverage, trust và identity |
| Kiểm schema, bỏ authorization | Dữ liệu hợp XSD nhưng thao tác vào tenant khác | Quyền dựa trên principal và resource |
| Tin `clientRequestId` như proof chống replay | Attacker có thể gửi lại/làm giả key | Replay protection ở security + idempotency ở business |
| Xem JAXB object hợp lệ là đã qua XSD | Invalid XML vẫn được unmarshall | Bật schema validation và test âm |
| Bật response security rồi sửa Body bằng interceptor | Client verify response thất bại | Validate/hoàn thiện response trước bước ký tương ứng |
| Exception ở security bị chuyển thành thông báo quá chi tiết | Lộ truststore/certificate/internal state | SOAP Fault có kiểm soát, log nội bộ đã lọc |
| Chỉ bật security ở endpoint interceptor | Request no endpoint hoặc parse error chưa được bảo vệ ở mọi tầng | Gateway/parser safeguards; review dispatcher behavior |

Một chiến lược tốt không phải “kiểm mọi thứ thật sớm” mà là **kiểm đúng thứ tự phụ thuộc và tách điểm ra quyết định**.

## 12. Xử lý SOAP Fault theo loại lỗi và thời điểm thất bại

SOAP Fault là lỗi trong thông điệp SOAP; không phải mọi lỗi HTTP đều có SOAP Envelope. Khi lỗi xảy ra **trước khi** message được parse hoặc kết nối TLS được thiết lập, gateway có thể chỉ trả HTTP error.

| Nhóm lỗi | Phân loại thông thường | Gợi ý phản hồi |
| --- | --- | --- |
| XML sai cú pháp hoặc SOAP Envelope sai | Lỗi giao thức/request | SOAP Fault phía request nếu đã có SOAP processing context; nếu không, transport error |
| Không hợp XSD | Lỗi hợp đồng dữ liệu | Client/Sender Fault theo SOAP version và chính sách |
| Signature/token/timestamp không hợp lệ | Lỗi bảo mật | Security Fault chung, không lộ key/trust details |
| Không được quyền đối với customerId | Lỗi authorization | Fault đã chuẩn hóa; tránh lộ tài nguyên tồn tại hay không |
| Hết tồn kho hoặc vi phạm hạn mức | Lỗi nghiệp vụ | Business Fault detail theo WSDL/XSD nếu đã công bố |
| Database lỗi hoặc hệ thống không sẵn sàng | Lỗi server/hạ tầng | Server/Receiver Fault; retry policy khi thích hợp |

SOAP 1.1 thường dùng fault code `Client`/`Server`; SOAP 1.2 sử dụng `Sender`/`Receiver` cùng cấu trúc Fault khác. Không lấy một XML SOAP 1.1 Fault rồi trả cho client SOAP 1.2.

Một SOAP 1.1 Fault minh họa:

~~~xml
<soapenv:Envelope
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
    <soapenv:Body>
        <soapenv:Fault>
            <faultcode>soapenv:Client</faultcode>
            <faultstring>Yêu cầu không hợp lệ</faultstring>
        </soapenv:Fault>
    </soapenv:Body>
</soapenv:Envelope>
~~~

Đoạn trên chỉ minh họa cấu trúc; **không khẳng định** Spring-WS sẽ tự trả Fault này cho mọi lỗi schema hoặc security. Cần cấu hình validation interceptor, security fault mapping, exception resolvers và chính sách riêng của dịch vụ.

### Vì sao lỗi bảo mật nên hạn chế chi tiết?

Đối với chữ ký sai, token thiếu, trust chain không hợp lệ hoặc tài khoản không tồn tại, phản hồi quá chi tiết có thể biến endpoint thành **oracle** giúp đoán cấu hình. Nội bộ có thể ghi loại lỗi, certificate thumbprint đã lọc, correlation ID và thông số chẩn đoán phù hợp, nhưng không tiết lộ private key, password, raw token, stack trace hay chuỗi quyết định authorization.

Ngược lại, sau khi caller đã được xác thực và được phép biết dữ liệu, một business Fault chuẩn có thể cung cấp mã lỗi và thông tin có ích để client xử lý, theo hợp đồng.

## 13. Outbound: validate, marshal, ký và gửi response

Thứ tự phía response cần được thiết kế, không chỉ phía request.

~~~mermaid
flowchart LR
    A["Domain result"] --> B["JAXB response object"]
    B --> C["Marshal SOAP Body"]
    C --> D["Validate XSD response<br/>nếu policy yêu cầu"]
    D --> E["Bổ sung SOAP Header hợp đồng"]
    E --> F["WS-Security outbound<br/>ký/mã hóa"]
    F --> G["HTTP/TLS transport"]
~~~

Thứ tự này là **mô hình kết quả mong muốn**. Thứ tự thực tế của `handleResponse`/`handleFault` và securement theo Spring-WS/WSS4J cần được kiểm tra. Nếu một interceptor schema response validation đọc dữ liệu sau khi mã hóa hoặc sửa message sau khi ký, nó có thể làm hỏng security envelope. Thiết kế một pipeline bảo đảm **schema validation nhìn đúng XML nghiệp vụ** và **signature bảo vệ chính những node cuối cùng được gửi**.

### Kiểm tra outbound khác kiểm tra inbound

- **Request XSD validation** bảo vệ hệ thống trước payload không hợp contract.
- **Response XSD validation** giúp phát hiện lỗi do server sinh XML sai: thiếu `orderId`, sai namespace, enum response không thuộc XSD.
- **Outbound security** bảo vệ response khi hợp đồng yêu cầu ký/mã hóa; nó không chứng minh response hợp schema.
- **Fault response** có định dạng và chính sách bảo mật riêng; không được giả định mọi Fault sẽ đi qua cùng luồng validation như response nghiệp vụ.

Trước khi gửi response chứa dữ liệu nhạy cảm, service cần kiểm tra nó không tiết lộ thông tin của tenant khác và những SOAP Header được ký/mã hóa đúng policy.

## 14. Trường hợp dùng SOAP Header và nội dung có chữ ký

SOAP Header có thể mang `CorrelationId`, `TenantContext`, `WS-Addressing` và `wsse:Security`. Nếu một header có ý nghĩa bảo mật/nghiệp vụ, đặt nó vào message **không đủ để tin được**.

Ví dụ một SOAP request có:

~~~xml
<soapenv:Header
    xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
    xmlns:hdr="urn:example:headers:v1">
    <hdr:TenantContext>tenant-a</hdr:TenantContext>
</soapenv:Header>
~~~

Một client độc hại có thể tự đổi `TenantContext` thành `tenant-b`. Vì vậy:

1. Nếu contract đòi header đó được bảo vệ, security policy phải xác minh header được **ký đúng phạm vi**, không chỉ Body.
2. Authorization vẫn phải so `TenantContext` với **principal/tenant** đã xác minh.
3. Nếu header không bắt buộc, không nên sử dụng nó để quyết định quyền truy cập.
4. Nếu interceptor đặt property vào `MessageContext` từ header, property đó không tự trở thành đáng tin; cần gắn nhãn nguồn và kết quả validation phù hợp.

**Quan trọng:** `mustUnderstand` yêu cầu SOAP node hiểu/xử lý một header nhắm đến nó; nó không có nghĩa header đã được ký, xác minh hoặc được phép dùng làm danh tính.

## 15. Kiểm thử thứ tự xử lý, không chỉ kiểm thử giá trị trả về

Một test “request hợp lệ trả ACCEPTED” không chứng minh rằng request chữ ký sai **chưa từng ghi database**. Để xác minh đúng thứ tự, cần kiểm tra cả **side effects, callbacks, Fault và nội dung SOAP thực tế**.

### Ma trận test đề xuất

| Test | Input hoặc cấu hình | Mong đợi |
| --- | --- | --- |
| Thành công | SOAP 1.1/1.2 hợp đồng, policy security đạt, quantity hợp lệ, caller có quyền | Endpoint chạy một lần, response hợp XSD và được bảo vệ theo policy |
| Thiếu chữ ký bắt buộc | SOAP Body hợp XSD nhưng không ký | Security từ chối, không gọi nghiệp vụ/ghi DB |
| Chữ ký không hợp lệ | Body bị thay sau khi ký | Không gọi business side effects |
| Signer không được tin cậy | Chữ ký đúng bằng khóa không thuộc trust policy | Bị từ chối trước nghiệp vụ |
| Signature wrapping | Chữ ký hợp lệ trên node khác với Body dùng | Không được chấp nhận |
| Timestamp hết hạn | Signed message cũ | Từ chối theo policy |
| Replay message | Message/nonce bị dùng lại trái policy | Từ chối; không tạo thêm đơn |
| XML hỏng/DTD ngoài | Parser không tạo message an toàn | Bị chặn, không gọi endpoint |
| Payload quá lớn | Vượt quota gateway/parser | Bị chặn trước tiêu tốn tài nguyên quá mức |
| XSD sai kiểu | `quantity=zero` | Fault dữ liệu, không ghi DB |
| XSD sai giới hạn | `quantity=0` | Fault dữ liệu, không ghi DB |
| Sai namespace | `urn:example:orders:v2` khi server chỉ có v1 | Không dispatch thành v1 hợp lệ |
| Không có quyền | Signature đúng nhưng caller không được phép dùng `CUST-001` | Không ghi DB; Fault authorization có kiểm soát |
| Sai nghiệp vụ | Còn 2 sản phẩm nhưng order yêu cầu 3 | Business Fault, không bán quá tồn kho |
| Retry hợp lệ | Cùng caller/key/payload theo idempotency policy | Không tạo đơn thứ hai |
| Cùng key, khác payload | Conflict với request trước | Từ chối hoặc xử lý theo contract, không ghi nhầm |
| Outbound thiếu field | Service tạo response không hợp XSD | Test phát hiện trước khi gửi response thành công |
| Outbound signature sai | Interceptor sửa Header/Body sau bước ký | Client verify thất bại; sửa pipeline |
| Fault sau security | XSD/business từ chối sau verify | Fault đúng SOAP version; không rò thông tin nhạy cảm |
| Lỗi tại proxy | TLS/route lỗi, chưa tới Spring-WS | Quan sát transport, không giả định endpoint callback chạy |

### Kiểm thử server với MockWebServiceClient

`MockWebServiceClient` cho phép gửi SOAP payload vào endpoint ở Spring test `ApplicationContext` và kiểm tra XML response/Fault. Để kiểm thử **WS-Security**, test phải tạo request có SOAP Header chữ ký/token thật và tải đúng security interceptor/trust material của môi trường test. Chỉ gọi `withPayload(new StringSource(...))` **không tự thêm chữ ký**.

Ví dụ payload hợp XSD:

~~~xml
<ord:PlaceOrderRequest xmlns:ord="urn:example:orders:v1">
    <ord:customerId>CUST-001</ord:customerId>
    <ord:clientRequestId>REQ-2026-001</ord:clientRequestId>
    <ord:sku>SKU-42</ord:sku>
    <ord:quantity>3</ord:quantity>
</ord:PlaceOrderRequest>
~~~

Có thể dùng mock/stub domain service để kiểm tra:

- Với request đã ký hợp lệ và có quyền, service được gọi chính xác một lần.
- Với chữ ký sai, service **không** được gọi.
- Với XSD invalid, service **không** được gọi.
- Với caller thiếu quyền, repository/transaction **không** ghi đơn.
- Trường hợp tạo Fault vẫn đi qua những bước cần thiết theo cấu hình.

### Kiểm thử client và tương thích thật

`MockWebServiceServer` kiểm tra request mà `WebServiceTemplate` sinh ra (SOAP Body/headers) và cách client xử lý response/Fault. Nó không thay thế kiểm thử server với `MockWebServiceClient`.

Sau các test mock, cần kiểm thử client **Java, .NET hoặc ESB** từ WSDL/XSD được công bố, đi qua TLS/mTLS, reverse proxy và WS-Security thực tế. Mismatch SOAP 1.1/1.2, SOAPAction, certificate trust, timestamp skew hoặc body signature coverage có thể không bộc lộ trong test endpoint đơn giản.

## 16. Quan sát và điều tra khi một request bị từ chối

Để tìm lỗi đúng tầng, log và metric nên mô tả **giai đoạn thất bại** mà không làm lộ bí mật:

~~~text
requestId=REQ-2026-001
stage=SCHEMA_VALIDATION
operation={urn:example:orders:v1}PlaceOrderRequest
result=REJECTED
errorCode=INVALID_QUANTITY
sideEffectExecuted=false
~~~

Đây là ví dụ **nội dung log đã được lọc**, không phải Spring-WS tự tạo sẵn log với các trường đó. Ở giai đoạn trước khi xác thực, correlation ID do client gửi có thể bị giả mạo; nếu cần uniqueness/tracing nội bộ, tạo thêm một server-side ID và tránh dùng correlation ID do client cấp làm chứng cứ danh tính.

### Ranh giới quan sát phù hợp

| Giai đoạn thất bại | Nơi có thông tin hữu ích | Điều không nên làm |
| --- | --- | --- |
| TLS/proxy | Gateway access log, TLS metrics, load balancer | Kỳ vọng `@Endpoint` log lỗi |
| XML parser | SOAP message factory/container logs | Dump raw request chứa dữ liệu nhạy cảm |
| WS-Security | Security interceptor, audit log đã lọc | Log private key/raw token/ciphertext nhạy cảm |
| Schema validation | Validator error code, QName, field name | Trả stack trace nội bộ cho client |
| Authorization | Decision reason nội bộ, verified principal ID | Tiết lộ resource của tenant khác |
| Business logic | Domain error và transaction outcome | Retry mù quáng một lệnh không idempotent |
| Outbound validation/signature | Serializer/security trace ở môi trường test | Sửa Body sau khi ký mà không tái ký |

Không biến một lỗi schema validation thành cảnh báo “unauthenticated user” chỉ vì security context không có principal do pipeline chưa đến bước đó. Ngược lại, khi chữ ký sai, không cần giải thích chi tiết `quantity` sai ở đâu cho một caller chưa được tin cậy.

## 17. Chẩn đoán các lỗi phổ biến

| Triệu chứng | Khả năng gây ra | Bước điều tra đầu tiên |
| --- | --- | --- |
| XML hợp XSD nhưng vẫn bị từ chối | Signature, timestamp, authorization hoặc business rule sai | Xem stage/reason của security và domain |
| Request chữ ký sai vẫn tạo đơn | Security được bỏ qua hoặc thực thi quá muộn | Kiểm tra interceptor registration, verify path và transaction |
| Request chưa auth nhận lỗi schema quá chi tiết | Validation sớm/lộ lỗi hoặc security bị bỏ qua | Cấu hình order, Fault policy và log |
| XSD validator không thấy dữ liệu | Body đang mã hóa hoặc Source không ở trạng thái thích hợp | Security decrypt/verify và message lifecycle |
| JAXB object có quantity 0 dù XSD cấm | Unmarshal không bật schema validation | Xem validator/schema config và test âm |
| Endpoint không chạy với QName đúng | Lỗi routing/adapter hoặc security chặn | Phân biệt `EndpointMapping`/interceptor/adapter |
| Fault bị proxy đổi thành HTML | Lỗi ở gateway hoặc error interception | So response trước/sau proxy |
| Valid signed request bị từ chối do clock skew | Đồng hồ client/server lệch, timestamp policy quá chặt | Đối chiếu NTP, policy, timestamp |
| Ký đúng nhưng client/server verify khác nhau | Sai canonicalization, signed parts hoặc trust material | Kiểm tra signature refs, actual consumed Body, cert trust |
| SOAP Header tenant bị tin nhầm | Header chưa được ký hoặc không ràng buộc với identity | Header scope, authorization và validated principal |
| Response đã ký không xác minh được | Validation/interceptor sửa message sau ký | Kiểm tra outbound order và message gửi thực tế |
| Client retry tạo đơn trùng | Không có idempotency atomic | Scope key, unique constraint, transaction/outbox |

### Sơ đồ chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["SOAP POST đến dịch vụ"] --> B{"Transport và XML parse an toàn?"}
    B -->|Không| C["Sửa gateway / TLS / parser / quota"]
    B -->|Có| D{"WS-Security policy đạt?"}
    D -->|Không| E["Verify signature, timestamp, trust, coverage"]
    D -->|Có| F{"Body hợp XSD và binding đúng?"}
    F -->|Không| G["Sửa schema / namespace / JAXB"]
    F -->|Có| H{"Caller được phép?"}
    H -->|Không| I["Kiểm tra principal, scope và ownership"]
    H -->|Có| J{"Business constraints và idempotency đạt?"}
    J -->|Không| K["Business Fault; không side effect sai"]
    J -->|Có| L["Transaction → response XSD → outbound security"]
~~~

Sơ đồ chú ý **thứ tự tin cậy**, không khẳng định framework luôn gọi chính các interceptor theo một tuyến tính cố định; endpoint mapping, Fault và các bước decrypt/verify còn phụ thuộc SOAP stack.

## 18. Bài tập tự kiểm tra

### Bài 1 — Phân loại lỗi theo tầng

Với bốn request `PlaceOrder` sau, hãy chỉ ra tầng phải từ chối và chứng minh rằng database không bị ghi:

1. `quantity=0` nhưng chữ ký hợp lệ và caller có quyền.
2. `quantity=3`, XSD hợp lệ nhưng signature Body sai.
3. `quantity=3`, signature hợp lệ nhưng caller thuộc tenant khác `customerId`.
4. `quantity=3`, auth và schema hợp lệ nhưng SKU đã hết hàng.

### Bài 2 — Lập bản thiết kế interceptor

Tạo một cấu hình Spring-WS với `Wss4jSecurityInterceptor` và `PayloadValidatingInterceptor`. Mô tả rõ:

- Những validation actions/security policy nào cần có?
- Interceptor nào nên nhìn thấy Body sau khi được giải mã/xác minh?
- Nếu `handleRequest` trả `false` hoặc có SOAP Fault, chuyện gì xảy ra với endpoint?
- Outbound response phải được kiểm tra trước/chữ ký sau như thế nào trên đúng runtime?
- Request không có endpoint phù hợp được chặn bằng lớp bảo vệ nào?

### Bài 3 — Kiểm tra chữ ký bao phủ đúng dữ liệu

Giả sử SOAP Header có một `ds:Signature` hợp lệ nhưng chỉ ký một node khác SOAP Body mà endpoint thực tế xử lý. Vì sao **có signature hợp lệ** vẫn chưa đủ? Hãy mô tả cách kiểm tra signed parts và chống XML Signature Wrapping.

### Bài 4 — Thiết kế idempotency

Một đối tác gửi `clientRequestId=REQ-2026-001` và retry khi timeout. Thiết kế khóa idempotency có scope caller/tenant, fingerprint payload và transaction, đồng thời giải thích vì sao mọi retry vẫn phải qua authentication/WS-Security policy.

### Bài 5 — Kiểm thử negative path

Viết test với `MockWebServiceClient` và security test fixtures cho ba request: hợp lệ, XML hợp lệ nhưng signature sai, và signature đúng nhưng XSD sai. Sử dụng mock service/repository để khẳng định **không có side effect** ở hai request bị từ chối. Sau đó kiểm tra SOAP Fault theo contract.

### Bài 6 — Ký response

Giả sử response đã được ký, một interceptor sau đó chèn `CorrelationId` vào SOAP Header bắt buộc phải có chữ ký. Hãy giải thích vì sao signature policy có thể thất bại, rồi đề xuất cách đặt thứ tự bổ sung Header, schema validation và securement outbound phù hợp.

## 19. Checklist trước khi triển khai production

| Nhóm | Điều kiện chấp nhận |
| --- | --- |
| **Transport** | TLS/mTLS, host trust, proxy header sanitization, limits và route POST chính xác |
| **XML parser** | Chặn DTD/XXE không cần thiết, giới hạn kích thước/độ sâu, resolver schema đáng tin cậy |
| **WS-Security** | Verify signature/token/timestamp/certificate trust, signed parts đúng, replay policy rõ |
| **Schema** | Validate payload đã giải mã/xác minh; XSD import/include resolve đầy đủ; Body và response có test |
| **JAXB/OXM** | Generated classes phù hợp XSD, không trộn `javax`/`jakarta`, marshal/unmarshal kiểm tra được |
| **Authorization** | Principal đáng tin, quyền theo operation và resource/tenant, không tin client-supplied IDs |
| **Business** | Rules/invariants, transaction, concurrency control, idempotency và outbox khi cần |
| **SOAP Fault** | Phân loại transport/schema/security/business; đúng SOAP version; không lộ bí mật |
| **Outbound** | Response hợp schema trước sign/encrypt, signed headers theo policy, client verify được |
| **Testing** | Happy path, signature invalid, schema invalid, unauthorized, replay, double submit, Fault và interop |
| **Observability** | Correlation nội bộ, audit có lọc, metrics theo stage, không log private key/token/raw SOAP vô hạn |

**Kết luận:** Trong dịch vụ **SPRING_WEB_SERVICES**, **kiểm tra dữ liệu**, **xác minh bảo mật** và **thực hiện nghiệp vụ** là những ranh giới độc lập nhưng có thứ tự phụ thuộc chặt chẽ. Phải làm an toàn kết nối và XML parser ngay từ đầu; xác minh thông điệp SOAP và phạm vi chữ ký/token theo chính sách trước khi tin dữ liệu; validate XSD/JAXB trước khi chuyển dữ liệu vào nghiệp vụ; chỉ thực hiện transaction khi caller đã được xác thực, có quyền và dữ liệu thỏa các ràng buộc cần thiết. Phản hồi cũng phải đúng XSD, SOAP Fault và WS-Security policy. Thứ tự callback thực tế có thể thay đổi theo SOAP stack, nhưng bất biến cần giữ là **không tác dụng phụ từ request chưa được tin cậy, không lộ thông tin ở nhánh lỗi và không sửa nội dung đã ký trái chính sách**.
