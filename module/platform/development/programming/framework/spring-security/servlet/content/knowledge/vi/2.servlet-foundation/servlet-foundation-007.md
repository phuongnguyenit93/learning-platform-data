# Vòng đời luồng xử lý và giới hạn của `ThreadLocal` trong ứng dụng web

> **Ngữ cảnh:** Nền tảng Servlet, Java 17+, ứng dụng web dùng Spring Security trên Servlet stack. Bài tập trung vào quan hệ giữa **request HTTP**, **thread của Servlet container** và **ngữ cảnh gắn với thread**. Những ví dụ chỉ dùng Java SE được ghi rõ; đoạn dùng Spring/Spring Security cần thư viện và vòng đời ứng dụng tương ứng.

## 1. Cần phân biệt ba vòng đời

- **HTTP request:** bắt đầu khi máy chủ nhận yêu cầu và kết thúc khi việc xử lý/ghi phản hồi hoàn tất (trường hợp bất đồng bộ có thể kéo dài sau khi thread ban đầu đã rời filter chain).
- **Thread xử lý:** là tài nguyên thực thi do Servlet container hoặc executor quản lý. Một thread có thể phục vụ nhiều request nối tiếp; một request bất đồng bộ có thể được xử lý qua nhiều thread.
- **Giá trị `ThreadLocal`:** thuộc về **thread đang thực thi**, tồn tại cho tới khi bị thay thế, gọi `remove()`, hoặc chính thread kết thúc. Nó không tự biến mất chỉ vì một request đã trả phản hồi.

Bởi vậy, quan hệ “một request = một thread = một vùng nhớ riêng” chỉ gần đúng ở một **đoạn xử lý đồng bộ**, và không phải cam kết của Servlet API. Đây là gốc của các lỗi rò rỉ thông tin giữa request, đọc sai người dùng và mất context khi chạy bất đồng bộ.

### Luồng Servlet đồng bộ điển hình

~~~text
Client gửi HTTP request
  -> Servlet container nhận và phân công thread T1 từ pool
  -> Servlet Filter chain (có Spring Security filters)
  -> DispatcherServlet -> Controller -> Service -> trả kết quả
  -> Filter chain kết thúc; các context đã bind được dọn trong finally
  -> T1 quay lại pool và có thể phục vụ request khác
~~~

Trong quá trình đó, filter bảo mật có thể cung cấp `SecurityContext` cho thread hiện tại; controller/service truy cập qua `SecurityContextHolder`. Khi chain rời đi, việc dọn trạng thái gắn thread phải xảy ra, kể cả khi có exception. **Thread vẫn sống** trong pool, nên giá trị còn sót có thể xuất hiện ở request tiếp theo.

## 2. `ThreadLocal<T>` thật sự làm gì?

`ThreadLocal<T>` là một khóa giúp mỗi `Thread` lưu một giá trị riêng. Với cùng một đối tượng `ThreadLocal`, thread T1 có thể thấy `alice`, còn T2 thấy `bob`. Một biến `static ThreadLocal<?>` là **khóa được chia sẻ**, không có nghĩa giá trị lưu bên trong được chia sẻ giữa tất cả các thread.

Các thao tác chính:

| API | Ý nghĩa |
| --- | --- |
| `set(value)` | Đặt giá trị cho **thread hiện tại**. |
| `get()` | Đọc giá trị trên thread hiện tại; mặc định là `null` nếu chưa có giá trị và không khai báo `initialValue`. |
| `remove()` | Bỏ liên kết giá trị của thread hiện tại, cho lần dùng sau bắt đầu sạch. |
| `ThreadLocal.withInitial(supplier)` | Cấp giá trị ban đầu theo từng thread; **không** thay thế nhu cầu dọn trạng thái theo request. |

`ThreadLocal` không mang theo thông tin sang thread của `ExecutorService`, `CompletableFuture` hay Servlet async một cách tự động. Nó cũng không phải nơi lưu session, dữ liệu nghiệp vụ dài hạn hoặc phương tiện truyền thông tin giữa các thread.

### Vì sao thread pool dễ gây lỗi?

Container giữ thread để tái sử dụng. Nếu request A gắn `alice` lên T1 nhưng quên `remove()`, request B sau đó được phân vào đúng T1 có thể đọc lại `alice`. Nếu T2 xử lý request B thì lỗi có thể “biến mất”, khiến kiểm thử ít tải không phát hiện. Dùng `set(null)` không diễn đạt rõ thao tác tháo binding và có thể để lại entry; ưu tiên `remove()`.

## 3. Thí nghiệm Java 17: rò rỉ qua thread tái sử dụng

Tạo tệp **`ThreadLocalLifecycleDemo.java`**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalLifecycleDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> {
                CURRENT_USER.set("alice");
                System.out.println("A: " + CURRENT_USER.get());
                // Cố ý quên CURRENT_USER.remove().
            }).get();

            pool.submit(() ->
                System.out.println("B: " + CURRENT_USER.get())
            ).get();

            pool.submit(() -> {
                CURRENT_USER.set("carol");
                try {
                    System.out.println("C: " + CURRENT_USER.get());
                } finally {
                    CURRENT_USER.remove();
                }
            }).get();

            pool.submit(() ->
                System.out.println("D: " + CURRENT_USER.get())
            ).get();
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac ThreadLocalLifecycleDemo.java
java ThreadLocalLifecycleDemo
~~~

Kết quả chính xác:

~~~text
A: alice
B: alice
C: carol
D: null
~~~

`newSingleThreadExecutor()` bảo đảm cả bốn task chạy tuần tự trên cùng một worker thread; `Future.get()` đợi từng task xong. Task B **không tự đặt** người dùng nhưng vẫn nhìn thấy `alice` do task A bỏ qua cleanup. Task C đặt giá trị mới rồi dọn trong `finally`, vì thế D thấy `null`. Ví dụ này mô phỏng cơ chế tái sử dụng thread, **không phải** mô phỏng đầy đủ Servlet container hay Spring Security.

Bài học: mã nào tự quản lý `ThreadLocal` phải có cặp **bind → làm việc → remove trong finally**. Nếu dùng framework quản lý context, hãy để đúng thành phần của framework phụ trách dọn dẹp.

## 4. Mẫu sử dụng an toàn trong Servlet filter

Ví dụ sau minh họa một context tùy chỉnh (request ID), trong ứng dụng Jakarta Servlet dùng `jakarta.servlet-api`. Đây là **một lớp tích hợp**, không phải chương trình Java SE độc lập.

~~~java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import java.io.IOException;
import java.util.UUID;

public final class RequestIdFilter implements Filter {
    private static final ThreadLocal<String> REQUEST_ID = new ThreadLocal<>();

    public static String currentRequestId() {
        return REQUEST_ID.get();
    }

    @Override
    public void doFilter(ServletRequest request,
                         ServletResponse response,
                         FilterChain chain)
            throws IOException, ServletException {
        REQUEST_ID.set(UUID.randomUUID().toString());
        try {
            chain.doFilter(request, response);
        } finally {
            REQUEST_ID.remove();
        }
    }
}
~~~

Filter cần được đăng ký vào ứng dụng bằng cấu hình Servlet/Spring phù hợp. Bất kể controller trả về bình thường hay ném exception, `finally` vẫn dọn binding của **thread đang chạy filter**. Nếu logic trước `try` có thể ném lỗi sau khi đã bind, hãy đưa nó vào khối được bảo vệ tương ứng; ví dụ dùng `UUID.randomUUID()` trước `set` để tránh tình huống đó.

**Giới hạn quan trọng:** `finally` ở lần dispatch hiện tại không đồng nghĩa toàn bộ request HTTP đã kết thúc nếu request bật async; giá trị `ThreadLocal` này không tự có trên thread xử lý bất đồng bộ. Nếu chỉ cần ID xuyên suốt request, hãy cân nhắc **request attribute** và truyền ID vào công việc nền, thay vì trông đợi `ThreadLocal` tồn tại xuyên thread. Cũng cần xử lý trường hợp nested invocation hoặc filter dispatch lại: đặt giá trị mới rồi `remove()` sẽ không phục hồi giá trị cũ của thread. Với mã có thể lồng nhau, phải xác định rõ chính sách restore giá trị cũ; đừng áp dụng mẫu này máy móc.

Ví dụ request attribute không lệ thuộc vào thread:

~~~java
String requestId = UUID.randomUUID().toString();
request.setAttribute("requestId", requestId);
chain.doFilter(request, response);
~~~

Đoạn thứ hai là mảnh code nằm trong filter có biến `request`, `response`, `chain` và import phù hợp; request attribute gắn với `ServletRequest`, nên đọc được từ các bước còn giữ cùng request object. Không dùng nó sau khi vòng đời request chấm dứt.

## 5. Điều gì thay đổi khi HTTP request bất đồng bộ?

Ở Servlet async, một request có thể trải qua nhiều nhịp thực thi:

~~~text
T1: nhận request -> filter/controller -> startAsync() hoặc MVC bắt đầu async
T1: rời lần dispatch đầu, được trả lại pool (request vẫn chưa hoàn tất)
T2: executor thực thi công việc bất đồng bộ
T3: container có thể ASYNC-dispatch để hoàn tất response
     (T1, T2, T3 có thể trùng hoặc khác nhau; không được giả định)
~~~

- Giá trị gắn với T1 qua `ThreadLocal` **không tự chuyển** sang T2/T3.
- Cố giữ giá trị trên T1 “cho đến khi async xong” gây nguy cơ rò sang request khác do T1 đã được pool tái sử dụng.
- `InheritableThreadLocal` chỉ cho phép thread **mới tạo** kế thừa giá trị từ thread cha tại thời điểm tạo thread (thường là cùng tham chiếu với object mutable). Nó không cập nhật an toàn cho task chạy trên thread pool đã tồn tại; vì vậy không nên dùng nó như cách lan truyền danh tính cho request.
- Servlet `AsyncContext.start(...)`, `CompletableFuture.supplyAsync(...)`, `@Async` và executor tự tạo cần kiểm tra **riêng cơ chế truyền context**. `CompletableFuture` mặc định có thể dùng common pool, nơi không có request context của caller.

Có ba hướng kiểm soát đúng: **(1)** truyền thông tin tối thiểu qua tham số task, **(2)** dùng wrapper/context propagation do framework cung cấp, hoặc **(3)** lưu dữ liệu theo request rồi lấy lại từ request trong các dispatch hợp lệ. Không sao chép tùy tiện cả đối tượng request hay security context vào nơi lưu lâu dài.

### Truyền giá trị tường minh

Nếu task chỉ cần mã định danh khách hàng, chụp nó thành biến trước khi submit và truyền theo tham số, ví dụ:

~~~java
String customerId = currentCustomerId; // Đã xác thực/ủy quyền tại request.
executor.execute(() -> processCustomer(customerId));
~~~

Đây là **mảnh code minh họa** trong service có biến `currentCustomerId`, `executor` và hàm `processCustomer`; không chạy độc lập. Tham số ở đây thể hiện dependency rõ ràng và không gắn kết logic nghiệp vụ với một thread cụ thể. Tại ranh giới thực thi/ủy quyền mới, vẫn phải kiểm tra quyền theo chính sách ứng dụng; việc mang ID sang task không tự cấp quyền.

## 6. Spring Security dùng `ThreadLocal` như thế nào?

Trên **Servlet stack**, `SecurityContextHolder` theo mặc định dùng chiến lược `MODE_THREADLOCAL`. Nó cung cấp `SecurityContext` của thread hiện tại, thường chứa `Authentication`. Vì vậy trong xử lý **đồng bộ** qua Spring Security filter chain, component có thể gọi:

~~~java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
~~~

Đây là **mảnh code Spring Security**, cần import `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. `Authentication` có thể bằng `null` hoặc là anonymous authentication; **không dùng riêng `isAuthenticated()` để quyết định quyền truy cập**. Ưu tiên cơ chế authorization của Spring Security (HTTP security, method security, authorization managers) cho quyết định bảo mật.

Trong một cấu hình Servlet thông thường, các filter quản lý security context (chẳng hạn `SecurityContextHolderFilter` trong các cấu hình hiện đại, hoặc `SecurityContextPersistenceFilter` ở cấu hình khác) làm nhiệm vụ thiết lập/đưa context tới chain và **xóa context khỏi thread khi chain kết thúc**. Cách nạp/lưu context vào `SecurityContextRepository` phụ thuộc cấu hình và phiên bản; lưu context cho request kế tiếp là vấn đề khác với dọn `ThreadLocal` sau request. **Dọn context khỏi thread không đồng nghĩa đăng xuất người dùng hay xóa session.**

Đừng tự gọi `SecurityContextHolder.clearContext()` giữa chừng trong controller/service nếu vẫn đang dựa vào authentication hiện tại. Khi tự gán context trong **task độc lập do chính mình quản lý**, phải có quy trình set/restore/clear an toàn, tốt nhất nhờ wrapper của Spring Security. Không bật `MODE_GLOBAL` trong server có nhiều người dùng: chế độ đó chia sẻ một context trên toàn JVM. `MODE_INHERITABLETHREADLOCAL` cũng không giải quyết an toàn việc tái dùng thread pool.

### Tích hợp khi chạy async với Spring Security

- **Spring MVC `Callable`:** Spring Security có tích hợp qua `WebAsyncManagerIntegrationFilter` để đưa `SecurityContext` vào thread chạy `Callable` do Spring MVC xử lý, với điều kiện cấu hình filter chain tích hợp đúng. Không mở rộng bảo đảm đó sang mọi task tự submit.
- **`DeferredResult` / callback tự quản lý / `CompletableFuture`:** việc hoàn tất trong một thread bên ngoài không mặc nhiên kế thừa security context từ request khởi tạo. Cần chủ động truyền dữ liệu hoặc bọc executor/task.
- **`@Async`:** có thể cấu hình `DelegatingSecurityContextAsyncTaskExecutor` cho executor thích hợp; kiểm tra thời điểm capture và cleanup trong cấu hình thực tế.
- **ExecutorService:** `DelegatingSecurityContextExecutorService` có thể bọc executor để chuyển context tới task khi được submit và phục hồi/dọn context quanh task.

Ví dụ **mảnh code tích hợp** trong service có sẵn một `ExecutorService delegate` dùng lâu dài:

~~~java
ExecutorService securedExecutor =
        new DelegatingSecurityContextExecutorService(delegate);

securedExecutor.submit(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    // Chỉ dùng auth theo phạm vi và chính sách đã xác thực.
});
~~~

Cần import `java.util.concurrent.ExecutorService`, `org.springframework.security.concurrent.DelegatingSecurityContextExecutorService`, `org.springframework.security.core.Authentication` và `org.springframework.security.core.context.SecurityContextHolder`. Wrapper không thể thay kiểm tra quyền, không giải quyết việc task chạy sau khi identity đã đổi/thu hồi quyền, và cần được quản lý vòng đời tương ứng với executor gốc (bean/shared executor, shutdown khi ứng dụng đóng). Tránh tạo mới pool cho mỗi request. Khi dùng wrapper với context truyền vào constructor khác, hãy phân biệt **context cố định** với context lấy tại thời điểm submit; không vô tình dùng danh tính của một người cho mọi task.

### Đâu là ranh giới tin cậy?

`SecurityContextHolder.getContext()` phản ánh context gắn với thread **ở thời điểm gọi**, không phải bằng chứng độc lập rằng mọi công việc phía sau luôn được ủy quyền. Mã nghiệp vụ chạy qua message queue, scheduler, event listener hay thread pool khác phải được thiết kế danh tính và quyền của **từng lần thực thi**. Không tạo một “super-user” dùng chung trong `ThreadLocal` để chữa lỗi mất context.

## 7. `OncePerRequestFilter` và async dispatch

Tên `OncePerRequestFilter` dễ gây nhầm: khái niệm “once” phụ thuộc **một lần dispatch**, cách filter được đăng ký và chính sách xử lý async/error dispatch. Khi async dispatch được thực hiện, thread khác có thể chạy qua filter chain theo dispatcher type và các điều kiện cấu hình. Các hook như `shouldNotFilterAsyncDispatch()` ảnh hưởng đến việc filter tùy chỉnh có tham gia async dispatch hay không.

Vì vậy, nếu tự bind context trong filter:
1. Xác định filter chạy với dispatcher type nào (`REQUEST`, `ASYNC`, `ERROR` khi liên quan).
2. Bind context đúng cho **mỗi thread/dispatch cần sử dụng**, rồi cleanup trong `finally` của lần đó.
3. Nếu muốn giữ dữ liệu xuyên request async, dùng cơ chế lưu theo request hoặc truyền explicit; **không giữ binding ở thread đã rời dispatch**.

Không có quy tắc mặc định rằng filter tự viết chạy duy nhất một lần cho toàn bộ vòng đời HTTP bất đồng bộ.

## 8. Lỗi thường gặp, nguyên nhân và cách xử lý

| Hiện tượng | Nguyên nhân gốc | Hướng xử lý |
| --- | --- | --- |
| Request B đôi lúc thấy người dùng/request ID của A | Thread pool tái sử dụng worker còn giá trị cũ | Bind rõ ở đầu phạm vi, `remove()` trong `finally`; kiểm thử nhiều request trên cùng executor. |
| Async task thấy `null` ở `SecurityContextHolder` | Task chạy trên thread khác, không có context tương ứng | Truyền identity tối thiểu hoặc dùng wrapper executor của Spring Security. |
| Chạy ổn trong thử nghiệm đơn giản, lỗi khi tải cao | Tùy cách pool phân công và thời điểm submit | Kiểm thử tuần tự trên pool một thread, sau đó chạy đồng thời nhiều người dùng. |
| Dùng `InheritableThreadLocal` vẫn sai danh tính | Pool thread tạo trước request, kế thừa không gắn với mỗi task | Không dựa vào inheritance của thread; chuyển context theo task. |
| Sau exception, request khác bị “dính” context | Cleanup đặt sau lệnh có thể throw, không nằm trong `finally` | Dùng `try/finally` bao quanh phạm vi gắn context. |
| Bộ nhớ tăng hoặc redeploy bị giữ tài nguyên | Giá trị ThreadLocal còn tham chiếu object sống lâu qua worker threads, có thể giữ classloader | Dọn mọi binding; tránh lưu request/response/entity graph hoặc tài nguyên lớn. |
| Xóa context trong service rồi mất authentication | Dọn context quá sớm trong request do framework quản lý | Để security filters quản lý vòng đời; chỉ clear context do mình gắn độc lập. |

`ThreadLocalMap` của mỗi thread giữ tham chiếu tới value; khóa `ThreadLocal` dùng weak reference, nhưng value có thể còn tồn tại cho tới khi entry được dọn hoặc thread kết thúc. Không nên coi GC là cơ chế cleanup đúng cho dữ liệu theo request. Với một ứng dụng nhiều người dùng, giá trị còn sót gây rủi ro **sai danh tính và lộ dữ liệu**, không chỉ là lỗi bộ nhớ.

## 9. Chọn nơi lưu dữ liệu theo vòng đời cần thiết

| Nhu cầu | Lựa chọn thường phù hợp | Vì sao |
| --- | --- | --- |
| Đọc principal trong đoạn Servlet request đồng bộ do Spring Security quản lý | `SecurityContextHolder` / API authorization của Spring Security | Framework gắn và dọn security context trong phạm vi thích hợp. |
| Dữ liệu tồn tại qua nhiều dispatch của **cùng** Servlet request | `ServletRequest.setAttribute/getAttribute` | Vòng đời dữ liệu gắn với request, không cố định theo thread. |
| Truyền correlation ID / user ID cho task bất đồng bộ | Tham số task, immutable context object hoặc công cụ context propagation đã kiểm soát | Rõ ràng ở ranh giới chuyển thread và có thể giới hạn thông tin mang theo. |
| Quyền truy cập, session hoặc dữ liệu dùng giữa nhiều request | Session/repository/database hoặc cơ chế auth chuẩn theo yêu cầu | Thời gian tồn tại dài hơn thread/request; có kiểm soát đồng bộ và bảo mật. |
| Dữ liệu tạm thời thực sự chỉ cần trong một đoạn xử lý trên một thread | `ThreadLocal` với `try/finally` và `remove()` | Phù hợp thread confinement, miễn là phạm vi được ràng buộc chặt. |

`ThreadLocal` không khiến object trở nên thread-safe: nếu hai thread cùng tham chiếu đến **một object mutable** được truyền/chia sẻ từ nơi khác, chúng vẫn có thể tranh chấp dữ liệu. Nó chỉ tách **binding của biến theo thread**.

## 10. Cách tự kiểm chứng khi xây web app

Thử nghiệm nên bao phủ các ranh giới nơi thread được tái sử dụng hoặc thay đổi:

1. Gửi hai request tuần tự cho hai danh tính khác nhau trên executor một thread; kiểm tra request sau không thấy dữ liệu request trước.
2. Cố ý ném exception ở giữa filter/service rồi kiểm tra cleanup.
3. So sánh log `Thread.currentThread().getName()` và correlation ID khi chạy controller đồng bộ, Servlet async/Spring MVC `Callable`, và task `CompletableFuture`. Tên thread chỉ giúp quan sát, **không** là hợp đồng bảo đảm identity.
4. Với Spring Security, thử cả authenticated, anonymous và background task; xác minh đúng principal/quyền tại nơi xử lý.
5. Kiểm tra filter registration, dispatcher types và chính sách async khi có redispatch hoặc error.
6. Không log token, credential hay toàn bộ `SecurityContext`; log ID an toàn, không nhạy cảm.

Một kiểm thử đặc biệt hữu ích là tuần tự hóa task trên **cùng** worker thread, như ví dụ Java ở trên. Nó làm lộ lỗi sót cleanup vốn dễ bị che khuất khi pool ngẫu nhiên chuyển request sang thread khác.

## 11. Câu hỏi ôn tập

**Q1. Vì sao request mới có thể đọc được giá trị `ThreadLocal` của request trước?** Vì thread của container/executor được tái sử dụng và binding cũ chưa bị xóa. `ThreadLocal` gắn với thread, không tự bám theo vòng đời HTTP request.

**Q2. Tại sao `remove()` nên ở `finally`?** Vì cả luồng thành công lẫn exception đều phải dọn dữ liệu đã bind trước khi thread quay lại pool.

**Q3. Tại sao `InheritableThreadLocal` không sửa được lỗi async?** Vì inheritance diễn ra khi tạo thread mới, không phải mỗi lần submit task vào thread pool đã tồn tại; tham chiếu mutable còn có thể bị chia sẻ ngoài dự tính.

**Q4. Spring Security lưu `Authentication` ở đâu trên Servlet stack mặc định?** Trong `SecurityContext` truy cập qua `SecurityContextHolder` với chiến lược thread-local. Filter chain quản lý phạm vi context; hệ thống lưu phiên/đăng nhập là cơ chế tách biệt.

**Q5. Nếu dùng `CompletableFuture` hay `DeferredResult`, phải làm gì?** Xác định thread thực sự chạy task; truyền dữ liệu cần thiết tường minh hoặc dùng executor/wrapper được cấu hình để chuyển đúng context và dọn nó sau task. Không giả định toàn bộ context Servlet sẽ tự có ở mọi thread.

**Ghi nhớ:** `ThreadLocal` có vòng đời theo **thread**; bảo mật của một request cần vòng đời theo **request và từng lần thực thi**. Hễ có thread pool hoặc chuyển thread, phải xác định rõ lúc bind, lúc truyền và lúc cleanup context.
