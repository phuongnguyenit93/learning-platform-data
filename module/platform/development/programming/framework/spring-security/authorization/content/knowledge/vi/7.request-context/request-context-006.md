# SecurityContext trong request bất đồng bộ và lời gọi sang luồng khác

Trong Spring Security cho **ứng dụng Servlet/Spring MVC**, một controller có thể biết người dùng hiện tại qua `SecurityContextHolder.getContext().getAuthentication()`, nhưng một tác vụ được gửi sang `ExecutorService`, `@Async` hoặc `CompletableFuture.supplyAsync(...)` lại thấy `Authentication` rỗng. Tình huống đối nghịch cũng nguy hiểm: một worker thread tái sử dụng context của người dùng trước đó rồi vô tình thực hiện công việc của người dùng mới với quyền cũ.

Điểm mấu chốt: **`SecurityContext` không tự đi cùng mọi tác vụ bất đồng bộ**. Ở Servlet stack, `SecurityContextHolder` mặc định gắn context vào **thread đang chạy** bằng `ThreadLocal`. Spring Security có một số tích hợp tự động cho async request do framework quản lý, và các wrapper chuyên dụng để truyền context khi ứng dụng tự tạo công việc ở thread khác. Phải hiểu **khi nào context được chụp, ai cài đặt nó trên worker, ai khôi phục/dọn nó, và liệu quyền còn hợp lệ lúc job chạy hay không**.

Bài này phân biệt xử lý Servlet async, Spring MVC `Callable`, `DeferredResult`, `AsyncContext.start`, `@Async`, thread pool và `CompletableFuture`; trình bày `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextCallable`, `DelegatingSecurityContextExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`, cùng ví dụ Java 17+ chạy độc lập và các ca kiểm thử chống rò rỉ danh tính. Các đoạn Spring minh họa dựa trên **Spring Boot 3 / Spring Security 6.x (Servlet stack)**; cấu hình WebFlux/reactive có cơ chế khác, không dùng trực tiếp quy tắc `ThreadLocal` này.

## 1. `SecurityContext`, `Authentication` và `SecurityContextHolder` là gì?

Hệ thống có ba khái niệm liên quan nhưng khác nhiệm vụ:

| Thành phần | Nó đại diện cho điều gì? | Cách truy cập phổ biến |
| --- | --- | --- |
| `SecurityContext` | Vùng chứa thông tin bảo mật của execution context, đặc biệt là `Authentication`. | `SecurityContextHolder.getContext()`. |
| `Authentication` | Principal, authorities và dữ liệu liên quan trạng thái xác thực. | `context.getAuthentication()`. |
| `SecurityContextHolder` | Nơi cung cấp/giữ `SecurityContext` cho luồng đang thực thi theo một `SecurityContextHolderStrategy`. | `SecurityContextHolder.getContext()` hoặc `getContextHolderStrategy()`. |

Trong ứng dụng Servlet thông thường, strategy mặc định là **`MODE_THREADLOCAL`**: mỗi thread có vùng context riêng. Một HTTP request thường chạy qua filter chain, nơi cơ chế quản lý security context đưa context thích hợp vào thread đang xử lý; khi request kết thúc, Spring Security bảo đảm dọn context của thread theo vòng đời tương ứng.

~~~text
HTTP request: Alice
   |
   v
Servlet thread T1
   SecurityContextHolder[T1] = {Authentication=Alice}
   |
   +--- Controller -> Service chạy trên T1:
   |       getContext().getAuthentication() -> Alice
   |
   +--- Tạo job và gửi vào thread pool
           |
           v
        Worker thread T9
        SecurityContextHolder[T9] ?  <- không tự là Alice
~~~

Đăng nhập thành công **không có nghĩa** `Authentication` là biến global áp dụng cho cả tiến trình Java. Trong thiết kế an toàn, T1 và T9 là hai execution contexts khác nhau; T9 chỉ có quyền của Alice nếu một cơ chế **có chủ đích và được kiểm soát** chuyển quyền sang.

Đọc context trong mã Spring:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

if (authentication == null) {
    throw new AccessDeniedException("No authentication in this task");
}

String username = authentication.getName();
boolean allowed = authentication.getAuthorities().stream()
        .anyMatch(a -> a.getAuthority().equals("REPORT_READ"));
~~~

Đây là **đoạn code đặt trong Spring-managed service**, cần imports của Spring Security. Không nên chỉ dựa vào `authentication != null` hoặc `isAuthenticated()` để kết luận principal là người dùng thật: anonymous authentication có cách biểu diễn riêng; dùng `AuthorizationManager`, policy và các điều kiện phù hợp để xác minh quyền.

### Vì sao sử dụng `ThreadLocal`?

`ThreadLocal` cho phép những hàm được gọi trong **cùng thread** đọc `SecurityContext` mà không phải truyền tham số qua từng method. Cách này hữu ích trong xử lý Servlet đồng bộ. Đổi lại, khi task được phân phối sang pool, chương trình không thể giả định worker có dữ liệu `ThreadLocal` của request.

Nếu worker không có context → method security có thể từ chối, service thấy anonymous hoặc gặp `NullPointerException` khi code đọc `getAuthentication().getName()`. Nếu worker mang context cũ → có nguy cơ **cross-user data exposure** và thực thi quyền sai. Hai tình huống đều phải được xử lý bằng contract propagation rõ ràng.

## 2. Phân biệt ba kiểu bất đồng bộ khác nhau

Từ “async” thường che ba tình huống không đồng nhất:

1. **Servlet async request/dispatch**: container duy trì một HTTP request trong chế độ bất đồng bộ, có thể chuyển công việc xử lý và sau đó dispatch lại.
2. **Spring MVC async controller**: controller trả `Callable<T>`, `WebAsyncTask<T>`, `DeferredResult<T>` hoặc kiểu kết quả được adapter async xử lý.
3. **Background task do ứng dụng tự chạy**: gửi job vào `Executor`/`ExecutorService`, `@Async`, `CompletableFuture`, scheduler hoặc tạo thread trực tiếp.

Cả ba có thể bắt đầu từ cùng một request, nhưng **không có nghĩa cùng một cơ chế truyền SecurityContext**.

| Tình huống | Hành vi mặc định cần biết | Cách xử lý khi cần đọc principal trong job |
| --- | --- | --- |
| Service đồng bộ trên thread request | Dùng context hiện hành ở cùng thread. | Không cần wrapper khác nếu không chuyển thread. |
| Spring MVC controller trả `Callable<T>` | Spring Security có tích hợp `WebAsyncManager` để đặt context cho thread chạy Callable. | Thường không cần wrapper riêng cho chính Callable; kiểm thử framework và security filter setup. |
| `DeferredResult<T>` được hoàn thành bởi executor do app dùng | **Không có tích hợp tự động cho phần công việc tùy ý** tạo/hoàn thành DeferredResult. | Sử dụng executor hoặc Runnable/Callable wrapper có propagation. |
| Servlet `AsyncContext.start(Runnable)` qua request wrapper Spring Security | Spring Security có tích hợp truyền context cho Runnable. | Bảo đảm async-supported/filter mapping phù hợp; kiểm thử thực tế. |
| `@Async` gọi qua Spring proxy | Spring chuyển method sang executor; context **phụ thuộc executor** được cấu hình. | Chọn `DelegatingSecurityContextAsyncTaskExecutor` hoặc cơ chế propagation tương thích. |
| `ExecutorService.submit`, `CompletableFuture.supplyAsync` | JDK executor thông thường **không sao chép SecurityContext**. | Wrap executor, submit qua delegating executor hoặc đưa identity vào job một cách an toàn. |
| Scheduler, job chạy sau nhiều phút | Không còn một HTTP request sống để lấy context theo cách thông thường. | Thiết kế service identity hoặc actor/permission snapshot có chính sách hết hạn/tái kiểm tra. |

Không thể nhìn tên hàm có chữ “async” rồi kết luận rằng Spring tự truyền quyền. Phải xác định **ai kiểm soát việc chọn thread và chạy task**.

## 3. Spring MVC `Callable`: trường hợp có tích hợp sẵn

Với Spring MVC trên Servlet stack, Spring Security tích hợp với **`WebAsyncManager`**. Khi controller trả `Callable`, framework có thể truyền `SecurityContext` đã có tại thời điểm **`startCallableProcessing`** vào thread thực thi Callable, rồi dọn context sau khi task hoàn tất.

Ví dụ controller đặt trong Spring Boot MVC:

~~~java
import java.util.concurrent.Callable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CallableController {

    @GetMapping("/async/callable")
    Callable<String> currentUser() {
        return () -> {
            Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
            return auth == null ? "anonymous" : auth.getName();
        };
    }
}
~~~

Đây là **ví dụ cần Spring Boot/Spring MVC/Spring Security dependencies**; không chạy độc lập chỉ với JDK. Khi test đã xác thực là Alice và Spring Security integration được cấu hình đúng, `Callable` sẽ đọc `Authentication` của Alice trong worker thread.

**Chi tiết quan trọng:** không mô tả cơ chế này đơn giản là “context được chụp khi `new Callable`”. Theo Spring Security, context dùng cho Callable gắn với thời điểm xử lý bắt đầu ở `WebAsyncManager.startCallableProcessing`. Nếu bạn thay đổi context giữa lúc tạo object Callable và lúc framework thực sự bắt đầu xử lý, nên xác minh chính xác hành vi qua integration test thay vì suy đoán từ closure Java.

Ở cuối async computation, Servlet container có thể thực hiện **`ASYNC` dispatch** để hoàn tất HTTP response. Việc khôi phục security context cho dispatch và việc gắn context vào **Callable worker** là các mắt xích khác nhau; chúng dựa vào filter registration, security context repository/strategy và cấu hình servlet. Cần kiểm tra cả controller execution lẫn phản hồi khi dùng custom filter hoặc nhiều security chains.

`WebAsyncTask` có liên quan đến nhánh Callable của MVC, nhưng nếu tự lồng executor hoặc `CompletableFuture` ở bên trong Callable thì những task phụ **không tự nhận toàn bộ propagation của Callable**. Chỉ work do cơ chế này quản lý mới được đảm bảo theo contract tương ứng.

## 4. `DeferredResult`: không có propagation tự động cho phần việc người dùng quản lý

`DeferredResult<T>` cho phép controller trả về một “lời hứa kết quả”, còn một tác vụ bất kỳ sẽ gọi `setResult(...)` hoặc `setErrorResult(...)` sau đó. Spring MVC không thể tự biết bạn đã gửi tác vụ vào executor nào, chạy trên thread nào và bắt đầu lúc nào; vì vậy **không có đảm bảo tự động gắn SecurityContext cho công việc hoàn thành `DeferredResult`**.

Ví dụ dễ gặp vấn đề:

~~~java
@GetMapping("/async/deferred")
DeferredResult<String> delayed() {
    DeferredResult<String> result = new DeferredResult<>(5000L);

    // rawExecutor là một Executor JDK/Spring CHƯA bọc security context.
    rawExecutor.execute(() -> {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        result.setResult(auth == null ? "anonymous" : auth.getName());
    });

    return result;
}
~~~

Đây là **mảnh minh họa nằm trong một Spring-managed controller**, cần bean `rawExecutor` và các imports; không phải file Java độc lập. Trong một pool mặc định, kết quả không được đảm bảo là user request; nó thường là `anonymous` hoặc context rỗng. Giải pháp đúng không phải tự đặt `SecurityContextHolder.setContext(...)` mà quên dọn, vì pool thread sẽ xử lý yêu cầu của người khác sau đó.

Một cách dùng executor đã được bọc:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.request.async.DeferredResult;

@RestController
class DeferredController {
    private final AsyncTaskExecutor securedTaskExecutor;

    DeferredController(
            @Qualifier("securedTaskExecutor")
            AsyncTaskExecutor securedTaskExecutor) {
        this.securedTaskExecutor = securedTaskExecutor;
    }

    @GetMapping("/async/deferred")
    DeferredResult<String> delayed() {
        DeferredResult<String> result = new DeferredResult<>(5000L);
        securedTaskExecutor.execute(() -> {
            try {
                Authentication auth =
                    SecurityContextHolder.getContext().getAuthentication();
                if (auth == null) {
                    result.setErrorResult(new IllegalStateException(
                            "Missing security context"));
                } else {
                    result.setResult(auth.getName());
                }
            } catch (Exception ex) {
                result.setErrorResult(ex);
            }
        });
        return result;
    }
}
~~~

Cấu hình bean `securedTaskExecutor` ở phần sau. Trong hệ thống thật, **không trả stacktrace/exception message thô cho người dùng**; exception mapper phải chuyển lỗi thành phản hồi an toàn. Ví dụ chỉ chứng minh điểm cần đặt context khi task chạy, không tự kiểm thử status 500/403 của app.

Nếu task có timeout, bị hủy hoặc client ngắt kết nối, hãy xác định cách giải phóng tài nguyên và cleanup context trong mọi đường đi. Propagation wrapper giúp dọn context của worker theo `finally`, nhưng không tự xử lý nghiệp vụ timeout/retry.

## 5. Tại sao `new Thread` hoặc `ExecutorService` thường không thấy principal?

Hãy xét:

~~~java
Authentication inRequest =
        SecurityContextHolder.getContext().getAuthentication();

executorService.submit(() -> {
    Authentication inWorker =
        SecurityContextHolder.getContext().getAuthentication();
    // Không được giả định inWorker == inRequest.
});
~~~

Mặc định, Java `ExecutorService` là bộ lập lịch và thực thi task, **không phải một cơ chế của Spring Security**. Nó không biết cần nhân bản `SecurityContext`, không biết principal của request nào và không tự cập nhật context khi người dùng chuyển.

Với thread pool, cùng một worker có thể chạy nhiệm vụ của Alice, rồi Bob:

~~~text
Request Alice (T1)  -> submit(Job A) -> Worker T8
Request Bob   (T2)  -> submit(Job B) -> Worker T8 (được tái sử dụng)

Sai:  T8.setContext(Alice); Job A; // không clear
      Job B tiếp tục thấy Alice -> rò rỉ danh tính

Đúng: chụp context tại thời điểm submit;
      trên T8 cài context phù hợp cho Job A;
      chạy Job A trong try;
      finally khôi phục/dọn context;
      khi Job B chạy sẽ có context của Bob nếu job B được bọc đúng.
~~~

Đặt `SecurityContextHolder.setContext(context)` ở đầu task mà không có `finally` để clear/restore có thể gây hậu quả nghiêm trọng khi task ném exception. Dùng các wrapper **`DelegatingSecurityContext...`** để framework quản lý vòng đời thay vì lặp lại đoạn code đó khắp service.

## 6. DelegatingSecurityContextRunnable và Callable hoạt động ra sao?

Spring Security cung cấp `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable<T>`, có nhiệm vụ:

1. Nhận task gốc và context cần sử dụng (có thể lấy từ `SecurityContextHolder` khi tạo wrapper).
2. Khi chạy task trên thread đích, đặt context tương ứng để code trong task có thể đọc `SecurityContextHolder`.
3. Gọi Runnable/Callable gốc.
4. Trong `finally`, dọn hoặc khôi phục context trước đó của worker theo triển khai/phiên bản, kể cả khi task ném exception.

Ví dụ gửi một `Runnable` với context hiện hành:

~~~java
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.context.SecurityContextHolder;

Runnable job = () -> {
    var auth = SecurityContextHolder.getContext().getAuthentication();
    // Gọi service đã được phân quyền, dùng auth trong policy nếu cần.
};

Runnable wrapped = new DelegatingSecurityContextRunnable(job);
executorService.submit(wrapped);
~~~

Đây là **mảnh code Spring**, `executorService` phải được quản lý vòng đời (pool shutdown), không phải file chạy độc lập. Constructor một tham số dùng context đang có tại lúc wrapper được tạo. Nếu tạo wrapper quá sớm rồi giữ lại trong cache hoặc queue lâu dài, đó có thể là **context cũ**, không phải principal của người thực sự đang kích hoạt tác vụ sau này.

Nếu cần explicit context trong một tình huống kiểm soát chặt:

~~~java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable wrapped =
    new DelegatingSecurityContextRunnable(job, captured);

executorService.execute(wrapped);
~~~

Điều này **không tạo một deep copy bất biến của SecurityContext**. `SecurityContext` và những đối tượng liên quan có thể mang trạng thái thay đổi; nếu cùng object được chia sẻ giữa các thread và có code sửa `Authentication`, cần kiểm tra tính thread-safe, phạm vi sử dụng và thời điểm thay đổi. Để thay `Authentication` thủ công, Spring Security khuyến nghị tạo **SecurityContext rỗng mới** rồi gọi `setAuthentication`, tránh sửa context chung đang được chia sẻ.

**Không truyền toàn bộ HTTP request/session hoặc JWT nguyên văn cho worker chỉ để lấy username.** Nếu tác vụ chỉ cần một actor ID, dùng input immutable tối thiểu có thể là giải pháp tốt hơn, nhất là với job dài hạn; quyền truy cập dữ liệu vẫn phải được kiểm tra tại điểm thực thi.

## 7. Executor được bọc: khuyến nghị cho `@Async`, DeferredResult và nhiều task

Thay vì bắt từng service biết đến `DelegatingSecurityContextRunnable`, có thể bọc **Executor** một lần. Các class thường dùng:

| Class Spring Security | Bao bọc đối tượng nào? | Dùng phù hợp |
| --- | --- | --- |
| `DelegatingSecurityContextExecutor` | `java.util.concurrent.Executor` | Gửi các `Runnable` bằng `execute`. |
| `DelegatingSecurityContextExecutorService` | `ExecutorService` | `submit` Runnable/Callable, `Future` và nhiều API `ExecutorService`. |
| `DelegatingSecurityContextAsyncTaskExecutor` | Spring `AsyncTaskExecutor` | Tích hợp với `@Async`, executor Spring, tác vụ Runnable/Callable. |
| `DelegatingSecurityContextTaskExecutor` | Spring `TaskExecutor` | Khi chỉ cần hợp đồng task executor. |
| `DelegatingSecurityContextSchedulingTaskExecutor` hoặc các class scheduling chuyên dụng | Executor lập lịch | Khi tích hợp cụ thể với scheduler và có identity thích hợp. |

**Có hai dạng context quan trọng:**

- Constructor **không truyền `SecurityContext` cố định**: các delegating executor thông thường lấy context của **thread gửi task tại thời điểm submit/execute**, rồi bọc task. Hợp với work on behalf of current user.
- Constructor **có truyền một `SecurityContext` cố định**: mọi task dùng cùng context được cung cấp. Chỉ dùng khi thật sự có một **service identity** được quản trị và được phép cho toàn bộ job, không vô tình cố định context của admin Alice tại lúc khởi tạo bean để mọi người khác hưởng quyền admin.

Một ví dụ cấu hình **Spring Boot 3 + Spring Security 6** có bean riêng cho `@Async` và `DeferredResult`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class SecuredAsyncConfiguration {

    @Bean("rawWorkerExecutor")
    ThreadPoolTaskExecutor rawWorkerExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(2);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(50);
        pool.setThreadNamePrefix("secured-worker-");
        return pool;
    }

    @Bean("securedTaskExecutor")
    AsyncTaskExecutor securedTaskExecutor(
            @Qualifier("rawWorkerExecutor")
            ThreadPoolTaskExecutor rawWorkerExecutor) {
        return new DelegatingSecurityContextAsyncTaskExecutor(
                rawWorkerExecutor);
    }
}
~~~

Khi `ThreadPoolTaskExecutor` là Spring bean, Spring quản lý khởi tạo/hủy theo lifecycle tương ứng. Đoạn trên **cần dependencies Spring Framework và Spring Security** và không thể biên dịch với JDK thuần. Việc đặt tên bean giúp tránh nhầm executor raw với secured. Không tự đưa tất cả scheduled jobs chạy dưới context người dùng request khi không có request.

Dùng trong service:

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class ReportAsyncService {

    @Async("securedTaskExecutor")
    public CompletableFuture<String> actorName() {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        if (auth == null) {
            return CompletableFuture.completedFuture("anonymous");
        }
        return CompletableFuture.completedFuture(auth.getName());
    }
}
~~~

Một bean khác gọi `reportAsyncService.actorName()` **qua Spring proxy** sẽ gửi method đến executor được nêu. `@EnableAsync` cho phép cơ chế `@Async`; lời gọi **self-invocation** kiểu `this.actorName()` bên trong cùng bean có thể bỏ qua proxy và chạy đồng bộ, không theo executor. Cũng cần kiểm soát exception handling của `@Async` và backpressure khi queue đầy.

**Tránh nhầm lẫn:** `@Async` không tự cấp role/permission; wrapped executor chỉ làm cho task thấy danh tính/authority tương ứng với lúc submit. Nếu tác vụ sửa dữ liệu, policy vẫn phải kiểm tra chủ sở hữu, tenant và trạng thái thực tế.

## 8. `CompletableFuture`: các stage có thể chạy trên những thread khác nhau

Một lỗi thường gặp:

~~~java
CompletableFuture.supplyAsync(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "anonymous" : a.getName();
});
~~~

Khi không truyền `Executor` riêng, `CompletableFuture.supplyAsync` sử dụng **default async execution facility** của JDK (thường là common ForkJoinPool). Nó không tự hiểu `SecurityContextHolder` của Servlet request. Không thể dựa vào việc một môi trường test dùng thread “tình cờ” giống thread request.

Nếu bạn đã cấu hình executor truyền context, hãy chỉ định **chính executor đó** cho các stage cần context:

~~~java
CompletableFuture<String> future = CompletableFuture.supplyAsync(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    return a == null ? "anonymous" : a.getName();
}, securedTaskExecutor);
~~~

Đoạn này giả định `securedTaskExecutor` là bean `AsyncTaskExecutor` ở phần trên, cũng triển khai `Executor`. Với `CompletableFuture` chuỗi stage:

~~~java
future.thenApply(name -> name.toUpperCase());       // không có hợp đồng đổi thread
future.thenApplyAsync(name -> name.toUpperCase());  // có thể vào common pool
future.thenApplyAsync(name -> name.toUpperCase(),
                      securedTaskExecutor);         // dùng executor chỉ định
~~~

Nếu stage phụ cần `Authentication`, đừng suy rằng bởi stage đầu được bọc nên toàn bộ `thenApplyAsync` kế tiếp tự mang cùng context. **Mỗi ranh giới scheduling bất đồng bộ phải được kiểm tra.** Khi stage được đăng ký sau khi request đã hoàn tất, động thái capture context ở thời điểm đăng ký/submit có thể không còn principal gốc; cần thiết kế actor context như một input rõ ràng, hoặc wrapper đúng tại điểm có thể tin cậy.

Các non-async stage như `thenApply` có thể chạy trên thread hoàn tất stage trước hoặc thread đăng ký nếu future đã hoàn tất; **không lấy giả định về thread scheduling làm chính sách bảo mật**. `CompletionStage` không phải tự thân là security context carrier.

## 9. Servlet `AsyncContext.start` và ASYNC redispatch

Ngoài Spring MVC, Servlet API có:

~~~java
AsyncContext async = request.startAsync();
async.start(() -> {
    Authentication a =
        SecurityContextHolder.getContext().getAuthentication();
    // Có thể đọc context khi đi qua tích hợp của Spring Security
    // và Servlet async request wrapper được cấu hình thích hợp.
    async.complete();
});
~~~

Spring Security có tích hợp với `AsyncContext.start(Runnable)` để truyền context của request vào Runnable. Tuy nhiên, điều này **không có nghĩa** mọi cách tạo thread trong Servlet đều tự được bọc. Chỉ áp dụng khi request được xử lý qua tích hợp Servlet API của Spring Security và async support đã thiết lập đúng.

**ASYNC dispatch** là lượt đi tiếp trong Servlet container sau khi xử lý bất đồng bộ. Phải phân biệt:

- Worker thread chạy Callable hoặc Runnable có security context theo cơ chế propagation.
- Request được Servlet container **dispatch lại** với `DispatcherType.ASYNC`, có thể đi qua filter chain tùy filter mapping và cấu hình.
- Những filter khác nhau (bao gồm custom `OncePerRequestFilter`) có thể áp dụng quy tắc riêng cho dispatch ban đầu và dispatch tiếp theo.

Với cấu hình Spring Boot Servlet hiện đại, async support thường được auto-configure phù hợp. Nếu ứng dụng cũ đăng ký `DelegatingFilterProxy` qua `web.xml` hoặc tự đăng ký filter, cần bảo đảm `async-supported` và dispatcher types, thường gồm **`REQUEST`** và **`ASYNC`**, phù hợp với thiết kế; nếu không, việc quản lý context khi redispatch có thể khác kỳ vọng.

**AuthorizationFilter** có thể kiểm tra nhiều dispatcher types. Khi dùng `authorizeHttpRequests`, xem lại chính sách đối với `DispatcherType.ASYNC` và `ERROR`: không tự `permitAll` mọi ASYNC dispatch chỉ để chữa 403, vì sẽ thay đổi ranh giới authorization ở lượt dispatch. Thay vào đó, xác định chain, matcher và context ở từng lượt; nếu cần ngoại lệ dispatcher, khai báo hẹp và test quyền ở request gốc vẫn được giữ.

## 10. MODE_INHERITABLETHREADLOCAL và MODE_GLOBAL có giải quyết được mọi thứ không?

Spring Security cho phép thay đổi `SecurityContextHolderStrategy`, ví dụ:

- **`MODE_THREADLOCAL`**: mặc định phù hợp đa số Servlet apps; context theo thread.
- **`MODE_INHERITABLETHREADLOCAL`**: một thread con *được tạo mới* có thể nhận giá trị context lúc thread được tạo. **Không phải cơ chế truyền danh tính an toàn cho pool đã tồn tại**.
- **`MODE_GLOBAL`**: dùng một holder toàn tiến trình; **không phù hợp server nhiều người dùng**, có nguy cơ tài khoản này ghi đè context của tài khoản khác.

**Vì sao InheritableThreadLocal nguy hiểm với thread pool?** Worker thread có thể được tạo từ lâu khi một user tình cờ khởi tạo pool. Những request về sau chỉ **tái sử dụng worker**, không tạo lại thread, nên inherited context có thể **cũ**, không phải context của request hiện tại. Ngay cả ở thread con mới, các object context bên trong có thể được chia sẻ và thay đổi. Kết quả có thể là rò rỉ quyền hoặc test chạy đúng trên local nhưng sai dưới tải production.

Đổi strategy toàn app để cứu một `@Async` thiếu context thường là giải pháp quá rộng. **Ưu tiên wrapper/executor theo tác vụ**, kiểm tra lifecycle và xác thực lại nếu quyền thay đổi. Không dùng `MODE_GLOBAL` trong Servlet app phục vụ nhiều user.

## 11. Tính nhất quán và bảo mật của context được truyền sang worker

Có context đúng ở worker **không đồng nghĩa** quyền của task là vĩnh viễn hợp lệ:

1. **Thời điểm capture:** một wrapper có thể chụp context khi submit task. Nếu queue chờ 20 phút, user có thể đã bị thu hồi quyền.
2. **Thời điểm chạy:** task có thể cần kiểm tra lại quyền và resource state ở server (tenant, owner, trạng thái, hạn mức) ngay trước side effect.
3. **Mutable context:** `SecurityContext` không tự trở thành snapshot bất biến sâu; tránh thay `Authentication` trong context đang dùng chung nhiều thread.
4. **Phân vùng dữ liệu:** user có `ORDER_APPROVE` lúc submit không cho phép duyệt mọi đơn, đặc biệt khác tenant.
5. **Timeout và cancellation:** task có thể tiếp tục chạy sau khi client ngắt kết nối; phải có điều kiện hủy/job ownership và idempotency.
6. **Audit:** ghi actor hợp lệ, thời điểm và lý do tác vụ; không giả định thread name hoặc MDC là proof of identity.
7. **Không vận chuyển bí mật:** tránh đưa raw JWT, password, cookie hoặc Servlet request object vào queue lâu dài. Nếu task cần service credential, dùng cơ chế cấp credential/service identity riêng có quản lý vòng đời.
8. **Không truyền context vượt trust boundary tùy tiện:** executor cùng process khác hẳn việc publish message sang Kafka/RabbitMQ hoặc đẩy job sang service khác. Spring `ThreadLocal` **không tự đi qua network/process**.

Với background jobs dài, cách rõ ràng thường là truyền **jobId + actorId + tenantId + action** như dữ liệu immutable đã được xác minh; worker đọc lại chính sách lúc chạy hoặc dùng một service identity được cấp quyền tối thiểu. Việc truyền actor ID **không tự thay thế authorization**: bên nhận phải kiểm chứng nguồn event/queue, scope và quyền hiệu lực.

### “Được chạy với quyền của người dùng” và “được phép làm công việc” khác nhau

Một thao tác export báo cáo có thể được submit lúc Alice được cấp `REPORT_EXPORT`. Khi executor truyền context, code có thể đọc `Authentication` của Alice. Nhưng để xuất tất cả đơn của tenant, service vẫn cần kiểm tra:

~~~text
actor.role/authority (REPORT_EXPORT)
  AND report.tenant == actor.currentTenant
  AND report.owner/sharedScope is allowed
  AND export job still eligible
  AND quota/consent/business checks are valid
~~~

Một `Authentication` từ lúc submit không tự bảo đảm tất cả điều kiện này còn đúng sau delay. Với tác vụ nhạy cảm, cần cách rõ ràng để hủy hoặc kiểm tra lại quyền trước khi sinh file/gửi email/thực hiện ghi dữ liệu.

## 12. Java 17+ độc lập: ThreadLocal, capture và cleanup khi dùng thread pool

Ví dụ chạy độc lập dưới đây không dùng Spring Security; nó mô phỏng một **principal theo thread** bằng `ThreadLocal<String>` và một wrapper `Callable` chụp giá trị ở thread gửi task. Nó có ý nghĩa dạy nguyên lý, **không phải bản thay thế** các class `DelegatingSecurityContext...` của Spring.

Thiết kế:

- Request Alice đặt context vào thread chính.
- Pool một thread ban đầu không thấy context của Alice.
- Wrapper capture Alice để chạy trên pool, rồi `finally` dọn/khôi phục context worker.
- Khi thread chính chuyển sang Bob, wrapper **đã được tạo trước đó** vẫn giữ Alice; wrapper mới sẽ mang Bob.
- Một task được bọc ném exception nhưng worker sau đó vẫn anonymous, chứng minh cleanup hoạt động.

Lưu chính xác thành **`ThreadContextPropagationDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadContextPropagationDemo {
    private static final ThreadLocal<String> ACTOR = new ThreadLocal<>();

    static String currentActor() {
        return ACTOR.get() == null ? "anonymous" : ACTOR.get();
    }

    static <T> Callable<T> capture(Callable<T> task) {
        String capturedActor = ACTOR.get();
        return () -> {
            String previousActor = ACTOR.get();
            try {
                if (capturedActor == null) ACTOR.remove();
                else ACTOR.set(capturedActor);
                return task.call();
            } finally {
                if (previousActor == null) ACTOR.remove();
                else ACTOR.set(previousActor);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            ACTOR.set("alice");
            System.out.println("request alice: " + currentActor());
            System.out.println("plain pool: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());
            Callable<String> aliceTask = capture(
                    ThreadContextPropagationDemo::currentActor);
            System.out.println("wrapped alice: " + pool.submit(aliceTask).get());
            System.out.println("pool after alice: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());

            ACTOR.set("bob");
            System.out.println("captured before switch: "
                    + pool.submit(aliceTask).get());
            System.out.println("wrapped bob: "
                    + pool.submit(capture(
                            ThreadContextPropagationDemo::currentActor)).get());
            try {
                pool.submit(capture(() -> {
                    throw new IllegalStateException("expected");
                })).get();
            } catch (ExecutionException ex) {
                System.out.println("wrapped task failed: "
                        + ex.getCause().getMessage());
            }
            System.out.println("pool after failure: "
                    + pool.submit(ThreadContextPropagationDemo::currentActor).get());
        } finally {
            ACTOR.remove();
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 ThreadContextPropagationDemo.java
java ThreadContextPropagationDemo
~~~

Kết quả chuẩn:

~~~text
request alice: alice
plain pool: anonymous
wrapped alice: alice
pool after alice: anonymous
captured before switch: alice
wrapped bob: bob
wrapped task failed: expected
pool after failure: anonymous
~~~

**Đọc kết quả:**

- `plain pool: anonymous` chứng minh `ThreadLocal` ở thread gọi `submit` không tự sang worker.
- `wrapped alice: alice` có được nhờ chụp context và cài nó vào worker.
- `pool after alice: anonymous` và `pool after failure: anonymous` chứng minh dọn context bằng `finally` kể cả khi task lỗi.
- `captured before switch: alice` cảnh báo snapshot đã gắn vào wrapper cũ: một caller Bob gửi lại wrapper của Alice sẽ gây chạy với Alice. **Đừng tái sử dụng wrapped task/context của người khác.**
- `wrapped bob: bob` cho thấy task của Bob được bọc riêng mang đúng identity.

Wrapper của demo có `String` immutable, đơn giản hơn `SecurityContext` thật. Với Spring, dùng class do framework cung cấp, tuân thủ ràng buộc truyền/lưu context và không tự tạo global `ThreadLocal` chứa token.

## 13. Truyền Authentication bằng tham số có tốt hơn dùng ThreadLocal không?

Không có một đáp án đúng cho mọi trường hợp; phụ thuộc tác vụ cần context để làm gì.

### Tình huống A — Task gọi service dùng method security

Nếu service được bảo vệ bởi `@PreAuthorize("hasAuthority('REPORT_EXPORT')")` và kiểm tra quyền thông qua `SecurityContextHolder`, worker cần có context phù hợp **khi gọi method** hoặc phải thiết kế cách cấp một `Authentication` tin cậy riêng. Lúc này `DelegatingSecurityContextAsyncTaskExecutor` hoặc `DelegatingSecurityContextExecutorService` là công cụ phù hợp cho job ngắn cùng process.

### Tình huống B — Task chỉ cần actor ID cho audit

Nếu job không có yêu cầu Spring method security và chỉ cần biết actor để ghi audit, truyền `actorId` immutable vào đối tượng command có thể đơn giản, dễ test và ít rò context. Nhưng không được tự coi ID đó là quyền truy cập; policy tại worker vẫn phải được kiểm tra.

### Tình huống C — Task chạy ngoài request hoặc qua message queue

Job chạy theo lịch và event consumer không tự có HTTP context. Nên dùng **service principal/authorization context rõ ràng**, credential và scope được quản lý, hoặc kiểm tra quyền theo domain. `SecurityContextHolder.getContext()` trống ở worker là tình trạng bình thường, không phải bug cần sửa bằng `MODE_GLOBAL`.

### Tình huống D — Task dài và quyền thay đổi thường xuyên

Chỉ lưu `SecurityContext` từ lúc submit có nguy cơ stale. Nên thiết kế **authorization ở execution time**, refresh/revocation và giới hạn thao tác theo tenant, owner, trạng thái thực tế. Có thể kết hợp propagated context để audit user ban đầu với decision policy dùng dữ liệu hiện thời. Không dùng principal snapshot như một token quyền vô hạn.

## 14. SecurityContext propagation không đồng nghĩa truyền mọi ngữ cảnh khác

Trong web apps, ngoài `SecurityContextHolder` còn có:

- `RequestContextHolder` và `ServletRequestAttributes`.
- Logging MDC (request ID, trace ID, tenant debug tag).
- Transaction context gắn thread bởi Spring Transaction.
- Locale, tracing/observation context và các `ThreadLocal` ứng dụng khác.

**DelegatingSecurityContextExecutor chỉ truyền Spring Security context theo cơ chế của nó**, không mặc nhiên truyền MDC, transaction, request attributes hay mọi `ThreadLocal` khác. Một task có `Authentication` đúng nhưng MDC rỗng không chứng tỏ security propagation sai. Ngược lại, một task có MDC `user=alice` **không phải bằng chứng** nó có `Authentication` của Alice.

Không copy toàn bộ `ServletRequestAttributes` sang job lâu dài chỉ để đọc tenant/request ID: request có vòng đời ngắn, có thể bị recycle/cleanup. Trích xuất metadata cần thiết thành immutable command và giới hạn sự lưu trữ thông tin nhạy cảm.

Các công cụ context-propagation chung hoặc `TaskDecorator` cần được cấu hình cẩn thận để không copy security context hai lần hoặc giữ reference quá lâu. Khi một app dùng cả Spring Security wrapper và thư viện context propagation khác, phải xác định **nguồn chính** cho authentication và có test xác minh cleanup/cross-user isolation.

## 15. Kiểm thử đúng: asyncDispatch, concurrent users và trường hợp exception

**Chỉ test controller đồng bộ không đủ**. Một test `SecurityContextHolder` trên thread gọi method chưa chứng minh worker thread nhìn thấy context phù hợp. Đối với Spring MVC async, dùng `spring-security-test` và `MockMvc` để xác nhận cả giai đoạn chờ và dispatch kết quả.

Ví dụ test `Callable` với một controller như mục 3:

~~~java
MvcResult result = mvc.perform(
        get("/async/callable")
            .with(user("alice").roles("USER")))
    .andExpect(request().asyncStarted())
    .andReturn();

mvc.perform(asyncDispatch(result))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
~~~

Đây là **trích đoạn trong Spring Boot/JUnit/MockMvc test**, cần `MockMvc` inject, Spring Security Test, static imports tương ứng, endpoint fixture và filter chain được tích hợp vào MockMvc. Nó minh họa test hai giai đoạn, không phải chương trình Java chạy độc lập.

Đối với service `@Async`, kiểm tra phương thức được gọi **qua Spring bean/proxy** và executor có tên `securedTaskExecutor`, không chỉ gọi trực tiếp một instance mới bằng `new`. Có thể dùng `CountDownLatch` hoặc `Future.get(timeout)` trong test để kiểm soát completion và tránh race condition; đừng dùng `Thread.sleep(...)` như bằng chứng tin cậy.

Ma trận kiểm thử nên có:

| Trường hợp | Điều cần kiểm chứng |
| --- | --- |
| Request Alice → `Callable` MVC | Worker đọc đúng `Authentication` Alice; response đúng mong đợi. |
| Request Bob → `Callable` khác | Không thấy Alice dù thread pool được tái sử dụng. |
| `DeferredResult` dùng raw executor | Không giả định context request tự xuất hiện ở worker. |
| `DeferredResult` dùng secured executor | Task đọc đúng identity, kết quả được chuyển về async response. |
| `@Async` qua Spring proxy | Executor được cấu hình đúng, policy bên trong task thấy principal phù hợp. |
| `@Async` tự gọi trong cùng class | Phát hiện việc bỏ qua proxy/không async như tưởng tượng. |
| `CompletableFuture.supplyAsync` không truyền executor | Không suy ra có context; test đúng thực tế JDK executor. |
| `thenApplyAsync` sau stage có context | Kiểm tra stage dùng executor nào, không tự nhận context từ stage trước. |
| Task lỗi trước khi return | Worker thread được dọn context trong `finally`. |
| Alice task rồi Bob task trên cùng pool | Bob không thể nhìn thấy Alice; tránh rò dữ liệu xuyên người dùng. |
| Pool queue chờ lâu và quyền bị thu hồi | Policy execution-time chặn job nhạy cảm nếu quyền không còn hợp lệ. |
| Anonymous hoặc thiếu quyền | Fail closed hoặc trả lỗi được thiết kế, không gán service/admin context tùy tiện. |
| HTTP ASYNC dispatch | Đúng security chain/matcher và response khi redispatch; không tự permit mọi ASYNC. |
| Job được chạy từ scheduler không có HTTP request | Dùng service identity/command rõ ràng, không phụ thuộc `SecurityContextHolder` có user. |

Trong test truyền context qua pool, cách mạnh là khởi tạo **pool một thread** rồi lần lượt chạy A và B để buộc tái sử dụng worker, kiểm tra sau mỗi job context sạch. Với pool nhiều thread, cần thiết kế test có đồng bộ hóa để thực sự quan sát lại cùng thread, tránh kết luận “không rò” chỉ vì scheduler chọn worker khác.

Nếu một test có `@WithMockUser`, đó là context được test framework thiết lập cho thread test/HTTP request; **không** biến mọi `ExecutorService` dùng trong test thành executor có propagation. Phải kiểm chứng lớp wrapper/bean thật.

## 16. Chẩn đoán lỗi thường gặp

### “Controller thấy user, nhưng `@Async` thấy null”

Kiểm tra lần lượt:

1. `@EnableAsync` đã được bật chưa? Method có được gọi qua Spring proxy hay là self-invocation?
2. Bean executor mà `@Async` sử dụng là bean nào? Có đúng `securedTaskExecutor` không?
3. Task được submit từ thread có context hợp lệ **tại đúng thời điểm submit** không?
4. Có stage `CompletableFuture` phụ dùng common pool sau đó không?
5. Có lớp nào tự clear context trước khi submit hoặc tạo wrapper quá sớm không?
6. Có một security context strategy tùy chỉnh hoặc custom filter thay đổi cách lưu context không?

Không sửa bằng cách đặt `SecurityContextHolder.MODE_GLOBAL` hay hard-code admin credentials cho worker.

### “Job của Bob lại chạy với quyền của Alice”

Đây là **lỗi nghiêm trọng**. Tìm:

- Code gọi `SecurityContextHolder.setContext(...)` không có `finally`.
- `InheritableThreadLocal` với pooled threads hoặc custom `ThreadLocal` bị giữ lại.
- Executor bean được tạo bằng **fixed SecurityContext của Alice** thay vì lấy context per submit.
- `Runnable` hoặc `Callable` đã được bọc cho Alice rồi bị cache, re-submit dưới request Bob.
- Object `SecurityContext` được chia sẻ và bị mutate từ thread khác.
- Một custom task decorator hoặc listener để lại MDC/security state cũ.

Tạm ngưng hành động nhạy cảm và kiểm tra phạm vi ảnh hưởng, log audit và isolation trước khi đưa fix vào production. Sau đó thêm regression test A→B→A trên cùng worker và test exception path.

### “Task chạy xong nhưng HTTP request chưa trả về”

Context propagation không làm job tự gửi HTTP response: với `DeferredResult`, phải gọi `setResult`/`setErrorResult`; với Servlet async phải hoàn tất `AsyncContext`, và với MVC Callable framework quản lý completion. Xem timeout, executor rejection, deadlock, futures chưa await, controller mapping và ASYNC redispatch. Không đồng nhất “đã có principal” với “lifecycle request đúng”.

### “MDC có trace nhưng authentication không có”

MDC và `SecurityContextHolder` là hai context khác nhau; framework hoặc instrumentation có thể truyền MDC mà không truyền SecurityContext. Kiểm tra riêng executor và propagation mechanism. Tránh dùng `MDC.get("user")` để quyết định quyền.

### “Request async trả 403 ở lượt dispatch cuối”

Kiểm tra dispatcher type, `AuthorizationFilter`, `securityMatcher`, role/authority thực tế và filter registration cho ASYNC. Nếu custom filter bị gọi lại, xem `shouldNotFilterAsyncDispatch()` và chính sách auth ở filter đó. Không dùng `requestMatchers("/**").permitAll()` chỉ để che lỗi async vì sẽ mở mọi endpoint.

## 17. Checklist triển khai an toàn

1. Xác định loại async: Spring MVC `Callable`, `DeferredResult`, Servlet `AsyncContext`, `@Async`, JDK executor hay scheduler.
2. Phân biệt thread request với thread chạy task; nêu rõ **ai tạo context** và **thời điểm context được capture**.
3. Với `Callable` MVC, kiểm tra tích hợp `WebAsyncManager` và test `asyncDispatch`.
4. Với task do app sở hữu, dùng `DelegatingSecurityContextRunnable`/`Callable` hoặc **delegating executor** tương ứng.
5. Chọn per-submit context cho work on behalf of user; fixed context chỉ cho tác vụ/service identity đã được quản trị.
6. Không dùng `MODE_GLOBAL` trong server nhiều user và không dựa vào `MODE_INHERITABLETHREADLOCAL` để truyền context trên thread pool.
7. Đảm bảo dọn/khôi phục context trong `finally` kể cả khi task exception, timeout hoặc hủy.
8. Với `@Async`, bật proxy qua `@EnableAsync`, gọi từ bean khác và chỉ định đúng executor.
9. Với `CompletableFuture`, truyền executor cho mọi async stage cần context; không tin default common pool.
10. Không nhầm truyền Spring Security context với MDC, request scope, transaction hoặc dữ liệu HTTP.
11. Không coi context snapshot là phép cấp quyền vĩnh viễn; kiểm tra tài nguyên, tenant và quyền mới nhất ở điểm thực thi nếu nghiệp vụ yêu cầu.
12. Test cùng worker phục vụ Alice rồi Bob, task lỗi, task chờ lâu, anonymous, revocation và ASYNC redispatch.
13. Dùng actor ID/service identity rõ ràng cho scheduler, queue hoặc tác vụ cross-process; không gửi raw JWT hay Servlet request object vào job lâu dài.
14. Không dùng việc tắt toàn bộ security filter chain, tắt authorization hoặc gán quyền admin mặc định để chữa lỗi thiếu SecurityContext.

**Kết luận:** `SecurityContextHolder` ở Servlet stack mặc định chỉ đảm bảo context trên **thread hiện tại**. Spring Security có tích hợp tự động cho **Spring MVC Callable** và **`AsyncContext.start`** trong điều kiện thích hợp, nhưng **không tự truyền context cho mọi task do ứng dụng lập lịch**, nhất là `DeferredResult`, `@Async` chưa dùng executor phù hợp và `CompletableFuture` với common pool. Hãy chọn cơ chế propagation cho đúng ranh giới thread, chụp context đúng thời điểm, dọn worker ngay cả khi lỗi và luôn phân biệt **identity được mang theo** với **quyền nghiệp vụ còn hợp lệ**.

### Tài liệu tham khảo chính thức

- [Spring Security — Servlet Authentication Architecture và SecurityContextHolder](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Spring Security 6.5 — Spring MVC Async Integration: Callable và DeferredResult](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html)
- [Spring Security — Servlet API Integration: AsyncContext.start(Runnable)](https://docs.spring.io/spring-security/reference/servlet/integrations/servlet-api.html)
- [Spring Security 6.5 — DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html)
- [Spring Security 6.5 — DelegatingSecurityContextExecutorService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html)
- [Spring Framework — Spring MVC Async Requests](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html)
