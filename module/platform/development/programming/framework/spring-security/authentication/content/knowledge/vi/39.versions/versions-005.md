# Thay đổi cơ chế lưu SecurityContext và trách nhiệm explicit save

Khi nâng ứng dụng từ **Spring Security 5.x lên Spring Security 6.x**, một hiện tượng quen thuộc là: controller tự xác thực username/password, gọi `SecurityContextHolder.setContext(...)`, request đăng nhập trả HTTP 200, nhưng **request tiếp theo lại bị coi là anonymous** và chuyển về trang đăng nhập. Mật khẩu có thể hoàn toàn đúng, `Authentication.isAuthenticated()` có thể là `true` ngay trong request đầu, nhưng `SecurityContext` **chưa được lưu vào nơi mà request sau có thể đọc lại**.

Điểm thay đổi chính trong **Spring Security Servlet** là cơ chế mặc định chuyển từ `SecurityContextPersistenceFilter` — có logic **tự phát hiện và lưu thay đổi** — sang `SecurityContextHolderFilter` — **chỉ nạp context**, không tự lưu. Nếu ứng dụng có **controller/filter đăng nhập tự viết**, phía viết context phải **gọi rõ `SecurityContextRepository.saveContext(...)`** khi muốn người dùng duy trì phiên ở request tiếp theo.

Tuy nhiên, một cách diễn giải khác cũng sai: “Spring Security 6 không còn tự lưu đăng nhập nào nữa”. **Các cơ chế xác thực do framework cung cấp**, như form login Servlet, vẫn phối hợp với repository và tự thực hiện các bước cần thiết để persist authentication. Trách nhiệm explicit save quan trọng nhất ở **code tùy chỉnh thay thế/bỏ qua các authentication filters chuẩn** hoặc code tự sửa/clear context và mong thay đổi tồn tại giữa các request.

Bài Knowledge thuộc nhóm **Phiên bản** trong **Spring Security - authentication**, tập trung vào hành vi **5.x → 6.x (đối chiếu với Spring Security 6.5)**, khái niệm repository/filter, migration, ví dụ **Java 17+ / Spring Boot 3.5.x**, tests dùng MockMvc qua hai request, và các lỗi thường gặp khi login, logout, session hoặc custom security filter.

## 1. Hiểu SecurityContext: thread hiện tại khác state xuyên request

### 1.1. Ba khái niệm không đồng nghĩa

- **`Authentication`**: kết quả xác thực (principal, authorities, trạng thái và tùy implementation có credentials/details). Nó không tự tạo HTTP session.
- **`SecurityContext`**: đối tượng chứa `Authentication` đang được Spring Security dùng.
- **`SecurityContextHolder`**: cách truy cập context trong luồng xử lý hiện tại; mặc định thường là chiến lược `ThreadLocal`, được filter quản lý/clear ở cuối request.

Ví dụ đặt trong method đã có một `Authentication authentication` hợp lệ:

~~~java
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
~~~

Ba dòng trên **chỉ chứng minh SecurityContext hiện tại đã được cập nhật**. Nếu context holder bị clear khi request kết thúc mà không có repository lưu, request mới **không thể tự động khôi phục** người dùng từ thao tác trên.

Muốn dùng context ở request sau, phải có một cơ chế persistence phù hợp — thường là `HttpSessionSecurityContextRepository`/`DelegatingSecurityContextRepository` — và **lời gọi save đúng thời điểm**, hoặc một cơ chế authentication stateless có thể xác minh lại credential/token cho mỗi request.

### 1.2. Sơ đồ có và không có persistence

~~~text
Request 1: POST /api/manual-login
   │
   ├─ AuthenticationManager xác minh password
   ├─ Tạo SecurityContext và set Authentication
   ├─ SecurityContextHolder.setContext(context)
   │          │
   │          ├─ KHÔNG gọi repository.saveContext(...)
   │          │      └─ response 200 rồi kết thúc request
   │          │               └─ holder được clear
   │          │
   │          └─ CÓ gọi repository.saveContext(context, req, resp)
   │                 └─ repository ghi vào HTTP session (nếu phù hợp)
   │                        └─ response mang session cookie (khi cần)
   ▼
Request 2: GET /api/me
   │
   ├─ SecurityContextHolderFilter yêu cầu repository nạp context
   │
   ├─ Không lưu ở request 1 → anonymous / 401 / redirect login
   └─ Có lưu + client gửi lại session cookie hợp lệ
          → context được phục hồi → authenticated / được authorize
~~~

**Không nên lưu `SecurityContext` bằng cách gán nó vào một biến `static` hoặc `ThreadLocal` tự quản lý.** Cách đó không gắn với phiên người dùng, có thể làm rò principal giữa các request/thread, không hoạt động đúng trong cluster và không bảo đảm security context cleanup.

## 2. Điều gì thay đổi theo phiên bản?

| Giai đoạn | Filter/cơ chế phổ biến | Trách nhiệm của code tự xác thực |
| --- | --- | --- |
| **Spring Security 5.x mặc định** | `SecurityContextPersistenceFilter` nạp, theo dõi và lưu context phù hợp khi request hoàn tất/response commit | Nhiều đoạn code cũ chỉ `setContext(...)` vẫn có thể được lưu tự động |
| **Spring Security 5.8 trong lộ trình nâng cấp** | Có thể chủ động bật `requireExplicitSave(true)` để dùng semantics mới và sửa code | Bổ sung explicit `saveContext(...)` trước khi chuyển hẳn sang 6 |
| **Spring Security 6.x mặc định** | `SecurityContextHolderFilter` **nạp** context nhưng không tự ghi thay đổi | Khi code tự quản lý authentication mà muốn lưu liên request, phải gọi `SecurityContextRepository.saveContext(...)` |
| **Spring Security 6.5.x** | Tiếp tục semantics explicit save trong Servlet; built-in form login vẫn đảm nhiệm persistence của chính luồng nó | Kiểm tra custom controller/filter, logout và repository/session policy |

**Phiên bản 5.8 không đồng nghĩa mọi project 5.8 đã tự động chuyển hết behavior**: nó là nhánh chuyển tiếp hỗ trợ cấu hình tương thích. Hãy xác minh chính xác cấu hình/filter chain của ứng dụng, không chỉ nhìn version number trong `build.gradle`.

### 2.1. Tại sao framework thay đổi?

Theo tài liệu migration Spring Security:

1. `SecurityContextPersistenceFilter` phải theo dõi context có thay đổi không để quyết định có cần save.
2. Nó phải tránh lỗi **commit response/redirect trước khi kịp tạo session cookie**; vì vậy có logic wrapper xử lý ngay trước commit.
3. Việc tự phát hiện thay đổi đôi khi tạo **ghi không cần thiết** vào `SecurityContextRepository`/`HttpSession`, đặc biệt khi quản lý session phức tạp.
4. `SecurityContextHolderFilter` tách rõ trách nhiệm **read/restore/clear** khỏi **save**: component tạo/sửa authentication sẽ xác định khi nào cần ghi.
5. Cách mới dễ dự đoán hơn nếu code tự quản lý context, nhưng buộc custom code trước đây dựa vào implicit save phải được sửa.

Đổi lại, Spring Security 6 cho phép ứng dụng **quyết định rõ** khi nào authentication được coi là đủ điều kiện persistence. Không phải mọi request đọc context cũng cần ghi lại session.

### 2.2. Tham số requireExplicitSave(true/false)

Trong Java DSL Spring Security 6.x, cấu hình minh họa:

~~~java
http.securityContext(securityContext -> securityContext
        .requireExplicitSave(true));
~~~

`true` là semantics mặc định của Spring Security 6. Nó khiến `SecurityContextHolderFilter` được cấu hình thay cho `SecurityContextPersistenceFilter`. Với Spring Security 6 đã dùng default, dòng này thường **không cần thêm**, nhưng giúp người đọc hiểu mục tiêu migration.

Cấu hình tạm thời phục vụ tương thích legacy:

~~~java
http.securityContext(securityContext -> securityContext
        .requireExplicitSave(false));
~~~

Tùy phiên bản, cấu hình tương thích có thể quay lại semantics dựa trên `SecurityContextPersistenceFilter`. **Đừng chọn `false` làm giải pháp lâu dài chỉ để tránh sửa custom login**. Cần lập kế hoạch chuyển sang explicit save, test các đường login/logout và loại dần implicit persistence.

**Không bao giờ đặt cả `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter` trong cùng một filter chain chỉ để “chắc chắn có lưu”.** Tài liệu Spring Security 6 nhấn mạnh một ứng dụng/chain chỉ nên dùng **một trong hai** filter này.

### 2.3. Không nhầm với thay đổi SessionManagementFilter

Spring Security 6 còn chuyển một số trách nhiệm session khác:

- `SessionManagementFilter` **không được cấu hình mặc định** như trong một số cơ chế Spring Security 5.
- Với authentication filter mới, chính cơ chế xác thực cần gọi `SessionAuthenticationStrategy` phù hợp sau khi authentication thành công.
- Vì thế custom login không chỉ cần `saveContext`: còn có thể cần session fixation protection, concurrent session rules, remember-me, CSRF, MFA, success/failure handling và audit.
- Một số option trong DSL cũ liên quan `SessionManagementFilter` không có tác dụng như trước hoặc có thể bị từ chối theo version/cấu hình; kiểm docs migration.
- **`SecurityContextRepository` và `SessionAuthenticationStrategy` là hai trách nhiệm khác nhau:** repository lưu/khôi phục context, strategy xử lý chính sách session khi xác thực.

`saveContext(...)` có thể làm request sau nhận lại principal, nhưng **không tự thực hiện đầy đủ quy trình form login**. Với ứng dụng web thông thường, luôn ưu tiên bộ lọc đăng nhập chuẩn nếu không có lý do phải tự viết.

## 3. SecurityContextRepository: lưu vào đâu?

| Implementation | Đặc điểm | Giới hạn cần nhớ |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Dùng `HttpSession` để giữ context giữa HTTP requests của cùng session | Cần session/cookie hợp lệ, không thích hợp nếu project thực sự stateless |
| `RequestAttributeSecurityContextRepository` | Lưu context dưới request attribute, hữu ích với dispatch khác trong **cùng request** như ERROR | **Không** giữ authentication qua request HTTP độc lập tiếp theo |
| `DelegatingSecurityContextRepository` | Ủy quyền đọc/ghi tới nhiều repository, mặc định Spring Security 6 thường gồm RequestAttribute + HttpSession | Phải xác minh delegates/đúng instance của chain; không hiểu nhầm chỉ có request attribute |
| `NullSecurityContextRepository` | Không lưu context và thường không trả context đã lưu | Không phù hợp khi muốn browser có session login persistent |
| Custom repository | Có thể dùng cache/DB hoặc cơ chế phân tán | Phải tuân thủ contract, concurrency, invalidation, TTL và security |

### 3.1. Default 5.x so với 6.x

Trong hướng dẫn migration:

- Default Spring Security 5 thường là `HttpSessionSecurityContextRepository`.
- Default Spring Security 6 thường là `DelegatingSecurityContextRepository`, bao gồm `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`.

Một trong các nguyên nhân là ERROR dispatch có thể chạy sau khi request context holder đã được clear; repository qua request attribute giúp context còn dùng được **trong cùng request** mà không buộc mọi thứ dựa vào session.

**Quan trọng:** “default DelegatingSecurityContextRepository” không có nghĩa Spring tự động save mọi thay đổi trong mỗi request; nó chỉ xác định **nơi lưu khi `saveContext` được gọi**.

### 3.2. Ví dụ tạo cùng một repository cho custom controller và filter chain

Trong method cấu hình Spring có các imports phù hợp:

~~~java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());

http.securityContext(context -> context
        .securityContextRepository(repository)
        .requireExplicitSave(true));
~~~

Các class thuộc package `org.springframework.security.web.context`. Nếu custom code dùng một repo khác với repo mà filter đang đọc, có thể gặp tình trạng **ghi một chỗ, đọc một chỗ**. Trong bài lab ở mục 7, repository được đăng ký thành **cùng một bean** rồi inject vào `SecurityFilterChain` và controller.

### 3.3. Khi nào HttpSession được tạo?

`HttpSessionSecurityContextRepository` cố gắng tránh tạo session vô ích:

- Chỉ nạp context từ session có sẵn **không có nghĩa** tạo session ngay.
- Khi `saveContext` cần lưu authenticated context và policy cho phép, repo có thể tạo session nếu chưa có.
- Nếu context rỗng hoặc anonymous theo `AuthenticationTrustResolver`, có thể không lưu/không tạo session.
- `setAllowSessionCreation(false)` ngăn repository tự tạo session mới, nhưng không cấm các thành phần khác tạo session và repo vẫn có thể ghi vào session đã tồn tại.
- `SessionCreationPolicy.IF_REQUIRED` (thường phù hợp với form login) khác `STATELESS`.
- Cookie `JSESSIONID` phải được client lưu/gửi lại đúng Host/Path/SameSite/Secure, reverse proxy HTTPS và session store phải hoạt động.

Do đó test “gọi saveContext không ném exception” **chưa đủ**; hãy kiểm request mới với cùng session/cookie và đúng người dùng. Khi chỉ có `RequestAttributeSecurityContextRepository`, test trong cùng request có thể pass còn request sau lại anonymous.

### 3.4. STATeless không phải lỗi explicit save

Nếu thiết kế API dùng `SessionCreationPolicy.STATELESS` và `NullSecurityContextRepository`, việc không giữ context cho request sau thường **đúng mục tiêu**: mỗi request phải mang Bearer token/API key/HTTP Basic hoặc cơ chế xác thực lại.

~~~java
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS));
~~~

Snippet cần import `org.springframework.security.config.http.SessionCreationPolicy`. **Đừng sửa API stateless bằng cách bật HTTP session chỉ để “sửa login”** nếu contract đã chọn JWT/Bearer. Hãy kiểm client thực sự gửi token, signature/issuer/audience/expiration và đúng `SecurityFilterChain`.

## 4. Cơ chế cũ: SecurityContextPersistenceFilter và implicit save

Với semantics cũ (mô tả ở mức khái niệm):

~~~text
SecurityContextPersistenceFilter
   │
   ├─ load SecurityContext từ SecurityContextRepository
   ├─ đặt vào SecurityContextHolder
   ▼
Controller / authentication filter:
   └─ set Authentication vào SecurityContextHolder
   ▼
SecurityContextPersistenceFilter:
   ├─ phát hiện context đã đổi
   ├─ save nếu cần, kể cả xử lý trước response commit/redirect
   └─ clear SecurityContextHolder
~~~

Vì thế đoạn code legacy này **có thể từng hoạt động**:

~~~java
// Code legacy; không đủ để duy trì login với default Spring Security 6.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
return ResponseEntity.ok().build();
~~~

Nếu không có component khác save, request sau trong Spring Security 6 sẽ không khôi phục context. Lưu ý **response OK** không chứng minh context được ghi; user có thể nhận HTTP 200 “login succeeded” rồi gặp redirect login ở request kế tiếp.

### 4.1. Response commit và redirect

Khi browser nhận redirect 302, response có thể được commit sớm. Nếu context cần tạo HTTP session và `Set-Cookie`, save **sau response commit** có thể quá muộn. Logic implicit cũ từng dùng response wrappers để xử lý sớm, nhưng explicit save mới đòi **auth component gọi `saveContext(...)` trước khi response bị commit**.

Đối với custom controller, thứ tự đúng cơ bản là:

~~~text
authenticate
   → áp policy SessionAuthenticationStrategy cần thiết
   → create context
   → set authenticated principal vào context
   → set SecurityContextHolder
   → repository.saveContext(context, request, response)
   → gửi HTTP 200 / redirect / JSON response
~~~

Không gọi `sendRedirect` hoặc ghi/flush response rồi mới save; không kỳ vọng repository có thể đặt session cookie sau khi headers đã được gửi.

### 4.2. Vì sao không sửa bằng setAuthentication trên context có sẵn?

Cách sau có thể làm logic khó quan sát hơn:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

Không chỉ thiếu `saveContext`, việc **sửa trực tiếp một SecurityContext có thể được chia sẻ/reuse** có thể dẫn tới race ở những tình huống session/request đồng thời. Tài liệu Spring Security khuyên tạo context mới:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(authentication);
SecurityContextHolder.setContext(fresh);
repository.saveContext(fresh, request, response);
~~~

Cần bảo đảm `repository` đúng với filter chain đang dùng và session policy cho phép lưu. Khi dùng custom `SecurityContextHolderStrategy`/nhiều ApplicationContexts, có thể inject strategy thay vì gọi static global; xem tài liệu `SecurityContextHolderStrategy`.

## 5. Cơ chế mới: SecurityContextHolderFilter và explicit save

Sơ đồ mặc định của Spring Security 6:

~~~text
Request đến:
  SecurityContextHolderFilter
     │
     ├─ gọi SecurityContextRepository.loadDeferredContext(request)
     ├─ cung cấp context cho SecurityContextHolderStrategy
     │
     ▼
  Authentication filter / Controller / Service
     │
     ├─ đọc Authentication hiện tại (nếu có)
     ├─ có thể tạo Authentication mới
     └─ nếu muốn persist → tự gọi repository.saveContext(...)
     │
     ▼
  Response
     │
     ▼
  SecurityContextHolderFilter clear context holder
     │
     └─ KHÔNG tự tìm thay đổi để save khi kết thúc request

Request tiếp theo:
  SecurityContextHolderFilter nạp từ repository
  hoặc trả anonymous nếu không tìm được context
~~~

### 5.1. “Explicit save” nghĩa là gọi phương thức nào?

Chữ ký của Spring Security 6.5:

~~~java
void saveContext(
        SecurityContext context,
        HttpServletRequest request,
        HttpServletResponse response);
~~~

`SecurityContextRepository.saveContext(...)` nhận **đầy đủ context + request + response**; không phải chỉ lưu `Authentication`, không phải `SecurityContextHolderStrategy.setContext(...)`, không phải `HttpSession.setAttribute("username", ...)`.

Ví dụ code đặt trong controller/filter có ba biến `context`/`request`/`response`:

~~~java
SecurityContextHolder.setContext(context);
securityContextRepository.saveContext(context, request, response);
~~~

Cần bảo đảm context chứa **Authentication đã được xác minh**; không đặt một `UsernamePasswordAuthenticationToken.authenticated(...)` do client điều khiển mà chưa gọi `AuthenticationManager.authenticate(...)`. Kẻ tấn công không được tự gửi `role`/`isAuthenticated` rồi biến thành session.

### 5.2. Built-in formLogin có còn tự duy trì phiên không?

**Có, nếu cấu hình session-based thông thường.** Với `UsernamePasswordAuthenticationFilter` (kế thừa `AbstractAuthenticationProcessingFilter`), Spring Security:

1. Tạo token chưa xác thực từ request.
2. Gọi `AuthenticationManager`/`AuthenticationProvider`.
3. Thực thi `SessionAuthenticationStrategy` sau khi thành công, tùy cấu hình.
4. Tạo `SecurityContext` và đặt Authentication vào holder.
5. Lưu context qua repository mà authentication filter đã được cấu hình.
6. Gọi remember-me/event/success handler rồi trả response.

Trong tài liệu phiên bản 6.5, phần authentication architecture diễn tả các bước của bộ lọc và nhấn mạnh khi cần persistence ở request sau phải có explicit `saveContext`. Code built-in filter thực hiện trách nhiệm này; **developer dùng `formLogin(...)` bình thường không phải tự viết `saveContext` trong controller của mình**.

Ngược lại, nếu developer **tự viết `POST /api/login` và chỉ gọi authenticationManager.authenticate(...)**, họ đã bỏ qua phần quản lý context và session của form filter. Khi đó trách nhiệm là của custom endpoint.

### 5.3. Basic/JWT/Resource Server

Một request `httpBasic()` hoặc Bearer JWT có thể được xác thực **độc lập mỗi lần**, không cần session. Khi client ngừng gửi Basic header/Bearer token, request sau có thể anonymous. Đừng kết luận “explicit save bị lỗi” khi hệ thống vốn được cấu hình stateless.

Ngược lại, nếu hệ thống chủ đích muốn lưu một xác thực ban đầu vào session, cần xác minh repository và semantics của **chính authentication filter đó**; chỉ thiết lập repository trên `SecurityContextHolderFilter` không đảm bảo mọi stateless filter sẽ tự dùng nó.

## 6. Minh họa Java 17 độc lập: holder tạm thời và kho lưu lâu hơn

Chương trình này **không dùng Spring**; nó là phép so sánh đơn giản về sự khác nhau giữa state trong request và state đã lưu cho request sau. Kho map trong ví dụ chỉ tồn tại trong một process và **không phải mô hình quản lý phiên an toàn**.

Tệp `ContextLifecycleDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ContextLifecycleDemo {
    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();
    private static final Map<String, String> SAVED =
            new HashMap<>();

    private static void beginRequest(String sessionKey) {
        CURRENT.set(SAVED.get(sessionKey));
    }

    private static void authenticate(String username) {
        CURRENT.set(username);
    }

    private static void explicitSave(String sessionKey) {
        SAVED.put(sessionKey, CURRENT.get());
    }

    private static void endRequest() {
        CURRENT.remove();
    }

    public static void main(String[] args) {
        beginRequest("lab-session");
        authenticate("alice");
        System.out.println("during-first-request=" + CURRENT.get());
        endRequest();

        beginRequest("lab-session");
        System.out.println("without-save=" +
                (CURRENT.get() == null ? "anonymous" : CURRENT.get()));
        endRequest();

        beginRequest("lab-session");
        authenticate("alice");
        explicitSave("lab-session");
        endRequest();

        beginRequest("lab-session");
        System.out.println("after-explicit-save=" + CURRENT.get());
        endRequest();
    }
}
~~~

Biên dịch/chạy bằng JDK 17+:

~~~bash
javac --release 17 ContextLifecycleDemo.java
java ContextLifecycleDemo
~~~

**Stdout chính xác:**

~~~text
during-first-request=alice
without-save=anonymous
after-explicit-save=alice
~~~

`CURRENT` đóng vai **context holder tạm thời**, `SAVED` đóng vai một repository mô phỏng, còn `beginRequest/endRequest` mô tả restore/clear. Chương trình không có Servlet session, cookie, CSRF, AuthenticationManager hoặc SecurityContext; **không copy HashMap/ThreadLocal này vào ứng dụng web**.

## 7. Ví dụ Spring Boot 3.5 / Spring Security 6.5 có thể chạy

Ví dụ này có **hai cơ chế login** trong cùng ứng dụng lab:

- **Built-in form login:** Spring Security xử lý `POST /login` và tự persist context theo cấu hình.
- **Custom JSON login:** controller xử lý `POST /api/manual-login`, gọi `AuthenticationManager` rồi **tự `saveContext(...)`**.

Endpoint `GET /api/me` dùng để chứng minh **request thứ hai** khôi phục được Authentication từ session. Default `POST /logout` của Spring Security xử lý cleanup và invalidation. App giữ CSRF **bật** cho cả form và custom login, vì đây là mô hình cookie/session. Test với `.with(csrf())`.

**Giới hạn:** đây là lab local có user/password test. Sản phẩm production phải bổ sung rate limiting, account lifecycle, dữ liệu thật, HTTPS, session fixation/concurrent sessions phù hợp, CSRF frontend wiring, audit, MFA và privacy policy. Custom JSON login chỉ được dùng nếu ứng dụng có lý do mạnh và đã rà soát đầy đủ policy; form login chuẩn thường đơn giản/an toàn hơn.

### 7.1. Gradle dependencies

Đặt trong `build.gradle` của project Spring Boot 3.5.x đã có Boot plugin/BOM, Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Không tự thêm version Spring Security 7.x cho riêng test module khi runtime dùng 6.5. `spring-security-test` cung cấp `formLogin()`, `csrf()`, authentication result matchers, còn `MockMvc` từ Spring Boot test.

### 7.2. Một file Java có cấu hình + controller

Tạo `src/main/java/example/contextsave/ExplicitSaveApplication.java`:

~~~java
package example.contextsave;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.DelegatingSecurityContextRepository;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ExplicitSaveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitSaveApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class DemoSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        // Chỉ mật khẩu lab, tuyệt đối không dùng lại ở hệ thống thật.
        UserDetails student = User.withUsername("student")
                .password(encoder.encode("lab-only-password-2026"))
                .roles("USER")
                .build();
        return new InMemoryUserDetailsManager(student);
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users, PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return new ProviderManager(List.of(provider));
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        // Dùng CHÍNH bean này ở filter chain và custom controller.
        return new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());
    }

    @Bean
    SessionAuthenticationStrategy manualSessionStrategy() {
        // Minh họa session fixation changeSessionId khi có session.
        // Không thay thế mọi session strategy/MFA/rate limit production.
        return new ChangeSessionIdAuthenticationStrategy();
    }

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {

        http.securityContext(context -> context
                .securityContextRepository(repository)
                .requireExplicitSave(true));

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/manual-login").permitAll()
                .anyRequest().authenticated());

        http.formLogin(Customizer.withDefaults());
        http.logout(Customizer.withDefaults());

        // CSRF GIỮ MẶC ĐỊNH, áp cả POST /api/manual-login.
        return http.build();
    }
}

record ManualLoginRequest(
        @NotBlank String username,
        @NotBlank String password) {
}

@RestController
class ManualLoginController {
    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;

    ManualLoginController(AuthenticationManager authenticationManager,
                          SecurityContextRepository repository,
                          SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
    }

    @PostMapping("/api/manual-login")
    ResponseEntity<Map<String, String>> login(
            @Valid @RequestBody ManualLoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        // Token chưa xác thực; provider kiểm password thật.
        Authentication candidate =
                UsernamePasswordAuthenticationToken.unauthenticated(
                        input.username(), input.password());

        Authentication verified =
                authenticationManager.authenticate(candidate);

        // Áp strategy tối thiểu đã cấu hình trước khi save.
        sessionStrategy.onAuthentication(verified, request, response);

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verified);
        SecurityContextHolder.setContext(context);

        // QUYẾT ĐỊNH để request sau còn Authentication.
        repository.saveContext(context, request, response);

        // Chỉ trả trạng thái chung, không trả cookie/password/hash.
        return ResponseEntity.ok(Map.of(
                "status", "AUTHENTICATED"));
    }

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("username", authentication.getName());
    }
}

@RestControllerAdvice
class SafeAuthErrors {

    @ExceptionHandler(AuthenticationException.class)
    ResponseEntity<Map<String, String>> invalidCredentials(
            AuthenticationException ignored) {
        // Không in username, password, Authentication hay exception.
        return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "INVALID_CREDENTIALS"));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, String>> invalidInput(
            MethodArgumentNotValidException ignored) {
        // Không trả FieldError.getRejectedValue() của password.
        return ResponseEntity.badRequest()
                .body(Map.of("error", "INVALID_REQUEST"));
    }
}
~~~

**Điều kiện compile:** một tệp chỉ có một public top-level class `ExplicitSaveApplication`; các class/record khác package-private. Trong thực tế nên tách file theo lớp. Các API `DaoAuthenticationProvider(UserDetailsService)`, `ProviderManager(List<AuthenticationProvider>)`, `SecurityContextRepository.saveContext(...)`, `ChangeSessionIdAuthenticationStrategy` và `HttpSecurity.securityContext(...)` thuộc nhánh Spring Security 6.5.

### 7.3. Giải thích thứ tự trong controller

- `AuthenticationManager.authenticate` **thực sự xác minh** password bằng provider có `UserDetailsService` + `PasswordEncoder`; không tạo authenticated token từ raw input mà không kiểm tra.
- `SessionAuthenticationStrategy.onAuthentication` được gọi trước khi save. `ChangeSessionIdAuthenticationStrategy` chỉ minh họa fixation protection với session hiện có; sản phẩm thật có thể cần composite strategy, concurrent session registry và nhiều policy khác.
- `SecurityContextHolder.createEmptyContext` tạo context mới, tránh sửa context chia sẻ/cũ.
- `SecurityContextHolder.setContext(context)` làm Authentication hiện diện trong request hiện tại.
- `repository.saveContext(context, request, response)` là **bước bắt buộc của custom controller** khi muốn duy trì authentication ở session cho request kế tiếp.
- `SecurityFilterChain` sử dụng **cùng repository bean**; nếu filter nạp repo A trong khi controller ghi repo B, test persistence có thể thất bại.
- CSRF được giữ bật; với JSON login dựa trên session cookie, phải có CSRF token phù hợp. `MockMvc` sẽ gửi bằng `with(csrf())`, không tắt CSRF để cho ví dụ chạy.
- `SafeAuthErrors` trả thông báo chung cho credential sai, tránh tiết lộ account tồn tại hay secret. Sản phẩm cần rate limit, lockout/abuse monitoring và audit an toàn.
- `formLogin` chuẩn vẫn tồn tại song song; nó có own filter/session handling, **không gọi controller `/api/manual-login`**.
- Endpoint `/api/me` trả username lab sau authentication; dự án thật cần quyết định có nên trả PII hay không.

**Không hiểu ví dụ là một login implementation production hoàn chỉnh.** Với MFA, remember-me, concurrent session limits, login events, account policies hoặc Spring Session phân tán, việc chỉ gọi `ChangeSessionIdAuthenticationStrategy` là chưa đủ. Hãy sử dụng cơ chế framework và test theo threat model.

### 7.4. Chạy thử qua browser/HTTP

Trong thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Khi chưa đăng nhập, `GET /api/me` (Accept: text/html) thường bị chuyển tới `/login`. Nếu mở `/login`, Spring Security tạo trang form mặc định có CSRF token; đăng nhập bằng tài khoản lab `student`/`lab-only-password-2026` có thể tạo session.

**Không nên dùng lệnh curl POST trực tiếp mà thiếu token CSRF rồi kết luận explicit save lỗi**. Với custom JSON login, cần gửi cookie session và CSRF token hợp lệ. Phần MockMvc phía dưới mô tả chính xác điều kiện test; chạy qua browser thực phải thực hiện CSRF token handshake theo cấu hình frontend.

**Không dùng mật khẩu ví dụ ở production.** HTTP chỉ cho local lab; hệ thống thực yêu cầu HTTPS, cookie flags, secrets policy và chống brute force.

## 8. Kiểm thử Spring Security Test: chứng minh request thứ hai khôi phục context

Đây là phần then chốt của bài: **HTTP 200 ngay sau `saveContext` không đủ**. Test phải thực hiện một request thứ hai có cùng session và khẳng định principal được khôi phục.

Tệp `src/test/java/example/contextsave/ExplicitSaveApplicationTest.java`:

~~~java
package example.contextsave;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class ExplicitSaveApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void customLoginExplicitlySavesForNextRequest() throws Exception {
        MvcResult login = mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {
                      "username": "student",
                      "password": "lab-only-password-2026"
                    }
                    """))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("AUTHENTICATED"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        // Request thứ hai không gửi password nữa.
        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(authenticated().withUsername("student"))
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void builtInFormLoginAlsoPersistsContext() throws Exception {
        MvcResult login = mvc.perform(formLogin()
                .user("student")
                .password("lab-only-password-2026"))
            .andExpect(status().is3xxRedirection())
            .andExpect(authenticated().withUsername("student"))
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("student"));
    }

    @Test
    void manualLoginWithWrongPasswordDoesNotCreateUsableLogin()
            throws Exception {
        mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"wrong"}
                    """))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.error")
                    .value("INVALID_CREDENTIALS"));
    }

    @Test
    void manualLoginWithoutCsrfIsRejectedBeforeAuthentication()
            throws Exception {
        mvc.perform(post("/api/manual-login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"lab-only-password-2026"}
                    """))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestHasNoPersistentAuthentication()
            throws Exception {
        mvc.perform(get("/api/me")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void builtInLogoutInvalidatesSessionSavedByManualLogin()
            throws Exception {
        MvcResult login = mvc.perform(post("/api/manual-login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                    {"username":"student","password":"lab-only-password-2026"}
                    """))
            .andExpect(status().isOk())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);
        assertNotNull(session);
        assertFalse(session.isInvalid());

        mvc.perform(post("/logout")
                .session(session)
                .with(csrf()))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/login?logout"));

        assertTrue(session.isInvalid());

        // Không tái sử dụng session đã bị invalidated.
        mvc.perform(get("/api/me")
                .accept(MediaType.TEXT_HTML))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Có **6 HTTP tests** ở `ExplicitSaveApplicationTest`. Các ca xác minh:

1. Custom login: response 200 **và** GET tiếp theo dùng cùng session trả authenticated.
2. Form login: built-in filter cũng lưu context, không cần controller tự save.
3. Sai password: không phát usable login, trả 401 chung.
4. Thiếu CSRF: 403; không phải lỗi `saveContext`.
5. Anonymous request: vẫn cần login.
6. Logout: session được invalidate, không chỉ redirect.

Chạy bằng Gradle wrapper:

~~~bash
./gradlew test --tests example.contextsave.ExplicitSaveApplicationTest
~~~

Kết quả **dự kiến**: 6 test pass nếu môi trường, các starter và Spring Security 6.5 khớp. Bài không tuyên bố đã thực thi build trong một repository thực.

### 8.1. Unit test cô lập: setContext chưa phải saveContext

Một test nhỏ với `HttpSessionSecurityContextRepository` cho thấy chỉ set holder không tự ghi session. Tệp `src/test/java/example/contextsave/ExplicitRepositoryTest.java`:

~~~java
package example.contextsave;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;

import static org.junit.jupiter.api.Assertions.*;

class ExplicitRepositoryTest {

    @Test
    void settingHolderDoesNotWriteHttpSessionRepository() {
        HttpSessionSecurityContextRepository repo =
                new HttpSessionSecurityContextRepository();
        MockHttpServletRequest request =
                new MockHttpServletRequest();
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        SecurityContext context =
                SecurityContextHolder.createEmptyContext();
        context.setAuthentication(new TestingAuthenticationToken(
                "student", "test-only", "ROLE_USER"));

        try {
            SecurityContextHolder.setContext(context);

            // Chỉ có context trong thread, chưa persist.
            assertFalse(repo.containsContext(request));

            repo.saveContext(context, request, response);

            // Đã có context trong session của request này.
            assertTrue(repo.containsContext(request));
        }
        finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Test này kiểm **API lưu context**, không chạy filter chain hoặc HTTP login thật; nó bổ sung cho sáu integration tests, không thể thay thế chúng. Chạy:

~~~bash
./gradlew test --tests example.contextsave.ExplicitRepositoryTest
~~~

**Giới hạn:** `TestingAuthenticationToken` chỉ là test fixture; production phải dùng `AuthenticationManager`/provider đã xác minh credentials. Chưa có CSRF/session fixation/authorization trong unit test này.

### 8.2. Không dùng @WithMockUser để chứng minh persistence

Một test như:

~~~java
mvc.perform(get("/api/me").with(user("student")))
    .andExpect(status().isOk());
~~~

chỉ cung cấp principal giả cho **request đang test**. Nó không xác minh password, không kiểm saveContext, và không chứng minh session có thể phục hồi ở request kế tiếp. `@WithMockUser` hoặc `with(user(...))` hữu ích cho authorization unit tests, nhưng **không thay** kiểm thử hai request với session thực từ login flow.

### 8.3. MockMvc không kiểm được mọi vấn đề của browser

`MockHttpSession` là session mô phỏng: nó chứng minh repository/filter trong application context biết đọc-ghi qua request. Nó chưa chứng minh:

- Browser thật lưu và gửi `JSESSIONID` theo Cookie `Secure`/`SameSite`/`Path`/`Domain`.
- Spring Session + Redis/JDBC hoạt động đúng trong nhiều replicas.
- Reverse proxy/HTTPS/load balancer không làm mất cookie.
- Session ID được rotate đúng khi có concurrent logins và policy.
- OAuth2/OIDC callback/third-party cookies/MFA cũng đúng.
- Kịch bản mạng khi response commit, redirect bị bỏ dở hoặc session store unavailable.

Vì vậy thêm E2E/browser và staging integration test nếu mục tiêu là xác nhận login end-to-end trên hạ tầng production.

## 9. Đăng nhập thủ công: khi nào còn cần những bước khác?

`SecurityContextRepository.saveContext` chỉ giải quyết **persistence của context**. Một login hoàn chỉnh còn phải có:

| Thành phần | Vai trò | Nếu quên |
| --- | --- | --- |
| `AuthenticationManager`/provider | Kiểm chứng credential và account status | Có thể tạo Authentication giả → nghiêm trọng |
| `SessionAuthenticationStrategy` | Fixation/concurrency/session policy | Có session nhưng có thể vi phạm chính sách |
| `SecurityContextRepository` | Lưu/khôi phục context | Request sau anonymous |
| `RememberMeServices` (nếu bật) | Xử lý remember-me theo policy | Khác behavior built-in form login |
| CSRF | Chặn cross-site login/logout/state change | Login CSRF hoặc thao tác trạng thái không được bảo vệ |
| Success/failure handlers | Kiểm soát HTTP response, redirect, error mapping | Login UI bị loop, trả 200 sai hoặc rò thông tin |
| MFA/step-up | Đủ yếu tố xác thực theo policy | Lưu phiên có quyền quá sớm |
| Audit/rate limiting | Giám sát abuse, chống đoán password | Bị brute force và khó điều tra |
| Session lifecycle | Invalidate/logout/timeout/refresh | Session sống quá lâu hoặc không thu hồi |
| Idempotency/transaction | Ghi thay đổi account và sự kiện cần bền vững | Kết quả từng phần khó khôi phục |

Trong ví dụ lab, `SessionAuthenticationStrategy` chỉ là `ChangeSessionIdAuthenticationStrategy`; không tự xử lý concurrent sessions, OAuth2, remember-me hay MFA. Khi ứng dụng thực hiện các yêu cầu đó, hãy cấu hình/kiểm chứng từng chiến lược đúng như built-in filter hoặc dùng trực tiếp filter chuẩn.

### 9.1. Save trước hay sau MFA?

Nếu policy yêu cầu 2FA, “password đúng” chỉ là **một factor đã được kiểm tra**. Không lưu Authentication có đầy đủ authorities/roles vào session nếu bước MFA chưa hoàn tất, trừ khi ứng dụng cố tình biểu diễn trạng thái **partial authentication** và authorization rules chặn tài nguyên cần factor tiếp theo.

~~~text
Password accepted
    │
    ├─ Nếu MFA required: tạo trạng thái pending CHỈ có quyền làm MFA
    │                     (không cấp full business authorities)
    │
    └─ MFA completed → chuyển sang Authentication đủ factors
                        → lưu context/phiên theo policy
                        → truy cập protected resources
~~~

Mỗi thay đổi trạng thái authentication trong custom flow cần quyết định **có nên lưu context mới hay không**. Không chỉ set holder rồi chờ `SecurityContextHolderFilter` tự detect như phiên bản 5.

### 9.2. Khi điều chỉnh roles sau login

Nếu ứng dụng tự đổi `Authentication` hoặc authorities ở request hiện tại và mong request sau dùng role mới, cũng phải xác định cách repository/session nhận context mới. Đừng sửa principal dùng chung giữa các session một cách không đồng bộ hoặc kỳ vọng `@PreAuthorize` tự save thay bạn. Với thay đổi nhạy cảm, có thể cần invalidate/re-authentication thay vì âm thầm nâng quyền phiên hiện tại.

## 10. Logout và clear SecurityContext: cũng phải đồng bộ repository

### 10.1. Logout mặc định đã có trách nhiệm cleanup

Spring Security Servlet cung cấp logout support. Khi `POST /logout` có CSRF hợp lệ, các logout handlers mặc định thường:

- Invalidate HTTP session.
- Clear `SecurityContextHolderStrategy`.
- Clear `SecurityContextRepository` theo cơ chế handler.
- Xử lý remember-me và CSRF token phù hợp nếu được bật.
- Phát `LogoutSuccessEvent` và gọi success handler (thường redirect `/login?logout`).

Vì thế **đừng thay thế logout chuẩn bằng một controller đơn giản chỉ gọi `SecurityContextHolder.clearContext()`**. Nó có thể chỉ xóa holder của request hiện tại, trong khi session cũ vẫn chứa Authentication và request tiếp theo tiếp tục được xem là đã đăng nhập.

### 10.2. Vì sao clearContext() riêng lẻ chưa đủ?

~~~java
// SAI nếu còn Authentication đã lưu trong HTTP session.
SecurityContextHolder.clearContext();
return ResponseEntity.ok().build();
~~~

Request sau lại đọc từ repository và nhận context cũ. Với custom logout, Spring khuyến nghị dùng `SecurityContextLogoutHandler` và cấu hình cleanup thích hợp hoặc — tốt hơn — giữ `LogoutFilter`/logout DSL.

Minh họa **bên trong một controller đã có handler và request/response**:

~~~java
SecurityContextLogoutHandler handler =
        new SecurityContextLogoutHandler();
handler.setSecurityContextRepository(repository);
handler.logout(request, response,
        SecurityContextHolder.getContext().getAuthentication());
~~~

Snippet cần import `org.springframework.security.web.authentication.logout.SecurityContextLogoutHandler` và `SecurityContextRepository`, chỉ là **đoạn minh họa**. Trong production phải xét việc invalidate session, remember-me, CSRF, các token ngoài session và thông báo/audit; không copy snippet rồi tuyên bố logout toàn hệ thống hoàn chỉnh.

**Đừng nghĩ explicit save nghĩa là luôn phải gọi `saveContext(emptyContext)` sau `SecurityContextLogoutHandler` chuẩn**: handler/LogoutFilter có trách nhiệm cleanup riêng. Hãy tránh ghi lại một context đã bị logout vì xử lý sai thứ tự.

### 10.3. Logout cục bộ không tự thu hồi JWT/IdP session

- Xóa context khỏi HTTP session **không** tự revoke access token JWT stateless đang còn hạn.
- Xóa `JSESSIONID` phía client mà không invalidate server session chưa đủ.
- Local logout không đồng nghĩa đã sign out khỏi mọi session của OAuth2/OIDC IdP.
- Nếu app có refresh tokens, remember-me tokens hoặc Spring Session phân tán, cần plan thu hồi riêng.
- Unit test `SecurityContextHolder.clearContext()` pass không chứng minh logout HTTP hoạt động.

## 11. Những lỗi nâng cấp thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| Login POST 200 nhưng GET ngay sau bị redirect /login | Custom controller chỉ `setContext`, không `saveContext` | Test GET protected request khác với cùng session |
| Form login chuẩn vẫn hoạt động, custom JSON login không | Built-in filter save; custom login bỏ bước | So cấu hình repo và custom controller |
| Chỉ một node mất login state | Session store không chia sẻ/khác secret/cookie | Kiểm LB, Spring Session, sticky/shared storage |
| Có session nhưng `SecurityContext` không tồn tại | Ghi vào repo khác, save anonymous/empty hoặc sai session | Kiểm bean/repo chain và session ID đã scrub |
| Context dùng được trong ERROR dispatch nhưng không request sau | Chỉ dùng `RequestAttributeSecurityContextRepository` | Dùng thêm HttpSession repository khi muốn persistence |
| Custom filter set Authentication rồi GET kế tiếp vẫn anonymous | Filter chưa gọi save hoặc chỉ set ThreadLocal | Bổ sung save trước response commit |
| Đã gọi save nhưng không thấy JSESSIONID | STATELESS, `NullSecurityContextRepository`, allowSessionCreation=false, proxy, cookie | Kiểm policy và repo, tránh bật session nếu API stateless |
| Sau POST login request 2 bị 403 | Context có thể đã lưu nhưng user thiếu role/authority/MFA | Phân biệt authentication vs authorization |
| POST login trả 403 ngay | CSRF thiếu/sai | Kiểm `CsrfFilter` trước khi sửa repository |
| Sau logout vẫn authenticated | Chỉ clear holder, context cũ còn trong session | Dùng `LogoutFilter`/`SecurityContextLogoutHandler`, test session invalidation |
| Sau logout Basic/Bearer request vẫn vào được | Basic/JWT lại được xác thực trên mỗi request | Đổi credential/revoke token nếu cần; không phải persistence bug |
| Login đột nhiên tạo quá nhiều session | Eager session policy, request cache, custom repo | Kiểm session minimization và tracing, không chỉ explicit save |
| Đổi `requireExplicitSave(false)` thì login tạm hết lỗi | Legacy code dựa implicit save | Sửa custom code trước khi trở về default |
| Tự gắn 2 filters `HolderFilter` + `PersistenceFilter` | Cấu hình trùng/conflict | Chỉ dùng một, kiểm chain thực tế |
| Controller trả status đúng nhưng browser bị login loop | Cookie Domain/SameSite/Secure, redirect, session store | Browser/staging E2E |
| `@WithMockUser` test pass nhưng login thực fail | Mock user bỏ qua authentication/persistence | Dùng formLogin/custom POST qua filters và follow-up GET |
| `SessionAuthenticationStrategy` không áp dụng | Spring 6 không mặc định dựa `SessionManagementFilter` | Gọi strategy trong auth mechanism đúng thời điểm |
| Context bị lưu trước khi MFA xong | App lưu full Authentication quá sớm | Lưu partial state với quyền giới hạn hoặc chờ full MFA |
| Redirect trước khi save | Response commit, session cookie không thể thêm | Save trước `sendRedirect`/body flush |

### 11.1. Khi kiểm log, ghi gì và tránh gì?

Ghi audit như:

~~~text
event=MANUAL_LOGIN stage=AUTHENTICATED
event=MANUAL_LOGIN stage=CONTEXT_SAVE_ATTEMPTED
event=MANUAL_LOGIN stage=RESPONSE_SENT
event=PROTECTED_REQUEST stage=CONTEXT_RESTORED
~~~

Bốn dòng trên là **mẫu event do ứng dụng tự đặt**, không phải Spring Security tự phát đầy đủ. Không ghi raw password, `JSESSIONID`, `Authorization`, CSRF token, hoặc toàn bộ serialized `SecurityContext`/`Authentication`. Có thể dùng random correlation ID do server phát hành để nối các bước trong giới hạn retention/privacy.

Không tự kết luận “save thành công” chỉ vì log trước khi gọi `saveContext` đã in — còn cần xử lý exception và kiểm hành vi ở request sau.

## 12. Ma trận kiểm thử cho migration 5.x → 6.x

| ID | Tình huống | Điều phải đúng |
| --- | --- | --- |
| C01 | Custom login chỉ set holder, không save | Request hiện tại có Authentication; request sau không tự phục hồi |
| C02 | Custom login set + save với HttpSession repo | Request sau có cùng session phục hồi Authentication |
| C03 | Built-in formLogin mặc định | Tự xử lý persistence, không cần controller viết save |
| C04 | Sai username/password | Không tạo session authenticated |
| C05 | Thiếu CSRF khi POST login dựa cookie | 403, không phải lỗi explicit save |
| C06 | Save trước redirect/response commit | Cookie/session context được ghi kịp |
| C07 | Save sau response commit | Được phát hiện là triển khai sai và sửa |
| C08 | Repository chỉ RequestAttribute | Có thể có context trong dispatch cùng request; request sau không có |
| C09 | Delegating repository có HttpSession | Context bền giữa request nếu save và session hợp lệ |
| C10 | NullSecurityContextRepository | Không lưu HTTP session, đúng với stateless policy |
| C11 | SessionCreationPolicy.STATELESS | Không ép tạo session cho API bearer |
| C12 | SessionCreationPolicy.IF_REQUIRED | Repo có thể tạo session khi login cần |
| C13 | Custom repository đọc/ghi không cùng instance/backend | Phát hiện mismatch và sửa config |
| C14 | Logout chỉ `clearContext()` | Có thể còn context cũ, test phải bắt được |
| C15 | Built-in POST /logout có CSRF | Session invalidated và request sau anonymous |
| C16 | Custom logout với handler thích hợp | Clear repository và session đúng policy |
| C17 | Basic request không gửi header ở request sau | Không tự động còn authenticated do Basic |
| C18 | JWT request không gửi Bearer ở request sau | Resource server từ chối nếu không còn cơ chế auth khác |
| C19 | Password đúng nhưng MFA chưa xong | Không cấp full session/roles |
| C20 | Session fixation strategy sau manual auth | Session ID được đổi theo strategy khi phù hợp |
| C21 | Concurrent session control | Custom filter gọi đúng strategy, registry/hạn chế hoạt động |
| C22 | Session hết hạn trước request tiếp theo | Không tự resurrect Authentication từ ThreadLocal |
| C23 | Có 2 replicas/Redis Spring Session | State được đọc đúng và không leak user |
| C24 | Cookie Secure/SameSite/Domain/Path sai | Browser flow test phát hiện login loop |
| C25 | @WithMockUser trong test | Không coi là bằng chứng save/restore |
| C26 | MockMvc login + second GET cùng MockHttpSession | Chứng minh persistence trong application |
| C27 | Multiple SecurityFilterChain | Test đúng chain chứa repository và auth mechanism |
| C28 | Async request/thread khác | Không lấy ThreadLocal persistence làm session persistence |
| C29 | Request ERROR dispatch sau exception | RequestAttribute repository giúp truy cập context theo cơ chế được cấu hình |
| C30 | Save anonymous/empty context | Không tạo session authenticated ngoài ý muốn |
| C31 | Sau migration bỏ `requireExplicitSave(false)` | Toàn bộ custom auth flows vẫn qua tests |
| C32 | Người dùng đổi role hoặc logout | Context cũ được xử lý theo session invalidation/refresh policy |

Không cần “test từng class riêng” để chứng minh migration. Giá trị lớn nhất là **tập kiểm thử theo hành vi**: POST login thật → nhận session → GET tài nguyên cần authenticated → logout → GET lại bị chặn. Test thêm các biến thể custom, built-in, CSRF, stateless và distributed sessions.

## 13. Migration plan không làm gián đoạn người dùng

### Pha 1 — Inventory

1. Xác định phiên bản `spring-security-web/config/test` và Spring Boot BOM của từng module; không trộn 5.x/6.x/7.x tùy tiện.
2. Liệt kê mọi `SecurityFilterChain` và filter/context repository đang dùng.
3. Tìm nơi gọi `SecurityContextHolder.setContext`, `getContext().setAuthentication`, `clearContext`, implement custom `OncePerRequestFilter`, custom success handler hoặc login controller.
4. Kiểm custom `AuthenticationManager`, JWT/basic/OIDC flows và có dùng SessionManagementFilter mặc định trước đây hay không.
5. Kiểm session policy `ALWAYS`/`IF_REQUIRED`/`NEVER`/`STATELESS`, session registry, save strategies, remember-me và CSRF.
6. Kiểm repository per chain: HttpSession/RequestAttribute/Delegating/Null/custom.
7. Đọc tests hiện có; tách tests mock principal với tests chứng minh persistence qua hai requests.

### Pha 2 — Chuẩn hóa contract

1. Mỗi authentication flow ghi rõ **stateful** hay **stateless**.
2. Với stateful custom flow, xác định **ai gọi saveContext**, đúng repository nào và thời điểm trước response commit.
3. Với built-in form login, dựa vào trách nhiệm của framework, không thêm save bừa trong controller.
4. Với custom logout, ưu tiên logout DSL/handler chuẩn; nếu buộc tự viết phải clear và persist việc clear theo repository.
5. Với MFA, xác định mốc nào được lưu full Authentication.
6. Với concurrent session policy, đưa SessionAuthenticationStrategy vào auth mechanism thay vì chỉ gắn vào DSL cũ.

### Pha 3 — Chuyển qua behavior mới

Trong hệ còn ở Spring Security 5.8, có thể bật `requireExplicitSave(true)` như bước luyện migration, sửa custom code, rồi nâng lên Spring Security 6. Với project Spring Security 6.x, giữ default mới; chỉ bật `false` như giải pháp ngắn hạn có kế hoạch bỏ rõ ràng.

Kiểm tra **từng URL/chain/HTTP method**. Một ứng dụng có form login thành công chưa có nghĩa JSON login, token exchange hoặc custom impersonation/step-up flow cũng đã đúng.

### Pha 4 — Kiểm thử và rollout

1. Unit test repository behavior và error categories.
2. MockMvc integration test login/CSRF/session/logout.
3. E2E browser test qua proxy/HTTPS/cookie chính xác.
4. Test multi-node khi dùng Spring Session hoặc session replication.
5. Đảm bảo audit không chứa raw credentials, context, session IDs.
6. Feature flag/gradual rollout; theo dõi tỷ lệ login success handler vs protected request success, không chỉ HTTP 200 của login.
7. Có rollback config/code an toàn, tránh rollback khiến phiên cũ đọc sai state và khiến người dùng mất quyền.
8. Khi đã ổn định, xóa cấu hình tương thích legacy và cập nhật ADR/runbook.

### Pha 5 — Theo dõi sau triển khai

Đo các dấu hiệu có giá trị nhưng không thu bí mật:

- Login endpoint 200/302 thành công.
- Tỷ lệ **request protected ngay sau login** được authorize.
- Tỷ lệ redirect loop về login.
- Session creation/invalidations hợp lệ.
- Tỷ lệ CSRF 403, unauthorized 401, forbidden 403 được phân nhóm.
- Errors từ repository/store phân tán.
- Số lượt logout/expiration và session policy reject.
- Khác biệt theo chain/auth method và deploy version, tránh đánh đồng user actions với mỗi JWT verification.

**Bản chất của migration:** không phải “làm sao để `setContext` lại tự save như cũ”, mà là chuyển sang kiến trúc nơi **component tạo hoặc xóa authentication chịu trách nhiệm rõ ràng về persistence**.

## 14. Câu hỏi tự kiểm tra

1. `SecurityContextHolder.setContext` và `SecurityContextRepository.saveContext` khác nhau thế nào?
2. Filter nào mặc định có logic tự phát hiện/ghi context ở Spring Security 5.x?
3. `SecurityContextHolderFilter` trong Spring Security 6 có tự save khi request kết thúc không?
4. Spring Security 6 có làm built-in formLogin “không lưu session” theo mặc định không?
5. `requireExplicitSave(true)` được dùng để diễn tả behavior gì?
6. `requireExplicitSave(false)` có nên giữ mãi trong migration không?
7. `HttpSessionSecurityContextRepository` khác `RequestAttributeSecurityContextRepository` ở điểm nào?
8. Default `DelegatingSecurityContextRepository` của Spring Security 6 thường delegate tới đâu?
9. Vì sao `NullSecurityContextRepository` có thể là lựa chọn đúng cho API stateless?
10. Vì sao nên tạo `SecurityContextHolder.createEmptyContext` thay vì sửa đối tượng context có sẵn?
11. Khi custom login redirect, `saveContext` nên gọi trước hay sau `sendRedirect`?
12. Có phải chỉ cần saveContext là tự động có session fixation, MFA, remember-me và rate limiting không?
13. Vì sao `SecurityContextHolder.clearContext()` trong controller logout có thể chưa đủ?
14. Muốn kiểm rõ login persistence, cần bao nhiêu HTTP requests và gắn session thế nào?
15. `@WithMockUser` pass có xác minh persistence thực tế không?
16. Tại sao custom auth mechanism trong Spring Security 6 cần quan tâm `SessionAuthenticationStrategy`?
17. Khi request thứ hai trả 403, có thể coi context không được lưu không?
18. Khi JWT/Bearer API không giữ authentication qua request, đây luôn là lỗi không?
19. Làm sao xác định controller và filter đang dùng cùng repository?
20. Vì sao Spring Security giảm implicit writes vào `HttpSession`?

**Đáp án định hướng:** (1) holder là state hiện tại, save là ghi cho request sau; (2) SecurityContextPersistenceFilter; (3) không; (4) không, built-in filters xử lý; (5) semantics chỉ đọc + explicit save; (6) không, ưu tiên sửa code; (7) session liên request vs attribute cùng request; (8) RequestAttribute và HttpSession; (9) auth lại từng request; (10) tránh chia sẻ/mutation ngoài ý muốn; (11) trước; (12) không; (13) repo/session vẫn có context cũ; (14) ít nhất login rồi một request protected cùng session; (15) không; (16) session filters cũ không tự làm hết; (17) chưa chắc, có thể thiếu role; (18) không, stateless là đúng thiết kế; (19) cấu hình/bean và tests; (20) rõ trách nhiệm, hiệu suất và tránh ghi thừa.

## 15. Checklist cuối bài

- [ ] Đã phân biệt đúng Spring Security 5 implicit save và Spring Security 6 explicit save.
- [ ] Không gắn cả `SecurityContextPersistenceFilter` và `SecurityContextHolderFilter`.
- [ ] Repository được cấu hình thống nhất giữa filter chain và custom auth components.
- [ ] Custom login tạo Authentication qua provider, áp session policy, set context và `saveContext` trước response.
- [ ] Built-in form login để framework tự thực hiện persistence đúng flow.
- [ ] Không dùng `setContext`/`ThreadLocal` như bằng chứng login liên request.
- [ ] Form/JSON login dựa cookie/session giữ CSRF đúng kiến trúc; không tắt toàn app.
- [ ] Custom logout dùng handler/filter chuẩn; không chỉ clear holder.
- [ ] Stateless JWT/Basic có chính sách riêng, không cố lưu session ngoài contract.
- [ ] Unit + MockMvc tests quan sát cả request đầu và request protected sau với cùng session.
- [ ] Có tests CSRF, sai credential, logout, MFA, role và session policy.
- [ ] Có E2E browser tests cookie/proxy/HTTPS, distributed sessions khi cần.
- [ ] Audit/traces không chứa password, token, session ID hay full Authentication.
- [ ] Compatibility `requireExplicitSave(false)` được dùng có thời hạn, có plan loại bỏ.
- [ ] Không tuyên bố “login hoàn tất” chỉ từ status 200/302 của request đầu.

## 16. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Handling Logouts](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html)
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html)
- [Spring Security 6.5 — HttpSessionSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/HttpSessionSecurityContextRepository.html)
- [Spring Security 6.5 — DelegatingSecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/DelegatingSecurityContextRepository.html)
- [Spring Security 6.5 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html)
- [Spring Security 6.5 — SecurityContextHolderFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextHolderFilter.html)
- [Spring Security 6.5 — SecurityContextPersistenceFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextPersistenceFilter.html)
- [Spring Security 6.5 — Testing Servlet Authentication with MockMvc](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/authentication.html)
- [Spring Security 6.5 — Testing Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/form-login.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Framework — Servlet Session and Testing MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html)
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
