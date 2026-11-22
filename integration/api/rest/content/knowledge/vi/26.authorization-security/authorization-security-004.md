# Ngăn truy cập chức năng quản trị qua endpoint thiếu kiểm soát

Một API có thể xác thực người gọi đúng cách mà vẫn để người dùng thông thường thực hiện thao tác chỉ dành cho quản trị viên. Nguyên nhân phổ biến là một endpoint mới, endpoint cũ hoặc đường dẫn thay thế được thêm vào mà thiếu bước **phân quyền theo chức năng**. Đây là dạng *Broken Function Level Authorization* (BFLA): hệ thống biết ai đang gửi yêu cầu, nhưng không kiểm tra người đó có quyền thực hiện hành động được yêu cầu hay không.

Trong mô-đun **INTEGRATION_API_REST**, ta thiết kế API quanh resource, URI, phương thức HTTP và hợp đồng dữ liệu. Với những thao tác có đặc quyền như khóa tài khoản, duyệt hoàn tiền, tái tạo báo cáo, thay đổi cấu hình hoặc xuất dữ liệu nhạy cảm, hợp đồng API phải bao gồm cả **ai được phép gọi**. Đặt đường dẫn dưới `/admin`, ẩn nút trên giao diện hoặc yêu cầu người gọi đăng nhập đều chưa phải là một chính sách phân quyền đầy đủ.

## 1. Kết quả học tập

Sau bài này, người học có thể:

1. Nhận diện BFLA và phân biệt nó với lỗi truy cập trái phép vào đối tượng dữ liệu (BOLA/IDOR).
2. Lập bảng quyền cho các chức năng quản trị, bao gồm cả endpoint ít được chú ý như import, export, retry, bulk action và API nội bộ.
3. Kết hợp kiểm soát ở HTTP filter với kiểm soát tại service bằng Spring Security, đồng thời giới hạn dữ liệu theo tenant khi cần.
4. Thiết kế phản hồi HTTP, log và bài kiểm thử chứng minh một yêu cầu bị từ chối **trước khi** tạo ra tác dụng phụ.

## 2. Lỗ hổng phát sinh như thế nào?

Giả sử một hệ thống có hai endpoint tái tạo báo cáo:

~~~http
POST /api/v1/admin/reports/6c84.../rebuild HTTP/1.1
Authorization: Bearer <admin-token>

POST /api/v1/reports/6c84.../rebuild HTTP/1.1
Authorization: Bearer <ordinary-user-token>
~~~

Endpoint thứ nhất được cấu hình chỉ cho nhóm vận hành. Endpoint thứ hai ra đời khi ứng dụng di động cần gọi tác vụ tương tự; lập trình viên thêm `@PostMapping` nhưng chỉ dựa vào quy tắc “mọi URL còn lại phải đăng nhập”. Người dùng thường có thể gọi endpoint thứ hai và kích hoạt cùng thao tác đặc quyền. Trường hợp này là BFLA dù hệ thống xác thực token thành công.

Một biến thể khác là chức năng vốn nằm trên URL có vẻ vô hại:

~~~http
POST /api/v1/reports/6c84.../rebuild
POST /api/v1/jobs/72f1.../retry
DELETE /api/v1/users/104
POST /api/v1/refunds/293/approve
GET /api/v1/users/export
~~~

Từ khóa “admin” không xuất hiện trong URL, nhưng chức năng lại có quyền cao. Vì vậy, **quyền gắn với hành động nghiệp vụ**, không chỉ với cấu trúc đường dẫn.

| Tình huống | Câu hỏi phải kiểm tra | Loại rủi ro |
| --- | --- | --- |
| Người dùng thường gọi API khóa tài khoản | Người gọi có quyền `users.suspend` không? | BFLA (vượt quyền theo chức năng) |
| Nhân viên vận hành đọc báo cáo của tenant khác | Người gọi có quyền với **đúng đối tượng/tenant** này không? | BOLA, có thể cùng tồn tại với BFLA |
| Đã đăng nhập nhưng gọi API duyệt hoàn tiền | Quyền đọc hoàn tiền có bao gồm quyền duyệt không? | BFLA |
| API `/internal/jobs/retry` công khai do cấu hình gateway | Ai được phép gọi chức năng nội bộ, bất kể nguồn mạng? | BFLA và sai cấu hình hạ tầng |
| UI ẩn nút “Xóa toàn bộ”, request thủ công vẫn thực hiện được | Backend đã kiểm tra quyền độc lập với UI chưa? | BFLA |

**Xác thực** trả lời “người gọi là ai?”. **Phân quyền theo chức năng** trả lời “người đó có được phép thực hiện thao tác này?”. **Phân quyền theo đối tượng** trả lời tiếp “người đó có được phép thao tác trên bản ghi/tenant này?”. Một API quản trị an toàn thường cần cả ba câu hỏi.

## 3. Xây chính sách trước khi viết controller

Hãy liệt kê các endpoint theo **hành động** và định nghĩa quyền tối thiểu cho từng hành động. Ví dụ:

| Endpoint và phương thức | Ý nghĩa | Quyền bắt buộc | Ràng buộc bổ sung |
| --- | --- | --- | --- |
| `GET /api/v1/reports/{id}` | Đọc báo cáo | `reports.read` | Chỉ trong tenant được cấp |
| `POST /api/v1/reports/{id}/rebuild` | Tạo yêu cầu tái tạo báo cáo | `reports.rebuild` | Chỉ báo cáo thuộc tenant hợp lệ |
| `POST /api/v1/refunds/{id}/approve` | Duyệt hoàn tiền | `refunds.approve` | Giới hạn khoản tiền, tách người tạo và người duyệt nếu yêu cầu |
| `GET /api/v1/users/export` | Xuất dữ liệu người dùng | `users.export` | Phạm vi dữ liệu và mục đích sử dụng |
| `POST /api/v1/jobs/{id}/retry` | Chạy lại job nội bộ | `ops.jobs.retry` | Đúng môi trường, đúng loại job |
| `GET /actuator/health` | Kiểm tra liveness/health | Theo chính sách health công khai | Không rò thông tin nhạy cảm |

Trong bảng, tên quyền là một **hợp đồng do hệ thống định nghĩa**. Nếu API dùng OAuth 2.0 access token với scope, chúng có thể được biểu diễn bằng authority `SCOPE_reports.rebuild` trong Spring Security. Tổ chức khác có thể dùng RBAC hoặc ABAC với tập quyền khác, nhưng quy tắc cốt lõi không đổi: quyền đọc, sửa, phê duyệt và quản trị phải được tách riêng khi mức rủi ro khác nhau.

Một số nguyên tắc thiết kế đáng áp dụng:

- **Mặc định từ chối (deny by default):** route chưa có chính sách rõ ràng thì không tự động được phép truy cập.
- **Quyền tối thiểu:** nhân viên được xem báo cáo không mặc nhiên có quyền tái tạo hoặc xuất báo cáo.
- **Chính sách tập trung:** cùng một hành động nghiệp vụ có một điểm thực thi kiểm tra quyền, kể cả khi được gọi từ nhiều controller, phiên bản API hoặc cơ chế nội bộ.
- **Phạm vi dữ liệu độc lập:** quyền `reports.rebuild` không cho phép tự động sửa báo cáo của mọi tenant.
- **Đường đặc quyền được kiểm kê:** endpoint cũ, bulk action, import/export, callback, retry, admin console, actuator và công cụ vận hành phải nằm trong danh sách rà soát.

Không nên dùng một nhãn `ADMIN` tổng quát cho mọi tác vụ khi đội hỗ trợ, đội tài chính và đội vận hành có quyền khác nhau. Nếu dùng role, hãy ánh xạ role sang permission và kiểm tra permission tại hành động. Chức danh trong tổ chức cũng không nhất thiết tương đương quyền trong một tenant.

## 4. Luồng thực thi cần chặn ở đâu?

Một request quản trị thông thường đi qua các bước:

~~~mermaid
flowchart TD
    A["HTTP request: POST /reports/{id}/rebuild"] --> B["Xác thực token, issuer, audience, thời hạn"]
    B --> C{"Route có quyền tương ứng?"}
    C -- "Không" --> X["401 hoặc 403; không gọi nghiệp vụ"]
    C -- "Có" --> D["Controller gọi application service"]
    D --> E{"Service kiểm tra quyền chức năng?"}
    E -- "Không" --> X
    E -- "Có" --> F{"Bản ghi thuộc phạm vi tenant/đối tượng?"}
    F -- "Không" --> Y["403 hoặc 404 theo chính sách"]
    F -- "Có" --> G["Tạo job / thay đổi trạng thái"]
    G --> H["202 Accepted và audit log"]
~~~

Kiểm tra ở lớp HTTP giúp chặn sớm và giúp người vận hành nhìn thấy hợp đồng quyền của API. Kiểm tra ở service bảo vệ cùng chức năng khi có controller khác, endpoint legacy, phiên bản `v2` hoặc một caller nội bộ sử dụng lại service. Nếu quyền đối tượng phụ thuộc dữ liệu trong cơ sở dữ liệu, hãy kiểm tra trước thao tác ghi; truy vấn theo `id + tenantId` còn hạn chế rò rỉ bản ghi xuyên tenant.

Không dựa vào các điều kiện yếu như “đường dẫn có `/admin`”, “request đi từ VPN”, “header `X-Internal: true`”, “tham số `isAdmin=true`”, “người dùng không thấy nút” hoặc “đã đăng nhập”. Header và tham số do client gửi không phải bằng chứng cấp quyền. Chỉ những thuộc tính đã được xác thực và kiểm chứng từ cơ chế tin cậy mới được dùng làm căn cứ.

## 5. Áp dụng với Java và Spring Security

Ví dụ dưới đây dùng Spring Boot 3, Spring Security 6, REST API stateless nhận Bearer JWT do authorization server đáng tin cậy phát hành. Access token phải được kiểm tra chữ ký, issuer, thời hạn và **audience dành cho API này**. Cấu hình mặc định của một resource server không thay thế việc tự xác định hợp đồng audience/scope của ứng dụng.

### 5.1. Chặn sớm ở tầng HTTP

~~~java
@Configuration
@EnableMethodSecurity
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/v1/catalog/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/v1/reports/*")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/v1/reports/*/rebuild")
                    .hasAuthority("SCOPE_reports.rebuild")
                .requestMatchers("/api/v1/admin/**")
                    .hasAuthority("SCOPE_admin.access")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đây là **bảng route tối giản cho ví dụ**, không phải cấu hình đầy đủ của một ứng dụng thực tế. Khi thêm API hợp lệ khác, đội phát triển phải thêm quy tắc tương ứng trước `anyRequest().denyAll()`. Quy tắc cụ thể nên đứng trước quy tắc bao quát và được kiểm thử khi thay đổi đường dẫn. `@EnableMethodSecurity` kích hoạt xử lý các annotation như `@PreAuthorize`.

Trong ví dụ, quyền được đọc từ **scope** đã xác thực, với ánh xạ mặc định từ scope sang authority có tiền tố `SCOPE_`. Nếu hệ thống dùng claim role/permission riêng, phải cấu hình `JwtAuthenticationConverter` phù hợp; không được giả định `ROLE_ADMIN`, `ADMIN` và `SCOPE_admin.access` là một. Kiểm soát issuer/audience có thể cấu hình ở `JwtDecoder` hoặc bộ validator tương ứng với authorization server.

Lệnh vô hiệu hóa CSRF ở trên chỉ thích hợp cho API stateless dùng Bearer token trong header, **không dùng cookie trình duyệt để tự gửi thông tin xác thực**. Nếu phiên web dựa trên cookie/session, cần duy trì cơ chế chống CSRF cho những thao tác thay đổi trạng thái. Trường hợp triển khai nhiều `SecurityFilterChain`, phải kiểm tra thứ tự và `securityMatcher` để tránh một route rơi vào chain nới lỏng hơn dự kiến. Cổng Actuator cần cấu hình exposure và chính sách bảo vệ riêng; chỉ public health theo nhu cầu đã xác định.

### 5.2. Đặt kiểm soát quyền ngay tại nghiệp vụ

Controller chỉ nhận HTTP và chuyển yêu cầu. Service thực thi chức năng đặc quyền mới là nơi cần bảo vệ lâu dài:

~~~java
@RestController
@RequestMapping("/api/v1/reports")
public class ReportAdminController {
    private final RebuildService rebuildService;

    public ReportAdminController(RebuildService rebuildService) {
        this.rebuildService = rebuildService;
    }

    @PostMapping("/{id}/rebuild")
    public ResponseEntity<Void> rebuild(@PathVariable UUID id) {
        rebuildService.requestRebuild(id);
        return ResponseEntity.accepted().build();
    }
}

@Service
public class RebuildService {
    private final ReportRepository reports;
    private final RebuildJobRepository jobs;
    private final CurrentTenant currentTenant;

    public RebuildService(ReportRepository reports,
                          RebuildJobRepository jobs,
                          CurrentTenant currentTenant) {
        this.reports = reports;
        this.jobs = jobs;
        this.currentTenant = currentTenant;
    }

    @PreAuthorize("hasAuthority('SCOPE_reports.rebuild')")
    @Transactional
    public void requestRebuild(UUID reportId) {
        // CurrentTenant lấy tenant từ danh tính/token đã được xác minh.
        String tenantId = currentTenant.requiredTenantId();

        Report report = reports.findByIdAndTenantId(reportId, tenantId)
            .orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND));

        // Ghi job vào DB trong cùng transaction; worker xử lý sau.
        jobs.save(new RebuildJob(report.getId(), tenantId));
    }
}
~~~

Các kiểu `ReportRepository`, `RebuildJobRepository`, `CurrentTenant` và entity trong đoạn mã là thành phần ứng dụng cần triển khai; ví dụ giả định `ReportRepository` cung cấp `findByIdAndTenantId(UUID, String)`. `CurrentTenant` phải lấy tenant từ principal hoặc claim đã được kiểm chứng, tuyệt đối không tin trực tiếp `tenantId` lấy từ request body/query string. Nếu token không có tenant hoặc tenant không hợp lệ, hãy từ chối yêu cầu.

Ở đây, `202 Accepted` phản ánh việc **đã ghi nhận yêu cầu xử lý**, không có nghĩa báo cáo đã được tái tạo xong. Nếu phải gửi job sang broker ngoài cơ sở dữ liệu, dùng transactional outbox hoặc cơ chế bảo đảm bàn giao phù hợp, tránh tình trạng đã trả `202` nhưng job bị mất. Tác vụ chạy nền cũng cần được gắn với phạm vi tenant và quyền thao tác hợp lệ.

Điểm cần chú ý về Spring AOP: `@PreAuthorize` dựa trên proxy. Lời gọi từ phương thức này sang phương thức khác trên **cùng instance** (self-invocation), hoặc đối tượng tạo bằng `new` thay vì bean do Spring quản lý, có thể không đi qua lời kiểm tra của proxy. Vì vậy, gọi service bảo vệ qua bean Spring, kiểm thử đường gọi thật và tránh đặt kiểm tra duy nhất tại phương thức có thể bị gọi nội bộ mà không qua proxy. Đừng mặc định scheduler hay message consumer an toàn chỉ vì chúng không đi qua HTTP; hãy thiết kế service hoặc policy riêng cho principal của từng loại caller.

### 5.3. Endpoint thay thế phải dùng cùng kiểm soát

Giả sử có controller cũ:

~~~java
@RestController
@RequestMapping("/api/v1/legacy")
class LegacyReportController {
    private final RebuildService rebuildService;

    LegacyReportController(RebuildService rebuildService) {
        this.rebuildService = rebuildService;
    }

    @PostMapping("/rebuild/{id}")
    ResponseEntity<Void> rebuildOld(@PathVariable UUID id) {
        rebuildService.requestRebuild(id);
        return ResponseEntity.accepted().build();
    }
}
~~~

Nếu `/api/v1/legacy/rebuild/{id}` chưa được cấp quyền tại lớp HTTP của ví dụ, `anyRequest().denyAll()` sẽ từ chối. Nếu dự án cho phép route legacy qua filter, `@PreAuthorize` ở `RebuildService` vẫn là lớp bảo vệ tiếp theo. Khi phát hiện một alias không còn cần dùng, nên ngừng công khai hoặc loại bỏ nó có kiểm soát; tránh duy trì hai chính sách quyền khác nhau cho cùng chức năng.

## 6. Phản hồi HTTP và hợp đồng lỗi

Client cần phân biệt thiếu xác thực, thiếu quyền và không tìm thấy tài nguyên. Việc trả cùng mã cho mọi trường hợp làm sai ngữ nghĩa và khiến kiểm thử khó chỉ ra điểm lỗi.

| Trường hợp | Phản hồi thường dùng | Giải thích |
| --- | --- | --- |
| Không có token hoặc token không hợp lệ | `401 Unauthorized` | Resource server có thể gửi `WWW-Authenticate: Bearer` |
| Token hợp lệ nhưng không có quyền `reports.rebuild` | `403 Forbidden` | Đăng nhập không đủ để thao tác |
| Có quyền chức năng nhưng báo cáo không thuộc tenant cho phép | `404 Not Found` hoặc `403 Forbidden` | Chọn thống nhất theo chính sách che giấu sự tồn tại đối tượng |
| Có quyền, đã ghi job thành công | `202 Accepted` | Xử lý bất đồng bộ; có thể trả `Location` tới job nếu hỗ trợ |
| Gửi sai phương thức vào route tồn tại | `405 Method Not Allowed` nếu router cho phép bộc lộ | Không dùng lỗi này thay thế kiểm tra quyền |

Ví dụ yêu cầu từ người dùng không đủ quyền:

~~~http
POST /api/v1/reports/6c84f5b0-2dcc-49e1-9d6b-aa113b8c2d90/rebuild HTTP/1.1
Authorization: Bearer <token-with-reports.read-only>
Content-Type: application/json

HTTP/1.1 403 Forbidden
Content-Type: application/problem+json

{
  "type": "https://api.example.test/problems/forbidden",
  "title": "Forbidden",
  "status": 403,
  "detail": "Bạn không có quyền thực hiện thao tác này."
}
~~~

Đây là ví dụ hai chiều request/response; `<token-with-reports.read-only>` chỉ là ký hiệu minh họa. Có thể dùng RFC 9457 Problem Details cho cấu trúc lỗi nhất quán. Không nên trả về stack trace, biểu thức policy nội bộ, thông tin về quyền của tài khoản khác hay bí mật hệ thống. Tùy cơ chế OAuth Bearer, response `403` cũng có thể mang `WWW-Authenticate` với `error="insufficient_scope"`; cân nhắc mức thông tin được phép công bố.

Khi backend từ chối, **không được thực hiện một phần tác dụng phụ rồi mới trả 403**. Kiểm tra quyền phải xảy ra trước việc ghi DB, gọi hệ thống ngoài, đưa message vào queue, thay đổi trạng thái tài khoản hoặc xuất file. Nếu thao tác có hiệu ứng nhiều bước, cần thêm quản lý transaction, idempotency, chính sách retry và kiểm soát quyền tương ứng.

## 7. Quy trình rà soát toàn bộ bề mặt quản trị

Lỗ hổng thường nằm ở tuyến truy cập ít được nhìn thấy. Một cuộc rà soát nên bắt đầu từ **chức năng có khả năng gây tác hại**, sau đó lần ngược tới tất cả cách gọi chức năng đó.

1. **Lập danh mục hành động nhạy cảm:** khóa/mở tài khoản, đổi quyền, thay cấu hình, phê duyệt, export, chạy lại job, xóa dữ liệu, reindex, deploy, debug, cache flush. Đừng chỉ tìm chuỗi `/admin`.
2. **Tìm mọi điểm vào:** các `@RequestMapping`/`@PostMapping`/`@DeleteMapping`, API version cũ, alias, reverse proxy rewrite, callback, actuator, endpoint thử nghiệm, chức năng batch và entry point từ dịch vụ nội bộ.
3. **Truy ngược tới service chung:** phương thức nào trực tiếp tạo tác dụng phụ? Các controller có cùng gọi một service đã được bảo vệ không? Có code path bypass qua self-invocation hoặc gọi repository thẳng không?
4. **Gắn policy rõ ràng:** định nghĩa permission, đối tượng, tenant, điều kiện ngữ cảnh và người/nhóm được cấp. Với nghiệp vụ nhạy cảm, kiểm tra thêm nguyên tắc phân tách nhiệm vụ hoặc giới hạn mức tiền, thời gian, môi trường.
5. **Đối chiếu cấu hình triển khai:** route qua gateway, load balancer, reverse proxy, management port và các filter chain. Không để lớp mạng trở thành kiểm soát quyền duy nhất.
6. **Kiểm thử từ chối và tác dụng phụ:** người dùng chưa xác thực, người dùng thường, người được cấp đúng quyền, người dùng có quyền nhưng khác tenant; kiểm tra sau `403` không phát sinh job, dữ liệu hay sự kiện.
7. **Theo dõi khi vận hành:** ghi audit event cho hành động đặc quyền và quyết định từ chối, giữ `requestId`, định danh actor, tenant, action, resource và kết quả. Không log raw JWT, mật khẩu hoặc dữ liệu nhạy cảm.

Với Spring MVC, có thể dùng `RequestMappingHandlerMapping` tại runtime để liệt kê các mapping thật, đối chiếu với bảng policy và cấu hình gateway. Tìm annotation tĩnh bằng công cụ tìm kiếm chỉ là bước khởi đầu: routing có thể sinh qua interface, cấu hình hoặc thư viện, nên kết quả runtime và kiểm thử HTTP mới chứng minh được route thực sự được bảo vệ.

Một số ca dễ bỏ sót:

- `GET` có tác dụng phụ do thiết kế sai; crawler hoặc người dùng thường có thể kích hoạt thao tác đặc quyền. Hãy dùng phương thức HTTP phù hợp và phân quyền theo chức năng.
- Các request `HEAD`, `OPTIONS`, CORS preflight, method override hoặc đường dẫn được chuẩn hóa/rewrite khác nhau giữa proxy và backend. Không xem việc preflight được phép là quyền gọi API thực tế.
- Swagger/OpenAPI mô tả security scheme nhưng backend không enforce. Tài liệu giúp client hiểu hợp đồng, không thay thế policy chạy thật.
- Endpoint có tên `internal`, chỉ gọi trong mạng công ty hoặc có mTLS: cần xét cả danh tính dịch vụ và quyền trên chức năng. mTLS chứng minh phía gọi ở tầng kết nối, chưa tự động chứng minh được mọi quyền nghiệp vụ.
- Kiểm tra `hasRole('ADMIN')` tại controller nhưng có code path gọi thẳng vào service, hoặc role/authority mapping sai tiền tố khiến policy không tương đương trên các phiên bản.
- Quyền bị thu hồi nhưng token còn hạn. Cần thời gian sống token hợp lý và cơ chế thu hồi/chặn khi yêu cầu nghiệp vụ cần hiệu lực tức thời.

## 8. Kiểm thử bảo mật có thể lặp lại

Kiểm thử phải xác nhận **trạng thái HTTP và việc không tạo ra tác dụng phụ**, đồng thời đi qua các endpoint thực tế. Với Spring, `spring-security-test` cung cấp `jwt()` và `@WithMockUser`; nên kết hợp kiểm thử HTTP với kiểm thử service để bắt cả lỗi filter và lỗi annotation.

Ma trận tối thiểu cho `POST /api/v1/reports/{id}/rebuild`:

| Danh tính dùng để thử | Kỳ vọng | Bất biến sau request |
| --- | --- | --- |
| Không gửi token | `401` | Không có job mới |
| Token có `reports.read` nhưng thiếu `reports.rebuild` | `403` | Không có job mới |
| Token có `reports.rebuild`, báo cáo đúng tenant | `202` | Có đúng một job hợp lệ |
| Token có `reports.rebuild`, báo cáo khác tenant | `404` theo policy ví dụ | Không có job mới |
| Có quyền nhưng đi qua endpoint alias cũ chưa cho phép | `403` với rule `denyAll` | Không có job mới |
| Token sai chữ ký, issuer, audience hoặc hết hạn | `401` | Không có job mới |

Ví dụ kiểm thử một người dùng chỉ có quyền đọc bị từ chối ngay tại HTTP filter:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationHttpIT {
    @Autowired MockMvc mvc;
    @Autowired RebuildJobRepository jobs;

    @Test
    void userWithReadScopeCannotCreateRebuildJob() throws Exception {
        UUID id = UUID.randomUUID();
        long before = jobs.count();

        mvc.perform(post("/api/v1/reports/{id}/rebuild", id)
                .with(jwt()
                    .jwt(j -> j.claim("tenant_id", "tenant-a"))
                    .authorities(new SimpleGrantedAuthority("SCOPE_reports.read"))))
            .andExpect(status().isForbidden());

        assertThat(jobs.count()).isEqualTo(before);
    }
}
~~~

Đoạn kiểm thử giả định có các static import tương ứng của MockMvc, Spring Security Test và AssertJ, cùng repository trong context. Đừng thay service bằng mock trong *mọi* bài kiểm thử quyền: khi đó có thể bỏ qua proxy `@PreAuthorize`, vô tình kiểm thử chỉ một lớp bảo vệ. Một bài kiểm thử bổ sung nên gọi bean `RebuildService` thật với principal thiếu `SCOPE_reports.rebuild` và xác nhận `AccessDeniedException`, kể cả nếu đường vào HTTP có thay đổi.

Quan trọng: `jwt()` của Spring Security Test tạo authentication cho bài kiểm thử; nó **không xác minh chữ ký, issuer hoặc audience của token thật**. Để kiểm tra các điều kiện đó, phải có test riêng đi qua `JwtDecoder`/resource server bằng token hợp lệ và token bị sửa hoặc có claim không hợp lệ, hoặc integration test với authorization server thử nghiệm. Dữ liệu test cho trường hợp cross-tenant phải có ít nhất hai tenant và hai report để chứng minh rằng sự từ chối xuất phát từ chính sách đối tượng.

Trong CI, nên bổ sung test để phát hiện **route quản trị mới chưa có policy** và test tất cả endpoint alias. Danh mục route từ `RequestMappingHandlerMapping`, mapping trên gateway và ma trận permission là ba nguồn cần đối chiếu khi review thay đổi.

## 9. Bài tập thực hành

**Bài tập 1 — Tìm lỗ hổng.** Một API dùng `.anyRequest().authenticated()`. Controller có `POST /api/v1/refunds/{id}/approve` gọi `refundService.approve(id)`; frontend chỉ hiển thị nút duyệt cho nhân viên tài chính. Hãy chỉ ra vì sao người dùng thường vẫn có thể duyệt hoàn tiền bằng cURL. Đề xuất quyền cụ thể, vị trí đặt kiểm tra ở filter và service, và hai trường hợp test âm tính.

**Bài tập 2 — Bảo vệ đường vào thay thế.** Chức năng `rebuild` hiện có hai route `/api/v1/admin/reports/{id}/rebuild` và `/api/v1/reports/{id}/rebuild`, cùng một service. Thiết kế lại để người có `reports.read` không thể gọi cả hai; người có `reports.rebuild` chỉ thao tác trên báo cáo cùng tenant. Nêu rõ phản hồi cho ba trường hợp: thiếu token, thiếu permission và sai tenant. Kiểm chứng sau mỗi lần bị từ chối không sinh job.

**Bài tập 3 — Rà soát một dự án Spring.** Dùng danh sách mapping tại runtime và cây call vào các service tạo tác dụng phụ để tìm ít nhất năm hành động đặc quyền. Lập bảng `HTTP method + path → action → permission → tenant/object condition → negative test`. Bổ sung test tự động cho route chưa được gán chính sách. Viết mô tả lỗ hổng ngắn, kèm request mẫu trước/sau sửa.

### Tiêu chí hoàn thành

Lời giải được xem là đạt khi (1) mọi endpoint thực hiện cùng hành động quản trị đều áp dụng một chính sách chức năng nhất quán; (2) dịch vụ nghiệp vụ không thể bị gọi bằng quyền người dùng thường qua một đường vào khác; (3) kiểm tra quyền đối tượng/tenant diễn ra trước tác dụng phụ; (4) `401`, `403`, `404`, `202` được dùng có chủ đích; và (5) kiểm thử chứng minh các thao tác bị từ chối không thay đổi dữ liệu hoặc tạo job.

## 10. Checklist khi review pull request

- Mọi route mới có phân loại quyền, được khai báo trong chính sách và được đưa vào tài liệu OpenAPI tương ứng.
- Endpoint cũ, endpoint nội bộ và đường dẫn alias có kiểm soát tương đương với endpoint chính.
- Phương thức nghiệp vụ nhạy cảm kiểm tra quyền trước khi ghi dữ liệu; self-invocation và các đường gọi không qua proxy đã được xem xét.
- Quyền chức năng và phạm vi tenant/đối tượng được kiểm tra độc lập; tham số do client gửi không tự cấp quyền.
- Có test cho `401`, `403`, cross-tenant, trường hợp thành công và sự bất biến khi từ chối.
- Log/audit đủ truy vết nhưng không chứa token hoặc bí mật; cấu hình gateway, security chain và management endpoints phù hợp với policy.

**Điểm cốt lõi:** một chức năng quản trị phải được bảo vệ tại **mọi cách gọi đến nó**. Endpoint thiếu bước kiểm soát quyền có thể trở thành đường vượt quyền dù cơ chế đăng nhập, giao diện và những endpoint quản trị khác đã được cấu hình đúng.
