# Quản lý Lifecycle, SmartLifecycle và tài nguyên cần đóng

> **Chương:** Vòng đời ứng dụng  
> **Module:** SPRING_CLOUD_CORE

Một ứng dụng Spring Cloud không chỉ khởi tạo controller và service rồi chờ request. Nó còn phải bắt đầu consumer, scheduler, kết nối tới hệ thống phụ thuộc, ngừng nhận công việc mới khi shutdown và giải phóng tài nguyên đúng thứ tự. Nếu thứ tự dừng sai, một consumer có thể tiếp tục gửi message trong khi connection đã đóng; nếu ứng dụng thoát quá sớm, request đang xử lý hoặc message đang chạy có thể bị mất.

Spring Framework cung cấp các abstraction **Lifecycle**, **SmartLifecycle** và **LifecycleProcessor** để điều phối những thành phần có thể bắt đầu và dừng theo vòng đời của ApplicationContext. Cơ chế callback hủy bean như **@PreDestroy**, **DisposableBean** và destroy method bổ sung bước giải phóng tài nguyên cuối cùng. Bài này trình bày cách phối hợp các cơ chế đó để khởi động và shutdown có kiểm soát trong ứng dụng **SPRING_CLOUD_CORE**.

## 1. Hai lớp vòng đời cần phân biệt

Vòng đời của một ứng dụng Spring có thể nhìn ở hai lớp:

- **Vòng đời bean:** tạo instance, inject dependency, gọi initialization callback, sử dụng bean và gọi destruction callback khi container đóng.
- **Vòng đời ứng dụng:** refresh ApplicationContext, khởi động các thành phần nền, tiếp nhận công việc, dừng các thành phần theo thứ tự và đóng tài nguyên.

Một bean có thể tham gia cả hai lớp. Ví dụ, một message consumer được Spring tạo như bean, được LifecycleProcessor gọi start khi context sẵn sàng, được gọi stop khi context đóng và cuối cùng được giải phóng tài nguyên.

~~~mermaid
flowchart TB
    A["SpringApplication.run()"] --> B["Tạo và refresh ApplicationContext"]
    B --> C["Tạo bean và inject dependency"]
    C --> D["Initialization callbacks"]
    D --> E["LifecycleProcessor.onRefresh()"]
    E --> F["Lifecycle beans start theo phase tăng dần"]
    F --> G["Ứng dụng phục vụ request / xử lý message"]
    G --> H["SIGTERM hoặc context.close()"]
    H --> I["ContextClosedEvent"]
    I --> J["LifecycleProcessor.onClose()"]
    J --> K["Lifecycle beans stop theo phase giảm dần"]
    K --> L["Bean destruction callbacks"]
    L --> M["Đóng ApplicationContext"]
~~~

Sơ đồ mô tả thứ tự tổng quát khi đóng context. Chi tiết tích hợp của server, container và phiên bản framework có thể bổ sung các bước riêng, nhưng nguyên tắc quan trọng là dừng công việc đang chạy trước khi giải phóng những dependency mà công việc đó cần.

## 2. Lifecycle: hợp đồng start và stop cơ bản

`org.springframework.context.Lifecycle` là interface đơn giản để biểu diễn một thành phần có thể chạy và dừng:

~~~java
public interface Lifecycle {
    void start();
    void stop();
    boolean isRunning();
}
~~~

Ý nghĩa:

- `start()` bắt đầu hoạt động của thành phần.
- `stop()` yêu cầu thành phần ngừng hoạt động.
- `isRunning()` cho biết thành phần đang chạy hay không.

Ví dụ một scheduler đơn giản:

~~~java
import org.springframework.context.Lifecycle;
import org.springframework.stereotype.Component;

@Component
public class ReportSchedulerLifecycle implements Lifecycle {

    private volatile boolean running;

    @Override
    public void start() {
        if (running) {
            return;
        }

        // Khởi động scheduler hoặc đăng ký công việc định kỳ.
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        // Ngừng nhận và lên lịch công việc mới.
        running = false;
    }

    @Override
    public boolean isRunning() {
        return running;
    }
}
~~~

`Lifecycle` phù hợp khi thành phần chỉ cần hành vi start/stop cơ bản. Spring cung cấp `LifecycleProcessor` để quản lý những bean triển khai Lifecycle trong vòng đời ApplicationContext. Thông thường, LifecycleProcessor bắt đầu các thành phần trong quá trình refresh context và dừng chúng khi context đóng.

Với thành phần cần điều khiển thứ tự hoặc cần hoàn tất shutdown bất đồng bộ, `SmartLifecycle` cung cấp thêm hợp đồng.

## 3. SmartLifecycle bổ sung phase và callback shutdown

`SmartLifecycle` mở rộng `Lifecycle` và `Phased`. Nó bổ sung:

- `isAutoStartup()`: cho biết bean có tự khởi động khi context refresh hay không.
- `getPhase()`: xác định phase để sắp xếp thứ tự start/stop.
- `stop(Runnable callback)`: cho phép báo cho LifecycleProcessor biết khi việc dừng bất đồng bộ đã hoàn tất.

Một bean SmartLifecycle thường được tự khởi động khi ApplicationContext refresh hoàn tất nếu `isAutoStartup()` trả về true. Giá trị mặc định của phương thức này là true. Phase mặc định của SmartLifecycle là `Integer.MAX_VALUE`; hãy khai báo phase tường minh khi thứ tự giữa các thành phần có ý nghĩa.

### 3.1. Phase quyết định thứ tự start và stop

Spring sắp xếp lifecycle components theo phase:

- Khi **start**, phase thấp hơn được bắt đầu trước.
- Khi **stop**, phase cao hơn được dừng trước.

Ví dụ một message consumer cần connection manager hoạt động trước khi nó start. Consumer cũng cần dừng trước khi connection manager đóng:

| Thành phần | Phase | Thứ tự start | Thứ tự stop |
| --- | ---: | ---: | ---: |
| Connection manager | 0 | Trước | Sau |
| Message consumer | 100 | Sau | Trước |
| Background dispatcher | 200 | Cuối | Đầu |

Quy tắc này giúp dependency có thời gian sống phù hợp: tài nguyên nền tảng được mở trước, thành phần sử dụng chúng bắt đầu sau; khi shutdown, thành phần sử dụng tài nguyên dừng trước rồi mới đóng tài nguyên nền tảng.

Các bean cùng phase không nên dựa vào thứ tự ngẫu nhiên để đảm bảo dependency. Nếu có quan hệ phụ thuộc rõ ràng, hãy biểu diễn dependency trong cấu hình Spring hoặc thiết kế phase khác nhau.

Bean chỉ triển khai `Lifecycle` và không cung cấp phase được xử lý ở phase 0 trong cơ chế mặc định. `SmartLifecycle` có phase mặc định là `Integer.MAX_VALUE`, nên thường được start sau các Lifecycle bean thông thường và stop trước chúng. Nếu cần thứ tự khác, hãy override `getPhase()`.

### 3.2. Auto startup

`isAutoStartup()` trả về true nếu bean cần tự start khi context refresh. Nếu trả về false, bean không được tự động start theo cơ chế SmartLifecycle; ứng dụng cần một thành phần quản trị gọi start khi phù hợp.

Ví dụ:

~~~java
@Override
public boolean isAutoStartup() {
    return false;
}
~~~

Có thể dùng cách này cho một worker chỉ chạy sau khi hệ thống đã hoàn tất một bước kiểm tra hoặc sau khi có lệnh quản trị. Tuy nhiên, phải có quy trình start tường minh và xử lý trạng thái chưa chạy khi context đóng.

## 4. stop(Runnable) và shutdown bất đồng bộ

Điểm khác biệt quan trọng của SmartLifecycle là callback trong `stop(Runnable)`. Với một thành phần có công việc đang chạy, việc gọi stop có thể gồm nhiều bước:

1. Ngừng nhận công việc mới.
2. Chờ công việc đang chạy hoàn tất hoặc hết thời gian drain.
3. Đóng consumer hoặc tài nguyên liên quan.
4. Gọi callback để thông báo đã dừng xong.

Nếu phương thức stop trả về ngay nhưng thành phần vẫn đang drain, LifecycleProcessor có thể hiểu nhầm việc shutdown đã hoàn tất và chuyển sang dừng phase tiếp theo. Vì vậy, callback phải được gọi sau khi quá trình dừng thật sự kết thúc.

### 4.1. Ví dụ message consumer có drain

Giả sử thư viện messaging cung cấp abstraction sau:

~~~java
import java.util.concurrent.CompletionStage;

public interface MessageConsumer {
    void start();
    void stopAccepting();
    CompletionStage<Void> drain();
    void close();
}
~~~

Bean quản lý consumer:

~~~java
import org.springframework.context.SmartLifecycle;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumerLifecycle implements SmartLifecycle {

    private final MessageConsumer consumer;
    private volatile boolean running;

    public OrderConsumerLifecycle(MessageConsumer consumer) {
        this.consumer = consumer;
    }

    @Override
    public void start() {
        if (running) {
            return;
        }

        consumer.start();
        running = true;
    }

    @Override
    public void stop() {
        if (!running) {
            return;
        }

        try {
            consumer.stopAccepting();
            consumer.drain().toCompletableFuture().join();
        } finally {
            try {
                consumer.close();
            } finally {
                running = false;
            }
        }
    }

    @Override
    public void stop(Runnable callback) {
        if (!running) {
            callback.run();
            return;
        }

        try {
            consumer.stopAccepting();
            consumer.drain().whenComplete((ignored, failure) -> {
                try {
                    if (failure != null) {
                        // Ghi nhận lỗi drain bằng logger/metric phù hợp.
                    }
                    consumer.close();
                } finally {
                    running = false;
                    callback.run();
                }
            });
        } catch (RuntimeException ex) {
            try {
                consumer.close();
            } finally {
                running = false;
                callback.run();
            }
            throw ex;
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
}
~~~

Ví dụ giả định `MessageConsumer` cung cấp thao tác dừng nhận message, drain công việc đang xử lý và đóng tài nguyên. Trong hệ thống thật, cần xác định rõ điều gì xảy ra nếu drain thất bại, timeout hoặc callback được gọi trong lúc consumer đã dừng.

Một số nguyên tắc khi triển khai callback:

- Gọi callback đúng một lần cho mỗi yêu cầu stop.
- Gọi callback sau khi thành phần đã ngừng nhận công việc và hoàn tất bước dừng được cam kết.
- Bảo đảm callback vẫn được gọi khi cleanup gặp lỗi, nếu không LifecycleProcessor có thể phải chờ tới timeout.
- Ghi nhận lỗi drain/close để vận hành biết shutdown có hoàn tất sạch hay phải bỏ công việc.
- Làm cho start/stop có tính idempotent nếu framework hoặc ứng dụng có thể gọi nhiều lần.

Không gọi callback ngay sau khi lên lịch drain nếu công việc thực tế vẫn đang chạy. Callback chính là tín hiệu đồng bộ giữa thành phần và LifecycleProcessor.

## 5. LifecycleProcessor điều phối toàn bộ thành phần

`LifecycleProcessor` là abstraction quản lý lifecycle beans trong ApplicationContext. Implementation mặc định thường là `DefaultLifecycleProcessor`.

Các trách nhiệm chính:

- Bắt đầu lifecycle components khi context refresh.
- Sắp xếp start theo phase.
- Dừng lifecycle components khi context đóng.
- Sắp xếp stop theo thứ tự phase ngược lại.
- Với SmartLifecycle, chờ callback stop bất đồng bộ trong giới hạn timeout của phase.

Có thể thay đổi cấu hình processor trong các trường hợp đặc biệt, nhưng đa số ứng dụng nên dùng implementation mặc định. Trước khi tự viết LifecycleProcessor, hãy xác định yêu cầu mà phase, callback và timeout tiêu chuẩn chưa đáp ứng được.

### 5.1. Timeout theo phase

Nếu một SmartLifecycle không gọi callback, hoặc drain bị treo, shutdown không thể chờ vô hạn. DefaultLifecycleProcessor có timeout cho việc dừng mỗi phase. Trong Spring Boot, có thể cấu hình thời gian chờ qua:

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Giá trị này áp dụng theo từng phase, không phải một ngân sách tổng duy nhất cho toàn bộ shutdown. Nếu nhiều phase cần dừng, tổng thời gian có thể dài hơn timeout của một phase. Giá trị mặc định và API cấu hình có thể khác theo phiên bản Spring Boot/Spring Framework; kiểm tra tài liệu của release đang dùng.

Timeout không làm cho công việc drain hoàn tất một cách thần kỳ. Nếu timeout hết, processor phải tiếp tục shutdown theo chính sách của framework; thành phần cần tự có timeout nội bộ và xử lý phần công việc chưa hoàn tất.

## 6. Khi nào dùng Lifecycle, SmartLifecycle hay callback hủy bean?

Không phải mọi tài nguyên đều cần SmartLifecycle. Hãy chọn cơ chế theo hành vi mà thành phần cần.

| Nhu cầu | Cơ chế phù hợp | Lý do |
| --- | --- | --- |
| Thành phần có start/stop đơn giản | `Lifecycle` | Hợp đồng tối thiểu |
| Cần tự start, phase và dừng bất đồng bộ | `SmartLifecycle` | Hỗ trợ auto startup, ordering và callback |
| Chỉ cần giải phóng tài nguyên khi bean bị hủy | `@PreDestroy` hoặc destroy method | Không cần mô hình chạy/dừng riêng |
| Muốn Spring gọi callback hủy theo interface | `DisposableBean` | Hợp đồng destruction rõ ràng |
| Cần đóng tài nguyên sau khi ngừng nhận công việc | `SmartLifecycle` kết hợp destruction callback | Tách graceful stop khỏi cleanup cuối cùng |

Ví dụ:

- Message listener container thường có vòng đời start/stop nên phù hợp với Lifecycle.
- Scheduler cần ngừng lên lịch và chờ tác vụ có thể cần SmartLifecycle.
- Một file handle chỉ cần đóng khi bean bị hủy có thể dùng @PreDestroy hoặc destroy method.
- Một HTTP client dùng chung có thể được Spring quản lý bằng bean với close method; nếu nó cần dừng sau consumer, hãy sắp xếp phase/dependency phù hợp.

Nhiều thư viện Spring đã cung cấp bean quản lý lifecycle sẵn. Nếu sử dụng message listener container, scheduler hoặc connection factory do starter tạo, hãy kiểm tra cơ chế shutdown tích hợp trước khi viết một Lifecycle wrapper khác.

## 7. Destruction callback: @PreDestroy, DisposableBean và destroy method

Sau khi lifecycle components được dừng, Spring hủy các singleton bean và gọi các destruction callback được khai báo.

### 7.1. @PreDestroy

`@PreDestroy` đánh dấu method được gọi khi bean bị hủy:

~~~java
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class LocalFileCache {

    private final FileCache cache;

    public LocalFileCache(FileCache cache) {
        this.cache = cache;
    }

    @PreDestroy
    public void close() {
        cache.close();
    }
}
~~~

Với Spring Boot 3, annotation thuộc namespace `jakarta.annotation`. Dự án Boot 2 có thể dùng `javax.annotation` tùy phiên bản và dependency. Không trộn hai namespace.

`@PreDestroy` phù hợp với cleanup đồng bộ, ngắn gọn. Nó không có callback bất đồng bộ để yêu cầu LifecycleProcessor chờ một quá trình drain dài.

### 7.2. DisposableBean

Bean có thể triển khai `DisposableBean`:

~~~java
import org.springframework.beans.factory.DisposableBean;
import org.springframework.stereotype.Component;

@Component
public class TemporaryResourceHolder implements DisposableBean {

    private final TemporaryResource resource;

    public TemporaryResourceHolder(TemporaryResource resource) {
        this.resource = resource;
    }

    @Override
    public void destroy() {
        resource.close();
    }
}
~~~

Spring gọi `destroy()` khi hủy bean. Cách này tạo phụ thuộc trực tiếp vào Spring API, nên nếu muốn lớp domain hoặc thư viện không phụ thuộc Spring, callback annotation hoặc cấu hình bean thường linh hoạt hơn.

### 7.3. Destroy method trên @Bean

Với bean được tạo qua `@Bean`, có thể khai báo method đóng tài nguyên:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ClientConfiguration {

    @Bean(destroyMethod = "close")
    ExternalClient externalClient() {
        return new ExternalClient();
    }
}
~~~

Spring gọi method `close()` khi bean bị hủy. Với nhiều loại bean, Spring có thể suy luận các method tên `close` hoặc `shutdown` theo quy tắc destroy method mặc định. Khai báo tường minh giúp ý định dễ đọc hơn khi có nhiều method cleanup.

### 7.4. Không cleanup cùng một tài nguyên nhiều lần

Một bean có thể vô tình gọi cùng thao tác đóng ở `stop()`, `@PreDestroy` và `DisposableBean.destroy()`. Nếu các callback cùng đóng một socket hoặc pool, có thể phát sinh lỗi double-close hoặc mất thông tin lỗi đầu tiên.

Chọn một nơi chịu trách nhiệm chính cho mỗi giai đoạn:

- Lifecycle stop: ngừng công việc, drain và dừng thành phần.
- Destruction callback: giải phóng tài nguyên cuối cùng còn thuộc quyền sở hữu bean.

Nếu cần gọi close ở nhiều đường do thiết kế thư viện, thao tác close nên idempotent và có trạng thái bảo vệ rõ ràng.

## 8. Thứ tự shutdown và dependency giữa các bean

Khi đóng ApplicationContext, Spring phát sự kiện đóng context và LifecycleProcessor dừng các lifecycle beans. Sau khi dừng lifecycle, container gọi destruction callbacks của các bean.

Thứ tự phase giúp điều phối các thành phần nền. Quan hệ dependency giữa bean cũng quan trọng: một bean sử dụng tài nguyên của bean khác phải dừng trước khi tài nguyên đó bị đóng.

Ví dụ:

~~~mermaid
flowchart TB
    A["Khởi động"] --> B["Phase 0: mở connection manager"]
    B --> C["Phase 100: start message consumer"]
    C --> D["Phase 200: start dispatcher"]
    D --> E["Ứng dụng chạy"]
    E --> F["Shutdown"]
    F --> G["Phase 200: dừng dispatcher"]
    G --> H["Phase 100: stop consumer và drain"]
    H --> I["Phase 0: đóng connection manager"]
    I --> J["Destroy callbacks"]
~~~

Trong ví dụ, dispatcher phụ thuộc consumer; consumer phụ thuộc connection manager. Khi start, hạ tầng mở trước rồi các thành phần sử dụng nó mới chạy. Khi stop, thứ tự đảo ngược.

Đừng dùng phase như một con số tùy ý. Hãy ghi lại dependency thực tế và đặt phase để biểu diễn quan hệ đó. Với những bean phụ thuộc trực tiếp nhau, có thể khai báo dependency trong Spring để container biết thứ tự khởi tạo và hủy phù hợp.

## 9. Graceful shutdown trong Spring Boot

Một ứng dụng web thường cần ngừng nhận request mới và cho request đang xử lý thời gian hoàn tất. Spring Boot hỗ trợ graceful shutdown cho embedded web server.

Ví dụ cấu hình:

~~~yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Khi ApplicationContext bắt đầu đóng, web server tích hợp thực hiện graceful shutdown theo hỗ trợ của server đang dùng: ngừng nhận request mới và cho các request đang xử lý hoàn tất trong khoảng thời gian cho phép. Chi tiết có thể khác giữa Tomcat, Jetty, Reactor Netty và Undertow cũng như phiên bản Boot.

### 9.1. Phối hợp với nền tảng triển khai

Trong Kubernetes hoặc một nền tảng điều phối container, tiến trình thường nhận SIGTERM trước khi bị kết thúc cưỡng bức. Thời gian termination grace của nền tảng phải đủ để ứng dụng:

1. Ngừng nhận traffic mới hoặc chuyển readiness theo chiến lược triển khai.
2. Dừng listener và consumer nhận công việc mới.
3. Drain request/message đang xử lý.
4. Đóng connection, pool, scheduler và tài nguyên còn lại.
5. Thoát trước khi hết thời gian termination grace.

Không đặt timeout của Spring dài hơn thời gian nền tảng cho phép tiến trình sống. Nên dành khoảng dự phòng cho việc dừng JVM và các bước cleanup cuối cùng.

### 9.2. Graceful shutdown không bảo đảm mọi công việc đều hoàn tất

Một request hoặc message có thể vượt quá timeout. Hệ thống cần xác định:

- Có thể retry công việc chưa hoàn tất hay không?
- Message có được ack sau khi xử lý thành công không?
- Có cơ chế visibility timeout hoặc redelivery không?
- Công việc có idempotent để tránh xử lý trùng không?
- Nếu shutdown timeout, dữ liệu đang xử lý được lưu checkpoint hay được đưa lại hàng đợi?

Lifecycle điều phối thời gian dừng; tính đúng đắn của nghiệp vụ khi bị gián đoạn vẫn cần cơ chế retry, transaction và idempotency riêng.

## 10. Kiểm thử lifecycle và destruction

Nên kiểm tra cả thứ tự start/stop và callback hủy. Một test đơn giản có thể dùng `AnnotationConfigApplicationContext` để quan sát vòng đời:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.context.SmartLifecycle;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class ApplicationLifecycleTest {

    @Test
    void startsAndStopsLifecycleBeansByPhase() {
        List<String> events = new ArrayList<>();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {
            context.registerBean("connection", ConnectionLifecycle.class,
                    () -> new ConnectionLifecycle(events));
            context.registerBean("consumer", ConsumerLifecycle.class,
                    () -> new ConsumerLifecycle(events));

            context.refresh();

            assertThat(events).containsExactly(
                    "connection-start",
                    "consumer-start");

        }

        assertThat(events).containsExactly(
                "connection-start",
                "consumer-start",
                "consumer-stop",
                "connection-stop");
    }

    static class ConnectionLifecycle implements SmartLifecycle {
        private final List<String> events;
        private boolean running;

        ConnectionLifecycle(List<String> events) {
            this.events = events;
        }

        @Override
        public void start() {
            events.add("connection-start");
            running = true;
        }

        @Override
        public void stop() {
            events.add("connection-stop");
            running = false;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 0;
        }
    }

    static class ConsumerLifecycle implements SmartLifecycle {
        private final List<String> events;
        private boolean running;

        ConsumerLifecycle(List<String> events) {
            this.events = events;
        }

        @Override
        public void start() {
            events.add("consumer-start");
            running = true;
        }

        @Override
        public void stop() {
            events.add("consumer-stop");
            running = false;
        }

        @Override
        public boolean isRunning() {
            return running;
        }

        @Override
        public int getPhase() {
            return 100;
        }
    }
}
~~~

Ví dụ dùng phase 0 cho connection và phase 100 cho consumer. Khi start, connection bắt đầu trước; khi stop, consumer dừng trước. Có thể bổ sung test cho `stop(Runnable)` để xác nhận callback chỉ được gọi sau khi drain hoàn tất.

### 10.1. Những kịch bản nên kiểm thử thêm

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Context refresh | Bean auto-start được bắt đầu đúng phase |
| Auto startup false | Bean không tự start và có đường start tường minh |
| Stop nhiều lần | Thành phần xử lý trạng thái đã dừng an toàn |
| Stop bất đồng bộ | Callback chỉ được gọi sau khi drain hoàn tất |
| Drain thất bại | Lỗi được ghi nhận và callback không bị bỏ quên |
| Timeout phase | Shutdown không chờ vô hạn |
| Destruction callback | Tài nguyên được đóng đúng một lần |
| Dependency order | Consumer dừng trước connection/pool mà nó dùng |
| SIGTERM | Server ngừng nhận request mới và request đang chạy được drain theo timeout |
| Shutdown cưỡng bức | Message/request chưa hoàn tất có thể retry an toàn |

## 11. Lỗi thường gặp và cách tránh

1. **Đóng connection trước khi dừng consumer:** đặt phase để consumer dừng trước dependency mà nó sử dụng.
2. **Không gọi callback trong stop(Runnable):** LifecycleProcessor phải chờ tới timeout; bảo đảm callback được gọi đúng một lần.
3. **Gọi callback quá sớm:** thành phần vẫn đang drain nhưng context đã chuyển sang phase tiếp theo.
4. **Đặt mọi bean cùng phase:** thứ tự không thể hiện rõ dependency; chia phase theo quan hệ start/stop.
5. **Dùng @PreDestroy để drain bất đồng bộ:** destruction callback không cung cấp cơ chế chờ callback như SmartLifecycle.
6. **Cleanup cùng tài nguyên ở nhiều callback:** chọn trách nhiệm rõ ràng và làm thao tác close idempotent.
7. **Không cấu hình timeout:** shutdown có thể chờ quá lâu hoặc bị nền tảng kết thúc cưỡng bức.
8. **Timeout ứng dụng vượt thời gian termination grace:** tiến trình không đủ thời gian hoàn tất shutdown.
9. **Cho rằng graceful shutdown bảo đảm mọi message hoàn tất:** thiết kế retry, ack, transaction và idempotency cho công việc bị gián đoạn.
10. **Tự quản lý bean đã có lifecycle tích hợp:** kiểm tra starter/framework trước khi viết wrapper trùng lặp.

## 12. Quy trình thiết kế vòng đời cho một dịch vụ Spring Cloud

Khi thêm một consumer, scheduler hoặc tài nguyên dùng chung vào dịch vụ, hãy xác định:

1. Thành phần cần start tự động khi ApplicationContext refresh hay cần lệnh start riêng.
2. Nó phụ thuộc tài nguyên nào và phải start sau thành phần nào.
3. Khi shutdown, nó cần ngừng nhận công việc, drain trong bao lâu và xử lý lỗi ra sao.
4. Có cần SmartLifecycle phase hay chỉ cần Lifecycle đơn giản.
5. Tài nguyên nào được đóng trong stop và tài nguyên nào được giải phóng ở destruction callback.
6. Timeout mỗi phase và timeout tổng của nền tảng triển khai có phù hợp không.
7. Test có xác nhận thứ tự start/stop, callback bất đồng bộ và close resource không.
8. Metric/log có cho biết shutdown thành công, timeout hoặc còn công việc chưa hoàn tất không.

**Điểm ghi nhớ:** `Lifecycle` cung cấp start/stop cơ bản; `SmartLifecycle` bổ sung tự khởi động, phase và callback để điều phối shutdown bất đồng bộ; `LifecycleProcessor` quản lý các thành phần đó trong vòng đời ApplicationContext. Sau khi lifecycle components dừng, `@PreDestroy`, `DisposableBean` hoặc destroy method giải phóng tài nguyên còn lại. Thiết kế tốt phải mở dependency trước khi consumer chạy, dừng consumer trước khi đóng dependency và dành đủ thời gian cho graceful shutdown trong môi trường triển khai của **SPRING_CLOUD_CORE**.
