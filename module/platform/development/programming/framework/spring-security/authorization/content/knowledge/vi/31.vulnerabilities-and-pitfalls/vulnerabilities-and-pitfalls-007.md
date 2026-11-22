# Ẩn nút trên giao diện nhưng thiếu kiểm soát tại server

> **Nhóm:** Sai sót và lỗ hổng trong Spring Security authorization. **Vấn đề:** frontend ẩn hoặc vô hiệu hóa một chức năng, nhưng endpoint/service backend vẫn chấp nhận request trái quyền. **Nguyên tắc:** UI chỉ hỗ trợ trải nghiệm; mọi request phải được backend xác thực và kiểm tra quyền trên *hành động* lẫn *tài nguyên cụ thể*.

## 1. Tình huống: không nhìn thấy nút vẫn gọi được API

Giả sử hệ thống quản lý báo cáo có:

- `an` sở hữu báo cáo `101` và có quyền `report:read`.
- `binh` sở hữu báo cáo `102`.
- Một reviewer được cấp cả `report:read` và quyền mở rộng `report:read:any`.

Giao diện React chỉ hiển thị nút/link khi quyền từ phiên người dùng có `report:read`:

~~~jsx
// Chỉ kiểm soát UI; không phải hàng rào bảo mật.
function ReportActions({ reportId, permissions }) {
  const canRead = permissions.includes("report:read");
  return canRead
    ? <a href={"/reports/" + reportId}>Xem báo cáo</a>
    : null;
}
~~~

Dù nút bị ẩn, trình duyệt của người dùng vẫn có thể gửi request bằng DevTools, hoặc người dùng dùng curl/Postman để gọi API trực tiếp:

~~~http
GET /api/reports/102 HTTP/1.1
Host: example.test
Authorization: Bearer <access-token-of-an>
~~~

Đoạn HTTP trên minh họa một ứng dụng có Bearer token hợp lệ; ví dụ ứng dụng Spring Boot ở phần sau dùng HTTP Basic để dễ kiểm thử nên không được hiểu rằng Bearer header tự hoạt động trong chương trình đó.

Nếu backend chỉ kiểm tra “đã đăng nhập” rồi truy vấn `reports.findById(102)` mà không kiểm tra quyền trên bản ghi, `an` có thể đọc báo cáo của `binh`. Đổi ID cũng có thể dẫn tới hành vi phê duyệt, sửa hoặc xóa báo cáo của người khác. Đây là **Broken Access Control** và đặc biệt là **BOLA/IDOR**: thiếu authorization ở cấp đối tượng.

Cần phân biệt hai câu hỏi:

1. **Function-level:** principal có được gọi chức năng đọc, sửa, duyệt hoặc xóa báo cáo?
2. **Object-level:** principal có được thực hiện chức năng đó trên **báo cáo có ID đang yêu cầu** không?

Ẩn nút trên UI không chứng minh được cả hai. Kể cả backend dùng `hasAuthority("report:read")`, hệ thống vẫn mắc IDOR nếu người có quyền đọc báo cáo của mình có thể đọc của người khác.

## 2. Vì sao UI guard, CSS và route guard không đủ?

Frontend chạy trên môi trường người dùng có quyền quan sát và điều khiển. Một người dùng có thể:

- Gọi endpoint trực tiếp, bỏ qua nút hoặc trang.
- Đổi path/query/body, ví dụ `/api/reports/101` thành `/api/reports/102`.
- Sửa `role`, `permissions`, `isAdmin` hoặc `ownerId` trong JavaScript/runtime/request.
- Gửi lại request từng chạy thành công hoặc tự viết HTTP client.
- Sử dụng endpoint khác (mobile API, GraphQL, batch/export, URL cũ), dù menu hiện hành không nhắc tới.

Vì vậy **không tin** các field `isAdmin=true`, `ownerId` hay `tenantId` do client gửi để quyết định phân quyền. Server phải xác thực danh tính qua cơ chế đáng tin (session/token đã kiểm chứng) rồi đối chiếu quyền thực tế và tài nguyên đang truy cập.

Frontend vẫn nên ẩn/disable nút: giảm nhầm lẫn và cải thiện UX. Tuy nhiên không gọi nó là “đã bảo vệ chức năng” nếu API vẫn thiếu authorization.

## 3. Mã có lỗ hổng: nhận diện trước khi sửa

Đoạn sau **cố ý không an toàn**, chỉ minh họa một controller Spring MVC thiếu object-level authorization:

~~~java
// VULNERABLE: giả định người dùng đã đăng nhập,
// nhưng không kiểm tra họ có quyền đọc id cụ thể hay không.
@GetMapping("/api/reports/{id}")
public Report view(@PathVariable long id) {
    return repository.findById(id)
            .orElseThrow(() -> new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Report not found"));
}
~~~

Một biến thể nguy hiểm khác cho chức năng ghi:

~~~java
// VULNERABLE: quyền từ request body không đáng tin.
@PostMapping("/api/reports/{id}/approve")
public void approve(@PathVariable long id,
                    @RequestBody ApproveRequest body) {
    if (body.isAdmin()) {
        reportService.approve(id);
    }
}
~~~

Bất cứ client nào cũng có thể tự đặt `isAdmin=true`. Không nên kiểm tra quyền bằng “nút có hiển thị”, “UI có gửi trường isAdmin” hoặc “người dùng biết URL bí mật”. Server phải kiểm tra từ `Authentication` đã được thiết lập bởi security filter chain, sau đó kiểm tra owner/tenant/trạng thái đối tượng.

## 4. Thiết kế bản sửa: defense in depth

Một thiết kế an toàn có ba lớp kiểm tra:

- **Authentication:** danh tính/principal từ session, HTTP Basic, JWT/OIDC… đã được server xác minh.
- **Authorization theo endpoint:** `SecurityFilterChain` với `authorizeHttpRequests`/`requestMatchers` quy định những quyền được phép gọi HTTP method và path tương ứng.
- **Authorization theo nghiệp vụ/tài nguyên:** service/domain policy kiểm tra owner, tenant, quan hệ được phân công, trạng thái và quyền đặc biệt của bản ghi trước khi truy cập hoặc thay đổi nó.

Dùng **deny by default** cho những endpoint chưa được liệt kê. Đặt kiểm tra quan trọng trong service để đường vào khác (controller mới, API khác, job, handler) không dễ bỏ qua. Spring Security hỗ trợ `@EnableMethodSecurity` và `@PreAuthorize` cho Spring bean; lời gọi phải đi qua proxy Spring. Tự khởi tạo service bằng `new` hoặc self-invocation `this.protectedMethod()` có thể không chạy interceptor.

| Tình huống | Kết quả HTTP thường dùng |
| --- | --- |
| Không có thông tin đăng nhập hợp lệ | `401 Unauthorized` với API HTTP authentication, hoặc login redirect tùy cấu hình |
| Đã xác thực nhưng thiếu quyền chức năng | `403 Forbidden` |
| Có quyền chức năng nhưng sai owner/tenant | `403` hoặc `404` theo chính sách chống tiết lộ sự tồn tại |
| Đủ quyền và bản ghi tồn tại | `200 OK` khi đọc |
| Đủ quyền nhưng bản ghi không tồn tại | `404 Not Found` |

Status HTTP là **kết quả sau kiểm tra**, không phải thay thế authorization. Không trả một phần dữ liệu nhạy cảm rồi để frontend ẩn.

## 5. Bài thực hành hoàn chỉnh: Spring Boot, Java 17+, Spring MVC

Ví dụ theo **Spring Boot 3.x / Spring Security 6.x**, Java 17+. API demo chỉ có `GET /api/reports/{id}`; dữ liệu nằm trong memory để tập trung vào kiểm tra owner. Khi triển khai thật, cần thay nguồn dữ liệu bằng DB có lọc theo tenant/owner và thay cơ chế xác thực demo bằng cấu hình phù hợp.

### 5.1. Maven dependencies

Trong Spring Boot Maven project đã cấu hình parent hoặc BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

### 5.2. Bật bảo vệ ở method/service

Tạo `src/main/java/com/example/authorization/AuthorizationDemoApplication.java`:

~~~java
package com.example.authorization;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class AuthorizationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationDemoApplication.class, args);
    }
}
~~~

`@EnableMethodSecurity` **không mặc định được bật** chỉ bằng cách thêm Spring Security Starter. Nó đăng ký method-security interceptors để `@PreAuthorize` hoạt động ở các bean.

### 5.3. HTTP authorization: từ chối mặc định

Tạo `src/main/java/com/example/authorization/SecurityConfig.java`:

~~~java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/*")
                    .hasAuthority("report:read")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

`GET /api/reports/{id}` yêu cầu authority **đúng chuỗi** `report:read`; các request khác bị deny. HTTP Basic dùng để thử response 401 đơn giản, không phải gợi ý dùng username/password Basic cho mọi môi trường production. Bài demo chỉ có GET nên không phải tắt CSRF; giữ CSRF mặc định cho các unsafe methods khi thêm tính năng ghi. `hasRole('ADMIN')` thường tương ứng authority `ROLE_ADMIN`, khác `hasAuthority('ADMIN')`.

### 5.4. Model và repository

Tạo `src/main/java/com/example/authorization/Report.java`:

~~~java
package com.example.authorization;

public record Report(long id, String owner, String title) {
}
~~~

Tạo `src/main/java/com/example/authorization/ReportRepository.java`:

~~~java
package com.example.authorization;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Repository;

@Repository
public class ReportRepository {

    private final Map<Long, Report> reports = Map.of(
            101L, new Report(101L, "an", "Bao cao cua An"),
            102L, new Report(102L, "binh", "Bao cao cua Binh")
    );

    public Optional<Report> findById(long id) {
        return Optional.ofNullable(reports.get(id));
    }
}
~~~

Dữ liệu cố định giúp test được IDOR: `an` và `binh` cùng có bản ghi nhưng owner khác nhau. `Map.of` là immutable; ví dụ không xây dựng tác vụ update.

### 5.5. Kiểm tra quyền đối với đúng báo cáo

Tạo `src/main/java/com/example/authorization/ReportPolicy.java`:

~~~java
package com.example.authorization;

import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {

    private final ReportRepository repository;

    public ReportPolicy(ReportRepository repository) {
        this.repository = repository;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return repository.findById(id)
                .map(report ->
                        report.owner().equals(authentication.getName())
                        || authentication.getAuthorities().stream()
                                .anyMatch(a ->
                                        "report:read:any".equals(a.getAuthority())))
                .orElse(false);
    }
}
~~~

Policy lấy tên đăng nhập từ `Authentication` do Spring Security thiết lập. Người dùng được đọc khi **là owner**, hoặc được backend cấp authority mở rộng `report:read:any`. Quyền đó không tự xuất hiện khi client sửa biến JS. Với bản ghi không tồn tại, policy trả `false`; ví dụ cố ý trả 403 từ method security thay vì tiết lộ sự tồn tại tài nguyên.

### 5.6. Service bảo vệ cả chức năng và đối tượng

Tạo `src/main/java/com/example/authorization/ReportService.java`:

~~~java
package com.example.authorization;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class ReportService {

    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('report:read') and @reportPolicy.canRead(authentication, #p0)"
    )
    public Report read(long id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Report not found"));
    }
}
~~~

`#p0` là tham số đầu tiên (`id`) của method trong SpEL; không phụ thuộc Java compiler có ghi metadata tên tham số. Biểu thức `and` bắt buộc có **cả** `report:read` và permission trên ID. Quyền `report:read:any` bỏ giới hạn owner nhưng **không** thay thế `report:read`. `ResponseStatusException(404)` là fallback nếu dữ liệu biến mất sau lúc kiểm tra hoặc khi policy khác cho phép lookup mà bản ghi không còn.

### 5.7. Controller gọi service đã được bảo vệ

Tạo `src/main/java/com/example/authorization/ReportController.java`:

~~~java
package com.example.authorization;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final ReportService service;

    public ReportController(ReportService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    public Report view(@PathVariable long id) {
        return service.read(id);
    }
}
~~~

Controller không đọc `isAdmin` hoặc `ownerId` từ browser để cấp quyền. Nó gọi một Spring bean qua dependency injection; Spring method-security proxy bảo vệ lời gọi ngay cả khi sau này có nhiều controller.

## 6. Kiểm thử tấn công trực tiếp API bằng MockMvc

Người kiểm thử **không cần nhìn hoặc nhấp nút frontend**. Test gửi request thẳng tới endpoint với các danh tính/quyền khác nhau và thử thay ID. `@SpringBootTest` + `@AutoConfigureMockMvc` cho phép chạy SecurityFilterChain thật; `@WithMockUser` đặt danh tính giả phục vụ authorization test.

Tạo `src/test/java/com/example/authorization/ReportSecurityIntegrationTest.java`:

~~~java
package com.example.authorization;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ReportService service;

    @Test
    void anonymousGets401() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:write")
    void missingReadAuthorityGets403() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void ownerCanReadOwnRecord() throws Exception {
        mvc.perform(get("/api/reports/101"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(101))
                .andExpect(jsonPath("$.owner").value("an"));
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void changingIdCannotReadAnotherOwnersRecord() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(
            username = "reviewer",
            authorities = {"report:read", "report:read:any"})
    void reviewerMayReadWithExplicitElevatedAuthority() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("binh"));
    }

    @Test
    @WithMockUser(username = "reviewer", authorities = "report:read:any")
    void elevatedObjectAuthorityAloneIsInsufficient() throws Exception {
        mvc.perform(get("/api/reports/102"))
                .andExpect(status().isForbidden());
    }

    @Test
    @WithMockUser(username = "an", authorities = "report:read")
    void serviceItselfAlsoEnforcesOwnerPolicy() {
        assertThrows(AccessDeniedException.class,
                () -> service.read(102L));
    }
}
~~~

Lệnh từ thư mục gốc dự án Maven đã khai báo các dependency trên:

~~~bash
./mvnw -Dtest=ReportSecurityIntegrationTest test
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd -Dtest=ReportSecurityIntegrationTest test
~~~

**Kết quả kỳ vọng:** cả **7 test PASS** khi project được cấu hình đúng. Test không có `System.out.println` nên không có stdout chương trình riêng để dự đoán; thông điệp Maven tùy plugin/phiên bản. Đây là kỳ vọng từ logic mẫu, không phải báo cáo đã thực chạy Maven.

| Ca | Context/đường dẫn | Kỳ vọng |
| --- | --- | --- |
| Chưa đăng nhập | GET `/api/reports/101` | `401` với HTTP Basic |
| Đã đăng nhập, không có `report:read` | `an` GET `101` | `403` |
| Đủ quyền và đúng owner | `an` GET `101` | `200`, JSON owner `an` |
| Đủ quyền chức năng nhưng sai owner | `an` GET `102` | `403` |
| Reviewer được cấp cả hai authority | `reviewer` GET `102` | `200`, owner `binh` |
| Reviewer chỉ có `report:read:any` | GET `102` | `403` |
| Bỏ qua HTTP, gọi trực tiếp service | `an` gọi `service.read(102)` | `AccessDeniedException` |

Bộ test nêu bật **kiểm tra âm tính**: chính việc không có nút trên UI không liên quan đến khả năng chặn request. Test cuối còn phát hiện lỗi chỉ bảo vệ ở controller nhưng quên rule tại service. `@WithMockUser` không xác minh password/JWT thật; cần test riêng cho cơ chế login/token.

## 7. Các cơ chế khác không thay thế server authorization

| Cơ chế | Nó làm gì | Giới hạn |
| --- | --- | --- |
| UI ẩn/disable nút | UX, ngăn thao tác vô tình | Request trực tiếp vẫn được gửi |
| Frontend route guard | Điều hướng màn hình | Không bảo vệ API |
| Authentication | Kiểm chứng danh tính | Không cấp quyền vô hạn lên mọi object |
| `SecurityFilterChain` | Bảo vệ HTTP endpoint, method, path | Chưa tự biết owner/tenant của từng ID |
| `@PreAuthorize`/domain policy | Phân quyền dựa trên principal và nghiệp vụ | Cần bật method security, không được bypass proxy |
| CORS | Hạn chế script cross-origin trong browser | Không ngăn curl/Postman hoặc người dùng cùng origin |
| CSRF | Bảo vệ request thay đổi trạng thái khi browser tự gửi credentials | Không thay thế role/owner authorization |
| JWT validation | Kiểm chứng token hợp lệ và các claim liên quan | Không tự cấp quyền đọc mọi bản ghi |
| WAF/API gateway | Lọc/ràng buộc truy cập ở rìa hệ thống | Thường không biết chính sách từng object trong DB |

Nếu JWT chứa `role` hoặc `scope` do nhà cấp token ký, backend có thể tin các claim **sau khi xác thực chữ ký, issuer, audience, expiry…** theo ứng dụng; tuy nhiên vẫn cần kiểm tra quyền trên `reportId`. Tuyệt đối không chỉ tin bản JWT do client tự decode trên JS, hay tin field `isAdmin` chưa được server xác minh.

## 8. Khi thêm thao tác POST/PUT/DELETE

Hành động ghi và xóa cần authority **khác đọc** và policy về trạng thái/owner. Ví dụ snippet (không nằm trong project GET độc lập phía trên):

~~~java
@PreAuthorize(
    "hasAuthority('report:approve') and " +
    "@reportPolicy.canApprove(authentication, #p0)"
)
public void approve(long id) {
    // Chỉ cập nhật trạng thái sau khi được phân quyền.
}
~~~

Phải viết thêm `canApprove` thật trước khi sử dụng snippet. Policy duyệt có thể yêu cầu user được phân công, đúng tenant, trạng thái cho phép duyệt, không tự duyệt tài liệu của mình. Không suy ra quyền approve từ việc thấy nút hoặc quyền đọc.

Những điểm cần làm khi đưa lên production:

- **Ràng buộc truy vấn DB** bằng identity đã xác thực, ví dụ `WHERE id = :id AND tenant_id = :trustedTenantId`; với owner thì thêm điều kiện owner hoặc dùng policy đặc thù. Không dùng `tenantId` do client cung cấp làm trusted value.
- **Tránh TOCTOU:** sau bước check, owner/status có thể đổi trước update; cân nhắc update có điều kiện, optimistic locking, transaction và kiểm tra row count.
- **Bulk/list/export:** kiểm tra quyền với từng bản ghi; không trả tất cả báo cáo rồi để JavaScript lọc, vì dữ liệu đã được lộ qua response.
- **Files/download:** không chỉ ẩn link tải; endpoint hoặc ký URL tải phải có authorization đúng resource và thời hạn.
- **Cache:** cache key phải phân biệt principal/tenant khi dữ liệu phụ thuộc quyền; không reuse response người khác.
- **Audit:** ghi principal, hành động, ID, kết quả deny/allow theo policy dữ liệu; không log credential hoặc nội dung nhạy cảm.
- **CSRF:** giữ bảo vệ phù hợp cho các unsafe HTTP methods khi browser dùng session/cookie hay credentials tự gửi; không tắt CSRF để “sửa 403” nếu chưa hiểu mô hình xác thực.

## 9. Sai sót thường gặp và hướng sửa

**Chỉ `anyRequest().authenticated()`.** Bất kỳ user đăng nhập nào cũng gọi được API, chưa có chức năng/owner check. Khắc phục bằng rule theo method/path và policy theo đối tượng.

**Chỉ `hasRole('USER')`.** Mọi user thường đều có role này; người dùng A có thể truy cập bản ghi B. Kiểm tra owner/tenant cùng với chức năng.

**Quyền nằm duy nhất ở UI.** Ẩn nút, disable, CSS `display:none` hoặc route guard không chặn HTTP request; backend bắt buộc ra quyết định.

**Quyền nằm duy nhất ở controller.** Controller mới, message handler hoặc method service khác có thể đi đường vòng; đưa policy cốt lõi vào tầng nghiệp vụ và viết test gọi trực tiếp service.

**`@PreAuthorize` không có tác dụng.** Xác minh `@EnableMethodSecurity`, proxy Spring và tránh self-invocation. Không tự `new` service cần bảo vệ.

**Đưa owner/tenant lên client để quyết định.** Request body/query/header có thể bị giả mạo; luôn đối chiếu với server-side principal và dữ liệu domain.

**Trả cả tập dữ liệu rồi lọc ở frontend.** API response vẫn chứa thông tin trái quyền. Lọc ở query/server trước khi serialize.

**Nhầm 401/403/404.** HTTP status phụ thuộc quy tắc; tests phải chỉ ra một hành động có được phép không, và có phát dữ liệu trái phép không. Có thể dùng 404 để hạn chế lộ sự tồn tại, nhưng không dùng việc đổi status thay cho policy.

**Chỉ test luồng được phép.** Bổ sung anonymous, thiếu quyền, sai owner, sai tenant, ID không tồn tại, quyền đặc biệt, bulk và direct service.

**Nhầm CORS/CSRF với authorization.** CORS không chặn API client có chủ ý; CSRF không quyết định ai có quyền trên báo cáo.

## 10. Quy trình kiểm tra một tính năng đang ẩn nút

1. Xác định nút thực sự gọi HTTP method/path nào, nhận ID/body gì và gây tác dụng phụ gì.
2. Liệt kê quyền chức năng và chính sách theo resource: owner, tenant, reviewer, trạng thái.
3. Test HTTP **không qua giao diện** bằng MockMvc hoặc API client với user anonymous, ít quyền, đúng quyền, sai owner và user tenant khác.
4. Kiểm tra cấu hình `SecurityFilterChain` và service/domain authorization; policy phải lấy danh tính từ authentication đáng tin.
5. Bổ sung test negative chứng minh response không chứa dữ liệu trái quyền và database không thay đổi khi bị deny.
6. Kiểm tra các đường vào khác: GraphQL, batch, export, file URL, job, API cũ, endpoint mới.
7. Khi backend đã an toàn, giữ logic ẩn nút để cải thiện UX, đồng bộ thông báo lỗi `403`/`404`.

### Checklist review

- [ ] Không xem ẩn/disable nút là biện pháp bảo mật.
- [ ] Mỗi endpoint có authentication và quyền đúng chức năng.
- [ ] Mỗi tài nguyên có kiểm tra owner/tenant/status cần thiết.
- [ ] Không tin `isAdmin`, `ownerId`, `tenantId` từ client.
- [ ] Có deny-by-default và guard ở tầng service/domain.
- [ ] Không có đường vòng do self-invocation/proxy hoặc API khác.
- [ ] Có test anonymous, thiếu quyền, sai owner, đúng owner, quyền đặc biệt.
- [ ] POST/PUT/DELETE, bulk/export/cache/file download có policy riêng.
- [ ] Không để lộ dữ liệu trước khi server quyết định allow.

## Tài liệu chính thức và tham khảo

- [Spring Security — HTTP Request Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Security — Testing with MockMvc and @WithMockUser](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [OWASP API Security Top 10:2023 — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/)
- [OWASP Top 10 — Broken Access Control](https://owasp.org/Top10/A01_2021-Broken_Access_Control/)

**Bài tự luyện:** thêm endpoint phê duyệt chỉ cho người có `report:approve` và được phân công cho đúng báo cáo. Viết test thiếu authority, sai resource, đúng resource và client tự gửi `isAdmin=true`. Chính server phải từ chối ba request đầu không đủ quyền dù frontend có thể ẩn hoặc hiện nút tùy ý.