# Tạo Observation cho listener quan trọng trong Spring Framework Application Events

## 1. Tại sao phải tự tạo Observation cho listener?

Một ứng dụng Spring có thể dùng `ApplicationEventPublisher.publishEvent(...)` để phát sự kiện nghiệp vụ và dùng `@EventListener`, `ApplicationListener` hoặc `@TransactionalEventListener` để xử lý. Listener quan trọng có thể gửi yêu cầu tạo hóa đơn, lập chỉ mục tìm kiếm, đồng bộ đơn hàng, hoặc gọi một hệ thống downstream. Nếu chỉ biết rằng event đã được phát, ta chưa trả lời được những câu hỏi vận hành:

- Listener nào chậm và chậm bao nhiêu?
- Tỷ lệ lỗi của từng loại event là bao nhiêu?
- Một request HTTP chậm vì xử lý chính hay vì một listener chạy đồng bộ?
- Event nào tương ứng với trace hoặc yêu cầu gốc?
- Sau khi chuyển sang async, có còn tìm được quan hệ giữa event và request khởi phát không?
- Listener sau commit lỗi: cơ sở dữ liệu đã commit nhưng tác vụ hậu kỳ thất bại ở đâu?

**Spring Framework không tự phát sinh Observation cho từng lời gọi `@EventListener`.** Tài liệu Spring nêu rằng sự kiện ứng dụng mặc định được publish và xử lý đồng bộ trên cùng thread, nên không có ngữ nghĩa đủ rõ để framework tự instrument mọi listener. Khi có yêu cầu quan sát cụ thể, ứng dụng nên **tạo một Micrometer `Observation` quanh phần xử lý quan trọng**.

Ví dụ cơ bản:

~~~java
@EventListener
public void on(OrderPlaced event) {
    Observation.createNotStarted("app.event.listener", observationRegistry)
        .contextualName("handle OrderPlaced")
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "order-notification")
        .highCardinalityKeyValue("order.id", event.orderId())
        .observe(() -> notificationService.notifyOrder(event.orderId()));
}
~~~

Đây là **đoạn tích hợp**, cần `ObservationRegistry`, `OrderPlaced`, `notificationService`, import và Spring bean tương ứng. `observe(...)` quản lý start, scope, đo thời gian, ghi nhận exception thoát ra và stop; bản thân nó không bảo đảm có metric hay trace nếu registry chưa được cấu hình handler tương ứng.

### Mục tiêu bài học

1. Phân biệt `Observation`, `ObservationRegistry`, `ObservationHandler` và `MeterRegistry`.
2. Ghi thời gian, lỗi và metadata cho **listener quan trọng**, không tạo vô số metric trùng lặp.
3. Dùng low/high cardinality tags đúng cách, tránh biến `orderId` thành metric tag không giới hạn.
4. Tạo ví dụ Java 17 + Spring Framework + Micrometer runnable, kiểm tra hai lần xử lý (thành công/thất bại).
5. Hiểu scope, trace context, async context propagation và giới hạn transaction/event lifecycle.
6. Định nghĩa kiểm thử, dashboard, alert và chính sách lỗi có thể triển khai.

## 2. Mô hình Micrometer Observation

Micrometer cung cấp một abstraction để **instrument một hành động một lần** rồi kết nối nhiều khả năng quan sát tùy cấu hình.

| Thành phần | Vai trò | Điều cần nhớ |
|---|---|---|
| `Observation` | Một lần hoạt động được theo dõi: bắt đầu, kết thúc, lỗi, event, metadata | Có lifecycle riêng, phải stop đúng |
| `ObservationRegistry` | Quản lý cấu hình, handler, filter, predicate, current observation | Nên inject registry được ứng dụng cấu hình |
| `ObservationHandler` | Nhận callback lifecycle để tạo metric, span hoặc hành động khác | Nếu không có handler hữu ích, observation có thể không tạo telemetry |
| `MeterRegistry` | Nơi tạo/lưu/xuất meter như `Timer`, `Counter` | Không đồng nghĩa `ObservationRegistry` |
| `DefaultMeterObservationHandler` | Biến observation thành metric trong `MeterRegistry` | Tạo timer và tags từ key values phù hợp |
| Tracing observation handler | Gắn observation với tracing/span theo backend | Cần bridge/tracer/exporter được cấu hình |
| `Observation.Context` | Metadata và trạng thái của một observation | Không thay thế event payload hoặc repository |

Luồng khái niệm:

~~~text
OrderPlaced event
    |
    v
@EventListener(OrderPlaced)
    |
    +-- Observation.createNotStarted("app.event.listener", registry)
    |       +-- low cardinality: event.type, listener
    |       +-- high cardinality: order.id (khi phù hợp)
    |
    +-- observation.start()
    |       +-- Handler.onStart(...)
    |
    +-- observation.openScope()
    |       +-- xử lý nghiệp vụ
    |       +-- có thể có observation con
    |       +-- nếu lỗi: observation.error(exception)
    |
    +-- đóng scope
    |
    +-- observation.stop()
            +-- Meter handler -> Timer, error tag
            +-- Tracing handler (nếu cấu hình) -> span
~~~

**Observation không phải event nghiệp vụ.** Spring event là thông điệp nội bộ mang ý nghĩa như `OrderPlaced`. Observation mô tả **một lần xử lý** của listener, phục vụ giám sát. Một event có thể dẫn tới ba listener và ba observation khác nhau; một listener cũng có thể nhận lại cùng event nhiều lần khi ứng dụng tự retry.

## 3. Nên instrument ở đâu?

Có ba ranh giới đo khác nhau:

| Ranh giới đo | Bắt đầu / kết thúc | Ý nghĩa |
|---|---|---|
| `publishEvent(...)` của publisher | Trước và sau lời gọi publication | Đo toàn bộ thời gian dispatch theo mô hình đồng bộ; có thể bao gồm nhiều listener |
| Phần thân một `@EventListener` | Bắt đầu và kết thúc handler cụ thể | Đo **thời gian của listener**; phù hợp mục tiêu bài học |
| Công việc async / job / message consumer | Khi worker thực sự nhận và xử lý task | Đo thời gian thực thi worker, không phải thời gian chờ hàng đợi |

Nếu có ba listener và chỉ instrument publisher, một timer `event.publish` không cho biết listener nào chậm. Nếu một listener quan trọng xử lý nhiều giai đoạn như validate → gọi API → ghi DB, có thể thêm observation con cho bước tốn thời gian, nhưng đừng tạo span cho mọi hàm nhỏ.

**Nguyên tắc:** chọn ranh giới mà người vận hành muốn có dashboard/SLO, ví dụ `app.event.listener` cho “xử lý notification theo event”, thay vì chỉ đo mọi method có annotation.

### Đặt tên observation ổn định

~~~java
Observation.createNotStarted("app.event.listener", registry)
    .contextualName("handle OrderPlaced")
    .lowCardinalityKeyValue("event.type", "OrderPlaced")
    .lowCardinalityKeyValue("listener", "notification");
~~~

- Tên `app.event.listener` là **loại hoạt động** ổn định, ít thay đổi qua lần gọi.
- `contextualName` mô tả operation ở mức thân thiện với trace/span; không nên thêm ID động vào tên.
- `event.type` và `listener` có tập giá trị hữu hạn nếu ứng dụng quản lý danh sách loại event/handler.
- Dùng một observation name chung cho một nhóm hoạt động có cùng ý nghĩa, hoặc tách tên nếu contract và dashboard khác hẳn.

Không tạo tên động:

~~~java
// Tránh: một tên Observation/meter cho từng đơn hàng.
Observation.createNotStarted("handle.order." + event.orderId(), registry);
~~~

Cách này làm dữ liệu metric phân mảnh, tăng số series và gây khó tổng hợp.

## 4. Low cardinality và high cardinality: ranh giới cần giữ nghiêm

**Cardinality** là số giá trị khác nhau mà một key có thể nhận.

- **Low-cardinality key values:** nhóm hữu hạn, ví dụ `event.type=OrderPlaced`, `listener=notification`, `result=success|error`, `phase=after_commit`. Handler metric dùng chúng làm tags để phân tách series.
- **High-cardinality key values:** gần như riêng cho từng lần xử lý, ví dụ `order.id`, `event.id`, `request.id`, `user.id`. Không đưa chúng vào metric tags; nếu thật sự cần, cân nhắc high-cardinality metadata cho tracing có kiểm soát và chính sách bảo mật.

Micrometer `DefaultMeterObservationHandler` dùng **low cardinality values** cho meter tags; high cardinality values **không** được dùng làm tags của meter qua handler này. Điều đó bảo vệ registry metric khỏi số chuỗi không giới hạn.

| Key ví dụ | Phân loại gợi ý | Lý do |
|---|---|---|
| `event.type=OrderPlaced` | Low | Số loại sự kiện hữu hạn |
| `listener=order-notification` | Low | Số listener quan trọng hữu hạn |
| `phase=after_commit` | Low | Vài pha transaction |
| `outcome=success|failure` | Low | Tập giá trị nhỏ |
| `tenant.tier=free|pro|enterprise` | Low (nếu kiểm soát danh mục) | Ít giá trị, có ý nghĩa vận hành |
| `order.id=ORD-244` | High | Mỗi đối tượng có giá trị riêng |
| `event.id=UUID` | High | Mỗi event một giá trị |
| `email.address` | Thường **không thu thập** | PII, nhạy cảm và không cần cho timer |
| `exception.message` | **Không làm metric tag** | Có thể chứa ID, URL, dữ liệu nhạy cảm; số giá trị không giới hạn |

Ví dụ API:

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "payment-confirmation")
        .lowCardinalityKeyValue("event.type", "PaymentSucceeded")
        .highCardinalityKeyValue("payment.id", paymentId);
~~~

Đoạn minh họa này chỉ **tạo observation**, chưa start; cần `observation.observe(...)` hoặc `start()/stop()` để hoàn chỉnh.

**Không mặc định high-cardinality metadata luôn an toàn:** trace có thể được xuất ra vendor hoặc lưu dài ngày; hãy áp dụng chính sách masking, sampling và retention. Với ID có thể xác định người dùng, đôi khi chỉ lưu correlation ID đã xử lý phù hợp hoặc không thu thập ID.

## 5. Dùng observe(...) để ghi thời gian và lỗi chuẩn

Micrometer có API:

~~~java
Observation.createNotStarted("app.event.listener", registry)
    .lowCardinalityKeyValue("event.type", "OrderPlaced")
    .observe(() -> importantWork());
~~~

Đối với lambda `Runnable`, `observe(...)` thực hiện:

1. Gọi `start()`, kích hoạt handlers.
2. Mở scope để observation trở thành current observation khi xử lý.
3. Chạy lambda.
4. Nếu lambda ném lỗi, ghi `observation.error(thrown)` rồi **ném lỗi trở lại**.
5. Đóng scope và gọi `stop()` trong mọi trường hợp.

Điều này giúp lỗi không bị che đi: publisher vẫn nhận exception theo đường gọi listener mặc định, còn metric handler có thể ghi nhận nhãn lỗi.

Với hàm trả kết quả, có thể dùng overload nhận `Supplier<T>`:

~~~java
Receipt result = Observation
    .createNotStarted("app.event.listener", registry)
    .observe(() -> receiptService.buildReceipt(event.orderId()));
~~~

Đây là **mã tích hợp** có kiểu `Receipt` và service giả định. Micrometer có overload phù hợp để trả giá trị từ lambda.

### Nếu xử lý lỗi bên trong lambda?

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "notification");

observation.observe(() -> {
    try {
        externalClient.send();
    } catch (IllegalStateException ex) {
        log.warn("External service failed", ex);
        // Không rethrow -> observe(...) thấy lambda hoàn tất bình thường.
    }
});
~~~

Đoạn này là **mã minh họa**. Nếu exception bị bắt và bỏ qua, `observe(...)` không tự biết đó là lỗi. Nếu nghiệp vụ chủ động chấp nhận recover nhưng vẫn muốn ghi error trong observation:

~~~java
observation.observe(() -> {
    try {
        externalClient.send();
    } catch (RuntimeException ex) {
        observation.error(ex);
        fallback.sendLater();
    }
});
~~~

Ở đây các collaborator cần được định nghĩa trong ứng dụng. Chọn cách này khi muốn metric báo lỗi downstream, dù nghiệp vụ xử lý fallback và listener trả về bình thường. Có thể thêm `outcome` tag hữu hạn nếu cần phân biệt `recovered` với `failed`; tránh tự ghi lỗi hai lần nếu exception lại được ném để `observe(...)` tự xử lý.

## 6. Ví dụ runnable: Java 17 + Spring Framework 6.2 + Micrometer

Ví dụ này dùng:

- **Java 17+** và Maven.
- Spring Framework **6.2.8** (`spring-context`).
- Micrometer **1.16.7** (`micrometer-core` và `micrometer-observation`).
- `SimpleMeterRegistry` giữ metrics trong bộ nhớ để xem ngay sau khi phát event.
- `DefaultMeterObservationHandler` biến observations thành `Timer` và tag `error`.

Chương trình tạo một bean `@EventListener` quan trọng, phát một `OrderPlaced` thành công và một `OrderPlaced` có lỗi có chủ đích, rồi kiểm tra các timers. Đây là **minh họa in-process**, không cần Spring Boot, cơ sở dữ liệu, broker, tracing exporter hoặc web server.

### Cấu trúc

~~~text
important-listener-observation/
├── pom.xml
└── src/main/java/demo/ImportantListenerObservationDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>important-listener-observation</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-core</artifactId>
            <version>1.16.7</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.16.7</version>
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
~~~

### src/main/java/demo/ImportantListenerObservationDemo.java

~~~java
package demo;

import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class ImportantListenerObservationDemo {

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            SimpleMeterRegistry meters = ctx.getBean(SimpleMeterRegistry.class);

            // Thành công: handler chạy trong một observation hoàn chỉnh.
            ctx.publishEvent(new OrderPlaced("ORD-OK", false));

            // Lỗi: handler ghi error và ném lại cho publisher.
            try {
                ctx.publishEvent(new OrderPlaced("ORD-FAIL", true));
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }

            long successCount = meters.find("app.event.listener")
                .timers().stream()
                .filter(t -> "none".equals(t.getId().getTag("error")))
                .mapToLong(Timer::count).sum();

            long failureCount = meters.find("app.event.listener")
                .timers().stream()
                .filter(t -> !"none".equals(t.getId().getTag("error")))
                .mapToLong(Timer::count).sum();

            System.out.println("success observations=" + successCount);
            System.out.println("failed observations=" + failureCount);
            System.out.println("total observations=" +
                    (successCount + failureCount));
        }
    }

    public record OrderPlaced(String orderId, boolean fail) {}

    public static final class ImportantOrderListener {
        private final ObservationRegistry registry;

        public ImportantOrderListener(ObservationRegistry registry) {
            this.registry = registry;
        }

        @EventListener
        public void on(OrderPlaced event) {
            Observation.createNotStarted("app.event.listener", registry)
                .contextualName("handle OrderPlaced")
                .lowCardinalityKeyValue("event.type", "OrderPlaced")
                .lowCardinalityKeyValue("listener", "important-order-listener")
                .highCardinalityKeyValue("order.id", event.orderId())
                .observe(() -> {
                    System.out.println("handling=" + event.orderId());
                    if (event.fail()) {
                        throw new IllegalStateException(
                            "simulated downstream failure");
                    }
                });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public SimpleMeterRegistry meterRegistry() {
            return new SimpleMeterRegistry();
        }

        @Bean
        public ObservationRegistry observationRegistry(
                SimpleMeterRegistry meters) {
            ObservationRegistry registry = ObservationRegistry.create();
            registry.observationConfig()
                .observationHandler(
                    new DefaultMeterObservationHandler(meters));
            return registry;
        }

        @Bean
        public ImportantOrderListener importantOrderListener(
                ObservationRegistry registry) {
            return new ImportantOrderListener(registry);
        }
    }
}
~~~

### Chạy chương trình

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImportantListenerObservationDemo
~~~

Các dòng do **mã ứng dụng** in, trong mô hình mặc định đồng bộ:

~~~text
handling=ORD-OK
handling=ORD-FAIL
caught=simulated downstream failure
success observations=1
failed observations=1
total observations=2
~~~

Log phụ thuộc Maven/Spring có thể xuất hiện tùy môi trường; những dòng trên là output của chương trình.

### Phân tích chạy

1. `AnnotationConfigApplicationContext` đăng ký bean listener, `SimpleMeterRegistry` và `ObservationRegistry`.
2. `observationConfig().observationHandler(...)` đưa `DefaultMeterObservationHandler` vào registry, nên observation có đầu ra là metric.
3. Spring phát `OrderPlaced("ORD-OK", false)`; phương thức `@EventListener` gọi `observe(...)`, hoàn tất bình thường. Timer ghi thời gian với tag `error=none`.
4. Sự kiện thứ hai phát vào cùng listener, in `handling=ORD-FAIL`, rồi ném `IllegalStateException`.
5. `observe(...)` ghi error và dừng observation trong `finally`, sau đó exception vẫn đi về caller `publishEvent`. `main` bắt lỗi để tiếp tục đọc metrics.
6. `meters.find("app.event.listener").timers()` trả các `Timer` được tạo cho tên observation. `getTag("error")` phân biệt timer không lỗi với timer lỗi.
7. `successCount=1` và `failureCount=1` xác nhận **hai lần xử lý** được đo. `Timer.count()` là số lần timing được ghi, không phải thời gian thực thi; thời gian có thể đọc qua `Timer.mean(TimeUnit.MILLISECONDS)` hoặc `Timer.max(...)`.

**Giới hạn demo:** `SimpleMeterRegistry` chỉ lưu trong bộ nhớ và không tự xuất số liệu sang Prometheus/Grafana. Mã cũng không tạo distributed traces vì **chưa đăng ký tracing handler**. Không coi việc có Micrometer dependency là mặc định đã có span hoặc exporter.

## 7. Quản lý Observation thủ công bằng start/openScope/error/stop

`observe(...)` là lựa chọn gọn và an toàn khi một đoạn xử lý phù hợp một lambda đồng bộ. Khi cần mở rộng ngữ cảnh xử lý hoặc làm việc với API yêu cầu lifecycle thủ công:

~~~java
Observation observation =
    Observation.createNotStarted("app.event.listener", registry)
        .lowCardinalityKeyValue("listener", "inventory-reservation")
        .lowCardinalityKeyValue("event.type", "OrderPlaced");

observation.start();
try (Observation.Scope scope = observation.openScope()) {
    reserveInventory(orderId);
} catch (RuntimeException ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
~~~

Đây là **mã tích hợp**; `reserveInventory` và `orderId` do ứng dụng định nghĩa. Những quy tắc:

- Gọi `start()` trước khi tính thời gian cần đo.
- Dùng `try-with-resources` để đóng scope dù logic thất bại.
- Gọi `error(ex)` khi exception bị xử lý ở ngoài `observe(...)`, để handler nhận biết lỗi.
- **Luôn gọi `stop()` trong `finally`**. Nếu quên, timer không hoàn chỉnh và scope/metric có thể khó phân tích.
- Không gọi `stop()` hai lần hoặc mở/đóng scope chéo giữa các thread một cách ngẫu nhiên.
- Nếu callback không nên ném lại exception vì chính sách nghiệp vụ, ghi rõ trạng thái recovered/dropped và đảm bảo lỗi vẫn có thể được theo dõi.

Với listener quan trọng đơn giản, ưu tiên `observe(...)` để giảm lỗi quản lý lifecycle.

## 8. Scope, parent observation và liên hệ đến trace

Khi `Observation` được mở scope, những observation được tạo trong cùng ngữ cảnh có thể gắn với observation hiện hành để phản ánh quan hệ cha–con. Trong ứng dụng HTTP được instrument sẵn:

~~~text
http.server.requests
    |
    +-- OrderController -> OrderService
            |
            +-- publishEvent(OrderPlaced)
                    |
                    +-- app.event.listener
                            |
                            +-- http.client.requests (nếu listener gọi HTTP client được instrument)
~~~

Đây là **cấu trúc mong muốn**, không phải output bắt buộc trong mọi cấu hình. Với dispatch đồng bộ mặc định, listener chạy trên thread publisher nên scope/ThreadLocal của Micrometer có thể tồn tại trên cùng đường gọi. Nếu cấu hình tracing phù hợp, span của listener có thể là span con của request hoặc observation bao ngoài.

**Không nhầm:**

- `ObservationRegistry` có **khả năng quản lý observation**, nhưng chưa chắc có `TracingObservationHandler`.
- `MeterRegistry` + `DefaultMeterObservationHandler` tạo metric, **không tự tạo distributed trace**.
- Exporter (OTLP/Zipkin/Prometheus) chỉ có ý nghĩa khi được cấu hình đúng và có backend nhận dữ liệu.
- `contextualName` là tên mô tả operation, không nên gắn ID theo lần xử lý vào tên span.
- Trace sampling có thể khiến không phải event nào cũng xuất hiện trên trace backend, dù metric vẫn ghi ở phía ứng dụng nếu cấu hình tương ứng.

Một observation có thể được xử lý bởi nhiều handler để phát đồng thời metric và tracing. Việc code listener chỉ biết `ObservationRegistry` giúp tách logic nghiệp vụ khỏi backend giám sát.

## 9. Spring Boot và Actuator: nên dùng registry có sẵn

Nếu ứng dụng dùng Spring Boot với Micrometer/Actuator, thường **không cần tự tạo thêm `ObservationRegistry.create()` trong mỗi listener**. Nên inject registry được Boot cấu hình:

~~~java
@Component
public class ImportantPaymentListener {

    private final ObservationRegistry observations;

    public ImportantPaymentListener(ObservationRegistry observations) {
        this.observations = observations;
    }

    @EventListener
    public void on(PaymentCaptured event) {
        Observation.createNotStarted("app.event.listener", observations)
            .contextualName("handle PaymentCaptured")
            .lowCardinalityKeyValue("event.type", "PaymentCaptured")
            .lowCardinalityKeyValue("listener", "payment-receipt")
            .observe(() -> sendReceipt(event.paymentId()));
    }
}
~~~

Đây là **đoạn tích hợp**; cần `@Component`, `@EventListener`, event `PaymentCaptured` và hàm `sendReceipt` của hệ thống. Với Spring Boot, cung cấp dependency `spring-boot-starter-actuator` và cấu hình metric/tracing exporter phù hợp với stack đang dùng. Chính xác bean/handlers nào được auto-configured còn phụ thuộc version, dependency và cấu hình quản lý; không khẳng định chỉ cần actuator là tất cả tracing đã hoạt động.

### Quan sát bằng actuator/metric endpoint

Khi được cấu hình và cho phép truy cập, `/actuator/metrics` có thể liệt kê meter; truy vấn `/actuator/metrics/app.event.listener` nếu meter đã xuất hiện. Với Prometheus registry và actuator endpoint được exposure, tên time series có thể được chuẩn hóa theo quy tắc tên của backend. Không dùng tên dashboard phát sinh từ một phiên bản registry làm contract bất biến giữa mọi monitoring system.

**Bảo mật:** không công khai endpoints quản trị, metric tags, trace links chứa thông tin nội bộ mà thiếu giới hạn quyền truy cập.

### @Observed có thay thế manual instrumentation được không?

Micrometer có annotation `@Observed` cho một số kịch bản AOP; muốn hoạt động phải có **Aspect/Proxy và cấu hình tương ứng**. Nó không phải quy tắc “chỉ gắn annotation lên mọi `@EventListener` là Spring Framework tự động quan sát”. Với listener cần tags theo event payload, error handling và boundary rõ ràng, viết `Observation.createNotStarted(...).observe(...)` ngay ở service/handler vẫn dễ kiểm soát.

Tránh bật AOP observation và bọc cùng phương thức bằng manual observation nếu không có ý định tạo **hai lớp observation**; điều đó có thể khiến dashboard đo trùng.

## 10. Listener đồng bộ, bất đồng bộ và context propagation

Spring Framework mặc định dispatch application events đồng bộ theo thread của publisher. Nhưng ứng dụng có thể:

- Gắn `@Async` lên phương thức `@EventListener` và cung cấp executor.
- Cấu hình custom `ApplicationEventMulticaster` với `TaskExecutor`.
- Tạo job/thread/callback khác ở trong listener.

Khi xử lý chuyển thread, **ThreadLocal-based context, MDC, security context hoặc observation scope không mặc định đi theo**. Vì vậy cần tách hai bài toán:

1. **Instrument worker đúng thời gian thực:** tạo/mở observation khi worker thực sự chạy để đo thời gian xử lý.
2. **Liên kết nó với parent trace của publisher:** truyền context bằng cơ chế được hỗ trợ, hoặc dùng correlation ID trong event payload.

### ContextPropagatingTaskDecorator

Spring Framework cung cấp `ContextPropagatingTaskDecorator`, hỗ trợ cùng Micrometer Context Propagation, để mang context phù hợp từ nơi submit task tới executor worker trong những trường hợp được hỗ trợ. Cần thư viện `io.micrometer:context-propagation` trên classpath và cấu hình executor/task decorator đúng.

Ví dụ **cấu hình tích hợp**:

~~~java
@Bean(name = "eventExecutor")
public ThreadPoolTaskExecutor eventExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(100);
    executor.setThreadNamePrefix("event-worker-");
    executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
    executor.initialize();
    return executor;
}
~~~

Đoạn này cần import `org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor` và `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, cùng bean configuration Spring và dependency propagation. Nếu dùng `@Async("eventExecutor")`, cần `@EnableAsync`/Spring AOP infrastructure hợp lệ và xác nhận lời gọi đi qua proxy. Nó **không tạo transaction DB mới** trong worker và không thay thế delivery bền vững.

### Những nhầm lẫn hay gặp

- “Listener async có cùng ThreadLocal transaction”: **sai**; giao dịch JDBC gắn với thread, nên một worker khác không tự tham gia T1.
- “Đã chuyển trace context thì transaction context cũng được truyền”: **sai**; tracing context propagation không phải transaction propagation.
- “Có correlationId nên đã có span con”: **sai**; correlation ID giúp liên hệ log nghiệp vụ nhưng không tự tạo quan hệ trace/parent span.
- “Metric trong callback HTTP trả về ngay đo cả việc async”: **sai**; observation phải bao quanh công việc ở worker hoặc giai đoạn thực thi cần đo.

Với Reactor/R2DBC, còn có **Reactor Context** thay vì chỉ ThreadLocal. Phải đặt observation đúng vào thời điểm subscribe/execution, không tạo một observation xong rồi stop ngay khi phương thức trả về `Mono` mà pipeline chưa chạy.

## 11. Reactive listener: vì sao không được stop khi mới trả Mono?

Nếu logic listener trả về một publisher, thời điểm **assembly** khác thời điểm **subscription**:

~~~java
// Phản ví dụ khái niệm: chỉ đo lúc tạo Mono, không đo xử lý async thật.
Observation.createNotStarted("app.event.listener", registry)
    .observe(() -> service.processAsync(event)); // Trả Mono, chưa subscribe.
~~~

Nếu chỉ gọi hàm trả `Mono` rồi thoát lambda, observation kết thúc **trước khi xử lý dữ liệu**. Đoạn trên là phản ví dụ và không phải cơ chế `@EventListener` tự động subscribe vào reactive publisher.

Cách thiết kế đúng là **đặt lifecycle observation quanh subscription/execution** và đảm bảo stop ở success/error/cancel, thường bằng helper instrument Reactor phù hợp hoặc composition với `Mono.defer(...)`/`doFinally(...)`/context handling được kiểm thử. Khi cần parent tracing giữa subscriber, dùng Reactor Context propagation phù hợp thay vì dựa vào một scope ThreadLocal được mở khi assembly.

Ví dụ cấu trúc được minh họa ở mức ý tưởng:

~~~text
Mono.defer(...)
  |
  +-- onSubscribe -> tạo/start Observation
  +-- onNext / onComplete / onError -> xử lý và ghi trạng thái
  +-- doFinally(...) -> stop Observation với success/error/cancel
~~~

Không sao chép mô hình `Observation.openScope()` qua ranh giới thread mà không hiểu contract; nhiều ứng dụng nên ưu tiên Micrometer Reactor instrumentation đã được hỗ trợ thay vì tự dựng context propagation phức tạp.

Nếu event được xử lý bằng `@TransactionalEventListener` với **reactive transaction**, transaction context cần có trong **event source** (Spring 6.1+), thường qua `TransactionalEventPublisher`. Điều này **khác** với Observation Context và khác cả việc propagation trace. Ba loại context không được đánh đồng.

## 12. Transaction phase: Observation đo điều gì, không đo điều gì?

Khi listener quan trọng gắn với transaction, thời điểm xử lý là một phần của contract:

| Listener | Khi chạy | Observation thường đo |
|---|---|---|
| `@EventListener` đồng bộ | Ngay lúc publish trong transaction T1 (nếu đang ở T1) | Thời gian listener trong đường gọi publisher |
| `@TransactionalEventListener(BEFORE_COMMIT)` | Trước commit | Thời gian callback chuẩn bị commit |
| `@TransactionalEventListener(AFTER_COMMIT)` | Sau khi commit thành công | Thời gian xử lý hậu commit, **không phải thời gian commit T1** |
| `@TransactionalEventListener(AFTER_ROLLBACK)` | Sau rollback | Thời gian compensation/ghi nhận thất bại |
| `@TransactionalEventListener(AFTER_COMPLETION)` | Sau commit hoặc rollback | Thời gian cleanup/hậu completion |

Ví dụ:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    Observation.createNotStarted("app.event.listener", observations)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "post-commit-indexer")
        .lowCardinalityKeyValue("phase", "after_commit")
        .observe(() -> searchIndexer.refresh(event.orderId()));
}
~~~

Đây là **mã tích hợp** cần bean transaction, event, `ObservationRegistry` và search indexer. Nếu search indexer thất bại, observation có thể ghi lỗi, nhưng transaction T1 đã commit nên exception này **không thể rollback T1**.

Spring Javadoc lưu ý tài nguyên transaction có thể còn bị gắn tạm trong callback completion; thao tác DB hậu commit nếu cần giao dịch mới nên dùng boundary riêng, ví dụ gọi bean khác có `@Transactional(propagation = REQUIRES_NEW)`. Đừng coi “có Observation” là đã tạo transaction, đã commit dữ liệu hay đã publish message bền vững.

### Quan sát và xử lý lỗi độc lập

Đối với email, webhook, message broker hoặc dịch vụ ngoài JVM, hãy tách:

- **Business transaction outcome:** đơn hàng đã commit/rollback ra sao?
- **Listener processing outcome:** tác vụ hậu commit thành công/thất bại?
- **Delivery outcome:** message/notification thực sự tới hệ thống đích chưa?
- **Retry outcome:** tác vụ có đang chờ, đang retry, bị dead-letter hay hoàn tất?

Một timer của listener không tự cho biết message đã được recipient xử lý hoặc có durable retry.

## 13. Thiết kế metrics cho listener quan trọng

Với `DefaultMeterObservationHandler`, một observation tên `app.event.listener` thường tạo `Timer` cùng low-cardinality tags và tag lỗi `error`. Timer giúp đo:

- `count()`: số lần operation đã kết thúc và được ghi timing.
- `totalTime(TimeUnit)`: tổng thời gian đã đo.
- `mean(TimeUnit)`: thời gian trung bình.
- `max(TimeUnit)`: thời gian lớn nhất trong thống kê hiện tại.
- Phân phối percentiles/histogram nếu `MeterRegistry` được cấu hình phù hợp; **không tự coi p95/p99 có sẵn trên mọi registry**.

Ví dụ đọc từ `MeterRegistry`:

~~~java
Timer t = meters.find("app.event.listener")
    .tag("event.type", "OrderPlaced")
    .tag("listener", "important-order-listener")
    .tag("error", "none")
    .timer();

if (t != null) {
    System.out.println(t.count());
    System.out.println(t.mean(TimeUnit.MILLISECONDS));
}
~~~

Đây là đoạn tích hợp, cần import `io.micrometer.core.instrument.Timer` và `java.util.concurrent.TimeUnit`. Nếu meter chưa từng được tạo hoặc chưa có handler metric, `timer()` có thể trả `null`. Không viết code production giả định nó luôn tồn tại.

### Dashboard gợi ý

Đối với một listener quan trọng, dashboard có thể gồm:

1. **Throughput:** số lần xử lý/giây theo `listener` và `event.type`.
2. **Error rate:** số lần lỗi chia cho tổng số lần xử lý, theo cùng hệ tags.
3. **Latency:** p50/p95/p99 nếu histogram/summary và backend được cấu hình; nếu không, hiển thị mean/max với nhãn rõ.
4. **Async queue depth và tuổi tác vụ:** metric riêng từ executor/broker, không lấy từ listener timer.
5. **Success after commit:** tỷ lệ tác vụ hậu commit thực sự hoàn tất, phân biệt thành công nghiệp vụ và hoàn tất callback.
6. **Trace exemplars:** nếu hệ thống metric/tracing tương thích, dùng exemplars/trace ID để drill down chậm.

Đặt ngưỡng alert theo SLO có căn cứ, ví dụ “p95 listener critical tăng bền vững so với baseline” và “error rate vượt mức chấp nhận”; không tạo hàng nghìn alert do mỗi `orderId` một nhãn.

## 14. Một Observation không đồng nghĩa một event

Cần phân biệt các đơn vị đếm:

~~~text
OrderPlaced(eventId=E1)
  |
  +-- Listener A xử lý lần 1 -> Observation A1
  |
  +-- Listener B xử lý lần 1 -> Observation B1
  |
  +-- Listener B retry        -> Observation B2
~~~

Có **một business event occurrence E1**, nhưng **ba lần thực thi listener**. Một dashboard metric listener nên đếm số lần **handler attempt**, không tự coi đó là số event độc nhất.

Muốn biết event đã được xử lý **thành công cuối cùng** sau retry, cần metric/trạng thái riêng: outcome, attempt count, queue acknowledgment hoặc processed event record. Observation là dữ liệu quan sát runtime, không phải durable idempotency store.

Nếu listener ghi `eventId` vào high-cardinality trace metadata, cần cân nhắc bảo mật và sampling. Nếu cần deduplication, lưu trạng thái ứng dụng theo `eventId`/consumer name ở database hoặc hệ thống có durability; **không dùng metric count để chống trùng**.

### Retry và long-running listener

Một retry policy có thể chạy cùng một observation bao tất cả attempts hoặc tạo observation con cho từng attempt. Hai lựa chọn trả lời câu hỏi khác nhau:

- Quan sát **toàn bộ operation**: tổng độ trễ mà caller/worker phải chịu, gồm backoff.
- Quan sát **từng attempt**: tốc độ và lỗi của mỗi lần gọi downstream.
- Cả hai cấp: hữu ích khi cần root cause, nhưng phải phân biệt tên và quan hệ parent/child để tránh tưởng số request nghiệp vụ tăng gấp đôi.

Đừng tạo timer mới với tên động theo số thứ tự retry, ví dụ `retry.1`, `retry.2`, ... không giới hạn; dùng `attempt.bucket`/`outcome` hữu hạn hoặc counter riêng.

## 15. Error recording đúng và không che exception

Một listener có thể gây lỗi mà không ném ra ngoài do chính sách fallback:

~~~java
@EventListener
public void on(OrderPlaced event) {
    Observation obs = Observation.createNotStarted(
        "app.event.listener", observationRegistry)
        .lowCardinalityKeyValue("listener", "post-payment-email");

    obs.observe(() -> {
        try {
            emailGateway.send(event.orderId());
        } catch (RuntimeException ex) {
            obs.error(ex);
            retryStore.enqueue(event.orderId());
        }
    });
}
~~~

Đây là code tích hợp; `emailGateway` và `retryStore` do ứng dụng cung cấp. Nếu enqueue thành công, listener có thể kết thúc mà không throw nhưng observation vẫn ghi nhận lỗi gửi email. Tuy vậy, **nếu chính retryStore thất bại**, exception mới nên được xử lý/ghi nhận riêng, không cố “nuốt hết lỗi để metric luôn xanh”.

Đối với listener có `@TransactionalEventListener(AFTER_COMMIT)`, lỗi callback không rollback commit gốc. Với listener đồng bộ `@EventListener` chạy trong T1, exception không bị bắt có thể làm T1 rollback; **việc thêm Observation không nên vô tình thay đổi chính sách rollback**. `observe(...)` giữ đường lan truyền lỗi ra ngoài, còn `obs.error(...)` chỉ ghi telemetry; nó **không** tương đương `TransactionStatus.setRollbackOnly()`.

## 16. Test metrics và observation đúng ý nghĩa

Một test không nên dựa vào khoảng thời gian cố định như “listener phải chạy đúng 12ms” vì hệ điều hành/JVM có thể thay đổi. Hãy kiểm tra:

1. Listener được gọi đúng với event type và condition.
2. Số lần `Timer.count()` tăng đúng khi handler hoàn tất.
3. Khi handler ném exception, error tag khác `none` và exception vẫn được lan truyền theo dispatch policy.
4. `order.id` **không có trong metric tags** của `DefaultMeterObservationHandler`; key này là high-cardinality metadata.
5. Scope được đóng sau khi xử lý; observation con (nếu có tracing) liên hệ cha–con đúng.
6. Với `@Async`, chờ bằng latch/await condition có timeout, **không assert ngay** sau publish.
7. Với `AFTER_COMMIT`, thực sự commit transaction trong test thay vì giữ test transaction chưa hoàn tất.

### Dùng TestObservationRegistry

Micrometer cung cấp công cụ test chuyên dụng trong module `micrometer-observation-test`, gồm `TestObservationRegistry` và các assertion helpers. Ví dụ cấu hình test có thể:

~~~java
TestObservationRegistry registry = TestObservationRegistry.create();
// Inject registry này vào ImportantOrderListener đang được test.
// Gọi handler rồi kiểm tra Observation context/name/key values/error.
~~~

Đây là **đoạn test minh họa**: cần thêm test dependency và assertion library phù hợp. Không thêm `TestObservationRegistry` vào code runtime của chương trình main nếu chỉ muốn lấy metrics.

### Một integration test về lỗi

Trong demo mục 6, handler ném `IllegalStateException` khi `fail=true`. Test có thể assert:

- `assertThrows(IllegalStateException.class, () -> ctx.publishEvent(...))` nếu dispatcher đồng bộ mặc định và không có ErrorHandler nuốt exception.
- `successCount == 1` và `failureCount == 1`.
- Những timer có tag `listener=important-order-listener` và `event.type=OrderPlaced`.
- Không có metric series với tag `order.id=ORD-OK` hoặc `ORD-FAIL`.

Nếu ứng dụng đổi sang dispatcher bất đồng bộ, test cần thay cách chờ và quan sát lỗi theo executor/worker. Không đem assertion về thứ tự synchronous vào test async.

### Kiểm thử transaction phase

Một test có `@Transactional` do Spring Test quản lý thường rollback cuối test. Để kiểm tra `@TransactionalEventListener(AFTER_COMMIT)`, cần commit thật (`TestTransaction.flagForCommit()` và `TestTransaction.end()` khi phù hợp) hoặc gọi service bean có transaction riêng từ test method không transactional. Nếu không, listener sau commit không chạy, nên timer của nó cũng không xuất hiện.

## 17. Hiệu năng: instrument hợp lý và hạn chế telemetry bùng nổ

Observation có overhead: tạo context, gọi handlers, có thể tạo metric, span, serialize tags và xuất dữ liệu. Trong listener cực nóng (hàng trăm nghìn events/giây), cần cân nhắc:

- Chỉ instrument **listener quan trọng** hoặc boundary có giá trị SLO/điều tra sự cố.
- Đặt tên và low-cardinality tags có danh mục được kiểm soát.
- Cấu hình sampling cho traces; metric thường được tổng hợp nên có thể ghi số lượng khác với sampled spans.
- Tránh ghi stack trace vào mỗi observation thành công; chỉ log lỗi có mục đích.
- Không đưa body, token, email, số điện thoại, thông tin thanh toán hay PII vào tags.
- Nếu handler quan sát phát lỗi, phải hiểu chính sách của registry/handler; observability không nên làm hỏng business flow chỉ vì backend telemetry gặp sự cố.
- Giám sát chi phí số time series theo tích các chiều tags (`event.type × listener × phase × outcome × region`).
- Tạo một shared `ObservationRegistry` được cấu hình thay vì tạo `ObservationRegistry.create()` bên trong mỗi callback.

Micrometer có `ObservationPredicate` để cho phép/tắt observation theo tên/context và `ObservationFilter` để bổ sung/chỉnh metadata. Đây là lựa chọn khi cần chính sách chung. Đừng chỉnh global config theo từng request hoặc thêm tag động không giới hạn.

## 18. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
|---|---|---|
| Nghĩ rằng `@EventListener` tự được instrument | Framework không tự tạo Observation cho mỗi event listener | Instrument listener trọng yếu bằng `Observation` |
| Tạo observation nhưng không `start()/observe()` | Không có lifecycle đo hữu ích | Dùng `observe(...)` hoặc start/scope/stop đầy đủ |
| Chỉ có `ObservationRegistry` nhưng không handler | Không có metric/trace backend tương ứng | Cấu hình `DefaultMeterObservationHandler` hoặc tracing handlers |
| Nhầm `MeterRegistry` với `ObservationRegistry` | Chức năng khác nhau | Kết nối qua observation handler |
| Dùng `order.id` làm low-cardinality tag | Metric cardinality bùng nổ | Đưa ID vào high-cardinality context nếu phù hợp |
| Ghi exception message thành tag | Biến động/PII/không giới hạn | Dùng error class/outcome hữu hạn |
| Catch lỗi bên trong lambda rồi không `obs.error(ex)` | Metric báo thành công dù downstream lỗi | Ghi error có chủ đích, phân biệt recovered |
| Stop observation khi vừa tạo `Mono` | Đo assembly chứ không đo execution | Instrument khi subscribe và stop ở terminal signal |
| Xem timer listener là thời gian commit | Listener có phase khác transaction | Tạo đo riêng ở transaction/DB nếu cần |
| `@Async` nhưng vẫn kỳ vọng parent trace tự đi theo | Mất ngữ cảnh khi đổi thread | Dùng context propagation/correlation đúng |
| Nghĩ observation tự rollback transaction | Telemetry không phải transaction manager | Để rollback rules/phase quyết định |
| Dùng metric count để dedupe event | Count không phải durable storage | eventId/idempotency store |
| Tin timer sẽ tự có p95/p99 | Cần cấu hình phân phối/backend | Bật histogram/SLO buckets phù hợp |
| Lộ email/token trong span | Rủi ro dữ liệu nhạy cảm | Giảm hoặc mask metadata trước khi xuất |
| Double instrumentation khi bật AOP/manual | Dễ đếm trùng hoặc tăng overhead | Định nghĩa một ranh giới và ownership rõ |

## 19. Checklist triển khai và vận hành

1. **Listener nào thực sự quan trọng?** Gắn với SLO như email thanh toán, đồng bộ ledger, indexer hay fulfillment.
2. **Boundary đo ở đâu?** Publisher, listener, downstream attempt hay job worker?
3. **Tên observation có ổn định không?** Ví dụ `app.event.listener`, không chứa ID.
4. **Low-cardinality tags hữu hạn chưa?** Loại event, tên listener, phase, outcome.
5. **High-cardinality/PII đã xử lý an toàn chưa?** Không lộ dữ liệu vào metric labels hoặc trace backend không được phép.
6. **Registry có handler không?** Metric, tracing, exporter nào đã được cấu hình?
7. **Lỗi có được ghi đúng không?** Exception throw, catch/recover, timeout/cancel được phân biệt.
8. **Sync/async có được xác định?** Dispatch strategy, executor, context propagation.
9. **Transaction phase có đúng?** Quan sát hậu commit không đồng nghĩa rollback hoặc delivery.
10. **Dashboard có giúp hành động không?** Throughput, error rate, latency, backlog và trace drill-down.
11. **Test đã xác nhận count/error/tags chưa?** Có nhánh success, error, async, rollback.
12. **Đã có cơ chế retry/durable delivery chưa?** Observation chỉ nói “đã xảy ra gì”, không tự cứu các tác vụ thất bại.

## 20. Tổng kết

Để theo dõi listener quan trọng trong Spring Framework Application Events, **tạo `Observation` trực tiếp quanh phần xử lý** bằng `ObservationRegistry`. Dùng `Observation.createNotStarted("app.event.listener", registry)`, gắn low-cardinality tags như loại event và tên listener, đặt high-cardinality metadata có kiểm soát như ID nghiệp vụ, rồi chạy `observe(...)` hoặc quản lý start/scope/error/stop đúng lifecycle.

Với `DefaultMeterObservationHandler`, Observation có thể tạo `Timer` và phân biệt thành công/lỗi; tracing chỉ xuất hiện khi có tracing handler và exporter phù hợp. Chú ý ranh giới giữa listener đồng bộ, `@Async`, Reactor và `@TransactionalEventListener`: một observation không thay đổi giao dịch, không tự truyền context qua mọi thread và không tạo durable message delivery. Hãy dùng metrics/traces để phát hiện và chẩn đoán sự cố, còn retry, idempotency, outbox và transaction boundaries để giải quyết tính đúng đắn nghiệp vụ.

### Tài liệu chính thức để đối chiếu

- [Spring Framework — Observability Support, Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html) — Spring không tự instrument từng @EventListener; context propagation khi async.
- [Micrometer Reference — Observation Components](https://docs.micrometer.io/micrometer/reference/observation/components.html) — lifecycle, handler, metric timer, low/high cardinality.
- [Micrometer Reference — Introduction to Observation](https://docs.micrometer.io/micrometer/reference/observation/introduction.html) — `observe(...)`, errors và tag conventions.
- [Micrometer Reference — Instrumenting Code](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html) — ngữ cảnh, handler và đặt tên.
- [Spring Framework Reference — Context Propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html) — `ContextPropagatingTaskDecorator` trong event listeners async.
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — các pha transaction của `@TransactionalEventListener`.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html) — registry/metrics/exporter khi dùng Spring Boot.
