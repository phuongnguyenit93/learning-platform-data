# Lưu yêu cầu trước đăng nhập và chọn địa chỉ quay lại an toàn

> **Phạm vi:** Spring Security fundamentals → **Đăng nhập và đăng xuất**. Bài này giải thích cách Spring Security ghi nhớ một tài nguyên mà người dùng muốn truy cập **trước khi đăng nhập**, đưa họ trở lại sau khi xác thực thành công, và cách kiểm soát **địa chỉ redirect** để tránh open redirect, lộ thông tin, login loop hoặc quay về sai vị trí. Ví dụ chính dùng **Spring MVC / Servlet, Spring Boot 3.x, Spring Security 6.x và Java 17+**; WebFlux, API stateless và SSO được so sánh ở mức kiến trúc.

## 1. Bài toán: đăng nhập xong, người dùng muốn quay lại đâu?

Một người dùng chưa đăng nhập bấm một liên kết tới báo cáo riêng tư:

```text
GET /reports/7?view=summary
```

Ứng dụng yêu cầu authentication. Browser được chuyển đến `/login`. Sau khi người dùng nhập đúng username/password, trải nghiệm mong muốn là trở lại **`/reports/7?view=summary`**, không phải luôn rơi vào trang chủ. Nhưng nếu người dùng mở thẳng `/login` từ menu và đăng nhập, không có tài nguyên đã yêu cầu trước đó, ứng dụng nên về **`/dashboard`**.

Hai kịch bản:

```text
A. Deep link vào trang cần xác thực

Browser
  ├─ GET /reports/7?view=summary
  ├─ Spring Security nhận thấy chưa đăng nhập
  │    ├─ lưu yêu cầu ban đầu trong RequestCache
  │    └─ redirect /login
  ├─ POST /login với credentials + CSRF token
  ├─ đăng nhập thành công
  ├─ success handler lấy SavedRequest
  ├─ redirect tới URL ban đầu
  └─ GET /reports/7?view=summary với session đã xác thực


B. Chủ động mở trang đăng nhập

Browser
  ├─ GET /login
  ├─ POST /login với credentials + CSRF token
  ├─ đăng nhập thành công; không có SavedRequest
  └─ redirect tới /dashboard (fallback an toàn)
```

Điều quan trọng: **URL quay lại sau login là một quyết định điều hướng, không phải quyết định cấp quyền**. Sau redirect, request tới báo cáo vẫn phải đi qua HTTP authorization, method security và object/tenant-level authorization. Một URL được lưu trước login không được phép cấp quyền đọc báo cáo của người khác.

### 1.1. Yêu cầu chức năng và bảo mật

1. Nhớ **đúng đích ban đầu** khi người dùng mở deep link cần xác thực.
2. Giữ những phần URL cần cho điều hướng như path/query trong giới hạn chính sách, không vô tình bỏ tham số trang.
3. Nếu không có yêu cầu được lưu, sử dụng đích mặc định đã biết, ví dụ `/dashboard`.
4. Không lấy chuỗi từ `?next=`, `?returnUrl=`, body hoặc `Referer` rồi đưa thẳng vào HTTP `Location`.
5. Không chuyển người dùng tới host ngoài ý muốn, kể cả thông qua URL dạng `//host` hoặc giá trị mã hóa.
6. Không tự động lặp lại thao tác ghi (POST/PUT/DELETE) chỉ vì người dùng đã đăng nhập.
7. Không để saved request cũ, tab khác, login thất bại, session hết hạn hay logout gây redirect lạc chỗ.
8. Có integration test cho cả đường được phép và đường bị từ chối, không chỉ kiểm tra “login 200”.

## 2. Các thành phần Spring Security cần phân biệt

| Thành phần | Vai trò |
|---|---|
| `ExceptionTranslationFilter` | Khi request gặp tình huống cần bắt đầu authentication, có thể yêu cầu `RequestCache` lưu request rồi gọi `AuthenticationEntryPoint` |
| `AuthenticationEntryPoint` | Bắt đầu quá trình xác thực; với form login thường redirect tới `/login` |
| `RequestCache` | Hợp đồng lưu, tìm và xóa request đã được bảo vệ |
| `HttpSessionRequestCache` | Một hiện thực mặc định thông dụng của `RequestCache` trên Servlet, dùng `HttpSession` |
| `SavedRequest` / `DefaultSavedRequest` | Dữ liệu mô tả yêu cầu HTTP ban đầu, bao gồm URL/headers/parameters cần cho việc tiếp tục |
| `SavedRequestAwareAuthenticationSuccessHandler` | Sau khi xác thực thành công, cân nhắc saved request để xác định URL redirect |
| `RequestCacheAwareFilter` | Khi request quay lại sau redirect, phối hợp với cache để khôi phục/bao bọc thông tin request đã lưu theo cơ chế framework |
| `SimpleUrlAuthenticationSuccessHandler` | Success handler cơ bản để chuyển tới một URL theo chính sách cấu hình |
| `HttpSecurity.formLogin` | Cấu hình authentication form, URL login và xử lý thành công/thất bại |
| `defaultSuccessUrl` | Đích fallback, hoặc đích bắt buộc nếu bật tùy chọn `alwaysUse` |

**Tên gần nhau không có nghĩa là cùng việc:** `RequestCache` lưu yêu cầu; `AuthenticationSuccessHandler` chọn đích sau login; `AuthenticationEntryPoint` đưa người dùng đi login trước đó; `SecurityFilterChain` bảo vệ các URL. Nếu custom một thành phần mà bỏ quên thành phần còn lại, hành vi trở về URL cũ có thể không còn đúng.

### 2.1. Khi nào một request được lưu?

Với form login theo cấu hình quen thuộc, một request **chưa được xác thực** tới URL cần authentication sẽ đi qua bảo vệ HTTP. `ExceptionTranslationFilter` có thể lưu request vào `RequestCache` rồi bắt đầu login. Request đến trang public thường không cần lưu vì không phát sinh yêu cầu authentication.

Việc lưu phụ thuộc **RequestCache được cấu hình**, session creation policy, matcher của cache, exception handling và loại authentication. Không phải mọi request tới `/login`, mọi lỗi 403, hay mọi API bearer-token đều tự trở thành một `SavedRequest`.

### 2.2. Saved request lưu trong session, không nằm nguyên ở query login

Với `HttpSessionRequestCache`, thông tin request có thể được lưu trong server-side `HttpSession` (tên attribute mặc định thường là `SPRING_SECURITY_SAVED_REQUEST`). Browser chỉ mang session cookie; không cần gửi nguyên `returnUrl` tới login form bằng cách nối chuỗi tùy ý.

Đây là **lợi ích thiết kế**, nhưng không phải bảo đảm tuyệt đối rằng URL lưu sẵn luôn an toàn: URL ban đầu vẫn chứa phần chịu ảnh hưởng của client, và deployment có thể có Host/forwarded-header sai. Cần kiểm tra host đáng tin, đường dẫn, proxy và URL redirect khi thiết kế ứng dụng thật.

### 2.3. Một phiên chỉ có một “yêu cầu đang lưu” theo cache thông dụng

Mặc định một `HttpSessionRequestCache` không phải một hàng đợi nhiều tab cho mọi thao tác người dùng. Khi tab A mở `/reports/7` và tab B mở `/profile` trước khi login trong cùng session, hành vi có thể khiến yêu cầu mới thay yêu cầu cũ. Không xây giả định “mỗi tab có một SavedRequest độc lập” nếu chưa thiết kế cơ chế tương ứng.

Nếu sản phẩm yêu cầu **multi-tab continuation**, hãy có UX và state riêng với thời hạn, định danh giao dịch, ràng buộc session, kiểm soát đầu vào và test tranh chấp; không cố dùng `HttpSessionRequestCache` như bộ nhớ vô hạn.

## 3. Luồng thực tế: trước login và sau login

Với Servlet, trình tự thường là:

```text
GET /reports/7?view=summary (anonymous)
    |
    v
SecurityFilterChain
    |
    v
Yêu cầu .authenticated() không thỏa
    |
    v
ExceptionTranslationFilter
    ├─ RequestCache.saveRequest(...)
    └─ AuthenticationEntryPoint → 302 /login
            |
            v
Browser GET /login
            |
            v
POST /login với username/password/CSRF token
            |
            +-- thất bại --> /login?error (không có authenticated session)
            |
            +-- thành công
                    |
                    v
             AuthenticationSuccessHandler
                    |
                    +-- Có SavedRequest?
                    |      |
                    |      +-- Có → redirect tới đích đã lưu
                    |      |
                    |      +-- Không → fallback /dashboard
                    |
                    v
             Browser gửi request mới tới đích
                    |
                    v
          HTTP + method + data authorization tiếp tục
```

Khi success handler chọn saved request, nó chuyển hướng browser tới URL. **Không được hiểu là server tự “phát lại” mọi side effect của request ban đầu.** Một HTTP 302 dẫn browser đi theo redirect, thường thành **GET**. Cơ chế saved request có thể khôi phục metadata trên request đến sau redirect thông qua wrapper/filter, nhưng không phải một cơ chế tự động gửi lại nội dung POST thanh toán hay nạp lại luồng upload tệp.

### 3.1. Query string có thể được bảo toàn, nhưng phải kiểm soát nội dung

Đích ban đầu `/reports/7?view=summary` có thể được lưu cùng query để quay về đúng tab báo cáo. Tuy vậy, **không nên đưa credential, access token, password reset token hoặc secret vào query string**: URL có thể bị lưu trong browser history, log proxy, analytics, Referer và saved request/session state.

Một số phiên bản Spring Security 6 dùng tham số đánh dấu `continue` cho `RequestCache` nhằm tránh truy cập session trên mọi request. URL sau login có thể kèm một query marker phục vụ cơ chế cache; test đích nên xét semantics path + query cần thiết thay vì ép mọi URL byte-for-byte giống ví dụ giấy. Xác minh chính xác bằng version/config của dự án.

### 3.2. Không có SavedRequest thì làm gì?

Nếu người dùng chủ động mở `/login`, hoặc request cache bị vô hiệu, hoặc login được khởi đầu bằng một luồng khác, success handler cần **đích mặc định ổn định**, ví dụ `/dashboard`. Không cố suy ra trang trước đó từ `Referer` nếu không có chính sách và xác minh an toàn: header này có thể thiếu, giả hoặc trỏ ra ngoài origin.

Một URL fallback phải thật sự tồn tại và user được phép truy cập; nếu cấu hình fallback trỏ vào endpoint yêu cầu quyền mà người đăng nhập không có, người dùng có thể gặp 403 hoặc vòng redirect khó hiểu.

## 4. `SavedRequestAwareAuthenticationSuccessHandler` chọn URL như thế nào?

Theo API Spring Security 6, các nhánh cần nhớ khi authentication thành công:

1. **`alwaysUseDefaultTargetUrl = true`:** luôn dùng đích mặc định được cấu hình và loại saved request có liên quan.
2. **`targetUrlParameter` được cấu hình và request chứa tham số tương ứng có nội dung:** success handler cơ sở có thể sử dụng đích do tham số cung cấp, đồng thời bỏ saved request. **Điều này đặc biệt nguy hiểm nếu tham số chưa được ràng buộc, vì có thể tạo open redirect.**
3. **Có `SavedRequest` hợp lệ trong `RequestCache`:** dùng URL của yêu cầu đã lưu để redirect; bản ghi saved request có thể tạm còn trong cache để `RequestCacheAwareFilter` xử lý khi browser quay về.
4. **Không có saved request:** trở về logic của handler cơ sở, thường là đích fallback.

Bảng lựa chọn:

| Tình huống | Cấu hình | Đích dự kiến |
|---|---|---|
| Mở báo cáo riêng trước login | `defaultSuccessUrl("/dashboard", false)` | URL báo cáo đã lưu |
| Mở trực tiếp `/login` | `defaultSuccessUrl("/dashboard", false)` | `/dashboard` |
| Mở báo cáo riêng nhưng cấu hình luôn ưu tiên default | `defaultSuccessUrl("/dashboard", true)` | `/dashboard`, bỏ qua saved request |
| Custom `successHandler` luôn gửi `/home` | Handler do lập trình viên viết | `/home`; có thể vô tình bỏ luồng SavedRequest |
| Cấu hình `targetUrlParameter("next")` nhưng không kiểm soát `next` | User có thể tự gán URL | Nguy cơ open redirect |
| RequestCache bị tắt bằng `NullRequestCache` | Không lưu request cũ | Fallback hoặc logic khác của handler |

**Ghi nhớ đặc biệt:** `defaultSuccessUrl("/dashboard", false)` không đồng nghĩa “luôn redirect dashboard”. Boolean `false` nghĩa là **không bắt buộc dùng đích mặc định** khi trước đó có saved request. Với `true`, deep link có thể bị bỏ qua.

Đừng tự đồng nhất `targetUrlParameter` với `matchingRequestParameterName` của `HttpSessionRequestCache`. Một tham số dùng để **chọn target URL do request cung cấp**; tham số còn lại có thể là **marker điều khiển lúc nào kiểm tra saved request**. Chúng không có cùng semantics an toàn.

## 5. Ví dụ chạy được: Spring Boot 3.x, Java 17+, form login

Bài mẫu này có:
- Một route public `GET /public/ping`.
- Một route cần authentication `GET /reports/{id}?view=...`.
- Một route fallback `GET /dashboard`.
- Login mặc định của Spring Security.
- `defaultSuccessUrl("/dashboard", false)` để ưu tiên saved request nếu có.
- Một bộ integration test kiểm chứng deep link, login trực tiếp và tham số redirect giả mạo.

Mục tiêu là **hiểu request cache và đích điều hướng**; ví dụ không có database và chưa có rule owner/tenant cho từng báo cáo. Trong production cần bổ sung kiểm tra quyền object ở service/repository.

### 5.1. Tạo project Gradle

Từ Spring Initializr tạo project Java 17+, Spring Boot 3.x, chọn **Spring Web** và **Spring Security**. Trong `build.gradle` do Initializr tạo, bảo đảm khối:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Đây **chỉ là khối dependencies**: giữ plugins, repositories và các phần còn lại từ project đã tạo.

### 5.2. Một tệp Java cho ứng dụng

Tạo `src/main/java/example/savedrequest/SavedRequestDemoApplication.java`:

```java
package example.savedrequest;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class SavedRequestDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavedRequestDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/reports/*").authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/dashboard").authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form
                .permitAll()
                .defaultSuccessUrl("/dashboard", false))
            .build();
    }

    @Bean
    UserDetailsService demoUsers() {
        UserDetails user = User.withUsername("alice")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }
}

@RestController
class PageController {

    @GetMapping("/public/ping")
    public String ping() {
        return "ok";
    }

    @GetMapping("/dashboard")
    public String dashboard(Authentication authentication) {
        return "dashboard for " + authentication.getName();
    }

    @GetMapping("/reports/{id}")
    public Map<String, String> report(
            @PathVariable long id,
            @RequestParam(defaultValue = "summary") String view,
            Authentication authentication) {
        return Map.of(
            "reportId", Long.toString(id),
            "view", view,
            "username", authentication.getName());
    }
}
```

**Cấu trúc Java:** Tệp có một public class trùng tên file và một top-level controller class package-private cùng package. Controller được Spring Boot component-scan khi chạy; Spring Security nhận authentication từ session form login. `{noop}` **không hash mật khẩu** và chỉ chấp nhận trong demo cục bộ, không dùng cho production.

Trong cấu hình:

1. `/public/**` public.
2. `GET /reports/*` và `GET /dashboard` yêu cầu đăng nhập; các route chưa khai báo bị `denyAll`.
3. `formLogin(...).permitAll()` cho phép truy cập các endpoint phục vụ login được Spring Security cấu hình, kể cả `POST /login`; framework cung cấp login page mặc định khi không khai báo trang custom.
4. `defaultSuccessUrl("/dashboard", false)` cho phép sau login dùng `SavedRequestAwareAuthenticationSuccessHandler` để ưu tiên một request đã được lưu, nếu không có thì trở về dashboard.
5. Bài không thêm `targetUrlParameter("next")` và **không tự đọc `next` để redirect**.

**Không tắt CSRF**: `POST /login` cần CSRF token hợp lệ khi protection được bật. Integration test sẽ sử dụng `csrf()` từ `spring-security-test`.

### 5.3. Chạy thủ công

Trong project có Gradle Wrapper, chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Mở cửa sổ browser mới hoặc private tab tại:

```text
http://localhost:8080/reports/7?view=summary
```

Khi chưa đăng nhập, ứng dụng sẽ hướng đến form login. Đăng nhập bằng `alice / demo123`. Sau login thành công, browser được hướng về URL báo cáo đã yêu cầu (có thể kèm marker `continue` tùy phiên bản). JSON dự kiến chứa:

```json
{
  "reportId": "7",
  "view": "summary",
  "username": "alice"
}
```

Nếu mở trực tiếp `http://localhost:8080/login` trước khi có saved request, đăng nhập sẽ chuyển về `/dashboard` với body:

```text
dashboard for alice
```

**Không coi đây là test phân quyền trên báo cáo:** Bất kỳ user nào đã xác thực đều qua rule `authenticated()` trong demo. Ứng dụng thật phải quyết định user có quyền xem **báo cáo số 7** không.

## 6. Integration test kiểm chứng đích quay lại và open redirect

Tạo `src/test/java/example/savedrequest/SavedRequestDemoTest.java`:

```java
package example.savedrequest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class SavedRequestDemoTest {

    @Autowired
    MockMvc mvc;

    @Test
    void savedDeepLinkWinsOverFallback() throws Exception {
        // GET vào trang yêu cầu đăng nhập.
        MvcResult entry = mvc.perform(
                get("/reports/7").param("view", "summary"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"))
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) entry.getRequest().getSession(false);
        assertThat(session).isNotNull();

        // POST login giữ cùng anonymous session chứa SavedRequest.
        MvcResult login = mvc.perform(
                post("/login")
                    .session(session)
                    .with(csrf())
                    .param("username", "alice")
                    .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        String target = login.getResponse().getRedirectedUrl();
        assertThat(target).isNotNull();
        assertThat(target).contains("/reports/7");
        assertThat(target).contains("view=summary");

        // Session có thể được rotate ID khi authentication thành công.
        MockHttpSession authenticatedSession =
            (MockHttpSession) login.getRequest().getSession(false);

        mvc.perform(get("/reports/7")
                .param("view", "summary")
                .session(authenticatedSession))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"))
            .andExpect(jsonPath("$.reportId").value("7"))
            .andExpect(jsonPath("$.view").value("summary"));
    }

    @Test
    void directLoginUsesKnownLocalFallback() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void untrustedNextParameterIsIgnoredByThisConfig()
            throws Exception {
        // Không có targetUrlParameter: user input không được
        // tự động biến thành redirect đích.
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "demo123")
                .param("next", "https://attacker.example/collect"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/dashboard"));
    }

    @Test
    void anonymousDoesNotGetReportDirectly() throws Exception {
        mvc.perform(get("/reports/7"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrlPattern("**/login"));
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**Giải thích cách test:**

- Test đầu đi qua Spring Security filter chain thực, vì thế `ExceptionTranslationFilter` và `RequestCache` có cơ hội lưu request trước login.
- Cùng một `MockHttpSession` được truyền vào POST login; nếu tạo session khác, handler có thể không thấy saved request và test về sai dashboard.
- `csrf()` giúp POST login hợp lệ thay vì bị CSRF filter từ chối trước khi authentication.
- Test cố tình chỉ khẳng định target **có đúng path và query nghiệp vụ**, không khẳng định URL byte-for-byte, để không phụ thuộc vào `continue` marker theo phiên bản.
- Test `next` xác nhận **cấu hình cụ thể trong ví dụ** bỏ qua tham số chưa tin cậy. Nó **không phải chứng minh tổng quát mọi custom handler đều an toàn**.
- Khi test với trình duyệt thật, phải kiểm tra cookie, context path và redirect chain. MockMvc không thay thế cho thử nghiệm HTTPS/forwarded headers ở gateway.

## 7. Open redirect: lỗi nguy hiểm khi tự chọn “return URL”

### 7.1. Vì sao open redirect là rủi ro?

Open redirect xảy ra khi ứng dụng chuyển hướng browser tới một URL do bên không đáng tin kiểm soát mà thiếu ràng buộc. URL ban đầu vẫn thuộc domain hợp lệ, vì thế kẻ xấu có thể dùng uy tín của domain đó để đưa nạn nhân tới trang phishing.

**Cách làm không an toàn** — chỉ để nhận diện, không dùng trong sản phẩm:

```java
@GetMapping("/after-login")
public void redirectUnsafe(
        @RequestParam String next,
        HttpServletResponse response) throws IOException {
    response.sendRedirect(next); // Không kiểm tra next!
}
```

Đoạn code trên **không phải chương trình hoàn chỉnh**. Nếu `next` nhận giá trị như `https://attacker.example/login`, HTTP response có thể trỏ browser ra ngoài. Đừng triển khai logic này hoặc dùng thẳng `request.getParameter("returnUrl")` trong success handler.

Ví dụ các giá trị cần nghi ngờ:

| Input | Tại sao nguy hiểm/không đáng tin |
|---|---|
| `https://attacker.example/phish` | URL tuyệt đối trỏ sang origin ngoài |
| `http://attacker.example/` | Chuyển tới host khác, hạ HTTPS nếu trình duyệt đi theo |
| `//attacker.example/path` | Scheme-relative URL dùng scheme hiện tại nhưng đổi host |
| `\\attacker.example` hoặc các biến thể backslash | Một số bộ phân tích URL/browser có thể chuẩn hóa khác nhau |
| `javascript:...`, `data:...` | Scheme không phù hợp với HTTP navigation an toàn |
| `%2F%2Fattacker.example` | Biến thể percent-encoded có thể trở thành `//` sau decode |
| `/logout?next=...` | Có thể gây chain redirect và thay đổi trạng thái |
| `/redirect?url=https://...` | Redirect gián tiếp vẫn có thể rời origin |
| String chứa CR/LF hoặc encoding bất thường | Rủi ro parser/response splitting nếu API xử lý sai |
| `Referer` không kiểm chứng | Header có thể không có hoặc không đáng tin cho quyết định điều hướng |

Không dùng phép thử ngây thơ `startsWith("/")` làm kết luận an toàn tuyệt đối: `//host` cũng bắt đầu bằng `/`; URL decoding nhiều lớp, dấu backslash, context path và proxy normalization có thể tạo sai khác giữa tầng kiểm tra và browser.

### 7.2. Thiết kế đơn giản và mạnh nhất: server-side allowlist

Thay vì chấp nhận URL tự do, nhận một **mã đích** hữu hạn do server định nghĩa. Ví dụ người dùng chọn “Dashboard” hoặc “Báo cáo” thông qua giá trị alias:

```java
// Utility Java 17+ độc lập; ví dụ code có thể biên dịch.
public final class ReturnDestination {
    private ReturnDestination() {}

    public static String fromAlias(String alias) {
        if ("report-seven".equals(alias)) {
            return "/reports/7";
        }
        // Bao gồm null, giá trị lạ, và URL tuyệt đối.
        return "/dashboard";
    }
}
```

Kết quả:

| Tham số | URL server duyệt |
|---|---|
| `report-seven` | `/reports/7` |
| `dashboard` | `/dashboard` |
| `https://attacker.example/` | `/dashboard` |
| `//attacker.example/` | `/dashboard` |
| `null` hoặc không có tham số | `/dashboard` |

**Đây mới là hàm chọn đích, chưa phải custom success handler.** Trong ứng dụng thật, nếu cần dùng alias tại login success, tích hợp nó với `AuthenticationSuccessHandler` theo thứ tự ưu tiên rõ ràng và vẫn phải tôn trọng kiểm tra quyền của endpoint đích. Không dùng giá trị `report-seven` cố định làm minh chứng rằng user có quyền với report 7.

Mức an toàn của allowlist tốt hơn validation regex cho URL tự do vì không cần giải thích mọi biến thể URL có thể tồn tại. Khi cần URL động, dùng một route identifier hoặc business object ID đã xác minh và xây URL **từ phía server**, ví dụ `"/reports/" + approvedReportId`; đừng nối trực tiếp phần path do client kiểm soát nếu có khả năng path traversal/URL parser confusion.

### 7.3. Nếu bắt buộc hỗ trợ URL ngoài origin?

Một số flow OIDC, federation hoặc ứng dụng đa domain có nhu cầu redirect tới domain khác. Khi đó cần một **danh sách origin và callback chính xác được phê duyệt**, đối chiếu URL đã parse/canonicalize theo scheme, host, port, path, không cho userinfo, không dùng wildcard hậu tố kiểu `endsWith("trusted.com")` (có thể khớp `eviltrusted.com`), không chấp nhận scheme không an toàn.

Đối với **OAuth2/OIDC redirect URI**, dùng cơ chế validation của authorization server/client theo chuẩn và danh sách callback đăng ký, không tự sáng tạo một `next` tùy ý như landing page. OAuth2 `state` và PKCE dùng cho mục đích khác; không coi đó là biện pháp thay thế allowlist redirect URI.

## 8. SavedRequest có mặc nhiên “đáng tin” không?

Saved request tốt hơn việc để user tự nhập `returnUrl` tại POST login vì nó gắn với request ban đầu trong session và được Spring Security quản lý. Tuy nhiên, đường đi ban đầu vẫn do HTTP client tạo ra, nên cần xem:

1. **Host header / forwarded headers:** URL tuyệt đối để redirect có thể dựa trên scheme/host/port từ request. Nếu proxy tin `Host` hoặc `X-Forwarded-Host` độc hại, URL được ghi lại có thể sai origin. Cần allowlist hostname tại edge, cấu hình trusted proxy chính xác, không tin forwarded headers từ Internet.
2. **Path có nội dung chưa tin:** Cho phép quay lại `/account/delete` hay một trang có side effect qua GET là thiết kế sai. GET phải safe/idempotent theo semantics; nếu không, URL quay lại có thể gây hành động không mong muốn.
3. **Query nhạy cảm:** SavedRequest có thể giữ một URL mang token/secret lộ qua redirect, browser history hoặc log; tránh truyền credential qua query.
4. **Đường dẫn không còn được phép:** User đã login nhưng thiếu quyền với tài nguyên thì vẫn nhận 403/404 khi redirect tới đó. SavedRequest không cấp quyền.
5. **Nhiều tab cùng session:** Saved request mới có thể thay saved request trước, tạo UX khác dự kiến.
6. **Session fixation:** Session chứa saved request phải được bảo vệ tại login; Spring Security thường đổi session ID khi authentication thành công. Không hủy fixation protection để “giữ lại yêu cầu cũ”.
7. **External link có chủ đích:** Một URL thuộc cùng origin nhưng đi qua endpoint open redirect khác vẫn có thể dẫn ra ngoài. Cần review các chuỗi redirect.
8. **Rò dữ liệu qua log/tracing:** Tránh log nguyên session cookie, Authorization header, query string nhạy cảm hoặc toàn bộ DefaultSavedRequest nếu chứa dữ liệu riêng tư.

**Thực hành nên có:** ghi nhận các host hợp lệ và kiểm tra chuỗi redirect end-to-end qua trình duyệt khi triển khai sau reverse proxy, không chỉ assert path bằng unit test.

## 9. Xử lý thứ tự ưu tiên khi có nhiều loại “địa chỉ quay lại”

Một ứng dụng có thể có bốn nguồn:

- Saved request từ một protected resource đã bị chặn vì chưa xác thực.
- Đích cố định sau login, ví dụ `/dashboard`.
- Đích do UI chọn (tab “Báo cáo”), dưới dạng **alias đã duyệt**.
- URL external callback ở một flow OAuth2/OIDC đã đăng ký.

Không nên để các nguồn cạnh tranh không có chính sách. Một thứ tự tham khảo:

```text
Authentication thành công
       |
       +-- Có saved request phù hợp/chính sách tin cậy?
       |      |
       |      +-- Có → tiếp tục tới protected route
       |
       +-- Có alias UI hợp lệ từ allowlist?
       |      |
       |      +-- Có → route cố định nội bộ
       |
       +-- Không → /dashboard
```

Tùy sản phẩm, alias có thể đứng trước saved request, nhưng phải quyết định **tường minh** và không cho tham số tùy ý của attacker ép đích external. Không sử dụng `Referer` làm nguồn ưu tiên chỉ vì tiện.

Trong Spring Security, gọi `formLogin(form -> form.successHandler(custom))` có thể **thay thế** handler SavedRequestAware mặc định. Nếu custom handler không đọc chung `RequestCache` hoặc không delegate đúng, deep link sẽ bị mất. Nếu chỉ muốn đổi fallback, **ưu tiên `defaultSuccessUrl("/dashboard", false)`**, vì đơn giản và giữ khả năng tiếp tục saved request.

### 9.1. Khi nào sử dụng `defaultSuccessUrl(..., true)`?

`true` có ích khi yêu cầu sản phẩm là “sau login luôn về một landing page”, chẳng hạn onboarding phải qua màn xác nhận bắt buộc. Nó **cố ý** bỏ qua SavedRequest. Không chọn `true` rồi kỳ vọng deep link trở về như cũ.

Nếu bắt buộc mọi user hoàn thành MFA/terms/onboarding trước khi truy cập tài nguyên, việc tiếp tục saved request phải phụ thuộc vào **trạng thái xác thực đầy đủ** và policy đã được thiết kế; không cho redirect sau xác thực một bước trở thành lối đi vòng điều kiện.

## 10. Điều gì xảy ra với POST/PUT/PATCH/DELETE trước login?

**Câu hỏi quan trọng:** “Người dùng đang gửi đơn hàng, session hết hạn, ứng dụng yêu cầu login, sau đó có tự gửi lại đơn hàng không?”

Không được giả định thế. Một redirect HTTP là một bước điều hướng, không phải cơ chế idempotent retry mọi request.

- `302`/`303` thường làm browser chuyển đến một GET của địa chỉ đích. Không bảo đảm body POST ban đầu được gửi lại.
- `307`/`308` có semantics bảo toàn method/body khác, và **không nên được dùng tùy tiện để “phát lại” một thao tác tài chính** sau login.
- `SavedRequest` có thể lưu thông tin về request, nhưng không biến `POST /checkout` thành quy trình giao dịch an toàn “resume transaction”.
- Kết quả sau login phải kiểm tra lại CSRF, quyền, trạng thái đơn, idempotency key và business invariants.
- Với thao tác ghi đang thực hiện dở, giải pháp UX thường là **lưu bản nháp phía server với mã tham chiếu**, xác thực xong đưa user về trang review/confirm và yêu cầu xác nhận lại, không tự replay side effect.
- Với upload lớn, cần flow upload/resume riêng hoặc chính sách hết hạn; đừng lưu nguyên file body vào session chỉ để quay lại sau login.

Ví dụ luồng mua hàng an toàn:

```text
POST /checkout khi session hết hạn
    |
    v
Không tự thực hiện thanh toán
    |
    v
Lưu draft đơn hàng theo token/ngữ cảnh được bảo vệ
    |
    v
Login/MFA
    |
    v
GET /checkout/review?id=server-issued-draft-id
    |
    v
Kiểm tra quyền + CSRF + số dư + giá + idempotency
    |
    v
Người dùng xác nhận một lần
    |
    v
POST /checkout/confirm
```

Cần đánh giá riêng mức độ nhạy cảm của thông tin đã nhập, thời gian lưu draft, giới hạn truy cập và xử lý session đã hết hạn.

## 11. Bật, tắt và thu hẹp `RequestCache` có chủ đích

Ở ứng dụng form login, `HttpSessionRequestCache` thường hợp lý. Nhưng không phải route nào cũng nên được lưu, nhất là endpoints dành cho API client, polling, static assets hoặc health probes.

### 11.1. Cấu hình `RequestCache` riêng

Đoạn cấu hình minh họa đặt **trong một class configuration khác** hoặc thay bean ở ví dụ chính; **không phải chương trình Java độc lập**:

```java
@Bean
SecurityFilterChain configuredCache(HttpSecurity http) throws Exception {
    HttpSessionRequestCache cache = new HttpSessionRequestCache();

    // Chỉ lưu GET thuộc nhóm báo cáo. Tránh ghi nhớ POST
    // có side effect hoặc một số route kỹ thuật.
    cache.setRequestMatcher(
        new AntPathRequestMatcher("/reports/**", "GET"));

    return http
        .requestCache(requestCache -> requestCache
            .requestCache(cache))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/reports/**").authenticated()
            .anyRequest().denyAll())
        .formLogin(form -> form
            .permitAll()
            .defaultSuccessUrl("/dashboard", false))
        .build();
}
```

Cần imports `HttpSessionRequestCache` và `AntPathRequestMatcher` thuộc Spring Security 6.x. Lưu ý trong các phiên bản Spring Security mới hơn, một số matcher API có thể deprecated hoặc khác; dùng matcher có semantics tương thích với project, hoặc viết `RequestMatcher` theo mục đích. **Đoạn này chỉ minh họa**, không thay ứng dụng chính vì `/dashboard` chưa được mở trong rule. Khi áp dụng thật, phải mở đúng fallback route và test. Các phiên bản/vị trí cấu hình cache có thể ảnh hưởng cả request saving và request matching.

Để không phụ thuộc vào pattern matcher cụ thể, một `RequestMatcher` tương đương dễ đọc là:

```java
RequestMatcher reportsGet = request ->
    "GET".equals(request.getMethod()) &&
    request.getServletPath().startsWith("/reports/");
cache.setRequestMatcher(reportsGet);
```

Đây là **một đoạn điều kiện tối giản**, không phải URL canonicalization policy hoàn chỉnh; kiểm tra context path, servlet mapping, trailing slash và deployment thực tế.

### 11.2. `continue` marker và Spring Security 6

Trong Spring Security 6, `HttpSessionRequestCache` có tùy chọn `matchingRequestParameterName`, thường là `continue`, để `getMatchingRequest` chỉ kiểm tra session khi URL chứa marker. Mục tiêu là **giảm số lần đọc session không cần thiết**. Với request cache đã lưu, redirect URL có thể được xây cùng marker theo version/config để trigger việc khôi phục trên lần GET tiếp theo.

Ví dụ một cấu hình tùy chỉnh rõ ràng:

```java
HttpSessionRequestCache cache = new HttpSessionRequestCache();
cache.setMatchingRequestParameterName("continue");
```

**Không nhầm:** `continue` marker không phải secret, không cấp quyền, không phải `next` hoặc token chống CSRF. Nó là tín hiệu tới request cache. Truy cập URL `?continue` không thể thay thế authentication và authorization. Khi có nhiều proxy/SPA router hoặc logic rewrite URL, phải đảm bảo marker không bị xóa sai hoặc bị hiểu là tham số nghiệp vụ.

### 11.3. `NullRequestCache` khi không muốn lưu request

Một số API dùng HTTP Basic, JWT bearer hoặc được thiết kế stateless sẽ **không muốn** tạo HttpSession chỉ để giữ deep link. Có thể dùng:

```java
.requestCache(cache -> cache
    .requestCache(new NullRequestCache()))
```

Đây là đoạn DSL đặt trong `HttpSecurity`; cần import `org.springframework.security.web.savedrequest.NullRequestCache`. Với JSON REST API, client thường xử lý 401 và tự tiếp tục navigation sau khi xác thực, chứ server không redirect qua form login.

Không dùng `NullRequestCache` cho toàn ứng dụng khi các trang web session-based còn yêu cầu quay lại deep link; nếu có nhiều `SecurityFilterChain`, thiết kế cache theo từng chain và auth mechanism.

## 12. WebFlux/reactive và SPA: cùng nhu cầu, API khác

Ví dụ runnable ở trên là **Servlet**: `HttpSecurity`, `HttpSessionRequestCache`, `SavedRequestAwareAuthenticationSuccessHandler`. Với WebFlux, Spring Security dùng `ServerHttpSecurity`, `SecurityWebFilterChain` và các thành phần request-cache/redirect tương ứng trên reactive stack, chẳng hạn `ServerRequestCache`; không chép trực tiếp Servlet `HttpServletRequest`/`HttpSession` sang `WebSession`.

Ở SPA có backend JSON hoặc OAuth2 login, việc “trở về màn hình cũ” có thể do client router quản lý. Nếu SPA lưu vị trí dự định trong `sessionStorage` hoặc URL state, nội dung đó vẫn là **dữ liệu do client kiểm soát**, phải ràng buộc route và tránh chuyển sang origin khác. Backend vẫn phải xác minh quyền cho API bất kể frontend quay về màn hình nào.

| Kiến trúc | Ai thường giữ trạng thái quay lại? | Vấn đề an toàn |
|---|---|---|
| Servlet form login + session | `HttpSessionRequestCache` trên server | Session cookie, saved URL, success handler, trusted host |
| Server-rendered app với SSO | Authentication success handler và framework OAuth2/OIDC state | Callback URI đăng ký, transaction binding, login success redirect |
| Spring WebFlux session app | `ServerRequestCache` / `WebSession` theo cấu hình | Reactive flow, WebSession, redirect policy |
| SPA + bearer-token JSON API | SPA router/state tùy thiết kế | Validate local route, không dùng open redirect, API phải authorize |
| API machine-to-machine | Thường không redirect browser | 401/403, retry semantics, token refresh và idempotency |

Với OAuth2/OIDC, **`redirect_uri`** là callback bảo mật của giao thức, khác với “đường dẫn UI muốn quay lại sau khi đã hoàn tất login”. Không cho client tùy ý đổi callback để tiện return navigation. Trong federation, dùng cơ chế state/authorization request repository và danh sách callback hợp lệ theo framework.

## 13. Các lỗi phổ biến khi triển khai

| Nhận định hoặc code | Hậu quả | Cách sửa |
|---|---|---|
| `formLogin(form -> form.defaultSuccessUrl("/dashboard", true))` rồi mong quay deep link | Saved request bị bỏ qua | Dùng `false` khi muốn ưu tiên saved request |
| Custom success handler luôn `sendRedirect("/home")` | Mất logic SavedRequest | Delegate đúng hoặc dùng cấu hình mặc định |
| `response.sendRedirect(request.getParameter("next"))` | Open redirect/phishing | Server-side allowlist hoặc alias |
| `startsWith("/")` là đủ để validate URL | Có thể nhận `//evil` và parser khác nhau | Ưu tiên alias; nếu dùng URL, canonicalize và check chặt |
| Bật `targetUrlParameter("next")` mà không xem trust boundary | User ép đích ngoài origin | Không bật nếu không cần; ràng buộc allowlist |
| Dùng `Referer` làm URL quay lại mặc định | Header thiếu hoặc giả | Dùng RequestCache hoặc fallback an toàn |
| Redirect sau login được xem như quyền xem dữ liệu | Lộ IDOR/BOLA | HTTP + method + object scope vẫn bắt buộc |
| Cho phép GET thực hiện thanh toán | Saved URL có thể kích hoạt side effect | GET an toàn, mutation bằng POST + CSRF/idempotency |
| Mong request cache tự replay POST body | Form/upload/transaction không được phục hồi an toàn | Draft/review/confirm có token chống trùng |
| Bắt buộc redirect exact URL trong test | Test fail do `continue` hoặc context path | Kiểm thử semantics path/query và policy |
| Test mở `/login` mà mong có saved request | Không hề đi qua protected URL | Test deep link trước, cùng session |
| Chạy nhiều browser tabs và tin mỗi tab có SavedRequest riêng | Quay về tab không đúng | Định nghĩa UX multi-tab/session state |
| Tắt CSRF để POST login test được | Giảm protection trên browser session | Dùng `csrf()` và config hợp lệ |
| Không cấu hình Host/proxy tin cậy | Saved absolute URL có thể sai origin | Allowlist host, trusted forwarded headers |
| Log nguyên URL có token/query nhạy cảm | Tiết lộ credential | Redaction, tránh token trong URL |
| Tắt request cache ở app form login | Mất deep link | Chỉ tắt ở API/chain không cần |
| Dùng URL external tự do cho SSO return | Redirect URI attack | Callback đăng ký cố định, state đúng chuẩn |

## 14. Ma trận test nên có trước khi release

Đối với một ứng dụng có user, route private và form login:

1. **Anonymous + deep link hợp lệ:** `GET /reports/7?view=summary` dẫn tới login, saved request được tạo, POST login thành công quay về báo cáo.
2. **Login trực tiếp:** không có saved request, login trả `/dashboard`.
3. **Credentials sai:** login thất bại không cho vào báo cáo; flow không được tự nâng quyền.
4. **Tham số redirect độc hại:** POST login với `next=https://attacker.example`, `next=//attacker.example`, encoded variants hoặc header Referer từ ngoài không gây redirect external.
5. **Query:** các tham số hợp lệ như view/sort/page được giữ đủ để mở đúng màn hình; không lưu secret.
6. **User không đủ quyền:** sau login, redirect vào tài nguyên ngoài scope phải bị service/DB chặn, không bị saved request “vượt cửa”.
7. **Login page custom:** có CSRF token, form action, username/password fields và save-request continuity đúng.
8. **Custom success handler:** có cả nhánh saved request, fallback và allowlisted alias, test thứ tự ưu tiên.
9. **HTTP method nhạy cảm:** POST/PUT/PATCH/DELETE không bị replay tự động gây side effect; file upload có recovery flow riêng.
10. **Multi-tab:** mở hai protected URLs trong cùng session trước login; hành vi được mô tả và test theo product requirement.
11. **Expired session:** saved request cũ không tồn tại hoặc không còn hợp lệ; redirect fallback hợp lý.
12. **Logout rồi login user khác:** saved request và dữ liệu liên quan không để lộ thông tin liên user.
13. **Session fixation:** session ID thay đổi sau login theo policy; không dùng ID anonymous cũ để vào private route.
14. **Trusted host/proxy:** ở stage sau gateway, Location header đúng HTTPS host chính thức, không nhận domain do Host/forwarded headers bị giả.
15. **Nhiều security chains:** chain nào redirect form, chain nào trả 401 JSON, request cache nào bật/tắt; không lẫn hai cơ chế.
16. **CORS/CSRF:** browser navigation khác JSON client; không “sửa lỗi redirect” bằng cách mở sai matcher hoặc vô hiệu exploit protection.

Những bài test âm tính (unsafe target, sai quyền, session khác, side effect không lặp) thường quan trọng ngang hoặc hơn happy path “login rồi về đúng trang”.

## 15. Checklist code review cho URL quay lại

- [ ] Đã xác định authentication mechanism: form session, OAuth2/OIDC, WebFlux, stateless SPA/API?
- [ ] Protected URL đi qua filter chain và `ExceptionTranslationFilter`/request cache như dự kiến?
- [ ] `defaultSuccessUrl` dùng `false` hay `true` có chủ đích, được kiểm thử?
- [ ] Custom `successHandler` có giữ/delegate chức năng SavedRequest không?
- [ ] Không gán trực tiếp `next`/`returnUrl`/`redirect`/`Referer` vào `Location`.
- [ ] Nếu cần do UI chọn đích, ưu tiên **server-side alias allowlist**.
- [ ] Nếu cần external callback, có allowlist origin/URI chính xác và cơ chế giao thức chuẩn.
- [ ] Host/forwarded headers được proxy tin cậy kiểm soát; không có Host header poisoning.
- [ ] Redirect sau login không thay thế authorization ở endpoint/dữ liệu.
- [ ] Không replay POST/PUT/DELETE hoặc upload bằng redirect; có draft/retry/idempotency rõ ràng nếu cần.
- [ ] Session/cookie và RequestCache còn hiệu lực qua login, session fixation protection không bị vô hiệu.
- [ ] Fallback route tồn tại, được người login hợp lệ phép truy cập và không tạo loop.
- [ ] SavedRequest không giữ query chứa token/secret, logging có redaction.
- [ ] Có test: deep link, direct login, malicious next, wrong owner, multi-tab, expired session, proxy.
- [ ] Đã kiểm thử production topology (TLS termination, ingress, context path, hostname).

## 16. Bài tập tự kiểm tra

**Bài 1.** User mở `/reports/7?view=summary` khi chưa xác thực; sau login ứng dụng dùng `defaultSuccessUrl("/dashboard", false)`. Đích nào được ưu tiên?

**Đáp án:** Khi `RequestCache` đã lưu đúng yêu cầu và success handler có thể dùng saved request, URL báo cáo ban đầu được ưu tiên. `/dashboard` chỉ là fallback.

**Bài 2.** Đổi `false` thành `true` trong `defaultSuccessUrl` thì sao?

**Đáp án:** Handler chọn `/dashboard` ngay cả khi có saved request; saved request liên quan bị bỏ qua/xóa theo semantics handler. Đó là lựa chọn UX chủ ý, không phải bug ngẫu nhiên.

**Bài 3.** Gán `response.sendRedirect(request.getParameter("next"))` sau login có rủi ro gì?

**Đáp án:** Open redirect nếu attacker truyền host ngoài hoặc biến thể mã hóa. Dùng alias allowlist hoặc route xây dựng từ phía server.

**Bài 4.** Có SavedRequest tới báo cáo của Bob, Alice login thành công. Alice có được nhận nội dung Bob?

**Đáp án:** Không chỉ vì được redirect. Backend vẫn phải kiểm tra quyền đọc object/tenant tại URL đích. SavedRequest không trao quyền.

**Bài 5.** Tại sao test POST login cần `csrf()`?

**Đáp án:** Khi session-based Spring Security bật CSRF protection, form POST cần token hợp lệ; nếu thiếu, request có thể bị 403 trước khi authentication, khiến test không thực sự kiểm tra return URL.

**Bài 6.** Tại sao không cho saved request tự retry POST thanh toán?

**Đáp án:** Redirect không có hợp đồng bảo đảm replay method/body an toàn, và tự lặp lại mutation có thể gây giao dịch trùng. Cần draft/review/confirm, CSRF và idempotency.

**Bài 7.** Trong Spring Security 6, thấy `?continue` sau redirect có phải bị tấn công không?

**Đáp án:** Không kết luận như vậy. Đây có thể là marker hợp lệ của `HttpSessionRequestCache` phục vụ lấy saved request. Nó không phải token quyền và không thay authentication. Cần đối chiếu cấu hình/version đang chạy.

**Bài 8.** Nếu muốn user chuyển về một trang do UI chọn, giải pháp nào giảm rủi ro URL parsing nhất?

**Đáp án:** Cho UI gửi một mã `dashboard`/`report-seven` hữu hạn; backend ánh xạ mã thành local route đã được phê duyệt. Không nhận đường dẫn arbitrary nếu không bắt buộc.

## 17. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet Architecture, Saving Requests Between Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `ExceptionTranslationFilter`, `RequestCache`, `RequestCacheAwareFilter` và cấu hình kiểm tra session có `continue`.
- [Spring Security 6.5 — SavedRequestAwareAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): thứ tự ưu tiên default target, target parameter, saved request và fallback.
- [Spring Security 6.5 — AbstractAuthenticationFilterConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/AbstractAuthenticationFilterConfigurer.html): semantics `defaultSuccessUrl(String, boolean)` và custom `successHandler`.
- [Spring Security 6.5 — FormLoginConfigurer API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/annotation/web/configurers/FormLoginConfigurer.html): form login, login processing URL và login page mặc định.
- [Spring Security — CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF trong browser session và kiểm thử.
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): cookies, session fixation protection, login flow.
- [OWASP — Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): rủi ro open redirect, allowlist đích.
- [OWASP — Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): bảo vệ thao tác thay đổi trạng thái.

**Kết luận:** Để giữ trải nghiệm deep link sau login, dùng `RequestCache` + `SavedRequestAwareAuthenticationSuccessHandler` theo mặc định trước khi viết custom logic. Cấu hình `defaultSuccessUrl("/dashboard", false)` khi cần ưu tiên request cũ và fallback an toàn. Tuyệt đối không biến `next`/`returnUrl` do client nhập thành HTTP redirect tùy ý; nếu cần lựa chọn đích, dùng server-side allowlist và bảo vệ quyền trên URL đích như mọi request thông thường.
