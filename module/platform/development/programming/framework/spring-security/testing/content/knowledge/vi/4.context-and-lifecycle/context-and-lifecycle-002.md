# TestSecurityContextHolder và vai trò trong kiểm thử web giả lập

Trong ứng dụng Servlet, mỗi HTTP request đi qua chuỗi filter của Spring Security. Filter có thể tải một `SecurityContext` từ `SecurityContextRepository` vào `SecurityContextHolder`, rồi dọn context khỏi luồng khi request kết thúc. Điều này đặt ra vấn đề khi viết kiểm thử: nếu một bài test đặt người dùng vào `SecurityContextHolder`, làm sao giữ được danh tính mong muốn cho những lần gọi `MockMvc.perform(...)` tiếp theo?

`TestSecurityContextHolder` thuộc thư viện `spring-security-test` giải quyết chính vấn đề đó. Nó lưu **ngữ cảnh dự kiến của bài test**, tách khỏi biến chứa ngữ cảnh mà HTTP security filter thao tác trong vòng đời request. Bài học nằm trong chương **Ngữ cảnh và vòng đời** của module `SPRING_SECURITY_TESTING`, phục vụ mục tiêu kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `MockMvc` trên Servlet, đồng thời phân biệt cơ chế này với `WebTestClient` trên Reactive.

## 1. Vì sao cần thêm TestSecurityContextHolder?

Cần phân biệt hai khái niệm có tên gần giống nhau:

- `SecurityContextHolder` là API Spring Security ứng dụng dùng khi xử lý nghiệp vụ: lấy `Authentication` từ context hiện tại của luồng.
- `TestSecurityContextHolder` là API trong gói **`org.springframework.security.test.context`**, cung cấp context có chủ đích cho các bài test, đặc biệt khi HTTP filter có thể thay đổi/dọn `SecurityContextHolder` trong quá trình thực hiện request giả lập.

Ví dụ một bài test gọi liên tiếp hai request:

```text
Luồng chạy JUnit:
  TestSecurityContextHolder  ───── Authentication của "lan" ───────┐
          │                                                         │
          │  .with(testSecurityContext())                            │
          ▼                                                         │
  MockMvc.perform(GET /api/me)                                       │
          │                                                         │
          ▼                                                         │
  Chuỗi filter Spring Security                                      │
    ├─ nạp context của request vào SecurityContextHolder            │
    ├─ chạy controller và kiểm tra quyền                             │
    └─ dọn SecurityContextHolder khi kết thúc request                │
          │                                                         │
          └─ kết quả HTTP trả về cho JUnit                           │
                                                                    │
  MockMvc.perform(GET /api/me) ◄─────────────────────────────────────┘
          │       tiếp tục lấy context dự kiến của bài test
          └─ request thứ hai xử lý theo ngữ cảnh đã cung cấp
```

Sơ đồ diễn tả cơ chế kiểm thử Servlet khi `MockMvc` đã được tích hợp Spring Security. Những filter và repository cụ thể phụ thuộc phiên bản/cấu hình bảo mật; nguyên tắc vẫn là **context dùng trong request và context mà bài test muốn dùng lại có vòng đời khác nhau**.

Nếu chỉ gọi:

```java
SecurityContextHolder.setContext(context);
mockMvc.perform(get("/api/me"));
```

thì không có bảo đảm request sẽ sử dụng `context` vừa đặt. Filter có thể tải context khác từ repository, và thường dọn `SecurityContextHolder` khi hoàn tất xử lý. Đó là lý do tồn tại `TestSecurityContextHolder` và request postprocessor `testSecurityContext()`.

> **Giới hạn:** `TestSecurityContextHolder` chỉ giúp dựng danh tính giả lập trong bài test. Nó không đăng nhập vào server, không chứng minh session đã được lưu, không ký JWT và không làm cho HTTP request gửi qua cổng mạng mang danh tính này.

## 2. Bốn API cần nhớ

Lớp `TestSecurityContextHolder` có các phương thức tĩnh sau:

| API | Tác dụng | Khi sử dụng |
| --- | --- | --- |
| `setAuthentication(Authentication)` | Tạo `SecurityContext` mới chứa authentication; đặt context này vào **cả** `TestSecurityContextHolder` và `SecurityContextHolder` | Muốn nhanh chóng thiết lập một danh tính có sẵn |
| `setContext(SecurityContext)` | Đặt một context đã tạo vào **cả hai** holder | Cần context tùy biến hoặc principal đặc biệt |
| `getContext()` | Đọc context được lưu trong `TestSecurityContextHolder` | Kiểm tra ngữ cảnh dự kiến của bài test |
| `clearContext()` | Dọn **cả** `TestSecurityContextHolder` và `SecurityContextHolder` trên luồng hiện hành | Thu hồi trạng thái giả lập sau khi dùng |

`setAuthentication(...)` hữu ích nếu đã có một `Authentication` mà không muốn viết lại các bước tạo context.

```java
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.test.context.TestSecurityContextHolder;

Authentication reader = new UsernamePasswordAuthenticationToken(
        "lan",
        "N/A",
        AuthorityUtils.createAuthorityList("ROLE_READER")
);

try {
    TestSecurityContextHolder.setAuthentication(reader);

    Authentication fromTestHolder =
            TestSecurityContextHolder.getContext().getAuthentication();
    // fromTestHolder.getName().equals("lan")
} finally {
    TestSecurityContextHolder.clearContext();
}
```

Khác với cách chỉ gọi `SecurityContextHolder.setContext(...)`, lời gọi `TestSecurityContextHolder.setAuthentication(reader)` cập nhật cả hai holder cùng lúc. Nhờ vậy, dịch vụ chạy trực tiếp trên luồng test có thể đọc được `SecurityContextHolder`, trong khi phần kiểm thử HTTP có thể sử dụng context từ `TestSecurityContextHolder`.

Khi cần context tùy biến, dùng `setContext(...)`:

```java
SecurityContext testContext = SecurityContextHolder.createEmptyContext();
testContext.setAuthentication(reader);
TestSecurityContextHolder.setContext(testContext);
```

Không dùng `TestSecurityContextHolder.getContext().setAuthentication(...)` khi chưa thiết lập context một cách rõ ràng: việc có sẵn context từ listener hay không phụ thuộc vào cấu hình và vòng đời test. Gọi `setAuthentication(...)` hoặc tự tạo context giúp ví dụ dễ hiểu, dễ tái lập hơn.

## 3. Tương tác với @WithMockUser và TestExecutionListener

Trong bài test tích hợp Spring TestContext Framework, `WithSecurityContextTestExecutionListener` tìm annotation như `@WithMockUser`, `@WithUserDetails` hoặc annotation tùy biến dựa trên `@WithSecurityContext`. Listener tạo context giả lập và thiết lập nó để bài test dùng được.

Vòng đời thường gặp với JUnit Jupiter:

```text
WithSecurityContextTestExecutionListener.beforeTestMethod
    └─ tạo và đặt context từ @WithMockUser vào test/security holder

@BeforeEach
@Test
    ├─ mã kiểm thử có thể đọc Authentication
    └─ MockMvc lấy context giả lập nếu được cấu hình tích hợp
@AfterEach

WithSecurityContextTestExecutionListener.afterTestMethod
    └─ TestSecurityContextHolder.clearContext()
       (dọn cả test holder và SecurityContextHolder)
```

Mặc định context được thiết lập trước `@BeforeEach`. Có thể chuyển sang `setupBefore = TestExecutionEvent.TEST_EXECUTION` để đặt context sau `@BeforeEach` nhưng trước phương thức test; đây là lựa chọn khi việc dựng context phụ thuộc vào dữ liệu khởi tạo trước đó.

Với `@WithMockUser(username = "lan", roles = "READER")`, listener tạo `Authentication` giả lập có tên `lan` và authority `ROLE_READER`. `@WithMockUser` **không** kiểm tra mật khẩu và không bắt buộc tài khoản `lan` tồn tại trong cơ sở dữ liệu.

Ví dụ:

```java
@Test
@WithMockUser(username = "lan", roles = "READER")
void listenerDatDanhTinhChoBaiTest() {
    Authentication auth =
            TestSecurityContextHolder.getContext().getAuthentication();

    assertThat(auth.getName()).isEqualTo("lan");
    assertThat(auth.getAuthorities())
            .extracting("authority")
            .contains("ROLE_READER");
}
```

Các import liên quan là `org.springframework.security.test.context.TestSecurityContextHolder`, `org.springframework.security.test.context.support.WithMockUser` và `org.springframework.security.core.Authentication`. Đoạn trên phải chạy trong Spring TestContext có listener Spring Security; một test JUnit thuần không tự kích hoạt `@WithMockUser` chỉ vì thêm annotation.

**Không cần tự gọi `setAuthentication(...)` khi `@WithMockUser` đã mô tả đúng người dùng.** Việc ghi thủ công giữa bài test có thể thay danh tính mà listener tạo, khiến kết quả khó theo dõi. Dùng API thủ công khi mục đích bài test là dựng `Authentication` hoặc `SecurityContext` đặc biệt.

## 4. Cầu nối từ ngữ cảnh kiểm thử vào MockMvc

Để các request Servlet nhận đúng security context giả lập, `MockMvc` phải có phần tích hợp Spring Security. Với `WebApplicationContext`, thiết lập phổ biến là:

```java
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;

@BeforeEach
void setUp() {
    mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
            .apply(springSecurity())
            .build();
}
```

`springSecurity()` thêm chuỗi filter của Spring Security và `TestSecurityContextHolderPostProcessor` cần thiết để lấy context test khi chạy với annotation. Nếu dùng `@SpringBootTest` hoặc `@WebMvcTest` kết hợp `@AutoConfigureMockMvc` và bật các security filter theo cấu hình mặc định, phần tích hợp thường được Spring Boot dựng sẵn.

Request postprocessor có tên `SecurityMockMvcRequestPostProcessors.testSecurityContext()` cho phép nói rõ request này dùng context từ `TestSecurityContextHolder`:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.testSecurityContext;

mockMvc.perform(get("/api/me").with(testSecurityContext()))
       .andExpect(status().isOk());
```

Khi đã gọi `apply(springSecurity())`, việc chuyển context của annotation vào request thường được cấu hình tự động. Viết thêm `.with(testSecurityContext())` là cách **tường minh hóa** cơ chế cầu nối trong bài học, hữu ích khi tự kiểm tra hoặc dựng context bằng code.

Nếu dựng `MockMvc` bằng `standaloneSetup(...)` mà không thêm security filter phù hợp, một request thành công có thể chỉ chứng minh controller xử lý được dữ liệu. Nó **chưa chứng minh** luật xác thực/phân quyền tại HTTP layer đã được thực thi. Ngoài ra, request postprocessor có thể gắn context cho request, nhưng chỉ khi cơ chế filter/security context repository phù hợp tham gia thì controller và các kiểm tra bảo mật mới nhận được context đó.

## 5. Ví dụ hoàn chỉnh: hai HTTP request dùng cùng danh tính giả lập

Ví dụ sau dùng Spring Test, Spring MVC và `spring-security-test`; không phụ thuộc Spring Boot. Nó dựng endpoint `GET /api/me` trả về tên người dùng, khai báo luật yêu cầu xác thực, rồi thực hiện nhiều request để thể hiện vai trò của `TestSecurityContextHolder`.

Các dependency cần có trong dự án: `spring-test`, `spring-webmvc`, `spring-security-config`, `spring-security-web`, `spring-security-test`, JUnit Jupiter và AssertJ.

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.test.context.TestSecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.testSecurityContext;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup
        .SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = TestSecurityContextWebTest.WebConfig.class)
class TestSecurityContextWebTest {

    @Autowired
    WebApplicationContext webApplicationContext;

    MockMvc mockMvc;

    @BeforeEach
    void setup() {
        mockMvc = MockMvcBuilders.webAppContextSetup(webApplicationContext)
                .apply(springSecurity())
                .build();
    }

    @Test
    @WithMockUser(username = "lan", roles = "READER")
    void withMockUserTuongTacVoiMockMvc() throws Exception {
        assertThat(TestSecurityContextHolder.getContext()
                .getAuthentication().getName()).isEqualTo("lan");

        mockMvc.perform(get("/api/me").with(testSecurityContext()))
                .andExpect(status().isOk())
                .andExpect(content().string("lan"));
    }

    @Test
    void setAuthenticationChoNhieuRequest() throws Exception {
        Authentication mai = new UsernamePasswordAuthenticationToken(
                "mai", "N/A",
                AuthorityUtils.createAuthorityList("ROLE_READER"));

        try {
            TestSecurityContextHolder.setAuthentication(mai);

            mockMvc.perform(get("/api/me").with(testSecurityContext()))
                    .andExpect(status().isOk())
                    .andExpect(content().string("mai"));

            // Request đầu đã kết thúc, nhưng ngữ cảnh của bài test
            // vẫn có thể được dùng lại cho request tiếp theo.
            assertThat(TestSecurityContextHolder.getContext()
                    .getAuthentication().getName()).isEqualTo("mai");

            mockMvc.perform(get("/api/me").with(testSecurityContext()))
                    .andExpect(status().isOk())
                    .andExpect(content().string("mai"));
        } finally {
            TestSecurityContextHolder.clearContext();
        }
    }

    @Test
    void postProcessorDatDanhTinhRiengChoRequest() throws Exception {
        mockMvc.perform(get("/api/me").with(user("binh").roles("READER")))
                .andExpect(status().isOk())
                .andExpect(content().string("binh"));
    }

    @Test
    void khongCoDanhTinhThiNhan401() throws Exception {
        mockMvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @RestController
    static class MeController {
        @GetMapping("/api/me")
        String currentUser(Authentication authentication) {
            return authentication.getName();
        }
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    @Import(MeController.class)
    static class WebConfig {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            return http
                    .authorizeHttpRequests(authorize -> authorize
                            .requestMatchers("/api/me").authenticated()
                            .anyRequest().denyAll())
                    .httpBasic(Customizer.withDefaults())
                    .build();
        }
    }
}
```

Trong ví dụ, `401` ở request vô danh đến từ entry point HTTP Basic. Nếu ứng dụng dùng form login, tình huống tương tự có thể dẫn đến `302` chuyển hướng; mã phản hồi phải được đánh giá theo cấu hình bảo mật thật của dự án.

Điều cần quan sát trong `setAuthenticationChoNhieuRequest()`:

1. `setAuthentication(mai)` đặt context dự kiến vào test holder.
2. `.with(testSecurityContext())` cấp context đó cho request thứ nhất.
3. Filter xử lý request, sau đó trả quyền quản lý luồng về cho bài test.
4. `TestSecurityContextHolder.getContext()` vẫn là nguồn ngữ cảnh dự kiến của test.
5. Request thứ hai lại được cấp danh tính `mai` mà không cần thực hiện đăng nhập mới.

**Không được suy ra từ việc hai request đều thấy `mai` rằng ứng dụng đã lưu session đăng nhập.** Test đã chủ động cấp context cho từng request. Để kiểm chứng session/cookie persistence, cần thử chuỗi request mang đúng session/cookie và không cấp danh tính giả lập lại.

## 6. Chọn cách cung cấp người dùng: ba phạm vi khác nhau

| Phương án | Phạm vi ý định | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| `@WithMockUser` / `@WithUserDetails` | Danh tính mặc định cho một test hoặc lớp test qua listener | Gọn, diễn đạt dễ đọc | Phụ thuộc Spring TestContext; không xác thực token/mật khẩu thật |
| `TestSecurityContextHolder.setAuthentication(...)` / `setContext(...)` | Context do code của test thiết lập, có thể cấp lại cho nhiều request giả lập | Hỗ trợ principal và authentication tùy chỉnh | Phải quản lý dọn dẹp, cần cầu nối sang request |
| `.with(user(...))` / `.with(authentication(...))` / `.with(securityContext(...))` | Danh tính của **một request MockMvc cụ thể** | Phù hợp kiểm tra nhiều vai trò trong cùng một test | Chỉ có tác dụng khi tích hợp filter/security context đúng |
| `.with(jwt())` / `.with(oauth2Login())` / `.with(oidcLogin())` | Request giả lập theo kiểu JWT, OAuth2 hoặc OIDC | Kiểm tra phân quyền theo claim, scope, principal | Không chứng minh chữ ký JWT hoặc luồng đăng nhập từ nhà cung cấp thật |

Cùng một endpoint, có thể viết trường hợp cấp quyền và từ chối ngay tại request:

```java
mockMvc.perform(get("/api/admin").with(user("lan").roles("READER")))
       .andExpect(status().isForbidden());

mockMvc.perform(get("/api/admin").with(user("mai").roles("ADMIN")))
       .andExpect(status().isOk());
```

Hai assertion này giả định `/api/admin` tồn tại, yêu cầu `ROLE_ADMIN` và trả `200` khi thành công. Chúng kiểm thử rule ở tầng HTTP tốt hơn việc chỉ assert đối tượng `Authentication` tồn tại trong test holder.

Trong bài test có `@WithMockUser` ở cấp lớp hoặc đã gọi `setAuthentication(...)`, nên xác định rõ request nào muốn giữ danh tính mặc định và request nào muốn ghi đè. Khi dùng postprocessor `user(...)`, `authentication(...)` hoặc `securityContext(...)`, hãy thể hiện lựa chọn ngay tại `perform(...)` để tránh diễn giải nhầm người dùng nào đang hoạt động.

## 7. Những sai lầm về vòng đời và tính cô lập

### 7.1. Chỉ dọn SecurityContextHolder

```java
TestSecurityContextHolder.setAuthentication(reader);

// ... thực hiện kiểm thử ...

SecurityContextHolder.clearContext(); // Chưa dọn test holder!
```

Lời gọi cuối chỉ dọn `SecurityContextHolder`, trong khi `TestSecurityContextHolder` có bộ nhớ context riêng. Nếu một request tiếp theo sử dụng `testSecurityContext()`, nó vẫn có thể nhận context cũ. Với các test tự quản lý, phải dùng:

```java
try {
    TestSecurityContextHolder.setAuthentication(reader);
    // assertions
} finally {
    TestSecurityContextHolder.clearContext();
}
```

Nếu đang dùng `WithSecurityContextTestExecutionListener`, listener sẽ dọn hai holder sau phương thức test. `finally` vẫn phù hợp cho những đoạn tự thiết lập context cần có phạm vi độc lập hoặc khi không chạy trong listener.

### 7.2. Coi test holder là kho trạng thái chung toàn ứng dụng

Cả holder mặc định trong Servlet lẫn cơ chế lưu của `TestSecurityContextHolder` đều gắn với ngữ cảnh chạy kiểm thử trên luồng. Đừng dùng `TestSecurityContextHolder` như singleton danh tính để chia sẻ cho các luồng khác, cho server chạy cổng ngẫu nhiên hoặc cho test chạy song song. Request HTTP gửi qua mạng không tự mang `Authentication` của luồng JUnit; cần gửi Authorization header, session/cookie hoặc thông tin đăng nhập thật.

Nếu thực sự muốn kiểm tra logic trong `ExecutorService` hoặc `@Async`, cần dùng cơ chế truyền `SecurityContext` đến luồng xử lý (ví dụ `DelegatingSecurityContextExecutorService`) và kiểm tra kết quả tác vụ. `TestSecurityContextHolder` không thay thế cơ chế truyền luồng.

### 7.3. Nhầm context giả lập với quá trình xác thực

`@WithMockUser` và `.with(user(...))` tạo danh tính đã được chấp nhận cho kiểm thử. Nếu muốn thử người dùng nhập sai mật khẩu, cần thực hiện request tới endpoint đăng nhập/cơ chế HTTP Basic với credentials tương ứng. Nếu muốn kiểm chứng resource server từ chối JWT sai chữ ký, cần chạy bộ kiểm tra giải mã/xác minh token; chỉ dùng `.with(jwt())` sẽ bỏ qua phần xác thực token thực.

Với OAuth2/OIDC, `oauth2Login()` và `oidcLogin()` hữu ích để mô phỏng principal, claims và authorities cho bước phân quyền, nhưng không kiểm tra toàn bộ redirect/callback của bên cung cấp danh tính.

### 7.4. Dựa vào SecurityContextHolder sau request

Khi HTTP security filter kết thúc xử lý, `SecurityContextHolder` có thể đã được dọn. Vì vậy, assertion đọc `SecurityContextHolder.getContext()` **sau** `mockMvc.perform(...)` không phải cách đáng tin cậy để xác minh người dùng **trong** controller. Hãy dùng:

- `content()`, `jsonPath()`, `status()` hoặc kết quả nghiệp vụ của endpoint;
- request postprocessor phù hợp để thiết lập danh tính;
- `TestSecurityContextHolder.getContext()` nếu mục tiêu riêng là kiểm tra context của bài test.

### 7.5. Bỏ cấu hình filter nhưng vẫn kết luận phân quyền đúng

Nếu `MockMvcBuilders.standaloneSetup(controller)` chạy mà không có các security filter cần thiết, test có thể gọi controller thẳng. Kiểm tra `200` trong môi trường này không chứng minh rằng `@PreAuthorize`, luật `authorizeHttpRequests` hay bảo vệ CSRF đã được áp dụng đầy đủ.

Để test HTTP Servlet, ưu tiên `webAppContextSetup(...).apply(springSecurity())` hoặc Spring Boot auto-configure `MockMvc` với filter đang bật. Khi kiểm thử request thay đổi trạng thái bằng `POST`/`PUT`/`DELETE`, còn cần xét CSRF: request có thể bị `403` vì thiếu token CSRF, hoàn toàn không liên quan tới vai trò của người dùng.

## 8. So sánh với kiểm thử Reactive

Trong WebFlux, `ReactiveSecurityContextHolder` truyền ngữ cảnh thông qua **Reactor Context**. `TestSecurityContextHolder` và request postprocessor của `MockMvc` được thiết kế chủ yếu cho kiểm thử HTTP **Servlet**, không phải là cách truyền danh tính cho mọi luồng trong reactive pipeline.

Với `WebTestClient`, Spring Security cung cấp cơ chế riêng, chẳng hạn:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

webTestClient.mutateWith(mockUser("lan").roles("READER"))
        .get().uri("/api/me")
        .exchange()
        .expectStatus().isOk();
```

Đoạn ví dụ giả định ứng dụng WebFlux có endpoint `/api/me` cho phép người dùng `READER` và `WebTestClient` đã tích hợp Spring Security. Khi dùng cấu hình tự tạo, cần thêm `SecurityMockServerConfigurers.springSecurity()` đúng cách. Nếu muốn mô phỏng OAuth2/JWT trên Reactive, dùng các API tương ứng của `SecurityMockServerConfigurers`; không lấy `TestSecurityContextHolder.getContext()` rồi giả định sẽ tự đi xuyên qua Reactor pipeline.

## 9. Bảng kiểm gỡ lỗi nhanh

| Triệu chứng | Cần kiểm tra | Hướng giải quyết |
| --- | --- | --- |
| Test holder có `lan` nhưng endpoint báo vô danh | `MockMvc` có security filter và postprocessor hay chưa | Dùng `apply(springSecurity())`, `@AutoConfigureMockMvc` đúng cấu hình, hoặc `.with(testSecurityContext())` |
| Request đầu thành công, request sau mất user | Context của request có được gắn lại từ test holder không | Dùng `testSecurityContext()` cho request cần giả lập; không suy diễn session persistence |
| Test kế tiếp mang danh tính của test trước | Có gọi `clearContext()` trên **test holder** không | `try/finally` hoặc listener Spring Security, tránh biến static |
| Có `@WithMockUser` nhưng `getContext()` trống | Test có Spring TestContext listener hay không; `setupBefore` lúc nào | Bật tích hợp Spring TestContext và xét thời điểm gọi |
| Request dùng `.with(user(...))` vẫn trả `200` dù không có phân quyền | Có áp dụng chuỗi filter HTTP thực sự không | Cấu hình `MockMvc` tích hợp bảo mật và assert trường hợp bị từ chối |
| `POST` nhận `403` bất ngờ | CSRF có bật không; request có token không | Dùng `.with(csrf())` cho bài test có CSRF hợp lệ, và thêm ca thiếu token |
| Test JWT giả lập thành công nhưng JWT thật bị từ chối | Có thử decode/chữ ký/issuer/audience thật không | Tách test phân quyền mock khỏi test xác thực token |
| `WebTestClient` không thấy danh tính | Có Spring Security WebFlux/Reactor Context hay không | Dùng hỗ trợ Reactive tương ứng |

## 10. Thực hành tự kiểm tra

Hãy tự xây dựng một endpoint `GET /api/reports` với quy tắc `hasRole("ADMIN")` và viết các trường hợp sau:

1. Dùng `@WithMockUser(username = "mai", roles = "ADMIN")`, đọc tên người dùng từ `TestSecurityContextHolder.getContext()` rồi gọi request bằng `MockMvc`.
2. Bỏ annotation, tự tạo `Authentication` cho `mai` bằng `setAuthentication(...)`; gọi hai request liên tiếp với `testSecurityContext()`. Kiểm tra cả hai đều được phép.
3. Đổi danh tính bằng `.with(user("lan").roles("READER"))` cho một request và kỳ vọng `403`; tiếp theo gửi request với `ADMIN` và kỳ vọng `200`.
4. Thêm một ca `POST` với cấu hình yêu cầu CSRF để phân biệt lỗi do CSRF và lỗi do phân quyền.
5. Viết một test khác dùng `try/finally` để tự dọn context; giải thích vì sao gọi riêng `SecurityContextHolder.clearContext()` không đủ.

Sau khi làm xong, trả lời ba câu hỏi: **Ai sở hữu context của bài test? Ai xử lý context trong từng HTTP request? Bằng chứng nào chứng minh phân quyền đã chạy?** Nếu phân biệt được ba ranh giới này, bạn sẽ chọn đúng cách tạo danh tính và tránh phần lớn lỗi nhiễm ngữ cảnh trong kiểm thử web giả lập.

## Tài liệu tham khảo

- [Spring Security API — TestSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/context/TestSecurityContextHolder.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Security — Running a Test as a User in Spring MVC Test](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/authentication.html)
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html)
- [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html)
- [Spring Security — Testing Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
