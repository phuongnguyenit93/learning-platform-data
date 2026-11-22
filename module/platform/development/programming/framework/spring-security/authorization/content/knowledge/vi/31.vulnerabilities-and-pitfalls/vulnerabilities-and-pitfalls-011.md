# Quyền cũ còn trong session, token hoặc cache sau khi bị thu hồi

## 1. Vấn đề bảo mật: đã thu hồi nhưng vẫn được phép

Trong hệ thống sử dụng Spring Security, quản trị viên có thể gỡ quyền **EXPORT_REPORT** của người dùng ở database lúc 10:00, nhưng người dùng vẫn xuất được báo cáo lúc 10:05. Đường thực thi có thể không hề lỗi xác thực: session vẫn chứa authority cũ, JWT vẫn hợp lệ về chữ ký và thời hạn, hoặc một cache còn lưu kết quả **allow** từ lần kiểm tra trước.

Đây là lỗi **stale authorization**: quyết định cấp quyền dựa trên một ảnh chụp của chính sách cũ, trong khi chính sách hiện hành đã thay đổi. Bản thân người dùng đã xác thực hợp lệ (**authentication**) không có nghĩa họ còn được phép thực hiện một hành động cụ thể (**authorization**). Nguy cơ xuất hiện đặc biệt ở thao tác tải dữ liệu nhạy cảm, quản trị, chuyển tiền, thay đổi chủ sở hữu, sửa ACL hoặc truy cập tenant khác.

Sau bài học, bạn cần giải thích được quyền cũ nằm ở đâu, khi nào nó bị đọc lại, tại sao logout/đổi role không tự động thu hồi mọi token, cách áp dụng cơ chế kiểm tra trạng thái mới, và cách kiểm thử cả session, token lẫn cache trong điều kiện nhiều thiết bị/nhiều node.

**Ranh giới kiến thức:** tập trung vào lỗi và biện pháp bảo đảm quyền *sau khi bị thu hồi* trong Spring Security authorization. Không triển khai toàn bộ authorization server hay giao thức OAuth/OIDC; chỉ sử dụng các khái niệm token cần thiết để hiểu cửa sổ quyền cũ.

## 2. Phân biệt ba loại trạng thái dễ bị nhầm

| Nơi chứa trạng thái | Ví dụ về dữ liệu cũ | Vì sao tiếp tục cho phép? | Cách buộc kiểm tra mới |
| --- | --- | --- | --- |
| **Session / SecurityContext** | Authentication với ROLE_ADMIN hoặc ROLE_EXPORT tại thời điểm đăng nhập | Request sau có thể khôi phục Authentication cũ từ SecurityContextRepository | Hủy đúng những session liên quan; làm mới Authentication; hoặc kiểm tra quyền hiện tại mỗi lần cần |
| **Access token** | JWT chứa scope/role lúc phát hành và còn hạn | Resource Server xác minh chữ ký, thời gian, issuer… nhưng không mặc nhiên truy vấn quyền vừa đổi trong DB | Token ngắn hạn kết hợp chính sách hiệu lực; kiểm tra version/revocation; hoặc introspection có trạng thái hiện hành |
| **Authorization cache** | Quyết định user X được READ resource Y, hoặc danh sách ACL/roles đã cache | Cache hit bỏ qua việc tra lại dữ liệu đã bị thu hồi | Evict/đổi key theo version; đồng bộ invalidation đa node; tránh dùng dữ liệu stale khi quyết định nhạy cảm |

Cùng một request có thể đi qua *nhiều* lớp: cookie phiên → SecurityContext → quyền từ Authentication → service authorization → cache ACL/quyết định → dữ liệu. Làm mới một lớp không bảo đảm lớp kia đã mới. Ngược lại, hệ thống Resource Server dùng **SessionCreationPolicy.STATELESS** có thể không lưu phiên HTTP nhưng JWT và application cache vẫn có vấn đề quyền cũ.

**Một tình huống cụ thể**

- **09:00**: Mai đăng nhập; session A và JWT T1 được cấp với quyền EXPORT_REPORT. Cache tại node B lưu allow cho report 42.
- **09:30**: quản trị viên thu hồi quyền EXPORT_REPORT; thay đổi đã commit ở nguồn quyền.
- **09:31**: request dùng session A hoặc T1 vẫn gửi danh tính hợp lệ; node B vẫn trả allow nếu chỉ xem snapshot/cache.
- **09:32**: cơ chế kiểm tra quyền hiện hành, revoke token hoặc invalidation cache có thể chặn request — *nếu hệ thống thực sự triển khai và xác minh những cơ chế đó*.

Cần xác định rõ thời điểm cam kết hiệu lực: ví dụ “mọi request authorization **bắt đầu sau khi transaction thu hồi commit** đều phải bị từ chối”. Request đã bắt đầu trước commit là một tình huống đồng thời riêng cần chính sách xử lý; không dùng câu “ngay lập tức” mơ hồ nếu chưa xác định boundary.

## 3. Session: Authentication không tự cập nhật quyền mỗi request

Ở ứng dụng Servlet, Spring Security dùng **SecurityContextHolder** cho context của request. **SecurityContextRepository** có thể lưu/khôi phục SecurityContext giữa các request; một triển khai thường gặp là **HttpSessionSecurityContextRepository**. Authentication bên trong chứa principal và tập **GrantedAuthority** được tạo ở lần xác thực hoặc lần cập nhật gần nhất. Khi role trong database thay đổi, không có quy tắc mặc định rằng mọi Authentication đã lưu trên tất cả session đều được xây dựng lại ngay.

Ví dụ chính sách kiểm tra:

~~~java
@PreAuthorize("hasRole('ADMIN')")
public void approveReport(long reportId) {
    // ...
}
~~~

Đây là **đoạn minh họa không độc lập**. Biểu thức **hasRole('ADMIN')** chủ yếu kiểm tra authority **ROLE_ADMIN** hiện có trong Authentication của lời gọi. Nếu Authentication vẫn mang ROLE_ADMIN cũ, method có thể được cho phép, dù bảng user-role đã gỡ quyền. Chỉ thêm **@EnableMethodSecurity** không biến truy vấn hasRole thành truy vấn database tươi mỗi lần.

Các thao tác cần phân biệt:

1. **SecurityContextHolder.clearContext()** xóa context gắn với luồng thực thi hiện tại; không tự thu hồi JWT, không bảo đảm xóa tất cả HttpSession của người dùng trên các thiết bị.
2. **Đăng xuất (logout)** trong luồng chuẩn có thể hủy session hiện tại và xóa Authentication. Điều đó không có nghĩa các session khác của cùng người dùng đã bị hủy hoặc bearer token riêng đã vô hiệu.
3. **Invalidating HttpSession** phía server ngăn sử dụng tiếp session đó khi cơ chế session thật sự được dùng. Xóa cookie ở browser mà không vô hiệu session server không có cùng mức bảo đảm.
4. **Thay đổi quyền trong UserDetailsService** hoặc DB không tự làm mới mọi Authentication đang tồn tại. Cache UserDetails khi xác thực lại cũng có thể còn dữ liệu cũ nếu không invalidation.
5. **Remember-me, refresh-token hoặc SSO session** có thể tạo Authentication mới sau khi session bị hủy. Nếu nguồn quyền hoặc cơ chế đăng nhập lại vẫn giữ grant cũ, người dùng có thể được cấp quyền trở lại.

Trong Spring Security 6+, cơ chế persistence đã thay đổi so với phiên bản 5: khi tự thiết lập SecurityContext trong custom authentication flow, việc lưu vào **SecurityContextRepository** có thể cần thao tác **saveContext(...)** rõ ràng. Điều này liên quan đến lưu phiên, *không phải* một cơ chế tự động thu hồi quyền. Hãy đọc tài liệu theo phiên bản đang chạy.

**Cách xử lý theo yêu cầu sản phẩm:** nếu cần khóa một tài khoản ở tất cả thiết bị, quản lý tập session theo principal trong phạm vi các node có thể kiểm soát, invalidation đúng session, đồng thời vô hiệu khả năng cấp credential mới nếu cần. **SessionRegistry** không tự bảo đảm có đủ session phân tán khi không cấu hình session tracking phù hợp; với Spring Session có thể dùng repository và chỉ mục principal nếu được hỗ trợ/cấu hình. Kiểm thử bằng hai browser/thiết bị và hai application node, không suy từ một thao tác logout cục bộ.

## 4. Token: chữ ký hợp lệ không chứng minh quyền còn hiệu lực

### 4.1. JWT access token là ảnh chụp quyền tại lúc phát hành

JWT tự chứa claim như **sub**, **scope/scp**, **roles**, **iat**, **nbf**, **exp**, **iss**, **aud**. Với cấu hình JWT Resource Server, **JwtDecoder** xác minh chữ ký và các điều kiện hợp lệ đã cấu hình; phạm vi scope thường được ánh xạ thành authority dạng **SCOPE_x**. Nếu một claim ghi role cũ, một chữ ký vẫn đúng và **exp** còn trong tương lai thì **JWT mặc nhiên không biết role tại DB đã bị sửa**.

Ví dụ: access token có **SCOPE_reports.export**, expires 10:15, nhưng quyền export bị thu hồi lúc 10:00. Tại 10:01, nếu resource server chỉ kiểm tra token còn hợp lệ rồi dùng authority **SCOPE_reports.export**, nó vẫn có thể cho xuất báo cáo. Chữ ký và timestamp không sai; lỗi nằm ở giả định rằng scope ghi trong token phải phản ánh mọi biến động quyền thời gian thực.

JWT ngắn hạn **giảm độ dài tối đa của cửa sổ stale** khi mọi validation khác đã đúng, nhưng không chứng minh thu hồi tức thì. Cấu hình clock skew có thể làm thời điểm chấp nhận exp/nbf lệch một khoảng so với đồng hồ; nên xác định thời hạn thực tế trong test. Khi dùng JWT, vẫn cần xác minh issuer, audience phù hợp, thuật toán ký, key và tất cả validation liên quan; kiểm tra revocation là bước bổ sung chứ không thay thế bảo vệ token cơ bản.

### 4.2. Refresh token và access token có vòng đời khác nhau

Thu hồi **refresh token** ngăn sử dụng refresh token đó để xin access token mới (theo chính sách authorization server), nhưng **access token đã phát hành trước đó có thể còn dùng được** đến hết hạn hoặc đến khi có cơ chế phát hiện thu hồi tại resource server. RFC 7009 quy định server phải hỗ trợ thu hồi refresh token và khuyến nghị hỗ trợ thu hồi access token; chi tiết ảnh hưởng tới token liên quan phụ thuộc triển khai và chính sách server.

Không nên viết test “revoke refresh token → old JWT access token phải 401 ngay” nếu hệ thống không có cơ chế thu hồi access token thực sự. Ngược lại, nếu sản phẩm yêu cầu logout mọi thiết bị/khóa tài khoản ngay thì phải thiết kế đường kiểm tra ở resource server.

### 4.3. Opaque token và introspection

Với opaque bearer token, Spring Security Resource Server có thể gọi **OpaqueTokenIntrospector** tại authorization server để xác nhận token đang **active=true**. Đây là hướng phù hợp khi cần server giữ trạng thái token và có thể thu hồi. Tuy nhiên, không bảo đảm tức thì nếu authorization server trả trạng thái lỗi thời, resource server cache kết quả introspection quá lâu hoặc network bị partition.

Một hệ thống có thể cấu hình introspection cho cả JWT nếu muốn kiểm tra trạng thái server-side, nhưng **JWT Resource Server mode mặc định không tự introspect mỗi request**. Phải chọn và cấu hình rõ chính sách, chi phí round-trip, SLA và cách xử lý khi introspection endpoint không truy cập được.

## 5. Cache: stale allow có thể sống lâu hơn session và token

Những cache thường tác động tới authorization:

- **UserDetails/authorities cache:** principal được nạp từ DB rồi được dùng lại ở các lần xác thực; đổi role nhưng không evict/reload có thể tiếp tục phát Authentication mang quyền cũ.
- **ACL cache:** ACL của một ObjectIdentity, danh sách ACE, parent ACL hoặc policy được lưu; cập nhật ACL con/cha mà không invalidation đủ có thể giữ quyền kế thừa đã thu hồi.
- **Authorization decision cache:** lưu kết quả true/false của canRead/canExport/hasPermission; giá trị **true** dễ gây lỗ hổng nếu key hoặc lifetime không gắn với phiên bản chính sách.
- **Cache ở API gateway/edge/ứng dụng con:** các lớp ngoài Spring Security có thể lưu phản hồi, entitlements hoặc kết quả policy. Invalidate tại Spring service không tự invalidate mọi cache bên ngoài.
- **Cache phân tán và local cache trên từng pod:** xóa Redis key không tự xóa một bản sao Caffeine còn nằm trong process; thông điệp invalidation có thể đến chậm hoặc thất lạc.

**Lỗi thiết kế key:** cache “userId:action” mà không chứa **tenantId/resourceId** có thể cấp nhầm quyền giữa các tài liệu. Key chỉ theo resourceId thiếu userId cũng nguy hiểm. Key có đủ user, tenant, resource, action nhưng không phản ánh **policy revision** vẫn có thể stale sau revoke.

Một key khái niệm:

~~~text
tenantId / principalId / resourceType / resourceId / action / policyRevision
~~~

Đưa revision vào key chỉ hữu ích nếu **mỗi request lấy được revision hiện hành từ nguồn đủ mới**. Nếu revision cũng bị giữ trong cache local cũ, hệ thống vẫn truy cập key cũ và lỗ hổng vẫn tồn tại. Tương tự, cập nhật DB rồi mới publish invalidate có một khoảng giữa commit và sự kiện; cần định nghĩa mức nhất quán và cơ chế đóng cửa sổ theo yêu cầu.

Cache kết quả **deny** cũng cần chính sách rõ: sau khi cấp lại quyền, deny cũ có thể chặn hợp lệ đến khi hết TTL. Đây là lỗi tính đúng đắn/khả dụng, dù khác mức nghiêm trọng với stale allow.

### 5.1. Race condition khi invalidate

Một luồng đọc quyền cũ đúng trước thời điểm revoke; luồng khác commit revoke, xóa cache; luồng đọc đầu tiên sau đó ghi **allow** cũ trở lại cache. Đây là lý do “đã gọi evict” vẫn có thể chưa đủ.

Biện pháp: sử dụng **policy revision**/etag từ dữ liệu có thẩm quyền, kiểm tra revision trước khi chấp nhận ghi cache, gắn cache entry với revision và loại bỏ entry không trùng revision khi đọc. Với kiến trúc event-driven, sử dụng sự kiện sau commit, outbox/queue có retry và thứ tự version để tránh event cũ ghi đè trạng thái mới. Cơ chế nào cũng phải được đo và test trong điều kiện nhiều node.

## 6. Chiến lược thu hồi: chọn theo cửa sổ nhất quán

Không có một cách “thu hồi token và cache” duy nhất phù hợp mọi ứng dụng. Hãy định nghĩa yêu cầu:

| Mục tiêu | Cơ chế khả thi | Giới hạn cần nhận thức |
| --- | --- | --- |
| Từ chối quyền ngay ở **request mới sau commit** | Truy vấn chính sách hiện hành; session invalidation; token revocation check/introspection; policy-version guard | Cần nguồn trạng thái nhất quán và đường kiểm tra sống trên mọi node |
| Chấp nhận cửa sổ rất ngắn, có số đo | Access token TTL ngắn; cache TTL giới hạn; event invalidation | TTL là giới hạn trễ tương đối, không phải thu hồi tức thì; cần tính clock skew/lỗi sự kiện |
| Chặn đăng nhập/refresh trở lại | Disable account; revoke refresh token; revoke remember-me/SSO session theo cơ chế tương ứng | Các access token/session có sẵn có thể còn hiệu lực nếu không xử lý riêng |
| Quyền đổi theo từng tài liệu | Recheck ACL/policy hiện hành tại điểm đọc/sửa; invalidate ACL parent/children | Token version chỉ theo user có thể bỏ sót thay đổi ở ACL/resource nếu không tăng version tương ứng |
| Hệ thống nhiều instance | Shared authoritative store hoặc introspection; truyền event có xác nhận, revision check | Evict tại node A chưa bảo đảm node B đã thấy ngay |
| Thao tác nhạy cảm kéo dài | Kiểm tra quyền khi bắt đầu và tại điểm commit/phát hành dữ liệu | Quyền có thể đổi giữa check và use (TOCTOU) |

**Hai thiết kế thường dùng:**

**A. Quyền hiện hành ở tầng service.** Bearer token/session xác định ai đang gọi; **@PreAuthorize** hoặc AuthorizationManager tra chính sách mới theo subject, tenant và tài nguyên. Với hành động nhạy cảm, kiểm tra trong transaction phù hợp và/hoặc ngay trước khi xuất dữ liệu. Cần tránh gọi lại một decision cache chưa có chiến lược invalidation.

**B. Version hóa credential/authorization.** Mỗi user có **authzVersion** tăng cùng transaction thay đổi quyền. Session/token chứa version tại lúc phát hành. Request so với version hiện hành; nếu khác, từ chối credential cũ hoặc tái tải quyền theo chính sách. Khi thu hồi quyền theo **resource**, tenant, nhóm hay ACL parent, version gắn user đơn lẻ sẽ không đủ nếu không tăng đúng các version bị ảnh hưởng. Có thể dùng kết hợp userVersion, membershipVersion, resourcePolicyVersion.

Bảo đảm quan trọng là **đọc version mới từ nơi có độ nhất quán đáp ứng SLA**. Đọc replica chậm, cache revision lâu hoặc xử lý event bất đồng bộ trước khi ra quyết định có thể làm quy trình version hóa vô tác dụng. Nếu lookup trạng thái thất bại ở một thao tác rủi ro cao, không được coi “không tra được = có quyền”.

## 7. Ví dụ Java 17+ chạy độc lập: thấy lỗi snapshot và version guard

Chương trình dưới đây **mô phỏng** ba nguồn stale: quyền giữ trong session, token tự chứa claim, và authorization cache. Phần **freshGuard** truy vấn chính sách hiện hành với revision. Mục đích là minh họa logic: chương trình không ký JWT, không dùng Spring Security và không thay thế kiểm thử bảo mật thật.

Tạo file **StalePermissionDemo.java**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class StalePermissionDemo {
    record Policy(long version, boolean canExport) {}
    record Credential(String user, long version, boolean exportClaim) {}

    private static final Map<String, Policy> currentPolicies =
            new ConcurrentHashMap<>();

    private static Credential issue(String username) {
        Policy p = currentPolicies.get(username);
        if (p == null) {
            throw new IllegalStateException("No policy for " + username);
        }
        return new Credential(username, p.version(), p.canExport());
    }

    // Minh hoa cach dung lai role/claim duoc chup luc dang nhap.
    private static boolean snapshotAllow(Credential c) {
        return c.exportClaim();
    }

    // Chi an toan neu currentPolicies la nguon quyen du moi.
    private static boolean freshGuard(Credential c) {
        Policy now = currentPolicies.get(c.user());
        return now != null
                && now.version() == c.version()
                && now.canExport()
                && c.exportClaim();
    }

    public static void main(String[] args) {
        currentPolicies.put("mai", new Policy(1, true));
        Credential session = issue("mai");
        Credential token = issue("mai");

        Map<String, Boolean> decisionCache = new HashMap<>();
        String key = "mai:report-42:EXPORT";
        decisionCache.put(key, snapshotAllow(token));

        System.out.printf(
                "before session=%s token=%s cache=%s guard=%s%n",
                snapshotAllow(session), snapshotAllow(token),
                decisionCache.get(key), freshGuard(token));

        // Gia lap thu hoi: thay doi quyen va version cung mot lan.
        currentPolicies.put("mai", new Policy(2, false));
        System.out.printf(
                "after session=%s token=%s cache=%s guard=%s%n",
                snapshotAllow(session), snapshotAllow(token),
                decisionCache.get(key), freshGuard(token));

        // Cap lai quyen: credential cu van lech version.
        currentPolicies.put("mai", new Policy(3, true));
        Credential newToken = issue("mai");
        System.out.printf(
                "regrant old=%s new=%s%n",
                freshGuard(token), freshGuard(newToken));
    }
}
~~~

Chạy tại thư mục chứa file, với JDK 17 trở lên:

~~~bash
javac StalePermissionDemo.java
java StalePermissionDemo
~~~

Kết quả chuẩn:

~~~text
before session=true token=true cache=true guard=true
after session=true token=true cache=true guard=false
regrant old=false new=true
~~~

Bài học từ output: session/token/cache lưu **allow** cũ không tự biến mất khi policy đổi; kiểm tra current version và policy mới phát hiện thu hồi. Sau khi cấp quyền lại, token cũ vẫn bị chặn do version mismatch; cần một token/Authentication mới nếu áp dụng chiến lược từ chối credential cũ.

**Giới hạn mô phỏng:** ConcurrentHashMap thay cho database và transaction, không có race giữa hai node, token ở đây là record chứ không phải JWT thật, và không có xác thực chữ ký. Trong ứng dụng thật, cập nhật **policy + version** phải atomic; kiểm tra version cần đọc trạng thái đáng tin; đối chiếu session/token phải diễn ra tại đường cấp quyền thực.

## 8. Áp dụng vào Spring Security authorization

Với quyền theo tài nguyên, cách rõ ràng là để **Authentication nhận diện người dùng** rồi kiểm tra policy hiện hành tại tầng nghiệp vụ. Bật method security bằng **@EnableMethodSecurity**; ví dụ sau là **mã minh họa cần dự án Spring và repository thật**, không phải chương trình Java độc lập:

~~~java
@Configuration
@EnableMethodSecurity
class SecurityMethodsConfiguration {
}

@Service
class ReportService {
    @PreAuthorize("@freshReportPolicy.canExport(authentication, #reportId)")
    public byte[] exportReport(long reportId) {
        return reportRepository.generateExport(reportId);
    }
}
~~~

Bean **freshReportPolicy** phải thực sự truy vấn những điều kiện cấp quyền ở thời điểm request: user còn active, vai trò/nhóm mới, tenant/resource đúng, quyền EXPORT hiện hành, trạng thái báo cáo, các chính sách chặn khác. Không được viết implementation chỉ kiểm tra **authentication.getAuthorities()** rồi gọi đó là “fresh”. Với biểu thức tham chiếu **#reportId**, cần đảm bảo Spring có thể phát hiện tên tham số (ví dụ compile với **-parameters**). Method security kiểm tra lời gọi qua Spring AOP proxy; self-invocation bên trong cùng instance có thể bỏ qua advice nếu không có thiết kế xử lý.

Nếu endpoint cần thêm OAuth scope, có thể dùng phép AND:

~~~java
@PreAuthorize(
    "hasAuthority('SCOPE_reports.export')"
    + " and @freshReportPolicy.canExport(authentication, #reportId)"
)
public byte[] exportReport(long reportId) {
    return reportRepository.generateExport(reportId);
}
~~~

Scope trong token **không thay thế** kiểm tra quyền đang còn; vế policy hiện hành mới ngăn stale allow. Nếu quyền vừa *được cấp thêm* sau phát hành token, scope cũ có thể khiến truy cập tiếp tục bị deny đến khi cấp token mới — thường là hành vi bảo thủ có chủ ý.

Trong môi trường triển khai thật, cần lựa chọn API cho phản hồi khi thu hồi: credential hết hiệu lực/bị chặn có thể dẫn đến **401**, còn danh tính hợp lệ nhưng không được phép vào tài nguyên thường là **403**. Với tài nguyên cần giấu sự tồn tại, ứng dụng có thể chủ động trả **404**. Chốt hợp đồng API và dùng test đúng đường đi; không dựa vào một mã duy nhất cho mọi loại từ chối.

### Tại sao không chỉ “reload quyền từ DB” vô điều kiện?

Lấy authorities hiện hành tại mỗi request có thể phù hợp cho yêu cầu mạnh, nhưng tăng chi phí truy vấn và không tự giải quyết quyết định dựa trên resource ACL, cache downstream hoặc request đang chạy. Thiết kế tốt thường chọn **bộ dữ liệu quyền tối thiểu cần kiểm tra theo hành động**, một cơ chế version/invalidation đã kiểm chứng, và nguồn trạng thái có tính nhất quán rõ ràng. Các quyết định nhạy cảm có thể phải đọc bản chính thay vì replica trễ.

## 9. Kịch bản kiểm thử hồi quy bắt buộc

Các ca sau kiểm chứng **đường truy cập thực**, không chỉ một hàm kiểm tra bằng dữ liệu giả. Mỗi ca cần có trạng thái **trước thu hồi: allow** để chứng minh setup hợp lệ, sau đó commit thu hồi, và xác minh **sau thu hồi: deny** bằng đúng credential/cache cũ.

| Mã | Trạng thái đã warm trước revoke | Hành động | Kỳ vọng sau revoke |
| --- | --- | --- | --- |
| S1 | Browser A giữ session có ROLE_EXPORT | Xóa role và commit | Browser A không còn xuất báo cáo |
| S2 | Hai browser/thiết bị A và B giữ hai session | Khóa user hoặc revoke all sessions theo yêu cầu | Cả A và B bị chặn; session B không lọt |
| S3 | Session A đã logout nhưng remember-me còn hoạt động | Thử đăng nhập tự động trở lại | Không khôi phục quyền bị thu hồi |
| J1 | JWT T1 còn exp, chứa SCOPE_reports.export | Revoke role trong DB | T1 bị chặn theo cơ chế freshness/revocation đã cam kết |
| J2 | T1 còn hạn; refresh token bị thu hồi | Dùng T1 rồi thử refresh | T1 theo policy access đã cấu hình; refresh không còn cấp token mới |
| J3 | JWT cũ ở node B; JWT mới ở node A | Thay policy và phát token mới | Cũ bị chặn, mới chỉ có quyền hiện hành |
| O1 | Opaque token introspection active=true | Revoke token tại authorization server | Lần kiểm tra mới trả inactive/deny theo SLA |
| C1 | Cache decision tại một node giữ allow | Thu hồi + invalidate | Request tiếp theo không nhận allow lỗi thời |
| C2 | Node A và B đều có bản cache allow | Thu hồi tại A, gọi B | B không giữ quyền vượt cửa sổ cam kết |
| C3 | Cache ACL con kế thừa quyền từ cha | Thu hồi ACE ở cha | Child không còn kế thừa grant bị thu hồi |
| C4 | Quyền được thu hồi rồi cấp lại | Chạy hai chiều policy change | Old allow không lọt; old deny không chặn vĩnh viễn |
| R1 | User X có quyền trên tài liệu 42 | Revoke X trên 42 | Không ảnh hưởng user Y hoặc tài liệu 43 ngoài dự kiến |
| T1 | Hai request đồng thời với thao tác revoke | Ghi nhận order/commit boundary | Kết quả phù hợp consistency contract, không có stale allow sau mốc đã cam kết |
| F1 | Introspection/permission-store/invalidation gặp lỗi | Gọi operation nhạy cảm | Không tự động fail-open khi nguồn quyền không xác minh được |

**Quy trình mẫu cho integration test nhiều node:**

1. Tạo user và grant thật ở nguồn policy; cấp session/token trước khi thay đổi; xác minh request qua service/API được allow.
2. Làm warm cache ở **tất cả node tham gia bài test**, ghi nhận version và trạng thái cache/hit; nếu kiểm tra ACL, tạo cả parent và child.
3. Qua đường quản trị thực, thu hồi quyền và commit; ghi thời điểm commit, revision mới và event invalidation nếu có.
4. Gửi lại **đúng session ID/cookie hoặc token cũ** tới từng node, với cùng resource/action; kiểm tra response bị chặn và không có dữ liệu nhạy cảm trong body/stream.
5. Kiểm tra người dùng khác và resource khác vẫn có đúng quyền; re-grant quyền rồi xác minh token/session mới hoặc policy mới hoạt động.
6. Gây lỗi event/network và đồng thời request/revoke để phát hiện stale insertion; nếu SLA cho phép eventual consistency, đo cửa sổ thực tế và so với ngưỡng đã định.

**Bẫy kiểm thử với Spring Security:** dùng riêng **@WithMockUser(roles="ADMIN")** chỉ dựng Authentication giả tại test, không chứng minh session thực đã được thay mới sau thay đổi DB. Với servlet session cần test giữ lại **MockHttpSession** hoặc cookie của request đăng nhập thật; với bearer JWT phải cấp token hợp lệ theo cấu hình Resource Server và thử lại chính token cũ. JUnit/MockMvc hữu ích cho regression test nhưng unit test chỉ mock Authentication không chứng minh token validation, revocation hay cache đa node.

Đối với REST API, kiểm tra response **401/403/404** theo hợp đồng cùng với việc **không có dữ liệu trả về**. Một response 200 bị cắt dữ liệu sai hoặc một export đã ghi file trước khi policy chặn vẫn là lỗi. Với WebSocket/SSE, job bất đồng bộ và tải xuống dài, authorization ở lúc handshake/bắt đầu chưa đủ nếu sản phẩm yêu cầu thu hồi khi luồng đang mở; quyết định nơi cần recheck và policy hủy công việc đang chạy.

## 10. Checklist phòng tránh khi triển khai

**Nguồn quyền và giao dịch**

- [ ] Xác định rõ quyền đang nằm trong user-role, group membership, ACL, tenant, policy engine hay nhiều nguồn.
- [ ] Thao tác revoke cập nhật đúng mọi nguồn grant; không chỉ xóa một role khi còn quyền kế thừa hoặc grant khác.
- [ ] Ghi policy version/permission mutation trong transaction có ranh giới rõ; event invalidation sau commit và có cơ chế retry.
- [ ] Tránh đọc quyền từ replica hoặc cache có độ trễ vượt SLA bảo mật của thao tác.

**Credential và session**

- [ ] Kiểm tra mọi session/thiết bị cần revoke, remember-me và refresh token; phân biệt logout phiên hiện tại với logout toàn bộ.
- [ ] JWT validator kiểm tra chữ ký, issuer, audience, exp/nbf theo cấu hình; cơ chế revocation/freshness được thiết kế độc lập.
- [ ] Với quyền phải thu hồi ngay, không chỉ trông chờ JWT hết hạn hoặc refresh token bị thu hồi.
- [ ] Nếu dùng denylist theo **jti**, kiểm tra issuer, phạm vi token, thời hạn lưu entry đến hết cửa sổ hợp lệ và tính nhất quán giữa node; không log nguyên token.

**Cache và enforcement**

- [ ] Key cache bao gồm đúng identity, tenant, resource, action và revision/policy dependency khi cần.
- [ ] Cơ chế invalidation bao phủ cache parent/child, cache local và distributed; có kiểm thử nhiều instance.
- [ ] Không tự cho phép khi permission store/introspection xảy ra lỗi hoặc khi revision không xác minh được.
- [ ] Quyền được kiểm tra tại service thực thi, không chỉ ở frontend/menu; các endpoint list, search, export, batch và background job đều được rà soát.
- [ ] Không chỉ tin authority đã giữ trong Authentication nếu bài toán đòi quyền động; phân biệt authority tĩnh với phép tra ACL/policy sống.

**Quan sát và audit**

- [ ] Ghi actor thu hồi, subject, tenant/resource, quyền, thời điểm commit, revision và kết quả access sau thu hồi.
- [ ] Đo cache hit/miss, invalidation delay, số request được allow sau mốc revoke và trạng thái khác biệt giữa node.
- [ ] Giữ bí mật session ID, bearer token, refresh token; không ghi những credential này vào log.
- [ ] Có cảnh báo khi post-revoke authorization tiếp tục allow hoặc khi permission-check phải chạy ở chế độ degradation.

## 11. Sai lầm phổ biến cần nhận diện

1. **“Tôi đã xóa role trong DB nên session tự hết quyền.”** Sai nếu Authentication chứa authority snapshot chưa được làm mới.
2. **“Đã gọi logout nên mọi thiết bị và mọi API token đều bị thu hồi.”** Chỉ đúng nếu chính sách đã triển khai đầy đủ invalidation cho các credential/sessions đó.
3. **“JWT hợp lệ về chữ ký nghĩa là role trong token còn đúng.”** Chữ ký chứng minh integrity/issuer theo cấu hình, không phản ánh thay đổi role sau khi phát hành.
4. **“Thu hồi refresh token làm old access token lập tức không dùng được.”** Phải kiểm tra policy và cách resource server phát hiện thu hồi access token.
5. **“Cache có TTL 10 phút là đã hỗ trợ revoke ngay.”** TTL chỉ giới hạn một phần thời gian stale; không bảo đảm sau commit sẽ deny ở request kế tiếp.
6. **“Đã @CacheEvict ở node A nên node B chắc chắn đã biết.”** Phụ thuộc cache topology, pub/sub, version và cơ chế delivery.
7. **“Dùng policyVersion trong key là tự đủ.”** Nếu version vẫn đến từ cache stale hoặc replica trễ, phép kiểm tra vẫn sai.
8. **“Chỉ chặn endpoint quản trị trong web là đủ.”** URL khác, method tự gọi, job nền hoặc kênh export có thể đi vòng điểm kiểm soát.
9. **“Không tra được authorization server thì tạm cho qua.”** Với thao tác nhạy cảm, điều này là fail-open; cần quy tắc xử lý lỗi rõ và bảo thủ.
10. **“Test bằng @WithMockUser pass nên revoke hoàn chỉnh.”** Test giả không thể chứng minh hiệu lực của session tồn tại, JWT cũ, DB commit hoặc cache đa node.

## 12. Bài tập vận dụng

**Bài tập A — Session cũ:** viết integration test đăng nhập bằng session A, gỡ ROLE_EDITOR rồi gọi lại endpoint sửa tài liệu bằng **chính session A**. Triển khai một trong hai cách có căn cứ: invalidation các session liên quan, hoặc quyết định service luôn tra entitlement mới. Nêu rõ boundary sau commit.

**Bài tập B — JWT và refresh token:** phát JWT có claim export; thu hồi quyền, thử JWT cũ trước exp, refresh token trước/sau thu hồi, JWT mới sau khi cập nhật. Xây bảng kết quả 401/403 theo chính sách thực tế của resource server. Bảo đảm một JWT cũ không tiếp tục allow nếu bài toán yêu cầu thu hồi quyền ngay.

**Bài tập C — Cache và race:** warm cache allow tại A/B, revoke quyền, gây race read-old/evict/write-back-old và chứng minh revision guard hoặc invalidation loại bỏ stale allow. Bổ sung trường hợp ACL cha bị revoke nhưng ACL con đã cache trước đó.

**Tiêu chí hoàn thành:** giải thích được *tại sao* session/token/cache còn mang quyền cũ; chỉ ra chính xác nguồn quyền mới và thời điểm quyết định có hiệu lực; đo được cửa sổ revoke; xác minh request bằng credential **đã phát trước revoke** bị chặn theo SLA; không làm hỏng quyền của người dùng/tài nguyên khác; và không bỏ qua lỗi cache/multiple nodes.

## Tài liệu tham khảo chính thức

- [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
