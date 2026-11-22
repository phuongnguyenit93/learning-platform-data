# AndRequestMatcher, OrRequestMatcher và NegatedRequestMatcher trong Spring Security

> **Chủ đề:** Spring Security — RequestMatcher. Bài này hướng dẫn cách **ghép nhiều điều kiện nhận diện HTTP request** bằng AND, OR, NOT; đọc đúng ý nghĩa của các biểu thức ghép; đưa chúng vào `authorizeHttpRequests` và `securityMatcher`; đồng thời kiểm thử những trường hợp giao nhau, bị loại trừ và mặc định từ chối. Ví dụ dùng Java 17+, Spring Boot 3.5.x và Spring Security 6.5.x theo mô hình Servlet.

## 1. RequestMatcher trả lời câu hỏi gì?

`org.springframework.security.web.util.matcher.RequestMatcher` là một giao diện dùng để kiểm tra một `HttpServletRequest` có thỏa **điều kiện nhận diện** hay không.

~~~java
@FunctionalInterface
public interface RequestMatcher {
    boolean matches(HttpServletRequest request);
    // Các phiên bản hiện đại còn có phương thức mặc định matcher(request)
    // để trả MatchResult, có thể chứa path variables.
}
~~~

Đây là **mã khái niệm rút gọn** nhằm giải thích hợp đồng; không chép nó vào project vì Spring Security đã cung cấp interface. Phần kiểm tra quan trọng là `matches(request)` trả `true` hoặc `false`.

Ví dụ về điều kiện nhận diện:

- Đường dẫn thuộc `/api/docs/**`.
- HTTP method là `GET`.
- Header nhất định tồn tại; query parameter được cung cấp theo định dạng yêu cầu.
- Request thuộc một dispatcher type cụ thể.
- Đường dẫn là **một trong hai** endpoint báo cáo.
- Request là **GET tài liệu nhưng không phải tài liệu private**.

**Tuy nhiên:** matcher trả `true` chỉ có nghĩa **request thuộc nhóm mà rule này điều chỉnh**, **không phải** “người dùng được cấp quyền”. Quyền thực sự nằm ở `AuthorizationManager` gắn với matcher đó, ví dụ `hasAuthority("docs:read")`, `authenticated()` hoặc `denyAll()`.

### Ví dụ: cùng matcher, quyết định quyền khác nhau

~~~java
// Fragment trong authorizeHttpRequests:
.requestMatchers(docsReadMatcher).hasAuthority("docs:read")
~~~

Ở đây:

1. `docsReadMatcher.matches(request)` xác định đây có phải request đọc tài liệu thường hay không.
2. Chỉ khi matcher phù hợp, rule `hasAuthority("docs:read")` mới kiểm tra `Authentication` của người gọi.
3. User thiếu `docs:read` bị **DENY**, kể cả matcher trả `true`.
4. Nếu matcher trả `false`, Spring Security thử **rule HTTP tiếp theo** trong danh sách, không phải tự động cấp quyền.

Phân biệt hai câu hỏi:

- **Request matching:** “Đây là loại request nào?”
- **Authorization:** “Danh tính hiện tại có được thực hiện request loại này trên tài nguyên đó không?”

## 2. Ba bộ ghép và ý nghĩa Boolean

Spring Security cung cấp:

| Class | Biểu thức logic | `matches(request)` trả `true` khi... |
| --- | --- | --- |
| `AndRequestMatcher` | `A ∧ B` | **Mọi** matcher con đều khớp |
| `OrRequestMatcher` | `A ∨ B` | **Ít nhất một** matcher con khớp |
| `NegatedRequestMatcher` | `¬A` | Matcher được bọc **không** khớp |

Tên import:

~~~java
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
~~~

Hai matcher AND/OR có constructor nhận nhiều `RequestMatcher` qua **varargs** hoặc `List<RequestMatcher>`; NOT nhận **một** `RequestMatcher`. Trong thực tế, nên cung cấp ít nhất các matcher con cần thiết, tránh dùng danh sách rỗng hoặc cấu hình không có chủ ý và rồi dựa vào hành vi biên chưa kiểm chứng.

### Bảng chân trị

| A | B | AND `A ∧ B` | OR `A ∨ B` | NOT `¬A` |
| :---: | :---: | :---: | :---: | :---: |
| false | false | false | false | true |
| false | true | false | true | true |
| true | false | false | true | false |
| true | true | true | true | false |

Các class áp dụng quy tắc logic này cho **cùng một HTTP request**.

**Lưu ý:** `AND` và `OR` ở đây ghép **request matchers**, không ghép “hai authority của user”. Muốn “có `docs:read` **hoặc** `ROLE_ADMIN`”, dùng `hasAnyAuthority`/một `AuthorizationManager` thích hợp; không viết `new OrRequestMatcher(...)` rồi hy vọng tự tạo logic quyền.

## 3. `AndRequestMatcher` — thỏa **đồng thời** nhiều điều kiện

Nghiệp vụ: chỉ nhận diện request **GET thuộc `/api/docs/**`**.

Đặt tên:

- `GET_METHOD`: `request.getMethod().equals("GET")`.
- `DOCS_PATH`: đường dẫn khớp `/api/docs/**`.

Ta cần:

`docsGet = GET_METHOD AND DOCS_PATH`.

Trong Spring Security 6.5, có thể dùng `PathPatternRequestMatcher` để match đường dẫn và một lambda cho method:

~~~java
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

var path = PathPatternRequestMatcher.withDefaults();

RequestMatcher getMethod =
    request -> "GET".equals(request.getMethod());

RequestMatcher docsPath = path.matcher("/api/docs/**");

RequestMatcher docsGet =
    new AndRequestMatcher(getMethod, docsPath);
~~~

Đây là **fragment**, không có `main`; đặt nó trong cấu hình Spring và import những lớp cần thiết. API `PathPatternRequestMatcher` hiện diện từ Spring Security 6.5, nên với project cũ hơn cần chọn matcher được phiên bản đó hỗ trợ thay vì copy nguyên code.

Ví dụ:

| Request | `GET_METHOD` | `DOCS_PATH` | `docsGet` |
| --- | :---: | :---: | :---: |
| `GET /api/docs/42` | true | true | **true** |
| `POST /api/docs/42` | false | true | false |
| `GET /api/reports/42` | true | false | false |
| `POST /api/reports/42` | false | false | false |

Với `new AndRequestMatcher(a, b, c)`, tất cả ba điều kiện phải khớp. Khi chia logic thành nhiều matcher đơn giản, việc kiểm thử thường dễ hơn một matcher khổng lồ đọc method, path, header, query và user trong cùng một hàm.

**Không dùng các matcher để thay thế authorization:** nếu `docsGet` trả true thì vẫn phải xét authority, owner, tenant và các ràng buộc nghiệp vụ liên quan trước khi trả dữ liệu.

## 4. `OrRequestMatcher` — một trong nhiều tình huống được nhận diện

Nghiệp vụ: cả hai đường dẫn báo cáo `/api/reports/summary` và `/api/reports/draft` đều thuộc nhóm **READ_REPORT**. Ta cần:

`reportPath = summaryPath OR draftPath`.

~~~java
var path = PathPatternRequestMatcher.withDefaults();

RequestMatcher reportPath = new OrRequestMatcher(
    path.matcher("/api/reports/summary"),
    path.matcher("/api/reports/draft")
);

RequestMatcher reportGet = new AndRequestMatcher(
    request -> "GET".equals(request.getMethod()),
    reportPath
);
~~~

Kết quả:

| Request | Summary | Draft | OR hai path | GET AND OR |
| --- | :---: | :---: | :---: | :---: |
| `GET /api/reports/summary` | true | false | true | **true** |
| `GET /api/reports/draft` | false | true | true | **true** |
| `GET /api/reports/other` | false | false | false | false |
| `POST /api/reports/summary` | true | false | true | false |

Nhiều endpoint có cùng **chính sách phân quyền** là lý do thực tế để dùng OR. Ở DSL, bạn cũng có thể truyền nhiều đường dẫn trực tiếp cho một rule:

~~~java
// Khi hai endpoint cùng một policy, cách viết ngắn hơn có thể đủ:
.requestMatchers("/api/reports/summary", "/api/reports/draft")
    .hasAuthority("report:read")
~~~

Nhưng nếu cần ghép thêm method, header, dispatcher type hoặc loại trừ một tập path, `OrRequestMatcher` và `AndRequestMatcher` giúp biểu thức rõ ràng hơn.

**Không hiểu nhầm** `OrRequestMatcher(summaryPath, draftPath)` thành phép “quyền A OR quyền B”. Nó chỉ hợp nhất **tập HTTP requests** sẽ được một rule áp dụng.

## 5. `NegatedRequestMatcher` — loại trừ một trường hợp

Nghiệp vụ: đọc tài liệu thông thường cần `docs:read`, nhưng tài liệu dưới `/api/docs/private/**` cần `docs:private:read`. Ta không muốn rule rộng cho tài liệu thường bắt luôn private.

Gọi:

- `DOCS_PATH` = `/api/docs/**`.
- `PRIVATE_PATH` = `/api/docs/private/**`.

Tập tài liệu thường là:

`normalDocs = GET ∧ DOCS_PATH ∧ ¬PRIVATE_PATH`.

~~~java
RequestMatcher get = request -> "GET".equals(request.getMethod());
RequestMatcher allDocs =
    PathPatternRequestMatcher.withDefaults().matcher("/api/docs/**");
RequestMatcher privateDocs =
    PathPatternRequestMatcher.withDefaults()
        .matcher("/api/docs/private/**");

RequestMatcher normalDocsGet = new AndRequestMatcher(
    get,
    allDocs,
    new NegatedRequestMatcher(privateDocs)
);

RequestMatcher privateDocsGet =
    new AndRequestMatcher(get, privateDocs);
~~~

Bảng:

| Request | GET | DOCS_PATH | PRIVATE_PATH | NOT PRIVATE | `normalDocsGet` | `privateDocsGet` |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| `GET /api/docs/42` | T | T | F | T | **T** | F |
| `GET /api/docs/private/99` | T | T | T | F | F | **T** |
| `POST /api/docs/42` | F | T | F | T | F | F |
| `GET /api/reports/summary` | T | F | F | T | F | F |

### Nguy cơ đặc biệt: NOT một mình thường khớp **quá rộng**

~~~java
// Nguy hiểm nếu dùng như một rule công khai:
new NegatedRequestMatcher(privateDocs);
~~~

Biểu thức trên là true với **mọi request không nằm trong vùng private**, bao gồm `/admin/delete`, `/billing/export` và các đường dẫn khác không hề thuộc nhóm tài liệu. Nếu kết hợp với `permitAll()` ở đầu danh sách rule, bạn có thể **công khai gần như cả ứng dụng**.

**Cách an toàn:** giới hạn bằng điều kiện dương trước:

`GET ∧ /api/docs/** ∧ NOT /api/docs/private/**`.

NOT là **phép đảo một điều kiện nhận diện**, không phải “cấm tất cả user thiếu permission”. Để từ chối quyền, dùng `denyAll()`, `hasAuthority(...)` hay policy phù hợp.

## 6. Lồng các matcher, dấu ngoặc và De Morgan

Vì đây là logic Boolean, việc **gom nhóm** cần được đọc rõ ràng. Đặt:

- `G` = request dùng GET.
- `D` = path thuộc `/api/docs/**`.
- `P` = path thuộc `/api/docs/private/**`.
- `S` = path đúng `/api/reports/summary`.
- `R` = path đúng `/api/reports/draft`.

Các biểu thức:

| Ý tưởng | Logic | Cách ghép |
| --- | --- | --- |
| GET tài liệu thường | `G ∧ D ∧ ¬P` | `And(G, D, Negated(P))` |
| GET một trong hai báo cáo | `G ∧ (S ∨ R)` | `And(G, Or(S, R))` |
| GET tài liệu thường **hoặc** GET báo cáo | `(G ∧ D ∧ ¬P) ∨ (G ∧ (S ∨ R))` | `Or(And(G,D,Negated(P)), And(G,Or(S,R)))` |
| Không phải GET tài liệu thường | `¬(G ∧ D ∧ ¬P)` | `Negated(And(G,D,Negated(P)))` |

Dạng Java thể hiện phép ghép sâu:

~~~java
RequestMatcher normalOrReportRead = new OrRequestMatcher(
    new AndRequestMatcher(
        get,
        allDocs,
        new NegatedRequestMatcher(privateDocs)
    ),
    new AndRequestMatcher(
        get,
        new OrRequestMatcher(summaryPath, draftPath)
    )
);
~~~

Đây là **fragment** và giả định các biến `get`, `allDocs`, `privateDocs`, `summaryPath`, `draftPath` đã có. Nếu biểu thức quá sâu, đặt tên các matcher trung gian để dễ đọc và test.

Hai công thức De Morgan:

- `¬(A ∨ B) = ¬A ∧ ¬B`.
- `¬(A ∧ B) = ¬A ∨ ¬B`.

Ví dụ “không thuộc summary **và** không thuộc draft” tương đương “phủ định việc thuộc một trong hai endpoint”. Tuy nhiên, không nên áp dụng một phép NOT quá rộng vào `permitAll` mà thiếu điều kiện ranh giới đường dẫn.

**Không giả định về side effect hay thứ tự gọi** của các matcher con. Dù một implementation có thể ngắt khi kết quả đã rõ, matcher nên là phép kiểm tra **không gây side effect**, không đọc body request để làm thay đổi trạng thái, và không phụ thuộc vào việc matcher khác được gọi trước.

## 7. Java 17 thuần: kiểm tra logic ghép trước khi dùng framework

Chương trình dưới đây mô phỏng AND/OR/NOT bằng `java.util.function.Predicate`, không cần Spring. Nó giúp xác minh các bảng chân trị và ví dụ request. Đây là **mô hình học tập**, không phải mã của `PathPatternRequestMatcher`: chương trình dùng `startsWith` cho path.

Tạo tệp **`MatcherLogicDemo.java`**:

~~~java
import java.util.List;
import java.util.function.Predicate;

public class MatcherLogicDemo {

    record Request(String method, String path) {}

    static void show(
        Request request,
        Predicate<Request> normalDocs,
        Predicate<Request> privateDocs,
        Predicate<Request> reports
    ) {
        System.out.println(
            request.method() + " " + request.path()
                + " => normal=" + normalDocs.test(request)
                + ", private=" + privateDocs.test(request)
                + ", report=" + reports.test(request)
        );
    }

    public static void main(String[] args) {
        Predicate<Request> get =
            request -> "GET".equals(request.method());

        Predicate<Request> docs =
            request -> request.path().startsWith("/api/docs/");

        Predicate<Request> privatePath =
            request -> request.path().startsWith("/api/docs/private/");

        Predicate<Request> summary =
            request -> "/api/reports/summary".equals(request.path());

        Predicate<Request> draft =
            request -> "/api/reports/draft".equals(request.path());

        Predicate<Request> normal = get
            .and(docs)
            .and(privatePath.negate());

        Predicate<Request> privateRead = get.and(privatePath);
        Predicate<Request> reportRead = get.and(summary.or(draft));

        List<Request> requests = List.of(
            new Request("GET", "/api/docs/42"),
            new Request("GET", "/api/docs/private/99"),
            new Request("POST", "/api/docs/42"),
            new Request("GET", "/api/reports/summary"),
            new Request("GET", "/api/reports/draft"),
            new Request("GET", "/api/reports/other")
        );

        for (Request request : requests) {
            show(request, normal, privateRead, reportRead);
        }
    }
}
~~~

Chạy bằng JDK 17+:

~~~bash
javac MatcherLogicDemo.java
java MatcherLogicDemo
~~~

**Stdout chính xác:**

~~~text
GET /api/docs/42 => normal=true, private=false, report=false
GET /api/docs/private/99 => normal=false, private=true, report=false
POST /api/docs/42 => normal=false, private=false, report=false
GET /api/reports/summary => normal=false, private=false, report=true
GET /api/reports/draft => normal=false, private=false, report=true
GET /api/reports/other => normal=false, private=false, report=false
~~~

Ý nghĩa:

1. `normal=true` chỉ xuất hiện khi GET thuộc `/api/docs/**` nhưng không thuộc private.
2. `private=true` chỉ xuất hiện khi GET thuộc private.
3. `report=true` chỉ xuất hiện khi GET một trong hai endpoint summary/draft.
4. POST cùng path có thể rơi ra ngoài cả ba matcher vì điều kiện method không khớp.
5. Tất cả false chỉ chứng minh **không matcher nào nhận diện**; trong chính sách HTTP phải có fallback, thường là `denyAll()`.

## 8. Đưa ba loại matcher vào một cấu hình Spring Boot

### 8.1. Quy ước chính sách cho demo

Chọn ứng dụng nhỏ có các endpoint:

| HTTP request | Matcher logic | Authority cần |
| --- | --- | --- |
| `GET /public/ping` | GET AND public path | `permitAll()` |
| `GET /api/docs/42` | GET AND docs AND NOT private | `docs:read` |
| `GET /api/docs/private/99` | GET AND private | `docs:private:read` |
| `GET /api/reports/summary` | GET AND (summary OR draft) | `report:read` |
| `GET /api/reports/draft` | GET AND (summary OR draft) | `report:read` |
| `POST /api/reports` | POST AND reports collection | `report:write` |
| Các request khác | Không khớp rule nào ở trên | `denyAll()` |

Để thấy hiệu lực NOT, cấu hình bên dưới đặt **rule normal docs trước rule private docs**. Dù normal docs dùng pattern rộng `/api/docs/**`, phần `NegatedRequestMatcher(privateDocsPath)` bảo đảm private docs **không bị nhận vào rule normal**. Trong production, bạn vẫn có thể chọn rule cụ thể trước rule rộng để dễ review và phòng sai sót khi phát triển thêm.

Tài khoản demo:

| User | Authorities |
| --- | --- |
| `alice` | `docs:read`, `report:read` |
| `bob` | `docs:private:read` |
| `carol` | `report:read`, `report:write` |
| `dave` | `ROLE_USER` |

Lưu ý: `ROLE_USER` không tự mang `docs:read`. Mỗi `hasAuthority(...)` so khớp chuỗi **chính xác**.

### 8.2. Spring Boot 3.5.x / Java 17+ hoàn chỉnh

Dùng Maven project với `spring-boot-starter-web` và `spring-boot-starter-security`. Tạo tệp **`src/main/java/com/example/matchers/MatcherApplication.java`**:

~~~java
package com.example.matchers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.servlet.util.matcher.PathPatternRequestMatcher;
import org.springframework.security.web.util.matcher.AndRequestMatcher;
import org.springframework.security.web.util.matcher.NegatedRequestMatcher;
import org.springframework.security.web.util.matcher.OrRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MatcherApplication {

    public static void main(String[] args) {
        SpringApplication.run(MatcherApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        var paths = PathPatternRequestMatcher.withDefaults();

        RequestMatcher get = request -> "GET".equals(request.getMethod());
        RequestMatcher post = request -> "POST".equals(request.getMethod());

        RequestMatcher allDocs = paths.matcher("/api/docs/**");
        RequestMatcher privateDocsPath =
            paths.matcher("/api/docs/private/**");

        RequestMatcher normalDocs = new AndRequestMatcher(
            get,
            allDocs,
            new NegatedRequestMatcher(privateDocsPath)
        );
        RequestMatcher privateDocs = new AndRequestMatcher(
            get,
            privateDocsPath
        );

        RequestMatcher reportsRead = new AndRequestMatcher(
            get,
            new OrRequestMatcher(
                paths.matcher("/api/reports/summary"),
                paths.matcher("/api/reports/draft")
            )
        );

        RequestMatcher reportsCreate = new AndRequestMatcher(
            post,
            paths.matcher("/api/reports")
        );

        RequestMatcher publicPing = new AndRequestMatcher(
            get,
            paths.matcher("/public/ping")
        );

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(publicPing).permitAll()
                .requestMatchers(normalDocs).hasAuthority("docs:read")
                .requestMatchers(privateDocs)
                    .hasAuthority("docs:private:read")
                .requestMatchers(reportsRead).hasAuthority("report:read")
                .requestMatchers(reportsCreate).hasAuthority("report:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        // CSRF vẫn bật; test POST phải cung cấp token hợp lệ.
        return http.build();
    }

    @Bean
    PasswordEncoder encoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .authorities("docs:read", "report:read")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .authorities("docs:private:read")
            .build();

        UserDetails carol = User.withUsername("carol")
            .password(encoder.encode("demo789"))
            .authorities("report:read", "report:write")
            .build();

        UserDetails dave = User.withUsername("dave")
            .password(encoder.encode("demo000"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(
            alice, bob, carol, dave
        );
    }

    @RestController
    static class Api {

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/docs/{id}")
        String normalDoc(@PathVariable("id") long id) {
            return "doc " + id;
        }

        @GetMapping("/api/docs/private/{id}")
        String privateDoc(@PathVariable("id") long id) {
            return "private doc " + id;
        }

        @GetMapping("/api/reports/summary")
        String summary() {
            return "summary";
        }

        @GetMapping("/api/reports/draft")
        String draft() {
            return "draft";
        }

        @PostMapping("/api/reports")
        ResponseEntity<String> createReport() {
            // Chỉ minh họa authorization, không ghi database.
            return ResponseEntity.status(HttpStatus.CREATED)
                .body("report created");
        }

        @GetMapping("/api/reports/other")
        String unlisted() {
            // Có controller, nhưng fallback phải chặn.
            return "must not be exposed";
        }
    }
}
~~~

**Điểm kiểm tra chính trong mã:**

1. `PathPatternRequestMatcher.withDefaults()` tạo matcher theo đường dẫn (bỏ context path khi khai báo pattern) cho Spring Security 6.5; không lắp chuỗi bằng cách so `request.getRequestURI()` tùy tiện khi ứng dụng có context path/servlet mapping khác.
2. Lambda `get`/`post` kiểm tra method của chính HTTP request, không đụng vào quyền user.
3. `normalDocs` là **AND(GET, docs, NOT private)**.
4. `reportsRead` là **AND(GET, OR(summary, draft))**.
5. `reportsCreate` là **AND(POST, reports collection)**; vì khác method và path nên không bị nhập nhằng với các GET.
6. `authorizeHttpRequests` ghép **mỗi matcher với một AuthorizationManager** như `hasAuthority`; ba class ghép không tự cấp quyền.
7. `anyRequest().denyAll()` bảo vệ các request chưa được nhận diện. Nếu mở một controller mới, endpoint đó vẫn bị chặn cho tới khi có rule được phê duyệt.
8. Không dùng `@EnableMethodSecurity` vì bài chỉ minh họa **HTTP authorization**. Để bảo vệ owner, tenant và trạng thái resource, cần bổ sung policy ở service hoặc domain.

**Không dùng mật khẩu demo trong môi trường thật.** HTTP Basic phải chạy qua HTTPS nếu đưa vào production, và nguồn authority nên đến từ hệ thống định danh/authorization đáng tin cậy.

## 9. Ma trận kết quả HTTP cho ứng dụng mẫu

Giả sử có một request `GET` hoặc `POST` tới đúng URL trong bảng; với POST, giả định CSRF token hợp lệ.

| Subject | Public GET | Normal doc GET | Private doc GET | Summary GET | Draft GET | Report POST* | Other GET |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Anonymous** | 200 | 401 | 401 | 401 | 401 | 401 | 401 |
| **Alice** | 200 | **200** | 403 | **200** | **200** | 403 | 403 |
| **Bob** | 200 | 403 | **200** | 403 | 403 | 403 | 403 |
| **Carol** | 200 | 403 | 403 | **200** | **200** | **201** | 403 |
| **Dave** | 200 | 403 | 403 | 403 | 403 | 403 | 403 |

`*` `Report POST` chỉ là test authorization khi đã cung cấp CSRF token hợp lệ. Nếu thiếu CSRF, một user đúng quyền như Carol vẫn có thể nhận **403**, nhưng đó là kết quả của **CSRF filter** chứ không phải matcher hay `hasAuthority("report:write")`.

**Các ô đáng chú ý:**

- Alice được xem docs thường nhưng **không** xem docs private. Đây là test quan trọng nhất của `NegatedRequestMatcher`.
- Bob chỉ có `docs:private:read`, nên **được xem private** nhưng **không được xem docs thường**. Nó chứng minh quyền private không tự suy ra quyền normal.
- Carol được xem cả `summary` lẫn `draft`, chứng minh `OrRequestMatcher` áp dụng một rule cho hai endpoint.
- Carol **không** được `GET /api/reports/other` dù có `report:read`: matcher OR chỉ khớp hai path đã liệt kê.
- Dave được đăng nhập nhưng không có authority nghiệp vụ, nên không được truy cập các API nhạy cảm.
- Anonymous chỉ được vào public; HTTP Basic dùng **401** khi chưa xác thực trên request bảo vệ.

Những status là **dự kiến cho cấu hình demo**, không phải hợp đồng phổ quát của mọi ứng dụng; form login có thể redirect (302), bearer token có các error response khác, và filter ngoại lệ có thể được tùy biến.

## 10. Chạy ứng dụng và kiểm chứng thủ công

Từ thư mục root project Maven:

~~~bash
# macOS / Linux
./mvnw spring-boot:run

# Windows PowerShell / Command Prompt
mvnw.cmd spring-boot:run
~~~

Khi ứng dụng chạy ở `localhost:8080`, các request GET có thể kiểm tra ngay:

~~~bash
# Công khai: 200
curl -i http://localhost:8080/public/ping

# Alice có docs:read: 200, nhưng không có private: 403
curl -i -u alice:demo123 http://localhost:8080/api/docs/42
curl -i -u alice:demo123 http://localhost:8080/api/docs/private/99

# Bob có docs:private:read: 200 cho private, 403 cho normal
curl -i -u bob:demo456 http://localhost:8080/api/docs/private/99
curl -i -u bob:demo456 http://localhost:8080/api/docs/42

# Carol có report:read: cả summary và draft đều 200
curl -i -u carol:demo789 http://localhost:8080/api/reports/summary
curl -i -u carol:demo789 http://localhost:8080/api/reports/draft

# Path khác không thuộc OR: 403
curl -i -u carol:demo789 http://localhost:8080/api/reports/other

# Anonymous trên URL bảo vệ: 401 với HTTP Basic
curl -i http://localhost:8080/api/docs/42
~~~

Kết quả body với request được phép:

| Request | Body |
| --- | --- |
| `GET /public/ping` | `pong` |
| Alice `GET /api/docs/42` | `doc 42` |
| Bob `GET /api/docs/private/99` | `private doc 99` |
| Carol `GET /api/reports/summary` | `summary` |
| Carol `GET /api/reports/draft` | `draft` |

**Vì sao không khẳng định lệnh `curl -u carol:demo789 -X POST /api/reports` phải trả 201?** CSRF protection đang bật. Một request POST thiếu token hợp lệ có thể bị chặn 403 **trước khi tới authorization**. Để kiểm tra `reportsCreate` và authority `report:write` đúng, dùng MockMvc kết hợp `csrf()` ở phần kế tiếp.

## 11. Kiểm thử tự động bằng MockMvc + Spring Security Test

### 11.1. Dependencies

Trong `pom.xml`, các dependencies test cần thiết:

~~~xml
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
~~~

Đây là **fragment** nằm trong `<dependencies>` của Maven POM, không phải toàn bộ `pom.xml`. Nếu project đã có starter-test thì không thêm bản trùng. Spring Boot 3.5 sẽ quản lý phiên bản tương thích của các dependency khi dùng BOM/parent mặc định.

### 11.2. Test class chạy trong cùng project

Tạo tệp **`src/test/java/com/example/matchers/MatcherApplicationTests.java`**:

~~~java
package com.example.matchers;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;

@SpringBootTest
@AutoConfigureMockMvc
class MatcherApplicationTests {

    @Autowired
    MockMvc mvc;

    @ParameterizedTest
    @CsvSource({
        // username,password,method,path,expectedStatus
        "anonymous,none,GET,/public/ping,200",
        "anonymous,none,GET,/api/docs/42,401",
        "anonymous,none,GET,/api/docs/private/99,401",
        "anonymous,none,GET,/api/reports/summary,401",

        "alice,demo123,GET,/api/docs/42,200",
        "alice,demo123,GET,/api/docs/private/99,403",
        "alice,demo123,GET,/api/reports/summary,200",
        "alice,demo123,GET,/api/reports/draft,200",
        "alice,demo123,GET,/api/reports/other,403",
        "alice,demo123,POST,/api/reports,403",

        "bob,demo456,GET,/api/docs/42,403",
        "bob,demo456,GET,/api/docs/private/99,200",
        "bob,demo456,GET,/api/reports/summary,403",
        "bob,demo456,POST,/api/reports,403",

        "carol,demo789,GET,/api/docs/42,403",
        "carol,demo789,GET,/api/docs/private/99,403",
        "carol,demo789,GET,/api/reports/summary,200",
        "carol,demo789,GET,/api/reports/draft,200",
        "carol,demo789,GET,/api/reports/other,403",
        "carol,demo789,POST,/api/reports,201",

        "dave,demo000,GET,/api/docs/42,403",
        "dave,demo000,GET,/api/docs/private/99,403",
        "dave,demo000,GET,/api/reports/draft,403",
        "dave,demo000,GET,/public/ping,200"
    })
    void authorizationMatrix(
            String username, String password, String method,
            String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request =
            "POST".equals(method) ? post(path) : get(path);

        if (!"anonymous".equals(username)) {
            request.with(httpBasic(username, password));
        }

        // Để kiểm tra quyền POST, loại yếu tố CSRF gây nhiễu.
        if ("POST".equals(method)) {
            request.with(csrf());
        }

        mvc.perform(request).andExpect(status().is(expected));
    }

    @Test
    void ordinaryDocAndPrivateDocAreMutuallyExclusive() throws Exception {
        mvc.perform(get("/api/docs/42")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("doc 42"));

        mvc.perform(get("/api/docs/private/99")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/docs/private/99")
                .with(httpBasic("bob", "demo456")))
            .andExpect(status().isOk())
            .andExpect(content().string("private doc 99"));
    }

    @Test
    void orMatcherCoversBothReports() throws Exception {
        mvc.perform(get("/api/reports/summary")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports/draft")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/reports/other")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfStillRequiresWriteAuthority() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        mvc.perform(post("/api/reports")
                .with(httpBasic("carol", "demo789"))
                .with(csrf()))
            .andExpect(status().isCreated())
            .andExpect(content().string("report created"));
    }

    @Test
    void missingCsrfIsNotProofOfMissingAuthority() throws Exception {
        mvc.perform(post("/api/reports")
                .with(httpBasic("carol", "demo789")))
            .andExpect(status().isForbidden());
    }

    @Test
    void unsupportedMethodIsDenied() throws Exception {
        mvc.perform(post("/api/docs/42")
                .with(httpBasic("alice", "demo123"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }
}
~~~

**Kết cấu test:**

- `@SpringBootTest` + `@AutoConfigureMockMvc` tải cấu hình security và các controller thực của ứng dụng.
- `httpBasic()` đưa credential demo qua Basic authentication để đi qua `UserDetailsService`. So với `@WithMockUser`, cách này còn kiểm tra quá trình xác thực và việc cấp authority của user demo.
- `csrf()` chỉ phục vụ **request test**, tạo token hợp lệ để kiểm chứng rule write; không đồng nghĩa client production có thể tùy ý tự tạo token.
- `@CsvSource` cung cấp **24 trường hợp** với các kết quả 200/201/401/403; các test riêng nhấn mạnh NOT, OR, method và CSRF.
- Các test thiếu quyền là **bắt buộc**: nếu lỡ để matcher tài liệu thường bắt cả tài liệu private, test Alice bị 403 ở private sẽ phát hiện regression.

Chạy test:

~~~bash
# macOS / Linux
./mvnw test

# Windows
mvnw.cmd test
~~~

Output test còn phụ thuộc phiên bản JUnit/Maven, nên không khẳng định trước số dòng log hoặc thời gian chạy. Điều cần xác nhận là các test **pass**, quá trình Maven trả mã thoát 0 và không còn failure/error.

## 12. Hai tầng matcher: `securityMatcher` và `requestMatchers`

Một điểm dễ nhầm là **ghép RequestMatcher để chọn SecurityFilterChain** và **ghép RequestMatcher để chọn một authorization rule** dùng chung API matcher nhưng **tác động khác nhau**.

### 12.1. `securityMatcher(composite)` chọn *cả chain*

Ví dụ chỉ áp dụng một chain cho các API dành cho tài liệu **hoặc** báo cáo:

~~~java
RequestMatcher docsOrReports = new OrRequestMatcher(
    paths.matcher("/api/docs/**"),
    paths.matcher("/api/reports/**")
);

http.securityMatcher(docsOrReports);
~~~

Đây là **fragment cấu hình** với biến `paths` đã khai báo. Nó điều khiển việc một `SecurityFilterChain` có tham gia xử lý request hay không. Nếu request nằm ngoài tập này, chain **không chạy** và các rule bên trong chain cũng **không có tác dụng** cho request đó.

Nếu ứng dụng chỉ có chain giới hạn `docsOrReports` mà không có chain fallback, `/admin` hoặc `/public` có thể **không được Spring Security bảo vệ**. Cần có fallback chain phù hợp. Không sao chép fragment này vào ứng dụng một chain ở mục 8 khi chưa thiết kế lại phạm vi bảo vệ.

### 12.2. `requestMatchers(composite)` chọn *rule trong chain*

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers(reportsRead).hasAuthority("report:read")
    .anyRequest().denyAll()
);
~~~

`reportsRead` chỉ phân loại request **sau khi chain đã được chọn**. Với danh sách rule HTTP, **rule đầu tiên khớp** được áp dụng; nếu nó từ chối, Spring không thử rule phía dưới để tìm ALLOW.

**Ví dụ lỗ hổng do thứ tự:**

~~~java
// Sai: rule quá rộng che matcher ghép bên dưới.
.requestMatchers("/api/**").authenticated()
.requestMatchers(normalDocs).hasAuthority("docs:read")
~~~

Một user đã đăng nhập nhưng thiếu `docs:read` có thể vượt HTTP authorization cho tài liệu thường do `/api/**` đứng trước. Dù `normalDocs` tính đúng Boolean, nó vẫn **không được dùng** nếu rule trước đã khớp.

### 12.3. Nguyên tắc phân tầng

- **Chain selection:** `FilterChainProxy` chọn chain đầu tiên khớp theo ưu tiên.
- **Rule selection:** `AuthorizationFilter` chọn rule đầu tiên khớp trong chain.
- **Authorization decision:** `hasAuthority`, `authenticated`, `denyAll` hoặc custom `AuthorizationManager` đưa ra quyết định quyền.
- **Domain policy:** kiểm tra tenant, owner, trạng thái tài nguyên ở tầng nghiệp vụ khi cần.

Không đồng nhất bốn khái niệm này. **AND/OR/NOT của matcher không thay thế AND/OR/NOT của quyết định quyền**.

## 13. Rủi ro khi ghép header, query, path và trạng thái request

Vì `RequestMatcher` là functional interface, bạn có thể ghép cả matcher tùy biến:

~~~java
RequestMatcher isGet = request ->
    "GET".equals(request.getMethod());

RequestMatcher hasPreviewFlag = request ->
    "true".equals(request.getParameter("preview"));

RequestMatcher previewDocs = new AndRequestMatcher(
    isGet,
    paths.matcher("/api/docs/**"),
    hasPreviewFlag
);
~~~

Đây là **fragment**; có thể dùng khi request có nhánh preview riêng. Nhưng cần phân biệt:

- Client có thể **tự đặt query parameter hoặc header**. Một matcher như `X-Is-Admin=true` **không** chứng minh người gọi là admin.
- Một `OrRequestMatcher` ghép path và header theo cách thiếu ràng buộc có thể mở rộng tập được khớp ra ngoài dự định: `OR(docsPath, previewHeader)` khớp **mọi path** nếu client tự gửi header.
- Dùng `NegatedRequestMatcher` trên tín hiệu do client kiểm soát rất nguy hiểm nếu rule đó gắn với `permitAll()`.
- Query string nói chung không phải một phần của path pattern. Nếu chính sách phụ thuộc query, cần matcher kiểm query tường minh và test trường hợp thiếu/giả mạo.
- Matcher đọc header/query chỉ nên điều hướng đến **chính sách phù hợp**; cấp quyền vẫn dựa vào `Authentication` và server-side policy.
- Tránh matcher thực hiện I/O nặng, đọc body hoặc thay đổi request khi kiểm tra. Hệ thống có thể đánh giá matcher trong các bối cảnh khác nhau; không nên dựa vào side effect hay số lần nó được gọi.

### Path và servlet context

`PathPatternRequestMatcher` dùng pattern tương đối với context path của ứng dụng; nếu bạn chạy sau một proxy hoặc có servlet path khác mặc định, cần cấu hình pattern/base path tương ứng. Không lấy URL đầy đủ do user thấy trên browser rồi mặc định matcher so chính xác cùng chuỗi.

Với Spring Security 6.5, `AntPathRequestMatcher` đã bị đánh dấu deprecated for removal; nên ưu tiên `PathPatternRequestMatcher` cho dự án mới, trong khi migration từ code cũ cần test lại các pattern và servlet mappings. Khi nâng Spring Security 7, kiểm tra sự thay đổi API/DSL theo tài liệu phiên bản đích.

## 14. Kết quả `matcher(request)` và biến đường dẫn

Bên cạnh `matches(request)` trả boolean, `RequestMatcher` có `matcher(HttpServletRequest)` trả `MatchResult`, có thể chứa các biến được trích từ path matcher.

- `AndRequestMatcher.matcher(request)` có thể ghép các biến từ những matcher con đã khớp; trong Spring Security 6.5, nếu trùng tên biến, giá trị của matcher sau có thể ghi đè.
- `OrRequestMatcher.matcher(request)` sử dụng biến từ matcher khớp đầu tiên.
- `NegatedRequestMatcher` đảo điều kiện khớp. Không nên trông chờ NOT giúp trích xuất biến của matcher phủ định trong nhánh không khớp.
- Nếu custom matcher cần trả biến, có thể phải override `matcher(request)`; một lambda chỉ định nghĩa `matches(request)` thường chỉ đưa lại kết quả match mặc định, không có biến tự trích.

Ví dụ nếu cần `documentId` trong biểu thức authorization, hãy dùng đúng API matcher/path variables đã được xác minh, thay vì tự phân tích chuỗi path thiếu kiểm tra. Với bài này, các matcher chỉ chọn rule nên **không cần dựa vào trích biến**.

## 15. Checklist kiểm thử AND / OR / NOT

| Nhóm kiểm thử | Request hoặc điều kiện | Kỳ vọng |
| --- | --- | --- |
| AND đủ điều kiện | GET + docs path thường | Khớp normal docs |
| AND thiếu method | POST + docs path thường | Không khớp normal docs |
| AND thiếu path | GET + reports path | Không khớp normal docs |
| OR nhánh trái | GET summary | Khớp reportsRead |
| OR nhánh phải | GET draft | Khớp reportsRead |
| OR không nhánh nào | GET other | Không khớp reportsRead |
| NOT loại trừ | GET docs private | Không khớp normal; khớp private |
| NOT nằm trong scope đúng | GET outside docs | Không khớp normal |
| Phân quyền thiếu authority | Alice gọi private | 403, dù request private khớp |
| Phân quyền đúng authority | Bob gọi private | 200 |
| Fallback | Carol gọi report other | 403 |
| CSRF độc lập | Carol POST báo cáo thiếu token | 403 do CSRF |
| CSRF hợp lệ + đủ quyền | Carol POST báo cáo có token | 201 |
| CSRF hợp lệ + thiếu quyền | Alice POST báo cáo có token | 403 do authorization |

**Lưu ý test âm tính:** Các trường hợp “không được khớp” thường bắt được lỗi nguy hiểm nhất. Nếu NOT bị bỏ quên, Alice có `docs:read` có thể đọc private ngoài ý muốn. Test chỉ kiểm Bob đọc private được 200 sẽ **không phát hiện** lỗi này.

**Test với nhiều chain:** Nếu ứng dụng có `@Order` và nhiều `securityMatcher`, thêm các ca cho request vào chain A, chain B, và request không khớp chain nào; một `anyRequest().denyAll()` bên trong chain A không bảo vệ request nằm ngoài chain A.

## 16. Những lỗi thiết kế hay gặp

1. **Dùng `OrRequestMatcher` để mong “có quyền A hoặc B”.** Sai loại logic; đó là OR cho **request**, không phải OR cho authorities.
2. **Dùng `AndRequestMatcher` với `getMethod` nhưng quên ràng buộc path.** Có thể chọn quá nhiều request GET không liên quan.
3. **Đặt `NegatedRequestMatcher(secret)` một mình với `permitAll`.** Gần như mọi URL khác có thể được mở.
4. **Quên fallback `anyRequest().denyAll()`.** Dẫn đến chính sách không rõ ràng khi xuất hiện endpoint mới.
5. **Đặt matcher bao quát `/api/**.authenticated()` phía trước matcher ghép chi tiết.** Matcher chi tiết không còn cơ hội được dùng.
6. **Tin rằng hai matcher trùng path sẽ tạo AND/OR của các quyết định quyền.** Rule đầu tiên khớp được dùng; hãy ghép các điều kiện vào cùng một manager/rule khi cần.
7. **Dựa vào header do client gửi để cấp role.** Header/query không phải authority đáng tin.
8. **Dùng pattern đường dẫn sai context/servlet path.** Có thể bỏ qua rule quan trọng hoặc vô tình match sai.
9. **Viết `NOT` không có scope dương.** Phủ định một tập nhỏ sẽ trở thành một tập request khổng lồ.
10. **Bỏ qua HTTP method.** Rule GET có thể vô tình bao phủ request ghi, nếu path matcher đứng riêng.
11. **Kết luận 403 do thiếu quyền khi POST thiếu CSRF token.** Cần test có CSRF hợp lệ để cô lập authorization.
12. **Chỉ test trường hợp được phép.** Có thể không bắt được lỗi mở quyền cho user không đủ authority.
13. **Dựa vào thứ tự gọi hoặc side effect của matcher con.** Matcher nên thuần và ổn định.
14. **Cho rằng `securityMatcher` và `requestMatchers` là cùng một phạm vi.** Một cái chọn chain, một cái chọn rule.

## 17. Câu hỏi tự kiểm tra

**1.** `AndRequestMatcher(GET, "/api/docs/**")` có khớp `POST /api/docs/42` không?  
**Đáp án:** Không. Method không khớp dù path khớp.

**2.** `OrRequestMatcher(summaryPath, draftPath)` có tự cho người dùng quyền `report:read` không?  
**Đáp án:** Không. Nó chỉ xác định request thuộc một trong hai path; authority vẫn được kiểm ở rule `hasAuthority("report:read")`.

**3.** `NegatedRequestMatcher(privateDocsPath)` có khớp `GET /admin/delete` không?  
**Đáp án:** Có, vì request đó **không thuộc privateDocsPath**. Đó là lý do NOT phải được giới hạn bằng AND với tập path/method mong muốn.

**4.** Biểu thức nào mô tả “GET docs nhưng không private”?  
**Đáp án:** `And(GET, DOCS, Negated(PRIVATE))`.

**5.** Alice có `docs:read` nhưng không có `docs:private:read`. Vì sao `GET /api/docs/private/99` phải là 403?  
**Đáp án:** NOT loại request khỏi normalDocs; rule privateDocs khớp và kiểm authority `docs:private:read` mà Alice thiếu.

**6.** Nếu đặt `/api/**.authenticated()` trước `normalDocs` thì sao?  
**Đáp án:** Một user chỉ đăng nhập có thể qua HTTP authorization của tài liệu thường; rule chi tiết bị che khuất bởi first-match.

**7.** Có thể dùng `new OrRequestMatcher(A, B)` ở `http.securityMatcher` không?  
**Đáp án:** Có; lúc đó nó quyết định **cả SecurityFilterChain** có áp dụng cho request không, chứ chưa quyết định quyền.

**8.** Vì sao test `POST /api/reports` với CSRF token hợp lệ mới có ý nghĩa để xác minh `report:write`?  
**Đáp án:** Vì thiếu CSRF token có thể bị chặn trước authorization, tạo 403 không liên quan tới authority.

**9.** `¬(A ∨ B)` có bằng `¬A ∧ ¬B` không?  
**Đáp án:** Có (De Morgan), nhưng phải xác định đúng tập request A, B và phạm vi dùng biểu thức phủ định.

**10.** Nếu user đủ quyền truy cập URL nhưng tài liệu thuộc tenant khác, có được kết luận ALLOW chưa?  
**Đáp án:** Chưa. Matcher và HTTP permission không thay thế kiểm tra tài nguyên cụ thể trong service/domain policy.

**Ghi nhớ:** `AndRequestMatcher` = **tất cả điều kiện request**, `OrRequestMatcher` = **một trong nhiều điều kiện request**, `NegatedRequestMatcher` = **đảo điều kiện request**. **Matcher chỉ chọn rule; AuthorizationManager mới quyết định quyền.** Luôn ràng buộc NOT bằng scope dương, sắp thứ tự rule đúng, dùng default deny và test cả các ca không được phép.

## Tài liệu chính thức

- Spring Security 6.5 — `RequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/RequestMatcher.html
- Spring Security 6.5 — `AndRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/AndRequestMatcher.html
- Spring Security 6.5 — `OrRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/OrRequestMatcher.html
- Spring Security 6.5 — `NegatedRequestMatcher` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/util/matcher/NegatedRequestMatcher.html
- Spring Security 6.5 — Authorize HTTP Requests: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html
- Spring Security 6.5 — Java Configuration / SecurityFilterChain selection: https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html
- Spring Security — MockMvc and HTTP Basic tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/http-basic.html
- Spring Security — MockMvc CSRF testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
