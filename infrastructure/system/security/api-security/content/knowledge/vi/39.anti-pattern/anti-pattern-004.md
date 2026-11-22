# Tin API key là đủ cho tài nguyên nhạy cảm

API key hữu ích để nhận diện một ứng dụng, đối tác hoặc integration đang gọi API. Nhưng một API key tĩnh thường là bearer secret: ai lấy được key có thể sử dụng nó với danh tính client mà key đại diện. Việc request có key hợp lệ chỉ chứng minh caller đang nắm credential đó; nó không tự chứng minh người dùng cuối là ai, họ có quyền trên hồ sơ nào, hay hành động hiện tại có phù hợp với nghiệp vụ không.

Anti-pattern xuất hiện khi backend coi một API key hợp lệ là điều kiện duy nhất để đọc hoặc sửa tài nguyên nhạy cảm. Ví dụ, một ứng dụng gửi header X-API-Key và backend trả mọi hồ sơ khách hàng, hóa đơn hoặc tài liệu nếu key tồn tại. Nếu key được nhúng trong frontend, commit vào repository, ghi vào log hoặc chia sẻ giữa nhiều đối tác, bất kỳ ai lấy được key đều có thể kế thừa quyền quá rộng đó.

API key vẫn có chỗ đứng trong thiết kế bảo mật. Nó có thể nhận diện client, áp quota, phân biệt môi trường hoặc bảo vệ API ít nhạy cảm. Với dữ liệu nhạy cảm, cần đặt key trong một mô hình nhiều lớp: xác thực principal phù hợp, phân quyền chức năng, kiểm tra quyền trên từng object và áp dụng business rule theo trạng thái tài nguyên.

## 1. API key thực sự chứng minh điều gì?

API key thường là một chuỗi ngẫu nhiên được cấp cho client hoặc integration. Client gửi key trong header, ví dụ:

~~~http
GET /api/documents/8f2a HTTP/1.1
Host: api.example.test
X-API-Key: sk_live_example_secret
~~~

Server tra cứu key, xác minh secret và tìm credential record tương ứng. Record đó có thể gắn với một client, tenant, environment, quota, scope hoặc ngày hết hạn.

Nếu key được thiết kế đúng, server có thể kết luận:

- Request đang sử dụng credential đã được cấp cho một client/integration.
- Credential chưa bị revoke hoặc hết hạn.
- Credential thuộc environment/tenant được cấu hình.
- Client có thể được phép gọi một số nhóm chức năng theo policy gắn với key.

Tuy nhiên, key tự nó không chứng minh:

- Người đang cầm key là user nào.
- Người dùng cuối có đăng nhập hoặc còn là thành viên tenant không.
- Người gọi có quyền đọc một customer, invoice, document hoặc order cụ thể không.
- Người gọi có quyền thực hiện hành động nhạy cảm như export, approve, refund hoặc delete không.
- Request đến từ đúng ứng dụng chính thức hay một script đã sao chép key.
- Credential chưa bị sao chép sang máy khác.
- Hành động phù hợp với trạng thái hiện tại của resource hoặc workflow.

Một key có thể nhận diện service account mà không nhận diện user cuối. Nếu ứng dụng cần thực hiện hành động thay mặt một người dùng, phải có cơ chế delegation và kiểm tra quyền của user đó.

### 1.1. Phân biệt client authentication và user authentication

| Danh tính | Câu hỏi | Credential thường dùng |
|---|---|---|
| Application/client | Ứng dụng hoặc integration nào đang gọi? | API key, OAuth client credentials, mTLS |
| End user | Người dùng nào đang thực hiện hành động? | User access token, session |
| Workload/service | Service nào đang gọi service khác? | Workload identity, OAuth client credentials, mTLS |
| Delegated actor | Service đang hành động thay mặt user nào? | Delegated access token, token exchange hoặc cơ chế delegation tương đương |

Không thay user identity bằng một API key chung của frontend hoặc backend. Nếu một service nhận key của ứng dụng nhưng thao tác trên dữ liệu của nhiều user, nó cần xác định user/tenant context đáng tin cậy và kiểm tra quyền của user đối với resource.

### 1.2. API key có scope vẫn chưa đủ cho object authorization

Một API key record có thể được gán scope như documents:read hoặc payments:create. Điều này giúp giới hạn chức năng mà client được gọi.

Nhưng scope documents:read không có nghĩa client được đọc mọi document trong hệ thống. Server vẫn phải kiểm tra document thuộc tenant, project, customer hoặc case nào và principal có quan hệ truy cập hợp lệ hay không.

Có thể hình dung:

- Authentication: key có hợp lệ không?
- Client authorization: client này được gọi operation nào?
- User authorization: user đang hành động có quyền gì?
- Object authorization: user/client có quyền trên resource cụ thể không?
- Business rule: resource có đang ở trạng thái cho phép hành động không?

Bỏ qua bất kỳ lớp nào có thể tạo ra BOLA/IDOR hoặc lạm quyền nghiệp vụ.

## 2. Vì sao tin API key là đủ lại nguy hiểm?

### 2.1. Key bị lộ đồng nghĩa credential bị sao chép

API key tĩnh thường có thể được sao chép và sử dụng lại cho tới khi hết hạn hoặc bị revoke. Một attacker không cần chiếm tài khoản người dùng nếu có thể lấy key từ:

- JavaScript bundle hoặc mobile application package.
- Git repository, CI log, build artifact hoặc file cấu hình.
- Browser local storage, extension hoặc developer tools.
- Log của application, API gateway, reverse proxy hoặc APM.
- URL/query string, analytics, browser history hoặc referrer.
- Ticket hỗ trợ, email, chat hoặc tài liệu onboarding.
- Máy developer, máy đối tác hoặc môi trường staging.
- Một integration/subprocessor được cấp key nhưng bảo vệ yếu.

Obfuscation, minification hoặc đổi tên biến không làm key trong client-side code trở thành secret. Người dùng kiểm soát browser/device có thể quan sát request và trích xuất credential.

### 2.2. Một key dùng chung tạo phạm vi ảnh hưởng lớn

Nếu nhiều user, tenant hoặc partner cùng dùng một key, hệ thống khó xác định ai thực sự thực hiện request. Khi key lộ, không thể dễ dàng revoke quyền của một user cụ thể mà không ảnh hưởng mọi consumer dùng chung key.

Key dùng chung cũng làm audit kém chính xác: log chỉ cho thấy integration A gọi API, không cho biết user X hay Y đã đọc hồ sơ nào. Nếu service nhận user ID từ request body mà không xác minh, attacker có thể giả mạo actor.

### 2.3. Key quá rộng biến lỗi nhỏ thành sự cố lớn

Một key được cấp quyền đọc mọi customer, tải mọi file và export mọi giao dịch có blast radius rất lớn. Ngay cả khi key chỉ lộ trong thời gian ngắn, attacker có thể thu thập nhiều dữ liệu trước khi bị phát hiện.

Giới hạn theo endpoint hoặc tenant có thể giảm phạm vi, nhưng phải được enforce ở server. Không dùng một key chung cho cả staging và production; không dùng key read-only cho thao tác ghi; không cấp quyền admin cho integration chỉ cần một chức năng hẹp.

### 2.4. Key không mang theo ngữ cảnh người dùng

Một API key thường không thể hiện membership hiện tại, assignment, consent, purpose hoặc trạng thái phiên của user. Nếu user rời tenant nhưng integration key vẫn hoạt động, backend có thể tiếp tục cho phép truy cập dữ liệu tenant đó nếu không kiểm tra membership.

Tương tự, một nhân viên có thể được phép xem metadata nhưng không được tải file gốc. API key chung không tự biểu diễn được sự khác biệt quyền này.

### 2.5. Replay và giả mạo request

Với static key gửi trong header, người lấy được key có thể replay request. HTTPS bảo vệ dữ liệu trên đường truyền nhưng không ngăn key bị lộ ở endpoint client, log, máy chủ hoặc công cụ quan sát.

Nếu API dùng HMAC request signing, chữ ký có thể ràng buộc method, path, timestamp và body digest, nhưng hệ thống vẫn cần chống replay bằng nonce/timestamp window và lưu trạng thái cần thiết. HMAC chứng minh request được ký bằng secret của client; nó không tự chứng minh user cuối có quyền trên object.

## 3. Các biến thể phổ biến của anti-pattern

| Biến thể | Vì sao sai | Hậu quả |
|---|---|---|
| Đặt API key trong JavaScript frontend | Mọi visitor có thể trích xuất key | Key bị dùng ngoài ứng dụng |
| Một key cho tất cả user | Không có actor identity riêng | Không thể thu hồi/audit theo user |
| Một key cho nhiều tenant | Key không cô lập dữ liệu | Cross-tenant exposure |
| Key hợp lệ thì cho phép mọi endpoint | Không có function authorization | Privilege escalation |
| Có scope read thì đọc mọi object | Thiếu object authorization | BOLA/IDOR |
| Tin tenant ID do client gửi | Context không đáng tin | Tenant spoofing |
| Key không hết hạn và không rotate | Credential tồn tại lâu | Cửa sổ khai thác kéo dài |
| Key nằm trong query string | Dễ xuất hiện trong URL log/history/referrer | Credential leakage |
| Log raw key để debug | Log trở thành kho credential | Credential compromise |
| Chỉ bảo vệ ở API gateway | Có thể có đường gọi trực tiếp upstream | Gateway bypass |
| CORS cho phép origin đáng tin nên coi key an toàn | CORS không xác thực caller và không giấu secret | Key vẫn bị lấy và replay |
| API key thay cho MFA hoặc user login | Không xác minh người dùng | Hành động nhạy cảm thiếu xác thực phù hợp |

## 4. Khi nào API key là lựa chọn phù hợp?

API key không phải lúc nào cũng sai. Vấn đề là dùng nó như danh tính duy nhất cho tài nguyên có mức nhạy cảm cao hoặc cấp quyền rộng.

Có thể dùng API key cho:

- Nhận diện client gọi một public API ít nhạy cảm.
- Áp rate limit, quota, billing hoặc analytics theo integration.
- Phân biệt project/environment.
- Một service nội bộ khi đã có network boundary và các lớp identity/authorization khác.
- Legacy integration đang trong quá trình chuyển sang OAuth2 hoặc workload identity.

Ngay cả trong các trường hợp này, key nên có scope hẹp, quota rõ, expiry/rotation, khả năng revoke và audit.

Không nên dùng static API key làm cơ chế duy nhất cho:

- Đọc hồ sơ khách hàng, tài chính, sức khỏe hoặc pháp lý.
- Tải tài liệu riêng tư hoặc dữ liệu tenant.
- Thay đổi role, permission hoặc membership.
- Approve, refund, transfer, delete hoặc thao tác có tác động tài chính.
- Thực hiện hành động thay mặt user.
- Truy cập admin/control plane hoặc secret management.
- Truy cập nhiều tenant bằng một credential không có object-level policy.

Nếu một key được giới hạn thành capability chỉ đọc đúng một object và một action, có expiry ngắn và có thể revoke, nó đang hoạt động như một capability token chuyên biệt. Hãy mô hình hóa và quản lý nó như capability có phạm vi rõ, không coi nó là API key chung có quyền đọc tài nguyên nhạy cảm.

## 5. Chọn cơ chế xác thực theo loại caller

### 5.1. Browser và ứng dụng mobile

Không nhúng secret API key dùng chung vào JavaScript hoặc mobile binary. Mọi secret trong client do người dùng kiểm soát đều có thể bị trích xuất.

Với ứng dụng có user đăng nhập:

- Dùng Authorization Code Flow với PKCE cho public client.
- Nhận access token ngắn hạn gắn với user và audience phù hợp.
- Dùng scope tối thiểu cho chức năng cần gọi.
- Backend kiểm tra object-level authorization trên từng request.
- Dùng refresh token rotation và bảo vệ session theo hướng dẫn của identity provider.
- Không đặt token trong URL hoặc log.

Mobile application có thể có cơ chế attestation hoặc secure storage hỗ trợ giảm rủi ro, nhưng không nên coi chúng là bằng chứng duy nhất rằng người gọi được phép đọc mọi resource.

### 5.2. Service-to-service

Với workload hoặc backend service, ưu tiên identity dành cho workload:

- OAuth2 Client Credentials để cấp access token ngắn hạn với audience và scope giới hạn.
- Mutual TLS để xác thực service ở tầng kết nối.
- Workload identity của nền tảng triển khai nếu có.
- Secret manager để cấp và rotate credential.

Nếu vẫn phải dùng API key trong integration cũ, gắn key với một service principal cụ thể, tenant/environment rõ, scope hẹp, quota và expiry. Cân nhắc mTLS hoặc HMAC signing như lớp bổ sung tùy threat model. Service nhận request vẫn phải kiểm tra resource và business permission.

### 5.3. Service hành động thay mặt user

Dùng delegated user token hoặc token exchange phù hợp với identity platform. Token cần thể hiện actor/delegation và audience; service chỉ nhận các scope cần thiết.

Không dùng client credentials của integration rồi tin một trường userId trong body để quyết định quyền. User ID do client tự gửi có thể bị thay đổi. Nếu API cần actor ID, lấy từ token đã xác minh hoặc một delegation context được ký/xác thực.

### 5.4. Partner API

Với đối tác server-to-server, có thể kết hợp:

- Partner identity riêng.
- OAuth2 client credentials hoặc credential tương đương.
- mTLS hoặc request signing khi cần xác thực kênh/client mạnh hơn.
- Scope và tenant binding ở server.
- Object-level policy và business constraints.
- Quota, rate limit, monitoring và quy trình revoke.

Một partner key chỉ nên đại diện cho partner integration đã đăng ký. Nếu partner có nhiều khách hàng cuối, cần truyền và xác minh context khách hàng theo mô hình delegation hoặc tenant mapping được kiểm soát.

## 6. Mô hình authorization cho tài nguyên nhạy cảm

Một quyết định truy cập nên dựa trên principal, action, resource và context.

| Thành phần | Dữ liệu cần xác minh |
|---|---|
| Principal | User, client, service account hoặc delegated actor đã xác thực |
| Tenant | Tenant từ identity/server-side membership đã xác minh |
| Action | read metadata, download, update, approve, export, delete |
| Resource | Customer, invoice, document, order hoặc record cụ thể |
| Relationship | Owner, member, assignee, ACL, parent project |
| Context | Purpose, environment, risk, session, time, approval |
| State | Resource active, not revoked, đúng workflow state |
| Decision | Allow/deny và reason code phục vụ audit |

### 6.1. Kiểm tra tenant từ nguồn đáng tin

Không lấy tenant ID từ query/body/header rồi dùng thẳng để truy vấn dữ liệu. Tenant phải đến từ token đã xác minh, membership lookup hoặc server-side client binding.

Ví dụ, một service principal có thể được gắn với tenant A trong credential registry. Nếu request gửi tenant B, backend phải bỏ qua hoặc từ chối thay vì chuyển context sang tenant B.

### 6.2. Kiểm tra quyền trên từng object

Một user có scope documents:read vẫn cần được kiểm tra document thuộc tenant/project mà user được phép truy cập.

Ví dụ truy vấn có ràng buộc:

~~~sql
SELECT d.*
FROM documents d
JOIN project_members pm ON pm.project_id = d.project_id
WHERE d.id = :documentId
  AND d.tenant_id = :verifiedTenantId
  AND pm.user_id = :authenticatedUserId
  AND pm.can_read_documents = TRUE
  AND d.status = 'AVAILABLE';
~~~

Schema thực tế có thể khác. Ý chính là ràng buộc object, tenant và principal phải cùng tham gia quyết định. Không truy xuất object toàn cục rồi dựa vào frontend hoặc một check tùy chọn để lọc dữ liệu.

### 6.3. Phân biệt quyền chức năng và quyền dữ liệu

Một principal có thể được phép gọi GET /documents/{id} nhưng chỉ đọc metadata. Quyền download bytes, preview, share, export và delete nên được mô hình hóa riêng nếu rủi ro khác nhau.

Tương tự, scope payments:read không tự cho phép refund. Scope orders:write không tự cho phép approve mọi order. Kiểm tra role/scope, object relationship và workflow state độc lập.

## 7. Thiết kế API key an toàn khi vẫn cần sử dụng

Nếu hệ thống phải tiếp tục hỗ trợ API key, hãy giới hạn key thành credential nhận diện client với quyền được cấu hình phía server.

### 7.1. Sinh key có entropy đủ mạnh

- Dùng bộ sinh số ngẫu nhiên mật mã (CSPRNG).
- Có đủ entropy để chống đoán; không dùng timestamp, UUID tự tạo từ random yếu hoặc chuỗi tuần tự.
- Có prefix để nhận diện môi trường/loại key nếu cần, nhưng prefix không phải secret.
- Tách public key identifier khỏi secret component để tra cứu record hiệu quả.
- Hiển thị secret đầy đủ một lần khi tạo; không cho xem lại raw key.
- Không encode tenant, role hoặc permission trong chuỗi key rồi tin các giá trị đó mà không xác minh.

Ví dụ format minh họa:

~~~text
ak_live_7F3K9Q.<high-entropy-secret>
~~~

Prefix và identifier chỉ phục vụ lookup/operational handling. Quyền thực tế phải nằm trong credential record được bảo vệ ở server.

### 7.2. Lưu trữ và xác minh key

Không lưu raw key trong database nếu không cần khả năng khôi phục. Có thể lưu public identifier cùng hash của secret bằng thuật toán phù hợp với secret entropy cao, kèm salt/pepper theo thiết kế. Khi nhận key:

1. Validate format và độ dài.
2. Dùng public identifier để tìm credential record.
3. Tính hash theo cấu hình hiện tại.
4. So sánh theo cách constant-time phù hợp.
5. Kiểm tra trạng thái active, expiry, revocation, environment và client binding.
6. Nạp scope/quota từ record server-side.
7. Tạo authenticated client principal.

Nếu key có entropy cao, hash nhanh chuyên dụng có thể phù hợp hơn password hashing chậm; chọn cách lưu theo threat model và chuẩn nội bộ. Không dùng password hash cho API key entropy thấp mà không đánh giá lại khả năng brute-force. Bảo vệ pepper/master secret bằng secret manager/KMS.

### 7.3. Least privilege và credential record

Credential record nên có tối thiểu:

| Thuộc tính | Mục đích |
|---|---|
| key_id/public_id | Tra cứu và audit |
| secret_hash | Xác minh secret |
| client_id | Client/integration sở hữu key |
| tenant_id | Tenant được gắn với client, nếu có |
| environment | Development/staging/production |
| scopes/permissions | Các chức năng được phép |
| resource constraints | Resource/project/account được giới hạn |
| rate_limit/quota | Ngưỡng sử dụng |
| created_at/expires_at | Vòng đời |
| last_used_at | Theo dõi hoạt động |
| revoked_at/revocation_reason | Thu hồi |
| created_by | Người hoặc quy trình cấp key |

Không cho caller tự gửi scopes hoặc tenant rồi ghi đè record. Khi quyền thay đổi, cập nhật record/policy phía server và bảo đảm cache/replica được đồng bộ trong thời gian chấp nhận được.

### 7.4. Tách key theo environment và purpose

Dùng key riêng cho development, staging và production. Dùng key riêng cho read-only, upload, billing hoặc integration khác nhau nếu chúng có vòng đời và rủi ro khác nhau.

Không sao chép production key vào file cấu hình cá nhân, test fixture hoặc CI log. CI cần lấy credential từ secret store với quyền và thời hạn tối thiểu.

### 7.5. Expiry, rotation và revoke

- Đặt expiry phù hợp với loại integration.
- Có quy trình rotate trước ngày hết hạn.
- Hỗ trợ giai đoạn overlap ngắn giữa key cũ và key mới nếu không thể đổi đồng loạt.
- Theo dõi last_used_at và thu hồi key không còn dùng.
- Revoke được theo key, client hoặc tenant khi có sự cố.
- Khi revoke, làm mất hiệu lực cache/replica trong SLA đã định nghĩa.
- Audit ai tạo, xem secret lúc cấp, rotate hoặc revoke key.

Không dùng một key vĩnh viễn cho hệ thống có dữ liệu nhạy cảm. Không để overlap vô thời hạn vì điều đó biến rotation thành thêm một credential sống song song.

## 8. Truyền key, browser và CORS

### 8.1. Dùng HTTPS và header phù hợp

Gửi key qua TLS và header chuyên dụng như X-API-Key nếu contract yêu cầu. Không gửi key trong query string vì URL có thể xuất hiện trong access log, proxy log, browser history, analytics và referrer.

Không ghi raw key trong log, trace, exception hoặc support ticket. Log key ID/public identifier và kết quả xác thực thay cho secret.

### 8.2. CORS không bảo vệ API key

CORS là chính sách browser quyết định JavaScript từ origin nào được đọc response. Nó không phải cơ chế xác thực client và không ngăn curl, script hoặc attacker dùng key đã lấy được.

Một key nhúng trong frontend vẫn có thể bị trích xuất dù server chỉ allowlist một domain. CORS không chứng minh request thực sự đến từ code chính thức của domain đó.

### 8.3. Không dùng API key như mật khẩu phía browser

Nếu browser cần truy cập dữ liệu nhạy cảm, người dùng phải được xác thực và backend phải áp dụng user/object authorization. Không đặt một key có quyền đọc dữ liệu tenant vào bundle hoặc local storage để mọi user cùng sử dụng.

Một số nhà cung cấp gọi key được phép xuất hiện trong browser là **publishable key** hoặc **public key**. Loại key này phải được thiết kế như public identifier: nó chỉ bật một tập chức năng công khai, không mở dữ liệu riêng tư, không cho phép thao tác quản trị và không thể dùng để suy ra secret key tương ứng. Rate limit, domain restriction hoặc CORS có thể hỗ trợ kiểm soát abuse, nhưng không biến public key thành secret. Nếu một credential có quyền đọc tài nguyên nhạy cảm, coi nó là secret và giữ ở backend.

## 9. Ví dụ Spring: key chỉ tạo client principal

### 9.1. Cách làm nguy hiểm

~~~java
@GetMapping("/api/documents/{id}")
public Document getDocument(
        @RequestHeader("X-API-Key") String apiKey,
        @PathVariable UUID id) {

    if (!apiKey.equals(configuredKey)) {
        throw new UnauthorizedException();
    }

    return documentRepository.findById(id)
        .orElseThrow(NotFoundException::new);
}
~~~

Đoạn code này có nhiều vấn đề:

- Một key chung đại diện cho mọi caller.
- Không có client/tenant identity được mô hình hóa rõ.
- Không kiểm tra permission cho action document:read.
- Không kiểm tra quyền trên document.
- Không xử lý expiry, revoke, rotation hoặc audit.
- So sánh key theo cách không phù hợp cho secret.
- Có thể trả document của tenant khác nếu ID hợp lệ.

### 9.2. Xác thực key thành service principal

Ví dụ dưới đây minh họa ý tưởng: filter xác minh key qua service quản lý credential và tạo principal đã được xác thực. Đây không phải implementation hoàn chỉnh cho mọi hệ thống; cần bổ sung exception handling, dependency injection và mapping authority theo framework/version thực tế.

~~~java
public class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    private final ApiKeyService apiKeyService;
    private final AuthenticationEntryPoint authenticationEntryPoint;

    public ApiKeyAuthenticationFilter(
            ApiKeyService apiKeyService,
            AuthenticationEntryPoint authenticationEntryPoint) {
        this.apiKeyService = apiKeyService;
        this.authenticationEntryPoint = authenticationEntryPoint;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String rawKey = request.getHeader("X-API-Key");

        if (rawKey == null || rawKey.isBlank()) {
            chain.doFilter(request, response);
            return;
        }

        try {
            ApiClientPrincipal principal = apiKeyService.authenticate(rawKey);

            var authentication =
                new UsernamePasswordAuthenticationToken(
                    principal,
                    null,
                    principal.authorities()
                );

            SecurityContextHolder.getContext()
                .setAuthentication(authentication);
        } catch (AuthenticationException ex) {
            SecurityContextHolder.clearContext();
            authenticationEntryPoint.commence(request, response, ex);
            return;
        }

        chain.doFilter(request, response);
    }
}
~~~

Trong thực tế, ví dụ cần inject AuthenticationEntryPoint và cấu hình filter đúng vị trí trong Spring Security filter chain. apiKeyService.authenticate phải từ chối key sai, hết hạn, revoked hoặc sai environment/client binding bằng AuthenticationException. Nếu endpoint yêu cầu key mà key thiếu, authorization entry point phải trả 401; nếu key được gửi nhưng sai, không âm thầm fallback sang anonymous. Chỉ cho request không có key đi tiếp khi endpoint thực sự cho phép anonymous hoặc một scheme khác được chấp nhận.

Chỉ áp dụng filter cho route cần API key. Nếu một route hỗ trợ cả bearer token và API key, xác định rõ chúng là lựa chọn OR hay phải kết hợp; dùng request matcher/filter chain phù hợp hoặc một authentication provider xử lý semantics đó. Không để filter API key âm thầm ghi đè một user principal đã được bearer filter xác thực.

Không ghi raw key hoặc đưa key vào principal details. Principal chỉ nên chứa key ID, client ID, tenant binding và authorities cần thiết.

### 9.3. Kiểm tra scope và object trong service

~~~java
@Service
public class DocumentService {

    @PreAuthorize("hasAuthority('SCOPE_documents:read')")
    public Document read(
            UUID documentId,
            ApiClientPrincipal client,
            CurrentUserPrincipal user) {

        Document document = documentRepository
            .findVisibleTo(documentId, client.tenantId(), user.id())
            .orElseThrow(NotFoundException::new);

        documentAuthorization.requireCanRead(
            client, user, document);

        return document;
    }
}
~~~

Đây là ví dụ mô hình hóa cả client và user context. Không phải mọi service đều cần cả hai; nếu workload hoạt động hoàn toàn theo service identity, policy phải giới hạn resource theo service principal và tenant binding. Nếu hành động thay mặt user, user identity phải được xác minh bằng delegation chứ không nhận từ request body.

findVisibleTo nên áp dụng điều kiện tenant/relationship ở tầng truy vấn. requireCanRead kiểm tra policy bổ sung và không được thay bằng một boolean do frontend gửi.

### 9.4. Không tin tenant ID từ request

Không viết:

~~~java
String tenantId = request.getHeader("X-Tenant-Id");
return repository.findByTenantIdAndId(tenantId, documentId);
~~~

trừ khi header đó được một trusted gateway ghi đè, ký/xác minh và backend chỉ chấp nhận từ gateway trong trust boundary. Thông thường, tenant context phải lấy từ authenticated principal hoặc server-side binding. Client có thể gửi tenant selector để chọn context, nhưng server phải kiểm tra membership/authorization trước khi dùng.

## 10. Kết hợp API key với OAuth2, mTLS và request signing

Không có một scheme phù hợp cho mọi integration. Có thể kết hợp nhiều lớp khi threat model yêu cầu.

| Cơ chế | Nó giúp xác minh điều gì? | Giới hạn |
|---|---|---|
| API key | Client/integration đang dùng credential đã cấp | Static bearer secret có thể bị copy/replay |
| OAuth2 client credentials | Workload client được identity provider cấp token và scope | Không tự chứng minh user cuối hoặc quyền trên mọi object |
| OAuth2 delegated token | Hành động được gắn với user/delegation context | Vẫn cần object/business authorization |
| mTLS | Peer có client certificate được trust | Không tự quyết định quyền dữ liệu ở application |
| HMAC request signing | Request được ký bằng secret client, có thể ràng buộc method/path/body | Cần chống replay; không tự xác thực user |
| DPoP hoặc sender-constrained token | Token bị ràng buộc với key của client theo protocol | Cần hỗ trợ end-to-end và vẫn cần authorization |

### 10.1. HMAC signing

Nếu phải dùng HMAC, chữ ký nên ràng buộc các thành phần cần thiết như HTTP method, canonical path/query, timestamp, nonce và digest của body. Server phải canonicalize giống client, kiểm tra timestamp window và từ chối nonce đã dùng để giảm replay.

Không tự thiết kế protocol ký request sơ sài. Khác biệt canonicalization, encoding hoặc proxy rewrite có thể tạo lỗi xác minh. Dùng chuẩn/thư viện đã được đánh giá và test negative cases.

### 10.2. mTLS và workload identity

mTLS giúp xác thực service peer ở tầng transport. Sau khi xác minh certificate, gateway hoặc application phải map certificate identity sang workload principal và policy. Không coi mọi certificate do cùng CA cấp là có cùng quyền.

### 10.3. OAuth2 token không thay object authorization

Access token ngắn hạn có issuer, audience và scope giúp giảm thời gian sử dụng credential bị lộ và gắn identity rõ hơn. Nhưng token hợp lệ vẫn có thể được dùng sai nếu service không kiểm tra tenant/object/action. Không coi việc chuyển từ API key sang JWT là đã giải quyết BOLA.

## 11. Rate limit, quota và blast radius

Credential riêng giúp rate limit và audit tốt hơn, nhưng giới hạn cần đặt theo nhiều chiều:

- Per key/client để bảo vệ integration.
- Per user nếu thao tác đại diện user.
- Per tenant để nhiều key không nhân quota tenant.
- Per endpoint/action theo chi phí và độ nhạy cảm.
- Global guardrail để bảo vệ service và downstream.

Nếu một key bị lộ, giới hạn theo tenant, scope và object giúp thu hẹp tác động. Alert khi có bất thường như key sử dụng từ nhiều vùng/ASN không mong đợi, tốc độ tăng đột biến, truy cập object ngoài pattern, nhiều lỗi authorization hoặc gọi endpoint nhạy cảm lần đầu.

Không dùng rate limit thay authorization. Một attacker có thể đọc ít dữ liệu mỗi giờ nhưng vẫn đọc trái phép. Cần deny quyền trước khi xử lý dữ liệu và chỉ sau đó mới áp dụng quota/rate policy phù hợp.

## 12. Audit và giám sát

Audit log nên cho biết:

- Key ID/public identifier, client ID và workload/user principal.
- Tenant đã xác minh.
- Action và resource ID.
- Kết quả authentication và authorization.
- Reason code cho deny.
- Request ID, timestamp và nguồn kết nối theo policy.
- Key created/rotated/revoked và actor thực hiện.

Không log raw API key, Authorization header, token, HMAC signature hoặc request body nhạy cảm. Không ghi toàn bộ URL nếu có query signature. Dùng event metadata và identifier nội bộ để điều tra.

Giám sát các dấu hiệu:

- Key dùng từ nhiều IP/region bất thường.
- Key cũ đột nhiên hoạt động sau thời gian dài không dùng.
- Một integration tăng số lượng request hoặc bytes tải xuống đột ngột.
- Một key thử nhiều tenant/resource ID.
- Một key bắt đầu gọi endpoint admin/write ngoài hành vi thường ngày.
- Nhiều key trong cùng tenant cùng vượt quota.
- Key đã revoke vẫn xuất hiện trong traffic do cache hoặc replica chưa cập nhật.

Alert cần có runbook: xác định key record, revoke, rotate, kiểm tra log/trace và đánh giá dữ liệu đã truy cập.

## 13. Quy trình xử lý khi API key bị lộ

1. Xác định key ID, client, tenant, environment và scope liên quan.
2. Revoke key bị lộ; nếu nghi ngờ compromise ở cấp client, thu hồi toàn bộ credential của client đó.
3. Cấp key mới qua secret manager hoặc quy trình provisioning an toàn.
4. Kiểm tra request history, resource đã đọc/ghi, export và downstream side effect.
5. Xác định nơi key bị lộ: source control, frontend bundle, log, CI, support ticket hoặc máy đối tác.
6. Loại bỏ secret khỏi nơi lưu trữ và các bản sao theo quy trình; không chỉ xóa dòng hiển thị trên dashboard.
7. Kiểm tra cache/replica/gateway để bảo đảm revoke có hiệu lực trong thời gian cam kết.
8. Đánh giá dữ liệu cá nhân/tài chính bị truy cập và nghĩa vụ xử lý sự cố.
9. Bổ sung test và thay đổi quy trình để ngăn tái diễn.

Nếu key nằm trong git history, xóa file hiện tại không làm credential cũ biến mất khỏi lịch sử. Revoke/rotate trước, sau đó xử lý repository theo quy trình phù hợp. Không giả định secret chưa bị dùng chỉ vì chưa thấy alert.

## 14. Kiểm thử bảo mật cho API key và tài nguyên nhạy cảm

Dùng key giả và dữ liệu test trong local/staging. Test cả authentication, authorization, object isolation, lifecycle và logging.

| Nhóm test | Tình huống | Kết quả mong đợi |
|---|---|---|
| Missing key | Không gửi API key tới endpoint protected | 401 |
| Invalid key | Key không tồn tại hoặc secret sai | 401 |
| Expired key | Key quá hạn | 401 |
| Revoked key | Key đã thu hồi | 401 |
| Environment binding | Staging key gọi production | Từ chối |
| Scope | Key chỉ có read gọi write/approve | 403 |
| Object boundary | Key/client tenant A truy cập object tenant B | 403/404 theo policy |
| User delegation | Thay user ID trong body/path | Không đổi principal hoặc quyền |
| Shared key | Nhiều user dùng cùng client key | Audit vẫn phân biệt actor theo user token/delegation; nếu không có thì không được giả định có user identity |
| Key rotation | Key cũ và mới trong overlap đã định | Chỉ hoạt động theo thời hạn overlap |
| Revocation propagation | Revoke rồi gọi qua mọi replica/gateway | Bị từ chối trong SLA revoke |
| Rate limit | Một key vượt ngưỡng | 429; key/tenant khác không bị block nhầm |
| Query leakage | Gửi key trong query ở endpoint không hỗ trợ | Bị từ chối; key không xuất hiện trong log |
| Browser exposure | Tìm key trong JS bundle/source map | Không có production secret |
| Logging | Marker key trong request | Raw key không xuất hiện trong app/proxy/APM log |
| Gateway bypass | Gọi upstream trực tiếp trong test network | Bị chặn hoặc vẫn áp policy tương đương |
| HMAC replay | Gửi lại cùng nonce/request signature | Replay bị từ chối |
| Audit | Đọc/deny/rotate/revoke | Có event với key ID và actor, không có secret |
| Cross-operation | Key read-only gọi export/delete | Từ chối |

### 14.1. Kiểm tra BOLA dù key hợp lệ

Dùng hai tenant A/B, hai client principal và nhiều resource:

- Key của client A gọi document ID thuộc tenant A.
- Key của client A thay ID thành document thuộc tenant B.
- User A có scope read nhưng không phải member project chứa document.
- Client có scope read metadata nhưng gọi content/download.
- Client được quyền read nhưng thử update/delete.
- Tenant membership hoặc ACL bị revoke rồi gọi lại.
- Một export job tạo bởi client A chứa object tenant B.

Kết quả phải phản ánh object-level policy. Việc request có API key hợp lệ không được làm thay đổi kết quả của các kiểm tra này.

### 14.2. Kiểm tra key không bị lộ

Tạo test key marker như TEST_API_KEY_DO_NOT_LOG_4c82 và gửi qua các đường request phù hợp. Tìm marker trong:

- Application logs.
- Gateway/reverse proxy access logs.
- APM/tracing events.
- Exception messages.
- CI/build output.
- Error reporting và support artifacts.

Nếu marker xuất hiện ở bất kỳ sink nào, xử lý như secret exposure và sửa nơi thu thập.

## 15. Lộ trình chuyển khỏi anti-pattern

Nếu hệ thống đang dùng một API key chung cho tài nguyên nhạy cảm, chuyển đổi theo các bước:

1. **Inventory:** liệt kê consumer, key, endpoint, tenant, scope và loại dữ liệu được truy cập.
2. **Classify:** đánh dấu endpoint public, low-risk, sensitive và high-impact.
3. **Narrow:** thu hẹp key hiện có theo client, environment, scope, quota và resource constraints.
4. **Add identity:** bổ sung user identity hoặc workload identity phù hợp với loại caller.
5. **Enforce object policy:** kiểm tra tenant, owner, membership, ACL và action ở service/repository.
6. **Migrate consumers:** cấp credential mới, hỗ trợ overlap có thời hạn và thông báo thay đổi contract.
7. **Observe:** theo dõi key cũ, lỗi auth, usage và các consumer chưa migrate.
8. **Revoke:** thu hồi key chung sau khi xác minh consumer đã chuyển.
9. **Verify:** chạy negative tests, cross-tenant tests, revoke propagation và log scanning.

Không giữ key cũ vô thời hạn chỉ vì một consumer chưa migrate. Xác định owner và deadline cho từng integration; nếu cần ngoại lệ, giới hạn scope và tài nguyên rõ ràng.

## 16. Checklist trước khi phát hành

- [ ] API key được dùng để nhận diện client/integration, không tự động đại diện cho end user.
- [ ] Không nhúng production secret vào browser JavaScript, mobile binary hoặc public repository.
- [ ] Credential có key ID, secret entropy cao, expiry, rotation và revoke.
- [ ] Raw key không được lưu/log/hiển thị lại sau khi cấp.
- [ ] Key được gắn với client, tenant và environment phía server.
- [ ] Scope và quota lấy từ credential record đã xác minh, không lấy từ request.
- [ ] User-delegated action có user identity được xác minh.
- [ ] Mọi operation nhạy cảm có function authorization.
- [ ] Mọi resource riêng tư có object/tenant/relationship authorization.
- [ ] Business state và approval được kiểm tra trước side effect.
- [ ] Không dùng CORS như cơ chế bảo vệ API key.
- [ ] Key không truyền trong URL/query và không xuất hiện trong log/trace.
- [ ] Gateway và upstream không có đường bypass policy.
- [ ] Có rate limit theo key/client, user, tenant và global guardrail phù hợp.
- [ ] Có audit cho access, deny, key issue, rotation và revoke.
- [ ] Có test missing/invalid/expired/revoked key, scope, BOLA, cross-tenant, replay, logging và revoke propagation.
- [ ] Có lộ trình migration và deadline thu hồi key dùng chung.

API key là credential hữu ích để nhận diện client và kiểm soát mức sử dụng, nhưng possession of key không đồng nghĩa với quyền đọc mọi tài nguyên nhạy cảm. Hãy xác thực đúng user hoặc workload, giới hạn chức năng theo scope, kiểm tra tenant và quyền trên từng object, rồi áp dụng business rule trước khi trả dữ liệu hoặc tạo side effect. Khi API key được giữ ở đúng vai trò client credential và vòng đời của nó được quản lý chặt, hệ thống có thể tận dụng sự đơn giản của key mà không biến một secret bị lộ thành quyền truy cập toàn hệ thống.
