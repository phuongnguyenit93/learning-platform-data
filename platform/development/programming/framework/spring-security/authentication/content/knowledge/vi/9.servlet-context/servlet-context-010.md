# Truyền danh tính sang tác vụ nền bằng các lớp DelegatingSecurityContext

> **Phạm vi:** Spring Security Authentication trên **Servlet stack** (Spring MVC, Java 17+). Chủ đề là cách truyền `SecurityContext` từ thread đang xử lý request sang thread của `Runnable`, `Callable`, `Executor`, `ExecutorService` và tác vụ `@Async` bằng họ lớp `DelegatingSecurityContext...`. Bài giải thích rõ **thời điểm capture context**, quyền của tác vụ, cleanup/restoration trên thread pool, sự khác nhau với session persistence và các giới hạn an toàn. Có project Gradle + Java 17 chạy độc lập bằng **Spring Security Core 6.5.11**, với stdout xác định và tình huống task lỗi.

## 1. Vấn đề: HTTP request có người dùng, background thread lại không thấy

Trong một request đã đăng nhập, Spring Security thường cho phép:

```java
Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();

String username = authentication.getName();
```

Đây là **snippet trong một request đã xác thực**, không phải chương trình hoàn chỉnh. Ở Servlet stack, `SecurityContextHolder` mặc định dùng `ThreadLocal` để lưu `SecurityContext` của **thread hiện tại**. Điều này có ích cho controller, service và những phương thức chạy trong cùng thread: không phải truyền một tham số `Authentication` qua mọi hàm.

Tuy nhiên, một tác vụ nền thường chạy trên **thread khác**:

```java
// Anti-pattern: đừng mặc định task này thấy cùng danh tính với request.
executor.execute(() -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    // current có thể null, hoặc là danh tính không mong đợi nếu rò rỉ thread.
});
```

Nếu một service được bảo vệ bằng `@PreAuthorize`, thiếu context có thể khiến tác vụ bị từ chối. Nguy hiểm hơn, nếu lập trình viên tự gắn `Authentication` vào thread pool mà **không dọn sạch**, thread được tái sử dụng có thể mang danh tính request trước sang request sau.

Spring Security cung cấp các lớp **`DelegatingSecurityContext...`** để giải quyết việc **đưa context thích hợp vào thread thực thi, chạy công việc, rồi khôi phục/dọn trạng thái**. Đây là **context propagation**, không phải việc xác minh lại mật khẩu, tạo session hay cấp thêm quyền.

### Mục tiêu học tập

Sau bài học, bạn cần:

1. Giải thích vì sao `SecurityContextHolder` mặc định không tự đi từ request thread sang thread pool.
2. Phân biệt `SecurityContext`, `Authentication`, `SecurityContextHolder` và `SecurityContextRepository`.
3. Chọn đúng `DelegatingSecurityContextRunnable`, `Callable`, `Executor`, `ExecutorService` hoặc `AsyncTaskExecutor`.
4. Biết constructor **có truyền `SecurityContext`** thường áp dụng **một context cố định**, còn constructor không truyền context của executor thường **lấy context lúc submit task**.
5. Nhận biết khác biệt giữa **lúc tạo wrapper**, **lúc submit task** và **lúc worker thực thi**.
6. Đảm bảo cleanup/restoration khi task thành công, lỗi hoặc thread pool tái sử dụng worker.
7. Tránh đưa danh tính request vào job hàng giờ, job chạy lại sau logout hoặc hệ thống queue phân tán.
8. Kiểm thử task nhìn thấy đúng user và task sau không bị rò rỉ authority.

## 2. Bốn khái niệm không nên nhập làm một

| Thành phần | Vai trò | Không đảm nhận |
| --- | --- | --- |
| `Authentication` | Principal, trạng thái authenticated, authorities của một lần xác thực | Không tự đi sang thread khác |
| `SecurityContext` | Chứa `Authentication` của một execution context | Không tự lưu vào HTTP session |
| `SecurityContextHolder` | Giữ/đọc context gắn với thread hoặc strategy đã chọn | Không tự tạo quyền hoặc xác minh password |
| `SecurityContextRepository` | Lưu/khôi phục context qua scope phù hợp như HTTP session/request | Không tự truyền context cho `ExecutorService` |

**Dòng đời trong Servlet request** có thể hình dung:

```text
Request thread T1:
SecurityContextHolderFilter
    ↓ load SecurityContext từ repository
Controller / service thấy Authentication của "mai"
    ↓ submit công việc sang thread pool
Request hoàn tất
    ↓ holder của T1 được framework dọn

Worker thread T2:
    nếu chỉ là Runnable thường -> không tự có context của "mai"
    nếu dùng DelegatingSecurityContext -> đặt context đúng cho task
    ↓ chạy công việc
    ↓ finally: cleanup / restore context cũ
```

**Quan trọng:** việc `SecurityContextRepository.saveContext(...)` lưu đăng nhập cho **request HTTP kế tiếp** khác với `DelegatingSecurityContext...` chuyển context sang **thread đang thực thi một task**. Một cơ chế không thay thế cơ chế kia. Nếu controller tự đăng nhập nhưng chưa lưu session, wrapper có thể cho worker thấy user trong request hiện tại; điều đó **không chứng minh** session đã được lưu cho browser.

### ThreadLocal mặc định, InheritableThreadLocal và Global

`SecurityContextHolder` hỗ trợ nhiều strategy, nhưng với Servlet application phổ biến, mặc định `MODE_THREADLOCAL` là lựa chọn thích hợp. Hai mode khác cần cẩn trọng:

- `MODE_INHERITABLETHREADLOCAL`: thread con có thể thừa hưởng giá trị lúc thread được tạo, **không đồng nghĩa** lấy user mới mỗi lần thread pool nhận task. Một pool worker được tạo dưới request Alice có thể được tái sử dụng cho Bob; thừa hưởng context kiểu này dễ gây nhầm danh tính.
- `MODE_GLOBAL`: chia sẻ một context ở phạm vi JVM; không thích hợp để đại diện cho mỗi người dùng của ứng dụng web nhiều request đồng thời.

**Không bật inheritable/global chỉ để sửa một lỗi `@Async` không thấy principal.** Dùng wrapper theo task, đảm bảo context được đặt và dọn đúng lifecycle.

## 3. Họ lớp DelegatingSecurityContext... có nhiệm vụ gì?

Các lớp dưới đây thuộc Spring Security 6.5; package tùy loại:

| Lớp | API được bọc | Dùng khi |
| --- | --- | --- |
| `DelegatingSecurityContextRunnable` | `Runnable` | Một task `void run()` riêng lẻ |
| `DelegatingSecurityContextCallable<V>` | `Callable<V>` | Task cần kết quả hoặc checked exception |
| `DelegatingSecurityContextExecutor` | `Executor` | Chỗ gọi chỉ sử dụng `execute(Runnable)` |
| `DelegatingSecurityContextExecutorService` | `ExecutorService` | Cần `submit`, `Future`, `invokeAll`, shutdown… |
| `DelegatingSecurityContextScheduledExecutorService` | `ScheduledExecutorService` | Task định kỳ hoặc chạy sau delay, với chính sách identity rõ ràng |
| `DelegatingSecurityContextTaskExecutor` | Spring `TaskExecutor` | Dùng abstractions `execute` của Spring Task |
| `DelegatingSecurityContextAsyncTaskExecutor` | Spring `AsyncTaskExecutor` | Dùng `@Async`, submit với `Future`/`CompletableFuture` |
| `DelegatingSecurityContextTaskScheduler` / `SchedulingTaskExecutor` | Spring Task scheduling | Khi dùng scheduler hoặc những adapter tương ứng của Spring |

Các lớp `Runnable`, `Callable`, `Executor` và `ExecutorService` thuộc `org.springframework.security.concurrent`. `DelegatingSecurityContextTaskExecutor` và `DelegatingSecurityContextAsyncTaskExecutor` thuộc `org.springframework.security.task`. Không import nhầm package hoặc nghĩ đây là API chung của `java.util.concurrent`.

### Quy tắc chung

Các wrapper:

1. Lấy `SecurityContext` theo constructor/chính sách được chọn.
2. Đặt context phù hợp vào `SecurityContextHolder` của worker khi task chạy.
3. Thực thi delegate `Runnable.run()` hoặc `Callable.call()`.
4. Dọn hoặc khôi phục context có trước đó trong `finally` theo implementation/version, kể cả khi delegate ném exception.
5. Không tự quyết định user có quyền chạy job hay không; authorization phải được thiết kế độc lập.

Trong tài liệu Spring Security có mô hình tối giản:

```java
try {
    SecurityContextHolder.setContext(securityContext);
    delegate.run();
} finally {
    SecurityContextHolder.clearContext();
}
```

Đây là **mô hình ý tưởng**, không phải code cần tự chép thay cho thư viện. Javadoc của các lớp mới hơn lưu ý rằng nếu worker đã có context trước task thì context đó có thể được **khôi phục**, không chỉ luôn xóa trắng. Điều cần bảo đảm là wrapper không để **danh tính của task vừa chạy** bị rò rỉ vào task độc lập sau đó.

## 4. DelegatingSecurityContextRunnable: một task đơn lẻ

### 4.1. Constructor lấy context hiện tại

```java
Runnable businessAction = () -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    System.out.println(auth == null ? "NONE" : auth.getName());
};

// Wrap tại lúc còn SecurityContext phù hợp.
Runnable wrapped =
        new DelegatingSecurityContextRunnable(businessAction);

new Thread(wrapped, "background-once").start();
```

Đây là **snippet**: thread creation/cleanup, lifecycle và test đầy đủ được trình bày ở ví dụ runnable. Constructor `new DelegatingSecurityContextRunnable(Runnable)` dùng context trong `SecurityContextHolder` **tại thời điểm tạo wrapper**.

Cần phân biệt:

```text
t0 - request của Alice có SecurityContext(Alice)
t1 - tạo DelegatingSecurityContextRunnable(delegate)
     → wrapper lấy context của Alice
t2 - request thread đổi/xóa SecurityContextHolder
t3 - worker mới bắt đầu chạy wrapper
     → worker sử dụng context đã gắn ở t1
t4 - wrapper kết thúc → cleanup/restore
```

Không nên tạo wrapper rất sớm dưới anonymous context rồi mang dùng sau khi đã login; nó có thể capture sai trạng thái. Cũng không nên giữ wrapper của Alice như một **singleton** để nhiều user submit cùng một `Runnable` về sau.

### 4.2. Constructor nhận SecurityContext rõ ràng

```java
SecurityContext captured = SecurityContextHolder.getContext();

Runnable wrapped = new DelegatingSecurityContextRunnable(
        () -> securedService.performOperation(),
        captured);
```

Đây là **snippet phụ thuộc `securedService`**. Truyền context tường minh hữu ích khi bạn cần xác định chính xác quyền dùng cho task, nhưng đồng nghĩa **trách nhiệm chọn đúng context và vòng đời** thuộc về ứng dụng.

**Chú ý tham chiếu object:** wrapper nhận một `SecurityContext` object, không phải lời hứa rằng mọi field của principal/authorities được deep-copy bất biến. Nếu cùng object được code khác sửa trong lúc task nằm ở queue, kết quả có thể khác mong đợi. Đừng mutate context shared; khi cần snapshot rõ ràng, tạo context mới chỉ chứa thông tin cần thiết hoặc lưu identity ID rồi revalidate theo chính sách.

### 4.3. Trường hợp không cần wrapper

Nếu mọi code chạy **cùng thread Servlet**, `SecurityContextHolder` đã có context. Thêm wrapper không tự cải thiện bảo mật. Chỉ dùng context propagation khi có **thực sự chuyển execution sang thread khác** hoặc một nền tảng không tự tích hợp.

## 5. DelegatingSecurityContextCallable: task có kết quả

Một `Callable<V>` trả về kết quả và có thể ném checked exception. Wrapper `DelegatingSecurityContextCallable<V>` giữ cùng mục đích như Runnable:

```java
Callable<String> lookup = () -> {
    Authentication current =
            SecurityContextHolder.getContext().getAuthentication();
    return current == null ? "NONE" : current.getName();
};

Callable<String> delegated =
        new DelegatingSecurityContextCallable<>(lookup);

Future<String> result = executorService.submit(delegated);
String username = result.get();
```

Đây là **snippet**, giả định `executorService` có sẵn, imports và xử lý exceptions đúng. Khi tạo delegated `Callable` trong request Alice, task chạy sau đó có thể thấy context đã capture, kể cả khi T1 đã clear holder.

**Có nên dùng một Callable wrapper và một DelegatingSecurityContextExecutorService đồng thời?** Thường **không cần**. Nếu executor đã đảm nhận wrapping, người gọi chỉ nên submit một task bình thường. Double-wrap làm logic capture và cleanup khó kiểm tra, nhất là khi context bên ngoài và bên trong được lấy ở **hai thời điểm khác nhau**.

## 6. DelegatingSecurityContextExecutor: tự wrap ở điểm submit

Giả sử có `Executor` do application sở hữu:

```java
Executor rawExecutor = command -> new Thread(command).start();

Executor securedExecutor =
        new DelegatingSecurityContextExecutor(rawExecutor);

securedExecutor.execute(() -> {
    Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
    // Code nghiệp vụ có thể đọc auth của người submit.
});
```

Đây là snippet minh họa; **không** dùng cách tạo thread không giới hạn này ở production. Dùng bounded thread pool, queue cap, rate control, metrics và shutdown phù hợp.

### Hai kiểu constructor là hai chính sách khác nhau

**Kiểu 1 — capture context của người submit từng task:**

```java
Executor secured =
        new DelegatingSecurityContextExecutor(rawExecutor);
```

Mỗi lần `secured.execute(task)`, wrapper lấy context hiện có trong `SecurityContextHolder` của **thread gọi `execute`** rồi gắn cho task. Đây là kiểu phù hợp nếu request Alice submit task của Alice, request Bob submit task của Bob.

**Kiểu 2 — dùng context cố định cho mọi task:**

```java
SecurityContext fixed = SecurityContextHolder.createEmptyContext();
// fixed phải được xây từ principal/service identity ĐÃ được tin cậy.
Executor secured =
        new DelegatingSecurityContextExecutor(rawExecutor, fixed);
```

Ở kiểu này, **mọi** task của executor dùng **cùng context fixed**, bất kể ai submit. Tình huống hợp lý có thể là một background service account chuyên dụng, đã được cấp quyền tối thiểu theo chính sách. Rủi ro cực lớn nếu vô tình dùng context admin/request user rồi lưu executor đó thành singleton.

**Tránh lỗi phổ biến:** dựng bean `DelegatingSecurityContextExecutor(delegate, SecurityContextHolder.getContext())` lúc startup rồi mong nó tự chuyển sang principal của từng request. Nó sẽ giữ context cố định lúc bean khởi tạo (thường anonymous/empty), không phải context lúc submit.

### Capture-at-submit khác execute-time

```text
Alice submit task A (gắn Alice) ────────┐
Bob submit task B (gắn Bob) ───────┐   │
                                  ▼   ▼
                          Thread pool queue
                                  │
                          Worker xử lý B/A
                                  │
            mỗi task dùng context đã capture tại submit,
            không phải context của worker trước đó
```

Task có thể bắt đầu chạy sau khi HTTP request đã hoàn tất. Điều này không biến captured identity thành **quyền bất biến vĩnh viễn**: nếu account bị khóa hoặc role bị thu hồi trong thời gian chờ, task vẫn có thể mang snapshot cũ. Với tác vụ nhạy cảm, cần kiểm tra lại quyền/phiên bản danh tính **tại lúc xử lý**, hoặc dùng service-to-service authorization phù hợp.

## 7. Ví dụ Java 17+ chạy được: chứng minh capture, fixed context và cleanup

Ví dụ này **không cần Servlet container**, nhằm cô lập cơ chế ThreadLocal propagation. Nó tạo hai danh tính **giả lập chỉ cho test local**, không thực hiện username/password authentication. Không copy cách tự tạo `UsernamePasswordAuthenticationToken` này vào endpoint thật để thay `AuthenticationManager`.

Chương trình cố ý dùng **một single-thread executor** để chứng minh:

- Task chạy trên pool thô **không tự có** context của main thread.
- `DelegatingSecurityContextExecutorService(delegate)` lấy **mai** hoặc **an** tại lúc submit.
- `DelegatingSecurityContextExecutorService(delegate, fixedContext)` luôn dùng **service-operator**.
- Sau task thành công **và khi task ném exception**, pool thread không giữ danh tính cũ.
- `DelegatingSecurityContextRunnable` được tạo khi main có `lan` rồi main clear context vẫn cho worker task thấy `lan`.

### 7.1. Cấu trúc project

```text
security-context-concurrency-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/SecurityContextConcurrencyDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-concurrency-demo'
```

`build.gradle`:

```groovy
plugins {
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
    implementation 'org.springframework.security:spring-security-core:6.5.11'
}

application {
    mainClass = 'demo.SecurityContextConcurrencyDemo'
}
```

### 7.2. Java file hoàn chỉnh

Tạo `src/main/java/demo/SecurityContextConcurrencyDemo.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.security.concurrent.DelegatingSecurityContextExecutorService;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;

public final class SecurityContextConcurrencyDemo {

    public static void main(String[] args) throws Exception {
        ExecutorService rawPool = Executors.newSingleThreadExecutor();

        try {
            // Worker chưa nhận context nào.
            System.out.println("raw-before=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Chỉ mô phỏng principal đã xác thực trong test.
            setDemoIdentity("mai");
            System.out.println("main=" + name());

            // Thread pool thô không tự có ThreadLocal của main thread.
            System.out.println("raw-during=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Không truyền SecurityContext => capture mỗi lúc submit.
            DelegatingSecurityContextExecutorService perSubmission =
                    new DelegatingSecurityContextExecutorService(rawPool);

            System.out.println("wrapped-mai=" +
                    perSubmission.submit(SecurityContextConcurrencyDemo::name).get());

            setDemoIdentity("an");

            System.out.println("wrapped-an=" +
                    perSubmission.submit(SecurityContextConcurrencyDemo::name).get());

            System.out.println("raw-after-wrapped=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Truyền một SecurityContext rõ ràng => fixed identity.
            SecurityContext fixed = newContext("service-operator");

            DelegatingSecurityContextExecutorService fixedExecutor =
                    new DelegatingSecurityContextExecutorService(rawPool, fixed);

            System.out.println("fixed=" +
                    fixedExecutor.submit(SecurityContextConcurrencyDemo::name).get());

            System.out.println("main-after-fixed=" + name());

            // Context không được rò rỉ sau task bị lỗi.
            Future<?> failed = perSubmission.submit(() -> {
                throw new IllegalStateException("intentional");
            });

            try {
                failed.get();
            } catch (ExecutionException expected) {
                System.out.println("failure=" +
                        expected.getCause().getClass().getSimpleName());
            }

            System.out.println("raw-after-failure=" +
                    rawPool.submit(SecurityContextConcurrencyDemo::name).get());

            // Runnable wrap dưới identity lan, rồi clear main.
            setDemoIdentity("lan");
            Runnable wrappedOnce = new DelegatingSecurityContextRunnable(
                    () -> System.out.println("runnable=" + name()));

            SecurityContextHolder.clearContext();

            Thread once = new Thread(wrappedOnce, "example-once");
            once.start();
            once.join();

            System.out.println("main-cleared=" + name());

        } finally {
            SecurityContextHolder.clearContext();
            rawPool.shutdown();
            if (!rawPool.awaitTermination(5, TimeUnit.SECONDS)) {
                rawPool.shutdownNow();
            }
        }
    }

    private static String name() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        return authentication == null
                ? "NONE"
                : authentication.getName();
    }

    private static void setDemoIdentity(String username) {
        SecurityContextHolder.setContext(newContext(username));
    }

    private static SecurityContext newContext(String username) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Test fixture ONLY: không dùng để bypass real login.
        Authentication demoAuthentication =
                new UsernamePasswordAuthenticationToken(
                        username,
                        null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER")));

        context.setAuthentication(demoAuthentication);
        return context;
    }
}
```

Chạy trong thư mục `security-context-concurrency-demo`:

```bash
gradle run
```

Nếu có Gradle Wrapper, sử dụng `./gradlew run` trên macOS/Linux hoặc `gradlew.bat run` trên Windows. Cần JDK 17+ và Gradle tương thích.

### 7.3. Stdout dự kiến

```text
raw-before=NONE
main=mai
raw-during=NONE
wrapped-mai=mai
wrapped-an=an
raw-after-wrapped=NONE
fixed=service-operator
main-after-fixed=an
failure=IllegalStateException
raw-after-failure=NONE
runnable=lan
main-cleared=NONE
```

**Giải thích từng nhóm kết quả:**

1. `raw-before=NONE`, `raw-during=NONE`: worker thread riêng không tự nhận `ThreadLocal` từ main. Không có chứng cứ nào rằng pool chưa wrap sẽ sở hữu danh tính đang login.
2. `wrapped-mai=mai`: khi main giữ context mai và gọi `perSubmission.submit`, wrapper capture mai cho task đó.
3. `wrapped-an=an`: chính executor wrapper **được tái sử dụng**, nhưng lần submit sau capture an; không giữ một identity cố định từ lần đầu.
4. `raw-after-wrapped=NONE`: sau task wrap, worker được dọn/khôi phục trạng thái phù hợp, không rò rỉ mai/an vào task thô kế tiếp.
5. `fixed=service-operator`: overload constructor có `SecurityContext fixed` cố ý dùng một identity khác với người submit. Đây là tính năng phải được cấp quyền/đánh giá rõ trong production.
6. `main-after-fixed=an`: worker không tự sửa context của main thread.
7. `failure=IllegalStateException`: task cố ý ném exception và `Future.get()` bọc trong `ExecutionException`. Sau đó `raw-after-failure=NONE` chứng minh cleanup khi lỗi.
8. `runnable=lan`: `DelegatingSecurityContextRunnable` capture context lúc wrapper được tạo, trước khi main gọi `clearContext`.
9. `main-cleared=NONE`: context của main được dọn; việc wrapper chạy ở thread khác không tự đưa identity trở lại main.

**Điều kiện của ví dụ:** các task được submit và đợi hoàn thành theo thứ tự xác định bằng `Future.get()`/`Thread.join()`. Vì thế output không phụ thuộc việc thread pool chạy song song theo thứ tự nào. Nếu bạn bỏ các thao tác đồng bộ này, thứ tự dòng console có thể thay đổi.

**Bảo mật:** `new UsernamePasswordAuthenticationToken(username, null, authorities)` là cách dựng **test fixture**. Nó tạo token được xem là authenticated mà **không kiểm tra mật khẩu**; tuyệt đối không biến cách này thành đăng nhập thực. Trong ứng dụng production, `Authentication` phải đến từ `AuthenticationManager`/provider hoặc nguồn danh tính đáng tin.

**Giới hạn runtime:** ví dụ được thiết kế theo API Spring Security 6.5.11; mã và output được rà soát theo tài liệu, không phải log thực thi của dự án production. Nếu thay version hoặc context strategy, cần kiểm thử lại.

## 8. Sử dụng ExecutorService thay vì bọc từng task

Khi ứng dụng có `ExecutorService` chung, bạn có thể wrap **executor** một lần thay vì buộc mọi caller biết `DelegatingSecurityContextCallable`:

```java
ExecutorService rawPool = Executors.newFixedThreadPool(4);
ExecutorService securedPool =
        new DelegatingSecurityContextExecutorService(rawPool);

// Trong request của người dùng đã xác thực:
Future<String> future = securedPool.submit(
        () -> SecurityContextHolder.getContext()
                .getAuthentication().getName());
```

Đây là snippet; cần xử lý `Future.get`, shutdown, bounded queue và exception. Điều quan trọng là caller chỉ submit task bình thường; executor wrapper lo việc capture/set/cleanup.

**Không làm:**

```java
// Sai: giữ một authentication context request tại singleton bean startup.
SecurityContext userContext = SecurityContextHolder.getContext();
ExecutorService securedPool =
        new DelegatingSecurityContextExecutorService(rawPool, userContext);
```

Một bean dùng chung có thể giữ forever anonymous context hoặc một user không mong đợi. Nếu muốn **danh tính của người submit**, dùng constructor chỉ có `rawPool`. Nếu muốn **một service identity cố định**, tạo theo cơ chế tin cậy, giới hạn quyền và không nhầm với request principal.

### Lifecycle và shutdown

`DelegatingSecurityContextExecutorService` là một wrapper của `ExecutorService` thật. Để vận hành ổn định:

- Chọn executor có queue bounded, thread naming, rejection policy và metrics; `Executors.newFixedThreadPool(...)` có thể tạo queue không bounded theo implementation mặc định.
- Shutdown **một lần theo ownership** của underlying executor; không để nhiều bean tự cùng shutdown một raw pool chia sẻ.
- Nếu task đợi quá lâu, request user có thể logout, đổi role hoặc bị khóa trước khi task chạy. Wrapper không tự revoke/refresh credential.
- Xử lý `Future` exceptions, timeout/cancellation và retry rõ ràng. Không log toàn bộ `Authentication` hoặc raw token trong job logs.
- Với `submit`, exception có thể nằm trong `Future.get()`, không tự xuất ra request thread khi task chưa được chờ.
- Nên phân biệt bounded local task với persistent job queue; truyền `SecurityContext` object qua queue/network là thiết kế sai ranh giới.

## 9. Tích hợp Spring Boot @Async với DelegatingSecurityContextAsyncTaskExecutor

Trong Spring application, `@Async` chuyển method sang executor khác. Vì vậy method async có thể không thấy principal nếu executor không được tích hợp đúng.

Cách dùng `DelegatingSecurityContextAsyncTaskExecutor` với `ThreadPoolTaskExecutor`:

```java
@Configuration
@EnableAsync
class AsyncSecurityConfiguration {

    @Bean(name = "securityTaskExecutor")
    AsyncTaskExecutor securityTaskExecutor() {
        ThreadPoolTaskExecutor delegate = new ThreadPoolTaskExecutor();
        delegate.setCorePoolSize(2);
        delegate.setMaxPoolSize(4);
        delegate.setQueueCapacity(64);
        delegate.setThreadNamePrefix("security-task-");
        delegate.initialize();

        // Không truyền SecurityContext cố định:
        // lấy identity của người submit từng tác vụ.
        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

Đây là snippet **trong ứng dụng Spring Boot**: cần imports `org.springframework.context.annotation.Bean`, `Configuration`, `EnableAsync`, `AsyncTaskExecutor`, `ThreadPoolTaskExecutor` và `DelegatingSecurityContextAsyncTaskExecutor`. Ví dụ không bao gồm toàn bộ authentication configuration/application main; không coi đây là một project độc lập.

Một service khác:

```java
@Service
public class DocumentReportService {

    @Async("securityTaskExecutor")
    public CompletableFuture<String> submit() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        String username = authentication == null
                ? "NONE"
                : authentication.getName();

        // Demo: production nên trả job ID, không giữ request mở vô hạn.
        return CompletableFuture.completedFuture(username);
    }
}
```

Các điều kiện phải biết:

1. `@EnableAsync` được bật và method nằm trong Spring bean.
2. Method `@Async` phải được gọi **qua Spring proxy** (ví dụ controller gọi `DocumentReportService` bean); self-invocation như `this.submit()` trong cùng object có thể bypass proxy và chạy đồng bộ.
3. `@Async("securityTaskExecutor")` chọn đúng executor đã được wrap; không giả định mọi executor bean đều tự truyền context.
4. Constructor chỉ nhận delegate cho phép lấy context ở **lúc submit**, tránh giữ một user từ thời điểm ứng dụng khởi động.
5. Task phải có policy authorization riêng; chỉ truyền context không bảo đảm dữ liệu/truy cập hợp lệ.
6. Không ghi dữ liệu trong `SecurityContextHolder` để làm shared storage giữa task và request.
7. Nếu cần long-running job, trả `jobId` rồi xử lý theo identity được lưu và revalidate có kiểm soát, thay vì giữ toàn bộ mutable context.

**Lưu ý khi @Async gặp lỗi:** với method trả `CompletableFuture`, exception cần được xử lý qua returned future/error handler. Với `void` async method, lỗi có thể đi qua `AsyncUncaughtExceptionHandler`; đừng tưởng controller sẽ luôn nhận exception từ thread async.

### Tại sao không dùng TaskDecorator tự viết để set holder?

Spring `TaskDecorator` có thể dùng để truyền MDC, locale hoặc context khác. Bạn có thể tự viết decorator đặt/restore `SecurityContextHolder`, nhưng dễ quên `finally`, dùng sai context strategy hoặc capture không đúng thời điểm. Khi mục tiêu là Spring Security propagation, ưu tiên adapter `DelegatingSecurityContextAsyncTaskExecutor` chính thức; với tracing/MDC, dùng thêm cơ chế propagation tương ứng và tránh double-wrap không kiểm soát.

## 10. @PreAuthorize trong background task: quyền và principal không tự “hợp lệ mãi mãi”

Ví dụ có method security:

```java
@Service
public class ExportService {
    @PreAuthorize("hasAuthority('documents:export')")
    public void exportDocuments() {
        // ... truy vấn dữ liệu được phép xuất ...
    }
}
```

Đây là snippet, giả định `@EnableMethodSecurity` được bật và invocation đi qua Spring proxy. Nếu task được submit sau khi Alice đã xác thực, `DelegatingSecurityContext...` có thể giúp security interceptor lấy authorities của Alice trên worker thread.

Nhưng lưu ý:

- **Propagation không tự xác minh lại** Alice. Context có thể chứa authorities tại lúc submit, trong khi vai trò đã đổi trước khi task chạy.
- `@PreAuthorize` chỉ kiểm tra condition được viết. Nó không tự giới hạn tenant, owner hoặc phạm vi từng tài liệu nếu bạn không định nghĩa policy đó.
- Method security cũng có proxy boundary; gọi method nội bộ trong cùng bean có thể không chạy authorization advice.
- Nếu job cần truy cập object sau hàng giờ, phải xác định quyền theo **thời điểm enqueue hay thời điểm execute**. Với thao tác nhạy cảm, thường nên kiểm tra lại tại lúc execute.
- Không dùng một `ROLE_ADMIN` cố định cho tất cả task chỉ để “cho @PreAuthorize pass”; đó là nguy cơ privilege escalation.
- Không truyền raw password, access token, refresh token hoặc session cookie trong job payload để tái tạo authentication.

### Long-running và persistent background jobs: truyền ID, không truyền nguyên object context

Nếu công việc có thể chờ hàng phút, chạy sau logout, retry sau khi server restart hoặc chuyển qua nhiều node, wrapper ThreadLocal không còn là cơ chế identity phù hợp. Một thiết kế rõ hơn:

```text
HTTP request authenticated
   ↓
Authorization + validate quyền tạo job
   ↓
Lưu job record: jobId, requesterAccountId, tenantId,
               loại tác vụ, scope được yêu cầu, thời điểm
   ↓
Message queue / worker service
   ↓
Worker dùng service identity đáng tin
   ↓
Nạp account/tenant/resource, revalidate policy và trạng thái
   ↓
Chạy tác vụ, audit theo requester + service actor
```

Đây là **thiết kế khái niệm**, không phải code Java. Không serialize `SecurityContext` vào Kafka/SQS/Redis rồi coi đó là chứng chỉ lâu dài. Các quyền từ `Authentication` của request có thể đã hết hiệu lực, principal có thể chứa dữ liệu nhạy cảm và ThreadLocal không tồn tại xuyên process.

Nên lưu hai loại danh tính trong audit:

- **Requester (on-behalf-of):** người khởi tạo yêu cầu, account ID/tenant đáng tin.
- **Execution identity:** service/job principal thực sự chạy task, quyền được cấp theo service policy.

Hai giá trị khác nhau giúp phân biệt “ai yêu cầu” với “ai thực hiện”. Tránh dùng fixed admin context cho mọi worker chỉ vì code dễ chạy.

## 11. Context snapshot, mutable state và nguy cơ rò rỉ giữa người dùng

### 11.1. Context có thể là một object mutable

`SecurityContext` thường giữ một `Authentication` object. Khi wrapper capture một context, đó không có nghĩa toàn bộ principal/authorities/session state đã được deep-copy.

Nếu một code path sửa trực tiếp context đang được share, tác vụ nằm trong queue có thể thấy kết quả khác dự kiến. Các hướng bảo vệ:

1. Xem `SecurityContext` của request là trạng thái phục vụ request, **không phải object truyền dài hạn**.
2. Không sửa context shared tại chỗ khi cập nhật authentication; khi cần, tạo `SecurityContextHolder.createEmptyContext()`, gắn `Authentication` phù hợp.
3. Khi task chỉ cần vài trường, **truyền immutable DTO** gồm internal ID, tenant ID và authorization scope đã xác minh; không truyền entire context.
4. Với job có tác động nhạy cảm, revalidate trạng thái account/permission khi chạy, tránh dựa vào snapshot cũ.
5. Không đưa JPA entity nguyên vẹn với lazy relations hoặc password hash vào principal/background payload.
6. Không để wrapper fixed giữ một user context trong singleton lâu hơn cần thiết.

### 11.2. Thread pool tái sử dụng thread

Giả sử worker xử lý job của Alice rồi job của Bob:

```text
Thread pool worker-1:
    task Alice
       set SecurityContext(Alice)
       run
       finally restore/clear
    task Bob
       set SecurityContext(Bob)
       run
       finally restore/clear
    task không wrap
       không được thấy Alice/Bob
```

Nếu lập trình viên tự viết:

```java
executor.execute(() -> {
    SecurityContextHolder.setContext(aliceContext);
    performWork();
    // THIẾU finally -> có thể rò rỉ identity.
});
```

Đây là anti-pattern, phụ thuộc `aliceContext` và `performWork()`. Nếu task ném exception hoặc bị cancel trước cleanup, worker có thể giữ context của Alice. Vì executor tái sử dụng thread, đó là lỗi cách ly nghiêm trọng.

**Đừng nhầm “current context restored” với “user Alice vẫn còn quyền”.** Restoration chỉ là hygiene của ThreadLocal; không phải reauthorization.

### 11.3. Context strategy riêng

Các wrapper có thể sử dụng `SecurityContextHolderStrategy` đang được cấu hình trong ứng dụng. Nếu một dự án custom strategy, context provider của filter và wrapper phải tương thích; chỉ đổi strategy ở một phần có thể gây “worker không thấy auth”. Không đặt custom/global strategy tùy tiện để chữa propagation. Với Servlet app thông thường, mặc định ThreadLocal cộng với delegating wrapper đủ rõ ràng.

## 12. Spring MVC async và Servlet async: những tích hợp đã có sẵn

Không phải mọi trường hợp chuyển sang thread khác đều cần bạn tự thêm wrapper. Spring Security có một số **integration tự động** ở Servlet stack.

### 12.1. Controller trả Callable<T>

Spring MVC hỗ trợ method trả `Callable<T>` để xử lý bất đồng bộ:

```java
@GetMapping("/reports/current-user")
public Callable<String> currentUserLater() {
    return () -> {
        Authentication auth =
                SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "NONE" : auth.getName();
    };
}
```

Đây là snippet controller. Khi cấu hình Spring Security Servlet/MVC integration chuẩn, `WebAsyncManagerIntegrationFilter`/`SecurityContextCallableProcessingInterceptor` truyền `SecurityContext` vào `Callable` của controller, nên phần này **thường đã có cơ chế propagation**. Tài liệu Spring Security cho biết capture diễn ra khi Spring MVC bắt đầu `startCallableProcessing`.

**Không đồng nhất** với `CompletableFuture.supplyAsync(...)` do ứng dụng tự gọi. Nếu bạn tự submit vào common pool hoặc một executor không wrap, cơ chế tích hợp `Callable` của Spring MVC không tự bảo đảm context cho task đó.

### 12.2. DeferredResult<T>

`DeferredResult` thường được hoàn thành từ thread do ứng dụng sở hữu. Spring Security không thể tự biết thread đó được tạo ở đâu, nên **không có cùng mức auto-propagation như Callable controller**. Bạn có thể dùng `DelegatingSecurityContextExecutor`/`AsyncTaskExecutor` để bọc task thực sự hoàn tất kết quả.

### 12.3. Servlet AsyncContext.start(Runnable)

Spring Security có integration để truyền context với `AsyncContext.start(Runnable)` của Servlet API khi request đi qua wrapper/filter phù hợp. Nhưng điều đó **không có nghĩa** tất cả các `new Thread`, `CompletableFuture`, scheduler hoặc queue của ứng dụng đều tự được wrap. Hãy kiểm thử trên đúng API mà code đang dùng.

### 12.4. @Async không phải Spring MVC Callable

`@Async` thường chạy qua Spring Task `AsyncTaskExecutor`. Một controller trả `Callable` là cơ chế Spring MVC async với integration riêng. Cần xem **executor nào thực sự nhận task**, tránh vừa wrap ở MVC integration vừa wrap tùy tiện ở tầng khác và tạo context capture ở sai thời điểm.

## 13. Các API async không được tự động hỗ trợ trong mọi trường hợp

| Cách chạy | Có sẵn security context? | Hướng xử lý |
| --- | --- | --- |
| Code đồng bộ trong request thread | Thường có | Dùng holder bình thường |
| `new Thread(runnable)` | Không bảo đảm | Wrap `DelegatingSecurityContextRunnable` |
| `Executor.execute(runnable)` | Tùy executor | `DelegatingSecurityContextExecutor` |
| `ExecutorService.submit(callable)` | Tùy executor | `DelegatingSecurityContextExecutorService` hoặc Callable wrapper |
| `@Async` | Tùy bean executor/integration | `DelegatingSecurityContextAsyncTaskExecutor` |
| `CompletableFuture.supplyAsync(...)` default common pool | Không bảo đảm | Truyền executor đã wrap hoặc truyền identity rõ ràng |
| `CompletableFuture.supplyAsync(..., executor)` | Nếu executor đã wrap đúng | Kiểm tra capture-at-submit và cleanup |
| `parallelStream()` | Không bảo đảm trên ForkJoinPool | Tránh phụ thuộc ThreadLocal; thiết kế explicit identity |
| Spring MVC `Callable<T>` controller | Có integration Spring Security khi được cấu hình đúng | Không double-wrap nếu đã được hỗ trợ |
| Spring MVC `DeferredResult<T>` | Không có auto-propagation tương đương Callable | Wrap task do ứng dụng submit |
| `AsyncContext.start(Runnable)` Servlet | Có integration Spring Security trong flow phù hợp | Kiểm tra request wrapper/filter |
| Scheduler định kỳ | Không có “user request” tự nhiên | Service identity cố định được giới hạn hoặc no user context |
| Message queue/worker process khác | Không mang ThreadLocal qua process | Truyền account ID + proof/policy và revalidate |

### CompletableFuture và chain tiếp theo

Một bẫy thường gặp:

```java
CompletableFuture<String> first = CompletableFuture.supplyAsync(
        () -> currentUserName(),
        delegatingExecutor);

// thenApplyAsync không truyền executor có thể chạy trên commonPool.
CompletableFuture<String> second = first.thenApplyAsync(
        name -> currentUserName());
```

Đây là snippet, giả định `currentUserName()` và `delegatingExecutor` có sẵn. Chỉ task được submit qua executor đã wrap mới có điều kiện propagation rõ. **Không bảo đảm** các stage `thenApplyAsync`/`thenComposeAsync` dùng common pool có identity phù hợp. Mỗi async boundary cần explicit executor hoặc thiết kế không phụ thuộc holder.

### Scheduler và fixed identity

Một `@Scheduled` job chạy lúc nửa đêm **không có người đang đăng nhập để capture**. Nếu cần principal của system job, tạo một service identity riêng có quyền tối thiểu và quản lý rõ vòng đời, không dùng identity của request cuối cùng đã submit trước đó. `DelegatingSecurityContextScheduledExecutorService` có thể wrap task, nhưng identity vẫn cần được thiết kế và kiểm soát như mọi thành phần bảo mật khác.

## 14. Phân biệt context propagation với authorization và audit

**Có `Authentication` trong worker không có nghĩa mọi thao tác đều được phép.** Context giúp một authorization mechanism tìm thấy principal, nhưng việc có quyền hay không phụ thuộc:

- Authorities thực sự được cấp từ nguồn tin cậy, không phải client tự gán.
- Rule tại method/endpoint/resource, ví dụ `hasAuthority("documents:export")`.
- Tenant, owner, project scope, trạng thái account, token validity và thời điểm revalidation.
- Chính sách xử lý account bị khóa hoặc role bị thu hồi sau khi enqueue.
- Quyền kỹ thuật của background service với cơ sở dữ liệu/tài nguyên bên ngoài.

Nếu user Alice submit job khi có quyền `documents:export`, rồi admin thu hồi quyền trước khi worker xử lý, bạn phải quyết định policy nghiệp vụ: “quyền tại lúc submit là đủ” hay “phải còn quyền ở lúc thực thi”. Không nên để mặc định kỹ thuật của ThreadLocal **vô tình quyết định** chính sách này.

### Nguyên tắc least privilege

- Truyền identity của request chỉ cho các task cần hành động **on behalf of user** trong một thời gian ngắn.
- Với job hệ thống, ưu tiên một **service identity với quyền tối thiểu**, không phải user admin tùy tiện.
- Chỉ truyền các trường danh tính được phép, không giữ plaintext credentials hoặc session cookie.
- Ghi audit requester ID và executor/service actor ID tách biệt.
- Không serialize toàn bộ `SecurityContext` sang job payload/log.
- Khi task gọi HTTP API khác, ThreadLocal SecurityContext **không tự trở thành Authorization header**. Cần một cơ chế service-to-service credential/delegation riêng, ví dụ OAuth2 token exchange theo thiết kế.
- Nếu task có thể chạy lại (retry), kiểm tra lại quyền và idempotency thay vì replay một context snapshot không có hạn sử dụng.

## 15. Kiểm thử: đúng danh tính, đúng thời điểm, không rò rỉ

Một bài test tốt không chỉ assert “task thấy mai”. Nó cần bảo đảm cả **tác vụ sau trên cùng worker** không thấy thông tin của người trước.

### 15.1. Test các trường hợp tối thiểu

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Raw thread pool không wrap | Không tự có principal request |
| Wrapper per-submit với Alice | Task Alice thấy Alice |
| Cùng wrapper per-submit với Bob | Task Bob thấy Bob |
| Raw task sau Alice/Bob trên cùng worker | Không thấy Alice/Bob do rò rỉ |
| Wrapper fixed service context | Mọi task dùng service identity cố định theo cấu hình |
| Delegate ném exception | Context của task vẫn được dọn/khôi phục |
| Wrapper Runnable tạo khi Alice, chạy sau khi caller clear | Task vẫn thấy context capture đúng lúc tạo wrapper |
| `@Async` đi qua Spring proxy với secured executor | Task thấy danh tính theo policy per-submit |
| `@Async` self-invocation | Có thể không chạy async/proxy; test để phát hiện |
| `CompletableFuture` stage dùng default common pool | Không giả định propagation |
| User bị revoke quyền sau enqueue | Authorization xử lý theo chính sách đã định |
| Scheduled system job không có request | Không tự có “user cuối cùng” |
| Task ở node/process khác | Không phụ thuộc ThreadLocal; identity mapping riêng |
| Cancel/timeout/exception/retry | Không leak context, resource cleanup đúng |
| Multi-tenant cross-request | Không bao giờ dùng tenant hoặc authorities của request trước |

### 15.2. Mẫu integration test với ExecutorService

Nếu dùng JUnit 5, có thể test định hướng (snippet, cần imports/test project):

```java
@Test
void submitCapturesIdentityAndDoesNotLeakToPool() throws Exception {
    ExecutorService raw = Executors.newSingleThreadExecutor();
    try {
        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                        "mai", null,
                        List.of(new SimpleGrantedAuthority("ROLE_READER"))));
        SecurityContextHolder.setContext(context);

        ExecutorService secured =
                new DelegatingSecurityContextExecutorService(raw);

        assertEquals("mai", secured.submit(() ->
                SecurityContextHolder.getContext()
                        .getAuthentication().getName()).get());

        // Worker thô phải không giữ authentication của task trước.
        assertNull(raw.submit(() ->
                SecurityContextHolder.getContext()
                        .getAuthentication()).get());
    } finally {
        SecurityContextHolder.clearContext();
        raw.shutdownNow();
    }
}
```

Đoạn này minh họa **test fixture**, không phải login thật. `@WithMockUser` có thể chuẩn bị context ở một thread của test, nhưng **không tự bảo đảm** các task chạy trên một executor tùy ý có context; bạn vẫn phải submit qua wrapper và kiểm tra kết quả.

### 15.3. Integration test Spring Boot @Async

Khi test `@Async` trong Spring app:

1. Bật `@EnableAsync` và định nghĩa bean `securityTaskExecutor` theo cấu hình.
2. Tạo identity của test bằng security testing support hoặc một login request thật theo mục tiêu.
3. Gọi public `@Async` method qua bean khác, không gọi trực tiếp `this.method()`.
4. Đợi `CompletableFuture` với timeout hữu hạn; assert principal được truyền đúng.
5. Gửi một task thứ hai dưới identity khác; xác nhận không bị lẫn.
6. Nếu task có `@PreAuthorize`, test cho user thiếu authority và user được phép, bảo đảm interceptor đang hoạt động.
7. Tạo task ném exception; kiểm tra worker thread không còn context của task trước.
8. Kiểm tra executor thread count, queue bounded, shutdown và error reporting.

Không dùng `Thread.sleep(1000)` làm điều kiện đồng bộ duy nhất trong test; dùng `Future.get(timeout)` hoặc latches phù hợp để tránh flakiness.

## 16. Những lỗi phổ biến

1. **Tưởng `SecurityContextHolder` là biến toàn cục cho toàn JVM:** mặc định nó gắn với thread, không tự di chuyển qua task.
2. **Bật `MODE_INHERITABLETHREADLOCAL` để chữa thread pool:** worker có thể được tạo dưới một request rồi phục vụ nhiều user; nguy cơ lẫn identity.
3. **Dùng `MODE_GLOBAL` trong web app:** dễ phá cách ly giữa các request đồng thời.
4. **Tạo `DelegatingSecurityContextRunnable` quá sớm:** capture context khác với lúc task thực thi.
5. **Tạo singleton executor với context của một request:** vô tình chạy mọi task dưới cùng user.
6. **Quên constructor no-context để capture per submit:** context cố định không tự cập nhật mỗi request.
7. **Tưởng per-submit là deep-copy immutable:** context/principal có thể mutable, stale hoặc bị chia sẻ.
8. **Không cleanup `SecurityContextHolder` trong thread pool:** task sau có thể thấy quyền task trước.
9. **Không kiểm thử khi delegate ném exception:** cleanup trong `finally` là thuộc tính bảo mật cốt lõi.
10. **Dùng raw `CompletableFuture.supplyAsync` common pool:** không có propagation đảm bảo.
11. **Wrap executor nhưng stage `thenApplyAsync` lại dùng common pool:** identity có thể biến mất ở stage tiếp.
12. **Tưởng Spring MVC Callable và @Async là cùng một cơ chế:** các integration khác nhau.
13. **Tưởng DeferredResult tự có context như Callable controller:** task hoàn thành DeferredResult do ứng dụng sở hữu.
14. **Tưởng explicit-save của SecurityContextRepository thay thế propagation:** session persistence khác threading.
15. **Tưởng propagation là tự kiểm tra password/role lại:** wrapper không xác thực lại user.
16. **Giữ context request qua job dài hoặc queue retry:** danh tính/role có thể lỗi thời, không thích hợp serialize.
17. **Dùng fixed admin identity cho mọi scheduled job:** privilege escalation và audit khó truy dấu.
18. **Gán authorities do client gửi rồi chuyển vào worker:** bypass trust boundary.
19. **Chỉ kiểm tra authentication.getName() trong test:** không kiểm tra cleanup và cross-user.
20. **Không kiểm tra Spring proxy của @Async/@PreAuthorize:** self-invocation có thể bypass cơ chế.
21. **Nhầm worker ThreadLocal với outbound token:** gọi REST API khác không tự mang header Authorization.
22. **Cấp permission bằng group snapshot mà quên tenant/object policy:** có thể vượt phạm vi tài nguyên.
23. **Logging toàn bộ context, credentials hoặc token:** nguy cơ lộ dữ liệu nhạy cảm.
24. **Không giới hạn executor queue/thread count:** có thể cạn tài nguyên khi người dùng submit nhiều task.
25. **Cho rằng cancel Future tự đảm bảo task đã dừng và context được dọn ngay:** phải thiết kế cancellation, interrupt handling và resource lifecycle.
26. **Dùng wrapper hai lần ở nhiều tầng không hiểu capture timing:** dễ tạo nested contexts khó gỡ lỗi.
27. **Tự thay đổi SecurityContextHolderStrategy ở một component:** filter và wrapper có thể không đồng nhất.
28. **Không xác định policy khi quyền bị thu hồi giữa enqueue và execute:** lỗ hổng không phải ở ThreadLocal mà ở thiết kế authorization.

## 17. Bài tập thực hành

**Bài 1 — ThreadLocal:** chạy demo, chỉ ra vì sao `raw-during=NONE` khi main đang có user mai. Thử đổi executor sang pool hai thread và xem vì sao cần synchronization để không dự đoán thứ tự console.

**Bài 2 — Constructor và capture:** tạo wrapper `DelegatingSecurityContextRunnable` khi Alice còn đăng nhập, thay main context thành Bob trước khi chạy. Dự đoán user trong task. Sau đó tạo `DelegatingSecurityContextExecutor` không có fixed context, submit dưới Bob, so sánh.

**Bài 3 — Context cố định:** dùng một `SecurityContext` service-operator với chỉ `ROLE_REPORT_WORKER`, chạy hai task submit từ hai user khác nhau. Giải thích vì sao task dùng service-operator và các rủi ro nếu thay bằng ROLE_ADMIN.

**Bài 4 — Cleanup khi lỗi:** tạo task ném `RuntimeException`, assert `Future.get()` có exception và raw task sau đó trên cùng pool không thấy principal cũ. Kiểm tra cả kết quả khi task chạy thành công.

**Bài 5 — @Async:** tạo Spring Boot web app có `@EnableAsync`, bean `DelegatingSecurityContextAsyncTaskExecutor`, service method `@Async("securityTaskExecutor")`. Viết integration test gọi từ hai user khác nhau qua Spring proxy.

**Bài 6 — CompletableFuture:** tạo chain `supplyAsync(..., securedExecutor)` rồi `thenApplyAsync(...)` không truyền executor. Ghi nhận danh tính và sửa bằng executor đã wrap ở từng boundary hoặc dùng explicit identity parameters.

**Bài 7 — Method Security:** bật `@EnableMethodSecurity`, tạo `@PreAuthorize("hasAuthority('documents:export')")`. Kiểm tra user có quyền và không có quyền qua một task đã propagate, rồi kiểm tra tenant policy riêng.

**Bài 8 — Revocation:** một job được enqueue khi Alice có quyền, rồi admin thu hồi quyền trước lúc chạy. Định nghĩa policy cụ thể, thay cách chỉ mang context bằng việc lưu requester ID và revalidate lúc execute.

**Bài 9 — Long-running queue:** thiết kế payload cho job xử lý báo cáo sau nhiều giờ, bao gồm requester ID, tenant ID, job ID và scope; không serialize `Authentication`. Trình bày execution service identity, authorization và audit.

**Bài 10 — MVC async:** so sánh Spring MVC controller trả `Callable<T>` và `DeferredResult<T>`. Xác định trường hợp Spring Security có integration tự động và trường hợp cần wrapper riêng.

### Tiêu chí hoàn thành

Người học có thể nói rõ:

- Vì sao `SecurityContextHolder` mặc định là ThreadLocal và task pool không tự thấy user?
- `DelegatingSecurityContextRunnable`, `Callable` và `ExecutorService` dùng vào lúc nào?
- Constructor không có SecurityContext và constructor có fixed SecurityContext khác nhau thế nào?
- Vì sao **capture time** và **execution time** có thể khác biệt?
- Cleanup/restore trong `finally` ngăn cross-user leak ra sao?
- `@Async` cần executor/proxy phù hợp và Spring MVC Callable có tích hợp nào?
- Vì sao context propagation **không phải** authentication, authorization hay session persistence?
- Khi job chạy lâu hoặc qua queue khác process, vì sao nên truyền identity ID và revalidate thay vì mang nguyên context?

## 18. Tài liệu chính thức

- [Spring Security 6.5 — Concurrency Support](https://docs.spring.io/spring-security/reference/6.5/features/integrations/concurrency.html): `DelegatingSecurityContextRunnable`, `DelegatingSecurityContextExecutor` và các lớp concurrency liên quan.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `SecurityContextHolder`, ThreadLocal và `Authentication`.
- [Spring Security 6.5.11 — DelegatingSecurityContextExecutorService API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextExecutorService.html): hai constructors, `submit` và lifecycle.
- [Spring Security 6.5.11 — DelegatingSecurityContextCallable API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/concurrent/DelegatingSecurityContextCallable.html): wrapping Callable.
- [Spring Security 6.5 — DelegatingSecurityContextRunnable API](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/concurrent/DelegatingSecurityContextRunnable.html): capture và restoration semantics.
- [Spring Security 6.5 — Spring MVC Async Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/mvc.html): Callable và `WebAsyncManagerIntegrationFilter`.
- [Spring Security 6.5 — Servlet API Integration](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/servlet-api.html): `AsyncContext.start(Runnable)`.
- [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@EnableMethodSecurity` và `@PreAuthorize`.
- [Spring Framework — Async Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@Async`, executor selection, method proxy và scheduling.

**Ghi chú phiên bản:** ví dụ hoàn chỉnh dùng Java 17 / Spring Security Core 6.5.11. Nếu dự án đang chạy Spring Security 7, WebFlux/Reactor, virtual threads hay framework/task executor có context propagation riêng, phải xác minh cơ chế phù hợp thay vì áp dụng trực tiếp mô hình ThreadLocal của Servlet. Với reactive flows, context thường đi qua Reactor Context, không phải các wrapper Servlet ThreadLocal của bài này.