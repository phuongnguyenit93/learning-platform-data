# Dọn SecurityContext sau yêu cầu và ngăn rò rỉ danh tính giữa các luồng

Trong ứng dụng **Spring Security sử dụng Servlet**, mỗi HTTP request có thể mang danh tính và quyền khác nhau. Servlet container thường dùng lại các thread trong pool; nếu thông tin của người dùng A vẫn tồn tại trên thread sau khi request A kết thúc, một request của người dùng B hoặc một tác vụ nền chạy sau đó có nguy cơ đọc nhầm danh tính của A. Đây là **rò rỉ ngữ cảnh bảo mật** (security context leakage), có thể dẫn đến log sai người dùng, kiểm tra quyền sai hoặc truy cập dữ liệu không được phép.

Spring Security thiết kế quy trình **thiết lập ngữ cảnh khi xử lý request và dọn ngữ cảnh khi kết thúc** để tránh lỗi đó. Bài học giải thích chính xác đối tượng nào phải được dọn, thành phần nào chịu trách nhiệm, vì sao `ThreadLocal` có thể gây rò rỉ, cách xử lý tác vụ chạy bất đồng bộ và cách kiểm thử. Các ví dụ framework dưới đây theo **Spring Security 6.x Servlet / Spring Boot 3.x / Java 17+**; ở phiên bản khác cần đối chiếu cơ chế và API cụ thể.

## 1. Dọn SecurityContext nghĩa là gì?

Quan hệ ba thành phần cơ bản:

~~~text
SecurityContextHolder
    |
    | getContext()
    v
SecurityContext (context gắn với execution hiện tại)
    |
    | getAuthentication()
    v
Authentication
    |-- principal   : người được nhận diện
    |-- authorities : quyền/role/scope
    |-- credentials : thông tin dùng cho xác thực (nếu còn)
    |-- authenticated : trạng thái của token xác thực
~~~

- `SecurityContextHolder` là điểm truy cập đến context thông qua một `SecurityContextHolderStrategy`. Trong ứng dụng Servlet truyền thống, chiến lược mặc định là `MODE_THREADLOCAL`: context gắn với thread hiện tại.
- `SecurityContext` là đối tượng giữ `Authentication`. Nó có thể mutable; không nên chia sẻ tùy tiện giữa các request hoặc thread.
- `Authentication` là thông tin về principal, authorities và trạng thái xác thực. Context có thể trống hoặc chứa một anonymous authentication; không phải mọi request đều có người dùng đã đăng nhập.

Lệnh chính để dọn **ngữ cảnh gắn với thread đang thực thi** là:

~~~java
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContextHolder.clearContext();
~~~

Khi dùng chiến lược mặc định, thao tác này xóa tham chiếu đến context ở storage của thread hiện tại. Nó **không phải** thao tác logout hoàn chỉnh, không tự hủy session HTTP, không xóa mọi security context đã lưu trong repository và không thu hồi token truy cập đã phát hành.

**Ranh giới quan trọng:** Ứng dụng bình thường nên để các security filter của Spring Security quản lý việc dọn context của request. Code tự gọi `clearContext()` giữa request có thể làm authentication biến mất trước khi authorization hoặc bước nghiệp vụ tiếp theo chạy. Tự dọn trong `finally` chủ yếu cần khi code **tự thiết lập context ngoài vòng đời filter chuẩn** hoặc tạo ranh giới thực thi độc lập có trách nhiệm quản lý context.

## 2. Vì sao thread pool khiến lỗi lan sang request khác?

Một Servlet container có thể có ít thread worker phục vụ nhiều nghìn request theo thời gian. Minh họa:

~~~text
Thời điểm t1: worker-thread-7 xử lý GET /account của Alice
                 SecurityContextHolder -> Authentication(Alice)
                                  |
                             request xong

Thời điểm t2: worker-thread-7 được tái sử dụng cho GET /account của Bob
                 (nếu context Alice không bị dọn)
                 SecurityContextHolder -> Authentication(Alice)  [SAI]

Đúng:
   request Alice  -> set/load context Alice -> xử lý -> clear
   request Bob    -> set/load context Bob   -> xử lý -> clear
~~~

`ThreadLocal` cô lập dữ liệu **theo thread**, nhưng **không cô lập theo HTTP request**. Nếu một thread được tái sử dụng, giá trị `ThreadLocal` có thể tồn tại đến lần dùng sau, trừ khi code hoặc framework chủ động xóa/ghi đè nó. Đây là lý do cleanup phải nằm ở ranh giới xử lý request và thường ở khối `finally`: dù request thành công, ném exception hoặc bị từ chối sớm, tiến trình dọn vẫn phải chạy.

Lỗi này có thể chỉ xuất hiện gián đoạn trong môi trường thật do lịch sử sử dụng thread quyết định request nào kế tiếp dùng cùng worker. Một vài test chạy tuần tự trên thread mới có thể bỏ sót vấn đề.

### Hậu quả của rò rỉ ngữ cảnh

| Dấu hiệu | Nguyên nhân có thể | Hậu quả |
| --- | --- | --- |
| Controller đọc `getAuthentication().getName()` ra user của request trước | Context cũ còn ở thread worker | Hiển thị sai dữ liệu, audit nhầm người |
| Custom authorization dùng principal từ holder cũ | Tự set context mà không dọn | Quyết định quyền sai |
| Tác vụ trong executor thấy user của tác vụ trước | Worker thread dùng lại `ThreadLocal` | Task có thể chạy với nhầm danh tính |
| Sau logout, một custom thread vẫn giữ principal cũ | Đã hủy session nhưng giữ bản context cũ trong thread khác | Log hoặc logic nền còn coi user đã tồn tại |
| Test riêng lẻ PASS, production lỗi lẻ tẻ | Pool reuse và scheduling khác môi trường test | Khó tái hiện, nguy cơ liên quan bảo mật |

Không phải mọi trường hợp thấy danh tính không mong đợi đều do `ThreadLocal`: còn có session/cookie không được thay đổi, token còn hiệu lực, cache nghiệp vụ, custom thread context propagation hoặc chính sách xác thực. Cần xác định chính xác nguồn context và nơi nào đã gắn nó.

## 3. Thành phần Spring Security nào thiết lập và dọn context?

Trong kiến trúc Servlet, request thường đi qua:

~~~text
HTTP request
   |
   v
Servlet container filter chain
   |
   v
DelegatingFilterProxy ("springSecurityFilterChain")
   |
   v
FilterChainProxy -> chọn SecurityFilterChain khớp đầu tiên
   |
   v
SecurityContextHolderFilter (cấu hình Spring Security 6.x thường gặp)
   |-- lấy/defer context từ SecurityContextRepository
   |-- làm context sẵn có qua SecurityContextHolderStrategy
   |-- gọi chain.doFilter(...)
   |-- finally: clear SecurityContextHolder
   |
   v
Authentication filters -> AuthorizationFilter -> Controller
~~~

Sơ đồ thể hiện trách nhiệm và một thứ tự điển hình; danh sách/thứ tự filter cụ thể phụ thuộc cấu hình và phiên bản. Trong luồng xử lý thực, `SecurityContextHolderFilter` bao quanh việc gọi các filter phía sau và **xóa ngữ cảnh khỏi holder trong khối finally** khi rời luồng xử lý thuộc phạm vi của nó. Nếu controller ném exception, việc dọn vẫn được thực hiện khi stack trở về filter, miễn là luồng chạy và filter được thực thi theo vòng đời bình thường.

### SecurityContextHolderFilter khác SecurityContextPersistenceFilter

Đây là điểm thường gây hiểu nhầm khi đọc tài liệu của các phiên bản Spring Security khác nhau:

| Filter | Vai trò | Lưu context qua request |
| --- | --- | --- |
| `SecurityContextHolderFilter` | Nạp hoặc chuẩn bị nạp context từ repository, gắn vào holder và dọn khi kết thúc | Thiết kế **explicit save**: bản thân filter không tự động lưu mọi thay đổi context |
| `SecurityContextPersistenceFilter` | Cơ chế lịch sử để nạp và lưu context theo hợp đồng của nó, đồng thời quản lý holder | Trước đây thường tự lưu context sau xử lý request trong cấu hình tương ứng |

Trong Spring Security 6, nhiều cấu hình dùng `SecurityContextHolderFilter` và yêu cầu các cơ chế xác thực thích hợp **chủ động gọi `SecurityContextRepository.saveContext(...)`** nếu muốn context tồn tại cho request sau. Các authentication filter chuẩn đã có cơ chế xử lý riêng. Nếu tự làm login, cần hiểu hợp đồng này, không cho rằng gọi `SecurityContextHolder.setContext(...)` là đã ghi vào session.

**Hai thao tác riêng biệt:**

1. **Cleanup:** `SecurityContextHolder.clearContext()` ngăn context của request hiện tại ở lại trong storage của thread.
2. **Persistence:** `SecurityContextRepository.saveContext(context, request, response)` lưu context đã được xác thực để các request khác có thể nạp lại **nếu mô hình đăng nhập và repository cho phép**.

Có thể lưu context vào session cho request sau **và vẫn phải dọn holder của thread hiện tại**. Xóa holder khi kết thúc request là hành vi đúng cả ở ứng dụng có session lẫn API stateless.

### Nếu SecurityFilterChain không được chọn thì sao?

`FilterChainProxy` áp dụng filter của **SecurityFilterChain đầu tiên khớp**. Nếu request nằm ngoài mọi chain, filter quản lý context của các chain ấy không chạy cho request đó. Khi có custom servlet filter bên ngoài Spring Security và tự đặt holder, code đó phải chịu trách nhiệm riêng cho việc dọn context. Đừng đặt `securityMatcher("/api/**")` chỉ bao phủ API rồi cho rằng mọi endpoint khác vẫn được filter bảo vệ.

## 4. Mô phỏng rò rỉ và cách khắc phục bằng Java 17 thuần

Đây là chương trình **Java 17 độc lập, chạy bằng javac/java**, sử dụng `ThreadLocal` chuẩn của JDK để mô phỏng phạm vi lưu trữ của `SecurityContextHolder` mặc định. Nó cố ý tạo một trường hợp sai rồi dọn sạch để minh họa đúng nguyên nhân. Đây **không phải implementation Spring Security**, không dùng nó làm cơ chế xác thực thật.

Lưu tệp đúng tên `ThreadPoolIdentityLeakDemo.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ThreadPoolIdentityLeakDemo {
    private static final ThreadLocal<String> CURRENT_USER = new ThreadLocal<>();

    private static String who() {
        String user = CURRENT_USER.get();
        return user == null ? "<none>" : user;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<String> alice = pool.submit(() -> {
                CURRENT_USER.set("alice");
                // CỐ TÌNH QUÊN remove() để minh họa lỗi.
                return "task A: " + who();
            });
            System.out.println(alice.get());

            Future<String> next = pool.submit(() -> "task B: " + who());
            System.out.println(next.get());

            Future<String> reset = pool.submit(() -> {
                CURRENT_USER.remove();
                return "cleanup: " + who();
            });
            System.out.println(reset.get());

            Future<String> carol = pool.submit(() -> {
                CURRENT_USER.set("carol");
                try {
                    return "task C: " + who();
                } finally {
                    CURRENT_USER.remove();
                }
            });
            System.out.println(carol.get());

            Future<String> after = pool.submit(() -> "task D: " + who());
            System.out.println(after.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac ThreadPoolIdentityLeakDemo.java
java ThreadPoolIdentityLeakDemo
~~~

Stdout chính xác:

~~~text
task A: alice
task B: alice
cleanup: <none>
task C: carol
task D: <none>
~~~

**Giải thích từng bước:**

1. Pool chỉ có **một worker thread**, nên task A và task B dùng lại cùng thread.
2. Task A gán `alice` rồi quên `remove()`, vì vậy task B (không có danh tính của riêng mình) vẫn nhìn thấy `alice`. Đây là lỗi có chủ đích trong ví dụ.
3. Task reset xóa giá trị cũ. Task C thiết lập `carol` trong ranh giới `try/finally` và luôn xóa nó khi kết thúc.
4. Task D đọc ra `<none>`, chứng tỏ cleanup đúng khiến worker không giữ identity từ task C.

Chương trình dùng `Future.get()` để đợi lần lượt từng task, tạo thứ tự output xác định. Với pool nhiều thread, lỗi có thể phụ thuộc vào thread nào được tái sử dụng; tình huống một thread giúp quan sát rõ bản chất mà không cần phỏng đoán scheduling.

**Quy tắc tổng quát:** Bất kỳ vùng mã nào **tự thiết lập trạng thái gắn với thread** và sở hữu vòng đời của trạng thái ấy phải có cleanup trong `finally`, kể cả khi có exception. Tuy nhiên, ở một request đã được Spring Security quản lý, tránh dọn holder thủ công ở giữa request vì framework đã lo ranh giới của nó.

## 5. Cleanup khi request thành công, thất bại và response bị dừng sớm

Không chỉ luồng trả HTTP `200` mới cần cleanup. Một số đường kết thúc phải được xét:

- **Controller thành công:** Sau khi chuỗi filter hoàn tất, holder được dọn để thread có thể phục vụ request khác.
- **Authentication/authorization thất bại:** Filter có thể trả `401`, `403` hoặc redirect `302`; cleanup vẫn cần xảy ra khi stack trả về filter quản lý context.
- **Exception trong controller:** Khi exception lan ra filter hoặc bị MVC xử lý rồi tiếp tục kết thúc, bộ lọc quản lý holder vẫn cần hoàn tất cleanup của phạm vi đó.
- **Filter dừng chain sớm:** Nếu request đã vào filter quản lý context và filter phía sau không gọi tiếp `chain.doFilter(...)`, phần `finally` của filter quản lý vẫn phải được chạy.
- **Client ngắt kết nối / I/O lỗi:** Code được viết đúng với `try/finally` giúp cleanup khi control flow unwinds, dù response không hoàn tất bình thường.

Trong Servlet async hoặc error dispatch, việc filter nào chạy lại và thread nào tiếp tục phụ thuộc dispatcher type, cấu hình đăng ký filter và các cơ chế tích hợp của Spring Security. Không được mặc định rằng toàn bộ vòng đời bất đồng bộ chỉ chạy trên một thread hoặc kết thúc đúng lúc phương thức controller trả về.

### Tại sao không gọi clearContext trong mọi controller?

Ví dụ sai:

~~~java
// Mã minh họa sai: KHÔNG dùng làm mẫu.
public String account() {
    String user = SecurityContextHolder.getContext()
            .getAuthentication().getName();

    SecurityContextHolder.clearContext(); // xóa quá sớm

    return service.loadAccount(user); // phần sau có thể cần context
}
~~~

Nếu `service.loadAccount(...)` có method security, audit logic hoặc một đoạn code dùng holder, việc dọn sớm có thể gây thiếu authentication hoặc hành vi phân quyền bất ngờ. Phân quyền nên do Spring Security thực thi ở tầng thích hợp, và cleanup request nên được filter đảm nhiệm.

### Dọn ở ranh giới tự sở hữu

Nếu một chương trình nền độc lập **chủ động đặt ngữ cảnh** cho toàn bộ task và không có Spring Security servlet filter bao quanh nó, cần dọn trong `finally`:

~~~java
// Mã đặt trong ứng dụng Spring Security; authentication đã được
// kiểm tra bằng cơ chế tin cậy trước đó.
SecurityContext taskContext = SecurityContextHolder.createEmptyContext();
taskContext.setAuthentication(verifiedAuthentication);

try {
    SecurityContextHolder.setContext(taskContext);
    task.run();
} finally {
    SecurityContextHolder.clearContext();
}
~~~

Đoạn này là **fragment**, không phải class Java chạy độc lập: `verifiedAuthentication` và `task` do ứng dụng cung cấp, imports từ Spring Security. Mẫu `clearContext()` phù hợp khi task **sở hữu toàn bộ ranh giới context** trên thread executor độc lập. Nếu đây chỉ là một scope lồng trong thread đã có context hợp lệ, cần dùng cơ chế **save/restore context trước đó** chứ không xóa bừa context của scope bên ngoài. Trường hợp này ưu tiên các wrapper chuẩn của Spring Security.

## 6. Truyền security context sang thread khác: điều gì có thể sai?

Chiến lược `MODE_THREADLOCAL` không tự chuyển context của HTTP request sang một thread mới. Các trường hợp hay gặp:

- Gọi `@Async` để xử lý sau khi controller trả response.
- Gửi `Runnable` hoặc `Callable` vào `ExecutorService` / thread pool.
- Tự tạo thread mới bằng `new Thread(...)`.
- Đặt callback/tác vụ trong hệ thống job hoặc message consumer.

Vì vậy có **hai rủi ro đối lập**:

1. Task không nhận được authentication cần thiết nên thấy anonymous/`null`.
2. Task tự set/copy authentication nhưng không cleanup; tác vụ tiếp theo đọc nhầm user cũ.

**Không giải quyết bằng cách đặt `SecurityContextHolder.MODE_GLOBAL`** trong web application đa người dùng: strategy global chia sẻ context vượt quá ranh giới request. `MODE_INHERITABLETHREADLOCAL` cũng không phù hợp làm giải pháp chung cho executor lâu sống: thread có thể được tạo trước khi request đến và dùng lại qua nhiều request; context có thể bị thừa kế sai thời điểm hoặc trở nên cũ.

### Dùng wrapper của Spring Security

Spring Security cung cấp các abstraction để bọc công việc cần security context, ví dụ:

- `DelegatingSecurityContextRunnable`.
- `DelegatingSecurityContextCallable`.
- `DelegatingSecurityContextExecutor`.
- Các biến thể tương ứng cho executor service hoặc task executor tùy API.

Một ví dụ fragment trong ứng dụng Spring Security:

~~~java
import java.util.concurrent.Executor;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

// Chạy trong request đã được xác thực:
// Chụp context độc lập để hạn chế chia sẻ chính object mutable.
Authentication auth =
        SecurityContextHolder.getContext().getAuthentication();

SecurityContext captured = SecurityContextHolder.createEmptyContext();
captured.setAuthentication(auth);

Runnable job = () -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(current == null ? "<none>" : current.getName());
};

Runnable securedJob = new DelegatingSecurityContextRunnable(job, captured);
executor.execute(securedJob);
~~~

`executor` ở đây là biến kiểu `Executor` do ứng dụng quản lý; đây là **đoạn mã minh họa trong ứng dụng Spring**, không phải Java độc lập. Wrapper đặt context cần thiết vào thread khi chạy job và khôi phục/dọn holder theo cơ chế của Spring Security khi job kết thúc. Cách dùng wrapper giúp tránh quên cleanup kể cả khi task ném exception.

Lưu ý về an toàn:

- `captured` là **context mới**, nhưng `Authentication auth` bên trong có thể là cùng một object tham chiếu với request gốc; không được mutate hoặc lưu nó vô hạn. Nếu task chỉ cần user ID hay tenant ID đã được xác minh, truyền đúng những dữ liệu nghiệp vụ cần thiết thường đơn giản và an toàn hơn.
- Cần quyết định **thời điểm capture**. Nếu chụp context khi khởi động application thay vì khi submit task, mọi task có thể dùng sai danh tính cố định.
- Không truyền authentication của client A vào tác vụ xử lý cho client B. Việc truyền context là hành động cấp quyền truy cập dữ liệu nhạy cảm, phải có lý do nghiệp vụ rõ ràng.
- Task chạy lâu sau khi request kết thúc có thể giữ thông tin xác thực cũ; cần chính sách kiểm tra lại quyền, thời hạn token hoặc danh tính dịch vụ riêng nếu công việc yêu cầu.
- Executor cần lifecycle quản lý thích hợp; tránh tạo thread pool mới cho từng HTTP request.

Với nhiều task dùng chung executor, một mẫu là bọc executor bởi `DelegatingSecurityContextExecutor`. Khi dùng constructor lấy context tại thời điểm submit, hãy xác minh ngữ nghĩa capture của phiên bản đang dùng và không giữ cố định một user lâu dài. Đây không thay thế cơ chế xác thực/ủy quyền ở luồng công việc nền.

### Async Servlet khác task chạy tự do

Spring MVC có một số tích hợp security context cho những cơ chế async được hỗ trợ, nhưng không nên suy ra mọi callback hoặc CompletableFuture tùy biến đều tự động có context. Với Servlet `ASYNC`/`ERROR` dispatch, việc lưu context trong request attributes và cấu hình dispatcher type có thể ảnh hưởng khả năng nhìn thấy principal ở lần dispatch tiếp theo. Chẩn đoán bằng test với đúng flow được dùng và xác nhận holder đã được dọn ở các thread tham gia.

## 7. Khi nào cần save/restore thay vì chỉ clear?

Một hàm tiện ích có thể được gọi **lồng nhau trên cùng thread**:

~~~text
Context ngoài: user=alice
    |
    +--> Scope tạm thời: technicalPrincipal
             |
             +--> chạy một công việc có quyền riêng
             |
         scope kết thúc
    |
Context ngoài cần quay lại: user=alice
~~~

Trong tình huống này, `clearContext()` sau scope tạm sẽ xóa cả khả năng nhìn lại context của scope ngoài. Mẫu **save/restore** thích hợp hơn:

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

SecurityContext previous = SecurityContextHolder.getContext();

try {
    SecurityContext temporary = SecurityContextHolder.createEmptyContext();
    temporary.setAuthentication(temporaryAuthentication);
    SecurityContextHolder.setContext(temporary);
    action.run();
} finally {
    SecurityContextHolder.setContext(previous);
}
~~~

Đây là fragment có các biến `temporaryAuthentication` và `action` do code gọi cung cấp, cần hệ thống có Spring Security. Sử dụng **context mới** nhằm tránh thao tác `previous.setAuthentication(...)` lên cùng object mutable rồi tưởng đã có bản sao. Mẫu save/restore chỉ đúng khi **previous thực sự là context hợp lệ của scope ngoài**, không phải context cũ bị rò từ request khác.

Với task độc lập từ một executor, đầu vào phải có context được cấp phép rõ ràng và cuối cùng thread cần trở về trạng thái sạch. Đừng xem việc restore một context cũ, không rõ nguồn là hành động an toàn; nó có thể giữ nguyên một leak đã tồn tại.

Nếu có Spring Security wrapper tương ứng cho Runnable/Callable/Executor, ưu tiên nó vì nó giải quyết việc gắn context và cleanup/restore theo hợp đồng của framework, giảm rủi ro bỏ sót nhánh exception.

## 8. Cleanup không đồng nghĩa logout, xóa session hay thu hồi token

Bốn thao tác sau giải quyết **bốn phạm vi khác nhau**:

| Thao tác | Phạm vi | Điều không được suy diễn |
| --- | --- | --- |
| `SecurityContextHolder.clearContext()` | Storage context hiện tại của holder/strategy | Không tự xóa session, database record hoặc token đã phát hành |
| `SecurityContextRepository.saveContext(...)` | Lưu context theo repository được cấu hình | Không tự bảo đảm mọi thread khác đều cập nhật ngay |
| Logout handler như `SecurityContextLogoutHandler` | Xử lý logout theo cấu hình: xóa authentication, có thể invalidate session và các cleanup liên quan | Không tự thu hồi mọi JWT stateless đã phát hành nếu không có cơ chế revocation riêng |
| Hết hạn/thu hồi bearer token | Token/layer xác thực của các request sau | Không thay thế cleanup ThreadLocal của request hiện tại |

Ví dụ một ứng dụng dùng form login và `HttpSessionSecurityContextRepository`: sau request đầu, context được lưu trong session cho request sau; cuối **mỗi request** vẫn phải xóa holder trên thread worker. Khi logout, ứng dụng cần vô hiệu hóa session/điều chỉnh repository và cookie theo thiết kế. Chỉ clear holder mà giữ nguyên session có thể khiến request sau lại nạp đúng authentication cũ từ session.

Với API dùng Bearer token/JWT stateless, từng request thường xây lại `Authentication` từ token nhận được; kết thúc request cần clear holder, nhưng token ở client có thể vẫn dùng được cho request mới đến khi hết hạn hoặc bị thu hồi theo thiết kế. Đừng dùng `clearContext()` như một cách “logout JWT”.

### Tại sao stateless cũng cần cleanup?

“Stateless” trong thiết kế API chủ yếu nói về **không dựa vào session để ghi nhớ đăng nhập giữa các HTTP request**. Trong **một** request, Spring Security vẫn cần một context tạm thời để những filter/controller có thể truy cập principal, authorities hoặc chi tiết xác thực. Khi request xong, context này vẫn phải được dọn khỏi thread, bất kể ứng dụng có sử dụng session hay không.

## 9. Vấn đề context mutable và danh tính lưu trong biến static

Một số lỗi không xuất phát trực tiếp từ việc quên `clearContext()` mà từ **chia sẻ đối tượng**:

~~~java
// Ví dụ SAI: một biến toàn cục được dùng chung cho mọi request.
static Authentication currentAuthentication;
~~~

Nếu request A ghi `currentAuthentication=authAlice` và request B ghi `authBob`, code ở request A có thể thấy `authBob`. Đây là race condition/dữ liệu dùng chung, hoàn toàn khác với ThreadLocal nhưng cũng gây lẫn danh tính.

Ngay cả với `SecurityContextHolder`, cần cẩn trọng:

~~~java
// Không nên cập nhật context có thể bị chia sẻ ngoài ý muốn:
SecurityContextHolder.getContext().setAuthentication(newAuthentication);
~~~

Nếu thật sự cần tự đặt context sau khi đã xác minh bằng một cơ chế đáng tin cậy, nên tạo context mới:

~~~java
SecurityContext fresh = SecurityContextHolder.createEmptyContext();
fresh.setAuthentication(verifiedAuthentication);
SecurityContextHolder.setContext(fresh);
~~~

Đây là fragment trong ứng dụng Spring Security; `verifiedAuthentication` phải đến từ quy trình xác thực hợp lệ, **không được tạo token trusted chỉ từ username hoặc role mà client tự khai báo**. Khi cần giữ login qua request, còn phải tuân thủ cơ chế lưu `SecurityContextRepository` và những biện pháp session security phù hợp. Không tự sửa authentication chỉ để cho qua `@PreAuthorize` hay authorization filter.

Không lưu `SecurityContext` hoặc `Authentication` của request vào singleton field, static map, callback sống vô hạn hoặc cache toàn ứng dụng khi không có mô hình quản lý vòng đời và dữ liệu rõ ràng.

## 10. Bộ lọc tùy biến: ai được quyền dọn context?

Một custom servlet filter có thể muốn log identity, gắn correlation ID hoặc đo thời gian. Nếu nó chạy **bên trong** `SecurityFilterChain`, cần hiểu vị trí tương đối với filter quản lý context và các authentication filter.

Ví dụ bộ lọc chỉ đọc principal:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public class IdentityAuditFilter extends OncePerRequestFilter {
    private static final Logger log =
            LoggerFactory.getLogger(IdentityAuditFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();
        String name = authentication == null ? "none" : authentication.getName();

        log.debug("Security principal for {}: {}", request.getRequestURI(), name);
        chain.doFilter(request, response);
    }
}
~~~

Đây là class dùng trong ứng dụng Spring Security 6.x có Jakarta Servlet và SLF4J, không chạy trực tiếp bằng `javac` nếu thiếu classpath. Để đảm bảo filter nhìn thấy context/authentication ở thời điểm mong muốn, cần thêm nó vào đúng vị trí của chain, chẳng hạn thông qua `HttpSecurity.addFilterAfter(...)` hoặc `addFilterBefore(...)` với lớp mốc hợp lệ và hiểu thứ tự filter thực tế.

Không cần chèn `SecurityContextHolder.clearContext()` trong `finally` của mọi custom filter đọc context. Nếu Spring Security đã bao quanh request, cleanup đã thuộc trách nhiệm filter chuyên dụng; một custom filter đặt sai vị trí có thể xóa context trước khi downstream code cần nó. Nếu custom filter **tự thiết lập** context ngoài chain chuẩn, nó phải chịu trách nhiệm cleanup của chính scope đó, kể cả exception path.

**Đăng ký filter hai lần là một lỗi riêng.** Nếu class vừa có `@Component` để Spring Boot tự đăng ký ở Servlet container vừa được thêm vào `HttpSecurity`, nó có thể chạy ở hai vị trí hoặc ảnh hưởng request ngoài dự kiến. Cần quyết định rõ mức Servlet filter hay Security filter chain cho custom filter; tắt đăng ký cấp container bằng `FilterRegistrationBean` khi phù hợp.

### Về log và privacy

Chỉ log danh tính khi thật sự phục vụ audit/diagnostic và đã áp dụng chính sách dữ liệu thích hợp. Không log `Authentication.getCredentials()`, bearer token, password hash, cookie hoặc toàn bộ `Authentication.getDetails()`. Cảnh giác với principal chứa thông tin cá nhân và với việc log một identity đã bị rò: log sai danh tính có thể khiến việc điều tra sự cố càng khó.

## 11. Kiểm thử request không dùng nhầm danh tính

Giả sử có controller đơn giản:

~~~java
import java.security.Principal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class WhoAmIController {
    @GetMapping("/whoami")
    public String whoAmI(Principal principal) {
        return principal.getName();
    }
}
~~~

Và chain minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WhoAmISecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/whoami").authenticated()
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Cả hai class là các thành phần trong dự án Spring Boot 3.x có `spring-boot-starter-web` và `spring-boot-starter-security`. Phía dưới là test MockMvc yêu cầu thêm `spring-boot-starter-test`, `spring-security-test`, controller được component-scan và Spring Security filter hoạt động trong MockMvc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ContextCleanupTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void identitiesAreIsolatedAcrossRequests() throws Exception {
        mockMvc.perform(get("/whoami").with(user("alice")))
                .andExpect(status().isOk())
                .andExpect(content().string("alice"));

        assertNull(SecurityContextHolder.getContext().getAuthentication());

        mockMvc.perform(get("/whoami").with(user("bob")))
                .andExpect(status().isOk())
                .andExpect(content().string("bob"));

        assertNull(SecurityContextHolder.getContext().getAuthentication());

        mockMvc.perform(get("/whoami"))
                .andExpect(status().isUnauthorized());

        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }
}
~~~

Ở đây `user(...)` là request post-processor của `spring-security-test`, **không kiểm tra password thật**. Với HTTP Basic entry point và chain ở ví dụ, request không có authentication sẽ thường nhận 401; test cũng xác nhận holder của thread MockMvc đã được dọn sau mỗi lần request hoàn tất.

**Giới hạn của test:** `MockMvc` không tự chứng minh hệ thống production không rò danh tính trong mọi thread pool, Servlet async dispatch, message consumer và custom executor. Test trên chỉ kiểm tra ba request trong môi trường MockMvc. Muốn xác minh lỗi pool reuse, bổ sung integration test/case có worker thread dùng lại, tác vụ async hoặc test server thực; nên tạo các request từ hai identity xen kẽ và kiểm tra luôn outcome nghiệp vụ.

Không dùng `@WithMockUser` trong test này nếu mục tiêu là kiểm tra holder **trống sau từng request**, bởi test execution listener có thể cố ý thiết lập context trên thread test trước request và dọn cuối test, làm điều kiện cần kiểm tra khác đi.

## 12. Quy trình chẩn đoán một nghi vấn rò rỉ identity

Nếu một endpoint bất chợt thấy user sai, nên kiểm tra theo thứ tự:

1. **Xác định request thực tế:** endpoint, HTTP method, session cookie hoặc Authorization header có mặt không, có reverse proxy và nhiều `SecurityFilterChain` không.
2. **Kiểm tra chain được chọn:** `FilterChainProxy` có thực sự chọn chain chứa filter quản lý context hay không, và custom filter đứng ở đâu trong chain?
3. **Xem nguồn authentication:** đến từ HTTP session repository, bearer token, Basic authentication, test principal hay code tự đặt context?
4. **Tìm mọi nơi gọi** `SecurityContextHolder.setContext(...)`, `getContext().setAuthentication(...)` và `setStrategyName(...)`. Với những nơi tự đặt, xem có cleanup/restore trong `finally` không.
5. **Tìm task/executor:** mã có dùng `@Async`, `new Thread`, `CompletableFuture`, scheduled job, thread pool hoặc wrapper truyền context không?
6. **Xem thời điểm capture và thời gian sống:** security context có bị giữ trong singleton, shared mutable object hoặc task queue rất lâu sau khi request kết thúc không?
7. **Tách persistence khỏi cleanup:** session còn hiệu lực không; việc nạp lại context từ session có được mong đợi không; stateless API có tự gửi lại bearer token không?
8. **Thử hai danh tính:** chạy A rồi B trên cùng worker trong test kiểm soát được, xác nhận không có authentication cũ ở ranh giới giữa hai tác vụ.
9. **Quan sát error/async paths:** thử cả request thành công, authorization denied, exception và async callback; tìm `finally` bị bỏ qua do tự quản lý bất thường.
10. **Xác nhận sau sửa:** test tự động đo hành vi, không chỉ tin vào một dòng debug log đã in “clear”.

Ở môi trường phát triển/kiểm thử, có thể tăng logging của Spring Security:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.core.context=DEBUG
~~~

Tên logger và mức chi tiết thay đổi theo phiên bản, không bảo đảm log luôn hiển thị mọi thao tác holder. Tránh in credentials, token hoặc security context đầy đủ. Nếu cần quan sát identity phục vụ test, chỉ ghi thông tin an toàn, có lý do và phải xóa log nhạy cảm sau điều tra.

### Khi dùng tài liệu từ nhiều phiên bản Spring Security

Một số bài viết cũ cho rằng `SecurityContextPersistenceFilter` luôn tự nạp/lưu rồi clear context. Ở Spring Security 6.x, tùy configuration, `SecurityContextHolderFilter` và mô hình explicit save có thể khác. Cần kiểm tra phiên bản, danh sách filter thực tế và `SecurityContextRepository` trước khi áp dụng code sao chép từ phiên bản khác.

Điểm nhất quán: **thread đang xử lý request không được giữ lại identity của request trước** sau ranh giới cleanup, dù persistence qua session/token có thể tồn tại theo chính sách authentication.

## 13. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách làm |
| --- | --- | --- |
| “ThreadLocal tự hết hạn khi request xong” | Thread sống lâu hơn request và được dùng lại | Framework cleanup; code tự quản lý phải dùng `finally` |
| Gọi `clearContext()` giữa controller | Xóa authentication khi các bước tiếp theo còn cần | Để filter quản lý vòng đời request |
| Tự `setContext(...)` cho job rồi quên dọn | Worker pool giữ identity task trước | Bọc task bằng Spring Security delegation hoặc cleanup đúng scope |
| Bật `MODE_GLOBAL` cho web server | Dữ liệu context vượt ranh giới từng user | Dùng thread-local và cơ chế truyền context phù hợp |
| Bật `MODE_INHERITABLETHREADLOCAL` để sửa thread pool | Thread được tạo/tái dùng không theo request | Wrapper/executor có capture và cleanup rõ |
| Dùng `SecurityContextHolder.clearContext()` như logout | Session/token có thể vẫn còn | Dùng logout handler và cơ chế revoke/invalidate hợp lệ |
| Đặt `newAuthentication` vào context cũ đang chia sẻ | Mutable context có thể bị tham chiếu bởi scope khác | Tạo context mới từ nguồn xác thực tin cậy |
| Giữ `Authentication` trong biến static của singleton | Mọi request đọc/ghi chung | Dùng context theo scope và dữ liệu nghiệp vụ có vòng đời rõ |
| Coi `setContext(...)` là save vào session | Holder và repository có hợp đồng khác nhau | Xem explicit save của phiên bản/cấu hình |
| Test một request duy nhất | Không quan sát được reuse hoặc leak A→B | Test hai identity, exception và thread pool |

## 14. Bài tập tự kiểm tra

**Tình huống A.** Servlet thread `http-worker-3` vừa xử lý Alice, sau đó chuyển sang Bob. `ThreadLocal` đã từng chứa Alice. Vì sao vẫn cần dọn sau request Alice?

**Đáp án:** Servlet thread có thể được dùng lại. Nếu context Alice vẫn còn trong `ThreadLocal` và không được thay thế/dọn đúng cách, Bob hoặc một đoạn code trước khi xác thực mới có thể thấy identity của Alice. Filter quản lý ngữ cảnh của Spring Security phải dọn holder ở ranh giới request.

**Tình huống B.** Một ứng dụng dùng session login. Sau mỗi request, Spring Security gọi cleanup holder. Người dùng có phải đăng nhập lại cho request tiếp theo không?

**Đáp án:** Không nhất thiết. Nếu context được lưu đúng trong `SecurityContextRepository` (ví dụ session), request sau có thể nạp lại authentication. Cleanup holder của thread và lưu context qua request là hai trách nhiệm tách biệt.

**Tình huống C.** Một custom executor chỉ dùng một thread. Task A đặt auth Alice, không clear; task B không thiết lập auth. Task B có thể thấy ai?

**Đáp án:** Nó có thể thấy authentication của Alice, vì thread worker được dùng lại. Phải dùng cơ chế propagation/cleanup phù hợp. Ví dụ `ThreadPoolIdentityLeakDemo` minh họa chính xác hiện tượng này bằng JDK ThreadLocal.

**Tình huống D.** Trong một service đang xử lý user Alice, code đổi tạm context sang technical identity rồi gọi `clearContext()` trước khi quay lại service. Điều gì có thể sai?

**Đáp án:** Context của Alice ở scope ngoài có thể không còn sẵn có. Với scope lồng nhau, cần save/restore context trước đó, tốt nhất bằng abstraction của Spring Security, và bảo đảm technical identity đã được cấp phép hợp lệ.

**Tình huống E.** Một JWT đã được gửi cho client và vẫn còn hiệu lực. Server vừa gọi `clearContext()` khi request kết thúc. JWT có bị thu hồi không?

**Đáp án:** Không. Cleanup chỉ dọn ngữ cảnh hiện tại. Thu hồi token phải do chính sách expiry/revocation và cơ chế xác thực token thực hiện.

**Tình huống F.** App dùng `@Async` để xử lý nghiệp vụ. Trong async task, `SecurityContextHolder.getContext().getAuthentication()` là `null`. Có nên bật `MODE_GLOBAL` để sửa không?

**Đáp án:** Không. Cần wrapper/context propagation phù hợp với cách chạy task, hoặc truyền user ID đã được xác minh như dữ liệu nghiệp vụ. Strategy global có thể khiến request khác đọc nhầm identity.

## 15. Checklist áp dụng trong dự án

- Xác định **SecurityFilterChain nào** quản lý request và filter xử lý context ở phiên bản Spring Security đang dùng.
- Nhớ rằng default Servlet `SecurityContextHolder` thường dựa trên `ThreadLocal`, trong khi thread pool sống lâu hơn từng request.
- Để filter của Spring Security **dọn holder sau request**; đừng xóa authentication tùy tiện khi controller/service còn cần.
- Với code tự thiết lập context ở **ranh giới task độc lập**, luôn cleanup trong `finally`; với scope lồng nhau, save/restore đúng context trước đó.
- Phân biệt **cleanup holder**, **lưu context trong repository**, **logout** và **thu hồi session/token**.
- Sử dụng wrapper như `DelegatingSecurityContextRunnable` khi cần chuyển identity qua executor; không dùng strategy global cho server nhiều người dùng.
- Tránh mutable `SecurityContext` dùng chung, `Authentication` static và các biến giữ principal không có vòng đời.
- Test request của Alice rồi Bob, user anonymous, request bị từ chối, exception, thread pool và async path theo thực tế.
- Theo dõi thông tin vừa đủ để chẩn đoán; không log credentials/token hay dữ liệu principal không cần thiết.

**Kết luận:** Bảo mật ngữ cảnh theo request cần cả **nạp/gắn đúng `SecurityContext` khi bắt đầu**, **dọn holder khi kết thúc**, và **quản lý rõ ranh giới khi truyền thông tin sang thread khác**. Một `ThreadLocal` không được dọn có thể biến identity của người dùng trước thành danh tính của người dùng sau; cleanup đúng thời điểm và sử dụng wrapper chuẩn của Spring Security giúp tránh loại lỗi đó.