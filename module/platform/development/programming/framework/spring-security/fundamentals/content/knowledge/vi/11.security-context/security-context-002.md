# SecurityContextHolder trong mô hình xử lý Servlet

**SecurityContextHolder** là điểm truy cập đến **SecurityContext** của luồng xử lý hiện tại trong Spring Security. Trong một ứng dụng **Servlet** như Spring MVC chạy với Spring Security 6, ngữ cảnh này cho biết **Authentication nào đang gắn với request**: principal hiện tại, các quyền (GrantedAuthority) và những thông tin xác thực liên quan. Mặc định, Spring Security dùng cơ chế **ThreadLocal** để các lớp xử lý trên cùng thread có thể truy cập ngữ cảnh mà không cần chuyển Authentication qua mọi tham số.

Tuy nhiên, hiểu SecurityContextHolder chỉ là “biến toàn cục chứa user” sẽ dẫn đến lỗi nghiêm trọng. Context có **vòng đời theo request**, cần được **thiết lập, sử dụng, dọn sạch**, và không đồng nghĩa với nơi lưu session lâu dài. Spring Security 6 có sự khác biệt quan trọng giữa **SecurityContextHolderFilter**, **SecurityContextPersistenceFilter** và **SecurityContextRepository**; việc chuyển sang thread khác cũng không tự mang theo ThreadLocal trong mọi trường hợp.

Bài học thuộc nhóm **Ngữ cảnh bảo mật**, tập trung vào **SecurityContextHolder trong mô hình xử lý Servlet**. Nội dung gồm kiến trúc, ví dụ Java 17/Spring Boot 3.3.6 + Spring Security 6.x, các kiểm thử MockMvc/JUnit và tình huống lỗi thực tế. **Không áp dụng nguyên xi cách truy cập ThreadLocal này cho server WebFlux**: mô hình reactive chủ yếu dùng Reactor Context và ReactiveSecurityContextHolder.

## 1. Ba lớp cần phân biệt trước tiên

| Thành phần | Là gì? | Trách nhiệm |
| --- | --- | --- |
| **SecurityContextHolder** | API tĩnh sử dụng một SecurityContextHolderStrategy ở phía sau. | Cho code hiện tại truy cập/thiết lập/xóa SecurityContext theo chiến lược đang cấu hình. |
| **SecurityContext** | Đối tượng chứa Authentication, có thể rỗng. | Giữ trạng thái xác thực đang được xem là context hiện tại. |
| **Authentication** | Principal, credentials, authorities, trạng thái authenticated và details. | Biểu diễn yêu cầu xác thực hoặc kết quả xác thực đã được kiểm chứng. |
| **GrantedAuthority** | Một quyền/role/scope được cấp cho principal. | Dùng trong quy tắc authorization, ví dụ ROLE_ADMIN hoặc orders:read. |
| **SecurityContextRepository** | Hợp đồng lưu/đọc context giữa các request hoặc dispatch. | Xác định context có được khôi phục từ session/request và lưu lại hay không. |

Quan hệ khái quát:

~~~text
SecurityContextHolder
        |
        v
SecurityContext
        |
        v
Authentication
   |          |            |
   v          v            v
principal  credentials  authorities
("alice")  (thường đã   [ROLE_USER,
            xóa sau      orders:read]
            xác thực)
~~~

Khi một Controller gọi:

~~~java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();
~~~

nó đang lấy **Authentication trong SecurityContext gắn với thread hiện tại** theo chiến lược của holder. Code đó **không** tự đi xác minh password, tra user từ database, kiểm JWT hay tạo session.

### 1.1. SecurityContext là nơi lưu trạng thái, không phải AuthenticationManager

**AuthenticationManager** và AuthenticationProvider có trách nhiệm kiểm credential để tạo Authentication hợp lệ. **SecurityContextHolder** chỉ làm việc với context đã được cơ chế bảo mật gắn vào. Việc tự tạo một Authentication rồi đặt vào holder mà không kiểm chứng credential không phải là một luồng xác thực an toàn.

Một request điển hình có hai giai đoạn khác nhau:

- **Authentication**: credential được xác minh; kết quả Authentication hợp lệ được đưa vào context.
- **Authorization**: luật URL/method/domain quyết định Authentication hiện có có quyền gọi thao tác hay không.

Nếu người dùng nhận **403** sau khi đã đăng nhập đúng, việc tìm lỗi trong SecurityContextHolder cần tập trung vào authorities hoặc quy tắc authorization chứ không tự động kết luận password sai.

## 2. Vòng đời SecurityContext trong một Servlet request

Trong ứng dụng Servlet, một request đi qua servlet filter chain trước khi đến DispatcherServlet, Controller và Service:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["DelegatingFilterProxy"]
    B --> C["FilterChainProxy / SecurityFilterChain phù hợp"]
    C --> D["SecurityContextHolderFilter: nạp/defer context"]
    D --> E["Authentication filter nếu có credential"]
    E --> F["AuthenticationManager/Provider xác minh"]
    F --> G["SecurityContextHolder có SecurityContext/Authentication"]
    G --> H["AuthorizationFilter + các security filters khác"]
    H --> I["DispatcherServlet / Controller / Service"]
    I --> J["Response"]
    J --> K["Hoàn tất filter processing: dọn context"]
~~~

Sơ đồ cố ý giản lược thứ tự một số filter, exception translation, anonymous authentication, session và error dispatch. **Không phải request nào cũng chạy một authentication filter thành công**: request public không credential có thể mang anonymous Authentication; request bị từ chối có thể không bao giờ vào Controller.

Các điểm quan trọng:

1. **DelegatingFilterProxy** nối thế giới Servlet container với Spring-managed filters.
2. **FilterChainProxy** chọn SecurityFilterChain khớp request. Cấu hình có nhiều chain phải bảo vệ cả các URL ngoài matcher hẹp.
3. **SecurityContextHolderFilter** trong cấu hình Spring Security 6 thông dụng nạp/defer context từ SecurityContextRepository, để các filter sau sử dụng.
4. Authentication filter (Basic, form login, Bearer...) xác thực credential phù hợp và có thể thiết lập context chứa Authentication thành công.
5. **Authorization** dựa vào Authentication từ context; nếu không đáp ứng, request có thể bị chặn.
6. Controller/Service có thể truy cập principal trong phạm vi request.
7. Khi request/luồng filter kết thúc, framework **dọn holder** để thread được Servlet container tái sử dụng không mang danh tính của người trước.

### 2.1. Vì sao phải dọn SecurityContextHolder?

Servlet container dùng thread pool. Thread T1 vừa phục vụ Alice có thể được dùng để xử lý Bob hoặc một request ẩn danh sau đó. Nếu T1 vẫn giữ context Alice, request tiếp theo có thể nhìn thấy **danh tính và quyền của Alice**, là lỗi bảo mật nghiêm trọng.

Spring Security quản lý việc clear context trong vòng đời filter của nó. Nếu tự setContext trong code chạy **ngoài** vòng đời filter chuẩn (test đơn vị, scheduled task, background executor, thư viện tự quản lý thread), phải đảm bảo **clearContext trong finally** khi sở hữu trách nhiệm cleanup. Đừng dựa vào ThreadLocal tự mất khi thread được tái sử dụng.

### 2.2. Điều gì xảy ra khi request không có Authentication?

SecurityContextHolder.getContext() có thể trả một SecurityContext **không chứa Authentication**. Vì vậy:

~~~java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();

String username = authentication == null
    ? "none"
    : authentication.getName();
~~~

Đây là **mảnh code minh họa có thể đặt trong một method đã import**. Đừng viết getAuthentication().getName() ở code chạy ngoài security filter khi chưa xử lý khả năng null.

Trong request đã qua **AnonymousAuthenticationFilter**, authentication có thể là **AnonymousAuthenticationToken**, không phải null. Điểm tinh tế: AnonymousAuthenticationToken có thể trả **isAuthenticated() = true** theo hợp đồng Authentication dù nó **không** đại diện người đăng nhập thật. Vì thế **auth != null && auth.isAuthenticated() không đủ** để kết luận request là user đã đăng nhập. Dùng policy authenticated() của Spring Security hoặc AuthenticationTrustResolver/điều kiện tương ứng khi cần phân biệt anonymous với principal đáng tin.

## 3. Default strategy: MODE_THREADLOCAL

Mặc định SecurityContextHolder dùng **MODE_THREADLOCAL**: SecurityContext được giữ theo luồng Java, thường là thread đang phục vụ request Servlet.

~~~text
Thread servlet-1
  SecurityContextHolder -> Authentication(alice)

Thread servlet-2
  SecurityContextHolder -> Authentication(bob)

Thread servlet-3
  SecurityContextHolder -> empty / anonymous
~~~

Ba dòng minh họa không phải một global map hiển thị tất cả user; mỗi thread tự nhìn thấy context gắn với nó.

**Lợi ích:** Service đang chạy trong cùng thread có thể truy cập Authentication mà không chuyển object qua nhiều tầng. **Giới hạn:** khi chuyển sang một thread khác, ThreadLocal của thread mới thường **không có context trước đó**.

### 3.1. Các mode của SecurityContextHolder

| Mode | Hành vi | Hướng sử dụng |
| --- | --- | --- |
| **MODE_THREADLOCAL** | Context gắn với thread hiện tại. | **Mặc định phù hợp** cho phần lớn Servlet application. |
| **MODE_INHERITABLETHREADLOCAL** | Thread mới tạo có thể kế thừa giá trị context từ thread cha lúc tạo. | Chỉ dùng khi hiểu rõ lifecycle; **không thay thế propagation an toàn trong thread pool**. |
| **MODE_GLOBAL** | Dùng một context chung trong JVM. | Không phù hợp cho multi-user Servlet server vì dễ lẫn danh tính giữa các request. |
| **Custom SecurityContextHolderStrategy** | Tự định nghĩa cách lưu/truy cập context. | Chỉ khi có use case chuyên biệt và kiểm thử nghiêm ngặt. |

**Không chuyển sang MODE_GLOBAL** để “giải quyết” việc service async không nhìn thấy user. Một server phục vụ Alice và Bob đồng thời sẽ có rủi ro gắn chung principal cho cả hai.

**Không thay đổi strategy động lúc server đang phục vụ request**. Strategy là cấu hình cấp hệ thống; thay bằng setStrategyName hoặc setContextHolderStrategy sau khi nhiều thread đã hoạt động có thể gây race conditions và sự không nhất quán. Phần lớn ứng dụng nên giữ mặc định.

### 3.2. ThreadLocal không đồng nghĩa session

ThreadLocal sống theo **thread**, không sống theo **tài khoản** hay **HTTP session**:

- Thread hôm nay xử lý Alice, sau đó có thể xử lý Bob.
- HTTP session có thể tồn tại qua nhiều request và qua nhiều thread.
- SecurityContextRepository có thể nạp context từ session vào holder ở request mới.
- Một API stateless có thể xác thực Bearer/Basic ở từng request mà không lưu context trong session.
- SecurityContextHolder không phải cơ sở dữ liệu người dùng và không phải token store.

Đây là điểm quyết định khi debug: **“tôi đã setContext ở request trước” không bảo đảm context xuất hiện ở request sau**.

## 4. Các API SecurityContextHolder thường dùng

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// 1. Đọc context hiện tại.
SecurityContext current = SecurityContextHolder.getContext();

// 2. Đọc Authentication nếu có.
Authentication auth = current.getAuthentication();

// 3. Tạo context hoàn toàn mới để thiết lập có chủ đích.
SecurityContext fresh = SecurityContextHolder.createEmptyContext();

// 4. Chỉ đặt Authentication đã được xác minh bởi nguồn tin cậy.
fresh.setAuthentication(verifiedAuthentication);

// 5. Đặt context vào holder của luồng hiện tại.
SecurityContextHolder.setContext(fresh);

// 6. Dọn context khi chính code sở hữu lifecycle ngoài filter.
SecurityContextHolder.clearContext();
~~~

Đây là **mảnh code giải thích API**, không phải một method chạy nguyên khối: biến verifiedAuthentication phải được tạo bởi cơ chế xác thực đáng tin cậy, và không được vô điều kiện set hoặc clear holder trong giữa request bình thường.

### 4.1. Vì sao nên createEmptyContext()?

Spring Security khuyến nghị khi cần thiết lập Authentication theo cách thủ công thì tạo một **SecurityContext mới**:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(authenticationVerified);
SecurityContextHolder.setContext(fresh);
~~~

Không nên tùy tiện sửa trực tiếp một SecurityContext được chia sẻ:

~~~java
// Kém an toàn hơn nếu ngữ cảnh có thể đang được chia sẻ:
SecurityContextHolder.getContext()
    .setAuthentication(authenticationVerified);
~~~

Tạo context mới giúp giảm rủi ro **race condition** khi nhiều thread/luồng xử lý tình cờ tham chiếu cùng một SecurityContext object. Nó không thay thế bước xác minh credential; cũng không làm context tự được lưu sang request sau.

### 4.2. getContext() khác getDeferredContext()

Các phiên bản Spring Security 6 còn có cơ chế **deferred SecurityContext**, cho phép việc load context từ repository chỉ diễn ra khi cần. Điều này có thể giảm công việc không cần thiết trên request không truy cập authentication.

Không tự diễn giải rằng gọi getContext() luôn truy vấn database hoặc session; kết quả tùy strategy/repository/filter. Khi viết filter tích hợp sâu, ưu tiên API chính thức của phiên bản cụ thể thay vì giữ một tham chiếu SecurityContext tĩnh lâu dài.

## 5. Servlet filters nào nạp, lưu và dọn context?

### 5.1. SecurityContextHolderFilter: hướng thường gặp trong Spring Security 6

**SecurityContextHolderFilter** có nhiệm vụ **đưa ngữ cảnh từ SecurityContextRepository vào phạm vi truy cập của SecurityContextHolder**, thường hỗ trợ deferred loading. Nó **không tự lưu thay đổi của context** vào repository để request sau sử dụng.

Với chế độ **requireExplicitSave(true)**, nếu **custom code** tự đăng nhập rồi muốn duy trì đăng nhập qua session, cần **gọi SecurityContextRepository.saveContext(context, request, response)** ở vị trí thích hợp.

~~~text
Request mới
  -> SecurityContextHolderFilter load/defer SecurityContext
  -> Authentication mechanism / authorization / Controller
  -> Custom authentication thành công?
       -> SecurityContextHolder.setContext(newContext)
       -> Nếu cần lưu sang request sau:
            SecurityContextRepository.saveContext(newContext, request, response)
  -> Filter kết thúc và dọn holder
~~~

Đừng suy ra từ việc SecurityContextHolder.getContext() có principal ở request hiện tại rằng session đã được ghi thành công.

### 5.2. SecurityContextPersistenceFilter: cơ chế cũ và tương thích

**SecurityContextPersistenceFilter** nạp context trước filter chain và theo dõi việc lưu context đã thay đổi khi hoàn tất/commit response theo repository. Trong cơ chế đó, nhiều ứng dụng cũ chỉ cần setContext và framework lưu thay đổi qua repository.

**Spring Security 6 thường mặc định sử dụng SecurityContextHolderFilter với explicit-save**, thay vì lối tự lưu của SecurityContextPersistenceFilter ở Spring Security 5. Hai filter này không nên cùng được thêm như hai cơ chế cạnh tranh trong một chain.

Đây là nguyên nhân phổ biến của bug khi nâng cấp:

~~~text
Ứng dụng cũ:
  custom filter set SecurityContextHolder
  -> cơ chế cũ tự lưu context

Nâng cấp sang Spring Security 6:
  custom filter set SecurityContextHolder
  -> request hiện tại có user
  -> request sau không có user vì custom filter chưa gọi saveContext()
~~~

**Không sửa bằng cách tắt authorization hoặc để quyền truy cập public.** Hãy xác định đúng SecurityContextRepository và liệu cơ chế xác thực đã save context theo policy hay chưa.

### 5.3. Cơ chế authentication có sẵn thường quản lý phần lưu phù hợp

Form login, remember-me, Basic, Bearer token và các filter framework hỗ trợ có những logic riêng cho việc gắn context và lưu khi cần. **Không thêm saveContext() vào mọi Controller** chỉ vì framework 6 dùng explicit-save.

Chỉ khi tự xây một authentication filter/controller và chủ động muốn **duy trì login giữa request**, cần áp dụng contract đúng. Nếu thiết kế **stateless**, không lưu session mới là mong muốn; việc tự save rồi nghĩ là đã tạo session có thể sai với NullSecurityContextRepository.

## 6. SecurityContextRepository: lưu ở đâu và trong bao lâu?

SecurityContextHolder và SecurityContextRepository giải quyết hai bài toán khác nhau:

- Holder giúp **code ở thread hiện tại** truy cập context.
- Repository giúp **đọc/lưu context** theo một nguồn thích hợp qua request hoặc dispatch.

| Repository | Ý nghĩa | Dùng khi nào? |
| --- | --- | --- |
| **HttpSessionSecurityContextRepository** | Lưu/liên kết context với HttpSession. | Ứng dụng web có session login, theo policy và lifecycle của session. |
| **RequestAttributeSecurityContextRepository** | Giữ context theo request attribute để phục vụ các servlet dispatch như error dispatch trong cùng request. | Khi muốn context có sẵn trong các dispatch của một request. |
| **DelegatingSecurityContextRepository** | Kết hợp nhiều repository; có thể nạp từ một delegate, save qua nhiều delegate. | Cấu hình mặc định thường gồm request attribute + HTTP session trong Spring Security 6. |
| **NullSecurityContextRepository** | Không lưu context để lấy lại ở request sau. | API stateless không gắn authentication với session. |

**RequestAttributeSecurityContextRepository không phải session**: một error dispatch có thể vẫn thấy context trong cùng request, nhưng request HTTP mới không tự kế thừa.

**NullSecurityContextRepository không có nghĩa bỏ qua authentication**: filter vẫn có thể xác thực Basic/Bearer token của từng request và đặt Authentication trong holder hiện tại, sau đó context được dọn khi kết thúc.

### 6.1. Minh họa cấu hình repository cho stateful login

Trong một ứng dụng **session-based** (khác ví dụ stateless ở mục 9), cấu hình có thể gồm:

~~~java
// Mảnh DSL trong một SecurityFilterChain session-based:
.securityContext(securityContext -> securityContext
    .requireExplicitSave(true)
    .securityContextRepository(
        new DelegatingSecurityContextRepository(
            new RequestAttributeSecurityContextRepository(),
            new HttpSessionSecurityContextRepository()
        )
    )
)
~~~

Code này cần import các repository từ **org.springframework.security.web.context**. Nếu chỉ dùng cấu hình mặc định của Spring Security 6 phù hợp, bạn không nhất thiết phải tự khai báo lại repository; ví dụ nhằm hiểu cách phối hợp các delegate.

### 6.2. Minh họa cấu hình stateless

Trong API không muốn lưu authentication trong HttpSession:

~~~java
// Mảnh DSL trong SecurityFilterChain dùng HttpSecurity:
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
.securityContext(securityContext -> securityContext
    .securityContextRepository(new NullSecurityContextRepository()))
~~~

Code cần import **org.springframework.security.config.http.SessionCreationPolicy** và **org.springframework.security.web.context.NullSecurityContextRepository**. Nó không phải file Java hoàn chỉnh.

**STATELESS** trong Spring Security là một chính sách của security layer; nó không bảo đảm toàn bộ ứng dụng, servlet container hoặc thư viện khác tuyệt đối không bao giờ tạo một HttpSession cho mục đích riêng. Cần kiểm từng thành phần và cookies trên response.

### 6.3. Save context không bằng cấp quyền

Nếu một custom login đã xác thực Alice với ROLE_USER và lưu context, request sau có thể khôi phục danh tính Alice. Điều này **không tự cho Alice quyền ROLE_ADMIN**. Authorization vẫn dựa trên Authentication authorities và các policy ở URL/Service/domain.

Cũng cần xem **session fixation protection, CSRF, session timeout, logout, session invalidation, concurrent sessions** khi chủ động thiết kế đăng nhập bằng session. SecurityContextRepository là một mảnh quan trọng, không phải toàn bộ giải pháp session security.

## 7. Ví dụ custom authentication: thiết lập và lưu context đúng lúc

Đây là **mảnh code minh họa bên trong một custom authentication filter hoặc một flow đăng nhập đã được kiểm soát**. Nó không phải Controller login hoàn chỉnh để chép vào production, vì chưa biểu diễn validation, exception handling, CSRF, session fixation, success/failure handlers và các kiểm soát khác.

~~~java
// Giả sử có authenticationManager, securityContextRepository,
// HttpServletRequest request, HttpServletResponse response,
// String username và char/password input được xử lý an toàn.

Authentication attempt =
    UsernamePasswordAuthenticationToken.unauthenticated(
        username, rawPassword);

Authentication result =
    authenticationManager.authenticate(attempt);

// Chỉ sau authenticate() thành công, tạo context mới.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

// Chỉ nếu chọn thiết kế LƯU LOGIN qua nhiều request.
// NullSecurityContextRepository sẽ không lưu được phiên.
securityContextRepository.saveContext(context, request, response);
~~~

Các nguyên tắc bắt buộc:

1. **Credential phải được kiểm trước** qua AuthenticationManager hoặc cơ chế tin cậy; không nhận role từ client rồi setAuthenticated(true).
2. Chỉ dùng **Authentication kết quả đã xác thực**. Tránh đặt UsernamePasswordAuthenticationToken chưa được kiểm vào holder rồi xem là principal thật.
3. Dùng **createEmptyContext()** thay vì sửa bừa một context cũ có thể bị chia sẻ.
4. **SaveContext chỉ khi cần persistence** và repository thực sự hỗ trợ; dùng đúng request/response, trước khi response được commit theo yêu cầu.
5. Nếu custom filter tự quản lý context ngoài vòng đời chuẩn, cần clear trong finally; nếu đang ở trong chain được Spring Security quản lý, phải tôn trọng lifecycle của framework, tránh xóa context quá sớm.
6. Nếu có HTTP session, cần xem session authentication strategy và session fixation, không triển khai login chỉ bằng mười dòng trên.
7. Không log rawPassword, result credentials hoặc session cookie; nguyên tắc bảo vệ secrets không thay đổi.

### 7.1. Vì sao đăng nhập thành công trong request A nhưng request B vẫn 401?

Giả sử custom filter đặt context đúng trong request A, Controller trả 200, nhưng request B chỉ gửi cookie và nhận 401. Các nguyên nhân:

- Dùng **SecurityContextHolderFilter** và custom code **quên saveContext**.
- Đã save vào **NullSecurityContextRepository** vốn không giữ state.
- Không có hoặc không gửi đúng session cookie.
- Browser không gửi cookie vì domain/path/SameSite/Secure policy.
- Session hết hạn hoặc bị invalidated.
- Filter chain của request B chọn repository khác.
- Ứng dụng dùng stateless Basic/Bearer nên **request B phải gửi credential**.

Cách debug đúng là kiểm cơ chế xác thực, repository, session policy và thực tế cookie/token, không gỡ rule authenticated().

## 8. Các cách lấy principal trong Servlet Controller

Trong Spring MVC, không phải lúc nào cũng cần gọi API tĩnh của SecurityContextHolder trực tiếp. Framework có thể tiêm thông tin vào handler:

| Cách đọc | Ví dụ | Khi phù hợp |
| --- | --- | --- |
| **SecurityContextHolder.getContext()** | Lấy SecurityContext rồi getAuthentication(). | Code cần truy cập context ở lớp không có method argument hỗ trợ. |
| **Authentication method argument** | public ... me(Authentication authentication) | Controller muốn current Authentication trực tiếp. |
| **Principal method argument** | public ... me(Principal principal) | Chỉ cần tên/danh tính trừu tượng. |
| **@AuthenticationPrincipal** | public ... me(@AuthenticationPrincipal UserDetails user) | Biết principal type của cơ chế auth hiện tại. |
| **@CurrentSecurityContext** | Nhận SecurityContext hoặc expression lấy Authentication. | Muốn truy cập context hiện tại qua annotation. |
| **HttpServletRequest.getUserPrincipal()** | Servlet API từ request wrapper. | Tích hợp code Servlet, filter hoặc thư viện cũ. |

### 8.1. Lấy principal qua Authentication

~~~java
@GetMapping("/api/me")
Map<String, String> me(Authentication authentication) {
    return Map.of("username", authentication.getName());
}
~~~

Đây là **mảnh method**: để chạy cần @RestController/@GetMapping và imports. Một endpoint protected bởi authenticated() có thể dựa vào Authentication được Spring Security cấp; không tin userId từ request để xác định danh tính.

### 8.2. Lấy UserDetails bằng annotation

~~~java
@GetMapping("/api/principal")
Map<String, String> principal(
        @AuthenticationPrincipal UserDetails user) {
    return Map.of("username", user.getUsername());
}
~~~

**Chỉ đúng khi principal thực sự là UserDetails** (thường gặp ở form/Basic với DaoAuthenticationProvider). Với JWT Resource Server, principal có thể là Jwt; với OAuth2 login có thể là OidcUser/OAuth2User. Nếu gắn chặt UserDetails vào mọi endpoint, có thể nhận null hoặc ClassCastException khi đổi cơ chế auth.

Khi chỉ cần username, **Authentication.getName()** thường ít phụ thuộc implementation hơn. Khi cần ID nội bộ hoặc tenant, thiết kế principal/domain identity adapter từ thông tin đã xác minh.

### 8.3. @CurrentSecurityContext

~~~java
@GetMapping("/api/context-name")
Map<String, String> context(
    @CurrentSecurityContext(expression = "authentication.name")
    String username) {

    return Map.of("username", username);
}
~~~

Mảnh code yêu cầu import org.springframework.security.core.annotation.CurrentSecurityContext và các kiểu Spring MVC. Expression được xử lý theo annotation và SecurityContext; nếu chưa xác thực hoặc principal khác kiểu, cần bảo đảm endpoint có policy thích hợp và xử lý null.

**Không tự tạo một singleton service giữ Authentication làm field** để “tiện cho Controller”. Một singleton được dùng cho tất cả request và có nguy cơ trộn thông tin user.

## 9. Dự án đầy đủ Java 17: SecurityContextHolder với HTTP Basic stateless

Dự án này thiết kế **stateless có chủ đích** để dễ kiểm chứng vòng đời context: client gửi HTTP Basic credential **mỗi request**, filter đặt Authentication trong SecurityContextHolder **trong request**, Controller đọc được, sau request không có session authentication được lưu. Test cũng kiểm request sau không gửi credential phải bị 401, không tự kế thừa Alice.

**Chú ý:** HTTP Basic + mật khẩu demo ở localhost chỉ để học. Khi vận hành thực phải có HTTPS, nguồn danh tính tin cậy, bảo vệ credential, lựa chọn authentication mechanism phù hợp và kiểm thử an ninh thực tế. Các ví dụ chỉ dùng HTTP GET, không yêu cầu tắt CSRF.

### 9.1. Cấu trúc thư mục

~~~text
servlet-context-demo/
  pom.xml
  src/main/java/com/example/contextdemo/
    ServletContextApplication.java
    SecurityConfig.java
    ContextController.java
  src/test/java/com/example/contextdemo/
    ContextHttpTests.java
    ContextThreadTests.java
~~~

Yêu cầu **Java 17+**, Maven 3.9+ và cổng 8080 trống. Package trong tất cả file Java là **com.example.contextdemo**.

### 9.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.6</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-context-demo</artifactId>
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
~~~

Đây là ứng dụng **Servlet/Spring MVC**, không phải WebFlux. Nếu thêm spring-boot-starter-webflux vào một project có cả web và webflux, Boot thường chọn MVC server theo cơ chế cấu hình; không dùng HttpSecurity để kết luận chain reactive đã được bảo vệ.

### 9.3. ServletContextApplication.java

~~~java
package com.example.contextdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ServletContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextApplication.class, args);
    }
}
~~~

Class main đặt trong package gốc, giúp Spring Boot tìm SecurityConfig và ContextController.

### 9.4. SecurityConfig.java

~~~java
package com.example.contextdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
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

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo-alice"))
            .authorities("ROLE_USER", "orders:read")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("demo-admin"))
            .authorities("ROLE_ADMIN", "orders:read")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .securityContext(context -> context
                .securityContextRepository(
                    new NullSecurityContextRepository()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/api/principal")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

**Phân tích cấu hình:**

1. **UserDetailsService** dùng hai user giả, BCryptPasswordEncoder tạo hash từ password demo.
2. HTTP Basic xác thực username/password trên từng request có Authorization phù hợp.
3. **SessionCreationPolicy.STATELESS** yêu cầu Spring Security không tạo hoặc sử dụng HTTP session để lấy Authentication. Đây là ý định cho API lab.
4. **NullSecurityContextRepository** không lưu SecurityContext để khôi phục trong request sau.
5. **/api/public** là GET công khai có chủ đích; mọi HTTP method khác trên cùng path không tự được phép.
6. **/api/me** và **/api/principal** yêu cầu authenticated().
7. **/api/admin** yêu cầu ROLE_ADMIN, không phải bất cứ ai có credential đúng.
8. **anyRequest().denyAll()** từ chối những URL/method khác chưa có policy rõ ràng.
9. Demo **không tắt CSRF**, vì chỉ thực hiện GET. Nếu thêm POST/PUT/DELETE, phải thiết kế CSRF theo credential/browser threat model.
10. **SecurityContextHolder được framework quản lý trong từng request**, nên Controller không gọi setContext hoặc clearContext.

Không thêm một custom filter tự set ROLE_ADMIN vì thấy header X-Role: ADMIN; authorities chỉ được tạo từ UserDetails/nguồn xác thực đáng tin sau khi password đã được kiểm.

### 9.5. ContextController.java

~~~java
package com.example.contextdemo;

import java.util.List;
import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ContextController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, Object> currentUser(
            Authentication methodArgument) {

        Authentication fromHolder = SecurityContextHolder
            .getContext().getAuthentication();

        List<String> authorities = fromHolder.getAuthorities()
            .stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();

        return Map.of(
            "name", fromHolder.getName(),
            "sameNameAsMethodArgument",
                fromHolder.getName().equals(methodArgument.getName()),
            "authorities", authorities
        );
    }

    @GetMapping("/api/principal")
    public Map<String, String> userDetailsPrincipal(
            @AuthenticationPrincipal UserDetails user) {

        return Map.of("username", user.getUsername());
    }

    @GetMapping("/api/admin")
    public Map<String, String> adminOnly() {
        return Map.of("message", "admin");
    }
}
~~~

**Vì sao từ holder không null trong /api/me?** SecurityFilterChain yêu cầu authenticated() cho endpoint này và HTTP Basic filter đã tạo Authentication nếu credential hợp lệ. Trong một Controller public hoặc một scheduled job, giả định đó có thể không đúng; hãy kiểm null hoặc dùng annotation/method argument phù hợp.

**sameNameAsMethodArgument** cho thấy Authentication do MVC cấp và Authentication từ holder mô tả cùng principal trong request. **Không dùng phép so sánh tên làm kiểm tra bảo mật**; việc xác thực đã diễn ra ở filter và kiểm quyền ở authorization.

**Không trả UserDetails nguyên object qua JSON**: nó có thể chứa password hash và account flags không dành cho client. API demo chỉ xuất username/authorities để quan sát. Trên production, ngay cả authorities nội bộ cũng chỉ nên trả nếu có mục đích rõ.

### 9.6. Chạy ứng dụng

~~~bash
mvn test
mvn spring-boot:run
~~~

Trên Windows PowerShell dùng **curl.exe**, Linux/macOS dùng curl. Các lệnh dưới đây chỉ dùng credential giả trên localhost:

~~~powershell
curl.exe -i http://localhost:8080/api/public
curl.exe -i http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/me
curl.exe -i -u alice:demo-alice http://localhost:8080/api/principal
curl.exe -i -u alice:demo-alice http://localhost:8080/api/admin
curl.exe -i -u admin:demo-admin http://localhost:8080/api/admin
curl.exe -i -H "X-Role: ADMIN" http://localhost:8080/api/admin
~~~

Bảng kết quả dự kiến:

| Request | Status | Lý do |
| --- | --- | --- |
| GET /api/public ẩn danh | 200 | PermitAll() có chủ đích, body message=public. |
| GET /api/me ẩn danh | 401 | Không có credential hợp lệ cho endpoint protected. |
| GET /api/me với alice/demo-alice | 200 | Basic auth hợp lệ, holder chứa Authentication alice trong request. |
| GET /api/principal với alice | 200 | @AuthenticationPrincipal lấy UserDetails alice. |
| GET /api/admin với alice | 403 | Alice không có ROLE_ADMIN. |
| GET /api/admin với admin/demo-admin | 200 | Có ROLE_ADMIN. |
| GET /api/admin chỉ với header X-Role | 401 | Header tùy ý không phải credential đáng tin. |

Response JSON của /api/me với alice có các trường:

~~~json
{
  "name": "alice",
  "sameNameAsMethodArgument": true,
  "authorities": ["ROLE_USER", "orders:read"]
}
~~~

**Không khẳng định thứ tự key JSON luôn như ví dụ**; các phần tử authorities được sort trong code nên mảng có thứ tự ổn định. Các header HTTP khác có thể xuất hiện tùy servlet container.

**Kiểm request độc lập:** Sau khi GET /api/me với Basic hợp lệ trả 200, gọi lại **GET /api/me không gửi Authorization** sẽ là **401**. Lý do: ở cấu hình này không lưu Authentication vào session, nên context request trước không tự đi sang request sau.

## 10. Test HTTP qua MockMvc: đọc context đúng request

Tạo **src/test/java/com/example/contextdemo/ContextHttpTests.java**:

~~~java
package com.example.contextdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextHttpTests {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void privateEndpointNeedsCredentials() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicAuthenticationIsVisibleInHolder()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.sameNameAsMethodArgument")
                .value(true))
            .andExpect(jsonPath("$.authorities[0]")
                .value("ROLE_USER"))
            .andExpect(jsonPath("$.authorities[1]")
                .value("orders:read"));
    }

    @Test
    void authenticationPrincipalResolvesUserDetails()
            throws Exception {
        mvc.perform(get("/api/principal")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("alice"));
    }

    @Test
    void incorrectPasswordIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownUserIsRejected() throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("missing", "anything")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void ordinaryUserCannotAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminCanAccessAdmin() throws Exception {
        mvc.perform(get("/api/admin")
                .with(httpBasic("admin", "demo-admin")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void adminEndpointNeedsAuthentication() throws Exception {
        mvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void forgedRoleHeaderDoesNotAuthenticate() throws Exception {
        mvc.perform(get("/api/admin")
                .header("X-Role", "ADMIN"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void unknownRouteIsDeniedEvenForValidUser()
            throws Exception {
        mvc.perform(get("/api/unknown")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void previousRequestDoesNotLeakIdentity()
            throws Exception {
        mvc.perform(get("/api/me")
                .with(httpBasic("alice", "demo-alice")))
            .andExpect(status().isOk());

        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Bộ này có **12 kiểm thử HTTP**, bao phủ các trạng thái 200/401/403, sự đồng nhất danh tính trong request và **không kế thừa identity từ request trước**.

MockMvc gắn với Spring TestContext và SecurityFilterChain; nó kiểm luồng MVC/Security mà không mở cổng mạng. Nó không tự chứng minh reverse proxy, TLS, session cookie trong browser hoặc setup production đã đúng.

### 10.1. Vì sao dùng httpBasic() thay vì chỉ @WithMockUser?

**@WithMockUser** là công cụ mô phỏng Authentication cho test authorization. Nó rất hữu ích khi chỉ quan tâm quyền, nhưng **không xác minh password thật, PasswordEncoder, UserDetailsService hay BasicAuthenticationFilter**.

Trong bộ test này, **httpBasic("alice", "demo-alice")** gửi một HTTP Basic header, để chuỗi filter và nguồn người dùng mẫu quyết định authentication. Vì mục tiêu là quan sát **SecurityContextHolder trong Servlet request**, cách test đó minh họa một luồng auth thực tế hơn.

Khi test phương thức độc lập cần mô phỏng principal, bạn vẫn có thể dùng @WithMockUser hoặc SecurityMockMvcRequestPostProcessors.user(...), nhưng phải biết rõ thứ gì được mock và thứ gì được xác minh thực.

## 11. SecurityContextHolder với thread mới và ExecutorService

Đây là khu vực có lỗi tinh vi. Vì default strategy dùng **ThreadLocal**, context trong servlet thread **không tự xuất hiện** trong một thread do ExecutorService chạy.

~~~text
Servlet thread:
  Authentication = alice
       |
       | executor.submit(task)
       v
Worker thread:
  SecurityContextHolder.getContext()
  -> thường không có Authentication của alice
~~~

Nếu background job cần được phép xử lý dưới danh tính Alice, phải có **propagation có chủ đích**; nếu không nên xử lý dưới một service identity riêng với quyền tối thiểu. Không tự copy một chuỗi username vào global variable rồi cho background task “được phép” thay người dùng.

### 11.1. DelegatingSecurityContextRunnable

Spring Security cung cấp **DelegatingSecurityContextRunnable** để chạy một Runnable với SecurityContext được cung cấp. Wrapper thiết lập context trong worker thread trước khi gọi delegate và dọn context sau đó theo contract, kể cả khi delegate ném exception.

~~~java
// Mảnh code minh họa trong một method có các biến phù hợp.
// Dùng context đã được chọn sau xác thực và kiểm quyền cần thiết.
SecurityContext context =
    SecurityContextHolder.getContext();

Runnable businessTask = () -> {
    Authentication auth = SecurityContextHolder
        .getContext().getAuthentication();
    // Sử dụng auth theo policy, không log secrets.
};

Runnable wrapped =
    new DelegatingSecurityContextRunnable(businessTask, context);

executor.execute(wrapped);
~~~

Cần import org.springframework.security.concurrent.DelegatingSecurityContextRunnable. **Đây không phải lời khuyên chạy mọi business task với identity của request**. Context có thể mang quyền nhạy cảm hoặc snapshot đã cũ; job chạy sau nhiều giờ cần chính sách re-authorization và auditing phù hợp.

### 11.2. Vì sao MODE_INHERITABLETHREADLOCAL không giải quyết thread pool?

Thread trong executor thường được tạo và tái sử dụng; InheritableThreadLocal có thể kế thừa giá trị **lúc thread được tạo**, không phải tự cập nhật mỗi khi submit một task. Điều đó có thể gây:

- Worker không thấy request context mới.
- Worker giữ identity cũ của một request khác.
- Ngữ cảnh được vô tình truyền đến job không cần quyền.
- Race condition khi nhiều request gửi task vào cùng pool.

Ưu tiên wrapper/executor tích hợp của Spring Security hoặc một cách truyền identity **có kiểm soát và được xác minh**. Không đổi global strategy để chữa lỗi từng task.

### 11.3. Async trong Spring MVC

Spring MVC có thể dùng Callable, DeferredResult, @Async hoặc AsyncContext.start. Spring Security có tích hợp propagation cho **một số cơ chế async cụ thể**, nhưng không nên xem **tất cả CompletableFuture, ExecutorService và thư viện callback** đều tự bảo toàn SecurityContext.

Đặc biệt:

- **Callable** do Spring MVC quản lý có tích hợp qua WebAsyncManagerIntegrationFilter theo mô hình tương ứng.
- **AsyncContext.start(Runnable)** có hỗ trợ qua tích hợp Servlet API của Spring Security khi wrapper được áp dụng.
- **ExecutorService tự tạo / CompletableFuture.supplyAsync** không mặc nhiên đảm bảo propagation.
- Với **@Async**, có thể sử dụng cơ chế phù hợp như DelegatingSecurityContextAsyncTaskExecutor, nhưng phải cấu hình đúng executor.

Cần test trên chính đường async đã dùng, bởi timing, thread reuse và việc clear context làm cho các lỗi này khó tái hiện chỉ bằng test login đồng bộ.

## 12. Kiểm thử ThreadLocal, propagation và cleanup bằng JUnit

Tạo **src/test/java/com/example/contextdemo/ContextThreadTests.java**. Class này kiểm trực tiếp SecurityContextHolder trên thread test và trên thread trong ExecutorService. Nó **không** tạo HTTP request nên phù hợp để học ranh giới ThreadLocal mà không lẫn MVC.

~~~java
package com.example.contextdemo;

import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.assertj.core.api.Assertions.assertThat;

class ContextThreadTests {

    private static SecurityContext contextForUnitUser() {
        Authentication verifiedForTest =
            UsernamePasswordAuthenticationToken.authenticated(
                "unit-user",
                null,
                List.of(new SimpleGrantedAuthority("ROLE_USER"))
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(verifiedForTest);
        return context;
    }

    @Test
    void manualContextMustBeClearedInFinally() {
        SecurityContextHolder.setContext(contextForUnitUser());
        try {
            assertThat(SecurityContextHolder.getContext()
                .getAuthentication().getName())
                .isEqualTo("unit-user");
        } finally {
            SecurityContextHolder.clearContext();
        }

        assertThat(SecurityContextHolder.getContext()
            .getAuthentication()).isNull();
    }

    @Test
    void newExecutorThreadDoesNotInheritDefaultThreadLocal()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        SecurityContextHolder.setContext(contextForUnitUser());

        try {
            Authentication inWorker = executor.submit(() ->
                SecurityContextHolder.getContext()
                    .getAuthentication()
            ).get(5, TimeUnit.SECONDS);

            assertThat(inWorker).isNull();
        } finally {
            SecurityContextHolder.clearContext();
            executor.shutdownNow();
        }
    }

    @Test
    void delegatingRunnablePropagatesAndCleansWorkerContext()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();
        SecurityContext context = contextForUnitUser();
        SecurityContextHolder.setContext(context);

        AtomicReference<String> observedName =
            new AtomicReference<>();

        Runnable work = () -> observedName.set(
            SecurityContextHolder.getContext()
                .getAuthentication().getName()
        );

        try {
            Runnable wrapped =
                new DelegatingSecurityContextRunnable(work, context);

            executor.submit(wrapped).get(5, TimeUnit.SECONDS);

            assertThat(observedName.get()).isEqualTo("unit-user");

            Authentication afterTask = executor.submit(() ->
                SecurityContextHolder.getContext()
                    .getAuthentication()
            ).get(5, TimeUnit.SECONDS);

            assertThat(afterTask).isNull();
        } finally {
            SecurityContextHolder.clearContext();
            executor.shutdownNow();
        }
    }
}
~~~

**Ba test** làm rõ:

1. Khi tự set context ở code không có filter quản lý, phải **clear trong finally**.
2. Thread mới từ executor, theo default MODE_THREADLOCAL, **không có Authentication của caller** nếu không propagation.
3. DelegatingSecurityContextRunnable **đưa context có chủ đích vào worker và dọn sau khi hoàn thành**, nên task tiếp theo trên cùng worker không tự nhìn thấy identity unit-user.

Cần nhớ context trong test được tạo từ **UsernamePasswordAuthenticationToken.authenticated(...)** cho mục đích unit test, không phải credential đã qua PasswordEncoder. **Không tái sử dụng mẫu tạo authenticated token trực tiếp với dữ liệu HTTP client trong production.**

### 12.1. Giới hạn kiểm thử thread

Những test trên chạy với default MODE_THREADLOCAL của Spring Security, không chứng minh mọi executor/framework đều hoạt động giống nhau. Nếu project đã thay strategy toàn JVM, điều kiện test cần được điều chỉnh hoặc khôi phục trước test một cách an toàn.

Với sản phẩm thật, bổ sung test cho worker pool tái sử dụng nhiều lần, task ném exception, task bị hủy và session/token được thu hồi trước khi job chạy. Một task chạy bằng context cũ vẫn có thể cần **kiểm quyền hiện hành** tại thời điểm thực hiện nghiệp vụ.

## 13. SecurityContextHolder và việc quản lý session

Một sơ đồ session-based:

~~~text
Lần 1: POST /login
  -> filter kiểm password thành công
  -> tạo SecurityContext(Authentication=alice)
  -> lưu vào HttpSessionSecurityContextRepository
  -> browser giữ cookie phiên

Lần 2: GET /dashboard + session cookie
  -> filter nạp context từ repository
  -> SecurityContextHolder của request có Alice
  -> authorize + Controller
  -> cuối request dọn ThreadLocal

Lần 3: GET /dashboard + session cookie
  -> có thể do một thread khác xử lý
  -> repository vẫn có thể nạp Alice theo session
~~~

Điểm cần hiểu: **Không phải ThreadLocal tự sống qua ba request**. Việc nối danh tính giữa các request nằm ở **repository/session cookie** hoặc một cơ chế token được xác minh lại ở request mới.

### 13.1. Form login và session fixation

Khi form login thành công, framework có cơ chế để xử lý session fixation, ví dụ thay session ID theo cấu hình phù hợp. Một custom authentication flow tự lưu SecurityContext mà bỏ qua SessionAuthenticationStrategy có thể tạo rủi ro session fixation, concurrent sessions hoặc trạng thái không nhất quán.

Đừng “tự làm form login” chỉ bằng setContext rồi saveContext. Nếu muốn tùy biến, ưu tiên authentication filter/handler chuẩn, cấu hình session và security context phù hợp, test login success/failure/logout/CSRF/session invalidation.

### 13.2. Logout làm gì với context?

Logout đúng cần xử lý những gì nằm trong threat model: SecurityContext hiện tại, SecurityContextRepository/HttpSession nếu stateful, session cookie và các remember-me/token liên quan. **SecurityContextHolder.clearContext() một mình không đảm bảo** session cũ bị vô hiệu hoặc token phát hành trước đó bị revoke.

Nếu dùng JWT stateless, clearContext chỉ tác động thread/request hiện tại; token đang hợp lệ vẫn có thể được gửi ở request mới. Cần TTL/revocation/introspection hoặc chính sách thu hồi phù hợp khi yêu cầu logout tức thời.

### 13.3. User bị khóa khi session đang tồn tại

Nếu một người đã đăng nhập bằng session trước đó rồi admin khóa account trong database, context trong session có thể vẫn chứa Authentication cũ. Không mặc định SecurityContextHolder sẽ tự gọi UserDetailsService trên mọi request để cập nhật bốn account flags.

Thiết kế sự thu hồi session, quyền và dữ liệu nhạy cảm phải tách khỏi việc lưu context. Điều tương tự áp dụng token JWT với claims/authorities đã phát hành trước đó.

## 14. Anonymous Authentication và kiểm tra quyền đúng cách

AnonymousAuthenticationFilter có thể tạo AnonymousAuthenticationToken cho request không đăng nhập. Đây là một Authentication object được framework sử dụng để biểu diễn người gọi anonymous, chứ không phải bằng chứng có password/JWT hợp lệ.

Cần phân biệt:

~~~java
Authentication auth = SecurityContextHolder
    .getContext().getAuthentication();

// Không đủ để xác nhận user thật:
boolean flag = auth != null && auth.isAuthenticated();
~~~

Một AnonymousAuthenticationToken có thể có isAuthenticated() = true. Để quyết định quyền truy cập URL, dùng framework rule **authenticated()** / **fullyAuthenticated()** / **anonymous()** theo yêu cầu, thay vì tự viết if (auth.isAuthenticated()) trong Controller.

Khi logic ứng dụng thật cần kiểm principal hiện tại:

~~~java
Authentication auth = SecurityContextHolder
    .getContext().getAuthentication();

AuthenticationTrustResolver resolver =
    new AuthenticationTrustResolverImpl();

boolean realUser = auth != null
    && auth.isAuthenticated()
    && !resolver.isAnonymous(auth);
~~~

Code là **mảnh Java**, cần import AuthenticationTrustResolver và AuthenticationTrustResolverImpl từ org.springframework.security.authentication. Với ứng dụng cần phân biệt remember-me và fully-authenticated, dùng resolver.isRememberMe(...) hoặc authorization rule phù hợp theo version.

**Không coi tên username "anonymousUser" là cơ chế nhận diện anonymous an toàn**: tên đó là giá trị cấu hình, có thể thay đổi hoặc trùng với user thật. Hãy sử dụng type/resolver/chính sách chính thức.

### 14.1. Có thể dùng SecurityContextHolder để kiểm role thủ công không?

Kỹ thuật:

~~~java
boolean isAdmin = SecurityContextHolder.getContext()
    .getAuthentication().getAuthorities().stream()
    .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
~~~

được dùng đôi khi trong integration code, nhưng thường **không phải lựa chọn đầu tiên** để bảo vệ endpoint. Ưu tiên cấu hình authorization ở HTTP và method/domain:

- **requestMatchers("/api/admin/**").hasRole("ADMIN")** cho đường HTTP.
- **@PreAuthorize("hasAuthority('orders:read')")** tại Service khi method security được bật.
- **Owner/tenant checks** trong domain Service khi quyền phụ thuộc đối tượng cụ thể.

Tự check role trong Controller dễ bỏ sót ở route mới hoặc ở nơi Service được gọi ngoài HTTP, và không tự xử lý IDOR/BOLA. Authentication từ context là input đáng tin **sau authentication**, nhưng quyền nghiệp vụ vẫn cần policy chính xác.

## 15. SecurityContextHolder và async/error dispatch

Một request Servlet có thể trải qua nhiều **dispatch type**: REQUEST, ASYNC, ERROR. Điều này có thể thay đổi thread và thời điểm xử lý security context.

### 15.1. Error dispatch

Một lỗi trong Controller có thể dẫn tới ERROR dispatch. Nếu context chỉ nằm trong ThreadLocal của một nhánh đã được clear, error handler có thể không thấy principal. **RequestAttributeSecurityContextRepository** được thiết kế để giữ context ở request attribute trong cùng request, giúp một số error dispatch truy cập ngữ cảnh khi được filter/dispatch cấu hình phù hợp.

Không dùng HttpSession chỉ để chữa mọi lỗi error dispatch; hiểu xem repository nào nên lưu state trong một request và repository nào dùng cho cross-request persistence.

### 15.2. Async dispatch

Với Callable/DeferredResult hoặc servlet async, context có thể được truyền bởi tích hợp framework hoặc mất khi chuyển thread tùy loại API. Những nơi cần kiểm:

- Filter chain có tham gia ASYNC dispatch như mong đợi không?
- Task được tạo bởi Spring MVC hay ExecutorService tự tạo?
- SecurityContext nào được snapshot: trước hay sau khi authentication hoàn thành?
- Ai chịu trách nhiệm clear context ở worker thread?
- Nếu request kết thúc trước task, task còn được phép hành động dưới principal cũ không?

Không sửa vấn đề async bằng cách đặt SecurityContext vào một **static ThreadLocal** không clear hoặc chuyển sang MODE_GLOBAL. Hãy dùng cơ chế propagation chính thức và test.

## 16. Những lỗi phổ biến với SecurityContextHolder

### 16.1. Lưu Authentication vào biến static

~~~java
// ANTI-PATTERN: mọi request có thể chia sẻ một biến.
static Authentication currentUser;
~~~

Một ứng dụng nhiều user dùng chung class trong JVM. Biến static không phân biệt request, nên dữ liệu người A có thể bị lộ cho B. Dùng SecurityContextHolder theo lifecycle chuẩn hoặc một request-scoped abstraction phù hợp.

### 16.2. Set Authentication trước khi kiểm credential

Nếu Controller nhận username và role trong request body rồi dùng UsernamePasswordAuthenticationToken.authenticated(...), client có thể tự tạo ROLE_ADMIN. Không tạo Authentication đáng tin từ input chưa xác minh.

### 16.3. Quên clearContext trong background worker

Thread pool tái sử dụng thread. Custom code tự set context rồi không clear trong finally có thể khiến task tiếp theo chạy với quyền người khác.

### 16.4. Sửa context được chia sẻ

SecurityContext có thể tham chiếu cùng object giữa các luồng hoặc nơi lưu khác nhau; mutating trực tiếp một context đang được chia sẻ tạo race và rò quyền. Khi cần đặt Authentication thủ công, tạo context mới và chỉ thiết lập sau khi xác thực hợp lệ.

### 16.5. Nghĩ rằng context tự được lưu vào session

SetContext trong request hiện tại và repository persistence là hai thao tác khác nhau trong Spring Security 6 với explicit-save. Đăng nhập custom có thể thành công một request nhưng request kế tiếp 401.

### 16.6. Thêm hai filter quản lý context

Cấu hình cả SecurityContextPersistenceFilter và SecurityContextHolderFilter cùng một chain có thể tạo vòng đời/ghi đè không nhất quán. Dùng cách cấu hình được Spring Security 6 hỗ trợ theo phiên bản đang triển khai.

### 16.7. Đổi MODE_GLOBAL để làm @Async nhìn thấy user

Context sẽ thành dữ liệu toàn JVM, trái mô hình multi-user Servlet. Dùng DelegatingSecurityContextRunnable/Executor hoặc principal/service identity được kiểm chứng.

### 16.8. Giả định isAuthenticated() loại trừ anonymous

AnonymousAuthenticationToken có thể báo authenticated=true. Dùng authenticated() của authorization DSL hoặc AuthenticationTrustResolver để phân biệt.

### 16.9. Cast principal luôn là UserDetails

Với JWT/OIDC/mTLS có thể không phải UserDetails. Dùng Authentication.getName() khi chỉ cần tên; thiết kế identity adapter khi cần stable userId/tenant.

### 16.10. Trả SecurityContext hoặc Authentication thẳng ra JSON

Context/Authentication có thể chứa credentials, details, session attributes, claims hoặc authorities nội bộ. Chỉ trả response DTO cần thiết; không log raw Authorization header, session cookie, password hash, token.

### 16.11. Dùng 401/403 làm bằng chứng chắc chắn lỗi holder

401 có thể do credential, entry point hoặc session persistence; 403 có thể do authority, CSRF hoặc object policy. Cần kiểm filter, authentication manager, holder, repository, authorization theo thứ tự.

### 16.12. Nhầm SecurityContextHolder với RequestContextHolder

**RequestContextHolder** của Spring Web lưu request attributes, không phải Spring Security Authentication. Lấy request context không có nghĩa đã có verified principal.

### 16.13. Quên bảo vệ service/domain sau authenticated()

Một user có Authentication hợp lệ nhưng gọi GET /orders/42 của người khác vẫn cần owner/tenant check. Context cung cấp danh tính, **không tự xác minh quyền truy cập đối tượng**.

### 16.14. Quên test session và thread leakage

Mỗi test request 200 độc lập không phát hiện việc request sau nhìn thấy user cũ. Cần test **authenticated request → anonymous request** trên cùng tiến trình và **worker task → task kế tiếp trên cùng executor**.

## 17. Quy trình debug SecurityContextHolder theo dấu vết request

Khi endpoint đọc được Authentication khác dự kiến, kiểm lần lượt:

1. **Đúng Servlet stack chưa?** Nếu server chạy WebFlux, xem Reactor Context và ReactiveSecurityContextHolder, không ép dùng ThreadLocal Servlet.
2. **SecurityFilterChain nào khớp?** Có chain dùng securityMatcher hẹp khiến request ngoài bảo vệ không?
3. **SecurityContextHolderFilter đang dùng repository nào?** HttpSession/RequestAttribute/Delegating/Null; có explicit-save không?
4. **Request có credential/session cookie gì?** Basic, Bearer, form session hoặc remember-me? Không in raw credential vào log.
5. **Authentication filter có chạy không?** Nếu không có credential, có anonymous authentication không?
6. **AuthenticationManager có thành công không?** Nếu thất bại, HTTP có 401/challenge hoặc redirect không?
7. **Trong Controller, Authentication principal/authorities là gì?** Chỉ log trường an toàn trong môi trường có kiểm soát.
8. **Nếu cùng request có nhiều thread**, context có được propagate đúng qua executor/framework integration không?
9. **Nếu request B mất login**, context có được save vào repository không? Cookie có được browser gửi lại không? Có đang cấu hình Null repository không?
10. **Nếu request B thấy sai user**, kiểm thread pool, custom context set/clear, singleton/static field và session routing.
11. **Nếu có 403 sau login**, kiểm hasRole/hasAuthority, CSRF và object-level policy; không vội gỡ authorization.
12. **Nếu lỗi chỉ xuất hiện khi ERROR/ASYNC dispatch**, xem dispatcher types, request attributes và security filter invocation.
13. **Nếu quyền cũ tồn tại sau disable/logout**, kiểm session/token revocation và source of authority, không chỉ clearContext một thread.
14. **Viết test tái hiện** cho cả request thành công, request sau không credential, worker thread và thread cleanup.

Đây là quy trình tìm nguyên nhân, không phải lời khuyên bật log raw SecurityContext ở production. Context chứa dữ liệu danh tính nhạy cảm; nếu cần logging, chỉ giữ request ID và mã nguyên nhân đã được redacted.

## 18. Kiểm thử phân biệt những tầng trách nhiệm

| Test | Lớp được kiểm | Bằng chứng nên có |
| --- | --- | --- |
| Request ẩn danh tới /api/public | URL authorization | 200 và body công khai tối thiểu. |
| Request ẩn danh tới /api/me | Authentication entry point | 401, không gọi dữ liệu bảo vệ. |
| Basic đúng tới /api/me | Authentication filter + holder + Controller | Name/authorities phù hợp principal đã xác thực. |
| Basic sai tới /api/me | AuthenticationManager + filter failure | 401, không có body dữ liệu bảo vệ. |
| Alice gọi /api/admin | Authorization, không phải xác thực mật khẩu | 403 dù authentication hợp lệ. |
| Admin gọi /api/admin | Role rule | 200 và đúng role. |
| GET /api/me với Basic rồi request khác không gửi Basic | Không lưu login trong stateless API | Request sau 401. |
| Set context trong một JUnit thread | ThreadLocal strategy | Thread hiện tại đọc được Authentication. |
| Executor mới không wrapper | Boundary của ThreadLocal | Worker không tự có Authentication. |
| DelegatingSecurityContextRunnable | Controlled propagation và cleanup | Worker đọc được principal khi chạy, task sau không bị rò. |

Nếu ứng dụng có phiên stateful, bổ sung test **form login tạo session cookie → request sau gửi cookie thành công → logout → request sau bị từ chối**. Không dùng cùng kết quả mong đợi với demo stateless vì hai mô hình có chính sách persistence khác nhau.

## 19. Câu hỏi tự kiểm tra

1. SecurityContextHolder có trực tiếp kiểm password hoặc JWT không? **Gợi ý:** không; nó quản lý quyền truy cập tới SecurityContext.
2. SecurityContext chứa đối tượng chính nào? **Gợi ý:** Authentication.
3. Vì sao createEmptyContext() được khuyến nghị khi tự gắn một Authentication? **Gợi ý:** tránh sửa context có thể đang được chia sẻ.
4. MODE_THREADLOCAL làm được gì và mất gì khi chuyển sang ExecutorService? **Gợi ý:** giữ theo thread, không tự propagate.
5. Vì sao MODE_GLOBAL nguy hiểm trong Servlet server nhiều user? **Gợi ý:** một ngữ cảnh toàn JVM.
6. Request A đăng nhập thành công nhưng request B 401. Những nguyên nhân ở repository/session/credential nào cần kiểm?
7. SecurityContextHolderFilter khác SecurityContextPersistenceFilter ở khả năng lưu context như thế nào?
8. RequestAttributeSecurityContextRepository giữ dữ liệu qua **HTTP request mới** hay qua dispatch của cùng request?
9. HttpSessionSecurityContextRepository khác NullSecurityContextRepository ở điểm nào?
10. Vì sao SecurityContextHolder.clearContext() không tương đương logout session hoặc revoke JWT?
11. Có thể dùng Authentication.isAuthenticated() một mình để xác định user thật không? **Gợi ý:** anonymous token.
12. Lấy principal bằng @AuthenticationPrincipal UserDetails có an toàn với JWT/OIDC không? **Gợi ý:** principal type khác.
13. @WithMockUser kiểm được password hash thật không? **Gợi ý:** không; nó mock Authentication.
14. Vì sao một custom Servlet login cần xét SessionAuthenticationStrategy bên cạnh saveContext?
15. Làm sao test sự rò context giữa hai task cùng thread pool?
16. Với một session còn sống sau khi tài khoản bị disable, vì sao holder không tự biết quyền phải thu hồi?
17. Nếu một app dùng WebFlux server, nên dùng cơ chế nào thay ThreadLocal holder để lấy security context? **Gợi ý:** ReactiveSecurityContextHolder/Reactor Context.
18. Controller đã thấy Authentication(alice), vậy Alice có tự đọc được đơn của Bob không? **Gợi ý:** cần object-level policy riêng.

### Checklist ghi nhớ

- **SecurityContextHolder** là điểm truy cập SecurityContext của execution hiện tại, không phải AuthenticationManager hoặc user database.
- **SecurityContext** chứa Authentication; có thể chưa có Authentication hoặc có anonymous Authentication.
- **MODE_THREADLOCAL** là mặc định Servlet; không tự truyền sang mọi executor thread.
- **Spring Security filter chain** quản lý việc thiết lập và dọn context cho request bình thường.
- Khi tự set context ở code ngoài filter, **tạo context mới và clear trong finally**.
- **SecurityContextHolderFilter** thường nạp/defer context trong Spring Security 6; **explicit save** cần thiết khi custom code muốn duy trì login giữa request.
- **SecurityContextRepository** quyết định persistence: HttpSession, RequestAttribute, Delegating hoặc Null.
- **STATELESS + NullSecurityContextRepository** không lưu Authentication cho request tiếp theo.
- **SecurityContextHolder không tự động là một session** và clearContext không tự logout/revoke token.
- **AnonymousAuthenticationToken có thể isAuthenticated=true**; dùng authorization DSL/AuthenticationTrustResolver đúng nghĩa.
- **@AuthenticationPrincipal, Authentication method argument và @CurrentSecurityContext** giúp đọc principal trong MVC.
- **DelegatingSecurityContextRunnable** giúp propagation có chủ đích và cleanup trong worker thread.
- **Đọc principal khác với cấp quyền**; role/permission/tenant/object authorization vẫn cần riêng.
- **Test HTTP và thread lifecycle**, không chỉ login 200.

## Tài liệu tham khảo

1. [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContextHolder, SecurityContext, Authentication và ThreadLocal.
2. [Spring Security — Persisting Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html): SecurityContextRepository, SecurityContextHolderFilter, SecurityContextPersistenceFilter và explicit save.
3. [Spring Security — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html): session, requireExplicitSave và nâng cấp hành vi framework.
4. [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): DelegatingSecurityContextRunnable và propagation giữa threads.
5. [Spring Security — Servlet API Integration](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html): HttpServletRequest, Principal và servlet async.
6. [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc, @WithMockUser và cơ chế tạo context trong test.
7. [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): requestMatchers, hasRole, authenticated và denyAll.

**Phiên bản:** Code lab nhắm Java 17 và Spring Boot 3.3.6 (Spring Security 6.3.x) để ví dụ API nhất quán. Khi tạo dự án mới, hãy chọn bản Spring Boot/Spring Security được hỗ trợ, kiểm Javadoc theo dependency hiện hành và chạy lại test. Các chi tiết filter mặc định, persistence và integration có thể khác khi nâng cấp.

## Kết luận

Trong mô hình xử lý **Servlet**, **SecurityContextHolder** cho phép code truy cập **SecurityContext của execution hiện tại**, nơi thường chứa Authentication đã được Spring Security xác thực. Với chiến lược mặc định **ThreadLocal**, context phù hợp xử lý trong một request nhưng **không tự trở thành dữ liệu toàn phiên** và **không tự chạy theo mọi thread khác**. Filter chain chịu trách nhiệm lifecycle; SecurityContextRepository quyết định persistence; cơ chế async cần propagation an toàn; còn authorization quyết định người dùng được truy cập resource nào. Phân biệt rành mạch các vai trò này và kiểm thử cả **request kế tiếp, thread kế tiếp, authentication lẫn authorization** là cách tránh rò danh tính, mất session và cấp quyền sai.
