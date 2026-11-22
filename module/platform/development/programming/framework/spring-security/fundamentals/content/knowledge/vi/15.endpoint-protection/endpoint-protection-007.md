# Điều kiện chọn chuỗi không thay thế các quy tắc bên trong chuỗi

## 1. Vấn đề: “Chọn chuỗi” và “cho phép request” là hai quyết định khác nhau

Trong Spring Security Servlet, mỗi `SecurityFilterChain` chứa một nhóm security filter áp dụng cho những HTTP request phù hợp. Khi có nhiều chuỗi, Spring Security cần quyết định **request nào đi vào chuỗi nào** trước khi các filter trong chuỗi đó xử lý xác thực và phân quyền.

Hai câu hỏi quan trọng phải được trả lời **theo đúng thứ tự**:

1. **Chọn chuỗi:** `SecurityFilterChain` nào áp dụng cho request này? Đây là trách nhiệm của `FilterChainProxy` cùng bộ so khớp ở cấp chuỗi, thường cấu hình bằng `http.securityMatcher(...)`.
2. **Kiểm tra quyền trong chuỗi đã chọn:** Request có được truy cập endpoint hay không? Đây là trách nhiệm của cấu hình `http.authorizeHttpRequests(...)` với `requestMatchers(...)`, `authenticated()`, `hasAuthority(...)`, `permitAll()`, `denyAll()`, v.v.

**Mệnh đề cần nhớ:** `securityMatcher("/api/**")` có nghĩa **“chuỗi này được chọn cho request thuộc phạm vi `/api/**`”**, **không có nghĩa** “ai đó được phép truy cập toàn bộ `/api/**`” hoặc “mọi request thuộc `/api/**` đều đòi đăng nhập”. Điều kiện chọn chuỗi không tự tạo ra quy tắc phân quyền.

Có thể hình dung:

~~~text
HTTP request
    |
    v
FilterChainProxy: xét SecurityFilterChain theo thứ tự ưu tiên
    |
    |-- Không khớp chuỗi hiện tại --> thử chuỗi tiếp theo
    |
    |-- Khớp một chuỗi -----------> chỉ chạy các filter của chuỗi đó
                                       |
                                       v
                           Authentication / SecurityContext
                                       |
                                       v
                           AuthorizationFilter (khi được cấu hình)
                                       |
                                       v
                           authorizeHttpRequests:
                             requestMatchers(...) / anyRequest()
                                       |
                              ALLOW hoặc DENY
    |
    |-- Không khớp bất kỳ chuỗi nào --> không được bảo vệ bởi
                                      Spring Security filter chains
~~~

Lưu ý: nếu request đã khớp một chuỗi nhưng **bị từ chối bên trong chuỗi đó**, `FilterChainProxy` **không thử lại** chuỗi tiếp theo để tìm một rule dễ hơn. Chỉ khi **điều kiện chọn chuỗi không khớp** thì mới xét chuỗi sau. Một request thông thường được xử lý bởi **chuỗi khớp đầu tiên**, không phải kết hợp quyền của mọi chuỗi.

## 2. Phân biệt ba cấp matcher

| Cấu hình | Vai trò | Phạm vi thực sự | Sai lầm thường gặp |
| --- | --- | --- | --- |
| `http.securityMatcher("/api/**")` | Chọn phạm vi cho một `HttpSecurity`/`SecurityFilterChain` | Chỉ request khớp `/api/**` có thể được chuỗi này xử lý | Tưởng chỉ khai báo selector là đã yêu cầu đăng nhập |
| `http.authorizeHttpRequests(a -> a.requestMatchers("/api/admin/**").hasRole("ADMIN"))` | Định nghĩa rule truy cập endpoint | Chỉ được xét **sau khi request đã vào chuỗi đó** | Tưởng rule có thể “kéo” request ngoài phạm vi selector vào chuỗi |
| `authorize.anyRequest().denyAll()` | Rule cuối cho request chưa khớp rule cụ thể | Mọi request **còn lại trong chính chuỗi đang được chọn** | Tưởng `anyRequest()` của chuỗi API bảo vệ toàn bộ ứng dụng |

Ví dụ với chuỗi có `securityMatcher("/api/**")`:

- `GET /api/reports/7`: có thể vào chuỗi đó. Rule nội bộ quyết định cho phép hay từ chối.
- `GET /api/users/5`: cũng có thể vào chuỗi đó; nếu không có rule cụ thể, `anyRequest()` của **chuỗi API** sẽ quyết định.
- `GET /admin/settings`: không vào chuỗi API. Một `requestMatchers("/admin/**")` được đặt *bên trong chuỗi API* không thể áp dụng cho request này.
- `GET /health`: không vào chuỗi API; phải do một chuỗi khác xử lý nếu muốn Spring Security bảo vệ/quy định truy cập.

Đừng nhầm `requestMatchers` trong `authorizeHttpRequests` với `securityMatchers`/`securityMatcher` ở cấp `HttpSecurity`: API đều có từ “matcher”, nhưng chúng nằm ở **hai bước khác nhau của luồng request**.

## 3. Cơ chế thực thi của nhiều SecurityFilterChain

Mỗi bean `SecurityFilterChain` có một `RequestMatcher` riêng để xác định xem nó có áp dụng cho request hay không. `FilterChainProxy` duyệt danh sách chuỗi theo thứ tự, chọn chuỗi **đầu tiên** có matcher đúng.

Thông thường:

- `@Order(1)` được ưu tiên hơn `@Order(2)`.
- Một bean không có `@Order` thường đứng sau các bean có độ ưu tiên cao hơn.
- Cấu hình `securityMatcher(...)` thay bộ chọn mặc định của chuỗi (mặc định khớp mọi request).
- Một chuỗi không có `securityMatcher(...)` thường đóng vai trò **catch-all/fallback**.
- Khi đã chọn, chỉ bộ lọc của chuỗi đó chạy; bộ lọc và các rule cấu hình riêng của chuỗi khác không được “ghép thêm” vào.
- Nếu không chuỗi nào khớp, request không chịu sự bảo vệ của các Spring Security filter chains. Ứng dụng vẫn có thể có cơ chế bảo vệ khác, nhưng không nên trông chờ vào chúng một cách ngầm định.

Ví dụ hai chuỗi:

~~~text
Chain A: @Order(1), securityMatcher("/api/**")
Chain B: không có securityMatcher (fallback toàn bộ request còn lại)

GET /api/reports/7  -> Chain A (dù Chain B cũng có thể match)
GET /health         -> Chain B
GET /unknown        -> Chain B
~~~

**Thứ tự chọn chuỗi** hoàn toàn khác với **thứ tự chọn rule bên trong một chuỗi**:

- `FilterChainProxy`: chuỗi khớp đầu tiên theo thứ tự `SecurityFilterChain`.
- `authorizeHttpRequests`: rule khớp đầu tiên theo thứ tự `requestMatchers(...)`/`anyRequest()` trong **chuỗi đã chọn**.

Hai tầng này có thể cùng dựa trên đường dẫn HTTP nhưng phục vụ hai mục tiêu khác nhau. Mỗi tầng cần kiểm thử riêng.

## 4. Ví dụ cấu hình Spring Security Servlet đúng và có fallback

Ví dụ sau dành cho ứng dụng Spring Boot dùng Spring Web (Servlet) và Spring Security, với Java 17+. Đây là **class cấu hình tích hợp trong dự án Spring**, không phải chương trình Java độc lập chạy trực tiếp bằng `javac`. Các endpoint và quyền chỉ là ví dụ về cách thiết kế.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class EndpointSecurityConfiguration {

    // Chuỗi đầu: chỉ áp dụng cho đường dẫn bắt đầu bằng /api/.
    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("report:read")
                .requestMatchers(HttpMethod.POST, "/api/reports/**")
                    .hasAuthority("report:write")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }

    // Chuỗi fallback: được xét khi chuỗi API không khớp.
    @Bean
    @Order(2)
    SecurityFilterChain fallbackChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/health").permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

Đọc chính xác theo từng bước:

**A. Chọn chuỗi bằng `securityMatcher`.** Với `GET /api/reports/42`, `FilterChainProxy` chọn `apiChain` vì đường dẫn khớp `/api/**`. Fallback không được dùng cho request này. Với `GET /health`, chuỗi API không khớp nên fallback được xét.

**B. Phân quyền bên trong `apiChain`.** `GET /api/reports/42` cần authority chính xác `report:read`. `POST /api/reports/42` cần `report:write`. Một request khác như `DELETE /api/reports/42` hay `GET /api/unknown` không khớp hai rule trước, nên gặp `anyRequest().denyAll()` và bị từ chối.

**C. Phân quyền bên trong `fallbackChain`.** Chỉ `GET /health` được `permitAll()`; các request còn lại chưa được chuỗi API nhận sẽ gặp `denyAll()`. Chúng **không được “đi vòng” về chuỗi API**.

**D. Filter và cơ chế bảo mật khác.** Ví dụ cấu hình HTTP Basic cho API, nhưng một request POST vẫn có thể chịu **CSRF protection** theo cấu hình mặc định; có authority `report:write` không có nghĩa mọi POST chắc chắn thành công. Ứng dụng API token stateless cần cấu hình xác thực, quản lý session và CSRF theo mô hình client thực tế, không nên tắt CSRF chỉ để ví dụ trả 200.

**E. Cấu hình ứng dụng thực tế.** Phải bổ sung route hợp lệ, authentication provider/JWT/session, các security chain cần thiết và quyền trên đối tượng nghiệp vụ. `hasAuthority("report:read")` chỉ kiểm tra khả năng đọc theo authority; việc đọc báo cáo ID 42 có thể còn đòi đúng tenant/owner ở service hoặc repository. Không nên dùng một authority để bỏ qua kiểm tra dữ liệu per-resource.

### 4.1. Tại sao `anyRequest().denyAll()` ở chuỗi API có ý nghĩa?

Trong ví dụ trên, selector `/api/**` nói rằng *những request này dùng bộ lọc API*. Rule cuối `denyAll()` nói rằng *mọi loại endpoint API chưa được khai báo rõ quyền sẽ bị từ chối*. Đây là hai chính sách bổ trợ nhau.

Nếu thay `denyAll()` thành `authenticated()` thì các URL API còn lại **được phép ở cấp HTTP authorization** cho bất kỳ người dùng nào đã xác thực, miễn không có rule cụ thể chặn. Đôi khi đây là yêu cầu hợp lệ; trong API nhạy cảm nên chủ động kiểm kê những route được mở theo fallback này.

Nếu bỏ hẳn `authorizeHttpRequests`, chỉ còn selector và các filter khác được cấu hình; **selector tự thân không phải là rule bắt buộc xác thực hoặc phân quyền**. Vì thế phải review đầy đủ cả việc chọn chuỗi lẫn cấu hình authorization.

## 5. Bảng dự đoán kết quả của cấu hình

Bảng dưới đây nói về **quyết định authorization tại lớp HTTP** của ví dụ. Kết quả cuối cùng của request thực tế còn phụ thuộc xác thực, CSRF, endpoint có tồn tại và kiểm tra nghiệp vụ.

| Request | Principal/authority | Chuỗi chọn | Rule nội bộ | Quyết định authorization |
| --- | --- | --- | --- | --- |
| `GET /api/reports/7` | Đã đăng nhập, có `report:read` | `apiChain` | GET reports → `hasAuthority("report:read")` | **ALLOW** |
| `GET /api/reports/7` | Đã đăng nhập, không có `report:read` | `apiChain` | GET reports | **DENY** |
| `POST /api/reports/7` | Chỉ có `report:read` | `apiChain` | POST reports → `hasAuthority("report:write")` | **DENY** |
| `POST /api/reports/7` | Có `report:write` | `apiChain` | POST reports | **ALLOW** ở bước authorization; các filter khác có thể chặn |
| `DELETE /api/reports/7` | Có cả read/write | `apiChain` | `anyRequest().denyAll()` | **DENY** |
| `GET /api/unknown` | Có `report:read` | `apiChain` | `anyRequest().denyAll()` | **DENY** |
| `GET /health` | Chưa đăng nhập | `fallbackChain` | `permitAll()` | **ALLOW** |
| `GET /profile` | Đã đăng nhập, có mọi authority API | `fallbackChain` | `denyAll()` | **DENY** |
| `POST /health` | Chưa đăng nhập | `fallbackChain` | `denyAll()` (không khớp GET) | **DENY** |

**Quan trọng:** `DENY` trong bảng là kết quả tại rule, không mặc định gắn với một mã HTTP cố định. Với endpoint yêu cầu xác thực, thiếu authentication thường dẫn tới entry point (ví dụ HTTP Basic trả 401), đã xác thực nhưng thiếu quyền thường là 403. Nếu CSRF thất bại, kết quả cũng có thể là 403 dù authority đúng. Một rule `permitAll()` không tự tắt CSRF, các filter khác hoặc validation của controller.

## 6. Hai lỗi về thứ tự cần phân biệt

### 6.1. Lỗi thứ tự **giữa các chuỗi**

Giả sử ứng dụng muốn áp dụng cơ chế mạnh hơn cho `/api/admin/**` nhưng viết:

~~~java
@Bean
@Order(1)
SecurityFilterChain broadApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // Các filter và quy tắc API phổ thông...
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain adminApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/admin/**");
    // Các filter và quy tắc admin chặt hơn...
    return http.build();
}
~~~

Đây là **đoạn minh họa lỗi thứ tự**, không phải cấu hình đầy đủ. Request `GET /api/admin/users` khớp `/api/**` ở chuỗi thứ nhất, vì thế `adminApi` thứ hai **không bao giờ được chọn** cho request đó. Không có cơ chế tự “nâng cấp” sang chuỗi admin khi rule của chuỗi đầu không đạt.

**Cách sửa:** đưa chain chuyên biệt `/api/admin/**` lên độ ưu tiên cao hơn, ví dụ `@Order(1)`, đặt chain tổng quát `/api/**` ở `@Order(2)`, rồi một catch-all sau cùng. Mỗi chuỗi vẫn phải khai báo authorization bên trong.

### 6.2. Lỗi thứ tự **giữa các rule nội bộ**

Đoạn dưới sai vì rule tổng quát đứng trước rule chi tiết:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/**").authenticated()
        .requestMatchers("/api/admin/**").hasRole("ADMIN")
    );
~~~

Đây là **ví dụ anti-pattern**, không phải cấu hình khuyến nghị. Rule `/api/**` đã khớp với request `/api/admin/users` trước khi `hasRole("ADMIN")` được xét, khiến quy tắc chuyên biệt không có hiệu lực như mong muốn. Các phiên bản/cách cấu hình có thể cảnh báo hoặc từ chối rule không thể được dùng sau một matcher quá rộng; dù vậy thứ tự tổng quát trước cụ thể là sai thiết kế.

**Cách sửa:** đặt `requestMatchers("/api/admin/**").hasRole("ADMIN")` trước matcher chung; kết thúc bằng `anyRequest().denyAll()` hoặc một fallback quyền phù hợp. Thứ tự giữa các *chain* và thứ tự giữa các *rule* đều quan trọng nhưng **không thể thay thế cho nhau**.

## 7. Những cấu hình dễ hiểu sai

### Trường hợp A — Chỉ chọn chuỗi mà không định nghĩa quyền

~~~java
http.securityMatcher("/api/**")
    .httpBasic(Customizer.withDefaults());
~~~

Đoạn này chỉ nói HTTP Basic là một cơ chế xác thực trong chuỗi API; nó **không tự định nghĩa** rằng mọi request API phải có principal, role hoặc authority. Các security filter khác trong chuỗi vẫn có thể hoạt động, nên không được diễn giải đây là “tắt toàn bộ bảo mật”; nhưng đừng xem nó đã bảo vệ endpoint bằng rule phân quyền.

Cần khai báo có chủ đích, chẳng hạn:

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults());
~~~

Đây là yêu cầu đăng nhập cho các request nằm trong chuỗi API; nếu API đòi quyền theo thao tác, thay bằng các `requestMatchers(...).hasAuthority(...)` phù hợp trước rule cuối.

### Trường hợp B — Rule nội bộ ngoài phạm vi selector

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/admin/**").hasRole("ADMIN")
        .anyRequest().permitAll()
    );
~~~

`/admin/**` nằm ngoài phạm vi `/api/**` nên rule admin này **không bao giờ được xét cho `/admin/**`** trong chain trên. `anyRequest().permitAll()` chỉ áp dụng cho request **đã đi vào chuỗi API**, làm toàn bộ API còn lại được permit ở tầng HTTP authorization. Nếu không có fallback, `/admin/**` còn có thể không được Spring Security filter chain nào bảo vệ.

Cách giải quyết: sửa selector để chứa phạm vi cần bảo vệ, hoặc đặt rule admin trong chuỗi có selector phù hợp; thêm catch-all và test từng route. Không “chữa cháy” bằng cách chỉ thêm rule vào nhầm chuỗi.

### Trường hợp C — Một chuỗi giới hạn mà quên fallback

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        );
    return http.build();
}
~~~

Nếu đây là **chuỗi duy nhất** của ứng dụng, `/api/**` được kiểm soát, nhưng các request như `/admin`, `/actuator/health`, `/files` không được chain này chọn. Khi **không có bất kỳ chain nào khác khớp**, Spring Security filter chains không bảo vệ request đó. Sự tồn tại của `anyRequest().authenticated()` bên trong `onlyApi` không thay đổi phạm vi `/api/**`.

Giải pháp phổ biến là thêm **fallback chain không đặt `securityMatcher`**, kiểm soát các endpoint công khai thật sự cần mở, và `denyAll` hoặc `authenticated` cho phần còn lại theo chính sách của hệ thống.

### Trường hợp D — Dùng `permitAll` và bỏ qua Spring Security như nhau

`permitAll()` là quyết định ở bước **authorization** của chuỗi đã chọn. Những filter khác vẫn có thể thực thi (headers, CSRF, security context...). Ngược lại, request không khớp chain nào không đi qua các security filter của `FilterChainProxy`. Cũng không nên nhầm với cấu hình `web.ignoring()`, vốn bỏ qua lớp security filter cho các request phù hợp và có hệ quả khác đối với headers/observability. Khi mở một endpoint công khai, thường nên dùng `permitAll()` trong chain phù hợp.

## 8. Điểm đặc biệt: filter tự cung cấp endpoint

Một số filter Spring Security trực tiếp xử lý endpoint như login/logout. Ví dụ `formLogin()` có thể cung cấp `POST /login`; nếu chuỗi chỉ chọn `/secured/**` thì `/login` không khớp chuỗi đó. Kết quả có thể là **404** vì filter xử lý login không chạy cho đường dẫn ngoài selector.

~~~text
Chain chỉ nhận /secured/** và có formLogin()
POST /login          -> không khớp chain này
POST /secured/login  -> chỉ hoạt động nếu đã tùy chỉnh URL login tương ứng
~~~

Tùy ngữ cảnh, có thể cấu hình `loginPage("/secured/login")` và `loginProcessingUrl("/secured/login")`, hoặc bố trí login trong một chain khác có matcher phù hợp. Tương tự, hãy xét đúng path cho logout, OAuth2 authorization/callback, endpoint token hoặc cơ chế xác thực do filter cung cấp.

**Bài học:** chỉnh `securityMatcher` có thể làm endpoint do filter cung cấp **rời khỏi phạm vi chuỗi**, ngay cả khi các rule `authorizeHttpRequests` trông hợp lý. Kiểm thử login/logout/callback là việc riêng, không chỉ thử REST controller.

## 9. Mô phỏng runnable Java 17: chọn chain trước, chọn rule sau

Ví dụ Java thuần dưới đây mô phỏng **nguyên tắc hai tầng** với hai chuỗi và các rule có thứ tự. Đây là **mô hình dạy học**, không mô phỏng toàn bộ `FilterChainProxy`, request matcher thực tế, cơ chế authentication, CSRF hay HTTP status.

Tạo tệp **`ChainSelectionDemo.java`**:

~~~java
import java.util.List;
import java.util.Set;
import java.util.function.Predicate;

public class ChainSelectionDemo {
    record Request(String method, String path, boolean authenticated,
                   Set<String> authorities) {}
    record Rule(String name, Predicate<Request> pathMatches,
                Predicate<Request> allow) {}
    record Chain(String name, Predicate<Request> selector, List<Rule> rules) {}

    static String decide(Request request, List<Chain> chains) {
        for (Chain chain : chains) {
            if (!chain.selector().test(request)) continue;
            for (Rule rule : chain.rules()) {
                if (rule.pathMatches().test(request)) {
                    return chain.name() + " / " + rule.name() + " -> "
                            + (rule.allow().test(request) ? "ALLOW" : "DENY");
                }
            }
            return chain.name() + " / no authorization rule";
        }
        return "NO CHAIN MATCHED";
    }

    public static void main(String[] args) {
        Predicate<Request> isReport = r -> r.path().startsWith("/api/reports/");
        List<Chain> chains = List.of(
            new Chain("api", r -> r.path().startsWith("/api/"), List.of(
                new Rule("GET report:read",
                    r -> r.method().equals("GET") && isReport.test(r),
                    r -> r.authorities().contains("report:read")),
                new Rule("POST report:write",
                    r -> r.method().equals("POST") && isReport.test(r),
                    r -> r.authorities().contains("report:write")),
                new Rule("api denyAll", r -> true, r -> false)
            )),
            new Chain("fallback", r -> true, List.of(
                new Rule("health permitAll", r -> r.path().equals("/health"),
                    r -> true),
                new Rule("fallback denyAll", r -> true, r -> false)
            ))
        );
        System.out.println(decide(new Request("GET", "/api/reports/7", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("GET", "/api/reports/7", true,
            Set.of()), chains));
        System.out.println(decide(new Request("POST", "/api/reports/7", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("POST", "/api/reports/7", true,
            Set.of("report:write")), chains));
        System.out.println(decide(new Request("GET", "/api/unknown", true,
            Set.of("report:read")), chains));
        System.out.println(decide(new Request("GET", "/health", false,
            Set.of()), chains));
        System.out.println(decide(new Request("GET", "/profile", true,
            Set.of("report:read")), chains));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên, trong thư mục chứa file:

~~~bash
javac --release 17 ChainSelectionDemo.java
java ChainSelectionDemo
~~~

**Stdout chính xác (đã kiểm chứng):**

~~~text
api / GET report:read -> ALLOW
api / GET report:read -> DENY
api / POST report:write -> DENY
api / POST report:write -> ALLOW
api / api denyAll -> DENY
fallback / health permitAll -> ALLOW
fallback / fallback denyAll -> DENY
~~~

Điều cần quan sát:

1. Cả bốn request đầu tiên cùng dùng `api` chain, nhưng kết quả khác nhau vì authority và HTTP method.
2. `GET /api/unknown` vẫn chọn `api` chain; vì không khớp rule báo cáo, nó bị `api denyAll`. **Nó không quay sang fallback**.
3. `GET /health` không khớp selector của `api`, nên chọn `fallback` và được mở bằng rule `health permitAll`.
4. `GET /profile` cũng chọn fallback, nhưng gặp `fallback denyAll`.
5. Các predicate trong demo dùng `startsWith` đơn giản; Spring Security ngoài đời dùng `RequestMatcher` và quy tắc path matching tùy ngữ cảnh. Không dùng đoạn mã mô phỏng làm security engine production.

Nếu xoá chain fallback trong mô hình, những request ngoài `/api/**` sẽ trả `NO CHAIN MATCHED`. Đó là điểm cần cảnh giác khi cấu hình securityMatcher giới hạn phạm vi trong Spring Security.

## 10. Cách kiểm thử để chứng minh selector không thay rule

Với Spring MVC, thường dùng `MockMvc` cùng `spring-security-test` và security filter chain thật để kiểm thử. Không chỉ test mỗi một user có quyền; cần kiểm tra **cả cặp (chain, rule)** và các trường hợp từ chối.

### 10.1. Ma trận test cốt lõi

| Test | Đường vào | Quyền giả lập | Dự kiến |
| --- | --- | --- | --- |
| Chain API chọn đúng | GET `/api/reports/7` | `report:read` | Qua HTTP authorization của API chain |
| Rule API chặn thiếu quyền | GET `/api/reports/7` | User đã xác thực nhưng không có `report:read` | Bị từ chối |
| Phân biệt method | POST `/api/reports/7` | Chỉ có `report:read` | Bị từ chối |
| Rule theo POST | POST `/api/reports/7` | `report:write` | Qua authorization; test CSRF/side effect riêng |
| Không có rule API | DELETE `/api/reports/7` | User có read/write | Bị `denyAll` |
| Fallback public | GET `/health` | Anonymous | Qua `permitAll` |
| Fallback deny | GET `/profile` | User đã xác thực | Bị `denyAll` |
| Selector ngoài scope | GET `/admin` | Admin | Không được chuỗi API chọn; fallback quyết định |
| Đường cụ thể và tổng quát | GET `/api/admin/users` | User thường | Chỉ chain phù hợp thứ tự mới quyết định, không “hạ” sang chain sau |
| Endpoint filter | POST login/callback | Tùy auth flow | Chỉ filter chain thực sự chọn path đó mới xử lý |
| Phạm vi không có fallback | GET `/unknown` | Anonymous | Phát hiện request không được chain nào bảo vệ |

Cần chuẩn bị controller/route mẫu và user store/test principal phù hợp. Với request POST/PUT/DELETE, thêm CSRF token trong test **nếu cấu hình dùng CSRF**, để phân biệt lỗi CSRF với lỗi authorization. Với authentication HTTP Basic cần dùng request helper hoặc header thực tế nếu kiểm thử cơ chế này.

### 10.2. Một số assertion nên có

- Verify route được chọn thuộc chain nào, đặc biệt khi có nhiều `@Order` và selector lồng nhau.
- Verify rule khớp trong chain đầu **không rơi sang chain thứ hai** khi quyền thất bại.
- Test tài nguyên không tồn tại, resource khác tenant/owner, và các HTTP method chưa khai báo. Rule URL không thay được kiểm tra business.
- Kiểm tra không có side effect khi request bị deny: dữ liệu DB không cập nhật, event không phát, response không lộ dữ liệu.
- Verify các endpoint do filter tạo: login, logout, OAuth2 callback; tránh chỉ kiểm thử controller.
- Kiểm tra các route công khai cố ý như health/static vẫn đi qua chain phù hợp và được `permitAll`, thay vì vô tình không khớp chain nào.
- Khi sửa selector, dùng regression test cho toàn bộ route chính và route dự phòng; khi sửa rule, test boundary giữa quyền các vai trò.

Một test chỉ thấy HTTP 200 hoặc 403 **chưa đủ** để biết lý do thực: 403 có thể đến từ CSRF hoặc method policy; 200 có thể do endpoint vô tình nằm ngoài Spring Security. Kết hợp assertion response, log chọn chain và thử nghiệm thay authority.

## 11. Debug khi request đi vào sai chuỗi hoặc đúng chuỗi nhưng sai quyền

Quy trình theo thứ tự:

1. **Xác nhận path và method thực tế** đến server. Xem context path, servlet path, reverse proxy rewrite, tiền tố version API và HTTP method. Đường dẫn giả định sai làm matcher không khớp.
2. **Liệt kê `SecurityFilterChain` theo thứ tự `@Order`**, selector thực tế của từng chain. Xác định chuỗi đầu tiên khớp request. Đừng suy đoán chỉ từ tên bean.
3. **Xem cấu hình bên trong chuỗi được chọn**: `authorizeHttpRequests` đã khai báo chưa, thứ tự `requestMatchers`, fallback `anyRequest`, `hasRole` so với `hasAuthority`, nơi gắn `permitAll`/`denyAll`.
4. **Kiểm tra principal và authorities** sau xác thực: `hasRole("ADMIN")` mặc định tìm `ROLE_ADMIN`; `hasAuthority("report:read")` khớp chính xác chuỗi `report:read`.
5. **Phân loại nguồn từ chối**: thiếu xác thực, thiếu quyền, CSRF, method security, business policy hay controller không tồn tại; mỗi nguồn có cách sửa khác nhau.
6. **Bật log an toàn trong môi trường phát triển** khi cần, ví dụ `logging.level.org.springframework.security=DEBUG`; thông điệp `FilterChainProxy` và filter authorization có thể giúp xác định đường đi. Không bật log nhạy cảm hoặc ghi token/password trong production.
7. **Chạy lại ma trận test** sau khi thay selector hoặc rule; đặc biệt thử request thuộc hai selector lồng nhau, request ngoài mọi selector và endpoint authentication callback.

Có thể dùng test tích hợp để quan sát request qua filter chain thật. Không nên giả lập trực tiếp `AuthorizationManager` rồi kết luận rằng thứ tự các chain là đúng: unit test quyết định quyền **không thay thế** test chọn chain.

## 12. Những nhầm lẫn phổ biến và cách sửa

| Nhầm lẫn | Vì sao sai | Cách sửa |
| --- | --- | --- |
| “Có `securityMatcher("/api/**")` là API đã yêu cầu đăng nhập” | Selector chỉ chọn chuỗi | Khai báo `authorizeHttpRequests` với `authenticated`/authority/deny rõ ràng |
| “`requestMatchers("/admin/**")` trong API chain sẽ tự bảo vệ `/admin/**`” | `/admin/**` nằm ngoài selector của chain | Đặt rule trong chain phù hợp hoặc đổi selector một cách có chủ đích |
| “`anyRequest().denyAll()` trong API chain bảo vệ mọi route” | `anyRequest` chỉ xét những request đã vào API chain | Thêm fallback chain cho các request khác |
| “Bị deny ở chain thứ nhất thì Spring thử chain sau” | Chỉ thử chain sau **khi selector không khớp** | Sửa rule của chain được chọn, không dựa vào fallthrough |
| “Chain `/api/admin/**` có @Order sau `/api/**` vẫn bảo vệ admin” | Chuỗi tổng quát bắt request trước | Đưa selector cụ thể lên trước |
| “Đặt rule `/api/**` trước rule `/api/admin/**` không sao” | Rule rộng bắt request trước | Đặt rule chi tiết trước và fallback cuối |
| “`permitAll` là hoàn toàn bỏ qua security filters” | Đây chỉ là rule cấp phép | Để request qua chain khi cần headers/CSRF/context |
| “Có `httpBasic` hoặc `formLogin` nên mặc nhiên có URL authorization đúng” | Authentication và authorization là hai trách nhiệm | Chỉ định rõ chính sách authorization cho từng phạm vi |
| “Đã qua URL rule thì được đọc mọi bản ghi” | Quyền trên URL chưa đủ cho ownership/tenant | Dùng domain/method/repository policy per-resource |
| “POST có authority đúng mà 403 tức là matcher sai” | Có thể là CSRF hay rule khác | Xem security flow và test với CSRF đúng |
| “Request ngoài mọi chain chắc chắn được bảo vệ bằng default” | Không có fallback thì không có chain khớp | Cấu hình catch-all theo chính sách và test |

## 13. Checklist khi review một cấu hình nhiều chain

- [ ] Mỗi `SecurityFilterChain` có phạm vi selector được mô tả rõ, đúng thứ tự ưu tiên.
- [ ] Có chain fallback bảo vệ các request không được các chain chuyên biệt nhận.
- [ ] Các selector lồng nhau được xếp từ cụ thể tới tổng quát.
- [ ] Mỗi chain có `authorizeHttpRequests` hoặc cơ chế authorization được chủ động thiết kế và kiểm chứng.
- [ ] Rule nội bộ chỉ nhắm tới request có thể đi vào chain của nó.
- [ ] Rule từ cụ thể tới tổng quát, kết thúc bằng `anyRequest` phù hợp.
- [ ] Những route chưa khai báo không được cấp quyền tình cờ.
- [ ] Phân biệt rõ `permitAll`, `authenticated`, `hasRole`, `hasAuthority`, `denyAll`.
- [ ] Login/logout/callback mà filter cung cấp có đường dẫn nằm trong chuỗi đúng.
- [ ] CSRF, session, HTTP Basic/JWT và filter set được xem xét theo từng chain.
- [ ] Có test chứng minh việc thay selector không lách được rule và thay rule không để endpoint rơi ra ngoài mọi chain.
- [ ] Có kiểm tra quyền nghiệp vụ trên bản ghi nếu chỉ kiểm tra URL là chưa đủ.

### Câu hỏi tự kiểm tra

**Câu 1.** Một chuỗi có `securityMatcher("/api/**")` và `authorizeHttpRequests(auth -> auth.anyRequest().authenticated())`. Request `GET /admin` có bị rule `authenticated()` này chặn không?

**Trả lời:** Không. `/admin` không vào chuỗi `/api/**`, nên `anyRequest()` ở chuỗi đó không được xét. Kết quả phụ thuộc chain khác; nếu không chain nào khớp, request không được Spring Security filter chains bảo vệ.

**Câu 2.** Có hai chuỗi `@Order(1) /api/**` và `@Order(2) /api/admin/**`. Request `/api/admin/users` chọn chuỗi nào?

**Trả lời:** Chuỗi `/api/**` ở `@Order(1)` khớp trước, nên được chọn. Chuỗi admin phía sau không được dùng. Sửa bằng cách đặt selector admin lên trước.

**Câu 3.** Với `securityMatcher("/api/**")`, thêm `requestMatchers("/api/reports/**").hasAuthority("report:read")` đã đủ bảo vệ các endpoint còn lại của API chưa?

**Trả lời:** Chưa thể kết luận. Phải xem **rule cuối** của chuỗi: `anyRequest().denyAll()` chặn các endpoint khác; `authenticated()` mở chúng cho mọi người đã đăng nhập; thiếu authorization policy có thể để lọt hành vi không mong muốn.

**Thông điệp chính:** `securityMatcher` định tuyến request đến **bộ lọc bảo mật nào**; `requestMatchers` và `anyRequest` bên trong `authorizeHttpRequests` quyết định **request thuộc chuỗi đó cần quyền gì**. Hãy bảo vệ cả **phạm vi lựa chọn chuỗi** lẫn **các rule phân quyền trong chuỗi**, đồng thời có fallback cho request chưa được chuỗi chuyên biệt nhận.

### Tài liệu tham khảo chính thức

- Spring Security — Java Configuration, Multiple HttpSecurity Instances và Choosing securityMatcher or requestMatchers: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security — Authorize HttpServletRequests, Security Matchers: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Security — Architecture / Security Filters: https://docs.spring.io/spring-security/reference/servlet/architecture.html
