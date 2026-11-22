# SecurityContextHolderStrategy và giới hạn của các chiến lược lưu

Trong ứng dụng Spring Security Servlet, bạn thường thấy code sau:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
```

Nó đọc được người dùng vừa được xác thực trong một controller hoặc service đồng bộ. Nhưng tại sao code tương tự chạy trong `CompletableFuture.supplyAsync(...)` lại thấy `null`? Vì sao một lần đổi `MODE_INHERITABLETHREADLOCAL` dường như “sửa” được vấn đề khi tạo `new Thread(...)`, nhưng lại gây rủi ro với thread pool? Và vì sao đổi `MODE_GLOBAL` có thể khiến hai request của hai người dùng nhìn thấy danh tính của nhau?

Câu trả lời nằm ở **SecurityContextHolderStrategy**: một *hợp đồng quản lý vị trí của `SecurityContext` trong luồng thực thi hiện tại*, không phải kho tài khoản, không phải session repository và không phải chức năng tự xác thực. Chọn sai chiến lược hoặc không dọn ngữ cảnh tại ranh giới request/task có thể gây **rò danh tính giữa người dùng**, truy cập sai quyền hoặc mất authentication khi chuyển thread.

Bài thuộc nhóm **Ngữ cảnh Servlet** trong chủ đề *Spring Security - authentication*. Phạm vi chính là Spring Security Servlet 6.x trên Java 17+. Ví dụ Gradle/Spring Security Core 6.5.x chạy được cho `MODE_THREADLOCAL` và truyền ngữ cảnh có kiểm soát; phần tích hợp Spring Boot 3.x, Spring MVC async và `SecurityContextRepository` giải thích ranh giới request/session. **Không áp dụng nguyên xi ThreadLocal cho WebFlux/Reactor.**

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích khác nhau giữa `SecurityContext`, `Authentication`, `SecurityContextHolder`, `SecurityContextHolderStrategy`, `SecurityContextRepository` và filter quản lý vòng đời request.
2. Nêu hành vi/giới hạn của `MODE_THREADLOCAL`, `MODE_INHERITABLETHREADLOCAL` và `MODE_GLOBAL`; xác định chế độ phù hợp cho servlet server nhiều người dùng.
3. Hiểu API `getContext`, `createEmptyContext`, `setContext`, `clearContext`, `getDeferredContext`, `setDeferredContext` và ý nghĩa của chiến lược tùy biến.
4. Giải thích khi nào context mất đi hoặc có thể rò qua thread pool, `@Async`, `CompletableFuture`, scheduler và callback.
5. Dùng `DelegatingSecurityContextRunnable`/`DelegatingSecurityContextExecutor` để chuyển context đúng thời điểm, làm sạch ở thread nhận và kiểm ranh giới.
6. Phân biệt **lưu theo thread trong một lần thực thi** với **lưu qua nhiều HTTP request** bằng session/cookie/`SecurityContextRepository`.
7. Tránh tự đặt `Authentication` đã xác thực trước khi kiểm credential, tránh giữ raw password và tránh truyền ngữ cảnh có đặc quyền cao vào task không liên quan.
8. Tự chạy code và dùng ma trận kiểm thử để chứng minh context không bị trộn giữa hai người dùng/request.

## 2. Sáu thành phần gần nhau về tên nhưng khác trách nhiệm

| Thành phần | Trách nhiệm | Không tự cung cấp |
| --- | --- | --- |
| `Authentication` | Biểu diễn yêu cầu xác thực hoặc kết quả xác thực, gồm principal, credentials, authorities và trạng thái authenticated. | Không tự bảo đảm trạng thái account còn mới trong DB. |
| `SecurityContext` | Container chứa `Authentication` của luồng xử lý bảo mật hiện tại. | Không tự lưu session, không tự verify password. |
| `SecurityContextHolder` | Façade static để truy cập `SecurityContext` từ code đang chạy. | Không phải database hay HTTP session. |
| **`SecurityContextHolderStrategy`** | Quy định **cách lưu/tìm/xóa context cho execution**. | Không tự tạo authentication đúng, không tự persist sang request sau. |
| `SecurityContextRepository` | Nạp/lưu `SecurityContext` qua ranh giới request bằng session, request attribute hoặc kho khác. | Không định nghĩa ai được xác thực; không tự thay thế strategy. |
| `SecurityContextHolderFilter` / `SecurityContextPersistenceFilter` | Thiết lập/khôi phục/đảm bảo cleanup theo luồng filter tùy phiên bản/cấu hình. | Không mặc định cấp quyền cho client chưa qua authentication. |

Tách đúng ba câu hỏi:

- **Ai đã được xác thực?** → `Authentication` được tạo bởi filter/provider/cơ chế đáng tin.
- **Code đang chạy nhìn thấy context đó như thế nào?** → `SecurityContextHolder`/`SecurityContextHolderStrategy`.
- **Request mới có thể lấy lại authentication của request trước không?** → `SecurityContextRepository` + cookie/session/token/filter configuration.

Một chiến lược `MODE_THREADLOCAL` có thể hoàn toàn đúng cho request hiện tại dù hệ thống dùng `HttpSession`, JWT stateless hoặc opaque token. **Chế độ holder không quyết định có tạo session hay không.**

### 2.1 Sơ đồ hai vòng đời

```text
VÒNG ĐỜI REQUEST (Servlet)
  HTTP request
    |
    v
  SecurityContextRepository.loadDeferredContext(...)
    |
    v
  SecurityContextHolderFilter nạp context vào HolderStrategy
    |
    v
  Authentication filter/provider nếu cần
    |
    v
  Controller/Service đọc HolderStrategy.getContext()
    |
    v
  Nếu cần persistence: saveContext(...) theo cơ chế thích hợp
    |
    v
  Kết thúc request / cleanup context khỏi thread

VÒNG ĐỜI THREAD/TASK
  Request worker thread A
    -> MODE_THREADLOCAL: context A nằm ở A
    -> gửi task sang thread B
         B không tự nhận context A
         nếu có wrapper: truyền snapshot/context có kiểm soát
         chạy task B
         finally: dọn context của B
```

Trong Spring Security 6, `SecurityContextHolderFilter` thường chịu trách nhiệm **nạp** context, và cơ chế custom authentication muốn persist phải **save rõ vào `SecurityContextRepository`**. `SecurityContextPersistenceFilter` của cấu hình cũ có cơ chế tự save khi thích hợp; không đăng ký cả hai cho cùng luồng theo mặc định. Xem phần 8 để phân biệt.

## 3. SecurityContextHolderStrategy là gì?

`SecurityContextHolderStrategy` là một interface trong package `org.springframework.security.core.context`. Nó định nghĩa thao tác để một thành phần lấy, đặt hoặc xóa `SecurityContext`. Các thành phần Spring Security có thể truy cập strategy qua `SecurityContextHolder.getContextHolderStrategy()` hoặc được cấu hình strategy tương ứng.

Hợp đồng API chính, diễn giải để học:

```java
public interface SecurityContextHolderStrategy {
    void clearContext();
    SecurityContext getContext();
    void setContext(SecurityContext context);
    SecurityContext createEmptyContext();

    // Default methods có trong Spring Security 5.8+:
    Supplier<SecurityContext> getDeferredContext();
    void setDeferredContext(Supplier<SecurityContext> deferredContext);
}
```

**Đây là bản minh họa chữ ký, không phải file cần định nghĩa lại.** Interface thật của thư viện là nơi chuẩn để đối chiếu hành vi và default methods theo phiên bản.

### 3.1 Các thao tác quan trọng

- `getContext()`: lấy context được liên kết với execution hiện tại; theo hợp đồng phải trả một đối tượng không `null`. **Không đảm bảo `getAuthentication()` khác `null`**.
- `createEmptyContext()`: tạo một context rỗng **mới** theo strategy; nên dùng trước khi đặt một authentication mới để tránh thay đổi một instance context đang được chia sẻ.
- `setContext(context)`: liên kết context với execution theo strategy hiện hành; không tự lưu vào `HttpSession`.
- `clearContext()`: xóa liên kết trên execution hiện tại theo strategy. Với ThreadLocal, dọn sau request/task là bắt buộc để tránh thread kế tiếp thấy danh tính cũ.
- `getDeferredContext()`: lấy `Supplier<SecurityContext>` để truy cập context có thể hoãn theo strategy; không phải token portable có thể gửi giữa tiến trình.
- `setDeferredContext(supplier)`: đặt supplier context, có ý nghĩa với deferred loading; strategy có thể override default để tối ưu.
- `SecurityContextHolder.getContextHolderStrategy()`: cho phép lấy strategy mà façade hiện sử dụng; hữu ích khi custom component phải nhất quán với filter chain.

### 3.2 Context rỗng không phải anonymous authentication

`getContext()` thường trả một context, kể cả khi chưa có người dùng; `getContext().getAuthentication()` khi đó có thể là `null`. Trong một request qua Spring Security, `AnonymousAuthenticationFilter` có thể đặt `AnonymousAuthenticationToken` để các lớp downstream nhìn thấy một authentication biểu diễn anonymous. Điều này **không có nghĩa anonymous được coi là authenticated đủ để truy cập endpoint bảo vệ**; `AuthenticationTrustResolver` và authorization rules phân biệt anonymous.

Không viết:

```java
// Sai: có context object không có nghĩa đã đăng nhập.
boolean loggedIn =
        SecurityContextHolder.getContext() != null;
```

Khi muốn biết principal đang xử lý request, dùng `Authentication` được framework cung cấp, đồng thời để authorization rule quyết định quyền; đừng suy diễn chỉ từ sự tồn tại của container.

## 4. Ba chiến lược tích hợp sẵn

Spring Security định nghĩa ba mode trong `SecurityContextHolder`:

| Chế độ | Phạm vi lưu context | Phù hợp | Rủi ro và giới hạn |
| --- | --- | --- | --- |
| **`MODE_THREADLOCAL`** | Mỗi thread có một association riêng qua ThreadLocal. Đây là default. | **Servlet server nhiều user**, request processing đồng bộ. | Context không tự theo task chạy trên thread khác; phải cleanup thread sau sử dụng. |
| **`MODE_INHERITABLETHREADLOCAL`** | Thread mới được tạo có thể kế thừa giá trị ThreadLocal từ parent lúc tạo thread. | Một vài ứng dụng desktop/batch có thread con thực sự được tạo có kiểm soát. | **Không phải propagation per-task trong thread pool**; có thể kế thừa/chia sẻ reference ngoài ý định, giữ principal cũ hoặc rò dữ liệu. |
| **`MODE_GLOBAL`** | Một context trong phạm vi JVM được dùng giữa nhiều threads. | Trường hợp standalone đặc biệt với một danh tính chung trong JVM. | **Không phù hợp web server nhiều người dùng**: request A/B có thể overwrite hoặc thấy identity của nhau. |

Tài liệu Spring Security mô tả `MODE_THREADLOCAL` là lựa chọn mặc định thích hợp cho server. Đừng đổi sang `MODE_GLOBAL` để làm cho worker thread “thấy user”; đây có thể là lỗi bảo mật nghiêm trọng nhất trong ba cách xử lý.

### 4.1 MODE_THREADLOCAL: đúng vì nó không chia sẻ mặc định

Giả sử servlet container tái sử dụng hai thread cho các request:

```text
Thread T1: Request của Alice
   HolderStrategy[T1] -> Context(Alice)

Thread T2: Request của Bob
   HolderStrategy[T2] -> Context(Bob)

Nếu Alice gửi task sang T2:
   Task chạy trên T2 KHÔNG tự có Context(Alice).
   Framework/callback phải thiết lập scope phù hợp một cách có kiểm soát.
```

ThreadLocal bảo vệ khỏi việc **mặc định dùng cùng context cho mọi thread**, nhưng không bảo đảm hoàn toàn an toàn nếu lập trình viên không dọn/không thiết lập scope đúng. Thread pool giữ các worker lâu dài; nếu một task tự `setContext` nhưng quên `clearContext` trong `finally`, task sau có thể thấy principal cũ.

`ThreadLocal` cũng không phải *một context khác nhau cho mỗi HTTP request* theo định nghĩa Java. Nó là *một value slot cho mỗi thread*. Spring Security filter chain phải nạp đúng context khi request vào và cleanup khi request kết thúc. Không coi thread ID là user ID.

### 4.2 MODE_INHERITABLETHREADLOCAL: child thread khác pooled thread

Java `InheritableThreadLocal` truyền giá trị **khi child thread được tạo**, không phải khi submit một task vào một thread đã tồn tại. Một thread pool có thể khởi tạo workers lúc chưa có context hoặc dưới danh tính của một request bất kỳ. Sau đó các task của Bob/Alice cùng tái sử dụng workers; kế thừa không xảy ra lại mỗi lần `submit`.

Ngoài ra, mặc định của `InheritableThreadLocal.childValue` là chuyển **cùng reference value** sang child trừ khi có logic copy riêng. Với `SecurityContext` có trạng thái mutable, parent và child có thể vô tình cùng quan sát thay đổi của object. Việc một thread `clearContext` không mặc nhiên xóa reference được giữ ở child khác.

Ví dụ nguy hiểm về mặt thời điểm:

```text
09:00 Thread request(Alice) tạo Worker-7 khi context=Alice
09:01 Worker-7 hoàn thành task và vẫn tồn tại trong pool
09:02 Thread request(Bob) gửi task tới Worker-7
09:03 Worker-7 có thể vẫn gắn context đã kế thừa/còn sót của Alice
=> Không thể dùng inherited thread-local như phân quyền task.
```

**Quy tắc:** Với `ExecutorService`, `@Async`, `CompletableFuture` và scheduler, truyền security context theo **task submission/execution boundary** bằng wrapper được hỗ trợ hoặc một hợp đồng identity tường minh có kiểm quyền. Không dựa vào “bật inheritable là xong”.

### 4.3 MODE_GLOBAL: tất cả thread dùng một vị trí

Nếu ứng dụng Servlet có Alice và Bob chạy đồng thời:

```text
Request Alice đặt global Authentication(Alice).
Request Bob đặt global Authentication(Bob).
Request Alice tiếp tục và đọc global context => có thể thấy Bob.
```

Đây là mô hình **cross-user leakage/cross-request identity confusion**. `MODE_GLOBAL` chỉ có ý nghĩa trong chương trình đặc thù với ngữ cảnh an ninh chung toàn JVM, không phải multi-tenant/multi-user web service.

Nếu thấy lỗi “async task không nhìn thấy user”, **không** xử lý bằng `MODE_GLOBAL`. Hãy xem vì sao task cần identity và dùng `DelegatingSecurityContextExecutor` hoặc cơ chế được framework quản lý.

## 5. Khi nào thiết lập strategy và vì sao không nên đổi giữa các request?

Một chiến lược được chọn ở mức **JVM-wide** thông qua `SecurityContextHolder`. Có thể đặt ở startup bằng system property được tài liệu hỗ trợ hoặc `SecurityContextHolder.setStrategyName(...)`. Cũng có API `setContextHolderStrategy(customStrategy)` cho chiến lược tùy biến.

Ví dụ minh họa lựa chọn **trước khi ứng dụng khởi tạo các filter và thread**:

```java
// Chỉ dùng lúc bootstrap, không chạy trong controller/request.
SecurityContextHolder.setStrategyName(
        SecurityContextHolder.MODE_THREADLOCAL);
```

Trên một JVM production, default đã là `MODE_THREADLOCAL`, nên **thường không cần dòng cấu hình này**. Nếu đổi strategy sau khi app đã có threads/request đang chạy:

- Thread cũ có thể đang giữ context theo strategy trước.
- Một số component có thể đã nhận/tham chiếu strategy cũ.
- Việc chuyển static strategy làm thay đổi cách tất cả thread nhìn context.
- `SecurityContextHolder.getInitializeCount()` tăng theo số lần tái khởi tạo (hữu ích chẩn đoán, **không phải metric đăng nhập**).
- Kết quả dưới tải đồng thời có thể không nhất quán hoặc rò an ninh.

Javadoc nêu rõ không nên gọi `setStrategyName` nhiều lần cho cùng JVM; `setContextHolderStrategy` cũng **không thread-safe** và không dùng để chuyển đổi ở lúc request đang chạy.

### 5.1 Custom SecurityContextHolderStrategy

Khi có yêu cầu thật sự đặc biệt, có thể cung cấp implementation của `SecurityContextHolderStrategy`. Nhưng đó là thay đổi *security infrastructure*, không phải cách thông thường để “thêm một field vào principal”. Custom strategy cần:

1. Bảo đảm `getContext()` không `null`, `createEmptyContext()` tạo đúng context rỗng, `setContext(null)` bị từ chối theo hợp đồng.
2. Quy định rõ scope, sự cách ly giữa requests/tasks và cách `clearContext()` loại bỏ association.
3. Xử lý đúng `Supplier<SecurityContext>` và deferred loading nếu framework dựa vào `getDeferredContext()`/`setDeferredContext()`.
4. Kiểm classloader/application restart, shared singleton, memory retention và thread-safety.
5. Đảm bảo filter/repository/delegating concurrency wrappers đang dùng cùng strategy, đặc biệt khi chúng được cấu hình bằng setter `setSecurityContextHolderStrategy(...)` ở từng component.
6. Thử xuyên suốt authentication, logout, servlet async, task executors và điều kiện lỗi/exception.
7. Không tự thay JVM-wide static strategy để áp dụng tenant riêng cho một request; tenant là dữ liệu đã xác thực trong principal/context, **không phải một mode toàn JVM**.

Ví dụ **sử dụng strategy đã cấu hình** mà không thay đổi nó:

```java
SecurityContextHolderStrategy strategy =
        SecurityContextHolder.getContextHolderStrategy();

SecurityContext fresh = strategy.createEmptyContext();
fresh.setAuthentication(authenticationFromTrustedProvider);
strategy.setContext(fresh);

// Khi quản lý một scope thủ công, phải dọn sau khi kết thúc.
strategy.clearContext();
```

Đoạn trên là **mẫu minh họa cho code bảo mật nội bộ**, không phải login flow hoàn chỉnh và **không được tự tạo authentication đã xác thực từ username do client gửi**. Với servlet thông thường, filter chain đã quản lý scope, controller không nên tự đổi global context.

## 6. Cách đặt Authentication vào context đúng và không rò dữ liệu

Khi một thành phần authentication đáng tin vừa xác minh credential, code thường tạo **một context mới** rồi gắn kết quả:

```java
// authentication là kết quả THẬT của AuthenticationManager.authenticate(...),
// không phải object tự đánh dấu authenticated từ input chưa kiểm.
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(authentication);
SecurityContextHolder.setContext(context);
```

Tại sao không viết ngắn:

```java
SecurityContextHolder.getContext().setAuthentication(authentication);
```

Trong một số kiến trúc, instance context có thể được giữ/shared bởi repository, session hoặc thread khác. Mutate một context đang được tái sử dụng có thể tạo điều kiện race giữa nhiều xử lý. Tạo context mới giúp phạm vi và ownership rõ hơn, nhưng **không thay việc save đúng vào repository nếu muốn login qua request sau**.

### 6.1 Dọn bằng finally khi tự quản lý scope

Nếu bạn tự đặt context trong một tác vụ không do Spring Security FilterChainProxy quản lý:

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContext scoped = SecurityContextHolder.createEmptyContext();
    scoped.setAuthentication(trustedAuthentication);
    SecurityContextHolder.setContext(scoped);
    // Chạy công việc trong phạm vi identity đã được phép.
} finally {
    SecurityContextHolder.clearContext();
    // Với scope lồng nhau có hợp đồng restore thật sự, thiết kế restore
    // previous riêng và kiểm không giữ reference ngoài phạm vi.
}
```

Với pooled workers, mặc định **clear context trong finally** để task sau không nhận danh tính cũ. Tuy nhiên, nếu đã có security context hợp lệ trên thread trước khi vào scope lồng nhau, blindly clear có thể làm mất context của caller. Dùng wrapper/cơ chế có contract cleanup/restore đã được kiểm thử hoặc truyền identity tường minh; không tự viết helper “save/restore” thiếu hiểu biết.

### 6.2 Không tự tạo Authentication “authenticated” từ raw input

```java
// SAI: username đến từ request không chứng minh danh tính.
var forged = UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));

SecurityContextHolder.getContext().setAuthentication(forged);
```

Đây là anti-pattern nghiêm trọng. `SecurityContextHolderStrategy` chỉ giữ object bạn đặt vào; nó **không gọi PasswordEncoder**, không xác minh token signature và không ngăn việc bạn tự đánh dấu authenticated. Phải để `AuthenticationManager`/provider/filter được tin cậy trả về kết quả đã xác thực, sau đó lưu đúng cách.

### 6.3 clearContext không phải logout toàn bộ thiết bị

`SecurityContextHolder.clearContext()` xóa association của execution hiện tại (thường là ThreadLocal). Nó **không tự**:

- invalidate `HttpSession` đã lưu context;
- xóa cookie phía browser hoặc session của các tab/thiết bị khác;
- revoke JWT, refresh token hay remember-me cookie;
- thay đổi enabled/locked/account state trong database;
- thu hồi authorities đã cấp trong một request khác đang chạy.

Logout đúng cần handler/session repository/token revocation phù hợp. Đừng chỉ gọi `clearContext()` trong controller rồi trả “đã đăng xuất mọi thiết bị”.

## 7. Chuyển thread: tại sao ThreadLocal không truyền context?

Một tác vụ Java có thể chạy trong thread khác bởi `new Thread(...)`, `ExecutorService`, `CompletableFuture`, `@Async` hoặc scheduler. Với `MODE_THREADLOCAL`, thread nhận **không tự có** context của thread gửi.

```text
HTTP request thread A
  SecurityContextHolder[A] -> Alice
           |
           | pool.submit(work)
           v
Pooled worker thread B
  SecurityContextHolder[B] -> empty (hoặc dữ liệu sót nếu code lỗi)

Nếu A gắn Alice cho B bằng wrapper được hỗ trợ:
  save/capture context khi gửi task
  set Alice cho B trong scope của task
  work.run()
  finally clear/restore context B
```

Đừng sửa bằng cách gọi `SecurityContextHolder.getContext()` ngay trong task rồi hy vọng được Alice: lúc đó bạn đang đọc **thread B**, không phải thread A.

### 7.1 DelegatingSecurityContextRunnable

Spring Security có `org.springframework.security.concurrent.DelegatingSecurityContextRunnable`. Nó bao bọc một `Runnable`, thiết lập `SecurityContext` cho thread thực thi, gọi delegate và dọn holder sau khi xong. Với constructor nhận một `Runnable`, wrapper có thể lấy context của caller tại thời điểm tạo wrapper.

```java
Runnable businessTask = () -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "(none)" : auth.getName());
};

Runnable securedTask =
        new DelegatingSecurityContextRunnable(businessTask);

executor.execute(securedTask);
```

**Đây là đoạn mã ghép vào execution flow đã có**, chưa tự khai báo `executor` hay tạo Authentication. Chỉ wrap sau khi request được xác thực, không wrap trước khi current user đã được đặt vào context.

### 7.2 DelegatingSecurityContextExecutor và hai cách capture

`DelegatingSecurityContextExecutor` bọc một `Executor`, tránh phải wrap từng `Runnable` thủ công:

```java
Executor delegate = ...;

// Constructor này lấy context của caller khi gửi mỗi task,
// phù hợp cho task ngắn cần chạy dưới principal hiện tại.
Executor securityAware =
        new DelegatingSecurityContextExecutor(delegate);

securityAware.execute(() -> doAuthorizedWork());
```

Nếu constructor nhận **context cố định**:

```java
SecurityContext explicitContext = ...;
Executor securityAware =
        new DelegatingSecurityContextExecutor(
                delegate, explicitContext);
```

thì các task có thể dùng **cùng context cố định**, không nhất thiết là user đang gửi task. Điều này hữu ích với một identity service đặc biệt đã được kiểm soát, nhưng nguy hiểm nếu vô tình tạo executor dùng `ROLE_ADMIN` rồi đưa cho mọi nơi trong ứng dụng. Xem chính xác constructor và lifetime; **không chia sẻ mutable context có quyền cao giữa các request độc lập**.

Spring Security còn có `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutorService`, `DelegatingSecurityContextAsyncTaskExecutor`, các wrapper liên quan scheduler và Spring Task. Chọn adapter khớp abstraction thực tế, không tự xóa thread-local của Spring Security một cách tùy tiện.

### 7.3 Propagation là truyền identity, không phải cập nhật quyền live

Khi một task được gửi lúc 10:00 với context chứa `ROLE_ADMIN`, sau đó quyền bị thu hồi lúc 10:01, task chạy 10:02 **không tự biết** role đã bị thu hồi chỉ vì wrapper đã chuyển context. Với tác vụ quan trọng, kiểm lại account status, tenant membership và object-level authorization tại lúc thực hiện.

Nếu task được đưa vào queue lâu, gửi sang process khác hoặc xử lý bởi message broker, không nên serialize nguyên `SecurityContext`/principal/password verifier để dùng mãi. Hãy truyền subject ID/tenant/action đã kiểm, thiết kế delegation token hoặc service identity có hạn, rồi **reauthorize** ở consumer theo policy.

## 8. Ví dụ Java 17+ chạy được: worker không có context, wrapper truyền đúng

Ví dụ dùng `spring-security-core` 6.5.6 và Java 17. Nó tạo `Authentication` giả lập **được đánh dấu đã xác thực chỉ để kiểm tra hành vi holder trong test local**, không làm user login HTTP thật. Không dùng kỹ thuật tạo token giả này tại boundary với dữ liệu client.

Dự án:

```text
context-holder-lab/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ContextHolderLab.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'context-holder-lab'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-core:6.5.6'
}

application {
    mainClass = 'demo.ContextHolderLab'
}
```

File `src/main/java/demo/ContextHolderLab.java`:

```java
package demo;

import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class ContextHolderLab {

    private ContextHolderLab() {
    }

    private static String principalName() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "(none)" : auth.getName();
    }

    public static void main(String[] args) throws Exception {
        // Chỉ demo một lần ở startup, KHÔNG đổi strategy trong request.
        SecurityContextHolder.setStrategyName(
                SecurityContextHolder.MODE_THREADLOCAL);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext context =
                    SecurityContextHolder.createEmptyContext();

            // Token giả lập một kết quả đã xác thực chỉ cho test local.
            context.setAuthentication(
                    UsernamePasswordAuthenticationToken.authenticated(
                            "alice",
                            null,
                            AuthorityUtils.createAuthorityList(
                                    "ROLE_READER")));
            SecurityContextHolder.setContext(context);

            System.out.println("main=" + principalName());

            // Thực thi trong worker của pool, không truyền context.
            String withoutContext = pool.submit(
                    (Callable<String>) ContextHolderLab::principalName)
                    .get();
            System.out.println("worker-plain=" + withoutContext);

            // Bao task khi còn ở main thread đang có context Alice.
            Runnable wrapped = new DelegatingSecurityContextRunnable(
                    () -> System.out.println(
                            "worker-wrapped=" + principalName()));

            pool.submit(wrapped).get();

            // Wrapper đã dọn context trên pooled worker.
            String afterWrappedTask = pool.submit(
                    (Callable<String>) ContextHolderLab::principalName)
                    .get();
            System.out.println("worker-after=" + afterWrappedTask);
        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdown();
        }

        System.out.println("main-after-clear=" + principalName());
        SecurityContextHolder.clearContext();
    }
}
```

### 8.1 Chạy chương trình

Nếu project có Gradle wrapper:

```bash
./gradlew run --console=plain
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat run --console=plain
```

Nếu chưa có wrapper, có thể dùng `gradle run --console=plain` sau khi cài Gradle tương thích. `javac ContextHolderLab.java` đơn lẻ không đủ vì code import Spring Security; Gradle giải quyết classpath.

Stdout **của chương trình Java** (không bao gồm log của Gradle):

```text
main=alice
worker-plain=(none)
worker-wrapped=alice
worker-after=(none)
main-after-clear=(none)
```

Đây là kết quả logic xác định với `MODE_THREADLOCAL`, một worker và không có ai khác can thiệp. Nó minh họa:

1. Context của main thread chứa Alice.
2. Raw worker khác không có context Alice.
3. Wrapper đưa Alice vào đúng phạm vi một task.
4. Sau task, wrapper dọn context của worker.
5. Main thread vẫn giữ Alice đến khi chính main thực hiện cleanup.

**Không suy ra** vì một wrapper chạy đúng nên mọi `@Async`/scheduler đã được bảo vệ. Mỗi execution path phải dùng abstraction hoặc decorator phù hợp, đặc biệt với task được submit ở thread khác hoặc thay đổi strategy.

### 8.2 Test thêm điều gì?

- Gửi task với Bob sau Alice, xác nhận worker không còn thấy Alice.
- Gửi task ném exception rồi tiếp tục task khác, xác nhận cleanup vẫn thực hiện.
- Gửi nhiều task đồng thời trên pool nhiều threads, kiểm mỗi task thấy đúng submitting principal.
- Tạo wrapper với context cố định rồi kiểm policy không vô tình cấp cùng quyền cho mọi caller.
- Đổi security strategy giữa tasks chỉ trong chương trình test riêng để quan sát sự cố, **không làm trong JVM đang phục vụ request**.

## 9. Lưu giữa HTTP requests: SecurityContextRepository, không phải holder strategy

**Khác biệt quan trọng nhất của chủ đề:** `SecurityContextHolderStrategy` trả lời **nơi context của execution hiện tại được liên kết**. `SecurityContextRepository` trả lời **làm sao request mới tìm lại context đã được lưu**. Một ứng dụng vẫn dùng `MODE_THREADLOCAL` khi có HTTP session, vì request mới có thể chạy trên thread khác và filter sẽ nạp context từ repository đúng thời điểm.

Các implementation điển hình:

| Repository | Đặc tính | Khi nào dùng |
| --- | --- | --- |
| `HttpSessionSecurityContextRepository` | Gắn `SecurityContext` với `HttpSession`, cho phép request sau dùng session cookie tải lại context. | Form login/session stateful. |
| `RequestAttributeSecurityContextRepository` | Giữ context trong attribute **chỉ của một request**, hỗ trợ các dispatch như error trong cùng request. | Request lifetime cần bảo toàn qua servlet dispatch. |
| `NullSecurityContextRepository` | Không lưu context cho request sau. | Stateless authentication nơi mỗi request được xác minh độc lập. |
| `DelegatingSecurityContextRepository` | Ủy nhiệm cho nhiều repository, ví dụ request attribute + HTTP session. | Cấu hình Servlet phổ biến trong Spring Security 6. |

Đổi `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` **không** làm session tự tồn tại sau request. Tương tự, lưu `HttpSession` **không** làm một `@Async` task tự có context khi chạy trên thread pool nếu không có propagation.

### 9.1 SecurityContextHolderFilter và explicit save trong Spring Security 6

Với cấu hình Spring Security 6 dùng `SecurityContextHolderFilter`, filter **nạp** context từ `SecurityContextRepository` và thiết lập nó ở holder; các thành phần tự thực hiện authentication (custom filter/controller) muốn persist sang request khác cần gọi `saveContext(context, request, response)` qua repository phù hợp.

Mẫu minh họa **sau khi AuthenticationManager đã xác minh credential**:

```java
Authentication verified =
        authenticationManager.authenticate(authenticationRequest);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);
securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(
        context, httpRequest, httpResponse);
```

Đây là **mẫu tích hợp**, không phải class Java độc lập. `authenticationManager`, `authenticationRequest`, `httpRequest`, `httpResponse` và repository phải đến từ cấu hình/framework thực tế. Không gọi `saveContext` sau khi response đã commit hoặc trên request/response không đúng.

`SecurityContextPersistenceFilter` trong cấu hình cũ có hành vi tự lưu khi thích hợp; bản thân `setContext` không bảo đảm persistence ở mọi phiên bản. Framework form login/built-in filters thường xử lý lưu context theo cơ chế của chúng, nên không tự thêm một filter save tùy ý chồng lên chain.

### 9.2 Một request có nhiều dispatch

Servlet có thể có REQUEST, ERROR, FORWARD, ASYNC dispatch. Khi một error dispatch diễn ra sau khi thread-local đã bị dọn, `RequestAttributeSecurityContextRepository` giúp giữ context cho cùng request trong một số cấu hình. Điều đó khác với `HttpSessionSecurityContextRepository`, nơi context tồn tại qua **nhiều request** có cookie/session.

Không coi request attribute là giải pháp lưu người dùng đăng nhập sau khi browser đóng hoặc mở request mới. Cũng không giả định `SecurityContextHolderStrategy` tự hiểu lifecycle error/async dispatch.

### 9.3 Stateless không có nghĩa không có SecurityContext

Với JWT resource server stateless, mỗi request vẫn có một `Authentication`/`SecurityContext` trong execution hiện tại sau khi verify token. `NullSecurityContextRepository` có thể được chọn để **không persist giữa requests**, nhưng holder strategy vẫn cung cấp context trên thread đó. Request sau phải trình token lại và được kiểm tương ứng.

Cơ chế bearer JWT không mặc định gọi `UserDetailsService`, nên principal có thể là `Jwt` thay vì `UserDetails`. Nếu controller ép kiểu principal thành `UserDetails` mọi lúc, ứng dụng có thể lỗi dù holder strategy vận hành hoàn toàn đúng.

## 10. Servlet async: Callable, DeferredResult, @Async và thread pools

Cùng là “bất đồng bộ” nhưng mức tự tích hợp Spring Security khác nhau:

| Cách chạy | Tình trạng SecurityContext | Giải pháp |
| --- | --- | --- |
| Controller đồng bộ trong security filter chain | Context do filter/repository thiết lập cho request thread. | Dùng `Authentication` injected hoặc holder đúng chỗ. |
| Spring MVC controller trả `Callable<T>` | Spring Security MVC integration thường **tự truyền context** tới thread gọi Callable qua `WebAsyncManagerIntegrationFilter`. | Đảm bảo MVC/Security async integration có trong chain, test dispatch. |
| MVC `DeferredResult<T>` với task do ứng dụng tự chạy | **Không có tích hợp propagation tự động cho mọi task**. | Dùng DelegatingSecurityContext wrappers/Executor hoặc tường minh principal. |
| `@Async` trên Spring executor tùy biến | Task thường chạy thread khác, không tự nhận ThreadLocal. | `DelegatingSecurityContextAsyncTaskExecutor`/TaskDecorator phù hợp và cleanup. |
| `CompletableFuture.supplyAsync` mặc định | Có thể chạy common ForkJoinPool, không giữ context caller. | Truyền executor có context hoặc explicit trusted identity; không dùng global. |
| `ExecutorService.submit` | Workers được tái sử dụng; context không tự theo task. | `DelegatingSecurityContextExecutorService` hoặc bao Runnable/Callable. |
| Scheduler/job/background message | Có thể không còn HTTP request/principal hợp lệ. | Dùng service identity hoặc subject ID + kiểm quyền thời điểm chạy. |
| Reactive WebFlux / Reactor | Dùng Reactor `Context` và `ReactiveSecurityContextHolder`. | Không lấy ThreadLocal Servlet làm cơ chế chính. |

**Đặc biệt:** Spring Security có hỗ trợ tự động với `Callable` của Spring MVC, nhưng tài liệu nói **không tự tích hợp hoàn toàn với `DeferredResult`** vì task hoàn thành nó được ứng dụng điều phối. Không thể kết luận “Spring MVC async luôn mang SecurityContext”.

### 10.1 Ví dụ Servlet Callable (đoạn controller)

Trong một `@RestController` đã đi qua filter chain:

```java
@GetMapping("/api/callable-name")
public Callable<String> callableName() {
    return () -> {
        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();

        return current == null
                ? "(none)"
                : current.getName();
    };
}
```

Đoạn này cần Spring Web MVC và Spring Security Servlet, không thể chạy độc lập bằng `javac`. Với cấu hình MVC async chuẩn, `WebAsyncManagerIntegrationFilter` sẽ liên kết context hiện có với thread thực thi `Callable`. Hãy test cả request, async dispatch và lỗi/timeout theo security chain thực tế.

### 10.2 Ví dụ DeferredResult với executor đã bọc

Nếu app tự gửi công việc sang executor:

```java
private final Executor securityAwareExecutor;

// Trong constructor:
// securityAwareExecutor =
//     new DelegatingSecurityContextExecutor(rawExecutor);

@GetMapping("/api/deferred-name")
public DeferredResult<String> deferredName() {
    DeferredResult<String> result = new DeferredResult<>(5000L);

    securityAwareExecutor.execute(() -> {
        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        result.setResult(current == null
                ? "(none)"
                : current.getName());
    });

    return result;
}
```

Đoạn này là **một phần của controller**, không gồm đầy đủ imports/beans. `securityAwareExecutor` phải là executor được cấu hình đúng để capture context của caller tại thời điểm `execute(...)`. Cần xử lý timeout/cancel/errors, shutdown executor, async servlet dispatch và không giữ context sau khi task kết thúc.

### 10.3 Truyền identity cho background job có phải luôn đúng?

Không. Duy trì nguyên quyền Alice ở một job chạy nhiều giờ có thể gây *stale authority* nếu Alice bị thu hồi quyền hoặc đổi tenant. Với job durable, thường tốt hơn là:

- Ghi **account ID/tenant ID/action/request ID** đã kiểm, không serialize raw `SecurityContext` hoặc password.
- Ghi rõ policy về job chạy theo quyền của requester, service account hay quyền được phê duyệt.
- Kiểm lại account/membership và quyền trên tài nguyên tại thời điểm job thực hiện, hoặc dùng delegation grant có hạn và scope.
- Tránh tái sử dụng một `SecurityContext` mutable cho nhiều tasks chạy song song.
- Dọn/revoke sự kiện khi worker hoàn thành, thất bại hoặc retry.

Propagation là **bảo toàn một ngữ cảnh thực thi**, không phải thay thế authentication hoặc authorization.

## 11. Spring Boot 3.x: controller đọc principal đã được filter cung cấp

Ví dụ nhỏ sau cho thấy một servlet app dùng `MODE_THREADLOCAL` mặc định mà vẫn xác thực được user ở mỗi request. Vì dùng HTTP Basic, code **không tự cài strategy** hoặc lưu context toàn cục.

Cấu trúc:

```text
context-servlet-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ServletContextApplication.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'context-servlet-demo'
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
}
```

File `src/main/java/demo/ServletContextApplication.java`:

```java
package demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ServletContextApplication {

    public static void main(String[] args) {
        SpringApplication.run(ServletContextApplication.class, args);
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("READER")
                .build();

        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("different-local-password"))
                .roles("READER")
                .build();

        return new InMemoryUserDetailsManager(alice, bob);
    }

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

@RestController
class ContextController {

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        Authentication fromHolder =
                SecurityContextHolder.getContext().getAuthentication();

        return Map.of(
                "argumentName", authentication.getName(),
                "holderName", fromHolder.getName(),
                "authorities", authentication.getAuthorities().stream()
                        .map(a -> a.getAuthority())
                        .sorted()
                        .toList());
    }
}
```

Đây là app chạy độc lập nếu đã cài đúng hai starter; không phải chương trình chỉ có JDK. Nó cho thấy cùng request, Spring MVC inject `Authentication` và holder đọc cùng principal theo cấu hình bình thường. **Không dùng ví dụ này để kết luận mọi async executor hoặc request sau không cần xác thực**.

Chạy:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Gửi yêu cầu (chỉ localhost demo; với password thật phải dùng HTTPS):

```bash
curl -i http://localhost:8080/api/me
curl -i -u alice:local-demo-password http://localhost:8080/api/me
curl -i -u bob:different-local-password http://localhost:8080/api/me
```

Kết quả kỳ vọng:

| Yêu cầu | Trạng thái | Body/ý nghĩa |
| --- | --- | --- |
| Không cung cấp credential | HTTP 401 | Endpoint yêu cầu authenticated. |
| Alice + password đúng | HTTP 200 | `argumentName=alice` và `holderName=alice`; `ROLE_READER`. |
| Bob + password đúng | HTTP 200 | `argumentName=bob` và `holderName=bob`; `ROLE_READER`. |

Mỗi request đi qua filter/manager tương ứng và được đặt vào execution context riêng. Khi container dùng lại cùng physical thread, filter chain phải thiết lập và dọn context đúng; **không phải vì ThreadLocal tự có nhận thức về HTTP cookie hoặc user ID**.

## 12. Rò ngữ cảnh trong thread pool: hai lỗi hay gặp

### 12.1 Quên dọn sau task

```java
// SAI: minh họa một job tự quản lý scope không có finally.
executor.execute(() -> {
    SecurityContextHolder.setContext(contextOfAlice);
    processSomething();
    // Quên clearContext; pooled worker có thể chạy task của Bob tiếp.
});
```

Nếu worker được dùng lại, một task khác đọc `SecurityContextHolder` trước khi thiết lập context của riêng nó có thể nhìn thấy Alice. Đây là lỗi **cross-request/cross-user confusion**.

Đúng hơn, dùng `DelegatingSecurityContextRunnable`/`Executor`; hoặc khi tự viết adapter vì yêu cầu đặc biệt, có contract rõ về lưu/restore context và cleanup trong `finally`, test cả khi task ném exception.

### 12.2 Capture context ở sai thời điểm

```text
T0: App startup tạo SecurityContext cố định với service-admin.
T1: Alice gửi task đến Executor dùng context cố định đó.
T2: Bob gửi task tương tự.
T3: Cả Alice và Bob đều chạy dưới service-admin.
```

Dùng constructor `DelegatingSecurityContextExecutor(delegate, explicitContext)` khi **cố ý** chạy bằng service identity và đã thiết kế quyền riêng. Nếu muốn mỗi task dùng identity của caller, dùng constructor `DelegatingSecurityContextExecutor(delegate)` và để nó capture tại task submission.

Cần tránh chuyển một `Authentication` có credential/hash nhạy cảm tới task không cần nó. Với xử lý background dài, lưu context lâu khiến role snapshot stale, tăng rủi ro giữ bí mật trong memory và khó revoke.

## 13. Deferred loading, supplier và cái bẫy “giữ Supplier để dùng ở tương lai”

Spring Security 5.8+ có `getDeferredContext()` và `setDeferredContext(Supplier<SecurityContext>)` trên strategy. Chúng hỗ trợ cách **hoãn lấy `SecurityContext` tới khi cần**, nhất là khi repository không muốn truy xuất session nếu request không cần authentication.

Ví dụ khái niệm:

```java
SecurityContextHolderStrategy strategy =
        SecurityContextHolder.getContextHolderStrategy();

Supplier<SecurityContext> deferred =
        strategy.getDeferredContext();

// Khi có nhu cầu thực sự trong cùng lifecycle hợp lệ:
SecurityContext current = deferred.get();
```

**Không nhầm supplier với identity token bất biến.** Nó có thể phụ thuộc scope/repository/request/thread của thời điểm lấy và không được dùng tùy ý sau khi HTTP request đã kết thúc. Không serialize supplier vào queue, không giữ nó trong singleton/cache và không tự chuyển supplier sang worker thread rồi coi là propagation chính thức.

Nếu bạn cần capture identity cho task, dùng wrapper được Spring Security hỗ trợ hoặc một snapshot/principal đã được kiểm soát, kèm cleanup. Nếu muốn lưu login qua request sau, dùng `SecurityContextRepository.saveContext`, không dùng `setDeferredContext` như một “thay thế session”.

### 13.1 Khi tùy biến strategy, phải tôn trọng deferred API

Một implementation cũ chỉ nghĩ tới `getContext`/`setContext`/`clearContext` có thể bỏ qua hiệu năng hoặc semantics của deferred suppliers khi Spring Security component đã dùng `getDeferredContext`. Hãy đọc Javadoc chính xác của phiên bản, triển khai default/override đúng, thử request không truy cập authentication, error dispatch và async boundary.

Đừng đoán rằng một strategy dựa trên `ThreadLocal<SecurityContext>` là đủ nếu app sử dụng propagation/repository tích hợp có supplier. Tùy biến lõi bảo mật cần đầy đủ unit/integration tests, không thực hiện như một mẹo giải quyết null principal.

## 14. Giới hạn Servlet, @Async và Reactive stack

### 14.1 WebFlux không sử dụng ThreadLocal theo cách Servlet

Spring WebFlux/Reactor có mô hình bất đồng bộ, scheduler có thể đổi thread trong pipeline. `ReactiveSecurityContextHolder` đặt context trong **Reactor Context**; việc chỉ gọi `SecurityContextHolder.setStrategyName(MODE_INHERITABLETHREADLOCAL)` không thay thế reactive context propagation.

Đừng copy controller Servlet sang Reactor `Mono/Flux` rồi giả định `SecurityContextHolder.getContext()` luôn có principal. Dùng APIs của `ReactiveSecurityContextHolder`, `ReactiveSecurityContextRepository` và các toán tử thích hợp với pipeline. Bài này không triển khai reactive authentication vì trọng tâm là Servlet.

### 14.2 Virtual threads không làm lỗi scope tự biến mất

Java 21+ có virtual threads, nhưng ứng dụng minh họa chạy Java 17. Dù là platform thread hay virtual thread, bạn vẫn phải xác định **lifetime và ownership** của context, nơi chuyển execution và cách cleanup. Không đổi `MODE_GLOBAL` chỉ vì ứng dụng dùng virtual threads.

### 14.3 Multi-tenant và principal

Hai người dùng thuộc hai tenant có thể có cùng username. Strategy không phải nơi chọn tenant. Principal đã xác thực cần mang account/tenant ID từ nguồn tin cậy, còn authorization/query phải scoped theo tenant và resource. Một ThreadLocal bị rò có thể làm service tưởng request của tenant B thuộc tenant A — vì thế cleanup và test cross-tenant đặc biệt quan trọng.

### 14.4 Session/JWT không tự cập nhật authorities

Propagation giữ một instance `SecurityContext`/`Authentication` có thể là **snapshot** lúc login. Nếu account disabled, role bị thu hồi hoặc membership tenant thay đổi, thread/task đang giữ context không tự nạp trạng thái mới. Cần session/token revocation, auth version/freshness hoặc authorization live theo chính sách; đây là một giới hạn **khác** với câu hỏi chiến lược lưu theo thread.

## 15. Ma trận kiểm thử quan trọng

| Tình huống | Kết quả cần khẳng định |
| --- | --- |
| Mặc định MODE_THREADLOCAL | Hai thread độc lập không tự thấy cùng security context. |
| Request Alice và Bob xen kẽ trên pool | Mỗi request đọc đúng principal; không rò Alice sang Bob. |
| Controller đồng bộ | `Authentication` injected và holder phù hợp sau filter authentication. |
| Raw Executor task từ Alice | Không có Alice tự động trên worker khi không propagation. |
| Wrapped Runnable từ Alice | Worker thấy Alice **trong scope**; task sau không còn Alice. |
| Wrapped task ném exception | Context worker được dọn ngay cả khi exception xảy ra. |
| Executor cố định context admin | Chỉ dùng khi có ý định/authorization; caller Alice/Bob không vô tình thành admin. |
| InheritableThreadLocal + new Thread | Child có thể thấy parent tại thời điểm thread tạo; parent/child ownership được test. |
| InheritableThreadLocal + pooled Executor | Không phụ thuộc inheritance theo submission; không được rò user cũ. |
| MODE_GLOBAL trên server | Không được bật; test cấu hình đảm bảo server dùng strategy thích hợp. |
| Custom strategy | `getContext` không null, `clearContext` thật sự dọn association, deferred API đúng. |
| Form login + HttpSession | Context được save/reload qua request dù thread vật lý thay đổi. |
| Custom authentication không save | Request sau không chắc có login; phải gọi repository đúng. |
| NullSecurityContextRepository | Không persist giữa requests; vẫn có context trong request đã xác thực. |
| ERROR/ASYNC dispatch | Request attribute/repository + async integration giữ context theo cấu hình. |
| MVC Callable | Context có thể được propagate tự động bởi integration filter. |
| MVC DeferredResult tự submit task | Cần executor/wrapper; không mặc định truyền từ mọi nguồn. |
| @Async / CompletableFuture common pool | Không đọc user caller nếu không có propagation hợp lệ. |
| Logout | clearContext không được coi là revoke mọi session/token. |
| Role bị thu hồi khi task đang chờ | Authorization/freshness được kiểm tại thời điểm thực thi nếu policy yêu cầu. |
| JWT/OIDC principal | Không ép kiểu mọi principal thành `UserDetails`. |
| WebFlux pipeline | Sử dụng ReactiveSecurityContextHolder, không dựa vào servlet ThreadLocal. |

Đối với kiểm thử concurrent, nên dùng `CountDownLatch`/`CyclicBarrier` để buộc hai user xen kẽ thay vì chỉ test tuần tự. Đồng thời test cleanup khi exception, timeout, cancel và restart các worker. Test “không leak principal” quan trọng không kém test “principal được propagate”.

## 16. Lỗi phổ biến và checklist debug

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Trong controller có principal, trong `CompletableFuture` thấy null | Task chạy thread khác với MODE_THREADLOCAL. | Dùng security-aware executor hoặc truyền identity tường minh; không bật GLOBAL. |
| `@Async` đôi khi thấy user khác | Thread pool giữ context sót hoặc inheritance capture lúc thread tạo. | Cleanup trong finally, dùng delegating executor/TaskDecorator chuẩn, test xen kẽ users. |
| Đã login nhưng request kế tiếp anonymous | Custom authentication chỉ `setContext` mà chưa `saveContext` vào repository, hoặc policy stateless. | Kiểm SecurityContextHolderFilter/Repository, session cookie và explicit save. |
| Logout xong vẫn thấy session cũ | Chỉ clearContext trên thread hoặc không invalidate session/server token. | Dùng logout handlers/repository/session invalidation và token revoke theo policy. |
| MODE_GLOBAL làm user B nhận quyền A | Một context JVM-wide chia sẻ qua requests. | Không dùng GLOBAL trong Servlet server. |
| Inheritable hoạt động với new Thread nhưng lỗi trên pool | Inheritance chỉ lúc tạo thread, không theo mỗi task. | Dùng DelegatingSecurityContextExecutor/Callable phù hợp. |
| Đã dùng wrapper nhưng task thấy role cũ | Context được capture trước role change; snapshot không tự refresh. | Thực thi reauthorization/freshness check theo policy. |
| ThreadLocal không rò ở unit test nhưng rò production | Test không reuse threads, không có exception/timeout. | Stress test pool, reuse worker, exception cleanup, mixed principals. |
| Dùng `getContext().setAuthentication` làm session B đổi theo A | Mutate context instance có thể được chia sẻ. | Tạo context mới và xác định ownership/persistence. |
| Hệ thống reactive thiếu principal | Cố dùng Servlet ThreadLocal trong Reactor pipeline. | Dùng ReactiveSecurityContextHolder/Reactor Context. |
| Filter chain custom không thấy principal | Strategy/repository khác nhau, filter order sai, auth chưa xong. | Kiểm đúng filter/manager, getContextHolderStrategy và save lifecycle. |
| Có context nhưng `getAuthentication()==null` | Context rỗng, chưa xác thực hoặc bị clear. | Kiểm nơi authentication được đặt, anonymous handling và pipeline. |
| SecurityContextHolder.getInitializeCount tăng bất thường | Có code thay strategy nhiều lần. | Loại việc đổi strategy trong request/test lẫn vào runtime, cấu hình một lần lúc startup. |

### Trình tự debug an toàn

1. Request đã qua đúng `SecurityFilterChain` và được authentication bởi provider nào?
2. `SecurityContextHolderStrategy` hiện là gì? Có ai gọi `setStrategyName`/`setContextHolderStrategy` khi app đang chạy không?
3. `Authentication` có tồn tại **trên thread đang thực thi**? Đừng chỉ nhìn thread khác trong debugger.
4. Nếu async, executor/Callable/DeferredResult nào tạo thread? Context được capture **lúc nào**?
5. Task có dọn context trong `finally`, kể cả khi exception/timeout?
6. Nếu qua request mới, `SecurityContextRepository` là loại nào, đã `saveContext` và có session/token thật chưa?
7. Có thay quyền/trạng thái sau login? Context snapshot còn đúng policy không?
8. Với nhiều người/tenant, có trộn identity do pool, cache hoặc global mode?
9. Logs có đang ghi raw `Authentication`, credentials, cookie, JWT hoặc password hash không? Phải lọc.

Không log nguyên `SecurityContext` hoặc `Authentication` để debug trên production. Thông tin đủ thường là request ID, loại filter/strategy, thread ID (không thay user ID), account ID đã được kiểm, loại principal và outcome đã chuẩn hóa.

## 17. Bài tập có đáp án

**Câu 1.** Một controller đọc được Alice. Một `CompletableFuture.supplyAsync(...)` dùng common pool đọc `SecurityContextHolder` lại thấy authentication `null`. Vì sao?

**Đáp án:** Với `MODE_THREADLOCAL`, worker thread có slot context riêng, không tự kế thừa của request thread. Dùng executor/wrapper có security context propagation phù hợp hoặc truyền subject ID đã xác thực rồi reauthorize ở nơi chạy.

**Câu 2.** Vì sao không bật `MODE_GLOBAL` để mọi thread nhìn thấy principal?

**Đáp án:** Global dùng một context chung trên JVM; nhiều người dùng concurrent có thể overwrite/nhìn thấy identity của nhau. Đây là rủi ro cross-user/cross-tenant, không dùng cho Servlet server nhiều user.

**Câu 3.** `MODE_INHERITABLETHREADLOCAL` đã giúp `new Thread(...)` đọc user. Tại sao submit vào `ExecutorService` vẫn sai?

**Đáp án:** Inheritance xảy ra khi worker thread **được tạo**, không phải lúc `submit`. Worker trong pool tái sử dụng có thể thừa hưởng từ thời điểm cũ hoặc không có context, làm sai scope. Dùng delegating executor.

**Câu 4.** Một task set context của Alice trên pooled worker rồi quên clear. Request của Bob sau đó dùng cùng worker sẽ ra sao?

**Đáp án:** Nếu không có filter/wrapper nào thiết lập và dọn đúng, task của Bob có thể đọc danh tính Alice. Phải enforce cleanup trong `finally` và test worker reuse.

**Câu 5.** `SecurityContextHolder.setContext(...)` có tự giúp login tồn tại ở request sau không?

**Đáp án:** Không. Holder strategy quản lý execution scope, không persist qua HTTP requests. Khi dùng Spring Security 6 custom authentication, cần save vào `SecurityContextRepository` nếu policy yêu cầu stateful login.

**Câu 6.** `RequestAttributeSecurityContextRepository` và `HttpSessionSecurityContextRepository` khác nhau ở đâu?

**Đáp án:** Request attribute giữ ngữ cảnh trong một request qua một số dispatch; HttpSession gắn context với session để request khác dùng session cookie có thể nạp lại. Cả hai độc lập với chọn ThreadLocal hay InheritableThreadLocal.

**Câu 7.** `clearContext()` được gọi trong controller. Có thể nói người dùng đã logout khỏi mọi thiết bị không?

**Đáp án:** Không. Nó xóa association hiện tại, không tự invalidate phiên khác, revoke JWT/refresh tokens hay session store. Cần cơ chế logout/revocation thích hợp.

**Câu 8.** Một `DelegatingSecurityContextExecutor` được tạo với explicit context `ROLE_SUPERADMIN` ở startup. User bình thường submit task. Có thể xảy ra điều gì?

**Đáp án:** Task có thể chạy dưới cùng context cố định có quyền cao. Chỉ dùng cố định khi có thiết kế service identity được phép; với per-user tasks, dùng wrapper capture context tại submission và reauthorize khi cần.

**Câu 9.** Spring MVC `Callable` và `DeferredResult` có cùng mức tự propagate context không?

**Đáp án:** Không. Spring Security có MVC integration cho `Callable`. Với `DeferredResult` được một worker tự hoàn tất, không có auto integration bao trùm tất cả task; cần security-aware executor/wrapper hoặc explicit identity.

**Câu 10.** Một JWT đã được verify trong servlet request, `SecurityContextHolder` trả principal `Jwt`. Code ép `(UserDetails) authentication.getPrincipal()` có chắc đúng?

**Đáp án:** Không. Principal phụ thuộc authentication mechanism. Dùng `Authentication.getName()` hoặc adapter type-safe và policy tương ứng; holder chỉ cung cấp context, không chuẩn hóa mọi principal thành UserDetails.

**Câu 11.** Admin thu hồi `ROLE_MANAGER` sau khi task đã được capture với quyền đó. Wrapper có tự lấy role mới không?

**Đáp án:** Không. Wrapper truyền context hiện có, không mặc định query store lại. Với job nhạy cảm, kiểm account/membership/authorization hiện hành tại điểm thao tác, hoặc sử dụng expiry/revocation policy.

**Câu 12.** Tại sao nên dùng `createEmptyContext()` khi tạo authentication mới?

**Đáp án:** Để có một `SecurityContext` mới với ownership rõ ràng, tránh mutate instance có thể đã được chia sẻ bởi session/repository/thread khác. Tuy nhiên phải save đúng vào repository nếu muốn giữ qua request.

## 18. Checklist thiết kế production

1. **Giữ mode mặc định:** Servlet server nhiều user dùng `MODE_THREADLOCAL` trừ khi có lý do được review rất kỹ.
2. **Một lần cấu hình:** Không đổi JVM-wide holder strategy trong controller, filter hoặc sau khi threads đang chạy.
3. **Scope rõ:** Filter/request/task có lifecycle tạo, đặt, dọn và restore thích hợp; cleanup khi exception.
4. **Không trộn responsibilities:** HolderStrategy quản lý execution association; repository quản lý persistence; provider quản lý authentication.
5. **Async toàn diện:** Audit `@Async`, `CompletableFuture`, `ExecutorService`, MVC `Callable`, `DeferredResult`, scheduler và message workers.
6. **Truyền có giới hạn:** Per-user task dùng wrapper/capture tại submit; service account context cố định chỉ khi chủ ý, không đặt role cao cho mọi job.
7. **Identity tối thiểu:** Context/principal không giữ raw password, không serialize secrets; dùng account/tenant ID từ nguồn đã xác minh.
8. **Chống stale:** Propagation không thay kiểm authorization; có chính sách role/account status freshness và token/session revocation.
9. **Servlet persistence:** Khi custom login cần stateful, gọi `SecurityContextRepository.saveContext` đúng lifecycle Spring Security 6.
10. **Stateless rõ:** Dùng repo/chains phù hợp; mỗi request JWT/Basic vẫn cần authentication, không giả định ThreadLocal giữ login sang lần sau.
11. **Kiểm concurrency:** Chạy thử Alice/Bob xen kẽ, thread-pool reuse, exception, async dispatch, cancel, timeout, nhiều tenant.
12. **Khác Reactive:** WebFlux dùng Reactor Context; không sao chép ThreadLocal strategy từ Servlet.
13. **Giám sát:** Log metadata đã lọc, phát hiện reinitialize strategy bất thường, lỗi thiếu principal và dấu hiệu cross-user exposure.
14. **Đánh giá an ninh:** Nếu có custom strategy hoặc context propagation mới, review thread-safety và quyền theo task/resource.

## 19. Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, default ThreadLocal, các holder strategy và vòng đời filter.
- [Spring Security 6.5 — SecurityContextHolder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html): `MODE_THREADLOCAL`, `MODE_INHERITABLETHREADLOCAL`, `MODE_GLOBAL`, `getInitializeCount`, `setStrategyName`, `getDeferredContext`.
- [Spring Security 6.5 — SecurityContextHolderStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolderStrategy.html): `get/set/clear/createEmptyContext` và supplier API.
- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và các wrappers có kiểm soát.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository`, `HttpSessionSecurityContextRepository`, `RequestAttributeSecurityContextRepository`, `NullSecurityContextRepository` và holder filter.
- [Spring Security 6.5 — Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): explicit save, `SecurityContextHolderFilter` và session lifecycle.
- [Spring Security 6.5 — Spring MVC Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): `@AuthenticationPrincipal`, `Callable` propagation và `DeferredResult` limitation.
- [Spring Security 6.5 — WebAsyncManagerIntegrationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/context/request/async/WebAsyncManagerIntegrationFilter.html): tích hợp SecurityContext với MVC Callable.
- [Spring Security — Reactive SecurityContextHolder](https://docs.spring.io/spring-security/reference/reactive/authentication/architecture.html): khác biệt Reactor Context với Servlet ThreadLocal.

**Ghi nhớ:** `SecurityContextHolderStrategy` quyết định **context gắn với execution hiện tại như thế nào**, chứ không xác thực người dùng và không lưu phiên qua HTTP request. Trong Servlet server, **MODE_THREADLOCAL + filter cleanup** là mặc định an toàn; khi chuyển thread, truyền identity đúng từng task bằng công cụ được hỗ trợ; khi chuyển request, dùng `SecurityContextRepository`/session/token phù hợp. Không dùng `MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` để “vá” null principal trên thread pool, vì khả năng rò quyền giữa người dùng nghiêm trọng hơn lỗi thiếu context ban đầu.