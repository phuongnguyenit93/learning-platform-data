# DestinationResolver và quá trình phân giải tên trong Spring JMS

## 1. Vấn đề mà DestinationResolver giải quyết

Khi một ứng dụng Spring gửi message bằng lời gọi:

~~~java
jmsTemplate.convertAndSend("orders.requests", "ORDER-42");
~~~

"orders.requests" là **String do ứng dụng cung cấp**, trong khi JMS API thực sự cần một đối tượng jakarta.jms.Destination, thường là jakarta.jms.Queue hoặc jakarta.jms.Topic. Spring phải có một cách chuyển tên dạng chuỗi sang đúng Destination mà JMS provider hiểu.

Lớp trừu tượng làm việc này là **org.springframework.jms.support.destination.DestinationResolver**. Một DestinationResolver nhận tên, JMS Session và thông tin đó là queue hay topic, rồi trả về Destination. Nó cho phép code nghiệp vụ gọi tên ổn định mà không phải tự viết JNDI lookup hay Session.createQueue() trong mỗi nơi gửi/nhận.

Có ba cách phân giải phổ biến:

- **DynamicDestinationResolver**: dùng chính JMS Session hiện tại để tạo đối tượng Queue/Topic theo tên; đây là mặc định của JmsTemplate trong Spring Framework 6.x.
- **JndiDestinationResolver**: tra cứu một JMS Destination đã được cấu hình/bind trong JNDI; có cache và có thể bật fallback sang dynamic khi lookup thất bại.
- **BeanFactoryDestinationResolver**: tra cứu một Spring bean có tên tương ứng và kiểu jakarta.jms.Destination.

Bài học phân biệt **phân giải tên** (name resolution), **cấp phát/tạo vật lý** destination trên broker (broker provisioning) và **message delivery**. Chúng có liên quan nhưng không phải cùng một thao tác.

## 2. Destination trong JMS là gì?

JMS Destination là đích gửi hoặc nguồn nhận message. Hai kiểu thường gặp:

| JMS type | Ý nghĩa | Đặc điểm cơ bản |
| --- | --- | --- |
| jakarta.jms.Queue | Kênh point-to-point | Các consumer cạnh tranh trên cùng queue chia nhau message; một message được tiêu thụ theo semantics queue. |
| jakarta.jms.Topic | Kênh publish/subscribe | Mỗi subscription phù hợp có thể nhận bản giao của cùng một message theo chính sách subscription. |

Destination không phải message body, không phải MessageConverter và không phải địa chỉ URL HTTP. Một queue/topic có thể có tên logic, tên vật lý, địa chỉ broker và quy tắc cấp quyền khác nhau tùy provider.

Sơ đồ tổng quát:

~~~mermaid
flowchart LR
    A["Ứng dụng: destinationName = orders.requests"] --> B["Spring JMS"]
    B --> C["DestinationResolver"]
    C --> D{"Chiến lược"}
    D --> E["Session.createQueue / createTopic"]
    D --> F["JNDI lookup"]
    D --> G["Spring BeanFactory lookup"]
    E --> H["jakarta.jms.Destination"]
    F --> H
    G --> H
    H --> I["JMS producer hoặc consumer"]
    I --> J["Message broker"]
~~~

**Điểm cốt lõi:** resolver trả về một đối tượng Destination để dùng với API JMS. Nó **không** chứng minh queue đã được khai báo, đã có quyền truy cập, có người tiêu thụ hay sẽ giữ message bền vững.

Ví dụ: broker có thể cho phép ứng dụng nhắc đến tên "orders.requests" nhưng từ chối gửi vì thiếu quyền; broker cũng có thể chỉ cho dùng những queue đã được quản trị viên tạo trước. Hai trường hợp đều nằm ngoài logic cơ bản của việc biến String thành Destination.

## 3. Hợp đồng của DestinationResolver

Trong Spring Framework 6.x, interface có chữ ký:

~~~java
package org.springframework.jms.support.destination;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;

@FunctionalInterface
public interface DestinationResolver {
    Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException;
}
~~~

Đây là **chữ ký minh họa** của interface, không phải file cần chép vào dự án. Ứng dụng dùng interface đã có trong spring-jms; không tự định nghĩa một interface trùng package.

Giải thích từng tham số:

| Tham số | Ý nghĩa |
| --- | --- |
| session | JMS Session hiện hành. Dynamic resolver cần session để gọi createQueue/createTopic; resolver tra cứu tài nguyên đã đăng ký có thể không cần sử dụng nó. |
| destinationName | Tên mà code cung cấp: ví dụ "orders.requests" hoặc "java:/jms/queue/Orders". Ngữ nghĩa tên phụ thuộc chiến lược. |
| pubSubDomain | true: yêu cầu hướng publish/subscribe (Topic); false: point-to-point (Queue). Đặc biệt quan trọng khi phân giải động. |
| Giá trị trả về | jakarta.jms.Destination phù hợp, thường là Queue hoặc Topic. |
| Lỗi | JMSException khi JMS API/provider gặp lỗi; DestinationResolutionException của Spring khi không thể phân giải tên theo chiến lược. |

Tên method là **resolveDestinationName**, không phải createDestination; chữ "resolve" có nghĩa tìm một representation phù hợp. Với JNDI, kết quả có thể là đối tượng Queue/Topic được cấu hình sẵn; với dynamic, thường có được từ Session.createQueue()/createTopic().

Một số phương thức JmsTemplate nhận **Destination object trực tiếp**, ví dụ convertAndSend(Destination, Object). Trong trường hợp đó đã có đối tượng đích, không cần đưa String qua DestinationResolver nữa.

### 3.1. Hợp đồng có thể được cài bằng lambda

Vì interface chỉ có một phương thức trừu tượng, có thể cài bằng lambda:

~~~java
DestinationResolver resolver = (session, name, pubSubDomain) -> {
    return pubSubDomain
            ? session.createTopic(name)
            : session.createQueue(name);
};
~~~

Đây là snippet Java nằm trong nơi đã import DestinationResolver và có JMS provider. Lambda trên tương đương tư tưởng dynamic resolver cơ bản, chưa có quy tắc tên, logging, security hay provisioning.

### 3.2. Tách tên logic và tên vật lý

Trong hệ thống lớn, code nghiệp vụ có thể cần gọi tên ổn định như "orders.incoming", nhưng broker sử dụng địa chỉ "corp.sales.orders.v2". Resolver tùy chỉnh có thể ánh xạ giữa hai tên:

~~~text
logical name:  orders.incoming
                      |
                      v
DestinationResolver: "corp.sales.orders.v2"
                      |
                      v
JMS Queue/Topic object gửi vào broker
~~~

Đây là chính sách do ứng dụng thiết kế, **không phải một ánh xạ tự động có sẵn** cho mọi resolver.

## 4. Toàn bộ hành trình phân giải khi gửi

Xét trường hợp gửi tên dạng String:

~~~java
jmsTemplate.convertAndSend("orders.incoming", "ORDER-42");
~~~

Các bước khái niệm trong JmsTemplate:

1. Chọn ConnectionFactory, tạo/lấy một Connection và Session phù hợp với cấu hình Spring, transaction và cơ chế cache/pooling đang dùng.
2. Nhận String "orders.incoming" làm destinationName.
3. Gọi DestinationResolver.resolveDestinationName(session, "orders.incoming", pubSubDomain).
4. Nhận đối tượng jakarta.jms.Destination, chẳng hạn Queue.
5. Dùng MessageConverter chuyển String "ORDER-42" thành một JMS Message, mặc định thường là TextMessage.
6. Dùng JMS MessageProducer gửi tới Destination, áp dụng transaction, quality-of-service và lỗi provider nếu có.
7. Giải phóng hoặc trả tài nguyên về pool theo cơ chế Spring/provider.

~~~mermaid
sequenceDiagram
    autonumber
    participant App as Application
    participant T as JmsTemplate
    participant R as DestinationResolver
    participant S as JMS Session
    participant B as Broker
    App->>T: convertAndSend("orders.incoming", payload)
    T->>R: resolveDestinationName(session, name, pubSubDomain)
    alt Dynamic
        R->>S: createQueue/createTopic(name)
        S-->>R: Destination
    else JNDI / Spring bean
        R->>R: lookup(name)
    end
    R-->>T: Destination
    T->>T: convert payload to JMS Message
    T->>B: send(message, Destination)
    B-->>T: result / exception
    T-->>App: complete / exception
~~~

Đây là sơ đồ logic; ConnectionFactory, transaction manager, caching và provider có thể thay đổi các bước quản lý tài nguyên cụ thể. **DestinationResolver không chịu trách nhiệm chuyển đổi payload**: MessageConverter đảm nhận việc đó.

### 4.1. Vai trò của default destination

JmsTemplate có thể được cấu hình tên đích mặc định:

~~~java
jmsTemplate.setDefaultDestinationName("orders.incoming");
jmsTemplate.convertAndSend("ORDER-42"); // Không truyền tên đích tại call site.
~~~

Khi sử dụng defaultDestinationName, tên vẫn cần được phân giải thành Destination. Ngược lại, nếu cấu hình defaultDestination bằng **Destination object**, phần tra cứu theo tên không cần thực hiện cho object đó.

Đừng nhầm lời gọi convertAndSend(Object) với convertAndSend(String destinationName, Object). Cách quá tải method quyết định việc String là **payload** hay **tên đích**.

## 5. DynamicDestinationResolver: mặc định và dễ bắt đầu

DynamicDestinationResolver nằm trong package:

~~~java
org.springframework.jms.support.destination.DynamicDestinationResolver
~~~

Resolver này dựa trên JMS Session hiện tại:

~~~java
// Ý tưởng nội bộ ở mức khái niệm:
Destination destination = pubSubDomain
        ? session.createTopic(destinationName)
        : session.createQueue(destinationName);
~~~

Đây là snippet mô tả cơ chế, không phải mã nguồn nội bộ chép nguyên văn. Khi pubSubDomain=false, tên "orders.incoming" dẫn tới Queue; khi pubSubDomain=true, cùng chuỗi có thể dẫn tới Topic, tức **hai kiểu đích khác nhau**.

### 5.1. "Dynamic" có phải tự tạo queue vật lý?

**Không có bảo đảm chung như vậy.** Theo JMS API, Session.createQueue(String) / createTopic(String) tạo representation của destination; ý nghĩa provisioning thực tế phụ thuộc JMS provider. Một số broker hỗ trợ auto-create khi truy cập, một số chỉ tham chiếu tới destination đã được cấu hình, một số yêu cầu khai báo/ACL trước.

Vì vậy:

- Nếu broker cho phép auto-create, lúc gửi/nhận có thể xuất hiện destination vật lý tương ứng.
- Nếu broker tắt auto-create hoặc cấm quyền, resolution có thể có object hợp lệ nhưng send/receive vẫn thất bại.
- Cấu hình queue bền vững, routing type, DLQ, giới hạn dung lượng, TTL, permission và retention vẫn là trách nhiệm của broker/đội vận hành.
- **Dynamic destination khác TemporaryQueue/TemporaryTopic**. Temporary destination do JMS API tạo để dùng tạm theo vòng đời Connection; tên dynamic do ứng dụng cung cấp thường có vòng đời khác.

Tên lớp DynamicDestinationResolver nói đến chiến lược resolution, không phải lệnh buộc broker "tạo mới bằng mọi giá".

### 5.2. Ưu điểm và giới hạn

Ưu điểm: ít cấu hình, thuận tiện cho demo và môi trường nơi broker cho phép dùng destination theo naming convention. Hạn chế: tên String có thể lệch cấu hình broker, cấu hình security hoặc routing; nếu thiếu quản trị naming, các lỗi đánh máy có thể dẫn tới queue khác hoặc message bị tồn đọng.

Không nên giả định "JmsTemplate gửi không lỗi" nghĩa là tên destination đã đúng về nghiệp vụ: một queue vô tình được tạo vẫn có thể không có consumer.

## 6. JndiDestinationResolver: tra cứu đích được đăng ký

Một môi trường enterprise có thể khai báo sẵn Destination qua **JNDI** (Java Naming and Directory Interface), rồi binding với tên như "java:/jms/queue/Orders". JndiDestinationResolver diễn giải destinationName như một tên JNDI để tra cứu Queue/Topic đã được quản lý.

Ví dụ cấu hình Spring:

~~~java
import org.springframework.jms.support.destination.JndiDestinationResolver;

JndiDestinationResolver resolver = new JndiDestinationResolver();
resolver.setCache(true);
resolver.setFallbackToDynamicDestination(false);

jmsTemplate.setDestinationResolver(resolver);
jmsTemplate.setPubSubDomain(false);

// Tên dưới đây phải tồn tại trong JNDI environment thực tế:
jmsTemplate.convertAndSend("java:/jms/queue/Orders", "ORDER-42");
~~~

Đây là **snippet cấu hình**, không phải project chạy độc lập: jmsTemplate, JNDI provider, JNDI environment và binding phải có thật. JndiDestinationResolver kế thừa hỗ trợ cấu hình JNDI environment; cú pháp URL, JNDI InitialContext và namespace **phụ thuộc server/provider**.

**JNDI lookup không tự tạo destination trong broker.** Nó lấy đối tượng đích đã được bind theo cấu hình môi trường. Nếu application server trả về destination không tương thích với ConnectionFactory đang dùng, việc send/receive vẫn có thể lỗi.

### 6.1. Cache và invalidation

JndiDestinationResolver có các thiết lập quan trọng:

| Thuộc tính | Giá trị mặc định | Ý nghĩa |
| --- | --- | --- |
| cache | true | Cache destination đã phân giải theo tên để tránh lookup lại mỗi lần. |
| fallbackToDynamicDestination | false | Nếu JNDI lookup thất bại, mặc định **không** tự chuyển sang dynamic resolution. |
| dynamicDestinationResolver | DynamicDestinationResolver của Spring | Chiến lược dùng khi đã chủ động bật fallback. |

Có thể điều khiển cache qua setCache(boolean) và các phương thức của CachingDestinationResolver như clearCache() / removeFromCache(name).

Một điểm dễ bỏ sót: cache dùng **destination name** làm khóa. Nếu trộn Queue và Topic dùng cùng một tên trong JNDI/dynamic fallback, có thể bị nhầm representation đã cache. Vì thế nên dùng **tên phân biệt cho queue và topic**, ví dụ "queue.orders" và "topic.orders", ngay cả khi broker hỗ trợ những tên vật lý giống nhau.

Cache có ích vì giảm lookup, nhưng có thể giữ handle cũ khi đội vận hành rebind JNDI hoặc restart một destination. Nếu cần hot replacement, cân nhắc invalidation hoặc tắt cache trong tình huống phù hợp, rồi thử nghiệm lại với provider.

### 6.2. Fallback không phải mặc định

~~~java
resolver.setFallbackToDynamicDestination(true);
~~~

Khi bật, nếu tên **không tìm thấy qua JNDI** và tình huống lỗi phù hợp để fallback, resolver dùng dynamic resolver để thử tạo representation theo JMS Session. Điều này thuận tiện trong một số môi trường phát triển nhưng **có rủi ro tạo/đọc sai queue** trong production: một binding viết sai có thể âm thầm trở thành dynamic destination khác.

Nếu tổ chức yêu cầu mọi queue/topic được khai báo và review trước, giữ fallback=false để thiếu binding được phát hiện sớm.

### 6.3. JNDI name có nhất thiết bằng broker physical name?

Không. Ví dụ:

~~~text
Tên code dùng:             java:/jms/queue/Orders
Binding trong JNDI:        jakarta.jms.Queue của provider
Tên vật lý phía broker:    corp.sales.orders.v2
~~~

Đây là một mapping hợp lệ nếu server/JNDI admin cấu hình như vậy. Chính sự tách biệt này giúp đổi physical destination mà ít sửa code, đổi lại cần kiểm soát cấu hình JNDI và cache chặt chẽ.

## 7. BeanFactoryDestinationResolver: phân giải qua Spring bean

BeanFactoryDestinationResolver tra cứu một bean trong Spring ApplicationContext/BeanFactory theo tên, yêu cầu bean có kiểu jakarta.jms.Destination.

~~~text
Application code: "ordersQueue"
         |
         v
Spring BeanFactory: bean name = ordersQueue
         |
         v
Object: jakarta.jms.Queue của JMS provider
~~~

Ví dụ resolver được tạo bởi Spring:

~~~java
@Bean
DestinationResolver destinationResolver(BeanFactory beanFactory) {
    return new BeanFactoryDestinationResolver(beanFactory);
}
~~~

Đây là snippet trong lớp @Configuration với các import Spring tương ứng. **Phải có bean tên ordersQueue thực sự trả về Destination**; resolver này không tự tạo object Queue nếu bean chưa tồn tại.

Bean có thể được cấp từ JNDI lookup, cấu hình JMS provider hoặc factory method riêng. BeanFactoryDestinationResolver có constructor nhận BeanFactory để sử dụng ngoài việc để container inject BeanFactoryAware.

Ưu điểm: mapping tên String sang các Destination bean được cấu hình thống nhất tại Spring IoC; phù hợp khi ứng dụng đã quản lý các destination objects như bean. Nhược điểm: phụ thuộc tên bean, cách tạo Destination và lifecycle của bean; không tự giải quyết quyền broker hay việc tạo queue vật lý.

## 8. So sánh ba chiến lược

| Tiêu chí | DynamicDestinationResolver | JndiDestinationResolver | BeanFactoryDestinationResolver |
| --- | --- | --- | --- |
| Tên String được hiểu là | Tên queue/topic cho JMS Session | Địa chỉ binding JNDI | Tên Spring bean |
| Nguồn đối tượng Destination | Session.createQueue/createTopic | JNDI lookup | BeanFactory lookup |
| Cần JMS Session để phân giải? | Có | Có thể không cần để lookup | Thường không cần |
| Có cache tích hợp ở resolver? | Không dùng JNDI cache như Jndi | Có, mặc định bật | Theo BeanFactory và vòng đời bean |
| Cần khai báo sẵn tên? | Tùy broker và policy | Có JNDI binding, trừ khi bật fallback | Có bean Destination |
| Cách báo lỗi phổ biến | JMSException/provider error | Missing binding, type mismatch, JNDI lookup error | Bean không tìm thấy hoặc sai type |
| Phù hợp | Demo, tên động có quản lý | Application server/enterprise naming | Mapping do Spring container quản lý |

**Chọn chiến lược dựa trên nơi thật sự chứa sự thật về destination.** Nếu broker dùng auto-create theo naming convention, dynamic có thể đủ. Nếu môi trường triển khai cấp phát Destination qua JNDI, resolver JNDI là phù hợp. Nếu ứng dụng đã có destination beans, dùng BeanFactory. Một chiến lược thống nhất giúp truy vết lỗi tên dễ hơn.

## 9. pubSubDomain: cùng tên nhưng có thể khác loại đích

Một điểm quan trọng là boolean pubSubDomain trong phương thức resolveDestinationName:

- **false** nghĩa Queue (point-to-point), giá trị mặc định của JmsTemplate.
- **true** nghĩa Topic (publish/subscribe).

~~~java
JmsTemplate template = new JmsTemplate(connectionFactory);
template.setPubSubDomain(false); // String sẽ được resolve theo Queue.
template.convertAndSend("orders.events", "ORDER-42");
~~~

Nếu đổi thành:

~~~java
template.setPubSubDomain(true);  // String sẽ được resolve theo Topic.
template.convertAndSend("orders.events", "ORDER-42");
~~~

hai lời gọi đều dùng String "orders.events" nhưng target có thể khác hoàn toàn. Cả hai snippet cần biến connectionFactory đã được cấp; chúng minh họa quyết định domain, không phải hai chương trình độc lập.

### 9.1. Hệ quả thiết kế

- Cấu hình sender là Queue nhưng listener là Topic sẽ dẫn tới việc họ không giao tiếp cùng destination theo cách mong muốn.
- Queue đã được cấu hình đúng nhưng topic chưa có subscription lúc gửi có thể khiến message publish không được nhận lại bởi subscriber non-durable đến sau.
- JndiDestinationResolver thường phải nhận đúng loại Queue/Topic từ binding; đừng hy vọng setPubSubDomain(true) sẽ tự chuyển một Queue object thành Topic.
- Trong ứng dụng có cả queue và topic, nên cấu hình template/listener factory riêng theo mục đích, hoặc dùng Destination object cụ thể ở những nơi cần bảo đảm loại đích.
- **JMS topic không chỉ là queue có nhiều consumer**: mô hình subscription khác nhau và ảnh hưởng việc giữ message/selector/durable subscription.

### 9.2. Định danh tên rõ ràng

Có thể áp dụng quy ước:

~~~text
queue.orders.requests
topic.orders.events
queue.orders.retries
queue.orders.deadletter
~~~

Đây chỉ là quy ước đặt tên trong ứng dụng; broker thực tế có thể áp dụng địa chỉ/routing naming riêng. Thống nhất tên ở publisher/consumer, broker ACL, monitoring và cấu hình triển khai.

## 10. Ví dụ chạy được: Spring Boot 3.3.x + Artemis + Java 17

Phần này tạo một ứng dụng tối giản để **nhìn thấy lúc Spring phân giải tên**. Ứng dụng gửi và đọc một message trên cùng queue bằng JmsTemplate, sử dụng DynamicDestinationResolver bọc bởi một resolver có logging. Code không dùng @JmsListener, tránh việc listener cạnh tranh với receiveAndConvert trong demo đồng bộ.

### 10.1. Chuẩn bị

Cần JDK 17+, Maven 3.9+, Docker và cổng 61616 còn trống. Chạy Apache ActiveMQ Artemis bằng image chính thức:

~~~bash
docker run --detach --rm --name jms-resolver-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Đợi broker sẵn sàng trước khi chạy Spring Boot. Image demo mặc định có user/password artemis/artemis; đây là thông tin dành cho học tập, không dùng ở môi trường thật. Nếu broker cấu hình không cho auto-create, phải khai báo queue demo.orders và cấp quyền trước khi thực thi.

Cấu trúc dự án:

~~~text
spring-jms-resolver-demo/
├── pom.xml
└── src/main/
    ├── java/example/destination/DestinationResolverDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. pom.xml

~~~xml
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
    <groupId>example</groupId>
    <artifactId>spring-jms-resolver-demo</artifactId>
    <version>1.0.0</version>
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

spring-boot-starter-artemis cung cấp các dependency Spring JMS và Artemis client để Spring Boot cấu hình ConnectionFactory. Ví dụ cố định phiên bản Spring Boot 3.3.13 để đảm bảo class/import dựa trên Spring Framework 6.x và jakarta.jms; không dùng namespace javax.jms của Spring 5/Java EE cũ.

### 10.3. application.properties

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

Đây là cấu hình broker native chạy riêng; không dùng embedded broker. Cổng, user/password cần khớp với container đang chạy. Ứng dụng chỉ chạy một CommandLineRunner rồi dừng khi không còn service/thread giữ process; log Spring Boot và Artemis có thể xuất hiện xung quanh stdout của demo.

### 10.4. DestinationResolverDemoApplication.java

~~~java
package example.destination;

import jakarta.jms.ConnectionFactory;
import jakarta.jms.Destination;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

@SpringBootApplication
public class DestinationResolverDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DestinationResolverDemoApplication.class, args);
    }

    @Bean
    JmsTemplate jmsTemplate(ConnectionFactory connectionFactory) {
        DynamicDestinationResolver delegate =
                new DynamicDestinationResolver();

        DestinationResolver tracingResolver =
                (session, destinationName, pubSubDomain) -> {
                    Destination resolved =
                            delegate.resolveDestinationName(
                                    session, destinationName, pubSubDomain);

                    System.out.printf(
                            "resolve %s: %s%n",
                            pubSubDomain ? "topic" : "queue",
                            destinationName);
                    return resolved;
                };

        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(tracingResolver);
        template.setPubSubDomain(false);
        template.setReceiveTimeout(5_000L);
        return template;
    }

    @Bean
    CommandLineRunner demo(JmsTemplate jmsTemplate) {
        return args -> {
            String destinationName = "demo.orders";

            jmsTemplate.convertAndSend(destinationName, "Order-42");
            System.out.println("sent: Order-42");

            Object payload =
                    jmsTemplate.receiveAndConvert(destinationName);
            System.out.println("received: " + payload);
        };
    }
}
~~~

Giải thích:

1. Spring Boot tạo ConnectionFactory từ cấu hình Artemis.
2. Bean jmsTemplate được đăng ký tường minh và gắn tracingResolver. Vì là một bean JmsTemplate, cấu hình template tự động mặc định của Boot sẽ không cần tạo thêm bean trùng mục đích.
3. Trong tracingResolver, delegate là DynamicDestinationResolver chính thức; lambda **không tự thay đổi logic tạo Queue/Topic**.
4. setPubSubDomain(false) khiến "demo.orders" được phân giải theo Queue.
5. convertAndSend trước hết phân giải tên và gửi TextMessage với body "Order-42".
6. receiveAndConvert phân giải cùng tên, nhận rồi chuyển TextMessage thành String theo SimpleMessageConverter mặc định.
7. receiveTimeout 5 giây tránh trường hợp receive chờ mãi khi broker không giao message.

**Trường hợp production:** giữ logging ở mức phù hợp, tránh lộ tên nhạy cảm hoặc đưa dữ liệu payload vào log vô tội vạ. Resolver tùy chỉnh nên đảm bảo policy naming, mapping, validation và exception nhất quán giữa producer và consumer.

### 10.5. Chạy thử và kết quả mong đợi

Trong thư mục có pom.xml:

~~~bash
mvn spring-boot:run
~~~

Khi broker/queue hoạt động bình thường, các dòng do chương trình in sẽ là:

~~~text
resolve queue: demo.orders
sent: Order-42
resolve queue: demo.orders
received: Order-42
~~~

Ngoài ra có log Spring Boot/provider phụ thuộc môi trường. Nếu queue demo.orders đã có message cũ từ lần chạy trước, receiveAndConvert có thể lấy message đó trước; để tái lập output, chạy trên broker/queue thử nghiệm sạch, hoặc dùng tên queue demo riêng cho mỗi lần chạy.

Nếu broker chưa sẵn sàng hoặc cấm auto-create, có thể nhận exception khi phân giải/gửi/nhận. Đừng tự kết luận lỗi ở resolver khi exception thực ra đến từ transport, ACL hoặc thiếu destination vật lý.

Dừng container demo sau khi thực hành:

~~~bash
docker stop jms-resolver-broker
~~~

### 10.6. Hai thí nghiệm nhỏ

**Thí nghiệm 1 – đổi queue thành topic:** đổi setPubSubDomain(false) thành true. Ứng dụng gửi trước rồi mới tạo consumer để nhận, vì thế **topic không có non-durable subscriber tại thời điểm publish có thể mất message đó**. Khi thử topic cần thiết kế subscriber sẵn có hoặc durable/shared subscription thích hợp; không mong chương trình nhận lại như queue.

**Thí nghiệm 2 – tên sai:** đổi destinationName thành "demo.orderz". Nếu broker bật auto-create, chương trình có thể vẫn tự gửi/nhận qua queue mới nên “chạy thành công” dù gửi sai tên nghiệp vụ. Đây là lý do cần naming contract, kiểm tra cấu hình và policy broker thay vì chỉ dựa trên thành công của send.

## 11. Cùng một resolver cho @JmsListener và JmsTemplate

Trong hệ thống thực tế, producer và consumer có thể nằm trong cùng application hoặc ở hai dịch vụ khác nhau. Cần đảm bảo chúng hiểu **cùng tên logic** và **cùng loại destination**.

Ví dụ listener Spring:

~~~java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderListener {
    @JmsListener(destination = "orders.incoming")
    public void handle(String text) {
        // Xử lý message sau khi broker giao vào listener.
    }
}
~~~

Đây chỉ là **snippet trong ứng dụng đã bật JMS listener infrastructure**, không phải chương trình Java độc lập. @JmsListener chọn destination bằng tên String; listener container factory sẽ sử dụng DestinationResolver của nó để phân giải.

Một nhầm lẫn hay gặp: chỉ cấu hình JmsTemplate.setDestinationResolver(custom) rồi tưởng @JmsListener tự dùng cùng custom resolver. **Chúng là các thành phần cấu hình riêng.** Muốn nhất quán, cấu hình resolver phù hợp cho cả template lẫn listener container factory.

Ví dụ minh họa dùng JNDI cho cả hai:

~~~java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.JndiDestinationResolver;

@Configuration
@EnableJms
class JmsDestinationConfig {

    @Bean
    DestinationResolver destinationResolver() {
        JndiDestinationResolver resolver = new JndiDestinationResolver();
        resolver.setCache(true);
        resolver.setFallbackToDynamicDestination(false);
        return resolver;
    }

    @Bean
    JmsTemplate jmsTemplate(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        JmsTemplate template = new JmsTemplate(connectionFactory);
        template.setDestinationResolver(destinationResolver);
        template.setPubSubDomain(false);
        return template;
    }

    @Bean(name = "jmsListenerContainerFactory")
    DefaultJmsListenerContainerFactory listenerFactory(
            ConnectionFactory connectionFactory,
            DestinationResolver destinationResolver) {
        DefaultJmsListenerContainerFactory factory =
                new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);
        factory.setDestinationResolver(destinationResolver);
        factory.setPubSubDomain(false);
        return factory;
    }
}
~~~

Đoạn trên là **khung cấu hình**, chỉ chạy được khi ứng dụng đã cấu hình JNDI provider, những binding tương ứng và các thành phần Spring JMS. Với production, listener factory còn cần cấu hình transaction, acknowledgement, error handling, concurrency, recovery, cache và monitoring theo yêu cầu. Mẫu tối giản trên **không** thay thế toàn bộ Spring Boot JMS auto-configuration khi cần các tùy chọn đó.

Khi gọi:

~~~java
jmsTemplate.convertAndSend("java:/jms/queue/Orders", "Order-42");
~~~

và listener dùng:

~~~java
@JmsListener(destination = "java:/jms/queue/Orders")
~~~

hai nơi đều có thể tra JNDI cùng tên, nếu thực sự dùng bean resolver/factory vừa cấu hình. Phần annotation là snippet, không phải class độc lập.

### 11.1. Khi ứng dụng dùng cả Queue và Topic

Spring listener factory có cấu hình pubSubDomain tương ứng. Có thể đăng ký nhiều listener factory với các cấu hình khác nhau, rồi chọn một factory theo tên:

~~~java
@JmsListener(
    destination = "topic.orders.events",
    containerFactory = "topicListenerFactory")
~~~

Trong đó topicListenerFactory phải được cấu hình setPubSubDomain(true), đúng DestinationResolver và ConnectionFactory. Với JNDI, binding phải trả về Topic phù hợp. Đối với producer, dùng JmsTemplate riêng đã bật pubSubDomain(true), hoặc truyền đối tượng Topic trực tiếp khi cần.

## 12. Viết một resolver tùy chỉnh khi có naming contract

Khi tên trong code cố định theo nghiệp vụ nhưng tên broker thay đổi theo hệ thống, có thể tự hiện thực DestinationResolver để mapping và kiểm tra whitelist.

Ví dụ lớp Java hoàn chỉnh về thuật toán mapping (phải được chạy **trong ứng dụng có Spring JMS dependency và JMS Session**):

~~~java
package example.destination;

import jakarta.jms.Destination;
import jakarta.jms.JMSException;
import jakarta.jms.Session;
import org.springframework.jms.support.destination.DestinationResolutionException;
import org.springframework.jms.support.destination.DestinationResolver;
import org.springframework.jms.support.destination.DynamicDestinationResolver;

public final class MappingDestinationResolver
        implements DestinationResolver {

    private final DynamicDestinationResolver delegate =
            new DynamicDestinationResolver();

    @Override
    public Destination resolveDestinationName(
            Session session,
            String destinationName,
            boolean pubSubDomain) throws JMSException {

        if (pubSubDomain) {
            throw new DestinationResolutionException(
                    "This resolver only accepts queues");
        }

        String physicalName;
        switch (destinationName) {
            case "orders.incoming":
                physicalName = "company.sales.orders.v1";
                break;
            case "payments.incoming":
                physicalName = "company.finance.payments.v1";
                break;
            default:
                throw new DestinationResolutionException(
                        "Unknown logical destination: " + destinationName);
        }

        return delegate.resolveDestinationName(
                session, physicalName, false);
    }
}
~~~

Lớp trên compile trong project có spring-jms/Jakarta Messaging, nhưng **không có main()** nên cần được cài vào JmsTemplate/listener factory để sử dụng. Mẫu này cho phép các call sites chỉ biết "orders.incoming", còn mapping chứa tại một điểm. Để cập nhật mapping ở runtime, cân nhắc version hóa cấu hình, khả năng reload và giám sát sai tên.

**Không nhầm kiểm tra tên với bảo mật:** dù whitelist có thể hạn chế nhầm destination, producer/consumer vẫn phải được broker xác thực và phân quyền. Mapping cũng không bảo đảm message tương thích schema hay có consumer xử lý.

### 12.1. Lỗi trong resolver nên được xử lý ra sao?

Resolver có thể phát sinh JMSException từ Session/provider hoặc DestinationResolutionException khi không tìm được tên. JmsTemplate thường chuyển JMSException sang nhóm JmsException runtime của Spring; lỗi phân giải cũng thường được phản ánh lên call site. Không nên catch tất cả rồi chuyển tên không hợp lệ sang một queue mặc định mà không có sự cho phép nghiệp vụ: làm vậy dễ gửi nhầm dữ liệu.

Đối với hệ thống nhiều producer, nên log ở điểm phù hợp: logical name, physical target, domain, thời điểm, exception category; tuyệt đối tránh log credentials hoặc payload chứa thông tin nhạy cảm.

## 13. Các vấn đề vận hành thường đi kèm resolution

### 13.1. Có thể resolve thành công nhưng send/receive thất bại

Một resolver trả về Queue object không đồng nghĩa broker đã tạo queue. Hãy tách bốn lớp khi chẩn đoán:

1. **Tên ở ứng dụng:** đúng spelling/case, mapping, config và môi trường chưa?
2. **Chiến lược resolution:** đang dùng Dynamic, JNDI, Spring bean hay custom?
3. **Broker/provider:** destination đã được cấp phát, routing mode đúng, ACL/credentials còn hợp lệ chưa?
4. **Message delivery:** có consumer match selector, subscription, transaction/ack và khả năng redelivery không?

Nếu lỗi xuất hiện ngay lúc application khởi động, có thể do JNDI lookup hoặc bean cấu hình sai. Nếu gửi được nhưng không ai nhận, nguyên nhân có thể là queue/topic lệch nhau, selector không match, listener chưa start, hoặc message được gửi vào tên khác.

### 13.2. Tên JNDI khác tên physical

Một tên "java:/jms/queue/Orders" có thể được server bind tới tên "corp.order.in" của broker. Việc copy nguyên tên JNDI sang DynamicDestinationResolver sẽ **không tự tạo cùng mapping**; dynamic thường dùng chuỗi đó làm tên đích JMS, gây lệch môi trường.

Nếu đổi từ JNDI sang dynamic, cần kiểm tra rõ bộ ánh xạ tên và cấu hình broker. Không chỉ thay implementation của resolver rồi kỳ vọng các message tự tìm đúng người nhận.

### 13.3. Cache với nhiều miền/tenant

JndiDestinationResolver cache theo tên. Nếu một ứng dụng đổi destinationName cùng chuỗi "orders" để trỏ đến hai môi trường/tenant khác nhau mà không tách resolver/context/cache, dữ liệu có thể đi sai đích. Dùng naming namespace rõ ràng, lifecycle riêng của resolver theo môi trường và test trước khi đưa vào production.

Các hệ thống multi-tenant cần xác thực/ủy quyền tenant tại tầng application/broker. Việc đưa tenant vào destinationName là lựa chọn kiến trúc cần giới hạn số lượng destination, không nên tự sinh vô hạn queue mà không quản lý.

### 13.4. Spring Boot auto-configuration

Spring Boot thường tạo ConnectionFactory/JmsTemplate và listener infrastructure dựa trên classpath/properties. Nhưng các tùy chọn về **DestinationResolver** là một phần cấu hình Spring JMS. Khi tạo bean JmsTemplate hoặc listener factory tùy chỉnh, phải hiểu những default của Boot có còn được áp dụng hay không.

Nếu ứng dụng dùng cả @JmsListener và JmsTemplate, việc thiếu một cấu hình thống nhất có thể dẫn tới tình trạng producer dùng JNDI còn consumer dùng Dynamic; cả hai cùng viết "orders" nhưng thực tế không cùng Destination.

### 13.5. Không đồng nhất nhiều loại resolver trong Spring

Spring cũng có interface **org.springframework.messaging.core.DestinationResolver<D>** dùng cho abstraction messaging tổng quát. Bài này nói đến **org.springframework.jms.support.destination.DestinationResolver** với phương thức resolveDestinationName(Session, String, boolean) và return type jakarta.jms.Destination. Khi import nhầm interface của Spring Messaging, lambda hoặc cấu hình có thể không compile dù tên đều là DestinationResolver.

## 14. Checklist kiểm tra khi gặp sự cố

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Queue có tên nhưng JmsTemplate báo không tìm thấy | JNDI resolver lookup sai path hoặc binding chưa tồn tại | Kiểm tra JNDI context, tên binding và fallback. |
| Gửi thành công nhưng listener không nhận | Producer/consumer dùng domain hoặc resolver khác nhau | So sánh String, pubSubDomain, JNDI mapping, listener factory. |
| Trên broker xuất hiện queue sai tên | Dynamic resolver + typo, auto-create bật | Whitelist tên, quản trị provisioning, kiểm tra ACL. |
| Chuyển sang topic rồi chương trình không nhận | Subscriber chưa tồn tại khi publish | Thiết kế lifecycle subscription, durable subscription khi cần. |
| Gửi vào queue khác dù String giống nhau | Một nơi JNDI logical name, nơi khác dynamic physical name | Đồng bộ contract resolver và cấu hình broker. |
| Sau JNDI rebind vẫn dùng địa chỉ cũ | Destination cache còn giữ handle cũ | Xem xét removeFromCache/clearCache hoặc disable cache. |
| Queue và topic cùng tên bị nhầm với JNDI cache | Resolver cache theo destination name | Tên riêng cho từng domain, không dùng cùng cache key. |
| Resolver tùy chỉnh không chạy trong @JmsListener | Chỉ cấu hình JmsTemplate, chưa cấu hình container factory | Gắn resolver tương ứng vào listener factory. |
| Kiểu Destination không đúng | JNDI trả Queue nhưng nơi dùng kỳ vọng Topic | Kiểm tra binding type và pubSubDomain. |
| Không tạo được queue trên production | Broker tắt auto-create hoặc ACL không cho phép | Đăng ký destination trước, cấu hình quyền đúng. |
| Nhầm constructor hoặc compile sai type | Import org.springframework.messaging.core.DestinationResolver | Import org.springframework.jms.support.destination.DestinationResolver. |

### 14.1. Các câu hỏi giúp khoanh vùng nhanh

- Ai cấp tên destination: code, properties, JNDI, environment variables hay bảng cấu hình?
- JmsTemplate được tạo bởi Boot hay là bean tùy chỉnh?
- Listener container factory nào thực sự được @JmsListener sử dụng?
- pubSubDomain của phía gửi và nhận có trùng nhau không?
- Resolver trả Destination object loại Queue hay Topic?
- Tên logical và physical có trùng nhau không, và ai sở hữu mapping?
- Broker có auto-create hoặc chỉ cho dùng destination đã đăng ký?
- JNDI cache có giữ mapping cũ sau đợt deploy hay không?
- Một message bị “mất” do resolution hay do selector/transaction/TTL/subscription?

Không đọc trạng thái provider từ tên destination duy nhất. Dùng logs ứng dụng, broker console/metrics, quyền truy cập và cấu hình deployment để xác minh từng lớp.

## 15. Câu hỏi tự kiểm tra

**1. Vì sao JmsTemplate.convertAndSend(String, Object) cần DestinationResolver?**

Vì JMS API làm việc với Destination object, còn method nhận String chỉ cung cấp tên. Resolver chuyển String sang Destination.

**2. pubSubDomain=false dẫn tới hành vi gì khi dùng DynamicDestinationResolver?**

Resolver gọi cơ chế Queue trên JMS Session (Session.createQueue), biểu diễn miền point-to-point.

**3. JNDI resolver có tự tạo queue vật lý không?**

Không. Nó tra cứu binding đã tồn tại; nếu bật fallback, có thể thử dynamic resolution, còn broker provisioning vẫn tùy môi trường.

**4. Default JndiDestinationResolver có fallback sang dynamic khi không thấy binding không?**

Không. fallbackToDynamicDestination mặc định false.

**5. Vì sao tên "orders" có thể đi vào hai destination khác nhau?**

Vì Queue/Topic khác loại, hoặc một bên phân giải qua JNDI logical binding trong khi bên kia lấy chính String làm physical name động.

**6. Khi nào truyền Destination object trực tiếp?**

Khi đã có destination handle hợp lệ và muốn tránh lookup theo String; JmsTemplate có các overload nhận Destination.

**7. Có thể thiết lập resolver trên JmsTemplate rồi mặc nhiên áp dụng cho mọi @JmsListener không?**

Không. Listener container factory được cấu hình riêng; phải kiểm tra và thiết lập resolver của container nếu cần.

**8. Cache JNDI có điểm nào cần cẩn thận?**

Cache theo tên; JNDI binding thay đổi có thể làm handle cũ còn được dùng. Queue và Topic dùng cùng tên có thể gây nhầm khi cache.

**9. DynamicDestinationResolver có bảo đảm tự tạo queue vật lý không?**

Không. Tính năng auto-create và quyền phụ thuộc provider/broker, không do interface DestinationResolver bảo đảm.

**10. DestinationResolver khác MessageConverter ở đâu?**

Resolver quyết định **đích** gửi/nhận; converter quyết định **biểu diễn JMS Message** của payload.

### Bài tập áp dụng

1. Chạy ví dụ mục 10, ghi lại hai lần "resolve queue". Giải thích vì sao gửi và nhận đều phải resolve một tên String.
2. Đổi resolver lambda để ánh xạ "orders.incoming" sang "demo.orders". Giữ consumer/producer dùng cùng tên logic và kiểm tra message được giao.
3. Tạo sai chính tả ở sender trong một broker có auto-create. Quan sát queue mới được tạo và thảo luận cách ngăn lỗi.
4. Viết một custom resolver từ chối mọi tên không nằm trong tập cho phép; kiểm tra exception ở JmsTemplate.
5. Dùng hai JmsTemplate riêng cho Queue và Topic, áp dụng naming khác nhau; giải thích lý do tránh trộn domain.
6. Trong môi trường có JNDI thật, thử setCache(true), rebind destination, rồi gọi removeFromCache để quan sát sự thay đổi.
7. Tạo @JmsListener với containerFactory riêng, kiểm tra resolver của listener và JmsTemplate có cùng mapping không.
8. Mô tả bộ kiểm thử integration cần có để chứng minh ứng dụng gửi đến đúng physical queue trong môi trường staging/production.

## 16. Tài liệu tham khảo chính thức

- Spring Framework — JMS Destination Management: https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Framework — Sending a Message: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.2 — DestinationResolver API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/DestinationResolver.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Spring Framework 6.2 — BeanFactoryDestinationResolver: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/destination/BeanFactoryDestinationResolver.html
- Spring Framework 6.2 — DefaultJmsListenerContainerFactory: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html
- Spring Framework 6.2 — JndiDestinationResolver: https://docs.spring.io/spring-framework/docs/6.2.x-SNAPSHOT/javadoc-api/org/springframework/jms/support/destination/JndiDestinationResolver.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
