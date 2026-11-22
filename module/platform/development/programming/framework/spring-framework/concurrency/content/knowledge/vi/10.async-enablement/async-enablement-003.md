# Đặt @Async trên phương thức hoặc lớp trong Spring Framework

## 1. Vấn đề và kết quả cần hiểu

Trong Spring Framework, `@Async` đánh dấu một **phương thức ứng viên chạy bất đồng bộ**. Có hai vị trí phổ biến:

- Đặt `@Async` **trực tiếp trên phương thức** để chỉ phương thức đó được gửi tới executor khi được gọi qua Spring proxy.
- Đặt `@Async` **trên lớp** để các phương thức nghiệp vụ đủ điều kiện trong lớp được xem là phương thức async; có thể ghi đè executor của riêng một phương thức bằng annotation ở mức phương thức.

Ví dụ: một service có `generateReport()` mất nhiều giây và `getDescription()` chỉ đọc dữ liệu tại chỗ. Đặt annotation lên `generateReport()` giúp hai hành vi tách bạch; đặt annotation lên cả lớp vô tình có thể đưa `getDescription()` vào cơ chế async dù API của nó vẫn trả về `String`. Điều này có thể dẫn đến lỗi runtime vì kiểu trả về của phương thức async không hợp lệ.

**Điểm cốt lõi:** vị trí annotation quyết định **phương thức nào được proxy intercept**, còn `@EnableAsync` và executor quyết định **cơ chế chạy thực tế**. Có annotation thôi chưa bảo đảm code chạy trên luồng khác: lời gọi phải đi qua proxy và executor được chọn phải thực sự có khả năng gửi việc sang luồng khác.

Phạm vi ví dụ: Spring Framework 6.x, Spring Boot 3.3.x, Java 17, chế độ proxy mặc định. Hành vi AspectJ weaving được nhắc riêng vì có luật self-invocation khác proxy.

## 2. Điều kiện để @Async có hiệu lực

### 2.1. Bật hỗ trợ

Trong ứng dụng Java configuration, bật `@EnableAsync` một lần ở cấu hình thích hợp:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfiguration {
}
~~~

Đây là đoạn cấu hình minh họa, chưa phải chương trình hoàn chỉnh. `@SpringBootApplication` có thể nằm cùng lớp với `@EnableAsync`. `@EnableAsync` áp dụng cho `ApplicationContext` nơi nó được khai báo; không tự động kích hoạt cho một context độc lập khác.

Spring sẽ áp dụng một advisor/interceptor cho những bean được quản lý và có annotation async phù hợp. Khi code bên ngoài gọi method qua proxy, interceptor xác định executor, gửi công việc và trả quyền điều khiển cho caller theo hợp đồng async. Nếu không bật `@EnableAsync` (và không có cơ chế khác kích hoạt async), annotation chỉ là metadata và lời gọi chạy như Java thông thường.

### 2.2. Lời gọi phải đi qua Spring proxy

~~~mermaid
flowchart LR
    Caller["Controller / bean khác"] --> Proxy["Spring proxy"]
    Proxy -->|"gửi task"| Executor["Executor được chọn"]
    Executor --> Worker["Luồng xử lý"]
    Worker --> Target["Phương thức trên bean thật"]
    Self["this.someMethod() trong chính bean"] -.->|"bỏ qua proxy"| Target
~~~

Với `@EnableAsync` mặc định `mode = AdviceMode.PROXY`:

1. **Gọi từ một bean khác qua proxy:** annotation được áp dụng nếu method đủ điều kiện.
2. **Gọi `this.asyncMethod()` trong chính đối tượng:** bỏ qua proxy, method thường chạy đồng bộ trên luồng hiện tại.
3. **Tự `new ReportService()` thay vì lấy bean Spring:** không có proxy; annotation không tự tạo bất đồng bộ.
4. **Gọi trong constructor, `@PostConstruct` hoặc quá sớm trước khi proxy sẵn sàng:** không phải cách đáng tin để kích hoạt async. Để khởi chạy sau startup, có thể cho bean khác gọi service đã được proxy hóa.

Với proxy dựa trên subclass, `private` và `final` method không thể được subclass proxy override để intercept; class `final` cũng gây trở ngại. Với JDK interface proxy, chỉ các lời gọi đi qua interface proxy mới được intercept. Để code dễ đoán, đặt `@Async` trên **public method của Spring-managed service**, được caller khác inject và gọi.

`@EnableAsync(mode = AdviceMode.ASPECTJ)` kết hợp weaving có thể intercept cả lời gọi nội bộ, nhưng đòi hỏi cấu hình AspectJ và không phải mặc định của ví dụ.

## 3. Đặt @Async trên từng phương thức

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    @Async("reportExecutor")
    public CompletableFuture<String> generate(String id) {
        String path = "reports/" + id + ".csv";
        return CompletableFuture.completedFuture(path);
    }

    public String description() {
        return "Dịch vụ báo cáo";
    }
}
~~~

Đây là class có thể đặt trong ứng dụng Spring đã bật async và khai báo executor tên `reportExecutor`; cần caller gọi qua Spring proxy.

- `generate(id)` là ứng viên chạy async với `reportExecutor` vì annotation nằm ngay trên method.
- `description()` không có annotation và lớp cũng không có `@Async`, nên lời gọi thông thường vẫn chạy đồng bộ.
- Việc `generate()` trả `CompletableFuture.completedFuture(path)` **bên trong method thực thi** không mâu thuẫn với async: Spring proxy trả Future đại diện cho công việc được executor thực hiện, còn implementation phải tuân kiểu chữ ký đã khai báo.
- Đoạn này tạo chuỗi đường dẫn nhanh chỉ để minh họa; đổi thành tạo báo cáo thật cần lưu trạng thái, backpressure, timeout và kiểm soát tài nguyên.

Có thể dùng `@Async` không chỉ định tên executor:

~~~java
// Đoạn minh họa trong Spring-managed bean:
@Async
public void refreshCache() {
    // Phương thức async không trả kết quả cho caller.
}
~~~

Khi đó Spring dùng executor mặc định được cấu hình hoặc tìm được trong context. Đừng đoán số lượng luồng chỉ dựa trên sự hiện diện của `@Async`; Spring Framework có fallback riêng, Spring Boot lại có lớp auto-configuration riêng.

## 4. Đặt @Async trên cả lớp

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("batchExecutor")
public class BatchService {
    public CompletableFuture<String> rebuildIndex() {
        return CompletableFuture.completedFuture("index");
    }

    public CompletableFuture<String> publishSnapshot() {
        return CompletableFuture.completedFuture("snapshot");
    }

    @Async("reportExecutor")
    public CompletableFuture<String> urgentRebuild() {
        return CompletableFuture.completedFuture("urgent");
    }
}
~~~

Khi caller ở bean khác gọi qua Spring proxy:

- `rebuildIndex()` và `publishSnapshot()` được áp dụng async bằng executor `batchExecutor`, vì `@Async("batchExecutor")` đặt ở lớp.
- `urgentRebuild()` có annotation riêng `@Async("reportExecutor")`, **ưu tiên qualifier của phương thức** so với qualifier ở lớp.
- Nếu method-level `@Async` có giá trị rỗng, nó biểu thị chọn executor mặc định theo luật resolution, không phải nhất thiết kế thừa tên executor ở lớp. Khi thiết kế nhiều pool, nên ghi rõ qualifier trên method cần khác biệt.
- Class-level annotation không khiến constructor, field initializer, các lời gọi nội bộ hay mọi method private trở thành các task độc lập.

Cách đặt annotation ở lớp hợp lý khi phần lớn API public của service được thiết kế từ đầu để async. Tuy nhiên thay đổi sau này rất dễ gây tác dụng phụ: người khác thêm một method tiện ích trả `String` hay `long` vào lớp và vô tình biến nó thành ứng viên async với kiểu trả về không hợp lệ.

### So sánh phạm vi

| Cách đặt | Phương thức nào bị áp dụng? | Ưu điểm | Rủi ro |
| --- | --- | --- | --- |
| `@Async` trên một method | Method đó khi gọi qua proxy | Kiểm soát chính xác, dễ review | Có thể quên đánh dấu method mới cần async |
| `@Async` trên class | Các method nghiệp vụ đủ điều kiện của class khi gọi qua proxy | Gọn khi toàn bộ service dùng async | Dễ ảnh hưởng thêm method mới, kiểu trả về không phù hợp |
| Class `@Async("batchExecutor")` + method `@Async("reportExecutor")` | Mặc định class, method riêng ghi đè | Phân pool cho task ưu tiên | Cần rà soát qualifier và cấu hình executor |
| Class không có annotation + method không có annotation | Không có interceptor async từ những annotation này | Hành vi đồng bộ rõ ràng | Muốn async cần gọi qua cơ chế khác |

**Ví dụ không nên dùng:**

~~~java
// Anti-pattern minh họa; không gọi method này qua @Async proxy.
@Service
@Async("batchExecutor")
public class MixedPurposeService {
    public String status() {
        return "READY";
    }
}
~~~

Trong proxy async thông thường, Spring chỉ hỗ trợ return type `void`, `Future<T>` hoặc `CompletableFuture<T>`. Nếu `status()` bị async interceptor xử lý, chữ ký trả `String` không phù hợp và có thể bị `IllegalArgumentException` thay vì trả chuỗi như trước. Hãy tách status/query đồng bộ sang bean khác, hoặc đặt annotation trên từng method async.

## 5. Dự án chạy được: method-level so với class-level

Ứng dụng Java 17 + Spring Boot 3.3.5 dưới đây có hai executor với prefix khác nhau. Ta quan sát trên **luồng thật của method được intercept** và tránh dựa vào `Thread.sleep` hay thứ tự chạy ngẫu nhiên.

### 5.1. Cấu trúc

~~~text
async-placement-demo/
├── pom.xml
└── src/main/java/com/example/async/
    ├── AsyncPlacementApplication.java
    ├── MethodOnlyService.java
    └── ClassWideService.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>async-placement-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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
~~~

`spring-boot-starter-aop` bảo đảm hạ tầng proxy AOP có trên classpath của demo; `@Async` được kích hoạt qua `@EnableAsync`. Đây là ứng dụng command-line, không cần web server.

### 5.3. AsyncPlacementApplication.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableAsync
public class AsyncPlacementApplication {
    public static void main(String[] args) {
        // ApplicationRunner chạy trong SpringApplication.run() trước khi trả context.
        SpringApplication.run(AsyncPlacementApplication.class, args).close();
    }

    @Bean("reportExecutor")
    ThreadPoolTaskExecutor reportExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("report-");
        return pool;
    }

    @Bean("batchExecutor")
    ThreadPoolTaskExecutor batchExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("batch-");
        return pool;
    }

    @Bean
    ApplicationRunner verifyPlacement(
            MethodOnlyService methodService, ClassWideService classService) {
        return args -> {
            String caller = Thread.currentThread().getName();

            // Gửi qua proxy rồi mới chờ, để đọc thread name thật bên trong task.
            CompletableFuture<String> method = methodService.generateReport();
            CompletableFuture<String> cls1 = classService.rebuildIndex();
            CompletableFuture<String> cls2 = classService.publishSnapshot();
            CompletableFuture<String> override = classService.urgentRebuild();

            System.out.println("METHOD_LEVEL_REPORT_POOL="
                    + method.get(5, TimeUnit.SECONDS).startsWith("report-"));
            System.out.println("UNANNOTATED_STAYS_CALLER="
                    + methodService.descriptionThread().equals(caller));
            System.out.println("CLASS_METHOD_1_BATCH_POOL="
                    + cls1.get(5, TimeUnit.SECONDS).startsWith("batch-"));
            System.out.println("CLASS_METHOD_2_BATCH_POOL="
                    + cls2.get(5, TimeUnit.SECONDS).startsWith("batch-"));
            System.out.println("METHOD_OVERRIDES_CLASS="
                    + override.get(5, TimeUnit.SECONDS).startsWith("report-"));
            System.out.println("SELF_INVOCATION_STAYS_CALLER="
                    + methodService.selfInvocationThread().equals(caller));
        };
    }
}
~~~

Hai bean executor được Spring quản lý, khởi tạo và dọn vòng đời. Mỗi pool chỉ có một worker để tên luồng dễ theo dõi; `queueCapacity=8` không có nghĩa tám worker. Không dựa vào mặc định số thread của Spring Framework hay Boot trong bài thử này.

### 5.4. MethodOnlyService.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class MethodOnlyService {
    @Async("reportExecutor")
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    // Không có @Async ở method hay class -> chạy ngay trên caller.
    public String descriptionThread() {
        return Thread.currentThread().getName();
    }

    public String selfInvocationThread() {
        // Gọi qua this, bỏ qua Spring proxy, nên chạy inline.
        return generateReport().join();
    }
}
~~~

Chú ý `selfInvocationThread()` **không** được chú thích `@Async`; vì lời gọi từ ApplicationRunner là vào method đồng bộ, nó chạy trên caller. Bên trong nó, `generateReport()` được gọi trực tiếp qua `this` nên method mang annotation chạy inline. Nếu thay bằng một lời gọi từ bean khác qua proxy, `generateReport()` sẽ được gửi sang `reportExecutor`.

### 5.5. ClassWideService.java

~~~java
package com.example.async;

import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
@Async("batchExecutor")
public class ClassWideService {
    // Không cần @Async tại method vì class đã có.
    public CompletableFuture<String> rebuildIndex() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    public CompletableFuture<String> publishSnapshot() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }

    @Async("reportExecutor")
    public CompletableFuture<String> urgentRebuild() {
        return CompletableFuture.completedFuture(
                Thread.currentThread().getName());
    }
}
~~~

### 5.6. Chạy và kiểm tra stdout

Tại thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

Bỏ qua log startup/shutdown của Spring, chương trình in **sáu dòng** theo thứ tự (đều là boolean; không giả định hậu tố tên thread):

~~~text
METHOD_LEVEL_REPORT_POOL=true
UNANNOTATED_STAYS_CALLER=true
CLASS_METHOD_1_BATCH_POOL=true
CLASS_METHOD_2_BATCH_POOL=true
METHOD_OVERRIDES_CLASS=true
SELF_INVOCATION_STAYS_CALLER=true
~~~

Giải thích: `get(5, TimeUnit.SECONDS)` chỉ được gọi **sau khi** nhận handle future, nên chương trình không khẳng định thứ tự hoàn tất giữa các executor; nó chỉ chờ kết quả mỗi việc có hạn định. Method-level `generateReport` chạy trong `report-*`, hai method thuộc class-level chạy trong `batch-*`, `urgentRebuild` ghi đè dùng `report-*`. `descriptionThread()` và lời gọi nội bộ `selfInvocationThread()` đều chạy trên caller nên trả đúng thread name đã ghi lại.

**Kiểm thử này xác minh vị trí annotation và đường đi proxy**, chưa chứng minh giới hạn throughput hay mức chịu tải thực tế. Muốn kiểm thử xử lý chồng nhau, hãy dùng `CountDownLatch`/barrier với một pool có nhiều worker và kiểm tra invariant, không chỉ nhìn tên thread.

## 6. Hợp đồng method khi quyết định vị trí annotation

Vị trí `@Async` phải phù hợp chữ ký của **từng method được intercept**: `void`, `Future<T>` hoặc `CompletableFuture<T>`. Khi gắn annotation ở cấp lớp, cần rà soát toàn bộ public business methods; một getter trả `String` thêm sau này có thể vô tình bị async advice áp dụng và lỗi vì return type không hỗ trợ.

| Loại method | Vị trí annotation nên chọn | Kênh quan sát |
| --- | --- | --- |
| Chạy nền, không trả kết quả | Method-level `@Async` | Handler/log cho lỗi `void` |
| Có kết quả và cần phối hợp | Method-level hoặc class-level đã kiểm soát | Future/CompletableFuture, timeout và lỗi |
| Query/getter đồng bộ trả `String`/DTO | Không được phủ bởi class-level `@Async` | Kết quả trực tiếp trên caller |

Caller gọi `get()`/`join()` ngay sau submit vẫn có thể block; callback trên `CompletableFuture` cho phép chuỗi tác vụ linh hoạt hơn. Khi task lỗi, future hoàn thành lỗi; khi executor từ chối ngay lúc submit, phải xử lý rejection tại biên gọi. Các cơ chế composition, cancellation và exception chi tiết thuộc hợp đồng của chính kiểu trả về, tách biệt với quyết định **đặt annotation ở method hay class**.

## 7. Hiểu đúng executor khi gắn annotation

`@Async("reportExecutor")` chỉ định **bean name hoặc qualifier**, không chỉ định số luồng. Cần khai báo bean executor tương ứng và theo dõi chính sách queue/rejection.

Nếu `@Async` không có qualifier:

1. `@EnableAsync` có thể dùng executor do `AsyncConfigurer` cung cấp.
2. Trong Spring Framework, cơ chế mặc định tìm bean `TaskExecutor` duy nhất; nếu không chọn được, xét bean `Executor` tên `taskExecutor`.
3. Nếu không có ứng viên phù hợp, Spring Framework có fallback `SimpleAsyncTaskExecutor`. Đây không phải pool worker tái sử dụng kiểu `ThreadPoolTaskExecutor`.
4. Spring Boot có thể tự cung cấp executor theo auto-configuration khi điều kiện phù hợp; trong môi trường Boot, kết quả thực tế còn phụ thuộc bean hiện hữu và properties.

Khi dùng nhiều executor, **chỉ rõ qualifier cho method có yêu cầu riêng**. Với class-level annotation, nêu cả default của class và method override trong review. Không giả định rằng thêm một bean tên tùy ý sẽ khiến mọi `@Async` tự dùng bean ấy.

Trong ứng dụng sản xuất, nên cấu hình `corePoolSize`, `maxPoolSize`, `queueCapacity`, thread name prefix, timeout và hành vi khi overload; đừng để queue tăng không giới hạn. Một pool 4 worker không bảo đảm bốn việc CPU-bound sẽ nhanh hơn một core hoặc DB đủ connection; đo thực tế.

## 8. Trạng thái request, transaction và tác động khi chạy trên thread khác

Lời gọi async chuyển việc sang thread khác (khi dùng executor bất đồng bộ thật sự) làm thay đổi các giả định về ngữ cảnh:

- **Transaction:** transaction của HTTP/request thread không tự truyền sang worker. Nếu method async cần giao dịch, tạo boundary ở service được worker gọi trên thread ấy, ví dụ `@Transactional` với lời gọi qua proxy, và giới hạn transaction quanh DB operations. Không giữ transaction trong suốt lúc gọi API chậm hoặc tạo file.
- **Request scope:** bean `@RequestScope` và `RequestContextHolder` thường gắn với request thread. Không giả định worker luôn truy cập được request context. Lấy các giá trị cần thiết (request ID, user ID, immutable DTO) trước khi dispatch.
- **SecurityContext/MDC/ThreadLocal:** không mặc nhiên hiện diện trong worker. Dùng cơ chế context propagation thích hợp hoặc truyền dữ liệu rõ ràng, đồng thời dọn trạng thái thread-local khi luồng được tái sử dụng.
- **Mutable inputs:** nếu caller tiếp tục sửa danh sách/DTO sau khi gửi việc, worker có thể thấy dữ liệu thay đổi không nhất quán. Truyền snapshot bất biến hoặc dùng đồng bộ hóa thích hợp.
- **Lỗi/side effects:** worker có thể ghi kết quả sau khi caller timeout hoặc client retry. Thiết kế idempotency key và trạng thái job để tránh xử lý trùng.

Đặt `@Async` trên cả lớp **không biến field singleton thành thread-safe**. Nhiều worker có thể đồng thời gọi cùng một instance, nên `count++` trên field mutable vẫn mất cập nhật. Ưu tiên service stateless, `AtomicLong`/lock cho state trong JVM hoặc transaction/optimistic locking cho dữ liệu chia sẻ giữa nhiều pod.

## 9. Các lỗi phổ biến khi chọn vị trí @Async

| Triệu chứng | Nguyên nhân hay gặp | Cách xác minh/sửa |
| --- | --- | --- |
| Có `@Async` nhưng vẫn chạy trên caller | Thiếu `@EnableAsync`, tự `new` object, hoặc self-invocation | Kiểm tra bean proxy và thread name; gọi từ bean khác |
| Method trong class `@Async` trả `String` bị lỗi | Class-level annotation đã phủ lên getter/query đồng bộ | Tách bean hoặc chỉ annotate method async; trả Future hợp lệ |
| Method đặc biệt chạy sai pool | Class-level qualifier đang áp dụng; method chưa override đúng | Dùng `@Async("executorName")` và kiểm tra tên thread |
| `private`/`final` method không được intercept | Giới hạn proxy mặc định | Dùng public, non-final method gọi từ bên ngoài proxy |
| Exception của `void` không tới caller | Task chạy ở worker, không có result handle | Cấu hình `AsyncUncaughtExceptionHandler`, log và metric |
| Future không bao giờ hoàn thành | Task bị mất khi overload/shutdown hoặc mắc kẹt I/O | Dùng rejection có tín hiệu, deadline, timeout và job status |
| HTTP trả chậm dù đã dùng async | Caller gọi `future.join()/get()` ngay | Trả job ID/202 sớm, tách endpoint tra trạng thái |
| Đọc request/transaction context lỗi trong worker | Ngữ cảnh gắn với luồng, không tự chuyển | Truyền ID/dữ liệu cần thiết; mở transaction ở worker |
| Test bằng executor đồng bộ vẫn pass | `SyncTaskExecutor` không chuyển thread và che giấu race/context | Test thêm với executor production và concurrency có kiểm soát |
| Đặt `@Async` lên `@PostConstruct` | Lifecycle callback không phải điểm kích hoạt async thích hợp | Cho bean khởi tạo khác gọi qua proxy sau khi context sẵn sàng |

## 10. Hướng dẫn quyết định và checklist review

**Ưu tiên đặt trên phương thức khi:** lớp có cả query đồng bộ và command async, ít method cần chạy nền, hoặc mỗi job cần executor riêng. Đây thường là lựa chọn dễ kiểm soát cho controller/service có API hỗn hợp.

**Có thể đặt trên lớp khi:** mọi public business method của lớp đều chủ đích async, kiểu trả về đều tương thích, và team thống nhất rằng method thêm mới sẽ tự chịu quy tắc async. Để tránh vô tình thay đổi contract, tài liệu hóa ràng buộc ở lớp và giữ các utility/query đồng bộ trong bean khác.

Trước khi đưa code vào production, kiểm tra:

1. Bean được Spring quản lý và `@EnableAsync` bật trong đúng context; không gọi `new` để thay bean.
2. Caller gọi qua proxy từ bean khác; không dựa vào `this.method()` hoặc constructor/`@PostConstruct`.
3. Annotation đặt trên method hay cả lớp đúng chủ đích; với class-level, đã rà soát **tất cả public business method** và return type.
4. Executor tên/qualifier đúng và sẵn có; có pool/queue hữu hạn, rejection policy có tín hiệu và graceful shutdown hợp lý.
5. Caller biết cách nhận kết quả: `void` được log/metric; `Future/CompletableFuture` có error handling và timeout; không block HTTP request không cần thiết.
6. Task nhận input an toàn và quản lý transaction, request context, security context, MDC đúng khi chuyển thread.
7. Dùng test xác minh method-level/class-level/method override; dùng concurrency test thực cho shared state và test bão hòa để xác minh rejection.
8. Khi chạy nhiều instance, trạng thái job quan trọng nằm ở DB/broker đáng tin cậy và có retry/idempotency thích hợp.

### Câu hỏi tự kiểm tra

1. Nếu chỉ `generateReport()` cần chạy nền còn `getSummary()` phải trả `String` ngay, bạn sẽ đặt `@Async` ở đâu và vì sao?
2. `@Async("batchExecutor")` ở class và `@Async("reportExecutor")` ở method cùng tồn tại: method đó dùng executor nào?
3. Trong cùng bean, `this.generateReport()` có được interceptor của `@EnableAsync` mặc định bắt không? Làm thế nào để kích hoạt đúng?
4. Vì sao một method trong class có `@Async` không nên trả trực tiếp `List<Report>` khi proxy intercept?
5. Khác biệt giữa exception trong worker trả `CompletableFuture` và exception trong method `@Async void` là gì?
6. Nếu test dùng `SyncTaskExecutor` còn production dùng `ThreadPoolTaskExecutor`, điều gì có thể thay đổi về transaction, ThreadLocal, thứ tự và lỗi?
7. Với endpoint muốn trả 202 ngay sau khi tiếp nhận yêu cầu, vì sao không nên gọi `future.get()` ngay trên request thread?

**Ghi nhớ:** đặt `@Async` ở **method** để chỉ rõ việc nào chạy nền; đặt ở **class** khi tất cả method nghiệp vụ đủ điều kiện được thiết kế async. Cả hai đều phụ thuộc `@EnableAsync`, proxy, executor và return type hợp lệ. Annotation có mặt trong source code không phải bằng chứng task thật sự chạy trên worker.

## Tài liệu chính thức

- [Spring Framework 6.2 — The @Async Annotation](https://docs.spring.io/spring-framework/reference/6.2/integration/scheduling.html#scheduling-annotation-support-async)
- [Spring Framework 6.2 — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework 6.2 — Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/scheduling/annotation/Async.html)
