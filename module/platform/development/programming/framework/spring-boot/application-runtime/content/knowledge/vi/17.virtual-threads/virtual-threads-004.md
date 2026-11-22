# Phân biệt bật hỗ trợ Boot với tự chuyển mọi tác vụ trong ứng dụng

**`spring.threads.virtual.enabled=true` không phải công tắc biến toàn bộ thread của một ứng dụng Java thành virtual thread.** Đây là tùy chọn để **Spring Boot sử dụng luồng ảo tại những điểm tích hợp mà Spring Boot tự cấu hình hoặc hỗ trợ**, khi chạy trên **Java 21 trở lên**. Những đoạn mã tự tạo `Thread`, `ExecutorService`, `ThreadPoolExecutor`, `CompletableFuture` hay thread do thư viện ngoài quản lý **không tự được viết lại** chỉ vì thuộc tính này xuất hiện trong `application.properties`.

Bài học thuộc module **Spring Boot Application Runtime**, nhóm **Luồng ảo**, dùng **Spring Boot 3.3.x / Spring Framework 6.1 / Java 21**. Mục tiêu không phải khuyên chuyển mọi tác vụ sang virtual threads, mà là xác định **tác vụ nào đang chạy ở đâu**, kiểm chứng bằng `Thread.currentThread().isVirtual()`, rồi chọn hướng thay đổi thích hợp.

Sau bài này, bạn cần có khả năng:

- Giải thích virtual thread khác platform thread ở điểm nào, và vì sao chúng phù hợp nhất với nhiều tác vụ **đang chờ I/O**.
- Biết `spring.threads.virtual.enabled` ảnh hưởng đến executor, scheduler và những tích hợp web tương ứng của Spring Boot 3.3.
- Biết `@Async` không tự hoạt động nếu thiếu `@EnableAsync` và những cuộc gọi không đi qua Spring proxy có thể không được chuyển sang executor.
- Chỉ ra code tự tạo pool, `new Thread`, `CompletableFuture.supplyAsync` hay thư viện tự quản lý thread **không được tự động di chuyển**.
- Tự đo bằng `isVirtual()` thay vì đoán từ tên thread, cấu hình hoặc cảm giác hiệu năng.
- Hiểu rủi ro của `@Scheduled(fixedDelay=...)`, daemon threads, pinning trên Java 21, quá tải tài nguyên ngoài và cách kiểm thử trước production.

## 1. Virtual thread là một loại `Thread`, không phải chế độ toàn cục của JVM

Từ Java 21, virtual threads là một phần chính thức của nền tảng Java, theo **JEP 444**. Cả platform thread và virtual thread đều là `java.lang.Thread`, đều thực thi Java code, có stack trace và có thể sử dụng các cơ chế đồng bộ thích hợp.

| Đặc điểm | Platform thread | Virtual thread |
| --- | --- | --- |
| Liên hệ với OS thread | Thường gắn với một OS thread trong suốt vòng đời | Được JVM lập lịch trên các carrier platform threads |
| Chi phí khi có nhiều tác vụ chờ I/O | OS thread bị giữ trong thời gian chờ | Virtual thread có thể tạm ngắt, nhường carrier cho công việc khác |
| Số lượng thường thích hợp | Giới hạn bởi số OS threads và tài nguyên hệ thống | Có thể tạo số lượng lớn hơn nhiều cho tác vụ phù hợp |
| Cách tạo trong Java 21 | `new Thread(...)`, `Thread.ofPlatform()`, thread pool truyền thống | `Thread.ofVirtual()`, `Executors.newVirtualThreadPerTaskExecutor()` |
| `Thread.currentThread().isVirtual()` | `false` | `true` |
| Thời gian thực thi CPU-bound | Không được virtual threads tự làm tăng tốc | Không được virtual threads tự làm tăng tốc |

Virtual threads có thể cải thiện **khả năng phục vụ nhiều tác vụ đồng thời đang chờ** (ví dụ gọi HTTP, database hoặc socket theo API blocking), chứ **không làm một phép tính CPU nặng chạy nhanh hơn**. Chúng cũng không xóa giới hạn của database connection pool, remote API rate limit, bộ nhớ hay tài nguyên hệ thống.

### Thử bằng Java 21 thuần, không cần Spring

Tạo file `ThreadKinds.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ThreadKinds {
    public static void main(String[] args) throws Exception {
        System.out.println(
                "mainVirtual=" + Thread.currentThread().isVirtual());

        try (ExecutorService fixed = Executors.newFixedThreadPool(1);
             ExecutorService virtual = Executors.newVirtualThreadPerTaskExecutor()) {

            boolean fixedResult = fixed.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            boolean virtualResult = virtual.submit(
                    () -> Thread.currentThread().isVirtual()).get();

            System.out.println("fixedPoolVirtual=" + fixedResult);
            System.out.println("explicitVirtual=" + virtualResult);
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 21+**:

~~~bash
javac ThreadKinds.java
java ThreadKinds
~~~

Các dòng do chương trình in là:

~~~text
mainVirtual=false
fixedPoolVirtual=false
explicitVirtual=true
~~~

Không có Spring Boot, không có property nào và vẫn tạo được virtual thread. Đây là **tính năng Java**, không phải thứ chỉ xuất hiện khi Spring Boot bật hỗ trợ. Ngược lại, một `newFixedThreadPool` mặc định tiếp tục dùng platform threads nếu bạn không chủ động đổi cách tạo executor.

## 2. `spring.threads.virtual.enabled` thực sự biểu thị điều gì?

Trong Spring Boot 3.3, cấu hình:

~~~properties
spring.threads.virtual.enabled=true
~~~

hoặc:

~~~yaml
spring:
  threads:
    virtual:
      enabled: true
~~~

yêu cầu Spring Boot sử dụng hỗ trợ virtual threads **ở các phần tích hợp liên quan** khi ứng dụng chạy với **Java 21 trở lên**.

Điều kiện phải được tách rõ:

1. **JVM:** chạy thực tế bằng Java 21+; không chỉ khai báo `sourceCompatibility` hoặc `toolchain` rồi chạy production trên JVM cũ.
2. **Spring Boot:** bản có hỗ trợ virtual threads, ví dụ Spring Boot 3.3.
3. **Tích hợp:** thành phần thực sự sử dụng executor/scheduler/web-server integration được Boot cấu hình; không bị thay bằng executor riêng không tương thích với mục tiêu.
4. **Đường gọi:** code thực sự đi qua cơ chế đó. Một phương thức đồng bộ gọi trực tiếp không tự trở thành task bất đồng bộ.

Cấu hình **không** có ý nghĩa như sau:

~~~text
spring.threads.virtual.enabled=true
    X  Thay toàn bộ new Thread(...) trong source
    X  Thay mọi Executors.newFixedThreadPool(...)
    X  Chuyển mọi CompletableFuture.supplyAsync(...) sang virtual
    X  Buộc mọi thư viện bên thứ ba dùng virtual threads
    X  Chuyển mọi CPU-bound loop sang virtual
    X  Biến tất cả Netty event-loop threads thành virtual
    X  Bảo đảm mọi method được gọi sau run() đều chạy virtual
~~~

Cần đọc code và cấu hình executor thật để biết task được phân phối ở đâu.

## 3. Bảng phạm vi: phần nào Boot hỗ trợ, phần nào cần xử lý riêng?

Bảng này xét **Spring Boot 3.3** với JDK 21+, không tự áp dụng nguyên trạng cho mọi phiên bản Boot hoặc thư viện.

| Đường thực thi | Bật property có thể làm gì? | Điều kiện hoặc giới hạn |
| --- | --- | --- |
| HTTP request trên **embedded Tomcat/Jetty** do Boot quản lý | Có tích hợp dùng virtual threads cho xử lý request | Phụ thuộc server thực tế và việc không thay thế cấu hình executor theo cách riêng |
| `@Async` qua Spring async infrastructure | Auto-config `AsyncTaskExecutor` dùng `SimpleAsyncTaskExecutor` với virtual threads | Cần `@EnableAsync` và lời gọi đi qua Spring proxy; custom executor có thể override |
| Spring MVC asynchronous request processing | Dùng Boot-managed `applicationTaskExecutor` phù hợp | Không đồng nghĩa mọi controller được chuyển sang task khác |
| Spring for GraphQL `Callable` async | Có thể sử dụng auto-configured executor | Chỉ đường xử lý thực sự qua integration |
| Spring WebFlux **blocking execution support** | Có thể dùng Boot task executor khi chuyển công việc blocking sang executor | **Không** chuyển mặc định Reactor Netty event-loop threads thành virtual |
| `@Scheduled` với scheduler auto-configured | Dùng `SimpleAsyncTaskScheduler` hỗ trợ virtual threads | Cần `@EnableScheduling`; fixed-delay có ngoại lệ về scheduler thread |
| `Executors.newFixedThreadPool(...)` tự viết | **Không tự đổi** | Muốn virtual phải đổi executor hoặc đường phân phối rõ ràng |
| `new Thread(...)` hoặc `Thread.ofPlatform()` | **Không tự đổi** | Đây là platform thread nếu tạo theo API platform |
| `Executors.newVirtualThreadPerTaskExecutor()` | Vẫn tạo virtual threads kể cả khi property Boot là `false` | Đây là quyết định Java của ứng dụng |
| `CompletableFuture.supplyAsync(...)` không truyền executor | **Không tự đổi sang Boot executor** | Mặc định dùng `ForkJoinPool.commonPool()` hoặc cơ chế fallback của JDK |
| `@Async("legacyExecutor")` | Dùng executor tên `legacyExecutor` | Nếu executor này là platform pool thì task vẫn platform |
| Reactor `publishOn`/`subscribeOn` với scheduler mặc định | **Không tự viết lại** | Cần xác định scheduler được chọn, không chỉ nhìn property Boot |
| Thread pool do SDK/client/broker riêng quản lý | Không thể suy ra tự đổi | Kiểm tra tài liệu/tích hợp tương ứng của từng SDK |

**Nhấn mạnh:** tích hợp là tính năng cụ thể. Câu “Boot hỗ trợ virtual threads” không chứng minh “tất cả thread của ứng dụng đều virtual”.

## 4. Auto-configured task executor: điểm hỗ trợ quan trọng nhất

Theo tài liệu Spring Boot 3.3 về task execution, **khi không có bean `Executor` do ứng dụng tự cung cấp**, Boot tự cấu hình một `AsyncTaskExecutor`:

~~~text
Java 21+, spring.threads.virtual.enabled=false
    -> ThreadPoolTaskExecutor (platform thread pool)

Java 21+, spring.threads.virtual.enabled=true
    -> SimpleAsyncTaskExecutor dùng virtual threads
~~~

`SimpleAsyncTaskExecutor` theo cấu hình này là kiểu **task-per-thread**, không phải pool worker platform truyền thống. Khi chạy bằng virtual threads, các thuộc tính cấu hình kích thước thread pool như `spring.task.execution.pool.core-size`, `max-size`, `queue-capacity` **không còn ý nghĩa cho executor virtual được Boot tự tạo**. Điều đó **không** có nghĩa mọi custom pool trong ứng dụng bị vô hiệu hóa.

Một số tích hợp mà `applicationTaskExecutor` có thể phục vụ trong Spring Boot 3.3:

- Chạy phương thức `@Async` khi Spring async support được bật và không có executor khác có ưu tiên.
- Spring MVC asynchronous request processing.
- Một số đường bất đồng bộ của Spring for GraphQL.
- Hỗ trợ chuyển việc blocking sang executor trong Spring WebFlux.

### Tại sao custom `Executor` rất quan trọng?

Nếu bạn khai báo một `Executor` bean riêng:

~~~java
@Configuration
public class LegacyExecutorConfig {
    @Bean(destroyMethod = "shutdown")
    ExecutorService legacyExecutor() {
        return Executors.newFixedThreadPool(8);
    }
}
~~~

đoạn **minh họa** này cần import `@Configuration`, `@Bean`, `ExecutorService`, `Executors` và đặt trong dự án Spring. Nó có thể làm auto-configuration của executor mặc định Boot **lùi lại**. Khi đó, tác vụ `@Async` có thể sử dụng executor custom còn tồn tại theo quy tắc lựa chọn executor của Spring, thay vì được tự động chuyển sang virtual.

Một số quy tắc của Spring Boot 3.3:

- Khi có một custom `Executor` trong context, việc lựa chọn executor cho `@EnableAsync` và GraphQL có thể đi theo custom bean.
- Spring MVC/WebFlux cần executor phù hợp kiểu `AsyncTaskExecutor` và tên `applicationTaskExecutor` cho các tích hợp tương ứng.
- Nếu có nhiều `Executor` bean, tên `taskExecutor` và `applicationTaskExecutor` cùng `AsyncConfigurer` là các điểm cần kiểm tra theo mục đích.
- `@Async("legacyExecutor")` chỉ định rõ executor custom theo tên hoặc qualifier, nên **không** có chuyện Boot tự bỏ qua lựa chọn đó.

**Không sao chép mặc định hướng dẫn về `spring.task.execution.mode=force` từ phiên bản Spring Boot mới sang 3.3 khi chưa đối chiếu.** Bài này cố định ở hành vi của Spring Boot 3.3; với version khác phải đọc lại tài liệu chính xác của version đó.

### `@Async` chỉ tác dụng khi Spring quản lý lời gọi

~~~java
@Service
public class AsyncService {

    @Async
    public CompletableFuture<Boolean> checkThread() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().isVirtual());
    }
}
~~~

Đây là **đoạn class minh họa**, cần import `@Service`, `@Async` và `CompletableFuture`, cùng `@EnableAsync` trong cấu hình Spring. Muốn tác vụ chạy trong executor:

- Phương thức `@Async` nên được gọi **qua bean proxy mà Spring cấp**, ví dụ controller A gọi bean service B.
- Lời gọi nội bộ `this.checkThread()` trong chính cùng bean có thể **bỏ qua proxy**; method chạy đồng bộ trên thread hiện tại.
- Nếu method có `@Async("someExecutor")`, hãy kiểm tra executor đã chọn, không chỉ property toàn cục.
- Gắn `@Async` mà không bật `@EnableAsync` trong dự án Spring thông thường không đảm bảo Spring kích hoạt async advice.

Đừng nhầm: một method async được kích hoạt và một task sử dụng virtual thread là **hai vấn đề khác nhau**. Chúng liên quan qua executor được chọn nhưng không phải một thao tác duy nhất.

## 5. Scheduling: hỗ trợ thật, nhưng không phải mọi loại lịch giống nhau

Nếu bật scheduling (thường bằng `@EnableScheduling`), Spring Boot có thể tự tạo scheduler để thực thi `@Scheduled`:

~~~text
Virtual threads tắt:
  ThreadPoolTaskScheduler (pool-backed)

Virtual threads bật và điều kiện phù hợp:
  SimpleAsyncTaskScheduler (virtual-thread capable)
~~~

`SimpleAsyncTaskScheduler` hoạt động theo mô hình một scheduler thread điều phối và có thể tạo thread riêng cho mỗi lần thực thi. **Ngoại lệ quan trọng của Spring Framework 6.1:** những tác vụ `@Scheduled(fixedDelay=...)` dùng **một scheduler thread** để giữ ngữ nghĩa fixed-delay, nên có thể không có tính song song như mong đợi. Tác vụ dùng `fixedRate` hoặc `cron` thường hợp hơn với mô hình scheduler virtual-thread-per-task, nhưng vẫn phải kiểm tra nguy cơ chạy chồng và tải thực tế.

Một ví dụ minh họa đặt trong bean:

~~~java
@Component
class TimedJobs {
    @Scheduled(fixedRate = 5000)
    void poll() {
        System.out.println(
                "scheduledVirtual=" + Thread.currentThread().isVirtual());
    }
}
~~~

Đoạn trên cần import `@Component`, `@Scheduled` và cấu hình `@EnableScheduling`. **Không dự đoán số dòng hay thời điểm stdout** vì lịch chạy phụ thuộc thời điểm khởi động và dừng ứng dụng.

Khi bật virtual threads:

- `spring.task.scheduling.pool.size` và các thuộc tính liên quan pool không được dùng để điều khiển `SimpleAsyncTaskScheduler` như `ThreadPoolTaskScheduler`.
- Nếu tự định nghĩa `TaskScheduler` hoặc `SchedulingConfigurer` chọn scheduler riêng, kết quả phụ thuộc chính scheduler ấy.
- Một `@Scheduled` không được Spring quản lý như bean/scheduler hợp lệ sẽ không tự bắt đầu chỉ vì bật property.
- Với tác vụ có nguy cơ chạy chồng hoặc truy cập cùng tài nguyên, cần giới hạn concurrency và kiểm soát tính đúng đắn.

### Virtual threads là daemon: vấn đề ứng dụng chỉ có scheduler

Java virtual threads là **daemon threads**. Nếu tiến trình **không còn non-daemon thread**, JVM có thể kết thúc dù bạn nghĩ “vẫn còn scheduled jobs”. Spring Boot 3.3 khuyến nghị khi cần giữ JVM chạy:

~~~properties
spring.threads.virtual.enabled=true
spring.main.keep-alive=true
~~~

`spring.main.keep-alive=true` giúp giữ tiến trình sống ngay cả khi các công việc còn lại là daemon/virtual threads. Điều này đặc biệt quan trọng với **ứng dụng CLI chạy `@Scheduled` mà không có web server hay công việc non-daemon khác**.

Trong ứng dụng web, vòng đời server có thể có cơ chế giữ tiến trình chạy; không nên suy luận “mỗi khi bật virtual threads JVM chắc chắn thoát”. Hãy kiểm tra theo kiểu ứng dụng và server thực tế.

## 6. HTTP request: Tomcat/Jetty khác WebFlux event loop

Ở Spring Boot 3.3 trên Java 21+, embedded **Tomcat/Jetty** được Boot hỗ trợ cấu hình để xử lý HTTP request bằng virtual threads khi bật property và dùng cấu hình web-server tương ứng. Một method trong MVC controller xử lý request đồng bộ có thể vì vậy được gọi trên virtual thread.

Điều này **không có nghĩa**:

- Thread của `main` thành virtual.
- Mọi thread nội bộ của Tomcat, connector, acceptor, JVM GC và các SDK đều virtual.
- Một controller tự gọi một executor custom sẽ khiến các task custom cũng virtual.
- Reactor Netty event loops của ứng dụng WebFlux tự động biến thành virtual threads.
- Mọi HTTP client trong ứng dụng đổi executor hoặc protocol.

Với Spring WebFlux, mô hình event loop/non-blocking vẫn tồn tại. Tích hợp executor virtual của Boot có thể có vai trò với **blocking execution support** khi đường xử lý được chuyển đúng cách, chứ không phải công tắc biến toàn bộ reactive pipeline sang mô hình một virtual thread trên mỗi operator.

Một bảng phân biệt hữu ích:

| Tình huống | Điều phải kiểm tra |
| --- | --- |
| `@RestController` với Spring MVC và embedded Tomcat | `Thread.currentThread().isVirtual()` trong request handler |
| `@Async` được controller gọi | Thread bên trong phương thức async, và executor thực dùng |
| Controller gọi `Executors.newFixedThreadPool` | Thread bên trong pool, không phải thread của controller |
| Reactive pipeline có `publishOn(Schedulers.boundedElastic())` | Scheduler thực tế của Reactor/version/cấu hình, không suy từ cờ Boot |
| Thư viện HTTP client riêng có thread pool | Executor và tài liệu của client |

**Một request có thể đi qua cả virtual và platform threads**, phụ thuộc nơi công việc được chuyển tiếp. Gắn nhãn toàn bộ request là “ảo” chỉ vì điểm vào controller là virtual có thể dẫn tới hiểu sai.

## 7. Ví dụ Spring Boot 3.3 chạy được: bốn cách thực thi, bốn kết quả

Ví dụ này dùng **Spring Boot 3.3.13 + Java 21 + Gradle**, có embedded Tomcat từ `spring-boot-starter-web`. Endpoint `GET /threads` đo trực tiếp:

1. **`requestVirtual`:** thread đang chạy controller (do Tomcat phục vụ).
2. **`asyncVirtual`:** thread chạy một phương thức `@Async` thông qua bean Spring khác.
3. **`legacyPoolVirtual`:** thread của pool tự tạo `Executors.newFixedThreadPool(1)`.
4. **`explicitVirtual`:** thread được tạo tường minh bằng `Thread.ofVirtual()`.

Đây là demo kiểm chứng hành vi, không phải kiến trúc production: đừng tạo thread mới trên mỗi request ngoài mục đích thí nghiệm, và đừng dựa vào `Future.get()` đồng bộ để xây dựng hệ thống tải cao mà không xem xét timeout/backpressure.

### 7.1. Cấu trúc dự án

~~~text
boot-virtual-scope-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/virtualscope/
    │   ├── VirtualScopeApplication.java
    │   ├── AsyncProbe.java
    │   └── ThreadProbeController.java
    └── resources/application.properties
~~~

### 7.2. Tệp `settings.gradle`

~~~groovy
rootProject.name = 'boot-virtual-scope-demo'
~~~

### 7.3. Tệp `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    // Gradle native BOM quản lý phiên bản tương thích của starter.
    implementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Lưu ý **Java 21**, không phải chỉ Java 17 như nhiều ví dụ Spring Boot thông thường. Dùng Gradle tương thích Spring Boot 3.3 và một JDK 21+ để **chạy JVM thật**. Gradle toolchain dùng compiler Java 21, nhưng `java -version` ở runtime cũng phải cho thấy Java 21+.

BOM đã được khai báo nên `spring-boot-starter-web` không cần một version riêng. Đừng bỏ BOM rồi nghĩ plugin `org.springframework.boot` đơn độc chắc chắn tự quản lý mọi phiên bản dependency.

### 7.4. `application.properties`

~~~properties
server.port=8080
spring.threads.virtual.enabled=true
~~~

Đây là giá trị ứng dụng mặc định trong demo. Để chạy so sánh, ta sẽ override bằng đối số `--spring.threads.virtual.enabled=false` mà **không sửa code**.

### 7.5. Lớp ứng dụng và `@EnableAsync`

`src/main/java/com/example/virtualscope/VirtualScopeApplication.java`:

~~~java
package com.example.virtualscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class VirtualScopeApplication {

    public static void main(String[] args) {
        System.out.println(
                "MAIN virtual=" + Thread.currentThread().isVirtual());
        SpringApplication.run(VirtualScopeApplication.class, args);
    }
}
~~~

**Vì sao có `@EnableAsync`?** Vì đây là điều kiện kích hoạt việc thực thi các phương thức `@Async` qua Spring async infrastructure. Chỉ bật virtual-thread property **không tự biến mọi method thông thường thành async**.

Dòng `MAIN virtual=false` cho thấy `main` vẫn là platform thread dù Boot sắp dùng virtual threads cho các integration sau đó.

### 7.6. Service sử dụng `@Async`

`src/main/java/com/example/virtualscope/AsyncProbe.java`:

~~~java
package com.example.virtualscope;

import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncProbe {

    @Async
    public CompletableFuture<Boolean> inspect() {
        boolean isVirtual = Thread.currentThread().isVirtual();
        return CompletableFuture.completedFuture(isVirtual);
    }
}
~~~

Hàm `inspect()` được Spring AOP/proxy đưa vào executor phù hợp khi được gọi từ một bean khác. Nó ghi trạng thái của **thread đang chạy body method**, không phải thread của caller. `CompletableFuture.completedFuture(...)` ở đây bọc giá trị đã đo bên trong method; không có `CompletableFuture.supplyAsync` không rõ executor.

Không gọi `new AsyncProbe().inspect()` hoặc `this.inspect()` rồi mong có async: các cách gọi đó không đi qua Spring proxy.

### 7.7. Controller so sánh các nguồn thread

`src/main/java/com/example/virtualscope/ThreadProbeController.java`:

~~~java
package com.example.virtualscope;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

import jakarta.annotation.PreDestroy;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ThreadProbeController {

    private final AsyncProbe asyncProbe;

    // Đây chỉ là một field của controller, KHÔNG phải @Bean Executor.
    // Nó được giữ cố định là platform-thread pool trong cả hai mode.
    private final ExecutorService legacyPool =
            Executors.newFixedThreadPool(1);

    public ThreadProbeController(AsyncProbe asyncProbe) {
        this.asyncProbe = asyncProbe;
    }

    @GetMapping("/threads")
    public Map<String, Boolean> check() throws Exception {
        boolean requestVirtual = Thread.currentThread().isVirtual();

        // Gọi qua bean/proxy, vì AsyncProbe là @Service riêng.
        boolean asyncVirtual = asyncProbe.inspect()
                .get(5, TimeUnit.SECONDS);

        Future<Boolean> legacyFuture = legacyPool.submit(
                () -> Thread.currentThread().isVirtual());
        boolean legacyPoolVirtual = legacyFuture.get(5, TimeUnit.SECONDS);

        AtomicBoolean explicitResult = new AtomicBoolean();
        Thread explicit = Thread.ofVirtual().start(() ->
                explicitResult.set(Thread.currentThread().isVirtual()));
        explicit.join();

        Map<String, Boolean> result = new LinkedHashMap<>();
        result.put("requestVirtual", requestVirtual);
        result.put("asyncVirtual", asyncVirtual);
        result.put("legacyPoolVirtual", legacyPoolVirtual);
        result.put("explicitVirtual", explicitResult.get());
        return result;
    }

    @PreDestroy
    public void closePool() {
        legacyPool.shutdownNow();
    }
}
~~~

**Cần hiểu đúng field `legacyPool`:** vì executor được tạo làm **field riêng**, không đăng ký thành `@Bean Executor`, nên nó **không làm Boot auto-configured task executor tự lùi lại**. Đây là chủ ý thiết kế demo để giữ nguyên executor của `@Async`, nhưng vẫn quan sát được một pool do code ứng dụng tự quản lý.

Tạo platform thread pool cố định chỉ để chứng minh sự khác biệt. Trong ứng dụng thật, cần quản lý kích thước pool, queue, shutdown và backpressure dựa trên tải. Không tạo một pool riêng cho mỗi request.

### 7.8. Chạy khi bật virtual threads

Với Gradle Wrapper của dự án:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chỉ có Gradle cài sẵn, có thể dùng `gradle bootRun`.

Trong terminal khác:

~~~bash
curl -sS http://localhost:8080/threads
~~~

Với **JDK 21+**, Spring Boot 3.3.13, embedded Tomcat và **không có custom `Executor` bean làm đổi auto-configuration**, JSON dự kiến là:

~~~json
{
  "requestVirtual": true,
  "asyncVirtual": true,
  "legacyPoolVirtual": false,
  "explicitVirtual": true
}
~~~

Dữ liệu JSON có thể được in trên một dòng; thứ tự các key được chuẩn bị bằng `LinkedHashMap` để dễ đọc. Ngoài JSON, console server sẽ có log khởi động do Spring Boot và dòng:

~~~text
MAIN virtual=false
~~~

**Giải thích từng giá trị:**

- `requestVirtual=true`: Tomcat do Boot cấu hình xử lý request trên virtual thread trong môi trường demo đã nêu.
- `asyncVirtual=true`: `@Async` đi qua executor tự cấu hình đang dùng virtual threads.
- `legacyPoolVirtual=false`: `Executors.newFixedThreadPool(1)` do code tự tạo vẫn sử dụng platform thread.
- `explicitVirtual=true`: `Thread.ofVirtual()` tạo virtual thread **bất kể cờ Boot**.

### 7.9. Chạy lại cùng code với virtual threads tắt

Dừng server trước đó, rồi khởi động lại:

~~~bash
./gradlew bootRun --args="--spring.threads.virtual.enabled=false"
~~~

Trên PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.threads.virtual.enabled=false"
~~~

Gọi lại:

~~~bash
curl -sS http://localhost:8080/threads
~~~

Kết quả dự kiến trong điều kiện demo:

~~~json
{
  "requestVirtual": false,
  "asyncVirtual": false,
  "legacyPoolVirtual": false,
  "explicitVirtual": true
}
~~~

Khi property Boot bị tắt, controller Tomcat sử dụng platform request threads và auto-configured `@Async` executor sử dụng pool platform. Hai nguồn do ứng dụng tự quyết định **không đổi**: legacy pool vẫn platform và `Thread.ofVirtual()` vẫn virtual.

Đây chính là minh chứng:

> **Bật hỗ trợ của Boot thay đổi đường tích hợp được Boot quản lý, chứ không tự chuyển toàn bộ tác vụ hoặc tắt khả năng tự tạo virtual thread của Java.**

Nếu trong dự án thực tế thấy `asyncVirtual=false` dù đã bật cờ, đừng vội kết luận Spring Boot có lỗi. Hãy kiểm tra `@EnableAsync`, bean executor custom, `@Async("...")`, `AsyncConfigurer`, cách gọi qua proxy và runtime JDK.

### 7.10. Build JAR chạy trực tiếp

~~~bash
./gradlew clean bootJar
java -version
java -jar build/libs/boot-virtual-scope-demo-1.0.0.jar \
     --spring.threads.virtual.enabled=true
~~~

Tệp JAR nêu trên theo tên project/version mẫu; nếu Gradle cấu hình lại classifier hoặc tên artifact, hãy dùng tên build thực tế. Với JDK thấp hơn 21, API `Thread.ofVirtual()`/`Thread.isVirtual()` không phù hợp, nên **không dùng cùng project Java 21 trên runtime Java 17**.

## 8. Tự kiểm thử bằng JUnit và HTTP thay vì đoán

Bài thực hành có thể bổ sung `spring-boot-starter-test` vào `build.gradle`:

~~~groovy
dependencies {
    testImplementation platform(
            org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **phần cần ghép vào file build hiện có**; nếu `dependencies` đã tồn tại, **chỉ thêm hai dòng dependency vào block cũ**, không tạo hai block chỉ vì ví dụ trình bày riêng.

### Test bật virtual threads

Tệp `src/test/java/com/example/virtualscope/VirtualEnabledTest.java`:

~~~java
package com.example.virtualscope;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=true")
class VirtualEnabledTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void managedPathsUseVirtualAndLegacyPoolStaysPlatform() {
        Map<?, ?> body = rest.getForObject("/threads", Map.class);

        assertEquals(Boolean.TRUE, body.get("requestVirtual"));
        assertEquals(Boolean.TRUE, body.get("asyncVirtual"));
        assertEquals(Boolean.FALSE, body.get("legacyPoolVirtual"));
        assertEquals(Boolean.TRUE, body.get("explicitVirtual"));
    }
}
~~~

### Test tắt virtual threads

Tệp `src/test/java/com/example/virtualscope/VirtualDisabledTest.java`:

~~~java
package com.example.virtualscope;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = "spring.threads.virtual.enabled=false")
class VirtualDisabledTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void propertyOffDoesNotDisableExplicitVirtualThreads() {
        Map<?, ?> body = rest.getForObject("/threads", Map.class);

        assertEquals(Boolean.FALSE, body.get("requestVirtual"));
        assertEquals(Boolean.FALSE, body.get("asyncVirtual"));
        assertEquals(Boolean.FALSE, body.get("legacyPoolVirtual"));
        assertEquals(Boolean.TRUE, body.get("explicitVirtual"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Hai class test dùng hai thuộc tính khác nhau nên Spring Boot Test cần context tương ứng theo cấu hình. Chúng là **kiểm tra hành vi**, không phải benchmark throughput. Đừng suy đoán độ trễ từ thời gian Gradle test vì Gradle/JUnit/khởi tạo test context khác production.

Nếu dùng một server khác Tomcat, custom `Executor`, custom `TaskScheduler` hoặc cấu hình Boot khác, hãy điều chỉnh expected result theo **khả năng hỗ trợ thực tế**, không sao chép cứng JSON trên.

## 9. Tự chuyển các tác vụ ngoài Boot: những nơi thường bị bỏ sót

### `new Thread(...)`

~~~java
Thread worker = new Thread(() ->
        System.out.println(Thread.currentThread().isVirtual()));
worker.start();
worker.join();
~~~

Đây là đoạn minh họa bên trong method có `throws InterruptedException` hoặc xử lý tương ứng. Nó dùng platform thread theo cách tạo mặc định, không phụ thuộc `spring.threads.virtual.enabled`.

Muốn virtual tường minh:

~~~java
Thread worker = Thread.ofVirtual().start(() ->
        System.out.println(Thread.currentThread().isVirtual()));
worker.join();
~~~

Khi chạy Java 21, output của đoạn thứ hai là:

~~~text
true
~~~

Không phải vì Boot đã bật cờ, mà vì code gọi trực tiếp `Thread.ofVirtual()`.

### `ExecutorService` tự tạo

~~~java
ExecutorService oldPool = Executors.newFixedThreadPool(16);
~~~

Dòng trên tạo platform thread pool truyền thống. Cờ Boot không tự biến pool thành virtual. Nếu phù hợp mô hình công việc, có thể chủ động tạo:

~~~java
ExecutorService virtualExecutor =
        Executors.newVirtualThreadPerTaskExecutor();
~~~

Đoạn này là **một fragment**, không phải chương trình Java đầy đủ. Nếu code tạo executor, cần đóng nó đúng vòng đời: `try-with-resources` cho tác vụ cục bộ, hoặc `shutdown()`/`shutdownNow()` theo chính sách nếu tồn tại lâu dài.

Virtual thread executor **không phải thread pool cần đặt core/max-size như cũ**. Giới hạn lượng công việc đồng thời nên đặt theo **tài nguyên khan hiếm** như kết nối DB, số request downstream hoặc khả năng xử lý hàng đợi, không theo việc “chỉ tạo được N virtual thread”.

### `CompletableFuture.supplyAsync(...)`

~~~java
CompletableFuture<Boolean> result =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual());
~~~

Đoạn trên mặc định dùng common pool hoặc đường fallback do JDK quản lý, **không tự lấy Spring Boot `applicationTaskExecutor`**. Muốn kiểm soát executor, truyền rõ:

~~~java
CompletableFuture<Boolean> result =
        CompletableFuture.supplyAsync(
                () -> Thread.currentThread().isVirtual(),
                virtualExecutor);
~~~

`virtualExecutor` ở đây phải là `Executor` đã được tạo và quản lý. Nếu đây là `Executors.newVirtualThreadPerTaskExecutor()`, task chạy trên virtual thread. Nếu là pool cố định, task chạy trên platform thread.

Điều này cũng đúng với các API Java sử dụng executor mặc định hoặc nhận executor riêng: **phải xác định executor nguồn** mới nói chắc được loại thread.

### `@Async("someExecutor")`

~~~java
@Async("reportExecutor")
public CompletableFuture<String> generateReport() {
    return CompletableFuture.completedFuture("done");
}
~~~

Đây là fragment trong một Spring-managed bean. Nó yêu cầu dùng `reportExecutor` được chọn theo qualifier. Nếu `reportExecutor` là `ThreadPoolTaskExecutor` platform hoặc `ExecutorService` fixed pool, method tiếp tục chạy platform **dù Boot property đang bật**.

Chỉ đổi annotation `@Async` mà bỏ qua executor thực tế là chưa đủ để chuyển công việc.

### Reactor, Kafka, RabbitMQ, SDKs

Một số công nghệ có **tích hợp riêng** với Spring Boot virtual-thread support trong các phiên bản nhất định (ví dụ một số listener container). Nhưng điều đó **không cho phép kết luận mọi thread của một Kafka client, RabbitMQ client, Netty event loop, SDK HTTP hoặc thư viện xử lý file đều đổi loại**.

Với mỗi công nghệ cần:

1. Xác định bean/container factory và executor/scheduler thực được sử dụng.
2. Đọc tài liệu tương ứng **đúng phiên bản**.
3. Quan sát `Thread.currentThread().isVirtual()` trong callback quan trọng.
4. Đo tải và lỗi thực tế trước khi quyết định đổi cấu hình.

Không đưa giả định “virtual enabled tức là 100% threads virtual” vào dashboard hoặc tài liệu vận hành.

## 10. Phân biệt cách xử lý nhiều request với tự tạo tác vụ mới

Giả sử controller đồng bộ xử lý:

~~~java
@GetMapping("/report")
public String report() {
    return reportService.generate();
}
~~~

Khi Tomcat đang xử lý request trên virtual thread, lời gọi Java **đồng bộ** `reportService.generate()` thường chạy trên **cùng virtual thread đó** nếu không có điểm chuyển thread. Điều này **không tạo ra một virtual thread mới cho mỗi lời gọi phương thức**.

Ngược lại:

~~~java
@GetMapping("/report")
public CompletableFuture<String> report() {
    return reportService.generateAsync();
}
~~~

Nếu `generateAsync()` được xử lý bằng `@Async` proxy hoặc executor đúng, nó chạy trên **task thread của executor**, có thể là một virtual thread **khác**. Một request có thể sử dụng nhiều thread, còn một phương thức đồng bộ có thể chỉ là lời gọi cùng stack.

Đây là lý do cần đo tại **điểm code chạy thật**, không chỉ kiểm tra một thuộc tính `Environment`.

### Phân biệt thread name với thread type

Không nên viết:

~~~java
boolean virtual = Thread.currentThread().getName()
        .contains("virtual");
~~~

Tên thread có thể bị tùy chỉnh hoặc rỗng; đây không phải phép kiểm tra hợp đồng. Với Java 21, dùng:

~~~java
boolean virtual = Thread.currentThread().isVirtual();
~~~

Nếu muốn log phục vụ chẩn đoán, ghi cả `isVirtual()` và tên thread, cùng operation/trace ID. Tránh log quá nhiều lần trên luồng tải cao.

## 11. Khi bật virtual threads, điều gì có thể giảm hiệu năng?

Virtual threads phù hợp khi **nhiều tác vụ đồng thời bị chặn chờ I/O** mà vẫn muốn viết code theo kiểu blocking dễ đọc. Nhưng chúng **không làm CPU nhiều lõi hơn**, không thay đổi tốc độ đọc DB và không loại bỏ contention.

### CPU-bound work

Nếu 100 task cùng tính hash nặng hoặc mã hóa dữ liệu sử dụng hết CPU, tạo 100 virtual threads **không bảo đảm tổng thời gian ngắn hơn** so với dùng platform threads có kiểm soát. JVM vẫn lập lịch chúng trên số carrier threads và CPU thực có hạn.

### Downstream và connection pools

Ví dụ ứng dụng tạo được hàng nghìn virtual threads nhưng DB pool chỉ có 20 connections. Những task còn lại vẫn phải chờ connection. Nếu đồng thời tạo quá nhiều request xuống API giới hạn tốc độ, hệ thống có thể bị timeouts/rate limiting.

Vì vậy, không biến virtual threads thành lý do bỏ giới hạn **concurrency, queue, backpressure** và **timeout**. Giới hạn theo năng lực thật của downstream, không theo số virtual threads JVM có thể tạo.

### Pinning trên Java 21

Trong Java 21, một virtual thread có thể bị **pinned** vào carrier thread khi làm blocking operation trong vùng `synchronized` hoặc trong native/foreign code phù hợp. Khi đó carrier không được nhường để xử lý virtual thread khác, có thể làm giảm throughput nếu blocking xảy ra **thường xuyên và kéo dài**.

Ví dụ minh họa vấn đề:

~~~java
synchronized (lock) {
    blockingRemoteCall();
}
~~~

Đây là **mã mô tả**, giả định `lock` và `blockingRemoteCall()` đã tồn tại. Không phải mọi khối `synchronized` đều nguy hiểm: khóa ngắn bảo vệ state trong bộ nhớ thường không có vấn đề. Điều cần đo là **blocking kéo dài khi thread bị pinned**.

Với Java 21, có thể dùng:

~~~bash
java -Djdk.tracePinnedThreads=short -jar app.jar \
     --spring.threads.virtual.enabled=true
~~~

hoặc dùng **Java Flight Recorder (JFR)**, đặc biệt sự kiện `jdk.VirtualThreadPinned` khi được ghi. Đừng thay toàn bộ `synchronized` một cách máy móc. Chỉ cải thiện những đoạn thực sự gây pinning dài và thường xuyên, ví dụ xem xét `ReentrantLock` khi phù hợp hợp đồng đồng bộ.

**Lưu ý phiên bản:** cơ chế pinning đã thay đổi ở những JDK mới hơn. Bài tập đang cố định ở **Java 21**; không áp dụng từng kết luận về `synchronized` cho mọi JDK tương lai mà không kiểm tra.

## 12. ThreadLocal, context propagation và lỗi chức năng

Virtual threads vẫn hỗ trợ `ThreadLocal`. Nhưng khi có nhiều task threads ngắn hạn và sự chuyển tiếp giữa Spring MVC, `@Async`, executor, Reactor hoặc thư viện ngoài, dữ liệu gắn vào thread có thể **không tự được truyền sang một thread khác**.

Những dữ liệu cần kiểm tra:

- Logging MDC, trace ID, correlation ID.
- Spring Security `SecurityContext`.
- Request context, locale, tenant context.
- Transaction context vốn gắn với thread.
- Thư viện dùng `ThreadLocal` để cache đối tượng lớn hoặc giữ trạng thái lâu.

Đừng giả định `@Transactional` ở request thread tự kéo transaction sang một `@Async` task thread mới. Async tạo ranh giới thread, nên transaction/context propagation cần thiết kế rõ ràng.

`TaskDecorator` hoặc các cơ chế context propagation chuyên dụng có thể hữu ích, nhưng cách áp dụng khác nhau theo integration và version. **Virtual thread không tự giải quyết context propagation**, và ngược lại, không phải cứ dùng virtual thread là mất mọi thread-local; vấn đề chính là **ranh giới chuyển thread**.

### Vì sao không nên dùng `ThreadLocal` như cache vô hạn?

Với platform thread pool có ít worker sống lâu, lưu state lớn trong `ThreadLocal` vốn đã có rủi ro leak. Với virtual-thread-per-task, số lượng thread có thể cao hơn rất nhiều; tạo cache theo thread không phù hợp có thể làm allocation/memory tăng nhanh. Thiết kế cache theo phạm vi ứng dụng, request hoặc kho dữ liệu phù hợp, và đo footprint thực tế.

## 13. Phân biệt tối ưu hóa concurrency với tối ưu hóa latency

Một yêu cầu I/O mất 500 ms để nhận phản hồi từ remote service **không tự hoàn thành trong 5 ms** vì đang ở virtual thread. Lợi ích có thể là JVM không phải giữ một OS thread riêng suốt khoảng 500 ms chờ đó, giúp xử lý nhiều request đồng thời hơn trong điều kiện thích hợp.

Để quyết định bật property hoặc chuyển thêm task, đo:

| Chỉ số | Mục đích |
| --- | --- |
| Concurrent requests/throughput | Ứng dụng phục vụ thêm bao nhiêu công việc chờ I/O? |
| p50/p95/p99 latency | Tail latency có cải thiện hoặc suy giảm? |
| Error rate, timeouts | Downstream có bị quá tải không? |
| CPU utilization và carrier saturation | Công việc đã CPU-bound hay chưa? |
| Heap/RSS/GC | Nhiều task đồng thời có làm memory tăng? |
| Connection pool wait time | DB/HTTP client pool có thành nút thắt? |
| JFR virtual-thread pinning events | Có pinned blocking dài/thường xuyên? |
| Thread dump/metrics và `isVirtual()` | Đường code thật chạy trên loại thread nào? |
| Shutdown và unfinished work | Executor có đóng đúng, task có bị bỏ dở? |

### Thử nghiệm A/B

1. **Baseline:** Java 21, Spring Boot 3.3, `spring.threads.virtual.enabled=false`; giữ version, artifact và cấu hình nhất quán.
2. **Candidate:** chỉ bật `spring.threads.virtual.enabled=true`; kiểm tra framework executor/web-server và các custom executor thực tế.
3. **Mẫu workload:** chọn endpoint I/O-heavy, CPU-heavy, job scheduling và task dùng custom pool.
4. **Warm-up hợp lý:** tách cold startup/classloading ra khỏi phép đo tải ổn định.
5. **Giới hạn:** giữ cùng CPU, memory, DB connections, upstream rate limit, heap và loại môi trường.
6. **Đọc kết quả:** nếu throughput tăng nhưng p99/5xx hoặc memory tăng mạnh, không kết luận cấu hình tốt chỉ từ throughput.

**Không mặc định mọi task phải di chuyển.** Có thể giữ platform pool cho một nhóm CPU-heavy hoặc nhóm cần giới hạn concurrency rõ ràng, đồng thời dùng virtual threads cho I/O-heavy task qua executor phù hợp.

## 14. Quy trình rà soát từng luồng xử lý trong dự án thật

Trước khi bật trên production, lập bảng:

| Đường công việc | Ai tạo thread/executor? | Đã virtual? | Cần hành động? |
| --- | --- | --- | --- |
| Spring MVC request trên embedded Tomcat | Boot/server integration | Kiểm `isVirtual()` ở controller | Đo web latency/concurrency |
| `@Async` service | AsyncConfigurer hoặc Boot `applicationTaskExecutor` | Kiểm trong method | Kiểm proxy/qualifier/custom executor |
| `@Scheduled` job | TaskScheduler / SchedulingConfigurer | Kiểm trong method và loại trigger | Đặc biệt chú ý fixedDelay |
| `CompletableFuture.supplyAsync` | JDK commonPool hoặc executor được truyền | Kiểm inside supplier | Truyền executor rõ nếu cần |
| `new Thread` hoặc fixed pool tự viết | Code ứng dụng | Platform nếu API tạo platform | Đổi có chủ đích, dọn executor đúng |
| Kafka/Rabbit listener | Container factory và tích hợp theo version | Đo trong listener | Kiểm config/version thực |
| Reactor pipeline | Reactor Scheduler | Đo trong operator quan trọng | Không suy từ cờ Boot |
| HTTP client/DB driver | Thư viện, network loop, pool | Kiểm docs/metrics | Kiểm connection/resource limit |
| Batch job, script độc lập | Code riêng | Tùy cách tạo | Đánh giá riêng từng executable JVM |

Với mỗi hàng:

1. Ghi tên bean/executor thực tế hoặc API tạo thread.
2. Chạy `Thread.currentThread().isVirtual()` tại **điểm tác vụ chạy thật**.
3. Đối chiếu behavior khi bật và tắt property, cùng artifact và JDK.
4. Xem ảnh hưởng đến concurrency, context propagation, errors và shutdown.
5. Chỉ thay executor khi có lợi ích hoặc yêu cầu rõ; thêm test để ngăn hồi quy.

Không dùng “property là `true`” như bằng chứng rằng mọi task đã chuyển.

## 15. Những lỗi phổ biến

**Lỗi 1 — Nghĩ bật property sẽ đổi `new Thread`.** Sai: Java code tạo platform thread vẫn platform; phải đổi cách tạo nếu thực sự cần.

**Lỗi 2 — Nghĩ `@Async` nào cũng virtual.** Cần `@EnableAsync`, lời gọi qua proxy, executor đúng; qualifier/custom executor có thể giữ platform.

**Lỗi 3 — Định nghĩa `@Bean ExecutorService` rồi thắc mắc Boot không tạo virtual executor.** Custom `Executor` có thể khiến auto-config lùi lại. Phải kiểm tra bean type, tên và `AsyncConfigurer`.

**Lỗi 4 — Dùng `@Async` để gọi method trong cùng bean bằng `this`.** Self-invocation không đi qua proxy Spring AOP; method có thể chạy đồng bộ.

**Lỗi 5 — Nghĩ một controller virtual thì mọi task nó gọi cũng virtual.** Chỉ lời gọi đồng bộ trên cùng thread giữ loại thread; khi chuyển qua executor khác, loại thread do executor đó quyết định.

**Lỗi 6 — Nghĩ `CompletableFuture.supplyAsync` mặc định dùng Boot executor.** Không: overload không truyền executor không tự gắn với Boot context.

**Lỗi 7 — Nghĩ Netty event loops tự đổi thành virtual.** Reactive event-loop architecture vẫn có scheduler riêng; cần kiểm từng integration.

**Lỗi 8 — Nghĩ mọi `@Scheduled` có cùng cách chạy.** `fixedDelay` trong `SimpleAsyncTaskScheduler` có tính chất riêng trên scheduler thread; phải phân biệt fixedRate/cron.

**Lỗi 9 — Bật virtual nhưng ứng dụng scheduler-only thoát.** Virtual threads là daemon; cần cân nhắc `spring.main.keep-alive=true` và vòng đời tiến trình.

**Lỗi 10 — Dựa vào tên thread.** Tên có thể tùy chỉnh. Dùng `Thread.currentThread().isVirtual()`.

**Lỗi 11 — Giả định virtual = request nhanh hơn.** Virtual threads chủ yếu giúp concurrency khi chờ; CPU và downstream không nhanh hơn vì cờ.

**Lỗi 12 — Không giới hạn tác vụ đồng thời.** Virtual threads rẻ hơn OS threads nhưng DB pool, memory và upstream API vẫn hữu hạn.

**Lỗi 13 — Bỏ qua pinning trên Java 21.** Blocking kéo dài trong `synchronized`/native có thể giữ carrier; dùng JFR và sửa code theo bằng chứng.

**Lỗi 14 — Bỏ qua ThreadLocal/security/transactions.** Context không tự chảy qua mọi async boundary; phải kiểm propagation.

**Lỗi 15 — Không đóng custom executor.** Thread/task không được dừng đúng có thể giữ tài nguyên hoặc gây lỗi shutdown.

**Lỗi 16 — So sánh hai ứng dụng khác version JDK hoặc config.** Không thể quy khác biệt throughput/latency riêng cho virtual threads.

**Lỗi 17 — Áp dụng cấu hình mới của Boot version khác vào Boot 3.3.** Phải đối chiếu tài liệu đúng phiên bản.

## 16. Câu hỏi tự kiểm tra

1. **`spring.threads.virtual.enabled=true` có đổi toàn bộ `new Thread` không?** Không.
2. **JDK tối thiểu để dùng hỗ trợ virtual threads trong Spring Boot 3.3?** Java 21.
3. **Cờ Boot có làm `Executors.newVirtualThreadPerTaskExecutor()` ngừng tạo virtual khi tắt không?** Không. Đây là Java API độc lập.
4. **Khi nào auto-configured task executor dùng `SimpleAsyncTaskExecutor` virtual?** Khi Java 21+, cờ bật và không có custom `Executor` làm thay đổi auto-configuration theo điều kiện Boot.
5. **Có cần `@EnableAsync` khi dùng `@Async` trong Spring thông thường?** Có.
6. **Vì sao `this.asyncMethod()` có thể chạy đồng bộ?** Không qua proxy quản lý async advice.
7. **`@Async("fixedPool")` có dùng virtual theo property dù fixedPool là platform không?** Không; explicit executor quyết định.
8. **`CompletableFuture.supplyAsync(...)` không truyền executor có phải Boot executor?** Không, nó theo JDK default.
9. **Spring MVC request chạy virtual có nghĩa request không bao giờ dùng platform thread?** Không; có thể chuyển tiếp sang custom executor/platform thread khác.
10. **Spring WebFlux Netty event loops tự trở thành virtual vì cờ Boot?** Không.
11. **Điểm đặc biệt của `@Scheduled(fixedDelay)` với `SimpleAsyncTaskScheduler`?** Có thể thực thi trên một scheduler thread theo fixed-delay semantics; không suy ra song song như cron/fixedRate.
12. **Vì sao ứng dụng chỉ có scheduled virtual tasks có thể tự thoát?** Virtual threads là daemon, không giữ JVM sống nếu không có non-daemon thread khác.
13. **Property Boot nào giúp giữ JVM sống trong tình huống này?** `spring.main.keep-alive=true`.
14. **Cách kiểm tra loại thread đúng trong Java 21?** `Thread.currentThread().isVirtual()`.
15. **Virtual threads có tăng tốc tính toán CPU-bound?** Không tự động.
16. **Pinned virtual thread trên Java 21 nguy hiểm khi nào?** Khi blocking thường xuyên/kéo dài giữ carrier, làm giảm throughput.
17. **Nếu DB pool chỉ có 20 connection, tạo 10.000 virtual threads có thành 10.000 connections không?** Không.
18. **Dữ liệu MDC/security có chắc tự truyền qua `@Async` boundary không?** Không; cần kiểm cơ chế propagation.
19. **Nếu đã bật cờ nhưng một SDK vẫn dùng platform threads, đó có phải lỗi chắc chắn của Boot?** Không; SDK có thể tự quản lý executor độc lập.
20. **Tiêu chí quyết định chuyển một task sang virtual là gì?** Đường chạy thật, workload I/O/CPU, giới hạn tài nguyên, latency/throughput, context và shutdown; không chỉ cấu hình.

**Tổng kết:** Hỗ trợ virtual threads của Spring Boot 3.3 là **sự lựa chọn tại các điểm tích hợp được Boot quản lý**, không phải phép chuyển đổi tự động toàn bộ source code hoặc mọi thư viện. Bật `spring.threads.virtual.enabled=true` có thể làm web requests trên Tomcat/Jetty và các executor/scheduler tự cấu hình phù hợp sử dụng virtual threads. Nhưng `new Thread`, fixed pools, `CompletableFuture` mặc định, custom `@Async` executor và các thread của SDK vẫn tuân theo cách chúng được tạo. Hãy **đo bằng `isVirtual()` tại từng đường chạy**, đọc tài liệu đúng phiên bản, kiểm thử JDK 21 pinning/concurrency/daemon/context propagation và chỉ chuyển các công việc có lợi ích thật.

### Tài liệu tham khảo

- Spring Boot 3.3.13 — **SpringApplication: Virtual threads** (cờ bật, pinning, daemon và `spring.main.keep-alive`): https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3.13 — **Task Execution and Scheduling** (auto-configured `AsyncTaskExecutor`, `TaskScheduler`, custom `Executor`): https://docs.spring.io/spring-boot/3.3/reference/features/task-execution-and-scheduling.html
- Spring Boot 3.2 release notes — **Technology Specific Integrations**, Tomcat/Jetty, task executors: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.2-Release-Notes
- Spring Framework 6.1 — **SimpleAsyncTaskScheduler** (fixed-delay scheduling semantics): https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/scheduling/concurrent/SimpleAsyncTaskScheduler.html
- Oracle Java 21 — **Virtual Threads** (tạo virtual thread, `isVirtual`, pinning, JFR): https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html
- JEP 444 — Virtual Threads: https://openjdk.org/jeps/444
- Spring Boot 3.3 — Gradle Plugin: Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
