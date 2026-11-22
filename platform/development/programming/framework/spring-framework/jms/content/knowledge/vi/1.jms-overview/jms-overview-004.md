# Phân biệt chuẩn API JMS với giao thức truyền tin

## 1. Mục tiêu và kết luận cốt lõi

Khi lập trình hệ thống gửi/nhận message với Java và Spring, cần tách rõ ba câu hỏi:

1. **Ứng dụng gọi API nào?** Java Message Service (JMS), ngày nay thuộc đặc tả **Jakarta Messaging**, đưa ra các interface và ngữ nghĩa gửi/nhận message cho ứng dụng Java.
2. **Dữ liệu đi qua mạng bằng cách nào?** Một **wire protocol** (giao thức trao đổi trên đường truyền) quyết định cách client và broker trao đổi frame, thương lượng kết nối, mã hóa message và xác nhận truyền nhận. Ví dụ: **AMQP 1.0, MQTT, STOMP, OpenWire, Artemis Core**.
3. **Ai thực hiện kết nối, định tuyến và lưu trữ?** **JMS provider/client library** hiện thực API JMS; **message broker** nhận, định tuyến, lưu trữ và chuyển message theo cấu hình.

**Kết luận quan trọng nhất: JMS là chuẩn API Java và ngữ nghĩa messaging; bản thân JMS không quy định wire protocol.** Hai chương trình cùng dùng JMS chưa chắc nói chuyện trực tiếp được nếu chúng sử dụng hai client/provider và hai giao thức không tương thích. Ngược lại, hai chương trình không dùng JMS vẫn có thể trao đổi qua cùng broker nếu broker hỗ trợ các giao thức và cách ánh xạ message tương ứng.

Ví dụ thực tế: một ứng dụng Spring gọi `JmsTemplate.convertAndSend(...)`. Apache ActiveMQ Artemis JMS client có thể chuyển thao tác đó thành Artemis **Core protocol** để nói chuyện với broker. Cùng broker ấy có thể nhận kết nối **AMQP 1.0**, **MQTT** hay **STOMP** từ các client khác. Điều này không biến JMS thành Core, AMQP, MQTT hoặc STOMP.

## 2. JMS chuẩn hóa những gì?

### 2.1. Vị trí và tên gọi

- **JMS** là viết tắt của *Java Message Service*. Trong hệ sinh thái Java EE trước đây, mã nguồn thường import `javax.jms.*`.
- Tên đặc tả hiện đại là **Jakarta Messaging**; với Jakarta Messaging 3.x, namespace là `jakarta.jms.*`. Spring Framework 6+ và Spring Boot 3+ dùng hệ Jakarta. Đổi namespace không đồng nghĩa đổi wire protocol.
- **JMS 1.1/2.0** và **Jakarta Messaging 3.x** là các thế hệ API/đặc tả. Khi đọc tài liệu cũ, cần nhận diện đúng thế hệ thư viện; không trộn `javax.jms.ConnectionFactory` với `jakarta.jms.ConnectionFactory`.

### 2.2. Các thành phần API

| Thành phần JMS/Jakarta Messaging | Vai trò ở tầng API |
| --- | --- |
| `ConnectionFactory` | Điểm vào để tạo kết nối/ngữ cảnh tới provider; thông số URL, xác thực, TLS thường phụ thuộc provider. |
| `Connection`, `Session` (classic API) | Quản lý vòng đời kết nối, phiên, giao dịch và chế độ xác nhận. |
| `JMSContext` (simplified API) | Gộp các thao tác thường gặp để tạo producer/consumer và quản lý tài nguyên thuận tiện hơn. |
| `Destination`, `Queue`, `Topic` | Đích gửi/nhận và hai mô hình tiêu biểu: hàng đợi và chủ đề. |
| `MessageProducer`/`MessageConsumer` hoặc `JMSProducer`/`JMSConsumer` | Gửi/nhận message theo hợp đồng Java. |
| `Message`, `TextMessage`, `BytesMessage`, … | Kiểu dữ liệu message với header, properties và body. |
| `MessageListener` | Callback nhận message bất đồng bộ ở tầng API. |

JMS định nghĩa những thuộc tính/ngữ nghĩa quan trọng như `JMSMessageID`, `JMSCorrelationID`, `JMSReplyTo`, delivery mode (persistent/non-persistent), priority, time-to-live, selectors, acknowledgement và transaction. Tuy nhiên, chi tiết lưu trữ, clustering, cách tạo queue vật lý, cấu hình bảo mật, retry/DLQ và việc ánh xạ chúng thành frame mạng là trách nhiệm của provider/broker và cấu hình vận hành.

**Queue so với Topic:** Với queue, mỗi message thường được phân phối cho một consumer trong nhóm cùng dùng queue; với topic, message được phân phối đến các subscription phù hợp. Subscription bền vững, selector, transaction và acknowledgement có quy tắc cụ thể trong API nhưng kết quả thực tế vẫn phụ thuộc cách provider thực thi và cấu hình.

### 2.3. Ví dụ thuần API: code Java mô tả cùng một hợp đồng

Đoạn dưới là **mảnh code sử dụng API**, chưa phải chương trình tự chạy độc lập vì `factory` phải là `ConnectionFactory` do một JMS provider cụ thể cung cấp, và broker cần đang hoạt động:

~~~java
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSContext;
import jakarta.jms.Queue;

// factory do container/configuration/provider cung cấp.
static void publishOrder(ConnectionFactory factory) {
    try (JMSContext context = factory.createContext()) {
        Queue orders = context.createQueue("orders.demo");
        context.createProducer().send(orders, "ORDER-42");
    }
}
~~~

Lệnh gửi thể hiện **hợp đồng Java**; đoạn code không có tên AMQP, MQTT, STOMP hoặc Core. Muốn biết trên mạng dùng giao thức gì, phải kiểm tra **implementation của `ConnectionFactory`**, driver/client jar, endpoint và cấu hình broker. Chỉ thêm dependency `jakarta.jms-api` sẽ cung cấp interface để biên dịch, **chưa đủ** để kết nối broker khi chạy.

## 3. Wire protocol là gì? Khác API ra sao?

Wire protocol định nghĩa thông điệp trao đổi *giữa các thực thể giao tiếp*, chẳng hạn handshake, framing, encoding, cách định danh đích, flow control, heartbeat, settlement/acknowledgement và xử lý lỗi trên đường truyền. Nó hoạt động trên các transport như TCP hoặc WebSocket và có thể được bảo vệ bằng TLS. **TCP/TLS là transport/bảo mật truyền tải; AMQP/MQTT/STOMP/Core là giao thức messaging; JMS là API ứng dụng.**

| Góc nhìn | JMS / Jakarta Messaging API | Wire protocol messaging |
| --- | --- | --- |
| Định nghĩa chính | Interface, kiểu message và ngữ nghĩa cho mã Java | Quy tắc trao đổi byte/frame giữa client và broker |
| Đối tượng dùng | Lập trình viên ứng dụng Java, thư viện/framework | Client library và broker, kể cả khác ngôn ngữ |
| Ví dụ | `JMSContext`, `Message`, `Queue`, `Session` | AMQP 1.0, MQTT 5, STOMP 1.2, OpenWire, Core |
| Nhìn thấy ở đâu? | Import Java, method call, dependency và cấu hình Spring | Client driver, listener/port, packet capture, broker protocol config |
| Tương thích được đảm bảo? | Độ tương thích ở mức API theo phiên bản đặc tả/implementation | Độ tương thích trên đường truyền khi cả hai phía hỗ trợ cùng phiên bản/cấu hình |
| Những gì không tự bảo đảm | Không chọn sẵn giao thức mạng, broker hay định dạng payload liên ngôn ngữ | Không tự cung cấp các interface JMS và toàn bộ ngữ nghĩa JMS |

**Một API có thể được hiện thực bằng nhiều giao thức; một giao thức có thể được dùng bởi nhiều API.** Ví dụ, AMQP 1.0 có client thuần AMQP ở nhiều ngôn ngữ, đồng thời một JMS provider phù hợp cũng có thể triển khai API JMS trên AMQP 1.0. API chuẩn hóa mã gọi; wire protocol chuẩn hóa trao đổi mạng. Hai loại chuẩn giải quyết hai lớp khác nhau.

### 3.1. Một số giao thức thường gặp

| Giao thức | Đặc điểm chính | Lưu ý khi liên hệ với JMS |
| --- | --- | --- |
| **AMQP 1.0** | Giao thức messaging có wire format, link/settlement và flow control, hướng tới liên thông giữa implementation. | Có thể làm nền cho **JMS client** (ví dụ client JMS dựa trên AMQP) nhưng AMQP **không phải** JMS. Đừng nhầm AMQP 1.0 với các biến thể AMQP 0-9-1. |
| **MQTT 3.1.1 / 5.0** | Giao thức nhẹ, nổi bật với publish/subscribe, topic và QoS 0/1/2; phổ biến ở IoT. | MQTT client thường gọi API MQTT; QoS MQTT **không ánh xạ tự động một-một** sang acknowledgement, transaction hay subscription semantics của JMS. |
| **STOMP 1.2** | Giao thức hướng text frame, dễ kết nối từ nhiều ngôn ngữ, có các frame SEND, SUBSCRIBE, ACK, … | STOMP client không mặc nhiên là JMS client; cách ánh xạ destination/header cần theo broker. |
| **OpenWire** | Giao thức wire gắn với ActiveMQ Classic và các client tương thích. | Java JMS API có thể được client ActiveMQ triển khai bằng OpenWire; đó là lựa chọn implementation. |
| **Artemis Core** | Giao thức native của Apache ActiveMQ Artemis. | JMS/Jakarta Messaging client native của Artemis được xây trên Core; broker có thể tiếp nhận thêm protocol khác. |

Không suy luận một cổng từ một API: `61616` thường gặp ở Artemis/Core hoặc acceptor đa giao thức, `5672` thường gặp với AMQP, `1883` với MQTT, `61613` với STOMP, **nhưng port thực tế do broker cấu hình**. Mở được cổng TCP cũng chưa chứng minh client đã thương lượng đúng wire protocol.

## 4. Sơ đồ luồng thực thi trong Spring JMS

~~~text
Ứng dụng Java (business logic)
       │ gọi JmsTemplate / @JmsListener
       ▼
Spring JMS (resource handling, conversion, listener container)
       │ gọi các interface jakarta.jms.*
       ▼
JMS provider client library (implementation của ConnectionFactory)
       │ mã hóa thao tác JMS thành frame của wire protocol đã chọn
       ▼
Transport TCP/TLS/WebSocket (tùy provider/cấu hình)
       │
       ▼
Message broker (ví dụ Apache ActiveMQ Artemis)
       │ định tuyến, lưu trữ, giao message, xử lý ack/redelivery
       ▼
JMS client phía nhận → listener container → business handler
~~~

Spring JMS cung cấp các tiện ích:
- `JmsTemplate` để gửi và nhận đồng bộ mà không tự viết nhiều thao tác mở/đóng tài nguyên.
- `@JmsListener` và listener container (ví dụ `DefaultMessageListenerContainer`) để tiêu thụ bất đồng bộ, quản lý thread, connection/session và giao dịch.
- `MessageConverter` để chuyển giữa đối tượng Java và JMS message body. **Message converter không thay thế wire protocol.**
- `ConnectionFactory` là ranh giới nối Spring với provider; muốn biết giao thức cần xem provider thực tế và cấu hình kết nối.

**Spring JMS không phải một broker và không định nghĩa một wire protocol mới.** Nếu đổi ActiveMQ Artemis sang provider JMS khác, business code chỉ dùng API chuẩn có thể giữ nhiều phần, nhưng dependency, bean `ConnectionFactory`, địa chỉ, tên đích, bảo mật, transaction và hành vi vận hành vẫn phải kiểm tra lại.

## 5. Thực hành chạy được: Spring Boot gửi/nhận qua JMS

Ví dụ minh họa sự tách lớp: ứng dụng chỉ gọi Spring/JMS, còn **Apache ActiveMQ Artemis JMS client** thực hiện giao tiếp với broker. Yêu cầu: **JDK 17+**, Maven, Docker. Đoạn ví dụ là một project nhỏ hoàn chỉnh; dùng Spring Boot 3.5.7 (Jakarta namespace) để giữ API phù hợp. Có thể thay phiên bản Spring Boot bằng bản tương thích Java 17 đang được quản lý trong dự án thực tế.

**Bước 1 — Chạy broker Artemis trong Docker** (chỉ publish cổng lên máy local để thực hành):

~~~bash
docker run --rm -d --name jms-demo \
  -p 127.0.0.1:61616:61616 \
  -p 127.0.0.1:8161:8161 \
  apache/artemis:latest-alpine
~~~

Image chính thức dùng tài khoản lab mặc định `artemis/artemis`. Đây chỉ là cấu hình **demo local**; triển khai thật cần bảo mật và quản trị tài khoản riêng.

**Bước 2 — Tạo `pom.xml`** tại thư mục project:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jms-api-vs-wire</artifactId>
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

Starter thêm Spring JMS cùng Artemis JMS provider/client. `jakarta.jms-api` chỉ là phần giao diện của stack; ứng dụng cần implementation từ starter để hoạt động.

**Bước 3 — Tạo `src/main/resources/application.properties`:**

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
~~~

`native` nghĩa là kết nối tới broker riêng, không khởi tạo embedded broker. URL trên được đưa cho **Artemis provider**, chứ không phải khai báo rằng “JMS dùng TCP 61616 theo chuẩn”. Với client Artemis mặc định, giao thức messaging ở dưới là **Artemis Core**.

**Bước 4 — Tạo `src/main/java/com/example/jms/MessagingApplication.java`:**

~~~java
package com.example.jms;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
public class MessagingApplication {
    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }

    @Bean
    CommandLineRunner sendOneOrder(JmsTemplate jmsTemplate) {
        return args -> jmsTemplate.convertAndSend("orders.demo", "ORDER-42");
    }
}

@Component
class OrderConsumer {
    @JmsListener(destination = "orders.demo")
    public void onMessage(String body) {
        System.out.println("Received: " + body);
    }
}
~~~

**Bước 5 — Từ thư mục chứa `pom.xml`, chạy:**

~~~bash
mvn spring-boot:run
~~~

Trong log khởi động, khi listener tiêu thụ message thành công, sẽ xuất hiện dòng:

~~~text
Received: ORDER-42
~~~

Các dòng log Spring khác và thứ tự xuất hiện có thể thay đổi. Lệnh `convertAndSend` biến chuỗi thành `TextMessage` qua converter mặc định; `@JmsListener` nhận payload chuỗi. Trong code business **không có mã encode frame Core hay port protocol**, dù các frame này tồn tại trên đường truyền. Broker Artemis trong cấu hình demo có thể tự tạo queue theo chính sách mặc định của instance; ở hệ thống thật thường phải quản lý queue/address, quyền và routing rõ ràng.

Dừng chương trình bằng Ctrl+C, dừng broker:

~~~bash
docker stop jms-demo
~~~

**Điều gì thay đổi nếu muốn dùng AMQP 1.0?** Không thể chỉ đổi `61616` thành `5672` cho client Artemis Core rồi mặc định mọi thứ chạy. Cần **JMS provider/client có triển khai trên AMQP 1.0**, endpoint AMQP được broker mở, cấu hình `ConnectionFactory` phù hợp và kiểm tra mapping semantics. Khi lớp provider được thay đúng, các lời gọi `JmsTemplate`/`@JmsListener` có thể vẫn tương tự; phần giao tiếp mạng đã thay đổi. Đây chính là giá trị của abstraction JMS.

## 6. Tính di động và khả năng tương tác: ba mức cần kiểm tra

1. **Di động ở mã nguồn Java (API portability):** Cả hai provider đều hỗ trợ phiên bản JMS/Jakarta Messaging mà ứng dụng dùng; giới hạn các tính năng vendor-specific. Điều này giúp tái sử dụng logic nhưng **không bảo đảm chạy chỉ bằng cách đổi một URL**.
2. **Tương tác trên mạng (wire interoperability):** Client và broker hiểu cùng giao thức, phiên bản, cơ chế xác thực, TLS, destination mapping và các phần mở rộng cần thiết. Một client MQTT có thể kết nối broker Artemis hỗ trợ MQTT, nhưng không nhờ thế sở hữu API JMS.
3. **Tương thích dữ liệu và nghiệp vụ:** Body dùng chung schema/encoding (JSON, Protobuf, Avro, …), header/property/selector được ánh xạ đúng, thống nhất ý nghĩa destination và delivery. Cùng wire protocol vẫn có thể không đọc được payload của nhau nếu khác schema.

Ví dụ về **hai chiều không suy diễn**:

| Tình huống | Nhận định đúng |
| --- | --- |
| Spring app A và Spring app B đều dùng JMS nhưng driver A = Core, driver B = AMQP | Chỉ biết API giống; cần broker/bridge tương thích để trao đổi message. |
| Java app dùng JMS-over-AMQP và Python app dùng AMQP client | Có thể trao đổi qua broker AMQP khi thống nhất address, message format và routing; Python không cần JMS. |
| Broker hỗ trợ MQTT và STOMP | Chứng minh broker có protocol adapter, **không** chứng minh client MQTT/STOMP tự triển khai JMS. |
| Hai hệ thống đều ghi đích tên `orders.demo` | Tên giống nhau không tự bảo đảm trỏ cùng queue/topic hoặc cùng routing across protocols. |
| Đổi từ `javax.jms.*` sang `jakarta.jms.*` | Thay thế namespace/API generation; wire protocol có thể vẫn giữ nguyên nếu provider hỗ trợ. |

## 7. Những giới hạn cần biết khi thiết kế hệ thống

### 7.1. Acknowledgement, transaction và mức bảo đảm

- JMS đưa ra cơ chế acknowledge và transaction; broker/protocol phải thực hiện chúng, nhưng không được mặc định các protocol khác có ngữ nghĩa tương đương từng chi tiết.
- Trên MQTT, **QoS 0/1/2** nói về mức giao nhận ở các chặng của giao thức MQTT; không được đánh đồng thẳng với `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE` hay transaction JMS.
- Redelivery sau lỗi/rollback có thể tạo **duplicate** ở tầng nghiệp vụ. Consumer cần idempotent (ví dụ lưu business key/processed ID) khi thao tác không thể xử lý lặp.
- `PERSISTENT`, TTL, priority và durable subscription cần được xem cùng cấu hình provider/broker. “Đã gọi send thành công” không tự suy ra end-to-end exactly-once giữa cơ sở dữ liệu và hệ thống message.
- Muốn đồng bộ commit giữa database và JMS cần xem transaction strategy (local JMS transaction, JTA/XA hoặc outbox pattern); wire protocol riêng lẻ không giải quyết toàn bộ nhất quán nghiệp vụ.

### 7.2. Quản trị và bảo mật

JMS không chuẩn hóa API quản trị broker hay một cơ chế chung cho toàn bộ TLS, user/role, certificate, queue creation, cluster/HA hoặc DLQ. Những phần này nằm ở broker/provider và hạ tầng. Vì thế, **khả năng thay JMS provider** cần được kiểm thử không chỉ ở compile-time mà cả deployment, throughput, recovery, permission, monitoring và failure semantics.

### 7.3. Khi nào dùng Spring JMS, khi nào dùng protocol API trực tiếp?

- **Spring JMS:** hệ Java/Spring cần queue/topic semantics chuẩn JMS, transaction/acknowledgement JMS, và tận dụng `JmsTemplate`/listener container.
- **Client AMQP/MQTT/STOMP trực tiếp:** cần tính năng đặc thù giao thức, giao tiếp với thiết bị/stack không Java, hoặc broker không cung cấp provider JMS phù hợp. API code khi đó theo thư viện giao thức.
- **Cần tích hợp hai kiểu client:** kiểm tra khả năng đa giao thức của broker/bridge, routing và schema trước khi chọn. Đừng chọn API chỉ vì tên broker có “JMS” hay chọn giao thức chỉ vì endpoint giống nhau.

## 8. Lỗi tư duy và lỗi cấu hình phổ biến

1. **“JMS là giao thức chạy trên TCP 61616.”** Sai: JMS là API. `61616` chỉ là cổng broker phổ biến, có thể gắn với Core hoặc acceptor đa giao thức.
2. **“Broker hỗ trợ AMQP nên mọi JMS client đều kết nối AMQP được.”** Sai: provider/client được dùng phải thực hiện AMQP 1.0; ví dụ Artemis native client thường dùng Core.
3. **“Thêm `jakarta.jms-api` là đủ gửi message.”** Sai: chỉ có interface; cần provider implementation, connection config và broker.
4. **“`@JmsListener` tự biến payload thành JSON.”** Sai: conversion theo `MessageConverter`. Demo trên dùng String/TextMessage; object JSON cần converter và schema cấu hình phù hợp.
5. **“MQTT topic và JMS Topic là cùng một đối tượng.”** Sai: khác model API/protocol; broker có thể ánh xạ nhưng phải xem tài liệu và cấu hình address/routing.
6. **“Queue name giống nhau thì mọi protocol chia sẻ được message.”** Không chắc: broker có mapping và chính sách anycast/multicast, prefix và routing riêng.
7. **“Send nhận ACK nghĩa là business transaction đã hoàn tất exactly-once.”** Sai: phải phân biệt acknowledgement của client/broker với xử lý nghiệp vụ và transaction database.
8. **“Spring Boot 2 dùng `javax.jms`, Spring Boot 3 dùng `jakarta.jms`, cứ trộn hai bộ jar là được.”** Sai: namespace không tương thích ở mức type; dùng bộ dependency cùng generation.
9. **“Kết nối TCP thành công tức là cấu hình protocol đúng.”** Sai: vẫn có thể fail handshake, SASL/auth, TLS hoặc destination lookup.
10. **“Đổi broker là không cần kiểm thử.”** Sai: cần test retry, redelivery, concurrency, transaction, DLQ, durable topic và message conversion.

### Checklist chẩn đoán nhanh khi lỗi kết nối hoặc không nhận message

- **Dependency:** Có đúng JMS API generation và provider implementation hay không? Bean `ConnectionFactory` thực tế thuộc class/package nào?
- **Endpoint:** URL, port, TLS, user/password, broker đang chạy; endpoint đó bật **giao thức messaging nào**?
- **Mapping:** Tên `Queue`/`Topic`, cấu hình point-to-point/pub-sub, địa chỉ anycast/multicast, subscription và permissions có khớp?
- **Payload:** Body type, encoding, converter, property/filter/selector có thống nhất?
- **Delivery:** Listener startup, queue depth, concurrency, ack/transaction, rollback, redelivery/DLQ, TTL có ảnh hưởng?
- **Quan sát:** Log client/provider và log broker; khi cần, xem protocol acceptor/connection thống kê. Chỉ packet capture khi được phép và có khả năng giải mã TLS phù hợp.

## 9. Tự kiểm tra kiến thức

**Câu 1.** Spring gọi `JmsTemplate` rồi Artemis client gửi frame Core. Vậy Spring “dùng JMS hay Core”?  
**Đáp:** Spring/Java code dùng **JMS API** qua provider; trên dây mạng provider dùng **Core**. Cả hai mô tả hai lớp khác nhau.

**Câu 2.** Python producer AMQP có giao tiếp được với Java JMS consumer?  
**Đáp:** **Có thể**, nếu Java JMS provider và broker cùng hỗ trợ mô hình kết nối phù hợp, thống nhất address/routing và schema message. Không thể kết luận chỉ từ từ “JMS”.

**Câu 3.** Tại sao đổi sang broker khác có thể giữ phần lớn business code nhưng vẫn cần sửa cấu hình?  
**Đáp:** Business logic phụ thuộc API JMS/Spring; kết nối, wire protocol, destination và khả năng đặc thù do provider/broker quyết định.

**Câu 4.** MQTT QoS 2 có đồng nghĩa transaction JMS + database được exactly-once end-to-end không?  
**Đáp:** **Không**. QoS 2 chỉ mang ngữ nghĩa MQTT trong phạm vi giao thức; xử lý nghiệp vụ, lưu database và idempotency là câu chuyện khác.

**Câu 5.** Import `jakarta.jms.ConnectionFactory` cho biết chắc giao thức AMQP không?  
**Đáp:** **Không**. Phải xác định class implementation, dependency và broker protocol endpoint.

## 10. Tài liệu chuẩn để tra cứu

- Jakarta Messaging 3.1 Specification, mục giới thiệu và phần “What Jakarta Messaging does not include” (nêu rõ **không định nghĩa wire protocol**): https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Spring Framework Reference — Using Spring JMS (`JmsTemplate`, `ConnectionFactory` và listener containers): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Spring Boot Reference — JMS và Artemis auto-configuration: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Guide — Messaging with JMS: https://spring.io/guides/gs/messaging-jms/
- ActiveMQ Artemis — Protocols and Interoperability (AMQP, MQTT, STOMP, OpenWire, Core): https://artemis.apache.org/components/artemis/documentation/latest/protocols-interoperability.html
- ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
