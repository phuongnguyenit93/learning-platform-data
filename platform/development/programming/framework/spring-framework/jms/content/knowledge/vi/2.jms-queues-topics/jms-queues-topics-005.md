# Consumer, subscription và bản sao message trong JMS (Queue và Topic)

## 1. Ba khái niệm khác nhau ở ba tầng

Trong Jakarta Messaging (JMS), **producer gửi message tới destination**, còn broker quyết định đưa message tới những nơi nhận nào. Khi đọc sơ đồ Queue/Topic, phải tách bạch:

| Khái niệm | Bản chất | Câu hỏi nó trả lời |
| --- | --- | --- |
| **Consumer** | Đối tượng JMS nhận message (ví dụ `MessageConsumer`/`JMSConsumer`); trong Spring, một listener container quản lý một hoặc nhiều consumer và gọi phương thức `@JmsListener`. | **Ai** đang thực sự nhận và xử lý message? |
| **Subscription** | Quan hệ đăng ký với một **Topic**, được broker quản lý; có thể tồn tại trong thời gian ngắn hoặc bền vững, và có thể có một hoặc nhiều consumer. | **Nhóm/luồng nhận nào** có quyền nhận message từ Topic? |
| **Bản sao message (delivery copy)** | Đơn vị giao nhận **logic độc lập** được tạo cho mỗi subscription đủ điều kiện khi publish lên Topic. | **Có bao nhiêu nhóm** cần nhận sự kiện này? |

**Mấu chốt:** số consumer **không tự quyết định** số bản sao message. Với Topic, số subscription phù hợp mới quyết định số bản giao logic; nhiều consumer **cùng một shared subscription** chia nhau xử lý **một** bản dành cho subscription đó. Với Queue, message được phân phối tới **một** consumer trong số các consumer cạnh tranh.

Từ “bản sao” mô tả **ngữ nghĩa độc lập của việc giao/acknowledge**, không cam kết broker đã sao chép payload thành nhiều vùng nhớ hay nhiều bản ghi vật lý. Broker có thể dùng reference, queue nội bộ hoặc cấu trúc tối ưu riêng. Các mô hình dưới đây giả định message không hết hạn, selector đều khớp và không xảy ra lỗi giao nhận.

## 2. Queue: nhiều consumer cạnh tranh cho một luồng công việc

```text
Producer --send(M1)--> Queue orders
                          |-- Consumer A
                          `-- Consumer B

M1 được giao cho A HOẶC B, không được nhân đôi cố ý cho cả hai.
```

- Queue có thể tồn tại và giữ message khi chưa có consumer, tùy cấu hình retention/expiry của broker. Queue không dùng “Topic subscription” để fan-out.
- Nếu A và B đều nghe cùng Queue, một lần gửi M1 chỉ có **một lượt xử lý thành công dự kiến** trong nhóm cạnh tranh. Broker chọn A hay B theo lịch điều phối riêng; JMS **không hứa round-robin, 50/50 hoặc thứ tự chia đều**.
- Thêm consumer thường để **tăng khả năng xử lý song song** và dự phòng. Không làm mỗi consumer nhận đủ toàn bộ message.
- Nếu consumer nhận rồi rollback, mất kết nối hoặc chưa acknowledge hợp lệ, message **có thể bị redelivery** tới A hoặc B. Đó là **gửi lại cùng công việc**, không phải fan-out tạo subscription mới.

**Ví dụ:** Queue nhận Q1, Q2, Q3; có consumer A, B. Một phân phối hợp lệ là A nhận Q1 và Q3, B nhận Q2; cũng có thể A nhận cả ba. Không thể suy luận consumer nào nhận message cụ thể chỉ từ số consumer.

## 3. Topic: publish tới các subscription, rồi mới phân phối cho consumer

```text
                      Topic orders.events
                       publish(E-101)
                             |
          +------------------+------------------+
          |                  |                  |
  Subscription audit   Subscription billing  Subscription search
      (1 consumer)       (shared: B1, B2)       (1 consumer)
          |                  |                  |
       Audit A          B1 HOẶC B2           Search S
      copy #1            copy #2              copy #3
```

Giả sử cả ba subscription đang có hiệu lực và selector đều khớp, **một** lần publish E-101 tạo **ba lượt giao logic độc lập**: audit, billing, search. Trong billing, B1 và B2 chia nhau **một** lượt của nhóm billing; không có hai lượt riêng chỉ vì có hai consumer.

Hệ quả quan trọng:

1. **Một subscription, nhiều consumer (shared):** một event được giao cho **một** consumer trong nhóm. Dùng để scale-out một nghiệp vụ.
2. **Nhiều subscription độc lập:** cùng một event được giao **một lần cho mỗi subscription**. Dùng khi các nghiệp vụ khác nhau đều cần event, chẳng hạn billing và audit.
3. **Hai consumer Topic không shared:** mỗi consumer tạo một **unshared non-durable subscription riêng**. Nếu cả hai đang hoạt động khi publish thì mỗi bên nhận một bản; chúng **không** tự trở thành “competing consumers” trên cùng subscription.
4. **Thêm một consumer vào shared subscription hiện có** không tăng số bản sao logic. **Thêm một subscription độc lập** thường làm tăng số bản cần giao cho mỗi event phù hợp.

Với mỗi bản ở các subscription khác nhau, việc acknowledge/rollback, độ trễ và backlog là **độc lập**. Audit đã xử lý xong E-101 không có nghĩa billing đã xử lý xong; lỗi ở billing không buộc audit nhận lại. Một subscription có selector không khớp sẽ không được cấp bản tương ứng.

### Bảng tình huống: một message gửi/publish, không lỗi

| Destination và cách đăng ký | Số consumer | Số subscription Topic | Số lượt giao logic dự kiến |
| --- | ---: | ---: | --- |
| Queue, A và B cùng tiêu thụ | 2 | Không áp dụng | **1 tổng cộng**, cho A hoặc B |
| Topic, A và B mỗi người có unshared subscription riêng, đều online | 2 | 2 | **2**, mỗi bên 1 |
| Topic, A và B cùng shared subscription `billing` | 2 | 1 | **1 tổng cộng**, cho A hoặc B |
| Topic, shared `billing` có B1+B2; `audit` có A1 | 3 | 2 | **2**, billing 1 và audit 1 |
| Topic, `audit` đang online; non-durable `email` offline hoàn toàn | 1 đang online | 1 còn tồn tại | **1** cho audit; email không có backlog |

“Số lượt giao” ở bảng là số bản **theo mô hình định tuyến**, **không** phải số lần callback thực tế khi có retry/redelivery. Chỉ tính những subscription thực sự tồn tại tại thời điểm publish và đáp ứng selector, chính sách TTL, v.v.

## 4. Subscription có hai chiều cấu hình độc lập

**Chiều 1 – shared hay unshared:** một subscription cho phép bao nhiêu consumer **đang cùng** tiêu thụ?

- **Unshared:** tối đa **một** consumer hoạt động trên subscription đó. Mở consumer thứ hai trên cùng một *unshared durable subscription* khi consumer thứ nhất chưa đóng sẽ gây lỗi.
- **Shared:** **nhiều** consumer có thể cùng gắn vào một subscription đã đặt tên; mỗi message của subscription đi tới **một** consumer trong nhóm. Đây là cạnh tranh **bên trong subscription**, không phải broadcast tới từng consumer.

**Chiều 2 – durable hay non-durable:** broker có giữ subscription/backlog khi không có consumer nào?

- **Non-durable:** chỉ tồn tại trong lúc consumer tương ứng hoạt động; khi đóng consumer cuối cùng, subscription biến mất. Event publish trong thời gian không có subscription đó **không được truy hồi sau này**.
- **Durable:** broker duy trì subscription sau khi consumer ngắt kết nối, giữ các message phù hợp chưa được xác nhận theo điều kiện tồn tại, expiry và chính sách broker. Consumer tái kết nối đúng danh tính có thể nhận phần tồn đọng. Durable **không có nghĩa** lưu lại mọi message kể từ trước khi subscription được tạo.

| Loại subscription Topic | Consumer đồng thời | Danh tính điển hình | Khi tất cả consumer offline |
| --- | --- | --- | --- |
| Unshared + non-durable | 1 | Được tạo ngầm, không có tên | Bị xóa; không tích lũy message mới |
| Shared + non-durable | Nhiều | `subscriptionName` và `clientId` nếu đã thiết lập | Bị xóa sau consumer cuối cùng; không tích lũy message mới |
| Unshared + durable | 1 | **Bắt buộc** `clientId + subscriptionName` | Vẫn tồn tại; có thể tích lũy message hợp lệ |
| Shared + durable | Nhiều | `subscriptionName` và `clientId` **tùy chọn** | Vẫn tồn tại; có thể tích lũy message hợp lệ |

Hai cấu hình có cùng tên hiển thị **chưa chắc** cùng một subscription: cần xét domain/topic, shared/durable và danh tính client mà provider dùng. Các consumer chia sẻ một subscription phải dùng cấu hình tương thích về topic và selector. Thay topic/selector của durable subscription khi offline có thể có ngữ nghĩa xóa rồi tạo lại theo chuẩn; không coi đó là cập nhật vô hại.

**Phân biệt hai chữ “durable/persistent”:** durable subscription nói về **vòng đời đăng ký**; delivery mode `PERSISTENT` nói về **độ bền message trước sự cố broker**. Muốn khôi phục sau broker crash còn phụ thuộc delivery mode, cấu hình lưu trữ, transaction, expiry và chính sách provider. Durable subscription không biến mọi message `NON_PERSISTENT` thành an toàn tuyệt đối.

## 5. Tách “copy giữa các subscription” khỏi “redelivery trong một subscription”

Xét E-42 được publish cho hai subscription `audit` và `billing`:

```text
                         E-42
                   /               \
             audit copy         billing copy
               ACK OK            xử lý lỗi
              hoàn tất              |
                             rollback/recover
                                    |
                             redeliver E-42
                             cho B1 hoặc B2
```

- **Fan-out:** audit và billing có hai đơn vị giao nhận logic **khác nhau** ngay từ khi routing; ACK của audit không ACK thay billing.
- **Redelivery:** broker giao lại phần **chưa hoàn tất của billing**. Nếu billing là shared subscription, lần đầu B1 nhận nhưng lần sau B2 có thể nhận. Không tạo subscription thứ ba.
- **Duplicate do producer:** nếu producer gửi E-42 hai lần vì retry không có deduplication, đó lại là hai lần publish. Không đồng nhất với hai bản do hai subscription hay một bản bị redelivery.
- **Concurrent processing:** có nhiều consumer hoặc nhiều bản ở các subscription khác nhau thì các handler có thể chạy song song; **không suy ra** thứ tự log hoặc thứ tự hoàn thành.

Để quan sát retry, xem `JMSRedelivered` và `JMSXDeliveryCount` (provider Jakarta Messaging 2.0+ đặt thuộc tính đếm lần giao). Dùng **business event ID** riêng trong payload/header để theo dõi cùng một sự kiện qua các subscription và hỗ trợ idempotency; đừng chỉ dựa vào số lần log hay số instance `Message` trong JVM. `JMSMessageID` là metadata do provider gán và không thay thế khóa nghiệp vụ.

**Lưu ý vận hành:** JMS acknowledgement/transaction giải quyết việc broker coi message đã xử lý hay chưa, nhưng không tự bảo đảm hiệu ứng side effect trong database hoặc HTTP là “exactly once”. Handler nên **idempotent** theo `eventId`; nếu cần, dùng bảng inbox/unique constraint và transaction phù hợp. Rollback đúng cách cho phép retry; poison message cần giới hạn số lần thử và chính sách DLQ của broker.

## 6. Thực hành Spring Framework: nhìn rõ consumer nào chia sẻ subscription

Ví dụ dưới dùng Java 17, Spring Boot 3.3.13 / Spring Framework 6.x, Jakarta Messaging (`jakarta.jms`) và Apache ActiveMQ Artemis. Nó tạo:

- Một Queue `orders.queue` với **2 consumer cạnh tranh** trên cùng listener.
- Một Topic `orders.events` với hai **unshared non-durable subscription** độc lập: audit và email.
- Cùng Topic với một **shared durable subscription** tên `analytics` có **2 consumer cạnh tranh**.

Ba message được gửi tới Queue và ba message khác được publish tới Topic. Đây là ứng dụng minh họa có broker thật; không dùng mô phỏng in-memory thay cho JMS.

### 6.1. Chuẩn bị broker

Docker cài sẵn, chạy lệnh sau từ terminal (cấu hình mặc định tạo broker thử nghiệm, cổng JMS 61616):

```bash
docker run --detach --rm --name jms-demo-broker -p 61616:61616 \
  -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:latest-alpine
```

Nếu dùng PowerShell, viết lệnh trên thành **một dòng** (hoặc thay ký tự nối dòng bằng backtick PowerShell). Đợi broker khởi động trước khi chạy ứng dụng. Dùng broker mới/trống để số đếm bên dưới không lẫn backlog của lần chạy trước. Lệnh dừng sau bài học: `docker stop jms-demo-broker`.

### 6.2. Tạo dự án Gradle

`settings.gradle`:

```groovy
rootProject.name = 'jms-copy-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo.jms'
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
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
    user: demo
    password: demo
```

`src/main/java/demo/jms/JmsDemoApplication.java`:

```java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class JmsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsDemoApplication.class, args);
    }

    @Bean("queueFactory")
    DefaultJmsListenerContainerFactory queueFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(false);  // Queue
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("topicIndependentFactory")
    DefaultJmsListenerContainerFactory topicIndependentFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);   // Topic
        factory.setSessionTransacted(true);
        return factory;                  // non-durable, unshared (mặc định)
    }

    @Bean("topicSharedFactory")
    DefaultJmsListenerContainerFactory topicSharedFactory(ConnectionFactory cf) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(cf);
        factory.setPubSubDomain(true);
        factory.setSubscriptionShared(true);
        factory.setSubscriptionDurable(true);
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("queueSender")
    JmsTemplate queueSender(ConnectionFactory cf) {
        var template = new JmsTemplate(cf);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean("topicSender")
    JmsTemplate topicSender(ConnectionFactory cf) {
        var template = new JmsTemplate(cf);
        template.setPubSubDomain(true);
        return template;
    }

    @Bean
    ApplicationRunner publishDemo(
            @Qualifier("queueSender") JmsTemplate queue,
            @Qualifier("topicSender") JmsTemplate topic) {
        return args -> {
            for (int i = 1; i <= 3; i++) {
                queue.convertAndSend("orders.queue", "Q-" + i);
                topic.convertAndSend("orders.events", "T-" + i);
            }
        };
    }
}

@Component
class RoutingListeners {

    @JmsListener(
            destination = "orders.queue",
            containerFactory = "queueFactory",
            concurrency = "2-2")
    public void queueWorker(String message) {
        System.out.println("QUEUE [" + Thread.currentThread().getName() + "] " + message);
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicIndependentFactory")
    public void audit(String message) {
        System.out.println("AUDIT " + message);
    }

    @JmsListener(
            destination = "orders.events",
            containerFactory = "topicIndependentFactory")
    public void email(String message) {
        System.out.println("EMAIL " + message);
    }

    @JmsListener(
            destination = "orders.events",
            subscription = "analytics",
            containerFactory = "topicSharedFactory",
            concurrency = "2-2")
    public void analytics(String message) {
        System.out.println("ANALYTICS [" + Thread.currentThread().getName() + "] " + message);
    }
}
```

Chạy bằng Gradle 8.5+ tương thích với phiên bản Spring Boot nêu trên:

```bash
./gradlew bootRun
```

Trên Windows dùng `gradlew.bat bootRun`. Nếu dự án chưa có Gradle Wrapper, tạo wrapper bằng Gradle cài sẵn hoặc chạy `gradle bootRun`.

### 6.3. Đọc kết quả đúng cách

Với broker mới, các listener đã khởi chạy, không lỗi và không hết hạn, tổng các dòng do bốn handler in ra sẽ là:

| Handler | Những message nhận được | Số dòng dự kiến |
| --- | --- | ---: |
| `QUEUE` | Mỗi `Q-1`, `Q-2`, `Q-3` xuất hiện **một lần tổng cộng** | 3 |
| `AUDIT` | `T-1`, `T-2`, `T-3` | 3 |
| `EMAIL` | `T-1`, `T-2`, `T-3` | 3 |
| `ANALYTICS` | `T-1`, `T-2`, `T-3` **một lần cho cả nhóm analytics** | 3 |
| **Tổng** | 3 queue deliveries + 3 × 3 topic subscription deliveries | **12** |

Thứ tự các dòng và thread nhận message **không cố định**. `QUEUE` không bảo đảm cân 1/2 giữa hai thread; `ANALYTICS` cũng vậy. Nếu chạy ứng dụng nhiều lần trên broker đã có durable subscription, những message tồn đọng có thể được nhận thêm. Nếu subscriber non-durable chưa kịp hoạt động trước lúc publish, có thể thiếu dòng tương ứng; hãy đảm bảo startup thành công và thử lại với broker mới.

**Điểm phải hiểu khi đọc code:**

- `@JmsListener` đánh dấu **handler**; Spring tạo listener container và những JMS consumer thật ở phía dưới. `concurrency="2-2"` yêu cầu 2 consumer đồng thời cho Queue và cho shared subscription (nếu broker hỗ trợ).
- `setPubSubDomain(false/true)` là lựa chọn **Queue/Topic**. Producer cũng phải dùng đúng domain; gửi vào Queue tên X không đồng nghĩa publish tới Topic cùng tên X.
- Hai phương thức `audit()` và `email()` dùng **unshared non-durable**, tạo **hai subscription độc lập**; vì thế cả hai đều thấy T-1..T-3 khi online.
- `analytics()` dùng `setSubscriptionShared(true)` **và** `subscription="analytics"`: hai consumer ở **một nhóm**. `setSubscriptionDurable(true)` cho phép subscription này tiếp tục tồn tại khi ứng dụng tắt. Đối với **shared durable**, Jakarta Messaging cho phép không đặt `clientId`; với **unshared durable**, phải chỉ định `clientId` ổn định và duy nhất phù hợp chính sách broker.
- `setSessionTransacted(true)` giúp listener rollback việc consume trong JMS khi handler ném lỗi; nếu handler ghi database riêng, JMS transaction **không tự động** bao trùm database.
- Chỉ đặt `subscription="analytics"` trong annotation **không đủ** để biến một Topic listener thành shared/durable; hai thuộc tính đó nằm ở container factory. Không dùng cùng một tên shared subscription cho hai nghiệp vụ cần nhận **mỗi bên một bản**.

## 7. Các quyết định thiết kế và lỗi thường gặp

**Chọn Queue khi** nhiều worker thực hiện **cùng một loại công việc**, ví dụ xử lý một order ở đúng một worker. **Chọn Topic với các subscription riêng khi** nhiều hệ thống/nghiệp vụ cần **tự xử lý cùng một event**, ví dụ audit, notification, analytics. **Dùng shared subscription khi** một nghiệp vụ cần nhiều replica nhưng vẫn chỉ muốn **một replica xử lý mỗi event**.

Những lỗi cần tránh:

1. **“Topic có ba consumer nên luôn tạo ba bản.”** Sai: hai consumer có thể cùng một shared subscription; và subscription offline non-durable không giữ bản.
2. **“Hai `@JmsListener` cùng destination là hai consumer load-balance.”** Với Queue thường có cạnh tranh; với Topic unshared mặc định là **hai subscription**, mỗi bên nhận event.
3. **“Durable = consumer đang mở / backlog vô hạn.”** Durable nói về subscription tồn tại khi offline; còn thời gian giữ, expiry, quota, delivery mode, DLQ và policy vẫn có hiệu lực.
4. **“ACK ở một subscriber là đủ cho toàn Topic.”** Sai: mỗi subscription có trạng thái xử lý/ack độc lập.
5. **“Nhìn message xuất hiện hai lần là broker đã copy sai.”** Phải phân biệt publish hai lần, fan-out tới hai subscription, redelivery sau rollback và client log in nhiều lần.
6. **“Tăng concurrency cho unshared durable để scale.”** Unshared durable chỉ cho phép một consumer hoạt động; muốn scale cùng một nhóm, chọn shared durable và kiểm tra broker/provider tương thích.
7. **“Message selector của từng consumer trong shared subscription tùy ý khác nhau.”** Cấu hình topic/selector phải nhất quán cho cùng một shared subscription; không dùng selector để giả lập những subscription nghiệp vụ độc lập khi lại muốn tất cả các bên đều nhận message.
8. **“JMS xử lý exactly once mọi side effect.”** Handler có thể chạy lại; cần khóa nghiệp vụ/idempotency và quản lý transaction phù hợp.
9. **“Cùng tên destination chắc chắn cùng loại.”** Queue và Topic là hai domain khác nhau trong JMS. Cấu hình `pubSubDomain` sai có thể tạo đích khác ý định hoặc gặp lỗi broker.

### Tự kiểm tra hiểu bài

- Gửi một event lên Topic có `payment` (shared, 4 consumer) và `audit` (unshared, 1 consumer): **2 bản giao logic**, payment nhận ở **một trong bốn**, audit nhận **một**.
- Tắt hết consumer `payment` khi `payment` là **shared durable** đã được tạo: event mới phù hợp có thể vào backlog của payment; khi bật lại, cả nhóm chia nhau xử lý các event còn lại.
- Nếu `payment` là **shared non-durable** và tắt consumer cuối, subscription biến mất; event gửi trong khoảng trống **không được giao bù** chỉ nhờ việc tạo consumer cùng tên về sau.
- Nếu consumer Queue đã nhận nhưng rollback, broker redeliver cho một consumer khác: **vẫn là một công việc logic của Queue**, phát sinh lượt nhận lại do xử lý chưa hoàn tất.

## 8. Tài liệu chuẩn đối chiếu

- [Jakarta Messaging 3.1 Specification, mục 4.1 (Queue) và 4.2/8.3 (Topic subscription)](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html)
- [Spring Framework: Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html)
- [Spring Framework: Using Spring JMS, transactions và listener containers](https://docs.spring.io/spring-framework/reference/integration/jms/using.html)
- [Apache ActiveMQ Artemis: Docker image chính thức](https://artemis.apache.org/components/artemis/documentation/latest/docker.html)

**Ghi nhớ:** Queue phân phối **một công việc tới một consumer**; Topic nhân **lượt giao theo subscription**; consumer trong cùng **shared subscription** cạnh tranh xử lý lượt của **một** subscription.
