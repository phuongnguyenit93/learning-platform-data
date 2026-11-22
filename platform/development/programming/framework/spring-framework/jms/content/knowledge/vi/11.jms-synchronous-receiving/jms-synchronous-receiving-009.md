# Tiêu chí chọn polling đồng bộ hay listener bất đồng bộ trong Spring JMS

## 1. Hai cách nhận JMS và câu hỏi cần quyết định

Một ứng dụng Spring có queue `orders.in` chứa các sự kiện đơn hàng. Nhóm phát triển phải chọn cách lấy message:

- **Polling đồng bộ:** ứng dụng chủ động gọi `JmsTemplate.receive(...)` hoặc `receiveAndConvert(...)` tại một thời điểm do mình chọn. Thread gọi chờ broker trả về message hoặc hết timeout.
- **Listener bất đồng bộ:** đăng ký `@JmsListener`; Spring quản lý một **message listener container** để liên tục nhận message và gọi phương thức xử lý mỗi khi có message phù hợp. Luồng nghiệp vụ không phải tự gọi `receive` trong vòng lặp.

Cả hai đều sử dụng Jakarta Messaging (JMS) và đều có thể nhận từ cùng loại queue/topic khi cấu hình đúng. Khác biệt chính là **ai sở hữu vòng đời nhận message, khi nào được phép nhận, cách cấp thread, điều tiết tải, quản lý acknowledgment/transaction và phục hồi sự cố**.

Một cách hình dung:

```text
POLLING ĐỒNG BỘ                          LISTENER BẤT ĐỒNG BỘ
----------------                          -------------------
Scheduler / batch job                     Spring JMS listener container
      |                                              |
      | (đến giờ chạy)                              | (duy trì consumer)
      v                                              v
JmsTemplate.receive(queue)                 nhận message qua JMS
      |                                              |
      | block <= receiveTimeout                      v
      v                                      @JmsListener handler(...)
message hoặc null                                  |
      |                                              v
      v                                       xử lý + ack/transaction
business handler
      |
đợi lần poll kế tiếp
```

**Quan trọng:** “listener bất đồng bộ” là cách **ứng dụng được gọi theo sự kiện**; không có nghĩa bên dưới broker luôn dùng cơ chế push không polling. `DefaultMessageListenerContainer` của Spring có thể sử dụng các vòng gọi `MessageConsumer.receive()` trên những thread do container quản lý. Vì vậy nên so sánh **hợp đồng ứng dụng và vận hành**, không phải chỉ so sánh một nhãn “polling vs push”.

### Kết quả học tập

Sau bài, bạn có thể chọn giải pháp theo SLA độ trễ, tần suất message, khoảng thời gian được phép chạy, lượng thread/connection, burst và backpressure, transaction/redelivery, yêu cầu thứ tự, giám sát và khả năng vận hành. Bạn cũng sẽ viết được ví dụ Java 17+ cho cả hai hướng và biết các bẫy khi chuyển từ một hướng sang hướng kia.

## 2. JmsTemplate.receive: polling đồng bộ thực chất là gì?

Trong Spring Framework 6.x, `org.springframework.jms.core.JmsTemplate` có các phương thức như:

```java
jakarta.jms.Message receive(String destinationName);
Object receiveAndConvert(String destinationName);
```

Các chữ ký rút gọn trên dùng để minh họa; nullability và overload đầy đủ xem Javadoc.

- `receive(...)` trả về một JMS `Message`, chẳng hạn `TextMessage`.
- `receiveAndConvert(...)` dùng `MessageConverter` đã cấu hình và trả về object Java; với `SimpleMessageConverter` mặc định, `TextMessage` thường chuyển thành `String`.
- Cả hai có thể trả `null` khi **hết thời gian chờ mà không có message**.
- Spring quản lý JMS connection/session/consumer cho thao tác của template và chuyển `JMSException` thích hợp thành `JmsException` unchecked.
- Method chỉ kết thúc khi nhận được message, timeout hoặc phát sinh lỗi; thread gọi **bị chiếm dụng** trong khoảng chờ.

### 2.1. receiveTimeout: điều kiện sống còn

`JmsTemplate` có cấu hình:

```java
template.setReceiveTimeout(1_000L); // tối đa khoảng 1 giây chờ message
```

Ý nghĩa trong Spring `JmsTemplate`:

| Giá trị | Hành vi |
| --- | --- |
| `-1`, mặc định `RECEIVE_TIMEOUT_INDEFINITE_WAIT` | Chờ **vô hạn** cho tới khi có message hoặc một sự kiện khác giải phóng thao tác |
| `0`, `RECEIVE_TIMEOUT_NO_WAIT` | Thử nhận ngay, **không chờ** nếu chưa có message |
| Số dương, ví dụ `1_000` | Chờ tối đa khoảng 1.000 ms cho một lần nhận |
| Giá trị âm khác `-1` | Được `JmsTemplate` coi như nhánh không chờ; không nên dùng số âm tùy ý khó hiểu |

Không lẫn quy ước timeout của `JmsTemplate` với quy ước của API `MessageConsumer.receive(long)`: ở API JMS thuần, tham số `0` của `receive(0)` mang nghĩa chờ vô hạn, còn Spring `JmsTemplate.setReceiveTimeout(0)` có nghĩa **no-wait**.

**Sai lầm có tác động lớn:** dùng `receive(...)` mặc định ở một thread xử lý HTTP request hoặc một `@Scheduled` job rồi tưởng nó trả về ngay khi queue trống. Nếu không có message, method có thể bị chặn vô hạn. Hãy đặt timeout hữu hạn hoặc dùng cấu hình no-wait có chủ đích.

### 2.2. Polling không nhất thiết đồng nghĩa busy-wait

Mẫu không tốt:

```java
while (true) {
    Object message = template.receiveAndConvert("orders.in");
    // Nếu receiveNoWait và không có backoff, có thể lặp rất nhanh.
}
```

Đây là **phản ví dụ**, không phải chương trình chạy riêng. Poll liên tục với no-wait có thể làm nóng CPU, tăng số lần gọi/bộ nhớ cấp phát và tạo tải vô ích lên broker. Một poller tốt phải có **lịch chạy, timeout, giới hạn số message mỗi lượt và chiến lược nghỉ/backoff**.

Nếu lịch là 5 giây và mỗi lần chỉ lấy tối đa một message, thì ngay cả khi queue backlog lớn, throughput của lịch có thể rất thấp. Ngược lại, nếu một lần poll xử lý một batch hàng nghìn message, phải kiểm soát giới hạn thời gian, transaction boundary và shutdown của batch đó.

## 3. @JmsListener: nhận bất đồng bộ theo góc nhìn ứng dụng

Trong Spring JMS, ví dụ cơ bản:

```java
@JmsListener(destination = "orders.in")
public void onOrder(String payload) {
    orderHandler.handle(payload);
}
```

Đây là **method trong một Spring-managed bean**, với biến `orderHandler` đã được inject. Spring quét annotation, tạo endpoint và dùng `JmsListenerContainerFactory` để khởi tạo listener container. Container phụ trách lấy connection/session/consumer, dispatch message, threading và phần lớn xử lý khôi phục.

Một bean listener có thể luôn sẵn sàng nhận message khi container đang chạy. Khi message tới, framework gọi handler mà không đợi scheduler của ứng dụng đến lượt poll tiếp theo.

**Không nhầm hai khái niệm:**

- **Producer asynchronous send:** dùng `CompletionListener` để được báo kết quả gửi.
- **Consumer asynchronous listener:** dùng `@JmsListener`/listener container để xử lý message nhận được mà code nghiệp vụ không tự gọi `receive`.

`@JmsListener` không tự biến handler thành non-blocking: nếu handler gọi database hoặc HTTP chậm, thread của listener container vẫn bị chiếm dụng trong lúc xử lý. Concurrency và số consumer quyết định throughput, còn ack/transaction quyết định hành vi khi lỗi.

### 3.1. Container làm gì thay ứng dụng?

Với `DefaultMessageListenerContainer`, Spring có khả năng:

- Duy trì số consumer/thread theo cấu hình, hỗ trợ tăng giảm số consumer trong các giới hạn.
- Nhận message qua JMS provider và gọi đúng handler.
- Tạo/giải phóng tài nguyên JMS theo lifecycle container; khôi phục khi kết nối broker tạm thời lỗi.
- Tích hợp transaction, acknowledge mode và chuyển lỗi vào cơ chế container.
- Hỗ trợ start/stop hoặc quản lý endpoint qua `JmsListenerEndpointRegistry`.

Nhưng ứng dụng vẫn phải thiết kế **idempotency, xử lý Poison Message/DLQ, timeout của dependency, kiểm soát dữ liệu, observability và bảo đảm thứ tự nghiệp vụ**. Listener container không tự bảo đảm exactly-once end-to-end.

## 4. Bảng quyết định: nên chọn giải pháp nào?

| Tiêu chí | Polling đồng bộ (`JmsTemplate.receive`) | Listener bất đồng bộ (`@JmsListener`) |
| --- | --- | --- |
| **Ai kích hoạt?** | Scheduler, batch, lệnh của admin hoặc workflow chủ động gọi | Listener container duy trì việc nhận khi endpoint đang chạy |
| **Độ trễ mong muốn** | Chấp nhận trễ theo khoảng poll và thời gian chờ | Phù hợp mục tiêu phản ứng sớm khi message khả dụng |
| **Khối lượng message** | Ít, theo đợt, có thể gom batch/giới hạn lượng xử lý | Ổn định hoặc liên tục, cần xử lý backlog và điều chỉnh concurrency |
| **Giờ hoạt động** | Hợp khi chỉ được xử lý trong maintenance window hoặc theo lịch rõ | Hợp khi consumer cần sẵn sàng hầu như liên tục |
| **Backpressure** | Rõ ràng qua số lần poll/batch limit và lịch chạy | Cần cấu hình concurrency, số consumer, luồng xử lý, pause/stop |
| **Chi phí thread** | Thread chỉ chiếm khi chạy; nhưng `receive` có thể block | Có thread và JMS consumer tồn tại thường xuyên, kể cả lúc ít tải |
| **Transaction/ACK** | Phải chủ động gói receive **và** xử lý trong transaction nếu cần rollback | Listener container có điểm tích hợp transaction thuận tiện hơn |
| **Khả năng phục hồi** | Lịch chạy và lỗi/retry do code/scheduler điều phối | Container có cơ chế recovery cho lỗi kết nối; lỗi nghiệp vụ vẫn phải xử lý |
| **Mở rộng** | Tăng số job/worker nhưng dễ cạnh tranh và có vấn đề lịch chạy | Cấu hình concurrency, tăng replica; cần kiểm soát thứ tự và tài nguyên |
| **Vận hành** | Quan sát số lượt poll rỗng, số lần poll, thời gian/batch | Quan sát container running, active consumers, retries, backlog, handler failures |
| **Độ phức tạp nội bộ** | Ít hạ tầng lúc đầu nhưng dễ phải tự viết vòng lặp, backoff, shutdown | Spring quản lý hạ tầng nhận, phải hiểu lifecycle và consumer concurrency |
| **Sự phụ thuộc vào broker** | Cần broker khi poll, không có message thì null hoặc block | Cần broker khi listener active; lúc mất broker container phục hồi theo chính sách |

**Kết luận thực dụng:** nếu requirement là “có message thì xử lý sớm, chạy 24/7 và lượng message có thể thay đổi”, **ưu tiên listener container**. Nếu requirement là “chỉ xử lý khi job được bật, tối đa N message mỗi đợt, hoặc chỉ chạy trong giờ được phép”, **polling có kiểm soát** thường phù hợp hơn.

Đây không phải xếp hạng “listener luôn đúng, polling luôn sai”. Polling cho quyền quyết định chính xác *khi nào* tiêu thụ; listener giảm lượng hạ tầng phải tự duy trì và thường tốt hơn cho xử lý sự kiện liên tục.

## 5. Sáu câu hỏi chọn hướng khi thiết kế hệ thống

### 5.1. Message phải được xử lý nhanh đến mức nào?

Nếu có SLA xử lý vài giây và queue có message bất chợt, polling theo chu kỳ vài chục giây tạo độ trễ không cần thiết. Khi polling theo lịch, độ trễ chờ thêm phụ thuộc **pha đến của message so với lịch**, thời gian xử lý các lượt trước và tải scheduler. Không lấy công thức trung bình đơn giản làm SLA nếu có burst hoặc job chạy lâu.

Nếu nghiệp vụ cho phép tổng hợp vào cuối giờ/ngày, polling theo batch có thể dễ kiểm soát hơn.

### 5.2. Có cần chủ động tạm dừng nhận theo cửa sổ thời gian không?

Ví dụ chỉ nhập dữ liệu vào hệ thống cũ từ 01:00 đến 02:00: scheduler poll trong cửa sổ đó là biểu đạt tự nhiên. Một listener vẫn có thể tạm dừng bằng start/stop container và lịch, nhưng cần quy tắc drain in-flight message và xử lý shutdown; không phải đơn giản hơn trong mọi trường hợp.

### 5.3. Backlog tăng đột biến thì hệ thống phản ứng ra sao?

Listener có thể mở rộng số consumer đến ngưỡng đã cấu hình, nhưng quá nhiều consumer có thể làm quá tải database/API phía sau. Poller có thể cố tình giới hạn số message mỗi lượt để bảo vệ hệ thống phụ thuộc, nhưng nếu tốc độ lấy chậm hơn tốc độ gửi liên tục thì backlog sẽ tăng.

Cần đo **arrival rate**, **processing rate**, độ trễ theo tuổi message, số message pending/in-flight, lỗi/rollback. Dùng **capacity planning** để chọn concurrency hoặc batch size, không suy luận chỉ từ tổng số queue message.

### 5.4. Xử lý phải rollback/redeliver khi lỗi không?

Nếu bắt buộc “business handler thất bại thì message còn để xử lý lại”, phải kiểm tra ranh giới receive/ack/transaction. Với `JmsTemplate.receiveAndConvert(...)` dùng ngoài transaction, message có thể đã được ACK/commit **trước** khi code phía sau xử lý xong. Listener container dùng JMS transaction đúng cấu hình có thể rollback khi handler ném exception.

Không kết luận “listener = at-least-once” nếu container đang dùng AUTO_ACK hoặc callback tự nuốt exception; cấu hình mới quyết định.

### 5.5. Có yêu cầu đúng thứ tự theo một đối tượng không?

Dù polling chạy một thread hoặc listener `concurrency = 1`, vẫn có thể có **nhiều instance ứng dụng, producer khác session, priority khác nhau, redelivery** khiến thứ tự business phức tạp. Không dùng “một thread” làm bảo đảm toàn cục. Khi cần thứ tự, nên dùng `aggregateId`, `sequence/version`, idempotency và kiểm soát commit theo aggregate.

### 5.6. Ai vận hành restart/stop/retry?

Nếu là job chạy định kỳ do scheduler ngoài Kubernetes/CronJob quản lý, polling dễ gắn vào vòng đời job. Nếu là dịch vụ nhận message liên tục, listener container có sẵn lifecycle/recovery giảm đáng kể code tự viết.

Tuy nhiên phải có operational runbook cho cả hai: mất broker, sai credentials, queue không tồn tại, consumer kẹt, message lỗi lặp, backlog vượt ngưỡng, deployment/scale-down và DLQ.

## 6. Ví dụ Spring Boot 3.x/Java 17+: một nghiệp vụ, hai chế độ nhận

Dưới đây là một dự án mẫu sử dụng ActiveMQ Artemis và queue `orders.in`, tách hai chế độ bằng **Spring profiles** để không chạy poller và listener cạnh tranh nhau trên cùng queue trong lúc thực hành.

- Profile `publish`: gửi một event test.
- Profile `poll`: mỗi lượt schedule gọi `JmsTemplate.receiveAndConvert`.
- Profile `listener`: dùng `@JmsListener` do Spring quản lý.

Broker phải chạy, tài khoản JMS có quyền và queue `orders.in` phải tồn tại. Các đoạn là file Java đầy đủ trong **project Spring Boot đã cấu hình Gradle**, không thể biên dịch riêng bằng `javac` khi thiếu các dependency Spring/JMS.

### 6.1. Dependency và kết nối

Trong `build.gradle` (Groovy DSL) của dự án Spring Boot 3.x có plugin Boot và dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Dùng Java 17+ và Gradle wrapper của project. Tạo `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    queue: "${JMS_QUEUE:orders.in}"
  poll:
    fixed-delay-ms: 5000
    receive-timeout-ms: 1000
```

Đừng ghi password thật trong repository. Cấu hình tên queue chỉ là tên để resolve `Destination`, **không đảm bảo broker sẽ tự provision queue vật lý**. Hai profile phải nhắm **cùng broker và cùng queue type** để quan sát đúng.

### 6.2. Application bật listener và scheduler

File `src/main/java/demo/receive/ReceiveApplication.java`:

```java
package demo.receive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableJms
@EnableScheduling
public class ReceiveApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReceiveApplication.class, args);
    }
}
```

Trong Spring Boot, hạ tầng listener thường đã được auto-configure khi có JMS. `@EnableJms` được thêm tường minh để giải thích ví dụ, còn `@EnableScheduling` dùng cho poller. Việc bật scheduling không khiến listener nhận message theo lịch: hai cơ chế vẫn độc lập.

### 6.3. Handler chung

File `src/main/java/demo/receive/OrderHandler.java`:

```java
package demo.receive;

import org.springframework.stereotype.Service;

@Service
public class OrderHandler {

    public void handle(String payload) {
        if (payload == null || !payload.startsWith("OrderCreated:")) {
            throw new IllegalArgumentException("Unsupported order event");
        }
        System.out.println("Xử lý sự kiện: " + payload);
    }
}
```

Handler demo chỉ in log, chưa có database. Production cần một thao tác idempotent và transaction boundary rõ ràng; việc in dòng “Xử lý” không tự chứng minh nghiệp vụ đã commit.

### 6.4. Cấu hình JmsTemplate dành riêng cho polling

File `src/main/java/demo/receive/PollingJmsConfiguration.java`:

```java
package demo.receive;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;

@Configuration(proxyBeanMethods = false)
@Profile("poll")
public class PollingJmsConfiguration {

    @Bean("pollingJmsTemplate")
    public JmsTemplate pollingJmsTemplate(
            ConnectionFactory connectionFactory,
            @Value("${app.poll.receive-timeout-ms}") long timeoutMs) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setReceiveTimeout(timeoutMs);
        return template;
    }
}
```

Lợi ích của template riêng:

- Cấu hình `receiveTimeout` cho poller mà không đổi một `JmsTemplate` khác đang dùng để gửi.
- Dùng cùng `ConnectionFactory` Spring Boot đã chuẩn bị.
- Cố định timeout **hữu hạn** 1 giây trong ví dụ, tránh block job vô hạn.

**Lưu ý:** cấu hình này chỉ nhằm mô tả polling cơ bản. Nó **chưa** mở transaction bao quanh cả việc nhận và xử lý message. Vì vậy chưa phù hợp cho nghiệp vụ cần retry chắc chắn sau khi handler lỗi.

### 6.5. Poller nhận tối đa một message mỗi lượt

File `src/main/java/demo/receive/OrderPoller.java`:

```java
package demo.receive;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@Profile("poll")
public class OrderPoller {
    private final JmsTemplate template;
    private final OrderHandler handler;
    private final String queue;

    public OrderPoller(
            @Qualifier("pollingJmsTemplate") JmsTemplate template,
            OrderHandler handler,
            @Value("${app.jms.queue}") String queue) {
        this.template = template;
        this.handler = handler;
        this.queue = queue;
    }

    @Scheduled(fixedDelayString = "${app.poll.fixed-delay-ms}")
    public void pollOnce() {
        Object value = template.receiveAndConvert(queue);
        if (value == null) {
            // Queue trống hoặc hết receiveTimeout; không phải exception.
            return;
        }
        if (!(value instanceof String text)) {
            throw new IllegalArgumentException("Expected TextMessage");
        }
        handler.handle(text);
    }
}
```

Cách chạy:

- Với `fixedDelay`, lần tiếp theo bắt đầu **sau khi** lần thực thi trước kết thúc cộng thêm 5 giây, không phải cứ đúng mốc đồng hồ mỗi 5 giây.
- Mỗi lần chỉ nhận tối đa **một** JMS message.
- Nếu queue rỗng, `receiveAndConvert` có thể chờ đến 1 giây rồi trả `null`.
- Nếu listener có profile khác được bật đồng thời, hai consumer có thể cạnh tranh lấy message cùng queue — **không nhân đôi mỗi message theo kiểu fan-out**.

Nếu muốn xử lý batch, hãy thêm giới hạn rõ ràng về **số message, thời gian, memory và policy lỗi**; đừng viết vòng `while(true)` vô hạn trong `@Scheduled` method.

### 6.6. Listener không cần tự gọi receive

File `src/main/java/demo/receive/OrderListener.java`:

```java
package demo.receive;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("listener")
public class OrderListener {
    private final OrderHandler handler;

    public OrderListener(OrderHandler handler) {
        this.handler = handler;
    }

    @JmsListener(destination = "${app.jms.queue}", concurrency = "1")
    public void onMessage(String body) {
        handler.handle(body);
    }
}
```

Spring tự đăng ký endpoint thông qua `JmsListenerContainerFactory`. Với starter JMS và Spring Boot auto-config, listener container được tạo tự động nếu chưa có factory tự định nghĩa; Boot 3.4 mặc định cấu hình listener factory theo cơ chế transactional (JTA nếu phù hợp, nếu không dùng local session transaction). **Không áp đặt default này cho mọi phiên bản Spring Boot hoặc custom factory**: hãy kiểm tra cấu hình thật của ứng dụng.

`concurrency = "1"` chỉ giới hạn container của endpoint ở **một concurrent consumer theo cấu hình của chính endpoint**. Nếu ứng dụng scale nhiều replica, vẫn có nhiều consumer tổng cộng. Nó không biến queue thành một thứ tự business global, và không giúp throughput cao khi handler quá chậm.

### 6.7. Producer thử nghiệm riêng để đưa message vào queue

File `src/main/java/demo/receive/PublishRunner.java`:

```java
package demo.receive;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publish")
public class PublishRunner implements ApplicationRunner {
    private final JmsTemplate template;
    private final String queue;

    public PublishRunner(
            JmsTemplate template,
            @Value("${app.jms.queue}") String queue) {
        this.template = template;
        this.queue = queue;
    }

    @Override
    public void run(ApplicationArguments args) {
        template.convertAndSend(queue, "OrderCreated:order-42");
        System.out.println("Đã gọi gửi: OrderCreated:order-42");
    }
}
```

Vì profile `publish` không kích hoạt `PollingJmsConfiguration`, Spring Boot có thể auto-configure `JmsTemplate` mặc định cho producer. Đoạn runner chỉ gửi **một message mỗi lần khởi động**, không kiểm tra nhận/ACK của consumer.

### 6.8. Chạy thử ba profile, không chạy hai consumer cùng lúc

Mở broker ở môi trường thử nghiệm và đặt credentials qua biến môi trường. Để kiểm tra polling:

1. Gửi một message bằng profile `publish`.
2. Dừng process producer sau khi thao tác gửi hoàn tất.
3. Khởi động process với profile `poll` và quan sát log.

```bash
# Terminal 1: gửi event (có thể kết thúc process sau khi gửi)
./gradlew bootRun --args='--spring.profiles.active=publish'

# Terminal 2, sau khi chỉ còn broker và message đang chờ:
./gradlew bootRun --args='--spring.profiles.active=poll'
```

Với dữ liệu demo và broker nhận message đúng, poller có thể in:

```text
Xử lý sự kiện: OrderCreated:order-42
```

Để kiểm tra listener, hãy **không chạy profile poll đồng thời**. Khởi động app chỉ với profile `listener`, sau đó từ một process khác gửi message với profile `publish`:

```bash
# Terminal 1: chỉ listener
./gradlew bootRun --args='--spring.profiles.active=listener'

# Terminal 2: gửi một event vào cùng broker
./gradlew bootRun --args='--spring.profiles.active=publish'
```

Listener cũng có thể in:

```text
Xử lý sự kiện: OrderCreated:order-42
```

Đây chỉ là **dòng log do `OrderHandler` sinh ra**; stdout thật còn nhiều log Spring/Artemis và thứ tự giữa hai process không cố định. Nếu có hai bản message, có thể thấy hai dòng. Nếu broker không có queue/quyền hoặc không kết nối được, ví dụ sẽ thất bại thay vì in kết quả.

**Không suy ra chính sách redelivery từ demo `OrderPoller`.** Với lần nhận đồng bộ ngoài transaction, message có thể đã được nhận/ack trước khi handler ném lỗi, nên phải thiết kế transaction trước khi dùng cho xử lý quan trọng.

## 7. Transaction và ACK: yếu tố quyết định độ tin cậy hơn “poll hay listener”

Đây là điểm quan trọng nhất khi biến một prototype thành ứng dụng thực.

### 7.1. Polling nhận rồi xử lý sau: khoảng hở dễ bị bỏ qua

Mã này trông rất tự nhiên:

```java
Object payload = jmsTemplate.receiveAndConvert("orders.in");
if (payload != null) {
    businessService.updateDatabase(payload);
}
```

Nhưng nếu `receiveAndConvert` dùng một JMS session không được bao bởi transaction chung với xử lý, **điểm xác nhận message có thể xảy ra ngay trong thao tác receive**. Khi `updateDatabase` thất bại sau đó, broker có thể coi message đã được tiêu thụ và không redeliver như kỳ vọng.

Thay `receiveAndConvert` bằng `receive` **không tự giải quyết** khoảng hở này. Tách việc nhận và xử lý khỏi transaction boundary là nguyên nhân, không phải tên method.

### 7.2. Polling đáng tin hơn khi cùng JMS transaction

Muốn rollback message khi handler thất bại, có thể dùng `JmsTransactionManager` cùng `ConnectionFactory` với `JmsTemplate`; một Spring-managed transaction phải bao quanh **cả receive và xử lý**.

Ví dụ **minh họa bổ sung** cho một ứng dụng có bean transaction manager JMS tên `jmsTransactionManager`:

```java
@Transactional("jmsTransactionManager")
public void pollAndHandle() {
    Object body = pollingJmsTemplate.receiveAndConvert("orders.in");
    if (body instanceof String text) {
        businessHandler.handle(text);
    }
}
```

Đây là **method minh họa**, không phải một file Java độc lập. Annotation cần import `org.springframework.transaction.annotation.Transactional`. Bean transaction manager có thể tạo bằng:

```java
@Bean("jmsTransactionManager")
JmsTransactionManager jmsTransactionManager(
        ConnectionFactory connectionFactory) {
    return new JmsTransactionManager(connectionFactory);
}
```

Cần import `jakarta.jms.ConnectionFactory`, `org.springframework.jms.connection.JmsTransactionManager` và `org.springframework.context.annotation.Bean`, đặt method trong một `@Configuration` class. Method `pollAndHandle` phải được gọi **qua Spring transaction proxy** chứ không phải self-invocation `this.pollAndHandle()`. Nếu muốn giữ lịch `@Scheduled`, hãy đảm bảo scheduler gọi đúng method/proxy được quản lý.

`JmsTransactionManager` chỉ quản lý transaction **của JMS**; nó không làm database transaction cùng broker atomic. Nếu DB đã commit nhưng JMS commit thất bại, message có thể được gửi lại. Consumer vẫn cần idempotency, hoặc mô hình outbox/inbox/XA theo nhu cầu.

### 7.3. Listener: transaction nằm trong listener container

Spring `DefaultMessageListenerContainer` được thiết kế để chạy listener trong JMS transaction khi cấu hình `sessionTransacted = true` hoặc transaction manager phù hợp. Khi handler ném exception **để lỗi đi ra container**, JMS transaction có thể rollback và provider redeliver message.

Ngược lại, theo Javadoc Spring, `DefaultMessageListenerContainer` với `AUTO_ACKNOWLEDGE` có thể ACK **trước** khi handler chạy; khi handler lỗi, không thể mặc định mong message được redeliver. Vì vậy không được viết:

```java
@JmsListener(destination = "orders.in")
public void onMessage(String body) {
    try {
        businessHandler.handle(body);
    } catch (Exception ex) {
        // PHẢN VÍ DỤ: nuốt lỗi, container có thể coi là thành công.
    }
}
```

Đây là **phản ví dụ**. Hãy quyết định rõ trường hợp nào retry, trường hợp nào chuyển DLQ, và để exception/transaction policy biểu đạt đúng kết quả. Các mode `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` và local transaction không tương đương nhau, cũng không có một behavior giống hệt trên mọi listener container.

### 7.4. Không gộp ACK của JMS với business commit

Dù là polling hay listener, nếu phần business xử lý trên database riêng, **JMS transaction không tự bao trùm database transaction**. Có thể xảy ra DB đã commit nhưng JMS chưa ACK/commit và event được giao lại. Thiết kế consumer idempotent dựa vào `eventId`/khóa nghiệp vụ là nền tảng.

Với những yêu cầu mạnh hơn, cân nhắc inbox/deduplication, transactional outbox, hoặc transaction coordinator hỗ trợ XA (đổi lại có chi phí và phức tạp vận hành). Không chọn listener chỉ vì nghe có vẻ “reliable hơn”; hãy kiểm tra cấu hình và failure modes thực tế.

## 8. Thứ tự, scaling và việc hai consumer cạnh tranh cùng queue

Trong ví dụ, poller và listener cùng nhắm queue `orders.in`. Nếu chạy **cả hai profile hoặc hai dịch vụ** cùng nhận:

```text
                         queue "orders.in"
                                |
                    +-----------+-----------+
                    |                       |
             Poller consumer           Listener consumer
               nhận M1?                  nhận M2?
```

Đối với **queue**, một message thường được giao tới **một consumer phù hợp**, không tự động copy cho mỗi consumer. Hai cách nhận cùng queue có thể **cạnh tranh tiêu thụ** khiến kết quả demo không ổn định. Với **topic**, semantics của subscription khác, nên phải xét `pubSubDomain`, durable/shared subscription, selector và connection/client ID.

Các yếu tố cần xem khi tăng concurrency:

- `@JmsListener(concurrency = "1")` giới hạn concurrent consumer của endpoint, không giới hạn tổng replica ở các máy.
- Nhiều consumer có thể hoàn tất xử lý theo thứ tự khác nhau; ngay cả một consumer cũng có thể gặp redelivery, delayed delivery và producer đa session.
- JMS priority, selector và transaction cũng ảnh hưởng trật tự quan sát.
- Nếu nghiệp vụ cần thứ tự theo đơn hàng, hãy dùng `aggregateId`, `sequence/version`, message group khi broker hỗ trợ, và kiểm tra cập nhật trạng thái theo phiên bản.
- Không dùng nhiều poller trên cùng queue với giả định mỗi poller đọc một “partition riêng” nếu broker không có cơ chế phân phối/partition được cấu hình.

**Đổi từ polling sang listener không tự tạo exactly-once, strict FIFO, hay fan-out.** Những bảo đảm này yêu cầu hợp đồng và cấu hình riêng.

## 9. Performance và backpressure

### 9.1. Khi polling có lợi

- Message đến thưa, chỉ cần xử lý vào các thời điểm nhất định.
- Hệ thống phụ thuộc giới hạn số request, nên muốn xử lý tối đa một lượng nhỏ trong mỗi lượt.
- Workflow batch cần biết mốc bắt đầu/kết thúc để báo cáo tổng hợp.
- Job cần được bật/tắt rõ ràng theo lịch và các resource phụ thuộc.
- Nhận message là một bước trong chuỗi điều phối đồng bộ **đã có timeout hữu hạn**.

Polling không có nghĩa tiết kiệm tài nguyên trong mọi trường hợp: một job nhận no-wait rất thường xuyên có thể tốn công hơn listener container đã tối ưu pooling/consumer.

### 9.2. Khi listener có lợi

- Cần xử lý gần như ngay khi message đến.
- Dòng message liên tục, backlog có thể tăng đột biến.
- Muốn framework quản lý container lifecycle/recovery/throttling cơ bản.
- Cần scaling bằng số consumer, có quan sát lag và lỗi phù hợp.
- Xử lý theo sự kiện là trách nhiệm nền lâu dài của service.

Tuy nhiên listener không tự giải quyết overload. Ví dụ tăng `concurrency` từ 1 lên 20 trong khi database chỉ chịu được vài transaction đồng thời có thể giảm độ ổn định toàn hệ thống.

### 9.3. Các núm điều chỉnh khác nhau

| Poller | Listener |
| --- | --- |
| `fixedDelay` hoặc lịch cron | Số concurrent consumers |
| `receiveTimeout` | Container `receiveTimeout` và recovery/backoff |
| Số message tối đa mỗi lượt | Max concurrency, pool/executor limits |
| Batch duration, next-run backoff | Stop/start endpoint, điều tiết consumer |
| Job deadline và shutdown | Container graceful shutdown/drain |
| Số job/replica | Số listener instances/replica |

Đừng lấy `receiveTimeout` của listener container làm “chu kỳ ứng dụng” giống `@Scheduled`: container có chiến lược nhận lặp, thread lifecycle và scaling riêng.

Một ví dụ cảnh báo: với `@Scheduled(fixedDelayString="5000")` và poller chỉ nhận tối đa một message, mỗi lần phải xử lý xong rồi đợi thêm 5 giây. Nếu backlog tăng, đây thường là nút thắt có chủ đích; nếu không chủ đích, có thể cần tăng batch size, dùng worker pool theo policy hoặc chuyển sang listener.

## 10. Quan sát, kiểm thử và quy trình đổi kiến trúc

### 10.1. Metrics cần quan tâm

| Metric đề xuất | Polling | Listener |
| --- | --- | --- |
| `queue_depth` / `oldest_message_age` | Có | Có |
| `poll_attempt_total` | Chính | Không cần theo nghĩa ứng dụng |
| `poll_empty_total` | Quan trọng khi đánh giá chi phí gọi rỗng | Không cần cùng định nghĩa |
| `poll_duration` | Chờ receive + xử lý | Không |
| `listener_active_consumers` | Không | Quan trọng |
| `message_process_success_total` | Có | Có |
| `message_process_failure_total` | Có | Có |
| `redelivery_total` / DLQ depth | Có | Có |
| `processing_latency` (arrival → business commit) | Có | Có |

Đây là **tên metrics gợi ý**, không phải thuộc tính có sẵn của Spring. Dùng Micrometer/Actuator và broker metrics tương ứng, gắn `destination`, `consumerType`, `eventId`/correlation khi cần truy vết; hạn chế ghi dữ liệu nhạy cảm vào log.

### 10.2. Test polling

Với `OrderPoller`, unit test có thể mock `JmsTemplate`:

```java
package demo.receive;

import org.junit.jupiter.api.Test;
import org.springframework.jms.core.JmsTemplate;

import static org.mockito.Mockito.*;

class OrderPollerTest {
    @Test
    void noMessageMeansNoBusinessCall() {
        JmsTemplate template = mock(JmsTemplate.class);
        OrderHandler handler = mock(OrderHandler.class);
        when(template.receiveAndConvert("orders.in")).thenReturn(null);

        OrderPoller poller =
                new OrderPoller(template, handler, "orders.in");
        poller.pollOnce();

        verify(template).receiveAndConvert("orders.in");
        verifyNoInteractions(handler);
    }

    @Test
    void receivedTextGoesToHandler() {
        JmsTemplate template = mock(JmsTemplate.class);
        OrderHandler handler = mock(OrderHandler.class);
        when(template.receiveAndConvert("orders.in"))
                .thenReturn("OrderCreated:order-42");

        new OrderPoller(template, handler, "orders.in").pollOnce();

        verify(handler).handle("OrderCreated:order-42");
    }
}
```

Lưu ở `src/test/java/demo/receive/OrderPollerTest.java`, chạy:

```bash
./gradlew test --tests demo.receive.OrderPollerTest
```

Nếu test passes thì Gradle báo thành công (log tùy phiên bản). Test mock **không chứng minh** broker đã ACK, redeliver hay xử lý transaction; nó chỉ kiểm tra control flow và cách xử lý `null`.

### 10.3. Test listener

Với listener, unit test có thể gọi `new OrderListener(mockHandler).onMessage("OrderCreated:order-42")` và verify handler. Còn integration test mới kiểm tra container thực, broker/destination, việc nhận, ack/rollback, concurrency, recovery và cấu hình transaction.

Các kịch bản tối thiểu cần chạy với **cả hai cách**:

1. Queue trống: polling phải timeout/trả null; listener không được tự gọi business handler.
2. Một message hợp lệ: xử lý đúng và ghi nhận chính xác một **ý định nghiệp vụ** (có idempotency).
3. Business handler ném exception: xem message có rollback/redeliver như **policy đã thiết kế** không.
4. Broker gián đoạn rồi hoạt động lại: lịch poll/container phục hồi thế nào, có trùng lặp không.
5. Backlog lớn và dependency chậm: tốc độ xử lý, queue age, concurrency và pressure.
6. Hai application instance: cạnh tranh tiêu thụ, business order, graceful shutdown.

### 10.4. Đổi từ poller sang listener mà không mất message

Một quy trình chuyển đổi an toàn:

1. Xác định **cùng destination**, selector, queue/topic semantics, converter, schema và permissions.
2. Ghi nhận chính sách ack/transaction hiện tại của polling; thiết kế listener mới có failure/retry/DLQ tương đương hoặc tốt hơn.
3. Dùng một business handler chung, có idempotency, để tránh khác biệt hành vi.
4. Triển khai listener nhưng **chưa cho đồng thời nhận production**; chạy trên queue thử nghiệm hoặc consumer được tách biệt hợp lệ.
5. Dừng poller có kiểm soát, chờ job đang xử lý/transaction kết thúc, rồi bật listener. Đừng cho hai loại consumer chạy song song nếu bạn cần cutover rõ ràng.
6. Quan sát backlog, queue age, redelivery, DLQ và tốc độ xử lý; có rollback plan và tiêu chí tránh duplicate/mất sự kiện.

Rollback kiến trúc cũng tương tự: tắt listener có kiểm soát và xác minh in-flight, rồi mới cho scheduler polling hoạt động. Dừng listener không có nghĩa mọi message đang xử lý đã commit; phải kiểm tra thời gian drain và transaction.

## 11. Các lỗi hiểu nhầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Hướng xử lý |
| --- | --- | --- |
| Dùng `JmsTemplate.receive` mặc định trong HTTP handler | Có thể chặn thread vô hạn | Timeout hữu hạn hoặc tách xử lý nhận khỏi request thread |
| Nhầm `receiveTimeout=0` của Spring với `MessageConsumer.receive(0)` | Hai quy ước khác nhau | Với `JmsTemplate`, 0 là no-wait; -1 là indefinite |
| Poll no-wait trong `while(true)` không backoff | Busy polling làm tăng tải vô ích | Scheduler, backoff, batch limits |
| Nghĩ `@Scheduled` khiến `receive` không còn đồng bộ | Scheduler chỉ gọi method trên thread khác | Thread scheduler vẫn block trong `receive` |
| Nghĩ `@JmsListener` không dùng thread hoặc luôn push | Container có thread, có thể receive loop | Tính cả thread/connection và container lifecycle |
| Polling nhận rồi xử lý DB ngoài transaction | Message có thể ACK trước lỗi nghiệp vụ | Transaction bao quanh receive + handling hoặc idempotency/inbox |
| Listener nuốt exception | Container có thể coi xử lý đã thành công | Cho exception đi ra theo retry/DLQ policy |
| Chọn listener vì “exactly once” | Không có exactly-once business mặc định | Chốt transaction, idempotency và dedup |
| Chạy poller và listener cùng queue để “so sánh” | Cạnh tranh lấy message và làm log khó hiểu | Chạy profiles riêng, queue thử nghiệm riêng |
| Tăng listener concurrency và mong thứ tự được giữ | Xử lý song song có thể đảo thứ tự commit | Version/sequence, grouping, partition theo aggregate |
| Dùng một polling job cho backlog rất lớn nhưng mỗi lần lấy một message | Throughput quá thấp | Tăng capacity trong ngưỡng hoặc chuyển listener |
| Tăng listener concurrency vô hạn | Quá tải DB/API, tạo redelivery storm | Giới hạn concurrency/backpressure, DLQ |
| Cho rằng queue trống là lỗi `receiveAndConvert` | Hết timeout trả `null` | Xử lý null bình thường, metrics poll rỗng |
| Xem queue nhận message là business đã hoàn tất | JMS ACK và DB commit khác nhau | Có business status/confirmation riêng |

## 12. Checklist quyết định

Hãy đi theo chuỗi câu hỏi:

1. **Chỉ được tiêu thụ theo lịch / batch / cửa sổ bảo trì?** Nếu có, chọn polling theo lịch hoặc một listener có lifecycle được điều phối rõ ràng; polling thường đơn giản hơn.
2. **Cần xử lý gần như liên tục khi message đến?** Nếu có, ưu tiên `@JmsListener`.
3. **Có SLA và backlog đáng kể?** Đo throughput, handler latency, resource budgets; listener có concurrency thường thuận tiện hơn, nhưng phải giới hạn tải.
4. **Handler thất bại có cần redelivery?** Thiết kế transaction/ack trước khi chọn; đừng dùng poller demo ngoài transaction cho nghiệp vụ quan trọng.
5. **Cần thứ tự theo aggregate?** Cố định hợp đồng `aggregateId`/`sequence` và idempotency; đánh giá concurrency, số replica, message groups/provider.
6. **Cần tạm dừng/quản lý shutdown?** Định nghĩa drain, retry, metrics và trách nhiệm vận hành cụ thể.

**Ghi nhớ:** `JmsTemplate.receive` là **nhận đồng bộ có block thread gọi** và phù hợp cho các tác vụ nhận có lịch/giới hạn rõ ràng. `@JmsListener` là **mô hình xử lý bất đồng bộ ở cấp ứng dụng**, do Spring listener container quản lý, phù hợp cho tiêu thụ sự kiện liên tục. Chất lượng và độ tin cậy của cả hai phụ thuộc vào transaction, acknowledgment, idempotency, backpressure và vận hành — **không phải chỉ tên API**.

### Tài liệu tham khảo

- Spring Framework 6.2 — Receiving a Message (synchronous receive và message-driven POJOs): https://docs.spring.io/spring-framework/reference/6.2/integration/jms/receiving.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Framework 6.2 — JmsTemplate Javadoc (receive, receiveAndConvert, receiveTimeout): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — DefaultMessageListenerContainer và acknowledge/transaction: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html
- Spring Boot 3.4 — JMS với Artemis, JmsTemplate và listener auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
