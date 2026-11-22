# Xử lý ngoại lệ trong bộ lọc tùy chỉnh và ngăn xác thực lặp — Spring Security Servlet

Một bộ lọc xác thực tùy chỉnh có thể hoạt động tốt trong thử nghiệm đơn lẻ nhưng gây lỗi khó chẩn đoán khi tích hợp vào Spring Security: một request bị kiểm tra credential hai lần, login thất bại trả 500 thay vì 401, filter tự viết HTTP response rồi controller vẫn tiếp tục chạy, hoặc filter ném `AuthenticationException` nhưng không có thành phần nào bắt lỗi đúng cách.

Trong **Spring Security Servlet / Spring MVC**, xử lý vấn đề này cần hiểu cả **vị trí của filter**, **ranh giới exception**, **một lần thực thi trên một request/dispatch** và **cách đăng ký filter vào Servlet container so với Spring Security filter chain**. Không thể chỉ thêm `try/catch` hoặc kế thừa `OncePerRequestFilter` rồi coi mọi trường hợp đã giải quyết xong.

Bài học triển khai theo nguyên tắc: **mỗi request chỉ đi vào đúng security chain, bộ lọc chỉ thử authentication khi cần, lỗi có chủ sở hữu xử lý rõ, response không bị ghi nhiều lần và ngữ cảnh xác thực không rò sang request khác**. Ví dụ dùng Spring Security 6.x (Servlet), Spring Boot 3.x và Java 17+ theo mốc minh họa; dự án thật phải kiểm tra phiên bản hiện hành và chính sách hỗ trợ trước khi triển khai.

## 1. Phân biệt lỗi xác thực với lỗi ứng dụng và lỗi phân quyền

Ba loại tình huống có HTTP status điển hình khác nhau nhưng không nên quy tất cả về cùng một handler:

| Tình huống | Exception hoặc trạng thái thường gặp | Response thường phù hợp |
|---|---|---|
| Request không mang credential để vào tài nguyên cần login | Chưa có `Authentication` hợp lệ | 401 hoặc redirect tới login tùy loại client và `AuthenticationEntryPoint` |
| Credential được gửi nhưng không hợp lệ | `BadCredentialsException`, `AuthenticationException` | 401 hoặc failure redirect/response do authentication filter/handler quyết định |
| Credential hợp lệ nhưng thiếu quyền | `AccessDeniedException` hoặc authorization decision bị từ chối | 403 với user đã xác thực |
| Request thiếu CSRF token khi cần | CSRF filter từ chối trước hoặc trong chain | Thường 403, không mặc định là password sai |
| Database, I/O, bug, null pointer hoặc hệ thống ngoài bị lỗi | `DataAccessException`, `IOException`, `RuntimeException` phù hợp | Lỗi server được xử lý bởi tầng thích hợp, không che hết thành “sai mật khẩu” |
| HTTP response đã commit nhưng code tiếp tục ghi | Lỗi vòng đời response | Tránh ghi/chuyển hướng lần hai; log và chẩn đoán đúng điểm commit |

**401 Unauthorized** là yêu cầu xác thực hợp lệ chưa được đáp ứng. **403 Forbidden** là request đã đi tới quyết định từ chối quyền, hoặc bộ lọc bảo vệ như CSRF từ chối. Tên trạng thái 401 hơi khó hiểu; nó không có nghĩa request đã được authorization nhưng không được phép.

Không trả 403 chỉ vì mật khẩu sai, cũng không biến mọi exception không lường trước thành 401. Ngoài HTTP semantics, việc phân biệt này giúp monitoring và điều tra sự cố chính xác hơn.

## 2. Filter chain: ngoại lệ được ném ra ở đâu?

Trong Servlet stack, request thường đi qua:

```text
HTTP request
  |
Servlet container filter chain
  |
DelegatingFilterProxy ("springSecurityFilterChain")
  |
FilterChainProxy
  |
  +-- chọn SecurityFilterChain phù hợp theo thứ tự
        |
        +-- SecurityContextHolderFilter / các filter khác
        +-- custom authentication filter (tùy vị trí addFilter...)
        +-- ExceptionTranslationFilter
        +-- AuthorizationFilter
        +-- controller/service
```

**Đây là sơ đồ khái niệm**, không phải danh sách/định thứ tự cố định của mọi ứng dụng. Filter thực tế phụ thuộc các tính năng được bật và thứ tự được cấu hình.

Điều đặc biệt quan trọng: **`ExceptionTranslationFilter` chỉ bắt exception xuất hiện trong phần xử lý downstream mà nó bao quanh.** Nếu một custom authentication filter nằm **phía trước** `ExceptionTranslationFilter` và chính filter đó ném `AuthenticationException` trước khi gọi downstream, không được mặc định rằng ExceptionTranslationFilter phía sau sẽ bắt exception ấy.

Có hai cách tổ chức phổ biến:

1. **Filter xác thực tự điều phối lỗi của chính mình.** Với custom filter triển khai trực tiếp `OncePerRequestFilter`, bắt `AuthenticationException` phát sinh từ lệnh authenticate và gọi `AuthenticationEntryPoint` hoặc `AuthenticationFailureHandler` tùy flow.
2. **Filter kế thừa cơ chế xác thực đã có.** `AbstractAuthenticationProcessingFilter` và các subclass như `UsernamePasswordAuthenticationFilter` có nhánh `unsuccessfulAuthentication` và `AuthenticationFailureHandler` được framework hỗ trợ.

Do đó cần trả lời trước khi viết code: **exception này phát sinh trong filter nào, filter nào đứng trước/sau nó, và ai sở hữu response?** Không dựa vào suy đoán rằng “Spring Security sẽ bắt mọi `AuthenticationException` ở mọi vị trí”.

## 3. Ranh giới try/catch đúng: chỉ bao phần thử xác thực

Một anti-pattern rất dễ gặp:

```java
try {
    Authentication result = authenticationManager.authenticate(candidate);
    SecurityContextHolder.getContext().setAuthentication(result);
    filterChain.doFilter(request, response);
} catch (AuthenticationException exception) {
    response.sendError(401);
}
```

**Đây là đoạn minh họa lỗi**, chưa có đủ khai báo biến/import. Nó đặt `filterChain.doFilter(...)` **bên trong** khối bắt lỗi authentication của chính filter. Nếu một filter phía sau hoặc method security ném `AuthenticationException`, custom filter có thể bắt nhầm và diễn giải thành “API key sai” dù authentication vừa thành công.

Một mẫu dễ kiểm soát hơn là:

```java
Authentication verified;
try {
    verified = authenticationManager.authenticate(candidate);
} catch (AuthenticationException invalidCredential) {
    SecurityContextHolder.clearContext();
    authenticationEntryPoint.commence(request, response, invalidCredential);
    return;
}

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

try {
    filterChain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

**Đoạn này là mảnh code mô tả cấu trúc**, không phải filter hoàn chỉnh. Biến `candidate` phải là authentication request chưa đáng tin; `authenticationEntryPoint` cần được cấu hình; lỗi từ downstream được để cho thành phần phù hợp xử lý thay vì bị nhận nhầm là lỗi của provider.

Những điểm cần duy trì:

- Bắt đúng `AuthenticationException` phát sinh **từ phép xác thực bạn sở hữu**.
- Sau khi viết response lỗi, **`return`**: không gọi filter chain tiếp nếu request đã bị từ chối.
- Dọn `SecurityContextHolder` ở nhánh thất bại để tránh giữ context sai trong scope hiện tại, nhưng hiểu rằng Spring Security còn có lifecycle cleanup của nó.
- Với filter **stateless**, không tự lưu authentication vào HttpSession chỉ để “sửa” một request tiếp theo thiếu credential.
- Với login **stateful**, sau xác thực thành công còn cần session strategy và `SecurityContextRepository.saveContext(...)` theo flow chuẩn. Đừng copy đoạn stateless rồi kỳ vọng browser có session đăng nhập.

### Không bắt toàn bộ Exception thành BadCredentialsException

`catch (Exception ex) { throw new BadCredentialsException("invalid"); }` có thể che đi lỗi timeout database, lỗi coding hoặc sự cố hệ thống. Kết quả là người dùng liên tục thử mật khẩu, monitoring không phát hiện server lỗi, và vận hành không biết phân biệt lỗi credential với lỗi availability.

Nếu một identity provider/service ngoài ném exception hạ tầng, cân nhắc một `AuthenticationServiceException` hoặc exception chuyên biệt ở đúng tầng và để handler quyết định phản hồi không tiết lộ nội bộ. Nhưng **không ép mọi lỗi thành 401**: hệ thống có thể cần 503/5xx khi provider bị lỗi. Quyết định nên được tiêu chuẩn hóa theo hợp đồng API và kiểm thử.

Không log raw password/API key/token trong catch. Chỉ log mã tương quan request, loại lỗi được chuẩn hóa, thời điểm, user ID đã biết từ nguồn đáng tin, và context vận hành tối thiểu.

## 4. OncePerRequestFilter: “một lần” nghĩa là phạm vi nào?

`OncePerRequestFilter` là lớp cơ sở của Spring Framework giúp tránh thực thi lại `doFilterInternal(...)` nhiều lần **trong cùng một dispatch phù hợp**, bằng cơ chế request attribute đánh dấu filter đã áp dụng. Nó hỗ trợ các hook:

- `shouldNotFilter(HttpServletRequest)`: bỏ qua các request không thuộc phạm vi filter.
- `shouldNotFilterAsyncDispatch()`: điều khiển tham gia những dispatch async; thông thường mặc định không tham gia.
- `shouldNotFilterErrorDispatch()`: điều khiển xử lý error dispatch; thông thường mặc định không tham gia.
- `doFilterInternal(...)`: nơi triển khai logic cho request cần filter xử lý.

**Không diễn giải sai:**

- Một lần **không** có nghĩa chỉ xác thực một lần trong cả phiên đăng nhập.
- Mỗi **HTTP request mới** vẫn có thể cần xác thực lại, nhất là API stateless.
- Một request có thể có dispatch `REQUEST`, `ASYNC` hoặc `ERROR` khác nhau; cấu hình và Servlet container ảnh hưởng việc filter được gọi.
- Nếu bạn tạo **hai filter instances khác nhau**, filter mang tên/marker khác nhau, hoặc hai security chains khác nhau nhận cùng request ở những thời điểm độc lập, không có một khóa “toàn cục” tự ngăn mọi xác thực lặp.
- Nếu đăng ký filter hai chỗ, `OncePerRequestFilter` có thể giúp tránh một số trùng lặp trong một dispatch, nhưng **không biến việc đăng ký trùng thành thiết kế an toàn**. Thứ tự thực thi, handler và cleanup vẫn có thể sai.

### Phạm vi shouldNotFilter

Khi custom authentication chỉ dành cho `/api/secure/**`, không kiểm tra credential trên `/api/public/**`, `/login`, static assets hoặc health endpoint. Nếu kiểm tra mọi request một cách mù quáng, bạn có thể làm trang công khai trả 401 chỉ vì browser đã mang một header lỗi.

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/secure/");
}
```

Đây là **mảnh method**. Với ứng dụng phức tạp, nên dùng matcher Spring Security phù hợp với path/method/context-path và cấu hình multiple chains; không tự coi `startsWith` đơn giản là tương đương mọi pattern MVC. Matcher quá rộng có thể làm filter xác thực trên endpoint không cần thiết; matcher quá hẹp có thể khiến endpoint bí mật không được bảo vệ.

## 5. Vấn đề lớn nhất: một filter được đăng ký hai lần

Trong Spring Boot Servlet, một class triển khai `jakarta.servlet.Filter` được khai báo là **Spring bean** có thể được Boot tự đăng ký vào **Servlet container filter chain**. Đồng thời, nếu gọi:

```java
http.addFilterBefore(customFilter, UsernamePasswordAuthenticationFilter.class);
```

bạn còn đăng ký **chính filter đó vào Spring Security chain**. Cấu hình kết hợp không cẩn thận có thể khiến filter tham gia **hai pipeline**:

```text
Servlet container
  |
  +-- customFilter (đăng ký tự động như một Servlet Filter)
  |
  +-- DelegatingFilterProxy
           |
           +-- FilterChainProxy
                   |
                   +-- customFilter (được addFilterBefore)
```

Hệ quả có thể là:

- `doFilterInternal` hoặc callback liên quan bị chạy không như dự kiến.
- Credential bị kiểm tra hai lần, tăng tải cho `AuthenticationManager` và downstream identity provider.
- Response bị ghi/commit hoặc exception bị xử lý ở nhánh thứ hai.
- Một lượt chạy ngoài Spring Security chain không có context/filter order/exception handler như bên trong chain.
- Đăng nhập thất bại khó kiểm tra vì Servlet filter ngoài chain có lifecycle khác các security filters.

**Cách giải quyết:** xác định filter đó nên được quản lý **chỉ bởi Spring Security** hay là một **container filter độc lập**. Nếu dùng `addFilterBefore` hoặc `addFilterAfter` cho authentication filter, cần ngăn tự động đăng ký cùng bean dưới Servlet container, ví dụ `FilterRegistrationBean.setEnabled(false)`; xem project runnable ở mục 8.

Đừng đổi filter thành `@Component` hay `@Bean` rồi thêm vào security chain mà bỏ qua cơ chế auto-registration của Boot. Đừng cố giải quyết bằng một biến global `static boolean alreadyAuthenticated`: biến đó sai về concurrency, thread safety, scope request và đa instance.

## 6. Đặt filter vào đúng SecurityFilterChain, không chỉ chọn vị trí addFilterBefore

Spring Security có thể có nhiều `SecurityFilterChain` với `securityMatcher` và thứ tự `@Order` khác nhau. `FilterChainProxy` chọn **chain đầu tiên khớp**; không chạy toàn bộ các chain liên tiếp để kiểm tra cùng request.

Một thiết kế rõ phạm vi:

```text
/api/**       -> API chain (custom header authentication, stateless)
/web/**       -> web chain (form login + HttpSession nếu có)
/other/**     -> fallback chain theo chính sách deny/authenticated
```

Với một API chain riêng:

- `securityMatcher("/api/**")` xác định request được chain nhận.
- `shouldNotFilter(...)` xác định endpoint **bên trong chain** có cần custom filter không.
- `authorizeHttpRequests(...)` quyết định quyền truy cập sau khi context đã được thiết lập.
- `addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)` đặt filter vào vị trí tương ứng theo danh sách order của Spring Security.

**Không có fallback chain** có thể khiến một URL nằm ngoài mọi `securityMatcher` không được Spring Security bảo vệ. Ngược lại, đặt cùng filter instance vào nhiều chains với các matcher chồng lấn không biến nó thành hai bước xác thực bổ trợ; thường chỉ tạo khó khăn về quản lý trách nhiệm.

Cần xem thứ tự thực tế và được chọn qua integration tests thay vì suy đoán từ tên method bean.

## 7. Error dispatch, async dispatch và response đã commit

Servlet request có thể đi qua một số loại dispatch:

| Dispatch | Đặc điểm | Rủi ro khi filter custom không được kiểm soát |
|---|---|---|
| `REQUEST` | Request gốc từ client | Logic xác thực chính; cần chạy đúng một lần trong phạm vi |
| `ERROR` | Dispatch tới error page sau một lỗi HTTP/exception | Xác thực lại trên error page, thay đổi status, tạo vòng lặp lỗi |
| `ASYNC` | Tiếp tục xử lý request bất đồng bộ | Đọc holder sai thread, chạy lại xác thực không cần thiết |
| `FORWARD` | Chuyển nội bộ đến resource khác | Matcher và filter dispatcher type có thể khác request gốc |

**`OncePerRequestFilter` không thay thế cấu hình dispatcher types và security context propagation.** Mặc định phương thức hook thường bỏ qua async/error dispatch, nhưng Servlet registration, container và filter chain cũng ảnh hưởng việc request đến filter. Nếu API thực sự phải bảo vệ một ERROR/ASYNC dispatch, phải thiết kế và test cụ thể; không chỉ đổi hook sang `false` mà không có lý do.

Vấn đề response commit:

```java
response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
filterChain.doFilter(request, response);  // SAI: tiếp tục sau khi từ chối
```

Nếu filter đã trả lỗi, cần `return`. Gọi `sendError` có thể kích hoạt ERROR dispatch trong Servlet container, khiến routing phức tạp hơn. Với stateless API có hợp đồng trả 401 đơn giản, có thể dùng `response.setStatus(401)` và kết thúc xử lý, để tránh một error dispatch không cần thiết; nếu cần JSON response thì đặt content type/body phù hợp, viết **một lần** và không leak nội dung exception.

Không ghi body sau khi `response.isCommitted()` đã true. Với request đã đi sâu xuống downstream, nếu lỗi xảy ra sau khi response commit, không thể tin rằng entry point hay failure handler còn ghi một response hoàn chỉnh mới; thiết kế cần xử lý thời điểm commit đúng.

## 8. Ví dụ Java 17+ đầy đủ: custom authentication, lỗi 401/403 và không đăng ký filter trùng

Ví dụ tạo Spring Boot Servlet app nhỏ, có API dùng header `X-Demo-Key`. Chúng ta **không dùng nó như cơ chế API key production**: key mẫu hard-code chỉ để học, chưa có provisioning, rotation, revocation, scope, replay/abuse control và quản lý bí mật. Trong sản phẩm thực, **ưu tiên cơ chế chuẩn** như OAuth2 Resource Server/bearer token, mTLS hoặc giải pháp API-key đã được thiết kế và audit.

Mục tiêu kỹ thuật ví dụ:

- `DemoKeyFilter` kế thừa `OncePerRequestFilter`.
- Filter chỉ thử xác thực trên `/api/secure/**`.
- Không có header: để authorization/entry point trả 401; **không thử xác thực**.
- Có header sai: provider ném `AuthenticationException`, filter bắt lỗi đúng phạm vi và trả 401; **không chạy controller**.
- Header đúng: đặt authentication hợp lệ vào `SecurityContextHolder`, downstream authorization kiểm tra role.
- Có authentication nhưng thiếu role ADMIN: trả 403, **không bị filter bắt nhầm thành credential error**.
- Filter bean được **vô hiệu hóa đăng ký tự động vào Servlet container** và chỉ tham gia Spring Security chain.
- Các test đếm số lần provider được gọi và số lần `doFilterInternal` chạy cho request có header, giảm nguy cơ hồi quy đăng ký trùng.

### 8.1. Cấu trúc dự án

```text
custom-filter-demo/
├── pom.xml
└── src/
    ├── main/java/example/filterdemo/
    │   ├── FilterDemoApplication.java
    │   ├── DemoKeyAuthenticationProvider.java
    │   ├── DemoKeyFilter.java
    │   ├── ApiSecurityConfig.java
    │   └── ApiController.java
    └── test/java/example/filterdemo/
        └── DemoKeyFilterTest.java
```

### 8.2. pom.xml

Ví dụ dùng **Spring Boot 3.3.5** và Java 17, chỉ như một mốc tái tạo minh họa; không khẳng định bản này là bản stable mới nhất hoặc còn được hỗ trợ.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>custom-filter-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
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
```

Spring Boot parent quản lý phiên bản Security và Framework tương thích. Không tự gắn một `spring-security-web` khác version với framework để “sửa nhanh” lỗi filter order.

### 8.3. Entry point

Tạo `src/main/java/example/filterdemo/FilterDemoApplication.java`:

```java
package example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
```

### 8.4. AuthenticationProvider chỉ dùng trong bài demo

Tạo `src/main/java/example/filterdemo/DemoKeyAuthenticationProvider.java`:

```java
package example.filterdemo;

import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public class DemoKeyAuthenticationProvider implements AuthenticationProvider {

    private final PasswordEncoder encoder = new BCryptPasswordEncoder();
    private final String keyVerifier = encoder.encode("demo-only-key");
    private final AtomicInteger attempts = new AtomicInteger();

    @Override
    public Authentication authenticate(Authentication authentication) {
        attempts.incrementAndGet();

        Object candidate = authentication.getCredentials();
        if (!"demo-client".equals(authentication.getName())
                || !(candidate instanceof String presentedKey)
                || !encoder.matches(presentedKey, keyVerifier)) {
            throw new BadCredentialsException("Bad credentials");
        }

        return UsernamePasswordAuthenticationToken.authenticated(
            "demo-client",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_API"))
        );
    }

    @Override
    public boolean supports(Class<?> authenticationType) {
        return UsernamePasswordAuthenticationToken.class
            .isAssignableFrom(authenticationType);
    }

    int attemptCount() {
        return attempts.get();
    }
}
```

Trong demo, chuỗi `demo-only-key` xuất hiện trong source chỉ để tạo fixture; nó không phải secret sản xuất. Việc dùng BCrypt để kiểm chứng **không biến một secret hard-coded thành key an toàn**, cũng không thay thế chính sách key rotation và giới hạn sử dụng. Lớp provider không log hoặc trả credential về client.

Phép kiểm chứng nằm trong provider; filter **không** tự so sánh password/API key và không tự đánh dấu một token chưa kiểm chứng thành authenticated.

### 8.5. OncePerRequestFilter tập trung vào một trách nhiệm

Tạo `src/main/java/example/filterdemo/DemoKeyFilter.java`:

```java
package example.filterdemo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class DemoKeyFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;
    private final AtomicInteger invocations = new AtomicInteger();

    public DemoKeyFilter(AuthenticationManager authenticationManager) {
        this.authenticationManager = authenticationManager;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return !request.getServletPath().startsWith("/api/secure/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        invocations.incrementAndGet();
        String key = request.getHeader("X-Demo-Key");

        if (key == null) {
            // Không có credential: để authorization/entry point quyết định.
            chain.doFilter(request, response);
            return;
        }

        Authentication verified;
        try {
            Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                    "demo-client", key
                );
            verified = authenticationManager.authenticate(candidate);
        } catch (AuthenticationException invalidCredential) {
            // Chỉ bắt lỗi của authenticate(...), KHÔNG bắt lỗi downstream.
            SecurityContextHolder.clearContext();
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        try {
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }

    int invocationCount() {
        return invocations.get();
    }
}
```

Tại sao thứ tự này có ý nghĩa?

- Không header: filter **không** tạo request authentication vô ích. Nếu URL cần quyền, authorization của Spring Security sẽ dẫn đến entry point trả 401.
- Header sai: `AuthenticationManager.authenticate` ném `AuthenticationException`, filter bắt trực tiếp trước khi response commit, trả 401 và dừng.
- Header đúng: provider trả một Authentication với `ROLE_API`; context mới được đặt cho phần downstream. Bộ authorization vẫn có thể từ chối nếu endpoint đòi `ROLE_ADMIN`.
- `chain.doFilter` **nằm ngoài try/catch AuthenticationException**, nên lỗi ở filter/controller phía sau không bị diễn giải sai thành credential không hợp lệ.
- `finally` dọn holder ngay cả khi downstream ném exception; Spring Security còn có cleanup của security-context filter. Đây là demo stateless, nên **không save context vào session**.
- Biến `AtomicInteger` chỉ để đo hành vi trong test, không nên dùng như security control hoặc bộ đếm toàn hệ thống ở production.

Với filter authentication stateful, mô hình khác: có thể cần `SessionAuthenticationStrategy`, `SecurityContextRepository.saveContext(...)`, success/failure handlers. Đừng đem nguyên class stateless này ghép vào form-login session rồi kỳ vọng đăng nhập vẫn còn sau redirect.

### 8.6. Security configuration, filter bean và chặn auto-registration

Tạo `src/main/java/example/filterdemo/ApiSecurityConfig.java`:

```java
package example.filterdemo;

import java.util.List;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class ApiSecurityConfig {

    @Bean
    AuthenticationManager demoAuthenticationManager(
            DemoKeyAuthenticationProvider provider) {
        return new ProviderManager(List.of(provider));
    }

    @Bean
    DemoKeyFilter demoKeyFilter(AuthenticationManager demoAuthenticationManager) {
        return new DemoKeyFilter(demoAuthenticationManager);
    }

    @Bean
    FilterRegistrationBean<DemoKeyFilter> disableContainerRegistration(
            DemoKeyFilter filter) {
        FilterRegistrationBean<DemoKeyFilter> registration =
            new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http, DemoKeyFilter filter)
            throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/secure/admin").hasRole("ADMIN")
                .requestMatchers("/api/secure/**").hasRole("API")
                .anyRequest().denyAll())
            .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth.anyRequest().denyAll())
            .build();
    }
}
```

**Những chỗ quan trọng trong cấu hình:**

1. Bean `DemoKeyFilter` là một Servlet `Filter`. Vì đã đưa vào Spring Security chain bằng `addFilterBefore`, ta khai báo `FilterRegistrationBean.setEnabled(false)` để Spring Boot **không đăng ký cùng bean làm filter độc lập ngoài security chain**.
2. API chain có matcher riêng và order 1. Fallback chain order 2 giúp URL ngoài API **không vô tình nằm ngoài mọi chain**.
3. API stateless chỉ sử dụng credential gửi chủ động qua header. Việc tắt CSRF **chỉ trong chain API này** là quyết định có mục đích cho demo header-token, **không được copy sang website form login sử dụng cookie/session**. Nếu browser tự gửi credential qua cookie, phải phân tích CSRF lại.
4. Trong cấu hình này, API client không cần redirect HTML: authentication entry point trả 401. Access denied với principal có role không đủ sẽ thường trả 403 qua access-denied handling.
5. `ProviderManager` chỉ gọi provider demo cho token của filter. Với hệ thống thật, không dùng một provider giả key cố định để thay thế OAuth2 Resource Server hoặc API-key infrastructure.
6. `hasRole("API")` kiểm tra authority `ROLE_API`; `hasRole("ADMIN")` đòi `ROLE_ADMIN`. Không đánh dấu người dùng đã authenticate là tự có toàn quyền.
7. `FilterRegistrationBean.setEnabled(false)` không vô hiệu filter bên trong security chain: nó chỉ vô hiệu **đường đăng ký container** do Boot thực hiện.

Một số ứng dụng có custom filter được tạo bằng `new` trực tiếp trong config (không phải bean), hoặc dùng cơ chế `DelegatingFilterProxy` riêng. Khi đó cách tránh trùng phải căn theo **đường đăng ký thực tế**, không lặp máy móc mọi bean/method trên.

### 8.7. Controller public và protected

Tạo `src/main/java/example/filterdemo/ApiController.java`:

```java
package example.filterdemo;

import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/health")
    public String health() {
        return "PUBLIC_OK";
    }

    @GetMapping("/api/secure/data")
    public String data(Principal principal) {
        return "Hello, " + principal.getName();
    }

    @GetMapping("/api/secure/admin")
    public String admin(Principal principal) {
        return "ADMIN_ONLY: " + principal.getName();
    }
}
```

Controller không tự kiểm tra header và không tự gọi manager lần nữa. Điều đó tránh việc **vừa xác thực ở filter, vừa xác thực lại ở controller**. Nếu nghiệp vụ cần role/object-level authorization, đặt kiểm tra quyền ở security layer/service đúng vị trí, không gửi raw credential xuống service chỉ để mỗi method tự xác thực lại.

### 8.8. Integration tests cho exception và xác thực lặp

Tạo `src/test/java/example/filterdemo/DemoKeyFilterTest.java`:

```java
package example.filterdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class DemoKeyFilterTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    DemoKeyFilter filter;

    @Autowired
    DemoKeyAuthenticationProvider provider;

    @Test
    void publicEndpointSkipsCustomAuthentication() throws Exception {
        int before = filter.invocationCount();

        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk())
            .andExpect(content().string("PUBLIC_OK"));

        assertEquals(before, filter.invocationCount());
    }

    @Test
    void missingCredentialYieldsUnauthorized() throws Exception {
        int attempted = provider.attemptCount();

        mvc.perform(get("/api/secure/data"))
            .andExpect(status().isUnauthorized());

        assertEquals(attempted, provider.attemptCount());
    }

    @Test
    void invalidCredentialYieldsUnauthorized() throws Exception {
        int before = provider.attemptCount();

        mvc.perform(get("/api/secure/data").header("X-Demo-Key", "invalid"))
            .andExpect(status().isUnauthorized());

        assertEquals(before + 1, provider.attemptCount());
    }

    @Test
    void validCredentialAuthenticatesExactlyOnce() throws Exception {
        int beforeFilter = filter.invocationCount();
        int beforeProvider = provider.attemptCount();

        mvc.perform(get("/api/secure/data")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isOk())
            .andExpect(content().string("Hello, demo-client"));

        assertEquals(beforeFilter + 1, filter.invocationCount());
        assertEquals(beforeProvider + 1, provider.attemptCount());
    }

    @Test
    void authenticatedButWrongRoleIsForbidden() throws Exception {
        mvc.perform(get("/api/secure/admin")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isForbidden());
    }

    @Test
    void requestWithoutCredentialDoesNotInheritPreviousContext()
            throws Exception {
        mvc.perform(get("/api/secure/data")
                .header("X-Demo-Key", "demo-only-key"))
            .andExpect(status().isOk());

        mvc.perform(get("/api/secure/data"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Kỳ vọng của 6 test khi chạy đúng môi trường**:

- Public GET được phục vụ mà `doFilterInternal` của custom filter không chạy.
- Không có credential dẫn tới 401 do authorization/entry point, provider không bị gọi.
- Key sai dẫn tới 401 do custom filter trực tiếp xử lý `AuthenticationException`, provider được gọi một lần.
- Key đúng dẫn tới 200, filter/provider được gọi **đúng một lần** cho request trong test.
- Key đúng nhưng không có role ADMIN dẫn tới 403 do authorization, **không** bị catch như key sai.
- Request mới không có header không dùng lại `SecurityContext` của request trước.

Test đếm bằng `AtomicInteger` kiểm chứng hành vi trên **cùng ứng dụng test chạy tuần tự**; nếu test chạy song song hoặc request khác chạy đồng thời, bộ đếm toàn bean không thể dùng assertion delta mà không cô lập traffic. Đây là hỗ trợ quan sát, không phải hợp đồng bảo mật production.

### 8.9. Lệnh chạy

Trong thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

Với JDK 17+, Maven và dependencies resolve được, dự kiến **6 test pass**. Dòng log Maven/Boot phụ thuộc môi trường; không khẳng định đây là kết quả đã chạy thực tế. Demo có thể dùng cổng 8080 mặc định nếu chưa bị chiếm.

Ở terminal khác:

```bash
curl -i http://localhost:8080/api/public/health
curl -i http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: invalid" http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: demo-only-key" http://localhost:8080/api/secure/data
curl -i -H "X-Demo-Key: demo-only-key" http://localhost:8080/api/secure/admin
```

Kỳ vọng theo thứ tự: `200 PUBLIC_OK`, `401`, `401`, `200 Hello, demo-client`, `403`. Đừng triển khai token mẫu cố định này lên mạng công khai; đây là fixture để chứng minh đường đi exception và filter, không phải hệ quản lý API key.

## 9. Khi dùng AbstractAuthenticationProcessingFilter thay vì OncePerRequestFilter

Nếu custom filter đại diện cho **endpoint đăng nhập tương tác** như POST một form hoặc callback authentication, kế thừa `AbstractAuthenticationProcessingFilter` có thể đúng hơn:

- `requiresAuthentication`/`RequestMatcher` xác định request login.
- `attemptAuthentication` gọi manager/provider và có ba kết quả: Authentication thành công, `null` chưa hoàn tất, hoặc `AuthenticationException`.
- `successfulAuthentication` phối hợp session strategy, context repository, remember-me và success handler.
- `unsuccessfulAuthentication` dọn holder và gọi failure handler.

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) throws AuthenticationException {
    // Tạo token chưa được tin cậy, gọi AuthenticationManager,
    // trả Authentication đã xác thực hoặc ném AuthenticationException.
}
```

Đây chỉ là **phác thảo hook**, chưa có method body/return đầy đủ, không phải class biên dịch độc lập. Tùy biến handler để đổi redirect hoặc response thường tốt hơn override `successfulAuthentication` chỉ để viết JSON.

Khi override success/failure hook, cần biết việc gọi `super.successfulAuthentication(...)` hoặc `super.unsuccessfulAuthentication(...)` có vai trò quan trọng: logic của lớp cơ sở xử lý SecurityContext, repository, remember-me, event và handler. Bỏ `super` mà không tái hiện hợp đồng có thể làm context không được lưu hoặc response bị viết hai lần.

Ngược lại, một filter đọc credential ở mọi HTTP request API (stateless) thường phù hợp với `OncePerRequestFilter`, nhưng nếu framework đã có filter chuẩn như `BearerTokenAuthenticationFilter`, nên sử dụng nó thay vì tự viết lại token parsing và validation.

## 10. Ngăn xác thực lặp không phải là cache “đã đăng nhập” vô thời hạn

Một số người tránh xác thực lặp bằng cách đặt:

```java
private static boolean authenticated = false;
```

**Sai về bảo mật và concurrency**: cờ static có phạm vi cả JVM, không gắn vào request, principal hay client. Một user đăng nhập có thể khiến request khác bị coi là authenticated, hoặc nhiều thread gây race. Không bao giờ dùng cờ global để bỏ kiểm tra credential.

Một phương án khác là chỉ nhìn:

```java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

if (current != null && current.isAuthenticated()) {
    // Có thể bỏ authentication?
}
```

Cũng **không đủ căn cứ** để áp dụng máy móc: anonymous token cũng có thể biểu diễn trạng thái authenticated theo nghĩa kỹ thuật; `isAuthenticated()` không tự xác định đây là principal từ nguồn nào hoặc còn đáp ứng yêu cầu endpoint không. Nếu thực sự cần tối ưu, phải xác định chain, trusted authentication source, credentials, principal và policy; không bỏ qua kiểm chứng token chỉ vì holder chứa một object.

### Những kiểu xác thực lặp thường gặp

| Dạng lặp | Ví dụ | Hướng ngăn |
|---|---|---|
| Đăng ký cùng filter ở container và Security chain | Bean implements Filter + `addFilterBefore` | Disable container registration hoặc chọn chỉ một nơi |
| Cùng request chạy lại filter trong async/error dispatch | Hook hoặc dispatcher mapping cho phép xử lý lại | Thiết kế theo dispatcher types; dùng `OncePerRequestFilter` và test |
| Hai filter khác nhau cùng đọc một credential | Custom bearer filter + Resource Server filter chuẩn | Giữ một source of truth; bỏ filter dư |
| Filter và controller cùng gọi authenticate | Controller tự kiểm tra header sau khi filter đã làm | Đẩy authentication vào filter/provider, controller đọc principal |
| Nhiều chains có matcher sai và nhiều filter instances | Chain API + chain web cấu hình không nhất quán | Ưu tiên securityMatcher/order rõ và fallback chain |
| Client retry POST login | Client timeout rồi gửi lại | Idempotency và retry policy tại application; không dùng static flag |
| Microservice gateway và backend đều xác thực token | Nhiều trust boundaries có thể yêu cầu xác minh độc lập | Không bỏ kiểm tra ở backend chỉ vì gateway đã nhận token |
| Một request mới của API stateless | Client gọi lại với bearer/header credential | Có thể cần xác thực mỗi request; đây **không phải lặp sai** |

Chỉ gọi `AuthenticationManager.authenticate(...)` một lần **trong filter** chưa đủ nếu còn một filter khác hoặc controller khác cũng gọi manager. Muốn kiểm soát tận gốc cần sơ đồ ownership và integration tests end-to-end.

## 11. Retry, multi-thread, async và sự kiện đăng nhập

“Ngăn xác thực lặp” có hai lớp ngữ nghĩa:

1. **Kỹ thuật filter invocation:** tránh thực thi sai hai lần trong cùng request/dispatch do đăng ký trùng, filter chain sai hoặc custom code gọi authenticate ở hai tầng.
2. **Nghiệp vụ:** người dùng/client có thể thực sự gửi **hai HTTP requests** gần nhau, do double click, retry, load balancer, timeout hoặc refresh. `OncePerRequestFilter` không hợp nhất hai request độc lập.

Nếu authentication thành công có **side effect** như gửi email, tạo audit record, ghi sự kiện hoặc cấp one-time token, cần thiết kế idempotency, khóa giao dịch hoặc deduplication tại đúng tầng nghiệp vụ. Không đặt `static Set<String> processedRequestIds` không giới hạn làm biện pháp chống lặp: nó dễ rò bộ nhớ, sai khi ứng dụng nhiều instance và có nguy cơ đánh đồng người dùng.

Một số câu hỏi cần trả lời:

- Client retry có được phép với flow login không?
- Nếu tạo one-time credential, cơ chế tiêu thụ token có atomic và chống replay không?
- Event/audit có thể phát trùng do ít nhất một lần giao nhận ở hệ thống message queue không?
- Trong async dispatch, SecurityContext có được truyền sang thread thực thi đúng cách không?
- Nếu response đã commit, có ai còn cố redirect hoặc phát thông báo thành công lần nữa không?

**Request attribute marker của OncePerRequestFilter** chỉ là điều kiện thực thi filter trong request, không phải hệ thống idempotency phân tán. Các hệ thống cấp token hoặc giao dịch có side effect cần cơ chế riêng và kiểm thử các tình huống retry.

## 12. Xử lý exception và security context theo luồng stateful

Bài ví dụ ở mục 8 là **API stateless**; mỗi request mang header và context không được lưu vào session. Còn với custom **form login/session**, sau khi provider xác minh credential thành công, có thêm trách nhiệm:

```text
1. Nhận request login đúng method/path và kiểm tra CSRF theo chính sách.
2. AuthenticationManager.authenticate(untrustedToken).
3. SessionAuthenticationStrategy.onAuthentication(...).
4. Tạo SecurityContext mới chứa Authentication đã xác minh.
5. SecurityContextHolder.setContext(context).
6. SecurityContextRepository.saveContext(context, request, response).
7. SuccessHandler quyết định redirect/response.
8. Khi thất bại: dọn context và gọi FailureHandler đúng một lần.
```

Trong Spring Security 6, `SecurityContextHolderFilter` không tự lưu mọi thay đổi context từ custom code. Nếu bạn quên `saveContext` trong flow tự xây, HTTP 302 login thành công có thể theo sau bằng request anonymous. Đừng nhầm đây là “filter bị chạy lại sai”: với session login, request mới cần được khôi phục authentication từ repository.

**Chỉ xử lý `AuthenticationException` từ phép authenticate bạn sở hữu**, không bắt `Exception` từ toàn bộ controller để tự chuyển thành lỗi password. Nếu session strategy từ chối đăng nhập bằng `SessionAuthenticationException`, flow failure phải xử lý riêng theo chính sách. Trong mã standard form login, `AbstractAuthenticationProcessingFilter` đã tổ chức những nhánh này; ưu tiên dùng nó khi hợp với giao thức.

Tránh gọi `sessionAuthenticationStrategy.onAuthentication(...)` hoặc `securityContextRepository.saveContext(...)` lần thứ hai ở success handler nếu filter chuẩn đã làm. Một chiến lược session có thể đổi ID hoặc đăng ký phiên, nên gọi lặp có thể tạo lỗi concurrency hoặc phát sự kiện không đúng.

## 13. Kiểm thử sâu hơn: ngoài status code cần quan sát điều gì?

**Status 401/403/200 chưa chứng minh filter chỉ chạy một lần.** Để chứng minh, cần kiểm tra đúng boundary:

1. **Filter invocation count:** mỗi request đúng scope làm `doFilterInternal` chạy một lần trong test tuần tự.
2. **Provider attempt count:** một request có credential gọi `AuthenticationManager.authenticate` đúng một lần.
3. **No duplicate servlet registration:** cùng bean không chạy ngoài chain với order không kiểm soát.
4. **Correct response ownership:** invalid credential không vào controller, không gọi downstream, không leak credential và không viết response lần hai.
5. **Wrong role is authorization failure:** request authenticated nhưng thiếu role phải đi nhánh 403 chứ không biến thành BadCredentialsException.
6. **SecurityContext cleanup:** request mới không mang credential không dùng lại principal từ request cũ.
7. **Request matching:** public route không bắt user cung cấp header giả.
8. **Error/async dispatch:** cấu hình và test riêng nếu app có async/error routes.
9. **Resilience:** provider bị timeout/exception hạ tầng không bị chuyển máy móc thành lỗi mật khẩu.
10. **Load/concurrency:** đo hành vi khi nhiều requests đồng thời, không tin rằng counter demo hoặc ThreadLocal tự tạo là security boundary.

Một integration test thật còn có thể đưa request qua container/embedded server để kiểm tra chính xác Servlet filter registration. `MockMvc` rất hữu ích nhưng không mô phỏng mọi cấu hình/error dispatch của reverse proxy và servlet container production. Vì thế unit + MockMvc test **và** kiểm thử real container ở môi trường triển khai thường bổ trợ nhau.

## 14. Checklist khi đưa custom filter vào ứng dụng thật

- [ ] Đã xác định Servlet stack, `FilterChainProxy`, đúng SecurityFilterChain và thứ tự filter.
- [ ] Filter có matcher/path/method rõ, không xử lý tất cả endpoints tùy tiện.
- [ ] Credential được xác minh qua manager/provider đáng tin; filter không tự đánh dấu untrusted input là authenticated.
- [ ] `AuthenticationException` từ authenticate được xử lý ở đúng điểm, không catch lỗi từ toàn bộ downstream chain.
- [ ] Response 401/403/5xx có hợp đồng rõ ràng; sau khi xử lý lỗi có `return`, không ghi response lần hai.
- [ ] Không log password, API key, JWT, session ID hoặc raw credential.
- [ ] Dùng `OncePerRequestFilter` phù hợp với dispatcher types, nhưng không xem nó là idempotency cho nhiều HTTP requests.
- [ ] Không đăng ký cùng filter qua cả Servlet container và Spring Security; cân nhắc `FilterRegistrationBean.setEnabled(false)` khi dùng Spring bean Filter.
- [ ] Không có hai filter/parser và controller cùng thực hiện authentication cho một credential một cách không cần thiết.
- [ ] `SecurityContextHolder` được thiết lập và dọn đúng; nếu stateful, session strategy/context repository được lưu đúng lúc.
- [ ] API stateless không vô tình lưu authentication vào session hoặc dùng static “already authenticated” flag.
- [ ] CSRF/session/HTTPS được thiết kế dựa trên cách client gửi credential, không tắt bảo mật toàn cục để làm thử nghiệm pass.
- [ ] Có test 200, 401 (thiếu/sai credential), 403 (đã xác thực nhưng thiếu quyền), no-credential ở request mới.
- [ ] Có test provider/filter invocation count và test container registration/dispatch khi hệ thống phức tạp.
- [ ] Các side effect của login/token issuance có thiết kế retry/idempotency riêng, không dựa vào request filter marker.

### Câu hỏi tự kiểm tra

**1.** Custom filter đứng trước `ExceptionTranslationFilter`, tự ném `BadCredentialsException` rồi hy vọng ExceptionTranslationFilter phía sau luôn bắt được. Đúng không?  
**Đáp án:** Không. Thành phần phía sau không tự bao ngoài phép xử lý phía trước. Bắt lỗi của `AuthenticationManager.authenticate` ngay trong filter hoặc dùng cơ chế authentication failure handler được Spring Security hỗ trợ.

**2.** Vì sao không đặt `filterChain.doFilter(...)` trong một khối `try/catch(AuthenticationException)` rộng?  
**Đáp án:** Vì exception từ downstream có thể bị hiểu nhầm là credential error của filter, làm sai status, handler và log.

**3.** Một filter là Spring bean vừa được Boot auto-register vừa được `http.addFilterBefore`. Rủi ro gì?  
**Đáp án:** Nó có thể tham gia cả container filter chain và security filter chain, gây xử lý lặp/order khó kiểm soát. Cần chọn một nơi đăng ký; với bean Filter chỉ dùng trong security chain, disable container registration thích hợp.

**4.** `OncePerRequestFilter` bảo đảm hai HTTP requests retry độc lập chỉ được xử lý một lần?  
**Đáp án:** Không. Nó hạn chế lời gọi nội bộ trong một phạm vi request/dispatch; idempotency/retry nhiều requests là một trách nhiệm khác.

**5.** Credential đúng nhưng thiếu `ROLE_ADMIN`, API nên trả 401 vì key “không đủ mạnh” không?  
**Đáp án:** Không. Credential đã xác minh danh tính; thiếu quyền là authorization failure, thường trả 403.

**6.** Vì sao API ví dụ không lưu `SecurityContext` vào HttpSession?  
**Đáp án:** Nó được thiết kế stateless; mỗi request phải mang credential. Chỉ lưu session khi đó là chủ đích của giao thức khác, ví dụ form login stateful.

**7.** Login POST thành công rồi request sau bị chuyển lại trang login có nhất thiết là filter chạy lặp không?  
**Đáp án:** Không. Có thể custom login chưa lưu SecurityContext vào repository hoặc client không giữ đúng session cookie.

**Kết luận:** xử lý exception trong custom authentication filter phải **đúng điểm phát sinh, đúng chủ thể chịu trách nhiệm phản hồi, đúng loại status**, trong khi chống xác thực lặp phải kiểm soát đồng thời **matcher, chain selection, filter registration, dispatch và việc authenticate tại một nguồn duy nhất**. `OncePerRequestFilter` hỗ trợ giới hạn thực thi trong request, còn `FilterRegistrationBean` và thiết kế security chain giúp tránh đăng ký trùng. Với flow stateful hoặc side effects, vẫn cần session persistence và idempotency riêng.