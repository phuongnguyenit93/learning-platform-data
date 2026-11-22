# Lưu ngữ cảnh khi đăng nhập tùy chỉnh và trước khi response được hoàn tất

Giả sử ứng dụng Java/Spring Security có API đăng nhập tự viết `POST /api/login`. Controller nhận username/password, gọi `AuthenticationManager.authenticate(...)` thành công, đặt kết quả vào `SecurityContextHolder` và trả HTTP 200. Ngay sau đó, trình duyệt gửi cookie phiên tới `GET /api/me` — nhưng server lại trả 401 hoặc coi request là anonymous. Vì sao **request đăng nhập vừa thành công** mà **request kế tiếp không giữ được đăng nhập**?

Nguyên nhân rất thường gặp trong Spring Security 6 Servlet: **đặt `Authentication` vào `SecurityContextHolder` chỉ tác động tới ngữ cảnh đang thực thi; muốn giữ nó qua HTTP request khác, custom authentication phải lưu qua `SecurityContextRepository.saveContext(context, request, response)`.** Việc lưu cần được thực hiện **trước khi `HttpServletResponse` bị commit** (gửi headers/body/redirect hoặc flush làm response hoàn tất ở mức HTTP), đặc biệt khi repository cần tạo `HttpSession` và gửi `Set-Cookie` chứa session ID mới. Nếu response đã commit, ứng dụng có thể không tạo/gửi được session cookie đúng lúc, và các request sau không thể khôi phục context.

Đây là bài Knowledge thuộc **Ngữ cảnh Servlet** của chủ đề *Spring Security - authentication*. Bài phân biệt **xác thực — đặt context — lưu context — phát response — nạp context ở request sau**, triển khai ví dụ Spring Boot 3.x/Java 17+ với custom login REST, session fixation protection, CSRF và MockMvc tests; đồng thời giải thích response commit race, repo mặc định, các chiến lược session và lỗi thường gặp.

**Nguyên tắc nhớ nhanh:** Sau khi `AuthenticationManager` xác minh credential, tạo **`SecurityContext` mới**, đặt `Authentication` đáng tin vào đó, `setContext` cho request hiện tại, và **`saveContext` vào đúng repository trước khi trả/commit response**. Đừng mong một biến `ThreadLocal` tự lưu thành phiên đăng nhập. Với JWT/stateless, quy trình khác: client cần mang token ở request sau, không dựa vào lưu `HttpSession`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `SecurityContextHolder`, `SecurityContextHolderStrategy`, `SecurityContext`, `Authentication`, `SecurityContextRepository` và `HttpSession`.
2. Diễn giải hành vi **explicit save** trong Spring Security 6: `SecurityContextHolderFilter` chủ yếu nạp context; custom auth phải lưu nếu cần tồn tại qua requests.
3. Nhận biết điểm `HttpServletResponse` đã commit, hậu quả của gọi `sendRedirect`, `sendError`, `flushBuffer`, flush writer hoặc streaming trước `saveContext`.
4. Viết login controller/filter xác minh credential qua `AuthenticationManager`, xây context mới, gọi `setContext` và `saveContext` đúng thứ tự.
5. Cấu hình **cùng một `SecurityContextRepository`** cho security filter chain và custom login; hiểu sự khác nhau giữa `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `DelegatingSecurityContextRepository` và `NullSecurityContextRepository`.
6. Không bỏ qua session fixation protection, CSRF và các session authentication strategy chỉ vì tự viết endpoint login.
7. Chạy Spring Boot/MockMvc để chứng minh: login đúng tạo session → request khác được authenticated; thiếu save → phiên không được duy trì; login sai/thiếu CSRF bị từ chối; user đã login nhưng thiếu quyền vẫn 403.
8. Kiểm tra những giới hạn còn lại: async response, multiple filter chains, request cache, logout, remember-me, stale authorities và nhiều server.

## 2. Ba ranh giới: xác thực, lưu trên thread, lưu qua requests

| Thành phần | Trách nhiệm | Điều KHÔNG tự bảo đảm |
| --- | --- | --- |
| `AuthenticationManager` | Tiếp nhận `Authentication` chưa xác thực, gọi provider để kiểm credential và trả kết quả hợp lệ hoặc ném exception. | Không tự lưu kết quả vào `HttpSession` khi được gọi trực tiếp từ controller. |
| `Authentication` | Chứa principal, credentials, authorities và trạng thái authentication. | Không tự trở thành phiên HTTP. |
| `SecurityContext` | Container chứa `Authentication` của execution/request. | Không tự gửi cookie phiên. |
| `SecurityContextHolder` / `SecurityContextHolderStrategy` | Gắn context với thread/execution hiện tại (mặc định ThreadLocal trong Servlet). | Không tự lưu context cho request khác; không tự verify password. |
| **`SecurityContextRepository`** | Đọc/lưu context theo vòng đời HTTP: session, request attribute hoặc cơ chế khác. | Không tự xác minh credential; không phải mọi repo lưu qua nhiều request. |
| `SecurityContextHolderFilter` | Nạp/defer nạp context từ repository vào holder và dọn scope request. | Trong cấu hình explicit-save, không tự quan sát `setContext` rồi persist. |
| `HttpServletResponse` | Mang status, headers, cookie và body tới client. | Không bảo đảm thêm được `Set-Cookie` sau khi đã commit. |

Có **hai vị trí lưu hoàn toàn khác nhau**:

- **Trong execution hiện tại:** `SecurityContextHolderStrategy.setContext(context)` giúp code downstream của *request này* đọc `Authentication`.
- **Qua HTTP request mới:** `SecurityContextRepository.saveContext(context, request, response)` giúp repository ghi vào session/nguồn lưu thích hợp; filter ở request mới nạp lại từ client cookie/session ID.

Một controller có thể gọi `SecurityContextHolder.getContext().getAuthentication()` ngay sau `setContext` và thấy Alice, nhưng điều đó chỉ chứng minh **ThreadLocal của request đang chạy** đã có giá trị. Bài test quan trọng là **request mới mang cookie** có khôi phục được Alice không.

### 2.1 Sơ đồ request đăng nhập và request kế tiếp

```text
REQUEST A: POST /api/login
    |
    v
CSRF/filter chain (nếu dùng cookie session)
    |
    v
Custom controller / authentication filter
    |
    +--> UsernamePasswordAuthenticationToken.unauthenticated(...)
    +--> AuthenticationManager.authenticate(...)
    |        +--> ProviderManager / DaoAuthenticationProvider
    |        +--> UserDetailsService + PasswordEncoder + status
    |
    +--> SessionAuthenticationStrategy (fixation, CSRF... nếu custom)
    |
    +--> SecurityContext context = createEmptyContext()
    +--> context.setAuthentication(verified)
    +--> SecurityContextHolderStrategy.setContext(context)
    +--> SecurityContextRepository.saveContext(context, req, resp)
    |        +--> HttpSession ghi SPRING_SECURITY_CONTEXT
    |        +--> nếu cần tạo session: gửi Set-Cookie/JSESSIONID
    |
    +--> Trả 200 / redirect / response body; response commit
    |
    v
Servlet security filter cleanup ThreadLocal

REQUEST B: GET /api/me (trình duyệt mang cookie phiên)
    |
    v
SecurityContextHolderFilter / SecurityContextRepository
    |
    +--> tìm HttpSession theo session ID
    +--> nạp SecurityContext chứa Alice
    |
    v
Authorization: authenticated?
    |
    v
Controller nhận Authentication Alice
```

Tất cả các bước có thể xảy ra trên **hai thread vật lý khác nhau**. Repository/session xử lý persistence; không cần bật `MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` để “truyền” principal giữa requests.

### 2.2 Xác thực thành công không đồng nghĩa phiên đã lưu

Trong custom endpoint, hai dòng:

```java
Authentication verified = manager.authenticate(loginToken);
SecurityContextHolder.getContext().setAuthentication(verified);
```

chưa đủ để đảm bảo request kế tiếp authenticated. Còn phải xét `SecurityContextRepository`, session creation policy, cookie path/domain/SameSite/Secure, thời điểm response commit và cơ chế token ở client.

Spring Security chính thức khuyến nghị tạo **context mới** thay vì sửa context đã lấy từ holder để hạn chế race khi context được chia sẻ qua session/thread:

```java
SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);
repository.saveContext(context, request, response);
```

Mẫu này **chỉ dùng sau khi `verified` thực sự được provider tin cậy xác minh**. Không tạo token với `authenticated=true` từ username/role do client tự khai.

## 3. Spring Security 5 so với Spring Security 6: tại sao explicit save quan trọng?

### 3.1 Lịch sử của cơ chế tự lưu

Trong các cấu hình Spring Security 5 dùng `SecurityContextPersistenceFilter`, filter có thể nạp context đầu request và cố lưu lại context cuối request. Nó còn dùng response wrappers để ghi trước commit nếu response sớm kết thúc. Cách này giúp một số custom code chỉ `setContext` mà vẫn được lưu trong session.

Tuy nhiên, cơ chế tự suy đoán “context đã thay đổi hay chưa, có cần save hay không” gây write thừa và tình huống timing khó đoán. Spring Security 6 chuyển mặc định sang `SecurityContextHolderFilter` và yêu cầu **lưu rõ** khi custom authentication muốn persistence qua requests.

| Khía cạnh | Cơ chế cũ thường gặp | Mặc định Spring Security 6 |
| --- | --- | --- |
| Filter chính | `SecurityContextPersistenceFilter` | `SecurityContextHolderFilter` |
| Vai trò với repository | Nạp và tự xử lý lưu khi phù hợp | Chủ yếu nạp/defer nạp context |
| Custom code gọi `setContext` | Có thể được tự save tùy cấu hình | **Phải gọi `saveContext`** nếu muốn persist |
| Thời điểm ghi | Cuối request hoặc trước response commit thông qua wrapper | Do authentication mechanism quyết định rõ |
| SessionAuthenticationStrategy | Có cấu hình cũ dựa vào `SessionManagementFilter` | Authentication mechanism cần tự thực hiện strategy liên quan |
| Rủi ro khi migration | Dựa vào side effect không còn tồn tại | Request sau anonymous nếu thiếu save |

Không nên đăng ký **cả `SecurityContextHolderFilter` và `SecurityContextPersistenceFilter`** vào cùng một chain để chữa lỗi. Tài liệu Spring Security 6 nhấn mạnh chỉ nên có một trong hai. Với ứng dụng mới, giữ explicit-save và viết flow đúng.

### 3.2 `requireExplicitSave(true)`

Trong Spring Security 6, `requireExplicitSave(true)` là mặc định trong cấu hình điển hình. Bạn có thể chỉ rõ để làm ý đồ dễ đọc:

```java
http.securityContext(context -> context
        .requireExplicitSave(true)
        .securityContextRepository(repository));
```

**Đây chỉ là một đoạn cấu hình.** Nó không lưu authentication thay bạn; vẫn phải gọi `repository.saveContext(...)` trong custom login. Với code port từ Spring Security 5, hãy search tất cả chỗ tự gọi `SecurityContextHolder.setContext` mà trước đây dựa vào tự lưu, rồi cập nhật đúng cơ chế. Không cần chuyển toàn bộ ứng dụng về `requireExplicitSave(false)` như giải pháp mặc định.

### 3.3 Built-in login và custom login khác nhau ở đâu?

Filter đăng nhập có sẵn (ví dụ form login của Spring Security) đã có cơ chế quản lý authentication, session strategy, success/failure handler và lưu context theo hợp đồng framework. Nếu bạn **thay thế** nó bằng REST controller hoặc custom servlet filter, **bạn trở thành người chịu trách nhiệm** nối đúng những bước tương đương: authenticate, security context, session fixation/CSRF, save, response.

Đừng vô tình giữ một built-in login handler khác cùng URL hay hai filter có matcher chồng nhau. Nhiều `SecurityFilterChain` có thể dùng repository/manager khác; phải kiểm request thực sự đi qua chain nào.

## 4. Response commit: thời điểm quyết định lưu session

### 4.1 Commit nghĩa là gì?

Một `HttpServletResponse` bị commit khi container đã gửi status/headers tới client (hoặc bắt đầu gửi response theo quy tắc buffer của servlet container). Sau đó, ứng dụng không thể tin rằng mình vẫn sửa được headers, ví dụ thêm `Set-Cookie: JSESSIONID=...`.

Những thao tác có thể làm response commit hoặc đẩy response tới commit:

- `response.sendRedirect("/home")` thường gửi 302 + `Location` và commit.
- `response.sendError(401)` hoặc handler trả lỗi và flush.
- `response.flushBuffer()`.
- `response.getWriter().flush()` / output stream flush; phụ thuộc buffering, status và container.
- Streaming large body, `StreamingResponseBody`, file download hoặc Server-Sent Events khi byte đầu đã được gửi.
- Container tự flush khi response body vượt buffer; controller trả `ResponseEntity` rồi serialization hoàn tất cũng có thể commit.

**Không được viết logic dựa vào giả định “sau khi return controller tôi vẫn còn thời gian để lưu”.** Một khi bạn đã chuyển sang response writing, cơ hội tạo/gửi cookie phiên có thể đã mất.

### 4.2 Thứ tự sai và đúng

**Sai: response trước, save sau.**

```java
// SAI: minh họa lỗi thứ tự, không phải controller hoàn chỉnh.
Authentication verified = manager.authenticate(loginRequest);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

response.sendRedirect("/app"); // Response có thể đã commit!
repository.saveContext(context, request, response); // Quá muộn.
```

Dù `saveContext` không ném exception trong mọi container, HTTP client có thể không nhận session ID mới; login “thành công” trong request A nhưng request B vẫn 401. Không suy ra thành công chỉ từ log “saveContext invoked”.

**Đúng: save trước khi gửi redirect/body.**

```java
Authentication verified = manager.authenticate(loginRequest);
sessionAuthenticationStrategy.onAuthentication(verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

repository.saveContext(context, request, response); // Trước commit.
response.sendRedirect("/app");                      // Sau save.
```

Mã này vẫn là **mẫu ghép vào flow đã có**: các biến phải được cung cấp bởi bean/filter/controller thực tế, credential phải được xác minh, session strategy phải cấu hình đúng và response chưa commit.

### 4.3 Vì sao “đã ghi session trong DB rồi” vẫn chưa đủ?

Một repository dùng `HttpSession` có thể cần tạo session nếu request chưa có. Khi tạo session, server cần gửi **session ID** cho browser qua cookie (hoặc cơ chế quản lý session được container hỗ trợ). Nếu response đã commit, header cookie mới có thể không đến được browser. Một số hệ thống có sẵn session/cookie cũ nên bug chỉ lộ ra ở **lần đăng nhập đầu** hoặc tab ẩn danh. Vì thế cần test cả request **không có session ban đầu** và request **đã có session trước login**.

Còn có race: nếu response A được commit sớm và client gửi request B trước khi context A được lưu, B có thể tải context cũ/không có context. Save sớm trước khi gửi response giúp giữ thứ tự rõ.

### 4.4 `isCommitted()` chỉ là công cụ chẩn đoán

`response.isCommitted()` có thể cho biết response đã commit tại một thời điểm, nhưng **không được dùng để trì hoãn save đến sát lúc committed**. Thiết kế đúng là save **trước** các bước có khả năng commit, không dựa vào polling. Khi đã committed, không cố “gửi lại cookie” bằng cách ghi header trễ.

### 4.5 Servlet async và streaming

Với response async/streaming, body có thể được ghi trên thread khác hoặc sau khi controller return. Nếu login xảy ra trên request thread, **save trước khi bắt đầu async stream/redirect**. Không lưu `SecurityContext` lần đầu trong callback sau khi dữ liệu đã được ghi. Phân biệt:

- **Context propagation** sang async thread: dùng integration/wrapper phù hợp.
- **Context persistence** qua requests: dùng `SecurityContextRepository.saveContext`.
- **Response commitment**: giới hạn lúc headers/cookie có thể gửi.

Một chương trình có thể propagation đúng nhưng vẫn không persist vì bỏ save, hoặc persist đúng nhưng task async không thấy ThreadLocal vì không propagate.

## 5. Chọn SecurityContextRepository đúng cho mục tiêu

Spring Security có nhiều implementation:

| Repository | Dữ liệu lưu ở đâu? | Phù hợp | Giới hạn |
| --- | --- | --- | --- |
| `HttpSessionSecurityContextRepository` | `HttpSession`, thường key `SPRING_SECURITY_CONTEXT`. | Custom login stateful, muốn request B dùng cookie session. | Phụ thuộc session/cookie, policy tạo session, session fixation, cluster. |
| `RequestAttributeSecurityContextRepository` | Attribute của **cùng một request**. | Giữ context qua một số dispatch (ví dụ error) trong cùng request. | **Không** tự giữ login cho HTTP request mới. |
| `DelegatingSecurityContextRepository` | Ủy nhiệm nhiều repository, thường request attribute + HttpSession. | Cấu hình phổ biến của Spring Security 6 Servlet. | Phải biết các delegate nào đang được sử dụng để save/load. |
| `NullSecurityContextRepository` | Không persist. | Stateless authentication (JWT/Basic mỗi request) khi không cần session. | Gọi `saveContext` không khiến cookie session xuất hiện. |
| Custom repository | Redis/DB hoặc hạ tầng bảo mật khác theo hợp đồng. | Quy mô cluster/policy đặc thù. | Phải xử lý serialization, TTL, concurrency, consistency, cleanup và error handling. |

### 5.1 Cấu hình repo cùng instance cho filter chain và login controller

Nếu custom login gọi `repoA.saveContext` nhưng `SecurityContextHolderFilter` lại đọc từ `repoB` khác hoặc có cấu hình `NullSecurityContextRepository`, bạn có thể lưu thành công ở nơi A nhưng request B vẫn anonymous. Cách an toàn là khai báo một bean và **dùng cùng bean đó**:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        SecurityContextRepository repository) throws Exception {
    return http
        .securityContext(context -> context
            .requireExplicitSave(true)
            .securityContextRepository(repository))
        // ... authorization, CSRF, session policy ...
        .build();
}
```

Controller nhận đúng `SecurityContextRepository repository` qua constructor injection. Đây là cấu hình rút gọn, **chưa phải ứng dụng độc lập**; ví dụ đầy đủ ở mục 8.

### 5.2 Mặc định DelegatingSecurityContextRepository

Trong cấu hình Spring Security 6 thông dụng, repository mặc định cho Servlet là `DelegatingSecurityContextRepository`, kết hợp `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository`. Ý tưởng: có context cho một số servlet dispatch trong **cùng request**, đồng thời cho phép lưu qua **nhiều requests** nhờ session khi thích hợp.

Ví dụ tạo bean tường minh:

```java
@Bean
SecurityContextRepository securityContextRepository() {
    return new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository());
}
```

Nếu thay bằng **chỉ** `HttpSessionSecurityContextRepository` trong demo, login qua session vẫn hoạt động; nhưng mất một số lợi ích request-attribute cho error dispatch. Đây là lựa chọn dạy học có chủ ý, không phải lời khuyên thay toàn bộ default production.

### 5.3 SessionCreationPolicy có tác động gì?

- `IF_REQUIRED`: có thể tạo session khi cần, phù hợp custom stateful login.
- `ALWAYS`: tạo session sớm cho mỗi request theo cấu hình, thường không cần thiết.
- `NEVER`: Spring Security không chủ động tạo nhưng vẫn có thể dùng session đã tồn tại; nếu bạn mong lần login đầu phải có session mới, cần kiểm policy và repository cụ thể.
- **`STATELESS`:** Spring Security không tạo hoặc dùng session để lưu security context, thường dùng `NullSecurityContextRepository`. **Không mong gọi `saveContext` trên Null repo tạo login phiên.**

Nên quyết định API là **stateful cookie** hay **stateless token**, không trộn cả hai vô tình. Browser dùng session cookie cần CSRF defense; bearer token trong `Authorization` có lifecycle/chính sách khác.

### 5.4 Repository có thể từ chối lưu dù đã gọi save

`HttpSessionSecurityContextRepository` có logic không lưu context rỗng/anonymous, có lựa chọn không tạo session, và sẽ phụ thuộc khả năng tạo session/response chưa commit. Nếu code tạo `Authentication` thuộc anonymous/unauthenticated hoặc repo được cấu hình `allowSessionCreation=false`, gọi save không chắc tạo phiên mới. **Xem cả kết quả ở request sau**, không chỉ đo số lần method được gọi.

## 6. Thuật toán custom login an toàn theo thứ tự

Một custom login stateful nên có sequence tối thiểu:

1. **Request và CSRF:** nếu dùng cookie session cho browser, bảo đảm request login đi qua chính sách CSRF; validate kiểu/độ dài input; không in password.
2. **Tạo token chưa xác thực:** dùng `UsernamePasswordAuthenticationToken.unauthenticated(username, rawPassword)`; không tự gán authorities/`authenticated=true` từ client.
3. **Xác minh:** gọi `AuthenticationManager.authenticate(...)`. Chỉ tiếp tục nếu trả kết quả authenticated hợp lệ. Exception → phản hồi từ chối chung; không lưu fake context.
4. **Session authentication strategy:** nếu custom login, thực thi các chính sách liên quan (session fixation, CSRF token rotation/clear, concurrent sessions nếu được cấu hình).
5. **Context mới:** `SecurityContextHolderStrategy.createEmptyContext()`, đặt `Authentication` đã xác minh.
6. **Gắn vào request hiện tại:** `strategy.setContext(context)`.
7. **Lưu:** `repository.saveContext(context, request, response)` vào repo đúng, khi response **chưa commit**.
8. **Phát response:** trả 200/204/302 cùng cookie/session ID cần thiết; không trả hash/credentials/`UserDetails` nguyên gốc.
9. **Request kế tiếp:** gửi cookie tương ứng, filter nạp context từ repository; authorization dùng Authentication đã khôi phục. Nếu không muốn session, phát/verify bearer token theo flow khác.
10. **Logout/thu hồi:** vô hiệu session và xóa context tại repository theo chính sách; clear ThreadLocal một mình không phải logout.

**Không đảo bước 7 và 8.** Cũng không gọi `saveContext` **trước khi** đã xác thực credential. Nếu lưu context chưa xác minh, có thể mở lỗ hổng truy cập tùy code authorization.

### 6.1 Những sự kiện custom flow phải tự giải quyết

Việc custom controller chỉ thực hiện `authenticate + set + save` có thể duy trì session nhưng **không tự tái tạo toàn bộ hành vi** của `UsernamePasswordAuthenticationFilter`:

- Session fixation protection: đổi session ID sau login nếu có pre-auth session, dùng `SessionAuthenticationStrategy` phù hợp.
- CSRF token rotation/clear khi identity thay đổi, nếu app dùng cookie+CSRF.
- Concurrent session control/`SessionRegistry` nếu có giới hạn số phiên.
- Authentication success/failure events và audit/metrics theo policy.
- Login failure rate limit, account lockout, credential stuffing protection, MFA/step-up nếu cần.
- Remember-me, saved-request redirect, request cache và logout semantics.
- Error handling khi session store/replica bị lỗi: không trả “login successful” nếu chưa lưu phiên theo hợp đồng.
- Session cookie attributes: `Secure`, `HttpOnly`, `SameSite`, path/domain và HTTPS/TLS.

Trong ví dụ chạy được, chúng ta sẽ thực hiện **session fixation protection + CSRF token invalidation** bằng `CompositeSessionAuthenticationStrategy`, nhưng production còn phải đánh giá các chính sách trên theo kiến trúc.

## 7. Java 17 thuần: mô hình hóa thứ tự save/commit

Đây là ví dụ **chạy bằng JDK 17 không cần Spring** để hiểu thứ tự thao tác, không phải mô phỏng chính xác mọi servlet container. `FakeResponse` chỉ minh họa rằng nếu response đã commit thì không còn bảo đảm có thể thêm cookie.

File `SaveBeforeCommitDemo.java`:

```java
public final class SaveBeforeCommitDemo {

    static final class FakeResponse {
        boolean committed;
        boolean sessionCookieSent;

        void saveSession() {
            if (committed) {
                throw new IllegalStateException("response already committed");
            }
            sessionCookieSent = true;
        }

        void redirect() {
            committed = true;
        }
    }

    public static void main(String[] args) {
        FakeResponse correct = new FakeResponse();
        correct.saveSession();
        correct.redirect();

        System.out.println("correct-cookie=" + correct.sessionCookieSent);
        System.out.println("correct-committed=" + correct.committed);

        FakeResponse wrong = new FakeResponse();
        wrong.redirect();
        try {
            wrong.saveSession();
            System.out.println("wrong-save-rejected=false");
        } catch (IllegalStateException expected) {
            System.out.println("wrong-save-rejected=true");
        }
        System.out.println("wrong-cookie=" + wrong.sessionCookieSent);
    }
}
```

Biên dịch và chạy:

```bash
javac SaveBeforeCommitDemo.java
java SaveBeforeCommitDemo
```

Stdout chính xác:

```text
correct-cookie=true
correct-committed=true
wrong-save-rejected=true
wrong-cookie=false
```

**Giới hạn minh họa:** Class `FakeResponse` chủ ý ném exception sau commit để thấy failure. `HttpSessionSecurityContextRepository` và servlet container **không bắt buộc ném đúng exception này**; có thể trả về nhưng client không nhận `Set-Cookie`. Trong Spring thật phải thử bằng integration test với HTTP client mới và session/cookie thật.

## 8. Ví dụ hoàn chỉnh Spring Boot 3.x: custom REST login có persist session

Dùng **Java 17+, Spring Boot 3.3.13, Spring Security 6.x**, lưu user demo trong memory và lưu security context qua `HttpSession`. Gồm:

- `POST /api/login`: custom controller thực hiện xác thực thực sự qua `AuthenticationManager`; gọi session strategy, `setContext`, `saveContext` **trước** khi trả body.
- `GET /api/me`: yêu cầu authenticated, đọc principal và authorities của request khác.
- `GET /api/admin`: cần `ROLE_ADMIN`.
- `POST /api/logout`: dùng Spring Security LogoutFilter thay vì chỉ `clearContext`.
- CSRF **không tắt**; test dùng `spring-security-test` để cung cấp token phù hợp.
- Hai user local demo: `alice` có `ROLE_USER`, `bob` có `ROLE_ADMIN` với mật khẩu khác nhau.

Tài khoản/mật khẩu hardcode chỉ để học trên localhost, không phải cấu hình production. Phiên bản Boot được ghim cho tính tái lập bài học, **không phải khuyến nghị dùng một nhánh đã hết vòng hỗ trợ cho production mới**.

### 8.1 Cấu trúc và Gradle

```text
custom-context-save/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/CustomContextSaveApplication.java
    └── test/java/demo/CustomContextSaveTest.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'custom-context-save'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không cần cơ sở dữ liệu cho demo này; `InMemoryUserDetailsManager` lưu verifier chỉ trong JVM, còn `HttpSessionSecurityContextRepository` lưu `SecurityContext` trong phiên. Với production nhiều node, chuyển session store theo kiến trúc phù hợp, ví dụ Spring Session Redis, và kiểm tính nhất quán.

### 8.2 Ứng dụng và cấu hình Spring Security

File `src/main/java/demo/CustomContextSaveApplication.java`:

```java
package demo;

import java.util.List;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.context.SecurityContextHolderStrategy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CustomContextSaveApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomContextSaveApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build(),
                User.withUsername("bob")
                        .password(encoder.encode("different-demo-password"))
                        .roles("ADMIN")
                        .build());
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
        // Cùng bean được dùng bởi SecurityFilterChain và controller.
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository csrfRepository) {
        return new CompositeSessionAuthenticationStrategy(List.of(
                new ChangeSessionIdAuthenticationStrategy(),
                new CsrfAuthenticationStrategy(csrfRepository)));
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            SecurityContextRepository repository,
            CsrfTokenRepository csrfRepository) throws Exception {

        return http
                .securityContext(context -> context
                        .requireExplicitSave(true)
                        .securityContextRepository(repository))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(
                                SessionCreationPolicy.IF_REQUIRED))
                .csrf(csrf -> csrf.csrfTokenRepository(csrfRepository))
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.POST, "/api/login")
                            .permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/me")
                            .authenticated()
                        .requestMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .anyRequest().denyAll())
                .exceptionHandling(exceptions -> exceptions
                        .authenticationEntryPoint((request, response, e) ->
                                response.sendError(
                                        HttpServletResponse.SC_UNAUTHORIZED)))
                .formLogin(AbstractHttpConfigurer::disable)
                .httpBasic(AbstractHttpConfigurer::disable)
                .logout(logout -> logout
                        .logoutUrl("/api/logout")
                        .permitAll()
                        .logoutSuccessHandler((request, response, auth) ->
                                response.setStatus(
                                        HttpServletResponse.SC_NO_CONTENT)))
                .build();
    }
}

record LoginRequest(String username, String password) {
}

record LoginResponse(String status, String username) {
}

@RestController
class CustomLoginController {

    private final AuthenticationManager authenticationManager;
    private final SecurityContextRepository repository;
    private final SessionAuthenticationStrategy sessionStrategy;
    private final SecurityContextHolderStrategy holder;

    CustomLoginController(
            AuthenticationManager authenticationManager,
            SecurityContextRepository repository,
            SessionAuthenticationStrategy sessionStrategy) {
        this.authenticationManager = authenticationManager;
        this.repository = repository;
        this.sessionStrategy = sessionStrategy;
        this.holder = SecurityContextHolder.getContextHolderStrategy();
    }

    @PostMapping("/api/login")
    ResponseEntity<LoginResponse> login(
            @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {

        if (input == null
                || input.username() == null
                || input.username().isBlank()
                || input.password() == null
                || input.password().length() > 256) {
            return ResponseEntity.badRequest().body(
                    new LoginResponse("invalid_request", ""));
        }

        try {
            // 1. Input chưa được xác minh; tuyệt đối không tự cấp role.
            Authentication requested =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            input.username(), input.password());

            // 2. Manager/Provider kiểm username, password hash và status.
            Authentication verified =
                    authenticationManager.authenticate(requested);

            // 3. Chống session fixation và xóa CSRF token cũ
            //    theo cấu hình session authentication strategy.
            sessionStrategy.onAuthentication(verified, request, response);

            // 4. Tạo context mới sau khi đã xác thực.
            SecurityContext context = holder.createEmptyContext();
            context.setAuthentication(verified);
            holder.setContext(context);

            // 5. LƯU TRƯỚC KHI controller trả body/commit response.
            repository.saveContext(context, request, response);

            return ResponseEntity.ok(
                    new LoginResponse("ok", verified.getName()));
        } catch (AuthenticationException failure) {
            // Thông báo chung; không rò thông tin user tồn tại hay không.
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED).body(
                    new LoginResponse("rejected", ""));
        }
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
                "username", authentication.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(granted -> granted.getAuthority())
                        .sorted()
                        .toList());
    }

    @GetMapping("/api/admin")
    String adminOnly() {
        return "admin";
    }
}
```

**Tính runnable:** Một file Java chứa đúng một public class `CustomContextSaveApplication`; các record/controller còn lại package-private ở cùng `package demo`. Gradle tải Spring Boot Web/Security và spring-security-test; Java 17 hỗ trợ record và `Stream.toList()`. Demo không cần JPA, JDBC hoặc external database.

### 8.3 Diễn giải các quyết định trong code

**A. Vì sao manager được khai báo rõ?** Để custom controller thật sự gọi `ProviderManager` chứa `DaoAuthenticationProvider`, lấy `UserDetails` từ `InMemoryUserDetailsManager` và dùng `PasswordEncoder` tương ứng. Không gọi raw password vào `UserDetailsService` rồi tự so text. Nếu thêm provider khác, hãy kiểm `supports` và thứ tự/fallback.

**B. Vì sao token `unauthenticated`?** Username/password mới đến từ client chưa là bằng chứng. Chỉ provider thành công mới trả `Authentication` được tin cậy. Không tự gọi factory `authenticated(...)` với role do request truyền.

**C. Vì sao strategy chạy sau authenticate nhưng trước save?** Khi login thành công từ một pre-login session, `ChangeSessionIdAuthenticationStrategy` giúp thay session ID để giảm session fixation. `CsrfAuthenticationStrategy` xóa/đặt lại token cũ theo cơ chế repository khi identity đổi. Nếu lưu rồi mới đổi session/commit response, lifecycle khó kiểm soát và có thể tạo ra cookie/context không nhất quán.

**D. Vì sao dùng cùng một repository bean?** `SecurityContextHolderFilter` của chain tải bằng instance đó; controller cũng lưu vào instance đó. Đây là cách hạn chế lỗi “repo A save, repo B load” khi có nhiều chain hoặc custom adapter.

**E. Vì sao `saveContext` nằm trước `ResponseEntity.ok`?** Spring MVC xử lý body khi controller trả về; lưu trong controller trước `return` là một điểm trước commit rõ ràng. Nếu bạn gọi `response.getWriter().println(...)` rồi flush và cuối cùng mới save, timing có thể sai.

**F. Vì sao không tắt CSRF để demo chạy dễ?** Custom REST login đang dùng session cookie ở browser, nên CSRF có thể quan trọng cả ở endpoint login và các endpoint thay đổi trạng thái. `spring-security-test` có helper gửi CSRF token trong kiểm thử. Nếu app thuần bearer không dùng cookie, đánh giá chính sách khác thay vì tắt toàn bộ CSRF một cách máy móc.

**G. Vì sao không dùng `HttpSession` trực tiếp để tự đặt `SPRING_SECURITY_CONTEXT`?** Repository là abstraction quản lý lưu/đọc; tự thao tác attribute string dễ bỏ qua logic không lưu anonymous, session creation policy và những repository khác. Với Spring Security 6, API công khai để lưu là `saveContext`.

**H. Vì sao không set strategy JVM-wide?** `SecurityContextHolder.getContextHolderStrategy()` lấy chiến lược mà framework đang dùng, thường `MODE_THREADLOCAL`. Không đổi `MODE_GLOBAL` để giữ login qua requests; persistence thuộc repository.

### 8.4 Kiểm thử tự động qua HTTP request thật của MockMvc

File `src/test/java/demo/CustomContextSaveTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import org.springframework.security.web.context
        .HttpSessionSecurityContextRepository;
import org.springframework.security.core.context.SecurityContext;

@SpringBootTest
@AutoConfigureMockMvc
class CustomContextSaveTest {

    @Autowired
    MockMvc mvc;

    private MvcResult login(
            String username, String password) throws Exception {
        return mvc.perform(post("/api/login")
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"username":"%s","password":"%s"}
                        """.formatted(username, password)))
                .andReturn();
    }

    @Test
    void correctLoginIsSavedAndAvailableInNextRequest()
            throws Exception {
        MvcResult result = login("alice", "local-demo-password");
        assertEquals(200, result.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) result.getRequest().getSession(false);
        assertNotNull(session);

        Object saved = session.getAttribute(
                HttpSessionSecurityContextRepository
                        .SPRING_SECURITY_CONTEXT_KEY);
        assertNotNull(saved);
        SecurityContext context = (SecurityContext) saved;
        assertEquals("alice", context.getAuthentication().getName());

        // Một MockMvc request MỚI dùng cùng server session.
        mvc.perform(get("/api/me").session(session))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"));

        mvc.perform(get("/api/admin").session(session))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordDoesNotSaveAuthenticatedContext()
            throws Exception {
        MvcResult failed = login("alice", "wrong-password");
        assertEquals(401, failed.getResponse().getStatus());

        MockHttpSession session =
                (MockHttpSession) failed.getRequest().getSession(false);
        if (session != null) {
            assertNull(session.getAttribute(
                    HttpSessionSecurityContextRepository
                            .SPRING_SECURITY_CONTEXT_KEY));
        }

        mvc.perform(get("/api/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void loginRequiresCsrfTokenForCookieBasedFlow()
            throws Exception {
        mvc.perform(post("/api/login")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"username":"alice",
                                 "password":"local-demo-password"}
                                """))
                .andExpect(status().isForbidden());
    }

    @Test
    void existingPreLoginSessionChangesIdAfterAuthentication()
            throws Exception {
        MockHttpSession preLoginSession = new MockHttpSession();
        String oldId = preLoginSession.getId();

        MvcResult response = mvc.perform(post("/api/login")
                .session(preLoginSession)
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"username":"bob",
                         "password":"different-demo-password"}
                        """))
                .andExpect(status().isOk())
                .andReturn();

        MockHttpSession newSession =
                (MockHttpSession) response.getRequest().getSession(false);
        assertNotNull(newSession);
        assertNotEquals(oldId, newSession.getId());

        mvc.perform(get("/api/admin").session(newSession))
                .andExpect(status().isOk());
    }
}
```

**Về import dài:** Java cho phép xuống dòng giữa các token như cách diễn đạt trên, nhưng để giảm rủi ro formatter/IDE, có thể viết các `import static` và `import` của test thành **một dòng mỗi import** theo convention. Không đặt dấu chấm ở cuối một dòng rồi thêm whitespace/comment làm đổi token; ở đây chỉ có xuống dòng trước dấu `.` và compiler vẫn coi là token liên tiếp.

Để tránh mọi mơ hồ khi tự gõ, **mẫu import ngắn chuẩn** cho các dòng được chia là:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.core.context.SecurityContext;
```

Những import đã xuất hiện ở test là cùng lớp/member; **không được giữ hai bản trùng khi ghép file**. Phần code test đã dùng tên đúng; IDE/formatter chỉ cần chuẩn hóa các dòng import nếu muốn.

### 8.5 Chạy

Dùng Gradle wrapper có sẵn:

```bash
./gradlew test
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat bootRun
```

Nếu chưa có wrapper nhưng đã cài Gradle tương thích, dùng `gradle test` / `gradle bootRun`. Không chạy `javac CustomContextSaveApplication.java` đơn lẻ vì project cần Spring Boot/Web/Security dependencies.

**Kỳ vọng:** `./gradlew test` chạy bốn test MockMvc thành công nếu project được tạo đúng. Đây là **kết quả kỳ vọng theo code**, không phải stdout đã được build trong môi trường người đọc. Log của Spring/Gradle thay đổi theo máy và phiên bản.

| Case | HTTP/mong đợi | Bằng chứng |
| --- | --- | --- |
| Login Alice đúng, CSRF hợp lệ | 200, body `status=ok` | AuthenticationManager xác minh; controller lưu context. |
| Request mới `GET /api/me` với session Alice | 200, username `alice` | Repository đã persist, filter đã nạp. |
| Alice `GET /api/admin` | 403 | Có authentication nhưng thiếu ROLE_ADMIN. |
| Login sai password | 401 | Không tạo authentication success context. |
| POST login thiếu CSRF | 403 | CSRF filter chặn trước custom controller. |
| Login Bob với pre-login session | 200, session ID đổi | Session fixation protection được gọi trong custom flow. |
| Bob `GET /api/admin` với session mới | 200 | Context lưu đúng và role ADMIN hợp lệ. |

Với browser/curl thủ công, cần lấy CSRF token thực tế kèm session cookie trước khi POST JSON. Demo không cung cấp endpoint `/api/csrf` riêng; vì vậy **hãy dùng MockMvc tests** thay vì tắt CSRF hoặc giả lập token bằng một chuỗi bất kỳ. Trong production, SPA có thể dùng CSRF token endpoint/cookie theo thiết kế riêng và phải giữ origin/session boundaries.

### 8.6 Không nên tuyên bố test chứng minh tất cả

MockMvc chứng minh Spring Security filter/controller và request/session mock tương tác đúng trong cấu hình trên. Nó **chưa phải** test với browser cookie thật, HTTPS reverse proxy, Tomcat response buffering hay Spring Session Redis cluster. Với production, bổ sung integration/E2E test qua HTTP client thực, cookie jar và nhiều node; đặc biệt kiểm **Set-Cookie trước response commit** và request B được xác thực. Không giả định chỉ vì MockMvc pass mà cấu hình load balancer/session store luôn đúng.

## 9. Một ví dụ đối chiếu lỗi thiếu save

Giả sử trong custom login chỉ có:

```java
Authentication verified = authenticationManager.authenticate(requested);
SecurityContext context = holder.createEmptyContext();
context.setAuthentication(verified);
holder.setContext(context);

return ResponseEntity.ok(new LoginResponse("ok", verified.getName()));
```

Request login trả 200 và code ở **cùng request** có thể đọc Alice từ `SecurityContextHolder`. Nhưng nếu `SecurityContextHolderFilter` dùng explicit save, `HttpSessionSecurityContextRepository` **chưa hề được yêu cầu lưu**. Sau khi filter cleanup, request B nạp lại từ repository mà không thấy context; kết quả `/api/me` có thể là 401.

**Cách sửa đúng:** thêm `repository.saveContext(context, request, response)` trước `return`, bảo đảm repo của chain và login trùng nhau. Không thay bằng:

```java
request.getSession().setAttribute("user", verified.getName());
```

Dòng đó chỉ lưu một attribute tùy ý, không phải `SecurityContext` mà Spring Security nạp. Tự ghi session attribute bằng key `SPRING_SECURITY_CONTEXT` cũng không được khuyến nghị: nó bỏ qua abstraction, điều kiện save và các repository khác.

### 9.1 Vì sao controller đầu tiên có thể được authenticated mà request sau 401?

Vì context hiện tại nằm trong holder của request A. Authorization downstream trong cùng request A dùng nó được. Sau khi request kết thúc, filter dọn ThreadLocal; request B lấy context từ repo. Nếu repo chưa có dữ liệu thì B không biết Alice. Cùng một biểu hiện có thể xảy ra nếu cookie không được client gửi/nhận, hoặc session hết hạn; phải kiểm cả phía server và HTTP.

### 9.2 Vì sao đặt save trong `finally` là sai?

`finally` thường chạy sau khi body/redirect đã được viết hoặc response committed, tùy cách tổ chức code. Lúc đó không còn bảo đảm session cookie. **Đừng coi persistence là cleanup.** Save ở đường **authentication success**, sau session strategy, **trước** response writing; cleanup ThreadLocal ở request boundary thuộc filter.

### 9.3 Login thành công nhưng `saveContext` thất bại

Nếu session store bị outage/quota hoặc repo ném lỗi, app không nên trả body “ok” và phát một trạng thái nửa vời theo chính sách stateful login. Cần exception handling rõ, metric/audit, và trả lỗi an toàn (ví dụ 503), tránh công bố đã đăng nhập khi client không thể dùng phiên. Đừng bắt mọi lỗi rồi im lặng tiếp tục.

## 10. Logout, xóa context và response timing

Lưu `Authentication` khi đăng nhập chỉ là một nửa vòng đời. Logout phải xóa context ở nơi đã persist, vô hiệu session và xử lý cookie/token theo policy.

Dùng Spring Security logout support thường tốt hơn tự viết:

```java
http.logout(logout -> logout
        .logoutUrl("/api/logout")
        .permitAll());
```

Với cookie-session API, giữ CSRF khi POST logout. Logout filter/handlers chuẩn xử lý `SecurityContext` và session theo cấu hình. Nếu viết custom logout controller, cần:

- Kiểm phạm vi user/session và CSRF.
- Clear `SecurityContextHolder`/strategy của current execution.
- Xóa context khỏi `SecurityContextRepository` theo đúng hợp đồng (không chỉ clear ThreadLocal).
- Invalidate `HttpSession` hoặc xóa session state đúng, xử lý cookie expiration theo container.
- Nếu có remember-me/refresh token/JWT, revoke theo policy; logout session **không tự revoke mọi bearer token**.
- Trả response sau khi state đã được thu hồi; không gửi body “logout success” trước rồi mới cleanup.

Đừng gọi `SecurityContextHolder.clearContext()` một mình và tưởng đã “logout all devices”. Session ID/cookie cũ có thể còn ánh xạ tới context đã lưu.

## 11. Session fixation và CSRF ở custom login

### 11.1 Vì sao session ID phải đổi khi login?

Kẻ tấn công có thể khiến nạn nhân dùng một pre-login session ID mà attacker biết. Nếu sau login vẫn là session ID đó, attacker có thể tìm cách dùng lại session đã được nâng quyền (*session fixation*). Spring Security built-in authentication có session fixation protection, nhưng **custom controller không mặc định tự gọi toàn bộ strategy**. Với Servlet 3.1+, `ChangeSessionIdAuthenticationStrategy` có thể yêu cầu container đổi ID của session hiện tại sau authentication.

Trong ví dụ, strategy được gọi **sau** `AuthenticationManager.authenticate` thành công và **trước** `saveContext`/response. Không đổi session ID mỗi khi sai password, không gọi `request.changeSessionId()` tùy ý trên một session không tồn tại. Với concurrent sessions hoặc session registry, thay bằng `CompositeSessionAuthenticationStrategy` phù hợp policy và kiểm toàn bộ lifecycle.

### 11.2 CSRF trên endpoint login

Dù login không phải thao tác CRUD dữ liệu kinh doanh, **login CSRF** có thể ép browser đăng nhập bằng account do attacker kiểm soát, làm lệch hành vi/ghi nhận tài khoản. Với ứng dụng cookie-based, CSRF protection cần được đánh giá cả trên login. Demo giữ filter mặc định và dùng `CsrfAuthenticationStrategy` để xóa token cũ sau đổi identity.

Khi tích hợp SPA hoặc frontend, token CSRF thường phải lấy qua một flow được thiết kế trước, kèm cookie/session; không nên tắt `csrf()` toàn app chỉ vì request POST JSON không có token. Với API chỉ dùng bearer header và không dùng cookie để xác thực, đánh giá CSRF khác nhưng vẫn phải kiểm CORS, token storage và credential forwarding.

### 11.3 SessionAuthenticationStrategy không tự được gọi chỉ vì có Bean

Spring Security 6 mặc định không dựa vào `SessionManagementFilter` để phát hiện mọi authentication mới. Custom authentication mechanism phải **tự gọi** các session strategies cần thiết hoặc dùng abstraction built-in đã hỗ trợ. Khai báo `SessionAuthenticationStrategy` bean rồi chỉ `setContext` không bảo đảm session fixation protection/concurrency đã chạy.

Nếu áp đặt `maximumSessions` hoặc đăng ký `SessionRegistry`, còn cần cấu hình additional strategies và authentication success flow; code demo chỉ minh họa fixation+CSRF, không khẳng định đã có concurrent-session control đầy đủ.

## 12. Authentication success handler trong custom filter

Khi tự viết Servlet filter thay vì controller, nguyên tắc không đổi. Mẫu thứ tự trong `successfulAuthentication`/custom success branch:

```java
// Sau khi filter đã có Authentication verified từ manager.
sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context = strategy.createEmptyContext();
context.setAuthentication(verified);
strategy.setContext(context);

securityContextRepository.saveContext(
        context, request, response);

// Chỉ lúc này mới ghi body, redirect hoặc gọi success handler
// có thể commit response.
successHandler.onAuthenticationSuccess(
        request, response, verified);
```

**Mẫu này chỉ là đoạn ghép vào một filter custom có context phù hợp.** Nếu bạn kế thừa `AbstractAuthenticationProcessingFilter`, superclass/built-in success flow có thể đã quản lý context/save; phải đọc implementation và tránh lưu/chuyển hướng hai lần. Đặc biệt, `AuthenticationSuccessHandler` có thể gọi `sendRedirect` và commit ngay, nên nó phải chạy **sau khi save** nếu flow của bạn tự kiểm soát.

Nếu custom filter kế thừa `OncePerRequestFilter` và tự thực hiện authentication, cần cân nhắc filter order, exception handling, session strategy, context repository, CSRF, request/response wrappers và không đăng ký filter **hai lần** (vừa `@Component` servlet filter, vừa `addFilterBefore`). Không dùng một static global `Authentication` giữa nhiều requests.

## 13. Nhiều SecurityFilterChain và hai lỗi cấu hình repo

### 13.1 Ví dụ hai chain

Giả sử:

```text
Chain A: /api/**    STATELESS + NullSecurityContextRepository
Chain B: /web/**    IF_REQUIRED + HttpSessionSecurityContextRepository

Custom login nằm ở /api/login nhưng muốn session cho /web/home.
```

Đây là tình huống có nguy cơ: login đang chạy qua chain A stateless, save vào repo khác hoặc không tạo cookie theo policy, trong khi request B dùng chain B. Chỉ vì controller dùng `HttpSessionSecurityContextRepository` không chứng minh security chain/cookie policy nhất quán. Hãy chọn rõ một flow (cookie session hoặc bearer token) và bố trí matcher, repository, session policy thống nhất. Nếu cần phối hợp hai chain, phải cấu hình có chủ đích và test end-to-end.

### 13.2 Lưu vào request attribute không giữ qua request mới

`RequestAttributeSecurityContextRepository.saveContext` có ích với error dispatch/forward trong một request, nhưng không làm request mới có session login. Nếu đặt nó làm repository duy nhất và trả 200, client vẫn có thể anonymous ở request B. Dùng session repo hoặc delegate có session khi cần cross-request.

### 13.3 Stateless không có nghĩa không có context trong request

JWT/bearer resource server thường đặt `Authentication` vào `SecurityContextHolder` khi verify token mỗi request, nhưng không lưu login theo cookie session. `NullSecurityContextRepository` có thể là lựa chọn đúng. Không “sửa” API stateless bằng việc ép tạo HttpSession khi product cần token-only.

### 13.4 Cookie không đến browser

Ngay cả khi server đã lưu `SPRING_SECURITY_CONTEXT` đúng, client có thể không gửi cookie do:

- Cookie `Secure` nhưng request đang HTTP không an toàn.
- `SameSite`, `Domain`, `Path` không phù hợp với frontend/API origin.
- CORS credentials mode sai; browser không gửi/nhận credential cross-origin.
- Proxy/load balancer thay host/path/scheme, set-cookie bị strip.
- Session store node A không chia sẻ cho node B, sticky sessions hoặc Spring Session chưa đúng.
- Cookie chưa được gửi vì response đã committed trước khi session tạo.

**Đọc Set-Cookie và Cookie headers ở test HTTP thực**, nhưng không log toàn bộ cookie/session ID vào log production.

## 14. Các anti-pattern cần tránh

### A. Tự tạo Authentication authenticated từ request

```java
// SAI: do client khai báo, chưa được manager/provider kiểm.
Authentication forged =
        UsernamePasswordAuthenticationToken.authenticated(
                usernameFromRequest,
                null,
                AuthorityUtils.createAuthorityList("ROLE_ADMIN"));

SecurityContextHolder.getContext().setAuthentication(forged);
```

Repository dù lưu được cũng chỉ lưu một **danh tính giả mạo**. Bước quan trọng nhất vẫn là xác minh credential/token hợp lệ trước khi tạo principal có quyền.

### B. Save sau redirect

```java
// SAI:
response.sendRedirect("/app");
repository.saveContext(context, request, response);
```

Client có thể không nhận session cookie. Luôn save **trước** redirect.

### C. Chỉ setContext rồi kết luận đã persist

```java
// SAI nếu muốn login tồn tại qua requests trên Spring Security 6:
SecurityContextHolder.setContext(context);
return ResponseEntity.ok().build();
```

Context có thể bị filter cleanup sau request. Cần repository save.

### D. Save qua repo khác với repo đang load

```text
Controller save: HttpSessionSecurityContextRepository A
Filter chain load: NullSecurityContextRepository B
Request sau: anonymous
```

Chọn repository/chain nhất quán; đừng test chỉ request login.

### E. Tắt CSRF hoặc session fixation protection để “chữa 403”

HTTP 403 ở POST login có thể do CSRF, không phải password sai. Tắt bảo vệ mà không phân tích credential/cookie model có thể mở lỗ hổng. Với custom session login, phải xử lý fixation sau authentication.

### F. Tự lưu chuỗi username thay vì SecurityContext

```java
request.getSession().setAttribute("username", authentication.getName());
```

Đây chỉ là dữ liệu tùy ý. Security filter không tự chuyển nó thành `Authentication`. Dùng repository.

### G. Lưu sau khi ghi StreamingResponseBody

Nếu response stream đã gửi byte đầu, Set-Cookie mới có thể không đi theo. Custom login không nên được gắn ở cuối stream; xác thực/save ở giai đoạn trước commit.

### H. Cho rằng HTTP 200 của login là test đủ

Không. Nếu không có request B gửi cookie và xác nhận principal, test có thể bỏ sót lỗi persistence hoàn toàn. Kiểm session repository và network cookie.

## 15. Ma trận kiểm thử theo ranh giới

| Tình huống | Thao tác | Kết quả cần chứng minh |
| --- | --- | --- |
| Custom login đúng, không có session trước | POST login có CSRF/credential đúng | 200 và session/context được lưu, client nhận cookie. |
| Request B với cookie đã cấp | GET protected | 200, principal từ repository đúng người. |
| Request B không cookie | GET protected | 401/redirect theo entry point, không nhận nhầm principal. |
| Login sai password | POST login | 401, không tạo context authenticated. |
| Login thiếu CSRF với cookie flow | POST login không token | 403; custom controller không tự bỏ qua. |
| Login user disabled/locked | Manager xác thực | Bị từ chối, không persist context. |
| Login Alice, gọi ADMIN URL | GET admin | 403 dù Alice đã authenticated. |
| Login Bob có ADMIN | GET admin | 200 đúng principal/authority. |
| Không gọi `saveContext` | Login trả success local | Request sau anonymous: phát hiện bằng integration test. |
| Save sau `sendRedirect` | Response đã commit | Cookie/session mới không được bảo đảm, fail test HTTP client mới. |
| Save trước `sendRedirect` | Response chưa commit | Client nhận session/cookie và request B authenticated. |
| Save sau `flushBuffer` | Response committed | Không thể bảo đảm Set-Cookie; không dùng pattern này. |
| Pre-login session | Login thành công | Session ID được thay theo fixation policy. |
| Custom repo chỉ RequestAttribute | Save local rồi request mới | Không được giả định cross-request persistence. |
| Null repo/stateless | Verify token mỗi request | Không tạo login session; request sau phải có token. |
| Nhiều filter chains | Login và API thuộc các chain khác | Authentication persistence/policy nhất quán theo thiết kế. |
| Session expiry | Dùng cookie cũ | Không được khôi phục session hết hạn. |
| Logout | POST logout có CSRF | Session/context cũ không còn dùng được. |
| Session store outage | POST login khi store không ghi được | Không báo thành công sai; xử lý lỗi an toàn. |
| Proxy/cookie flags | Browser HTTPS/SameSite/cross-origin | Cookie được nhận/gửi phù hợp, không rò giữa origin. |
| Async/streaming login | Bắt đầu trả body rồi mới save | Phải phát hiện sai thời điểm commit. |
| Concurrent requests | Request B chạy sát thời điểm login | Không thấy dữ liệu trước khi save; không login race. |
| Cross-user session | Alice và Bob hai session | Context không trộn qua thread pool hoặc shared mutable object. |
| Role revoked sau login | Dùng cookie cũ | Authorization/freshness theo policy, không tự cho role còn mới. |
| Form login built-in | Đăng nhập qua standard filter | Framework tự thực thi appropriate success flow; không double-save tùy tiện. |

Test tốt kiểm **cả repository state ở server** lẫn **cookie và HTTP status ở client**. Một số client tự động follow redirect khiến bạn chỉ thấy status cuối, bỏ lỡ thời điểm `Set-Cookie` được phát; khi debug, tắt auto-follow hoặc quan sát từng response.

## 16. Debug theo triệu chứng

| Triệu chứng | Gợi ý nguyên nhân | Cách điều tra |
| --- | --- | --- |
| Login POST trả 200 nhưng GET kế tiếp 401 | Thiếu `saveContext` hoặc cookie/session không lưu. | Kiểm controller đã save trước return, repo đúng, session key và cookie. |
| POST login không vào controller, trả 403 | CSRF filter chặn trước MVC. | Kiểm CSRF token, cookie/session và chính sách origin. |
| Login handler chạy nhưng response chưa có JSESSIONID | Repo null/không tạo session, response commit sớm, policy stateless hoặc cookie bị strip. | Xem `SessionCreationPolicy`, repo implementation, response.isCommitted(), headers an toàn. |
| Có session ID nhưng request sau anonymous | Session không có `SPRING_SECURITY_CONTEXT`, repo khác hoặc session store node khác. | Kiểm server session attribute, chain/repository và cluster. |
| Request đầu đúng, request thứ hai sai user | Shared static context, mutate object chung, thread pool không cleanup hoặc cookie gắn sai. | Dùng context mới, ThreadLocal default, kiểm session ID per client. |
| Redirect xong không giữ login | `sendRedirect` trước `saveContext` hoặc race response commit. | Đổi thứ tự, test 302 Set-Cookie riêng. |
| Sau upgrade Spring Security 5 → 6 bị mất login | Code dựa vào `SecurityContextPersistenceFilter` tự lưu. | Thêm explicit repository save trong custom auth. |
| Logout trả 204 nhưng cookie cũ vẫn truy cập | Chỉ clear ThreadLocal, không invalidate session/repository. | Dùng LogoutFilter/handlers, test cookie cũ ở request khác. |
| Login mới vẫn dùng session ID cũ do attacker biết | Custom login không gọi SessionAuthenticationStrategy. | Gọi fixation protection trước save, test ID đổi. |
| Role/authority khác lúc request B | Custom auth lấy sai provider/user store hoặc stale Session/Cache. | Kiểm principal sau authenticate và after reload, policy revalidation. |
| Async response trả trước khi save | Save trong future/callback sau writer flush. | Save ở request thread trước commit, propagate context riêng. |
| Multiple chains có Null repo | Filter chain khác với login/endpoint. | Ghi lại matcher/chain, repo và session policy tại request. |

### Checklist khi xử lý production incident

1. Có bằng chứng `AuthenticationManager.authenticate` thật sự trả kết quả hợp lệ không? Không log password/hash.
2. Có custom controller/filter nào gọi `setContext` mà không `saveContext`?
3. Repo/strategy đang dùng là gì; có Null/RequestAttribute-only không?
4. `saveContext` có được gọi **trước** body/redirect/flush không?
5. Response đã commit trước lúc save chưa; có Set-Cookie trong response gốc không?
6. Client có gửi Cookie ở request tiếp theo không; path/domain/SameSite/Secure/CORS hợp lệ?
7. Session store có context, TTL và key đúng không; node nào xử lý request?
8. Có `SessionAuthenticationStrategy` để thay session ID, xử lý CSRF và concurrent sessions không?
9. SecurityFilterChain nào chạy ở từng URL, có trùng matcher hoặc custom filter hai lần không?
10. Logs có đang chứa raw password, Set-Cookie, JWT hoặc full `Authentication` không? Nếu có, phải giảm/redact.

## 17. Bài tập tự kiểm tra có đáp án

**Câu 1.** Một controller gọi `AuthenticationManager.authenticate(...)` thành công, rồi `SecurityContextHolder.setContext(context)` nhưng không gọi `saveContext`. Ở request thứ hai, user có chắc còn login không?

**Đáp án:** Không. Trong cấu hình Spring Security 6 explicit save, holder chỉ giữ context execution hiện tại; request sau cần repository/session và cookie. Phải gọi `SecurityContextRepository.saveContext(context, request, response)` trước commit.

**Câu 2.** Vì sao `SecurityContextHolder.getContext().getAuthentication()` trả Alice ngay sau login không chứng minh persistence?

**Đáp án:** Vì code vẫn chạy trong thread/request hiện tại, nơi context vừa được đặt. Khi filter cleanup, thread-local hết association; request mới cần nạp lại từ repository.

**Câu 3.** Khi nào `response.sendRedirect("/app")` nên chạy?

**Đáp án:** Sau khi manager đã xác minh, session authentication strategy đã chạy, context mới được set và repository đã save. Redirect có thể commit headers, không nên save sau nó.

**Câu 4.** Nếu app dùng `NullSecurityContextRepository` trong stateful login nhưng vẫn gọi `saveContext`, có được session không?

**Đáp án:** Không. Null repository không persist. Phải chọn repo có session persistence hoặc thiết kế token-only stateless đúng mục tiêu.

**Câu 5.** `RequestAttributeSecurityContextRepository` có giúp browser giữ login ở HTTP request mới không?

**Đáp án:** Không. Nó giữ context trong phạm vi một request, có ích qua dispatch, không thay HttpSession repo hoặc token.

**Câu 6.** Vì sao thay `MODE_THREADLOCAL` bằng `MODE_GLOBAL` là sai khi muốn login tồn tại qua request?

**Đáp án:** GLOBAL chia sẻ context trên JVM cho mọi thread, dễ rò danh tính giữa user. Persistence qua requests thuộc `SecurityContextRepository`/session.

**Câu 7.** Login custom có CSRF token hợp lệ nhưng không thay session ID. Có rủi ro gì?

**Đáp án:** Session fixation. Nếu attacker kiểm soát pre-login session ID, nạn nhân login có thể nâng quyền cho session đó. Custom login cần invoke session fixation protection theo policy.

**Câu 8.** Có session attribute `"username"="alice"`, tại sao `GET /api/me` vẫn 401?

**Đáp án:** Spring Security không tự chuyển attribute tùy ý thành `SecurityContext`. Cần lưu đúng context qua `SecurityContextRepository`.

**Câu 9.** Một request login trả 200, HTTP response chứa cookie, nhưng API protected ở node khác vẫn 401. Có chắc là lỗi controller không save không?

**Đáp án:** Không. Kiểm shared session store, cookie domain/path, session ID, repository của chain bên kia, node routing và TTL. Việc có cookie chưa chứng minh context tồn tại ở nơi request B đọc.

**Câu 10.** App custom POST login trả 403 trước khi manager được gọi. Có phải password sai?

**Đáp án:** Không nhất thiết; CSRF có thể từ chối POST trước controller, hoặc authorization filter/matcher chặn. Phải kiểm status, filter order và CSRF token.

**Câu 11.** Sau khi `saveContext` thành công, có thể bỏ kiểm role/resource khi request sau không?

**Đáp án:** Không. Authentication persistence chỉ giữ danh tính/authorities đã xác thực; authorization vẫn phải kiểm từng endpoint, tenant và object, cùng chính sách freshness khi role đổi.

**Câu 12.** Vì sao một custom filter có `AuthenticationSuccessHandler` dễ gặp bug timing?

**Đáp án:** Success handler có thể redirect/commit response. Nếu filter gọi handler trước `saveContext` thì cookie/session không được bảo đảm. Với built-in filter, kiểm logic superclass để tránh tự save hai lần.

## 18. Checklist triển khai và giới hạn của bài

**Đăng nhập tùy chỉnh:**

- Input được validate/rate-limit, password đi qua TLS, không xuất/log credential.
- Manager/provider kiểm đúng credential, trạng thái account, tenant/authority nguồn tin cậy.
- Chỉ dùng `UsernamePasswordAuthenticationToken.unauthenticated` khi nhận request.
- Session fixation và CSRF được xử lý trong custom flow, không trông chờ bean tự chạy.
- `SecurityContext` mới chứa Authentication verified.
- `SecurityContextHolderStrategy.setContext` áp dụng cho request đang chạy.
- **`SecurityContextRepository.saveContext` chạy rõ ràng, dùng đúng repo của chain, trước response commit.**
- Response chỉ chứa dữ liệu tối thiểu, không serialize `UserDetails.getPassword()`.
- Client giữ/gửi session cookie đúng HTTPS/SameSite/Secure/HttpOnly theo app.
- Request kế tiếp xác nhận context được load và authorization chạy bình thường.
- Logout/revocation xóa state đúng repository/session/token lifecycle.

**Giới hạn:**

- Trong Spring Security 6, built-in login filters và custom authentication không đồng nhất về trách nhiệm; xem source/filter contract tương ứng.
- Demo dùng in-memory users và session local, không mô phỏng password rotation, database, Spring Session Redis hay JWT.
- `HttpSessionSecurityContextRepository` cố ý dùng riêng để thấy stateful persistence; production có thể giữ `DelegatingSecurityContextRepository` mặc định cho request/error dispatch.
- Spring Security 7.x có thể thay API/config; các đoạn code ở đây dành cho Spring Security 6.x/Boot 3.x, không thay tư vấn migration theo phiên bản.
- MockMvc test kiểm framework logic, chưa xác minh Set-Cookie của browser thật qua proxy/container.
- Không nên để lời nhắc “save trước response” trở thành lý do tự cấp authentication từ dữ liệu client. **Xác thực là điều kiện trước save.**

## 19. Tài liệu chính thức

- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): custom controller/filter cần `SecurityContextRepository.saveContext`; `SecurityContextHolderFilter` và `requireExplicitSave`; session policies, strategies và fixation.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): context repository, response commit race, `HttpSession`/`RequestAttribute`/`Null`/`DelegatingSecurityContextRepository`.
- [Spring Security 6.5 — Session Management Migrations](https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html): chuyển từ tự save sang explicit save trong Spring Security 6.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `Authentication`, `SecurityContextHolder` và nguyên tắc tạo context mới.
- [Spring Security 6.5 — SecurityContextRepository API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/SecurityContextRepository.html): `loadDeferredContext`, `saveContext` và `containsContext`.
- [Spring Security 6.5 — DaoAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/dao-authentication-provider.html): xác minh username/password qua UserDetailsService và PasswordEncoder.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): cookie-based requests, CSRF token lifecycle và login/logout.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc.html): hỗ trợ MockMvc security integration và CSRF request post-processors.
- [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session fixation, cookie flags, TTL, invalidation và bảo vệ session ID.

**Kết luận:** Trong custom login Spring Security Servlet, **`AuthenticationManager.authenticate(...)` xác minh**, **`SecurityContextHolder.setContext(...)` giúp request hiện tại nhìn thấy người dùng**, còn **`SecurityContextRepository.saveContext(...)` mới giúp giữ context qua requests khi chọn session persistence**. Hãy save sau khi xác thực và session strategy hoàn tất, **trước `sendRedirect`, `sendError`, flush hoặc return body dẫn tới commit**. Kiểm bằng request thứ hai mang cookie, không chỉ quan sát status 200 của request login; đồng thời giữ CSRF/session fixation, phân quyền và lifecycle logout đúng.