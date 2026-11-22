# Chọn mô hình một issuer hoặc nhiều issuer cho các tenant

## 1. Bối cảnh và mục tiêu

Trong một **OAuth 2.0/OpenID Connect Authorization Server** dùng **Spring Security**, **Spring Authorization Server** và **Spring Boot**, nhiều tổ chức có thể cùng sử dụng một nền tảng đăng nhập nhưng vẫn cần tách client, người dùng, chính sách, khóa ký và dữ liệu authorization. Kiến trúc này thường được gọi là multi-tenancy.

Một quyết định nền tảng khi thiết kế Authorization Server đa tenant là chọn:

- **Một issuer dùng chung:** mọi tenant dùng cùng một OpenID Provider (OP) identity và cùng giá trị issuer. Tenant được phân biệt bằng ngữ cảnh, client, claim hoặc dữ liệu authorization.
- **Một issuer cho mỗi tenant:** mỗi tenant có issuer identifier riêng. Mỗi issuer là một OP identity độc lập về mặt giao thức, dù có thể cùng chạy trên một deployment và chia sẻ hạ tầng.

Đây không chỉ là quyết định về URL. Issuer ảnh hưởng tới discovery metadata, giá trị `iss` trong token, cách client xác minh ID Token, cách Resource Server xác minh access token, key set, client registry, consent, logout, cache và vận hành.

Ví dụ xuyên suốt: nền tảng `login.example.com` phục vụ ba tenant là Acme, Fabrikam và Northwind. Cả ba tenant có thể dùng chung giao diện đăng nhập, nhưng Acme yêu cầu khóa ký riêng và issuer riêng để liên kết với hệ thống federation của họ. Fabrikam và Northwind chỉ cần phân tách dữ liệu và quyền truy cập trong cùng một trust domain.

Sau bài học, bạn có thể:

1. Phân biệt issuer identifier với tenant ID, client ID và domain đăng nhập.
2. So sánh mô hình một issuer dùng chung với nhiều issuer theo tenant.
3. Chọn mô hình dựa trên trust boundary, federation, key management, compliance và chi phí vận hành.
4. Thiết kế tenant resolution từ hostname/path một cách an toàn.
5. Bảo đảm discovery metadata, endpoint và claim `iss` nhất quán.
6. Phân tách RegisteredClient, authorization, consent, signing key và persistence theo tenant.
7. Hiểu giới hạn cấu hình issuer tĩnh của Spring Authorization Server và phần mở rộng cần thiết cho nhiều issuer.
8. Thiết kế Resource Server tin cậy đúng danh sách issuer.
9. Lập kế hoạch chuyển đổi issuer mà không làm hỏng token đang lưu hành.
10. Kiểm thử lỗi định tuyến tenant, truy cập chéo tenant và rò rỉ dữ liệu.

**Phạm vi phiên bản:** Ví dụ tham chiếu Spring Authorization Server 1.5.8 và Spring Security 6.x. Framework cung cấp các core service và cấu hình issuer; việc định tuyến nhiều tenant/issuer là trách nhiệm kiến trúc của ứng dụng. Một bean cấu hình issuer tĩnh không tự biến Authorization Server thành multi-issuer server.

## 2. Issuer là gì và vì sao quyết định này quan trọng?

### 2.1. Issuer xác định một OpenID Provider

Issuer identifier là định danh URL của OpenID Provider. Nó xuất hiện trong:

- Trường `issuer` của OpenID Provider Discovery metadata.
- Claim `iss` trong ID Token.
- Claim `iss` trong JWT access token nếu Authorization Server phát hành access token dạng JWT.
- Cấu hình tin cậy của OIDC client và OAuth 2.0 Resource Server.
- Cách client tìm discovery document và JWKS endpoint.

Ví dụ một issuer:

~~~text
https://login.example.com
~~~

Issuer không phải tên tenant, tenant ID hay client ID. Hai tenant có thể có tenant ID khác nhau nhưng vẫn dùng chung một issuer. Ngược lại, hai issuer có thể cùng phục vụ một tenant nếu kiến trúc có nhiều OP identity cho các môi trường hoặc vùng độc lập.

### 2.2. Giá trị iss phải nhất quán

Client và Resource Server xác minh issuer theo giá trị đã tin cậy. Giá trị `iss` trong token phải khớp chính xác issuer mà client/Resource Server đã cấu hình hoặc đã lấy từ discovery metadata.

Ví dụ:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-8f2a",
  "aud": "orders-api",
  "tenant_id": "acme"
}
~~~

Trong ví dụ này, `iss` xác định OP dùng chung; `tenant_id` là claim ứng dụng biểu diễn tenant. Claim `tenant_id` không thay thế việc xác minh issuer, chữ ký, audience và thời hạn token.

Không tạo token có `iss=https://login.example.com/acme` nếu discovery metadata của client công bố issuer là `https://login.example.com`. Sự không nhất quán làm token validation thất bại hoặc tạo điều kiện cho lỗi cấu hình trust.

### 2.3. Issuer là trust boundary ở tầng giao thức

Một issuer riêng giúp client và Resource Server nhận biết token được phát hành bởi OP nào. Nhưng issuer riêng **không tự động bảo đảm** dữ liệu, database, signing key hoặc tiến trình được cách ly vật lý.

Ví dụ hai issuer:

~~~text
https://acme.login.example.com
https://fabrikam.login.example.com
~~~

Chúng có thể dùng hai database riêng và hai HSM key riêng, hoặc vẫn dùng chung PostgreSQL với cột tenant ID và cùng một application process. Mức cô lập thực tế phụ thuộc thiết kế storage, key management, runtime và quyền vận hành.

### 2.4. Không đồng nhất domain đăng nhập với issuer

Một nền tảng có thể dùng:

- Một domain đăng nhập chung nhưng nhiều issuer.
- Nhiều custom domain nhưng một issuer canonical.
- Một issuer chung và chuyển tenant sau khi người dùng đăng nhập.

Điều quan trọng là discovery document, endpoint, ID Token và access token phải nhất quán với issuer đã công bố. Không suy luận issuer chỉ từ hostname request mà không kiểm tra hostname đó thuộc tenant nào.

### 2.5. Quy tắc định dạng và tính ổn định của issuer

Issuer identifier trong OpenID Connect là URL dùng HTTPS. Giá trị này không được chứa query hoặc fragment; nên chọn URL canonical ổn định và giữ nguyên cách biểu diễn trong discovery metadata và token. Các biến thể chỉ khác dấu `/` cuối, hostname alias hoặc scheme có thể bị client so sánh như những issuer khác nhau.

Không đổi issuer theo mỗi lần đăng nhập, theo tenant label có thể đổi tên hoặc theo hostname do request tự cung cấp. Nếu tenant đổi tên hiển thị, giữ issuer identifier cũ; thay đổi issuer URL phải được xử lý như migration giao thức.

## 3. Hai mô hình kiến trúc

### 3.1. Một issuer dùng chung cho mọi tenant

Ví dụ:

~~~text
Issuer: https://login.example.com

Tenant Acme      -> tenant_id=acme
Tenant Fabrikam  -> tenant_id=fabrikam
Tenant Northwind -> tenant_id=northwind
~~~

Tất cả client dùng cùng discovery document. Token có cùng issuer; tenant được ràng buộc bằng tenant context, client policy và claim.

~~~mermaid
flowchart TD
    A["Tenant Acme"] --> D["Shared Authorization Server"]
    B["Tenant Fabrikam"] --> D
    C["Tenant Northwind"] --> D
    D --> E["Issuer: login.example.com"]
    E --> F["Shared discovery and JWKS"]
    E --> G["Tenant-aware client / authorization policy"]
    G --> H[("Tenant-partitioned storage")]
    G --> I["Tokens with tenant context"]
~~~

Đặc điểm:

- Một issuer identifier và một discovery document.
- Có thể dùng chung signing key set.
- Client registry và authorization store phải xác định tenant context khi cần phân tách.
- Resource Server xác minh một issuer và tiếp tục kiểm tra tenant claim/authorization.
- Dễ vận hành discovery và tích hợp client.

Mô hình phù hợp khi các tenant thuộc cùng trust domain, chia sẻ policy nền tảng và không cần federation identity riêng.

### 3.2. Một issuer cho mỗi tenant

Ví dụ:

~~~text
Tenant Acme:
  https://acme.login.example.com

Tenant Fabrikam:
  https://fabrikam.login.example.com

Tenant Northwind:
  https://northwind.login.example.com
~~~

Mỗi tenant có issuer identifier riêng. Discovery metadata, token issuer và trust configuration của client/Resource Server được xác định theo tenant.

~~~mermaid
flowchart TD
    A["Tenant Acme"] --> D["Tenant routing"]
    B["Tenant Fabrikam"] --> D
    C["Tenant Northwind"] --> D
    D --> E["Acme issuer context"]
    D --> F["Fabrikam issuer context"]
    D --> G["Northwind issuer context"]
    E --> H["Acme discovery / JWKS / keys"]
    F --> I["Fabrikam discovery / JWKS / keys"]
    G --> J["Northwind discovery / JWKS / keys"]
    H --> K[("Tenant-scoped persistence")]
    I --> K
    J --> K
~~~

Đặc điểm:

- Mỗi tenant có issuer identifier và discovery metadata riêng.
- Có thể có key set, signing key, client registry, consent và policy riêng.
- Client có thể trust một tenant cụ thể thay vì trust toàn bộ OP dùng chung.
- Resource Server phải xác minh issuer nằm trong allow-list.
- Vận hành phức tạp hơn do quản lý nhiều issuer, endpoint, key rotation và discovery.

Mô hình phù hợp khi tenant có trust domain, federation, key ownership, compliance hoặc vòng đời độc lập.

### 3.3. Nhiều issuer không nhất thiết là nhiều deployment

Có ba cách triển khai thường gặp:

| Cách triển khai | Đặc điểm | Độ phức tạp |
| --- | --- | --- |
| Một deployment, một issuer | Một bộ cấu hình Authorization Server dùng chung. | Thấp |
| Một deployment, nhiều issuer | Request được định tuyến vào tenant-specific issuer context và service. | Cao |
| Nhiều deployment, mỗi deployment một issuer | Mỗi tenant hoặc nhóm tenant có cấu hình và runtime riêng. | Vận hành hạ tầng cao hơn, ranh giới rõ hơn |

Không có yêu cầu một issuer phải chạy trên một máy chủ riêng. Issuer là identity ở tầng protocol; deployment là cách tổ chức runtime.

## 4. Chọn mô hình theo yêu cầu

### 4.1. Bảng quyết định

| Tiêu chí | Một issuer dùng chung | Một issuer mỗi tenant |
| --- | --- | --- |
| Trust domain | Các tenant tin cùng một OP. | Mỗi tenant có thể có trust relationship riêng. |
| Discovery | Một metadata document. | Metadata riêng cho từng issuer. |
| Client registration | Có thể dùng chung registry, cần tenant scoping. | Registry riêng hoặc namespace theo issuer. |
| Signing key | Có thể dùng chung key set. | Có thể tách key set và quyền quản lý key. |
| Token issuer | Cùng `iss`; tenant được biểu diễn thêm trong claims/context. | `iss` khác nhau theo tenant. |
| Resource Server | Một issuer validator và tenant authorization. | Allow-list hoặc resolver nhiều issuer. |
| Federation | Một cấu hình OP chung, policy theo tenant. | Federation endpoint/policy độc lập dễ thể hiện hơn. |
| Custom domain | Có thể dùng domain chung hoặc alias. | Có thể có issuer hostname riêng theo tenant. |
| Compliance | Phù hợp khi chấp nhận chung trust boundary. | Hỗ trợ tách biệt logic issuer; physical isolation vẫn phải thiết kế riêng. |
| Key rotation | Thường điều phối chung. | Có thể rotate theo tenant. |
| Vận hành | Ít metadata, key và endpoint hơn. | Nhiều issuer và cấu hình cần quản lý. |
| Tenant onboarding/offboarding | Thường là tạo/cấu hình tenant trong một OP. | Cần tạo/retire issuer và trust configuration tương ứng. |
| Blast radius | Lỗi key/policy chung có thể ảnh hưởng mọi tenant. | Có thể giới hạn theo issuer nếu hạ tầng cũng tách phù hợp. |

### 4.2. Chọn một issuer khi

Một issuer thường là lựa chọn hợp lý nếu:

- Tất cả tenant thuộc cùng tổ chức hoặc cùng trust domain.
- Client có thể xác định tenant từ tenant context, domain nghiệp vụ hoặc client registration.
- Không cần tenant sở hữu issuer identifier riêng.
- Key management và signing policy có thể được quản lý tập trung.
- Discovery, federation và onboarding nên thống nhất.
- Resource Server có thể kiểm tra tenant claim và quyền truy cập sau khi xác minh token.

Ví dụ: một SaaS quản lý đơn hàng có nhiều doanh nghiệp. Tất cả doanh nghiệp đăng nhập qua cùng nền tảng, dùng cùng OP identity và cùng chính sách MFA. Token mang `tenant_id`, còn API kiểm tra người dùng có quyền trên tenant được yêu cầu.

### 4.3. Chọn nhiều issuer khi

Issuer riêng theo tenant phù hợp nếu:

- Tenant cần trust relationship/federation độc lập với OP.
- Tenant yêu cầu issuer URL riêng trong cấu hình OIDC client.
- Tenant cần signing key do họ kiểm soát hoặc key rotation độc lập.
- Tenant có chính sách authentication, token lifetime hoặc consent khác biệt đáng kể.
- Một tenant cần offboard/retire trust mà không ảnh hưởng issuer của tenant khác.
- Các hệ thống downstream phân biệt tenant bằng issuer và không thể chỉ dựa vào claim.
- Quy định hợp đồng/compliance yêu cầu issuer identity tách biệt.

Ví dụ: Acme yêu cầu issuer riêng để cấu hình enterprise federation, đưa public key vào trust store riêng và chỉ chấp nhận token có `iss` của Acme.

### 4.4. Không dùng nhiều issuer chỉ để thay tenant claim

Nếu tất cả tenant vẫn dùng cùng policy, cùng key, cùng client registry và cùng trust relationship, tạo issuer riêng có thể tăng đáng kể chi phí:

- Discovery metadata và JWKS phải phục vụ riêng.
- Client và Resource Server phải cấu hình nhiều issuer.
- Monitoring, key rotation và incident response phức tạp hơn.
- Mỗi issuer có thể cần dữ liệu client/authorization riêng.

Nếu yêu cầu chỉ là phân biệt tenant trong nghiệp vụ, tenant claim cùng authorization policy thường đơn giản hơn.

### 4.5. Không dùng một issuer nếu cần trust isolation thực sự

Ngược lại, nếu tenant yêu cầu trust store riêng, signing key riêng, federation metadata riêng và khả năng thu hồi trust độc lập, chỉ thêm `tenant_id` vào token có thể không đáp ứng yêu cầu. Khi đó cần nhiều issuer hoặc deployment tách biệt theo mức cô lập đã cam kết.

## 5. Mô hình một issuer: thiết kế tenant context

### 5.1. Tenant context phải được xác định trước khi xử lý protocol

Với một issuer chung, server cần xác định tenant trong từng request để áp dụng đúng:

- Danh sách client được phép.
- Chính sách đăng nhập và MFA.
- Consent và quyền người dùng.
- Tenant claim đưa vào token.
- Branding hoặc giao diện đăng nhập.
- Giới hạn rate, quota và audit.

Tenant context phải có trước khi endpoint xác thực client, đọc authorization hoặc tạo token. Không đợi đến lúc thêm claim rồi mới xác định tenant.

### 5.2. Nguồn xác định tenant

| Nguồn | Cách dùng | Rủi ro/cách kiểm soát |
| --- | --- | --- |
| Hostname đã đăng ký | `acme.login.example.com` ánh xạ tới tenant Acme. | Chỉ tin host sau proxy normalization và allow-list. |
| Path cố định | `/t/acme/oauth2/authorize`. | Chuẩn hóa path, chặn path traversal và route ambiguity. |
| Client registration | Client ID thuộc một tenant đã xác định. | Client lookup phải tenant-aware; không chỉ tin client ID do caller gửi. |
| User membership | Người dùng chọn tenant sau login. | Kiểm tra membership và quyền chuyển tenant. |
| Trusted gateway assertion | Gateway nội bộ truyền tenant context đã ký/xác thực. | Chỉ tin header từ gateway được xác thực; strip header do client gửi. |

Không lấy tenant trực tiếp từ query parameter như `?tenant=acme` rồi dùng ngay cho persistence lookup. Query parameter có thể là một gợi ý UI, nhưng server phải kiểm tra tenant được phép theo host, client, user hoặc trusted routing policy.

### 5.3. Hostname và forwarded headers

Nếu dùng hostname:

1. Dùng allow-list ánh xạ hostname canonical sang tenant ID.
2. Reverse proxy phải xóa `Forwarded`/`X-Forwarded-Host` do client tự gửi và đặt giá trị đáng tin.
3. Chỉ tin forwarded header từ proxy/gateway được xác thực.
4. Chuẩn hóa hostname, port, trailing dot và chữ hoa/thường theo một quy tắc.
5. Unknown host phải bị từ chối; không fallback về tenant mặc định.
6. Không tạo issuer tùy ý bằng cách nối chuỗi từ Host header.

Nếu attacker có thể điều khiển hostname dùng để tạo issuer, Authorization Server có nguy cơ phát hành token với issuer không được client mong đợi hoặc công bố endpoint sai.

### 5.4. Tenant context phải được giới hạn theo request

Ví dụ mô hình:

~~~java
public record TenantContext(
    String tenantId,
    String issuer,
    TenantPolicy policy
) {}
~~~

Filter resolve tenant từ request đã được chuẩn hóa:

~~~java
TenantContext tenant = tenantResolver.resolve(request);
if (tenant == null) {
    response.sendError(404);
    return;
}

try (TenantContextScope ignored = tenantContext.bind(tenant)) {
    filterChain.doFilter(request, response);
}
~~~

Đây là pseudocode. `TenantContextScope` cần bảo đảm context được clear trong `close()`/`finally`, kể cả khi authentication thất bại hoặc downstream ném exception. Nếu xử lý async, executor hoặc reactive flow, phải truyền context theo cơ chế tương ứng; không dựa vào ThreadLocal đơn thuần.

### 5.5. Tenant claim và authorization

Với một issuer chung, token có thể chứa:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant_id": "acme",
  "scope": "orders.read"
}
~~~

Resource Server cần kiểm tra:

- Chữ ký và issuer hợp lệ.
- Audience có chứa API đích.
- Token chưa hết hạn và chưa bị revoke theo cơ chế mà API sử dụng.
- Tenant claim có giá trị hợp lệ.
- Principal có quyền trên tenant được yêu cầu.
- Resource được truy cập thuộc tenant tương ứng.

Không coi `tenant_id` là quyền truy cập tự thân. Claim chỉ cho biết token được phát hành trong tenant context nào; API vẫn phải kiểm tra authorization và tenant boundary ở từng thao tác dữ liệu.

### 5.6. Tenant context phải ràng buộc với client và user

Trong một issuer chung, client ID có thể được dùng trên toàn hệ thống hoặc chỉ trong một tenant. Nếu client ID chỉ duy nhất trong tenant, repository phải lookup theo cặp `(tenant_id, client_id)`. Không dùng repository mặc định theo client ID toàn cục nếu có thể có collision giữa tenant.

Khi người dùng có membership nhiều tenant, cần xác định tenant context cụ thể cho authorization transaction. Không để một login session ở tenant A tự động cấp token cho tenant B nếu không có bước kiểm tra membership/consent phù hợp.

## 6. Mô hình nhiều issuer: định tuyến issuer theo tenant

### 6.1. Registry issuer phải do server quản lý

Duy trì một tenant registry đáng tin cậy:

| tenant_id | issuer | hostname | trạng thái |
| --- | --- | --- | --- |
| `acme` | `https://acme.login.example.com` | `acme.login.example.com` | ACTIVE |
| `fabrikam` | `https://fabrikam.login.example.com` | `fabrikam.login.example.com` | ACTIVE |
| `northwind` | `https://northwind.login.example.com` | `northwind.login.example.com` | ACTIVE |

Registry có thể lưu trong configuration service hoặc database quản trị. Không nhận issuer URL bất kỳ từ request rồi fetch metadata hoặc dùng làm issuer context.

### 6.2. Resolve issuer trước khi xử lý endpoint

Luồng tổng quát:

1. Nhận request và xác định canonical host/path.
2. Tìm tenant registry entry.
3. Kiểm tra tenant đang ACTIVE và hostname thuộc issuer đó.
4. Nạp tenant-specific Authorization Server configuration.
5. Bind issuer context trong suốt request.
6. Chạy protocol endpoint và các core service trong đúng tenant namespace.
7. Clear context sau request.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OIDC Client
    participant P as Reverse Proxy
    participant R as Tenant Registry
    participant AS as Authorization Server
    participant S as Tenant Services
    C->>P: Request tới acme.login.example.com
    P->>AS: Forward host đã chuẩn hóa
    AS->>R: Resolve canonical host
    R-->>AS: Tenant Acme + issuer + policy
    AS->>AS: Bind tenant/issuer context
    AS->>S: Resolve client, authorization, keys
    S-->>AS: Dữ liệu tenant Acme
    AS-->>C: Response với issuer Acme
~~~

### 6.3. Một deployment nhiều issuer cần tenant-aware components

Spring Authorization Server 1.5.8 cung cấp `AuthorizationServerSettings` để cấu hình issuer và endpoint settings. Cấu hình `.issuer(...)` thường được khai báo như một bean dùng chung. Nếu chỉ khai báo một bean tĩnh, ứng dụng đang cấu hình một issuer cho server context đó.

Để phục vụ nhiều issuer trong một deployment, ứng dụng phải có routing layer và các component tenant-aware. Có thể dùng:

- Một Authorization Server application context/filter chain cho mỗi issuer.
- Các tenant-specific runtime/configuration được chọn trước khi endpoint xử lý request.
- Decorator cho core service, JWK source và issuer context để delegate sang đúng tenant.
- Nhiều deployment riêng nếu cần boundary vận hành mạnh hơn.

Không chỉ đọc Host header rồi thay `iss` trong JWT. Discovery, endpoint URL, token generator, JWK source, client authentication, authorization store và issuer validation đều phải dùng cùng tenant context.

### 6.4. Tenant runtime

Một mô hình cấu hình có thể biểu diễn:

~~~java
public record TenantAuthorizationServerRuntime(
    String tenantId,
    AuthorizationServerSettings settings,
    RegisteredClientRepository clients,
    OAuth2AuthorizationService authorizations,
    OAuth2AuthorizationConsentService consents,
    JWKSource<SecurityContext> jwkSource
) {}
~~~

Ứng dụng duy trì registry từ tenant ID/issuer đã được xác thực tới runtime tương ứng. Các adapter dùng context hiện tại để delegate:

~~~java
RegisteredClient findByClientId(String clientId) {
    TenantAuthorizationServerRuntime runtime =
        tenantRuntimeRegistry.requireCurrent();
    return runtime.clients().findByClientId(clientId);
}
~~~

Đây là pseudocode mô tả pattern, không phải cấu hình hoàn chỉnh có thể copy vào ứng dụng. Cần kiểm tra API và lifecycle của Spring Authorization Server đúng phiên bản, đặc biệt cách `AuthorizationServerContext` được thiết lập, cách `AuthorizationServerSettings` được resolve và thứ tự filter.

### 6.5. AuthorizationServerContext và issuer

Spring Authorization Server sử dụng `AuthorizationServerContext` để cung cấp issuer/settings cho các thành phần xử lý request. Trong mô hình một issuer, framework có thể dùng cấu hình settings tĩnh.

Trong mô hình nhiều issuer, request cần có context đúng trước khi các component tạo discovery metadata, authorization response hoặc token. Nếu mở rộng context theo tenant, phải:

- Resolve tenant từ registry đáng tin cậy.
- Bind context trước endpoint/provider cần dùng issuer.
- Không cho component fallback sang issuer mặc định khi tenant không hợp lệ.
- Clear context sau request.
- Bảo đảm context không rò sang thread khác hoặc request kế tiếp.
- Kiểm thử song song hai request của hai issuer trên cùng process.

Nếu không thể bảo đảm các điều kiện này bằng extension point ổn định, dùng application context/filter chain hoặc deployment riêng cho từng issuer sẽ an toàn và dễ kiểm thử hơn.

### 6.6. Không dùng một JWK source chung ngoài ý muốn

Mỗi issuer phải công bố JWKS tương ứng với signing key mà issuer đó dùng để ký token. Nếu tenant cần key riêng:

- Tách key alias trong HSM/KMS theo tenant.
- Tách JWK Set và `kid` namespace.
- Tách quyền rotate/revoke key.
- Không để issuer Acme trả public key dùng để xác minh token của Fabrikam nếu policy yêu cầu isolation.
- Ghi audit cho key activation/retirement theo tenant.

Nếu nhiều issuer cố ý dùng chung key, vẫn phải bảo đảm `iss` được xác minh chính xác. Dùng chung key không làm hai issuer trở thành một issuer.

## 7. Phân tách core services và dữ liệu theo tenant

### 7.1. RegisteredClientRepository

`RegisteredClientRepository` có các method `findById`, `findByClientId` và `save`; API không nhận tham số tenant riêng. Với một issuer chung có client ID trùng giữa tenant, custom repository phải lấy tenant từ context đã xác thực và truy vấn theo cặp tenant/client.

Ví dụ schema:

~~~sql
CREATE TABLE oauth2_registered_client (
    tenant_id varchar(100) NOT NULL,
    id varchar(100) NOT NULL,
    client_id varchar(200) NOT NULL,
    client_secret varchar(500),
    client_settings text NOT NULL,
    token_settings text NOT NULL,
    PRIMARY KEY (tenant_id, id),
    UNIQUE (tenant_id, client_id)
);
~~~

DDL chỉ minh họa composite key. Cần đối chiếu schema đầy đủ của RegisteredClient, độ dài cột, unique constraint và mapper đang dùng. Nếu các tenant có client ID toàn cục duy nhất, có thể dùng unique key toàn cục nhưng vẫn phải xác minh client thuộc tenant nào.

### 7.2. OAuth2AuthorizationService

Authorization cần gắn với tenant từ lúc tạo:

- Authorization ID thuộc namespace tenant.
- RegisteredClient ID phải tham chiếu client trong cùng tenant.
- Token lookup phải tenant-aware.
- `findById` và `findByToken` không được trả authorization thuộc tenant khác.
- Refresh/revoke/introspection phải dùng cùng tenant context đã resolve.

Schema dùng chung có thể thêm `tenant_id` và các index bắt đầu bằng tenant ID. Ví dụ:

~~~sql
CREATE INDEX idx_authorization_tenant_id
    ON oauth2_authorization (tenant_id, id);
~~~

Index minh họa phải khớp query thật. Cột tenant ID trong row không đủ nếu query hoặc repository quên thêm điều kiện tenant.

### 7.3. OAuth2AuthorizationConsentService

Consent được tìm theo RegisteredClient ID và principal name. Với một issuer dùng chung, nên đảm bảo client ID nội bộ đã thuộc đúng tenant. Nếu cùng principal name tồn tại trong nhiều tenant, consent key cần thêm tenant namespace trong storage/custom service.

Không dùng email làm tenant-independent principal key nếu email có thể được tái sử dụng hoặc thay đổi. Chọn immutable subject/user ID phù hợp với identity model.

### 7.4. Dùng chung database hay database riêng?

| Mô hình persistence | Lợi ích | Hạn chế |
| --- | --- | --- |
| Shared tables + `tenant_id` | Dễ vận hành, migration và connection pooling tập trung. | Mọi query phải tenant-scoped; lỗi predicate có thể gây cross-tenant data leak. |
| Schema riêng mỗi tenant | Tách namespace và quyền truy cập tốt hơn. | Migration, connection routing và schema lifecycle phức tạp. |
| Database riêng mỗi tenant | Boundary dữ liệu mạnh, backup/restore và residency độc lập. | Chi phí vận hành, connection pool, monitoring và migration cao. |
| Hybrid | Tenant lớn/đặc biệt có DB riêng, tenant khác dùng shared schema. | Cần abstraction và routing thống nhất. |

Issuer model và database model là hai quyết định riêng. Một issuer có thể dùng database riêng theo tenant; nhiều issuer cũng có thể dùng chung database với cột tenant ID. Chọn từng quyết định theo yêu cầu trust và data isolation.

### 7.5. Row-level security và connection pool

Nếu database hỗ trợ Row-Level Security (RLS), policy có thể thêm lớp bảo vệ cho tenant-scoped tables. Tuy nhiên:

- Tenant context phải được đặt bằng cơ chế đáng tin cậy trong transaction.
- Session variable phải được reset đúng cách khi trả connection về pool.
- Không để request tiếp theo thừa hưởng tenant ID của request trước.
- Application role không được có quyền bypass RLS ngoài chủ đích.
- Test cả native query, batch job và migration account.

RLS là lớp phòng thủ bổ sung, không thay thế tenant predicate trong repository và authorization policy.

## 8. Discovery, endpoint và token validation

### 8.1. Discovery metadata phải khớp issuer

Với một issuer dùng chung, discovery document công bố issuer chung và endpoint chung.

Với nhiều issuer, mỗi discovery document phải công bố đúng issuer của tenant và các endpoint tương ứng. Không trả discovery document của Acme cho request đã resolve thành Fabrikam.

Kiểm tra:

- `issuer` khớp chính xác tenant issuer.
- `authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint` và các endpoint khác thuộc đúng issuer.
- TLS certificate/hostname phù hợp với public issuer URL.
- URL endpoint không bị tạo từ Host header tùy ý.
- Metadata cache được namespace theo issuer và invalidated khi cấu hình thay đổi.

### 8.2. Issuer path và hostname

Hai kiểu URL thường gặp:

~~~text
https://acme.login.example.com
https://login.example.com/issuers/acme
~~~

Hostname riêng thường dễ quan sát và ánh xạ TLS hơn. Path-based issuer có thể giảm số hostname nhưng đòi hỏi reverse proxy, discovery well-known URL và endpoint routing phải xử lý path nhất quán theo đặc tả.

Không tự ghép well-known URL bằng string concatenation mà bỏ qua quy tắc discovery khi issuer có path. Dùng thư viện/client tuân thủ chuẩn và kiểm thử URL được công bố từ bên ngoài proxy.

### 8.3. Client phải ràng buộc authorization request với issuer

Khi một client hỗ trợ nhiều issuer, mỗi authorization transaction cần lưu issuer mong đợi. Client phải xác minh issuer trong response theo giao thức và cơ chế mix-up protection mà nó hỗ trợ.

Không chỉ chọn issuer theo tham số callback hoặc state do caller gửi mà không đối chiếu với authorization request ban đầu. Với OIDC, client cũng phải xác minh `iss` trong ID Token khớp issuer đã chọn.

OAuth 2.0 Authorization Server có thể hỗ trợ tham số response issuer theo RFC 9207 để client phân biệt authorization server trong môi trường nhiều issuer. Hãy xác minh hỗ trợ của client và framework/version đang triển khai; không mặc định mọi client đều kiểm tra tham số này.

### 8.4. Resource Server xác minh nhiều issuer

Nếu API nhận token từ nhiều issuer, Resource Server cần resolver tới một `AuthenticationManager`/decoder tương ứng với issuer đã tin cậy. Danh sách issuer phải được quản trị:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://acme.login.example.com",
        "https://fabrikam.login.example.com",
        "https://northwind.login.example.com"
    );
~~~

Đoạn code minh họa mô hình allow-list issuer với Spring Security. Không dùng resolver chấp nhận mọi issuer tùy ý lấy từ claim `iss` rồi tự động fetch discovery metadata. Nếu attacker có thể đưa issuer URL do họ kiểm soát, Resource Server có thể bị SSRF hoặc tin nhầm key.

Sau khi xác minh issuer, Resource Server vẫn phải kiểm tra audience, scope/authority, tenant binding và quyền trên resource.

### 8.5. Issuer và tenant claim cùng tồn tại

Với nhiều issuer, token vẫn có thể chứa tenant claim để API dùng cho authorization:

~~~json
{
  "iss": "https://acme.login.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "tenant_id": "acme",
  "scope": "orders.read"
}
~~~

Kiểm tra `tenant_id` nhất quán với issuer-to-tenant mapping. Nếu token có `iss` của Acme nhưng claim tenant là Fabrikam, phải từ chối hoặc xử lý theo policy rõ ràng; không tự chọn một trong hai giá trị.

## 9. Key management và bảo mật

### 9.1. Một issuer, một hay nhiều key?

Một issuer chung có thể dùng:

- Một signing key set dùng chung cho tất cả tenant.
- Nhiều key trong cùng JWKS, nhưng vẫn thuộc một issuer.
- Key alias theo tenant trong HSM, trong khi JWKS của issuer công bố public key phù hợp.

Lựa chọn phụ thuộc policy. Nếu mọi token cùng issuer và Resource Server chỉ tin issuer, key compromise của một key được issuer công bố có thể ảnh hưởng trust của toàn issuer.

### 9.2. Nhiều issuer, key tách biệt

Với issuer riêng, có thể:

- Mỗi tenant có signing key riêng.
- Tenant quản lý key rotation độc lập.
- Phân quyền operator theo tenant.
- Thu hồi hoặc retire key của một tenant mà không đổi key của tenant khác.

Key store phải namespace theo tenant/issuer. Không chỉ dùng `kid` làm global key lookup nếu `kid` có thể trùng giữa issuer; cặp issuer + kid mới xác định key context.

### 9.3. Không suy issuer từ kid

`kid` chỉ là key identifier trong phạm vi JWK Set/key source được chọn. Không dùng `kid` để quyết định tenant hoặc issuer. Trình tự an toàn là:

1. Resolve issuer từ trusted request/client configuration.
2. Chọn issuer-specific metadata/JWKS.
3. Chọn key theo `kid` trong JWKS đó.
4. Xác minh chữ ký và claims.

### 9.4. TLS, domain và DNS

Custom domain/hostname theo tenant cần:

- Domain ownership verification trước khi gắn tenant.
- TLS certificate đúng hostname.
- Chống domain takeover khi tenant offboard.
- Kiểm soát CNAME/DNS changes.
- Không cho tenant tự trỏ issuer sang hostname chưa được xác minh.
- Giữ issuer ổn định sau khi client đã cấu hình trust.

Không xóa DNS/TLS mapping trước khi hoàn tất quá trình retire issuer và xử lý token/client còn hoạt động.

## 10. Vòng đời tenant và thay đổi issuer

### 10.1. Onboarding tenant

Với một issuer dùng chung:

1. Tạo tenant record và tenant policy.
2. Cấu hình hostname/path hoặc cơ chế chọn tenant.
3. Cấp client trong tenant namespace.
4. Thiết lập user membership, consent và quota.
5. Cấu hình Resource Server/API tenant authorization.
6. Kiểm thử token có tenant claim đúng.

Với nhiều issuer:

1. Tạo tenant record và issuer identifier canonical.
2. Xác minh domain và TLS.
3. Cấp signing key/HSM alias.
4. Tạo discovery metadata và JWKS endpoint.
5. Cấu hình client registry, authorization và consent store.
6. Đưa issuer vào trusted issuer allow-list của Resource Server.
7. Kiểm thử discovery, authorization, token validation, logout và key rotation.

### 10.2. Issuer không nên thay đổi tùy ý

Issuer được client dùng làm trust identifier. Thay hostname hoặc path có thể làm:

- Discovery URL cũ không còn hoạt động.
- Client từ chối ID Token vì `iss` thay đổi.
- Resource Server không còn tin token mới.
- Logout/session management không tìm đúng OP.
- Federation trust bị đứt.

Nếu cần đổi issuer, coi đó là migration giao thức. Cần công bố kế hoạch, hỗ trợ song song issuer cũ/mới trong thời gian chuyển tiếp, cập nhật client/resource server và chờ token cũ hết hạn hoặc revoke theo policy.

### 10.3. Chuyển từ một issuer sang nhiều issuer

Một kế hoạch chuyển đổi có thể gồm:

1. Xác định tenant nào cần issuer riêng và lý do.
2. Tạo issuer mới, key set, discovery metadata và storage namespace.
3. Cấu hình Resource Server tin issuer cũ và issuer mới trong giai đoạn migration.
4. Cập nhật OIDC client với issuer mới và redirect URI.
5. Re-authenticate hoặc re-issue token dưới issuer mới.
6. Không sửa claim `iss` của token đã phát hành để giả lập issuer mới.
7. Chờ token cũ hết hạn hoặc xử lý revoke.
8. Loại issuer cũ khỏi allow-list khi không còn dependency.

### 10.4. Chuyển từ nhiều issuer về một issuer

Quy trình tương tự theo chiều ngược lại:

- Chọn issuer canonical mới.
- Cấu hình tenant claim và tenant authorization.
- Cập nhật client discovery/trust.
- Re-issue token dưới issuer chung.
- Giữ validation issuer cũ trong thời gian chuyển tiếp cần thiết.
- Retire key/endpoint cũ sau khi hết token và hoàn tất logout/session policy.

Không thể đổi `iss` của token đang lưu mà vẫn giữ nguyên chữ ký. Token phải được phát hành lại.

### 10.5. Offboarding tenant

Offboarding cần xử lý:

- Chặn đăng nhập và client authentication mới.
- Thu hồi/disable client.
- Revoke authorization/token theo policy.
- Vô hiệu hóa refresh token và session.
- Gỡ issuer khỏi discovery/trusted issuer khi phù hợp.
- Giữ audit/retention data theo yêu cầu.
- Xử lý custom domain/TLS/DNS an toàn.
- Xác nhận tenant khác không bị ảnh hưởng.

Với issuer dùng chung, không được tắt toàn issuer chỉ để offboard một tenant. Với issuer riêng, việc retire issuer vẫn cần xử lý token và client đã lưu hành.

## 11. Các lỗi thường gặp

### Lỗi 1: Nhầm tenant ID với issuer

**Triệu chứng:** Token có tenant claim nhưng client validation dùng claim đó thay cho `iss`.

**Nguyên nhân:** Không phân biệt tenant context với OP identity.

**Cách xử lý:** Xác minh issuer theo discovery/trust configuration; dùng tenant claim cho authorization sau đó.

### Lỗi 2: Dùng một issuer nhưng không đưa tenant vào authorization

**Triệu chứng:** Người dùng tenant A có thể truy cập resource tenant B.

**Nguyên nhân:** API chỉ kiểm tra chữ ký và scope, bỏ qua tenant boundary.

**Cách xử lý:** Ràng buộc tenant claim, client, principal và resource trong authorization policy.

### Lỗi 3: Chọn tenant từ Host header không đáng tin

**Triệu chứng:** Attacker gửi Host/X-Forwarded-Host để truy cập tenant khác hoặc tạo issuer giả.

**Nguyên nhân:** Tin header từ Internet hoặc tự nối host thành issuer.

**Cách xử lý:** Chuẩn hóa ở trusted proxy, allow-list hostname và tra tenant registry.

### Lỗi 4: Nhiều issuer nhưng dùng chung client registry không tenant-aware

**Triệu chứng:** Client ID trùng tenant gây trả nhầm RegisteredClient hoặc dùng secret của tenant khác.

**Nguyên nhân:** Repository chỉ tra theo client ID toàn cục.

**Cách xử lý:** Tách repository hoặc thêm tenant/issuer namespace và unique constraint phù hợp.

### Lỗi 5: Discovery của tenant này trả issuer của tenant khác

**Triệu chứng:** Client nhận metadata nhưng ID Token bị từ chối vì `iss` mismatch.

**Nguyên nhân:** Tenant routing và issuer context không đồng nhất.

**Cách xử lý:** Kiểm thử discovery, endpoint URL và token `iss` trên từng tenant hostname/path.

### Lỗi 6: Dùng chung JWK source ngoài ý muốn

**Triệu chứng:** Tenant thấy public key của tenant khác hoặc key rotation ảnh hưởng không đúng phạm vi.

**Nguyên nhân:** Key source không tenant-aware.

**Cách xử lý:** Namespace key theo issuer/tenant và kiểm soát quyền HSM/KMS.

### Lỗi 7: Resource Server tự động tin mọi issuer

**Triệu chứng:** API fetch discovery/JWKS từ issuer do token attacker cung cấp.

**Nguyên nhân:** Không có trusted issuer allow-list.

**Cách xử lý:** Quản lý issuer registry tin cậy; không cho claim `iss` tùy ý quyết định outbound URL.

### Lỗi 8: Tenant context rò giữa các request

**Triệu chứng:** Request sau được xử lý bằng tenant của request trước.

**Nguyên nhân:** ThreadLocal không được clear hoặc async context không được truyền đúng.

**Cách xử lý:** Scope có try/finally, clear context và kiểm thử thread reuse/concurrency.

### Lỗi 9: Chỉ thêm tenant_id vào database nhưng quên query

**Triệu chứng:** Repository trả authorization/client/consent của tenant khác.

**Nguyên nhân:** Query thiếu tenant predicate hoặc unique constraint không đúng.

**Cách xử lý:** Tenant-aware repository, composite key/index, RLS bổ sung và negative tests cross-tenant.

### Lỗi 10: Thay issuer mà không migration client

**Triệu chứng:** Client/resource server từ chối token sau rollout.

**Nguyên nhân:** `iss` và discovery URL thay đổi nhưng trust configuration cũ.

**Cách xử lý:** Migration issuer có giai đoạn dual trust, re-issue token và retire issuer cũ theo kế hoạch.

## 12. Ma trận kiểm thử

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Single issuer, tenant Acme | Discovery và token đều dùng issuer chung; tenant claim là Acme. |
| Single issuer, tenant Fabrikam | Cùng issuer; không đọc client/authorization của Acme. |
| Tenant không tồn tại | Từ chối request; không fallback tenant mặc định. |
| Host header giả | Không thể đổi tenant/issuer bằng header không đáng tin. |
| Trusted proxy forwarded host | Ánh xạ đúng canonical hostname. |
| Multi issuer Acme discovery | Issuer và endpoint thuộc Acme. |
| Multi issuer Fabrikam discovery | Issuer và endpoint thuộc Fabrikam. |
| Token Acme gửi tới validator Fabrikam-only | Bị từ chối do issuer mismatch. |
| Token có `iss` Acme nhưng `tenant_id` Fabrikam | Bị từ chối theo tenant/issuer consistency policy. |
| Client ID trùng giữa tenant | Repository trả đúng client theo tenant context hoặc từ chối collision. |
| Token lookup trùng/collision namespace | Không trả authorization tenant khác. |
| Consent lookup | Chỉ trả consent đúng tenant/client/principal. |
| Key rotation Acme | Không làm thay đổi key set của Fabrikam. |
| Unknown issuer trong JWT | Resource Server từ chối; không fetch issuer tùy ý. |
| Tenant context với thread reuse | Request sau không thừa hưởng context trước. |
| Concurrent request hai issuer | Discovery/token không bị trộn issuer context. |
| Tenant offboarding | Client/token/issuer bị xử lý theo policy, tenant khác vẫn hoạt động. |
| Issuer migration | Client/resource server validate được issuer theo giai đoạn chuyển đổi. |
| JWT local validation | Thu hồi ở Authorization Server không bị hiểu nhầm là tự động revoke JWT tại API. |

## 13. Checklist production

| Hạng mục | Câu hỏi cần xác nhận |
| --- | --- |
| Issuer decision | Có lý do rõ ràng cho một issuer hay nhiều issuer? |
| Trust boundary | Tenant nào chia sẻ trust domain và tenant nào cần tách? |
| Canonical issuer | Issuer URL ổn định, HTTPS và được quản lý? |
| Tenant resolution | Host/path/client/user context được xác thực trước endpoint? |
| Proxy | Forwarded headers được strip/overwrite tại trusted proxy? |
| Unknown tenant | Request không xác định tenant bị từ chối, không fallback? |
| Discovery | Metadata issuer/endpoints/JWKS khớp tenant context? |
| Token claims | `iss`, `aud`, tenant claim và client binding nhất quán? |
| Client registry | Lookup và unique constraint có tenant/issuer scope? |
| Authorization store | findById/findByToken không thể đọc chéo tenant? |
| Consent | Key có client, principal và tenant namespace? |
| Signing keys | Key/JWK source và quyền rotation đúng boundary? |
| Resource Server | Chỉ trust issuer trong allow-list? |
| Persistence | Shared schema, schema riêng hay DB riêng phù hợp isolation requirement? |
| RLS | Session context được set/reset an toàn nếu dùng? |
| Cache | Cache key có tenant/issuer namespace và invalidation đúng? |
| Logout/session | Logout và session state được giới hạn theo issuer/tenant? |
| Migration | Có kế hoạch dual trust và re-issue token nếu đổi issuer? |
| Offboarding | Có quy trình revoke, retire issuer và xử lý custom domain? |
| Observability | Log/metric có tenant ID an toàn, không chứa token/secret? |
| Tests | Có negative test cross-tenant và concurrency nhiều issuer? |

## 14. Bài tập thực hành

Một nền tảng SaaS có ba tenant:

- Acme yêu cầu issuer riêng, signing key trong HSM riêng và OIDC federation với IdP của họ.
- Fabrikam và Northwind dùng chung giao diện đăng nhập, MFA policy và Resource Server; họ chỉ yêu cầu tách dữ liệu nghiệp vụ.
- Hệ thống hiện có một Spring Authorization Server deployment, PostgreSQL và ba instance chạy sau reverse proxy.

Hãy thiết kế kiến trúc:

1. Chọn mô hình issuer cho từng tenant và giải thích lý do.
2. Xác định canonical issuer URL, hostname và discovery endpoint.
3. Thiết kế tenant registry và trusted host mapping.
4. Quyết định phần nào dùng chung và phần nào tách cho RegisteredClient, authorization, consent và signing key.
5. Thiết kế tenant-aware repository khi client ID có thể trùng giữa tenant.
6. Mô tả cách bind issuer context trong request và clear context an toàn.
7. Thiết kế Resource Server validator cho issuer Acme và issuer chung Fabrikam/Northwind.
8. Xác định claims và authorization checks để ngăn Fabrikam truy cập resource Northwind.
9. Thiết kế key rotation cho Acme mà không ảnh hưởng hai tenant còn lại.
10. Viết test giả mạo Host/X-Forwarded-Host, issuer mismatch và tenant context leakage.
11. Lập kế hoạch nếu Fabrikam sau này cũng yêu cầu issuer riêng.
12. Định nghĩa quy trình offboard Acme nhưng vẫn giữ dịch vụ Fabrikam/Northwind hoạt động.

**Tiêu chí đạt:** Issuer phản ánh đúng trust boundary; tenant được resolve từ nguồn tin cậy; discovery, token `iss`, JWK source và persistence đều dùng cùng tenant context; Resource Server chỉ tin issuer được allow-list; test chứng minh không có truy cập chéo tenant.

## 15. Tài liệu đối chiếu

- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Issuer Identifier và Provider Configuration metadata.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token issuer, audience và validation.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer và authorization server metadata.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207): issuer identification trong authorization response để hỗ trợ mix-up protection.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình Authorization Server endpoints và settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerSettings Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/AuthorizationServerSettings.html): issuer và endpoint settings.
- [Spring Authorization Server 1.5.8 — AuthorizationServerContext Javadoc](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/context/AuthorizationServerContext.html): context cung cấp issuer và settings.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): RegisteredClient, authorization, consent và service contracts.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer validation và Resource Server configuration.
- [Spring Security — Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): định tuyến nhiều issuer tới AuthenticationManager trong Resource Server.
