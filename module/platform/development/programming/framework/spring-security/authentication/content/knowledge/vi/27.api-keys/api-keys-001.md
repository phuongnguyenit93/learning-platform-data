# API key đại diện cho ứng dụng, dịch vụ hoặc tài khoản theo chính sách cụ thể

API key là một **credential**: chuỗi bí mật mà client trình ra khi gọi API để máy chủ kiểm tra quyền sử dụng. Khi credential hợp lệ, ứng dụng phải trả lời tiếp **key này đại diện cho ai**. Theo chính sách cấp phát, đó có thể là một ứng dụng (application), một dịch vụ chạy tự động (service account), hoặc một tài khoản người dùng/tổ chức (account).

**Có key đúng không đồng nghĩa với được phép làm mọi việc.** Key chỉ là bằng chứng sở hữu credential. Danh tính (principal), tenant, scopes, trạng thái và quyền hiệu lực được quyết định bởi bản ghi cấp phát cùng chính sách phía server. Đây là ranh giới quan trọng nhất khi thiết kế API key với Spring Security.

Bài học phân biệt rõ key ID, secret, principal và owner; trình bày ba mô hình đại diện; cách dựng `Authentication` và `GrantedAuthority`; nguyên tắc phân quyền theo tenant/resource; vòng đời key; ví dụ Java 17+ và đoạn cấu hình Spring Security Servlet.

## 1. Key, principal, chủ sở hữu và người tạo key là bốn khái niệm khác nhau

Client có thể gửi:

~~~http
GET /api/catalog/items HTTP/1.1
Host: api.example.org
X-API-Key: <secret-do-client-luu>
~~~

Header `X-API-Key` chỉ là quy ước truyền credential của ứng dụng. **Spring Security không mặc nhiên xác thực mọi header X-API-Key**; hệ thống cần filter/provider/verifier riêng hoặc gateway đáng tin cậy đã được cấu hình.

Một bản ghi cấp phát có thể chứa:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Raw API key | Chuỗi ngẫu nhiên dài được phát cho client | Bí mật chứng minh quyền dùng credential |
| Public key ID | `ak_7c82d1` | Định danh bản ghi để tra cứu, audit, thu hồi; không phải secret |
| Subject type | `APPLICATION`, `SERVICE_ACCOUNT`, `ACCOUNT` | Loại thực thể được key đại diện |
| Subject ID | `app:checkout`, `svc:billing-sync`, `user:lan` | ID của principal mà API nhận diện |
| Owner ID | `team:commerce`, `team:finance`, `user:lan` | Ai quản lý và chịu trách nhiệm key |
| Created by | `user:security-admin` | Ai đã yêu cầu/phát hành key |
| Tenant ID | `tenant-a` | Phạm vi tổ chức/dữ liệu được phép |
| Key scopes | `CATALOG_READ`, `INVOICE_WRITE` | Giới hạn quyền có thể yêu cầu qua key |
| Status, expiry | `ACTIVE`, thời điểm hết hạn | Điều kiện tiếp tục được sử dụng |

**Owner không nhất thiết là principal:** trưởng nhóm có thể quản lý key của `svc:billing-sync` nhưng khi job gọi API, principal phải là service account, không phải trưởng nhóm. Người tạo key cũng không tự trở thành người dùng cuối của mọi request.

**Key ID không đủ xác thực:** mã công khai có thể xuất hiện trong trang quản trị hoặc log có kiểm soát; chỉ có ID mà thiếu secret hợp lệ thì không được cấp Authentication.

**Principal khác subject của tài nguyên:** request do service gọi có thể thao tác lên hóa đơn của khách hàng. Khách hàng là chủ tài nguyên, không phải actor đang thực thi HTTP request.

## 2. Ba chính sách đại diện danh tính

### 2.1. API key đại diện ứng dụng (application key)

Ví dụ:

~~~yaml
keyId: ak_app_01
subjectType: APPLICATION
subjectId: app:checkout
ownerId: team:commerce
tenantId: tenant-a
keyScopes:
  - CATALOG_READ
status: ACTIVE
~~~

Key này chứng minh client biết credential đã cấp cho **ứng dụng checkout**. Nếu 10.000 người dùng đều thao tác qua cùng một backend, từ key này riêng lẻ **không thể suy ra người dùng cuối là ai**.

Khi cần xác định người dùng cuối, ứng dụng phải bổ sung một cơ chế user authentication/authorization phù hợp như session, OAuth2/OIDC hoặc access token có subject người dùng. Không thể cho client tự gửi thêm `X-User: admin` rồi coi đó là bằng chứng ủy quyền.

Key cố định nhúng trong bundle JavaScript, web public hoặc ứng dụng mobile công khai thường có thể bị trích xuất. Nó có thể dùng nhận diện *loại client* hoặc hỗ trợ quota công khai, nhưng không nên được coi là secret mạnh để bảo vệ dữ liệu nhạy cảm.

**Ví dụ quyền:** app:checkout được đọc catalog, không được sửa tài khoản người dùng và không được thay mặt người mua thanh toán chỉ vì nắm một application key.

### 2.2. API key đại diện dịch vụ (service account key)

Ví dụ:

~~~yaml
keyId: ak_service_01
subjectType: SERVICE_ACCOUNT
subjectId: svc:billing-sync
ownerId: team:finance-platform
tenantId: tenant-a
keyScopes:
  - INVOICE_READ
  - INVOICE_WRITE
status: ACTIVE
~~~

Một job đồng bộ hóa hóa đơn chạy theo lịch có **machine identity** riêng. Request tới API là hành vi của `svc:billing-sync`. Tài khoản này không phải user thật và không nhất thiết có màn hình login/MFA. Quyền của nó được cấp theo nhiệm vụ: đồng bộ hóa hóa đơn đúng tenant, đúng endpoints.

Service key nên gắn với môi trường hoặc workload để có thể thu hồi độc lập. Nếu mọi service trong tổ chức dùng chung một key `internal-admin`, audit không phân biệt ai đã gọi, quyền quá rộng và một sự cố có thể ảnh hưởng tất cả.

Nếu cần bảo đảm mạnh hơn về máy thực thi, xem xét workload identity, mTLS hoặc OAuth2 client credentials. Một bearer API key thông thường chứng minh **người gửi sở hữu chuỗi secret**, không chứng minh đó là một process hoặc máy cụ thể.

### 2.3. API key gắn với tài khoản (account-bound key)

Ví dụ người dùng Lan tạo key cho script báo cáo:

~~~yaml
keyId: ak_user_01
subjectType: ACCOUNT
subjectId: user:lan
ownerId: user:lan
tenantId: tenant-a
keyScopes:
  - REPORT_READ
status: ACTIVE
~~~

API có thể nhận diện request dưới account `user:lan`, **nhưng không được kết luận Lan vừa tương tác trực tiếp**. Bất kỳ script hoặc bên nào giữ key đều có thể sử dụng nó. Audit phải ghi phương thức xác thực là API key để phân biệt với login tương tác.

Key cá nhân phải chịu ràng buộc trạng thái tài khoản và quyền hiện tại. Nếu account bị vô hiệu hóa, bị loại khỏi tenant hoặc mất quyền đọc báo cáo, key không được tiếp tục giữ các quyền đó vô hạn chỉ vì lúc phát hành từng được phép.

“Account” cũng có thể là tài khoản tổ chức, dự án hoặc billing account: `account:billing-prod`. Khi đó principal phải thể hiện đúng loại account, không tự gán cho người đã nhấn nút tạo key.

### So sánh

| Tiêu chí | Application | Service account | Account-bound |
| --- | --- | --- | --- |
| Danh tính chính | Client application | Workload/job/service | Account cụ thể |
| Thường do ai quản lý | Nhóm phát triển app | Nhóm vận hành | Chủ tài khoản hoặc admin |
| Chứng minh user đang thao tác? | Không | Không | Không chứng minh tương tác trực tiếp |
| Phạm vi cần giới hạn | Chức năng app, tenant, environment | Công việc service, tài nguyên | Quyền account hiện tại ∩ scope key |
| Rủi ro nổi bật | Key lộ từ public client | Key chung quá rộng | Key sống tiếp sau khi mất quyền |
| Audit actor | app ID | service ID | account ID + phương thức API key |

Một hệ thống có thể dùng cả ba loại, nhưng phải định nghĩa chính sách cấp phát riêng và không âm thầm chuyển một key từ principal này sang principal khác.

## 3. Actor, resource owner, createdBy và on-behalf-of

Ví dụ:

~~~text
keyId           = ak_service_01
actorPrincipal  = svc:billing-sync
owner           = team:finance-platform
createdBy       = user:security-admin
resourceOwner   = customer:42
tenant          = tenant-a
~~~

**Actor principal** là dịch vụ gọi API. **Resource owner** là khách hàng có hóa đơn đang được xử lý. **Owner của key** là team quản trị secret. **CreatedBy** là người tạo key. Bốn thông tin phục vụ mục đích khác nhau và không được đồng nhất.

Nếu dịch vụ cần hành động *thay mặt* một người dùng (on behalf of user), cần bằng chứng ủy quyền riêng: ai chấp thuận, ủy quyền cho ai, phạm vi/tài nguyên nào, thời gian bao lâu, thu hồi bằng cách nào. Một header do client tự đặt như:

~~~http
X-API-Key: <secret>
X-Acting-User: admin
~~~

không phải bằng chứng ủy quyền. Có thể dùng OAuth2 Authorization Code hoặc một cơ chế delegation/token exchange được thiết kế đúng khi bài toán cần user identity trong chuỗi nhiều dịch vụ.

Audit nên lưu ít nhất `actorType`, `actorId`, `keyId`, `tenantId`, `resourceOwnerId`, action, kết quả và correlation ID. Không đưa raw API key hay hash bí mật vào log.

## 4. Pipeline từ credential đến Authentication

Một request sử dụng API key trong ứng dụng Servlet thường đi qua các bước:

~~~text
Client gửi X-API-Key qua HTTPS
    |
    v
API gateway / Spring Security filter
    |
    v
Kiểm tra format, độ dài, số lượng header
    |
    v
Tra keyId và xác minh secret với digest/HMAC đáng tin cậy
    |
    v
Kiểm tra revoked/expiry/status/tenant/environment
    |
    v
Xác định subjectType, subjectId, owner và policy phía server
    |
    v
Kiểm tra principal còn hợp lệ; tính authorities hiệu lực
    |
    v
Tạo Authentication (principal, authorities; không giữ raw key)
    |
    v
SecurityContext của request
    |
    v
Authorization theo action + tenant + resource
    |
    v
Cho phép hoặc từ chối
~~~

Cần phân biệt các lớp kết quả:

- **Không có credential** ở endpoint chỉ cho API key: chưa được xác thực, thường trả **401**.
- **Key sai, hết hạn, bị thu hồi:** không tạo authenticated principal; thường **401** với thông báo chung.
- **Key hợp lệ nhưng scope hoặc resource policy không đủ:** người gọi đã được nhận diện nhưng không được phép; thường **403**.
- **Key store, HSM, policy store không khả dụng:** fail closed, không tạo principal mặc định; có thể trả **5xx/503** theo thiết kế.
- **Rate limit/quota:** có thể trả **429**, là chính sách bổ sung, không thay cho việc kiểm quyền.

Trong Spring Security Servlet, `Authentication` chứa `principal`, `credentials`, `authorities`. `SecurityContextHolder` quản lý ngữ cảnh xác thực của luồng xử lý; không lưu principal hiện tại trong trường `static` hoặc singleton mutable.

Spring Security có `AuthenticationManager`, `ProviderManager` và `AuthenticationProvider` để tổ chức luồng xác thực. Với API key custom, ứng dụng có thể triển khai AuthenticationProvider hoặc filter gọi một dịch vụ xác minh riêng. **Không có quy tắc mặc định rằng mọi X-API-Key hợp lệ sẽ tự trở thành một user trong Spring Security.**

## 5. Quyền hiệu lực là giao của nhiều điều kiện

Được xác thực và được ủy quyền là hai câu hỏi khác nhau. Một mô hình kiểm soát truy cập:

~~~text
ALLOW(request) =
    key_valid
  AND principal_active
  AND key_tenant_matches_resource
  AND requested_action_in_key_scopes
  AND requested_action_in_principal_entitlements
  AND resource_policy_allows
  AND contextual_constraints_allow
~~~

Đặc biệt, **scope của key là giới hạn trên, không tự cấp quyền vượt quá principal**.

Ví dụ key của Lan có scopes `REPORT_READ` và `REPORT_EXPORT`. Nếu tài khoản Lan hiện chỉ còn quyền `REPORT_READ`, thì export phải bị từ chối. Ngược lại, tài khoản Lan có quyền `REPORT_EXPORT` nhưng key chỉ cấp `REPORT_READ` thì export cũng bị từ chối.

Với application/service account, “principal entitlements” có thể đến từ kho chính sách machine identity, không nhất thiết là RBAC của người dùng.

Một key thuộc `tenant-a` không được đọc tài nguyên tenant B dù cùng tên authority `INVOICE_READ`. Giới hạn tenant phải xuất phát từ principal/policy đáng tin cậy ở server, **không** chỉ từ tham số `tenantId` mà client yêu cầu.

### Java 17+: chương trình độc lập

Tạo tệp **ApiKeyIdentityDemo.java**:

~~~java
import java.util.Set;

public class ApiKeyIdentityDemo {

    enum SubjectType { APPLICATION, SERVICE_ACCOUNT, ACCOUNT }

    record KeyPolicy(
            String keyId,
            SubjectType type,
            String subjectId,
            String ownerId,
            String tenantId,
            Set<String> keyScopes,
            Set<String> subjectEntitlements,
            boolean active) {
    }

    static String principal(KeyPolicy key) {
        return key.type() + ":" + key.subjectId();
    }

    static boolean allows(KeyPolicy key, String resourceTenant,
                          String action) {
        return key.active()
                && key.tenantId().equals(resourceTenant)
                && key.keyScopes().contains(action)
                && key.subjectEntitlements().contains(action);
    }

    public static void main(String[] args) {
        KeyPolicy app = new KeyPolicy(
                "key-app", SubjectType.APPLICATION, "app:checkout",
                "team:commerce", "tenant-a",
                Set.of("CATALOG_READ"),
                Set.of("CATALOG_READ", "ORDER_WRITE"), true);

        KeyPolicy service = new KeyPolicy(
                "key-service", SubjectType.SERVICE_ACCOUNT,
                "svc:billing-sync", "team:finance", "tenant-a",
                Set.of("INVOICE_WRITE"), Set.of("INVOICE_WRITE"), true);

        KeyPolicy account = new KeyPolicy(
                "key-account", SubjectType.ACCOUNT, "user:lan",
                "user:lan", "tenant-a",
                Set.of("REPORT_READ", "REPORT_EXPORT"),
                Set.of("REPORT_READ"), true);

        KeyPolicy revoked = new KeyPolicy(
                "key-revoked", SubjectType.ACCOUNT, "user:lan",
                "user:lan", "tenant-a",
                Set.of("REPORT_READ"), Set.of("REPORT_READ"), false);

        System.out.println("App principal = " + principal(app));
        System.out.println("Service principal = " + principal(service));
        System.out.println("Account principal = " + principal(account));
        System.out.println("App catalog read = "
                + allows(app, "tenant-a", "CATALOG_READ"));
        System.out.println("App order write = "
                + allows(app, "tenant-a", "ORDER_WRITE"));
        System.out.println("Service invoice write = "
                + allows(service, "tenant-a", "INVOICE_WRITE"));
        System.out.println("Account report export = "
                + allows(account, "tenant-a", "REPORT_EXPORT"));
        System.out.println("Cross-tenant report read = "
                + allows(account, "tenant-b", "REPORT_READ"));
        System.out.println("Revoked key report read = "
                + allows(revoked, "tenant-a", "REPORT_READ"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac ApiKeyIdentityDemo.java
java ApiKeyIdentityDemo
~~~

Stdout chính xác:

~~~text
App principal = APPLICATION:app:checkout
Service principal = SERVICE_ACCOUNT:svc:billing-sync
Account principal = ACCOUNT:user:lan
App catalog read = true
App order write = false
Service invoice write = true
Account report export = false
Cross-tenant report read = false
Revoked key report read = false
~~~

Mỗi key được gắn với **một** principal. `App order write = false` vì scope key không có quyền ghi, dù entitlement của app có thể có. `Account report export = false` vì account đã mất quyền. `Cross-tenant... = false` vì tenant không khớp. Key revoked thất bại dù các dữ liệu khác vẫn hợp lệ.

Đây là mô hình **policy sau khi credential đã được xác minh**, không phải thư viện xử lý API key hoàn chỉnh. Hệ thống thật còn phải lấy trạng thái principal/tenant và quyền từ nguồn tin cậy, kiểm resource ownership và xử lý cache cập nhật quyền.

## 6. Cấp phát key với danh tính có cấu trúc

Một bảng key nội bộ có thể chứa:

| Trường | Mục đích |
| --- | --- |
| `key_id` | Public identifier dùng lookup/audit |
| `secret_digest` / `secret_mac` | Dấu xác minh secret, tránh lưu plaintext |
| `subject_type` | APPLICATION, SERVICE_ACCOUNT hoặc ACCOUNT |
| `subject_id` | ID bất biến của app/service/account |
| `owner_id` / `created_by` | Quản trị và truy vết |
| `tenant_id` / `environment` | Phân vùng tổ chức và triển khai |
| `allowed_scopes` | Giới hạn trên của quyền key |
| `status` / `created_at` / `expires_at` | Quản lý vòng đời |
| `revoked_at` / `last_used_at` | Thu hồi, vận hành |
| `rotation_group_id` | Liên kết credential cũ/mới nếu có chính sách rotation |

Metadata có thể trông như sau:

~~~yaml
keyId: ak_7c82d1
subjectType: SERVICE_ACCOUNT
subjectId: svc:billing-sync
ownerId: team:finance-platform
tenantId: tenant-a
environment: production
allowedScopes:
  - INVOICE_READ
  - INVOICE_WRITE
status: ACTIVE
expiresAt: "2027-01-01T00:00:00Z"
~~~

Đây là dữ liệu minh họa. **Không bao giờ tạo Authentication chỉ từ keyId/metadata công khai trước khi kiểm secret.** Trường `subject_id` là identity được gắn ở server; không lấy trực tiếp từ header hoặc body do client chọn.

Nếu một tài khoản bị xóa/disable, policy phải quyết định các key còn hoạt động có được tiếp tục dùng không. Với key cá nhân, thông thường cần vô hiệu hóa cùng tài khoản; với service key, có thể chuyển **owner quản trị** sang team mới mà giữ nguyên principal service, miễn là quy trình được phê duyệt và audit.

## 7. Sinh và lưu secret an toàn

Dùng bộ sinh số ngẫu nhiên mật mã như `SecureRandom` để tạo key có entropy lớn (ví dụ 256 bit). Có thể biểu diễn:

~~~text
ak_live_<public-id>.<random-secret>
~~~

Prefix và public-id giúp phân loại/tra bản ghi nhưng **không phải bằng chứng xác thực**. Phần random-secret mới là bí mật. Cần có ID riêng theo môi trường; key sản xuất không được sử dụng lại trong staging/dev.

Quy trình:

1. Server sinh public key ID duy nhất và secret ngẫu nhiên mật mã.
2. Lưu digest của secret có entropy cao (SHA-256) hoặc HMAC-SHA-256 với pepper được bảo vệ ngoài database, kèm metadata.
3. Hiển thị raw secret **một lần** cho client qua kênh bảo mật; không đưa vào log, trace, URL hoặc email không bảo vệ.
4. Khi request đến, kiểm format và giới hạn độ dài, tra bản ghi theo ID, tính lại digest/MAC và so sánh theo thời gian hằng trên digest bytes.
5. Kiểm status, expiry, principal, tenant, scope và resource policy trước khi chấp nhận request.

Với secret ngẫu nhiên đủ mạnh, digest mật mã nhanh có thể phù hợp vì brute force offline không thực tế. Password do người dùng tự chọn thường có entropy thấp nên cần bộ mã hóa mật khẩu chậm (Argon2/bcrypt/scrypt) theo chính sách riêng. Không dùng timestamp, username, hoặc random thông thường làm API key.

Ví dụ Java 17+ độc lập sinh secret **nhưng không in secret**:

~~~java
import java.security.SecureRandom;
import java.util.Base64;

public class ApiKeySecretDemo {
    public static void main(String[] args) {
        byte[] secret = new byte[32];
        new SecureRandom().nextBytes(secret);

        String encoded = Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(secret);

        System.out.println("Secret bytes = " + secret.length);
        System.out.println("Encoded characters = " + encoded.length());
        System.out.println("URL-safe = "
                + encoded.matches("[A-Za-z0-9_-]+"));
    }
}
~~~

Chạy:

~~~bash
javac ApiKeySecretDemo.java
java ApiKeySecretDemo
~~~

Stdout chính xác:

~~~text
Secret bytes = 32
Encoded characters = 43
URL-safe = true
~~~

Giá trị `encoded` không được in ra để tránh vô tình đưa secret vào terminal log. Chương trình này chỉ cho thấy khâu sinh secret; hệ thống thực cần thêm ID, database, digest/MAC, TTL, audit và quy trình cấp phát.

So sánh digest bytes bằng API có sẵn:

~~~java
boolean accepted = java.security.MessageDigest.isEqual(
        computedDigestBytes,
        storedDigestBytes);
~~~

Đây là **mảnh mã minh họa**; hai biến phải là mảng byte digest được tạo bằng cùng thuật toán, không phải raw password. So sánh thời gian hằng chỉ giải quyết một nguy cơ nhỏ; vẫn cần hạn chế thử sai, khóa truy cập và thông báo lỗi không tiết lộ key nào tồn tại.

Ưu tiên truyền key qua **header và HTTPS**, không đặt trong query string vì URL thường lọt vào access log, browser history, referrer, proxy và APM. Header chứa key cũng phải được redaction trong log/tracing. Secret nhúng trong frontend/mobile public không được xem là bí mật đáng tin.

## 8. Ánh xạ API key thành Spring Security principal

Spring Security dùng `Authentication` để biểu diễn principal và authorities. Ở ứng dụng xác thực API key, một principal có cấu trúc có thể là:

~~~text
ApiPrincipal
    type        = SERVICE_ACCOUNT
    subjectId   = svc:billing-sync
    tenantId    = tenant-a
    keyId       = ak_7c82d1
~~~

Sau khi xác minh key và policy, server có thể tạo `Authentication` đã xác thực, không giữ raw secret làm credentials. Authorities như `INVOICE_READ` và `INVOICE_WRITE` phải được tính từ **policy phía server**, không từ header `X-Scope` client tự cung cấp.

### 8.1. Filter minh họa cho Servlet

Tệp **ApiKeyAuthenticationFilter.java** dùng Spring Boot 3.x / Spring Security 6.x theo Servlet API Jakarta; có thể đưa vào project phù hợp. Interface `Verifier` là contract của hệ thống key store và policy: phải được triển khai bằng service an toàn.

~~~java
package demo.apikey;

import java.io.IOException;
import java.util.Enumeration;
import java.util.List;
import java.util.Optional;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    public record ApiPrincipal(
            String type, String subjectId, String tenantId, String keyId) {
    }

    public record VerifiedKey(
            ApiPrincipal principal, List<GrantedAuthority> authorities) {
    }

    @FunctionalInterface
    public interface Verifier {
        Optional<VerifiedKey> verify(String rawKey);
    }

    private final Verifier verifier;

    public ApiKeyAuthenticationFilter(Verifier verifier) {
        this.verifier = verifier;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        Enumeration<String> values = request.getHeaders("X-API-Key");
        if (!values.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String raw = values.nextElement();
        if (raw == null || raw.isBlank() || values.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Optional<VerifiedKey> verified = verifier.verify(raw);
        if (verified.isEmpty()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        VerifiedKey result = verified.get();
        var authentication = new UsernamePasswordAuthenticationToken(
                result.principal(), null, result.authorities());

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

**Giải thích bảo mật:**

- Không có header: filter chuyển tiếp; tầng authorization phải yêu cầu Authentication với API chỉ nhận key.
- Header lỗi hoặc verifier không xác thực: trả 401, **không** dựng một principal “anonymous-admin”.
- `Verifier.verify` phải kiểm raw secret, trạng thái key, subject và policy. Kết quả `VerifiedKey` chỉ chứa principal/authorities server đã xác minh.
- Constructor `UsernamePasswordAuthenticationToken(principal, null, authorities)` tạo đối tượng authenticated. Chỉ dùng **sau** bước xác minh; tuyệt đối không dùng từ dữ liệu key chưa kiểm tra.
- `SecurityContextHolder.createEmptyContext()` cô lập context mới; `finally` dọn ngữ cảnh thread đồng bộ.
- Verifier gặp lỗi database/KMS/timeout phải **fail closed**; không trả quyền dự phòng. Mảnh filter này không bao gồm async Servlet, tích hợp gateway, distributed tracing hoặc triển khai verifier thực tế.

Đây là code cho **Spring Security Servlet**. Không sao chép trực tiếp `OncePerRequestFilter` và `SecurityContextHolder` đồng bộ sang WebFlux; môi trường reactive dùng `SecurityWebFilterChain`, `ReactiveAuthenticationManager` và Reactor Context.

### 8.2. Giới hạn filter chain và quyền

Tệp **ApiSecurityConfig.java**:

~~~java
package demo.apikey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutFilter;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            ApiKeyAuthenticationFilter.Verifier verifier)
            throws Exception {

        return http
                .securityMatcher("/api/**")
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .exceptionHandling(errors -> errors
                        .authenticationEntryPoint((request, response, ex) ->
                                response.sendError(401)))
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/catalog/**")
                        .hasAuthority("CATALOG_READ")
                        .requestMatchers(HttpMethod.POST, "/api/invoices/**")
                        .hasAuthority("INVOICE_WRITE")
                        .anyRequest().denyAll())
                .addFilterAfter(
                        new ApiKeyAuthenticationFilter(verifier),
                        LogoutFilter.class)
                .build();
    }
}
~~~

Đây là class cấu hình Servlet trong Spring Boot, **không chạy độc lập với `javac`**. Cần bean triển khai `ApiKeyAuthenticationFilter.Verifier`, dependency `spring-boot-starter-security` và API controllers thực tế. Filter được khởi tạo trực tiếp trong security chain để tránh đăng ký hai lần qua `@Component`/Servlet container.

- `securityMatcher("/api/**")` chỉ chọn đường dẫn API; nếu app còn trang web, endpoint ngoài API phải có chain/bảo vệ khác.
- `SessionCreationPolicy.STATELESS` phù hợp với API dùng key ở mỗi request.
- Tắt CSRF trong ví dụ chỉ vì nhánh API này **không dùng cookie/browser session** để xác thực. Không áp dụng mù quáng cho endpoint dùng cookie.
- `hasAuthority` khớp chính xác chuỗi permission; `hasRole("ADMIN")` mặc định có quy ước tiền tố `ROLE_` khác.
- `anyRequest().denyAll()` từ chối các API path ngoài chính sách đã khai.
- Filter nên đứng trước authorization. Nếu dùng `AuthenticationManager`/`AuthenticationProvider`, trách nhiệm kiểm credential và tạo Authentication có thể được phân tách rõ hơn.

**Quan trọng:** HTTP-level authority là chưa đủ cho hệ thống nhiều tenant. Controller/service còn phải kiểm quyền truy cập trên **resource cụ thể**.

## 9. Tenant và resource owner trong nghiệp vụ

Giả sử `svc:billing-sync` thuộc tenant A và có authority `INVOICE_READ`. Nó gửi:

~~~http
GET /api/invoices/INV-100 HTTP/1.1
X-API-Key: <secret-cua-tenant-a>
~~~

Nếu hóa đơn `INV-100` thuộc tenant B, việc chỉ kiểm authority sẽ để lộ dữ liệu. Cần thêm điều kiện:

~~~text
principal.tenantId == invoice.tenantId
AND principal được phép truy cập loại hóa đơn này
AND keyScopes chứa INVOICE_READ
AND chính sách resource cho phép
~~~

Có thể triển khai kiểm tenant ở repository bằng truy vấn có cả `invoiceId` và `tenantId`, tránh tải nhầm dữ liệu của tenant khác rồi quên kiểm. Client không được tự chọn tenant bằng query parameter để bỏ giới hạn.

Tài nguyên có thể có owner khác tenant: hóa đơn thuộc customer:42 trong tenant A. Khi xử lý ủy quyền phức tạp, phải kiểm thêm account/project/resource ownership, ACL hoặc relationship policy. Không coi service account có tên “internal” là được truy cập toàn bộ dữ liệu.

## 10. Kiểm soát vòng đời credential và principal

Một API key nên có các trạng thái/hoạt động:

~~~text
CREATED
   |
   v
ACTIVE
   |--- ROTATING: key cũ + key mới cùng hợp lệ trong cửa sổ được duyệt
   |                     |
   |                     v
   |                 REVOKED key cũ
   |--- SUSPENDED
   |--- EXPIRED
   +--- REVOKED
~~~

Với key gắn với account, thay đổi trạng thái account phải ảnh hưởng tới key theo SLA đã thiết kế:

| Sự kiện | Chính sách cần xác định |
| --- | --- |
| User đổi mật khẩu | Key cá nhân có bị thu hồi hay vẫn hiệu lực? Cần quy định rõ |
| User bị khóa/disable | Key có thể bị vô hiệu hóa cùng tài khoản |
| User rời tenant | Key không còn truy cập tài nguyên tenant đó |
| User mất role | Quyền hiệu lực của key giảm theo |
| Service ngừng hoạt động | Thu hồi service key |
| Team đổi người quản lý | Chuyển owner quản trị, giữ principal service nếu phù hợp |
| Nghi rò secret | Thu hồi ngay, cấp credential mới, kiểm tra audit |
| Key hết hạn | Từ chối xác thực và dùng cơ chế rotation |

**Cache là bẫy phổ biến:** nếu API xác minh key bằng kết quả cache trong 30 phút, việc thu hồi khẩn cấp có thể chưa có hiệu lực ngay. Cần thiết kế TTL/invalidation hoặc tra trạng thái nhạy cảm theo mỗi request.

### Xoay vòng không đổi principal

1. Tạo key mới với **cùng principal** và chính sách quyền đã được duyệt lại.
2. Phân phối secret mới qua secret manager/CI/CD an toàn.
3. Kiểm thử credential mới, quan sát public key ID trong audit.
4. Cho hai key cùng hoạt động ngắn hạn khi cần chuyển đổi.
5. Thu hồi key cũ, xác minh không còn request hợp lệ sử dụng nó.

Việc key cũ và mới cùng đại diện một service không có nghĩa hai secret được phép chia sẻ với mọi service khác. **Key và principal là hai vòng đời khác nhau**: có thể rotate secret mà không đổi danh tính service.

## 11. Quota, billing và audit theo key hay theo account?

API key thường còn dùng cho rate limiting, billing hoặc analytics. Cần tách mục đích:

- **Rate limit theo keyId**: giới hạn một credential cụ thể.
- **Rate limit theo principalId**: giới hạn tổng request của một app/service/account qua nhiều key.
- **Rate limit theo tenant**: hạn mức cấp tổ chức.
- **Billing owner**: entity chịu phí có thể là tổ chức hoặc project, khác actor principal.
- **Authorization**: quyết định quyền truy cập resource; **không** suy ra từ việc key có quota còn lại.

Nếu key một dịch vụ dùng chung ở nhiều môi trường, audit keyId chỉ cho biết credential được dùng, không đủ xác định instance. Nên cấp key riêng theo deployment/environment hoặc dùng workload identity để tăng khả năng truy vết.

Ví dụ log audit đã loại secret:

~~~json
{
  "requestId": "req-8f42",
  "keyId": "ak_service_01",
  "actorType": "SERVICE_ACCOUNT",
  "actorId": "svc:billing-sync",
  "tenantId": "tenant-a",
  "action": "INVOICE_WRITE",
  "decision": "DENY",
  "reasonCode": "RESOURCE_TENANT_MISMATCH"
}
~~~

Không log raw `X-API-Key`, HMAC key, digest bí mật, private key hoặc header Authorization chứa credential. Proxy/APM, access logs và exception messages cần có quy tắc redaction.

Nếu gateway xác minh key rồi chuyển thông tin principal xuống backend, backend chỉ được tin **header nội bộ từ gateway đã xác thực** và phải ngăn client Internet tự giả header đó. Kênh gateway–backend cần có cơ chế tin cậy và kiểm soát tuyến truy cập trực tiếp.

## 12. So sánh API key với các cơ chế xác thực khác

| Cơ chế | Danh tính thường đại diện | Đặc điểm |
| --- | --- | --- |
| API key opaque | App, service hoặc account theo policy | Bearer secret, lifecycle do hệ thống tự quản |
| OAuth2 client credentials | Client/service machine-to-machine | Token có thời hạn/scope, authorization server phát hành |
| OAuth2 Authorization Code + OIDC | User và client được ủy quyền | Có quy trình đăng nhập/ủy quyền người dùng |
| JWT access token | Subject theo issuer/audience/claims đã xác minh | Ký số, thời hạn; cần kiểm issuer, audience, signature |
| mTLS client certificate | Machine/workload/device theo PKI | Chứng minh private key qua TLS |
| Session cookie | User browser tương tác | Phụ thuộc cookie/session và chính sách CSRF |

API key **không tự biến thành JWT** chỉ vì chuỗi được gửi trong header `Authorization`. Nếu dùng Spring Security `oauth2ResourceServer().jwt()`, phải thật sự có JWT được phát hành và xác minh theo cấu hình tương ứng. Với key opaque do ứng dụng tự cấp, cần verifier/key store hoặc cơ chế token introspection do hệ thống hỗ trợ.

Khi bài toán đòi hỏi delegation của user, token sống ngắn, nhiều downstream services, tenant phức tạp hoặc chứng minh danh tính workload mạnh hơn, nên cân nhắc giao thức/hạ tầng chuyên biệt. API key vẫn phù hợp cho nhiều tích hợp đơn giản nếu quản lý scope, expiry, thu hồi và audit đúng.

## 13. Lỗi phổ biến

| Lỗi | Hậu quả | Hướng xử lý |
| --- | --- | --- |
| Coi mọi key là user hiện tại | Audit sai, mất ranh giới user/service | Lưu principalType và subjectId rõ ràng |
| Client tự gửi userId/role | Giả mạo danh tính | Resolve principal/authority ở server |
| Gán admin cho mọi key hợp lệ | Bị lộ key gây truy cập rộng | Least privilege, scope và resource policy |
| Dùng một key trên mọi tenant | Rò dữ liệu, khó thu hồi | Bind key với tenant, check resource tenant |
| Dùng key public trong frontend làm secret | Secret dễ bị trích xuất | Cơ chế cho public client thích hợp |
| Lưu secret plaintext | Lộ toàn bộ credential từ database | Digest/HMAC và secret lifecycle |
| Đưa key vào URL/query | Log và history lộ secret | Header qua HTTPS, redaction |
| Key không expiry/revoke | Lộ key tồn tại quá lâu | TTL, rotate, revoke |
| Key còn quyền sau khi account mất role | Bỏ qua quản trị quyền account | Lấy giao giữa key scope và entitlement hiện tại |
| Key revoked nhưng cache vẫn cho qua | Thu hồi không có hiệu lực kịp | Invalidation hoặc TTL có SLA |
| Quá tin gateway header | Client giả actor đã xác thực | Chỉ tin gateway trên kênh nội bộ được bảo vệ |
| Dùng một key cho nhiều actor | Không biết ai thực thi | Key riêng theo ứng dụng/service/tenant |
| Đổi subjectId của key đang phát hành | Credential cũ vô tình thành danh tính mới | Cấp key mới và ghi audit migration |

## 14. Kiểm thử theo semantics đại diện

Nên có các test cho cả credential, principal và quyền:

| Test | Kết quả mong đợi |
| --- | --- |
| Không gửi key đến API-key-only endpoint | 401 |
| Gửi key sai/hết hạn/bị thu hồi | Không có authenticated principal |
| Key APPLICATION hợp lệ | Principal type APPLICATION, subjectId đúng app |
| Key SERVICE_ACCOUNT hợp lệ | Principal type SERVICE_ACCOUNT, đúng service |
| Key ACCOUNT của Lan | Principal là account Lan nhưng audit ghi authenticationMethod=API_KEY |
| Client gửi thêm X-Acting-User: admin | Không thay principal nếu không có delegation đã xác thực |
| Key scope thiếu thao tác ghi | 403 |
| Key có scope nhưng principal mất quyền | 403 |
| Key tenant A truy cập tenant B | 403 hoặc 404 theo policy bảo vệ sự tồn tại resource |
| Service principal bị disable | Không tiếp tục cho sử dụng key |
| Thu hồi một trong hai key cùng principal | Key bị thu hồi thất bại, key còn lại hoạt động |
| Rotation trong giai đoạn chồng lấp | Cả key được duyệt hoạt động, sau đó key cũ bị vô hiệu |
| Database/key store gặp sự cố | Fail closed, không tự cấp role |
| Header trùng lặp hoặc quá dài | Bị từ chối theo validation |
| API gateway bị bypass | Backend không tin header giả |
| Log/APM chứa raw key | Test phát hiện và yêu cầu redaction |

Có thể dùng MockMvc để kiểm FilterChain/Authentication trong Spring Boot Servlet, test repository/key lifecycle bằng integration test, và unit test riêng policy scope/tenant. Nếu hệ thống phụ thuộc gateway, cần thử đường truy cập trực tiếp vào backend để chắc chắn không thể giả identity.

## 15. Checklist trước triển khai

1. **Identity:** loại principal là APPLICATION, SERVICE_ACCOUNT hay ACCOUNT? Subject ID có ổn định/duy nhất theo tenant?
2. **Ownership:** ai tạo, quản lý, rotate/revoke key? Owner có bị nhầm với actor không?
3. **Secrets:** key có entropy cao, lưu digest/HMAC và hiển thị một lần? Có bảo vệ ở transit/log không?
4. **Permissions:** keyScopes, principalEntitlements, tenant và resource policy có được áp dụng đồng thời?
5. **Runtime:** verifier có fail closed và chỉ cấp Authentication sau xác minh không? Filter chain có đúng scope?
6. **Lifecycle:** expiry, revoke, rotation và tài khoản bị disable có tác dụng kịp thời?
7. **Audit:** có ghi key ID, actor, tenant, resource, hành động và decision mà không ghi secret?
8. **Delegation:** nếu cần hành động thay user, đã có cơ chế ủy quyền riêng hay chưa?

Kết luận: **API key xác thực một credential; bản ghi cấp phát và chính sách phía server xác định credential đó đại diện cho ứng dụng, dịch vụ hay tài khoản.** Chỉ sau khi xác định đúng principal và kiểm tra đồng thời scopes, entitlement, tenant, resource policy, hệ thống mới được cho phép thao tác. Không đánh đồng key hợp lệ với danh tính người dùng đang tương tác hoặc quyền quản trị mặc định.

### Tài liệu tham khảo chính thức

- Spring Security — Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security — Security Filter Chain and Custom Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Security — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Authentication API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/Authentication.html
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
