# Topic khi subscriber trực tuyến hoặc ngoại tuyến trong Spring JMS

## 1. Hiểu đúng bài toán

Trong mô hình publish/subscribe của Jakarta Messaging (JMS), publisher gửi message đến một **Topic**. Broker phân phối message đến các **subscription** phù hợp; mỗi subscription có thể có một hoặc nhiều consumer tùy kiểu đăng ký. Câu hỏi cốt lõi của bài này là: **nếu subscriber đang hoạt động, đang tắt, hoặc chỉ kết nối lại sau khi message đã được gửi thì chuyện gì xảy ra?**

Câu trả lời phụ thuộc trước hết vào **loại subscription**, thời điểm subscription được tạo, và điều kiện lưu giữ message trên broker.

- **Non-durable subscription**: chỉ tồn tại khi còn consumer đang hoạt động. Khi không còn consumer, subscription bị xóa; message xuất hiện trong khoảng vắng mặt không được dành riêng cho nó để nhận sau.
- **Durable subscription**: broker lưu danh tính subscription qua những lần consumer ngắt kết nối. Sau khi subscription **đã được tạo**, message phù hợp được gửi lúc consumer ngoại tuyến có thể nằm trong backlog để nhận khi consumer kết nối lại.
- **Không có cơ chế replay lịch sử mặc định**: subscriber tạo mới lần đầu **sau** khi message đã được publish không tự nhiên nhận lại các message cũ, kể cả khi tạo durable subscription.
- **Online/offline là trạng thái của consumer đối với subscription**. Chỉ có tiến trình Java đang chạy hoặc socket vừa được mở không đủ chứng minh một consumer đã đăng ký Topic.

Mục tiêu sau bài học: giải thích được thời điểm nhận/mất message, chọn non-durable hay durable theo yêu cầu nghiệp vụ, cấu hình Topic trong Spring JMS và tự kiểm chứng qua thử nghiệm ngắt/kết nối lại.

## 2. Topic khác Queue ở điểm nào?

Với **Queue**, nhiều consumer cùng lấy việc từ một hàng đợi; mỗi message thường được một consumer xử lý thành công. Với **Topic**, một message được fan-out tới **từng subscription đủ điều kiện**; hai subscription độc lập có thể cùng nhận hai bản phân phối của cùng một message.

~~~text
                          +--> Subscription A --> Consumer A
Publisher --> Topic ------+
                          +--> Subscription B --> Consumer B
                          |
                          +--> Subscription C --> Consumer C
~~~

Ví dụ hệ thống phát sự kiện `orders.changed`:

- Dịch vụ tính điểm và dịch vụ audit có hai subscription riêng: cả hai có thể nhận sự kiện `Order-42`.
- Hai consumer cùng chia sẻ **một shared subscription** thì cạnh tranh công việc trong subscription đó; mỗi message của subscription chỉ giao cho một consumer, không fan-out tới cả hai consumer.
- Hai phương án trên khác nhau dù đều có thể dùng Topic.

**Quy tắc dễ nhớ:** Topic phân phối theo **subscription**, còn việc message có được nhận khi subscriber trở lại hay không do **vòng đời subscription** quyết định.

## 3. Online/offline với non-durable và durable

Giả định broker vẫn hoạt động, không có selector loại message, message chưa hết hạn và được giữ trong hạn mức lưu trữ.

| Tình huống | Non-durable subscription | Durable subscription đã tồn tại |
| --- | --- | --- |
| Consumer đang hoạt động khi M1 được publish | Có thể nhận M1 | Có thể nhận M1 |
| Consumer đã đóng/ngắt, M2 được publish | Không giữ M2 cho subscription đã biến mất | Broker tích lũy M2 cho subscription |
| Consumer tạo lại/kết nối lại sau M2 | Nhận các message mới từ lúc đăng ký lại; không tự nhận M2 | Có thể nhận backlog M2 còn hợp lệ rồi tiếp tục nhận message mới |
| M0 được publish **trước lần đầu** tạo subscription | Không nhận M0 | Không nhận M0 |
| Consumer dừng vĩnh viễn | Subscription bị loại bỏ | Subscription vẫn chiếm tài nguyên cho đến khi được xóa/được quản trị |

Cụm từ **“durable subscriber”** thường là cách gọi ngắn của **consumer dùng durable subscription**. Thực thể được broker giữ lại là subscription và trạng thái message của nó, không phải thread/đối tượng Java đang chạy.

### Ví dụ theo dòng thời gian

Giả sử Topic `news.events` có subscription A non-durable và B durable. Cả hai được tạo tại T0; tại T1 cả hai đang online.

~~~text
T0: Tạo A (non-durable) và B (durable)
T1: Publish M1        -> A nhận M1; B nhận M1
T2: Đóng consumer A/B
T3: Publish M2, M3    -> A không có backlog; B giữ M2, M3
T4: Khởi động lại A/B -> A không nhận M2/M3; B nhận M2/M3 nếu còn hợp lệ
T5: Publish M4        -> Cả A và B đều có thể nhận M4
~~~

Các điều kiện quan trọng:

1. **B phải được tạo trước T3.** Nếu B chỉ được tạo tại T4, `M2` và `M3` không có trong backlog của B.
2. “Nhận” nghĩa là message được giao để xử lý; việc đã xử lý bền vững hay chưa còn phụ thuộc ACK/transaction và lỗi ứng dụng.
3. Nếu M2 hết TTL, bị selector lọc hoặc broker loại vì chính sách lưu trữ, B không thể đòi lại message đó chỉ bằng cách bật durable.
4. Nếu một non-durable consumer chỉ bị chập chờn mạng nhưng chưa thực sự bị broker coi là đóng, trạng thái tạm thời phụ thuộc provider và thời điểm phát hiện lỗi. Không dựa vào khoảng chập chờn này để bảo đảm dữ liệu.

## 4. Vòng đời subscription và định danh khi kết nối lại

### 4.1. Non-durable: subscription gắn với consumer

Khi tạo consumer bình thường cho Topic, provider tạo một non-durable subscription. Trong dạng **unshared**, consumer đóng thì subscription kết thúc. Trong dạng **shared non-durable**, subscription có thể có nhiều consumer nhưng vẫn bị xóa khi consumer cuối cùng đóng. Message publish sau thời điểm đó không được tích lũy cho subscription vừa biến mất.

Non-durable hợp lý khi dữ liệu chỉ hữu ích “ngay lúc này”: cập nhật màn hình live, tín hiệu đo lường có thể bỏ qua, trạng thái có thể tái đồng bộ từ nguồn khác. Không nên dùng khi mỗi sự kiện đều cần được xử lý sau đợt bảo trì hoặc restart.

### 4.2. Durable: broker giữ danh tính và backlog

Với **unshared durable subscription**, danh tính thường bao gồm:

- **`clientId`** của JMS connection: ổn định qua các lần restart, duy nhất đối với các kết nối đang hoạt động theo quy tắc provider.
- **`subscriptionName`**: tên subscription ổn định. Trong Spring có thể đặt bằng thuộc tính `subscription` của `@JmsListener`.
- **Topic** gắn với subscription và các điều kiện như selector/noLocal: cần nhất quán khi tái kết nối.

Tại lần kết nối đầu, consumer đăng ký subscription. Khi consumer đóng, broker **không** xóa durable subscription; message phù hợp tiếp tục được tích lũy. Lần sau, consumer dùng đúng danh tính có thể tiếp tục lấy backlog.

**Đừng đổi clientId hoặc subscriptionName tùy tiện sau deploy**: đổi định danh có thể làm ứng dụng tạo subscription mới và để lại backlog cũ chưa được xử lý. Với unshared durable subscription, chỉ một consumer active được gắn vào subscription tại một thời điểm; scale ngang bằng nhiều instance dùng cùng định danh sẽ gây xung đột.

### 4.3. Shared durable khi cần nhiều consumer cùng xử lý backlog

Jakarta Messaging hỗ trợ **shared durable subscription**. Nhiều consumer có thể cùng gắn vào *một* durable subscription và chia nhau message. Với loại shared, clientId có thể không được đặt; nếu đã đặt khi tạo, các consumer tham gia phải dùng cùng định danh theo hợp đồng JMS/provider.

So sánh:

| Tổ chức consumer | Kết quả với một message phù hợp |
| --- | --- |
| Subscription `audit` và `analytics` độc lập | Mỗi subscription có một bản phân phối |
| Hai consumer cùng shared subscription `analytics` | Chỉ một trong hai nhận message đó |
| Hai unshared durable consumer dùng trùng clientId/name cùng lúc | Không hợp lệ; provider có thể báo lỗi khi consumer thứ hai đăng ký |

Muốn **broadcast cho từng dịch vụ**, hãy tạo subscription riêng theo dịch vụ; muốn **chia tải cho các instance của cùng dịch vụ**, cân nhắc shared durable hoặc kiến trúc queue phù hợp broker.

### 4.4. Khi nào subscription thật sự bị xóa?

Đóng consumer hoặc tắt ứng dụng **không phải** hành động xóa durable subscription. Để ngừng giữ backlog lâu dài, cần thao tác quản trị tương ứng hoặc gọi `Session.unsubscribe(name)` / `JMSContext.unsubscribe(name)` trong điều kiện hợp lệ (không còn consumer active hoặc message thuộc transaction/ACK đang dở). Xóa có chủ đích, sau khi chắc chắn không cần dữ liệu còn chờ.

## 5. “Durable” không đồng nghĩa với “persistent message”

Có hai chiều độc lập:

1. **Subscription durability**: subscription có tiếp tục tồn tại khi consumer offline hay không.
2. **Delivery mode** của message: `PERSISTENT` yêu cầu provider xử lý thông điệp với mức bảo vệ bền vững hơn qua lỗi vận chuyển/broker; `NON_PERSISTENT` ưu tiên hiệu năng và có rủi ro mất khi gặp lỗi.

Một message được gửi ở chế độ `PERSISTENT` **không tự biến non-durable subscription thành durable**. Nếu consumer non-durable đã đóng, broker không có nghĩa vụ tạo backlog của nó. Ngược lại, durable subscription có thể nhận message gửi dạng `NON_PERSISTENT` khi broker còn giữ message; nhưng không thể giả định message vẫn còn sau crash/restart broker.

Khả năng nhận backlog thực tế còn chịu tác động của:

- **TTL/expiration**: message đã hết hạn không được giao sau khi subscriber trở lại.
- **Message selector**: chỉ message có property khớp bộ lọc của subscription được tích lũy.
- **Retention, quota và chính sách broker**: hết dung lượng, giới hạn số message, chính sách drop, dead-letter hoặc quản trị có thể thay đổi kết quả.
- **Broker restart/failover**: cần cấu hình journal/persistence, cụm broker và vận hành tương ứng nếu muốn bảo đảm qua hỏng hóc.
- **ACK và transaction**: message được delivery không có nghĩa đã commit xử lý nghiệp vụ; rollback hoặc crash có thể khiến delivery lại.

Vì vậy, cần đọc đúng ba câu hỏi riêng: **subscription còn tồn tại không? message có được giữ không? xử lý đã được xác nhận chưa?**

## 6. Ví dụ Spring Boot 3.3 / Spring JMS, Java 17

Ví dụ dưới đây dùng **một broker ActiveMQ Artemis đang chạy riêng**, để các tiến trình publisher/subscriber cùng nhìn thấy Topic và backlog. Không dùng broker nhúng riêng cho từng tiến trình, vì như thế chúng sẽ không giao tiếp với nhau.

Điều kiện: JDK 17+, Gradle 8.x, một Artemis broker hỗ trợ Jakarta Messaging và cho phép client truy cập địa chỉ `tcp://127.0.0.1:61616`. Cấu hình người dùng/mật khẩu, tự tạo Topic (nếu cần) và lưu trữ durable phải phù hợp broker thực tế. Dự án mẫu đặt các file Java trong `src/main/java/demo/jms/`.

### 6.1. Build và kết nối broker

`settings.gradle`:

~~~groovy
rootProject.name = 'jms-topic-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
~~~

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://127.0.0.1:61616
spring.jms.pub-sub-domain=true
~~~

Nếu broker yêu cầu đăng nhập, bổ sung `spring.artemis.user` và `spring.artemis.password` bằng tài khoản được broker cấp. Thuộc tính **`spring.jms.pub-sub-domain=true`** làm `JmsTemplate` gửi đến **Topic**; cấu hình riêng cho listener factory bên dưới cũng phải bật Topic. Mặc định của Spring Boot cho `JmsTemplate` thường là queue mode, nên bỏ sót bước này là lỗi rất hay gặp.

### 6.2. Ứng dụng và hai kiểu listener

`TopicDemoApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TopicDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TopicDemoApplication.class, args);
    }
}
~~~

`TopicConfig.java`:

~~~java
package demo.jms;

import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class TopicConfig {

    @Bean("nonDurableTopicFactory")
    DefaultJmsListenerContainerFactory nonDurableTopicFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }

    @Bean("durableTopicFactory")
    DefaultJmsListenerContainerFactory durableTopicFactory(
            ConnectionFactory connectionFactory) {
        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setPubSubDomain(true);
        factory.setSubscriptionDurable(true);
        factory.setClientId("audit-service-v1");
        factory.setConcurrency("1");
        factory.setSessionTransacted(true);
        return factory;
    }
}
~~~

`NonDurableSubscriber.java`:

~~~java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("non-durable")
public class NonDurableSubscriber {

    @JmsListener(
        destination = "demo.events",
        containerFactory = "nonDurableTopicFactory"
    )
    public void onMessage(String body) {
        System.out.println("LIVE RECEIVED: " + body);
    }
}
~~~

`DurableSubscriber.java`:

~~~java
package demo.jms;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("durable")
public class DurableSubscriber {

    @JmsListener(
        destination = "demo.events",
        containerFactory = "durableTopicFactory",
        subscription = "audit-events-v1"
    )
    public void onMessage(String body) {
        System.out.println("DURABLE RECEIVED: " + body);
    }
}
~~~

Giải thích các dòng quyết định:

- `setPubSubDomain(true)`: listener nhận từ **Topic**, không phải Queue.
- `setSubscriptionDurable(true)`: factory thứ hai tạo durable subscription.
- `setClientId("audit-service-v1")` + `subscription = "audit-events-v1"`: định danh dùng lại qua các lần chạy. Giữ nguyên chúng trong thử nghiệm.
- `setConcurrency("1")`: unshared durable subscription chỉ cho phép một consumer active, nên không cố mở nhiều consumer cùng subscription.
- `setSessionTransacted(true)`: nếu listener ném exception thì session có thể rollback và message có thể được giao lại; đây là lựa chọn phù hợp hơn AUTO_ACKNOWLEDGE mặc định cho bài toán cần độ tin cậy.
- `@Profile` giúp chạy riêng hai loại subscriber, tránh tự động kích hoạt mọi listener khi chạy publisher.

### 6.3. Publisher gửi message đến Topic

`TopicPublisher.java`:

~~~java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
@Profile("publisher")
public class TopicPublisher implements ApplicationRunner {
    private final JmsTemplate jmsTemplate;

    public TopicPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        String body = args.getNonOptionArgs().isEmpty()
            ? "sample-event"
            : String.join(" ", args.getNonOptionArgs());

        jmsTemplate.convertAndSend("demo.events", body);
        System.out.println("PUBLISHED: " + body);
    }
}
~~~

Spring Boot cung cấp `ConnectionFactory` và `JmsTemplate` từ starter Artemis. `convertAndSend` chuyển chuỗi thành JMS text message và publish lên `demo.events` khi `pub-sub-domain` đã được bật. Lệnh gửi hoàn tất không chứng minh subscriber đã xử lý; hãy kiểm tra log bên consumer hoặc trạng thái ACK trên broker.

### 6.4. Thử nghiệm có thể lặp lại

Tạo JAR trong thư mục dự án:

~~~bash
gradle bootJar
~~~

JAR ví dụ là `build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar`. Mỗi lệnh Java bên dưới chạy trong **terminal riêng**; giữ broker chung hoạt động suốt thử nghiệm. Nếu trình chạy publisher không tự thoát do hạ tầng JMS, dừng nó sau khi log `PUBLISHED` xuất hiện.

**Thử nghiệm A – non-durable**

1. Chạy subscriber: `java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=non-durable`.
2. Khi log cho thấy listener đã kết nối broker, ở terminal khác publish `live-1`:

   ~~~bash
   java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=publisher live-1
   ~~~

3. Subscriber đang online sẽ in `LIVE RECEIVED: live-1` (khi giao thành công).
4. Dừng hẳn tiến trình non-durable. Publish `offline-1` khi không có non-durable consumer:

   ~~~bash
   java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=publisher offline-1
   ~~~

5. Khởi động lại non-durable subscriber. Bạn **không** thấy `offline-1` được phát lại chỉ vì subscriber kết nối lại. Publish thêm `live-2` sau khi listener sẵn sàng thì nó có thể nhận `live-2`.

**Thử nghiệm B – durable**

1. Chạy `java -jar build/libs/jms-topic-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=durable` ít nhất một lần để **tạo durable subscription trước**. Đợi listener kết nối thành công.
2. Publish `durable-live-1`; xác nhận có log `DURABLE RECEIVED: durable-live-1`.
3. Dừng hẳn durable subscriber; **không xóa subscription trên broker**.
4. Publish `durable-offline-1` và `durable-offline-2` lúc subscriber tắt.
5. Khởi động lại durable subscriber **với cùng** `clientId` và `subscription`. Nếu message chưa hết hạn, broker giữ được backlog và không bị chính sách lưu trữ loại bỏ, log subscriber sẽ lần lượt ghi nhận các message được gửi lúc offline. Thứ tự quan sát còn phụ thuộc bảo đảm thứ tự của provider/producer và các điều kiện đồng thời; đừng dựa vào thứ tự dòng log của nhiều tiến trình.

**Thử nghiệm C – tạo durable muộn**

Trên một subscription/tên mới hoàn toàn, hãy publish `before-first-subscribe` **trước** khi khởi tạo durable subscription mới. Sau đó khởi tạo subscription lần đầu. Bạn **không** nhận lại `before-first-subscribe` theo quy tắc JMS chuẩn; durable chỉ giữ message từ sau khi subscription được tạo. Muốn replay lịch sử cần cơ chế lưu sự kiện riêng hoặc tính năng riêng của broker.

Để lặp lại thử nghiệm B với trạng thái sạch, quản lý subscription ở broker theo hướng dẫn vận hành của provider. Tránh xóa subscription thật khi còn backlog nghiệp vụ cần xử lý.

## 7. ACK, lỗi và xử lý lặp

Durable subscription giải quyết vấn đề **subscriber vắng mặt**, nhưng không tự giải quyết mọi vấn đề **xử lý đúng một lần**:

1. Broker phát message cho listener.
2. Listener chạy logic ứng dụng.
3. Session commit hoặc ACK theo chế độ cấu hình.
4. Nếu lỗi xảy ra trước commit, broker có thể giao lại message; nếu ứng dụng đã cập nhật DB nhưng chưa commit việc nhận JMS, tác dụng phụ có thể bị lặp.

Do vậy, khi xử lý đơn hàng hoặc phát thông báo quan trọng, cần dùng **idempotency key** (ví dụ `eventId`) và bảo vệ thao tác nghiệp vụ trước duplicate. `setSessionTransacted(true)` chỉ giao dịch các thao tác trong JMS session; không tự động biến cập nhật một cơ sở dữ liệu bên ngoài thành một distributed transaction với broker. Với lỗi lặp liên tục, cần chính sách retry, backoff và dead-letter queue (DLQ) phù hợp broker.

Không suy ra “đã giao” = “đã xử lý thành công”; quan sát cả số message pending, redelivery và ACK/commit.

## 8. Sai lầm thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Điều cần kiểm tra |
| --- | --- | --- |
| Subscriber không nhận message nào | Publisher/Listener bị cấu hình queue mode hoặc khác tên Topic | `spring.jms.pub-sub-domain`, `setPubSubDomain(true)`, tên destination |
| Offline rồi bật lại bị mất message | Dùng non-durable, hoặc durable chưa được tạo trước lúc publish | Kiểu subscription và thời điểm tạo đầu tiên |
| Tưởng PERSISTENT là tự lưu cho mọi subscriber | Nhầm delivery mode với durability của subscription | Trạng thái durable theo broker, không chỉ header của message |
| Restart làm backlog “biến mất” | Đổi clientId/subscriptionName, TTL hết hạn, retention policy hoặc xóa subscription | Danh tính trước/sau restart, expiry, quota và log broker |
| Instance thứ hai lỗi client ID hoặc duplicate consumer | Hai unshared durable listener cùng định danh đang chạy | ClientId duy nhất khi active, concurrency=1; xem shared durable khi cần scale |
| Nhận lại một message sau lỗi | Transaction rollback, chưa ACK, crash trước commit | Cấu hình transaction và xử lý idempotent |
| Có message trên Topic nhưng subscriber không thấy | Message không khớp selector/noLocal hoặc được publish trước khi subscription tồn tại | Selector, property, thời điểm tạo và broker routing |
| Broker khởi động lại rồi backlog mất | Chưa cấu hình persistence/HA hoặc chính sách lưu trữ không đáp ứng yêu cầu | Chế độ PERSISTENT, journal và cấu hình broker |

Khi debug, dùng danh tính **Topic + clientId + subscriptionName** (hoặc tên shared subscription phù hợp) để tìm đúng subscription; đừng chỉ nhìn số connection hay số message đang tồn tại toàn broker.

## 9. Chọn phương án theo nhu cầu nghiệp vụ

- **Dashboard live, dữ liệu có thể bỏ qua**: Topic + non-durable subscription, khi reconnect có thể tự lấy snapshot mới.
- **Audit, đồng bộ dữ liệu, sự kiện phải bắt kịp sau bảo trì**: durable subscription, delivery mode và broker persistence phù hợp, transaction/ACK và idempotency.
- **Mỗi dịch vụ cần một bản sao sự kiện**: các subscription tách biệt, mỗi dịch vụ tự quyết định durable hay không.
- **Nhiều instance của cùng dịch vụ muốn chia nhau backlog**: shared durable subscription (nếu provider hỗ trợ đúng nhu cầu), hoặc thiết kế queue/group consumer phù hợp.
- **Cần đọc lại lịch sử không giới hạn theo offset/time**: cân nhắc event log chuyên dụng hoặc tính năng riêng của broker; JMS Topic durable thông thường là backlog chưa ACK của subscription, không phải kho lưu sự kiện vô hạn.

## 10. Tự kiểm tra hiểu bài

1. Publisher gửi M1, sau đó consumer A mới tạo **durable subscription lần đầu**. A có nhận M1 không? **Không** theo JMS chuẩn; M1 được gửi trước lúc subscription tồn tại.
2. A đã có durable subscription, tắt trong 10 phút; M2 publish lúc tắt và TTL là 1 phút. A bật lại sau 10 phút có chắc nhận M2 không? **Không**; M2 có thể đã hết hạn.
3. Hai subscription độc lập A/B cùng theo dõi một Topic. Một message được gửi khi cả hai active thì ai có thể nhận? **Cả A và B** (mỗi subscription một bản phân phối).
4. Hai consumer cùng một shared durable subscription có cùng nhận một message không? **Không**; message đó chỉ được giao cho một consumer trong shared subscription.
5. Message `PERSISTENT` gửi khi một non-durable consumer đã đóng có tự được replay khi mở lại không? **Không**.
6. Vì sao listener durable cần idempotency? Vì crash/rollback trước ACK hoặc commit có thể dẫn đến **redelivery**.

## 11. Ghi nhớ và tài liệu đối chiếu

**Công thức quyết định:** *Có subscriber hoạt động ngay lúc publish?* → non-durable có thể nhận. *Subscription durable đã tồn tại, nhưng consumer tạm offline?* → broker có thể giữ message hợp lệ để giao khi reconnect. *Subscription chưa từng được tạo?* → không có backlog lịch sử tự động.

Tài liệu chính thức để tra cứu chi tiết, nhất là khi triển khai trên broker khác:

- Jakarta Messaging 3.1 Specification, phần **Subscriptions**, **Creating a consumer on a topic**, **Reliability**: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework – **Annotation-driven Listener Endpoints**: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Spring Framework – **Using Spring JMS** (listener container, ACK và transaction): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot – **JMS / ActiveMQ Artemis Support**: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
