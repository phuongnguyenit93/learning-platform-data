# Phân biệt ngữ cảnh giả lập với dữ liệu được lưu qua nhiều request

Một test dùng `@WithMockUser(username = "lan")` có thể đọc được người dùng `lan` và gọi thành công một service được bảo vệ. Nhưng điều đó không chứng minh ứng dụng đã lưu phiên đăng nhập để request tiếp theo tiếp tục nhận ra `lan`. Danh tính giả lập trong test và security context được lưu qua nhiều HTTP request là hai cơ chế khác nhau.

Trong module **SPRING_SECURITY_TESTING**, bài học thuộc chương **Ngữ cảnh và vòng đời**, tập trung vào ranh giới giữa `SecurityContext` do test dựng, context được cấp riêng cho một request và context được lưu bởi `SecurityContextRepository`/session. Người học sẽ thực hành với `@WithMockUser`, request postprocessor `user(...)`, `MockMvc`, `formLogin()`, `MockHttpSession` và HTTP client kết nối server thật. Phần cuối đối chiếu mô hình session của Servlet với `WebSession` trong Reactive.

## 1. Ba kiểu trạng thái thường bị nhầm lẫn

Một ứng dụng Spring Security có thể làm việc với nhiều context ở các phạm vi khác nhau:

| Trạng thái | Được tạo bởi | Phạm vi | Mục đích |
| --- | --- | --- | --- |
| Test security context | `@WithMockUser`, `@WithAnonymousUser`, listener hoặc code test | Phương thức test và thread JUnit | Mô phỏng principal/authorities cho ca kiểm thử |
| Request security context | Security filter chain khi xử lý request | Một HTTP request | Cung cấp authentication cho filter, controller và authorization |
| Context được lưu qua request | `SecurityContextRepository`, thường gắn với HTTP session | Nhiều request của cùng client/session | Khôi phục danh tính đã xác thực cho request sau |

Có thể hình dung:

~~~text
Test method
  @WithMockUser("lan")
       │
       ▼
TestSecurityContextHolder
       │
       ▼
SecurityContextHolder trên thread JUnit
       │
       ├── MockMvc có thể được tích hợp để cấp context cho request giả lập
       │
       └── Không tự ghi context vào session của server thật

HTTP request 1
  Authorization / login credentials / session cookie
       │
       ▼
Security filter chain
       │
       ▼
SecurityContextRepository.loadContext(...)
       │
       ▼
SecurityContextHolder của request
       │
       ├── authentication thành công
       │
       └── lưu context nếu cơ chế xác thực/repository yêu cầu
                    │
                    ▼
             Session hoặc repository
                    │
                    ▼
HTTP request 2 gửi lại session cookie
                    │
                    ▼
SecurityContextRepository tải context đã lưu
~~~

Điểm cốt lõi: một đối tượng context tồn tại trong bộ nhớ của test không tự trở thành dữ liệu được lưu cho client. Để danh tính tồn tại qua nhiều request, ứng dụng phải có cơ chế lưu và khôi phục context, và client phải gửi thông tin liên kết tới trạng thái đã lưu, thường là session cookie.

## 2. @WithMockUser chỉ mô phỏng danh tính cho bài test

`@WithMockUser` là annotation của `spring-security-test`. `WithSecurityContextTestExecutionListener` tạo context giả lập trước khi phương thức test chạy, đặt authentication vào holder của test và dọn trạng thái khi test kết thúc.

~~~java
@Test
@WithMockUser(username = "lan", roles = "READER")
void testRunsAsLan() {
    Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

    assertThat(authentication.getName()).isEqualTo("lan");
    assertThat(authentication.getAuthorities())
            .extracting("authority")
            .contains("ROLE_READER");
}
~~~

Test này hữu ích để kiểm tra method security hoặc logic nghiệp vụ phụ thuộc principal. Nó không thực hiện:

- Gửi username/password tới endpoint đăng nhập.
- Chạy provider để kiểm tra mật khẩu.
- Tạo session đăng nhập như một người dùng thật.
- Ghi `SecurityContext` vào `HttpSessionSecurityContextRepository`.
- Tạo cookie `JSESSIONID` và gửi cookie đó tới server.
- Chứng minh request kế tiếp sẽ được xác thực mà không cấp lại danh tính.

Sau khi test kết thúc, listener dọn context của test. Việc đó giúp các test độc lập với nhau; nó cũng có nghĩa không thể dựa vào danh tính do annotation tạo để mô phỏng một phiên đăng nhập bền vững giữa các phương thức test.

Nếu muốn kiểm thử trạng thái đã lưu qua nhiều request, hãy chạy quy trình xác thực thật trong test: gửi login request hoặc credential/token theo cơ chế ứng dụng, giữ session/cookie/token do server phát hành, rồi gửi request tiếp theo bằng dữ liệu đó.

## 3. Request postprocessor user(...) cũng là danh tính giả lập theo request

Với `MockMvc`, `.with(user("lan"))` cấp một `Authentication` giả lập cho request cụ thể:

~~~java
mockMvc.perform(get("/api/profile")
        .with(user("lan").roles("READER")))
        .andExpect(status().isOk());
~~~

Tương tự, `.with(authentication(authentication))` hoặc `.with(testSecurityContext())` có thể cấp context giả lập vào request MockMvc. Các postprocessor này giúp kiểm tra authorization ở tầng HTTP mà không phải thực hiện đăng nhập thật.

Nếu test muốn gửi request khác với danh tính khác, hãy cấp danh tính rõ cho request đó:

~~~java
mockMvc.perform(get("/api/profile")
        .with(user("lan").roles("READER")))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/admin")
        .with(user("lan").roles("READER")))
        .andExpect(status().isForbidden());

mockMvc.perform(get("/api/admin")
        .with(user("mai").roles("ADMIN")))
        .andExpect(status().isOk());
~~~

Ví dụ giả định `/api/profile` cho phép `ROLE_READER`, `/api/admin` yêu cầu `ROLE_ADMIN`, MockMvc đã tích hợp security filter và endpoint trả status như kỳ vọng.

Đừng diễn giải `.with(user(...))` thành một lần đăng nhập. Nó tạo authentication phục vụ request giả lập. Nếu mục tiêu là chứng minh session được lưu và khôi phục, phải thực hiện một luồng login hoặc cơ chế xác thực có lưu context rồi tái sử dụng session.

## 4. SecurityContextRepository chịu trách nhiệm lưu và khôi phục context

Trên Servlet, `SecurityContextRepository` là abstraction mà Spring Security dùng để tải và lưu `SecurityContext`. Các implementation thường gặp:

| Repository | Cách hoạt động | Phạm vi phù hợp |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu context trong HTTP session và tải lại ở request sau | Ứng dụng stateful dùng session/cookie |
| `RequestAttributeSecurityContextRepository` | Lưu context trong request attribute để dùng trong phạm vi request/dispatch | Chia sẻ context trong cùng request, ví dụ dispatch/error |
| `NullSecurityContextRepository` | Không lưu context | Ứng dụng stateless hoặc cấu hình không cần persistence |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository | Kết hợp lưu request attribute và session theo cấu hình |

Trong cấu hình Servlet stateful thông thường, `HttpSessionSecurityContextRepository` thường là một phần của cơ chế lưu context. Client nhận session cookie, gửi lại trong request tiếp theo và server dùng session đó để tìm context.

Trong ứng dụng stateless, repository có thể là `NullSecurityContextRepository` hoặc session creation policy được cấu hình `STATELESS`. Khi đó, mỗi request phải mang thông tin xác thực riêng, ví dụ bearer token. Không nên kỳ vọng server tự nhớ người dùng từ request trước.

### Vai trò của SecurityContextHolderFilter

Các phiên bản Spring Security hiện hành dùng `SecurityContextHolderFilter` trong cấu hình phổ biến để tải context từ repository vào `SecurityContextHolder`. Filter này theo mô hình explicit save: việc đặt context trong holder không tự động bảo đảm context được lưu cho request sau. Cơ chế xác thực thành công tích hợp với Spring Security thường thực hiện việc lưu cần thiết; nếu ứng dụng tự viết filter và tự đặt authentication, phải hiểu rõ repository và gọi lưu context đúng lúc khi muốn persistence.

Ở các cấu hình/phiên bản cũ có `SecurityContextPersistenceFilter` với hành vi tự lưu khi request kết thúc. Không nên trộn giả định của hai mô hình. Khi kiểm thử custom authentication filter, xác định filter chain đang dùng cơ chế nào và kiểm tra việc gọi `SecurityContextRepository.saveContext(...)` có diễn ra hay không.

## 5. Kiểm thử persistence bằng MockMvc: đăng nhập thật rồi dùng lại session

Đây là ví dụ quan trọng để phân biệt danh tính giả lập với session được tạo qua quy trình login.

Giả định ứng dụng có:

- Form login tại `/login`.
- Người dùng `lan` với password dành riêng cho test.
- `SecurityContextRepository` lưu context trong HTTP session.
- `GET /api/profile` yêu cầu authentication.
- MockMvc được tích hợp Spring Security.

Test gửi form login, lấy session từ request đăng nhập thành công, rồi dùng session đó trong request kế tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionPersistenceMockMvcTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void successfulLoginIsReusedByNextRequest() throws Exception {
        MvcResult loginResult = mockMvc.perform(
                        formLogin()
                                .user("lan")
                                .password("correct-test-password"))
                .andExpect(authenticated().withUsername("lan"))
                .andReturn();

        MockHttpSession session =
                (MockHttpSession) loginResult.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mockMvc.perform(get("/api/profile").session(session))
                .andExpect(status().isOk())
                .andExpect(authenticated().withUsername("lan"));
    }
}
~~~

`formLogin()` gửi một request đăng nhập qua filter chain. Khi xác thực thành công và cấu hình session-based persistence, server lưu context trong session. Test lấy `MockHttpSession` của request đăng nhập và gắn session đó vào request tiếp theo. Lần thứ hai không dùng `@WithMockUser` hay `.with(user(...))`; danh tính được khôi phục từ session mà login đã tạo.

Đoạn code giả định endpoint, form login và test user đã được cấu hình trong ứng dụng. `formLogin()` có thể cần tùy chỉnh URL hoặc tên parameter nếu ứng dụng không dùng mặc định. Nếu bật CSRF, builder của Spring Security Test hỗ trợ form login request theo cơ chế test; hãy giữ CSRF bật nếu mục tiêu là kiểm thử cấu hình thật.

### Thêm ca không gửi lại session

Để chứng minh session mới là thứ giữ danh tính, gửi một request mới không có session:

~~~java
mockMvc.perform(get("/api/profile"))
        .andExpect(status().is3xxRedirection());
~~~

Với form login mặc định, request vô danh thường được redirect `302` tới trang đăng nhập. Nếu ứng dụng dùng HTTP Basic/custom entry point, có thể đổi assertion sang `401`. Mục tiêu của ca này là xác nhận một request độc lập không tự kế thừa authentication từ request login trước nếu không gửi session.

### Kiểm tra logout và session

Có thể kiểm tra logout qua filter chain, rồi xác minh request tiếp theo không còn được xác thực:

~~~java
mockMvc.perform(post("/logout").session(session).with(csrf()))
        .andExpect(status().is3xxRedirection());

mockMvc.perform(get("/api/profile"))
        .andExpect(status().is3xxRedirection());
~~~

Ví dụ giả định logout mặc định chuyển hướng và session bị vô hiệu hóa. Ứng dụng tùy chỉnh logout success handler có thể trả status khác. Hãy xác minh hành vi thực tế của ứng dụng thay vì cố định kỳ vọng theo ví dụ.

## 6. Session persistence không đồng nghĩa giữ một object Java trong test

`MockHttpSession` là session giả lập trong môi trường MockMvc. Nó giúp mô phỏng nhiều request cùng một session trong tiến trình test. Khi dùng server thật, client phải giữ cookie session mà server trả về.

Trên Servlet, cookie mặc định thường là `JSESSIONID`, nhưng tên cookie có thể thay đổi theo container và cấu hình. Với HTTP thật, luồng tổng quát là:

~~~text
POST /login
  Cookie: (chưa có)
  Body: username=lan&password=...
       │
       ▼
Server xác thực
       │
       ▼
Server tạo/lưu session và SecurityContext
       │
       ▼
Response
  Set-Cookie: JSESSIONID=abc...
       │
       ▼
Client lưu cookie
       │
       ▼
GET /api/profile
  Cookie: JSESSIONID=abc...
       │
       ▼
Server tải session + SecurityContext
       │
       ▼
Controller nhận Authentication của lan
~~~

Nếu client bỏ cookie ở request thứ hai, server không có thông tin liên kết với session đã tạo. Request có thể trở thành anonymous hoặc bị yêu cầu xác thực lại.

Trong test tích hợp với `WebTestClient.bindToServer()`, có thể lấy cookie từ response đăng nhập rồi gửi lại:

~~~java
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.web.reactive.function.BodyInserters;

import static org.assertj.core.api.Assertions.assertThat;

EntityExchangeResult<Void> loginResult = client.post()
        .uri("/login")
        .body(BodyInserters.fromFormData("username", "lan")
                .with("password", "correct-test-password"))
        .exchange()
        .expectStatus().is3xxRedirection()
        .expectBody()
        .returnResult();

ResponseCookie sessionCookie =
        loginResult.getResponseCookies().getFirst("JSESSIONID");

assertThat(sessionCookie).isNotNull();

client.get()
        .uri("/api/profile")
        .cookie("JSESSIONID", sessionCookie.getValue())
        .exchange()
        .expectStatus().isOk();
~~~

Đây là minh họa cách giữ cookie cho một server Servlet chạy thật; cần điều chỉnh cookie name, login URL, CSRF token và redirect theo ứng dụng. Một số client có cookie store tự động, khi đó không cần tự trích xuất và gắn cookie. Nếu server dùng cookie khác `JSESSIONID`, hãy dùng tên thực tế trong response.

Session có thể được lưu trong memory của server, Redis hoặc một kho session khác. Việc session tồn tại qua nhiều request trong test không có nghĩa session sẽ tồn tại sau khi server restart hoặc sau khi hết hạn. Đó là một bài toán persistence/expiration khác.

## 7. HTTP Basic và bearer token thường là xác thực theo từng request

Không phải mọi cơ chế xác thực đều dùng session.

### HTTP Basic

Với cấu hình HTTP Basic stateless, mỗi request cần gửi lại `Authorization: Basic ...`. Server giải mã credential và xác thực request đó. Không nên giả định một request Basic thành công sẽ tạo session được tái sử dụng.

~~~java
client.get().uri("/api/profile")
        .headers(headers -> headers.setBasicAuth("lan", "password"))
        .exchange()
        .expectStatus().isOk();

client.get().uri("/api/profile")
        .exchange()
        .expectStatus().isUnauthorized();
~~~

Kết quả thứ hai giả định ứng dụng không lưu authentication vào session và request không có credential khác. Nếu cấu hình thêm session persistence, hành vi có thể khác; hãy kiểm tra `SecurityFilterChain`.

### Bearer token

Với Resource Server, client gửi access token trong từng request:

~~~http
Authorization: Bearer eyJ...
~~~

Token có thể được tái sử dụng trong thời hạn hợp lệ, nhưng server thường xác minh token trên mỗi request. Không cần lưu một `SecurityContext` session nếu ứng dụng được cấu hình stateless.

Trong test, `jwt()` hoặc `mockJwt()` thường tạo authentication giả lập cho request cụ thể. Chúng hữu ích để kiểm tra authorization theo scope/claim, nhưng không chứng minh decoder xác minh chữ ký token thật. Muốn kiểm tra xác thực thật, hãy gửi bearer token hợp lệ qua HTTP tới server hoặc gọi decoder với token phù hợp.

### SessionCreationPolicy

Một số giá trị thường gặp trong cấu hình session:

| Chính sách | Ý nghĩa tổng quát |
| --- | --- |
| `ALWAYS` | Luôn tạo HTTP session |
| `IF_REQUIRED` | Tạo session khi cần; thường dùng trong ứng dụng stateful |
| `NEVER` | Không tự tạo session, nhưng có thể sử dụng session đã tồn tại |
| `STATELESS` | Không tạo và không dùng HTTP session để lưu security context cho cơ chế xác thực |

Nếu test mong đợi session persistence nhưng ứng dụng đặt `STATELESS`, test sẽ thất bại vì không có session context để tái sử dụng. Hãy xác định chính sách session trước khi viết assertion.

Có thể khai báo stateless tường minh trong cấu hình Servlet:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;

http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Với cấu hình này, request phải tự mang credential/token theo cơ chế xác thực của ứng dụng. Một request Basic hoặc bearer token hợp lệ không làm server giữ danh tính cho request sau thông qua HTTP session.

## 8. Tự đặt Authentication không tự động lưu qua request sau

Giả sử một custom filter hoặc code test thực hiện:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Đoạn này chỉ đặt context trong holder hiện tại. Với mô hình explicit-save của `SecurityContextHolderFilter`, nó không tự bảo đảm context được lưu trong repository. Nếu code ứng dụng tự xác thực và cần persistence, phải lưu context qua `SecurityContextRepository` theo request/response thích hợp:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
~~~

Đây là phác thảo cho custom authentication flow trong filter; cần thực hiện trong đúng lifecycle và sau khi xác thực thành công, đồng thời xử lý session fixation/session strategy, response commit và cleanup theo cấu hình. Không dùng đoạn này để tự tin một username nhận từ request mà chưa xác minh credentials.

Với test, nếu chỉ gọi `TestSecurityContextHolder.setAuthentication(...)`, bạn đang dựng context test. Nó không thay thế việc lưu context vào `SecurityContextRepository` của server. Đây là điểm khác biệt quan trọng giữa mô phỏng principal và kiểm thử persistence.

## 9. Reactive: WebSessionServerSecurityContextRepository

Trong WebFlux, Spring Security không dùng `HttpSessionSecurityContextRepository` của Servlet. Nó dùng abstraction `ServerSecurityContextRepository`. Với ứng dụng stateful, `WebSessionServerSecurityContextRepository` có thể lưu security context trong `WebSession`; client nhận cookie session (mặc định thường là `SESSION`) và gửi lại trong request tiếp theo.

Với ứng dụng Reactive stateless, có thể dùng `NoOpServerSecurityContextRepository` để không lưu context. Khi đó, bearer token hoặc credential phải được gửi theo từng request.

| Mô hình | Repository thường gặp | Cách duy trì danh tính |
| --- | --- | --- |
| WebFlux stateful | `WebSessionServerSecurityContextRepository` | Gửi lại cookie gắn với WebSession |
| WebFlux stateless | `NoOpServerSecurityContextRepository` | Gửi lại bearer token/credential trong từng request |
| Test request bằng `WebTestClient.mutateWith(mockUser(...))` | Test configurer | Danh tính giả lập cho request test, không chứng minh login/session persistence |

Ví dụ cấp user giả lập cho một request Reactive:

~~~java
webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/profile")
        .exchange()
        .expectStatus().isOk();
~~~

Đây là request mock, không phải luồng đăng nhập WebFlux. Muốn kiểm thử persistence qua WebSession, gửi login request tới server hoặc WebTestClient đã bind với ứng dụng, lấy cookie session và gửi lại ở request kế tiếp. Đừng suy luận từ việc hai request đều dùng `mutateWith(mockUser(...))` rằng session đã được lưu; mỗi request đang được cấp danh tính giả lập.

## 10. Phân biệt các kiểu test theo mục tiêu

| Mục tiêu | Công cụ | Có kiểm tra persistence qua nhiều request không? |
| --- | --- | --- |
| Method security với người dùng giả lập | `@WithMockUser` | Không |
| Authorization của một request MockMvc | `.with(user(...))` / `testSecurityContext()` | Không tự chứng minh |
| HTTP login và dùng lại session trong MockMvc | `formLogin()` + `MockHttpSession` | Có, trong phạm vi test session |
| HTTP Basic với credential thật | HTTP client gửi Basic header | Thường xác thực từng request; phụ thuộc cấu hình |
| Resource Server xác minh bearer token | HTTP client gửi token | Token được gửi lại mỗi request; không cần session nếu stateless |
| Session login trên server thật | HTTP client giữ và gửi cookie | Có, nếu server lưu context trong session |
| WebFlux request mock | `WebTestClient.mutateWith(mockUser(...))` | Không |
| WebFlux WebSession persistence | Login HTTP + cookie `SESSION` | Có, nếu dùng WebSession repository |

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `@WithMockUser` test pass nhưng request thứ hai trên server thật nhận `401` | Test context không được lưu thành session | Thực hiện login qua HTTP và giữ cookie |
| Request đầu dùng `.with(user(...))` thành công, request tiếp theo anonymous | Mỗi request được cấp danh tính riêng; không có login flow persistence | Tái sử dụng session được tạo bởi login thật |
| Login thành công nhưng request sau bị từ chối | Không gửi lại session cookie hoặc session đã hết hạn | Kiểm tra `Set-Cookie` và `Cookie` |
| MockMvc request thứ hai mất user | Không truyền lại `MockHttpSession` | Lấy session từ login result và dùng `.session(session)` |
| Context đặt thủ công nhưng không tồn tại sau request | Chưa gọi `SecurityContextRepository.saveContext(...)` trong explicit-save flow | Lưu context đúng nơi/thời điểm sau xác thực |
| App đặt `STATELESS` nhưng test chờ session | Cấu hình không lưu context vào HTTP session | Gửi credential/token mỗi request hoặc đổi yêu cầu test theo kiến trúc |
| HTTP Basic request sau không còn authentication | Client không gửi lại Authorization header và app không lưu session | Gửi Basic header trên từng request |
| WebFlux test mock user pass nhưng session test fail | `mockUser()` cấp user cho request, không chứng minh WebSession persistence | Login qua WebFlux server và giữ cookie session |
| Test suite phụ thuộc thứ tự do context test cũ còn tồn tại | Cleanup test holder hoặc session fixture chưa đúng | Dọn context test, tạo session độc lập và không dùng biến static |

## 12. Bài thực hành

Tạo ứng dụng Servlet có form login, user test `lan` và endpoint `GET /api/profile` yêu cầu authentication. Sau đó:

1. Viết test `@WithMockUser` và chứng minh test thread đọc được principal `lan`.
2. Gửi request `GET /api/profile` bằng `.with(user("lan"))`; sau đó gửi request mới không có postprocessor và quan sát vì sao không nên coi đây là một phiên đăng nhập.
3. Dùng `formLogin()` gửi username/password hợp lệ, lấy `MockHttpSession` từ kết quả login và dùng session đó cho request thứ hai.
4. Gửi request thứ hai không có session để chứng minh server không tự nhận ra danh tính từ request trước.
5. Thực hiện logout, sau đó gửi lại session cũ và kiểm tra session đã bị vô hiệu hóa theo cấu hình ứng dụng.
6. Cấu hình một test stateless và xác minh HTTP Basic hoặc bearer token phải được gửi trong từng request.
7. Nếu dùng WebFlux, so sánh `WebTestClient.mutateWith(mockUser(...))` với login thực và cookie `SESSION` của `WebSession`.
8. Với custom authentication filter, xác minh việc đặt context và việc gọi `SecurityContextRepository.saveContext(...)` là hai bước riêng trong explicit-save flow.

Sau bài thực hành, hãy trả lời ba câu hỏi: **Danh tính do test giả lập hay do server xác thực? Context được lưu ở repository/session nào? Request sau mang cookie hoặc token gì để server khôi phục danh tính?** Khi trả lời rõ ba câu hỏi này, bạn sẽ phân biệt được test authorization một request với kiểm thử trạng thái đăng nhập được duy trì qua nhiều request.

## Tài liệu tham khảo

- [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security — MockMvc Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html)
- [Spring Security — Reactive SecurityContextRepository](https://docs.spring.io/spring-security/reference/reactive/security-context.html)
- [Spring Security — Reactive Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
