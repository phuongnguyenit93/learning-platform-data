# Giữ dữ liệu của từng yêu cầu tách khỏi trạng thái bean trong Spring

Khi nhiều HTTP request đến cùng lúc, Spring có thể cho các luồng khác nhau gọi **cùng một đối tượng controller hoặc service**. Nếu bean đó lưu tên người dùng, tham số request, mã truy vết hay dữ liệu xử lý tạm thời vào **field dùng chung**, request này có thể ghi đè dữ liệu của request khác. Hậu quả không chỉ là kết quả sai: với dữ liệu gắn với người dùng, đó còn có thể là **rò rỉ dữ liệu giữa các yêu cầu**.

Nguyên tắc chính: **dữ liệu chỉ thuộc một request nên đi theo lời gọi, đối tượng dữ liệu của request hoặc một phạm vi request được quản lý rõ ràng; không được âm thầm trở thành trạng thái dùng chung của singleton bean**. Bài này giải thích cơ chế, các lựa chọn thiết kế an toàn, cách xử lý khi có bất đồng bộ và những giới hạn của từng cách.

## 1. Vì sao trạng thái bean liên quan trực tiếp đến concurrency?

Trong Spring, các stereotype thông dụng như **@Component, @Service, @Repository, @Controller, @RestController** mặc định có **singleton scope**: trong một Spring container, một bean definition singleton thường có một instance được chia sẻ cho mọi nơi sử dụng bean đó. Singleton là phạm vi vòng đời của đối tượng, **không phải bảo đảm thread-safe**.

Hãy hình dung hai request cùng gọi một bean:

~~~text
Request A (user=An)    Request B (user=Bình)
        |                       |
        +----------+------------+
                   |
             Singleton bean
             field currentUser
                   |
        An ghi vào | Bình ghi đè
                   |
        An đọc lại -> "Bình"  (sai ngữ cảnh)
~~~

Mỗi request có dữ liệu và luồng điều khiển riêng, nhưng **field của bean singleton thuộc về cùng một object trên heap**, nên mọi invocation đều nhìn thấy *cùng vị trí trạng thái*. Spring không tạo thêm bản sao controller/service singleton cho từng request.

Phân biệt rõ:

| Thành phần | Vòng đời và chia sẻ | Có phù hợp để giữ dữ liệu từng request? |
| --- | --- | --- |
| Tham số phương thức và biến cục bộ | Mỗi lần gọi có các biến/tham chiếu riêng | **Có**, khi không trỏ đến đối tượng mutable dùng chung |
| DTO/record tạo mới cho request | Một đối tượng cụ thể được cấp/phân phối cho request | **Có**, nếu không bị tái sử dụng, publish hoặc mutate sai cách |
| Field của singleton controller/service | Một field được chia sẻ giữa các lần gọi | **Không**, đối với dữ liệu chỉ thuộc một request |
| Field của request-scoped bean | Một target bean gắn với một HTTP request đang hoạt động | **Có điều kiện**, khi cần chia sẻ ngữ cảnh trong cùng request |
| Field của session-scoped bean | Gắn với HTTP session, có thể tồn tại qua nhiều request | **Không thay thế request scope**; nhiều request cùng session có thể chạy đồng thời |
| ThreadLocal | Giá trị gắn với thread, không phải trực tiếp với request | **Chỉ cho cơ chế hạ tầng có quản lý và cleanup**, không là giải pháp mặc định |
| Field static | Chung ở cấp class/classloader | **Không**, cho dữ liệu riêng từng request |

**Không phải mọi field singleton đều nguy hiểm.** Một dependency bất biến qua constructor, configuration đã được đóng băng, service stateless hoặc cache được thiết kế thread-safe có thể được chia sẻ hợp lý. Điều cần tránh là đặt **trạng thái thay đổi riêng theo request** vào chỗ dùng chung. Ngay cả field có từ khóa **final** cũng chỉ khóa *tham chiếu*, không làm đối tượng được tham chiếu tự động bất biến hoặc thread-safe.

## 2. Anti-pattern: lưu dữ liệu request trong field của controller

Ví dụ sau là **đoạn mã Spring MVC để nhận diện lỗi**, không phải một chương trình Java độc lập:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class UnsafeGreetingController {
    private String currentName; // Dùng chung giữa mọi request!

    @GetMapping("/unsafe/greet")
    public String greet(@RequestParam String name) {
        currentName = name;                 // Request A có thể vừa ghi "An".
        return "Xin chào " + currentName;   // Request B có thể đã ghi "Bình".
    }
}
~~~

Nếu A và B chạy xen kẽ, A có thể trả “Xin chào Bình” dù tham số của A là “An”. Không thể kết luận lỗi này sẽ xuất hiện ở *mọi* lần gọi, vì lịch CPU không cố định. Đây còn là **data race**: các luồng cùng đọc/ghi field không được đồng bộ, nên khả năng quan sát giá trị phụ thuộc vào Java Memory Model và quan hệ happens-before.

Một cách sửa sai thường thấy là thêm **synchronized** quanh phương thức. Điều đó có thể loại bỏ một số race trên field, nhưng biến xử lý request độc lập thành công việc phải xếp hàng và vẫn giữ mô hình dữ liệu đặt sai phạm vi. Tương tự, đổi sang **volatile** hoặc **AtomicReference<String>** có thể thay đổi tính hiển thị/thao tác nguyên tử, nhưng **không biến một ô nhớ chung thành ô riêng của từng request**. Đúng về cơ chế đồng bộ chưa chắc đúng về ngữ nghĩa dữ liệu.

## 3. Tái hiện lỗi có kiểm soát bằng Java 17+

Ví dụ Java độc lập sau mô phỏng hai request truy cập một object dùng chung. **CountDownLatch** chủ động buộc thứ tự xen kẽ, vì vậy không phải dựa vào Thread.sleep hay sự may rủi của scheduler.

Lưu thành **RequestLeakDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class RequestLeakDemo {
    static final class SharedBean {
        private String currentUser;

        String handleAn(CountDownLatch anStored,
                        CountDownLatch binhStored) throws InterruptedException {
            currentUser = "An";
            anStored.countDown();
            binhStored.await(); // Chờ B ghi đè rồi mới đọc.
            return currentUser;
        }

        String handleBinh(CountDownLatch anStored,
                          CountDownLatch binhStored) throws InterruptedException {
            anStored.await();
            currentUser = "Bình";
            binhStored.countDown();
            return currentUser;
        }
    }

    public static void main(String[] args) throws Exception {
        SharedBean bean = new SharedBean();
        CountDownLatch anStored = new CountDownLatch(1);
        CountDownLatch binhStored = new CountDownLatch(1);

        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> an = executor.submit(
                    () -> bean.handleAn(anStored, binhStored));
            Future<String> binh = executor.submit(
                    () -> bean.handleBinh(anStored, binhStored));

            System.out.println("Request An đọc: " + an.get());
            System.out.println("Request Bình đọc: " + binh.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 RequestLeakDemo.java
java RequestLeakDemo
~~~

Kết quả:

~~~text
Request An đọc: Bình
Request Bình đọc: Bình
~~~

**Vì sao kết quả xác định?** A ghi “An”, báo hiệu cho B bằng anStored, rồi chờ. B chỉ chạy phần ghi “Bình” sau khi nhận tín hiệu; B báo binhStored và A mới đọc lại. Các thao tác countDown/await tạo các quan hệ happens-before cần thiết để A quan sát lần ghi của B. Ví dụ cố ý đặt state vào field chung để làm rõ lỗi; không khuyến khích viết chương trình thực tế theo cấu trúc đó.

**Một request không phải một thread cố định.** Trong Servlet MVC, xử lý đồng bộ thường diễn ra trên request thread; nhưng khi dùng async dispatch, @Async, CompletableFuture hoặc thư viện I/O, phần việc có thể sang thread khác. Vì thế, luôn xác định **ai sở hữu dữ liệu** thay vì dựa vào giả định thread nào đang chạy.

## 4. Giải pháp mặc định: singleton stateless, tham số và biến cục bộ

Cách đơn giản nhất là **truyền dữ liệu vào phương thức**, chỉ tạo biến cục bộ hoặc đối tượng kết quả mới. Bean có thể giữ dependency ổn định, nhưng không lưu “request hiện tại” vào field.

Lưu thành **StatelessRequestDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class StatelessRequestDemo {
    static final class GreetingService {
        String greet(String user) {
            String result = "Xin chào " + user;
            return result;
        }
    }

    public static void main(String[] args) throws Exception {
        GreetingService service = new GreetingService();
        ExecutorService executor = Executors.newFixedThreadPool(2);
        try {
            Future<String> an =
                    executor.submit(() -> service.greet("An"));
            Future<String> binh =
                    executor.submit(() -> service.greet("Bình"));

            System.out.println(an.get());
            System.out.println(binh.get());
        } finally {
            executor.shutdown();
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 StatelessRequestDemo.java
java StatelessRequestDemo
~~~

Kết quả:

~~~text
Xin chào An
Xin chào Bình
~~~

Hai task dùng **cùng một service** nhưng mỗi invocation có tham số user và biến result của chính nó. Dù executor chạy chúng theo thứ tự nào, một task không thể ghi đè biến cục bộ của task kia.

Một lưu ý quan trọng: **biến cục bộ là tham chiếu riêng, không tự làm đối tượng được trỏ tới an toàn**. Nếu hai request cùng giữ tham chiếu tới một List hoặc Map mutable được chia sẻ, chỉnh sửa collection đó vẫn có thể gây race. Kiểm tra cả object graph, không chỉ vị trí khai báo biến.

Một quy tắc thiết kế dễ áp dụng:

~~~text
HTTP request
    -> Controller đọc input và thông tin request
    -> DTO/record riêng cho lời gọi
    -> Service stateless nhận DTO qua tham số
    -> Repository / external client theo hợp đồng thread-safe
    -> Response tạo mới cho caller
~~~

Đây là kiến trúc mặc định tốt cho phần lớn Spring MVC REST endpoints.

## 5. Ví dụ Spring MVC: controller và service không mang request state

Các mã sau là **các lớp/tệp trong một ứng dụng Spring MVC có dependency Spring Web**, không chạy bằng lệnh javac trần nếu chưa thêm classpath Spring. Mỗi khối thể hiện một tệp Java riêng.

**GreetingResponse.java** — dữ liệu kết quả bất biến dạng record:

~~~java
package example.web;

public record GreetingResponse(String requestId, String message) {
}
~~~

**GreetingService.java** — service có thể là singleton vì không có field request:

~~~java
package example.web;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingResponse build(String requestId, String name) {
        String message = "Xin chào " + name.trim();
        return new GreetingResponse(requestId, message);
    }
}
~~~

**GreetingController.java** — tạo thông tin riêng từng request rồi truyền qua tham số:

~~~java
package example.web;

import java.util.UUID;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {
    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greet")
    public GreetingResponse greet(@RequestParam String name) {
        String requestId = UUID.randomUUID().toString();
        return greetingService.build(requestId, name);
    }
}
~~~

Khi hai HTTP request đi vào **/greet?name=An** và **/greet?name=Bình**, mỗi lần gọi tạo một requestId mới rồi xây dựng đối tượng response riêng. **Không có field currentName/currentRequestId** trong singleton controller hay service. Field final greetingService là dependency được chia sẻ có chủ đích, và implementation ví dụ này không giữ trạng thái request.

UUID ở đây chỉ minh họa tạo mã truy vết; trong hệ thống thật, một tracing/request ID có thể đến từ middleware đáng tin hoặc cơ chế quan sát đã chuẩn hóa. **Request ID không phải thông tin xác thực hoặc bằng chứng phân quyền**.

Tách biệt cả khi ứng dụng có nhiều tầng: controller có thể chuyển tiếp **request DTO** sang service rồi repository; không cần service giữ “người dùng đang xử lý” trong field. Khi logic cần người dùng đã xác thực, lấy từ security principal thích hợp ở ranh giới rồi truyền một đối tượng context đủ thông tin, đã được kiểm tra quyền.

## 6. Đối tượng riêng cho request: DTO và immutable snapshot

Khi một request có nhiều thông tin cần truyền cùng nhau, thay vì lặp nhiều tham số, hãy tạo một **request context thuộc về lời gọi**:

~~~java
package example.web;

public record RequestSnapshot(
        String requestId,
        String userId,
        String localeTag
) {
}
~~~

Có thể tạo record này trong controller từ dữ liệu đã xác thực/chuẩn hóa, rồi truyền nó qua các tầng service. Record giữ các field final, và các String của ví dụ là immutable. Nếu record chứa List, Map hoặc đối tượng mutable, người tạo vẫn phải copy phòng vệ khi cần; chỉ từ khóa **record** không bảo đảm toàn bộ cấu trúc con bất biến.

Với Spring service:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {
    public String describe(RequestSnapshot snapshot, String invoiceId) {
        return "user=" + snapshot.userId() + ", invoice=" + invoiceId;
    }
}
~~~

Đây là **đoạn minh họa** giả sử InvoiceService và RequestSnapshot nằm trong package/import phù hợp. Những giá trị userId, invoiceId thuộc về invocation nên không lưu trong field. Một singleton service có thể thực hiện hàng nghìn lời gọi độc lập mà không cần khóa riêng chỉ để giữ các biến này.

Nếu dữ liệu có bí mật (token, thông tin định danh nhạy cảm), chỉ giữ phần tối thiểu cần cho tác vụ; tránh log hoặc truyền snapshot dư thừa sang những hệ thống không cần dùng.

## 7. Khi nào dùng @RequestScope?

Đôi khi nhiều thành phần trong cùng request cần dùng **một đối tượng ngữ cảnh có vòng đời request**, ví dụ mã correlation, thông tin localization đã tính hoặc một bộ nhớ tạm ngắn hạn. Spring Web cung cấp **request scope**: bean target được tạo/duy trì trong phạm vi một HTTP request đang hoạt động.

**RequestTrace.java** (một bean riêng):

~~~java
package example.web;

import java.util.UUID;
import org.springframework.stereotype.Component;
import org.springframework.web.context.annotation.RequestScope;

@Component
@RequestScope
public class RequestTrace {
    private final String requestId = UUID.randomUUID().toString();

    public String id() {
        return requestId;
    }
}
~~~

**TraceController.java** (singleton controller phụ thuộc request-scoped bean):

~~~java
package example.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TraceController {
    private final RequestTrace trace;

    public TraceController(RequestTrace trace) {
        this.trace = trace;
    }

    @GetMapping("/trace")
    public String trace() {
        return trace.id();
    }
}
~~~

Trong Spring, **@RequestScope** mặc định dùng **class-based scoped proxy**. Controller singleton giữ **proxy**, và khi phương thức được gọi trong HTTP request hợp lệ, proxy giải quyết **request-scoped target** của request hiện tại. Hai request khác nhau có target RequestTrace khác nhau; nhiều lần truy cập trong *cùng* request sử dụng cùng target.

Điểm cần hiểu chính xác:

- **@RequestScope không có nghĩa một object riêng cho mỗi thread.** Nếu cùng request điều phối nhiều công việc đồng thời và các công việc ấy thực sự truy cập cùng target, field mutable bên trong target vẫn cần xét concurrency.
- Scoped bean cần **request context đang hoạt động**; gọi proxy ở ngoài request, hoặc trong executor thread không có context tương ứng, có thể dẫn tới lỗi scope không active.
- Đừng mang request-scoped proxy hoặc target vào một background task chạy sau khi request kết thúc rồi mong nó còn hoạt động. Hãy trích xuất dữ liệu cần thiết thành immutable snapshot trước khi chuyển ranh giới bất đồng bộ.
- Request scope không cần thiết khi vài biến cục bộ và một DTO đã giải quyết được yêu cầu. Thêm scope tạo phụ thuộc ngầm vào vòng đời HTTP, tăng khó khăn cho test và async.

**Request scope khác prototype scope.** Một prototype bean được tạo khi Spring giải quyết yêu cầu lấy bean mới; nếu prototype được inject trực tiếp vào constructor của một singleton, tham chiếu được inject **không tự đổi mỗi HTTP request**. Cũng không dùng **@SessionScope** để giả lập request scope: nhiều request song song của cùng session vẫn có thể dùng chung đối tượng session.

## 8. ThreadLocal không đồng nghĩa với request scope

ThreadLocal lưu một giá trị **theo thread**, ví dụ một request ID được middleware gắn vào thread khi xử lý request. Nó không tạo quyền sở hữu theo HTTP request.

Ở server dùng thread pool:

1. Worker thread T1 phục vụ request A.
2. Nếu A đặt ThreadLocal rồi quên xóa, T1 có thể được tái sử dụng để phục vụ request B.
3. B đọc nhầm giá trị còn lại của A: rò rỉ ngữ cảnh giữa các request.

Nếu một cơ chế tầng hạ tầng thật sự dùng ThreadLocal, tối thiểu phải **dọn trong finally** trên mọi nhánh lỗi và thành công:

~~~java
public final class TraceHolder {
    private static final ThreadLocal<String> CURRENT =
            new ThreadLocal<>();

    private TraceHolder() {
    }

    public static void runWithTrace(String id, Runnable action) {
        CURRENT.set(id);
        try {
            action.run();
        } finally {
            CURRENT.remove();
        }
    }

    public static String currentId() {
        return CURRENT.get();
    }
}
~~~

Đây là **lớp Java độc lập có thể biên dịch** nhưng chỉ minh họa cleanup cho một ngữ cảnh không lồng nhau. Nếu cho phép lồng context, cần lưu và phục hồi giá trị trước đó một cách có chủ đích. Tránh tự xây kho request-state toàn cục bằng ThreadLocal khi tham số/DTO đủ dùng.

Spring MVC có **RequestContextHolder** và một số cơ chế sử dụng thread-bound request attributes trong quá trình xử lý web. Đây là một phần hạ tầng có vòng đời bind/unbind, **không có nghĩa tùy ý tạo @Async task là request attributes sẽ tự đi theo task**. Với executor tái sử dụng thread, dựa vào **InheritableThreadLocal** cho dữ liệu request đặc biệt nguy hiểm vì thời điểm tạo thread và thời điểm gán request không trùng nhau, đồng thời dễ mang theo context cũ.

Trong reactive WebFlux, quá trình xử lý có thể đổi thread qua nhiều operator; ThreadLocal càng không phải phương tiện đáng tin để định danh một logical request. Với Reactor, **Context** là nơi phù hợp cho dữ liệu gắn với reactive subscriber khi không tiện truyền trực tiếp qua biến/hàm.

## 9. Qua ranh giới @Async / CompletableFuture: truyền snapshot, không mượn field

Giả sử HTTP controller đã xác thực người dùng và chuẩn hóa thông tin request. Sau đó cần chạy việc lâu trên executor:

~~~text
HTTP request trên thread xử lý
    |
    | lấy requestId, userId; kiểm tra quyền
    v
RequestSnapshot (giá trị riêng)
    |
    | truyền qua tham số
    v
@Async / CompletableFuture / worker
    |
    | chỉ dùng snapshot được truyền vào
    v
Kết quả/response hoặc xử lý nền có vòng đời rõ ràng
~~~

Ví dụ trong Spring (cần **@EnableAsync**, bean executor tên **appExecutor**, và gọi phương thức thông qua Spring proxy):

**RequestSnapshot.java**:

~~~java
package example.async;

public record RequestSnapshot(String requestId, String userId) {
}
~~~

**ReportWorker.java**:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("appExecutor")
    public CompletableFuture<String> build(RequestSnapshot snapshot) {
        String result = "request=" + snapshot.requestId()
                + ", user=" + snapshot.userId();
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Điểm chính: **snapshot là tham số đã được tạo trước khi rời request thread**. Spring proxy đưa phương thức @Async tới executor; mã bên trong chỉ đọc snapshot. Việc trả completedFuture trong phương thức này hợp lý vì phương thức đã được interceptor @Async chuyển sang luồng thực thi phù hợp, không cần bọc thêm supplyAsync chỉ để chuyển luồng một lần nữa.

Nếu dùng Java thuần, cũng truyền snapshot như vậy:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> generateFor(snapshot), executor);
~~~

Đây là **đoạn minh họa** với snapshot, generateFor và executor được khai báo sẵn. Lambda capture một *tham chiếu*; nếu snapshot hoặc object bên trong bị thread khác mutate thì vẫn có race. Dùng immutable DTO hoặc defensive copy khi crossing boundary.

**Những cảnh báo cần nhớ:**

- @Async **không tự mang theo mọi ThreadLocal**, ví dụ MDC log hoặc SecurityContext trong mọi cấu hình. Nếu thực sự cần propagation, dùng cơ chế được framework hỗ trợ, chẳng hạn TaskDecorator và wrapper tương ứng cho Spring Security; không tự sao chép bừa bãi các trạng thái bảo mật.
- @Async trong cấu hình proxy thông thường **không có tác dụng khi self-invocation** (một phương thức cùng bean gọi trực tiếp phương thức @Async của chính nó). Điều này liên quan cách Spring chuyển luồng, không phải giải pháp để cô lập state.
- Nếu tác vụ chạy **sau khi HTTP request kết thúc**, không đọc tùy tiện HttpServletRequest, request-scoped proxy hoặc RequestContextHolder ở worker. Tạo snapshot đủ dùng trước, xác định deadline và trách nhiệm dọn tài nguyên.
- Khi dùng callback **thenApply/whenComplete**, callback có thể chạy trên thread hoàn tất tương lai hoặc luồng đăng ký. Không giả định callback vẫn nằm trên “request thread”.
- Không đưa cả request body lớn, session, principal mutable hoặc đối tượng servlet request vào queue chỉ để giữ context; giữ dữ liệu nhỏ, an toàn, đúng nhu cầu.

## 10. Với WebFlux: cô lập theo subscription, không theo thread

Trong Spring WebFlux, request được biểu diễn bằng reactive pipeline. Nhiều subscription có thể dùng chung thread và một subscription có thể chuyển thread. Cách truyền dữ liệu qua tham số và tạo DTO riêng vẫn tốt; với metadata xuyên nhiều operator, **Reactor Context** giúp giữ thông tin theo chuỗi subscriber:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> response = Mono.deferContextual(view ->
        Mono.just("requestId=" + view.<String>get("requestId")))
    .contextWrite(Context.of("requestId", "req-42"));
~~~

Đây là **đoạn code minh họa trong phạm vi phương thức có Reactor dependency**. Khi subscribe, dữ liệu req-42 được truy cập từ context tương ứng; nó không đến từ một static/field currentRequest. Reactor Context không tự động biến mọi request thành có ID trên: application/filter cần cung cấp giá trị theo đúng pipeline.

Nếu bài toán chỉ cần truyền một DTO cho một hàm, hãy truyền DTO trực tiếp; không cần đẩy mọi tham số nghiệp vụ vào Reactor Context. Reactor Context phù hợp hơn với ngữ cảnh xuyên nhiều operator như tracing và các thông tin kỹ thuật cần thiết. Lưu ý trách nhiệm dọn/giới hạn dữ liệu khi pipeline hoàn tất và việc không đưa thông tin bí mật vào log.

## 11. Chọn cách giữ trạng thái đúng phạm vi

| Nhu cầu | Lựa chọn nên ưu tiên | Điều cần tránh |
| --- | --- | --- |
| Tên, filter, pagination của một HTTP request | Tham số phương thức, request DTO | Field mutable currentFilter trong singleton |
| Giá trị trung gian tính toán trong service | Biến cục bộ, object mới | Cache chung không có key và vòng đời rõ ràng |
| Response được tạo riêng cho caller | Immutable DTO/record | Tái sử dụng cùng response builder mutable |
| Mã request cần dùng ở vài tầng MVC | Truyền context rõ ràng; @RequestScope khi thực sự có ích | Biến static hoặc ThreadLocal thủ công kéo dài |
| Công việc @Async / executor | Snapshot bất biến truyền như tham số | Đọc request attributes từ worker sau request |
| Trace/logging xuyên task | Context propagation do hạ tầng quản lý | Tin rằng MDC tự chuyển thread |
| Dòng xử lý reactive | DTO qua operator; Reactor Context cho cross-cutting context | Gắn thông tin request vào ThreadLocal đơn thuần |
| Bộ đếm/caches dùng chung thật sự | Primitive thread-safe, ConcurrentHashMap, cơ chế đồng bộ đúng | Dùng field chung kiểu “current user” |
| State duy trì trong session | Cơ chế session có kiểm soát và đồng bộ khi cần | Xem session bean là chỉ một request tại một thời điểm |

**State dùng chung hợp lệ khác với request state.** Một metrics counter toàn hệ thống có thể là AtomicLong; một cache dùng chung có thể dùng concurrent collection; một client bất biến/thread-safe có thể inject vào singleton. Nhưng **AtomicReference<UserContext> currentUser** vẫn là một khe duy nhất cho mọi caller, nên giữ đúng tính nguyên tử không chữa sai lầm về quyền sở hữu request.

**Request scope cũng không thay thế authorization.** Mỗi request có context riêng không bảo đảm dữ liệu trong đó được xác thực, hoặc caller có quyền truy cập tài nguyên. Phải kiểm tra quyền và kiểm soát việc lộ dữ liệu riêng.

## 12. Kiểm thử tách biệt request

Đừng chỉ chạy tuần tự hai request rồi kết luận an toàn: bug chỉ bộc lộ khi có xen kẽ. Một chiến lược kiểm thử:

1. **Unit test đồng thời có kiểm soát** bằng CountDownLatch/CyclicBarrier để hai lời gọi thật sự chen vào đoạn ghi/đọc trạng thái, thay vì Thread.sleep và mong scheduler tạo race.
2. **Kiểm tra hai request có dữ liệu phân biệt**, chẳng hạn userId=An, userId=Bình, requestId khác nhau. Assert mỗi kết quả chỉ chứa dữ liệu của request tương ứng.
3. **Kiểm tra lỗi và hủy**: nếu xử lý thất bại, request context/ThreadLocal do ứng dụng quản lý có được giải phóng không? Pool có tái sử dụng worker mang context cũ không?
4. **Kiểm tra async boundary**: task hoạt động sau khi request thread kết thúc có thể xử lý từ snapshot, không truy vấn scope đã đóng.
5. **Kiểm tra shared dependencies**: service có thể stateless nhưng cache, mapper, builder hoặc collection được inject có mutable state. Đảm bảo loại object đó thật sự thread-safe hoặc được tạo riêng theo invocation.

Với test ứng dụng Spring, có thể kết hợp unit test với MockMvc/WebTestClient hoặc HTTP integration test phù hợp stack. Nếu muốn tái hiện race, nên kiểm soát điểm xen kẽ bằng latch trong fixture/test seam; một phép test đồng thời có lịch chạy không kiểm soát có thể pass rất nhiều lần rồi bất chợt thất bại.

## 13. Những hiểu nhầm thường gặp

**“Spring singleton có một instance nên chỉ một thread dùng nó tại một thời điểm.”** Sai. Nhiều request threads có thể gọi một singleton cùng lúc.

**“Mỗi lần vào method, field sẽ là bản riêng.”** Sai. Biến cục bộ thuộc invocation; field thuộc object. Nếu object là singleton, field được chia sẻ.

**“Thêm volatile/synchronized/AtomicReference vào currentRequest sẽ cô lập các request.”** Sai về mô hình dữ liệu. Đồng bộ có thể quản lý truy cập, nhưng không tạo ngữ cảnh riêng theo request.

**“Chỉ cần prototype là mỗi request có instance mới.”** Không nhất thiết. Prototype được phân phối khi lấy bean; inject một lần vào singleton không tự làm mới ở mọi request. Request scope có ngữ nghĩa riêng.

**“@RequestScope có một bean cho mỗi thread.”** Sai. Scope dựa trên HTTP request đang hoạt động, không dựa trên danh tính thread.

**“ThreadLocal tồn tại đúng bằng một HTTP request.”** Sai. Thread thường được tái sử dụng; task async có thể chạy ở thread khác. Phải có cơ chế bind/cleanup và propagation được quản lý.

**“record luôn deep immutable.”** Sai. Record ngăn thay đổi tham chiếu thành phần sau khi tạo, nhưng thành phần trỏ đến mutable collection/object vẫn có thể bị sửa.

**“Không có field mutable trong service thì ứng dụng chắc chắn thread-safe.”** Chưa đủ. Dependencies, static state, mutable input được chia sẻ, I/O clients và transaction/session boundaries đều cần xem xét.

**“Dùng @Async rồi mới đọc request-scoped bean cũng giống request thread.”** Không được bảo đảm. Cần truyền snapshot hoặc sử dụng propagation được hỗ trợ với vòng đời hợp lệ; không đánh đồng request scope với executor task scope.

## 14. Quy trình rà soát trước khi đưa lên production

Khi xem một controller/service xử lý concurrent request, hãy tự hỏi:

1. **Dữ liệu này thuộc ai?** Một HTTP request, một user session, một workflow hay toàn ứng dụng?
2. **Nó đang nằm ở đâu?** Tham số/local, DTO mới, field bean, static, ThreadLocal, request scope hay shared cache?
3. **Ai có thể đọc/ghi đồng thời?** Nhiều HTTP request, cùng session mở nhiều tab, worker @Async, CompletableFuture callbacks?
4. **Có cần chia sẻ không?** Nếu không, truyền qua tham số hoặc tạo object mới; nếu có, xác định scope và cơ chế đồng bộ đúng.
5. **Ranh giới async nằm ở đâu?** Snapshot nào cần đi theo task; thông tin nào có thể biến mất khi request kết thúc?
6. **Cleanup và bảo mật ra sao?** Giá trị ThreadLocal, dữ liệu nhạy cảm, lifecycle của worker và request-scoped object có được xử lý phù hợp?
7. **Có test xen kẽ thật sự chưa?** Dùng công cụ điều phối thread trong test để kiểm tra dữ liệu của từng request không nhiễm nhau.

Ví dụ sửa anti-pattern ngắn:

~~~text
SAI:
SingletonService.currentUser = request.user
SingletonService.process() đọc currentUser

ĐÚNG:
RequestSnapshot snapshot = lấy dữ liệu đúng của request
SingletonService.process(snapshot) chỉ đọc dữ liệu được truyền
~~~

Nếu một dependency chung cần giữ dữ liệu nghiệp vụ dài hạn, hãy dùng kho lưu trữ có định danh cụ thể và cơ chế concurrency thích hợp (ví dụ DB transaction, optimistic locking, cache theo key); đừng dùng field currentUser làm nơi lưu tạm.

## 15. Tự kiểm tra

**Câu 1.** Một bean @Service không khai báo scope, hai request gọi đồng thời. Mỗi request có service riêng không?

**Đáp án:** Không. Theo mặc định, bean là singleton trong Spring container. Hai invocation có tham số/local riêng nhưng cùng thấy các instance field.

**Câu 2.** Thay currentUser bằng AtomicReference<String> có bảo đảm A không đọc nhầm user của B?

**Đáp án:** Không. AtomicReference quản lý thao tác trên *một tham chiếu chia sẻ*, nhưng A và B vẫn dùng chung ô currentUser.

**Câu 3.** Nếu một method chỉ có String userId làm tham số, tạo String result từ userId và trả về, tại sao thường an toàn khi gọi đồng thời?

**Đáp án:** Các binding tham số/local tách theo invocation; miễn không truy cập hay mutate object chung không an toàn ở sâu bên dưới.

**Câu 4.** Request-scoped bean được inject vào singleton hoạt động ra sao?

**Đáp án:** Với @RequestScope mặc định, singleton thường giữ scoped proxy; proxy giải quyết target thuộc request đang active khi được gọi. Không được giả định proxy hoạt động ở bất kỳ executor thread nào sau đó.

**Câu 5.** Một @Async task cần requestId sau khi HTTP response đã hoàn tất; nên lấy dữ liệu bằng RequestContextHolder ở worker không?

**Đáp án:** Không nên phụ thuộc vào request context của thread HTTP. Tạo immutable snapshot trước ranh giới và truyền cho task; tracing/security propagation cần cơ chế chuyên dụng.

**Câu 6.** Có phải mọi field trong singleton đều bị cấm?

**Đáp án:** Không. Dependencies stateless/thread-safe, cấu hình bất biến, metrics và cache được đồng bộ đúng vẫn phù hợp. Cái sai là lưu state vốn thuộc một request vào ô nhớ chia sẻ không có định danh sở hữu.

## Kết luận

**Scope của Spring quyết định vòng đời object; lời gọi concurrent quyết định ai có thể truy cập nó; mô hình dữ liệu quyết định trạng thái thuộc về ai.** Với request-specific data, lựa chọn mặc định nên là **singleton stateless + tham số + DTO/record riêng**. Chỉ dùng **@RequestScope** khi thực sự cần đối tượng tồn tại xuyên các thành phần trong cùng request, và hiểu cơ chế proxy/lifecycle. Không sử dụng field singleton, ThreadLocal hay prototype như giải pháp ngầm để giữ “request hiện tại”. Khi chuyển sang **@Async, CompletableFuture hoặc Reactor**, tiếp tục giữ quyền sở hữu dữ liệu rõ ràng bằng snapshot hoặc context propagation được thiết kế đúng cho môi trường thực thi.

**Tra cứu thêm khi triển khai:** tài liệu Spring Framework về Bean Scopes, Request Scope, Task Execution and Scheduling/@Async, Spring MVC/WebFlux; JDK về Java Memory Model, CountDownLatch và ThreadLocal; Project Reactor về Context.
