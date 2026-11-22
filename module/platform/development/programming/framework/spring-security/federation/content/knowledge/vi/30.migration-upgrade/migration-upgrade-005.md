# Chuyển CAS client và bộ lọc sang thư viện tương thích Jakarta Servlet

> **Module:** Spring Security – federation · **Nhóm:** Chuyển đổi và nâng cấp. Hướng dẫn chuyển ứng dụng đang dùng **Apereo Java CAS Client 3.x**, `javax.servlet.*`, `web.xml`/Servlet filters và đôi khi `spring-security-cas` sang **Jakarta Servlet** trên Spring Boot 3/4 hoặc Servlet container thế hệ mới. Mục tiêu không chỉ là biên dịch: CAS service ticket vẫn được xác thực một lần với **đúng service URL**; chuỗi filter có thứ tự an toàn; CAS Single Logout (SLO), Session và Spring SecurityContext không bị bỏ qua; endpoint/cookie/TLS hoạt động sau reverse proxy. Bài có bản đồ phụ thuộc theo JDK và framework, các fragment Java/XML, quy trình kiểm thử và **một Java 17 demo biên dịch/chạy độc lập** để rà soát migration policy. Các URI/người dùng trong bài là ví dụ, không chứa secret thực.

## 1. Tại sao nâng Spring Boot làm CAS client đang chạy bị hỏng?

Ứng dụng cũ thường có:

```text
Java 8/11/17
  |
  +-- Spring Framework 5 / Spring Boot 2
  |      Servlet API: javax.servlet.*
  |
  +-- Apereo Java CAS Client 3.x
  |      AuthenticationFilter
  |      Cas20/Cas30...TicketValidationFilter
  |      SingleSignOutFilter
  |      SingleSignOutHttpSessionListener
  |
  +-- Servlet container như Tomcat 9
         implements javax.servlet.* API
```

Khi chuyển lên Spring Boot 3/Spring Framework 6 hoặc container Jakarta (ví dụ Tomcat 10.1):

```text
Spring Boot 3 / Spring Framework 6
  |
  +-- Jakarta Servlet 6.0: jakarta.servlet.*
  |
  +-- Application custom filters require jakarta.servlet.Filter
  |
  +-- CAS client 3.x compiled against javax.servlet.Filter
          |
          +-- cannot be used as jakarta.servlet.Filter
          +-- ClassNotFoundException / NoClassDefFoundError
          +-- ClassCastException / BeanCreationException
          +-- FilterRegistrationBean generic type mismatch
```

`javax.servlet.Filter` và `jakarta.servlet.Filter` **là hai kiểu Java khác nhau**, dù signatures/method names tương tự. Đổi `import javax.servlet.*` trong code ứng dụng không biến bytecode của thư viện `cas-client-core` cũ thành Jakarta classes. Đồng thời, CAS có thể bị lỗi logic dù app khởi động: sai service callback URL, bị đăng ký filter hai lần, callback logout bị CSRF filter chặn, session index bị mất khi triển khai nhiều pods.

**Phạm vi bài:** CAS protocol (CAS 2/3 service-ticket login, tùy ứng dụng có SAML 1.1 CAS, proxy tickets, SLO). Không đánh đồng CAS client filter với Spring Security **SAML2 Web SSO**; CAS và SAML2 có thể cùng tồn tại ở IdP nhưng token/callback/validation profile khác nhau.

### 1.1. Kết quả học tập

Sau bài này, bạn có thể:

1. Đánh giá tương thích JDK–Spring Boot–Servlet–CAS client trước khi đổi dependencies.
2. Thay `javax.servlet` bằng `jakarta.servlet` trong code app, filters, listeners và kiểm tra transitive dependencies.
3. Chọn giữa **Apereo CAS servlet filters**, **Spring Security CAS AuthenticationProvider/Filter**, hoặc **Apereo Spring Boot integration** theo kiến trúc, tránh duplicate authentication.
4. Chuyển `web.xml` hoặc đăng ký `FilterRegistrationBean` mà vẫn giữ **SingleSignOutFilter trước các CAS filters**.
5. Xác minh CAS ticket validation, service URL exact match, TLS, service callback qua proxy.
6. Xử lý `HttpServletRequestWrapperFilter`, `AssertionThreadLocalFilter`, character encoding filter và lifecycle của `SingleSignOutHttpSessionListener` khi còn dùng.
7. Tránh trùng `springSecurityFilterChain`/Servlet container filter registration.
8. Thiết kế tương thích SLO trong cluster, xử lý cookie, session fixation và Redis/Spring Session.
9. Viết migration tests phát hiện `javax.servlet-api` lẫn `jakarta.servlet-api`, CAS client cũ, wrong filter order, thiếu listener, wrong service và ticket replay.
10. Lên kế hoạch canary, rollback, alert và kiểm thử hậu triển khai.

## 2. Xác định rõ đang sử dụng CAS client theo kiến trúc nào

Ba cách cấu hình đều có thể thấy trong legacy systems:

| Kiến trúc | Thành phần chính | Cơ chế auth thực |
| --- | --- | --- |
| **A — Apereo Java CAS Client Filters thuần** | `AuthenticationFilter`, `Cas30ProxyReceivingTicketValidationFilter`, request wrapper, SLO filter/listener | CAS library validate ticket và đặt assertion trong request/session, app dùng principal/attributes |
| **B — Spring Security CAS integration** | `CasAuthenticationFilter`, `CasAuthenticationProvider`, `CasAuthenticationEntryPoint`, `ServiceProperties`, CAS TicketValidator | Spring Security quản lý `Authentication`/`SecurityContext`/roles; ticket được provider validate |
| **C — Apereo CAS Spring Boot Support** | `cas-client-support-springboot`, `@EnableCasClient` và cấu hình `cas.*` | Module tự đăng ký CAS client filters/listeners theo lựa chọn, app vẫn phải thiết kế cách bridge authorization/security |

Nếu trong dự án có **cả** `org.apereo.cas.client.authentication.AuthenticationFilter` và `org.springframework.security.cas.web.CasAuthenticationFilter` xử lý cùng callback/service ticket, rất dễ có **double redirect / double ticket validation**. CAS service ticket thường **single-use**: filter thứ nhất validate thành công, filter thứ hai dùng lại cùng ticket sẽ fail, khiến login loop và lỗi ngẫu nhiên.

**Trước migration, chọn một owner chính của request CAS callback.** Có thể giữ `SingleSignOutFilter`/listener từ Apereo cùng Spring Security CAS nếu được thiết kế và kiểm chứng, nhưng không tự động bật toàn bộ hai authentication stacks.

### 2.1. Không biến việc “nâng dependency” thành “đổi protocol”

- CAS `/login?service=...` rồi browser quay lại với query `ticket=ST-...` là **CAS service-ticket flow**.
- SAML 2.0 Web SSO đưa `SAMLResponse` tới ACS, verify XML signatures/Assertions.
- CAS SAML 1.1 validator (`Saml11TicketValidationFilter`) là CAS client protocol variant; **không** phải tự động tương thích Spring Security `saml2Login()`.
- OIDC dùng authorization code, ID Token, JWKS/nonce/PKCE khác CAS service-ticket validation.
- Nếu dự án muốn thay CAS bằng OIDC/SAML2, đó là **migration xác thực mới** với trust, session, logout, claims và compatibility plan riêng; không nằm trong bước chỉ đổi Servlet API.

### 2.2. Inventory trước khi sửa

Lập bảng theo *cấu hình đang chạy*, không dựa trên tài liệu cũ:

| Phần cần rà | Câu hỏi cần có câu trả lời |
| --- | --- |
| Runtime | JDK thực tế, servlet container/embedded Tomcat/Jetty, WAR hay executable JAR? |
| Framework | Spring Boot 2.x, 3.x hay 4.x? Spring Security version? |
| CAS libraries | `cas-client-core` bản nào, `spring-security-cas` có không, transitive dependencies cũ? |
| Filter registration | `web.xml`, `@WebFilter`, `@EnableCasClient`, `FilterRegistrationBean`, `HttpSecurity.addFilter...`? |
| CAS service | `casServerUrlPrefix`/`casServerLoginUrl`/`serverName`/`service`, actual callback URI và proxy host? |
| Ticket validation | CAS 1/2/3? CAS20/30 validator? Proxy ticket/PGT? Timeout/TLS? |
| SLO | `SingleSignOutFilter`, `SingleSignOutHttpSessionListener`, callback path, session registry, cluster? |
| Security context | Ai tạo `Authentication`/principal và gán authorities? |
| HTTP edges | Ingress forwarded headers, cookie SameSite/Domain/Path, CSRF, redirects, logout POST? |
| Tests | Positive login, invalid/replayed ticket, SLO local/multi-node, filters count/order, failover? |

Mọi migration nên có **baseline behavior** trong test environment trước khi thay thư viện.

## 3. Ma trận phiên bản: không chọn 4.1.x chỉ vì nó mới hơn

Theo Maven Central POM được kiểm tra vào tháng 11/2026, Apereo Java CAS Client **4.0.4** dùng `jakarta.servlet-api` 6.0, baseline Java **17** với dependencies thuộc thế hệ Spring Boot 3/Spring Framework 6. CAS Client **4.1.1** cũng là Jakarta, nhưng POM của nó đặt Java **21**, Servlet **6.1** và dependencies phát triển theo Spring Boot 4/Spring Framework 7.

| Dòng ứng dụng | CAS client phù hợp để đánh giá | JDK tối thiểu theo nhánh | Lưu ý |
| --- | --- | --- | --- |
| Legacy Spring Boot 2 / Tomcat 9 | Apereo CAS Client 3.x legacy | Tùy bản cũ | `javax.servlet.*`, chưa phải Jakarta |
| Spring Boot 3 / Tomcat 10.1 / Spring 6 | Apereo CAS Client 4.0.x Jakarta, ví dụ 4.0.4 | 17 | Thử với Spring Boot BOM cụ thể, SLO/security/bugs và supported patches |
| Spring Boot 4 / Spring 7 / Servlet 6.1 | Apereo CAS Client 4.1.x Jakarta, ví dụ 4.1.1 | 21 | Kiểm cả Boot/CAS artifacts và release compatibility |
| WAR triển khai container bên ngoài | CAS client phải cùng Jakarta Servlet generation với container | Theo artifact/container | Không tự đóng gói duplicate servlet-api |
| Spring Security CAS integration | `spring-security-cas` tương ứng Spring Security major, CAS protocol validator tương thích | Theo Spring Security version | **Không** tự trộn CAS provider mới với `cas-client-core` 3.x |

**Cẩn thận:** bảng là **mốc phụ thuộc có thể kiểm chứng**, không bảo đảm mọi kết hợp patch chạy tốt. Xem build POM/BOM của artifact được chọn, release notes, CVEs và CI. Nếu ứng dụng **bắt buộc Java 17**, không dùng một CAS Client 4.1.1 yêu cầu Java 21 rồi chỉ đặt `maven.compiler.release=17`; bytecode/library dependencies vẫn có thể đòi runtime 21.

### 3.1. Vì sao version hỗn hợp gây lỗi âm thầm?

Giả sử:
- `cas-client-core:3.6.4` từ legacy.
- `cas-client-support-springboot:4.1.1` từ module mới.
- `spring-security-cas` thuộc nhánh Spring 6/7 khác.
- Embedded Servlet API của Boot 3 là Jakarta.

Build có thể chọn classpath phiên bản bất ngờ qua dependency mediation; một module import `javax.servlet.Filter` còn module kia import `jakarta.servlet.Filter`. Đến runtime mới nổ `NoClassDefFoundError: javax/servlet/Filter`, CAS authentication filter không được register hoặc ticket được validate hai lần.

**Quy tắc:** chốt **một bộ versions được thử cùng nhau** qua BOM/dependency management; không override Spring Framework/Security/Tomcat tùy tiện chỉ để “qua compile”.

### 3.2. Kiểm Maven và Gradle trước khi sửa code

Maven:

```bash
mvn -q -DskipTests dependency:tree
mvn -q help:effective-pom
mvn -q -DskipTests clean package
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency cas-client-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency servlet-api --configuration runtimeClasspath
./gradlew test
```

Tìm **javax.servlet**, **jakarta.servlet**, phiên bản `cas-client-core`, `spring-security-cas`, `tomcat-embed-core` và transitive modules. Một module chứa từ `javax` trong package name **không phải luôn lỗi** (nhiều chuẩn Java SE vẫn dùng `javax.crypto`/`javax.net.ssl`); tập trung đúng namespace `javax.servlet.*`/`javax.annotation.*` thuộc Jakarta migration và các types thực đang được dùng.

### 3.3. Phân biệt API và implementation

- `jakarta.servlet:jakarta.servlet-api` chỉ là **Servlet API**; Tomcat/Jetty thực thi API.
- Embedded Spring Boot thường cung cấp container phù hợp qua starter.
- Khi build WAR cho server ngoài, servlet API nên ở **provided** scope, không tạo hai implementations trong WAR.
- Đừng thêm `javax.servlet-api` để cố “cung cấp class thiếu” cho CAS client 3.x bên cạnh Jakarta runtime; nó chỉ tạo hai worlds kiểu Java **không thể ép cast** qua nhau.
- Không tự dùng class transformer/shading như một biện pháp lâu dài khi có artifact Jakarta chính thức; nếu buộc dùng transformation tạm, thử binary compatibility, filter init/async/session/listeners và security regressions, không suy rằng tự động đổi bytecode là hoàn tất migration.

## 4. Từ javax.servlet sang jakarta.servlet — chính xác phần nào đổi?

### 4.1. Bảng đổi namespace thường gặp

| Trước nâng cấp | Sau nâng cấp |
| --- | --- |
| `javax.servlet.Filter` | `jakarta.servlet.Filter` |
| `javax.servlet.FilterChain` | `jakarta.servlet.FilterChain` |
| `javax.servlet.FilterConfig` | `jakarta.servlet.FilterConfig` |
| `javax.servlet.ServletRequest` | `jakarta.servlet.ServletRequest` |
| `javax.servlet.ServletResponse` | `jakarta.servlet.ServletResponse` |
| `javax.servlet.ServletException` | `jakarta.servlet.ServletException` |
| `javax.servlet.http.HttpServletRequest` | `jakarta.servlet.http.HttpServletRequest` |
| `javax.servlet.http.HttpServletResponse` | `jakarta.servlet.http.HttpServletResponse` |
| `javax.servlet.http.HttpSession` | `jakarta.servlet.http.HttpSession` |
| `javax.servlet.http.HttpSessionEvent` | `jakarta.servlet.http.HttpSessionEvent` |
| `javax.servlet.http.HttpSessionListener` | `jakarta.servlet.http.HttpSessionListener` |
| `javax.servlet.annotation.WebFilter` | `jakarta.servlet.annotation.WebFilter` |
| `javax.servlet.annotation.WebListener` | `jakarta.servlet.annotation.WebListener` |
| `javax.servlet.DispatcherType` | `jakarta.servlet.DispatcherType` |

**Không** thay `javax.crypto` hoặc `javax.net.ssl` bằng `jakarta`: chúng thuộc Java SE và vẫn là `javax.*`. Không blind search/replace mọi `javax`.

### 4.2. Custom filter sau migration

```java
package example.security;

import java.io.IOException;
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;

public final class RequestAuditFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {
        // Example only. Never log the CAS ticket or session cookie.
        chain.doFilter(request, response);
    }
}
```

Fragment trên **biên dịch được khi có Jakarta Servlet API** trong classpath, nhưng không chạy độc lập chỉ với JDK 17. Nó minh họa đúng imports/interface, không có CAS authentication logic. Với filters cần `init(FilterConfig)`/`destroy()` hoặc dispatcher handling, thử toàn lifecycle; Java source import đổi xong chưa đủ nếu các utility libraries trong classpath vẫn dùng javax.

### 4.3. HttpSessionListener sau migration

```java
package example.security;

import jakarta.servlet.http.HttpSessionEvent;
import jakarta.servlet.http.HttpSessionListener;

public final class SessionCleanupListener
        implements HttpSessionListener {
    @Override
    public void sessionDestroyed(HttpSessionEvent event) {
        // Application-specific cleanup of non-sensitive indexes.
        // Keep CAS client listener separately if its SLO mapping uses it.
    }
}
```

Một listener tự viết như trên **không thay thế** `SingleSignOutHttpSessionListener` của Apereo; listener của Apereo dọn mapping SLO tương ứng. Nếu đổi `web.xml` sang Boot registration, kiểm cả hai listeners được đăng ký **mỗi loại một lần** và sự kiện thật sự chạy khi session expires/invalidate.

### 4.4. web.xml Jakarta namespace

Với một Jakarta Servlet 6.0 WAR, descriptor theo schema Jakarta:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<web-app
    xmlns="https://jakarta.ee/xml/ns/jakartaee"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
    xsi:schemaLocation="
      https://jakarta.ee/xml/ns/jakartaee
      https://jakarta.ee/xml/ns/jakartaee/web-app_6_0.xsd"
    version="6.0">

  <filter>
    <filter-name>cas-single-sign-out</filter-name>
    <filter-class>org.apereo.cas.client.session.SingleSignOutFilter</filter-class>
    <init-param>
      <param-name>logoutCallbackPath</param-name>
      <param-value>/cas/logout/callback</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-single-sign-out</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <filter>
    <filter-name>cas-auth</filter-name>
    <filter-class>org.apereo.cas.client.authentication.AuthenticationFilter</filter-class>
    <init-param>
      <param-name>casServerUrlPrefix</param-name>
      <param-value>https://sso.example.org/cas</param-value>
    </init-param>
    <init-param>
      <param-name>serverName</param-name>
      <param-value>https://portal.example.org</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-auth</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <filter>
    <filter-name>cas-validate</filter-name>
    <filter-class>
      org.apereo.cas.client.validation.Cas30ProxyReceivingTicketValidationFilter
    </filter-class>
    <init-param>
      <param-name>casServerUrlPrefix</param-name>
      <param-value>https://sso.example.org/cas</param-value>
    </init-param>
    <init-param>
      <param-name>serverName</param-name>
      <param-value>https://portal.example.org</param-value>
    </init-param>
  </filter>
  <filter-mapping>
    <filter-name>cas-validate</filter-name>
    <url-pattern>/*</url-pattern>
  </filter-mapping>

  <listener>
    <listener-class>
      org.apereo.cas.client.session.SingleSignOutHttpSessionListener
    </listener-class>
  </listener>
</web-app>
```

**Đây là descriptor minh họa thứ tự SLO → authentication → validation**, không phải deployment hoàn chỉnh. Chưa cấu hình request wrapper/AssertionThreadLocalFilter, Spring Security filter chain, service callback exact, public health exclusions, security headers, CSRF exceptions có scope, CAS server registered service, TLS và session cluster. `Cas30ProxyReceivingTicketValidationFilter` chỉ bật proxy validation policy khi explicitly configured; không đặt `acceptAnyProxy=true` nếu không có trust contract.

### 4.5. Khi nào vẫn giữ web.xml?

WAR deployed vào external Tomcat hoặc WebSphere/Liberty có thể cần descriptor; việc giữ web.xml là hợp lý khi runtime hỗ trợ Jakarta và cấu hình được kiểm chứng. Spring Boot executable JAR thường thích Java configuration/FilterRegistrationBean. **Không bật cùng lúc web.xml + @WebFilter + FilterRegistrationBean cho cùng CAS filter.**

## 5. Đổi dependency: Maven ví dụ hai lộ trình

### 5.1. Lộ trình Java 17 + Spring Boot 3 (đánh giá CAS Client 4.0.4)

```xml
<!-- Fragment pom.xml; Boot BOM/parent quản lý Spring/Tomcat versions. -->
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-core</artifactId>
  <version>4.0.4</version>
</dependency>
```

Dùng đúng `cas-client-core`, **không** dùng `cas-client` POM aggregator như thể nó chứa filter classes. Khi có SAML 1.1 CAS support, proxy ticket cache hoặc Apereo Boot integration, thêm artifact đúng nhu cầu và **cùng nhánh version**.

### 5.2. Lộ trình Java 21 + Spring Boot 4 (đánh giá CAS Client 4.1.1)

```xml
<!-- Fragment cho ứng dụng đủ baseline Java 21 / Boot 4. -->
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-core</artifactId>
  <version>4.1.1</version>
</dependency>
```

Bản 4.1.1 POM được công bố với `project.build.sourceVersion=21`. Không quảng bá 4.1.1 là drop-in cho Java 17. Với Spring Boot 3 Java 17, đánh giá bản CAS Client 4.0.x cùng security fixes; nếu có rủi ro bảo mật chưa được backport thì phải có risk decision/upgrade runtime được duyệt, không chọn thư viện không chạy được.

### 5.3. Apereo CAS Spring Boot support

Apereo README mô tả module:

```xml
<dependency>
  <groupId>org.apereo.cas.client</groupId>
  <artifactId>cas-client-support-springboot</artifactId>
  <version>4.1.1</version>
</dependency>
```

Các properties documented:

```properties
cas.server-url-prefix=https://sso.example.org/cas
cas.server-login-url=https://sso.example.org/cas/login
cas.client-host-url=https://portal.example.org
```

Với `@EnableCasClient`, module có thể tự đăng ký authentication/validation/SLO filters. **Chọn một trong hai:** dùng module để tự register, **hoặc** tự khai `FilterRegistrationBean`; không bật cả hai. Đặc biệt module 4.1.1 phải được thử theo Boot 4/JDK 21; không tự copy `@EnableCasClient` sang project đang ở 4.0.x rồi cho rằng cùng APIs.

### 5.4. Jakarta Servlet API dependency

Ví dụ WAR build với Jakarta Servlet 6.0:

```xml
<dependency>
  <groupId>jakarta.servlet</groupId>
  <artifactId>jakarta.servlet-api</artifactId>
  <scope>provided</scope>
</dependency>
```

Version do framework BOM/container policy quản lý. Với executable Boot JAR, thường **không cần khai báo servlet API trực tiếp**, vì web starter/container cung cấp. Không thêm `javax.servlet-api` như workaround.

### 5.5. Dependency tree fail gate

Để ngăn legacy filters lọt vào runtime:

```text
FAIL migration gate if runtimeClasspath contains:
  javax.servlet:javax.servlet-api
  cas-client-core 3.x used in Jakarta request pipeline
  custom filter compiled as javax.servlet.Filter
  obsolete javax.servlet-dependent add-on
  two incompatible CAS client core versions

PASS only after verifying:
  jakarta servlet filter classes compile and load
  chosen CAS client matches JDK and Boot generation
  only one owner for CAS ticket authentication
  SLO listener/filter lifecycle registered and tested
```

Có thể dùng Maven Enforcer `bannedDependencies` để cấm `javax.servlet-api` (Apereo source POM cũng có rule loại bỏ các legacy deps) và fail CI khi dependency tree sai. **Không cấm toàn bộ `javax.*`** vì Java SE/JNDI/crypto còn dùng namespace đó.

## 6. Spring Boot 3: đăng ký Apereo filters bằng FilterRegistrationBean

Nếu ứng dụng chọn **kiến trúc A — Apereo filters thuần**, dùng `FilterRegistrationBean` để quản lý order/URL/init params thay cho servlet web.xml. Cấu hình dưới đây mô tả APIs của Spring Boot 3/Jakarta Servlet nhưng chưa có full authentication/authorization integration.

```java
package example.cas;

import org.apereo.cas.client.authentication.AuthenticationFilter;
import org.apereo.cas.client.validation
        .Cas30ProxyReceivingTicketValidationFilter;
import org.apereo.cas.client.session.SingleSignOutFilter;
import org.apereo.cas.client.session.SingleSignOutHttpSessionListener;

import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.boot.web.servlet.ServletListenerRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;

@Configuration
public class CasJakartaFilterConfiguration {

    private static final String CAS =
            "https://sso.example.org/cas";
    private static final String PUBLIC_ORIGIN =
            "https://portal.example.org";

    @Bean
    FilterRegistrationBean<SingleSignOutFilter> casSloFilter() {
        var registration = new FilterRegistrationBean<>(
                new SingleSignOutFilter());
        registration.setName("cas-single-sign-out");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "logoutCallbackPath", "/cas/logout/callback");
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 10);
        return registration;
    }

    @Bean
    FilterRegistrationBean<AuthenticationFilter> casAuthentication() {
        var registration = new FilterRegistrationBean<>(
                new AuthenticationFilter());
        registration.setName("cas-authentication");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "casServerUrlPrefix", CAS);
        registration.addInitParameter(
                "serverName", PUBLIC_ORIGIN);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 20);
        return registration;
    }

    @Bean
    FilterRegistrationBean<Cas30ProxyReceivingTicketValidationFilter>
            casTicketValidation() {
        var registration = new FilterRegistrationBean<>(
                new Cas30ProxyReceivingTicketValidationFilter());
        registration.setName("cas-ticket-validation");
        registration.addUrlPatterns("/*");
        registration.addInitParameter(
                "casServerUrlPrefix", CAS);
        registration.addInitParameter(
                "serverName", PUBLIC_ORIGIN);
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE + 30);
        return registration;
    }

    @Bean
    ServletListenerRegistrationBean<SingleSignOutHttpSessionListener>
            casSessionListener() {
        return new ServletListenerRegistrationBean<>(
                new SingleSignOutHttpSessionListener());
    }
}
```

**Cần xem ví dụ là fragment cấu hình có điều kiện:** phải có `cas-client-core` Jakarta version; Boot web starter và Jakarta Servlet runtime; application must choose filter strategy; CAS registered service URL/port/context path phải khớp; SLO logout callback phải thực sự được CAS server gọi. Kế hoạch production còn cần request wrapper/AssertionThreadLocalFilter theo use case, fallback login loop handling, protected URL rules, local authority mapping, health endpoints, CSRF cho user-initiated logout, cookie/TLS and distributed sessions.

### 6.1. Tại sao đặt order tường minh?

Spring Boot `FilterRegistrationBean.setOrder(int)` điều khiển thứ tự **container filter chain**. Ở ví dụ:

```text
CAS SingleSignOutFilter      order = HIGHEST_PRECEDENCE + 10
CAS AuthenticationFilter     order = HIGHEST_PRECEDENCE + 20
CAS TicketValidationFilter   order = HIGHEST_PRECEDENCE + 30
... request wrapper, Spring Security/DispatcherServlet as configured
```

**Chú ý:** order số nhỏ hơn chạy sớm hơn. Apereo README yêu cầu `SingleSignOutFilter` đứng **trước các filter CAS còn lại** khi dùng web filters. Thứ tự authentication/validation phù hợp cấu hình client thông dụng nhưng phải xác minh end-to-end với version/filter feature đã chọn. Nếu một filter đọc body của logout POST, đặt charset/encoding filter theo documented requirements để tránh parse sai; đừng tự ép mọi filter vào `Ordered.HIGHEST_PRECEDENCE` không phân tích lifecycle.

### 6.2. Đừng tự đăng ký cùng instance lần hai

Một `Filter` được khai báo `@Bean` có thể được Spring Boot tự register làm Servlet container filter. Nếu developer đồng thời thêm filter đó vào `http.addFilterBefore(...)`, filter có thể chạy hai lần: một lần ngoài `springSecurityFilterChain`, một lần bên trong. Spring Security reference khuyến nghị **disable container registration** nếu filter chỉ thuộc SecurityFilterChain:

```java
// Fragment nếu filter custom chỉ nên chạy TRONG SecurityFilterChain.
@Bean
FilterRegistrationBean<MySecurityFilter> noContainerAutoRegistration(
        MySecurityFilter filter) {
    var bean = new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
```

`MySecurityFilter` là custom type giả định, không phải CAS class. Phải chọn ownership rõ: **container filter** hoặc **Spring Security filter**, không vô tình hai nơi. Nếu dùng `FilterRegistrationBean` theo phần 6 để trực tiếp register CAS filters, **không** thêm lại các filter đó vào `HttpSecurity`.

### 6.3. Servlet registration và SecurityFilterChain order là hai thứ khác nhau

`FilterRegistrationBean.setOrder` kiểm **container chain**. `http.addFilterBefore/After` kiểm **bên trong Spring Security FilterChainProxy**. Không chỉ nhìn con số order của một CAS filter rồi suy ra nó chạy trước `AuthorizationFilter` nếu registration diễn ra ở chain khác/dispatcher type khác.

Dùng startup logs có giới hạn, `FilterChainProxy` debug traces đã sanitize và integration test thực để xác định:
- SLO callback vào đúng filter một lần.
- CAS ticket được validate một lần.
- Protected route kiểm principal + local roles.
- Session invalidation và SecurityContext clear.
- Failure không tạo anonymous→authenticated context sai.
- Không có infinite redirect chain.

## 7. Spring Security CAS: khi không dùng full Apereo filter stack

Nếu ứng dụng đã dùng `spring-security-cas` và Spring `SecurityContext` làm nguồn xác thực/authorization, hãy giữ nhất quán mô hình:

```text
Spring Security FilterChainProxy
  |
  +-- CAS entry point redirects to CAS /login?service=...
  +-- CasAuthenticationFilter receives ticket at callback
  +-- CasAuthenticationProvider validates ticket
  |     via CAS TicketValidator (Apereo client API)
  +-- creates authenticated CasAuthenticationToken
  +-- local authorities / role mapping
  +-- SecurityContext/session
```

Các classes được Spring Security CAS docs mô tả:

- `org.springframework.security.cas.web.CasAuthenticationFilter`;
- `org.springframework.security.cas.authentication.CasAuthenticationProvider`;
- `org.springframework.security.cas.web.CasAuthenticationEntryPoint`;
- `org.springframework.security.cas.ServiceProperties`;
- `org.apereo.cas.client.validation.Cas20ServiceTicketValidator` và các TicketValidator khác.

Đây là **khác** với `org.apereo.cas.client.authentication.AuthenticationFilter`; cùng tên “CAS authentication” nhưng owner/request chain khác nhau.

### 7.1. Những điểm cần cấu hình lại

1. `CasAuthenticationEntryPoint` dùng đúng `loginUrl` của CAS server và `ServiceProperties.service` URL canonical.
2. `CasAuthenticationFilter` chỉ xử lý **đúng callback path** đã đăng ký và chuyển service ticket cho `AuthenticationManager`.
3. `CasAuthenticationProvider` dùng `TicketValidator` tới **trusted CAS server** qua HTTPS, cùng service URL và registered service.
4. `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` (theo release) ánh xạ CAS principal/attributes sang local authorities; không mặc định trust một email.
5. Local account LOCKED/DISABLED và tenant roles vẫn phải được enforce sau ticket validation.
6. `SecurityContextRepository`, session fixation protection và `LogoutFilter` hoạt động tương thích với Spring Security version.
7. CAS `SingleSignOutFilter` (nếu cần) có thể được đặt ngoài/trước auth chain theo documented integration; kiểm session indexing và listener.
8. Không giữ thêm Apereo `AuthenticationFilter` + `TicketValidationFilter` trên đúng callback đang do Spring CAS filter xử lý.

### 7.2. Vì sao không copy XML namespace config của Spring Security 3.x?

Tài liệu Spring Security CAS có các snippet kiểu:

```xml
<security:http entry-point-ref="casEntryPoint">
  <security:custom-filter position="CAS_FILTER" ref="casFilter"/>
</security:http>
```

Đây là syntax XML cấu hình Spring Security lịch sử, **không** phải mẫu bắt buộc để dùng Spring Security 6/7; tên classes/Jakarta dependencies phải kiểm đúng release. Không lấy dependency `cas-client-core:3.1.12` trong một bảng docs lịch sử làm bản chuẩn trên Boot 4. Cần chạy compile/integration tests để xác nhận module `spring-security-cas` hỗ trợ exact Spring Security major đang dùng.

### 7.3. Tương thích Spring Security CAS và Apereo phiên bản

Spring Security CAS sử dụng các APIs của Java CAS client trong ticket validation. Khi nâng đồng thời Spring 5→6/7 và CAS client 3→4, nguy cơ **binary incompatibility** đến từ:
- Package `javax.servlet` vs `jakarta.servlet` trong implementation/filters.
- API signatures/constructors khác giữa Apereo 3.x/4.x.
- Spring Security filter/session repository APIs thay đổi.
- Transitive Spring dependencies bị override.
- Startup container registries có filter trùng.

Vì vậy cần **dependency convergence, compile và integration test trên thực artifact**, không chỉ dựa trên docs text. Nếu module CAS cụ thể không chạy với stack mới, cân nhắc dùng Apereo Jakarta servlet filters thuần + thiết kế bridge đã kiểm soát, hoặc kế hoạch federation sang OIDC/SAML2. Đừng tạo một custom filter “chỉ tin ticket string” để vượt qua validator.

## 8. CAS service URL phải khớp từ đầu đến cuối

### 8.1. Luồng CAS service ticket

```text
Browser -> SP /reports
  SP redirects -> https://sso.example.org/cas/login
       ?service=https%3A%2F%2Fportal.example.org%2Fcas%2Fcallback

CAS authenticates user
  CAS issues one-time Service Ticket ST-X
  CAS redirect ->
       https://portal.example.org/cas/callback?ticket=ST-X

SP TicketValidator (server-to-server HTTPS)
  GET https://sso.example.org/cas/p3/serviceValidate
      ?service=https%3A%2F%2Fportal.example.org%2Fcas%2Fcallback
      &ticket=ST-X

CAS returns valid principal/attributes for matching service
  SP establishes local authentication/session
```

Endpoint `/p3/serviceValidate` chỉ là ví dụ CAS 3 protocol; CAS 2 có `/serviceValidate`, CAS 1 có `/validate`, proxy validation có `/proxyValidate` tùy validator/protocol. **Không hardcode endpoint khác với implementation của TicketValidator.**

### 8.2. Không chỉ hostname: service URL exact match

Một ticket được CAS cấp cho service `https://portal.example.org/cas/callback` thường **không hợp lệ** khi SP validate bằng:
- `http://portal.example.org/cas/callback` (thiếu HTTPS),
- `https://portal.example.org:443/cas/callback` (canonicalization khác theo policy),
- `https://portal.example.org/internal/cas/callback`,
- `http://127.0.0.1:8080/cas/callback`,
- `https://portal.example.org/cas/callback/` (trailing slash nếu CAS không normalize).

Service registry của CAS cũng có rules/regex và canonicalization; **test với giá trị thực đúng IdP config**, không nói mọi CAS luôn so bằng chuỗi thô trong mọi deployment.

### 8.3. Reverse proxy và forwarded headers

Ở ingress, SP thấy internal `http://pod:8080` nhưng browser dùng `https://portal.example.org`. Cấu hình `serverName` hoặc `service` theo public URL đã được phê duyệt, cùng redirect/callback và ticket validator. Nếu dùng forwarded headers, chỉ chấp nhận từ **trusted ingress** và strip user-supplied `X-Forwarded-Host/Proto`. Không cho attacker chọn service URL qua query `?service=...`.

### 8.4. Chọn một service URL cố định khi có thể

Với ứng dụng đa route, service callback canonical `/cas/callback` giảm khả năng redirect mismatch và ticket validation errors. Sau khi validate, phục hồi saved request/target theo **server-side safe redirect state**, không nhận tùy ý external URL do client khai. Nếu CAS service parameter thay đổi giữa requests do query param, cần normalization và validation nhất quán.

### 8.5. Ticket là bearer artifact, ngắn hạn và single-use

Một CAS Service Ticket có thể bị kẻ tấn công dùng nếu rò trước khi được validate. Do đó:
- Bảo vệ HTTPS, không log raw `ticket` trong access log/tracing.
- Validate chỉ với trusted CAS server và exact expected service.
- Không chấp nhận lại ticket đã sử dụng; replay phải fail.
- Sau validation, redirect sang clean URL không chứa ticket nếu client config hỗ trợ, tránh referer leaks.
- Không tạo new session dựa trên query `ticket` mà không gọi CAS TicketValidator.
- Không nhận Proxy Ticket tùy ý nếu app chỉ được phép Service Ticket.
- Không tắt hostname verification hoặc certificate validation khi CAS đổi chứng thư.

## 9. Chọn Cas20/Cas30 validation filter đúng protocol

Apereo Java CAS Client có nhiều filters:

| Filter | Mục đích |
| --- | --- |
| `Cas10TicketValidationFilter` | CAS 1.0 ticket protocol |
| `Cas20ProxyReceivingTicketValidationFilter` | CAS 2.0 ticket validation, tùy config proxy support |
| `Cas30ProxyReceivingTicketValidationFilter` | CAS 3.0 ticket validation / attributes support |
| `Cas30JsonProxyReceivingTicketValidationFilter` | CAS3 validation response dạng JSON |
| `Saml11TicketValidationFilter` | CAS-compatible SAML 1.1 validation, không phải SAML2 SSO |
| `CasJWTTicketValidationFilter` | CAS server-issued JWT ticket profile có riêng trust rules |

Tên gói Java thường là `org.apereo.cas.client.validation.*`. **Không tự đổi Cas20→Cas30** chỉ vì hệ thống nâng Java; protocol response parser và IdP server capabilities phải khớp.

### 9.1. Ví dụ init params

```properties
casServerUrlPrefix=https://sso.example.org/cas
serverName=https://portal.example.org
redirectAfterValidation=true
useSession=true
exceptionOnValidationFailure=true
```

Các tên property trên đến từ Apereo CAS client filter documentation; đánh giá lại defaults cho version cụ thể. `redirectAfterValidation` hỗ trợ clean ticket URL; `useSession` lưu assertion vào HttpSession nếu bật. Nếu chạy sau một reverse proxy, test URL thật và forwarded headers.

### 9.2. Proxy ticket đặc biệt nguy hiểm khi mở rộng trust

Một ứng dụng chỉ cần login không nên bật `acceptAnyProxy=true`. Khi business cần PGT/PT:
- Xác định trusted proxy chain/`allowedProxyChains`.
- `proxyCallbackUrl` phải HTTPS public đúng, phù hợp `proxyReceptorUrl`.
- Backend validator verify proxy chain/PGT và callback ownership.
- PGT state lưu ở protected store, TTL và revocation rõ.
- Test invalid/unapproved proxy chain bị reject.
- Không đưa PGT/PT vào logs hoặc client-side storage.

### 9.3. Đừng nhầm CAS SLO với SAML2 SLO

Apereo CAS `SingleSignOutFilter` có thể xử lý `logoutRequest` callback; CAS logout message có thể sử dụng XML/SAML namespace trong payload tùy profile, nhưng đó là **CAS protocol logout integration**, không tự động phải cấu hình Spring Security `saml2Logout()`. Chọn SLO handler tương ứng đúng CAS client/IdP config; chỉ cho authenticated/trusted SLO event invalidation.

## 10. Single Sign-Out: thứ tự filter và listener là bảo vệ trạng thái

### 10.1. CAS client SLO components

Apereo documentation hướng dẫn:
- `org.apereo.cas.client.session.SingleSignOutFilter` xử lý CAS server logout callbacks và session mapping.
- `org.apereo.cas.client.session.SingleSignOutHttpSessionListener` dọn mapping khi HttpSession bị invalidated/expired.
- `SingleSignOutFilter` phải được đặt **trước các CAS web filters khác** nếu dùng Servlet filters.

```text
Browser / CAS server
    |
    v
SingleSignOutFilter
    |  tracks CAS ticket->HttpSession, detects logoutRequest
    v
AuthenticationFilter
    |
    v
Cas30...TicketValidationFilter
    |
    v
Request wrapper / app / Spring Security policies
```

Nếu SLO nằm sau authentication filter, một server-to-server logout POST **có thể bị chuyển hướng tới CAS login** trước khi SLO xử lý. Nếu SLO đứng sau body-consuming filter, callback XML có thể không đọc được. Đừng coi “filter đã tồn tại trong Spring context” là đã được container gọi đúng order.

### 10.2. Listener chỉ dọn mapping, không thay filter

Nếu `SingleSignOutFilter` có bảng ticket→session, listener giúp cleanup khi session expired. Nhưng tự đăng ký listener **không** xử lý inbound SLO. Ngược lại, chỉ đăng ký filter mà thiếu listener có thể gây stale mapping/memory leak theo implementation. Test cả hai.

### 10.3. logoutCallbackPath

Apereo Client hỗ trợ init param `logoutCallbackPath` để xác định đường dẫn nhận logout callback. Nếu ứng dụng có controllers khác cần đọc raw request body, việc scope chính xác callback giúp tránh filter can thiệp mọi POST. Chọn path thật được CAS server dùng; test callback đến qua ingress, đúng HTTP method/content type/charset, và không yêu cầu user browser session cookie.

### 10.4. CSRF: không tắt bảo vệ toàn bộ POST

User-initiated local logout từ browser nên dùng **POST + valid CSRF** nếu ứng dụng dùng cookie sessions. Nhưng CAS server-to-server SLO callback không có CSRF token trình duyệt. Do đó có thể cần **ngoại lệ CSRF hẹp cho endpoint SLO** đã được bảo vệ bằng **kiểm tra CAS logout request hợp lệ** và các security controls tương ứng (source/trust/protocol handling). Không viết `csrf.disable()` toàn ứng dụng hoặc miễn `/logout/**` một cách tùy tiện.

Nếu `SingleSignOutFilter` ở container chain chạy trước Spring Security và consume SLO callback đúng cách, có thể không cần đi qua controller/CSRF filter ở cùng cách; **integration test thực** thay vì tự suy. Một endpoint CSRF-exempt không có xác minh logout request là điểm có thể bị lợi dụng để ép người khác logout (logout CSRF).

### 10.5. CAS logout message phải đáng tin

SLO qua back-channel có thể nhận XML `logoutRequest`. Đừng lấy một `SessionIndex` hoặc ticket ID trong **raw unauthenticated HTTP POST** rồi xoá bất kỳ session nếu implementation không kiểm tính hợp lệ/nguồn của logout message. Cần review CAS client/version, CAS server configuration, request provenance, binding, replay và network/TLS trust; message-validation semantics khác SAML2 SLO signature profiles. Đừng đưa giả định “CAS SLO luôn có chữ ký XML như SAML2 LogoutRequest” vào code.

### 10.6. Multi-node SLO

Nếu ứng dụng có nhiều pods và CAS SLO callback đến node B nhưng ticket/session mapping nằm trong memory node A, node B có thể không tìm session để invalidate. Spring Session Redis có thể chia sẻ HttpSession **theo session ID**, nhưng không tự động bảo đảm Apereo CAS client SLO ticket mapping phân tán.

Kiểm:
- SingleSignOutFilter session mapping store có shared implementation phù hợp hoặc callback routing/architecture bảo đảm.
- Ticket/identifier index → **các active HttpSession IDs** theo policy, không chỉ current request.
- Session ID rotation/fixation update mappings.
- Session expiry/cleanup và Redis failover.
- Không xóa sessions của user khác dựa trên email/username.
- CAS logout should invalidate local sessions across nodes and older browser cookies fail after callback.
- Không phát false “global logout complete” khi session vẫn active.

**Lưu ý:** distributed proxy ticket cache/Ehcache/Memcached modules của CAS client không mặc nhiên là replacement cho **CAS SLO session mapping**; kiểm API/implementation thực của module đã chọn.

## 11. Request wrapper, thread-local assertion và dispatch

### 11.1. Wrapper filter

`HttpServletRequestWrapperFilter` của CAS client có thể cung cấp một wrapped request exposing CAS-authenticated principal theo Servlet API. Nếu ứng dụng Spring Security đã dùng `SecurityContext` riêng, cần quyết định cách bridge. Một CAS validated principal từ HttpServletRequest **không tự trở thành Spring `Authentication` có local authorities**.

**Ranh giới tin cậy:** Chỉ map principal sau khi CAS TicketValidator đã xác minh ticket; không tin request parameter `user` hoặc HTTP header `X-CAS-User` từ client internet.

### 11.2. AssertionThreadLocalFilter

Một số legacy app dùng `AssertionThreadLocalFilter` để truy cập CAS Assertion trong request thread. Nếu chuyển sang Jakarta app / async servlet / reactive executor / thread pools:
- ThreadLocal không tự propagate sang new threads.
- ThreadLocal cần cleanup đúng khi request xong để tránh leak user context giữa requests.
- Không tự giữ assertion trong static ThreadLocal dài hạn.
- Tránh dùng global thread-local làm primary authority source cho async jobs.
- Test exceptions, error dispatch, async request, executor handoff nếu có dùng.

### 11.3. Dispatcher types

Filter registration có dispatcher type như `REQUEST`, `FORWARD`, `ERROR`, `ASYNC`. Khi mapping thay đổi sau Boot migration, một filter có thể:
- không chạy ở callback vì dispatcher type khác,
- chạy lại ở error/forward gây login loop,
- nuốt form POST body khi SLO parse,
- làm authenticated principal không có ở async continuation.

Không bật mọi dispatcher type bừa bãi. Xem protocol entrypoints, filter-specific expectations, Spring Boot defaults và test actual deployed container.

## 12. Filter order khi kết hợp Spring Security

### 12.1. Các chain khác nhau

```text
Embedded Servlet container:
   [CharacterEncodingFilter]
   [Apereo CAS SLO filter]
   [Apereo CAS auth/validation filters (IF strategy A)]
   [springSecurityFilterChain / DelegatingFilterProxy]
       -> Spring Security FilterChainProxy
          SecurityContextHolderFilter / authentication filters
          ... AuthorizationFilter
   [DispatcherServlet]
```

**Đây là layout giải thích**, thứ tự chính xác phụ thuộc registration và framework. Nếu Spring Security CAS là **strategy B**, `CasAuthenticationFilter` nên nằm **trong SecurityFilterChain**; Apereo authentication/validation filters không được song song xử lý cùng ticket.

### 12.2. Double registration thường gây lỗi gì?

- `ticket=ST-X` được consume hai lần: CAS trả “INVALID_TICKET”.
- Browser bị redirect lặp CAS login dù CAS session còn valid.
- Một filter đặt principal trong HttpSession nhưng Spring Security load context cũ/anonymous.
- SecurityContext được ghi rồi filter thứ hai xóa/replace.
- SLO callback không được match do outer filter đi redirect.
- Controller thấy request user nhưng `Authentication` vẫn anonymous.
- Cùng filter chạy trên ERROR/FORWARD lần nữa và nổ.
- Startup log báo hai registrations cùng URL pattern.

**Test được:** instrument một CAS callback ở test environment, đếm mỗi CAS TicketValidator call và filter invocation; yêu cầu **một validation thành công cho mỗi ST** và không có duplicate CAS auth ownership.

### 12.3. FilterRegistrationBean disabled khi filter nằm trong HttpSecurity

Nếu bạn chọn thêm một `Filter` vào `HttpSecurity` và để nó là Spring Bean, Boot có thể tự container-register. Cần dùng `FilterRegistrationBean#setEnabled(false)` nếu không muốn container registration; còn việc thêm filter vào SecurityFilterChain phải do `HttpSecurity.addFilterBefore/After` đúng anchor filter trong release.

Không cố dùng cùng filter instance theo hai pathways chỉ để “đề phòng” callback bị bỏ sót. Đây là nguồn bugs và bypass order khó nhìn.

## 13. Session, Cookie, CORS và CSRF sau migration

### 13.1. CAS SSO thường cần browser session

CAS service ticket login có thể tạo `HttpSession` chứa authenticated assertion/Spring SecurityContext. Sau chuyển sang Jakarta:
- `HttpSession` type là `jakarta.servlet.http.HttpSession`.
- Session cookie có thể là `JSESSIONID` hoặc `SESSION` với Spring Session.
- `SameSite`, Secure, HttpOnly, Path/Domain cần kiểm với browser thật.
- HTTPS redirect từ CAS server về service callback phải giữ đúng cookie nếu cần saved request.
- Session fixation protection có thể đổi session ID sau login.
- Logout/SLO cần invalidate đúng session ID, kể cả node change.

### 13.2. CAS ticket không phải CSRF token

Một `ticket` là một bearer proof từ CAS server, không thay browser CSRF state/session binding cho tất cả endpoints. Các business POST vẫn cần CSRF protection với cookie-authenticated app. Với CAS callback, thiết kế chống login CSRF/session fixation và service validation; CAS-specific callback có thể khác OIDC `state` nhưng không có nghĩa có thể bỏ mọi browser-flow checks.

### 13.3. Cookie SameSite và cross-site redirects

CAS browser login truyền người dùng qua IdP domain. Callback thường là top-level GET với service ticket, trong trường hợp đó SameSite=Lax có behavior thuận lợi hơn cross-site POST. Tuy nhiên use cases gateway/gateway=true, AJAX, browser blocking và cookie Domain/Path có thể ảnh hưởng. Không set SameSite=None chỉ vì thấy lỗi 302; kiểm callback method/browser behavior, rồi chọn cookie policy có CSRF controls tương ứng.

### 13.4. CORS không sửa được redirect login

Một SPA gọi protected API bằng `fetch` và nhận 302 đến CAS login có thể bị CORS error ở browser; “cho phép * mọi origin” không phải giải pháp. Dùng BFF/server-side session login redirect hoặc protocol API phù hợp, frontend điều hướng top-level khi cần. CAS client filter dành cho servlet/browser flows, không phải mọi XHR endpoint.

## 14. SSL/TLS, secrets và giới hạn tin cậy

### 14.1. Back-channel ticket validation

`TicketValidator` gọi CAS server bằng HTTPS. Production:
- Tin đúng server TLS certificate chain và hostname.
- Không disable certificate checks khi CA đổi.
- Giới hạn timeout, redirects và response size; tránh treo filter threads.
- Chỉ cấu hình CAS server URL do admin approve, không dùng user query param.
- Không log raw service ticket, PGT, session cookies, CAS attributes nhạy cảm.
- Kiểm XML parser XXE/DTD/oversized responses với dependency version an toàn.
- Proxy settings và egress policy chặn kết nối tới host ngoài allowlist.

### 14.2. Service URL và Host header spoofing

Nếu service URL tự build từ `Host` hoặc `X-Forwarded-Host` chưa được ingress sanitize, attacker có thể làm redirect/validator chọn service khác. Đặt canonical public URL hoặc trusted forwarded-header config. CAS registered service rules cần chặt và không dùng broad regex cho mọi domain.

### 14.3. Proxy granting ticket

Nếu dùng PGT, `pgtUrl`/`proxyCallbackUrl` có thể tạo inbound callback từ CAS server; identity phải được ràng buộc với service và allowed proxy chain. Đừng set `acceptAnyProxy` không kiểm soát, không mở host verifier wildcard và không giữ PGT trong DB/log vô hạn.

### 14.4. Dependency scanning

Sau migration, chạy SCA/CVE scan của:
- `cas-client-core`;
- Spring Security/Boot/Web;
- XML parsing/security dependencies;
- Commons Codec/SLF4J;
- embedded servlet container;
- cache/session libraries.

Một bản “Jakarta-compatible” không đồng nghĩa là mới nhất hoặc đã vá mọi CVE. Xác minh vulnerabilities theo deployed dependency tree, không tin một con số version đơn lẻ từ bài viết.

## 15. Quy trình nâng cấp an toàn theo từng đợt

### Phase 0 — Đóng băng hành vi hiện tại

- Ghi baseline flows: browser CAS login, renew/gateway, ticket validate, logout local, CAS SLO, proxy ticket (nếu có).
- Ghi public service URL và CAS server registered service rules.
- Chụp dependency graph, filter order/registrations, session behavior (không lưu raw ticket).
- Định nghĩa acceptance criteria và kiểm bảo mật hiện tại.
- Đánh dấu owner của authentication/authorization/Session/SLO.

### Phase 1 — Chọn target platform

- Nếu Java 17/Boot 3: thử CAS client Jakarta 4.0.x và compatibility/security matrix.
- Nếu Java 21/Boot 4: thử CAS client Jakarta 4.1.x và Boot 4 support.
- Nếu application có `spring-security-cas`: khóa một tương thích module/provider và không tự thêm Apereo filters vào callback.
- Nếu muốn protocol replacement OIDC: thực hiện thành initiative riêng, có data/identity account linking migration.

### Phase 2 — Dependency migration

- Update CAS modules đồng bộ.
- Dùng `jakarta.servlet-api` từ Boot/container; bỏ `javax.servlet-api` khỏi runtime.
- Chuyển custom filters/listeners/imports.
- Fix `@WebFilter`/`@WebListener` nếu dùng.
- Kiểm XML descriptors và deployment WAR.
- Maven/Gradle dependency convergence; fail khi legacy modules còn tồn tại.

### Phase 3 — Filter registration

- Chọn web.xml **hoặc** FilterRegistrationBean **hoặc** Apereo Boot auto registration.
- Một owner CAS login/ticket validation; tránh Spring CAS + Apereo auth double path.
- SLO filter đứng sớm theo CAS docs, listener registered.
- Wrapper/thread-local nếu ứng dụng cần.
- Đúng URL patterns/dispatcher types, không bảo vệ /actuator bằng login redirect ngoài dự kiến.
- Test filter order bằng real embedded container, không chỉ unit Java.

### Phase 4 — Secure CAS ticket validation

- Cấu hình trusted CAS server URL/TLS/hostname.
- Canonical service URL chung browser login và back-channel validation.
- Bật đúng protocol validator; proxy chain allowlist nếu có.
- Ticket single-use, redirectAfterValidation/clean URL policy.
- Map CAS principal vào local account/authorities có kiểm tra trạng thái.
- Bảo vệ user logout POST/CSRF, khóa SLO callback riêng và validate legitimacy.

### Phase 5 — Session/SLO/cluster

- Verify session cookie behavior/Session fixation.
- CAS SLO back-channel callback hoạt động **không có browser cookie**.
- Listener cleanup đúng; session invalidated ở mọi nodes nếu HA.
- Redis/shared session mapping nếu architecture cần, chứ không giả định Spring Session tự chia CAS SLO map.
- Revoke old sessions khi user disabled/locked theo policy.
- Không đưa raw ST/PGT/NameID vào logs/metrics.

### Phase 6 — Canary và rollback

- Deploy canary với một phần users; capture safe reason codes.
- So tỉ lệ CAS login/validation fail, latency, redirect loops và SLO misses với baseline.
- Test cross-version deployment nếu shared sessions/serialized data, không blind rolling deploy.
- Kiểm backward-compatible session representation và TTL; có thể cần controlled re-login.
- Chuẩn bị rollback target gồm app version, CAS registered service, config secrets và domain/cookie behavior.
- Không rollback về `javax.servlet` artifact trong Jakarta runtime; rollback phải coherent full stack.

## 16. Java 17 demo độc lập: audit cấu hình migration trước khi deploy

Ví dụ sau là **bộ kiểm tra quy tắc tĩnh** bằng Java 17, không cần Spring/Jakarta CAS dependencies và không tạo real HttpSession. Nó mô hình hóa `Deployment` và phát hiện:

- CAS client 3.x/Jakarta: không tương thích.
- CAS client 4.1.x chạy Java 17: baseline Java thấp.
- Runtime còn `javax.servlet`: namespace mix-up.
- Filter auth/validate/SLO bị đăng ký trùng.
- Đồng thời bật Apereo auth filters và Spring Security CAS auth cho same callback.
- SingleSignOutFilter đứng sau authentication filter.
- Thiếu SLO HttpSessionListener.
- service URL của browser khác expected canonical URL.

Giới hạn: tên filters trong demo là các **nhãn cấu hình** (không phải actual servlet Filter objects). Nó không đọc `pom.xml`/`web.xml`, không chứng minh compatibility/safe parsing, không gọi CAS server, không verify ticket/XML signature hoặc test SecurityContext. Đầu ra là một **checklist executable**, không phải security verifier.

Lưu file `CasJakartaMigrationAudit.java`:

```java
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public class CasJakartaMigrationAudit {

    private static final String EXPECTED_SERVICE =
            "https://portal.example.org/cas/callback";

    record Deployment(
            String clientVersion,
            int jdk,
            int servletMajor,
            boolean hasJavaxServlet,
            boolean hasJakartaServlet,
            List<String> filters,
            boolean hasSloListener,
            boolean twoAuthStacks,
            String serviceUrl) {}

    static String audit(Deployment deployment) {
        String version = deployment.clientVersion();
        if (version.startsWith("3.")) {
            return "FAIL_LEGACY_CAS_CLIENT";
        }
        if (!version.startsWith("4.0.")
                && !version.startsWith("4.1.")) {
            return "FAIL_UNKNOWN_VERSION";
        }

        int requiredJdk = version.startsWith("4.1.") ? 21 : 17;
        if (deployment.jdk() < requiredJdk) {
            return "FAIL_JDK_BASELINE";
        }
        if (deployment.servletMajor() < 6) {
            return "FAIL_SERVLET_GENERATION";
        }
        if (deployment.hasJavaxServlet()
                || !deployment.hasJakartaServlet()) {
            return "FAIL_SERVLET_NAMESPACE";
        }

        Set<String> unique = new HashSet<>(deployment.filters());
        if (unique.size() != deployment.filters().size()) {
            return "FAIL_DUPLICATE_FILTER";
        }
        if (deployment.twoAuthStacks()) {
            return "FAIL_DUAL_AUTH_STACK";
        }

        List<String> filters = deployment.filters();
        int slo = filters.indexOf("slo");
        int auth = filters.indexOf("auth");
        int validate = filters.indexOf("validate");

        if (slo < 0 || auth < 0 || validate < 0) {
            return "FAIL_INCOMPLETE_CHAIN";
        }
        if (slo > auth || slo > validate) {
            return "FAIL_SLO_FILTER_ORDER";
        }
        if (!deployment.hasSloListener()) {
            return "FAIL_SLO_LISTENER";
        }
        if (!EXPECTED_SERVICE.equals(deployment.serviceUrl())) {
            return "FAIL_SERVICE_URL";
        }
        return "PASS";
    }

    static Deployment baseline() {
        return new Deployment(
                "4.0.4", 17, 6, false, true,
                List.of("slo", "auth", "validate"),
                true, false, EXPECTED_SERVICE);
    }

    static Deployment copy(
            Deployment base, String version, int jdk,
            boolean hasJavax, List<String> filters,
            boolean listener, boolean twoStacks,
            String serviceUrl) {
        return new Deployment(
                version, jdk, base.servletMajor(),
                hasJavax, base.hasJakartaServlet(), filters,
                listener, twoStacks, serviceUrl);
    }

    static void check(String name, Deployment deployment) {
        System.out.println(name + ": " + audit(deployment));
    }

    public static void main(String[] args) {
        Deployment base = baseline();

        check("Boot3 Java17 CAS4.0", base);
        check("Legacy CAS3 on Jakarta",
                copy(base, "3.6.4", 17, true,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("CAS4.1 on Java17",
                copy(base, "4.1.1", 17, false,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Boot4 Java21 CAS4.1",
                copy(base, "4.1.1", 21, false,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Mixed javax and jakarta",
                copy(base, "4.0.4", 17, true,
                    base.filters(), true, false, EXPECTED_SERVICE));
        check("Duplicate auth filter",
                copy(base, "4.0.4", 17, false,
                    List.of("slo", "auth", "validate", "auth"),
                    true, false, EXPECTED_SERVICE));
        check("Two authentication stacks",
                copy(base, "4.0.4", 17, false,
                    base.filters(), true, true, EXPECTED_SERVICE));
        check("SLO runs too late",
                copy(base, "4.0.4", 17, false,
                    List.of("auth", "slo", "validate"),
                    true, false, EXPECTED_SERVICE));
        check("Missing SLO listener",
                copy(base, "4.0.4", 17, false,
                    base.filters(), false, false, EXPECTED_SERVICE));
        check("Wrong service URL",
                copy(base, "4.0.4", 17, false,
                    base.filters(), true, false,
                    "http://pod:8080/cas/callback"));
        check("Missing validation filter",
                copy(base, "4.0.4", 17, false,
                    List.of("slo", "auth"),
                    true, false, EXPECTED_SERVICE));
    }
}
```

Chạy trên JDK 17 hoặc JDK mới hơn:

```bash
javac CasJakartaMigrationAudit.java
java CasJakartaMigrationAudit
```

Stdout **chính xác**:

```text
Boot3 Java17 CAS4.0: PASS
Legacy CAS3 on Jakarta: FAIL_LEGACY_CAS_CLIENT
CAS4.1 on Java17: FAIL_JDK_BASELINE
Boot4 Java21 CAS4.1: PASS
Mixed javax and jakarta: FAIL_SERVLET_NAMESPACE
Duplicate auth filter: FAIL_DUPLICATE_FILTER
Two authentication stacks: FAIL_DUAL_AUTH_STACK
SLO runs too late: FAIL_SLO_FILTER_ORDER
Missing SLO listener: FAIL_SLO_LISTENER
Wrong service URL: FAIL_SERVICE_URL
Missing validation filter: FAIL_INCOMPLETE_CHAIN
```

### 16.1. Diễn giải

- `Boot3 Java17 CAS4.0: PASS`: một tổ hợp qua được **audit tĩnh đơn giản**, không có nghĩa build/runtime chắc chắn tương thích; vẫn cần integration test.
- `Legacy CAS3 on Jakarta` bị từ chối vì CAS 3.x dựa vào `javax.servlet`.
- `CAS4.1 on Java17` bị từ chối theo baseline Java 21 công bố của CAS client 4.1.x.
- `Mixed javax and jakarta` là lỗi ngay cả khi CAS 4.0.x đã được chọn.
- `Duplicate auth filter` bắt việc register cùng một filter hai lần.
- `Two authentication stacks` bắt double CAS ticket processing giữa Apereo auth/validation và Spring Security CAS.
- `SLO runs too late`: SLO phải được nhận trước các CAS web filters theo docs Apereo.
- `Missing SLO listener`: thiếu lifecycle cleanup theo cách CAS client đang dùng.
- `Wrong service URL`: browser callback/public service khác cấu hình; trong hệ thống thật service ticket sẽ bị CAS từ chối theo registry/validation rules.
- `Missing validation filter`: không có đường kiểm CAS ticket; **không** bao giờ coi ticket string là danh tính.

### 16.2. Giới hạn của audit demo

1. `Audit` không kiểm actual pom dependency graph, không parse bytecode hoặc XML.
2. `servletMajor=6` là tối thiểu trong demo; CAS 4.1.x build với 6.1, nên deployment thật cần kiểm **minor version** và class APIs; demo không xác nhận điều đó.
3. Không xác minh Spring Security CAS module behavior hoặc filter-chain ordering bên trong Spring.
4. Không kiểm TLS CA/hostname, CAS registered service, single-use ticket, SLO authenticity, listener callback coverage.
5. Không phát hiện CAS 4.0.x patch nào có security advisories.
6. Không tính WAR vs JAR và class-loader/container differences.
7. Không kiểm proxy policy, CSRF, session cookie, multi-node SLO mapping.
8. `twoAuthStacks` là boolean đã được người dùng demo cung cấp; production phải scan actual registration.
9. Không bảo đảm SLO listener đúng khi deployed; phải làm integration tests.
10. Chính sách kiểm Java theo version được minh họa bằng 4.0.x/4.1.x; **các nhánh tương lai cần xác minh POM thực**.

## 17. Kiểm thử nâng cấp: unit, integration, browser và cluster

### 17.1. Dependency/API tests

| Test ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| DEP-01 | Boot 3/JDK 17, CAS client 4.0.x Jakarta | Compile + start container khi versions đã verify |
| DEP-02 | Boot 3/JDK 17, CAS client 3.x javax | CI FAIL, không đóng gói release |
| DEP-03 | Boot 4/JDK 21, CAS client 4.1.x | Compile + SSO integration pass |
| DEP-04 | Boot 3/JDK17 + cas-client-core 4.1.1 | Reject incompatible Java bytecode |
| DEP-05 | Runtime có cả `javax.servlet.Filter` và Jakarta Filter trong pipeline | Fail migration gate |
| DEP-06 | Filter custom import `javax.servlet` | Compile gate phát hiện |
| DEP-07 | WAR bundling duplicate servlet-api implementation | Fail deployment review |
| DEP-08 | `cas-client` POM aggregator tưởng là filter JAR | Fail dependency resolution/class existence |
| DEP-09 | Spring Security CAS module kéo Apereo client cũ | Dependency convergence fail |
| DEP-10 | Boot starter + FilterRegistrationBean cùng CAS auth filter | Duplicate registration test fails |

### 17.2. Filter lifecycle/order tests

| ID | Scenario | Kỳ vọng |
| --- | --- | --- |
| FIL-01 | Startup register đúng 1 SingleSignOutFilter | PASS |
| FIL-02 | SLO filter đứng trước CAS auth/validation filters | PASS |
| FIL-03 | Listener `SingleSignOutHttpSessionListener` registered 1 lần | PASS |
| FIL-04 | Double `AuthenticationFilter` hoặc `CasAuthenticationFilter` | FAIL |
| FIL-05 | Có cả Apereo CAS auth và Spring Security CAS cùng ticket callback | FAIL |
| FIL-06 | Validation filter nhận redirect callback với `ticket` | Validate một lần |
| FIL-07 | Missing validation filter | Không authenticate bằng unverified ticket |
| FIL-08 | AuthenticationFilter redirect cả CAS SLO POST | FAIL |
| FIL-09 | Invalid logoutRequest body | Không hủy arbitrary session |
| FIL-10 | Wrapped request returns trusted CAS principal | Chỉ sau successful validation |
| FIL-11 | AssertionThreadLocal giữ user sau request exception | FAIL, tránh context leak |
| FIL-12 | Async dispatch/read body | Đúng filter dispatcher & charset semantics |
| FIL-13 | Duplicate filter from @WebFilter + @Bean | FAIL |
| FIL-14 | CAS filter added to HttpSecurity but Boot also container-registers | FAIL |
| FIL-15 | Public health/actuator route bị login redirect ngoài policy | FAIL |
| FIL-16 | Unauthenticated protected route bypasses CAS unexpectedly | FAIL |

### 17.3. Ticket validation tests

| ID | Tình huống | Expected |
| --- | --- | --- |
| TKT-01 | Browser bị redirect đến CAS login với exact service | PASS |
| TKT-02 | Ticket valid và cùng service URL, đúng validator | Tạo principal/authentication |
| TKT-03 | Ticket issued to different service URL | Reject |
| TKT-04 | Ticket đã validate một lần, submit lại | Reject replay |
| TKT-05 | Ticket forged/bị đổi ký tự | Reject |
| TKT-06 | CAS server HTTPS certificate invalid | Reject; không tắt hostname verifier |
| TKT-07 | CAS server unavailable/timeouts | Fail closed, no local admin |
| TKT-08 | CAS response XML/JSON malformed | Reject/parser error sanitized |
| TKT-09 | CAS returns principal B, local link A | Không auto link theo email |
| TKT-10 | CAS principal ACTIVE nhưng local user LOCKED | RP deny theo local status |
| TKT-11 | Valid CAS principal nhưng thiếu local role | Protected endpoint deny |
| TKT-12 | Proxy ticket từ unapproved proxy chain | Reject |
| TKT-13 | `acceptAnyProxy=true` bật nhầm | Security review FAIL |
| TKT-14 | Ticket retained in browser URL after validation | Clean-url policy fail nếu không xử lý |
| TKT-15 | Valid CAS Ticket nhưng Spring SecurityContext vẫn anonymous | Integration bridge/mapping issue |
| TKT-16 | `renew=true` policy | CAS forces reauth according to validated profile |
| TKT-17 | `gateway=true` policy | Không bị redirect loop, xử lý anonymous kết quả |
| TKT-18 | Service URL dùng proxy Host giả | Reject/normalize trusted host |

### 17.4. SLO và session tests

| ID | Scenario | Expected |
| --- | --- | --- |
| SLO-01 | Local logout do user POST + CSRF | Current local session invalidated |
| SLO-02 | CAS SLO callback tới configured path | Session corresponding to ticket revoked |
| SLO-03 | SLO callback không kèm browser cookie | Server-side session mapping vẫn xử lý |
| SLO-04 | Missing SingleSignOutHttpSessionListener | FAIL lifecycle QA |
| SLO-05 | Expired HttpSession | Ticket→session mapping cleanup |
| SLO-06 | Browser giữ old cookie sau SLO | Protected endpoints deny |
| SLO-07 | CAS SLO tới pod B, original session ở pod A | Revoke nếu architecture yêu cầu HA |
| SLO-08 | Session ID rotated after login | SLO mapping updated |
| SLO-09 | Same user has two sessions | Target theo CAS logout mapping, không đoán |
| SLO-10 | SLO callback giả mạo | Không xóa sessions |
| SLO-11 | Duplicate/replayed SLO message | Idempotent/reject according to policy |
| SLO-12 | LogoutResponse/partial status không tồn tại trong CAS flow này | Không tự áp SAML2 SLO semantics |
| SLO-13 | Spring Session Redis khỏe nhưng Apereo SLO local map | Phát hiện missing distributed index |
| SLO-14 | Session expire event bị bỏ lỡ | Reaper/reconciliation cleanup |
| SLO-15 | CSRF exempt toàn `/logout/**` | Security QA FAIL |
| SLO-16 | Servlet listener đăng ký kép | Test detects duplicate lifecycle |
| SLO-17 | ThreadLocal assertion từ user A lộ sang B | Security QA FAIL |
| SLO-18 | Raw logoutRequest/ticket/sessionID trong logs | Security QA FAIL |

### 17.5. Browser, ingress và multi-region tests

| ID | Scenario | Expected |
| --- | --- | --- |
| BRI-01 | Public HTTPS URL, internal HTTP pod | CAS uses canonical public service |
| BRI-02 | Forwarded headers do attacker tự đặt | Không đổi trusted service URL |
| BRI-03 | Cookie Path khác callback | Test phát hiện mất session |
| BRI-04 | SameSite/Lax/Strict/None behavior qua CAS redirect | Theo browser flow và CSRF policy |
| BRI-05 | CAS login success trên Chrome/Firefox/mobile | Không loop |
| BRI-06 | SPA fetch theo redirect CAS login | UX BFF/top-level navigation đúng |
| BRI-07 | Two nodes có CAS client versions khác | Canary review/compatibility tests |
| BRI-08 | Redis failover giữa ticket validation và session save | Không tạo phantom auth |
| BRI-09 | Request tới node B sau login ở A | SecurityContext/session vẫn hợp lệ |
| BRI-10 | Node A restart trước CAS SLO callback | HA SLO đúng architecture |
| BRI-11 | Service ticket logging ở ingress | Redaction policy fail |
| BRI-12 | Cross-tenant CAS principals giống nhau | Local account isolation |

## 18. Failure modes và cách sửa đúng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `NoClassDefFoundError: javax/servlet/Filter` | CAS client 3.x hoặc lib khác chưa Jakarta | Đổi sang artifact Jakarta tương thích, kiểm dependency tree |
| `ClassCastException: Filter cannot be cast` | javax Filter bị nhét vào Jakarta registration | Chọn đúng CAS version; không thêm javax.servlet-api workaround |
| `UnsupportedClassVersionError` | CAS 4.1.x bytecode Java21 chạy JDK17 | Dùng JDK21/Boot4 đúng stack hoặc artifact Java17 branch |
| `BeanCreationException` filter registration | Servlet API/JDK version mismatch | Audit classloader/imports/transitives |
| Infinite CAS login redirect | Filter registered twice, wrong service URL hoặc callback bị auth filter chặn | Chọn một auth owner, so redirect/validation path |
| CAS trả INVALID_TICKET | Ticket replay, double validator, wrong service | Đếm validator calls và compare canonical service |
| CAS trả INVALID_SERVICE | Service mismatch/registry, scheme/host/path | Fix public origin/registered service config |
| 302 ngay trên SLO callback | CAS AuthenticationFilter chặn logout POST | SLO filter trước auth và scope đúng path |
| Local logout works, CAS SLO doesn't | SLO filter/listener/callback mapping missing | Test signed/trusted callback, session mapping/cluster |
| SLO chỉ hủy một node | Mapping local memory, session store không shared | Distributed revocation/session indexing |
| User principal ở request nhưng Spring Security anonymous | Apereo filter không bridge SecurityContext | Chọn Spring Security CAS hoặc validated principal bridge |
| User bị thiếu role mặc dù CAS validate OK | Local authority mapping absent/wrong prefix | Map local roles, không auto admin |
| Failed CAS login dẫn 500 lộ details | ExceptionOnValidationFailure/handlers | Sanitize failure, preserve reject |
| Browser giữ ticket trên URL | redirectAfterValidation disabled/wrong path | Clean URL sau validation |
| Service URL lộ pod HTTP URL | Proxy forwarded header trust/canonical URL | Explicit public origin, ingress sanitizer |
| Raw PGT/ticket in access logs | Query logging/tracing | Redact query keys/headers |
| SLO XML parse errors do encoding | Filter order/encoding/body read | CharacterEncodingFilter, callback path, tests |
| Build passes, startup fails WAR | Servlet API included/loader versions mismatch | Provided scope, compatible container |
| Filter chạy hai lần trong Spring Boot | Bean auto registration + HttpSecurity registration | Disable container registration for SecurityFilterChain-owned filters |
| CI tests all pass but logout fails in cluster | Mocks không dùng actual HttpSession on two pods | HA SLO integration and chaos tests |

## 19. Runbook nâng cấp và triển khai

### 19.1. Trước release

1. Chốt một target JDK/Boot/CAS client version và approval list.
2. Verify active CAS server endpoint, registered service rules và TLS certificate chain.
3. Review dependency tree: không có obsolete servlet filters, không mix APIs.
4. Review filter chain registrations và expected order.
5. Test positive CAS login với real CAS test server và role mapping.
6. Test same ticket replay, wrong service, TLS failure.
7. Test local logout/IdP CAS SLO callback không có browser cookie.
8. Test canary cross-node sessions và SLO if HA required.
9. Verify no raw ticket/PGT/NameID in logs.
10. Có rollback **coherent** (không dùng javax JAR trên Jakarta runtime).

### 19.2. Trong canary

- Monitor `cas_login_redirect_total`, `cas_ticket_invalid_total`, `cas_service_mismatch_total`, `cas_slo_callback_total` và `cas_slo_revocation_fail_total`.
- Thêm `filter_registration_duplicate_total` hoặc startup assertion expected count.
- Theo dõi timeouts/back-channel latency, CAS server HTTP errors.
- So session invalidation/expiry và 403 local authorization after authentication.
- Không dùng email, raw ticket hoặc session cookie làm metric labels.
- Nếu thấy `INVALID_TICKET` sau một success, nghi double validation; kiểm duplicates trước khi nới trust.
- Nếu SLO suddenly 302 tới login, kiểm filter order.
- Roll back toàn bộ version/config khi symptom vượt threshold, không disable TLS/callback checks.

### 19.3. Sau release

1. Rà Spring Boot runtime dependency tree thực được đóng gói.
2. Giữ canary tests sau khi traffic shift nhiều nodes.
3. Kiểm user logged in trước deploy bị logout theo expected policy; không silent share stale session contexts.
4. Test active account lock and CAS SLO from test IdP.
5. Kiểm listener lifecycle và stale indexes, cache memory growth.
6. Scan CVEs và security advisories sau mỗi patch upgrade.
7. Ghi migration decision record: chọn strategy nào, why, source links, owner/rollback.

## 20. Checklist production

- [ ] Có inventory JDK, Spring Boot, Spring Security, Servlet container, CAS client và topology.
- [ ] Target CAS client là Jakarta-compatible **và** chạy trên JDK đang deploy.
- [ ] Boot 3/Java17 đánh giá CAS client 4.0.x; Boot 4/Java21 đánh giá 4.1.x.
- [ ] Dependencies không chứa `javax.servlet-api` legacy trong Jakarta web request pipeline.
- [ ] Custom filters/listeners dùng `jakarta.servlet.*`.
- [ ] Không blind replace `javax.crypto` hoặc `javax.net.ssl`.
- [ ] WAR descriptor/schema theo Jakarta servlet container, API scope đúng.
- [ ] Chọn duy nhất một CAS authentication strategy (Apereo filters/Spring Security CAS).
- [ ] Không đăng ký filter trùng bằng web.xml, @WebFilter, FilterRegistrationBean, @EnableCasClient hoặc HttpSecurity.
- [ ] SingleSignOutFilter đứng trước các CAS filters theo docs; listener registered một lần.
- [ ] Charset/callback path/dispatcher types cho SLO được kiểm thực.
- [ ] Service URL canonical public HTTPS đúng browser redirect và CAS validation.
- [ ] CAS server registered service, trusted TLS, exact ticket validation path đúng protocol.
- [ ] Ticket được validate một lần, có replay negative test.
- [ ] Không mở acceptAnyProxy nếu không có proxy trust policy.
- [ ] CAS principal/attributes được đưa tới local role/locked status gate an toàn.
- [ ] Spring SecurityContext không bị bypass/double processed.
- [ ] Local logout từ browser POST có CSRF; CAS SLO callback xử lý riêng có trusted checks.
- [ ] SLO invalidates right HttpSessions và cleanup mappings, kể cả failover nếu HA.
- [ ] Session fixation, Redis/Spring Session, SameSite/Domain/Path được test.
- [ ] Ingress forwarded headers được trust only from proxy; không Host spoofing.
- [ ] Không ghi ticket, PGT, session IDs, raw logoutRequest, password hoặc PII vào logs.
- [ ] Migrations có JUnit/integration/browser/multi-node tests và canary rollback.
- [ ] Security advisories và dependency convergence được review trước release.
- [ ] Java17 runnable audit demo đã chạy để hiểu version, filter chain và service URL policy.

## 21. Câu hỏi ôn tập

**1. Vì sao không thể dùng CAS Client 3.x trong Spring Boot 3 chỉ bằng đổi import ở project?**  
Vì JAR của client cũ đã biên dịch với `javax.servlet.Filter`; Servlet container Jakarta yêu cầu `jakarta.servlet.Filter`, hai kiểu không tương thích.

**2. CAS Java Client 4.0.4 và 4.1.1 cùng chạy Java17 không?**  
Không. POM được kiểm cho 4.0.4 dùng baseline Java17; 4.1.1 đặt baseline Java21.

**3. Thư viện Maven nào chứa core filters?**  
`org.apereo.cas.client:cas-client-core`, không phải chỉ artifact aggregator `cas-client` loại POM.

**4. Cần đổi `javax.crypto` thành `jakarta.crypto` không?**  
Không. `javax.crypto` thuộc Java SE; thay namespace kiểu đó là sai.

**5. SingleSignOutFilter nên đặt ở đâu?**  
Trước các CAS web filters khác theo Apereo README; filter/listener cần được đăng ký theo một chiến lược nhất quán.

**6. Có nên bật `AuthenticationFilter` và `CasAuthenticationFilter` cho cùng callback?**  
Không. Chúng thuộc hai stacks và có thể validate lại cùng single-use ticket, gây redirect loop/INVALID_TICKET.

**7. FilterRegistrationBean order khác HttpSecurity.addFilterBefore ở đâu?**  
Một cái quản lý Servlet container chain; cái kia quản lý vị trí bên trong Spring Security FilterChainProxy.

**8. Khi @Bean Filter đã thêm HttpSecurity, vì sao có thể bị chạy hai lần?**  
Spring Boot có thể tự container-register Filter Bean; dùng FilterRegistrationBean enabled=false nếu chỉ muốn filter ở SecurityFilterChain.

**9. Vì sao CAS service URL cần chính xác?**  
Ticket được cấp cho service và validator phải xác minh cùng service được CAS server công nhận; khác scheme/host/path có thể khiến CAS reject.

**10. INVALID_TICKET sau migration có nhất thiết do CAS server hỏng không?**  
Không. Thường do ticket đã single-use bị validate hai lần, double registration hoặc service mismatch.

**11. SingleSignOutHttpSessionListener thay thế SingleSignOutFilter không?**  
Không. Listener cleanup session mapping; filter nhận/process logout callbacks.

**12. Vì sao Spring Session Redis không tự bảo đảm CAS SLO multi-node?**  
Vì CAS client có thể giữ ticket-to-session mapping riêng ở local memory; phải xác minh hoặc triển khai distributed mapping tương ứng.

**13. CAS `Saml11TicketValidationFilter` có phải Spring Security SAML2 login không?**  
Không. CAS SAML 1.1 protocol variant khác SAML2 Web Browser SSO.

**14. Có thể chấp nhận một URL `jku` hoặc endpoint CAS server từ query callback không?**  
Không. CAS server/keys/trust config phải do server quản trị, không từ input chưa xác thực.

**15. Nên làm gì khi chứng thư CAS server đổi?**  
Cập nhật trusted TLS chain/hostname theo quy trình chứng thư, không disable certificate validation.

**16. Tại sao CAS SLO callback có thể không chứa cookie?**  
Có thể là back-channel request từ CAS server, không phải trình duyệt; session lookup cần server-side ticket/session mapping.

**17. Có nên tắt CSRF cho mọi endpoint để CAS logout POST hoạt động?**  
Không. Chỉ xử lý endpoint CAS callback cụ thể với trust validation; browser actions vẫn cần CSRF.

**18. CAS ticket đã validate thành công nhưng Spring SecurityContext vẫn anonymous, vì sao?**  
Apereo filter và Spring Security context có thể không được bridge; cần chọn Spring Security CAS strategy hoặc validated integration rõ ràng.

**19. CAS 4.1.x trong Boot3/Java17 compile fail thì hạ compiler target xuống 17 được không?**  
Không. Compiler target của app không đổi bytecode/baseline trong dependency; chọn compatible artifact/JDK.

**20. Test nào chứng minh migration thành công hơn “service khởi động”?**  
Real browser CAS login; ticket one-time validation, wrong service reject, local authz, CAS SLO, cross-node session, duplicate filter absence và safe logging.

## 22. Tài liệu chính thức và tham khảo

- [Apereo Java CAS Client (GitHub README)](https://github.com/apereo/java-cas-client): module `cas-client-core`, Servlet filters, filter init parameters, `AuthenticationFilter`, `Cas30ProxyReceivingTicketValidationFilter`, `SingleSignOutFilter`/listener và `@EnableCasClient`.
- [Maven Central — CAS Client Core 4.0.4](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-core/4.0.4): artifact Jakarta dùng với Java17/Servlet6 generation.
- [Maven Central — CAS Client 4.0.0 POM](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client/4.0.0): `jakarta.servlet-api:6.0.0` và `project.build.sourceVersion=17`.
- [Maven Central — CAS Client 4.1.1 Parent POM](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client/4.1.1): Servlet 6.1, JDK21, Boot4/Spring7.
- [Maven Central — CAS Client Boot Support 4.1.1](https://central.sonatype.com/artifact/org.apereo.cas.client/cas-client-support-springboot/4.1.1): artifact Boot integration.
- [Spring Security — CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): `CasAuthenticationFilter`, `CasAuthenticationProvider`, `CasAuthenticationEntryPoint`, TicketValidator, SLO integration. Các ví dụ XML có phần lịch sử, phải kiểm bản/framework hiện tại.
- [Spring Security — Servlet Security Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy`, filter order và cảnh báo Filter Bean bị container register kép.
- [Spring Boot — Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): `FilterRegistrationBean`, `ServletListenerRegistrationBean`, ordering and startup filter inspection.
- [Jakarta Servlet 6.0 Specification](https://jakarta.ee/specifications/servlet/6.0/): API và web.xml Jakarta namespace, container version.
- [Jakarta Servlet 6.1 Specification](https://jakarta.ee/specifications/servlet/6.1/): servlet generation mới với Jakarta EE 11.
- [Spring Boot 3 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java17, Spring Framework6, Jakarta EE APIs.
- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): generic errors, local status/reauthentication.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): cookies, session fixation, logout/invalidation.
- [OWASP CSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): user-initiated logout và request protections.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): tránh log ST/PGT/credentials/session IDs.

**Ghi nhớ:** Nâng CAS client lên Jakarta không đơn giản là đổi `javax.servlet` thành `jakarta.servlet` ở source ứng dụng. Phải chọn **CAS artifact biên dịch cho Jakarta + đúng Java/Spring generation**, bỏ legacy servlet dependency, xác định **một chủ sở hữu việc xác thực CAS ticket**, đăng ký `SingleSignOutFilter` và listener đúng thứ tự, dùng canonical `service` URL và trusted TLS ticket validation, giữ session/CSRF/SLO đúng semantics. Trong Spring Boot, chú ý filter được register ở **container** hay **SecurityFilterChain** để tránh validate một ST hai lần. Kiểm thử **browser login, ticket replay, wrong service, local authorities, SLO và multi-node** trước khi go-live; không bypass các bảo vệ chỉ để ứng dụng hết redirect loop.