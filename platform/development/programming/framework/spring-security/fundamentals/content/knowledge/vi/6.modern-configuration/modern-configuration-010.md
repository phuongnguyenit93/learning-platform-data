# Nhận diện API cũ trong ví dụ và tra cứu cú pháp đúng phiên bản Spring Security đang dùng

Một bài hướng dẫn Spring Security trên Internet có thể chạy hoàn hảo với môi trường của tác giả nhưng không biên dịch trong dự án của bạn. Ví dụ dùng `WebSecurityConfigurerAdapter`, `antMatchers`, `authorizeRequests` hoặc cách nối DSL bằng `.and()` từng hợp lệ trong những đời Spring Security trước, nhưng đã bị deprecated hoặc loại bỏ ở các mốc nâng cấp khác nhau. Lỗi không hẳn do bạn viết sai Java: **một ví dụ đúng cho phiên bản A có thể không còn là API hợp lệ trong phiên bản B**.

Bài học này giúp bạn **nhận ra tín hiệu ví dụ cũ, xác định phiên bản thực sự đang dùng, tra đúng tài liệu/Javadoc và chuyển sang cú pháp phù hợp mà không vô tình thay đổi chính sách bảo mật**. Trọng tâm là Spring Security cho **Spring MVC / Servlet** và cách cấu hình với `SecurityFilterChain`. Ví dụ chạy đầy đủ sử dụng **Spring Boot 3 + Spring Security 6 + Java 17+**, đồng thời giải thích các điểm cần kiểm tra khi chuyển sang **Spring Boot 4 + Spring Security 7**.

> Nguyên tắc học tập: Đừng chọn API chỉ vì đoạn code xuất hiện trong bài viết mới được đăng. **Hãy lấy version đang được build thực tế làm mốc, mở tài liệu đúng dòng phiên bản, rồi xác minh bằng compile và test hành vi.**

## 1. Vì sao ví dụ bảo mật hay bị lỗi sau khi nâng cấp?

Một dự án Java có nhiều lớp phiên bản:

- **JDK**: xác định ngôn ngữ, class library, bytecode và runtime.
- **Spring Framework**: cung cấp IoC container, Web MVC, proxy, servlet integration, annotation.
- **Spring Boot**: cung cấp starter, auto-configuration, plugin và dependency management.
- **Spring Security**: cung cấp authentication, authorization, filter chain, password utilities và test support.
- **Jakarta Servlet API** hoặc stack reactive: xác định kiểu import và luồng xử lý web.
- **Thư viện phụ thuộc khác**: OAuth2, JWT, database, testing, Spring Cloud, custom DSL.

Ví dụ:

```text
Mẫu học liệu cũ:
Spring Boot 2.x + Spring Security 5.x + javax.servlet.*
    -> WebSecurityConfigurerAdapter / antMatchers / cấu hình DSL cũ

Mẫu học liệu Spring Boot 3:
Spring Boot 3.x + Spring Security 6.x + jakarta.servlet.*
    -> SecurityFilterChain bean / requestMatchers / Lambda DSL

Mẫu học liệu Spring Boot 4:
Spring Boot 4.x + Spring Security 7.x
    -> SecurityFilterChain + Lambda DSL bắt buộc
    -> tiếp tục kiểm tra những thay đổi riêng của Boot 4, Security 7
```

Đây là **các dòng phiên bản thường đi cùng nhau**, không phải quy tắc suy diễn mọi phiên bản minor/patch. Hãy để BOM/dependency management của dự án xác định những version tương thích. Không tự ghép một Spring Security JAR bản mới vào dự án Boot cũ chỉ vì muốn dùng một method thấy trên tài liệu mới.

### 1.1. Những thay đổi mốc cần nhớ

| Mốc | Thay đổi quan trọng | Ảnh hưởng khi copy ví dụ |
| --- | --- | --- |
| Spring Security **5.4** | Hỗ trợ cấu hình web bằng `SecurityFilterChain` bean | Có thể dùng kiểu component-based thay adapter |
| Spring Security **5.7** | `WebSecurityConfigurerAdapter` bị deprecated | Các hướng dẫn dùng `extends WebSecurityConfigurerAdapter` trở thành tín hiệu cần cập nhật |
| Spring Security **6.0** | Loại bỏ `WebSecurityConfigurerAdapter` và nhiều matcher API cũ; chuyển sang nền Jakarta trong Spring Framework 6 | `extends WebSecurityConfigurerAdapter`, `antMatchers` cũ, import `javax.servlet` thường không biên dịch |
| Spring Security **6.x** | `SecurityFilterChain` + `authorizeHttpRequests` + `requestMatchers` là mẫu cấu hình Servlet hiện đại | Có thể giữ tương đương về quyền khi chuyển đổi có kiểm tra |
| Spring Security **6.2+** | `HttpSecurity.apply(...)` cho custom DSL bị deprecated; khuyến nghị `with(...)` | Tác giả custom DSL nên tra API chuyển đổi |
| Spring Security **6.5 → 7.0** | Hướng dẫn migration chuẩn bị Lambda DSL bắt buộc | Cấu hình kiểu `.authorizeHttpRequests().and()` phải được viết lại |
| Spring Security **7.0** | Loại bỏ kiểu DSL `.and()` cũ và `authorizeRequests` theo tài liệu What's New; các API Access Decision legacy được tách sang module legacy | Không dùng nguyên xi các hướng dẫn `authorizeRequests` hoặc chuỗi DSL cũ khi build 7.x |

Các mốc trên là **lý do cần tra cứu đúng version**, không phải bảng exhaustive của mọi thay đổi. Khi nâng cấp, đọc release notes/migration guide của **từng chặng phiên bản**, bởi ngoài cú pháp có thể thay đổi default behavior, matcher semantics, dependency module hoặc filter order.

## 2. Xác định phiên bản thực sự đang được build

Đây là bước số một trước khi sửa import hoặc API.

### 2.1. Dự án Gradle

Đọc `plugins`, `dependencies` và các chỗ cấu hình platform/BOM trong `build.gradle` hoặc `build.gradle.kts`; sau đó dùng Gradle để biết bản nào **được giải quyết cuối cùng**.

```bash
# Dự án dùng Gradle Wrapper (macOS/Linux)
./gradlew --version

# Tìm version thực của spring-security-config trong runtime graph
./gradlew dependencyInsight \
  --dependency spring-security-config \
  --configuration runtimeClasspath

# Tìm version của core, web, crypto và nguyên nhân bị kéo vào
./gradlew dependencyInsight \
  --dependency spring-security-core \
  --configuration runtimeClasspath

# Toàn bộ classpath runtime
./gradlew dependencies --configuration runtimeClasspath

# Test classpath, nơi spring-security-test có thể dùng version khác nếu cấu hình sai
./gradlew dependencies --configuration testRuntimeClasspath
```

Với Windows PowerShell, viết lệnh trên **một dòng** và dùng `.\gradlew.bat`, ví dụ:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-security-config --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
.\gradlew.bat dependencies --configuration testRuntimeClasspath
```

`dependencyInsight` hữu ích hơn việc chỉ nhìn dòng `implementation` vì thư viện có thể được kéo vào **transitively**, version có thể do BOM, constraints hoặc resolution strategy chọn. Nếu output có nhiều variant/configuration, đọc đúng configuration nơi đang compile/chạy. `compileClasspath` cũng có thể cần kiểm tra khi IDE báo không tìm thấy method; `runtimeClasspath` giúp xác nhận phiên bản thực chạy.

### 2.2. Dự án Maven

```bash
mvn -version

# Kiểm tra các Spring Security artifacts và phiên bản thực
mvn dependency:tree -Dincludes=org.springframework.security

# Khi cần kiểm tra phiên bản được quản lý qua parent/BOM
mvn help:effective-pom
```

Nếu dùng Maven Wrapper:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.security
```

Trong PowerShell, chú ý cú pháp shell và có thể dùng `.\mvnw.cmd`. Không suy ra version từ một snippet không có `parent` hoặc `dependencyManagement`; BOM có thể quyết định số phiên bản thực.

### 2.3. Kiểm tra JDK và stack web

```bash
java -version
javac -version
```

Sau đó xác định:

- Dự án dùng `spring-boot-starter-web` (Servlet/MVC) hay `spring-boot-starter-webflux` (Reactive)?
- Đang dùng `HttpSecurity` và `SecurityFilterChain` hay `ServerHttpSecurity` và `SecurityWebFilterChain`?
- Import Servlet là `jakarta.servlet.*` hay `javax.servlet.*`?
- Các module `spring-security-core`, `web`, `config`, `crypto`, `test` có đang nhất quán phiên bản không?

**Không dùng cấu hình Servlet `HttpSecurity` để dán thẳng vào WebFlux.** Reactive có security chain, matcher và testing API khác.

### 2.4. Nếu chỉ có một JAR và không có source build

Với một artifact đã đóng gói, có thể tra `META-INF/MANIFEST.MF` hoặc build metadata của đúng JAR; nhưng thông tin phụ thuộc vào cách đóng gói và không phải lúc nào cũng chứa bản đầy đủ. Tốt nhất là quay về build file/BOM/lockfile hoặc output của dependency resolver. Chỉ nhìn file jar có tên viết tắt cũng có thể sai khi ứng dụng dùng fat jar và dependency được đóng gói bên trong.

## 3. Nhận diện API cũ chỉ từ vài dòng code

Bảng sau giúp **phát hiện và đặt câu hỏi**, không phải cho phép thay toàn bộ API bằng find-and-replace.

| Mẫu nhìn thấy trong bài viết | Vì sao đáng nghi? | Hướng hiện đại | Kiểm tra trước khi thay |
| --- | --- | --- | --- |
| `extends WebSecurityConfigurerAdapter` | Deprecated 5.7, removed 6 | Bean `SecurityFilterChain`; beans riêng cho user store/provider | Có các `configure(HttpSecurity)`, `configure(AuthenticationManagerBuilder)`, `configure(WebSecurity)` cũ không? |
| `@Override protected void configure(HttpSecurity http)` trong adapter | Gắn policy vào superclass cũ | `@Bean SecurityFilterChain filterChain(HttpSecurity http)` | Có cấu hình session/filter/entry point phải chuyển không? |
| `authorizeRequests()` | Luồng authorization legacy; removed 7 | `authorizeHttpRequests(auth -> ...)` | Semantics của `FilterSecurityInterceptor`/`AuthorizationFilter` và custom authorization |
| `antMatchers(...)` / `mvcMatchers(...)` trong rule | Các overload cũ không có ở 6 | `requestMatchers(...)` | Path matching, Servlet path, method và các trường hợp ngoại lệ |
| `http.antMatcher("/api/**")` | Cách chọn phạm vi chain cũ | `http.securityMatcher("/api/**")` | Chain order, fallback và những URL không khớp |
| `http.authorizeHttpRequests().anyRequest()...and()` | DSL builder chaining cũ; bị loại trong 7 | Lambda DSL `authorizeHttpRequests(auth -> ...)` | Mỗi configurer nằm đúng lambda, không thay logic rule |
| `http.csrf().disable()` | Dùng chained configurer cũ | `csrf(csrf -> csrf.disable())` nếu có căn cứ | Có thật cần tắt CSRF? Mô hình credentials/cookie là gì? |
| `http.httpBasic()` / `http.formLogin()` không có Customizer | Cú pháp no-arg DSL cũ, không hợp lệ khi lên 7 | `httpBasic(Customizer.withDefaults())` / `formLogin(Customizer.withDefaults())` | Client nào được nhận Basic challenge hay form redirect? |
| `http.apply(customDsl)` | `apply` deprecated từ 6.2 | `http.with(customDsl, dsl -> ...)` | Custom DSL đang dùng phiên bản nào? |
| `@EnableGlobalMethodSecurity(prePostEnabled = true)` | Cách bật method security cũ, thường chuyển sang `@EnableMethodSecurity` | `@EnableMethodSecurity` và `@PreAuthorize` | Method security thực sự được bật? Proxy/self-invocation? |
| `javax.servlet.http.HttpServletRequest` | Phù hợp hệ Servlet cũ; Boot 3/Framework 6 dùng Jakarta | `jakarta.servlet.http.HttpServletRequest` | Phải chuyển cả dependency/namespace; thay import riêng lẻ không đủ |
| `web.ignoring().antMatchers("/static/**")` | API matcher cũ, đồng thời bỏ request qua security filters | Cân nhắc `requestMatchers("/static/**").permitAll()` | Có cần giữ security headers/filters cho static resources? |
| `User.withDefaultPasswordEncoder()` | Tiện cho demo nhưng không phù hợp production | `PasswordEncoder` với BCrypt/Delegating | Password hashes, migration và user store |
| `AccessDecisionManager` / `AccessDecisionVoter` | Kiến trúc authorization cũ, ở 7 tách sang `spring-security-access` | `AuthorizationManager` | Cần chuyển policy, không chỉ đổi import |
| `@EnableWebSecurity` với nhiều cấu hình lạ | Không tự động là lỗi; tùy dự án có thể cần | Kiểm tra Boot auto-config và chain hiện có | Tránh tạo hai chain xung đột hoặc tắt default configuration ngoài ý muốn |

**Không phải mọi dòng trông “cũ” đều đã bị loại ở mọi phiên bản.** Ví dụ `authorizeRequests` có thể còn trong một số phiên bản 6 nhưng bị loại trong 7. Mục tiêu là nhận diện **điểm cần xác minh ở đúng version**, không gắn nhãn lỗi chỉ vì cú pháp khác ví dụ mới nhất.

### 3.1. Cần phân biệt các loại thay đổi

- **Deprecated:** compiler/IDE cảnh báo, API vẫn có thể chạy ở bản hiện tại; thường có kế hoạch thay thế.
- **Removed:** không còn symbol/method/class trong version đang dùng; lỗi compile hoặc linkage.
- **Changed behavior:** code vẫn biên dịch nhưng matcher, filter, default policy hoặc mapping có thay đổi.
- **Configuration mistake:** API tồn tại nhưng đặt sai matcher/chain hoặc vô tình dùng `permitAll()` làm endpoint public.
- **Wrong stack:** copy API Servlet vào WebFlux hoặc ngược lại.
- **Wrong dependency:** code có method hợp lệ trong tài liệu nhưng classpath chứa phiên bản khác.

Nên phân loại trước khi sửa. Một lỗi `Cannot resolve symbol` khác với một API compile thành công nhưng request không được bảo vệ.

## 4. Chuyển từ WebSecurityConfigurerAdapter sang SecurityFilterChain

### 4.1. Ví dụ kiểu cũ để nhận diện, không copy cho Spring Security 6+

Trong tài liệu Spring Security 5.x có thể thấy:

```java
// OLD: đoạn minh họa từ kiểu WebSecurityConfigurerAdapter.
@Configuration
class OldSecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http
            .authorizeRequests()
                .antMatchers("/public/**").permitAll()
                .antMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            .and()
            .httpBasic();
    }
}
```

Điều dễ nhận ra: adapter, override `configure`, `antMatchers` và `.and()`. Đây là mẫu **phụ thuộc vào API của Spring Security đời cũ**, không phải Java 17/Spring Boot 3 code có thể chạy nguyên xi.

### 4.2. Mẫu component-based phù hợp với Spring Security 6

```java
@Configuration
class SecurityConfig {
    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
```

Điều chuyển đổi:

1. Không kế thừa `WebSecurityConfigurerAdapter`. Cấu hình được đóng trong bean `SecurityFilterChain`.
2. `authorizeHttpRequests` thay cho `authorizeRequests` của ví dụ cũ.
3. `requestMatchers` thay cho `antMatchers` trong DSL authorization, nhưng bạn phải kiểm tra lại cách match URL/HTTP method.
4. `.httpBasic(Customizer.withDefaults())` dùng Lambda DSL nhất quán.
5. `.build()` tạo chain cho Servlet filters.
6. `anyRequest().authenticated()` chỉ yêu cầu đăng nhập; nếu đây là ứng dụng nhạy cảm, cần quyết định liệu route chưa khai báo phải `denyAll()` hay không.
7. `hasRole("ADMIN")` mặc định kiểm tra authority `ROLE_ADMIN`. Nguồn user/role phải được cấu hình riêng.

**Không dừng ở compile.** Phải kiểm tra anonymous, role USER, ADMIN, URI public/admin và những đường dẫn còn lại. Nếu ứng dụng có nhiều filter chain, cần xác minh chain nào thực sự nhận request.

### 4.3. Từ configure(AuthenticationManagerBuilder) sang beans

Nếu ví dụ cũ override:

```java
@Override
protected void configure(AuthenticationManagerBuilder auth)
        throws Exception {
    auth.inMemoryAuthentication()
        .withUser("reader")
        .password("{noop}password")
        .roles("USER");
}
```

Thay vì port bằng máy móc, trong ví dụ Spring Boot hiện đại có thể đăng ký:

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
UserDetailsService userDetailsService(PasswordEncoder encoder) {
    var reader = User.withUsername("reader")
        .password(encoder.encode("demo-password"))
        .roles("USER")
        .build();

    return new InMemoryUserDetailsManager(reader);
}
```

Đây là **đoạn mã trong một ứng dụng Spring**, cần imports và các dependency phù hợp. `{noop}` của snippet cũ chỉ nên dùng trong môi trường thử nghiệm rất hạn chế; production nên dùng password hashing được thiết kế đúng. Với JDBC, LDAP, OAuth2 hoặc custom provider, cấu hình tương ứng sẽ khác; **không phải tất cả đều chuyển thành InMemoryUserDetailsManager**.

### 4.4. Khi cần AuthenticationManager bean

Một số code cũ gọi `authenticationManagerBean()` từ adapter. Trong ứng dụng Spring Security 6, có thể lấy `AuthenticationManager` được cấu hình thông qua `AuthenticationConfiguration` khi cần:

```java
@Bean
AuthenticationManager authenticationManager(
        AuthenticationConfiguration configuration
) throws Exception {
    return configuration.getAuthenticationManager();
}
```

Chỉ đăng ký bean này khi kiến trúc thực sự cần inject manager vào component khác; các filter tích hợp có thể hoạt động qua cấu hình Spring Security mà không cần bạn tự tạo authentication manager bean công khai. Với nhiều provider hoặc nhiều chain, phải hiểu manager nào được sử dụng.

## 5. Chuyển rule cũ: antMatchers, mvcMatchers và authorizeRequests

### 5.1. Mẫu cũ

```java
// OLD: phù hợp một số bài hướng dẫn Spring Security 5.
http.authorizeRequests()
    .antMatchers(HttpMethod.GET, "/public/**").permitAll()
    .antMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated();
```

Mẫu tương ứng trong Spring Security 6:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
    .requestMatchers("/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
```

**Điều không được bỏ qua:** `requestMatchers` có nhiều overload và chọn loại `RequestMatcher` tùy classpath/ngữ cảnh. Path matching theo Spring MVC, servletPath, context path và path pattern có thể khác chi tiết kiểu Ant cũ. Nếu policy liên quan đường dẫn nhạy cảm, hãy **viết integration test cho path chính xác**, không coi đây là phép thay chuỗi hoàn toàn tương đương.

Ví dụ các test edge cases cần xét khi di chuyển:

- `/admin` và `/admin/`;
- `/admin/users` và `/admin-other`;
- servlet path khác root;
- path có encoded characters hoặc dấu chấm phẩy khi routing cho phép;
- method GET vs POST;
- fallback của nhiều security chains.

Chỉ giữ những test có ý nghĩa với routing cấu hình thật; mục tiêu là phát hiện endpoint bị mở ngoài ý muốn, không cố tìm một cú pháp string có thể bảo đảm mọi ứng dụng.

### 5.2. securityMatcher chọn chain, requestMatchers chọn rule

Một đoạn code khác dễ bị nhầm:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}

@Bean
SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
        .anyRequest().denyAll()
    );
    return http.build();
}
```

- `securityMatcher("/api/**")` giới hạn **toàn bộ chain thứ nhất**.
- `requestMatchers("/api/admin/**")` chọn rule **bên trong chain đã khớp**.
- `@Order(1)` quyết định chain ưu tiên đầu tiên.
- Chain thứ hai không khai báo `securityMatcher`, đóng vai trò fallback.
- `anyRequest().denyAll()` trên fallback không thay thế matcher của chain API; nó chỉ áp dụng cho request được chain fallback nhận.

Nếu bạn chuyển từ `http.antMatcher("/api/**")` sang `http.securityMatcher("/api/**")` và quên fallback, request nằm ngoài `/api/**` có thể **không đi qua bất kỳ Spring Security filter chain nào**. Đó là lỗi cấu hình nghiêm trọng dù source code compile hoàn toàn bình thường.

### 5.3. web.ignoring khác permitAll

Một số bài cũ viết:

```java
// OLD / chỉ dùng khi thật sự muốn bỏ qua Spring Security filters:
@Override
public void configure(WebSecurity web) {
    web.ignoring().antMatchers("/static/**");
}
```

Trong nhiều ứng dụng, điều bạn thực sự muốn là cho phép đọc tài nguyên công khai nhưng vẫn giữ các filter/headers bảo vệ phù hợp:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/static/**").permitAll()
    .anyRequest().authenticated()
);
```

`permitAll` **khác** bỏ request ra khỏi Spring Security. Có trường hợp cần `WebSecurityCustomizer` để bỏ qua request, nhưng phải hiểu rõ ranh giới; đừng dùng `ignoring` như cách chữa lỗi 401/403 mà không đánh giá các bảo vệ bị mất.

## 6. Chuyển từ DSL cũ sang Lambda DSL

### 6.1. Nhận diện kiểu gọi .and()

Trong bài viết cũ:

```java
// OLD: mẫu DSL không dùng lambda.
http.authorizeHttpRequests()
        .anyRequest().authenticated()
        .and()
    .formLogin()
        .loginPage("/login")
        .permitAll()
        .and()
    .httpBasic();
```

Mẫu thích hợp hơn cho Spring Security 6 và là hướng bắt buộc trong Spring Security 7:

```java
http.authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .formLogin(form -> form
        .loginPage("/login")
        .permitAll()
    )
    .httpBasic(Customizer.withDefaults());
```

Trong Lambda DSL, mỗi phần cấu hình nằm trong lambda có đối tượng tương ứng. `HttpSecurity` được trả lại sau mỗi lambda; **không cần `.and()`**.

### 6.2. Vì sao Lambda DSL cải thiện khả năng đọc?

Ví dụ với CSRF:

```java
http.csrf(csrf -> csrf
    .csrfTokenRepository(tokenRepository)
);
```

Đọc trực tiếp là “configurer CSRF nhận một cấu hình repository”. Khi dùng DSL cũ, phải biết `.and()` đang trả về builder nào để thêm bước tiếp theo. Một số API no-arg deprecated trước khi bị loại ở major tiếp theo.

**Không đổi cả cách xử lý security chỉ vì đổi syntax.** Khi chuyển `csrf().disable()` thành `csrf(csrf -> csrf.disable())`, request vẫn **bị tắt CSRF protection**; code có thể hiện đại về cú pháp nhưng không chắc đã an toàn. Đầu tiên cần xác minh CSRF có phù hợp threat model không, đặc biệt với app dùng session cookie.

### 6.3. Các DSL thông dụng

| Kiểu cũ có thể gặp | Kiểu lambda dễ đọc hơn | Cần nhớ |
| --- | --- | --- |
| `http.httpBasic()` | `http.httpBasic(Customizer.withDefaults())` | Bật Basic với defaults |
| `http.formLogin()` | `http.formLogin(Customizer.withDefaults())` | Bật form login với defaults |
| `http.csrf().disable()` | `http.csrf(csrf -> csrf.disable())` | Chỉ tắt nếu được thiết kế và kiểm chứng |
| `http.headers().frameOptions().disable()` | `http.headers(headers -> headers.frameOptions(frame -> frame.disable()))` | Cẩn thận clickjacking; chỉ thay khi có nhu cầu |
| `http.sessionManagement().sessionCreationPolicy(...)` | `http.sessionManagement(s -> s.sessionCreationPolicy(...))` | Đổi syntax không thay chính sách session |
| `http.apply(myDsl)` | `http.with(myDsl, dsl -> ...)` từ phiên bản phù hợp | Dùng cho custom DSL, tra Javadoc version thực |
| `authorizeRequests()` | `authorizeHttpRequests(auth -> ...)` | Cần kiểm tra quyền trên từng URL |
| `antMatchers(...)` | `requestMatchers(...)` | Cần kiểm tra matcher semantics |

Không phải một biểu thức trên bảng có thể ghép trực tiếp vào mọi code mà không có import hoặc bean. Tra đúng kiểu lambda của **method trên class phiên bản đang dùng** và xem ví dụ chính thức trọn vẹn.

## 7. Method security: từ @EnableGlobalMethodSecurity sang @EnableMethodSecurity

Trong các bài hướng dẫn cũ có thể thấy:

```java
// OLD:
@EnableGlobalMethodSecurity(prePostEnabled = true)
class LegacyMethodSecurityConfig {
}
```

Trong Spring Security 6, cách phổ biến hơn là:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

`@EnableMethodSecurity` bật các interceptor method security theo cách hiện đại; mặc định pre/post annotations như `@PreAuthorize` được hỗ trợ. Không cần copy mọi tham số cũ theo máy móc.

Ví dụ:

```java
@Service
class ReportService {
    @PreAuthorize("hasAuthority('report:read')")
    public String read() {
        return "report";
    }
}
```

Để test phương thức này có được bảo vệ hay không, hãy gọi qua Spring-managed bean/proxy. **Self-invocation** (`this.read()` trong cùng object) có thể không đi qua proxy nên annotation không được thực thi theo cách bạn kỳ vọng.

### 7.1. Tham số method trong biểu thức SpEL

Một ví dụ dùng `@PreAuthorize("@authz.check(#orderId, authentication)")` có thể phụ thuộc khả năng Spring tìm ra tên tham số Java. Trong Spring Framework 6.1+, khi kiểm tra quyền dựa trên tên tham số, hãy biên dịch với `-parameters` phù hợp hoặc dùng cách tham chiếu tham số mà phiên bản hỗ trợ.

Ví dụ Gradle Java:

```groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
```

Không đánh giá thay đổi bằng việc chỉ nhìn annotation trong IDE: cần kiểm thử lời gọi thật và trường hợp bị từ chối. Đặc biệt, method security không tự biết user có sở hữu order ID hoặc tenant của tài nguyên không nếu policy không kiểm tra.

## 8. Nhận diện namespace Java EE/Jakarta EE

Spring Boot 3 đi cùng Spring Framework 6, chuyển các API Servlet và nhiều API Jakarta EE sang namespace `jakarta.*`:

```java
// OLD: Java EE servlet namespace
import javax.servlet.http.HttpServletRequest;

// Spring Boot 3 / Spring Framework 6:
import jakarta.servlet.http.HttpServletRequest;
```

Tương tự với Bean Validation:

```java
// OLD:
import javax.validation.Valid;

// Với Spring Boot 3:
import jakarta.validation.Valid;
```

Không phải mọi `javax.*` đều đổi thành `jakarta.*`. Ví dụ `javax.crypto`, `javax.net.ssl` là các Java SE packages, **không đổi** vì Spring Boot nâng phiên bản. Không dùng global search-and-replace `javax` thành `jakarta` trên toàn codebase.

Thay import mà vẫn để dependency servlet/validation cũ có thể không compile hoặc phát sinh runtime errors. Cần nâng cả stack theo migration guide, nhất là servlet container, security filters, validation starter và thư viện bên thứ ba.

## 9. Khi dự án dùng Spring Security 7 cần kiểm tra thêm gì?

Spring Security 7 có những thay đổi lớn hơn về API cấu hình:

1. **Lambda DSL bắt buộc:** cách nối `.and()` không còn hợp lệ.
2. **`authorizeRequests` legacy bị loại:** dùng `authorizeHttpRequests` và policy phù hợp.
3. **Một số AccessDecision API legacy** đã chuyển sang module `spring-security-access`, đồng thời hướng khuyến nghị là `AuthorizationManager`.
4. **Custom DSL:** nếu còn dùng `HttpSecurity.apply`, cần tra `with` và cách khởi tạo DSL.
5. **Method security:** cần xem những thay đổi migration về annotation template, parameter names và components tùy ứng dụng.
6. **Các integration như Jackson** có thể thay đổi giữa dòng Spring Boot/Spring Security; không copy class/module cấu hình serializer cũ một cách vô điều kiện.
7. **Build tool/plugin/test packages:** nâng theo tài liệu Spring Boot 4; một test Spring Boot 3 không được giả định luôn biên dịch nguyên xi trong Boot 4.

Chọn tài liệu có đường dẫn version rõ ràng, ví dụ:

- Spring Security 6.5: `https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html`
- Spring Security 7.0: `https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html`
- Hướng dẫn chuẩn bị từ 6.5 lên 7: `https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html`
- Migration 7: `https://docs.spring.io/spring-security/reference/7.0/migration/`

**Không cố suy đoán “bản mới nhất” theo trí nhớ của người viết tài liệu.** Tại thời điểm bạn làm việc, hãy kiểm tra version resolver, danh sách docs ổn định và patch version được tổ chức/dự án chấp nhận. Bài này cố ý dùng URL theo dòng phiên bản để luôn có điểm tham chiếu ổn định.

## 10. Cách tra đúng Javadoc và documentation: một quy trình có thể lặp lại

Khi thấy ví dụ không compile, làm theo chuỗi:

```text
1. Chụp lại lỗi và symbol cụ thể
       |
       v
2. Xác minh Gradle/Maven resolved Spring Security version
       |
       v
3. Xác định Servlet vs WebFlux và Boot/JDK version
       |
       v
4. Chọn docs đúng major.minor (không chỉ search snippet)
       |
       v
5. Mở API / package trong Javadoc của cùng phiên bản
       |
       v
6. Đọc migration guide giữa version của ví dụ và dự án
       |
       v
7. Chuyển policy + import + beans theo ngữ nghĩa
       |
       v
8. Compile và test request cho phép + từ chối
       |
       v
9. Kiểm tra runtime security chain và không có endpoint bị mở
```

### 10.1. Truy vấn tìm kiếm có hiệu quả

Ví dụ đang dùng Spring Security 6.5:

```text
site:docs.spring.io/spring-security/reference/6.5/
    "SecurityFilterChain" "authorizeHttpRequests"

site:docs.spring.io/spring-security/reference/6.5/
    "requestMatchers" "securityMatcher"

site:docs.spring.io/spring-security/reference/6.5/migration-7/
    "Lambda DSL"
```

Các ví dụ search có thể được gõ thành **một dòng** trong công cụ tìm kiếm; dấu xuống dòng ở đây để dễ đọc. Với Security 7, đổi `/6.5/` thành `/7.0/` hoặc version phù hợp đã xác nhận. Dùng trang reference và Javadoc chính thức, tránh snippets cắt mất imports, config, chain matcher, test setup và security context.

### 10.2. Javadoc trả lời ba câu hỏi

Khi IDE báo `Cannot resolve method`, tìm Javadoc theo phiên bản của **kiểu nhận method**:

- `HttpSecurity` có những overload nào của `authorizeHttpRequests`, `csrf`, `httpBasic`?
- `AuthorizeHttpRequestsConfigurer` / registry tương ứng có `requestMatchers` nào?
- `AuthenticationManager`, `UserDetailsService`, `AuthorizationManager` có đúng method signature không?

Sau đó xem `@since`/`@Deprecated`, các lớp liên quan và ví dụ chính thức. Một method không xuất hiện ở package A không có nghĩa Java import thiếu; có thể bạn đang dùng ví dụ dành cho **một version khác hoặc một loại builder khác**.

### 10.3. Khi một phương thức tồn tại ở docs mà IDE vẫn không thấy

Kiểm tra:

1. `compileClasspath` có version giống version mà bạn xem tài liệu không?
2. IDE có đang mở project đúng Gradle/Maven module không?
3. Có nhiều bản `spring-security-config`/`core` trên classpath do override BOM không?
4. Bạn import đúng class không? `HttpSecurity` khác `ServerHttpSecurity`.
5. Có đổi package `javax.servlet` sang `jakarta.servlet` theo đúng nền Boot 3 không?
6. Method bạn muốn gọi nằm trên `HttpSecurity` hay trên configurer bên trong lambda?
7. Build error phát sinh từ Java source hay từ annotation processor/code generated?

Sau khi sửa dependency, refresh/reimport Gradle/Maven vào IDE và chạy build từ command line. **Không “sửa” bằng cách tắt security** hay bỏ hết matcher cho code biên dịch.

## 11. Ví dụ Spring Boot 3 / Spring Security 6 hoàn chỉnh

Ví dụ này minh họa cấu hình theo kiểu hiện đại với ba chức năng:

- GET `/public`: cho anonymous.
- GET `/me`: yêu cầu đăng nhập HTTP Basic.
- GET `/admin`: yêu cầu authority `ROLE_ADMIN`.

Nó dùng **bean SecurityFilterChain**, **Lambda DSL** và **UserDetailsService** thay cho adapter cũ; có bài test để chứng minh không vô tình mở endpoint khi di chuyển API.

### 11.1. Dependency dự án

Trong `build.gradle` của một dự án Spring Boot 3 dùng Java 17+ đã cấu hình Spring Boot Gradle plugin, repository và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây là **đoạn dependencies**, không phải build file hoàn chỉnh. Đừng tự thêm phiên bản cho từng Spring Security JAR khi Boot BOM đang quản lý chúng.

### 11.2. Main class

Tạo `src/main/java/example/versionguide/VersionGuideApplication.java`:

```java
package example.versionguide;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class VersionGuideApplication {
    public static void main(String[] args) {
        SpringApplication.run(VersionGuideApplication.class, args);
    }
}
```

### 11.3. SecurityConfig theo Lambda DSL

Tạo `src/main/java/example/versionguide/SecurityConfig.java`:

```java
package example.versionguide;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin-pass"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/me")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Cách đối chiếu:

- `SecurityFilterChain` thay adapter cũ.
- `authorizeHttpRequests` và `requestMatchers` thay mẫu `authorizeRequests`/`antMatchers`.
- `Customizer.withDefaults()` kích hoạt HTTP Basic theo kiểu lambda.
- `anyRequest().denyAll()` làm endpoint chưa khai báo bị từ chối.
- `BCryptPasswordEncoder` tránh lưu plaintext password trong user store.
- `@Configuration` đăng ký các beans tách biệt; không override method `configure`.

Cấu hình này cố ý chỉ mở các GET cụ thể; nếu thêm controller mới, bạn phải cập nhật rule. Đây là ví dụ học tập, không phải bản cấu hình production: credential hardcode chỉ dành cho local và HTTP Basic phải đi qua HTTPS khi có dữ liệu thật.

### 11.4. Controller

Tạo `src/main/java/example/versionguide/DemoController.java`:

```java
package example.versionguide;

import java.security.Principal;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/admin")
    public String admin() {
        return "admin";
    }
}
```

`Principal` được Spring MVC cung cấp từ ngữ cảnh request đã xác thực. Controller không xử lý password và không tự tin header `X-User-Id` do client gửi.

### 11.5. Chạy và quan sát

Trong root của dự án Spring Boot với Gradle Wrapper:

```bash
./gradlew bootRun
```

Trên Windows:

```powershell
.\gradlew.bat bootRun
```

Khi ứng dụng nghe tại `http://localhost:8080`:

```bash
# 200: endpoint public
curl -i http://localhost:8080/public

# 401: chưa xác thực
curl -i http://localhost:8080/me

# 200: Alice có credentials hợp lệ
curl -i -u alice:demo-alice-pass http://localhost:8080/me

# 403: Alice không có ROLE_ADMIN
curl -i -u alice:demo-alice-pass http://localhost:8080/admin

# 200: Admin có ROLE_ADMIN
curl -i -u admin:demo-admin-pass http://localhost:8080/admin

# 401: sai mật khẩu
curl -i -u alice:wrong-pass http://localhost:8080/me
```

Ở đây mã HTTP **là kỳ vọng từ cấu hình mẫu**. Chi tiết body/header, realm và thứ tự response headers có thể khác. `curl -u` với password trên chỉ dùng local demo; thông tin bí mật thật cần HTTPS và quản lý an toàn, tránh lộ trong history/process list.

## 12. Kiểm thử để tránh đổi syntax nhưng thay đổi behavior

Trước khi migration, hãy lưu kết quả mong đợi từ API hiện có. Sau khi chuyển sang `SecurityFilterChain`, kiểm tra cùng một tập request trên cấu hình mới.

Thêm `spring-security-test` trong test classpath như mục 11.1. Tạo `src/test/java/example/versionguide/SecurityVersionMigrationTest.java`:

```java
package example.versionguide;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityVersionMigrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicGetIsAllowed() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));
    }

    @Test
    void anonymousMeIsChallenged() throws Exception {
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicUserCanReadOwnName() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("alice"));
    }

    @Test
    void userCannotAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-alice-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-admin-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownRouteIsNotPublic() throws Exception {
        mvc.perform(get("/unregistered"))
            .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test --tests example.versionguide.SecurityVersionMigrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.versionguide.SecurityVersionMigrationTest
```

**Kỳ vọng:** sáu ca đầu thành công với status đã mô tả. Với ca `/unregistered`, cấu hình `denyAll` từ chối cả anonymous nên request thường trả 403 theo hành vi Spring Security hiện đại, nhưng chi tiết status có thể chịu tác động từ entry point, exception handling và phiên bản; nếu khác, kiểm tra rằng endpoint **không bị công khai hoặc trả dữ liệu** rồi điều chỉnh assertion theo policy thực tế. Đây là kiểm thử **được đề xuất**, không phải kết quả đã chạy trong tài liệu.

**Với dự án đang nâng cấp thực**, bổ sung test chặt chẽ cho:

- GET/POST và quyền theo từng HTTP method;
- Admin, user thường, anonymous, permission cụ thể;
- Chain order và URL rơi ngoài `securityMatcher`;
- Resource ID khác owner/tenant;
- CSRF token thiếu/sai/hợp lệ khi ứng dụng dùng cookie/session;
- Endpoint OAuth2 login/logout và token parsing nếu có;
- Request forward/error dispatcher khi đang có cấu hình đặc biệt;
- Đảm bảo không có side effect khi policy từ chối.

Không “fix” test lỗi bằng cách bỏ `@PreAuthorize`, thay `denyAll` thành `permitAll` hoặc tắt CSRF mà chưa hiểu nguyên nhân. **Migration thành công phải bảo toàn yêu cầu bảo mật, không chỉ làm compiler hết đỏ.**

## 13. Java 17 độc lập: công cụ quét dấu hiệu API cũ

Không phải lúc nào cũng cần mở IDE để nhận ra dấu hiệu API cũ. Công cụ nhỏ sau **biên dịch bằng Java 17 thuần**, đọc một file text/Java, in các dòng chứa keyword và gợi ý tra cứu. Nó cố ý là **scanner văn bản**, không phải Java parser hay bằng chứng chính thức rằng API bị loại ở phiên bản bạn dùng.

Tạo `LegacyApiScanner.java`:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

public class LegacyApiScanner {
    record Rule(String needle, String advice) {}

    static final List<Rule> RULES = List.of(
        new Rule("WebSecurityConfigurerAdapter",
            "use SecurityFilterChain bean (removed in 6)"),
        new Rule("authorizeRequests(",
            "check authorizeHttpRequests (removed in 7)"),
        new Rule("antMatchers(",
            "check requestMatchers (removed in 6)"),
        new Rule(".and()",
            "use Lambda DSL for 7"),
        new Rule("javax.servlet",
            "check jakarta.servlet for Boot 3+"),
        new Rule("EnableGlobalMethodSecurity",
            "check EnableMethodSecurity")
    );

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            System.out.println("Usage: java LegacyApiScanner <file>");
            return;
        }

        List<String> lines = Files.readAllLines(Path.of(args[0]));
        int matches = 0;

        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            for (Rule rule : RULES) {
                if (line.contains(rule.needle())) {
                    matches++;
                    System.out.println(
                        "line " + (i + 1) + ": " + rule.needle()
                            + " -> " + rule.advice()
                    );
                }
            }
        }

        System.out.println("Signals found: " + matches);
    }
}
```

Tạo file thử **`legacy-snippet.txt`** với nội dung:

```text
import javax.servlet.http.HttpServletRequest;
class Config extends WebSecurityConfigurerAdapter {
  void configure() {
    http.authorizeRequests().antMatchers("/admin").authenticated();
    http.httpBasic().and();
  }
}
```

Biên dịch và chạy:

```bash
javac LegacyApiScanner.java
java LegacyApiScanner legacy-snippet.txt
```

**Stdout chính xác của ví dụ:**

```text
line 1: javax.servlet -> check jakarta.servlet for Boot 3+
line 2: WebSecurityConfigurerAdapter -> use SecurityFilterChain bean (removed in 6)
line 4: authorizeRequests( -> check authorizeHttpRequests (removed in 7)
line 4: antMatchers( -> check requestMatchers (removed in 6)
line 5: .and() -> use Lambda DSL for 7
Signals found: 5
```

**Giới hạn của scanner:** đọc line text nên có thể báo keyword trong comment, string literal hoặc ví dụ đang giải thích “old code”. Nó không biết version Gradle/Maven, không parse syntax và không xác minh endpoint an toàn. Vì vậy hãy dùng nó để **liệt kê vị trí cần đọc kỹ**, sau đó tra API theo version, build, test và review chính sách. Không tự động thay toàn bộ keyword trong repository.

Nếu chạy với file không tồn tại, `Files.readAllLines` phát sinh IOException; chương trình intentionally không che giấu lỗi này. Với dự án lớn, có thể dùng `rg`/IDE Find in Files để tìm các dấu hiệu nhanh hơn.

## 14. Tình huống debug cụ thể

### 14.1. “Cannot resolve symbol WebSecurityConfigurerAdapter”

- Xác nhận version `spring-security-config` đã resolve.
- Nếu đang trên Spring Security 6+, nguyên nhân thường là adapter đã bị loại.
- Chuyển sang bean `SecurityFilterChain`, đồng thời chuyển cấu hình user/provider có trước đó.
- Không thêm JAR Spring Security 5.x vào Boot 3 chỉ để tìm lại class: điều đó có thể phá tính tương thích và an toàn.

### 14.2. “Cannot resolve method antMatchers”

- Kiểm tra bạn đang ở `authorizeRequests`/`authorizeHttpRequests` hay `WebSecurityCustomizer`.
- Trong Security 6+, dùng `requestMatchers` phù hợp.
- Chọn đúng method overload khi match HTTP method; kiểm tra đường dẫn/servletPath và fallback.
- Viết test anonymous và user có/không có role cho mọi pattern nhạy cảm.

### 14.3. “Cannot resolve method and()” sau khi nâng Security 7

- Mở hướng dẫn migration DSL.
- Thay cấu hình chained no-arg bằng lambda và `Customizer.withDefaults()`.
- Kiểm tra các custom DSL dùng `.apply(...)`; xem `.with(...)`.
- Không chuyển `csrf().disable()` một cách mù quáng: quyết định có bật CSRF là một quyết định bảo mật.

### 14.4. IDE báo import javax.servlet không tồn tại

- Kiểm tra Boot 3/Framework 6 có dùng `jakarta.servlet` hay không.
- Xác nhận dependency web/Servlet phù hợp đã có.
- Không đổi các package Java SE như `javax.crypto`.
- Kiểm tra thư viện bên thứ ba còn yêu cầu javax cũ gây xung đột hay không.

### 14.5. Compile thành công nhưng URL admin thành public

- Xác minh `securityMatcher` của từng chain, `@Order` và fallback.
- Xem thứ tự `requestMatchers`: rule `permitAll` quá rộng có thể khớp trước admin rule.
- Kiểm tra `web.ignoring` có bỏ URL ra khỏi filters không.
- Test với người dùng chưa login, user không có admin role và request biến thể.
- Việc “build xanh” không chứng minh chính sách tương đương.

### 14.6. @PreAuthorize không chặn dù đã cập nhật annotation

- Có `@EnableMethodSecurity` ở đúng application context không?
- Class/method được Spring quản lý và gọi qua proxy không? Có self-invocation không?
- Method sử dụng tên tham số trong SpEL có được biên dịch với `-parameters` không?
- Có method public/đúng invocation boundary theo cơ chế AOP đang dùng không?
- Test lời gọi thực qua bean và đối chiếu quyền, không chỉ kiểm tra annotation tồn tại.

### 14.7. Mâu thuẫn giữa tài liệu search và IDE

Ví dụ trang blog dùng `http.antMatcher` nhưng Javadoc version dự án chỉ có `securityMatcher`. **Ưu tiên API thực của version đang resolve**, tiếp theo là reference/migration guide cùng phiên bản. Nếu website có menu version ở đầu trang, hãy chọn đúng dòng. Với dependency nhiều lớp, kiểm tra BOM trước khi kết luận docs sai.

## 15. Quy trình nâng cấp API có kiểm soát

Một migration tốt có thể chia thành các bước kỹ thuật tuần tự:

1. **Chốt hiện trạng**: version Boot, Security, JDK, Servlet/WebFlux, danh sách chain và policies.
2. **Lập bảng dấu hiệu cũ**: adapter, `authorizeRequests`, matchers, no-arg DSL, `.and()`, `apply`, method security annotations, import `javax`.
3. **Mở migration đúng chặng**: với 5.x → 6.x đọc hướng dẫn chuyển lên 6; với 6.5 → 7.x đọc hướng dẫn lên 7, đừng nhảy qua thông tin breaking changes.
4. **Giữ behavior dự kiến**: lưu test 200/401/403, redirect, CSRF, session và quyền trên object trước khi sửa.
5. **Cập nhật dependencies đồng bộ**: dùng Boot BOM/constraints, không override tùy tiện từng module.
6. **Chuyển code theo trách nhiệm**: security chain, authentication provider/store, request authorization, method security, protections và exception handlers.
7. **Biên dịch**: kiểm tra lỗi import/method/annotation, test classpath và khớp Java/toolchain.
8. **Chạy security regression tests**: đặc biệt những đường đã bị deny trước migration.
9. **Kiểm tra runtime**: đúng chain được chọn, fallback tồn tại, không có bypass do matcher khác semantics.
10. **Ghi lại lý do sửa**: phiên bản cũ/mới, policy đã giữ, điểm thay đổi có chủ đích và test chứng minh.

Đừng tối ưu thành một script tìm-thay toàn project. Khi thay `antMatchers` thành `requestMatchers`, hoặc đổi chain selection, một chữ có thể ảnh hưởng đến toàn bộ attack surface. Review security rules tương tự thay đổi nghiệp vụ quan trọng.

## 16. Checklist trước khi tin một ví dụ trên Internet

Khi thấy đoạn code Spring Security từ blog, Stack Overflow, video hoặc repository mẫu, hãy hỏi:

- Tác giả ghi rõ **Spring Boot, Spring Security, Java, Servlet/WebFlux version** chưa?
- Dự án thật của bạn có cùng major/minor và BOM không?
- Có `WebSecurityConfigurerAdapter`, `antMatchers`, `authorizeRequests` hoặc `.and()` kiểu cũ không?
- Ví dụ có import `javax.servlet` trong khi bạn dùng Boot 3 không?
- Có cả lớp main/config/controller/dependencies cần thiết không, hay chỉ một fragment?
- Các route không có rule được xử lý thế nào? Có fallback chain không?
- `hasRole("ADMIN")` tương ứng `ROLE_ADMIN` được cấp từ đâu?
- Ví dụ có tắt CSRF hoặc `web.ignoring` mà không giải thích nguy cơ không?
- Cơ chế login/token có đúng client và cách quản lý credentials của bạn không?
- Ví dụ có test anonymous, wrong password, thiếu quyền và CSRF không?
- Nếu có custom provider/OAuth2, đã verify issuer, audience, signing key và scope đúng không?
- Có tài liệu migration/Javadoc chính thức cùng version xác nhận method đang dùng không?

Câu trả lời “code trên blog compile” là một tín hiệu tốt, nhưng **chưa chứng minh config đã bảo vệ đúng mọi đường truy cập**. Cần test trường hợp bị từ chối và tác dụng phụ.

## 17. Tự kiểm tra

**Câu 1.** Một bài viết dùng `extends WebSecurityConfigurerAdapter`. Dự án Spring Boot 3/Security 6 báo không tìm thấy class. Đây là lỗi gì, và hướng sửa?

**Câu 2.** `antMatchers("/admin/**")` từ bài cũ chuyển thành `requestMatchers("/admin/**")`. Vì sao vẫn phải test path matching?

**Câu 3.** `HttpSecurity.securityMatcher` khác `authorizeHttpRequests().requestMatchers` thế nào?

**Câu 4.** Vì sao `authorizeRequests()` có thể biên dịch ở một project 6.x nhưng lại không ở project 7.x?

**Câu 5.** Một snippet dùng `http.csrf().disable()`. Thay bằng `http.csrf(csrf -> csrf.disable())` có tự làm ứng dụng an toàn hơn không?

**Câu 6.** Vì sao không nên thêm Spring Security 5.x JAR vào Boot 3 chỉ để tiếp tục dùng adapter?

**Câu 7.** Tại sao `@WithMockUser` test pass chưa chứng minh HTTP Basic/login provider hoạt động thật?

**Câu 8.** Ứng dụng đổi hết `javax.*` sang `jakarta.*` có đúng không?

**Câu 9.** Nếu build và test happy path đều qua nhưng request anonymous vào `/admin` nhận 200, migration thành công chưa?

**Câu 10.** Bài cũ dùng `@EnableGlobalMethodSecurity`. Khi đổi sang `@EnableMethodSecurity`, phải kiểm chứng gì?

**Đáp án gợi ý:**

1. API adapter bị loại ở Security 6; dùng bean `SecurityFilterChain`, chuyển các bean/provider liên quan.
2. Matcher semantics có thể khác, nhất là Servlet/MVC path, method và những pattern nhạy cảm; test để bảo đảm không mở endpoint.
3. `securityMatcher` chọn toàn chain, `requestMatchers` đặt rule trong chain đã chọn.
4. `authorizeRequests` là API legacy bị loại ở 7; cần tra Javadoc/version thực.
5. Không. Chỉ thay cú pháp, vẫn tắt CSRF; phải đánh giá threat model.
6. Dễ xung đột Framework/Jakarta/dependency, gây lỗi runtime và vô hiệu việc nâng cấp an toàn.
7. Mock user giả lập security context, không tự kiểm tra password provider hay token verifier.
8. Không. Chỉ những package thuộc Jakarta EE phù hợp mới chuyển; `javax.crypto`, `javax.net.ssl` vẫn là Java SE.
9. Chưa. Đây là lỗi phân quyền nghiêm trọng cần sửa và regression test.
10. Kiểm tra method interception qua Spring proxy, authority chính xác, tham số SpEL và cả ca bị từ chối.

## 18. Tài liệu chính thức theo dòng phiên bản

- [Spring Security – Reference 6.5 / Java Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security – Reference 7.0 / Java Configuration](https://docs.spring.io/spring-security/reference/7.0/servlet/configuration/java.html)
- [Spring Security – Migrating to 6.0](https://docs.spring.io/spring-security/reference/6.5/migration/index.html)
- [Spring Security – Preparing for 7 / Configuration Migrations](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Spring Security – Migrating to 7.0](https://docs.spring.io/spring-security/reference/7.0/migration/)
- [Spring Security – What's New in 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html)
- [Spring Security – Authorization / Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/7.0/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html)
- [Spring – Security without WebSecurityConfigurerAdapter](https://spring.io/blog/2022/02/21/spring-security-without-the-websecurityconfigureradapter)
- [Spring Boot – Managed Dependency Versions](https://docs.spring.io/spring-boot/appendix/dependency-versions/index.html)
