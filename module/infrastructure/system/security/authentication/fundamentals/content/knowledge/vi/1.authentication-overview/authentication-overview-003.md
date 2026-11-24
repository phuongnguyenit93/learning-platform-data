# Authentication và authorization

> **Chủ đề:** Bức tranh tổng thể về xác thực danh tính (authentication) và kiểm soát quyền truy cập (authorization). Đây là hai quyết định liên quan nhưng độc lập: hệ thống cần biết yêu cầu đến từ **ai** trước khi quyết định chủ thể ấy **được làm gì** với một tài nguyên cụ thể.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt authentication (AuthN) với authorization (AuthZ) qua câu hỏi, đầu vào, kết quả và lỗi thường gặp.
- Mô tả mối quan hệ giữa danh tính, credential, authenticator, session/token, principal, quyền và tài nguyên.
- Theo dõi một yêu cầu từ lúc đăng nhập đến lúc truy cập API, chỉ ra nơi thiết lập và kiểm tra ranh giới tin cậy.
- Nhận diện vì sao đăng nhập thành công, có MFA hoặc mang token hợp lệ vẫn chưa đủ để đọc/sửa bất kỳ dữ liệu nào.
- Thiết kế và kiểm tra nguyên tắc **deny by default**, **least privilege** và kiểm tra quyền ở cấp đối tượng (object-level authorization).

Trong phạm vi module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, xác thực được nghiên cứu từ credential, mật khẩu, MFA, passkey, chứng chỉ cho đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này xây dựng mô hình tổng thể để hiểu các cơ chế ấy phục vụ bước AuthN như thế nào và kết nối an toàn với quyết định AuthZ ra sao. Những cơ chế chuyên sâu sẽ được khảo sát riêng; trọng tâm ở đây là phân định trách nhiệm và tránh nhầm lẫn khi xây dựng luồng truy cập.

## 2. Hai câu hỏi bảo mật khác nhau

**Authentication (xác thực)** trả lời: *“Bên đang tương tác là chủ thể nào và bằng chứng xác thực có đủ đáng tin hay không?”* Ví dụ, máy chủ kiểm tra mật khẩu, một phản hồi WebAuthn/passkey, mã MFA, chứng chỉ máy khách hoặc một phiên đã được thiết lập và còn hợp lệ. Sau khi xác thực, hệ thống có thể tạo **authenticated principal**: biểu diễn danh tính đã được xác nhận trong ngữ cảnh của yêu cầu.

**Authorization (phân quyền/cho phép truy cập)** trả lời: *“Chủ thể đã biết này có được thực hiện hành động cụ thể trên tài nguyên cụ thể, trong bối cảnh hiện tại hay không?”* Ví dụ, người dùng A được xem hóa đơn của A nhưng không được sửa hóa đơn của B; một nhân viên hỗ trợ được xem thông tin cần thiết để giải quyết yêu cầu, nhưng không được xuất toàn bộ dữ liệu khách hàng.

| Góc nhìn | Authentication — AuthN | Authorization — AuthZ |
|---|---|---|
| Câu hỏi chính | Ai đang đưa ra yêu cầu? Có bằng chứng xác thực hợp lệ không? | Chủ thể này có được thực hiện hành động này trên tài nguyên này không? |
| Đầu vào điển hình | Credential, authenticator, session cookie, access token, kết quả xác thực từ IdP | Principal đã xác thực, hành động, tài nguyên, chính sách, quan hệ sở hữu, ngữ cảnh |
| Kết quả | Xác thực thành công/thất bại; có thể lập phiên hoặc tạo security context | Permit/deny và đôi khi các ràng buộc bổ sung |
| Phạm vi | Gắn một yêu cầu với danh tính/chủ thể đáng tin ở mức yêu cầu | Giới hạn quyền đối với API, thao tác, đối tượng dữ liệu hoặc chức năng |
| Ví dụ lỗi | Mật khẩu sai, mã MFA sai, phiên hết hạn, token không hợp lệ | Đúng tài khoản nhưng không có quyền sửa, không phải chủ sở hữu, vượt phạm vi ủy quyền |
| Câu hỏi kiểm thử | Kẻ tấn công có thể giả mạo hoặc chiếm phiên của người khác không? | Người đã đăng nhập có thể truy cập dữ liệu/hành động ngoài quyền không? |

Một người có thể **xác thực đúng** nhưng vẫn **bị từ chối truy cập**. Ngược lại, một quy tắc cho phép xem tài nguyên công khai có thể cho phép yêu cầu ẩn danh; khi ấy AuthZ vẫn đưa ra quyết định, nhưng không bắt buộc phải có AuthN.

**Phân biệt thêm ba khái niệm gần nhau:**

1. **Identification (khai báo danh tính):** người dùng nhập tên đăng nhập “alice”; đây mới là lời khai “tôi là Alice”.
2. **Authentication (chứng minh quyền sử dụng danh tính):** người dùng chứng minh mình kiểm soát authenticator/credential gắn với tài khoản Alice.
3. **Identity proofing (thẩm định danh tính ngoài đời):** một quy trình riêng để xác minh thông tin pháp lý hoặc con người thực. Tài khoản đăng nhập hợp lệ tự nó không chứng minh chủ tài khoản chính là một cá nhân ngoài đời đã được thẩm định.

## 3. Những thành phần trong quyết định truy cập

Hãy xét API xem hóa đơn của một ứng dụng thương mại:

| Thành phần | Vai trò trong ví dụ |
|---|---|
| **Subject / principal** | Người dùng đã xác thực với định danh nội bộ ổn định, chẳng hạn userId = U123 |
| **Credential / authenticator** | Mật khẩu, passkey, khóa bảo mật, chứng chỉ hoặc bằng chứng xác thực khác dùng tại bước đăng nhập |
| **Session / token** | Cách máy chủ nhận biết những yêu cầu tiếp theo thuộc phiên/danh tính nào; chính sách kiểm tra hiệu lực vẫn phải được thực thi |
| **Action** | read, create, update, delete, approve, export…; với yêu cầu hiện tại là read |
| **Resource** | Hóa đơn INV-42, có ownerId = U123, trạng thái và thuộc tính riêng |
| **Policy** | Chẳng hạn “chủ sở hữu được đọc hóa đơn của mình; nhân viên tài chính chỉ được đọc trong phạm vi được giao” |
| **Context** | Tổ chức/tenant đang chọn, thời gian, thiết bị, mức độ xác thực gần đây hoặc trạng thái nghiệp vụ nếu chính sách cần |
| **Enforcement point** | Lớp API/service/database thực thi quyết định cho phép/từ chối, không phụ thuộc giao diện có ẩn nút hay không |

Ta có thể mô tả quyết định AuthZ ở mức khái niệm:

~~~text
decision = authorize(principal, action, resource, context, policy)
decision ∈ {PERMIT, DENY}
~~~

Chính sách có thể yêu cầu thêm điều kiện, ví dụ buộc **xác thực lại** hoặc **step-up MFA** trước khi chuyển tiền lớn. Khi đó AuthZ yêu cầu mức bảo đảm xác thực cao hơn; việc vừa hoàn thành bước AuthN ban đầu không mặc nhiên đáp ứng điều kiện mới.

**Ranh giới tin cậy:** trình duyệt, ứng dụng di động và các giá trị do khách hàng gửi (userId trong URL, trường ownerId trong JSON, role tự khai, trạng thái nút bấm) đều nằm phía **không đáng tin**. Chỉ thành phần máy chủ được phép xác thực session/token, gắn principal và quyết định quyền dựa trên dữ liệu/chính sách đáng tin.

## 4. Ví dụ: đã đăng nhập nhưng vẫn không được đọc hóa đơn của người khác

Giả sử ứng dụng có hai người dùng, An (U123) và Bình (U456). An đăng nhập hợp lệ rồi gửi yêu cầu:

~~~http
GET /api/invoices/INV-42
Cookie: session=<session-của-An>
~~~

Máy chủ kiểm tra phiên và xác định principal = U123. Trong cơ sở dữ liệu, hóa đơn INV-42 có ownerId = U123. Chính sách cho phép: **AuthN thành công, AuthZ thành công**, API trả về dữ liệu.

Bây giờ An thay ID tài nguyên thành INV-99, vốn thuộc Bình:

~~~http
GET /api/invoices/INV-99
Cookie: session=<session-của-An>
~~~

Phiên của An **vẫn hợp lệ**, nên AuthN tiếp tục thành công. Nhưng vì ownerId của INV-99 là U456, kiểm tra AuthZ phải từ chối. Nếu API chỉ kiểm tra “đã đăng nhập chưa?” và trả hóa đơn theo ID, đó là lỗi **Broken Object Level Authorization (BOLA)**, thường được gọi là **IDOR (Insecure Direct Object Reference)** trong các tình huống tham chiếu đối tượng thiếu kiểm tra quyền.

Việc đoán ID khó, dùng UUID, đổi tên trường, ẩn liên kết hoặc đặt role = USER không thay thế được kiểm tra quyền cho **từng đối tượng**. API phải xử lý trường hợp người dùng thay đổi URL/ID, gọi trực tiếp endpoint hoặc bỏ qua hoàn toàn giao diện.

## 5. Luồng hoàn chỉnh: từ đăng nhập đến mỗi yêu cầu API

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant Auth as Dịch vụ xác thực
    participant API as API
    participant Policy as Bộ kiểm tra quyền
    participant DB as CSDL

    User->>Browser: Nhập thông tin / dùng passkey
    Browser->>Auth: Gửi bằng chứng xác thực qua TLS
    Auth->>Auth: Kiểm tra credential, MFA và rủi ro
    alt Xác thực không đạt
        Auth-->>Browser: Từ chối đăng nhập
    else Xác thực đạt
        Auth-->>Browser: Thiết lập phiên an toàn
        Browser->>API: GET /invoices/INV-42 + cookie phiên
        API->>Auth: Kiểm tra hiệu lực phiên
        Auth-->>API: Principal U123
        API->>DB: Đọc thuộc tính hóa đơn và tenant
        DB-->>API: ownerId, tenantId, trạng thái...
        API->>Policy: Được read(INV-42) không?
        alt Không đủ quyền
            Policy-->>API: DENY
            API-->>Browser: 403 hoặc 404 theo chính sách
        else Đủ quyền
            Policy-->>API: PERMIT
            API-->>Browser: 200 + dữ liệu được phép xem
        end
    end
~~~

Sơ đồ minh họa phiên lưu phía máy chủ; khi dùng token tự chứa, API thường xác thực token tại chính API hoặc lớp bảo mật chung. Dù cơ chế vận chuyển danh tính khác nhau, hai phép kiểm tra vẫn tồn tại:

1. **Kiểm tra tin cậy của principal:** cookie phiên có tra được phiên hợp lệ không? Access token có chữ ký và các thuộc tính bắt buộc hợp lệ không? Phiên/token có hết hạn, bị thu hồi hoặc không phù hợp với API này không?
2. **Kiểm tra quyền cho yêu cầu hiện tại:** principal có được gọi hành động này không, trên tài nguyên này, với tenant/trạng thái/điều kiện hiện tại không?

Không nên coi kết quả kiểm tra quyền tại thời điểm đăng nhập là quyền vĩnh viễn của mọi yêu cầu về sau: quyền, vai trò, quyền sở hữu và trạng thái tài nguyên đều có thể thay đổi trong thời gian phiên tồn tại.

### Vì sao session/token không tự mang lại mọi quyền?

- **Session cookie** là một giá trị tham chiếu hoặc phương tiện liên kết yêu cầu với một phiên. Nó chỉ đáng tin khi máy chủ kiểm tra tính hợp lệ, thời hạn và trạng thái phiên; cookie bị đánh cắp có thể bị lạm dụng như bearer secret nếu không có biện pháp bảo vệ phù hợp.
- **Access token** thường đại diện một quyền truy cập được cấp cho client hoặc một principal trong một phạm vi nhất định. API phải kiểm tra token được phát hành bởi bên tin cậy, dành cho chính API này, còn hiệu lực và đáp ứng yêu cầu bảo mật. Token hợp lệ không tự động cấp quyền với mọi đối tượng dữ liệu.
- **ID token trong OpenID Connect (OIDC)** chủ yếu truyền thông tin về sự kiện xác thực và người dùng tới client dự kiến nhận token; không nên dùng ID token thay access token để gọi API.
- **OAuth 2.0** là khuôn khổ cấp quyền truy cập/ủy quyền. Khi cần lớp xác thực đăng nhập có danh tính chuẩn hóa trên OAuth, thường dùng OIDC. Một OAuth scope có thể giúp giới hạn quyền của ứng dụng khách, nhưng vẫn cần kiểm tra quyền sở hữu và chính sách nghiệp vụ đối với tài nguyên.

Với JWT access token, bước kiểm tra điển hình bao gồm thuật toán/chữ ký theo cấu hình tin cậy, issuer (iss), audience (aud), thời hạn (exp), thời điểm có hiệu lực (nbf) nếu có, cũng như các ràng buộc ứng dụng liên quan. **Giải mã** payload JWT không có nghĩa đã **xác minh** token; các claim do client tự gửi không thể được coi là đáng tin trước khi kiểm tra đầy đủ.

## 6. Cách triển khai authorization

Không phải mọi hệ thống đều dùng một kiểu chính sách. Các mô hình thường phối hợp với nhau:

| Mô hình | Dựa vào | Ví dụ | Giới hạn cần lưu ý |
|---|---|---|---|
| **RBAC** — Role-Based Access Control | Vai trò và các quyền được gán | ADMIN có quyền quản trị người dùng; ANALYST xem báo cáo tổng hợp | Có role không đồng nghĩa có quyền trên mọi hóa đơn của mọi tenant |
| **ABAC** — Attribute-Based Access Control | Thuộc tính của principal, tài nguyên, hành động, ngữ cảnh | Chỉ người thuộc cùng tenant được xem báo cáo trong thời gian dự án còn mở | Thuộc tính phải đến từ nguồn đáng tin và cập nhật khi thay đổi |
| **ReBAC** — Relationship-Based Access Control | Quan hệ giữa chủ thể và đối tượng | Chủ sở hữu, thành viên nhóm, người được chia sẻ tài liệu | Phải kiểm tra quan hệ thực ở phía máy chủ, không tin ID do client tự khai |
| **Quyền tường minh / permission** | Tập hành động được cấp | invoice:read, invoice:approve, user:invite | Quyền thao tác chung có thể vẫn cần ràng buộc dữ liệu theo đối tượng |

Trong hệ thống nhiều tổ chức (**multi-tenant**), cần xét đồng thời quyền thao tác và **ranh giới tenant**. Ví dụ, nhân viên hỗ trợ của tenant T1 có quyền invoice:read nhưng không vì thế được đọc hóa đơn thuộc tenant T2. Việc client chuyển header hoặc tham số tenantId sang T2 không được coi là bằng chứng của tư cách thành viên T2.

**Các nguyên tắc triển khai:**

- **Deny by default:** nếu không có quy tắc cho phép rõ ràng, kết quả là DENY.
- **Least privilege:** chỉ cấp quyền nhỏ nhất cần cho công việc; tách quyền đọc, chỉnh sửa, phê duyệt, xuất dữ liệu nếu mức rủi ro khác nhau.
- **Server-side enforcement:** kiểm tra tại máy chủ/API và các lớp dữ liệu phù hợp; ẩn nút trên UI chỉ là trải nghiệm, không phải cơ chế bảo mật.
- **Check per action and object:** kiểm tra với mỗi endpoint/operation và từng bản ghi hoặc tập dữ liệu; đối với truy vấn danh sách, lọc theo quyền ngay ở truy vấn thay vì lấy tất cả rồi trả về.
- **Không tin metadata tự khai:** client gửi role, userId hoặc tenantId chỉ để mô tả yêu cầu; server lấy danh tính/quyền từ security context hoặc nguồn dữ liệu được kiểm soát.
- **Cập nhật và thu hồi:** thay đổi vai trò, khóa tài khoản hoặc thu hồi quyền cần có chiến lược hiệu lực rõ ràng với session, cache quyền và token còn hạn.

## 7. Ví dụ Java: chặn truy cập ở cả tuyến API và đối tượng dữ liệu

Đoạn mã Spring Security dưới đây minh họa hai lớp kiểm tra. Cấu hình tuyến yêu cầu **đã xác thực**; dịch vụ nghiệp vụ tiếp tục kiểm tra **quyền sở hữu**. Các kiểu như AccountPrincipal, Invoice và InvoiceRepository là kiểu của ứng dụng giả định.

~~~java
// Cấu hình: mọi yêu cầu tới hóa đơn phải có principal hợp lệ.
@Bean
SecurityFilterChain security(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(registry -> registry
            .requestMatchers("/api/invoices/**").authenticated()
            .anyRequest().denyAll())
        .build();
}

@RestController
class InvoiceController {
    private final InvoiceService service;

    InvoiceController(InvoiceService service) {
        this.service = service;
    }

    @GetMapping("/api/invoices/{invoiceId}")
    InvoiceDto getInvoice(
            @AuthenticationPrincipal AccountPrincipal principal,
            @PathVariable UUID invoiceId) {
        return service.readInvoice(principal.accountId(), invoiceId);
    }
}

@Service
class InvoiceService {
    private final InvoiceRepository repository;

    InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    InvoiceDto readInvoice(UUID authenticatedAccountId, UUID invoiceId) {
        Invoice invoice = repository.findById(invoiceId)
            .orElseThrow(ResourceNotFoundException::new);

        // AuthZ cấp đối tượng: không suy ra quyền chỉ vì đã đăng nhập.
        if (!invoice.ownerAccountId().equals(authenticatedAccountId)) {
            throw new AccessDeniedException("Không được đọc hóa đơn này");
        }

        return InvoiceDto.from(invoice);
    }
}
~~~

Trong ứng dụng thực tế, đối tượng AccountPrincipal phải được tạo từ cơ chế xác thực tin cậy; tuyến phải được bảo vệ bởi đúng cấu hình security chain. Phải xử lý an toàn các endpoint còn lại (POST, PATCH, DELETE, export), quyền theo tenant, quy tắc nghiệp vụ và dữ liệu nhạy cảm trong thông báo lỗi. Khi sử dụng xác thực dựa trên cookie, phải cân nhắc **CSRF** và cài đặt cookie phù hợp (Secure, HttpOnly, SameSite theo luồng); khi dùng token, cần bảo vệ lưu trữ, truyền tải và vòng đời token. Không nên vô hiệu hóa các bảo vệ mặc định chỉ để đoạn ví dụ chạy nhanh.

Có thể đẩy kiểm tra xuống truy vấn để giảm rủi ro truy xuất nhầm đối tượng và hỗ trợ cả danh sách:

~~~sql
-- authenticatedAccountId do server lấy từ principal, không lấy từ body/URL.
SELECT id, amount, currency, issued_at
FROM invoices
WHERE id = :invoiceId AND owner_account_id = :authenticatedAccountId;
~~~

Với chính sách phức tạp (quản trị viên, chia sẻ, tenant, phòng ban), truy vấn và lớp policy cần biểu diễn đầy đủ các ngoại lệ được phép; không giản lược thành “có vai trò ADMIN thì bỏ mọi kiểm tra tenant”.

## 8. Phân biệt mã phản hồi và xử lý lỗi

| Tình huống | Phản hồi thường phù hợp | Lý do |
|---|---|---|
| API bắt buộc đăng nhập nhưng thiếu hoặc không có thông tin xác thực hợp lệ | **401 Unauthorized** | Cần xác thực hợp lệ; với HTTP authentication có thể kèm WWW-Authenticate |
| Principal hợp lệ nhưng không có quyền thực hiện thao tác | **403 Forbidden** | AuthN thành công; AuthZ từ chối |
| Tài nguyên không tồn tại | **404 Not Found** | Không tìm thấy tài nguyên |
| Muốn tránh tiết lộ sự tồn tại của tài nguyên mà người gọi không được biết | Có thể trả **404** thay **403** theo chính sách nhất quán | Giảm rò rỉ thông tin qua việc phân biệt ID có tồn tại hay không |
| Chỉ được xem các dòng của tenant A, nhưng truy vấn danh sách lại trả cả tenant B | **Lỗi AuthZ dù HTTP trả 200** | Không chỉ kiểm tra mã trạng thái; cần kiểm thử dữ liệu kết quả |

Tên “401 Unauthorized” trong chuẩn HTTP dễ gây nhầm vì 401 thường phản ánh **chưa được xác thực hợp lệ**, còn 403 phản ánh **bị từ chối truy cập**. Trong UI, hệ thống có thể chuyển người dùng về màn hình đăng nhập hoặc hiển thị thông báo thân thiện, nhưng API vẫn cần ngữ nghĩa lỗi nhất quán.

## 9. Các kiểu tấn công và bước bảo vệ tương ứng

| Rủi ro | Nhắm vào lớp nào? | Biện pháp cốt lõi |
|---|---|---|
| Credential stuffing, đoán mật khẩu | AuthN | Giới hạn tốc độ, phát hiện bất thường, mật khẩu mạnh và lưu bằng password hashing thích hợp, MFA |
| Phishing, đánh cắp mã OTP hoặc phiên | AuthN/duy trì phiên | Ưu tiên passkey/WebAuthn chống phishing cho ngữ cảnh phù hợp, bảo vệ phiên, ràng buộc và xác minh nguồn đăng nhập |
| Replay bằng chứng đăng nhập hoặc token bị đánh cắp | AuthN/duy trì phiên | Challenge/nonce khi giao thức yêu cầu, TLS, token ngắn hạn, kiểm soát vòng đời và thu hồi phiên/token |
| Sử dụng token phát hành cho dịch vụ khác | Kiểm tra danh tính tại API | Xác minh issuer, audience, chữ ký, thời hạn và ràng buộc giao thức |
| BOLA/IDOR: đổi invoiceId để đọc dữ liệu người khác | AuthZ cấp đối tượng | Kiểm tra ownership/quan hệ/quyền trên **mỗi** đối tượng |
| Vượt quyền ngang (người A lấy dữ liệu người B) hoặc dọc (USER làm việc ADMIN) | AuthZ | Kiểm tra cả phạm vi dữ liệu lẫn quyền thao tác, từ chối mặc định |
| Truy cập chéo tenant | AuthZ và cô lập dữ liệu | Xác thực tư cách thành viên tenant, ràng buộc tenant ở policy và truy vấn |
| Confused deputy: dịch vụ có quyền cao làm thay yêu cầu không đủ quyền | AuthZ giữa các dịch vụ | Phân biệt danh tính service với người dùng ủy quyền; ràng buộc quyền theo đối tượng/hành động và không dùng quyền service để bỏ kiểm tra người gọi |

**MFA không sửa được lỗi AuthZ.** Dù An đã dùng passkey và nhiều yếu tố xác thực, An vẫn không được đọc dữ liệu của Bình nếu thiếu quyền. Tương tự, che giấu ID hoặc kiểm tra ở frontend không thay thế việc xác minh danh tính và quyết định truy cập tại backend.

## 10. Ma trận kiểm thử cho một API

Với endpoint GET /api/invoices/{invoiceId}, giả sử U123 sở hữu INV-42, U456 sở hữu INV-99, và không có chính sách chia sẻ chéo. Khi kiểm thử cần thay đổi **ai gọi**, **gọi hành động gì** và **đối tượng nào**:

| Người gọi | Tài nguyên / trạng thái | Kết quả mong đợi |
|---|---|---|
| Ẩn danh | INV-42, endpoint yêu cầu xác thực | 401 |
| U123, phiên hợp lệ | INV-42 thuộc U123 | 200, chỉ các trường được phép |
| U123, phiên hợp lệ | INV-99 thuộc U456 | 403 hoặc 404 theo chính sách |
| U123, phiên hết hạn/đã thu hồi | INV-42 | 401 |
| U456, phiên hợp lệ | INV-42 thuộc U123 | 403 hoặc 404 theo chính sách |
| Người dùng có quyền chỉ đọc | PATCH /api/invoices/INV-42 | 403, không thay đổi dữ liệu |
| U123 thuộc tenant T1 | Hóa đơn của tenant T2 dù biết đúng ID | Bị từ chối, không rò rỉ dữ liệu |

Khi mở rộng test, cần thử thêm: gọi API trực tiếp không qua UI; đổi path/query/body ID; tráo tenantId; dùng access token có audience khác; dùng token hết hạn; phân quyền bị thu hồi trong khi phiên còn sống; truy vấn danh sách, export và endpoint lồng nhau. Quan sát **dữ liệu thực tế trả về**, tác động lên hệ thống và log sự kiện, không chỉ dựa vào mã HTTP.

## 11. Quy trình tư duy khi thiết kế một luồng mới

Trước khi xây dựng endpoint hoặc hành động nhạy cảm, hãy trả lời theo thứ tự:

1. **Ai là principal?** Danh tính người dùng, tài khoản dịch vụ hay ứng dụng thứ ba? Có phải request ẩn danh được phép không?
2. **Bằng chứng AuthN nào là đủ?** Session/token có kiểm tra hiệu lực chưa? Thao tác có cần xác thực lại hoặc MFA gần thời điểm thực hiện không?
3. **Tài nguyên và hành động là gì?** “Được dùng tính năng hóa đơn” quá rộng; cần cụ thể “được đọc hóa đơn số X” hay “được phê duyệt hóa đơn X”.
4. **Quyền đến từ đâu?** Role, permission, quan hệ sở hữu/chia sẻ, tenant và trạng thái nghiệp vụ lấy từ nguồn nào được tin cậy?
5. **Chính sách được thực thi tại đâu?** Cả đường dẫn trực tiếp, job nền, API xuất dữ liệu và các service phụ có cùng kết quả kiểm tra không?
6. **Điều gì xảy ra khi thiếu bằng chứng hoặc thiếu quyền?** Từ chối mặc định; phản hồi 401/403/404 phù hợp; không để lộ tài nguyên hoặc thông tin nhạy cảm qua lỗi.
7. **Điều gì thay đổi trong lúc phiên còn sống?** Nếu tài khoản bị khóa hoặc quyền bị thu hồi, hệ thống cập nhật quyết định bằng cách nào?

## 12. Ghi nhớ trọng tâm

- **Authentication xác minh danh tính/nguồn gốc yêu cầu; authorization quyết định phạm vi hành động trên tài nguyên.** Chúng liên kết nhưng không thay thế nhau.
- **Credential, MFA, passkey, chứng chỉ, session và token giúp chứng minh hoặc truyền ngữ cảnh xác thực**; mức độ tin cậy phụ thuộc cơ chế kiểm tra và vòng đời tương ứng.
- **Một principal hợp lệ vẫn có thể không được phép** thực hiện thao tác, truy cập đối tượng hoặc vượt ranh giới tenant.
- **Bảo vệ phải nằm ở backend và được áp dụng cho mỗi hành động, mỗi đối tượng cần bảo vệ.** Mọi dữ liệu do client tự khai phải được kiểm chứng.
- **Thiết kế bắt đầu từ ranh giới tin cậy và chính sách quyền rõ ràng**: deny by default, least privilege, thu hồi kịp thời và kiểm thử các trường hợp truy cập chéo.

Khi tách đúng hai quyết định này, hệ thống có thể nâng cấp phương thức xác thực (chẳng hạn từ mật khẩu sang passkey) mà vẫn giữ nguyên nguyên tắc phân quyền; đồng thời có thể thay đổi vai trò, quyền sở hữu hoặc tenant mà không phải nhầm lẫn với việc người dùng đăng nhập thành công hay thất bại.
