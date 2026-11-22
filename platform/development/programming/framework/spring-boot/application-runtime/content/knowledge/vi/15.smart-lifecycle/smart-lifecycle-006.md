# Thứ tự dừng ngược lại và quan hệ phụ thuộc `depends-on` trong `SmartLifecycle`

## 1. Mục tiêu: dừng an toàn các thành phần có quan hệ phụ thuộc

Một ứng dụng Spring Boot thường có nhiều thành phần chạy trong suốt vòng đời process:

- Một **transport** mở kết nối hoặc tiếp nhận bản tin.
- Một **consumer** đọc bản tin qua transport và xử lý công việc.
- Một **scheduler** tạo job định kỳ.
- Một **publisher** dùng connection pool để gửi kết quả.
- Một **health/monitoring component** theo dõi trạng thái của các thành phần khác.

Lúc khởi động, ta thường muốn tài nguyên nền tảng sẵn sàng **trước** thành phần sử dụng nó: mở transport trước rồi mới chạy consumer. Lúc tắt ứng dụng, trình tự an toàn phải **ngược lại**: ngừng consumer trước để nó không phát sinh công việc mới, sau đó mới đóng transport. Nếu đóng transport quá sớm, consumer có thể gặp lỗi kết nối, mất bản tin hoặc không hoàn tất tác vụ đang chạy.

Spring Framework cung cấp `Lifecycle`, `Phased` và đặc biệt là `SmartLifecycle` để các bean phối hợp việc **start/stop**. Có hai quy tắc quan trọng:

1. **Quy tắc phase:** khi khởi động, phase **thấp hơn khởi động trước**; khi dừng, phase **cao hơn dừng trước**.
2. **Quy tắc phụ thuộc `depends-on`:** nếu bean `consumer` phụ thuộc vào bean `transport`, Spring phải **start `transport` trước `consumer`**, đồng thời **stop `consumer` trước `transport`**, kể cả khi phase của chúng gợi ý thứ tự khác.

Vì vậy, “dừng theo thứ tự ngược lại” không đơn thuần là lật ngược một danh sách bean tình cờ. Đây là quá trình do `LifecycleProcessor` điều phối, kết hợp phase và quan hệ phụ thuộc mà `BeanFactory` biết.

Bài này dùng khái niệm và API trong **Spring Framework 6.x / Spring Boot 3.x**, với ví dụ **Java 17+**.

## 2. Ba interface cần phân biệt

### 2.1. `Lifecycle`: biết bắt đầu và dừng

`org.springframework.context.Lifecycle` định nghĩa ba thao tác:

```java
void start();
void stop();
boolean isRunning();
```

Một bean triển khai `Lifecycle` có thể tham gia vào các lời gọi `ApplicationContext.start()` và `ApplicationContext.stop()` khi có lifecycle processor phù hợp. Nhưng **không nên suy ra mọi bean `Lifecycle` thông thường đều được tự động start khi context refresh**: việc tự động tham gia pha khởi động là một lợi ích của `SmartLifecycle`.

`isRunning()` cần phản ánh trạng thái thật của component; chỉ trả `true` cố định có thể khiến Spring tin rằng thành phần vẫn hoạt động hoặc bỏ qua một bước cần thiết.

### 2.2. `Phased`: cung cấp phase

`org.springframework.context.Phased` khai báo `int getPhase()`.

Giá trị phase là **một số nguyên**, không phải thời gian tính bằng giây. Giá trị âm, 0 và dương đều hợp lệ. Khi so sánh, Spring không yêu cầu phase phải liên tiếp:

```text
phase -100  →  phase 0  →  phase 200
      start từ trái sang phải
      stop từ phải sang trái
```

Hai bean độc lập có phase khác nhau sẽ có thứ tự tương đối theo phase. Hai bean cùng phase **không có bảo đảm tổng quát về thứ tự start/stop bên trong nhóm đó**; nếu thứ tự là điều kiện đúng đắn, hãy khai báo quan hệ phụ thuộc thực tế thay vì trông chờ tên bean, thứ tự khai báo source hoặc thời điểm component scan.

### 2.3. `SmartLifecycle`: lifecycle có auto-start và stop callback

`org.springframework.context.SmartLifecycle` mở rộng `Lifecycle` và `Phased`, bổ sung:

```java
boolean isAutoStartup();
void stop(Runnable callback);
```

`isAutoStartup()` cho biết component có tự động được start khi context refresh hay không. Trong các phiên bản Framework hiện hành, mặc định của `SmartLifecycle` là auto-start; với thành phần phải khởi động thủ công, có thể override thành `false`.

`stop(Runnable callback)` cho phép lifecycle processor biết **khi nào việc stop đã thực sự hoàn tất**, kể cả khi dừng bất đồng bộ. Bean phải gọi `callback.run()` **sau khi đã kết thúc hoạt động cần chờ**, và phải bảo đảm callback được gọi khi kết thúc cả nhánh thành công lẫn nhánh lỗi đã xử lý.

> `SmartLifecycle` có mặc định phase `SmartLifecycle.DEFAULT_PHASE`, tương đương `Integer.MAX_VALUE` trong Spring Framework 6.x. `Lifecycle` thông thường không triển khai `Phased` được lifecycle processor xem như phase `0`. Do đó, một `SmartLifecycle` không override phase thường start rất muộn và stop rất sớm so với bean phase 0; hãy đặt phase tường minh khi thứ tự có ý nghĩa nghiệp vụ.

### 2.4. Bảng tóm tắt

| Cơ chế | Công dụng | Có tự định nghĩa thứ tự không? |
| --- | --- | --- |
| `Lifecycle` | Cung cấp `start`, `stop`, `isRunning` | Không tự có phase riêng |
| `Phased` | Đưa bean vào một phase cụ thể | Có, so với các phase khác |
| `SmartLifecycle` | Tự động start và stop callback, có phase | Có, với phase và dependency |
| `@DependsOn` | Khai báo bean phụ thuộc một bean khác | Có, **ưu tiên hơn phase** cho cặp bean phụ thuộc |
| `@Order` / `Ordered` | Sắp xếp một số tập hợp/callback được Spring xử lý | **Không thay thế** hợp đồng phase của `SmartLifecycle` |
| `@PreDestroy` / `DisposableBean` | Hủy và giải phóng bean sau vòng đời sử dụng | Không phải cơ chế start/stop theo phase |

## 3. Quy tắc phase: start tăng dần, stop giảm dần

Giả sử ba bean `SmartLifecycle` **không phụ thuộc nhau**:

| Bean | `getPhase()` | Start | Stop |
| --- | ---: | ---: | ---: |
| `ConnectionPoolLifecycle` | -200 | 1 | 3 |
| `ConsumerLifecycle` | 0 | 2 | 2 |
| `MetricsLifecycle` | 100 | 3 | 1 |

Khi context được refresh và bean auto-start:

```text
START:
  connection-pool (-200)
  consumer        (0)
  metrics         (100)

STOP:
  metrics         (100)
  consumer        (0)
  connection-pool (-200)
```

Tại sao reverse có ích? Khi metrics phụ thuộc logic đang chạy, nó có thể cần dừng các hoạt động đo đạc mới trước; consumer có thể cần ngừng nhận việc trước khi pool đóng. Nhưng tên/ý nghĩa của bean trong bảng chỉ là ví dụ; **phase phải phản ánh quan hệ sống/chết thực tế**.

### 3.1. Phase không phải priority của thread

`getPhase() = 100` không có nghĩa một thread dùng priority 100 hay chờ 100 ms. Nó chỉ cung cấp thứ tự tương đối cho vòng đời.

Không có quy tắc “phase âm luôn là hạ tầng, phase dương luôn là nghiệp vụ” bắt buộc bởi Framework. Đây chỉ có thể là **quy ước nội bộ** của dự án, cần ghi tài liệu và tránh xung đột với phase của các integration Spring.

### 3.2. Phase không đồng nghĩa thứ tự tạo bean

Trước khi start một `SmartLifecycle`, Spring cần tạo bean instance và giải quyết constructor dependencies. Bean definitions có thể được nạp/tạo theo những cơ chế khác phase: autowiring, bean factory post-processing, component scanning, singleton pre-instantiation và auto-start detection.

Vì vậy, không dùng `getPhase()` như công cụ duy nhất để ra lệnh **constructor của bean A phải chạy trước constructor của bean B**. Nếu cần quan hệ khởi tạo, sử dụng dependency injection và/hoặc `@DependsOn` theo đúng mục đích.

### 3.3. Phase không bảo đảm thứ tự trong cùng nhóm

Nếu `A` và `B` đều ở phase 0, bạn không nên dựa vào thứ tự `@Bean` trong source file để kết luận chắc chắn start A rồi B trong mọi môi trường. Khi `B` thực sự dùng `A` để hoạt động, hãy diễn đạt quan hệ này tường minh.

## 4. `depends-on`: quan hệ phụ thuộc được ưu tiên hơn phase

Giả sử bean `consumer` sử dụng bean `transport`. Quan hệ chính xác là:

```text
consumer depends on transport
```

Diễn đạt với Spring:

```java
@Bean("transport")
SmartLifecycle transport() {
    return new TransportLifecycle();
}

@Bean("consumer")
@DependsOn("transport")
SmartLifecycle consumer() {
    return new ConsumerLifecycle();
}
```

Đây là **đoạn minh họa**: cần định nghĩa hai implementation và imports `@Bean`, `@DependsOn`, `SmartLifecycle`. Ví dụ đầy đủ có thể chạy ở mục 7.

Khi khai báo `@DependsOn("transport")` trên bean `consumer`, Spring biết:

- Để tạo bean `consumer`, bean `transport` phải được khởi tạo trước.
- Trong quá trình start lifecycle, `transport` phải được start **trước** `consumer`.
- Trong quá trình stop lifecycle, `consumer` phải được stop **trước** `transport`.
- Với singleton beans, trong giai đoạn destruction, bean phụ thuộc (`consumer`) được hủy **trước** bean mà nó phụ thuộc (`transport`).

**Chiều quan hệ rất dễ viết ngược:** `@DependsOn("transport")` đặt trên `consumer`, chứ không đặt `@DependsOn("consumer")` trên `transport`.

### 4.1. Nếu phase mâu thuẫn với `depends-on`?

Ví dụ:

| Bean | Phase | Quan hệ |
| --- | ---: | --- |
| `transport` | 100 | Nguồn tài nguyên |
| `consumer` | -100 | `consumer` **depends on** `transport` |

Nếu **chỉ** nhìn phase, người mới học có thể dự đoán consumer start trước transport. Nhưng điều đó làm consumer khởi động khi tài nguyên của nó chưa sẵn sàng.

Khi quan hệ `depends-on` đã được đăng ký trong BeanFactory, **dependency thắng phase**:

```text
START thực tế:
  transport  (100)   ← phải sẵn sàng trước
  consumer  (-100)

STOP thực tế:
  consumer  (-100)   ← không còn dùng transport
  transport  (100)
```

Quy tắc này được `DefaultLifecycleProcessor` áp dụng khi xử lý bean có quan hệ phụ thuộc. Mục đích là giữ invariant, không cho phase “ép” một dependent start trước dependency hoặc stop sau dependency.

### 4.2. Với nhiều cấp phụ thuộc

Nếu:

```text
webConsumer depends-on messageRouter
messageRouter depends-on transport
```

thứ tự hợp lệ về mặt phụ thuộc là:

```text
START: transport → messageRouter → webConsumer
STOP:  webConsumer → messageRouter → transport
```

Ngay cả khi cả ba được gán phase khó hiểu, Spring vẫn tôn trọng quan hệ đã khai báo. Tuy nhiên, một hệ thống dễ bảo trì nên **chọn phase phù hợp với graph phụ thuộc**, thay vì cố tình tạo xung đột. Ví dụ mâu thuẫn ở mục 7 chỉ để chứng minh nguyên tắc ưu tiên.

### 4.3. `@DependsOn` và constructor injection có giống nhau?

Không hoàn toàn.

```java
@Bean
ConsumerService consumerService(TransportClient transportClient) {
    return new ConsumerService(transportClient);
}
```

Constructor/factory-method injection diễn đạt **nhu cầu một object**; Spring phải resolve dependency để tạo consumer. BeanFactory cũng có thể theo dõi các quan hệ dependency phục vụ lifecycle.

```java
@Bean
@DependsOn("transportLifecycle")
ConsumerService consumerService() {
    return new ConsumerService();
}
```

`@DependsOn` diễn đạt một **quan hệ khởi tạo/ngừng/hủy giữa các bean theo tên** ngay cả khi consumer không nhận một constructor parameter thuộc transport, ví dụ khi cả hai tương tác qua một singleton registry hoặc broker ngoài JVM.

Nếu có một dependency về mặt code thực sự, ưu tiên **constructor injection** để compiler và test thấy được hợp đồng. Dùng `@DependsOn` khi có yêu cầu rõ ràng về bean lifecycle mà quan hệ injection không diễn đạt đầy đủ hoặc không trực tiếp.

`@DependsOn` **không tiêm** đối tượng vào field, không tự tạo kênh giao tiếp và không chứng minh hệ thống bên ngoài đã healthy. Nó bảo đảm dependency bean được chuẩn bị/start theo thứ tự Spring biết, còn “sẵn sàng nhận message” phải do `start()` của component thực hiện đúng nghĩa.

### 4.4. Phạm vi singleton của thứ tự hủy

Trong Spring Framework, quan hệ `depends-on` có thể ảnh hưởng thứ tự **destroy của singleton beans**. Không áp giả định này cho mọi prototype: Spring không quản lý vòng đời hủy của prototype theo cách quản lý singleton. Nếu code tự tạo tài nguyên ngoài container, Spring cũng không tự đóng nó chỉ vì có `@DependsOn`.

## 5. `DefaultLifecycleProcessor` điều phối thứ tự như thế nào?

Spring Framework có `DefaultLifecycleProcessor`, thường được đăng ký dưới tên `lifecycleProcessor` trong `ApplicationContext`.

Trong đường startup thông thường:

1. Context refresh đến giai đoạn kết thúc.
2. `LifecycleProcessor.onRefresh()` tìm các bean lifecycle phù hợp và auto-start các `SmartLifecycle` có `isAutoStartup() == true`.
3. Các bean được tổ chức theo phase; bean phase thấp được xử lý trước ở đường start.
4. Khi start một bean, processor xem xét **dependencies** của bean đó: phải start dependency trước.
5. Bean thực thi `start()` và cập nhật trạng thái `isRunning()`.

Trong đường shutdown thông thường:

1. `ApplicationContext.close()` gọi lifecycle processor để dừng các component đang chạy.
2. Các phase được duyệt **từ cao xuống thấp**.
3. Trước khi dừng một bean, processor dừng các bean phụ thuộc vào nó (dependent beans).
4. Với `SmartLifecycle`, processor gọi `stop(Runnable callback)` và chờ callback của phase theo chính sách timeout.
5. Sau giai đoạn stop, context tiếp tục hủy singleton và giải phóng những tài nguyên do container quản lý.

Đây là mô hình giải thích, không phải cam kết về từng bước triển khai nội bộ cho mọi Spring Framework version. Thứ tự của **một bean cụ thể** còn phụ thuộc việc bean có đang chạy hay không, đã auto-start hay chưa, callback có trả về không và context có đang shutdown bình thường hay bị kill đột ngột.

### 5.1. Phân biệt “stop” và “destroy”

Một bean có thể trải qua hai cơ chế:

```text
Context đang hoạt động
       |
       v
LifecycleProcessor.stop: dừng công việc, thread, nhận message
       |
       v
Destroy singleton: @PreDestroy / DisposableBean / destroyMethod
       |
       v
Context đã đóng
```

`stop()` phục vụ **ngừng hoạt động**. Destroy callback phục vụ **giải phóng tài nguyên** khi bean bị hủy. Có bean hỗ trợ cả hai; thiết kế phải idempotent, không double-close tài nguyên dẫn đến lỗi.

Ví dụ consumer cần ngừng nhận message và đợi xử lý xong ở `stop(Runnable)`, sau đó destroy method giải phóng registry hoặc thread pool nếu thuộc sở hữu bean. Nếu consumer còn dùng transport khi `stop()` đang chạy, transport phải chưa bị đóng.

### 5.2. Shutdown theo phase không tự bảo đảm toàn bộ process kết thúc

Để callback chạy, ứng dụng phải đi qua shutdown phù hợp: `ConfigurableApplicationContext.close()`, Spring Boot shutdown hook khi nhận tín hiệu được xử lý bình thường, hoặc context stop/close do hạ tầng quản lý.

Nếu process bị `kill -9`, crash native, hoặc bị container force-kill sau khi quá thời gian grace period, Spring **không có cơ hội** bảo đảm dừng theo thứ tự. Thứ tự lifecycle là một phần của thiết kế an toàn, không phải thay thế cho timeout, xử lý tín hiệu, idempotency và khả năng phục hồi từ lỗi.

## 6. `stop(Runnable callback)` và deadline dừng

### 6.1. Callback là tín hiệu hoàn thành, không phải signal bắt đầu

Khi một `SmartLifecycle` được stop, lifecycle processor có thể gọi:

```java
@Override
public void stop(Runnable callback) {
    try {
        stop();
    } finally {
        callback.run();
    }
}
```

Đoạn trên là cách triển khai **dừng đồng bộ** khi `stop()` thực sự đã dừng công việc. Nếu `stop()` chỉ gửi tín hiệu nhưng consumer vẫn còn chạy, gọi callback ngay là sai về ý nghĩa: processor có thể cho dependency dừng trong khi consumer chưa ngừng sử dụng nó.

Với stop bất đồng bộ, `stop(Runnable callback)` phải chỉ gọi `callback.run()` **sau khi việc ngừng đã hoàn thành**, kể cả khi luồng dừng chạy ở thread khác. Cần bảo đảm callback được gọi **một lần**, không bị mất trong các nhánh lỗi hoặc khi executor từ chối task.

Đoạn pseudocode minh họa ý tưởng:

```java
@Override
public void stop(Runnable callback) {
    shutdownExecutor.execute(() -> {
        try {
            stopAcceptingNewMessages();
            waitForInFlightWorkToFinish();
        } finally {
            running = false;
            callback.run();
        }
    });
}
```

Đây **không phải ví dụ chạy độc lập**: cần thiết kế `shutdownExecutor`, `stopAcceptingNewMessages`, `waitForInFlightWorkToFinish`, timeout và xử lý task rejection. Trong production, không nên để `waitForInFlightWorkToFinish()` chờ vô hạn; deadline của task phải nhỏ hơn ngân sách shutdown.

### 6.2. Timeout theo phase trong Spring Boot

Spring Boot cho phép cấu hình:

```properties
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Đây là **ngân sách chờ theo phase của lifecycle processor** trong shutdown; không phải timeout riêng cho mỗi bean và cũng không biến `stop()` của bạn thành phương thức tự bị hủy cưỡng bức sau 20 giây.

Nếu callback của một bean không đến trong thời hạn, processor có thể tiếp tục shutdown theo cơ chế của framework; các tài nguyên phụ thuộc có nguy cơ bị đóng trước khi công việc nền kết thúc. Vì vậy:

- `stop(Runnable)` phải phát callback khi hoàn tất.
- Tác vụ I/O cần timeout của chính nó.
- Công việc đang chạy cần cơ chế drain/cancel trong thời hạn xác định.
- Shutdown graceful của web server và termination grace period của hạ tầng phải có ngân sách tương thích.

Một dòng cấu hình timeout **không sửa được deadlock** hoặc lời gọi I/O blocking không có timeout trong implementation.

### 6.3. `server.shutdown=graceful` có liên quan ra sao?

Với ứng dụng web được hỗ trợ, có thể dùng:

```properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

Graceful shutdown web server tìm cách ngừng tiếp nhận request mới và cho các request đang xử lý một khoảng thời gian hoàn tất. Quá trình đó phối hợp với lifecycle processor của Spring Boot, nhưng **không tự bảo đảm** consumer MQ, background job hay client tự quản đều đã drain đúng.

Hãy thiết kế bean `SmartLifecycle` cho những tài nguyên ngoài web server và kiểm tra thứ tự liên hệ thực tế. Không tự gán phase bất kỳ trùng với phase hạ tầng của Boot nếu chưa có lý do và kiểm thử trên đúng stack Servlet/Reactive đang dùng.

## 7. Ví dụ hoàn chỉnh: `@DependsOn` thắng phase trong start/stop

Ví dụ dưới đây dùng **Java 17+, Spring Boot 3.3.x**, và chỉ cần dependency `spring-boot-starter`. Ứng dụng chạy ở chế độ `WebApplicationType.NONE` để tránh tác động của web server, giúp output về thứ tự các bean ngắn và dễ kiểm chứng.

Ta tạo ba `SmartLifecycle`:

- `heartbeat`, phase `-200`, **không** có dependency.
- `transport`, phase `100`, cung cấp tài nguyên.
- `consumer`, phase `-100`, khai báo `@DependsOn("transport")`.

Điểm cố ý để kiểm chứng: phase `consumer=-100` **thấp hơn** phase `transport=100`. Nếu chỉ xét phase, consumer sẽ start trước. Nhưng do `depends-on`, transport phải start trước consumer và ngừng sau consumer.

### 7.1. Tạo Maven project

Cấu trúc:

```text
smart-lifecycle-order-demo/
├── pom.xml
└── src/main/
    └── java/com/example/lifecycle/LifecycleOrderDemoApplication.java
```

File `pom.xml`:

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
    <artifactId>smart-lifecycle-order-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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

### 7.2. Mã ứng dụng đầy đủ

Tạo `src/main/java/com/example/lifecycle/LifecycleOrderDemoApplication.java`:

```java
package com.example.lifecycle;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.DependsOn;

@SpringBootApplication
public class LifecycleOrderDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(LifecycleOrderDemoApplication.class);
        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("main:context-ready");
        }
    }

    @Bean("heartbeat")
    SmartLifecycle heartbeat() {
        return new LoggingLifecycle("heartbeat", -200);
    }

    @Bean("transport")
    SmartLifecycle transport() {
        return new LoggingLifecycle("transport", 100);
    }

    @Bean("consumer")
    @DependsOn("transport")
    SmartLifecycle consumer() {
        return new LoggingLifecycle("consumer", -100);
    }

    static final class LoggingLifecycle implements SmartLifecycle {

        private final String name;
        private final int phase;
        private volatile boolean running;

        LoggingLifecycle(String name, int phase) {
            this.name = name;
            this.phase = phase;
        }

        @Override
        public int getPhase() {
            return phase;
        }

        @Override
        public boolean isAutoStartup() {
            return true;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public void start() {
            if (!running) {
                running = true;
                System.out.println("start:" + name);
            }
        }

        @Override
        public void stop() {
            if (running) {
                running = false;
                System.out.println("stop:" + name);
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
    }
}
```

**Giải thích triển khai:**

1. `LoggingLifecycle` là một implementation `SmartLifecycle` thật, có `getPhase()`, `start()`, `stop()`, `stop(Runnable)` và `isRunning()`. Ví dụ chỉ log nên không cần executor hoặc socket.
2. Các method `@Bean` được Spring đăng ký với đúng tên `heartbeat`, `transport`, `consumer`.
3. `@DependsOn("transport")` đặt trên **bean consumer**, diễn đạt consumer cần transport.
4. `isAutoStartup()` trả `true`, nên lifecycle processor khởi động các component trong refresh.
5. Khi `application.run(args)` trả về, context đã được khởi động; dòng `main:context-ready` nằm **sau các dòng start**.
6. `try-with-resources` đóng `ConfigurableApplicationContext`. Lúc đóng, Spring gọi `stop(Runnable)` cho những lifecycle bean đang chạy, nên các dòng stop xuất hiện.
7. `stop(Runnable)` gọi callback ngay **vì stop đồng bộ đã hoàn tất trong chính thread đó**. Trong ứng dụng thật, chỉ callback khi tài nguyên đã ngừng sử dụng xong.

### 7.3. Build và chạy

Tại thư mục chứa `pom.xml`:

```bash
mvn package
```

Chạy:

```bash
java -jar target/smart-lifecycle-order-demo-0.0.1-SNAPSHOT.jar
```

Nếu dự án đã có Maven Wrapper:

```bash
./mvnw package
```

Windows PowerShell khi có wrapper:

```powershell
.\mvnw.cmd package
```

Lệnh chạy giả định Maven/JDK và dependency đã được tải về. Đây không phải chương trình Java thuần có thể biên dịch trực tiếp bằng một lệnh `javac` thiếu Spring libraries trên classpath.

### 7.4. Output kỳ vọng

Trong môi trường không có bean lifecycle bổ sung làm thay đổi việc quan sát, **các dòng do mã demo tự in** là:

```text
start:heartbeat
start:transport
start:consumer
main:context-ready
stop:consumer
stop:transport
stop:heartbeat
```

Console có thể có thêm log từ Spring Boot, Maven hoặc hệ thống logging; bài này chỉ cam kết **thứ tự tương đối các dòng mà demo in**.

Lý giải từng bước:

- `heartbeat` có phase `-200`, start đầu vì nó độc lập và có phase thấp nhất.
- `consumer` có phase `-100`, nên được xét sớm hơn `transport` (phase `100`) nếu chỉ nhìn phase. Nhưng dependency được kiểm tra: processor **start `transport` trước**, rồi mới start `consumer`.
- Khi hết khối `try`, context đóng và processor bắt đầu stop theo phase giảm dần. Nó xem `transport` thuộc phase cao, nhưng phát hiện **`consumer` phụ thuộc `transport`**, nên stop consumer **trước** transport.
- Cuối cùng, `heartbeat` độc lập ở phase `-200` được stop.

Vì vậy, output cho thấy hai luật cùng hiện diện: **phase** sắp xếp các thành phần độc lập, còn **depends-on** bảo vệ thứ tự giữa những bean có quan hệ phụ thuộc.

### 7.5. Bài thử đối chứng: bỏ `@DependsOn`

Để thấy rõ vai trò dependency, hãy thử **trên một bản sao dự án** và chỉ bỏ annotation `@DependsOn("transport")` ở bean consumer. Build/run lại với ba phase không đổi.

Khi hai bean không còn quan hệ dependency do BeanFactory biết, thứ tự riêng của chúng dựa trên phase:

```text
start:heartbeat
start:consumer
start:transport
main:context-ready
stop:transport
stop:consumer
stop:heartbeat
```

Output minh họa rủi ro: consumer start trước transport, và transport stop trước consumer. Trong hệ thống có message broker thật, điều này có thể làm lỗi start hoặc mất khả năng drain khi shutdown. Vì vậy, đừng chỉ đặt phase mà **quên diễn đạt quan hệ phụ thuộc thực tế**.

### 7.6. Bài thử thứ hai: phase phù hợp dependency

Giữ `@DependsOn("transport")`, đổi phase thành:

```text
heartbeat = -200
transport = -100
consumer  = 100
```

Cả phase và dependency giờ cùng hướng:

```text
START: heartbeat → transport → consumer
STOP:  consumer  → transport → heartbeat
```

Đây là cách bố trí **nên dùng trong production** khi có thể: phase phản ánh các tầng khởi động và depends-on diễn đạt ràng buộc cụ thể. Không cố ý tạo phase mâu thuẫn như bản demo chỉ để thử API.

## 8. Phân biệt ba cơ chế thứ tự: phase, `depends-on`, `@Order`

Một lỗi thiết kế phổ biến là thay đổi `@Order` trên bean rồi trông chờ trình tự shutdown đổi theo. Hãy phân biệt:

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Sắp xếp các nhóm component có vòng đời start/stop | `SmartLifecycle.getPhase()` | LifecycleProcessor tổ chức các phase |
| Bắt consumer start sau transport và stop trước transport | `@DependsOn("transport")` hoặc dependency quan hệ được BeanFactory nhận biết | Ràng buộc start/stop và singleton destruction |
| Sắp xếp `ApplicationRunner` hoặc tập listeners | `Ordered` / `@Order` khi API hỗ trợ | Dành cho thứ tự thực thi callback, không tự điều phối lifecycle graph |
| Sắp xếp bean init dựa trên class injection | Constructor/factory-method dependency | BeanFactory phải resolve trước khi tạo dependent |
| Giải phóng connection vào cuối vòng đời | `@PreDestroy`, `DisposableBean` hay destroy method | Hủy tài nguyên sau khi stop phù hợp |
| Bảo đảm producer không gửi việc mới khi đang drain | API stop/disable producer và giao thức phối hợp | Spring phase không thay logic nghiệp vụ |
| Tránh mất dữ liệu khi process bị kill | Ack/retry/idempotency và thiết kế consumer | Lifecycle order không thể bảo đảm callback khi process bị kill |

`@DependsOn` còn có thể dùng ở cấp `@Component`:

```java
@Component
@DependsOn("transport")
class ConsumerLifecycle implements SmartLifecycle {
    // Triển khai start(), stop(), getPhase(), ...
}
```

Đây là minh họa khai báo annotation; class chưa đầy đủ các method. Trong sản phẩm, thường dùng bean constructor injection nếu consumer nhận được transport như một dependency Java rõ ràng.

Không xem phase như một cơ chế transaction. Spring không tự rollback mọi side effect của một component đã start nếu component sau thất bại.

## 9. Thiết kế shutdown cho hệ thống thực tế

### 9.1. Producer → queue → consumer

Giả sử có:

```text
HTTP request → producer → local queue → consumer → external transport
```

Nếu các thành phần đều có lifecycle riêng:

- Khi startup: chuẩn bị transport và consumer, sau đó mới cho producer tạo thêm việc.
- Khi shutdown: producer **ngừng nhận/sinh việc mới**, consumer **drain queue và dừng**, rồi transport **đóng kết nối**.

Một kế hoạch phase có thể là:

| Thành phần | Phase đề xuất minh họa | Quan hệ thực tế |
| --- | ---: | --- |
| Transport | -200 | Hạ tầng cần sống lâu nhất |
| Consumer | -100 | `depends-on` transport |
| Producer | 100 | `depends-on` consumer |

Thứ tự:

```text
START: Transport → Consumer → Producer
STOP:  Producer  → Consumer → Transport
```

Các con số chỉ là **quy ước minh họa**, không phải phase cố định do Spring Boot khuyến cáo cho mọi loại bean. Trong dự án web thật, server/lifecycle integration của Boot cũng có phase riêng; cần kiểm tra kết quả thực tế để tránh tranh chấp với graceful shutdown HTTP.

### 9.2. Không dừng tài nguyên trước khi dependent hoàn thành

Một lỗi thường gặp:

```text
stop:transport
stop:consumer
```

Ở thời điểm consumer cố flush result hoặc ack message, transport đã đóng. Dù log có thể cho thấy JVM kết thúc “thành công”, nghiệp vụ vẫn mất dữ liệu hoặc kích hoạt retry bên ngoài.

Đúng hơn:

```text
stop:consumer (ngừng nhận, drain và ack công việc đang chạy)
stop:transport (đóng kết nối sau khi consumer ngừng dùng)
```

**Chỉ đổi thứ tự method call không đủ** nếu `stop(consumer)` trả về trước khi xử lý đang bay (in-flight) kết thúc. Callback phải phản ánh việc drain thật sự, nếu không lifecycle processor có thể cho transport dừng quá sớm.

### 9.3. Deadline shutdown và mức độ đảm bảo

Trong container/Kubernetes, quá trình tắt thường theo thứ tự: orchestrator gửi tín hiệu ngừng, ứng dụng cố gắng graceful shutdown trong grace period, sau đó process có thể bị kill nếu quá hạn.

Vì vậy:

- Đặt timeout của mỗi tác vụ nhỏ hơn tổng shutdown budget.
- Ngừng nhận việc mới trước khi drain.
- Dùng idempotency và retry để phục hồi công việc còn dở nếu process bị kill.
- Kiểm tra `terminationGracePeriodSeconds` của Pod và `spring.lifecycle.timeout-per-shutdown-phase`.
- Không cho rằng chỉ cần một `@DependsOn` là mọi request hoặc queue message chắc chắn hoàn tất.

### 9.4. Khi `isAutoStartup()` là `false`

Một bean `SmartLifecycle` có thể không auto-start khi context refresh nếu nó override:

```java
@Override
public boolean isAutoStartup() {
    return false;
}
```

Nó có thể được start bởi một thao tác tường minh. Khi shutdown, processor thường xét trạng thái đang chạy; bean chưa chạy không nhất thiết có `stop()` được gọi. Do đó, kỳ vọng dòng log stop xuất hiện cho mọi bean đã được đăng ký là không chính xác.

Nếu bắt buộc có cleanup ngay cả khi bean chưa từng start, hãy thiết kế destroy method riêng và đặt điều kiện để tránh double cleanup.

## 10. Lỗi phổ biến và cách chẩn đoán

### Lỗi 1 — “Đã đặt phase cao nhưng bean vẫn stop sau một bean phase thấp”

Kiểm tra quan hệ `@DependsOn` và các dependencies được BeanFactory biết. Quan hệ phụ thuộc được ưu tiên để bảo vệ dependent. Đây là hành vi đúng, không nhất thiết là bug của `DefaultLifecycleProcessor`.

### Lỗi 2 — “Consumer stop trước transport nhưng vẫn gặp Connection closed”

Thứ tự đã đúng **ở mốc gọi stop**, nhưng `consumer.stop()` có thể chỉ gửi tín hiệu bất đồng bộ rồi trả về ngay hoặc gọi callback quá sớm. Cần đợi in-flight work hoàn thành **trước callback**, với deadline và xử lý lỗi.

### Lỗi 3 — “Chỉ thêm `@Order(1)` nhưng thứ tự dừng không đổi”

`@Order` không phải phase của `SmartLifecycle`. Override `getPhase()` hoặc khai báo quan hệ phụ thuộc nếu có invariant thực tế.

### Lỗi 4 — “Không thấy `stop(Runnable)` chạy lúc nhấn Stop trong IDE”

Có thể IDE/process đã bị force-kill, ứng dụng không đi qua Spring shutdown hook, context chưa đóng hoặc bean không ở trạng thái running. Hãy test bằng `context.close()` trong chương trình thử nghiệm và kiểm tra tín hiệu kill mà môi trường thực sự gửi.

### Lỗi 5 — “Shutdown chờ mãi rồi tài nguyên khác bị dừng”

Một callback có thể không được gọi, hoặc bước drain chờ vô hạn. Kiểm tra `stop(Runnable)`, timeout network, thread dump và cấu hình `spring.lifecycle.timeout-per-shutdown-phase`. Không che lỗi bằng cách chỉ tăng timeout vô hạn.

### Lỗi 6 — “`@DependsOn` trỏ sai bean”

Tên trong annotation là **bean name**, không phải tên interface Java hay tên biến tùy ý. Ví dụ `@Bean("transport")` ứng với `@DependsOn("transport")`. Sai tên có thể làm context fail khi tạo bean hoặc không có quan hệ như mong muốn nếu annotation không được gắn vào đúng bean definition.

### Lỗi 7 — “Có vòng phụ thuộc: A depends-on B, B depends-on A”

Đó là dependency cycle không hợp lệ. Spring không thể tìm thứ tự start/stop tuyến tính thỏa cả hai; startup có thể thất bại khi resolve bean definitions. Hãy thiết kế lại ownership, tách một registry/mediator độc lập hoặc bỏ quan hệ vòng.

### Lỗi 8 — “Stop callback chạy hai lần”

Nếu tự gọi callback trong nhiều nhánh và thêm `finally` gọi lại, processor có thể nhận tín hiệu completion không nhất quán. Thiết kế callback exactly-once, kể cả trường hợp executor reject task và trường hợp task thất bại.

### Lỗi 9 — “Bean không tự start dù implements `SmartLifecycle`”

Kiểm tra `isAutoStartup()`, bean có được đăng ký trong context thực tế không, method `start()` có chuyển `isRunning()` đúng không, và có exception trong startup hay không. Nếu bean thuộc child context, đừng giả định parent context lifecycle tự điều phối chính xác mọi bean con ngoài API của nó.

### Lỗi 10 — “Thay đổi phase khiến bean constructor vẫn chạy theo thứ tự cũ”

Phase điều phối **start/stop lifecycle**, không định nghĩa tổng thứ tự constructor/injection. Nếu bean B phải có bean A lúc tạo, dùng dependency injection/`@DependsOn`; để phase diễn đạt thứ tự **kích hoạt hoạt động**.

### Lỗi 11 — “`@PreDestroy` đã chạy đúng nên chắc chắn message không mất”

`@PreDestroy` thường chạy trong giai đoạn hủy bean, khi nhiều component khác có thể đã stop. Để ngừng nhận message, drain in-flight rồi mới đóng dependency, sử dụng `SmartLifecycle.stop(Runnable)` với callback chính xác.

### Lỗi 12 — “Thử nghiệm chạy không có web server, production chạy khác”

Web server, broker listener container, scheduler và framework integrations có thể đăng ký `SmartLifecycle` riêng. Trong production, thứ tự shutdown tổng thể có thể có thêm phase, callback và context. Kiểm thử với đúng starter/dependencies và cùng shutdown signal, không suy diễn toàn bộ từ bản demo `WebApplicationType.NONE`.

## 11. Kiểm thử thứ tự và bảo vệ không mất dữ liệu

### 11.1. Unit test logic `SmartLifecycle`

Với bean đơn giản, kiểm tra:

1. Sau `start()`, `isRunning()` trở thành `true`.
2. Sau `stop()`, `isRunning()` trở thành `false`.
3. `stop(Runnable)` thực hiện cleanup rồi gọi callback.
4. `start()`/`stop()` lặp lại không gây double-ack hay double-close.

Đối với component có nhiều thread, dùng latch, stub client và executor được quản lý để kiểm soát thời điểm completion thay vì `Thread.sleep(...)` trong test.

### 11.2. Integration test thực sự trên ApplicationContext

Một unit test gọi thủ công `consumer.start()` rồi `transport.start()` **không kiểm tra được** thứ tự do Spring lifecycle processor điều phối.

Hãy tạo context với ba bean như ví dụ mục 7, thu các sự kiện start/stop vào một danh sách thread-safe, đóng context và assert thứ tự:

```text
start:heartbeat
start:transport
start:consumer
stop:consumer
stop:transport
stop:heartbeat
```

Nếu shutdown có async callbacks, test phải đợi context close hoàn tất theo hợp đồng timeout và xác nhận in-flight tasks đã kết thúc. Khi test Spring Boot, kiểm tra thêm những lifecycle beans do starter khác tự đăng ký để tránh vô tình dựa vào một thứ tự toàn cục không được bảo đảm.

### 11.3. Test failure path

Ít nhất có ba lỗi đáng chủ động mô phỏng:

- `transport.start()` ném exception: consumer không được bắt đầu phục vụ bình thường.
- `consumer.stop()` chậm hơn timeout cho phép: cần hiểu processor có thể tiếp tục stop dependency và thiết kế khôi phục.
- Process bị kill khi đang drain: công việc chưa ack phải có cơ chế retry/idempotency ngoài process.

Mục tiêu không chỉ chứng minh dòng log đẹp, mà là **tài nguyên không bị đóng khi dependent còn cần**, trong phạm vi bảo đảm mà shutdown bình thường có thể cung cấp.

## 12. Câu hỏi luyện tập và đáp án

**Câu 1.** A có phase `-10`, B phase `20`, không có quan hệ phụ thuộc. Start/stop thế nào?

*Đáp án:* Start A rồi B; stop B rồi A.

**Câu 2.** `Consumer` phase `-100`, `Transport` phase `100`, nhưng `Consumer @DependsOn("transport")`. Start/stop thế nào?

*Đáp án:* Start Transport rồi Consumer; stop Consumer rồi Transport. `depends-on` có ưu tiên so với phase.

**Câu 3.** `@DependsOn("transport")` đặt trên bean Transport nghĩa là gì?

*Đáp án:* Transport phụ thuộc bean tên `transport` (nếu chính nó mang tên đó, tạo quan hệ sai/cycle); nó **không** diễn đạt “consumer dùng transport”. Annotation phải đặt ở **consumer** và chỉ tới tên bean dependency.

**Câu 4.** Có `@Order(1)` trên Consumer và `@Order(2)` trên Transport; có thể bỏ `@DependsOn` và tin shutdown đúng không?

*Đáp án:* Không. `@Order` có công dụng ở những API hỗ trợ sắp xếp, không thay thế cơ chế phase/dependency của `SmartLifecycle`.

**Câu 5.** `stop(Runnable callback)` gửi một task nền rồi gọi callback ngay, khi task chưa drain queue xong. Điều gì sai?

*Đáp án:* Callback báo dừng hoàn tất quá sớm. Lifecycle processor có thể tiếp tục đóng Transport trong khi Consumer vẫn xử lý queue.

**Câu 6.** Tại sao bean `SmartLifecycle` chưa start có thể không in dòng stop?

*Đáp án:* Processor xem trạng thái running trước khi dừng; bean chưa hoạt động không nhất thiết cần `stop()`. Destroy callback là cơ chế riêng.

**Câu 7.** Đặt `spring.lifecycle.timeout-per-shutdown-phase=10s` có chắc mọi socket bị cắt ngay sau 10 giây?

*Đáp án:* Không. Property điều khiển thời gian chờ callback theo phase. I/O blocking cần timeout/cancel của chính thư viện, và process manager có chính sách kill riêng.

**Câu 8.** Vì sao `@DependsOn` không thay thế retry/idempotency khi consumer MQ shutdown?

*Đáp án:* Nó điều phối start/stop trong context khi shutdown bình thường. Nó không đảm bảo JVM luôn chạy callback, không ngăn process bị kill, cũng không điều khiển trạng thái message đã ack ở broker.

**Câu 9.** Nếu ba bean đều phase 0, có nên dựa vào thứ tự tên file Java?

*Đáp án:* Không. Khai báo dependency thực tế; phase 0 chỉ cùng một nhóm lifecycle, không tạo quy tắc thứ tự bền vững cho từng bean.

**Câu 10.** Bean Consumer có constructor nhận Transport, vậy có cần `@DependsOn` không?

*Đáp án:* Constructor injection đã diễn đạt dependency thực sự và BeanFactory có thể theo dõi quan hệ đó. Chỉ thêm `@DependsOn` nếu muốn làm rõ một ràng buộc lifecycle khởi tạo/hủy theo tên mà injection chưa diễn đạt đủ; kiểm chứng bằng integration test.

## 13. Checklist triển khai

Trước khi đưa một cặp `SmartLifecycle` vào production:

- [ ] Xác định rõ **ai sở hữu tài nguyên** và ai tiêu thụ tài nguyên đó.
- [ ] Gán phase có quy ước, tránh sử dụng default max phase khi thứ tự có ý nghĩa.
- [ ] Khai báo quan hệ phụ thuộc thật bằng DI và/hoặc `@DependsOn`; **dependent start sau, stop trước** dependency.
- [ ] Viết `start()` / `stop()` idempotent, `isRunning()` phản ánh trạng thái thực.
- [ ] Trong `stop(Runnable)`, không callback trước khi ngừng nhận việc và drain xong.
- [ ] Có deadline/timeout cho I/O và queue draining, bao gồm nhánh lỗi.
- [ ] Chọn `spring.lifecycle.timeout-per-shutdown-phase` phù hợp với termination budget.
- [ ] Nếu có web server, phối hợp với graceful shutdown; không giả định cùng phase với các starter.
- [ ] Kiểm thử bằng **đóng ApplicationContext thật**, không chỉ gọi method đơn lẻ.
- [ ] Thử shutdown bình thường, startup error và force-kill; có retry/idempotency cho công việc không kịp hoàn tất.

## 14. Tài liệu chính thức

Các tài liệu sau là nguồn nền cho Spring Framework 6.x và Spring Boot 3.x:

- [Spring Framework Javadoc — `SmartLifecycle`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/SmartLifecycle.html): phase, `isAutoStartup`, `stop(Runnable)` và quy tắc ưu tiên của `depends-on`.
- [Spring Framework Javadoc — `DefaultLifecycleProcessor`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/support/DefaultLifecycleProcessor.html): điều phối bean lifecycle theo phase và callback shutdown.
- [Spring Framework Javadoc — `@DependsOn`](https://docs.spring.io/spring-framework/docs/6.1.6/javadoc-api/org/springframework/context/annotation/DependsOn.html): initialization-time dependency và singleton destruction-time ordering.
- [Spring Framework Reference — Lifecycle callbacks và `SmartLifecycle`](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): vòng đời bean và lifecycle processor.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): graceful shutdown web server và cấu hình timeout phù hợp.

## 15. Kết luận

**`SmartLifecycle` dùng phase để sắp xếp khởi động theo thứ tự tăng dần và dừng theo thứ tự giảm dần.** Nhưng với những bean có quan hệ phụ thuộc, `depends-on` có ưu tiên hơn phase: **dependency phải start trước và stop sau dependent**.

Quy tắc này bảo vệ những tài nguyên cần sống đủ lâu để component sử dụng chúng có thể dừng an toàn. Để biến thứ tự đúng thành shutdown thực sự an toàn, cần thêm `stop(Runnable)` callback đúng thời điểm, giới hạn thời gian, khả năng drain, idempotency và chính sách xử lý process bị kill.

Hãy thiết kế phase như bản đồ các tầng lifecycle, và `@DependsOn` như hợp đồng phụ thuộc giữa các bean. Khi cả hai cùng diễn đạt đúng kiến trúc, shutdown trở nên dễ dự đoán và dễ kiểm chứng.