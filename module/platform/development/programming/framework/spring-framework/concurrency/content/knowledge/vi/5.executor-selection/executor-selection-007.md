# DefaultManagedTaskExecutor trong môi trường Jakarta EE

## 1. Vì sao ứng dụng Spring chạy trong Jakarta EE cần bộ thực thi do container quản lý?

Trong Java SE, một ứng dụng có thể trực tiếp dùng `Executors.newFixedThreadPool(...)` để tạo và quản lý các luồng xử lý nền. Khi ứng dụng Spring được triển khai **bên trong một Jakarta EE application server**, câu chuyện khác: server quản lý vòng đời ứng dụng, tài nguyên dùng chung, định danh bảo mật, classloader, naming context và khả năng kiểm soát tải. Tác vụ nền thường nên chạy bằng **luồng do application server quản lý (managed threads)** thay vì một pool tự tạo mà server không biết cách theo dõi hoặc dọn dẹp.

Spring cung cấp lớp:

```java
org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor
```

Lớp này nối **giao diện thực thi tác vụ của Spring** với **executor có sẵn trong JNDI** của môi trường triển khai. Mặc định nó tra cứu:

```text
java:comp/DefaultManagedExecutorService
```

Đây là tên tài nguyên chuẩn của `ManagedExecutorService` trong Jakarta Concurrency (trước đây được biết qua JSR-236). Server Jakarta EE tương thích cung cấp executor và chịu trách nhiệm quản lý các worker thread, năng lực xử lý, ngữ cảnh thực thi và vòng đời của tài nguyên. Spring nhận executor đã được cấp sẵn rồi chuyển các lời gọi `TaskExecutor.execute(...)` hoặc `AsyncTaskExecutor.submit(...)` sang executor ấy.

**Mô hình cần nhớ:**

```text
Lời gọi ứng dụng / @Async
          |
          v
TaskExecutor / AsyncTaskExecutor (Spring)
          |
          v
DefaultManagedTaskExecutor
          |
          | lookup JNDI khi bean khởi tạo
          v
java:comp/DefaultManagedExecutorService
          |
          v
ManagedExecutorService của Jakarta EE server
          |
          +-- luồng do server quản lý
          +-- cơ chế cấp phát và giới hạn tài nguyên của server
          +-- ngữ cảnh Jakarta EE theo cấu hình/tập hợp bảo đảm
          +-- vòng đời do server sở hữu
```

**DefaultManagedTaskExecutor không phải bộ tạo thread pool mới.** Nó là một bộ **ủy quyền/thích nghi (adapter)** để ứng dụng Spring gửi việc đến một `java.util.concurrent.Executor` được tìm thấy qua JNDI; trong trường hợp chuẩn, đối tượng đó là `jakarta.enterprise.concurrent.ManagedExecutorService`. Phần nhận biết và thích nghi khi delegate là managed executor nằm ở lớp cha `ConcurrentTaskExecutor`.

Mục tiêu của bài: hiểu đúng hợp đồng, cấu hình Spring, cơ chế lookup JNDI, cách dùng với `@Async` hoặc gửi `Runnable` trực tiếp, quản lý kết quả/lỗi, giới hạn lan truyền ngữ cảnh và những lỗi triển khai cần tránh.

## 2. Vị trí trong hệ thống API

### 2.1. Các kiểu và quan hệ kế thừa

```text
java.util.concurrent.Executor
  └─ execute(Runnable)

org.springframework.core.task.TaskExecutor
  └─ execute(Runnable)

org.springframework.core.task.AsyncTaskExecutor
  ├─ execute(Runnable)
  └─ submit(Runnable/Callable)

ConcurrentTaskExecutor
  └─ triển khai AsyncTaskExecutor,
     thích nghi với java.util.concurrent.Executor bất kỳ
          ^
          |
DefaultManagedTaskExecutor
  ├─ extends ConcurrentTaskExecutor
  ├─ implements InitializingBean
  ├─ tra cứu JNDI trong afterPropertiesSet()
  └─ delegate cho Executor đã tìm được

jakarta.enterprise.concurrent.ManagedExecutorService
  └─ extends java.util.concurrent.ExecutorService
     (là tài nguyên Jakarta EE, không phải lớp con của Spring executor)
```

Một số điểm dễ nhầm:

- `DefaultManagedTaskExecutor` là **lớp Spring**, gói `org.springframework.scheduling.concurrent`.
- `ManagedExecutorService` là **giao diện Jakarta Concurrency**, gói `jakarta.enterprise.concurrent` ở các phiên bản Jakarta hiện đại.
- `Executors` (số nhiều) là lớp factory của Java SE; **không** phải tên khác của `DefaultManagedTaskExecutor`.
- `ThreadPoolTaskExecutor` là bean Spring tự điều hành pool theo cấu hình ứng dụng; `DefaultManagedTaskExecutor` **dùng executor đã thuộc quyền quản lý của server**.
- `ConcurrentTaskExecutor` là adapter chung cho một `Executor` được cung cấp sẵn; `DefaultManagedTaskExecutor` thêm việc tra cứu JNDI theo quy ước.

JavaDoc Spring mô tả lớp này từ Spring Framework 4.0, và hiện diện cả trong Spring Framework 6.x/7.x. Dòng mô tả cũ nhắc “JSR-236” vì tên đặc tả ban đầu; khi làm việc với Jakarta EE mới, hãy dùng các package `jakarta.*` tương ứng của môi trường hiện tại thay vì sao chép `javax.enterprise.concurrent.*` từ ví dụ Java EE cũ.

### 2.2. Vì sao không gọi ManagedExecutorService trực tiếp?

Có thể dùng trực tiếp `ManagedExecutorService` khi viết một thành phần Jakarta EE. Tuy nhiên, trong ứng dụng Spring, việc phụ thuộc vào `TaskExecutor` hoặc `AsyncTaskExecutor` giúp service không biết tên tài nguyên JNDI hay cấu hình server. Một cấu hình runtime có thể chọn `DefaultManagedTaskExecutor`, còn cấu hình local/test chọn executor khác.

`DefaultManagedTaskExecutor` đặc biệt hữu ích khi muốn dùng chung một giao diện Spring cho:

1. Lời gọi `TaskExecutor.execute(Runnable)` trực tiếp.
2. Phương thức Spring `@Async("managedTaskExecutor")`.
3. Các phần mềm Spring yêu cầu một executor dạng `TaskExecutor` hoặc `AsyncTaskExecutor`.

Nó không phải cơ chế chạy tác vụ bền vững giữa các lần restart, không thay thế message broker, và cũng không tự bảo đảm thao tác nền sẽ chạy thành công trong mọi tình huống.

## 3. JNDI và tài nguyên mặc định của Jakarta EE

### 3.1. JNDI là gì trong ví dụ này?

JNDI (Java Naming and Directory Interface) là API Java cho phép lookup một đối tượng đã được ràng buộc dưới tên quản lý của runtime. Với Jakarta Concurrency, application server cung cấp mặc định:

```text
java:comp/DefaultManagedExecutorService
```

Tên này tham chiếu đến một `ManagedExecutorService` mà server đã tạo/cấu hình. Việc lookup không tự sinh một executor mới; nó lấy một tham chiếu đến đối tượng server cho phép thành phần ứng dụng sử dụng.

Theo Jakarta Concurrency, dịch vụ mặc định có thể truyền ít nhất ngữ cảnh **naming**, **classloader** và **security** từ thành phần đã gửi công việc, theo quy tắc của đặc tả. Những ngữ cảnh này có mục tiêu giúp tác vụ thực thi đúng môi trường Jakarta EE; không có nghĩa mọi loại `ThreadLocal` tùy ý của ứng dụng được sao chép.

### 3.2. Luồng khởi tạo bean

Khi `DefaultManagedTaskExecutor` là bean trong Spring, nó triển khai `InitializingBean`. Sau khi thiết lập các property, Spring gọi `afterPropertiesSet()`. Lớp thực hiện lookup JNDI với tên đã cấu hình (mặc định là tên chuẩn ở trên), yêu cầu kiểu `Executor`, rồi đặt đối tượng đó làm delegate cho `ConcurrentTaskExecutor`.

```text
Spring tạo bean
   |
   v
new DefaultManagedTaskExecutor()
   |
   +-- setJndiName(...), setResourceRef(...), nếu được cấu hình
   |
   v
afterPropertiesSet()
   |
   +-- JNDI lookup(name, Executor.class)
   |
   +-- thành công -> setConcurrentExecutor(foundExecutor)
   |
   +-- thất bại -> lỗi lookup/khởi tạo bean; cần sửa runtime/tên/mapping
```

**Không có cơ chế fallback mặc định sang một pool tự tạo khi JNDI lookup thất bại.** Nếu chạy ứng dụng trong môi trường Java SE hoặc embedded servlet container không cung cấp tài nguyên này, cấu hình bean có thể thất bại khi khởi động. Cần chọn executor phù hợp với runtime thay vì giả định chỉ thêm dependency Jakarta Concurrency là JNDI resource sẽ tự xuất hiện.

### 3.3. Tên đầy đủ và tên tương đối

API cấu hình đáng chú ý:

| Phương thức | Mục đích | Lưu ý |
|---|---|---|
| `setJndiName(String)` | Thay tên JNDI mặc định bằng executor do server công bố | Tên phải tồn tại và đối tượng phải thích hợp với `Executor` |
| `setResourceRef(boolean)` | Điều chỉnh cách nhận diện tên tương đối trong môi trường `java:comp/env/` | Không tự sinh resource mới trên server |
| `setJndiTemplate(JndiTemplate)` | Tùy biến đối tượng thực hiện JNDI lookup | Chủ yếu cho tích hợp/test hoặc môi trường JNDI đặc thù |
| `setJndiEnvironment(Properties)` | Cung cấp property JNDI nếu runtime yêu cầu | Thường không cần khi JNDI của container đã có sẵn |

Với tên **đầy đủ** `java:comp/DefaultManagedExecutorService`, thông thường không cần thêm `java:comp/env/`. Nếu dùng tên tương đối và `resourceRef=true`, quy tắc lookup có thể thêm prefix `java:comp/env/`. Không nên sửa tên mặc định chỉ vì thấy “env” xuất hiện trong các ví dụ khác.

## 4. Ví dụ Spring: đăng ký executor từ JNDI

Mẫu Java Configuration sau dùng cho một ứng dụng Spring Framework chạy **trong Jakarta EE server có cung cấp tài nguyên JNDI mặc định**.

**Tệp `ManagedExecutorConfiguration.java`**

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor;

@Configuration
@EnableAsync
public class ManagedExecutorConfiguration {

    @Bean("managedTaskExecutor")
    public DefaultManagedTaskExecutor managedTaskExecutor() {
        return new DefaultManagedTaskExecutor();
    }
}
```

Đây là **class cấu hình Spring**, không phải một chương trình Java SE độc lập với `main`. Để hoạt động, ứng dụng cần Spring Framework phù hợp trên classpath, được khởi tạo bằng Spring ApplicationContext, và được triển khai trong Jakarta EE runtime cung cấp `java:comp/DefaultManagedExecutorService`. Lớp này không tạo hoặc cấu hình một pool mới.

Tại sao dùng `@EnableAsync`? Vì annotation này kích hoạt cơ chế Spring xử lý phương thức `@Async`. Nó **không bắt buộc** khi ứng dụng chỉ inject `TaskExecutor` rồi gọi `execute(...)` thủ công. Nhưng muốn `@Async` hoạt động qua proxy Spring thì cần bật hỗ trợ async theo cấu hình ứng dụng.

Tên `managedTaskExecutor` được khai báo rõ để các phương thức `@Async` có thể chọn đúng executor. Nếu ứng dụng có nhiều executor, đừng phụ thuộc vào việc Spring tự chọn một bean nào đó theo tình cờ.

### 4.1. Chọn JNDI name khác

Nếu người quản trị server tạo một resource riêng và công bố tại `java:comp/env/concurrent/ReportingExecutor`, có thể cấu hình:

```java
@Bean("managedTaskExecutor")
public DefaultManagedTaskExecutor managedTaskExecutor() {
    DefaultManagedTaskExecutor executor =
            new DefaultManagedTaskExecutor();

    executor.setJndiName(
            "java:comp/env/concurrent/ReportingExecutor");
    return executor;
}
```

Đây là **phương thức bean thay thế** phương thức trong `ManagedExecutorConfiguration`, không phải phương thức thứ hai được định nghĩa cùng tên trong cùng lớp. Server phải có cấu hình/mapping tương ứng. Tên ví dụ không phải một resource được Jakarta EE tự bảo đảm; hãy kiểm tra tài liệu và cấu hình của application server thực tế.

Không nên gọi `afterPropertiesSet()` thủ công trong phương thức bean trên. Khi tạo bean qua Spring, container sẽ xử lý lifecycle và gọi phương thức đó sau khi các property đã được cấu hình.

### 4.2. Cấu hình XML nếu dự án dùng XML

Cùng ý tưởng có thể biểu đạt bằng bean XML:

```xml
<bean id="managedTaskExecutor"
      class="org.springframework.scheduling.concurrent.DefaultManagedTaskExecutor" />
```

Đây là **mảnh XML cấu hình Spring**, cần namespace/khai báo XML đầy đủ ở file chứa nó. Spring khởi tạo bean rồi thực hiện JNDI lookup khi container bắt đầu. Có thể thêm property `jndiName` nếu cần tài nguyên khác.

## 5. Ví dụ @Async chạy trên managed executor

**Tệp `ReportService.java`**

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("managedTaskExecutor")
    public CompletableFuture<String> buildReport(String reportId) {
        // Giả lập phần tính toán hoặc gọi dịch vụ bên ngoài.
        String result = "Báo cáo " + reportId + " đã tạo";
        return CompletableFuture.completedFuture(result);
    }
}
```

**Tệp `ReportControllerOrCaller.java`** — ví dụ một Spring component khác gọi service:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.stereotype.Component;

@Component
public class ReportControllerOrCaller {
    private final ReportService reportService;

    public ReportControllerOrCaller(ReportService reportService) {
        this.reportService = reportService;
    }

    public CompletableFuture<String> request(String reportId) {
        return reportService.buildReport(reportId);
    }
}
```

Hai đoạn trên là **các class thành phần Spring**; để chạy thực sự còn cần cấu hình khởi tạo Spring, dependency và server Jakarta EE như đã nói. Không có stdout cố định: thứ tự chạy và thời gian hoàn tất phụ thuộc managed executor.

Cơ chế:

1. `ReportControllerOrCaller` nhận `ReportService` qua dependency injection. Lời gọi từ bean khác đi qua Spring proxy.
2. `@Async("managedTaskExecutor")` yêu cầu Spring dùng bean executor có tên đã chỉ định.
3. Spring gửi công việc vào executor; `DefaultManagedTaskExecutor` ủy quyền cho `ManagedExecutorService` nhận từ JNDI.
4. Worker do Jakarta EE server quản lý thực thi thân phương thức; kết quả được quan sát qua `CompletableFuture<String>`.
5. Caller có thể xử lý hoàn tất hoặc ngoại lệ mà không cần chặn ngay luồng request.

**Cẩn thận với self-invocation:** Nếu chính `ReportService` gọi `this.buildReport(...)` từ một phương thức của nó, lời gọi thường không đi qua proxy Spring nên không kích hoạt hành vi `@Async` ở chế độ proxy mặc định. Hãy thiết kế một bean gọi qua bean khác hoặc dùng cơ chế proxy/AspectJ có chủ đích, tùy ứng dụng.

### 5.1. @Async không có nghĩa mọi bước tiếp theo đều ở managed executor

Nếu phía gọi sử dụng các phép kết hợp `CompletableFuture`, cần biết chúng được chạy trên executor nào. Những lời gọi `thenApplyAsync(...)` hoặc `CompletableFuture.supplyAsync(...)` **không truyền executor** có thể dùng executor mặc định của CompletableFuture/Java SE. Không nên giả định mọi callback sẽ tiếp tục chạy bằng `ManagedExecutorService` chỉ vì giai đoạn đầu bắt đầu từ `@Async`.

Khi cần một callback cụ thể chạy bằng managed executor, hãy truyền executor đó vào overload nhận `Executor`, hoặc dùng cơ chế hoàn tất bất đồng bộ do `ManagedExecutorService` cung cấp trực tiếp theo phiên bản Jakarta Concurrency đang dùng.

### 5.2. Ngoại lệ của @Async

Với phương thức trả `CompletableFuture<T>`, caller nên quan sát lỗi qua `whenComplete(...)`, `handle(...)`, `exceptionally(...)` hoặc `get()/join()` ở nơi được phép chờ. Nếu `@Async` trả `void`, caller không có đối tượng kết quả để nhận lỗi; Spring cung cấp `AsyncUncaughtExceptionHandler` để xử lý các ngoại lệ đó.

Không dùng `join()` ngay trong luồng nhận HTTP request nếu mục tiêu là không chặn request. Điều phối kết quả theo hợp đồng của endpoint, timeout và khả năng của runtime.

## 6. Gửi tác vụ trực tiếp qua TaskExecutor

Không nhất thiết phải dùng `@Async`. Một service có thể nhận trực tiếp `TaskExecutor` bằng constructor injection và gửi `Runnable`:

**Tệp `AuditDispatchService.java`**

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.core.task.TaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class AuditDispatchService {
    private final TaskExecutor executor;

    public AuditDispatchService(
            @Qualifier("managedTaskExecutor") TaskExecutor executor) {
        this.executor = executor;
    }

    public void dispatch(String eventId) {
        executor.execute(() -> {
            // Minh họa tác vụ độc lập với caller.
            System.out.println("Đã xử lý sự kiện: " + eventId);
        });
    }
}
```

Đây là **thành phần Spring**, dùng bean cấu hình ở mục 4. Phương thức `execute(...)` chỉ gửi `Runnable`, không trả `Future` để lấy giá trị hoặc lỗi. Đối với tác vụ có yêu cầu lưu lại trạng thái nghiệp vụ, cần thiết kế ghi nhận kết quả, retry và idempotency theo yêu cầu.

Nếu inject dưới kiểu `AsyncTaskExecutor` (mà `DefaultManagedTaskExecutor` triển khai), có thể gọi `submit(Callable<T>)` để nhận `Future<T>`. Tuy nhiên kết quả/ngoại lệ vẫn cần được quan sát. Với Spring Framework 7 và các phiên bản có API khác nhau, luôn tra cứu Javadoc cho đúng phiên bản thư viện đang triển khai; không sao chép nguyên các overload từ tài liệu Spring cũ nếu API đã thay đổi.

## 7. Sự khác nhau giữa Spring adapter và ManagedExecutorService thật

Có hai lớp trách nhiệm:

| Mặt | DefaultManagedTaskExecutor | ManagedExecutorService |
|---|---|---|
| Nằm ở đâu? | Trong thư viện Spring Framework | Trong Jakarta Concurrency API và bản triển khai của server |
| Ai tạo worker thread? | Không tạo pool; ủy quyền | Application server cung cấp worker do nó quản lý |
| Chức năng chính | Lookup JNDI, điều hợp `Executor` với `TaskExecutor` | Nhận tác vụ, thực thi có ngữ cảnh, áp dụng cấu hình tài nguyên server |
| Cấu hình pool size/queue | Không có các setter quản trị pool như `ThreadPoolTaskExecutor` | Do cấu hình/chính sách của server, tùy sản phẩm |
| Vòng đời executor | Spring quản lý vòng đời **adapter bean** | Server quản lý vòng đời tài nguyên/worker |
| Quyền gọi `shutdown()` | Không phải chỗ đóng managed pool | Ứng dụng không được tự đóng pool do server quản lý |
| Mục tiêu | Dễ tích hợp với `TaskExecutor`, `@Async` | Bảo đảm môi trường Jakarta EE đúng quy tắc |

Cần phân biệt thêm: vì `DefaultManagedTaskExecutor` có thể ủy quyền tới **bất kỳ `Executor` phù hợp được đăng ký trong JNDI**, việc dùng lớp Spring này **không tự chứng minh** delegate là `ManagedExecutorService`. Với JNDI mặc định của Jakarta EE server tương thích, đó là tài nguyên managed executor; nếu đổi `setJndiName` sang resource khác, phải xác minh loại và ngữ nghĩa thực tế.

## 8. Jakarta EE context: những gì được và không được truyền

### 8.1. Các ngữ cảnh được server quản lý

Khi một Jakarta EE component gửi tác vụ vào `ManagedExecutorService`, server thực hiện các quy tắc truyền ngữ cảnh của Jakarta Concurrency. Với default managed executor, các nhóm ngữ cảnh được đặc tả yêu cầu gồm **naming context**, **classloader context** và **security information**.

Ví dụ, tác vụ có thể cần classloader của ứng dụng để nạp lớp hoặc JNDI context để truy cập resource tương ứng. Chạy worker “ngoài tầm quản lý” của application server có thể khiến những giả định này sai.

Tuy nhiên, các chi tiết cụ thể về thông tin bảo mật nào được dùng và quyền nào tác vụ có được vẫn phụ thuộc mô hình bảo mật và chính sách của Jakarta EE runtime. Không suy ra mọi user identity hoặc mọi context ứng dụng tự động được sao chép.

### 8.2. Ngữ cảnh transaction không tự theo caller

Theo Jakarta Concurrency, tác vụ chạy mà **không tham gia sẵn vào transaction của thành phần đã gửi**. Việc caller đang trong `@Transactional` không có nghĩa managed task tự tiếp tục cùng giao dịch. Nếu công việc nền cần transaction, hãy tạo ranh giới transaction thích hợp **trong worker** bằng dịch vụ Spring được proxy quản lý hoặc cơ chế Jakarta transaction của ứng dụng.

Ví dụ về nguyên tắc:

```text
Request thread:
  @Transactional bắt đầu TX-A
  gửi @Async task
  tiếp tục xử lý và kết thúc TX-A

Managed worker thread:
  chạy sau hoặc đồng thời
  không tự kế thừa TX-A
  nếu cần: bắt đầu TX-B phù hợp trong worker
```

Cần cân nhắc cả tính nhất quán dữ liệu: tác vụ async có thể đọc dữ liệu trước khi transaction của caller commit. Muốn công việc chỉ bắt đầu sau commit thì thiết kế sự kiện sau commit, outbox hoặc một cơ chế có độ bền phù hợp thay vì chỉ tin vào thứ tự gửi `@Async`.

### 8.3. ThreadLocal, Spring Security và MDC

Không mặc định rằng `ThreadLocal` của request, `RequestContextHolder`, `SecurityContextHolder`, MDC logging hoặc trace context của thư viện khác được truyền đúng chỉ vì dùng `DefaultManagedTaskExecutor`. Mỗi loại context có quy tắc riêng; context Jakarta EE do runtime quản lý khác với biến cục bộ theo luồng do ứng dụng tạo.

Nếu tác vụ cần `correlationId`, `tenantId` hoặc principal ứng dụng, truyền dữ liệu bất biến rõ ràng trong tham số task hoặc dùng cơ chế truyền ngữ cảnh đã được kiểm chứng. Với dữ liệu nhạy cảm, không nhân bản bừa bãi cả request object hoặc tài nguyên có vòng đời ngắn sang worker.

## 9. Tác vụ mẫu và kết quả: Runnable, Callable, Future

`ManagedExecutorService` kế thừa `ExecutorService`, vì vậy hỗ trợ những phương thức như `execute(Runnable)` và `submit(Callable<T>)`; bản thân adapter Spring đưa ra các phương thức gửi việc tương ứng với `TaskExecutor`/`AsyncTaskExecutor`.

```text
Runnable
  └── công việc không trả giá trị trực tiếp

Callable<T>
  └── công việc trả T, có thể ném checked exception

AsyncTaskExecutor.submit(Callable<T>)
  └── Future<T>
       ├── get()           nhận giá trị / báo lỗi / có thể chặn
       ├── isDone()        có thể true cả khi lỗi/hủy
       └── cancel(true)    yêu cầu hủy/ngắt theo cơ chế hợp tác
```

Các nguồn lỗi cần tính tới:

- Lookup JNDI thất bại ở **khởi tạo bean**: lỗi cấu hình/tài nguyên, khác với lỗi của một task.
- Executor từ chối nhận việc mới: có thể phát sinh `TaskRejectedException` ở tầng Spring hoặc lỗi từ delegate theo hợp đồng; xử lý theo nơi gọi.
- Task chạy rồi ném ngoại lệ: khi gửi bằng `submit`, `Future.get()` báo lại qua `ExecutionException`; xem `getCause()` để biết lỗi gốc.
- Đợi quá lâu: `Future.get(timeout, unit)` ném `TimeoutException`; việc hết hạn không tự hủy task.
- Task bị hủy: `Future` có thể báo `CancellationException`; không nên hiểu việc hủy luôn dừng ngay thao tác I/O.

**Không được dùng `future.get()` vô thời hạn trong một worker mà task phụ thuộc cũng cần chính worker/tài nguyên đó để chạy.** Hệ thống có thể kẹt vì phụ thuộc vòng, giới hạn số worker hoặc khóa chung. Managed executor vẫn phải tuân theo giới hạn tài nguyên thực tế.

## 10. Vòng đời: đừng đóng pool của application server

Một điểm khác biệt cốt lõi giữa Jakarta EE và Java SE:

**Trong chương trình Java SE tự tạo `ExecutorService`**, code sở hữu pool phải đảm bảo đóng nó bằng `shutdown()`/`shutdownNow()` theo chính sách thích hợp.

**Trong Jakarta EE**, `ManagedExecutorService` được quản lý bởi application server. Ứng dụng **không được tự đóng** shared managed executor. Đặc tả quy định các thao tác lifecycle trên `ManagedExecutorService` như `shutdown()`, `shutdownNow()`, `awaitTermination()`, `isShutdown()` và `isTerminated()` bị từ chối bằng `IllegalStateException`.

Do đó:

- Khi dùng `DefaultManagedTaskExecutor`, hãy để Spring quản lý **adapter bean**, nhưng để application server quản lý **executor thật**.
- Đừng cố lấy delegate ra rồi gọi `shutdown()` như đang sở hữu pool Java SE.
- Không tạo pool “mỗi lần gọi một cái” chỉ để chạy công việc nền; trong Jakarta EE hãy dùng tài nguyên server cung cấp.
- Khi redeploy/undeploy, server có thể ngừng nhận việc, hủy việc đang chờ hoặc ngắt task đang chạy theo đặc tả/chính sách runtime.
- Managed executor thực thi tác vụ trong tiến trình, không phải hàng đợi bền vững. Nếu cần hoàn thành công việc bất chấp restart/crash, hãy dùng giải pháp xử lý bền vững thích hợp.

Ở phía ứng dụng, vẫn cần thiết kế timeout, khả năng hủy, lỗi từ task, giới hạn đầu vào và cách khôi phục công việc. “Managed” là trách nhiệm quản trị tài nguyên của server; nó không có nghĩa ứng dụng không phải xử lý thất bại.

## 11. So sánh với ThreadPoolTaskExecutor và ConcurrentTaskExecutor

| Tiêu chí | DefaultManagedTaskExecutor | ThreadPoolTaskExecutor | ConcurrentTaskExecutor |
|---|---|---|---|
| Nguồn executor | Lookup JNDI; mặc định managed executor của Jakarta EE | Spring tạo và cấu hình `ThreadPoolExecutor` | Nhận một `Executor` đã có |
| Runtime phù hợp | Jakarta EE application server có JNDI resource | Ứng dụng Spring tự quản lý tài nguyên, điển hình Spring Boot độc lập | Khi có `Executor` từ thư viện/nguồn khác cần chuyển thành Spring executor |
| Cấu hình `corePoolSize`/`maxPoolSize`/`queueCapacity` | Cấu hình tại application server thay vì trên adapter này | Có setter trực tiếp trên bean | Tùy delegate, không tự định nghĩa pool |
| Ai sở hữu worker? | Application server | Ứng dụng/Spring bean | Bên cung cấp delegate |
| Lookup JNDI mặc định | Có | Không | Không |
| Hợp với `@Async` | Có, khi bean được chọn và runtime sẵn sàng | Có | Có |

**Chọn DefaultManagedTaskExecutor khi:** ứng dụng Spring được đóng gói/deploy vào một Jakarta EE runtime hỗ trợ Jakarta Concurrency, muốn dùng executor do server quản lý và muốn Spring service chỉ phụ thuộc `TaskExecutor`.

**Chọn ThreadPoolTaskExecutor khi:** ứng dụng Spring chạy độc lập và chủ động quản lý pool, giới hạn queue, shutdown; không có tài nguyên Jakarta EE managed executor mà runtime cấp cho ứng dụng.

**Chọn ConcurrentTaskExecutor khi:** bạn đã có một đối tượng `Executor` phù hợp và chỉ cần đưa nó vào giao diện Spring, không cần thêm quy ước JNDI mặc định.

Một embedded servlet container không tự động tương đương Jakarta EE application server với đầy đủ Jakarta Concurrency. Hãy kiểm tra tính năng/tài nguyên JNDI của runtime cụ thể thay vì chọn theo tên “Jakarta” trong dependency.

## 12. Mẫu triển khai theo môi trường

### 12.1. Môi trường production Jakarta EE

Bản triển khai tương đối điển hình:

1. Administrator xác nhận server tương thích và cho phép ứng dụng dùng default managed executor hoặc một resource riêng.
2. Ứng dụng Spring cấu hình bean `DefaultManagedTaskExecutor` với đúng JNDI name.
3. Tại khởi động, Spring lookup; lỗi lookup phải làm rõ cấu hình, không im lặng đổi pool.
4. Service inject `TaskExecutor` hoặc chọn `@Async("managedTaskExecutor")`.
5. Quản trị số worker, giới hạn tài nguyên, chính sách từ chối và giám sát theo tính năng application server.
6. Kiểm thử chính trên môi trường triển khai thực tế: quyền, context, timeout, hủy, shutdown/redeploy.

### 12.2. Chạy local/test không có Jakarta EE server

Không thể giả định `new DefaultManagedTaskExecutor()` chạy trong một unit test Java SE thuần vì thiếu binding JNDI mặc định. Tùy cấu trúc dự án, có thể:

- Trong unit test, inject một `TaskExecutor` chạy trực tiếp `Runnable::run` hoặc một executor test có kiểm soát; kiểm tra logic nghiệp vụ không phụ thuộc thread cụ thể.
- Trong cấu hình local của ứng dụng, dùng `ThreadPoolTaskExecutor` với giới hạn worker/queue và shutdown rõ ràng.
- Trong integration test muốn chứng minh JNDI và managed contexts thực sự, chạy trên Jakarta EE runtime tương thích hoặc một thiết bị kiểm thử tương đương có resource được cấu hình.

Ví dụ **Java 17 độc lập** chứng minh việc code phụ thuộc vào `Executor` có thể chạy trên delegate khác nhau. **Đây chỉ là mô phỏng nguyên tắc ủy quyền**, không có JNDI, Spring hay managed executor Jakarta EE.

**Tệp `ExecutorDelegationDemo.java`**

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class ExecutorDelegationDemo {
    static void dispatch(Executor executor,
                         CountDownLatch done) {
        executor.execute(() -> {
            System.out.println(
                    "Luồng xử lý: "
                    + Thread.currentThread().getName());
            done.countDown();
        });
    }

    public static void main(String[] args)
            throws InterruptedException {

        ExecutorService owner = Executors.newSingleThreadExecutor(
                runnable -> new Thread(runnable, "demo-worker"));

        try {
            CountDownLatch done = new CountDownLatch(1);
            dispatch(owner, done);
            done.await();
            System.out.println("Caller nhận tín hiệu hoàn tất");
        } finally {
            owner.shutdown();
        }
    }
}
```

Lệnh biên dịch/chạy bằng Java 17+:

```bash
javac ExecutorDelegationDemo.java
java ExecutorDelegationDemo
```

Kết quả chính xác:

```text
Luồng xử lý: demo-worker
Caller nhận tín hiệu hoàn tất
```

Tại sao chương trình này minh họa đúng kiến trúc? Phương thức `dispatch` chỉ biết `Executor`, không tạo hay quản lý pool. `main` tạo nguồn executor cho demo và chịu trách nhiệm `shutdown` chính pool nó đã tạo. Còn trong Jakarta EE, Spring adapter nhận executor do server sở hữu qua JNDI, và **ứng dụng không được shutdown delegate managed executor**.

Tín hiệu `CountDownLatch` làm thứ tự hai dòng ra xác định; không cần dùng `Thread.sleep(...)` để “đợi cho may”. Trong ví dụ tối giản này, tác vụ luôn in trước khi gửi `countDown()`. Ứng dụng thật phải thêm xử lý exception để bảo đảm chốt chờ không bị treo nếu task có thể thất bại trước khi đếm chốt.

## 13. So sánh hai cách truy cập resource: JNDI trực tiếp và Spring adapter

Jakarta EE cho phép lookup/inject `ManagedExecutorService` trực tiếp. Nếu viết code phụ thuộc Jakarta API, về nguyên tắc có thể làm như sau:

**Đoạn Java minh họa đặt trong một Jakarta EE component (không phải chương trình độc lập):**

```java
import jakarta.enterprise.concurrent.ManagedExecutorService;
import javax.naming.InitialContext;
import javax.naming.NamingException;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Future;

public String runWithManagedExecutor()
        throws NamingException,
               InterruptedException,
               ExecutionException {

    ManagedExecutorService managed =
            (ManagedExecutorService) new InitialContext().lookup(
                    "java:comp/DefaultManagedExecutorService");

    Future<String> result = managed.submit(
            () -> "managed result");

    return result.get();
}
```

Để dùng snippet này, cần Jakarta Concurrency API thích hợp trong classpath (thường do server cung cấp) và một component đang chạy trong môi trường JNDI hợp lệ. `javax.naming.InitialContext` vẫn thuộc API JNDI của Java SE; không đổi tên thành `jakarta.naming.InitialContext`. `get()` có thể chặn, nên không dùng theo cách này trong code cần trả lời bất đồng bộ ngay.

Cách Spring:

```java
// Đặt trong một Spring-managed component đã được inject.
private final TaskExecutor executor;

public void submitJob() {
    executor.execute(() -> System.out.println("Managed job"));
}
```

Mảnh trên không phải class độc lập; cần inject bean `TaskExecutor` từ mục 4. Khi dùng Spring adapter, tầng nghiệp vụ không cần trực tiếp import `ManagedExecutorService` hay biết tên resource JNDI.

**Hai cách không mâu thuẫn:** chọn trực tiếp Jakarta API khi thật sự cần khả năng riêng của managed executor; chọn adapter Spring khi kiến trúc chủ yếu sử dụng abstraction của Spring.

## 14. Không nhầm ManagedTaskExecutor với scheduler

Jakarta Concurrency có `ManagedScheduledExecutorService` cho tác vụ theo lịch/độ trễ. Spring có lớp khác tên:

```java
org.springframework.scheduling.concurrent.DefaultManagedTaskScheduler
```

Lớp scheduler này dùng tên JNDI mặc định tương ứng:

```text
java:comp/DefaultManagedScheduledExecutorService
```

`DefaultManagedTaskExecutor` trong bài tập trung vào **thực thi tác vụ**, không tự biến mọi `Runnable` thành tác vụ theo lịch lặp. Việc một executor thuộc nhóm `SchedulingTaskExecutor` trong Spring không đồng nghĩa nó là `TaskScheduler` phục vụ lịch cron hoặc delay.

Nếu yêu cầu là chạy mỗi 5 phút hoặc theo biểu thức cron, hãy nghiên cứu `TaskScheduler`, `@Scheduled` và cấu hình scheduler riêng, không áp dụng `DefaultManagedTaskExecutor` như một lịch hẹn giờ tùy ý.

## 15. Quản trị tải, tính ổn định và observability

Vì resource do server sở hữu, khả năng chạy đồng thời và giới hạn queue thường được điều chỉnh qua **cấu hình application server**, không phải `setCorePoolSize(...)` trên `DefaultManagedTaskExecutor`. Cần xem tài liệu của server được triển khai cho tên property và khả năng hỗ trợ cụ thể.

Các chỉ số cần quan sát:

- Số tác vụ được gửi, đang chạy, hoàn thành, lỗi hoặc bị từ chối.
- Độ trễ từ khi gửi đến lúc bắt đầu chạy; độ sâu hàng chờ khi runtime cho phép.
- Thời gian thực thi p95/p99 và tỷ lệ quá hạn.
- Độ trễ của hệ thống ngoài mà task phụ thuộc.
- Dấu hiệu worker bị chặn ở I/O, mutex hoặc `Future.get()`.
- Hành vi khi application đang tắt, restart hoặc redeploy.

**Giới hạn đồng thời không thay thế giới hạn đầu vào.** Nếu request có thể ồ ạt tạo tác vụ dài hoặc nhiều tác vụ con, server có thể từ chối task. Ứng dụng cần quyết định trả lỗi, áp dụng backpressure, retry có giới hạn, hoặc đưa công việc vào hàng đợi bền vững.

Đừng coi “managed” là cách để tránh mọi race condition: nếu nhiều task cùng sửa trạng thái mutable của bean singleton, vẫn phải dùng chiến lược thread safety như immutable data, `AtomicLong`, concurrent collection hoặc `synchronized` với vùng khóa ngắn. Ngữ cảnh do server quản lý không tự bảo vệ dữ liệu Java.

## 16. Các lỗi triển khai thường gặp

| Sai lầm | Triệu chứng hoặc hệ quả | Cách xử lý |
|---|---|---|
| Deploy Spring Boot JAR thuần nhưng bật `DefaultManagedTaskExecutor` | Lookup `java:comp/DefaultManagedExecutorService` không tồn tại | Chọn pool Spring cho runtime standalone hoặc cung cấp Jakarta EE resource thật |
| Tưởng `new DefaultManagedTaskExecutor()` tạo pool riêng | Không thấy tùy chọn core/max pool và gặp lỗi JNDI | Hiểu đây là adapter; quản trị pool tại server |
| Cấu hình `setJndiName(...)` nhưng chưa map resource trên server | Bean không khởi tạo do không tìm thấy tên | Kiểm tra JNDI binding và kiểu đối tượng được tra cứu |
| Dùng nhầm `java:comp/env/` trước tên mặc định | Lookup sai tên | Dùng tên chuẩn; chỉ dùng tên tương đối khi cấu hình đúng `resourceRef` |
| Gọi `@Async` mà chưa bật cơ chế async | Method chạy đồng bộ | Cấu hình `@EnableAsync` hoặc cơ chế tương đương |
| Gọi `this.asyncMethod()` trong cùng bean | Bỏ qua Spring proxy ở chế độ mặc định | Tách thành phần gọi qua bean được Spring quản lý |
| Có nhiều executor nhưng không chỉ rõ executor dùng cho task | Chạy trên pool ngoài mong đợi | Dùng `@Async("managedTaskExecutor")` hoặc `@Qualifier` |
| Nghĩ các `ThreadLocal`/request context đều tự theo task | Thiếu hoặc sai context | Truyền dữ liệu cần thiết, kiểm chứng công cụ context propagation |
| Nghĩ task async kế thừa transaction của caller | Dữ liệu chưa commit hoặc không cùng transaction | Tạo transaction mới thích hợp trong task hoặc thiết kế after-commit |
| Gọi `shutdown()` trên raw managed executor | Vi phạm lifecycle Jakarta EE; có thể ném `IllegalStateException` | Để application server quản lý |
| Bỏ qua `Future`/`CompletableFuture` hoặc không có error handler | Lỗi công việc không được ghi nhận đầy đủ | Quan sát hoàn tất/lỗi; xử lý retry có giới hạn |
| Dùng `CompletableFuture.supplyAsync(...)` không truyền executor | Có thể chạy trên common pool, ngoài kỳ vọng managed | Truyền executor hoặc dùng API Jakarta managed stage thích hợp |
| Cho rằng task tồn tại qua redeploy/crash | Mất công việc chưa hoàn tất | Chọn hàng đợi bền vững nếu nghiệp vụ yêu cầu |

## 17. Checklist kiểm chứng một triển khai thật

Khi nhận một ứng dụng Spring được giao triển khai lên Jakarta EE server, hãy lần lượt xác minh:

1. **Runtime:** Server thực sự hỗ trợ Jakarta Concurrency và cung cấp `java:comp/DefaultManagedExecutorService` hoặc tài nguyên riêng được cấu hình.
2. **Tương thích thư viện:** Phiên bản Spring Framework và Jakarta EE API phù hợp với classloader của runtime; tránh trộn package `javax.enterprise.concurrent` cũ và `jakarta.enterprise.concurrent` mới.
3. **Bean:** `DefaultManagedTaskExecutor` được Spring tạo và khởi tạo thành công; nếu lookup lỗi, kiểm tra JNDI name/mapping, không vá tạm bằng pool không kiểm soát.
4. **Định tuyến:** `@Async` chỉ rõ bean hoặc inject `TaskExecutor` với `@Qualifier`, và lời gọi đi qua proxy nếu dùng `@Async`.
5. **Ngữ cảnh:** Kiểm chứng naming, classloader, security; không dựa vào request `ThreadLocal` hay caller transaction tự lan truyền.
6. **Kết quả:** Caller có con đường quan sát thành công, lỗi, timeout, hủy; task không nuốt ngoại lệ hoặc ngắt.
7. **Tải:** Server có giới hạn số task/worker rõ ràng; thử tải và kiểm tra chính sách từ chối.
8. **Vòng đời:** Ứng dụng không tự `shutdown` raw managed executor; biết rõ điều gì xảy ra khi redeploy.
9. **Độ bền:** Nếu cần bảo đảm không mất việc sau crash, có hệ thống lưu công việc bền vững thay vì chỉ gửi in-memory task.

Trong kiểm thử tích hợp, có thể ghi nhận thời điểm gửi và bắt đầu thực thi, logging correlation ID rõ ràng, lỗi lookup và lỗi từ chối; tuyệt đối không lấy một tên thread cụ thể làm bằng chứng duy nhất rằng task đang chạy trên managed executor. Bằng chứng tốt hơn gồm JNDI binding đúng kiểu, cấu hình server và telemetry của runtime.

## 18. Bài tập tự kiểm tra

**Bài 1 — Chọn runtime phù hợp.** Một ứng dụng Spring Boot chạy bằng `java -jar` không có binding JNDI. Nếu thêm bean `DefaultManagedTaskExecutor`, chuyện gì có khả năng xảy ra khi khởi tạo context? Nêu hai phương án đúng để phát triển local và triển khai lên Jakarta EE server.

**Định hướng:** Lookup mặc định không tìm thấy resource; cấu hình executor khác cho local, giữ managed executor cho môi trường Jakarta EE có resource thật.

**Bài 2 — Chỉ ra ai sở hữu pool.** Ứng dụng gọi `managedExecutor.shutdown()` trong phương thức `@PreDestroy` vì cho rằng phải dọn dẹp mọi tài nguyên. Sai ở đâu?

**Định hướng:** Lifecycle của managed executor thuộc server; các method lifecycle của `ManagedExecutorService` bị cấm cho code ứng dụng. Đóng adapter bean không có nghĩa đóng pool server.

**Bài 3 — Chọn executor với @Async.** Trong ApplicationContext có hai bean `ThreadPoolTaskExecutor` và `DefaultManagedTaskExecutor`. Làm sao bảo đảm phương thức quan trọng được gửi đến managed executor?

**Định hướng:** Đặt tên bean ổn định và dùng `@Async("managedTaskExecutor")`; caller phải đi qua proxy Spring.

**Bài 4 — Phân tích transaction.** Request đang trong `@Transactional` tạo task bằng `@Async`, task đọc một bản ghi vừa được sửa nhưng chưa commit. Có bảo đảm task thấy bản mới và cùng transaction không?

**Định hướng:** Không. Task không tự tham gia transaction của caller. Cần thiết kế transaction trong task và điều phối sau commit nếu phù hợp.

**Bài 5 — Kiểm tra context.** Một task cần `tenantId` lưu trong `ThreadLocal` của request. Vì sao dùng managed executor chưa đủ để cam kết có `tenantId`? Đề xuất cách truyền dữ liệu.

**Định hướng:** Context Jakarta EE được đặc tả quản lý khác với `ThreadLocal` tự tạo; truyền tenant ID bất biến qua argument, kiểm tra quyền ở worker và không giữ đối tượng request lâu hơn vòng đời của nó.

**Bài 6 — Thực hành Java 17.** Chạy `ExecutorDelegationDemo`, thay `ExecutorService` bằng executor inline `Runnable::run` rồi giải thích vì sao đầu ra chuyển sang thread `main` dù code `dispatch` không đổi.

**Định hướng:** `Executor` chỉ cam kết thực thi `Runnable`, không cam kết tạo thread mới. Trường hợp inline chỉ chạy ngay trên luồng gọi; adapter Spring dùng delegate theo runtime nên hành vi cần dựa vào executor thật.

## 19. Tóm tắt nguyên tắc

- **`DefaultManagedTaskExecutor` là cầu nối của Spring** tới một `Executor` qua JNDI; mặc định tra cứu `java:comp/DefaultManagedExecutorService`.
- **ManagedExecutorService thuộc Jakarta Concurrency** và do application server tạo, cấu hình, cấp phát worker, áp dụng các ngữ cảnh tương ứng và quản lý vòng đời.
- **Không có fallback pool tự động** nếu không tìm thấy JNDI resource. Chọn đúng executor cho đúng môi trường.
- **Dùng Spring TaskExecutor hoặc @Async có tên rõ ràng** để tầng nghiệp vụ không phụ thuộc trực tiếp vào cấu hình JNDI.
- **Managed context không có nghĩa mang theo mọi ThreadLocal hoặc transaction**; phải thiết kế truyền thông tin và transaction cụ thể.
- **Không shutdown tài nguyên managed executor** từ ứng dụng; đồng thời vẫn phải xử lý lỗi, giới hạn tài nguyên, timeouts, hủy, và tính bền vững của công việc.

### Tài liệu gốc để đối chiếu

- [Spring Framework API — DefaultManagedTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/DefaultManagedTaskExecutor.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Jakarta EE Platform API — ManagedExecutorService](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/enterprise/concurrent/managedexecutorservice)
- [Jakarta Concurrency Specification](https://jakarta.ee/specifications/concurrency/3.0/jakarta-concurrency-spec-3.0)
