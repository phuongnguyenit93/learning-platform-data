# Đóng tài nguyên và dọn ngữ cảnh trong mọi nhánh kết thúc của Spring AOP

## 1. Mục tiêu: không để tài nguyên hoặc ngữ cảnh rò rỉ sau method execution

Khi một Spring service được gọi qua AOP proxy, custom `@Aspect` có thể tạo **tài nguyên tạm** hoặc **ngữ cảnh theo lời gọi** để tracing, audit, logging, đo thời gian, kiểm soát resource handle hay tích hợp một client bên ngoài. Những đối tượng này phải được dọn dẹp cả khi target **trả về thành công**, **trả `null`**, **hoàn tất `void`**, **ném exception**, hoặc khi interceptor bên trong trả sớm.

Ví dụ:

- Aspect đặt mã tương quan vào `ThreadLocal` trước khi gọi `proceed()`. Nếu quên xóa/khôi phục, thread pool có thể mang mã của request trước vào lần xử lý sau.
- Aspect tự mở `AutoCloseable` lease để theo dõi một call. Nếu target ném exception, chỉ đóng trong nhánh success sẽ làm lease bị rò rỉ.
- Aspect tạo MDC logging fields tạm thời. Nếu scope lồng nhau, gọi `clear()` vô điều kiện có thể xóa luôn ngữ cảnh hợp lệ của caller.
- Aspect ghi nhận “cleanup complete” nhưng callback cleanup tự ném exception, khiến exception gốc bị che khuất.
- Aspect tưởng method trả `CompletableFuture` bình thường nghĩa là công việc asynchronous đã kết thúc và đóng tài nguyên cần dùng về sau quá sớm.

**Mục tiêu thực hành:** thiết kế cleanup **theo vòng đời của từng invocation Spring AOP**: tài nguyên nào aspect thật sự sở hữu thì aspect đóng; context tạm do aspect đặt thì aspect khôi phục đúng trạng thái trước đó; exception/result của target được giữ nguyên nếu cleanup chỉ nhằm quan sát. Đối với transaction/security/HTTP request context do Spring infrastructure sở hữu, không tự tiện đóng hoặc xóa.

**Phạm vi:** Spring Framework, Spring-managed `@Aspect`, `@After` (after-finally), `@Around` với Java `try/finally` và `try-with-resources`, proxy boundary, nested invocation, transaction/async/reactive nuances và test. Đây không phải hướng dẫn AspectJ compile-time/load-time weaving.

## 2. Điều Spring bảo đảm và điều Spring không thể bảo đảm

Spring Framework mô tả `@After` là **after (finally) advice**: nó được gọi khi một **matched method execution** thoát ra, bất kể đường trả về bình thường hay bằng exception. `@AfterReturning` chỉ dành cho normal return, `@AfterThrowing` dành cho exceptional exit. Spring cũng hỗ trợ `@Around` với `ProceedingJoinPoint.proceed()`, nhờ đó chính advice có thể dùng `finally` bảo vệ phần scope mà nó tạo.

Nhưng cụm “mọi nhánh kết thúc” phải hiểu **đúng ranh giới**:

1. **Đã đi vào advice hay chưa?** `@After` không chạy nếu method không qua Spring proxy, pointcut không match hoặc một outer interceptor short-circuit **trước khi** tới advisor của nó.
2. **Một lần method execution hay hoàn tất tác vụ bất đồng bộ?** Khi method trả `Future`/`Mono`/`Flux` bình thường, một Spring proxy advice đồng bộ có thể kết thúc trước khi dữ liệu/task bên trong hoàn thành.
3. **Target đã return hay transaction đã commit?** `@After` quanh target execution không mặc nhiên là callback “after DB commit”; vị trí transaction advisor và transaction propagation quyết định thời điểm.
4. **Cleanup có hoàn toàn không thể lỗi?** `finally` cố chạy cleanup trong Java khi thread thực thi bình thường qua control flow, nhưng không phải cam kết khi process bị kill, JVM dừng bất thường hoặc xảy ra lỗi hệ thống ngoài khả năng kiểm soát. Bản thân cleanup cũng có thể ném exception.
5. **Ai sở hữu tài nguyên?** Tài nguyên được `PlatformTransactionManager` hoặc Servlet/Spring Security filter quản lý không thuộc quyền custom aspect tự `close()`/`clear()`.
6. **Nhiều Spring aspects cùng tham gia?** Advice precedence có thể ảnh hưởng phạm vi cleanup: aspect ngoài có thể bọc nhiều interceptors hơn aspect trong.

Bởi vậy, không viết “`@After` luôn chạy cho mọi method gọi trong ứng dụng”. Câu đúng là: **khi một lời gọi method được Spring proxy intercept và đã đi vào `@After` advice phù hợp, Spring áp dụng after-finally khi join point thoát**, với các hạn chế proxy/invocation lifecycle ở trên.

## 3. Bảng chọn cơ chế cleanup phù hợp trong Spring AOP

| Mục tiêu | Cơ chế ưu tiên | Lý do |
| --- | --- | --- |
| Chạy bước dọn sau normal return hoặc exception của method matching | `@After` | Semantics after-finally của Spring AOP; không cần quyền điều khiển `proceed()`. |
| Aspect **tự cấp phát** resource trước invocation và phải đóng đúng handle của lần gọi ấy | `@Around` + `try/finally` hoặc `try-with-resources` | Resource handle nằm trong biến cục bộ của chính invocation; tránh dùng singleton aspect field chia sẻ. |
| Tạm đặt `ThreadLocal`/MDC cho target và khôi phục giá trị trước invocation | `@Around` + capture/restore trong `finally` | Scope bao quanh chính phần target dùng context; hỗ trợ nested calls. |
| Ghi nhận **chỉ normal-return value** | `@AfterReturning(returning="result")` | Quan sát kết quả; **không đủ** để cleanup trên exceptional exit. |
| Log/metric exception loại cụ thể | `@AfterThrowing(throwing="error")` | Đọc lỗi; **không đủ** để cleanup trên success. |
| Cleanup resource do Spring transaction management quản lý | Transaction manager/`TransactionSynchronization` | Resource lifecycle phụ thuộc transaction, có thể sống dài hơn một service method. |
| Dọn request-level SecurityContext | Spring Security filter/security infrastructure | Custom service aspect không nên xóa authentication/context của caller. |
| Cleanup khi future hoàn tất hoặc publisher terminal | Callback API/reactive operators đúng lifecycle | Synchronous `finally` trong AOP chỉ bảo vệ lúc method trả wrapper. |

**Quy tắc chọn:** nếu chỉ cần dọn ở cuối method mà không khởi tạo context riêng, `@After` đơn giản hơn. Nếu advice đã tạo một context/resource ở **đầu** call và cần sở hữu handle, `@Around` + `finally` thể hiện ownership/timing rõ nhất.

## 4. @After là after-finally, không phải after-success

Ví dụ annotation từ `org.aspectj.lang.annotation`:

```java
@Aspect
public class CompletionAuditAspect {
    @After(
        "execution(public * com.example.cleanup.TaskService.*(..))"
    )
    public void afterCompletion(JoinPoint jp) {
        System.out.println("finished:" + jp.getSignature().getName());
    }
}
```

Đây là đoạn minh họa, cần imports `Aspect`, `After`, `JoinPoint`, aspect bean và target Spring bean để chạy. Khi target method matching **return bình thường** hoặc **throw exception**, advice có thể ghi sự kiện kết thúc trong cả hai trường hợp.

**Phân biệt:**

```java
@AfterReturning(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterSuccess() {
    // Không chạy nếu method thoát bằng exception.
}

@AfterThrowing(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterError() {
    // Không chạy nếu method return bình thường.
}

@After(
    "execution(public * com.example.cleanup.TaskService.*(..))"
)
public void afterFinally() {
    // Dành cho bước dọn ở cả hai kiểu thoát.
}
```

Các đoạn trên minh họa **ba advice có semantics khác nhau**, không thêm vào project demo chính nếu không muốn thay stdout. Hai callbacks `@AfterReturning`/`@AfterThrowing` **không phải** một bộ đôi đủ thay thế cleanup chung khi còn các failure modes như chính advice khác ném exception hoặc outer chain short-circuit trước/giữa các layers.

### 4.1. @After không tự nhận return và exception object

`@After` có thể nhận `JoinPoint` để lấy method signature/arguments. Nó **không có cùng cú pháp `returning` của `@AfterReturning` hay `throwing` của `@AfterThrowing` để tự bind đồng thời cả result và exception**.

Nếu cleanup chỉ cần release resource, không cần quan sát payload. Nếu phải biết outcome, có thể kết hợp với các advice thích hợp hoặc dùng **một `@Around`** kiểm soát normal/exception branches mà vẫn đặt cleanup trong `finally`.

### 4.2. Thận trọng với exception do @After ném ra

Ví dụ nguy hiểm:

```java
@After("execution(* com.example.cleanup.TaskService.*(..))")
public void close() {
    throw new IllegalStateException("cleanup failed");
}
```

Đây là anti-pattern minh họa. Nếu target đang ném lỗi gốc, exception do cleanup ném thêm có thể làm caller quan sát lỗi khác, tùy chuỗi advisors. **After-finally nghĩa là có cơ hội cleanup khi join point thoát; không nghĩa Spring tự cách ly mọi lỗi phát sinh trong cleanup.**

Nếu cleanup best-effort, quyết định rõ policy logging/suppression. Nếu resource close failure làm operation thất bại theo contract, truyền lỗi một cách chủ đích và giữ cause/suppressed exceptions khi cần.

## 5. @Around + try/finally cho tài nguyên aspect sở hữu

`@Around` là lựa chọn tự nhiên khi resource/context được tạo **trong cùng một advice**:

```java
@Around("execution(public * com.example.cleanup.TaskService.*(..))")
public Object withResource(ProceedingJoinPoint pjp) throws Throwable {
    final ResourceHandle handle = openMyResource();
    try {
        return pjp.proceed();
    } finally {
        handle.close();
    }
}
```

Đây là đoạn minh họa cần `ResourceHandle`, `openMyResource()` và import Java/Spring tương ứng. Nó đảm bảo trên các đường Java control flow thông thường đi ra khỏi `proceed()`, `handle.close()` được gọi.

Tuy nhiên:

- Nếu `openMyResource()` **throw trước `try`**, handle chưa được tạo để đóng; những trạng thái tạm nào đã được thay đổi trước đó vẫn cần được bảo vệ bằng một outer `try/finally`.
- Nếu `handle.close()` throw trong `finally` khi `proceed()` đang throw, exception cleanup có thể **che exception gốc**.
- Nếu scope được tạo theo invocation, không lưu handle vào field mutable của singleton aspect để các threads ghi đè handle của nhau.
- `pjp.proceed()` chỉ nên chạy một lần nếu không có retry/short-circuit được định nghĩa rõ; cleanup vẫn phải tính cho mỗi attempt khi có retry.
- Nếu resource handle thuộc target hoặc transaction infrastructure, không tự close chỉ vì có thể lấy reference tới nó.

### 5.1. try-with-resources giữ ngoại lệ gốc tốt hơn finally close thủ công

Java `try-with-resources` có quy tắc suppression khi cả body và `close()` đều throw:

```java
try (MyResource resource = acquire()) {
    return pjp.proceed();
}
```

Nếu `proceed()` throw lỗi A và `resource.close()` throw lỗi B, với `try-with-resources`, lỗi A thường là primary, B được lưu trong `A.getSuppressed()`; đây là cơ chế **Java**, rất hữu ích cho Spring AOP cleanup. Nếu body return bình thường nhưng close throw, thì caller có thể nhận close failure: đó là behavior cần được ghi rõ nếu resource release là critical.

**Mã minh họa**: `MyResource`/`acquire()` là giả định. Trong project runnable ở mục 9, `Lease.close()` không ném exception để giữ rõ hợp đồng bảo toàn normal/exception outcome.

### 5.2. Nếu acquisition fail giữa chừng

Với nhiều resources:

```java
try (ResourceA a = openA();
     ResourceB b = openB()) {
    return pjp.proceed();
}
```

Nếu `openA()` thành công nhưng `openB()` throw, Java `try-with-resources` vẫn đóng `a`. Đóng theo thứ tự ngược với thứ tự mở. Điều này tránh rò resource A do việc acquire B fail.

Đây là đoạn minh họa độc lập về syntax Java; không mặc định Spring quản lý hai resource types giả định này. Đối với resources do Spring/JPA/JDBC quản lý, sử dụng lifecycle APIs của framework thay vì tự ý đóng.

## 6. Dọn ThreadLocal/context: khôi phục trạng thái trước đó, không phải luôn clear

Một custom Spring aspect có thể tạm đặt **correlation ID, tracing label hoặc request-scoped marker** vào `ThreadLocal` để service downstream đọc trên cùng thread:

```java
String previous = Context.current();
Context.set("task:" + pjp.getSignature().getName());
try {
    return pjp.proceed();
} finally {
    Context.set(previous);
}
```

Đây là đoạn minh họa. `Context.set(null)` phải thực hiện `ThreadLocal.remove()` trong implementation để không giữ reference dư. **Tại sao khôi phục** thay vì `remove()` vô điều kiện?

Giả sử caller đã đặt `"request-42"`, outer aspect tạm đổi thành `"service:save"`. Khi method xong, code dùng `remove()` vô điều kiện sẽ **xóa luôn request context do caller sở hữu**. Code capture `previous` rồi restore `previous` đúng hơn:

```text
Caller scope: context = request-42
  Aspect enters: previous = request-42
  Aspect sets: context = service:save
    Target reads: service:save
  Aspect finally restores: context = request-42
Caller continues: context = request-42
```

Với nested invocations:

```text
Caller context = caller
  Outer Spring advice sets outer
    Collaborator call via second Spring proxy sets inner
    Inner finally restores outer
  Outer finally restores caller
```

Mỗi layer phải chỉ restore **trạng thái mà layer ấy đã thay**. Nếu mỗi advice gọi `clear()` global, inner layer có thể phá context của outer layer.

### 6.1. ThreadLocal và ThreadPool

Thread pool tái sử dụng threads. Nếu advice đặt `ThreadLocal` mà không restore/remove trong `finally`, một invocation tiếp theo trên cùng worker thread có thể quan sát marker cũ, gây:

- Log correlation sai (dính request/tenant trước);
- Giữ object reference lớn lâu hơn cần thiết;
- Rò dữ liệu ngữ cảnh giữa các requests/tasks;
- Test flaky phụ thuộc thread reuse và thứ tự chạy.

Tuy nhiên, **không tự xóa mọi ThreadLocal của framework khác**. Aspect chỉ dọn ThreadLocal do nó tạo/quản lý, hoặc scope API công khai có ownership rõ.

### 6.2. MDC/SLF4J

Nếu logging tích hợp SLF4J MDC, một Spring `@Around` thường cần thiết lập một marker tạm trong `MDC` rồi restore marker trước đó:

```java
String oldValue = MDC.get("operation");
MDC.put("operation", operationName);
try {
    return pjp.proceed();
} finally {
    if (oldValue == null) {
        MDC.remove("operation");
    } else {
        MDC.put("operation", oldValue);
    }
}
```

Đây là **mẫu minh họa** cần `org.slf4j.MDC` và logger implementation/SLF4J dependency thích hợp. Nó không nằm trong demo không phụ thuộc SLF4J ở mục 9. Không gọi `MDC.clear()` vô điều kiện nếu caller/framework đã đặt request ID hoặc trace fields khác.

Nếu bạn chỉ muốn restore **một key**, giữ đúng key cũ. Nếu advice chủ động thay toàn bộ MDC map, cân nhắc snapshot/restore toàn map bằng API của logging integration và đánh giá chi phí/context coupling.

### 6.3. SecurityContextHolder của Spring Security không thuộc ownership mặc định của aspect

Trong Servlet applications, Spring Security thường lưu authentication state trong `SecurityContextHolder` (mặc định dùng `ThreadLocal`) và xử lý lifecycle qua filter infrastructure. Một custom Spring service aspect **không nên** kết thúc mỗi call bằng:

```java
SecurityContextHolder.clearContext(); // Không làm bừa ở mọi service exit.
```

Code này là **anti-pattern minh họa** khi Spring Security filter/caller vẫn cần authenticated principal. Nó có thể xóa context giữa một request còn đang thực thi, khiến downstream authorization sai.

Chỉ can thiệp nếu component **thật sự sở hữu việc thiết lập context tạm** theo hợp đồng rõ ràng, và phải restore context trước đó đúng cách. Với task execution cross-thread, dùng các công cụ Spring Security `DelegatingSecurityContext...` phù hợp thay vì gán/clear context thủ công tùy tiện.

## 7. Không đóng tài nguyên Spring/JPA/JDBC do tầng khác quản lý

Spring transaction infrastructure có thể bind resources vào thread, quản lý connection/EntityManager và synchronization callbacks. Một `@Aspect` custom không được tự kết luận “method sắp kết thúc, tôi có quyền `Connection.close()`/`EntityManager.close()`”.

### 7.1. @Transactional và resource ownership

Nếu Spring service có:

```java
@Transactional
public void writeOrder(String id) {
    // JPA repository / JdbcTemplate work
}
```

Đoạn minh họa chỉ hợp lệ khi ứng dụng bật transaction management và có transaction manager/data source đúng. `@Transactional` service execution có thể tham gia **transaction của caller**, kéo dài qua nhiều service methods.

Nếu một custom aspect đóng connection/EntityManager trong `@After` của method giữa transaction, resource vẫn có thể đang được Spring cần cho các operations còn lại. Hậu quả có thể là premature close, rollback, lỗi lazy loading hoặc mất context.

**Quy tắc:** dùng `JdbcTemplate`, Spring data repositories, transaction-aware resource access hoặc Spring transaction APIs. Không lấy trực tiếp Spring-bound resource rồi đóng theo lifecycle của *một method advice* nếu resource thuộc lifecycle transaction.

### 7.2. Cleanup cần gắn với transaction completion?

Dùng Spring transaction synchronization:

```java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCompletion(int status) {
                // Giải phóng một resource do COMPONENT NÀY sở hữu
                // sau transaction completion tương ứng.
            }
        }
    );
}
```

Đây là đoạn **minh họa**, cần imports từ `org.springframework.transaction.support` và resource ownership rõ ràng. `afterCompletion` nhận status commit/rollback/unknown của transaction synchronization; nó có semantics khác `@After` trên một target method.

Nếu synchronization không active, ứng dụng phải quyết định policy riêng: cleanup ngay, không đăng ký, hoặc báo lỗi theo contract. Không gọi `registerSynchronization` vô điều kiện.

Khi cần sự kiện nghiệp vụ **sau commit**, có thể dùng `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` nếu phù hợp; nó cũng **không phải** thay thế chung cho cleanup local `AutoCloseable`.

### 7.3. Lỗi commit có thể xảy ra sau khi target return

Thứ tự custom aspect và transaction advisor ảnh hưởng việc `@After`/`finally` của bạn nằm trước hay sau commit. Target method return bình thường nhưng commit có thể thất bại ở interceptor bên ngoài. Đừng gán `cleanup-called` nghĩa là database committed.

Với test transaction, xác nhận actual DB state và thời điểm callback đúng transaction boundary; không suy chỉ từ thứ tự log.

## 8. @After và @Around khác nhau ở ownership, không chỉ cú pháp

So sánh hai patterns:

**Pattern A — `@After` giải phóng một state do infrastructure riêng quản lý:**

```java
@After("execution(* com.example.cleanup.TaskService.*(..))")
public void recordEnd(JoinPoint jp) {
    recorder.record(jp.getSignature().getName());
}
```

`@After` có thể hợp lý nếu chỉ ghi completion event vào một bean recorder thread-safe; không cần giữ resource handle được tạo ở đầu invocation. `recorder` là dependency minh họa, chưa có definition trong đoạn code này.

**Pattern B — `@Around` sở hữu scope theo invocation:**

```java
@Around("execution(* com.example.cleanup.TaskService.*(..))")
public Object withScope(ProceedingJoinPoint pjp) throws Throwable {
    String previous = MyContext.current();
    MyContext.set("within");
    try (AutoCloseable resource = myResourceFactory.open()) {
        return pjp.proceed();
    } finally {
        MyContext.restore(previous);
    }
}
```

**Đoạn B chỉ minh họa thiết kế**, `AutoCloseable.close()` có thể khai báo `throws Exception`, vì vậy chữ ký `throws Throwable` của advice cho phép propagate và Java try-with-resources dùng suppression. `MyContext`/`myResourceFactory` phải có implementation.

Pattern B có **scope owner rõ**: aspect tạo handle và giữ nó bằng local variable, bao đúng phạm vi target invocation. Với singleton Spring `@Aspect`, đừng dùng mutable instance fields như `currentHandle`/`currentRequestId` để lưu state per-call vì nhiều requests đồng thời có thể ghi đè nhau.

### 8.1. Không dùng @AfterReturning + @AfterThrowing thay try/finally một cách máy móc

Có thể viết hai advices riêng, nhưng dễ lặp cleanup code và có thể khác loại exception/type binding. Khi resource handle được tạo từ `@Before`, làm sao `@AfterReturning` và `@AfterThrowing` lấy đúng handle theo invocation/thread? Dùng singleton field là sai; chuyển qua ThreadLocal lại thêm một lifecycle phải quản lý.

Nếu logic là **setup → proceed → cleanup**, một `@Around` với lexical scope và `finally` thường gọn, an toàn và dễ test hơn.

## 9. Demo chạy được Java 17+: cleanup ở thành công, void, null và exception

Demo dưới đây thực sự chạy **Spring Framework AOP proxy** với một Spring-managed `@Aspect`. Aspect tạo **một lease (resource handle)** và **đặt một marker ThreadLocal** riêng cho từng invocation. Với cả normal return, `void`, `null` và target exception, aspect luôn đóng lease rồi **khôi phục marker của caller**.

Môi trường: Java 17+, Spring Framework **6.2.19**, AspectJ Weaver **1.9.25.1**, Gradle. Các resource objects được tạo trong demo là **resource giả chỉ ghi count**, không mở socket/JDBC connection; không dùng chúng để suy transaction resource cleanup.

### 9.1. Cây thư mục

```text
spring-aop-cleanup/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/cleanup/
    ├── AppConfig.java
    ├── CallContext.java
    ├── ProbeResources.java
    ├── CleanupAspect.java
    ├── TaskService.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-aop-cleanup'
```

**`build.gradle`**

```gradle
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
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.cleanup.Main'
}
```

Với Spring Boot production, để Boot BOM quản lý versions của Spring modules và AspectJ, không sao chép các versions của demo vào một project Boot major khác thiếu kiểm tra tương thích.

### 9.2. Một CallContext có restore đúng previous value

**`CallContext.java`**

```java
package com.example.cleanup;

public final class CallContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private CallContext() {}

    public static String current() {
        return CURRENT.get();
    }

    public static void set(String value) {
        if (value == null) {
            CURRENT.remove();
        } else {
            CURRENT.set(value);
        }
    }
}
```

Trong demo, `CallContext` đóng vai trò một **ThreadLocal do ứng dụng/aspect sở hữu**, hoàn toàn độc lập với `SecurityContextHolder` hay Spring transaction manager. `set(null)` gọi `remove()` để release reference ở thread khi không có parent value.

Main cố ý đặt `"caller"` trước các service calls; advice phải restore **`"caller"`**, không được gọi clear vô điều kiện vì trạng thái này do caller sở hữu.

### 9.3. Lease resource mở/đóng có đếm số lần

**`ProbeResources.java`**

```java
package com.example.cleanup;

import java.util.concurrent.atomic.AtomicInteger;

public class ProbeResources {
    private final AtomicInteger opened = new AtomicInteger();
    private final AtomicInteger closed = new AtomicInteger();

    public Lease open(String name) {
        opened.incrementAndGet();
        System.out.println("resource:open:" + name);
        return new Lease(name);
    }

    public int openedCount() {
        return opened.get();
    }

    public int closedCount() {
        return closed.get();
    }

    public final class Lease implements AutoCloseable {
        private final String name;
        private boolean done;

        private Lease(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            if (!done) {
                done = true;
                closed.incrementAndGet();
                System.out.println("resource:close:" + name);
            }
        }
    }
}
```

Mỗi `open()` tạo **Lease riêng**; không tái sử dụng một handle mutable chung trong aspect singleton. `close()` trong demo không khai báo/ném checked exception nên không làm che exception từ target.

`AtomicInteger` bảo vệ counters nếu nhiều threads cập nhật; boolean `done` thuộc từng handle và demo không chuyển cùng handle giữa threads. Nếu một resource thực sự được đóng concurrently từ nhiều threads, cần concurrency/idempotency contract riêng.

### 9.4. Spring target có bốn đường thoát

**`TaskService.java`**

```java
package com.example.cleanup;

public class TaskService {
    public String ok(String id) {
        System.out.println("target:ok:context=" + CallContext.current());
        return "ok:" + id;
    }

    public void refresh() {
        System.out.println("target:refresh:context=" + CallContext.current());
    }

    public String missing() {
        System.out.println("target:missing:context=" + CallContext.current());
        return null;
    }

    public String fail() {
        System.out.println("target:fail:context=" + CallContext.current());
        throw new IllegalStateException("boom");
    }
}
```

Các methods đều public/non-final; class không final. `fail()` đại diện exceptional exit; `missing()` đại diện **normal return của `null`**; `refresh()` đại diện normal completion của `void`.

### 9.5. Spring aspect dùng try-with-resources và finally

**`CleanupAspect.java`**

```java
package com.example.cleanup;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class CleanupAspect {
    private final ProbeResources resources;

    public CleanupAspect(ProbeResources resources) {
        this.resources = resources;
    }

    @Around("execution(public * com.example.cleanup.TaskService.*(..))")
    public Object around(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        String previous = CallContext.current();
        CallContext.set("scope:" + method);

        try {
            try (ProbeResources.Lease lease = resources.open(method)) {
                System.out.println(
                    "advice:enter:" + method
                    + ":context=" + CallContext.current()
                );
                return pjp.proceed();
            }
        } finally {
            CallContext.set(previous);
            System.out.println(
                "advice:restore:" + method
                + ":context=" + CallContext.current()
            );
        }
    }
}
```

**Thứ tự hoạt động chính xác:**

1. Capture `previous` **trước** khi thay đổi current marker.
2. Set marker tạm cho invocation hiện tại.
3. `resources.open(method)` tạo Lease.
4. Target được gọi **một lần** qua `pjp.proceed()`.
5. Nếu target return hoặc throw, Java `try-with-resources` gọi `Lease.close()` (trong ví dụ chỉ tăng count và in).
6. `finally` của wrapper **luôn khôi phục previous** khi control flow thoát khỏi phần try, kể cả nếu `open()` hoặc `close()` throw.
7. Advice không bắt rồi biến lỗi thành `null`; nó để exception gốc truyền về caller theo Java propagation rules.
8. Nếu `close()` trong một resource thực tế throw, phải xét suppression/masking behavior; `Lease.close()` trong demo cố ý no-throw để quan sát rõ 4 outcomes.

**Chi tiết thiết kế quan trọng:** đoạn cleanup trong `finally` vẫn có `System.out.println`. Trong app production, ngay cả logging cũng nên được coi là side effect có khả năng lỗi theo môi trường; nếu bảo toàn exception/result là contract bắt buộc, cần thiết kế cleanup/error logging sao cho failure policy tường minh. `finally` chỉ bảo đảm control flow tới cleanup trong các đường Java bình thường, không biến mọi side effect thành infallible.

### 9.6. Đăng ký Spring beans và bật AOP support

**`AppConfig.java`**

```java
package com.example.cleanup;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    ProbeResources probeResources() {
        return new ProbeResources();
    }

    @Bean
    CleanupAspect cleanupAspect(ProbeResources resources) {
        return new CleanupAspect(resources);
    }

    @Bean
    TaskService taskService() {
        return new TaskService();
    }
}
```

`@Aspect` không tự là `@Component`; `@Bean` đăng ký aspect vào Spring container. Target `TaskService` cũng là Spring-managed bean. `@EnableAspectJAutoProxy(proxyTargetClass=true)` kích hoạt Spring AOP class-based proxy, nên `getBean(TaskService.class)` có thể trả proxy của concrete class.

Không cần `@ComponentScan`, vì đã khai báo cả ba beans. Spring AOP dùng AspectJ annotations/pointcut parser nhưng interception vẫn là proxy, không cần `-javaagent`.

### 9.7. Main chạy bốn trường hợp và kiểm tra resource count

**`Main.java`**

```java
package com.example.cleanup;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            TaskService service = context.getBean(TaskService.class);
            ProbeResources resources = context.getBean(ProbeResources.class);

            CallContext.set("caller");

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("before=" + CallContext.current());

            System.out.println("result=" + service.ok("A"));
            System.out.println("afterOk=" + CallContext.current());

            service.refresh();
            System.out.println("afterRefresh=" + CallContext.current());

            System.out.println(
                "missingIsNull=" + (service.missing() == null)
            );
            System.out.println("afterMissing=" + CallContext.current());

            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
            System.out.println("afterFail=" + CallContext.current());

            System.out.println("opened=" + resources.openedCount());
            System.out.println("closed=" + resources.closedCount());

            CallContext.set(null);
            System.out.println("afterClear=" + CallContext.current());
        }
    }
}
```

Ở root project, với Java 17+ và Gradle có sẵn:

```bash
gradle run --quiet
```

Với Gradle Wrapper: `./gradlew run --quiet` (Linux/macOS), `gradlew.bat run --quiet` (Windows).

**Stdout do chương trình in, theo đúng thứ tự** (không tính thông báo ngoài của JVM/Gradle/Spring):

```text
proxy=true
before=caller
resource:open:ok
advice:enter:ok:context=scope:ok
target:ok:context=scope:ok
resource:close:ok
advice:restore:ok:context=caller
result=ok:A
afterOk=caller
resource:open:refresh
advice:enter:refresh:context=scope:refresh
target:refresh:context=scope:refresh
resource:close:refresh
advice:restore:refresh:context=caller
afterRefresh=caller
resource:open:missing
advice:enter:missing:context=scope:missing
target:missing:context=scope:missing
resource:close:missing
advice:restore:missing:context=caller
missingIsNull=true
afterMissing=caller
resource:open:fail
advice:enter:fail:context=scope:fail
target:fail:context=scope:fail
resource:close:fail
advice:restore:fail:context=caller
caught=boom
afterFail=caller
opened=4
closed=4
afterClear=null
```

### 9.8. Bốn outcomes, cùng một cleanup invariant

| Method call | Target outcome | `Lease.close()` được gọi? | `CallContext` sau call | Caller nhận |
| --- | --- | --- | --- | --- |
| `ok("A")` | Normal `String` | Có | `caller` | `ok:A` |
| `refresh()` | Normal `void` | Có | `caller` | Không có value |
| `missing()` | Normal `null` | Có | `caller` | `null` |
| `fail()` | Throw `IllegalStateException` | Có | `caller` | Exception `boom` |

Hai invariants được demo chứng minh theo thiết kế:

- **`opened=4` và `closed=4`**: một lease per intercepted external invocation, đóng đúng một lần mỗi handle.
- **`afterOk=afterRefresh=afterMissing=afterFail=caller`**: nested aspect scope không xóa context của caller. Sau cùng, chính caller dọn `CallContext` mà caller đã đặt, nên `afterClear=null`.

Đừng nhầm **số lần close** với số transaction commits. Lease của demo là resource ứng dụng tự tạo, không phải Spring transaction-managed connection.

## 10. Case nâng cao: nested Spring bean calls và context scopes

Khi một service gọi sang **một Spring collaborator bean khác qua proxy**, có thể tồn tại nhiều nested aspect scopes:

```text
Request scope = req-42
  Proxy A: @Around sets service-A
    Service A calls injected proxy B
      Proxy B: @Around sets service-B
      Service B target sees service-B
      Proxy B finally restores service-A
    Service A target sees service-A again
  Proxy A finally restores req-42
Request scope still req-42
```

Muốn tính đúng, mỗi around advice giữ **`previous` riêng trong local variable** và restore trong `finally`. Không dùng field `previousContext` trên singleton `@Aspect` vì concurrent calls sẽ ghi đè nhau.

Nếu Service A gọi `this.someMethod()` nội bộ, invocation đó **không quay qua Spring AOP proxy**, nên không có scope mới của advice nhắm riêng `someMethod`; đây là giới hạn Spring proxy, không phải lỗi `finally`.

### 10.1. Trường hợp context ban đầu là null

Nếu `CallContext.current()` trả `null` trước khi advice vào:

```java
String previous = CallContext.current(); // null
CallContext.set("scope:work");
try {
    return pjp.proceed();
} finally {
    CallContext.set(previous); // set(null) thực thi ThreadLocal.remove()
}
```

Sau call `ThreadLocal` lại trống. Đây là behavior đúng đối với một invocation không có parent context.

## 11. Tài nguyên đóng lỗi: bảo toàn lỗi gốc và xác định failure policy

**Mọi lời khuyên “luôn đóng trong finally” đều phải xét việc đóng có thể thất bại.**

### 11.1. finally close thủ công có thể che target exception

```java
try {
    return pjp.proceed();  // Ném ServiceException
} finally {
    resource.close();      // Lại ném IOException
}
```

Nếu `close()` ném trên đường unwind của `finally`, Java có thể khiến exception cleanup thay exception service ở caller. Với audit/metric resource không critical, behavior ấy thường không mong muốn.

### 11.2. try-with-resources quản lý suppressed exceptions

```java
try (MyResource resource = acquire()) {
    return pjp.proceed();
}
```

Nếu method body ném A và `close()` ném B, Java `try-with-resources` đặt B vào `A.getSuppressed()` trong trường hợp thông thường. Nhờ đó exception chính còn lại để caller xử lý.

Nhưng không biến `try-with-resources` thành câu “cleanup không bao giờ làm target call thất bại”: nếu target return bình thường nhưng close ném exception, close failure vẫn có thể trở thành lỗi caller nhận.

### 11.3. Suppress lỗi cleanup có kiểm soát

Đối với cleanup **best-effort**:

```java
Throwable primary = null;
try {
    return pjp.proceed();
} catch (Throwable error) {
    primary = error;
    throw error;
} finally {
    try {
        bestEffortResource.close();
    } catch (Exception cleanupFailure) {
        if (primary != null && primary != cleanupFailure) {
            primary.addSuppressed(cleanupFailure);
        } else {
            // Chọn rõ policy khi target đã return bình thường.
            // Ví dụ ghi telemetry qua kênh an toàn không ném lỗi.
        }
    }
}
```

Đây là **đoạn minh họa** với `bestEffortResource` đã được tạo ở scope ngoài. Cần quyết định policy cho error từ logger/telemetry và từ `Error` của cleanup. Không lạm dụng `catch(Throwable)` để nuốt các lỗi fatal; nếu resource release là critical, propagate và giữ cause/suppressed information.

### 11.4. Đóng tài nguyên của ai?

| Resource | Chủ sở hữu thường gặp | Hành động của custom aspect |
| --- | --- | --- |
| Lease/temporary handle được aspect tạo riêng per invocation | Chính aspect | Đóng trong scope của advice. |
| File/InputStream/socket do component custom mở | Component mở | Đóng đúng chỗ, chọn lifecycle theo use case. |
| JDBC connection do `JdbcTemplate`/transaction manager quản lý | Spring JDBC/Transaction infrastructure | **Không** đóng thủ công khi method advice thoát. |
| JPA EntityManager của transaction | Persistence/transaction infrastructure | **Không** gọi `close()` tùy tiện trong custom aspect. |
| SecurityContext trong Servlet request | Spring Security filter/security framework | Không `clearContext()` vô điều kiện trong service advice. |
| MDC key do aspect đặt tạm | Aspect | Restore key trước đó, không xóa các keys khác. |
| Reactor Context của reactive chain | Reactor subscription/context operators | Quản lý bằng reactive lifecycle, không dùng một ThreadLocal context giả định xuyên mọi signals. |

## 12. Future, @Async và reactive: dọn đúng vòng đời thực

### 12.1. CompletableFuture

Giả sử service:

```java
public CompletableFuture<String> loadAsync(String id) {
    return remoteCallAsync(id);
}
```

Một Spring `@Around` đồng bộ có thể thấy `pjp.proceed()` **return `CompletableFuture` rất nhanh**. `finally` chạy ngay sau khi trả wrapper khỏi target invocation, **trước khi asynchronous computation thật sự hoàn tất**.

Nếu resource chỉ cần trong lúc **tạo/schedule** future, cleanup trong `finally` có thể đúng. Nếu async task vẫn dùng resource đó, đóng ngay là **quá sớm**.

Có thể gắn completion callback vào future khi hợp đồng cho phép:

```java
CompletableFuture<String> future = serviceOperation();
future.whenComplete((value, error) -> {
    // Cleanup resource được sở hữu cho đến khi future kết thúc.
});
```

Đây là đoạn minh họa. Callback có thể chạy trên thread khác hoặc ngay khi completed; resource ownership cần thread safety, cancellation semantics và error policy. Với `@Async` của Spring, async proxy interceptors có thể chuyển phần target/advice sang executor thread; kiểm tra advisor ordering và execution thread trước khi quyết định context/cleanup scope.

**Không lấy `ThreadLocal` của caller và kỳ vọng nó tự xuất hiện ở worker thread**. Khi cần truyền context, sử dụng Spring TaskDecorator, phù hợp với executor và context cụ thể; với SecurityContext dùng công cụ Spring Security hỗ trợ context propagation.

### 12.2. Mono / Flux

Một method trả reactive publisher:

```java
public Mono<String> findReactive(String id) {
    return repository.find(id);
}
```

Đoạn minh họa cần Reactor/Spring reactive dependencies và repository thật. Với lazy publishers, `@Around` đồng bộ chỉ bọc **thời điểm trả publisher object**, không tự bọc subscription, cancellation hoặc terminal signals.

Khi resource thuộc vòng đời subscription, dùng Reactor `using`/`usingWhen` hoặc `doFinally` với `SignalType` thích hợp; các APIs này xử lý các nhánh complete/error/cancel theo lifecycle reactive. Không dùng `try/finally` đồng bộ để đóng connection mà publisher chỉ dùng **sau** khi subscribe.

### 12.3. Khác biệt giữa exception đồng bộ và exception async

Nếu `pjp.proceed()` throw ngay, `catch/finally` của `@Around` thấy exception đồng bộ. Nếu nó trả `Future` bình thường rồi future complete exceptionally về sau, advice sync **không nhận lần exceptional exit đó** qua `@AfterThrowing` trên method return wrapper. Muốn đo async failure, quan sát future completion hoặc reactive error signal theo đúng API.

## 13. Spring Boot: cấu hình cần đủ nhưng không tự can thiệp lifecycle framework

Trong Spring Boot có AOP auto-configuration phù hợp, bạn có thể đăng ký:

```java
@Aspect
@Component
public class CleanupAspect {
    @Around("execution(public * com.example.app..*Service.*(..))")
    public Object cleanup(ProceedingJoinPoint pjp) throws Throwable {
        // Capture context, acquire owned lease, proceed, restore in finally.
        return pjp.proceed();
    }
}
```

Đây là **khung minh họa**, chưa có logic cleanup; các package/imports cần bổ sung. `@Aspect` **không tự** là Spring bean, vì vậy `@Component` cần nằm trong component scan hoặc aspect cần được trả từ `@Bean`.

Một số lưu ý Spring-specific:

- Spring Framework Java configuration có `@EnableAspectJAutoProxy`; Boot thường tự bật AOP khi có starter thích hợp.
- Với JDK proxy, method được advice phải expose qua interface; với CGLIB, class/method `final` không được override. `private` method không phải Spring AOP proxy entry.
- `this.innerMethod()` từ target bypass proxy; Spring không tạo additional cleanup scope cho nó.
- Aspect bean thường singleton; giữ invocation state trong **locals** chứ không trong shared mutable fields.
- `@Order` với transaction/cache/security/async advisors có thể khiến cleanup scope nằm ngoài hoặc trong features ấy. Kiểm tra actual proxy/advisor chain.
- Không gọi `TransactionSynchronizationManager.clear()`/`SecurityContextHolder.clearContext()` như một “universal cleanup” từ custom business aspect.

Dependencies theo major version của Spring Boot (chọn **một** nếu Boot dependency management tương ứng):

```gradle
// Spring Boot 3.x
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

```gradle
// Spring Boot 4.x
implementation 'org.springframework.boot:spring-boot-starter-aspectj'
```

Không thêm đồng thời cả hai chỉ để hy vọng tăng khả năng interception. Spring AOP proxy và Spring transaction/request security lifecycle vẫn cần được hiểu tách biệt.

## 14. Test Spring AOP cleanup đúng cách

### 14.1. Vì sao unit test gọi trực tiếp aspect không đủ?

`new CleanupAspect(resources).around(fakeProceedingJoinPoint)` có thể kiểm tra logic Java của advice nhưng **không chứng minh Spring đã đăng ký @Aspect bean, chọn method execution, tạo proxy hoặc nối interceptor chain**.

Integration test phải lấy `TaskService` **từ ApplicationContext**, gọi qua Spring proxy, kiểm tra `AopUtils.isAopProxy(service)` và assert state/resources sau từng invocation.

### 14.2. Các invariant cần assert

Với demo:

1. `service.ok("A")` trả đúng `"ok:A"`; lease đóng, context restore.
2. `service.refresh()` hoàn tất; lease đóng, context restore dù `void`.
3. `service.missing()` trả đúng `null`; lease đóng, context restore.
4. `service.fail()` vẫn ném `IllegalStateException("boom")`; lease đóng, context restore.
5. `openedCount == closedCount == 4` sau bốn external proxy calls.
6. Caller `"caller"` còn nguyên sau mỗi method call, không bị `finally` xóa nhầm.
7. Nếu caller ban đầu `null`, sau một intercepted call context lại `null`.
8. Một raw `new TaskService()` không kích hoạt Spring advice, nên không làm counter resource của Spring aspect tăng.
9. Nếu thêm nested collaborator bean/proxy, inner scope restore outer scope rồi outer restore caller.
10. Nếu một outer aspect short-circuit không `proceed()`, inner cleanup không được gọi vì inner không sở hữu resource nào ở invocation đó.

### 14.3. Test assertion ví dụ

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    TaskService service = context.getBean(TaskService.class);
    ProbeResources resources = context.getBean(ProbeResources.class);
    CallContext.set("parent");

    if (!"ok:X".equals(service.ok("X"))) {
        throw new AssertionError("Result changed");
    }
    if (!"parent".equals(CallContext.current())) {
        throw new AssertionError("Parent context lost on normal return");
    }

    service.refresh();
    if (service.missing() != null) {
        throw new AssertionError("Null return changed");
    }

    try {
        service.fail();
        throw new AssertionError("Expected IllegalStateException");
    } catch (IllegalStateException expected) {
        if (!"boom".equals(expected.getMessage())) {
            throw new AssertionError("Wrong original exception", expected);
        }
    }

    if (!"parent".equals(CallContext.current())) {
        throw new AssertionError("Parent context lost on exception");
    }
    if (resources.openedCount() != 4 || resources.closedCount() != 4) {
        throw new AssertionError("Resource lease count mismatch");
    }

    CallContext.set(null);
}
```

Đây là **đoạn test minh họa** sử dụng classes trong demo, cần import `AnnotationConfigApplicationContext` và đặt trong Java test/main phù hợp; nó khởi tạo context riêng, **không ghép vào `Main`** nếu muốn giữ stdout mục 9.7. Với JUnit có thể dùng `assertThrows`/`assertEquals` cùng `@SpringJUnitConfig` hoặc `@SpringBootTest`.

### 14.4. Failure injection nên kiểm tra thêm

- Resource acquisition throw: context vẫn restore trong outer `finally`.
- Resource close throw sau target normal return: exception close được xử lý/propagate theo policy đã định.
- Resource close throw khi target đang throw: `try-with-resources` giữ error gốc và đánh dấu close exception suppressed.
- Logger/metric callback throw: không tự ý làm mất target exception/outcome nếu telemetry best-effort.
- Two concurrent requests: không chia sẻ mutable resource handles hoặc current context field trong singleton aspect.
- Async task/thread swap: cleanup thuộc đúng thread và đúng lifecycle thay vì dùng synchronous assertion giả.
- Transaction participation: không đóng Spring-managed resource khi method chỉ là một bước trong transaction rộng hơn.

## 15. Những lỗi phổ biến và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Aspect cleanup không chạy khi service method kết thúc | Target không qua Spring proxy, pointcut không match, aspect chưa là bean hoặc outer short-circuit | Kiểm tra `AopUtils.isAopProxy`, `@EnableAspectJAutoProxy`, bean registry và caller path. |
| Cleanup chỉ chạy trên success | Đặt trong `@AfterReturning` hoặc sau `proceed()` mà không có `finally` | Chuyển sang `@After` hoặc `@Around` + `finally` đúng ownership. |
| Context request biến mất sau nested service call | Inner aspect gọi `remove()/clear()` vô điều kiện | Capture previous và restore trong `finally`. |
| Thread pool giữ marker của request trước | Thiếu `finally`/`ThreadLocal.remove()` lúc không có parent | Tạo scope per invocation; test thread reuse. |
| Resource close khi target exception bị bỏ qua | Code close chỉ nằm sau `return pjp.proceed()` | Dùng `try-with-resources`/`finally`. |
| Caller nhận cleanup exception thay vì lỗi gốc | `finally close()` ném trên đường exceptional exit | Dùng suppression policy, không throw từ best-effort telemetry. |
| Dao/JPA lỗi sau một service call | Aspect đóng connection/EntityManager do Spring transaction quản lý | Bỏ manual close, dùng Spring transaction-managed APIs. |
| `@After` in log nhưng DB chưa commit | Advice nằm trước transaction completion trong advisor chain | Inspect order và dùng transaction synchronization khi cần afterCompletion. |
| Security principal bị mất giữa request | Custom aspect xóa `SecurityContextHolder` | Để Spring Security filter quản lý; chỉ restore context mà component tự sở hữu. |
| Future lỗi sau khi aspect báo success | Aspect chỉ thấy future wrapper normal return | Quan sát future completion. |
| Mono/Flux dùng resource đã đóng | Aspect sync finally đóng trước khi subscribe | Sử dụng Reactor resource lifecycle `using/usingWhen/doFinally`. |
| Nested proxy scopes chen lẫn sai | Lưu previous context ở field singleton aspect | Dùng local per-invocation state và restore theo LIFO. |
| Cùng một resource bị đóng hai lần | Nhiều advice cùng nhận là owner hoặc cleanup không idempotent | Xác định ownership một nơi, quản lý close contract. |
| @After không chạy khi @Around outer trả sớm | Inner advice không hề được đi vào | Cleanup phải thuộc layer đã acquire resource; không mong downstream finally chạy. |
| `@After` chạy nhưng ngoại lệ business bị đổi | Cleanup code tự throw hoặc swallow trong advice khác | Kiểm tra exception primary/suppressed và contract. |

## 16. Quy trình thiết kế thực tế

**Bước 1 — Xác định resource/context thuộc về ai.** Custom aspect có thực sự mở/đặt nó không? Nếu resource do transaction/security/Servlet/Reactor infrastructure sở hữu, chọn lifecycle API tương ứng, không close/clear thủ công.

**Bước 2 — Chọn đúng scope.** Mọi cleanup cần gắn với một per-invocation handle hoặc local snapshot: `previous ThreadLocal`, `Lease`, span scope, trace field key.

**Bước 3 — Chọn advice ít quyền nhất.** `@After` cho completion observation; `@Around` khi cần setup/teardown lexical scope và giữ resource handle. Đừng dùng `@Around` chỉ để in log sau method nếu `@After` đủ.

**Bước 4 — Chuẩn bị trước khi proceed.** Capture previous context rồi set temporary state; acquire resources trong một `try` được bảo vệ để acquisition failure cũng restore mọi state đã thay.

**Bước 5 — Giữ contract.** `return pjp.proceed()` trong try, không tự đổi return type/reference hoặc nuốt exception trừ khi API/policy cho phép. Chạy `proceed()` một lần nếu không có retry design.

**Bước 6 — Cleanup đáng tin.** Với tài nguyên owned, `try-with-resources` hoặc `finally`; restore parent context trong outer `finally`. Xác định cleanup failure policy, dùng suppressed exceptions để giữ root cause.

**Bước 7 — Kiểm tra nested/concurrent calls.** Không dùng fields singleton aspect để giữ per-call mutable state. Với thread pool, dọn `ThreadLocal` khi previous null; với nested scopes, restore previous thay vì clear global.

**Bước 8 — Xem lifecycle thực.** `@Async`/future/reactive subscription, transaction completion và HTTP request/security scopes có thể dài hơn một method execution. Đặt cleanup vào đúng hook.

**Bước 9 — Khóa bằng integration tests.** Chạy qua Spring proxy thật, test return/void/null/exception, resource counts, parent context restoration, cleanup failure injection, self-call và worker-thread behaviors nếu liên quan.

## 17. Checklist trước khi đưa vào production

- [ ] Aspect có `@Aspect` và được Spring đăng ký làm bean, target là Spring-managed bean?
- [ ] Spring AOP được bật và caller đi qua đúng JDK/CGLIB proxy?
- [ ] Pointcut match đúng service method, không tưởng `this.method()` cũng được advice?
- [ ] Đã phân biệt `@After` finally với `@AfterReturning` success-only và `@AfterThrowing` exception-only?
- [ ] Tài nguyên cần cleanup có thật sự **do aspect sở hữu**, không phải transaction/security infrastructure?
- [ ] Nếu advice khởi tạo resource, đã dùng local handle và `try-with-resources`/`finally`?
- [ ] Nếu thay `ThreadLocal`/MDC, có snapshot previous và restore trong `finally`?
- [ ] Nếu previous null, code `remove()` thay vì giữ key/thread reference?
- [ ] Nested invocations restore context LIFO, không `clear()` parent context?
- [ ] Không lưu per-invocation `Resource`/`previousContext` vào mutable field của singleton aspect?
- [ ] Cleanup failure có policy rõ; không làm mất root exception hoặc biến normal return thành failure ngoài contract?
- [ ] Nếu resource close có thể throw, đã xét `getSuppressed()`/try-with-resources?
- [ ] Không đóng JDBC/JPA Spring-managed connections/entity managers trong custom `@After`?
- [ ] Không xóa `SecurityContextHolder` hoặc transaction synchronization global vô điều kiện?
- [ ] Với future/`@Async`/Reactor, cleanup gắn đúng completion/terminal lifecycle?
- [ ] Có integration tests Spring proxy thật cho success, `void`, `null`, exception, nested và concurrency?
- [ ] Audit cleanup log không được hiểu là transaction commit hoặc async business success?
- [ ] Các outer aspects/cache/security advisors có thể short-circuit đã được xét khi đặt cleanup ownership?

**Ghi nhớ:** Trong Spring AOP, **`@After` là after-finally của matched method execution**, còn **`@Around` + Java `try/finally`/`try-with-resources`** là cách rõ ràng nhất khi chính aspect mở tài nguyên hoặc tạm đặt ngữ cảnh. Dọn **đúng cái mình sở hữu** và **khôi phục trạng thái caller**, không xóa/đóng resource do transaction, security hay async/reactive lifecycle khác quản lý. Hoàn tất method không nhất thiết là hoàn tất transaction hoặc asynchronous computation.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Declaring Advice: After (Finally) Advice và Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Proxying Mechanisms và self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Resource Synchronization with Transactions](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Security — SecurityContextHolder và Servlet authentication architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Java — try-with-resources và suppressed exceptions](https://docs.oracle.com/javase/tutorial/essential/exceptions/tryResourceClose.html)
