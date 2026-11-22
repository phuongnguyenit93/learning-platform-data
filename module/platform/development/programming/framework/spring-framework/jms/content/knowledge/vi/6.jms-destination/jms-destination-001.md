# Destination có sẵn và tên destination trong mã ứng dụng (Spring JMS)

## 1. Bài toán: ứng dụng kết nối vào một destination đã tồn tại

Trong hệ thống JMS, broker nhận, lưu trữ và phân phối message qua các **destination**. Một destination có thể là **queue** (mô hình point-to-point) hoặc **topic** (mô hình publish/subscribe). Tình huống thường gặp trong hệ thống doanh nghiệp là hạ tầng đã tạo sẵn queue/topic; ứng dụng Spring chỉ cần biết đúng **tên** và cách truy cập để gửi hoặc nhận message.

Ví dụ: đội vận hành đã cấu hình queue `orders.in` trên broker. Dịch vụ đặt hàng phải gửi vào chính queue này, còn dịch vụ xử lý đơn hàng lắng nghe cùng queue. Hai phía cần thống nhất tên, loại destination, broker/namespace và quyền truy cập. Khai báo chuỗi `"orders.in"` trong Java không tự chứng minh queue đã tồn tại.

**Sau bài này, bạn có thể:** phân biệt destination vật lý với đối tượng JMS và tên logic trong code; cấu hình Spring JMS trỏ tới queue có sẵn; hiểu cách Spring phân giải tên; chọn giữa cấu hình chuỗi, đối tượng `Destination` và JNDI; kiểm tra các lỗi sai tên hoặc sai loại destination.

## 2. Ba lớp cần phân biệt

| Lớp | Ví dụ | Vai trò |
| --- | --- | --- |
| Tài nguyên vật lý do broker quản lý | Queue `orders.in`, được provision trước | Nơi broker định tuyến/lưu trữ message theo cấu hình của chính broker |
| Đối tượng JMS trong ứng dụng | `jakarta.jms.Queue` / `jakarta.jms.Topic`, đều là `Destination` | Handle để API JMS gửi/nhận; có thể chỉ đóng gói tên do provider hiểu |
| Tên mà Spring nhận từ mã/cấu hình | `"orders.in"`, `${app.jms.orders.input}` hoặc `"jms/OrdersQueue"` | Đầu vào cho `DestinationResolver`; cách ánh xạ sang đối tượng JMS phụ thuộc resolver |

`ConnectionFactory` xác định cách kết nối tới provider/broker; **nó không thay thế tên destination**. Cùng chuỗi `orders.in` trên hai broker khác nhau không có nghĩa là cùng một hàng đợi.

- **Queue:** mỗi message được chuyển tới một consumer đủ điều kiện trong các consumer cạnh tranh trên cùng queue; không phải mọi consumer đều nhận một bản sao.
- **Topic:** thông điệp được phát tới các subscription phù hợp; hành vi nhận lại khi offline phụ thuộc loại subscription, tính bền vững và cấu hình provider.
- **Tên logic/JNDI:** `jms/OrdersQueue` có thể là khóa tra cứu một đối tượng `Queue` được quản trị sẵn, còn tên vật lý trong broker có thể khác. Không mặc định xem hai chuỗi này là một.

## 3. Trách nhiệm khi dùng destination có sẵn

**Phía hạ tầng/broker** tạo hoặc provision queue/topic theo cách provider hỗ trợ, đặt routing type, địa chỉ/tên, quyền gửi/nhận, chính sách lưu trữ, redelivery và dead-letter khi cần. Với ActiveMQ Artemis, ví dụ queue point-to-point thường gắn với một address có routing type `ANYCAST`; chi tiết phụ thuộc cấu hình broker.

**Phía ứng dụng Spring** sử dụng `ConnectionFactory` đã cấu hình, chọn đúng tên và loại destination, rồi gửi bằng `JmsTemplate` hoặc nhận qua `@JmsListener`. Ứng dụng không nên dựa vào tính năng tự tạo destination của broker nếu hợp đồng triển khai quy định queue phải được provision sẵn.

Một hợp đồng cấu hình tối thiểu cần ghi rõ:

| Thuộc tính | Ví dụ |
| --- | --- |
| Broker hoặc cluster | `tcp://localhost:61616` trong môi trường thực hành |
| Destination type | `queue` |
| Tên destination tại broker | `orders.in` |
| Hướng sử dụng | Producer gửi, consumer nhận |
| Quyền | Tài khoản được send/consume đúng destination |
| Quy tắc tạo | Provision trước; xác định rõ broker có cho phép auto-create không |

Tên nên được coi là **hợp đồng tích hợp giữa các hệ thống**. Tránh đổi tên tùy tiện hoặc suy ra tên từ tên class/method. Nếu mỗi môi trường đặt namespace khác nhau, đặt giá trị tại cấu hình triển khai thay vì ghép tiền tố rải rác trong mã.

## 4. Ví dụ Spring JMS: gửi và nhận bằng tên queue đã có

Giả định queue `orders.in` **đã được tạo trên broker** và tài khoản ứng dụng được phép gửi/nhận. Ví dụ dùng Java 17+, Spring Boot 3.x (Spring Framework 6+, namespace `jakarta.jms`) và ActiveMQ Artemis ở chế độ kết nối tới broker ngoài. Các class dưới đây thuộc một dự án Spring Boot có hỗ trợ JMS; chúng **không phải chương trình Java SE độc lập**.

Với Gradle Groovy, thêm starter (phiên bản do Spring Boot dependency management quản lý):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

Tạo `src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: "${JMS_BROKER_URL:tcp://localhost:61616}"
    user: "${JMS_USER}"
    password: "${JMS_PASSWORD}"

app:
  jms:
    orders:
      input: "orders.in"
```

Ở đây `spring.artemis.*` cấu hình kết nối, còn `app.jms.orders.input` là tên queue mà chương trình sử dụng. Cần cấp biến môi trường `JMS_USER` và `JMS_PASSWORD` phù hợp broker; giá trị mặc định cho URL chỉ để tiện thực hành. Trong triển khai thực tế, cấu hình đích và thông tin kết nối nên đến từ hệ thống quản lý cấu hình/secrets.

Tạo `src/main/java/demo/jms/DemoApplication.java`:

```java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tạo `src/main/java/demo/jms/OrderPublisher.java`:

```java
package demo.jms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderPublisher {
    private final JmsTemplate jmsTemplate;
    private final String queueName;

    public OrderPublisher(
            JmsTemplate jmsTemplate,
            @Value("${app.jms.orders.input}") String queueName) {
        this.jmsTemplate = jmsTemplate;
        this.queueName = queueName;
    }

    public void publish(String orderId) {
        jmsTemplate.convertAndSend(queueName, orderId);
    }
}
```

Ở lệnh `convertAndSend(queueName, orderId)`, tham số thứ nhất là **tên đích**, tham số thứ hai là payload. Với bộ chuyển đổi mặc định của Spring JMS, `String` được gửi dưới dạng JMS `TextMessage`. Đừng đảo thứ tự hai tham số hoặc nhầm tên queue với nội dung message.

Tạo `src/main/java/demo/jms/OrderConsumer.java`:

```java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class OrderConsumer {
    @JmsListener(destination = "${app.jms.orders.input}")
    public void receive(String orderId) {
        System.out.println("Đã nhận đơn: " + orderId);
    }
}
```

`@JmsListener` đọc tên destination từ cùng property với producer. `@EnableJms` bật hạ tầng annotation listener trong Spring; Spring Boot có thể tự cấu hình `JmsTemplate`, `ConnectionFactory` và listener factory khi có starter/provider tương ứng.

Để phát thử một message khi chạy profile `demo`, thêm `src/main/java/demo/jms/DemoSendRunner.java`:

```java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("demo")
public class DemoSendRunner implements ApplicationRunner {
    private final OrderPublisher publisher;

    public DemoSendRunner(OrderPublisher publisher) {
        this.publisher = publisher;
    }

    @Override
    public void run(ApplicationArguments args) {
        publisher.publish("ORDER-1001");
    }
}
```

Khởi động broker có queue `orders.in` trước, cung cấp credentials, rồi chạy ứng dụng với profile `demo` (ví dụ `./gradlew bootRun --args='--spring.profiles.active=demo'` trong dự án Gradle Boot đã cấu hình task `bootRun`). Khi kết nối và quyền truy cập đúng, runner gửi một message và listener có thể in:

```text
Đã nhận đơn: ORDER-1001
```

Đây là **dòng output kỳ vọng từ listener**, không phải toàn bộ stdout của Spring Boot. Việc nhận diễn ra bất đồng bộ; thời điểm dòng log xuất hiện phụ thuộc broker, listener và môi trường. Không bật profile `demo` trong production vì nó cố ý gửi một đơn mẫu mỗi lần khởi động.

Luồng xử lý:

```text
application.yml
  app.jms.orders.input = orders.in
        |
        +--> OrderPublisher --> JmsTemplate --> DestinationResolver
        |                                    --> broker queue orders.in
        |
        +--> @JmsListener --> listener container --> consumer của orders.in
```

Cấu hình tên ở một chỗ giúp producer và consumer dùng cùng hợp đồng; chúng vẫn có thể nằm ở **hai ứng dụng khác nhau** nếu hai ứng dụng cùng kết nối đúng broker/đích.

## 5. Tên destination có thể xuất hiện ở đâu trong mã?

| Cách dùng | Ví dụ | Khi nào phù hợp / lưu ý |
| --- | --- | --- |
| Chuỗi trực tiếp | `jmsTemplate.convertAndSend("orders.in", body)` | Demo nhỏ; dễ sai tên nếu nhiều nơi cùng gõ |
| Constant Java | `static final String ORDERS_IN = "orders.in";` | Giảm lỗi gõ trong một bản triển khai; thay tên theo môi trường vẫn phải build lại |
| Externalized configuration | `@Value("${app.jms.orders.input}")` | Thường phù hợp nhất khi destination do hạ tầng cung cấp; giá trị có thể khác theo môi trường |
| Default destination của template | `setDefaultDestinationName("orders.in")` rồi `convertAndSend(body)` | Producer chủ yếu gửi một đích; phải phân biệt overload có/không có tham số tên |
| Đối tượng `Destination` | `convertAndSend(destination, body)` | Khi đã có một `Queue`/`Topic` object hoặc được DI từ cấu hình/JNDI |
| Tên lookup JNDI | `jms/OrdersQueue` | Môi trường quản trị destination dưới JNDI; cần resolver/lookup phù hợp |

Nếu dùng constant, nên tập trung trong một lớp định nghĩa hợp đồng thay vì nhân bản literal. Nếu dùng property, đảm bảo giá trị không trống và kiểm tra khi khởi động; ghi nhận tên đích hiệu lực trong log cấu hình (không ghi credentials). Không tạo các tên khác nhau bằng cách nối chuỗi ngẫu nhiên từ user input, vì có thể phát sinh destination ngoài dự kiến trên broker cho phép auto-create.

## 6. Spring phân giải chuỗi thành đối tượng Destination như thế nào?

`JmsTemplate` không gửi trực tiếp vào một chuỗi: nó nhờ `DestinationResolver` chuyển tên thành đối tượng JMS `Destination`. Mặc định `JmsTemplate` dùng `DynamicDestinationResolver`:

1. Spring nhận `destinationName`, ví dụ `orders.in`.
2. Resolver dựa trên cờ `pubSubDomain` để chọn `Session.createQueue("orders.in")` (queue) hoặc `Session.createTopic("...")` (topic).
3. JMS provider trả về đối tượng `Queue`/`Topic`, rồi Spring gửi/nhận thông qua provider.

**Điểm dễ nhầm:** theo Jakarta Messaging, `Session.createQueue(name)` tạo **đối tượng Java mô tả queue**, *không phải lệnh tiêu chuẩn tạo queue vật lý trên broker*. Một số provider có tính năng tự tạo queue khi truy cập tên chưa có; có provider yêu cầu admin tạo trước hoặc từ chối. Vì vậy, “code biên dịch được”, “đã gọi `createQueue`” và “queue tồn tại trên broker” là ba điều khác nhau. Muốn bảo đảm dùng destination có sẵn, hãy kiểm tra cấu hình/quyền của broker và không dựa vào auto-create.

Mặc định `JmsTemplate` có `pubSubDomain=false`, tức cách phân giải động theo queue. Nếu đích thực tế là **topic**, phải cấu hình producer và listener factory đúng miền pub/sub; đổi tên chuỗi từ `queue.foo` sang `topic.foo` không tự chuyển chế độ xử lý sang topic. Với topic cần cân nhắc subscription bền vững/chia sẻ tùy yêu cầu nhận message.

Hai overload cần phân biệt:

```java
// Có tên đích cụ thể: gửi tới destination được phân giải từ "orders.in".
jmsTemplate.convertAndSend("orders.in", "ORDER-1001");

// Không có tên đích: chỉ đúng khi đã cấu hình default destination.
jmsTemplate.convertAndSend("ORDER-1001");
```

Đoạn trên minh họa cách gọi bên trong một method đã được inject `JmsTemplate`; đây không phải class Java chạy độc lập. Lệnh thứ hai sẽ cần `defaultDestination` hoặc `defaultDestinationName` đã được thiết lập phù hợp.

## 7. Khi broker cung cấp destination qua JNDI

Một số môi trường enterprise không muốn mã ứng dụng chứa tên vật lý. Hạ tầng xuất bản đối tượng JMS được quản trị sẵn qua JNDI, chẳng hạn `jms/OrdersQueue`, ánh xạ tới một queue thực tế. Khi đó có thể dùng `JndiDestinationResolver` để Spring phân giải **tên lookup** thành `Destination`.

Ví dụ cấu hình Java sau là một **đoạn trong class `@Configuration`**, giả định JNDI context đã được cấu hình và lookup hoạt động:

```java
@Bean
DestinationResolver destinationResolver() {
    JndiDestinationResolver resolver = new JndiDestinationResolver();
    resolver.setFallbackToDynamicDestination(false);
    return resolver;
}
```

Các import tương ứng là `org.springframework.context.annotation.Bean`, `org.springframework.jms.support.destination.DestinationResolver` và `org.springframework.jms.support.destination.JndiDestinationResolver`. Trong Spring Boot, khi dùng auto-configuration JMS, một bean `DestinationResolver` có thể được áp dụng cho `JmsTemplate` và default listener factory; nếu tự tạo các bean này, hãy gắn resolver nhất quán cho cả hai.

Với JNDI, `@JmsListener(destination = "jms/OrdersQueue")` và `JmsTemplate.convertAndSend("jms/OrdersQueue", payload)` nói tới **khóa lookup**, không nhất thiết là tên queue vật lý. Cần có provider/JNDI binding tương ứng. `JndiDestinationResolver` mặc định không fallback về dynamic destination; cấu hình `false` ở ví dụ làm rõ ý định phát hiện lỗi lookup thay vì chấp nhận một tên đích khác ngoài dự kiến.

**Chọn cách nào?** Nếu hệ thống chỉ cung cấp tên queue trên broker và không có JNDI, dùng externalized property với resolver động thường đơn giản. Nếu hạ tầng cấp phát đối tượng qua JNDI, dùng tên JNDI đúng hợp đồng và cấu hình lookup. Không tự biến tên JNDI thành tên broker.

## 8. Kiểm tra trước khi triển khai

1. **Xác nhận tồn tại:** tra broker console/CLI hoặc cấu hình IaC để biết queue/topic đã có, tên chính xác và routing type. Nếu broker có nhiều namespace/vhost/cluster, xác nhận đúng phạm vi.
2. **Xác nhận producer và consumer:** hai bên tham chiếu cùng destination thực tế; thống nhất queue/topic và cấu hình `pubSubDomain`/listener factory. Nếu dùng JNDI, xác nhận ánh xạ cả hai phía.
3. **Xác nhận phân quyền:** user ứng dụng có quyền connect, send và consume tương ứng; không suy từ việc kết nối thành công rằng đủ quyền trên destination.
4. **Gửi một thông điệp thử có mã định danh:** quan sát producer gửi thành công, broker nhận message và consumer xử lý một lần như kỳ vọng trong môi trường thử nghiệm; kiểm tra queue depth, consumer count và log listener.
5. **Kiểm soát tự tạo:** biết chính xác broker có bật auto-create không. Khi kiểm thử sai tên trên broker có auto-create, một queue “ma” có thể xuất hiện khiến producer tưởng đã gửi đúng.
6. **Kiểm tra độ ổn định của hợp đồng:** tài liệu hóa tên, loại, chủ sở hữu, nơi cấu hình, quy tắc đổi tên, schema payload và chính sách xử lý lỗi.

Nếu message được consume nhanh, queue depth trở về 0 không có nghĩa là chưa từng có message; hãy kết hợp thống kê enqueue/dequeue, trace hoặc log có correlation ID.

## 9. Lỗi phổ biến và cách nhận diện

| Triệu chứng | Nguyên nhân nên kiểm tra | Hướng xử lý |
| --- | --- | --- |
| `InvalidDestinationException` hoặc lỗi destination không tồn tại | Sai tên; queue/topic chưa provision; broker không cho auto-create; JNDI lookup sai | Đối chiếu tên/routing trên broker; sửa cấu hình hoặc provision qua quy trình vận hành |
| Producer báo gửi thành công nhưng consumer không nhận | Hai phía trỏ khác broker/namespace hoặc khác tên; tự tạo nhầm queue; consumer chưa chạy | So sánh giá trị cấu hình hiệu lực, broker URL, consumer count và metrics của đích thực |
| Listener chạy nhưng không nhận theo cách mong đợi | Lẫn queue/topic; topic subscription chưa đúng; message selector lọc bỏ; consumer khác đang tranh message trên queue | Kiểm tra `pubSubDomain`, listener container, selector và mô hình queue/topic |
| Lỗi quyền truy cập | User kết nối được nhưng thiếu send/consume hoặc quyền tạo/đọc destination | Cấp quyền tối thiểu cần thiết trên đúng queue/topic |
| Có các queue tên gần giống nhau | Gõ sai literal, khác chữ hoa/thường, tiền tố môi trường, hoặc tự ghép tên | Chuẩn hóa hợp đồng và property; kiểm tra danh sách đích phát sinh |
| `convertAndSend(payload)` không có destination | Gọi overload không nêu tên nhưng chưa cấu hình default destination | Dùng `convertAndSend(destinationName, payload)` hoặc cấu hình default rõ ràng |
| JNDI không tìm thấy `jms/OrdersQueue` | Không có binding/Context hoặc cấu hình lookup sai | Xác minh JNDI context/binding; phân biệt lookup name với physical name |

Không khắc phục lỗi tên đích bằng cách cho ứng dụng tự tạo mọi queue trên production: điều đó che lỗi hợp đồng và có thể bỏ qua chính sách vận hành của broker.

## 10. Ghi nhớ và câu hỏi tự kiểm tra

- **Tên trong mã** là đầu vào để Spring phân giải destination; **tài nguyên vật lý** thuộc broker và có vòng đời/quyền riêng.
- Cả `JmsTemplate` và `@JmsListener` có thể sử dụng cùng property; chọn đúng queue/topic và đúng môi trường quan trọng hơn việc đặt tên class.
- `Session.createQueue` / `createTopic` theo chuẩn chỉ tạo đối tượng tham chiếu; auto-create tài nguyên vật lý phụ thuộc JMS provider/broker.
- Dùng property cho tên triển khai, dùng JNDI khi hạ tầng đã cung cấp binding, và xác minh readback/metrics trên broker khi thử kết nối.

Tự kiểm tra: (1) Nếu gọi `convertAndSend("orders.in", body)` thành công nhưng listener không nhận, bạn sẽ đối chiếu những giá trị nào? (2) `Session.createQueue("orders.in")` có đảm bảo queue vật lý đã được tạo không? (3) Tại sao `@JmsListener(destination = "jms/OrdersQueue")` không nhất thiết dùng tên queue vật lý `jms/OrdersQueue`?

### Tài liệu tham khảo

- Spring Framework 6.2 — Using Spring JMS, phần Destination Management: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/using.html
- Spring Framework 6.2 — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/annotated.html
- Spring Boot — JMS và cấu hình ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Jakarta Messaging — `Session.createQueue(String)` và ý nghĩa của destination object: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/session
