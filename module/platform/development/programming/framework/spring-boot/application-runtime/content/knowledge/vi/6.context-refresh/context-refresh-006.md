# Vai trò của `LifecycleProcessor` trong refresh và đóng context

Trong Spring Boot, nhiều thành phần không chỉ cần **được tạo thành bean** mà còn phải **bắt đầu hoạt động**, **dừng nhận việc mới** và **giải phóng tài nguyên** đúng thứ tự. Ví dụ: kết nối tới một hệ thống ngoài, bộ nhận thông điệp từ hàng đợi, một bộ lập lịch, hoặc một thành phần xử lý tác vụ nền. Để điều phối phần **bắt đầu/dừng hoạt động** của các thành phần này khi `ApplicationContext` được làm mới hoặc đóng lại, Spring Framework dùng **`LifecycleProcessor`**.

Bài học này tập trung vào `LifecycleProcessor` trong chu kỳ **`refresh()` → chạy ứng dụng → `close()`** của `ApplicationContext`, theo Spring Framework 6.1/Spring Boot 3.3, trên Java 17 trở lên. Các điểm quan trọng là: nó chạy ở đâu, quản lý loại bean nào, `phase` quyết định thứ tự ra sao, `SmartLifecycle.stop(Runnable)` hoạt động thế nào và vì sao **stop** khác **destroy**.

## 1. Mô hình ban đầu: một bean có ba loại trạng thái khác nhau

Giả sử ứng dụng có một thành phần nhận công việc từ hàng đợi:

1. Spring **tạo bean** và inject phụ thuộc; bean tồn tại trong container.
2. Thành phần **start**: mở kết nối, đăng ký consumer, bắt đầu xử lý.
3. Thành phần **stop**: ngừng tiếp nhận, hoàn tất hoặc bàn giao công việc đang chạy.
4. Khi context đóng, Spring có thể **destroy** bean: gọi callback hủy để giải phóng phần tài nguyên còn lại.

Không nên gộp tất cả vào “Spring tạo bean” hoặc “JVM kết thúc”. Ba hành vi cần tách ra:

| Hành vi | Cơ chế Spring thường dùng | Ý nghĩa |
| --- | --- | --- |
| Tạo/khởi tạo bean | Constructor, dependency injection, `BeanPostProcessor`, `@PostConstruct` | Biến định nghĩa bean thành đối tượng có cấu hình cần thiết |
| Bắt đầu/dừng hoạt động | `Lifecycle`, `SmartLifecycle`, được `LifecycleProcessor` điều phối | Quyết định lúc nào thành phần **chạy** và **ngừng chạy** |
| Hủy bean | `@PreDestroy`, `DisposableBean.destroy()`, phương thức destroy | Giải phóng tài nguyên khi container hủy singleton |

Một bean có thể đã được tạo và khởi tạo thành công nhưng vẫn chưa `start()`. Ngược lại, sau `stop()`, đối tượng bean **vẫn tồn tại** cho tới bước destroy. Chính sự phân biệt đó giúp thực hiện shutdown có kiểm soát.

## 2. `LifecycleProcessor` là gì?

`org.springframework.context.LifecycleProcessor` là giao diện kế thừa `Lifecycle`, bổ sung hai phương thức:

~~~java
void onRefresh();
void onClose();
~~~

Ý nghĩa:

- **`onRefresh()`**: được context gọi khi hoàn tất giai đoạn refresh để điều phối tự khởi động những thành phần thích hợp.
- **`onClose()`**: được context gọi trong giai đoạn đóng để yêu cầu dừng những thành phần còn đang hoạt động.

`LifecycleProcessor` còn có các hành vi kế thừa từ `Lifecycle`: `start()`, `stop()` và `isRunning()`. Chúng cho phép context hỗ trợ thao tác start/stop tường minh mà không nhất thiết đóng context.

Spring Framework cung cấp **`org.springframework.context.support.DefaultLifecycleProcessor`** làm triển khai mặc định. Khi refresh context, Spring tìm bean mang tên **`lifecycleProcessor`**. Nếu ứng dụng không định nghĩa bean đó, Spring tạo triển khai mặc định để sử dụng.

Điểm cần nhớ: `LifecycleProcessor` là **bộ điều phối**, không phải từng thành phần nghiệp vụ. Nó tìm và gọi các bean thực hiện `Lifecycle`/`SmartLifecycle` theo quy tắc phù hợp. Vì vậy, lập trình viên thường cài đặt `SmartLifecycle` cho thành phần có vòng đời cần kiểm soát, thay vì tự viết một `LifecycleProcessor` mới.

## 3. Hai vị trí quan trọng trong `refresh()` và `close()`

### Trong `ApplicationContext.refresh()`

Với nền tảng `AbstractApplicationContext`, phần cuối chuỗi refresh có thể hiểu như sau:

~~~text
ApplicationContext.refresh()
    |
    +-- Chuẩn bị BeanFactory và xử lý BeanDefinitions
    +-- Đăng ký BeanPostProcessors
    +-- Khởi tạo những singleton cần khởi tạo sớm
    |
    +-- finishRefresh()
          |
          +-- initLifecycleProcessor()
          |     Lấy bean "lifecycleProcessor" nếu có,
          |     nếu không thì tạo DefaultLifecycleProcessor
          |
          +-- lifecycleProcessor.onRefresh()
          |     Tự start các SmartLifecycle đủ điều kiện
          |
          +-- publish ContextRefreshedEvent
    |
    v
refresh() hoàn tất
~~~

Điểm dễ nhầm: **`onRefresh()` chạy trước `ContextRefreshedEvent`** trong luồng mặc định của `AbstractApplicationContext`. Do đó, một bean `SmartLifecycle` được tự start trong `onRefresh()` có thể đã ở trạng thái running khi listener của `ContextRefreshedEvent` được gọi.

`onRefresh()` không phải lần “tạo bean đầu tiên”. Phần lớn singleton không lazy đã được tạo trước đó trong `finishBeanFactoryInitialization`. Tuy nhiên, `SmartLifecycle` có thể khiến những bean liên quan được khởi tạo lúc bộ điều phối tìm bean hoặc chuẩn bị start, kể cả khi khai báo lazy.

Trong một ứng dụng Spring Boot bình thường, `SpringApplication.run(...)` gọi quy trình refresh của context rồi mới đi tiếp tới `ApplicationStartedEvent`, runners và `ApplicationReadyEvent`. Vì thế, việc tự start của `SmartLifecycle` diễn ra **trước** các runner trên đường khởi động thành công.

### Trong `ApplicationContext.close()`

Khi context được đóng một cách có kiểm soát, phần cốt lõi của `AbstractApplicationContext.doClose()` có thứ tự:

~~~text
context.close()
    |
    +-- publish ContextClosedEvent
    |
    +-- lifecycleProcessor.onClose()
    |     Stop các Lifecycle đang chạy
    |     Theo phase giảm dần, có xét quan hệ phụ thuộc
    |
    +-- destroyBeans()
    |     Thực hiện @PreDestroy / DisposableBean / destroy callback
    |
    +-- closeBeanFactory() và các bước hoàn tất đóng context
    |
    v
context không còn hoạt động
~~~

Vì vậy, **`ContextClosedEvent` được phát trước `onClose()`**, còn các callback hủy bean thông thường diễn ra **sau bước stop**. Listener nhận `ContextClosedEvent` không nên giả định mọi `SmartLifecycle` đã dừng ở chính thời điểm listener bắt đầu chạy.

Chuỗi này mô tả đường đóng bình thường. Nếu tiến trình bị dừng cưỡng bức, bị `kill -9` hoặc gặp sự cố nghiêm trọng, JVM có thể không chạy được shutdown hook và Spring không thể bảo đảm mọi callback dừng/hủy được thực hiện.

## 4. `Lifecycle` và `SmartLifecycle` khác nhau như thế nào?

### `Lifecycle`: giao diện điều khiển chạy/dừng cơ bản

~~~java
package org.springframework.context;

public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Triển khai `Lifecycle` cung cấp cách khởi động/dừng có thể gọi tường minh. **Một bean chỉ triển khai `Lifecycle` thông thường không tự được start chỉ vì context refresh.** Nó có thể được start khi gọi `context.start()` hoặc khi một thành phần khác/quan hệ phụ thuộc khiến bộ điều phối cần start nó.

### `SmartLifecycle`: tự khởi động, theo pha và hỗ trợ dừng bất đồng bộ

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Các phương thức quan trọng:

~~~java
boolean isAutoStartup();
int getPhase();
void stop(Runnable callback);
~~~

Ý nghĩa:

- **`isAutoStartup()`**: cho biết có được tự start trong `onRefresh()` hay không; mặc định của `SmartLifecycle` là `true`.
- **`getPhase()`**: nhóm thứ tự startup/shutdown. Giá trị càng nhỏ thì thường start càng sớm và stop càng muộn.
- **`stop(Runnable callback)`**: cho phép bean báo **đã thực sự dừng** bằng cách gọi `callback.run()`. Đây là phương thức mà bộ điều phối dùng khi stop một bean `SmartLifecycle`.

| Tiêu chí | `Lifecycle` thông thường | `SmartLifecycle` |
| --- | --- | --- |
| Có `start()`, `stop()`, `isRunning()` | Có | Có |
| Tự start khi context refresh | Không mặc định | Có nếu `isAutoStartup() == true` |
| Phase mặc định mà bộ điều phối dùng | `0` nếu không có `Phased` | `Integer.MAX_VALUE` |
| Có callback xác nhận kết thúc dừng | Không có trong giao diện | Có, qua `stop(Runnable)` |
| Phù hợp | Thành phần chỉ cần start/stop tường minh | Listener/consumer/worker cần startup tự động hoặc shutdown có thứ tự |

**Ngoại lệ cần biết:** quan hệ phụ thuộc rõ ràng giữa các bean được ưu tiên hơn phase và lựa chọn auto-start riêng lẻ. Vì vậy, đừng tuyên bố một bean `Lifecycle` hoặc `SmartLifecycle` với `isAutoStartup=false` “không thể” được start trong lúc refresh trong mọi trường hợp; nó có thể cần được start vì là phụ thuộc của một bean khác đang được start.

`SmartLifecycle` có cơ chế tìm bean phục vụ auto-start ngay cả khi bean được đánh dấu lazy. Vì vậy, chỉ thêm `@Lazy` không phải cách đáng tin để ngăn một `SmartLifecycle` tự khởi động. Muốn điều khiển tự start, hãy dùng `isAutoStartup()` và thiết kế quan hệ phụ thuộc phù hợp.

## 5. Quy tắc `phase`: start tăng dần, stop giảm dần

Giả sử có ba thành phần:

- `connection` có phase **-100**, thiết lập kết nối nền.
- `consumer` có phase **0**, đọc dữ liệu thông qua kết nối.
- `publisher` có phase **100**, phụ thuộc vào hoạt động của consumer.

Nếu cả ba đều đủ điều kiện start:

~~~text
REFRESH / START:
connection (-100) --> consumer (0) --> publisher (100)

CLOSE / STOP:
publisher (100) --> consumer (0) --> connection (-100)
~~~

Đây là nguyên tắc **start từ phase thấp lên cao, stop từ phase cao xuống thấp**. Trong cùng một phase, **không nên phụ thuộc vào thứ tự chính xác** nếu không có ràng buộc khác.

Một số chi tiết quan trọng:

1. Phase có thể là số âm, số 0 hoặc số dương. Không phải enum cố định và không cần liên tiếp.
2. `SmartLifecycle` mặc định dùng `Integer.MAX_VALUE`, tức thường start khá muộn và stop khá sớm so với bean phase 0.
3. Bean chỉ thực hiện `Lifecycle` thường được bộ điều phối xếp ở phase 0.
4. **`depends-on`/quan hệ phụ thuộc mà container biết được có thể ưu tiên hơn phase**. Bean phụ thuộc phải được start sau dependency và stop trước dependency, kể cả khi phase được khai báo ngược.
5. Dùng phase để biểu đạt yêu cầu vận hành. Ví dụ consumer nên ngừng nhận tin trước khi đóng kết nối mà nó dùng.

Phase **không thay thế thứ tự khởi tạo bean**, cũng không phải thứ tự của `ApplicationRunner`. Nó là trục điều phối **start/stop của các Lifecycle bean**.

## 6. `stop()` và `stop(Runnable)`: điểm dễ sai nhất

Một triển khai `SmartLifecycle` phải quan tâm cả hai cách dừng:

~~~java
@Override
public void stop() {
    // Dừng đồng bộ nếu thích hợp
}

@Override
public void stop(Runnable callback) {
    // Dừng hoạt động, rồi báo đã hoàn tất
    stop();
    callback.run();
}
~~~

Đây là đoạn minh họa đơn giản. Với shutdown **bất đồng bộ**, cách đúng là chỉ gọi callback sau khi công việc dừng thực sự hoàn tất, ví dụ:

~~~java
@Override
public void stop(Runnable callback) {
    stopAcceptingNewMessages();

    backgroundExecutor.execute(() -> {
        try {
            awaitInFlightMessages();
        } finally {
            running = false;
            callback.run();
        }
    });
}
~~~

Đoạn trên là **mã mô tả cơ chế**, giả định lớp đã có `stopAcceptingNewMessages()`, `backgroundExecutor`, `awaitInFlightMessages()` và trạng thái `running`; không phải chương trình độc lập để biên dịch.

Khi dừng theo phase, `DefaultLifecycleProcessor` cần biết lúc nào các bean ở phase hiện tại hoàn tất để tiếp tục các phase sau. **Nếu bean `SmartLifecycle` quên gọi `callback.run()`, processor có thể phải chờ đến giới hạn timeout của phase**, khiến shutdown kéo dài. Đừng gọi callback ngay khi chỉ mới gửi lệnh dừng nếu thành phần vẫn đang xử lý cần phải hoàn tất.

Hợp đồng quan trọng:

- Bean `SmartLifecycle` được processor dừng thông qua **`stop(Runnable)`**, không nhất thiết qua `stop()` không tham số.
- Với triển khai dừng đồng bộ, có thể gọi `stop()` rồi `callback.run()` trong `finally` để bảo đảm xác nhận hoàn tất kể cả khi xảy ra lỗi.
- Với dừng bất đồng bộ, bảo đảm callback được gọi **đúng một lần khi công việc kết thúc**, và xử lý tình huống không thể lập lịch công việc.
- `isRunning()` nên phản ánh trạng thái hoạt động thực tế. Một cờ running không chính xác có thể khiến processor xử lý sai thành phần.
- Thiết kế `start()` và `stop()` có khả năng gọi lặp hợp lý: `start()` trên đối tượng đã chạy và `stop()` trên đối tượng đã dừng không nên gây hiệu ứng nhân đôi.

### Timeout shutdown theo phase

Trong Spring Framework **6.1**, `DefaultLifecycleProcessor.setTimeoutPerShutdownPhase(long)` cho phép cấu hình thời gian tối đa chờ mỗi nhóm phase; giá trị mặc định theo API 6.1 là **30.000 ms (30 giây)**. Đây là giới hạn chờ các callback dừng của nhóm phase, **không phải giới hạn sống của toàn JVM** hay thời lượng bắt buộc mọi shutdown phải mất.

Trong Spring Boot 3.3, có thể cấu hình thời hạn liên quan bằng:

~~~properties
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

Đặt 20 giây chỉ là ví dụ cấu hình; nên chọn dựa trên thời gian dừng thật của các thành phần. Cần xem xét cả **timeout của bộ điều phối container/orchestrator bên ngoài**, vì nếu hệ thống ngoài gửi tín hiệu kill trước khi Spring hoàn tất, bean vẫn có thể bị cắt ngang.

## 7. Ví dụ chạy được: quan sát hai phase trong refresh và close

Ví dụ sử dụng **Java 17 + Spring Boot 3.3.13 + Gradle**. Để đầu ra tập trung vào thứ tự Lifecycle, chương trình chạy **không mở web server**, tắt banner và log startup do `SpringApplication` phát ra. Bản thân `LifecycleProcessor` vẫn thực hiện đầy đủ công việc.

### Cấu trúc dự án

~~~text
lifecycle-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/lifecycle/LifecycleDemoApplication.java
~~~

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'lifecycle-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
}

group = 'com.example'
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
    // Gradle native BOM quản lý phiên bản cho các starter của Spring Boot.
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

BOM đã được khai báo nên `spring-boot-starter` không cần tự ghi phiên bản. Cần Gradle tương thích với plugin Spring Boot 3.3 và có thể tải phụ thuộc khi xây dựng lần đầu. Nếu đang làm trong dự án Spring Boot có sẵn, sử dụng cấu hình phụ thuộc của dự án thay vì thêm plugin trùng lặp.

Tệp `src/main/java/com/example/lifecycle/LifecycleDemoApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.boot.context.event.ApplicationStartedEvent;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

@SpringBootApplication
public class LifecycleDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context =
                     application.run(args)) {
            System.out.println("MAIN contextActive=" + context.isActive());
        }
        System.out.println("MAIN after close");
    }

    @Bean
    SmartLifecycle receiver() {
        return new PhasedWorker("receiver", -100);
    }

    @Bean
    SmartLifecycle processor() {
        return new PhasedWorker("processor", 100);
    }

    @Bean
    ApplicationRunner runner() {
        return args -> System.out.println("RUNNER");
    }

    @Bean
    DisposableBean cleanupResource() {
        return () -> System.out.println("DESTROY resource");
    }

    @EventListener
    public void afterRefresh(ContextRefreshedEvent event) {
        System.out.println("EVENT ContextRefreshedEvent");
    }

    @EventListener
    public void afterStarted(ApplicationStartedEvent event) {
        System.out.println("EVENT ApplicationStartedEvent");
    }

    @EventListener
    public void afterReady(ApplicationReadyEvent event) {
        System.out.println("EVENT ApplicationReadyEvent");
    }

    @EventListener
    public void beforeStop(ContextClosedEvent event) {
        System.out.println("EVENT ContextClosedEvent");
    }

    static final class PhasedWorker implements SmartLifecycle {
        private final String name;
        private final int phase;
        private volatile boolean running;

        PhasedWorker(String name, int phase) {
            this.name = name;
            this.phase = phase;
        }

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("START " + name + " phase=" + phase);
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("STOP " + name + " phase=" + phase);
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
            return phase;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }
    }
}
~~~

Mã dùng `DisposableBean` để làm nổi bật sự khác nhau giữa **dừng các thành phần `SmartLifecycle`** và **hủy tài nguyên ở cuối quá trình đóng context**. Hai bean `receiver` và `processor` chỉ in log start/stop. Bean `cleanupResource` in log destroy và **không** triển khai `Lifecycle`.

### Chạy

Tại thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có wrapper nhưng đã cài Gradle tương thích, chạy `gradle bootRun`. Dòng in từ Gradle hoặc hệ thống logging có thể xuất hiện thêm; **các dòng do mã ví dụ `System.out.println` tạo ra** trên đường chạy thành công có thứ tự:

~~~text
START receiver phase=-100
START processor phase=100
EVENT ContextRefreshedEvent
EVENT ApplicationStartedEvent
RUNNER
EVENT ApplicationReadyEvent
MAIN contextActive=true
EVENT ContextClosedEvent
STOP processor phase=100
STOP receiver phase=-100
DESTROY resource
MAIN after close
~~~

Giải thích từng nhóm:

1. `receiver` có phase -100 nên start trước `processor` phase 100, mặc dù cả hai là bean `SmartLifecycle` tự khởi động.
2. `ContextRefreshedEvent` xuất hiện **sau** khi `onRefresh()` đã start các thành phần.
3. `ApplicationStartedEvent` xuất hiện sau refresh; `ApplicationRunner` chạy tiếp theo; `ApplicationReadyEvent` xuất hiện sau runner.
4. Khi `run` trả về, context vẫn đang hoạt động. Khối `try-with-resources` sau đó gọi `context.close()`.
5. `ContextClosedEvent` phát trước lúc lifecycle processor dừng bean.
6. Stop đi ngược phase: 100 rồi -100.
7. `DESTROY resource` xuất hiện khi Spring bắt đầu hủy các singleton sau giai đoạn stop. Nó chứng minh callback destroy là cơ chế riêng.
8. `MAIN after close` chỉ xuất hiện sau khi `close()` trả về.

**Lưu ý về đầu ra:** hệ thống có thể phát thêm log của Spring/Gradle; ví dụ không dự đoán mọi dòng từ thư viện. Kết quả trên mô tả chính xác các dòng do mã `System.out.println` trong ví dụ tạo ra, khi không có lỗi và không có thành phần tùy biến khác chen vào chuỗi vòng đời.

### Thử thay đổi một phase

Đổi bean `processor` thành:

~~~java
@Bean
SmartLifecycle processor() {
    return new PhasedWorker("processor", -200);
}
~~~

Khi chạy lại, `processor` phase -200 sẽ **start trước** `receiver` -100, và **stop sau** `receiver`. Chỉ thay đổi `phase`, không cần sắp thứ tự thủ công trong `main`.

### Thử `isAutoStartup()`

Thay `return true;` trong `isAutoStartup()` của `PhasedWorker` thành `return false;`. Nếu không có quan hệ phụ thuộc đặc biệt và không gọi `context.start()`, hai bean này **không tự start trong refresh**. Chúng vẫn được tạo thành bean, có thể nhận injection và chờ lệnh start tường minh.

Để thử riêng, có thể gọi:

~~~java
context.start();
~~~

trong khối `try` của ví dụ, sau dòng in trạng thái. Đây là **thao tác tường minh trên context đang hoạt động**; bộ điều phối sẽ start những `Lifecycle` thích hợp còn chưa chạy, và khi `context.close()` xảy ra thì tiếp tục stop chúng.

## 8. Quan hệ với `@PostConstruct`, `@PreDestroy` và `DisposableBean`

Ví dụ một bean kết nối có thể có các callback:

~~~java
@PostConstruct
public void initialize() {
    // Chuẩn bị dữ liệu, kiểm tra cấu hình ban đầu
}

@Override
public void start() {
    // Bắt đầu consumer hoặc luồng xử lý
}

@Override
public void stop() {
    // Dừng tiếp nhận và ngừng xử lý
}

@PreDestroy
public void release() {
    // Đóng socket, giải phóng tài nguyên còn lại
}
~~~

Đây là **mã minh họa các phương thức trong cùng một class được cài đặt đúng interface**, không phải một lớp Java hoàn chỉnh. Annotation `@PostConstruct`/`@PreDestroy` cần import tương ứng `jakarta.annotation.*` trong Spring Boot 3.x.

Thứ tự thường thấy với singleton không lazy có `SmartLifecycle` auto-start:

~~~text
Tạo bean, inject, @PostConstruct
             |
             v
LifecycleProcessor.onRefresh() -> start()
             |
             v
ContextRefreshedEvent -> Started -> Ready
             |
             v
ContextClosedEvent
             |
             v
LifecycleProcessor.onClose() -> stop(Runnable)
             |
             v
Destroy bean: @PreDestroy / DisposableBean / destroy-method
~~~

Không lấy thứ tự trên làm cam kết cho **mọi bean lazy**, hoặc cho một bean được tạo muộn sau refresh. Hơn nữa, khi có nhiều loại callback destroy trên cùng bean, Spring còn quy định thứ tự giữa các cơ chế đó; bài học này chỉ nhấn mạnh **stop do LifecycleProcessor điều phối trước hủy singleton trong đường đóng context bình thường**.

**Nguyên tắc thiết kế:** `@PostConstruct` phù hợp để thiết lập trạng thái của một bean; `SmartLifecycle.start()` phù hợp khi cần phát lệnh bắt đầu xử lý theo trật tự với các thành phần khác; `stop(Runnable)` phù hợp để dừng hoạt động có điều phối; `@PreDestroy`/`DisposableBean` để hoàn tất dọn dẹp tài nguyên.

## 9. `context.start()` và `context.stop()` không giống `refresh()` và `close()`

Có thể thao tác trực tiếp:

~~~java
context.stop();   // Ngừng những Lifecycle bean đang chạy
context.start();  // Yêu cầu start lại những Lifecycle bean phù hợp
context.close();  // Đóng container và hủy các singleton
~~~

Sự khác nhau:

| Lời gọi | Phạm vi | Context còn có thể hoạt động tiếp? |
| --- | --- | --- |
| `context.refresh()` | Xây dựng/làm mới container theo hợp đồng của kiểu context | Có, nếu refresh thành công |
| `context.start()` | Gọi processor `start()` đối với các Lifecycle bean phù hợp | Có |
| `context.stop()` | Gọi processor `stop()` đối với các Lifecycle bean đang chạy | Có; có thể gọi start trở lại nếu thiết kế hỗ trợ |
| `context.close()` | Phát sự kiện close, stop Lifecycle rồi hủy bean và đóng container | Không; không thể đơn giản gọi `start()` để hồi sinh context đã đóng |

Không phải mọi loại context đều hỗ trợ refresh lặp lại sau lần refresh đầu; ví dụ `GenericApplicationContext` chỉ hỗ trợ refresh một lần. Đừng coi `refresh()` là lệnh restart an toàn của mọi Spring Boot application.

`ContextStartedEvent` và `ContextStoppedEvent` gắn với việc gọi `context.start()/stop()` rõ ràng; chúng **không tương đương** với `ApplicationStartedEvent`/`ApplicationReadyEvent` của Spring Boot. Tên tương tự nhưng điểm phát và ý nghĩa vòng đời khác nhau.

## 10. Kết nối với graceful shutdown của Spring Boot

Khi ứng dụng Spring Boot chạy máy chủ web, Spring Boot có thể tổ chức dừng tiếp nhận HTTP và chờ request đang xử lý thông qua cơ chế **graceful shutdown**, tùy phiên bản/cấu hình máy chủ. Nó sử dụng các điểm mở rộng vòng đời để tham gia vào shutdown có thứ tự.

Ví dụ cấu hình:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=30s
~~~

Các giá trị trên chỉ liên quan đến quá trình **đóng context có kiểm soát**. Chúng không biến mọi kết nối bên ngoài thành graceful shutdown tự động. Nếu ứng dụng tự quản lý consumer, worker hay socket, cần triển khai cơ chế ngừng nhận việc và chờ việc đang xử lý trong `SmartLifecycle.stop(Runnable)` hoặc cơ chế quản lý tài nguyên tương ứng.

Một số nguyên tắc:

- Đặt phase có chủ đích để **dừng nguồn sinh việc trước khi dừng tài nguyên nền mà nguồn đó cần**.
- Đảm bảo stop không bị treo vô hạn: dùng timeout nội bộ, callback hợp lệ và quan sát lỗi.
- Bảo đảm giá trị timeout của Spring và hạn chót shutdown của Kubernetes/systemd/container không mâu thuẫn nhau.
- Đừng giả định sự kiện `ContextClosedEvent` nghĩa là mọi request/consumer đã ngừng; sự kiện này có thể phát trước quá trình dừng bean.
- Nếu ứng dụng bị kill cưỡng bức, callback Java có thể không chạy đủ. Với công việc quan trọng, cần cơ chế bảo đảm dữ liệu nằm ở tầng hàng đợi, giao dịch hoặc hệ thống lưu trữ.

## 11. Chọn `phase` khi các thành phần phụ thuộc nhau

Giả sử có ba thành phần thuộc ứng dụng xử lý thông điệp:

| Thành phần | Vai trò | Phase minh họa |
| --- | --- | --- |
| `connectionManager` | Kết nối tới dịch vụ ngoài | -100 |
| `messageConsumer` | Nhận thông điệp dựa trên kết nối | 0 |
| `reportingWorker` | Xử lý phần kết quả cuối | 100 |

Theo phase, start là `connectionManager → messageConsumer → reportingWorker`, stop ngược lại. **Nhưng** điều đó chỉ là một thiết kế ví dụ. Phase không tự chứng minh thứ tự đó đúng cho mọi hệ thống. Nếu `reportingWorker` phải tiếp tục xử lý cho tới khi consumer dừng hoàn toàn, có thể cần **dừng consumer trước worker**. Khi đó phải thiết kế phase và quan hệ phụ thuộc lại dựa trên luồng dữ liệu thật, không sao chép máy móc các con số.

Khi thành phần có quan hệ phụ thuộc chắc chắn ở cấp bean, khai báo phụ thuộc rõ ràng theo cơ chế Spring có thể giúp bộ điều phối sắp thứ tự start/stop. Tuy nhiên, phase vẫn cần được đọc và kiểm chứng để tránh mâu thuẫn với các bean khác của framework.

Đối với bean có cùng phase, hãy coi thứ tự là không xác định. Nếu cần thứ tự chặt chẽ, dùng phase khác nhau và quan hệ phụ thuộc thích hợp.

## 12. Cấu hình timeout hoặc thay bộ xử lý mặc định

Trong phần lớn ứng dụng Spring Boot, không cần tự khai báo bean `LifecycleProcessor`. Triển khai mặc định đã hỗ trợ phase và callback.

Khi cần điều chỉnh thời gian chờ trong Spring Boot 3.3, ưu tiên cấu hình:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 30s
~~~

Ở cấp Spring Framework, `DefaultLifecycleProcessor` có phương thức:

~~~java
processor.setTimeoutPerShutdownPhase(30_000L);
~~~

Dòng này là **mã minh họa** khi đã có biến `DefaultLifecycleProcessor processor`; nó không phải lệnh cần tự thêm vào mỗi ứng dụng.

Có thể thay bộ xử lý bằng bean mang tên `lifecycleProcessor`, nhưng làm vậy nghĩa là thay một thành phần điều phối quan trọng cho cả context. Nếu chỉ muốn timeout, dùng cấu hình Spring Boot khi có thể. Khi thay thế, phải bảo toàn đúng hợp đồng `LifecycleProcessor`, kể cả onRefresh, onClose, điều phối start/stop và xử lý phụ thuộc.

## 13. Lỗi phổ biến khi tự triển khai vòng đời

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Bean đã được tạo nhưng `start()` không chạy sau refresh | Chỉ triển khai `Lifecycle`; hoặc `isAutoStartup()` trả `false` | Dùng `SmartLifecycle` và lựa chọn auto-start đúng; kiểm tra quan hệ phụ thuộc |
| `start()` gọi trước khi tài nguyên nền sẵn sàng | Phase không phù hợp hoặc phụ thuộc chưa khai báo | Đặt phase thấp hơn cho tài nguyên nền và khai báo phụ thuộc cần thiết |
| Shutdown mất đúng khoảng timeout rồi mới đi tiếp | `stop(Runnable)` không gọi callback, callback gọi quá muộn hoặc tác vụ dừng bị kẹt | Đảm bảo callback được gọi khi dừng xong; có timeout/log đủ để chẩn đoán |
| Có `ContextClosedEvent` nhưng bean vẫn running | Sự kiện close được phát **trước** lifecycle processor dừng bean | Quan sát log `stop` hoặc callback dừng, không dùng event close làm dấu hiệu stop xong |
| `@PreDestroy` chạy nhưng không có log `STOP` | Bean không nằm trong nhóm Lifecycle đang chạy; hoặc ứng dụng chỉ dùng destroy callback | Kiểm tra interface/`isRunning()`/trạng thái thực tế |
| `SmartLifecycle` gắn `@Lazy` nhưng vẫn được tạo lúc startup | Cơ chế auto-start có thể yêu cầu khởi tạo bean để start | Dùng `isAutoStartup()` phù hợp; đừng dựa vào lazy-init như công tắc lifecycle |
| Lệnh `context.stop()` tưởng là tắt toàn bộ ứng dụng | `stop()` không hủy bean hay đóng container | Chỉ gọi `close()`/shutdown hợp lệ khi muốn giải phóng context |
| Stop phase cao diễn ra trước bean mà nó đang phụ thuộc, gây lỗi | Chưa biểu đạt đúng quan hệ dừng hoặc đang dùng phase sai | Thiết kế phase theo thứ tự dừng cần thiết và khai báo phụ thuộc rõ ràng |
| Dùng `Thread.sleep` trong callback dừng quá lâu | Chặn tiến trình shutdown, có thể vượt giới hạn của container | Dừng có điều kiện, dùng callback và giới hạn thời gian thay vì chờ vô hạn |

## 14. Câu hỏi tự kiểm tra

1. **`LifecycleProcessor.onRefresh()` xảy ra trước hay sau `ContextRefreshedEvent` trong `AbstractApplicationContext`?** Trước.
2. **Một bean chỉ triển khai `Lifecycle` có tự start khi refresh theo mặc định không?** Không; ngoại lệ có thể phát sinh do ràng buộc phụ thuộc của thành phần tự start khác.
3. **Một `SmartLifecycle` mặc định trả giá trị nào từ `isAutoStartup()`?** `true`.
4. **Một `SmartLifecycle` không ghi đè `getPhase()` có phase mặc định nào trong Spring 6.1?** `Integer.MAX_VALUE`.
5. **Hai bean phase -10 và 20, bean nào start trước?** -10; khi đóng bình thường, 20 stop trước.
6. **Vì sao `stop(Runnable)` phải gọi `callback.run()`?** Để bộ điều phối biết việc dừng đã hoàn tất và tiếp tục tiến trình shutdown theo phase mà không chờ đến timeout.
7. **`ContextClosedEvent` đã phát có nghĩa mọi bean được destroy chưa?** Chưa; event close được phát trước stop và destroy.
8. **`context.stop()` có hủy bean không?** Không. Nó điều phối dừng hoạt động, còn `close()` thực hiện đóng context và hủy các bean thích hợp.
9. **Một bean đang running sau refresh nhưng không phải `SmartLifecycle` có thể được dừng khi context đóng không?** Có, nếu là `Lifecycle` đã chạy và được bộ điều phối quản lý.
10. **Có thể dùng `@PreDestroy` thay hoàn toàn `SmartLifecycle` không?** Không phải trong mọi trường hợp: `@PreDestroy` là giai đoạn hủy bean; `SmartLifecycle` còn kiểm soát tự start, phase, stop và xác nhận hoàn tất dừng.

Khi theo dõi khởi động và shutdown, hãy tách ba đường: **khởi tạo bean**, **start/stop do `LifecycleProcessor` điều phối**, và **destroy bean**. `refresh()` kết thúc bằng việc tự start những thành phần `SmartLifecycle` phù hợp; `close()` phát sự kiện đóng, điều phối stop theo thứ tự rồi mới hủy singleton. Hiểu ranh giới này giúp thiết kế bộ nhận tin, tác vụ nền và shutdown ổn định hơn.

### Tài liệu tham khảo

- Spring Framework 6.1 — `LifecycleProcessor` API: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/LifecycleProcessor.html
- Spring Framework 6.1 — `SmartLifecycle` API (phase, auto-start, callback): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.1 — `DefaultLifecycleProcessor` API (onRefresh/onClose, timeout): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework 6.1 — `AbstractApplicationContext` API (`finishRefresh`, `doClose`): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html
- Spring Boot 3.3 — Graceful Shutdown: https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html
- Spring Boot Gradle — Managing Dependencies: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
