# Dùng user token vô thời hạn cho service

## 1. Vấn đề và bối cảnh

Một anti-pattern thường gặp trong hệ thống nhiều service là lấy access token hoặc refresh token của người dùng rồi lưu lại để một service tiếp tục sử dụng trong thời gian dài. Ban đầu, cách làm này có vẻ tiện: người dùng đăng nhập một lần, backend nhận token và các worker có thể gọi API thay người dùng mà không cần yêu cầu đăng nhập lại. Theo thời gian, token được đưa vào database, queue, biến môi trường, file cấu hình hoặc cache dùng chung; service tiếp tục gọi API ngay cả khi người dùng đã đăng xuất, đổi quyền hoặc không còn làm việc đó nữa.

**User token không phải credential vô thời hạn của service.** Access token đại diện cho một authorization context có subject, audience, scope và thời hạn. Refresh token có thể duy trì grant theo policy, nhưng nó vẫn là credential nhạy cảm gắn với client/session và phải có vòng đời, binding, lưu trữ, rotation và revocation rõ ràng. Giữ token của user để service sử dụng mãi làm mờ ranh giới giữa quyền của người dùng và danh tính của workload.

Bài học thuộc chương **Lỗi thường gặp** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**. Nội dung gắn với mô hình tin cậy và vòng đời token bảo mật, phân biệt JWT/opaque token, access/refresh token, xác thực và phân quyền OAuth 2.0/OIDC, issuer, claims, scope, audience, lưu trữ, thu hồi và phòng chống token bị đánh cắp hoặc phát lại.

Sau bài này, người học có thể:

1. Nhận diện việc dùng user token lâu dài như một lỗi thiết kế identity và authorization.
2. Phân biệt quyền của user, actor/service và workload identity.
3. Giải thích rủi ro khi kéo dài access token hoặc giữ refresh token vô thời hạn.
4. Chọn client credentials/workload identity, token exchange hoặc delegated job authorization phù hợp.
5. Thiết kế TTL, audience, scope, tenant, revocation, audit và secret storage cho service.
6. Di chuyển khỏi mô hình cũ và kiểm thử để chứng minh token không bị dùng sai ngữ cảnh.

## 2. Anti-pattern: biến token của user thành credential thường trực của service

Ví dụ: người dùng Alice đăng nhập Portal, backend nhận user access token và lưu token đó vào bảng `user_tokens`. Một worker chạy mỗi đêm đọc token này để gọi Billing API, Export API hoặc CRM API. Nếu token hết hạn, worker dùng refresh token đã lưu để xin access token mới rồi tiếp tục chạy.

~~~mermaid
flowchart TD
    U[User Alice đăng nhập] --> P[Portal nhận access token và refresh token]
    P --> DB[(Database lưu token của Alice)]
    DB --> W[Background worker chạy theo lịch]
    W --> AS[Authorization Server]
    AS -->|Refresh token của Alice| W
    W --> API[Billing / Export / CRM API]
    API --> D[Hành động dưới quyền Alice]
~~~

Mô hình này tạo ra nhiều câu hỏi khó trả lời:

- Alice đã đăng xuất hoặc bị khóa tài khoản, worker có tiếp tục chạy không?
- Alice đã bị thu hồi consent hoặc mất quyền vào tenant, token cache có được cập nhật không?
- Worker có cần toàn bộ quyền của Alice hay chỉ cần một quyền hẹp để hoàn thành job?
- Nếu database hoặc log bị lộ, kẻ tấn công có thể lấy token để hoạt động như Alice trong bao lâu?
- Audit ghi Alice là người thực hiện, nhưng workload thực tế là worker nào?
- Khi Alice rời tổ chức, ai tìm và thu hồi mọi token đã được lưu ở các service?

Nếu không có câu trả lời rõ ràng, hệ thống đang dùng danh tính người dùng làm credential lâu dài cho một workload.

### 2.1. Các dạng anti-pattern

| Biểu hiện | Vì sao nguy hiểm |
| --- | --- |
| Đặt access token có TTL rất dài để worker ít phải refresh | Mở rộng cửa sổ replay nếu token bị đánh cắp; khó phản ánh thay đổi quyền. |
| Lưu refresh token của user trong database dùng chung | Refresh token có thể tiếp tục duy trì grant và cấp access token mới. |
| Dùng một user token cho nhiều service | Mọi service chia sẻ quyền và khó phân biệt actor thực tế. |
| Dùng token của admin/service owner cho cron job | Một credential cá nhân có thể cấp quyền quá rộng và phụ thuộc vào vòng đời nhân sự. |
| Copy token vào queue, dead-letter queue hoặc file backup | Credential tồn tại ngoài nơi kiểm soát và có thể bị replay. |
| Không revoke token khi user logout hoặc đổi quyền | Service có thể tiếp tục hành động theo authorization context cũ. |
| Dùng refresh token để tự động gia hạn mãi mãi | Không có giới hạn rõ ràng cho phiên ủy quyền và không kiểm tra lại nhu cầu nghiệp vụ. |
| Ghi token vào log để debug worker | Log/APM trở thành nơi chứa bearer credential. |

## 3. Phân biệt subject, actor và workload identity

Để sửa anti-pattern, trước hết phải xác định ai đang được đại diện và ai thực sự thực hiện công việc.

- **Subject:** người dùng hoặc chủ thể mà quyền đang được đại diện, ví dụ `alice`.
- **Actor:** service/workload thực hiện hành động, ví dụ `monthly-export-worker`.
- **OAuth client:** client đã xác thực với authorization server để xin token.
- **Resource server:** API nhận access token và quyết định có cho phép hành động hay không.
- **Workload identity:** danh tính của ứng dụng đang chạy trong môi trường tin cậy, ví dụ service account, managed identity hoặc SPIFFE identity.

Trong một request đồng bộ, service có thể cần hành động thay người dùng. Khi đó token ngắn hạn có thể giữ subject của user và thể hiện actor theo policy. Trong một job chạy độc lập vào ban đêm, subject có thể là hệ thống hoặc một authorization grant riêng đã được cấp cho job. Hai trường hợp này không nên dùng chung một cơ chế chỉ vì đều cần gọi API.

| Nhu cầu | Danh tính phù hợp | Token/flow thường dùng |
| --- | --- | --- |
| Service đọc dữ liệu vận hành của chính nó | Workload/service identity | OAuth client credentials hoặc workload federation |
| Service xử lý request đang được user thực hiện | User subject + service actor | Token exchange/OBO hoặc delegation token ngắn hạn |
| Job được user lên lịch và chạy sau đó | Job identity/grant có giới hạn; lưu người yêu cầu như metadata | Job authorization riêng, workload identity và policy kiểm tra lại |
| Tác vụ quản trị hệ thống | Privileged workload identity có approval và scope riêng | Client credentials/workload identity với quyền đặc biệt được kiểm soát |
| Service gọi API công khai theo quyền của tenant | Workload identity gắn tenant authorization | Client credentials kết hợp policy tenant, hoặc token exchange theo profile |

Không suy ra actor từ header do caller tự gửi như `X-User`, `X-Service-Name` hoặc từ IP. Danh tính workload phải được xác thực bằng client authentication, mTLS, platform identity hoặc cơ chế tin cậy tương đương.

## 4. Vì sao dùng user token vô thời hạn là sai?

### 4.1. Vi phạm ranh giới vòng đời token

Access token được cấp cho một mục đích, audience, scope và thời hạn cụ thể. Khi service giữ token lâu hơn request/session ban đầu, token được dùng ngoài ngữ cảnh dự kiến. Token còn hạn không tự động có nghĩa user vẫn muốn hoặc vẫn được phép thực hiện hành động đó.

Refresh token thường có thời hạn dài hơn access token, nhưng không có nghĩa là vô hạn. Authorization server có thể áp dụng absolute lifetime, idle timeout, rotation, reuse detection, client binding, consent revocation và session policy. Dùng refresh token như một chìa khóa vĩnh viễn sẽ làm mất tác dụng của các giới hạn đó.

### 4.2. Mất khả năng phản ánh thay đổi quyền

Quyền user có thể thay đổi:

- User bị khóa hoặc rời tổ chức.
- User mất membership trong tenant/project.
- Admin thu hồi role hoặc consent.
- Quyền truy cập dữ liệu bị giảm.
- Session bị logout hoặc revoke sau sự cố.
- Chính sách bảo mật thay đổi, yêu cầu MFA hoặc xác thực lại.

Nếu service tiếp tục dùng token cũ, hành động có thể vẫn được chấp nhận cho tới khi token hết hạn hoặc hệ thống có cơ chế thu hồi hiệu lực. Với JWT được xác minh offline, resource server có thể không biết trạng thái revoke ngay lập tức.

### 4.3. Mở rộng blast radius khi token bị đánh cắp

Bearer token là credential: ai sở hữu token và đáp ứng điều kiện sử dụng có thể gửi request trong phạm vi token. Khi token của user được lưu trong database, backup, queue hoặc log, mỗi bản sao làm tăng nơi có thể bị lấy cắp. Một token có TTL dài hoặc refresh token có thể tiếp tục tạo access token mới, khiến thời gian lạm dụng kéo dài.

Nếu một user token được dùng bởi nhiều service, việc điều tra khó xác định service nào đã thực hiện request. Kẻ tấn công có thể tận dụng token để gọi API trực tiếp từ môi trường khác nếu token không được sender-constrain và resource server không kiểm actor/workload.

### 4.4. Audit sai chủ thể thực hiện

Nếu audit chỉ ghi `sub=alice`, báo cáo có thể khiến người đọc nghĩ Alice trực tiếp thao tác. Trên thực tế, một cron job hoặc worker đã thực hiện request. Khi xảy ra sự cố, tổ chức cần phân biệt:

- User đã yêu cầu hoặc phê duyệt hành động nào?
- Service/workload nào thực hiện?
- Job nào, lần chạy nào và phiên bản code nào?
- Authorization policy nào cho phép hành động?
- Hành động được thực hiện vào thời điểm nào?

Một audit record tốt giữ được subject reference, actor/workload identity, job/correlation ID và quyết định policy.

### 4.5. Tạo phụ thuộc availability không cần thiết

Service có thể ngừng hoạt động nếu user bị khóa, refresh token hết hạn, consent bị thu hồi hoặc client session thay đổi, dù công việc của service vẫn cần chạy theo hợp đồng nghiệp vụ. Ngược lại, nếu giữ token cũ để tránh gián đoạn, service có thể tiếp tục truy cập sau khi quyền user đã bị thu hồi.

Đây là dấu hiệu thiết kế lẫn lộn giữa **ủy quyền của user** và **quyền vận hành của workload**.

## 5. Access token dài hạn và refresh token vô hạn không phải giải pháp

### 5.1. Tăng TTL access token

Tăng `exp` để worker chạy lâu hơn chỉ kéo dài thời gian credential có thể bị sử dụng. Với JWT offline, việc thu hồi sớm cần thêm denylist, grant/session state hoặc cơ chế khác. Với opaque token, introspection có thể phản ánh trạng thái active, nhưng cache vẫn tạo độ trễ.

Access token nên có thời hạn phù hợp với độ nhạy của resource, khả năng refresh, latency và yêu cầu revocation. Không chọn TTL dài chỉ vì worker không muốn xử lý lỗi refresh.

### 5.2. Refresh token kéo dài mãi

Refresh token không phải credential dành cho resource server. Nó chỉ được gửi tới authorization server/token endpoint theo grant và client binding. Việc lưu refresh token trong service cần một quyết định authorization rõ ràng, client được phép, secure storage, rotation/reuse detection, expiry và revocation.

Nếu ứng dụng có một delegated refresh token theo thiết kế được phê duyệt, điều đó vẫn không biến nó thành credential của workload vô thời hạn. Phải xác định user consent, session lifetime, tenant, scope, client, nơi lưu và hành vi khi user bị disable hoặc revoke grant.

### 5.3. So sánh hành vi

| Thiết kế | Sau khi user logout/consent bị revoke | Rủi ro chính |
| --- | --- | --- |
| Access token ngắn hạn, không refresh | Token cũ hết hiệu lực theo exp hoặc cơ chế revoke | Cần xử lý job hết quyền và retry/reauthorization. |
| Access token rất dài | Có thể còn dùng được lâu, nhất là JWT offline | Cửa sổ replay lớn và thay đổi quyền chậm phản ánh. |
| Refresh token lưu lâu, refresh liên tục | Có thể tiếp tục xin access token nếu grant còn active | Rò refresh token cho phép duy trì truy cập; khó kiểm soát phiên. |
| Workload identity + scope hẹp | Không phụ thuộc session user cho tác vụ của service | Cần policy riêng và audit workload. |
| Delegation token ngắn hạn theo từng job/request | Giữ được subject/actor và giới hạn thời gian/quyền | Cần STS/policy hỗ trợ và kiểm tra lại authorization. |

## 6. Chọn mô hình thay thế

Không có một flow duy nhất cho mọi service. Chọn theo câu hỏi: **công việc đang thực hiện vì quyền của ai và ai chịu trách nhiệm thực hiện?**

### 6.1. Client credentials hoặc workload identity cho service-owned work

Nếu service thực hiện công việc của chính nó, dùng workload identity. OAuth 2.0 client credentials là lựa chọn phù hợp cho confidential client được phép dùng grant này. Platform có thể cấp identity ngắn hạn hoặc federated credential để giảm phụ thuộc vào static client secret.

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Background Worker
    participant AS as Authorization Server
    participant API as Resource Server

    W->>AS: Xác thực workload/client
    AS->>AS: Kiểm tra client policy, scope và resource
    AS-->>W: Service access token ngắn hạn
    W->>API: Request + service access token
    API->>API: Kiểm issuer, audience, scope và workload policy
    API-->>W: Response
~~~

Ví dụ scope có thể là `reports:generate` hoặc `inventory:read`, audience là API đích. Token đại diện service, không giả làm một user cụ thể. Resource server vẫn phải kiểm tra tenant/resource-level authorization theo ngữ cảnh công việc.

### 6.2. Token exchange/OBO cho công việc thực sự thay mặt user

Nếu service xử lý request của user và cần gọi downstream trong cùng ngữ cảnh, có thể dùng token exchange hoặc On-Behalf-Of (OBO) theo nền tảng hỗ trợ:

1. Resource server xác minh user access token đầu vào.
2. Service xác thực workload của chính nó với authorization server/STS.
3. Service yêu cầu token mới cho audience downstream và scope tối thiểu.
4. STS kiểm subject, actor/client, grant và policy.
5. Downstream xác minh token mới và kiểm tra quyền nghiệp vụ.

Token mới có thể giữ subject của user và biểu diễn actor/service theo profile. Token này nên có TTL ngắn, audience cụ thể và chỉ được dùng trong luồng đã được cấp. Không chuyển tiếp user token nguyên vẹn tới mọi downstream nếu audience không phù hợp.

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant O as Orders API
    participant STS as Token Exchange / STS
    participant I as Inventory API

    U->>O: Request + user access token
    O->>O: Verify issuer, audience, scope, user permission
    O->>STS: Subject token + workload authentication
    STS->>STS: Evaluate delegation policy
    STS-->>O: Short-lived token for Inventory
    O->>I: Request + exchanged token
    I->>I: Verify subject, actor, audience and scope
    I-->>O: Result
    O-->>U: Response
~~~

OBO là thuật ngữ được một số nền tảng sử dụng; cần tuân thủ profile và contract của authorization server cụ thể. RFC 8693 định nghĩa OAuth 2.0 Token Exchange, nhưng không tự cấp quyền delegation cho mọi client.

### 6.3. Job chạy sau khi user rời phiên

Đây là tình huống dễ thiết kế sai nhất. Ví dụ user yêu cầu xuất báo cáo, job được đưa vào queue và chạy sau 30 phút. Không nên giả định user access token ban đầu sẽ còn hợp lệ hoặc giữ refresh token vô thời hạn chỉ để job hoàn thành.

Hãy tách **yêu cầu nghiệp vụ** khỏi **credential thực thi**:

- Khi tạo job, lưu `requested_by`/subject reference, tenant, resource target, action, scope nghiệp vụ, thời điểm, correlation ID và trạng thái phê duyệt.
- Xác định policy cho phép job chạy sau khi user logout hay không.
- Khi worker thực thi, dùng workload identity để xác thực.
- Authorization service hoặc domain policy kiểm tra job grant còn hiệu lực, tenant còn hợp lệ, user/approver còn đủ quyền theo policy và action chưa bị hủy.
- Cấp service token hoặc delegation token ngắn hạn đúng audience/scope cho lần chạy.
- Audit cả người yêu cầu và workload thực thi.

Nếu nghiệp vụ yêu cầu quyền user phải còn hiệu lực tại thời điểm job chạy, worker cần kiểm tra lại authorization. Nếu nghiệp vụ ghi nhận một approval có hiệu lực tại thời điểm submit, hãy lưu approval record có thời hạn/phạm vi và để policy quyết định job còn được thực thi không. Không dùng một bearer token tồn tại lâu để thay thế quyết định nghiệp vụ đó.

### 6.4. Scheduled job định kỳ

Job chạy định kỳ như đồng bộ tồn kho, tổng hợp báo cáo hệ thống hoặc dọn dữ liệu thường là hoạt động do service sở hữu. Dùng workload identity với scope riêng. Nếu cần hành động theo tenant, gắn tenant context vào job và kiểm tra quyền tenant ở domain/API; không cần mượn token của một admin user làm credential.

## 7. Thiết kế quyền cho service token

Dù dùng client credentials hay token exchange, token phải có giới hạn rõ ràng:

1. **Issuer:** chỉ chấp nhận authorization server được tin cậy.
2. **Audience/resource:** chỉ API đích nhận token.
3. **Scope:** chỉ hành động cần cho job/request.
4. **Actor/client:** đúng workload được xác thực.
5. **Tenant/resource context:** chỉ dữ liệu trong phạm vi được phép.
6. **Lifetime:** đủ ngắn cho request/job hoặc lần chạy có giới hạn.
7. **Sender constraint:** cân nhắc mTLS/DPoP khi threat model yêu cầu.

Ví dụ token dành cho Inventory có thể chứa:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "inventory-sync-worker",
  "aud": ["inventory-api"],
  "scope": "inventory:read inventory:sync",
  "iat": 1893452400,
  "exp": 1893452700
}
~~~

Payload trên chỉ minh họa service identity. Với delegation token, sub có thể là user còn act thể hiện service; không tự giả định sub luôn là user hoặc luôn là workload. Cần tuân thủ token profile của issuer. Resource server phải xác minh chữ ký/introspection, issuer, audience, thời gian, scope và quyền dữ liệu.

Không cấp `aud=*`, `scope=admin` hoặc quyền truy cập mọi tenant để đơn giản hóa worker. Nếu một job cần nhiều API, ưu tiên token riêng theo từng audience hoặc exchange riêng cho từng downstream.

## 8. Lưu trữ token và dữ liệu job an toàn

### 8.1. Không đưa token vào queue hoặc business database

Queue nên mang dữ liệu nghiệp vụ tối thiểu:

~~~json
{
  "job_id": "job-91c2",
  "job_type": "monthly-report",
  "requested_by": "user-ref-42",
  "tenant_id": "tenant-17",
  "resource_id": "report-scope-2026-11",
  "requested_action": "report:generate",
  "approval_ref": "approval-71a8",
  "correlation_id": "trace-a190"
}
~~~

Thông điệp không cần chứa access_token, refresh_token, Authorization header hoặc client secret. Worker dùng workload identity để lấy token mới khi cần. Các trường subject/tenant vẫn phải được xác minh và ràng buộc với job record; không tin payload queue chỉ vì nó đến từ broker nội bộ.

### 8.2. Nếu buộc phải lưu delegated credential

Một số sản phẩm thực sự cần duy trì kết nối tới dịch vụ bên thứ ba theo user consent. Khi đó cần một thiết kế riêng:

- Lưu credential trong secret vault/encrypted token store, tách khỏi dữ liệu nghiệp vụ.
- Mã hóa bằng key được quản lý qua KMS/HSM; phân quyền truy cập theo workload.
- Ràng buộc với user, client, tenant, provider, scope và consent record.
- Dùng refresh token rotation/reuse detection nếu provider hỗ trợ.
- Đặt idle/absolute expiry và cơ chế re-consent.
- Revoke khi user disconnect, consent bị rút, account bị khóa hoặc incident xảy ra.
- Không chia sẻ credential giữa tenant/user.
- Audit việc đọc, refresh, revoke và lỗi; không ghi raw token.
- Có quy trình xóa credential và bản sao theo retention policy.

Đây là delegated integration credential được user cho phép theo một sản phẩm cụ thể, không phải cách biến user token thành danh tính mặc định cho mọi service.

## 9. Thu hồi, đăng xuất và thay đổi quyền

Thiết kế phải quy định điều gì xảy ra khi:

| Sự kiện | Hành vi mong muốn |
| --- | --- |
| User logout | Session/token theo policy được revoke; job đang chạy được xử lý theo semantics đã công bố. |
| User bị disable | Không cấp delegation token mới; job cần kiểm tra lại policy và dừng nếu không còn được phép. |
| User rời tenant | Từ chối thao tác trên tenant đó; không dựa vào claim cũ mà bỏ qua domain membership. |
| Consent bị revoke | Ngừng refresh/delegated access cho provider/resource liên quan. |
| Job bị cancel | Worker kiểm tra cancellation state trước các bước không thể đảo ngược. |
| Service bị compromise | Revoke workload credential, token/grant liên quan và điều tra hành động đã thực hiện. |
| Scope bị giảm | Token mới chỉ nhận scope còn được cấp; resource server áp dụng policy mới theo thiết kế. |

JWT được xác minh offline có thể còn hợp lệ đến exp nếu không có denylist, session/grant check hoặc cơ chế thu hồi khác. Opaque token qua introspection có thể phản ánh active=false, nhưng cache TTL và propagation cần được tính đến. Vì vậy, access token ngắn hạn và policy kiểm tra lại khi job chạy là biện pháp quan trọng.

## 10. Ví dụ Java/Spring: worker lấy service token

Ví dụ dưới đây là pseudocode theo phong cách Spring. Worker xác thực bằng workload identity/client authentication được cấu hình bên ngoài, nhận access token ngắn hạn và gọi API bằng token có scope riêng.

~~~java
public class InventoryWorker {
    private final OAuthServiceTokenProvider tokenProvider;
    private final WebClient inventoryClient;
    private final JobAuthorizationService jobAuthorization;

    public Mono<Void> run(Job job) {
        return jobAuthorization.authorizeExecution(
                job.requestedBy(),
                job.tenantId(),
                job.requestedAction(),
                job.approvalRef())
            .flatMap(authorization -> tokenProvider
                .getToken("inventory-api", "inventory:sync"))
            .flatMap(token -> inventoryClient.post()
                .uri("/tenants/{tenantId}/sync", job.tenantId())
                .headers(headers -> headers.setBearerAuth(token.value()))
                .bodyValue(new SyncRequest(job.resourceId(), job.jobId()))
                .retrieve()
                .bodyToMono(Void.class));
    }
}
~~~

`OAuthServiceTokenProvider` cần xác thực workload với authorization server bằng cơ chế được hỗ trợ (ví dụ client credentials, private_key_jwt, mTLS hoặc federation), cache token theo client/audience/scope/binding context và không log token. `JobAuthorizationService` là policy nghiệp vụ: nó xác minh job, tenant, approval và trạng thái thực thi. Đây là helper minh họa, không phải API có sẵn của Spring.

### 10.1. Ví dụ gọi downstream theo user delegation

Với request đồng bộ đang xử lý user, service có thể exchange token sau khi xác minh token đầu vào:

~~~java
public Mono<OrderInventory> getInventory(
        JwtAuthenticationToken authentication,
        String sku) {

    Jwt userJwt = authentication.getToken(); // Resource Server đã validate

    return delegationTokenClient.exchange(
            userJwt.getTokenValue(),
            "inventory-api",
            "inventory:read")
        .flatMap(delegatedToken -> inventoryClient.get()
            .uri("/items/{sku}", sku)
            .headers(h -> h.setBearerAuth(delegatedToken.value()))
            .retrieve()
            .bodyToMono(OrderInventory.class));
}
~~~

Ví dụ này giả định STS hỗ trợ token exchange/OBO và policy cho phép actor. Phải kiểm audience/scope của user token đầu vào, quyền user trên order, client authentication của service, target audience, scope được cấp và actor context. Không lưu `userJwt.getTokenValue()` để dùng cho các job tương lai.

## 11. Migration khỏi mô hình user token lâu dài

Không nên chỉ xóa token khỏi database rồi hy vọng worker tiếp tục hoạt động. Hãy di chuyển theo từng bước có thể kiểm chứng:

### Bước 1: Inventory nơi đang lưu và sử dụng token

Tìm access token/refresh token trong:

- Database, cache, object storage, file cấu hình và secret vault.
- Queue, retry topic, dead-letter queue và event snapshot.
- Environment variable, container image, deployment manifest và backup.
- Log, trace, APM, crash dump và CI artifact.
- Code path dùng token trong cron, scheduled task, worker và service-to-service call.

Không in giá trị token ra kết quả tìm kiếm hoặc ticket. Ghi nhận vị trí, owner, loại token, subject/client/tenant reference, scope, expiry và consumer.

### Bước 2: Phân loại công việc

Với từng luồng, xác định:

- Công việc thuộc về service hay đang thực hiện thay mặt user?
- Có cần user consent không?
- Có cần quyền user tại thời điểm chạy hay chỉ cần approval tại thời điểm submit?
- Job chạy đồng bộ hay bất đồng bộ?
- API downstream cần audience/scope nào?
- Khi user bị disable/cancel job thì expected behavior là gì?

### Bước 3: Chọn identity model

- Service-owned operation: workload identity/client credentials.
- Synchronous user delegation: token exchange/OBO ngắn hạn.
- Delayed job: job authorization record + workload identity, hoặc delegated job grant có TTL/consent/policy rõ.
- Third-party user integration: secure delegated credential store, rotation/revocation và re-consent.

### Bước 4: Triển khai và kiểm thử song song

Đưa identity model mới vào staging/canary. So sánh scope, audience, tenant, actor, latency và kết quả nghiệp vụ. Không chạy song song hai credential nếu chưa có cách tránh thao tác nghiệp vụ bị thực hiện hai lần; dùng idempotency key hoặc chế độ shadow chỉ đọc khi phù hợp.

### Bước 5: Ngừng cấp quyền cho mô hình cũ

Khi tất cả consumer đã chuyển:

- Ngừng lưu token mới theo cách cũ.
- Revoke refresh token/grant cũ theo policy.
- Xóa bản sao token khỏi queue, cache, database và backup theo retention/incident policy.
- Xử lý log/artifact có token bị lộ theo quy trình bảo mật.
- Thu hồi quyền client/service account cũ nếu không còn cần.
- Chạy negative test chứng minh token cũ không được dùng lại.

### Bước 6: Theo dõi sau migration

Theo dõi lỗi invalid_grant, invalid_client, 401/403, job bị từ chối do policy, token exchange failure và workload token issuance. Kiểm tra audit cho thấy actor đúng, subject/tenant đúng và scope không bị mở rộng.

## 12. Test matrix

| ID | Tình huống | Kiểm tra | Kết quả mong đợi |
| --- | --- | --- | --- |
| UT-001 | User token dùng cho request đồng bộ | Token có issuer/audience/scope hợp lệ | Request được xử lý trong ngữ cảnh user đã xác minh. |
| UT-002 | User token hết hạn | Gửi token đã hết hạn | Service từ chối; không dùng token cũ hoặc tự refresh ngoài policy. |
| UT-003 | User logout | Revoke session/grant rồi thử tạo delegation token | Không cấp delegation token mới theo policy. |
| UT-004 | User bị disable | Worker chạy job của user đã disable | Job bị chặn nếu policy yêu cầu user còn active. |
| UT-005 | Tenant membership bị thu hồi | Job dùng tenant cũ | Domain authorization từ chối. |
| UT-006 | Workload identity hợp lệ | Worker lấy service token | Token có đúng workload identity, audience và scope. |
| UT-007 | Workload identity sai | Dùng credential của service khác | Authorization server từ chối. |
| UT-008 | Service token sai audience | Token cho Orders gửi tới Inventory | Inventory từ chối. |
| UT-009 | Scope vượt quyền | Worker xin scope admin | STS từ chối hoặc chỉ cấp phần policy cho phép. |
| UT-010 | Delegation actor không được phép | Service exchange token thay user nhưng actor không được policy cho phép | STS từ chối. |
| UT-011 | Token exchange đúng | Subject token hợp lệ, actor được phép, target đúng | Token ngắn hạn có subject/actor context theo profile. |
| UT-012 | Forward user token nguyên vẹn | Gửi token có audience khác tới downstream | Downstream từ chối; service phải exchange theo policy. |
| UT-013 | Queue message chứa credential | Kiểm tra schema job/event | Không có access/refresh token hoặc Authorization header. |
| UT-014 | Job chạy sau logout | Kiểm tra policy đã công bố | Job tiếp tục hoặc bị hủy đúng theo job authorization, không phụ thuộc token user bị giữ lại. |
| UT-015 | Job bị cancel | Worker nhận cancellation trước bước ghi dữ liệu | Không thực hiện bước không thể đảo ngược sau khi cancel được xác nhận. |
| UT-016 | Refresh token reuse | Dùng lại refresh token đã rotation | Bị từ chối/reuse detection theo policy. |
| UT-017 | Consent bị revoke | Worker thử delegated refresh | Không cấp token mới; dừng integration theo policy. |
| UT-018 | Token bị lộ trong log | Scan log/APM/trace/test artifact | Không có raw token hoặc credential. |
| UT-019 | Cache key sai | Cùng subject nhưng khác actor/tenant/audience | Không dùng chung token từ context khác. |
| UT-020 | JWT revoke propagation | Revoke grant rồi gửi JWT cũ | Kết quả phù hợp cơ chế offline/denylist/session check đã thiết kế. |
| UT-021 | Opaque introspection inactive | Token bị revoke | Resource server từ chối khi introspection trả inactive, xét cache TTL. |
| UT-022 | Worker scale-out | Replica mới khởi động | Lấy workload identity/token mới theo policy; không đọc user token dùng chung. |
| UT-023 | Audit attribution | Worker thực hiện job thay mặt Alice | Audit ghi cả requester/subject và actor/job identity. |
| UT-024 | Secret rotation | Workload credential được rotate | Replica mới dùng credential mới; credential cũ bị từ chối sau revoke. |
| UT-025 | Job retry | Worker retry cùng job | Idempotency và authorization được kiểm tra; không tạo hành động trùng ngoài ý muốn. |
| UT-026 | Token provider unavailable | Authorization server tạm thời không truy cập được | Fail theo policy, retry giới hạn; không fallback sang user token cũ vô thời hạn. |

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng token của admin làm service credential | Quyền quá rộng, audit sai chủ thể | Cấp workload identity riêng và scope tối thiểu. |
| Giữ refresh token của user trong database | Duy trì quyền user ngoài phiên dự kiến | Chuyển sang workload identity hoặc delegated grant có TTL/consent rõ. |
| Tăng access token TTL để worker không phải refresh | Tăng cửa sổ replay và độ trễ revocation | Dùng access token ngắn hạn, refresh theo policy của workload. |
| Dùng cùng user token cho nhiều downstream | Sai audience và khó truy actor | Exchange token theo từng resource server. |
| Dùng client credentials cho hành động cần quyền user mà không kiểm domain policy | Service có thể truy cập dữ liệu vượt quyền user | Kết hợp tenant/resource authorization hoặc delegation phù hợp. |
| Hủy token nhưng quên job đã queue | Job có thể tiếp tục bằng credential lưu sẵn | Job authorization và cancellation state phải độc lập token. |
| Lưu token trong queue/DLQ | Token bị sao chép và tồn tại lâu | Chỉ gửi job reference; worker tự lấy token lúc chạy. |
| Audit chỉ ghi subject | Không xác định service thực hiện | Ghi subject, actor, workload, job ID và correlation ID. |
| Cache token chỉ theo user ID | Lẫn tenant, actor, scope và audience | Cache key theo đầy đủ authorization context hoặc không cache. |
| Revoke refresh token nhưng giả định JWT cũ lập tức mất hiệu lực | Resource server offline có thể còn chấp nhận tới exp | Kiểm tra cơ chế revoke access token và propagation riêng. |

## 14. Checklist thiết kế đúng

- [ ] Xác định rõ công việc thuộc về service hay đang thực hiện thay mặt user.
- [ ] Tách subject, actor, OAuth client và workload identity.
- [ ] Không dùng access token hoặc refresh token của user làm credential thường trực cho service.
- [ ] Dùng workload identity/client credentials cho service-owned operation.
- [ ] Dùng token exchange/OBO ngắn hạn cho request thực sự cần user delegation.
- [ ] Với job bất đồng bộ, lưu job authorization/approval reference thay vì bearer token.
- [ ] Xác minh tenant, resource, scope và trạng thái quyền tại thời điểm chạy theo policy.
- [ ] Giới hạn audience, scope, TTL và actor cho từng downstream.
- [ ] Bảo vệ delegated credential nếu sản phẩm thật sự cần lưu; có rotation, revocation, re-consent và retention.
- [ ] Không đưa token vào queue, log, trace, database nghiệp vụ hoặc image.
- [ ] Audit được cả requester/subject và actor/workload/job.
- [ ] Kiểm thử logout, user disable, tenant change, consent revoke, replay và token leakage.
- [ ] Có migration plan, cleanup và negative test cho token cũ.

## 15. Kết luận và tài liệu tham khảo

Dùng user token vô thời hạn cho service là lỗi thiết kế vì nó biến quyền của một người dùng thành credential vận hành lâu dài của workload. Access token có audience, scope và expiry; refresh token có client binding, rotation, expiry và revocation. Giữ chúng lâu hơn ngữ cảnh ban đầu làm tăng nguy cơ replay, giữ quyền cũ sau khi user thay đổi trạng thái và khiến audit không xác định được actor thực sự.

Hãy chọn identity theo loại công việc: workload identity/client credentials cho hoạt động của service; token exchange/OBO ngắn hạn cho request cần hành động thay user; job authorization riêng cho tác vụ bất đồng bộ. Khi đó, user vẫn có thể là requester hoặc subject được đại diện, còn workload được xác thực và audit như actor thực hiện công việc.

Tài liệu tiêu chuẩn liên quan:

- **RFC 6749 — OAuth 2.0 Authorization Framework:** access token, refresh token, client authentication và client credentials grant.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** sử dụng bearer access token và rủi ro khi token bị lộ.
- **RFC 7009 — OAuth 2.0 Token Revocation:** thu hồi token và giới hạn của hành vi revocation.
- **RFC 7662 — OAuth 2.0 Token Introspection:** kiểm tra trạng thái opaque token.
- **RFC 8693 — OAuth 2.0 Token Exchange:** trao đổi token, subject và actor trong delegation.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** xác thực workload bằng mTLS và token binding.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** khuyến nghị bảo vệ access token, refresh token và authorization flow.
- **OpenID Connect Core:** ID token, session và ngữ cảnh xác thực người dùng.
