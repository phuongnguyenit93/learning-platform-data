# Subject và principal

> **Chương:** Identity  
> **Phạm vi:** Module **SECURITY_AUTHENTICATION_FUNDAMENTALS** nghiên cứu xác thực danh tính từ credential, mật khẩu, MFA, passkey, chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Để thiết kế luồng xác thực an toàn, trước tiên cần biết **ai là thực thể đang hành động (subject)** và **danh tính nào được hệ thống tin cậy để biểu diễn thực thể đó (principal)**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích **subject** và **principal**, nêu được điểm chung, điểm khác và lý do thuật ngữ đôi khi được dùng khác nhau giữa các công nghệ.
2. Phân biệt con người, tài khoản, danh tính số, credential, authenticator, principal, role và permission.
3. Mô tả quá trình xác thực tạo ra một **security context** có principal đáng tin, sau đó được dùng để kiểm tra quyền.
4. Hiểu ý nghĩa của claim **sub (subject)** trong OpenID Connect (OIDC)/JWT, vì sao cần kết hợp với **iss (issuer)** và vì sao không dùng email hoặc tên hiển thị làm khóa danh tính mặc định.
5. Xác định đúng chủ thể hành động trong hệ thống nhiều tenant, tài khoản dịch vụ, liên kết tài khoản và thao tác **on behalf of**.
6. Phát hiện các lỗi như tin vào userId do client gửi, nhầm service principal với người dùng cuối, nhầm xác thực thành phân quyền hoặc hợp nhất nhầm hai danh tính.

## 2. Subject và principal: hai góc nhìn về danh tính

Trong mô hình bảo mật tổng quát:

- **Subject (chủ thể):** thực thể mà một hành động hoặc một phát biểu về danh tính liên quan đến. Subject có thể là **người dùng**, **tiến trình**, **dịch vụ**, **thiết bị** hoặc **ứng dụng**. Trong kiểm soát truy cập, subject là bên yêu cầu thao tác; trong một phát biểu danh tính, subject là bên mà phát biểu đó nói đến.
- **Principal (định danh bảo mật/chủ thể được biểu diễn):** một biểu diễn danh tính mà thành phần bảo mật sử dụng để nhận biết chủ thể trong ngữ cảnh nhất định. Principal thường mang định danh ổn định, nguồn cấp danh tính, loại thực thể và đôi khi các thuộc tính xác thực liên quan. Trong nhiều framework, principal là đối tượng được đặt vào ngữ cảnh bảo mật sau khi chứng minh danh tính.

Đây là **quy ước khái niệm để tư duy**, không phải định nghĩa giống hệt trong mọi API. Có hệ thống dùng hai từ gần như đồng nghĩa; có hệ thống dùng *subject* cho đối tượng chứa nhiều principal; có giao thức dùng *subject identifier* làm claim mang định danh. Luôn đọc ý nghĩa của thuật ngữ **trong chính ngữ cảnh đang xét**.

### Một ví dụ trực quan

An đăng nhập vào một ứng dụng quản lý tài liệu bằng passkey qua nhà cung cấp danh tính (Identity Provider — IdP). Trong trường hợp này:

| Khái niệm | Ví dụ | Điều cần nhớ |
|---|---|---|
| **Con người** | An, một người sử dụng hệ thống | Một con người có thể sở hữu nhiều tài khoản/danh tính số |
| **Subject ở góc nhìn nghiệp vụ** | An là người đang yêu cầu xem tài liệu | Là thực thể thực hiện hành động trong tình huống đang xét |
| **Danh tính tại IdP** | Cặp (issuer, subject identifier) do IdP cấp | Mỗi IdP có không gian định danh riêng |
| **Principal tại ứng dụng** | Bản ghi đã xác thực đại diện cho danh tính của An trong request | Do thành phần bảo mật tạo ra từ bằng chứng đã được xác minh |
| **Tài khoản ứng dụng** | Account A-104, liên kết với danh tính IdP | Là thực thể quản lý hồ sơ, dữ liệu và quan hệ trong ứng dụng |
| **Credential/authenticator** | Passkey trên thiết bị của An | Dùng để chứng minh quyền kiểm soát danh tính khi xác thực |
| **Role/permission** | MEMBER, document:read | Mô tả quyền, không phải bản thân danh tính |
| **Resource** | Tài liệu DOC-12 thuộc tenant T1 | Đối tượng mà quyết định phân quyền áp dụng |

Từ bảng trên, không thể kết luận “An đã đăng nhập nên An có quyền xem mọi tài liệu”. Đăng nhập cho ứng dụng biết **principal nào đang được xác thực**; kiểm tra quyền còn cần biết tài liệu thuộc ai, ở tenant nào và chính sách cho phép điều gì.

## 3. Các thuật ngữ dễ bị trộn lẫn

### 3.1. Identity khác account

**Identity (danh tính số)** là tập các định danh và thuộc tính dùng để nhận biết một thực thể trong miền tin cậy cụ thể. **Account (tài khoản)** là bản ghi được hệ thống quản lý, thường gắn với trạng thái tài khoản, dữ liệu nghiệp vụ, quan hệ và chính sách.

Một tài khoản có thể liên kết nhiều cách đăng nhập (mật khẩu, passkey, đăng nhập doanh nghiệp), và một người có thể có nhiều tài khoản ở nhiều hệ thống. Quan hệ giữa “một người”, “một tài khoản” và “một danh tính từ IdP” **không tự động là một-một**.

Ví dụ, tài khoản nội bộ A-104 có thể được liên kết sau một quy trình an toàn với hai danh tính bên ngoài:

~~~text
Ứng dụng: account_id = A-104
   ├── issuer = https://login.company-a.example
   │   subject = 00u8d3...    (đăng nhập doanh nghiệp)
   └── issuer = https://login.partner-b.example
       subject = a93f21...    (đăng nhập đối tác)
~~~

Việc liên kết này chỉ hợp lệ sau khi hệ thống xác minh người đang thao tác thực sự kiểm soát **cả các danh tính cần liên kết** theo chính sách. Không được tự hợp nhất chỉ vì hai hồ sơ có cùng email.

### 3.2. Credential và authenticator không phải principal

- **Credential** là dữ liệu/bằng chứng được dùng trong xác thực theo một cơ chế xác định, chẳng hạn mật khẩu, khóa/cert hoặc credential WebAuthn.
- **Authenticator** là phương tiện giúp tạo ra bằng chứng xác thực hoặc kiểm soát credential: khóa bảo mật, ứng dụng xác thực, thiết bị chứa passkey, v.v.
- **Principal** là biểu diễn danh tính sau khi yêu cầu đã được kiểm tra bởi thành phần tin cậy; principal **không phải mật khẩu**, OTP hoặc private key.

Khi người dùng đổi mật khẩu, thêm passkey hay chuyển thiết bị, danh tính ứng dụng thường vẫn có thể là cùng một principal/account. Ngược lại, việc có được credential bị đánh cắp không biến kẻ tấn công thành chủ tài khoản ngoài đời: hệ thống có thể **nhận lầm** kẻ tấn công là principal của nạn nhân, và đó là thất bại của bước xác thực.

### 3.3. Principal, role và permission không đồng nghĩa

Principal trả lời **“ai?”**; role và permission giúp trả lời **“được làm gì?”**:

~~~text
principal = (issuer="https://idp.example", subject="u-7d4")
role trong tenant T1 = EDITOR
quyền khả dụng = document:read, document:update
quy tắc đối tượng = chỉ sửa tài liệu có quyền chỉnh sửa tại tenant T1
~~~

Không nên nhét “ADMIN” hoặc email vào vị trí định danh duy nhất của principal. Vai trò có thể thay đổi, trùng nhau ở nhiều tenant hoặc bị thu hồi. Quyết định phân quyền phải xét hành động, tài nguyên và ngữ cảnh bên cạnh danh tính đã xác thực.

## 4. Một subject có thể có nhiều principal — tùy hệ thống

Một người có thể dùng nhiều danh tính:

- Danh tính doanh nghiệp để truy cập ứng dụng nội bộ.
- Danh tính cá nhân để mua hàng.
- Danh tính cộng tác viên tại tổ chức khác.

Các danh tính đó **không mặc nhiên liên kết** chỉ vì cùng một con người. Một tiến trình cũng có thể chạy bằng tài khoản hệ điều hành, sử dụng workload identity để gọi dịch vụ và mang theo thông tin người dùng đang được phục vụ. Mỗi danh tính thuộc một **miền tin cậy** và có mục đích khác nhau.

### Khi đọc tài liệu Java, OIDC hay Spring Security

| Ngữ cảnh | Cách dùng thuật ngữ |
|---|---|
| **Mô hình kiểm soát truy cập** | Subject thường là thực thể thực hiện yêu cầu; chính sách đánh giá subject, action, resource và environment |
| **OIDC** | Claim **sub** là định danh của subject mà issuer phát biểu; cặp **iss + sub** xác định subject trong không gian định danh phù hợp |
| **JWT** | Claim **sub** chỉ là một trường định danh tùy ngữ cảnh token; cần xác minh toàn bộ token và hiểu token được phát hành cho mục đích gì |
| **Java** — `java.security.Principal` | Một interface biểu diễn một định danh; `getName()` trả tên của principal |
| **JAAS** — `javax.security.auth.Subject` | `Subject` có thể tập hợp **nhiều Principal**, public credentials và private credentials thuộc cùng subject |
| **Spring Security** | `Authentication.getPrincipal()` cung cấp principal theo cơ chế xác thực đang dùng, có thể là `UserDetails`, `Jwt`, tên định danh hoặc một đối tượng tùy biến |

Vì vậy không nên diễn giải cứng nhắc rằng “subject luôn là một con người còn principal luôn là username”. Cả hai đều có thể biểu diễn workload hoặc danh tính không phải con người. Với JAAS, subject là một đối tượng chứa tập principal; với OIDC, **subject** thường được thấy ở dạng giá trị claim `sub`.

## 5. Từ bằng chứng xác thực đến trusted principal

Một principal chỉ nên được xem là **đáng tin trong request hiện tại** sau khi hệ thống hoàn tất các bước kiểm tra phù hợp. Xem ví dụ ứng dụng dùng OIDC:

~~~mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant Browser as Trình duyệt
    participant IdP as Identity Provider
    participant App as Ứng dụng / API
    participant Account as Kho liên kết danh tính
    participant Policy as Bộ kiểm tra quyền

    User->>Browser: Yêu cầu đăng nhập
    Browser->>IdP: Khởi động luồng đăng nhập
    User->>IdP: Chứng minh danh tính bằng authenticator
    IdP-->>Browser: Kết quả đăng nhập theo giao thức
    Browser->>App: Hoàn tất luồng hoặc gửi access token
    App->>App: Xác minh giao thức, token/phiên và các ràng buộc
    App->>Account: Ánh xạ danh tính tin cậy (iss, sub)
    Account-->>App: Principal/tài khoản ứng dụng tương ứng
    App->>Policy: Subject/principal + action + resource + context
    Policy-->>App: PERMIT hoặc DENY
    App-->>Browser: Kết quả theo quyết định quyền
~~~

Sơ đồ là mô hình khái niệm; ở các luồng OIDC thực tế còn có redirect, `state`, `nonce`, PKCE và những kiểm tra riêng theo loại client/luồng. Có ứng dụng xác thực tại server rồi tạo session cookie; có API đóng vai trò OAuth resource server và kiểm tra access token. Hai kiểu này tạo security context bằng cách khác nhau nhưng phải chung nguyên tắc: **không lấy danh tính được tin cậy trực tiếp từ dữ liệu do client tùy ý khai**.

### Các bước quan trọng

1. **Thu nhận bằng chứng:** mật khẩu, passkey, MFA, chứng chỉ, phiên hoặc token đến từ luồng được thiết kế cụ thể.
2. **Kiểm tra tính hợp lệ và nguồn tin:** xác minh credential/challenge, giao thức hoặc token; với token cần đánh giá chữ ký/thuật toán cho phép, issuer, audience, thời hạn, loại token và các ràng buộc cần thiết.
3. **Xây dựng security context:** tạo hoặc lấy ra principal đã xác thực và thông tin đáng tin phục vụ request.
4. **Ánh xạ vào mô hình ứng dụng:** tìm tài khoản nội bộ hoặc tạo tài khoản qua quy trình đã kiểm soát; kiểm tra trạng thái khóa, thành viên tổ chức, liên kết danh tính và các thuộc tính liên quan.
5. **Kiểm tra authorization:** đánh giá principal cùng hành động, tài nguyên, tenant và chính sách; xác thực thành công **không đồng nghĩa** thao tác được phép.

Một username, email, userId, role hay tenantId gửi qua body, query, cookie tự tạo hoặc header không được xác minh chỉ là **dữ liệu đầu vào**, không phải principal đáng tin. Nếu có proxy/gateway truyền identity header, backend chỉ nên tin khi ranh giới mạng và cơ chế xác thực giữa các dịch vụ bảo đảm header do gateway đáng tin tạo ra và client không thể tự chèn/ghi đè.

## 6. Subject identifier trong OIDC, JWT và hệ thống nhiều IdP

Trong OIDC, `sub` là định danh subject do issuer cung cấp. Nó thường được thiết kế để ổn định trong phạm vi issuer và không được gán lại cho chủ thể khác theo quy tắc của giao thức. Tuy nhiên, **không gian định danh phụ thuộc issuer**; hai IdP có thể phát cùng giá trị `sub` cho hai người khác nhau.

Ví dụ:

~~~json
{
  "iss": "https://login.company-a.example",
  "sub": "user-0182",
  "aud": "app-portal",
  "exp": 2000000000
}
~~~

Nếu một token từ `https://login.partner-b.example` cũng có `sub = "user-0182"`, hai subject đó không nhất thiết là một. Do vậy, ứng dụng đa IdP thường xác định danh tính ngoài bằng khóa tổng hợp **(issuer, subject)** rồi ánh xạ vào accountId nội bộ:

~~~text
external_identity_key = (verified_issuer, verified_subject)
internal_account_id   = lookup_link(external_identity_key)
~~~

Các lưu ý thực tế:

- **Đọc `sub` trong payload chưa chứng minh token hợp lệ.** JWT có thể bị sửa nếu không xác minh chữ ký và các điều kiện của token. Không tự coi `sub` đáng tin chỉ vì có ba phần phân tách bằng dấu chấm.
- **`iss`, `aud` và mục đích token quan trọng.** API phải kiểm tra access token đúng issuer, dành cho chính API, chưa hết hạn và đáp ứng các chính sách khác. **OIDC ID token** nhằm truyền thông tin xác thực đến client nhận token; không dùng nó thay access token để gọi API.
- **`sub` không mặc nhiên là người thật.** Trong một số loại access token, subject có thể liên quan đến ứng dụng/tài khoản dịch vụ; phải hiểu cách issuer định nghĩa subject cho loại token đó.
- **`sub` có thể là pairwise identifier.** Một IdP có thể cấp subject khác nhau theo nhóm ứng dụng (sector) để hạn chế khả năng theo dõi chéo; không giả định một người luôn có cùng `sub` ở mọi ứng dụng.
- **Email không phải định danh an toàn để tự nối tài khoản.** Email có thể đổi, được tái sử dụng, chưa được xác minh hoặc xuất hiện trùng giữa các nguồn. `email_verified` giúp hiểu một thuộc tính email trong ngữ cảnh issuer, nhưng không tự chứng minh hai danh tính ở hai issuer là cùng một chủ thể.
- **Định danh từ IdP và accountId nội bộ là hai khóa khác nhau.** Thiết kế rõ việc liên kết, hủy liên kết, thay IdP, chuyển tenant và khôi phục tài khoản, thay vì ngầm giả định chúng là một.

Một cách lưu liên kết danh tính:

| issuer | subject | account_id | verified_at |
|---|---|---|---|
| `https://login.company-a.example` | `user-0182` | `A-104` | Thời điểm liên kết đã kiểm tra |
| `https://login.partner-b.example` | `p-667` | `A-104` | Thời điểm liên kết đã kiểm tra |

Trong cơ sở dữ liệu thực, cần ràng buộc duy nhất trên cặp **(issuer, subject)** và xây dựng quy trình quản lý thay đổi liên kết; bảng này chỉ minh họa mô hình dữ liệu.

## 7. Phân biệt subject, actor và người được đại diện

Trong hệ thống phân tán, câu “ai gọi API?” có thể có **nhiều tầng danh tính**:

1. **Người dùng cuối:** An yêu cầu tạo báo cáo trong ứng dụng web.
2. **Ứng dụng khách:** Frontend hoặc backend của ứng dụng gửi request.
3. **Workload/service:** Dịch vụ báo cáo gọi dịch vụ lưu trữ bằng danh tính máy của chính nó.
4. **Chủ thể được ủy quyền:** Một dịch vụ thực hiện tác vụ *on behalf of* An với phạm vi đã được cấp.

| Tình huống | Danh tính cần phân biệt | Rủi ro nếu nhầm |
|---|---|---|
| An gọi API trực tiếp bằng phiên | Principal đại diện An | Dùng principal sai tài khoản, truy cập dữ liệu không thuộc An |
| Worker chạy tác vụ định kỳ không có người dùng trực tiếp | Service principal của worker | Gán nhầm quyền người dùng hoặc cho phép tác vụ không có quy tắc riêng |
| Dịch vụ báo cáo gọi dịch vụ tài liệu thay An | Service principal **và** ngữ cảnh ủy quyền của An, nếu giao thức/chính sách yêu cầu | **Confused deputy**: dịch vụ có quyền rộng làm thay việc An không được phép |
| Nhân viên hỗ trợ được quyền truy cập hỗ trợ khách hàng | Danh tính nhân viên, khách hàng bị tác động và lý do/phiên hỗ trợ | Không thể truy vết ai thực hiện hành động; cấp quyền vượt phạm vi hỗ trợ |
| Admin chọn thao tác “xem dưới góc người dùng” | Actor gốc là admin, subject đích là người dùng được mô phỏng | Nhật ký ghi nhầm người dùng là tác nhân thực sự |

Không được thay nguyên principal của dịch vụ bằng một header `X-User-Id` do caller tự gửi rồi coi đó là quyền của người dùng. Với ủy quyền giữa các dịch vụ, hệ thống cần cơ chế được xác minh để chuyển thông tin người dùng, phạm vi được ủy quyền và danh tính dịch vụ thực hiện; việc truyền tiếp access token, dùng token exchange hoặc cơ chế delegation nào phải phù hợp thiết kế và phạm vi tin cậy.

**Audit log nên phân biệt:** actor thực hiện, chủ thể/khách hàng được tác động, danh tính service, hành động, tài nguyên, tenant, kết quả và correlation ID. Tránh ghi mật khẩu, private key, access token hoặc session secret vào log.

## 8. Ví dụ Java và Spring Security: dùng principal từ security context

Giả sử API đọc tài liệu được bảo vệ bằng **JWT access token** từ một IdP đã được cấu hình tin cậy. Ví dụ Spring Security sau minh họa cách lấy principal đã được xác minh. Các lớp `DocumentService`, `DocumentView` và `ExternalIdentity` là lớp minh họa của ứng dụng.

~~~java
// Cấu hình minh họa: ứng dụng đóng vai OAuth2 Resource Server.
// Cần cấu hình issuer, bộ xác minh JWT và audience phù hợp với API.
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/documents/**").authenticated()
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}

record ExternalIdentity(String issuer, String subject) {}

@RestController
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/api/documents/{id}")
    DocumentView read(
            @AuthenticationPrincipal Jwt jwt,
            @PathVariable UUID id) {
        // Spring Security đã xác minh token theo Resource Server config.
        // Bảo đảm config chấp nhận đúng issuer và audience dành cho API.
        ExternalIdentity identity = new ExternalIdentity(
            jwt.getIssuer().toString(),
            jwt.getSubject()
        );
        return service.readAs(identity, id);
    }
}
~~~

Phần quan trọng ở tầng dịch vụ (mã giả Java):

~~~java
DocumentView readAs(ExternalIdentity identity, UUID documentId) {
    // 1. Tra danh tính bên ngoài đã được xác minh.
    Account account = accounts.findByExternalIdentity(
        identity.issuer(), identity.subject()
    ).orElseThrow(AccessDeniedException::new);

    // 2. Chỉ tìm tài nguyên thuộc phạm vi tenant có hiệu lực của account.
    Document document = documents.findById(documentId)
        .orElseThrow(ResourceNotFoundException::new);

    // 3. Quyết định quyền cho hành động và đối tượng cụ thể.
    if (!policy.canRead(account, document)) {
        throw new AccessDeniedException("Access denied");
    }
    return DocumentView.from(document);
}
~~~

Ví dụ không định nghĩa toàn bộ model, dependency và exception; mục tiêu là cho thấy ranh giới trách nhiệm. `Account` phải có trạng thái và tư cách thành viên tenant hợp lệ; `policy.canRead` phải xét cả tenant và quan hệ với tài liệu. Với truy vấn danh sách, nên lọc theo quyền ngay từ tầng dữ liệu để tránh lộ bản ghi. Khi cần che giấu sự tồn tại tài nguyên, chính sách có thể dùng phản hồi 404 thay 403 một cách nhất quán.

**Tại sao mã này không nhận `userId` từ URL hoặc body?** Vì client không có quyền chọn mình là ai; backend rút danh tính từ security context đã xác minh. `jwt.getSubject()` chỉ an toàn trong bối cảnh pipeline xác thực đúng. Nếu tự đọc payload bằng Base64 hoặc `JWT.decode(...)` mà chưa verify, `sub` là dữ liệu chưa đáng tin.

### Lưu ý riêng về Java `Principal` và JAAS `Subject`

~~~java
// API Java SE: một Principal biểu diễn một định danh.
Principal principal = () -> "account:A-104";
String principalName = principal.getName();

// API JAAS: một Subject có thể chứa nhiều principal.
Subject subject = new Subject();
subject.getPrincipals().add(principal);
~~~

Đoạn này chỉ mô tả cách các kiểu dữ liệu liên hệ với nhau. **Tự tạo `Principal` hoặc `Subject` không tương đương xác thực thành công**; một đối tượng Java được khởi tạo thủ công chưa có bằng chứng nào được kiểm chứng. Việc thiết lập security context tin cậy phải do cơ chế xác thực phù hợp chịu trách nhiệm.

## 9. Subject và principal qua vòng đời danh tính

Hai thuật ngữ tiếp tục hữu ích sau khi đăng nhập:

| Giai đoạn | Vấn đề danh tính cần giải quyết |
|---|---|
| **Đăng ký và cấp tài khoản** | Xác định account/subject trong ứng dụng; phân biệt tạo tài khoản với thẩm định danh tính con người ngoài đời |
| **Đăng nhập bằng mật khẩu, MFA, passkey hoặc chứng chỉ** | Chứng minh quyền kiểm soát authenticator/credential gắn với danh tính mong đợi; chống phishing, guessing và replay |
| **Cấp phiên/token** | Gắn những yêu cầu sau với principal đã xác thực, kiểm tra hiệu lực, ràng buộc và giới hạn phiên/token |
| **Đăng nhập liên kết / federation** | Ánh xạ subject do IdP phát hành vào account nội bộ theo chính sách, tránh nhầm issuer và chủ thể |
| **Liên kết và hủy liên kết danh tính** | Xác minh quyền kiểm soát trước khi thay quan hệ giữa external identity và account; ngăn account takeover |
| **Phân quyền / chuyển tenant** | Kiểm tra principal tại tenant đang hoạt động cùng chính sách, đối tượng và hành động hiện tại |
| **Khôi phục tài khoản** | Kiểm tra lại quyền kiểm soát danh tính bằng quy trình đủ tin cậy; ngăn khôi phục sai vào account của người khác |
| **Thu hồi / khóa tài khoản** | Quy định khi nào security context, phiên và token đã cấp không còn được chấp nhận |

Ví dụ, đổi phương thức đăng nhập từ mật khẩu sang passkey **không cần đổi accountId**. Nhưng nếu liên kết tài khoản sai, kẻ tấn công có thể thêm cách đăng nhập của họ vào một account hợp lệ và tiếp tục đăng nhập dù người dùng thật đã đổi mật khẩu. Vì vậy cơ chế account linking và recovery phải kiểm tra **chủ thể đang thao tác** và quy trình chứng minh quyền kiểm soát phù hợp.

## 10. Những lỗi thiết kế thường gặp

| Cách làm sai | Hậu quả | Thiết kế đúng |
|---|---|---|
| Gán principal từ `X-User-Id` hoặc `userId` trong body do client gửi | Giả mạo danh tính, truy cập ngang tài khoản | Lấy principal từ security context sau xác thực; kiểm tra dữ liệu do client gửi theo chính sách |
| Dùng email làm khóa duy nhất giữa mọi IdP | Nhầm/hợp nhất sai account, chiếm tài khoản qua email bị tái sử dụng | Dùng `(verified issuer, subject)` và quy trình linking có xác minh |
| Đọc JWT `sub` nhưng không xác minh token | Tin vào subject tùy ý do kẻ tấn công viết | Xác minh token và mục đích sử dụng theo cấu hình tin cậy |
| Xem service principal là bằng chứng người dùng cuối đã đồng ý | Dịch vụ trở thành tác nhân có quyền rộng làm thay người dùng | Quản lý riêng service identity, user identity và delegation |
| Xem `role = ADMIN` là một loại danh tính | Role thay đổi có thể gây lẫn quyền và lỗi multi-tenant | Tách định danh chủ thể khỏi các thuộc tính quyền |
| Chỉ check `isAuthenticated()` rồi cho sửa mọi tài nguyên | Broken Object Level Authorization/IDOR | Kiểm tra authorization tại mỗi hành động và đối tượng |
| Dùng display name/email để ghi audit | Khó truy vết khi trùng tên, đổi tên hoặc chuyển IdP | Ghi định danh ổn định có namespace, actor, resource, thời gian và kết quả |
| Tin mọi thông tin identity header từ reverse proxy | Header spoofing và leo thang quyền | Xác định rõ trusted proxy, xóa/ghi đè header không đáng tin và bảo vệ kết nối nội bộ |
| Cache role/quyền suốt đời session bất kể thay đổi | Người bị thu hồi quyền vẫn có thể thao tác | Thiết kế cách làm mới quyết định quyền và chiến lược thu hồi phù hợp |

Đăng nhập bằng **MFA hay passkey chống phishing** có thể tăng độ tin cậy của kết quả AuthN, nhưng **không làm biến mất lỗi AuthZ hoặc lỗi liên kết danh tính**. Tương tự, token ký số đúng vẫn có thể bị sử dụng sai nếu bỏ qua audience, tenant, quyền cấp đối tượng hoặc sự khác nhau giữa client và người dùng cuối.

## 11. Ma trận kiểm thử identity → principal → quyền

Giả sử tài liệu D-1 thuộc account A-104 trong tenant T1; tài liệu D-2 thuộc account B-205 trong tenant T2. Mục tiêu là kiểm tra cả danh tính được chọn và phạm vi truy cập:

| Kiểm thử | Principal/bằng chứng | Kết quả mong đợi |
|---|---|---|
| Đăng nhập hợp lệ, truy cập D-1 | Subject đã xác minh, ánh xạ A-104, có quyền read ở T1 | Cho phép đọc những trường được cấp quyền |
| Cùng người dùng đổi URL sang D-2 | Vẫn là A-104, không có quyền với T2 | Từ chối; không lộ dữ liệu T2 |
| Client gửi `userId=B-205` để đọc D-2 | Principal thật vẫn là A-104 | Không chuyển danh tính theo tham số tự khai |
| JWT có `sub` đúng nhưng sai `iss` | Không có identity tin cậy từ issuer được chấp nhận | Từ chối token hoặc từ chối ánh xạ tùy cấu hình |
| JWT được ký nhưng `aud` dành cho API khác | Token không dành cho API hiện tại | Từ chối xác thực |
| Hai IdP cùng phát `sub="42"` | Hai khóa `(iss, sub)` khác nhau | Không tự hợp nhất hai tài khoản |
| Worker có service token hợp lệ nhưng không có ủy quyền của An | Danh tính service, không có quyền đại diện An | Từ chối thao tác phụ thuộc quyền của An |
| Nhân viên bị xóa khỏi tenant T1 sau khi đăng nhập | Principal vẫn có thể nhận diện nhân viên | Quyền tenant mới phải có hiệu lực theo chiến lược thu hồi |
| Người dùng khôi phục tài khoản | Bằng chứng recovery đạt/chưa đạt yêu cầu | Chỉ gắn lại authenticator cho đúng account sau xác minh |

Khi triển khai test tự động, đo cả **response** lẫn **tác động thực tế**: database có bị sửa không, export có chứa dữ liệu tenant khác không, log có ghi đúng actor không và token/credential có bị lộ không.

## 12. Bài tập tình huống

Một công ty triển khai nền tảng đa tenant. API nhận:

~~~http
GET /api/tenants/T2/reports/R-50
Authorization: Bearer <access-token-của-An>
X-User-Id: admin
~~~

Token hợp lệ, xác thực được principal của An; An là thành viên tenant T1. Trong khi đó, R-50 thuộc tenant T2. Backend đang lấy `X-User-Id` làm actor để tra quyền và bỏ qua thông tin tenant thực tế.

**Câu hỏi:**

1. Subject/actor thật của request là ai? Principal nào phải được sử dụng?
2. Vì sao `X-User-Id: admin` không thể dùng làm căn cứ xác thực?
3. Tại sao access token hợp lệ chưa đủ để trả R-50?
4. Cần kiểm tra những điều kiện nào trước khi trả báo cáo?

**Gợi ý lời giải:**

1. Actor trong ngữ cảnh người dùng là An; API phải lấy principal do lớp xác thực tạo ra từ token đã được xác minh. Nếu có thêm service trung gian, cần phân biệt service actor và user được đại diện.
2. Header do client kiểm soát là dữ liệu chưa đáng tin. Kẻ tấn công có thể thay thành bất kỳ tên nào; không được dùng nó để thay đổi principal.
3. Token hợp lệ chỉ giúp xác lập danh tính/ngữ cảnh xác thực và phạm vi token. AuthZ vẫn phải xét quyền của An đối với tenant T2 và báo cáo R-50.
4. Kiểm tra token đúng issuer/audience/thời hạn; ánh xạ danh tính đúng account; tư cách thành viên tenant T2; quyền report:read; quan hệ với R-50; trạng thái báo cáo và các điều kiện nghiệp vụ khác. Thiếu một điều kiện cần thiết thì từ chối.

## 13. Ghi nhớ trọng tâm

- **Subject** là thực thể được nói đến hoặc đang hành động trong ngữ cảnh; **principal** là biểu diễn danh tính được thành phần bảo mật sử dụng. Ý nghĩa chính xác phụ thuộc mô hình, giao thức và framework.
- **Principal khác credential và quyền.** Mật khẩu, MFA, passkey, chứng chỉ giúp xác thực; role và permission giúp quyết định hành động được phép.
- **Không mặc định đồng nhất con người, account, external identity và principal.** Một con người có thể có nhiều danh tính, một account có thể liên kết nhiều IdP, còn service cũng có principal riêng.
- **OIDC/JWT `sub` phải được hiểu cùng issuer và ngữ cảnh token.** Chỉ tin claim sau khi giao thức/token được xác minh; không dùng email để tự hợp nhất danh tính.
- **Mọi kiểm tra quyền dùng principal từ nguồn tin cậy**, sau đó áp dụng chính sách cho hành động, đối tượng và tenant cụ thể. Header hoặc ID do client tự khai không tạo ra danh tính đáng tin.
- **Khi có hệ thống trung gian hoặc ủy quyền**, phân biệt actor thực hiện với người được đại diện để tránh confused deputy và để nhật ký có khả năng truy vết.

Nắm chắc subject và principal giúp thiết kế đúng ranh giới tin cậy xuyên suốt đăng nhập, duy trì phiên, dùng token, liên kết danh tính và khôi phục tài khoản; đồng thời tránh việc một cơ chế xác thực mạnh bị vô hiệu hóa bởi ánh xạ danh tính hoặc phân quyền sai.
