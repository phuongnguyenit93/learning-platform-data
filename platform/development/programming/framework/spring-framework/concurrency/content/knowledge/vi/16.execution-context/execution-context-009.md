# Phân biệt ngữ cảnh bảo mật cần bộ hỗ trợ riêng với ThreadLocal tùy ý

Trong **Spring Framework - concurrency**, một ứng dụng có thể tiếp nhận hai HTTP request của hai người dùng khác nhau, sau đó gửi công việc sang cùng một **ThreadPoolTaskExecutor**. Nếu xử lý ngữ cảnh thực thi không đúng, worker có thể không biết người dùng hiện tại là ai, hoặc tệ hơn, nhìn thấy thông tin của request trước trên một thread được tái sử dụng.

Có hai loại dữ liệu thường bị đánh đồng:

1. **ThreadLocal tùy ý** của ứng dụng: chẳng hạn mã tương quan log, ngôn ngữ, requestId hoặc một giá trị tạm dùng để tiện truy cập trong cùng thread.
2. **Ngữ cảnh bảo mật** do **Spring Security** quản lý: **SecurityContextHolder**, **SecurityContext**, **Authentication**, principal và authorities. Chúng không chỉ là chuỗi để gắn log mà còn liên quan trực tiếp tới **xác thực, phân quyền và tính cô lập người dùng**.

Mặc dù SecurityContextHolder trong ứng dụng servlet thông thường mặc định dùng cơ chế gần với **ThreadLocal**, **không nên truyền ngữ cảnh bảo mật qua thread pool bằng cách tự sao chép một ThreadLocal tùy tiện**. Spring Security cung cấp những bộ hỗ trợ chuyên biệt, như **DelegatingSecurityContextRunnable**, **DelegatingSecurityContextCallable**, **DelegatingSecurityContextExecutor**, **DelegatingSecurityContextExecutorService** và **DelegatingSecurityContextAsyncTaskExecutor**, để thiết lập/ngừng sử dụng ngữ cảnh đúng ranh giới tác vụ.

**Kết luận cần nhớ ngay:** ThreadLocal là **cơ chế lưu giá trị theo thread**; SecurityContext là **một phần hợp đồng bảo mật**; việc truyền SecurityContext cần chính sách identity, quyền, vòng đời và cleanup. Không phải cứ copy một tham chiếu ThreadLocal là đã có context propagation an toàn.

Bài học thuộc nhóm **Ngữ cảnh thực thi** và hướng tới Java 17+, ExecutorService, Spring **@Async** và Spring Security trong ứng dụng server có nhiều request đồng thời.

## 1. Vì sao việc chuyển sang worker làm mất context?

Một HTTP servlet request thường được xử lý trên một thread được framework/container quản lý:

~~~text
HTTP request A -- Security filters --> request-thread-7
                                    |
                                    +-- SecurityContextHolder
                                    |      Authentication: alice
                                    |
                                    +-- submit(task) ---> worker-2
                                                          |
                                                          +-- ThreadLocal riêng
                                                              thường không có Alice
~~~

Trong cấu hình mặc định **MODE_THREADLOCAL**, SecurityContextHolder gắn thông tin với **thread đang chạy**, không gắn với một đối tượng HTTP request có khả năng tự đi qua mọi executor.

Khi task được gửi bằng **ExecutorService.submit**, **CompletableFuture.supplyAsync**, **ThreadPoolTaskExecutor.execute** hay lời gọi **@Async**, worker có thể là một thread khác. Trên worker:

- **SecurityContextHolder.getContext().getAuthentication()** có thể là null.
- Một ThreadLocal ứng dụng tự tạo cũng thường không có giá trị của request thread.
- Một worker bị sử dụng không đúng có thể giữ **giá trị cũ từ lần thực thi trước**.
- Transaction, MDC, RequestContextHolder và tracing không nhất thiết có cùng hành vi truyền/cleanup như SecurityContext.

**Khác biệt giữa “không có context” và “sai context” cực kỳ quan trọng.** Không có Authentication có thể khiến tác vụ bị từ chối truy cập như mong đợi; sai Authentication có thể khiến tác vụ bị thực thi dưới danh tính hoặc quyền của người khác, nghiêm trọng hơn nhiều.

### Quy tắc Spring Security

Theo tài liệu Spring Security, đối với servlet security thông thường, **SecurityContextHolder** lưu thông tin xác thực của thread hiện hành và cơ chế filter quản lý việc dọn nó sau request. Cấu trúc cơ bản là:

~~~text
SecurityContextHolder (holder + strategy)
    |
    +-- SecurityContext (trạng thái bảo mật hiện tại)
             |
             +-- Authentication
                     |
                     +-- principal
                     +-- credentials (tùy cơ chế)
                     +-- authorities / roles / scopes
~~~

Một **Authentication** không chỉ là tên đăng nhập. Nó có thể chứa authorities, thông tin về phương thức xác thực, principal object và những chi tiết liên quan quyền. Vì vậy, một custom ThreadLocal<String> lưu mỗi username **không tương đương** với việc cung cấp SecurityContext hợp lệ.

## 2. ThreadLocal bình thường hoạt động ra sao?

**ThreadLocal<T>** cho phép mỗi **Thread** giữ một giá trị T riêng:

~~~java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();
~~~

Đây là **khai báo trường trong class Java**, không phải chương trình độc lập.

Nếu main/request thread set REQUEST_ID="A", worker từ pool **không tự đọc ra "A"** chỉ vì Runnable/lambda do main gửi có thể tham chiếu trường static REQUEST_ID. Trường ThreadLocal là một điểm truy cập; **giá trị được tra theo Thread.currentThread()**, không theo caller đã submit.

~~~text
ThreadLocal REQUEST_ID
    |
    +-- request-thread: "A"
    +-- worker-1:      null
    +-- worker-2:      "stale-B"  (nếu lần trước không remove!)
~~~

Lưu ý rằng ThreadLocal **không tự đồng bộ dữ liệu chung**. Nó phân tách slot theo thread, nhưng giá trị T vẫn có thể là **một object mutable được chia sẻ** bởi các thread nếu bạn đưa cùng tham chiếu vào nhiều slot.

### Thread pool khiến lỗi nặng hơn

ThreadPoolTaskExecutor và ExecutorService thường **tái sử dụng worker**. Nếu một task gọi **ThreadLocal.set(value)** rồi quên **remove()** trong finally:

- Worker có thể được dùng cho task sau.
- Task sau nhìn thấy **stale value** dù nó xuất phát từ request khác.
- Dữ liệu nhạy cảm có thể còn bám vào thread sống lâu.
- Khi worker không có việc và chạy lâu, stale references có thể giữ các object lớn trong bộ nhớ.

Không chỉ có memory leak; với dữ liệu định danh/ủy quyền, đây còn là **cross-request context leak**.

## 3. Java 17 chạy độc lập: không tự truyền context và có thể rò rỉ

Chương trình dưới đây hoàn toàn **thuần Java 17**, không cần Spring. Nó chứng minh ba sự kiện trong cùng một worker thread:

1. ThreadLocal của caller **không tự đến worker**.
2. Một Executor wrapper có thể **chụp giá trị tại submit, set trong worker và remove trong finally** khi dùng đúng.
3. Nếu một task tự set ThreadLocal rồi **không dọn**, worker có thể để lại giá trị sai cho task sau.

Lưu thành **ThreadLocalBoundaryDemo.java**:

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ThreadLocalBoundaryDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static String current() {
        String value = CONTEXT.get();
        return value == null ? "<empty>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();

        // Wrapper ví dụ cho một ThreadLocal phi bảo mật đơn giản.
        Executor contextAware = command -> {
            String captured = CONTEXT.get();  // Đọc tại submit.
            worker.execute(() -> {
                try {
                    if (captured == null) {
                        CONTEXT.remove();
                    } else {
                        CONTEXT.set(captured);
                    }
                    command.run();
                } finally {
                    CONTEXT.remove();
                }
            });
        };

        try {
            CONTEXT.set("alice");

            String rawAlice = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            String wrappedAlice = CompletableFuture.supplyAsync(
                    ThreadLocalBoundaryDemo::current, contextAware)
                    .get(5, TimeUnit.SECONDS);

            CONTEXT.set("bob");

            String wrappedBob = CompletableFuture.supplyAsync(
                    ThreadLocalBoundaryDemo::current, contextAware)
                    .get(5, TimeUnit.SECONDS);

            String rawAfter = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            // Minh họa một task sai quên cleanup trên worker.
            worker.submit(() -> CONTEXT.set("stale-alice"))
                    .get(5, TimeUnit.SECONDS);

            String leaked = worker.submit(
                    ThreadLocalBoundaryDemo::current)
                    .get(5, TimeUnit.SECONDS);

            // Dọn sự cố cố ý tạo ra trong ví dụ.
            worker.submit(CONTEXT::remove)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Raw worker thấy: " + rawAlice);
            System.out.println("Wrapped Alice: " + wrappedAlice);
            System.out.println("Wrapped Bob: " + wrappedBob);
            System.out.println("Raw sau wrapper: " + rawAfter);
            System.out.println("Giá trị bị rò: " + leaked);
        } finally {
            CONTEXT.remove();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ThreadLocalBoundaryDemo.java
java ThreadLocalBoundaryDemo
~~~

**Stdout của ví dụ:**

~~~text
Raw worker thấy: <empty>
Wrapped Alice: alice
Wrapped Bob: bob
Raw sau wrapper: <empty>
Giá trị bị rò: stale-alice
~~~

Giải thích:

- Worker đầu tiên được tạo bởi **newSingleThreadExecutor** và không có giá trị CONTEXT của main, nên rawAlice = empty.
- **contextAware** chụp alice/bob ngay lúc **execute** được gọi, sau đó đặt đúng giá trị trên worker.
- **finally CONTEXT.remove()** bảo đảm worker không giữ lại thông tin Alice/Bob sau mỗi task thông qua wrapper.
- Một task **không đi qua wrapper** cố ý set stale-alice và quên remove; task raw kế tiếp sử dụng cùng worker nên đọc được stale-alice.
- Dòng dọn cuối được gửi như một task vào cùng worker để loại giá trị cũ; pool được shutdown ở finally.
- **get(timeout)** đợi từng bước hoàn tất, không dựa vào Thread.sleep hay đoán lịch scheduler.

**Quan trọng:** wrapper này chỉ nhằm giảng giải ThreadLocal **phi bảo mật**, không phải bộ truyền SecurityContext nên copy vào production. Trong thư viện/phân hệ có callback lồng nhau chạy đồng bộ cùng thread, còn cần cân nhắc **lưu và phục hồi giá trị context trước đó** thay vì chỉ remove. Với thông tin bảo mật, dùng cơ chế Spring Security chuyên dụng.

## 4. Tại sao SecurityContextHolder không thể thay bằng ThreadLocal<String> userId?

Một custom value như REQUEST_USER.set("alice") có thể hữu ích cho việc tạo **label log** nếu dữ liệu không nhạy cảm và có cleanup. Nhưng nó **không tự trở thành Authentication được Spring Security tin cậy**.

Phân biệt:

| Thành phần | Mục đích | Ai quản lý hợp đồng? |
| --- | --- | --- |
| **ThreadLocal<String> requestId** | Metadata tương quan log | Ứng dụng, logging framework hoặc context propagation |
| **MDC** | Log diagnostic context | Logging framework; thường cần TaskDecorator/context propagation |
| **SecurityContextHolder** | Truy cập SecurityContext của thread hiện hành | Spring Security và SecurityContextHolderStrategy |
| **SecurityContext** | Chứa Authentication | Spring Security; gắn với lifecycle xác thực/ủy quyền |
| **Authentication** | Principal, trạng thái authenticated, authorities và chi tiết khác | Spring Security và authentication providers |
| **AuthorizationManager / method security** | Ra quyết định truy cập tài nguyên/thao tác | Spring Security theo policy ứng dụng |
| **RequestContextHolder** | Request attributes | Spring Web, không phải kho bảo mật |
| **Reactor Context** | Context đi theo reactive subscriber chain | Reactor; dùng **ReactiveSecurityContextHolder** cho reactive security |

Sai lầm nguy hiểm là tạo một **ThreadLocal<String> CURRENT_USER** rồi truyền nó sang worker và tin rằng **@PreAuthorize**, **hasRole** hoặc security authorization sẽ tự nhìn thấy user đó. Spring Security thường đọc **SecurityContextHolder / Authentication** theo integration thực tế, không đọc biến tự tạo.

Ở chiều ngược lại, gắn một Authentication vào SecurityContextHolder **không tự bảo đảm người dùng còn quyền tại thời điểm một tác vụ nền chạy nhiều giờ sau**. Context propagation là kỹ thuật đưa một ngữ cảnh vào đúng thread; **quyết định authorization hợp lệ** là vấn đề nghiệp vụ và chính sách phải xét tại điểm sử dụng.

## 5. Spring Security hỗ trợ cơ chế chuyên biệt nào?

Các wrapper chính thức hoạt động theo một ý tưởng chung:

~~~text
caller thread (SecurityContextHolder)
     |
     | submit Runnable / Callable
     v
DelegatingSecurityContext* wrapper
     |
     | chọn SecurityContext theo constructor và thời điểm submit
     v
underlying executor
     |
     v
worker:
     set SecurityContextHolder -> delegate.run()/call()
                                   |
                                   v
                           finally clearContext()
~~~

Spring Security cung cấp:

| Loại lời gọi / executor | Công cụ |
| --- | --- |
| Chỉ một Runnable cụ thể | **DelegatingSecurityContextRunnable** |
| Một Callable<T> cụ thể | **DelegatingSecurityContextCallable<T>** |
| Executor với **execute(Runnable)** | **DelegatingSecurityContextExecutor** |
| ExecutorService có **submit/execute** | **DelegatingSecurityContextExecutorService** |
| Spring TaskExecutor | **DelegatingSecurityContextTaskExecutor** |
| Spring AsyncTaskExecutor và **@Async** | **DelegatingSecurityContextAsyncTaskExecutor** |
| Scheduled executor, scheduler | Các biến thể **DelegatingSecurityContextScheduledExecutorService / TaskScheduler** tương ứng |

**Các wrapper chuyên dụng** thực hiện việc chuyển ngữ cảnh ở ranh giới task và **dọn context trong finally**. Chúng không biến pool thành pool mới không giới hạn, không bảo đảm task được chấp nhận, và không tự mang mọi ThreadLocal ứng dụng khác đi theo.

### Một SecurityContext cố định hay context của từng lần submit?

Có hai dạng constructor đáng phân biệt:

**Dùng context cố định:**

~~~java
SecurityContext serviceContext = /* context đã tạo hợp lệ */;
Executor secured = new DelegatingSecurityContextExecutor(
        underlyingExecutor,
        serviceContext);
~~~

Đây là **đoạn minh họa**. Mọi task đi qua wrapper này nhận **cùng context** được cung cấp, bất kể caller hiện tại. Chế độ này chỉ phù hợp khi **có chủ đích sử dụng một identity cố định**, ví dụ một công việc nội bộ đã được phê duyệt. Nó **không thích hợp cho một shared request executor được tạo bằng context của user đầu tiên**.

**Dùng context hiện hành tại submit:**

~~~java
Executor secured = new DelegatingSecurityContextExecutor(
        underlyingExecutor);
~~~

Đây cũng là **đoạn minh họa**. Dạng constructor không nhận SecurityContext làm wrapper chọn **context từ SecurityContextHolder khi task được gửi vào wrapper**. Nó hữu ích cho nhiều request của người dùng khác nhau: mỗi lần submit dùng context đang hiện diện tại ranh giới gửi việc.

**Cảnh báo quan trọng:** các wrapper sử dụng tham chiếu **SecurityContext**, không nên coi đây là thao tác deep-copy toàn bộ Authentication/principal/authorities. Nếu code khác tiếp tục **mutate cùng SecurityContext object**, bản “capture” tham chiếu vẫn có thể quan sát thay đổi. Tránh sửa chung một SecurityContext giữa các thread; nếu thực sự cần snapshot bất biến, xác định chính xác field và nghiệp vụ cần thiết. Spring Security cũng khuyến nghị tạo một SecurityContext mới thay vì sửa Authentication ngay trên object context có thể đang được chia sẻ.

## 6. Ví dụ chạy được với Spring Security: đúng user trên cùng một worker

Ví dụ này dùng **Spring Security Core** nhưng **không cần web server, filter chain hoặc Spring Boot**. Nó chứng minh một ThreadPoolExecutor một worker lần lượt phục vụ request giả lập của **alice** và **bob**, wrapper lấy đúng SecurityContext ở mỗi lần submit, rồi dọn sạch context trên worker.

Cấu trúc:

~~~text
security-context-demo/
├── pom.xml
└── src/main/java/example/SecurityContextDelegationDemo.java
~~~

**pom.xml** (Java 17, Spring Security Core 6.5.11):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>security-context-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-core</artifactId>
            <version>6.5.11</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.SecurityContextDelegationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/SecurityContextDelegationDemo.java**:

~~~java
package example;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public class SecurityContextDelegationDemo {
    private static void signInForDemo(String name) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        Authentication authentication =
                UsernamePasswordAuthenticationToken.authenticated(
                        name,
                        "not-a-real-password",
                        AuthorityUtils.createAuthorityList("ROLE_USER"));

        context.setAuthentication(authentication);
        SecurityContextHolder.setContext(context);
    }

    private static String currentPrincipal() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();
        return auth == null ? "<none>" : auth.getName();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService raw = Executors.newSingleThreadExecutor();
        DelegatingSecurityContextExecutorService secured =
                new DelegatingSecurityContextExecutorService(raw);

        try {
            signInForDemo("alice");

            String rawAlice = raw.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            String securedAlice = secured.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            signInForDemo("bob");

            String securedBob = secured.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            String rawAfter = raw.submit(
                    SecurityContextDelegationDemo::currentPrincipal)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Raw Alice: " + rawAlice);
            System.out.println("Wrapped Alice: " + securedAlice);
            System.out.println("Wrapped Bob: " + securedBob);
            System.out.println("Raw sau wrappers: " + rawAfter);
        } finally {
            SecurityContextHolder.clearContext();
            secured.shutdown();
            if (!secured.awaitTermination(5, TimeUnit.SECONDS)) {
                secured.shutdownNow();
            }
        }
    }
}
~~~

Chạy từ thư mục có **pom.xml**:

~~~bash
mvn -q compile exec:java
~~~

**Stdout của ứng dụng**, không tính thông tin Maven/logging:

~~~text
Raw Alice: <none>
Wrapped Alice: alice
Wrapped Bob: bob
Raw sau wrappers: <none>
~~~

**Tại sao ví dụ đúng?**

1. **signInForDemo** tạo SecurityContext mới, rồi đặt Authentication giả lập cho thread đang submit. Đây **không phải quy trình đăng nhập production**; chỉ dùng để tạo fixture.
2. **raw.submit** đưa task vào worker chưa có SecurityContextHolder được thiết lập, vì context của main không tự truyền qua thread pool.
3. **secured.submit** dùng DelegatingSecurityContextExecutorService để bọc Callable. Wrapper lấy SecurityContext tương ứng ở **thời điểm submit** của Alice.
4. Khi worker thực thi, wrapper đặt context của Alice và gọi Callable; Callable đọc Authentication.getName() đúng là alice.
5. Caller thay context của mình bằng một **SecurityContext object mới** cho Bob. Wrapper của lần submit tiếp theo dùng Bob, mặc dù executor vẫn tái sử dụng cùng một worker.
6. Wrapper dọn SecurityContextHolder sau mỗi lần chạy. Task cuối chạy **raw** nên không còn thấy Alice hay Bob trên worker.
7. **get(timeout)** bảo đảm từng bước hoàn tất trước khi in. Kết quả không phụ thuộc worker name hay may rủi scheduler.

**Phạm vi:** đây là chương trình minh họa library integration, không khởi tạo Spring web security, không xác thực mật khẩu thật, không cấp quyền thực tế. Cấu hình Maven dùng một phiên bản phát hành Spring Security đã được xác nhận có artifact; trong dự án production, chọn bản patch được duy trì và quản lý dependency qua Spring Boot BOM thích hợp.

### Tại sao không tự viết lời gọi setContext mà bỏ finally?

Nếu một task tự làm:

~~~java
SecurityContextHolder.setContext(requestContext);
doWork();
// Quên SecurityContextHolder.clearContext().
~~~

Đây là **đoạn minh họa**. Worker có thể tiếp tục giữ Authentication cũ khi task kế tiếp được gán vào cùng thread. Hãy ưu tiên wrapper Spring Security đã kiểm soát lifecycle, thay vì copy-paste đoạn setContext/clearContext thủ công ở từng service.

## 7. MODE_INHERITABLETHREADLOCAL không giải quyết được thread pool

Spring Security cho phép cấu hình các chiến lược lưu SecurityContext, bao gồm:

- **MODE_THREADLOCAL**: mặc định thông thường trong servlet application; context thuộc thread hiện tại.
- **MODE_INHERITABLETHREADLOCAL**: thread con mới có thể thừa hưởng giá trị khi **thread được tạo**.
- **MODE_GLOBAL**: một context dùng toàn JVM, phù hợp một số loại ứng dụng đơn người dùng đặc thù, **không phải cấu hình thích hợp cho web server đa người dùng**.

Thay đổi chiến lược của **SecurityContextHolder** là thao tác mang tính **toàn cục**, không nên làm tùy tiện trong khi ứng dụng đang có request in-flight. Đặc biệt, MODE_INHERITABLETHREADLOCAL **không truyền đúng context theo từng lần submit vào một worker pool tái sử dụng**.

Ví dụ thuần Java minh họa sai lầm này, lưu thành **InheritablePoolTrap.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class InheritablePoolTrap {
    private static final InheritableThreadLocal<String> USER =
            new InheritableThreadLocal<>();

    private static String current() {
        String value = USER.get();
        return value == null ? "<empty>" : value;
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            USER.set("alice");
            String first = pool.submit(
                    InheritablePoolTrap::current)
                    .get(5, TimeUnit.SECONDS);

            // Thay caller nhưng pool vẫn tái sử dụng thread cũ.
            USER.set("bob");
            String second = pool.submit(
                    InheritablePoolTrap::current)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("Task đầu: " + first);
            System.out.println("Task sau: " + second);
        } finally {
            USER.remove();
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 InheritablePoolTrap.java
java InheritablePoolTrap
~~~

Stdout với executor một worker được tạo khi submit đầu tiên:

~~~text
Task đầu: alice
Task sau: alice
~~~

**Giải thích:** InheritableThreadLocal sao chép/thừa hưởng giá trị lúc **worker thread mới được tạo**. Worker không phải được tạo lại mỗi lần submit. Khi Bob gửi task, worker cũ vẫn giữ giá trị đã thừa hưởng từ Alice.

Nếu worker của pool được tạo **trước khi** caller set Alice, giá trị có thể là null; nếu worker được tạo bởi một thread khác, giá trị cũng có thể khác. Vì vậy đây **không phải cơ chế bảo đảm per-request propagation**. Ví dụ làm rõ một tình huống có kiểm soát chứ không tuyên bố mọi pool luôn trả Alice.

**Không chuyển SecurityContextHolder sang MODE_INHERITABLETHREADLOCAL trên web server để “sửa nhanh @Async”.** Nó còn có thể gây rò rỉ ngữ cảnh vào thread con không mong muốn hoặc chia sẻ tham chiếu SecurityContext có thể bị thay đổi.

## 8. Tích hợp đúng vào Spring @Async với AsyncTaskExecutor

Khi một method được đánh dấu **@Async**, Spring AOP thường chuyển lời gọi qua một **TaskExecutor**. Nếu method body cần đọc Authentication, có thể bọc một ThreadPoolTaskExecutor bằng **DelegatingSecurityContextAsyncTaskExecutor**.

Cấu hình dưới đây là **hai tệp minh họa trong ứng dụng đã tích hợp Spring Framework 6.x và Spring Security 6.x**; để biên dịch cần dependencies Spring Context và Security Core thích hợp, không phải javac thuần.

**SecureAsyncConfig.java**:

~~~java
package example.async;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class SecureAsyncConfig {
    @Bean("rawAsyncExecutor")
    public ThreadPoolTaskExecutor rawAsyncExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("secure-work-");
        return executor;
    }

    @Bean("securityAwareExecutor")
    public DelegatingSecurityContextAsyncTaskExecutor
            securityAwareExecutor(
                @Qualifier("rawAsyncExecutor")
                ThreadPoolTaskExecutor delegate) {

        // Không truyền context cố định ở lúc tạo bean.
        return new DelegatingSecurityContextAsyncTaskExecutor(
                delegate);
    }
}
~~~

**SecureReportService.java**:

~~~java
package example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class SecureReportService {
    @Async("securityAwareExecutor")
    public CompletableFuture<String> currentUserReport() {
        Authentication auth = SecurityContextHolder
                .getContext().getAuthentication();

        if (auth == null || !auth.isAuthenticated()) {
            throw new AccessDeniedException("Chưa xác thực");
        }

        return CompletableFuture.completedFuture(
                "report-for:" + auth.getName());
    }
}
~~~

Khi một bean/controller khác được bảo vệ bởi Spring Security gọi **secureReportService.currentUserReport()** qua Spring proxy:

1. Thread request đang có SecurityContextHolder do cơ chế security chính thức quản lý.
2. **@Async("securityAwareExecutor")** chọn wrapper Security-aware thay vì rawAsyncExecutor.
3. Wrapper **chụp ngữ cảnh của lời submit hiện tại**, đưa task tới rawAsyncExecutor rồi thiết lập context cho worker trước khi body method chạy.
4. Body có thể đọc Authentication tương ứng; khi task kết thúc, wrapper dọn SecurityContextHolder trên worker.
5. Return type **CompletableFuture<String>** giúp caller quan sát outcome, nhưng **không thay thế authorization tại điểm sử dụng dữ liệu**.

**Điều kiện bắt buộc:** bean do Spring quản lý, @EnableAsync được bật, method async là điểm vào thích hợp và lời gọi **đi qua Spring proxy**. Tự gọi this.currentUserReport() trong cùng service thường bỏ qua interception ở chế độ proxy.

**Lưu ý:** method này chỉ minh họa đọc Authentication và định danh. Trong sản phẩm thật, một lần đọc auth.getName() **không thay thế việc kiểm tra quyền đọc bản báo cáo**. Nếu task chạy trễ và quyền người dùng thay đổi, phải có chính sách ủy quyền lại thích hợp.

### Tại sao không đặt context của Alice trong @Bean?

Sai lầm đáng tránh:

~~~java
SecurityContext ctx = SecurityContextHolder.getContext();
return new DelegatingSecurityContextAsyncTaskExecutor(
        delegate, ctx);
~~~

Đây là **đoạn minh họa trong phương thức cấu hình bean**. Nếu vô tình cố định context lúc khởi tạo bean toàn cục, mọi task sau đó có thể dùng một context rỗng hoặc context của một người không liên quan. Constructor có đối số SecurityContext chỉ nên dùng khi **cố ý muốn mọi tác vụ của wrapper dùng cùng identity đã xác lập**. Đối với executor xử lý nhiều HTTP users, constructor không truyền context thường phù hợp hơn.

## 9. @Async và CompletableFuture không tự động truyền context ở mọi stage

Xét service:

~~~java
@Async("securityAwareExecutor")
public CompletableFuture<String> load() {
    return CompletableFuture.completedFuture("data");
}
~~~

Nếu gọi qua proxy, **body của load** có thể chạy trong worker đã được wrapper truyền SecurityContext.

Tuy nhiên:

~~~java
CompletableFuture<String> result = service.load()
        .thenApplyAsync(value -> {
            // Không được tự giả định SecurityContextHolder có ở đây.
            return enrich(value);
        });
~~~

Đây là **đoạn minh họa**, không phải chương trình độc lập. **thenApplyAsync** không truyền executor thường dùng default asynchronous execution facility của CompletableFuture (thường là ForkJoinPool.commonPool), nên callback có thể **không có SecurityContext** của request.

Ngay cả khi truyền **securityAwareExecutor** cho **thenApplyAsync**, cần hiểu thời điểm capture:

- Một callback được scheduling sau khi upstream hoàn thành có thể được gửi từ **thread làm upstream complete**, không phải từ thread HTTP request ban đầu.
- Wrapper với constructor không nhận SecurityContext lấy context **tại lúc callback được đưa vào Executor**, không nhất thiết là context gốc từ HTTP.
- Do đó, **từng ranh giới async phải được thiết kế và test riêng**, nhất là khi task pipeline có nhiều executor hoặc callback chạy sau khi request kết thúc.

Nếu toàn pipeline cần dùng một context **được xác định rõ cho một job duy nhất**, có thể tạo **wrapper theo từng job/request** với context cố định có kiểm soát, thay vì dùng shared singleton executor giữ một user:

~~~java
SecurityContext taskContext =
        SecurityContextHolder.getContext();

Executor perJob = new DelegatingSecurityContextExecutor(
        rawExecutor,
        taskContext);

CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> loadForAuthorizedUser(), perJob)
        .thenApplyAsync(
                value -> transformForAuthorizedUser(value), perJob);
~~~

Đây là **đoạn code minh họa** trong nơi có rawExecutor, loadForAuthorizedUser và transformForAuthorizedUser. Nó nhấn mạnh rằng **perJob wrapper** giữ cùng SecurityContext được chỉ định cho hai lần schedule. Nếu muốn một snapshot bất biến, code phải đảm bảo SecurityContext/Authentication được sở hữu và không bị mutate đồng thời; constructor **không deep-copy** context. Khi job kéo dài, quyền và trạng thái bảo mật có thể phải được kiểm tra lại ở thời điểm thực hiện.

**Không đưa một perJob wrapper chứa user-specific context vào một @Bean singleton dùng cho mọi request khác.** Đây là lỗi về scope/ownership có thể khiến cả ứng dụng chạy dưới identity sai.

## 10. SecurityContext khác ngữ cảnh logging/tracing

Trong ứng dụng Spring, một TaskDecorator thường được dùng để mang theo **MDC** hoặc một số metadata quan sát:

~~~java
import org.springframework.core.task.TaskDecorator;

public final class LoggingTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        String traceId = TraceIdHolder.get();  // Ở lúc submit.

        return () -> {
            try {
                TraceIdHolder.set(traceId);
                task.run();
            } finally {
                TraceIdHolder.remove();
            }
        };
    }
}
~~~

Đây là **đoạn minh họa không độc lập**, vì TraceIdHolder là abstraction giả định của ứng dụng. Nó không nên được sao chép nguyên vào production nếu TaskDecorator cần xử lý nested scopes, rollback trạng thái cũ hoặc tracing framework có contract khác.

**TaskDecorator** là hook chuẩn trên nhiều Spring TaskExecutor, hữu ích cho những phần cần thiết lập/cleanup context chung. Nhưng:

- **MDC không phải Authentication**; traceId có trong log không chứng minh caller đã được xác thực.
- **Truyền log context** không tự khiến @PreAuthorize hoặc quyền thao tác chạy dưới đúng user.
- **Không nên tự viết TaskDecorator copy và set một SecurityContextHolder tùy tiện** nếu thư viện đã cung cấp wrapper chuyên dụng. Các implementation security chính thức hiểu holder strategy và thiết kế lifecycle của chúng.
- Nếu kết hợp nhiều decorator/wrapper, phải kiểm tra **thứ tự thiết lập và cleanup**, trường hợp lỗi/reject, và cả việc stage chạy lại trên worker tái sử dụng.

**Micrometer Context Propagation / ContextSnapshot** có thể giúp chuyển một số context đã đăng ký accessors phù hợp giữa thread, nhưng **không được mặc nhiên coi SecurityContext được truyền tự động cho mọi library hoặc reactive stage**. Cần chọn đúng integration, cấu hình accessor và kiểm thử bảo mật trên đường thực thi thực tế.

## 11. Authentication và SecurityContext có thể mutable: cẩn thận chia sẻ tham chiếu

Một điểm dễ bỏ sót: **SecurityContext là object**. Khi một wrapper “capture SecurityContext”, trong nhiều trường hợp nó giữ **tham chiếu tới object** đó, không serialize và clone toàn bộ Authentication.

Ví dụ nguy hiểm:

~~~java
SecurityContext context = SecurityContextHolder.getContext();
context.setAuthentication(otherUserAuthentication);
~~~

Đây là **đoạn minh họa**. Nếu object context được tham chiếu bởi một worker đang chờ thực thi, việc mutate cùng object có thể thay đổi identity mà worker thấy. Trong luồng xử lý authentication bình thường, nên tạo một **SecurityContext mới** rồi gọi **SecurityContextHolder.setContext(newContext)**, thay vì sửa một object có thể đang được dùng chung, phù hợp với hướng dẫn của Spring Security.

Cần cân nhắc sâu hơn:

- Principal/UserDetails hoặc Authentication instance có thể chứa trạng thái mutable.
- Authorities/scope có thể thay đổi trong cơ sở dữ liệu sau khi task được xếp hàng.
- Credentials/tokens là dữ liệu nhạy cảm; không sao chép toàn bộ vào message queue hoặc log.
- Context capture không phải bằng chứng **token còn hạn** hoặc user vẫn có quyền ở thời điểm xử lý.
- Một background service không được nâng quyền chỉ vì caller gửi một userId hoặc role string không được kiểm chứng.

Khi task chỉ cần **gắn người tạo tác vụ vào audit record**, có thể đủ để chụp một **userId**/requestId immutable và xác thực được ở request boundary. Khi task thực sự cần gọi API phụ thuộc Spring method security, nên dùng **SecurityContext propagation có chủ đích** hoặc **tái xác thực/ủy quyền tại worker**, không chỉ truyền String tùy ý.

### Phân biệt identity dùng cho audit với quyền được dùng để thao tác

| Mục đích | Dữ liệu thường cần | Điều phải bảo đảm |
| --- | --- | --- |
| Audit: ai đã yêu cầu job? | userId, requestId, thời điểm và nguồn xác thực đã được kiểm chứng | Không bị client tự điền userId giả mạo; lưu được theo hợp đồng audit |
| Authorization: có được xuất dữ liệu này? | Authentication/authorities và policy đọc tài nguyên hiện hành | Kiểm tra ở điểm thao tác, cả resource-level permissions |
| Gọi downstream thay mặt user | Token có scope thích hợp, thời hạn và cơ chế delegation được thiết kế | Không dùng token đã hết hạn; giới hạn quyền |
| Job nội bộ theo service account | Service identity có quyền tối thiểu | Không chia sẻ quyền cao hơn cần thiết cho mọi task của app |
| Correlation logging | traceId hoặc requestId | Không coi ID log như bằng chứng danh tính |

**Propagation** giải quyết “context nào được nhìn thấy ở đây”; **authentication/authorization** giải quyết “context đó có hợp lệ và có quyền thực hiện hành động hiện tại không”.

## 12. Spring Security filter chain và ranh giới HTTP request

Trong Spring MVC với Security Filter Chain, các filter bảo mật quản lý **đọc/ghi/xóa** SecurityContext theo request và session/repository phù hợp.

Tùy cấu hình và phiên bản, **Spring MVC Callable** và các cơ chế MVC async chính thức có thể được Spring Security tích hợp propagation đặc biệt. Nhưng điều này **không có nghĩa** một Runnable tự gửi đến ExecutorService riêng hoặc một **CompletableFuture.supplyAsync** bất kỳ tự nhận SecurityContext.

Cần phân biệt:

~~~text
A. MVC-managed async flow
   Security Filter Chain -> MVC async integration -> Callable path
   Có thể được framework áp dụng security integration phù hợp.

B. User-created background work
   Controller -> customExecutor.submit(task)
   Cần khai báo rõ SecurityContext propagation hoặc policy khác.

C. Reactive flow
   WebFlux/Reactor publisher chain
   Dùng ReactiveSecurityContextHolder / Reactor Context,
   không giả định cách hoạt động của servlet ThreadLocal.
~~~

**Không dùng HttpServletRequest hoặc request-scoped object như một bản snapshot hợp lệ cho background job**; sau khi request hoàn tất, vòng đời tài nguyên có thể không còn. Nếu worker chỉ cần một vài tham số đã kiểm chứng, hãy chụp immutable DTO trước khi chuyển luồng.

## 13. Vì sao ThreadLocal và InheritableThreadLocal không phải chiến lược phân quyền?

Xét ba anti-pattern:

**A. Tự gắn userId vào một ThreadLocal ứng dụng và coi đó là identity đáng tin.**

~~~java
CURRENT_USER.set(request.getParameter("userId"));
executor.execute(() -> readSecret(CURRENT_USER.get()));
~~~

Đây là **đoạn mã sai nhằm minh họa**. Nó vừa tin userId do client gửi, vừa giả định ThreadLocal truyền sang executor. Không dùng giá trị này làm nguồn authorization.

**B. Đổi tất cả SecurityContextHolder sang MODE_GLOBAL.**

Một global context dùng chung cho tất cả threads là rủi ro nghiêm trọng trong server đa người dùng. Không khắc phục context loss bằng cách đánh đổi cách ly identity của các request.

**C. Bật MODE_INHERITABLETHREADLOCAL rồi tin thread pool luôn tạo worker mới.**

Pool có thể sống lâu, worker được tạo khi nhận task đầu tiên, và giá trị kế thừa có thể cũ hoặc của request khác. Các thread con không thuộc quyền kiểm soát ứng dụng có thể vô tình thừa hưởng identity. Giải pháp này không bảo đảm đúng context theo lần submit.

**D. Dùng một static mutable field cho Authentication hiện hành.**

~~~java
static Authentication CURRENT_AUTH;
~~~

Trong web server có nhiều request đồng thời, mọi thread cùng đọc/ghi một field nên có thể ghi đè user của nhau. Đây không phải một implementation thay thế cho SecurityContextHolder.

**E. Tạo một DelegatingSecurityContextExecutor với context của Alice ở application startup và chia sẻ cho toàn bộ người dùng.**

Đó là **fixed-context mode**, không phải mode capture theo request. Nếu muốn mỗi task dùng quyền của caller hiện hành, dùng wrapper không cố định context ở lần tạo bean và xác định đúng ranh giới submit.

## 14. Xử lý cleanup đúng cách kể cả khi task lỗi

Một wrapper context propagation an toàn phải coi **cleanup là bắt buộc**, không chỉ chạy khi nghiệp vụ thành công.

~~~text
set context for worker
    |
    +-- task returns normally --------+
    |                                 |
    +-- task throws exception --------+--> finally cleanup
    |                                 |
    +-- task cancellation/interruption+
~~~

Với custom ThreadLocal metadata, dùng try/finally và thận trọng với giá trị đang tồn tại trước khi wrapper chạy. Trong một cơ chế nested synchronous execution, **lưu previous rồi restore previous** có thể cần thiết; trong worker pool thuần với boundary độc lập, **clear** phải bảo đảm không lưu giá trị của request trước. Không chọn một cách cleanup chung bất kể framework có hợp đồng gì.

Với Spring Security, **DelegatingSecurityContextRunnable/Callable** và các wrapper executor dùng cơ chế setup/clear của SecurityContextHolder. Đừng chèn thêm một finally thủ công **clearContext()** ở giữa một flow mà framework đang sở hữu và sau đó còn cần dùng identity, nếu điều đó phá nested scope. Nên để wrapper chuyên dụng làm chủ toàn bộ ranh giới.

**Nếu task bị reject trước khi bắt đầu:** body và finally **bên trong body không bao giờ chạy**. Do đó, không phân bổ tài nguyên hoặc giữ reference nhạy cảm ở caller rồi trông cậy vào finally của task để dọn. Khi wrapper được tạo nhưng task chưa thực thi, cần xem lifecycle của Runnable/Callable và queue theo executor.

## 15. Thời điểm capture: submit, execute và future completion

Ngữ cảnh của caller chỉ đúng tại **một thời điểm**. Đây là yếu tố rất quan trọng nếu tác vụ được gửi trễ:

~~~text
Request thread Alice:
    t0: SecurityContextHolder = Alice
    t1: create Runnable
    t2: later, thread context đã đổi
    t3: executor.execute(Runnable)
                                |
                                +-- wrapper capture tại execute/submit
~~~

Với wrapper không truyền SecurityContext cố định, **context được chọn ở lúc nó wrap task cho lần submit**. Nếu code tạo Runnable dưới Alice nhưng chỉ submit khi context đã bị xóa, task có thể không mang Alice.

Tương tự, với **CompletableFuture**:

~~~java
CompletableFuture<String> future =
        CompletableFuture.supplyAsync(
                () -> load(), securedExecutor);
~~~

Đây là **đoạn minh họa**. Với Executor wrapper capture tại execute, supplier có context theo thread đã gọi supplyAsync ở lúc scheduling, miễn không có tầng xử lý khác thay đổi ngữ cảnh.

Khi một **thenApplyAsync** được scheduling sau khi upstream hoàn tất, thread yêu cầu executor chạy callback có thể là thread của upstream completion. Nếu thread đó không có SecurityContext phù hợp, một wrapper capture-per-submit cũng không tự tìm lại request cũ.

Muốn pipeline nhiều bước giữ context nghiệp vụ nhất quán, hãy chọn rõ:

1. Dùng **per-job context** được quản lý an toàn và wrapper riêng cho scope ấy (không dùng lại như singleton của toàn ứng dụng).
2. Hoặc **chụp immutable user ID/command** và ủy quyền lại tại từng bước có side effect.
3. Hoặc dùng integration context propagation phù hợp với loại pipeline/framework, rồi test thực tế.
4. Không chỉ nối thêm Async callbacks mà không chỉ định executor hoặc context contract.

## 16. Ranh giới bảo mật trong tác vụ nền dài hạn

Context capture có thể đúng lúc request bắt đầu, nhưng sau vài phút hoặc vài giờ:

- Quyền người dùng có thể bị thu hồi.
- Session/token có thể hết hạn.
- Resource permission có thể thay đổi.
- Người dùng có thể không còn là thành viên tổ chức.
- Job có thể được chuyển sang một process/queue khác không chia sẻ ThreadLocal.

Vì vậy, lựa chọn cần phù hợp yêu cầu nghiệp vụ:

| Kiểu tác vụ | Mô hình thường phù hợp |
| --- | --- |
| Tác vụ ngắn trong cùng process và cần method security | Dùng Spring Security wrapper trên executor, kiểm tra context theo contract |
| Tác vụ chỉ ghi audit ai yêu cầu | Chụp immutable audit identity/requestId từ ngữ cảnh đã xác thực |
| Tác vụ lâu hoặc có quyền nhạy cảm | Lưu job identity, xác thực/ủy quyền lại tại thời điểm thực hiện |
| Công việc qua message broker | Truyền metadata đã xác thực/ký hoặc job ID; bên nhận xây authorization context theo chính sách |
| Tác vụ hệ thống không đại diện user nào | Identity riêng của service account với quyền tối thiểu, không tái sử dụng context người dùng |
| Reactive/WebFlux pipeline | ReactiveSecurityContextHolder trên Reactor Context, không chỉ servlet ThreadLocal |

**Không serialize nguyên SecurityContext** (đặc biệt credentials, token hoặc principal object lớn) vào durable queue chỉ để dễ truyền ngữ cảnh. Chỉ lưu những dữ liệu tối thiểu, có thể chứng thực lại và đáp ứng quy định bảo mật của hệ thống.

## 17. Cách chọn DelegatingSecurityContext wrapper phù hợp

| Bạn đang có | Nên xem xét | Lưu ý |
| --- | --- | --- |
| Một Runnable cần chạy với context hiện tại | DelegatingSecurityContextRunnable | Capture theo constructor; cleanup được hỗ trợ |
| Một Callable trả dữ liệu | DelegatingSecurityContextCallable | Dùng khi cần result/exception qua Callable |
| JDK Executor chỉ có execute | DelegatingSecurityContextExecutor | Không có submit/get trực tiếp ở interface Executor |
| JDK ExecutorService có submit/Future | DelegatingSecurityContextExecutorService | Bao cả Runnable và Callable, quản lý lifecycle delegate theo wrapper |
| Spring TaskExecutor | DelegatingSecurityContextTaskExecutor | Có thể chọn context cố định hoặc theo submit |
| Spring @Async với AsyncTaskExecutor | DelegatingSecurityContextAsyncTaskExecutor | Đăng ký bean executor có tên rồi dùng @Async("...") |
| Chạy định kỳ/scheduled | Các wrapper ScheduledExecutorService/TaskScheduler tương ứng | Phân biệt job chạy theo service identity hay theo caller |

**Đừng nhầm:** wrapper xử lý context không nâng **corePoolSize**, **maxPoolSize** hoặc dung lượng queue của underlying executor. Nếu pool bị overload, task có thể bị reject; nếu executor chưa nhận, không có worker để mang context. Vẫn phải xử lý TaskRejectedException/RejectedExecutionException và retry policy.

## 18. Test an toàn: hai người dùng, cùng một worker, không rò context

Một kiểm thử integration có giá trị cần đủ các trường hợp:

1. Thiết lập context **Alice** trên caller.
2. Submit vào **raw executor** và xác minh worker không tự có Alice.
3. Submit qua **security wrapper** và xác minh worker thấy Alice.
4. Đặt **SecurityContext object mới** của **Bob**, submit qua cùng wrapper/pool và xác minh thấy Bob.
5. Submit task raw ngay sau đó trên **chính worker** và xác minh **không còn Alice/Bob**.
6. Cho task được bảo vệ ném exception; xác minh wrapper vẫn cleanup sau exceptional completion.
7. Nếu sử dụng CompletableFuture và nhiều executor, kiểm tra từng **thenApplyAsync**/thenComposeAsync khi upstream complete trên thread khác.
8. Kiểm tra một nhánh **executor rejection** và một nhánh shutdown; không báo job đã được tiếp nhận nếu task không chạy.
9. Nếu test với @Async, luôn gọi **Spring-managed bean qua proxy**, không new bean trực tiếp và không self-invocation.
10. Khi cần ổn định lịch chạy, dùng **CountDownLatch** và **Future.get(timeout)**, không chỉ Thread.sleep để mong worker đúng thời điểm.

**Không chỉ assert kết quả nghiệp vụ đúng.** Một đoạn code chạy dưới Authentication sai vẫn có thể trả kết quả giống kỳ vọng trong trường hợp dữ liệu công khai. Test phải quan sát **principal/authorities trong worker** và việc cleanup sau task.

### Kiểm tra lỗi trong công việc bảo mật

Một integration test thực tế nên có test:

~~~java
Future<?> failed = secured.submit(() -> {
    if (SecurityContextHolder.getContext()
            .getAuthentication() == null) {
        throw new IllegalStateException("Thiếu context");
    }
    throw new IllegalStateException("Giả lập lỗi nghiệp vụ");
});
~~~

Đây là **đoạn minh họa** trong scope có secured kiểu ExecutorService và caller đã set SecurityContext. Sau khi failed.get() báo lỗi (ExecutionException), submit một task **raw** vào cùng worker để xác minh context đã bị dọn. Đừng dùng kết quả Future.isDone() làm bằng chứng rằng cleanup đã xong mà không có quan sát thích hợp.

## 19. Những nhầm lẫn rất thường gặp

**“SecurityContextHolder dùng ThreadLocal nên tôi có thể truyền bằng bất kỳ ThreadLocal wrapper nào.”** Sai. Cần giữ đúng security strategy, identity và lifecycle; dùng wrapper Spring Security hoặc integration có hợp đồng tương đương.

**“Cứ tạo ThreadLocal<String> USER rồi set username là Spring method security nhận biết.”** Sai. Spring Security đọc SecurityContext/Authentication theo cơ chế của nó, không đọc biến tùy ý của bạn.

**“Đổi sang InheritableThreadLocal là đủ cho ThreadPoolTaskExecutor.”** Sai. Inheritance chủ yếu xảy ra khi thread mới được tạo; worker pool có thể tái sử dụng giá trị cũ.

**“MODE_GLOBAL giúp mọi worker thấy user hiện tại, nên tốt cho web.”** Sai. Nó có thể làm nhiều request chia sẻ identity, không phù hợp server đa người dùng.

**“Đã dùng DelegatingSecurityContextAsyncTaskExecutor là mọi CompletableFuture stage tự có security context.”** Sai. Mỗi lần scheduling/Executor khác là một ranh giới cần xem xét.

**“Constructor có SecurityContext và constructor không có SecurityContext giống nhau.”** Sai. Một dạng dùng context cố định; dạng kia capture context hiện tại khi submit.

**“Wrapper Spring Security deep-copy toàn bộ Authentication.”** Không nên giả định. Có thể giữ reference SecurityContext; tránh mutate context dùng chung và xem lại authorization của job chạy trễ.

**“SecurityContext đã được propagate thì job được quyền đọc mọi resource.”** Sai. Propagation không thay thế authorization/resource-level checks.

**“@Async luôn chạy trên worker có đúng identity.”** Sai. Cần Spring proxy, executor đã đăng ký, wrapper phù hợp và context hợp lệ ở submit.

**“Dùng TaskDecorator truyền MDC là đã truyền SecurityContext.”** Sai. MDC và SecurityContext là hai miền khác nhau; không dùng log metadata để quyết định quyền.

**“Lưu nguyên SecurityContext vào queue để xử lý ngày mai là an toàn.”** Không mặc nhiên. Context có thể chứa dữ liệu nhạy cảm và quyền đã lỗi thời; job lâu dài cần chính sách identity/ủy quyền rõ ràng.

**“Task kết thúc sẽ tự remove ThreadLocal do tôi set.”** Sai. ThreadLocal không tự remove khi Runnable hoàn tất; pool giữ thread, nên cần cleanup ở ranh giới.

**“Một userId client gửi trong request là đủ chứng minh người đó đã xác thực.”** Sai. User identity dùng cho auth/audit phải được lấy từ cơ chế xác thực đáng tin và kiểm tra theo policy.

**“Reactor dùng thread pool nên tôi cứ dùng SecurityContextHolder từ servlet.”** Không đúng mô hình chung. Reactive security dùng **Reactor Context/ReactiveSecurityContextHolder**; việc đổi thread trong reactive pipeline không tương đương ThreadLocal-based servlet flow.

## 20. Bài tập suy luận

**Câu 1.** Caller có SecurityContext của Alice nhưng gửi Runnable qua Executors.newFixedThreadPool mà không wrapper. Worker có chắc nhìn thấy Alice không?

**Đáp án:** Không. Với MODE_THREADLOCAL mặc định, worker thường không tự có context của caller.

**Câu 2.** Một worker được tái sử dụng đã từng chạy tác vụ của Bob. Task mới của Alice chỉ dùng ThreadLocal tùy ý và quên remove sau khi chạy. Rủi ro là gì?

**Đáp án:** Task sau có thể thấy stale value của Alice hoặc Bob nếu thread không được dọn; rủi ro rò thông tin giữa request.

**Câu 3.** DelegatingSecurityContextExecutor được tạo bằng constructor chỉ nhận Executor. Lúc submit từ Alice và Bob, nó dùng context nào?

**Đáp án:** Theo cơ chế wrapper hiện hành, nó lấy SecurityContextHolder ở **thời điểm mỗi lần task được gửi vào wrapper**, không cố định một user từ lúc khởi tạo wrapper.

**Câu 4.** Nếu constructor nhận một SecurityContext của service account, rồi wrapper được dùng bởi nhiều caller khác nhau, các task nhận context nào?

**Đáp án:** Cùng context cố định đã được cung cấp, theo thiết kế của constructor đó; chỉ hợp lý nếu việc dùng identity chung có chủ đích và đúng quyền.

**Câu 5.** Vì sao MODE_INHERITABLETHREADLOCAL có thể để worker tiếp tục thấy Alice khi Bob gửi task?

**Đáp án:** Nó truyền giá trị lúc worker được tạo; pool có thể tái sử dụng worker thay vì sinh một thread mới tại mỗi submit.

**Câu 6.** @Async("securityAwareExecutor") method thấy đúng Alice. Sau đó caller dùng thenApplyAsync(fn) không truyền executor. Có chắc fn thấy Alice không?

**Đáp án:** Không. CompletableFuture có default async executor riêng, thường commonPool. Phải xét context ở stage đó.

**Câu 7.** Task chạy trong worker có Authentication của Alice nhưng quyền trên một resource vừa bị thu hồi. Chỉ nhìn auth.getName() có cho phép truy cập resource không?

**Đáp án:** Không. Cần áp dụng policy authorization phù hợp tại thời điểm thao tác; context capture không bảo đảm quyền còn hiệu lực.

**Câu 8.** Một custom wrapper set SecurityContextHolder nhưng không clear trong finally vì task đã hoàn thành. Có vấn đề gì?

**Đáp án:** Có. Worker thread pool có thể tái sử dụng và giữ Authentication cũ, rò dữ liệu/nguy cơ chạy với user sai.

**Câu 9.** Một task cần ghi lại ai đã tạo job, nhưng không cần thực thi thay mặt người dùng. Có nhất thiết giữ nguyên SecurityContext trong queue nhiều giờ không?

**Đáp án:** Không. Có thể chụp userId đã xác thực và dữ liệu audit tối thiểu, lưu theo hợp đồng nghiệp vụ, không giữ credentials/Authentication dư thừa.

**Câu 10.** Reactor/WebFlux có nên dùng các giả định y hệt ThreadLocal của servlet security không?

**Đáp án:** Không. Reactive security dùng Reactor Context và integration riêng; phải xác định loại ứng dụng và cơ chế propagation thực sự.

## 21. Checklist triển khai

- [ ] Xác định loại context cần dùng: **SecurityContext** hay metadata logging/tracing.
- [ ] Không thay thế Spring Security Authentication bằng **ThreadLocal<String> userId** tự tạo.
- [ ] Với Spring Security servlet, hiểu rõ **SecurityContextHolderStrategy / MODE_THREADLOCAL** đang dùng.
- [ ] Không dùng **MODE_GLOBAL** trong web app đa người dùng để sửa context loss.
- [ ] Không dùng **MODE_INHERITABLETHREADLOCAL** làm lời giải mặc định cho thread pool.
- [ ] Với Runnable/Callable, chọn **DelegatingSecurityContextRunnable/Callable** khi phù hợp.
- [ ] Với Executor/ExecutorService, dùng **DelegatingSecurityContextExecutor/ExecutorService**.
- [ ] Với Spring @Async, xác định **DelegatingSecurityContextAsyncTaskExecutor** và tên bean đúng.
- [ ] Không cố định một user SecurityContext trong singleton executor xử lý nhiều request.
- [ ] Tránh chia sẻ/mutate cùng SecurityContext instance giữa nhiều thread.
- [ ] Xác nhận **@Async đi qua proxy**, không self-invocation.
- [ ] Nếu pipeline có nhiều CompletableFuture stages, xác định context ở **từng lần scheduling**.
- [ ] Dùng **TaskDecorator hoặc tracing integration** cho MDC/request correlation, không đánh đồng với security.
- [ ] Cleanup context trong finally hoặc để wrapper Spring Security chuyên dụng đảm trách.
- [ ] Truyền input nghiệp vụ bằng **immutable snapshot**, không giữ HttpServletRequest/transaction ở background.
- [ ] Khi job chạy trễ hoặc lâu dài, kiểm tra lại quyền/token/resource theo policy.
- [ ] Test **Alice → Bob trên cùng một worker**, rồi raw task để xác minh không rò context.
- [ ] Kiểm tra cả lỗi/rejection/shutdown, timeout và cleanup khi task bất thường.
- [ ] Không serialize credentials hoặc SecurityContext nhạy cảm vào queue/log một cách tùy tiện.

## Kết luận

**ThreadLocal chỉ cung cấp nơi lưu trữ theo thread; SecurityContextHolder là cổng truy cập vào một ngữ cảnh bảo mật có ý nghĩa xác thực và phân quyền.** Khi công việc đi qua ExecutorService, CompletableFuture hoặc Spring @Async, context của request không tự đi theo mọi thread. Tự truyền một ThreadLocal tùy ý có thể gây mất context, rò rỉ giữa request và nhầm lẫn identity.

Với Spring Security, ưu tiên **DelegatingSecurityContextRunnable/Callable** hoặc những wrapper **DelegatingSecurityContextExecutor / ExecutorService / AsyncTaskExecutor** tương ứng. Chọn rõ **context cố định hay context tại lúc submit**, bảo đảm **cleanup trên worker**, không coi InheritableThreadLocal là phương án mặc định cho pool, và test nhiều người dùng trên **cùng một worker tái sử dụng**. Cuối cùng, **context propagation không thay thế authorization**: dữ liệu, token và quyền phải được kiểm chứng theo thời điểm thao tác và yêu cầu nghiệp vụ.

**Tài liệu chính thức để tra cứu:**

- [Spring Security — Concurrency Support](https://docs.spring.io/spring-security/reference/features/integrations/concurrency.html): các wrapper DelegatingSecurityContext* và cơ chế set/clear.
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): SecurityContextHolder, Authentication và holder strategy.
- [DelegatingSecurityContextAsyncTaskExecutor Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/task/DelegatingSecurityContextAsyncTaskExecutor.html).
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): TaskExecutor, TaskDecorator và @Async.
- [Java SE 17 — ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html), [InheritableThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InheritableThreadLocal.html) và [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
