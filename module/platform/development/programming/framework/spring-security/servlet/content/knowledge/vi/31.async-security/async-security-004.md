# DelegatingSecurityContextRunnable và DelegatingSecurityContextCallable — truyền SecurityContext qua luồng bất đồng bộ

## 1. Mục tiêu

Trong ứng dụng **Spring Security Servlet (Spring Boot 3.x, Spring Security 6.x, Java 17+)**, thông tin người gọi hiện tại thường nằm trong `SecurityContextHolder`, mặc định được quản lý bằng **`ThreadLocal`**. Khi công việc chạy ở luồng khác, ví dụ qua `ExecutorService`, task trong thread pool, `@Async` hoặc một callback của `CompletableFuture`, luồng làm việc **không tự nhận SecurityContext của request**.

Hai lớp `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable` cung cấp cách **bọc task** để thiết lập một `SecurityContext` trên luồng chạy task, gọi công việc thật, rồi khôi phục trạng thái bảo mật trước đó trong `finally`.

Sau bài học, bạn có thể:

1. Phân biệt `SecurityContext`, `Authentication`, `GrantedAuthority` và cơ chế `ThreadLocal`.
2. Bọc `Runnable`/`Callable` để truyền context khi task được thực thi ở luồng khác.
3. Hiểu khác nhau giữa **ngữ cảnh cố định do caller truyền vào** và **ngữ cảnh đang có tại lúc tạo wrapper**.
4. Kiểm tra context được **khôi phục hoặc xóa** sau khi task chạy, kể cả khi có exception.
5. Chọn `DelegatingSecurityContextExecutor`, `DelegatingSecurityContextExecutorService` hoặc `DelegatingSecurityContextAsyncTaskExecutor` khi có nhiều task.
6. Nhận diện rủi ro rò rỉ quyền giữa các tác vụ trong thread pool, context cũ, session hết hạn và công việc chạy sau request.

Bài chỉ nói về **Spring Security Servlet, tác vụ Java trên luồng khác**. Không áp dụng cách sao chép `ThreadLocal` này nguyên xi cho Spring Security WebFlux/Reactor, nơi security context thường được đưa qua **Reactor Context**.

## 2. Vì sao bất đồng bộ làm mất thông tin đăng nhập?

### 2.1. SecurityContextHolder không phải biến toàn cục cho mọi luồng

Trong mô hình thông thường:

- `SecurityContext` chứa `Authentication` hiện tại.
- `Authentication` mô tả principal, credentials, danh sách authority và trạng thái authenticated.
- `SecurityContextHolder.getContext()` tìm context **của luồng đang chạy**, thông qua `SecurityContextHolderStrategy`.
- Trong Spring Security Servlet, chiến lược mặc định thường là `MODE_THREADLOCAL`.

Khi một servlet request đã được xác thực, filter chain thiết lập `SecurityContext` cho luồng xử lý request. Sau khi request kết thúc, Spring Security thực hiện cleanup phù hợp để không giữ Authentication của request trước trên luồng container tái sử dụng.

Nếu cùng request gửi task sang một `ExecutorService`:

```text
Luồng servlet (request A)                  Luồng worker trong thread pool
---------------------------------          --------------------------------
SecurityContext: alice
submit(task)  ------------------------->    SecurityContext: thường rỗng
                                           task đọc getContext()
                                           authentication == null
<--------------------------------------    task kết thúc
```

Đây là vấn đề **ranh giới luồng**, không nhất thiết là lỗi đăng nhập: `alice` đã được xác thực trên request thread nhưng một worker thread có `ThreadLocal` độc lập.

### 2.2. Vì sao không “sửa” bằng MODE_GLOBAL hay InheritableThreadLocal?

`SecurityContextHolder.MODE_GLOBAL` chia sẻ context trên toàn JVM: rất nguy hiểm cho ứng dụng đa người dùng vì request này có thể nhìn thấy quyền của request khác.

`MODE_INHERITABLETHREADLOCAL` truyền giá trị ThreadLocal khi **tạo luồng con**, không truyền context mới cho mỗi lần sử dụng một luồng worker đã tồn tại. Với thread pool, luồng được tạo từ trước và tái sử dụng nhiều lần nên cách này vừa **không đáng tin để truyền đúng caller**, vừa có nguy cơ giữ quyền cũ. Đừng bật toàn cục chỉ để sửa một task bất đồng bộ.

Giải pháp ở đây là **gắn SecurityContext vào phạm vi thực thi của đúng task**, không thay chiến lược trên toàn ứng dụng.

## 3. Cơ chế của hai wrapper

### 3.1. DelegatingSecurityContextRunnable

Đây là lớp triển khai `Runnable`. Nó nắm:

- `delegate`: `Runnable` thật sự thực hiện công việc.
- `delegateSecurityContext`: context dự kiến dùng khi delegate chạy.

Mô hình khái niệm (pseudocode, **không phải nguyên văn mã nguồn framework**):

```java
SecurityContext previous = SecurityContextHolder.getContext();
try {
    SecurityContextHolder.setContext(delegatedContext);
    delegate.run();
} finally {
    // Khôi phục previous, hoặc clear context nếu previous rỗng.
    restoreOrClear(previous);
}
```

Giữ **context trước đó** và xử lý trong `finally` rất quan trọng. Một worker thread có thể đang chạy hàng nghìn task; nếu không dọn, user A có thể để lại authorities cho task của user B hoặc một công việc không có danh tính.

Spring Security thực hiện việc set/restore/clear qua `SecurityContextHolderStrategy`; đừng tự copy pseudocode thành một `Runnable` production rồi bỏ mất các chi tiết xử lý context rỗng, exception hoặc strategy tùy chỉnh.

### 3.2. DelegatingSecurityContextCallable<V>

`Callable<V>` trả về giá trị kiểu `V` và có thể ném checked exception. `DelegatingSecurityContextCallable<V>` thực hiện **cùng cơ chế propagation và cleanup** nhưng trả kết quả từ `delegate.call()`.

| Tiêu chí | `DelegatingSecurityContextRunnable` | `DelegatingSecurityContextCallable<V>` |
| --- | --- | --- |
| Interface được bọc | `Runnable` | `Callable<V>` |
| Phương thức delegate | `void run()` | `V call() throws Exception` |
| Kết quả | Không có giá trị nghiệp vụ trực tiếp | Có kết quả kiểu `V` |
| Gửi tới `ExecutorService` | `submit(Runnable)` | `submit(Callable<V>)` |
| Truyền SecurityContext | Có | Có |
| Dọn/khôi phục context | Trong `finally` | Trong `finally` |
| Exception | Lỗi unchecked; khi submit có thể bọc trong `ExecutionException` | Checked/unchecked; `Future.get()` có thể ném `ExecutionException` |

Cả hai chỉ **đưa SecurityContext tới nơi công việc chạy**. Chúng không tự cấp authority mới, không tạo session đăng nhập, không tự xin access token và không thay thế quyết định phân quyền.

## 4. Hai cách khởi tạo wrapper và thời điểm capture

### 4.1. Capture ngữ cảnh hiện tại khi tạo wrapper

```java
Runnable wrapped =
    new DelegatingSecurityContextRunnable(originalRunnable);

Callable<String> wrappedCall =
    new DelegatingSecurityContextCallable<>(originalCallable);
```

Ở những constructor không truyền context tường minh, Spring Security dùng context của **luồng gọi tại thời điểm khởi tạo wrapper**, rồi giữ context đó để dùng khi task chạy. Cần tạo wrapper **khi đang ở luồng có Authentication đúng**, thường là request thread sau khi Spring Security xác thực.

Không được tạo một wrapper duy nhất lúc ứng dụng startup khi chưa có người đăng nhập, rồi dùng lại để xử lý task của mọi user; nó sẽ không tự chọn Authentication mới theo từng request.

### 4.2. Truyền context được chọn rõ ràng

```java
SecurityContext context = SecurityContextHolder.getContext();

Runnable wrapped =
    new DelegatingSecurityContextRunnable(originalRunnable, context);

Callable<String> wrappedCall =
    new DelegatingSecurityContextCallable<>(
        originalCallable, context);
```

Đây là **đoạn dùng API trong một phương thức đã có biến delegate**, không phải Java class độc lập. Context tường minh hữu ích khi:

- Muốn kiểm soát chính xác context nào được dùng.
- Đã thu thập context tại ranh giới request và tạo task ở tầng khác.
- Cần thiết lập một **service identity được cấp quyền có kiểm soát** cho tác vụ hệ thống, với audit và giới hạn rõ ràng.

**Cảnh báo:** dùng fixed context với quyền `ADMIN` cho một wrapper/executor phục vụ nhiều user sẽ khiến task nào đi qua wrapper đó cũng chạy dưới quyền ấy. Chỉ dùng service identity khi kiến trúc và audit cho phép; không “mượn” Authentication của user khác.

### 4.3. Capture không có nghĩa là deep-copy

`SecurityContext` là object có thể thay đổi. Constructor wrapper thường **giữ tham chiếu** tới context, không tạo snapshot bất biến của toàn bộ principal, authorities hoặc credentials. Nếu code khác thay `Authentication` trong cùng object trước khi worker chạy, worker có thể nhìn thấy thay đổi đó.

Nếu cần đóng băng thông tin cho công việc:

- Cân nhắc tạo `SecurityContext` mới chứa một Authentication đã được kiểm soát và có vòng đời xác định.
- Hiểu rằng gán cùng `Authentication` vào context mới vẫn chỉ là **shallow copy**, không clone toàn bộ principal/credentials.
- Tốt hơn với job lâu dài: chuyển **identity/tenant/id nguồn được phép** thành command data tối thiểu, rồi xác minh lại permission trong service tại thời điểm thực thi, thay vì giữ nguyên session context hàng giờ.

## 5. Ví dụ Java 17+ có thể chạy: mất context và khôi phục context

Ví dụ dùng **Spring Security Core** và một `ExecutorService` đơn luồng. Có thể tạo project Gradle mới với hai file sau. Không cần servlet container để mô phỏng ranh giới ThreadLocal; logic wrapper chính là logic dùng trong ứng dụng Servlet.

### 5.1. Tập tin `build.gradle` (Groovy DSL)

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.4.1')
    implementation 'org.springframework.security:spring-security-core'

    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.SecurityContextPropagationDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng một phiên bản Spring Boot 3.x BOM để quản lý Spring Security 6.x và JUnit phù hợp. Trong dự án Spring Boot có sẵn dependency management, hãy dùng phiên bản do dự án quản lý thay vì ép thêm một BOM khác. Mẫu Gradle cần Java 17 và Gradle tương thích với Java/toolchain.

### 5.2. Tập tin `src/main/java/demo/SecurityContextPropagationDemo.java`

```java
package demo;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.concurrent.DelegatingSecurityContextRunnable;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

public final class SecurityContextPropagationDemo {

    static String currentUser() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();
        return authentication == null ? "none" : authentication.getName();
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext aliceContext =
                SecurityContextHolder.createEmptyContext();

            aliceContext.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    "alice",
                    "not-a-real-password",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );

            SecurityContextHolder.setContext(aliceContext);

            System.out.println("main=" + currentUser());

            // Luồng worker không tự kế thừa context của luồng main.
            String raw = pool.submit(
                (Callable<String>) SecurityContextPropagationDemo::currentUser
            ).get();
            System.out.println("raw=" + raw);

            Runnable delegate = () ->
                System.out.println("runnable=" + currentUser());

            // Constructor 1 tham số capture context khi bọc task.
            Runnable securedRunnable =
                new DelegatingSecurityContextRunnable(delegate);
            pool.submit(securedRunnable).get();

            // Constructor 2 tham số nhận context tường minh.
            Callable<String> securedCallable =
                new DelegatingSecurityContextCallable<>(
                    SecurityContextPropagationDemo::currentUser,
                    aliceContext
                );

            System.out.println(
                "callable=" + pool.submit(securedCallable).get());

            // Nếu wrapper cleanup đúng, worker lại không có Authentication.
            String after = pool.submit(
                (Callable<String>) SecurityContextPropagationDemo::currentUser
            ).get();
            System.out.println("workerAfter=" + after);

        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy:

```bash
gradle --quiet run
```

Nếu project có Gradle Wrapper đã được tạo, dùng `./gradlew --quiet run` trên Bash/macOS/Linux hoặc `.\gradlew.bat --quiet run` trên Windows PowerShell.

**Stdout mong đợi trong môi trường khởi chạy chuẩn (không có process khác sửa ThreadLocal):**

```text
main=alice
raw=none
runnable=alice
callable=alice
workerAfter=none
```

**Tại sao kết quả ổn định?**

1. `SecurityContextHolder` trên luồng main chứa `alice`, nên `main=alice`.
2. `Executors.newSingleThreadExecutor()` dùng worker riêng; ThreadLocal của worker chưa được set, nên `raw=none`.
3. `DelegatingSecurityContextRunnable` được tạo **trên luồng main khi aliceContext đang active**, nên wrapper gắn context đó vào worker khi chạy và in `runnable=alice`.
4. `DelegatingSecurityContextCallable` nhận chính `aliceContext`, nên trả `"alice"` qua `Future.get()`.
5. Sau cả hai task bọc, wrapper khôi phục/clear context trước đó; task thường chạy tiếp ở **cùng pool một luồng** nhưng không thấy `alice`, nên `workerAfter=none`.

`Future.get()` ở đây chờ task trước hoàn tất, khiến thứ tự dòng output xác định được. **Không dùng `Thread.sleep()` để “đợi context truyền xong”**: propagation diễn ra khi wrapper chạy trên worker, không phụ thuộc thời gian ngủ. Ứng dụng nhiều luồng phải test đúng đồng bộ/correlation.

### 5.3. `Callable` và giá trị trả về

Khi task tạo kết quả, kiểu generic vẫn được giữ:

```java
Callable<String> delegate = () ->
    SecurityContextHolder.getContext().getAuthentication().getName();

Callable<String> secured =
    new DelegatingSecurityContextCallable<>(delegate);

String username = pool.submit(secured).get();
```

Đoạn này giả định chạy trong phạm vi có `pool` và Authentication hợp lệ, giống chương trình ở trên. Nếu `delegate.call()` ném exception, `Future.get()` sẽ ném `ExecutionException` (hoặc `InterruptedException` khi thread chờ bị interrupt); lỗi gốc ở `getCause()`. Wrapper vẫn cleanup trong `finally`.

Không bắt exception rồi trả kết quả “thành công” nếu thực chất task đã bị từ chối vì thiếu quyền; cần propagate lỗi hoặc map thành lỗi nghiệp vụ rõ ràng.

## 6. Kiểm thử: xác minh không rò context giữa các task

Một lỗi nguy hiểm hơn `authentication == null` là **user A bị giữ lại trên worker rồi user B nhận quyền của A**. Vì thế test không chỉ cần kiểm tra context xuất hiện trong delegate mà còn phải kiểm tra **context sau task**.

Tập tin `src/test/java/demo/ContextPropagationTest.java`:

```java
package demo;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.concurrent.DelegatingSecurityContextCallable;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ContextPropagationTest {

    @Test
    void callablePropagatesThenCleansWorkerContext() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    "alice",
                    "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );

            SecurityContextHolder.setContext(context);

            Callable<String> action = () ->
                SecurityContextHolder.getContext()
                    .getAuthentication().getName();

            Callable<String> wrapped =
                new DelegatingSecurityContextCallable<>(action);

            assertEquals("alice", pool.submit(wrapped).get());

            Authentication workerAuthentication = pool.submit(
                (Callable<Authentication>) () ->
                    SecurityContextHolder.getContext().getAuthentication()
            ).get();

            assertNull(workerAuthentication);
        } finally {
            SecurityContextHolder.clearContext();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```bash
gradle --quiet test
```

Test này xác minh **propagation và cleanup trên worker pool**, không chứng minh người dùng có quyền gọi một API cụ thể. Muốn xác minh authorization, thêm test Spring MVC/Method Security với `hasAuthority` hoặc `@PreAuthorize` ở service thật.

### 6.1. Test exception path

Một wrapper đúng phải restore/clear context **ngay cả khi delegate ném lỗi**. Có thể đổi task thành một `Callable` ném `IllegalStateException("demo")`, gọi `.get()` và `assertThrows(ExecutionException.class, ...)`, sau đó submit task không bọc để kiểm tra Authentication trên worker là null. Đừng nuốt lỗi kiểm thử; nếu `finally` không chạy, test phải fail.

### 6.2. Test có nhiều user

Với cùng một executor một luồng, lần lượt:

1. Set SecurityContext của `alice`, tạo wrapper A rồi submit.
2. Thay context caller bằng context của `bob`, tạo wrapper B rồi submit.
3. Kiểm tra A thấy `alice`, B thấy `bob`, và task không bọc sau đó thấy `null`.

Quan trọng: **tạo wrapper riêng trong đúng context của từng user**; không tạo sẵn wrapper A rồi tái sử dụng cho B. Đừng test bằng `SecurityContextHolder.MODE_GLOBAL`, vì nó che mất ranh giới thread thực tế.

## 7. Tại sao context phải được restore, không chỉ clear?

Hãy xét hai tình huống:

- Worker ban đầu **không có** Authentication. Wrapper set context của user A, chạy task rồi clear. Kết quả đúng là worker lại không có Authentication.
- Worker ban đầu có một context hợp lệ **từ phạm vi kiểm soát khác**. Wrapper tạm thời thay bằng context A, chạy task, rồi **khôi phục context ban đầu** để không phá trạng thái của code gọi bên ngoài.

Vì vậy phát biểu chính xác là **“restore previous context hoặc clear khi trước đó rỗng”**, không phải “wrapper luôn gọi clearContext cho mọi tình huống”. Điều này càng quan trọng khi có wrapper lồng nhau.

```text
Worker bắt đầu: context X
  └─ Runnable wrapper A: context A
       └─ Callable wrapper B: context B
            └─ call() xong -> quay về A
       └─ run() xong -> quay về X
```

Trong ứng dụng thực tế, wrapper thường được dùng để gắn context vào worker thread ban đầu rỗng; logic restore vẫn là một phần quan trọng của hợp đồng an toàn.

## 8. Khi có nhiều task: bọc executor thay vì từng Runnable/Callable

Tạo wrapper thủ công phù hợp cho một vài task. Nếu mọi lệnh submit trong một subsystem đều cần propagation, có thể bọc toàn bộ executor với Spring Security:

- `org.springframework.security.concurrent.DelegatingSecurityContextExecutor`
- `org.springframework.security.concurrent.DelegatingSecurityContextExecutorService`
- `org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor`

Với một `ExecutorService`:

```java
ExecutorService underlying = Executors.newFixedThreadPool(4);

// ExecutorService wrapper tự bọc các Runnable/Callable được submit.
ExecutorService secured =
    new DelegatingSecurityContextExecutorService(underlying);

try {
    // Gọi submit trong phạm vi SecurityContext của caller.
    Future<String> result = secured.submit(() ->
        SecurityContextHolder.getContext()
            .getAuthentication().getName());

    String username = result.get();
} finally {
    secured.shutdown();
}
```

Đoạn này thuộc một phương thức có imports cho `ExecutorService`, `Executors`, `Future`, `DelegatingSecurityContextExecutorService`, `SecurityContextHolder`; cần thực thi trong phạm vi có Authentication để không gặp null. Một `DelegatingSecurityContextExecutorService` **không có context tường minh** thường capture context của caller tại thời điểm **submit**, tốt hơn việc giữ một wrapper tạo sẵn ở startup.

Nếu constructor truyền **SecurityContext cố định**, tất cả task trên wrapper đó sẽ dùng cùng context. Cách này dùng cho service account được kiểm soát, **không** dùng cho executor phục vụ nhiều người dùng với các quyền khác nhau. Khi dùng wrapper executor, tránh bọc thêm wrapper task không cần thiết khiến việc theo dõi context và vòng đời khó hiểu.

### 8.1. ExecutorService không biến task thành request mới

Nếu `Future.get()` chờ lâu trên request thread, request vẫn bị giữ; mặc dù công việc dùng executor, đoạn gọi có thể vẫn làm HTTP response chậm. Cân nhắc timeout, queue capacity, cancellation và tách nhiệm vụ dài thành job độc lập.

Propagating `SecurityContext` chỉ giải quyết **danh tính trong task**. Nó không tự giữ transaction của JPA, persistence context, MDC tracing, request attributes hoặc locale của servlet request. Những context đó cần cơ chế riêng nếu thực sự cần; đừng coi SecurityContext wrapper là “copy toàn bộ request”.

## 9. Kết hợp với Spring `@Async` trong ứng dụng Servlet

`@Async` thường dùng `TaskExecutor` và chạy method trong thread pool. Một `@Async` method **không tự động** được bảo đảm có Authentication của request chỉ vì annotation tồn tại. Có thể dùng `DelegatingSecurityContextAsyncTaskExecutor` để bọc delegate `ThreadPoolTaskExecutor`.

### 9.1. Cấu hình bean `AsyncTaskExecutor`

Giả sử ứng dụng Spring Boot 3 đã có `spring-boot-starter-security`, `spring-boot-starter-web`, method security nếu dùng `@PreAuthorize`, và dependency cho Spring `@Async`.

Tập tin minh họa `AsyncSecurityConfig.java`:

```java
package com.example.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.security.task.DelegatingSecurityContextAsyncTaskExecutor;

@Configuration
@EnableAsync
public class AsyncSecurityConfig {

    @Bean
    ThreadPoolTaskExecutor applicationTaskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("secured-async-");
        executor.initialize();
        return executor;
    }

    @Bean("securityTaskExecutor")
    AsyncTaskExecutor securityTaskExecutor(
            @Qualifier("applicationTaskExecutor")
            ThreadPoolTaskExecutor delegate) {

        return new DelegatingSecurityContextAsyncTaskExecutor(delegate);
    }
}
```

`AsyncTaskExecutor` bọc delegate theo **context của caller tại lúc submit**, nên worker thấy Authentication tương ứng và wrapper dọn lại context sau khi chạy. `ThreadPoolTaskExecutor` được quản lý như bean, có cấu hình pool/queue rõ ràng; đừng khởi tạo một pool mới cho từng request.

Tại môi trường thật, chọn pool size/queue/timeout theo tải và cấu hình graceful shutdown. Async task có chứa context của người dùng phải được bảo vệ khi ghi log, khi thất bại và khi job bị hủy.

### 9.2. Service bất đồng bộ và caller

Tập tin minh họa `AuditService.java`:

```java
package com.example.web;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class AuditService {

    @Async("securityTaskExecutor")
    public CompletableFuture<String> currentActor() {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        String actor = authentication == null
            ? "none"
            : authentication.getName();

        return CompletableFuture.completedFuture(actor);
    }
}
```

Nếu một controller/service **khác bean** gọi `auditService.currentActor()` từ request thread đã được xác thực, task được dispatch qua `securityTaskExecutor`, capture context của caller và trả `CompletableFuture<String>`. Không gọi `this.currentActor()` từ bên trong cùng bean nếu kỳ vọng `@Async` proxy tự xử lý: **self-invocation** có thể bỏ qua proxy và chạy đồng bộ.

Đây là ví dụ trong ứng dụng Spring Boot, **không phải chương trình tự biên dịch một file bằng `javac`** vì cần framework, application context và security configuration. Trong API thật, trước khi tác vụ thực hiện hành động nhạy cảm, nên có kiểm tra authorization tại nơi thực thi phù hợp; chỉ vì Authentication tồn tại không đồng nghĩa đã có quyền.

### 9.3. CompletableFuture.supplyAsync

Đoạn sau **không** tự truyền SecurityContext:

```java
CompletableFuture<String> task =
    CompletableFuture.supplyAsync(() ->
        SecurityContextHolder.getContext()
            .getAuthentication().getName());
```

Không chỉ định executor nghĩa là thường dùng `ForkJoinPool.commonPool()`; worker không có context của servlet thread, có thể ném `NullPointerException`. Hãy dùng executor **đã bọc propagation**:

```java
CompletableFuture<String> task =
    CompletableFuture.supplyAsync(
        () -> SecurityContextHolder.getContext()
            .getAuthentication().getName(),
        securedExecutor
    );
```

Ở đây `securedExecutor` là `Executor` bọc bằng `DelegatingSecurityContextExecutor` hoặc executor tương thích khác được cấp sẵn cho scope đúng. Mọi stage bất đồng bộ được đăng ký sau đó (`thenApplyAsync`, `thenComposeAsync`...) có thể nhảy sang executor khác; stage nào cần Authentication thì phải dùng executor có propagation thích hợp. Không nghĩ rằng context tự “chạy theo” toàn bộ chain của `CompletableFuture`.

## 10. Spring MVC async và các cơ chế khác

### 10.1. Controller trả Callable

Spring Security Servlet có tích hợp hỗ trợ cho **Spring MVC asynchronous `Callable`** thông qua `WebAsyncManagerIntegrationFilter` và cơ chế integration của Spring. Trong cấu hình Spring Security thông thường, context của request có thể được thiết lập phù hợp khi `Callable` chạy trên luồng của MVC.

Điều này khác với việc tự gọi `executor.submit(...)` ở bất kỳ service nào. Đừng bọc chồng bừa bãi một `Callable` của MVC nếu integration của framework đã quản lý. Hãy test thực tế cùng phiên bản Spring Security và cách cấu hình async executor.

### 10.2. DeferredResult, ResponseBodyEmitter, custom threads

Với `DeferredResult`, `ResponseBodyEmitter`, `SseEmitter`, servlet callbacks hoặc thread tạo thủ công, lập trình viên có thể phải chủ động quản lý context ở **đúng đoạn code thực thi**. Không được suy diễn việc `Callable` có integration nghĩa là mọi loại async của MVC tự động truyền authentication.

### 10.3. WebFlux/Reactor

Trong **Spring WebFlux**, `ReactiveSecurityContextHolder` dựa trên Reactor Context. Dùng `DelegatingSecurityContextRunnable` để bắt `ThreadLocal` không phải mô hình chuẩn cho toàn bộ reactive pipeline. Nếu một hệ thống có cả Servlet và Reactive, phân biệt rõ mô hình concurrency trước khi chọn cách truyền security context.

## 11. Ranh giới bảo mật: propagation không phải authorization

### 11.1. SecurityContext hiện tại có thể là anonymous

Trên một số filter chain, `SecurityContextHolder.getContext().getAuthentication()` có thể là `AnonymousAuthenticationToken` thay vì null. **Đừng xem `authentication != null` là bằng chứng người dùng thật đã đăng nhập**.

Khi cần phân quyền, dùng cơ chế `AuthorizationManager`, `hasAuthority`, `@PreAuthorize` hoặc authentication trust resolver của Spring Security theo cấu hình thực. `isAuthenticated()` trên một số loại Authentication cũng có ý nghĩa khác với “interactive user đã được xác minh”; test chính sách bảo mật ở tầng nghiệp vụ thay vì dùng mỗi `getName()`.

### 11.2. Context cũ vẫn là context cũ

Ví dụ user gửi task lúc 10:00, sau đó logout hoặc mất quyền trước khi task chạy lúc 10:30. Việc wrap `SecurityContext` **không tự revalidate** session, password, role trong database hoặc access token tại thời điểm chạy. Nếu job thay đổi dữ liệu hoặc gọi dịch vụ quan trọng sau một khoảng chờ, phải định nghĩa cách kiểm tra quyền **tại thời điểm thực thi**, deadline và cơ chế hủy.

Đối với background jobs dài hạn, nên dùng `jobId`, `subjectId`, `tenantId` đã kiểm tra và một execution policy cụ thể thay vì giữ object `SecurityContext` trong queue bền vững. Tránh serialize Authentication với credentials và nhét vào message broker.

### 11.3. Không truyền context của một user sang user khác

Một pool dùng chung được phép phục vụ nhiều người gọi, nhưng mỗi task phải capture context **đúng caller**. Nếu bạn tạo singleton:

```java
SecurityContext adminContext = ...; // demo: context đặc quyền
Runnable wrapped = new DelegatingSecurityContextRunnable(task, adminContext);
```

thì mọi lần gọi `wrapped.run()` đều dùng **adminContext**, dù user nào đưa task vào hàng đợi. Đoạn này cố tình **không phải Java có thể chạy độc lập**: nó minh họa anti-pattern cần tránh trong multi-tenant/multi-user application. Không dùng principal đặc quyền tĩnh để “sửa” lỗi null context.

### 11.4. Không giữ request-scoped objects tùy tiện

`HttpServletRequest`, transaction, Hibernate session, `RequestContextHolder`, MDC logging, tracing baggage và locale có vòng đời/transport khác với `SecurityContext`. Propagation security không đảm bảo các đối tượng trên còn hợp lệ khi task chạy.

Nếu task cần dữ liệu của request, chỉ trích xuất các giá trị bất biến và tối thiểu cần thiết, áp dụng phân quyền trước và tại điểm sử dụng, rồi đưa chúng vào task như tham số. Không giữ reference tới request hoặc response để dùng sau khi kết thúc HTTP request.

## 12. Bảng lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra và xử lý |
| --- | --- | --- |
| Request thread có user, worker có `authentication == null` | `ThreadLocal` không truyền qua Executor | Bọc task bằng DelegatingSecurityContextRunnable/Callable hoặc executor thích hợp |
| Task đầu tiên đúng user nhưng task sau sai user | Worker giữ context cũ hoặc wrapper tái sử dụng sai | Kiểm tra cleanup, wrapper mới theo mỗi caller, test một pool nhiều user |
| `@Async` method không thấy principal | Executor chưa bọc hoặc proxy `@Async` không được áp dụng | Dùng `DelegatingSecurityContextAsyncTaskExecutor`, `@EnableAsync`, gọi qua bean proxy |
| Context vẫn sai sau khi thêm wrapper | Wrapper được khởi tạo ở startup hoặc thread khác không có Authentication | Xác minh **thời điểm tạo wrapper/capture**, không chỉ thời điểm submit |
| Tất cả task luôn chạy dưới một user | Constructor fixed-context được dùng cho pool nhiều user | Chuyển sang capture theo submit/caller, loại fixed service principal trái phép |
| `Callable` ném lỗi khi `.get()` | Delegate ném exception, Future bọc trong `ExecutionException` | Đọc `getCause()`; xác minh wrapper cleanup ở finally |
| Worker sau task vẫn có `alice` | Code tự setContext nhưng không khôi phục, hoặc task không qua wrapper | Dùng wrapper chuẩn và test workerAfter; xem wrapper lồng nhau |
| `CompletableFuture` stage sau mất user | Stage chuyển sang common pool hoặc executor không bọc | Cung cấp wrapped Executor cho **từng async stage** cần context |
| Mất authentication sau logout nhưng job vẫn có user | Job đã capture context cũ trước khi logout | Phân quyền lại khi job chạy, timeout/revocation theo yêu cầu |
| Có Authentication nhưng quyền bị từ chối | Principal anonymous, thiếu GrantedAuthority hoặc policy khác | Kiểm tra authentication thật và policy, không cấp thêm quyền bằng wrapper |
| `hasAuthority` trong worker không được áp dụng | Chỉ đọc principal, không đi qua guard bảo mật | Đặt method/authorization guard ở service thực thi |
| Thread pool rò rỉ dữ liệu giữa tenant | Context cũ, shared mutable context, hoặc không check tenant | Bọc theo caller, restore context, xác minh tenant trên từng resource |
| Spring MVC `Callable` làm việc nhưng custom executor không | MVC có integration riêng, executor tự quản không có | Đánh giá từng async boundary và chọn wrapper phù hợp |
| Dùng `MODE_INHERITABLETHREADLOCAL` nhưng vẫn lỗi | Thread pool tái sử dụng luồng cũ | Không dùng chiến lược đó để thay propagation theo task |
| Muốn truyền SecurityContext sang một service khác qua HTTP | `ThreadLocal` chỉ ở trong JVM | Dùng cơ chế authentication/token delegation qua network, không serialize context |

### 12.1. Gợi ý quan sát log an toàn

Khi debug trong môi trường kiểm soát, log tối thiểu:

- Thread name, task ID và correlation ID.
- Loại Authentication (hoặc **tên principal không nhạy cảm** đã được policy cho phép log).
- Trạng thái authorized/denied và tên policy.
- Thời điểm capture, submit, execute, finish.
- Có context được restore/clear sau task không (test hoặc debug-only).

Không log raw password, Bearer token, session cookie, private key hoặc credentials trong `Authentication`. Đừng in toàn bộ object `SecurityContext` ra centralized log.

## 13. Checklist triển khai an toàn

- [ ] Xác định chính xác ranh giới luồng: servlet request → executor, `@Async`, `CompletableFuture` hay Spring MVC async.
- [ ] Với task đơn lẻ, chọn `DelegatingSecurityContextRunnable` hoặc `DelegatingSecurityContextCallable` phù hợp kiểu trả về.
- [ ] Capture context **đúng caller** khi tạo wrapper, hoặc dùng context tường minh chỉ khi có chính sách rõ ràng.
- [ ] Với nhiều task, dùng `DelegatingSecurityContextExecutor(Service)` hoặc `DelegatingSecurityContextAsyncTaskExecutor`; tránh viết lại logic ThreadLocal.
- [ ] Bảo đảm wrapper khôi phục context cũ hoặc clear khi task xong, **kể cả khi exception**.
- [ ] Test nhiều user trên cùng worker pool, test task không bọc sau đó không thấy Authentication cũ.
- [ ] Không dùng `MODE_GLOBAL` hoặc `MODE_INHERITABLETHREADLOCAL` như giải pháp mặc định cho web app đa user.
- [ ] Không coi context propagation thay thế authorization, CSRF, token validation hoặc kiểm tra tenant/resource.
- [ ] Với job chạy trễ, có chính sách TTL/timeout và kiểm tra lại quyền ở thời điểm execution.
- [ ] Không giữ request/transaction/MDC bằng suy luận từ SecurityContext propagation; dùng cơ chế riêng.
- [ ] Không truyền SecurityContext qua network hoặc message broker như một credential có thể tái sử dụng.
- [ ] Tách rõ Spring Security Servlet với Reactor/WebFlux khi thiết kế async pipeline.

**Kết luận:** `DelegatingSecurityContextRunnable` và `DelegatingSecurityContextCallable` là **task-level adapters** giúp thiết lập SecurityContext của caller trong thread chạy công việc và **dọn/khôi phục** trạng thái để thread pool không rò quyền. Khi nhiều task cần cơ chế này, bọc executor thay vì tự bọc từng task; khi dùng `@Async` hoặc các async stages, kiểm tra đúng executor và thời điểm capture. Việc có Authentication ở worker **không** tự chứng minh người đó vẫn được phép làm một hành động nhạy cảm khi tác vụ thực thi: xác thực, phân quyền và vòng đời phiên vẫn phải được kiểm soát riêng.
