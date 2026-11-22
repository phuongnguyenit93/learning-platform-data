# Hợp đồng Lifecycle: `start()`, `stop()` và `isRunning()` trong Spring Boot 3.3

## 1. Mục tiêu

Một Spring bean có thể được **tạo thành công** nhưng một tác vụ gắn với bean ấy vẫn **chưa khởi chạy**. Ví dụ: consumer chưa subscribe vào broker, một nguồn thu thập dữ liệu chưa polling, hoặc một service nền đã được inject nhưng chưa mở kết nối. Đây là lý do Spring Framework cung cấp hợp đồng **`org.springframework.context.Lifecycle`**:

- `start()`: bắt đầu hoặc tiếp tục hoạt động của thành phần.
- `stop()`: yêu cầu thành phần dừng hoạt động.
- `isRunning()`: cho biết thành phần hiện được xem là đang chạy hay không.

Spring Framework còn cung cấp **`SmartLifecycle`**, mở rộng `Lifecycle` để tự động khởi động khi `ApplicationContext.refresh()`, cho phép sắp xếp start/stop theo **phase**, và hỗ trợ callback `stop(Runnable)` để điều phối shutdown bất đồng bộ.

Bài tập trung vào **hợp đồng Lifecycle và cách container gọi nó trong Spring Boot 3.3**. Sau khi học, bạn có thể:

1. Phân biệt bean **đã tạo**, **đã initialized**, **đang running**, **đã stopped** và **đã destroyed**.
2. Viết class triển khai `Lifecycle` chính xác, idempotent, trả `isRunning()` trung thực.
3. Giải thích vì sao `Lifecycle` thông thường không tự start chỉ vì context refresh, trong khi `SmartLifecycle` có thể.
4. Dùng `ConfigurableApplicationContext.start()`, `.stop()`, `.close()` đúng mục đích.
5. Hiểu `isAutoStartup()`, `getPhase()` và `SmartLifecycle.stop(Runnable)`.
6. Xây dựng demo Java 21 / Spring Boot 3.3.13 chạy được với log có thứ tự xác định.
7. Tránh những lỗi khi async startup/shutdown, cancellation, retry và graceful shutdown.

**Thông điệp chính:** `Lifecycle` quản lý **trạng thái hoạt động của component**, không phải chỉ việc Spring tạo/hủy đối tượng Java. `start()` và `stop()` cần là những thao tác có ý nghĩa đối với tài nguyên hoặc công việc thật; `isRunning()` phải phản ánh thực trạng đó.

## 2. Phân biệt vòng đời bean với hợp đồng Lifecycle

Spring quản lý nhiều mốc khác nhau:

```text
Đăng ký BeanDefinition
      |
      +-- Tạo instance (constructor hoặc factory method)
      +-- Inject dependencies
      +-- BeanPostProcessor và init callbacks
      |     +-- @PostConstruct
      |     +-- InitializingBean.afterPropertiesSet()
      |
      +-- Bean đã initialized
      |     |
      |     +-- Lifecycle.start() (khi được yêu cầu)
      |     +-- Thành phần đang running
      |     +-- Lifecycle.stop() (khi được yêu cầu)
      |
      +-- Đóng ApplicationContext
            +-- Stop các lifecycle beans còn chạy
            +-- Destroy các singleton
                  +-- @PreDestroy / DisposableBean / destroy method
```

Sơ đồ mang tính khái niệm; một bean có thể không triển khai `Lifecycle`, có thể lazy, prototype hoặc có cơ chế đặc thù.

| Khái niệm | Mục đích | Có đồng nghĩa với running không? |
| --- | --- | --- |
| Constructor | Tạo đối tượng Java và nhận dependencies | Không |
| `@PostConstruct` | Khởi tạo bean sau khi dependency injection | Không mặc nhiên |
| `Lifecycle.start()` | Bật hoạt động hoặc tài nguyên của bean | Có, nếu start thật sự thành công |
| `Lifecycle.isRunning()` | Quan sát trạng thái hoạt động hiện thời | Phải do implementation phản ánh |
| `Lifecycle.stop()` | Dừng hoạt động của bean | Sau khi dừng, nên báo false |
| `@PreDestroy` | Cleanup khi bean bị hủy | Khác với tạm stop và có thể restart |
| `ApplicationContext.close()` | Đóng toàn bộ context | Sau khi đóng không thể start lại context ấy |

Ví dụ: một `MessageConsumer` có thể đã constructor-inject `MessageClient` và qua `@PostConstruct`, nhưng vẫn chưa đăng ký consumer với broker. Khi `start()` được gọi, component mới bắt đầu nhận message; `stop()` dừng nhận message. Trong khi đó, `@PreDestroy` còn có thể giải phóng connection pool hoặc các tài nguyên cuối cùng.

**Tránh nhầm:** không phải mọi bean đều thực hiện `start()`. Chỉ các object triển khai `Lifecycle` (hoặc extension tương ứng) mới được `LifecycleProcessor` quản lý theo hợp đồng này.

## 3. Lifecycle interface: hợp đồng ba phương thức

Các phương thức chính của `org.springframework.context.Lifecycle`:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Đây là **hợp đồng API được trích minh họa**, không phải file tự tạo trong ứng dụng; ứng dụng dùng interface từ Spring Framework.

### 3.1. `start()`

Ý nghĩa: đánh dấu điểm bắt đầu hoạt động của component. Một implementation nên:

- Có thể được gọi nhiều lần mà không tạo consumer/thread/connection trùng lặp.
- Chỉ đặt running thành `true` sau khi phần **bắt đầu thực sự cần thiết** đã thành công.
- Nếu khởi động lỗi, để trạng thái phản ánh chính xác và báo exception phù hợp.
- Không bỏ tài nguyên dở dang khi start thất bại một phần; cần rollback/cleanup.
- Xác định rõ `start()` có phải đợi đến lúc component thật sự hoạt động hay chỉ submit một tác vụ nền.

Ví dụ logic:

```java
@Override
public synchronized void start() {
    if (running) {
        return;
    }

    // Bật một resource thực tế trước khi báo running.
    openConsumer();

    running = true;
}
```

Đây là **đoạn minh họa**, cần field `running` và phương thức `openConsumer()` do ứng dụng định nghĩa. Khi `openConsumer()` ném exception, flag vẫn false. Với khởi động async, phải định nghĩa riêng khi nào được coi là running, và tránh báo true trước khi thực sự sẵn sàng nếu consumer còn chưa kết nối.

### 3.2. `stop()`

Ý nghĩa: yêu cầu component ngừng hoạt động. Implementation nên:

- Idempotent: stop khi đã stopped không gây lỗi hoặc dừng tài nguyên lần thứ hai.
- Không nhận thêm việc khi chuyển sang stopping.
- Quyết định rõ có chờ các tác vụ đang xử lý hoàn thành không, thời gian chờ tối đa là bao nhiêu.
- Đóng/cancel resource theo thứ tự an toàn.
- Cập nhật `running=false` đúng lúc đã dừng, không chỉ vì một yêu cầu stop vừa được gửi.

Ví dụ:

```java
@Override
public synchronized void stop() {
    if (!running) {
        return;
    }

    // Dừng resource, hủy đăng ký và thu hồi tài nguyên.
    closeConsumer();

    running = false;
}
```

Đây là **mẫu minh họa**, không phải chương trình độc lập; `closeConsumer()` cần được triển khai. Cần một failure policy rõ ràng: nếu close thất bại, tiếp tục cleanup phần nào có thể, log nguyên nhân và cân nhắc trạng thái phản ánh mức độ thực tế.

### 3.3. `isRunning()`

Ý nghĩa: phản ánh trạng thái hoạt động hiện tại; không phải một lệnh để Spring “bật” component.

```java
@Override
public boolean isRunning() {
    return running;
}
```

Nếu start/stop có thể được gọi từ nhiều threads, dùng state đồng bộ hóa phù hợp (`volatile`, lock hoặc atomic state) để bảo đảm visibility. Trong ví dụ chạy được ở mục 7, state được giữ bằng `volatile boolean` và việc chuyển trạng thái trong `synchronized` methods.

**Không viết `isRunning() { return true; }` chỉ để tránh bị container start lại.** `LifecycleProcessor` dựa trên `isRunning()` để biết khi nào cần gọi start/stop. Báo sai có thể khiến bean không start khi cần, hoặc shutdown bỏ sót tài nguyên.

### 3.4. Hợp đồng trạng thái tối thiểu

```text
STOPPED
   | start() thành công
   v
RUNNING
   | stop() hoàn tất
   v
STOPPED
```

Vòng chuyển trạng thái đơn giản:

| Trạng thái ban đầu | Hành động | Kết quả mong đợi |
| --- | --- | --- |
| STOPPED | `start()` | RUNNING |
| RUNNING | `start()` lần nữa | Vẫn RUNNING, không tạo tài nguyên trùng |
| RUNNING | `stop()` | STOPPED |
| STOPPED | `stop()` lần nữa | Vẫn STOPPED, không lỗi |
| STARTING | `stop()` đồng thời | Phải có chính sách phối hợp, tránh race |
| STOPPING | `start()` đồng thời | Phải có chính sách restart hoặc từ chối rõ ràng |

Hai dòng cuối thuộc hệ thống thực tế có concurrency. `boolean` đơn giản chỉ phù hợp với ví dụ đơn luồng/đồng bộ ngắn; ứng dụng production có thể cần state machine `NEW → STARTING → RUNNING → STOPPING → STOPPED → FAILED`, cùng timeout và khóa đồng bộ.

## 4. Lifecycle được container gọi khi nào?

### 4.1. Plain `Lifecycle` không tự start vì refresh

Chỉ triển khai `Lifecycle` **không** đồng nghĩa Spring sẽ gọi `start()` tự động ở `ApplicationContext.refresh()`.

`LifecycleProcessor` mặc định của Spring nhận lệnh trong các trường hợp:

- Context được yêu cầu **`start()`**: container gọi `start()` trên các Lifecycle beans cần start, theo phase/dependency.
- Context được yêu cầu **`stop()`**: container gọi `stop()` trên các Lifecycle beans đang running, theo thứ tự stop.
- Context **`close()`**: quá trình đóng context quản lý việc stop lifecycle components còn running rồi destroy beans.
- Context **`refresh()`**: processor xử lý **auto-startup** của các `SmartLifecycle` tương ứng; plain Lifecycle thường chưa start.

Vì vậy đoạn sau **không đủ** để kết luận plain Lifecycle đã chạy:

```java
@Component
class DataCollector implements Lifecycle {
    // Có các method start, stop, isRunning...
}
```

Đây là **mẫu minh họa**, không phải class Java đầy đủ. Object được tạo/initialize không tự bảo đảm `start()` của nó được gọi tại refresh.

### 4.2. ConfigurableApplicationContext có thể điều khiển lifecycle

Trong một application context hỗ trợ điều khiển:

```java
ConfigurableApplicationContext context = ...;

context.start();  // Start Lifecycle components.
context.stop();   // Stop Lifecycle components.
context.close();  // Stop nếu cần, destroy bean và đóng context.
```

Đây là đoạn minh họa, cần biến `context` từ Spring Boot hoặc Spring Framework. Hai phương thức `start()` và `stop()` của **context** điều phối lifecycle components; chúng không phải lệnh refresh lại bean definitions hoặc tạo lại một `ApplicationContext`.

Phân biệt:

- `context.stop()` không destroy các singleton; có thể gọi `context.start()` lại nếu các components hỗ trợ restart.
- `context.close()` đóng context, destroy singleton; không thể “mở lại” context đã đóng bằng `start()`.
- Gọi `aLifecycleBean.start()` trực tiếp chỉ can thiệp **bean đó** và có thể bỏ qua ordering/coordination của toàn context; muốn điều phối hệ thống, dùng context lifecycle processor hoặc một service điều phối phù hợp.

### 4.3. Vòng đời Spring Boot

Trong một lần Boot khởi động thông thường:

```text
SpringApplication.run(args)
  |
  +-- refresh ApplicationContext
  |     +-- init bean
  |     +-- LifecycleProcessor.onRefresh()
  |           +-- Auto-start các SmartLifecycle cần start
  |
  +-- ContextRefreshedEvent
  +-- ApplicationStartedEvent
  +-- ApplicationRunner / CommandLineRunner
  +-- ApplicationReadyEvent
  |
  +-- SpringApplication.run(...) trả về
```

Vì vậy một `SmartLifecycle` auto-starting có thể bắt đầu **trước** khi `ApplicationRunner` được gọi. Muốn xử lý dữ liệu sau khi các runners hoàn tất, không được coi `SmartLifecycle.start()` là callback “sau ready”.

## 5. SmartLifecycle bổ sung những gì?

`org.springframework.context.SmartLifecycle` kế thừa `Lifecycle` và `Phased`. Trong Spring Framework 6.1, nó cung cấp các method mặc định và callback:

```java
public interface SmartLifecycle extends Lifecycle, Phased {
    default boolean isAutoStartup() { return true; }
    default int getPhase() { return Integer.MAX_VALUE; }
    default void stop(Runnable callback) {
        stop();
        callback.run();
    }
}
```

Đây là **mô hình minh họa hợp đồng mặc định**, không phải source chính xác toàn bộ interface thư viện. Không sao chép thành file thay thế `org.springframework.context.SmartLifecycle`. Các override thật phải tuân theo `SmartLifecycle` của Spring.

Bảng so sánh:

| Khía cạnh | `Lifecycle` | `SmartLifecycle` |
| --- | --- | --- |
| `start()` | Bắt buộc triển khai | Kế thừa, vẫn cần triển khai |
| `stop()` | Bắt buộc triển khai | Kế thừa, vẫn cần triển khai |
| `isRunning()` | Bắt buộc triển khai | Kế thừa, vẫn cần triển khai |
| `isAutoStartup()` | Không có | Mặc định `true` |
| `getPhase()` | Không có (phase hiệu dụng mặc định 0) | Mặc định `Integer.MAX_VALUE` |
| `stop(Runnable callback)` | Không có | Có default; có thể override để shutdown async |
| Tự start khi refresh | Không mặc định | Có nếu `isAutoStartup()==true` |
| Start/stop theo phase | Tham gia ở phase 0 khi không khai báo `Phased` | Tham gia theo `getPhase()` |

### 5.1. `isAutoStartup()`

Mặc định `SmartLifecycle.isAutoStartup()` trả `true`. Khi context refresh, `DefaultLifecycleProcessor` sẽ gọi `start()` cho các SmartLifecycle được coi là cần tự start.

Nếu override trả `false`:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

Component **không được auto-start từ refresh**. Nhưng khi gọi **`context.start()`** tường minh, nó vẫn có thể được start như Lifecycle bean khác. Không hiểu `false` là “Spring sẽ không bao giờ gọi start”.

**Cảnh báo về lazy:** `SmartLifecycle` có thể cần được bean factory tạo sớm để kiểm tra `isAutoStartup` và quản lý start/stop, nên `@Lazy` trên một SmartLifecycle bean không phải cách đáng tin để hoãn mọi lần khởi tạo của nó. Nếu muốn kiểm soát lúc thực sự bật resource, dùng `isAutoStartup()` và `start()` thay vì đặt niềm tin hoàn toàn vào lazy flag.

### 5.2. `getPhase()` và thứ tự start/stop

Khi Spring điều phối các lifecycle components:

- **Start theo phase tăng dần**: phase nhỏ hơn trước; phase lớn hơn sau.
- **Stop theo phase giảm dần**: phase lớn hơn trước; phase nhỏ hơn sau.
- `Lifecycle` thông thường, nếu không có phase metadata riêng, có phase hiệu dụng **0**.
- `SmartLifecycle` mặc định dùng `Integer.MAX_VALUE`: vì vậy một SmartLifecycle không override phase thường start muộn và stop sớm hơn Lifecycle ở phase 0.
- Có thể override `getPhase()` để đưa component vào phase phù hợp với hạ tầng của app.

Ví dụ:

```java
@Override
public int getPhase() {
    return 100;
}
```

Nếu consumer phase 100 phụ thuộc một resource phase 0, startup theo phase cho phép resource start trước consumer; shutdown ngược lại.

**Giới hạn:** quan hệ bean dependency (`depends-on`, DI và dependencies mà Spring biết) có thể **được ưu tiên hơn thứ tự phase** khi framework điều phối. Không tạo phase graph trái với dependency graph rồi dựa vào kết quả ngẫu nhiên. Các beans **cùng phase** không có một thứ tự theo tên class được bảo đảm, nên dùng dependency thật khi có ràng buộc bắt buộc.

### 5.3. `stop(Runnable callback)` và shutdown bất đồng bộ

Đây là điểm khác biệt rất quan trọng:

```java
@Override
public void stop(Runnable callback) {
    stop();
    callback.run();
}
```

Với Spring Framework 6.1, `SmartLifecycle` có default implementation dạng tương tự. `DefaultLifecycleProcessor` sẽ gọi **`stop(Runnable)`** khi dừng SmartLifecycle; nó không bắt buộc gọi trực tiếp `stop()` no-arg trừ khi code `stop(Runnable)` delegate.

Callback không phải “thông báo đã yêu cầu dừng”; nó phải được gọi **khi công việc dừng đã hoàn tất** để processor có thể tiếp tục các phase và tránh chờ đến timeout. Nếu stop bất đồng bộ, callback phải chạy **sau khi đóng consumer, drain công việc và giải phóng resource** theo hợp đồng cần thiết.

Ví dụ pseudo-code cho stop async:

```java
@Override
public void stop(Runnable callback) {
    shutdownExecutor.execute(() -> {
        try {
            drainAndClose(); // Chỉ trả về khi đã dừng xong.
            running = false;
        }
        finally {
            callback.run();
        }
    });
}
```

Đây là **mã minh họa, không độc lập**: cần `shutdownExecutor`, `drainAndClose()`, state synchronization và xử lý khi executor từ chối task. Trong production, nếu `execute(...)` thất bại trước khi scheduling, bạn vẫn phải xử lý fallback/callback đúng cách, nếu không shutdown có thể treo tới timeout.

Nếu stop được xử lý hoàn toàn đồng bộ, override `stop(Runnable)` để gọi no-arg `stop()` rồi callback là đủ. Không nên tạo thread chỉ để giả lập async shutdown.

### 5.4. Default `stop(Runnable)` không thay thế stop no-arg

Một implementation SmartLifecycle cần hiểu hai đường gọi:

- `myComponent.stop()` được code ứng dụng gọi trực tiếp.
- `LifecycleProcessor` gọi `myComponent.stop(callback)` để phối hợp shutdown.

Nếu override `stop(Runnable)` nhưng **quên thực hiện dừng thực tế** hoặc quên gọi callback, lifecycle processor có thể chờ cho đến timeout và tài nguyên còn chạy.

### 5.5. Timeout per shutdown phase

Spring Boot 3.3 có thuộc tính:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Ví dụ trên đặt thời gian chờ cho mỗi shutdown phase. Timeout không phải bảo đảm mọi thread đã dừng nếu implementation sai hoặc resource treo. Khi cấu hình graceful shutdown cho web application trong Boot 3.3, có thể đặt:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Cấu hình này thuộc **một dự án web phù hợp**, không biến chương trình non-web ở mục 7 thành HTTP service. Cần đủ thời gian shutdown cho nghiệp vụ thật, đồng thời thiết kế các tác vụ idempotent/khả năng phục hồi sau khi hết thời gian.

## 6. Thứ tự Lifecycle, Context và ứng dụng

### 6.1. Context refresh không tự động gọi start của mọi bean

`SpringApplication.run(...)` dẫn đến `refresh()` của context. Lifecycle processor tự khởi động các SmartLifecycle cho phép auto-start, nhưng **plain Lifecycle không tự động chạy** chỉ vì context refresh.

Điều này không có nghĩa plain Lifecycle không hữu dụng. Có hệ thống muốn tạo bean tại startup nhưng chỉ bắt đầu nhận message khi operator gọi `context.start()`, khi một cấu hình được kích hoạt hoặc khi một coordinator ra lệnh.

### 6.2. Lifecycle stop khác bean destroy

Khi `context.stop()`:

- Spring gọi stop cho các lifecycle components đang chạy.
- Bean vẫn ở trong container; một context còn active có thể `start()` lại.
- `@PreDestroy` không phải phần mặc định của `stop()`.

Khi `context.close()`:

- Spring dừng lifecycle components đang chạy.
- Context đi vào quá trình hủy singleton và cleanup.
- `@PreDestroy`/destroy methods có thể được gọi cho những bean tương ứng.
- Context đã đóng không thể restart bằng `context.start()`.

**Điểm tránh nhầm:** `isRunning()==false` không có nghĩa bean đã destroyed. Nó chỉ là tín hiệu về **trạng thái hoạt động** do `Lifecycle` định nghĩa.

### 6.3. Lifecycle start không tương đương availability READY

Spring Boot còn có `ApplicationAvailability` và `ReadinessState`. Một `SmartLifecycle` báo `isRunning()==true` cho **một component** không chứng minh toàn bộ ứng dụng đã hoàn tất runners, healthy, hoặc sẵn sàng nhận traffic. Cần nối yêu cầu nghiệp vụ với readiness probes/health checks đúng chỗ.

Trình tự thông thường:

```text
refresh context
  -> start SmartLifecycle auto components
  -> ApplicationStartedEvent
  -> ApplicationRunner và CommandLineRunner
  -> ApplicationReadyEvent
  -> ReadinessState.ACCEPTING_TRAFFIC
```

Nếu component khởi động một tác vụ async rồi trả về ngay và `isRunning()` báo true quá sớm, Spring Boot vẫn có thể đạt mốc ready khi subsystem chưa sẵn sàng. Phải định nghĩa startup completion và readiness rõ ràng.

## 7. Ví dụ hoàn chỉnh: plain Lifecycle so với SmartLifecycle

Mục tiêu demo:

- `ManualPollingWorker` triển khai **`Lifecycle`**. Sau `SpringApplication.run(...)`, bean đã được tạo nhưng chưa chạy. Nó chỉ start khi **`context.start()`** được gọi tường minh.
- `AutoPollingWorker` triển khai **`SmartLifecycle`**, `isAutoStartup()` true, `getPhase()==100`. Nó tự start trong context refresh.
- `context.stop()` dừng AutoPollingWorker ở phase 100 **trước** ManualPollingWorker ở phase 0.
- `isRunning()` xác nhận state trước và sau từng thao tác.
- Sau `context.stop()`, `try-with-resources` đóng context để giải phóng resources mà không gọi stop thêm cho bean đã dừng.

### 7.1. Cấu trúc dự án

```text
lifecycle-contract-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/lifecycle/
    │       ├── LifecycleContractApplication.java
    │       ├── ManualPollingWorker.java
    │       └── AutoPollingWorker.java
    └── test/
        └── java/com/example/lifecycle/
            └── LifecycleContractTest.java
```

### 7.2. Maven

Tệp `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-contract-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
```

`spring-boot-starter` đủ để tạo ứng dụng non-web có `ApplicationContext`. `spring-boot-starter-test` cung cấp JUnit Jupiter và công cụ kiểm thử Spring context.

### 7.3. Bean Lifecycle thông thường

Tệp `src/main/java/com/example/lifecycle/ManualPollingWorker.java`:

```java
package com.example.lifecycle;

import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class ManualPollingWorker implements Lifecycle {

    private volatile boolean running;

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        // Demo không tạo thread thực: mô phỏng bật polling.
        running = true;
        System.out.println("MANUAL start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        // Demo không tạo thread thực: mô phỏng tắt polling.
        running = false;
        System.out.println("MANUAL stop");
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

Không có `@PostConstruct` khởi chạy polling; constructor/bean creation không đồng nghĩa start. Chỉ khi `context.start()` hoặc lời gọi `start()` phù hợp xảy ra, `running` mới true.

`synchronized` làm các phép chuyển flag tuần tự trong demo; `volatile` giúp các thread khác nhìn thấy cập nhật. Trong production, nếu start/stop tốn thời gian, đừng giữ lock vô thời hạn; thêm timeout và state machine để điều phối race.

### 7.4. Bean SmartLifecycle tự khởi động

Tệp `src/main/java/com/example/lifecycle/AutoPollingWorker.java`:

```java
package com.example.lifecycle;

import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class AutoPollingWorker implements SmartLifecycle {

    private volatile boolean running;

    @Override
    public synchronized void start() {
        if (running) {
            return;
        }
        // Demo không tạo thread thực: mô phỏng bật nguồn nhận việc.
        running = true;
        System.out.println("AUTO start");
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        running = false;
        System.out.println("AUTO stop");
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        }
        finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @Override
    public int getPhase() {
        return 100;
    }
}
```

Phần `stop(Runnable)` gọi stop đồng bộ rồi báo hoàn tất cho lifecycle processor. `finally` bảo đảm callback được gọi dù một bước cleanup ném exception; trong production, phải log lỗi, xác định trạng thái tài nguyên và có policy phù hợp thay vì mặc định “callback đã chạy” tương đương “resource dừng thành công”.

`isAutoStartup()==true` đã là default của Spring Framework 6.1; ở đây override để người học thấy rõ hợp đồng. `getPhase()==100` giúp so sánh với plain Lifecycle ở phase hiệu dụng 0.

### 7.5. Lớp main

Tệp `src/main/java/com/example/lifecycle/LifecycleContractApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class LifecycleContractApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(LifecycleContractApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            AutoPollingWorker auto = context.getBean(AutoPollingWorker.class);
            ManualPollingWorker manual =
                    context.getBean(ManualPollingWorker.class);

            System.out.println("MAIN initial auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());

            context.start();
            System.out.println("MAIN after-start auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());

            context.stop();
            System.out.println("MAIN after-stop auto=" + auto.isRunning()
                    + ", manual=" + manual.isRunning());
        }
    }
}
```

Mốc `app.run(args)` đã bao gồm refresh, `ApplicationStartedEvent`, runners (nếu có) và `ApplicationReadyEvent`; khi method trả về, SmartLifecycle auto-start đã hoạt động. `context.start()` gọi lifecycle processor và bắt đầu plain Lifecycle chưa chạy. `context.stop()` dừng cả hai theo phase; context vẫn có thể `start()` lại nếu muốn. Demo đóng context sau khi in xong trạng thái.

### 7.6. Chạy chương trình

Cần JDK 21, Maven và quyền tải dependencies phù hợp. Trong thư mục `lifecycle-contract-demo`:

```bash
java -version
mvn -version
mvn test
mvn package
java -jar target/lifecycle-contract-demo-0.0.1-SNAPSHOT.jar
```

Những dòng **do code demo chủ động in**, sau khi bỏ qua banner và logging từ Spring Boot, có thứ tự:

```text
AUTO start
MAIN initial auto=true, manual=false
MANUAL start
MAIN after-start auto=true, manual=true
AUTO stop
MANUAL stop
MAIN after-stop auto=false, manual=false
```

Giải thích chi tiết:

1. `AUTO start` xảy ra trong quá trình refresh context, do `SmartLifecycle.isAutoStartup()==true`.
2. Khi `app.run(args)` trả về, auto đã running, manual chưa running.
3. `context.start()` khiến plain Lifecycle start. Auto vẫn running nên không start lần nữa.
4. `context.stop()` dừng phase 100 **trước** phase 0: `AUTO stop` rồi `MANUAL stop`.
5. Hai cờ running đều false. `context.close()` trong `try-with-resources` thực hiện cleanup context; hai beans không cần chạy lại stop vì đã ở trạng thái stopped.

**Quan trọng:** các dòng in không có mã thực hiện polling hay kết nối mạng; demo chỉ mô phỏng state. Để dùng production, phải đưa việc đăng ký và hủy tài nguyên thật vào start/stop, đảm bảo flag chỉ phản ánh kết quả thực tế.

### 7.7. Bài tập restart context lifecycle

Trong `main`, sau `context.stop()` và trước khi rời khối try, có thể thử:

```java
context.start();
System.out.println("MAIN restarted auto=" + auto.isRunning()
        + ", manual=" + manual.isRunning());
```

Đây là đoạn **bổ sung vào main đã có biến `context`, `auto`, `manual`**, không phải chương trình độc lập. Vì cả hai đang stopped, `context.start()` sẽ gọi `MANUAL start` ở phase 0 trước `AUTO start` ở phase 100. Sau đó, `close()` sẽ dừng hai beans còn running theo thứ tự ngược phase.

Điều này minh họa: **auto-startup chỉ quyết định hoạt động tại refresh; phase quyết định thứ tự điều phối khi cần start/stop**. Nếu có dependency thật giữa components, xem thêm mục 9 về thứ tự theo dependency.

## 8. JUnit test để xác nhận contract

Không cần kiểm tra toàn bộ log của Spring Boot. Có thể test trực tiếp state của beans.

Tệp `src/test/java/com/example/lifecycle/LifecycleContractTest.java`:

```java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        classes = LifecycleContractApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LifecycleContractTest {

    @Autowired
    private AutoPollingWorker auto;

    @Autowired
    private ManualPollingWorker manual;

    @Autowired
    private ConfigurableApplicationContext context;

    @Test
    void autoStartsButPlainLifecycleNeedsExplicitStart() {
        assertTrue(auto.isRunning());
        assertFalse(manual.isRunning());

        context.start();
        assertTrue(auto.isRunning());
        assertTrue(manual.isRunning());

        context.stop();
        assertFalse(auto.isRunning());
        assertFalse(manual.isRunning());
    }
}
```

`@SpringBootTest` tạo context thực nhưng không gọi `main(...)` của demo để thực hiện `context.start()` trong `try`. Vì vậy test có thể quan sát `auto` running và `manual` stopped ngay sau khi refresh. `@DirtiesContext` bảo đảm context bị loại khỏi cache của Spring Test sau class, giảm ảnh hưởng trạng thái stop tới test khác.

Chạy:

```bash
mvn test
```

Kỳ vọng **1 test thành công, 0 failures, 0 errors** cho class này, nếu không thêm test khác. Lệnh `mvn package` chạy tests theo mặc định nên có thể quan sát log auto start/stop trong giai đoạn test; đó là output của lifecycle beans trong test, **không phải một lần chạy main**.

Nếu muốn test concurrency/async stop thật, phải dùng concurrency primitives (latches/futures) và timeout thay vì `Thread.sleep(...)` rồi đoán task đã hoàn thành.

## 9. Phase và dependency: cách phối hợp nhiều components

Giả sử một component cung cấp nguồn dữ liệu, một component khác xử lý dữ liệu. Hệ thống có thể cần:

```text
START:
  resourceProvider (phase 0)
       |
       v
  consumer (phase 100)

STOP:
  consumer (phase 100)
       |
       v
  resourceProvider (phase 0)
```

Đây là trường hợp phase đặc biệt hữu ích: người nhận việc khởi động sau nguồn phụ thuộc và dừng trước nguồn phụ thuộc.

Tuy nhiên, **phase không phải phương tiện diễn đạt mọi bean dependency**. Nếu consumer thực sự dùng `ResourceProvider`, hãy dùng constructor injection. Với quan hệ khởi tạo phụ thuộc side effect, có thể xem xét `@DependsOn`, khi đó LifecycleProcessor còn tính dependency khi điều phối.

Ví dụ minh họa:

```java
@Component
class ConsumerCoordinator implements SmartLifecycle {

    private final ResourceProvider resourceProvider;

    ConsumerCoordinator(ResourceProvider resourceProvider) {
        this.resourceProvider = resourceProvider;
    }

    // start(), stop(), isRunning() và getPhase()
    // được triển khai như hợp đồng ở trên.
}
```

Đây là **mẫu thiết kế không độc lập**: cần định nghĩa `ResourceProvider` và triển khai các method. Spring biết bean dependency qua constructor injection, nên không cần cố dựa vào tên bean để mong ordering.

### 9.1. Cùng phase có bảo đảm thứ tự theo alphabet không?

**Không.** Nếu hai Lifecycle beans có cùng phase và không có dependency giữa chúng, thứ tự tương đối có thể do quá trình đăng ký/khởi tạo của container. Không dựa vào tên class, file hoặc `@Order` như một cách tự động quyết định mọi thứ tự start/stop.

Khi cần A hoạt động trước B, hãy tạo dependency thực, đưa chúng vào một coordinator hoặc thiết kế phase phù hợp với contract. Tránh khởi tạo vòng dependency.

### 9.2. `@Order` khác `getPhase()`

`@Order` thường dùng cho việc sắp collection/strategies hoặc callback ở những extension points hỗ trợ ordering. `getPhase()` là hợp đồng **lifecycle start/stop order**. Chúng không thay thế nhau.

| Nhu cầu | Cơ chế |
| --- | --- |
| Sắp `List<Handler>` theo ưu tiên xử lý | `@Order` |
| Kiểm soát thứ tự `start()`/`stop()` của lifecycle components | `Phased` / `SmartLifecycle.getPhase()` |
| B phải nhận instance A khi constructor chạy | Constructor injection |
| B cần side effect init của A hoàn tất | `@DependsOn` khi không có object dependency phù hợp |
| B chỉ chạy sau khi A kết thúc công việc async | Điều phối future/callback hoặc workflow state rõ ràng |

### 9.3. `isAutoStartup=false` không đồng nghĩa phase bị bỏ qua

Một SmartLifecycle trả `false` trong `isAutoStartup()` sẽ không auto start lúc refresh, nhưng khi context được `start()` thủ công, `getPhase()` của nó vẫn có ý nghĩa trong điều phối. Khi context `stop()`/`close()`, các component **đang running** vẫn được xử lý phù hợp.

## 10. Hợp đồng với công việc bất đồng bộ

### 10.1. Start bất đồng bộ: báo running lúc nào?

Nếu `start()` chỉ submit một task rồi trở về:

```java
@Override
public void start() {
    executor.submit(this::connectToBroker);
    running = true;
}
```

Đây là **đoạn anti-pattern minh họa**, không phải file độc lập. `running=true` được đặt trước khi `connectToBroker` thực sự kết nối thành công. `isRunning` do đó có thể báo true trong lúc component chưa phục vụ được.

Những thiết kế tốt hơn tùy yêu cầu:

- Nếu broker phải sẵn sàng **trước startup hoàn tất**, start có thể đợi kết nối có timeout và báo lỗi rõ ràng khi thất bại.
- Nếu chấp nhận kết nối nền, dùng state machine `STARTING`/`RUNNING` và chỉ chuyển `RUNNING` khi kết nối thành công. `Lifecycle.isRunning` là Boolean nên có thể cần thêm API trạng thái nội bộ cho diagnostics.
- Nếu readiness của toàn ứng dụng phụ thuộc vào kết nối, kết hợp health checks và startup readiness policy thay vì tin vào boolean `isRunning()` đơn độc.

### 10.2. Stop bất đồng bộ: callback phải đúng thời điểm

Một SmartLifecycle có thể cho phép dừng trong background nhưng **phải gọi callback sau khi đã dừng xong**:

```text
LifecycleProcessor
    |
    +-- stop(callback)
          +-- Ngừng nhận việc mới
          +-- Hoàn tất/drain công việc đang chạy
          +-- Đóng resource
          +-- Đặt isRunning=false
          +-- callback.run()     <-- báo thật sự hoàn tất
```

**Không** gọi callback ngay khi mới enqueue shutdown nếu cleanup vẫn chạy phía sau. Khi callback bị bỏ quên, processor có thể chờ đến timeout per phase, kéo dài hoặc làm lỗi đóng ứng dụng.

Với event-driven or external resource shutdown, phải xác nhận khi nào tác vụ chấm dứt. Dùng `CompletableFuture.whenComplete`, latch/ack hoặc signal completion có xử lý lỗi; callback cần được gọi đúng một lần kể cả khi cleanup thất bại, đồng thời báo rõ lỗi cho observability. Nếu callback gọi quá sớm, shutdown có thể tiếp tục phase sau và đóng dependency trước khi consumer dừng hẳn.

### 10.3. Thread safety và memory visibility

`isRunning()` thường được gọi từ lifecycle processor, health checks và code ứng dụng trên các threads khác nhau. Nếu cập nhật flag không có memory visibility, thread khác có thể đọc state cũ.

- Dùng `volatile`, `AtomicBoolean` hoặc lock phù hợp.
- Bảo đảm `start()`/`stop()` idempotent khi có lời gọi lặp.
- Nếu trạng thái có nhiều pha, một boolean đơn lẻ có thể thiếu thông tin.
- Không giữ lock trong khi chờ resource do thread khác cần cùng lock để hoàn tất: dễ deadlock.
- Có timeout hữu hạn và xử lý `InterruptedException` bằng cách restore interruption flag khi cần.

**Ví dụ demo** giữ logic start/stop ngắn, chạy đồng bộ, nên `volatile` và `synchronized` đủ để giải thích contract. Nó **không** thay thế bài toán quản lý thread pool, consumer và shutdown thực tế.

### 10.4. Shutdown trong Kubernetes hoặc container

Trong triển khai thực tế, orchestration có thể gửi tín hiệu dừng tới tiến trình. Để Spring xử lý `SmartLifecycle.stop(Runnable)`, context cần được đóng theo cách có kiểm soát.

- Một lần kill cưỡng bức không có bảo đảm callback stop hoặc `@PreDestroy` sẽ chạy.
- Cấu hình graceful shutdown và thời gian chờ hợp lý.
- Dừng nhận việc mới trước khi cắt nguồn tài nguyên bên dưới.
- Không phụ thuộc vào shutdown hook để bảo đảm “exactly once”; consumer có thể bị kill giữa hai bước.
- Tác vụ xử lý message nên có idempotency, retry và checkpoint phù hợp để phục hồi.

Trong Boot web application, graceful HTTP shutdown và custom SmartLifecycle phase có thể tương tác; kiểm tra phase và dependency của server/consumer thật, không chọn số phase tùy tiện khi cần thứ tự chặt chẽ.

## 11. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bean `Lifecycle` đã tạo nhưng `start()` không chạy khi Boot startup | Plain Lifecycle không tự start ở refresh | Gọi `context.start()` hoặc dùng `SmartLifecycle` auto-start |
| `SmartLifecycle` không tự start | `isAutoStartup()` trả false, bean không được đăng ký hoặc startup lỗi | Kiểm tra registration, auto-start flag, exception |
| `isRunning()` luôn true dù consumer đã dừng | Flag chỉ set tại constructor hoặc không cập nhật lúc stop | Chỉ đổi flag khi resource thực sự start/stop |
| `start()` được gọi hai lần tạo hai consumers | Implementation không idempotent | Kiểm tra state và đồng bộ hóa start |
| `stop()` hai lần ném lỗi | Không thiết kế idempotency | Kiểm tra trạng thái trước cleanup |
| `stop(Runnable)` không gọi callback | LifecycleProcessor chờ đến timeout, shutdown kéo dài | Gọi callback đúng một lần sau khi dừng xong |
| Callback gọi ngay khi enqueue shutdown | Phase sau có thể đóng dependency quá sớm | Gọi sau completion signal thật |
| `stop()` của SmartLifecycle không được gọi bởi processor | Processor dùng overload `stop(Runnable)` | Implement/delegate callback overload đúng |
| `@Order(1)` không làm bean start trước | `@Order` khác `getPhase()` | Dùng phase và dependency graph |
| `getPhase()` lớn nhưng start không theo mong đợi | Có dependency override phase hoặc cùng phase | Kiểm tra DI/`depends-on` và các phase |
| `@Lazy` không trì hoãn SmartLifecycle như mong đợi | Auto-start lifecycle có thể kéo bean vào refresh | Dùng `isAutoStartup()` cho bật/tắt auto |
| `context.stop()` không chạy `@PreDestroy` | Stop không phải destroy | Dùng `context.close()` khi muốn đóng toàn context |
| `context.close()` rồi gọi `context.start()` | Context đã đóng | Tạo context mới qua `SpringApplication.run(...)` nếu cần |
| Component running nhưng ứng dụng không ready | Một bean running không đồng nghĩa app readiness | Kiểm tra runners, `ApplicationAvailability`, health probes |
| Exception trong `start()` bị nuốt | Processor tưởng start xong dù resource hỏng | Propagate hoặc xử lý lỗi với state trung thực |
| Shutdown bị timeout | Async stop chậm, deadlock, callback không gọi hoặc broker không trả lời | Timeout, drain protocol, cancellation và observability |

### 11.1. Checklist chẩn đoán

1. Bean có thật được Spring đăng ký (`@Component`, `@Bean`) không?
2. Nó triển khai `Lifecycle` hay `SmartLifecycle`?
3. `isAutoStartup()` có trả true không? Context đã refresh chưa?
4. `isRunning()` ban đầu có phản ánh đúng false không?
5. `start()` có thực sự bật resource hay chỉ submit tác vụ async?
6. Có dependency/phase làm thay đổi thứ tự start không?
7. `stop(Runnable)` có được gọi và callback có chạy sau khi stop hoàn tất không?
8. Context đang `stop()` hay `close()`? Nó đã closed chưa?
9. Có caller nào trực tiếp gọi start/stop và bỏ qua processor không?
10. Có race giữa start/stop, timeout hoặc interrupt không?
11. Application readiness có yêu cầu thêm ngoài `isRunning()` của bean không?
12. Có log/metrics để phân biệt STARTING, RUNNING, STOPPING và FAILED không?

## 12. Tình huống thực tế

### 12.1. Consumer message broker

Khi app startup, client connection được inject nhưng consumer chưa subscribe. `SmartLifecycle.start()` có thể thực hiện đăng ký nhận messages; `stop(Runnable)` dừng nhận mới, drain các messages đang xử lý, rồi gọi callback. Nếu coordinator phải bảo đảm database/resource provider có trước consumer, dùng dependency và phase phù hợp.

### 12.2. Một task collector chỉ chạy khi operator bật

Một component chỉ triển khai plain `Lifecycle`. App tạo bean nhưng chưa start collector. Khi operator kích hoạt một flow quản trị, coordinator có thể gọi lifecycle API theo chính sách. Tránh expose trực tiếp `context.start()` cho request tùy ý vì nó sẽ tác động **tất cả** Lifecycle components thích hợp, không chỉ collector.

### 12.3. Server nhận traffic và worker nền

Trong app web, `SmartLifecycle` của worker có thể start trong refresh, trước `ApplicationReadyEvent`. Nếu worker chỉ được phép xử lý sau khi kiểm tra startup hoàn tất, cần coordinator/runner/ready policy, không mặc định `start()` tương đương “app ready”.

### 12.4. Graceful rolling deployment

Khi orchestrator yêu cầu shutdown, app nên giảm traffic, dừng nhận việc mới, chờ xử lý dở trong thời gian hữu hạn, flush state và giải phóng resources. `SmartLifecycle.stop(Runnable)` cung cấp một điểm hợp tác với Spring shutdown processor; nhưng việc route traffic và retry vẫn cần cấu hình ở load balancer, consumer hoặc Kubernetes.

### 12.5. Bean singleton nhưng cần restart hoạt động

Một singleton có thể duy trì tồn tại trong context trong khi `Lifecycle.stop()` khiến nó tạm ngừng. Nếu implementation hỗ trợ restart, `Lifecycle.start()` có thể bật nó lại. Đây là điểm khác biệt quan trọng với destroy/recreate bean.

## 13. Bài tập tự kiểm tra

1. `@PostConstruct` khác `Lifecycle.start()` như thế nào? Bean đã init có nhất thiết running không?
2. Viết chữ ký ba phương thức của `Lifecycle`; `isRunning()` nên phản ánh điều gì?
3. Vì sao một bean chỉ triển khai `Lifecycle` và có `@Component` có thể không start khi Boot khởi động?
4. Trong ví dụ, vì sao dòng `AUTO start` xuất hiện trước `MAIN initial`?
5. Vì sao `MANUAL start` chỉ xuất hiện sau `context.start()`?
6. Vì sao `AUTO stop` xảy ra trước `MANUAL stop` khi `context.stop()`?
7. `isAutoStartup=false` có ngăn context start thủ công không?
8. So sánh default phase của plain Lifecycle và SmartLifecycle trong Spring Framework 6.1.
9. Chuyện gì xảy ra khi hai lifecycle beans có cùng phase và không có dependency? Có nên dựa vào tên bean để đoán thứ tự không?
10. `stop(Runnable)` khác no-arg `stop()` ở điểm nào? Vì sao callback quan trọng?
11. Nếu implementation `stop(Runnable)` gọi callback **trước** khi resource đóng, hậu quả nào có thể xảy ra ở shutdown phase tiếp theo?
12. Nếu một `SmartLifecycle.start()` chỉ submit một task nền rồi đặt `running=true`, điều gì sai với ý nghĩa `isRunning()`?
13. `context.stop()` có làm gọi `@PreDestroy` không? `context.close()` khác gì?
14. Sau `context.close()`, có thể dùng `context.start()` để khôi phục context không?
15. Có quan hệ DI A → B và `getPhase()` trái chiều: framework có thể ưu tiên quan hệ dependency hay không?
16. `@Order(1)` trên bean có cùng ý nghĩa với `getPhase()==1` không? Giải thích.
17. Với app CLI có hai lifecycle beans, vì sao một bean tự chạy không đồng nghĩa `ReadinessState.ACCEPTING_TRAFFIC`?
18. Làm sao test idempotency của start/stop và callback stop được gọi đúng lúc?
19. Mô tả cách xử lý shutdown khi broker không phản hồi trước timeout.
20. Với một consumer production, đề xuất state machine ít nhất có `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` và tiêu chí chuyển trạng thái.

**Tiêu chí đạt:** chạy được ví dụ Spring Boot non-web; giải thích đúng các dòng output; hiểu chính xác ý nghĩa `start`, `stop`, `isRunning`; phân biệt plain Lifecycle và SmartLifecycle; biết ứng dụng phase và callback shutdown mà không ngộ nhận chúng thay thế readiness hoặc dependency thật.

## 14. Tài liệu tham khảo chính thức

- Spring Framework 6.1 — `Lifecycle`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework 6.1 — `SmartLifecycle` và default methods: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `LifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `ConfigurableApplicationContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Boot 3.3 — Graceful Shutdown và `spring.lifecycle.timeout-per-shutdown-phase`: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot 3.3 — SpringApplication / Application Availability: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
