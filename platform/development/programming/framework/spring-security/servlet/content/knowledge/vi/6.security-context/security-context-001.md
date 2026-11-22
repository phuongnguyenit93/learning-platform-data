# SecurityContextHolder, SecurityContext và Authentication liên hệ thế nào

Trong **Spring Security cho ứng dụng Servlet**, ba khái niệm `SecurityContextHolder`, `SecurityContext` và `Authentication` liên kết với nhau để trả lời câu hỏi: **trong lần thực thi hiện tại, Spring Security biết gì về người gọi?**

- **`Authentication`** biểu diễn thông tin về chủ thể và trạng thái xác thực: ai đang được nhận diện, authority nào được gán, thông tin xác thực liên quan là gì.
- **`SecurityContext`** là vùng chứa `Authentication` hiện tại, được các thành phần bảo mật chia sẻ trong phạm vi thực thi phù hợp.
- **`SecurityContextHolder`** là điểm truy cập tĩnh (facade) tới `SecurityContext` thông qua một `SecurityContextHolderStrategy`; trong ứng dụng Servlet thông thường, chiến lược mặc định gắn context với **thread hiện tại**.

Ba thành phần tạo thành quan hệ:

~~~text
Code chạy trong request / filter / controller
                |
                v
SecurityContextHolder.getContext()
                |
                v
         SecurityContext
                |
                v
       getAuthentication()
                |
                v
          Authentication
          |   |        |
       principal  authorities  authenticated / credentials / details
~~~

Đây là mô hình **ngữ cảnh bảo mật đang được sử dụng**, không có nghĩa mọi request đều đã đăng nhập hoặc dữ liệu context tồn tại vĩnh viễn. Bài học sẽ đi từ cấu trúc đối tượng đến vòng đời request, bảo mật luồng, session, các API thực tế và kiểm thử.

## 1. Phân biệt nhiệm vụ của từng thành phần

| Thành phần | Đại diện cho cái gì? | API tiêu biểu | Những điều KHÔNG nên suy diễn |
| --- | --- | --- | --- |
| `SecurityContextHolder` | Cách mã ứng dụng truy cập ngữ cảnh bảo mật gắn với chiến lược lưu trữ hiện tại | `getContext()`, `setContext(...)`, `clearContext()`, `createEmptyContext()` | Không mặc định là một biến toàn cục dùng chung cho mọi người dùng |
| `SecurityContext` | Đối tượng giữ `Authentication` hiện tại | `getAuthentication()`, `setAuthentication(...)` | Không tự xác minh mật khẩu, không tự phân quyền |
| `Authentication` | Thông tin chủ thể cùng authorities và trạng thái xác thực | `getPrincipal()`, `getCredentials()`, `getAuthorities()`, `isAuthenticated()` | Một cờ `isAuthenticated()` không đủ để kết luận đây là người dùng thật, fully authenticated |
| `SecurityContextRepository` | Đọc/ghi context tại một kho lưu trữ giữa các lần xử lý nếu được cấu hình | `loadDeferredContext(...)`, `saveContext(...)` | Không đồng nghĩa với `SecurityContextHolder`, và không phải ứng dụng nào cũng lưu vào session |
| `AuthenticationManager` / `AuthenticationProvider` | Kiểm tra chứng cứ xác thực và tạo/kết quả xác thực hợp lệ | `authenticate(...)` | Không phải đối tượng lưu context cho từng thread |

Một hình dung đơn giản: `SecurityContextHolder` là **cách tìm đúng hộp hiện tại**; `SecurityContext` là **cái hộp**; `Authentication` là **thông tin được đặt trong hộp**. Còn `SecurityContextRepository` có thể **lưu và nạp lại** hộp giữa các HTTP request nếu ứng dụng theo mô hình stateful.

### Truy xuất theo API

Trong một đoạn mã đang được xử lý bởi Spring Security:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
Authentication authentication = context.getAuthentication();
~~~

Các import cần thiết:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
~~~

Đây là **đoạn mã của ứng dụng có dependency Spring Security**, không phải chương trình Java độc lập chạy bằng `javac`. `getContext()` thường cung cấp một context đang có hoặc context rỗng; nhưng `getAuthentication()` có thể là `null` khi chưa có authentication. Đừng gọi ngay `authentication.getName()` trước khi kiểm tra trường hợp rỗng.

## 2. Authentication giữ những thông tin nào?

`Authentication` kế thừa `Principal` trong Java và mở rộng bằng các đặc điểm phục vụ security. Những API quan trọng:

| API | Nội dung | Ví dụ / lưu ý |
| --- | --- | --- |
| `getPrincipal()` | Chủ thể được xác định hoặc đối tượng mô tả danh tính | Có thể là `UserDetails`, `Jwt`, một `String`, hoặc kiểu principal riêng |
| `getName()` | Tên đại diện cho principal dưới dạng chuỗi | Thường là username; không mặc định là ID duy nhất của hệ thống |
| `getCredentials()` | Dữ liệu được dùng để xác thực | Có thể là password/token và thường được xóa sau xác thực; tuyệt đối không log |
| `getAuthorities()` | Tập `GrantedAuthority` phục vụ quyết định truy cập | Chẳng hạn `ROLE_USER`, `ROLE_ADMIN` hoặc scope/permission |
| `getDetails()` | Chi tiết bổ sung do cơ chế authentication cung cấp | Có thể là metadata của web request; không nên coi mọi trường là đã được kiểm chứng |
| `isAuthenticated()` | Trạng thái xác thực của object theo cơ chế đã tạo nó | Không nhất thiết tương đương “người dùng đã login bằng tài khoản đầy đủ” |

Ví dụ sau khi đăng nhập bằng username/password, một `UsernamePasswordAuthenticationToken` hợp lệ có thể mang principal là `UserDetails`, authorities là `ROLE_USER` và trạng thái `isAuthenticated()=true`. Với JWT Resource Server, kiểu object và principal có thể khác; ứng dụng không nên ép `getPrincipal()` thành `UserDetails` cho mọi cơ chế.

### Authentication vừa là yêu cầu, vừa có thể là kết quả

Trong luồng xác thực, cùng abstraction `Authentication` có thể được dùng ở hai giai đoạn:

~~~text
Client gửi credentials
      |
      v
Authentication chưa được xác thực
(ví dụ UsernamePasswordAuthenticationToken.unauthenticated)
      |
      v
AuthenticationManager / AuthenticationProvider
      | xác minh credentials, tài khoản, chính sách
      v
Authentication đã được xác thực
(có principal và authorities tin cậy)
      |
      v
SecurityContext.setAuthentication(...)
      |
      v
SecurityContextHolder.setContext(...)
~~~

Khi chưa được kiểm tra, `Authentication` có thể mang username/password để nhà cung cấp xác thực xác minh. Sau khi xác minh thành công, `AuthenticationManager.authenticate(...)` trả một `Authentication` được xác thực; object này thường chứa các authorities cuối cùng.

**Không tạo token đã xác thực chỉ từ dữ liệu người dùng gửi lên.** Ví dụ gọi `UsernamePasswordAuthenticationToken.authenticated("alice", null, authorities)` với username do client nhập rồi đặt vào context sẽ khiến ứng dụng tự tin vào danh tính chưa hề được kiểm chứng. Phải dùng cơ chế authentication đáng tin cậy để xác minh trước.

### AnonymousAuthenticationToken có thể vẫn trả isAuthenticated() = true

Spring Security thường có `AnonymousAuthenticationFilter`, tạo một `AnonymousAuthenticationToken` khi chưa có authentication hợp lệ. Với object anonymous tiêu chuẩn, `isAuthenticated()` có thể là `true`, vì đây là thuộc tính kỹ thuật của token, **không có nghĩa có người dùng thật đã đăng nhập**.

Do đó, kiểm tra kiểu:

~~~java
if (authentication != null && authentication.isAuthenticated()) {
    // Không đủ điều kiện để kết luận đây là tài khoản đã đăng nhập.
}
~~~

là quá đơn giản. Đối với phân quyền, hãy ưu tiên DSL/`AuthorizationManager` của Spring Security, ví dụ `authenticated()`, `fullyAuthenticated()`, `hasRole(...)`. Framework dùng các cơ chế như `AuthenticationTrustResolver` để phân biệt anonymous và remember-me. Đối với hiển thị tên người dùng, cần loại trừ anonymous hoặc dùng cơ chế lấy principal phù hợp.

## 3. SecurityContext có gì, và vì sao phải tạo context mới?

Interface `SecurityContext` về cốt lõi cho phép **đọc/đặt `Authentication`**:

~~~java
Authentication authentication = context.getAuthentication();
context.setAuthentication(authentication);
~~~

Một ứng dụng thông thường không cần tự đặt authentication: các filter và provider của Spring Security thực hiện theo luồng xác thực. Nếu phát triển **cơ chế đăng nhập riêng đã được thiết kế đầy đủ**, sau khi `AuthenticationManager` trả kết quả tin cậy, mẫu an toàn là tạo context trống mới và đặt vào holder:

~~~java
// Minh họa một bước SAU KHI AuthenticationManager xác minh thành công:
Authentication result = authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
                submittedUsername, submittedPassword));

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(result);
SecurityContextHolder.setContext(context);

// Nếu là login stateful cần lưu qua các request, cơ chế đăng nhập
// có thể cần gọi securityContextRepository.saveContext(
//         context, request, response) theo cấu hình.
~~~

Đoạn này **không phải một endpoint đăng nhập hoàn chỉnh**: các biến `authenticationManager`, `submittedUsername`, `submittedPassword`, `request`, `response` và `securityContextRepository` do ứng dụng cung cấp; cần thêm imports của `UsernamePasswordAuthenticationToken` và cơ chế xử lý lỗi/login phù hợp. Đừng tự sao chép đoạn mã như một phương thức public nhận credentials rồi bỏ qua validation, session fixation, CSRF hoặc rate limiting.

Tạo context mới với `createEmptyContext()` hữu ích vì object context là mutable. Sửa một context đã bị dùng chung ngoài ý muốn có thể ảnh hưởng các đoạn code hoặc thread khác đang giữ tham chiếu đến cùng object. Việc sử dụng context mới cho authentication vừa được tạo giúp giảm lỗi chia sẻ trạng thái.

Sau khi đã thiết lập context, phần mã cùng execution context có thể đọc `Authentication` qua holder. Tuy nhiên, đặt vào `SecurityContextHolder` **chỉ bảo đảm việc truy cập theo phạm vi lưu trữ hiện tại**; không tự động lưu lại cho HTTP request sau.

## 4. Vòng đời ngữ cảnh trong một Servlet request

Xem một request `GET /me` trong ứng dụng Spring Boot 3.x / Spring Security 6.x, có một `SecurityFilterChain` thông thường:

~~~text
(1) HTTP request đến container
         |
         v
(2) DelegatingFilterProxy -> FilterChainProxy
         |
         v
(3) SecurityContextHolderFilter hoặc cơ chế tương ứng
         |-- dùng SecurityContextRepository để lấy context
         |-- gắn/làm sẵn context cho thread/request hiện tại
         v
(4) Authentication filters (nếu có dữ liệu xác thực)
         |-- xác minh và có thể cập nhật SecurityContext
         v
(5) AuthorizationFilter
         |-- đọc Authentication / context theo cơ chế bảo mật
         |-- cho phép hoặc từ chối
         v
(6) Controller / Service
         |-- đọc SecurityContextHolder khi cần
         v
(7) Kết thúc request
         |-- có thể lưu SecurityContext nếu chiến lược yêu cầu
         |-- clear SecurityContextHolder để tránh rò giữa request
         v
    Container tái sử dụng thread an toàn hơn
~~~

Các chi tiết thay đổi theo cấu hình và phiên bản; không phải request nào cũng đi qua mọi loại authentication filter. Trong những cấu hình Spring Security 6.x dùng `SecurityContextHolderFilter`, việc nạp context có thể được trì hoãn đến lúc cần, theo `SecurityContextRepository`. **`SecurityContextHolderFilter` không tự động lưu mọi thay đổi trở lại repository**; nếu xây cơ chế xác thực riêng có persistence, phải nắm hợp đồng lưu context rõ ràng.

### Vì sao phải clear holder?

Servlet container thường dùng **thread pool**. Thread từng phục vụ người dùng A có thể được dùng lại cho request của B. Nếu không xóa security context đúng lúc, dữ liệu `Authentication` của A có nguy cơ tồn tại sai trong lần chạy tiếp theo.

Spring Security filter xử lý vòng đời holder và cleanup (thường trong `finally`). Nếu mã ứng dụng tự thiết lập holder khi chạy ngoài chuỗi filter thông thường, phải bảo đảm cleanup bằng `try/finally` hoặc abstraction được Spring Security cung cấp.

**Không tự đặt `SecurityContextHolder.clearContext()` giữa request trong controller** chỉ vì đã đọc xong user; thao tác đó có thể làm các thành phần tiếp theo không còn thấy authentication. Việc clear tùy tiện không thay thế logout hoặc cơ chế vô hiệu hóa session/token.

## 5. Context hiện tại khác với việc lưu context giữa các request

Hãy phân biệt rõ ba phạm vi:

1. **Trong thread đang xử lý:** `SecurityContextHolder` cho truy cập context hiện tại; chiến lược phổ biến là `MODE_THREADLOCAL`.
2. **Trong vòng đời của một HTTP request:** security filter thiết lập/khôi phục context khi request bắt đầu và dọn dẹp khi kết thúc.
3. **Giữa nhiều HTTP request:** nếu cần trạng thái đăng nhập stateful, `SecurityContextRepository` có thể nạp/lưu context vào session hoặc một vị trí đã chọn. Nếu ứng dụng stateless, mỗi request thường được xác thực độc lập.

Các repository thường gặp:

| Repository | Đặc tính | Khi thường dùng |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Lưu/nạp context qua `HttpSession` khi phù hợp cấu hình | Đăng nhập dựa trên session, form login |
| `RequestAttributeSecurityContextRepository` | Lưu context trong request attributes, hữu ích cho một số dispatch trong cùng request | Duy trì context giữa các servlet dispatch liên quan |
| `DelegatingSecurityContextRepository` | Ủy quyền cho nhiều repository, có thể kết hợp request attribute và session | Cấu hình hỗ trợ nhiều phạm vi |
| `NullSecurityContextRepository` | Không giữ context để nạp lại từ repository | Mô hình stateless phù hợp, request xác thực lại độc lập |

Không nên nghĩ cứ gọi `SecurityContextHolder.setContext(context)` thì sau đó session đã chứa user. **Lưu vào holder và lưu vào repository là hai hành động khác nhau.**

### SecurityContextHolderFilter và SecurityContextPersistenceFilter

Hai tên API dễ gây nhầm:

- `SecurityContextHolderFilter`: đưa context từ `SecurityContextRepository` đến holder (có thể dùng deferred loading), dọn dẹp holder khi request xong; việc **saveContext rõ ràng** thuộc trách nhiệm của authentication mechanism hoặc code đã thiết kế cho mục đích ấy.
- `SecurityContextPersistenceFilter`: cơ chế trong các cấu hình/phiên bản cũ hơn, vốn gắn với việc lưu context ở cuối quá trình xử lý theo mô hình tương ứng.

Khi nâng cấp Spring Security, xem chính xác phiên bản và cách security context được lưu. Không suy luận rằng mọi authentication đều tự được ghi lại session, cũng không tự gọi `saveContext(...)` ở mọi controller. Các authentication filter tích hợp của Spring Security có thể quản lý việc lưu theo luồng hoạt động của chúng.

### Ví dụ vòng đời stateful và stateless

| Tình huống | Request đầu | Request sau |
| --- | --- | --- |
| Form login có session | Xác thực thành công, lưu context theo cơ chế đã cấu hình | Repository có thể nạp context từ session, không bắt người dùng nhập mật khẩu lại |
| HTTP Basic stateless | Mỗi request mang Authorization phù hợp, filter xác thực | Request sau cần gửi thông tin xác thực trở lại |
| Bearer/JWT stateless | Filter kiểm tra token, tạo `Authentication` cho request | Request sau gửi lại token; không cần context đăng nhập trong session |
| Chỉ đặt context vào holder thủ công | Mã của request hiện tại đọc được authentication | Không có bảo đảm request sau nhận lại context |

`SessionCreationPolicy.STATELESS` là một lựa chọn cấu hình Spring Security phổ biến cho API stateless. Khi dùng, cần xác minh cả cơ chế authentication, repository và những thành phần có thể sử dụng session; stateless không đồng nghĩa toàn hệ thống Servlet không thể tạo session vì lý do khác.

## 6. ThreadLocal, đa luồng và truyền ngữ cảnh đúng cách

### 6.1. Holder mặc định gắn với thread

Trong ứng dụng Servlet truyền thống, `SecurityContextHolder` mặc định sử dụng một strategy dựa trên `ThreadLocal` (`MODE_THREADLOCAL`). Code chạy trong cùng thread có thể đọc cùng context đã được gắn; nhưng một `Thread` mới, task trong `ExecutorService` hoặc phương thức `@Async` không tự nhận đúng context từ thread cha.

Giả định phổ biến nhưng **sai** là "tôi đã đăng nhập trong request nên mọi thread chạy sau đều biết người dùng đó".

Ví dụ Java 17 độc lập dưới đây dùng `ThreadLocal` thuần của JDK để **mô phỏng ý nghĩa phạm vi thread**. Nó không triển khai `SecurityContextHolder` thật, nên mục đích chỉ là giải thích vì sao một thread con không tự có dữ liệu thread cha.

~~~java
public class ThreadLocalContextDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    private static String currentUser() {
        String value = CURRENT_USER.get();
        return value == null ? "<none>" : value;
    }

    public static void main(String[] args) throws InterruptedException {
        CURRENT_USER.set("alice");
        System.out.println("main before = " + currentUser());

        Thread child = new Thread(
                () -> System.out.println("child = " + currentUser()));
        child.start();
        child.join();

        System.out.println("main after = " + currentUser());
        CURRENT_USER.remove();
        System.out.println("main cleared = " + currentUser());
    }
}
~~~

Lưu vào `ThreadLocalContextDemo.java`; dùng JDK 17+:

~~~bash
javac ThreadLocalContextDemo.java
java ThreadLocalContextDemo
~~~

Stdout chính xác vì `join()` đợi thread con kết thúc:

~~~text
main before = alice
child = <none>
main after = alice
main cleared = <none>
~~~

Trong một ứng dụng thật, thread pool còn làm nguy cơ **rò danh tính giữa các task** lớn hơn nếu tự sao chép context rồi không restore/clear.

### 6.2. Dùng cơ chế bọc task/executor của Spring Security

Khi thật sự cần chuyển context sang tác vụ chạy trên thread khác, Spring Security cung cấp các abstraction như:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor` và các biến thể bọc executor.

Ví dụ **đoạn mã minh họa trong ứng dụng có Spring Security**, không phải chương trình Java độc lập:

~~~java
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.context.SecurityContextHolder;

Runnable task = () -> {
    var authentication =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(authentication == null
            ? "No authentication"
            : authentication.getName());
};

Runnable withContext = new DelegatingSecurityContextRunnable(
        task,
        SecurityContextHolder.getContext());

new Thread(withContext).start();
~~~

Đoạn này cần chạy trong nơi holder đã có context hợp lệ. Wrapper bảo đảm thiết lập context cho lúc chạy task và dọn/khôi phục theo cơ chế của nó. Trong dự án sản xuất, hãy dùng executor quản lý thay vì tùy tiện tạo thread mới cho mỗi request; cân nhắc thời điểm **capture context**, quyền được phép truyền và sự hết hạn của authentication.

**Không bật `MODE_GLOBAL` cho web application đa người dùng** vì chiến lược này chia sẻ context ở phạm vi process, không phù hợp cách ly các request. `MODE_INHERITABLETHREADLOCAL` cũng không phải giải pháp chung cho thread pool: thread được tái sử dụng hoặc tạo ở thời điểm khác dễ mang context cũ, sai người dùng.

### 6.3. Async và Servlet dispatch

Bất kỳ xử lý bất đồng bộ nào cũng cần xét ranh giới: Servlet async request, `Callable` của Spring MVC, `@Async` và task trong executor không hoàn toàn giống nhau. Một số tích hợp Spring Security/MVC có cơ chế truyền context cho tình huống cụ thể, nhưng không có quy tắc rằng mọi callback đều mang context gốc.

Nếu phải truy cập principal sau khi request đã kết thúc, thiết kế tốt thường là chuyển **chỉ dữ liệu nghiệp vụ cần thiết** (ví dụ ID đã kiểm tra) vào task, hoặc dùng wrapper bảo mật thích hợp. Đừng giữ tham chiếu mutable tới toàn bộ `SecurityContext` vô thời hạn.

**Phạm vi bài này là Servlet.** Spring WebFlux dùng mô hình reactive và `ReactiveSecurityContextHolder` với Reactor context; không áp dụng máy móc `ThreadLocal` như cách xử lý Servlet.

## 7. Đọc Authentication an toàn trong controller

Trong ứng dụng Spring Boot 3.x / Spring Security 6.x với `spring-boot-starter-web` và `spring-boot-starter-security`, có thể xây controller ví dụ:

~~~java
import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {
    @GetMapping("/public")
    public String publicMessage() {
        return "public";
    }

    @GetMapping("/me")
    public Map<String, Object> currentUser() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();

        if (auth == null || auth instanceof AnonymousAuthenticationToken) {
            return Map.of("status", "anonymous");
        }

        return Map.of(
                "name", auth.getName(),
                "authenticated", auth.isAuthenticated(),
                "authorities", auth.getAuthorities().stream()
                        .map(authority -> authority.getAuthority())
                        .toList());
    }
}
~~~

Đây là class Java đặt trong dự án Spring Boot; cần classpath/dependencies tương ứng, không chạy độc lập bằng một lệnh `javac` trống. Với request đã xác thực hợp lệ, endpoint có thể trả JSON như:

~~~json
{
  "name": "alice",
  "authenticated": true,
  "authorities": ["ROLE_USER"]
}
~~~

Đó là **một ví dụ output có điều kiện** khi principal tên `alice` mang `ROLE_USER`. Giá trị thực tế phụ thuộc cơ chế xác thực và dữ liệu người dùng.

Trong môi trường thật, không nên trả toàn bộ authorities ra endpoint public khi không cần thiết; ví dụ dùng chúng để giải thích object. Không bao giờ trả `credentials`, password hash, session token, access token hoặc toàn bộ `Authentication.getDetails()` cho client.

### Có nhất thiết phải dùng Holder trong controller không?

Không. Spring Security có nhiều cách tiện hơn để nhận principal đã xác thực trong web layer, ví dụ method argument `Principal`, `Authentication`, hoặc `@AuthenticationPrincipal` với kiểu principal phù hợp:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;

// Trong một @RestController:
@GetMapping("/me/name")
public String currentName(Principal principal) {
    return principal.getName();
}
~~~

Mẫu này phù hợp khi endpoint đã được cấu hình yêu cầu authentication, bảo đảm `principal` khác `null`. Nếu endpoint công khai, cần xử lý null hoặc anonymous phù hợp. Mục đích của `@AuthenticationPrincipal` là lấy **principal** chứ không phải trả về toàn bộ `SecurityContext`.

Với logic nghiệp vụ, hãy tránh để mỗi service tự diễn giải danh tính và role khác nhau. Nên đặt quy tắc quyền ở cấu hình authorization, method security hoặc một policy được kiểm thử tập trung.

## 8. Authentication được dùng để phân quyền như thế nào?

Các filter authentication giúp tạo `Authentication`; các cơ chế authorization như `AuthorizationFilter` và method security dùng thông tin xác thực và authorities để quyết định truy cập. Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CurrentUserSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/me", "/me/name").authenticated()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đây là cấu hình Spring Security 6.x tương ứng với controller phía trên. Các trường hợp:

| Request | Authentication hiện tại | Quy tắc | Kết quả thường gặp |
| --- | --- | --- | --- |
| `GET /public` | Có thể anonymous | `permitAll()` | Controller trả `public` nếu không bị filter khác chặn |
| `GET /me` | Anonymous hoặc thiếu authentication | `authenticated()` | HTTP Basic thường trả 401 |
| `GET /me` | Đã xác thực hợp lệ | `authenticated()` | Chuyển tới controller |
| `GET /admin/audit` | Đã xác thực, thiếu `ROLE_ADMIN` | `hasRole("ADMIN")` | Thường là 403 |
| `GET /admin/audit` | Có `ROLE_ADMIN` | `hasRole("ADMIN")` | Qua authorization; endpoint vẫn cần tồn tại để trả 200 |

Spring Security mặc định diễn giải `hasRole("ADMIN")` bằng authority `ROLE_ADMIN`. `hasAuthority("ADMIN")` lại kiểm tra authority tên `ADMIN` đúng như truyền vào; đừng nhầm tên role với prefix.

**Có authentication trong context không đồng nghĩa được phép mọi endpoint.** Object này là dữ liệu đầu vào; `AuthorizationManager` mới đưa quyết định theo chính sách hiện hành. Tương tự, có principal trong controller không có nghĩa request đã qua rule mong muốn: cần chắc chắn `SecurityFilterChain` phù hợp đã được chọn và quy tắc authorization đã chạy.

## 9. Kiểm thử SecurityContext và Authentication

Trong dự án Spring Boot có `spring-boot-starter-test`, `spring-security-test`, `MockMvc` và cấu hình security như trên, có thể kiểm tra controller nhìn thấy principal và authorities như mong đợi:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CurrentUserContextTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void requestWithoutLoginIsRejected() throws Exception {
        mockMvc.perform(get("/me"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    @WithMockUser(username = "alice", roles = "USER")
    void loggedInRequestReadsContext() throws Exception {
        mockMvc.perform(get("/me"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value("alice"))
                .andExpect(jsonPath("$.authenticated").value(true))
                .andExpect(jsonPath("$.authorities[0]").value("ROLE_USER"));
    }
}
~~~

Những assertion giả định: đúng controller và `SecurityFilterChain` ở ví dụ, HTTP Basic mặc định và filter bảo mật tích hợp vào MockMvc. `@WithMockUser` thiết lập authentication cho **môi trường test**, không xác minh password qua `AuthenticationProvider` thật; test này nhằm xác nhận cách ngữ cảnh được dùng trong request.

Để kiểm thử cơ chế authentication thực, thêm test với request mang credentials/token hợp lệ hoặc không hợp lệ qua đường đi thực tế. Để kiểm tra phân quyền, thêm cả test người dùng thiếu quyền và có quyền. Nếu cần kiểm thử persistence, gửi **hai request nối tiếp** với session/token đã cấu hình; một request duy nhất không chứng minh context được lưu giữa các request.

### Test hai request có cùng session

Với form login stateful, một kiểm thử phù hợp sẽ xác thực ở request đầu, nhận session/cookie, rồi dùng lại session/cookie ở request hai và xác nhận endpoint vẫn nhận đúng principal. Với bearer API stateless, mỗi request nên mang lại bearer token, và không dựa vào session để lấy user.

Chỉ cần nhìn `SecurityContextHolder.getContext().getAuthentication()` trong cùng request không thể chứng minh mã đã xử lý đúng persistence hoặc cleanup giữa nhiều request.

## 10. Những lỗi thường gặp và nguyên nhân

### Lỗi 1: Authentication là null trên endpoint public

`permitAll()` chỉ cho phép truy cập, không bảo đảm có người dùng đã login. Nếu chưa có authentication, `getAuthentication()` có thể là `null` hoặc một anonymous token tùy chain/filter. Truy cập trực tiếp `getPrincipal()` mà không kiểm tra có thể gây `NullPointerException`.

### Lỗi 2: isAuthenticated() là true nhưng request vẫn không được coi fully authenticated

Đây thường là trường hợp `AnonymousAuthenticationToken` hoặc remember-me. Authorization DSL phân biệt anonymous, authenticated và fully authenticated bằng ngữ nghĩa của framework. Không tự thay rule bằng một phép kiểm tra cờ Boolean đơn giản.

### Lỗi 3: Service lấy context nhưng thread khác đọc ra null

`@Async`, custom executor hoặc thread do ứng dụng tạo không tự chia sẻ `MODE_THREADLOCAL`. Chọn đúng cách truyền ngữ cảnh, hoặc truyền dữ liệu người dùng đã kiểm chứng dưới dạng tham số nghiệp vụ nếu đủ.

### Lỗi 4: Có người dùng A trong request của B

Nguy cơ rò ngữ cảnh khi mã tự set context mà không clear, dùng thread pool với propagation sai hoặc bật strategy global. Phải xác định nơi set, thời điểm restore/clear và không lưu static `Authentication` dùng chung.

### Lỗi 5: Login thành công trong request nhưng request sau thành anonymous

Việc lưu vào `SecurityContextHolder` không tự động bảo đảm lưu vào session. Kiểm tra authentication filter, `SecurityContextRepository`, `saveContext(...)`, session/cookie và chính sách stateless. Đặc biệt với `SecurityContextHolderFilter`, phải hiểu cơ chế **explicit save** cho luồng đăng nhập tự viết.

### Lỗi 6: Ép principal thành UserDetails rồi bị ClassCastException

Với các cơ chế khác nhau, principal có thể là `Jwt`, `String`, object domain hoặc `UserDetails`. Nếu cần một kiểu domain thống nhất, hãy xây adapter/mapping rõ ràng hoặc kiểm tra kiểu trước khi cast.

### Lỗi 7: Set Authentication thủ công để vượt qua authorization

Không có bước xác minh mà tự đặt token trusted vào context là một lỗ hổng nghiêm trọng. Luôn sử dụng `AuthenticationManager`/provider hay một cơ chế tin cậy đã được kiểm tra, và giới hạn nơi mã có thể tạo authentication đã xác thực.

### Lỗi 8: Nghĩ context hiện tại tương đương database user

`Authentication` biểu diễn principal/authorities tại thời điểm xác thực hoặc request hiện tại. Quyền trong context có thể chưa phản ánh một thay đổi mới ở database, session hoặc token cũ. Hệ thống cần chính sách riêng về refresh authority, token expiration, revocation và đọc quyền động khi nghiệp vụ yêu cầu.

### Lỗi 9: Bật MODE_INHERITABLETHREADLOCAL để sửa mọi vấn đề async

Strategy inheritable có thể chép context ở thời điểm **tạo thread**, nhưng thread pool tạo sẵn và tái sử dụng thread làm semantics trở nên khó kiểm soát. Với ứng dụng server nhiều người dùng, ưu tiên các wrapper của Spring Security hoặc thiết kế truyền context có kiểm soát.

### Lỗi 10: Chỉ test giá trị trong cùng request và kết luận không có rò dữ liệu

Một unit test đơn luồng không kiểm tra được cleanup khi request kết thúc, propagation sang executor, session persistence hoặc hai người dùng xen kẽ. Những tình huống này cần integration test và mô hình concurrency phù hợp.

## 11. Bài tập tự kiểm tra

**Bài 1.** Controller gọi `SecurityContextHolder.getContext()` và nhận context hợp lệ, nhưng `getAuthentication()` trả `null`. Có mâu thuẫn không?

**Đáp án:** Không. Context có thể tồn tại ở trạng thái rỗng. Không nên giả định sự tồn tại của context đồng nghĩa đã có principal được xác thực.

**Bài 2.** Người dùng đã gửi thông tin xác thực, `AuthenticationManager` kiểm tra thành công. Đặt kết quả vào đâu để mã trong thread hiện tại nhìn thấy?

**Đáp án:** Tạo `SecurityContext` bằng `SecurityContextHolder.createEmptyContext()`, đặt `Authentication` đã xác thực bằng `setAuthentication(...)`, rồi `SecurityContextHolder.setContext(...)`. Với stateful login, còn phải xem cơ chế lưu context và session; chỉ set holder không tự bảo đảm request sau nhận được.

**Bài 3.** Trong endpoint public, `authentication.isAuthenticated()` bằng `true`. Có chắc là một user đã login không?

**Đáp án:** Không. Anonymous token cũng có thể trả true. Nên dùng cơ chế phân biệt anonymous/remember-me của framework và quy tắc authorization tương ứng.

**Bài 4.** Một request từ user A gọi `ExecutorService.submit(...)` và task chạy ở thread pool. Task có chắc thấy Authentication của A không?

**Đáp án:** Không, với mặc định ThreadLocal. Cần wrapper/truyền dữ liệu phù hợp và cleanup; tránh gắn context dùng chung hoặc phụ thuộc vào việc tái sử dụng thread.

**Bài 5.** API stateless dùng Bearer token. Khi request thứ nhất hoàn tất, có cần giữ authentication của nó mãi trong thread để request sau dùng lại không?

**Đáp án:** Không. Mỗi request thường tự xác thực từ token được gửi theo request. Holder phải được dọn sau xử lý để không rò state sang request khác.

**Bài 6.** Một user có `ROLE_USER` và `Authentication` đã xác thực. API `/admin/audit` yêu cầu `ROLE_ADMIN`. Vì sao user không được vào dù holder có Authentication?

**Đáp án:** Context chỉ chứa dữ liệu danh tính/authority; authorization kiểm tra quyền theo policy riêng. Người dùng thiếu authority nên thường bị từ chối 403.

## 12. Checklist khi dùng SecurityContext trong ứng dụng Servlet

- Xác định **ai tạo Authentication**, ai xác minh credentials và ai đặt kết quả vào `SecurityContext`.
- Hiểu quan hệ **holder → context → authentication**, và mỗi API thực sự trả về gì.
- Xử lý trường hợp authentication là `null` hoặc anonymous; không coi `isAuthenticated()` là bằng chứng đầy đủ của login.
- Tránh log credentials/token và tránh cast cứng principal sang một kiểu không được bảo đảm.
- Để framework quản lý context theo request; nếu tự set context, bảo đảm đúng nguồn xác thực, persistence cần thiết và cleanup.
- Phân biệt **context trong thread** với **context lưu giữa các request** qua repository/session.
- Xem xét propagation khi dùng executor/`@Async`; không chia sẻ holder kiểu global giữa người dùng.
- Kiểm thử anonymous, authenticated, phân quyền, request tiếp theo, cleanup và concurrency theo nhu cầu thật.

**Ghi nhớ:** `SecurityContextHolder` giúp tìm **SecurityContext của luồng xử lý hiện tại**; `SecurityContext` giữ **Authentication**; `Authentication` mô tả danh tính và quyền được trình bày cho Spring Security. Cách đọc, lưu và dọn ngữ cảnh theo đúng vòng đời Servlet mới tạo nên hành vi xác thực và phân quyền nhất quán.