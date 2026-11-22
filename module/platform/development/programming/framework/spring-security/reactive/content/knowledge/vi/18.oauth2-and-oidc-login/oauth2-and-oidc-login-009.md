# Tùy chỉnh ReactiveOAuth2UserService và ánh xạ claim thành quyền trong Spring Security reactive

## 1. Mục tiêu

Trong ứng dụng **Spring WebFlux**, người dùng có thể đăng nhập qua hệ thống danh tính doanh nghiệp bằng **OAuth2 Login/OpenID Connect (OIDC)**. IdP cung cấp danh tính và các thuộc tính như `sub`, `email`, `groups` hoặc một claim riêng `app_roles`. Nhưng Spring Security không thể tự suy ra rằng một chuỗi `"admin"` trong claim tùy biến tương đương với `ROLE_ADMIN` của ứng dụng. Bạn cần **ánh xạ dữ liệu danh tính đáng tin thành GrantedAuthority** trước khi Spring Security ra quyết định phân quyền.

Bài học này hướng dẫn cách chọn và tùy chỉnh `ReactiveOAuth2UserService` trong **Spring Security reactive**, giữ nguyên xác minh OIDC của framework và tạo quyền có kiểm soát. Bạn sẽ:

1. Phân biệt OAuth2 Login, OIDC Login và OAuth2 Resource Server JWT.
2. Hiểu hợp đồng `ReactiveOAuth2UserService<R,U>.loadUser(...)` và vai trò của `DefaultReactiveOAuth2UserService`, `OidcReactiveOAuth2UserService`.
3. Chọn `GrantedAuthoritiesMapper` hoặc custom user service tùy có cần I/O reactive hay không.
4. Map claim `app_roles` từ **ID Token do trusted IdP phát hành** qua allowlist thành `ROLE_USER`, `ROLE_ADMIN`, `REPORT_VIEW`.
5. Giữ `OidcIdToken`, `OidcUserInfo`, danh tính principal và các authorities mặc định khi tạo `DefaultOidcUser`.
6. Tạo ứng dụng Spring Boot 4.1.x/Java 17+ có WebFlux OAuth2 Login, trong đó role thực sự được dùng bởi `hasRole` và `hasAuthority`.
7. Chạy chương trình Java 17 thuần để kiểm thử mapping **không cần IdP**, sau đó chạy login end-to-end khi đã provision IdP thật.
8. Test thiếu/sai claim, unknown role, multiple issuer, quyền thay đổi sau login, callback và session.

**Tư tưởng bảo mật:** role không được lấy từ request header, query parameter hay một field client tùy ý thay đổi. Role có quyền lực cao phải đến từ **nguồn đã xác minh issuer/tenant/client và có hợp đồng ngữ nghĩa rõ ràng**.

## 2. Luồng OAuth2/OIDC Login và điểm gắn user service

~~~text
Browser                         Spring WebFlux                          IdP
   |                                 |                                    |
   | GET /reports                    |                                    |
   |-------------------------------->|                                    |
   | anonymous -> redirect login     |                                    |
   |<--------------------------------|                                    |
   | GET /oauth2/authorization/corp   |                                    |
   |-------------------------------->|  Authorization Request + state     |
   |                                 |----------------------------------->|
   |                                 |           IdP authenticates user   |
   |                                 |<-----------------------------------|
   | GET /login/oauth2/code/corp?... |                                    |
   |-------------------------------->|  Exchange code for tokens         |
   |                                 |----------------------------------->|
   |                                 |<-- access token / ID Token --------|
   |                                 | OIDC token validation               |
   |                                 | OidcReactiveOAuth2UserService      |
   |                                 | custom role mapping                 |
   |                                 | OAuth2AuthenticationToken          |
   |                                 | WebSession SecurityContext         |
   | GET /reports + session cookie    |                                    |
   |-------------------------------->| hasAuthority("REPORT_VIEW")        |
   |<--------------------------------| 200 or 403                         |
~~~

Đây là sơ đồ khái niệm, không thay thế protocol trace. Spring Security còn xử lý `state`, redirect URI, nonce, PKCE khi thích hợp, token exchange, UserInfo và validation. Không tự parse ID Token nhận qua browser hoặc tự viết callback controller chỉ để map role.

### 2.1. Những thành phần dễ nhầm

| Khái niệm | Vai trò |
| --- | --- |
| `OAuth2AccessToken` | Access token được cấp cho client để gọi protected resource; **không tự tương đương role** |
| `OidcIdToken` | JWT chứa thông tin xác thực/claim của user và được OIDC client kiểm chứng |
| `OidcUserInfo` | Claim lấy từ protected UserInfo endpoint, có thể vắng mặt |
| `OAuth2User` | Principal OAuth2 có attributes/authorities |
| `OidcUser` | OAuth2User có thêm ID Token/UserInfo OIDC |
| `GrantedAuthority` | Quyền dùng ở policy Spring Security, ví dụ `ROLE_ADMIN` |
| `OAuth2AuthenticationToken` | Authentication của OAuth2 Login với final authorities |
| `JwtAuthenticationToken` | Authentication của **Resource Server** sau khi xác thực Bearer JWT; là cơ chế khác |

**Điều kiện quan trọng:** một ứng dụng API chỉ nhận `Authorization: Bearer <token>` thường dùng `oauth2ResourceServer().jwt(...)` và JWT authorities converter. `ReactiveOAuth2UserService` của **OAuth2 Client Login** không tự được gọi khi resource server xác minh access token của API.

### 2.2. Vai trò AuthorizationManager

Sau khi `OAuth2AuthenticationToken` được tạo, authorization layer trong `SecurityWebFilterChain` hoặc method-security sẽ kiểm tra authorities. Ví dụ `hasRole("ADMIN")` kiểm `ROLE_ADMIN` theo role prefix mặc định; `hasAuthority("REPORT_VIEW")` yêu cầu chính xác authority `REPORT_VIEW`. Mapping claim vào authorities **không** tự sửa dữ liệu IdP hay nội dung token.

## 3. ReactiveOAuth2UserService: contract và delegate

Javadoc định nghĩa interface:

~~~java
@FunctionalInterface
public interface ReactiveOAuth2UserService<
        R extends OAuth2UserRequest, U extends OAuth2User> {

    Mono<U> loadUser(R userRequest)
            throws OAuth2AuthenticationException;
}
~~~

Đây là **chữ ký rút gọn** nhằm giảng giải, không phải code phải tự khai báo lại. `R` chứa thông tin về client registration và access token; `U` là OAuth2/OIDC principal. Publisher `Mono<U>` cho phép gọi UserInfo hoặc một API phụ bằng `WebClient` không block event loop.

| Kiểu login | UserService type | Delegate Spring Security |
| --- | --- | --- |
| OAuth2 provider **không OIDC** | `ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>` | `DefaultReactiveOAuth2UserService` |
| OIDC provider có scope `openid` | `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` | `OidcReactiveOAuth2UserService` |

`DefaultReactiveOAuth2UserService` sử dụng access token gọi UserInfo qua `WebClient`. Với provider không OIDC, thường phải biết `user-name-attribute` từ UserInfo response. `OidcReactiveOAuth2UserService` tích hợp OIDC ID Token và UserInfo; `OidcUser.getUserInfo()` có thể trả `null`. Đừng tự thay OIDC user service bằng generic OAuth2 user service rồi đánh mất ID Token/principal semantics.

### 3.1. Đúng extension point trong Spring Security 7.1

Ở **Spring Security 7.1 WebFlux**, có thể khai báo **`@Bean ReactiveOAuth2UserService<OidcUserRequest, OidcUser>`** và giữ `.oauth2Login(Customizer.withDefaults())`. Spring Security tìm implementation theo kiểu generic.

Điểm dễ sai là copy ví dụ Servlet:

~~~java
// Chỉ để nhận diện khác biệt API; KHÔNG dùng cho WebFlux:
http.oauth2Login(oauth2 -> oauth2
        .userInfoEndpoint(userInfo ->
                userInfo.oidcUserService(oidcUserService)));
~~~

Trong Javadoc reactive `ServerHttpSecurity.OAuth2LoginSpec` của phiên bản 7.1, **không có method `userInfoEndpoint(...)`** như Servlet DSL. Với WebFlux hãy dùng user-service bean hoặc `GrantedAuthoritiesMapper` như tài liệu reactive. Trong dự án Spring Security 6.5, cũng cần đối chiếu đúng API đang resolve thay vì dùng Servlet snippet.

### 3.2. Khi nào loadUser được gọi?

Nó nằm trong quá trình OAuth2/OIDC Login, **không phải mỗi HTTP request** của người dùng đã có session. Authentication sau khi login thường được giữ trong `WebSession`. Vì thế **role thay đổi ở IdP sau login** chưa chắc phản ánh ngay trong authorities của session hiện tại.

### 3.3. Mono và xử lý lỗi

Trong `loadUser`, nên dùng `delegate.loadUser(request).map(...)` hoặc `flatMap(...)` khi cần I/O thêm. Không dùng `block()` trên Netty event loop, không tự `subscribe()` rồi trả principal trước khi API role hoàn tất. Khi IdP/API roles lỗi, **không fallback thành admin**; định nghĩa rõ chính sách fail closed hoặc reject login.

## 4. Claims, scopes và role không đồng nghĩa

OIDC có các claim nhận dạng phổ biến như `iss`, `aud`, `sub`, `name`, `email`, `email_verified`. **Không có claim role chung bắt buộc mà mọi provider phải gửi**. Một IdP doanh nghiệp có thể có:

~~~json
{
  "iss": "https://login.corp.example/realms/employees",
  "aud": "web-dashboard",
  "sub": "employee-123",
  "email": "reader@corp.example",
  "app_roles": ["viewer", "report_reader"]
}
~~~

Đây là **ví dụ payload**, không phải token thật. `app_roles` phải được team IdP cấu hình rõ và phát trong **ID Token** nếu code đọc ID Token. Một số provider chỉ đặt group trong UserInfo hoặc một protected roles API. Nếu dùng nested claim như `realm_access.roles`, không thể đọc thẳng bằng `claims.get("app_roles")`.

### 4.1. So sánh authorities

| Dữ liệu | Policy ví dụ | Nhận xét |
| --- | --- | --- |
| `ROLE_USER` | `hasRole("USER")` | Rule role, prefix `ROLE_` mặc định |
| `ROLE_ADMIN` | `hasRole("ADMIN")` | Role admin ứng dụng |
| `REPORT_VIEW` | `hasAuthority("REPORT_VIEW")` | App-specific authority |
| `SCOPE_profile` | `hasAuthority("SCOPE_profile")` | Authority từ OAuth2 scope, nếu có |
| `OIDC_USER` | Thể hiện principal loại OIDC | **Không phải admin** |
| `OAUTH2_USER` | Thể hiện principal OAuth2 | **Không phải admin** |
| `SCOPE_openid` | Một scope OAuth2/OIDC | **Không tự cấp role** |

Việc người dùng được cấp scope `openid profile email` không có nghĩa là được làm admin, xem báo cáo hay quản lý user. Những quyền ứng dụng cần mapping riêng.

### 4.2. Map theo allowlist

Bài sử dụng một bảng ánh xạ cụ thể:

| Giá trị `app_roles` | GrantedAuthority |
| --- | --- |
| `"viewer"` | `ROLE_USER` |
| `"admin"` | `ROLE_ADMIN` |
| `"report_reader"` | `REPORT_VIEW` |
| `"super_admin"` hoặc role chưa định nghĩa | Không cấp authority |
| Claim thiếu/null/sai kiểu | Không cấp app authority |
| Item là số, object, boolean | Bỏ qua item sai kiểu |

Không biến mọi string bằng `"ROLE_" + claim`. Với yêu cầu cao, role không chuẩn định dạng có thể **làm login thất bại** thay vì bỏ qua; bài chọn mô hình **không cấp quyền nhạy cảm** nếu dữ liệu sai. Dù dùng cách nào, **không** cấp quyền mặc định cao hơn khi nguồn role lỗi.

## 5. Chuỗi tin cậy trước khi cấp quyền

Một claim trong ID Token chỉ phù hợp để ra quyết định role nếu:

1. Client registration trỏ tới **IdP được phép phát quyền ứng dụng**.
2. Spring Security đã xác minh ID Token: signature, issuer, audience, expiry và các điều kiện OIDC thích hợp.
3. Claim role được IdP **gán phía server**, không phải trường user có thể tự sửa.
4. Role được cấp cho **đúng client/tenant**; IdP có thể phát realm roles cho ứng dụng khác, không tự trộn namespace.
5. Ánh xạ chỉ qua allowlist đã review, không tự suy quyền từ tên nhóm gần giống.
6. Tài khoản nội bộ được liên kết bằng khóa bền vững như `issuer + subject`, không chỉ email.
7. Hệ thống có chiến lược thu hồi quyền sau khi user đã login.

### 5.1. Anti-pattern dễ tạo lỗ hổng

~~~java
// Sai: tin header do client tự gửi.
String role = exchange.getRequest()
        .getHeaders().getFirst("X-Role");
new SimpleGrantedAuthority("ROLE_" + role);

// Sai: tin mọi string trong token sẽ là app role an toàn.
String input = (String) claims.get("role");
new SimpleGrantedAuthority(
        "ROLE_" + input.toUpperCase());

// Sai: email domain không đủ để cấp admin.
if (email.endsWith("@corp.example")) {
    authorities.add(new SimpleGrantedAuthority("ROLE_ADMIN"));
}
~~~

Đây là **các snippet nguy hiểm để nhận diện**, không dùng trong chương trình thật. Chữ ký ID Token bảo vệ tính toàn vẹn của claim, nhưng **không tự đảm bảo ngữ nghĩa** rằng claim đó là quyền admin cho ứng dụng của bạn.

## 6. Chọn GrantedAuthoritiesMapper hay user service

| Tiêu chí | `GrantedAuthoritiesMapper` | `ReactiveOAuth2UserService` |
| --- | --- | --- |
| Chỉ cần đọc claim có sẵn | Phù hợp | Phù hợp |
| Cần truy cập `OidcIdToken`/`OidcUserInfo` | Qua `OidcUserAuthority` | Qua `OidcUser` của delegate |
| Cần HTTP call protected roles API | Không phù hợp (mapper đồng bộ) | Phù hợp bằng `WebClient` reactive |
| Cần thay principal name/attributes | Không phải mục tiêu chính | Có thể tái tạo principal |
| Gắn vào WebFlux | Bean `GrantedAuthoritiesMapper` | Bean `ReactiveOAuth2UserService<...>` |
| Dễ test policy thuần | Có | Có; nên tách mapper thuần |
| Rủi ro | Bỏ mất authorities mặc định | Làm mất ID Token/UserInfo/flow mặc định |

**Nếu chỉ cần đổi claim đã có thành authorities, dùng GrantedAuthoritiesMapper thường đơn giản hơn.** Nếu cần delegate tùy chỉnh, lấy thêm dữ liệu bằng access token hoặc thay principal, user service phù hợp hơn.

### 6.1. Ví dụ GrantedAuthoritiesMapper

~~~java
@Bean
GrantedAuthoritiesMapper authoritiesMapper() {
    return incoming -> {
        Set<GrantedAuthority> result =
                new LinkedHashSet<>(incoming);

        for (GrantedAuthority authority : incoming) {
            if (authority instanceof OidcUserAuthority oidc) {
                Object claim = oidc.getIdToken()
                        .getClaims().get("app_roles");
                for (String granted :
                        ClaimRolePolicy.mapProviderRoles(claim)) {
                    result.add(new SimpleGrantedAuthority(granted));
                }
            }
        }
        return result;
    };
}
~~~

Đây là **method snippet** trong Spring configuration; cần import `GrantedAuthoritiesMapper`, `OidcUserAuthority`, `GrantedAuthority`, `SimpleGrantedAuthority`, `Set` và `LinkedHashSet`. Nó dùng utility ở phần 7.

**Lưu ý:** mapper này không có trực tiếp `ClientRegistration` để kiểm registrationId như user service. Nếu ứng dụng hỗ trợ nhiều IdP, **chưa đủ** để quyết định claim của issuer nào được tin. Cần thiết kế policy phân biệt provider/issuer hoặc dùng custom user service có request context rõ ràng.

Trong ví dụ tích hợp chính bên dưới, chúng ta **không đăng ký mapper bean này**, để tránh map hai lần và tránh nhầm final authorities.

## 7. Dự án WebFlux Java 17+ với role claim tùy chỉnh

Ứng dụng sử dụng Spring Boot 4.1.2, **Spring Reactive Web**, **Spring Security** và **OAuth2 Client**. Có hai phần kiểm thử:

- **Pure Java role mapping** chạy độc lập bằng `javac`, không cần mạng/IdP.
- **Spring WebFlux OAuth2/OIDC Login** chỉ hoàn tất login end-to-end khi bạn cung cấp IdP/ClientRegistration thật.

### 7.1. pom.xml

Tạo project Maven, group `com.example`, artifact `reactive-oidc-roles`, Java 17+.

**Spring Boot 4** đổi tên OAuth2 Client starter thành `spring-boot-starter-security-oauth2-client`; starter tên cũ `spring-boot-starter-oauth2-client` được giữ tương thích nhưng đã đổi tên/deprecated. `pom.xml` đầy đủ:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>reactive-oidc-roles</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Để Spring Boot BOM quản lý phiên bản Spring Security, Framework, Reactor tương thích. Không thêm `spring-boot-starter-web` của Servlet. `oauth2-client` khác `oauth2-resource-server`; cái sau dành cho API Bearer/JWT.

### 7.2. application.properties

Tạo `src/main/resources/application.properties`:

~~~properties
server.port=8080

spring.security.oauth2.client.registration.corp.provider=corp
spring.security.oauth2.client.registration.corp.client-id=${CORP_CLIENT_ID}
spring.security.oauth2.client.registration.corp.client-secret=${CORP_CLIENT_SECRET}
spring.security.oauth2.client.registration.corp.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.corp.scope=openid,profile,email
spring.security.oauth2.client.registration.corp.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}

spring.security.oauth2.client.provider.corp.issuer-uri=${CORP_OIDC_ISSUER_URI}
~~~

Khi bài được lưu, các ký hiệu `${...}` trong đoạn mã trên được chuyển thành cú pháp **Spring Property Placeholder `$...`**; ứng dụng dùng biến môi trường `CORP_CLIENT_ID`, `CORP_CLIENT_SECRET` và `CORP_OIDC_ISSUER_URI`.

**Để chạy login thực**, phải provision một IdP hỗ trợ OIDC discovery qua HTTPS, cấp Client ID/Secret và đăng ký callback `http://localhost:8080/login/oauth2/code/corp` cho **local dev**. Môi trường production cần HTTPS và redirect URI public thật, không commit client secret vào Git. Spring Boot có thể cần truy vấn OIDC discovery khi startup; issuer không khả dụng sẽ làm startup/login fail, không phải lỗi mapping.

**Quan trọng:** IdP phải được cấu hình **phát `app_roles` trong ID Token** cho client `corp`. Bài này không giả định một provider công khai tự phát claim đó.

### 7.3. ClaimRolePolicy.java — chạy độc lập bằng JDK 17

Tạo file `src/main/java/com/example/oidcroles/ClaimRolePolicy.java`:

~~~java
package com.example.oidcroles;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public final class ClaimRolePolicy {

    private ClaimRolePolicy() {
    }

    public static Set<String> mapProviderRoles(Object claim) {
        if (!(claim instanceof Collection<?> values)) {
            return Set.of();
        }

        Set<String> result = new LinkedHashSet<>();
        for (Object item : values) {
            if (!(item instanceof String role)) {
                continue;
            }
            switch (role) {
                case "viewer" -> result.add("ROLE_USER");
                case "admin" -> result.add("ROLE_ADMIN");
                case "report_reader" -> result.add("REPORT_VIEW");
                default -> {
                    // Unknown role cannot create app privileges.
                }
            }
        }
        return Set.copyOf(result);
    }

    public static void main(String[] args) {
        Set<String> allowed = mapProviderRoles(List.of(
                "viewer", "admin", "report_reader", "super_admin"));

        System.out.println("allowed=" +
                String.join(",", new TreeSet<>(allowed)));

        System.out.println("unknown=" +
                mapProviderRoles(List.of("super_admin")).size());

        System.out.println("wrong_type=" +
                mapProviderRoles("admin").size());
    }
}
~~~

Chương trình này **chỉ dùng Java standard library**, không cần Spring hay IdP. Tên file, package và class thống nhất. Nó:

- Chỉ xử lý claim dạng collection; claim `"admin"` kiểu scalar không được map.
- Chỉ chấp nhận String đã có trong allowlist; `super_admin` không được map.
- Không tự nối `ROLE_` vào chuỗi user input.
- Bỏ qua item sai kiểu, không nâng quyền.
- Trả immutable Set; thứ tự được xử lý khi in bằng `TreeSet`.

Chạy bằng JDK 17 tại thư mục project:

~~~bash
mkdir -p out
javac -d out src/main/java/com/example/oidcroles/ClaimRolePolicy.java
java -cp out com.example.oidcroles.ClaimRolePolicy
~~~

Windows PowerShell: tạo thư mục bằng `New-Item -ItemType Directory -Force out`, rồi chạy `javac` và `java` tương tự. **Stdout xác định theo code**:

~~~text
allowed=REPORT_VIEW,ROLE_ADMIN,ROLE_USER
unknown=0
wrong_type=0
~~~

Đây là **kiểm thử policy allowlist**, chưa phải kiểm thử signature của một ID Token thật.

### 7.4. OidcRolesApplication.java — WebFlux OAuth2 Login

Tạo `src/main/java/com/example/oidcroles/OidcRolesApplication.java`:

~~~java
package com.example.oidcroles;

import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcReactiveOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.userinfo.ReactiveOAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class OidcRolesApplication {

    public static void main(String[] args) {
        SpringApplication.run(OidcRolesApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/").permitAll()
                        .pathMatchers("/admin").hasRole("ADMIN")
                        .pathMatchers("/reports")
                                .hasAuthority("REPORT_VIEW")
                        .anyExchange().authenticated())
                .httpBasic(basic -> basic.disable())
                .formLogin(form -> form.disable())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }

    @Bean
    ReactiveOAuth2UserService<OidcUserRequest, OidcUser>
            oidcUserService() {

        OidcReactiveOAuth2UserService delegate =
                new OidcReactiveOAuth2UserService();

        return request -> delegate.loadUser(request).map(user -> {
            Set<GrantedAuthority> mapped =
                    new LinkedHashSet<>(user.getAuthorities());

            // Only this trusted client registration grants app roles.
            if ("corp".equals(
                    request.getClientRegistration().getRegistrationId())) {

                Object claim = user.getIdToken().getClaims()
                        .get("app_roles");

                for (String role :
                        ClaimRolePolicy.mapProviderRoles(claim)) {
                    mapped.add(new SimpleGrantedAuthority(role));
                }
            }

            // Preserve ID Token, UserInfo, default authorities.
            // Default name uses the OIDC subject (sub).
            return new DefaultOidcUser(
                    mapped, user.getIdToken(), user.getUserInfo());
        });
    }

    @RestController
    static class DemoController {

        @GetMapping(value = "/",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> index() {
            return Mono.just(
                    "Open /oauth2/authorization/corp to sign in");
        }

        @GetMapping("/me")
        Mono<Map<String, Object>> me(
                @AuthenticationPrincipal OidcUser user) {
            return Mono.just(Map.of(
                    "subject", user.getSubject(),
                    "authorities", user.getAuthorities().stream()
                            .map(GrantedAuthority::getAuthority)
                            .sorted()
                            .toList()));
        }

        @GetMapping(value = "/admin",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> admin() {
            return Mono.just("ADMIN_OK");
        }

        @GetMapping(value = "/reports",
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> reports() {
            return Mono.just("REPORT_OK");
        }
    }
}
~~~

**Giải thích các quyết định:**

1. `ReactiveOAuth2UserService<OidcUserRequest, OidcUser>` được đăng ký dưới dạng bean, phù hợp Spring Security WebFlux 7.1.
2. `OidcReactiveOAuth2UserService` chuẩn vẫn thực hiện UserInfo/OIDC logic; không tự bỏ cơ chế validation mặc định.
3. `delegate.loadUser(...).map(...)` là thao tác reactive, không gọi `block()` hoặc `subscribe()`.
4. `registrationId == "corp"` là điều kiện tối thiểu để không cho social login chưa được tin cậy cấp quyền app. Với production nhiều issuer, cần xác minh cả nguồn claim/tenant theo hợp đồng và issuer đã validate.
5. Claim lấy từ **ID Token**: `user.getIdToken().getClaims().get("app_roles")`. Nếu IdP chỉ phát trong UserInfo, **không** tự có role với code này; phải chọn nguồn đúng và kiểm chứng schema.
6. `new LinkedHashSet<>(user.getAuthorities())` giữ authority mặc định từ delegate, như `OIDC_USER` và `SCOPE_*`, rồi thêm quyền được map.
7. `DefaultOidcUser` được dựng với same ID Token/UserInfo; constructor 3 tham số dùng `sub` làm principal name, không lấy email làm khóa định danh.
8. `/admin` yêu cầu `ROLE_ADMIN` thông qua `hasRole("ADMIN")`; `/reports` yêu cầu `REPORT_VIEW` chính xác.
9. `/me` chỉ trả `subject` và tên authorities để dễ thử. **Không trả ID Token, access token hoặc toàn bộ UserInfo** qua API debug.
10. `httpBasic(disable)`/`formLogin(disable)` loại cơ chế không dùng trong mẫu, `oauth2Login` vẫn phục vụ OAuth2 authorization/callback.
11. Không tắt CSRF cho cookie/session app; demo chỉ có GET.
12. Nếu có nhiều SecurityWebFilterChain, chain xử lý OAuth2 phải bao phủ `/oauth2/authorization/**` và `/login/oauth2/code/**`.

**Nếu ứng dụng cần custom name attribute:** với OIDC, constructor `DefaultOidcUser(..., nameAttributeKey)` chỉ nên dùng khi trường đã có và đúng hợp đồng IdP. `sub` cùng `iss` thường đáng tin hơn email/username cho liên kết danh tính. Không tự đổi `getName()` thành email rồi coi mọi IdP có cùng email là cùng user.

### 7.5. IdP phải phát đúng claim

Để user đăng nhập và có `REPORT_VIEW`, IdP phải phát **đúng claim** trong ID Token của trusted client, ví dụ:

~~~json
{
  "iss": "https://login.corp.example/realms/employees",
  "sub": "employee-123",
  "aud": "web-dashboard",
  "app_roles": ["viewer", "report_reader"]
}
~~~

Nếu login thành công nhưng `app_roles` không có, người dùng vẫn có thể authenticated, nhưng **không có app role nào được cấp từ allowlist**. Đây là behavior fail closed cho các protected routes, không nên vá bằng cách cấp `ROLE_ADMIN` mặc định.

### 7.6. Chạy OAuth2 Login với IdP thật

Đầu tiên chạy pure Java như phần 7.3. Sau khi IdP được cấu hình:

~~~bash
export CORP_CLIENT_ID='web-dashboard'
export CORP_CLIENT_SECRET='secret-issued-by-your-idp'
export CORP_OIDC_ISSUER_URI='https://login.corp.example/realms/employees'
./mvnw clean package
./mvnw spring-boot:run
~~~

Các giá trị trên **chỉ mang tính minh họa**. Thay bằng credential và issuer thực tế; không commit secret. Windows PowerShell dùng `$env:CORP_CLIENT_ID="..."` và tương tự cho hai biến còn lại, rồi `.\mvnw.cmd spring-boot:run`.

Khi đang chạy, có thể kiểm tra:

~~~bash
# Trang công khai:
curl -i http://localhost:8080/

# Bắt đầu Authorization Code flow (redirect 302 đến IdP):
curl -i http://localhost:8080/oauth2/authorization/corp

# Anonymous chưa đăng nhập:
curl -i http://localhost:8080/me
curl -i http://localhost:8080/admin
~~~

`curl` không thể tự hoàn tất browser login/callback của IdP. Dùng browser với một profile thử nghiệm:

1. Mở `http://localhost:8080/oauth2/authorization/corp` và hoàn tất login trên IdP.
2. Mở `http://localhost:8080/me` để thấy principal subject và authorities.
3. Nếu IdP cấp `app_roles=["viewer","report_reader"]`, người dùng sẽ có `ROLE_USER` và `REPORT_VIEW`; `GET /reports` thành công **200** `REPORT_OK`, `GET /admin` bị **403**.
4. Nếu IdP cấp `app_roles=["admin"]`, `GET /admin` thành công **200** `ADMIN_OK`.
5. Nếu claim thiếu hoặc sai kiểu, `/admin` và `/reports` bị từ chối cho authenticated user; không có fallback admin.
6. Nếu user chưa login, private endpoint thường điều hướng tới login/OIDC flow, không phải 403 của user thiếu quyền.

**Giới hạn kiểm chứng:** code mapping thuần là runnable không cần IdP. Luồng OAuth2 end-to-end chỉ kiểm thử được sau khi có IdP hợp lệ, client registration và role claim mapper. Không tuyên bố đã chạy login hoặc xác minh chữ ký token thật nếu chưa có môi trường đó.

## 8. OAuth2 non-OIDC: DefaultReactiveOAuth2UserService

Provider không có scope `openid`/ID Token sẽ đi theo service khác. Trong một Spring configuration cho registration `legacy`, có thể dùng:

~~~java
@Bean
ReactiveOAuth2UserService<OAuth2UserRequest, OAuth2User>
        oauth2UserService() {

    DefaultReactiveOAuth2UserService delegate =
            new DefaultReactiveOAuth2UserService();

    return request -> delegate.loadUser(request).map(user -> {
        Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(user.getAuthorities());

        if ("legacy".equals(
                request.getClientRegistration().getRegistrationId())) {
            Object claim = user.getAttributes().get("app_roles");

            for (String role :
                    ClaimRolePolicy.mapProviderRoles(claim)) {
                mapped.add(new SimpleGrantedAuthority(role));
            }
        }

        String nameKey = request.getClientRegistration()
                .getProviderDetails().getUserInfoEndpoint()
                .getUserNameAttributeName();

        if (nameKey == null || nameKey.isBlank()) {
            throw new IllegalStateException(
                    "Configure user-name-attribute for the provider");
        }

        return new DefaultOAuth2User(
                mapped, user.getAttributes(), nameKey);
    });
}
~~~

**Đây là method snippet, không phải Java file độc lập**. Cần import `OAuth2UserRequest`, `OAuth2User`, `DefaultReactiveOAuth2UserService`, `DefaultOAuth2User`, `ReactiveOAuth2UserService`, `Set`, `LinkedHashSet`, `GrantedAuthority` và `SimpleGrantedAuthority`, cùng registration `legacy` thật.

- OAuth2 non-OIDC nhận UserInfo attributes chứ không có OIDC ID Token.
- `DefaultReactiveOAuth2UserService` gọi UserInfo bằng `WebClient` (với access token).
- `DefaultOAuth2User` cần `nameKey` trỏ tới thuộc tính thật trong UserInfo, ví dụ `id` khi provider cung cấp `id`.
- UserInfo có thể thay đổi schema giữa provider; luôn xem API docs trước khi map.
- Không giả mạo `OidcUser` nếu không có ID Token hợp lệ.

Nếu provider chỉ có API trả group riêng, cần thêm reactive call rõ ràng thay vì hy vọng `DefaultReactiveOAuth2UserService` tự biết endpoint đó.

## 9. Lấy role từ protected API bằng access token

Khi role không có trong ID Token/UserInfo mà nằm ở một API của IdP, custom `ReactiveOAuth2UserService` có thể gọi API bằng `WebClient` và access token đã được cấp. Logic khái niệm:

~~~java
// Snippet: rolesWebClient, RoleResponse và addTrustedAuthorities
// là các thành phần của ứng dụng phải định nghĩa theo provider API.
return delegate.loadUser(request)
        .flatMap(user -> rolesWebClient.get()
                .uri("/v1/my-roles")
                .headers(h -> h.setBearerAuth(
                        request.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(RoleResponse.class)
                .timeout(Duration.ofSeconds(2))
                .map(roles -> addTrustedAuthorities(user, roles)));
~~~

Đây là **pseudocode ứng dụng**, không phải file chạy riêng: `RoleResponse` và `addTrustedAuthorities` cần được hiện thực theo hợp đồng API. Không đưa code này vào example chính nếu chưa có roles API.

Các nguyên tắc:

- Endpoint phải là HTTPS và **fixed trusted base URL**, không lấy URL tùy ý từ request (SSRF).
- Access token phải có audience/scope hợp lệ đối với roles API. **Không dùng ID Token thay access token.**
- Có timeout, giới hạn retry và phân loại lỗi 401/403/5xx rõ ràng.
- Đừng log Bearer token, UserInfo raw hoặc response chứa PII.
- Nếu API role unavailable, **không cấp admin**. Có thể fail login hoặc login với quyền tối thiểu khi chính sách cho phép.
- Dùng I/O reactive; tránh JDBC blocking hoặc `RestTemplate` ngay trên Netty event loop.
- Không viết `Mono.just(blockingCall())` vì blockingCall vẫn thực thi trước khi Mono được tạo.

### 9.1. Khi nào không cần custom user service?

Nếu chỉ muốn map OIDC claim có sẵn, bean `GrantedAuthoritiesMapper` là lựa chọn đơn giản và dễ audit. Khi không có logic I/O hoặc biến đổi principal, không cần tạo user service dài chỉ để thêm một `SimpleGrantedAuthority`.

## 10. Kiểm thử role mapping ở nhiều cấp

### 10.1. Test policy thuần

`ClaimRolePolicy.java` có main xác định kết quả; bổ sung JUnit assertions cho các trường hợp:

| Claim đầu vào | App authorities mong đợi |
| --- | --- |
| `["viewer"]` | `ROLE_USER` |
| `["admin"]` | `ROLE_ADMIN` |
| `["report_reader"]` | `REPORT_VIEW` |
| `["viewer","admin"]` | `ROLE_USER`, `ROLE_ADMIN` |
| `["super_admin"]` | Không có |
| `null` | Không có |
| `"admin"` (scalar) | Không có |
| `["ADMIN"]` | Không có |
| `[]` | Không có |
| Mixed list String và số | Chỉ map những String đã allowlist |

JUnit snippet:

~~~java
@Test
void unknownRoleIsNotAdmin() {
    assertFalse(ClaimRolePolicy
            .mapProviderRoles(List.of("super_admin"))
            .contains("ROLE_ADMIN"));
}

@Test
void knownAdminMapsExactly() {
    assertEquals(Set.of("ROLE_ADMIN"),
            ClaimRolePolicy.mapProviderRoles(List.of("admin")));
}
~~~

Đây là **test method snippet**, cần JUnit 5 và static imports `assertFalse`, `assertEquals`. `List.of(null)` bị Java cấm; muốn test null item dùng mutable List hoặc `Arrays.asList`.

### 10.2. Test user service với delegate giả lập

Tách logic mapping thành policy thuần rồi inject fake OIDC delegate trong test để assert:

- `registrationId="corp"` + trusted ID Token `app_roles=["admin"]` → có `ROLE_ADMIN`.
- Registration khác (social/unknown) → không cấp quyền app từ claim trùng tên.
- Missing claim, invalid type, duplicate values → không tạo privileged authority không định nghĩa.
- Các `OIDC_USER`/`SCOPE_*` và `getIdToken()/getUserInfo()` vẫn được giữ.
- Delegate báo lỗi → user service không biến lỗi thành thành công admin.
- `getName()` ổn định theo `sub`, không lấy email làm khóa liên kết nếu không được thiết kế.

Mock delegate kiểm tra **mapping và reactive composition**, không kiểm tra chữ ký JWT. Muốn kiểm OIDC protocol cần IdP thật hoặc fake OIDC provider đủ tiêu chuẩn.

### 10.3. WebTestClient: authorization HTTP

Spring Security Test reactive cung cấp `mockOidcLogin()` để giả lập OAuth2 authentication sau khi login. Ví dụ:

~~~java
// Snippet trong integration test có WebTestClient phù hợp:
webTestClient.mutateWith(
        mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_ADMIN")))
        .get().uri("/admin")
        .exchange()
        .expectStatus().isOk();

webTestClient.mutateWith(
        mockOidcLogin().authorities(
                new SimpleGrantedAuthority("ROLE_USER")))
        .get().uri("/admin")
        .exchange()
        .expectStatus().isForbidden();
~~~

Đây là **test snippet**, không phải class hoàn chỉnh. Nó cần Spring Security Test reactive `SecurityMockServerConfigurers.mockOidcLogin`, `WebTestClient` và test runtime được cấu hình. `mockOidcLogin().authorities(...)` **gán trực tiếp authorities**, nghĩa là **không gọi `ReactiveOAuth2UserService` và không kiểm ID Token signature**. Phải test policy và service riêng, sau đó có E2E OIDC flow với IdP để xác nhận toàn bộ hệ thống.

### 10.4. Test matrix

| Trường hợp | Kết quả đúng |
| --- | --- |
| Trusted `corp` có `app_roles=["admin"]` | Có `ROLE_ADMIN` |
| Trusted `corp` có `app_roles=["viewer","report_reader"]` | Có `ROLE_USER` và `REPORT_VIEW` |
| Unknown/uppercase role | Không thêm role cao |
| Claim thiếu/sai kiểu | Không thêm app role |
| Claim có phần tử khác String | Không cấp quyền từ phần tử đó |
| Social provider tự có field app_roles giống nhau | Không áp policy corp |
| UserInfo null | Giữ ID Token, không NPE |
| Role từ protected API bị 403 | Không mặc định cấp admin |
| OIDC ID Token invalid issuer/audience/signature | Login thất bại trước authorization |
| OAuth2 non-OIDC | Dùng DefaultReactiveOAuth2UserService |
| API chỉ có Bearer JWT | Dùng JWT converter của resource server |
| User bị thu hồi admin khi còn WebSession | Cần revoke/refresh/recheck |
| Multi-tenant cùng email | Không tự hợp nhất authorities |
| App sau proxy | Callback redirect URI và HTTPS đúng |

## 11. Vòng đời quyền sau khi login

Một rủi ro là **role snapshot**. `ReactiveOAuth2UserService` thường được gọi khi đăng nhập, còn `OAuth2AuthenticationToken` của user có thể được giữ trong `WebSession`:

~~~text
10:00 IdP cấp app_roles=["admin"]
10:00 user đăng nhập -> ROLE_ADMIN trong Authentication
10:05 quản trị IdP thu hồi role admin
10:06 browser vẫn giữ WebSession đã authenticated
10:06 app có thể còn thấy ROLE_ADMIN cũ
      nếu chưa có session revoke, re-login hoặc dynamic authorization
~~~

Để giảm độ trễ thu hồi quyền:

- Giới hạn thời gian session và yêu cầu re-authentication cho hành động nhạy cảm.
- Xây dựng quy trình revoke WebSession khi tài khoản/role đổi; hỗ trợ cluster/distributed store.
- Khi có OIDC back-channel logout từ IdP, dùng thành phần phù hợp nếu provider hỗ trợ; không mặc định rằng mọi sự kiện role change sẽ thành logout.
- Đối với hành động high-risk, gọi policy service hoặc database hiện thời bằng ReactiveAuthorizationManager, áp cache TTL phù hợp.
- Với Bearer access token JWT ở resource server, phải có expiry/revocation/introspection hoặc token version policy riêng. **Thu hồi WebSession của OAuth2 Login không tự vô hiệu hóa mọi JWT đã phát ra.**

Không nhầm “mapping đúng khi đăng nhập” với “quyền luôn cập nhật trong thời gian thực”. Đây là hai bài toán.

## 12. Những lỗi thường gặp

### 12.1. Copy Servlet DSL sang WebFlux

`HttpSecurity.oauth2Login(...userInfoEndpoint(...))` không phải API của `ServerHttpSecurity.OAuth2LoginSpec` WebFlux 7.1. Dùng bean `ReactiveOAuth2UserService` hoặc `GrantedAuthoritiesMapper` đúng stack; không thêm Servlet filters để chữa lỗi compile.

### 12.2. OIDC user service đọc sai nguồn claim

Ứng dụng đọc `user.getIdToken().getClaims().get("app_roles")` nhưng IdP lại gửi role trong UserInfo. Kết quả là không có app role dù login thành công. Kiểm tra hợp đồng claim location, cấu hình IdP và schema trước khi sửa mapper.

### 12.3. Giữ sai principal type

Với OIDC, đừng tạo `DefaultOAuth2User` chỉ có attributes mà bỏ `OidcIdToken`. Giữ `OidcUser`, ID Token, UserInfo (có thể null) và principal name bằng `DefaultOidcUser`.

### 12.4. Mất authorities mặc định

Nếu tạo list authorities mới chỉ chứa `ROLE_ADMIN`, có thể làm rơi `OIDC_USER`, `SCOPE_*` hoặc provider-granted authorities. Nên copy `user.getAuthorities()` rồi thêm quyền đã map.

### 12.5. ROLE_ADMIN khác SCOPE_ADMIN

`hasRole("ADMIN")` kiểm `ROLE_ADMIN`, không phải `ADMIN` hoặc `SCOPE_ADMIN`. Xem final Authentication authorities khi debug; đừng log full token.

### 12.6. Trust every token claim

Dùng `"ROLE_" + string` với claim bất kỳ có thể vô tình map quyền của app khác hoặc role do user tự sửa được. Dùng allowlist và xác định trusted issuer/client/tenant.

### 12.7. Dùng email làm identity key xuyên provider

Hai IdP có thể cung cấp cùng email hoặc email có thể đổi. Dùng `iss + sub` hoặc khóa local account linking được xác minh; `email_verified` không tự cấp admin.

### 12.8. Blocking HTTP trong service

`ReactiveOAuth2UserService` chạy trong reactive login. Gọi blocking I/O có thể chặn event loop. Dùng `WebClient`, timeout và error handling không nâng quyền.

### 12.9. Dùng mapper bean và user service cùng map một claim

Điều này có thể trùng authorities, khó xác định nơi quyết định và kiểm thử. Chọn một nơi map quyền chính và ghi rõ responsibility, đặc biệt khi nhiều provider.

### 12.10. Chỉ test mockOidcLogin rồi kết luận mapping hoạt động

Mock OIDC login gán sẵn Authentication và có thể bỏ qua user service. Phải unit test claim policy/delegation và test OIDC login thật hoặc mock provider có token flow.

### 12.11. Dùng user service của OAuth2 Login để xử lý Bearer JWT API

Đây là hai chức năng khác nhau. Resource Server JWT cần converter trong `oauth2ResourceServer().jwt(...)`; user service OAuth2 Login không tự chạy khi kiểm JWT API.

### 12.12. Role bị thu hồi nhưng session còn quyền

Login là sự kiện, không phải một lần kiểm tra role trên mọi request. Cần session revocation, reauth, hoặc policy kiểm tra động nếu yêu cầu.

### 12.13. Đưa token/claims ra log hay endpoint debug

Không log ID Token, access token, refresh token, client secret hoặc toàn bộ UserInfo. Endpoint `/me` demo chỉ hiển thị subject và authority names; production cần cân nhắc bỏ endpoint debug.

## 13. Checklist production

1. Phân biệt OAuth2 Login, OIDC Login và Resource Server JWT.
2. Đúng Spring Security WebFlux reactive APIs, không dùng Servlet DSL.
3. Spring Boot/Security dependency BOM tương thích, OAuth2 Client starter đúng Boot version.
4. IdP issuer/discovery, client ID/secret, redirect URI HTTPS và TLS được xác minh.
5. Custom service delegate sang đúng implementation và không tự bỏ ID Token validation.
6. Claim role được cấp bởi IdP server-side, đúng client/tenant/issuer, không do user tự sửa.
7. Có allowlist mapping, fail closed với missing/invalid/unknown role.
8. Giữ các authorities có sẵn, ID Token, UserInfo và principal identifier.
9. Phân biệt `ROLE_*`, `SCOPE_*`, `OIDC_USER` và app authorities.
10. Không cấp role từ HTTP header/query/form hoặc email domain.
11. Nếu gọi roles API, cần HTTPS, fixed URL, đúng audience/scope, timeout và fail-safe.
12. Giữ CSRF, state/nonce, WebSession/cookie policy, không tự tắt security để login chạy.
13. Kiểm tra callback URL khi chạy sau reverse proxy/ingress.
14. Unit test mapping thuần, user service, HTTP rule và OIDC integration flow.
15. Có chiến lược re-evaluate/revoke authorities khi user/role/account thay đổi.
16. Không phơi secret/token/PII trong debug response, log, analytics.
17. Nhiều issuer/tenant phải có isolation và account linking rõ ràng.
18. Document provider claim contract và review mỗi khi IdP thay đổi schema.

## 14. Tự kiểm tra

**Câu 1.** Vì sao `app_roles=["admin"]` không tự vượt qua `hasRole("ADMIN")`?

**Đáp án:** Spring Security kiểm `ROLE_ADMIN` trong `Authentication.getAuthorities()`. Claim riêng không tự được đổi thành authority; phải map rõ.

**Câu 2.** Khi nào nên dùng `GrantedAuthoritiesMapper`?

**Đáp án:** Khi chỉ đọc claim/authorities đã có và map đồng bộ. Nếu cần gọi roles API bằng access token, dùng reactive user service với `WebClient`.

**Câu 3.** Tại sao nên delegate sang `OidcReactiveOAuth2UserService` trước khi map?

**Đáp án:** Để giữ xử lý OIDC UserInfo và principal mặc định của Spring Security; custom mapper chỉ bổ sung logic quyền.

**Câu 4.** `app_roles="admin"` là string scalar, code cấp admin không?

**Đáp án:** Không. Policy chỉ nhận collection và các String nằm trong allowlist.

**Câu 5.** Vì sao copy `user.getAuthorities()` trước khi thêm quyền?

**Đáp án:** Để giữ `OIDC_USER`, `SCOPE_*` và authorities sẵn có; không vô tình xóa quyền hợp lệ/metadata.

**Câu 6.** Một provider ngoài `corp` trả cùng claim `app_roles=["admin"]`, có cấp admin không?

**Đáp án:** Không theo mẫu: điều kiện registrationId `corp` phải đúng. Production vẫn cần kiểm issuer/tenant và hợp đồng IdP.

**Câu 7.** `mockOidcLogin().authorities(...)` chứng minh điều gì?

**Đáp án:** Chứng minh HTTP rule 200/403 với authorities đã cho; **không** chứng minh claim mapping hay token validation.

**Câu 8.** Vì sao user có thể giữ admin sau khi role bị thu hồi ở IdP?

**Đáp án:** WebSession/Authentication có thể giữ snapshot authorities từ lần login. Cần session revoke/reauth/kiểm quyền động.

**Câu 9.** `ReactiveOAuth2UserService` có xử lý Bearer JWT ở resource server không?

**Đáp án:** Không tự động. Resource server dùng JWT authentication converter/authorization riêng.

**Câu 10.** Có được dùng `email_verified=true` hoặc email domain để tự cấp ROLE_ADMIN không?

**Đáp án:** Không. Email xác minh chỉ là thông tin nhận dạng/liên hệ; quyền admin cần nguồn ủy quyền riêng, đáng tin và đúng ứng dụng.

## 15. Tài liệu chính thức

- [Spring Security — Reactive OAuth2 Login: Advanced Configuration and Mapping Authorities](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/advanced.html)
- [Spring Security — Reactive OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/core.html)
- [Spring Security — Reactive OAuth2 Login Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html)
- [Javadoc — ReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/ReactiveOAuth2UserService.html)
- [Javadoc — OidcReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/oidc/userinfo/OidcReactiveOAuth2UserService.html)
- [Javadoc — DefaultReactiveOAuth2UserService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/userinfo/DefaultReactiveOAuth2UserService.html)
- [Javadoc — DefaultOidcUser](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/oidc/user/DefaultOidcUser.html)
- [Javadoc — ServerHttpSecurity.OAuth2LoginSpec](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.OAuth2LoginSpec.html)
- [Spring Security — Reactive Testing OAuth2/OIDC](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Boot 4.0 Migration Guide — Renamed OAuth2 Client Starter](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
