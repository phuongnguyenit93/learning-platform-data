# Lifecycle cho thành phần cần khởi động, dừng chủ động trong Spring Core Container

## 1. Bài toán: khởi tạo bean xong chưa có nghĩa thành phần đã chạy

Một Spring bean có thể được tạo thành công, được inject đầy đủ dependency và hoàn tất initialization callback nhưng vẫn **chưa được phép bắt đầu công việc**. Điều này đúng với message consumer, polling worker, scheduler nội bộ, stream listener, bộ xử lý hàng đợi, server phụ hoặc một dịch vụ duy trì kết nối dài hạn.

Ví dụ, một worker nhận message có ba trạng thái nghiệp vụ khác nhau:

1. **Đã tạo và cấu hình:** đã có client, endpoint, credentials và thông số chạy.
2. **Đang chạy:** đã bắt đầu nhận message hoặc chạy vòng polling.
3. **Đã dừng:** không nhận công việc mới, các tác vụ đang chạy được dừng/hoàn tất theo chính sách.

Đặt toàn bộ logic này trong constructor hoặc `@PostConstruct` khiến việc kiểm soát start/stop theo application context khó rõ ràng. Spring Core Container cung cấp giao thức `org.springframework.context.Lifecycle` để bean công khai trạng thái và thao tác **khởi động/dừng chủ động**. Nếu cần tự khởi động lúc context refresh, thứ tự theo phase hoặc shutdown bất đồng bộ, Spring cung cấp `SmartLifecycle`.

Sau bài học, bạn có thể:

- Viết một bean triển khai chính xác `Lifecycle.start()`, `stop()`, `isRunning()`.
- Phân biệt `context.refresh()`, `context.start()`, `context.stop()` và `context.close()`.
- Hiểu `SmartLifecycle`, `isAutoStartup()`, `getPhase()` và `stop(Runnable callback)`.
- Lựa chọn giữa start/stop chủ động, tự khởi động khi refresh và destruction callback.
- Điều phối thứ tự giữa các thành phần phụ thuộc nhau, tránh dừng sai thứ tự hoặc chặn shutdown.
- Chạy chương trình Java 17 + Spring Framework 6.2 để quan sát lifecycle và kết quả stdout xác định.

Phạm vi là vòng đời `ApplicationContext` trong Spring Framework Core Container. Không giả định ứng dụng bắt buộc dùng Spring Boot, Web MVC hay hệ thống message broker.

## 2. Giao diện `Lifecycle`

Interface thuộc package `org.springframework.context`:

~~~java
package org.springframework.context;

public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Đây là **chữ ký minh họa hợp đồng API**, không cần tự tạo source cho interface vì nó có sẵn trong thư viện Spring.

Ba phương thức có ý nghĩa riêng:

| Method | Ý nghĩa | Hợp đồng nên thực hiện |
| --- | --- | --- |
| `start()` | Chuyển component sang trạng thái running, bắt đầu hoạt động chủ động | An toàn nếu được gọi lại khi đang running; chỉ công bố running khi khởi động thành công |
| `stop()` | Yêu cầu component dừng hoạt động | Dừng nhận việc mới, giải phóng tài nguyên vận hành phù hợp; an toàn nếu gọi lại |
| `isRunning()` | Báo component hiện đang hoạt động hay không | Phản ánh **trạng thái thực tế**, không chỉ bean đã được constructor gọi |

**Một bean có implements `Lifecycle` không đương nhiên được Spring tự start chỉ vì bean được tạo.** Với plain `Lifecycle`, container mặc định không tự khởi động ở thời điểm refresh; có thể gọi `context.start()` hoặc thiết lập luồng điều phối phù hợp. Đây là điểm khác `SmartLifecycle`.

### Lifecycle khác gì bean initialization?

- Constructor, dependency injection, `@PostConstruct` hoặc `InitializingBean.afterPropertiesSet()` phục vụ **chuẩn bị bean**.
- `Lifecycle.start()` phục vụ **bắt đầu chạy**, có thể xảy ra sau initialization và có thể gọi lại sau một lần stop.
- `Lifecycle.stop()` phục vụ **ngừng chạy**, không nhất thiết đồng nghĩa destroy bean hoặc close context.
- `@PreDestroy` và custom destroy method phục vụ **kết thúc vòng đời bean**, thường khi context đóng đối với singleton.

Do đó, có thể có một bean đã hoàn tất `@PostConstruct` nhưng `isRunning() == false`.

## 3. Ví dụ `Lifecycle` tối giản cho worker

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.context.Lifecycle;

public final class PollingWorker implements Lifecycle {
    private final AtomicBoolean running = new AtomicBoolean(false);

    @Override
    public void start() {
        if (running.compareAndSet(false, true)) {
            System.out.println("worker started");
        }
    }

    @Override
    public void stop() {
        if (running.compareAndSet(true, false)) {
            System.out.println("worker stopped");
        }
    }

    @Override
    public boolean isRunning() {
        return running.get();
    }
}
~~~

Class này **biên dịch được khi có spring-context trên classpath**, nhưng chỉ đổi trạng thái để minh họa; worker thực tế cần thực hiện việc đăng ký listener hoặc điều khiển executor tương ứng. `AtomicBoolean` giúp ví dụ đọc/ghi trạng thái an toàn giữa các thread, nhưng bản thân nó **không đủ** để quản lý vòng đời nhiều tài nguyên, xử lý task đang chạy hay khởi động thất bại.

Nếu tạo bằng `new PollingWorker()` rồi gọi `start()` thủ công, đó chỉ là Java object. Để Spring điều phối, đăng ký class thành bean qua `@Component` hoặc `@Bean`.

Một nguyên tắc thiết kế: `start()` và `stop()` nên **idempotent ở trạng thái**. Gọi `start()` khi component đang chạy không được mở thêm một listener giống hệt; gọi `stop()` hai lần không được cố đóng cùng socket một cách nguy hiểm.

## 4. Vòng đời `ApplicationContext` và thời điểm gọi

Trong `ConfigurableApplicationContext`, bốn hành động có mục đích khác nhau:

| Hành động | Mục đích | Ảnh hưởng đến lifecycle component |
| --- | --- | --- |
| `refresh()` | Xây dựng/làm mới context, khởi tạo infrastructure và các singleton cần thiết | `LifecycleProcessor.onRefresh()` có thể auto-start `SmartLifecycle` |
| `start()` | Gửi tín hiệu start cho các `Lifecycle` bean thông qua lifecycle processor | Bắt đầu những component chưa chạy, theo phase/dependency |
| `stop()` | Gửi tín hiệu stop cho những component đang chạy | Dừng có tổ chức theo phase/dependency, context vẫn mở |
| `close()` | Đóng context, ngừng lifecycle components và destroy singleton được quản lý | Ngừng những component còn chạy, sau đó thực hiện bean destruction |

### 4.1. Refresh không đồng nghĩa start mọi bean `Lifecycle`

Ví dụ:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(AppConfig.class)) {
    // Context đã refresh và có thể dùng getBean().
    context.start(); // Yêu cầu start các Lifecycle bean.
    context.stop();  // Yêu cầu stop; context vẫn có thể dùng.
}
~~~

Đoạn trên **phụ thuộc `AppConfig`** ở phần ví dụ hoàn chỉnh. Trong `AnnotationConfigApplicationContext(AppConfig.class)`, constructor đã thực hiện `refresh()`. Không gọi thêm `refresh()` trên context này như một thao tác “restart” tùy ý; `GenericApplicationContext`/`AnnotationConfigApplicationContext` thông thường chỉ hỗ trợ refresh một lần.

### 4.2. Stop chưa phải close

Sau `context.stop()`, bean definition và nhiều singleton vẫn còn tồn tại; có thể gọi `context.start()` lại để khởi động các component phù hợp. Khi `context.close()`, Spring tiến hành shutdown và destroy các bean theo lifecycle; không giả định context đã close có thể restart.

Với một component quản lý resource, `stop()` có thể hủy subscription hoặc dừng vòng polling nhưng giữ cấu hình để restart; `destroy()`/`@PreDestroy` có thể đóng client hoặc pool vĩnh viễn. Thiết kế nào phù hợp còn tùy ownership của resource.

### 4.3. Context cũng implements `Lifecycle`

`ConfigurableApplicationContext` mở rộng `Lifecycle`; `start()`, `stop()` và `isRunning()` của context được ủy quyền qua `LifecycleProcessor`. Gọi `context.start()` **không** có nghĩa Spring tạo lại tất cả singleton. Việc tạo bean và việc khởi động thành phần vận hành là hai pha khác nhau.

## 5. `LifecycleProcessor` làm nhiệm vụ gì?

Spring dùng interface `LifecycleProcessor` để điều phối lifecycle của các bean đăng ký trong context. Implementation mặc định thường là `DefaultLifecycleProcessor`.

Vai trò chính:

1. Khi refresh xong, gọi `onRefresh()` để quyết định start các `SmartLifecycle` auto-start.
2. Khi ứng dụng gọi `context.start()`, start các `Lifecycle` bean thích hợp.
3. Khi gọi `context.stop()`, stop những bean đang chạy.
4. Khi close context, gọi `onClose()` để dừng lifecycle components trước khi destroy bean.
5. Xử lý thứ tự qua `phase` và quan hệ bean dependency.

Một chương trình bình thường không cần tự tạo `DefaultLifecycleProcessor`. Chỉ cấu hình processor riêng nếu thực sự cần thay đổi chính sách như timeout shutdown hoặc cách điều phối nâng cao.

Quan trọng: callback của `LifecycleProcessor` thuộc **vòng đời context**; callback init/destroy của bean thuộc **vòng đời một bean instance**. Có thể liên quan nhau nhưng không thay thế cho nhau.

## 6. `SmartLifecycle`: tự khởi động và điều phối theo phase

`org.springframework.context.SmartLifecycle` mở rộng cả `Lifecycle` và `Phased`. Nó dành cho component cần:

- Auto-start sau khi context refresh.
- Điều phối startup/shutdown theo phase.
- Báo hoàn tất shutdown bất đồng bộ bằng `stop(Runnable callback)`.

Các phương thức liên quan:

~~~java
import org.springframework.context.SmartLifecycle;

public final class MessageConsumer implements SmartLifecycle {
    // Cần tự triển khai start(), stop(), isRunning() và
    // có thể override isAutoStartup(), getPhase(), stop(Runnable).
}
~~~

Đây chỉ là skeleton minh họa; để class biên dịch cần implementation hợp lệ của các abstract methods.

| Method | Mặc định trong `SmartLifecycle` | Khi thường override |
| --- | --- | --- |
| `isAutoStartup()` | `true` | Muốn component chỉ chạy khi start chủ động |
| `getPhase()` | `Integer.MAX_VALUE` trong Spring 6.2 | Cần đặt thứ tự startup/shutdown phù hợp |
| `stop(Runnable callback)` | Delegate sang `stop()`, sau đó gọi callback | Component ngừng bất đồng bộ, cần báo khi dừng xong |

Chính mặc định `isAutoStartup() == true` là lý do một `SmartLifecycle` singleton có thể chạy ngay sau `refresh()` mà không cần `context.start()`.

### 6.1. Thứ tự phase

Với `DefaultLifecycleProcessor`:

- **Start:** phase **nhỏ trước, lớn sau**.
- **Stop:** phase **lớn trước, nhỏ sau**.
- Plain `Lifecycle` mặc định nằm ở phase `0` nếu không triển khai `Phased`.
- `SmartLifecycle` mặc định có phase `Integer.MAX_VALUE`, thường start muộn và stop sớm so với plain `Lifecycle`.

Ví dụ ý tưởng:

~~~text
START:
phase -100 (Infrastructure) -> phase 0 (Core) -> phase 100 (Consumer)

STOP:
phase 100 (Consumer) -> phase 0 (Core) -> phase -100 (Infrastructure)
~~~

Vì consumer cần hạ tầng trước khi nhận việc, hạ tầng nên start trước và stop sau. Tuy nhiên, **dependency đã khai báo giữa các bean có thể ưu tiên hơn phase**; một dependent bean phải start sau dependency, stop trước dependency, kể cả phase định nghĩa khác. Không dùng phase như cách duy nhất để biểu đạt quan hệ phụ thuộc thực tế.

### 6.2. `isAutoStartup() == false`

Nếu một `SmartLifecycle` trả `false` ở `isAutoStartup()`, container không auto-start nó ở `refresh()` chỉ vì interface này. Component có thể được start bằng `context.start()` hoặc thao tác chủ động phù hợp.

Chỉ định `@Lazy` **không đảm bảo** `SmartLifecycle` auto-start không bị khởi tạo trong refresh. Lifecycle processor có thể cần phát hiện và khởi tạo các `SmartLifecycle` bean để quyết định auto-start; tài liệu Spring cảnh báo tác dụng lazy-init trên loại bean này khá hạn chế.

## 7. Ví dụ Java 17 chạy được: lifecycle chủ động và auto-start

Chương trình sau dùng Spring Framework 6.2.x thuần Java, không cần Spring Boot hoặc servlet. Nó đăng ký:

- `ManualWorker` implements `Lifecycle` và chỉ bắt đầu khi gọi `context.start()`.
- `AutoConsumer` implements `SmartLifecycle`, tự bắt đầu lúc refresh, phase 100.
- Hai component giữ trạng thái bằng `AtomicBoolean`, in log khi chuyển trạng thái.
- `stop(Runnable)` của `AutoConsumer` **luôn gọi callback sau khi đã dừng**.

### 7.1. Cấu trúc dự án

~~~text
spring-lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── lifecycle/
                        └── LifecycleDemo.java
~~~

### 7.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>spring-lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.lifecycle.LifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.3. `src/main/java/com/example/lifecycle/LifecycleDemo.java`

~~~java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.Lifecycle;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class LifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ManualWorker manual = context.getBean(ManualWorker.class);
            AutoConsumer auto = context.getBean(AutoConsumer.class);

            System.out.println("after refresh: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.start();
            System.out.println("after start: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.stop();
            System.out.println("after stop: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());

            context.start();
            System.out.println("after restart: manual=" + manual.isRunning()
                    + ", auto=" + auto.isRunning());
        } // close() dừng những component còn running.
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        ManualWorker manualWorker() {
            return new ManualWorker();
        }

        @Bean
        AutoConsumer autoConsumer() {
            return new AutoConsumer();
        }
    }

    public static class ManualWorker implements Lifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("manual.start");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("manual.stop");
            }
        }

        @Override
        public boolean isRunning() {
            return running.get();
        }
    }

    public static class AutoConsumer implements SmartLifecycle {
        private final AtomicBoolean running = new AtomicBoolean();

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public int getPhase() {
            return 100;
        }

        @Override
        public void start() {
            if (running.compareAndSet(false, true)) {
                System.out.println("auto.start");
            }
        }

        @Override
        public void stop() {
            if (running.compareAndSet(true, false)) {
                System.out.println("auto.stop");
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
            return running.get();
        }
    }
}
~~~

Cấu hình dùng `@Bean` trên các method trong `Config`; `ManualWorker` và `AutoConsumer` được đăng ký singleton mặc định. Hai class nested được khai báo `static` nên không phụ thuộc instance ngoài. Chương trình không tạo thread hay kết nối mạng, vì vậy log xác định và không có yếu tố tranh chấp bất đồng bộ.

### 7.4. Lệnh chạy và output

Yêu cầu JDK 17+ và Maven 3.9+. Từ thư mục `spring-lifecycle-demo` chạy:

~~~bash
mvn -q compile exec:java
~~~

Các dòng được in bởi `System.out.println` trong chương trình:

~~~text
auto.start
after refresh: manual=false, auto=true
manual.start
after start: manual=true, auto=true
auto.stop
manual.stop
after stop: manual=false, auto=false
manual.start
auto.start
after restart: manual=true, auto=true
auto.stop
manual.stop
~~~

Plugin Maven hoặc Spring logging có thể tạo thêm dòng log tùy cấu hình; các dòng trên chỉ là output chủ động của mã ví dụ.

**Tại sao đúng thứ tự đó?**

1. Tạo `AnnotationConfigApplicationContext(Config.class)` tự refresh context; `AutoConsumer` auto-start vì `SmartLifecycle.isAutoStartup() == true`. `ManualWorker` chưa chạy.
2. `context.start()` thấy `ManualWorker` chưa chạy, gọi `manual.start`. `AutoConsumer` đang chạy nên không start lại.
3. `context.stop()` ngừng những lifecycle bean đang chạy theo phase giảm dần: auto phase 100 trước, manual phase 0 sau.
4. `context.start()` lần hai start manual phase 0 trước, auto phase 100 sau.
5. `try-with-resources` đóng context và stop các component còn chạy: auto trước, manual sau.

Thứ tự này kiểm chứng khác biệt **refresh vs start**, **stop có thể restart**, và **phase của `SmartLifecycle`**.

### 7.5. Những giới hạn của ví dụ

Ví dụ chỉ quản lý flag để minh họa contract, không quản lý một worker thread thực tế. Khi production có nhiều thread:

- `start()` phải đảm bảo listener/loop đã sẵn sàng trước khi công bố running.
- `stop()` phải dừng nhận việc và xử lý những công việc đang chạy theo chính sách.
- `stop(Runnable callback)` chỉ gọi callback **sau khi shutdown thật sự hoàn tất**.
- Phải giải quyết race giữa start và stop; một `AtomicBoolean` riêng không tự quản lý trạng thái STARTING, STOPPING, FAILED và tài nguyên đang khởi tạo.
- Không sử dụng một thread daemon chạy vô hạn như cách “triển khai Lifecycle”.

## 8. `stop(Runnable callback)`: điều phối shutdown bất đồng bộ

Một `SmartLifecycle` có thể phải hoàn thành một quá trình dừng lâu hơn một lời gọi đồng bộ: ngừng nhận message, chờ task đang xử lý, đóng channel, flush buffer. `stop(Runnable callback)` cho phép lifecycle processor biết **khi nào component thực sự đã dừng**.

Đặc biệt:

- Với `SmartLifecycle`, `DefaultLifecycleProcessor` dùng overload **`stop(Runnable callback)`**; không đảm bảo sẽ tự gọi `stop()` không tham số.
- Nếu tự override `stop(Runnable callback)`, bạn phải thực hiện logic stop hoặc delegate tới `stop()`, rồi **gọi `callback.run()` khi đã dừng xong**.
- Nếu không override, default method của `SmartLifecycle` có thể delegate sang `stop()` và gọi callback ngay sau đó; chỉ phù hợp khi `stop()` xử lý hoàn tất đồng bộ.
- Bỏ quên callback có thể khiến lifecycle processor phải đợi đến timeout của phase, làm shutdown chậm hoặc không đúng thứ tự mong muốn.
- Không gọi callback **trước** khi resource thật sự dừng vì phase tiếp theo có thể bị đóng quá sớm.

Ví dụ minh họa cho một class triển khai `SmartLifecycle`, có executor chạy riêng và stop bất đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    executor.execute(() -> {
        try {
            stopAcceptingNewWork();
            awaitInFlightWork();
            releaseResources();
            running.set(false);
        } finally {
            callback.run();
        }
    });
}
~~~

Đây là **đoạn minh họa trong một class đã định nghĩa** các field/method `executor`, `stopAcceptingNewWork()`, `awaitInFlightWork()`, `releaseResources()`, `running`; không phải file Java chạy độc lập. Khi sử dụng thực tế phải bảo đảm executor dùng để chạy shutdown **vẫn còn hoạt động**, không bị dừng trước khi callback được submit. Phải xử lý trường hợp submit bị từ chối, cleanup ném exception, timeout, interrupt và điều kiện khi component đã dừng.

Nếu shutdown quá phức tạp, thiết kế một state machine riêng rõ ràng rồi cho `stop(Runnable)` điều phối theo state machine đó. Callback thuộc contract mà Spring dùng để xác nhận completion; cần được gọi đúng một lần trên mọi đường hoàn thành theo chính sách.

### Ví dụ dừng đồng bộ an toàn hơn cho phần lớn component

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Mẫu này gọi callback sau khi `stop()` trả về hoặc ném exception. Nó có thể phù hợp với shutdown đồng bộ, nhưng nếu `stop()` fail trước khi thực sự hoàn tất, phải xem xét cách thông báo trạng thái lỗi và cleanup; không được coi callback là bằng chứng hạ tầng đã dừng thành công trong mọi trường hợp. Một ứng dụng cần timeout/recovery phải quản lý trạng thái fail cụ thể.

## 9. Phase và dependency: bắt đầu hạ tầng trước consumer

Giả sử có hai thành phần:

- `ConnectionTransport` tạo/duy trì kênh liên lạc.
- `EventSubscriber` bắt đầu subscribe và nhận event trên kênh đó.

Nếu cả hai triển khai `SmartLifecycle`, muốn transport có trước consumer thì dùng phase:

~~~java
@Override
public int getPhase() {
    return -100; // ConnectionTransport: start sớm, stop muộn.
}
~~~

~~~java
@Override
public int getPhase() {
    return 100; // EventSubscriber: start muộn, stop sớm.
}
~~~

Đây là hai đoạn method minh họa thuộc **hai class khác nhau**. Thứ tự:

~~~text
Startup:   ConnectionTransport → EventSubscriber
Shutdown:  EventSubscriber → ConnectionTransport
~~~

Ngoài phase, nên khai báo **dependency thật** nếu consumer bắt buộc cần transport, chẳng hạn qua constructor injection:

~~~java
public EventSubscriber(ConnectionTransport transport) {
    this.transport = transport;
}
~~~

Dependency được Spring biết rõ ảnh hưởng tới thứ tự start/stop: dependent bean được start **sau** dependency và stop **trước** dependency, ngay cả khi phase khai báo có thể mâu thuẫn. Vì vậy:

1. Sử dụng **constructor injection** để biểu đạt dependency object.
2. Sử dụng **phase** để điều phối nhóm component cần thứ tự vận hành.
3. Tránh biến phase thành một hệ thống “đánh số thủ công” thiếu tài liệu về ai phụ thuộc ai.

Nếu cần bảo đảm hạ tầng **thực sự ready** sau `start()`, hãy xác định hợp đồng ready/health cụ thể, vì một method `start()` chỉ khởi động bất đồng bộ rồi trả ngay không nhất thiết cho thấy transport đã kết nối thành công.

## 10. Phân biệt `Lifecycle` với init và destroy callback

| Cơ chế | Thời điểm | Có thể chạy nhiều lần trong cùng context? | Mục đích |
| --- | --- | --- | --- |
| Constructor / factory method `@Bean` | Khi bean được tạo | Với prototype: mỗi instance mới; với singleton: thường một lần | Tạo object, gán dependency |
| `@PostConstruct` | Initialization của từng bean instance | Theo số lần bean instance được tạo | Chuẩn bị sau injection |
| `InitializingBean.afterPropertiesSet()` | Initialization của từng bean instance | Theo số instance | Xác thực/khởi tạo state nội bộ |
| Custom `@Bean(initMethod = "...")` | Initialization của từng bean instance | Theo số instance | Gọi init method cấu hình |
| `Lifecycle.start()` | Theo yêu cầu start/lifecycle processor | **Có**, có thể sau stop rồi restart | Bắt đầu vận hành |
| `Lifecycle.stop()` | Theo yêu cầu stop/lifecycle processor | **Có**, mỗi vòng start/stop | Ngừng vận hành |
| `@PreDestroy` / destroy method | Khi instance thực sự được Spring destroy | Thường cuối bean lifetime | Cleanup cuối vòng đời |

Một ứng dụng sai thường gọi worker `start()` trong `@PostConstruct` **và** khai báo bean `SmartLifecycle` auto-start. Điều này có thể làm worker bị start hai lần. Thay vào đó, init callback chỉ nên chuẩn bị cấu hình; lifecycle processor chịu trách nhiệm thời điểm start.

### Vì sao không dùng `@PreDestroy` thay `stop()`?

`@PreDestroy` chỉ là bước cleanup khi bean thực sự bị destroy. Trong khi đó `context.stop()` không destroy context; ứng dụng có thể **start lại** cùng bean instance. Một worker có stop/start nghiệp vụ cần `Lifecycle`, để không buộc destroy/tạo lại toàn bộ bean hoặc context chỉ vì tạm dừng nhận công việc.

Đối với prototype được trao cho caller, Spring không tự theo dõi để gọi destruction callback khi context đóng; việc dùng `Lifecycle` trên prototype cũng không tự biến nó thành một singleton lifecycle component được container điều phối giống các bean thường gặp. Thành phần nền cần start/stop theo context thường nên được thiết kế là singleton phù hợp.

## 11. Chọn `Lifecycle` hay `SmartLifecycle`?

### 11.1. Dùng `Lifecycle` khi start phải diễn ra chủ động

Ví dụ nhu cầu:

- Một ứng dụng chỉ bắt đầu polling khi người vận hành bật chức năng.
- Một nhóm worker được start theo điều kiện sau khi hệ thống cấp tài nguyên.
- Một component muốn hỗ trợ stop/start qua `context.start()`, `context.stop()` mà không auto-start lúc refresh.

Plain `Lifecycle` thường đủ nếu không yêu cầu phase đặc biệt, auto-start hoặc callback shutdown bất đồng bộ.

### 11.2. Dùng `SmartLifecycle` khi start là một phần của startup context

Ví dụ nhu cầu:

- Một consumer cần tự subscribe khi application context sẵn sàng.
- Hệ thống phải dừng consumer trước transport hoặc infrastructure.
- Có nhiều service cùng cần thứ tự theo phase.
- Component dừng bất đồng bộ và muốn báo completion có tổ chức.

Trường hợp này nên triển khai `SmartLifecycle` với trạng thái nhất quán, phase rõ ràng và callback chính xác.

### 11.3. Nếu chỉ cần đóng resource một lần khi context đóng

Một connection pool singleton có thể chỉ cần custom `destroyMethod` hoặc `AutoCloseable.close()`, **không nhất thiết cần `Lifecycle`**. Chỉ thêm giao thức start/stop khi component thật sự có thao tác vận hành chủ động, hỗ trợ pause/restart hoặc cần phối hợp shutdown.

## 12. Vòng đời thread, executor và message consumer

### 12.1. Không khởi động thread trong constructor nếu phải điều phối lifecycle

~~~java
public MessagePoller() {
    // Không nên tự start worker thread ở đây nếu muốn
    // Spring điều khiển thời điểm start/stop.
}
~~~

Đây là đoạn minh họa constructor. Nếu thread bắt đầu trước khi container hoàn tất injection và refresh, worker có thể chạy với dependency chưa ready. Nên tạo/chuẩn bị state ở constructor/init rồi start loop trong `start()` phù hợp.

### 12.2. Dừng nhận việc khác với hoàn tất việc đang chạy

Một consumer có thể có nhiều bước khi stop:

1. Ngừng polling/subscribe để **không nhận công việc mới**.
2. Đợi in-flight jobs hoàn tất trong giới hạn thời gian, hoặc chủ động cancel theo chính sách.
3. Commit/acknowledge các công việc hoàn tất nếu hạ tầng yêu cầu.
4. Đóng channel, socket hoặc tài nguyên do component sở hữu.
5. Cập nhật trạng thái `running` sau khi thực sự ngừng.
6. Nếu dùng `SmartLifecycle.stop(Runnable)`, gọi callback **sau khi hoàn tất**.

Lệnh `stop()` không phải chỉ là `running = false` khi còn thread đang sử dụng resource. Với long-running tasks, cần xử lý interrupt, timeout và executor shutdown để tránh dừng treo.

### 12.3. Resource ownership

Nếu `EventSubscriber` **mượn** một HTTP client hoặc connection pool singleton từ `ConnectionTransport`, subscriber thường nên ngừng subscription trước và không tự đóng pool chung. Transport hoặc owner thực sự sẽ đóng pool ở vòng đời của nó.

Một số lỗi shutdown phát sinh vì một component đóng dependency shared trước khi component khác ngừng sử dụng. Phase/dependency và ownership phải cùng phản ánh thứ tự shutdown mong muốn.

### 12.4. Thread-safety của trạng thái running

Nếu có thể gọi `start()`/`stop()` từ nhiều thread:

- `volatile boolean` hoặc `AtomicBoolean` có thể giúp công bố flag, nhưng **không biến toàn bộ start/stop thành atomic**.
- Có thể cần `synchronized`/lock/state machine để bảo vệ lifecycle nhiều bước.
- Phân biệt trạng thái `NEW`, `STARTING`, `RUNNING`, `STOPPING`, `STOPPED`, `FAILED` khi cần.
- Không để `isRunning()` trả `true` chỉ vì cờ bật nhưng listener tạo thất bại.
- Đảm bảo callback shutdown không bỏ sót trên nhánh lỗi.

Dùng giao thức Spring giúp container điều phối, nhưng **không tự làm implementation của bạn thread-safe**.

## 13. Lỗi: quên gọi callback shutdown

Đây là anti-pattern đối với `SmartLifecycle`:

~~~java
@Override
public void stop(Runnable callback) {
    stop();
    // Sai: không gọi callback.run().
}
~~~

Đoạn này thuộc class triển khai `SmartLifecycle`, không phải file độc lập. Spring có thể đợi phase shutdown đến timeout vì không nhận tín hiệu completion.

Sửa với shutdown đồng bộ:

~~~java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
~~~

Với shutdown bất đồng bộ, gọi callback **từ phía hoàn thành thực tế** thay vì ngay sau khi submit task. Không gửi callback sớm để “tránh timeout”: làm vậy đánh lừa lifecycle processor rằng consumer đã dừng và có thể khiến resource phụ thuộc bị đóng khi vẫn còn dùng.

## 14. Lỗi: nhầm phase âm và phase dương

Một số người đặt component “quan trọng” phase lớn để start sớm. Trong Spring lifecycle, điều này ngược ý định:

- `getPhase() = -100`: **start sớm**, **stop muộn**.
- `getPhase() = 100`: **start muộn**, **stop sớm**.

Phase không phải mức ưu tiên CPU hoặc thread priority; nó chỉ là **thứ tự điều phối lifecycle**. Phụ thuộc trực tiếp giữa bean có thể ảnh hưởng thứ tự ngoài phase.

Đừng dùng một số phase ngẫu nhiên mà không giải thích. Nên thiết lập hằng số nghiệp vụ, ví dụ `TRANSPORT_PHASE = -100` và `CONSUMER_PHASE = 100` trong cấu hình của chính hệ thống.

## 15. Lỗi: `SmartLifecycle` và `@Lazy`

Code:

~~~java
@Bean
@Lazy
SmartLifecycle consumer() {
    return new MyConsumer();
}
~~~

Đây là minh họa; cần các import Spring và class `MyConsumer` implement `SmartLifecycle`. Dễ nhầm rằng `@Lazy` bảo đảm consumer không bao giờ được tạo lúc startup. Tuy nhiên, `DefaultLifecycleProcessor` có thể phải khởi tạo những `SmartLifecycle` bean để auto-start; tài liệu Spring lưu ý cờ lazy-init có tác dụng rất hạn chế với nhóm này.

Nếu mục tiêu là **không chạy khi refresh**, cân nhắc `isAutoStartup() = false` cùng chính sách start chủ động, chứ không chỉ thêm `@Lazy`. Nếu mục tiêu là **không tạo bean cho đến khi thật sự được yêu cầu**, cần thiết kế lifecycle và cách đăng ký phù hợp, tránh phụ thuộc vào auto-start.

## 16. Lỗi: tự gọi `start()` trên một bean không được quản lý

~~~java
var worker = new PollingWorker();
worker.start();
~~~

Lời gọi Java này có thể hoạt động vì interface public, nhưng Spring không biết đây là bean để lifecycle processor điều phối, không inject các dependency của worker, cũng không tự gọi `stop()` khi context đóng. Nếu cần container quản lý, đăng ký bean bằng `@Bean` hoặc component scanning rồi truy xuất bean từ context.

Tương tự, các object được tạo động ngoài container hoặc prototype được cấp cho caller cần chính sách sở hữu vòng đời rõ ràng; context shutdown không tự truy tìm mọi object Java đang tồn tại.

## 17. Tương tác với Spring Boot

Trong ứng dụng Spring Boot, context cũng là một Spring `ApplicationContext`; `SmartLifecycle` có thể auto-start trong quá trình refresh. Nhưng **auto-start không phải lời đảm bảo rằng ứng dụng đã sẵn sàng nhận mọi request hoặc tất cả startup hook đã chạy**.

Hãy phân biệt:

| Cơ chế | Ý nghĩa |
| --- | --- |
| `@PostConstruct` | Initialization callback của một bean |
| `SmartLifecycle.start()` | Start theo lifecycle processor, thường trong refresh |
| `ApplicationRunner` / `CommandLineRunner` | Logic chạy sau khi application context đã tạo, thuộc quy trình startup của Spring Boot |
| `ApplicationReadyEvent` | Event Spring Boot khi ứng dụng hoàn thành các runner và chuẩn bị được xem là ready |
| `@PreDestroy` | Destruction callback khi bean bị destroy |

Không có một hook nào tự động thay thế mọi hook còn lại. Một consumer cần hoạt động ngay từ refresh có thể dùng `SmartLifecycle`; một công việc một lần sau khi Boot startup có thể hợp với runner. Nếu vận hành liên quan readiness probe của Kubernetes hoặc load balancer, cần xét chính sách readiness và việc dừng nhận traffic đồng bộ với shutdown.

Trong Spring Boot 3.3, cấu hình graceful shutdown của web server có cơ chế vòng đời riêng. Đừng tự đoán phase tích hợp của web server hoặc tự đóng server từ một lifecycle bean; dùng cơ chế framework hỗ trợ, và chỉ thêm component của ứng dụng khi có nhu cầu thực sự.

## 18. Cấu hình timeout shutdown phase

`DefaultLifecycleProcessor` cho phép cấu hình thời gian chờ shutdown của từng phase. Trong Spring 6.2.x, có API `setTimeoutPerShutdownPhase(long)`. Khi một `SmartLifecycle` dừng bất đồng bộ nhưng không gọi callback, lifecycle processor không thể biết nó đã hoàn tất, và việc chờ timeout có thể làm shutdown kéo dài.

Một cấu hình minh họa:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class LifecycleProcessorConfig {

    @Bean(name = "lifecycleProcessor")
    public DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor = new DefaultLifecycleProcessor();
        processor.setTimeoutPerShutdownPhase(10_000);
        return processor;
    }
}
~~~

Đây là **cấu hình ví dụ độc lập**. Không thêm cùng bean name nếu ứng dụng đã có lifecycle processor riêng; Spring context sử dụng bean với tên chuẩn `lifecycleProcessor` để điều phối.

Giá trị `10_000` thể hiện 10.000 ms = 10 giây cho mỗi shutdown phase, là một **ví dụ cấu hình**, không khẳng định mặc định của mọi phiên bản Spring.

Cần lưu ý:

1. Timeout shutdown không tự kill một thread hoặc đóng cưỡng bức mọi resource.
2. Phải đo thời gian hoàn tất thực tế và đặt timeout phù hợp với nghiệp vụ.
3. Callback vẫn phải chạy khi dừng xong, kể cả khi công việc cần đợi bất đồng bộ.
4. Tránh áp dụng một thời gian chờ quá dài cho tất cả phase mà không quan sát.
5. Khi shutdown bất thường hoặc JVM bị kill cưỡng bức, không thể bảo đảm lifecycle callbacks chạy.

## 19. Kiểm thử lifecycle chủ động

Ví dụ `LifecycleDemo` kiểm tra luồng phổ biến bằng stdout. Đối với test tự động, nên assert state và thứ tự event thay vì chỉ grep log:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(LifecycleDemo.Config.class)) {

    var manual = context.getBean(LifecycleDemo.ManualWorker.class);
    var auto = context.getBean(LifecycleDemo.AutoConsumer.class);

    if (manual.isRunning()) {
        throw new AssertionError("Manual worker should be stopped after refresh");
    }
    if (!auto.isRunning()) {
        throw new AssertionError("SmartLifecycle should auto-start");
    }

    context.start();
    if (!manual.isRunning()) {
        throw new AssertionError("Manual worker did not start");
    }

    context.stop();
    if (manual.isRunning() || auto.isRunning()) {
        throw new AssertionError("Lifecycle components did not stop");
    }
}
~~~

Đây là **đoạn chạy phụ** có thể đặt trong một method `main` hoặc test khác với dependency từ mục 7. Trong test case thực tế, thêm assertions cho idempotency (start khi đã running, stop khi đã stopped), phase ordering, failure path và callback shutdown bất đồng bộ. Không cần khởi chạy một server hoặc thread thật chỉ để test hợp đồng lifecycle cốt lõi.

### Kiểm thử stop callback bất đồng bộ

Với `SmartLifecycle.stop(Runnable)` tùy biến, nên thiết kế test có `CountDownLatch`:

1. Gọi lifecycle stop qua context.
2. Khi task nền báo hoàn tất, gọi callback.
3. Assert callback được gọi một lần.
4. Assert shutdown của phase phụ thuộc không xảy ra trước completion.
5. Dùng timeout hữu hạn để test không treo vô hạn khi implementation sai.

Lưu ý rằng việc test tính đồng thời bằng `Thread.sleep(...)` lâu hoặc phụ thuộc thứ tự thời gian ngẫu nhiên dễ gây flaky test. Dùng latch hoặc cơ chế đồng bộ xác định hơn.

## 20. Những vấn đề thường gặp khi vận hành

| Hiện tượng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| Implements `Lifecycle` nhưng component không chạy khi refresh | Plain `Lifecycle` không auto-start mặc định | Gọi `context.start()` hoặc cân nhắc `SmartLifecycle` |
| Implements `SmartLifecycle` nhưng vẫn không auto-start | `isAutoStartup() == false` hoặc bean không được context quản lý | Kiểm tra bean registration và flag auto-start |
| Worker khởi động hai lần | Gọi start trong `@PostConstruct` và để lifecycle processor start | Chọn một cơ chế start |
| Shutdown treo đến timeout | `stop(Runnable)` không gọi callback hoặc stop không hoàn tất | Luôn báo completion đúng lúc; kiểm tra executor và timeout |
| Consumer stop sau transport | Phase sai hoặc dependency được khai báo không đúng | Consumer phase cao hơn transport, dependency phải rõ |
| `@Lazy` consumer vẫn được tạo lúc refresh | `SmartLifecycle` cần được processor phát hiện và auto-start | Dùng `isAutoStartup()`/thiết kế khác thay vì chỉ `@Lazy` |
| Gọi `context.stop()` nhưng bean vẫn tồn tại | Stop chỉ ngừng vận hành, không destroy context | Gọi `close()` khi thật sự kết thúc vòng đời context |
| `isRunning()` true khi client chưa kết nối | Flag không phản ánh readiness thực | Quản lý STARTING/READY/FAILED rõ ràng |
| Stop đóng resource trong lúc task vẫn chạy | Thiếu drain/cancel/in-flight tracking | Dừng nhận việc, đợi/cancel hợp lý trước cleanup |
| Callback destroy không chạy trên worker tạo bằng `new` | Object không do Spring quản lý | Đăng ký bean hoặc quản lý ownership bằng Java |
| Spring shutdown nhưng process vẫn không thoát | User-created non-daemon thread/executor chưa dừng | Shutdown/interrupt/join đúng cách trong lifecycle |
| Lifecycle callback được gọi khi chưa đủ dependency vận hành | Coi `start()` là toàn bộ ứng dụng ready | Xác định contract readiness và thứ tự component |

## 21. Checklist thiết kế

Khi định nghĩa một thành phần cần start/stop, hãy trả lời:

- Thành phần có **công việc vận hành liên tục** cần khởi động/dừng không, hay chỉ cần initialization và destroy?
- Nó có nên **auto-start khi context refresh** không? Nếu có, `SmartLifecycle` thường phù hợp.
- Nó cần đứng ở phase nào và phụ thuộc vào component nào?
- `start()` có idempotent không? Nếu khởi động thất bại, trạng thái có trở lại nhất quán không?
- `stop()` có dừng nhận việc mới và hoàn tất/cancel việc đang chạy đúng chính sách không?
- Nếu dùng `stop(Runnable)`, callback có được gọi khi thực sự kết thúc không?
- Resource được đóng ở `stop()` hay chỉ ở destroy, và component có thể restart sau stop không?
- Các thao tác lifecycle có thể chạy đồng thời không, và state có được bảo vệ?
- Làm sao test start/stop/restart, phase ordering, failure và timeout mà không phụ thuộc log ngẫu nhiên?
- Có cần readiness/liveness khác với `isRunning()` không?

Một thiết kế đạt yêu cầu cho phép context **start → stop → start → close** mà không rò resource, không nhận việc sau stop và không khiến shutdown của các dependency diễn ra trước khi component hoàn tất công việc.

## 22. Câu hỏi kiểm tra kiến thức

**Câu 1.** Một bean implements `Lifecycle`, đăng ký singleton và được Spring tạo khi context refresh. Vì sao `isRunning()` vẫn có thể false?

**Trả lời:** Vì bean initialization không tự đồng nghĩa với lifecycle start. Plain `Lifecycle` không auto-start khi refresh theo cơ chế mặc định. `context.start()` hoặc một lời gọi start phù hợp mới chuyển component sang running.

**Câu 2.** Một bean implements `SmartLifecycle` trả `isAutoStartup() == true`. Khi nào nó thường bắt đầu?

**Trả lời:** Khi `ApplicationContext` refresh hoàn tất giai đoạn thích hợp và `LifecycleProcessor.onRefresh()` điều phối auto-start. Điều này không cần caller gọi `context.start()` thủ công.

**Câu 3.** Hai component A phase -10 và B phase 20, không có dependency rõ ràng. Thứ tự thường như thế nào?

**Trả lời:** Start A rồi B; stop B rồi A. Nếu giữa hai bean có dependency trực tiếp, dependency ordering có thể ưu tiên hơn phase.

**Câu 4.** `context.stop()` có tự hủy singleton và đóng context không?

**Trả lời:** Không. Nó yêu cầu lifecycle components dừng, context vẫn còn. `context.close()` mới thực hiện shutdown context và bean destruction theo chính sách.

**Câu 5.** Nếu `SmartLifecycle.stop(Runnable)` hoàn tất dừng nhưng không gọi `callback.run()`, tác hại là gì?

**Trả lời:** Lifecycle processor không nhận được tín hiệu completion, có thể phải chờ timeout của phase và làm trễ shutdown, ảnh hưởng thứ tự dừng các component khác.

**Câu 6.** Một singleton client chỉ cần `close()` khi ứng dụng tắt, không hỗ trợ pause/restart. Có bắt buộc implements `Lifecycle` không?

**Trả lời:** Không. Custom `destroyMethod`, `AutoCloseable` hoặc callback destruction phù hợp có thể đủ. `Lifecycle` chỉ hữu ích khi có hành vi vận hành chủ động.

**Câu 7.** Vì sao `@PostConstruct` không thích hợp để trực tiếp mở polling loop vô hạn?

**Trả lời:** Callback initialization cần hoàn thành để bean/context được khởi tạo đúng; một loop vô hạn sẽ chặn startup. Hãy chuẩn bị cấu hình lúc init và bắt đầu worker qua lifecycle, với cơ chế thread/executor và stop rõ ràng.

## 23. Tài liệu chính thức

- [Spring Framework 6.2 — `Lifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/Lifecycle.html): contract `start`, `stop` và `isRunning`.
- [Spring Framework 6.2 — `SmartLifecycle` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/SmartLifecycle.html): auto-start, phase, callback shutdown và mặc định của interface.
- [Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): điều phối phase, start/stop, refresh/close và timeout.
- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): phân biệt lifecycle callbacks và hành vi quản lý bean.
- [Spring Framework — `ConfigurableApplicationContext` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html): `refresh`, `start`, `stop`, `close` và contract context.
