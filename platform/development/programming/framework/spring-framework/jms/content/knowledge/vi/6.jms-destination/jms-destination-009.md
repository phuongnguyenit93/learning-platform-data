# Quyền tạo destination khác với quyền gửi nhận trong Spring JMS

## 1. Mục tiêu và vấn đề thực tế

Một ứng dụng có thể **gửi message vào Queue** mà không được phép **tạo Queue mới**. Tương tự, một worker có thể **nhận message** nhưng không được phép **gửi message**, xóa queue hay thay đổi cấu hình broker.

Đây là sự phân biệt giữa hai nhóm thao tác:

- **Provisioning / administration:** tạo, xóa, cấu hình các destination vật lý trên message broker, hoặc quản lý những subscription/tài nguyên liên quan.
- **Messaging:** gửi (`send`), nhận (`consume`) hoặc đọc không tiêu thụ (`browse`) message trên destination **đã có và được cấp quyền**.

Phân biệt này đặc biệt quan trọng với Spring JMS vì code như `jmsTemplate.convertAndSend("orders.commands", data)` và `@JmsListener(destination = "orders.commands")` thường chỉ khai báo **tên destination**. Việc tài nguyên thật được tạo sẵn, tự tạo hay bị từ chối do **JMS provider/broker** quyết định.

Sau bài này, bạn cần:

1. Phân biệt `Queue`/`Topic` là đối tượng API và destination vật lý trên broker.
2. Giải thích vì sao `Session.createQueue()` không đồng nghĩa với quyền tạo queue trên server.
3. Tách quyền tạo/xóa, gửi, nhận, browse và quản trị; áp dụng **least privilege**.
4. Hiểu ảnh hưởng của cấu hình **auto-create** của ActiveMQ Artemis.
5. Cấu hình thử nghiệm Spring Boot + Artemis với tài khoản gửi riêng, tài khoản nhận riêng.
6. Chẩn đoán khi ứng dụng có tên queue đúng nhưng vẫn không gửi/nhận được vì thiếu quyền hoặc destination chưa tồn tại.

## 2. Hai lớp phải phân biệt: API destination và tài nguyên broker

Jakarta Messaging (JMS) định nghĩa `jakarta.jms.Destination`, với hai kiểu chính là `Queue` (point-to-point) và `Topic` (publish/subscribe). Một đối tượng Java mang tên `orders.commands` **không tự bảo đảm** broker có queue hoặc topic vật lý tương ứng.

~~~mermaid
flowchart LR
    A["Ứng dụng Spring JMS"] --> B["Queue/Topic object mang tên"]
    B --> C["Kết nối và thao tác send/consume"]
    C --> D{"Broker kiểm tra"}
    D --> E["Destination tồn tại hoặc auto-create hợp lệ?"]
    E --> F["Tài khoản có quyền phù hợp?"]
    F --> G["Giao hoặc nhận message"]
~~~

**Cụ thể:**

~~~java
// Fragment: Session session đã được tạo từ Connection.
jakarta.jms.Queue queue = session.createQueue("orders.commands");
~~~

`createQueue(String)` tạo một **đối tượng Queue gói tên do provider hiểu**; theo đặc tả JMS, nó **không phải lệnh tạo queue vật lý**. Tương tự, `session.createTopic("domain.events")` không phải lệnh tạo topic vật lý. Một provider có thể hỗ trợ tự tạo tài nguyên trong quá trình gửi/đăng ký consumer, nhưng đó là **cơ chế riêng của provider**.

Với JNDI:

~~~java
// Fragment: context đã được cấu hình cho JMS provider.
jakarta.jms.Queue queue =
        (jakarta.jms.Queue) context.lookup("jms/queue/Orders");
~~~

`lookup` tìm một **administered object** đã được cấu hình theo JNDI; lookup cũng không tự cấp quyền `send`/`consume` và không đồng nghĩa với tạo một queue vật lý. Cú pháp tên JNDI khác tên thực trên broker và phụ thuộc cấu hình nhà cung cấp.

**Ngoại lệ cần nhớ:** `Session.createTemporaryQueue()`/`createTemporaryTopic()` thực sự tạo **temporary destination** có vòng đời gắn với connection. Vì vậy thao tác này có thể cần quyền tạo tài nguyên tương ứng ở broker. Temporary destination thường dùng cho `JMSReplyTo` trong request/reply và cần chính sách quyền riêng; đừng suy ra từ `createQueue(String)`.

### 2.1. Ví dụ cụ thể

Giả sử hệ thống có tài nguyên vật lý `orders.commands`:

- Dịch vụ **Order API** chỉ gửi lệnh `ORDER-101`.
- Dịch vụ **Order Worker** chỉ nhận và xử lý lệnh.
- Nhóm vận hành tạo queue, đặt độ bền, DLQ, max-size, ACL và theo dõi backlog.

Order API **không cần quyền tạo/xóa queue** chỉ vì nó biết tên và có thể gửi. Order Worker **không cần quyền tạo/xóa queue** chỉ vì nó dùng `@JmsListener`.

Nếu chưa tạo queue mà broker đang **auto-create**, lần gửi/nhận đầu tiên *có thể* kích hoạt tạo tài nguyên. Chính sách cấp phép và hành vi cụ thể sẽ do broker, phiên bản, security manager và cấu hình xác định; ở môi trường cần kiểm soát chặt, nên **provision trước** và **khóa auto-create** cho namespace quan trọng.

## 3. Authentication khác authorization

Trước khi nói đến quyền tạo/gửi/nhận, cần tách:

- **Authentication:** xác thực danh tính kết nối, ví dụ user `order-sender` đăng nhập thành công vào Artemis.
- **Authorization:** quyết định tài khoản đó được làm những thao tác gì, trên **address/queue nào**.

Đăng nhập thành công không có nghĩa người dùng được gửi mọi Queue, đọc mọi Topic hay tạo destination tùy ý. Cùng một user có thể được `send` tới `orders.commands` nhưng bị từ chối `consume` trên chính queue đó.

Ví dụ bốn vai trò:

| Role | Mục đích | Quyền tối thiểu trên `orders.commands` |
| --- | --- | --- |
| `order-senders` | Producer gửi lệnh | `send` |
| `order-workers` | Consumer xử lý lệnh | `consume` |
| `order-auditors` | Xem message khi được phép | `browse` |
| `broker-admins` | Provision/xóa destination có kiểm soát | `createAddress`, `createDurableQueue`, v.v. |

Đây là **ví dụ phân quyền**, không phải các role có sẵn của JMS. Jakarta Messaging xác định API và ngữ nghĩa gửi/nhận; tên quyền và cách gán role là **cụ thể theo provider**.

Với ứng dụng production, nên quản lý tài khoản broker riêng cho từng service thay vì dùng một tài khoản `admin` cho cả producer và consumer. Việc chia role giúp thu hẹp tác động nếu credentials của một service bị lộ hoặc service gửi message sai địa chỉ.

## 4. Các nhóm quyền trên ActiveMQ Artemis

ActiveMQ Artemis cung cấp mô hình bảo mật theo role, chủ yếu áp dụng **trên address** (và có thể tinh chỉnh consume bằng fully qualified queue name trong một số trường hợp). Những quyền thường gặp:

| Quyền Artemis | Ý nghĩa | Ví dụ đối tượng cần |
| --- | --- | --- |
| `createAddress` | Tạo một **address** phù hợp `match`. | Hệ thống provisioning, thao tác auto-create address. |
| `deleteAddress` | Xóa address phù hợp. | Công cụ quản trị, thao tác bảo trì. |
| `createDurableQueue` | Tạo durable queue dưới address phù hợp. | Provision persistent work queue/subscription. |
| `deleteDurableQueue` | Xóa durable queue. | Vận hành sau khi kiểm tra backlog và dữ liệu. |
| `createNonDurableQueue` | Tạo non-durable queue. | Một số subscription/temporary resource. |
| `deleteNonDurableQueue` | Xóa non-durable queue. | Dọn subscription/tài nguyên tạm theo policy. |
| `send` | Gửi message tới address phù hợp. | Producer. |
| `consume` | Nhận/tiêu thụ message từ queue trên address phù hợp. | Worker, `@JmsListener`. |
| `browse` | Xem message trong queue **không tiêu thụ**. | `QueueBrowser`, người quan sát. |
| `manage` | Dùng management operations qua management address. | Quản trị broker theo chính sách. |
| `view` / `edit` | Phân quyền đọc/ghi chi tiết cho management API nếu tính năng quản trị tương ứng được bật. | Console/JMX/API quản lý. |

**Không có quyền nào trong danh sách tự động suy ra mọi quyền khác.** Chẳng hạn `send` không có nghĩa được `consume` hoặc `deleteDurableQueue`. `browse` khác `consume`: browse không loại message khỏi queue; consume có thể dẫn đến acknowledgment và xóa message khỏi backlog theo semantics nhận.

Tuy nhiên, **auto-create** và các cơ chế tương thích/plugin của broker có thể khiến thao tác gửi/nhận tạo tài nguyên phụ trợ. Muốn kiểm chứng least privilege cần kiểm tra **cả cấu hình auto-create lẫn ACL**, không chỉ nhìn bảng quyền.

### 4.1. Artemis dùng address và queue, không chỉ tên Queue của JMS

Trong Artemis:

- **Address:** điểm nhận message từ producer, sau đó định tuyến theo quy tắc.
- **Queue:** nơi message được lưu/consumer nhận; một address có thể có một hoặc nhiều queue.
- **Anycast:** thường dùng cho mô hình JMS Queue, chia công việc cho competing consumers trên một queue đích.
- **Multicast:** thường dùng cho mô hình JMS Topic, phân phối cho các subscription queue phù hợp.

Ví dụ một address `orders.commands` chứa một queue cùng tên. Producer gửi tới address, worker consume từ queue. Permission `send` được kiểm tra với address; permission `consume` áp dụng khi nhận từ queue gắn với address.

Với địa chỉ có nhiều queue, Artemis có thể hỗ trợ cú pháp **FQQN** `address::queue` để tham chiếu queue cụ thể và giới hạn `consume` tinh hơn. Nhưng **không giả định** ACL `send` trên FQQN tự chặn message gửi tới address chung: message gửi tới address có thể vẫn được route tới nhiều queue. Cần đọc tài liệu security/FQQN trước khi phân quyền theo từng subscription.

## 5. Vì sao lệnh tạo Queue trong code không đòi quyền admin?

Xem đoạn Java JMS:

~~~java
// Fragment: có ConnectionFactory factory.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.commands");
    context.createProducer().send(queue, "ORDER-101");
}
~~~

Ở đây có **hai việc tách biệt**:

1. `context.createQueue("orders.commands")` tạo **đối tượng tham chiếu tên**.
2. `createProducer().send(queue, ...)` yêu cầu broker thực hiện **gửi message** và có thể kiểm tra thêm khả năng định tuyến/tài nguyên.

Nếu `orders.commands` đã được provision và tài khoản chỉ có `send`, lần gửi **vẫn có thể thành công** dù tài khoản không có `createAddress` hay `createDurableQueue`. Điều kiện là tài khoản đăng nhập đúng, broker hoạt động và không có policy khác chặn gửi.

Nếu destination chưa tồn tại:

- Với **auto-create tắt**, broker không tự provision nên thao tác gửi/nhận có thể thất bại hoặc không được định tuyến; biểu hiện cụ thể phụ thuộc provider và policy.
- Với **auto-create bật**, broker có thể tạo address/queue theo quy tắc; việc tạo có thể cần quyền tạo hoặc được security manager xử lý theo cơ chế riêng.
- Với **sai routing type** hoặc tên address/queue, gửi vẫn không có nghĩa một consumer dự kiến sẽ nhận đúng message.

Do đó **“API có chữ create” không đồng nghĩa “ứng dụng đã có quyền tạo tài nguyên broker”**. Cần phân biệt đối tượng Java, hành vi side effect và kiểm tra quyền ở server.

## 6. Cấu hình Artemis: provision trước, gửi/nhận sau

Ví dụ dưới đây giả định **ActiveMQ Artemis broker độc lập đã được khởi tạo và bật security**. Các đoạn XML là các **khối cấu hình thuộc `etc/broker.xml`**, chèn vào đúng phần của file hiện có; không phải một file XML hoàn chỉnh để chạy độc lập. Tài khoản `sender` thuộc role `order-senders`, `worker` thuộc role `order-workers`, tài khoản vận hành thuộc `broker-admins`; việc tạo user và gán role thực hiện trong cơ chế authentication broker đang dùng.

### 6.1. Khai báo address + Queue tồn tại từ trước

~~~xml
<addresses>
    <address name="orders.commands">
        <anycast>
            <queue name="orders.commands">
                <durable>true</durable>
            </queue>
        </anycast>
    </address>
</addresses>
~~~

Đây là mẫu cấu hình **anycast** của Artemis. Kỹ thuật này khác với việc gọi `session.createQueue(...)`: broker tạo tài nguyên từ cấu hình lúc khởi động hoặc reload theo cơ chế được hỗ trợ.

### 6.2. Tắt tự tạo trong namespace quan trọng

~~~xml
<address-settings>
    <address-setting match="orders.#">
        <auto-create-addresses>false</auto-create-addresses>
        <auto-create-queues>false</auto-create-queues>
    </address-setting>
</address-settings>
~~~

`orders.#` theo wildcard mặc định của Artemis khớp các address trong namespace `orders`. Mục đích: service chỉ được dùng tài nguyên đã được provision, không tự sinh thêm queue vì gõ nhầm tên. Không cấu hình trùng một `address-setting` cùng `match` mà không hiểu cách broker xử lý; hãy nhập các thuộc tính vào block hiện có để giữ những policy như redelivery, paging, DLQ.

**Cẩn trọng:** việc tắt auto-create dành cho các queue ứng dụng đã provision; một số loại Topic subscription cần tạo queue đại diện subscription trong quá trình hoạt động. Phải đánh giá policy cho namespace Topic/temporary destinations riêng, không áp dụng máy móc lên toàn broker.

### 6.3. Tách quyền theo vai trò

~~~xml
<security-settings>
    <security-setting match="orders.#">
        <permission type="send" roles="order-senders,broker-admins"/>
        <permission type="consume" roles="order-workers,broker-admins"/>
        <permission type="browse" roles="order-auditors,broker-admins"/>

        <permission type="createAddress" roles="broker-admins"/>
        <permission type="deleteAddress" roles="broker-admins"/>
        <permission type="createDurableQueue" roles="broker-admins"/>
        <permission type="deleteDurableQueue" roles="broker-admins"/>
        <permission type="createNonDurableQueue" roles="broker-admins"/>
        <permission type="deleteNonDurableQueue" roles="broker-admins"/>
    </security-setting>
</security-settings>
~~~

**Cách hiểu:** tài khoản role `order-senders` chỉ có quyền `send` phù hợp; role `order-workers` chỉ có `consume`; role `order-auditors` chỉ có `browse`; role `broker-admins` có các quyền trên address/queue này. Nếu cần `manage` hoặc `view`/`edit` qua management address, đó là **chính sách bổ sung**, không tự xuất hiện do cấp `createAddress`.

Đây là **ví dụ minh họa một namespace**: phải đảm bảo credentials, roles, wildcard mặc định và những block bảo mật khác được cấu hình tương thích. Trong Artemis, nếu nhiều security settings khớp một address, **match cụ thể nhất được ưu tiên và không tự kế thừa permission từ match rộng hơn**. Chẳng hạn một block `orders.commands` cụ thể hơn có thể thay thế toàn bộ quyền của `orders.#`. Hãy kiểm tra tất cả block đang áp dụng.

**Không thay** toàn bộ `broker.xml` chỉ bằng các snippet trên; file còn chứa acceptor, connectors, journal, security manager và các thiết lập khác. Với production, thay đổi phải được kiểm thử và triển khai qua quy trình vận hành.

### 6.4. Trạng thái kỳ vọng sau cấu hình

| Tài khoản/role | Gửi vào queue tồn tại | Nhận từ queue tồn tại | Tạo/xóa destination | Browse |
| --- | --- | --- | --- | --- |
| `sender` / `order-senders` | Có | Không | Không | Không |
| `worker` / `order-workers` | Không | Có | Không | Không |
| `auditor` / `order-auditors` | Không | Không | Không | Có |
| `admin` / `broker-admins` | Có | Có | Có theo chính sách | Có |

Lưu ý quyền gửi/nhận còn phụ thuộc vào việc **queue vật lý đã có và định tuyến đúng**. Nếu người dùng thuộc nhiều role thì quyền hiệu lực có thể là tổng các quyền được cấp theo broker. Bảng giả định mỗi tài khoản chỉ thuộc role được nêu.

## 7. Ví dụ Spring Boot 3.5.x chạy với broker có ACL

Ví dụ dùng **Java 17+**, **Spring Boot 3.5.7**, kết nối **Artemis broker độc lập** trên `localhost:61616`. Dùng hai profile để chạy cùng mã nguồn dưới hai danh tính khác nhau:

- Profile `producer`: Spring `JmsTemplate` gửi `ORDER-101`.
- Profile `consumer`: Spring `@JmsListener` nhận `ORDER-101`.

**Yêu cầu chuẩn bị:** broker đã chạy, queue `orders.commands` đã được provision như mục 6, và có hai tài khoản `sender`/ `worker` với role tương ứng. Mật khẩu được cấp tại broker; không lưu mật khẩu thật vào repository. Đặt biến môi trường `SPRING_ARTEMIS_USER` và `SPRING_ARTEMIS_PASSWORD` trước khi khởi động mỗi process.

Cấu trúc:

~~~text
jms-acl-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jmsacl/
    │   ├── JmsAclApplication.java
    │   ├── ProducerConfiguration.java
    │   └── OrderReceiver.java
    └── resources/
        └── application.properties
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>jms-acl-demo</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
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
~~~

Không thêm embedded Artemis dependency: ví dụ này phải kết nối broker độc lập **đang bật ACL** để nhìn thấy sự khác nhau giữa role gửi và role nhận. Nếu thay bằng embedded broker cấu hình security khác, kết quả có thể không tương đương.

### 7.2. application.properties

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.jms.pub-sub-domain=false
spring.main.banner-mode=off
~~~

Spring Boot tự đọc `SPRING_ARTEMIS_USER` và `SPRING_ARTEMIS_PASSWORD` từ environment để bind tới `spring.artemis.user`/`spring.artemis.password`. Từng process phải cung cấp tài khoản tương ứng.

`spring.jms.pub-sub-domain=false` cấu hình gửi/nhận Queue; không có nghĩa queue được tạo tự động hay quyền broker được bỏ qua.

### 7.3. JmsAclApplication.java

~~~java
package com.example.jmsacl;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class JmsAclApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsAclApplication.class, args);
    }
}
~~~

### 7.4. ProducerConfiguration.java

~~~java
package com.example.jmsacl;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.jms.core.JmsTemplate;

@Configuration
@Profile("producer")
public class ProducerConfiguration {

    @Bean
    ApplicationRunner sendOrder(JmsTemplate jmsTemplate) {
        return args -> {
            jmsTemplate.convertAndSend("orders.commands", "ORDER-101");
            System.out.println("SENT ORDER-101");
        };
    }
}
~~~

Với profile `producer`, `JmsTemplate` resolve tên destination và gọi API gửi dưới credentials của process. `SENT ORDER-101` chỉ được in sau lời gọi `convertAndSend` trả thành công; không có nghĩa consumer đã xử lý xong.

### 7.5. OrderReceiver.java

~~~java
package com.example.jmsacl;

import org.springframework.context.annotation.Profile;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
@Profile("consumer")
public class OrderReceiver {

    @JmsListener(destination = "orders.commands")
    public void receive(String body) {
        System.out.println("RECEIVED " + body);
    }
}
~~~

Với profile `consumer`, Spring tạo listener container, dùng tài khoản đã cấu hình để kết nối và **consume** từ Queue. Nếu thiếu quyền, container có thể log lỗi, thử khởi động lại/reconnect; không cam kết lỗi luôn làm process dừng ngay.

### 7.6. Khởi động và xem kết quả

Trong **terminal A**, đặt environment `SPRING_ARTEMIS_USER=worker` và mật khẩu của tài khoản worker (qua cơ chế quản lý bí mật của môi trường), sau đó:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=consumer
~~~

Trong **terminal B**, đặt environment `SPRING_ARTEMIS_USER=sender` và mật khẩu tài khoản sender, rồi:

~~~bash
mvn spring-boot:run -Dspring-boot.run.profiles=producer
~~~

Khi broker, queue, role và credentials đều đúng, các dòng ứng dụng kỳ vọng (ngoài log Spring/Artemis) là:

~~~text
SENT ORDER-101
RECEIVED ORDER-101
~~~

Đây là **hai dòng đến từ hai process**; không phải stdout gộp cố định. Dòng `SENT` không xác nhận `RECEIVED` đã xuất hiện: gửi và nhận có thể cách nhau một khoảng thời gian. Nếu chạy sender khi consumer tắt, message có thể còn trên queue chờ worker, phụ thuộc delivery mode, persistence, TTL, broker policy và transaction.

Để tự xem role thực tế, dùng công cụ quản trị broker được tổ chức cho phép; **không cấp quyền admin vào application chỉ để kiểm tra**.

## 8. Kiểm chứng riêng từng quyền

Đừng kiểm chứng ACL bằng đúng một luồng “gửi rồi nhận thành công”. Nó chỉ chứng minh **cả hai process kết hợp** có khả năng truyền một message, chưa chứng minh service không có quyền thừa.

Bộ kiểm tra theo nguyên tắc **positive + negative**:

| Trường hợp | Danh tính sử dụng | Hành động | Kỳ vọng |
| --- | --- | --- | --- |
| 1 | `sender` | `convertAndSend` vào `orders.commands` | Thành công khi queue tồn tại và broker khỏe. |
| 2 | `worker` | `@JmsListener` trên `orders.commands` | Nhận được message hợp lệ. |
| 3 | `sender` | Khởi động consumer trên cùng queue | Bị từ chối `consume`, không được giao message. |
| 4 | `worker` | Thử `convertAndSend` | Bị từ chối `send`. |
| 5 | `sender` hoặc `worker` | Dùng broker management API tạo/xóa queue | Không có quyền quản trị tạo/xóa; chính sách quản trị cần kiểm tra độc lập. |
| 6 | `auditor` | Browse qua `QueueBrowser` | Đọc không tiêu thụ nếu có `browse`, không có quyền `consume`. |

Các test âm tính phải chạy trong **môi trường thử nghiệm** hoặc với message/tài nguyên được phép dùng, để không ảnh hưởng queue đang xử lý nghiệp vụ thật. Tránh xóa queue chỉ để chứng minh đã hạn chế quyền xóa; dùng quyền API hoặc tài nguyên thử nghiệm có vòng đời riêng.

Ví dụ fragment tự tạo consumer dưới danh tính chỉ có quyền send:

~~~java
// Fragment: factory là ConnectionFactory đã xác thực là "sender".
// Queue đã tồn tại, nhưng sender không được cấp consume.
try (jakarta.jms.JMSContext context = factory.createContext()) {
    jakarta.jms.Queue queue = context.createQueue("orders.commands");
    try (jakarta.jms.JMSConsumer ignored =
                 context.createConsumer(queue)) {
        // Nếu broker cho phép, kiểm tra lại security config.
    }
}
~~~

Điểm thất bại có thể nằm ở `createConsumer`, lúc broker bắt đầu delivery hoặc trong listener container. Loại exception và message cụ thể phụ thuộc provider, phiên bản, đường gọi và security manager. Có thể gặp `JMSSecurityException`, exception JMS tương đương hoặc lỗi provider được Spring chuyển thành `JmsException`; hãy xem **cause chain** và log từ broker, không dựa vào một chuỗi thông báo lỗi cố định.

## 9. Auto-create: tác dụng phụ khiến bạn hiểu nhầm

Artemis hỗ trợ cấu hình:

- `auto-create-addresses`
- `auto-create-queues`
- `auto-delete-addresses`
- `auto-delete-queues`

Khi tự tạo bật, tùy protocol và chính sách provider, **lần gửi tới address chưa tồn tại hoặc consumer mở queue chưa có** có thể khiến broker tự tạo tài nguyên. Một số plugin/compatibility mode có thể xử lý quyền auto-create khác cơ chế cấp quyền quản trị trực tiếp; vì vậy phải xác minh trên phiên bản và security manager cụ thể.

### 9.1. Tình huống dễ gây hiểu lầm

Ứng dụng gọi:

~~~java
jmsTemplate.convertAndSend("orders.commmands", "ORDER-101");
~~~

Tên có **ba chữ m** là lỗi gõ so với `orders.commands`. Nếu broker cho phép tự tạo, địa chỉ sai có thể được tạo ra hoặc message được định tuyến sang nơi không có worker, khiến hệ thống âm thầm có backlog lạ. Nếu auto-create tắt và cấu hình broker kiểm tra destination tồn tại, lỗi thường được bộc lộ sớm hơn.

**Không lấy việc message send trả về thành công làm chứng cứ đích đã được consumer đúng nhận.** Cần quan sát queue depth, số consumer, routing và acknowledgment/transaction. Kể cả gửi thành công tới một address tồn tại, message có thể không được route tới queue bạn kỳ vọng nếu quy tắc routing không đúng.

### 9.2. Phân biệt “được phép auto-create” và “được phép quản trị”

Một broker có thể áp dụng những hành vi khác nhau:

1. Yêu cầu `createAddress`/`createDurableQueue` để auto-create tài nguyên cho client.
2. Có chính sách cấp phép tự tạo phụ thuộc role `send`/compatibility.
3. Tạo sẵn một số tài nguyên phụ trợ cho Topic/subscription theo giao thức.
4. Tắt auto-create toàn bộ namespace để bắt buộc pre-provisioning.

Do đó cách phát biểu an toàn là: **quyền tạo destination và quyền gửi/nhận là các hành động khái niệm khác nhau; chính sách và tác dụng phụ thực tế do broker quyết định**. Tránh khẳng định `send` luôn tạo được hoặc tuyệt đối không thể tạo được tài nguyên trên mọi broker.

## 10. Topic subscription, TemporaryQueue và request/reply

### 10.1. Topic thường cần tài nguyên subscription riêng

Với JMS Topic, một `@JmsListener` không chỉ cần quyền đọc address `events`; broker có thể tạo một **queue đại diện cho subscription**, nhất là với durable subscription. Vì vậy, consumer của Topic có thể cần quyền tạo non-durable/durable subscription queue trong một số triển khai, dù mã nguồn không có lệnh `createQueue`.

Ví dụ minh họa (fragment cấu hình listener, **không phải ứng dụng độc lập**):

~~~java
@JmsListener(
        destination = "domain.events",
        subscription = "billing",
        containerFactory = "topicListenerFactory")
public void onEvent(String event) {
    // Xử lý business event; factory cấu hình pubSubDomain=true.
}
~~~

`topicListenerFactory` là bean cần do ứng dụng định nghĩa; khi dùng durable subscription còn phải cấu hình `subscriptionDurable`, client ID và các yêu cầu JMS tương ứng. **Không mặc định cấp quyền tạo mọi queue cho mọi worker** chỉ vì một ứng dụng Topic cần tạo subscription; hãy giới hạn address, loại queue và vòng đời cần thiết.

### 10.2. Temporary destination là ngoại lệ rõ ràng

`Session.createTemporaryQueue()` và `JMSContext.createTemporaryQueue()` **thực sự yêu cầu tạo temporary destination**, thường dùng làm `JMSReplyTo` cho request/reply. Việc tạo và xóa tài nguyên tạm có thể cần `createAddress`, `createNonDurableQueue` hoặc quyền tương ứng của provider.

Temporary Queue thường chỉ cho phép **connection tạo ra nó** được tạo consumer, dù các connection khác có thể gửi reply theo quy tắc của provider. Thiết kế quyền phải tính tới tên temporary address, policy auto-delete và quyền gửi reply; **không cấp `create*` trên toàn bộ namespace nghiệp vụ** chỉ để request/reply hoạt động.

### 10.3. Browse không phải consume

`QueueBrowser` (JMS) cho phép xem message trong queue mà **không lấy chúng khỏi queue**. Tuy nhiên, một snapshot browse không bảo đảm ổn định nếu producer/consumer đồng thời hoạt động, và việc thấy message body có thể tiết lộ thông tin nhạy cảm. Vì vậy role `order-auditors` cần kiểm soát như một quyền đọc dữ liệu, không phải mặc nhiên an toàn chỉ vì không xóa message.

## 11. Vì sao Spring JMS không “cấp quyền hộ”?

Spring xử lý lifecycle và chuyển đổi API, nhưng không thay thế authorization của broker:

- `JmsTemplate` dùng `DestinationResolver`. Mặc định `DynamicDestinationResolver` resolve tên thành đối tượng Queue/Topic JMS; điều này **không cấp quyền tạo destination vật lý**.
- `JndiDestinationResolver` lookup administered destination nếu hệ thống cấu hình JNDI; lookup không phải chứng thực quyền send/consume.
- `@JmsListener(destination="orders.commands")` đăng ký listener dưới credentials của `ConnectionFactory`; broker vẫn có thể từ chối.
- `@EnableJms` kích hoạt hạ tầng listener; nó **không tự tạo tài khoản broker hoặc bỏ qua ACL**.
- `spring.jms.pub-sub-domain=true/false` chọn cách hiểu Topic/Queue mặc định; nó **không mở quyền**.

Vì vậy nếu Spring application khởi động bình thường nhưng listener báo authorization failure, hãy tìm **broker user/role, destination, match security, auto-create, subscription queue**, thay vì tự động thêm một bean `Queue` hoặc bật quyền admin cho service.

**Không nhầm với Spring Security.** Spring Security kiểm soát HTTP/method authorization của ứng dụng; broker ACL kiểm soát kết nối JMS và thao tác message tại broker. Một endpoint HTTP được phép gọi không có nghĩa credentials JMS của ứng dụng có `send`.

## 12. Chẩn đoán lỗi cụ thể

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| `createQueue("name")` trả object nhưng `send` lỗi | Chưa có queue thực, sai address, thiếu `send`, broker không cho auto-create | Kiểm tra broker `addresses/queues`, username, role và log security. |
| Producer gửi được nhưng listener không nhận | Consumer thiếu `consume`, selector sai, không có queue binding, listener không chạy | Kiểm tra role consumer, queue depth, consumer count, destination name. |
| Listener báo lỗi tạo subscription | Topic subscription cần queue phụ trợ, thiếu `createDurableQueue`/`createNonDurableQueue` theo provider | Kiểm tra durable/shared settings, client ID, subscription name và ACL địa chỉ Topic. |
| Queue tự xuất hiện khi app chạy | `auto-create-queues`/`auto-create-addresses` bật hoặc provider provision tự động | Kiểm tra address settings, security manager, protocol và audit event. |
| Sender có `send` nhưng không tạo được queue mới bằng console | `send` khác `create*` hoặc `manage` | Xem security setting match thực tế và role mapping. |
| Consumer nhận được nhưng không browse được | `consume` và `browse` là quyền riêng | Test `QueueBrowser` với tài khoản dành cho kiểm thử. |
| Đã cấp role mà vẫn thiếu quyền | Security match cụ thể hơn override match rộng, role chưa đồng bộ, cache authorization, credentials sai | Đọc effective security settings và log broker. |
| Thêm quyền `createDurableQueue` vẫn không tạo được | Còn thiếu `createAddress`, thuộc namespace khác hoặc management API cần quyền riêng | Kiểm tra resource type, address và đường gọi API. |
| App dùng admin thì chạy, dùng service user thì lỗi | Service user thiếu ACL hoặc auto-create chỉ được bật cho admin | Provision trước, cấp quyền tối thiểu, không dùng admin làm cách sửa cố định. |

Quy trình chẩn đoán nên theo thứ tự:

1. **Authentication:** username/password/client certificate đúng? Kết nối có thành công?
2. **Destination:** loại Queue hay Topic, tên address/queue, routing type và sự tồn tại vật lý?
3. **ACL hiệu lực:** tài khoản thuộc role nào, security-setting nào **cụ thể nhất** đang match?
4. **Operation:** lỗi phát sinh ở `send`, `consume`, `browse`, tự tạo queue hay management?
5. **Provider behavior:** auto-create, subscription queue, FQQN và security plugins có làm phát sinh quyền bổ sung?
6. **Observability:** xem server log, application exception cause chain, queue depth và số consumer.

Tránh “sửa” lỗi bằng cách tắt `security-enabled` hay cấp mọi quyền trên `#` trong môi trường thật. Việc này che mất cấu hình sai và làm tăng phạm vi truy cập ngoài ý muốn.

## 13. Nguyên tắc triển khai an toàn và dễ vận hành

**Provision destination trước khi triển khai service:** dùng cấu hình broker, hạ tầng-as-code hoặc bước provisioning do đội vận hành kiểm soát. Cấu hình gồm tên address/queue, routing type, persistence, TTL, DLQ, size limit, retry policy và permission.

**Tách danh tính theo service và môi trường:** `order-sender` có `send` tới `orders.commands`; `order-worker` có `consume` từ queue này. Tài khoản staging không nên dùng chung secrets với production.

**Giới hạn phạm vi namespace:** `orders.#` hẹp hơn `#`. Tuy nhiên wildcard không tự bảo vệ đủ khi bạn tạo một rule cụ thể hơn; các rule cụ thể có thể thay thế quyền của rule rộng. Đánh giá cả security-setting và address-setting.

**Xem `browse` là quyền đọc dữ liệu:** message payload có thể chứa ID khách hàng, email, thông tin đơn. Cần quản lý role quan sát, thời gian lưu và audit.

**Giám sát các thao tác tạo/xóa:** bật log/audit phù hợp cho provisioning, kiểm tra queue không mong muốn, cảnh báo khi destination hoặc subscription queue mới xuất hiện bất thường.

**Thiết kế riêng các ngoại lệ hợp lệ:** request/reply cần temporary destinations; Topic cần subscription queues; các đặc quyền này nên giới hạn theo namespace và chính sách riêng, thay vì nâng cả ứng dụng lên broker admin.

**Kiểm thử ACL tự động ở môi trường phù hợp:** kết hợp thử nghiệm thành công và từ chối. Việc `sender` gửi thành công **chưa chứng minh** rằng nó không thể consume hoặc tạo queue; phải có ít nhất một kiểm chứng âm tính có kiểm soát.

## 14. Câu hỏi tự kiểm tra

1. **`session.createQueue("orders.commands")` có thật sự tạo queue vật lý?** Không. Nó tạo đối tượng tham chiếu tên; việc tạo tài nguyên thật thuộc provider/administration.
2. **Producer cần quyền `createDurableQueue` để gửi vào queue đã có không?** Về khái niệm không; cần `send` và điều kiện broker tương ứng. Các policy tự tạo/ACL khác có thể thêm yêu cầu trong từng triển khai.
3. **Worker chỉ cần xử lý message thì nên được cấp quyền gì?** `consume` trên queue cần dùng; không mặc định cấp send, browse, create hoặc delete.
4. **Vì sao sender không nên được cấp quyền `browse`?** Browse cho phép xem payload của message tồn đọng, là một quyền đọc dữ liệu riêng.
5. **Nếu bật auto-create thì tên queue viết sai có tác hại gì?** Broker có thể tạo queue lạ hoặc nhận message không có consumer phù hợp; cần theo dõi và cân nhắc tắt auto-create.
6. **`JndiDestinationResolver` có cho phép tạo queue thật hoặc cấp quyền send không?** Không. Nó resolve đối tượng từ JNDI; broker vẫn quyết định các thao tác.
7. **Vì sao một Topic subscriber có thể cần quyền tạo queue?** Broker có thể tạo queue làm subscription; quyền phụ thuộc durable/non-durable và cấu hình.
8. **`createTemporaryQueue()` có cùng ý nghĩa với `createQueue("x")` không?** Không. TemporaryQueue là tài nguyên tạm thật gắn với connection.
9. **Đã có role `send` nhưng management API từ chối tạo queue, có mâu thuẫn không?** Không. Tạo/quản lý là quyền khác gửi.
10. **Vì sao cần xét security-setting cụ thể nhất?** Artemis không tự kế thừa quyền từ rule rộng hơn khi có một rule cụ thể hơn match; effective ACL có thể khác kỳ vọng.

## 15. Tài liệu tham khảo

- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html), các phần **Destination**, **Queue management**, **temporary destinations**, **administered objects**.
- [Jakarta Messaging — Session API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/session), `createQueue`, `createTopic` và `createTemporaryQueue`.
- [Spring Framework — Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html), `JmsTemplate`, `DynamicDestinationResolver`, `JndiDestinationResolver`.
- [Spring Boot — JMS / Artemis](https://docs.spring.io/spring-boot/3.5/reference/messaging/jms.html), cấu hình broker native và tự động cấu hình connection.
- [Apache ActiveMQ Artemis — Authentication & Authorization](https://artemis.apache.org/components/artemis/documentation/latest/security.html), vai trò `create*`, `send`, `consume`, `browse`, `manage` và precedence của security settings.
- [Apache ActiveMQ Artemis — Address Model](https://artemis.apache.org/components/artemis/documentation/latest/address-model.html), address, queue, anycast/multicast và provisioning.
- [Apache ActiveMQ Artemis — Address Settings](https://artemis.apache.org/components/artemis/documentation/latest/address-settings.html), `auto-create-addresses`/`auto-create-queues` và chính sách auto-delete.

**Điểm cần ghi nhớ:** việc ứng dụng biết tên destination hoặc gọi `createQueue(String)` **không phải quyền tạo tài nguyên thật trên broker**. Quyền `send`, `consume`, `browse` và `create/delete/manage` có mục đích khác nhau. Spring JMS giúp gọi API thuận tiện, còn broker kiểm tra authorization; muốn tách quyền chắc chắn hãy provision trước, kiểm soát auto-create và kiểm thử ACL theo từng role.
