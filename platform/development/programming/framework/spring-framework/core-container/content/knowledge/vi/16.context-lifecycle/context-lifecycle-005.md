# SmartLifecycle, autoStartup và thứ tự phase trong Spring Framework

## 1. Vấn đề: nhiều thành phần cần khởi động và dừng theo thứ tự

Spring IoC Container có thể quản lý các bean chỉ phục vụ tính toán thông thường như `PricingService`, `OrderRepository`, cùng các bean chủ động vận hành như consumer, scheduler, listener, bộ nhận thông điệp hoặc thành phần duy trì kết nối. Một bean chủ động vận hành thường phải **start** sau khi các dependency cần thiết đã sẵn sàng, và phải **stop** trước khi dependency đó bị dừng.

Ví dụ một pipeline:
- `ConnectionManager` phải được bật trước để mở khả năng sử dụng kết nối.
- `MessageConsumer` chỉ bắt đầu nhận thông điệp khi hạ tầng kết nối đã sẵn sàng.
- Khi tắt, consumer ngừng nhận thông điệp và hoàn tất phần đang xử lý, sau đó connection manager mới đóng.

Chỉ dùng constructor hoặc `@PostConstruct` để tạo thread và khởi động consumer dễ gây sai thứ tự: chúng chạy trong quá trình tạo **từng bean**, khi những thành phần khác có thể chưa hoàn tất vòng đời. `SmartLifecycle` cung cấp hợp đồng để Spring quản lý thao tác start/stop tại cấp ApplicationContext với **autoStartup**, **phase** và **callback dừng bất đồng bộ**.

### Các khái niệm cốt lõi

| Khái niệm | Ý nghĩa |
| --- | --- |
| `Lifecycle` | Interface cơ bản với `start()`, `stop()`, `isRunning()` |
| `SmartLifecycle` | Kế thừa `Lifecycle` và `Phased`, bổ sung `isAutoStartup()` và `stop(Runnable)` |
| `isAutoStartup()` | Có nên Spring tự start bean khi context refresh hay không |
| `getPhase()` | Giá trị nguyên quyết định nhóm và thứ tự start/stop |
| `LifecycleProcessor` | Infrastructure điều phối lifecycle của các bean |
| `DefaultLifecycleProcessor` | Implementation mặc định của Spring, hỗ trợ phase, dependency ordering và timeout khi stop |
| `ContextRefreshedEvent` | Event phát sau khi context refresh hoàn tất; thường sau khi auto-start lifecycle beans |
| `ContextStartedEvent` / `ContextStoppedEvent` | Event gắn với lệnh `context.start()` / `context.stop()` |
| `ContextClosedEvent` | Event khi context đóng; không đồng nghĩa gọi `stop()` lần nữa trên bean đã dừng |

**Ranh giới:** `SmartLifecycle` quản lý vòng đời bên trong **một Spring ApplicationContext**, không đồng bộ thứ tự giữa nhiều JVM/pod, không tự bảo đảm dependency bên ngoài đã healthy và không thay thế transaction hay concurrency control.

## 2. Hợp đồng SmartLifecycle trong Spring

Tên đầy đủ là `org.springframework.context.SmartLifecycle`. Nó kế thừa `Lifecycle` và `Phased`:

```java
// Chữ ký API giản lược để giải thích; đây không phải file định nghĩa lại Spring.
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}

public interface Phased {
    int getPhase();
}

public interface SmartLifecycle extends Lifecycle, Phased {
    boolean isAutoStartup();
    void stop(Runnable callback);
}
```

Đoạn trên mang tính mô tả interface; Spring hiện đại có **default methods** cho một số method trong `SmartLifecycle`. Không tự khai báo lại các interface này trong ứng dụng, hãy import interface chính thức. Một class implements `SmartLifecycle` nên thể hiện đầy đủ:

- `start()`: khởi động service, chuyển `isRunning()` sang `true` khi thực sự sẵn sàng theo hợp đồng của component. Nên idempotent: gọi lại khi đã chạy thì không tạo thread/consumer trùng.
- `stop()`: dừng đồng bộ khi caller gọi trực tiếp. Nếu đã dừng, thao tác không nên tạo side effect.
- `isRunning()`: trả trạng thái hiện tại đáng tin. Không giữ `true` mãi sau khi worker chết hoặc component đã stop.
- `isAutoStartup()`: mặc định là `true` theo Spring 6.2, có thể override thành `false` nếu muốn đợi tín hiệu start rõ ràng.
- `getPhase()`: mặc định `SmartLifecycle.DEFAULT_PHASE` (tương đương `Integer.MAX_VALUE` ở Spring 6.2); có thể override về một số nguyên phù hợp.
- `stop(Runnable callback)`: được `LifecycleProcessor` dùng để điều phối shutdown và cho phép dừng async. **Phải gọi `callback.run()` sau khi component thực sự stop**; với dừng đồng bộ có thể gọi ngay sau khi `stop()` hoàn tất.

`SmartLifecycle` cho phép quản lý **một component có vòng đời sống lâu**, ví dụ listener container hoặc message consumer. Nó không phải nơi tốt để thực thi một job nghiệp vụ “chạy đúng một lần toàn hệ thống” hoặc một method chỉ dùng để validate property.

### Tại sao phải có stop(Runnable)?

Nếu consumer cần đợi các message đang xử lý xong, dừng đồng bộ có thể giữ thread của Spring một thời gian dài. Spring cho phép `stop(Runnable)` bắt đầu quy trình ngừng nhận việc, rồi gọi callback khi đã giải phóng tài nguyên. `DefaultLifecycleProcessor` dùng callback để biết một phase đã hoàn tất và có thể chuyển sang phase tiếp theo theo thứ tự shutdown.

```text
Spring LifecycleProcessor
       |
       +-- stop(callback) trên consumer phase 100
                    |
                    +-- đánh dấu ngừng nhận message mới
                    +-- chờ các message đang xử lý hoàn tất
                    +-- đóng subscription
                    +-- cập nhật running=false
                    +-- callback.run()  <-- Spring biết đã stop xong
       |
       +-- sau khi phase 100 xong, dừng phase thấp hơn
```

**Không gọi callback quá sớm** khi component vẫn còn giữ connection/worker và làm các phase sau bị dừng trước. **Không quên gọi callback** khi stop hoàn tất, vì Spring sẽ tiếp tục chờ đến timeout của phase. Chỉ gọi callback một lần theo mỗi lần `stop(Runnable)` được yêu cầu.

## 3. autoStartup thực sự chạy vào lúc nào?

Trong một `ApplicationContext.refresh()` điển hình, Spring tạo các singleton thông thường ở `finishBeanFactoryInitialization()`, rồi trong `finishRefresh()` gọi `LifecycleProcessor.onRefresh()` để auto-start các `SmartLifecycle` phù hợp. Sau đó Spring phát `ContextRefreshedEvent`.

```text
context.refresh()
     |
     +-- BeanFactoryPostProcessors
     +-- BeanPostProcessors
     +-- tạo singleton thông thường, inject dependencies
     +-- @PostConstruct / InitializingBean / initMethod
     +-- SmartInitializingSingleton.afterSingletonsInstantiated()
     |
     +-- LifecycleProcessor.onRefresh()
     |       +-- auto-start SmartLifecycle beans nếu isAutoStartup()==true
     |       +-- tuân thủ phase và depends-on
     |
     +-- publish ContextRefreshedEvent
     +-- refresh() trả về
```

Thứ tự này giải thích vì sao tự khởi động ở `start()` của `SmartLifecycle` thường thích hợp hơn tự mở consumer trong constructor hoặc `@PostConstruct`. Trong `start()`, các regular singleton đã được tạo và initialization của chúng đã xong. Tuy vậy, không được suy ra rằng mọi lazy/prototype bean đã tạo, mọi database đã kết nối được, hay job async vừa khởi chạy đã sẵn sàng theo tiêu chí ứng dụng.

### isAutoStartup() == true

Đây là giá trị mặc định của `SmartLifecycle`. Khi context refresh thành công và lifecycle processor xử lý bean, Spring gọi `start()` cho bean chưa chạy. Không cần tự gọi `context.start()` để kích hoạt các auto-start components.

### isAutoStartup() == false

Bean không chủ động được Spring lựa chọn để auto-start chỉ vì refresh. Có thể bật sau bằng `context.start()`, hoặc gọi `start()` trên chính bean khi thiết kế phù hợp. **Ngoại lệ cần nhớ:** bean là dependency của một auto-start lifecycle component có thể vẫn được khởi động để đáp ứng quan hệ `depends-on`; vì vậy flag `false` không phải rào chắn tuyệt đối trong mọi đồ thị phụ thuộc.

`context.start()` chủ động yêu cầu start **tất cả lifecycle beans cần start**, bao gồm `SmartLifecycle` có `isAutoStartup()==false` và `Lifecycle` thông thường. Bean đã chạy không nên bị start trùng. `context.stop()` yêu cầu dừng các lifecycle beans đang chạy. Không nhầm `start()/stop()` với `refresh()/close()`: hai lệnh đầu không tạo lại bean definitions hay khởi tạo lại ApplicationContext.

| Hành động | Bean `SmartLifecycle(true)` | Bean `SmartLifecycle(false)` | Bean chỉ implement `Lifecycle` |
| --- | --- | --- | --- |
| Khi context refresh | Tự start (nếu không bị cản bởi dependency/lỗi) | Mặc định không auto-start | Không tự start |
| `context.start()` | Start nếu chưa chạy | Start nếu chưa chạy | Start nếu chưa chạy |
| `context.stop()` | Stop nếu đang chạy | Stop nếu đang chạy | Stop nếu đang chạy |
| `context.close()` | Stop trong quá trình đóng nếu còn chạy; destroy singleton | Tương tự nếu đang chạy; destroy | Tương tự |

Lưu ý về `@Lazy`: Spring cần phát hiện lifecycle beans để auto-start, nên một bean implements `SmartLifecycle` có thể bị tạo ngay trong pha startup dù bean definition khai báo lazy. Tài liệu Spring nói `@Lazy` thường có **tác dụng rất hạn chế** với `SmartLifecycle`. Nếu thật sự cần lazy-on-demand resource, phải chủ động thiết kế BeanFactory/loader và lifecycle phù hợp, không chỉ dựa vào `@Lazy`.

## 4. Quy tắc getPhase(): tăng dần khi start, giảm dần khi stop

`getPhase()` trả một `int`. Với các bean `SmartLifecycle` không có quan hệ `depends-on` ép thứ tự đặc biệt:

- **Khởi động:** phase **nhỏ hơn chạy trước** phase lớn hơn.
- **Dừng:** phase **lớn hơn dừng trước** phase nhỏ hơn.
- Hai component **cùng phase** không có thứ tự cố định theo contract; không giả định alphabetical order hoặc thứ tự `@Bean`.
- Phase có thể âm, 0 hoặc dương. Không cần dùng số liên tiếp.

```text
START (thấp -> cao):
    phase -100: connection
         |
    phase   0: base service
         |
    phase 100: message consumer
         |
    phase 200: serving endpoint

STOP (cao -> thấp):
    phase 200: serving endpoint
         |
    phase 100: message consumer
         |
    phase   0: base service
         |
    phase -100: connection
```

| Bean | Phase | Thứ tự start | Thứ tự stop |
| --- | ---: | ---: | ---: |
| ConnectionManager | -100 | 1 | 4 |
| BaseLifecycleService | 0 | 2 | 3 |
| MessageConsumer | 100 | 3 | 2 |
| IngressEndpoint | 200 | 4 | 1 |

Bảng giả định mọi bean đều được start và không có quan hệ `depends-on` đảo thứ tự. Tùy hạ tầng ứng dụng, bean có thể không cần chia nhiều phase; phase chỉ nên được phân tách khi thực sự có phụ thuộc lifecycle.

### Các default phase quan trọng

- `Lifecycle` thông thường (không implement `SmartLifecycle`) được lifecycle processor coi như có **phase 0**.
- `SmartLifecycle` ở Spring 6.2 có `DEFAULT_PHASE = Integer.MAX_VALUE`. Vì vậy nếu không override `getPhase()`, component SmartLifecycle mặc định thường khởi động muộn hơn `Lifecycle` phase 0 và dừng sớm hơn.
- Một số Spring infrastructure bean có default phase riêng, ví dụ một số executor/scheduler ở `Integer.MAX_VALUE / 2`. **Không mặc định tất cả infrastructure dùng phase 0 hoặc MAX_VALUE.**
- Trong Spring Boot/Web, web server, messaging container, scheduler, task executors có thể có lifecycle/phase riêng. Khi đặt phase tùy chỉnh, kiểm tra Javadoc và thứ tự dependency thực tế của phiên bản bạn triển khai.

Không dùng `@Order` như cách thay thế `getPhase()` để điều phối `SmartLifecycle`. `@Order` có thể điều khiển thứ tự injection collection hoặc một số sorting theo facility, nhưng lifecycle processor quản lý phase và `depends-on` theo hợp đồng của nó.

## 5. Quan hệ depends-on ưu tiên hơn phase

Spring cho phép khai báo dependency explicit, chẳng hạn `@DependsOn("connectionManager")` hoặc `@Bean` có `@DependsOn`. Khi hai lifecycle beans có quan hệ phụ thuộc, Spring ưu tiên:

- Bean A **phụ thuộc** bean B → B phải được **start trước** A.
- Khi dừng → A phải được **stop trước** B.

Điều này đúng dù các giá trị phase của chúng gợi ý thứ tự ngược. Ví dụ A phase -100 nhưng depends-on B phase 100: B vẫn cần chạy trước A để đáp ứng dependency.

```java
@Configuration(proxyBeanMethods = false)
class PipelineConfig {
    @Bean("connectionManager")
    SmartLifecycle connectionManager() {
        return new ConnectionManager();
    }

    @Bean("messageConsumer")
    @DependsOn("connectionManager")
    SmartLifecycle messageConsumer() {
        return new MessageConsumer();
    }
}
```

Đây là mã mô tả cấu hình, **chưa chạy độc lập** vì `ConnectionManager`, `MessageConsumer` chưa được định nghĩa và thiếu imports Spring. Phần cần nắm là ý nghĩa `@DependsOn`, không phải các giá trị phase trong các class chưa có ở đây.

Phân biệt:
- Constructor dependency như `MessageConsumer(ConnectionManager manager)` bảo đảm **instance manager được tạo trước** khi consumer được tạo.
- `@DependsOn` thể hiện dependency cho container và có ảnh hưởng đến **lifecycle ordering**, không chỉ thứ tự tạo.
- `getPhase()` thể hiện quan hệ trật tự giữa **nhóm** component, rất hữu ích khi không có dependency trực tiếp hoặc nhiều component cùng loại cần bật trước.
- Nếu A phải đợi B không chỉ “start đã được gọi” mà còn **thực sự nhận kết nối khỏe mạnh**, hãy thiết kế readiness handshake rõ; chỉ sắp xếp phase không chứng minh external service khỏe.

## 6. Ví dụ Spring Core hoàn chỉnh (Java 17+): autoStartup và phase

Ví dụ này chạy bằng **Java 17+, Maven 3.9+ và Spring Framework 6.2.19**, không cần Spring Boot, servlet hoặc DB. Ba bean implements `SmartLifecycle` có phase -100, 100 và 200. Hai bean đầu auto-start khi refresh; bean thứ ba `isAutoStartup() == false` và chỉ bắt đầu khi code gọi `context.start()`. Tất cả stop theo phase đảo ngược.

### Cấu trúc thư mục

```text
smart-lifecycle-demo/
├── pom.xml
└── src/main/java/edu/example/lifecycle/
    ├── AppConfig.java
    ├── PhaseComponent.java
    ├── ContextEvents.java
    └── Main.java
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.example</groupId>
    <artifactId>smart-lifecycle-demo</artifactId>
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
                <version>3.5.0</version>
                <configuration>
                    <mainClass>edu.example.lifecycle.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/java/edu/example/lifecycle/PhaseComponent.java**

```java
package edu.example.lifecycle;

import org.springframework.context.SmartLifecycle;

public final class PhaseComponent implements SmartLifecycle {
    private final String name;
    private final int phase;
    private final boolean autoStartup;
    private volatile boolean running;

    public PhaseComponent(String name, int phase, boolean autoStartup) {
        this.name = name;
        this.phase = phase;
        this.autoStartup = autoStartup;
    }

    @Override
    public int getPhase() {
        return phase;
    }

    @Override
    public boolean isAutoStartup() {
        return autoStartup;
    }

    @Override
    public synchronized void start() {
        if (running) {
            return; // Chống start trùng.
        }
        // Ví dụ chỉ đổi cờ. Production phải start resource thật.
        running = true;
        System.out.println("start " + name + " phase=" + phase);
    }

    @Override
    public synchronized void stop() {
        if (!running) {
            return;
        }
        // Production phải stop resource trước khi cập nhật running.
        running = false;
        System.out.println("stop " + name + " phase=" + phase);
    }

    @Override
    public void stop(Runnable callback) {
        try {
            stop(); // Dừng đồng bộ trong ví dụ này.
        } finally {
            callback.run(); // Báo đã hoàn tất cho LifecycleProcessor.
        }
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
```

Ví dụ dùng `volatile` bảo đảm các thread đọc trạng thái `running` thấy cập nhật; `synchronized` ngăn hai lời gọi start/stop trùng lặp trong class tối giản. Nó không đại diện cho cách điều phối một consumer async phức tạp. Với production, chỉ đặt `running=true` sau khi resource **thực sự start**, và chỉ báo stop hoàn tất khi đã drain/close xong.

**src/main/java/edu/example/lifecycle/AppConfig.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AppConfig {
    @Bean("infrastructure")
    public PhaseComponent infrastructure() {
        return new PhaseComponent("infrastructure", -100, true);
    }

    @Bean("worker")
    public PhaseComponent worker() {
        return new PhaseComponent("worker", 100, true);
    }

    @Bean("manual")
    public PhaseComponent manual() {
        return new PhaseComponent("manual", 200, false);
    }

    @Bean
    public ContextEvents contextEvents() {
        return new ContextEvents();
    }
}
```

**src/main/java/edu/example/lifecycle/ContextEvents.java**

```java
package edu.example.lifecycle;

import org.springframework.context.ApplicationListener;
import org.springframework.context.event.ApplicationContextEvent;
import org.springframework.context.event.ContextClosedEvent;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.ContextStartedEvent;
import org.springframework.context.event.ContextStoppedEvent;

public final class ContextEvents
        implements ApplicationListener<ApplicationContextEvent> {

    @Override
    public void onApplicationEvent(ApplicationContextEvent event) {
        if (event instanceof ContextRefreshedEvent) {
            System.out.println("event: refreshed");
        } else if (event instanceof ContextStartedEvent) {
            System.out.println("event: started");
        } else if (event instanceof ContextStoppedEvent) {
            System.out.println("event: stopped");
        } else if (event instanceof ContextClosedEvent) {
            System.out.println("event: closed");
        }
    }
}
```

**src/main/java/edu/example/lifecycle/Main.java**

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class Main {
    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        context.register(AppConfig.class);

        try {
            context.refresh();

            PhaseComponent infra =
                    context.getBean("infrastructure", PhaseComponent.class);
            PhaseComponent worker =
                    context.getBean("worker", PhaseComponent.class);
            PhaseComponent manual =
                    context.getBean("manual", PhaseComponent.class);

            System.out.println("after refresh: infra=" + infra.isRunning()
                    + ", worker=" + worker.isRunning()
                    + ", manual=" + manual.isRunning());

            context.start();
            System.out.println("after start: manual=" + manual.isRunning());

            context.stop();
            System.out.println("after stop: infra=" + infra.isRunning()
                    + ", worker=" + worker.isRunning()
                    + ", manual=" + manual.isRunning());
        } finally {
            context.close();
        }

        System.out.println("after close: active=" + context.isActive());
    }
}
```

Chạy từ thư mục có `pom.xml`:

```bash
mvn -q compile exec:java
```

**Output từ `System.out.println` của chương trình:**

```text
start infrastructure phase=-100
start worker phase=100
event: refreshed
after refresh: infra=true, worker=true, manual=false
start manual phase=200
event: started
after start: manual=true
stop manual phase=200
stop worker phase=100
stop infrastructure phase=-100
event: stopped
after stop: infra=false, worker=false, manual=false
event: closed
after close: active=false
```

Các log do Maven hoặc logging framework có thể khác theo môi trường; những dòng ở trên do chính chương trình in ra. Kết quả được xác định vì ba phase khác nhau, không có `depends-on` và không tạo thêm lifecycle component custom nào. Trong `finishRefresh()`, container đã tạo các singleton và gọi auto-start cho infrastructure (-100), worker (100); manual (200) có `autoStartup=false` nên chưa chạy. Event refresh xuất hiện **sau** khi auto-start hoàn tất.

Lệnh `context.start()` làm manual bắt đầu, còn infrastructure/worker đang chạy nên `start()` không được chạy lại. Lệnh `context.stop()` gọi shutdown theo phase **200 → 100 → -100**, và ví dụ `stop(Runnable)` gọi callback ngay khi stop đồng bộ hoàn thành. Sau khi cả ba đã stop, `context.close()` phát `ContextClosedEvent`; không cần in stop thêm lần nữa. `isActive()` là `false` sau close.

**Kiểm chứng:** Thay `context.start()` bằng không làm gì thì manual vẫn `false`; nó sẽ không được stop nếu chưa chạy. Thử chỉnh worker phase thành -200: worker sẽ start trước infrastructure, cho thấy vì sao đặt phase phải gắn với dependency thực tế. Không nên bắt production consumer start trước hạ tầng kết nối chỉ để “kiểm tra”.

## 7. stop(Runnable): dừng bất đồng bộ đúng hợp đồng

Ví dụ ở trên dừng đồng bộ, vì vậy `stop(Runnable)` có thể gọi `stop()` rồi `callback.run()`. Với một subscriber cần drain message queue, cách khác là dừng bất đồng bộ và gọi callback **sau khi thực sự xong**:

```java
@Override
public void stop(Runnable callback) {
    // PSEUDOCODE: taskExecutor và consumer là dependency có thật
    consumer.stopAcceptingNewMessages();

    taskExecutor.execute(() -> {
        try {
            consumer.awaitInFlightTasks();
            consumer.close();
            running = false;
        } finally {
            callback.run();
        }
    });
}
```

Đây là **pseudocode API minh họa**, không phải một class độc lập chạy được; `consumer`, `taskExecutor` và `running` phải được định nghĩa, `awaitInFlightTasks()` không phải API Spring mặc định. Mục đích: callback phải được gọi khi stop thực tế đã hoàn tất (kể cả khi xử lý lỗi theo chính sách của component), và không được gọi trước khi async task chạy xong. Trong mã production, cần xử lý cả trường hợp `taskExecutor.execute` từ chối task hoặc shutdown bị hủy để không bỏ sót callback và báo lỗi hợp lý.

Một phương án vững hơn cho shutdown async cần làm rõ:
1. Ngay lúc nhận stop, **ngừng nhận việc mới**.
2. Giữ trạng thái “stopping” để không nhận yêu cầu start trùng gây race.
3. Cho việc đang xử lý cơ hội hoàn thành theo deadline chính sách.
4. Đóng connection/subscription theo thứ tự an toàn.
5. Cập nhật `isRunning()` về `false` sau khi release resource.
6. Gọi callback đúng một lần ngay khi đã hoàn tất, kể cả nhánh lỗi đã cleanup.

`DefaultLifecycleProcessor` chờ các callback của một phase theo timeout. Nếu một component không gọi callback, Spring có thể log warning và tiếp tục theo chính sách của processor sau timeout; không xem sự kiện “context đã đóng” là bảo đảm mọi tài nguyên riêng đã được dọn sạch. Khi chạy nhiều bean cùng phase, callback hỗ trợ stop song song **về mặt điều phối**, nhưng thời điểm thực thi cụ thể còn phụ thuộc implementation và công việc dừng.

## 8. Timeout theo phase và cấu hình LifecycleProcessor

`DefaultLifecycleProcessor` là processor mặc định cho context phổ biến. Spring Framework **6.2** có default timeout **10 giây cho mỗi shutdown phase**, còn tài liệu của phiên bản khác có thể dùng giá trị khác (chẳng hạn Spring Framework 7.x ghi 30 giây). Vì vậy luôn kiểm tra Javadoc đúng **version** khi muốn kiểm soát thời gian dừng.

Có thể đăng ký bean tên `lifecycleProcessor` để ghi đè processor mặc định, hoặc dùng config extension cho phiên bản phù hợp. Ví dụ cấu hình bean processor với timeout:

```java
package edu.example.lifecycle;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.DefaultLifecycleProcessor;

@Configuration(proxyBeanMethods = false)
public class LifecycleTimeoutConfig {
    @Bean(name = "lifecycleProcessor")
    public DefaultLifecycleProcessor lifecycleProcessor() {
        DefaultLifecycleProcessor processor =
                new DefaultLifecycleProcessor();
        processor.setTimeoutPerShutdownPhase(20_000L);
        return processor;
    }
}
```

Đây là **file cấu hình tùy chọn**, không thuộc project runnable mục 6 trừ khi bạn chủ động đăng ký `LifecycleTimeoutConfig`; method `setTimeoutPerShutdownPhase(long)` có trong Spring Framework 6.2. Một số phiên bản cũng có API đặt timeout riêng theo phase, ví dụ `setTimeoutForShutdownPhase(int, long)` trong 6.2. Chỉ định timeout dựa trên deadline yêu cầu của ứng dụng và môi trường triển khai, không chỉ trên giá trị mặc định.

Nếu container deployment gửi SIGTERM và có termination grace period, thời gian shutdown thực tế cần vừa đủ cho tổng thời gian dừng các phase, callback và các thành phần khác. Config timeout bên trong Spring **không kéo dài** thời hạn process bị orchestration layer kill.

Không sửa `lifecycleProcessor` của ứng dụng đang chạy chỉ để thay timeout mà không hiểu thứ tự Spring đăng ký infrastructure; cấu hình processor phải có sẵn đúng thời điểm trong context.

## 9. Sự khác biệt giữa start/stop và init/destroy

Một lỗi phổ biến là dùng `@PostConstruct` để khởi chạy một thread và `@PreDestroy` để dừng nó, rồi giả định đã có phase ordering. Thực tế:

| Cơ chế | Khi kích hoạt | Công việc phù hợp |
| --- | --- | --- |
| Constructor | Khi bean được tạo | Thiết lập invariant và required dependencies |
| `@PostConstruct` | Sau injection của bean đó | Validate config, tạo immutable index, chuẩn bị resource nhẹ |
| `SmartInitializingSingleton` | Sau eager regular singleton pre-instantiation | Kiểm tra tổng hợp/registry các bean đã tạo |
| `SmartLifecycle.start()` | Trong auto-start ở refresh hoặc explicit start | Bắt đầu component chạy dài: consumer, listener, polling |
| `SmartLifecycle.stop(Runnable)` | Context stop/close qua lifecycle processor | Graceful shutdown có callback hoàn tất |
| `@PreDestroy` | Khi destroy bean theo scope/container | Dọn resource cuối vòng đời |
| `ContextRefreshedEvent` | Khi context refresh thành công | Nhận sự kiện context-level |
| `ApplicationRunner` (Spring Boot) | Trong quy trình startup của Boot sau context refresh | Startup logic cấp ứng dụng |

Một component có thể đồng thời có `@PostConstruct` và `SmartLifecycle`, nhưng trách nhiệm nên tách rõ:

```text
constructor:
    nhận dependencies
@PostConstruct:
    validate và chuẩn bị cấu hình (chưa start consumer)
SmartLifecycle.start():
    kết nối/subscribe/start processing
SmartLifecycle.stop(callback):
    ngừng nhận việc, drain, close, callback
@PreDestroy:
    dọn trạng thái/tài nguyên còn lại nếu có
```

Có thể thiết kế `stop()` idempotent và `@PreDestroy` gọi cleanup dự phòng; tránh resource đóng hai lần gây lỗi. Không nên dùng `@PreDestroy` như phương tiện duy nhất để dừng consumer nếu cần phase ordering và graceful draining.

### Vì sao lifecycle phase quan trọng ở shutdown?

Khi stop consumer phase 100 trước connection phase -100, consumer có cơ hội hoàn tất các message đang xử lý trong lúc connection vẫn còn. Nếu đảo phase, connection ngắt trước và consumer có thể lỗi giữa shutdown. Phase là cách khai báo **quan hệ thời gian**; nếu còn dữ liệu tồn đọng, chính code consumer vẫn phải bảo đảm ACK, retry, idempotency và các invariant của hệ thống.

## 10. Những trường hợp đặc biệt cần hiểu

### 10.1. Same phase không cam kết thứ tự

Nếu hai bean đều `getPhase() == 50`, Spring không cam kết A start trước B trong hợp đồng API, dù trên máy dev bạn thấy luôn A trước. Nếu thực sự có dependency, dùng explicit `depends-on` hoặc tách phase.

### 10.2. @DependsOn làm thay đổi thứ tự phase

Đây là quan hệ có **ưu tiên cao hơn** số phase. Không tạo vòng `A depends-on B` và `B depends-on A`. Nếu phase A thấp hơn B nhưng A cần B để start, hãy cân nhắc sửa phase thể hiện đúng logic, dù framework vẫn có thể ưu tiên depends-on.

### 10.3. @Lazy trên SmartLifecycle

`@Lazy` thường không ngăn lifecycle processor instantiate bean `SmartLifecycle` khi cần xem auto-start. Không dùng lazy flag làm thay thế `isAutoStartup()`. Nếu bean tự động start có dependency nặng, cân nhắc thiết kế khởi tạo phân pha rõ ràng thay vì mong bean không được tạo.

### 10.4. Một SmartLifecycle bean chạy cùng nhiều ApplicationContext

Mỗi context có vòng đời riêng. Parent/child contexts có thể khởi động và đóng riêng; không mặc định `SmartLifecycle` ở child điều phối lifecycle của root và ngược lại. Không gắn các external singleton thật sự global vào nhiều context rồi cho từng context cùng stop resource.

### 10.5. Auto-start không có nghĩa server “ready”

`LifecycleProcessor.onRefresh()` thường chạy trước `ContextRefreshedEvent`. Nó là mốc yêu cầu start theo contract, không tự ping database/Kafka hay kiểm chứng consumer đã gắn subscription nếu `start()` chỉ mở async task rồi trả ngay. Nếu cần readiness thật, expose health/readiness signal của component, đợi handshake có timeout hợp lý, và cập nhật health indicator.

### 10.6. Thread safety của trạng thái running

`isRunning()` có thể được thread khác gọi với `start()/stop()`. Nếu có concurrency thực, dùng `volatile`/`AtomicBoolean`, lock hoặc state machine rõ ràng. Một cờ `volatile boolean running` giải quyết visibility cho cờ nhưng **không** đảm bảo toàn bộ start/stop của socket/thread là atomic; phải bảo vệ chuỗi bước phức tạp.

### 10.7. Spring Boot và infrastructure phase

Spring Boot/web server, message listener containers, schedulers và executors có thể implement `SmartLifecycle` với phase cụ thể. Việc can thiệp vào phase của custom bean có thể khiến worker nhận traffic trước khi dependency khởi động, hoặc dừng sau khi executor cần thiết đã bị đóng. Kiểm tra tài liệu đúng version của từng component, đặt thứ tự thể hiện dependency thực.

### 10.8. Restart bằng context.start() sau context.stop()

Với một context **chưa đóng**, `context.stop()` rồi `context.start()` có thể điều khiển lại những bean implement `Lifecycle` nếu logic `start/stop` của chúng thực sự hỗ trợ restart. Spring không tự tạo lại bean khi start lần hai. Nếu code component đã đóng một resource **không thể reopen**, `start()` cần chủ động tạo resource mới hoặc contract phải ghi rõ không restartable.

### 10.9. Bean chưa từng start

Nếu `isAutoStartup=false` và không ai gọi `start()`, Spring không cần gọi stop callback cho một bean không chạy theo quản lý vòng đời thông thường. Nhưng bean singleton đó vẫn có thể nhận destruction callback khi context đóng (nếu có). Đừng đặt cleanup quan trọng **chỉ** trong stop callback mà giả định bean luôn được start.

## 11. Cách kiểm tra thứ tự lifecycle thực tế

Một bài integration test có thể giữ danh sách event thread-safe, đăng ký ba lifecycle components với phase khác nhau rồi chạy `context.refresh()`, `context.start()`, `context.stop()`. Kiểm tra:

- Sau refresh, auto-start=true bean đang chạy; false bean chưa chạy (nếu không có dependency ép start).
- Các dấu start của phase thấp xuất hiện trước phase cao.
- Sau explicit `start()`, bean false có thể chuyển sang running.
- Khi stop, các phase lớn kết thúc **trước** phase nhỏ; với async stop phải dùng completion callback/latch thay vì chỉ đánh dấu đã gọi `stop`.
- Sau close, context inactive và tài nguyên được giải phóng, không có thread lạ còn chạy.
- Đặt timeout hợp lý để test fail rõ khi một callback bị quên.

Không dùng `Thread.sleep(100)` để đoán rằng shutdown xong. Dùng synchronization primitives như `CountDownLatch`/`Future` và một deadline cụ thể. Khi test async stop, cần bảo đảm callback chỉ được gọi sau khi trạng thái thật đã chuyển sang stop, vì Spring có thể chuyển sang phase kế tiếp ngay khi callback chạy.

Với production observability, log trường `component`, `phase`, `action=start|stop`, `elapsedMs` và `outcome`; đừng chỉ xem thứ tự câu lệnh trong source. Những logs này giúp phân biệt lỗi khi tạo bean, chậm start, timeout stop hoặc resource bị kill bởi orchestration layer.

## 12. Lỗi phổ biến và cách sửa

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Consumer start ngay lúc refresh dù không gọi `context.start()` | `SmartLifecycle.isAutoStartup()` mặc định `true` | Override `isAutoStartup()` thành `false` nếu muốn khởi động explicit |
| `@Lazy` bean vẫn được tạo lúc startup | Lifecycle processor có thể khởi tạo SmartLifecycle để auto-start | Không dùng lazy như công tắc start; thiết kế lifecycle riêng |
| Resource phụ thuộc chưa chạy khi consumer start | Phase bị đảo hoặc thiếu dependency relationship | Phase của dependency thấp hơn; khai báo `depends-on` khi phù hợp |
| Stop connection trước consumer | Shutdown phase sắp sai | Consumer phase cao hơn connection để stop trước |
| Context close dừng chậm đến timeout | `stop(Runnable)` quên gọi callback hoặc chưa shutdown hoàn thành | Gọi callback đúng một lần sau completion, xử lý cả nhánh lỗi |
| Callback chạy nhưng task chưa drain | Gọi callback ngay sau khi schedule async shutdown | Gọi trong completion handler sau khi resource thực sự dừng |
| Cùng phase chạy thứ tự không ổn định | API không cam kết thứ tự trong cùng phase | Tách phase hoặc khai báo dependency |
| `@Order` không điều khiển lifecycle | LifecycleProcessor dùng phase/depends-on | Override `getPhase()` |
| Đóng context rồi gọi `start()` | Context đã kết thúc vòng đời | Tạo context mới; quản lý start/stop trước khi close |
| `isRunning()` luôn false dù đã start | Không cập nhật hoặc không publish state đúng | Đồng bộ trạng thái, phản ánh resource thật |
| Calling `stop()` trực tiếp rồi quên callback | Caller trực tiếp gọi overload khác với lifecycle processor | Implement cả `stop()` và `stop(Runnable)` nhất quán |
| Context refresh hoàn thành nhưng external broker unavailable | start có thể trả về trước handshake, hoặc hệ thống bên ngoài hỏng | Định nghĩa readiness riêng, retry/backoff/timeout |
| Một bean chạy nhiều lần ở nhiều pod | Mỗi context có lifecycle độc lập | Dùng coordination phân tán nếu logic chỉ được phép một instance |
| Shutdown không đủ thời gian để drain | Timeout Spring hoặc SIGTERM grace period quá ngắn | Cấu hình shutdown deadline nhiều tầng và tiêu chí dừng |

## 13. Tự kiểm tra và bài tập thiết kế

1. Một `SmartLifecycle` không override `isAutoStartup()`. Trong `ApplicationContext.refresh()` bình thường, nó được start tự động hay đợi `context.start()`?
2. Có bean A phase -20 và B phase 30, không có dependency explicit. Thứ tự start và stop là gì?
3. Vì sao `SmartLifecycle.DEFAULT_PHASE` trong Spring 6.2 đặt ở `Integer.MAX_VALUE` có tác dụng với `Lifecycle` phase 0?
4. Nếu cả A và B cùng phase 100, Spring có bảo đảm A start trước B không?
5. Nếu A `depends-on` B nhưng A có phase -100, B có phase 100 thì thứ tự khởi động nên hiểu thế nào?
6. Bean `isAutoStartup()==false` có thể start khi `context.start()` được gọi không?
7. Nếu một bean `@Lazy` implements `SmartLifecycle`, có thể đảm bảo bean không bị tạo trong startup bằng `@Lazy` không?
8. `stop(Runnable)` được gọi khi đang drain 10 message. Có thể gọi callback ngay khi bắt đầu drain không?
9. Một consumer phase 200 dùng ConnectionManager phase -100. Khi shutdown, bean nào dừng trước?
10. `@PostConstruct` khác `SmartLifecycle.start()` ở mốc lifecycle và mục đích thế nào?
11. `context.stop()` và `context.close()` khác nhau ở chỗ nào?
12. Làm sao kiểm chứng async stop thực sự hoàn tất trước khi Spring chuyển sang dừng phase thấp hơn?
13. Nếu một Spring Boot ứng dụng có ba replica, một bean `SmartLifecycle` auto-start chạy bao nhiêu lần tổng cộng?
14. Khi nào timeout per phase 10 giây của Spring Framework 6.2 có thể không đủ?
15. Nếu listener container `start()` chỉ enqueue một tác vụ async rồi trả về, có thể suy ra broker đã ready không?

**Đáp án gợi ý:** (1) Tự start vì mặc định true. (2) Start A→B; stop B→A. (3) Default SmartLifecycle thường start sau Lifecycle 0 và stop trước Lifecycle 0. (4) Không. (5) Dependency B trước A, quan hệ depends-on ưu tiên. (6) Có. (7) Không bảo đảm, lazy có tác dụng hạn chế. (8) Không; callback sau khi drain/close hoàn tất. (9) Consumer 200 dừng trước manager -100. (10) PostConstruct thuộc init một bean; SmartLifecycle điều phối start/stop của component sau bootstrap. (11) Stop không destroy context; close kết thúc context và destroy singletons. (12) Dùng callback/latch cùng invariant tài nguyên thật, kiểm tra phase kế tiếp chỉ tiến sau completion. (13) Thường ba lần, mỗi context/pod một lần, trừ cấu hình riêng. (14) Khi có task dài, nhiều consumer hoặc transport drain chậm; điều chỉnh timeout và grace period. (15) Không, cần readiness thực và kiểm tra external system.

## Tài liệu chính thức

- Spring Framework 6.2 — `SmartLifecycle` Javadoc (default auto-start/phase, depends-on, stop callback): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/SmartLifecycle.html
- Spring Framework 6.2 — `DefaultLifecycleProcessor` Javadoc (phase ordering, shutdown timeout): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html
- Spring Framework — Customizing the Nature of a Bean (Lifecycle và SmartLifecycle): https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — `Lifecycle` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/Lifecycle.html
- Spring Framework — `ConfigurableApplicationContext` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/ConfigurableApplicationContext.html
- Spring Framework — `ContextRefreshedEvent`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
