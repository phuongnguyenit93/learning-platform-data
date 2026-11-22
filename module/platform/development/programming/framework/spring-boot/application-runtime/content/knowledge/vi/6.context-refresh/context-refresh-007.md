# Trạng thái active, running và closed của ApplicationContext trong Spring Boot

## 1. Vì sao phải phân biệt ba trạng thái?

Một ứng dụng Spring Boot có nhiều “cột mốc đang hoạt động” dễ bị gọi chung là *đã chạy*: tiến trình JVM tồn tại, `ApplicationContext` đã được tạo, Spring đã hoàn tất `refresh()`, các thành phần quản lý bằng `Lifecycle` đã bắt đầu, tác vụ `ApplicationRunner` đã kết thúc, ứng dụng sẵn sàng nhận yêu cầu và cuối cùng context được đóng. Các mốc này không xảy ra cùng lúc.

Trong Spring Framework, hai API giúp quan sát trạng thái của context là:

- `ConfigurableApplicationContext.isActive()`: context có còn ở trạng thái **active** theo vòng đời `refresh/close` hay không.
- `ConfigurableApplicationContext.isRunning()`: bộ quản lý vòng đời `LifecycleProcessor` của context có đang ở trạng thái **running** hay không.

Còn **closed** diễn tả việc `close()` đã thực hiện đóng context và giải phóng bean/tài nguyên. Trong API `ConfigurableApplicationContext` thông dụng **không có phương thức `isClosed()`** đối xứng với hai phương thức trên. Chỉ từ `isActive() == false` không thể biết đó là context chưa từng refresh, refresh thất bại hay đã được đóng.

Đây là ba khái niệm về **vòng đời Spring context**; chúng cũng khác với `LivenessState` và `ReadinessState` của Spring Boot, hay trạng thái PID/HTTP server ngoài hệ điều hành.

**Mục tiêu của bài:** đọc và giải thích đúng từng trạng thái, nhận biết tác dụng của `refresh()`, `start()`, `stop()`, `close()`, biết lúc nào bean được khởi động/dừng/tiêu hủy và tránh dùng nhầm trạng thái context làm health check.

Ngữ cảnh kỹ thuật: **Spring Boot 3.3.x, Spring Framework 6.1.x, Java 17+**.

## 2. Bản đồ vòng đời của một context điển hình

```text
SpringApplication tạo ApplicationContext
                  |
                  v
       Context mới, chưa refresh
       isActive()  = false
       isRunning() = false
                  |
                  v
       Chuẩn bị bean definitions
       context.refresh()
          | 
          +--> prepareRefresh() / xử lý BeanFactory
          +--> tạo bean + post-processors
          +--> khởi tạo LifecycleProcessor
          +--> tự start SmartLifecycle phù hợp
          +--> ContextRefreshedEvent
                  |
                  v
       Context hoạt động bình thường
       isActive()  = true
       isRunning() = true (*) 
                  |
          +-------+--------+
          |                |
       stop()           close()
          |                |
          v                v
   isActive = true    ContextClosedEvent
   isRunning = false  ngừng Lifecycle beans
          |           hủy singleton, đóng factory
       start()             |
          |                v
          v           Context đã đóng
   isActive = true    isActive = false
   isRunning = true   isRunning = false
```

`(*)`: kết quả `isRunning() == true` là hành vi thông thường sau `refresh()` thành công với `DefaultLifecycleProcessor` của Spring, dù ứng dụng không có web server. Có thể thay `LifecycleProcessor` hoặc gặp vòng đời lỗi/tùy chỉnh; hãy đọc giá trị thực tế thay vì coi sơ đồ là bất biến cho mọi implementation.

**Cảnh báo về thời điểm trong `refresh()`:** Spring có thể đặt cờ active trong pha chuẩn bị refresh **trước khi toàn bộ bean đã dựng xong**. Vì thế `isActive() == true` nếu quan sát giữa các callback của `refresh()` **không bảo đảm** khởi động thành công hay đã nhận được traffic. Javadoc mô tả active về mặt hợp đồng như “đã được refresh và chưa đóng”, còn chi tiết chuyển cờ ở bên trong giải thích vì sao callback sớm cần thận trọng.

Khi nói “đã đóng”, ta quan tâm đến kết quả **sau khi `close()` trả về thành công**. Trong lúc phát `ContextClosedEvent` hoặc đang hủy bean, một số trạng thái vẫn có thể phản ánh quá trình chuyển tiếp, chưa phải trạng thái cuối.

## 3. `isActive()`: context còn hợp lệ cho giai đoạn sử dụng bean?

### 3.1. Ý nghĩa API

`ConfigurableApplicationContext.isActive()` cho biết context có đang active hay không. Trong triển khai `AbstractApplicationContext` thông thường, cờ này gắn với vòng đời refresh và close:

- **Trước `refresh()`**: chưa active; bean factory/bean definitions có thể chưa sẵn sàng.
- **Khi `refresh()` đang chạy**: cờ có thể được bật từ pha đầu của refresh; các bean vẫn có thể chưa tạo xong.
- **Sau `refresh()` thành công**: active là `true`; có thể truy cập các bean theo hợp đồng container.
- **Sau `stop()`**: active **vẫn `true`** vì `stop()` chỉ dừng thành phần thuộc lifecycle.
- **Sau `close()`**: active là `false`; context không còn là nơi hợp lệ để lấy và dùng bean.
- **Sau refresh thất bại**: triển khai có thể reset active/cleanup; không coi việc từng thấy `true` là bằng chứng ứng dụng startup thành công.

Trong các chương trình thông thường, có thể dùng `isActive()` để kiểm tra một `ConfigurableApplicationContext` do chính bạn giữ trước khi thao tác BeanFactory. Nhưng kiểm tra trạng thái là **ảnh chụp tại một thời điểm**; thread khác có thể yêu cầu đóng context ngay sau đó. Bản thân `isActive()` không thay thế thiết kế đồng bộ hay quản lý tài nguyên.

### 3.2. Những điều `isActive() == true` không chứng minh

Nó **không chứng minh**:

1. Các `ApplicationRunner`/`CommandLineRunner` đã chạy xong.
2. `ApplicationReadyEvent` đã được phát.
3. `ReadinessState` đang là `ACCEPTING_TRAFFIC`.
4. Máy chủ HTTP đang mở đúng cổng hoặc request thật sẽ thành công.
5. Mọi `SmartLifecycle` bean vẫn chạy.
6. Mọi dependency ngoài (database, cache, message broker) vẫn khỏe.
7. Ứng dụng chưa bị yêu cầu dừng ở tầng Kubernetes/load balancer.

Ví dụ: context đã refresh thành công, nhưng một `ApplicationRunner` đang đồng bộ dữ liệu trong vài giây. Khi đó `isActive()` thường là `true`; Spring Boot **chưa** phát `ApplicationReadyEvent`, nên readiness vẫn có thể là `REFUSING_TRAFFIC`. Dựa duy nhất vào active để định tuyến request sẽ quá sớm.

## 4. `isRunning()`: vòng đời của các thành phần đã được khởi động?

`ConfigurableApplicationContext` kế thừa interface `Lifecycle`, vì vậy có:

```java
void start();
void stop();
boolean isRunning();
```

Bên trong `AbstractApplicationContext`, các thao tác này được chuyển cho `LifecycleProcessor`. Spring thường dùng `DefaultLifecycleProcessor` để điều phối những bean implements `Lifecycle`/`SmartLifecycle`.

**Ý nghĩa thực tế:** `context.isRunning()` phản ánh trạng thái quản lý lifecycle của container. Nó không đo “thread JVM nào còn sống”, “scheduler đã xong tất cả job”, “HTTP endpoint có phản hồi”, hoặc “100% các service do ứng dụng tự tạo đang khỏe”.

### 4.1. `Lifecycle` và `SmartLifecycle`

Một bean implements `Lifecycle` có `start()`, `stop()`, `isRunning()`. Đó là contract cho thành phần có thể chạy/dừng mà không nhất thiết bị tiêu hủy.

`SmartLifecycle` bổ sung những khả năng quan trọng:

- `isAutoStartup()`: cho phép bean tự khởi động trong quá trình refresh nếu trả về `true`.
- `getPhase()`: hỗ trợ thứ tự khởi động và dừng theo pha.
- `stop(Runnable callback)`: thông báo cho container biết khi thao tác dừng bất đồng bộ đã hoàn tất; **phải gọi callback** sau khi thực sự dừng.

`DefaultLifecycleProcessor` thường **tự khởi động** các `SmartLifecycle` bean chọn auto-start trong pha kết thúc refresh. Bean chỉ implements `Lifecycle` thông thường không tự động được `onRefresh()` start như một auto-start `SmartLifecycle`; nhưng một lệnh `context.start()` rõ ràng có thể khởi động các bean `Lifecycle` phù hợp.

Khi `context.stop()`, processor dừng các lifecycle beans đang running, theo pha (thứ tự dừng đảo với khởi động), và trạng thái running của processor trở thành `false`. Sau đó `context.start()` có thể gọi start lại nếu context **chưa đóng**.

### 4.2. Đừng đồng nhất running với ready

Bên dưới Spring Boot, một bean `SmartLifecycle` có thể đã chạy khi `ContextRefreshedEvent` được phát, trước khi Boot gọi `ApplicationRunner`. Bởi vậy có thể gặp:

```text
context.isActive()  == true
context.isRunning() == true

nhưng:

ApplicationReadyEvent chưa xảy ra
ReadinessState == REFUSING_TRAFFIC
```

Trường hợp này **không mâu thuẫn**: context/managed lifecycle đã chạy, còn điều kiện nhận traffic của toàn ứng dụng vẫn chưa hoàn tất.

Ngược lại, có thể có `isActive() == true` và `isRunning() == false` sau `context.stop()`; nhiều singleton vẫn tồn tại và có thể được gọi, nhưng các component lifecycle đã ngừng. Đó không phải là context “closed”.

## 5. Closed: điều gì xảy ra khi gọi `close()`?

`ConfigurableApplicationContext` kế thừa `Closeable` và cung cấp `close()`. Với `AbstractApplicationContext` và chuỗi shutdown chuẩn, việc đóng bao gồm các trách nhiệm chính:

1. Bắt đầu đóng context, công bố `ContextClosedEvent` cho listener.
2. Yêu cầu `LifecycleProcessor` dừng các bean có vòng đời cần dừng (ví dụ `SmartLifecycle`).
3. Hủy các singleton do context quản lý, chạy callback như `@PreDestroy`, `DisposableBean.destroy()`, destroy method nếu được cấu hình.
4. Đóng hạ tầng BeanFactory/context, giải phóng tài nguyên liên quan và đánh dấu context không còn active.

Kết quả kỳ vọng khi `close()` trả về bình thường:

```text
context.isActive()  -> false
context.isRunning() -> false
```

Đó là **trạng thái sau đóng**, khác với thời điểm listener nhận `ContextClosedEvent`. Event được phát trong quy trình close, trước khi toàn bộ teardown kết thúc; đừng viết listener giả định rằng mọi bean đều đã bị destroy tại thời điểm đó.

### 5.1. Sau close có được dùng bean nữa không?

Không nên. Dù mã Java vẫn còn giữ **tham chiếu trực tiếp** đến một bean từng lấy từ context, tài nguyên bên trong bean đó có thể đã đóng (DataSource, thread pool, kết nối mạng…). Tham chiếu còn tồn tại **không chứng minh bean còn sử dụng an toàn**.

Lời gọi `getBean(...)` sau khi context đóng có thể gây `IllegalStateException` vì BeanFactory không còn active. Không viết cơ chế “hồi sinh” context đóng bằng cách gọi `start()`. `start()` chỉ điều khiển lifecycle components khi context còn hợp lệ; nó **không** tạo lại bean definitions hoặc chạy lại `refresh()`.

### 5.2. `close()` khác kết thúc JVM

Một chương trình có thể dùng Spring Boot trong CLI, test hoặc service. Khi context đóng:

- Các bean thuộc context được cleanup.
- JVM **có thể vẫn sống** nếu còn thread non-daemon, context khác hoặc phần code khác đang chạy.
- Nếu ứng dụng có JVM shutdown hook do Boot đăng ký, khi JVM nhận yêu cầu kết thúc bình thường, hook có thể đóng context.
- Mất điện, crash JVM, `SIGKILL` hoặc `Runtime.halt()` có thể bỏ qua cơ chế đóng có trật tự.

Cũng đừng coi `ContextClosedEvent` là bằng chứng toàn bộ process đã chết: nó là sự kiện **của một context**, không phải sự kiện toàn hệ điều hành.

## 6. Bảng đối chiếu các trạng thái trong thực tế

| Tình huống | `isActive()` | `isRunning()` | Ý nghĩa |
| --- | --- | --- | --- |
| Vừa tạo context, chưa `refresh()` | `false` | `false` | Chưa dựng bean container đầy đủ. |
| Trong pha đầu của `refresh()` | Có thể `true` | Thường `false` | Chưa thể suy ra đã startup xong. |
| `refresh()` thành công và lifecycle processor đang chạy | `true` | `true` | Context và thành phần lifecycle hoạt động. |
| Sau `ApplicationStartedEvent`, runner chưa hoàn tất | `true` | Thường `true` | Chưa chắc sẵn sàng nhận traffic. |
| Sau `context.stop()` | `true` | `false` | Bean container còn tồn tại; managed lifecycle dừng. |
| Sau `context.start()` thành công | `true` | `true` | Các lifecycle beans được khởi động lại. |
| Đang xử lý `ContextClosedEvent` | Có thể vẫn `true` | Tùy giai đoạn | Quá trình đóng còn đang thực hiện. |
| Sau `context.close()` | `false` | `false` | Context đã đóng, bean cần được coi là không sử dụng nữa. |
| Khởi động thất bại | Không có kết quả ổn định để dựa vào | Không có kết quả ổn định | Boot xử lý lỗi và thường cleanup; xem ngoại lệ gốc. |

Bảng phản ánh hành vi điển hình của `AbstractApplicationContext`, `DefaultLifecycleProcessor` và ứng dụng Spring Boot 3.3 bình thường. Với context tùy chỉnh hoặc lifecycle processor thay thế, cách triển khai có thể khác. Không dùng riêng hai boolean để xây một bộ chẩn đoán toàn bộ runtime.

### 6.1. Ma trận hai boolean

```text
+----------------------+-----------------------+-------------------------------+
| isActive()            | isRunning()           | Cách đọc                       |
+----------------------+-----------------------+-------------------------------+
| false                 | false                 | Chưa refresh / đã đóng / lỗi  |
| true                  | false                 | Active nhưng lifecycle dừng   |
| true                  | true                  | Active và lifecycle đang chạy |
| false                 | true                  | Không phải tổ hợp chuẩn sau   |
|                       |                       | một close/refresh bình thường |
+----------------------+-----------------------+-------------------------------+
```

**Không thể xác định “closed” từ ma trận** nếu không biết đã từng gọi `refresh()`/`close()` hay chưa. Ví dụ `false/false` xuất hiện **cả trước refresh lẫn sau close**. Nếu cần lưu “đã đóng” trong một thư viện tự viết, hãy quản lý trạng thái lifecycle có chủ đích thay vì suy diễn từ `isActive()` duy nhất.

## 7. `refresh()`, `start()`, `stop()`, `close()` khác nhau ở đâu?

| Phương thức | Việc chính được giao cho container | Có tạo/làm mới bean? | Có hủy bean? | Sau khi gọi, context còn dùng được? |
| --- | --- | --- | --- | --- |
| `refresh()` | Chuẩn bị BeanFactory, processor, singleton và lifecycle | **Có**, theo loại context | Có thể cleanup khi refresh lại/lỗi tùy triển khai | Có nếu thành công. |
| `start()` | Gọi start trên các `Lifecycle` beans thích hợp | **Không**, không phải refresh | Không | Có, khi chưa đóng. |
| `stop()` | Gọi stop trên các lifecycle beans thích hợp | Không | **Không** theo nghĩa destroy singleton | Có, context vẫn active. |
| `close()` | Dừng lifecycle rồi hủy bean/đóng container | Không | **Có** | Không. |

### 7.1. `refresh()` không phải là `start()`

Trong `refresh()`, Spring có thể tạo singleton, thực hiện dependency injection, gọi `BeanFactoryPostProcessor`/`BeanPostProcessor`, gọi callback init, và ở cuối gọi `LifecycleProcessor.onRefresh()`. Sau refresh, `isRunning()` thường `true`.

Trong `start()`, Spring **không chạy lại** toàn bộ chuỗi tạo bean hoặc đọc lại `@Configuration`. Nó chỉ khởi động các lifecycle beans theo cơ chế `LifecycleProcessor`.

### 7.2. `stop()` không phải là `close()`

`stop()` nhằm **tạm dừng các thành phần có lifecycle**. Một bean thông thường không implements `Lifecycle` có thể vẫn tồn tại và không nhận lệnh stop. Callback `@PreDestroy` không được gọi chỉ vì context stop.

`close()` là **kết thúc vòng đời context**: lifecycle components bị dừng nếu còn chạy, sau đó singleton bị hủy. Đây là ranh giới lớn khi quản lý tài nguyên.

### 7.3. Có thể refresh lại context hay không?

Không mặc định. Một số subclass của `AbstractApplicationContext` có chiến lược hỗ trợ refresh nhiều lần, nhưng `GenericApplicationContext` và nhiều application context hiện đại có ràng buộc chỉ refresh một lần. Với context do `SpringApplication` tạo, đừng dùng `refresh()` như API “khởi động lại service” hay như một cách phục hồi sau close. Thay đổi config lớn hoặc khởi động lại ứng dụng phải đi theo cơ chế được hỗ trợ của runtime/deployment.

## 8. Ví dụ Java 17+ chạy được: stop, start và close cùng một context

Đây là ví dụ **đầy đủ trong một file Java**, không cần HTTP server. Sử dụng `spring-boot-starter`, Java 17+ và Spring Boot 3.3.x. Nội dung in trạng thái từ chính `ConfigurableApplicationContext` và tạo một bean `SmartLifecycle` để nhìn thấy lúc component start/stop.

**File:** `src/main/java/com/example/contextstate/ContextStateDemoApplication.java`

```java
package com.example.contextstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ContextStateDemoApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ContextStateDemoApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addInitializers(context -> printState("INITIALIZER", context));

        ConfigurableApplicationContext context = app.run(args);
        try {
            printState("AFTER_RUN", context);

            context.stop();
            printState("AFTER_STOP", context);

            context.start();
            printState("AFTER_RESTART", context);
        } finally {
            context.close();
        }

        printState("AFTER_CLOSE", context);
    }

    private static void printState(
            String label, ConfigurableApplicationContext context) {
        System.out.println(
                label
                + " active=" + context.isActive()
                + " running=" + context.isRunning()
        );
    }

    @Bean
    SmartLifecycle exampleComponent() {
        return new SmartLifecycle() {
            private volatile boolean running;

            @Override
            public void start() {
                running = true;
                System.out.println("COMPONENT start");
            }

            @Override
            public void stop() {
                running = false;
                System.out.println("COMPONENT stop");
            }

            @Override
            public void stop(Runnable callback) {
                stop();
                callback.run();
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
                return 0;
            }
        };
    }
}
```

Trong ứng dụng Gradle đã áp dụng Spring Boot plugin 3.3.x và dependency management, dependency của ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Chạy từ thư mục dự án có Gradle Wrapper:

```bash
./gradlew bootRun
```

Windows CMD dùng `gradlew.bat bootRun`; PowerShell dùng `.\gradlew.bat bootRun`. Không cần `spring-boot-starter-web`, không cần cổng 8080 hoặc database.

### 8.1. Các dòng trạng thái kỳ vọng

Bỏ qua banner/log Spring Boot của môi trường. Trong một lần chạy thành công bằng `DefaultLifecycleProcessor`, các dòng mà chương trình in thường theo thứ tự:

```text
INITIALIZER active=false running=false
COMPONENT start
AFTER_RUN active=true running=true
COMPONENT stop
AFTER_STOP active=true running=false
COMPONENT start
AFTER_RESTART active=true running=true
COMPONENT stop
AFTER_CLOSE active=false running=false
```

Giải thích lần lượt:

1. **`INITIALIZER`** chạy trước refresh, chưa có lifecycle processor hoạt động: `false/false`.
2. Trong refresh, Spring nhận thấy `SmartLifecycle.isAutoStartup() == true` nên gọi `COMPONENT start`.
3. `app.run(args)` chỉ trả về sau khi Boot hoàn tất trình tự khởi động, gồm runner và ready event: thường `true/true`.
4. `context.stop()` khiến managed lifecycle component nhận `stop()`, nhưng context vẫn active: `true/false`.
5. `context.start()` khởi động component lần nữa: `true/true`.
6. `context.close()` dừng component và đóng context. Sau khi close trả về: `false/false`.

`SmartLifecycle.stop(Runnable)` trong ví dụ luôn gọi `callback.run()` sau khi hoàn thành stop. Đây là phần **bắt buộc nếu bạn triển khai stop bất đồng bộ**: processor cần tín hiệu hoàn tất để không đợi đến timeout của pha. Trong ví dụ chúng ta dừng đồng bộ rồi gọi callback ngay.

**Không nên dùng ví dụ này để mô phỏng khôi phục web server ngoài thực tế.** Đây là ứng dụng `NONE` nhằm minh họa lifecycle. Với web server, broker listener và hạ tầng phức tạp, `stop()/start()` có thể gây gián đoạn nhận request hoặc hoạt động mạng; hãy xác định contract của từng component và dùng hệ thống điều phối phù hợp.

### 8.2. Vì sao có `try/finally`?

`close()` nằm trong `finally` để được gọi khi phần thao tác stop/start có exception sau khi `run` đã trả về context. Nếu **chính `app.run(...)` thất bại**, biến context chưa được gán nên đoạn `finally` này chưa chạy; Spring Boot có xử lý startup failure riêng. Đừng diễn giải ví dụ là mọi trường hợp crash JVM hoặc mất điện đều được cleanup.

## 9. Ví dụ nhỏ: `@PreDestroy` chỉ khi hủy bean, không phải `stop()`

Tạo một bean thông thường:

```java
package com.example.contextstate;

import jakarta.annotation.PreDestroy;

public class ReportClient {

    @PreDestroy
    public void dispose() {
        System.out.println("ReportClient destroyed");
    }
}
```

Đăng ký bean đó trong class `@Configuration`/`@SpringBootApplication`:

```java
@Bean
ReportClient reportClient() {
    return new ReportClient();
}
```

Nếu thêm bean trên vào ví dụ `ContextStateDemoApplication` và giữ trình tự `stop() → start() → close()`, log `ReportClient destroyed` xuất hiện khi context hủy bean ở quá trình `close()`, không chỉ vì `context.stop()`.

Hai đoạn trên là **các phần bổ sung cho project ở mục 8**. Đặt class `ReportClient` vào đúng package, import `@Bean` trong class cấu hình; không chạy hai đoạn riêng lẻ như chương trình Java độc lập. Spring Boot starter 3.3 đã tích hợp hạ tầng Jakarta annotations cần thiết cho mô hình này.

Một bean cũng có thể có `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()`. Những callback khởi tạo này xảy ra khi bean được tạo trong refresh, **không chạy lại** sau lệnh `context.start()`. Các callback destroy có hợp đồng riêng và cũng không được gọi khi chỉ `stop()`.

## 10. Context state khác gì trạng thái Boot Liveness/Readiness?

Spring Boot có abstraction `ApplicationAvailability` với hai trục:

- **`LivenessState`**: `CORRECT` hoặc `BROKEN`, đại diện đánh giá khả năng nội tại của ứng dụng.
- **`ReadinessState`**: `ACCEPTING_TRAFFIC` hoặc `REFUSING_TRAFFIC`, đại diện quyết định có nên tiếp nhận công việc/lưu lượng hay không.

Trong startup mặc định:

```text
Context được tạo
     |
     v
refresh thành công
  active=true
  lifecycle running (thông thường true)
     |
     v
ApplicationStartedEvent
     |
     v
LivenessState.CORRECT
     |
     v
ApplicationRunner / CommandLineRunner
     |
     v
ApplicationReadyEvent
     |
     v
ReadinessState.ACCEPTING_TRAFFIC
```

Vì vậy:

- `isActive()` trả lời một câu hỏi về **vòng đời của Spring context**.
- `isRunning()` trả lời một câu hỏi về **LifecycleProcessor và các component do nó quản lý**.
- `LivenessState`/`ReadinessState` là **tín hiệu vận hành của Spring Boot** dành cho quyết định restart/định tuyến.
- Một probe HTTP trả về 200/503 còn phụ thuộc server, Actuator, routing và health indicators.

**Điểm cần nhớ:** `context.stop()` không phải một giao thức tổng quát có bảo đảm tự công bố `ReadinessState.REFUSING_TRAFFIC` cho hệ thống điều phối. Tùy ứng dụng và thành phần web, lệnh stop có thể làm hạ tầng ngừng phục vụ nhưng không đồng nghĩa readiness đã được thay đổi theo đúng chiến lược drain. Nếu cần dừng nhận traffic có điều khiển, thiết kế readiness, quy trình rút instance và graceful shutdown riêng.

Khi có `spring-boot-starter-actuator`, Spring Boot có thể expose `/actuator/health/liveness` và `/actuator/health/readiness` khi probes được bật (Boot tự bật trong Kubernetes hoặc có thể đặt `management.endpoint.health.probes.enabled=true` ở nơi khác). **Không** thay thế các endpoint này bằng một health indicator chỉ trả về kết quả của `isActive()`.

## 11. `ContextClosedEvent` xảy ra lúc nào?

`ContextClosedEvent` là sự kiện Spring Framework phát khi context bắt đầu quá trình đóng. Nó **không** có nghĩa “mọi bean đã destroy xong”.

Nếu bạn đăng ký:

```java
@EventListener
public void onClosing(ContextClosedEvent event) {
    System.out.println("Context is closing");
}
```

Đây là **method minh họa** nằm trong một bean `@Component` hoặc class `@Configuration`, có import `org.springframework.context.event.ContextClosedEvent` và `org.springframework.context.event.EventListener`. Listener được gọi trong quá trình `close()`, thường trước khi lifecycle beans bị dừng và singleton được hủy.

Vì event được phát khi context vẫn đang đóng, **đừng khẳng định `event.getApplicationContext()` sẽ báo `isActive() == false` ngay trong callback**. Trạng thái cuối cần kiểm tra **sau khi `close()` đã trả về**.

Nếu cần dừng hạ tầng có cấu trúc và bảo đảm trình tự, `SmartLifecycle`/`LifecycleProcessor` thường phù hợp hơn việc nhét toàn bộ teardown vào listener. Nếu cần giải phóng tài nguyên do một bean sở hữu, dùng `@PreDestroy` hoặc destroy method cho bean đó.

Lưu ý context có thể có quan hệ parent/child: event từ child có thể truyền tới parent listener. Khi triển khai event listener trong hệ thống nhiều context, nên kiểm tra identity của context mà sự kiện thuộc về để tránh chạy logic cleanup nhiều lần không chủ ý.

## 12. Context đã đóng có thể mở lại không?

Câu trả lời dùng cho ứng dụng Spring Boot thông thường: **đừng coi context đóng là đối tượng có thể mở lại bằng `start()`**.

- `start()` không làm lại `refresh()` và không tạo mới các bean đã destroy.
- `isActive() == false` sau close phản ánh vòng đời đã kết thúc; không thử gọi `getBean(...)` để phục hồi.
- Một số class context đặc biệt có cơ chế refresh nhiều lần, nhưng đó là **contract của implementation cụ thể**, không phải bảo đảm chung của mọi `ApplicationContext`.
- Nếu muốn tạo instance ứng dụng mới sau khi instance cũ đã đóng, cần quy trình tạo một context **mới** bằng SpringApplication hoặc môi trường triển khai phù hợp.
- Với service trong container/Kubernetes, khởi động lại process/pod theo deployment thường rõ ràng hơn việc tự quản lý reset context giữa lúc nhận traffic.

### 12.1. Vì sao việc gọi `refresh()` lần hai có thể lỗi?

`GenericApplicationContext` có contract đăng ký bean definitions rồi refresh một lần; việc gọi lại `refresh()` có thể ném `IllegalStateException`. Trong Spring Boot, các implementation web context tương ứng có chính sách và trạng thái nội bộ của riêng mình. Không giả định “có method refresh() là có thể restart tùy ý”.

### 12.2. Có cần đặt cờ “closed” riêng?

Chỉ khi ứng dụng/thư viện có yêu cầu thật sự. Một hệ thống quản lý tài nguyên của bạn có thể lưu enum rõ ràng `NEW → STARTING → RUNNING → STOPPING → CLOSED` để theo dõi những thay đổi do chính nó kiểm soát. Nếu chỉ giữ một tham chiếu `ConfigurableApplicationContext`, dùng `isActive()` và `isRunning()` để quan sát trạng thái Spring, nhưng không suy ra mọi giai đoạn tùy biến trong nghiệp vụ.

## 13. Graceful shutdown và đóng context

Trong một ứng dụng web Spring Boot 3.3, graceful shutdown là cơ chế phối hợp giữa HTTP server và lifecycle của context. Cấu hình rõ ràng:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Khi ứng dụng nhận tín hiệu dừng được xử lý bình thường, các thành phần có `SmartLifecycle` được dừng theo thứ tự pha, web server ngừng tiếp nhận request mới theo khả năng của implementation và cho request đang chạy cơ hội hoàn thành trong thời gian cho phép.

**Đừng đánh đồng:**

- **`context.stop()`**: yêu cầu dừng managed lifecycle components, thường giữ context active.
- **`context.close()`**: hoàn tất shutdown context và hủy beans.
- **Graceful shutdown HTTP**: chính sách server xử lý request đang chạy khi context dừng/đóng.
- **Container/pod termination**: deadline của nền tảng có thể buộc kết thúc nếu app dừng quá chậm.

`spring.lifecycle.timeout-per-shutdown-phase` là giới hạn thời gian cho **mỗi pha** dừng, không bảo đảm tất cả công việc nền sẽ hoàn tất. Một `KafkaListener`, scheduler hay thread tự tạo có contract dừng riêng; cần bảo đảm nó ngừng lấy công việc mới, giải phóng tài nguyên và tuân thủ thời gian được cấp.

### 13.1. Thứ tự stop theo phase

`DefaultLifecycleProcessor` start các lifecycle beans theo phase tăng dần và stop theo phase giảm dần. Ví dụ A có `phase=0` và B có `phase=100`:

```text
START: A -> B
STOP:  B -> A
```

Mục đích là khi B phụ thuộc A, A được khởi động trước, và B được dừng trước khi hạ A xuống. Spring cũng có thể tính đến quan hệ bean dependency. Không nên chọn phase chỉ theo số “càng lớn càng quan trọng”; hãy xác định dependency và thứ tự dừng thực tế.

Với `SmartLifecycle.stop(Runnable)`, nếu shutdown bất đồng bộ, callback **phải** được gọi khi component thực sự dừng; nếu bỏ qua, processor có thể đợi hết timeout của phase. Đó là khác biệt giữa một shutdown được điều phối và một lệnh hủy tài nguyên đột ngột.

## 14. Các kịch bản chẩn đoán thường gặp

### Kịch bản A — isActive true, nhưng HTTP 503

Context có thể active và running, nhưng readiness hiện là `REFUSING_TRAFFIC` hoặc hệ thống ngoài không phục vụ được. Kiểm tra `ApplicationReadyEvent`, readiness probe, health indicator, server logs và dependency liên quan. Không tự kết luận context bị đóng.

### Kịch bản B — isActive true, isRunning false

Có thể ai đó gọi `context.stop()` hoặc lifecycle processor bị dừng do điều phối. Bean container vẫn active; inspect call site thực hiện stop và trạng thái của từng `Lifecycle` bean. Nếu app còn nhận traffic ở một nơi khác, cần thiết kế lại quy trình drain vì hai cờ không là bộ lọc lưu lượng hoàn chỉnh.

### Kịch bản C — isActive false ngay trong initializer

Đây là hành vi bình thường: initializer nhận context trước `refresh()`. Không cố gọi `context.refresh()` từ initializer để “sửa” cờ false; `SpringApplication` phải điều khiển thứ tự refresh.

### Kịch bản D — isActive false sau khi gọi close

Đó là kết quả đúng. Không giữ bean cũ để tiếp tục gửi request đến connection pool đã đóng. Nếu logic phía sau vẫn cần dịch vụ, phải quản lý ranh giới shutdown và tạo context/process mới theo thiết kế.

### Kịch bản E — shutdown đợi lâu

Có thể `SmartLifecycle.stop(Runnable)` không gọi callback, có pha dừng quá lâu hoặc còn work queue đang xử lý. Kiểm tra `spring.lifecycle.timeout-per-shutdown-phase`, thread dump và thời hạn của orchestrator. Đừng chỉ nhìn `isRunning()` vì nó không giải thích *component nào* chưa hoàn tất.

### Kịch bản F — log ContextClosedEvent nhưng JVM không thoát

`ContextClosedEvent` chỉ chứng minh chuỗi đóng context đã bắt đầu, chưa chứng minh kết thúc process. Kiểm tra thread non-daemon, shutdown hook khác, client/timer không thuộc context và container còn chạy. Nếu JVM bị `SIGKILL` thì event có thể không được phát.

## 15. Những hiểu lầm cần tránh

| Hiểu lầm | Kết luận đúng |
| --- | --- |
| “`isActive() == true` nghĩa là service đã ready.” | Active là trạng thái context; readiness là tín hiệu vận hành riêng. |
| “`isRunning() == true` nghĩa mọi thread đều chạy tốt.” | Running do `LifecycleProcessor` quản lý; không đo mọi thread/JVM component. |
| “`stop()` đóng toàn bộ bean và gọi `@PreDestroy`.” | Stop thường chỉ dừng managed lifecycle; destroy xảy ra khi close/destroy. |
| “`start()` sau stop sẽ chạy lại `ApplicationRunner`.” | Start không chạy lại toàn bộ SpringApplication startup. |
| “`false/false` luôn nghĩa context closed.” | Cũng có thể là context chưa từng refresh. |
| “Thấy `ContextClosedEvent` nghĩa mọi resource đã đóng.” | Event phát trong quá trình close, trước teardown hoàn tất. |
| “`close()` sẽ buộc JVM dừng ngay.” | JVM có thể còn thread hoặc context khác giữ sống. |
| “Tự gọi `refresh()` lần nữa là cách restart Spring Boot.” | Refresh lặp không được bảo đảm; nhiều context chỉ refresh một lần. |
| “Đặt graceful shutdown bảo đảm mọi request/job đều xong.” | Phụ thuộc giới hạn thời gian và cơ chế dừng của từng thành phần. |
| “Một bean không implements `Lifecycle` cũng nhận stop.” | Thông thường nó không nhận callback stop; nó vẫn có callback destroy khi close. |
| “`isActive()` chính xác bằng đã xử lý xong `ApplicationReadyEvent`.” | Active có thể true rất sớm trong refresh và trước runners. |

## 16. Checklist áp dụng vào một dự án thực tế

1. Xác định **ai sở hữu** `ConfigurableApplicationContext` và ai có quyền `close()`, tránh đóng từ tầng request bất kỳ.
2. Quan sát `isActive()` và `isRunning()` đúng lúc, nhưng không dùng hai cờ thay thế readiness probe.
3. Kiểm kê các bean implements `Lifecycle`/`SmartLifecycle`, đặc biệt listener, scheduler, consumer và web server.
4. Kiểm tra `isAutoStartup()` và `getPhase()`; đừng mặc định bean nào cũng tự start giống nhau.
5. Khi viết `stop(Runnable)`, bảo đảm callback được gọi **sau khi** dừng hoàn tất.
6. Đặt timeout cho shutdown, theo dõi callback dọn dẹp và tránh công việc I/O vô hạn trong listener.
7. Dùng `@PreDestroy`/destroy method để giải phóng tài nguyên do bean sở hữu khi context close.
8. Tránh gọi `refresh()`/`start()` để “hồi sinh” context đã closed.
9. Với web service, đối chiếu readiness, liveness, HTTP server, lỗi và deployment deadline khi khởi động/dừng.
10. Khi phân tích sự cố, ghi nhận mốc sự kiện (`ContextRefreshedEvent`, `ApplicationStartedEvent`, `ApplicationReadyEvent`, `ContextClosedEvent`) và ngoại lệ gốc thay vì suy luận từ một boolean.

## 17. Tóm tắt mô hình cần ghi nhớ

**Active** nói context còn ở trạng thái vòng đời cho phép container hoạt động; **running** nói lifecycle processor đang vận hành các thành phần được quản lý; **closed** nói context đã hoàn tất quá trình đóng và hủy bean. Ba trạng thái liên quan chặt chẽ nhưng **không thay thế cho nhau**.

```text
refresh thành công -> active
lifecycle processor start -> running
stop -> running=false, active vẫn true
start -> running=true, active vẫn true
close -> destroy + active=false, running=false

ready/healthy HTTP? -> kiểm tra readiness/liveness/server riêng
```

Điểm quan trọng nhất để làm việc an toàn với Spring Boot: **`stop()` và `close()` không tương đương; `isActive()` và `isRunning()` không tương đương; cả hai cũng không tương đương với readiness**.

## Tài liệu chính thức

- [Spring Framework 6.1 — ConfigurableApplicationContext: refresh, close, isActive, Lifecycle](https://docs.spring.io/spring-framework/docs/6.1.0/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html)
- [Spring Framework 6.1 — AbstractApplicationContext: isActive/isRunning và quá trình đóng](https://docs.spring.io/spring-framework/docs/6.1.2/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html)
- [Spring Framework 6.1 — DefaultLifecycleProcessor: onRefresh, onClose, start, stop và phase](https://docs.spring.io/spring-framework/docs/6.1.7/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html)
- [Spring Framework 6.1 — Lifecycle và SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.1.10/javadoc-api/org/springframework/context/Lifecycle.html)
- [Spring Framework — Customizing the Nature of a Bean (Lifecycle, SmartLifecycle)](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html)
- [Spring Boot 3.3 — SpringApplication Events, Runners, Liveness, Readiness](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)
