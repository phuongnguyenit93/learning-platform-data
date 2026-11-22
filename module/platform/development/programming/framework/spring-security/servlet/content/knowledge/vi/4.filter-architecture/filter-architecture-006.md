# SecurityContextHolderFilter và vòng đời ngữ cảnh của một yêu cầu

> **Phạm vi:** Spring Security trên **Servlet stack**, trong ngữ cảnh kiến trúc bộ lọc. Mục tiêu là hiểu `SecurityContextHolderFilter` đưa `SecurityContext` vào luồng xử lý thế nào, ai lưu ngữ cảnh cho request sau, khi nào ngữ cảnh được xóa, và những điều kiện đặc biệt như exception, nhiều filter chain hoặc xử lý bất đồng bộ. Các ví dụ Spring bên dưới dùng API phổ biến của Spring Security 6.x / Spring Boot 3.x (Java 17+); cấu hình thực tế có thể thay đổi theo phiên bản và lựa chọn bảo mật.

## 1. Bốn khái niệm không nên đánh đồng

| Thành phần | Vai trò | Vòng đời đặc trưng |
| --- | --- | --- |
| `SecurityContext` | Chứa `Authentication` hiện tại (principal, authorities và thông tin xác thực liên quan). | Một bản context dùng trong lần thực thi; có thể được nạp lại từ nơi lưu theo cấu hình. |
| `SecurityContextHolder` | Điểm truy cập `SecurityContext` từ mã chạy trên thread hiện tại. Chiến lược mặc định của Servlet stack là `MODE_THREADLOCAL`. | Theo thread đang xử lý; phải dọn khi kết thúc phạm vi filter. |
| `SecurityContextRepository` | Nạp và, khi được gọi, lưu `SecurityContext` vào nơi được cấu hình (ví dụ request attribute hoặc HTTP session). | Có thể trải qua một dispatch hoặc nhiều HTTP request, tùy loại repository. |
| `SecurityContextHolderFilter` | Thiết lập khả năng truy cập context lấy từ repository cho phần còn lại của filter chain, rồi dọn holder. | Phạm vi một lần thực thi filter chain tương ứng với dispatch/thread. |

**Phân biệt then chốt:** việc **có context trong `SecurityContextHolder`** không tự có nghĩa context đó **đã được lưu** cho HTTP request sau. Và việc `clearContext()` lúc ra khỏi filter chain không đồng nghĩa xóa session, hủy tài khoản hay đăng xuất.

Trong ứng dụng Servlet, `DelegatingFilterProxy` thường nối hệ thống filter của container với `FilterChainProxy` của Spring Security. `FilterChainProxy` chọn một `SecurityFilterChain` phù hợp với request; bên trong chain, `SecurityContextHolderFilter` chạy trước các filter xác thực/ủy quyền phụ thuộc vào security context. Thứ tự và danh sách filter **phụ thuộc cấu hình**, không nên suy ra chỉ từ tên lớp.

## 2. Dòng thời gian của một HTTP request đồng bộ

~~~text
HTTP request -> Servlet container gán worker thread T1
  -> DelegatingFilterProxy / FilterChainProxy
     -> chọn SecurityFilterChain theo request
        -> SecurityContextHolderFilter
           (1) tạo deferred context từ SecurityContextRepository
           (2) gắn deferred context vào SecurityContextHolder cho T1
           -> authentication filters (nếu cần)
           -> authorization filters
           -> controller/service
           (3) authentication thành công có thể lưu context qua repository
           (4) kết thúc chain, clear holder trong finally
  -> T1 quay về pool, có thể nhận request khác
~~~

Có thể hiểu cơ chế chính bằng mã giả **rút gọn** sau; đây không phải phần cài đặt nguồn đầy đủ của Spring Security:

~~~java
// PSEUDOCODE: minh họa vòng đời, không phải class tự chạy.
var deferred = repository.loadDeferredContext(request);
try {
    securityContextHolderStrategy.setDeferredContext(deferred);
    chain.doFilter(request, response);
} finally {
    securityContextHolderStrategy.clearContext();
}
~~~

Những điểm cần giữ đúng khi đọc sơ đồ:

1. `loadDeferredContext(request)` cho phép **nạp trì hoãn**: filter thiết lập một nguồn cung cấp context, và việc truy cập kho lưu có thể chỉ xảy ra khi downstream thực sự cần context. Không đồng nghĩa mỗi request luôn đọc session ngay lúc vào filter.
2. Lời gọi `SecurityContextHolder.getContext()` ở downstream khiến ứng dụng lấy context khả dụng cho thread hiện tại; nếu repository không có context đã lưu, cơ chế có thể cung cấp context trống ban đầu.
3. Các filter xác thực có thể đặt một `Authentication` thành công vào context mới. Các filter cấp quyền sau đó dựa trên authentication/context để kiểm tra quyền.
4. **`SecurityContextHolderFilter` không tự gọi `saveContext(...)` khi request kết thúc**. Với chế độ lưu tường minh, thành phần thực hiện thay đổi cần chịu trách nhiệm lưu khi muốn giữ authentication cho lần sau.
5. `finally` bảo đảm dọn holder khi phần filter chain phía dưới kết thúc hoặc ném exception. Context lưu trong repository (nếu đã lưu) vẫn còn theo chính sách của repository.

Sơ đồ chỉ mô tả **phạm vi thực thi đồng bộ**. Một HTTP request có thể tiếp tục qua async dispatch hoặc thread khác, nên không được coi một request luôn gắn cố định với một T1.

## 3. Nạp trì hoãn (`DeferredSecurityContext`) là gì?

`SecurityContextRepository` hỗ trợ `loadDeferredContext(HttpServletRequest)` để lấy một đối tượng `DeferredSecurityContext`. Nó cung cấp khả năng truy cập context khi cần; Spring Security có thể dùng `Supplier<SecurityContext>` của nó để tích hợp với `SecurityContextHolderStrategy.setDeferredContext(...)`.

So sánh hai tình huống:

- **Request không cần quyền hoặc principal:** filter vẫn thiết lập nguồn context, nhưng không nhất thiết phải tải dữ liệu xác thực từ session nếu không ai cần truy cập nó.
- **Request truy cập endpoint được bảo vệ:** filter authorization hoặc mã khác cần `Authentication`; context được truy xuất từ repository phù hợp, hoặc được tạo mới nếu chưa có bản lưu.

“Deferred” là **thời điểm truy cập dữ liệu**, không phải phép truyền context xuyên thread và cũng không phải cơ chế duy trì login. Sau khi một context được nạp hoặc tạo, những thay đổi của context vẫn cần được lưu theo chính sách explicit-save nếu muốn chúng tồn tại bên ngoài phạm vi hiện tại.

Nếu thấy `SecurityContextHolder.getContext().getAuthentication()` trả `null`, có thể chưa có xác thực. Nếu thấy một `AnonymousAuthenticationToken`, đó vẫn không phải người dùng đã đăng nhập. Đừng viết logic bảo mật chỉ dựa trên điều kiện “Authentication khác null”; hãy dùng authorization rules của Spring Security.

## 4. Phân biệt hai filter liên quan: Holder và Persistence

| Câu hỏi | `SecurityContextHolderFilter` | `SecurityContextPersistenceFilter` |
| --- | --- | --- |
| Đưa context tới phần còn lại của filter chain? | Có, qua cơ chế deferred context và holder. | Có, theo cách nạp context của filter đời trước. |
| Dọn holder khi phần việc của chain hoàn tất? | Có. | Có. |
| Tự lưu context khi chain kết thúc? | **Không**; yêu cầu lưu tường minh khi cần. | Có cơ chế lưu tự động ở cuối request/response trong mô hình cấu hình tương ứng. |
| Khi nào thường thấy? | Phổ biến trong cấu hình Spring Security hiện đại với `requireExplicitSave(true)`. | Một số cấu hình/phiên bản tương thích theo mô hình tự lưu, chẳng hạn chọn `requireExplicitSave(false)` nơi API còn hỗ trợ. |

Không tự chèn cả hai vào chain để “chắc chắn”; hãy cấu hình dựa trên phiên bản và hành vi mong muốn, rồi kiểm tra filter chain thực tế.

**Lý do explicit-save quan trọng:** kết thúc request không phải thời điểm đáng tin cậy duy nhất để xác định cần lưu context. Response có thể đã commit, có thể có async, hoặc nhiều tác vụ ghi ngữ cảnh không mong muốn. Với `SecurityContextHolderFilter`, quyết định **khi nào lưu** được đưa về nơi xử lý sự kiện xác thực/thay đổi context. Điều này làm rõ trách nhiệm và tránh dựa vào cơ chế ghi tự động khó quan sát.

## 5. Ai chịu trách nhiệm lưu `SecurityContext`?

Hãy phân biệt ba hành động:

1. **Đọc:** `SecurityContextHolder.getContext()` lấy context đang gắn với thread, có thể gây nạp deferred context.
2. **Thiết lập:** `SecurityContextHolder.setContext(context)` thay context của thread hiện tại.
3. **Lưu bền trong phạm vi repository:** `securityContextRepository.saveContext(context, request, response)` làm repository cập nhật nơi lưu theo chính sách.

Ví dụ **mảnh mã trong filter xác thực tùy chỉnh**, sau khi đã xác minh thông tin đăng nhập qua `AuthenticationManager`:

~~~java
Authentication authentication = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(username, password)
);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);

// Quan trọng: dùng đúng repository của security filter chain.
securityContextRepository.saveContext(context, request, response);
~~~

Mảnh mã cần Spring Security 6+ với các import `Authentication`, `AuthenticationManager`, `UsernamePasswordAuthenticationToken`, `SecurityContext`, `SecurityContextHolder`, `SecurityContextRepository`, các đối tượng `request`/`response`, và biến `username`/`password` đã được lấy từ request bằng quy trình an toàn. Nó **không phải chương trình Java SE độc lập** hoặc một filter đăng nhập hoàn chỉnh: filter thực tế còn phải xử lý xác thực thất bại, CSRF, session fixation, success/failure handler và không được ghi log password.

- Tạo context bằng `createEmptyContext()` rồi đặt `Authentication` vào đó giúp tránh vô tình chỉnh sửa một context được dùng lại ở nơi khác.
- Gọi `saveContext` **trước khi response bị commit** khi việc lưu đòi hỏi session/cookie. Nếu không lưu, authentication có thể vẫn khả dụng ở request hiện tại nhưng request kế tiếp trở về trạng thái chưa xác thực.
- Một số cơ chế xác thực **có sẵn** của Spring Security (ví dụ form login được cấu hình chuẩn) đã tích hợp việc lưu context phù hợp. Không tự gọi thêm `saveContext` ở controller một cách tràn lan.
- Khi security được cấu hình **stateless**, context của token/basic authentication thường được tạo lại hoặc xác thực mỗi request; không có nghĩa ứng dụng phải tạo HTTP session để “sửa” việc không lưu.

**Nguyên tắc:** `SecurityContextHolderFilter` quản lý **scope truy cập và cleanup**; thành phần xác thực chịu trách nhiệm **thiết lập authentication**, còn repository và cơ chế xác thực quyết định **lưu hay không lưu**.

### Cấu hình minh họa dùng Spring Boot 3 / Spring Security 6

Trong dự án Spring Boot có `spring-boot-starter-web` và `spring-boot-starter-security`, tạo `SecurityConfig.java` trong package được component scan:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .securityContext(c -> c.requireExplicitSave(true))
            .authorizeHttpRequests(a -> a
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đoạn này là **lớp cấu hình trong ứng dụng Spring**, không chạy riêng bằng `javac` nếu không có classpath Spring. `requireExplicitSave(true)` thể hiện rõ chính sách, và `formLogin` do Spring Security cung cấp thực hiện các bước xác thực/lưu context thích hợp. Đường dẫn `/public` chỉ là ví dụ; ứng dụng cần có endpoint tương ứng nếu muốn truy cập nó. Khi thay đổi cấu hình security, phải kiểm tra các chain khác cũng như phiên bản Spring Security thực tế.

## 6. `SecurityContextRepository` quyết định dữ liệu tồn tại bao lâu

| Repository | Phạm vi dữ liệu | Khi nên nghĩ tới |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Có thể giữ context giữa những HTTP request dùng cùng session hợp lệ, theo chính sách tạo/sử dụng session. | Ứng dụng stateful dùng session, chẳng hạn login qua form. |
| `RequestAttributeSecurityContextRepository` | Giữ context qua các dispatch của **cùng request** khi request attribute còn tồn tại; hữu ích cho error dispatch. | Khi cần context qua một số nhịp dispatch của cùng yêu cầu, không phải session dài hạn. |
| `NullSecurityContextRepository` | Không lưu context để tái nạp giữa request. | Endpoint stateless hoặc mô hình xác thực từng request. |
| `DelegatingSecurityContextRepository` | Kết hợp nhiều repository; hành vi load/save theo các delegate được cấu hình. | Cấu hình Servlet phổ biến muốn kết hợp request attribute và session. |

Một số cấu hình Spring Security 6 dùng `DelegatingSecurityContextRepository` kết hợp request attribute và session; đừng mặc định mọi ứng dụng đều dùng tổ hợp này. Việc có session và nội dung của session phụ thuộc `SessionCreationPolicy`, repository thực tế, cách xác thực và thiết lập security.

### Ba request giúp phân biệt holder với session

~~~text
Request A (session S)
  filter nạp context: chưa có authentication
  người dùng đăng nhập thành công: Authentication = alice
  authentication flow lưu context qua repository
  filter kết thúc: clear context trên thread T1

Request B (cũng session S)
  filter có thể nạp lại context của alice từ repository
  authorization đọc Authentication = alice
  filter kết thúc: clear context trên thread đang dùng

Request C (session khác hoặc stateless không có credentials)
  không được kế thừa Authentication của A hoặc B
  có thể thấy context trống/anonymous tùy filter chain
~~~

**Vòng đời holder theo thread** và **vòng đời context lưu ở repository** là hai điều khác nhau. `clearContext()` ngăn dữ liệu của A còn dính lên worker thread phục vụ C; nó không xóa context đã lưu có chủ đích trong session S. Ngược lại, nếu không lưu ở A mà vẫn chỉ nhìn thấy authentication trong A, việc B không đăng nhập được là hành vi có thể dự đoán.

## 7. Thí nghiệm Java 17 có thể chạy: load, save và clear

Ví dụ dưới đây sử dụng Java SE để **mô phỏng** quan hệ giữa kho lưu, thread-local holder và cleanup trên cùng một worker thread. Đây **không phải cài đặt của Spring Security**: ví dụ chủ động nạp **eagerly**, còn `SecurityContextHolderFilter` có hỗ trợ deferred loading; repository thực là HTTP/session-aware chứ không phải `ConcurrentHashMap`.

Tạo tệp `ContextLifecycleDemo.java`:

~~~java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ContextLifecycleDemo {
    private static final Map<String, String> STORED = new ConcurrentHashMap<>();
    private static final ThreadLocal<String> HOLDER = new ThreadLocal<>();

    private static void request(String name, String session, Runnable chain) {
        String saved = STORED.get(session);
        if (saved == null) {
            HOLDER.remove();
        } else {
            HOLDER.set(saved);
        }

        try {
            System.out.println(name + " loaded: " + HOLDER.get());
            chain.run();
        } finally {
            HOLDER.remove();
            System.out.println(name + " cleared: " + HOLDER.get());
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            worker.submit(() -> request("R1", "S1", () -> {
                HOLDER.set("alice");
                STORED.put("S1", HOLDER.get()); // Lưu tường minh.
                System.out.println("R1 saved: " + STORED.get("S1"));
            })).get();

            worker.submit(() -> request("R2", "S1", () ->
                System.out.println("R2 sees: " + HOLDER.get())
            )).get();

            worker.submit(() -> request("R3", "S2", () ->
                System.out.println("R3 sees: " + HOLDER.get())
            )).get();
        } finally {
            worker.shutdown();
        }
    }
}
~~~

Chạy trên JDK 17 trở lên:

~~~bash
javac ContextLifecycleDemo.java
java ContextLifecycleDemo
~~~

Kết quả chính xác:

~~~text
R1 loaded: null
R1 saved: alice
R1 cleared: null
R2 loaded: alice
R2 sees: alice
R2 cleared: null
R3 loaded: null
R3 sees: null
R3 cleared: null
~~~

Ba task chạy tuần tự trên cùng worker do `newSingleThreadExecutor()` và `Future.get()`. R1 thiết lập và **lưu** “alice” cho S1; R2 có cùng session S1 nên nạp lại được; R3 có S2 nên không có giá trị đó. Cả ba đều gọi `remove()` trong `finally`, bảo đảm thread tái sử dụng không giữ dữ liệu từ request trước. Nếu bỏ `STORED.put(...)`, R2 cũng sẽ thấy `null` dù R1 đã từng gắn “alice” trong holder.

Đừng dùng ví dụ này như cách cài xác thực: chuỗi “alice” không phải `Authentication` đã xác minh và map dùng chung không thể thay session manager. Mục đích là chứng minh **lưu và clear là hai hành động độc lập**.

## 8. Exception, error dispatch và xử lý bất đồng bộ

### Exception trong filter chain

~~~text
SecurityContextHolderFilter -> authentication/authorization/controller
                           -> exception
                           -> unwind filter stack
                           -> finally: clearContext() trên thread đang chạy
~~~

Khi downstream ném exception, `finally` của `SecurityContextHolderFilter` vẫn dọn security context mà nó đã gắn trong phạm vi thực thi. Ngoại lệ có thể được `ExceptionTranslationFilter` hoặc exception handler khác chuyển thành response; điều đó không thay thế trách nhiệm cleanup. Nếu code tự tạo `ThreadLocal` hoặc tự set context trong task ngoài chain, nó phải có cleanup của **chính nó**.

### ERROR và ASYNC dispatch

Một HTTP request có thể trải qua nhiều dispatch trên các thread khác nhau. `RequestAttributeSecurityContextRepository` giúp giữ context ở phạm vi request trong một số trường hợp như ERROR dispatch; nhưng việc filter chạy trên dispatch nào còn phụ thuộc Servlet dispatcher types, đăng ký filter và cấu hình.

Ở xử lý async:
- Thread T1 có thể thoát khỏi lần xử lý request đầu tiên, được trả lại pool trong khi response chưa hoàn tất.
- Thread T2 xử lý `Callable`, `CompletableFuture`, `@Async` hoặc callback; nó **không mặc nhiên** nhìn thấy `SecurityContextHolder` của T1.
- Spring Security hỗ trợ tích hợp với Spring MVC `Callable` thông qua `WebAsyncManagerIntegrationFilter` khi filter chain tương ứng được áp dụng. Không suy ra hỗ trợ tự động cho mọi executor/task khác.
- Khi tự quản lý task, cân nhắc truyền dữ liệu nhận dạng tối thiểu qua tham số hoặc sử dụng `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService` (hoặc wrapper executor phù hợp), với context được capture/clear đúng phạm vi.
- Dùng `MODE_INHERITABLETHREADLOCAL` không giải quyết việc chuyển context giữa các task trong thread pool đã tạo sẵn.

**Không giữ context trên T1 tới lúc async hoàn tất**: T1 có thể đã nhận request của người khác. Nếu công việc nền chạy rất lâu, còn phải xét khả năng danh tính/quyền đã thay đổi giữa thời điểm submit và thực thi. Việc copy context không tự cấp quyền truy cập tài nguyên.

## 9. Tương tác với authentication, authorization, logout

Một chuỗi xử lý có thể gồm các thành phần có vai trò khác nhau:

- `SecurityContextHolderFilter`: chuẩn bị nơi lấy security context và dọn holder khi ra khỏi chain.
- Authentication filters như form login hoặc bearer token authentication: **xác minh credentials/token** qua cơ chế tương ứng và thiết lập `Authentication` thích hợp.
- `AnonymousAuthenticationFilter`: có thể đặt anonymous authentication nếu chưa có authenticated principal phù hợp.
- `AuthorizationFilter` / authorization managers: kiểm tra quyền truy cập tài nguyên dựa trên context/authorization policy.
- Logout handler: có thể vô hiệu hóa session, xóa context và thực hiện thao tác xóa liên quan tới repository theo cấu hình.

Các việc trên không nên được gộp vào một filter tùy chỉnh chỉ vì đã có `SecurityContextHolder`. Dọn thread-local khi kết thúc request **không phải** logout, và tự gọi `clearContext()` trong controller khi muốn logout **không đảm bảo** xóa ngữ cảnh được lưu ở HTTP session. Hãy dùng cơ chế logout của Spring Security.

Nếu có nhiều `SecurityFilterChain` (ví dụ `/api/**` stateless và phần web stateful), từng chain có thể có các filter/repository khác nhau. Hãy kiểm tra **chain nào thực sự match request** trước khi kết luận `saveContext` hoặc session behavior đang sai. Một request có thể không match Spring Security chain nào hoặc match chain khác với chain bạn đang đọc cấu hình.

## 10. Các lỗi phổ biến và cách chẩn đoán

| Hiện tượng | Điều có thể xảy ra | Kiểm tra/cách xử lý |
| --- | --- | --- |
| Đăng nhập thành công trong cùng request nhưng request kế tiếp lại là anonymous | Custom authentication đã `setContext` mà không `saveContext` trong explicit-save mode; session/cookie không duy trì; hoặc repository không lưu. | Xác nhận cơ chế login, repository và cookie/session; gọi `saveContext` tại nơi có trách nhiệm nếu là auth tùy chỉnh. |
| Dữ liệu người dùng A xuất hiện trong request của B | Custom thread-local không được dọn, tự sửa holder ngoài lifecycle chuẩn, hoặc dùng `MODE_GLOBAL`/inheritance không đúng. | Kiểm tra bind/clear trong `finally`, thread pool, cấu hình strategy; không chia sẻ context xuyên user. |
| `SecurityContextHolder.getContext()` trống trong `@Async`/`CompletableFuture` | Task chạy thread khác, chưa có context propagation. | Truyền tham số hoặc wrapper executor có chính sách capture và cleanup rõ. |
| Ở ERROR dispatch không đọc được authentication | Phân phối dispatch/chain hoặc repository chỉ có context theo thread, thiếu lưu theo request. | Kiểm tra dispatcher types và `RequestAttributeSecurityContextRepository` nếu đúng nhu cầu. |
| Đã gọi `clearContext()` mà request kế tiếp vẫn đăng nhập | Session repository vẫn giữ context có chủ đích. | Phân biệt cleanup thread và logout; dùng logout handler thích hợp. |
| Repository có session nhưng không lưu như mong đợi | Cấu hình stateless/`NullSecurityContextRepository`, response commit quá sớm, explicit-save bỏ sót, hoặc dùng repo khác với chain. | Xác minh repository thực, thời điểm save, session policy và response flow. |
| Filter chỉ chạy một số endpoint | `SecurityFilterChain` có request matcher và thứ tự chain khác nhau. | Kiểm tra matcher và thứ tự chain được chọn; không chỉ nhìn vào một `SecurityFilterChain`. |
| Test bằng một request luôn xanh nhưng tải cao bị lỗi | Thread pool tái sử dụng và async làm lộ context còn sót hoặc thiếu propagation. | Test tuần tự nhiều user cùng worker, exception path và async path. |

Không kết luận “`SecurityContextHolderFilter` bị lỗi” chỉ vì authentication trống: có thể request là anonymous, chain chưa chạy filter xác thực, token không hợp lệ, repo stateless, hoặc task đang ở thread khác.

## 11. Quy trình kiểm chứng thực tế

1. **Đọc cấu hình chain:** xác định matcher, thứ tự filter, `securityContext()`, `requireExplicitSave(...)`, `SessionCreationPolicy` và repository thật. Đặc biệt khi web và API có nhiều chain.
2. **Theo dõi một lần đăng nhập:** tại điểm authentication thành công, kiểm tra context mới có `Authentication` đúng; xác định chỗ lưu qua repository và thời điểm trước commit response.
3. **Gửi request kế tiếp cùng session:** kiểm tra client gửi lại đúng cookie/session, context được nạp, và authorization hoạt động theo principal mong đợi.
4. **Gửi request không cùng session:** bảo đảm không kế thừa principal của request trước dù container tái sử dụng cùng thread.
5. **Gây exception:** kiểm tra holder đã được dọn ở ranh giới filter chain; đừng log password, access token hoặc toàn bộ security context.
6. **Thử async/error:** kiểm tra `Callable`, task executor tự tạo, error dispatch và nested dispatch; đánh giá riêng context propagation và cleanup theo thread.
7. **Kiểm thử logout:** phân biệt context trong holder hiện tại với context đã lưu trong repository/session; xác nhận phiên sau logout không còn quyền cũ.

Khi debug local, có thể bật logging ở mức phù hợp cho `FilterChainProxy` và các filter bảo mật để biết chain được chọn và thứ tự filter. Tắt logging chi tiết trước môi trường production, đồng thời chỉ log request ID/loại authentication cần thiết, không log secrets.

### Câu hỏi tự kiểm tra

**1. Tại sao `SecurityContextHolderFilter` vẫn có thể lấy lại login sau khi đã `clearContext()`?** Vì `clearContext()` dọn dữ liệu gắn với thread; context đã được lưu trong `SecurityContextRepository` có thể được nạp lại cho request tiếp theo.

**2. Nếu dùng `setContext(context)` nhưng không `saveContext(...)` thì điều gì xảy ra?** Downstream trong lần xử lý hiện tại có thể thấy context mới; với explicit-save, repository không được cập nhật chỉ vì filter kết thúc, nên request sau có thể không thấy authentication đó.

**3. Vì sao deferred loading không phải context propagation?** Deferred loading quyết định khi nào truy xuất repository trên thread hiện tại; propagation là cách mang context/dữ liệu sang thread hoặc task khác.

**4. Có nên tự thêm `SecurityContextPersistenceFilter` sau `SecurityContextHolderFilter` để tự lưu?** Không. Chọn mô hình lưu theo phiên bản/cấu hình; thêm filter tùy ý có thể gây vòng đời chồng chéo.

**5. Stateless có nghĩa là không có `SecurityContextHolder`?** Không. Request hiện tại vẫn cần security context để authorization; stateless chỉ nói rằng không phụ thuộc vào lưu session/authentication qua các request theo chính sách cấu hình.

**Ghi nhớ:** `SecurityContextHolderFilter` **nạp theo nhu cầu → cho downstream sử dụng → dọn holder**. Khi muốn authentication có mặt ở request sau, phải hiểu **ai lưu context, lưu vào đâu, vào thời điểm nào**. Đây là ranh giới cốt lõi giữa vòng đời của một thread, một HTTP request và một phiên người dùng.
