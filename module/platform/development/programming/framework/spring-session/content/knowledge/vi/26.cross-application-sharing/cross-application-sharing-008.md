# Cách ly tenant bằng thiết kế định danh, kho và kiểm tra quyền

Spring Session cho phép nhiều instance ứng dụng dùng chung một kho session như Redis hoặc JDBC. Khả năng chia sẻ này giúp scale ngang và có thể hỗ trợ một số kiến trúc nhiều ứng dụng. Tuy nhiên, khi hệ thống phục vụ nhiều tenant, việc dùng chung kho dữ liệu không có nghĩa là các tenant được phép dùng chung trạng thái phiên. Mỗi session phải gắn với đúng danh tính và tenant; mọi request phải được kiểm tra quyền trong phạm vi tenant đó.

Ranh giới tenant cần được bảo vệ ở nhiều lớp: định danh tenant, cookie hoặc header chứa session ID, namespace hoặc repository, dữ liệu session, principal, truy vấn nghiệp vụ và quy trình logout. Nếu chỉ thêm tenantId vào URL hoặc session attribute mà không kiểm tra ở server, ứng dụng vẫn có thể mắc lỗi truy cập chéo tenant (cross-tenant access).

## 1. Phân biệt ứng dụng, tenant, principal và session

Bốn khái niệm này có vai trò khác nhau:

- **Ứng dụng (application):** một hệ thống hoặc client triển khai, ví dụ portal quản trị và API bán hàng.
- **Tenant:** một tổ chức hoặc không gian dữ liệu độc lập trong ứng dụng, ví dụ công ty A và công ty B.
- **Principal:** danh tính đã xác thực, thường là người dùng hoặc service account.
- **Session:** trạng thái đăng nhập của một client cụ thể, được nhận diện bằng session ID.

Một principal có thể thuộc một tenant hoặc được cấp quyền ở nhiều tenant. Một principal cũng có thể có nhiều session trên các thiết bị khác nhau. Session ID không phải tenant ID và không nên được dùng để suy ra tenant bằng cách phân tích chuỗi ID.

Ví dụ:

~~~text
Application: billing-portal
  Tenant: tenant-17
    Principal: user-42
      Session: opaque-session-id-A
      Session: opaque-session-id-B
  Tenant: tenant-29
    Principal: user-88
      Session: opaque-session-id-C
~~~

Session ID nên là định danh ngẫu nhiên, khó đoán và không chứa username, tenant name hoặc thông tin nghiệp vụ. Server lưu mối liên hệ giữa session, principal và tenant trong dữ liệu được kiểm soát.

## 2. Nguyên tắc cách ly tenant

Thiết kế an toàn cần bảo đảm:

1. Tenant được xác định từ nguồn đáng tin cậy và được kiểm tra với danh tính đã xác thực.
2. Một session đã gắn với tenant không thể tự chuyển sang tenant khác chỉ vì client thay đổi URL hoặc header.
3. Mọi truy vấn dữ liệu nghiệp vụ đều có điều kiện tenant ở phía server.
4. Repository hoặc namespace không làm các ứng dụng/tenant đọc nhầm session của nhau.
5. Cookie và header không vô tình gửi cùng một session ID đến những ứng dụng hoặc tenant không liên quan.
6. Logout và thu hồi session có phạm vi rõ ràng: một thiết bị, một principal, một tenant hay toàn bộ tài khoản.
7. Log, backup và công cụ quản trị cũng giữ nguyên ranh giới tenant.

Không xem tenantId do client gửi là bằng chứng quyền truy cập. Header X-Tenant-ID, query parameter, subdomain hoặc path chỉ là thông tin yêu cầu ngữ cảnh. Backend phải ánh xạ nó sang tenant hợp lệ và xác minh principal có quyền truy cập tenant đó.

## 3. Xác định tenant từ host hoặc miền truy cập

Nhiều hệ thống dùng subdomain hoặc custom domain để xác định tenant:

~~~text
tenant-17.example.com
tenant-29.example.com
customer-a.example.net
~~~

Host có thể là đầu mối thuận tiện để tìm tenant, nhưng không tự nó chứng minh người dùng có quyền. Quy trình nên là:

1. Đọc host đã được chuẩn hóa từ request sau khi xác thực proxy/forwarded headers.
2. Tra cứu host trong tenant registry để lấy tenant ID nội bộ.
3. Xác thực người dùng.
4. Kiểm tra principal có membership hoặc quyền trong tenant đó.
5. Gắn tenant đã xác minh vào request/security context cho các tầng sau.

Không lấy X-Forwarded-Host hoặc X-Forwarded-Proto từ bất kỳ client nào. Chỉ tin forwarded headers từ reverse proxy được cấu hình tin cậy. Nếu không, attacker có thể giả host để chọn tenant hoặc làm sai cookie domain.

Với ứng dụng dùng một host chung và header X-Tenant-ID, backend phải kiểm tra tenant ID đó có nằm trong tập tenant mà principal được phép truy cập. Không dùng trực tiếp giá trị header làm điều kiện duy nhất cho repository hoặc query.

## 4. Gắn tenant với principal và session

Sau khi xác thực và chọn tenant hợp lệ, ứng dụng có thể lưu tenant ID nội bộ trong SecurityContext/principal và trong session để kiểm tra tính nhất quán giữa các request.

Ví dụ principal có tenant:

~~~java
public interface TenantAwarePrincipal {
    String getTenantId();
    String getSubjectId();
}
~~~

Khi đăng nhập thành công, authentication flow có thể lưu tenant đã được xác minh vào session:

~~~java
import jakarta.servlet.http.HttpSession;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

class TenantAwareLoginSuccessHandler
        extends SavedRequestAwareAuthenticationSuccessHandler {

    @Override
    public void onAuthenticationSuccess(
            jakarta.servlet.http.HttpServletRequest request,
            jakarta.servlet.http.HttpServletResponse response,
            Authentication authentication)
            throws java.io.IOException, jakarta.servlet.ServletException {

        Object principal = authentication.getPrincipal();
        if (principal instanceof TenantAwarePrincipal tenantPrincipal) {
            HttpSession session = request.getSession();
            session.setAttribute("APP_TENANT_ID",
                tenantPrincipal.getTenantId());
        }

        super.onAuthenticationSuccess(request, response, authentication);
    }
}
~~~

Ví dụ minh họa hợp đồng principal; ứng dụng cần bảo đảm tenant trong principal đã được xác minh từ membership/identity service trước khi success handler được gọi. Không ghi tenant vào session bằng cách tin một form field hoặc header chưa được kiểm tra.

Tenant ID trong session là dữ liệu hỗ trợ kiểm tra, không phải cơ chế authorization độc lập. Mỗi request vẫn cần kiểm tra authentication và quyền hiện tại. Nếu quyền của người dùng bị thu hồi, session cũ không được tiếp tục cấp quyền chỉ vì attribute APP_TENANT_ID còn tồn tại.

## 5. Kiểm tra tenant ở đầu mỗi request

Với ứng dụng Servlet, có thể dùng filter hoặc thành phần authorization của Spring Security để xác nhận tenant được request yêu cầu khớp với tenant trong principal và session.

Ví dụ logic kiểm tra:

~~~java
String requestedTenant = tenantResolver.resolveValidatedTenant(request);
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

if (!(authentication.getPrincipal() instanceof TenantAwarePrincipal principal)) {
    throw new AccessDeniedException("Tenant-aware principal required");
}

String authenticatedTenant = principal.getTenantId();
HttpSession session = request.getSession(false);
String sessionTenant = session == null
    ? null
    : (String) session.getAttribute("APP_TENANT_ID");

if (!authenticatedTenant.equals(requestedTenant)
        || !authenticatedTenant.equals(sessionTenant)) {
    throw new AccessDeniedException("Tenant context mismatch");
}
~~~

Đây là đoạn logic minh họa, cần đặt sau khi Spring Security đã thiết lập Authentication và trước khi controller truy cập dữ liệu tenant. Nếu ứng dụng cho phép một principal truy cập nhiều tenant, không so sánh cứng với một tenant duy nhất; thay vào đó xác minh membership cho tenant được chọn và quản lý tenant context theo request một cách rõ ràng.

Không dùng session attribute làm nguồn duy nhất để xác định người dùng. Principal đã xác thực và quyền hiện hành phải là nguồn quyết định. Nếu session bị thiếu, hết hạn hoặc tenant attribute không khớp, từ chối request được bảo vệ và yêu cầu xác thực/chọn tenant lại theo quy trình.

## 6. Cách ly kho session theo ứng dụng và tenant

Spring Session cung cấp repository abstraction, nhưng không tự động tạo ranh giới tenant chỉ vì ứng dụng lưu tenantId trong session. Cần chọn mô hình lưu trữ phù hợp với mức cách ly yêu cầu.

### Một repository chung, namespace theo ứng dụng

Các instance của cùng một ứng dụng dùng chung Redis namespace hoặc cùng schema/bảng JDBC. Session chứa tenant ID đã xác minh; authorization kiểm tra tenant trên từng request.

Ưu điểm:

- Dễ vận hành và tiết kiệm tài nguyên.
- Phù hợp khi các tenant cùng một trust boundary và cùng chính sách vận hành.
- Các instance có thể chia sẻ session mà không cần sticky routing.

Giới hạn:

- Lỗi authorization có thể làm lộ dữ liệu giữa tenant.
- ACL của kho thường cấp quyền cho cả ứng dụng, không tự tách theo từng tenant.
- Backup, restore và thao tác quản trị có phạm vi rộng.

Đây là mô hình phổ biến cho multi-tenant SaaS, nhưng yêu cầu kiểm tra tenant nhất quán ở mọi tầng dữ liệu.

### Repository hoặc database tách riêng theo tenant

Với yêu cầu cách ly cao, có thể dùng Redis deployment riêng, database riêng hoặc schema/database user riêng cho từng tenant. Mỗi nhóm instance được cấu hình kết nối đến kho tương ứng sau khi tenant đã được xác định bằng nguồn đáng tin cậy.

Ưu điểm:

- Giảm phạm vi ảnh hưởng khi credential hoặc dữ liệu một tenant bị lộ.
- Có thể áp dụng retention, backup, key và quyền quản trị riêng.
- Dễ đáp ứng yêu cầu lưu trữ theo vùng hoặc hợp đồng khách hàng.

Đổi lại, cần quản lý nhiều repository, connection pool, backup, migration và giám sát. Việc chọn repository theo tenant đòi hỏi tenant context phải được xác định trước khi tải session. Không thể lấy tenant từ một session chưa đọc rồi mới quyết định kho dùng để đọc session đó; đây là vòng phụ thuộc cần thiết kế riêng.

### Không giả định Redis logical database là ranh giới bảo mật

Redis logical database hoặc key prefix có thể giúp tổ chức dữ liệu nhưng không thay thế ACL, network isolation và credential riêng. Trong Redis Cluster, logical database khác 0 không được hỗ trợ như Redis standalone. Nếu cần cách ly mạnh, cân nhắc deployment/cluster hoặc credential và ACL được phân tách theo khả năng nền tảng.

Với JDBC, schema hoặc database riêng có thể tạo ranh giới tốt hơn nếu quyền DB được cấu hình đúng. Chỉ đổi table prefix mà mọi tenant vẫn dùng chung một tài khoản có quyền đọc toàn bộ bảng không tạo được isolation mạnh.

## 7. Namespace Redis và schema JDBC

Với Redis repository, namespace giúp tách session của ứng dụng:

~~~yaml
spring:
  session:
    redis:
      namespace: billing-portal:session
~~~

Tất cả instance của billing-portal phải dùng đúng namespace. Một ứng dụng khác nên có namespace riêng, ví dụ inventory-api:session. Không để hai ứng dụng có mô hình principal, serializer hoặc security context khác nhau dùng chung namespace chỉ vì chúng kết nối cùng Redis.

Namespace tách ứng dụng, không tự động tách tenant bên trong ứng dụng. Nếu cần tenant-level storage isolation, phải thiết kế thêm repository/database separation hoặc cơ chế phân vùng được hỗ trợ và kiểm thử.

Với JDBC, có thể tách schema hoặc database theo ứng dụng/tenant. Nếu dùng schema chung và bảng Spring Session chuẩn, cần kiểm tra cách repository truy cập schema, quyền SQL và migration. Không giả định chỉ thêm cột tenant_id vào bảng chuẩn là repository tự động thêm điều kiện lọc; Spring Session JDBC mặc định không phải một hệ thống row-level tenant policy tổng quát.

## 8. Cookie và domain có thể làm ranh giới tenant bị mở rộng

Cookie được gửi theo domain và path. Nếu mọi tenant dùng subdomain dưới cùng một domain, cookie đặt Domain=.example.com có thể được gửi đến nhiều subdomain. Điều này có thể làm session ID của tenant A xuất hiện trong request đến host tenant B nếu các điều kiện cookie phù hợp.

Để giảm rủi ro:

- Ưu tiên host-only cookie khi mỗi tenant có host riêng.
- Không đặt Domain ở parent domain nếu không cần chia sẻ cookie giữa subdomain.
- Dùng cookie name riêng giữa các ứng dụng chạy chung host/path.
- Cân nhắc tiền tố __Host- cho cookie bảo mật: cần Secure, Path=/ và không có thuộc tính Domain.
- Giữ HttpOnly, Secure và SameSite phù hợp.
- Kiểm tra thực tế header Set-Cookie và Cookie qua reverse proxy.

Ví dụ cấu hình host-only cookie có tên riêng:

~~~java
DefaultCookieSerializer serializer = new DefaultCookieSerializer();
serializer.setCookieName("__Host-BILLING_SESSION");
serializer.setCookiePath("/");
serializer.setUseHttpOnlyCookie(true);
serializer.setUseSecureCookie(true);
serializer.setSameSite("Lax");
// Không gọi setDomainName(): cookie giữ phạm vi host hiện tại.
~~~

Tiền tố __Host- yêu cầu cookie phải Secure, Path=/ và không có Domain. Xác nhận browser hỗ trợ và cấu hình ứng dụng đáp ứng đầy đủ điều kiện. Nếu cần cookie chia sẻ giữa subdomain cho một luồng đăng nhập chung, đó là quyết định trust boundary; không nên bật rộng chỉ để tránh đăng nhập lại.

Path không phải ranh giới bảo mật mạnh. Ứng dụng khác cùng host có thể có các đường dẫn và cookie trùng tên; cần cookie name riêng hoặc tách host khi có thể.

## 9. Chia sẻ session giữa nhiều ứng dụng có thực sự cần thiết?

Hai ứng dụng dùng chung Redis không có nghĩa là nên dùng chung cùng một session ID và toàn bộ session attributes. Nếu ứng dụng A và B có quyền, vòng đời, serializer hoặc mức tin cậy khác nhau, việc dùng chung session có thể khiến:

- Ứng dụng B đọc SecurityContext hoặc thuộc tính do A tạo.
- Thay đổi class/serializer ở A làm B không giải mã được session.
- Logout ở một ứng dụng ảnh hưởng ngoài ý muốn đến ứng dụng kia.
- Một lỗi authorization ở ứng dụng yếu hơn mở rộng quyền sang ứng dụng khác.
- Cookie dùng chung bị gửi đến nhiều ứng dụng cùng domain.

Với các ứng dụng độc lập, lựa chọn thường an toàn hơn là mỗi ứng dụng có session riêng, còn xác thực tập trung qua OpenID Connect/OAuth 2.0 hoặc Identity Provider. Người dùng đăng nhập một lần ở Identity Provider; từng ứng dụng tạo session riêng sau khi xác minh token/identity assertion. Logout toàn cục được xử lý bằng cơ chế logout/token revocation phù hợp, không cần chia sẻ trực tiếp serialized HttpSession.

Chỉ chia sẻ cùng một Spring Session khi các ứng dụng nằm trong cùng trust boundary, có mô hình bảo mật tương thích, dùng cùng cấu trúc dữ liệu và có yêu cầu rõ ràng. Phải giới hạn dữ liệu session ở hợp đồng chung nhỏ, tránh để một ứng dụng có thể ghi các thuộc tính mà ứng dụng khác diễn giải thành quyền cao hơn.

## 10. Định danh session không thay thế authorization

Một session hợp lệ chứng minh request có trạng thái đăng nhập tương ứng; nó không chứng minh người dùng có quyền truy cập mọi tenant hoặc mọi tài nguyên.

Mỗi thao tác dữ liệu cần kiểm tra:

- Principal hiện tại là ai?
- Principal thuộc tenant nào hoặc có membership ở tenant nào?
- Tài nguyên được yêu cầu thuộc tenant nào?
- Principal có quyền thực hiện hành động cụ thể trên tài nguyên đó không?

Ví dụ truy vấn repository phải ràng buộc tenant:

~~~java
Optional<Invoice> findByTenantIdAndId(
    String tenantId,
    UUID invoiceId
);
~~~

Service lấy tenantId từ tenant context đã được xác minh, không lấy trực tiếp từ request body:

~~~java
Invoice loadInvoice(UUID invoiceId, TenantContext tenantContext) {
    return invoiceRepository
        .findByTenantIdAndId(tenantContext.tenantId(), invoiceId)
        .orElseThrow(ResourceNotFoundException::new);
}
~~~

Nếu query chỉ dùng invoiceId mà không ràng buộc tenant, người dùng tenant A có thể thử ID của tài nguyên tenant B. Đây là lỗi IDOR/cross-tenant access dù session của A hoàn toàn hợp lệ.

Áp dụng nguyên tắc tương tự cho cache key, file object storage, message queue, scheduled job, export, search index và WebSocket destination. Tenant boundary phải được duy trì xuyên suốt mọi tầng, không chỉ trong session.

## 11. Chuyển tenant trong cùng một tài khoản

Một người dùng có thể là thành viên của nhiều tenant. Việc chuyển từ tenant A sang tenant B phải là một thao tác được xác thực và kiểm soát:

1. Người dùng yêu cầu chuyển tenant.
2. Backend kiểm tra membership và quyền của principal với tenant đích.
3. Backend thay đổi tenant context theo quy trình có chủ đích.
4. Xoay session ID hoặc tạo session mới để giảm rủi ro session fixation và nhầm trạng thái cũ.
5. Xóa các attribute đặc thù tenant cũ hoặc khởi tạo session sạch cho tenant mới.
6. Ghi audit event gồm principal, tenant cũ, tenant mới và kết quả, không ghi session ID.

Không chỉ ghi đè APP_TENANT_ID dựa trên header rồi tiếp tục dùng các attribute cũ. Giỏ hàng, quyền, workflow hoặc cache key thuộc tenant A có thể bị sử dụng nhầm trong tenant B.

Nếu yêu cầu cách ly cao, cân nhắc một session riêng cho mỗi tenant hoặc yêu cầu đăng nhập lại khi chuyển tenant. Nếu principal có nhiều membership, quyền phải được kiểm tra lại theo tenant đích ở mọi request.

## 12. Logout và thu hồi session theo tenant

Cần định nghĩa rõ phạm vi logout:

- Logout thiết bị hiện tại: invalidate session hiện tại.
- Logout mọi thiết bị của principal trong một tenant: tìm và thu hồi các session có principal/tenant tương ứng.
- Logout mọi tenant của principal: thu hồi toàn bộ session gắn với principal trên mọi tenant.
- Khóa tài khoản: chặn xác thực mới và thu hồi session theo chính sách toàn hệ thống.

Không xóa tất cả session có cùng username nếu username có thể tồn tại ở nhiều tenant hoặc không phải định danh toàn cục. Principal key nên bao gồm tenant ID hoặc một subject ID toàn cục không nhập nhằng.

Với repository indexed, principal name có thể được tạo theo quy ước tenant-qualified, ví dụ tenant-17:user-42. Quy ước này phải ổn định, không chứa dữ liệu bí mật và được resolver áp dụng nhất quán. Nếu dùng subject ID toàn cục, vẫn cần kiểm tra tenant membership trong authorization.

Thao tác thu hồi nhiều session cần xử lý race với login mới. Nếu cần bảo đảm logout mọi nơi, dùng authentication version/session generation hoặc trạng thái account-level revocation bên ngoài snapshot session hiện tại.

## 13. Serializer và dữ liệu session giữa các ứng dụng

Khi nhiều ứng dụng đọc cùng repository, serializer là một phần của hợp đồng dữ liệu. Session có thể chứa class từ package riêng của ứng dụng A mà ứng dụng B không có hoặc có phiên bản khác. Điều này có thể gây lỗi deserialize hoặc tạo ra cách diễn giải dữ liệu không tương thích.

Nguyên tắc:

- Không chia sẻ serialized session giữa ứng dụng độc lập chỉ vì cùng dùng Redis/JDBC.
- Nếu buộc phải chia sẻ, định nghĩa DTO/attribute contract nhỏ, ổn định và có version.
- Không lưu trực tiếp entity ORM, request object hoặc object graph nội bộ.
- Không dùng tên attribute trùng nhau cho ý nghĩa khác nhau giữa ứng dụng.
- Kiểm tra serializer compatibility trong rolling deployment.
- Không cho ứng dụng ghi attribute mà ứng dụng khác hiểu thành quyền hoặc trạng thái xác thực.

Namespace riêng theo ứng dụng thường là lựa chọn mặc định. Nếu cần trao đổi danh tính giữa ứng dụng, dùng token/assertion có chữ ký hoặc giao thức SSO chuẩn, thay vì dùng session attributes như một API chia sẻ không chính thức.

## 14. Kiểm thử cách ly tenant

Kiểm thử cần chứng minh tenant A không thể đọc hoặc sửa dữ liệu của tenant B dù có session hợp lệ của chính A.

| Kịch bản | Thao tác | Kết quả cần xác nhận |
| --- | --- | --- |
| Tenant đúng | Đăng nhập user A trên tenant A và đọc tài nguyên A | Request được phép theo quyền |
| Giả tenant header | User A gửi X-Tenant-ID của B | Bị từ chối nếu A không có membership B |
| Giả host/forwarded host | Gửi host không được tenant registry ánh xạ hoặc forged forwarded header | Không thể chọn tenant tùy ý |
| Cookie giữa subdomain | Dùng cookie của tenant A gửi đến host B | Host B không nhận session A nếu thiết kế yêu cầu host isolation |
| Repository namespace | Tạo session ở app A rồi truy cập app B | B không đọc được session A nếu namespace được tách |
| Principal trùng username | Hai tenant có username giống nhau | Không nhầm principal hoặc thu hồi session chéo tenant |
| IDOR | User A yêu cầu resource ID thuộc B | Query có tenant predicate và từ chối truy cập |
| Chuyển tenant | User có membership A/B chuyển sang B | Quyền được kiểm tra lại, session ID được xoay và state A không rò sang B |
| Logout tenant-scoped | Thu hồi session của A | Session của B không bị xóa ngoài ý muốn |
| Restore backup | Khôi phục snapshot cũ | Session bị thu hồi và tenant mapping được kiểm tra trước khi mở traffic |
| Rolling deployment | Các phiên bản đọc cùng session contract | Serializer và tenant context tương thích |
| Cache/message isolation | Truy vấn cache hoặc subscribe destination tenant khác | Không thể đọc dữ liệu hoặc message ngoài tenant |

Nên có integration test với Redis/JDBC thật và nhiều ứng dụng hoặc nhiều instance. Mock SecurityContext không đủ để chứng minh cookie domain, namespace, serializer và repository isolation hoạt động đúng.

## 15. Giám sát và vận hành

Theo dõi các chỉ số có thể phát hiện truy cập chéo tenant:

- Số request bị từ chối do tenant context mismatch.
- Tần suất tenant ID từ host/header không ánh xạ được.
- Session lookup miss theo namespace.
- Lỗi deserialize hoặc serializer version mismatch.
- Số lần principal có nhiều tenant membership.
- Số lần chuyển tenant và thu hồi session.
- Truy vấn không có tenant predicate nếu hệ thống có thể phát hiện.
- Cấu hình cookie, namespace và repository giữa các replica.

Log nên chứa tenant ID nội bộ và request correlation ID khi chính sách cho phép, nhưng không chứa session ID, cookie, token hoặc serialized attributes. Với dữ liệu nhiều tenant, kiểm soát quyền truy cập dashboard và log để một tenant không thể xem telemetry riêng của tenant khác nếu đó là dữ liệu nhạy cảm.

Backup/restore cần giữ ranh giới tenant. Không khôi phục snapshot của tenant này vào namespace hoặc database của tenant khác. Nếu restore có thể làm sống lại session đã logout, áp dụng quy trình thu hồi sau restore trước khi cho phép traffic.

## 16. Lỗi thường gặp

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Người dùng tenant A đọc được dữ liệu B | Query không ràng buộc tenant hoặc tin tenant ID từ client | Lấy tenant từ context đã xác minh và thêm tenant predicate |
| Cookie session dùng được trên subdomain khác | Cookie Domain đặt ở parent domain quá rộng | Dùng host-only cookie hoặc tách domain/cookie theo trust boundary |
| Ứng dụng B đọc được session của A | Hai ứng dụng dùng chung namespace và serializer | Tách namespace; dùng SSO chuẩn thay vì chia sẻ HttpSession |
| Hai tenant cùng username bị nhập nhằng | Principal name không tenant-qualified hoặc subject không toàn cục | Dùng subject ổn định và tenant-aware identity mapping |
| Chuyển tenant vẫn thấy giỏ hàng cũ | Session attributes tenant cũ không được xóa hoặc cách ly | Xoay ID/tạo session mới và làm sạch state theo tenant |
| Tenant header giả mạo được chấp nhận | Backend dùng header làm nguồn quyền | Kiểm tra membership từ Authentication và tenant registry |
| Repository riêng bị chọn sai | Tenant routing dựa trên dữ liệu chưa xác thực hoặc cấu hình lệch | Xác định tenant từ nguồn tin cậy trước khi chọn repository |
| Logout tenant này làm logout tenant khác | Thu hồi theo username không đủ định danh | Xác định principal và tenant scope rõ ràng |
| Lỗi deserialize giữa ứng dụng | Session chứa class/serializer không tương thích | Tách namespace hoặc dùng contract DTO có version |

## 17. Checklist thiết kế

- [ ] Định nghĩa rõ application ID, tenant ID, subject/principal và session ID.
- [ ] Dùng session ID ngẫu nhiên, không nhúng tenant hoặc thông tin cá nhân vào ID.
- [ ] Xác định tenant từ host/registry hoặc membership đã xác minh; không tin header đơn lẻ.
- [ ] Gắn tenant đã xác minh với principal và kiểm tra tính nhất quán ở request.
- [ ] Bổ sung tenant predicate cho mọi truy vấn dữ liệu và cache key.
- [ ] Tách namespace theo ứng dụng; cân nhắc repository/database riêng cho tenant cần isolation mạnh.
- [ ] Không xem Redis key prefix hoặc logical DB là ranh giới bảo mật duy nhất.
- [ ] Dùng host-only cookie và cookie name riêng khi cần cách ly domain/app.
- [ ] Không chia sẻ cùng HttpSession giữa các ứng dụng độc lập; ưu tiên OIDC/SSO với session riêng.
- [ ] Thiết kế chuyển tenant, session rotation và logout theo phạm vi rõ ràng.
- [ ] Kiểm thử giả tenant header, cookie reuse, IDOR, serializer, backup/restore và nhiều instance.
- [ ] Giám sát tenant mismatch và bảo vệ log/backup khỏi session credential.

Cách ly tenant trong Spring Session là bài toán xuyên suốt từ định danh đến kho dữ liệu và authorization. Session ID chỉ xác định phiên; tenant phải được xác minh từ nguồn đáng tin cậy và gắn với principal. Namespace/repository cần tách theo ứng dụng hoặc tenant theo mức cách ly yêu cầu, cookie phải có phạm vi phù hợp, và mọi truy vấn nghiệp vụ phải ràng buộc tenant ở phía server. Khi các lớp này được thiết kế nhất quán, việc chia sẻ kho session giữa nhiều instance hoặc ứng dụng không làm mất ranh giới dữ liệu giữa các tenant.
