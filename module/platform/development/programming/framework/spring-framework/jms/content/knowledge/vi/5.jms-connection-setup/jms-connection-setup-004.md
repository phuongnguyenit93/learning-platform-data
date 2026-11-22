# Địa chỉ broker, thông tin xác thực và tùy chọn kết nối trong Spring JMS

## 1. Mục tiêu và mô hình kết nối

Ứng dụng Spring JMS chỉ có thể gửi hoặc nhận message khi biết **broker nào cần kết nối**, **dùng danh tính nào để đăng nhập** và **thiết lập connection theo chính sách nào**. Đây là phần cấu hình hạ tầng cho producer và consumer, độc lập với nội dung body và nghiệp vụ xử lý message.

~~~text
application.yml / biến môi trường / secret manager
       |  URL + username/password + TLS + retry + resource options
       v
Jakarta JMS ConnectionFactory (provider-specific)
       |
       +--> Spring JmsTemplate ---> Producer ---> broker
       |
       +--> Spring @JmsListener container ---> Consumer ---> broker
       |
       v
Network transport / authentication / authorization
       |
       v
Broker (ví dụ Apache ActiveMQ Artemis)
       +--> Queue và Topic
       +--> routing, persistence, security, HA
~~~

Các thuật ngữ phải tách bạch:

- **Broker URL**: địa chỉ endpoint mà JVM phải kết nối được qua mạng, thường gồm scheme, hostname/IP, port và có thể có tham số riêng của provider.
- **Credential**: username/password hoặc cơ chế xác thực khác, dùng để xác minh danh tính ứng dụng với broker.
- **Authorization**: quyền gửi, nhận, tạo/browse destination sau khi đã xác thực.
- **ConnectionFactory**: đối tượng `jakarta.jms.ConnectionFactory` cung cấp các JMS connection, ẩn các chi tiết provider và transport.
- **Destination**: Queue hoặc Topic có tên như `orders.commands`. Đây không phải địa chỉ host/port của broker.
- **Connection options**: TLS, timeout, retry/reconnect, caching/pooling, client ID, listener concurrency, phiên transaction và một số chính sách riêng của provider.

Bài này dùng **Spring Boot 3.x, Spring Framework 6, Jakarta Messaging và Apache ActiveMQ Artemis** để có ví dụ chạy được. Cấu hình khác nhau giữa Artemis, ActiveMQ Classic, IBM MQ và các JMS provider khác; không thay provider mà giữ nguyên mọi property.

## 2. Hiểu chính xác broker URL

### 2.1. Cấu trúc địa chỉ

Với **Artemis JMS client** và TCP transport:

~~~text
tcp://localhost:61616
 |     |         |
 |     |         +-- port broker acceptor
 |     +------------ hostname/IP nhìn từ JVM
 +------------------ transport scheme của Artemis
~~~

Ví dụ các môi trường:

| Nơi ứng dụng Java chạy | Broker hiện diện ở đâu | Broker URL minh họa |
| --- | --- | --- |
| Java chạy trên máy phát triển | Artemis Docker có publish cổng JMS | `tcp://localhost:61616` |
| Java trong container cùng Docker Compose network | Service có tên `artemis` | `tcp://artemis:61616` |
| Java chạy trên máy trong mạng nội bộ | Broker có DNS nội bộ | `tcp://broker.internal.example:61616` |
| Java trong Kubernetes | Broker có Service DNS | `tcp://artemis.messaging.svc.cluster.local:61616` |

**Lỗi cực thường gặp:** `localhost` bên trong container Java chỉ trỏ đến **container Java**, không trỏ đến container broker hay máy host. Địa chỉ phải phù hợp nơi chương trình thực sự chạy. Nếu broker ở container khác trên cùng network, dùng tên service do Docker/Kubernetes cung cấp hoặc endpoint tương ứng.

Cổng `61616` thường dùng cho Artemis messaging; cổng `8161` thường là web console quản trị. Mở thành công `http://localhost:8161` không chứng minh TCP listener JMS `61616` có thể nhận JMS connection.

### 2.2. Provider/protocol quyết định scheme và URI

JMS là **API chuẩn Java**, không phải một dây giao thức duy nhất:

- Artemis JMS client thường dùng `tcp://host:port` với Artemis Core client protocol/transport tương ứng.
- Một AMQP 1.0 client khác có thể yêu cầu `amqp://` hoặc `amqps://`; đổi prefix trong URL **không** tự chuyển Artemis JMS client thành AMQP provider.
- ActiveMQ Classic hoặc IBM MQ có cách cấu hình URL/factory và đặc tính TLS/HA khác. Khi đổi broker, đối chiếu thư viện provider và tài liệu của provider đó.
- Spring Boot 3 dùng API `jakarta.jms.*`. Thư viện client JMS đời cũ chỉ triển khai `javax.jms.*` không thể thay thế interface Jakarta trực tiếp.

Trước khi xử lý lỗi connection, xác nhận đủ **broker implementation + client JAR + protocol/transport + network endpoint**.

### 2.3. Không nhầm broker URL với tên Queue/Topic

~~~properties
spring.artemis.broker-url=tcp://localhost:61616
~~~

~~~java
jmsTemplate.convertAndSend("orders.commands", "Create order O-42");
~~~

Ở đây `localhost:61616` là đường đến broker. `orders.commands` là tên destination JMS, mặc định là Queue nếu `JmsTemplate` ở queue mode. Một broker có thể có nhiều Queue/Topic. Quyền kết nối vào broker không đương nhiên bao gồm quyền gửi/nhận từng destination.

Nếu broker tắt auto-create Queue, cần tạo destination qua quản trị trước khi client gửi. Nếu Artemis broker được cấu hình routing bất thường, cần kiểm tra address/routing type thay vì chỉ nhìn tên Queue.

## 3. Xác thực, phân quyền và quản lý bí mật

### 3.1. Username/password bảo vệ điều gì?

Khi client tạo JMS connection, broker thường kiểm tra username/password. Sau đó broker kiểm tra **quyền** của danh tính này với destination theo vai trò/ACL.

| Trường hợp | Cần diễn giải |
| --- | --- |
| Không kết nối được TCP | Chưa đến bước xác thực |
| TCP được nhưng đăng nhập bị từ chối | Sai credential, authentication realm hoặc tài khoản bị khóa |
| Đăng nhập thành công, gửi bị `Not authorized` | Thiếu quyền send/create hoặc broker routing policy |
| Gửi được nhưng listener không nhận | Có thể thiếu quyền consume, sai destination, selector hoặc Queue/Topic mode |
| TLS handshake lỗi | Chứng chỉ, CA/truststore, hostname hoặc TLS protocol không hợp lệ; có thể chưa tới bước đăng nhập |

Mỗi service nên dùng tài khoản riêng với quyền tối thiểu, chẳng hạn chỉ `send` tới `orders.commands` và `consume` từ `orders.results`. Không dùng tài khoản quản trị broker cho ứng dụng nghiệp vụ.

### 3.2. Spring Boot đọc credential từ cấu hình ngoài mã

Trong `application.properties` có thể viết:

~~~properties
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
~~~

Dạng `${KEY:default}` sẽ được đổi thành cú pháp placeholder Spring `${KEY:default}` trong file cấu hình thực tế. Trong **bài tập local**, `demo/demo` là tài khoản thử nghiệm; khi triển khai production, bỏ fallback credential, cấp user/password qua secret manager hoặc biến môi trường do nền tảng quản lý. Không commit mật khẩu thật vào repository.

Ví dụ trên **PowerShell**:

~~~powershell
$env:JMS_BROKER_URL = "tcp://localhost:61616"
$env:JMS_BROKER_USER = "demo"
$env:JMS_BROKER_PASSWORD = "demo"
gradle bootRun
~~~

Ví dụ trên **Bash**:

~~~bash
export JMS_BROKER_URL='tcp://localhost:61616'
export JMS_BROKER_USER='demo'
export JMS_BROKER_PASSWORD='demo'
gradle bootRun
~~~

Các dòng dùng password demo chỉ áp dụng cho broker học tập. Không ghi credential vào Git, issue, tài liệu công khai, command line audit hay log. Secret trong biến môi trường vẫn có rủi ro lộ qua quyền quản trị process và hệ thống vận hành; việc quản lý quyền truy cập và vòng đời secret vẫn cần thiết.

### 3.3. Thay mật khẩu khi ứng dụng đang chạy

Đổi secret trong secret store không có nghĩa một JMS connection đã tạo sẽ tự đổi danh tính đăng nhập. Tùy provider và cấu hình factory, connection có thể tiếp tục chạy với credential cũ cho đến khi reconnect, hoặc lần reconnect tiếp theo có thể lấy giá trị cũ nếu factory chưa được tái cấu hình.

Vì thế cần quy trình xoay secret: cấp credential mới, cập nhật môi trường ứng dụng, khởi tạo connection mới/restart instance theo kế hoạch, kiểm thử send/receive, sau đó thu hồi credential cũ. Không log cả mật khẩu cũ và mới để “debug”.

## 4. Các thuộc tính Spring Boot/Artemis quan trọng

Nhờ dependency `spring-boot-starter-artemis`, Spring Boot có thể auto-configure một Artemis `ConnectionFactory`, `JmsTemplate` và listener factory. Khi không dùng JNDI hoặc bean ConnectionFactory tùy biến, các property dưới đây thường đủ để bắt đầu.

| Cấu hình | Công dụng | Lưu ý |
| --- | --- | --- |
| `spring.artemis.mode=native` | Kết nối broker nằm ngoài ứng dụng | Không tự tạo broker embedded |
| `spring.artemis.broker-url` | URI kết nối Artemis | Đúng network namespace và port |
| `spring.artemis.user` | Username broker | Đưa qua secret injection |
| `spring.artemis.password` | Password broker | Không hardcode ở production |
| `spring.jms.pub-sub-domain` | Queue khi `false`; Topic khi `true` | Producer và listener phải dùng đúng domain |
| `spring.jms.cache.enabled` | Cache JMS session/resource theo Boot | Thường bật mặc định |
| `spring.jms.cache.session-cache-size` | Kích thước session cache | Không phải số network connections |
| `spring.jms.listener.auto-startup` | Listener tự khởi động | Mặc định thường bật |
| `spring.jms.listener.min-concurrency` | Concurrent listener thấp nhất | Tốn thêm session/consumer |
| `spring.jms.listener.max-concurrency` | Concurrent listener cao nhất | Phải phù hợp Queue/durable Topic |
| `spring.jms.client-id` | Client ID trên JMS connection | Chỉ đặt khi cần, chú ý trùng khi scale |
| `spring.jms.jndi-name` | Lookup factory từ JNDI | Khi dùng, ưu tiên JNDI so với Artemis auto-configuration |
| `spring.artemis.pool.enabled` | Bật pooled JMS connection factory khi dependency có sẵn | Kiểm thử lifecycle và giới hạn |
| `spring.artemis.pool.max-connections` | Số connection pool tối đa | Không có nghĩa mỗi request một connection |

**Phân lớp:** `spring.artemis.*` định cấu hình provider; `spring.jms.*` định cấu hình phần tích hợp Spring JMS. Các thay đổi về tên property giữa phiên bản Spring Boot cần đối chiếu tài liệu chính thức của bản đang chạy.

## 5. Ví dụ chạy được: Artemis + Spring Boot 3.x + Java 17

Mục tiêu: từ mã Spring, gửi message vào Queue và listener nhận được nó. Một phép thử send–receive có ý nghĩa hơn kiểm tra cổng TCP hoặc thấy ứng dụng startup.

### 5.1. Khởi động Artemis local

Máy cần Docker. Ví dụ dùng image Apache Artemis và chỉ publish cổng lên loopback host:

~~~bash
docker run --detach --rm --name artemis-connect-lab -p 127.0.0.1:61616:61616 -p 127.0.0.1:8161:8161 -e ARTEMIS_USER=demo -e ARTEMIS_PASSWORD=demo apache/artemis:2.57.0
~~~

Chờ broker khởi động hoàn toàn rồi xem log:

~~~bash
docker logs artemis-connect-lab
~~~

Container chỉ phục vụ học tập; khi xóa container, dữ liệu không được bảo đảm tồn tại nếu chưa gắn persistent volume. Artemis thường cho auto-create Queue ở môi trường mẫu. Nếu broker đã siết policy, hãy tạo trước Queue `connectivity.demo` và cấp quyền send/consume.

### 5.2. Dự án Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'spring-jms-connection-lab'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'demo'
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
~~~

Đây là phiên bản cố định để ví dụ nhất quán; với hệ thống thực, dùng bản Spring Boot maintenance/security được tổ chức hỗ trợ. Spring Boot 3.x cần client Jakarta JMS tương thích.

`src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=${JMS_BROKER_URL:tcp://localhost:61616}
spring.artemis.user=${JMS_BROKER_USER:demo}
spring.artemis.password=${JMS_BROKER_PASSWORD:demo}
spring.jms.pub-sub-domain=false
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=5
spring.jms.listener.auto-startup=true
spring.jms.listener.min-concurrency=1
spring.jms.listener.max-concurrency=1
~~~

Trong bản Markdown đã hoàn thiện, các placeholder bắt đầu bằng ký hiệu `$` và tuân theo cú pháp Spring `${NAME:default}`. `pub-sub-domain=false` nghĩa là ví dụ sử dụng Queue.

### 5.3. Main class và kích hoạt listener

`src/main/java/demo/jms/ConnectivityApplication.java`:

~~~java
package demo.jms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class ConnectivityApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConnectivityApplication.class, args);
    }
}
~~~

Spring tự cung cấp ConnectionFactory và JmsTemplate dựa trên starter và external properties. Với ví dụ này không cần tạo thủ công `ActiveMQConnectionFactory`; làm thêm có thể vô tình vô hiệu hóa auto-configuration.

### 5.4. Producer sử dụng ConnectionFactory gián tiếp

`src/main/java/demo/jms/PingPublisher.java`:

~~~java
package demo.jms;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@Component
public class PingPublisher implements ApplicationRunner {

    private final JmsTemplate jmsTemplate;

    public PingPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @Override
    public void run(ApplicationArguments args) {
        jmsTemplate.convertAndSend("connectivity.demo", "ping-001");
        System.out.println("SENT: ping-001");
    }
}
~~~

`convertAndSend` chuyển String thành `TextMessage` theo converter của Spring rồi gửi tới Queue. Khi gặp lỗi tạo connection/đăng nhập/gửi, Spring thường báo một `JmsException` có nguyên nhân bên dưới từ JMS provider. Dòng `SENT` chỉ xuất hiện sau khi phương thức send trả về bình thường.

### 5.5. Listener xác minh quyền nhận

`src/main/java/demo/jms/PingReceiver.java`:

~~~java
package demo.jms;

import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public class PingReceiver {

    @JmsListener(destination = "connectivity.demo")
    public void onPing(String body) {
        System.out.println("RECEIVED: " + body);
    }
}
~~~

Với Queue, message gửi trước khi listener sẵn sàng thường vẫn có thể chờ trong queue theo chính sách broker. Do đó bài tập không phụ thuộc vào một non-durable Topic subscription đang online đúng thời điểm publish.

### 5.6. Chạy và đối chiếu kết quả

~~~bash
gradle bootRun
~~~

Nếu dùng Gradle wrapper của chính dự án, có thể chạy `./gradlew bootRun` trên Bash hoặc `.\gradlew.bat bootRun` trên Windows. Cần JDK 17+ và Gradle tương thích với plugin đã chọn.

Khi broker reachable, credential hợp lệ, Queue được cho phép và producer/consumer có quyền, log sẽ chứa:

~~~text
SENT: ping-001
RECEIVED: ping-001
~~~

**Thứ tự hai dòng có thể đảo** do listener xử lý trên thread khác. Spring/Artemis cũng ghi thêm log của framework. Đây là output ứng dụng đúng ở điều kiện bình thường; lỗi mạng, auth hoặc broker chưa khởi động thì không bảo đảm nhận được cả hai dòng.

Chạy lại ứng dụng sẽ gửi thêm một JMS message mới với **body** giống `ping-001`. Nếu có nhiều consumer/dịch vụ cùng nghe Queue, chỉ một consumer có thể xử lý bản phân phối đó; hãy dừng các ứng dụng khác khi cần quan sát ổn định.

Dừng broker sau khi thực hành:

~~~bash
docker stop artemis-connect-lab
~~~

## 6. CachingConnectionFactory và pooling

Phần lớn ứng dụng cần **tái sử dụng tài nguyên JMS**:

~~~text
ConnectionFactory -> Connection -> Session -> Producer/Consumer
~~~

Tạo/đóng Connection/Session/Producer mới cho mỗi lần gửi có thể tốn tài nguyên. Spring Boot thường dùng `CachingConnectionFactory` bọc provider factory để cache tài nguyên JMS phù hợp.

### 6.1. Caching mặc định

~~~properties
spring.jms.cache.enabled=true
spring.jms.cache.session-cache-size=5
~~~

Ý nghĩa quan trọng:

- `session-cache-size=5` là giới hạn cache **Session** theo các chế độ session/ack, **không phải** số connection broker bắt buộc.
- Producer/session caching có thể giúp các lượt `JmsTemplate` gửi liên tiếp nhanh hơn.
- Listener container có cơ chế quản lý lifecycle resource riêng. Không suy ra mỗi listener thread sẽ dùng chính xác một session lấy từ cache.
- Nếu cấu hình bừa `client ID`, consumer caching hay session reuse khi dùng durable subscription, có thể gặp trùng định danh hoặc tài nguyên không được giải phóng đúng ý.

### 6.2. Khi cần pooled-jms

Khi tải cao cần kiểm soát nhiều connection/session đồng thời, Spring Boot với Artemis hỗ trợ lựa chọn pool nếu thêm thư viện:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
    implementation 'org.messaginghub:pooled-jms'
}
~~~

~~~properties
spring.artemis.pool.enabled=true
spring.artemis.pool.max-connections=8
~~~

Cấu hình trên **bật một phương án pool có giới hạn**, không có nghĩa luôn mở 8 connection. Khi pool đầy, các yêu cầu có thể chờ hoặc lỗi theo chính sách timeout; hãy đo connection count, session count, throughput, độ trễ và quota broker.

Đừng chủ động bọc một connection factory bằng nhiều tầng cache/pool khác nhau nếu không kiểm soát rõ lifecycle. Tăng connection count không tự tăng throughput khi bottleneck nằm ở DB, listener logic hoặc broker storage.

## 7. Timeout, phát hiện mất kết nối và retry

Lỗi kết nối có thể xảy ra ở nhiều thời điểm:

1. Không kết nối được khi ứng dụng startup.
2. Kết nối được nhưng broker/networks gián đoạn trong khi xử lý.
3. Broker restart, session cũ không còn.
4. Failover sang broker backup với trạng thái session/transaction khác.
5. Connection vẫn mở nhưng heartbeat phát hiện peer không phản hồi.

Cần phân biệt **timeout kết nối**, **timeout/heartbeat**, **retry kết nối lần đầu**, **reconnect sau sự cố** và **thời gian chờ nhận message**. Chúng không phải một tham số chung.

### 7.1. Tham số reconnect riêng của Artemis

Ví dụ provider-specific Artemis broker URL:

~~~properties
spring.artemis.broker-url=tcp://localhost:61616?retryInterval=1000&reconnectAttempts=10
~~~

- `retryInterval`: khoảng thời gian cơ sở giữa các lần thử reconnect, tính bằng millisecond.
- `reconnectAttempts`: số lần reconnect sau khi mất kết nối theo hợp đồng Artemis; `-1` thường nghĩa là không giới hạn.
- `initialConnectAttempts` kiểm soát một số kịch bản thất bại ở pha kết nối ban đầu; không nhầm với số lần reconnect sau khi có connection.
- `retryIntervalMultiplier` và `maxRetryInterval` hỗ trợ backoff/giới hạn delay.

Cần kiểm tra cấu hình provider cùng cơ chế recovery của Spring listener container. Không dùng retry vô hạn quá dày: nếu broker thực sự downtime hoặc secret bị từ chối, retry storm chỉ tạo thêm tải và làm log khó đọc.

### 7.2. Heartbeat và connection TTL

Artemis có các cấu hình:

~~~text
tcp://broker.internal:61616?connectionTTL=60000&clientFailureCheckPeriod=30000
~~~

`connectionTTL` (ms) là thời gian connection có thể không nhận dữ liệu trước khi được coi là chết; `clientFailureCheckPeriod` ảnh hưởng ping/phát hiện lỗi. Chúng là **connection liveness options**, không phải **message time-to-live**. Message TTL phải cấu hình ở thao tác send/producer.

Mạng có jitter, GC pause hoặc máy ảo chậm có thể làm các timeout quá ngắn gây false disconnect. Broker cũng có thể áp override; cần xem cả cấu hình phía server.

### 7.3. HA/failover và duplicate

Client có thể reconnect đến broker cũ hoặc backup trong một topology Artemis HA, nhưng tùy chọn như `ha=true` không tự xây cụm broker HA. Nếu mất kết nối lúc producer gửi hoặc consumer ACK, phía ứng dụng có thể không xác định chính xác broker đã commit đến đâu. Khi reconnect có thể xảy ra retry hoặc redelivery.

Với message nghiệp vụ quan trọng, cần **idempotency key**, transaction/ACK hợp lý, giám sát backlog và DLQ. Connection recovery chỉ giúp phục hồi kênh liên lạc; không tự bảo đảm exactly-once cho toàn bộ hệ thống.

## 8. TLS và bảo vệ kết nối

Username/password giải quyết **xác thực**, không mã hóa dữ liệu trên dây. Artemis hỗ trợ TLS thông qua cấu hình transport, ví dụ mẫu URL:

~~~text
tcp://broker.internal.example:61617?sslEnabled=true;verifyHost=true;trustStorePath=/etc/jms/truststore.p12;trustStoreType=PKCS12
~~~

Mẫu này đòi hỏi broker có TLS acceptor tương ứng, hostname khớp chứng chỉ và truststore chứa CA/certificate được tin cậy.

- `sslEnabled=true`: bật TLS cho transport Artemis.
- `verifyHost=true`: kiểm tra hostname kết nối khớp SAN/CN hợp lệ trên certificate.
- `trustStorePath` / `trustStoreType`: nơi lưu chứng chỉ được tin cậy và định dạng.
- Nếu broker yêu cầu **mutual TLS**, client phải có keystore/certificate/private key được cấp và server phải cấu hình xác minh client cert.
- Truststore/keystore password và các khóa bí mật phải được inject bởi runtime an toàn, không nhúng literal password vào URL trong source/log.

**Không tắt `verifyHost` hoặc bật `trustAll` trong production** để vượt qua lỗi handshake. Chỉnh DNS/chứng chỉ, CA/truststore, ngày hết hạn và TLS protocol/cipher cho khớp.

Với môi trường nội bộ đáng tin, TLS vẫn có giá trị: xác thực broker tránh kết nối nhầm endpoint và mã hóa các message có thể chứa dữ liệu nghiệp vụ nhạy cảm.

## 9. Client ID, listener concurrency và destination mode

Ba lựa chọn thường gây lỗi “kết nối được nhưng listener không đúng”:

**Client ID (`spring.jms.client-id`):**

- Client ID có thể dùng để định danh durable Topic subscription.
- Với unshared durable subscription, không cho hai consumer active trùng định danh đồng thời; scale ngang phải thiết kế subscription identity đúng.
- Với Queue bình thường như bài thực hành, không cần gán cùng một client ID cố định cho mọi instance.

**Queue hay Topic (`spring.jms.pub-sub-domain`):**

- `false`: mặc định destination là Queue.
- `true`: mặc định destination là Topic.
- Producer, listener factory và broker routing phải nhất quán. Một message gửi vào Queue sẽ không tự đến Topic cùng tên chỉ vì có consumer khác đăng ký.

**Listener concurrency:**

- `min-concurrency`/`max-concurrency` ảnh hưởng số consumer/session và áp lực resource.
- Queue có thể dùng consumer cạnh tranh để chia tải; Topic có ngữ nghĩa subscription riêng, đặc biệt unshared durable.
- Thay đổi concurrency không sửa được URL sai, credential sai hay ACL bị từ chối.

## 10. Chẩn đoán theo thứ tự từ ngoài vào trong

### 10.1. Bước 1: xác minh network endpoint

Windows PowerShell:

~~~powershell
Test-NetConnection localhost -Port 61616
~~~

Linux có netcat:

~~~bash
nc -vz localhost 61616
~~~

Chỉ kết luận **TCP port reachable**. Bước này **chưa** xác minh Artemis JMS handshake, auth, TLS certificate, ACL hay khả năng nhận message.

Với Docker broker:

~~~bash
docker ps
docker logs artemis-connect-lab
~~~

Nếu Java chạy trong container/pod, kiểm tra DNS, service port và network policy **từ chính container/pod đó**; thử trên host có thể cho kết quả khác.

### 10.2. Bước 2: phân loại lỗi

| Biểu hiện | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Connection refused` | Sai host/port, broker chưa listen, Docker publish port thiếu | Kiểm tra broker log, listener và URL thật |
| `Connect timed out` | Firewall, route, network policy, broker không đáp ứng | Test TCP từ môi trường JVM đang chạy |
| `UnknownHostException` | Sai DNS/service name hoặc khác Docker network | Kiểm tra DNS và namespace của ứng dụng |
| `Authentication failed` | Wrong secret, user không tồn tại, realm không đúng | Kiểm tra secret version và broker auth |
| `Not authorized` khi send | Đăng nhập được nhưng thiếu permission | Kiểm tra send/create ACL của destination |
| Listener không nhận | Sai Queue/Topic mode, destination, selector hoặc consume ACL | Đối chiếu tên/routing, nhận quyền |
| `SSLHandshakeException` | Truststore/CA, SAN/hostname, cipher, TLS version | Kiểm tra broker TLS acceptor và chứng chỉ |
| Local chạy, container lỗi | Dùng `localhost` trong container | Dùng service name/endpoint của broker |
| Trùng clientId | Nhiều instance dùng một ID cố định không phù hợp | Thiết kế định danh durable đúng |
| Nhiều connection bất thường | Tạo factory nhiều lần, pool/concurrency quá cao | Kiểm tra bean lifecycle và metrics broker |
| Sau reconnect có message lặp | ACK/send mơ hồ tại thời điểm lỗi | Idempotency, transaction, redelivery metrics |
| Sau rotate secret vẫn thất bại | Client còn dùng credential cũ | Kiểm tra restart/recreate factory và secret injection |

### 10.3. Bước 3: xác minh end-to-end

Những mốc này **không thể thay cho nhau**:

1. Port TCP reachable.
2. JMS connection được xác thực.
3. Producer gửi message thành công đến một destination.
4. Consumer thực sự nhận message.
5. Xử lý nghiệp vụ và ACK/transaction hoàn tất.

Nếu chỉ thấy “Started Application” mà không có `SENT` và `RECEIVED`, vẫn chưa chứng minh kết nối JMS end-to-end. Đọc exception chain, broker logs và các metric đang có; tuyệt đối không in password ra để tìm lỗi.

## 11. Tình huống vận hành thường gặp

### 11.1. Chuyển từ host sang Docker Compose

Trên host:

~~~properties
spring.artemis.broker-url=tcp://localhost:61616
~~~

Trong container cùng network với service Artemis tên `artemis`:

~~~properties
spring.artemis.broker-url=tcp://artemis:61616
~~~

Cùng broker, cùng port nhưng **hostname cần đổi** vì môi trường thực thi đổi. Với Kubernetes dùng Service DNS tương ứng, không dùng địa chỉ container tạm có thể đổi khi restart.

### 11.2. Staging và production khác tài khoản

Dù cùng một bản JAR, dùng username/secret và endpoint khác theo môi trường. Với secret rotation, theo dõi cả **kết nối mới** và **kết nối đang tồn tại**, bảo đảm không cắt bỏ user cũ trước khi các instance đã chuyển.

### 11.3. Broker HA nhưng ứng dụng vẫn gửi trùng

Một retry khi không chắc send trước đó đã thành công có thể tạo bản message mới. Như vậy lỗi không nhất thiết ở “không reconnect được”; đây là vấn đề transactional ambiguity. Thiết kế `eventId` ổn định ở payload/property và xử lý idempotent để giảm tác động của duplicate.

### 11.4. Kết nối thành công nhưng backlog cứ tăng

Kiểm tra concurrency, thời gian xử lý listener, lỗi ACK/transaction, consumer permission, poison message/DLQ và broker quotas. Tăng số connection không nhất thiết giúp nếu consumer xử lý chậm vì DB hoặc một tài nguyên ngoài broker.

## 12. Bài tập kiểm chứng cấu hình

1. **Đăng nhập sai:** đổi riêng `JMS_BROKER_PASSWORD` thành giá trị sai, chạy lại và xác minh lỗi authentication. Khôi phục đúng credential để nhìn thấy gửi–nhận bình thường.
2. **Sai port:** đổi URL từ `61616` thành port không có listener, xác minh sự khác nhau giữa connection error và authentication error.
3. **Sai host trong container:** đổi `tcp://artemis:61616` thành `tcp://localhost:61616` trong app container độc lập, quan sát lỗi và giải thích network namespace.
4. **Thiếu quyền:** nếu broker hỗ trợ tạo tài khoản chỉ consume, thử publish bằng tài khoản đó và phân biệt send ACL với broker login.
5. **Broker restart:** quan sát recovery với `reconnectAttempts`, ghi thời điểm mất/kết nối lại; kiểm tra message xử lý trùng thay vì mặc định exactly-once.
6. **Cache/pool:** quan sát số sessions/connections broker trước và sau khi đổi `session-cache-size` hoặc bật pool. Giải thích vì sao các con số không bằng nhau.

Khi báo cáo kết quả, ghi version broker, version JMS client, URL **đã loại bỏ secret**, cấu hình retry và exception loại nào xuất hiện. Không đính kèm full environment dump chứa mật khẩu.

## 13. Checklist thiết lập kết nối trước khi deploy

- [ ] Đã xác định đúng JMS provider, Jakarta client, transport/protocol tương thích.
- [ ] Broker URL đúng với network namespace của JVM, đúng host và messaging port.
- [ ] Tài khoản service có credential được quản lý an toàn, có quyền send/consume tối thiểu.
- [ ] TLS, truststore, hostname và certificate được kiểm chứng ở môi trường cần bảo vệ.
- [ ] ConnectionFactory/JmsTemplate/listener factory dùng thống nhất provider đã chọn.
- [ ] Queue/Topic mode, destination và broker routing trùng khớp.
- [ ] Caching/pooling, listener concurrency có giới hạn dựa trên nhu cầu thực tế.
- [ ] Retry/reconnect, timeout và broker HA có chính sách rõ, có giám sát lỗi.
- [ ] Client ID/durable subscription không gây xung đột khi chạy nhiều instance.
- [ ] Đã chạy kiểm thử send–receive và theo dõi ACK/redelivery theo nghiệp vụ.
- [ ] Có phương án rotate credential và kiểm tra kết nối sau rollout.

## 14. Câu hỏi tự đánh giá

**1.** Tại sao `tcp://localhost:61616` chạy trên host nhưng có thể lỗi khi đưa Java vào Docker container khác broker?

Vì `localhost` giờ trỏ tới container Java, nên phải dùng endpoint nhìn được từ container (thường là tên service trên cùng network).

**2.** Mở TCP port thành công đồng nghĩa username/password đúng?

Không. Socket reachability chỉ là tầng mạng; JMS handshake, xác thực và phân quyền chưa được chứng minh.

**3.** `spring.jms.cache.session-cache-size=5` có phải năm broker connections?

Không. Đây là cấu hình cache Session, không phải số network connection hay số consumer bắt buộc.

**4.** Tại sao listener có thể nhận message lặp lại sau failover?

Kết quả ACK/commit có thể không rõ khi mạng đứt; provider có thể redeliver. Cần idempotency và transaction đúng.

**5.** Đặt `ha=true` phía client có tạo ra HA broker?

Không. Broker phải có topology live/backup và khả năng failover thực sự.

**6.** Có nên ghi credential vào broker URL để dễ debug?

Không. Tách secret khỏi URL và log; cấu hình an toàn qua secret injection.

**7.** Cấu hình SSL/TLS có làm tài khoản tự được quyền consume Queue?

Không. TLS bảo vệ đường truyền/định danh certificate; broker ACL vẫn quyết định quyền consume/send.

## 15. Tài liệu tham khảo chính thức

- Spring Boot — JMS / ActiveMQ Artemis: https://docs.spring.io/spring-boot/3.4/reference/messaging/jms.html
- Spring Boot — Common Application Properties: https://docs.spring.io/spring-boot/3.4/appendix/application-properties/index.html
- Spring Framework — Using Spring JMS (Connections/Caching/Listener): https://docs.spring.io/spring-framework/reference/integration/jms/using.html
- Artemis — Using JMS / Jakarta Messaging: https://artemis.apache.org/components/artemis/documentation/latest/using-jms.html
- Artemis — Configuring the Transport (TCP/TLS): https://artemis.apache.org/components/artemis/documentation/latest/configuring-transports.html
- Artemis — Detecting Dead Connections: https://artemis.apache.org/components/artemis/documentation/latest/connection-ttl.html
- Artemis — Core Client Failover: https://artemis.apache.org/components/artemis/documentation/latest/client-failover.html

**Kết luận học tập:** Kết nối JMS vững chắc là sự phối hợp của **địa chỉ broker đúng, protocol/client đúng, credential/ACL hợp lệ, bảo mật truyền tải, vòng đời connection và chính sách phục hồi**. Luôn kiểm chứng bằng một message gửi–nhận thực tế và quan sát các lỗi tại đúng tầng.
