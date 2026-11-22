# ThreadLocal và yêu cầu dọn ngữ cảnh để tránh rò rỉ danh tính

> **Điểm cốt lõi:** Trong ứng dụng Spring Security dựa trên **Servlet**, `SecurityContextHolder` mặc định giữ `SecurityContext` bằng `ThreadLocal`. Nhờ đó, code trên **cùng thread xử lý request** có thể đọc `Authentication` hiện tại mà không cần truyền tham số qua từng method. Nhưng **thread của servlet container và thread pool được tái sử dụng**. Nếu code tự đặt danh tính vào `SecurityContextHolder` rồi **không dọn trong `finally`**, request/tác vụ tiếp theo dùng lại thread đó có thể nhìn thấy danh tính hoặc quyền của người trước — một dạng **rò rỉ ngữ cảnh bảo mật, có thể gây leo thang quyền và lộ dữ liệu chéo người dùng**. Spring Security filter chain thông thường quản lý và dọn context ở cuối request; code tự tạo thread, custom filter, custom authentication và background executor cần tuân thủ vòng đời tương ứng.

Bài thuộc nhóm **Ngữ cảnh bảo mật** trong module **Spring Security – fundamentals**. Ví dụ dùng **Java 17+, Spring Boot 3.5.16 và Spring Security 6.5.x, Spring MVC/Servlet**. Với **Spring WebFlux**, context được truyền qua **Reactor Context** và `ReactiveSecurityContextHolder`, không áp dụng ThreadLocal Servlet như mặc định. Các ví dụ tự tạo authentication trong unit test chỉ nhằm chứng minh cách giữ/dọn context, **không phải cách login người dùng thật**.

## 1. Mục tiêu học tập

Kết thúc bài, bạn có thể:

1. Giải thích `ThreadLocal` trong Java và vì sao một biến “gắn với thread” không phải biến “gắn với request” hoặc “gắn với user”.
2. Phân biệt `SecurityContextHolder`, `SecurityContext`, `Authentication`, `SecurityContextRepository` và `HttpSession`.
3. Mô tả filter nạp context ở đầu request và cơ chế dọn ở cuối request, kể cả khi handler ném exception.
4. Chỉ ra lỗi nghiêm trọng khi một `ExecutorService` một thread chạy tác vụ của Alice rồi Bob và dữ liệu `ThreadLocal` từ Alice còn sót lại.
5. Viết mẫu `try/finally` để dọn ngữ cảnh đúng, không phụ thuộc đường xử lý thành công.
6. Biết vì sao `SecurityContextHolder.clearContext()` khác việc xóa session hoặc logout.
7. Sử dụng `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và các wrapper tương ứng để **truyền context theo tác vụ** và **khôi phục/dọn** khi task kết thúc.
8. Biết giới hạn của `MODE_INHERITABLETHREADLOCAL`, `MODE_GLOBAL`, `@Async` và `CompletableFuture` không cấu hình executor bảo mật.
9. Viết bài test kiểm tra request liên tiếp khác danh tính, thread-pool cleanup, đường exception, và không tự lan identity sang background task.
10. Áp dụng checklist khi review custom filter, custom login, thread pool, scheduled tasks, audit và reactive code.

## 2. ThreadLocal của Java hoạt động như thế nào?

`ThreadLocal<T>` tạo một điểm truy cập tới **giá trị riêng của từng thread**, không tạo “bộ nhớ riêng cho user”. Hai thread khác nhau có thể đọc hai giá trị khác nhau thông qua cùng một biến `ThreadLocal`. Nếu một thread được dùng lại, giá trị của nó vẫn còn trừ khi được thay hoặc xóa.

### 2.1. Ví dụ Java độc lập, không cần Spring

Tạo file `ThreadLocalDemo.java`:

```java
public class ThreadLocalDemo {
    private static final ThreadLocal<String> CURRENT =
        new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        Thread worker = new Thread(() -> {
            try {
                CURRENT.set("alice");
                System.out.println("worker=" + CURRENT.get());
            } finally {
                CURRENT.remove();
            }
            System.out.println("worker-after=" + CURRENT.get());
        }, "demo-worker");

        worker.start();
        worker.join();

        System.out.println("main=" + CURRENT.get());
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac ThreadLocalDemo.java
java ThreadLocalDemo
```

**Stdout kỳ vọng chính xác:**

```text
worker=alice
worker-after=null
main=null
```

Giải thích:

- `CURRENT.set("alice")` chỉ đặt giá trị trong **thread worker**.
- `CURRENT.get()` của main vẫn null; ThreadLocal không phải biến global dùng chung.
- `CURRENT.remove()` xóa mapping của worker; nó không tự xóa một “user session” nào.
- `finally` đảm bảo cleanup vẫn được gọi nếu code trong `try` throw exception.
- Ví dụ tạo mới thread rồi kết thúc, nhưng trong **thread pool** một thread sống lâu và thực thi nhiều task, nên xóa dữ liệu càng quan trọng.

### 2.2. Rủi ro khi thread pool tái sử dụng thread

```text
ExecutorService một worker thread tên pool-1-thread-1

Task #1 (Alice)
  CURRENT.set("alice")
  xử lý
  KHÔNG remove()    <-- BUG
  return

Task #2 (Bob/anonymous) trên CÙNG thread
  CURRENT.get() -> "alice"    <-- RÒ RỈ danh tính

Task #3 (Charlie)
  thậm chí có thể kế thừa dữ liệu sai nếu không khởi tạo/clear
```

Đây là cơ chế cốt lõi cần hiểu, không nhất thiết do Spring Security mắc lỗi: **code tùy chỉnh ngoài lifecycle filter** có thể giữ giá trị cũ trên worker thread. Một đối tượng thread có thể phục vụ rất nhiều request trong servlet container; không được coi thread ID là session ID hoặc user ID.

### 2.3. Hai kiểu lỗi khác nhau

- **Không truyền context:** Alice submit background task vào executor khác thread, task thấy `Authentication` null và từ chối quyền hoặc không biết actor. Đây thường là lỗi chức năng và có thể che lấp bug phân quyền.
- **Truyền hoặc tạo context rồi không dọn:** Task của Alice còn lưu authenticated principal khi thread được tái sử dụng cho Bob. Đây có thể là **lỗ hổng rò rỉ danh tính xuyên tác vụ**, nghiêm trọng hơn lỗi không truyền.

Cách giải quyết **không phải** bật một context dùng chung toàn JVM, mà là **truyền danh tính có chủ đích cho đúng task và dọn/khôi phục sau task**.

## 3. SecurityContextHolder là ai trong Spring Security?

### 3.1. Ba đối tượng liên quan

```text
SecurityContextHolder
    |
    |  dùng SecurityContextHolderStrategy (mặc định ThreadLocal)
    v
SecurityContext
    |
    +-- Authentication
           |
           +-- principal      (danh tính đang được tin cậy)
           +-- authorities    (role/permission)
           +-- credentials    (thường được xóa sau khi auth)
           +-- details        (metadata nếu có)
```

`SecurityContextHolder` là API tĩnh để truy cập context theo strategy. `SecurityContext` chứa một `Authentication`. `Authentication` đại diện input chưa xác thực hoặc kết quả xác thực đáng tin, tùy chỗ sử dụng; ở controller sau filter, ta thường làm việc với kết quả đã xác thực hoặc anonymous token.

Các API thường dùng:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext context = SecurityContextHolder.getContext();
Authentication current = context.getAuthentication();

SecurityContext newContext = SecurityContextHolder.createEmptyContext();
newContext.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(newContext);

// Khi tự quản lý một scope:
SecurityContextHolder.clearContext();
```

Đây là **snippet**; `verifiedAuthentication` phải do cơ chế xác thực đáng tin tạo ra. Không lấy username/roles từ JSON request rồi gọi factory `authenticated(...)` để tự phong user trước authorization.

### 3.2. getContext() có phải null khi anonymous?

Thông thường **không**. `SecurityContextHolder.getContext()` có thể trả một context rỗng thay vì null, còn `context.getAuthentication()` có thể null khi chưa có principal. Trong Spring Security filter chain thông thường, `AnonymousAuthenticationFilter` còn có thể thiết lập `AnonymousAuthenticationToken`. Token anonymous có thể trả `isAuthenticated()==true` về mặt interface, nhưng **không đại diện user đã login**.

Vì thế:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // CHƯA ĐỦ để kết luận đã login bằng credential thực.
}
```

Đoạn trên là phản ví dụ để học. Ở HTTP boundary, sử dụng rule `authenticated()`, `fullyAuthenticated()`, `hasRole(...)`, `hasAuthority(...)` của Spring Security; nếu code cần phân biệt anonymous, dùng `AuthenticationTrustResolver` hoặc cơ chế policy tương ứng. Đừng lấy “token có cờ true” làm proof về actor đủ quyền.

### 3.3. getName() ở thread hiện tại chưa phải quyền trên dữ liệu

Một request đã xác thực Alice có thể đọc `auth.getName()=="alice"`. Điều đó chỉ giúp xác định identity. Khi Alice yêu cầu `GET /accounts/bob/invoices`, service vẫn phải kiểm owner/tenant, trạng thái và permissions trên resource. **Xóa ThreadLocal đúng không thay thế object-level authorization**.

## 4. Vì sao SecurityContextHolder dùng ThreadLocal theo mặc định?

Trong ứng dụng Servlet cổ điển, request đi vào container thread rồi qua filter/controller/service. Dùng ThreadLocal cho phép các lớp sâu lấy principal mà không cần truyền `Authentication` qua mọi tham số method.

```text
Thread A (servlet worker)
  |
  +-- Security filter: load/initialize SecurityContext(Alice)
  |     |
  |     +-- AuthorizationFilter: đọc Alice
  |     +-- Controller: đọc Alice
  |     +-- Service: đọc Alice nếu cần
  |     |
  |     +-- finally: clear context của Thread A
  |
  +-- có thể phục vụ request khác sau đó

Thread B (servlet worker khác)
  |
  +-- Security filter: load/initialize SecurityContext(Bob)
  |     |
  |     +-- Controller: đọc Bob
  |     |
  |     +-- finally: clear context của Thread B
```

Lợi ích là API thống nhất để đọc danh tính trong request. Cái giá phải trả là vòng đời gắn với thread, trong khi thread thường được tái sử dụng.

**Quan trọng:** “thread có context” không nghĩa “mọi xử lý request chạy trên một thread”. Servlet asynchronous processing, `@Async`, `CompletableFuture`, scheduled jobs, messaging listeners và reactive streams có thể chuyển execution context. Phải hiểu integration cụ thể thay vì mong ThreadLocal tự đồng hành với logical request.

### 4.1. Các strategy của SecurityContextHolder

| Strategy | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `MODE_THREADLOCAL` | Mỗi thread có SecurityContext riêng; mặc định phổ biến | Phải dọn khi kết thúc scope; context không tự đi sang thread khác |
| `MODE_INHERITABLETHREADLOCAL` | Child thread mới có thể nhận tham chiếu context ở thời điểm tạo thread | Rất dễ sai với thread pool, lifecycle và dữ liệu mutable; **không dùng làm giải pháp mặc định cho @Async** |
| `MODE_GLOBAL` | Context dùng chung trong JVM | **Không an toàn cho server nhiều user**; dành cho trường hợp đặc biệt không phải web multi-user |
| Custom `SecurityContextHolderStrategy` | Cách lưu/đọc khác theo kiến trúc | Cần thiết kế và kiểm thử riêng, không dùng chỉ để tránh viết cleanup |

Không nên gọi `SecurityContextHolder.setStrategyName(...)` giữa lúc server đang phục vụ request. Đây là một thiết lập có ảnh hưởng toàn JVM; thay strategy trong runtime có thể gây lỗi/rò rỉ bất ngờ và làm test của module khác sai. Thông thường giữ `MODE_THREADLOCAL` mặc định.

## 5. Spring Security dọn context ở đâu trong một HTTP request?

### 5.1. Vòng đời Servlet

Với Spring Security 6.x, một filter quan trọng là `SecurityContextHolderFilter`. Nó nạp/defer nạp `SecurityContext` thông qua `SecurityContextRepository`, làm context khả dụng trong `SecurityContextHolder` ở phạm vi xử lý request, rồi **dọn ngữ cảnh khỏi holder khi thoát**. Spring Security cũng có mô hình lịch sử `SecurityContextPersistenceFilter`, nhưng không được cài cả hai cùng lúc.

```text
HTTP request
    |
    v
DelegatingFilterProxy(springSecurityFilterChain)
    |
    v
FilterChainProxy
    |
    v
SecurityContextHolderFilter
    |
    +-- SecurityContextRepository.load/deferred context
    +-- cung cấp SecurityContext cho current thread
    |
    v
Authentication Filters -> Authorization -> Controller
    |
    +-- return bình thường
    |      hoặc
    +-- exception/redirect/error
    |
    v
finally trong lifecycle filter
    |
    +-- SecurityContextHolder.clearContext()
    |
    v
HTTP response / thread trở lại container pool
```

Không hiểu nhầm sơ đồ như thứ tự chính xác của **mọi filter** trong mọi `SecurityFilterChain`; thứ tự filter còn phụ thuộc cấu hình. Ý nghĩa bảo mật là **scope của thread phải được dọn kể cả khi downstream fail**.

Tài liệu Spring Security cũng nhấn mạnh `FilterChainProxy` đảm bảo việc dọn `SecurityContext` trong luồng web chuẩn. Khi phát hiện context còn sót ở **custom pool ngoài filter chain** thì không nên ngay lập tức quy lỗi cho Spring Security.

### 5.2. Dọn sau request khác với persist cho request sau

Bảng phân biệt:

| Hành động | API/thành phần | Mục đích |
| --- | --- | --- |
| Đặt danh tính trong request hiện tại | `SecurityContextHolder.setContext(context)` | Code trong scope có thể đọc |
| Dọn danh tính khỏi thread hiện tại | `SecurityContextHolder.clearContext()` | Không rò rỉ sang scope tiếp theo trên cùng thread |
| Lưu để request HTTP khác khôi phục | `SecurityContextRepository.saveContext(...)` | Session hoặc storage khác tùy policy |
| Nạp lại context khi request mới đến | `SecurityContextHolderFilter` và repository | Xác định current user của request mới |
| Kết thúc session/logout | `LogoutFilter`, logout handlers, repository/session | Không còn authenticated session |
| Xóa user hoặc đổi password trong database | Domain account service | Cập nhật credential/account, cần revoke riêng khi thích hợp |

**Thí dụ:** Khi Alice đăng nhập bằng form login, security context có thể được lưu trong HTTP session. Cuối request, framework **vẫn dọn ThreadLocal**. Request sau mang cookie session sẽ **nạp lại** context đã lưu. Không có mâu thuẫn: dọn thread không xóa session, còn giữ session không có nghĩa ThreadLocal sống mãi.

### 5.3. Spring Security 6 và explicit save

Trong Spring Security 6, `SecurityContextHolderFilter` thường chỉ **nạp** context, không tự lưu mọi thay đổi. Nếu bạn **tự viết custom login controller/filter** và muốn authentication tồn tại qua các request, ngoài việc set holder còn phải gọi `SecurityContextRepository.saveContext(context, request, response)` ở thời điểm phù hợp, trước khi response commit.

Điều này **khác** trách nhiệm cleanup:

- `saveContext` giải quyết **persistence**.
- `clearContext` giải quyết **không rò rỉ danh tính giữa các lần dùng thread**.
- Gọi `saveContext` không thay `clearContext`.
- Gọi `clearContext` không tự xóa authentication đã lưu trong session.

Với form login/OAuth2 filters tiêu chuẩn, Spring Security đã thiết kế việc save/context lifecycle theo cơ chế đó. Không cần chèn `clearContext()` giữa controller xử lý request bình thường chỉ vì muốn bảo mật “hơn”; làm vậy có thể xóa current authentication quá sớm.

### 5.4. Ngoại lệ và redirect

`finally` phải chạy dù handler:

- Trả status `200` hay `403`.
- Ném exception rồi framework chuyển sang exception handler.
- Đưa browser tới `302` redirect sau login.
- Bị dừng bởi authentication/authorization filter.
- Gặp timeout/cancellation theo flow mà wrapper thực thi.

Nếu custom code có:

```java
SecurityContextHolder.setContext(context);
doBusinessWork();                      // throw exception
SecurityContextHolder.clearContext();  // KHÔNG ĐƯỢC GỌI
```

thì cleanup có thể bị bỏ qua. Mẫu đúng khi **bạn là chủ scope**:

```java
SecurityContextHolder.setContext(context);
try {
    doBusinessWork();
} finally {
    SecurityContextHolder.clearContext();
}
```

Đây là snippet nguyên tắc, không phải custom login endpoint hoàn chỉnh. Khi chạy trong chính một Servlet request đã có filter quản lý context, **không** tự đặt/thay context tùy tiện rồi dọn ở giữa luồng request. Dùng các API Spring Security và phân quyền đúng lifecycle.

## 6. Rò rỉ danh tính có thể xảy ra theo cơ chế nào?

### 6.1. Thread reuse + stale SecurityContext

Giả sử ứng dụng tự tạo worker pool để xử lý import tài liệu:

```text
Pool worker P (reused)

10:00  Task của Alice
       create/set SecurityContext(Alice)
       xử lý file A
       QUÊN clearContext()

10:01  Task của Bob
       không tạo context mới vì tin rằng đã có sẵn
       đọc SecurityContextHolder
       thấy Authentication(Alice)  <-- identity leak
       ghi audit sai actor / đọc nhầm dữ liệu Alice

10:02  Task anonymous
       có thể tiếp tục thấy Authentication(Alice)
```

Mức độ hậu quả tùy vào việc business code tin context tới đâu. Nó có thể gây ghi audit sai, truy cập dữ liệu chéo tenant, thực thi thao tác với authority không thuộc requester hoặc rò PII. Không dùng “thấy username ở log” làm bằng chứng duy nhất: cần kiểm tra authorization thực tế và các vùng dữ liệu có thể bị đọc/ghi.

### 6.2. Custom filter ở sai vị trí

Một `Filter` không nằm trong phạm vi Spring Security filter chain, hoặc chạy theo dispatcher/async path khác, có thể tự đặt context rồi quên dọn. Đặc biệt cần xem:

- Filter chạy **trước** `DelegatingFilterProxy` hay không, có set context sớm không?
- Custom authentication filter có dùng `SecurityContextHolderStrategy`/`SecurityContextRepository` đúng không?
- Nó có bao bọc `chain.doFilter(...)` trong `try/finally` khi **chính nó** set context ngoài scope được framework quản lý không?
- Có bảo đảm không chạy hai lần khiến context bị ghi đè/clear sai ở nested dispatch không?
- Nó có bỏ qua một số request/URL khiến dữ liệu của worker thread còn sót không?
- Có xử lý thread dispatch khác nhau cho ERROR/ASYNC không?

Đừng “sửa” bằng cách xóa tất cả filter hoặc bật `permitAll()`; phải tìm điểm đang sở hữu lifecycle của context.

### 6.3. Custom login sai

Một controller tự gọi `AuthenticationManager.authenticate(...)` rồi set authentication vào holder, nhưng:

- Không dùng `SecurityContextRepository.saveContext(...)` khi cần session login.
- Không xử lý session fixation/CSRF/exception/success/failure đúng.
- Không dọn context trong code chạy ngoài filter hoặc dọn nhầm khi filter còn cần auth.

Tùy lỗi, người dùng có thể mất login ngay request sau hoặc identity leak qua scope không được quản lý. Với mục tiêu học, dùng filter login tiêu chuẩn của Spring Security trước; chỉ tự viết khi có lý do và test đầy đủ.

### 6.4. Biến static/singleton chứa current Authentication

```java
// PHẢN VÍ DỤ NGUY HIỂM — KHÔNG DÙNG.
class CurrentActorCache {
    static Authentication currentUser;
}
```

Một field static hoặc một field mutable trong `@Service` singleton **không phải thread-local**. Nó có thể bị request khác ghi đè cùng lúc và làm mọi thread dùng danh tính cuối cùng. Ngay cả ThreadLocal static cũng cần remove; việc dùng static field thường còn tệ hơn vì chia sẻ toàn JVM.

### 6.5. InheritableThreadLocal và thread pool

`MODE_INHERITABLETHREADLOCAL` chuyển giá trị từ parent thread sang **child thread tại thời điểm child được tạo**; nó không tạo “đường dây đồng bộ danh tính” cho mọi task sau này.

```text
Alice request -> tạo worker thread lần đầu
                 worker kế thừa context Alice
                 |
Bob request -> submit vào worker đó (không tạo child thread mới)
                 worker vẫn có thể giữ context Alice
```

`SecurityContext` còn là object mutable; việc kế thừa/chia sẻ reference có thể dẫn tới thay đổi không mong muốn. Bật InheritableThreadLocal toàn ứng dụng web để “fix @Async” có thể làm rò quyền. Dùng wrapper theo **thời điểm submit task** thay vì đặt chiến lược toàn JVM.

### 6.6. MODE_GLOBAL càng nguy hiểm

`MODE_GLOBAL` chia một context cho các thread của JVM; trên máy chủ nhiều user, người dùng có thể giẫm lên nhau. Nó chỉ phù hợp với mô hình không phải server multi-user trong một số trường hợp rất đặc biệt. Không chuyển ứng dụng Servlet sang MODE_GLOBAL để “mọi nơi lấy được Authentication”.

### 6.7. Dữ liệu độc lập khỏi context vẫn có thể bị rò

Xóa `SecurityContextHolder` **không xóa** các ThreadLocal tùy chỉnh khác như `TenantContext`, `MDC`, request-scoped cache tự viết hay datasource routing key. Mỗi context có lifecycle riêng. Khi truyền identity qua executor, cũng cần xét trace/correlation/tenant, không chỉ authentication. Xóa `SecurityContext` rồi nhưng giữ `TenantContext=tenantA` vẫn có thể gây truy vấn nhầm tenant.

## 7. Truyền context sang thread khác: khi nào và bằng cách nào?

### 7.1. Không có propagation tự động cho mọi thread pool

Với `MODE_THREADLOCAL` mặc định:

```java
Authentication current =
    SecurityContextHolder.getContext().getAuthentication();

CompletableFuture.supplyAsync(() -> {
    Authentication background =
        SecurityContextHolder.getContext().getAuthentication();
    return background == null ? "none" : background.getName();
});
```

Đây là snippet minh họa: task `CompletableFuture.supplyAsync` mặc định thường chạy trên pool khác. Nó **không chắc** có `SecurityContext` của caller. Nếu code cần actor, hãy quyết định có nên truyền identity, và nếu có thì dùng executor bảo mật hoặc truyền một actor ID đã xác minh như dữ liệu, rồi **reauthorize** khi tác vụ chạy muộn.

### 7.2. DelegatingSecurityContextRunnable

Spring Security cung cấp `DelegatingSecurityContextRunnable`. Nó bọc một `Runnable`, đặt context cần dùng vào holder trước khi delegate chạy và **dọn/khôi phục** khi task kết thúc theo implementation/version.

```java
SecurityContext submittedContext =
    SecurityContextHolder.getContext();

Runnable work = () -> {
    Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();
    // Chỉ làm thao tác được quyền sau kiểm tra policy.
};

Runnable secured =
    new DelegatingSecurityContextRunnable(work, submittedContext);

executor.execute(secured);
```

Đây là snippet; biến `executor` là một `Executor` mà ứng dụng đã cấu hình, không phải một instance giả trong tài liệu. Với constructor không truyền context, wrapper lấy context từ holder khi tạo. **Điểm cần nhớ:** bắt context đúng thời điểm submit, không dùng context của một admin hard-coded để chạy mọi tác vụ.

### 7.3. DelegatingSecurityContextExecutor

Khi muốn mọi lần `executor.execute(...)` được bọc nhất quán:

```java
ExecutorService rawPool = Executors.newFixedThreadPool(4);

Executor safeExecutor =
    new DelegatingSecurityContextExecutor(rawPool);

// Gọi trong request của Alice:
safeExecutor.execute(() -> {
    Authentication current =
        SecurityContextHolder.getContext().getAuthentication();
    // Task thấy context được lấy khi submit.
});
```

Đây cũng là snippet. Constructor chỉ nhận delegate `Executor` (không truyền một context cố định) sẽ lấy `SecurityContext` của caller **mỗi lần submit** và bọc task. Wrapper quản lý việc thiết lập và dọn thread scope. Phải đóng `rawPool` khi ứng dụng dừng, dùng cancellation/exception handling, và không truyền toàn bộ context vào hàng đợi chạy nhiều giờ nếu không có chính sách hết hạn quyền.

### 7.4. Sự khác nhau giữa hai constructor quan trọng

| Cách tạo executor | Context sử dụng | Cảnh báo |
| --- | --- | --- |
| `new DelegatingSecurityContextExecutor(rawExecutor)` | Context lấy từ `SecurityContextHolder` lúc **submit mỗi task** | Hữu ích khi cần tác vụ thực thi bằng identity hiện tại |
| `new DelegatingSecurityContextExecutor(rawExecutor, fixedContext)` | **Cùng một context cố định** cho mọi task | Chỉ dùng khi thật sự có system identity được kiểm soát; rất nguy hiểm nếu cố định một user có quyền cao |

Không dùng fixed context của user admin cho mọi công việc rồi coi đó là “an toàn vì wrapper có finally”. Cleanup ngăn context còn sót **sau** task; nó không chứng minh task được cấp đúng quyền khi chạy.

### 7.5. @Async và CompletableFuture

- `@Async` có thể chạy trên `ThreadPoolTaskExecutor` hoặc một executor do Spring Boot cấu hình; ThreadLocal của request **không tự động** theo mọi task.
- Một cách tích hợp là `DelegatingSecurityContextAsyncTaskExecutor` bọc một `AsyncTaskExecutor`; sau đó định tuyến `@Async("securityAwareExecutor")` qua bean đã bọc.
- `CompletableFuture.supplyAsync(supplier)` mặc định không dùng executor bạn đã bọc. Phải truyền rõ `supplyAsync(supplier, securityAwareExecutor)` nếu có lý do bảo mật để propagation.
- `TaskDecorator` có thể hỗ trợ truyền một số context như MDC, nhưng không tự coi là cơ chế thay thế Spring Security wrapper nếu chưa được thiết kế và test.
- `ExecutorService.submit(Callable)` với raw executor cũng không được `DelegatingSecurityContextExecutor` bảo vệ nếu bạn bỏ qua wrapper.
- `@Scheduled`/job queue chạy lâu nên ưu tiên **service identity hoặc actor ID bất biến + kiểm lại quyền**; không mang nguyên authentication token cũ sang một job chạy ngày hôm sau.

Một sketch tích hợp Spring `@Async` (cần import/class phù hợp):

```java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean
    ThreadPoolTaskExecutor taskPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.initialize();
        return executor;
    }

    @Bean("securityAwareAsyncExecutor")
    AsyncTaskExecutor securityAwareAsyncExecutor(
            ThreadPoolTaskExecutor taskPool) {
        return new DelegatingSecurityContextAsyncTaskExecutor(taskPool);
    }
}

// Ở bean khác, lời gọi qua Spring proxy:
@Async("securityAwareAsyncExecutor")
public CompletableFuture<String> process() {
    return CompletableFuture.completedFuture(
        SecurityContextHolder.getContext().getAuthentication().getName());
}
```

Đây là **snippet định hướng**: cần class/bean chứa method, imports, scope và xử lý null/authz; không phải một ứng dụng độc lập. `@Async` có cơ chế proxy (self-invocation thường không được intercept), context có thể được propagate theo thời điểm submit và wrapper dọn sau task. Chỉ dùng cách này nếu business policy cho phép task làm việc theo caller identity.

### 7.6. Khi không nên mang cả SecurityContext vào background job

Nếu queue có độ trễ hoặc task tiếp tục chạy sau logout/khóa account, context captured ở thời điểm submit có thể không phản ánh quyền hiện tại. Thay vì giữ cả `Authentication` và raw claims, đưa vào message **actor ID**, **tenant ID**, **action**, **resource ID**, **trace ID** và **thời điểm yêu cầu** theo data contract đã ký/kiểm soát, rồi khi worker thực sự chạy kiểm tra quyền và trạng thái lại. Với system automation, tạo service principal/authorization riêng, không mượn một admin session.

**Không coi logout là tự động hủy các task đã được submit và đang giữ reference đến SecurityContext**. Cần cơ chế cancel/revoke/reauthorize tùy nghiệp vụ.

## 8. Demo đầy đủ: Spring Boot MVC quan sát ThreadLocal trong request và worker pool

Ứng dụng nhỏ làm ba việc:

1. HTTP Basic xác thực Alice và admin với user store BCrypt hash.
2. `GET /me` đọc `Authentication` từ current servlet thread.
3. `GET /thread/plain` dùng `ExecutorService` thường: background thread **không tự thấy Alice**.
4. `GET /thread/delegated` dùng `DelegatingSecurityContextExecutor`: background thread thấy Alice **chỉ trong task được bọc**.
5. Request sau và task raw sau đó **không được kế thừa ngữ cảnh** của Alice.

Lưu ý: Demo cố tình chờ `Future.get` trong MVC controller để minh họa đơn giản. Với production có tải, không nên để endpoint HTTP đồng bộ chặn thread chờ background job; hãy dùng asynchronous request handling/queue và policy phù hợp.

### 8.1. Phiên bản và cấu trúc

- JDK **17+**.
- Spring Boot **3.5.16**, Spring Security **6.5.x** theo Boot BOM.
- Maven 3.9+ (hoặc Maven wrapper tương đương).
- Spring MVC/Servlet, không dùng WebFlux trong app này.

```text
security-context-threadlocal-demo/
├── pom.xml
└── src/
    ├── main/java/demo/context/
    │   └── SecurityContextThreadLocalApplication.java
    └── test/java/demo/context/
        ├── ContextWebTests.java
        └── ContextWorkerTests.java
```

Spring Boot 3.5.16 phát hành năm 2026 và là bản OSS cuối của nhánh 3.5.x. Ở dự án mới triển khai production, chọn bản Boot/Security còn được hỗ trợ và kiểm tra migration guide. Bài dùng 3.5.x để tái hiện API chính xác của Spring Security 6.5; Java 17 là mức nền phù hợp.

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>security-context-threadlocal-demo</artifactId>
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
```

### 8.3. Java ứng dụng

Tạo `src/main/java/demo/context/SecurityContextThreadLocalApplication.java`:

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

import jakarta.servlet.DispatcherType;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@SpringBootApplication
public class SecurityContextThreadLocalApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityContextThreadLocalApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class ContextSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me",
                    "/thread/plain", "/thread/delegated", "/boom")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            .build();
    }

    @Bean(name = "plainProbeExecutor", destroyMethod = "shutdownNow")
    ExecutorService plainProbeExecutor() {
        return Executors.newSingleThreadExecutor(r -> {
            Thread thread = new Thread(r, "context-probe-worker");
            thread.setDaemon(true);
            return thread;
        });
    }

    @Bean(name = "securityAwareProbeExecutor")
    Executor securityAwareProbeExecutor(
            @Qualifier("plainProbeExecutor") ExecutorService pool) {
        // Không truyền fixed SecurityContext: capture identity MỖI lần submit.
        return new DelegatingSecurityContextExecutor(pool);
    }
}

@Service
class ContextProbeService {
    private final ExecutorService rawPool;
    private final Executor securityAwareExecutor;

    ContextProbeService(
            @Qualifier("plainProbeExecutor") ExecutorService rawPool,
            @Qualifier("securityAwareProbeExecutor") Executor secureExecutor) {
        this.rawPool = rawPool;
        this.securityAwareExecutor = secureExecutor;
    }

    static String currentName() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
        return authentication == null
            ? "none"
            : authentication.getName();
    }

    String fromPlainExecutor()
            throws InterruptedException, ExecutionException,
                   TimeoutException {
        // Raw worker thread khác servlet request thread:
        // mặc định KHÔNG tự có authentication của caller.
        return rawPool.submit(ContextProbeService::currentName)
            .get(3, TimeUnit.SECONDS);
    }

    String fromDelegatingExecutor()
            throws InterruptedException, ExecutionException,
                   TimeoutException {

        CompletableFuture<String> answer = new CompletableFuture<>();

        securityAwareExecutor.execute(() -> {
            try {
                answer.complete(currentName());
            } catch (Throwable failure) {
                answer.completeExceptionally(failure);
            }
        });

        // Wrapper sẽ dọn worker context sau khi delegate hoàn tất.
        return answer.get(3, TimeUnit.SECONDS);
    }
}

@RestController
class ContextController {
    private final ContextProbeService probe;

    ContextController(ContextProbeService probe) {
        this.probe = probe;
    }

    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String current(Authentication authentication) {
        return "me:" + authentication.getName();
    }

    @GetMapping("/thread/plain")
    String plain(Authentication authentication) throws Exception {
        return "request:" + authentication.getName()
            + ";worker:" + probe.fromPlainExecutor();
    }

    @GetMapping("/thread/delegated")
    String delegated(Authentication authentication) throws Exception {
        return "request:" + authentication.getName()
            + ";worker:" + probe.fromDelegatingExecutor();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @GetMapping("/boom")
    String fail() {
        throw new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR, "lab error");
    }
}
```

### 8.4. Những điều phải hiểu trong code

1. `ContextSecurityConfiguration.securityFilterChain` dùng HTTP Basic và `SessionCreationPolicy.STATELESS`: request mới cần gửi credentials mới, không dùng server session để khôi phục Alice.
2. User `alice` và `admin` được tạo trong RAM với BCrypt hash; mật khẩu `demo-pass` chỉ dùng trên máy học.
3. `GET /me` nhận `Authentication` đã được filter xác minh, không phải một field global do controller giữ.
4. `plainProbeExecutor` là `ExecutorService` **một thread** để các task chắc chắn tái sử dụng đúng một worker trong demo.
5. `securityAwareProbeExecutor` là wrapper nhận **chính pool đó**, nhưng lấy context của thread gửi task **theo từng lần submit** (constructor không truyền fixed context).
6. `GET /thread/plain` cho thấy request thread nhìn Alice nhưng plain worker bình thường đọc thấy `none`.
7. `GET /thread/delegated` cho thấy request thread nhìn Alice và worker thấy Alice **trong đúng task** do wrapper cài context.
8. Khi task được bọc kết thúc, wrapper xử lý cleanup; vì vậy một task tiếp theo chạy trên raw worker không được nhìn lại Alice.
9. `/boom` tạo response lỗi từ controller để test luồng ngoại lệ; filter vẫn phải dọn ThreadLocal khi request kết thúc.
10. `@Bean(destroyMethod="shutdownNow")` yêu cầu đóng worker pool lúc application context shutdown. Đây là điều cần có cho pool có vòng đời dài.
11. Không gọi `SecurityContextHolder.setStrategyName(MODE_GLOBAL)`, không dùng InheritableThreadLocal và không sao chép ngữ cảnh qua biến static.

**Ranh giới:** Các endpoint `/thread/*` có mục đích trình diễn và dùng blocking wait. Không đưa nguyên kiểu endpoint này vào hệ thống xử lý tác vụ production, càng không trả raw security principal/claims ra JSON để “debug”.

### 8.5. Integration test: nhiều request, nhiều identity, task wrapper và exception

Tạo `src/test/java/demo/context/ContextWebTests.java`:

```java
package demo.context;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextWebTests {

    @Autowired
    MockMvc mvc;

    @AfterEach
    void cleanTestThread() {
        // Test isolation; không thay việc cleanup của Spring Security filter.
        SecurityContextHolder.clearContext();
    }

    @Test
    void sameTestThreadDoesNotKeepPreviousRequestIdentity()
            throws Exception {

        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"));

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        // Filter đã kết thúc: test thread không còn Alice.
        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:admin"));

        // Bỏ credential, không được thừa hưởng admin.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void rawPoolDoesNotInheritCurrentCallerAndWrapperDoes()
            throws Exception {

        mvc.perform(get("/thread/plain")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:none"));

        mvc.perform(get("/thread/delegated")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:alice"));

        // Cùng worker của pool, nhưng context từ task trước đã được dọn.
        mvc.perform(get("/thread/plain")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:admin;worker:none"));

        mvc.perform(get("/thread/delegated")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:admin;worker:admin"));

        mvc.perform(get("/thread/plain")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "request:alice;worker:none"));
    }

    @Test
    void failuresAndDeniedRequestsDoNotLeaveIdentity()
            throws Exception {

        mvc.perform(get("/me")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));

        mvc.perform(get("/boom")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isInternalServerError());

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        // Request ngay sau lỗi vẫn phải xác thực từ đầu.
        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());
    }
}
```

**Ý nghĩa của test:**

- `@SpringBootTest` nạp bean thật và `@AutoConfigureMockMvc` dùng Spring Security filter chain thật cho request.
- `httpBasic("alice", "demo-pass")` đưa credential đến provider, khác với `@WithMockUser` vốn giả lập principal và không xác minh password.
- Test cố ý chạy các request liên tục trong một method để dễ quan sát không có context cũ trên request thread của MockMvc.
- `GET /thread/plain` và `GET /thread/delegated` đối chiếu **không truyền** và **truyền đúng** context khi dùng cùng worker pool.
- Sau task delegated của Alice, task plain của admin vẫn đọc `none` ở worker — chứng minh wrapper đã dọn scope background.
- `GET /boom` tạo HTTP `500`, request sau anonymous vẫn `401`. Điều này thể hiện cleanup không chỉ diễn ra ở “đường thành công”.
- `@AfterEach` dọn test thread để cô lập test; trong request Servlet chuẩn, trách nhiệm lifecycle thuộc Spring Security filter chain.
- Các assertion mô tả behavior của demo trong cấu hình mặc định `MODE_THREADLOCAL`; nếu hệ thống đã thay strategy toàn JVM hoặc dùng custom filter không chuẩn, phải kiểm tra lại.

### 8.6. Unit test: tái hiện rò rỉ ở pool và kiểm tra cleanup

Tạo `src/test/java/demo/context/ContextWorkerTests.java`:

```java
package demo.context;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ContextWorkerTests {

    @AfterEach
    void clearMainTestThread() {
        SecurityContextHolder.clearContext();
    }

    private static String currentName() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "none" : auth.getName();
    }

    private static void installTestIdentity(String name) {
        // Chỉ tạo test Authentication, không xác minh credential.
        SecurityContext context =
            SecurityContextHolder.createEmptyContext();

        context.setAuthentication(
            new TestingAuthenticationToken(name, "not-a-password",
                "ROLE_USER"));

        SecurityContextHolder.setContext(context);
    }

    @Test
    void unsafeWorkerLeaksIdentityIntoNextTaskIfNeverCleared()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            String first = worker.submit(() -> {
                installTestIdentity("alice");
                // CỐ TÌNH KHÔNG clearContext: phản ví dụ.
                return currentName();
            }).get(3, TimeUnit.SECONDS);

            assertEquals("alice", first);

            String leaked = worker.submit(ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS);

            // ĐÂY LÀ LỖI CẦN NGĂN TRONG ỨNG DỤNG THẬT.
            assertEquals("alice", leaked);

            // Dọn ngay để test này không giữ rò rỉ.
            String afterCleanup = worker.submit(() -> {
                SecurityContextHolder.clearContext();
                return currentName();
            }).get(3, TimeUnit.SECONDS);

            assertEquals("none", afterCleanup);
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void finallyRemovesIdentityEvenWhenWorkThrows()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            assertThrows(ExecutionException.class, () ->
                worker.submit((Runnable) () -> {
                    installTestIdentity("alice");
                    try {
                        throw new IllegalStateException("demo failure");
                    } finally {
                        SecurityContextHolder.clearContext();
                    }
                }).get(3, TimeUnit.SECONDS));

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void delegatingExecutorCapturesCallerAndCleansWorker()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            installTestIdentity("alice");

            DelegatingSecurityContextExecutor secured =
                new DelegatingSecurityContextExecutor(worker);

            CompletableFuture<String> result = new CompletableFuture<>();

            // Context của test thread được capture ở THỜI ĐIỂM submit.
            secured.execute(() -> result.complete(currentName()));

            assertEquals("alice", result.get(3, TimeUnit.SECONDS));

            // Dọn test thread, kiểm raw worker không còn Alice.
            SecurityContextHolder.clearContext();

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));

            // Một task mới chỉ nhận identity khi caller có identity mới.
            installTestIdentity("bob");
            CompletableFuture<String> second = new CompletableFuture<>();
            secured.execute(() -> second.complete(currentName()));

            assertEquals("bob", second.get(3, TimeUnit.SECONDS));
            SecurityContextHolder.clearContext();

            assertEquals("none", worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }

    @Test
    void rawWorkerDoesNotAutomaticallySeeCallerAuthentication()
            throws Exception {

        ExecutorService worker = Executors.newSingleThreadExecutor();

        try {
            installTestIdentity("alice");

            // MODE_THREADLOCAL: một worker khác không tự thấy caller.
            String onWorker = worker.submit(
                ContextWorkerTests::currentName)
                .get(3, TimeUnit.SECONDS);

            assertEquals("none", onWorker);
            assertEquals("alice", currentName());
        } finally {
            SecurityContextHolder.clearContext();
            worker.shutdownNow();
        }
    }
}
```

**Các bài test có giá trị phân biệt:**

- `unsafeWorkerLeaksIdentityIntoNextTaskIfNeverCleared` **cố ý tạo tình huống sai** trên đúng một thread và assert giá trị rò rỉ. Đây là test để hiểu lỗ hổng, không phải một pattern production. Test dọn ngay sau khi xác minh.
- `finallyRemovesIdentityEvenWhenWorkThrows` làm task throw exception, nhưng `finally` vẫn xóa context trước task kế tiếp.
- `delegatingExecutorCapturesCallerAndCleansWorker` xác minh wrapper lấy identity theo lúc submit: Alice, Bob, và kiểm raw worker trống sau mỗi task.
- `rawWorkerDoesNotAutomaticallySeeCallerAuthentication` nhấn mạnh mặc định ThreadLocal không tự truyền sang raw executor.
- Mỗi test có **pool riêng**, shutdown trong `finally` và test thread cũng được dọn, tránh làm state của test khác sai.
- `TestingAuthenticationToken` trong unit test chỉ là object giả lập, **không phải** chứng cứ password đã được xác minh. Không đưa nó vào production authentication path.

**Cảnh báo về dọn context lồng nhau:** Nếu task library đang quản lý một context hợp lệ trước đó, việc tự gọi `clearContext` vô điều kiện có thể làm mất context của caller. Khi xây wrapper scope lồng nhau, nên dùng các wrapper framework hiểu lifecycle hoặc sao lưu/khôi phục context trước đó một cách có chủ đích. Mục đích chính là **sau khi task của Alice kết thúc, thread không còn mang Alice khi nhận task không liên quan**.

### 8.7. Cách chạy

Tại thư mục chứa `pom.xml`:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Kết quả dự kiến** khi ứng dụng và dependency hoạt động:

- `mvn test` chạy `ContextWebTests` và `ContextWorkerTests`; các assertion được thiết kế để pass, bao gồm test tái hiện lỗi cố ý rồi cleanup.
- `GET /me` anonymous → `401`, Alice đúng mật khẩu → `200 me:alice`.
- `GET /thread/plain` với Alice → `200 request:alice;worker:none`.
- `GET /thread/delegated` với Alice → `200 request:alice;worker:alice`.
- `GET /thread/plain` với admin ngay sau delegated → `200 request:admin;worker:none`.
- `GET /admin` với Alice → `403`; với admin → `200`.
- `GET /boom` đã xác thực → `500`; request tiếp theo không credential → `401`.

Đây là **kỳ vọng của code/test**, không phải output được thu thập từ một lần chạy Maven trong môi trường biên soạn.

Trong terminal thứ hai (chỉ trên localhost):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/me
curl -i -u alice http://localhost:8080/thread/plain
curl -i -u alice http://localhost:8080/thread/delegated
curl -i -u admin http://localhost:8080/thread/plain
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Curl sẽ hỏi password khi dùng `-u alice` hoặc `-u admin`; nhập `demo-pass` **chỉ trên máy lab**. Không nhúng password vào command history; không dùng HTTP Basic trên mạng thật nếu thiếu TLS. Trong PowerShell cũ có thể cần `curl.exe`.

**Đừng công khai các endpoint chẩn đoán thread/context** của demo. Chúng hiển thị username từ principal để dễ hiểu; sản phẩm thật chỉ trả dữ liệu đã qua DTO/authorization policy và không in security context ra response.

## 9. Kiểm soát lỗi trong custom code

### 9.1. Mẫu scope an toàn ngoài HTTP filter

Nếu bạn thật sự sở hữu vòng đời một task độc lập và phải set context:

```java
void runUnderVerifiedIdentity(
        Authentication verified, Runnable work) {

    SecurityContext scope =
        SecurityContextHolder.createEmptyContext();
    scope.setAuthentication(verified);

    SecurityContextHolder.setContext(scope);
    try {
        work.run();
    } finally {
        SecurityContextHolder.clearContext();
    }
}
```

Đây là **snippet** và điều kiện đầu vào rất quan trọng: `verified` phải được lấy từ source/cơ chế xác thực đáng tin, không phải token tự gắn role từ HTTP request. Nếu code có nested scopes, nên dùng wrapper Spring Security hoặc phương án restore previous context phù hợp để tránh vô tình xóa scope của caller.

### 9.2. Sao lưu và phục hồi context khi lồng scope

Trong một số library, code tạm thời thay context để gọi một thao tác, sau đó muốn trả lại context của caller đang chạy trên cùng thread:

```java
SecurityContext previous = SecurityContextHolder.getContext();

try {
    SecurityContext temporary =
        SecurityContextHolder.createEmptyContext();
    temporary.setAuthentication(systemIdentity);
    SecurityContextHolder.setContext(temporary);

    performScopedOperation();
} finally {
    SecurityContextHolder.setContext(previous);
}
```

**Đây là snippet theo trường hợp đặc biệt**, không phải lời khuyên nâng quyền tạm thời bằng tay. `systemIdentity` phải là principal được policy chấp nhận, còn previous context phải thuộc cùng scope đáng tin. Nếu thread vốn bị rò dữ liệu từ tác vụ trước, thao tác restore previous có thể **khôi phục lại context sai**; đó là lý do wrapper phải được đặt ở boundary đúng và worker mới phải bắt đầu ở trạng thái sạch.

### 9.3. Không clearContext trong controller một cách tùy tiện

```java
@GetMapping("/profile")
String profile() {
    SecurityContextHolder.clearContext(); // PHẢN VÍ DỤ
    return loadProfile();
}
```

Xóa context giữa request có thể khiến các filter/handler/service phía sau không còn current authentication, dẫn tới hành vi khác dự kiến. Khi request được quản lý bởi Spring Security, **framework chịu trách nhiệm cleanup ở boundary**. Bạn chỉ cần chủ động clear khi:
- Đang quản lý một scope **ngoài** filter chain.
- Đang thực hiện logout/invalidating flow với repository/session đúng.
- Đang viết library wrapper chủ động set context và đã xác định rõ phạm vi.
- Đang làm test isolation, sau khi test hoàn tất.

Cần tránh “clear một chỗ tùy ý để an toàn” làm hỏng logic nghiệp vụ hoặc gây sai audit.

### 9.4. Nếu custom filter tự đặt context

Một cách thường gặp là triển khai filter dựa trên `OncePerRequestFilter` rồi thực hiện authentication custom. Thay vì `setContext` tùy ý, nên tích hợp `AuthenticationManager`/`SecurityContextHolderStrategy`/`SecurityContextRepository` và các hook của Spring Security tương ứng. Nếu filter nằm ngoài lifecycle do `SecurityContextHolderFilter` quản lý, code phải bảo đảm cleanup ở `finally`, và với Servlet ASYNC/ERROR dispatch phải xét scope/dispatcher cụ thể.

**Không chỉ assert một request 200.** Test chuỗi request cùng thread/pool, request bị lỗi, wrong credential, anonymous, user khác, async path và session restore.

## 10. ThreadLocal, MDC, RequestAttributes và TenantContext

Trong hệ thống thực, một request có thể đồng thời giữ:

```text
SecurityContextHolder  -> Authentication: alice
MDC                    -> traceId: request-123, actorId: alice
TenantContext          -> tenantId: company-A
RequestContextHolder   -> Servlet request attributes
Custom ThreadLocal     -> vùng tùy chỉnh
```

Các context này **không tự có một lifecycle thống nhất**. Spring Security dọn `SecurityContextHolder`; logging framework có thể có `MDC.clear()` hoặc `MDC.remove("key")`; một `TenantContext` tự viết cần remove; `RequestContextHolder` được Spring Web quản lý theo dispatch tương ứng. Nếu tự tạo worker:

```java
TenantContext.set(tenantId);
MDC.put("traceId", traceId);
try {
    process();
} finally {
    MDC.remove("traceId");
    TenantContext.clear();
    SecurityContextHolder.clearContext(); // khi chính task sở hữu scope
}
```

Snippet này không chạy độc lập vì `TenantContext`, `MDC` và `process` là API/dữ liệu của ứng dụng; nó cho thấy **phải cleanup đúng từng loại**. Với executor đã có wrapper Spring Security, tránh lồng thêm `clearContext` sai thời điểm; thiết kế task decorator/context propagation có kiểm soát để dọn tất cả các lớp.

### 10.1. Vì sao tenant context leak đặc biệt nguy hiểm?

Nếu repository query dùng `TenantContext.get()` để lựa tenant/schema/database, rò tenant dù `SecurityContextHolder` đã sạch vẫn có thể dẫn tới dữ liệu cross-tenant. Do đó test “không rò identity” phải mở rộng sang **không rò tenant**, không chỉ current username.

### 10.2. Logging phải tránh lộ credential

Ngay cả khi cleanup đúng, log sai vẫn có thể rò username, access token, refresh token, session ID hoặc raw Basic header. Khi cần audit, ghi tối thiểu actor ID, tenant ID, action, outcome và correlation ID đã kiểm chứng; không ghi cả object `Authentication` hoặc request headers. Đừng dùng value của ThreadLocal làm nguồn duy nhất cho audit của một job chạy muộn: xác minh actor theo metadata tin cậy của job.

## 11. WebFlux và Reactor Context: không bê ThreadLocal Servlet sang reactive

Spring WebFlux có execution model reactive, nhiều pipeline có thể chạy trên những thread khác nhau và thread được tái sử dụng giữa nhiều subscription. Spring Security reactive thường dựa trên `ReactiveSecurityContextHolder` trong **Reactor Context**, không lấy `SecurityContextHolder` ThreadLocal Servlet làm cơ chế tiêu chuẩn.

```java
// Snippet reactive trong một WebFlux service:
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
}
```

Đoạn này cần import `Mono`, `ReactiveSecurityContextHolder`, `SecurityContext` và `Authentication` tương ứng. Nó là **snippet**, không được copy vào app Servlet demo ở mục 8. Với WebFlux, dùng `SecurityWebFilterChain` và `ServerHttpSecurity`, method security reactive nếu áp dụng. Không gọi `SecurityContextHolder.getContext()` từ bất kỳ reactive operator nào rồi cho rằng user luôn đúng vì request bắt đầu trên thread đó.

### 11.1. Khác biệt kỹ thuật

| Chủ đề | Servlet | WebFlux |
| --- | --- | --- |
| Context thường đọc bằng | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Cơ chế thực thi | Servlet thread-bound filter lifecycle | Reactor Context gắn với reactive subscription |
| Web security | `SecurityFilterChain`/`HttpSecurity` | `SecurityWebFilterChain`/`ServerHttpSecurity` |
| Tác vụ chuyển thread | Cần wrapper/integration có chủ đích | Dùng Reactor operators và Context propagation phù hợp |
| Kiểm thử HTTP | `MockMvc` | `WebTestClient` |
| Rủi ro leak | Worker thread reuse/custom ThreadLocal | Sai Reactor context scope/custom ThreadLocal/cross-subscriber data |
| Clear ThreadLocal cuối Servlet request | Có vai trò trực tiếp | Không giải thích đầy đủ cleanup của Reactor Context |

Không sửa lỗi WebFlux bằng `MODE_INHERITABLETHREADLOCAL` hoặc cố ép mọi publisher chạy một thread. Reactive context là một cơ chế khác, cần code/test đúng reactive API.

## 12. Một số bẫy với async và transaction

### 12.1. @Async thay thread nhưng không thay policy

Một method có `@PreAuthorize` chạy bên trong background task có thể không thấy authentication nếu không propagate context. Nhưng “fix” propagation không đồng nghĩa user được phép thực thi mọi hành động khi task chạy: quyền có thể đã bị thu hồi. Hãy kiểm actor, hành động, resource và thời gian khi task thực sự thực thi.

### 12.2. CompletableFuture dùng common pool

Không mặc định tin `CompletableFuture.supplyAsync(...)` có cùng identity với servlet thread. Cần truyền executor security-aware theo API có nhận `Executor`, hoặc truyền ID user đã kiểm chứng và giải quyết authorization trong worker. Trong bất kỳ trường hợp nào, task phải cleanup context của thread nó dùng.

### 12.3. Transaction cũng thường thread-bound

Spring transaction declarative thường gắn với thread thực thi. Khi bạn đưa công việc sang worker khác, transaction của request không tự chuyển sang worker, tương tự SecurityContext. **Không đánh đồng transaction propagation với security context propagation**. Task cần transaction riêng nếu thực hiện DB operations, và phải kiểm quyền/domain invariants tại đúng thời điểm.

### 12.4. Error/ASYNC dispatch không giống task pool tùy ý

Spring Security có tích hợp với Servlet async processing và Spring MVC async trong những trường hợp được hỗ trợ. Không kết luận “mọi Callable từ MVC đều mất context” chỉ vì raw `ExecutorService.submit` không tự propagate. Nhưng một task tùy chỉnh qua `@Async`/`CompletableFuture`/queue có thể dùng executor khác. Xác định **cơ chế gọi cụ thể**, rồi test.

### 12.5. Virtual threads Java 21+

Virtual threads vẫn là threads và có semantics ThreadLocal, nhưng vòng đời/phần tử scheduler khác thread pool truyền thống. `SecurityContextHolder` với `MODE_THREADLOCAL` vẫn cần scope rõ ràng; không được coi virtual threads tự giải quyết identity leakage hay auto-propagation. Khi dùng virtual-thread executor, xem hướng dẫn của Spring Boot/Security phiên bản tương thích và test async/cancellation/cleanup; ví dụ Java 17 ở bài này không phụ thuộc virtual threads.

## 13. Những lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Hướng khắc phục |
| --- | --- | --- |
| `SecurityContextHolder.setContext` rồi return không finally | Thread pool có thể mang context cũ | Chủ scope cần `try/finally`, hoặc wrapper chính thức |
| Bắt exception rồi quên cleanup | Identity còn trên worker | Cleanup trong `finally`, không đặt sau đoạn dễ throw |
| Bật `MODE_GLOBAL` cho web app | Mọi user chia sẻ context | Giữ `MODE_THREADLOCAL` |
| Bật `MODE_INHERITABLETHREADLOCAL` để sửa @Async | Thread pool có thể giữ identity của lúc thread tạo | `DelegatingSecurityContextAsyncTaskExecutor` |
| Dùng raw `CompletableFuture.supplyAsync` rồi nghĩ có auth | Task không thấy caller identity | Truyền executor bảo mật hoặc actor ID với reauthorize |
| Dùng fixed admin context cho mọi task | Task user thường có thể chạy bằng admin | Capture per submission hoặc service identity được kiểm soát |
| Lưu Authentication trong static singleton field | Race/leak identity toàn JVM | Không dùng global mutable current user |
| Dọn ThreadLocal trong controller trước business method | Business code mất auth giữa request | Để security filter quản scope HTTP |
| Tưởng clearContext = logout | Session/token còn hợp lệ | Logout handlers + repository/session/token revoke |
| Tưởng saveContext = clearContext | Worker vẫn có stale context | Dọn scope bằng finally/filter |
| Xóa SecurityContext nhưng không xóa TenantContext | Có thể query nhầm tenant | Cleanup độc lập cho tenant/MDC |
| Chỉ test request thành công | Lỗi 401/403/500/cancel không được phát hiện | Test cả failure và request kế tiếp |
| Dùng `@WithMockUser` rồi kết luận Basic login đúng | Mock bypass credential provider | Thêm test `httpBasic`/form login thực |
| Chỉ nhìn `isAuthenticated()==true` | Anonymous token cũng có thể true | Spring authorization/trust resolver |
| Mang user session trong queue chạy nhiều giờ | Role có thể stale/revoked | Actor ID + reauthorize/expiry/cancel |
| Tạo ThreadLocal cho current tenant rồi không remove | Cross-tenant access risk | Dùng try/finally/wrapper và test |
| WebFlux gọi `SecurityContextHolder` ThreadLocal | Sai identity khi thread đổi | `ReactiveSecurityContextHolder`/Reactor Context |

## 14. Ma trận kiểm thử đề xuất

| Trường hợp | Điều cần xác minh |
| --- | --- |
| `GET /public` anonymous | Response 200; không tạo authenticated user |
| `GET /me` anonymous | 401 với HTTP Basic entry point |
| `GET /me` Alice đúng password | 200, me:alice |
| `GET /me` password sai | 401 |
| Alice rồi anonymous trên cùng test thread | Anonymous vẫn 401, không “nhớ Alice” |
| Admin rồi anonymous | Không “nhớ admin” |
| Alice vào `/admin` | 403, role được kiểm tra |
| Admin vào `/admin` | 200 |
| Request authenticated ném error | Request sau không credential vẫn 401 |
| Raw worker executor được submit từ request Alice | Worker không tự thấy Alice |
| Delegating executor từ request Alice | Worker thấy Alice chỉ trong task |
| Delegating executor từ request Bob | Worker thấy Bob, không thấy Alice |
| Raw worker sau delegated task | Worker trở lại `none` |
| Manual worker setContext nhưng quên dọn | Test cố ý tái hiện stale Alice |
| Manual worker có finally | Context bị xóa ngay cả khi throw |
| Profile cấu hình sai MODE_GLOBAL | Test cấu hình/guard phát hiện |
| Servlet async/API background | Context propagation theo integration được test |
| Job sau logout/role revoke | Reauthorization không dùng stale grant |
| MDC/TenantContext cùng thread | Không rò trace/tenant |
| WebFlux reactive test | Dùng Reactor Context/`WebTestClient`, không ThreadLocal Servlet |
| Session-based login request kế tiếp | Repository khôi phục context hợp lệ; thread vẫn được dọn sau mỗi request |

Đây là ma trận cho **security lifecycle**, không chỉ checklist kiểu “endpoint trả 200”. Phải test chuỗi **A → B** trên cùng worker hoặc request pipeline mới phát hiện khả năng rò identity. Tuy nhiên, nếu code cố tạo đúng thứ tự thread bằng sleep, test có thể flaky; dùng một `newSingleThreadExecutor` và `Future.get(timeout)` như demo để xác định rõ worker tái sử dụng.

## 15. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `ThreadLocal` cần dọn khi thread pool tái sử dụng thread?

**Đáp án:** ThreadLocal gắn giá trị với **thread**, không gắn với task/user. Thread xử lý Alice rồi Bob có thể mang giá trị Alice nếu không `remove`/`clearContext`.

**Câu 2.** `SecurityContextHolder.getContext() == null` là cách chuẩn kiểm anonymous?

**Đáp án:** Không. Holder thường trả context rỗng; authentication có thể null hoặc là anonymous token. Dùng authorization rule và trust resolver phù hợp.

**Câu 3.** Spring Security 6 `SecurityContextHolderFilter` làm gì?

**Đáp án:** Nạp/defer nạp context qua `SecurityContextRepository` cho request và dọn holder sau scope; nó không tự lưu mọi thay đổi của custom authentication flow.

**Câu 4.** Sau login form, dọn ThreadLocal cuối request có làm user mất đăng nhập?

**Đáp án:** Không nếu context được lưu đúng ở session/repository. Request sau nạp lại context từ session; ThreadLocal cũ vẫn được dọn để không rò sang người khác.

**Câu 5.** Tại sao raw `ExecutorService` task không thấy current user từ servlet request?

**Đáp án:** Default strategy là `MODE_THREADLOCAL`. Worker khác thread không tự nhận context. Cần wrapper propagation hoặc truyền actor ID và kiểm quyền.

**Câu 6.** `DelegatingSecurityContextExecutor(rawExecutor)` khác `DelegatingSecurityContextExecutor(rawExecutor, fixedContext)` thế nào?

**Đáp án:** Bản một tham số capture context của caller mỗi lần submit; bản hai tham số dùng cùng fixed context cho mọi task. Fixed admin context dễ tạo leo thang quyền nếu dùng sai.

**Câu 7.** Nếu custom worker đã gọi `setContext`, để `clearContext` ở cuối method sau `work.run()` có đủ không?

**Đáp án:** Không khi `work.run()` throw exception. Cần `try/finally`.

**Câu 8.** `SecurityContextHolder.clearContext()` có đăng xuất tất cả session/refresh token không?

**Đáp án:** Không. Nó dọn thread hiện tại. Logout/revocation còn yêu cầu session/repository/token lifecycle theo policy.

**Câu 9.** Bật `MODE_INHERITABLETHREADLOCAL` có bảo đảm mỗi task của Bob trong pool nhận đúng Bob?

**Đáp án:** Không. Inheritance liên quan thời điểm thread được tạo, còn pool tái sử dụng thread, có thể giữ context cũ. Dùng wrapper per-task.

**Câu 10.** Thấy `none` trong background task có nghĩa cleanup đã đúng?

**Đáp án:** Chưa đủ. Có thể task chưa bao giờ nhận identity. Cần cả test delegated task thấy **đúng Alice** và test task sau thấy **none/Bob đúng**.

**Câu 11.** Tại sao không bê đoạn `SecurityContextHolder.getContext()` vào WebFlux?

**Đáp án:** Reactive pipeline có thể chạy nhiều thread; context bảo mật chuẩn được truyền qua Reactor Context bằng `ReactiveSecurityContextHolder`.

**Câu 12.** Khi Alice đổi quyền hoặc logout, một queued job đã capture SecurityContext Alice có tự bị thu hồi?

**Đáp án:** Không nhất thiết. Job cần chính sách expiry/revoke/reauthorize khi chạy; không nên giữ một snapshot authority lâu dài rồi xem nó luôn đúng.

## 16. Checklist cho code review

- [ ] App là Servlet hay WebFlux? Có dùng đúng cơ chế context?
- [ ] `SecurityContextHolder` dùng `MODE_THREADLOCAL` mặc định khi chạy web multi-user?
- [ ] Không có code bật `MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` vô lý?
- [ ] HTTP requests đều đi qua security filter chain đúng matcher/dispatcher?
- [ ] Custom filter/authentication đang đặt context ở đâu, ai sở hữu lifecycle?
- [ ] Với scope tự đặt context: cleanup bằng `finally` kể cả exception/cancel?
- [ ] Với Servlet filter chuẩn: không clear context tùy tiện trong controller?
- [ ] Custom login phân biệt `SecurityContextRepository.saveContext` với `clearContext`?
- [ ] Không lưu current Authentication ở static/singleton mutable field?
- [ ] `@Async`/`CompletableFuture`/thread pool có propagation đúng per-task nếu cần?
- [ ] Không dùng fixed privileged context cho task của mọi user?
- [ ] Executor pool có shutdown/lifecycle rõ và test worker reuse?
- [ ] Task chạy trễ kiểm actor/tenant/permissions lại khi cần?
- [ ] ThreadLocal tự tạo như MDC/TenantContext/trace đều được cleanup?
- [ ] Không log password, Basic header, access token, session cookie, raw Authentication?
- [ ] Kiểm thử theo chuỗi Alice → anonymous/Bob, bao gồm lỗi và exception?
- [ ] Kiểm tra không có cross-tenant read/write sau lỗi context?
- [ ] Tests dùng credential thật ở ít nhất một integration path, không chỉ mock user?
- [ ] Với session/SSO/JWT, có logout/revoke riêng, không nhầm cleanup là logout?
- [ ] Với WebFlux, test Reactor Context và không giả định ThreadLocal tự propagate?

## 17. Tóm tắt ghi nhớ

1. **ThreadLocal lưu theo thread, không theo request/user.** Khi thread tái sử dụng, thiếu cleanup có thể mang identity cũ sang tác vụ mới.
2. **SecurityContextHolder** dùng strategy, mặc định `MODE_THREADLOCAL` trong Servlet; `SecurityContext` chứa `Authentication` hiện tại.
3. **Spring Security filter chain chuẩn dọn context cuối request**. Nếu code tự set context ngoài filter lifecycle, phải có `try/finally` hoặc wrapper framework.
4. **Dọn context không xóa session**, và lưu `SecurityContextRepository` không thay cho dọn thread. Đây là hai mục tiêu khác nhau.
5. **@Async và ExecutorService không tự giữ identity đúng** chỉ vì parent thread đã authenticated. Dùng `DelegatingSecurityContextExecutor`/các wrapper tương ứng hoặc truyền actor ID và reauthorize.
6. **Không dùng MODE_GLOBAL hoặc INHERITABLETHREADLOCAL làm cách chữa chung** cho thread-pool propagation; có nguy cơ lộ quyền.
7. **Test theo chuỗi và theo thread reuse**: Alice rồi anonymous/Bob, task có propagation rồi task raw, exception rồi request mới.
8. **WebFlux dùng Reactor Context**; các lưu ý ThreadLocal Servlet không áp nguyên xi sang reactive.
9. **Không chỉ dọn SecurityContext**: MDC, tenant context và custom ThreadLocal cũng có thể rò thông tin nhạy cảm.

## Tài liệu chính thức

- [Spring Security 6.5 — Servlet Authentication Architecture: SecurityContextHolder và cleanup](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Concurrency Support: DelegatingSecurityContextRunnable/Executor](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html)
- [Spring Security 6.5 — Persisting Authentication, SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — SecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/context/SecurityContextHolder.html)
- [Spring Security 6.5 — DelegatingSecurityContextExecutor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutor.html)
- [Spring Security 6.5 — WebFlux Reactive Method Security và Reactor Context](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Security 6.5 — MockMvc HTTP Basic Test](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 3.5 — Web Security Auto-Configuration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Java 17 — ThreadLocal API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)
- [Java 17 — ExecutorService API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html)
