# ContextPropagatingTaskDecorator và điều kiện tích hợp thư viện ngữ cảnh

## 1. Bài toán: vì sao context biến mất khi chuyển sang worker thread?

Trong một ứng dụng Spring, luồng HTTP request thường có dữ liệu ngữ cảnh gắn với luồng hiện tại: mã tương quan (`correlationId`), tenant ID, thông tin quan sát (`Observation`), trace context hoặc MDC dùng để gắn metadata vào log. Nhiều thư viện dùng `ThreadLocal` để lưu các giá trị này trong phạm vi một luồng.

Khi gửi tác vụ sang `TaskExecutor` hoặc gọi một phương thức `@Async`, Spring có thể thực thi tác vụ trên **worker thread khác**. `ThreadLocal` của caller **không tự động chuyển sang worker**. Ví dụ:

```java
private static final ThreadLocal<String> TENANT = new ThreadLocal<>();

// Thread đang nhận request:
TENANT.set("tenant-A");

executor.execute(() -> {
    // Nếu không có cơ chế lan truyền, giá trị thường là null:
    System.out.println("Worker tenant = " + TENANT.get());
});

TENANT.remove();
```

Đây chỉ là **mảnh code minh họa**, giả định `executor` đã được cấu hình. Kết quả quan sát phụ thuộc executor và cấu hình thực tế: một executor chạy trực tiếp trên caller có thể đọc được `tenant-A`; thread pool bình thường không tự mang `ThreadLocal` của caller sang worker.

Spring Framework **6.1 trở lên** cung cấp lớp:

```java
org.springframework.core.task.support.ContextPropagatingTaskDecorator
```

Đây là một `TaskDecorator` chuyên **chụp một snapshot của context có thể truy cập tại nơi gửi task, rồi thiết lập context ấy trong lúc task thực thi**, sau đó khôi phục trạng thái trước đó khi scope kết thúc. Lớp dựa vào **Micrometer Context Propagation**, không phải một bản sao thần kỳ của toàn bộ `ThreadLocal` trên JVM.

Đề bài này có hai vế không thể tách rời:

1. **Cấu hình `ContextPropagatingTaskDecorator` trên executor thực sự nhận task.**
2. **Bảo đảm tích hợp thư viện ngữ cảnh và các accessor tương ứng** để dữ liệu cần truyền có thể được chụp/khôi phục.

Nếu thiếu vế thứ hai, decorator có thể vẫn được tạo nhưng không biết cách truy cập một `ThreadLocal` tùy chỉnh. Nếu thiếu thư viện `io.micrometer:context-propagation` ở runtime, ngay cả việc nạp hoặc khởi tạo lớp cũng có thể thất bại.

### Mục tiêu học tập

Sau bài này, bạn sẽ hiểu cơ chế snapshot/scope, kiểm tra đúng dependency và phiên bản, đăng ký `ThreadLocalAccessor`, dùng `ThreadPoolTaskExecutor.setTaskDecorator(...)`, áp dụng với `@Async`, viết ví dụ Maven chạy trên Java 17, kiểm chứng không rò context khi tái sử dụng worker và phân biệt nó với các cơ chế transaction, security, Reactor, MDC hoặc truyền tham số thủ công.

## 2. Vì sao ThreadLocal bình thường không qua ranh giới luồng?

`ThreadLocal<T>` cho mỗi thread một giá trị riêng. Cùng một đối tượng `ThreadLocal` nhưng các thread khác nhau có vùng lưu riêng:

```text
HTTP thread / caller              Worker thread
---------------------            ----------------
TENANT.set("tenant-A")             TENANT.get() -> null
        |
        +-- executor.execute(task) ---------->
        |
        +-- tiếp tục công việc               task.run()
                                           không tự có tenant-A
```

`InheritableThreadLocal` không phải cách sửa tổng quát: nó hỗ trợ kế thừa ở **thời điểm tạo thread con**, còn thread pool thường tái sử dụng worker được tạo từ trước hoặc bởi thread khác. Giá trị có thể cũ, sai tenant hoặc tồn tại vượt phạm vi request nếu sao chép không đúng.

Cũng không nên tự `TENANT.set(...)` trên worker rồi quên `remove()`. Worker thread có thể xử lý nhiều request liên tiếp; dữ liệu của yêu cầu A lưu trong thread-local có thể rò sang yêu cầu B. Với thông tin tenant hoặc security, lỗi này có thể thành sự cố cách ly dữ liệu.

**Nguyên tắc an toàn:** Nếu cần dùng thread-local ở worker, phải biết chính xác **giá trị nào được truyền, thời điểm chụp, thời điểm thiết lập, cách khôi phục và lúc nào xóa**. Một wrapper chỉ `set` mà không `restore` là chưa đủ.

## 3. ContextPropagatingTaskDecorator làm gì?

`ContextPropagatingTaskDecorator` nằm trong `spring-core` và hiện thực giao diện `TaskDecorator`. JavaDoc mô tả nó bọc việc thực thi task nhằm hỗ trợ context propagation, đặc biệt hữu ích cho **logging context** hoặc **observation context**.

Các thành phần chính:

| Thành phần | Package/API | Vai trò |
|---|---|---|
| `TaskDecorator` | `org.springframework.core.task.TaskDecorator` | Hợp đồng bọc một `Runnable` trước khi executor chạy |
| `ContextPropagatingTaskDecorator` | `org.springframework.core.task.support` | Decorator dựa vào Micrometer snapshot để truyền context |
| `ContextSnapshotFactory` | `io.micrometer.context` | Tạo snapshot và quản lý logic chụp/khôi phục |
| `ContextSnapshot` | `io.micrometer.context` | Giữ những giá trị context đã chụp |
| `ContextRegistry` | `io.micrometer.context` | Danh sách các accessor mà Micrometer biết |
| `ThreadLocalAccessor<T>` | `io.micrometer.context` | Đọc, đặt và reset một loại ThreadLocal |
| `ContextAccessor` | `io.micrometer.context` | Truy cập context dạng map-like, ví dụ tích hợp reactive |

Hợp đồng decorator rút gọn:

```java
Runnable decorate(Runnable original);
```

Spring gọi `decorate(...)` để tạo một Runnable có khả năng khôi phục ngữ cảnh xung quanh `original.run()`. Với `ThreadPoolTaskExecutor`, việc trang trí được kết nối bằng:

```java
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
```

**Không phải mọi Executor đều hỗ trợ `setTaskDecorator(...)`.** Một `java.util.concurrent.ExecutorService` tạo trực tiếp bằng `Executors.newFixedThreadPool(...)` không tự chạy decorator Spring chỉ vì bean khác trong context đã cấu hình nó. Phải dùng một Spring executor hỗ trợ `TaskDecorator` hoặc bọc task/executor bằng cơ chế tương ứng có chủ đích.

### 3.1. Hai constructor

JavaDoc Spring 6.1+ công bố:

```java
new ContextPropagatingTaskDecorator()
```

Constructor mặc định tạo một `ContextSnapshotFactory` mặc định, thông thường dùng `ContextRegistry` toàn cục của Micrometer.

Khi cần registry/factory riêng:

```java
new ContextPropagatingTaskDecorator(customFactory)
```

`customFactory` là một `io.micrometer.context.ContextSnapshotFactory` được cấu hình trước. Cách này hữu ích khi muốn kiểm soát các accessor/kiểu context tham gia, tránh nhầm với registry toàn cục; ví dụ đầy đủ ở mục 10.

### 3.2. Decorator không tạo thêm worker

Một decorator không có ý nghĩa quản trị thread pool. Nó không tự tăng worker, không thêm queue, không giải quyết rejection và không làm một phép tính đồng bộ biến thành bất đồng bộ. Nó chỉ bao quanh việc **thực thi Runnable** khi executor đã quyết định chạy task.

Nếu executor thực thi đồng bộ trên caller, thread-local của caller vốn đã sẵn có; decorator có thể không đem lại ích lợi mà vẫn tăng overhead. Điều này được chính JavaDoc của Spring nhấn mạnh: cơ chế có chi phí thêm, đặc biệt đáng cân nhắc nếu ứng dụng gửi số lượng lớn task cực nhỏ.

## 4. Điều kiện tích hợp: chỉ thêm spring-core là chưa đủ

Lớp `ContextPropagatingTaskDecorator` thuộc Spring Framework, nhưng phần lõi của cơ chế context snapshot dùng Micrometer. Với môi trường Spring Framework 6.1+ thông thường, hãy đảm bảo artifact sau **thực sự có trên runtime classpath**:

```text
io.micrometer:context-propagation
```

Ví dụ Maven cho dự án không dùng Spring Boot BOM:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework</groupId>
        <artifactId>spring-context</artifactId>
        <version>6.2.7</version>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>context-propagation</artifactId>
        <version>1.1.3</version>
    </dependency>
</dependencies>
```

Hai phiên bản ở đây là bộ phiên bản **cụ thể để minh họa và dùng trong demo** của bài, không phải tuyên bố đó là các phiên bản mới nhất. Khi làm việc trong dự án có Spring Boot/dependency management, ưu tiên **BOM của stack đã chọn** thay vì ép phiên bản Micrometer không tương thích. Cần đồng bộ Java requirement, classpath của runtime, dependency exclusions và môi trường triển khai.

**Phân biệt ba tầng điều kiện:**

1. Có Spring Framework phiên bản cung cấp `ContextPropagatingTaskDecorator` (**since Spring 6.1**).
2. Có jar `context-propagation` tương thích ở **runtime**, không chỉ compile; kiểm tra dependency tree, classloader và version conflicts.
3. Có `ThreadLocalAccessor`/`ContextAccessor` phù hợp trong `ContextRegistry` cho **loại dữ liệu bạn thực sự muốn truyền**. Custom `ThreadLocal` sẽ không tự có accessor chỉ vì đã thêm jar.

Thư viện này chỉ cung cấp **hạ tầng truyền context**. Muốn tạo trace/metrics đầy đủ còn cần instrumentation, registry, tracing bridge/exporter và cấu hình observability tương ứng. `ContextPropagatingTaskDecorator` không tự gửi span đến một hệ thống quan sát nếu không có hạ tầng tracing.

### 4.1. Những lỗi dependency thường gặp

| Hiện tượng | Khả năng nguyên nhân | Cách xử lý |
|---|---|---|
| Không tìm thấy `ContextPropagatingTaskDecorator` lúc biên dịch | Spring Framework quá cũ hoặc module/classpath sai | Xác minh Spring 6.1+ và import đúng `spring-core` |
| `NoClassDefFoundError: io/micrometer/context/ContextSnapshotFactory` | Thiếu Micrometer Context Propagation ở runtime | Thêm `io.micrometer:context-propagation` đúng scope/runtime |
| `NoSuchMethodError` liên quan Micrometer | Phiên bản jar không tương thích hoặc conflict | Dùng BOM phù hợp, kiểm tra cây phụ thuộc thực tế |
| Decorator chạy nhưng custom tenant vẫn null | Chưa đăng ký accessor, sai registry hoặc context vốn trống ở thread submit | Xác minh `ContextRegistry`, thời điểm set và capture |
| Chỉ một vài đường thực thi có context | Decorator gắn vào một executor, các đường khác dùng executor khác | Xác định đúng executor và mọi ranh giới chuyển thread |
| Context của request trước xuất hiện trong task sau | Set không reset, wrapper tự viết sai hoặc custom accessor lỗi | Test cùng worker tái sử dụng, khôi phục bằng Scope/finally |

Với dự án Maven, có thể kiểm tra dependency:

```bash
mvn dependency:tree -Dincludes=io.micrometer:context-propagation
```

Lệnh cho thấy version/scope/đường đi của dependency trong mô hình Maven; không đảm bảo bản deploy cuối có đúng jar nếu packaging/classloader bị cấu hình khác. Cũng cần kiểm tra bản build và môi trường chạy thực tế.

## 5. ContextRegistry và ThreadLocalAccessor: phần không được bỏ qua

`ContextRegistry` biết **cách đọc và đặt từng loại context** thông qua các accessor. Micrometer không thể phản chiếu toàn bộ các biến `ThreadLocal` trong một ứng dụng để tự hiểu ý nghĩa và vòng đời của chúng.

Ví dụ ứng dụng có:

```java
private static final ThreadLocal<String> REQUEST_ID =
        new ThreadLocal<>();
```

Để Micrometer có thể chụp giá trị `REQUEST_ID.get()` và khôi phục vào thread chạy task, có thể đăng ký accessor bằng callback:

```java
import io.micrometer.context.ContextRegistry;

ContextRegistry.getInstance().registerThreadLocalAccessor(
        "lesson.requestId",
        REQUEST_ID::get,
        REQUEST_ID::set,
        REQUEST_ID::remove
);
```

Đây là **mảnh mã Java trong class có `REQUEST_ID`**, không phải chương trình độc lập. `registerThreadLocalAccessor` với bốn đối số dùng:

- **key**: mã định danh ổn định của loại context, ví dụ `lesson.requestId`.
- **getter**: đọc giá trị ở **thread hiện tại**.
- **setter**: đặt giá trị trong scope lúc khôi phục.
- **resetter**: làm sạch giá trị (`ThreadLocal.remove()`) khi cần reset.

Trong demo, dùng `ContextRegistry.getInstance()` vì constructor mặc định của decorator tìm accessor qua registry toàn cục. Nếu tạo một `ContextRegistry` **riêng**, phải cung cấp registry đó cho `ContextSnapshotFactory` rồi đưa factory vào decorator; chỉ register vào một registry không được decorator sử dụng sẽ không có tác dụng.

### 5.1. Có thể triển khai ThreadLocalAccessor thành class

Micrometer còn có interface:

```java
import io.micrometer.context.ThreadLocalAccessor;

public final class RequestIdAccessor
        implements ThreadLocalAccessor<String> {

    public static final String KEY = "lesson.requestId";

    @Override
    public Object key() {
        return KEY;
    }

    @Override
    public String getValue() {
        return RequestIdContext.get();
    }

    @Override
    public void setValue(String value) {
        RequestIdContext.set(value);
    }

    @Override
    public void setValue() {
        RequestIdContext.clear();
    }
}
```

Đây là **class minh họa phụ thuộc `RequestIdContext` do ứng dụng định nghĩa**. Khi đó:

```java
ContextRegistry.getInstance().registerThreadLocalAccessor(
        new RequestIdAccessor());
```

Điều quan trọng không phải dạng callback hay class, mà là **accessor trả đúng key, đọc đúng ThreadLocal, khôi phục đúng giá trị và xóa đúng lúc**. Với nhiều loại context khác nhau, cần các accessor riêng hoặc bridge do thư viện tương ứng cung cấp.

### 5.2. Đăng ký accessor khi nào?

Nên đăng ký ở giai đoạn **khởi động cấu hình ứng dụng**, trước khi tạo/sử dụng các task cần context, và làm rõ ownership của registry. Đăng ký accessor trùng key từ nhiều module mà không kiểm soát có thể thay thế accessor cũ, khiến quan sát khó hiểu.

`ContextRegistry` là danh sách accessor, **không phải nơi giữ request ID cụ thể của từng request**. Giá trị request ID vẫn được set vào `ThreadLocal` trên caller khi thực thi; snapshot đọc giá trị lúc gửi task.

## 6. Cơ chế capture → restore → cleanup

Một lần thực thi qua decorator có thể hiểu như sau:

```text
Thread submit:
  set REQUEST_ID = "R-100"
  |
  v
TaskDecorator.decorate(original Runnable)
  |
  +-- ContextSnapshotFactory.captureAll()
  |   nhìn vào các accessor đã đăng ký
  |   lưu giá trị "R-100" trong snapshot
  |
  +-- trả Runnable có wrapper
  |
  v
Executor đưa wrapper vào queue / worker
  |
  v
Worker thread:
  snapshot mở Scope -> đặt REQUEST_ID = "R-100"
  |
  +-- chạy original.run()
  |      logging/tracing có thể đọc REQUEST_ID tương ứng
  |
  +-- Scope.close() -> khôi phục giá trị trước scope
  v
Worker có thể được tái sử dụng cho request khác
```

Đây là mô hình logic. Snapshot/scope được triển khai bởi Micrometer, còn `ThreadPoolTaskExecutor` quyết định lúc nào decorator được áp dụng và task được chạy.

### 6.1. Snapshot ở thời điểm **gửi**, không phải lúc worker lấy task

Giả sử:

```java
REQUEST_ID.set("R-100");
executor.execute(work); // decorator capture context ở đường gửi

REQUEST_ID.set("R-200");
// Worker có thể mới chạy work sau thời điểm đổi này.
```

Nếu `REQUEST_ID` có accessor và executor dùng decorator đúng, `work` dùng **giá trị đã chụp `R-100`**, không tự đổi thành `R-200` chỉ vì caller thay thread-local sau submit.

Hãy tránh giải thích rằng decorator giữ một reference “sống” tới toàn bộ ThreadLocal của caller. Nó lưu những giá trị mà accessor capture được tại thời điểm tương ứng. Với **đối tượng mutable**, snapshot thường giữ tham chiếu tới đối tượng đó, không tự deep-copy tất cả nội dung. Nếu đối tượng được sửa đồng thời, vẫn có race và quy tắc thread-safety riêng.

### 6.2. Scope và cleanup ngăn rò context

Micrometer dùng `ContextSnapshot.Scope` có thể đóng để reset/restore các thread-local sau khi task kết thúc. Điều này đặc biệt quan trọng với worker pool vì cùng một worker lần lượt chạy nhiều task.

Mô hình dùng snapshot thủ công:

```java
ContextSnapshot snapshot = factory.captureAll();

try (ContextSnapshot.Scope scope = snapshot.setThreadLocals()) {
    // Trong scope: các ThreadLocal đã đăng ký được khôi phục.
    process();
}
// Sau scope: các ThreadLocal được khôi phục về giá trị trước đó.
```

Đây là mảnh code minh họa; `factory` là `ContextSnapshotFactory` và `process()` do ứng dụng cung cấp. `ContextPropagatingTaskDecorator` giúp áp dụng logic tương tự quanh việc chạy `Runnable`, tránh phải lặp mã này ở mỗi task.

Không được kết luận “không có rò rỉ nào” trong mọi ứng dụng chỉ từ việc bật decorator: một `ThreadLocal` **chưa đăng ký**, một thư viện dùng cơ chế lưu khác hoặc một wrapper ngoài scope vẫn có thể gây leak. Test cần chứng minh các context **thực sự được hỗ trợ** đã được restore.

### 6.3. Context không có giá trị khi gửi

Nếu accessor được đăng ký nhưng caller **không set giá trị**, snapshot không thể phát minh ra tenant ID. Tùy cơ chế và cấu hình snapshot, một giá trị vắng mặt có thể không được đưa vào snapshot; vì vậy điều quan trọng là worker phải có baseline sạch và scope đúng, tránh dữ liệu từ task trước.

Với nghiệp vụ cần tuyệt đối không dùng lại tenant cũ, kết hợp accessor reset chính xác, dọn context tại biên request/task và integration test trên **cùng một worker tái sử dụng**. Không dùng việc truyền context như cơ chế cấp quyền truy cập một cách độc lập.

## 7. Cấu hình ThreadPoolTaskExecutor trong Spring

Mẫu Java Configuration thường gặp:

**Tệp `ContextExecutorConfiguration.java` — class cấu hình Spring.**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class ContextExecutorConfiguration {

    @Bean("contextExecutor")
    public ThreadPoolTaskExecutor contextExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();

        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("ctx-worker-");

        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());

        return executor;
    }
}
```

Điều kiện để đoạn này có tác dụng:

1. Có Spring Framework 6.1+ và `io.micrometer:context-propagation` phù hợp trong classpath.
2. Executor bean này **thực sự được sử dụng** để gửi task.
3. Accessor phù hợp đã được đăng ký hoặc thư viện tích hợp cung cấp.
4. Context cần truyền **đã được set trên thread gửi** trước khi task được trang trí.
5. Worker không dùng context ngoài chính sách bảo mật, transaction hay vòng đời đúng.

**Không cần `@EnableAsync` nếu chỉ inject `TaskExecutor` và gọi `execute(...)` trực tiếp.** Nếu muốn sử dụng phương thức `@Async("contextExecutor")`, cần bật cơ chế `@Async` và gọi qua Spring proxy.

### 7.1. @Async chọn đúng executor

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("contextExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture(
                "report=" + id + ", thread="
                + Thread.currentThread().getName());
    }
}
```

Lớp này là **Spring component**, cần application context, `@EnableAsync` và cấu hình executor ở trên; không phải Java SE standalone. Spring sẽ dùng bean có tên `contextExecutor`, tại đó task được decorate. Nhưng nếu method được gọi qua `this.generate(...)` trong chính bean, interceptor `@Async` bị bỏ qua ở proxy mode mặc định và decorator không được áp dụng qua đường đó.

Gắn decorator vào **một pool khác** không làm pool do `@Async` chọn có khả năng context propagation. Đây là lỗi cấu hình rất thường gặp khi ứng dụng có nhiều executor.

## 8. Ví dụ đầy đủ Java 17 + Spring Framework + Micrometer

Ví dụ dưới đây không cần servlet container hay hệ thống tracing. Ta đăng ký một accessor cho `ThreadLocal<String>` tự tạo, cấu hình hai executor: một pool **không** có decorator và một pool **có** decorator. Sau đó kiểm tra `@Async` cũng sử dụng pool được decorate.

Ví dụ cố tình làm kết quả có thể kiểm chứng bằng `Future.get(timeout)` thay vì `Thread.sleep(...)`.

### 8.1. Cấu trúc dự án

```text
context-propagation-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── lesson/
                └── ContextPropagationDemo.java
```

### 8.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>lesson</groupId>
    <artifactId>context-propagation-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.7</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.3</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` mang các thành phần Spring cần dùng, còn `context-propagation` là thư viện Micrometer cung cấp registry, snapshot và accessor. Các phiên bản được ghim để demo có cùng dependency khi người học chạy lại; dự án thật nên dùng dependency management của stack.

### 8.3. Tệp src/main/java/lesson/ContextPropagationDemo.java

```java
package lesson;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ContextPropagationDemo {

    private static final ThreadLocal<String> TENANT =
            new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        ContextRegistry registry = ContextRegistry.getInstance();
        registry.registerThreadLocalAccessor(
                "lesson.tenant",
                TENANT::get,
                TENANT::set,
                TENANT::remove);

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(Config.class)) {

            TaskExecutor plain = context.getBean(
                    "plainExecutor", TaskExecutor.class);
            TaskExecutor propagating = context.getBean(
                    "propagatingExecutor", TaskExecutor.class);
            TenantService service = context.getBean(TenantService.class);

            try {
                TENANT.set("tenant-A");
                System.out.println("Không decorator: "
                        + readTenant(plain));
                System.out.println("Có decorator: "
                        + readTenant(propagating));

                TENANT.set("tenant-B");
                System.out.println("Giá trị mới: "
                        + readTenant(propagating));
                System.out.println("@Async: "
                        + service.currentTenant()
                                .get(5, TimeUnit.SECONDS));

                TENANT.remove();
                System.out.println("Sau clear: "
                        + readTenant(propagating));
            } finally {
                TENANT.remove();
            }
        } finally {
            registry.removeThreadLocalAccessor("lesson.tenant");
        }
    }

    private static String readTenant(TaskExecutor executor)
            throws Exception {
        return CompletableFuture
                .supplyAsync(TENANT::get, executor)
                .get(5, TimeUnit.SECONDS);
    }

    private static ThreadPoolTaskExecutor pool(String prefix) {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix(prefix);
        return executor;
    }

    @Configuration
    @EnableAsync
    public static class Config {

        @Bean("plainExecutor")
        public ThreadPoolTaskExecutor plainExecutor() {
            return pool("plain-");
        }

        @Bean("propagatingExecutor")
        public ThreadPoolTaskExecutor propagatingExecutor() {
            ThreadPoolTaskExecutor executor = pool("ctx-");
            executor.setTaskDecorator(
                    new ContextPropagatingTaskDecorator());
            return executor;
        }

        @Bean
        public TenantService tenantService() {
            return new TenantService();
        }
    }

    public static class TenantService {

        @Async("propagatingExecutor")
        public CompletableFuture<String> currentTenant() {
            return CompletableFuture.completedFuture(
                    TENANT.get());
        }
    }
}
```

### 8.4. Biên dịch và chạy

Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=lesson.ContextPropagationDemo
```

Năm dòng **do chương trình in ra khi chạy bình thường**:

```text
Không decorator: null
Có decorator: tenant-A
Giá trị mới: tenant-B
@Async: tenant-B
Sau clear: null
```

Maven có thể in thêm thông báo riêng nếu cách chạy/cấu hình khác đi. Kết quả chương trình là xác định theo logic:

1. `TENANT` là `ThreadLocal` **thường**, không phải `InheritableThreadLocal`. Pool `plainExecutor` chạy trên worker riêng, nên không tự thấy `tenant-A` từ caller.
2. Pool `propagatingExecutor` được trang trí. Khi caller đang chứa `tenant-A`, accessor đọc nó vào snapshot; worker đọc được cùng giá trị trong scope.
3. Caller đổi thành `tenant-B` rồi gửi một task mới. Snapshot mới chứa giá trị mới; task mới không được dùng lại snapshot của task trước.
4. `TenantService.currentTenant()` là method `@Async("propagatingExecutor")` được gọi **qua Spring bean proxy**, nên nó đọc được `tenant-B` từ worker được decorate.
5. Caller gọi `TENANT.remove()` trước lần gửi cuối. Worker không có giá trị tenant còn sót lại; lần đọc cuối trả `null`.
6. `get(5, TimeUnit.SECONDS)` chỉ là cách demo chờ kết quả có giới hạn. Nó chặn `main`; trong HTTP request thật, việc chờ ngay có thể làm request chậm.
7. Context đóng bằng `try-with-resources`; Spring quản lý vòng đời hai bean executor. `ContextRegistry` toàn cục được trả về trạng thái không có accessor `lesson.tenant` khi demo kết thúc.

Mẫu này cố tình không dùng số thứ tự thread để kiểm thử: tên thread là chi tiết vận hành, còn **giá trị tenant** mới là điều cần xác nhận. Để kiểm thử chặt hơn trong dự án thật, hãy kết hợp với theo dõi worker reuse và bảo đảm không rò tenant qua các request đồng thời.

### 8.5. Điều cần tránh khi sao chép demo vào production

- Không dùng `TENANT` như một cơ chế tự quyết định quyền truy cập. Identity/authorization phải được kiểm chứng ở ranh giới nghiệp vụ và bảo mật.
- Không đăng ký lặp accessor toàn cục mỗi khi có HTTP request. Hãy đăng ký một lần theo vòng đời ứng dụng, và xác định ownership khi có nhiều module.
- Không tự thay đổi registry toàn cục của các thư viện khác để “sửa” lỗi context nếu chưa hiểu hệ thống tracing/security của chúng.
- Không tạo hai pool chỉ để chứng minh decorator; demo có pool plain để so sánh trước–sau.
- Không giữ token, request stream hoặc object mutable có vòng đời ngắn trong snapshot.
- Không diễn giải `TENANT.remove()` trên caller là thao tác xóa trực tiếp `ThreadLocal` của worker; việc dọn worker do scope/accessor đảm nhiệm.

## 9. Có thể dùng ContextSnapshotFactory tùy chỉnh thay registry toàn cục

Một ứng dụng lớn có thể muốn một tập accessor **riêng cho một executor**. Micrometer cho phép cấu hình `ContextSnapshotFactory` với một `ContextRegistry` cụ thể:

```java
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

ContextRegistry registry = new ContextRegistry();
registry.registerThreadLocalAccessor(
        "lesson.requestId",
        REQUEST_ID::get,
        REQUEST_ID::set,
        REQUEST_ID::remove);

ContextSnapshotFactory factory =
        ContextSnapshotFactory.builder()
                .contextRegistry(registry)
                .build();

ContextPropagatingTaskDecorator decorator =
        new ContextPropagatingTaskDecorator(factory);

executor.setTaskDecorator(decorator);
```

Đây là **mảnh code cấu hình**; `REQUEST_ID` là `ThreadLocal<String>` của ứng dụng và `executor` là một Spring executor hỗ trợ `setTaskDecorator`. Khác với constructor không tham số, đoạn này **ràng buộc decorator vào factory dùng registry được chỉ định**.

Cách tùy chỉnh có ích khi:

- Muốn test với registry riêng, tránh đụng accessor của cả JVM.
- Chỉ muốn truyền một tập context đã được đánh giá an toàn.
- Muốn kiểm soát cấu hình snapshot (và nếu phiên bản Micrometer hỗ trợ, các tùy chọn xử lý giá trị vắng mặt).
- Có nhiều thư viện đăng ký accessor khác nhau và cần tránh tương tác ngoài chủ đích.

Nhưng registry riêng có thể bỏ sót những accessor quan trọng do các thư viện observability đăng ký trên registry toàn cục. Nếu dùng registry tùy chỉnh, bạn phải biết rõ mình **đã loại bỏ hay giữ lại những loại context nào**. Không tự suy ra mọi span/MDC sẽ xuất hiện nếu factory chỉ nhìn thấy accessor của request ID.

## 10. Logging MDC, Observation và trace context: những trường hợp khác nhau

`ContextPropagatingTaskDecorator` đặc biệt hữu ích cho log correlation và observability, nhưng các khái niệm sau không giống nhau:

| Context | Mục đích | Yêu cầu tích hợp |
|---|---|---|
| Custom `ThreadLocal<String>` | Request ID, tenant ID hoặc thông tin kỹ thuật | Accessor do ứng dụng cung cấp/đăng ký |
| SLF4J/Logback `MDC` | Metadata trong log, ví dụ traceId/correlationId | Tích hợp `ThreadLocalAccessor` tương thích với cơ chế MDC; không giả định có sẵn |
| Micrometer `Observation` | Theo dõi phạm vi quan sát, metrics/tracing khi được cấu hình | Observation registry, accessor/instrumentation thích hợp |
| Trace/span context | Nối chuỗi thao tác trong hệ thống phân tán | Tracing bridge, exporters và context propagation phù hợp |
| Spring Security context | Thông tin xác thực/ủy quyền theo luồng | Cơ chế Spring Security riêng hoặc accessor đã được xác minh |
| Spring transaction context | Ranh giới giao dịch, resource gắn với luồng | **Không** coi là ngữ cảnh được sao chép an toàn sang worker |

**Có thư viện Context Propagation không có nghĩa mọi context đều tự được đăng ký.** Tùy bộ thư viện đang dùng, một số accessor có thể được cung cấp bởi integration/SPI; custom context thường cần đăng ký thủ công. Hãy kiểm tra thực tế `ContextRegistry` và thử một task để xác nhận, thay vì chỉ nhìn thấy dependency trong `pom.xml`.

### 10.1. MDC có tự được truyền không?

Không nên đưa ra một tuyên bố chung rằng mọi phiên bản SLF4J/Logback/Micrometer đều tự truyền MDC. Với hệ sinh thái observability được cấu hình đầy đủ, trace/span context và logging correlation có thể được bridge thông qua accessor/instrumentation. Ở ứng dụng không có bridge thích hợp, cần đăng ký một accessor cho dữ liệu MDC cần truyền hoặc chọn giải pháp log-context propagation tương ứng.

MDC thường là map theo thread. Nếu thực hiện thủ công, phải **copy** map có chủ đích khi capture và khôi phục map cũ trong `finally`; không dùng chung một mutable map giữa các request. Nếu dùng accessor chuyên dụng, phải xác minh nó hỗ trợ reset và không để MDC của request A rò sang request B.

### 10.2. Observation không đồng nghĩa tracing đã bật

Micrometer Observation có thể giúp tạo metric và span khi có handler/tracing bridge được cấu hình. Decorator có thể chuyển observation context sang worker, nhưng **nó không tự phát sinh observation mới hoặc xuất trace** cho mọi code.

Một task chỉ được decorate mà không có Observation hiện hành ở nơi submit có thể không có trace correlation nào để truyền. Hãy kiểm tra điểm bắt đầu observation, các accessor, logging pattern, tracing exporter và dữ liệu log thật.

## 11. SecurityContext và transaction: ranh giới an toàn

### 11.1. Context bảo mật cần chính sách riêng

`SecurityContextHolder` của Spring Security có chiến lược lưu theo thread; chuyển thread thường làm mất context nếu không có cơ chế rõ ràng. Một số integration có thể cung cấp accessor/adapter phù hợp, nhưng **không mặc định rằng `ContextPropagatingTaskDecorator` tự chép toàn bộ security context**.

Spring Security còn có những wrapper và executor riêng như `DelegatingSecurityContextAsyncTaskExecutor`. Khi chọn giải pháp, cần kiểm tra:

- Security context được chụp lúc nào; đang ở bước xác thực hay đã được làm sạch?
- Worker thực sự cần principal hay chỉ cần một ID phi nhạy cảm?
- Context của người dùng A có bị giữ sau khi task xong không?
- Có bị truyền nhầm một principal cũ qua worker pool hoặc callback khác không?
- Quyền được kiểm tra lại ở tác vụ nền nếu nghiệp vụ có thời gian chờ dài không?

Context propagation là **cơ chế vận chuyển thông tin**, không thay thế xác thực/ủy quyền. Không nên sao chép token, password hay đối tượng HTTP request sang worker nếu không có yêu cầu bảo mật được duyệt.

### 11.2. Không truyền transaction của caller như một ThreadLocal tùy ý

Spring transaction thường sử dụng thread-bound resource và trạng thái giao dịch. Truyền các `ThreadLocal` liên quan sang worker **không có nghĩa chuyển được an toàn cùng một transaction** sang luồng khác.

```text
Request thread:
  @Transactional TX-A bắt đầu
       |
       +--> executor gửi task
       |
  TX-A commit/rollback theo caller

Worker thread:
  thực thi độc lập về thời điểm
  không tự tham gia TX-A
  nếu cần transaction: thiết kế TX-B phù hợp ở worker
```

Khi task cần dữ liệu chỉ hợp lệ sau commit, cân nhắc transaction event, outbox hoặc cơ chế điều phối có độ bền phù hợp. Không tự viết `ThreadLocalAccessor` để sao chép raw JDBC connection, `EntityManager` hoặc transaction status của caller.

**Truyền correlation ID** và **truyền quyền truy cập vào resource gắn với thread** là hai vấn đề rất khác nhau.

## 12. @Async, CompletableFuture và mọi bước đổi executor

Một method `@Async("contextExecutor")` đi qua Spring proxy sẽ gửi phần thực thi method đến bean executor có decorator. Nhưng điều đó **không bảo đảm mọi bước CompletableFuture sau này chạy trên cùng executor**.

Ví dụ:

```java
CompletableFuture<Result> future = service.load();

CompletableFuture<String> next = future.thenApplyAsync(
        value -> transform(value));
```

Đây là **mảnh code minh họa**, với `Result` và `transform` do ứng dụng định nghĩa. `thenApplyAsync(...)` không truyền executor có thể dùng executor mặc định của CompletableFuture (thường common pool), nơi **không chắc có context propagation** của `contextExecutor`. Tương tự, `CompletableFuture.supplyAsync(...)` không truyền executor cũng có thể chạy ngoài pool được trang trí.

Nếu cần giữ đường thực thi có context, hãy chọn executor rõ:

```java
CompletableFuture<String> next = future.thenApplyAsync(
        value -> transform(value),
        contextExecutor);
```

Nhưng vẫn phải biết **thread nào đăng ký continuation** và context nào đang hiện hành **ở thời điểm continuation được schedule**. Nếu callback được lên lịch từ một thread không có context, decorator không thể tự tìm lại request ID gốc từ một Future đã hoàn tất.

Với pipeline phức tạp, có thể cần cách chụp snapshot ở ranh giới gốc, một executor/context-aware API, hoặc truyền explicit correlation ID vào từng bước. Không chỉ thêm decorator một lần rồi mặc định propagation xuyên qua mọi thư viện và mọi giai đoạn.

### 12.1. Tránh tạo hai lớp scheduling vô ích

Nếu service đã dùng `@Async("contextExecutor")`, không cần bọc thêm `CompletableFuture.supplyAsync(...)` không truyền executor trong thân method chỉ để “chạy bất đồng bộ hơn”. Làm vậy có thể chuyển công việc sang common pool, mất context và tăng độ phức tạp xử lý lỗi.

Tương tự, phương thức `@Async` trả `CompletableFuture.completedFuture(value)` trong worker **vẫn hợp lệ**: proxy Spring giữ handle bất đồng bộ của lần chạy method, còn method đích cung cấp future tạm đúng chữ ký.

## 13. TaskDecorator không phải cơ chế bắt lỗi task

JavaDoc `ThreadPoolTaskExecutor.setTaskDecorator(...)` nhắc rằng decorator có thể được áp dụng lên **callback thực thi nội bộ**, không phải chính `Runnable`/`Callable` do caller gửi. Với `submit(...)`, callback có thể là `FutureTask`: `FutureTask.run()` thường giữ exception bên trong Future thay vì ném ra khỏi wrapper.

Vì vậy một `TaskDecorator` tự viết kiểu:

```java
return () -> {
    try {
        runnable.run();
    } catch (RuntimeException error) {
        log(error);
        throw error;
    }
};
```

không thể được tin là sẽ log **mọi** lỗi từ `submit(...)`. Mảnh code trên chỉ minh họa cách catch ở wrapper; `runnable` và `log(...)` phải có trong một method/class phù hợp.

`ContextPropagatingTaskDecorator` có nhiệm vụ **đặt lại context xung quanh execution**, không phải xử lý lỗi. Với Spring `@Async void`, lỗi phù hợp có thể đến `AsyncUncaughtExceptionHandler`; với `Future/CompletableFuture`, caller phải quan sát Future; với `ExecutorService` Java thuần, lỗi theo hợp đồng `execute/submit` tương ứng.

Nếu task ném exception, scope của snapshot vẫn cần được đóng trong đường `finally` của cơ chế bọc để tránh rò context. Đây là một lý do nên dùng thư viện có hợp đồng scope rõ thay vì tự `set` rồi quên cleanup.

## 14. CompositeTaskDecorator khi cần nhiều concern

Một ứng dụng có thể cần thêm telemetry, đặt tên nghiệp vụ hoặc ghi thời gian chạy bên cạnh context propagation. Spring cung cấp `CompositeTaskDecorator` để kết hợp nhiều `TaskDecorator`:

```java
import java.util.List;
import org.springframework.core.task.TaskDecorator;
import org.springframework.core.task.support.CompositeTaskDecorator;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;

TaskDecorator timing = runnable -> () -> {
    long start = System.nanoTime();
    try {
        runnable.run();
    } finally {
        long elapsed = System.nanoTime() - start;
        System.out.println("elapsedNs=" + elapsed);
    }
};

TaskDecorator composite = new CompositeTaskDecorator(
        List.of(new ContextPropagatingTaskDecorator(), timing));

executor.setTaskDecorator(composite);
```

Đây là **đoạn code trong class cấu hình** với `executor` hỗ trợ `setTaskDecorator`. Nó không phải chương trình độc lập. Mục đích là chỉ ra cách ghép concern; trong production không dùng `System.out` cho mỗi task vì overhead.

**Thứ tự decorator ảnh hưởng thứ tự mở/đóng scope và thứ tự code đo thời gian.** Khi logging/timing decorator cần quan sát context đã được khôi phục, hãy kiểm thử thứ tự bọc thay vì suy luận theo cách đặt vào danh sách. Nếu hai decorator cùng thay một `ThreadLocal`, quy tắc cleanup phải tương thích, nếu không có thể ghi đè nhầm giá trị.

## 15. Quan sát và hiệu năng: không phải context nào cũng đáng chụp

Theo JavaDoc Spring, `ContextPropagatingTaskDecorator` có overhead và **không được khuyến nghị áp dụng mù quáng cho số lượng rất lớn tác vụ cực nhỏ**.

Các chi phí có thể bao gồm:

- Đọc các accessor đã đăng ký khi task được gửi.
- Tạo snapshot và wrapper cho mỗi task (tùy implementation).
- Đặt/khôi phục các giá trị trong `ThreadLocal` quanh mỗi lần thực thi.
- Phân bổ thêm object, áp lực GC và công việc của logging/tracing integration.
- Truyền quá nhiều dữ liệu context không cần thiết cho task.

Nếu task chỉ tăng một counter trong vài microsecond, overhead có thể đáng kể so với nghiệp vụ; nếu task gọi I/O hàng trăm millisecond, chi phí đó thường nhỏ hơn nhưng vẫn nên đo trên workload thực.

Gợi ý kiểm chứng:

1. Benchmark hai cấu hình cùng tải: có và không decorator, giữ nguyên số worker/queue.
2. Đo `task queue wait`, `run duration`, p95/p99 và throughput.
3. Đo allocated bytes/GC, kích thước snapshot và số accessor tham gia.
4. Đo khả năng trace/log correlation tăng lên có thực sự hữu ích không.
5. Giới hạn context vào những dữ liệu thật sự cần cho worker.
6. Không đặt token hoặc object request lớn vào ThreadLocal chỉ để chúng “đi theo” mọi task.

Lưu ý phân biệt **thông lượng**, **chi phí mỗi task** và **độ chính xác của ngữ cảnh**. Bật decorator mà tác vụ chạy được không đủ để nói integration đáp ứng yêu cầu vận hành.

## 16. Spring Boot: tự cấu hình không thay việc hiểu executor thực tế

Với một số phiên bản Spring Boot có hỗ trợ, tài liệu observability cung cấp thuộc tính:

```properties
spring.task.execution.propagate-context=true
```

Thuộc tính này có ý nghĩa **opt-in propagation cho AsyncTaskExecutor do Spring Boot tự cấu hình**. **Không phải mọi phiên bản Boot đều có thuộc tính này**, và nó không nên được dùng như bằng chứng một executor **tự đăng ký** đã có decorator.

Tài liệu Boot còn chỉ ra: nếu tự định nghĩa `AsyncTaskExecutor`, hãy cấu hình `ContextPropagatingTaskDecorator` phù hợp — chẳng hạn khai báo decorator bean hoặc gắn trực tiếp vào executor theo khả năng của phiên bản — thay vì kỳ vọng thuộc tính tự động thay đổi mọi pool tùy chỉnh.

Trong một hệ thống cụ thể, cần xác định:

- Phiên bản Spring Boot và `spring-context` thực tế.
- Bean `TaskExecutor`/`AsyncTaskExecutor` mà `@Async` đang dùng.
- Bean được Boot tạo hay do ứng dụng tự tạo.
- Có dependency `context-propagation` trong runtime không.
- Accessor/registry có được khởi tạo trước khi task gửi không.
- Các đường khác như `@Scheduled`, `CompletableFuture` hoặc thư viện bên ngoài có đi qua executor ấy không.

**Không nhầm với** `spring.reactor.context-propagation=auto`: đây là cấu hình cho cơ chế propagation của Reactor trong các phiên bản Boot hỗ trợ, không phải một lệnh toàn cục ép mọi Java thread pool sao chép ThreadLocal.

## 17. Reactor Context khác ThreadLocal context

Trong Spring WebFlux/Reactor, dữ liệu ngữ cảnh thường được đặt trong `reactor.util.context.Context` gắn với pipeline reactive. Nó không đồng nhất với `ThreadLocal`:

- `ThreadLocal` gắn với thread đang thực thi.
- Reactor `Context` gắn với chuỗi subscription/Publisher.
- Một pipeline reactive có thể đổi thread qua `publishOn`/`subscribeOn` mà không có nghĩa ThreadLocal hiện hành được giữ đúng theo thread mới.

Micrometer Context Propagation cung cấp `ContextAccessor` và các cơ chế snapshot để **chuyển giữa các kiểu context** khi được cấu hình. `ContextPropagatingTaskDecorator` hữu ích tại **ranh giới Runnable của TaskExecutor**, nhưng không tự biến mọi operator Reactor thành một đối tượng có MDC/ThreadLocal được khôi phục.

Nếu ứng dụng chuyển từ WebFlux sang `@Async` hoặc ngược lại, cần kiểm tra rõ:

1. Context nguồn là Reactor Context hay ThreadLocal?
2. Khi nào và ở đâu snapshot được capture?
3. Accessor thích hợp đã đăng ký chưa?
4. Executor/reactive operator nào chịu trách nhiệm restore?
5. Có thể làm mất/ghi đè các key context giữa các scope không?

Với trường hợp chỉ cần request ID để ghi log một task đơn giản, truyền explicit ID qua tham số còn dễ kiểm soát hơn việc dựng pipeline propagation phức tạp.

## 18. Ranh giới cần chọn giải pháp khác

| Nhu cầu | ContextPropagatingTaskDecorator có đủ không? | Giải pháp/kiểm tra thêm |
|---|---|---|
| Truyền custom request ID qua `ThreadPoolTaskExecutor` | Có thể, **khi accessor đã đăng ký** | Test capture/restore, cleanup |
| Giữ trace correlation cho `@Async` | Có thể, với observability integration phù hợp | Kiểm tra tracing bridge/accessor và đúng executor |
| Truyền MDC mọi logging framework | Không có bảo đảm chung | Đánh giá accessor và logging stack |
| Truyền Spring Security context | Không mặc nhiên | Cân nhắc Spring Security wrappers/bridge phù hợp |
| Giữ transaction của caller trên worker | **Không** | Mở transaction riêng, điều phối sau commit |
| Tự truyền context qua Java `ExecutorService` thuần | Không tự | Bọc task/executor hoặc chọn Spring executor có decorator |
| Truyền context qua mọi `CompletableFuture.*Async` | Không tự | Truyền executor phù hợp, xác định context ở lúc schedule |
| Truyền context sang JVM/service khác | Không | HTTP headers, messaging metadata, tracing propagation qua mạng |
| Đảm bảo task sống qua restart | Không | Hàng đợi bền vững, outbox, persistence |
| Giới hạn worker/queue/backpressure | Không | Cấu hình executor, load shedding, rejection policy |

**Điểm khó nhất:** truyền context không tạo ra **quan hệ giao dịch, quyền hạn hay độ bền công việc** giữa caller và worker. Nó chỉ đưa những giá trị được phép và được hỗ trợ đến phạm vi thực thi tương ứng.

## 19. Những lỗi triển khai và cách khắc phục

| Sai lầm | Triệu chứng | Sửa đúng |
|---|---|---|
| Thêm decorator nhưng không có `context-propagation` | Runtime thiếu lớp Micrometer | Khai báo dependency tương thích ở runtime |
| Dùng Spring cũ hơn 6.1 | Không tìm được class decorator | Nâng phiên bản Spring có API đó |
| Chỉ tạo `new ContextPropagatingTaskDecorator()` mà không gắn vào pool | Worker vẫn mất context | `executor.setTaskDecorator(...)` trên **pool đang dùng** |
| Đăng ký custom accessor vào registry riêng nhưng decorator dùng registry toàn cục | Task thấy `null` | Truyền factory sử dụng đúng registry |
| Tưởng mọi `ThreadLocal` tự được truyền | Tenant/MDC không xuất hiện | Đăng ký/kiểm tra `ThreadLocalAccessor` tương ứng |
| Thay `ThreadLocal` sau khi submit rồi mong worker thấy bản mới | Worker dùng giá trị cũ | Hiểu snapshot ở thời điểm schedule; gửi task mới nếu cần |
| Dùng `InheritableThreadLocal` để “sửa” thread pool | Giá trị có thể stale/sai yêu cầu | Truyền context có scope/restore rõ ràng |
| Tự set context trên worker nhưng quên remove | Request B đọc dữ liệu request A | Dùng scope/finally và test worker reuse |
| `@Async` gọi nội bộ `this.method()` | Không đi qua proxy, decorator không chạy | Gọi bean khác qua Spring proxy |
| `@Async` dùng executor khác với bean được decorate | Chỉ một vài task có context | Chỉ rõ `@Async("contextExecutor")` |
| `CompletableFuture.supplyAsync(...)` không truyền executor | Context có thể mất ở common pool | Cung cấp executor và capture đúng lúc |
| Xem context snapshot là sao chép sâu object | Shared mutable object gây race | Dùng immutable value hoặc ownership rõ |
| Sao chép transaction/JDBC resource sang worker | Lỗi transaction hoặc sử dụng tài nguyên sai luồng | Tạo transaction/resource riêng |
| Giả định có trace chỉ nhờ decorator | Không có span/export | Cấu hình observation/tracing bridge |
| Dùng decorator để bắt lỗi `submit` | Exception nằm trong Future | Quan sát `Future.get/CompletableFuture` |
| Bật cho hàng triệu task cực nhỏ mà không đo | Tăng allocation/CPU/GC | Benchmark, giới hạn context, chọn đường khác |

## 20. Kiểm thử đúng: truyền, không truyền và không rò rỉ

Để đánh giá một tính năng context propagation, không chỉ kiểm thử trường hợp “một request một task”.

### 20.1. Bộ kiểm thử tối thiểu

1. **Có context:** Caller set `requestId=A` rồi gửi task vào executor có decorator; worker phải thấy A.
2. **Không có decorator:** Gửi vào pool thường; worker không được vô tình thấy ThreadLocal A của caller.
3. **Đổi context:** Caller đổi thành B trước khi gửi task thứ hai; worker phải thấy B cho task đó, không phải A.
4. **Caller clear:** Sau khi caller remove context, task kế tiếp trên cùng worker phải không thấy A/B.
5. **Tác vụ lỗi:** Task ném exception; scope vẫn đóng, lần gửi kế tiếp không rò context của task lỗi.
6. **Nhiều worker:** Các task xen kẽ thuộc tenant khác nhau phải giữ đúng mỗi snapshot, không bị lẫn.
7. **Thử khi queue chờ:** Caller đổi context sau khi task đã được queue; worker vẫn dùng snapshot tại thời điểm submit.
8. **Nhiều executor:** Một executor có decorator, một executor không; xác nhận ranh giới nào thật sự hỗ trợ.
9. **Không có accessor:** Chứng minh custom ThreadLocal không được propagate khi chưa có bridge.
10. **Dependency runtime:** Đảm bảo deploy artifact chứa jar Micrometer và đúng phiên bản; không chỉ compile pass.

### 20.2. Tránh test dựa vào Thread.sleep

`Thread.sleep(100)` không bảo đảm worker chạy/handler cleanup xong. Dùng `CountDownLatch`, `Future.get(timeout)` hoặc `CompletableFuture` để chờ mốc cụ thể, đặt timeout hữu hạn cho integration test.

Ở demo mục 8, `get(5, TimeUnit.SECONDS)` giúp test có điểm chờ rõ ràng và thất bại khi môi trường không đáp ứng. Với test concurrency tải cao, nên dùng latch/queue có kiểm soát thay vì phụ thuộc vào thứ tự in log của các worker.

### 20.3. Kiểm chứng lỗi thiếu accessor riêng biệt

Nếu không đăng ký accessor cho `TENANT` mà vẫn gắn decorator vào executor, worker có thể không thấy tenant. Điều đó không chứng minh Spring decorator không hoạt động; nó cho biết registry không có cầu nối tới giá trị đó. Test cần phân biệt **thiếu dependency**, **thiếu accessor** và **chọn sai executor**, vì cách sửa khác nhau.

## 21. Checklist triển khai thực tế

Khi một PR thêm `ContextPropagatingTaskDecorator`, hãy lần lượt hỏi:

1. **Phiên bản:** Spring Framework có API từ 6.1+, dependency Micrometer Context Propagation tồn tại trong **runtime** và tương thích?
2. **Registry:** Dữ liệu cần truyền có accessor? Accessor được đăng ký vào registry mà decorator/factory thật sự dùng?
3. **Thời điểm:** Context đã được set trên thread gửi **trước** khi executor nhận task?
4. **Đường thực thi:** Task hoặc `@Async` có đi qua đúng `TaskExecutor` đã gắn decorator?
5. **Scope:** Context có được restore/reset sau mỗi task, kể cả khi ném exception?
6. **Bảo mật:** Không truyền token, principal hoặc request object trái quyền; không dùng propagation thay authorization?
7. **Transaction:** Không cố sao chép transaction/resource gắn với caller thread?
8. **Reactive boundary:** Có pipeline Reactor hay CompletableFuture chuyển executor khác cần chiến lược bổ sung?
9. **Hiệu năng:** Đo overhead context snapshot và tác động ở p95/p99 khi task ngắn hoặc submit quá nhiều?
10. **Vòng đời:** Registry/global accessor được đăng ký nhất quán, không lặp mỗi request; executor có giới hạn worker/queue?
11. **Tính quan sát:** Có kiểm tra log/trace thật, không suy từ việc jar đã được thêm?
12. **Test:** Có test worker reuse, task lỗi, context vắng mặt và nhiều tenant?
13. **Giới hạn cam kết:** Không tuyên bố decorator bảo đảm việc, retry, trace export, rollback hoặc truyền thông tin sang hệ thống ngoài.

## 22. Bài tập thực hành và đáp án gợi ý

### Bài 1 — Phân biệt hai dependency

Ứng dụng có Spring Framework 6.2.x nhưng thiếu `io.micrometer:context-propagation`. Developer thêm `new ContextPropagatingTaskDecorator()`. Việc gì có thể xảy ra?

**Gợi ý:** Thiếu lớp Micrometer tại runtime, có thể gặp `NoClassDefFoundError` hoặc lỗi khởi tạo. Thêm dependency hợp lệ và kiểm tra đúng scope/classpath.

### Bài 2 — Thiếu accessor

Ứng dụng đã gắn decorator vào `ThreadPoolTaskExecutor` nhưng custom `ThreadLocal<String> TENANT` vẫn null trên worker. Cần kiểm tra ba điều gì?

**Gợi ý:** (1) Registry có `ThreadLocalAccessor` cho TENANT không, (2) decorator dùng đúng registry/factory không, (3) caller set TENANT trước khi submit và task đi qua đúng executor không.

### Bài 3 — Snapshot theo thời điểm

Caller set `requestId=R1` rồi `execute(task)`; ngay sau đó đổi thành `R2` trước lúc worker bắt đầu. Task phải nhìn thấy giá trị nào khi context được capture đúng?

**Gợi ý:** R1 — snapshot đã chụp lúc schedule, không phải giá trị mới trên caller.

### Bài 4 — Kiểm tra rò context

Pool chỉ có một worker. Task A thuộc tenant X; task B thuộc tenant Y; task C không có tenant. Thứ tự giá trị nào cần có ở worker nếu truyền đúng và cleanup sạch?

**Gợi ý:** X, Y, rồi null. Nếu C thấy X hoặc Y thì cần điều tra cleanup, accessor reset và baseline thread.

### Bài 5 — @Async gọi nội bộ

Method `start()` trong cùng bean gọi `this.reportAsync()`, mặc dù `reportAsync()` gắn `@Async("contextExecutor")`. Vì sao decorator không có tác dụng như mong muốn?

**Gợi ý:** Self-invocation không đi qua Spring proxy ở chế độ mặc định. Tách thành bean khác để lời gọi được intercept.

### Bài 6 — Continuation ngoài executor

Method `@Async("contextExecutor")` trả CompletableFuture; caller dùng `thenApplyAsync(...)` không truyền executor. Có bảo đảm continuation nhận context từ method đầu không?

**Gợi ý:** Không. Continuation có thể chạy trên common pool; cần chọn executor và xác định context tại thời điểm schedule hoặc dùng cơ chế propagation riêng.

### Bài 7 — Security và transaction

Một task cần đọc dữ liệu tenant và ghi database. Có nên truyền thẳng JDBC Connection và SecurityContext qua custom ThreadLocalAccessor cho worker không?

**Gợi ý:** Không tự ý sao chép resource/transaction thread-bound hoặc dữ liệu bảo mật; dùng các abstraction và ranh giới authorization/transaction phù hợp ở worker.

### Bài 8 — Chạy Maven demo

Chạy project `ContextPropagationDemo`, xác nhận năm dòng output. Sau đó bỏ `registerThreadLocalAccessor(...)` và giải thích vì sao pool có decorator vẫn không có custom tenant.

**Gợi ý:** Không có accessor, snapshot không thể đọc/đặt TENANT. Decorator là hạ tầng bọc task; registry xác định context nào được hỗ trợ.

## 23. Tổng kết

- **`ContextPropagatingTaskDecorator` (Spring 6.1+)** hỗ trợ chụp và khôi phục context tại ranh giới thực thi `Runnable` của một executor phù hợp.
- **Điều kiện tích hợp thiết yếu:** `io.micrometer:context-propagation` phải có trên runtime classpath và có `ThreadLocalAccessor`/`ContextAccessor` phù hợp với dữ liệu cần truyền.
- **Không có phép màu tự sao chép mọi ThreadLocal.** Custom request ID/tenant cần một accessor đúng và đăng ký vào registry mà snapshot factory sử dụng.
- **Gắn decorator vào đúng executor**, ví dụ `ThreadPoolTaskExecutor.setTaskDecorator(...)`; với `@Async` cần thêm `@EnableAsync` và lời gọi qua proxy.
- **Snapshot phản ánh context tại thời điểm gửi**; worker tạm thiết lập context trong scope và khôi phục sau khi task chạy, tránh lẫn dữ liệu giữa các request.
- **Không đồng nhất logging, Observation, tracing, security và transaction.** Mỗi cơ chế cần tích hợp, quyền truy cập và kiểm chứng riêng.
- **Không bỏ qua overhead, scope hoặc lỗi Future.** Decorator không tạo worker, không bắt mọi exception, không bảo đảm job bền vững và không tự truyền context qua mọi pipeline.
- **Kiểm thử có/không decorator, đổi giá trị, clear, lỗi, worker reuse và đúng executor** là bằng chứng vận hành đáng tin hơn việc chỉ thêm dependency.

### Tài liệu chính thức

- [Spring Framework API — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [Spring Framework API — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework Reference — Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html)
- [Micrometer Context Propagation — Examples](https://docs.micrometer.io/context-propagation/reference/usage.html)
- [Micrometer Context Propagation — Installing](https://docs.micrometer.io/context-propagation/reference/installing.html)
- [Micrometer ContextRegistry API](https://javadoc.io/doc/io.micrometer/context-propagation/1.1.3/io/micrometer/context/ContextRegistry.html)
- [Spring Boot Reference — Observability and Context Propagation](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
