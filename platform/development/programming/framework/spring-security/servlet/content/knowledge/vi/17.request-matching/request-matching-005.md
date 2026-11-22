# AndRequestMatcher, OrRequestMatcher và NegatedRequestMatcher trong Spring Security Servlet

## 1. Bài toán và mục tiêu

Trong Spring Security Servlet, một điều kiện áp dụng chính sách bảo mật thường không chỉ là “đường dẫn bằng `/api/report`”. Ta có thể cần ghép nhiều tiêu chí:

- Request phải dùng **GET** và thuộc một trong hai nhóm URL `/api/reports/**` hoặc `/api/history/**`.
- Request **không** được thuộc nhánh nội bộ `/api/reports/internal/**`.
- Các URL nội bộ có quy tắc phân quyền riêng dành cho administrator.
- Các URL khác phải bị từ chối nếu ứng dụng chưa định nghĩa chính sách.
- Mọi thao tác ghép điều kiện phải được kiểm thử trên request Servlet thật, không chỉ so sánh chuỗi URL bằng `contains`.

Spring Security cung cấp `RequestMatcher` và ba implementation kết hợp điều kiện:

1. **`AndRequestMatcher`**: tất cả matcher thành phần phải khớp.
2. **`OrRequestMatcher`**: chỉ cần ít nhất một matcher thành phần khớp.
3. **`NegatedRequestMatcher`**: đảo kết quả true/false của một matcher thành phần.

Chúng giúp diễn đạt rule có chủ đích, thay vì viết một filter khổng lồ với điều kiện `if` lồng nhau. Tuy nhiên, **matcher chỉ quyết định một request có khớp không**; nó không tự xác thực user, không tự trao quyền và không bảo đảm endpoint an toàn nếu ta dùng matcher ở sai vị trí.

Bài tập trung vào **khớp yêu cầu** trong Spring Security Servlet, bao gồm cú pháp, phép toán logic, cách kết hợp với `authorizeHttpRequests`, phạm vi `SecurityFilterChain` và kiểm thử Java 17.

## 2. RequestMatcher là gì?

`org.springframework.security.web.util.matcher.RequestMatcher` là abstraction nhận một `HttpServletRequest` và trả về việc request có phù hợp với điều kiện hay không.

Ý tưởng đơn giản:

```java
// Chữ ký chủ chốt của RequestMatcher; đây là minh họa, không định nghĩa lại thư viện.
boolean matches(HttpServletRequest request);
```

Một matcher có thể quan sát các yếu tố phù hợp của request:

- Servlet path, path info và context path theo implementation.
- HTTP method: `GET`, `POST`, `PUT`, `DELETE`, v.v.
- Header, content type, host hoặc thuộc tính khác khi xây custom matcher.
- Metadata phụ thuộc framework, ví dụ quy tắc path của Spring MVC nếu dùng MVC-aware matcher.

Vì vậy một request có thể được kiểm tra theo nhiều chiều; không nên đồng nhất “request matcher” với “chuỗi URL có prefix X”.

Ví dụ với `AntPathRequestMatcher`:

```java
RequestMatcher reports =
    new AntPathRequestMatcher("/api/reports/**");

RequestMatcher onlyGetApi =
    new AntPathRequestMatcher("/api/**", "GET");
```

Các đoạn minh họa này cần import `RequestMatcher` và `AntPathRequestMatcher` từ package `org.springframework.security.web.util.matcher`. Chúng được dùng trong phương thức Java hoặc bean có classpath Spring Security, không phải chương trình `javac` độc lập.

`AntPathRequestMatcher` ở ví dụ Spring Security 6.3.x có thể khớp theo pattern và optional method. Một số phiên bản Spring Security mới hơn thay đổi khuyến nghị hoặc deprecate API matcher này; khi nâng cấp cần xem tài liệu API đúng phiên bản và cân nhắc matcher dùng `PathPattern`/Spring MVC phù hợp.

### 2.1. Kết quả matches không phải Authentication

Giả sử `reports.matches(request)` trả `true`. Điều đó chỉ nói request nằm trong vùng path đã xác định; nó **không** bảo đảm:

- request đã có `Authentication`;
- user mang authority `ROLE_READER`;
- user sở hữu báo cáo được yêu cầu;
- CSRF token hợp lệ;
- method có thể được phép thực hiện;
- controller sẽ trả 200.

Với Spring Security, việc áp dụng rule như `.hasRole("READER")` hoặc `.authenticated()` phải nằm ở authorization layer, sau khi request được nhận diện bằng matcher.

## 3. AndRequestMatcher: mọi điều kiện phải đúng

`AndRequestMatcher` kết hợp các matcher theo phép **AND**:

```text
AND(A, B, C) == A && B && C
```

Ví dụ: chỉ khớp khi là GET **và** đường dẫn thuộc khu vực reports:

```java
RequestMatcher getReports = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new AntPathRequestMatcher("/api/reports/**")
);
```

| Request | GET trong `/api/**`? | Thuộc `/api/reports/**`? | Kết quả AND |
| --- | --- | --- | --- |
| GET `/api/reports/summary` | Có | Có | **true** |
| POST `/api/reports/summary` | Không | Có | false |
| GET `/api/history/list` | Có | Không | false |
| GET `/web/reports/summary` | Không | Không | false |

Việc ghép path và method rất hữu ích khi một URL xử lý nhiều HTTP methods nhưng quyền truy cập khác nhau theo method. Ví dụ GET có thể là thao tác chỉ đọc, còn POST tạo báo cáo phải có authorization và CSRF policy riêng.

### 3.1. AND không tự bảo đảm một tập điều kiện “an toàn”

Nếu ta viết `AND(isGet, isTrustedHeader)`, kết quả vẫn có thể sai về an ninh nếu “trusted header” là header do client tự gắn. Matcher chỉ thực hiện điều kiện được cung cấp, không xác minh giả định nghiệp vụ về độ đáng tin.

Cần đặc biệt tránh dùng matcher tự kiểm `X-User-Role: admin` như bằng chứng phân quyền. Authority phải lấy từ nguồn authentication/authorization đáng tin, không phải một request header tùy ý của attacker.

### 3.2. Tính chất khi có nhiều matcher

`AndRequestMatcher` thường đánh giá các thành phần cho tới khi gặp một điều kiện false; những điều kiện còn lại không cần đánh giá để kết luận. Không thiết kế matcher chứa side effects, vì số lần gọi và thứ tự gọi không phải công cụ chạy nghiệp vụ an toàn.

Nếu phải kiểm tra dữ liệu từ database hoặc một API bên ngoài để xác định quyền, logic đó thường phù hợp với `AuthorizationManager` hoặc service domain có kiểm soát hơn là một `RequestMatcher` thuần path/method.

## 4. OrRequestMatcher: chỉ cần một điều kiện đúng

`OrRequestMatcher` kết hợp theo phép **OR**:

```text
OR(A, B, C) == A || B || C
```

Ví dụ một nhóm gồm cả báo cáo và lịch sử:

```java
RequestMatcher reportOrHistory = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/reports/**"),
    new AntPathRequestMatcher("/api/history/**")
);
```

| Request | Match reports? | Match history? | Kết quả OR |
| --- | --- | --- | --- |
| GET `/api/reports/summary` | Có | Không | **true** |
| GET `/api/history/list` | Không | Có | **true** |
| GET `/api/other` | Không | Không | false |
| GET `/web/history/list` | Không | Không | false |

Khi hai hoặc nhiều nhóm URL có cùng policy authorization, `OrRequestMatcher` có thể gom chúng thành một matcher thay vì lặp code ở nhiều nơi.

### 4.1. OR càng rộng càng cần review kỹ

Giả sử đang bảo vệ một khu vực đọc báo cáo, ta vô tình viết:

```java
RequestMatcher tooBroad = new OrRequestMatcher(
    new AntPathRequestMatcher("/api/reports/**"),
    new AntPathRequestMatcher("/**")
);
```

Vì `/**` quá rộng, phần lớn request khớp kể cả request không thuộc reports. Nếu sử dụng `tooBroad` cùng `permitAll()`, ứng dụng có thể mở quyền truy cập ngoài ý định.

**Quy tắc review:** kiểm tra từng nhánh OR riêng, đặc biệt wildcard, prefix rộng, những trường hợp encoded path hoặc path có dấu phân cách khác thường.

### 4.2. OR không thay thế quy tắc thứ tự URL

Trong `authorizeHttpRequests`, một matcher OR có thể khớp nhiều URL, nhưng rule được chọn vẫn là rule **đầu tiên** khớp theo danh sách. Nếu rule public quá rộng nằm trước rule internal, cấu hình có thể vô tình cho phép internal route.

## 5. NegatedRequestMatcher: phủ định một điều kiện

`NegatedRequestMatcher` nhận một `RequestMatcher` và đảo kết quả:

```text
NOT(A) == !A
```

Ví dụ:

```java
RequestMatcher notInternalReports =
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    );
```

Kết quả:

- GET `/api/reports/summary` → true.
- GET `/api/reports/internal/plan` → false.
- GET `/api/other` → **true**.
- GET `/web/home` → **true**.

Hai trường hợp cuối là điều thường bị bỏ qua. **Phủ định một nhánh path không có nghĩa tự giới hạn về phần còn lại của cùng nhánh.** “Không thuộc internal reports” có thể bao gồm cả website, API khác và URL ngoài phạm vi dự kiến.

### 5.1. Cách phủ định an toàn hơn: kết hợp với phạm vi dương

Thay vì:

```java
// NGUY HIỂM nếu dùng làm matcher permitAll mà thiếu positive scope:
RequestMatcher notInternal =
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    );
```

Hãy xác định vùng cho phép trước rồi mới loại trừ:

```java
RequestMatcher readReportsExceptInternal = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new AntPathRequestMatcher("/api/reports/**"),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    )
);
```

Khi đó một GET `/api/other` **không** được cho qua vì không thuộc positive reports scope, dù thỏa điều kiện NOT internal.

### 5.2. Phủ định không trao quyền cao hơn

`NOT(internalPath)` không phải `hasRole("READER")`. Nó chỉ xác định request không thuộc internal path; authorization vẫn phải gắn yêu cầu role, authentication hoặc policy tương ứng.

Đối với application có nhiều tenant, một matcher `NOT(/admin/**)` không thể thay kiểm tra user có quyền truy cập tài nguyên theo owner/tenant trong service.

## 6. Ghép ba loại matcher: GET AND (reports OR history) AND NOT internal

Đây là case trung tâm của bài:

- Phương thức phải là GET.
- URL nằm trong `/api/reports/**` **hoặc** `/api/history/**`.
- URL không nằm trong `/api/reports/internal/**`.
- Rule cho khu vực internal tách riêng, ưu tiên trước rule đọc chung.

Biểu thức:

```text
READ_ALLOWED_PATH(request) =
    isGetApi(request)
    AND (
        inReports(request)
        OR inHistory(request)
    )
    AND NOT inInternalReports(request)
```

Cấu hình matcher:

```java
RequestMatcher readArea = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new OrRequestMatcher(
        new AntPathRequestMatcher("/api/reports/**"),
        new AntPathRequestMatcher("/api/history/**")
    ),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/reports/internal/**")
    )
);
```

### 6.1. Bảng test logic không phụ thuộc user

| HTTP request | GET /api/** | Reports OR history | NOT internal | Composite |
| --- | --- | --- | --- | --- |
| GET `/api/reports/summary` | true | true | true | **true** |
| GET `/api/history/list` | true | true | true | **true** |
| POST `/api/reports/summary` | false | true | true | false |
| GET `/api/reports/internal/plan` | true | true | false | false |
| GET `/api/other` | true | false | true | false |
| GET `/web/reports/summary` | false | false | true | false |

Lưu ý kết quả composite **không hỏi user nào đang request**. Một request có matcher true vẫn phải đi qua authorization rule, ví dụ `hasAnyRole("READER", "ADMIN")`.

### 6.2. Suy luận bằng luật De Morgan

Các đồng nhất thức giúp review biểu thức phức tạp:

```text
NOT (A OR B) == (NOT A) AND (NOT B)
NOT (A AND B) == (NOT A) OR (NOT B)
```

Ví dụ “không thuộc reports hoặc history” là `NOT(OR(reports,history))`. Nó tương đương `AND(NOT(reports), NOT(history))`, **không** phải `OR(NOT(reports), NOT(history))`.

Một lỗi dùng sai De Morgan có thể làm rule khớp cả những đường dẫn cần loại trừ. Test trên ma trận true/false là cách phát hiện dễ hơn nhìn biểu thức bằng mắt.

### 6.3. Quy tắc đơn giản hóa và đặt tên

Thay vì nested class khó đọc ngay trong `authorizeHttpRequests`, đặt tên có ý nghĩa:

- `apiGet`;
- `reportOrHistory`;
- `notInternal`;
- `readArea`.

Tên biến nên phản ánh **các điều kiện request**, không tuyên bố “user được phép”. Ví dụ `readArea` vẫn phải gắn role policy, không nên đặt tên `authorizedReader` nếu biến chỉ có type RequestMatcher.

## 7. Kết hợp với authorizeHttpRequests: matcher khác authorization

Spring Security 6 dùng `authorizeHttpRequests` để cấu hình authorization rules cho HTTP request. Cơ chế khái niệm:

```text
HTTP request
     |
     v
FilterChainProxy chọn SecurityFilterChain
     |
     v
Authentication filters / SecurityContext
     |
     v
AuthorizationFilter
     |
     +-- duyệt các rule đã đăng ký theo thứ tự
     +-- tìm request matcher đầu tiên trả true
     +-- chạy AuthorizationManager của rule đó
     |
     +-- granted -> request tiếp tục
     +-- denied -> exception handling/entry point
```

Một rule có hai phần khác nhau:

```java
.requestMatchers(readArea).hasAnyRole("READER", "ADMIN")
```

- `requestMatchers(readArea)` quyết định **request có thuộc khu vực này không**.
- `hasAnyRole(...)` quyết định **Authentication hiện tại có quyền vào khu vực đó không**.

Vì vậy phân biệt:

| Công cụ | Câu hỏi mà nó trả lời |
| --- | --- |
| `AndRequestMatcher`/`OrRequestMatcher`/`NegatedRequestMatcher` | Request này có thỏa các điều kiện HTTP hay không? |
| `hasRole`/`hasAuthority`/`authenticated` | Danh tính hiện tại có đáp ứng policy authorization không? |
| `AuthenticationProvider`/`PasswordEncoder` | Cách chứng minh danh tính/password có hợp lệ? |
| Controller/service ownership check | User có quyền thao tác **bản ghi cụ thể** đó không? |

**Không nhầm match với grant.** Nếu bật `.permitAll()` cho một composite matcher rộng, mọi request khớp sẽ được phép qua HTTP authorization rule đó, bất kể user, trừ khi có cơ chế bảo vệ khác.

### 7.1. Thứ tự rule đầu tiên phù hợp

Ví dụ:

```java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(new AntPathRequestMatcher("/api/reports/internal/**"))
        .hasRole("ADMIN")
    .requestMatchers(readArea)
        .hasAnyRole("READER", "ADMIN")
    .anyRequest().denyAll()
);
```

Đây là mảnh cấu hình với biến `readArea` có sẵn. Internal nằm trước rule đọc chung để biểu thị rõ quyền cao hơn. Dù composite đã loại internal bằng NOT, thứ tự này thể hiện chính sách dễ review và tránh sự phụ thuộc mong manh vào một matcher duy nhất.

Nếu đảo thành một rule chung rộng hơn **không có NOT** ở phía trên rule internal, request internal có thể bị áp policy chung quá sớm. **Hai rule trùng URL không tự kết hợp bằng AND**; rule đầu tiên khớp được chọn.

### 7.2. denyAll fallback

`.anyRequest().denyAll()` giúp route chưa định nghĩa không tự được phép. Với ứng dụng web thực, cần cho phép rõ những URL công khai như static assets, error pages và health endpoint theo yêu cầu. Trong dự án API mẫu, chỉ `GET /api/public/status` được công khai.

## 8. securityMatcher và requestMatchers: hai tầng khác nhau

Cùng dùng kiểu `RequestMatcher`, nhưng ý nghĩa phụ thuộc nơi gắn:

- `http.securityMatcher(...)` xác định **một SecurityFilterChain có xử lý request hay không**.
- `authorizeHttpRequests(...).requestMatchers(...)` xác định **rule authorization nào trong chain đã được chọn**.

Giả sử có hai chain:

```text
@Order(1) API chain:
    securityMatcher("/api/**")
    Basic authentication
    HTTP authorization rules, trong đó có readArea

@Order(2) Web fallback:
    formLogin
    HTML session / other web routes
```

`FilterChainProxy` chọn chain đầu tiên khớp. Khi request `/api/reports/summary` vào API chain, web chain **không tiếp tục chạy sau**. Nếu custom API matcher có NOT quá rộng và API chain ở trước web fallback, có thể chọn sai chain cho URL web.

Ví dụ **nguy hiểm về phạm vi**:

```java
// Không dùng như API chain matcher nếu mục tiêu chỉ bao phủ /api/**:
http.securityMatcher(
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/internal/**")
    )
);
```

Matcher trên khớp hầu hết mọi URL không thuộc `/api/internal/**`, kể cả `/web/home`. Nếu đặt ở chain ưu tiên cao, nó có thể chiếm các request web đáng lẽ dùng form login.

Cách suy luận tốt hơn: dùng positive scope `/api/**` rồi AND với những ngoại lệ thực sự cần thiết, hoặc cấu hình chain API đơn giản `securityMatcher("/api/**")` và đặt authorization matcher phức tạp **bên trong chain**.

## 9. Chọn matcher path và HTTP method: lưu ý thực tế

### 9.1. Pattern khác URI, query và servlet path

Ví dụ pattern `/api/reports/**` là matcher path; query string như `?sort=date` không phải phần path theo ngữ nghĩa phổ biến của `AntPathRequestMatcher`.

Với test đơn thuần:

```text
GET /api/reports/summary?sort=date
path được matcher xem xét: /api/reports/summary
query: sort=date
```

Khi ứng dụng chạy dưới context path như `/myapp`, phải phân biệt `requestURI`, `contextPath`, `servletPath` và `pathInfo` theo implementation. Không tự nối chuỗi `request.getRequestURI()` rồi so thẳng với `"/api/..."` mà bỏ qua context path.

`AntPathRequestMatcher` trong ví dụ sử dụng path theo Servlet API (thường `servletPath + pathInfo`); cần kiểm thử nếu `DispatcherServlet` không map ở `/`, hoặc proxy rewrite path.

### 9.2. AntPathRequestMatcher có tính phiên bản

Ví dụ thực hành dùng Spring Boot 3.3.5 (Spring Security 6.3.x) và `AntPathRequestMatcher` vì cú pháp minh bạch. Ở các phiên bản Spring Security mới hơn, API/khuyến nghị matcher có thể thay đổi. Khi nâng cấp:

- Xem tài liệu chính thức của đúng version.
- Cân nhắc `MvcRequestMatcher` hoặc `PathPatternRequestMatcher` khi phù hợp.
- Kiểm chứng kết quả với contextPath, servletPath, URL encoded, trailing slash và path variables.
- Không chuyển pattern từ Ant sang PathPattern rồi giả định ngữ nghĩa hoàn toàn đồng nhất.

**Bảo mật phụ thuộc vào đường dẫn server thực sự xử lý**, không chỉ vào cách pattern trông giống nhau trong code.

### 9.3. Method matcher là phép match request, không phải CSRF policy

`new AntPathRequestMatcher("/api/**", "GET")` chỉ khớp GET. Nó không tự bật/tắt CSRF và không quyết định POST có được ghi dữ liệu hay không. Với HTTP Basic cho API, browser có thể tự gửi lại credentials trong một số tình huống; chính sách CSRF cho endpoint thay đổi dữ liệu phải được đánh giá theo threat model.

Bài mẫu bên dưới **chỉ khai báo GET endpoints**, giữ nguyên CSRF protection mặc định, không tuyên bố stateless là lý do đủ để tắt CSRF.

### 9.4. Tránh custom matcher làm công việc nguy hiểm

Một RequestMatcher tốt nên **nhanh, xác định, không tác dụng phụ**, chỉ đọc những thuộc tính cần thiết của request.

Không nên:

- Đọc và tiêu thụ request body một lần khiến controller không còn đọc được.
- Gọi database hoặc API bên ngoài cho mọi request để quyết định match path.
- Cấp quyền dựa vào header do client tự cung cấp, chưa được xác thực.
- Dùng regex rất tốn CPU với input do attacker điều khiển mà không có giới hạn.
- Ghi raw Authorization header, cookie hoặc session ID khi debug.
- Tự thay thế logic normalization của Servlet/Spring MVC một cách không nhất quán.

## 10. Ví dụ Spring Boot 3.3.5 + Java 17 chạy được

Ứng dụng mô phỏng một API đọc báo cáo. Chính sách:

1. `GET /api/public/status` cho phép anonymous.
2. `GET /api/reports/internal/**` chỉ cho `ROLE_ADMIN`.
3. `GET /api/reports/**` hoặc `GET /api/history/**`, trừ `/api/reports/internal/**`, cho `ROLE_READER` hoặc `ROLE_ADMIN`.
4. Mọi request khác bị `denyAll`.
5. Xác thực bằng HTTP Basic; dùng user lưu trong bộ nhớ để kiểm thử logic matcher.

### 10.1. Cấu trúc thư mục

```text
request-matcher-composition/
  pom.xml
  src/
    main/java/example/matcher/
      MatcherApplication.java
      SecurityConfig.java
      ApiController.java
    test/java/example/matcher/
      MatcherIntegrationTest.java
```

### 10.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>request-matcher-composition</artifactId>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

### 10.3. Lớp khởi động

File `src/main/java/example/matcher/MatcherApplication.java`:

```java
package example.matcher;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MatcherApplication {
    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }
}
```

### 10.4. SecurityConfig.java: AND, OR, NOT trong HTTP authorization

File `src/main/java/example/matcher/SecurityConfig.java`:

```java
package example.matcher;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.security.web.savedrequest.NullRequestCache;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo"))
            .roles("READER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    static RequestMatcher readAreaMatcher() {
        RequestMatcher getApi =
            new AntPathRequestMatcher("/api/**", "GET");

        RequestMatcher reportOrHistory = new OrRequestMatcher(
            new AntPathRequestMatcher("/api/reports/**"),
            new AntPathRequestMatcher("/api/history/**")
        );

        RequestMatcher notInternal = new NegatedRequestMatcher(
            new AntPathRequestMatcher("/api/reports/internal/**")
        );

        return new AndRequestMatcher(
            getApi, reportOrHistory, notInternal
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    new AntPathRequestMatcher("/api/public/status", "GET")
                ).permitAll()
                .requestMatchers(
                    new AntPathRequestMatcher("/api/reports/internal/**")
                ).hasRole("ADMIN")
                .requestMatchers(readAreaMatcher())
                    .hasAnyRole("READER", "ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache()));

        // Dữ liệu demo chỉ có GET; giữ CSRF mặc định.
        return http.build();
    }
}
```

Điểm đáng chú ý:

- `readAreaMatcher()` tạo một **matcher tổ hợp**; bản thân nó không biết user là reader hay admin.
- `new OrRequestMatcher(...)` cho phép reports hoặc history.
- `new NegatedRequestMatcher(...)` loại internal reports khỏi nhánh đọc chung.
- `new AndRequestMatcher(...)` yêu cầu đồng thời phương thức GET, thuộc vùng reports/history và không internal.
- Rule internal đặt trước rule đọc chung và yêu cầu `ROLE_ADMIN`.
- `hasAnyRole("READER", "ADMIN")` là authorization check, không phải một phần của RequestMatcher.
- `anyRequest().denyAll()` bảo vệ theo hướng **deny by default**. Route mới phải được khai báo rule rõ ràng.
- `STATELESS` và `NullSecurityContextRepository` thể hiện HTTP Basic request không dựa vào session login từ trước; mỗi request gửi credentials khi cần.
- `NullRequestCache` bỏ lưu saved URL phục vụ HTML redirect. API chưa xác thực trả Basic challenge (401), không dùng form login.
- Chính sách CSRF cho endpoint ghi dữ liệu chưa được bài này thiết kế; không sao chép cấu hình API GET thuần thành ví dụ production POST mà không đánh giá.

### 10.5. Controller định nghĩa các endpoint kiểm thử

File `src/main/java/example/matcher/ApiController.java`:

```java
package example.matcher;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/api/public/status")
    String status() {
        return "status:ok";
    }

    @GetMapping("/api/reports/summary")
    String summary(Authentication authentication) {
        return "reports:" + authentication.getName();
    }

    @GetMapping("/api/history/list")
    String history(Authentication authentication) {
        return "history:" + authentication.getName();
    }

    @GetMapping("/api/reports/internal/plan")
    String internal(Authentication authentication) {
        return "internal:" + authentication.getName();
    }
}
```

Controller không tự quyết định quyền bằng cách kiểm tra `if (path.startsWith(...))`. HTTP authorization đã diễn ra trước khi controller nhận request. Trong ứng dụng thật, khi controller tra cứu báo cáo theo ID, phải bổ sung quyền sở hữu/tenant ở service.

### 10.6. MockMvc integration tests

File `src/test/java/example/matcher/MatcherIntegrationTest.java`:

```java
package example.matcher;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.security.web.util.matcher.RequestMatcher;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
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
class MatcherIntegrationTest {

    @Autowired
    MockMvc mvc;

    private MockHttpServletRequest request(String method, String path) {
        MockHttpServletRequest request =
            new MockHttpServletRequest(method, path);

        // AntPathRequestMatcher dùng Servlet path/pathInfo để match.
        request.setServletPath(path);
        return request;
    }

    @Test
    void andRequiresAllConditions() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));

        assertFalse(matcher.matches(
            request("POST", "/api/reports/summary")));

        assertFalse(matcher.matches(
            request("GET", "/api/other")));
    }

    @Test
    void orMatchesEitherArea() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));

        assertTrue(matcher.matches(
            request("GET", "/api/history/list")));
    }

    @Test
    void negationExcludesInternalReports() {
        RequestMatcher matcher = SecurityConfig.readAreaMatcher();

        assertFalse(matcher.matches(
            request("GET", "/api/reports/internal/plan")));

        assertTrue(matcher.matches(
            request("GET", "/api/reports/summary")));
    }

    @Test
    void notAloneWouldBeTooBroad() {
        RequestMatcher notInternal =
            new org.springframework.security.web.util.matcher
                .NegatedRequestMatcher(
                    new org.springframework.security.web.util.matcher
                        .AntPathRequestMatcher(
                            "/api/reports/internal/**")
                );

        // Phủ định một URL cụ thể vẫn khớp path ngoài API.
        assertTrue(notInternal.matches(
            request("GET", "/web/home")));

        // Nhưng AND với positive path scope không khớp ngoài API.
        assertFalse(SecurityConfig.readAreaMatcher().matches(
            request("GET", "/web/home")));
    }

    @Test
    void queryStringDoesNotChangePathMatch() {
        MockHttpServletRequest request =
            request("GET", "/api/reports/summary");
        request.setQueryString("sort=date");

        assertTrue(SecurityConfig.readAreaMatcher().matches(request));
    }

    @Test
    void anonymousCanReadPublicStatus() throws Exception {
        mvc.perform(get("/api/public/status"))
            .andExpect(status().isOk())
            .andExpect(content().string("status:ok"));
    }

    @Test
    void anonymousReportGetsBasicChallenge() throws Exception {
        MvcResult response = mvc.perform(
                get("/api/reports/summary"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        String challenge = response.getResponse()
            .getHeader("WWW-Authenticate");
        assertNotNull(challenge);
        assertTrue(challenge.startsWith("Basic"));
    }

    @Test
    void readerCanReadReportsAndHistory() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("reports:reader"));

        mvc.perform(get("/api/history/list")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("history:reader"));
    }

    @Test
    void wrongPasswordIsAuthenticationFailure() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("reader", "wrong-demo")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readerCannotOpenInternalPlan() throws Exception {
        mvc.perform(get("/api/reports/internal/plan")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanOpenInternalPlan() throws Exception {
        mvc.perform(get("/api/reports/internal/plan")
                .with(httpBasic("admin", "admin-demo")))
            .andExpect(status().isOk())
            .andExpect(content().string("internal:admin"));
    }

    @Test
    void unknownPathIsDeniedEvenForAuthenticatedReader()
            throws Exception {
        mvc.perform(get("/api/other")
                .with(httpBasic("reader", "reader-demo")))
            .andExpect(status().isForbidden());
    }
}
```

Các test có hai tầng rõ ràng:

1. **Kiểm thử boolean của RequestMatcher** với `MockHttpServletRequest`: path và method; OR cho reports/history, NOT loại internal, positive scope ngăn NOT mở quá rộng.
2. **Integration test HTTP** với `MockMvc` qua Spring Security filter chain: 200 cho route public/đúng role, 401 cho thiếu/sai Basic credentials, 403 cho authenticated reader thiếu quyền hoặc request nằm ngoài rule.

Sử dụng `httpBasic("reader", "...")` để thực sự gửi header Basic, thay vì `.with(user("reader"))` có thể tạo principal giả và bỏ qua bước xác minh password.

**Các test không chạy tải hoặc kiểm chứng hiệu năng** của matcher. Nếu cần đánh giá performance, phải đo trên môi trường phù hợp và tránh matcher có logic truy cập tài nguyên bên ngoài.

### 10.7. Chạy Maven và quan sát kết quả

Với JDK 17+ và Maven, tại thư mục `request-matcher-composition`:

```bash
mvn test
mvn spring-boot:run
```

Nếu dependencies và môi trường khớp, **12 bài kiểm thử dự kiến pass**. Đây là dự kiến từ mã nguồn; không phải kết quả Maven đã được chạy thực tế. Log test/build không có một stdout cố định.

Có thể thử bằng `curl` trên **localhost demo**:

```bash
curl -i http://localhost:8080/api/public/status
curl -i http://localhost:8080/api/reports/summary
curl -i -u reader:reader-demo http://localhost:8080/api/reports/summary
curl -i -u reader:reader-demo http://localhost:8080/api/history/list
curl -i -u reader:reader-demo http://localhost:8080/api/reports/internal/plan
curl -i -u admin:admin-demo http://localhost:8080/api/reports/internal/plan
curl -i -u reader:reader-demo http://localhost:8080/api/other
```

**Không sử dụng HTTP không mã hóa với credentials thật.** Lệnh `curl -u` chứa password trong command line có thể lộ qua shell history/process listing; chỉ dùng password minh họa trên máy học tập.

Bảng kết quả dự kiến:

| Request | Kết quả | Lý do |
| --- | --- | --- |
| GET `/api/public/status` anonymous | 200 `status:ok` | Rule công khai |
| GET `/api/reports/summary` anonymous | 401 + Basic challenge | Composite match, nhưng thiếu authentication |
| GET `/api/reports/summary` reader Basic | 200 `reports:reader` | AND/OR/NOT match và `ROLE_READER` |
| GET `/api/history/list` reader Basic | 200 `history:reader` | Nhánh OR thứ hai match |
| GET `/api/reports/internal/plan` reader Basic | 403 | Rule internal chỉ cho admin |
| GET `/api/reports/internal/plan` admin Basic | 200 `internal:admin` | Rule internal và role đúng |
| GET `/api/other` reader Basic | 403 | Không match rule cụ thể, `denyAll` |
| GET `/api/reports/summary` Basic password sai | 401 | Authentication bị từ chối trước quyền truy cập |

## 11. Java 17 độc lập: tự viết mô hình AND, OR, NOT

Để nhìn thấy bảng chân trị mà không cần Spring Boot hoặc Maven, ta có thể tạo một chương trình Java 17 thuần. Nó minh họa boolean composition, **không thay thế** `RequestMatcher` hay ngữ nghĩa Servlet path của Spring Security.

Tạo file `CompositeMatcherLogicDemo.java`:

```java
public class CompositeMatcherLogicDemo {

    @FunctionalInterface
    interface Match {
        boolean matches(String method, String path);
    }

    static Match and(Match... conditions) {
        return (method, path) -> {
            for (Match condition : conditions) {
                if (!condition.matches(method, path)) {
                    return false;
                }
            }
            return true;
        };
    }

    static Match or(Match... conditions) {
        return (method, path) -> {
            for (Match condition : conditions) {
                if (condition.matches(method, path)) {
                    return true;
                }
            }
            return false;
        };
    }

    static Match not(Match condition) {
        return (method, path) ->
            !condition.matches(method, path);
    }

    static boolean inside(String path, String root) {
        return path.equals(root) || path.startsWith(root + "/");
    }

    public static void main(String[] args) {
        Match get = (method, path) -> "GET".equals(method);
        Match api = (method, path) -> inside(path, "/api");
        Match reports = (method, path) ->
            inside(path, "/api/reports");
        Match history = (method, path) ->
            inside(path, "/api/history");
        Match internal = (method, path) ->
            inside(path, "/api/reports/internal");

        Match readArea = and(get, api,
            or(reports, history), not(internal));

        String[][] cases = {
            {"GET", "/api/reports/summary"},
            {"GET", "/api/history/list"},
            {"POST", "/api/reports/summary"},
            {"GET", "/api/reports/internal/plan"},
            {"GET", "/api/other"},
            {"GET", "/web/home"}
        };

        for (String[] sample : cases) {
            System.out.printf("%s %s -> %b%n",
                sample[0], sample[1],
                readArea.matches(sample[0], sample[1]));
        }
    }
}
```

Biên dịch và chạy:

```bash
javac CompositeMatcherLogicDemo.java
java CompositeMatcherLogicDemo
```

Stdout **chính xác** với Java 17:

```text
GET /api/reports/summary -> true
GET /api/history/list -> true
POST /api/reports/summary -> false
GET /api/reports/internal/plan -> false
GET /api/other -> false
GET /web/home -> false
```

Chương trình này cố tình đơn giản hóa request thành hai chuỗi `method` và `path`. Nó không hiểu servlet context path, URL decoding, proxy rewriting, HTTP headers, PathPattern hay session. Phần Maven/MockMvc ở trên mới kiểm tra `RequestMatcher` thực sự của Spring Security Servlet.

## 12. Một số thiết kế hữu ích khác

### 12.1. Public GET cho nhiều path, loại trừ nội bộ

Giả sử ứng dụng cho phép anonymous GET các endpoint công khai dưới `/api/public/**` và `/api/docs/**`, nhưng không cho phép `/api/docs/internal/**`. Có thể dùng:

```java
RequestMatcher publicGet = new AndRequestMatcher(
    new AntPathRequestMatcher("/api/**", "GET"),
    new OrRequestMatcher(
        new AntPathRequestMatcher("/api/public/**"),
        new AntPathRequestMatcher("/api/docs/**")
    ),
    new NegatedRequestMatcher(
        new AntPathRequestMatcher("/api/docs/internal/**")
    )
);
```

Khi đăng ký:

```java
// Minh họa trong authorizeHttpRequests, không phải chương trình độc lập:
.requestMatchers(publicGet).permitAll()
```

Đây là trường hợp **nhạy cảm**, vì `permitAll` bỏ yêu cầu đăng nhập đối với tất cả request khớp. Cần test trực tiếp cả `/api/docs/internal/secret`, `/api/other` và mọi method state-changing. Đừng đặt một OR chứa `/**`.

### 12.2. Chọn chuỗi filter riêng cho một vùng API

Giả sử muốn có chain riêng cho API GET reports/history, còn API khác nằm ở fallback. Khi dùng composite trong `securityMatcher`, phải phân tích:

- Request POST vào cùng URL có đi chain nào khác và có bị bảo vệ không?
- Có chain fallback phù hợp cho `/api/reports/internal/**`?
- `/api/reports/internal/**` bị loại khỏi chain hiện tại sẽ đi đâu?
- URL không match chain nào có bị bỏ qua bảo vệ bởi Spring Security không?
- Form login/HTTP Basic/CSRF và entry point của chain được chọn có đúng trải nghiệm không?

Nếu phân quyền chỉ khác trong cùng API, **thường đơn giản hơn** là giữ một API chain `securityMatcher("/api/**")` và dùng composite matcher ở `authorizeHttpRequests` như bài mẫu. Chỉ chia nhiều chain khi authentication/session/entry point/filter composition thực sự khác nhau.

### 12.3. Matcher theo method không phải chính sách write-safe

Ví dụ matcher chỉ GET có thể tránh vô tình dùng rule đọc chung cho POST, nhưng không bảo đảm toàn bộ thao tác write-safe. Các endpoint state-changing cần method đúng, authentication, authorization, CSRF protection khi phù hợp, input validation, ownership và idempotency/transaction theo yêu cầu.

Một rule `POST /api/reports/**` có thể dùng matcher method riêng và `hasRole("EDITOR")`, nhưng phải xem cả tính hợp lệ của nguồn xác thực và việc ghi dữ liệu thật ở service.

## 13. Bảo mật và review matcher expression

### 13.1. Checklist chống lỗi mở phạm vi

- Mọi `NegatedRequestMatcher` dùng trong `permitAll` hoặc chain matcher có **positive scope** đủ hẹp chưa?
- Mỗi nhánh `OrRequestMatcher` có wildcard quá rộng không?
- Một matcher cho GET có vô tình áp sang POST/PUT/DELETE không?
- Một URL internal có rơi vào rule public rộng hơn do thứ tự matcher không?
- Đã có fallback `denyAll`/`authenticated` phù hợp và đầy đủ chain coverage chưa?
- Nếu có nhiều security chains, chain nào được `FilterChainProxy` chọn trước?
- Query, path encoding, trailing slash, context path và servlet path có được test không?
- Các URL static/health/error cần public có bị chặn ngoài ý định không?
- Khi bật `permitAll`, có phân biệt rõ “không cần Authentication” với “không đi qua security filters” không?

### 13.2. Path authorization không thay thế object-level authorization

Giả sử `GET /api/reports/812` khớp readArea và user mang `ROLE_READER`. Họ có chắc được xem báo cáo 812 không? **Không**: có thể báo cáo thuộc tenant khác.

Cần kiểm tra quyền trên resource cụ thể ở tầng nghiệp vụ, ví dụ service lấy báo cáo theo owner/tenant và kiểm tra user. Chỉ bảo vệ `/api/reports/**` ở HTTP level không giải quyết IDOR/BOLA.

### 13.3. Hành vi matcher khi request kỳ lạ

Các URL encoded, double-slash, semicolon/matrix parameters, case sensitivity và normalization qua proxy/container có thể tạo khác biệt giữa đường dẫn matcher thấy và route handler xử lý. Không nên tự viết matcher trên raw URI bằng `startsWith` mà thiếu canonicalization và path-segment boundary checks.

Với Spring MVC, nên chọn và test matcher tương thích framework routing. Một số cấu hình firewall của Spring Security có thể chặn request nguy hiểm trước khi matcher chạy; không dựa riêng vào một ví dụ dev để khẳng định mọi đường dẫn encoded được xử lý giống nhau ở production.

### 13.4. Observability không lộ secret

Có thể bật log debug trong môi trường phát triển:

```properties
logging.level.org.springframework.security=DEBUG
```

Để biết vì sao request không vào controller, quan sát security chain, rule match, authentication state và response status. Không log raw cookie, password, Authorization header, session ID hoặc access token. Một matcher “không đúng” có thể do request đang đi chain khác, không phải do boolean AND/OR/NOT sai.

## 14. Lỗi phổ biến và cách sửa

| Sai lầm | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Dùng `NegatedRequestMatcher(internal)` trực tiếp cùng `permitAll` | Cho phép cả đường dẫn ngoài vùng dự kiến | AND với positive scope rõ ràng |
| Dùng OR thay vì AND giữa path và method | GET ngoài path hoặc POST trong path có thể khớp | Dùng AND(method, scope) |
| Nhầm `NOT(A OR B)` với `NOT A OR NOT B` | Logic loại trừ sai theo De Morgan | Dùng NOT(OR(...)) hoặc AND(NOT A, NOT B) |
| Đặt `/**` trong nhánh OR | Composite matcher quá rộng | Review wildcard, dùng path cụ thể |
| Đặt rule chung `permitAll` trước internal rule | Internal có thể được public hóa | Đặt matcher chuyên biệt trước, test rule order |
| Đặt `anyRequest` trước rule cụ thể | Rule phía sau có thể không hoạt động hoặc config lỗi | Fallback ở cuối |
| Nghĩ matcher true nghĩa user có quyền | Bỏ qua Authentication/authority | Ghép với `AuthorizationManager` thích hợp |
| Dùng header `X-Role` do client gắn để xác minh admin | Client có thể tự giả mạo quyền | Dùng Authentication nguồn đáng tin |
| Dùng `startsWith("/api/report")` tự viết | `/api/report-evil` cũng có thể match | Dùng matcher path-aware phù hợp |
| Match raw requestURI mà quên context path | Sai match khi deploy ở subpath | Dùng Servlet-aware matcher, test context/servlet paths |
| Nghĩ query luôn là phần của Ant path pattern | Test sai ngữ nghĩa | Phân biệt query và path |
| Ghép matcher nhưng không test HTTP status | Có thể xác thực/entry point khác dự kiến | Test cả `matches` và MockMvc |
| Test chỉ user admin | Không phát hiện reader bị mở internal | Test anonymous/reader/admin |
| Đổi matcher implementation khi upgrade mà không test | Khác semantics trailing slash/encoded path | Pin version, integration test boundary |
| Dùng matcher có side effects | Hành vi khó dự đoán, lỗi body/DB | Matcher thuần điều kiện request |
| Dùng composite matcher làm `securityMatcher` quá rộng | API chain “nuốt” web requests | Giới hạn chain bằng positive API scope |
| Nghĩ stateless + HTTP Basic luôn không cần CSRF | Browser có thể tự gửi Basic credential | Đánh giá CSRF theo client và threat model |
| Không có fallback chain/rule | URL có thể không được bảo vệ hoặc sai quyền | Thiết kế chain coverage, fallback phù hợp |
| Matcher path bảo vệ đủ ID của resource | IDOR/BOLA có thể xảy ra | Thêm authorization theo owner/tenant |
| Logging raw request Authorization để debug matcher | Lộ credential | Chỉ log path/trace/decision an toàn |

## 15. Quy trình debug một request bị match sai

1. **Xác nhận URL, method thực tế**, không chỉ đường dẫn được developer dự đoán. Browser có thể gửi `HEAD`/`OPTIONS` hoặc redirect khác.
2. **Xác nhận SecurityFilterChain**: `securityMatcher`, `@Order`, chain fallback và authentication mechanism.
3. **Đọc từng matcher thành phần**: GET? reports? history? internal? Ghi kết quả boolean vào test có kiểm soát.
4. **Kiểm tra AND/OR/NOT đúng dấu ngoặc**. `AND(GET, OR(A,B), NOT(C))` khác `OR(AND(GET,A),B,NOT(C))`.
5. **Phân biệt matcher false và authorization denied**. Matcher false có thể khiến rule sau áp dụng; matcher true vẫn có thể 401/403 nếu thiếu credentials/role.
6. **Kiểm tra thứ tự requestMatchers** trong `authorizeHttpRequests`; rule đầu tiên phù hợp được dùng.
7. **Kiểm tra path API vs servlet path**, context path, proxy rewrite và encoding.
8. **Kiểm tra wildcard thật sự match gì**, nhất là `/**`, `/api/**` và nested paths.
9. **Kiểm tra scheme authentication**: Basic 401, form login 302 hoặc custom JSON 401 không phải do matcher một mình quyết định.
10. **Kiểm tra CSRF trên POST**, đừng nhầm HTTP 403 do CSRF với matcher/role denial.
11. **Kiểm tra quyền trên resource ID** ở service dù HTTP rule granted.
12. **Kiểm tra các test regression** cho URL internal, unknown, method khác, anonymous và user authority thấp.
13. **So sánh version framework** nếu behavior đổi sau upgrade matcher.
14. **Không lộ raw credential** trong logs khi điều tra.

## 16. Bài tập tự kiểm tra

**Câu 1.** `AND(GET, reports)` có match `POST /api/reports/summary` không?

**Đáp án:** Không. Path đúng nhưng method khác GET, nên AND false.

**Câu 2.** `OR(reports, history)` có match `GET /api/history/list` không?

**Đáp án:** Có, vì một nhánh OR đúng là đủ.

**Câu 3.** `NOT(internalReports)` có match `GET /web/home` không?

**Đáp án:** Có. `/web/home` không thuộc internalReports nên phủ định true. Đây là lý do phải thêm positive scope để tránh mở quá rộng.

**Câu 4.** Một composite matcher khớp GET reports và user chưa login. Có tự được truy cập dữ liệu không?

**Đáp án:** Không. Matcher chỉ xác định rule; authorization vẫn có thể yêu cầu authenticated/role và trả Basic challenge hoặc form login.

**Câu 5.** Tại sao đặt một rule `/api/**.permitAll()` trước `/api/reports/internal/**.hasRole("ADMIN")` nguy hiểm?

**Đáp án:** Vì first matching rule quyết định authorization; matcher rộng phía trước có thể cho phép internal trước khi rule admin được xét.

**Câu 6.** `NOT(A OR B)` và `OR(NOT A, NOT B)` có tương đương không?

**Đáp án:** Không. `NOT(A OR B)` tương đương `AND(NOT A, NOT B)` theo De Morgan.

**Câu 7.** Khi triển khai ở context path `/app`, có nên tự so `getRequestURI().startsWith("/api/")` không?

**Đáp án:** Không nên dựa vào đó nếu chưa xử lý context path. Dùng matcher phù hợp Servlet/MVC và test đầy đủ môi trường.

**Câu 8.** Hai bean SecurityFilterChain đều match request, chain nào chạy?

**Đáp án:** `FilterChainProxy` chọn chain đầu tiên khớp theo thứ tự cấu hình. Không chạy mọi chain nối tiếp để ghép quyền.

**Câu 9.** Matcher true cho `/api/reports/812` và user có `ROLE_READER`. User có tự được phép xem báo cáo của tenant khác không?

**Đáp án:** Không. Cần object-level authorization ở service/ownership/tenant, không chỉ path và role.

**Câu 10.** Nếu muốn cho anonymous GET trong `/api/public/**` trừ `/api/public/internal/**`, nên viết gì?

**Đáp án:** Một `AndRequestMatcher` chứa GET matcher, positive public path matcher và `NegatedRequestMatcher` cho internal. Sau đó gắn `permitAll` nếu policy thật sự cho công khai, đặt các rule nhạy cảm ở vị trí phù hợp và test boundary.

## 17. Ghi nhớ cốt lõi

- `AndRequestMatcher` là **AND**: mọi điều kiện cần đúng.
- `OrRequestMatcher` là **OR**: ít nhất một điều kiện đúng.
- `NegatedRequestMatcher` là **NOT**: đảo kết quả một matcher.
- Một phủ định đơn lẻ rất dễ **khớp rộng ngoài phạm vi**, nên ghép với positive path/method scope.
- Các matcher ghép bằng boolean chỉ trả lời “**request có thuộc nhóm này?**”; `authorizeHttpRequests` và `AuthorizationManager` trả lời “**người dùng có quyền?**”.
- Rule HTTP dùng **matcher đầu tiên phù hợp**; khi có nhiều security chains, `securityMatcher` xác định chain và `requestMatchers` xác định rule trong chain đó.
- Đừng quên method, query-vs-path, servlet context path, version matcher, URL normalization và quyền object-level.
- Kiểm thử trực tiếp `matches` với request Servlet và kiểm thử cả phản hồi **200/401/403** qua `MockMvc` để bắt lỗi ghép AND/OR/NOT, thứ tự rule và authority.
