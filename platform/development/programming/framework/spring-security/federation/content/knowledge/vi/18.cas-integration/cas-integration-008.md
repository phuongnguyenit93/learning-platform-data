# Đặt bộ lọc CAS trong SecurityFilterChain và tránh xử lý trùng yêu cầu

**Module:** Spring Security – federation  
**Chủ đề cha:** Tích hợp CAS  
**Phạm vi:** CAS Protocol Service Ticket authentication cho ứng dụng Servlet; Spring Boot 3.x, Spring Security 6.5, Java 17+. Bài không trộn CAS Protocol với Spring Security SAML2 login hoặc OAuth2/OIDC.

## 1. Mục tiêu: một callback CAS đi qua đúng đường xác thực

Trong Central Authentication Service (**CAS**), sau khi người dùng đăng nhập ở CAS Server, browser được chuyển về ứng dụng (**service/CAS client**) cùng tham số **ticket=ST-...**. Ứng dụng dùng **CasAuthenticationFilter** nhận callback, **CasAuthenticationProvider** và **TicketValidator** gọi CAS Server xác minh ticket, sau đó thiết lập **Authentication/SecurityContext** và phiên riêng của ứng dụng.

Vấn đề xảy ra khi bộ lọc CAS được đặt sai trong chuỗi bảo mật hoặc đăng ký trùng ở **hai tầng**:

1. **Servlet container filter chain:** Tomcat/Jetty/Undertow gọi các Servlet Filter được đăng ký với container.
2. **Spring Security FilterChainProxy:** bản thân được gọi qua **DelegatingFilterProxy**, chọn một **SecurityFilterChain** rồi chạy các security filters của chain đó.

Nếu một **CasAuthenticationFilter** vừa là **Filter bean** để Spring Boot tự đăng ký ở container, vừa được chèn bằng **http.addFilterAt(...)** vào Spring Security, cùng request có thể đi qua đối tượng filter **hai lần ở hai vị trí/thứ tự khác nhau**. Hậu quả có thể là xử lý lặp callback, session/redirect bất thường hoặc một nỗ lực validate lại Service Ticket đã được tiêu thụ.

**Nguyên tắc thực hành:** Một ứng dụng browser CAS thông thường cần **một CasAuthenticationFilter trong SecurityFilterChain đúng** và **không có đăng ký Servlet Filter độc lập cho chính filter đó**. Từng callback nên dẫn đến **một validation attempt** của Service Ticket tại CAS Server, không phải hai.

**Lưu ý chính xác:** Bị gọi hai lần ở cấp **doFilter** không phải lúc nào cũng có nghĩa hai lần validate ticket. **AbstractAuthenticationProcessingFilter** có thể xử lý thành công rồi redirect/ngắt chain trước khi filter khác chạy. Khi debug cần phân biệt **filter invocations**, **authentication attempts** và **back-channel CAS validation calls**, không suy diễn từ mỗi dòng log.

## 2. Hai tầng Servlet Filter và Spring Security là gì?

~~~text
HTTP request từ browser
       |
       v
Servlet Container Filter Chain
       |
       +-- Encoding / Observability / CORS filters (nếu có)
       |
       +-- DelegatingFilterProxy("springSecurityFilterChain")
               |
               v
         FilterChainProxy
               |
               +-- SecurityFilterChain #1 (vd: /api/**)?
               |       -> chỉ chọn khi matcher đầu tiên khớp
               |
               +-- SecurityFilterChain #2 (browser, fallback)
                       |
                       +-- SecurityContextHolderFilter
                       +-- HeaderWriterFilter
                       +-- CsrfFilter
                       +-- LogoutFilter
                       +-- CasAuthenticationFilter
                       +-- AnonymousAuthenticationFilter
                       +-- ExceptionTranslationFilter
                       +-- AuthorizationFilter
                       |
                       v
                    Controller/Servlet
~~~

**Sơ đồ là giản lược:** Danh sách và thứ tự cụ thể còn phụ thuộc cấu hình DSL, version và các filters khác. Không coi đây là toàn bộ thứ tự tuyệt đối của mọi ứng dụng. Điểm quan trọng là **CAS authentication filter nằm sau bước xử lý security context/exploit protection cần thiết và trước authorization**, không được đặt thành một container filter chạy bên ngoài ranh giới security mà không có chủ ý.

### 2.1. DelegatingFilterProxy

**DelegatingFilterProxy** là cầu nối giữa Servlet container và một Spring bean có chức năng Filter. Trong Spring Boot với Spring Security, đối tượng bean quan trọng thường mang tên **springSecurityFilterChain** và thực chất do **FilterChainProxy** cung cấp.

Bạn **không cần** tự tạo một DelegatingFilterProxy thứ hai hoặc tự khởi tạo FilterChainProxy để thêm CAS filter. Spring Boot/Spring Security đã quản lý cơ chế này khi có cấu hình Servlet Security phù hợp.

### 2.2. FilterChainProxy chỉ chọn chain đầu tiên khớp

Ví dụ có hai chains:

~~~text
@Order(1) SecurityFilterChain API:
  securityMatcher("/api/**")
  -> dành cho Basic/Bearer API

@Order(2) SecurityFilterChain Browser:
  matcher mặc định mọi request còn lại
  -> chứa CasAuthenticationFilter
~~~

Request **/api/orders** chọn API chain đầu tiên, **không chạy tiếp** browser chain. Request **/login/cas** không khớp /api/** nên chọn browser chain.

**Hai SecurityFilterChains cùng có thể match không có nghĩa cả hai đều chạy.** FilterChainProxy duyệt theo thứ tự ưu tiên và chọn **chain đầu tiên**. Nếu một chain sớm match **/** hoặc **/*** quá rộng nhưng không có CAS filter, callback bị “nuốt” vào chain khác, không đến CAS filter mong muốn.

### 2.3. securityMatcher khác requestMatchers trong authorizeHttpRequests

- **http.securityMatcher(...)** quyết định **SecurityFilterChain có được chọn để xử lý request hay không**.
- **authorizeHttpRequests(...).requestMatchers(...)** quyết định **phép kiểm tra quyền bên trong chain đã được chọn**.
- **permitAll()** chỉ nói quy tắc authorization cho phép URL; nó **không** tự tạo CAS callback endpoint, **không** tự chèn CasAuthenticationFilter và **không** sửa lỗi chọn sai chain.
- **web.ignoring()** bỏ qua Spring Security cho URL tương ứng; nếu bỏ qua **/login/cas** thì CAS filter nằm trong chain sẽ không nhìn thấy callback.

**Ví dụ lỗi:** Browser chain chỉ có **securityMatcher("/app/**")**; nhưng callback CAS là **/login/cas**. Filter dù đã được addFilterAt vẫn **không bao giờ được chạy** cho callback này. Cần sửa matcher hoặc đổi callback/service URL một cách đồng bộ, không dùng permitAll để “sửa đường đi”.

## 3. CasAuthenticationFilter làm gì khi nhận Service Ticket?

Spring Security cung cấp **CasAuthenticationFilter** trong module **spring-security-cas**. Với stateful browser CAS thông thường:

1. Browser truy cập tài nguyên được bảo vệ, chưa có Authentication.
2. **ExceptionTranslationFilter** dùng **CasAuthenticationEntryPoint** redirect browser tới CAS **/login?service=...**.
3. CAS Server xác thực hoặc sử dụng phiên SSO/TGT hợp lệ, cấp **Service Ticket** mới chỉ cho đúng service.
4. Browser trở về callback thường là **GET /login/cas?ticket=ST-...**.
5. **CasAuthenticationFilter**, qua cơ chế **AbstractAuthenticationProcessingFilter**, nhận request khớp callback và tạo **CasServiceTicketAuthenticationToken** chưa authenticated.
6. **AuthenticationManager/ProviderManager** chuyển token cho **CasAuthenticationProvider**.
7. Provider dùng **TicketValidator** gọi CAS Server **/serviceValidate** hoặc endpoint đã cấu hình, với **ticket + service URL**.
8. Nếu CAS trả **authenticationSuccess** và local account được chấp nhận, provider tạo **CasAuthenticationToken** đã authenticated.
9. Filter áp dụng **SessionAuthenticationStrategy**, cập nhật **SecurityContextHolder** và lưu context qua **SecurityContextRepository**.
10. Success handler redirect về tài nguyên ban đầu hoặc URL đã được cho phép; các request sau sử dụng SP HttpSession thay vì validate lại ST.

**ST chỉ được phép thử validate một lần.** CAS Protocol yêu cầu CAS Server làm vô hiệu ST sau **một validation attempt, kể cả kết quả thất bại**. Vì vậy callback bị xử lý trùng không đơn thuần là tốn CPU: lần validation sau có thể nhận **INVALID_TICKET** dù lần trước thành công.

### 3.1. Callback khớp đúng path

CasAuthenticationFilter mặc định theo dõi path **/login/cas**. Giá trị **ServiceProperties.getService()** phải là **public canonical callback URL** có cùng path, ví dụ:

~~~text
ServiceProperties.service = https://portal.example.org/login/cas

FilterProcessesUrl         = /login/cas

CAS login parameter:
service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas

CAS validation parameter:
service=https%3A%2F%2Fportal.example.org%2Flogin%2Fcas
~~~

Không cấu hình **ServiceProperties.service** là https://portal.example.org/ trong khi filter chờ /login/cas. Không xây service URL từ header Host/Forwarded chưa được tin; proxy HTTPS public và backend HTTP nội bộ phải thống nhất service URL mà CAS Server đã allowlist.

### 3.2. Không bật authenticateAllArtifacts nếu chỉ dùng browser ST

**ServiceProperties.setAuthenticateAllArtifacts(true)** là một chế độ mở rộng xử lý CAS artifact trên nhiều URL (thường dùng với proxy tickets/stateless clients). Nó thay đổi logic **requiresAuthentication** và service URL cần dùng; không cần cho luồng browser login đơn giản.

Mặc định cho ví dụ này giữ **authenticateAllArtifacts=false**, chỉ xử lý callback **/login/cas**. Không bật true để “chữa” path callback sai, vì có thể khiến các URL khác chứa query parameter ticket bị đưa vào xác thực ngoài mong muốn.

### 3.3. Service Ticket, session và yêu cầu idempotency

- **ST** là credential **one-time**, không thể coi việc xác minh nó là một request idempotent.
- **SP HttpSession** là kết quả xác thực cục bộ sau ST hợp lệ, có thể phục vụ nhiều HTTP requests trong thời hạn session.
- **Browser refresh callback URL** mang ST cũ là một HTTP request mới, không phải bằng chứng filter chạy hai lần trong cùng một request.
- **CAS Single Logout (SLO)** có filters và lifecycle riêng, không nên nhập chung với filter xác minh ST hoặc đăng ký CAS SingleSignOutFilter hai lần.

## 4. Các kiểu xử lý trùng và cách phân biệt

| Hiện tượng | Nguyên nhân điển hình | Cách xác định |
| --- | --- | --- |
| **Một HTTP request chạy CasAuthenticationFilter doFilter hai lần** | Filter bean được auto-register ở container **và** add vào security chain | Kiểm tra Spring Boot Filter registrations và SecurityFilterChain |
| **Hai CasAuthenticationFilter trong cùng chain** | Cấu hình addFilterAt/addFilterBefore hai lần hoặc DSL/plugin tự thêm một instance | In danh sách filters của matching chain, đếm đúng class |
| **Hai HTTP requests đến cùng callback** | Refresh/back button, double redirect, browser retry, reverse proxy retry, JS tự gọi lại | Request ID/trace ID, access logs đã mask ST, số lần CAS validate |
| **Hai lần CAS /serviceValidate** | Hai processing attempts hoặc code custom retry ST sau timeout | Metrics/mock CAS endpoint, TicketValidator invocation count |
| **Một callback bị xử lý tại hai lớp filter khác nhau** | Đăng ký raw CAS Servlet Filter/legacy web.xml và Spring Security CAS filter | Kiểm tra Servlet container registrations, thư viện legacy, filter order |
| **Một callback rơi vào wrong chain** | securityMatcher/@Order quá rộng hoặc thiếu callback path | Spring Security TRACE chain selection, FilterChainProxy.getFilters |
| **Filter log nhiều lần dù không gọi CAS validate** | DispatcherType.REQUEST/ERROR/FORWARD/ASYNC; instrumentation chạy ở nhiều dispatches | Log dispatcherType + path + correlation ID, kiểm tra attemptAuthentication |
| **CAS response Success nhưng app redirect loop** | SecurityContext không được save, session cookie thiếu, success handler sai | Đọc persistence/redirect chain, không chỉ đếm doFilter |
| **INVALID_TICKET sau lần thành công** | Ticket đã được consume; một flow khác cố dùng lại | Đếm validation attempts theo trace; không log ticket raw |

**Đừng sửa bằng cách bỏ CAS validation.** Nếu ticket chỉ được thử một lần, phải ngăn duplicate invocation và duplicate browser callback đúng nguyên nhân, không cache một kết quả authentication theo raw ST để chấp nhận replay bừa bãi.

## 5. Sai lầm số một: Filter bean tự đăng ký ngoài SecurityFilterChain

Ví dụ **nguy hiểm** trong Spring Boot:

~~~java
@Configuration
class IncorrectCasConfig {

    @Bean
    CasAuthenticationFilter casAuthenticationFilter() {
        return new CasAuthenticationFilter();
    }

    @Bean
    SecurityFilterChain web(HttpSecurity http,
                            CasAuthenticationFilter casFilter)
            throws Exception {
        http.addFilterAt(
            casFilter, UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }
}
~~~

Đây là **đoạn minh họa điều cần tránh, không phải class hoàn chỉnh có thể chạy** (thiếu AuthenticationManager, validator...). Nếu filter là bean, Spring Boot có thể **tự đăng ký nó với embedded Servlet container**; trong khi http.addFilterAt thêm cùng filter vào FilterChainProxy. Hệ quả là CAS filter có thể chạy **bên ngoài** và **bên trong** security chain.

### 5.1. Tại sao @Order trên Filter bean không đủ?

**@Order** hoặc container filter registration order chỉ điều chỉnh thứ tự bộ lọc ở phạm vi được áp dụng. Nó **không loại bỏ** việc cùng một filter bị đăng ký ở hai nơi và không buộc filter auto-registered chạy trong FilterChainProxy.

**@Order** trên **SecurityFilterChain bean** dùng để ưu tiên matcher các chains; một mục đích khác. Đừng thêm @Order vào CAS filter rồi coi duplicate processing đã được sửa.

### 5.2. Cách ưu tiên: tạo filter bằng new trong SecurityFilterChain

~~~java
@Bean
SecurityFilterChain browser(
        HttpSecurity http,
        ServiceProperties service,
        CasAuthenticationEntryPoint entryPoint,
        CasAuthenticationProvider provider)
        throws Exception {

    CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
    casFilter.setFilterProcessesUrl("/login/cas");
    casFilter.setServiceProperties(service);
    casFilter.setAuthenticationManager(new ProviderManager(provider));

    // Cấu hình SecurityContextRepository + session strategy
    // giống mục ví dụ hoàn chỉnh ở phần sau.

    http
        .exceptionHandling(e -> e.authenticationEntryPoint(entryPoint))
        .addFilterAt(
            casFilter, UsernamePasswordAuthenticationFilter.class);

    return http.build();
}
~~~

**Đây là fragment**, không phải code hoàn chỉnh. Điều cần học: CasAuthenticationFilter **không phải một @Bean** trong cách cấu hình này, vì thế Spring Boot **không tự phát hiện nó như một Servlet Filter bean**. Nó chỉ nằm ở chain mà bạn thêm vào bằng HttpSecurity.

### 5.3. Khi nhất thiết phải khai báo @Bean để inject

Đôi khi app cần một filter bean (tổ chức dependency injection, test hoặc reuse). Khi ấy phải chủ động tắt Servlet auto-registration:

~~~java
@Bean
FilterRegistrationBean<CasAuthenticationFilter>
disableCasServletRegistration(CasAuthenticationFilter filter) {
    FilterRegistrationBean<CasAuthenticationFilter> bean =
        new FilterRegistrationBean<>(filter);
    bean.setEnabled(false);
    return bean;
}
~~~

Các import:

~~~java
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.security.cas.web.CasAuthenticationFilter;
~~~

**Đây là lựa chọn THAY THẾ** cho cách tạo new ở mục 5.2, không phải đoạn phải thêm vào cả hai cùng lúc. Khi dùng variant bean: cấu hình **một bean CasAuthenticationFilter đã set đủ collaborator**, inject đúng instance đó vào **một** SecurityFilterChain, và khai báo FilterRegistrationBean disabled cho **chính instance ấy**.

**Cần hiểu setEnabled(false):** Nó ngăn **container registration** qua bean này, **không vô hiệu hóa CAS filter đã được chèn trong Spring Security**. Nếu còn một servlet filter registration khác bằng web.xml/@WebFilter/ServletContext.addFilter, phải dọn bản đăng ký đó riêng.

## 6. Chọn vị trí CasAuthenticationFilter trong HttpSecurity

Spring Security có các cách thêm filter:

- **addFilterBefore(customFilter, SomeKnownFilter.class)**: đặt trước một filter có slot thứ tự được Spring Security biết.
- **addFilterAfter(...)**: đặt sau một filter đã biết.
- **addFilterAt(customFilter, SomeKnownFilter.class)**: đặt tại **cùng thứ tự** với filter tham chiếu; rất phù hợp khi thay thế vị trí authentication filter theo kiểu CAS.

Với browser CAS **không bật formLogin** và không có authentication filter cùng slot cạnh tranh, ví dụ hay dùng:

~~~java
http.addFilterAt(
    casAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
~~~

**Không diễn giải addFilterAt là thao tác “xóa mọi filter khác cùng slot”.** Nó chỉ xác định vị trí. Nếu cấu hình khác cũng thêm UsernamePasswordAuthenticationFilter hoặc một CasAuthenticationFilter nữa tại cùng vị trí, cần loại bỏ xung đột bằng thiết kế đúng, không trông chờ thứ tự chạy ổn định của nhiều filters cùng order.

**Không dùng addFilterAfter(..., AuthorizationFilter.class)** cho CAS login: khi đó cơ chế authorization có thể từ chối trước khi ST được xác minh. Một authentication filter cần được đặt tại khu vực authentication, trước authorization và phù hợp với SecurityContext handling.

### 6.1. Các bước cần giữ nguyên

1. **SecurityContextHolderFilter/SecurityContextRepository** chuẩn bị cơ chế lấy SecurityContext hiện có.
2. Các filter bảo mật request (headers, CSRF theo method/endpoint, v.v.) vẫn hoạt động.
3. **CasAuthenticationFilter** xử lý callback đúng URL.
4. **AuthenticationManager** kiểm tra CAS token qua provider/validator.
5. **SessionAuthenticationStrategy** thực thi session fixation protection nếu dùng stateful browser login.
6. **SecurityContextRepository.saveContext(...)** được filter xác thực gọi qua cơ chế của Spring Security 6 khi thành công.
7. **AuthorizationFilter** quyết định quyền trên tài nguyên.
8. **SuccessHandler/FailureHandler** redirect hoặc báo lỗi phù hợp; không tự tạo Authentication từ query ticket.

**Không chỉnh thứ tự bằng cách tạo một DelegatingFilterProxy mới hoặc FilterChainProxy thứ hai.** Spring Security đã quản lý lifecycle và HttpFirewall; bypass cơ chế này có thể làm SecurityContext/session không nhất quán.

## 7. Ví dụ Spring Boot 3 / Spring Security 6.5 / Java 17: một filter, một callback

Đây là ví dụ Servlet Spring MVC dùng **CAS Protocol 2.0** cho browser login. Dùng **spring-security-cas**, không dùng saml2Login(). Các domain **example.org** là placeholder; để chạy CAS thật cần CAS Server HTTPS, service registry cho phép service URL, một user **demo** trên CAS Server và metadata/certificate TLS hợp lệ. Ví dụ chỉ cấp ROLE_USER cho demo; không thay thế account linking và authorization nghiệp vụ production.

### 7.1. Dependencies trong pom.xml

Trong Maven project có Spring Boot parent/BOM tương thích:

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
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-cas</artifactId>
  </dependency>
</dependencies>
~~~

CAS client validator được cung cấp qua dependency CAS client tương thích với Spring Security module. Nếu phiên bản đang dùng không đưa **cas-client-core** vào dependency tree, bổ sung theo hướng dẫn module và kiểm tra Maven dependencies; không ép một bản CAS client cũ ngoài BOM mà không xem tương thích.

### 7.2. application.yml

**src/main/resources/application.yml**

~~~yaml
app:
  cas:
    server-base-url: https://sso.example.org/cas
    login-url: https://sso.example.org/cas/login
    service-url: https://portal.example.org/login/cas

server:
  servlet:
    session:
      timeout: 30m

logging:
  level:
    org.springframework.security.web.FilterChainProxy: DEBUG
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
~~~

**server-base-url** là CAS Server base được cấu hình để validator gọi **/serviceValidate**. **login-url** là địa chỉ browser được redirect tới. **service-url** là public callback đã đăng ký với CAS service registry.

Không giả định **http://localhost:8080** có thể nhận CAS callback khi service URL công bố là **https://portal.example.org/login/cas**. Khi chạy ở test environment phải thay đồng bộ public service URL ở client + CAS registry + reverse proxy.

Lưu ý cấu hình logging này **chỉ nên dùng trong môi trường phát triển** và không log query ticket nguyên văn. Spring Security DEBUG có thể ghi request path/metadata; môi trường production cần sanitize access logs, trace và URL parameters.

### 7.3. Main class

**src/main/java/com/example/cas/CasApplication.java**

~~~java
package com.example.cas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CasApplication {
    public static void main(String[] args) {
        SpringApplication.run(CasApplication.class, args);
    }
}
~~~

### 7.4. CAS configuration đầy đủ

**src/main/java/com/example/cas/CasSecurityConfig.java**

~~~java
package com.example.cas;

import org.apereo.cas.client.validation.Cas20ServiceTicketValidator;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.cas.ServiceProperties;
import org.springframework.security.cas.authentication.CasAuthenticationProvider;
import org.springframework.security.cas.web.CasAuthenticationEntryPoint;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;

@Configuration
public class CasSecurityConfig {

    @Bean
    ServiceProperties serviceProperties(
            @Value("${app.cas.service-url}") String serviceUrl) {
        ServiceProperties props = new ServiceProperties();
        props.setService(serviceUrl);
        props.setSendRenew(false);
        props.setAuthenticateAllArtifacts(false);
        return props;
    }

    @Bean
    CasAuthenticationEntryPoint casEntryPoint(
            ServiceProperties serviceProperties,
            @Value("${app.cas.login-url}") String loginUrl) {

        CasAuthenticationEntryPoint entryPoint =
            new CasAuthenticationEntryPoint();
        entryPoint.setLoginUrl(loginUrl);
        entryPoint.setServiceProperties(serviceProperties);
        return entryPoint;
    }

    @Bean
    UserDetailsService localUsers() {
        // Chỉ phục vụ demo CAS user "demo"; không dùng password
        // để xác thực CAS. Production lookup local account DB.
        return username -> {
            if (!"demo".equals(username)) {
                throw new org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Local user not enabled");
            }
            return User.withUsername(username)
                .password("{noop}unused-by-cas")
                .roles("USER")
                .build();
        };
    }

    @Bean
    CasAuthenticationProvider casProvider(
            ServiceProperties serviceProperties,
            UserDetailsService localUsers,
            @Value("${app.cas.server-base-url}") String casBaseUrl) {

        CasAuthenticationProvider provider =
            new CasAuthenticationProvider();
        provider.setServiceProperties(serviceProperties);
        provider.setTicketValidator(
            new Cas20ServiceTicketValidator(casBaseUrl));
        provider.setUserDetailsService(localUsers);
        provider.setKey("portal-cas-provider-v1");
        return provider;
    }

    @Bean
    SecurityFilterChain browserSecurity(
            HttpSecurity http,
            ServiceProperties serviceProperties,
            CasAuthenticationEntryPoint entryPoint,
            CasAuthenticationProvider provider) throws Exception {

        SecurityContextRepository contextRepository =
            new HttpSessionSecurityContextRepository();

        // QUAN TRỌNG: không @Bean và không @Component.
        // Chỉ đăng ký qua HttpSecurity trong chain này.
        CasAuthenticationFilter casFilter =
            new CasAuthenticationFilter();

        casFilter.setFilterProcessesUrl("/login/cas");
        casFilter.setServiceProperties(serviceProperties);
        casFilter.setAuthenticationManager(
            new ProviderManager(provider));
        casFilter.setSecurityContextRepository(contextRepository);
        casFilter.setSessionAuthenticationStrategy(
            new ChangeSessionIdAuthenticationStrategy());

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint))
            .securityContext(sc -> sc
                .securityContextRepository(contextRepository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .addFilterAt(
                casFilter, UsernamePasswordAuthenticationFilter.class);

        return http.build();
    }
}
~~~

**Vì sao cách này tránh double registration?**

- Chỉ **CasAuthenticationProvider, ServiceProperties, CasAuthenticationEntryPoint** là beans được sử dụng lại. Chúng **không phải Servlet Filter**.
- **CasAuthenticationFilter** chỉ được tạo bằng **new** trong method **browserSecurity**; không có **@Bean** cho filter nên Spring Boot không auto-register filter đó bên ngoài Spring Security.
- Chỉ có **một http.addFilterAt** đưa nó vào đúng chain browser.
- **filterProcessesUrl=/login/cas** khớp public **ServiceProperties.service** đã đăng ký.
- **ProviderManager(provider)** chỉ chứa provider CAS cho callback; không có hai provider khác cùng xử lý CasServiceTicketAuthenticationToken.
- **HttpSessionSecurityContextRepository** dùng chung cho authentication filter và security chain, tránh login thành công trong một request rồi context không được persist.
- **ChangeSessionIdAuthenticationStrategy** giảm rủi ro session fixation khi CAS login thành công.
- **SessionCreationPolicy.IF_REQUIRED** giữ browser CAS stateful, không vô tình áp STATELESS làm mất session.
- Không bật **formLogin()**, không tạo một UsernamePasswordAuthenticationFilter khác cạnh tranh cùng slot. **addFilterAt** sử dụng vị trí authentication filter, không giả định một filter khác bị xóa tự động.
- Không cần **http.csrf().disable()** cho CAS callback GET thông thường. CSRF cho các thao tác thay đổi trạng thái ở ứng dụng vẫn được bảo vệ theo mặc định.

**Điều kiện thêm:** Cấu hình demo chỉ cho CAS user **demo**; nếu CAS login là user khác, local UserDetailsService trả lỗi dù ticket validation thành công. Đây là **fail closed** theo policy demo, không phải duplicate filter. Password field "{noop}unused-by-cas" là giá trị UserDetails mẫu, **không tham gia xác thực CAS**; production phải quản trị credential đúng nếu hệ thống dùng thêm phương thức xác thực khác.

### 7.5. Controller quan sát Authentication sau login

**src/main/java/com/example/cas/CasController.java**

~~~java
package com.example.cas;

import java.security.Principal;
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CasController {

    @GetMapping("/")
    public String home() {
        return "CAS filter-chain demo";
    }

    @GetMapping("/me")
    public Map<String, String> currentUser(Principal principal) {
        return Map.of(
            "name", principal.getName(),
            "authentication", "local-SP-session");
    }
}
~~~

Sau CAS callback thành công, **/me** dùng local Authentication từ SecurityContext/HttpSession. Không cần mang lại Service Ticket trong từng request. Production cần hạn chế hiển thị principal/attributes theo quyền của người dùng.

### 7.6. Lệnh chạy và kết quả kỳ vọng

Trong Maven project đầy đủ với Java 17+, chạy:

~~~bash
mvn spring-boot:run
~~~

Endpoint public nếu ứng dụng khởi động:

~~~bash
curl -i http://localhost:8080/
~~~

Body:

~~~text
CAS filter-chain demo
~~~

Đối với **GET /me** chưa authenticated ở public SP URL: browser được chuyển hướng tới CAS **/login?service=...**. Sau khi CAS cấp Service Ticket mới, callback **/login/cas?ticket=ST-...** đi qua một CasAuthenticationFilter đã cấu hình, ticket được xác minh qua CAS back-channel và SecurityContext được lưu. Browser sau đó sử dụng session cookie SP.

**Các bước này là kỳ vọng logic, không phải tuyên bố đã chạy end-to-end** với một CAS Server ở domain example.org. Nếu CAS server chưa tồn tại, service chưa được allowlist hoặc user không phải demo, không thể login hoàn chỉnh chỉ với mã mẫu.

## 8. Biến thể nhiều SecurityFilterChain: bảo đảm callback CAS không bị nuốt

Một ứng dụng có thể có **/api/** cho bearer/Basic API stateless và một browser area cho CAS stateful.

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain browserSecurity(HttpSecurity http,
        /* dependencies for CAS */) throws Exception {
    // Tạo/cấu hình CasAuthenticationFilter bằng new ở đây,
    // dùng ServiceProperties/ProviderManager/ContextRepository.
    // http.addFilterAt(casFilter, UsernamePasswordAuthenticationFilter.class);
    // Sau đó return http.build().
}
~~~

**Đây là fragment kiến trúc** (có chú thích placeholder và thiếu imports/dependencies của method thứ hai), không phải phần thứ hai cần copy nguyên văn vào class demo ở mục 7. Muốn dùng nhiều chain thật, thay thế method browserSecurity ở mục 7 cho đúng và import **org.springframework.core.annotation.Order**, **org.springframework.security.config.Customizer** cùng **SessionCreationPolicy**.

**Quy tắc matching:**

- GET **/api/orders** → API chain tại @Order(1); không dùng CasAuthenticationFilter.
- GET **/login/cas?ticket=...** → không khớp /api/**, đến browser chain có CAS filter.
- GET **/private** → browser chain, có thể khởi động CAS.
- Nếu browser chain dùng **securityMatcher("/web/**")**, callback **/login/cas** sẽ bị loại; cần bổ sung callback vào matcher hoặc dùng fallback chain, không chỉ permitAll.
- Nếu API chain dùng **securityMatcher("/**")** với thứ tự ưu tiên cao hơn, nó có thể bắt toàn bộ request, gồm callback; browser chain không chạy. Đây là **chain selection bug**, không phải CAS TicketValidator lỗi.

**Lưu ý:** Một ứng dụng có nhiều paths, proxy và authentication schemes cần thiết kế ranh giới rõ. Không bật HTTP Basic cho browser CAS nếu không cần, vì nó thay đổi entry point và trải nghiệm đăng nhập. Trong nhiều chain, mỗi chain còn có HttpSecurity shared objects/exception handling riêng; không mặc định configuration của API tự áp cho browser.

## 9. Cách tìm bộ lọc nào thật sự được chọn

Có hai cấp để kiểm tra:

### 9.1. Startup: danh sách filter của từng chain

Bật DEBUG có kiểm soát và xem thông tin **DefaultSecurityFilterChain** khi startup:

~~~yaml
logging:
  level:
    org.springframework.security.web.DefaultSecurityFilterChain: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

Bạn nên thấy danh sách security filters có **CasAuthenticationFilter** trong chain browser. Đếm số instance trong một chain: **mục tiêu là một**.

TRACE của FilterChainProxy thường cho thấy request được thử với matcher nào, chọn chain nào. **Không bật TRACE lâu dài ở production** vì có thể phát sinh URL chứa **ticket=ST-...**, path và thông tin truy cập nhạy cảm.

### 9.2. Runtime: phân biệt HTTP request và Servlet dispatch

Nếu log lặp, trước tiên ghi/đối chiếu những trường đã được làm sạch:

~~~text
request correlation ID
dispatcherType = REQUEST / FORWARD / ERROR / ASYNC
HTTP method
normalized path (KHÔNG có query ticket)
selected SecurityFilterChain
CasAuthenticationFilter.doFilter entry count
CasAuthenticationFilter.attemptAuthentication count
TicketValidator.validate count
HTTP response status / redirect destination (đã sanitize)
~~~

**Một request có thể được dispatch nhiều lần** trong Servlet lifecycle. Một exception có thể tạo **ERROR dispatch**; một request bất đồng bộ có thể có **ASYNC redispatch**. Điều này không nhất thiết là hai browser requests hoặc hai CAS validation attempts.

**Đừng log raw ticket.** Nếu cần correlation cho dev/test, dùng một **test-issued request ID** hoặc hash đã khóa/TTL phù hợp để tra, không sử dụng ticket làm identifier lưu lâu.

### 9.3. Đếm đúng thành phần để kết luận “double”

| Chỉ số | Giá trị cần kỳ vọng cho happy-path một callback | Ý nghĩa |
| --- | --- | --- |
| Browser callback HTTP request | 1 request từ browser đối với ST mới | Một URL vào ứng dụng |
| SecurityFilterChain được chọn | 1 (chain đầu tiên match) | FilterChainProxy không cộng dồn các chains |
| CasAuthenticationFilter có trong chosen chain | 1 | Không chèn hai instances |
| Servlet auto-registration cho CAS filter | 0 | Không có lớp xử lý CAS độc lập |
| CAS TicketValidator validation attempt | 1 | One-time Service Ticket |
| CAS Server ghi nhận serviceValidate | 1 | Chứng cứ back-channel theo server |
| SP SecurityContext sau callback | Authenticated khi local account hợp lệ | Không phải tự động được cấp chỉ từ ST string |

**Nếu thấy hai Servlet callbacks thực sự**, kiểm tra browser refresh, retry của proxy, callback JavaScript và redirect loop trước khi kết luận là filter bean auto-registration. Nếu thấy một request nhưng hai attempts, kiểm tra duplicate filter, custom provider retry, gateway interception hoặc exception/re-dispatch có xử lý lại.

## 10. Spring Boot tự đăng ký Filter bean như thế nào?

Trong Spring Boot Servlet, một Spring bean kiểu **jakarta.servlet.Filter** có thể được đăng ký như **Servlet Filter** với embedded container. Nếu cùng instance filter cũng được gọi từ Spring Security FilterChainProxy, nó có thể chạy hai chỗ.

Ví dụ:

~~~text
Servlet Container
  |
  +-- CasAuthenticationFilter bean   <-- đăng ký auto ngoài Security
  |
  +-- DelegatingFilterProxy(springSecurityFilterChain)
          |
          +-- FilterChainProxy
                  |
                  +-- CasAuthenticationFilter bean
                         <-- instance filter cũng được addFilterAt
~~~

**Vì vậy không phải cứ một Bean singleton là một lần chạy.** Một instance vẫn có thể tồn tại ở hai registration points. Điều cần kiểm tra là **đường đăng ký filter**, không chỉ số bean được tạo.

### 10.1. Bảng lựa chọn registration

| Cách khai báo | Có thể bị auto-register ở Servlet? | Có trong SecurityFilterChain? | Khuyến nghị |
| --- | --- | --- | --- |
| **new CasAuthenticationFilter() trong method @Bean SecurityFilterChain**, rồi addFilterAt một lần | Không do không phải Filter bean | Có | **Ưu tiên** |
| **@Bean CasAuthenticationFilter** + addFilterAt, không disable container registration | Có | Có | **Tránh** |
| **@Bean CasAuthenticationFilter** + **FilterRegistrationBean.enabled=false** + addFilterAt một lần | Được ngăn qua FilterRegistrationBean | Có | Dùng khi cần bean |
| Chỉ **@WebFilter** hoặc **ServletContext.addFilter** | Có | Không nhất thiết | Không thay CAS filter chuẩn của Spring Security |
| Tạo **hai CAS filters riêng** trong cùng chain | Có thể không auto-register | Có hai | Tránh |
| Đăng ký thêm **DelegatingFilterProxy** ngoài cấu hình Boot | Có thể gây nhiều đường vào Spring Security | Có | Tránh trừ kiến trúc được review kỹ |

**Một khi đã chọn một kiểu, không giữ lại cấu hình XML/web.xml/legacy filter registration từ dự án cũ.** Dọn việc đăng ký tại gốc quan trọng hơn việc thêm guard log hay suppress duplicate errors.

## 11. Chống duplicate validation ở cấp giao thức

CAS Service Ticket là **service-bound** và **one-time**. Một người thử cùng ST hai lần có thể gặp:

~~~text
Lần 1: CAS /serviceValidate(ticket=ST-X, service=portal)
   -> cas:authenticationSuccess
   -> ST-X bị consume

Lần 2: CAS /serviceValidate(ticket=ST-X, service=portal)
   -> cas:authenticationFailure/INVALID_TICKET
~~~

**Không có phương án an toàn là “thử lại đến khi được”.** Nếu callback được dùng hai lần hoặc CAS validation timeout không rõ đã consume chưa, cần lấy **ST mới** qua vòng CAS login mới theo flow chuẩn.

### 11.1. Đừng tạo callback GET mang tác dụng phụ nghiệp vụ

Callback GET của CAS đúng là thực hiện **login authentication** theo giao thức, nhưng ứng dụng không nên để **/login/cas** còn tạo đơn hàng, thanh toán hoặc những side effects khác. Xử lý ST thành công → thiết lập Authentication và redirect về một URL sạch, rồi các thao tác nghiệp vụ cần authorization và CSRF protection đúng.

### 11.2. Không đưa ticket vào redirect cuối

Thực hành:

~~~text
GET /login/cas?ticket=ST-X
  -> CAS validation
  -> login success
  -> 302 /private
  -> browser GET /private (không có ticket)
~~~

Tránh success handler redirect ngược về **request URL chứa ?ticket=ST-X**. Khi người dùng refresh lại URL đã có ticket, CAS phải từ chối replay. Những failure do “used ticket” sau browser back/refresh nên được xử lý bằng một vòng login mới có kiểm soát hoặc thông báo phù hợp, không cho phép ticket cũ được accept.

### 11.3. Vấn đề POST, CSRF và proxy retries

- CAS browser Service Ticket thông thường đến qua **GET callback**; default CSRF protection không yêu cầu token cho GET safe method.
- Những API POST/PUT/DELETE khác vẫn cần CSRF protection khi dùng cookie session; **không disable CSRF toàn bộ** để CAS callback chạy.
- Reverse proxy/load balancer không nên retry mù quáng callback GET mang ticket khi upstream có thể đã tiêu thụ ST; xử lý timeout/retry phải tuân theo single-use semantics.
- Nếu làm CAS callback qua custom POST hoặc gateway, phải thiết kế method matching và CSRF threat model riêng; không tự biến filter thành **authenticateAllArtifacts=true** cho mọi path.

## 12. Java 17 runnable: mô phỏng double registration và one-time ticket

Để thấy **hai đường registration có thể tạo hai validation attempts**, dùng một chương trình độc lập không cần Spring, CAS Server hoặc network. Đây là **mô phỏng có chủ đích**: framework thật có thể redirect/ngắt filter chain sau thành công và do đó không nhất thiết gọi CAS hai lần trong mọi lỗi cấu hình. Chương trình chứng minh vì sao không nên dựa vào giả định “nếu hai filters cùng tồn tại thì ST sẽ vẫn chạy được”.

**Tệp: DuplicateCasFilterDemo.java**

~~~java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class DuplicateCasFilterDemo {

    static final class TicketRegistry {
        private final Set<String> unused = new HashSet<>();
        int validationAttempts;

        void issue(String ticket) {
            unused.add(ticket);
        }

        boolean validateOnce(String ticket) {
            validationAttempts++;
            return unused.remove(ticket);
        }
    }

    static final class SimulatedCasFilter {
        private final TicketRegistry registry;
        int callbackInvocations;
        int successes;
        int failures;

        SimulatedCasFilter(TicketRegistry registry) {
            this.registry = registry;
        }

        void apply(String path, String ticket) {
            if (!"/login/cas".equals(path)) {
                return;
            }

            callbackInvocations++;
            if (registry.validateOnce(ticket)) {
                successes++;
            } else {
                failures++;
            }
        }
    }

    static final class Pipeline {
        final List<SimulatedCasFilter> servletFilters =
            new ArrayList<>();
        final List<SimulatedCasFilter> securityFilters =
            new ArrayList<>();

        void process(String path, String ticket) {
            for (SimulatedCasFilter filter : servletFilters) {
                filter.apply(path, ticket);
            }
            for (SimulatedCasFilter filter : securityFilters) {
                filter.apply(path, ticket);
            }
        }
    }

    public static void main(String[] args) {
        TicketRegistry goodTickets = new TicketRegistry();
        goodTickets.issue("ST-A");
        SimulatedCasFilter goodFilter =
            new SimulatedCasFilter(goodTickets);
        Pipeline good = new Pipeline();
        good.securityFilters.add(goodFilter);
        good.process("/login/cas", "ST-A");
        System.out.println(
            "singleInvocations=" + goodFilter.callbackInvocations);
        System.out.println(
            "singleValidations=" + goodTickets.validationAttempts);
        System.out.println(
            "singleSuccess=" + goodFilter.successes);

        TicketRegistry badTickets = new TicketRegistry();
        badTickets.issue("ST-B");
        SimulatedCasFilter badFilter =
            new SimulatedCasFilter(badTickets);
        Pipeline bad = new Pipeline();
        bad.servletFilters.add(badFilter);
        bad.securityFilters.add(badFilter);
        bad.process("/login/cas", "ST-B");
        System.out.println(
            "doubleInvocations=" + badFilter.callbackInvocations);
        System.out.println(
            "doubleValidations=" + badTickets.validationAttempts);
        System.out.println(
            "doubleSuccess=" + badFilter.successes);
        System.out.println(
            "doubleFailure=" + badFilter.failures);

        good.process("/private", null);
        System.out.println(
            "afterPrivateValidations=" +
                goodTickets.validationAttempts);

        good.process("/login/cas", "ST-A");
        System.out.println(
            "afterReplayValidations=" +
                goodTickets.validationAttempts);
        System.out.println(
            "afterReplayFailures=" + goodFilter.failures);
    }
}
~~~

Biên dịch/chạy (Java 17+):

~~~bash
javac DuplicateCasFilterDemo.java
java DuplicateCasFilterDemo
~~~

**Stdout chính xác:**

~~~text
singleInvocations=1
singleValidations=1
singleSuccess=1
doubleInvocations=2
doubleValidations=2
doubleSuccess=1
doubleFailure=1
afterPrivateValidations=1
afterReplayValidations=2
afterReplayFailures=1
~~~

**Giải thích:**

- Khi filter chỉ có trong security chain, callback đầu tiên tạo **một invocation và một validation**.
- Khi cùng instance được thêm cả **servletFilters** lẫn **securityFilters**, mô hình cố ý gọi cả hai, tạo **hai validation attempts**, CAS registry trả thành công lần một và thất bại lần hai.
- Request **/private** không khớp callback, filter không validate ticket mới.
- Một browser request mới tới **/login/cas** cùng ST-A đã dùng sẽ bị từ chối — đây là **replay request**, phân biệt với double registration trong cùng request.

**Giới hạn rõ ràng:** Trong Spring Security thật, CasAuthenticationFilter thường sử dụng success handler redirect nên filter chain có thể không chạy tới lượt đăng ký thứ hai. Mô phỏng chỉ minh họa rủi ro kiến trúc và cách đếm, **không dự đoán số lần thực tế ở mọi bản Spring**. Việc xác minh thực tế phải dựa vào filter registrations, selected chain và CAS TicketValidator/server metrics.

## 13. Integration test: xác minh chain chứa đúng một CAS filter

Trong dự án ví dụ, thêm dependency test vào pom.xml:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Đoạn kiểm tra cấu trúc chain có thể đặt trong test Spring Boot khởi động với properties CAS test hợp lệ. Ví dụ **class test đầy đủ**:

**src/test/java/com/example/cas/CasFilterChainTest.java**

~~~java
package com.example.cas;

import java.util.List;

import jakarta.servlet.Filter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.cas.web.CasAuthenticationFilter;
import org.springframework.security.web.FilterChainProxy;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
class CasFilterChainTest {

    @Autowired
    @Qualifier("springSecurityFilterChain")
    Filter springSecurityFilterChain;

    @Test
    void callbackHasExactlyOneCasFilter() {
        FilterChainProxy proxy =
            (FilterChainProxy) springSecurityFilterChain;

        List<Filter> filters = proxy.getFilters("/login/cas");
        assertNotNull(filters, "Callback must match a security chain");

        long count = filters.stream()
            .filter(CasAuthenticationFilter.class::isInstance)
            .count();

        assertEquals(1L, count,
            "Selected chain must have exactly one CAS filter");
    }

    @Test
    void ordinaryPathIsNotAnExtraCasCallback() {
        FilterChainProxy proxy =
            (FilterChainProxy) springSecurityFilterChain;

        List<Filter> filters = proxy.getFilters("/private");
        assertNotNull(filters);
        assertEquals(1L, filters.stream()
            .filter(CasAuthenticationFilter.class::isInstance)
            .count());

        // CAS filter có trong chain, nhưng chỉ attemptAuthentication
        // khi request thực sự khớp /login/cas.
    }
}
~~~

**Điểm giới hạn:** Test này kiểm tra **security filter list của chain được chọn**, không chứng minh **Servlet container không auto-register filter bean**. Với cấu hình mẫu tạo filter bằng **new** và không khai báo @Bean, rủi ro auto-registration của chính instance đó được tránh. Với variant @Bean, thêm test/inspection cho **FilterRegistrationBean.enabled=false** và Servlet container filter registrations.

### 13.1. Test đếm một CAS validation attempt

Bài kiểm thử tích hợp quan trọng hơn là khởi tạo một **ST test hợp lệ** trên CAS test server hoặc mock CAS endpoint tin cậy, rồi kiểm tra:

~~~text
Given:
  CAS user demo đã xác thực,
  CAS Server cấp một ST mới cho public service URL.

When:
  Browser GET /login/cas?ticket=<fresh-ST> một lần.

Then:
  Selected SecurityFilterChain chứa đúng một CasAuthenticationFilter;
  TicketValidator gọi CAS /serviceValidate chính xác một lần;
  CAS trả authenticationSuccess theo protocol;
  SP lưu authenticated SecurityContext;
  Browser được redirect tới URL sạch không có ticket.
~~~

Sau đó cố tình **refresh callback URL cũ**, phải nhận lỗi/khởi động flow mới an toàn; không được tái sử dụng ST thành công. Test thứ hai dùng **hai filter registrations** trên môi trường thử nghiệm để xác minh startup/structural test phát hiện sai cấu hình, không đưa lỗi cố ý vào production.

**Không mock AuthenticationProvider thành “always authenticated”** rồi kết luận đã test CAS validation. Test chain placement và test CAS protocol validation là hai phạm vi khác nhau; nên có cả test cấu trúc filter và test một lần gọi validator.

### 13.2. Bất đồng bộ/ERROR dispatch

Nếu test dùng Servlet async hoặc error page, có thể có nhiều dispatch cùng request. Log **DispatcherType** và số back-channel validation attempts. Mục tiêu không phải cấm mọi dispatch, mà là **không bao giờ tái xác thực cùng ST như thể một ticket mới**. Không dùng OncePerRequestFilter wrapper như biện pháp duy nhất để chữa hai registrations; cần loại bỏ duplicate registration tại gốc.

## 14. Bộ kiểm thử âm và checklist QA

| Ca kiểm thử | Kết quả mong muốn |
| --- | --- |
| Callback /login/cas có fresh ST | Filter nhận đúng một lần trong mô hình không duplicate, CAS validation thành công |
| Browser GET /private sau login | Khôi phục SecurityContext từ session, **không validate lại ST** |
| Refresh /login/cas?ticket=ST-cũ | CAS từ chối ST đã dùng, không tạo Authentication mới từ replay |
| Filter được khai báo cả @Bean và addFilterAt mà không disable auto-registration | Kiểm tra cấu hình phát hiện trùng, không triển khai production |
| Variant @Bean + FilterRegistrationBean.enabled=false | Không có Servlet auto-registration cho CAS filter đó |
| Hai instances CasAuthenticationFilter cùng trong chain | Structural test fail; cần giữ một instance |
| FilterChainProxy có API chain @Order(1) và browser @Order(2) | /api/** vào API chain; /login/cas vào browser chain |
| API chain matcher /** đặt ưu tiên trước browser | Test phát hiện callback không thấy CAS filter |
| Browser chain chỉ match /app/** | /login/cas không khớp; cần sửa matcher/URL |
| permitAll("/login/cas") nhưng securityMatcher loại callback | Vẫn không xử lý CAS; permitAll không sửa selection |
| web.ignoring("/login/cas") | Callback không vào Spring Security; không xử lý CAS login |
| ServiceProperties.service khác public callback URL | CAS service validation fail; không “chữa” bằng bypass |
| Reverse proxy chuyển HTTPS sang HTTP backend | Service URL giữ public HTTPS cấu hình cố định |
| Filter chạy hai Servlet dispatches ERROR/REQUEST | Phân biệt invocation với CAS validation attempt |
| CAS /serviceValidate timeout | Không retry cùng ST vô điều kiện; flow mới khi cần |
| CAS trả HTTP 200 nhưng XML authenticationFailure | Không tạo Authentication |
| CAS success nhưng local user disabled | Không được business access |
| Spring Security 6 context không save | Test fail/redirect loop; cấu hình repository đúng |
| GET callback không có ticket | Không tạo Authentication giả; xử lý lỗi/redirect thích hợp |
| POST nghiệp vụ có cookie mà không có CSRF token | Từ chối theo CSRF policy |
| CAS Server cluster 2 nodes | Ticket registry single-use atomic ở CAS Server |
| Filter bean legacy từ web.xml/@WebFilter còn tồn tại | Dọn duplicate registration, giữ một đường xử lý |
| Hai users đăng nhập cùng lúc trên hai sessions | Tách session/authentication, không lấy user từ shared mutable filter fields |
| Browser đóng tab ở CAS rồi mở lại | Không tự tạo Authentication nếu không có ST mới hợp lệ |
| Callback ticket bị lộ qua logs/analytics | Log đã sanitize query; không lưu raw ticket |

### Gợi ý assertion tự động

- **Số CasAuthenticationFilter trên chosen chain = 1**.
- **Số Servlet registrations tự động của CAS filter = 0**.
- **TicketValidator calls = 1** với một fresh ST và một callback HTTP request.
- **Authentication.isAuthenticated() = true** chỉ sau CAS response success và local account acceptance.
- **SecurityContext persistence** qua request tiếp theo hoạt động đúng.
- **ServiceProperties.service** trùng canonical service được CAS Server cấp ticket.
- **Không có raw ST** trong URL redirect cuối, application logs, APM, browser analytics.
- **Không có vòng redirect vô tận** khi session cookie hợp lệ.
- **CSRF/authorization** của resource nghiệp vụ vẫn hoạt động.

## 15. Những lỗi vận hành điển hình

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| **CasAuthenticationFilter xuất hiện hai lần trong logs** | Filter bean auto-register + http.addFilterAt, hoặc dispatch riêng | Kiểm tra cả servlet registrations và selected chain; log dispatcherType |
| **CAS INVALID_TICKET khi callback** | ST đã bị dùng; validator chạy trùng, refresh hoặc timeout | Đếm CAS validation calls, kiểm tra browser/proxy retry, tạo ST mới |
| **Không vào CasAuthenticationFilter dù ticket đã có** | callback bị securityMatcher loại, web.ignoring, wrong filter URL | Sửa chain match và ServiceProperties.service |
| **CAS Service Ticket mismatch** | http/https, host, port, path khác giữa /login và validate | Dùng canonical public service URL, proxy trust đúng |
| **Success rồi lại quay về CAS login** | SecurityContext không save, session mất, SameSite/cookie lỗi | Dùng HttpSessionSecurityContextRepository và session strategy đúng |
| **Lỗi 403 trên callback** | Security chain/CSRF/method không đúng; POST custom; rule sai | Kiểm tra method, matcher, CSRF policy; không disable toàn bộ |
| **CAS không được gọi nhưng controller thấy ticket** | Query được chuyển thẳng controller vì filter không match | Không tự xác thực ở controller; sửa CAS filter path |
| **Filter không có thứ tự mong muốn** | Đăng ký ngoài container, dùng @Order trên Filter sai mục đích | Dùng HttpSecurity.addFilterAt ở đúng chain |
| **ClassNotFoundException CAS client** | Thiếu module cas-client-core đúng phiên bản | Kiểm tra Maven dependency tree và compatibility |
| **CAS validation OK nhưng user không có quyền** | Local UserDetailsService/roles/account disabled | Tách xác thực CAS khỏi local authorization |
| **Hai chain đều “match” nhưng filter browser không chạy** | FilterChainProxy chọn chain đầu tiên | Sửa @Order/securityMatcher, bổ sung fallback browser chain |
| **Lỗi chỉ khi nhiều node ứng dụng** | Session không chia sẻ, proxy chuyển callback, state mất | Kiểm tra Spring Session/sticky session và cookie; CAS ticket registry riêng |
| **Filter duplicate sau migration từ XML** | Legacy CAS filter/DelegatingFilterProxy còn được đăng ký | Gỡ wiring cũ, chỉ giữ một SecurityFilterChain config |
| **Đăng xuất CAS không xóa local session** | SLO được cấu hình riêng, không liên quan CAS ST filter | Thiết kế CAS SingleSignOutFilter/session lifecycle có kiểm chứng |
| **Token ST xuất hiện trong trace** | Logs ghi URL query và redirect headers | Mask ticket parameter ở reverse proxy/APM/access logs |

### Trình tự chẩn đoán ngắn nhất

~~~text
1. CAS callback public service URL là gì?
2. /login/cas thuộc SecurityFilterChain nào?
3. FilterChainProxy selected filters có CasAuthenticationFilter không?
4. Trong chain có bao nhiêu CAS filter instances?
5. Servlet container có đăng ký thêm CAS filter không?
6. CasAuthenticationFilter có đúng filterProcessesUrl không?
7. ServiceProperties.service có khớp CAS service registry không?
8. TicketValidator gọi CAS bao nhiêu lần trên fresh ST?
9. CAS trả authenticationSuccess hay authenticationFailure?
10. Local UserDetailsService có chấp nhận user?
11. SecurityContextRepository có lưu session sau login không?
12. Browser được redirect tới URL sạch, không mang ticket?
~~~

Tránh giải pháp “cứ retry /serviceValidate thêm lần nữa” khi ST đã dùng. Đó là làm trầm trọng vấn đề, vì CAS ticket không idempotent.

## 16. Những điểm mở rộng cần cân nhắc

### 16.1. CAS proxy tickets/stateless integrations

Spring Security **CasAuthenticationFilter** còn hỗ trợ proxy ticket flows và **authenticateAllArtifacts**. Khi cần xác thực ticket trên URL khác callback mặc định, phải cấu hình **ServiceAuthenticationDetailsSource**, TicketValidator cho proxy, stateless ticket cache và policies đúng. **Không bật chế độ đó chỉ để sửa lỗi filter không match /login/cas**, vì nó làm mở rộng phạm vi request có thể kích hoạt xác thực.

**ST browser callback stateful** và **PT stateless API** có vòng đời khác nhau. Nếu ứng dụng đã có bearer/OAuth API, thường dùng chain stateless riêng thay vì mang ST theo mọi API request.

### 16.2. CAS Single Logout và duplicate filter

CAS Single Logout thường dùng filter/listener từ CAS client để nhận sự kiện logout/invalidates sessions. Đây **không phải** CasAuthenticationFilter xác minh ST. Nếu triển khai SLO, phải quyết định một phương thức đăng ký và thứ tự phù hợp, tránh vừa auto-register một SingleSignOutFilter bean vừa add nó vào Spring Security và xử lý logout event hai lần.

**Không trộn bài toán SLO vào CAS login callback:** việc đăng xuất từ CAS Server có thể đến khi user không còn request nào tại SP, cần session registry và chính sách phù hợp. Nhưng double registration ở SLO cũng có thể làm invalidation/logs trùng hoặc sai thứ tự.

### 16.3. Nhiều tenant và nhiều CAS servers

Nếu service hỗ trợ nhiều CAS Servers/tenant, không thể dùng một service URL hoặc TicketValidator nhận giá trị từ query tùy ý rồi tự chọn CAS Server. Phải chọn **trusted CAS configuration** theo tenant/route đã phê duyệt, canonical service URL riêng, và định danh local account gắn với issuer/CAS authority tương ứng. Với nhiều chains, callback cho từng tenant phải match đúng chain và có duy nhất một filter/validator theo policy.

Nếu hai chains có callback paths trùng nhau nhưng khác CAS Server, cần phân định route, host/tenant và state một cách xác minh được. Không dùng chuỗi ticket **ST-...** để đoán CAS server phát hành.

## 17. Checklist production

- [ ] Đã xác định đúng **CAS service callback** và canonical HTTPS URL, registry CAS Server cho phép.
- [ ] **CasAuthenticationFilter** chỉ nằm trong **SecurityFilterChain** được dự định, không auto-register ở container.
- [ ] Nếu filter phải là bean, có **FilterRegistrationBean.enabled=false** và không còn legacy servlet registration.
- [ ] Matching chain chứa CAS filter cho **/login/cas**; không bị chain ưu tiên cao hơn nuốt.
- [ ] Phân biệt **securityMatcher** (chọn chain) và **requestMatchers** (quyền bên trong chain).
- [ ] Không dùng **web.ignoring("/login/cas")** hoặc đặt CAS filter sau authorization.
- [ ] Không thêm filter hai lần tại cùng slot qua DSL/addFilterAt/legacy XML.
- [ ] **ServiceProperties.service** và **filterProcessesUrl** thống nhất với public URL được CAS Server cấp ST.
- [ ] **CasAuthenticationEntryPoint, CasAuthenticationProvider, TicketValidator** dùng cùng trusted CAS Server/service config.
- [ ] **authenticateAllArtifacts=false** với browser ST thông thường trừ khi có thiết kế proxy rõ ràng.
- [ ] **SecurityContextRepository/HttpSession** lưu Authentication sau callback; session fixation strategy phù hợp.
- [ ] One-time ST chỉ được validate một lần; không retry cùng ST sau lỗi/timeout.
- [ ] Sau CAS validation thành công, redirect tới URL sạch, browser requests sau dùng SP session.
- [ ] CSRF protection cho thao tác ứng dụng không bị vô hiệu hóa vì CAS callback.
- [ ] Logs/APM/proxy/browser không lưu raw ST, dùng correlation ID đã sanitize.
- [ ] Test structural chain, container registration, TicketValidator invocation count, session persistence và replay.
- [ ] Test multi-chain với /api/** và /login/cas; bảo đảm @Order không nuốt callback.
- [ ] Test browser retry, ERROR/ASYNC dispatch, wrong service URL, local account disabled và DB/CAS timeout.
- [ ] Có kế hoạch migration nếu dự án có CAS XML legacy/filter ngoài container hoặc Spring Security version khác.
- [ ] Không coi CAS authentication đã thành công là quyền nghiệp vụ; local account/roles/tenant vẫn cần kiểm tra.

**Kết luận:** Để tránh xử lý trùng yêu cầu trong Spring Security CAS, hãy đặt **một CasAuthenticationFilter đúng vị trí authentication của SecurityFilterChain**, để **FilterChainProxy chọn đúng chain cho /login/cas**, và ngăn Spring Boot tự đăng ký filter đó thêm một lần với Servlet container. Kết hợp với **CAS Service Ticket chỉ dùng một lần**, canonical service URL, persistence của SecurityContext và kiểm thử đếm validation attempts, ứng dụng sẽ có luồng CAS login dễ kiểm chứng và ít lỗi replay/redirect loop hơn.

## 18. Tài liệu tham khảo

- [Spring Security 6.5 – Servlet Security Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, filter ordering và cảnh báo Filter bean auto-registration.
- [Spring Security 6.5 – Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html): securityMatcher vs requestMatchers và first matching SecurityFilterChain.
- [Spring Security – CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CAS filter/provider/entry point, callback URL, stateful vs stateless CAS tickets.
- [Spring Security 6.5 – CasAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html): callback path, ticket processing, serviceProperties, security context repository.
- [Spring Security 6.5 – CasAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html): provider settings, local UserDetailsService và TicketValidator.
- [Spring Security 6.5 – FilterChainProxy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html): first-match chain selection, firewalling và filter lifecycle.
- [Spring Boot – Servlet Filters / FilterRegistrationBean](https://docs.spring.io/spring-boot/reference/web/servlet.html): Servlet filter bean auto-registration và kiểm soát filter registrations.
- [CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service-ticket one-time validation và service binding.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, session lifecycle, cookie security.
