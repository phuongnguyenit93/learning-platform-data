# Tương tác giữa SmartLifecycle, khởi tạo lười và đóng ApplicationContext

## 1. Bức tranh tổng thể

Trong Spring Boot, một bean có thể vừa tham gia **vòng đời của container**, vừa được đánh dấu **khởi tạo lười (lazy initialization)**, vừa sở hữu tài nguyên cần dừng an toàn khi `ApplicationContext` đóng. Ba chủ đề này thường bị nhầm thành một, dẫn tới các lỗi như:

- Đã đặt `@Lazy` nhưng constructor của bean `SmartLifecycle` vẫn chạy khi ứng dụng khởi động.
- Đã bật `spring.main.lazy-initialization=true` nhưng worker hoặc listener nền vẫn tự chạy.
- Đã triển khai `stop()` nhưng khi đóng context, công việc bất đồng bộ chưa kết thúc mà tài nguyên đã bị hủy.
- Đã đặt `@PreDestroy` nhưng không hiểu nó khác `SmartLifecycle.stop(Runnable)` ở đâu.
- Đã đặt `phase` nhưng lại dừng dependency trước khi dừng thành phần đang sử dụng nó.

**Kết luận cốt lõi:** `SmartLifecycle` dùng để **điều phối thời điểm start/stop** của một thành phần, đặc biệt là những thành phần cần tự chạy khi context refresh và cần stop theo thứ tự có kiểm soát. `@Lazy` và `spring.main.lazy-initialization=true` chủ yếu điều khiển **khi nào bean instance được tạo**. `ApplicationContext.close()` điều phối **đóng context**, bao gồm phát sự kiện, dừng lifecycle components rồi hủy các singleton thích hợp.

**Điểm dễ nhầm quan trọng nhất:** tài liệu chính thức của Spring Framework lưu ý rằng bean `SmartLifecycle` **thường vẫn được khởi tạo khi context startup**, ngay cả khi bean definition có lazy-init, bởi cơ chế auto-start cần phát hiện và xử lý lifecycle bean. Vì vậy `@Lazy` chỉ có **tác dụng rất hạn chế** đối với `SmartLifecycle`. Đừng dùng `@Lazy` như cam kết rằng một `SmartLifecycle` sẽ chưa được tạo hoặc chưa chạy trước request đầu tiên.

### 1.1. Sơ đồ ba lớp trách nhiệm

```text
SpringApplication.run(...)
          |
          v
 ApplicationContext.refresh()
          |
          +-- Tạo bean cần thiết
          |     |-- Singleton eager thông thường
          |     |-- Infrastructure beans
          |     +-- SmartLifecycle beans có thể được khởi tạo
          |         dù đã đánh dấu @Lazy
          |
          +-- LifecycleProcessor.onRefresh()
          |     +-- tìm những lifecycle components phù hợp
          |     +-- sắp xếp theo phase và dependency
          |     +-- gọi start() cho auto-start SmartLifecycle
          |
          +-- ContextRefreshedEvent
          |
          v
  ApplicationStartedEvent / runners / ApplicationReadyEvent
          |
          | Ứng dụng hoạt động
          |
          v
 ApplicationContext.close()
          |
          +-- ContextClosedEvent
          +-- LifecycleProcessor.onClose()
          |     +-- stop SmartLifecycle theo phase ngược
          |     +-- chờ stop(Runnable callback) hoàn tất
          |         trong giới hạn cấu hình
          +-- Destroy singleton instances
          |     +-- @PreDestroy
          |     +-- DisposableBean.destroy()
          |     +-- destroyMethod khác (nếu có)
          |
          v
 Context đóng
```

Sơ đồ rút gọn các giai đoạn quan trọng. Trật tự cụ thể còn tùy implementation và loại ứng dụng. Nó không có nghĩa mọi bean đều được tạo khi refresh, hoặc mọi `SmartLifecycle` đều phải auto-start.

## 2. Các interface phải phân biệt

### 2.1. Lifecycle

Spring Framework có interface:

```java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
```

Đây là **chữ ký được rút gọn để học**, không phải source file cần tạo lại. `Lifecycle` mô tả khả năng một thành phần được bắt đầu, dừng và báo trạng thái đang chạy. Nó không mặc nhiên yêu cầu bean được tự khởi động lúc context refresh theo cùng cơ chế của `SmartLifecycle`.

Một `Lifecycle` bean có thể được context start/stop qua `ConfigurableApplicationContext.start()` và `stop()` khi bộ xử lý lifecycle hoạt động.

### 2.2. Phased

`Phased` cung cấp:

```java
int getPhase();
```

Giá trị `phase` xác định thứ tự start/stop tương đối:

- **Start:** phase nhỏ trước, phase lớn sau.
- **Stop:** phase lớn trước, phase nhỏ sau.

Nếu bean B dùng bean A và muốn A chạy trước, đặt phase của A **nhỏ hơn** phase của B, trừ khi bạn đã khai báo quan hệ dependency rõ để framework áp dụng quy tắc phụ thuộc.

### 2.3. SmartLifecycle

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`, thêm hai khả năng quan trọng:

```java
public interface SmartLifecycle extends Lifecycle, Phased {

    default boolean isAutoStartup() {
        return true;
    }

    default void stop(Runnable callback) {
        stop();
        callback.run();
    }

    default int getPhase() {
        return Integer.MAX_VALUE;
    }
}
```

Đây là **bản biểu diễn hợp đồng mặc định theo Spring Framework 6.1**, lược bỏ Javadoc và các chi tiết thư viện. Khi viết code, hãy `implements org.springframework.context.SmartLifecycle` thay vì định nghĩa lại interface này.

Điểm cần hiểu:

1. `isAutoStartup()` trả `true` theo mặc định: bean thích hợp được tự start trong quá trình refresh.
2. `stop(Runnable callback)` là callback được bộ quản lý lifecycle sử dụng khi stop `SmartLifecycle`, cho phép báo **khi nào quá trình stop đã thật sự hoàn thành**.
3. `getPhase()` mặc định là `Integer.MAX_VALUE` trong Spring Framework 6.1: bean ở phase mặc định thường start muộn và stop sớm hơn các lifecycle beans ở phase thấp.
4. `isRunning()` phải phản ánh trạng thái thực; không được luôn trả `true` hoặc `false` cho tiện.
5. `start()` và `stop()` nên có hành vi gọi lại an toàn nếu kiến trúc có thể phát yêu cầu trùng.

**Không đồng nhất auto-start với lazy-init:** `isAutoStartup()` điều khiển **có tự gọi `start()` khi refresh hay không**; nó không phải cờ buộc container **không tạo instance**.

## 3. Bốn mốc thường bị lẫn lộn

| Mốc | Việc diễn ra | Điều chưa nên kết luận |
| --- | --- | --- |
| Tạo bean | Constructor, injection, lifecycle bean callbacks được xử lý | Bean đã `start()` và thực sự chạy |
| `SmartLifecycle.start()` | Thành phần chuyển sang trạng thái hoạt động khi được yêu cầu | Mọi runner đã chạy, app đã sẵn sàng nhận traffic |
| `SmartLifecycle.stop(Runnable)` | Thành phần được yêu cầu ngừng, có thể ngừng bất đồng bộ | Toàn bộ singleton đã bị destroy |
| Destruction callback | `@PreDestroy`, `DisposableBean`, custom destroy method của bean thích hợp | Chính callback này đã làm đúng mọi việc stop theo phase |

Một bean có thể:

- **Đã được tạo nhưng chưa running**: ví dụ `isAutoStartup() == false`.
- **Đã running nhưng chưa ready toàn ứng dụng**: `start()` được gọi trong refresh, trước các runner.
- **Đã stop nhưng instance vẫn tồn tại**: context đã thực hiện stop phase, chưa destroy singleton.
- **Đã được tạo và không bao giờ started**: vẫn có thể có `@PreDestroy` khi context đóng.

Thiết kế shutdown đúng phải xác định cả hai bước **ngừng nhận/xử lý công việc** và **giải phóng tài nguyên**; không nên gộp tên method để coi hai bước là một.

## 4. Vì sao @Lazy có tác dụng hạn chế với SmartLifecycle?

### 4.1. Cơ chế singleton lazy thông thường

Một bean singleton bình thường được đánh dấu:

```java
@Component
@Lazy
class OptionalFormatter {
    OptionalFormatter() {
        System.out.println("formatter.constructed");
    }
}
```

Nếu không có bean eager khác yêu cầu formatter, container có thể hoãn tạo nó cho đến khi `getBean` hoặc một đường injection/lời gọi cần dùng. `@Lazy` ở đây chủ yếu thay đổi việc **pre-instantiate** bean.

### 4.2. SmartLifecycle khác ở khâu phát hiện bean

Nếu lớp lại implements `SmartLifecycle`:

```java
@Component
@Lazy
class BackgroundReceiver implements SmartLifecycle {
    // start(), stop(), isRunning(), ...
}
```

`DefaultLifecycleProcessor` cần xác định những thành phần lifecycle phải auto-start và sắp xếp chúng theo phase. Để làm được, nó thường cần lấy/khởi tạo các bean `SmartLifecycle`. Do đó **lifecycle bean thường vẫn xuất hiện và được start trong startup**, kể cả khi bean definition có `@Lazy`.

Tài liệu Javadoc `SmartLifecycle` của Spring Framework 6.1 nêu thẳng: do khả năng auto-start, instance `SmartLifecycle` thường được khởi tạo lúc application context startup; vì vậy bean-definition lazy-init có hiệu quả rất hạn chế đối với những bean này.

**Không nên suy luận ngược:** lời khẳng định “thường được khởi tạo” không phải bảo đảm mọi implementation hoặc mọi điều kiện đều tạo **mọi** bean đó. Có thể có điều kiện đăng ký bean, proxy, custom lifecycle processor, scope hoặc context chưa hoàn tất refresh. Nhưng trong context chuẩn, **`@Lazy` không phải công cụ thích hợp để yêu cầu một `SmartLifecycle` mặc định nằm yên đến khi được gọi lần đầu**.

### 4.3. Global lazy cũng không bảo đảm SmartLifecycle được hoãn

Spring Boot cho phép:

```properties
spring.main.lazy-initialization=true
```

Cờ này áp dụng lazy initialization rộng cho các bean đủ điều kiện, thường có ích để giảm thời gian tạo singleton lúc startup. Tuy nhiên lifecycle infrastructure vẫn cần hoạt động; `SmartLifecycle` có thể tiếp tục được phát hiện, khởi tạo và auto-start.

Vì vậy trong application có global lazy:

```text
Ordinary @Lazy bean:
  Có thể chưa được tạo lúc SpringApplication.run() trả về.

SmartLifecycle @Lazy bean:
  Thường đã được khởi tạo và start trong refresh.
```

Điều quan trọng là phân biệt **lazy-initialization policy** với **lifecycle start policy**. Hai chính sách không thay thế nhau và không tự triệt tiêu nhau.

### 4.4. @Lazy tại injection point càng không phải công tắc start/stop

Ví dụ một bean nhận:

```java
MyCoordinator(@Lazy BackgroundReceiver receiver) {
    this.receiver = receiver;
}
```

Đoạn này là snippet minh họa: cần class `MyCoordinator` và bean `BackgroundReceiver` phù hợp, import `@Lazy`, field `receiver`; không phải chương trình Java độc lập.

`@Lazy` ở constructor parameter có thể khiến dependency được tiêm qua lazy-resolution proxy. Nhưng nếu `BackgroundReceiver` là bean `SmartLifecycle`, **lifecycle processor vẫn có thể chủ động tạo/start target độc lập** trong refresh. Proxy chỉ hoãn phân giải **qua đường tiêm đó**, không điều khiển lifecycle toàn cục của target.

Nếu muốn receiver **không tự start**, cần thiết kế `isAutoStartup()` và quyết định rõ ai/bao giờ gọi `start()`; đừng chỉ thêm `@Lazy` ở consumer.

## 5. isAutoStartup(): phân biệt chưa start và chưa tạo bean

Mặc định `SmartLifecycle.isAutoStartup()` trả `true`. Có thể override:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

Điều này nói với lifecycle processor: **đừng tự start bean này tại refresh; tôi sẽ quyết định lúc start sau**.

Tuy nhiên:

- `isAutoStartup() == false` **không phải** một cam kết rằng constructor chưa chạy.
- Container có thể vẫn cần khởi tạo instance để phát hiện lifecycle bean hoặc đọc `getPhase()`/`isAutoStartup()`.
- Một consumer eager, `ApplicationRunner` hoặc code khác vẫn có thể yêu cầu bean instance.
- Bean có thể được gọi `start()` sau đó qua API lifecycle hoặc qua `context.start()` theo cấu hình, khi đã được tạo và đăng ký đúng.
- Nếu bean chưa bao giờ running, việc stop phase xử lý nó có thể khác bean đã running; **destruction callback vẫn là trách nhiệm độc lập**.

**Công thức nhớ:** `isAutoStartup=false` = *không tự chuyển trạng thái sang running khi refresh*. Nó **không đồng nghĩa** *không có instance trong BeanFactory*.

Một cơ chế thật sự cần khởi động **theo nhu cầu nghiệp vụ** có thể phù hợp hơn với một service bình thường chứa phương thức `startOnDemand()` và `@PreDestroy`/`AutoCloseable`, thay vì ép `SmartLifecycle` chạy theo mô hình lazy.

## 6. Phases: thứ tự start thuận và stop ngược

Với các bean `SmartLifecycle` độc lập:

| Bean | `getPhase()` | Thứ tự start | Thứ tự stop |
| --- | ---: | ---: | ---: |
| StorageConnection | -100 | 1 | 3 |
| MessageDispatcher | 0 | 2 | 2 |
| RequestReceiver | 100 | 3 | 1 |

Diễn giải:

```text
START:
StorageConnection(-100)
        ↓
MessageDispatcher(0)
        ↓
RequestReceiver(100)

STOP:
RequestReceiver(100)
        ↓
MessageDispatcher(0)
        ↓
StorageConnection(-100)
```

Tại sao stop ngược? Vì receiver phải **ngừng nhận thêm dữ liệu** trước khi dispatcher dừng; dispatcher cần hoàn tất những việc đang xử lý trước khi storage đóng.

Spring Framework quy định khởi động từ phase thấp tới cao và shutdown theo thứ tự ngược lại. Nếu hai lifecycle components có **cùng phase**, không nên phụ thuộc vào thứ tự nội bộ của chúng để thực thi dependency quan trọng.

### 6.1. Quan hệ phụ thuộc tường minh ưu tiên hơn phase

Nếu bean B **phụ thuộc** bean A và container biết quan hệ đó, Spring yêu cầu B start sau A và stop trước A, ngay cả khi con số phase gợi ý ngược. Quan hệ dependency hợp lệ có thể thể hiện qua injection hoặc bean-definition depends-on metadata theo quy tắc của Spring.

Vì vậy:

- Dùng dependency đúng để mô tả sự phụ thuộc **tài nguyên/đối tượng**.
- Dùng `phase` để tổ chức **các tầng start/stop**.
- Đừng tạo vòng dependency để “giữ thứ tự”.
- Đừng suy luận đặt `@Order` trên một class bất kỳ là tương đương `SmartLifecycle.getPhase()`.

### 6.2. Default phase

Trong Spring Framework 6.1:

- `SmartLifecycle.DEFAULT_PHASE` là `Integer.MAX_VALUE`.
- `SmartLifecycle.getPhase()` mặc định trả giá trị đó.
- `Lifecycle` thông thường không triển khai `SmartLifecycle` được coi như phase **0** cho việc điều phối cơ bản.
- Bean `SmartLifecycle` dùng phase mặc định thường **start muộn** và **stop sớm** so với lifecycle bean phase 0.

Đây là một khác biệt có chủ ý của API. Nếu muốn receiver start trước một component phase 0, **phải chọn phase thích hợp** hoặc thể hiện dependency đúng; không dựa vào việc bean được tạo trước.

## 7. Quy trình refresh: khi nào SmartLifecycle.start() được gọi?

Trong một `ApplicationContext` chuẩn, quá trình `refresh()` thực hiện nhiều bước, trong đó có:

1. Chuẩn bị environment và bean factory.
2. Nạp/hoàn thiện bean definitions và hạ tầng post-processing.
3. Khởi tạo các singleton non-lazy phù hợp.
4. Chuẩn bị và sử dụng `LifecycleProcessor`.
5. Gọi `LifecycleProcessor.onRefresh()` để xử lý các lifecycle bean cần auto-start.
6. Hoàn tất refresh và phát `ContextRefreshedEvent`.

Lưu ý: sơ đồ này được rút gọn; thứ tự chi tiết của refresh trong từng implementation có thêm nhiều hook.

Khi dùng Spring Boot:

```text
SpringApplication.run(...)
    |
    +-- ApplicationContext.refresh()
    |      |
    |      +-- SmartLifecycle auto-start
    |      +-- ContextRefreshedEvent
    |
    +-- ApplicationStartedEvent
    |
    +-- ApplicationRunner / CommandLineRunner
    |
    +-- ApplicationReadyEvent
    |
    +-- return ApplicationContext
```

**Do đó `SmartLifecycle.start()` thường chạy trước các runners và trước `ApplicationReadyEvent`.** Nếu một SmartLifecycle receiver tự mở mạng hoặc bắt đầu nhận message trong `start()`, hoạt động đó có thể bắt đầu **trước lúc ứng dụng được Boot báo ready**.

Nếu nghiệp vụ phải đợi runner xây dữ liệu quan trọng, nên tổ chức lại thứ tự khởi tạo hoặc cơ chế gate nhận traffic/message; đừng giả định `ApplicationReadyEvent` luôn đi trước việc `SmartLifecycle` auto-start.

## 8. Ví dụ runnable Spring Boot 3.3, Java 17+: SmartLifecycle vẫn chạy dù lazy

Ví dụ này cố tình tạo **hai bean khác nhau**:

- `ManagedQueue` implements `SmartLifecycle`, có `@Lazy` trên class; nó mặc định auto-start.
- `OptionalCache` chỉ là bean `@Lazy` thông thường, không tham gia lifecycle. Không có consumer nào yêu cầu nó.

Bật `spring.main.lazy-initialization=true` rồi quan sát sau khi `SpringApplication.run(...)` hoàn thành.

### 8.1. Cấu trúc project

```text
smart-lifecycle-lazy-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/
        demo/
          lifecycle/
            LifecycleLazyApplication.java
    resources/
      application.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'smart-lifecycle-lazy-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

Dự án cần một Gradle wrapper tương thích và JDK 17+. Phiên bản Spring Boot 3.3.13 dùng để minh họa nhánh 3.3, không phải khuyến nghị chọn một bản đã hết vòng đời hỗ trợ cho dự án mới.

`src/main/resources/application.properties`:

```properties
spring.application.name=smart-lifecycle-lazy-demo
spring.main.web-application-type=none
spring.main.lazy-initialization=true
spring.main.banner-mode=off
logging.level.root=ERROR
```

Chọn non-web để ví dụ không cần HTTP server hay request, tránh nhiễu khi quan sát.

### 8.2. Mã Java hoàn chỉnh

File `src/main/java/demo/lifecycle/LifecycleLazyApplication.java`:

```java
package demo.lifecycle;

import jakarta.annotation.PreDestroy;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class LifecycleLazyApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                SpringApplication.run(LifecycleLazyApplication.class, args)) {

            var factory = context.getBeanFactory();

            System.out.println("main.managedCreated="
                    + factory.containsSingleton("managedQueue"));
            System.out.println("main.cacheCreated="
                    + factory.containsSingleton("optionalCache"));
            System.out.println("main.managedRunning="
                    + context.getBean(ManagedQueue.class).isRunning());
        }

        System.out.println("main.contextClosed");
    }
}

@Component
@Lazy
class ManagedQueue implements SmartLifecycle {

    private volatile boolean running;

    ManagedQueue() {
        System.out.println("managed.constructed");
    }

    @Override
    public void start() {
        if (!running) {
            running = true;
            System.out.println("managed.start");
        }
    }

    @Override
    public void stop() {
        if (running) {
            running = false;
            System.out.println("managed.stop");
        }
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop();
        } finally {
            callback.run();
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }

    @Override
    public int getPhase() {
        return 100;
    }

    @Override
    public boolean isAutoStartup() {
        return true;
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("managed.destroy");
    }
}

@Component
@Lazy
class OptionalCache {

    OptionalCache() {
        System.out.println("cache.constructed");
    }

    @PreDestroy
    public void cleanup() {
        System.out.println("cache.destroy");
    }
}
```

Tất cả class top-level nằm trong một file; chỉ `LifecycleLazyApplication` là `public`. Hai component có tên bean mặc định lần lượt là `managedQueue` và `optionalCache`. Import `@PreDestroy` theo `jakarta.annotation.PreDestroy`, phù hợp Spring Boot 3.x.

### 8.3. Chạy chương trình

Với dự án có Gradle wrapper:

```bash
./gradlew bootRun
```

Các dòng **do chính code ví dụ in ra** trong một lượt khởi động và đóng context bình thường, với cấu hình và tập bean như trên:

```text
managed.constructed
managed.start
main.managedCreated=true
main.cacheCreated=false
main.managedRunning=true
managed.stop
managed.destroy
main.contextClosed
```

Spring Boot và Gradle có thể in thêm thông báo khác. Những dòng trên là các marker quan trọng; không nên khẳng định toàn bộ stdout chỉ có tám dòng này.

Phân tích:

1. Bean `ManagedQueue` có `@Lazy` và global lazy cũng bật, nhưng bộ quản lý lifecycle vẫn cần nó để auto-start, nên constructor chạy trong startup.
2. `ManagedQueue.start()` chuyển `running` sang `true` trước khi `run(...)` trả về.
3. `main.managedCreated=true` phản ánh singleton instance đã được tạo.
4. Bean `OptionalCache` không implement lifecycle và không được ai yêu cầu, nên vẫn chưa có instance: `main.cacheCreated=false`.
5. `context.getBean(ManagedQueue.class)` trong code quan sát **không phải nguyên nhân làm nó được tạo**; nó đã được tạo trong refresh. Tuy nhiên ở ứng dụng khác, `getBean` có thể làm thay đổi trạng thái một bean lazy — vì thế ví dụ kiểm tra `containsSingleton` **trước khi gọi `getBean`**.
6. Ra khỏi `try-with-resources`, context đóng; bộ xử lý lifecycle gọi `stop(Runnable)`, phương thức này gọi `stop()` rồi `callback.run()`.
7. Sau khi dừng, destruction callback `@PreDestroy` chạy trên singleton `ManagedQueue`.
8. `OptionalCache` chưa từng được tạo, nên không có instance để gọi `@PreDestroy` của cache.

**Kết luận của thí nghiệm:** lazy initialization và lifecycle auto-start là hai hợp đồng khác nhau. `@Lazy` không phải công tắc “đừng start background receiver lúc startup”.

### 8.4. Nếu cấu hình global lazy=false?

Đổi:

```properties
spring.main.lazy-initialization=false
```

trong một **lần khởi động mới**. `OptionalCache` vẫn mang `@Lazy` trên chính bean definition, nên nếu không có consumer, nó vẫn có thể chưa được tạo. `ManagedQueue` vẫn tham gia lifecycle. Sự khác biệt của cờ global chỉ quan sát rõ nếu bạn có thêm **singleton không mang `@Lazy`** và không có consumer yêu cầu.

Vì vậy không nên dùng một demo gồm toàn bean `@Lazy` để kết luận global lazy “không có tác dụng”; mục tiêu của ví dụ này là chứng minh **ngoại lệ thực tế đối với SmartLifecycle**.

## 9. Biến thể: không tự start tại refresh

Sửa một method trong `ManagedQueue`:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

Đây là **một biến thể thay thế** cho method `isAutoStartup()` của class ở mục 8, không phải tạo thêm cùng chữ ký trong file.

Tác dụng: lifecycle processor **không tự gọi `start()`** cho component này trong lần refresh đó.

Điều **không được kết luận**:

- `ManagedQueue` chắc chắn chưa được construct.
- `managedQueue` chắc chắn không nằm trong cache singleton.
- Bean sẽ không thể được `getBean(...)`.
- Bean sẽ tự start ngay lần đầu consumer gọi method bất kỳ.

Một bean ở trạng thái chưa chạy vẫn có thể đã được tạo để framework đánh giá lifecycle, và việc có instance không đồng nghĩa với `isRunning()==true`.

### 9.1. Bắt đầu bằng API tường minh

Nếu muốn start các lifecycle components theo context:

```java
ConfigurableApplicationContext context = // context đã được tạo và refresh
context.start();
```

Đây là **snippet khái niệm**, không thể biên dịch nguyên văn với dấu chú thích `//` thay cho biểu thức gán. Trong chương trình thực, `context` phải là biến đã nhận từ `SpringApplication.run(...)` hoặc một context hợp lệ. `context.start()` gửi tín hiệu start tới các lifecycle bean theo quy tắc của context, không nhất thiết chỉ có một bean được chọn.

Nếu chỉ muốn start một component duy nhất, gọi qua API chuyên dụng của service đó hoặc:

```java
ManagedQueue queue = context.getBean(ManagedQueue.class);
queue.start();
```

Đoạn này đòi hỏi biến `context` đã tồn tại. Với trường hợp nhiều bean cần phối hợp phase, ưu tiên để `LifecycleProcessor` làm điều phối thay vì tự gọi một bean không xét các dependency.

### 9.2. Đóng khi bean chưa running

Một `SmartLifecycle` đã được tạo nhưng `isRunning()==false` có thể không đi qua cùng đường `stop(Runnable)` như một bean đang chạy. Tuy nhiên khi **context đóng**, singleton đã được tạo vẫn có thể nhận destructor như `@PreDestroy`, `DisposableBean.destroy()` hoặc custom destroy method.

Hãy tách hai câu hỏi:

- **Có đang chạy để cần stop?** → `isRunning()` và lifecycle stop processing.
- **Có instance sở hữu tài nguyên cần hủy?** → bean destruction và ownership.

Không đặt toàn bộ việc đóng file/pool ở `stop(Runnable)` rồi bỏ qua destructor, nếu bean có thể được tạo nhưng chưa từng start.

## 10. stop(Runnable callback): hợp đồng hoàn tất shutdown

Khi context đóng, `DefaultLifecycleProcessor` sử dụng **`SmartLifecycle.stop(Runnable callback)`** để cho phép dừng theo phase, kể cả khi thành phần cần thời gian để hoàn tất tác vụ bất đồng bộ.

Ý nghĩa của callback:

- Spring đang yêu cầu component dừng.
- Component có thể bắt đầu quá trình dừng và **chưa hoàn thành ngay**.
- **Chỉ khi thành phần thực sự hoàn thành shutdown**, nó phải gọi `callback.run()` để báo cho processor có thể tiếp tục quản lý phase.
- Nếu không gọi callback, processor phải chờ đến giới hạn timeout; việc đóng có thể kéo dài hoặc các dependency bị dừng trong tình trạng công việc chưa xong.

Javadoc Spring Framework quy định callback **phải được gọi khi quá trình dừng hoàn thành** để tránh chậm trễ không cần thiết trong việc đóng context.

### 10.1. Trường hợp dừng đồng bộ

Nếu việc stop hoàn tất ngay trên thread gọi, cách triển khai đơn giản:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop(); // thực sự hoàn tất việc dừng
    } finally {
        callback.run();
    }
}
```

Đây là method đặt **trong một class implements `SmartLifecycle`** có `stop()` phù hợp. `finally` giúp callback được gọi ngay cả khi cleanup đồng bộ gặp lỗi; nhưng trong production vẫn cần log và xử lý lỗi để tránh che nguyên nhân gốc hoặc báo “đã dừng thành công” khi trạng thái thực tế chưa sạch.

Điểm quan trọng: **`stop()` trong ví dụ phải thực sự hoàn thành stop đồng bộ**. Nếu nó chỉ phát tín hiệu rồi trả về, gọi callback ngay sẽ báo sai rằng công việc đã kết thúc.

### 10.2. Trường hợp dừng bất đồng bộ

Giả sử receiver có executor riêng và cần đợi các công việc đang xử lý. Một thiết kế đúng về nguyên tắc:

```text
stop(callback) được gọi
    |
    +-- ngừng nhận task mới
    +-- yêu cầu công việc đang chạy hoàn tất
    +-- trả về cho lifecycle processor (nếu async)
                |
                v
       Công việc cũ hoàn tất
                |
                +-- cập nhật isRunning=false
                +-- đóng/bàn giao tài nguyên theo thiết kế
                +-- callback.run()
                |
                v
       Processor có thể kết thúc phase
```

**Không gọi callback chỉ vì đã gửi yêu cầu dừng.** Callback mang ý nghĩa **đã hoàn tất**.

Ví dụ minh họa một method:

```java
@Override
public void stop(Runnable callback) {
    accepting.set(false);

    completionStage.whenComplete((unused, error) -> {
        try {
            running.set(false);

            if (error != null) {
                // Ghi lỗi không làm lộ dữ liệu nhạy cảm.
            }
        } finally {
            callback.run();
        }
    });
}
```

Đoạn này là **pseudo-code có tham chiếu đến `accepting`, `running` và `completionStage` cần được định nghĩa** trong implementation thật. Nó cho thấy cách nối callback với **kết quả hoàn tất**, không phải khuôn mẫu đầy đủ để sao chép chạy ngay. Một component production phải xử lý hoàn chỉnh tình huống completion đã kết thúc, lỗi, callback trùng lặp, executor bị từ chối và deadline hủy.

### 10.3. Không nhầm stop(Runnable) với stop()

Spring Framework 6.1 Javadoc ghi rõ `LifecycleProcessor` chỉ gọi biến thể **`stop(Runnable)`** đối với `SmartLifecycle`. Vì thế:

- Nếu chỉ override `stop()`, default `stop(Runnable)` của interface sẽ delegate tới `stop()` rồi gọi callback.
- Nếu tự override `stop(Runnable)`, hãy **tự đảm bảo callback được gọi** đúng thời điểm.
- Không kỳ vọng processor tự gọi thêm `stop()` sau khi `stop(Runnable)` hoàn tất, trừ khi implementation của bạn chủ động gọi.

Sai lầm thường gặp là viết:

```java
@Override
public void stop(Runnable callback) {
    // Đã gửi tín hiệu, nhưng chưa hoàn tất.
    requestStop();
    // Quên callback.run() khi thật sự hoàn thành.
}
```

Đây là snippet **phản ví dụ**; method `requestStop()` là giả định. Thiếu callback có thể làm processor đợi đến timeout.

## 11. Phase ảnh hưởng đến giới hạn chờ như thế nào?

Trong Spring Boot 3.3, có thể cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là timeout cho **mỗi phase shutdown**, không phải thời lượng tối đa của toàn bộ tiến trình theo mọi cấu hình. Khi có nhiều phase hoặc các hoạt động khác, tổng thời gian đóng có thể lớn hơn một timeout phase.

Giải thích theo mô hình đơn giản:

```text
Phase 100:
  ReceiverA.stop(callback)  ─┐
  ReceiverB.stop(callback)  ─┤ đợi callbacks / timeout của phase
                             ┘
Phase 0:
  Dispatcher.stop(callback) ── đợi callback / timeout của phase

Phase -100:
  Storage.stop(callback)    ── đợi callback / timeout của phase
```

Nếu hai bean cùng phase và một bean dừng bất đồng bộ, chúng có thể được yêu cầu dừng trong cùng giai đoạn. **Đừng giả định chúng có thứ tự nội bộ xác định** khi không có dependency rõ.

**Cực kỳ quan trọng:** timeout không phải cơ chế cưỡng bức làm tài nguyên dừng sạch. Khi hết thời gian chờ, lifecycle processor có thể tiếp tục tiến trình đóng, dẫn tới nguy cơ component chưa dừng xong thì dependency bị hủy. Vì vậy:

- Thời gian stop phải có giới hạn ở cấp component, không chỉ dựa vào timeout của framework.
- Callback phải phát đúng một lần khi hoàn tất.
- Cần policy xử lý các tác vụ đang xử lý dở: chờ, từ chối, retry, checkpoint hoặc cho phép bỏ theo yêu cầu nghiệp vụ.
- Với công việc dài, cần kết hợp readiness, dừng nhận task và signal shutdown đủ sớm.

Không chọn timeout quá nhỏ chỉ để ứng dụng “tắt nhanh” nếu nó đang mang nhiệm vụ phải hoàn tất; cũng không chọn timeout quá lớn mà không xét deadline của orchestrator.

## 12. Thứ tự khi ApplicationContext.close()

Một context Spring chuẩn thực hiện các giai đoạn lớn:

```text
ApplicationContext.close()
      |
      +-- ContextClosedEvent
      |
      +-- LifecycleProcessor.onClose()
      |      +-- xét trạng thái running
      |      +-- sắp xếp dừng theo phase đảo chiều
      |      +-- chờ callback hoàn tất hoặc timeout
      |
      +-- destroySingletons()
      |      +-- @PreDestroy trên bean đã tạo
      |      +-- DisposableBean.destroy()
      |      +-- destroy-method
      |
      +-- đóng bean factory và tài nguyên context khác
```

Đây là sơ đồ khái quát; các subclass có thể có hook thêm hoặc thứ tự dừng hạ tầng chuyên biệt.

### 12.1. Tại sao @PreDestroy thường chạy sau stop?

`SmartLifecycle.stop(Runnable)` phục vụ **ngừng hoạt động**: không nhận message/task mới, chờ worker đang chạy hoàn tất, cập nhật trạng thái.

`@PreDestroy` phục vụ **giải phóng tài nguyên instance**: đóng executor, buffer, client, connection hoặc file handle mà bean sở hữu.

Tách nhiệm vụ này giúp bảo đảm tài nguyên chưa bị đóng trong lúc component vẫn đang xử lý.

Ví dụ:

```text
SmartLifecycle.stop(callback)
    -> accepting=false
    -> drain/finish in-flight work
    -> callback.run()

@PreDestroy
    -> executor.shutdown()
    -> close client / buffers
```

Nếu `@PreDestroy` đóng executor **trước khi** `stop` hoàn thành, nhiệm vụ đang chờ hoàn tất có thể bị mất hoặc gây lỗi khi chạy. Ngược lại, nếu chỉ dọn executor ở `stop` và bean chưa bao giờ started, có thể bỏ sót cleanup.

### 12.2. ContextClosedEvent không phải @PreDestroy

`ContextClosedEvent` thông báo context bắt đầu đóng; nó không có nghĩa tất cả lifecycle bean đã stop. Một `ApplicationListener<ContextClosedEvent>` có thể nhìn thấy một số bean vẫn đang running.

Không nên:

- Gửi thêm công việc mới vào queue chỉ vì event `ContextClosedEvent` đến.
- Giả định mọi repository hoặc client đã đóng.
- Dùng `ContextClosedEvent` thay cho stop callback khi cần bảo đảm thứ tự phase.

### 12.3. Context.stop() không đồng nghĩa context.close()

`context.stop()` điều phối dừng các lifecycle components nhưng **không hủy toàn bộ singleton** như `context.close()`.

Tương tự:

- `context.start()` có thể tiếp tục start các lifecycle components.
- `context.close()` làm context chuyển sang trạng thái đóng và hủy các singleton phù hợp.
- Không nên dựa vào `context.start()` sau khi context đã đóng; thông thường cần tạo context mới.

Nếu muốn tạm dừng rồi tiếp tục một hệ thống, phải thiết kế lifecycle bean cho việc start/stop lặp lại và xử lý state nhất quán. Nếu muốn ứng dụng thật sự shutdown, hãy đóng context bằng đường phù hợp.

## 13. Tương tác với @PreDestroy, DisposableBean và destroyMethod

Một bean `SmartLifecycle` cũng có thể khai báo các destructor thông thường:

```java
@Component
class ConsumerLifecycle implements SmartLifecycle, DisposableBean {

    // Các method SmartLifecycle cần được cài đặt đầy đủ.

    @PreDestroy
    public void beforeDestroy() {
        System.out.println("destruction.preDestroy");
    }

    @Override
    public void destroy() {
        System.out.println("destruction.disposableBean");
    }
}
```

Đây là **snippet minh họa chưa biên dịch độc lập**, vì `SmartLifecycle.start`/`stop`/`isRunning` chưa được khai báo, và cần các import `Component`, `DisposableBean` và `PreDestroy`. Nó dùng để làm rõ một bean có thể tham gia cả **lifecycle stop** và **bean destruction**.

Khi context đóng đúng và bean có các callback phù hợp:

1. Lifecycle processor yêu cầu stop bean đang running.
2. Spring xử lý hủy singleton theo vòng đời BeanFactory.
3. `@PreDestroy` được xử lý bởi destruction-aware bean post-processor.
4. `DisposableBean.destroy()` được gọi nếu bean implement interface.
5. Custom destroy method, nếu được đăng ký và không trùng method đã xử lý, thường được gọi sau hai cơ chế trên.

**Trật tự `@PreDestroy → DisposableBean.destroy → custom destroy method` là thứ tự trong cùng một bean được hủy**, không phải mệnh đề rằng mọi bean trong context bị hủy theo thứ tự class hoặc tên bean.

### 13.1. Không double-close cùng một tài nguyên

Nếu `stop(Runnable)` và `@PreDestroy` đều gọi `executor.shutdownNow()` hoặc đóng cùng connection, ứng dụng có thể thực hiện cleanup trùng, gây lỗi hoặc mất công việc chưa hoàn tất.

Một thiết kế tốt:

- `stop`: ngừng nhận việc và phối hợp drain.
- Destructor: đóng/cancel các tài nguyên còn lại, không khởi động công việc mới.
- Phương thức dọn dẹp **idempotent** nếu có khả năng được gọi lại từ nhiều đường shutdown.
- Không thiết kế một callback phải gọi business method của dependency đã bị stop/hủy.

## 14. Lazy singleton bình thường và SmartLifecycle khác nhau khi đóng

Giả sử có hai bean:

```text
LazyCache (@Lazy)
SmartReceiver (@Lazy, implements SmartLifecycle)
```

Khi context refresh:

- `LazyCache` có thể **chưa được tạo** vì chưa có consumer yêu cầu.
- `SmartReceiver` thường **được khởi tạo** để lifecycle processor biết và xử lý auto-start.

Khi context đóng:

- Nếu `LazyCache` **chưa từng được tạo**, không có instance để gọi destructor. `@PreDestroy` trên class không được gọi cho một instance không tồn tại.
- Nếu `LazyCache` đã được tạo như singleton, container có thể gọi destructor phù hợp khi close.
- Nếu `SmartReceiver` đã running, lifecycle processor yêu cầu stop trước bước bean destruction.
- Nếu `SmartReceiver` đã được tạo nhưng không running, nó vẫn có thể có destructor cần thực thi; đừng chỉ dựa vào `stop()`.

**Đây là một lý do quan trọng để không coi lazy như “không có vòng đời”.** Một bean lazy vẫn có vòng đời Spring sau khi được tạo. Một bean `SmartLifecycle` vẫn có thể được dựng dù lazy, rồi tham gia cả start/stop và destroy.

## 15. Global lazy và các bean cần hoạt động lúc startup

Khi bật:

```yaml
spring:
  main:
    lazy-initialization: true
```

hãy đánh giá những thành phần:

- Listener nhận message từ broker.
- Scheduler/worker thread.
- Polling consumer.
- Web server lifecycle.
- Health/availability infrastructure.
- Bean dùng `@PostConstruct` để khởi động nền.
- `SmartLifecycle` wrapper cho client/queue.

Chúng không có cùng hành vi. Một service `@Lazy` thông thường chứa method nghiệp vụ có thể bị hoãn; một `SmartLifecycle` auto-start thường vẫn được đưa vào startup, trong khi một scheduled job có thể chịu tác động của việc các bean hạ tầng khác cần được khởi tạo.

**Không khẳng định global lazy vô hiệu hoàn toàn** vì quan sát một `SmartLifecycle` chạy sớm. Cờ vẫn có thể hoãn rất nhiều singleton khác.

### 15.1. @Lazy(false) có phải biện pháp chuẩn cho SmartLifecycle?

`@Lazy(false)` là cách chỉ định bean definition eager trong những tình huống cần được khởi tạo sớm khi global lazy bật. Nhưng vì `SmartLifecycle` vốn thường được tạo để auto-start, `@Lazy(false)` **không giải quyết câu hỏi “có tự start hay không”**.

Nếu mục tiêu là:

- **Phải auto-start:** `SmartLifecycle` phù hợp, `isAutoStartup()==true`; chọn phase.
- **Không auto-start:** `isAutoStartup()==false`; định nghĩa ai sẽ gọi start.
- **Không cần instance đến khi nghiệp vụ yêu cầu:** cân nhắc một bean thường với `@Lazy`/`ObjectProvider` thay vì buộc nó implement `SmartLifecycle`.
- **Bắt buộc fail-fast một dependency:** dùng chính sách eager hoặc kiểm tra trong startup/readiness phù hợp, không chỉ dựa vào proxy.

Đừng để một bean vừa có trách nhiệm lắng nghe lifecycle toàn ứng dụng vừa có yêu cầu tuyệt đối “không được tạo tới lần dùng đầu tiên” mà không xem xét xung đột thiết kế.

## 16. Mối liên hệ với ApplicationRunner và ApplicationReadyEvent

Cần phân biệt các mốc Spring Boot:

| Mốc | Đặc điểm |
| --- | --- |
| `@PostConstruct` | Chạy khi một bean instance đang được khởi tạo |
| `SmartLifecycle.start()` | Thường được gọi trong `refresh()` đối với auto-start bean |
| `ContextRefreshedEvent` | Phát khi refresh thành công |
| `ApplicationStartedEvent` | Boot phát sau refresh, trước runners |
| `ApplicationRunner` / `CommandLineRunner` | Chạy sau refresh, trước ready |
| `ApplicationReadyEvent` | Phát sau runners hoàn tất thành công |
| `ContextClosedEvent` | Phát ở đầu luồng đóng context |
| `SmartLifecycle.stop(Runnable)` | Dừng có thứ tự trong lifecycle shutdown |
| `@PreDestroy` | Hủy bean instance phù hợp sau phần stop |

Nếu receiver `SmartLifecycle` start trong refresh, nó **có thể nhận message trước khi `ApplicationRunner` chuẩn bị xong dữ liệu**. Đừng dựa vào logic sau runner để khởi tạo điều kiện mà receiver cần ngay khi start.

Một số giải pháp:

1. Đưa phần state tối thiểu vào dependency khởi tạo trước receiver.
2. Thiết kế receiver với một **gate**: start lifecycle nhưng chưa xử lý message cho tới khi điều kiện readiness thật sự đáp ứng.
3. Chọn `isAutoStartup=false` rồi có một orchestrator **chủ động start** sau khi chuẩn bị xong.
4. Dùng phase và dependency để đảm bảo thứ tự giữa các lifecycle components, nhưng đừng tưởng `phase` điều khiển thứ tự `ApplicationRunner`.

**`ApplicationReadyEvent` không tự động start lại những `SmartLifecycle` có `isAutoStartup=false`.** Nếu muốn start tại mốc đó, phải viết code thực hiện việc start rõ ràng, kiểm soát idempotence và lỗi.

## 17. SmartLifecycle và graceful shutdown web server của Spring Boot

Trong **Spring Boot 3.3**, khi chạy web app với server hỗ trợ, có thể bật graceful shutdown:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Spring Boot 3.3 hỗ trợ graceful shutdown trên các embedded web server được tài liệu liệt kê, và thực hiện nó như một phần của việc **đóng ApplicationContext** thông qua cơ chế `SmartLifecycle`/lifecycle phases.

Ý nghĩa:

- Khi context được đóng bằng đường thích hợp, web server tiến hành ngừng hoặc hạn chế tiếp nhận request mới theo cơ chế đặc thù của server.
- Các request đang xử lý có **khoảng thời gian** để hoàn tất trong giới hạn cấu hình.
- Hoạt động stop này tham gia vào các phase lifecycle, phối hợp với các thành phần khác.
- Một số server từ chối kết nối mới ở tầng mạng; server khác có thể trả mã HTTP tùy implementation.
- Không được mặc định graceful shutdown làm mọi background job hoặc message consumer của bạn tự drain an toàn. Những component đó cần lifecycle protocol riêng.

**Không áp dụng máy móc cho phiên bản khác:** các default của graceful shutdown có thể thay đổi ở các thế hệ Spring Boot. Bài này dùng ví dụ cấu hình rõ ràng để tránh phụ thuộc vào default không nêu.

### 17.1. Timeout phase khác timeout của orchestrator

`spring.lifecycle.timeout-per-shutdown-phase` quy định thời gian chờ cho mỗi phase từ góc nhìn Spring lifecycle processor. Container orchestration như Kubernetes có **deadline riêng**. Nếu orchestrator giết process trước khi Spring hoàn thành, callbacks còn lại có thể không chạy đủ.

Vì vậy hãy thiết kế sao cho:

- Tổng thời gian stop các phase + destroy + overhead nằm trong thời gian được cấp.
- Grace period của orchestrator đủ lớn cho công việc phải hoàn tất.
- Mỗi component có timeout nội bộ/logic fallback.
- Readiness được cập nhật thích hợp để giảm lượng công việc mới trong lúc dừng.
- Không log bí mật hoặc dữ liệu nhạy cảm từ các task đang hủy.

### 17.2. Vì sao server có thể start trước ready?

Web server có thể được tạo/start trong quá trình refresh, cũng là giai đoạn xử lý `SmartLifecycle`. Điều này có thể xảy ra **trước `ApplicationReadyEvent`**. Việc server lắng nghe port không tương đương ứng dụng đạt readiness ở cấp deployment.

Với consumer chủ động nhận message, rủi ro tương tự: `SmartLifecycle.start()` có thể kích hoạt hoạt động trước runner. Nếu các bước startup là bắt buộc cho tính đúng đắn, hãy có explicit gate hoặc orchestrator, không chỉ trông vào log “Started application”.

## 18. Tự đóng context, JVM shutdown hook và SIGTERM

Một context có thể được đóng bằng:

```java
try (ConfigurableApplicationContext context =
        SpringApplication.run(DemoApplication.class, args)) {
    // Ứng dụng CLI ngắn hạn.
}
```

Đây là code minh họa với `DemoApplication` phải tồn tại và import phù hợp. `try-with-resources` hợp lý cho CLI/batch dùng ngắn hạn; **không** sao chép việc đóng ngay context vào web server cần chạy lâu dài.

Với service, Spring Boot thường đăng ký shutdown hook theo cấu hình để đóng context khi JVM shutdown bình thường. Nhưng:

- `SIGTERM` thường cho JVM cơ hội chạy shutdown hooks theo cách môi trường triển khai hỗ trợ.
- `SIGKILL`/`kill -9` không cho JVM thực thi shutdown hook bình thường.
- Sự cố điện, kernel crash hoặc kill cưỡng bức có thể khiến `stop` và destructor không được gọi.
- IDE stop button đôi khi dùng cơ chế dừng khác; không nên coi nó giống `SIGTERM`.

Vì vậy cả `SmartLifecycle` và `@PreDestroy` **không phải cam kết cleanup trong mọi loại sự cố**. Các hệ thống ghi dữ liệu/broker cần thiết kế idempotency, retry, checkpoint và recovery khi restart.

## 19. Khi context refresh thất bại

Nếu một bean hoặc lifecycle component gây lỗi trong quá trình khởi động:

- `SpringApplication.run` có thể thất bại trước khi `ApplicationReadyEvent` được phát.
- Những bean đã được tạo có thể được container dọn dẹp theo đường thất bại phù hợp.
- Không phải mọi bean đã được tạo, nên không phải mọi `@PreDestroy` đều có instance để gọi.
- Nếu `start()` đã thực hiện một phần side effect rồi ném exception, cần hiểu cách ứng dụng thực hiện rollback/dọn dẹp, không chỉ dựa vào `stop()` chắc chắn sẽ được gọi.
- `ApplicationFailedEvent` có thể được phát theo cơ chế Spring Boot, nhưng callback của bean có thể chưa được đăng ký nếu lỗi xảy ra rất sớm.

Một `SmartLifecycle.start()` nên:

1. Kiểm tra dependency thật sự cần thiết.
2. Chỉ đặt `running=true` khi trạng thái hoạt động phù hợp hoặc bảo đảm rollback khi xảy ra lỗi.
3. Nếu tạo resource trước khi exception, tự dọn phần đã tạo theo `try/catch/finally` thích hợp.
4. Không nuốt lỗi khiến ứng dụng báo ready trong khi một thành phần bắt buộc không hoạt động.
5. Tránh blocking không giới hạn trong start.

Global lazy không giải quyết được lỗi start trong những `SmartLifecycle` vẫn được khởi tạo lúc refresh.

## 20. Tự xây một SmartLifecycle production-ready: các nguyên tắc

Một implementation tốt không chỉ implement cho đủ method. Cần có hợp đồng vận hành rõ ràng.

### 20.1. start phải idempotent

```java
@Override
public void start() {
    if (!running.compareAndSet(false, true)) {
        return;
    }
    // Bắt đầu nhận công việc, có xử lý rollback nếu lỗi.
}
```

Đây là **snippet** giả định `running` là `AtomicBoolean` đã khai báo. Trong thực tế, nếu khởi động resource có thể thất bại sau khi CAS thành công, phải khôi phục trạng thái và giải phóng resource trong nhánh lỗi. CAS không tự làm việc khởi tạo bên ngoài trở thành atomic.

### 20.2. isRunning phải phản ánh trạng thái thực

```java
@Override
public boolean isRunning() {
    return running.get();
}
```

Đây là snippet tiếp nối `AtomicBoolean`. Không nên trả true ngay khi đã *gửi yêu cầu start* nhưng receiver chưa thực sự nhận công việc. Nếu hệ thống có trạng thái `STARTING` / `RUNNING` / `STOPPING` / `STOPPED`, nên tổ chức state machine phù hợp thay vì một boolean quá đơn giản.

### 20.3. stop phải phối hợp với callback

```java
@Override
public void stop(Runnable callback) {
    try {
        stopAcceptingNewWork();
        awaitInFlightWorkWithinDeadline();
        releaseActiveHandles();
        running.set(false);
    } finally {
        callback.run();
    }
}
```

Đây là **pseudo-code**: các method `stopAcceptingNewWork`, `awaitInFlightWorkWithinDeadline`, `releaseActiveHandles` chưa được định nghĩa, nên không phải source chạy độc lập. Nó minh họa một stop đồng bộ có kiểm soát. Nếu phần dừng bất đồng bộ thực sự, callback phải được gọi từ tín hiệu **hoàn tất thực tế**, không từ thread gửi yêu cầu.

### 20.4. Destruction phải xử lý cả trường hợp chưa start

```java
@PreDestroy
public void destroyResources() {
    closeResourcesIfPresent();
}
```

Đây là snippet, cần implement `closeResourcesIfPresent` và import `jakarta.annotation.PreDestroy`. Mục đích là dọn được resource **đã tạo ở constructor/init** ngay cả khi `start` chưa được gọi. Destructor cần kiểm tra null/state và có tính gọi lại an toàn.

### 20.5. Không ném exception làm mất callback

Nếu stop có thể ném exception hoặc task async thất bại, cần quy định cách báo lỗi và **vẫn bảo đảm protocol callback**, trong phạm vi có thể. Tuy nhiên gọi callback không có nghĩa thông báo “dừng sạch” nếu còn tài nguyên sống. Phải log/metric trạng thái lỗi riêng và có chính sách fallback.

## 21. Tình huống thực tế: message consumer và database client

Giả sử một ứng dụng có:

- `DatabasePool`: quản lý kết nối database, cần sẵn sàng trước consumer.
- `MessageConsumer`: nhận thông điệp từ broker, gọi database.
- `OptionalAuditClient`: chỉ dùng ở một số nhánh nghiệp vụ, có thể lazy.

Thiết kế hợp lý:

```text
START:
DatabasePool (sẵn sàng)
    |
    v
MessageConsumer.start()
    |
    v
Nhận message

OptionalAuditClient (@Lazy) có thể chưa được tạo.

STOP:
MessageConsumer.stop(callback)
    |
    +-- Ngừng nhận message mới
    +-- Đợi message đang xử lý / checkpoint
    +-- callback.run()
    |
    v
DatabasePool đóng theo lifecycle và bean destruction
```

Nếu `MessageConsumer` implements `SmartLifecycle` để auto-start, việc thêm `@Lazy` **không bảo đảm nó được hoãn**. Nếu muốn chỉ chạy sau khi một bước import trong runner hoàn tất, cần chủ động tắt auto-start và có orchestrator start sau điều kiện đó, hoặc thiết kế startup gate.

Nếu `OptionalAuditClient` chỉ là service/SDK và thật sự hiếm dùng, **đừng bắt nó implement `SmartLifecycle` chỉ để có callback đóng**. Có thể để bean singleton `@Lazy` với `@PreDestroy` hoặc factory `destroyMethod` phù hợp; điều đó tránh áp đặt auto-start.

## 22. Test: xác nhận thứ tự start/stop và lazy

### 22.1. Test chính sách lazy qua hai loại bean

Sử dụng demo mục 8:

1. Bật `spring.main.lazy-initialization=true`.
2. Khởi chạy một SpringApplication mới.
3. Quan sát `managed.constructed` / `managed.start` xảy ra trong startup.
4. Kiểm tra `containsSingleton("managedQueue") == true`.
5. Kiểm tra `containsSingleton("optionalCache") == false` trước khi gọi `getBean(OptionalCache.class)`.
6. Đóng context và quan sát `managed.stop` rồi `managed.destroy`.
7. Xác nhận không có `cache.destroy` nếu cache chưa từng được tạo.

Bài test này phân biệt **instance creation**, **auto-start** và **destruction**, không chỉ so sánh thời gian startup.

### 22.2. Test isAutoStartup=false

Thay `isAutoStartup()` của `ManagedQueue` bằng `false`. Khởi chạy context mới, quan sát `managed.start` không được gọi tự động. **Đừng assert constructor chắc chắn không chạy**: tác dụng chính của thay đổi là chính sách start.

Sau đó gọi `context.start()` hoặc một API điều phối start thích hợp. Kiểm tra `isRunning()` thay đổi khi component thực sự được start và stop, rồi đóng context.

### 22.3. Test phase

Tạo hai bean `SmartLifecycle` với phase -100 và 100, mỗi bean ghi marker vào một `List<String>` được kiểm soát bởi test. Kỳ vọng:

```text
phase-100.start
phase100.start
phase100.stop
phase-100.stop
```

Đây là kỳ vọng **khi hai bean độc lập, đều auto-start và chạy/stop đồng bộ đúng hợp đồng**. Nếu có dependency tường minh giữa chúng hoặc phase khác, thứ tự cần được dự đoán lại.

### 22.4. Test callback stop bất đồng bộ

Đừng chỉ assert rằng `stop(Runnable)` đã được gọi. Hãy tạo một stop giả lập dùng `CountDownLatch` hoặc `CompletableFuture` để điều khiển việc hoàn tất:

1. Bắt đầu đóng context trong luồng kiểm thử độc lập có timeout.
2. Xác nhận `stop(Runnable)` được yêu cầu.
3. Giữ callback chưa được gọi, xác nhận processor đang đợi trong phạm vi timeout.
4. Hoàn tất hoạt động dừng rồi gọi callback.
5. Xác nhận context tiến tới destructor và đóng xong.

Tránh test dựa vào `Thread.sleep` ngẫu nhiên hoặc kéo dài quá timeout để tránh test chập chờn. Bảo đảm test luôn giải phóng latch/resource trong `finally`.

### 22.5. Test chính xác trước khi đo

Một số hành động introspection thay đổi chính thứ cần đo:

- `context.getBean(OptionalCache.class)` có thể **tạo bean lazy**.
- `BeanFactory.containsBean(...)` chỉ cho biết bean definition/bean có thể được tìm, **không khẳng định instance đã được tạo**.
- `ConfigurableListableBeanFactory.containsSingleton(name)` cho biết singleton instance có mặt mà không tự gọi constructor.
- Trong test dùng `@Autowired` vào chính bean lazy, test framework có thể kích hoạt bean sớm hơn kịch bản thực tế.

Muốn quan sát đúng, phải kiểm tra trạng thái **trước khi chủ động yêu cầu target**.

## 23. Bảng so sánh: công cụ nào cho mục đích nào?

| Yêu cầu | Cơ chế hợp lý | Điều phải hiểu |
| --- | --- | --- |
| Không tạo một SDK hiếm dùng cho đến khi cần | `@Lazy` trên bean bình thường / `ObjectProvider` | Consumer eager có thể ép tạo target |
| Hoãn khởi tạo nhiều singleton của Spring Boot | `spring.main.lazy-initialization=true` | Infrastructure và `SmartLifecycle` vẫn có ngoại lệ thực tế |
| Tự start receiver khi refresh | `SmartLifecycle.isAutoStartup()==true` | Bean thường được khởi tạo trong startup |
| Tạo bean nhưng chưa start receiver | `SmartLifecycle.isAutoStartup()==false` | Không cam kết instance vẫn lazy |
| Điều phối nhiều lifecycle components | `getPhase()` và dependency rõ ràng | Start tăng dần phase, stop giảm dần |
| Dừng receiver đang xử lý việc | `stop(Runnable callback)` | Callback phải báo **đã hoàn tất** |
| Giải phóng tài nguyên instance khi destroy | `@PreDestroy` / `DisposableBean` / `destroyMethod` | Không thay thế stop theo phase |
| Ngừng toàn application context | `ConfigurableApplicationContext.close()` | Stop lifecycle rồi destroy singleton |
| Tạm dừng / tiếp tục lifecycle | `context.stop()` / `context.start()` | Không đồng nghĩa đóng context |
| Cho HTTP request hoàn tất khi shutdown | Boot graceful shutdown | Bật đúng cấu hình trên Boot 3.3 và chọn timeout |
| Đảm bảo ứng dụng đã sẵn sàng nghiệp vụ | Readiness checks / startup orchestration | Auto-start và port listening chưa đồng nghĩa ready |

## 24. Những lỗi thường gặp

| Triệu chứng | Căn nguyên | Cách xử lý |
| --- | --- | --- |
| `@Lazy SmartLifecycle` vẫn construct lúc startup | LifecycleProcessor cần tìm/auto-start bean | Đây là hành vi thường gặp; đừng dùng `@Lazy` như chặn auto-start |
| Bật global lazy nhưng worker vẫn chạy | Worker là `SmartLifecycle` hoặc được startup infrastructure yêu cầu | Kiểm tra `isAutoStartup`, dependencies và lifecycle processor |
| `isAutoStartup=false` mà constructor vẫn chạy | Cờ này điều khiển start, không cam kết trì hoãn instance | Kiểm tra bean discovery/dependencies; dùng bean thường nếu cần lazy thật |
| `@Lazy` ở injection point nhưng receiver vẫn started | Lazy proxy chỉ tác động cạnh injection, lifecycle processor vẫn quản lý bean | Điều khiển start bằng `isAutoStartup` hoặc orchestrator |
| `stop()` có code nhưng không chạy như mong đợi | SmartLifecycleProcessor gọi `stop(Runnable)`; custom override không delegate | Implement `stop(Runnable)` đúng và gọi callback |
| Đóng context bị treo đến timeout phase | Quên `callback.run()` hoặc component không bao giờ hoàn tất | Chẩn đoán stop path, bảo đảm callback sau completion |
| `@PreDestroy` chạy khi receiver vẫn còn công việc | Callback stop báo hoàn tất quá sớm hoặc phase timeout | Sửa protocol drain và deadline |
| Client database đóng trước message consumer | Dependency/phase không đúng hoặc timeout khiến stop chưa xong | Khai báo quan hệ và phase rõ ràng, đủ thời gian |
| Phase lớn lại được gọi start sớm | Có quan hệ depends-on hoặc flow riêng | Xem dependency graph; dependency có ưu tiên hơn phase |
| Không có `managed.destroy` khi kill -9 | JVM không chạy hook shutdown | Dùng SIGTERM bình thường, thiết kế recovery khi bị kill |
| Bean lazy không thấy `@PreDestroy` | Chưa có instance để hủy | Kiểm tra scope và đã từng tạo instance chưa |
| Context.stop xong mà bean vẫn tồn tại | stop không phải destroy | Gọi close khi thực sự shutdown |
| Ready đến sau khi consumer đã nhận message | SmartLifecycle start trong refresh trước runner/ready | Dùng gate hoặc tắt auto-start và start sau chuẩn bị |
| Graceful HTTP shutdown chưa hoạt động | Chưa bật `server.shutdown=graceful` trên Boot 3.3 hoặc tín hiệu dừng không phù hợp | Kiểm tra phiên bản, cấu hình và lifecycle stop |
| Shutdown vượt deadline Kubernetes | Nhiều phase chờ, task dừng quá lâu | Đo từng phase, đặt timeout nội bộ và điều chỉnh deadline |
| Start lỗi khiến app ở trạng thái nửa hoạt động | Không rollback resource khi `start()` ném exception | Dọn phần khởi tạo, fail-fast và báo lỗi rõ |
| Dừng hai lần làm ném exception | stop/destructor không idempotent | Quản lý state và chỉ đóng resource khi còn mở |

### Chẩn đoán theo trình tự

1. Xác nhận bean có thực sự implements `SmartLifecycle` hay chỉ `Lifecycle`.
2. Kiểm tra bean definition có `@Lazy`, global lazy và `@Lazy` tại injection point hay không; đây là **ba cơ chế khác nhau**.
3. Xem `isAutoStartup()` trả về gì trong runtime.
4. Kiểm tra `isRunning()`, `start()` và callback stop có phản ánh trạng thái thật không.
5. Xem `getPhase()` của từng component; xác định dependency tường minh.
6. Xác định mốc log: constructor, start, application ready, context close, stop, destructor.
7. Nếu shutdown chậm, xem callback nào chưa gọi và timeout per phase.
8. Nếu component nhận message quá sớm, xác định gate và điều kiện sẵn sàng trước khi start.
9. Nếu resource bị đóng sớm, kiểm tra thứ tự giữa các phase và việc stop có thực sự đợi công việc hoàn tất không.
10. Chạy test có kiểm soát trên context độc lập, tránh dừng context của môi trường production để thử.

## 25. Câu hỏi tự kiểm tra

1. Vì sao bean `@Lazy` thông thường có thể chưa được tạo sau refresh, nhưng bean `@Lazy` implements `SmartLifecycle` thường đã được tạo?
2. `isAutoStartup=false` có nghĩa bean chắc chắn không được construct trong startup không?
3. `SmartLifecycle.start()` được gọi trước hay sau `ApplicationRunner` trong startup bình thường?
4. Nếu bean A phase 0, bean B phase 100 và hai bean độc lập, ai start trước, ai stop trước?
5. Nếu B phụ thuộc trực tiếp A nhưng có số phase thấp hơn A, quan hệ dependency có tác động thế nào tới việc điều phối?
6. Vì sao `stop(Runnable)` phải gọi callback **sau** khi tác vụ dừng hoàn tất, không chỉ sau khi gửi tín hiệu?
7. `@PreDestroy` của một bean đã tạo nhưng chưa running có còn ý nghĩa không?
8. `context.stop()` có hủy singleton và chạy mọi destructor như `context.close()` không?
9. Vì sao bật global lazy không phải chiến lược đáng tin để ngăn một message consumer auto-start?
10. Để dừng request HTTP và background message consumer cùng an toàn trong Boot 3.3, những giới hạn shutdown nào cần cấu hình hoặc đo?
11. Bean lazy chưa từng được tạo có thể nhận `@PreDestroy` không? Vì sao?
12. Có nên cài đặt một SDK hiếm dùng thành `SmartLifecycle` chỉ để được đóng lúc shutdown không?

### Đáp án gợi ý

1. Lifecycle processor cần tìm và quản lý auto-start components; lazy flag trên `SmartLifecycle` có hiệu lực rất hạn chế.
2. Không. Auto-start là **trạng thái hoạt động**, không phải **chính sách tạo instance**.
3. Thường trước runners, trong giai đoạn refresh.
4. A start trước B; B stop trước A.
5. Dependency được container nhận biết có ưu tiên khi xác định start/stop.
6. Nếu báo hoàn tất quá sớm, Spring có thể dừng/hủy dependency trong lúc component còn làm việc.
7. Có, để dọn resource đã tạo dù chưa start.
8. Không. `stop` điều phối lifecycle; `close` bao gồm destruction.
9. Vì `SmartLifecycle` thường được tìm và khởi tạo để start lúc refresh.
10. Shutdown phase timeout, server graceful shutdown, deadline của orchestrator và timeout/drain riêng của consumer.
11. Không có instance thì không có destructor instance để gọi.
12. Thường không cần; dùng bean thường với destructor phù hợp nếu không cần cơ chế auto-start/phase.

## 26. Quy tắc thiết kế cần nhớ

- **SmartLifecycle** dùng để phối hợp start/stop của thành phần có trạng thái hoạt động, đặc biệt những thành phần chạy nền.
- **@Lazy** và **global lazy** nói về tạo bean; đừng dùng chúng để kiểm soát auto-start của `SmartLifecycle`.
- **isAutoStartup=false** chỉ chặn auto-start tại refresh, không chứng minh bean instance chưa được tạo.
- **Phase thấp start trước, phase cao stop trước**; dependency tường minh vẫn phải được thể hiện đúng.
- **stop(Runnable)** phải gọi callback khi thực sự hoàn tất stop. Quên callback khiến việc đóng chờ timeout.
- **@PreDestroy** và các destructor khác dùng để giải phóng tài nguyên bean, thường sau giai đoạn lifecycle stop.
- **close() khác stop()**: đóng context mới thực hiện toàn bộ destruction tương ứng.
- **Global lazy là một lựa chọn hiệu năng có trade-off**: có thể dời lỗi hoặc chi phí khởi tạo sang thời điểm dùng, nhưng không ngăn infrastructure và SmartLifecycle hoạt động.
- **SmartLifecycle.start() có thể chạy trước ApplicationReadyEvent**. Nếu nghiệp vụ cần sẵn sàng trước khi nhận message, cần gate hoặc explicit startup orchestration.
- **Graceful shutdown không phải phép màu**: giới hạn timeout của Spring và deadline của nền tảng, phối hợp stop callback và thiết kế recovery khi shutdown bất thường.

### Tài liệu chính thức

- [Spring Framework 6.1 — SmartLifecycle API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html): auto-start, lazy-init semantics, phase, stop callback và default method.
- [Spring Framework 6.1 — DefaultLifecycleProcessor API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): quản lý start/stop theo phase và timeout.
- [Spring Framework — Startup and Shutdown Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html#beans-factory-lifecycle-processor): `LifecycleProcessor`, `SmartLifecycle` và xử lý context refresh/close.
- [Spring Framework — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): ý nghĩa lazy-init của singleton.
- [Spring Boot 3.3 — Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html): global lazy và những đánh đổi trong startup.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): `server.shutdown=graceful` và `spring.lifecycle.timeout-per-shutdown-phase`.
