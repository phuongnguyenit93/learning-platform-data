# Đăng ký nhiều IdP và chọn nhà cung cấp trên trang đăng nhập với Spring Security SAML2

Một ứng dụng **Service Provider (SP/Relying Party)** có thể cho người dùng đăng nhập bằng nhiều **Identity Provider (IdP/Asserting Party)**: IdP nội bộ của nhân viên, IdP đối tác, hoặc các IdP của từng tenant. Trong Spring Security SAML 2.0, mỗi quan hệ tin cậy SP–IdP được biểu diễn bằng một **`RelyingPartyRegistration`**, nhiều registration được quản lý qua **`RelyingPartyRegistrationRepository`**. Trang đăng nhập có thể trình bày các lựa chọn IdP rồi đưa người dùng tới **`/saml2/authenticate/{registrationId}`** để bắt đầu SAML Web Browser SSO.

**Nguyên tắc cốt lõi:** trang chọn IdP chỉ quyết định **nơi bắt đầu xác thực**, không tự xác thực người dùng, không xác nhận quyền tenant và không được lấy IdP SSO URL do trình duyệt cung cấp tùy ý. Sau khi IdP trả SAMLResponse, Spring Security vẫn phải kiểm chứng đúng registration, chữ ký, issuer, audience, recipient, thời hạn và tương quan AuthnRequest; ứng dụng phải kiểm tra quyền/tenant độc lập.

Bài học thuộc **Spring Security – federation → Nhiều IdP và tenant**. Nội dung bao gồm cấu hình nhiều IdP, trang chọn mặc định và tùy chỉnh, tenant discovery, quản lý metadata/registration, an toàn đa tenant, ví dụ Java 17 chạy độc lập và checklist vận hành.

## 1. Bài toán nhiều IdP xuất hiện như thế nào?

Giả sử một Portal có ba nhóm người dùng:

| Nhóm | Tổ chức xác thực | Mục đích |
| --- | --- | --- |
| Nhân viên | IdP doanh nghiệp | Truy cập hệ thống nội bộ |
| Đối tác cung ứng | IdP đối tác | Truy cập cổng nhà cung cấp |
| Khách hàng B2B | IdP riêng của từng tenant | Truy cập dữ liệu chỉ của tổ chức tương ứng |

Khi truy cập `https://portal.example.test/private`, người dùng chưa đăng nhập phải xác định **IdP nào thực hiện authentication**. Có thể hiện trang chọn:

~~~text
                 PORTAL — ĐĂNG NHẬP
      +-----------------------------------+
      | Chọn tổ chức hoặc nhà cung cấp    |
      |                                   |
      | [Đăng nhập nhân viên]             |
      | [Đăng nhập đối tác]               |
      |                                   |
      | Nếu thuộc khách hàng B2B:         |
      | nhập mã tổ chức do bạn được cấp   |
      +-----------------------------------+
          |                      |
          v                      v
/saml2/authenticate/corp   /saml2/authenticate/partner
          |                      |
          v                      v
     IdP doanh nghiệp      IdP đối tác
          |                      |
          +-----------+----------+
                      |
               POST SAMLResponse
                      |
             Spring Security SP
                      |
          Kiểm chứng + tạo Authentication
                      |
                Kiểm tra tenant
~~~

Trang chọn **không nhất thiết chứa tất cả IdP** của hệ thống. Với hàng nghìn tenant, trang công khai liệt kê toàn bộ IdP vừa khó sử dụng vừa có thể tiết lộ tên khách hàng. Có thể dùng mã tổ chức, domain discovery hoặc link đăng nhập đã được cấp trước, nhưng vẫn phải ánh xạ tới **một registration được cấu hình và tin cậy ở server**.

## 2. Những loại định danh dễ bị nhầm

| Thành phần | Ví dụ | Ai định nghĩa? | Tác dụng |
| --- | --- | --- | --- |
| `registrationId` | `corp` | SP/Spring Security | Khóa nội bộ để tìm registration |
| IdP `entityId` | `https://login.corp.example.test/idp` | IdP | Định danh protocol/issuer đáng tin |
| SP `entityId` | `https://portal.example.test/saml/sp` | SP | Định danh service provider mà IdP tin |
| IdP SSO endpoint | `https://login.corp.example.test/sso` | IdP metadata | Đích gửi AuthnRequest |
| SP ACS endpoint | `https://portal.example.test/login/saml2/sso/corp` | SP | Nơi nhận SAMLResponse |
| Tenant ID | `org-blue` | Ứng dụng nghiệp vụ | Phạm vi dữ liệu và quyền truy cập |
| Tên hiển thị trên trang | `Nhân viên công ty` | UX/SP | Nhãn dễ đọc, không phải SAML identity |
| Subject/NameID | Giá trị được IdP phát trong assertion | IdP trong phạm vi liên kết | Nhận dạng người dùng sau khi đã xác minh |

**Ba giá trị `registrationId`, IdP entityID và tenant ID không mặc nhiên giống nhau.** Một IdP có thể phục vụ nhiều tenant; một tenant cũng có thể có nhiều IdP (ví dụ IdP chính và IdP dự phòng đã được phê duyệt). Việc chọn IdP là một bước của luồng đăng nhập, không đủ để xác định quyền trên tenant.

**Ví dụ:** `registrationId=partner` chỉ nói ứng dụng muốn bắt đầu SSO qua cấu hình `partner`. Nó không chứng minh người dùng thuộc tenant đối tác nào hoặc có quyền `ROLE_ADMIN`.

## 3. Luồng chuẩn: từ trang đăng nhập đến SAMLResponse

~~~text
(1) Browser GET /private
            |
            v
(2) ExceptionTranslationFilter -> yêu cầu authentication
            |
            v
(3) Trang chọn IdP (/login hoặc /login/choose)
            |
   Người dùng chọn "corp"
            |
            v
(4) GET /saml2/authenticate/corp
            |
            v
(5) Saml2WebSsoAuthenticationRequestFilter
     -> RelyingPartyRegistrationRepository
     -> findByRegistrationId("corp")
     -> tạo AuthnRequest với issuer/ACS/destination
     -> lưu request correlation
            |
            v
(6) Browser đến IdP corp theo HTTP Redirect/POST
            |
            v
(7) IdP xác thực và trả SAMLResponse về SP ACS
            |
            v
(8) Saml2WebSsoAuthenticationFilter / OpenSAML
     -> resolve registration phù hợp
     -> verify signature, issuer, audience, recipient,
        response/assertion time và InResponseTo
            |
            v
(9) Tạo Authentication và session SP
            |
            v
(10) Authorization: account/tenant/role/resource
~~~

Mỗi bước có một trách nhiệm riêng:

- **Picker:** hiển thị lựa chọn được phép và link khởi tạo.
- **Repository:** lưu cấu hình tin cậy, không giữ tài khoản/mật khẩu.
- **SAML AuthnRequest resolver/filter:** tạo thông điệp đi tới IdP.
- **Response provider/filter:** xác minh thông điệp SAML trả về.
- **Ứng dụng:** liên kết account nội bộ, xác định tenant membership và quyền nghiệp vụ.

**Không nhầm điểm bắt đầu `/saml2/authenticate/corp` với ACS `/login/saml2/sso/corp`.** Trình duyệt gọi điểm bắt đầu để đi tới IdP; IdP gửi response về ACS sau khi xác thực.

## 4. Các API cốt lõi của Spring Security

| API/class | Vai trò |
| --- | --- |
| `RelyingPartyRegistration` | Mô tả một cặp SP–IdP, endpoint, entity IDs và credentials |
| `RelyingPartyRegistrationRepository` | Tra cứu registration theo `registrationId` |
| `InMemoryRelyingPartyRegistrationRepository` | Giữ tập registrations trong bộ nhớ; hỗ trợ iteration |
| `IterableRelyingPartyRegistrationRepository` | Hợp đồng repository có thể duyệt tất cả registration |
| `RelyingPartyRegistrations` | Tạo builder từ metadata IdP |
| `DefaultLoginPageGeneratingFilter` | Tạo trang đăng nhập mặc định khi điều kiện cấu hình cho phép |
| `Saml2WebSsoAuthenticationRequestFilter` | Xử lý endpoint bắt đầu SSO, tạo AuthnRequest |
| `Saml2AuthenticationRequestResolver` | Quyết định cách tạo AuthnRequest từ HTTP request |
| `Saml2WebSsoAuthenticationFilter` | Xử lý SAMLResponse tại ACS |
| `Saml2AuthenticationTokenConverter` | Đọc SAMLResponse và giải quyết registration phù hợp |
| `Saml2AuthenticationRequestRepository` | Lưu request đã phát để đối chiếu khi Response trở về |

**Đặc biệt:** `InMemoryRelyingPartyRegistrationRepository` implements `IterableRelyingPartyRegistrationRepository`. Khi nhiều registration và trang login mặc định được bật, Spring Security có thể **liệt kê các registrations để tạo các link SAML**. Một custom repository chỉ implements interface tra cứu cơ bản mà **không Iterable** có thể không cung cấp đủ thông tin cho trang picker mặc định.

Từ Spring Security 6.4, interface tên `IterableRelyingPartyRegistrationRepository` được chuẩn hóa; `InMemoryRelyingPartyRegistrationRepository` vẫn hỗ trợ duyệt. Khi nâng từ 5.x sang 6.x/7.x, kiểm tra các lớp/import và cơ chế trang login đúng release.

## 5. Cách 1 — Spring Boot properties: đăng ký nhiều IdP

Nếu Spring Boot 3.x tự cấu hình SAML2 từ properties, có thể khai báo nhiều mục bên dưới:

`src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    saml2:
      relyingparty:
        registration:
          corp:
            assertingparty:
              metadata-uri: "classpath:saml/corp-idp.xml"
          partner:
            assertingparty:
              metadata-uri: "classpath:saml/partner-idp.xml"
~~~

Hai tệp `src/main/resources/saml/corp-idp.xml` và `partner-idp.xml` phải là **metadata XML thực của hai IdP đã được tin cậy**. Metadata thường chứa IdP entityID, SSO endpoint/binding và public certificate dùng kiểm chứng chữ ký. **Đây là mẫu cấu hình ứng dụng, không thể chạy SSO nếu không có metadata thật, IdP thật và SP được đăng ký tại IdP.**

Kết quả logic:

| URL người dùng chọn | Registration được sử dụng | Đích |
| --- | --- | --- |
| `/saml2/authenticate/corp` | `corp` | SSO endpoint thuộc IdP corp |
| `/saml2/authenticate/partner` | `partner` | SSO endpoint thuộc IdP partner |
| `/login/saml2/sso/corp` | Callback ACS theo cấu hình `corp` | SP xác minh response |
| `/login/saml2/sso/partner` | Callback ACS theo cấu hình `partner` | SP xác minh response |
| `/saml2/metadata/corp` | SP metadata cho `corp` nếu bật metadata DSL | IdP corp dùng đăng ký SP |
| `/saml2/metadata/partner` | SP metadata cho `partner` nếu bật metadata DSL | IdP partner dùng đăng ký SP |

Khi dùng builder/metadata, Spring Security có thể resolve SP `entityId` và `assertionConsumerServiceLocation` từ URL template. **Phải so metadata SP thực tế với cấu hình IdP**. Nếu tổ chức yêu cầu riêng signing credential cho AuthnRequest hoặc decryption credential cho encrypted assertion, cần cấu hình bổ sung. Không tắt SAML signature validation khi tích hợp.

### Khai báo metadata-uri có đồng nghĩa tự refresh không?

Không. Với Spring Boot tạo một `InMemoryRelyingPartyRegistrationRepository`, metadata có thể được nạp và dựng thành registration lúc khởi động. Nếu IdP đổi certificate hoặc SSO URL, repository trong memory **không tự theo dõi mọi thay đổi**. Có thể dùng cơ chế metadata repository/refresh/cache theo version, nhưng phải định nghĩa chính sách trust, TTL, `validUntil`, rollover và behavior khi IdP metadata URL gặp lỗi.

### Có cần tạo Java @Bean repository riêng cùng lúc không?

Không mặc định. **Properties** và **bean thủ công** là **hai lựa chọn cấu hình thay thế**. Khi bạn tự khai báo `RelyingPartyRegistrationRepository` bean, Spring Boot thường lùi cấu hình tự động tương ứng; đừng giả định Boot sẽ hợp nhất hai tập registration.

## 6. Cách 2 — Tạo InMemory repository với nhiều registrations

Khi cần tùy biến Java, có thể xây mỗi registration từ metadata IdP đã được xác minh rồi trả về một repository có khả năng duyệt.

Tệp `src/main/java/com/example/security/MultiIdpSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.saml2.provider.service.registration.InMemoryRelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistration;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrations;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIdpSecurityConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingPartyRegistrationRepository() {
        RelyingPartyRegistration corp = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/corp-idp.xml")
            .registrationId("corp")
            .build();

        RelyingPartyRegistration partner = RelyingPartyRegistrations
            .fromMetadataLocation("classpath:saml/partner-idp.xml")
            .registrationId("partner")
            .build();

        return new InMemoryRelyingPartyRegistrationRepository(
                corp, partner);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/healthz").permitAll()
                .anyRequest().authenticated())
            .saml2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

**Mục đích:** đảm bảo cùng một ứng dụng chứa **hai registration IDs duy nhất** và login SAML được bật. `fromMetadataLocation` lấy cấu hình của từng IdP, không sử dụng URL IdP mà browser tự gửi tới.

**Điều kiện để chạy:** đây là **class trong dự án Spring Boot/Security**, không phải chương trình độc lập chạy bằng `javac`. Cần module `spring-security-saml2-service-provider`, Servlet Web, metadata thực có nguồn tin cậy, IdP đã đăng ký SP, cấu hình signing/decryption nếu cần. Không có stdout cố định.

**Nếu muốn dùng cách 1 với properties** thì **không thêm bean repository ở cách 2** mà không xác định rõ nguồn cấu hình cuối cùng.

## 7. Trang chọn IdP mặc định của Spring Security

Khi SAML2 Login bật và ứng dụng chưa cấu hình custom login page, Spring Security có thể dùng `DefaultLoginPageGeneratingFilter` để tạo một trang `/login`. Khi có **nhiều IdP** và repository hỗ trợ iteration, trang này có thể liệt kê các lựa chọn SAML tương ứng với registrations.

Điều kiện cần chú ý:

1. Security filter chain có `saml2Login`.
2. Repository có các registrations và có thể duyệt được, ví dụ `InMemoryRelyingPartyRegistrationRepository`.
3. Trang đăng nhập mặc định **không bị thay** bằng cấu hình `loginPage(...)` hoặc một cơ chế login khác có quyền ưu tiên.
4. Các URL khởi tạo SAML dùng matcher phù hợp với cấu hình của phiên bản Spring Security đang sử dụng.
5. App có thể có phương thức login khác (form/OAuth2); trang mặc định có thể hiện nhiều nhóm tùy filter chain và cấu hình.

### Tại sao chỉ có một IdP không thấy trang chọn?

Nếu chỉ có một registration, Spring Security có thể điều hướng thẳng tới điểm bắt đầu AuthnRequest. Trang picker hữu ích khi có **nhiều lựa chọn**. Không nên suy đoán trang picker sẽ xuất hiện trong mọi cấu hình: hãy thử `GET /private` khi chưa xác thực và theo dõi redirects đến `/login` hoặc `/saml2/authenticate/{id}`.

### Vì sao custom repository không hiện danh sách?

`RelyingPartyRegistrationRepository` chỉ yêu cầu lookup theo registrationId. Muốn các tính năng cần enumeration (ví dụ trang picker mặc định hoặc một số metadata endpoints), repository cần hỗ trợ **`Iterable`/ `IterableRelyingPartyRegistrationRepository`** theo API version. Không nên implement `iterator()` bằng cách trả một danh sách rỗng trong khi `findByRegistrationId` vẫn tìm thấy cặp IdP—điều đó khiến trang chọn không phản ánh cấu hình đang hoạt động.

**Trang mặc định** giúp thử nhanh federation, nhưng không thay thế yêu cầu UI, ngôn ngữ, hiển thị theo tenant, branding hoặc privacy của doanh nghiệp.

## 8. Cách 3 — Trang chọn IdP tùy chỉnh, có nhãn thân thiện

Nhiều ứng dụng cần trang đăng nhập phù hợp thiết kế: nút “Đăng nhập nhân viên”, “Đăng nhập đối tác” và link trợ giúp. Cách an toàn là để **SP định nghĩa các registration IDs được phép**, sau đó render link **tới endpoint của chính SP**, không render trực tiếp URL SSO do client nhập.

### SecurityFilterChain cho custom picker

Tệp `src/main/java/com/example/security/CustomPickerSecurityConfig.java`:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CustomPickerSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/healthz", "/login/choose", "/css/**")
                .permitAll()
                .anyRequest().authenticated())
            .saml2Login(saml -> saml
                .loginPage("/login/choose"))
            .build();
    }
}
~~~

Mẫu này là **phương án thay thế SecurityFilterChain ở mục 6**. Nếu đã có một filter chain phục vụ cùng phạm vi, hãy **chỉnh filter chain đó** thay vì khai báo hai bean trùng chức năng không rõ thứ tự. `/login/choose` cần permitAll để tránh redirect loop khi người dùng chưa xác thực.

**Quan trọng:** `loginPage("/login/choose")` chỉ cho Spring Security biết **URL của trang login do ứng dụng sở hữu**. Nó không tự tạo controller/template cho URL này, cũng không thay đổi endpoint ACS.

### Controller chỉ dùng danh sách lựa chọn được phê duyệt

Tệp `src/main/java/com/example/web/IdpPickerController.java`:

~~~java
package com.example.web;

import java.util.Comparator;
import java.util.List;
import java.util.Map;

import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class IdpPickerController {

    private static final Map<String, String> LABELS = Map.of(
        "corp", "Đăng nhập nhân viên",
        "partner", "Đăng nhập đối tác"
    );

    private final RelyingPartyRegistrationRepository repository;

    public IdpPickerController(RelyingPartyRegistrationRepository repository) {
        this.repository = repository;
    }

    public record Choice(String registrationId,
                         String label,
                         String path) {}

    @GetMapping("/login/choose")
    public String show(Model model) {
        List<Choice> choices = LABELS.entrySet().stream()
            .filter(e -> repository.findByRegistrationId(e.getKey()) != null)
            .map(e -> new Choice(
                e.getKey(),
                e.getValue(),
                "/saml2/authenticate/" + e.getKey()))
            .sorted(Comparator.comparing(Choice::label))
            .toList();

        model.addAttribute("choices", choices);
        return "login-choose";
    }
}
~~~

**Vì sao kiểm tra repository?** Một label chỉ nên hiển thị nếu registration tương ứng hiện tồn tại. **Vì sao hard-code danh sách labels?** Đây là allowlist UI của ứng dụng, không lấy tên doanh nghiệp từ query/browser hay tự công khai mọi tenant đã được cấu hình.

Đoạn này thuộc **Spring MVC project**, không phải Java độc lập. Cần view engine (ví dụ Thymeleaf), dependency Spring MVC và các registrations từ phần cấu hình trước.

### Template Thymeleaf

Tệp `src/main/resources/templates/login-choose.html`:

~~~html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Chọn phương thức đăng nhập</title>
</head>
<body>
  <main>
    <h1>Đăng nhập</h1>
    <p>Chọn tổ chức xác thực phù hợp với tài khoản của bạn.</p>
    <ul>
      <li th:each="choice : ${choices}">
        <a th:href="${choice.path}"
           th:text="${choice.label}">Đăng nhập</a>
      </li>
    </ul>
    <p th:if="${#lists.isEmpty(choices)}">
      Hiện chưa có nhà cung cấp đăng nhập khả dụng.
    </p>
  </main>
</body>
</html>
~~~

Thymeleaf sẽ render URL nội bộ ví dụ `/saml2/authenticate/corp` và escape nhãn. Các link dùng **HTTP GET** để bắt đầu một luồng AuthnRequest; không phải form thu mật khẩu của IdP và không gửi `SAMLResponse` tới trang picker.

**Lưu ý khi render link:** dùng dữ liệu `Choice` từ allowlist và registration đã xác minh; tránh cung cấp trực tiếp một `href` chưa kiểm tra lấy từ `?redirect=` hoặc `?idpUrl=`, vì có thể tạo open redirect/phishing.

### Tích hợp dependencies

Một dự án Spring Boot cần tương ứng Spring Web MVC, Spring Security, `spring-security-saml2-service-provider` và (nếu dùng template trên) **`spring-boot-starter-thymeleaf`**. Phiên bản module do Spring Boot BOM quản lý; không trộn thủ công OpenSAML 4 và 5.

## 9. Với rất nhiều tenant: dùng ô nhập mã tổ chức thay vì liệt kê IdP

Một hệ thống B2B với vài nghìn tổ chức không nên công khai tất cả tên IdP trên một trang. Thay vào đó, có thể yêu cầu **mã tổ chức** hoặc dùng link trong lời mời:

~~~text
GET /login/choose
        |
   Người dùng nhập "north"
        |
        v
GET /sso/start?tenant=north
        |
        v
Tenant Discovery Service
  map "north" -> registration "corp-north"
        |
        v
Check registration exists / tenant enabled
        |
        v
Redirect nội bộ:
 /saml2/authenticate/corp-north
~~~

**Mã tenant lúc này chỉ là lời yêu cầu định tuyến**, không được tin làm proof membership. Sau callback, ứng dụng cần xác minh người dùng thực sự thuộc tenant đó từ account mapping, assertion policy và domain authorization.

### Ví dụ Controller với allowlist tenant cố định

~~~java
package com.example.web;

import java.util.Map;

import org.springframework.security.saml2.provider.service.registration.RelyingPartyRegistrationRepository;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Controller
public class TenantSsoStartController {

    private static final Map<String, String> TENANT_TO_IDP = Map.of(
        "north", "corp",
        "suppliers", "partner"
    );

    private final RelyingPartyRegistrationRepository registrations;

    public TenantSsoStartController(
            RelyingPartyRegistrationRepository registrations) {
        this.registrations = registrations;
    }

    @GetMapping("/sso/start")
    public String start(@RequestParam String tenant) {
        String registrationId = TENANT_TO_IDP.get(tenant);
        if (registrationId == null
                || registrations.findByRegistrationId(registrationId) == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return "redirect:/saml2/authenticate/" + registrationId;
    }
}
~~~

**Điều kiện dùng:** nếu bật route `/sso/start` cho người dùng chưa đăng nhập, cần `permitAll()` cho đúng endpoint đó trong `SecurityFilterChain`; nếu không, request sẽ lại bị yêu cầu login và có thể tạo vòng lặp. Bên trên là **class dự án Spring**, không phải Java standalone.

**Không được suy ra tenant membership từ `?tenant=north`**. Sau SAML Response đã xác minh, so tài khoản nội bộ, IdP issuer, subject/NameID và membership trước khi cấp quyền north. Nếu tenant không được hỗ trợ, trả lỗi có kiểm soát, không redirect sang IdP mặc định “bất kỳ” hoặc URL do client chỉ định.

### Discovery bằng domain email

Một ứng dụng có thể nhập địa chỉ email chỉ để **gợi ý** IdP, ví dụ domain công ty. Nhưng email lúc chưa xác thực là dữ liệu người dùng nhập, không chứng minh chủ sở hữu domain đó. Cần:

- Domain mapping từ cấu hình quản trị đã phê duyệt.
- Không dùng chuỗi domain tự nhập để xây URL metadata/SSO mới.
- Cân nhắc hạn chế thông báo “email này có tài khoản”, tránh account enumeration.
- Với domain chung như Gmail, không thể xác định tenant đáng tin.
- Với nhiều IdP dùng cùng domain, cần lựa chọn rõ hoặc một discovery policy khác.
- Sau callback, xác minh actual subject/issuer rồi mới cấp quyền.

Không chuyển email discovery thành “chọn IdP theo MX DNS record”, “đăng nhập vào bất kỳ IdP trả metadata ở domain đó”, hoặc tin rằng email đã nhập trước login cũng là email đã được IdP xác thực.

## 10. Java 17 độc lập: bộ chọn IdP fail-closed

Ví dụ JDK 17 dưới đây mô phỏng **chính sách routing** trước khi bắt đầu SSO. Nó không truy cập IdP hay tạo SAMLResponse. Mỗi tenant được gắn với một `registrationId` do **server quản trị**, và chỉ những ID nằm trong tập enabled mới được chọn. Một tham số cố tình đưa URL IdP trực tiếp sẽ bị từ chối.

Tạo tệp `TenantIdpSelectionDemo.java`:

~~~java
import java.util.Map;
import java.util.Set;

public class TenantIdpSelectionDemo {

    private static final Map<String, String> TENANT_IDP = Map.of(
            "north", "corp",
            "suppliers", "partner"
    );

    private static final Set<String> ENABLED = Set.of(
            "corp", "partner"
    );

    static String choose(String tenant, String directIdpUrl) {
        if (directIdpUrl != null) {
            return "REJECT: direct IdP URL not allowed";
        }

        String registrationId = TENANT_IDP.get(tenant);
        if (registrationId == null || !ENABLED.contains(registrationId)) {
            return "REJECT: no approved registration";
        }

        return "START: /saml2/authenticate/" + registrationId;
    }

    public static void main(String[] args) {
        System.out.println(choose("north", null));
        System.out.println(choose("suppliers", null));
        System.out.println(choose("unknown", null));
        System.out.println(choose(
                "north", "https://untrusted.example.test/sso"));
    }
}
~~~

Biên dịch và chạy với Java 17+:

~~~bash
javac TenantIdpSelectionDemo.java
java TenantIdpSelectionDemo
~~~

**Stdout chính xác:**

~~~text
START: /saml2/authenticate/corp
START: /saml2/authenticate/partner
REJECT: no approved registration
REJECT: direct IdP URL not allowed
~~~

Đây là **mô phỏng xác định route**, không xác minh chữ ký, không kiểm tra tenant membership, không tạo SAML AuthnRequest và không chứng minh đăng nhập. Trong production, dữ liệu map có thể đặt ở database/configuration service có kiểm soát thay vì `Map.of`; việc cập nhật mapping phải có owner, audit, tenant isolation và test. Tránh dùng `ENABLED` do browser tự gửi.

## 11. Multi-IdP và multi-tenant không hoàn toàn giống nhau

**Multi-IdP:** một SP có nhiều hệ thống xác thực được tin.

**Multi-tenant:** một ứng dụng phục vụ nhiều tổ chức và dữ liệu/entitlements phải được cách ly. Có thể có:

- **Một tenant → một IdP:** ví dụ mỗi khách hàng B2B cung cấp một IdP.
- **Một tenant → nhiều IdP:** ví dụ IdP nhân viên và IdP nhà thầu riêng, hoặc hai nguồn được phê duyệt.
- **Nhiều tenant → một IdP:** ví dụ tập đoàn dùng cùng IdP nhưng phân tách dữ liệu các công ty con.
- **Một SP → nhiều cấu hình registration cho cùng IdP issuer:** có thể vì SP entityID, ACS, tenant hoặc đối tác giao thức khác nhau.

Vì vậy:

| Giá trị vừa nhận sau login | Có xác định tenant không? |
| --- | --- |
| `registrationId` | Không nhất thiết; chỉ xác định registration |
| IdP `entityId` / Issuer | Không nhất thiết; một IdP có thể phục vụ nhiều tenant |
| User email domain | Không đủ để tin membership |
| SAML NameID | Chỉ có nghĩa trong context issuer/NameID format |
| Tenant claim | Cần kiểm chứng nguồn, scope và policy mapping |
| Tenant ID được browser chọn | Là dữ liệu yêu cầu, cần kiểm tra tại server |
| Account+tenant membership nội bộ | Có thể làm nguồn quyết định nếu đã được quản trị và còn hiệu lực |

**Thiết kế đúng:** Tạo hoặc lookup account bằng **issuer + subject identifier đáng tin + registration/tenant scope phù hợp**, rồi kiểm tra membership/role ở domain authorization. Không gắn quyền toàn cục chỉ dựa vào việc người dùng đã click một button.

## 12. Tránh rò rỉ tenant và IdP qua trang chọn

Trang login công khai dễ trở thành nguồn thông tin về khách hàng nếu không thiết kế kỹ:

- **Liệt kê toàn bộ IdP:** tiết lộ danh sách doanh nghiệp đang dùng Portal.
- **Phản hồi “tổ chức này tồn tại nhưng bị đình chỉ”:** tạo kênh enumeration.
- **Hiển thị logo/tên tùy ý từ metadata không kiểm chứng:** có thể bị lạm dụng làm giao diện giả mạo.
- **Chấp nhận `next`/returnUrl bất kỳ:** tạo open redirect tới website giả.
- **Phân biệt timing quá rõ:** có thể cho biết tenant nào có cấu hình thực.
- **Lấy domain user nhập rồi tải metadata:** gây SSRF và risk trust injection.

Cách phòng tránh:

1. Với 2–5 IdP được công bố công khai, có thể liệt kê các nhãn thân thiện bằng allowlist.
2. Với nhiều tenant bí mật, ưu tiên discovery theo mã/link đã cấp, có rate limiting và phản hồi chung khi không hợp lệ.
3. Render HTML với escaping chuẩn, hạn chế script/CSP theo nhu cầu UX.
4. Chỉ redirect **đường dẫn nội bộ cố định** `/saml2/authenticate/{approvedRegistrationId}`.
5. Nếu phải lưu nơi người dùng muốn đến sau login, chỉ lưu resource path nội bộ đã kiểm tra, không cho một domain tùy ý.
6. Giám sát các hành vi dò tenant liên tiếp, nhưng không log email hay tên tenant nhạy cảm không cần thiết.

**Tránh nhầm lẫn:** “ẩn IdP khỏi picker” chỉ là biện pháp UX/privacy; **không phải authorization**. Endpoint `/saml2/authenticate/{registrationId}` vẫn có thể được truy cập trực tiếp, nên quyền tenant phải được thực thi server-side sau khi có Authentication.

## 13. Đối chiếu registration và response khi có nhiều IdP

SAML 2.0 không cho phép SP tin một Response chỉ vì browser đi qua link của IdP A. SP phải kiểm tra **thông điệp thực sự nhận được**.

| Điều kiện | Vì sao quan trọng |
| --- | --- |
| Registration được resolve đúng | Chọn đúng IdP và SP trust material |
| Response/Assertion signature hợp lệ | Message không bị sửa và được ký bởi khóa được phép |
| Issuer phù hợp asserting party metadata | Không chấp nhận IdP B như IdP A |
| AudienceRestriction chứa SP entityID đúng | Không nhận assertion dành cho SP khác |
| Recipient/Destination khớp ACS | Không nhận Response gửi sai endpoint |
| InResponseTo tương quan với AuthnRequest khi áp dụng | Ngăn response injection/replay/login CSRF |
| SubjectConfirmation và Conditions hợp lệ | Thời hạn, recipient và điều kiện sử dụng |
| Replay protection | Một Response/Assertion không được dùng lại trái chính sách |
| Tenant membership và quyền ứng dụng | Ngăn truy cập chéo tenant dù đã được IdP xác thực |

**Phép thử bắt buộc:** Login qua `/saml2/authenticate/corp`, sau đó thử một Response ký đúng bởi IdP partner nhưng tự ghép vào bối cảnh corp. Hệ thống phải từ chối hoặc ít nhất không bao giờ tạo phiên có quyền tenant corp từ Response của partner.

Nếu SP nhận IdP-initiated SSO không có AuthnRequest đã lưu, việc chọn registration cần chính sách khác; chỉ dùng Issuer chưa kiểm chứng như một **gợi ý candidate trong tập IdP đã phê duyệt**, rồi xác minh chữ ký/issuer/recipient/audience của candidate đó. Không tự tải metadata từ URL do Response mang theo.

## 14. Hai IdP có cùng issuer hoặc dùng chung certificate

Trường hợp khó: nhiều registration có cùng IdP `entityId` nhưng khác SP `entityId`, ACS hoặc tenant. Nếu resolver chỉ nhìn Issuer của Response, **có thể không xác định duy nhất registration**. API `findUniqueByAssertingPartyEntityId` chỉ phù hợp khi thực sự có **một** registration duy nhất ứng với issuer đó; nếu nhiều cặp, phải dùng request state hoặc resolver gắn tenant/recipient được kiểm chứng.

Trường hợp certificate dùng chung giữa các tenant hoặc IdP cũng không giải quyết được bài toán lựa chọn registration. Một chữ ký hợp lệ với khóa dùng chung chưa nói message dành cho **SP entityID/tenant nào**.

Nguyên tắc:

- Gắn registrationId vào **AuthnRequest context được lưu**, không tin cookie/query từ browser nếu chưa xác minh.
- Đối chiếu Audience/Recipient và SP entityID khi xử lý Response.
- Chỉ cho phép một IdP phục vụ nhiều tenant nếu có cơ chế mapping danh tính và tenant rõ ràng.
- Tránh “nếu lookup không duy nhất thì chọn registration đầu tiên” vì thứ tự iteration không phải ranh giới tin cậy.
- Nếu cần custom `RelyingPartyRegistrationResolver` hoặc `Saml2AuthenticationTokenConverter`, tuân theo đúng API version và giữ các validator SAML mặc định.

## 15. IdP discovery và session của trình duyệt

Một số người dùng nhấn “Đăng nhập đối tác”, nhưng browser đang có IdP session của công ty. Các IdP là những hệ thống riêng; kết quả phụ thuộc việc chúng có session sẵn, có cùng federation upstream hay không và policy của từng bên.

**Các tình huống:**

1. **Chọn corp khi đã có IdP corp session:** IdP có thể xác thực im lặng qua SSO.
2. **Chọn partner khi chỉ có corp session:** Partner IdP có thể hiển thị trang login riêng; không tự lấy session corp để chứng minh danh tính partner.
3. **Đổi lựa chọn giữa chừng:** một AuthnRequest/RelayState cũ vẫn có thể còn tồn tại; phải giữ correlation và tránh xử lý Response thuộc flow khác.
4. **Đăng xuất local rồi login lại:** IdP session có thể còn, khiến người dùng quay lại mà không nhập mật khẩu.
5. **Một người có tài khoản ở hai IdP:** sau login phải xác định **issuer+subject**, không gộp account chỉ dựa email trùng.
6. **MFA/assurance khác nhau:** hai IdP có thể có policy xác thực khác; quyền nghiệp vụ nhạy cảm cần xét AuthnContext/AuthnInstant từ assertion đã xác minh nếu yêu cầu.

Picker có thể hiển thị lựa chọn lại sau logout, nhưng **không được suy luận user đã “đổi tổ chức” an toàn chỉ vì click link mới**. Khi đổi tenant/account cần làm sạch trạng thái liên quan và kiểm tra lại session/authentication.

## 16. Khi muốn tự chọn IdP dựa trên subdomain hoặc đường dẫn

Một số hệ thống triển khai:

~~~text
https://north.portal.example.test/login
https://supplier.portal.example.test/login
           |
           v
Server xác minh host/route được cấu hình
           |
       allowlist mapping
           |
           v
       registrationId
           |
           v
/saml2/authenticate/{registrationId}
~~~

Thiết kế này có thể giảm thao tác chọn, nhưng cần chú ý:

- **Host header và X-Forwarded-Host không tự đáng tin.** Chỉ tin proxy được quản lý, cấu hình forwarded headers và host allowlist.
- Subdomain wildcard không được tự sinh metadata URL IdP từ tên host client.
- Mỗi registration có thể cần SP entityID và ACS riêng; IdP phải đăng ký đúng các URL này.
- Nếu dùng reverse proxy và `{baseUrl}`, kiểm tra metadata SP thật có HTTPS public hostname đúng.
- Khi một tenant bị đình chỉ, endpoint phải trả lỗi chính sách; không redirect sang default registration.
- Cần unit/integration test IDN/Unicode domain, case sensitivity, dấu chấm cuối và các host lạ; canonicalization phải nhất quán.

**Không lấy raw `Host` nối vào `/saml2/authenticate/` hoặc IdP SSO URL.** Mọi mapping phải xuất phát từ server configuration đáng tin cậy.

## 17. Metadata SP khi có nhiều registrations

Đối với mỗi cặp SP–IdP, IdP cần biết **SP entityID, ACS URL và signing/encryption certificates nếu áp dụng**. Spring Security hỗ trợ xuất SP metadata khi bật:

~~~java
http
    .saml2Login(Customizer.withDefaults())
    .saml2Metadata(Customizer.withDefaults());
~~~

Các đường dẫn tiêu biểu:

| Đường dẫn | Vai trò |
| --- | --- |
| `/saml2/metadata` | Endpoint metadata SP tổng hợp/khả năng liệt kê tùy repository và version |
| `/saml2/metadata/corp` | SP metadata theo registration corp |
| `/saml2/metadata/partner` | SP metadata theo registration partner |
| `/saml2/service-provider-metadata/corp` | Đường dẫn metadata tương thích theo Id |

**Metadata IdP là đầu vào để SP tin IdP; SP metadata là đầu ra để IdP đăng ký SP.** Đừng tải URL metadata của SP rồi dùng làm metadata IdP khi khởi tạo registration.

Khi SP entityID/ACS khác nhau theo registration, hai IdP có thể cần hai bộ metadata SP được nhập độc lập. Khi các registrations có SP entityID chung nhưng partner policies khác nhau, vẫn phải đối chiếu từng kết nối và ràng buộc response.

### Sau proxy

Nếu app chạy nội bộ trên HTTP nhưng bên ngoài là HTTPS, `{baseUrl}` có thể sai khi forwarded headers/host validation chưa đúng. Triệu chứng là metadata chứa `http://internal-host:8080` khiến IdP gửi SAMLResponse tới sai ACS hoặc từ chối request. Chỉ cho phép forwarded headers từ reverse proxy đáng tin và đối chiếu URL công khai thực tế.

## 18. Nâng từ picker mặc định lên picker tùy chỉnh: quy trình an toàn

**Bước 1 — kiểm thử registration:** bảo đảm URL `/saml2/authenticate/{id}` làm việc cho từng IdP. Không đổi UI khi trust config còn hỏng.

**Bước 2 — bật picker mặc định:** nếu có nhiều IdP, xem Spring có hiển thị lựa chọn đúng và repository có Iterable không.

**Bước 3 — tạo trang tùy chỉnh:** thêm route `GET /login/choose`, template có nhãn thân thiện; chỉ lấy ID từ allowlist.

**Bước 4 — cấu hình loginPage:** dùng `saml2Login(saml -> saml.loginPage("/login/choose"))` trong đúng SecurityFilterChain.

**Bước 5 — permitAll cho UI:** cho phép `/login/choose` và static assets công khai, tránh redirect loop.

**Bước 6 — thử mỗi nút:** phải dẫn tới đúng AuthnRequest endpoint, đúng IdP SSO location và đúng issuer/ACS.

**Bước 7 — thử callback và state:** session/RelayState/InResponseTo giữ đúng registration, không nhận Response của IdP khác.

**Bước 8 — kiểm tra tenant authorization:** sau login, trang và API phải không cho user của tenant A xem dữ liệu tenant B.

**Bước 9 — quan sát và rollback:** có khả năng đổi về default picker mà không thay đổi trust/metadata, giữ log đã làm sạch và quản lý lỗi.

**Bước 10 — kiểm tra privacy/UX:** không rò rỉ danh sách customer IdP nếu tổ chức yêu cầu bảo mật; có thông báo khi IdP không khả dụng mà không lộ thông tin nhạy cảm.

## 19. Kiểm tra các giới hạn của trang login mặc định

Trang được Spring Security tự sinh chủ yếu nhằm **hỗ trợ một cấu hình đăng nhập tiêu chuẩn**. Không nên tự giả định nó là portal discovery có đầy đủ chức năng:

- Không đảm bảo branding/nhãn kinh doanh theo ý tổ chức.
- Không thay thế tenant lifecycle hay chính sách đóng/mở quyền SSO.
- Không tự phân biệt IdP đang bảo trì, hết hạn metadata, thiếu certificate hoặc account chưa được onboarding.
- Không tự nhận user email để tìm IdP.
- Không tự bảo vệ dữ liệu tenant khỏi enumeration.
- Không tự quản lý account linking hoặc vai trò sau login.
- Không tự chuyển IdP dự phòng khi một IdP không hoạt động.
- Không tự biến IdP selection thành authorization.
- Không đảm bảo custom repository không Iterable vẫn được liệt kê.
- Không tự đồng bộ khóa/certificate mới tại IdP khi metadata thay đổi.

**Quyết định chọn custom picker** nên dựa trên UX, privacy, số lượng IdP và chính sách tenant. Nếu chỉ có hai IdP công khai trong nội bộ, default picker có thể đủ. Nếu cung cấp dịch vụ B2B nhiều khách hàng, thường nên xây discovery riêng có kiểm soát.

## 20. An toàn khi lưu AuthnRequest, RelayState và redirect sau login

Spring Security sử dụng `Saml2AuthenticationRequestRepository` để lưu thông tin AuthnRequest khi bắt đầu SSO. Theo tài liệu, mặc định thường là `HttpSessionSaml2AuthenticationRequestRepository`, giúp gắn request với browser session.

**Lý do quan trọng:** Nếu tùy ý lookup AuthnRequest chỉ bằng `RelayState` hoặc `InResponseTo` chưa được ràng buộc với browser/session, kẻ tấn công có thể thử đưa SAMLResponse của mình cho trình duyệt khác (login CSRF/fixation). Đây là rủi ro riêng cần cân nhắc nếu thay request repository bằng distributed cache.

Khi dùng nhiều IdP:

1. Lưu request ID và registration context từ luồng đã bắt đầu.
2. Khi Response về, lấy đúng ngữ cảnh và kiểm chứng signature/issuer/bên nhận.
3. Ràng buộc relay/correlation state với một browser/session hoặc token chống giả mạo được thiết kế kỹ.
4. Đặt TTL và dùng one-time consumption, chống replay.
5. Redirect sau login chỉ đến path/URL nội bộ đã được phê duyệt; không chuyển sang domain từ query tùy ý.
6. Với nhiều request song song ở nhiều tab, kiểm thử trạng thái và cách repository xử lý request trước đó.

**Không cho phép client truyền `registrationId` trong ACS rồi lấn át registration đã được xác minh từ AuthnRequest.** Việc chọn registration khi nhận Response có thể phụ thuộc previous state, issuer và converter tùy version; chính sách phải đảm bảo không có cross-IdP login.

## 21. Cấu hình khi IdP yêu cầu ký AuthnRequest hoặc mã hóa Assertion

Mỗi IdP có thể có yêu cầu khác nhau:

| Thông số | Corp | Partner |
| --- | --- | --- |
| IdP SSO binding | Redirect | POST |
| Có bắt buộc signed AuthnRequest? | Có | Không |
| Có gửi encrypted assertion? | Có thể | Có thể |
| Verification certificate | Cert corp | Cert partner |
| SP signing credential | Cần theo yêu cầu corp | Có thể không cần |
| SP decryption credential | Cần nếu assertion bị mã hóa | Cần nếu assertion bị mã hóa |
| SP entityID/ACS | Theo registration corp | Theo registration partner |

Do đó, **không nên sao chép nguyên mọi thuộc tính của registration corp sang partner**. Với builder thủ công cần định nghĩa `assertingPartyMetadata` của đúng IdP, SSO location, bindings, verification credentials; và SP signing/decryption credentials khi cần.

**Không nhầm:** Certificate dùng xác minh IdP Response là **public certificate IdP**. Private key SP để ký AuthnRequest và giải mã assertion là hai vai trò khác; không đưa private key vào picker page, metadata công khai hoặc logs.

Trong giai đoạn key rotation, một IdP có thể có nhiều verification credentials thuộc cùng issuer; điều đó không cho phép dùng certificate của IdP partner để xác minh Response của corp.

## 22. Xử lý sự cố IdP không sẵn sàng trong trang chọn

Một nút IdP có thể dẫn đến lỗi do SSO endpoint ngừng hoạt động, metadata hết hiệu lực, chứng thư thay đổi hoặc cấu hình callback không khớp. Nên phân biệt:

- **Metadata retrieval failure:** SP không nạp/cập nhật registration đáng tin.
- **SSO endpoint outage:** IdP đăng nhập mới không hoạt động dù metadata còn hợp lệ.
- **Signature validation error:** Certificate/issuer không khớp; không được bỏ kiểm tra để tiếp tục.
- **ACS mismatch:** IdP không gửi Response về đúng URL.
- **Authorization 403:** SAML authentication thành công nhưng tài khoản không có quyền tenant.
- **Tenant disabled:** SP không được phép khởi tạo hoặc chấp nhận phiên cho tenant đang bị đình chỉ.

UI nên báo **“Không thể đăng nhập bằng nhà cung cấp này lúc này”** và cho phép quay lại picker, không tiết lộ raw SAML assertion, certificate, NameID hoặc stack trace. Nếu có IdP dự phòng, chỉ hiển thị nó khi mối quan hệ trust/account mapping và chính sách bảo đảm danh tính đã được phê duyệt; **không tự failover từ corp sang partner**.

Cần cảnh báo khi một registration bị hỏng metadata, signature failures tăng, tenant mapping thiếu hoặc có nhiều lần truy cập các ID không hợp lệ. Rate limit các route discovery để tránh dò danh sách tenant.

## 23. Ma trận kiểm thử multi-IdP và tenant

| Test | Thao tác | Kết quả kỳ vọng |
| --- | --- | --- |
| 01 | Chỉ có corp registration | AuthnRequest corp chạy; picker có thể không hiện |
| 02 | Có corp và partner, repository Iterable | Trang mặc định có thể liệt kê hai lựa chọn |
| 03 | Chọn corp | Redirect/POST tới IdP corp theo registration |
| 04 | Chọn partner | Redirect/POST tới IdP partner theo registration |
| 05 | Đổi sang custom loginPage | Hiển thị route/view mới, không còn dùng generated page theo cấu hình |
| 06 | Mở `/login/choose` khi chưa login | Không bị redirect loop/403 do thiếu permitAll |
| 07 | Request `/sso/start?tenant=north` | Đi tới registration corp theo server allowlist |
| 08 | Tenant không tồn tại | Không chọn default IdP tùy ý; lỗi có kiểm soát |
| 09 | Query chứa `idpUrl` ngoài allowlist | Không dùng URL đó làm destination |
| 10 | URL returnUrl bên ngoài | Không redirect tới domain không được tin |
| 11 | Response ký bởi IdP B sau khi bắt đầu corp | Bị từ chối hoặc không cấp quyền corp |
| 12 | Issuer đúng nhưng Audience sai | Bị từ chối |
| 13 | InResponseTo không khớp | Bị từ chối trong SP-initiated flow |
| 14 | Hai registrations cùng IdP issuer | Resolver không chọn tùy tiện theo thứ tự |
| 15 | Một user có email trùng ở hai IdP | Không gộp account sai nếu chưa có linking policy |
| 16 | Account thuộc tenant north nhưng chọn suppliers | Không cấp quyền suppliers nếu không có membership |
| 17 | Một IdP rotation certificate | Chỉ registration đúng nhận keys mới được phê duyệt |
| 18 | IdP corp down, partner bình thường | Chỉ corp lỗi; không chuyển account sang partner tự động |
| 19 | Sau reverse proxy | ACS/Entity ID đúng HTTPS external origin |
| 20 | Trang có nhiều tenant bí mật | Không rò danh sách IdP nếu privacy policy cấm |
| 21 | User mở hai login flows ở hai tab | Request correlation không bị tráo/nhầm session |
| 22 | Sau login gọi API tenant khác | Domain authorization từ chối |
| 23 | IdP-initiated Response không có request state | Chỉ chấp nhận khi có policy riêng và validation đầy đủ |
| 24 | Custom repository không Iterable | Kiểm tra picker custom/listing không dựa vào enumeration thiếu |
| 25 | Metadata SP của corp và partner | IdP đã đăng ký đúng Entity ID/ACS/certificate |

Các test end-to-end phải chạy với **IdP thử nghiệm hoặc IdP thực**, certificate/metadata đáng tin. Unit test cho picker/mapping chỉ chứng minh routing logic, không chứng minh Spring đã xác minh SAMLResponse đúng.

## 24. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Trang login không liệt kê IdP nào | Repository không Iterable, chỉ một registration, hoặc custom login page đang bật | Kiểm tra cấu hình hợp đồng enumeration và URL login |
| Click nút corp ra 404 | Sai registrationId hoặc route initiation bị đổi | Kiểm tra URL `/saml2/authenticate/corp` và matcher |
| Login trả 500 khi khởi tạo registration | Metadata IdP lỗi hoặc nguồn không truy cập được | Xác minh source/validity, không tin metadata giả |
| Browser bị redirect liên tục `/login/choose` | Picker route chưa permitAll | Mở đúng GET picker và assets theo policy |
| User chọn đúng IdP nhưng Response signature invalid | Key IdP sai, rotation chưa đồng bộ | Kiểm tra certificate chỉ của IdP đó |
| IdP báo unknown SP | SP Entity ID chưa được đăng ký/không khớp | So SP metadata và IdP config |
| IdP redirect về ACS sai | URL proxy/ACS hoặc registration không đồng bộ | Đồng bộ external origin, metadata và loginProcessingUrl |
| Chọn tenant A nhưng vào dữ liệu tenant B | Domain authorization dùng hint thay membership | Kiểm tra tenant server-side và resource scope |
| Người dùng không có lựa chọn phù hợp | IdP của tenant chưa onboarding hoặc bị disable | Xử lý trạng thái riêng, không tạo IdP tự động |
| Cùng issuer khiến resolve lẫn registration | Nhiều cặp SP–IdP cùng Issuer | Dùng request state/recipient/audience tin cậy |
| SSO nhanh mà không hỏi mật khẩu sau chọn lại | IdP session đã tồn tại | Giải thích SSO reuse; dùng fresh auth khi policy yêu cầu |
| User login được nhưng nhận 403 | Quyền nghiệp vụ thiếu | Kiểm tra role, tenant membership, account status |
| Trang picker rò tên khách hàng | Liệt kê toàn bộ dynamic registrations | Đổi sang discovery có kiểm soát, privacy review |
| Đưa URL IdP qua query làm chuyển hướng lạ | Open redirect hoặc trust injection | Thay bằng server allowlist `registrationId` |

**Tránh sửa lỗi bằng cách** tắt chữ ký SAML, bỏ qua issuer/audience/recipient, chọn registration đầu tiên khi không chắc, hoặc cấp quyền tenant vì user đã chọn đúng nút.

## 25. Checklist trước khi triển khai production

- [ ] Có danh sách IdP được quản trị phê duyệt, mỗi cặp SP–IdP có registrationId duy nhất và ổn định.
- [ ] Mỗi registration dùng metadata IdP, entityID, SSO endpoint, verification credentials và bindings đúng đối tác.
- [ ] Có SP signing/decryption credentials nếu giao thức hoặc IdP yêu cầu.
- [ ] Phân biệt rõ `registrationId`, IdP entityID, SP entityID và tenant ID.
- [ ] Repository hỗ trợ Iterable khi cần picker mặc định hoặc metadata tổng hợp.
- [ ] Custom picker sử dụng allowlist tên hiển thị và chỉ trỏ tới các đường dẫn khởi tạo SP được phê duyệt.
- [ ] Custom `loginPage` có controller/view, permitAll và không trùng filter chain.
- [ ] Nếu có discovery tenant/email/subdomain, ánh xạ phải xuất phát từ server configuration tin cậy.
- [ ] Không tự tải metadata hay build SSO URL từ browser/query/Host header chưa xác minh.
- [ ] Đã đăng ký SP metadata Entity ID/ACS/certificate đúng ở từng IdP.
- [ ] Đã thử AuthnRequest/Response, signature, issuer, audience, recipient, InResponseTo và replay protection cho từng IdP.
- [ ] Sau authentication, xác minh account linking bằng issuer+subject và tenant membership bằng dữ liệu được phép.
- [ ] Domain authorization thực thi role/tenant/resource policy độc lập với picker.
- [ ] Không tiết lộ danh sách IdP/tenant bí mật hoặc gây user enumeration.
- [ ] Có handling khi IdP down, metadata hết hạn, rotation hoặc tenant disabled.
- [ ] Có test multi-tab/login flows song song, proxy public URL và session state.
- [ ] Đã xác định điểm nâng cấp Spring Security 6.x/7.x liên quan login page, resolver và metadata.
- [ ] Có log được làm sạch, audit thay đổi registration, tenant mapping và quyền truy cập.

## 26. Kết luận

**Đăng ký nhiều IdP trong Spring Security là cấu hình nhiều `RelyingPartyRegistration` trong một repository và để người dùng khởi tạo AuthnRequest theo `registrationId` thích hợp.** Với số ít IdP, `InMemoryRelyingPartyRegistrationRepository` kết hợp trang login mặc định có thể là giải pháp đơn giản. Khi cần thương hiệu, privacy hoặc discovery theo tenant, hãy tạo **custom picker** và mapping **allowlist phía server**.

Dù người dùng chọn IdP nào, SP chỉ được tạo phiên sau khi SAML Response đã được xác minh với **đúng issuer, khóa và recipient/audience**, sau đó phải kiểm tra tài khoản nội bộ, tenant membership và quyền nghiệp vụ. **Một nút đăng nhập không phải biên giới bảo mật**: mọi IdP selection, state/correlation, account linking và authorization phải được xác định ở server.

### Tài liệu tham khảo chính thức

- Spring Security — SAML 2.0 Login Overview, cấu hình nhiều IdP và login picker: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Security — SAML2 Authentication Requests: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication-requests.html
- Spring Security — Authenticating SAML Responses: https://docs.spring.io/spring-security/reference/servlet/saml2/login/authentication.html
- Spring Security — SAML2 Metadata: https://docs.spring.io/spring-security/reference/servlet/saml2/metadata.html
- Spring Security Javadoc — InMemoryRelyingPartyRegistrationRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/InMemoryRelyingPartyRegistrationRepository.html
- Spring Security Javadoc — IterableRelyingPartyRegistrationRepository: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/saml2/provider/service/registration/IterableRelyingPartyRegistrationRepository.html
- Spring Security Javadoc — Saml2LoginConfigurer: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/saml2/Saml2LoginConfigurer.html
- OASIS — SAML 2.0 Profiles (Web Browser SSO): https://docs.oasis-open.org/security/saml/v2.0/saml-profiles-2.0-os.pdf
