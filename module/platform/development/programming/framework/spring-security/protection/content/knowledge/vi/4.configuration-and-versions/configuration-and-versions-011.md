# Đọc API, migration guide và kiểm thử lại khi đổi phiên bản

> **Chương:** Cấu hình và phiên bản  
> **Module:** `SPRING_SECURITY_HTTP_PROTECTION`  
> **Phạm vi:** Nâng cấp Spring Security mà không làm suy giảm các lớp phòng vệ HTTP và trình duyệt: **CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session, logout và security chain**, trên cả **Servlet/Spring MVC** lẫn **Reactive/WebFlux**.  
> **Mốc biên soạn:** 26/11/2026. Hướng dẫn tập trung vào phương pháp đọc tài liệu **theo đúng phiên bản đã resolve**, sử dụng migration guide và xác minh qua kiểm thử; mọi API minh họa phải được đối chiếu với phiên bản dự án thực tế trước khi sử dụng.

## 1. Nâng Spring Security là thay đổi hành vi bảo mật, không chỉ đổi số phiên bản

Giả sử một ứng dụng MVC có SPA sử dụng cookie/session, một số API nhận Bearer JWT và một khu vực quản trị. Nhóm phát triển nâng dependency rồi thấy ứng dụng khởi động, trang chủ hiện bình thường và vài endpoint trả 200. Kết luận “nâng thành công” ở thời điểm đó **chưa đủ**: một request POST thiếu CSRF token có thể được xử lý; preflight CORS có thể bị 401; route `/admin/**` có thể rơi ngoài mọi security chain; CSP/HSTS có thể biến mất khỏi một response; cookie session có thể mất hiệu lực sau login/logout.

Những thay đổi này không nhất thiết gây lỗi biên dịch. Một matcher vẫn compile nhưng hiểu đường dẫn khác, một bean bảo mật mặc định không còn được auto-configure, hay một request handler đọc CSRF token theo dạng khác đều có thể tạo **regression về bảo mật**.

### Phân biệt bốn tiêu chí “nâng cấp xong”

| Tiêu chí | Câu hỏi | Bằng chứng cần có |
| --- | --- | --- |
| **Binary compatibility** | Dự án compile, package/API còn tồn tại? | Dependency graph và biên dịch |
| **Runtime compatibility** | Framework, web server, bean wiring, startup hoạt động? | Khởi động trên cấu hình thật, integration test |
| **Behavioral compatibility** | Login, logout, session, CORS, CSRF, matcher có cùng hợp đồng? | Contract/regression tests |
| **Security compatibility** | Request bị cấm vẫn bị cấm; không mất headers, token protection, firewall? | Negative tests, browser/E2E qua HTTPS public |

**Nguyên tắc của bài:** “Không có compile error” không đồng nghĩa “không có security regression”. Khi đổi major version, luôn làm **baseline → đối chiếu tài liệu theo phiên bản → thay đổi nhỏ có chủ đích → kiểm thử lại toàn bộ hợp đồng HTTP protection**.

### Bạn sẽ làm được gì?

1. Tìm và đọc đúng **Reference Guide**, **API Javadoc**, **Migration Guide**, **What's New**, release notes và hướng dẫn Spring Boot.
2. Xác định phiên bản Spring Security **thực sự được resolve**, thay vì chỉ đọc một dòng trong build file.
3. Lập danh sách API deprecated/removed/new và so sánh hành vi trước/sau.
4. Đối chiếu các thay đổi quan trọng từ Spring Security 5.8/6.x/6.5 đến 7.x.
5. Tổ chức việc nâng theo từng web stack, từng security chain và từng lớp phòng vệ.
6. Thiết kế kiểm thử Servlet bằng `MockMvc`, Reactive bằng `WebTestClient` và kiểm thử qua reverse proxy/HTTPS.
7. Ghi bằng chứng, điều kiện rollback và cách đọc một kết quả 400/401/403/404 sau migration.

## 2. Năm nguồn tài liệu: mỗi nguồn trả lời một câu hỏi khác nhau

Không bắt đầu bằng việc tìm một snippet ngẫu nhiên rồi dán vào `SecurityFilterChain`. Hãy chọn đúng nguồn cho câu hỏi đang cần giải quyết.

| Nguồn | Trả lời tốt nhất | Những gì phải xem |
| --- | --- | --- |
| **Reference Guide** | Framework nên được cấu hình **thế nào** trên một dòng version? | Servlet/Reactive tabs, default behavior, prerequisite, examples |
| **API Javadoc** | Method/class chính xác có tồn tại và có signature gì? | Package, constructor, parameters, return type, `Since`, `Deprecated`, `forRemoval`, linked types |
| **Migration Guide** | Những bước nào cần thực hiện khi chuyển từ version nguồn sang version đích? | Preparation, opt-in/opt-out, removed APIs, đổi default behavior |
| **What's New / Release Notes** | Tính năng mới, thay đổi có ảnh hưởng và bug fixes là gì? | Major/minor/patch, breaking change, CVEs nếu có |
| **Spring Boot/Framework docs** | Stack runtime, auto-configuration, servlet engine, proxy và property còn tương thích không? | BOM, starter/module names, Java baseline, config properties, web application type |

### 2.1. Đọc đúng hai chiều: “nguồn” và “đích”

Giả sử dự án dùng Spring Security **6.5.x** và đích là **7.0.x**:

```text
1. Chụp dependency graph hiện tại: 6.5.x đã resolve thực tế.
2. Đọc 6.5 Reference Guide: hành vi đang vận hành.
3. Đọc 6.5 Migration to 7 preparation: chuẩn bị API mới trước.
4. Đọc 7.0 Migration Guide: các bước khi chuyển major.
5. Đọc 7.0 Reference Guide + API: đích có class/method nào.
6. Đọc 7.x release notes của patch đích: thay đổi/cảnh báo bổ sung.
7. Compile + chạy contract tests + browser/HTTPS smoke tests.
```

Nếu target thực tế là 7.2 thay vì 7.0, còn phải đọc thay đổi của **7.1 và 7.2**, không nhảy thẳng từ hướng dẫn 7.0 rồi coi xong. Khi đọc trang docs dùng URL không pin version, luôn nhìn tên phiên bản ở đầu trang; URL `/reference/` có thể hiển thị dòng stable mới hơn vào lúc khác.

### 2.2. Cách đọc một Javadoc đúng quy trình

Lấy một API ví dụ `PathPatternRequestMatcher`:

1. Đọc **package**: `org.springframework.security.web.servlet.util.matcher` — đây là API Servlet, không phải matcher WebFlux.
2. Đọc **signature** và linked types: implement `RequestMatcher`, nhận các đối tượng liên quan `HttpServletRequest`.
3. Đọc **`Since`**: xác nhận từ dòng nào class/method có mặt; đừng lấy ví dụ target mới để chạy trên jar cũ.
4. Đọc **`Deprecated`/`forRemoval`** và gợi ý replacement. Deprecated **không** luôn có nghĩa đã bị loại ngay; bị loại trên target thì compile mới lỗi.
5. Đọc **chú thích semantics**: pattern **tương đối với context path**, servlet path cần `basePath` khi không dùng default servlet mapping.
6. Đọc **ví dụ Reference Guide/migration** để biết cách framework khởi tạo matcher và điều kiện parser.
7. Biến semantics quan trọng thành **test**. Ở đây cần test `/api`, `/api/`, `/api/orders`, servlet mapping `/mvc/*`, proxy rewrite, URL encoding.

**Cách phân loại phát hiện từ Javadoc:**

| Ký hiệu | Diễn giải chính xác | Quyết định tiếp theo |
| --- | --- | --- |
| `Since: X.Y` | API bắt đầu xuất hiện ở dòng đó | Kiểm tra jar resolved có version đủ mới |
| `@Deprecated` | API được khuyên không tiếp tục dùng | Đọc replacement/migration; chuẩn bị refactor |
| `forRemoval=true` | Có kế hoạch xóa theo deprecation contract | Ưu tiên xử lý trước major target |
| Thay đổi package | Class vẫn có thể mang tên giống nhưng không cùng type | Sửa import, bean wiring và test |
| Cùng method name | Không bảo đảm hành vi hoặc kiểu tham số giống | Kiểm tra owner class, signature, default và lifecycle |
| Default mới | Code không đổi nhưng runtime có thể đổi | Viết test trước/sau cho hành vi mặc định |

### 2.3. Bắt đầu từ “đích cần bảo vệ”, không chỉ từ tên method

Nếu thấy một thay đổi API liên quan CSRF, hãy hỏi **token sẽ được lưu ở đâu, lộ cho SPA thế nào, có bị xóa khi login/logout không?** Thấy matcher mới thì hỏi **request nào trước đây được bảo vệ nay rơi ngoài chain?** Thấy firewall mới thì hỏi **URL nào mới bị 400 hoặc từng bị normalization không an toàn?**

Tài liệu API cho biết hình dạng của một class; **threat model** giúp biến hiểu biết đó thành kiểm thử có giá trị.

## 3. Xác định phiên bản đã resolve trước khi chạm vào code

### 3.1. Spring Boot, Security và Framework không được chọn rời rạc

Spring Boot quản lý dependency thông qua BOM/dependency management. Khi nâng Boot, version Spring Framework, Spring Security, embedded web server, Jackson và các starter có thể đổi cùng nhau. Thay riêng một module `spring-security-web` mà bỏ qua `spring-security-config` hoặc Framework có thể gây lỗi link/class/method dù project compile một phần.

**Điểm đầu tiên trong migration:** chụp danh sách resolved versions của:

```text
Java runtime / JDK
Spring Boot (plugin, parent/BOM)
Spring Framework (spring-web, spring-webmvc hoặc spring-webflux)
Spring Security (security-core, security-config, security-web, security-test)
Session / OAuth2 Resource Server / Authorization Server (nếu có)
Reactor Netty hoặc Servlet container
Jackson, test libraries, dependency overrides
```

Ví dụ lệnh để người phát triển tự chạy trong dự án của họ:

```bash
# Maven: kiểm tra dependency đã resolve (không tự sửa POM).
./mvnw dependency:tree -Dincludes=org.springframework.security
./mvnw dependency:tree -Dincludes=org.springframework

# Gradle: kiểm tra module thực tế trên runtimeClasspath.
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Trên Windows, dùng `mvnw.cmd` hoặc `gradlew.bat`. Các command trên **chỉ minh họa cho quy trình**; bài học không yêu cầu hoặc xác nhận đã chạy chúng với dự án cụ thể nào.

### 3.2. “Cùng major” chưa phải bằng chứng tương thích

Nếu Reference Guide 7.0 khuyên dùng Spring Boot 4.0 patch phù hợp trước khi lên Spring Security 7, hãy tuân theo đường nâng được tài liệu xác nhận. Đừng ghép Boot 3.x với Security 7 chỉ vì Maven không báo lỗi ở một module nhỏ.

Tương tự, khi đổi Boot 3 → Boot 4, cần đọc migration của Boot về:

- Module/starter dependencies và namespace package.
- Property keys, test autoconfiguration/imports và auto-configuration conditions.
- Servlet vs Reactive application type, session/cookie settings.
- Cách cấu hình forwarded headers, TLS termination và externalized config.
- Jackson serialization nếu Security session/auth objects được lưu ngoài tiến trình.

Nếu hệ thống dùng Spring Session/Redis, sự tương thích **serialization** của `SecurityContext` cũng là một phần kế hoạch rollout/rollback; không chỉ cần unit tests cho controller.

### 3.3. Baseline hiện tại là hợp đồng, không phải “để mọi thứ y như cũ”

Không phải hành vi cũ nào cũng an toàn. Ví dụ dự án từng tắt CSRF mọi nơi hoặc bỏ qua `/public/**` khỏi Security chain, migration không nên “bảo toàn” cấu hình yếu ấy. Ghi baseline để biết tác động, sau đó xác định **policy mục tiêu an toàn** và những thay đổi có chủ đích.

Phân biệt rõ:

- **Regression:** URL ADMIN từng bị chặn bỗng được phép, hoặc token CSRF hợp lệ bị bỏ kiểm tra.
- **Hardening mong muốn:** firewall mới reject encoded slash vốn trước đây đi qua, hoặc CSP được siết theo kế hoạch.
- **Thay đổi UX có kiểm soát:** form login trả redirect khác, cookie refresh lại sau logout, frontend cần token bootstrap mới.

Một test “trước 200, sau 400” có thể là thay đổi tốt (request vốn nguy hiểm), **không** đồng nghĩa phải nới firewall để giữ 200.

## 4. Bản đồ thay đổi theo phiên bản liên quan đến HTTP protection

| Dòng | Thay đổi đáng chú ý | Kiểm tra liên quan bảo mật |
| --- | --- | --- |
| **5.2+** | Lambda DSL đã tồn tại | Chuyển cấu hình fluent `.and()` cũ sang Lambda DSL |
| **5.7/5.8** | `WebSecurityConfigurerAdapter` bị deprecate; hướng cấu hình bằng bean; 5.8 cung cấp migration preparation cho 6 | Bean `SecurityFilterChain`, `UserDetailsService`, `PasswordEncoder`, request matcher |
| **6.0** | `WebSecurityConfigurerAdapter` và APIs `antMatchers`/`mvcMatchers` cũ bị loại khỏi Java DSL; CSRF deferred loading/BREACH mặc định | CSRF SPA/form, matcher, chuyển sang bean |
| **6.2** | `HttpSecurity.apply(...)` cho custom DSL bị deprecate, thay bằng `with(...)` | Custom DSL tự thêm filter/header/security policies |
| **6.4** | Có public API Reactive HTTP firewall (`ServerWebExchangeFirewall`) | `StrictServerWebExchangeFirewall`, request rejected handler, proxy wiring |
| **6.5** | Dòng cuối 6.x, có migration-preparation hướng tới 7 | Bật thử PathPattern matchers, Lambda DSL, dọn API deprecated |
| **7.0 Servlet** | Loại `AntPathRequestMatcher`/`MvcRequestMatcher` ở đường API chuẩn; dùng `PathPatternRequestMatcher`; Lambda DSL được yêu cầu; `csrf.spa()` xuất hiện | Servlet path/context path, SPA cookie/header, CSRF, chain matcher |
| **7.0 Reactive** | Cần đọc migration/API WebFlux riêng, không tự dùng Servlet APIs | `SecurityWebFilterChain`, `ServerHttpSecurity`, Reactive CSRF/CORS/firewall |
| **7.1/7.2+** | Minor releases có thể tiếp tục thay đổi hành vi và sửa lỗi | Đọc release notes/What's New đúng target; chạy lại tests |

**Lưu ý:** bảng này là **danh sách chủ đề cần điều tra**, không phải bảng khẳng định mọi ứng dụng gặp mọi thay đổi. Bắt đầu từ dependency graph và API mà project đang dùng, không tạo một danh sách sửa code chỉ vì version khác.

### 4.1. Mốc nâng 6 → 7 nên đi qua 6.5

Spring Security chính thức khuyên **đưa ứng dụng lên dòng 6.5**, áp các bước chuẩn bị trên 6.5, sau đó mới lên 7.0. Cách này hữu ích vì nhiều behavior mới có opt-in trên 6.5, giúp phát hiện khác biệt khi vẫn còn khả năng quay lại trong cùng major.

```text
5.x (nếu đang ở 5.x)
   |
   +--> đọc 5.8 migration/prepare-to-6
   v
6.0–6.4
   |
   +--> nâng lên 6.5 patch phù hợp
   +--> bật trước API/behavior của 7 khi migration guide hướng dẫn
   +--> sửa warning/deprecation và ổn định regression tests
   v
6.5 đã chuẩn bị
   |
   +--> nâng Boot / Framework / Security theo tổ hợp tương thích
   +--> đọc Migration 7.0 và notes các minor/patch tiếp theo
   v
7.x
   |
   +--> regression, staging HTTPS, rollout có kiểm soát
```

Không khuyến khích “sửa hết bằng cách thêm các override dependency để project compile” vì một tổ hợp không được kiểm chứng có thể phá CSRF filters, matcher, JWT authentication hoặc các security headers trong runtime.

## 5. Đọc migration guide đúng cách: biến hướng dẫn thành danh sách thay đổi

Một migration guide không nên được đọc như tập hợp các dòng code để copy. Mỗi mục cần chuyển thành một **change record** với ít nhất sáu thông tin:

```text
API/behavior cần đổi:
Lý do thay đổi và phiên bản bắt đầu:
Điều kiện áp dụng cho dự án:
Code/config cũ -> code/config mới:
Rủi ro nếu bỏ qua:
Test chứng minh đã xử lý và đường rollback:
```

Ví dụ:

| Hạng mục | Trạng thái cũ | Đích | Kiểm thử bắt buộc |
| --- | --- | --- | --- |
| Servlet URL matcher | `AntPathRequestMatcher` hoặc `MvcRequestMatcher` | `PathPatternRequestMatcher` | Context/servlet path, slash, encoding, method |
| Cấu hình HTTP | `authorizeRequests`/`.and()`/adapter cũ | `SecurityFilterChain` + Lambda DSL | Chain coverage và rule order |
| CSRF Servlet 5 → 6 | Token load ngay, handler attribute cũ | Deferred loading + XOR masking | Form, SPA token, login/logout |
| SPA Servlet 6.5 → 7 | Request handler tự viết | `csrf(csrf -> csrf.spa())` khi thích hợp | Raw cookie/header và token rotation |
| Reactive firewall | Chưa có public API trước 6.4 | `StrictServerWebExchangeFirewall` trong WebFlux 6.4+ | URL không chuẩn, method, handler |
| CORS config | Một bean hoặc controller annotation | Servlet/Reactive source đúng stack/chain | OPTIONS được phép/bị từ chối |
| HSTS/header writer | Custom/default ở chain cũ | Chính sách tương đương có chủ đích | HTTPS public, CSP, nosniff |
| Session/identity | Cookie/serialized SecurityContext cũ | Lưu trữ/context repository phù hợp | Login/logout, timeout, multi-replica |

Mỗi dòng có **người chịu trách nhiệm**, phạm vi chain và bằng chứng test. Không đánh dấu “Done” chỉ vì IDE không còn gạch đỏ.

### 5.1. Phân biệt preparation guide và target migration

Đối với 6.5 → 7:

- **Preparation trên 6.5:** thay DSL `.and()`, thử PathPattern matcher mới, sửa API deprecated, chuẩn bị các hành vi mới **trước khi** nâng major.
- **Migration target 7.0:** giải quyết những APIs đã bị removed, module/serialization mới và mọi khác biệt sau khi nâng.
- **Reference 7.x:** kiểm tra cách cấu hình được hỗ trợ trong target.
- **Release notes từng patch:** xem những thay đổi không được liệt kê đầy đủ trong các ví dụ chính.

**Ví dụ thực tế:** một snippet trong hướng dẫn 6.5 dùng `PathPatternRequestMatcherBuilderFactoryBean` để **opt-in trước**; điều đó không có nghĩa một ứng dụng Security 7 cần copy y nguyên bean này. Trên 7, matcher mới đã là lựa chọn mặc định theo hướng dẫn mục tiêu. Phải phân biệt mã “để chuẩn bị” với mã “để vận hành dài hạn”.

### 5.2. Dấu hiệu nên dừng migration và điều tra

Nếu thấy một trong những hiện tượng sau, đừng chữa bằng `permitAll()` hoặc `csrf.disable()`:

- URL admin bỗng không cần authentication.
- API chain có `anyRequest().authenticated()` nhưng URL ngoài `securityMatcher` được phép.
- Browser POST cookie/session đi qua dù không có CSRF token.
- OPTIONS preflight từ frontend hợp lệ trả 401 hoặc 403.
- `Content-Security-Policy`/`Strict-Transport-Security` thiếu trên HTTPS public.
- Login redirect về HTTP nội bộ sau reverse proxy.
- `XSRF-TOKEN` tồn tại nhưng SPA không gửi được `X-XSRF-TOKEN`.
- 400 bất thường sau khi firewall nghiêm ngặt được bật.
- Session mất khi request sang pod khác hoặc token trong session deserialize lỗi.

Đây là các triệu chứng **cần bằng chứng từ HTTP layer và chain**, không phải lý do giảm bảo mật để “giữ hệ thống chạy”.

## 6. Thay đổi API cấu hình Servlet: từ adapter/`.and()` sang bean và Lambda DSL

### 6.1. Nhận ra ví dụ legacy

Một bài blog cũ có thể dùng:

```java
// LEGACY — minh họa API đã bị loại trong Spring Security 6.
@Configuration
@EnableWebSecurity
class LegacySecurity extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
                .and()
            .formLogin();
    }
}
```

**Không dùng đoạn này làm sample chạy trên Spring Security 7**. `WebSecurityConfigurerAdapter` đã bị loại từ 6, `antMatchers`/`authorizeRequests` và chaining `.and()` không còn là cấu hình hợp lệ cho target 7.

### 6.2. Cấu hình Servlet hiện đại

```java
package com.example.security.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class ServletProtectionConfiguration {

    @Bean
    SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

Đoạn này minh họa chain dành cho **browser form login/session**. `csrf(Customizer.withDefaults())` giữ CSRF cho unsafe HTTP methods; nếu website là SPA dùng cookie, cần đọc thêm mục 8. Nó không cung cấp sẵn user store, controller, CORS nguồn cross-origin, CSP đầy đủ cho CDN hoặc cookie policy production.

### 6.3. Những khác biệt cần đọc trong API

| Cấu hình cũ | Cấu hình mới cần tìm | Rủi ro nếu chỉ thay tên |
| --- | --- | --- |
| Kế thừa `WebSecurityConfigurerAdapter` | Bean `SecurityFilterChain` | Mất chain mặc định hoặc bean authentication |
| `authorizeRequests` | `authorizeHttpRequests` | Matcher/authorization semantics thay đổi |
| `antMatchers`/`mvcMatchers` | `requestMatchers`/matcher tường minh | Pattern khác nhau, servlet path bị bỏ sót |
| `.and()` | Lambda DSL | DSL lồng sai cấp, custom configurer sai |
| `HttpSecurity.apply(customDsl)` | `HttpSecurity.with(customDsl, customizer)` | Custom filter và thứ tự bị thay đổi |
| `web.ignoring("/public/**")` | Cân nhắc `permitAll()` | Public assets mất security headers |
| Global auth trong adapter | Các bean `UserDetailsService`, `AuthenticationProvider`, `AuthenticationManager` theo nhu cầu | User không được load, password encoder khác |

**Không nên gộp migration API và đổi authentication mechanism cùng lúc**. Trước tiên làm cho form-login/current JWT vẫn hoạt động trên config bean/Lambda DSL, test lại; sau đó mới cân nhắc đổi OAuth2, cookie session hoặc mô hình người dùng.

## 7. Thay đổi matcher ở Servlet 7: đọc semantics chứ không chỉ method name

Spring Security 7 chuyển Java DSL request matcher cho Servlet sang `PathPatternRequestMatcher`; `AntPathRequestMatcher` và `MvcRequestMatcher` không còn là lựa chọn tiêu chuẩn được giữ lại. Điểm quan trọng không phải chỉ thay class, mà là **đường dẫn nào được security nhìn thấy**.

### 7.1. Context path và servlet path

Ví dụ deployment:

```text
Browser gọi:         https://example.com/app/mvc/orders/123
Context path:        /app
DispatcherServlet:   /mvc/*
Handler mapping:     /orders/{id}

Path matcher cần xét: /mvc/orders/123
Không thêm /app vào pattern được kiểm tra.
```

Với Servlet security target có `PathPatternRequestMatcher`:

```java
import static org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher.withDefaults;

PathPatternRequestMatcher.Builder mvc =
    withDefaults().basePath("/mvc");

http.authorizeHttpRequests(auth -> auth
    .requestMatchers(mvc.matcher("/orders/**")).authenticated()
    .anyRequest().denyAll()
);
```

Phương thức `basePath("/mvc")` cho phép viết lại các matcher tương đối với prefix Servlet. Security path thường bỏ context root; cần xác định servlet mapping và parser tại runtime. Nếu ứng dụng dùng custom `PathPatternParser` cho Spring MVC, đọc Javadoc và cấu hình matcher để bảo đảm Security và HandlerMapping cùng cách hiểu pattern.

### 7.2. `securityMatcher` và `requestMatchers` không cùng cấp

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        );
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().authenticated()
    );
    return http.build();
}
```

**Đọc công thức:** `securityMatcher` quyết định chain có nhận request không; `requestMatchers` chỉ chọn rule quyền **bên trong chain đã chọn**. `anyRequest()` trong API chain không bảo vệ `/admin/**`. Khi thêm custom chains, Boot có thể không tạo chain mặc định theo mong đợi; vì vậy cần fallback tường minh.

### 7.3. Những URL cần kiểm thử khi đổi matcher

| Đường dẫn | Câu hỏi phải trả lời |
| --- | --- |
| `/api` và `/api/` | Matcher `/api/**` có nhận cả hai theo parser thực tế? |
| `/api/orders` và `/api-v2/orders` | Không match nhầm prefix? |
| `/admin/report` và `/admin/report/` | Có trailing-slash bypass hoặc handler mismatch? |
| `/admin//report` | Bị HTTP firewall/proxy xử lý an toàn? |
| `/admin%2Freport` | Encoding có làm router và matcher hiểu khác nhau? |
| `/mvc/orders/123` khi Servlet path `/mvc` | Pattern mới có đủ prefix? |
| `/app/mvc/orders/123` với context root `/app` | Không đưa context path vào matcher sai chỗ? |
| `/login`, `/logout`, `/error` | Vẫn nằm trong chain cung cấp filter/login/headers? |
| URL sau ingress rewrite | Backend nhận path gì, public URL là gì? |

Đừng “chữa” lỗi URL bằng `requestMatchers("/**").permitAll()`. Hãy đo request đang vào chain nào và handler nào; kiểm thử cả security filter chain lẫn controller routing.

## 8. CSRF migrations: deferred token, BREACH và SPA từ 7.0

### 8.1. Dòng 5 → 6 thay đổi mặc định CSRF token

Spring Security 6 mặc định dùng **deferred loading** và **XOR token presentation** để chống BREACH. Trước đó những app đã lấy raw CSRF token qua HTML form/JavaScript có thể thấy token trông khác đi hoặc không còn được load trên mọi GET.

| Thành phần | Hành vi cần quan sát | Regression test |
| --- | --- | --- |
| `CsrfTokenRepository` | Lưu token trong HttpSession hoặc cookie | GET/bootstrap rồi POST đúng token |
| `CsrfTokenRequestHandler` | Giải quyết token từ header/parameter; masking | Form `_csrf` và SPA header raw |
| Deferred loading | Token có thể chỉ được tạo/lấy khi cần | Token bootstrap trước POST |
| `CsrfAuthenticationStrategy` | Token cũ được xóa sau authentication success | Login rồi lấy token mới |
| `CsrfLogoutHandler` | Token cũ được xóa sau logout | Logout rồi refresh trước request mới |
| CSRF request matcher | Unsafe methods vẫn được bảo vệ | POST/PUT/PATCH/DELETE thiếu token bị chặn |

Chỉ cấu hình `CookieCsrfTokenRepository.withHttpOnlyFalse()` không tự giải quyết trường hợp **raw cookie token** được gửi trong header trong khi request handler mặc định đọc **masked token**. Đọc hướng dẫn SPA đúng phiên bản.

### 8.2. Servlet 7.0+: `csrf.spa()` khi SPA dùng cookie

```java
// Servlet HttpSecurity, Spring Security 7.0+
http.csrf(csrf -> csrf.spa());
```

`spa()` là cấu hình tiện ích cho Servlet: cookie repository và handler token phù hợp SPA. Nó **không** thay CORS, session management, auth/authorization, CSP, HSTS hoặc việc frontend thực sự đọc cookie theo hostname/path. Không gọi `spa()` trên WebFlux `ServerHttpSecurity.CsrfSpec` như thể hai API giống nhau.

### 8.3. Servlet 6.5 và WebFlux cần cách tiếp cận khác

| Tổ hợp | Cách xử lý phù hợp |
| --- | --- |
| Servlet 6.5 | `CookieCsrfTokenRepository` + request handler SPA tùy chỉnh theo reference nếu dùng raw cookie/header; hoặc token endpoint đúng lifecycle |
| Servlet 7+ | Cân nhắc `csrf(csrf -> csrf.spa())`, xác minh các custom cookie attributes cũ và test login/logout |
| WebFlux 6/7 | `CsrfWebFilter`/`ServerCsrfTokenRepository`, có thể dùng `WebSessionServerCsrfTokenRepository` và token endpoint; **không** copy Servlet `CsrfConfigurer.spa()` |
| Bearer-only API không có credential tự gửi | Có thể đánh giá phạm vi miễn CSRF riêng theo threat model, không áp dụng cho browser cookie chain |

**Test case quan trọng sau nâng:** `POST /orders` có session nhưng **không** có CSRF header/parameter phải bị 403; có token hợp lệ phải đi qua lớp CSRF. `with(csrf())` của spring-security-test kiểm tra filter chấp nhận token nhưng **chưa chứng minh** SPA có thể đọc cookie `XSRF-TOKEN`, nên phải có E2E cookie/header round-trip.

## 9. CORS: API giống nhau trên giấy nhưng nguồn cấu hình khác giữa hai stack

Khi nâng version, một số dự án bắt đầu sử dụng Servlet và WebFlux trong những service riêng. Về nghiệp vụ, cả hai đều cho phép frontend `https://app.example.com` gọi API; về Java type, **hai CORS source khác package**.

### 9.1. Servlet CORS source

```java
package com.example.security.servlet;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletCorsConfig {
    @Bean
    UrlBasedCorsConfigurationSource corsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

Trong `SecurityFilterChain` Servlet:

```java
http.cors(cors -> cors.configurationSource(servletCorsSource));
```

### 9.2. Reactive CORS source

```java
package com.example.security.reactive;

import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
class ReactiveCorsConfig {
    @Bean
    UrlBasedCorsConfigurationSource corsSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE"));
        cors.setAllowedHeaders(
            List.of("Content-Type", "X-CSRF-TOKEN", "X-XSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
```

Trong `SecurityWebFilterChain` Reactive:

```java
http.cors(cors -> cors.configurationSource(reactiveCorsSource));
```

Hai file mã trên là **hai ứng dụng độc lập**; chỉ khác một import nhưng không thể hoán đổi bean. Các đoạn `http.cors(...)` minh họa phần **bên trong method nhận HttpSecurity hoặc ServerHttpSecurity và source tương ứng**. Trong ứng dụng có nhiều source, cần inject tường minh bean đúng qualifier để không chọn nhầm nguồn CORS.

### 9.3. CORS preflight là một hợp đồng phải test lại

```http
OPTIONS /orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
```

Preflight thường **không kèm session cookie**, nên nếu API authentication xử lý trước CORS, request có thể 401/403. `@CrossOrigin` trên controller hoặc `permitAll` cho OPTIONS chưa đủ chứng minh policy CORS được gắn đúng security chain.

Test phải xác nhận:

- Origin hợp lệ trả `Access-Control-Allow-Origin` phù hợp, allowed methods/headers, credentials nếu cần.
- Origin lạ **không** được cấp quyền CORS.
- Không dùng wildcard `*` với credentialed CORS.
- Source CORS thuộc đúng stack và không có proxy/CDN ghi header trái ngược.
- Nếu response thay đổi theo origin, cache dùng `Vary` phù hợp để không trộn origin.

**Khi frontend và API khác subdomain**, cần phân biệt *cross-origin* với *cross-site*. Việc `Access-Control-Allow-Origin` đúng **không** chứng minh browser sẽ gửi cookie; `SameSite`, `Secure`, `Domain`, `Path` và third-party cookie policy cũng có tác động. Test browser Network tab sau migration, không chỉ `curl`.

## 10. Security headers và CSP/HSTS: kiểm tra phản hồi công khai

Một thay đổi version có thể làm config header cũ bị deprecated hoặc không còn được áp do một security chain mới. Điều kiện quan trọng là **header nào thực sự xuất hiện trên response mà browser nhận**.

### 10.1. CSP không có mặc định phù hợp với mọi ứng dụng

`Content-Security-Policy` phải được ứng dụng định nghĩa, không được Spring Security tự thêm một chính sách chung. Một cấu hình Servlet minh họa:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Reactive `ServerHttpSecurity` có DSL header riêng với cùng mục tiêu:

```java
http.headers(headers -> headers
    .contentSecurityPolicy(csp -> csp
        .policyDirectives(
            "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
        )
    )
);
```

Cú pháp trông tương tự nhưng owner class khác. Nếu HTML được CDN/frontend server phục vụ còn Spring chỉ trả JSON API, CSP **trên API response** không thay thế CSP của trang HTML. Sau migration, cần test `script-src`, `style-src`, `connect-src` và `frame-ancestors` ở đúng URL trang, đặc biệt khi SPA đổi origin/CDN.

Không tắt toàn bộ headers bằng `headers(headers -> headers.disable())` để sửa một lỗi giao diện. Hãy nới **đúng directive** được kiểm chứng hoặc dùng chế độ `Content-Security-Policy-Report-Only` có kế hoạch chuyển sang enforce.

### 10.2. HSTS không phải kiểm thử chỉ tại localhost HTTP

HSTS là header `Strict-Transport-Security` được gửi ở HTTPS. Browser ghi nhớ chính sách theo hostname (và có thể subdomain), không phải theo URL path.

Với Servlet, DSL có `httpStrictTransportSecurity(...)`; với Reactive, DSL có `hsts(...)` và kiểu thời gian khác. Đừng copy configurer Servlet sang WebFlux. Khi một reverse proxy terminate HTTPS rồi chuyển HTTP vào Spring, phải xác minh public scheme/forwarded headers/trusted proxy để biết ai là người ghi HSTS.

**Bảng acceptance headers sau nâng:**

| Response | Kiểm tra | Ý nghĩa |
| --- | --- | --- |
| HTML `GET /` qua HTTPS | CSP, HSTS, nosniff, cache policy | Browser thực sự nhận protection |
| `GET /public/help` | Headers còn trên public URL | `permitAll` không vô tình bị đổi sang `web.ignoring` |
| `GET /api/public/ping` | Header policy của API chain | Không mặc định kế thừa browser chain |
| `GET /admin/report` sau auth | CSP/HSTS và authorization | Header phải cùng tồn tại với kiểm soát quyền |
| CDN static asset | Header do CDN/edge quản lý | Không trông chờ Spring ghi headers cho response không đi qua app |

Nếu headers khác nhau giữa URL cùng host, điều tra **chain được chọn và nơi phục vụ response** trước khi đổi API. HSTS trên nhiều chain cùng host nên nhất quán; không bật `includeSubDomains`/`preload` khi chưa đánh giá toàn bộ subdomain.

### 10.3. Response có header đúng chưa đủ chứng minh quyền đúng

Proxy có thể tự thêm `X-Content-Type-Options` hoặc HSTS ngay cả khi Spring Security chain không được chọn. Một request vào `/admin/**` cần test user có/không có quyền **song song** với header assertions; đừng sử dụng sự tồn tại của một header làm bằng chứng chain authorization đã hoạt động.

## 11. HTTP firewall: xác minh version, defaults và ranh giới request

### 11.1. Servlet và Reactive là hai API khác nhau

| Thuộc tính | Servlet | Reactive |
| --- | --- | --- |
| Strict firewall | `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` |
| Proxy | `FilterChainProxy` | `WebFilterChainProxy` |
| Exception | `RequestRejectedException` | `ServerExchangeRejectedException` |
| Request object | `HttpServletRequest` | `ServerWebExchange` |
| Mốc public API Reactive | Không áp dụng | **Spring Security 6.4+** |
| HTTP test | `MockMvc` | `WebTestClient` |

Nếu Javadoc báo `Since: 6.4` cho `ServerWebExchangeFirewall`, không lấy snippet này đưa vào WebFlux Security 6.3. Ngược lại, khi nâng 6.3 → 6.4+, nên kiểm tra request bất thường trước đây có được xử lý khác do Strict firewall, thay vì vội gọi `setAllowSemicolon(true)` hoặc `setAllowUrlEncodedSlash(true)`.

### 11.2. Kiểm thử chặn URL bất thường

| Request | Mục tiêu |
| --- | --- |
| `GET /admin/report`, user thường | Authorization cấm |
| `GET /admin//report` | Không bypass do double slash |
| `GET /admin/../public` | Không bypass do traversal |
| `GET /admin%2Freport` | Không diễn giải encoded slash lệch |
| `GET /admin;role=1/report` | Semicolon policy rõ ràng |
| `TRACE /public/ping` | Method allowlist xử lý theo threat model |
| `OPTIONS /api/orders` | CORS preflight không bị firewall method allowlist chặn nhầm |

Lưu ý HTTP server/ingress có thể reject hoặc normalize request **trước** khi tới Spring Security; status 400 từ public URL không tự chứng minh Strict firewall là nguồn chặn. Cần test bean trực tiếp nếu cần phân biệt tầng, kết hợp log an toàn và E2E qua proxy.

### 11.3. Thay đổi ở Spring Security 7.2: HTTP method case

*What's New* 7.2 nêu rằng Spring Framework chuẩn hóa case ở `HttpMethod.valueOf`. Vì thế `StrictServerWebExchangeFirewall` không còn nhận biết method `get` viết thường như một giá trị riêng so với `GET` trong tình huống đã được chuẩn hóa. Những test từng yêu cầu `ServerExchangeRejectedHandler` phải chạy trên request lowercase có thể không còn phù hợp.

**Không nhầm** thay đổi này với việc mọi method được phép: allowlist vẫn có giá trị với `TRACE` hoặc methods không được cho phép. Nếu hệ thống muốn theo dõi raw HTTP method từ wire, cần quan sát ở HTTP server/ingress thay vì suy rằng đối tượng `HttpMethod` còn giữ nguyên ký tự ban đầu.

## 12. Session, logout, authentication và serialization khi nâng

Thay đổi CSRF/firewall hiếm khi sống độc lập. Browser dùng session có thể gặp các regression chỉ xuất hiện khi user login/logout hoặc khi load balancer chuyển replica.

### 12.1. Những thành phần cần kiểm thử

| Cơ chế | Servlet | Reactive | Điều cần xác minh |
| --- | --- | --- | --- |
| Session | `HttpSession` | `WebSession` | Tạo, hết hạn, gia hạn, logout |
| Security context | `SecurityContextRepository` | `ServerSecurityContextRepository` | Context tồn tại đúng phiên và không leak |
| CSRF token store | `HttpSessionCsrfTokenRepository` hoặc cookie | `WebSessionServerCsrfTokenRepository` hoặc cookie | Token đúng session, refresh sau login/logout |
| Auth manager | `AuthenticationManager` | `ReactiveAuthenticationManager` | Không dùng blocking adapter trong Reactive event loop |
| User store | `UserDetailsService` | `ReactiveUserDetailsService` | User/status/authority được map đúng |
| Logout | Servlet logout filter/handler | Reactive logout WebFilter/handler | Session invalidated/token rotate |
| Session serialization | Phụ thuộc serialization/proxy/store | Phụ thuộc WebSession/store | Bản cũ/bản mới rolling deploy có đọc được dữ liệu? |

Nếu ứng dụng lưu serialized `SecurityContext` ở Redis/JDBC, thay module hoặc serialization (chẳng hạn đổi cơ chế hỗ trợ Jackson khi lên Boot 4/Security 7) có thể khiến **replica phiên bản mới không đọc được session của bản cũ**. Đó là rủi ro rollout/rollback thực tế. Tùy công nghệ và chính sách tổ chức, có thể cần chuyển schema, giải pháp tương thích hai chiều, hoặc chấp nhận người dùng đăng nhập lại theo kế hoạch.

### 12.2. Login/logout URL và matcher

Form login/filter-provided endpoints chỉ hoạt động nếu request thuộc chain chứa filter. Một chain `securityMatcher("/admin/**")` có `formLogin` nhưng login URL vẫn `/login` có thể làm login endpoint rơi ngoài chain ấy. Khi đổi matcher trong 7.x, cần test:

- `GET /login` tạo trang login hoặc custom page đúng.
- `POST /login` có CSRF token hợp lệ, xác thực user và thiết lập session đúng.
- `POST /logout` có token hợp lệ, vô hiệu session/context và token cũ.
- Request sau logout không còn truy cập `/admin/**` bằng session cũ.
- URL error/redirect sau proxy/TLS không chuyển sang HTTP nội bộ.

### 12.3. Kiểm thử cookie trên browser, không chỉ mock request

`Secure`, `HttpOnly`, `SameSite`, `Domain` và `Path` có thể khác giữa local HTTP và staging HTTPS. Những lỗi này không nhất thiết xuất hiện trong `MockMvc`/`WebTestClient.bindToApplicationContext`. Thử browser thật trên public origin, kiểm tra Network tab và cookie jar, kết hợp TLS termination và trusted forwarded headers.

## 13. Reactive migration: đừng đổi tên lớp rồi cho rằng hành vi như Servlet

Spring WebFlux khác Spring MVC ở loại request, filter chain, authentication manager, CSRF repository và CORS source. Khi nâng version, phải đọc phần **Reactive** của migration guide/reference thay vì chỉ áp dụng danh sách Servlet.

### 13.1. Một cấu hình WebFlux hiện đại

```java
package com.example.security.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveProtectionConfiguration {

    @Bean
    SecurityWebFilterChain browserChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/public/**", "/error").permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .csrf(Customizer.withDefaults())
            .headers(headers -> headers
                .contentSecurityPolicy(csp -> csp
                    .policyDirectives(
                        "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
                    )
                )
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
```

Đây là **browser session/WebSession** use case; không dùng `SessionCreationPolicy.STATELESS` của Servlet cho Reactive. Nếu service thực sự là Bearer-only API, cần config Resource Server Reactive và repository phù hợp theo threat model; không tắt CSRF mọi WebFlux service chỉ vì tên “Reactive”.

### 13.2. Bản đồ các API không hoán đổi

| Servlet | Reactive | Tác động kiểm thử |
| --- | --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` | Cấu hình khác builder |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Hai proxy/filter pipelines khác |
| `RequestMatcher` | `ServerWebExchangeMatcher` | Test cách match path khác |
| `authorizeHttpRequests`/`requestMatchers` | `authorizeExchange`/`pathMatchers` | Test rule theo HTTP stack |
| `HttpSessionCsrfTokenRepository` | `WebSessionServerCsrfTokenRepository` | Test token/session lifecycle |
| `CookieCsrfTokenRepository` | `CookieServerCsrfTokenRepository` | Header/raw/XOR token handling |
| Servlet `CorsConfigurationSource` | `org.springframework.web.cors.reactive.CorsConfigurationSource` | Test OPTIONS ở đúng pipeline |
| `StrictHttpFirewall` | `StrictServerWebExchangeFirewall` (6.4+) | Test URL encoding/method reject |
| `MockMvc` | `WebTestClient` | Khác cách gắn security tests |

**Hai method có tên giống nhau không có nghĩa dùng cùng request handler**. Ví dụ `http.csrf(Customizer.withDefaults())` tồn tại ở cả hai DSL nhưng các loại repository, filter, token presentation và `ServerWebExchange`/`HttpServletRequest` khác nhau.

### 13.3. Multi-chain Reactive cũng cần fallback

```java
@Bean
@Order(1)
SecurityWebFilterChain api(ServerHttpSecurity http) {
    return http
        .securityMatcher(ServerWebExchangeMatchers.pathMatchers("/api/**"))
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallback(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .pathMatchers("/admin/**").hasRole("ADMIN")
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .csrf(Customizer.withDefaults())
        .build();
}
```

Đoạn này chỉ minh họa **chain selection**; API HTTP Basic có thể có nguy cơ CSRF nếu credential được browser tự đính kèm. **Không** mặc định cho rằng chain API ví dụ an toàn để tắt CSRF. Trong code thực tế, bổ sung CORS, CSP, HSTS, session/entry point và nguồn user phù hợp với từng chain.

Nếu một chain hẹp `/api/**` được khai báo mà **không có fallback**, `/admin/**` có thể bị bỏ ngoài security pipeline. Test chuỗi `securityMatcher`/`@Order` ngay cả khi chỉ chuyển từ 6.5 sang 7.0 mà không thay các URL.

## 14. Thiết kế regression suite: test nào bắt buộc phải giữ?

### 14.1. Test theo threat model, không chỉ theo endpoints phổ biến

Hãy lập một ma trận có thể chạy **trước** và **sau** nâng version. Thường cần ít nhất các nhóm sau:

| Nhóm bảo vệ | Request âm (phải bị chặn) | Request dương (phải được phép) | Lỗi thường gặp khi nâng |
| --- | --- | --- | --- |
| Authentication | Private GET không credential | GET với credential hợp lệ | Entry point/bean provider đổi |
| Authorization | USER gọi `/admin/**` | ADMIN gọi `/admin/**` | Matcher/role prefix khác |
| Chain coverage | URL ngoài API chain | URL fallback với login hợp lệ | Không còn chain mặc định |
| CSRF Servlet/browser | POST thiếu/sai token | POST token đúng | Handler/XOR/deferred token |
| SPA cookie/header | Cookie tự gửi nhưng thiếu CSRF header | Raw cookie token được gửi trong header | Cookie hostname/rotation |
| CORS | OPTIONS từ origin lạ | OPTIONS origin allowlisted | Sai source, 401 preflight |
| CSP | HTML thiếu CSP hoặc bị nới quá mức | Header hợp lệ, frontend tải asset dự kiến | Header writer đổi chain |
| HSTS | HTTPS public thiếu HSTS khi policy yêu cầu | HTTPS có HSTS đúng | Proxy scheme/headers |
| Firewall | `/admin//x`, encoded slash, TRACE | URL chuẩn/allowed method | Default Strict thay đổi |
| Session/login | Cookie cũ truy cập sau logout | Login/session mới hoạt động | Serialization/session store |
| Logout/CSRF token | Dùng token cũ sau logout | Bootstrap token mới rồi POST | Token rotation |
| Context/servlet path | `/app/mvc/admin/**` bị bỏ sót | URL đúng role trong MVC | PathPattern migration |
| Management port | Actuator endpoint private public hóa | Health endpoint đúng exposure | Context/auto-config |
| Proxy rewrite | Public URL route nhầm chain | URL canonical đúng chain | Prefix/forwarded headers |

**Kiểm thử âm có giá trị đặc biệt:** “Không ai truy cập được ADMIN khi thiếu quyền” và “cookie session POST thiếu token vẫn bị chặn” là những bất biến quan trọng hơn việc home page trả 200.

### 14.2. Chia suite thành bốn tầng

```text
Tầng A — Unit tests
  Matcher, firewall, token handler, authorization decision, property validation

Tầng B — Spring integration tests
  MockMvc hoặc WebTestClient với Spring Security filters/beans thật

Tầng C — HTTP tests (process thực)
  Server port thật, cookie jar, JWT decoder, login/logout, preflight

Tầng D — Staging/HTTPS qua ingress
  Public URL, TLS termination, CSP/HSTS, forwarded headers,
  CDN/edge, session across replicas, browser behavior
```

Một test ở Tầng B có thể thành công nhưng Tầng D vẫn sai vì proxy xóa `Set-Cookie` hoặc frontend ở khác origin không thể đọc cookie CSRF. Ngược lại, một 400 từ edge có thể che mất lỗi authorization matcher ở backend. Cần nhiều lớp bằng chứng.

### 14.3. Expected status theo security mechanism

| Trường hợp | Status thường gặp | Nguồn cần xác minh |
| --- | --- | --- |
| API Bearer thiếu token | 401 | Authentication entry point |
| Browser chưa login | 302 về login hoặc entry point khác | `formLogin`/exception handling |
| User đã login nhưng thiếu ADMIN | 403 | Authorization |
| POST thiếu CSRF | 403 | CSRF filter |
| OPTIONS sai origin | Có thể 403/không cấp CORS headers | CORS source/proxy |
| URL bị Strict firewall reject | Thường 400 | Firewall hoặc HTTP parser |
| URL không có handler | 404 | Routing; cũng có thể custom rejected handler |
| Method không được handler hỗ trợ | 405 | Routing; nhưng firewall có thể chặn trước |

**Không kết luận chỉ từ status.** Cùng 403 có thể do CSRF, authorization hoặc CORS. Test nên có user, CSRF token và headers chủ động để cô lập nguyên nhân.

## 15. Bộ test Servlet minh họa bằng `MockMvc`

Các ví dụ giả sử đã có `MockMvc mvc` được cấu hình qua Spring Security, và controller test `GET /public/ping`, `GET /admin/report`, `POST /orders` trả HTTP 200 khi request hợp lệ. Nếu handler thực tế trả 201/204 thì thay expected status theo contract.

### 15.1. Authentication và authorization

```java
import org.junit.jupiter.api.Test;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void publicAndAdminAuthorizationSurviveUpgrade() throws Exception {
    mvc.perform(get("/public/ping"))
        .andExpect(status().isOk());

    mvc.perform(get("/admin/report")
            .with(user("viewer").roles("USER")))
        .andExpect(status().isForbidden());

    mvc.perform(get("/admin/report")
            .with(user("admin").roles("ADMIN")))
        .andExpect(status().isOk());
}
```

`with(user(...))` cung cấp test authentication, **không** chứng minh user store/password encoder thực đang đúng sau khi migrate. Phải có thêm login flow test với credentials thật của fixture.

### 15.2. CSRF không bị tắt trong browser chain

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

@Test
void browserPostStillNeedsCsrfToken() throws Exception {
    mvc.perform(post("/orders").with(user("viewer")))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("viewer"))
            .with(csrf().useInvalidToken()))
        .andExpect(status().isForbidden());

    mvc.perform(post("/orders")
            .with(user("viewer"))
            .with(csrf()))
        .andExpect(status().isOk());
}
```

Đây là **regression test cho `CsrfFilter`**, nhưng chưa kiểm tra SPA đọc được cookie token. Nếu ứng dụng dùng `csrf.spa()` từ 7.0, cần thêm test `GET /csrf` sinh `XSRF-TOKEN` rồi POST với `Cookie: XSRF-TOKEN` và `X-XSRF-TOKEN` thực.

### 15.3. CSP/HSTS trên response phù hợp

```java
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;

@Test
void servletHeadersAreStillApplied() throws Exception {
    mvc.perform(get("/public/ping").secure(true))
        .andExpect(status().isOk())
        .andExpect(header().exists("Content-Security-Policy"))
        .andExpect(header().string("X-Content-Type-Options", "nosniff"))
        .andExpect(header().exists("Strict-Transport-Security"));
}
```

`secure(true)` mô phỏng HTTPS ở Servlet mock request, **không** xác minh proxy public đã cấu hình đúng. Sau migration, chạy thêm HTTP test thực qua TLS/ingress, kiểm tra HSTS và cookie `Secure`/`SameSite`.

### 15.4. CORS origin đúng và sai

```java
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;

@Test
void servletCorsPreflightRemainsRestricted() throws Exception {
    mvc.perform(options("/orders")
            .header("Origin", "https://app.example.com")
            .header("Access-Control-Request-Method", "POST")
            .header("Access-Control-Request-Headers", "content-type,x-csrf-token"))
        .andExpect(header().string(
            "Access-Control-Allow-Origin", "https://app.example.com"));

    mvc.perform(options("/orders")
            .header("Origin", "https://untrusted.example")
            .header("Access-Control-Request-Method", "POST"))
        .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
}
```

Đây là kịch bản cho **CORS source đã cấu hình đúng**. Negative preflight có thể trả 403 hoặc status khác, nhưng tuyệt đối không cấp `Access-Control-Allow-Origin` cho origin lạ. Nếu MockMvc khởi tạo thủ công, bảo đảm đã gắn `springSecurity()`.

## 16. Bộ test Reactive minh họa bằng `WebTestClient`

Reactive tests phải chạy trong đúng WebFlux application context và áp dụng `springSecurity()`. Nếu chỉ bind client vào một handler tùy ý mà không có Security WebFilters, những kết quả “endpoint trả 200” không chứng minh chain, firewall, CORS hay CSRF hoạt động.

### 16.1. Cấu hình test client

```java
import org.springframework.test.web.reactive.server.WebTestClient;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient client = WebTestClient
    .bindToApplicationContext(applicationContext)
    .apply(springSecurity())
    .configureClient()
    .build();
```

Biến `applicationContext` và `client` nằm trong fixture của test class. Đoạn trên minh họa cách tạo client cho integration test, không phải một Java class standalone.

### 16.2. Authorization và CSRF khi chuyển phiên bản

Giả sử WebFlux router/controller có `GET /public/ping`, `GET /admin/report` và `POST /orders`, trả HTTP 200 khi hợp lệ:

```java
import org.junit.jupiter.api.Test;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@Test
void reactiveSecurityContractSurvivesUpgrade() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("admin").roles("ADMIN"))
        .get().uri("/admin/report")
        .exchange()
        .expectStatus().isOk();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .post().uri("/orders")
        .exchange()
        .expectStatus().isForbidden();

    client.mutateWith(mockUser("viewer").roles("USER"))
        .mutateWith(csrf())
        .post().uri("/orders")
        .exchange()
        .expectStatus().isOk();
}
```

`mockUser()` của Spring Security Test không chứng minh authentication service thực có thể truy vấn user hoặc xác thực password. Cần bổ sung integration test login/session và resource server JWT thật nếu dự án sử dụng. `csrf()` chứng minh filter chấp nhận token do test cung cấp; với Reactive SPA còn phải test `GET /csrf` hoặc cookie-token flow riêng.

### 16.3. Reactive firewall khi nâng lên 6.4+

Nếu muốn test trực tiếp `StrictServerWebExchangeFirewall` mà không phụ thuộc router, dùng `MockServerWebExchange` và Reactor `StepVerifier`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.firewall.StrictServerWebExchangeFirewall;
import org.springframework.security.web.server.firewall.ServerExchangeRejectedException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@Test
void strictReactiveFirewallRejectsSuspiciousPath() {
    var firewall = new StrictServerWebExchangeFirewall();
    var exchange = MockServerWebExchange.from(
        MockServerHttpRequest.get("/admin;mode=x/report")
    );

    StepVerifier.create(
        Mono.defer(() -> firewall.getFirewalledExchange(exchange))
    )
        .expectError(ServerExchangeRejectedException.class)
        .verify();
}
```

Đoạn này yêu cầu `spring-security-web` 6.4+ và `reactor-test`. Unit test cho `new StrictServerWebExchangeFirewall()` **không tự xác nhận** application `WebFilterChainProxy` đang sử dụng đúng firewall bean. Kết hợp WebTestClient integration và HTTP public tests.

### 16.4. CORS headers và CSP trên WebFlux

```java
@Test
void reactiveCorsAndCspAreStillPresent() {
    client.get().uri("/public/ping")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("Content-Security-Policy")
        .expectHeader().valueEquals(
            "X-Content-Type-Options", "nosniff");

    client.options().uri("/orders")
        .header("Origin", "https://app.example.com")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers", "content-type,x-csrf-token")
        .exchange()
        .expectHeader().valueEquals(
            "Access-Control-Allow-Origin", "https://app.example.com");

    client.options().uri("/orders")
        .header("Origin", "https://untrusted.example")
        .header("Access-Control-Request-Method", "POST")
        .exchange()
        .expectHeader().doesNotExist("Access-Control-Allow-Origin");
}
```

Những expectations trên giả định `CorsConfigurationSource` Reactive đã được cấu hình như mục 9. Status cho origin bị từ chối có thể thay đổi, nhưng không được cấp quyền CORS. Với HSTS, phải kiểm tra qua HTTPS public hoặc một request test thật sự được nhận là secure; đừng kỳ vọng WebTestClient in-memory tự mô phỏng đầy đủ TLS termination.

## 17. Kiểm thử HTTP công khai và chẩn đoán sau khi chạy ứng dụng thật

### 17.1. CORS, CSP, HSTS trên staging

Các command sau dùng hostname minh họa. Chỉ thực hiện trên hệ thống bạn được phép kiểm thử:

```bash
# CORS preflight hợp lệ.
curl -i -X OPTIONS "https://api.staging.example.com/orders" \
  -H "Origin: https://app.staging.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"

# CORS preflight không hợp lệ.
curl -i -X OPTIONS "https://api.staging.example.com/orders" \
  -H "Origin: https://untrusted.example" \
  -H "Access-Control-Request-Method: POST"

# Headers mà trình duyệt thấy từ HTTPS public.
curl -i "https://app.staging.example.com/"
curl -i "https://api.staging.example.com/public/ping"
```

**CORS check bằng `curl` không thay thế test browser**: `curl` không thực thi Same-Origin Policy hoặc quy tắc cookie của browser. Nó chỉ giúp quan sát HTTP response. CSP cần được kiểm tra trên chính response HTML frontend; HSTS trên HTTPS public.

### 17.2. CSRF cookie round-trip

Với một **Servlet SPA dùng cookie**:

```text
GET /csrf
  -> nhận Set-Cookie: XSRF-TOKEN=T (khi cần)

POST /orders
  Cookie: JSESSIONID=...; XSRF-TOKEN=T
  KHÔNG có X-XSRF-TOKEN
  -> kỳ vọng bị CSRF chặn

POST /orders
  Cookie: JSESSIONID=...; XSRF-TOKEN=T
  X-XSRF-TOKEN: wrong
  -> kỳ vọng bị CSRF chặn

POST /orders
  Cookie: JSESSIONID=...; XSRF-TOKEN=T
  X-XSRF-TOKEN: T
  -> kỳ vọng vượt qua CSRF, tiếp tục authorization/handler
```

Không dán token/session thật vào log hay tài liệu công khai. Dùng cookie-aware test client hoặc browser E2E, giữ phiên qua login/logout. Với frontend khác origin, JavaScript **không tự đọc được cookie host-only của API** dù CORS được cấu hình đúng; phải kiểm thử kiến trúc token bootstrap hoặc BFF.

### 17.3. URL bất thường và reverse proxy

```bash
# Chỉ dùng tại staging/sandbox được cấp phép.
curl --path-as-is -i \
  "https://api.staging.example.com/admin//report"

curl --path-as-is -i \
  "https://api.staging.example.com/admin;v=1/report"
```

`--path-as-is` giảm việc `curl` tự normalize một số path; nó **không bảo đảm** ingress/Reactor Netty/Servlet container không normalize. Khi thấy status 400, xác định tầng nào chặn. Khi thấy 404, không mặc định request đã đi qua Security; có thể là routing hoặc custom rejection handler.

### 17.4. Kiểm tra redirect/cookie sau TLS proxy

Sau nâng Boot/Security, reverse proxy có thể truyền `Forwarded`/`X-Forwarded-Proto` khác hoặc ứng dụng đổi cách đọc header. Kiểm tra:

- `Location` của login/redirect có dùng **HTTPS public** và hostname đúng?
- Cookie session có `Secure`/`HttpOnly`/`SameSite`/`Path` theo policy?
- HSTS trên HTTPS public có `max-age`/`includeSubDomains` đúng?
- Cookie login có sống qua redirect và qua nhiều replicas không?
- Proxy đã xóa/ghi đè forwarded headers do client gửi để chống spoofing chưa?
- `/admin/**` ở public URL có được rewrite thành backend path khớp chain không?

Nếu proxy phục vụ static assets hoặc frontend HTML thay cho Spring, Security header của app chỉ áp dụng response đi qua app; edge/CDN cũng cần policy riêng được kiểm chứng.

## 18. Quy trình nâng phiên bản an toàn, có cổng kiểm soát

### Giai đoạn A — Inventory và baseline

1. Khóa thời điểm code/config hiện tại và dependency graph đã resolve.
2. Ghi Spring Boot/Framework/Security/JDK, web application type, server/ingress, session store và các starter liên quan.
3. Vẽ danh sách từng `SecurityFilterChain`/`SecurityWebFilterChain` với `@Order` và matcher.
4. Lập manifest cho CSRF, CORS, CSP, HSTS, firewall, session, authentication, authorization và login/logout.
5. Chạy regression baseline (bao gồm negative tests) trên version cũ, lưu kết quả và các ngoại lệ đã biết.

### Giai đoạn B — Đọc và phân loại tài liệu

6. Tìm tài liệu pinned cho **version nguồn** và **version đích**.
7. Đọc migration preparation (như 6.5 → 7), target migration và release notes các minor/patch liên quan.
8. Mở Javadoc các API đang dùng: ghi `Since`, `Deprecated`, replacement, signature, default behavior và web stack.
9. Phân loại từng thay đổi: compile-time, runtime default, URL matching, HTTP protocol, session serialization, security behavior.
10. Đưa vào bảng change record cùng test và người phụ trách.

### Giai đoạn C — Refactor có kiểm soát

11. Refactor DSL/bean mà **không** đổi authentication mechanism ngoài ý định.
12. Thử PathPattern migration, tính lại context/servlet path và URL proxy rewrite.
13. Giữ CSRF cho browser cookie; điều chỉnh token handler/SPA theo đúng version.
14. Giữ CORS source đúng stack/chain, CSP/HSTS và firewall policy chặt.
15. Đảm bảo có fallback security chain và các login/logout URLs nằm đúng chain.

### Giai đoạn D — CI và staging

16. Compile, chạy unit/integration tests cho Servlet/Reactive và ứng dụng thực tế.
17. Chạy cùng ma trận HTTP contract trên version nguồn và version đích; phân loại thay đổi **mong muốn** và **regression**.
18. Khởi động staging với **TLS/ingress/session topology giống production**; kiểm tra CORS/CSRF/cookie/headers/redirect bằng browser và HTTP client.
19. Chạy thử rolling deploy với session store/schema nếu dùng cluster; kiểm tra compatibility và rollback.
20. Kiểm tra Actuator/management context/port, rate limit, WAF và logs để không lộ thông tin nhạy cảm.

### Giai đoạn E — Triển khai và hậu kiểm

21. Triển khai canary hoặc rolling rollout có quy trình rollback đã thử.
22. Quan sát lỗi 401/403 (phân tách CSRF/auth), firewall rejection 400, CORS preflight, CSP reports và session churn.
23. Kiểm tra lại HTTP contracts từ public URL; không dựa vào cảm giác UI “vẫn chạy”.
24. Chỉ đóng migration khi có bằng chứng test, thay đổi được review và danh sách nợ kỹ thuật rõ ràng.

**Cổng chặn phát hành:** bất kỳ regression nào cho phép request thiếu quyền hoặc thiếu CSRF token được xử lý, làm lộ endpoint quản trị hoặc bỏ header/cookie security mà policy bắt buộc thì không nên được xem là “minor UI issue”.

## 19. Runbook: đọc triệu chứng và chọn tài liệu/API cần kiểm tra

### Lỗi A — `Cannot resolve method 'spa'` khi migrate CSRF

**Kiểm tra:** dự án đã resolve `spring-security-config` 7.0+ hay chưa? Code đang dùng Servlet `HttpSecurity` hay Reactive `ServerHttpSecurity`? `CsrfConfigurer.spa()` là API cho **Servlet từ 7.0**, không phải API có ở 6.5 hoặc WebFlux.

**Cách xử lý:** xem Javadoc signature và migration đúng stack. Không thêm dependency Servlet vào WebFlux để chữa compile error; chọn chiến lược CSRF/token endpoint đúng Reactive hoặc chuẩn bị handler SPA cho 6.x.

### Lỗi B — `AntPathRequestMatcher`/`MvcRequestMatcher` không còn compile

**Kiểm tra:** version đích 7.x và các APIs removed. Đọc 6.5 **Web Migrations**, mục `PathPatternRequestMatcher`, chú thích context/servlet path và parser.

**Cách xử lý:** dùng matcher phù hợp, sửa import và ngữ nghĩa pattern, test URL có và không có trailing slash, context root, servlet path, path encoding và proxy rewrite. Không mở `/**` để né test.

### Lỗi C — Sau migrate, `/admin/**` bỗng public

**Kiểm tra:** số `SecurityFilterChain`, `@Order`, `securityMatcher`, fallback chain, rule order. Đọc Java Configuration cho đúng version.

**Cách xử lý:** tạo fallback/deny-by-default phù hợp và test USER vs ADMIN trên route thường và route qua ingress. `anyRequest()` chỉ có hiệu lực **trong chain** đã chọn.

### Lỗi D — POST JSON của SPA bị 403 sau login/logout

**Kiểm tra:** `XSRF-TOKEN` cookie, `X-XSRF-TOKEN` header, deferred token, BREACH XOR handler, token rotation và session. Xác định exception `MissingCsrfTokenException` hay `InvalidCsrfTokenException` trước khi nghi authorization.

**Cách xử lý:** dùng token bootstrap mới sau auth/logout, chọn `spa()` trên Servlet 7 khi phù hợp hoặc handler đúng phiên bản; đừng tắt CSRF browser.

### Lỗi E — CORS preflight bị 401, còn GET same-origin vẫn OK

**Kiểm tra:** OPTIONS có đi qua đúng chain/CORS filter trước authentication không? Servlet/Reactive `CorsConfigurationSource` đúng package? Origin có đúng scheme/host/port, allowed headers/methods?

**Cách xử lý:** cấu hình nguồn CORS phù hợp và test preflight. `permitAll()` cho OPTIONS không thay thế CORS policy. CORS đúng cũng không thay CSRF.

### Lỗi F — Mất CSP/HSTS trên một số endpoint

**Kiểm tra:** response đi qua chain nào, có bị `web.ignoring()` không, CDN/ingress có phục vụ trực tiếp không? HSTS có được đo bằng HTTPS public?

**Cách xử lý:** gắn headers đúng chain/edge, giữ CSP do ứng dụng quyết định, HSTS nhất quán theo hostname và kiểm tra forwarded headers/trusted proxy.

### Lỗi G — Request URL lạ trả 400 sau khi nâng 6.3 → 6.4+

**Kiểm tra:** `StrictServerWebExchangeFirewall` ở Reactive, path/method/header bị reject, hoặc ingress/HTTP server đã chặn trước? Xem Javadoc `Since: 6.4` và test trực tiếp firewall.

**Cách xử lý:** sửa client/proxy/URL contract nếu có thể. Không dùng `ServerWebExchangeFirewall.INSECURE_NOOP`, `setUnsafeAllowAnyHttpMethod(true)` hoặc nới encoded slash/semicolon không qua review.

### Lỗi H — Test method `get` viết thường khác ở 7.2

**Kiểm tra:** Spring Framework `HttpMethod.valueOf` chuẩn hóa case; `StrictServerWebExchangeFirewall` có thể không thấy chữ thường như một giá trị riêng. Đọc *What's New 7.2*.

**Cách xử lý:** điều chỉnh regression tests theo đúng version. Nếu cần kiểm tra raw request line, quan sát ở HTTP server/ingress, không nới allowed method list.

### Lỗi I — Login redirect tới `http://service:8080` thay vì HTTPS public

**Kiểm tra:** Boot forwarded-header strategy theo version, trusted ingress, scheme/host và filter/redirect. Không tin `X-Forwarded-*` do client ngoài tự gửi.

**Cách xử lý:** sửa proxy trust và config theo Boot migration, test login/logout qua public HTTPS. Đừng chỉ sửa redirect URL hard-coded trong controller.

### Lỗi J — User đang đăng nhập bị logout hàng loạt trong rolling deploy

**Kiểm tra:** session serialization, SecurityContext codec, Jackson/version, Redis/JDBC store, cookie flags và session ID rotation. Đọc Boot/Security migration cho serialization.

**Cách xử lý:** xác định khả năng đọc chéo session giữa replicas, xây chiến lược tương thích hoặc kế hoạch user re-login, thử rollback với dữ liệu session thật đã được bảo vệ.

### Lỗi K — Test `with(csrf())` và `mockUser()` pass nhưng production fail

**Kiểm tra:** test đã thực sự gọi security filters chưa? Authentication provider/JWT decoder, cookie hostname, browser CSP, CORS preflight, TLS proxy, session store có được kiểm thử không?

**Cách xử lý:** thêm HTTP end-to-end qua public ingress và login thực với test account. Test helper chỉ cô lập một phần security behavior; không đại diện đầy đủ cho production browser.

## 20. Bài tập thực hành

### Bài 1 — Đọc Javadoc và xác định khả dụng

Tìm `PathPatternRequestMatcher`, `CsrfConfigurer.spa()` và `StrictServerWebExchangeFirewall` trong Javadoc cho các dòng 6.3, 6.5, 7.0. Ghi package, `Since`, owner stack, method signature và một test cần viết. Giải thích tại sao `WebFilterChainProxy` tồn tại lâu hơn không có nghĩa public API Reactive firewall đã có từ WebFlux 5.x.

### Bài 2 — Lập migration plan cho Boot 3/Security 6.5 → Boot 4/Security 7

Cho một ứng dụng Servlet có form login, SPA cookie, `/api/**` cho JWT và `/admin/**` cho session. Hãy xây bảng thay đổi DSL, request matchers, CSRF SPA, security chains, CORS, CSP/HSTS và session serialization. Đặt tiêu chí go/no-go và rollback.

### Bài 3 — PathPattern và Servlet path

Một Servlet ứng dụng được deploy dưới context path `/app`, DispatcherServlet map `/mvc/*`, handler `/orders/123`. Viết matcher bảo vệ `/mvc/orders/**` bằng `PathPatternRequestMatcher.Builder.basePath`, rồi test URL public `/app/mvc/orders/123` và các biến thể trailing slash/encoded slash. Vì sao không đặt `/app` trong matcher?

### Bài 4 — CSRF SPA sau login/logout

Một SPA dùng cookie `XSRF-TOKEN`, gửi raw token bằng `X-XSRF-TOKEN`. Sau login/logout request POST bị 403. Hãy phân biệt CSRF token cũ, BREACH handler, deferred token và session. Viết flow bootstrap và ít nhất ba negative tests (thiếu token, sai token, token cũ).

### Bài 5 — CORS Servlet so với Reactive

Tạo hai ứng dụng độc lập cùng allowlist `https://app.example.com`; cấu hình CORS source đúng package. Dùng `MockMvc` và `WebTestClient` kiểm tra OPTIONS origin hợp lệ và origin lạ, có `Access-Control-Request-Headers: x-csrf-token`. Giải thích vì sao import trùng tên `UrlBasedCorsConfigurationSource` không dùng thay cho nhau.

### Bài 6 — Firewall và lỗi 400

Nâng WebFlux Security 6.3 lên 6.5. Một request `/admin;mode=1/report` nay trả 400; developer muốn bật `setAllowSemicolon(true)`. Hãy xác minh tầng từ chối, giải thích rủi ro path ambiguity, đề xuất cách sửa client và những negative tests cần có trước khi cân nhắc ngoại lệ.

### Bài 7 — HSTS qua proxy

Staging có HTTPS public nhưng backend HTTP. `MockMvc`/`WebTestClient` thấy headers nhưng browser không thấy HSTS hoặc bị redirect HTTP. Hãy vẽ đường đi, xác định ai sở hữu header, kiểm tra forwarded-header strategy, trusted proxy và response cuối cùng.

### Bài 8 — Session compatibility khi rolling deploy

Hai phiên bản của ứng dụng dùng chung Redis session store, serialization `SecurityContext` khác sau migration. Viết một test ma trận: login ở pod cũ, request ở pod mới; login ở pod mới, request ở pod cũ; logout và rollback. Quyết định khi nào có thể deploy song song, khi nào cần migration schema hoặc đăng nhập lại.

## 21. Checklist khi review Pull Request nâng Spring Security

- [ ] Đã ghi **exact source/target versions**, BOM/patch và dependency graph thực sự được resolve.
- [ ] Đã đọc Reference Guide, API/Javadoc, migration preparation, target migration và release notes theo **đúng phiên bản**.
- [ ] Đã phân loại API removed/deprecated, thay đổi default, khác biệt stack và các điều kiện áp dụng.
- [ ] Code Servlet không sử dụng `WebSecurityConfigurerAdapter`/`.and()` cũ của target 7; Lambda DSL có đúng scope.
- [ ] `PathPatternRequestMatcher` và rule paths đã được thử với context/servlet path, trailing slash, encoded URL và proxy rewrite.
- [ ] Có danh sách `SecurityFilterChain`/`SecurityWebFilterChain`, `@Order`, chain matcher và fallback; không có URL nhạy cảm ngoài tất cả chain.
- [ ] CSRF cho browser cookie/session vẫn bật, POST thiếu/sai token bị từ chối; token hợp lệ được xử lý.
- [ ] SPA token được thử bằng cookie/header round-trip thực; token refresh sau login/logout.
- [ ] WebFlux không sử dụng Servlet `CsrfConfigurer.spa()`/`HttpSessionCsrfTokenRepository`/`StrictHttpFirewall`.
- [ ] CORS source đúng stack/chain; OPTIONS preflight origin đúng/sai được thử và credential CORS không dùng wildcard.
- [ ] CSP của **HTML frontend** có policy đúng, không dựa vào CSP trên API JSON; HSTS được kiểm tra ở HTTPS public.
- [ ] Static/public URL vẫn nhận security headers khi policy yêu cầu; `permitAll()` và `web.ignoring()` không bị nhầm.
- [ ] Firewall giữ strict defaults; URL bất thường và HTTP methods được kiểm thử theo version/ingress thực.
- [ ] Session, cookie flags, login/logout, rotation và serialization qua nhiều replicas có test.
- [ ] Management port/Actuator, error/forward dispatch, redirect và proxy forwarded headers được xác minh.
- [ ] Suite có cả tests âm, dương, unit/integration, browser/HTTP staging và có ghi nhận thay đổi mong muốn.
- [ ] Có quan sát sau deploy (401/403, CSRF, CORS, CSP, firewall reject, session churn) mà không log secrets.
- [ ] Có phương án rollback cho code, config, cookie/session store và các header có tác động lâu dài như HSTS.

## Tài liệu tham khảo chính thức

1. [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/index.html) — khuyến nghị chuẩn bị trên 6.5 và các bước sang 7; kiểm tra phiên bản hiển thị ở đầu trang.
2. [Spring Security 6.5 — Configuration Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html) — Lambda DSL, `.with()`, `dispatcherTypeMatchers` và các API liên quan.
3. [Spring Security 6.5 — Web Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html) — PathPattern matcher, servlet path, login filters và các thay đổi HTTP.
4. [Spring Security 7.0 — What's New](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) — các removals/new APIs của major 7.
5. [Spring Security 7.0 — Servlet Java Configuration](https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html) — `SecurityFilterChain`, chain matcher, order và fallback.
6. [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — `ServerHttpSecurity`/`SecurityWebFilterChain`.
7. [Spring Security — PathPatternRequestMatcher Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/servlet/util/matcher/PathPatternRequestMatcher.html) — semantics của context/servlet path và parser.
8. [Spring Security — Servlet CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html), [Reactive CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) — token repository/handler, SPA, deferred token/BREACH và test.
9. [Spring Security — Servlet CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html), [Reactive CORS](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html) — preflight và nguồn cấu hình.
10. [Spring Security — Servlet Security Headers](https://docs.spring.io/spring-security/reference/servlet/exploits/headers.html), [Reactive Security Headers](https://docs.spring.io/spring-security/reference/reactive/exploits/headers.html) — CSP/HSTS và defaults.
11. [Spring Security — Servlet HTTP Firewall](https://docs.spring.io/spring-security/reference/servlet/exploits/firewall.html), [Reactive Firewall](https://docs.spring.io/spring-security/reference/reactive/exploits/firewall.html) — URL normalization, method allowlist và rejection.
12. [Spring Security 6.5 API — ServerWebExchangeFirewall](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/firewall/ServerWebExchangeFirewall.html) — `Since: 6.4`.
13. [Spring Security 7.2 — What's New](https://docs.spring.io/spring-security/reference/7.2/whats-new.html) — thay đổi method case của `StrictServerWebExchangeFirewall`.
14. [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html), [MockMvc CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html) và [WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html) — gắn Security filters vào test.
15. [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html), [Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/index.html) — xác minh config theo bản Boot đã resolve.

**Câu hỏi tự đánh giá:** Khi nâng Spring Security, tại sao compile pass chưa đủ? Làm sao phân biệt một API `Since: 7.0` với một API chỉ được dùng trong migration preparation 6.5? Vì sao `securityMatcher` khác `requestMatchers`? Các thay đổi CSRF deferred/BREACH có thể làm SPA sai ra sao? Tại sao phải test HSTS trên HTTPS public và CORS OPTIONS trước authentication? Nếu URL admin mới trả 200, bằng chứng nào giúp xác định matcher, chain, authorization hay proxy là nguyên nhân? Và ở bước nào bạn sẽ quyết định dừng phát hành hoặc rollback?
